"""Project-backed persistence for the local visual flow editor.

Editor flows are ordinary ``flows/<name>.py`` modules plus the normal Weavem
``.toml`` sidecar.  The graph is reconstructed from a deliberately small AST
subset; this module never imports authored flow code to inspect it.
"""
from __future__ import annotations

import ast
import base64
import fcntl
from contextlib import contextmanager
import hashlib
import json
import keyword
import os
from pathlib import Path
import re
import tempfile
from threading import RLock
import tomllib
from typing import Any

from .config import resolve_project
from .editor_graph import EditorGraphError, editor_catalog, validate_graph
from .flow_contracts import FlowSpec
from .contracts import _validate_identity

_MAX_SOURCE = 1_000_000
_MAX_LAYOUT = 1_000_000
_MAX_JOURNAL = 5_000_000
_write_lock = RLock()

_NODE_COMMENT = re.compile(r"^\s*#\s*weavem-node:\s*(.+?)\s*$")
_EDGE_COMMENT = re.compile(r"^\s*#\s*weavem-edges:\s*(.+?)\s*$")


class FlowPersistenceError(ValueError):
    """A flow cannot be safely inspected or saved by the editor."""


class FlowConflictError(FlowPersistenceError):
    """The on-disk flow changed since the editor loaded it."""


def _name(name: Any) -> str:
    if (not isinstance(name, str) or Path(name).name != name or not name.isidentifier()
            or keyword.iskeyword(name) or (name.startswith("__") and name.endswith("__"))):
        raise FlowPersistenceError("flow name must be a non-reserved Python identifier")
    try:
        _validate_identity(name, "0.1.0")
    except ValueError as exc:
        raise FlowPersistenceError(str(exc)) from exc
    return name


def _paths(project: str | Path | None, name: str) -> tuple[Any, Path, Path, Path]:
    config = resolve_project(project)
    root = config.root / "flows"
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise FlowPersistenceError("flows must be a regular project directory")
    # Reads must not create project state.  save_flow creates this directory only
    # after all path checks have passed.
    # Child lexical paths are bare names, so they cannot escape this root.
    return config, root / f"{name}.py", root / f"{name}.toml", root / f"{name}.layout.json"


def _regular(path: Path, *, required: bool = False) -> bool:
    if path.is_symlink():
        raise FlowPersistenceError(f"symlinked editor flow path is not allowed: {path.name}")
    if not path.exists():
        if required:
            raise FlowPersistenceError(f"missing flow file: {path.name}")
        return False
    if not path.is_file():
        raise FlowPersistenceError(f"flow path must be a regular file: {path.name}")
    return True


def _read(path: Path, maximum: int) -> bytes:
    _regular(path, required=True)
    if path.stat().st_size > maximum:
        raise FlowPersistenceError(f"flow file is too large: {path.name}")
    raw = path.read_bytes()
    if len(raw) > maximum:
        raise FlowPersistenceError(f"flow file is too large: {path.name}")
    return raw


def _revision(source: bytes, metadata: bytes, layout: bytes | None) -> str:
    digest = hashlib.sha256()
    for value in (source, metadata, layout):
        digest.update(b"missing" if value is None else b"present")
        if value is not None:
            digest.update(len(value).to_bytes(8, "big"))
            digest.update(value)
    return digest.hexdigest()


def _sidecar(metadata: bytes) -> FlowSpec:
    try:
        data = tomllib.loads(metadata.decode("utf-8"))
        return FlowSpec.from_mapping(data.get("flow", data))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError, ValueError) as exc:
        raise FlowPersistenceError(f"invalid flow metadata: {exc}") from exc


def _layout(path: Path) -> Any:
    if not _regular(path):
        return None
    try:
        return json.loads(_read(path, _MAX_LAYOUT))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FlowPersistenceError(f"invalid flow layout: {exc}") from exc


