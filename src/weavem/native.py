"""Managed, offline native compilation for supported CPython/Linux runtimes.

The compiler comes from the pinned ziglang wheel. Audited CPython headers are
shipped with Weavem, never guessed from a Python minor version or installed via
an OS package manager. Each build uses a private workspace and import probe.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import tempfile

from .contracts import require_supported_runtime


class NativeError(RuntimeError):
    pass


def _headers(work: Path) -> tuple[list[Path], str]:
    resources = Path(__file__).with_name("_native_headers")
    config = sysconfig.get_config_vars()
    for record_path in sorted(resources.glob("*.json")):
        record = json.loads(record_path.read_text())
        if (record["minor"] != list(sys.version_info[:2])
                or record["soabi"] != config.get("SOABI")
                or tuple(record["version"]) > sys.version_info[:3]
                or any(config.get(key) != value for key, value in record["config"].items())):
            continue
        archive = resources / record["archive"]
        if hashlib.sha256(archive.read_bytes()).hexdigest() != record["sha256"]:
            raise NativeError("Bundled Python headers failed integrity checking; reinstall Weavem.")
        destination = work / "headers"
        destination.mkdir()
        with tarfile.open(archive) as source:
            source.extractall(destination, filter="data")
        return [destination], record_path.stem
    # Python installations which already supply their own headers need no pack.
    include = Path(sysconfig.get_path("include"))
    platform_include = Path(sysconfig.get_path("platinclude"))
    if (include / "Python.h").is_file() and Path(sysconfig.get_config_h_filename()).is_file():
        return list(dict.fromkeys([include, platform_include])), "interpreter"
    raise NativeError(
        f"No verified native header bundle matches CPython {sys.version.split()[0]} "
        f"({config.get('SOABI')}). This Python distribution is not supported for native "
        "authoring without its own headers. Use a supported standard CPython distribution; "
        "Weavem will not install system packages or guess an ABI."
    )


def _run(command: list[str], work: Path, env: dict[str, str]) -> None:
    result = subprocess.run(command, cwd=work, env=env, text=True, capture_output=True)
    if result.returncode:
        raise NativeError(f"Managed native build failed: {result.stderr.strip() or result.stdout.strip()}")


def _environment(work: Path) -> dict[str, str]:
    env = dict(os.environ)
    # A caller's compiler/SDK configuration must not hijack the managed builder.
    for key in ("CC", "CXX", "CFLAGS", "CPPFLAGS", "LDFLAGS", "LDSHARED", "CPATH",
                "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "LIBRARY_PATH", "PYTHONPATH",
                "ZIG_LIB_DIR"):
        env.pop(key, None)
    env.update(ZIG_GLOBAL_CACHE_DIR=str(work / "zig-cache"),
               ZIG_LOCAL_CACHE_DIR=str(work / "zig-local"),
               TMPDIR=str(work), SOURCE_DATE_EPOCH="0", PYTHONHASHSEED="0")
    return env


def _compiler(work: Path, headers: list[Path]) -> list[str]:
    return [sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-linux-gnu.2.28",
            "-shared", "-fPIC", "-O2", "-g0", "-s", "-fno-ident",
            "-Wl,--build-id=none", f"-ffile-prefix-map={work}=/weavem-build",
            *[f"-I{path}" for path in headers]]


def _prepare(work: Path) -> tuple[list[str], dict[str, str], dict[str, str]]:
    require_supported_runtime()
    try:
        version = importlib.metadata.version("ziglang")
    except importlib.metadata.PackageNotFoundError as exc:
        raise NativeError("Managed compiler is missing; reinstall Weavem with its declared dependencies.") from exc
    if version != "0.17.0":
        raise NativeError(f"Expected managed ziglang 0.17.0, found {version}; reinstall Weavem.")
    headers, pack = _headers(work)
    env = _environment(work)
    compiler = _compiler(work, headers)
    # Test header/loader compatibility in a child before compiling author code.
    (work / "probe.c").write_text(
        '#include <Python.h>\n'
        'static struct PyModuleDef m={PyModuleDef_HEAD_INIT,"_weavem_native_probe",NULL,-1,NULL};\n'
        'PyMODINIT_FUNC PyInit__weavem_native_probe(void){return PyModule_Create(&m);}\n'
    )
    suffix = sysconfig.get_config_var("EXT_SUFFIX")
    probe = work / ("_weavem_native_probe" + suffix)
    _run([*compiler, "probe.c", "-o", probe.name], work, env)
    _run([sys.executable, "-I", "-c",
          "import importlib.util,sys; s=importlib.util.spec_from_file_location('_weavem_native_probe',sys.argv[1]); "
          "m=importlib.util.module_from_spec(s); s.loader.exec_module(m)", str(probe)], work, env)
    return compiler, env, {"compiler": "ziglang==0.17.0", "headers": pack,
                           "target": "x86_64-linux-gnu.2.28", "debug_symbols": "stripped"}


def check_native(work_root: Path) -> dict[str, str]:
    work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="native-check-", dir=work_root) as temporary:
        _, _, facts = _prepare(Path(temporary).resolve())
        return {"python": sys.version.split()[0], **facts}


def compile_native(source: Path, staging: Path, leaf: str) -> tuple[Path, dict[str, str]]:
    with tempfile.TemporaryDirectory(prefix="native-", dir=staging) as temporary:
        work = Path(temporary).resolve()
        compiler, env, facts = _prepare(work)
        local_source = work / source.name
        shutil.copyfile(source, local_source)
        generated = leaf + ".c"
        _run([sys.executable, "-m", "cython", "-3", "--module-name", leaf,
              local_source.name, "-o", generated], work, env)
        name = leaf + sysconfig.get_config_var("EXT_SUFFIX")
        _run([*compiler, generated, "-o", name], work, env)
        binary = (work / name).read_bytes()
        if any(str(path.resolve()).encode() in binary for path in (source.parent, staging, work)):
            raise NativeError("Native artifact contains an absolute build path; publication refused.")
        target = staging / name
        target.write_bytes(binary)
        return target, facts
