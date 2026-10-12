"""Universal artifact validation and the thin lazy Prefect task adapter."""
from __future__ import annotations

import importlib.metadata
import importlib.util
from hashlib import sha256
from dataclasses import replace
from pathlib import Path
import sys
from contextlib import contextmanager
from contextvars import ContextVar
import sysconfig
import tempfile
from threading import RLock
from typing import Callable, Protocol, Any

from .contracts import CompatibilityError, ContractError, IntegrityError, Manifest, ManifestError, PolicyError, sha256_file, require_supported_runtime, source_digest
from .config import ProjectConfig
from .store import ArtifactRef, TaskStore


class TaskPolicy(Protocol):
    def __call__(self, manifest: Manifest) -> bool: ...


_loaded: dict[tuple[str, str], tuple[tuple[str, str, str, str, str], Callable[..., Any]]] = {}
_local_loaded: dict[tuple[str, str], tuple[Manifest, Callable[..., Any]]] = {}
_bound_task_refs: ContextVar[dict[str, tuple[ArtifactRef, str]] | None] = ContextVar("weavem_bound_task_refs", default=None)
_active_project: ContextVar[ProjectConfig | None] = ContextVar("weavem_project", default=None)
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
    _check_policy(manifest, policy)
    return manifest


def _check_policy(manifest: Manifest, policy: TaskPolicy | None) -> None:
    if policy is not None:
        try:
            allowed = policy(manifest)
        except Exception as exc:
            raise PolicyError(f"task policy failed closed: {exc}") from exc
        if allowed is not True:
            raise PolicyError(f"task policy denied {manifest.task_id}=={manifest.version}")


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


def _load_local(path: Path, project: ProjectConfig, policy: TaskPolicy | None):
    """Load editable source independently of the immutable release cache.

    Native source is compiled once per source/config digest in this process.
    Tests remain an explicit developer action, not a side effect of every call.
    """
    from .build import validate, _build_cython, _manifest
    from prefect.tasks import Task
    require_supported_runtime()
    spec, _, source = validate(path)
    raw = source.read_bytes()
    digest = source_digest(raw, spec.to_mapping())
    key = (str(source), digest)
    _check_dependencies(spec)
    with _load_lock:
        if key in _local_loaded:
            manifest, export = _local_loaded[key]
            _check_policy(manifest, policy)
            return export
        # Path salt keeps two editable copies independent, even with equal content.
        salt = sha256((str(source) + digest).encode()).hexdigest()
        leaf = f"_weavem_dev_{salt}"
        if leaf in sys.modules:
            raise IntegrityError("local task module leaf is already occupied")
        if spec.backend == "python":
            manifest = _manifest(spec, leaf, f"{leaf}.py", source, digest, {"backend": "python"})
            manifest = replace(manifest, artifact_sha256=sha256(raw).hexdigest(), artifact_size=len(raw))
            payload = source
            temporary = None
        else:
            project.work_dir.mkdir(parents=True, exist_ok=True)
            temporary = tempfile.TemporaryDirectory(prefix="dev-native-", dir=project.work_dir)
            stage = Path(temporary.name)
            snapshot = stage / source.name
            snapshot.write_bytes(raw)
            try:
                payload, facts = _build_cython(snapshot, stage, leaf)
                manifest = _manifest(spec, leaf, payload.name, payload, digest, {"backend": "cython", **facts})
            except BaseException:
                temporary.cleanup()
                raise
        try:
            _check_policy(manifest, policy)
            loader_spec = importlib.util.spec_from_file_location(leaf, payload)
            if loader_spec is None or loader_spec.loader is None:
                raise IntegrityError("cannot load local task source")
            module = importlib.util.module_from_spec(loader_spec)
            sys.modules[leaf] = module
            try:
                if spec.backend == "python":
                    exec(compile(raw, str(source), "exec"), module.__dict__)
                else:
                    loader_spec.loader.exec_module(module)
                export = getattr(module, spec.export)
                if not callable(export) or isinstance(export, Task):
                    raise IntegrityError("local task export must be a bare callable")
            except BaseException:
                sys.modules.pop(leaf, None)
                raise
            _local_loaded[key] = (manifest, export)
            return export
        finally:
            if temporary is not None:
                temporary.cleanup()