def _comments(raw: bytes) -> tuple[dict[int, str], dict[int, dict[str, str]]]:
    """Map assignment lines to stable IDs encoded in adjacent generated comments."""
    result: dict[int, str] = {}
    edge_result: dict[int, dict[str, str]] = {}
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise FlowPersistenceError("flow source must be UTF-8") from exc
    pending: str | None = None
    pending_edges: dict[str, str] | None = None
    for number, line in enumerate(lines, 1):
        edge_match = _EDGE_COMMENT.match(line)
        if edge_match:
            try:
                candidate = json.loads(edge_match.group(1))
            except json.JSONDecodeError as exc:
                raise FlowPersistenceError("invalid weavem edge comment") from exc
            if (not isinstance(candidate, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not v for k, v in candidate.items())):
                raise FlowPersistenceError("invalid weavem edge identifiers")
            pending_edges = candidate
            continue
        match = _NODE_COMMENT.match(line)
        if match:
            try:
                value = json.loads(match.group(1))
            except json.JSONDecodeError as exc:
                raise FlowPersistenceError("invalid weavem node comment") from exc
            if not isinstance(value, str) or not value:
                raise FlowPersistenceError("invalid weavem node identifier")
            pending = value
        elif line.strip() and not line.lstrip().startswith("#"):
            if pending is not None:
                result[number] = pending
                if pending_edges is not None:
                    edge_result[number] = pending_edges
                pending = None
                pending_edges = None
    return result, edge_result


def _literal(node: ast.AST) -> Any:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, MemoryError, RecursionError) as exc:
        raise FlowPersistenceError("only JSON literal parameters are visually editable") from exc
    # validate_graph is the central JSON value validator.
    return value


