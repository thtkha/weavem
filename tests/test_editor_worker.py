"""Saved-flow worker checks without requiring a running Prefect service."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from weavem.editor_worker import _run_saved_flow


class EditorWorkerTests(unittest.TestCase):
    def _request(self, root: Path, revision: str = "revision"):
        return {"project": str(root), "flowName": "demo", "revision": revision, "params": {}}

    def _opened(self, source: str, *, editable: bool = True, revision: str = "revision"):
        return {"name": "demo", "revision": revision, "editable": editable, "source": source,
                "graph": {"nodes": [{"id": "first"}, {"id": "second"}]} if editable else None}

    def test_runs_the_same_loaded_flow_and_observes_generated_assignments(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source_path = root / "flows" / "demo.py"; source_path.parent.mkdir()
            source = '''def demo():
    # weavem-node: "first"
    node_1 = first()
    # weavem-node: "second"
    node_2 = second(node_1)
    return {"second": node_2}
'''
            namespace = {"first": lambda: "a", "second": lambda value: value + "b"}
            exec(compile(source, str(source_path), "exec"), namespace)
            events = []
            with patch("weavem.editor_flows.open_flow", return_value=self._opened(source)), \
                    patch("weavem.flows.load_local_flow", return_value=namespace["demo"]) as load:
                result = _run_saved_flow(self._request(root), events.append)
            self.assertEqual({"second": "ab"}, result)
            load.assert_called_once_with("demo", project=str(root),
                                         expected_source_sha256=None,
                                         expected_metadata_sha256=None)
            self.assertIn({"type": "node", "nodeId": "first", "status": "running"}, events)
            self.assertTrue(any(event.get("nodeId") == "first" and event.get("status") == "completed" and event.get("preview") == "'a'" and event.get("value", {}).get("value") == "a" for event in events))
            self.assertTrue(any(event.get("nodeId") == "second" and event.get("status") == "completed" and event.get("preview") == "'ab'" and event.get("value", {}).get("value") == "ab" for event in events))
            self.assertEqual("completed", events[-1]["status"])
            self.assertEqual("{'second': 'ab'}", events[-1]["result"])

    def test_trace_handles_repeated_aliases_and_internal_retry_without_inventing_failure(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source_path = root / "flows" / "demo.py"; source_path.parent.mkdir()
            source = '''def demo():
    # weavem-node: "first"
    node_1 = retrying("a")
    # weavem-node: "second"
    node_2 = retrying(node_1)
    return {"second": node_2}
'''
            attempts = []
            def retrying(value):
                attempts.append(value)
                if len(attempts) in {1, 3}:
                    try:
                        raise RuntimeError("transient")
                    except RuntimeError:
                        pass
                return value + "!"
            namespace = {"retrying": retrying}
            exec(compile(source, str(source_path), "exec"), namespace)
            events = []
            with patch("weavem.editor_flows.open_flow", return_value=self._opened(source)), \
                    patch("weavem.flows.load_local_flow", return_value=namespace["demo"]):
                result = _run_saved_flow(self._request(root), events.append)
            self.assertEqual({"second": "a!!"}, result)
            self.assertFalse(any(event.get("status") == "failed" for event in events))
            self.assertEqual(["a", "a!"], attempts)

    def test_trace_reports_only_final_task_failure(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source_path = root / "flows" / "demo.py"; source_path.parent.mkdir()
            source = '''def demo():
    # weavem-node: "first"
    node_1 = retrying()
    # weavem-node: "second"
    node_2 = second(node_1)
    return {"second": node_2}
'''
            attempts = []
            def retrying():
                attempts.append(1)
                try:
                    raise RuntimeError("transient")
                except RuntimeError:
                    pass
                raise ValueError("final")
            namespace = {"retrying": retrying, "second": lambda value: value}
            exec(compile(source, str(source_path), "exec"), namespace)
            events = []
            with patch("weavem.editor_flows.open_flow", return_value=self._opened(source)), \
                    patch("weavem.flows.load_local_flow", return_value=namespace["demo"]):
                with self.assertRaisesRegex(ValueError, "final"):
                    _run_saved_flow(self._request(root), events.append)
            failed = [event for event in events if event.get("type") == "node" and event.get("status") == "failed"]
            self.assertEqual(["first"], [event["nodeId"] for event in failed])
            self.assertEqual(["second"], [event["nodeId"] for event in events if event.get("status") == "skipped"])

    def test_rejects_changed_source_before_loading(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            events = []
            with patch("weavem.editor_flows.open_flow", return_value=self._opened("", revision="new")), \
                    patch("weavem.flows.load_local_flow") as load:
                with self.assertRaisesRegex(RuntimeError, "changed on disk"):
                    _run_saved_flow(self._request(root), events.append)
            load.assert_not_called()

    def test_unsupported_handwritten_flow_is_still_runnable_without_node_claims(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            events = []
            with patch("weavem.editor_flows.open_flow", return_value=self._opened("def demo(): pass", editable=False)), \
                    patch("weavem.flows.load_local_flow", return_value=lambda: {"ok": True}):
                result = _run_saved_flow(self._request(root), events.append)
            self.assertEqual({"ok": True}, result)
            self.assertFalse(any(event.get("type") == "node" for event in events))
            self.assertEqual("completed", events[-1]["status"])


if __name__ == "__main__":
    unittest.main()
