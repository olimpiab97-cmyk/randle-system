"""Loopback-only host for the existing Command Center and service controls."""

from __future__ import annotations

import argparse
import json
import secrets
import threading
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from command_center_service_control import CONTROL_VERSION, ControlManager, ProductionServiceAdapter


HOST = "127.0.0.1"
PORT = 7100
SESSION_COOKIE = "randle_command_center_session"
CSRF_HEADER = "X-Command-Center-CSRF"
MAX_BODY_BYTES = 4096


class CommandCenterApplication:
    def __init__(self, repository_root: Path, controller: ControlManager) -> None:
        self.repository_root = repository_root.resolve()
        self.controller = controller
        self.html_path = self.repository_root / "command_center.html"
        self._sessions: dict[str, str] = {}
        self._session_lock = threading.Lock()

    def new_session(self) -> tuple[str, str]:
        session_id = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        with self._session_lock:
            self._sessions = {session_id: csrf}
        return session_id, csrf

    def csrf_for(self, session_id: str | None) -> str | None:
        with self._session_lock:
            return self._sessions.get(str(session_id or ""))

    def render_html(self, csrf: str) -> bytes:
        text = self.html_path.read_text(encoding="utf-8")
        return text.replace("__COMMAND_CENTER_CSRF_TOKEN__", csrf).encode("utf-8")


class CommandCenterHandler(BaseHTTPRequestHandler):
    server_version = "RandleCommandCenter/1"

    @property
    def application(self) -> CommandCenterApplication:
        return self.server.application  # type: ignore[attr-defined]

    def log_message(self, format_string: str, *args: Any) -> None:
        # Never include query strings, headers, cookies, or request bodies.
        path = urlsplit(self.path).path
        print(f"COMMAND_CENTER_ACCESS method={self.command} path={path} status={args[1] if len(args) > 1 else '-'}")

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _session_id(self) -> str | None:
        cookie = SimpleCookie(self.headers.get("Cookie") or "")
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin") or ""
        allowed = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
        return origin in allowed

    def _authorized(self, *, write: bool) -> bool:
        if self.client_address[0] not in {"127.0.0.1", "::1"}:
            return False
        expected = self.application.csrf_for(self._session_id())
        if not expected:
            return False
        if write:
            supplied = self.headers.get(CSRF_HEADER) or ""
            return self._same_origin() and secrets.compare_digest(expected, supplied)
        return True

    def _read_json(self) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if length <= 0 or length > MAX_BODY_BYTES:
            return None
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/health":
            self._send_json(HTTPStatus.OK, {"ok": True, "service": "command_center_host", "version": CONTROL_VERSION, "repository_root": str(self.application.repository_root)})
            return
        if path in {"/", "/command_center.html"}:
            session_id, csrf = self.application.new_session()
            body = self.application.render_html(csrf)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
            self.send_header("Set-Cookie", f"{SESSION_COOKIE}={session_id}; HttpOnly; SameSite=Strict; Path=/")
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/system-control/status":
            if not self._authorized(write=False):
                self._send_json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "local_control_session_required"})
                return
            self.application.controller.expire_arms()
            self._send_json(HTTPStatus.OK, self.application.controller.status())
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path not in {"/api/system-control/arm", "/api/system-control/confirm"}:
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        if not self._authorized(write=True):
            self._send_json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "local_same_origin_control_authority_required"})
            return
        payload = self._read_json()
        if payload is None:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_json"})
            return
        session_id = self._session_id() or ""
        if path.endswith("/arm"):
            result = self.application.controller.arm(
                str(payload.get("action") or ""),
                source="loopback_command_center",
                session_id=session_id,
            )
        else:
            result = self.application.controller.confirm(
                str(payload.get("request_id") or ""),
                session_id=session_id,
                action=str(payload.get("action") or ""),
                control_version=CONTROL_VERSION,
            )
        self._send_json(HTTPStatus.OK if result.get("ok") else HTTPStatus.CONFLICT, result)


class CommandCenterServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], application: CommandCenterApplication) -> None:
        self.application = application
        super().__init__(address, CommandCenterHandler)


def build_application(repository_root: Path) -> CommandCenterApplication:
    data_root = Path(__import__("os").environ.get("RANDLE_DATA_ROOT") or (repository_root / "Data"))
    audit_path = data_root / "command_center" / "service_control_audit.jsonl"
    adapter = ProductionServiceAdapter(repository_root)
    controller = ControlManager(adapter, audit_path)
    return CommandCenterApplication(repository_root, controller)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the loopback-only Randle Command Center host")
    parser.add_argument("--host", default=HOST, choices=[HOST])
    parser.add_argument("--port", type=int, default=PORT, choices=[PORT])
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    server = CommandCenterServer((args.host, args.port), build_application(root))
    print(f"COMMAND_CENTER_HOST_READY host={args.host} port={args.port} control_version={CONTROL_VERSION}")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
