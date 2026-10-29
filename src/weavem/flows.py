"""Local flow development and immutable, dependency-pinned flow releases."""
from __future__ import annotations

import functools
import hashlib
import importlib.util
import inspect
import json
import keyword
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from threading import RLock
import time
import tomllib

from .bindings import binding_store, manifest_digest, read_bindings
from .config import resolve_project
from .contracts import (CompatibilityError, IntegrityError, ManifestError, StoreError,
                        _validate_identity, require_supported_runtime, sha256_file, source_digest)
from .flow_contracts import FlowManifest, FlowSpec
from .runtime import bound_project, bound_tasks, validate_artifact
from .store import ArtifactRef, LocalStore


class FlowError(RuntimeError):
    """A flow source or release failed a lifecycle check."""


_loaded_flows: dict[str, tuple[bytes, object]] = {}
_flow_lock = RLock()


def _regular_tree(path: Path) -> None:
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise IntegrityError(f"symlinked flow path is not allowed: {path}")


def _spec(project, name: str, *, expected_metadata_sha256: str | None = None) -> tuple[FlowSpec, Path]:
    if (not name.isidentifier() or keyword.iskeyword(name)
            or (name.startswith("__") and name.endswith("__"))):
        raise FlowError("local flow name must be a non-reserved Python identifier")
    root = project.root / "flows"
    sidecar = root / f"{name}.toml"
    _regular_tree(sidecar)
    try:
        raw = sidecar.read_bytes()
        if expected_metadata_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_metadata_sha256:
            raise FlowError("flow metadata changed on disk; reload before running")
        data = tomllib.loads(raw.decode("utf-8"))
        spec = FlowSpec.from_mapping(data.get("flow", data))
    except (OSError, ValueError) as exc:
        raise FlowError(f"cannot read flow metadata: {exc}") from exc
    source = root / spec.source
    _regular_tree(source)
    if not source.is_file():
        raise FlowError(f"flow source does not exist: {source}")
    return spec, source


def _pins(project, spec):
    bindings = read_bindings(project)
    pins, dependencies = {}, []
    for alias in spec.tasks:
        binding = bindings.get(alias)
        if binding is None:
            raise FlowError(f"flow task binding not found: {alias}")
        if binding.release is None:
            raise FlowError(f"flow task {alias} is local; publish it and select its exact release first")
        task_id, version = binding.release.split("==", 1)
        ref = binding_store(project, binding).resolve(task_id, version)
        validate_artifact(ref, requested_task_id=task_id, requested_version=version)
        if manifest_digest(ref.manifest_path) != binding.manifest_sha256:
            raise IntegrityError(f"flow task binding digest differs: {alias}")
        pins[alias] = (ref, binding.manifest_sha256)
        dependencies.append({"alias": alias, "task_id": task_id, "version": version,
                             "manifest_sha256": binding.manifest_sha256})
    return pins, tuple(dependencies)


def _supported_flow(value):
    from prefect.flows import Flow
    from prefect.task_runners import ThreadPoolTaskRunner
    if not isinstance(value, Flow):
        raise FlowError("flow export must be a Prefect Flow")
    if (inspect.iscoroutinefunction(value.fn) or inspect.isasyncgenfunction(value.fn)
            or inspect.isgeneratorfunction(value.fn)):
        raise FlowError("async and generator flow exports are not supported by flow releases")
    # Pins use process-local ContextVars; do not silently lose them in remote workers.
    if type(value.task_runner) is not ThreadPoolTaskRunner:
        raise FlowError("flow releases require the local ThreadPoolTaskRunner")
    return value


def _import_flow(root: Path, manifest: FlowManifest, pins):
    payload = root / manifest.artifact_name
    raw = payload.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest.artifact_sha256 or len(raw) != manifest.artifact_size:
        raise IntegrityError("flow payload changed before import")
    identity = manifest.to_json_bytes()
    with _flow_lock:
        cached = _loaded_flows.get(manifest.module_leaf)
        if cached is not None:
            if cached[0] != identity:
                raise IntegrityError("flow module leaf is already occupied by a different manifest")
            return cached[1]
        if manifest.module_leaf in sys.modules:
            raise IntegrityError("flow module leaf is already occupied")
        loader = importlib.util.spec_from_file_location(manifest.module_leaf, payload)
        if loader is None or loader.loader is None:
            raise IntegrityError("cannot create flow loader")
        module = importlib.util.module_from_spec(loader)
        sys.modules[manifest.module_leaf] = module
        try:
            with bound_tasks(pins):
                exec(compile(raw, str(payload), "exec"), module.__dict__)
            value = _supported_flow(getattr(module, manifest.export, None))
        except BaseException:
            sys.modules.pop(manifest.module_leaf, None)
            raise
        _loaded_flows[manifest.module_leaf] = (identity, value)
        return value


