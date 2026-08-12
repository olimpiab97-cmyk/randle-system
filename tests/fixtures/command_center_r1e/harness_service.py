"""Process-backed, broker-free services for the R1E production-shaped harness."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def _state_path() -> Path:
    return Path(os.environ["R1E_STATE_PATH"]).resolve()


def _read_state() -> dict[str, Any]:
    for _ in range(20):
        try:
            return json.loads(_state_path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            time.sleep(0.01)
    raise RuntimeError("r1e_state_unavailable")


def _alive(pid: int | None) -> bool:
    if not pid:
        return False
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _service_from_path() -> str | None:
    path = Path(__file__).as_posix().lower()
    if path.endswith("/entryagent/tv_context_server.py"):
        return "entry_agent"
    if path.endswith("/engines/trade_manager.py"):
        return "trade_manager"
    return None


class Handler(BaseHTTPRequestHandler):
    service = ""

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self) -> None:  # noqa: N802
        state = _read_state()
        service = type(self).service
        if service == "executor":
            if self.path == "/orders":
                self._json(HTTPStatus.OK, {"ok": True, "orders": state.get("orders", [])})
                return
            if self.path == "/positions":
                self._json(HTTPStatus.OK, {"ok": True, "positions": state.get("positions", {})})
                return
            self._json(HTTPStatus.OK, {"ok": True, "service": "executor", "mode": "broker_free"})
            return

        if service == "trade_manager":
            if self.path == "/debug/version":
                self._json(HTTPStatus.OK, {"ok": True, "service": "trade_manager", "source": str(Path(__file__).resolve())})
                return
            if self.path == "/trades":
                behavior = state.get("trade_behavior", {})
                mode = str(behavior.get("mode") or "healthy")
                delay_ms = int(behavior.get("delay_ms") or 0)
                if mode == "hung":
                    time.sleep(float(behavior.get("hang_seconds") or 9.0))
                elif delay_ms:
                    time.sleep(delay_ms / 1000.0)
                if mode == "unavailable":
                    self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "reason": "fixture_unavailable"})
                    return
                if mode == "malformed":
                    self._json(HTTPStatus.OK, {"ok": True, "trades": []})
                    return
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "trades": state.get("trades", {}),
                        "orphan_exposure": state.get(
                            "orphan_exposure",
                            {"has_orphans": False, "has_manager_state_issue": False},
                        ),
                    },
                )
                return
            self._json(HTTPStatus.OK, {"ok": True, "service": "trade_manager"})
            return

        if service == "entry_agent":
            services = state.get("services", {})
            executor_ready = _alive((services.get("executor") or {}).get("pid"))
            rithmic_ready = _alive((services.get("rithmic_listener") or {}).get("pid"))
            if not (executor_ready and rithmic_ready):
                self._json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {
                        "ok": False,
                        "service_status": "REHYDRATING",
                        "rehydration_failures": [
                            {"symbol": "NQ", "reason": "canonical_completed_candle_unavailable"}
                        ],
                    },
                )
                return
            session = str(state.get("ladder_session") or datetime.now().date().isoformat())
            levels = {name: float(index) for index, name in enumerate(("PML", "PMH", "ONL", "ONH", "LL", "LH", "PDC", "PDO"), 1)}
            symbols = [
                {
                    "symbol": symbol,
                    "market_context": {
                        "session_date": session,
                        "locked": True,
                        "levels": levels,
                        "canonical_identity": state.get("ladder_identity"),
                    },
                }
                for symbol in ("NQ", "YM")
            ]
            self._json(HTTPStatus.OK, {"ok": True, "service_status": "READY", "mode": "read_only", "symbols": symbols})
            return

        if service == "ngrok":
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "service": "ngrok_model",
                    "public_host": "isolated.invalid",
                    "forward_to": "localhost:fixture_trade_manager",
                    "inspection": False,
                },
            )
            return

        self._json(HTTPStatus.OK, {"ok": True, "service": service})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", choices=("executor", "entry_agent", "trade_manager", "rithmic_listener", "ngrok"))
    args, _unknown = parser.parse_known_args()
    service = args.service or os.environ.get("R1E_TRANSITIONAL_SERVICE") or _service_from_path()
    if not service:
        raise RuntimeError("r1e_service_identity_unavailable")
    port = int(os.environ[f"R1E_PORT_{service.upper()}"])
    handler = type(f"{service.title()}Handler", (Handler,), {"service": service})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.daemon_threads = True
    server.serve_forever(poll_interval=0.1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
