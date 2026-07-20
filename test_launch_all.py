import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

import startup_public_health_check


class LaunchAllContractTests(unittest.TestCase):
    def run_market_policy(
        self,
        *,
        service_available=True,
        observation_valid=True,
        authority_ready=False,
        progress_advanced=False,
        elapsed_seconds=60,
        seconds_since_progress=60,
        maximum_observation_seconds=1020,
        stall_seconds=180,
        phase="ATR_WARMING",
        detail_reason="synthetic",
    ):
        script = pathlib.Path(__file__).with_name("launch_all.ps1").read_text(encoding="utf-8")
        function_block = "function Resolve-MarketReadinessState {" + script.split(
            "function Resolve-MarketReadinessState {", 1
        )[1].split("function Invoke-LocalJson {", 1)[0]

        def ps_bool(value):
            return "$true" if value else "$false"

        harness = function_block + "\n" + (
            "$result = Resolve-MarketReadinessState "
            f"-ServiceAvailable {ps_bool(service_available)} "
            f"-ObservationValid {ps_bool(observation_valid)} "
            f"-AuthorityReady {ps_bool(authority_ready)} "
            f"-ProgressAdvanced {ps_bool(progress_advanced)} "
            f"-ElapsedSeconds {elapsed_seconds} "
            f"-SecondsSinceProgress {seconds_since_progress} "
            f"-MaximumObservationSeconds {maximum_observation_seconds} "
            f"-StallSeconds {stall_seconds} "
            f'-Phase "{phase}" '
            f'-DetailReason "{detail_reason}"\n'
            "$result | ConvertTo-Json -Compress\n"
        )
        path = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".ps1", encoding="utf-8", delete=False) as handle:
                handle.write(harness)
                path = pathlib.Path(handle.name)
            completed = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            return json.loads(completed.stdout)
        finally:
            if path is not None:
                path.unlink(missing_ok=True)

    def test_listener_readiness_poll_uses_cached_pid_not_wmi_inventory(self):
        script = pathlib.Path(__file__).with_name("launch_all.ps1").read_text(encoding="utf-8")
        probe = script.split("function Test-ListenerBridgeContract {", 1)[1].split(
            "function Test-CommandCenterContract {", 1
        )[0]

        self.assertIn("$script:ListenerProcess", probe)
        self.assertIn("Get-Process -Id", probe)
        self.assertNotIn("Get-ManagedProcesses", probe)
        self.assertIn("$livePrices.last_prices.$nqContract", probe)
        self.assertIn("$livePrices.last_prices.$ymContract", probe)
        self.assertNotIn("$livePrices.last_prices.NQ", probe)
        self.assertNotIn("$livePrices.last_prices.YM", probe)
        self.assertIn("$publicationCurrent", probe)
        self.assertIn("last_successful_executor_price_post_timestamp_utc", probe)
        self.assertNotIn("nq_ym_publication_counts_not_increasing", probe)

        entry_current = script.split("function Verify-EntryCurrentSession {", 1)[1].split(
            "function Verify-CommandCenter {", 1
        )[0]
        self.assertIn("$entryCurrentSessionTimeoutSeconds = 130", entry_current)

    def test_ngrok_readiness_uses_agent_tunnel_and_local_upstream(self):
        script = pathlib.Path(__file__).with_name("launch_all.ps1").read_text(encoding="utf-8")
        probe = script.split("function Test-NgrokContract {", 1)[1].split(
            "function Get-NgrokFailureEvidence {", 1
        )[0]

        self.assertIn("$TradeManagerHealthUrl", probe)
        self.assertIn("single_https_tunnel_public_health_and_liquidity_relay_round_trip_confirmed", probe)
        self.assertIn("$processes = @(", probe)
        self.assertIn("Invoke-BoundedPublicHealthJson", probe)
        self.assertNotIn("Invoke-RestMethod", probe)

    def test_executor_maintenance_precedes_executor_start(self):
        script = pathlib.Path(__file__).with_name("launch_all.ps1").read_text(encoding="utf-8")
        ensure = script.split("function Ensure-Executor {", 1)[1].split(
            "function Ensure-TradeManager {", 1
        )[0]

        self.assertLess(ensure.index("Invoke-ExecutorJournalMaintenance"), ensure.index('Start-ManagedProcess "Executor"'))

        maintenance = script.split("function Invoke-ExecutorJournalMaintenance {", 1)[1].split(
            "function Ensure-Executor {", 1
        )[0]
        self.assertIn("$process.WaitForExit()", maintenance)
        self.assertIn("$process.Refresh()", maintenance)
        self.assertIn("$result.ok -ne $true", maintenance)
        self.assertNotIn("$process.ExitCode -ne 0", maintenance)

    def test_trade_manager_maintenance_precedes_trade_manager_start(self):
        script = pathlib.Path(__file__).with_name("launch_all.ps1").read_text(encoding="utf-8")
        ensure = script.split("function Ensure-TradeManager {", 1)[1].split(
            "function Ensure-EntryAgentAndRelay {", 1
        )[0]

        self.assertLess(
            ensure.index("Invoke-TradeManagerJournalMaintenance"),
            ensure.index('Start-ManagedProcess "TradeManager"'),
        )
        maintenance = script.split("function Invoke-TradeManagerJournalMaintenance {", 1)[1].split(
            "function Get-NgrokFailureEvidence {", 1
        )[0]
        self.assertIn("--executor-journal-root", maintenance)
        self.assertIn("--persistence-file", maintenance)
        self.assertIn("trade_manager_journal_maintenance_timeout", maintenance)
        self.assertIn("$result.ok -ne $true", maintenance)

    def test_trade_manager_probe_reports_the_exact_failed_endpoint(self):
        script = pathlib.Path(__file__).with_name("launch_all.ps1").read_text(encoding="utf-8")
        probe = script.split("function Test-TradeManagerContract {", 1)[1].split(
            "function Test-EntryAgentContract {", 1
        )[0]

        self.assertIn("trade_manager_health_endpoint_error", probe)
        self.assertIn("trade_manager_tick_pipeline_endpoint_error", probe)
        self.assertIn("trade_manager_canonical_atr_endpoint_error", probe)
        self.assertIn("FailedEndpoint = $TradeManagerHealthUrl", probe)
        self.assertIn("Process = $tradeManagerProcess", probe)
        self.assertNotIn("trade_manager_endpoint_error", probe)

    def test_listener_service_is_separate_from_market_data_readiness(self):
        script = pathlib.Path(__file__).with_name("launch_all.ps1").read_text(encoding="utf-8")
        orchestration = script.split('Write-StartupLine ("STARTUP_POLICY', 1)[1].split(
            "$requiredComponents", 1
        )[0]

        self.assertLess(
            orchestration.index("Ensure-ListenerBridge"),
            orchestration.index("Ensure-EntryAgentAndRelay"),
        )
        self.assertLess(
            orchestration.index("Ensure-Ngrok"),
            orchestration.index("Verify-MarketDataReadiness"),
        )
        listener_probe = script.split("function Test-ListenerBridgeContract {", 1)[1].split(
            "function Get-CanonicalAtrWarmupEvidence {", 1
        )[0]
        self.assertNotIn("Get-CanonicalCompletedCandleEvidence", listener_probe)
        self.assertIn("$loginAndSubscriptions", listener_probe)
        self.assertIn("$publicationCurrent", listener_probe)
        market_probe = script.split("function Get-MarketDataReadinessObservation {", 1)[1].split(
            "function Wait-ForMarketDataReadiness {", 1
        )[0]
        self.assertIn("Get-CanonicalCompletedCandleEvidence", market_probe)
        self.assertIn("Get-CanonicalAtrWarmupEvidence", market_probe)
        candle_probe = script.split("function Get-CanonicalCompletedCandleEvidence {", 1)[1].split(
            "function Test-ListenerBridgeContract {", 1
        )[0]
        self.assertIn('$_.' + 'status -eq "FINAL"', candle_probe)
        self.assertIn("$candle.session_date -eq $expectedSessionDate", candle_probe)
        self.assertIn("$ageSeconds -le 180", candle_probe)

    def test_market_readiness_bound_is_derived_from_canonical_minute_policy(self):
        script = pathlib.Path(__file__).with_name("launch_all.ps1").read_text(encoding="utf-8")
        self.assertIn("$CanonicalMinuteSeconds = 60", script)
        self.assertIn("$FirstCompleteCandleIntervalCount = 2", script)
        self.assertIn("$CanonicalAtrRequiredTrueRangeCount = 14", script)
        self.assertIn("$MarketReadinessSchedulingAllowanceIntervals = 1", script)
        self.assertIn("$MarketReadinessObservationSeconds = $FirstCompleteCandleMaximumSeconds +", script)
        self.assertNotIn("AtrTimeoutSeconds", script)
        self.assertIn("MaximumObservationSeconds = $MarketReadinessObservationSeconds", script)
        self.assertIn("CompletedCandleCount", script)
        self.assertIn("AtrIncludedCount", script)
        self.assertIn("AtrRequiredCount", script)
        self.assertIn("LastCompletedCandleTime", script)
        self.assertIn("AuthorityEpoch", script)
        self.assertIn("ProgressAdvanced", script)

    def test_market_policy_fails_when_service_is_unavailable(self):
        result = self.run_market_policy(service_available=False, phase="SERVICE_UNAVAILABLE")
        self.assertEqual(result["Status"], "FAILED")
        self.assertIn("service_unavailable", result["Reason"])
        self.assertFalse(result["TradingReady"])

    def test_market_policy_reports_completed_candle_warming(self):
        result = self.run_market_policy(phase="COMPLETED_CANDLE_WARMING")
        self.assertEqual(result["Status"], "WARMING")
        self.assertIn("COMPLETED_CANDLE_WARMING", result["Reason"])
        self.assertFalse(result["TradingReady"])

    def test_market_policy_reports_atr_warming(self):
        result = self.run_market_policy(phase="ATR_WARMING", progress_advanced=True)
        self.assertEqual(result["Status"], "WARMING")
        self.assertTrue(result["ProgressAdvancing"])
        self.assertFalse(result["TradingReady"])

    def test_market_policy_reports_advancing_warmup_at_governed_window(self):
        result = self.run_market_policy(
            phase="ATR_WARMING",
            progress_advanced=True,
            elapsed_seconds=1020,
            seconds_since_progress=10,
        )
        self.assertEqual(result["Status"], "WARMING")
        self.assertIn("governed_window_elapsed_while_progressing", result["Reason"])
        self.assertTrue(result["ProgressAdvancing"])
        self.assertFalse(result["TradingReady"])

    def test_market_policy_fails_when_progress_stalls(self):
        result = self.run_market_policy(
            phase="ATR_WARMING",
            progress_advanced=True,
            elapsed_seconds=300,
            seconds_since_progress=181,
        )
        self.assertEqual(result["Status"], "FAILED")
        self.assertIn("progress_stalled", result["Reason"])

    def test_market_policy_reports_completed_readiness(self):
        result = self.run_market_policy(
            authority_ready=True,
            progress_advanced=True,
            elapsed_seconds=900,
            seconds_since_progress=0,
            phase="READY_WAITING_FOR_ADVANCEMENT",
        )
        self.assertEqual(result["Status"], "READY")
        self.assertTrue(result["TradingReady"])

    def test_terminal_semantics_preserve_warming_as_not_trading_ready(self):
        script = pathlib.Path(__file__).with_name("launch_all.ps1").read_text(encoding="utf-8")
        self.assertIn('[ValidateSet("READY", "WARMING", "FAILED")]', script)
        self.assertIn('$finalStatus = if ($failedComponents.Count -gt 0) { "FAILED" } elseif ($warmingComponents.Count -gt 0) { "WARMING" } else { "READY" }', script)
        self.assertIn('TradingReadiness = $finalStatus -eq "READY"', script)
        self.assertIn('if ($finalStatus -eq "WARMING")', script)
        self.assertIn("exit 2", script)

    def test_public_health_helper_keeps_tls_verification_enabled(self):
        response = mock.Mock(status_code=200)
        response.json.return_value = {"ok": True, "pid": 7001}
        session = mock.Mock()
        session.get.return_value = response
        with mock.patch.object(startup_public_health_check.requests, "Session", return_value=session):
            result = startup_public_health_check.check_public_health("https://example.test/health", 5)

        self.assertTrue(result["ok"])
        session.request.assert_called_once_with(
            "GET",
            "https://example.test/health",
            timeout=(5, 5),
            verify=True,
            headers={"ngrok-skip-browser-warning": "1"},
        )


if __name__ == "__main__":
    unittest.main()
