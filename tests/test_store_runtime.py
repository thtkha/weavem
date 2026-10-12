from __future__ import annotations
import builtins
from pathlib import Path
import sys
import sysconfig
import unittest
from unittest.mock import patch

from _support import workspace

from weavem.contracts import IntegrityError, Manifest, PolicyError, sha256_file, source_digest, module_leaf
from weavem.runtime import load_export, validate_artifact
from weavem.store import LocalStore, StoreError


def stage(root: Path, task_id: str = "demo.double", version: str = "1.0.0", source: bytes = b"def run(x): return x * 2\n") -> Path:
    directory = root; directory.mkdir(parents=True)
    digest = source_digest(source, {"task": task_id, "version": version})
    leaf = module_leaf(task_id, version, digest)
    payload = directory / f"{leaf}.py"; payload.write_bytes(source)
    manifest = Manifest(1, task_id, version, "python", leaf, "run", payload.name, sha256_file(payload), len(source), digest,
                        sys.implementation.cache_tag, sysconfig.get_platform(), None)
    (directory / "manifest.json").write_bytes(manifest.to_json_bytes())
    return directory


class StoreRuntimeTests(unittest.TestCase):
    def test_publish_idempotence_and_version_conflict(self) -> None:
        with workspace() as raw:
            root = Path(raw); store = LocalStore(root / "store")
            first_candidate = stage(root / "one")
            second_candidate = stage(root / "two")
            first = store.publish(first_candidate)
            second = store.publish(second_candidate)
            self.assertEqual(first.root, second.root)
            self.assertTrue(first_candidate.is_dir())
            self.assertTrue(second_candidate.is_dir())
            conflict = stage(root / "three", source=b"def run(x): return x * 3\n")
            with self.assertRaises(StoreError):
                store.publish(conflict)
            self.assertTrue(conflict.is_dir())

    def test_digest_checked_before_policy_or_import(self) -> None:
        with workspace() as raw:
            root = Path(raw); ref = LocalStore(root / "store").publish(stage(root / "stage"))
            payload = next(path for path in ref.root.iterdir() if path.suffix == ".py")
            payload.write_bytes(b"raise RuntimeError('must not import')\n")
            called = False
            def policy(_):
                nonlocal called
                called = True
                return True
            with self.assertRaises(IntegrityError):
                validate_artifact(ref, policy=policy)
            self.assertFalse(called)

    def test_loader_executes_exact_payload(self) -> None:
        with workspace() as raw:
            root = Path(raw); ref = LocalStore(root / "store").publish(stage(root / "stage"))
            self.assertEqual(42, load_export(ref, task_id="demo.double", version="1.0.0")(21))


class LoaderStateTests(unittest.TestCase):
    def test_system_exit_during_import_cleans_owned_module(self) -> None:
        with workspace() as raw:
            root = Path(raw)
            ref = LocalStore(root / "store").publish(stage(
                root / "stage", task_id="cleanup.system-exit", source=b"raise SystemExit('stop')\n"))
            leaf = validate_artifact(ref).module_leaf
            try:
                with self.assertRaises(SystemExit):
                    load_export(ref)
                self.assertNotIn(leaf, sys.modules)
            finally:
                sys.modules.pop(leaf, None)

    def test_failed_import_preserves_replacement_module(self) -> None:
        source = (b"import sys, types\nreplacement = types.ModuleType(__name__)\n"
                  b"replacement.sentinel = True\nsys.modules[__name__] = replacement\n"
                  b"raise RuntimeError('replacement')\n")
        with workspace() as raw:
            root = Path(raw)
            ref = LocalStore(root / "store").publish(stage(
                root / "stage", task_id="cleanup.replacement", source=source))
            leaf = validate_artifact(ref).module_leaf
            try:
                with self.assertRaisesRegex(RuntimeError, "replacement"):
                    load_export(ref)
                self.assertTrue(getattr(sys.modules.get(leaf), "sentinel", False))
            finally:
                sys.modules.pop(leaf, None)

    def test_missing_prefect_fails_before_artifact_execution(self) -> None:
        with workspace() as raw:
            root = Path(raw)
            marker = root / "executed"
            source = (f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n"
                      "def run(): return 1\n").encode()
            ref = LocalStore(root / "store").publish(
                stage(root / "stage", task_id="cleanup.requires-prefect", source=source))
            manifest = validate_artifact(ref)
            original_import = builtins.__import__

            def without_prefect(name, *args, **kwargs):
                if name == "prefect.tasks":
                    raise ImportError("required Prefect dependency is unavailable")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=without_prefect):
                with self.assertRaisesRegex(ImportError, "required Prefect"):
                    load_export(ref)
            self.assertFalse(marker.exists())
            self.assertNotIn(manifest.module_leaf, sys.modules)

    def test_verified_python_module_is_reused_but_policy_is_rechecked(self) -> None:
        source = b"counter = 0\ndef run():\n global counter\n counter += 1\n return counter\n"
        with workspace() as raw:
            root = Path(raw); ref = LocalStore(root / "store").publish(stage(root / "stage", task_id="demo.state", source=source))
            checks: list[str] = []
            def policy(manifest):
                checks.append(manifest.task_id)
                return True
            self.assertEqual(1, load_export(ref, task_id="demo.state", version="1.0.0", policy=policy)())
            self.assertEqual(2, load_export(ref, task_id="demo.state", version="1.0.0", policy=policy)())
            self.assertEqual(["demo.state", "demo.state"], checks)

    def test_failed_import_is_not_left_in_sys_modules(self) -> None:
        source = b"raise RuntimeError('bad import')\n"
        with workspace() as raw:
            root = Path(raw); ref = LocalStore(root / "store").publish(stage(root / "stage", task_id="demo.bad", source=source))
            manifest = validate_artifact(ref)
            with self.assertRaises(RuntimeError):
                load_export(ref, task_id="demo.bad", version="1.0.0")
            self.assertNotIn(manifest.module_leaf, sys.modules)

