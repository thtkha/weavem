"""Focused regression checks for the standalone installed-wheel release gate."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from _support import ROOT


def _script_module():
    path = ROOT / "scripts" / "verify-installed-wheel.py"
    spec = importlib.util.spec_from_file_location("verify_installed_wheel", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstalledWheelScriptTests(unittest.TestCase):
    def test_preserved_snapshot_rejects_added_v1_files_but_allows_v2(self) -> None:
        module = _script_module()
        original = {"task/1/tag/manifest.json": "manifest", "task/1/tag/payload.so": "payload"}
        module._assert_preserved_releases(original, original | {"task/2/tag/manifest.json": "new"})
        with self.assertRaises(module.GateFailure):
            module._assert_preserved_releases(original, original | {"task/1/tag/extra.pyc": "unexpected"})

    def test_operator_store_and_prefect_configuration_are_not_inherited(self) -> None:
        module = _script_module()
        inherited = {
            "WEAVEM_STORE": "/unrelated/store",
            "PREFECT_API_URL": "https://example.invalid",
            "PREFECT_API_DATABASE_CONNECTION_URL": "postgresql://example.invalid/database",
            "PREFECT_PROFILES_PATH": "/unrelated/profiles.toml",
            "PYTHONHOME": "/unrelated/python",
        }
        with tempfile.TemporaryDirectory() as raw, patch.dict(os.environ, inherited):
            root = Path(raw)
            gate = module.Gate(root)
            for key in inherited:
                self.assertNotIn(key, gate.environment)
            self.assertEqual(str(root / "artifacts" / "prefect"), gate.environment["PREFECT_HOME"])

    def test_timeout_bytes_are_recorded_as_text_evidence(self) -> None:
        module = _script_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            gate = module.Gate(root)
            expired = subprocess.TimeoutExpired(["example"], 1, output=b"partial stdout", stderr=b"partial stderr")
            with patch.object(module.subprocess, "run", side_effect=expired):
                with self.assertRaises(module.GateFailure):
                    gate.command("timeout", "example", cwd=root)
            self.assertEqual("partial stdout", (root / "logs" / "timeout.stdout").read_text())
            self.assertEqual("partial stderr", (root / "logs" / "timeout.stderr").read_text())
            self.assertTrue(gate.commands[-1]["timed_out"])

    def test_compileall_store_gate_requires_and_records_a_flow_cache(self) -> None:
        module = _script_module()

        class RecordingGate:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[str, ...], Path]] = []

            def command(self, label: str, *command: str, cwd: Path):
                self.calls.append((label, command, cwd))

        with tempfile.TemporaryDirectory() as raw:
            store = Path(raw) / "task-store"
            cache = store / "_flows" / "release.money_flow" / "1.0.0" / "cpython-314" / "__pycache__"
            cache.mkdir(parents=True)
            (cache / "money_flow.cpython-314.pyc").write_bytes(b"derived cache")
            gate = RecordingGate()

            module._compile_store_and_assert_flow_cache(gate, store, version="1.0.0")

            self.assertEqual(
                [("compileall-store-after-flow-v1.0.0", (sys.executable, "-m", "compileall", "-q", "."), store)],
                gate.calls,
            )


if __name__ == "__main__":
    unittest.main()
