"""Validate and execute an editor graph through the normal Weavem runtime.

This module deliberately keeps browser/editor data separate from executable code:
all task selections are checked against the freshly-read project bindings before a
payload is imported or invoked.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import keyword
import math
from pathlib import Path
from typing import Any, Callable, Mapping

from .bindings import binding_store, manifest_digest, read_bindings
from .config import resolve_project
from .contracts import ContractError, Manifest, SourceSpec
from .editor_hints import metadata_parameter_hint, source_parameter_hint
from .project import Project
from .runtime import validate_artifact

MAX_NODES = 200
MAX_EDGES = 1_000
MAX_PREVIEW = 4_096


class EditorGraphError(ValueError):
    """An editor graph cannot be safely resolved or executed."""


@dataclass(frozen=True)
class GraphNode:
    id: str
    task_key: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class GraphEdge:
    id: str
    source: str
    target: str
    argument: str
    source_path: tuple[str | int, ...] = ()


@dataclass(frozen=True)
class GraphPlan:
    name: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    order: tuple[str, ...]
    aliases: Mapping[str, str]


def _error(message: str) -> EditorGraphError:
    return EditorGraphError(f"editor graph: {message}")


def _project_config(project: Project | str | Path):
    if isinstance(project, Project):
        # Project intentionally exposes metadata, rather than its selection
        # internals. Resolve the freshly reported root to get current bindings.
        return resolve_project(project.metadata()["project"]["root"])
    return resolve_project(project)


def _json_value(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool)):
        return True
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_value(item) for key, item in value.items())
    return False


def _argument(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or not value.isidentifier() or keyword.iskeyword(value):
        raise _error(f"{field} must be a non-reserved Python keyword argument name")
    if value.startswith("__") and value.endswith("__"):
        raise _error(f"{field} must not be a reserved dunder argument name")
    # Prefect consumes these in Task.__call__ rather than passing them to the
    # export. In particular return_state=True would hide a failed task result.
    if value in {"return_state", "wait_for"}:
        raise _error(f"{field} uses the reserved Prefect argument {value!r}")
    return value


def _task_key_for_local(task_toml: Path) -> str:
    return f"local:{task_toml.resolve()}"


def _task_key_for_release(root: Path, digest: str) -> str:
    return f"released:{root.resolve()}:{digest}"


def editor_catalog(project: Project | str | Path) -> dict[str, Any]:
    """Return the fresh metadata snapshot plus the task keys executable by it.

    ``bindings`` only contains explicit bindings. Discovered authored tasks are
    intentionally absent until a project author binds them in ``weavem.toml``.
    """
    active = project if isinstance(project, Project) else Project.open(project)
    metadata = active.metadata()
    config = _project_config(active)
    bindings: dict[str, str] = {}
    hints: dict[str, Any] = {}
    # Metadata is the existing, read-only project inspection surface.  Editor
    # hints are deliberately derived here rather than added to Project.metadata.
    for entry in metadata["tasks"]:
        task_toml = Path(entry["path"])
        try:
            spec = SourceSpec.from_toml(task_toml)
            key = _task_key_for_local(task_toml)
            hint = source_parameter_hint(task_toml, spec, spec.inputs) or metadata_parameter_hint(spec.inputs)
            if hint is not None:
                hints[key] = hint
        except (ContractError, OSError, ValueError):
            # Catalog availability must not depend on optional editor advice.
            continue
    for alias, binding in read_bindings(config).items():
        if binding.path is not None:
            bindings[_task_key_for_local(binding.path / "task.toml")] = alias
            continue
        assert binding.release is not None and binding.manifest_sha256 is not None
        task_id, version = binding.release.split("==", 1)
        ref = binding_store(config, binding).resolve(task_id, version)
        # The key includes the current resolved location and canonical pin, so a
        # browser cannot swap a released artifact after importing metadata.
        digest = manifest_digest(ref.manifest_path)
        key = _task_key_for_release(ref.root, digest)
        bindings[key] = alias
        # Released/native tasks are never reverse engineered.  Their existing
        # descriptive metadata can still provide conservative JSON fields.
        try:
            published = Manifest.from_json_bytes(ref.manifest_path.read_bytes())
            hint = metadata_parameter_hint(published.inputs)
            if hint is not None:
                hints[key] = hint
        except (ContractError, OSError, ValueError):
            pass
    return {"metadata": metadata, "bindings": bindings, "parameterHints": hints}


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error(f"{field} must be an object")
    return value


def validate_graph(spec: Any, project: Project | str | Path) -> GraphPlan:
    """Validate graph structure and current task pins without importing payloads."""
    root = _mapping(spec, "graph")
    if root.get("kind") != "weavem.graph" or type(root.get("schema")) is not int or root["schema"] not in {1, 2}:
        raise _error("requires kind 'weavem.graph' and schema 1 or 2")
    schema = root["schema"]
    name = root.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise _error("name must be a non-empty string no longer than 200 characters")
    raw_nodes = root.get("nodes")
    raw_edges = root.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise _error("nodes and edges must be arrays")
    if not raw_nodes:
        raise _error("requires at least one node")
    if len(raw_nodes) > MAX_NODES or len(raw_edges) > MAX_EDGES:
        raise _error(f"exceeds limits of {MAX_NODES} nodes or {MAX_EDGES} edges")

    catalog = editor_catalog(project)
    aliases: Mapping[str, str] = catalog["bindings"]
    nodes: list[GraphNode] = []
    node_ids: set[str] = set()
    for index, raw in enumerate(raw_nodes):
        item = _mapping(raw, f"nodes[{index}]")
        node_id = item.get("id")
        task_key = item.get("taskKey")
        parameters = item.get("parameters", {})
        if not isinstance(node_id, str) or not node_id or len(node_id) > 200:
            raise _error(f"nodes[{index}].id must be a non-empty string")
        if node_id in node_ids:
            raise _error(f"duplicate node id: {node_id}")
        if not isinstance(task_key, str) or task_key not in aliases:
            raise _error(f"nodes[{index}] selects a task that is not currently bound by the project")
        if not isinstance(parameters, dict) or not _json_value(parameters):
            raise _error(f"nodes[{index}].parameters must be a strict JSON object")
        for argument in parameters:
            _argument(argument, f"nodes[{index}].parameters key")
        node_ids.add(node_id)
        nodes.append(GraphNode(node_id, task_key, dict(parameters)))

    edges: list[GraphEdge] = []
    edge_ids: set[str] = set()
    incoming: dict[str, set[str]] = {node.id: set() for node in nodes}
    outgoing: dict[str, list[str]] = {node.id: [] for node in nodes}
    indegree: dict[str, int] = {node.id: 0 for node in nodes}
    for index, raw in enumerate(raw_edges):
        item = _mapping(raw, f"edges[{index}]")
        edge_id, source, target = item.get("id"), item.get("source"), item.get("target")
        if not isinstance(edge_id, str) or not edge_id or edge_id in edge_ids:
            raise _error(f"edges[{index}].id must be unique and non-empty")
        if (not isinstance(source, str) or source not in node_ids
                or not isinstance(target, str) or target not in node_ids):
            raise _error(f"edges[{index}] references an unknown node")
        if source == target:
            raise _error(f"edges[{index}] cannot connect a node to itself")
        argument = _argument(item.get("argument"), f"edges[{index}].argument")
        raw_path = item.get("sourcePath", [])
        if not isinstance(raw_path, list) or any(
                not isinstance(part, str) and (type(part) is not int or part < 0) for part in raw_path):
            raise _error(f"edges[{index}].sourcePath must be an array of string keys or non-negative indexes")
        if raw_path and schema < 2:
            raise _error(f"edges[{index}].sourcePath requires schema 2")
        source_path = tuple(raw_path)
        if argument in incoming[target]:
            raise _error(f"multiple edges assign {argument!r} on node {target}")
        target_node = next(node for node in nodes if node.id == target)
        if argument in target_node.parameters:
            raise _error(f"edge argument {argument!r} conflicts with literal parameters on node {target}")
        edge_ids.add(edge_id)
        incoming[target].add(argument)
        outgoing[source].append(target)
        indegree[target] += 1
        edges.append(GraphEdge(edge_id, source, target, argument, source_path))

    # Stable Kahn sort keeps execution deterministic when multiple nodes are ready.
    ready = deque(node.id for node in nodes if indegree[node.id] == 0)
    order: list[str] = []
    while ready:
        current = ready.popleft()
        order.append(current)
        for target in outgoing[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    if len(order) != len(nodes):
        raise _error("contains a cycle")

    # Validate all released artifact pins before code import/invocation. Local
    # bindings intentionally only validate their metadata/path at this stage.
    config = _project_config(project)
    known = read_bindings(config)
    for task_key in sorted(set(node.task_key for node in nodes)):
        alias = aliases[task_key]
        binding = known[alias]
        if binding.release is None:
            continue
        task_id, version = binding.release.split("==", 1)
        ref = binding_store(config, binding).resolve(task_id, version)
        digest = manifest_digest(ref.manifest_path)
        if task_key != _task_key_for_release(ref.root, digest):
            raise _error(f"released task pin changed for binding {alias}")
        if digest != binding.manifest_sha256:
            raise _error(f"released task pin changed for binding {alias}")
        validate_artifact(ref, requested_task_id=task_id, requested_version=version)

    return GraphPlan(name.strip(), tuple(nodes), tuple(edges), tuple(order), dict(aliases))


def _preview(value: Any) -> str:
    try:
        preview = repr(value)
    except BaseException:
        preview = "<unprintable result>"
    return preview[:MAX_PREVIEW]


def _error_text(error: BaseException) -> str:
    try:
        text = f"{type(error).__name__}: {error}"
    except BaseException:
        text = type(error).__name__
    return text[:MAX_PREVIEW]


def execute_graph(spec: Any, project: Project | str | Path,
                  emit: Callable[[dict[str, str]], None]) -> dict[str, Any]:
    """Run a validated graph once using normal Prefect task invocation.

    Results live only in this process so arbitrary Python objects can pass along
    edges; event payloads expose bounded repr previews, never the object itself.
    Raises on preflight or task failure after emitting a terminal run event.
    """
    completed: set[str] = set()
    running: str | None = None
    try:
        plan = validate_graph(spec, project)
        by_id = {node.id: node for node in plan.nodes}
        inputs: dict[str, list[GraphEdge]] = {node.id: [] for node in plan.nodes}
        for edge in plan.edges:
            inputs[edge.target].append(edge)
        config = _project_config(project)
        from . import flow, task

        def run():
            nonlocal running
            results: dict[str, Any] = {}
            for node_id in plan.order:
                node = by_id[node_id]
                arguments = dict(node.parameters)
                for edge in inputs[node_id]:
                    value = results[edge.source]
                    for part in edge.source_path:
                        value = value[part]
                    arguments[edge.argument] = value
                running = node_id
                emit({"type": "node", "nodeId": node_id, "status": "running"})
                try:
                    selected = task(plan.aliases[node.task_key], project=config.root,
                                    persist_result=False, retries=0)
                    result = selected(**arguments)
                except BaseException as exc:
                    emit({"type": "node", "nodeId": node_id, "status": "failed", "error": _error_text(exc)})
                    raise
                results[node_id] = result
                completed.add(node_id)
                emit({"type": "node", "nodeId": node_id, "status": "completed", "preview": _preview(result)})
                running = None
            return results

        # Graph names are user-facing draft labels and may contain filesystem
        # separators or punctuation that Prefect rejects as run names.
        result = flow(name="weavem-editor", persist_result=False, retries=0)(run)()
    except BaseException as exc:
        if 'plan' in locals():
            for node_id in plan.order:
                if node_id not in completed and node_id != running:
                    emit({"type": "node", "nodeId": node_id, "status": "skipped"})
        emit({"type": "run", "status": "failed", "error": _error_text(exc)})
        raise
    emit({"type": "run", "status": "completed"})
    return result