def _subprocess_env():
    # Tests/import smoke use the installed package, never the author's PYTHONPATH.
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _encoded_pins(pins) -> str:
    return json.dumps({alias: [str(ref.root), digest] for alias, (ref, digest) in pins.items()})


_PIN_SCRIPT = (
    "import json,pathlib,sys\n"
    "from weavem.runtime import bound_tasks\n"
    "from weavem.store import ArtifactRef\n"
    "pins={k:(ArtifactRef(pathlib.Path(v[0])),v[1]) for k,v in json.loads(sys.argv[1]).items()}\n"
)


def _run_flow_tests(project, name, source, raw, pins) -> None:
    tests = project.root / "tests" / "flows" / name
    _regular_tree(tests)
    if not tests.is_dir():
        raise FlowError(f"flow tests are required in tests/flows/{name}")
    with tempfile.TemporaryDirectory(prefix="flow-test-", dir=project.work_dir) as temporary:
        sandbox = Path(temporary)
        (sandbox / "flows").mkdir()
        (sandbox / "flows" / "__init__.py").write_text("")
        snapshot = sandbox / "flows" / source.name
        snapshot.write_bytes(raw)
        shutil.copytree(tests, sandbox / "tests")
        (sandbox / "weavem.toml").write_text("[weavem]\n")
        script = _PIN_SCRIPT + (
            "import unittest\n"
            "sys.path.insert(0,str(pathlib.Path.cwd()))\n"
            "with bound_tasks(pins):\n"
            " suite=unittest.defaultTestLoader.discover('tests')\n"
            " if not suite.countTestCases(): raise SystemExit(3)\n"
            " raise SystemExit(not unittest.TextTestRunner().run(suite).wasSuccessful())\n"
        )
        result = subprocess.run([sys.executable, "-I", "-c", script, _encoded_pins(pins)],
                                cwd=sandbox, env=_subprocess_env(), text=True, capture_output=True)
        if not snapshot.is_file() or snapshot.read_bytes() != raw:
            raise FlowError("flow source tests mutated the build snapshot")
        if result.returncode == 3:
            raise FlowError("flow source tests must contain at least one test")
        if result.returncode:
            raise FlowError(f"flow source tests failed: {result.stderr.strip() or result.stdout.strip()}")


def validate_source_flow(name, *, project=None, work_dir=None) -> None:
    """Check flow metadata and declared bindings without executing source."""
    project_config = resolve_project(project, work_dir=work_dir)
    spec, _ = _spec(project_config, name)
    bindings = read_bindings(project_config)
    from .build import validate
    for alias in spec.tasks:
        binding = bindings.get(alias)
        if binding is None:
            raise FlowError(f"flow task binding not found: {alias}")
        if binding.path is not None:
            validate(binding.path)
        else:
            _pins(project_config, FlowSpec(spec.schema, spec.flow_id, spec.version,
                                          spec.source, spec.export, (alias,)))


def test_flow(name, *, project=None, work_dir=None) -> None:
    """Run authored development tests; local source dependencies are allowed."""
    config = resolve_project(project, work_dir=work_dir)
    validate_source_flow(name, project=config.root)
    tests = config.root / "tests" / "flows" / name
    _regular_tree(tests)
    if not tests.is_dir():
        raise FlowError(f"flow tests are required in tests/flows/{name}")
    script = (
        "import pathlib,sys,unittest\n"
        "sys.path.insert(0,str(pathlib.Path.cwd()))\n"
        "suite=unittest.defaultTestLoader.discover(sys.argv[1])\n"
        "if not suite.countTestCases(): raise SystemExit(3)\n"
        "raise SystemExit(not unittest.TextTestRunner().run(suite).wasSuccessful())\n"
    )
    result = subprocess.run([sys.executable, "-I", "-c", script, str(tests)], cwd=config.root,
                            env=_subprocess_env(), text=True, capture_output=True)
    if result.returncode == 3:
        raise FlowError("flow source tests must contain at least one test")
    if result.returncode:
        raise FlowError(f"flow source tests failed: {result.stderr.strip() or result.stdout.strip()}")


