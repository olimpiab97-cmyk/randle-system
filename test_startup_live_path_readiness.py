import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import startup_public_health_check as public_check


ROOT = Path(__file__).resolve().parent
ENTRY_AGENT_ROOT = ROOT / "EntryAgent"
if str(ENTRY_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(ENTRY_AGENT_ROOT))


class StartupPublicHealthHelperTests(unittest.TestCase):
    def test_https_post_keeps_tls_verification_enabled_and_returns_json(self):
        response = mock.Mock()
        response.status_code = 200
        response.json.return_value = {"ok": True, "receipt_id": "receipt-1"}
        session = mock.Mock()
        session.request.return_value = response

        with mock.patch.object(public_check.requests, "Session", return_value=session):
            result = public_check.request_public_json(
                "https://example.ngrok-free.dev/webhook/tv-context",
                5,
                method="POST",
                payload={"source": "startup_liquidity_relay_probe"},
                query_token="test-query-token",
            )

        self.assertTrue(result["ok"])
        session.request.assert_called_once_with(
            "POST",
            "https://example.ngrok-free.dev/webhook/tv-context",
            timeout=(5, 5),
            verify=True,
            headers={"ngrok-skip-browser-warning": "1"},
            json={"source": "startup_liquidity_relay_probe"},
            params={"token": "test-query-token"},
        )

    def test_request_exception_redacts_environment_managed_query_token(self):
        detail = public_check.redacted_exception_detail(
            RuntimeError("request failed for ?token=never-log-this"),
            "never-log-this",
        )
        self.assertNotIn("never-log-this", detail)
        self.assertIn("token=<redacted>", detail)


class EntryRelayReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TV_CONTEXT_INTERNAL_RELAY_TOKEN"] = "startup-test-relay-token"
        spec = importlib.util.spec_from_file_location(
            "entry_relay_receipt_under_test",
            ROOT / "EntryAgent" / "tv_context_server.py",
        )
        cls.server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.server)

    def test_startup_probe_updates_only_diagnostic_receipt(self):
        before_context = copy.deepcopy(self.server.LATEST_TV_CONTEXT_BY_SYMBOL)
        self.server.TV_CONTEXT_DIAGNOSTIC_RECEIPT.clear()

        response = self.server.app.test_client().post(
            "/webhook/tv-context",
            headers={"X-Randle-Relay-Token": "startup-test-relay-token"},
            json={
                "source": "startup_liquidity_relay_probe",
                "receipt_id": "startup-receipt-2",
                "sent_at": "2026-07-16T05:00:00Z",
            },
        )
        receipt = self.server.app.test_client().get("/debug/tv-context-receipt").get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["receipt_id"], "startup-receipt-2")
        self.assertFalse(response.get_json()["liquidity_state_changed"])
        self.assertEqual(receipt["receipt"]["receipt_id"], "startup-receipt-2")
        self.assertEqual(self.server.LATEST_TV_CONTEXT_BY_SYMBOL, before_context)

    def test_probe_requires_a_receipt_id(self):
        response = self.server.app.test_client().post(
            "/webhook/tv-context",
            headers={"X-Randle-Relay-Token": "startup-test-relay-token"},
            json={"source": "startup_liquidity_relay_probe"},
        )
        self.assertEqual(response.status_code, 400)


class LauncherReadinessContractTests(unittest.TestCase):
    def test_launcher_separates_market_warmup_from_service_readiness(self):
        script = (ROOT / "launch_all.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("MarketDataReadiness", script)
        self.assertIn("COMPLETED_CANDLE_WARMING", script)
        self.assertIn("ATR_WARMING", script)
        self.assertIn("current_rithmic_rma_ready_and_projected", script)
        self.assertIn("MaximumObservationSeconds", script)
        self.assertIn("ProgressAdvanced", script)
        self.assertIn("startup_liquidity_relay_probe", script)
        self.assertIn("PublicRelayResponse", script)
        self.assertIn("entryRecord.atr_1m_14", script)
        self.assertIn("trade_manager_proxy_plus_fresh_entry_receipts", script)
        self.assertIn("proxyState.last_user_agent", script)
        self.assertNotIn("requests/http?limit=30", script)
        self.assertIn("ngrok_start_returned_no_pid", script)
        self.assertNotIn('Start-ManagedProcess "Ngrok"', script)
        self.assertIn("startup_public_health_check.py", script)
        self.assertIn("Invoke-BoundedPublicHealthJson", script)
        self.assertIn('"--query-token-env", $QueryTokenEnvironment', script)
        self.assertNotIn("authenticatedProbeUrl", script)
        self.assertIn("-WorkingDirectory $script:repositoryRoot", script)
        self.assertIn("Ensure-ListenerBridge\n    Ensure-EntryAgentAndRelay\n    Ensure-Ngrok", script)
        self.assertIn("current_canonical_completed_candles_confirmed", script)
        self.assertIn('STARTUP_RESULT=$finalStatus trading_readiness=', script)
        self.assertIn('if ($finalStatus -eq "WARMING")', script)
        self.assertNotIn("AtrTimeoutSeconds", script)
        self.assertNotIn("waiting_for_finalized_bar_advancement_after_startup", script)
        self.assertNotIn("VERIFY_RITHMIC_STATUS_WITHOUT_WAITING_FOR_WARMUP", script)


if __name__ == "__main__":
    unittest.main()
