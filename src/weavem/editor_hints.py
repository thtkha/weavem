"""Safe, advisory callable hints for the local visual editor.

This module only reads and parses authored source.  It never imports a task,
evaluates annotations, or tries to recover signatures from compiled artifacts.
"""
from __future__ import annotations

import ast
import json
import math
from pathlib import Path
from typing import Any

from .contracts import SourceSpec

_MAX_SOURCE = 1024 * 1024


def _json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_value(item) for key, item in value.items())
    return False


def _annotation(node: ast.expr | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except (ValueError, TypeError):
        return None


def _kind(annotation: str | None) -> str:
    normalized = (annotation or "").replace("typing.", "").replace("builtins.", "").lower()
    if normalized in {"str", "string"}:
        return "string"
    if normalized in {"int", "float", "number"}:
        return "number"
    if normalized in {"bool", "boolean"}:
        return "boolean"
    return "json"


def _default(node: ast.expr | None) -> tuple[object | None, str | None, bool]:
    if node is None:
        return None, None, False
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, MemoryError, RecursionError):
        value = _MISSING
    if value is not _MISSING and _json_value(value):
        return value, None, True
    try:
        return None, ast.unparse(node)[:200], False
    except (ValueError, TypeError):
        return None, "<unsupported default>", False


_MISSING = object()


def _metadata_parameters(inputs: tuple[str, ...]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in inputs:
        name, separator, annotation = item.partition(":")
        name, annotation = name.strip(), annotation.strip().partition("=")[0].strip()
        if not name.isidentifier():
            continue
        result.append({"name": name, "kind": _kind(annotation if separator else None),
                       "required": False, "hasDefault": False,
                       **({"annotation": annotation} if annotation else {})})
    return result


def _rebinds_export(node: ast.stmt, export: str) -> bool:
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return any(isinstance(target, ast.Name) and target.id == export for target in targets)
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return any((alias.asname or alias.name.split(".", 1)[0]) == export for alias in node.names)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name == export
    return False


def source_parameter_hint(task_toml: Path, spec: SourceSpec, inputs: tuple[str, ...] = ()) -> dict[str, Any] | None:
    """Return a static signature hint for an undecorated top-level export.

    Any ambiguity intentionally returns ``None``.  Hints are UI assistance,
    not a runtime contract.
    """
    source = task_toml.parent / spec.source_path
    try:
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(task_toml.parent.resolve()):
            return None
        if source.stat().st_size > _MAX_SOURCE:
            return None
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError, RecursionError):
        return None
    matches = [item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == spec.export]
    if len(matches) != 1 or matches[0].decorator_list:
        return None
    function = matches[0]
    # A later binding changes what import-time lookup would export.  Refuse to
    # claim a signature when static source makes that uncertainty visible.
    position = tree.body.index(function)
    if any(_rebinds_export(item, spec.export) for item in tree.body[position + 1:]):
        return None
    args = function.args
    # Positional-only and variadic arguments cannot be safely expressed as
    # named UI fields.  A raw JSON object remains available to the author.
    if args.posonlyargs or args.vararg or args.kwarg:
        return None
    defaults: list[ast.expr | None] = [None] * (len(args.args) - len(args.defaults)) + list(args.defaults)
    parameters: list[dict[str, Any]] = []
    metadata = {item["name"]: item for item in _metadata_parameters(inputs)}
    for argument, default in [*zip(args.args, defaults), *zip(args.kwonlyargs, args.kw_defaults)]:
        annotation = _annotation(argument.annotation)
        value, display, supported = _default(default)
        item: dict[str, Any] = {
            "name": argument.arg,
            "kind": _kind(annotation),
            "required": default is None,
            "hasDefault": default is not None,
        }
        if annotation:
            item["annotation"] = annotation
        elif argument.arg in metadata:
            item["kind"] = metadata[argument.arg]["kind"]
            if "annotation" in metadata[argument.arg]:
                item["annotation"] = metadata[argument.arg]["annotation"]
        if supported:
            item["defaultValue"] = value
        elif display:
            item["defaultDisplay"] = display
        parameters.append(item)
    return {"origin": "source", "parameters": parameters}


def metadata_parameter_hint(inputs: tuple[str, ...]) -> dict[str, Any] | None:
    """Conservatively expose descriptive metadata when no source is inspectable."""
    parameters = _metadata_parameters(inputs)
    if not parameters:
        return None
    return {"origin": "metadata", "parameters": parameters}
