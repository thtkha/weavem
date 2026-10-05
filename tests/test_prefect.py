"""Acceptance tests for the real Prefect boundary.

Import _support before Prefect so its local-only test environment is established.
"""
from __future__ import annotations

from _support import workspace  # noqa: F401
from pathlib import Path
import unittest

from weavem.build import build
from weavem.store import LocalStore


TASK_TOML = '''[task]
schema = 1
task_id = "{task_id}"
version = "{version}"
backend = "python"
source = "implementation.py"
export = "run"
dependencies = []
'''


def make_task(root: Path, *, task_id: str, version: str = "1.0.0",
              source: str = "def run(value):\n    return value * 2\n") -> Path:
    root.mkdir(parents=True)
    (root / "task.toml").write_text(TASK_TOML.format(task_id=task_id, version=version), encoding="utf-8")
    (root / "implementation.py").write_text(source, encoding="utf-8")
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_implementation.py").write_text(
        "import unittest\nfrom implementation import run\n\n"
        "class ImplementationTests(unittest.TestCase):\n"
        "    def test_export_behavior(self):\n"
        "        self.assertEqual(run(-1), -2)\n",
        encoding="utf-8",
    )
    return root


class PrefectAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._workspace = workspace("prefect-")
        self.root = Path(self._workspace.name)
        self.store = LocalStore(self.root / "store")
        self.work = self.root / "work"

    def tearDown(self) -> None:
        self._workspace.cleanup()

    def _build(self, task_id: str, *, source: str = "def run(value):\n    return value * 2\n") -> None:
        build(make_task(self.root / "author", task_id=task_id, source=source), store=self.store,
              work_dir=self.work, project=self.root)

    def test_task_and_flow_return_real_prefect_objects_and_run_artifact(self) -> None:
        task_id = "prefect.real-flow"
        self._build(task_id)
        from prefect import Flow
        from prefect.tasks import Task
        from prefect.testing.utilities import prefect_test_harness
        from weavem import flow, task

        wrapped = task(task_id, "1.0.0", store=self.store, name="artifact-double")

        @flow(name="artifact-flow")
        def artifact_flow(value: int):
            return wrapped(value, return_state=True)

        self.assertIsInstance(wrapped, Task)
        self.assertIsInstance(artifact_flow, Flow)
        with prefect_test_harness():
            flow_state = artifact_flow(21, return_state=True)
        self.assertTrue(flow_state.is_completed())
        task_state = flow_state.result()
        self.assertTrue(task_state.is_completed())
        self.assertEqual(task_state.result(), 42)

    def test_prefect_retries_a_task_that_fails_once(self) -> None:
        marker = self.root / "attempted"
        task_id = "prefect.retry-once"
        self._build(task_id, source=(
            "from pathlib import Path\n"
            f"MARKER = Path({str(marker)!r})\n"
            "def run(value):\n"
            "    if value >= 0 and not MARKER.exists():\n"
            "        MARKER.write_text('once')\n"
            "        raise RuntimeError('first attempt fails')\n"
            "    return value * 2\n"
        ))
        from prefect.testing.utilities import prefect_test_harness
        from weavem import flow, task

        wrapped = task(task_id, "1.0.0", store=self.store, retries=1, retry_delay_seconds=0)

        @flow
        def retrying_flow() -> int:
            return wrapped(21)

        with prefect_test_harness():
            self.assertEqual(retrying_flow(), 42)
        self.assertTrue(marker.exists())

    def test_zero_retries_leaves_a_normal_prefect_failed_state(self) -> None:
        task_id = "prefect.zero-retry"
        self._build(task_id, source="def run(value):\n    if value < 0:\n        return value * 2\n    raise RuntimeError('always fails')\n")
        from prefect.testing.utilities import prefect_test_harness
        from weavem import flow, task

        wrapped = task(task_id, "1.0.0", store=self.store, retries=0)

        @flow
        def failing_flow():
            return wrapped(21, return_state=True)

        with prefect_test_harness():
            flow_state = failing_flow(return_state=True)
        self.assertTrue(flow_state.is_failed())
        task_state = flow_state.result(raise_on_failure=False)
        self.assertTrue(task_state.is_failed())

    def test_policy_is_rechecked_for_each_task_invocation_before_loading(self) -> None:
        task_id = "prefect.policy-recheck"
        self._build(task_id)
        from prefect.testing.utilities import prefect_test_harness
        from weavem import flow, task

        decisions = [True, False]
        calls: list[str] = []

        def policy(manifest):
            calls.append(manifest.task_id)
            return decisions.pop(0)

        wrapped = task(task_id, "1.0.0", store=self.store, policy=policy)

        @flow
        def policy_flow(value: int) -> int:
            return wrapped(value)

        with prefect_test_harness():
            self.assertEqual(policy_flow(21), 42)
            with self.assertRaises(Exception):
                policy_flow(21)
        self.assertEqual(calls, [task_id, task_id])

    def test_with_options_preserves_prefect_escape_hatches(self) -> None:
        task_id = "prefect.with-options"
        self._build(task_id)
        from prefect import task as prefect_task
        from prefect.testing.utilities import prefect_test_harness
        from weavem import flow, task

        wrapped = task(task_id, "1.0.0", store=self.store, name="original").with_options(name="renamed")

        @prefect_task
        def ordinary_prefect(value: int) -> int:
            return value + 1

        @flow
        def mixed_flow() -> tuple[int, int, int]:
            return wrapped(21), ordinary_prefect(2), 3

        self.assertEqual(wrapped.name, "renamed")
        with prefect_test_harness():
            self.assertEqual(mixed_flow(), (42, 3, 3))


if __name__ == "__main__":
    unittest.main()
