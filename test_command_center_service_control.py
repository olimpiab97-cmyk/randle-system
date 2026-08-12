from __future__ import annotations

import http.client
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from command_center_host import CommandCenterApplication, CommandCenterServer
from command_center_service_control import ControlManager, ProductionServiceAdapter, ServiceClassification, load_service_manifest


ROOT = Path(__file__).resolve().parent
DUMMY = ROOT / "tests" / "fixtures" / "command_center" / "dummy_service.py"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class IsolatedServiceAdapter:
    NAMES = ("executor", "entry_agent", "trade_manager", "rithmic_listener", "ngrok")
    SHUTDOWN_ORDER = ("ngrok", "rithmic_listener", "trade_manager", "entry_agent", "executor")

    def __init__(self, root: Path):
        self.root = root
        self.ports = {name: free_port() for name in self.NAMES}
        self.processes: dict[str, subprocess.Popen] = {}
        self.start_events: list[str] = []
        self.stop_events: list[str] = []
        self.start_attempts = 0
        self.forced_classification: dict[str, str] = {}
        self.active_orders = 0
        self.nonzero_positions = 0
        self.pending_actions = 0
        self.write_authority_ok = True
        self.ladder = {"state": "WAITING", "label": "TV LADDER — WAITING FOR CURRENT SESSION"}

    def _ready(self, name: str) -> bool:
        process = self.processes.get(name)
        if not process or process.poll() is not None:
            return False
        try:
            connection = http.client.HTTPConnection("127.0.0.1", self.ports[name], timeout=0.2)
            connection.request("GET", "/health")
            response = connection.getresponse()
            response.read()
            connection.close()
            return response.status == 200
        except OSError:
            return False

    def snapshot(self):
        rows = []
        for index, name in enumerate(self.NAMES, 1):
            forced = self.forced_classification.get(name)
            ready = self._ready(name)
            classification = forced or (ServiceClassification.RUNNING_READY.value if ready else ServiceClassification.STOPPED.value)
            process = self.processes.get(name)
            rows.append({
                "name": name,
                "display_name": name.replace("_", " ").upper(),
                "classification": classification,
                "reason": "isolated_test",
                "pids": [process.pid] if ready and process else [],
                "port": self.ports[name],
                "start_order": index,
                "shutdown_order": 6 - index,
            })
        return {"captured_at": "isolated", "services": rows}

    def write_authority(self):
        if not self.write_authority_ok:
            return {"ok": False, "roots": {"spool": {"ok": False, "reason": "PermissionError"}}}
        results = {}
        for name in ("spool", "entry_agent", "runtime"):
            path = self.root / name
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".probe"
            probe.write_text("ok", encoding="utf-8")
            ok = probe.read_text(encoding="utf-8") == "ok"
            probe.unlink()
            results[name] = {"ok": ok}
        return {"ok": all(row["ok"] for row in results.values()), "roots": results}

    def _spawn(self, name: str):
        process = subprocess.Popen(
            [sys.executable, str(DUMMY), "--port", str(self.ports[name]), "--name", name],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.processes[name] = process
        self.start_events.append(name)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not self._ready(name):
            time.sleep(0.01)
        if not self._ready(name):
            raise RuntimeError(f"dummy service not ready: {name}")

    def start_stack(self):
        self.start_attempts += 1
        before = self.snapshot()
        values = {row["classification"] for row in before["services"]}
        if values == {ServiceClassification.RUNNING_READY.value}:
            return {"ok": True, "already_ready": True, "message": "SYSTEM ALREADY READY", "snapshot": before}
        unsafe = values.intersection({ServiceClassification.DUPLICATE.value, ServiceClassification.FOREIGN_PROCESS.value, ServiceClassification.UNKNOWN.value, ServiceClassification.RUNNING_NOT_READY.value})
        if unsafe:
            return {"ok": False, "message": "SYSTEM NOT READY", "reason": "unsafe_partial_runtime", "snapshot": before}
        probe = self.write_authority()
        if not probe["ok"]:
            return {"ok": False, "message": "SYSTEM NOT READY", "reason": "write_authority"}
        for name in self.NAMES:
            if not self._ready(name):
                self._spawn(name)
        return {"ok": True, "already_ready": False, "message": "SYSTEM READY", "snapshot": self.snapshot(), "write_authority": probe}

    def trading_safety(self):
        safe = self.active_orders == self.nonzero_positions == self.pending_actions == 0
        return {
            "ok": True,
            "safe": safe,
            "reason": "zero_exposure" if safe else "active_trading_state",
            "active_orders": self.active_orders,
            "nonzero_positions": self.nonzero_positions,
            "pending_executable_actions": self.pending_actions,
            "blocking_categories": [
                label for label, value in (
                    ("ACTIVE_ORDERS", self.active_orders),
                    ("NONZERO_POSITIONS", self.nonzero_positions),
                    ("PENDING_EXECUTABLE_ACTIONS", self.pending_actions),
                ) if value
            ],
        }

    def shutdown_stack(self):
        safety = self.trading_safety()
        if not safety["safe"]:
            return {"ok": False, "blocked": True, "message": "SHUTDOWN BLOCKED — ACTIVE TRADING STATE", "safety": safety, "stopped": []}
        for name in self.SHUTDOWN_ORDER:
            process = self.processes.get(name)
            if process and process.poll() is None:
                process.terminate()
                process.wait(timeout=3)
                self.stop_events.append(name)
        return {"ok": True, "blocked": False, "message": "SYSTEM OFFLINE", "safety": safety, "stopped": list(self.stop_events), "snapshot": self.snapshot()}

    def ladder_status(self):
        return dict(self.ladder)

    def cleanup(self):
        for process in self.processes.values():
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=3)


class CommandCenterServiceControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="command-center-r1-")
        self.root = Path(self.temp.name)
        self.adapter = IsolatedServiceAdapter(self.root)
        self.manager = ControlManager(self.adapter, self.root / "audit.jsonl", confirmation_window=0.12)

    def tearDown(self):
        self.adapter.cleanup()
        self.temp.cleanup()

    def confirm(self, action: str):
        armed = self.manager.arm(action)
        self.assertTrue(armed["ok"])
        confirmed = self.manager.confirm(armed["request_id"])
        self.assertTrue(confirmed["ok"])
        return self.manager.wait_for_idle(10)

    def test_manifest_matches_canonical_launcher_and_dependency_orders(self):
        manifest = load_service_manifest(ROOT)
        self.assertEqual(manifest["canonical_launcher"], "launch_all.ps1")
        services = manifest["services"]
        self.assertEqual([row["name"] for row in sorted(services, key=lambda row: row["start_order"])], list(IsolatedServiceAdapter.NAMES))
        self.assertEqual([row["name"] for row in sorted(services, key=lambda row: row["shutdown_order"])], list(IsolatedServiceAdapter.SHUTDOWN_ORDER))
        launcher = (ROOT / "launch_all.ps1").read_text(encoding="utf-8-sig")
        orchestration = launcher[launcher.index("try {", launcher.index("STARTUP_BEGIN")):]
        ordered_calls = ["Ensure-Executor", "Ensure-EntryAgentAndRelay", "Ensure-TradeManager", "Ensure-ListenerBridge", "Ensure-Ngrok"]
        offsets = [orchestration.index(call) for call in ordered_calls]
        self.assertEqual(offsets, sorted(offsets))

    def test_start_requires_second_confirmation_and_expiration_starts_nothing(self):
        armed = self.manager.arm("START")
        self.assertEqual(armed["message"], "PUSH AGAIN TO CONFIRM START")
        self.assertFalse(self.adapter.processes)
        time.sleep(0.14)
        self.manager.expire_arms()
        self.assertEqual(self.manager.status()["state"], "OFFLINE")
        self.assertFalse(self.adapter.processes)

    def test_confirmed_start_is_exact_once_idempotent_and_repairs_safe_partial(self):
        status = self.confirm("START")
        self.assertEqual(status["state"], "READY")
        self.assertEqual(status["message"], "SYSTEM SERVICES READY — WAITING FOR 06:15 TV LADDER")
        self.assertEqual(self.adapter.start_events, list(IsolatedServiceAdapter.NAMES))
        pids = {name: process.pid for name, process in self.adapter.processes.items()}
        attempts = self.adapter.start_attempts
        status = self.confirm("START")
        self.assertEqual(status["message"], "SYSTEM ALREADY READY")
        self.assertEqual({name: process.pid for name, process in self.adapter.processes.items()}, pids)
        self.assertEqual(self.adapter.start_attempts, attempts + 1)
        self.adapter.processes["ngrok"].terminate()
        self.adapter.processes["ngrok"].wait(timeout=3)
        status = self.confirm("START")
        self.assertEqual(status["state"], "READY")
        self.assertNotEqual(self.adapter.processes["ngrok"].pid, pids["ngrok"])
        self.assertEqual(sum(1 for process in self.adapter.processes.values() if process.poll() is None), 5)

    def test_current_day_ladder_stale_projects_degraded_without_restarting_services(self):
        self.confirm("START")
        self.adapter.ladder = {"state": "STALE", "label": "TV LADDER — STALE"}
        status = self.manager.status()
        self.assertEqual(status["state"], "DEGRADED")
        self.assertEqual(status["message"], "SYSTEM DEGRADED — TV LADDER STALE")
        pids = {name: process.pid for name, process in self.adapter.processes.items()}
        self.assertEqual(self.confirm("START")["message"], "SYSTEM DEGRADED — TV LADDER STALE")
        self.assertEqual({name: process.pid for name, process in self.adapter.processes.items()}, pids)

    def test_ready_status_follows_runtime_drift_instead_of_caching_success(self):
        self.assertEqual(self.confirm("START")["state"], "READY")
        self.adapter.processes["ngrok"].terminate()
        self.adapter.processes["ngrok"].wait(timeout=3)
        status = self.manager.status()
        self.assertEqual(status["state"], "DEGRADED")
        self.assertEqual(status["message"], "SYSTEM DEGRADED")

    def test_duplicate_or_foreign_partial_runtime_fails_closed(self):
        self.adapter.forced_classification["trade_manager"] = ServiceClassification.DUPLICATE.value
        status = self.confirm("START")
        self.assertEqual(status["state"], "ERROR")
        self.assertEqual(status["message"], "SYSTEM NOT READY")
        self.assertFalse(self.adapter.processes)

    def test_write_restricted_start_fails_before_any_process_creation(self):
        self.adapter.write_authority_ok = False
        status = self.confirm("START")
        self.assertEqual(status["state"], "ERROR")
        self.assertEqual(status["message"], "SYSTEM NOT READY")
        self.assertFalse(self.adapter.processes)

    def test_production_inventory_rejects_source_mismatched_process(self):
        adapter = ProductionServiceAdapter(ROOT)
        adapter._readiness_ok = lambda spec: (True, "test_ready")
        adapter._port_owners = lambda: {6001: [123], 7001: [], 7002: [], 4040: []}
        adapter._process_inventory = lambda: [{
            "ProcessId": 123,
            "Name": "python.exe",
            "CommandLine": r'python.exe "C:\\foreign\\executor.py"',
        }]
        executor = next(row for row in adapter.snapshot()["services"] if row["name"] == "executor")
        self.assertEqual(executor["classification"], ServiceClassification.FOREIGN_PROCESS.value)

        expected_executor_path = ROOT / "executor.py"
        adapter._process_inventory = lambda: [{
            "ProcessId": 123,
            "Name": "python.exe",
            "CommandLine": f'python.exe "{expected_executor_path}"',
        }]
        executor = next(row for row in adapter.snapshot()["services"] if row["name"] == "executor")
        self.assertEqual(executor["classification"], ServiceClassification.RUNNING_READY.value)

    def test_production_shutdown_safety_fails_closed_on_endpoint_or_schema_error(self):
        adapter = ProductionServiceAdapter(ROOT)
        healthy = {
            "/orders": {"ok": True, "orders": []},
            "/positions": {"ok": True, "positions": {}},
            "/trades": {"ok": True, "trades": {}, "orphan_exposure": {"has_orphans": False, "has_manager_state_issue": False}},
        }
        adapter._safety_json_get_result = lambda url, deadline=None: {
            "ok": True,
            "payload": healthy[next(path for path in healthy if url.endswith(path))],
            "status": 200,
            "reason": "isolated_fixture",
            "attempts": 1,
            "elapsed_ms": 0,
        }
        self.assertTrue(adapter.trading_safety()["safe"])
        healthy["/orders"] = {"ok": False, "orders": []}
        self.assertFalse(adapter.trading_safety()["safe"])
        healthy["/orders"] = {"ok": True, "orders": {}}
        result = adapter.trading_safety()
        self.assertFalse(result["safe"])
        self.assertEqual(result["reason"], "trading_state_schema_invalid")

    def test_shutdown_blocks_each_active_trading_category_without_stopping(self):
        self.confirm("START")
        original_pids = {name: process.pid for name, process in self.adapter.processes.items()}
        for field in ("active_orders", "nonzero_positions", "pending_actions"):
            setattr(self.adapter, field, 1)
            status = self.confirm("SHUTDOWN")
            self.assertEqual(status["state"], "SHUTDOWN_BLOCKED")
            self.assertEqual(status["message"], "SHUTDOWN BLOCKED — ACTIVE TRADING STATE")
            self.assertEqual({name: process.pid for name, process in self.adapter.processes.items()}, original_pids)
            self.assertTrue(all(process.poll() is None for process in self.adapter.processes.values()))
            setattr(self.adapter, field, 0)

    def test_safe_shutdown_order_host_survival_and_restart(self):
        self.confirm("START")
        status = self.confirm("SHUTDOWN")
        self.assertEqual(status["state"], "OFFLINE")
        self.assertEqual(self.adapter.stop_events, list(IsolatedServiceAdapter.SHUTDOWN_ORDER))
        self.assertTrue(all(process.poll() is not None for process in self.adapter.processes.values()))
        for port in self.adapter.ports.values():
            with socket.socket() as sock:
                self.assertEqual(sock.connect_ex(("127.0.0.1", port)), 10061)
        self.assertEqual(self.confirm("START")["state"], "READY")

    def test_production_shutdown_adapter_stops_disposable_processes_in_manifest_order(self):
        for name in self.adapter.NAMES:
            self.adapter._spawn(name)
        adapter = ProductionServiceAdapter(ROOT)
        adapter.snapshot = self.adapter.snapshot
        adapter.trading_safety = self.adapter.trading_safety
        adapter.protected_state_hashes = lambda: {"isolated_state": "unchanged"}
        stop_order = []
        def tracked_stop(pid):
            name = next(name for name, process in self.adapter.processes.items() if process.pid == pid)
            stop_order.append(name)
            process = self.adapter.processes[name]
            process.terminate()
            process.wait(timeout=3)
            return True

        adapter._stop_pid = tracked_stop
        result = adapter.shutdown_stack()
        self.assertTrue(result["ok"], result)
        self.assertEqual(stop_order, list(IsolatedServiceAdapter.SHUTDOWN_ORDER))
        self.assertTrue(result["protected_state_unchanged"])
        self.assertTrue(all(process.poll() is not None for process in self.adapter.processes.values()))

    def test_production_pid_terminator_is_fixed_and_escalates_only_to_force(self):
        adapter = ProductionServiceAdapter(ROOT)
        graceful = subprocess.CompletedProcess([], 1, "", "graceful unavailable")
        forced = subprocess.CompletedProcess([], 0, "terminated", "")
        with patch("command_center_service_control.subprocess.run", side_effect=[graceful, forced]) as run:
            self.assertTrue(adapter._stop_pid(12345))
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0], ["taskkill.exe", "/PID", "12345", "/T"])
        self.assertEqual(run.call_args_list[1].args[0], ["taskkill.exe", "/PID", "12345", "/T", "/F"])
        self.assertTrue(all(call.kwargs["shell"] is False for call in run.call_args_list))

    def test_command_center_http_host_survives_stack_shutdown_and_restart(self):
        application = CommandCenterApplication(ROOT, self.manager)
        server = CommandCenterServer(("127.0.0.1", 0), application)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.confirm("START")
            self.assertEqual(self.confirm("SHUTDOWN")["state"], "OFFLINE")
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            connection.request("GET", "/health")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertTrue(json.loads(response.read().decode("utf-8"))["ok"])
            connection.close()
            self.assertEqual(self.confirm("START")["state"], "READY")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_rapid_confirmation_is_one_operation_and_no_duplicate_processes(self):
        armed = self.manager.arm("START")
        results = []
        barrier = threading.Barrier(5)

        def worker():
            barrier.wait()
            results.append(self.manager.confirm(armed["request_id"]))

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.manager.wait_for_idle(10)
        self.assertEqual(sum(1 for row in results if row.get("accepted")), 1)
        self.assertEqual(self.adapter.start_attempts, 1)
        self.assertEqual(sum(1 for process in self.adapter.processes.values() if process.poll() is None), 5)

    def test_ui_contract_and_local_host_security(self):
        html = (ROOT / "command_center.html").read_text(encoding="utf-8")
        for text in ("START SYSTEM", "PUSH AGAIN TO CONFIRM START", "SHUTDOWN SYSTEM", "PUSH AGAIN TO CONFIRM SHUTDOWN", "SHUTDOWN BLOCKED — ACTIVE TRADING STATE"):
            self.assertIn(text, html)
        self.assertIn('RUNNING_READY: "READY"', html)
        self.assertIn('STOPPED: "OFFLINE"', html)
        application = CommandCenterApplication(ROOT, self.manager)
        server = CommandCenterServer(("127.0.0.1", 0), application)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_port
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            connection.request("GET", "/")
            response = connection.getresponse()
            page = response.read().decode("utf-8")
            cookie = response.getheader("Set-Cookie").split(";", 1)[0]
            token = page.split('const COMMAND_CENTER_CSRF = "', 1)[1].split('";', 1)[0]
            connection.close()
            # BaseHTTPRequestHandler serves HTTP/1.0 and may close the socket
            # after each response.  Use a fresh client connection for each
            # security assertion so the regression is transport-deterministic.
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            connection.request("POST", "/api/system-control/arm", body=json.dumps({"action": "START"}), headers={"Content-Type": "application/json"})
            denied = connection.getresponse()
            self.assertEqual(denied.status, 403)
            denied.read()
            connection.close()
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            connection.request("POST", "/api/system-control/arm", body=json.dumps({"action": "START"}), headers={"Content-Type": "application/json", "Cookie": cookie, "Origin": f"http://127.0.0.1:{port}", "X-Command-Center-CSRF": token})
            accepted = connection.getresponse()
            payload = json.loads(accepted.read().decode("utf-8"))
            self.assertEqual(accepted.status, 200)
            self.assertEqual(payload["message"], "PUSH AGAIN TO CONFIRM START")
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
