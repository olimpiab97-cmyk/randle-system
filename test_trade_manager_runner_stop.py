import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class TradeManagerRunnerStopTests(unittest.TestCase):
    def _load_manager(self):
        spec = importlib.util.spec_from_file_location(
            "trade_manager_runner_stop_under_test",
            ROOT / "Engines" / "trade_manager.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _patch_side_effects(self, manager, calls):
        manager.persist_trade_state = lambda trade: None
        manager.log_trade_event = lambda *args, **kwargs: None
        manager.lock_be_state = lambda trade, timestamp: trade.update({
            "be_state_locked": True,
            "be_trigger_processed_at": trade.get("be_trigger_processed_at") or timestamp,
        }) or trade
        manager.fetch_executor_orders = lambda: []

        def fake_modify_stop_order(**kwargs):
            calls.append(kwargs)
            return {"ok": True, "broker_order_id": kwargs["broker_order_id"]}

        manager.modify_stop_order = fake_modify_stop_order

    def test_tp1_after_be_keeps_long_runner_stop_at_entry(self):
        manager = self._load_manager()
        calls = []
        self._patch_side_effects(manager, calls)
        trade = {
            "trade_id": "T-runner-long",
            "status": "active",
            "symbol": "NQ",
            "direction": "long",
            "entry_price": 28906.25,
            "original_stop": 28888.25,
            "current_stop": 28906.25,
            "stop_order_id": "STOP-LONG",
            "tp1_order_id": "TP1-LONG",
            "tp1_price": 28934.25,
            "position_size": 2,
            "remaining_size": 2,
            "moved_to_be": True,
            "stop_state": "break_even",
            "tp1_hit": False,
        }

        manager.handle_tp1_hit(trade, "2026-05-12T06:55:00-07:00")

        self.assertEqual(trade["remaining_size"], 1.0)
        self.assertEqual(trade["current_stop"], trade["entry_price"])
        self.assertEqual(trade["stop_state"], "runner_entry")
        self.assertTrue(trade["moved_to_be"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["stop_price"], trade["entry_price"])
        self.assertEqual(calls[0]["qty"], 1.0)
        self.assertEqual(calls[0]["broker_order_id"], "STOP-LONG")
        self.assertEqual(calls[0]["tag"], "runner_entry")

    def test_tp1_before_be_moves_short_runner_stop_to_entry(self):
        manager = self._load_manager()
        calls = []
        self._patch_side_effects(manager, calls)
        trade = {
            "trade_id": "T-runner-short",
            "status": "active",
            "symbol": "NQ",
            "direction": "short",
            "entry_price": 21000.0,
            "original_stop": 21018.0,
            "current_stop": 21018.0,
            "stop_order_id": "STOP-SHORT",
            "tp1_order_id": "TP1-SHORT",
            "tp1_price": 20972.0,
            "position_size": 2,
            "remaining_size": 2,
            "moved_to_be": False,
            "stop_state": "original",
            "tp1_hit": False,
        }

        manager.handle_tp1_hit(trade, "2026-05-12T06:55:00-07:00")

        self.assertEqual(trade["remaining_size"], 1.0)
        self.assertEqual(trade["current_stop"], trade["entry_price"])
        self.assertEqual(trade["stop_state"], "runner_entry")
        self.assertTrue(trade["moved_to_be"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["stop_price"], trade["entry_price"])
        self.assertEqual(calls[0]["qty"], 1.0)
        self.assertEqual(calls[0]["broker_order_id"], "STOP-SHORT")
        self.assertEqual(calls[0]["tag"], "runner_entry")


if __name__ == "__main__":
    unittest.main()
