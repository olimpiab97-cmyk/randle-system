import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class CommandCenterListenerWatchdogTests(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / "command_center.html").read_text(encoding="utf-8")

    def test_operator_warning_names_rithmic_execution_truth_and_exact_contract_charts(self):
        self.assertIn("Rithmic live contract ticks", self.html)
        self.assertIn("not TradingView price", self.html)
        self.assertIn("NQM6/NQM2026", self.html)
        self.assertIn("RTYM6/RTYM2026", self.html)
        self.assertIn("Continuous symbols NQ1!/RTY1!", self.html)

    def test_submit_gate_uses_listener_status_errors(self):
        self.assertIn("function getSelectedListenerStatus()", self.html)
        self.assertIn("selectedListener.status !== \"fresh\"", self.html)
        self.assertIn("LISTENER_STALE", self.html)
        self.assertIn("LISTENER_MISSING", self.html)
        self.assertIn("Listener Stale", self.html)
        self.assertIn("Listener Missing", self.html)

    def test_critical_halt_and_flat_executor_clear_active_map(self):
        self.assertIn("function isExecutorFlatNoOrdersForTrade(trade)", self.html)
        self.assertIn("filterExecutorLiveActiveTrades", self.html)
        self.assertIn("stale_ui_trade_cleared", self.html)
        self.assertIn("CRITICAL HALT", self.html)
        self.assertIn("unprotected_position_no_stop", self.html)

    def test_live_trade_visual_separates_market_data_time_from_ui_refresh(self):
        self.assertIn("function getMarketDataState(symbolState)", self.html)
        self.assertIn("Market Data Age", self.html)
        self.assertIn("Last tick", self.html)
        self.assertIn("MARKET DATA", self.html)
        self.assertIn("marketDataUsable", self.html)
        self.assertIn("listenerFeedHealth.latest_listener_price", self.html)
        self.assertIn("last_listener_price_timestamp_utc", self.html)

    def test_market_liveness_comes_from_listener_feed_health_not_executor_snapshot_price(self):
        self.assertIn("latestFeedHealthPayload", self.html)
        self.assertIn("refreshFeedHealth", self.html)
        self.assertIn("listenerFeedHealth", self.html)
        self.assertNotIn('source: "snapshot.last_price"', self.html)
        self.assertNotIn('source: "snapshot.current_1m_bar.close"', self.html)

    def test_executor_price_fields_are_not_used_as_feed_truth(self):
        self.assertIn("function getMarketDataState", self.html)
        self.assertIn("feed_health", self.html)
        self.assertNotIn("const marketData = getMarketDataState(symbolState);", self.html)
        self.assertNotIn("const snapshotLastPrice = toFiniteNumber(symbolState.last_price);", self.html)
        self.assertNotIn("const currentBarClose = toFiniteNumber(symbolState.current_1m_bar && symbolState.current_1m_bar.close);", self.html)

    def test_operator_feed_status_and_submit_gate_use_listener_feed_health_source(self):
        self.assertIn("getSelectedListenerStatus(latestFeedHealthPayload", self.html)
        self.assertIn("Feed Status", self.html)
        self.assertIn("Last Tick Age", self.html)
        self.assertNotIn('const symbolState = ((latestSnapshot && latestSnapshot.symbols) || {})[symbol] || null;', self.html)

    def test_executor_snapshot_remains_execution_state_source_only(self):
        self.assertIn('const data = await fetchJson(`${EX_BASE}/sync_snapshot`);', self.html)
        self.assertIn("position_qty", self.html)
        self.assertIn("working_orders", self.html)
        self.assertIn("stop_order", self.html)
        self.assertIn("Executor Snapshot", self.html)

    def test_trade_visual_uses_backend_trade_and_executor_order_truth(self):
        self.assertIn('const data = await fetchJson(`${EX_BASE}/orders`);', self.html)
        self.assertIn("function buildTradeBackendReadModel(trade)", self.html)
        self.assertIn("getActiveStopOrderForTrade", self.html)
        self.assertIn("getTp1OrderForTrade", self.html)
        self.assertIn("active_stop_order_id", self.html)
        self.assertIn("active_stop_qty", self.html)
        self.assertIn("active_stop_price", self.html)
        self.assertIn("tp1_order_status", self.html)
        self.assertIn("oco_group", self.html)

    def test_trade_visual_warns_on_tm_executor_divergence(self):
        self.assertIn("Executor stop differs from TM stop", self.html)
        self.assertIn("Executor position differs from TM remaining_size", self.html)
        self.assertIn("No active protective stop", self.html)
        self.assertIn("Runner protected", self.html)
        self.assertIn("Backend synced", self.html)
        self.assertIn("display_stop_price", self.html)
        self.assertIn("display_remaining_size", self.html)


if __name__ == "__main__":
    unittest.main()
