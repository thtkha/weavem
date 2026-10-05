"""Focused promotion-lifecycle regression tests."""
from __future__ import annotations

import unittest
from pathlib import Path

from weavem.build import BuildError, build, test as run_task_tests
from weavem.store import LocalStore
from _support import workspace


class BuildLifecycleTests(unittest.TestCase):
    def _author(self, root: Path, *, test_body: str = "self.assertEqual(run(21), 42)") -> Path:
        root.mkdir()
        (root / "task.toml").write_text(
            '[task]\ntask_id = "demo.double"\nversion = "1.0.0"\nsource = "implementation.py"\nexport = "run"\n')
        (root / "implementation.py").write_text("def run(value):\n    return value * 2\n")
        tests = root / "tests"; tests.mkdir()
        (tests / "test_task.py").write_text(
            f"import unittest\nfrom implementation import run\n\nclass TaskTests(unittest.TestCase):\n    def test_run(self):\n        {test_body}\n")
        return root

    def test_missing_or_empty_source_tests_are_rejected(self) -> None:
        with workspace("build-gates-") as temporary:
            root = Path(temporary) / "empty"; root.mkdir()
            (root / "task.toml").write_text('[task]\ntask_id = "demo.empty"\nversion = "1.0.0"\n')
            (root / "implementation.py").write_text("def run():\n    return 1\n")
            with self.assertRaisesRegex(BuildError, "required"):
                run_task_tests(root, work_dir=Path(temporary) / "work")
            (root / "tests").mkdir()
            with self.assertRaisesRegex(BuildError, "at least one test"):
                run_task_tests(root, work_dir=Path(temporary) / "work")

    def test_mutating_source_from_tests_is_rejected(self) -> None:
        with workspace("build-mutate-") as temporary:
            root = self._author(Path(temporary) / "author", test_body="open('implementation.py', 'w').write('bad')")
            for operation in (run_task_tests, build):
                with self.subTest(operation=operation.__name__):
                    with self.assertRaisesRegex(BuildError, "mutated"):
                        operation(root, work_dir=Path(temporary) / "work")
            self.assertEqual((root / "implementation.py").read_text(),
                             "def run(value):\n    return value * 2\n")
            self.assertEqual(list((Path(temporary) / "work").iterdir()), [])

    def test_failed_test_preserves_existing_artifact_and_idempotent_build_cleans_work(self) -> None:
        with workspace("build-publish-") as temporary:
            temporary = Path(temporary); root = self._author(temporary / "author")
            store = LocalStore(temporary / "store"); work = temporary / "project" / "work"
            ref = build(root, store=store, work_dir=work)
            original = ref.manifest_path.read_bytes()
            self.assertEqual(list(work.glob("build-*")), [])
            self.assertEqual(build(root, store=store, work_dir=work).root, ref.root)
            self.assertEqual(list(work.glob("build-*")), [])
            (root / "tests" / "test_task.py").write_text("import unittest\nclass Broken(unittest.TestCase):\n    def test_no(self): self.fail('no')\n")
            with self.assertRaisesRegex(BuildError, "tests failed"):
                build(root, store=store, work_dir=work)
            self.assertEqual(store.resolve("demo.double", "1.0.0").manifest_path.read_bytes(), original)

    def test_relative_work_dir_is_anchored_to_selected_project(self) -> None:
        with workspace("build-root-") as temporary:
            temporary = Path(temporary); project = temporary / "project"; project.mkdir()
            root = self._author(temporary / "author")
            build(root, store=LocalStore(temporary / "store"), project=project, work_dir="nested/work")
            self.assertTrue((project / "nested" / "work").is_dir())