def build_flow(name, *, project=None, work_dir=None) -> ArtifactRef:
    require_supported_runtime()
    config = resolve_project(project, work_dir=work_dir)
    spec, source = _spec(config, name)
    # This gate is before imports, tests, workspace creation, or any publication.
    pins, deps = _pins(config, spec)
    raw = source.read_bytes()
    config.work_dir.mkdir(parents=True, exist_ok=True)
    _run_flow_tests(config, name, source, raw, pins)
    digest = source_digest(raw, spec.to_mapping() | {"task_dependencies": list(deps)})
    leaf = f"_weavem_flow_{digest}"
    stage = Path(tempfile.mkdtemp(prefix="flow-candidate-", dir=config.work_dir))
    try:
        payload = stage / f"{leaf}.py"
        payload.write_bytes(raw)
        manifest = FlowManifest(1, "flow", spec.flow_id, spec.version, leaf, spec.export,
                                payload.name, hashlib.sha256(raw).hexdigest(), len(raw),
                                sys.implementation.cache_tag, sysconfig.get_platform(), deps)
        (stage / "manifest.json").write_bytes(manifest.to_json_bytes())
        script = _PIN_SCRIPT + (
            "from weavem.flows import _import_flow\n"
            "from weavem.flow_contracts import FlowManifest\n"
            "root=pathlib.Path(sys.argv[2])\n"
            "m=FlowManifest.from_json_bytes((root/'manifest.json').read_bytes())\n"
            "_import_flow(root,m,pins)\n"
        )
        result = subprocess.run([sys.executable, "-I", "-c", script, _encoded_pins(pins), str(stage)],
                                cwd=stage, env=_subprocess_env(), text=True, capture_output=True)
        if result.returncode:
            raise FlowError(f"flow artifact smoke failed: {result.stderr.strip() or result.stdout.strip()}")
        _read_flow(ArtifactRef(stage))
        return ArtifactRef(stage)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _store(store=None, project=None) -> LocalStore:
    if isinstance(store, LocalStore):
        return store
    if store is not None and not isinstance(store, (str, Path)):
        raise FlowError("flow releases require a local folder store")
    return LocalStore(resolve_project(project, store=store).store_path)


def _read_flow(ref: ArtifactRef) -> FlowManifest:
    root = ref.root
    _regular_tree(root)
    if not root.is_dir():
        raise IntegrityError(f"flow directory does not exist: {root}")
    try:
        if (root / "manifest.json").is_symlink():
            raise IntegrityError("flow manifest must not be a symlink")
        manifest = FlowManifest.from_json_bytes(ref.manifest_path.read_bytes())
    except (OSError, ManifestError) as exc:
        raise IntegrityError(f"invalid flow manifest: {exc}") from exc
    entries = {entry.name for entry in root.iterdir()}
    unexpected = sorted(entries - {"manifest.json", manifest.artifact_name, "__pycache__"})
    if unexpected:
        raise IntegrityError(f"unexpected flow artifact entries: {', '.join(unexpected)}")
    if "__pycache__" in entries:
        cache = root / "__pycache__"
        if cache.is_symlink() or not cache.is_dir():
            raise IntegrityError(f"invalid flow cache directory: {cache}; expected a non-symlink directory")
        # Derived caches are never read: _import_flow compiles verified source.
        # Reject other contents without following links or recursing into them.
        for entry in cache.iterdir():
            if entry.is_symlink() or not entry.is_file() or entry.suffix != ".pyc":
                raise IntegrityError(f"invalid flow cache entry: {entry}; expected a regular non-symlink .pyc file")
    payload = root / manifest.artifact_name
    if payload.is_symlink():
        raise IntegrityError(f"flow payload must not be a symlink: {payload}")
    if not payload.exists():
        raise IntegrityError(f"flow payload is missing: {payload}")
    if not payload.is_file():
        raise IntegrityError(f"flow payload must be a regular file: {payload}")
    if (sha256_file(payload) != manifest.artifact_sha256
            or payload.stat().st_size != manifest.artifact_size):
        raise IntegrityError(f"flow payload hash or size differs from manifest: {payload}")
    return manifest


def _release_pins(manifest, store):
    pins = {}
    for dep in manifest.task_dependencies:
        ref = store.resolve(dep["task_id"], dep["version"])
        validate_artifact(ref, requested_task_id=dep["task_id"], requested_version=dep["version"])
        if manifest_digest(ref.manifest_path) != dep["manifest_sha256"]:
            raise IntegrityError(f"pinned flow dependency differs: {dep['alias']}")
        pins[dep["alias"]] = (ref, dep["manifest_sha256"])
    return pins


def validate_flow(ref: ArtifactRef, *, store=None) -> FlowManifest:
    require_supported_runtime()
    manifest = _read_flow(ref)
    if (manifest.python_cache_tag != sys.implementation.cache_tag
            or manifest.platform != sysconfig.get_platform()):
        raise CompatibilityError("flow artifact targets an incompatible interpreter/platform")
    _release_pins(manifest, _store(store))
    return manifest


