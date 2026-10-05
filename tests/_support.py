"""Shared test workspace: no implicit /tmp or developer-home artifacts."""
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = Path(os.environ.get("WEAVEM_ARTIFACTS_DIR", ROOT / ".artifacts")).resolve()
ARTIFACTS.mkdir(parents=True, exist_ok=True)
TMP = ARTIFACTS / "tmp"
TMP.mkdir(exist_ok=True)
os.environ["PREFECT_HOME"] = str(ARTIFACTS / "prefect")
os.environ["TMPDIR"] = str(TMP)
os.environ["PREFECT_SERVER_ANALYTICS_ENABLED"] = "false"
os.environ["PREFECT_LOGGING_LEVEL"] = "WARNING"
os.environ["PIP_NO_INDEX"] = "1"
os.environ.pop("PREFECT_API_URL", None)
os.environ.pop("PREFECT_API_KEY", None)
tempfile.tempdir = str(TMP)


def workspace(prefix="weavem-test-"):
    return tempfile.TemporaryDirectory(prefix=prefix, dir=TMP)
