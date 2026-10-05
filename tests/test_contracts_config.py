from __future__ import annotations
import sysconfig
from pathlib import Path
import unittest

from _support import workspace

from weavem.config import resolve_project
from weavem.contracts import ContractError, Manifest, ManifestError, SourceSpec, module_leaf, source_digest


class ContractTests(unittest.TestCase):
    def test_source_contract_and_digest_are_deterministic(self) -> None:
        with workspace() as raw:
            path = Path(raw) / "task.toml"
            path.write_text('[task]\nschema = 1\ntask_id = "demo.double"\nversion = "1.0.0"\nbackend = "python"\nsource = "implementation.py"\nexport = "run"\ninputs = ["number"]\noutput = "int"\n')
            spec = SourceSpec.from_toml(path)
        self.assertEqual("demo.double", spec.task_id)
        digest = source_digest(b"def run(): pass\n", spec.to_mapping())
        self.assertEqual(digest, source_digest(b"def run(): pass\n", spec.to_mapping()))
        self.assertTrue(module_leaf(spec.task_id, spec.version, digest).startswith("_weavem_"))

    def test_native_manifest_accepts_exact_extension_suffix(self) -> None:
        leaf = "_weavem_demo_native_1234567890abcdef"
        suffix = sysconfig.get_config_var("EXT_SUFFIX")
        manifest = Manifest(1, "demo.native", "1.0.0", "cython", leaf, "run", leaf + suffix,
                            "0" * 64, 1, "1" * 64, "cpython-312", sysconfig.get_platform(), suffix)
        self.assertEqual(manifest, Manifest.from_json_bytes(manifest.to_json_bytes()))

    def test_rejects_unsafe_contract_values(self) -> None:
        with self.assertRaises(ContractError):
            SourceSpec(1, "../bad", "1", "python", "implementation.py", "run")
        with self.assertRaises(ContractError):
            SourceSpec(1, "ok", "1", "python", "../implementation.py", "run")
        with self.assertRaises(ContractError):
            SourceSpec(1, "ok", "1", "python", "implementation.py", "not-valid")
        with self.assertRaises(ManifestError):
            Manifest(1, "ok", "1", "python", "_weavem_ok_1234567890abcdef", "run", "wrong.py", "0" * 64, 0, "0" * 64, "cpython-312", "linux-x86_64", None)


class ConfigTests(unittest.TestCase):
    def test_explicit_environment_config_default_precedence(self) -> None:
        with workspace() as raw:
            root = Path(raw)
            (root / "weavem.toml").write_text('[weavem]\nstore = "cfg-store"\nwork_dir = "cfg-work"\n')
            nested = root / "a" / "b"; nested.mkdir(parents=True)
            config = resolve_project(cwd=nested, environ={})
            self.assertEqual(root, config.root)
            self.assertEqual(root / "cfg-store", config.store_path)
            env_config = resolve_project(root, environ={"WEAVEM_STORE": str(root / "env-store"), "WEAVEM_ARTIFACTS_DIR": str(root / "env-work")})
            self.assertEqual(root / "env-store", env_config.store_path)
            explicit = resolve_project(root, environ={"WEAVEM_STORE": str(root / "env-store")}, store=root / "explicit")
            self.assertEqual(root / "explicit", explicit.store_path)
            bare = root / "bare"; bare.mkdir()
            self.assertEqual(bare / "task-store", resolve_project(bare, environ={}).store_path)

    def test_default_store_is_visible_in_working_directory(self) -> None:
        with workspace() as raw:
            root = Path(raw)
            config = resolve_project(cwd=root, environ={})
            self.assertEqual(root / "task-store", config.store_path)
            self.assertEqual(root / ".artifacts", config.work_dir)

    def test_explicit_missing_config_and_invalid_settings_are_rejected(self) -> None:
        with workspace() as raw:
            root = Path(raw)
            with self.assertRaises(ContractError):
                resolve_project(root / "weavem.toml", environ={})
            (root / "weavem.toml").write_text('[weavem]\nstore = 7\n')
            with self.assertRaises(ContractError):
                resolve_project(root, environ={})


if __name__ == "__main__":
    unittest.main()
