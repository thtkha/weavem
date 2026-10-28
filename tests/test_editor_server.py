"""Focused security and lifecycle checks for the loopback visual-editor bridge."""
from __future__ import annotations

import http.client
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from _support import workspace
from weavem.editor_server import EditorHTTPServer, _ui_directory
from weavem.config import resolve_project


class _Process:
    pid = 999999

    def poll(self):
        return None

    def wait(self, timeout=None):
        raise __import__("subprocess").TimeoutExpired("worker", timeout)


class EditorServerTests(unittest.TestCase):
    def setUp(self):
        self.raw = workspace()
        root = Path(self.raw.__enter__()) / "project"
        root.mkdir()
        task = root / "tasks" / "echo"
        task.mkdir(parents=True)
        (task / "task.toml").write_text(
            '[task]\ntask_id="editor.echo"\nversion="1.0.0"\nsource="implementation.py"\nexport="run"\n',
            encoding="utf-8")
        (task / "implementation.py").write_text("def run(value): return value\n", encoding="utf-8")
        (root / "weavem.toml").write_text(
            "[weavem]\nwork_dir = '.artifacts'\n[tasks.echo]\npath = 'tasks/echo'\n", encoding="utf-8")
        self.task_key = "local:" + str((task / "task.toml").resolve())
        ui = root / "ui"
        ui.mkdir()
        (ui / "index.html").write_text("<div>editor test fixture</div>", encoding="utf-8")
        (ui / "asset.js").write_text("console.log('fixture')", encoding="utf-8")
        self.server = EditorHTTPServer(("127.0.0.1", 0), resolve_project(root), _ui_directory(ui))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._close)

    def _close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.raw.__exit__(None, None, None)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        combined = {"Host": f"127.0.0.1:{self.server.server_port}"}
        combined.update(headers or {})
        if body is not None:
            combined.setdefault("Content-Type", "application/json")
            body = json.dumps(body)
        connection.request(method, path, body=body, headers=combined)
        response = connection.getresponse()
        result = response.status, response.read()
        connection.close()
        return result

    def session(self):
        status, raw = self.request("GET", "/api/session")
        self.assertEqual(200, status)
        return json.loads(raw)

    def test_session_uses_token_and_api_rejects_missing_token(self):
        session = self.session()
        self.assertEqual(str(self.server.project.root), session["project"])
        status, _ = self.request("GET", "/api/runs/nope")
        self.assertEqual(401, status)

    def test_connect_opens_a_project_flow_and_resolves_aliases_without_running_it(self):
        flows = self.server.project.root / "flows"
        flows.mkdir()
        definition = {"kind": "weavem.project-flow", "schema": 1, "name": "Ready to run",
                      "nodes": [{"id": "echo", "taskAlias": "echo", "parameters": {"value": "hello"}}],
                      "edges": []}
        (flows / "editor.json").write_text(json.dumps(definition), encoding="utf-8")
        graph = self.session()["flow"]
        self.assertEqual("weavem.graph", graph["kind"])
        self.assertEqual(self.task_key, graph["nodes"][0]["taskKey"])
        self.assertEqual({"value": "hello"}, graph["nodes"][0]["parameters"])
        self.assertFalse(self.server.runs._runs)

    def test_project_flow_rejects_unknown_alias_and_symlinks(self):
        flows = self.server.project.root / "flows"
        flows.mkdir()
        flow = flows / "editor.json"
        flow.write_text(json.dumps({"kind": "weavem.project-flow", "schema": 1, "name": "Bad",
                                   "nodes": [{"id": "bad", "taskAlias": "missing"}], "edges": []}), encoding="utf-8")
        self.assertEqual(400, self.request("GET", "/api/session")[0])
        flow.unlink()
        flow.symlink_to(self.server.ui_dir / "index.html")
        self.assertEqual(400, self.request("GET", "/api/session")[0])

    def test_rejects_bad_host_cross_origin_and_path_escape(self):
        status, _ = self.request("GET", "/api/session", headers={"Host": "example.test"})
        self.assertEqual(400, status)
        status, _ = self.request("GET", "/api/session", headers={"Origin": "https://example.test"})
        self.assertEqual(403, status)
        status, _ = self.request("GET", "/../../pyproject.toml")
        self.assertEqual(404, status)

    def test_mutation_requires_json_token_and_size_limit(self):
        token = self.session()["token"]
        headers = {"X-Weavem-Token": token}
        status, _ = self.request("POST", "/api/runs", {}, headers=headers)
        self.assertEqual(400, status)
        status, _ = self.request("POST", "/api/runs", {"graph": {}}, headers={**headers, "Origin": "http://wrong"})
        self.assertEqual(403, status)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        connection.putrequest("POST", "/api/runs")
        connection.putheader("Host", f"127.0.0.1:{self.server.server_port}")
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", str(5 * 1024 * 1024 + 1))
        connection.putheader("X-Weavem-Token", token)
        connection.endheaders()  # The server rejects from headers; do not send 5 MiB.
        response = connection.getresponse()
        self.assertEqual(413, response.status)
        response.read()
        connection.close()

    def test_only_one_active_run_and_cancel_terminates_its_group(self):
        token = self.session()["token"]
        graph = {"kind": "weavem.graph", "schema": 1, "name": "Echo",
                 "nodes": [{"id": "echo", "taskKey": self.task_key, "parameters": {"value": "ok"}}],
                 "edges": []}
        headers = {"X-Weavem-Token": token}
        with patch("weavem.editor_server.subprocess.Popen", return_value=_Process()) as spawn, \
                patch("weavem.editor_server.os.killpg") as kill:
            status, raw = self.request("POST", "/api/runs", graph, headers=headers)
            self.assertEqual(202, status)
            run_id = json.loads(raw)["runId"]
            self.assertEqual(409, self.request("POST", "/api/runs", graph, headers=headers)[0])
            status, raw = self.request("POST", f"/api/runs/{run_id}/cancel", {}, headers=headers)
            self.assertEqual(200, status)
            state = json.loads(raw)
            self.assertEqual("cancelled", state["status"])
            self.assertEqual("skipped", state["nodes"]["echo"]["status"])
            self.assertGreaterEqual(kill.call_count, 1)
            environment = spawn.call_args.kwargs["env"]
            self.assertEqual("", environment["PREFECT_API_URL"])
            self.assertEqual("", environment["PREFECT_API_KEY"])
            self.assertEqual("false", environment["PREFECT_SERVER_ANALYTICS_ENABLED"])
            self.assertTrue(Path(environment["PYTHONPATH"].split(":", 1)[0]).is_absolute())

    def test_exited_active_worker_is_refreshed_before_a_new_post(self):
        token = self.session()["token"]
        graph = {"kind": "weavem.graph", "schema": 1, "name": "Echo",
                 "nodes": [{"id": "echo", "taskKey": self.task_key, "parameters": {"value": "ok"}}],
                 "edges": []}
        first, second = _Process(), _Process()
        with patch("weavem.editor_server.subprocess.Popen", side_effect=[first, second]):
            self.assertEqual(202, self.request("POST", "/api/runs", graph, headers={"X-Weavem-Token": token})[0])
            first.poll = lambda: 0
            # No status polling occurs between these POSTs; start() refreshes it.
            self.assertEqual(202, self.request("POST", "/api/runs", graph, headers={"X-Weavem-Token": token})[0])

    def test_cancel_preserves_terminal_worker_event_that_already_exited(self):
        token = self.session()["token"]
        graph = {"kind": "weavem.graph", "schema": 1, "name": "Echo",
                 "nodes": [{"id": "echo", "taskKey": self.task_key, "parameters": {"value": "ok"}}],
                 "edges": []}
        process = _Process()
        with patch("weavem.editor_server.subprocess.Popen", return_value=process), \
                patch("weavem.editor_server.os.killpg") as kill:
            _, raw = self.request("POST", "/api/runs", graph, headers={"X-Weavem-Token": token})
            run_id = json.loads(raw)["runId"]
            run = self.server.runs._runs[run_id]
            run.events_path.write_text('{"type":"run","status":"completed"}\n', encoding="utf-8")
            process.poll = lambda: 0
            status, raw = self.request("POST", f"/api/runs/{run_id}/cancel", {},
                                       headers={"X-Weavem-Token": token})
            self.assertEqual(200, status)
            self.assertEqual("completed", json.loads(raw)["status"])
            kill.assert_not_called()

    def test_cancel_preserves_terminal_event_while_worker_cleans_up(self):
        token = self.session()["token"]
        graph = {"kind": "weavem.graph", "schema": 1, "name": "Echo",
                 "nodes": [{"id": "echo", "taskKey": self.task_key, "parameters": {"value": "ok"}}],
                 "edges": []}
        process = _Process()  # poll() remains None, simulating Prefect cleanup.
        with patch("weavem.editor_server.subprocess.Popen", return_value=process), \
                patch("weavem.editor_server.os.killpg") as kill:
            _, raw = self.request("POST", "/api/runs", graph, headers={"X-Weavem-Token": token})
            run_id = json.loads(raw)["runId"]
            run = self.server.runs._runs[run_id]
            run.nodes["echo"] = {"status": "completed", "preview": "ok"}
            run.events_path.write_text('{"type":"run","status":"completed"}\n', encoding="utf-8")
            status, raw = self.request("POST", f"/api/runs/{run_id}/cancel", {},
                                       headers={"X-Weavem-Token": token})
            self.assertEqual(200, status)
            state = json.loads(raw)
            self.assertEqual("completed", state["status"])
            self.assertEqual("completed", state["nodes"]["echo"]["status"])
            kill.assert_called()

    def test_invalid_graph_schema_does_not_start_a_worker(self):
        token = self.session()["token"]
        invalid = {"kind": "weavem.graph", "schema": True, "name": "No",
                   "nodes": [{"id": "echo", "taskKey": self.task_key, "parameters": {"value": "ok"}}],
                   "edges": []}
        with patch("weavem.editor_server.subprocess.Popen") as spawn:
            self.assertEqual(400, self.request("POST", "/api/runs", invalid,
                                               headers={"X-Weavem-Token": token})[0])
            spawn.assert_not_called()

    def test_worker_exit_without_terminal_event_is_never_success(self):
        token = self.session()["token"]
        graph = {"kind": "weavem.graph", "schema": 1, "name": "Echo",
                 "nodes": [{"id": "echo", "taskKey": self.task_key, "parameters": {"value": "ok"}}],
                 "edges": []}
        process = _Process()
        with patch("weavem.editor_server.subprocess.Popen", return_value=process):
            _, raw = self.request("POST", "/api/runs", graph, headers={"X-Weavem-Token": token})
            run_id = json.loads(raw)["runId"]
            process.poll = lambda: 0
            state = self.server.runs.state(run_id)
            self.assertEqual("failed", state["status"])
            self.assertEqual("skipped", state["nodes"]["echo"]["status"])
            self.assertIn("without a terminal event", state["error"])

    def test_static_spa_and_missing_asset(self):
        status, body = self.request("GET", "/")
        self.assertEqual(200, status)
        self.assertIn(b"<div", body)
        self.assertEqual(404, self.request("GET", "/missing.js")[0])

    def test_spa_fallback_cannot_follow_a_symlink_outside_the_ui_root(self):
        outside = self.server.ui_dir.parent / "private.html"
        outside.write_text("private content", encoding="utf-8")
        index = self.server.ui_dir / "index.html"
        index.unlink()
        index.symlink_to(outside)
        status, body = self.request("GET", "/nested/editor")
        self.assertEqual(404, status)
        self.assertNotIn(b"private content", body)


if __name__ == "__main__":
    unittest.main()
