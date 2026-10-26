#!/usr/bin/env python3
"""Verify a published native store transferred to a fresh machine.

CI runs this file with ``python -I`` on a runner which has only the tested
Weavem wheel and a copied task store.  It deliberately receives neither the
author project nor task source, so success proves that the released flow and
its native task can be consumed without rebuilding.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
from typing import Any


TIMEOUT_SECONDS = 180


class GateFailure(RuntimeError):
    """The transferred-store verification did not establish its contract."""


def _snapshot_tree(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


class Gate:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.logs = root / "logs"
        self.logs.mkdir()
        self.commands: list[dict[str, Any]] = []
        self.environment = self._environment()

    def _environment(self) -> dict[str, str]:
        artifacts = self.root / "artifacts"
        for directory in (artifacts / "home", artifacts / "tmp", artifacts / "prefect"):
            directory.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        for key in list(environment):
            if key.startswith("PREFECT_") or key in {"PYTHONPATH", "PYTHONHOME", "WEAVEM_STORE", "WEAVEM_ARTIFACTS_DIR"}:
                environment.pop(key)
        environment.update({
            "HOME": str(artifacts / "home"),
            "TMPDIR": str(artifacts / "tmp"),
            "PREFECT_HOME": str(artifacts / "prefect"),
            "PREFECT_SERVER_ANALYTICS_ENABLED": "false",
            "WEAVEM_ARTIFACTS_DIR": str(artifacts / "weavem"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        })
        return environment

    def command(self, label: str, *command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        started = time.time()
        try:
            result = subprocess.run(list(command), cwd=cwd, env=self.environment, text=True,
                                    capture_output=True, check=False, timeout=TIMEOUT_SECONDS)
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""
            stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr or ""
            result = subprocess.CompletedProcess(command, 124, stdout, stderr)
            timed_out = True
        (self.logs / f"{label}.stdout").write_text(result.stdout or "", encoding="utf-8")
        (self.logs / f"{label}.stderr").write_text(result.stderr or "", encoding="utf-8")
        self.commands.append({"label": label, "argv": list(command), "cwd": str(cwd),
                              "returncode": result.returncode, "timed_out": timed_out,
                              "elapsed_seconds": round(time.time() - started, 3)})
        (self.logs / "commands.json").write_text(json.dumps(self.commands, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if timed_out:
            raise GateFailure(f"{label} timed out after {TIMEOUT_SECONDS} seconds")
        if result.returncode:
            detail = (result.stderr or result.stdout or "command failed").strip()
            raise GateFailure(f"{label} returned {result.returncode}: {detail}")
        return result


def _expected_snapshot(path: Path) -> dict[str, str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))["v2_store_sha256"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise GateFailure(f"invalid producer handoff record: {path}") from exc
    if not isinstance(value, dict) or not value or not all(isinstance(key, str) and isinstance(digest, str) for key, digest in value.items()):
        raise GateFailure("producer handoff record has no valid store hashes")
    return value


def _assert_installed_distribution() -> dict[str, str]:
    import weavem

    origin = Path(weavem.__file__).resolve()
    prefix = Path(sys.prefix).resolve()
    if not origin.is_relative_to(prefix) or not any(part in {"site-packages", "dist-packages"} for part in origin.parts):
        raise GateFailure(f"weavem must import from the active installed wheel, got {origin}")
    return {"weavem_version": importlib.metadata.version("weavem"), "weavem_origin": str(origin),
            "python": sys.version, "executable": sys.executable}


def _assert_native_loaded(gate: Gate, store: Path, consumer: Path) -> None:
    manifest_path = next((store / "release.money" / "2.0.0").glob("*/manifest.json"), None)
    if manifest_path is None:
        raise GateFailure("transferred store does not contain release.money==2.0.0")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = manifest_path.parent / manifest["artifact_name"]
    if manifest.get("backend") != "cython" or not payload.name.endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES)):
        raise GateFailure("transferred release.money==2.0.0 is not a native extension")
    if payload.read_bytes()[:4] != b"\x7fELF":
        raise GateFailure("transferred native payload is not an ELF binary")
    script = (
        "import json, pathlib, sys\n"
        "from weavem import task\n"
        "store=pathlib.Path(sys.argv[1]).resolve()\n"
        "manifest=json.loads(next((store/'release.money'/'2.0.0').glob('*/manifest.json')).read_text())\n"
        "value=task('release.money','2.0.0',store=store).fn(7)\n"
        "module=sys.modules.get(manifest['module_leaf'])\n"
        "path=pathlib.Path(module.__file__).resolve() if module else None\n"
        "assert value == 21, value\n"
        "assert path is not None and path.is_relative_to(store) and path.suffix == '.so', path\n"
        "print(json.dumps({'value': value, 'module': str(path)}))\n"
    )
    result = gate.command("native-task-from-transferred-store", sys.executable, "-I", "-c", script, str(store), cwd=consumer)
    try:
        details = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise GateFailure("native task check did not return JSON") from exc
    if details.get("value") != 21:
        raise GateFailure("native task did not return the published v2 result")


def _run_flow(gate: Gate, consumer: Path, store: Path, version: str, expected: int) -> None:
    result = gate.command(f"released-flow-{version}", sys.executable, "-m", "weavem", "flow", "run",
                          f"release.money_flow=={version}", "--release", "--store", str(store),
                          "--params", '{"value": 7}', cwd=consumer)
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise GateFailure(f"released flow {version} did not return JSON") from exc
    if value != expected:
        raise GateFailure(f"released flow {version} returned {value!r}, expected {expected}")


def run(root: Path, transferred_store: Path, expected_path: Path) -> dict[str, Any]:
    gate = Gate(root)
    result: dict[str, Any] = {"status": "running", "metadata": _assert_installed_distribution()}
    try:
        expected = _expected_snapshot(expected_path)
        received = _snapshot_tree(transferred_store)
        if received != expected:
            raise GateFailure("transferred store hashes differ from the producer record")
        consumer = root / "consumer"
        gate.command("consumer-project-new", sys.executable, "-m", "weavem", "project", "new", str(consumer), cwd=root)
        copied_store = consumer / "task-store"
        shutil.copytree(transferred_store, copied_store)
        if _snapshot_tree(copied_store) != expected:
            raise GateFailure("consumer store copy changed transferred bytes")
        _assert_native_loaded(gate, copied_store, consumer)
        _run_flow(gate, consumer, copied_store, "1.0.0", 14)
        _run_flow(gate, consumer, copied_store, "2.0.0", 21)
        after = _snapshot_tree(copied_store)
        if after != expected:
            raise GateFailure("consuming released tasks or flows modified the transferred store")
        result.update({"status": "passed", "store_sha256": after})
        return result
    finally:
        result["commands"] = gate.commands
        (root / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True, type=Path, help="transferred published task-store")
    parser.add_argument("--expected", required=True, type=Path, help="producer result.json with store hashes")
    parser.add_argument("--work-dir", required=True, type=Path, help="new absent evidence directory")
    args = parser.parse_args()
    store, expected, root = args.store.resolve(), args.expected.resolve(), args.work_dir.resolve()
    if not store.is_dir():
        parser.error(f"--store must be an existing directory: {store}")
    if not expected.is_file():
        parser.error(f"--expected must be an existing file: {expected}")
    if root.exists() or not root.parent.is_dir():
        parser.error("--work-dir must be a new directory whose parent exists")
    root.mkdir()
    try:
        summary = run(root, store, expected)
    except BaseException as exc:
        result_path = root / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {"commands": []}
        result.update({"status": "failed", "error": str(exc), "traceback": traceback.format_exc()})
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"native handoff verification failed; evidence retained in {root}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
