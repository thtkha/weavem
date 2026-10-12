"""Project-root and local path resolution; imports no orchestration dependencies."""
from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path
import tomllib
from typing import Mapping
from .contracts import ContractError

@dataclass(frozen=True)
class ProjectConfig:
    root: Path
    store_path: Path
    work_dir: Path
    config_path: Path | None = None


def _bound(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    # Paths are anchored at the selected project root, but may deliberately point
    # to a shared sibling store or be absolute.
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _read_config(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ContractError(f"cannot read project config: {exc}") from exc
    section = data.get("weavem", {}) if "weavem" in data else {key: value for key, value in data.items() if key != "tasks"}
    if not isinstance(section, dict):
        raise ContractError("weavem.toml must contain a table")
    allowed = {"store", "store_path", "work_dir", "artifacts_dir"}
    unknown = set(section) - allowed
    if unknown:
        raise ContractError(f"unknown project config fields: {', '.join(sorted(unknown))}")
    return section


def resolve_project(project: str | Path | None = None, *, cwd: str | Path | None = None,
                    environ: Mapping[str, str] | None = None, store: str | Path | None = None,
                    work_dir: str | Path | None = None) -> ProjectConfig:
    env = os.environ if environ is None else environ
    current = Path.cwd() if cwd is None else Path(cwd)
    current = current.resolve()
    config_path: Path | None
    if project is not None:
        target = Path(project).expanduser().resolve()
        if target.is_file() or target.name == "weavem.toml":
            if not target.is_file():
                raise ContractError(f"explicit project config does not exist: {target}")
            root, config_path = target.parent, target
        elif target.is_dir():
            root = target
            candidate = root / "weavem.toml"
            config_path = candidate if candidate.is_file() else None
        else:
            raise ContractError(f"explicit project path does not exist: {target}")
    else:
        root, config_path = current, None
        for candidate_root in (current, *current.parents):
            candidate = candidate_root / "weavem.toml"
            if candidate.is_file():
                root, config_path = candidate_root, candidate
                break
    settings = _read_config(config_path)
    def choice(explicit: str | Path | None, env_key: str, config_keys: tuple[str, ...], default: str) -> Path:
        if explicit is not None:
            return _bound(root, explicit)
        if env.get(env_key):
            return _bound(root, env[env_key])
        for key in config_keys:
            if key in settings:
                value = settings[key]
                if not isinstance(value, str):
                    raise ContractError(f"{key} must be a string")
                return _bound(root, value)
        return root / default
    return ProjectConfig(root=root, store_path=choice(store, "WEAVEM_STORE", ("store", "store_path"), "task-store"),
                         work_dir=choice(work_dir, "WEAVEM_ARTIFACTS_DIR", ("work_dir", "artifacts_dir"), ".artifacts"), config_path=config_path)
