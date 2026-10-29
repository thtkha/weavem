"""Bounded, side-effect-free values exposed to the local editor."""
from __future__ import annotations

import json
import math
from typing import Any

_MAX_DEPTH = 6
_MAX_ITEMS = 100
_MAX_STRING_BYTES = 4_096
_MAX_VALUE_BYTES = 5_500
_MAX_ENVELOPE_BYTES = 15 * 1024


def safe_preview(value: object) -> dict[str, Any]:
    """Return a small JSON envelope for exact builtins, otherwise safe text.

    This deliberately does not invoke user container/serialization protocols.
    Truncation removes excess values instead of inserting synthetic fields.
    """
    converted, truncated, ok = _convert(value, 0, [_MAX_ITEMS], [_MAX_VALUE_BYTES], set())
    if ok:
        preview = _json_preview(converted)
        envelope: dict[str, Any] = {"kind": "json", "value": converted,
                                    "preview": preview, "truncated": truncated}
        if _encoded_size(envelope) <= _MAX_ENVELOPE_BYTES:
            return envelope
    return {"kind": "text", "preview": _safe_repr(value), "truncated": True}


def _convert(value: object, depth: int, items: list[int], budget: list[int], seen: set[int]) -> tuple[Any, bool, bool]:
    if depth > _MAX_DEPTH or items[0] <= 0 or budget[0] <= 0:
        return None, True, True
    if value is None or type(value) is bool:
        items[0] -= 1
        return value, False, True
    if type(value) is int:
        try:
            text = str(value)
        except ValueError:
            return None, True, True
        if len(text.encode("utf-8")) > 256:
            return None, True, True
        items[0] -= 1; budget[0] -= len(text)
        return value, False, True
    if type(value) is float:
        text = repr(value)
        items[0] -= 1; budget[0] -= len(text)
        return (value if math.isfinite(value) else text), not math.isfinite(value), True
    if type(value) is str:
        text, cut = _truncate_utf8(value, min(_MAX_STRING_BYTES, budget[0]))
        items[0] -= 1; budget[0] -= len(text.encode("utf-8"))
        return text, cut, True
    if type(value) not in (list, tuple, dict):
        return None, False, False
    identity = id(value)
    if identity in seen:
        return None, True, True
    seen.add(identity)
    try:
        if type(value) in (list, tuple):
            output: list[Any] = []
            truncated = False
            for item in value:
                if items[0] <= 0 or budget[0] <= 0:
                    truncated = True; break
                converted, cut, ok = _convert(item, depth + 1, items, budget, seen)
                if not ok:
                    return None, False, False
                if converted is None and cut:
                    output.append(None); truncated = True; continue
                output.append(converted); truncated |= cut
            return output, truncated, True
        output_dict: dict[str, Any] = {}
        truncated = False
        for key, item in value.items():
            if type(key) is not str:
                return None, False, False
            if items[0] <= 0 or budget[0] <= 0:
                truncated = True; break
            safe_key, key_cut = _truncate_utf8(key, min(256, budget[0]))
            if key_cut or safe_key in output_dict:
                truncated = True; continue
            budget[0] -= len(safe_key.encode("utf-8"))
            converted, cut, ok = _convert(item, depth + 1, items, budget, seen)
            if not ok:
                return None, False, False
            if converted is None and cut:
                truncated = True; continue
            output_dict[safe_key] = converted; truncated |= cut
        return output_dict, truncated, True
    finally:
        seen.remove(identity)


def _truncate_utf8(text: str, maximum: int) -> tuple[str, bool]:
    data = text.encode("utf-8")
    if len(data) <= maximum:
        return text, False
    return data[:maximum].decode("utf-8", errors="ignore"), True


def _encoded_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError, OverflowError):
        return _MAX_ENVELOPE_BYTES + 1


def _safe_repr(value: object) -> str:
    try:
        text = repr(value)
    except BaseException:
        text = "<unprintable result>"
    return _truncate_utf8(text, _MAX_STRING_BYTES)[0]


def _json_preview(value: Any) -> str:
    try:
        return _truncate_utf8(json.dumps(value, ensure_ascii=False, separators=(",", ":")), _MAX_STRING_BYTES)[0]
    except (TypeError, ValueError, OverflowError):
        return "<structured result>"