def _parse_source(raw: bytes, spec: FlowSpec, catalog: dict[str, Any]) -> dict[str, Any]:
    if len(raw) > _MAX_SOURCE:
        raise FlowPersistenceError("flow source is too large")
    try:
        tree = ast.parse(raw, filename=spec.source)
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise FlowPersistenceError(f"invalid Python flow source: {exc}") from exc
    aliases = set(spec.tasks)
    keys_by_alias = {alias: key for key, alias in catalog["bindings"].items()}
    if not aliases <= keys_by_alias.keys():
        raise FlowPersistenceError("flow task bindings are unavailable in this project")
    binding_vars: dict[str, str] = {}
    function: ast.FunctionDef | None = None
    imported = False
    for statement in tree.body:
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
            continue
        if isinstance(statement, ast.ImportFrom):
            if (statement.module == "weavem" and statement.level == 0
                    and [(item.name, item.asname) for item in statement.names] == [("flow", None), ("task", None)]
                    and not imported and not binding_vars and function is None):
                imported = True
                continue
            raise FlowPersistenceError("only 'from weavem import flow, task' is supported")
        if isinstance(statement, ast.Import):
            raise FlowPersistenceError("imports other than Weavem flow/task are not visually editable")
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
            target, value = statement.targets[0].id, statement.value
            if (isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "task"
                    and len(value.args) == 1 and not value.keywords and isinstance(value.args[0], ast.Constant)
                    and isinstance(value.args[0].value, str) and value.args[0].value in aliases):
                if (not imported or function is not None or target in {"flow", "task", spec.export}
                        or target in binding_vars or value.args[0].value in binding_vars.values()):
                    raise FlowPersistenceError("ambiguous or duplicate task binding in flow source")
                binding_vars[target] = value.args[0].value; continue
        if isinstance(statement, ast.FunctionDef) and statement.name == spec.export:
            if function is not None:
                raise FlowPersistenceError("multiple exported flow functions are not visually editable")
            function = statement; continue
        raise FlowPersistenceError("unsupported module-level Python in flow")
    if not imported or function is None or set(binding_vars.values()) != aliases:
        raise FlowPersistenceError("flow does not use the editor-supported task bindings")
    if len(function.decorator_list) != 1 or not isinstance(function.decorator_list[0], ast.Name) or function.decorator_list[0].id != "flow":
        raise FlowPersistenceError("flow must use bare @flow without options")
    if function.returns is not None or getattr(function, "type_params", []):
        raise FlowPersistenceError("annotated/generic flows are not visually editable yet")
    if (function.args.posonlyargs or function.args.args or function.args.kwonlyargs
            or function.args.vararg or function.args.kwarg or function.args.defaults or function.args.kw_defaults):
        raise FlowPersistenceError("parameterized flows are not visually editable yet")
    comments, edge_comments = _comments(raw)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    variable_ids: dict[str, str] = {}
    returns: ast.Return | None = None
    for position, statement in enumerate(function.body):
        if isinstance(statement, ast.Return):
            if returns is not None or position != len(function.body) - 1:
                raise FlowPersistenceError("flow must have exactly one final return")
            returns = statement; continue
        if (not isinstance(statement, ast.Assign) or len(statement.targets) != 1
                or not isinstance(statement.targets[0], ast.Name) or not isinstance(statement.value, ast.Call)):
            raise FlowPersistenceError("unsupported flow statement")
        call, variable = statement.value, statement.targets[0].id
        if variable in variable_ids or variable in binding_vars or not isinstance(call.func, ast.Name) or call.func.id not in binding_vars or call.args:
            raise FlowPersistenceError("task calls must use a task binding and keyword arguments")
        node_id = comments.get(statement.lineno, variable)
        if node_id in variable_ids.values():
            raise FlowPersistenceError("duplicate editor node identifier")
        parameters: dict[str, Any] = {}
        arguments_seen: set[str] = set()
        for item in call.keywords:
            if item.arg is None or item.arg in arguments_seen:
                raise FlowPersistenceError("expanded or duplicate keyword arguments are not visually editable")
            arguments_seen.add(item.arg)
            if isinstance(item.value, ast.Name) and item.value.id in variable_ids:
                edges.append({"id": edge_comments.get(statement.lineno, {}).get(item.arg, f"edge-{len(edges) + 1}"),
                              "source": variable_ids[item.value.id], "target": node_id, "argument": item.arg})
            else:
                parameters[item.arg] = _literal(item.value)
        variable_ids[variable] = node_id
        nodes.append({"id": node_id, "taskKey": keys_by_alias[binding_vars[call.func.id]], "parameters": parameters})
    if returns is None or not nodes or not isinstance(returns.value, ast.Dict):
        raise FlowPersistenceError("flow must contain tasks and return a dictionary of terminal results")
    returned: set[str] = set()
    for key, value in zip(returns.value.keys, returns.value.values):
        if (not isinstance(key, ast.Constant) or not isinstance(key.value, str) or not isinstance(value, ast.Name)
                or value.id not in variable_ids or variable_ids[value.id] != key.value or key.value in returned):
            raise FlowPersistenceError("terminal results must use unique editor node IDs")
        returned.add(key.value)
    outgoing = {node["id"]: 0 for node in nodes}
    for edge in edges: outgoing[edge["source"]] += 1
    terminals = [node_id for node_id, count in outgoing.items() if count == 0]
    if returned != set(terminals) or [key.value for key in returns.value.keys] != terminals:
        raise FlowPersistenceError("return must contain terminal node results in authored task order")
    graph = {"kind": "weavem.graph", "schema": 1, "name": spec.source[:-3], "nodes": nodes, "edges": edges}
    try:
        validate_graph(graph, resolve_project_root(catalog))
    except EditorGraphError as exc:
        raise FlowPersistenceError(str(exc)) from exc
    return graph

def resolve_project_root(catalog: dict[str, Any]) -> str:
    return catalog["metadata"]["project"]["root"]


