"""Focused command-line regression tests."""
from __future__ import annotations

import unittest
import json
from contextlib import chdir, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import py_compile
import tomllib

from _support import workspace
from weavem.cli import main
from weavem.build import test as run_task_tests, validate
from weavem.runtime import load_export
from weavem.store import LocalStore


class CliTests(unittest.TestCase):
    def test_project_new_creates_minimal_project_convention(self) -> None:
        with workspace("cli-project-") as temporary:
            root = Path(temporary) / "demo"
            self.assertEqual(main(["project", "new", str(root)]), 0)
            self.assertEqual((root / "weavem.toml").read_text(), "[weavem]\n")
            self.assertTrue((root / "tasks").is_dir())
            self.assertTrue((root / "flows" / "__init__.py").is_file())
            readme = (root / "README.md").read_text()
            for instruction in ("weavem task new tasks/my_task", "weavem task use", "weavem flow run",
                                "export", "Project", ".artifacts/", "task-store/"):
                self.assertIn(instruction, readme)
            self.assertEqual(
                (root / ".gitignore").read_text(),
                ".artifacts/\ntask-store/\n__pycache__/\n.venv/\n",
            )
            (root / "weavem.toml").write_text("user-owned edits\n")
            with redirect_stderr(StringIO()):
                self.assertEqual(main(["project", "new", str(root)]), 2)
            self.assertEqual((root / "weavem.toml").read_text(), "user-owned edits\n")

    def test_flow_new_uses_selected_project_and_is_valid_python(self) -> None:
        with workspace("cli-flow-") as temporary:
            root = Path(temporary) / "project"
            self.assertEqual(main(["project", "new", str(root)]), 0)
            with chdir(Path(temporary)):
                self.assertEqual(main(["--project", str(root), "flow", "new", "daily_sync"]), 0)
            flow = root / "flows" / "daily_sync.py"
            self.assertTrue(flow.is_file())
            self.assertIn("@flow\ndef daily_sync():\n    return None", flow.read_text())
            py_compile.compile(str(flow), doraise=True)
            with redirect_stderr(StringIO()):
                self.assertEqual(main(["--project", str(root), "flow", "new", "daily_sync"]), 2)
            self.assertTrue(flow.is_file())

    def test_flow_new_finds_nearest_project_and_rejects_unsafe_names(self) -> None:
        with workspace("cli-flow-names-") as temporary:
            root = Path(temporary) / "project"
            self.assertEqual(main(["project", "new", str(root)]), 0)
            nested = root / "tasks" / "author"
            nested.mkdir(parents=True)
            with chdir(nested):
                self.assertEqual(main(["flow", "new", "report"]), 0)
                for name in ("../escape", "nested/name", "not-valid", "class", "__init__", "__name__", "__debug__", "_private", "tâche", ""):
                    with self.subTest(name=name), redirect_stderr(StringIO()):
                        self.assertEqual(main(["flow", "new", name]), 2)
            self.assertTrue((root / "flows" / "report.py").is_file())
            self.assertFalse((root / "flows" / "escape.py").exists())

    def test_new_commands_refuse_dangling_symlinks(self) -> None:
        with workspace("cli-symlink-") as temporary:
            base = Path(temporary)
            project = base / "project"
            project.symlink_to(base / "missing-project")
            with redirect_stderr(StringIO()):
                self.assertEqual(main(["project", "new", str(project)]), 2)
            self.assertTrue(project.is_symlink())

            real_project = base / "real-project"
            self.assertEqual(main(["project", "new", str(real_project)]), 0)
            flow = real_project / "flows" / "linked.py"
            flow.symlink_to(base / "missing-flow")
            with redirect_stderr(StringIO()):
                self.assertEqual(main(["--project", str(real_project), "flow", "new", "linked"]), 2)
            self.assertTrue(flow.is_symlink())

    def test_flow_new_rejects_symlinked_flow_directory_without_writes(self) -> None:
        with workspace("cli-flow-boundary-") as temporary:
            base = Path(temporary)
            project = base / "project"
            project.mkdir()
            outside = base / "outside"
            outside.mkdir()
            (project / "flows").symlink_to(outside, target_is_directory=True)
            with redirect_stderr(StringIO()):
                self.assertEqual(main(["--project", str(project), "flow", "new", "report"]), 2)
            self.assertEqual(list(outside.iterdir()), [])

    def test_flow_new_preserves_invalid_existing_package_initializer(self) -> None:
        with workspace("cli-flow-initializer-") as temporary:
            project = Path(temporary)
            flows = project / "flows"
            flows.mkdir()
            init = flows / "__init__.py"
            init.symlink_to(project / "missing")
            with redirect_stderr(StringIO()):
                self.assertEqual(main(["--project", str(project), "flow", "new", "report"]), 2)
            self.assertTrue(init.is_symlink())
            self.assertFalse((flows / "report.py").exists())

    def test_name_only_creates_editable_metadata_and_runnable_boilerplate(self) -> None:
        with workspace("cli-simple-") as temporary:
            root = Path(temporary)
            with chdir(root):
                self.assertEqual(main(["task", "new", "double"]), 0)
            task_dir = root / "double"
            metadata = task_dir / "task.toml"
            data = tomllib.loads(metadata.read_text())["task"]
            self.assertEqual(data["task_id"], "double")
            self.assertEqual(data["version"], "0.1.0")
            self.assertEqual(data["backend"], "python")
            self.assertEqual(data["export"], "run")
            self.assertTrue((task_dir / "implementation.py").is_file())
            self.assertTrue((task_dir / "tests" / "test_task.py").is_file())
            run_task_tests(task_dir, work_dir=root / "work")
            output = StringIO()
            with chdir(root), redirect_stdout(output):
                self.assertEqual(main(["task", "build", "double", "--work-dir", str(root / "work")]), 0)
            self.assertFalse((root / "task-store").exists())
            candidate = json.loads(output.getvalue())["root"]
            with chdir(root), redirect_stdout(StringIO()):
                self.assertEqual(main(["task", "publish", candidate]), 0)
            ref = LocalStore(root / "task-store").resolve("double", "0.1.0")
            self.assertEqual(load_export(ref)(21), 21)
            metadata.write_text(metadata.read_text().replace('version = "0.1.0"', 'version = "0.2.0"'))
            self.assertEqual(validate(task_dir)[0].version, "0.2.0")

    def test_validate_and_test_report_success_only_after_passing(self) -> None:
        with workspace("cli-check-messages-") as temporary:
            root = Path(temporary) / "project"
            self.assertEqual(main(["project", "new", str(root)]), 0)
            with chdir(root):
                self.assertEqual(main(["task", "new", "tasks/example"]), 0)
                self.assertEqual(main(["flow", "new", "example"]), 0)
                for kind, target in (("task", "tasks/example"), ("flow", "example")):
                    for action in ("validate", "test"):
                        with self.subTest(kind=kind, action=action):
                            output = StringIO()
                            with redirect_stdout(output):
                                self.assertEqual(main([kind, action, target]), 0)
                            self.assertEqual(output.getvalue(), f"{kind} {action} passed: {target}\n")
                    test_path = (root / "tasks/example/tests/test_task.py" if kind == "task"
                                 else root / "tests/flows/example/test_flow.py")
                    test_path.write_text("import unittest\nclass Failure(unittest.TestCase):\n"
                                         "    def test_failure(self): self.fail('intentional')\n")
                    output, errors = StringIO(), StringIO()
                    with redirect_stdout(output), redirect_stderr(errors):
                        self.assertEqual(main([kind, "test", target]), 2)
                    self.assertEqual(output.getvalue(), "")
                    self.assertIn("intentional", errors.getvalue())
                    metadata = root / ("tasks/example/task.toml" if kind == "task" else "flows/example.toml")
                    metadata.write_text("invalid toml !")
                    with redirect_stdout(output), redirect_stderr(errors):
                        self.assertEqual(main([kind, "validate", target]), 2)
                    self.assertEqual(output.getvalue(), "")

    def test_native_starter_builds_and_runs_the_export(self) -> None:
        with workspace("cli-native-starter-") as temporary:
            root = Path(temporary)
            source = root / "my-task"
            self.assertEqual(main(["task", "new", str(source), "--backend", "cython"]), 0)
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["task", "build", str(source), "--work-dir", str(root / "work")]), 0)
            from weavem.store import ArtifactRef
            ref = ArtifactRef(Path(json.loads(output.getvalue())["root"]))
            self.assertEqual(load_export(ref)("unchanged"), "unchanged")

    def test_nested_directory_infers_id_from_task_name(self) -> None:
        with workspace("cli-nested-") as temporary:
            task_dir = Path(temporary) / "tasks" / "double"
            self.assertEqual(main(["task", "new", str(task_dir)]), 0)
            self.assertEqual(validate(task_dir)[0].task_id, "double")

    def test_optional_flags_override_defaults(self) -> None:
        with workspace("cli-override-") as temporary:
            task_dir = Path(temporary) / "double"
            self.assertEqual(main(["task", "new", str(task_dir), "--id", "company.double",
                                   "--version", "2.0.0", "--backend", "cython"]), 0)
            spec = validate(task_dir)[0]
            self.assertEqual((spec.task_id, spec.version, spec.backend), ("company.double", "2.0.0", "cython"))

    def test_invalid_names_or_overrides_do_not_create_files(self) -> None:
        with workspace("cli-invalid-") as temporary:
            for name, options in (("bad name", []), ("valid", ["--id", ""]),
                                  ("valid", ["--id", "../bad"]), ("valid", ["--version", ""])):
                task_dir = Path(temporary) / name
                with self.subTest(name=name, options=options), redirect_stderr(StringIO()):
                    self.assertEqual(main(["task", "new", str(task_dir), *options]), 2)
                self.assertFalse(task_dir.exists())

    def test_simple_command_preserves_existing_files(self) -> None:
        with workspace("cli-existing-") as temporary:
            task_dir = Path(temporary) / "double"
            self.assertEqual(main(["task", "new", str(task_dir)]), 0)
            metadata = task_dir / "task.toml"
            metadata.write_text("user-owned edits\n")
            with redirect_stderr(StringIO()):
                self.assertEqual(main(["task", "new", str(task_dir)]), 2)
            self.assertEqual(metadata.read_text(), "user-owned edits\n")

    def test_task_new_uses_canonical_task_schema_and_refuses_overwrite(self) -> None:
        with workspace("cli-new-") as temporary:
            task_dir = Path(temporary) / "demo"
            command = ["task", "new", str(task_dir), "--id", "demo.double", "--version", "1.0.0", "--backend", "python"]
            self.assertEqual(main(command), 0)
            self.assertIn('task_id = "demo.double"', (task_dir / "task.toml").read_text())
            self.assertFalse((task_dir / ".github").exists())
            self.assertEqual(main(command), 2)