def publish_flow(candidate, *, store=None, project=None) -> ArtifactRef:
    actual = _store(store, project)
    root = candidate.root if isinstance(candidate, ArtifactRef) else Path(candidate).absolute()
    manifest = validate_flow(ArtifactRef(root), store=actual)
    destination = actual.root / "_flows" / manifest.flow_id / manifest.version / manifest.python_cache_tag
    _regular_tree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / f".{destination.name}.lock"
    for _ in range(200):
        try:
            lock.mkdir()
            break
        except FileExistsError:
            time.sleep(0.01)
    else:
        raise StoreError("timed out waiting for cooperative flow publish lock")
    try:
        if destination.exists():
            if validate_flow(ArtifactRef(destination), store=actual).to_json_bytes() == manifest.to_json_bytes():
                return ArtifactRef(destination)
            raise StoreError(f"flow version already published with different bytes: {manifest.flow_id}=={manifest.version}")
        private = Path(tempfile.mkdtemp(prefix=f".{destination.name}.publishing-", dir=destination.parent))
        try:
            shutil.copyfile(root / "manifest.json", private / "manifest.json")
            shutil.copyfile(root / manifest.artifact_name, private / manifest.artifact_name)
            if validate_flow(ArtifactRef(private), store=actual).to_json_bytes() != manifest.to_json_bytes():
                raise IntegrityError("flow destination copy differs from candidate")
            os.replace(private, destination)
            return ArtifactRef(destination)
        finally:
            shutil.rmtree(private, ignore_errors=True)
    finally:
        lock.rmdir()


def load_flow(flow_id, version, *, store=None, project=None):
    """Return a real Prefect Flow using only its recorded task dependencies."""
    actual = _store(store, project)
    ref = FlowStore(actual).resolve(flow_id, version)
    manifest = validate_flow(ref, store=actual)
    identity = manifest.to_json_bytes()
    source_flow = _import_flow(ref.root, manifest, _release_pins(manifest, actual))

    @functools.wraps(source_flow.fn)
    def pinned(*args, **kwargs):
        current = validate_flow(ref, store=actual)
        if current.to_json_bytes() != identity:
            raise IntegrityError("published flow manifest changed after load")
        with bound_tasks(_release_pins(current, actual)):
            return source_flow.fn(*args, **kwargs)

    wrapped = source_flow.with_options()
    wrapped.fn = pinned
    return wrapped


def load_local_flow(name, *, project=None, expected_source_sha256=None, expected_metadata_sha256=None):
    """Load editable flow code with aliases anchored to the selected project.

    Optional expected hashes reject a changed definition before importing the
    exact bytes read here. They are used by revision-aware editor callers; normal
    CLI and Python callers continue to load the current on-disk definition.
    """
    config = resolve_project(project)
    spec, source = _spec(config, name, expected_metadata_sha256=expected_metadata_sha256)
    raw = source.read_bytes()
    if expected_source_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_source_sha256:
        raise FlowError("flow source changed on disk; reload before running")
    # Every local load is an independent source snapshot, not an immutable release.
    leaf = "_weavem_local_flow_" + hashlib.sha256(str(source).encode() + raw).hexdigest() + f"_{time.time_ns()}"
    loader = importlib.util.spec_from_file_location(leaf, source)
    if loader is None or loader.loader is None:
        raise FlowError("cannot create local flow loader")
    module = importlib.util.module_from_spec(loader)
    if leaf in sys.modules:
        raise IntegrityError("local flow module leaf is already occupied")
    sys.modules[leaf] = module
    try:
        with bound_project(config):
            exec(compile(raw, str(source), "exec"), module.__dict__)
        value = _supported_flow(getattr(module, spec.export, None))
    except BaseException:
        sys.modules.pop(leaf, None)
        raise

    @functools.wraps(value.fn)
    def local(*args, **kwargs):
        with bound_project(config):
            return value.fn(*args, **kwargs)

    wrapped = value.with_options()
    wrapped.fn = local
    return wrapped


class FlowStore:
    """Metadata-only discovery in the reserved `_flows` store namespace."""
    def __init__(self, store):
        self.store = store if isinstance(store, LocalStore) else LocalStore(store)

    def resolve(self, flow_id, version) -> ArtifactRef:
        _validate_identity(flow_id, version)
        base = self.store.root / "_flows" / flow_id / version
        _regular_tree(base)
        if not base.is_dir():
            raise StoreError(f"flow not found: {flow_id}=={version}")
        candidates = [p for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")]
        if len(candidates) != 1:
            raise StoreError(f"ambiguous or missing flow release: {flow_id}=={version}")
        ref = ArtifactRef(candidates[0])
        _regular_tree(ref.manifest_path)
        manifest = FlowManifest.from_json_bytes(ref.manifest_path.read_bytes())
        if manifest.flow_id != flow_id or manifest.version != version:
            raise StoreError("stored flow manifest identity differs from request")
        return ref

    def list(self):
        root = self.store.root / "_flows"
        _regular_tree(root)
        if not root.is_dir():
            return ()
        refs = []
        for path in sorted(root.glob("*/*/*/manifest.json")):
            _regular_tree(path)
            if not any(part.startswith(".") for part in path.relative_to(root).parts):
                refs.append(ArtifactRef(path.parent))
        return tuple(refs)
