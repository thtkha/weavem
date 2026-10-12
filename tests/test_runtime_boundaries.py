"""Universal checks remain enforced for injected stores and cached artifacts."""
from contextlib import chdir
from dataclasses import replace
import errno
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from _support import workspace
from test_store_runtime import stage
from weavem import task
from weavem.contracts import CompatibilityError, IntegrityError, Manifest, ManifestError, PolicyError, StoreError
from weavem.runtime import load_export, validate_artifact
from weavem.store import ArtifactRef, LocalStore


class RuntimeBoundaryTests(unittest.TestCase):
    def test_injected_store_ignores_malformed_ambient_project(self):
        with workspace() as raw:
            root = Path(raw)
            store = LocalStore(root / "store")
            ref = store.publish(stage(root / "stage", task_id="boundary.explicit"))
            (root / "weavem.toml").write_text("[invalid TOML")

            class CustomStore:
                def resolve(self, task_id, version):
                    return ref

            with chdir(root):
                for selected in (store, CustomStore()):
                    for project in (None, root):
                        with self.subTest(store=type(selected).__name__, project=project):
                            wrapped = task("boundary.explicit", "1.0.0",
                                           store=selected, project=project)
                            self.assertEqual(wrapped.fn(21), 42)

    def test_corrupt_cross_filesystem_copy_cannot_be_published(self):
        with workspace() as raw:
            root = Path(raw)
            staged = stage(root / "stage", task_id="boundary.corrupt-copy")
            copyfile = shutil.copyfile

            def corrupt_copy(source, destination):
                result = copyfile(source, destination)
                if Path(destination).suffix == ".py":
                    Path(destination).write_bytes(b"corrupt")
                return result

            with patch("weavem.store.os.replace", side_effect=OSError(errno.EXDEV, "different filesystems")), \
                    patch("weavem.store.shutil.copyfile", side_effect=corrupt_copy):
                with self.assertRaises(StoreError):
                    LocalStore(root / "store").publish(staged)
            self.assertTrue(staged.is_dir())
            self.assertEqual(list((root / "store").glob("*/*/*")), [])

    def test_cross_filesystem_publication_copies_then_atomically_renames(self):
        with workspace() as raw:
            root = Path(raw)
            staged = stage(root / "stage", task_id="boundary.cross-filesystem")
            original_replace = os.replace
            calls = []

            def cross_device_once(source, destination):
                calls.append((Path(source), Path(destination)))
                return original_replace(source, destination)

            with patch("weavem.store.os.replace", side_effect=cross_device_once):
                ref = LocalStore(root / "store").publish(staged)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0].parent, ref.root.parent)
            self.assertTrue(staged.exists())
            self.assertEqual(load_export(ref)(21), 42)

    def test_symlinked_task_ancestor_cannot_resolve_or_publish(self):
        with workspace() as raw:
            root = Path(raw)
            outside = LocalStore(root / "outside")
            outside.publish(stage(root / "one", task_id="boundary.symlink"))
            store = LocalStore(root / "store")
            store.root.mkdir()
            (store.root / "boundary.symlink").symlink_to(outside.root / "boundary.symlink", target_is_directory=True)
            with self.assertRaises(StoreError):
                store.resolve("boundary.symlink", "1.0.0")
            with self.assertRaises(StoreError):
                store.publish(stage(root / "two", task_id="boundary.symlink", version="2.0.0"))
            self.assertFalse((outside.root / "boundary.symlink" / "2.0.0").exists())

    def test_policy_requires_explicit_true_and_contract_fields_are_canonical(self):
        with workspace() as raw:
            ref = ArtifactRef(stage(Path(raw) / "stage", task_id="boundary.policy"))
            manifest = validate_artifact(ref)
            for decision in (None, 1, "yes", False):
                with self.subTest(decision=decision), self.assertRaises(PolicyError):
                    load_export(ref, policy=lambda _: decision)
            data = manifest.to_mapping()
            self.assertIn("task_id", data)
            for change in ({"id": "boundary.policy"}, {"description": 123},
                           {"python_cache_tag": "../../escape"}, {"module_leaf": 123},
                           {"backend": ["python"]}):
                with self.assertRaises(ManifestError):
                    Manifest.from_mapping(data | change)

    def test_abi_and_dependency_checks_precede_import(self):
        with workspace() as raw:
            root = Path(raw)
            ref = ArtifactRef(stage(root / "stage", task_id="boundary.compatibility",
                                    source=b"raise RuntimeError('must not import')\n"))
            original = Manifest.from_json_bytes(ref.manifest_path.read_bytes())
            variants = (
                replace(original, python_cache_tag="cpython-000"),
                replace(original, platform="unsupported-platform"),
                replace(original, dependencies=("weavem-missing-distribution-987654321==1",)),
                replace(original, dependencies=("prefect==0.0.0",)),
            )
            for manifest in variants:
                with self.subTest(manifest=manifest):
                    ref.manifest_path.write_bytes(manifest.to_json_bytes())
                    with self.assertRaises(CompatibilityError):
                        load_export(ref)

    def test_injected_store_cannot_bypass_requested_identity(self):
        with workspace() as raw:
            ref = ArtifactRef(stage(Path(raw) / "stage", task_id="boundary.actual"))

            class WrongStore:
                def resolve(self, task_id, version):
                    return ref

            wrapped = task("boundary.requested", "1.0.0", store=WrongStore())
            with self.assertRaises(IntegrityError):
                wrapped.fn(21)

    def test_versions_coexist_and_cached_exports_are_revalidated(self):
        with workspace() as raw:
            root = Path(raw)
            store = LocalStore(root / "store")
            first = store.publish(stage(root / "one", task_id="boundary.versions"))
            second = store.publish(stage(root / "two", task_id="boundary.versions", version="2.0.0",
                                         source=b"def run(x): return x * 4\n"))
            self.assertEqual(load_export(first)(21), 42)
            self.assertEqual(load_export(second)(21), 84)
            payload = first.root / validate_artifact(first).artifact_name
            payload.write_bytes(b"def run(x): return 999\n")
            with self.assertRaises(IntegrityError):
                load_export(first)


if __name__ == "__main__":
    unittest.main()
