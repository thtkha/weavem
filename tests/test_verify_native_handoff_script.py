"""Focused checks for the standalone cross-runner native handoff gate."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from _support import ROOT


def _script_module():
    path = ROOT / "scripts" / "verify-native-handoff.py"
    spec = importlib.util.spec_from_file_location("verify_native_handoff", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeHandoffScriptTests(unittest.TestCase):
    def test_expected_snapshot_requires_the_producer_v2_store_record(self) -> None:
        module = _script_module()
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "result.json"
            path.write_text(json.dumps({"v2_store_sha256": {"task/manifest.json": "abc"}}), encoding="utf-8")
            self.assertEqual({"task/manifest.json": "abc"}, module._expected_snapshot(path))
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(module.GateFailure):
                module._expected_snapshot(path)

    def test_consumer_environment_drops_ambient_runtime_configuration(self) -> None:
        module = _script_module()
        inherited = {
            "WEAVEM_STORE": "/unrelated/store",
            "PREFECT_API_URL": "https://example.invalid",
            "PREFECT_PROFILES_PATH": "/unrelated/profiles.toml",
            "PYTHONHOME": "/unrelated/python",
            "WEAVEM_ARTIFACTS_DIR": "/unrelated/artifacts",
        }
        with tempfile.TemporaryDirectory() as raw, patch.dict(os.environ, inherited):
            gate = module.Gate(Path(raw))
            for key in inherited:
                if key == "WEAVEM_ARTIFACTS_DIR":
                    continue
                self.assertNotIn(key, gate.environment)
            self.assertEqual(str(Path(raw) / "artifacts" / "prefect"), gate.environment["PREFECT_HOME"])
            self.assertEqual(str(Path(raw) / "artifacts" / "weavem"), gate.environment["WEAVEM_ARTIFACTS_DIR"])

    def test_snapshot_catches_changed_transferred_bytes(self) -> None:
        module = _script_module()
        with tempfile.TemporaryDirectory() as raw:
            store = Path(raw) / "store"
            store.mkdir()
            payload = store / "artifact.so"
            payload.write_bytes(b"one")
            before = module._snapshot_tree(store)
            payload.write_bytes(b"two")
            self.assertNotEqual(before, module._snapshot_tree(store))

    def test_run_rejects_mismatched_handoff_before_consumer_execution(self) -> None:
        module = _script_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            store = root / "store"
            store.mkdir()
            (store / "payload").write_bytes(b"received")
            expected = root / "producer-result.json"
            expected.write_text(json.dumps({"v2_store_sha256": {"payload": "different"}}), encoding="utf-8")
            evidence = root / "evidence"
            evidence.mkdir()
            with (patch.object(module, "_assert_installed_distribution", return_value={}),
                  patch.object(module.Gate, "command") as command):
                with self.assertRaisesRegex(module.GateFailure, "hashes differ"):
                    module.run(evidence, store, expected)
            command.assert_not_called()
            self.assertFalse((evidence / "consumer").exists())

    def test_run_rejects_store_mutation_after_flow_execution(self) -> None:
        module = _script_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            store = root / "store"
            store.mkdir()
            (store / "payload").write_bytes(b"original")
            expected = root / "producer-result.json"
            expected.write_text(json.dumps({"v2_store_sha256": module._snapshot_tree(store)}), encoding="utf-8")
            evidence = root / "evidence"
            evidence.mkdir()

            def mutate_store(_gate, _consumer, copied_store, _version, _expected):
                (copied_store / "payload").write_bytes(b"tampered")

            completed = subprocess.CompletedProcess(["weavem"], 0, "", "")
            with (patch.object(module, "_assert_installed_distribution", return_value={}),
                  patch.object(module.Gate, "command", return_value=completed),
                  patch.object(module, "_assert_native_loaded"),
                  patch.object(module, "_run_flow", side_effect=mutate_store) as run_flow):
                with self.assertRaisesRegex(module.GateFailure, "modified the transferred store"):
                    module.run(evidence, store, expected)
            self.assertEqual(2, run_flow.call_count)

    def test_native_check_rejects_non_native_payload_before_execution(self) -> None:
        module = _script_module()
        with tempfile.TemporaryDirectory() as raw:
            store = Path(raw) / "store"
            release = store / "release.money" / "2.0.0" / "cpython-312"
            release.mkdir(parents=True)
            (release / "manifest.json").write_text(json.dumps({"backend": "python", "artifact_name": "payload.py"}), encoding="utf-8")
            (release / "payload.py").write_text("pass\n", encoding="utf-8")

            class NoExecutionGate:
                def command(self, *args, **kwargs):
                    self.fail("a non-native payload must be rejected before execution")

            with self.assertRaisesRegex(module.GateFailure, "not a native extension"):
                module._assert_native_loaded(NoExecutionGate(), store, Path(raw))

    def test_flow_result_mismatch_is_rejected(self) -> None:
        module = _script_module()

        class WrongResultGate:
            def command(self, *args, **kwargs):
                return subprocess.CompletedProcess(args, 0, "999\n", "")

        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(module.GateFailure, "returned 999"):
                module._run_flow(WrongResultGate(), Path(raw), Path(raw) / "store", "2.0.0", 21)


if __name__ == "__main__":
    unittest.main()
