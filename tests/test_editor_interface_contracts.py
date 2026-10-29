from __future__ import annotations

import unittest

from weavem.editor_hints import source_parameter_hint
from weavem.editor_values import safe_preview
from weavem.errors import TaskError, serialize_error
from weavem.contracts import SourceSpec
from tests._support import workspace
from pathlib import Path


class InterfaceContractsTests(unittest.TestCase):
    def test_source_hints_read_literal_nullable_typeddict_and_return_without_importing(self):
        with workspace() as raw:
            task = Path(raw) / "task"; task.mkdir()
            source = task / "impl.py"
            source.write_text('''from typing import Literal, TypedDict\nclass Result(TypedDict):\n    label: str\n    count: int | None\ndef run(mode: Literal["fast", "safe"] = "fast", extra: int | None = None) -> Result:\n    """Useful description."""\n    return {"label": mode, "count": extra}\n''')
            spec = SourceSpec(schema=1, task_id="demo.hints", version="1.0.0", source_path="impl.py", export="run", backend="python", inputs=(), output="object")
            hint = source_parameter_hint(task / "task.toml", spec)
            assert hint is not None
            self.assertEqual("Useful description.", hint["description"])
            self.assertEqual(["fast", "safe"], hint["parameters"][0]["choices"])
            self.assertTrue(hint["parameters"][1]["nullable"])
            self.assertEqual("label", hint["output"]["fields"][0]["name"])

    def test_safe_preview_never_uses_custom_protocols(self):
        class Untrusted:
            def __repr__(self):
                raise AssertionError("repr called")
            def __iter__(self):
                raise AssertionError("iter called")
        preview = safe_preview({"ok": [1, 2], "deep": {"x": "a" * 5000}})
        self.assertEqual("json", preview["kind"])
        self.assertTrue(preview["truncated"])
        unsupported = safe_preview(Untrusted())
        self.assertEqual("text", unsupported["kind"])
        self.assertEqual("<unprintable result>", unsupported["preview"])

    def test_task_error_survives_wrapping_with_remediation(self):
        error = TaskError("bad_input", "Input is invalid", input="customer_id", remediation="Choose an existing ID", retryable=False)
        try:
            raise error
        except TaskError as cause:
            try:
                raise RuntimeError("wrapper") from cause
            except RuntimeError as wrapped:
                payload = serialize_error(wrapped)
        self.assertEqual("bad_input", payload["code"])
        self.assertEqual("customer_id", payload["input"])
        self.assertFalse(payload["retryable"])

class GraphSourcePathTests(unittest.TestCase):
    def test_graph_schema_two_allows_path_but_schema_one_rejects_it(self):
        from weavem.editor_graph import validate_graph, EditorGraphError
        from tests.test_editor_graph import EditorGraphTests
        with workspace() as raw:
            helper = EditorGraphTests()
            root = helper._project(Path(raw) / "project")
            first = helper._local(root, "first", "def run(): return {'items': ['ok']}\n")
            second = helper._local(root, "second", "def run(value): return value\n")
            graph = {"kind":"weavem.graph", "schema":2, "name":"path", "nodes":[
                {"id":"one", "taskKey":f"local:{first.resolve()}", "parameters":{}},
                {"id":"two", "taskKey":f"local:{second.resolve()}", "parameters":{}},
            ], "edges":[{"id":"edge", "source":"one", "target":"two", "argument":"value", "sourcePath":["items", 0]}]}
            self.assertEqual(("items", 0), validate_graph(graph, root).edges[0].source_path)
            graph["schema"] = 1
            with self.assertRaisesRegex(EditorGraphError, "requires schema 2"):
                validate_graph(graph, root)
