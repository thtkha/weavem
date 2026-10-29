"""Saved-flow RunManager contract tests without a loopback socket."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from _support import workspace
from weavem.config import resolve_project
from weavem.editor_server import EditorServerError, RunManager


class _Process:
    pid = 999999
    def poll(self): return None
    def wait(self, timeout=None): raise subprocess.TimeoutExpired("worker", timeout)


class SavedRunManagerTests(unittest.TestCase):
    def setUp(self):
        self.raw = workspace(); self.root = Path(self.raw.__enter__())
        (self.root / "weavem.toml").write_text("[weavem]\nwork_dir='.artifacts'\n", encoding="utf-8")
        self.manager = RunManager(resolve_project(self.root))
        self.opened = {"name": "demo", "revision": "r1", "editable": True,
                       "graph": {"nodes": [{"id": "first"}]}}

    def tearDown(self):
        self.manager.close(); self.raw.__exit__(None, None, None)

    def test_starts_exact_saved_revision_and_preserves_prefect_environment(self):
        old = os.environ.get("PREFECT_API_URL"); os.environ["PREFECT_API_URL"] = "https://prefect.example/api"
        try:
            with patch("weavem.editor_flows.open_flow", return_value=self.opened), \
                    patch("weavem.editor_server.subprocess.Popen", return_value=_Process()) as spawn:
                run = self.manager.start("demo", "r1", {"value": 1})
        finally:
            if old is None: os.environ.pop("PREFECT_API_URL", None)
            else: os.environ["PREFECT_API_URL"] = old
        request = __import__("json").loads(run.request_path.read_text(encoding="utf-8"))
        self.assertEqual({"project": str(self.root), "flowName": "demo", "revision": "r1", "params": {"value": 1}}, request)
        self.assertEqual("https://prefect.example/api", spawn.call_args.kwargs["env"]["PREFECT_API_URL"])
        self.assertEqual("pending", run.nodes["first"]["status"])

    def test_rejects_changed_revision_before_spawning(self):
        with patch("weavem.editor_flows.open_flow", return_value=self.opened), \
                patch("weavem.editor_server.subprocess.Popen") as spawn:
            with self.assertRaisesRegex(EditorServerError, "changed on disk"):
                self.manager.start("demo", "stale", {})
        spawn.assert_not_called()

    def test_state_carries_flow_identity_and_result(self):
        with patch("weavem.editor_flows.open_flow", return_value=self.opened), \
                patch("weavem.editor_server.subprocess.Popen", return_value=_Process()):
            run = self.manager.start("demo", "r1", {})
        self.manager._apply_event(run, {"type": "run", "status": "preparing", "message": "Preparing flow…"})
        self.manager._apply_event(run, {"type": "run", "status": "completed", "result": {"first": 3}})
        state = self.manager.state(run.run_id)
        self.assertEqual("demo", state["flowName"])
        self.assertEqual("r1", state["revision"])
        self.assertEqual({"first": 3}, state["result"])
        self.assertEqual("preparing", state["phase"])
        self.assertEqual("Preparing flow…", state["message"])


if __name__ == "__main__":
    unittest.main()
