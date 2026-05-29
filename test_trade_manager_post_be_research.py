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


if __name__ == "__main__":
    unittest.main()
