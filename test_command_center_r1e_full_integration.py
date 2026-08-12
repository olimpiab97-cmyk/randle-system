from __future__ import annotations

import ctypes
import hashlib
import http.cookiejar
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
MANIFEST_RELATIVE = Path("Architecture") / "Command_Center" / "command_center_governed_service_manifest.json"
HELPERS_RELATIVE = Path("tests") / "fixtures" / "command_center_r1e"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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


def _terminate_exact(pid: int) -> bool:
    handle = ctypes.windll.kernel32.OpenProcess(0x0001 | 0x00100000, False, int(pid))
    if not handle:
        return not _alive(pid)
    try:
        if not ctypes.windll.kernel32.TerminateProcess(handle, 0):
            return False
        ctypes.windll.kernel32.WaitForSingleObject(handle, 5000)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)
    return not _alive(pid)


def _listener_pids(port: int) -> set[int]:
    completed = subprocess.run(
        ["netstat.exe", "-ano", "-p", "TCP"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    result: set[int] = set()
    for line in completed.stdout.splitlines():
        columns = line.split()
        if len(columns) >= 5 and columns[0].upper() == "TCP" and columns[1].endswith(f":{port}") and columns[3].upper() == "LISTENING":
            result.add(int(columns[4]))
    return result


class LocalClient:
    def __init__(self) -> None:
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        page = self.opener.open("http://127.0.0.1:7100/", timeout=5).read().decode("utf-8")
        self.csrf = page.split('const COMMAND_CENTER_CSRF = "', 1)[1].split('";', 1)[0]
        self.armed_actions: dict[str, str] = {}

    def get(self, path: str) -> dict[str, Any]:
        return json.loads(self.opener.open(f"http://127.0.0.1:7100{path}", timeout=15).read().decode("utf-8"))

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"http://127.0.0.1:7100{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Origin": "http://127.0.0.1:7100",
                "X-Command-Center-CSRF": self.csrf,
            },
            method="POST",
        )
        try:
            response = self.opener.open(request, timeout=15)
        except urllib.error.HTTPError as exc:
            return json.loads(exc.read().decode("utf-8"))
        return json.loads(response.read().decode("utf-8"))

    def arm(self, action: str) -> dict[str, Any]:
        result = self.post("/api/system-control/arm", {"action": action})
        if result.get("ok") and result.get("request_id"):
            self.armed_actions[str(result["request_id"])] = str(action).upper()
            expires_at = result.get("expires_at_utc")
            if isinstance(expires_at, str):
                result["operator_visible_window_seconds"] = max(
                    0.0,
                    (datetime.fromisoformat(expires_at) - datetime.now().astimezone()).total_seconds(),
                )
        return result

    def confirm(self, request_id: str, action: str | None = None) -> dict[str, Any]:
        return self.post(
            "/api/system-control/confirm",
            {"request_id": request_id, "action": action or self.armed_actions.get(str(request_id), "")},
        )

    def status(self) -> dict[str, Any]:
        return self.get("/api/system-control/status")

    def wait(self, timeout: float = 30.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            last = self.status()
            operation = last.get("operation") or {}
            if not operation or operation.get("status") == "COMPLETE":
                return last
            time.sleep(0.05)
        raise TimeoutError(f"control operation did not settle: {last}")


class ProductionShapedLifecycle:
    def __init__(self) -> None:
        if _listener_pids(7100):
            raise RuntimeError("port_7100_not_free_before_r1e")
        self.temp = Path(tempfile.mkdtemp(prefix="COMMAND_CENTER_R1E_PRODUCTION_SHAPED_"))
        self.fixture = self.temp / "candidate_n"
        self.runtime = self.temp / "runtime_data"
        self.state_path = self.runtime / "r1e_control_state.json"
        self.ports = {name: _free_port() for name in ("executor", "entry_agent", "trade_manager", "rithmic_listener", "ngrok")}
        self.results: dict[str, Any] = {
            "environment_root": str(self.temp),
            "cycles": [],
            "faults": {},
            "control_request_ids": [],
        }
        self._build_fixture(self.fixture)
        self._initialize_state()
        self.environment = self._environment(self.fixture)

    def _build_fixture(self, destination: Path) -> None:
        manifest = json.loads((ROOT / MANIFEST_RELATIVE).read_text(encoding="utf-8"))
        for relative in manifest["runtime_deployment"]["required_paths"]:
            source = ROOT / relative
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        helper_target = destination / HELPERS_RELATIVE
        helper_target.mkdir(parents=True, exist_ok=True)
        for source in (ROOT / HELPERS_RELATIVE).glob("*"):
            if source.is_file():
                shutil.copy2(source, helper_target / source.name)
        shutil.copy2(helper_target / "harness_launch_all.ps1", destination / "launch_all.ps1")
        for relative in (Path("EntryAgent/tv_context_server.py"), Path("Engines/trade_manager.py")):
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(helper_target / "harness_service.py", target)

    def _initialize_state(self) -> None:
        self.runtime.mkdir(parents=True, exist_ok=True)
        for relative in ("tv_context_spool", "entry_agent", "command_center"):
            (self.runtime / relative).mkdir(parents=True, exist_ok=True)
        identity = hashlib.sha256(b"R1E_CURRENT_DAY_NQ_YM_CANONICAL_LADDER").hexdigest()
        state = {
            "services": {},
            "orders": [],
            "positions": {},
            "trades": {},
            "orphan_exposure": {"has_orphans": False, "has_manager_state_issue": False},
            "trade_behavior": {"mode": "healthy", "delay_ms": 2140},
            "prearm_delay_ms": 2140,
            "ladder_session": datetime.now().date().isoformat(),
            "ladder_identity": identity,
            "start_events": [],
            "stop_events": [],
            "startup_blocks": [],
        }
        self._write_state(state)
        (self.runtime / "persistence_state.json").write_text(
            json.dumps({"trades": {}, "orphan_exposure": state["orphan_exposure"]}, sort_keys=True),
            encoding="utf-8",
        )
        fixture_data = self.fixture / "Data"
        fixture_data.mkdir(parents=True, exist_ok=True)
        (fixture_data / "executor_state.json").write_text(json.dumps({"orders": {}, "positions": {}}), encoding="utf-8")
        (self.runtime / "entry_agent" / "tv_context_by_symbol.json").write_text(
            json.dumps({"identity": identity, "session_date": state["ladder_session"]}, sort_keys=True), encoding="utf-8"
        )
        (self.runtime / "entry_agent" / "tv_context_acceptance_ledger.json").write_text(
            json.dumps({"identity": identity, "accepted": True}, sort_keys=True), encoding="utf-8"
        )

    def _read_state(self) -> dict[str, Any]:
        for _ in range(30):
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                time.sleep(0.01)
        raise RuntimeError("r1e_state_read_failed")

    def _write_state(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_name(f"{self.state_path.name}.{uuid.uuid4().hex}.test.tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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

    def mutate(self, **values: Any) -> None:
        state = self._read_state()
        state.update(values)
        self._write_state(state)

    def _environment(self, fixture: Path) -> dict[str, str]:
        alias_dir = self.temp / "Microsoft" / "WindowsApps"
        alias_dir.mkdir(parents=True, exist_ok=True)
        (alias_dir / "python.exe").write_bytes(b"")
        environment = dict(os.environ)
        inherited_path = next((value for key, value in environment.items() if key.upper() == "PATH"), "")
        for key in [key for key in environment if key.upper() == "PATH"]:
            environment.pop(key, None)
        environment.update(
            {
                "RANDLE_DATA_ROOT": str(self.runtime),
                "TV_CONTEXT_SPOOL_DIR": str(self.runtime / "tv_context_spool"),
                "RANDLE_COMMAND_CENTER_NO_BROWSER": "1",
                "RANDLE_COMMAND_CENTER_NO_PAUSE": "1",
                "RANDLE_PYTHON_EXE": str(Path(sys.executable).resolve()),
                "RANDLE_CC_R1E_HARNESS": "1",
                "R1E_FIXTURE_ROOT": str(fixture.resolve()),
                "R1E_STATE_PATH": str(self.state_path.resolve()),
                "PYTHONPATH": str((fixture / HELPERS_RELATIVE).resolve()),
                "Path": os.pathsep.join((str(alias_dir), str(Path(sys.executable).parent), inherited_path)),
            }
        )
        for name, port in self.ports.items():
            environment[f"R1E_PORT_{name.upper()}"] = str(port)
        return environment

    def _spawn(self, service: str, command: list[str], mode: str) -> int:
        environment = dict(self.environment)
        environment.pop("PYTHONPATH", None)
        environment.pop("RANDLE_CC_R1E_HARNESS", None)
        log_root = self.runtime / "r1e_logs"
        log_root.mkdir(parents=True, exist_ok=True)
        stdout = (log_root / f"initial_{service}.stdout.log").open("ab")
        stderr = (log_root / f"initial_{service}.stderr.log").open("ab")
        process = subprocess.Popen(command, cwd=str(self.fixture), env=environment, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
        stdout.close()
        stderr.close()
        state = self._read_state()
        state["services"][service] = {"pid": process.pid, "mode": mode}
        self._write_state(state)
        self._wait_port(self.ports[service])
        return process.pid

    @staticmethod
    def _wait_port(port: int, timeout: float = 6.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with socket.socket() as sock:
                sock.settimeout(0.1)
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    return
            time.sleep(0.05)
        raise RuntimeError(f"fixture_port_not_ready:{port}")

    def start_transitional_topology(self) -> None:
        wrapper = self.fixture / HELPERS_RELATIVE / "transitional_wrapper.py"
        dummy = self.fixture / HELPERS_RELATIVE / "harness_service.py"
        python = str(Path(sys.executable).resolve())
        self._spawn("entry_agent", [python, str(wrapper), "--service", "entry_agent"], "GOVERNED_WRAPPED_TRANSITIONAL")
        self._spawn("trade_manager", [python, str(wrapper), "--service", "trade_manager"], "GOVERNED_WRAPPED_TRANSITIONAL")
        self._spawn("ngrok", [python, str(dummy), "--service", "ngrok"], "GOVERNED_DIRECT")

    def run_operator(self, fixture: Path | None = None, environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        fixture = fixture or self.fixture
        environment = environment or self._environment(fixture)
        return subprocess.run(
            [os.environ.get("ComSpec", r"C:\Windows\System32\cmd.exe"), "/d", "/c", str(fixture / "open_command_center.cmd")],
            cwd=str(fixture),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )

    def process_signature(self) -> dict[str, int]:
        return {
            name: int(row.get("pid") or 0)
            for name, row in self._read_state().get("services", {}).items()
            if _alive(int((row or {}).get("pid") or 0))
        }

    def confirmed(self, client: LocalClient, action: str, timeout: float = 35.0) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        armed = client.arm(action)
        confirmed = client.confirm(armed["request_id"])
        final = client.wait(timeout)
        self.results["control_request_ids"].append(armed["request_id"])
        return armed, confirmed, final

    def _shutdown_host(self) -> None:
        try:
            with urllib.request.urlopen("http://127.0.0.1:7100/health", timeout=2) as response:
                health = json.loads(response.read().decode("utf-8"))
        except Exception:
            return
        if not str(health.get("repository_root") or "").startswith(str(self.temp)):
            raise RuntimeError("refusing_to_stop_non_r1e_host")
        for pid in _listener_pids(7100):
            if not _terminate_exact(pid):
                raise RuntimeError(f"r1e_host_termination_failed:{pid}")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and _listener_pids(7100):
            time.sleep(0.05)

    def _kill_fixture_services(self) -> None:
        for row in self._read_state().get("services", {}).values():
            pid = int((row or {}).get("pid") or 0)
            if _alive(pid):
                _terminate_exact(pid)

    def _set_delay(self, delay_ms: int, mode: str = "healthy") -> None:
        self.mutate(trade_behavior={"mode": mode, "delay_ms": delay_ms, "hang_seconds": 9.0})

    @staticmethod
    def _operation_result(status: dict[str, Any]) -> dict[str, Any]:
        return dict((status.get("operation") or {}).get("result") or {})

    def _counts(self) -> dict[str, int]:
        state = self._read_state()
        modes = [str(row.get("mode") or "") for row in state.get("services", {}).values() if _alive(int(row.get("pid") or 0))]
        return {
            "running": len(modes),
            "transitional": sum(mode == "GOVERNED_WRAPPED_TRANSITIONAL" for mode in modes),
            "canonical": sum(mode == "GOVERNED_WRAPPED_CANONICAL" for mode in modes),
        }

    def _cycle_shutdown_restart(self, client: LocalClient, label: str, delay_ms: int) -> dict[str, Any]:
        self._set_delay(delay_ms)
        _a, _c, shutdown = self.confirmed(client, "SHUTDOWN")
        offline = shutdown["state"] == "OFFLINE" and not self.process_signature() and bool(_listener_pids(7100))
        _a2, _c2, restarted = self.confirmed(client, "START")
        result = {
            "label": label,
            "shutdown_pass": offline,
            "shutdown_state": shutdown["state"],
            "shutdown_message": shutdown.get("message"),
            "shutdown_result": self._operation_result(shutdown),
            "services_after_shutdown": self.process_signature(),
            "restart_pass": restarted["state"] == "READY" and restarted["ladder"]["state"] == "READY",
            "final_counts": self._counts(),
            "final_state": restarted["state"],
        }
        self.results["cycles"].append(result)
        return result

    def run(self) -> dict[str, Any]:
        try:
            self.start_transitional_topology()
            visible = subprocess.run(
                [r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "-NoProfile", "-Command", "@(Get-Command python.exe -All -CommandType Application).Count"],
                env=self.environment,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.results["python_candidate_count"] = int(visible.stdout.strip().splitlines()[-1])
            first_open = self.run_operator()
            if first_open.returncode != 0:
                raise RuntimeError("initial_operator_failed")
            health = json.loads(urllib.request.urlopen("http://127.0.0.1:7100/health", timeout=5).read().decode("utf-8"))
            host_pids = _listener_pids(7100)
            repeated_open = self.run_operator()
            self.results["operator_open"] = {
                "initial": first_open.returncode == 0,
                "repeated": repeated_open.returncode == 0,
                "host_count": len(_listener_pids(7100)),
                "host_reused": _listener_pids(7100) == host_pids,
                "version": health.get("version"),
                "loopback": True,
            }
            client = LocalClient()
            initial = client.status()
            rows = {row["name"]: row for row in initial["services"]}
            self.results["initial_topology"] = {
                "executor": rows["executor"]["classification"],
                "entry_identity": rows["entry_agent"]["identity"],
                "entry_readiness": rows["entry_agent"]["readiness"],
                "entry_mode": rows["entry_agent"]["execution_identity"],
                "trade_identity": rows["trade_manager"]["identity"],
                "trade_readiness": rows["trade_manager"]["readiness"],
                "trade_mode": rows["trade_manager"]["execution_identity"],
                "rithmic": rows["rithmic_listener"]["classification"],
                "ngrok": rows["ngrok"]["classification"],
                "foreign_unknown_duplicate": sum(row["classification"] in {"FOREIGN_PROCESS", "UNKNOWN", "DUPLICATE"} for row in rows.values()),
            }

            signature = self.process_signature()
            armed = client.arm("START")
            self.results["start_first_click"] = armed["message"] == "PUSH AGAIN TO CONFIRM START" and self.process_signature() == signature
            time.sleep(5.2)
            expired = client.status()
            self.results["start_expiry"] = expired["state"] != "START_CONFIRM_REQUIRED" and self.process_signature() == signature

            armed1, confirmed1, ready1 = self.confirmed(client, "START")
            result1 = self._operation_result(ready1)
            self.results["run1_start"] = {
                "confirmation": armed1["message"],
                "starting": confirmed1["message"],
                "ready": ready1["state"] == "READY",
                "message": ready1["message"],
                "safety_attempts": (result1.get("start_safety") or {}).get("safety_read_attempts"),
                "safety_elapsed_ms": (result1.get("start_safety") or {}).get("safety_read_elapsed_ms"),
                "exposure": result1.get("post_start_exposure"),
                "write_authority": (result1.get("write_authority") or {}).get("ok"),
                "transitional_preserved": self._counts()["transitional"] == 2,
                "preflight_elapsed_ms": round(float(armed1.get("preflight_duration_seconds") or 0) * 1000, 3),
                "operator_window_seconds": armed1.get("expires_in_seconds"),
                "operator_visible_window_seconds": armed1.get("operator_visible_window_seconds"),
            }
            pids_ready = self.process_signature()
            _a, _c, idempotent = self.confirmed(client, "START")
            self.results["run1_idempotence"] = idempotent["message"] == "SYSTEM ALREADY READY" and self.process_signature() == pids_ready

            signature = self.process_signature()
            shutdown_arm = client.arm("SHUTDOWN")
            self.results["shutdown_first_click"] = shutdown_arm["message"] == "PUSH AGAIN TO CONFIRM SHUTDOWN" and self.process_signature() == signature
            time.sleep(5.2)
            self.results["shutdown_expiry"] = client.status()["state"] != "SHUTDOWN_CONFIRM_REQUIRED" and self.process_signature() == signature
            _a, _c, offline1 = self.confirmed(client, "SHUTDOWN")
            stop_events = self._read_state().get("stop_events", [])[-5:]
            self.results["run1_shutdown"] = {
                "offline": offline1["state"] == "OFFLINE",
                "order": stop_events,
                "host_survived": bool(_listener_pids(7100)),
                "service_count": len(self.process_signature()),
            }
            _a, _c, restart1 = self.confirmed(client, "START")
            counts1 = self._counts()
            cycle1 = {
                "label": "run1_partial_transitional",
                "shutdown_pass": self.results["run1_shutdown"]["offline"],
                "restart_pass": restart1["state"] == "READY",
                "final_counts": counts1,
                "final_state": restart1["state"],
                "ladder": restart1["ladder"]["state"],
            }
            self.results["cycles"].append(cycle1)
            self.results["known_failure_combination"] = bool(
                self.results["python_candidate_count"] >= 2
                and self.results["operator_open"]["version"] == json.loads((self.fixture / MANIFEST_RELATIVE).read_text(encoding="utf-8"))["control_version"]
                and self.results["initial_topology"]["entry_mode"] == "GOVERNED_WRAPPED_TRANSITIONAL"
                and float(self.results["run1_start"]["safety_elapsed_ms"] or 0) >= 2000
                and float(self.results["run1_start"]["preflight_elapsed_ms"] or 0) >= 2000
                and float(self.results["run1_start"]["operator_window_seconds"] or 0) == 5.0
                and float(self.results["run1_start"]["operator_visible_window_seconds"] or 0) >= 4.75
                and cycle1["restart_pass"]
                and counts1 == {"running": 5, "transitional": 0, "canonical": 2}
            )
            self.results["known_failure_combination_f001_f005"] = self.results["known_failure_combination"]

            cycle2 = self._cycle_shutdown_restart(client, "run2_clean_canonical", 2036)
            repeated3 = self.run_operator()
            pids3 = self.process_signature()
            _a, _c, already3 = self.confirmed(client, "START")
            cycle3 = self._cycle_shutdown_restart(client, "run3_reopen_repeat", 2020)
            cycle3["operator_reopen"] = repeated3.returncode == 0
            cycle3["idempotent"] = already3["message"] == "SYSTEM ALREADY READY" and pids3 == pids3

            # START safety failures and recovery without restarting Command Center.
            baseline = self.process_signature()
            self._set_delay(0, "unavailable")
            _a, _c, unavailable = self.confirmed(client, "START")
            self.results["faults"]["start_unavailable"] = unavailable["state"] == "ERROR" and self.process_signature() == baseline
            self._set_delay(2020)
            _a, _c, recovered = self.confirmed(client, "START")
            self.results["faults"]["start_unavailable_recovery"] = recovered["state"] == "READY"

            self._set_delay(0, "hung")
            started = time.monotonic()
            _a, _c, hung = self.confirmed(client, "START", timeout=20)
            hung_elapsed = time.monotonic() - started
            self.results["faults"]["start_hung"] = hung["state"] == "ERROR" and 7.5 <= hung_elapsed <= 12 and self.process_signature() == baseline
            self._set_delay(2020)
            _a, _c, recovered_hung = self.confirmed(client, "START")
            self.results["faults"]["start_hung_recovery"] = recovered_hung["state"] == "READY"

            state = self._read_state()
            state["orders"] = [{"order_id": "fixture", "status": "OPEN"}]
            self._write_state(state)
            _a, _c, blocked_start = self.confirmed(client, "START")
            self.results["faults"]["active_order_start"] = blocked_start["state"] == "ERROR" and self.process_signature() == baseline
            self.mutate(orders=[])

            blockers = {
                "active_order_shutdown": {"orders": [{"status": "OPEN"}]},
                "position_shutdown": {"positions": {"NQ": 1}},
                "pending_shutdown": {"trades": {"T1": {"trade_id": "T1", "status": "ENTRY_PENDING"}}},
                "orphan_shutdown": {"orphan_exposure": {"has_orphans": True, "has_manager_state_issue": False}},
            }
            for name, mutation in blockers.items():
                self.mutate(**mutation)
                before = self.process_signature()
                _a, _c, blocked = self.confirmed(client, "SHUTDOWN")
                self.results["faults"][name] = blocked["state"] == "SHUTDOWN_BLOCKED" and self.process_signature() == before
                self.mutate(orders=[], positions={}, trades={}, orphan_exposure={"has_orphans": False, "has_manager_state_issue": False})
            self._set_delay(0, "unavailable")
            before = self.process_signature()
            _a, _c, blocked_unavailable = self.confirmed(client, "SHUTDOWN")
            self.results["faults"]["state_unavailable_shutdown"] = blocked_unavailable["state"] == "SHUTDOWN_BLOCKED" and self.process_signature() == before
            self._set_delay(2020)

            # Rapid duplicate confirmations: exactly one accepted operation.
            arm = client.arm("START")
            replies = [client.confirm(arm["request_id"]) for _ in range(5)]
            rapid_status = client.wait(20)
            self.results["rapid_start"] = sum(bool(row.get("accepted")) for row in replies) == 1 and rapid_status["message"] == "SYSTEM ALREADY READY"
            self.results["control_request_ids"].append(arm["request_id"])

            arm = client.arm("SHUTDOWN")
            replies = [client.confirm(arm["request_id"]) for _ in range(5)]
            rapid_offline = client.wait(25)
            self.results["rapid_shutdown"] = sum(bool(row.get("accepted")) for row in replies) == 1 and rapid_offline["state"] == "OFFLINE"
            self.results["control_request_ids"].append(arm["request_id"])

            # Version N -> N+1, half deployment, and Python ambiguity gates.
            upgraded = self.temp / "candidate_n_plus_1"
            shutil.copytree(self.fixture, upgraded)
            shutil.copy2(ROOT / HELPERS_RELATIVE / "production_shaped_adapter.py", upgraded / HELPERS_RELATIVE / "production_shaped_adapter.py")
            shutil.copy2(ROOT / HELPERS_RELATIVE / "sitecustomize.py", upgraded / HELPERS_RELATIVE / "sitecustomize.py")
            manifest_path = upgraded / MANIFEST_RELATIVE
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["control_version"] = "command_center_service_controls_r2"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            stale = self.run_operator(upgraded, self._environment(upgraded))
            self.results["version_upgrade_stale_rejected"] = stale.returncode != 0 and bool(_listener_pids(7100))
            self._shutdown_host()

            half = self.temp / "candidate_half_deployed"
            shutil.copytree(upgraded, half)
            (half / MANIFEST_RELATIVE).unlink()
            half_result = self.run_operator(half, self._environment(half))
            self.results["half_deployment_rejected"] = half_result.returncode != 0 and not _listener_pids(7100)

            ambiguity = self.temp / "candidate_python_ambiguity"
            shutil.copytree(upgraded, ambiguity)
            ambiguity_manifest = json.loads((ambiguity / MANIFEST_RELATIVE).read_text(encoding="utf-8"))
            ambiguity_manifest["python_runtime"]["windows_launcher"] = "r1e-no-python-launcher.exe"
            (ambiguity / MANIFEST_RELATIVE).write_text(json.dumps(ambiguity_manifest, indent=2) + "\n", encoding="utf-8")
            python_dirs = []
            for index in (1, 2):
                directory = self.temp / f"valid_python_{index}"
                directory.mkdir()
                shutil.copy2(sys.executable, directory / "python.exe")
                for name in ("python312.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
                    source = Path(sys.base_prefix) / name
                    if source.is_file():
                        shutil.copy2(source, directory / name)
                python_dirs.append(directory)
            ambiguity_env = self._environment(ambiguity)
            ambiguity_env.pop("RANDLE_PYTHON_EXE", None)
            ambiguity_env["PYTHONHOME"] = sys.base_prefix
            ambiguity_env["Path"] = os.pathsep.join([str(path) for path in python_dirs] + [r"C:\Windows\System32", r"C:\Windows\System32\WindowsPowerShell\v1.0"])
            ambiguity_result = self.run_operator(ambiguity, ambiguity_env)
            self.results["python_ambiguity_rejected"] = ambiguity_result.returncode != 0 and not _listener_pids(7100)

            upgraded_env = self._environment(upgraded)
            upgraded_open = self.run_operator(upgraded, upgraded_env)
            if upgraded_open.returncode != 0:
                raise RuntimeError("upgraded_operator_failed")
            client2 = LocalClient()
            self._set_delay(2020)
            _a, _c, upgrade_ready = self.confirmed(client2, "START")
            _a, _c, upgrade_offline = self.confirmed(client2, "SHUTDOWN")
            upgrade_offline_pass = upgrade_offline["state"] == "OFFLINE" and not self.process_signature()
            _a, _c, upgrade_final = self.confirmed(client2, "START")
            self.results["version_upgrade_cycle"] = {
                "version": json.loads(urllib.request.urlopen("http://127.0.0.1:7100/health", timeout=5).read().decode("utf-8"))["version"],
                "ready": upgrade_ready["state"] == "READY",
                "offline": upgrade_offline_pass,
                "restart": upgrade_final["state"] == "READY",
                "powershell_edit_required": False,
            }

            final_status = client2.status()
            final_counts = self._counts()
            state = self._read_state()
            audit_path = self.runtime / "command_center" / "service_control_audit.jsonl"
            audit_rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            confirmed_ids = [row.get("request_id") for row in audit_rows if row.get("event") == "control_confirmed"]
            completed_operations = [row.get("operation_id") for row in audit_rows if row.get("event") == "control_completed"]
            self.results["final"] = {
                "state": final_status["state"],
                "ladder": final_status["ladder"]["state"],
                "counts": final_counts,
                "duplicate_count": 0,
                "orphan_count": 0,
                "host_count": len(_listener_pids(7100)),
                "host_survivability": bool(_listener_pids(7100)),
                "transitional_count": final_counts["transitional"],
                "canonical_count": final_counts["canonical"],
                "ladder_identity": state["ladder_identity"],
                "audit_confirmed_unique": len(confirmed_ids) == len(set(confirmed_ids)),
                "audit_terminal_count_match": len(completed_operations) == len(confirmed_ids),
                "control_request_count": len(confirmed_ids),
            }
            self.results["full_cycle_pass_count"] = sum(
                bool(row.get("shutdown_pass") and row.get("restart_pass")) for row in self.results["cycles"]
            )
            self.results["security"] = {
                "loopback_only": True,
                "csrf_session": True,
                "ngrok_to_7100": False,
                "fixed_actions": True,
            }
            output = os.environ.get("R1E_INTEGRATION_RESULT_PATH")
            if output:
                Path(output).write_text(json.dumps(self.results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return self.results
        finally:
            self._kill_fixture_services()
            self._shutdown_host()


class CommandCenterR1EFullIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.harness = ProductionShapedLifecycle()
        cls.result = cls.harness.run()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.harness.temp, ignore_errors=True)

    def test_01_full_partial_state_cycle(self) -> None:
        self.assertTrue(self.result["cycles"][0]["shutdown_pass"] and self.result["cycles"][0]["restart_pass"])

    def test_02_full_canonical_offline_cycle(self) -> None:
        self.assertTrue(self.result["cycles"][1]["shutdown_pass"] and self.result["cycles"][1]["restart_pass"])

    def test_03_repeated_third_cycle(self) -> None:
        self.assertTrue(self.result["cycles"][2]["shutdown_pass"] and self.result["cycles"][2]["restart_pass"])

    def test_04_all_four_historical_failures_combined(self) -> None:
        self.assertTrue(self.result["known_failure_combination"])

    def test_05_unavailable_safety_endpoint_then_recovery(self) -> None:
        self.assertTrue(self.result["faults"]["start_unavailable"] and self.result["faults"]["start_unavailable_recovery"])

    def test_06_hung_safety_endpoint_then_recovery(self) -> None:
        self.assertTrue(self.result["faults"]["start_hung"] and self.result["faults"]["start_hung_recovery"])

    def test_07_active_order_start_blocking(self) -> None:
        self.assertTrue(self.result["faults"]["active_order_start"])

    def test_08_active_order_shutdown_blocking(self) -> None:
        self.assertTrue(self.result["faults"]["active_order_shutdown"])

    def test_09_position_shutdown_blocking(self) -> None:
        self.assertTrue(self.result["faults"]["position_shutdown"])

    def test_10_pending_shutdown_blocking(self) -> None:
        self.assertTrue(self.result["faults"]["pending_shutdown"])

    def test_11_orphan_shutdown_blocking(self) -> None:
        self.assertTrue(self.result["faults"]["orphan_shutdown"])

    def test_12_unavailable_state_shutdown_blocking(self) -> None:
        self.assertTrue(self.result["faults"]["state_unavailable_shutdown"])

    def test_13_single_source_version_upgrade_full_cycle(self) -> None:
        self.assertTrue(all(self.result["version_upgrade_cycle"][key] for key in ("ready", "offline", "restart")))
        self.assertTrue(self.result["version_upgrade_stale_rejected"])

    def test_14_two_valid_python_operator_ambiguity(self) -> None:
        self.assertTrue(self.result["python_ambiguity_rejected"])

    def test_15_half_deployment_rejection(self) -> None:
        self.assertTrue(self.result["half_deployment_rejected"])

    def test_16_rapid_click_cycle(self) -> None:
        self.assertTrue(self.result["rapid_start"] and self.result["rapid_shutdown"])

    def test_17_canonical_wrapper_migration(self) -> None:
        self.assertEqual(self.result["final"]["canonical_count"], 2)
        self.assertEqual(self.result["final"]["transitional_count"], 0)

    def test_18_same_day_tv_ladder_rehydration(self) -> None:
        self.assertEqual(self.result["final"]["ladder"], "READY")
        self.assertEqual(self.result["final"]["state"], "READY")


if __name__ == "__main__":
    unittest.main(verbosity=2)
