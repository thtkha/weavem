"""Black-box cross-project task artifact acceptance tests."""
from __future__ import annotations

from _support import ROOT, workspace
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import textwrap
import unittest
from zipfile import ZipFile, ZIP_DEFLATED


TASK_TOML = '''[task]
schema = 1
task_id = "demo.double"
version = "{version}"
backend = "{backend}"
source = "implementation.py"
export = "run"
dependencies = []
'''


class CliEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self._workspace = workspace("cli-e2e-")
        self.root = Path(self._workspace.name)
        self.author = self.root / "author-a"
        self.consumer = self.root / "consumer-b"
        self.store = self.root / "shared-store"
        self.work = self.root / "work"
        self.consumer.mkdir()
        (self.root / "tmp").mkdir()

    def tearDown(self) -> None:
        self._workspace.cleanup()

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        # Core package is intentionally available; author source is not.
        env["PYTHONPATH"] = str(ROOT / "src")
        env["PREFECT_HOME"] = str(self.root / "prefect")
        env["TMPDIR"] = str(self.root / "tmp")
        env["PREFECT_SERVER_ANALYTICS_ENABLED"] = "false"
        env.pop("PREFECT_API_URL", None)
        env.pop("PREFECT_API_KEY", None)
        env.pop("WEAVEM_STORE", None)
        return env

    def _command(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "weavem", *args], cwd=cwd or self.root,
                              env=self._env(), text=True, capture_output=True, check=False)

    def _author_task(self, *, version: str, backend: str, multiplier: int) -> Path:
        directory = self.author / version
        directory.mkdir(parents=True)
        (directory / "task.toml").write_text(TASK_TOML.format(version=version, backend=backend), encoding="utf-8")
        (directory / "implementation.py").write_text(f"def run(value):\n    return value * {multiplier}\n", encoding="utf-8")
        tests = directory / "tests"
        tests.mkdir()
        (tests / "test_implementation.py").write_text(
            "import unittest\nfrom implementation import run\n\n"
            "class TaskTests(unittest.TestCase):\n"
            f"    def test_export_behavior(self):\n        self.assertEqual(run(21), {21 * multiplier})\n",
            encoding="utf-8")
        return directory

    def _build(self, directory: Path) -> None:
        result = self._command("task", "build", str(directory), "--store", str(self.store), "--work-dir", str(self.work))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("manifest", json.loads(result.stdout))

    def _consume(self, version: str, *, default_store: bool = False) -> dict[str, object]:
        script = self.consumer / "consume.py"
        script.write_text(textwrap.dedent("""
            import json
            import socket
            import sys

            def deny_external(event, args):
                if event != "socket.connect":
                    return
                address = args[1]
                host = address[0] if isinstance(address, tuple) else ""
                if host not in {"127.0.0.1", "::1", "localhost"}:
                    raise PermissionError("consumer rejects non-loopback socket.connect")

            sys.addaudithook(deny_external)
            from prefect.testing.utilities import prefect_test_harness
            from weavem import flow, task
            from weavem.store import LocalStore

            options = {} if sys.argv[3] == "default" else {"store": LocalStore(sys.argv[1])}
            wrapped = task("demo.double", sys.argv[2], **options)
            @flow
            def consume():
                return wrapped(21)
            with prefect_test_harness():
                value = consume()
            module = next(m for name, m in sys.modules.items() if name.startswith("_weavem_demo_double_"))
            print(json.dumps({"value": value, "module_file": module.__file__}))
        """), encoding="utf-8")
        mode = "default" if default_store else "explicit"
        result = subprocess.run([sys.executable, str(script), str(self.store), version, mode], cwd=self.consumer,
                                env=self._env(), text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout.splitlines()[-1])

    def test_extracted_folder_runs_from_default_store_without_author_or_registration(self) -> None:
        self._build(self._author_task(version="1.0.0", backend="python", multiplier=2))
        self._build(self._author_task(version="1.0.1", backend="cython", multiplier=4))
        bundle = self.consumer / "company-tasks.zip"
        with ZipFile(bundle, "w", compression=ZIP_DEFLATED) as archive:
            for path in self.store.rglob("*"):
                if path.is_file():
                    archive.write(path, Path("task-store") / path.relative_to(self.store))
        shutil.rmtree(self.author)
        shutil.rmtree(self.store)
        with ZipFile(bundle) as archive:
            self.assertTrue(all(name.startswith("task-store/") for name in archive.namelist()))
            archive.extractall(self.consumer)
        bundle.unlink()
        # No consumer build, publish, registry, or configuration step.
        extracted_store = self.consumer / "task-store"
        listing = self._command("task", "list", "--json", cwd=self.consumer)
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertEqual(len(json.loads(listing.stdout)), 2)
        for version, expected in (("1.0.0", 42), ("1.0.1", 84)):
            result = self._consume(version, default_store=True)
            self.assertEqual(result["value"], expected)
            self.assertTrue(Path(str(result["module_file"])).is_relative_to(extracted_store))
        self.assertFalse((self.consumer / ".weavem").exists())

    def test_python_artifact_isolated_from_changed_and_removed_author_source(self) -> None:
        author = self._author_task(version="1.0.0", backend="python", multiplier=2)
        self._build(author)
        (author / "implementation.py").write_text("def run(value):\n    return 999\n", encoding="utf-8")
        first = self._consume("1.0.0")
        (author / "implementation.py").unlink()
        second = self._consume("1.0.0")
        self.assertEqual(first["value"], 42)
        self.assertEqual(second["value"], 42)
        self.assertTrue(Path(str(second["module_file"])).is_relative_to(self.store))

    def test_exact_pin_selects_new_version_without_changing_weavem(self) -> None:
        self._build(self._author_task(version="1.0.0", backend="python", multiplier=2))
        self._build(self._author_task(version="1.0.1", backend="python", multiplier=4))
        self.assertEqual(self._consume("1.0.0")["value"], 42)
        self.assertEqual(self._consume("1.0.1")["value"], 84)

    def test_cython_artifact_consumes_through_the_same_prefect_task_boundary(self) -> None:
        self._build(self._author_task(version="1.0.0", backend="cython", multiplier=2))
        result = self._consume("1.0.0")
        self.assertEqual(result["value"], 42)
        self.assertTrue(str(result["module_file"]).endswith(tuple(__import__("importlib").machinery.EXTENSION_SUFFIXES)))

    def test_json_discovery_does_not_execute_payload(self) -> None:
        author = self._author_task(version="1.0.0", backend="python", multiplier=2)
        self._build(author)
        ref = next(self.store.glob("*/*/*"))
        manifest = json.loads((ref / "manifest.json").read_text(encoding="utf-8"))
        (ref / manifest["artifact_name"]).write_text("raise RuntimeError('payload must not execute')\n", encoding="utf-8")
        listing = self._command("task", "list", "--store", str(self.store), "--json")
        info = self._command("task", "info", "demo.double==1.0.0", "--store", str(self.store), "--json")
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertEqual(info.returncode, 0, info.stderr)
        self.assertEqual(json.loads(info.stdout)["task_id"], "demo.double")

    def test_work_directory_override_contains_build_staging(self) -> None:
        author = self._author_task(version="1.0.0", backend="python", multiplier=2)
        self._build(author)
        self.assertTrue(self.work.is_dir())
        self.assertFalse((self.author / ".artifacts").exists())


if __name__ == "__main__":
    unittest.main()