def _generated_source(name: str, graph: dict[str, Any], aliases: dict[str, str], order: tuple[str, ...]) -> bytes:
    nodes_by_id = {node["id"]: node for node in graph["nodes"]}
    incoming: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in nodes_by_id}
    outgoing: dict[str, int] = {node_id: 0 for node_id in nodes_by_id}
    for edge in graph["edges"]:
        incoming[edge["target"]].append(edge); outgoing[edge["source"]] += 1
    variables = {node_id: f"_weavem_node_{index + 1}" for index, node_id in enumerate(order)}
    task_aliases: list[str] = []
    for node in graph["nodes"]:
        alias = aliases[node["taskKey"]]
        if alias not in task_aliases: task_aliases.append(alias)
    binding_vars = {alias: f"_weavem_task_{index + 1}" for index, alias in enumerate(task_aliases)}
    lines = [f'"""{name} flow authored with Weavem."""', "from weavem import flow, task", ""]
    for alias in task_aliases:
        lines.append(f'{binding_vars[alias]} = task({alias!r})')
    lines.extend(["", "", "@flow", f"def {name}():"])
    for node_id in order:
        node = nodes_by_id[node_id]
        arguments = dict(node.get("parameters", {}))
        for edge in incoming[node_id]: arguments[edge["argument"]] = ("__result__", edge["source"])
        rendered = []
        for argument, value in arguments.items():
            rendered.append(f"{argument}={variables[value[1]]}" if isinstance(value, tuple) else f"{argument}={value!r}")
        source_edges = {edge["argument"]: edge["id"] for edge in incoming[node_id]}
        if source_edges:
            lines.append(f"    # weavem-edges: {json.dumps(source_edges, sort_keys=True, ensure_ascii=False)}")
        lines.append(f"    # weavem-node: {json.dumps(node_id, ensure_ascii=False)}")
        lines.append(f"    {variables[node_id]} = {binding_vars[aliases[node['taskKey']]]}({', '.join(rendered)})")
    terminals = [node_id for node_id in order if outgoing[node_id] == 0]
    rendered_return = ", ".join(f"{node_id!r}: {variables[node_id]}" for node_id in terminals)
    lines.extend([f"    return {{{rendered_return}}}", ""])
    return "\n".join(lines).encode("utf-8")

def _metadata(name: str, task_aliases: list[str], old: bytes | None) -> bytes:
    if old is not None:
        spec = _sidecar(old)
        if spec.source != f"{name}.py" or spec.export != name:
            raise FlowPersistenceError("editor flow metadata source/export must match its flow name")
        flow_id, version = spec.flow_id, spec.version
    else:
        flow_id, version = name, "0.1.0"
    # JSON strings use TOML-compatible basic-string escapes; Python repr would
    # silently change aliases containing newlines/backslashes in literal TOML.
    aliases = list(dict.fromkeys(task_aliases))
    text = "[flow]\nschema = 1\n"
    for key, value in (("flow_id", flow_id), ("version", version), ("source", name + ".py"), ("export", name)):
        text += f"{key} = {json.dumps(value)}\n"
    text += f"tasks = {json.dumps(aliases)}\n"
    return text.encode()


@contextmanager
def _process_lock(root: Path):
    # The supported platform is Linux. Lock the directory inode itself so
    # inspection does not create a persistent lock file in the user's project.
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _fsync_directory(root: Path) -> None:
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _identity(value: bytes | None) -> str | None:
    return None if value is None else hashlib.sha256(value).hexdigest()


def _snapshot(paths: list[Path]) -> list[bytes | None]:
    return [_read(path, _MAX_LAYOUT if path.name.endswith('.layout.json') else _MAX_SOURCE)
            if _regular(path) else None for path in paths]


def _stage(path: Path, content: bytes) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _recover_journal(journal: Path, paths: list[Path]) -> None:
    if not _regular(journal):
        return
    try:
        data = json.loads(_read(journal, _MAX_JOURNAL))
        if (not isinstance(data, dict) or data.get("names") != [path.name for path in paths]
                or not isinstance(data.get("old"), list) or not isinstance(data.get("new"), list)
                or len(data["old"]) != len(paths) or len(data["new"]) != len(paths)):
            raise ValueError("unexpected transaction shape")
        old = [None if value is None else base64.b64decode(value, validate=True) for value in data["old"]]
        new = data["new"]
        if any(value is not None and (not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)) for value in new):
            raise ValueError("invalid transaction identity")
        if any(value is not None and len(value) > _MAX_SOURCE for value in old):
            raise ValueError("oversized transaction preimage")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise FlowPersistenceError("invalid editor recovery journal; original files preserved") from exc
    current = _snapshot(paths)
    identities = [_identity(value) for value in current]
    if current != old and identities != new:
        if any(value != before and identity != after
               for value, before, identity, after in zip(current, old, identities, new)):
            raise FlowConflictError("foreign flow changes conflict with pending editor recovery; files preserved")
        # A partial commit contains only known before/after versions. Revert
        # those files, never a later independent edit. The journal survives any
        # interrupted recovery so this operation is repeatable.
        for path, value in zip(paths, old):
            if value is None:
                path.unlink(missing_ok=True)
            else:
                temporary = _stage(path, value)
                try:
                    os.replace(temporary, path)
                finally:
                    temporary.unlink(missing_ok=True)
        _fsync_directory(journal.parent)
    journal.unlink()
    _fsync_directory(journal.parent)


