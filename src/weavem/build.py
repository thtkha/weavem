"""Task validation, testing, build and promotion."""
from __future__ import annotations

import compileall
import importlib.machinery
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tempfile

from .config import resolve_project
from .contracts import ContractError, Manifest, SourceSpec, module_leaf, require_supported_runtime, sha256_file, source_digest
from .store import LocalStore


class BuildError(RuntimeError):
    """A source task could not safely be promoted."""


def _safe_rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _source_path(spec: SourceSpec, config_path: Path) -> Path:
    path = (config_path.parent / spec.source_path).resolve()
    try:
        path.relative_to(config_path.parent.resolve())
    except ValueError as exc:
        raise BuildError("source path escapes task directory") from exc
    if not path.is_file():
        raise BuildError(f"source module does not exist: {spec.source_path}")
    return path


def validate(task_dir: str | Path) -> tuple[SourceSpec, Path, Path]:
    """Read and validate task.toml, returning spec, config, source paths."""
    root = Path(task_dir).resolve()
    config = root / "task.toml"
    if not config.is_file():
        raise BuildError(f"missing task.toml in {root}")
    try:
        spec = SourceSpec.from_toml(config)
    except (OSError, ValueError, ContractError) as exc:
        raise BuildError(str(exc)) from exc
    source = _source_path(spec, config)
    return spec, config, source


def _snapshot(config: Path, source: Path, destination: Path) -> tuple[Path, Path]:
    """Copy exactly the source and tests that are to be validated/promoted."""
    snapshot_root = destination / "source"
    snapshot_root.mkdir()
    snapshot_source = snapshot_root / source.name
    shutil.copyfile(source, snapshot_source)
    tests_dir = config.parent / "tests"
    if not tests_dir.is_dir():
        raise BuildError("task source tests are required in tests/")
    shutil.copytree(tests_dir, snapshot_root / "tests")
    return snapshot_root, snapshot_source


def test(task_dir: str | Path, *, work_dir: str | Path | None = None,
         project: str | Path | None = None) -> None:
    """Compile a work-directory snapshot and run its stdlib unittest suite."""
    require_supported_runtime()
    _, config, source = validate(task_dir)
    project_config = resolve_project(project, work_dir=work_dir)
    work_root = project_config.work_dir
    work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="test-", dir=work_root) as temporary:
        snapshot_root, snapshot_source = _snapshot(config, source, Path(temporary))
        _check_snapshot(snapshot_root, snapshot_source)


def _check_snapshot(snapshot_root: Path, snapshot_source: Path) -> None:
    if not compileall.compile_file(snapshot_source, quiet=1, force=True):
        raise BuildError("task source does not compile")
    before_test_bytes = snapshot_source.read_bytes()
    _run_source_tests(snapshot_root)
    if snapshot_source.read_bytes() != before_test_bytes:
        raise BuildError("task source tests mutated the build snapshot")


def _run_source_tests(snapshot_root: Path) -> None:
    script = (
        "import sys,unittest\n"
        "suite=unittest.defaultTestLoader.discover('tests')\n"
        "if not suite.countTestCases(): raise SystemExit(3)\n"
        "raise SystemExit(not unittest.TextTestRunner().run(suite).wasSuccessful())\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script], cwd=snapshot_root,
        env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
        text=True, capture_output=True, check=False,
    )
    if completed.returncode == 3:
        raise BuildError("task source tests must contain at least one test")
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise BuildError(f"task source tests failed: {detail}")


def _run(command: list[str], *, cwd: Path) -> None:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise BuildError(detail or f"build command failed: {command[0]}")


