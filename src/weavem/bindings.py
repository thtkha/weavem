"""Explicit project task bindings; importing this module never imports task code."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import tomllib
from typing import Mapping

from .config import ProjectConfig
from .contracts import ContractError, Manifest, ManifestError, _validate_identity

_RELEASE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*==[^=\s]+$")
_HEX = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class TaskBinding:
    alias: str
    path: Path | None = None
    release: str | None = None
    source: str | None = None
    manifest_sha256: str | None = None


def read_bindings(project: ProjectConfig) -> dict[str, TaskBinding]:
    """Read `[tasks.<alias>]` entries from the selected project's config."""
    if project.config_path is None:
        return {}
    try:
        data = tomllib.loads(project.config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ContractError(f"cannot read project config: {exc}") from exc
    tasks = data.get("tasks", {})
    if not isinstance(tasks, dict):
        raise ContractError("tasks must be a table")
    result: dict[str, TaskBinding] = {}
    for alias, raw in tasks.items():
        if not isinstance(alias, str) or not alias or not isinstance(raw, dict):
            raise ContractError("each task binding must be a named table")
        unknown = set(raw) - {"path", "release", "source", "manifest_sha256"}
        if unknown:
            raise ContractError(f"unknown task binding fields: {', '.join(sorted(unknown))}")
        path, release = raw.get("path"), raw.get("release")
        source, digest = raw.get("source"), raw.get("manifest_sha256")
        if (path is None) == (release is None):
            raise ContractError(f"task binding {alias} requires exactly one of path or release")
        if path is not None:
            if not isinstance(path, str) or not path:
                raise ContractError(f"task binding {alias} path must be a string")
            if source is not None or digest is not None:
                raise ContractError(f"path task binding {alias} cannot specify release metadata")
            candidate = (project.root / path).resolve()
            try:
                candidate.relative_to(project.root.resolve())
            except ValueError as exc:
                raise ContractError(f"task binding {alias} path escapes project") from exc
            result[alias] = TaskBinding(alias=alias, path=candidate)
        else:
            if not isinstance(release, str) or not _RELEASE.fullmatch(release):
                raise ContractError(f"task binding {alias} release must be id==version")
            _validate_identity(*release.split("==", 1))
            if not isinstance(source, str) or not source:
                raise ContractError(f"released task binding {alias} requires an explicit source path")
            if not isinstance(digest, str) or not _HEX.fullmatch(digest):
                raise ContractError(f"released task binding {alias} requires manifest_sha256")
            result[alias] = TaskBinding(alias=alias, release=release, source=source, manifest_sha256=digest)
    return result


def resolve_binding(bindings: Mapping[str, TaskBinding] | ProjectConfig, alias: str) -> TaskBinding:
    """Return the explicit binding for *alias*, never falling back to an id."""
    actual = read_bindings(bindings) if isinstance(bindings, ProjectConfig) else bindings
    try:
        return actual[alias]
    except KeyError as exc:
        raise ContractError(f"task binding not found: {alias}") from exc


def manifest_digest(path: Path) -> str:
    """Digest canonical manifest bytes, never formatting supplied on disk."""
    try:
        canonical = Manifest.from_json_bytes(path.read_bytes()).to_json_bytes()
    except (OSError, ManifestError) as exc:
        raise ContractError(f"invalid bound manifest: {exc}") from exc
    return hashlib.sha256(canonical).hexdigest()


def binding_store(project: ProjectConfig, binding: TaskBinding):
    """Resolve a selected folder, never search other sources for the same ID."""
    from .store import LocalStore
    if binding.source is None:
        raise ContractError(f"task binding {binding.alias} is local, not a release")
    root = project.store_path if binding.source == "task-store" else project.root / Path(binding.source).expanduser()
    return LocalStore(root)
