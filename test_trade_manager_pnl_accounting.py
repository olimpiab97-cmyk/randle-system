import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class TradeManagerPnlAccountingTests(unittest.TestCase):
    def _load_manager(self):
        spec = importlib.util.spec_from_file_location(
            "trade_manager_pnl_accounting_under_test",
            ROOT / "Engines" / "trade_manager.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_closed_nq_runner_flatten_total_pnl_includes_tp1_and_runner(self):
        manager = self._load_manager()
        trade = {
            "trade_id": "T-pnl-regression",
            "status": "active",
            "symbol": "NQ",
            "direction": "short",
            "entry_price": 21000.0,
            "position_size": 2,
            "remaining_size": 1,
            "tp1_hit": True,
            "tp1_filled_qty": 1,
            "tp1_exit_price": 20972.0,
            "tp1_price": 20972.0,
            "last_price": 20720.0,
            "current_stop": 21010.0,
        }
        evidence_order = {
            "order_id": "FLAT-1",
            "trade_id": trade["trade_id"],
            "status": "closed",
            "closed_reason": "flatten_symbol",
            "closed_at": "2026-05-12T12:00:00-07:00",
            "last_price": 20720.0,
        }

        closed = manager.close_trade_from_executor_flatten_evidence(trade, evidence_order)

        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["exit_reason"], "flatten_symbol")
        self.assertEqual(closed["exit_price"], 20720.0)
        self.assertEqual(closed["tp1_profit"], 560.0)
        self.assertEqual(closed["runner_profit"], 5600.0)
        self.assertEqual(closed["total_profit"], 6160.0)
        self.assertEqual(closed["realized_pnl"], 6160.0)
        self.assertEqual(closed["total_pnl"], 6160.0)

    def test_tp1_then_runner_flatten_archives_win_from_total_realized_pnl(self):
        manager = self._load_manager()
        trade = {
            "trade_id": "T-NQ-2026-06-02",
            "status": "active",
            "symbol": "NQ",
            "direction": "long",
            "entry_price": 30439.75,
            "original_stop": 30427.75,
            "current_stop": 30439.75,
            "position_size": 2,
            "remaining_size": 1,
            "moved_to_be": True,
            "be_hit_at": "2026-06-02T13:35:00Z",
            "stop_state": "break_even",
            "tp1_hit": True,
            "tp1_hit_at": "2026-06-02T13:36:00Z",
            "tp1_filled_qty": 1,
            "tp1_exit_price": 30463.75,
            "tp1_price": 30463.75,
            "realized_pnl": 0.0,
            "total_pnl": 0.0,
            "total_profit": 0.0,
        }
        evidence_order = {
            "order_id": "FLAT-NQ",
            "trade_id": trade["trade_id"],
            "status": "closed",
            "closed_reason": "flatten_symbol",
            "closed_at": "2026-06-02T13:45:00Z",
            "filled_price": 30439.75,
        }

        closed = manager.close_trade_from_executor_flatten_evidence(trade, evidence_order)
        archived = manager.public_trade_dict(closed)

        self.assertEqual(closed["exit_reason"], "flatten_symbol")
        self.assertEqual(closed["tp1_profit"], 480.0)
        self.assertEqual(closed["runner_profit"], 0.0)
        self.assertEqual(closed["realized_pnl"], 480.0)
        self.assertEqual(closed["total_pnl"], 480.0)
        self.assertEqual(closed["result"], "WIN")
        self.assertEqual(closed["r_multiple"], 1.0)
        self.assertEqual(archived["realized_pnl"], 480.0)
        self.assertEqual(archived["total_pnl"], 480.0)
        self.assertEqual(archived["total_profit"], 480.0)
        self.assertEqual(archived["result"], "WIN")
        self.assertEqual(archived["r_multiple"], 1.0)

    def test_tp1_then_runner_original_stop_archives_tp1_profit_plus_runner_loss(self):
        manager = self._load_manager()
        trade = {
            "trade_id": "T-NQ-ORIGINAL-STOP",
            "status": "active",
            "symbol": "NQ",
            "direction": "long",
            "entry_price": 30439.75,
            "original_stop": 30427.75,
            "current_stop": 30427.75,
            "position_size": 2,
            "remaining_size": 1,
            "moved_to_be": True,
            "be_hit_at": "2026-06-02T13:35:00Z",
            "stop_state": "runner_original",
            "tp1_hit": True,
            "tp1_hit_at": "2026-06-02T13:36:00Z",
            "tp1_filled_qty": 1,
            "tp1_exit_price": 30463.75,
            "tp1_price": 30463.75,
            "realized_pnl": 0.0,
            "total_pnl": 0.0,
            "total_profit": 0.0,
        }
        stop_order = {
            "order_id": "STOP-NQ",
            "trade_id": trade["trade_id"],
            "status": "closed",
            "closed_reason": "stop_triggered",
            "closed_at": "2026-06-02T13:45:00Z",
            "filled_at": "2026-06-02T13:45:00Z",
            "filled_price": 30427.75,
            "stop_price": 30427.75,
        }

        closed = manager.close_trade_from_executor_stop_fill(trade, stop_order)
        archived = manager.public_trade_dict(closed)

        self.assertEqual(closed["exit_reason"], "stop_hit")
        self.assertEqual(closed["tp1_profit"], 480.0)
        self.assertEqual(closed["runner_profit"], -240.0)
        self.assertEqual(closed["realized_pnl"], 240.0)
        self.assertEqual(closed["total_pnl"], 240.0)
        self.assertEqual(closed["result"], "WIN")
        self.assertEqual(closed["r_multiple"], 0.5)
        self.assertEqual(archived["realized_pnl"], 240.0)
        self.assertEqual(archived["total_pnl"], 240.0)
        self.assertEqual(archived["total_profit"], 240.0)
        self.assertEqual(archived["result"], "WIN")
        self.assertEqual(archived["r_multiple"], 0.5)


if __name__ == "__main__":
    unittest.main()
