"""Isolated process entrypoint for one saved editor flow run.

The editor does not execute a browser graph.  It loads the exact ordinary flow
source that a terminal invocation would load, after checking its revision a
second time in this fresh process.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any, Callable

from .editor_values import safe_preview
from .errors import serialize_error


def _event_writer(path: Path) -> Callable[[dict[str, object]], None]:
    def emit(event: dict[str, object]) -> None:
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"), default=str)
        with path.open("a", encoding="utf-8") as events:
            events.write(line + "\n")
            events.flush()
    return emit


def _preview(value: object) -> str:
    try:
        return repr(value)[:4096]
    except BaseException:
        return "<unprintable result>"


def _error_text(error: BaseException) -> str:
    try:
        return f"{type(error).__name__}: {error}"[:4096]
    except BaseException:
        return type(error).__name__


_NODE_COMMENT = re.compile(r"^\s*#\s*weavem-node:\s*(.+?)\s*$")


class _GeneratedFlowTrace:
    """Observe a supported flow without wrapping or changing its task calls."""
    def __init__(self, source: str, source_path: Path, flow_name: str,
                 graph: dict[str, object], emit: Callable[[dict[str, object]], None]):
        self.source_path = str(source_path)
        self.flow_name = flow_name
        self.emit = emit
        self.lines: dict[int, tuple[str, str]] = {}
        try:
            import ast
            tree = ast.parse(source, filename=self.source_path)
            function = next((item for item in tree.body if isinstance(item, ast.FunctionDef)
                             and item.name == flow_name), None)
            assignments = [item for item in (function.body if function is not None else [])
                           if isinstance(item, ast.Assign) and len(item.targets) == 1
                           and isinstance(item.targets[0], ast.Name) and isinstance(item.value, ast.Call)]
        except (SyntaxError, ValueError, MemoryError):
            assignments = []
        raw_nodes = graph.get("nodes", [])
        node_ids = [node.get("id") for node in raw_nodes if isinstance(node, dict)
                    and isinstance(node.get("id"), str)] if isinstance(raw_nodes, list) else []
        # The persistence parser uses the same source-order supported subset.
        # Comments carry durable IDs for generated code; source order provides
        # the safe handwritten fallback where its parsed node IDs already align.
        comments: dict[int, str] = {}
        pending: str | None = None
        for number, text in enumerate(source.splitlines(), 1):
            match = _NODE_COMMENT.match(text)
            if match:
                try: value = json.loads(match.group(1))
                except json.JSONDecodeError: value = None
                pending = value if isinstance(value, str) and value else None
            elif pending is not None and text.strip() and not text.lstrip().startswith("#"):
                comments[number] = pending; pending = None
        for index, assignment in enumerate(assignments):
            node_id = comments.get(assignment.lineno)
            if node_id is None and index < len(node_ids):
                node_id = node_ids[index]
            if node_id is not None:
                self.lines[assignment.lineno] = (node_id, assignment.targets[0].id)
        self.current: tuple[str, str] | None = None
        self.seen: set[str] = set()
        self.active_code: object | None = None

    def _complete(self, frame: object) -> None:
        if self.current is None:
            return
        node_id, variable = self.current
        local_values = getattr(frame, "f_locals", {})
        event: dict[str, object] = {"type": "node", "nodeId": node_id, "status": "completed"}
        try:
            if variable in local_values:
                event["preview"] = _preview(local_values[variable])
                event["value"] = safe_preview(local_values[variable])
        except (KeyError, TypeError):
            pass
        self.emit(event)
        self.current = None

    def __call__(self, frame: object, event: str, _arg: object):
        code = getattr(frame, "f_code", None)
        if event == "call":
            if (getattr(code, "co_filename", None) != self.source_path
                    or getattr(code, "co_name", None) != self.flow_name):
                return None
            self.active_code = code
            return self
        if code is not self.active_code:
            return None
        if event == "line":
            selected = self.lines.get(getattr(frame, "f_lineno", -1))
            if selected is not None:
                if self.current is not None and self.current[0] != selected[0]:
                    self._complete(frame)
                if self.current != selected:
                    self.current = selected
                    self.seen.add(selected[0])
                    self.emit({"type": "node", "nodeId": selected[0], "status": "running"})
        elif event == "return":
            self._complete(frame)
        elif event == "exception" and self.current is not None:
            node_id, _ = self.current
            error = _arg[1] if isinstance(_arg, tuple) and len(_arg) > 1 else RuntimeError("flow failed")
            self.emit({"type": "node", "nodeId": node_id, "status": "failed", "error": _error_text(error), "errorDetails": serialize_error(error)})
            self.current = None
        return self


def _run_saved_flow(request: dict[str, Any], emit: Callable[[dict[str, object]], None]) -> object:
    """Load and invoke the project's normal local flow without policy changes."""
    from .editor_flows import open_flow
    from .flows import load_local_flow

    project = request["project"]
    name = request["flowName"]
    revision = request["revision"]
    params = request["params"]
    opened = open_flow(name, project=project)
    if opened.get("revision") != revision:
        raise RuntimeError("flow changed on disk after the run started; reload before running")
    graph = opened.get("graph")
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    if not isinstance(nodes, list):
        nodes = []
    emit({"type": "run", "status": "preparing", "message": "Preparing flow…"})
    # `load_local_flow` is also used by `weavem flow run`: it preserves the
    # selected project's task bindings, Prefect configuration, retries, and
    # task runner exactly as authored.
    target = load_local_flow(name, project=project,
                             expected_source_sha256=opened.get("sourceSha256"),
                             expected_metadata_sha256=opened.get("metadataSha256"))
    trace = None
    if opened.get("editable") and isinstance(graph, dict):
        from .config import resolve_project
        from .flows import _spec
        # Match the ordinary loader's filename, including configured roots and
        # sidecars whose declared source filename differs from the local name.
        _, source_path = _spec(resolve_project(project), name,
                               expected_metadata_sha256=opened.get("metadataSha256"))
        trace = _GeneratedFlowTrace(opened["source"], source_path, name, graph, emit)
    emit({"type": "run", "status": "running"})
    previous_trace = sys.gettrace()
    try:
        if trace is not None:
            sys.settrace(trace)
        result = target(**params)
    except BaseException as exc:
        # No wrapper/hook modifies task behavior. For the supported generated
        # subset the trace reports the concrete failed assignment; arbitrary
        # handwritten source intentionally gets only flow-level failure.
        if trace is not None:
            for node in nodes:
                node_id = node.get("id") if isinstance(node, dict) else None
                if isinstance(node_id, str) and node_id not in trace.seen and node_id != trace.current:
                    emit({"type": "node", "nodeId": node_id, "status": "skipped"})
        emit({"type": "run", "status": "failed", "error": _error_text(exc), "errorDetails": serialize_error(exc)})
        raise
    finally:
        if trace is not None:
            sys.settrace(previous_trace)
    emit({"type": "run", "status": "completed", "result": _preview(result), "resultValue": safe_preview(result)})
    return result


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: python -m weavem.editor_worker REQUEST_JSON EVENTS_JSONL", file=sys.stderr)
        return 2
    request_path, events_path = map(Path, args)
    write_event = _event_writer(events_path)
    terminal_emitted = False

    def emit(event: dict[str, object]) -> None:
        nonlocal terminal_emitted
        if event.get("type") == "run" and event.get("status") in {"completed", "failed", "cancelled"}:
            terminal_emitted = True
        write_event(event)

    try:
        request: Any = json.loads(request_path.read_text(encoding="utf-8"))
        if (not isinstance(request, dict) or not isinstance(request.get("project"), str)
                or not isinstance(request.get("flowName"), str)
                or not isinstance(request.get("revision"), str)
                or not isinstance(request.get("params"), dict)):
            raise ValueError("request requires project, flowName, revision, and object params")
        _run_saved_flow(request, emit)
    except BaseException as exc:
        if not terminal_emitted:
            emit({"type": "run", "status": "failed", "error": _error_text(exc), "errorDetails": serialize_error(exc)})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
