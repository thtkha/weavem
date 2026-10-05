"""Universal artifact validation and the thin lazy Prefect task adapter."""
from __future__ import annotations

import importlib.metadata
import importlib.util
from pathlib import Path
import sys
import sysconfig
from threading import RLock
from typing import Callable, Protocol, Any

from .contracts import CompatibilityError, IntegrityError, Manifest, ManifestError, PolicyError, sha256_file, require_supported_runtime
from .store import ArtifactRef, TaskStore


class TaskPolicy(Protocol):
    def __call__(self, manifest: Manifest) -> bool: ...


_loaded: dict[tuple[str, str], tuple[tuple[str, str, str, str, str], Callable[..., Any]]] = {}
_load_lock = RLock()


def _regular_child(root: Path, name: str) -> Path:
    root = root.resolve()
    path = root / name
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise IntegrityError("artifact path escapes its directory") from exc
    if path.is_symlink() or not path.is_file():
        raise IntegrityError("artifact file must be a regular non-symlink file")
    return path


def _check_dependencies(manifest: Manifest) -> None:
    for pin in manifest.dependencies:
        distribution, expected = pin.split("==", 1)
        try:
            installed = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError as exc:
            raise CompatibilityError(f"missing required distribution: {pin}") from exc
        if installed != expected:
            raise CompatibilityError(f"required {pin}, installed {distribution}=={installed}")


def validate_artifact(ref: ArtifactRef, *, requested_task_id: str | None = None,
                      requested_version: str | None = None, policy: TaskPolicy | None = None) -> Manifest:
    require_supported_runtime()
    root = ref.root.resolve()
    if ref.root.is_symlink() or not root.is_dir():
        raise IntegrityError("artifact root must be a local regular directory")
    manifest_path = _regular_child(root, "manifest.json")
    try:
        manifest = Manifest.from_json_bytes(manifest_path.read_bytes())
    except (OSError, ManifestError) as exc:
        raise IntegrityError(f"invalid artifact manifest: {exc}") from exc
    if requested_task_id is not None and manifest.task_id != requested_task_id:
        raise IntegrityError("resolved artifact task id differs from request")
    if requested_version is not None and manifest.version != requested_version:
        raise IntegrityError("resolved artifact version differs from request")
    payload = _regular_child(root, manifest.artifact_name)
    stat = payload.stat()
    if stat.st_size != manifest.artifact_size or sha256_file(payload) != manifest.artifact_sha256:
        raise IntegrityError("artifact payload digest or size does not match manifest")
    if manifest.python_cache_tag != sys.implementation.cache_tag:
        raise CompatibilityError(f"artifact requires {manifest.python_cache_tag}, current is {sys.implementation.cache_tag}")
    if manifest.platform != sysconfig.get_platform():
        raise CompatibilityError(f"artifact requires platform {manifest.platform}")
    expected_suffix = sysconfig.get_config_var("EXT_SUFFIX") or ""
    if manifest.backend == "cython" and (manifest.ext_suffix != expected_suffix or not payload.name.endswith(expected_suffix)):
        raise CompatibilityError("artifact native extension suffix is incompatible")
    if manifest.backend == "python" and payload.suffix != ".py":
        raise IntegrityError("python artifact must have .py payload")
    _check_dependencies(manifest)
    if policy is not None:
        try:
            allowed = policy(manifest)
        except Exception as exc:
            raise PolicyError(f"task policy failed closed: {exc}") from exc
        if allowed is not True:
            raise PolicyError(f"task policy denied {manifest.task_id}=={manifest.version}")
    return manifest


def load_export(ref: ArtifactRef, *, task_id: str | None = None, version: str | None = None,
                policy: TaskPolicy | None = None) -> Callable[..., Any]:
    # Validation intentionally precedes lookup: a cached export never bypasses a
    # later digest/ABI/dependency/policy decision.
    manifest = validate_artifact(ref, requested_task_id=task_id, requested_version=version, policy=policy)
    # Required dependency, imported only at the execution boundary. Discovery
    # stays data-only; a broken Prefect environment must not execute task code.
    from prefect.tasks import Task

    key = (manifest.task_id, manifest.version)
    identity = (manifest.artifact_sha256, manifest.module_leaf, manifest.export,
                manifest.source_digest, manifest.backend)
    with _load_lock:
        existing = _loaded.get(key)
        if existing is not None:
            if existing[0] != identity:
                raise IntegrityError("a different task artifact identity is already loaded")
            return existing[1]
        payload = _regular_child(ref.root.resolve(), manifest.artifact_name)
        if manifest.module_leaf in sys.modules:
            raise IntegrityError("module leaf is already occupied")
        spec = importlib.util.spec_from_file_location(manifest.module_leaf, payload)
        if spec is None or spec.loader is None:
            raise IntegrityError("cannot create module loader for artifact")
        module = importlib.util.module_from_spec(spec)
        sys.modules[manifest.module_leaf] = module
        try:
            if manifest.backend == "python":
                # Compile source directly so an adjacent timestamp-valid .pyc
                # cannot substitute for the checksum-checked source file.
                code = compile(payload.read_bytes(), str(payload), "exec")
                exec(code, module.__dict__)
            else:
                spec.loader.exec_module(module)
            export = getattr(module, manifest.export)
            if not callable(export):
                raise IntegrityError("task export is not callable")
            if isinstance(export, Task):
                raise IntegrityError("task artifact export must be a bare callable, not a Prefect Task")
        except BaseException:
            if sys.modules.get(manifest.module_leaf) is module:
                sys.modules.pop(manifest.module_leaf, None)
            raise
        _loaded[key] = (identity, export)
        return export

def task(task_id: str, version: str, *, store: TaskStore | str | Path | None = None, policy: TaskPolicy | None = None,
         project: str | Path | None = None, **task_options: Any):
    """Return a real Prefect Task that validates and invokes one exact task artifact."""
    from .config import resolve_project
    from .store import LocalStore
    from prefect import task as prefect_task
    if store is None:
        actual_store = LocalStore(resolve_project(project).store_path)
    elif isinstance(store, (str, Path)):
        actual_store = LocalStore(resolve_project(project, store=store).store_path)
    else:
        actual_store = store

    def invoke(*args: Any, **kwargs: Any) -> Any:
        ref = actual_store.resolve(task_id, version)
        export = load_export(ref, task_id=task_id, version=version, policy=policy)
        return export(*args, **kwargs)
    return prefect_task(**task_options)(invoke)