def _atomic_write(files: list[tuple[Path, bytes | None]], expected: list[bytes | None]) -> None:
    """Commit under the directory lock; retain a recoverable journal on failure.

    Cooperating Weavem writers are serialized. External editors do not honor
    that lock, so compare bytes again immediately before replacing files rather
    than promising a filesystem-wide compare-and-swap transaction.
    """
    paths = [path for path, _ in files]
    journal = paths[0].parent / f".weavem-editor-{paths[0].stem}.journal"
    staged: list[tuple[Path, Path | None]] = []
    journal_temporary = None
    journal_written = False
    try:
        for path, content in files:
            if content is not None and len(content) > _MAX_SOURCE:
                raise FlowPersistenceError(f"flow file is too large: {path.name}")
            staged.append((path, _stage(path, content) if content is not None else None))
        if _snapshot(paths) != expected:
            raise FlowConflictError("flow changed while preparing save")
        record = {"names": [path.name for path in paths],
                  "old": [None if value is None else base64.b64encode(value).decode("ascii") for value in expected],
                  "new": [_identity(content) for _, content in files]}
        journal_temporary = _stage(journal, json.dumps(record, separators=(",", ":")).encode("utf-8"))
        os.replace(journal_temporary, journal)
        journal_written = True
        _fsync_directory(journal.parent)
        if _snapshot(paths) != expected:
            # No destination has been touched. Drop only our journal, retaining
            # the external edit rather than attempting rollback over it.
            journal.unlink()
            journal_written = False
            _fsync_directory(journal.parent)
            raise FlowConflictError("flow changed immediately before saving")
        for path, temporary in staged:
            if temporary is None:
                path.unlink(missing_ok=True)
            else:
                os.replace(temporary, path)
        _fsync_directory(journal.parent)
        journal.unlink()
        journal_written = False
        _fsync_directory(journal.parent)
    except BaseException:
        if journal_written:
            try:
                _recover_journal(journal, paths)
            except (OSError, ValueError) as recovery_error:
                raise FlowPersistenceError(
                    f"save interrupted; recovery journal retained at {journal.name}: {recovery_error}"
                ) from recovery_error
        raise
    finally:
        for _, temporary in staged:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        if journal_temporary is not None:
            journal_temporary.unlink(missing_ok=True)

def list_flows(project: str | Path | None = None) -> list[dict[str, Any]]:
    config = resolve_project(project); root = config.root / "flows"
    if root.is_symlink(): raise FlowPersistenceError("flows must be a regular project directory")
    if not root.exists(): return []
    catalog = editor_catalog(config.root)
    result = []
    for metadata in sorted(root.glob("*.toml")):
        name = metadata.stem
        try:
            item = open_flow(name, config.root, _catalog=catalog)
            result.append({key: item[key] for key in ("name", "revision", "editable", "reason")})
        except FlowPersistenceError as exc:
            result.append({"name": name, "revision": None, "editable": False, "reason": str(exc)})
    return result


