import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class CommandCenterListenerWatchdogTests(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / "command_center.html").read_text(encoding="utf-8")
        persistence_path = ROOT / "Data" / "persistence_state.json"
        self.persistence = json.loads(persistence_path.read_text(encoding="utf-8")) if persistence_path.is_file() else None

    def test_operator_warning_names_rithmic_execution_truth_and_exact_contract_charts(self):
        self.assertIn("Rithmic live contract ticks", self.html)
        self.assertIn("not TradingView price", self.html)
        self.assertIn("NQM6/NQM2026", self.html)
        self.assertIn("RTYM6/RTYM2026", self.html)
        self.assertIn("Continuous symbols NQ1!/RTY1!", self.html)

    def test_submit_gate_uses_listener_status_errors(self):
        self.assertIn("function getSelectedListenerStatus()", self.html)
        self.assertIn('selectedListener.status !== "fresh"', self.html)
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

    def test_trade_history_panel_shows_all_non_active_historical_statuses(self):
        self.assertIn('return status === "closed" || status === "archived" || status === "error" || status === "rejected";', self.html)
        self.assertIn('renderTradeList("closedTradesBox", historicalTrades, "closed", "No historical trades yet.");', self.html)
        self.assertIn('renderTradeList("errorTradesBox", errorTrades, "error", "No hidden error trades.");', self.html)
        self.assertNotIn('renderTradeList("closedTradesBox", closedTrades, "closed", "No closed trades yet.");', self.html)

    def test_kpi_starting_equity_ignores_stale_snapshot_balance_fields(self):
        start = self.html.index("function getKpiStartingEquity()")
        end = self.html.index("function getCurrentSyntheticEquity")
        body = self.html[start:end]
        self.assertIn('"starting_balance"', body)
        self.assertIn('"starting_equity"', body)
        self.assertIn('"baseline"', body)
        self.assertNotIn('"balance"', body)
        self.assertNotIn('"net_liq"', body)
        self.assertNotIn('"cash_balance"', body)

    def test_current_persistence_snapshot_contains_16_historical_trade_records(self):
        if self.persistence is None:
            self.skipTest("runtime persistence snapshot is intentionally absent from source-only worktrees")
        trades = self.persistence.get("trades", {})
        self.assertEqual(len(trades), 16)
        self.assertTrue(all(str(trade.get("status", "")).lower() == "closed" for trade in trades.values()))

    def test_entry_agent_ui_exposes_manual_override_and_compact_step_timestamps(self):
        self.assertIn("Override Frozen Lock From Latest TV", self.html)
        self.assertIn("data-liquidity-lock-override", self.html)
        self.assertIn("formatPtTimestamp", self.html)
        self.assertNotIn("Step Timeline", self.html)
        self.assertNotIn("Active Liquidity Price", self.html)
        self.assertNotIn("Step Milestones", self.html)
        self.assertIn("renderEntryAgentStepBlock", self.html)
        self.assertIn("renderEntryAgentCompactRow", self.html)
        self.assertIn('renderEntryAgentStepBlock("Step 2"', self.html)
        self.assertIn('renderEntryAgentStepBlock("Step 4"', self.html)
        self.assertIn("renderEntryAgentInvalidationBlock", self.html)
        self.assertNotIn("renderEntryAgentSectionTitle", self.html)
        self.assertNotIn("entry-agent-section-title", self.html)
        self.assertIn("Mode", self.html)
        self.assertIn("Time", self.html)
        self.assertIn("Candle Count", self.html)
        self.assertIn("Candle Count Time", self.html)
        self.assertIn('"n/a"', self.html)
        self.assertNotIn("Mode / Event", self.html)
        self.assertIn("Details", self.html)
        self.assertIn("Invalidation Details", self.html)
        self.assertIn("Source", self.html)
        self.assertIn("Session Window", self.html)
        self.assertIn("CLOSED", self.html)
        self.assertIn("OBSERVATIONAL", self.html)
        self.assertIn("LIVE", self.html)
        self.assertIn("Rejection", self.html)
        self.assertIn("Continuation", self.html)
        self.assertNotIn("Lane State", self.html)
        self.assertIn("Wick", self.html)
        self.assertIn("candleCount", self.html)
        self.assertNotIn("Current Candle", self.html)
        self.assertNotIn("Current Step Candle", self.html)
        self.assertIn("Reason", self.html)


if __name__ == "__main__":
    unittest.main()
