"""Stable, data-only contracts for Weavem task artifacts."""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import re
import platform as _platform
import sys
import sysconfig
import tomllib
from types import MappingProxyType
from typing import Any, Mapping

SCHEMA_VERSION = 1
_ID_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*\Z")
_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}\Z")
_LEAF_RE = re.compile(r"_weavem_[A-Za-z0-9_]+\Z")
_DEP_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*==[^\s;,@!<>=~\[\]]+\Z")


class ContractError(ValueError):
    """A source or manifest contract is malformed."""


class ManifestError(ContractError):
    """A manifest cannot be decoded or does not match its schema."""


class CompatibilityError(RuntimeError):
    """The current interpreter or installed dependencies cannot load an artifact."""


class IntegrityError(RuntimeError):
    """An artifact does not match its declared identity or digest."""


class PolicyError(PermissionError):
    """The configured task policy denied execution."""


class StoreError(RuntimeError):
    """A task store cannot resolve or safely publish an artifact."""


def _require_string(value: object, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ContractError(f"{name} must be a non-empty string")
    return value


def _safe_relative(value: object, name: str) -> str:
    value = _require_string(value, name)
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or len(path.parts) != 1 or value in {".", ".."}:
        raise ContractError(f"{name} must be a single safe relative filename")
    return value


def _validate_identity(task_id: object, version: object) -> tuple[str, str]:
    task_id = _require_string(task_id, "task_id")
    version = _require_string(version, "version")
    if len(task_id) > 128 or not _ID_RE.fullmatch(task_id) or not task_id.isascii():
        raise ContractError("task_id must be conservative ASCII identifier text")
    if not _VERSION_RE.fullmatch(version) or not version.isascii():
        raise ContractError("version must be an explicit ASCII version")
    return task_id, version


def _strings(value: object, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) or not item for item in value):
        raise ContractError(f"{name} must be an array of non-empty strings")
    return tuple(value)


def _dependencies(value: object) -> tuple[str, ...]:
    dependencies = _strings(value, "dependencies")
    for dependency in dependencies:
        if not dependency.isascii() or not _DEP_RE.fullmatch(dependency):
            raise ContractError("dependencies must use distribution==installed-version pins")
    return dependencies


def _frozen_mapping(value: object, name: str = "build") -> Mapping[str, str]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
        raise ContractError(f"{name} must be a string-to-string object")
    return MappingProxyType(dict(value))


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_digest(source: bytes, config: Mapping[str, Any]) -> str:
    """Return the canonical source/config digest used in a generated module leaf."""
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return sha256(b"weavem-source-v1\0" + canonical + b"\0" + source).hexdigest()


def module_leaf(task_id: str, version: str, digest: str) -> str:
    task_id, version = _validate_identity(task_id, version)
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ContractError("source_digest must be a SHA-256 hex digest")
    normalized = re.sub(r"[^A-Za-z0-9]", "_", f"{task_id}_{version}")
    leaf = f"_weavem_{normalized}_{digest[:16]}"
    if len(leaf) > 200 or not _LEAF_RE.fullmatch(leaf):  # defensive future-proofing
        raise ContractError("generated module leaf is unsafe")
    return leaf


