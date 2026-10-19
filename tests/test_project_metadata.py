"""Public, local-only project metadata snapshots."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from _support import workspace
from test_store_runtime import stage
from weavem.bindings import manifest_digest
from weavem.contracts import ContractError, Manifest
from weavem.store import LocalStore


class ProjectMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("WEAVEM_STORE", None)
        os.environ.pop("WEAVEM_ARTIFACTS_DIR", None)

    def _project(self, root: Path, *, store: str = "task-store") -> Path:
        root.mkdir(parents=True, exist_ok=True)
        (root / "weavem.toml").write_text(
            "[weavem]\n"
            f'store = "{store}"\n'
            'work_dir = ".artifacts"\n',
            encoding="utf-8",
        )
        return root

    def _task(self, root: Path, task_id: str, *, version: str = "1.0.0", marker: Path | None = None) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        (root / "task.toml").write_text(
            "[task]\n"
            f'task_id = "{task_id}"\n'
            f'version = "{version}"\n'
            'source = "implementation.py"\n'
            'export = "run"\n',
            encoding="utf-8",
        )
        body = "def run(value):\n    return value\n"
        if marker is not None:
            body = (
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('executed')\n" + body
            )
        (root / "implementation.py").write_text(body, encoding="utf-8")
        return root

    def _flow(self, project: Path, name: str, aliases: list[str], *, marker: Path | None = None) -> Path:
        flows = project / "flows"
        flows.mkdir(exist_ok=True)
        sidecar = flows / f"{name}.toml"
        sidecar.write_text(
            "[flow]\n"
            f'flow_id = "demo.{name}"\n'
            'version = "1.0.0"\n'
            f'source = "{name}.py"\n'
            f'export = "{name}"\n'
            f"tasks = {json.dumps(aliases)}\n",
            encoding="utf-8",
        )
        body = "raise RuntimeError('must not execute')\n"
        if marker is not None:
            body = (
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('executed')\n" + body
            )
        (flows / f"{name}.py").write_text(body, encoding="utf-8")
        return sidecar

    def _release(self, store_root: Path, *, task_id: str = "demo.released", cache_tag: str | None = None):
        candidate = stage(store_root.parent / "candidate", task_id=task_id)
        if cache_tag is not None:
            source = next(candidate.glob("*.py")).read_bytes()
            old = Manifest.from_json_bytes((candidate / "manifest.json").read_bytes())
            replacement = Manifest(
                old.schema, old.task_id, old.version, old.backend, old.module_leaf,
                old.export, old.artifact_name, old.artifact_sha256, old.artifact_size,
                old.source_digest, cache_tag, old.platform, old.ext_suffix,
                old.dependencies, old.description, old.inputs, old.output, old.build,
            )
            self.assertEqual(source, (candidate / old.artifact_name).read_bytes())
            (candidate / "manifest.json").write_bytes(replacement.to_json_bytes())
        return LocalStore(store_root).publish(candidate)

    def _append_local_binding(self, project: Path, alias: str, path: str) -> None:
        with (project / "weavem.toml").open("a", encoding="utf-8") as file:
            file.write(f"\n[tasks.{alias}]\npath = {path!r}\n")

    def _append_release_binding(self, project: Path, alias: str, ref, *, source: str = "task-store", digest: str | None = None) -> None:
        manifest = Manifest.from_json_bytes(ref.manifest_path.read_bytes())
        with (project / "weavem.toml").open("a", encoding="utf-8") as file:
            file.write(
                f"\n[tasks.{alias}]\n"
                f'release = "{manifest.task_id}=={manifest.version}"\n'
                f"source = {source!r}\n"
                f'manifest_sha256 = "{digest or manifest_digest(ref.manifest_path)}"\n'
            )

    def _metadata(self, project: Path | None = None):
        from weavem import Project
        return Project.open(project).metadata()

    def test_snapshot_contains_deduplicated_authored_definitions_bindings_and_flows(self) -> None:
        with workspace() as raw:
            root = self._project(Path(raw) / "project")
            nested = self._task(root / "tasks" / "nested" / "first", "demo.first")
            unbound = self._task(root / "tasks" / "unbound", "demo.unbound")
            extra = self._task(root / "local" / "second", "demo.second")
            self._append_local_binding(root, "first", "tasks/nested/first")
            self._append_local_binding(root, "second", "local/second")
            sidecar = self._flow(root, "pipeline", ["first", "second"])

            snapshot = self._metadata(root)

            self.assertEqual(1, snapshot["schema"])
            self.assertEqual(
                {"root", "config_path", "store_path", "work_dir"}, set(snapshot["project"]))
            self.assertEqual(str(root.resolve()), snapshot["project"]["root"])
            self.assertEqual(str((root / "weavem.toml").resolve()), snapshot["project"]["config_path"])
            self.assertEqual(str((root / "task-store").resolve()), snapshot["project"]["store_path"])
            self.assertEqual(str((root / ".artifacts").resolve()), snapshot["project"]["work_dir"])
            self.assertEqual(
                [str(path / "task.toml") for path in (extra, nested, unbound)],
                [task["path"] for task in snapshot["tasks"]],
            )
            self.assertEqual(["demo.second", "demo.first", "demo.unbound"],
                             [task["metadata"]["task_id"] for task in snapshot["tasks"]])
            self.assertEqual([str(sidecar.resolve())], [flow["path"] for flow in snapshot["flows"]])
            self.assertEqual(["first", "second"], snapshot["flows"][0]["metadata"]["tasks"])
            bindings = {binding["alias"]: binding for binding in snapshot["bindings"]}
            self.assertEqual(str(nested.resolve()), bindings["first"]["path"])
            self.assertEqual(str(extra.resolve()), bindings["second"]["path"])
            self.assertIsNone(bindings["first"]["release"])
            self.assertEqual([], snapshot["releases"])

    def test_open_none_discovers_project_and_existing_handle_rereads_task_and_config(self) -> None:
        with workspace() as raw:
            root = self._project(Path(raw) / "project")
            task = self._task(root / "tasks" / "one", "demo.one")
            nested = root / "nested" / "child"; nested.mkdir(parents=True)
            from weavem import Project
            with patch("weavem.config.Path.cwd", return_value=nested):
                project = Project.open()
            first = project.metadata()
            self.assertEqual(str((task / "task.toml").resolve()), first["tasks"][0]["path"])
            (task / "task.toml").write_text(
                (task / "task.toml").read_text(encoding="utf-8").replace('version = "1.0.0"', 'version = "2.0.0"'),
                encoding="utf-8",
            )
            config = root / "weavem.toml"
            config.write_text(config.read_text(encoding="utf-8").replace('work_dir = ".artifacts"', 'work_dir = "fresh-work"'),
                              encoding="utf-8")
            second = project.metadata()
            self.assertEqual("2.0.0", second["tasks"][0]["metadata"]["version"])
            self.assertEqual(str((root / "fresh-work").resolve()), second["project"]["work_dir"])

    def test_metadata_is_a_fresh_process_no_write_no_prefect_inspection(self) -> None:
        with workspace() as raw:
            root = self._project(Path(raw) / "project")
            task_marker = root / "task-executed"
            flow_marker = root / "flow-executed"
            self._task(root / "tasks" / "one", "demo.one", marker=task_marker)
            self._append_local_binding(root, "one", "tasks/one")
            self._flow(root, "pipeline", ["one"], marker=flow_marker)
            before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            source_root = Path(__file__).resolve().parents[1] / "src"
            code = """
