"""Local-only HTTP bridge for the experimental visual editor.

The browser never chooses a Python executable or project: both are fixed when
``weavem editor`` starts.  It is intentionally a small standard-library server,
not a hosted Weavem API.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import mimetypes
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from .config import ProjectConfig, resolve_project
from .contracts import ContractError

_MAX_BODY = 5 * 1024 * 1024
_MAX_LOG_TAIL = 64 * 1024


class EditorServerError(ContractError):
    """Raised for a safe-to-display editor startup error."""


def _ui_directory(value: str | Path | None) -> Path:
    """Resolve an explicit UI build, or the checkout's development build."""
    candidate = (Path(value).expanduser() if value is not None
                 else Path(__file__).resolve().parents[2] / "ui" / "dist")
    candidate = candidate.resolve()
    if not candidate.is_dir() or not (candidate / "index.html").is_file():
        raise EditorServerError(
            f"editor UI build is missing: {candidate}. Run `cd ui && npm run build`, "
            "or pass --ui-dir PATH.")
    return candidate


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _project_flow(project: ProjectConfig, catalog: dict) -> dict | None:
    """Open the optional project-local canvas entrypoint, resolving trusted aliases."""
    path = project.root / "flows" / "editor.json"
    if path.is_symlink() or path.parent.is_symlink():
        raise EditorServerError("flows/editor.json must not use symlinks")
    if not path.exists():
        return None
    if path.stat().st_size > _MAX_BODY:
        raise EditorServerError("flows/editor.json exceeds 5 MiB")
    definition = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(definition, dict) or definition.get("kind") != "weavem.project-flow"
            or type(definition.get("schema")) is not int or definition["schema"] != 1
            or not isinstance(definition.get("nodes"), list)):
        raise EditorServerError("flows/editor.json requires project-flow schema 1 and nodes")
    keys = {alias: key for key, alias in catalog["bindings"].items()}
    nodes = []
    for node in definition["nodes"]:
        if not isinstance(node, dict) or not isinstance(node.get("taskAlias"), str) or node["taskAlias"] not in keys:
            raise EditorServerError("flows/editor.json contains an unknown project task alias")
        nodes.append({"id": node.get("id"), "taskKey": keys[node["taskAlias"]],
                      "parameters": node.get("parameters", {})})
    graph = {"kind": "weavem.graph", "schema": 1, "name": definition.get("name"),
             "nodes": nodes, "edges": definition.get("edges")}
    from .editor_graph import validate_graph
    validate_graph(graph, project.root)
    return graph


def _bounded_preview(value: object) -> object:
    """Keep browser response/event handling bounded even for a bad worker event."""
    try:
        raw = _json_bytes(value)
    except (TypeError, ValueError):
        return str(value)[:4096]
    if len(raw) <= 16 * 1024:
        return value
    return raw[:16 * 1024].decode("utf-8", "replace") + "…"


@dataclass
class Run:
    run_id: str
    directory: Path
    process: subprocess.Popen[bytes]
    nodes: dict[str, dict[str, object]]
    request_path: Path
    events_path: Path
    stdout_path: Path
    stderr_path: Path
    status: str = "running"
    terminal_status: str | None = None
    error: str | None = None
    cancelled: bool = False
    event_offset: int = 0
    lock: threading.RLock = field(default_factory=threading.RLock)


