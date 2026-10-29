import base64
import hashlib
import json
from pathlib import Path
import unittest
import tomllib
from unittest.mock import patch

from weavem.editor_flows import FlowConflictError, FlowPersistenceError, list_flows, open_flow, save_flow
from tests._support import workspace


class EditorFlowsTests(unittest.TestCase):
    def project(self, root):
        root.mkdir()
        (root / "weavem.toml").write_text('[tasks.one]\npath = "tasks/one"\n[tasks.two]\npath = "tasks/two"\n')
        for name in ("one", "two"):
            task = root / "tasks" / name; task.mkdir(parents=True)
            (task / "task.toml").write_text(f'[task]\nschema = 1\ntask_id = "demo.{name}"\nversion = "1.0.0"\nbackend = "python"\nsource = "task.py"\ninputs = []\noutput = "object"\n')
            (task / "task.py").write_text("def run(**kwargs): return kwargs\n")
        return root

    def graph(self, root, name="demo"):
        one = root / "tasks" / "one" / "task.toml"; two = root / "tasks" / "two" / "task.toml"
        return {"kind":"weavem.graph", "schema":1, "name":name, "nodes":[
            {"id":"first-node", "taskKey":f"local:{one.resolve()}", "parameters":{"value": 1}},
            {"id":"second-node", "taskKey":f"local:{two.resolve()}", "parameters":{}},
        ], "edges":[{"id":"one", "source":"first-node", "target":"second-node", "argument":"input"}]}

    def test_save_open_roundtrip_and_dependencies(self):
        with workspace() as raw:
            root = self.project(Path(raw) / "project")
            saved = save_flow("demo", self.graph(root), {"schema":1,"nodes":[]}, None, root)
            self.assertTrue(saved["editable"])
            self.assertEqual(["one", "two"], tomllib.loads((root / "flows" / "demo.toml").read_text())["flow"]["tasks"])
            self.assertEqual(self.graph(root), saved["graph"])
            self.assertEqual({"schema":1,"nodes":[]}, saved["layout"])
            self.assertIn('from weavem import flow, task', saved["source"])
            self.assertEqual([{"name":"demo", "revision":saved["revision"], "editable":True, "reason":None}], list_flows(root))

    def test_generation_orders_dependencies_and_uses_safe_bindings(self):
        with workspace() as raw:
            root = self.project(Path(raw) / "project")
            graph = self.graph(root)
            graph["nodes"].reverse()  # input order is intentionally not execution order
            saved = save_flow("demo", graph, None, None, root)
            text = saved["source"]
            self.assertLess(text.index("_weavem_node_1 ="), text.index("_weavem_node_2 ="))
            self.assertIn("_weavem_task_1 = task(", text)

    def test_valid_authored_order_and_terminal_result_order_survive_save(self):
        with workspace() as raw:
            root = self.project(Path(raw) / "project")
            graph = self.graph(root)
            graph["nodes"].append({**graph["nodes"][0], "id": "independent"})
            saved = save_flow("demo", graph, None, None, root)
            self.assertEqual(["first-node", "second-node", "independent"],
                             [node["id"] for node in saved["graph"]["nodes"]])
            again = save_flow("demo", saved["graph"], None, saved["revision"], root)
            self.assertEqual(saved["source"], again["source"])

    def test_aliases_with_escapes_are_preserved_in_python_and_toml(self):
        with workspace() as raw:
            root = self.project(Path(raw) / "project")
            alias = "odd\\alias\nname"
            config = root / "weavem.toml"
            config.write_text(config.read_text().replace("[tasks.one]", f"[tasks.{json.dumps(alias)}]"))
            saved = save_flow("demo", self.graph(root), None, None, root)
            self.assertTrue(saved["editable"])
            self.assertEqual([alias, "two"], tomllib.loads((root / "flows" / "demo.toml").read_text())["flow"]["tasks"])

    def test_concurrent_saves_do_not_both_win_the_same_revision(self):
        from concurrent.futures import ThreadPoolExecutor
        with workspace() as raw:
            root = self.project(Path(raw) / "project")
            saved = save_flow("demo", self.graph(root), None, None, root)
            def attempt(value):
                graph = self.graph(root); graph["nodes"][0]["parameters"]["value"] = value
                try:
                    save_flow("demo", graph, None, saved["revision"], root)
                    return "saved"
                except FlowConflictError:
                    return "conflict"
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(["conflict", "saved"], sorted(pool.map(attempt, [2, 3])))

    def test_unsupported_import_decorator_and_early_return_are_not_editable(self):
        with workspace() as raw:
            root = self.project(Path(raw) / "project")
            saved = save_flow("demo", self.graph(root), None, None, root)
            path = root / "flows" / "demo.py"
            for replacement in ("import os\n", "@flow(name='changed')", "    return {}\n"):
                original = saved["source"]
                if replacement.startswith("import"):
                    mutated = replacement + original
                elif replacement.startswith("@"):
                    mutated = original.replace("@flow", replacement)
                else:
                    mutated = original.replace("    # weavem-node", replacement + "    # weavem-node", 1)
                path.write_text(mutated)
                self.assertFalse(open_flow("demo", root)["editable"])
                path.write_text(original)

    def test_stale_revision_and_create_only(self):
        with workspace() as raw:
            root = self.project(Path(raw) / "project")
            saved = save_flow("demo", self.graph(root), None, None, root)
            (root / "flows" / "demo.py").write_text("# changed\n")
            with self.assertRaises(FlowConflictError): save_flow("demo", self.graph(root), None, saved["revision"], root)
            with self.assertRaises(FlowConflictError): save_flow("demo", self.graph(root), None, None, root)

    def test_lexical_shadowing_annotations_and_invalid_keywords_are_source_only(self):
        with workspace() as raw:
            root = self.project(Path(raw) / "project")
            saved = save_flow("demo", self.graph(root), None, None, root)
            source = root / "flows" / "demo.py"
            mutations = [
                saved["source"].replace("_weavem_task_1", "flow"),
                saved["source"].replace("_weavem_task_1", "demo"),
                saved["source"].replace("def demo():", "def demo() -> dangerous():"),
                saved["source"].replace("from weavem import flow, task", ""),
                saved["source"].replace("value=1", "return_state=True"),
            ]
            for mutated in mutations:
                source.write_text(mutated)
                opened = open_flow("demo", root)
                self.assertFalse(opened["editable"], mutated)
                with self.assertRaises(FlowPersistenceError):
                    save_flow("demo", self.graph(root), None, opened["revision"], root)
                self.assertEqual(mutated, source.read_text())

    def test_different_metadata_export_is_source_only_not_unreadable(self):
        with workspace() as raw:
            root = self.project(Path(raw) / "project")
            name = "demo"
            saved = save_flow(name, self.graph(root, name), None, None, root)
            self.assertTrue(saved["editable"])
            metadata = root / "flows" / f"{name}.toml"
            metadata.write_text(metadata.read_text().replace(f'export = "{name}"', 'export = "another_export"'))
            opened = open_flow(name, root)
            self.assertFalse(opened["editable"])
            self.assertTrue(opened["revision"])

    def test_unsupported_python_is_never_executed_or_overwritten(self):
        with workspace() as raw:
            root = self.project(Path(raw) / "project")
            flow = root / "flows"; flow.mkdir()
            marker = root / "marker"
            source = f'from pathlib import Path\nPath({str(marker)!r}).write_text("ran")\n'
            (flow / "demo.py").write_text(source)
            (flow / "demo.toml").write_text('[flow]\nschema=1\nflow_id="demo"\nversion="0.1.0"\nsource="demo.py"\nexport="demo"\ntasks=[]\n')
            loaded = open_flow("demo", root)
            self.assertFalse(loaded["editable"]); self.assertFalse(marker.exists())
            with self.assertRaisesRegex(FlowPersistenceError, "unsupported handwritten"):
                save_flow("demo", self.graph(root), None, loaded["revision"], root)
            self.assertEqual(source, (flow / "demo.py").read_text())

    def test_failed_multi_file_save_restores_previous_flow(self):
        with workspace() as raw:
            root = self.project(Path(raw) / "project")
            saved = save_flow("demo", self.graph(root), {"old": True}, None, root)
            before = [(root / "flows" / filename).read_bytes() for filename in ("demo.py", "demo.toml", "demo.layout.json")]
            original = __import__("os").replace
            calls = 0
            def fail_second(source, target):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected replacement failure")
                return original(source, target)
            changed = self.graph(root); changed["nodes"][0]["parameters"] = {"value": 2}
            with patch("weavem.editor_flows.os.replace", side_effect=fail_second):
                with self.assertRaises(OSError): save_flow("demo", changed, {"new": True}, saved["revision"], root)
            after = [(root / "flows" / filename).read_bytes() for filename in ("demo.py", "demo.toml", "demo.layout.json")]
            self.assertEqual(before, after)

    def test_path_safety_and_layout_removal(self):
        with workspace() as raw:
            root = self.project(Path(raw) / "project")
            with self.assertRaises(FlowPersistenceError): save_flow("../bad", self.graph(root), None, None, root)
            saved = save_flow("demo", self.graph(root), {"a":1}, None, root)
            saved = save_flow("demo", self.graph(root), None, saved["revision"], root)
            self.assertIsNone(saved["layout"])
            self.assertFalse((root / "flows" / "demo.layout.json").exists())

    def _journal(self, root, old, new):
        paths = [root / "flows" / name for name in ("demo.py", "demo.toml", "demo.layout.json")]
        journal = root / "flows" / ".weavem-editor-demo.journal"
        journal.write_text(json.dumps({"names": [p.name for p in paths],
                                      "old": [None if b is None else base64.b64encode(b).decode() for b in old],
                                      "new": [None if b is None else hashlib.sha256(b).hexdigest() for b in new]}))
        return paths, journal

    def test_partial_crash_recovers_on_open_and_before_save_revision_check(self):
        with workspace() as raw:
            root = self.project(Path(raw) / "project")
            saved = save_flow("demo", self.graph(root), {"old": True}, None, root)
            old = [(root / "flows" / n).read_bytes() for n in ("demo.py", "demo.toml", "demo.layout.json")]
            new = [old[0] + b"\n# staged change\n", old[1], b'{"new":true}']
            paths, journal = self._journal(root, old, new)
            paths[0].write_bytes(new[0])
            self.assertEqual(saved["revision"], open_flow("demo", root)["revision"])
            self.assertFalse(journal.exists())
            self._journal(root, old, new)
            paths[0].write_bytes(new[0])
            save_flow("demo", self.graph(root), None, saved["revision"], root)

    def test_completed_crash_is_kept_and_foreign_edits_or_deletions_are_not_restored(self):
        with workspace() as raw:
            root = self.project(Path(raw) / "project")
            save_flow("demo", self.graph(root), {"old": True}, None, root)
            old = [(root / "flows" / n).read_bytes() for n in ("demo.py", "demo.toml", "demo.layout.json")]
            new = [old[0] + b"\n# new source\n", old[1], b'{"new":true}']
            paths, journal = self._journal(root, old, new)
            for p, data in zip(paths, new): p.write_bytes(data)
            self.assertIn("new source", open_flow("demo", root)["source"])
            self.assertFalse(journal.exists())
            for foreign in (b"# independent external change\n", None):
                self._journal(root, old, new)
                if foreign is None: paths[0].unlink()
                else: paths[0].write_bytes(foreign)
                with self.assertRaises(FlowConflictError): open_flow("demo", root)
                self.assertTrue(journal.exists())
                self.assertEqual(foreign, paths[0].read_bytes() if paths[0].exists() else None)

    def test_failure_after_source_replace_rolls_back_immediately(self):
        with workspace() as raw:
            root = self.project(Path(raw) / "project")
            saved = save_flow("demo", self.graph(root), {"old": True}, None, root)
            old = [(root / "flows" / n).read_bytes() for n in ("demo.py", "demo.toml", "demo.layout.json")]
            replace = __import__("os").replace
            failed = False
            def fail_metadata(source, target):
                nonlocal failed
                if Path(target).name == "demo.toml" and not failed:
                    failed = True
                    raise OSError("metadata replacement failed")
                return replace(source, target)
            graph = self.graph(root); graph["nodes"][0]["parameters"]["value"] = 99
            with patch("weavem.editor_flows.os.replace", side_effect=fail_metadata):
                with self.assertRaises(OSError): save_flow("demo", graph, {"new": True}, saved["revision"], root)
            self.assertEqual(old, [(root / "flows" / n).read_bytes() for n in ("demo.py", "demo.toml", "demo.layout.json")])

    def test_commit_rechecks_external_change_and_large_journal_recovers(self):
        import weavem.editor_flows as persistence
        with workspace() as raw:
            root = self.project(Path(raw) / "project")
            saved = save_flow("demo", self.graph(root), {"old": True}, None, root)
            atomic = persistence._atomic_write
            path = root / "flows" / "demo.py"
            foreign = path.read_bytes() + b"\n# editor outside Weavem\n"
            def mutate_then_commit(files, expected):
                path.write_bytes(foreign)
                return atomic(files, expected)
            with patch.object(persistence, "_atomic_write", side_effect=mutate_then_commit):
                with self.assertRaises(FlowConflictError): save_flow("demo", self.graph(root), None, saved["revision"], root)
            self.assertEqual(foreign, path.read_bytes())
            # Both individually valid preimages can exceed 1 MB in base64 together.
            path.write_bytes(foreign + b"#" + b"x" * 800_000 + b"\n")
            layout = root / "flows" / "demo.layout.json"
            layout.write_text(json.dumps({"padding": "x" * 800_000}))
            old = [p.read_bytes() for p in (path, root / "flows" / "demo.toml", layout)]
            new = [foreign, old[1], b"{}"]
            _, journal = self._journal(root, old, new)
            path.write_bytes(new[0])
            self.assertTrue(open_flow("demo", root)["editable"])
            self.assertEqual(old[0], path.read_bytes())
            self.assertFalse(journal.exists())

    def test_invalid_names_layout_and_metadata_identity(self):
        with workspace() as raw:
            root = self.project(Path(raw) / "project")
            with self.assertRaises(FlowPersistenceError): save_flow("é", self.graph(root, "é"), None, None, root)
            self.assertFalse((root / "flows").exists())
            saved = save_flow("demo", self.graph(root), {}, None, root)
            metadata = root / "flows" / "demo.toml"
            metadata.write_text(metadata.read_text().replace('flow_id = "demo"', 'flow_id = "team.demo"'))
            layout = root / "flows" / "demo.layout.json"
            layout.write_text("invalid JSON")
            opened = open_flow("demo", root)
            self.assertTrue(opened["editable"])
            self.assertIsNone(opened["layout"])
            self.assertIn("layout", opened["layoutError"])
            save_flow("demo", opened["graph"], None, opened["revision"], root)
            self.assertIn("team.demo", metadata.read_text())
            self.assertNotEqual(saved["revision"], opened["revision"])

if __name__ == "__main__": unittest.main()