def open_flow(name: str, project: str | Path | None = None, *, _catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    name = _name(name)
    config, source_path, metadata_path, layout_path = _paths(project, name)
    if not source_path.parent.exists():
        raise FlowPersistenceError(f"missing flow: {name}")
    with _write_lock, _process_lock(source_path.parent):
        _recover_journal(source_path.parent / f".weavem-editor-{name}.journal",
                         [source_path, metadata_path, layout_path])
        return _open_flow_locked(name, config.root, _catalog=_catalog)


def _open_flow_locked(name: str, project, *, _catalog=None) -> dict[str, Any]:
    config, source_path, metadata_path, layout_path = _paths(project, name)
    metadata = _read(metadata_path, _MAX_SOURCE)
    spec = _sidecar(metadata)
    source_path = source_path.parent / spec.source
    source = _read(source_path, _MAX_SOURCE)
    layout_raw = _read(layout_path, _MAX_LAYOUT) if _regular(layout_path) else None
    layout_error = None
    try:
        layout = json.loads(layout_raw) if layout_raw is not None else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        layout, layout_error = None, "Invalid optional flow layout; using automatic positions"
    revision = _revision(source, metadata, layout_raw)
    common = {"name": name, "revision": revision,
              "sourceSha256": hashlib.sha256(source).hexdigest(),
              "metadataSha256": hashlib.sha256(metadata).hexdigest(),
              "layout": layout, "layoutError": layout_error,
              "source": source.decode("utf-8", errors="replace")}
    try:
        if spec.source != f"{name}.py" or spec.export != name:
            raise FlowPersistenceError("source/export differs from the flow filename; visual rewriting is unavailable")
        graph = _parse_source(source, spec, _catalog or editor_catalog(config.root))
        return {**common, "editable": True, "reason": None, "graph": graph}
    except FlowPersistenceError as exc:
        return {**common, "editable": False, "reason": str(exc), "graph": None}


def save_flow(name: str, graph: Any, layout: Any, expected_revision: str | None,
              project: str | Path | None = None) -> dict[str, Any]:
    with _write_lock:
        return _save_flow_locked(name, graph, layout, expected_revision, project)


def _save_flow_locked(name: str, graph: Any, layout: Any, expected_revision: str | None,
                      project: str | Path | None = None) -> dict[str, Any]:
    name = _name(name); config, source_path, metadata_path, layout_path = _paths(project, name)
    # A newly authored flow is the only write path that may create flows/.
    source_path.parent.mkdir(parents=True, exist_ok=True)
    with _process_lock(source_path.parent):
        _recover_journal(source_path.parent / f".weavem-editor-{name}.journal", [source_path, metadata_path, layout_path])
        return _save_flow_under_process_lock(name, graph, layout, expected_revision, config, source_path, metadata_path, layout_path)


def _save_flow_under_process_lock(name, graph, layout, expected_revision, config, source_path, metadata_path, layout_path):
    source_exists, metadata_exists = _regular(source_path), _regular(metadata_path)
    if source_exists != metadata_exists:
        raise FlowPersistenceError("flow source and metadata must either both exist or both be new")
    old_source = _read(source_path, _MAX_SOURCE) if source_exists else None
    old_metadata = _read(metadata_path, _MAX_SOURCE) if metadata_exists else None
    old_layout = _read(layout_path, _MAX_LAYOUT) if _regular(layout_path) else None
    current = _revision(old_source, old_metadata, old_layout) if old_source is not None else None
    if expected_revision != current:
        if current is None and expected_revision is not None:
            raise FlowConflictError("new flow must be saved with no expected revision")
        raise FlowConflictError("flow changed on disk; reload before saving")
    plan = validate_graph(graph, config.root)
    if plan.name != name:
        raise FlowPersistenceError("graph name must match flow name")
    aliases = {key: alias for key, alias in plan.aliases.items()}
    original_order = tuple(node["id"] for node in graph["nodes"])
    positions = {node_id: index for index, node_id in enumerate(original_order)}
    # Preserve the authored statement order whenever it is already valid. A
    # fresh topological sort can move independent calls across dependent calls,
    # changing side effects when visually reopening handwritten source.
    order = (original_order if all(positions[edge["source"]] < positions[edge["target"]]
                                   for edge in graph["edges"]) else plan.order)
    generated = _generated_source(name, graph, aliases, order)
    generated_metadata = _metadata(name, [aliases[node["taskKey"]] for node in graph["nodes"]], old_metadata)
    _sidecar(generated_metadata)  # Refuse invalid definitions before committing any file.
    if layout is not None:
        try: layout_raw = json.dumps(layout, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc: raise FlowPersistenceError("layout must be JSON-compatible") from exc
        if len(layout_raw) > _MAX_LAYOUT: raise FlowPersistenceError("flow layout is too large")
    else:
        layout_raw = None
    # Existing non-editor code must never be overwritten just because it happens
    # to have valid metadata.
    if old_source is not None:
        current_view = _open_flow_locked(name, config.root)
        if not current_view["editable"]:
            raise FlowPersistenceError("refusing to overwrite unsupported handwritten Python")
    _atomic_write([(source_path, generated), (metadata_path, generated_metadata), (layout_path, layout_raw)], [old_source, old_metadata, old_layout])
    return _open_flow_locked(name, config.root)
