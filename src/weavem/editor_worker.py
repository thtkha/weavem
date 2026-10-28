"""Isolated process entrypoint for one editor graph run."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Callable

from .editor_graph import execute_graph


def _event_writer(path: Path) -> Callable[[dict[str, str]], None]:
    def emit(event: dict[str, str]) -> None:
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        with path.open("a", encoding="utf-8") as events:
            events.write(line + "\n")
            events.flush()
    return emit


def _execute_with_local_prefect(request: dict[str, Any], emit: Callable[[dict[str, str]], None]) -> None:
    """Run with no configured Prefect API, even when a project ``.env`` has one."""
    from prefect.settings import (PREFECT_API_KEY, PREFECT_API_URL,
                                  PREFECT_SERVER_ALLOW_EPHEMERAL_MODE,
                                  temporary_settings)

    # An empty API URL is not equivalent to None: Prefect treats it as an
    # EventsClient destination. Explicitly select ephemeral local orchestration.
    updates = {
        PREFECT_API_URL: None,
        PREFECT_API_KEY: None,
        PREFECT_SERVER_ALLOW_EPHEMERAL_MODE: True,
    }
    with temporary_settings(updates=updates):
        execute_graph(request.get("graph"), request["project"], emit)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: python -m weavem.editor_worker REQUEST_JSON EVENTS_JSONL", file=sys.stderr)
        return 2
    request_path, events_path = map(Path, args)
    write_event = _event_writer(events_path)
    terminal_emitted = False

    def emit(event: dict[str, str]) -> None:
        nonlocal terminal_emitted
        if event.get("type") == "run" and event.get("status") in {"completed", "failed"}:
            terminal_emitted = True
        write_event(event)

    try:
        request: Any = json.loads(request_path.read_text(encoding="utf-8"))
        if not isinstance(request, dict) or not isinstance(request.get("project"), str):
            raise ValueError("request requires string project")
        _execute_with_local_prefect(request, emit)
    except BaseException as exc:
        # Once execute_graph starts it owns the terminal event. Imports and
        # settings initialization can fail earlier, so report those once here.
        if not terminal_emitted:
            emit({"type": "run", "status": "failed",
                  "error": f"{type(exc).__name__}: {exc}"[:4096]})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
