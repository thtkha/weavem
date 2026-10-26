"""Derived bytecode must not break releases or replace verified flow source."""
from __future__ import annotations

import compileall
import hashlib
import importlib.util
import marshal
import os
from pathlib import Path
import struct
import sys
import sysconfig
import unittest

from _support import workspace
from weavem.contracts import IntegrityError
from weavem.flow_contracts import FlowManifest
from weavem.flows import load_flow, publish_flow, validate_flow
from weavem.store import ArtifactRef, LocalStore


class FlowCacheTests(unittest.TestCase):
    def _candidate(self, root: Path) -> ArtifactRef:
        root.mkdir()
        raw = (f"# {self.id()}\nfrom weavem import flow\n"
               "@flow\ndef report(): return 7\n").encode()
        digest = hashlib.sha256(raw).hexdigest()
        leaf = "_weavem_flow_" + digest
        manifest = FlowManifest(1, "flow", "cache.report", "1.0.0", leaf, "report",
                                leaf + ".py", digest, len(raw), sys.implementation.cache_tag,
                                sysconfig.get_platform(), ())
        (root / "manifest.json").write_bytes(manifest.to_json_bytes())
        (root / manifest.artifact_name).write_bytes(raw)
        return ArtifactRef(root)

    def test_compiled_candidate_and_release_remain_valid_and_idempotent(self):
        with workspace("flow-cache-") as raw:
            root = Path(raw)
            candidate = self._candidate(root / "candidate")
            manifest_bytes = candidate.manifest_path.read_bytes()
            self.assertTrue(compileall.compile_dir(candidate.root, quiet=1))
            self.assertTrue(list((candidate.root / "__pycache__").glob("*.pyc")))
            store = LocalStore(root / "store")
            published = publish_flow(candidate, store=store)
            # Publication copies declared artifacts, not derived caches.
            self.assertEqual(len(list(published.root.iterdir())), 2)
            self.assertTrue(compileall.compile_dir(published.root, quiet=1))
            self.assertEqual(validate_flow(published, store=store).to_json_bytes(), manifest_bytes)
            self.assertEqual(publish_flow(candidate, store=store).root, published.root)
            self.assertEqual(load_flow("cache.report", "1.0.0", store=store).fn(), 7)
            self.assertTrue((published.root / "__pycache__").is_dir())

    def test_empty_cache_is_allowed(self):
        with workspace("flow-cache-") as raw:
            root = Path(raw)
            candidate = self._candidate(root / "candidate")
            (candidate.root / "__pycache__").mkdir()
            validate_flow(candidate, store=LocalStore(root / "store"))

    def test_cached_bytecode_cannot_replace_verified_source(self):
        with workspace("flow-cache-") as raw:
            root = Path(raw)
            store = LocalStore(root / "store")
            published = publish_flow(self._candidate(root / "candidate"), store=store)
            manifest = FlowManifest.from_json_bytes(published.manifest_path.read_bytes())
            payload = published.root / manifest.artifact_name
            cache = Path(importlib.util.cache_from_source(str(payload)))
            cache.parent.mkdir()
            stat = payload.stat()
            code = compile("raise AssertionError('cached code executed')", str(payload), "exec")
            # A timestamp-valid CPython cache would be accepted by a normal loader.
            cache.write_bytes(importlib.util.MAGIC_NUMBER + struct.pack(
                "<III", 0, int(stat.st_mtime) & 0xffffffff, stat.st_size & 0xffffffff
            ) + marshal.dumps(code))
            self.assertEqual(load_flow("cache.report", "1.0.0", store=store).fn(), 7)
            cache.write_bytes(b"not even valid bytecode")
            self.assertEqual(load_flow("cache.report", "1.0.0", store=store).fn(), 7)

    def test_unexpected_release_entries_have_distinct_errors(self):
        with workspace("flow-cache-") as raw:
            root = Path(raw)
            candidate = self._candidate(root / "candidate")
            (candidate.root / "notes.txt").write_text("not a declared artifact")
            with self.assertRaisesRegex(IntegrityError, r"unexpected flow artifact entries: notes\.txt"):
                validate_flow(candidate, store=LocalStore(root / "store"))

    def test_invalid_cache_layout_is_rejected(self):
        cases = ("file", "directory_link", "broken_directory_link", "nested", "text",
                 "file_link", "broken_file_link", "fifo")
        with workspace("flow-cache-") as raw:
            root = Path(raw)
            outside = root / "outside"; outside.mkdir()
            target = outside / "real.pyc"; target.write_bytes(b"unused")
            for case in cases:
                with self.subTest(case=case):
                    candidate = self._candidate(root / case)
                    cache = candidate.root / "__pycache__"
                    if case == "file":
                        cache.write_bytes(b"not a directory")
                    elif case in {"directory_link", "broken_directory_link"}:
                        cache.symlink_to(outside if case == "directory_link" else root / "missing", target_is_directory=True)
                    else:
                        cache.mkdir()
                        if case == "nested": (cache / "nested").mkdir()
                        elif case == "text": (cache / "notes.txt").write_text("unexpected")
                        elif case in {"file_link", "broken_file_link"}:
                            (cache / "linked.pyc").symlink_to(target if case == "file_link" else root / "missing")
                        else: os.mkfifo(cache / "pipe.pyc")
                    with self.assertRaisesRegex(IntegrityError, "invalid flow cache"):
                        validate_flow(candidate, store=LocalStore(root / "store"))

    def test_corrupt_payload_is_rejected_despite_valid_cache(self):
        with workspace("flow-cache-") as raw:
            root = Path(raw)
            candidate = self._candidate(root / "candidate")
            self.assertTrue(compileall.compile_dir(candidate.root, quiet=1))
            manifest = FlowManifest.from_json_bytes(candidate.manifest_path.read_bytes())
            payload = candidate.root / manifest.artifact_name
            payload.write_bytes(payload.read_bytes().replace(b"return 7", b"return 8"))
            with self.assertRaisesRegex(IntegrityError, "flow payload hash or size differs"):
                validate_flow(candidate, store=LocalStore(root / "store"))

    def test_missing_and_unsafe_payload_errors(self):
        cases = ("missing", "directory", "symlink")
        with workspace("flow-cache-") as raw:
            root = Path(raw)
            for case in cases:
                with self.subTest(case=case):
                    candidate = self._candidate(root / case)
                    manifest = FlowManifest.from_json_bytes(candidate.manifest_path.read_bytes())
                    payload = candidate.root / manifest.artifact_name
                    original = payload.read_bytes()
                    payload.unlink()
                    if case == "directory": payload.mkdir()
                    elif case == "symlink":
                        target = root / "outside.py"; target.write_bytes(original)
                        payload.symlink_to(target)
                    expected = {"missing": "flow payload is missing", "directory": "flow payload must be a regular file",
                                "symlink": "flow payload must not be a symlink"}[case]
                    with self.assertRaisesRegex(IntegrityError, expected):
                        validate_flow(candidate, store=LocalStore(root / "store"))


if __name__ == "__main__":
    unittest.main()
