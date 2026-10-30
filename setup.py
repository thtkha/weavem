"""Keep setuptools' disposable metadata/build files in the chosen work directory."""
import os
import re
import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist

def require_editor():
    ui = Path(__file__).resolve().parent / "src/weavem/_ui"
    if not (ui / "index.html").is_file() or not any((ui / "assets").glob("*.js")):
        raise RuntimeError("Prebuilt editor assets are missing. Maintainers: run python scripts/stage-editor.py before packaging; consumers should reinstall a complete Weavem distribution.")

    for asset in re.findall(r'(?:src|href)="/([^"\s]+)"', (ui / "index.html").read_text()):
        if not (ui / asset).is_file():
            raise RuntimeError(f"Packaged editor references a missing asset: {asset}; restage the production UI")

class BuildWithEditor(build_py):
    def run(self):
        # Editable checkouts can use --ui-dir without staging production assets.
        if not getattr(self, "editable_mode", False):
            require_editor()
            old_assets = Path(self.build_lib) / "weavem/_ui"
            if old_assets.exists():
                shutil.rmtree(old_assets)
        super().run()

class SdistWithEditor(sdist):
    def run(self):
        require_editor()
        super().run()


work = Path(os.environ.get("WEAVEM_ARTIFACTS_DIR", ".artifacts")).resolve()
metadata = work / "metadata"
metadata.mkdir(parents=True, exist_ok=True)
setup(cmdclass={"build_py": BuildWithEditor, "sdist": SdistWithEditor}, options={"egg_info": {"egg_base": str(metadata)},
               "build": {"build_base": str(work / "framework-build")}})
