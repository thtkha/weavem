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
    def test_rejects_non_json_and_oversized_text(self):
        with workspace() as raw:
            directory=Path(raw)/"run"; directory.mkdir()
            with self.assertRaises(RunInspectionError): write_run_state(directory,{"status":"ok","bad":object()})
            snap=self.snapshot(); snap["source"]="x"*(65*1024)
            write_snapshot(directory, snap)
            self.assertEqual(64 * 1024, len(read_snapshot(directory)["source"]))
if __name__ == '__main__': unittest.main()
