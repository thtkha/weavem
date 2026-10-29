"""Bounded, side-effect-free values exposed to the local editor."""
from __future__ import annotations

import math
from typing import Any

_MAX_DEPTH = 6
_MAX_ITEMS = 100
_MAX_STRING = 4096
_MAX_BYTES = 16 * 1024


def safe_preview(value: object) -> dict[str, Any]:
    """Return JSON only for exact built-in containers/scalars, otherwise text."""
    budget = [_MAX_BYTES]
    converted, truncated, ok = _convert(value, 0, budget)
    if ok:
        return {"kind": "json", "value": converted, "preview": _json_preview(converted), "truncated": truncated}
    return {"kind": "text", "preview": _safe_repr(value), "truncated": False}


def _convert(value: object, depth: int, budget: list[int]) -> tuple[Any, bool, bool]:
    if depth > _MAX_DEPTH:
        return "<truncated depth>", True, True
    if value is None or type(value) is bool:
        return value, False, True
    if type(value) is int:
        return value, False, True
    if type(value) is float:
        return (value if math.isfinite(value) else str(value)), not math.isfinite(value), True
    if type(value) is str:
        text = value[:min(_MAX_STRING, budget[0])]
        budget[0] -= len(text)
        return text, len(text) != len(value), True
    if type(value) in (list, tuple):
        output, truncated = [], len(value) > _MAX_ITEMS
        for item in value[:_MAX_ITEMS]:
            converted, child_truncated, ok = _convert(item, depth + 1, budget)
            if not ok: return None, False, False
            output.append(converted); truncated |= child_truncated
            if budget[0] <= 0: truncated = True; break
        return output, truncated, True
    if type(value) is dict:
        output: dict[str, Any] = {}; truncated = len(value) > _MAX_ITEMS
        for index, (key, item) in enumerate(value.items()):
            if index >= _MAX_ITEMS: break
            if type(key) is not str: return None, False, False
            converted, child_truncated, ok = _convert(item, depth + 1, budget)
            if not ok: return None, False, False
            output[key] = converted; truncated |= child_truncated
            if budget[0] <= 0: truncated = True; break
        return output, truncated, True
    return None, False, False


def _safe_repr(value: object) -> str:
    try: text = repr(value)
    except BaseException: text = "<unprintable result>"
    return text[:_MAX_STRING]


def _json_preview(value: Any) -> str:
    try:
        import json
        return json.dumps(value, ensure_ascii=False)[:_MAX_STRING]
    except (TypeError, ValueError, OverflowError):
        return "<structured result>"