@contextmanager
def bound_project(project: ProjectConfig):
    """Select the author project while importing/running a local flow."""
    token = _active_project.set(project)
    try:
        yield
    finally:
        _active_project.reset(token)

@contextmanager
def bound_tasks(mapping: dict[str, tuple[ArtifactRef, str]]):
    """Temporarily pin aliases to exact validated artifact manifests for a flow run."""
    normalized = dict(mapping)
    token = _bound_task_refs.set(normalized)
    try:
        yield
    finally:
        _bound_task_refs.reset(token)


def task(task_id: str, version: str | None = None, *, store: TaskStore | str | Path | None = None,
         policy: TaskPolicy | None = None, project: str | Path | None = None, **task_options: Any):
    """Return a Prefect Task for an exact release or an explicit project alias."""
    from .config import resolve_project
    from .store import LocalStore
    from prefect import task as prefect_task
    from prefect.cache_policies import NO_CACHE

    # Every normal invocation must reach our integrity/binding checks. Opting into
    # Prefect result caching is explicit and can skip execution (and those checks).
    task_options.setdefault("cache_policy", NO_CACHE)
    active = _bound_task_refs.get()
    if active is not None and (version is not None or task_id not in active):
        raise IntegrityError(f"released flows must use a declared task alias: {task_id}")
    if version is None and store is not None:
        raise ContractError("alias sources are selected in project bindings; store= is only for exact ID/version calls")

    # Released-flow aliases have no ambient project fallback, even if their module
    # is imported from a directory containing unrelated or malformed configuration.
    # Explicit stores select their own source and need no ambient configuration.
    project_config = None
    if active is None and store is None:
        project_config = (resolve_project(project) if project is not None
                          else (_active_project.get() or resolve_project()))

    if version is not None:
        if store is None:
            actual_store: TaskStore = LocalStore(project_config.store_path)
        elif isinstance(store, (str, Path)):
            actual_store = LocalStore(resolve_project(project, store=store).store_path)
        else:
            actual_store = store
        def resolve_ref() -> tuple[ArtifactRef, str | None, str | None]:
            return actual_store.resolve(task_id, version), task_id, version
    else:
        from .bindings import binding_store, manifest_digest, resolve_binding
        def resolve_ref() -> tuple[ArtifactRef, str | None, str | None]:
            # Context is resolved at invocation, so a task declared outside a flow
            # still uses that flow's pinned dependency set.
            active = _bound_task_refs.get()
            if active is not None:
                if task_id not in active:
                    raise IntegrityError(f"bound task alias is not pinned: {task_id}")
                ref, expected_digest = active[task_id]
                if manifest_digest(ref.manifest_path) != expected_digest:
                    raise IntegrityError(f"bound task manifest digest differs for {task_id}")
                return ref, None, None
            if project_config is None:
                raise IntegrityError("released task alias invoked outside its flow binding context")
            binding = resolve_binding(project_config, task_id)
            if binding.path is not None:
                raise IntegrityError("local source is not a published artifact")
            assert binding.release is not None and binding.manifest_sha256 is not None
            requested_id, requested_version = binding.release.split("==", 1)
            selected_store = binding_store(project_config, binding)
            ref = selected_store.resolve(requested_id, requested_version)
            if manifest_digest(ref.manifest_path) != binding.manifest_sha256:
                raise IntegrityError(f"released binding manifest digest differs for {task_id}")
            return ref, requested_id, requested_version

    def invoke(*args: Any, **kwargs: Any) -> Any:
        if version is not None and _bound_task_refs.get() is not None:
            raise IntegrityError("released flows must use declared task aliases, not direct task ID/version calls")
        if version is None and _bound_task_refs.get() is None:
            from .bindings import resolve_binding
            if project_config is None:
                raise IntegrityError("released task alias invoked outside its flow binding context")
            binding = resolve_binding(project_config, task_id)
            if binding.path is not None:
                return _load_local(binding.path, project_config, policy)(*args, **kwargs)
        ref, requested_id, requested_version = resolve_ref()
        export = load_export(ref, task_id=requested_id, version=requested_version, policy=policy)
        return export(*args, **kwargs)
    return prefect_task(**task_options)(invoke)
