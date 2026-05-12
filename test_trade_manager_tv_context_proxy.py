import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class TradeManagerTvContextProxyTests(unittest.TestCase):
    def _load_manager(self):
        spec = importlib.util.spec_from_file_location(
            "trade_manager_tv_context_proxy_under_test",
            ROOT / "Engines" / "trade_manager.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_tv_context_proxy_forwards_payload_to_entry_agent(self):
        manager = self._load_manager()
        calls = []

        class FakeResponse:
            status_code = 200
            text = ""

            def json(self):
                return {"ok": True, "context": {"normalized_symbol": "YM"}}

        def fake_post(url, json=None, timeout=None):
            calls.append({"url": url, "json": json, "timeout": timeout})
            return FakeResponse()

        original_post = manager.requests.post
        manager.requests.post = fake_post
        try:
            response = manager.app.test_client().post(
                "/webhook/tv-context",
                json={
                    "source": "tradingview_level_helper",
                    "symbol": "CBOT_MINI:YM1!",
                    "ONH": 50100,
                },
            )
        finally:
            manager.requests.post = original_post

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["price_truth"], "Rithmic")
        self.assertEqual(calls[0]["url"], manager.ENTRY_AGENT_TV_CONTEXT_URL)
        self.assertEqual(calls[0]["json"]["source"], "tradingview_level_helper")
        self.assertEqual(calls[0]["timeout"], 1.0)

    def test_internal_service_urls_default_to_ipv4_loopback(self):
        manager = self._load_manager()

        self.assertEqual(manager.EXECUTOR_URL, "http://127.0.0.1:6001/execute")
        self.assertEqual(manager.EXECUTOR_ORDERS_URL, "http://127.0.0.1:6001/orders")
        self.assertEqual(manager.EXECUTOR_SNAPSHOT_URL, "http://127.0.0.1:6001/sync_snapshot")
        self.assertEqual(manager.ENTRY_AGENT_TV_CONTEXT_URL, "http://127.0.0.1:7002/webhook/tv-context")

    def test_tv_context_proxy_debug_returns_last_state(self):
        manager = self._load_manager()
        manager.TV_CONTEXT_PROXY_STATE.update({
            "last_forwarded_at": "2026-05-05T00:00:00Z",
            "last_status_code": 200,
            "last_ok": True,
            "last_error": None,
            "last_symbol": "NQ",
            "target_url": manager.ENTRY_AGENT_TV_CONTEXT_URL,
        })

        response = manager.app.test_client().get("/debug/tv-context-proxy")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["price_truth"], "Rithmic")
        self.assertEqual(payload["state"]["last_symbol"], "NQ")


if __name__ == "__main__":
    unittest.main()
