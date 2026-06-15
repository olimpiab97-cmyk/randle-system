import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class TradeManagerPostBeResearchTests(unittest.TestCase):
    def _load_manager(self):
        spec = importlib.util.spec_from_file_location(
            "trade_manager_post_be_research_under_test",
            ROOT / "Engines" / "trade_manager.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _base_trade(self, symbol="NQ", direction="short", entry=100.0, leg_high=None, leg_low=None):
        if direction == "short":
            original_stop = entry + 10.0
            tp1_price = entry - 10.0
            be_trigger = entry - 5.0
        else:
            original_stop = entry - 10.0
            tp1_price = entry + 10.0
            be_trigger = entry + 5.0

        return {
            "trade_id": f"T-{symbol}-{direction}",
            "status": "active",
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry,
            "original_stop": original_stop,
            "current_stop": entry,
            "tp1_price": tp1_price,
            "be_trigger": be_trigger,
            "entry_leg_high": leg_high,
            "entry_leg_low": leg_low,
            "moved_to_be": True,
            "be_hit_at": "2026-05-29T13:00:00Z",
            "position_size": 2,
            "remaining_size": 1,
            "total_profit": 0.0,
        }

    def _close_and_record(self, manager, trade, research_file):
        manager.TRADE_MANAGEMENT_RESEARCH_FILE = str(research_file)
        trade["status"] = "closed"
        trade["closed_at"] = "2026-05-29T13:05:00Z"
        trade["exit_price"] = trade["entry_price"]
        trade["exit_reason"] = "stop_hit"
        self.assertTrue(manager.record_trade_management_research_if_closed(trade))
        rows = research_file.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(rows), 1)
        self.assertFalse(manager.record_trade_management_research_if_closed(trade))
        return json.loads(rows[0])

    def test_nq_short_structural_dynamic_tp1_before_structural_stop(self):
        manager = self._load_manager()
        trade = self._base_trade(symbol="NQ", direction="short", entry=30418.0, leg_high=30424.5)

        manager.update_post_be_analytics(trade, 30414.0, "2026-05-29T13:01:00Z")
        manager.update_post_be_analytics(trade, 30411.25, "2026-05-29T13:02:00Z")

        self.assertEqual(trade["structural_dynamic_stop_price"], 30424.75)
        self.assertEqual(trade["structural_dynamic_stop_distance_points"], 6.75)
        self.assertEqual(trade["structural_dynamic_tp1_price"], 30411.25)
        self.assertTrue(trade["structural_dynamic_tp1_would_hit"])
        self.assertFalse(trade.get("structural_dynamic_stop_would_hit", False))
        self.assertEqual(trade["structural_dynamic_model_first_hit"], "tp1")

        with tempfile.TemporaryDirectory() as tmp_dir:
            row = self._close_and_record(manager, trade, Path(tmp_dir) / "research.jsonl")
        self.assertEqual(row["entry_leg_high"], 30424.5)
        self.assertEqual(row["structural_dynamic_model_result"], "tp1")
        self.assertTrue(row["structural_dynamic_tp1_would_hit"])
        self.assertFalse(row["structural_dynamic_stop_would_hit"])

    def test_ym_short_structural_dynamic_tp1_before_structural_stop(self):
        manager = self._load_manager()
        trade = self._base_trade(symbol="YM", direction="short", entry=40000.0, leg_high=40005.0)

        manager.update_post_be_analytics(trade, 39996.0, "2026-05-29T13:01:00Z")
        manager.update_post_be_analytics(trade, 39994.0, "2026-05-29T13:02:00Z")

        self.assertEqual(trade["structural_dynamic_stop_price"], 40006.0)
        self.assertEqual(trade["structural_dynamic_stop_distance_points"], 6.0)
        self.assertEqual(trade["structural_dynamic_tp1_price"], 39994.0)
        self.assertEqual(trade["structural_dynamic_model_first_hit"], "tp1")

        with tempfile.TemporaryDirectory() as tmp_dir:
            row = self._close_and_record(manager, trade, Path(tmp_dir) / "research.jsonl")
        self.assertEqual(row["structural_dynamic_model_result"], "tp1")

    def test_structural_dynamic_stop_can_fail_before_tp1(self):
        manager = self._load_manager()
        trade = self._base_trade(symbol="NQ", direction="short", entry=100.0, leg_high=101.75)

        manager.update_post_be_analytics(trade, 101.0, "2026-05-29T13:01:00Z")
        manager.update_post_be_analytics(trade, 102.0, "2026-05-29T13:02:00Z")
        manager.update_post_be_analytics(trade, 98.0, "2026-05-29T13:03:00Z")

        self.assertEqual(trade["structural_dynamic_stop_price"], 102.0)
        self.assertTrue(trade["structural_dynamic_stop_would_hit"])
        self.assertTrue(trade["structural_dynamic_tp1_would_hit"])
        self.assertEqual(trade["structural_dynamic_model_first_hit"], "stop")

        with tempfile.TemporaryDirectory() as tmp_dir:
            row = self._close_and_record(manager, trade, Path(tmp_dir) / "research.jsonl")
        self.assertEqual(row["structural_dynamic_model_result"], "stop")

    def test_long_trade_structural_logic_uses_entry_leg_low(self):
        manager = self._load_manager()
        trade = self._base_trade(symbol="NQ", direction="long", entry=100.0, leg_low=98.25)

        manager.update_post_be_analytics(trade, 99.5, "2026-05-29T13:01:00Z")
        manager.update_post_be_analytics(trade, 102.0, "2026-05-29T13:02:00Z")

        self.assertEqual(trade["post_be_best_price"], 102.0)
        self.assertEqual(trade["post_be_worst_price"], 99.5)
        self.assertEqual(trade["post_be_mfe_points"], 2.0)
        self.assertEqual(trade["post_be_mae_points"], 0.5)
        self.assertEqual(trade["structural_dynamic_stop_price"], 98.0)
        self.assertEqual(trade["structural_dynamic_tp1_price"], 102.0)
        self.assertEqual(trade["structural_dynamic_model_first_hit"], "tp1")

    def test_fixed_8_12_16_comparison_models_are_calculated(self):
        manager = self._load_manager()
        trade = self._base_trade(symbol="NQ", direction="short", entry=100.0, leg_high=105.0)

        manager.update_post_be_analytics(trade, 98.0, "2026-05-29T13:01:00Z")
        manager.update_post_be_analytics(trade, 96.0, "2026-05-29T13:02:00Z")

        self.assertEqual(trade["fixed_8_stop_price"], 102.0)
        self.assertEqual(trade["fixed_8_tp1_price"], 98.0)
        self.assertEqual(trade["fixed_8_stop_distance_points"], 2.0)
        self.assertTrue(trade["fixed_8_tp1_would_hit"])
        self.assertEqual(trade["fixed_8_model_first_hit"], "tp1")

        self.assertEqual(trade["fixed_12_stop_price"], 103.0)
        self.assertEqual(trade["fixed_12_tp1_price"], 97.0)
        self.assertEqual(trade["fixed_12_stop_distance_points"], 3.0)
        self.assertTrue(trade["fixed_12_tp1_would_hit"])

        self.assertEqual(trade["fixed_16_stop_price"], 104.0)
        self.assertEqual(trade["fixed_16_tp1_price"], 96.0)
        self.assertEqual(trade["fixed_16_stop_distance_points"], 4.0)
        self.assertTrue(trade["fixed_16_tp1_would_hit"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            row = self._close_and_record(manager, trade, Path(tmp_dir) / "research.jsonl")
        self.assertEqual(row["fixed_8_model_result"], "tp1")
        self.assertEqual(row["fixed_12_model_result"], "tp1")
        self.assertEqual(row["fixed_16_model_result"], "tp1")

    def test_entry_leg_extremes_are_captured_from_entry_context(self):
        manager = self._load_manager()
        trade = {"symbol": "NQ", "entry_leg_high": None, "entry_leg_low": None}

        manager.capture_entry_leg_extremes(
            trade,
            {"entry_context": {"high": 30424.5, "low": 30412.75, "timestamp": "2026-05-29T13:00:00Z"}},
        )

        self.assertEqual(trade["entry_leg_high"], 30424.5)
        self.assertEqual(trade["entry_leg_low"], 30412.75)
        self.assertEqual(trade["entry_leg_timestamp"], "2026-05-29T13:00:00Z")
        self.assertEqual(trade["entry_leg_source"], "entry_context")

    def test_entry_leg_extremes_are_captured_from_successful_entry_fill_metadata(self):
        manager = self._load_manager()
        trade = {"symbol": "NQ", "entry_leg_high": None, "entry_leg_low": None}

        manager.capture_entry_leg_extremes(
            trade,
            {
                "ok": True,
                "fill_price": 30439.75,
                "current_1m_bar_high": 30451.0,
                "current_1m_bar_low": 30424.5,
                "current_1m_bar_timestamp": "2026-06-02T13:41:00",
            },
        )

        self.assertEqual(trade["entry_leg_high"], 30451.0)
        self.assertEqual(trade["entry_leg_low"], 30424.5)
        self.assertEqual(trade["entry_leg_timestamp"], "2026-06-02T13:41:00")
        self.assertEqual(trade["entry_leg_source"], "entry_context")

    def test_submit_trade_persists_successful_entry_metadata_in_trade_state(self):
        manager = self._load_manager()
        persisted = []
        manager.can_execute_trade = lambda **kwargs: (True, "ok")
        manager.resolve_execution_symbol = lambda symbol: ("NQM6", "test")
        manager.fetch_trade_entry_atr_snapshot = lambda symbol: {
            "atr_value": 10.0,
            "atr_source": "test_atr",
            "atr_bar_timestamp": "2026-06-02T13:40:00",
        }
        manager.place_entry_order = lambda **kwargs: {
            "ok": True,
            "broker_order_id": "ENTRY-1",
            "fill_price": 30439.75,
            "fill_price_source": "executor_actual_fill",
            "current_1m_bar_high": 30451.0,
            "current_1m_bar_low": 30424.5,
            "current_1m_bar_timestamp": "2026-06-02T13:41:00",
            "order": {"filled_price": 30439.75},
        }
        manager.place_stop_order = lambda **kwargs: {"ok": True, "broker_order_id": "STOP-1"}
        manager.place_limit_order = lambda **kwargs: {"ok": True, "broker_order_id": "LIMIT-1"}
        manager.persist_trade_state = lambda trade: persisted.append(dict(trade))
        manager.log_trade_event = lambda *args, **kwargs: None
        manager.register_new_trade = lambda: None

        trade = manager.submit_trade({
            "event": "enter_trade",
            "symbol": "NQ",
            "direction": "long",
            "position_size": 2,
        })

        self.assertEqual(trade["entry_leg_high"], 30451.0)
        self.assertEqual(trade["entry_leg_low"], 30424.5)
        self.assertEqual(trade["entry_leg_timestamp"], "2026-06-02T13:41:00")
        self.assertEqual(trade["entry_price"], 30439.75)
        self.assertEqual(trade["original_stop"], 30429.75)
        self.assertEqual(trade["tp1_price"], 30449.75)
        self.assertEqual(trade["be_trigger"], 30444.75)
        self.assertTrue(any(item.get("entry_leg_high") == 30451.0 for item in persisted))

    def test_research_row_uses_entry_metadata_for_half_atr_without_recovery(self):
        manager = self._load_manager()
        trade = self._base_trade(symbol="NQ", direction="long", entry=30439.75, leg_low=None)
        trade["atr_value"] = 10.0
        manager.capture_entry_leg_extremes(
            trade,
            {
                "current_1m_bar_high": 30451.0,
                "current_1m_bar_low": 30424.5,
                "current_1m_bar_timestamp": "2026-06-02T13:41:00",
            },
        )

        manager.update_post_be_analytics(trade, 30445.0, "2026-06-02T13:42:00Z")
        manager.update_post_be_analytics(trade, 30455.25, "2026-06-02T13:43:00Z")
        row = manager.build_trade_management_research_row(trade)

        self.assertEqual(row["entry_leg_high"], 30451.0)
        self.assertEqual(row["entry_leg_low"], 30424.5)
        self.assertEqual(row["entry_leg_timestamp"], "2026-06-02T13:41:00")
        self.assertTrue(row["half_atr_dynamic_enabled"])
        self.assertTrue(row["half_atr_dynamic_trigger_reached"])
        self.assertEqual(row["half_atr_dynamic_setup_extreme"], 30424.5)
        self.assertEqual(row["half_atr_dynamic_exit_reason"], "tp1")

    def test_half_atr_dynamic_trigger_adjusts_stop_and_tp1(self):
        manager = self._load_manager()
        trade = self._base_trade(symbol="NQ", direction="short", entry=100.0, leg_high=106.75)
        trade["atr_value"] = 10.0

        manager.update_post_be_analytics(trade, 95.0, "2026-05-29T13:01:00Z")

        self.assertTrue(trade["half_atr_dynamic_enabled"])
        self.assertTrue(trade["half_atr_dynamic_trigger_reached"])
        self.assertEqual(trade["half_atr_dynamic_trigger_price"], 95.0)
        self.assertEqual(trade["half_atr_dynamic_setup_extreme"], 106.75)
        self.assertEqual(trade["half_atr_dynamic_offset_ticks"], 1)
        self.assertEqual(trade["half_atr_dynamic_stop_price"], 107.0)
        self.assertEqual(trade["half_atr_dynamic_stop_distance_ticks"], 28.0)
        self.assertEqual(trade["half_atr_dynamic_tp1_price"], 93.0)
        self.assertEqual(trade["half_atr_dynamic_tp1_distance_ticks"], 28.0)

    def test_half_atr_dynamic_tp1_exits_at_adjusted_risk_distance(self):
        manager = self._load_manager()
        trade = self._base_trade(symbol="NQ", direction="short", entry=100.0, leg_high=106.75)
        trade["atr_value"] = 10.0

        manager.update_post_be_analytics(trade, 95.0, "2026-05-29T13:01:00Z")
        manager.update_post_be_analytics(trade, 93.0, "2026-05-29T13:02:00Z")

        self.assertEqual(trade["half_atr_dynamic_exit_price"], 93.0)
        self.assertEqual(trade["half_atr_dynamic_exit_reason"], "tp1")
        self.assertEqual(trade["half_atr_dynamic_result_r"], 1.0)

    def test_half_atr_dynamic_keeps_original_when_structural_stop_worse(self):
        manager = self._load_manager()
        trade = self._base_trade(symbol="NQ", direction="short", entry=100.0, leg_high=106.75)
        trade["atr_value"] = 10.0
        trade["original_stop"] = 104.0
        trade["tp1_price"] = 96.0

        manager.update_post_be_analytics(trade, 95.0, "2026-05-29T13:01:00Z")

        self.assertTrue(trade["half_atr_dynamic_enabled"])
        self.assertTrue(trade["half_atr_dynamic_used_original_stop"])
        self.assertEqual(trade["half_atr_dynamic_stop_price"], 104.0)
        self.assertEqual(trade["half_atr_dynamic_stop_distance_ticks"], 16.0)
        self.assertEqual(trade["half_atr_dynamic_tp1_price"], 96.0)

    def test_half_atr_dynamic_missing_setup_extreme_is_not_evaluable(self):
        manager = self._load_manager()
        trade = self._base_trade(symbol="NQ", direction="short", entry=100.0, leg_high=None)
        trade["atr_value"] = 10.0

        manager.update_post_be_analytics(trade, 95.0, "2026-05-29T13:01:00Z")
        row = manager.build_trade_management_research_row(trade)

        self.assertFalse(row["half_atr_dynamic_enabled"])
        self.assertFalse(row["half_atr_dynamic_trigger_reached"])
        self.assertEqual(row["half_atr_dynamic_helped_hurt_same"], "unable_to_evaluate")
        self.assertEqual(row["half_atr_dynamic_unable_to_evaluate_reason"], "missing_setup_extreme")

    def test_half_atr_dynamic_live_trade_fields_are_unchanged(self):
        manager = self._load_manager()
        trade = self._base_trade(symbol="NQ", direction="short", entry=100.0, leg_high=106.75)
        trade["atr_value"] = 10.0
        before = {
            "original_stop": trade["original_stop"],
            "current_stop": trade["current_stop"],
            "tp1_price": trade["tp1_price"],
            "be_trigger": trade["be_trigger"],
        }

        manager.update_post_be_analytics(trade, 95.0, "2026-05-29T13:01:00Z")

        self.assertEqual(trade["original_stop"], before["original_stop"])
        self.assertEqual(trade["current_stop"], before["current_stop"])
        self.assertEqual(trade["tp1_price"], before["tp1_price"])
        self.assertEqual(trade["be_trigger"], before["be_trigger"])


if __name__ == "__main__":
    unittest.main()
