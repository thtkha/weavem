"""Source distribution build guard regression."""
from pathlib import Path
import unittest

class EditorPackagingTests(unittest.TestCase):
    def test_normal_build_refuses_missing_editor_assets(self) -> None:
        import subprocess, sys
        from tempfile import TemporaryDirectory
        root = Path(__file__).resolve().parents[1]
        evidence = root / '.artifacts' / 'packaging-tests'
        evidence.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=evidence) as temp:
            copy = Path(temp)
            (copy / 'setup.py').write_text((root / 'setup.py').read_text())
            (copy / 'pyproject.toml').write_text((root / 'pyproject.toml').read_text())
            result = subprocess.run([sys.executable, 'setup.py', 'build_py'], cwd=copy, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Prebuilt editor assets are missing', result.stderr)
