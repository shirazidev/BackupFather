"""Lightweight /healthz HTTP endpoint reporting last backup status.

Uses only the standard library so it adds no dependencies or attack surface.
Runs in a daemon thread; the scheduler owns its lifecycle.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from backupfather.models import BackupResult
from backupfather.utils.logger import get_logger

log = get_logger(__name__)


class HealthState:
    """Thread-safe record of the most recent run per database."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last: dict[str, dict[str, object]] = {}

    def record(self, result: BackupResult) -> None:
        with self._lock:
            self._last[result.db_name] = {
                "ok": result.ok,
                "duration_seconds": round(result.duration_seconds, 2),
                "failed_step": result.failed_step.value if result.failed_step else None,
                "size_mb": round(result.artifact.size_mb, 2) if result.artifact else None,
                "finished_at": result.artifact.created_at if result.artifact else None,
            }

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            databases = dict(self._last)
        if not databases:
            # No backup has run yet (e.g. waiting for the first scheduled run).
            status = "starting"
        elif all(d["ok"] for d in databases.values()):
            status = "ok"
        else:
            status = "degraded"
        return {"status": status, "databases": databases}


def render(state: HealthState, path: str) -> tuple[int, bytes]:
    """Pure routing: map (state, request path) -> (status_code, json body).

    Kept transport-free so it can be unit-tested without opening a socket.
    """
    if path.rstrip("/") not in ("/healthz", ""):
        return 404, b'{"error":"not found"}'
    snapshot = state.snapshot()
    # 200 while starting (no run yet) or healthy; 503 only once a run has failed.
    code = 503 if snapshot["status"] == "degraded" else 200
    return code, json.dumps(snapshot).encode()


def _make_handler(state: HealthState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            code, body = render(state, self.path)
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            # Silence default stderr access logging.
            return

    return Handler


class HealthServer:
    def __init__(self, state: HealthState, port: int) -> None:
        self._server = ThreadingHTTPServer(("0.0.0.0", port), _make_handler(state))  # noqa: S104
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self.port = port

    def start(self) -> None:
        self._thread.start()
        log.info("healthcheck listening on :%d/healthz", self.port)

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
