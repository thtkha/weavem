"""Safe, advisory callable hints for the local visual editor.

This module only reads and parses authored source.  It never imports a task,
evaluates annotations, or tries to recover signatures from compiled artifacts.
"""
from __future__ import annotations

import ast
import math
from pathlib import Path
from typing import Any

from .contracts import SourceSpec

_MAX_SOURCE = 1024 * 1024
_MAX_TYPED_DEPTH = 4
_MISSING = object()


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


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
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


def _literal_choices(node: ast.expr | None) -> list[Any] | None:
    if not isinstance(node, ast.Subscript) or _name(node.value) != "Literal":
        return None
    values = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
    try:
        parsed = [ast.literal_eval(value) for value in values]
    except (ValueError, TypeError, MemoryError, RecursionError):
        return None
    return parsed if parsed and all(_json_value(value) for value in parsed) else None


def _nullable(node: ast.expr | None) -> bool:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _nullable_member(node.left) or _nullable_member(node.right)
    if isinstance(node, ast.Subscript) and _name(node.value) == "Optional":
        return True
    if isinstance(node, ast.Subscript) and _name(node.value) == "Union":
        values = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        return any(_nullable_member(value) for value in values)
    return False


def _nullable_member(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _unwrap_required(node: ast.expr) -> tuple[ast.expr, bool | None]:
    if isinstance(node, ast.Subscript) and _name(node.value) in {"Required", "NotRequired"}:
        return node.slice, _name(node.value) == "Required"
    return node, None


def _typed_dicts(tree: ast.Module) -> dict[str, tuple[bool, list[tuple[str, ast.expr, bool]]]]:
    definitions: dict[str, tuple[bool, list[tuple[str, ast.expr, bool]]]] = {}
    for statement in tree.body:
        if not isinstance(statement, ast.ClassDef) or not any(_name(base) == "TypedDict" for base in statement.bases):
            continue
        total = True
        for keyword in statement.keywords:
            if keyword.arg == "total" and isinstance(keyword.value, ast.Constant) and type(keyword.value.value) is bool:
                total = keyword.value.value
        entries: list[tuple[str, ast.expr, bool]] = []
        for item in statement.body:
            if not isinstance(item, ast.AnnAssign) or not isinstance(item.target, ast.Name):
                continue
            annotation, required_override = _unwrap_required(item.annotation)
            entries.append((item.target.id, annotation, total if required_override is None else required_override))
        definitions[statement.name] = (total, entries)
    return definitions


def _hint(name: str, annotation: ast.expr | None, *, required: bool, has_default: bool,
          typed: dict[str, tuple[bool, list[tuple[str, ast.expr, bool]]]],
          ancestors: tuple[str, ...] = ()) -> dict[str, Any]:
    text = _annotation(annotation)
    item: dict[str, Any] = {"name": name, "kind": _kind(text), "required": required, "hasDefault": has_default}
    if text:
        item["annotation"] = text
    choices = _literal_choices(annotation)
    if choices is not None:
        item["choices"] = choices
    if _nullable(annotation):
        item["nullable"] = True
    if isinstance(annotation, ast.Name) and annotation.id in typed and len(ancestors) < _MAX_TYPED_DEPTH:
        if annotation.id not in ancestors:
            item["fields"] = [_hint(field_name, field_annotation, required=field_required,
                                    has_default=False, typed=typed, ancestors=ancestors + (annotation.id,))
                              for field_name, field_annotation, field_required in typed[annotation.id][1]]
    return item


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
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == export


def source_parameter_hint(task_toml: Path, spec: SourceSpec, inputs: tuple[str, ...] = ()) -> dict[str, Any] | None:
    """Return a source-only advisory signature for an undecorated export."""
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
    position = tree.body.index(function)
    if any(_rebinds_export(item, spec.export) for item in tree.body[position + 1:]):
        return None
    args = function.args
    if args.posonlyargs or args.vararg or args.kwarg:
        return None
    defaults = [None] * (len(args.args) - len(args.defaults)) + list(args.defaults)
    typed = _typed_dicts(tree)
    metadata = {item["name"]: item for item in _metadata_parameters(inputs)}
    parameters: list[dict[str, Any]] = []
    for argument, default in [*zip(args.args, defaults), *zip(args.kwonlyargs, args.kw_defaults)]:
        item = _hint(argument.arg, argument.annotation, required=default is None, has_default=default is not None, typed=typed)
        if argument.annotation is None and argument.arg in metadata:
            item.update({key: value for key, value in metadata[argument.arg].items() if key in {"kind", "annotation"}})
        value, display, supported = _default(default)
        if supported:
            item["defaultValue"] = value
        elif display:
            item["defaultDisplay"] = display
        parameters.append(item)
    result: dict[str, Any] = {"origin": "source", "parameters": parameters}
    description = ast.get_docstring(function)
    if description:
        result["description"] = description.strip()[:4096]
    if function.returns is not None:
        output = _hint("return", function.returns, required=False, has_default=False, typed=typed)
        output.pop("name")
        output.pop("required")
        output.pop("hasDefault")
        result["output"] = output
    return result


def metadata_parameter_hint(inputs: tuple[str, ...]) -> dict[str, Any] | None:
    parameters = _metadata_parameters(inputs)
    return {"origin": "metadata", "parameters": parameters} if parameters else None