@dataclass(frozen=True)
class SourceSpec:
    schema: int
    task_id: str
    version: str
    backend: str
    source_path: str
    export: str
    dependencies: tuple[str, ...] = ()
    description: str | None = None
    inputs: tuple[str, ...] = ()
    output: str = "Any"

    def __post_init__(self) -> None:
        if type(self.schema) is not int or self.schema != SCHEMA_VERSION:
            raise ContractError(f"unsupported source schema: {self.schema!r}")
        _validate_identity(self.task_id, self.version)
        if _require_string(self.backend, "backend") not in {"python", "cython"}:
            raise ContractError("backend must be 'python' or 'cython'")
        _safe_relative(self.source_path, "source_path")
        if not _require_string(self.export, "export").isidentifier():
            raise ContractError("export must be a safe Python identifier")
        _dependencies(self.dependencies)
        if self.description is not None and type(self.description) is not str:
            raise ContractError("description must be a string or null")
        _strings(self.inputs, "inputs")
        _require_string(self.output, "output")

    @classmethod
    def from_toml(cls, path: str | Path) -> "SourceSpec":
        try:
            data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ContractError(f"cannot read task TOML: {exc}") from exc
        section = data.get("task", data)
        if not isinstance(section, dict):
            raise ContractError("task TOML must contain a table")
        allowed = {"schema", "task_id", "version", "backend", "source", "source_path", "export", "dependencies", "description", "inputs", "output"}
        unknown = set(section) - allowed
        if unknown:
            raise ContractError(f"unknown task fields: {', '.join(sorted(unknown))}")
        return cls(
            schema=section.get("schema", SCHEMA_VERSION),
            task_id=section.get("task_id"),
            version=section.get("version"), backend=section.get("backend", "python"),
            source_path=section.get("source", section.get("source_path", "implementation.py")),
            export=section.get("export", "run"), dependencies=_dependencies(section.get("dependencies")),
            description=section.get("description"), inputs=_strings(section.get("inputs"), "inputs"), output=section.get("output", "Any"),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {"schema": self.schema, "task_id": self.task_id, "version": self.version, "backend": self.backend,
                "source": self.source_path, "export": self.export, "dependencies": list(self.dependencies),
                "description": self.description, "inputs": list(self.inputs), "output": self.output}


@dataclass(frozen=True)
class Manifest:
    schema: int
    task_id: str
    version: str
    backend: str
    module_leaf: str
    export: str
    artifact_name: str
    artifact_sha256: str
    artifact_size: int
    source_digest: str
    python_cache_tag: str
    platform: str
    ext_suffix: str | None
    dependencies: tuple[str, ...] = ()
    description: str | None = None
    inputs: tuple[str, ...] = ()
    output: str = "Any"
    build: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.schema) is not int or self.schema != SCHEMA_VERSION:
            raise ManifestError(f"unsupported manifest schema: {self.schema!r}")
        _validate_identity(self.task_id, self.version)
        if _require_string(self.backend, "backend") not in {"python", "cython"}:
            raise ManifestError("invalid backend")
        leaf = _require_string(self.module_leaf, "module_leaf")
        if len(leaf) > 200 or not _LEAF_RE.fullmatch(leaf):
            raise ManifestError("unsafe module_leaf")
        if not _require_string(self.export, "export").isidentifier():
            raise ManifestError("export must be a safe Python identifier")
        _safe_relative(self.artifact_name, "artifact_name")
        if self.backend == "python" and self.artifact_name != f"{self.module_leaf}.py":
            raise ManifestError("python artifact_name must exactly match module_leaf.py")
        if self.backend == "cython" and self.ext_suffix is not None and self.artifact_name != f"{self.module_leaf}{self.ext_suffix}":
            raise ManifestError("cython artifact_name must exactly match module_leaf plus ext_suffix")
        if not re.fullmatch(r"[0-9a-f]{64}", _require_string(self.artifact_sha256, "artifact_sha256")):
            raise ManifestError("artifact_sha256 must be SHA-256 hex")
        if type(self.artifact_size) is not int or self.artifact_size < 0:
            raise ManifestError("artifact_size must be a non-negative integer")
        if not re.fullmatch(r"[0-9a-f]{64}", _require_string(self.source_digest, "source_digest")):
            raise ManifestError("source_digest must be SHA-256 hex")
        cache_tag = _require_string(self.python_cache_tag, "python_cache_tag")
        if len(cache_tag) > 128 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", cache_tag):
            raise ManifestError("python_cache_tag must be a safe ASCII path component")
        _require_string(self.platform, "platform")
        if self.backend == "python" and self.ext_suffix is not None:
            raise ManifestError("python artifacts cannot declare ext_suffix")
        if self.backend == "cython" and not isinstance(self.ext_suffix, str):
            raise ManifestError("cython artifacts require ext_suffix")
        _dependencies(self.dependencies)
        if self.description is not None and not isinstance(self.description, str):
            raise ManifestError("description must be a string or null")
        _strings(self.inputs, "inputs")
        _require_string(self.output, "output")
        object.__setattr__(self, "build", _frozen_mapping(self.build))

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Manifest":
        if not isinstance(data, Mapping):
            raise ManifestError("manifest must be a JSON object")
        allowed = {"schema", "task_id", "version", "backend", "module_leaf", "export", "artifact_name", "artifact_sha256", "artifact_size", "source_digest", "python_cache_tag", "platform", "ext_suffix", "dependencies", "description", "inputs", "output", "build"}
        unknown = set(data) - allowed
        if unknown:
            raise ManifestError(f"unknown manifest fields: {', '.join(sorted(unknown))}")
        try:
            return cls(schema=data["schema"], task_id=data["task_id"], version=data["version"],
                       backend=data["backend"], module_leaf=data["module_leaf"], export=data["export"], artifact_name=data["artifact_name"],
                       artifact_sha256=data["artifact_sha256"], artifact_size=data["artifact_size"], source_digest=data["source_digest"],
                       python_cache_tag=data["python_cache_tag"], platform=data["platform"], ext_suffix=data.get("ext_suffix"),
                       dependencies=_dependencies(data.get("dependencies")), description=data.get("description"), inputs=_strings(data.get("inputs"), "inputs"),
                       output=data.get("output", "Any"), build=_frozen_mapping(data.get("build")))
        except KeyError as exc:
            raise ManifestError(f"missing manifest field: {exc.args[0]}") from exc
        except ContractError as exc:
            raise ManifestError(str(exc)) from exc

    @classmethod
    def from_json_bytes(cls, raw: bytes) -> "Manifest":
        def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ManifestError(f"duplicate JSON key: {key}")
                result[key] = value
            return result
        try:
            return cls.from_mapping(json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ManifestError(f"invalid manifest JSON: {exc}") from exc

    def to_mapping(self) -> dict[str, Any]:
        return {"schema": self.schema, "task_id": self.task_id, "version": self.version, "backend": self.backend,
                "module_leaf": self.module_leaf, "export": self.export, "artifact_name": self.artifact_name,
                "artifact_sha256": self.artifact_sha256, "artifact_size": self.artifact_size, "source_digest": self.source_digest,
                "python_cache_tag": self.python_cache_tag, "platform": self.platform, "ext_suffix": self.ext_suffix,
                "dependencies": list(self.dependencies), "description": self.description, "inputs": list(self.inputs), "output": self.output,
                "build": dict(self.build)}

    def to_json_bytes(self) -> bytes:
        return (json.dumps(self.to_mapping(), sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")



def require_supported_runtime() -> None:
    """Reject hosts outside the deliberately narrow local-MVP support lane."""
    if sys.implementation.name != "cpython" or not (3, 12) <= sys.version_info[:2] < (3, 15):
        raise CompatibilityError("Weavem requires standard CPython 3.12–3.14 (Prefect currently excludes 3.15)")
    if sys.platform != "linux" or _platform.machine().lower() not in {"x86_64", "amd64"}:
        raise CompatibilityError("Weavem local MVP requires Linux x86_64")

    if any(sysconfig.get_config_var(key) for key in ("Py_DEBUG", "Py_GIL_DISABLED", "Py_TRACE_REFS")):
        raise CompatibilityError("Weavem requires a standard GIL-enabled, non-debug CPython build")
    libc, version = _platform.libc_ver()
    if libc != "glibc" or tuple(int(x) for x in version.split(".")[:2]) < (2, 28):
        raise CompatibilityError("Weavem requires Linux x86_64 with glibc 2.28 or newer")
