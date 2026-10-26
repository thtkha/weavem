#!/usr/bin/env python3
"""Exercise an installed Weavem wheel without using a checkout.

This is intentionally a stdlib-only release gate.  CI copies this file outside
the checkout and invokes it with ``python -I`` after installing the wheel into
a fresh virtual environment.  Its work directory is evidence, not scratch:
it is never removed after a failure.
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
    """A release-gate assertion failed after its evidence was recorded."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Gate:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.logs = root / "logs"
        self.logs.mkdir()
        self.commands: list[dict[str, Any]] = []
        self.environment = self._environment()

    def _environment(self) -> dict[str, str]:
        artifacts = self.root / "artifacts"
        for directory in (artifacts, artifacts / "home", artifacts / "tmp", artifacts / "prefect", artifacts / "pip-cache"):
            directory.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        # Never inherit an operator's store, server, database, or active profile.
        for key in list(environment):
            if key.startswith("PREFECT_") or key in {"PYTHONPATH", "PYTHONHOME", "WEAVEM_STORE"}:
                environment.pop(key)
        environment["HOME"] = str(artifacts / "home")
        environment["TMPDIR"] = str(artifacts / "tmp")
        environment["PIP_CACHE_DIR"] = str(artifacts / "pip-cache")
        environment["PREFECT_HOME"] = str(artifacts / "prefect")
        environment["PREFECT_SERVER_ANALYTICS_ENABLED"] = "false"
        environment["WEAVEM_ARTIFACTS_DIR"] = str(artifacts / "weavem")
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONNOUSERSITE"] = "1"
        return environment

    def command(self, label: str, *command: str, cwd: Path, expect: int = 0) -> subprocess.CompletedProcess[str]:
        started = time.time()
        try:
            result = subprocess.run(
                list(command), cwd=cwd, env=self.environment, text=True,
                capture_output=True, check=False, timeout=TIMEOUT_SECONDS,
            )
            timeout = False
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")
            result = subprocess.CompletedProcess(command, 124, stdout, stderr)
            timeout = True
        (self.logs / f"{label}.stdout").write_text(result.stdout or "", encoding="utf-8")
        (self.logs / f"{label}.stderr").write_text(result.stderr or "", encoding="utf-8")
        entry = {
            "label": label, "argv": list(command), "cwd": str(cwd),
            "returncode": result.returncode, "expected_returncode": expect,
            "timed_out": timeout, "elapsed_seconds": round(time.time() - started, 3),
        }
        self.commands.append(entry)
        (self.logs / "commands.json").write_text(json.dumps(self.commands, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if timeout:
            raise GateFailure(f"{label} timed out after {TIMEOUT_SECONDS} seconds")
        if result.returncode != expect:
            detail = (result.stderr or result.stdout or "command failed").strip()
            raise GateFailure(f"{label} returned {result.returncode}, expected {expect}: {detail}")
        return result


def _metadata(root: Path) -> dict[str, Any]:
    import weavem

    origin = Path(weavem.__file__).resolve()
    distribution = importlib.metadata.distribution("weavem")
    origin_text = str(origin)
    if not any(part in {"site-packages", "dist-packages"} for part in origin.parts):
        raise GateFailure(f"weavem must import from an installed distribution, got {origin}")
    if origin.is_relative_to(root.resolve()) or "/src/weavem/" in f"{origin_text}/":
        raise GateFailure(f"weavem import is not isolated from the checkout: {origin}")
    prefix = Path(sys.prefix).resolve()
    if not origin.is_relative_to(prefix):
        raise GateFailure(f"weavem must be installed under the active environment ({prefix}), got {origin}")
    direct_url_text = distribution.read_text("direct_url.json")
    if direct_url_text is not None:
        try:
            direct_url = json.loads(direct_url_text)
        except json.JSONDecodeError as exc:
            raise GateFailure("installed weavem direct_url.json is invalid") from exc
        if direct_url.get("dir_info", {}).get("editable"):
            raise GateFailure("weavem must not be installed editable for this gate")
    versions = {}
    for name in ("weavem", "prefect", "fastapi", "starlette", "Cython", "setuptools", "ziglang"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return {
        "python": sys.version,
        "executable": sys.executable,
        "cwd": str(Path.cwd().resolve()),
        "weavem_version": importlib.metadata.version("weavem"),
        "weavem_origin": str(origin),
        "weavem_distribution": str(distribution.locate_file("")),
        "direct_url": json.loads(direct_url_text) if direct_url_text is not None else None,
        "distribution_versions": versions,
        "sys_path": sys.path,
    }


def _write_task(task_dir: Path, *, version: str, multiplier: int) -> None:
    (task_dir / "task.toml").write_text(
        "[task]\n"
        "schema = 1\n"
        "task_id = \"release.money\"\n"
        f"version = \"{version}\"\n"
        "backend = \"cython\"\n"
        "source = \"implementation.py\"\n"
        "export = \"money\"\n"
        "dependencies = []\n",
        encoding="utf-8",
    )
    (task_dir / "implementation.py").write_text(
        f"def money(value: int) -> int:\n    return value * {multiplier}\n",
        encoding="utf-8",
    )
    (task_dir / "tests" / "test_task.py").write_text(
        "import unittest\nfrom implementation import money\n\n"
        "class MoneyTests(unittest.TestCase):\n"
        f"    def test_money(self):\n        self.assertEqual(money(7), {7 * multiplier})\n",
        encoding="utf-8",
    )


def _write_flow(project: Path, *, version: str, expected: int) -> None:
    (project / "flows" / "money_flow.toml").write_text(
        "[flow]\n"
        "schema = 1\n"
        "flow_id = \"release.money_flow\"\n"
        f"version = \"{version}\"\n"
        "source = \"money_flow.py\"\n"
        "export = \"money_flow\"\n"
        "tasks = [\"money\"]\n",
        encoding="utf-8",
    )
    (project / "flows" / "money_flow.py").write_text(
        "from weavem import flow, task\n\n"
        "money = task(\"money\")\n\n"
        "@flow\n"
        "def money_flow(value: int) -> int:\n"
        "    return money(value)\n",
        encoding="utf-8",
    )
    tests = project / "tests" / "flows" / "money_flow"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "test_flow.py").write_text(
        "import unittest\nfrom flows.money_flow import money\n\n"
        "class FlowTests(unittest.TestCase):\n"
        f"    def test_bound_task_behavior(self):\n        self.assertEqual(money.fn(7), {expected})\n",
        encoding="utf-8",
    )


def _json_ref(result: subprocess.CompletedProcess[str]) -> str:
    try:
        data = json.loads(result.stdout)
        return str(data["root"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise GateFailure(f"Weavem did not return a candidate reference: {result.stdout!r}") from exc


def _run_json(gate: Gate, label: str, project: Path, *args: str, expected_value: int) -> None:
    result = gate.command(label, sys.executable, "-m", "weavem", *args, cwd=project)
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise GateFailure(f"{label} did not return JSON: {result.stdout!r}") from exc
    if value != expected_value:
        raise GateFailure(f"{label} returned {value!r}, expected {expected_value}")


def _plain_prefect(gate: Gate, directory: Path) -> None:
    script = directory / "plain_prefect.py"
    script.write_text(
        "from prefect import flow\n\n@flow\ndef increment(value):\n    return value + 1\n\n"
        "result = increment(4)\nassert result == 5, result\nprint(result)\n",
        encoding="utf-8",
    )
    gate.command("plain-prefect-flow", sys.executable, "-I", str(script), cwd=directory)


def _snapshot_tree(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): _sha256(path) for path in sorted(root.rglob("*")) if path.is_file()}


def _assert_preserved_releases(before: dict[str, str], after: dict[str, str]) -> None:
    prefixes = tuple(str(Path(name).parent) + "/" for name in before if name.endswith("/manifest.json"))
    current = {name: digest for name, digest in after.items() if name.startswith(prefixes)}
    if current != before:
        raise GateFailure("published v1 release snapshot changed after v2 publication")


def _flow_release_root(store: Path, version: str) -> Path:
    release = store / "_flows" / "release.money_flow" / version
    roots = [path for path in release.iterdir() if path.is_dir()]
    if len(roots) != 1:
        raise GateFailure(f"published flow {version} has an ambiguous release directory")
    return roots[0]


def _compile_store_and_assert_flow_cache(gate: Gate, store: Path, *, version: str) -> None:
    """Generate derived bytecode and prove the published flow received it.

    The handoff deliberately copies this cache with the store.  It is not a
    replacement payload or a filtered test fixture.
    """
    gate.command(f"compileall-store-after-flow-v{version}", sys.executable, "-m", "compileall", "-q", ".", cwd=store)
    root = _flow_release_root(store, version)
    cache = root / "__pycache__"
    if not cache.is_dir() or cache.is_symlink():
        raise GateFailure(f"compileall did not create a regular flow cache for {version}")
    cached_files = list(cache.iterdir())
    if not cached_files or not any(path.is_file() and not path.is_symlink() and path.suffix == ".pyc" for path in cached_files):
        raise GateFailure(f"compileall did not create a .pyc cache entry for flow {version}")


def _assert_native_release(store: Path) -> None:
    roots = [path for path in (store / "release.money" / "1.0.0").iterdir() if path.is_dir()]
    if len(roots) != 1:
        raise GateFailure("published native task has an ambiguous release directory")
    manifest = json.loads((roots[0] / "manifest.json").read_text(encoding="utf-8"))
    payload = roots[0] / manifest["artifact_name"]
    if manifest.get("backend") != "cython":
        raise GateFailure("published task was not recorded as a Cython/native artifact")
    if not payload.name.endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES)):
        raise GateFailure(f"native payload does not have an extension-module suffix: {payload.name}")
    if payload.read_bytes()[:4] != b"\x7fELF":
        raise GateFailure("native payload is not an ELF binary")


def run(root: Path) -> dict[str, Any]:
    gate = Gate(root)
    result: dict[str, Any] = {"status": "running", "metadata": _metadata(root)}
    (root / "metadata.json").write_text(json.dumps(result["metadata"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    author = root / "author"
    consumer = root / "consumer"
    source_hidden = root / "author-source-hidden"
    store = author / "task-store"
    try:
        _plain_prefect(gate, root)
        gate.command("project-new", sys.executable, "-m", "weavem", "project", "new", str(author), cwd=root)
        task_dir = author / "tasks" / "money"
        gate.command("task-new", sys.executable, "-m", "weavem", "task", "new", str(task_dir), "--backend", "cython", cwd=root)
        _write_task(task_dir, version="1.0.0", multiplier=2)
        _write_flow(author, version="1.0.0", expected=14)
        gate.command("task-use-local", sys.executable, "-m", "weavem", "task", "use", "money", "--path", "tasks/money", cwd=author)
        _run_json(gate, "local-editable-flow-v1", author, "flow", "run", "money_flow", "--params", '{"value": 7}', expected_value=14)
        for action in ("validate", "test"):
            gate.command(f"task-v1-{action}", sys.executable, "-m", "weavem", "task", action, str(task_dir), cwd=author)
        candidate_v1 = _json_ref(gate.command("task-v1-build", sys.executable, "-m", "weavem", "task", "build", str(task_dir), cwd=author))
        gate.command("task-v1-publish", sys.executable, "-m", "weavem", "task", "publish", candidate_v1, "--to", str(store), cwd=author)
        _assert_native_release(store)
        gate.command("task-use-v1", sys.executable, "-m", "weavem", "task", "use", "money", "--release", "release.money==1.0.0", cwd=author)
        for action in ("validate", "test"):
            gate.command(f"flow-v1-{action}", sys.executable, "-m", "weavem", "flow", action, "money_flow", cwd=author)
        flow_candidate_v1 = _json_ref(gate.command("flow-v1-build", sys.executable, "-m", "weavem", "flow", "build", "money_flow", cwd=author))
        gate.command("flow-v1-publish", sys.executable, "-m", "weavem", "flow", "publish", flow_candidate_v1, "--to", str(store), cwd=author)
        _run_json(gate, "local-flow-v1", author, "flow", "run", "money_flow", "--params", '{"value": 7}', expected_value=14)

        _compile_store_and_assert_flow_cache(gate, store, version="1.0.0")
        v1_bytes = _snapshot_tree(store)
        result["v1_store_sha256"] = v1_bytes
        gate.command("consumer-project-new", sys.executable, "-m", "weavem", "project", "new", str(consumer), cwd=root)
        shutil.copytree(store, consumer / "task-store")
        if _snapshot_tree(consumer / "task-store") != v1_bytes:
            raise GateFailure("consumer handoff did not copy the complete unfiltered v1 store")
        author.rename(source_hidden)
        if author.exists():
            raise GateFailure("author source path remained available after handoff")
        _run_json(gate, "released-flow-v1-consumer", consumer, "flow", "run", "release.money_flow==1.0.0", "--release", "--params", '{"value": 7}', expected_value=14)

        source_hidden.rename(author)
        task_dir = author / "tasks" / "money"
        _write_task(task_dir, version="1.0.0", multiplier=3)
        conflict_candidate = _json_ref(gate.command("task-v1-conflict-build", sys.executable, "-m", "weavem", "task", "build", str(task_dir), cwd=author))
        conflict = gate.command("task-v1-conflict-rejected", sys.executable, "-m", "weavem", "task", "publish", conflict_candidate, "--to", str(store), cwd=author, expect=2)
        if "version already published with different bytes" not in conflict.stderr:
            raise GateFailure("changed v1 publication was rejected for an unexpected reason")
        _write_task(task_dir, version="2.0.0", multiplier=3)
        for action in ("validate", "test"):
            gate.command(f"task-v2-{action}", sys.executable, "-m", "weavem", "task", action, str(task_dir), cwd=author)
        candidate_v2 = _json_ref(gate.command("task-v2-build", sys.executable, "-m", "weavem", "task", "build", str(task_dir), cwd=author))
        gate.command("task-v2-publish", sys.executable, "-m", "weavem", "task", "publish", candidate_v2, "--to", str(store), cwd=author)
        gate.command("task-use-v2", sys.executable, "-m", "weavem", "task", "use", "money", "--release", "release.money==2.0.0", cwd=author)
        _write_flow(author, version="2.0.0", expected=21)
        for action in ("validate", "test"):
            gate.command(f"flow-v2-{action}", sys.executable, "-m", "weavem", "flow", action, "money_flow", cwd=author)
        flow_candidate_v2 = _json_ref(gate.command("flow-v2-build", sys.executable, "-m", "weavem", "flow", "build", "money_flow", cwd=author))
        gate.command("flow-v2-publish", sys.executable, "-m", "weavem", "flow", "publish", flow_candidate_v2, "--to", str(store), cwd=author)
        _compile_store_and_assert_flow_cache(gate, store, version="2.0.0")
        after_v2 = _snapshot_tree(store)
        _assert_preserved_releases(v1_bytes, after_v2)
        shutil.copytree(store, consumer / "task-store", dirs_exist_ok=True)
        if _snapshot_tree(consumer / "task-store") != after_v2:
            raise GateFailure("consumer handoff did not copy the complete unfiltered v2 store")
        author.rename(source_hidden)
        _run_json(gate, "released-flow-v1-after-v2", consumer, "flow", "run", "release.money_flow==1.0.0", "--release", "--params", '{"value": 7}', expected_value=14)
        _run_json(gate, "released-flow-v2-consumer", consumer, "flow", "run", "release.money_flow==2.0.0", "--release", "--params", '{"value": 7}', expected_value=21)
        result["status"] = "passed"
        result["candidates"] = {"task_v1": candidate_v1, "task_v1_conflict": conflict_candidate,
                                "task_v2": candidate_v2, "flow_v1": flow_candidate_v1,
                                "flow_v2": flow_candidate_v2}
        result["v2_store_sha256"] = after_v2
        return result
    finally:
        result["commands"] = gate.commands
        (root / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, type=Path, help="new absent directory retained as evidence")
    args = parser.parse_args()
    root = args.work_dir.resolve()
    if root.exists():
        parser.error(f"--work-dir must not already exist: {root}")
    if not root.parent.is_dir():
        parser.error(f"--work-dir parent does not exist: {root.parent}")
    root.mkdir()
    try:
        summary = run(root)
    except BaseException as exc:
        result_path = root / "result.json"
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
        else:
            result = {"commands": []}
        result.update({"status": "failed", "error": str(exc), "traceback": traceback.format_exc()})
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"installed-wheel verification failed; evidence retained in {root}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
