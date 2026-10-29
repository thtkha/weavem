"""Generated Python has the same behavior without the browser or bridge."""
from __future__ import annotations

import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from _support import workspace
from weavem.editor_flows import open_flow, save_flow
from weavem.editor_graph import editor_catalog


@unittest.skipUnless(importlib.util.find_spec("prefect"), "Prefect is not installed")
class SavedFlowIntegrationTests(unittest.TestCase):
    def _project(self, root, definitions):
        bindings = []
        for alias, source, backend in definitions:
            directory = root / "tasks" / alias
            directory.mkdir(parents=True)
            (directory / "task.toml").write_text(
                f'[task]\ntask_id="saved.{alias}"\nversion="1.0.0"\nbackend="{backend}"\n',
                encoding="utf-8",
            )
            (directory / "implementation.py").write_text(source, encoding="utf-8")
            bindings.append(f'[tasks.{alias}]\npath="tasks/{alias}"\n')
        (root / "weavem.toml").write_text("\n".join(bindings), encoding="utf-8")
        return {alias: key for key, alias in editor_catalog(root)["bindings"].items()}

    def _command(self, root, *arguments):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        result = subprocess.run([sys.executable, *arguments], cwd=root, env=env,
                                capture_output=True, text=True, timeout=180)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return result

    def test_loader_rejects_changed_source_and_metadata_before_import(self):
        from weavem.flows import FlowError, load_local_flow
        with workspace("saved-stale-load-") as raw:
            root = Path(raw)
            keys = self._project(root, [("echo", "def run(value): return value\n", "python")])
            graph = {"kind": "weavem.graph", "schema": 1, "name": "echo_flow",
                     "nodes": [{"id": "echo", "taskKey": keys["echo"], "parameters": {"value": 4}}], "edges": []}
            saved = save_flow("echo_flow", graph, None, None, root)
            options = {"project": root, "expected_source_sha256": saved["sourceSha256"],
                       "expected_metadata_sha256": saved["metadataSha256"]}
            source = root / "flows" / "echo_flow.py"
            original = source.read_bytes()
            marker = root / "must-not-execute"
            source.write_text(f"open({str(marker)!r}, 'w').write('executed')\n" + original.decode())
            with self.assertRaisesRegex(FlowError, "source changed"):
                load_local_flow("echo_flow", **options)
            self.assertFalse(marker.exists())
            source.write_bytes(original)
            metadata = root / "flows" / "echo_flow.toml"
            metadata.write_text(metadata.read_text() + "\n# externally edited\n")
            with self.assertRaisesRegex(FlowError, "metadata changed"):
                load_local_flow("echo_flow", **options)

    def test_native_saved_flow_matches_python_cli_and_worker_without_layout(self):
        from weavem.flows import load_local_flow
        with workspace("saved-native-parity-") as raw:
            root = Path(raw)
            keys = self._project(root, [
                ("normalize", "def run(text): return text.strip().lower()\n", "cython"),
                ("decorate", "def run(text, suffix): return text + suffix\n", "python"),
            ])
            graph = {"kind": "weavem.graph", "schema": 1, "name": "summary",
                     "nodes": [
                         {"id": "native", "taskKey": keys["normalize"], "parameters": {"text": " Hello "}},
                         {"id": "final", "taskKey": keys["decorate"], "parameters": {"suffix": "!"}},
                     ], "edges": [{"id": "wire", "source": "native", "target": "final", "argument": "text"}]}
            saved = save_flow("summary", graph, {"schema": 1, "nodes": []}, None, root)
            source = (root / "flows" / "summary.py").read_text()
            self.assertNotIn("editor_", source)
            self.assertTrue((root / "flows" / "summary.toml").is_file())
            expected = {"final": "hello!"}
            self.assertEqual(expected, load_local_flow("summary", project=root)())
            (root / "flows" / "summary.layout.json").unlink()
            cli = self._command(root, "-m", "weavem", "flow", "run", "summary")
            self.assertEqual(expected, json.loads(cli.stdout.strip().splitlines()[-1]))
            # The worker invokes the same source in a fresh interpreter; its only
            # extra responsibility is bounded diagnostic observation.
            reopened = open_flow("summary", root)
            self.assertTrue(reopened["editable"])
            request = root / "request.json"
            events = root / "events.jsonl"
            request.write_text(json.dumps({"project": str(root), "flowName": "summary",
                                           "revision": reopened["revision"], "params": {}}))
            self._command(root, "-m", "weavem.editor_worker", str(request), str(events))
            emitted = [json.loads(line) for line in events.read_text().splitlines()]
            terminal = [e for e in emitted if e["type"] == "run" and e["status"] == "completed"]
            self.assertEqual(1, len(terminal))
            self.assertEqual(expected, ast.literal_eval(terminal[0]["result"]))
            completed = {e["nodeId"] for e in emitted if e["type"] == "node" and e["status"] == "completed"}
            self.assertEqual({"native", "final"}, completed)
            self.assertNotEqual(saved["revision"], reopened["revision"])

    def test_branch_join_repeated_alias_and_python_objects_are_not_serialized(self):
        from weavem.flows import load_local_flow
        with workspace("saved-object-graph-") as raw:
            root = Path(raw)
            keys = self._project(root, [
                ("stream", "from io import StringIO\ndef run(text): return StringIO(text)\n", "python"),
                ("consume", "def run(stream): return stream.read()\n", "python"),
                ("join", "def run(left, right): return left + right\n", "python"),
            ])
            graph = {"kind": "weavem.graph", "schema": 1, "name": "joined",
                     "nodes": [
                         {"id": "a", "taskKey": keys["stream"], "parameters": {"text": "hello"}},
                         {"id": "b", "taskKey": keys["stream"], "parameters": {"text": " world"}},
                         {"id": "c", "taskKey": keys["consume"], "parameters": {}},
                         {"id": "d", "taskKey": keys["consume"], "parameters": {}},
                         {"id": "e", "taskKey": keys["join"], "parameters": {}},
                     ], "edges": [
                         {"id": "ac", "source": "a", "target": "c", "argument": "stream"},
                         {"id": "bd", "source": "b", "target": "d", "argument": "stream"},
                         {"id": "ce", "source": "c", "target": "e", "argument": "left"},
                         {"id": "de", "source": "d", "target": "e", "argument": "right"},
                     ]}
            save_flow("joined", graph, None, None, root)
            self.assertEqual({"e": "hello world"}, load_local_flow("joined", project=root)())
            reopened = open_flow("joined", root)
            self.assertEqual(5, len(reopened["graph"]["nodes"]))
            self.assertEqual(4, len(reopened["graph"]["edges"]))


if __name__ == "__main__":
    unittest.main()
