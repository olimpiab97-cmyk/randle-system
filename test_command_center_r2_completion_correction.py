from __future__ import annotations

import json
import socket
import subprocess
import tempfile
import threading
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from command_center_service_control import ProductionServiceAdapter, load_control_version


ROOT = Path(__file__).resolve().parent
LAUNCHER = ROOT / "launch_all.ps1"
CONTROL = ROOT / "command_center_service_control.py"
MANIFEST = ROOT / "Architecture" / "Command_Center" / "command_center_governed_service_manifest.json"


def function_block(source: str, name: str, next_name: str) -> str:
    return f"function {name} {{" + source.split(f"function {name} {{", 1)[1].split(
        f"function {next_name} {{", 1
    )[0]


class _RehydratingHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - HTTP verb API
        payload = json.dumps(
            {
                "ok": False,
                "service_status": "REHYDRATING",
                "symbols": [],
                "rehydration_failures": [{"symbol": "NQ", "reason": "canonical_completed_candle_unavailable"}],
            }
        ).encode("utf-8")
        self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        return


class CommandCenterR2CompletionCorrectionTests(unittest.TestCase):
    def test_executor_relative_script_command_line_resolves_to_governed_repository(self):
        source = LAUNCHER.read_text(encoding="utf-8-sig")
        block = function_block(source, "Get-CommandPythonScriptPath", "Test-FileSha256")
        repository = str(ROOT).replace("'", "''")
        harness = (
            f"$script:repositoryRoot='{repository}'\n"
            + block
            + '\nGet-CommandPythonScriptPath \'"C:\\\\Python312\\\\python.exe" executor.py \'\n'
        )
        path = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".ps1", encoding="utf-8", delete=False) as handle:
                handle.write(harness)
                path = Path(handle.name)
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(Path(completed.stdout.strip()), ROOT / "executor.py")
        finally:
            if path is not None:
                path.unlink(missing_ok=True)

    def test_failure_diagnostics_tolerate_components_not_reached_after_fail_closed_gate(self):
        source = LAUNCHER.read_text(encoding="utf-8-sig")
        block = function_block(source, "Get-FinalDiagnostics", "Write-StartupLine")
        self.assertIn('$componentResult = $Results[$componentName]', block)
        self.assertIn('$null -ne $componentResult', block)
        self.assertNotIn('$Results["Ngrok"].Status', block)
        self.assertNotIn('$Results["Executor"].Evidence', block)

    def test_offline_start_accepts_source_valid_persistence_without_optional_orphan_projection(self):
        source = LAUNCHER.read_text(encoding="utf-8-sig")
        prestart = function_block(source, "Test-PreExecutorStartSafetyGate", "Test-StartupExposureGate")
        startup = function_block(source, "Test-StartupExposureGate", "Get-CommandPythonScriptPath")
        for block in (prestart, startup):
            self.assertIn('PSObject.Properties["orphan_exposure"]', block)
            self.assertIn('has_orphans = $false; has_manager_state_issue = $false', block)
            self.assertNotIn('.system.orphan_exposure', block)

    def test_two_canonical_wrappers_are_disambiguated_by_service_before_duplicate_evaluation(self):
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        services = {row["name"]: row for row in payload["services"]}
        self.assertIn(r"--service\s+entry_agent", services["entry_agent"]["command_marker"])
        self.assertNotIn("trade_manager", services["entry_agent"]["command_marker"].split("|", 1)[0])
        self.assertIn(r"--service\s+trade_manager", services["trade_manager"]["command_marker"])
        self.assertNotIn("entry_agent", services["trade_manager"]["command_marker"].split("|", 1)[0])
        launcher = LAUNCHER.read_text(encoding="utf-8-sig")
        self.assertIn("--service\\s+entry_agent", launcher)
        self.assertIn("--service\\s+trade_manager", launcher)

    def test_entry_503_json_survives_powershell_response_parser(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _RehydratingHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        source = LAUNCHER.read_text(encoding="utf-8-sig")
        block = function_block(source, "Invoke-LocalJsonResponse", "Get-ManagedProcesses")
        harness = (
            block
            + f"\n$r=Invoke-LocalJsonResponse 'http://127.0.0.1:{server.server_port}/entry/status' 3\n"
            + "$r | ConvertTo-Json -Compress -Depth 8\n"
        )
        path = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".ps1", encoding="utf-8", delete=False) as handle:
                handle.write(harness)
                path = Path(handle.name)
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            result = json.loads(completed.stdout)
            self.assertEqual(result["StatusCode"], 503)
            self.assertEqual(result["Payload"]["service_status"], "REHYDRATING")
            self.assertIsNone(result["ParseError"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
            if path is not None:
                path.unlink(missing_ok=True)

    def test_start_stack_redirects_launcher_to_governed_files_not_anonymous_pipes(self):
        source = CONTROL.read_text(encoding="utf-8")
        production = source.split("class ProductionServiceAdapter:", 1)[1]
        block = production.split("    def start_stack(self)", 1)[1].split("    @staticmethod\n    def _quantity", 1)[0]
        self.assertIn('launcher_log_root = data_root / "startup"', block)
        self.assertIn("stdout=launcher_stdout", block)
        self.assertIn("stderr=launcher_stderr", block)
        self.assertNotIn("capture_output=True", block)

    def test_trade_manager_probe_matches_the_deployed_read_only_contract(self):
        source = LAUNCHER.read_text(encoding="utf-8-sig")
        block = function_block(source, "Test-TradeManagerContract", "Test-EntryAgentContract")
        self.assertIn("$TradeManagerVersionUrl", block)
        self.assertIn("$TradeManagerSafetyUrl", block)
        self.assertIn("source_version_safety_schema_and_unique_port_owner_confirmed", block)
        self.assertNotIn("$TradeManagerHealthUrl", block)
        self.assertNotIn("$TradeManagerPipelineUrl", block)
        self.assertNotIn("$TradeManagerCanonicalAtrStatusUrl", block)

    def test_listener_and_atr_readiness_use_existing_production_projections(self):
        source = LAUNCHER.read_text(encoding="utf-8-sig")
        listener = function_block(source, "Test-ListenerBridgeContract", "Get-CanonicalAtrWarmupEvidence")
        atr = function_block(source, "Get-CanonicalAtrWarmupEvidence", "Get-MarketDataReadinessObservation")
        self.assertIn("counts.completed_by_trade_manager", listener)
        self.assertNotIn("$TradeManagerPipelineUrl", listener)
        self.assertIn("$EntryAgentStatusUrl", atr)
        self.assertIn("canonical_atr_ready", atr)
        self.assertIn("rithmic_exchange_time_rma14", atr)

    def test_ngrok_restart_uses_manifest_reserved_host_without_mutating_public_probe(self):
        source = LAUNCHER.read_text(encoding="utf-8-sig")
        contract = function_block(source, "Test-NgrokContract", "Invoke-ExecutorJournalMaintenance")
        ensure = function_block(source, "Ensure-Ngrok", "Get-FinalDiagnostics")
        self.assertIn("$script:ngrokPublicHost", contract)
        self.assertIn("$TradeManagerVersionUrl", contract)
        self.assertIn("$TradeManagerSafetyUrl", contract)
        self.assertNotIn('"POST"', contract)
        self.assertIn('"--url", $script:ngrokPublicUrl', ensure)
        self.assertIn('"--inspect=false"', ensure)

    def test_503_rehydration_payload_can_report_current_day_ladder_ready(self):
        today = datetime.now().date().isoformat()
        payload = {
            "ok": False,
            "service_status": "REHYDRATING",
            "symbols": [
                {
                    "symbol": symbol,
                    "market_context": {
                        "session_date": today,
                        "liquidity_context_locked": True,
                        "levels": {name: {"price": index} for index, name in enumerate(("YH", "YL", "ONH", "ONL", "PMH", "PML", "LH", "LL"))},
                    },
                }
                for symbol in ("NQ", "YM")
            ],
        }
        adapter = object.__new__(ProductionServiceAdapter)
        with patch.object(ProductionServiceAdapter, "_json_get_result", return_value=(503, payload)):
            result = adapter.ladder_status()
        self.assertEqual(result["state"], "READY")
        self.assertEqual(result["session_date"], today)

    def test_corrected_generation_authority_is_single_source_and_hash_validated(self):
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(payload["control_version"], "command_center_service_controls_r5")
        self.assertEqual(load_control_version(ROOT), payload["control_version"])
        required = payload["runtime_deployment"]["required_paths"]
        self.assertIn("launch_all.ps1", required)
        self.assertIn("Architecture/Command_Center/command_center_governed_service_manifest.json", required)


if __name__ == "__main__":
    unittest.main()
