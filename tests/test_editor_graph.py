"""Execution graph validation uses explicit project bindings, never canvas guesses."""
from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch
import sys
import types

from _support import workspace
from test_store_runtime import stage
from weavem.bindings import manifest_digest
from weavem.editor_graph import EditorGraphError, editor_catalog, execute_graph, validate_graph
from weavem.store import LocalStore


class EditorGraphTests(unittest.TestCase):
    def _project(self, root: Path) -> Path:
        root.mkdir(parents=True)
        (root / "weavem.toml").write_text('[weavem]\nstore = "task-store"\nwork_dir = ".artifacts"\n')
        return root

    def _local(self, root: Path, name: str, source: str) -> Path:
        task = root / "tasks" / name
        task.mkdir(parents=True)
        (task / "task.toml").write_text(
            f'[task]\ntask_id = "demo.{name}"\nversion = "1.0.0"\nsource = "implementation.py"\nexport = "run"\n')
        (task / "implementation.py").write_text(source)
        with (root / "weavem.toml").open("a") as output:
            output.write(f'\n[tasks.{name}]\npath = "tasks/{name}"\n')
        return task / "task.toml"

    def _graph(self, nodes, edges=()):
        return {"kind": "weavem.graph", "schema": 1, "name": "test", "nodes": nodes, "edges": list(edges)}

    def _node(self, node_id, key, parameters=None):
        return {"id": node_id, "taskKey": key, "parameters": parameters or {}}

    def test_catalog_only_exposes_explicit_bindings_and_graph_chain_executes(self):
        with workspace() as raw:
            root = self._project(Path(raw) / "project")
            one = self._local(root, "one", "def run(value): return {'value': value}\n")
            two = self._local(root, "two", "def run(item, suffix): return item['value'] + suffix\n")
            catalog = editor_catalog(root)
            self.assertEqual({f"local:{one.resolve()}", f"local:{two.resolve()}"}, set(catalog["bindings"]))
            graph = self._graph([
                self._node("one", f"local:{one.resolve()}", {"value": "a"}),
                self._node("two", f"local:{two.resolve()}", {"suffix": "b"}),
            ], [{"id":"wire", "source":"one", "target":"two", "argument":"item"}])
            events = []
            def fake_task(alias, **options):
                self.assertFalse(options["persist_result"])
                self.assertEqual(0, options["retries"])
                return {"one": lambda value: {"value": value},
                        "two": lambda item, suffix: item["value"] + suffix}[alias]
            with patch("weavem.flow", lambda **_: lambda fn: fn), patch("weavem.task", fake_task):
                result = execute_graph(graph, root, events.append)
            self.assertEqual("ab", result["two"])
            self.assertEqual(["running", "completed", "running", "completed"],
                             [event["status"] for event in events if event["type"] == "node" and event["status"] != "skipped"])
            self.assertEqual({"type":"run", "status":"completed"}, events[-1])

    def test_fork_join_and_repeated_task_instances(self):
        with workspace() as raw:
            root = self._project(Path(raw) / "project")
            source = self._local(root, "source", "def run(value): return value\n")
            join = self._local(root, "join", "def run(left, right): return (left, right)\n")
            graph = self._graph([
                self._node("a", f"local:{source.resolve()}", {"value": 1}),
                # Reusing the same task key is valid; construct actual key explicitly.
                self._node("b", f"local:{source.resolve()}", {"value": 2}),
                self._node("join", f"local:{join.resolve()}"),
            ], [
                {"id":"a-left","source":"a","target":"join","argument":"left"},
                {"id":"b-right","source":"b","target":"join","argument":"right"},
            ])
            def fake_task(alias, **_):
                return {"source": lambda value: value, "join": lambda left, right: (left, right)}[alias]
            with patch("weavem.flow", lambda **_: lambda fn: fn), patch("weavem.task", fake_task):
                self.assertEqual((1, 2), execute_graph(graph, root, lambda _: None)["join"])

    def test_invalid_graph_never_imports_or_runs_local_payload(self):
        with workspace() as raw:
            root = self._project(Path(raw) / "project")
            marker = root / "marker"
            task = self._local(root, "danger", f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\ndef run(): return 1\n")
            graph = self._graph([self._node("a", f"local:{task.resolve()}"), self._node("b", f"local:{task.resolve()}")], [
                {"id":"1","source":"a","target":"b","argument":"value"},
                {"id":"2","source":"b","target":"a","argument":"value"},
            ])
            with self.assertRaisesRegex(EditorGraphError, "cycle"):
                validate_graph(graph, root)
            self.assertFalse(marker.exists())

    def test_conflicting_wires_and_literals_fail_preflight(self):
        with workspace() as raw:
            root = self._project(Path(raw) / "project")
            task = self._local(root, "one", "def run(**kwargs): return kwargs\n")
            key = f"local:{task.resolve()}"
            graph = self._graph([self._node("a", key), self._node("b", key), self._node("target", key, {"input": 1})], [
                {"id":"a","source":"a","target":"target","argument":"input"},
                {"id":"b","source":"b","target":"target","argument":"input"},
            ])
            with self.assertRaisesRegex(EditorGraphError, "conflicts"):
                validate_graph(graph, root)

    def test_schema_is_not_boolean_and_prefect_control_arguments_are_rejected(self):
        with workspace() as raw:
            root = self._project(Path(raw) / "project")
            task = self._local(root, "one", "def run(**kwargs): return kwargs\n")
            key = f"local:{task.resolve()}"
            graph = self._graph([self._node("a", key)])
            with self.assertRaisesRegex(EditorGraphError, "schema 1"):
                validate_graph({**graph, "schema": True}, root)
            for argument in ("return_state", "wait_for"):
                with self.subTest(argument=argument), self.assertRaisesRegex(EditorGraphError, "reserved Prefect"):
                    validate_graph(self._graph([self._node("a", key, {argument: True})]), root)

    def test_failure_marks_remaining_nodes_skipped(self):
        with workspace() as raw:
            root = self._project(Path(raw) / "project")
            bad = self._local(root, "bad", "def run(): raise RuntimeError('boom')\n")
            later = self._local(root, "later", "def run(value): return value\n")
            events = []
            graph = self._graph([self._node("bad", f"local:{bad.resolve()}"), self._node("later", f"local:{later.resolve()}")], [
                {"id":"edge","source":"bad","target":"later","argument":"value"}])
            with patch("weavem.flow", lambda **_: lambda fn: fn), patch("weavem.task", lambda alias, **_: (lambda: (_ for _ in ()).throw(RuntimeError("boom")))):
                with self.assertRaisesRegex(Exception, "boom"):
                    execute_graph(graph, root, events.append)
            self.assertIn({"type":"node", "nodeId":"later", "status":"skipped"}, events)
            self.assertEqual("failed", events[-1]["status"])

    def test_result_preview_is_bounded_and_never_serializes_the_object(self):
        with workspace() as raw:
            root = self._project(Path(raw) / "project")
            task = self._local(root, "one", "def run(): return None\n")
            class LongResult:
                def __repr__(self):
                    return "x" * 5000
            events = []
            with patch("weavem.flow", lambda **_: lambda fn: fn), patch("weavem.task", lambda alias, **_: lambda: LongResult()):
                result = execute_graph(self._graph([self._node("one", f"local:{task.resolve()}")]), root, events.append)
            self.assertIsInstance(result["one"], LongResult)
            node_event = next(event for event in events if event.get("preview"))
            self.assertEqual(4096, len(node_event["preview"]))

    def test_graph_display_name_does_not_be_used_as_prefect_flow_name(self):
        with workspace() as raw:
            root = self._project(Path(raw) / "project")
            task = self._local(root, "one", "def run(): return None\n")
            graph = self._graph([self._node("one", f"local:{task.resolve()}")])
            graph["name"] = "draft / with punctuation : and spaces"
            flow_options = []
            def fake_flow(**options):
                flow_options.append(options)
                return lambda fn: fn
            with patch("weavem.flow", fake_flow), patch("weavem.task", lambda alias, **_: lambda: None):
                execute_graph(graph, root, lambda _: None)
            self.assertEqual("weavem-editor", flow_options[0]["name"])

    def test_worker_runs_saved_flow_request_without_prefect_setting_overrides(self):
        with workspace() as raw:
            from weavem.editor_worker import main
            root = Path(raw)
            request, events = root / "request.json", root / "events.jsonl"
            payload = {"project": str(root), "flowName": "demo", "revision": "r1", "params": {"x": 1}}
            request.write_text(json.dumps(payload))
            seen = {}
            def run(actual, emit):
                seen["request"] = actual
                emit({"type": "run", "status": "completed", "result": {"ok": True}})
            with patch("weavem.editor_worker._run_saved_flow", run):
                self.assertEqual(0, main([str(request), str(events)]))
            self.assertEqual(payload, seen["request"])
            self.assertEqual("completed", json.loads(events.read_text().splitlines()[-1])["status"])

    def test_worker_writes_a_terminal_event_for_malformed_request(self):
        with workspace() as raw:
            from weavem.editor_worker import main
            root = Path(raw)
            request, events = root / "request.json", root / "events.jsonl"
            request.write_text("not json")
            self.assertEqual(1, main([str(request), str(events)]))
            recorded = [json.loads(line) for line in events.read_text().splitlines()]
            self.assertEqual(1, len(recorded))
            self.assertEqual("failed", recorded[0]["status"])

    def test_worker_reports_pre_execution_load_error_once(self):
        with workspace() as raw:
            from weavem.editor_worker import main
            root = Path(raw)
            request, events = root / "request.json", root / "events.jsonl"
            request.write_text(json.dumps({"project": str(root), "flowName": "demo", "revision": "r1", "params": {}}))
            with patch("weavem.editor_worker._run_saved_flow", side_effect=ImportError("no prefect")):
                self.assertEqual(1, main([str(request), str(events)]))
            recorded = [json.loads(line) for line in events.read_text().splitlines()]
            self.assertEqual(1, len(recorded))
            self.assertIn("ImportError", recorded[0]["error"])

    def test_released_pin_is_validated_before_execution(self):
        with workspace() as raw:
            root = self._project(Path(raw) / "project")
            ref = LocalStore(root / "task-store").publish(stage(root / "candidate", task_id="demo.release"))
            digest = manifest_digest(ref.manifest_path)
            with (root / "weavem.toml").open("a") as output:
                output.write(f'\n[tasks.release]\nrelease = "demo.release==1.0.0"\nsource = "task-store"\nmanifest_sha256 = "{digest}"\n')
            key = f"released:{ref.root.resolve()}:{digest}"
            validate_graph(self._graph([self._node("released", key, {"x": 2})]), root)
            payload = next(ref.root.glob("*.py"))
            payload.write_text("raise RuntimeError('must not import')\n")
            with self.assertRaises(Exception):
                validate_graph(self._graph([self._node("released", key, {"x": 2})]), root)


if __name__ == "__main__":
    unittest.main()
