"""Packaging contracts that do not require Weavem runtime dependencies."""
from __future__ import annotations

from pathlib import Path
import tomllib
import unittest


class PackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[1]
        cls.package = tomllib.loads((root / "pyproject.toml").read_text())

    def test_native_authoring_tools_are_default_dependencies(self) -> None:
        dependencies = self.package["project"]["dependencies"]
        self.assertIn("Cython==3.3.0", dependencies)
        self.assertIn("setuptools==84.0.0", dependencies)
        self.assertIn("ziglang==0.17.0", dependencies)

    def test_native_extra_remains_a_compatible_no_op(self) -> None:
        self.assertEqual(self.package["project"]["optional-dependencies"]["native"], [])

    def test_prebuilt_editor_assets_are_package_data(self) -> None:
        patterns = self.package['tool']['setuptools']['package-data']['weavem']
        self.assertIn('_ui/index.html', patterns)
        self.assertIn('_ui/assets/*', patterns)
