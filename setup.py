"""Keep setuptools' disposable metadata/build files in the chosen work directory."""
import os
from pathlib import Path

from setuptools import setup

work = Path(os.environ.get("WEAVEM_ARTIFACTS_DIR", ".artifacts")).resolve()
metadata = work / "metadata"
metadata.mkdir(parents=True, exist_ok=True)
setup(options={"egg_info": {"egg_base": str(metadata)},
               "build": {"build_base": str(work / "framework-build")}})