class RunManager:
    def __init__(self, project: ProjectConfig):
        self.project = project
        self._runs: dict[str, Run] = {}
        self._active: str | None = None
        self._lock = threading.RLock()

    def start(self, graph: dict[str, object]) -> Run:
        # Validate before any artifact/process creation. Reserve the sole active
        # slot before spawning so concurrent POSTs cannot run two graphs.
        from .editor_graph import validate_graph
        validate_graph(graph, self.project.root)
        with self._lock:
            self._refresh_active()
            if self._active is not None:
                raise EditorServerError("a run is already active")
            self._active = "__starting__"
        try:
            nodes = graph.get("nodes")
            assert isinstance(nodes, list)  # validate_graph establishes this contract.
            run_id = str(uuid4())
            directory = self.project.work_dir / "editor-runs" / run_id
            directory.mkdir(parents=True, exist_ok=False)
            request_path = directory / "request.json"
            events_path = directory / "events.jsonl"
            stdout_path = directory / "worker.stdout.log"
            stderr_path = directory / "worker.stderr.log"
            request_path.write_bytes(_json_bytes({"project": str(self.project.root), "graph": graph}))
            events_path.touch()
            stdout = stdout_path.open("wb")
            stderr = stderr_path.open("wb")
            # A desktop editor must not accidentally inherit a remote Prefect
            # profile from its shell. The worker gets an isolated local home.
            environment = dict(os.environ)
            for key in ("PREFECT_API_URL", "PREFECT_API_KEY", "PREFECT_CLOUD_API_URL",
                        "PREFECT_PROFILES_PATH", "PREFECT_PROFILE", "PREFECT_SERVER_API_HOST",
                        "PREFECT_SERVER_API_PORT", "PREFECT_SERVER_ANALYTICS_ENABLED"):
                environment.pop(key, None)
            # Project dotenv/profile files must not turn a local visual run into
            # a remote Prefect connection after inherited shell settings are removed.
            environment["PREFECT_API_URL"] = ""
            environment["PREFECT_API_KEY"] = ""
            environment["PREFECT_SERVER_ANALYTICS_ENABLED"] = "false"
            environment["PREFECT_HOME"] = str(directory / "prefect")
            package_root = str(Path(__file__).resolve().parents[1])
            environment["PYTHONPATH"] = package_root + (os.pathsep + environment["PYTHONPATH"]
                                                        if environment.get("PYTHONPATH") else "")
            try:
                process = subprocess.Popen(
                    [sys.executable, "-m", "weavem.editor_worker", str(request_path), str(events_path)],
                    cwd=self.project.root,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    start_new_session=True,
                    env=environment,
                )
            finally:
                stdout.close()
                stderr.close()
            initial = {str(node["id"]): {"status": "pending"} for node in nodes if isinstance(node, dict)}
            run = Run(run_id, directory, process, initial, request_path, events_path, stdout_path, stderr_path)
            with self._lock:
                self._runs[run_id] = run
                self._active = run_id
            return run
        except Exception:
            with self._lock:
                if self._active == "__starting__":
                    self._active = None
            raise

    def _refresh_active(self) -> None:
        if self._active in (None, "__starting__"):
            return
        run = self._runs.get(self._active)
        if run is not None:
            with run.lock:
                self._finish_if_exited(run)

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        # The leader can exit before spawned grandchildren. Signal the process
        # group regardless, then escalate so cancellation leaves no worker tree.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass

    def _finish_if_exited(self, run: Run) -> None:
        self._consume_events(run)
        code = run.process.poll()
        if code is None:
            return
        if run.status == "running":
            if run.cancelled:
                run.status = "cancelled"
            elif run.terminal_status is not None:
                run.status = run.terminal_status
            else:
                run.status = "failed"
                # A native crash or os._exit(0) can bypass the worker protocol.
                # Exit code alone cannot prove that the graph completed.
                run.error = f"worker exited without a terminal event (status {code})"
            for node in run.nodes.values():
                if node.get("status") == "running":
                    node["status"] = "failed"
                    node["error"] = run.error or "worker stopped before this task finished"
                elif node.get("status") == "pending":
                    node["status"] = "skipped"
        if self._active == run.run_id:
            self._active = None

    def _consume_events(self, run: Run) -> None:
        try:
            with run.events_path.open("rb") as stream:
                stream.seek(run.event_offset)
                data = stream.read()
                run.event_offset = stream.tell()
        except OSError:
            return
        # A partial final line belongs to a future poll; retry it next time.
        lines = data.splitlines(keepends=True)
        if lines and not lines[-1].endswith((b"\n", b"\r")):
            run.event_offset -= len(lines.pop())
        for line in lines:
            try:
                event = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(event, dict):
                continue
            self._apply_event(run, event)

    @staticmethod
    def _apply_event(run: Run, event: dict[str, object]) -> None:
        status = event.get("status")
        node_id = event.get("nodeId", event.get("node_id"))
        if isinstance(node_id, str) and node_id in run.nodes:
            node = run.nodes[node_id]
            if isinstance(status, str) and status in {"pending", "running", "completed", "failed", "skipped"}:
                node["status"] = status
            if "preview" in event:
                node["preview"] = _bounded_preview(event["preview"])
            if isinstance(event.get("error"), str):
                node["error"] = event["error"][:4096]
        elif isinstance(status, str) and status in {"completed", "failed", "cancelled"}:
            run.terminal_status = status
            if isinstance(event.get("error"), str):
                run.error = event["error"][:4096]

    @staticmethod
    def _tail(path: Path) -> str:
        try:
            with path.open("rb") as stream:
                stream.seek(0, os.SEEK_END)
                size = stream.tell()
                stream.seek(max(0, size - _MAX_LOG_TAIL))
                text = stream.read().decode("utf-8", "replace")
                return ("…\n" if size > _MAX_LOG_TAIL else "") + text
        except OSError:
            return ""

    def state(self, run_id: str) -> dict[str, object] | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            with run.lock:
                self._finish_if_exited(run)
                payload: dict[str, object] = {"runId": run.run_id, "status": run.status,
                                              "nodes": run.nodes, "logs": self._tail(run.stdout_path) + self._tail(run.stderr_path)}
                if run.error:
                    payload["error"] = run.error
                return payload

    def cancel(self, run_id: str) -> dict[str, object] | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            with run.lock:
                # A terminal worker event can be on disk just as a user presses
                # Cancel. Reconcile its exit first; never overwrite completion.
                self._finish_if_exited(run)
                if run.status == "running" and run.terminal_status is not None:
                    # The graph already reported its terminal outcome, but the
                    # worker may still be cleaning up Prefect resources. Stop
                    # that remaining process without rewriting completed nodes.
                    self._terminate(run.process)
                    run.status = run.terminal_status
                    if self._active == run_id:
                        self._active = None
                elif run.status == "running":
                    run.cancelled = True
                    for node in run.nodes.values():
                        if node.get("status") == "running":
                            node["status"] = "failed"
                            node["error"] = "cancelled"
                        elif node.get("status") == "pending":
                            node["status"] = "skipped"
                    self._terminate(run.process)
                    run.status = "cancelled"
                    if self._active == run_id:
                        self._active = None
                return self.state(run_id)

    def close(self) -> None:
        with self._lock:
            runs = list(self._runs.values())
        for run in runs:
            with run.lock:
                if run.process.poll() is None:
                    run.cancelled = True
                    self._terminate(run.process)
                if run.status == "running":
                    run.status = "cancelled"


class EditorHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], project: ProjectConfig, ui_dir: Path):
        super().__init__(address, EditorHandler)
        self.project = project
        self.ui_dir = ui_dir
        self.token = secrets.token_urlsafe(32)
        self.runs = RunManager(project)

    def server_close(self) -> None:
        self.runs.close()
        super().server_close()


class EditorHandler(BaseHTTPRequestHandler):
    server: EditorHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:
        # Browser polling must not turn normal editor use into terminal noise.
        return

    def _allowed_host(self) -> bool:
        host = self.headers.get("Host", "")
        return host in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

    def _origin(self) -> str:
        return f"http://{self.headers.get('Host', '')}"

    def _trusted_request(self) -> bool:
        if not self._allowed_host():
            self._error(HTTPStatus.BAD_REQUEST, "invalid Host header")
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin != self._origin():
            self._error(HTTPStatus.FORBIDDEN, "cross-origin request denied")
            return False
        if self.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
            self._error(HTTPStatus.FORBIDDEN, "cross-site request denied")
            return False
        return True

    def _authorized(self) -> bool:
        if self.headers.get("X-Weavem-Token") != self.server.token:
            self._error(HTTPStatus.UNAUTHORIZED, "missing or invalid session token")
            return False
        return True

    def _json(self, status: HTTPStatus, data: object) -> None:
        body = _json_bytes(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, message: str) -> None:
        # Rejections can happen before an advertised POST body is consumed.
        # Close rather than parsing that body as a second HTTP request.
        self.close_connection = True
        body = _json_bytes({"error": message})
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, object] | None:
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._error(HTTPStatus.BAD_REQUEST, "Content-Length is required")
            return None
        if length < 0 or length > _MAX_BODY:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "JSON body exceeds 5 MiB")
            return None
        if self.headers.get("Content-Type", "").split(";", 1)[0].lower() != "application/json":
            self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Content-Type must be application/json")
            return None
        try:
            data = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error(HTTPStatus.BAD_REQUEST, "invalid JSON body")
            return None
        if not isinstance(data, dict):
            self._error(HTTPStatus.BAD_REQUEST, "JSON body must be an object")
            return None
        return data

    def do_GET(self) -> None:  # noqa: N802
        if not self._trusted_request():
            return
        path = urlsplit(self.path).path
        if path == "/api/session":
            from .editor_graph import editor_catalog
            try:
                catalog = editor_catalog(self.server.project.root)
                project_flow = _project_flow(self.server.project, catalog)
            except (ContractError, OSError, ValueError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._json(HTTPStatus.OK, {"token": self.server.token, "project": str(self.server.project.root),
                                       "flow": project_flow, **catalog})
            return
        if path.startswith("/api/"):
            if not self._authorized():
                return
            prefix = "/api/runs/"
            if path.startswith(prefix) and "/" not in path[len(prefix):]:
                state = self.server.runs.state(path[len(prefix):])
                if state is None:
                    self._error(HTTPStatus.NOT_FOUND, "run not found")
                else:
                    self._json(HTTPStatus.OK, state)
                return
            self._error(HTTPStatus.NOT_FOUND, "API endpoint not found")
            return
        self._static(path)

    def _static(self, raw_path: str) -> None:
        try:
            requested = unquote(raw_path).lstrip("/")
            lexical = self.server.ui_dir / requested
            candidate = lexical.resolve()
            if (not candidate.is_relative_to(self.server.ui_dir)
                    or any(part.is_symlink() for part in (lexical, *lexical.parents))):
                raise ValueError
            # Single-page app routes deliberately return index; real extension
            # paths must exist to avoid masking a missing JS/CSS asset.
            if not candidate.is_file():
                if "." in Path(requested).name:
                    self._error(HTTPStatus.NOT_FOUND, "asset not found")
                    return
                candidate = self.server.ui_dir / "index.html"
                # The SPA fallback is a separate lookup: it must not bypass the
                # same containment rule enforced for explicitly requested files.
                if candidate.is_symlink() or not candidate.resolve().is_relative_to(self.server.ui_dir):
                    raise ValueError
            content = candidate.read_bytes()
        except (OSError, ValueError):
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        mime = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:  # noqa: N802
        if not self._trusted_request() or not self._authorized():
            return
        path = urlsplit(self.path).path
        body = self._body()
        if body is None:
            return
        if path == "/api/runs":
            # The endpoint accepts the versioned graph itself; the browser
            # cannot supply a project, interpreter, or filesystem path.
            graph = body
            try:
                run = self.server.runs.start(graph)
            except EditorServerError as exc:
                self._error(HTTPStatus.CONFLICT, str(exc))
                return
            except (ContractError, OSError, ValueError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._json(HTTPStatus.ACCEPTED, {"runId": run.run_id, "status": "running"})
            return
        prefix = "/api/runs/"
        suffix = "/cancel"
        if path.startswith(prefix) and path.endswith(suffix):
            run_id = path[len(prefix):-len(suffix)]
            if "/" in run_id or not run_id:
                self._error(HTTPStatus.NOT_FOUND, "API endpoint not found")
                return
            result = self.server.runs.cancel(run_id)
            if result is None:
                self._error(HTTPStatus.NOT_FOUND, "run not found")
            else:
                self._json(HTTPStatus.OK, result)
            return
        self._error(HTTPStatus.NOT_FOUND, "API endpoint not found")


def serve_editor(project: str | Path | None, *, port: int = 8765,
                 ui_dir: str | Path | None = None) -> None:
    if not 0 <= port <= 65535:
        raise EditorServerError("--port must be between 0 and 65535")
    config = resolve_project(project)
    server = EditorHTTPServer(("127.0.0.1", port), config, _ui_directory(ui_dir))
    print(f"Project: {config.root}\nPython: {sys.executable}", flush=True)
    print(f"Weavem editor: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