class AdapterAndCompatibilityTests(unittest.TestCase):
    def test_loaded_python_export_has_artifact_file_metadata_and_exact_request(self) -> None:
        with workspace() as raw:
            root = Path(raw); ref = LocalStore(root / "store").publish(stage(root / "stage", task_id="demo.meta"))
            export = load_export(ref, task_id="demo.meta", version="1.0.0")
            module = sys.modules[export.__module__]
            self.assertEqual(ref.root / validate_artifact(ref).artifact_name, Path(module.__file__))
            with self.assertRaises(IntegrityError):
                load_export(ref, task_id="demo.other", version="1.0.0")

    def test_policy_exception_and_denial_happen_before_import(self) -> None:
        source = b"raise RuntimeError('imported')\n"
        with workspace() as raw:
            root = Path(raw); ref = LocalStore(root / "store").publish(stage(root / "stage", task_id="demo.policy", source=source))
            with self.assertRaises(PolicyError):
                load_export(ref, task_id="demo.policy", version="1.0.0", policy=lambda _: False)
            self.assertNotIn(validate_artifact(ref).module_leaf, sys.modules)
            with self.assertRaises(PolicyError):
                load_export(ref, task_id="demo.policy", version="1.0.0", policy=lambda _: (_ for _ in ()).throw(RuntimeError("no")))

class StoreBoundaryRegressionTests(unittest.TestCase):
    def test_corrupt_payload_and_symlinked_store_are_rejected(self) -> None:
        with workspace() as raw:
            root = Path(raw); staged = stage(root / "stage")
            payload = next(path for path in staged.iterdir() if path.suffix == ".py")
            payload.write_text("def run(): return 0\n")
            with self.assertRaises(StoreError):
                LocalStore(root / "store").publish(staged)
            real = root / "real"; real.mkdir()
            linked = root / "linked"; linked.symlink_to(real, target_is_directory=True)
            with self.assertRaises(StoreError):
                LocalStore(linked).list()

    def test_truthy_policy_does_not_authorize_execution(self) -> None:
        with workspace() as raw:
            root = Path(raw); ref = LocalStore(root / "store").publish(stage(root / "stage", task_id="demo.truthy"))
            with self.assertRaises(PolicyError):
                load_export(ref, task_id="demo.truthy", version="1.0.0", policy=lambda _: "yes")

    def test_existing_module_leaf_is_preserved(self) -> None:
        import types
        with workspace() as raw:
            root = Path(raw); ref = LocalStore(root / "store").publish(stage(root / "stage", task_id="demo.occupied"))
            leaf = validate_artifact(ref).module_leaf
            sentinel = types.ModuleType(leaf)
            sys.modules[leaf] = sentinel
            try:
                with self.assertRaises(IntegrityError):
                    load_export(ref, task_id="demo.occupied", version="1.0.0")
                self.assertIs(sentinel, sys.modules[leaf])
            finally:
                sys.modules.pop(leaf, None)


if __name__ == "__main__":
    unittest.main()