def _smoke(staging: Path) -> None:
    """Import solely from staged payload and verify its bare export is callable."""
    script = (
        "import importlib.util,json,pathlib,sys\n"
        "root=pathlib.Path(sys.argv[1]); m=json.loads((root/'manifest.json').read_text())\n"
        "p=root/m['artifact_name']; s=importlib.util.spec_from_file_location(m['module_leaf'],p)\n"
        "if s is None or s.loader is None: raise RuntimeError('cannot load artifact')\n"
        "mod=importlib.util.module_from_spec(s); sys.modules[m['module_leaf']]=mod; s.loader.exec_module(mod)\n"
        "fn=getattr(mod,m['export'])\n"
        "if not callable(fn): raise RuntimeError('export is not callable')\n"
        "from prefect import Task\n"
        "if isinstance(fn, Task): raise RuntimeError('export is already a Prefect Task')\n"
    )
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run([sys.executable, "-I", "-c", script, str(staging.resolve())], cwd=staging,
                               env=env, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise BuildError(f"artifact smoke failed: {completed.stderr.strip() or completed.stdout.strip()}")


def _manifest(spec: SourceSpec, leaf: str, artifact_name: str, artifact: Path,
              source_hash: str, build: dict[str, str]) -> Manifest:
    return Manifest(
        schema=1, task_id=spec.task_id, version=spec.version, backend=spec.backend,
        module_leaf=leaf, export=spec.export, artifact_name=artifact_name,
        artifact_sha256=sha256_file(artifact), artifact_size=artifact.stat().st_size,
        source_digest=source_hash, python_cache_tag=sys.implementation.cache_tag,
        platform=sysconfig.get_platform(), ext_suffix=(importlib.machinery.EXTENSION_SUFFIXES[0] if spec.backend == "cython" else None),
        dependencies=spec.dependencies, build=build, description=spec.description,
        inputs=spec.inputs, output=spec.output,
    )


def _build_python(source: Path, staging: Path, leaf: str) -> Path:
    target = staging / f"{leaf}.py"
    shutil.copyfile(source, target)
    return target


def _build_cython(source: Path, staging: Path, leaf: str) -> Path:
    setup = staging / "setup.py"
    setup.write_text(
        "from setuptools import Extension, setup\n"
        "from Cython.Build import cythonize\n"
        f"setup(ext_modules=cythonize([Extension({leaf!r}, [{str(source)!r}])], language_level=3))\n",
        encoding="utf-8",
    )
    _run([sys.executable, str(setup), "build_ext", "--inplace"], cwd=staging)
    suffix = importlib.machinery.EXTENSION_SUFFIXES[0]
    artifact = staging / f"{leaf}{suffix}"
    if not artifact.is_file():
        raise BuildError("Cython build did not create the expected extension artifact")
    setup.unlink(missing_ok=True)
    (staging / (source.stem + ".c")).unlink(missing_ok=True)
    _safe_rmtree(staging / "build")
    return artifact

def build(task_dir: str | Path, *, store=None, work_dir: str | Path | None = None,
          project: str | Path | None = None):
    """Run the promotion lifecycle and atomically publish a verified artifact."""
    require_supported_runtime()
    spec, config, source = validate(task_dir)
    project_config = resolve_project(project, work_dir=work_dir)
    publisher = store if store is not None else LocalStore(project_config.store_path)
    work_root = project_config.work_dir
    work_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="build-", dir=work_root))
    try:
        snapshot_root, snapshot_source = _snapshot(config, source, staging)
        _check_snapshot(snapshot_root, snapshot_source)
        source_hash = source_digest(snapshot_source.read_bytes(), spec.to_mapping())
        leaf = module_leaf(spec.task_id, spec.version, source_hash)
        if spec.backend == "python":
            artifact = _build_python(snapshot_source, staging, leaf)
            build_facts = {"backend": "python"}
        elif spec.backend == "cython":
            artifact = _build_cython(snapshot_source, staging, leaf)
            build_facts = {"backend": "cython", "python": sys.version}
        else:
            raise BuildError(f"unsupported backend: {spec.backend}")
        _safe_rmtree(snapshot_root)
        manifest = _manifest(spec, leaf, artifact.name, artifact, source_hash, build_facts)
        (staging / "manifest.json").write_bytes(manifest.to_json_bytes())
        _smoke(staging)
        _safe_rmtree(staging / "__pycache__")
        return publisher.publish(staging)
    finally:
        _safe_rmtree(staging)
