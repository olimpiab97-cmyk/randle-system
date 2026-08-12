"""Disposable service boundary for the real R1D host/controller integration path.

The operator launcher, version handshake, Python host, HTTP/CSRF layer,
ControlManager, wrapper identity matcher, bounded safety reader, and canonical
service launcher are production sources.  This adapter redirects only external
services and broker/tunnel dependencies to process-backed disposable fixtures.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import command_center_service_control as control


BaseAdapter = control.ProductionServiceAdapter
ServiceClassification = control.ServiceClassification
ServiceSpec = control.ServiceSpec


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


class ProductionShapedAdapter(BaseAdapter):
    NAMES = ("executor", "entry_agent", "trade_manager", "rithmic_listener", "ngrok")
    DISPLAY = {
        "executor": "EXECUTOR",
        "entry_agent": "ENTRY AGENT",
        "trade_manager": "TRADE MANAGER",
        "rithmic_listener": "RITHMIC",
        "ngrok": "NGROK",
    }
    START_ORDER = {"executor": 1, "entry_agent": 2, "trade_manager": 3, "rithmic_listener": 4, "ngrok": 5}
    SHUTDOWN_ORDER = {"ngrok": 1, "rithmic_listener": 2, "trade_manager": 3, "entry_agent": 4, "executor": 5}

    def __init__(self, repository_root: Path, *, timeout: float = 2.0) -> None:
        super().__init__(repository_root, timeout=timeout)
        self.state_path = Path(os.environ["R1E_STATE_PATH"]).resolve()
        self.fixture_helpers = self.repository_root / "tests" / "fixtures" / "command_center_r1e"
        self.launcher = self.repository_root / "launch_all.ps1"
        self.ports = {name: int(os.environ[f"R1E_PORT_{name.upper()}"]) for name in self.NAMES}
        self.safety_read_endpoint = f"http://127.0.0.1:{self.ports['trade_manager']}/trades"
        self._last_safety_read: dict[str, Any] = {}
        self.forced_termination_count = 0

    def _state(self) -> dict[str, Any]:
        for _ in range(20):
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                time.sleep(0.01)
        raise RuntimeError("r1e_state_unavailable")

    def _write_state(self, payload: dict[str, Any]) -> None:
        temporary = self.state_path.with_name(f"{self.state_path.name}.{uuid.uuid4().hex}.adapter.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        deadline = time.monotonic() + 2.0
        while True:
            try:
                os.replace(temporary, self.state_path)
                return
            except PermissionError:
                if time.monotonic() >= deadline:
                    temporary.unlink(missing_ok=True)
                    raise
                time.sleep(0.02)

    @staticmethod
    def _http_json(url: str, timeout: float = 1.0) -> tuple[int | None, dict[str, Any]]:
        try:
            with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=timeout) as response:
                value = json.loads(response.read().decode("utf-8"))
                return int(response.status), value if isinstance(value, dict) else {}
        except HTTPError as exc:
            try:
                value = json.loads(exc.read().decode("utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                value = {}
            return int(exc.code), value if isinstance(value, dict) else {}
        except (OSError, URLError, TimeoutError, json.JSONDecodeError):
            return None, {}

    def _wrapped_identity_pass(self, name: str, record: dict[str, Any]) -> bool:
        mode = str(record.get("mode") or "")
        if name not in {"entry_agent", "trade_manager"} or "WRAPPED" not in mode:
            return True
        if mode == "GOVERNED_WRAPPED_TRANSITIONAL":
            wrapper = self.fixture_helpers / "transitional_wrapper.py"
        else:
            wrapper = self.repository_root / "command_center_service_launcher.py"
        source = self.repository_root / (
            "EntryAgent/tv_context_server.py" if name == "entry_agent" else "Engines/trade_manager.py"
        )
        identity = {
            "type": "GOVERNED_WRAPPED",
            "wrapper_path": wrapper.relative_to(self.repository_root).as_posix(),
            "wrapper_sha256": hashlib.sha256(wrapper.read_bytes()).hexdigest(),
            "service_source_path": source.relative_to(self.repository_root).as_posix(),
            "service_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
        spec = ServiceSpec(
            name=name,
            display_name=self.DISPLAY[name],
            process_name="python",
            command_marker="",
            launch_path=source.relative_to(self.repository_root).as_posix(),
            port=self.ports[name],
            readiness={},
            start_order=self.START_ORDER[name],
            shutdown_order=self.SHUTDOWN_ORDER[name],
            dependencies=(),
            execution_identities=(identity,),
            write_authority_required=True,
        )
        command = f'python.exe "{wrapper}" --service {name}'
        process = {"Name": "python.exe", "CommandLine": command, "ProcessId": int(record.get("pid") or 0)}
        return self._identity_match(spec, process, identity)

    def _ready(self, name: str) -> tuple[bool, str]:
        paths = {
            "executor": "/health",
            "entry_agent": "/entry/status?symbols=NQ,YM",
            "trade_manager": "/debug/version",
            "rithmic_listener": "/health",
            "ngrok": "/health",
        }
        status, payload = self._http_json(f"http://127.0.0.1:{self.ports[name]}{paths[name]}", timeout=0.8)
        if status is not None and 200 <= status < 300 and payload.get("ok") is True:
            return True, "production_shaped_readiness_pass"
        if name == "entry_agent" and status == 503:
            failures = payload.get("rehydration_failures") or []
            reason = next((str(row.get("reason")) for row in failures if isinstance(row, dict)), "dependency_unavailable")
            return False, f"readiness_http_503:{reason}"
        return False, "readiness_unavailable"

    def snapshot(self) -> dict[str, Any]:
        state = self._state()
        rows: list[dict[str, Any]] = []
        for name in self.NAMES:
            record = dict((state.get("services") or {}).get(name) or {})
            pid = int(record.get("pid") or 0)
            running = _alive(pid)
            identity_ok = self._wrapped_identity_pass(name, record) if running else True
            if not running:
                classification = ServiceClassification.STOPPED.value
                identity = "TRUSTED"
                readiness = "STOPPED"
                reason = "expected_process_absent"
                pids: list[int] = []
            elif not identity_ok:
                classification = ServiceClassification.FOREIGN_PROCESS.value
                identity = "FOREIGN"
                readiness = "DEGRADED"
                reason = "wrapper_or_child_identity_mismatch"
                pids = [pid]
            else:
                ready, reason = self._ready(name)
                classification = (
                    ServiceClassification.RUNNING_READY.value if ready else ServiceClassification.RUNNING_NOT_READY.value
                )
                identity = "TRUSTED"
                readiness = "READY" if ready else "NOT_READY"
                pids = [pid]
            rows.append(
                {
                    "name": name,
                    "display_name": self.DISPLAY[name],
                    "identity": identity,
                    "readiness": readiness,
                    "execution_identity": record.get("mode"),
                    "identity_authority": "R1E_PINNED_PRODUCTION_SHAPED",
                    "classification": classification,
                    "reason": reason,
                    "pids": pids,
                    "port": self.ports[name],
                    "start_order": self.START_ORDER[name],
                    "shutdown_order": self.SHUTDOWN_ORDER[name],
                }
            )
        return {"captured_at": datetime.now().astimezone().isoformat(), "services": rows}

    def prearm_snapshot(self) -> dict[str, Any]:
        """Production-shaped Phase-A delay without aging the arm authority."""

        delay_ms = int(self._state().get("prearm_delay_ms") or 0)
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)
        return self.snapshot()

    def credential_authority(self) -> dict[str, Any]:
        return {
            "ok": True,
            "public_present": True,
            "internal_present": True,
            "public_format": True,
            "internal_format": True,
            "distinct": True,
            "authority": "isolated_presence_and_fingerprint_fixture_no_plaintext",
        }

    def _executor_payloads(self) -> tuple[dict[str, Any], dict[str, Any]]:
        _s1, orders = self._http_json(f"http://127.0.0.1:{self.ports['executor']}/orders")
        _s2, positions = self._http_json(f"http://127.0.0.1:{self.ports['executor']}/positions")
        return orders, positions

    def start_safety(self, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        snapshot = snapshot or self.snapshot()
        executor = next(row for row in snapshot["services"] if row["name"] == "executor")
        if executor["classification"] in {
            ServiceClassification.RUNNING_READY.value,
            ServiceClassification.RUNNING_NOT_READY.value,
        }:
            orders_payload, positions_payload = self._executor_payloads()
            if orders_payload.get("ok") is not True or positions_payload.get("ok") is not True:
                return {"ok": False, "safe": False, "reason": "running_executor_state_unavailable"}
            orders = orders_payload.get("orders")
            positions = positions_payload.get("positions")
            authority = "live_executor"
        else:
            state = self._state()
            orders = state.get("orders")
            positions = state.get("positions")
            authority = "persisted_executor_state"
        if not isinstance(orders, list) or not isinstance(positions, dict):
            return {"ok": False, "safe": False, "reason": "executor_state_schema_invalid"}
        active_orders = [row for row in orders if isinstance(row, dict) and str(row.get("status") or "active").lower() not in control.TERMINAL_ORDER_STATES]
        nonzero_positions = [value for value in positions.values() if abs(self._quantity(value)) > 0]
        if active_orders or nonzero_positions:
            return {
                "ok": True,
                "safe": False,
                "reason": "prestart_executor_exposure_active",
                "active_orders": len(active_orders),
                "nonzero_positions": len(nonzero_positions),
                "authority": authority,
            }
        trade = next(row for row in snapshot["services"] if row["name"] == "trade_manager")
        if trade["classification"] in {
            ServiceClassification.RUNNING_READY.value,
            ServiceClassification.RUNNING_NOT_READY.value,
        }:
            result = self._trade_manager_safety_read()
            self._last_safety_read = dict(result)
            if not result.get("ok"):
                return {
                    "ok": False,
                    "safe": False,
                    "reason": "running_trade_manager_state_unavailable",
                    "safety_read_reason": result.get("reason"),
                    "safety_read_attempts": result.get("attempts"),
                    "safety_read_elapsed_ms": result.get("elapsed_ms"),
                }
            payload = result["payload"]
        else:
            state = self._state()
            payload = {
                "trades": state.get("trades", {}),
                "orphan_exposure": state.get("orphan_exposure", {}),
            }
        trades = payload.get("trades")
        orphan = payload.get("orphan_exposure")
        if not isinstance(trades, dict) or not isinstance(orphan, dict):
            return {"ok": False, "safe": False, "reason": "trade_manager_safety_schema_invalid"}
        pending = [row for row in trades.values() if isinstance(row, dict) and str(row.get("status") or "active").lower() not in control.TERMINAL_TRADE_STATES]
        has_orphan = bool(orphan.get("has_orphans") or orphan.get("has_manager_state_issue"))
        safe = not pending and not has_orphan
        return {
            "ok": True,
            "safe": safe,
            "reason": "live_prestart_state_clear" if safe else "live_prestart_state_active",
            "pending_executable_actions": len(pending),
            "orphan_exposure": int(has_orphan),
            "authority": "live_trade_manager" if trade["classification"] != ServiceClassification.STOPPED.value else "persisted_start_gate_only",
            "safety_read_attempts": self._last_safety_read.get("attempts"),
            "safety_read_elapsed_ms": self._last_safety_read.get("elapsed_ms"),
        }

    def start_stack(self) -> dict[str, Any]:
        before = self.snapshot()
        unsafe = [
            row for row in before["services"]
            if row["classification"] in {
                ServiceClassification.DUPLICATE.value,
                ServiceClassification.FOREIGN_PROCESS.value,
                ServiceClassification.UNKNOWN.value,
            }
        ]
        if unsafe:
            return {"ok": False, "message": "SYSTEM NOT READY", "reason": "unsafe_process_identity", "snapshot": before}
        safety = self.start_safety(before)
        if not safety.get("safe"):
            return {"ok": False, "message": "SYSTEM NOT READY", "reason": "start_safety_unavailable_or_active", "start_safety": safety, "snapshot": before}
        write = self.write_authority()
        if not write.get("ok"):
            return {"ok": False, "message": "SYSTEM NOT READY", "reason": "production_write_authority_failed", "write_authority": write}
        if all(row["classification"] == ServiceClassification.RUNNING_READY.value for row in before["services"]):
            return {"ok": True, "already_ready": True, "message": "SYSTEM ALREADY READY", "start_safety": safety, "write_authority": write, "snapshot": before}
        completed = subprocess.run(
            [self._powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(self.launcher)],
            cwd=str(self.repository_root),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            shell=False,
        )
        after = self.snapshot()
        post_safety = self.trading_safety()
        ready = completed.returncode == 0 and all(row["classification"] == ServiceClassification.RUNNING_READY.value for row in after["services"]) and post_safety.get("safe") is True
        return {
            "ok": ready,
            "already_ready": False,
            "message": "SYSTEM READY" if ready else "SYSTEM NOT READY",
            "reason": "canonical_launcher_completed" if ready else "canonical_launcher_or_readiness_failed",
            "launcher_returncode": completed.returncode,
            "start_safety": safety,
            "write_authority": write,
            "post_start_exposure": post_safety,
            "snapshot": after,
        }

    def trading_safety(self) -> dict[str, Any]:
        deadline = self._safety_deadline()
        orders_read = self._safety_json_get_result(f"http://127.0.0.1:{self.ports['executor']}/orders", deadline=deadline)
        positions_read = self._safety_json_get_result(f"http://127.0.0.1:{self.ports['executor']}/positions", deadline=deadline)
        trades_read = self._trade_manager_safety_read(deadline=deadline)
        self._last_safety_read = dict(trades_read)
        if not all(row.get("ok") for row in (orders_read, positions_read, trades_read)):
            failed = next(row for row in (orders_read, positions_read, trades_read) if not row.get("ok"))
            return {
                "ok": False,
                "safe": False,
                "reason": "trading_state_unavailable",
                "safety_read_reason": failed.get("reason"),
                "safety_read_attempts": failed.get("attempts"),
                "safety_read_elapsed_ms": failed.get("elapsed_ms"),
                "active_orders": None,
                "nonzero_positions": None,
                "pending_executable_actions": None,
                "orphan_exposure": None,
            }
        orders = orders_read["payload"].get("orders")
        positions = positions_read["payload"].get("positions")
        trades = trades_read["payload"].get("trades")
        orphan = trades_read["payload"].get("orphan_exposure")
        if not isinstance(orders, list) or not isinstance(positions, dict) or not isinstance(trades, dict) or not isinstance(orphan, dict):
            return {"ok": False, "safe": False, "reason": "trading_state_schema_invalid"}
        active = [row for row in orders if isinstance(row, dict) and str(row.get("status") or "active").lower() not in control.TERMINAL_ORDER_STATES]
        nonzero = [row for row in positions.values() if abs(self._quantity(row)) > 0]
        pending = [row for row in trades.values() if isinstance(row, dict) and str(row.get("status") or "active").lower() not in control.TERMINAL_TRADE_STATES]
        has_orphan = bool(orphan.get("has_orphans") or orphan.get("has_manager_state_issue"))
        safe = not active and not nonzero and not pending and not has_orphan
        return {
            "ok": True,
            "safe": safe,
            "reason": "zero_exposure" if safe else "active_trading_state",
            "active_orders": len(active),
            "nonzero_positions": len(nonzero),
            "pending_executable_actions": len(pending),
            "orphan_exposure": int(has_orphan),
            "safety_read_attempts": trades_read.get("attempts"),
            "safety_read_elapsed_ms": trades_read.get("elapsed_ms"),
        }

    def _stop_pid(self, pid: int) -> bool:
        state = self._state()
        name = next((name for name, row in (state.get("services") or {}).items() if int((row or {}).get("pid") or 0) == int(pid)), None)
        handle = ctypes.windll.kernel32.OpenProcess(0x0001 | 0x00100000, False, int(pid))
        if not handle:
            return not _alive(pid)
        try:
            if not ctypes.windll.kernel32.TerminateProcess(handle, 0):
                return False
            ctypes.windll.kernel32.WaitForSingleObject(handle, 5000)
            self.forced_termination_count += 1
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and _alive(pid):
            time.sleep(0.02)
        if name:
            state = self._state()
            state.setdefault("stop_events", []).append(name)
            self._write_state(state)
        return not _alive(pid)

    def shutdown_stack(self) -> dict[str, Any]:
        initial = self.snapshot()
        if all(row["classification"] == ServiceClassification.STOPPED.value for row in initial["services"]):
            return {"ok": True, "blocked": False, "already_offline": True, "message": "SYSTEM OFFLINE", "stopped": [], "snapshot": initial}
        safety = self.trading_safety()
        if not safety.get("safe"):
            unavailable = safety.get("ok") is not True or safety.get("reason") in {"trading_state_unavailable", "trading_state_schema_invalid"}
            return {
                "ok": False,
                "blocked": True,
                "message": "SHUTDOWN BLOCKED — TRADING STATE UNAVAILABLE" if unavailable else "SHUTDOWN BLOCKED — ACTIVE TRADING STATE",
                "safety": safety,
                "stopped": [],
            }
        protected_before = self.protected_state_hashes()
        rows = {row["name"]: row for row in initial["services"]}
        stopped: list[str] = []
        for name in sorted(self.NAMES, key=lambda item: self.SHUTDOWN_ORDER[item]):
            for pid in rows[name].get("pids", []):
                if not self._stop_pid(int(pid)):
                    return {"ok": False, "blocked": False, "message": "SYSTEM NOT OFFLINE", "reason": f"stop_failed:{name}", "stopped": stopped}
            if rows[name].get("pids"):
                stopped.append(name)
        deadline = time.monotonic() + 10
        after = self.snapshot()
        while time.monotonic() < deadline and any(row["classification"] != ServiceClassification.STOPPED.value for row in after["services"]):
            time.sleep(0.1)
            after = self.snapshot()
        protected_after = self.protected_state_hashes()
        ok = all(row["classification"] == ServiceClassification.STOPPED.value for row in after["services"]) and protected_before == protected_after
        return {
            "ok": ok,
            "blocked": False,
            "message": "SYSTEM OFFLINE" if ok else "SYSTEM NOT OFFLINE",
            "safety": safety,
            "stopped": stopped,
            "snapshot": after,
            "protected_state_unchanged": protected_before == protected_after,
        }

    def ladder_status(self) -> dict[str, Any]:
        status, payload = self._http_json(f"http://127.0.0.1:{self.ports['entry_agent']}/entry/status?symbols=NQ,YM")
        symbols = payload.get("symbols") if isinstance(payload.get("symbols"), list) else []
        expected = str(self._state().get("ladder_session"))
        ready = 0
        for row in symbols:
            context = row.get("market_context") if isinstance(row, dict) else None
            if isinstance(context, dict) and context.get("session_date") == expected and context.get("locked") is True and len(context.get("levels") or {}) == 8:
                ready += 1
        if status == 200 and ready == 2:
            return {"state": "READY", "label": "TV LADDER — READY", "session_date": expected}
        return {"state": "STALE", "label": "TV LADDER — STALE", "session_date": expected}
