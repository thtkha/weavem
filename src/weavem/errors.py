"""Structured task failures suitable for people and editor clients."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaskError(Exception):
    """Optional public error contract; Prefect retry policy remains authoritative."""
    code: str
    message: str
    input: str | None = None
    remediation: str | None = None
    retryable: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip():
            raise ValueError("TaskError code must be a non-empty string")
        if not isinstance(self.message, str) or not self.message:
            raise ValueError("TaskError message must be a non-empty string")
        for value in (self.input, self.remediation):
            if value is not None and not isinstance(value, str):
                raise ValueError("TaskError optional text fields must be strings")
        if self.retryable is not None and type(self.retryable) is not bool:
            raise ValueError("TaskError retryable must be a boolean or None")
        Exception.__init__(self, self.message)


def serialize_error(error: BaseException, *, limit: int = 4096) -> dict[str, Any]:
    """Return bounded, explicit public error fields without leaking locals."""
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, TaskError):
            result: dict[str, Any] = {"type": type(error).__name__, "code": current.code,
                                      "message": current.message}
            if current.input is not None: result["input"] = current.input
            if current.remediation is not None: result["remediation"] = current.remediation
            if current.retryable is not None: result["retryable"] = current.retryable
            return _bound(result, limit)
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    try:
        message = str(error)
    except BaseException:
        message = "<unprintable error>"
    return _bound({"type": type(error).__name__, "message": message}, limit)


def _bound(value: dict[str, Any], limit: int) -> dict[str, Any]:
    remaining = max(0, limit)
    bounded: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, str):
            text = item[:remaining]
            bounded[key] = text
            remaining -= len(text)
        else:
            bounded[key] = item
    return bounded
