"""Distribution metadata contracts, exercised from a freshly built wheel."""
from __future__ import annotations

from email import policy
from email.parser import BytesParser
import hashlib
import io
import json
from pathlib import Path
import subprocess
import shutil
import sys
import unittest
import zipfile

from _support import ROOT, workspace


class PackagingDistributionTests(unittest.TestCase):
    def _assert_header_bundles(self, archive: zipfile.ZipFile) -> None:
        names = set(archive.namelist())
        for minor in ("312", "313", "314", "315"):
            prefix = f"weavem/_native_headers/cpython-{minor}-"
            bundles = {name for name in names if name.startswith(prefix) and name.endswith(".tar.gz")}
            records = {name for name in names if name.startswith(prefix) and name.endswith(".json")}
            self.assertTrue(bundles, f"Missing header archive for CPython {minor}")
            self.assertEqual(records, {name.removesuffix(".tar.gz") + ".json" for name in bundles},
                             f"Header archives and provenance records differ for CPython {minor}")
            for bundle in sorted(bundles):
                stem = bundle.removesuffix(".tar.gz")
                self.assertIn(stem + "-LICENSE.txt", names)
                record = json.loads(archive.read(stem + ".json"))
                self.assertEqual(record["archive"], Path(bundle).name)
                self.assertEqual(record["sha256"], hashlib.sha256(archive.read(bundle)).hexdigest(),
                                 f"Header archive checksum differs: {bundle}")

    def test_header_bundle_assertions_reject_incomplete_or_corrupt_packs(self) -> None:
        files = {}
        for minor in ("312", "313", "314", "315"):
            stem = f"weavem/_native_headers/cpython-{minor}-fixture"
            payload = f"headers for {minor}".encode()
            files[stem + ".tar.gz"] = payload
            files[stem + "-LICENSE.txt"] = b"fixture license"
            files[stem + ".json"] = json.dumps({
                "archive": Path(stem).name + ".tar.gz",
                "sha256": hashlib.sha256(payload).hexdigest(),
            }).encode()

        stem = "weavem/_native_headers/cpython-315-fixture"
        for fault in (None, "missing-json", "missing-archive", "missing-license", "wrong-reference", "wrong-hash"):
            with self.subTest(fault=fault):
                candidate = files.copy()
                if fault in ("missing-json", "missing-archive", "missing-license"):
                    suffix = {"missing-json": ".json", "missing-archive": ".tar.gz",
                              "missing-license": "-LICENSE.txt"}[fault]
                    del candidate[stem + suffix]
                elif fault in ("wrong-reference", "wrong-hash"):
                    record = json.loads(candidate[stem + ".json"])
                    record["archive" if fault == "wrong-reference" else "sha256"] = "incorrect"
                    candidate[stem + ".json"] = json.dumps(record).encode()
                with io.BytesIO() as buffer:
                    with zipfile.ZipFile(buffer, "w") as archive:
                        for name, content in candidate.items():
                            archive.writestr(name, content)
                    buffer.seek(0)
                    with zipfile.ZipFile(buffer) as archive:
                        if fault is None:
                            self._assert_header_bundles(archive)
                        else:
                            with self.assertRaises(AssertionError):
                                self._assert_header_bundles(archive)

    def test_wheel_exposes_native_authoring_dependencies_by_default(self) -> None:
        with workspace("packaging-wheel-") as temporary:
            wheel_dir = Path(temporary) / "wheelhouse"
            # Independent build roots permit parallel interpreter-matrix tests.
            project = Path(temporary) / "project"
            project.mkdir()
            for name in ("pyproject.toml", "README.md", "LICENSE", "NOTICE", "TRADEMARKS.md"):
                shutil.copyfile(ROOT / name, project / name)
            shutil.copytree(ROOT / "src", project / "src",
                            ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    "--no-deps",
                    "--no-build-isolation",
                    "--no-index",
                    str(project),
                    "--wheel-dir",
                    str(wheel_dir),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0)
            wheels = list(wheel_dir.glob("weavem-*.whl"))
            self.assertEqual(len(wheels), 1)

            with zipfile.ZipFile(wheels[0]) as archive:
                metadata_name = next(
                    name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
                )
                metadata = BytesParser(policy=policy.default).parsebytes(archive.read(metadata_name))
                self._assert_header_bundles(archive)

        requirements = metadata.get_all("Requires-Dist", [])
        self.assertEqual(set(metadata["Requires-Python"].split(",")), {">=3.12", "<3.16"})
        self.assertIn("Programming Language :: Python :: 3.15", metadata.get_all("Classifier", []))
        self.assertIn("prefect==3.9.0", requirements)
        self.assertIn("fastapi==0.143.0", requirements)
        self.assertIn("Cython==3.3.0", requirements)
        self.assertIn("setuptools==84.0.0", requirements)
        self.assertIn("ziglang==0.17.0", requirements)
        self.assertIn("native", metadata.get_all("Provides-Extra", []))
