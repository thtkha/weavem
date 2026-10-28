"""Actual Prefect calls: mocks cannot prove the graph/runtime integration."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

from _support import workspace
from weavem.editor_graph import editor_catalog, execute_graph


@unittest.skipUnless(importlib.util.find_spec("prefect"), "Prefect is not installed")
class EditorPrefectTests(unittest.TestCase):
    def _project(self, root: Path, definitions: dict[str, str]):
        bindings = []
        for name, source in definitions.items():
            folder = root / "tasks" / name
            folder.mkdir(parents=True)
            (folder / "task.toml").write_text(
                f'[task]\ntask_id="editor.integration.{name}"\nversion="1.0.0"\n',
                encoding="utf-8",
            )
            (folder / "implementation.py").write_text(source, encoding="utf-8")
            bindings.append(f'[tasks.{name}]\npath="tasks/{name}"\n')
        (root / "weavem.toml").write_text("\n".join(bindings), encoding="utf-8")
        aliases = editor_catalog(root)["bindings"]
        return {alias: key for key, alias in aliases.items()}

    def test_real_prefect_passes_python_objects_between_tasks(self):
        with workspace("editor-prefect-") as raw:
            root = Path(raw)
            keys = self._project(root, {
                "stream": "from io import StringIO\ndef run(text): return StringIO(text)\n",
                "consume": "def run(stream, suffix): return stream.read() + suffix\n",
            })
            graph = {
                "kind": "weavem.graph", "schema": 1, "name": "Object handoff",
                "nodes": [
                    {"id": "source", "taskKey": keys["stream"], "parameters": {"text": "hello"}},
                    {"id": "target", "taskKey": keys["consume"], "parameters": {"suffix": " world"}},
                ],
                "edges": [{"id": "wire", "source": "source", "target": "target", "argument": "stream"}],
            }
            events = []
            result = execute_graph(graph, root, events.append)
            self.assertEqual(result["target"], "hello world")
            self.assertEqual(events[-1], {"type": "run", "status": "completed"})
            self.assertIn("StringIO", next(event["preview"] for event in events
                                            if event.get("nodeId") == "source" and "preview" in event))
            json.dumps(events)  # The actual object stays in Python, not the wire protocol.

    def test_real_prefect_failure_skips_later_task(self):
        with workspace("editor-prefect-") as raw:
            root = Path(raw)
            keys = self._project(root, {
                "fail": "def run(): raise ValueError('intentional editor integration failure')\n",
                "untouched": f"def run(value):\n open({str(root / 'unexpected-side-effect')!r}, 'w').write('ran')\n return value\n",
            })
            graph = {
                "kind": "weavem.graph", "schema": 1, "name": "Fail fast",
                "nodes": [
                    {"id": "bad", "taskKey": keys["fail"], "parameters": {}},
                    {"id": "later", "taskKey": keys["untouched"], "parameters": {}},
                ],
                "edges": [{"id": "wire", "source": "bad", "target": "later", "argument": "value"}],
            }
            events = []
            with self.assertRaisesRegex(ValueError, "intentional editor integration failure"):
                execute_graph(graph, root, events.append)
            self.assertIn({"type": "node", "nodeId": "later", "status": "skipped"}, events)
            self.assertFalse((root / "unexpected-side-effect").exists())
            self.assertEqual(events[-1]["status"], "failed")

    def test_real_prefect_executes_a_pinned_published_native_task(self):
        from weavem.bindings import manifest_digest
        from weavem.build import build, publish
        from weavem.runtime import validate_artifact
        from weavem.store import LocalStore

        with workspace("editor-native-release-") as raw:
            root = Path(raw)
            self._project(root, {"native": "def run(text): return text.strip().lower()\n"})
            task = root / "tasks" / "native"
            with (task / "task.toml").open("a", encoding="utf-8") as definition:
                definition.write('backend="cython"\n')
            tests = task / "tests"
            tests.mkdir()
            (tests / "test_task.py").write_text(
                "import unittest\nfrom implementation import run\n"
                "class T(unittest.TestCase):\n"
                " def test_text(self): self.assertEqual(run(' Hello '), 'hello')\n",
                encoding="utf-8",
            )
            candidate = build(task, project=root)
            ref = publish(candidate, store=LocalStore(root / "task-store"))
            manifest = validate_artifact(ref)
            self.assertEqual("cython", manifest.backend)
            self.assertTrue(manifest.artifact_name.endswith(".so"))
            (root / "weavem.toml").write_text(
                '[tasks.native]\nrelease="editor.integration.native==1.0.0"\n'
                f'source="task-store"\nmanifest_sha256="{manifest_digest(ref.manifest_path)}"\n',
                encoding="utf-8",
            )
            key = next(iter(editor_catalog(root)["bindings"]))
            self.assertTrue(key.startswith("released:"))
            events = []
            result = execute_graph({
                "kind": "weavem.graph", "schema": 1, "name": "Published native task",
                "nodes": [{"id": "native", "taskKey": key, "parameters": {"text": " Hello Weavem "}}],
                "edges": [],
            }, root, events.append)
            self.assertEqual("hello weavem", result["native"])
            self.assertEqual("completed", events[-1]["status"])


if __name__ == "__main__":
    unittest.main()
