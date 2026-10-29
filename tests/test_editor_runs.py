from __future__ import annotations
import os
from pathlib import Path
import unittest
from _support import workspace
from weavem.editor_runs import (RunInspectionError, capture_snapshot, latest_run,
                                read_snapshot, write_run_state, write_snapshot)

class EditorRunTests(unittest.TestCase):
    def snapshot(self):
        return capture_snapshot({"name":"demo","revision":"rev","source":"def demo(): pass", "graph":{"nodes":[]}, "layout":None,
                                 "sourceSha256":"source", "metadataSha256":"meta"},
                                {"metadata":{"tasks":[]}, "bindings":{"x":"task"}}, {"value": 1}, started_at="now")
    def test_snapshot_roundtrip_and_latest_is_flow_specific(self):
        with workspace() as raw:
            root=Path(raw); directory=root/"editor-runs"/"one"; directory.mkdir(parents=True)
            write_snapshot(directory, self.snapshot()); write_run_state(directory, {"status":"completed","nodes":{},"result":"ok"})
            self.assertEqual("demo", read_snapshot(directory)["flowName"])
            found=latest_run(root,"demo")
            self.assertEqual("one", found["runId"]); self.assertEqual("completed",found["state"]["status"])
            self.assertIsNone(latest_run(root,"other"))
    def test_invalid_or_symlink_records_are_not_followed(self):
        with workspace() as raw:
            root=Path(raw); directory=root/"editor-runs"/"bad"; directory.mkdir(parents=True)
            (directory/"inspection.json").write_text("not json")
            self.assertIsNone(latest_run(root,"demo"))
            outside=root/"outside"; outside.mkdir(); os.symlink(outside, root/"editor-runs"/"link")
            self.assertIsNone(latest_run(root,"demo"))
    def test_preserves_large_definition_and_more_than_200_nodes(self):
        with workspace() as raw:
            directory=Path(raw)/"run"; directory.mkdir()
            snap=self.snapshot(); snap["source"]="x"*(65*1024)
            snap["graph"]={"nodes":[{"id":str(index)} for index in range(201)]}
            write_snapshot(directory, snap)
            loaded=read_snapshot(directory)
            self.assertEqual(snap["source"], loaded["source"])
            self.assertEqual(201, len(loaded["graph"]["nodes"]))
    def test_rejects_non_json_or_oversize_before_write(self):
        with workspace() as raw:
            directory=Path(raw)/"run"; directory.mkdir()
            with self.assertRaises(RunInspectionError): write_run_state(directory,{"status":"ok","bad":object()})
            snap=self.snapshot(); snap["source"]="x"*(9*1024*1024)
            with self.assertRaises(RunInspectionError): write_snapshot(directory,snap)
            self.assertFalse((directory/"inspection.json").exists())
if __name__ == '__main__': unittest.main()

class LastStartedRunTests(unittest.TestCase):
    def test_polling_old_run_does_not_make_it_latest(self):
        import os
        from weavem.editor_runs import capture_snapshot, write_snapshot, write_run_state, latest_run
        with workspace() as raw:
            root = Path(raw); runs = root / "editor-runs"; runs.mkdir()
            old = runs / "old"; new = runs / "new"; old.mkdir(); new.mkdir()
            snap = capture_snapshot({"name": "demo", "revision": "r1", "source": "x"}, {}, {})
            write_snapshot(old, snap); write_snapshot(new, snap)
            os.utime(old / "inspection.json", ns=(1, 1))
            os.utime(new / "inspection.json", ns=(2, 2))
            write_run_state(old, {"status": "completed"})
            self.assertEqual("new", latest_run(root, "demo")["runId"])
