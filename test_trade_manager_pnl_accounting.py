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


if __name__ == "__main__":
    unittest.main()
