"""Distribution metadata contracts, exercised from a freshly built wheel."""
from __future__ import annotations

from email import policy
from email.parser import BytesParser
from pathlib import Path
import subprocess
import shutil
import sys
import unittest
import zipfile

from _support import ROOT, workspace


class PackagingDistributionTests(unittest.TestCase):
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
                for minor in ("312", "313", "314", "315"):
                    self.assertTrue(any(name.startswith(f"weavem/_native_headers/cpython-{minor}-")
                                        and name.endswith(".tar.gz") for name in archive.namelist()))
                    self.assertTrue(any(name.startswith(f"weavem/_native_headers/cpython-{minor}-")
                                        and name.endswith("-LICENSE.txt") for name in archive.namelist()))

        requirements = metadata.get_all("Requires-Dist", [])
        self.assertEqual(set(metadata["Requires-Python"].split(",")), {">=3.12", "<3.16"})
        self.assertIn("Programming Language :: Python :: 3.15", metadata.get_all("Classifier", []))
        self.assertIn("prefect==3.9.0", requirements)
        self.assertIn("fastapi==0.143.0", requirements)
        self.assertIn("Cython==3.3.0", requirements)
        self.assertIn("setuptools==84.0.0", requirements)
        self.assertIn("ziglang==0.17.0", requirements)
        self.assertIn("native", metadata.get_all("Provides-Extra", []))
