import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent


class TradeManagerManualExitLimitTests(unittest.TestCase):
    def _load_manager(self):
        spec = importlib.util.spec_from_file_location(
            "trade_manager_manual_exit_limit_under_test",
            ROOT / "Engines" / "trade_manager.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _active_state(self):
        return {
            "system": {},
            "trades": {
                "T-MANUAL": {
                    "trade_id": "T-MANUAL",
                    "status": "active",
                    "symbol": "NQM6",
                    "direction": "long",
                    "position_size": 2,
                    "remaining_size": 2,
                    "oco_group": "OCO-T-MANUAL-PROTECTIVE",
                    "tp1_order_id": "LIMIT-TP1",
                }
            },
            "orders": {},
            "event_log": [],
            "risk_state": {},
            "failure_state": {},
        }

    def _executor_orders(self):
        return [
            {
                "order_id": "STOP-PROTECTIVE",
                "trade_id": "T-MANUAL",
                "type": "stop",
                "symbol": "NQM6",
                "qty": 2.0,
                "stop_price": 26980.0,
                "status": "active",
                "oco_group": "OCO-T-MANUAL-PROTECTIVE",
                "oco_role": "protective_stop",
            }
        ]

    def test_manual_exit_limit_validates_and_dispatches_reduce_only_executor_action(self):
        manager = self._load_manager()
        dispatched = []

        def fake_dispatch(action, payload, watch_failures=True):
            dispatched.append((action, payload, watch_failures))
            return {
                "ok": True,
                "broker_order_id": "LIMIT-MANUAL",
                "order": {
                    "order_id": "LIMIT-MANUAL",
                    "type": "limit",
                    "tag": "manual_exit_limit",
                },
            }

        with patch.object(manager, "load_state", return_value=self._active_state()), \
             patch.object(manager, "fetch_executor_snapshot", return_value={
                 "NQM6": {
                     "position_qty": 2.0,
                     "last_price": 27010.0,
                 }
             }), \
             patch.object(manager, "fetch_executor_orders", return_value=self._executor_orders()), \
             patch.object(manager, "dispatch_execution", side_effect=fake_dispatch), \
             patch.object(manager, "save_state", lambda *args, **kwargs: None), \
             patch.object(manager, "log_trade_event", lambda *args, **kwargs: None):
            response = manager.app.test_client().post(
                "/trades/T-MANUAL/manual_exit_limit",
                json={
                    "symbol": "NQ",
                    "price": 27025.0,
                    "quantity": 1,
                    "manual_confirmation": True,
                    "intent": "manual_exit_limit",
                    "replace_existing_tp": True,
                    "level_label": "YL",
                },
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(len(dispatched), 1)
        action, payload, watch_failures = dispatched[0]
        self.assertEqual(action, "set_manual_exit_limit")
        self.assertFalse(watch_failures)
        self.assertEqual(payload["trade_id"], "T-MANUAL")
        self.assertEqual(payload["symbol"], "NQM6")
        self.assertEqual(payload["limit_price"], 27025.0)
        self.assertEqual(payload["qty"], 1.0)
        self.assertTrue(payload["manual_confirmation"])
        self.assertEqual(payload["intent"], "manual_exit_limit")
        self.assertTrue(payload["replace_existing_tp"])
        self.assertEqual(payload["level_label"], "YL")
        self.assertEqual(payload["oco_group"], "OCO-T-MANUAL-PROTECTIVE")

    def test_manual_exit_limit_rejects_missing_manual_confirmation(self):
        manager = self._load_manager()

        with patch.object(manager, "load_state", return_value=self._active_state()):
            response = manager.app.test_client().post(
                "/trades/T-MANUAL/manual_exit_limit",
                json={
                    "symbol": "NQ",
                    "price": 27025.0,
                    "quantity": 1,
                    "intent": "manual_exit_limit",
                },
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "manual_confirmation_required")

    def test_manual_exit_limit_rejects_closed_trade(self):
        manager = self._load_manager()
        state = self._active_state()
        state["trades"]["T-MANUAL"]["status"] = "closed"

        with patch.object(manager, "load_state", return_value=state):
            response = manager.app.test_client().post(
                "/trades/T-MANUAL/manual_exit_limit",
                json={
                    "symbol": "NQ",
                    "price": 27025.0,
                    "quantity": 1,
                    "manual_confirmation": True,
                    "intent": "manual_exit_limit",
                },
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "trade_not_active")

    def test_manual_exit_limit_rejects_long_exit_below_current_price(self):
        manager = self._load_manager()

        with patch.object(manager, "load_state", return_value=self._active_state()), \
             patch.object(manager, "fetch_executor_snapshot", return_value={
                 "NQM6": {
                     "position_qty": 2.0,
                     "last_price": 27010.0,
                 }
             }), \
             patch.object(manager, "fetch_executor_orders", return_value=self._executor_orders()):
            response = manager.app.test_client().post(
                "/trades/T-MANUAL/manual_exit_limit",
                json={
                    "symbol": "NQ",
                    "price": 27000.0,
                    "quantity": 1,
                    "manual_confirmation": True,
                    "intent": "manual_exit_limit",
                },
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "invalid_exit_limit_direction")

    def test_manual_exit_limit_rejects_invalid_tick_increment(self):
        manager = self._load_manager()

        with patch.object(manager, "load_state", return_value=self._active_state()), \
             patch.object(manager, "fetch_executor_snapshot", return_value={
                 "NQM6": {
                     "position_qty": 2.0,
                     "last_price": 27010.0,
                 }
             }), \
             patch.object(manager, "fetch_executor_orders", return_value=self._executor_orders()):
            response = manager.app.test_client().post(
                "/trades/T-MANUAL/manual_exit_limit",
                json={
                    "symbol": "NQ",
                    "price": 27025.13,
                    "quantity": 1,
                    "manual_confirmation": True,
                    "intent": "manual_exit_limit",
                },
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "invalid_tick_increment")

    def test_manual_exit_limit_rejects_when_oco_linkage_not_confirmed(self):
        manager = self._load_manager()

        with patch.object(manager, "load_state", return_value=self._active_state()), \
             patch.object(manager, "fetch_executor_snapshot", return_value={
                 "NQM6": {
                     "position_qty": 2.0,
                     "last_price": 27010.0,
                 }
             }), \
             patch.object(manager, "fetch_executor_orders", return_value=[]):
            response = manager.app.test_client().post(
                "/trades/T-MANUAL/manual_exit_limit",
                json={
                    "symbol": "NQ",
                    "price": 27025.0,
                    "quantity": 1,
                    "manual_confirmation": True,
                    "intent": "manual_exit_limit",
                },
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "oco_linkage_not_confirmed")

    def test_reconcile_closes_trade_from_filled_manual_exit_limit(self):
        manager = self._load_manager()
        trade = self._active_state()["trades"]["T-MANUAL"]
        trade.update({
            "entry_price": 27000.0,
            "manual_exit_order_id": "LIMIT-MANUAL",
        })
        manual_order = {
            "order_id": "LIMIT-MANUAL",
            "trade_id": "T-MANUAL",
            "type": "limit",
            "symbol": "NQM6",
            "limit_price": 27025.0,
            "qty": 2.0,
            "status": "closed",
            "filled_at": "2026-05-24T10:00:00",
            "filled_price": 27025.0,
            "filled_qty": 2.0,
            "closed_reason": "limit_triggered",
            "tag": "manual_exit_limit",
            "oco_role": "manual_exit_limit",
        }

        updated = manager.reconcile_trade_with_executor_activity(
            trade,
            [manual_order],
            {"NQM6": {"position_qty": 0.0}},
        )

        self.assertEqual(updated["status"], "closed")
        self.assertEqual(updated["exit_reason"], "manual_exit_limit")
        self.assertEqual(updated["remaining_size"], 0)
        self.assertEqual(updated["manual_exit_filled_qty"], 2.0)
        self.assertEqual(updated["manual_exit_price"], 27025.0)
        self.assertEqual(updated["realized_pnl"], 1000.0)


if __name__ == "__main__":
    unittest.main()
