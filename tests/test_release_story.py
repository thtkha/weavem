"""End-to-end lifecycle regressions: candidates, bindings, and released flows."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from _support import workspace
from weavem.build import BuildError, build, publish
from weavem.bindings import manifest_digest
from weavem.cli import main
from weavem.contracts import IntegrityError, StoreError
from weavem.flows import FlowError, build_flow, load_flow, publish_flow
from weavem.store import LocalStore


class ReleaseStoryTests(unittest.TestCase):
    def _task(self, root: Path, *, value: int = 2) -> Path:
        root.mkdir(parents=True)
        (root / "task.toml").write_text(
            '[task]\ntask_id="story.double"\nversion="1.0.0"\n'
            'source="implementation.py"\nexport="run"\n')
        (root / "implementation.py").write_text(
            f"def run(value):\n    return value * {value}\n")
        tests = root / "tests"; tests.mkdir()
        (tests / "test_task.py").write_text(
            "import unittest\nfrom implementation import run\n\n"
            f"class T(unittest.TestCase):\n    def test_run(self): self.assertEqual(run(3), {value * 3})\n")
        return root

    def _project(self, root: Path) -> None:
        root.mkdir()
        (root / "weavem.toml").write_text('[weavem]\nstore="task-store"\nwork_dir=".artifacts"\n')

    def _release_binding(self, project: Path, ref) -> None:
        with (project / "weavem.toml").open("a") as config:
            config.write("\n[tasks.double]\nrelease=\"story.double==1.0.0\"\n"
                         "source=\"task-store\"\n"
                         f"manifest_sha256=\"{manifest_digest(ref.manifest_path)}\"\n")

    def _flow(self, project: Path, *, undeclared: bool = False, mutate_test: bool = False, submit: bool = False) -> None:
        (project / "flows").mkdir()
        aliases = '["double"]' if not undeclared else '[]'
        (project / "flows" / "story.toml").write_text(
            '[flow]\nschema=1\nflow_id="story.flow"\nversion="1.0.0"\n'
            f'source="story.py"\nexport="story"\ntasks={aliases}\n')
        invocation = "double.submit(value).result()" if submit else "double.fn(value)"
        (project / "flows" / "story.py").write_text(
            "from weavem import flow, task\n"
            "double = task('double')\n"
            "@flow(retries=2)\ndef story(value):\n    return " + invocation + "\n")
        tests = project / "tests" / "flows" / "story"; tests.mkdir(parents=True)
        body = ("from pathlib import Path\nPath('flows/story.py').write_text('bad')\n"
                if mutate_test else "")
        (tests / "test_flow.py").write_text(
            "import unittest\n" + body + "\nclass T(unittest.TestCase):\n"
            "    def test_source(self): self.assertTrue(True)\n")

    def test_local_python_alias_observes_source_edits_without_candidates(self):
        from weavem.runtime import task
        with workspace() as raw:
            root = Path(raw); project = root / "project"; self._project(project)
            local = self._task(project / "tasks" / "double", value=2)
            with (project / "weavem.toml").open("a") as config:
                config.write('\n[tasks.double]\npath="tasks/double"\n')
            wrapped = task("double", project=project)
            self.assertEqual(6, wrapped.fn(3))
            (local / "implementation.py").write_text("def run(value):\n    return value * 4\n")
            self.assertEqual(12, wrapped.fn(3))
            self.assertFalse((project / ".artifacts").exists())

    def test_build_is_unpublished_and_publish_preserves_candidate(self):
        with workspace() as raw:
            root = Path(raw); task = self._task(root / "task")
            candidate = build(task, work_dir=root / "work")
            store = LocalStore(root / "store")
            with self.assertRaises(StoreError): store.resolve("story.double", "1.0.0")
            ref = publish(candidate, store=store)
            self.assertTrue(candidate.root.is_dir())
            self.assertEqual(ref.root, publish(candidate, store=store).root)

    def test_conflicting_task_publications_allow_only_one_version_bytes(self):
        with workspace() as raw:
            root = Path(raw); store = LocalStore(root / "store")
            one = build(self._task(root / "one", value=2), work_dir=root / "work")
            two = build(self._task(root / "two", value=3), work_dir=root / "work")
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda candidate: self._publish_result(candidate, store), (one, two)))
            self.assertEqual(1, sum(result == "published" for result in results))
            self.assertEqual(1, sum(result == "conflict" for result in results))
            self.assertTrue(one.root.is_dir()); self.assertTrue(two.root.is_dir())

    @staticmethod
    def _publish_result(candidate, store):
        try:
            publish(candidate, store=store)
            return "published"
        except StoreError:
            return "conflict"

    def test_cli_release_binding_writes_digest(self):
        with workspace() as raw:
            root = Path(raw); project = root / "project"; self._project(project)
            ref = publish(build(self._task(root / "task"), project=project), store=LocalStore(project / "task-store"))
            self.assertEqual(0, main(["--project", str(project), "task", "use", "double", "--release", "story.double==1.0.0"]))
            config = (project / "weavem.toml").read_text()
            self.assertIn(manifest_digest(ref.manifest_path), config)

    def test_flow_build_rejects_local_dependency_before_workspace(self):
        with workspace() as raw:
            root = Path(raw); project = root / "project"; self._project(project)
            self._flow(project)
            with (project / "weavem.toml").open("a") as config:
                config.write('\n[tasks.double]\npath="tasks/double"\n')
            self._task(project / "tasks" / "double")
            with self.assertRaises(FlowError): build_flow("story", project=project)
            self.assertFalse((project / ".artifacts").exists())

    def test_flow_build_rejects_test_mutation(self):
        with workspace() as raw:
            root = Path(raw); project = root / "project"; self._project(project)
            ref = publish(build(self._task(root / "task"), project=project), store=LocalStore(project / "task-store"))
            self._release_binding(project, ref); self._flow(project, mutate_test=True)
            with self.assertRaisesRegex(FlowError, "mutated"):
                build_flow("story", project=project)

    def test_released_flow_survives_author_source_removal(self):
        with workspace() as raw:
            root = Path(raw); author = root / "author"; self._project(author)
            ref = publish(build(self._task(author / "tasks" / "double"), project=author), store=LocalStore(author / "task-store"))
            self._release_binding(author, ref); self._flow(author)
            flow_ref = publish_flow(build_flow("story", project=author), store=LocalStore(author / "task-store"))
            consumer = root / "consumer"; self._project(consumer)
            shutil.copytree(author / "task-store", consumer / "task-store", dirs_exist_ok=True)
            shutil.rmtree(author)
            self.assertEqual(42, load_flow("story.flow", "1.0.0", project=consumer).fn(21))
            self.assertTrue(flow_ref.root.name)

    def test_released_prefect_submit_keeps_pinned_context_and_options(self):
        from prefect.testing.utilities import prefect_test_harness
        with workspace() as raw:
            root = Path(raw); author = root / "author"; self._project(author)
            task_ref = publish(build(self._task(author / "tasks" / "double"), project=author),
                               store=LocalStore(author / "task-store"))
            self._release_binding(author, task_ref); self._flow(author, submit=True)
            publish_flow(build_flow("story", project=author), store=LocalStore(author / "task-store"))
            consumer = root / "consumer"; self._project(consumer)
            shutil.copytree(author / "task-store", consumer / "task-store")
            # A matching local alias must not replace the released flow pin.
            self._task(consumer / "tasks" / "double", value=9)
            with (consumer / "weavem.toml").open("a") as config:
                config.write('\n[tasks.double]\npath="tasks/double"\n')
            shutil.rmtree(author)
            loaded = load_flow("story.flow", "1.0.0", project=consumer)
            self.assertEqual(2, loaded.retries)
            try:
                with prefect_test_harness():
                    self.assertEqual(42, loaded(21))
            except PermissionError as exc:
                self.skipTest(f"Prefect harness cannot bind a local test port: {exc}")

    def test_loaded_flow_rejects_manifest_change(self):
        with workspace() as raw:
            root = Path(raw); project = root / "project"; self._project(project)
            ref = publish(build(self._task(root / "task"), project=project), store=LocalStore(project / "task-store"))
            self._release_binding(project, ref); self._flow(project)
            publish_flow(build_flow("story", project=project), store=LocalStore(project / "task-store"))
            loaded = load_flow("story.flow", "1.0.0", project=project)
            flow_manifest = next((project / "task-store" / "_flows").glob("*/*/*/manifest.json"))
            data = json.loads(flow_manifest.read_text()); data["export"] = "other"
            flow_manifest.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")))
            with self.assertRaises(IntegrityError): loaded.fn(2)

if __name__ == "__main__":
    unittest.main()