import sys
from weavem import Project
assert 'prefect' not in sys.modules
snapshot = Project.open(sys.argv[1]).metadata()
assert snapshot['tasks'][0]['metadata']['task_id'] == 'demo.one'
assert snapshot['flows'][0]['metadata']['flow_id'] == 'demo.pipeline'
assert 'prefect' not in sys.modules
"""
            environment = os.environ | {"PYTHONPATH": str(source_root)}
            result = subprocess.run(
                [sys.executable, "-B", "-c", code, str(root)],
                cwd=root, env=environment, capture_output=True, text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertFalse(task_marker.exists())
            self.assertFalse(flow_marker.exists())
            after = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            self.assertEqual(before, after)

    def test_released_binding_reads_manifest_without_importing_payload_or_requiring_abi_match(self) -> None:
        with workspace() as raw:
            root = self._project(Path(raw) / "project")
            marker = root / "payload-executed"
            external = root / "external-store"
            ref = self._release(external, cache_tag="cpython-999")
            payload = next(ref.root.glob("*.py"))
            payload.write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('executed')\n",
                encoding="utf-8",
            )
            # The inspector is intentionally metadata-only, so it validates the
            # manifest pin but does not validate/import payload bytes.
            self._append_release_binding(root, "released", ref, source="external-store")
            before_modules = set(sys.modules)
            snapshot = self._metadata(root)
            self.assertFalse(marker.exists())
            self.assertEqual(before_modules, set(sys.modules))
            self.assertEqual(1, len(snapshot["releases"]))
            release = snapshot["releases"][0]
            self.assertEqual("task", release["kind"])
            self.assertEqual(str(ref.root.resolve()), release["root"])
            self.assertEqual("cpython-999", release["metadata"]["python_cache_tag"])
            self.assertEqual(manifest_digest(ref.manifest_path), release["manifest_sha256"])
            self.assertEqual("demo.released==1.0.0", snapshot["bindings"][0]["release"])
            self.assertEqual("external-store", snapshot["bindings"][0]["source"])

    def test_missing_or_invalid_definitions_and_flow_aliases_fail_contextually(self) -> None:
        with workspace() as raw:
            root = self._project(Path(raw) / "project")
            self._flow(root, "bad", ["absent"])
            with self.assertRaisesRegex(ContractError, "absent"):
                self._metadata(root)
            (root / "flows" / "bad.toml").unlink()
            self._append_local_binding(root, "missing", "tasks/missing")
            with self.assertRaisesRegex(ContractError, "missing"):
                self._metadata(root)

            root = self._project(Path(raw) / "malformed")
            malformed = root / "tasks" / "bad"; malformed.mkdir(parents=True)
            (malformed / "task.toml").write_text("[task\ntask_id = 'bad'", encoding="utf-8")
            with self.assertRaises(ContractError):
                self._metadata(root)

    def test_empty_root_and_ignored_store_work_subtrees_do_not_need_valid_task_metadata(self) -> None:
        with workspace() as raw:
            bare = Path(raw) / "bare"; bare.mkdir()
            snapshot = self._metadata(bare)
            self.assertIsNone(snapshot["project"]["config_path"])
            self.assertEqual([], snapshot["tasks"])
            self.assertEqual([], snapshot["flows"])
            self.assertEqual([], snapshot["bindings"])
            self.assertEqual([], snapshot["releases"])

            root = self._project(Path(raw) / "project", store="tasks/store")
            config = root / "weavem.toml"
            config.write_text(config.read_text(encoding="utf-8").replace('work_dir = ".artifacts"', 'work_dir = "tasks/work"'),
                              encoding="utf-8")
            self._task(root / "tasks" / "author", "demo.author")
            for ignored in (root / "tasks" / "store" / "junk", root / "tasks" / "work" / "junk"):
                ignored.mkdir(parents=True)
                (ignored / "task.toml").write_text("not valid TOML [", encoding="utf-8")
            inspected = self._metadata(root)
            self.assertEqual(["demo.author"], [task["metadata"]["task_id"] for task in inspected["tasks"]])

    def test_missing_task_source_and_referenced_release_are_errors(self) -> None:
        with workspace() as raw:
            root = self._project(Path(raw) / "missing-source")
            missing = root / "tasks" / "missing"; missing.mkdir(parents=True)
            (missing / "task.toml").write_text(
                '[task]\ntask_id="demo.missing"\nversion="1.0.0"\nsource="gone.py"\nexport="run"\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ContractError, "gone.py|missing"):
                self._metadata(root)

            root = self._project(Path(raw) / "missing-release")
            with (root / "weavem.toml").open("a", encoding="utf-8") as file:
                file.write(
                    '\n[tasks.unknown]\nrelease="demo.unknown==1.0.0"\n'
                    'source="task-store"\nmanifest_sha256="' + "0" * 64 + '"\n'
                )
            with self.assertRaisesRegex(ContractError, "unknown|not found"):
                self._metadata(root)

    def test_project_inside_global_work_directory_still_discovers_tasks(self) -> None:
        with workspace() as raw:
            work = Path(raw)
            root = self._project(work / "project")
            self._task(root / "tasks" / "one", "demo.one")
            with patch.dict(os.environ, {"WEAVEM_ARTIFACTS_DIR": str(work)}):
                snapshot = self._metadata(root)
            self.assertEqual(str(work), snapshot["project"]["work_dir"])
            self.assertEqual(["demo.one"],
                             [task["metadata"]["task_id"] for task in snapshot["tasks"]])

    def test_release_digest_mismatch_and_symlinked_definition_paths_are_rejected(self) -> None:
        with workspace() as raw:
            root = self._project(Path(raw) / "project")
            ref = self._release(root / "task-store")
            self._append_release_binding(root, "released", ref, digest="0" * 64)
            with self.assertRaisesRegex(ContractError, "digest|sha256|manifest"):
                self._metadata(root)

            root = self._project(Path(raw) / "links")
            real = self._task(root / "real", "demo.real")
            linked = root / "tasks" / "linked"; linked.parent.mkdir()
            try:
                linked.symlink_to(real, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")
            snapshot = self._metadata(root)
            self.assertEqual([], snapshot["tasks"])
            self._append_local_binding(root, "linked", "tasks/linked")
            with self.assertRaisesRegex(ContractError, "symlink"):
                self._metadata(root)

    def test_snapshot_json_is_stable_and_releases_are_deduplicated_by_binding(self) -> None:
        with workspace() as raw:
            root = self._project(Path(raw) / "project")
            ref = self._release(root / "task-store")
            self._append_release_binding(root, "one", ref)
            self._append_release_binding(root, "two", ref)
            one = self._metadata(root)
            two = self._metadata(root)
            self.assertEqual(json.dumps(one, sort_keys=True, separators=(",", ":")),
                             json.dumps(two, sort_keys=True, separators=(",", ":")))
            self.assertEqual(1, len(one["releases"]))
            self.assertEqual(["one", "two"], [binding["alias"] for binding in one["bindings"]])


if __name__ == "__main__":
    unittest.main()
