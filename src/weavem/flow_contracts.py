"""Data-only source and release contracts for single-file flows."""
from __future__ import annotations

from dataclasses import dataclass
import json
import keyword
import re
from types import MappingProxyType
from typing import Any, Mapping

from .contracts import ContractError, ManifestError, _require_string, _safe_relative, _validate_identity

_HEX = re.compile(r"[0-9a-f]{64}\Z")


def _identifier(value: object, label: str) -> str:
    value = _require_string(value, label)
    if not value.isidentifier() or keyword.iskeyword(value):
        raise ContractError(f"{label} must be a Python identifier")
    return value


@dataclass(frozen=True)
class FlowSpec:
    schema: int
    flow_id: str
    version: str
    source: str
    export: str
    tasks: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.schema) is not int or self.schema != 1:
            raise ContractError("unsupported flow source schema")
        _validate_identity(self.flow_id, self.version)
        _safe_relative(self.source, "flow source")
        if not self.source.endswith(".py"):
            raise ContractError("flow source must be a Python filename")
        _identifier(self.source[:-3], "flow source module")
        _identifier(self.export, "flow export")
        if not isinstance(self.tasks, tuple) or any(not isinstance(x, str) or not x for x in self.tasks):
            raise ContractError("flow tasks must be an alias array")
        if len(set(self.tasks)) != len(self.tasks):
            raise ContractError("flow task aliases must be unique")

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> FlowSpec:
        allowed = {"schema", "flow_id", "version", "source", "export", "tasks"}
        if not isinstance(data, Mapping) or set(data) - allowed:
            raise ContractError("invalid or unknown flow source fields")
        tasks = data.get("tasks", [])
        if not isinstance(tasks, list):
            raise ContractError("flow tasks must be an array")
        return cls(data.get("schema", 1), data.get("flow_id"), data.get("version"),
                   data.get("source"), data.get("export"), tuple(tasks))

    def to_mapping(self) -> dict[str, Any]:
        return {"schema": self.schema, "flow_id": self.flow_id, "version": self.version,
                "source": self.source, "export": self.export, "tasks": list(self.tasks)}


@dataclass(frozen=True)
class FlowManifest:
    schema: int
    kind: str
    flow_id: str
    version: str
    module_leaf: str
    export: str
    artifact_name: str
    artifact_sha256: str
    artifact_size: int
    python_cache_tag: str
    platform: str
    task_dependencies: tuple[Mapping[str, str], ...]

    def __post_init__(self) -> None:
        try:
            self._validate()
        except ContractError as exc:
            raise ManifestError(str(exc)) from exc

    def _validate(self) -> None:
        if type(self.schema) is not int or self.schema != 1 or self.kind != "flow":
            raise ContractError("invalid flow manifest kind or schema")
        _validate_identity(self.flow_id, self.version)
        leaf = _identifier(self.module_leaf, "flow module_leaf")
        if len(leaf) > 200 or not leaf.isascii() or not leaf.startswith("_weavem_"):
            raise ContractError("unsafe flow module_leaf")
        _identifier(self.export, "flow export")
        if self.artifact_name != leaf + ".py":
            raise ContractError("flow artifact name must match module_leaf.py")
        if not isinstance(self.artifact_sha256, str) or not _HEX.fullmatch(self.artifact_sha256):
            raise ContractError("invalid flow payload digest")
        if type(self.artifact_size) is not int or self.artifact_size < 0:
            raise ContractError("invalid flow payload size")
        cache_tag = _require_string(self.python_cache_tag, "python_cache_tag")
        if len(cache_tag) > 128 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", cache_tag):
            raise ContractError("unsafe python_cache_tag")
        _require_string(self.platform, "platform")
        if not isinstance(self.task_dependencies, tuple):
            raise ContractError("flow task_dependencies must be an array")
        aliases = set()
        for dep in self.task_dependencies:
            if (not isinstance(dep, Mapping)
                    or set(dep) != {"alias", "task_id", "version", "manifest_sha256"}
                    or any(not isinstance(v, str) or not v for v in dep.values())):
                raise ContractError("invalid pinned flow task dependency")
            _validate_identity(dep["task_id"], dep["version"])
            if not _HEX.fullmatch(dep["manifest_sha256"]):
                raise ContractError("invalid flow task manifest digest")
            if dep["alias"] in aliases:
                raise ContractError("flow task aliases must be unique")
            aliases.add(dep["alias"])
        object.__setattr__(self, "task_dependencies", tuple(
            MappingProxyType(dict(dep)) for dep in self.task_dependencies))

    def to_mapping(self) -> dict[str, Any]:
        return {"schema": self.schema, "kind": self.kind, "flow_id": self.flow_id,
                "version": self.version, "module_leaf": self.module_leaf, "export": self.export,
                "artifact_name": self.artifact_name, "artifact_sha256": self.artifact_sha256,
                "artifact_size": self.artifact_size, "python_cache_tag": self.python_cache_tag,
                "platform": self.platform, "task_dependencies": [dict(x) for x in self.task_dependencies]}

    def to_json_bytes(self) -> bytes:
        return (json.dumps(self.to_mapping(), sort_keys=True, separators=(",", ":")) + "\n").encode()

    @classmethod
    def from_json_bytes(cls, raw: bytes) -> FlowManifest:
        def no_duplicates(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ManifestError(f"duplicate flow manifest field: {key}")
                result[key] = value
            return result
        try:
            data = json.loads(raw, object_pairs_hook=no_duplicates)
        except (UnicodeDecodeError, TypeError, ValueError) as exc:
            raise ManifestError(f"invalid flow manifest JSON: {exc}") from exc
        fields = set(cls.__dataclass_fields__)
        if not isinstance(data, dict) or set(data) != fields:
            raise ManifestError("invalid flow manifest fields")
        if not isinstance(data["task_dependencies"], list):
            raise ManifestError("flow task_dependencies must be an array")
        return cls(**(data | {"task_dependencies": tuple(data["task_dependencies"])}))
