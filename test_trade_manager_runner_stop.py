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

    def _load_executor(self):
        spec = importlib.util.spec_from_file_location(
            "executor_runner_stop_under_test",
            ROOT / "executor.py",
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

        def fake_reset_stop_to_original(**kwargs):
            calls.append(kwargs)
            return {"ok": True, "broker_order_id": "STOP-RUNNER-ORIGINAL"}

        manager.reset_stop_to_original = fake_reset_stop_to_original

    def test_tp1_after_be_returns_long_runner_stop_to_original(self):
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
        self.assertEqual(trade["current_stop"], trade["original_stop"])
        self.assertEqual(trade["stop_state"], "runner_original")
        self.assertTrue(trade["moved_to_be"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["stop_price"], trade["original_stop"])
        self.assertEqual(calls[0]["qty"], 1.0)
        self.assertEqual(calls[0]["oco_parent_group"], "OCO-T-runner-long-PROTECTIVE")

    def test_tp1_before_be_returns_short_runner_stop_to_original(self):
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
        self.assertEqual(trade["current_stop"], trade["original_stop"])
        self.assertEqual(trade["stop_state"], "runner_original")
        self.assertTrue(trade["moved_to_be"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["stop_price"], trade["original_stop"])
        self.assertEqual(calls[0]["qty"], 1.0)
        self.assertEqual(calls[0]["oco_parent_group"], "OCO-T-runner-short-PROTECTIVE")

    def test_reconciliation_resets_entry_stop_back_to_original_after_tp1(self):
        manager = self._load_manager()
        calls = []
        self._patch_side_effects(manager, calls)
        trade = {
            "trade_id": "T-runner-reconcile",
            "status": "active",
            "symbol": "NQ",
            "direction": "short",
            "entry_price": 21000.0,
            "original_stop": 21018.0,
            "current_stop": 21000.0,
            "stop_order_id": "STOP-RUNNER",
            "tp1_order_id": "TP1-RUNNER",
            "tp1_price": 20972.0,
            "position_size": 2,
            "remaining_size": 1,
            "moved_to_be": True,
            "be_state_locked": True,
            "stop_state": "break_even",
            "tp1_hit": True,
            "tp1_hit_at": "2026-05-12T06:55:00-07:00",
        }
        executor_orders = [
            {
                "trade_id": "T-runner-reconcile",
                "order_id": "STOP-RUNNER",
                "type": "stop",
                "status": "active",
                "symbol": "NQ",
                "stop_price": 21000.0,
                "qty": 1,
            },
        ]
        executor_snapshot = {"NQ": {"position_qty": -1}}

        manager.reconcile_trade_with_executor_activity(
            trade,
            executor_orders,
            executor_snapshot,
        )

        self.assertEqual(trade["remaining_size"], 1.0)
        self.assertEqual(trade["current_stop"], trade["original_stop"])
        self.assertEqual(trade["stop_state"], "runner_original")
        self.assertTrue(trade["moved_to_be"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["stop_price"], trade["original_stop"])
        self.assertEqual(calls[0]["qty"], 1.0)
        self.assertEqual(calls[0]["oco_parent_group"], "OCO-T-runner-reconcile-PROTECTIVE")

    def test_reset_stop_to_original_recreates_post_tp1_runner_at_original(self):
        executor = self._load_executor()
        executor.ORDERS.clear()
        executor.POSITIONS.clear()
        executor.LAST_PRICES.clear()
        executor.save_executor_state = lambda: None
        executor.log = lambda *args, **kwargs: None
        executor.validate_execution_safety = lambda payload: {"ok": True, "context": {}}
        executor.validate_order_risk_caps = lambda payload: {"ok": True}
        executor.ORDERS["STOP-OLD"] = {
            "order_id": "STOP-OLD",
            "trade_id": "T-df6563d1",
            "type": "stop",
            "status": "active",
            "symbol": "NQM6",
            "qty": 1.0,
            "stop_price": 29283.25,
            "tag": "breakeven",
            "oco_parent_group": "OCO-T-df6563d1-PROTECTIVE",
            "oco_role": "runner_stop",
            "update_reason": "resized_after_limit_fill",
        }
        executor.POSITIONS["NQM6"] = {
            "qty": -1.0,
            "avg_entry_price": 29283.25,
        }

        response = executor.app.test_client().post(
            "/execute",
            json={
                "action": "reset_stop_to_original",
                "trade_id": "T-df6563d1",
                "symbol": "NQM6",
                "stop_price": 29311.25,
                "qty": 1.0,
                "oco_parent_group": "OCO-T-df6563d1-PROTECTIVE",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(executor.ORDERS["STOP-OLD"]["status"], "cancelled")
        new_stop = executor.ORDERS[payload["new_stop_id"]]
        self.assertEqual(new_stop["stop_price"], 29311.25)
        self.assertEqual(new_stop["qty"], 1.0)
        self.assertEqual(new_stop["tag"], "runner_reset")
        self.assertEqual(new_stop["oco_role"], "runner_stop")


if __name__ == "__main__":
    unittest.main()
