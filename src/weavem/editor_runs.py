"""Bounded, local records for inspecting an editor flow's last run.

These files are diagnostic evidence, never an execution queue or replay format.
They live beside the existing worker logs in ``editor-runs/<uuid>/`` so a bridge
restart can still show what completed without claiming it can resume work.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

_MAX_FILE = 256 * 1024
_MAX_TEXT = 64 * 1024
_SNAPSHOT = "inspection.json"
_STATE = "inspection-state.json"


class RunInspectionError(ValueError):
    """A persisted editor-run inspection record is unsafe or malformed."""


def _json(value: Any) -> Any:
    """Return JSON data with recursively bounded strings, or reject it."""
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise RunInspectionError("run inspection does not support non-finite numbers")
        return value
    if isinstance(value, str):
        return value[:_MAX_TEXT]
    if isinstance(value, list):
        return [_json(item) for item in value[:200]]
    if isinstance(value, dict):
        return {str(key)[:256]: _json(item) for key, item in list(value.items())[:200]}
    raise RunInspectionError("run inspection only stores JSON values")


def _sha(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def capture_snapshot(opened: dict[str, Any], catalog: dict[str, Any], params: dict[str, Any], *,
                     started_at: str | None = None) -> dict[str, Any]:
    """Capture the inspected definition before its worker is launched.

    ``opened`` is deliberately the output of ``editor_flows.open_flow``: it
    supplies exact source/metadata hashes without importing task code.
    """
    name = opened.get("name")
    revision = opened.get("revision")
    if not isinstance(name, str) or not isinstance(revision, str):
        raise RunInspectionError("flow snapshot requires name and revision")
    source = opened.get("source")
    if source is not None and not isinstance(source, str):
        raise RunInspectionError("flow snapshot source must be text")
    graph = opened.get("graph")
    layout = opened.get("layout")
    return {
        "schema": 1,
        "flowName": name,
        "revision": revision,
        "source": source[:_MAX_TEXT] if isinstance(source, str) else None,
        "sourceSha256": opened.get("sourceSha256") if isinstance(opened.get("sourceSha256"), str) else _sha(source),
        "metadataSha256": opened.get("metadataSha256") if isinstance(opened.get("metadataSha256"), str) else None,
        "graph": _json(graph) if graph is not None else None,
        "layout": _json(layout) if layout is not None else None,
        "catalog": _json(catalog),
        "bindings": _json(catalog.get("bindings", {})) if isinstance(catalog, dict) else {},
        "params": _json(params),
        "startedAt": started_at,
    }


def _record_path(directory: str | Path, name: str) -> Path:
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise RunInspectionError("editor run directory must be a regular directory")
    path = root / name
    if path.is_symlink():
        raise RunInspectionError("editor inspection record must not be symlinked")
    return path


def _write(directory: str | Path, name: str, value: dict[str, Any]) -> None:
    path = _record_path(directory, name)
    payload = json.dumps(_json(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(payload) > _MAX_FILE:
        raise RunInspectionError("editor inspection record is too large")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload); output.flush(); os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_snapshot(directory: str | Path, snapshot: dict[str, Any]) -> None:
    """Atomically persist the immutable definition an editor run inspected."""
    if snapshot.get("schema") != 1:
        raise RunInspectionError("unsupported editor inspection snapshot")
    _write(directory, _SNAPSHOT, snapshot)


def write_run_state(directory: str | Path, state: dict[str, Any]) -> None:
    """Atomically persist a bounded terminal or active run state."""
    if not isinstance(state.get("status"), str):
        raise RunInspectionError("run inspection state requires status")
    _write(directory, _STATE, state)


def _read(directory: str | Path, name: str) -> dict[str, Any] | None:
    path = _record_path(directory, name)
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > _MAX_FILE:
        raise RunInspectionError("editor inspection record is invalid")
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunInspectionError("editor inspection record is invalid") from exc
    if not isinstance(value, dict):
        raise RunInspectionError("editor inspection record must be an object")
    return value


def read_snapshot(directory: str | Path) -> dict[str, Any] | None:
    value = _read(directory, _SNAPSHOT)
    if value is not None and (value.get("schema") != 1 or not isinstance(value.get("flowName"), str)
                              or not isinstance(value.get("revision"), str)):
        raise RunInspectionError("editor inspection snapshot is invalid")
    return value


def latest_run(work_dir: str | Path, flow_name: str) -> dict[str, Any] | None:
    """Return the most recently modified valid record for ``flow_name``.

    Invalid/foreign entries are ignored: diagnostics must never make opening a
    project fail. A state is optional, allowing inspection while a worker runs.
    """
    root = Path(work_dir) / "editor-runs"
    if root.is_symlink() or not root.exists():
        return None
    if not root.is_dir():
        return None
    found: list[tuple[int, dict[str, Any]]] = []
    for directory in root.iterdir():
        try:
            if directory.is_symlink() or not directory.is_dir():
                continue
            snapshot = read_snapshot(directory)
            if snapshot is None or snapshot["flowName"] != flow_name:
                continue
            state = _read(directory, _STATE)
            found.append((directory.stat().st_mtime_ns, {"runId": directory.name, "snapshot": snapshot, "state": state}))
        except (OSError, RunInspectionError):
            continue
    return max(found, key=lambda item: item[0])[1] if found else None
