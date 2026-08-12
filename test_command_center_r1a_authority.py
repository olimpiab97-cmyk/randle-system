from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import command_center_service_launcher as service_launcher
from command_center_service_control import (
    ProductionServiceAdapter,
    ServiceClassification,
    ServiceIdentity,
    ServiceReadiness,
)


ROOT = Path(__file__).resolve().parent


def snapshot_rows(classification: str) -> dict:
    return {
        "captured_at": "isolated",
        "services": [
            {
                "name": name,
                "display_name": name.upper(),
                "identity": ServiceIdentity.TRUSTED.value,
                "readiness": ServiceReadiness.STOPPED.value if classification == ServiceClassification.STOPPED.value else ServiceReadiness.READY.value,
                "classification": classification,
                "pids": [],
            }
            for name in ("executor", "entry_agent", "trade_manager", "rithmic_listener", "ngrok")
        ],
    }


class CommandCenterR1AAuthorityTests(unittest.TestCase):
    def adapter_for_identity(self) -> ProductionServiceAdapter:
        adapter = ProductionServiceAdapter(ROOT)
        adapter._readiness_ok = lambda spec: (True, "isolated_ready")
        adapter._port_owners = lambda: {6001: [], 7002: [123], 7001: [], 4040: []}
        return adapter

    @staticmethod
    def canonical_entry_process(pid: int = 123) -> dict:
        wrapper = ROOT / "command_center_service_launcher.py"
        return {"ProcessId": pid, "ParentProcessId": 1, "Name": "python.exe", "ExecutablePath": "python.exe", "CommandLine": f'python.exe "{wrapper}" --service entry_agent'}

    def replace_entry_identity(self, adapter: ProductionServiceAdapter, mutate) -> None:
        services = []
        for spec in adapter.services:
            if spec.name != "entry_agent":
                services.append(spec)
                continue
            identities = [dict(row) for row in spec.execution_identities]
            mutate(identities[0])
            services.append(replace(spec, execution_identities=tuple(identities)))
        adapter.services = services

    def test_canonical_wrapped_identity_is_trusted_and_ready(self):
        adapter = self.adapter_for_identity()
        adapter._process_inventory = lambda: [self.canonical_entry_process()]
        row = next(row for row in adapter.snapshot()["services"] if row["name"] == "entry_agent")
        self.assertEqual(row["identity"], ServiceIdentity.TRUSTED.value)
        self.assertEqual(row["readiness"], ServiceReadiness.READY.value)
        self.assertEqual(row["execution_identity"], "GOVERNED_WRAPPED")

    def test_wrapper_hash_mismatch_is_foreign(self):
        adapter = self.adapter_for_identity()
        self.replace_entry_identity(adapter, lambda row: row.__setitem__("wrapper_sha256", "0" * 64))
        adapter._process_inventory = lambda: [self.canonical_entry_process()]
        row = next(row for row in adapter.snapshot()["services"] if row["name"] == "entry_agent")
        self.assertEqual(row["identity"], ServiceIdentity.FOREIGN.value)
        self.assertEqual(row["classification"], ServiceClassification.FOREIGN_PROCESS.value)

    def test_child_source_mismatch_is_foreign(self):
        adapter = self.adapter_for_identity()
        self.replace_entry_identity(adapter, lambda row: row.__setitem__("service_source_sha256", "0" * 64))
        adapter._process_inventory = lambda: [self.canonical_entry_process()]
        row = next(row for row in adapter.snapshot()["services"] if row["name"] == "entry_agent")
        self.assertEqual(row["classification"], ServiceClassification.FOREIGN_PROCESS.value)

    def test_wrapper_absent_direct_child_is_foreign(self):
        adapter = self.adapter_for_identity()
        source = ROOT / "EntryAgent" / "tv_context_server.py"
        adapter._process_inventory = lambda: [{"ProcessId": 123, "Name": "python.exe", "CommandLine": f'python.exe "{source}"'}]
        row = next(row for row in adapter.snapshot()["services"] if row["name"] == "entry_agent")
        self.assertEqual(row["classification"], ServiceClassification.FOREIGN_PROCESS.value)

    def test_mixed_wrapper_and_direct_is_duplicate(self):
        adapter = self.adapter_for_identity()
        source = ROOT / "EntryAgent" / "tv_context_server.py"
        adapter._process_inventory = lambda: [
            self.canonical_entry_process(123),
            {"ProcessId": 124, "Name": "python.exe", "CommandLine": f'python.exe "{source}"'},
        ]
        row = next(row for row in adapter.snapshot()["services"] if row["name"] == "entry_agent")
        self.assertEqual(row["classification"], ServiceClassification.DUPLICATE.value)

    def test_direct_executor_identity_remains_governed(self):
        adapter = ProductionServiceAdapter(ROOT)
        source = ROOT / "executor.py"
        adapter._process_inventory = lambda: [{"ProcessId": 321, "Name": "python.exe", "CommandLine": f'python.exe "{source}"'}]
        adapter._port_owners = lambda: {6001: [321], 7002: [], 7001: [], 4040: []}
        adapter._readiness_ok = lambda spec: (True, "isolated_ready")
        row = next(row for row in adapter.snapshot()["services"] if row["name"] == "executor")
        self.assertEqual(row["identity"], ServiceIdentity.TRUSTED.value)
        self.assertEqual(row["execution_identity"], "GOVERNED_DIRECT")

    def test_entry_503_is_trusted_not_ready_with_dependency_reason(self):
        adapter = self.adapter_for_identity()
        adapter._readiness_ok = ProductionServiceAdapter._readiness_ok.__get__(adapter)
        adapter._process_inventory = lambda: [self.canonical_entry_process()]
        adapter._json_get_result = lambda url, timeout=None: (503, {"service_status": "REHYDRATING", "rehydration_failures": [{"symbol": "NQ", "reason": "canonical_completed_candle_unavailable"}]})
        row = next(row for row in adapter.snapshot()["services"] if row["name"] == "entry_agent")
        self.assertEqual(row["identity"], ServiceIdentity.TRUSTED.value)
        self.assertEqual(row["readiness"], ServiceReadiness.NOT_READY.value)
        self.assertIn("canonical_completed_candle_unavailable", row["reason"])

    def test_stopped_executor_start_gate_uses_persisted_state_not_live_executor(self):
        adapter = ProductionServiceAdapter(ROOT)
        with tempfile.TemporaryDirectory(prefix="r1a-start-gate-") as directory:
            root = Path(directory)
            (root / "persistence_state.json").write_text(json.dumps({"trades": {}, "system": {}}), encoding="utf-8")
            before = snapshot_rows(ServiceClassification.STOPPED.value)
            with patch.dict(os.environ, {"RANDLE_DATA_ROOT": str(root)}):
                result = adapter.start_safety(before)
        self.assertTrue(result["safe"], result)
        self.assertEqual(result["authority"], "persisted_start_gate_only")

    def test_stopped_executor_start_gate_blocks_persisted_pending_action(self):
        adapter = ProductionServiceAdapter(ROOT)
        with tempfile.TemporaryDirectory(prefix="r1a-start-block-") as directory:
            root = Path(directory)
            (root / "persistence_state.json").write_text(json.dumps({"trades": {"T-1": {"status": "active"}}, "system": {}}), encoding="utf-8")
            with patch.dict(os.environ, {"RANDLE_DATA_ROOT": str(root)}):
                result = adapter.start_safety(snapshot_rows(ServiceClassification.STOPPED.value))
        self.assertFalse(result["safe"])

    def test_stopped_executor_start_gate_blocks_persisted_executor_exposure(self):
        adapter = ProductionServiceAdapter(ROOT)
        with tempfile.TemporaryDirectory(prefix="r1a-executor-start-block-") as directory:
            source_root = Path(directory)
            (source_root / "Data").mkdir()
            (source_root / "Data" / "executor_state.json").write_text(
                json.dumps({"orders": {"O-1": {"status": "working"}}, "positions": {}}),
                encoding="utf-8",
            )
            runtime_root = source_root / "runtime"
            runtime_root.mkdir()
            (runtime_root / "persistence_state.json").write_text(
                json.dumps({"trades": {}, "system": {}}), encoding="utf-8"
            )
            adapter.repository_root = source_root
            with patch.dict(os.environ, {"RANDLE_DATA_ROOT": str(runtime_root)}):
                result = adapter.start_safety(snapshot_rows(ServiceClassification.STOPPED.value))
        self.assertFalse(result["safe"])
        self.assertEqual(result["reason"], "prestart_executor_exposure_active")
        self.assertEqual(result["executor"]["active_orders"], 1)

    def test_confirmed_start_allows_stopped_identity_without_prestart_executor_api(self):
        adapter = ProductionServiceAdapter(ROOT)
        before = snapshot_rows(ServiceClassification.STOPPED.value)
        after = snapshot_rows(ServiceClassification.RUNNING_READY.value)
        adapter.snapshot = Mock(side_effect=[before, after])
        adapter.start_safety = lambda snapshot=None: {"ok": True, "safe": True, "authority": "persisted_start_gate_only"}
        adapter.credential_authority = lambda: {"ok": True}
        adapter.write_authority = lambda: {"ok": True, "roots": {}}
        adapter.trading_safety = lambda: {"ok": True, "safe": True, "active_orders": 0, "nonzero_positions": 0, "pending_executable_actions": 0, "orphan_exposure": 0}
        completed = subprocess.CompletedProcess([], 0, "", "")
        with tempfile.TemporaryDirectory(prefix="command-center-launcher-logs-") as runtime_root:
            with patch.dict(os.environ, {"RANDLE_DATA_ROOT": runtime_root}):
                with patch("command_center_service_control.subprocess.run", return_value=completed) as run:
                    result = adapter.start_stack()
        self.assertTrue(result["ok"], result)
        self.assertEqual(run.call_count, 1)

    def test_shutdown_unavailable_uses_exact_block_and_stops_nothing(self):
        adapter = ProductionServiceAdapter(ROOT)
        running = snapshot_rows(ServiceClassification.RUNNING_READY.value)
        for index, row in enumerate(running["services"], 1):
            row["pids"] = [index]
        adapter.snapshot = lambda: running
        adapter.trading_safety = lambda: {"ok": False, "safe": False, "reason": "trading_state_unavailable"}
        adapter._stop_pid = Mock(return_value=True)
        result = adapter.shutdown_stack()
        self.assertTrue(result["blocked"])
        self.assertEqual(result["message"], "SHUTDOWN BLOCKED — TRADING STATE UNAVAILABLE")
        adapter._stop_pid.assert_not_called()

    def test_live_zero_and_active_exposure_are_not_replaced_by_persisted_counts(self):
        adapter = ProductionServiceAdapter(ROOT)
        payloads = {
            "/orders": {"ok": True, "orders": []},
            "/positions": {"ok": True, "positions": {}},
            "/trades": {"ok": True, "trades": {}, "orphan_exposure": {"has_orphans": False, "has_manager_state_issue": False}},
        }
        adapter._safety_json_get_result = lambda url, deadline=None: {
            "ok": True,
            "payload": payloads[next(path for path in payloads if url.endswith(path))],
            "status": 200,
            "reason": "isolated_fixture",
            "attempts": 1,
            "elapsed_ms": 0,
        }
        self.assertTrue(adapter.trading_safety()["safe"])
        payloads["/orders"] = {"ok": True, "orders": [{"status": "working"}]}
        active = adapter.trading_safety()
        self.assertFalse(active["safe"])
        self.assertEqual(active["active_orders"], 1)

    def test_canonical_launch_envelope_probes_all_disposable_write_roots(self):
        with tempfile.TemporaryDirectory(prefix="r1a-write-") as directory:
            with patch.dict(os.environ, {"RANDLE_DATA_ROOT": directory}, clear=False):
                target = service_launcher.configure_execution_envelope("entry_agent")
            self.assertEqual(target, (ROOT / "EntryAgent" / "tv_context_server.py").resolve())
            self.assertTrue((Path(directory) / "tv_context_spool").is_dir())
            self.assertTrue((Path(directory) / "entry_agent").is_dir())
            self.assertFalse(list(Path(directory).rglob(".command-center-service-launch-*.tmp")))

    def test_canonical_launch_envelope_denied_write_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="r1a-denied-") as directory:
            with patch.dict(os.environ, {"RANDLE_DATA_ROOT": directory}, clear=False), patch.object(service_launcher, "_probe_root", side_effect=PermissionError("denied")):
                with self.assertRaises(PermissionError):
                    service_launcher.configure_execution_envelope("trade_manager")

    def test_launcher_orders_executor_exposure_gate_before_execution_dependencies(self):
        launcher = (ROOT / "launch_all.ps1").read_text(encoding="utf-8-sig")
        orchestration = launcher[launcher.index("try {", launcher.index("STARTUP_BEGIN")):]
        order = ["Test-PreExecutorStartSafetyGate", "Ensure-Executor", "Test-StartupExposureGate", "Ensure-EntryAgentAndRelay", "Ensure-TradeManager", "Ensure-ListenerBridge", "Ensure-Ngrok"]
        offsets = [orchestration.index(value) for value in order]
        self.assertEqual(offsets, sorted(offsets))
        self.assertIn('Start-ManagedProcess "EntryAgent" $python @($ServiceWrapperPath, "--service", "entry_agent")', launcher)
        self.assertIn('Start-ManagedProcess "TradeManager" $python @($ServiceWrapperPath, "--service", "trade_manager")', launcher)

    def test_manifest_pins_wrapper_hash_and_disallows_direct_entry_manager(self):
        manifest = json.loads((ROOT / "Architecture" / "Command_Center" / "command_center_governed_service_manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["start_safety"]["require_zero_persisted_executor_exposure_when_stopped"])
        wrapper_sha = hashlib.sha256((ROOT / "command_center_service_launcher.py").read_bytes()).hexdigest()
        for name in ("entry_agent", "trade_manager"):
            service = next(row for row in manifest["services"] if row["name"] == name)
            canonical = next(row for row in service["execution_identities"] if row["name"] == "canonical_wrapper")
            self.assertEqual(canonical["wrapper_sha256"], wrapper_sha)
            self.assertFalse(any(row["type"] == "GOVERNED_DIRECT" for row in service["execution_identities"]))

    def test_wrapped_shutdown_owns_only_authenticated_root_pid_tree(self):
        adapter = ProductionServiceAdapter(ROOT)
        completed = subprocess.CompletedProcess([], 0, "", "")
        with patch("command_center_service_control.subprocess.run", return_value=completed) as run:
            self.assertTrue(adapter._stop_pid(4242))
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["taskkill.exe", "/PID", "4242", "/T"])
        self.assertNotIn("5151", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
