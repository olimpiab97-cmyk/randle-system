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

    def _stale_archived_nq_long(self, **overrides):
        trade = {
            "trade_id": "T-NQ-ARCHIVED",
            "status": "archived",
            "archived": True,
            "symbol": "NQ",
            "direction": "long",
            "entry_price": 30439.75,
            "original_stop": 30427.75,
            "position_size": 2,
            "remaining_size": 0,
            "closed_at": "2026-06-02T13:45:00Z",
            "tp1_hit": True,
            "tp1_hit_at": "2026-06-02T13:36:00Z",
            "tp1_filled_qty": 1,
            "tp1_exit_price": 30463.75,
            "tp1_price": 30463.75,
            "tp1_profit": None,
            "runner_profit": None,
            "total_profit": 0.0,
            "realized_pnl": 0.0,
            "total_pnl": 0.0,
            "result": "BE",
            "r_multiple": 0.0,
        }
        trade.update(overrides)
        return trade

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
        self.assertEqual(closed["runner_exit_price"], 20720.0)
        self.assertEqual(closed["runner_exit_price_source"], "last_price")
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
        self.assertEqual(closed["runner_exit_price"], 30439.75)
        self.assertEqual(closed["runner_exit_price_source"], "filled_price")
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

    def test_tp1_then_runner_flatten_uses_actual_fill_for_full_trade_pnl(self):
        manager = self._load_manager()
        trade = {
            "trade_id": "T-NQ-FULL-FLATTEN-PNL",
            "status": "active",
            "symbol": "NQ",
            "direction": "long",
            "entry_price": 30439.75,
            "original_stop": 30415.75,
            "current_stop": 30415.75,
            "position_size": 2,
            "remaining_size": 1,
            "tp1_hit": True,
            "tp1_filled_qty": 1,
            "tp1_exit_price": 30463.75,
            "tp1_price": 30463.75,
            "realized_pnl": 0.0,
            "total_pnl": 0.0,
            "total_profit": 0.0,
        }
        evidence_order = {
            "order_id": "FLAT-NQ-ACTUAL",
            "trade_id": trade["trade_id"],
            "status": "closed",
            "closed_reason": "flatten_symbol",
            "closed_at": "2026-06-02T16:03:12Z",
            "filled_price": 30611.0,
        }

        closed = manager.close_trade_from_executor_flatten_evidence(trade, evidence_order)
        archived = manager.public_trade_dict(closed)

        self.assertEqual(closed["exit_reason"], "flatten_symbol")
        self.assertEqual(closed["exit_price"], 30611.0)
        self.assertEqual(closed["runner_exit_price"], 30611.0)
        self.assertEqual(closed["runner_exit_price_source"], "filled_price")
        self.assertEqual(closed["tp1_profit"], 480.0)
        self.assertEqual(closed["runner_profit"], 3425.0)
        self.assertEqual(closed["total_profit"], 3905.0)
        self.assertEqual(closed["realized_pnl"], 3905.0)
        self.assertEqual(closed["total_pnl"], 3905.0)
        self.assertEqual(closed["result"], "WIN")
        self.assertEqual(closed["r_multiple"], 4.0677)
        self.assertEqual(archived["runner_exit_price"], 30611.0)
        self.assertEqual(archived["runner_profit"], 3425.0)
        self.assertEqual(archived["total_profit"], 3905.0)
        self.assertEqual(archived["realized_pnl"], 3905.0)
        self.assertEqual(archived["total_pnl"], 3905.0)
        self.assertEqual(archived["result"], "WIN")
        self.assertEqual(archived["r_multiple"], 4.0677)

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

    def test_stale_archived_flatten_record_public_serialization_backfills_total_pnl(self):
        manager = self._load_manager()
        stale_archived = {
            "trade_id": "T-NQ-STALE-ARCHIVE",
            "status": "archived",
            "archived": True,
            "symbol": "NQ",
            "direction": "long",
            "entry_price": 30439.75,
            "original_stop": 30427.75,
            "position_size": 2,
            "remaining_size": 0,
            "exit_reason": "flatten_symbol",
            "exit_price": 30439.75,
            "closed_at": "2026-06-02T13:45:00Z",
            "tp1_hit": True,
            "tp1_hit_at": "2026-06-02T13:36:00Z",
            "tp1_filled_qty": 1,
            "tp1_exit_price": 30463.75,
            "tp1_price": 30463.75,
            "tp1_profit": None,
            "runner_profit": None,
            "total_profit": 0.0,
            "realized_pnl": 0.0,
            "total_pnl": 0.0,
            "result": "BE",
            "r_multiple": 0.0,
        }

        archived = manager.public_trade_dict(stale_archived)

        self.assertEqual(archived["status"], "archived")
        self.assertEqual(archived["exit_reason"], "flatten_symbol")
        self.assertEqual(archived["tp1_profit"], 480.0)
        self.assertEqual(archived["runner_profit"], 0.0)
        self.assertEqual(archived["total_profit"], 480.0)
        self.assertEqual(archived["realized_pnl"], 480.0)
        self.assertEqual(archived["total_pnl"], 480.0)
        self.assertEqual(archived["result"], "WIN")
        self.assertEqual(archived["r_multiple"], 1.0)

    def test_kpi_serialization_backfills_stale_flatten_stop_price_record(self):
        manager = self._load_manager()
        stale_closed = {
            "trade_id": "T-ce62f567",
            "status": "closed",
            "archived": True,
            "symbol": "NQM6",
            "direction": "long",
            "entry_price": 30439.75,
            "original_stop": 30415.75,
            "current_stop": 30415.75,
            "position_size": 2,
            "remaining_size": 0,
            "exit_reason": "flatten_symbol",
            "exit_price": 30415.75,
            "closed_at": "2026-06-02T09:03:12.390174",
            "tp1_hit": True,
            "tp1_filled_qty": 1,
            "tp1_exit_price": 30463.75,
            "tp1_price": 30463.75,
            "tp1_profit": 480.0,
            "runner_profit": -480.0,
            "total_profit": 0.0,
            "realized_pnl": 0.0,
            "total_pnl": 0.0,
            "result": "BE",
            "r_multiple": 0.0,
        }

        serialized = manager.public_trade_dict(stale_closed)

        self.assertEqual(serialized["exit_reason"], "flatten_symbol")
        self.assertEqual(serialized["tp1_profit"], 480.0)
        self.assertEqual(serialized["runner_profit"], 0.0)
        self.assertEqual(serialized["total_profit"], 480.0)
        self.assertEqual(serialized["realized_pnl"], 480.0)
        self.assertEqual(serialized["total_pnl"], 480.0)
        self.assertEqual(serialized["result"], "WIN")
        self.assertEqual(serialized["r_multiple"], 0.5)

    def test_kpi_serialization_repairs_stale_flatten_stop_exit_from_last_price(self):
        manager = self._load_manager()
        stale_closed = {
            "trade_id": "T-ce62f567",
            "status": "closed",
            "archived": True,
            "symbol": "NQM6",
            "direction": "long",
            "entry_price": 30439.75,
            "original_stop": 30415.75,
            "current_stop": 30415.75,
            "position_size": 2,
            "remaining_size": 0,
            "exit_reason": "flatten_symbol",
            "exit_price": 30415.75,
            "closed_at": "2026-06-02T09:03:12.390174",
            "last_price": 30611.0,
            "last_price_at": "2026-06-02T16:03:12Z",
            "tp1_hit": True,
            "tp1_filled_qty": 1,
            "tp1_exit_price": 30463.75,
            "tp1_price": 30463.75,
            "tp1_profit": 480.0,
            "runner_profit": -480.0,
            "total_profit": 0.0,
            "realized_pnl": 0.0,
            "total_pnl": 0.0,
            "result": "BE",
            "r_multiple": 0.0,
        }

        serialized = manager.public_trade_dict(stale_closed)

        self.assertEqual(serialized["exit_price"], 30611.0)
        self.assertEqual(serialized["runner_exit_price"], 30611.0)
        self.assertEqual(serialized["runner_exit_price_source"], "trade_last_price")
        self.assertEqual(serialized["tp1_profit"], 480.0)
        self.assertEqual(serialized["runner_profit"], 3425.0)
        self.assertEqual(serialized["total_profit"], 3905.0)
        self.assertEqual(serialized["realized_pnl"], 3905.0)
        self.assertEqual(serialized["total_pnl"], 3905.0)
        self.assertEqual(serialized["result"], "WIN")
        self.assertEqual(serialized["r_multiple"], 4.0677)

        rows = [{"pnl": serialized["total_profit"]}]
        total_pnl = sum(row["pnl"] for row in rows)
        starting_equity = 100000.0
        equity_points = [starting_equity]
        cumulative = 0.0
        for row in rows:
            cumulative += row["pnl"]
            equity_points.append(starting_equity + cumulative)

        self.assertEqual(total_pnl, 3905.0)
        self.assertEqual(equity_points[-1], 103905.0)
        self.assertEqual(max(row["pnl"] for row in rows), 3905.0)

    def test_archived_tp1_runner_flatten_backfills_full_accounting(self):
        manager = self._load_manager()
        archived = manager.public_trade_dict(self._stale_archived_nq_long(
            trade_id="T-NQ-ARCHIVED-FLAT-WIN",
            exit_reason="flatten_symbol",
            exit_price=30451.75,
        ))

        self.assertEqual(archived["result"], "WIN")
        self.assertEqual(archived["tp1_profit"], 480.0)
        self.assertEqual(archived["runner_profit"], 240.0)
        self.assertEqual(archived["total_profit"], 720.0)
        self.assertEqual(archived["realized_pnl"], 720.0)
        self.assertEqual(archived["total_pnl"], 720.0)
        self.assertEqual(archived["r_multiple"], 1.5)

    def test_archived_tp1_runner_original_stop_uses_total_profit_not_runner_outcome(self):
        manager = self._load_manager()
        archived = manager.public_trade_dict(self._stale_archived_nq_long(
            trade_id="T-NQ-ARCHIVED-RUNNER-STOP",
            exit_reason="stop_hit",
            exit_price=30427.75,
            current_stop=30427.75,
            stop_state="runner_original",
        ))

        self.assertEqual(archived["tp1_profit"], 480.0)
        self.assertEqual(archived["runner_profit"], -240.0)
        self.assertEqual(archived["total_profit"], 240.0)
        self.assertEqual(archived["realized_pnl"], 240.0)
        self.assertEqual(archived["total_pnl"], 240.0)
        self.assertEqual(archived["result"], "WIN")
        self.assertEqual(archived["r_multiple"], 0.5)

    def test_archived_full_stop_without_tp1_remains_loss(self):
        manager = self._load_manager()
        archived = manager.public_trade_dict(self._stale_archived_nq_long(
            trade_id="T-NQ-ARCHIVED-FULL-STOP",
            tp1_hit=False,
            tp1_hit_at=None,
            tp1_filled_qty=None,
            tp1_exit_price=None,
            tp1_price=30463.75,
            exit_reason="stop_hit",
            exit_price=30427.75,
        ))

        self.assertIsNone(archived["tp1_profit"])
        self.assertEqual(archived["runner_profit"], -480.0)
        self.assertEqual(archived["total_profit"], -480.0)
        self.assertEqual(archived["realized_pnl"], -480.0)
        self.assertEqual(archived["total_pnl"], -480.0)
        self.assertEqual(archived["result"], "LOSS")
        self.assertEqual(archived["r_multiple"], -1.0)

    def test_active_trade_public_serialization_does_not_force_archived_result_fields(self):
        manager = self._load_manager()
        active = {
            "trade_id": "T-NQ-ACTIVE-PARTIAL",
            "status": "active",
            "symbol": "NQ",
            "direction": "long",
            "entry_price": 30439.75,
            "original_stop": 30427.75,
            "position_size": 2,
            "remaining_size": 1,
            "last_price": 30445.75,
            "tp1_hit": True,
            "tp1_filled_qty": 1,
            "tp1_exit_price": 30463.75,
            "tp1_price": 30463.75,
            "realized_pnl": None,
            "total_pnl": 0.0,
        }

        serialized = manager.public_trade_dict(active)

        self.assertEqual(serialized["status"], "active")
        self.assertEqual(serialized["tp1_profit"], 480.0)
        self.assertEqual(serialized["realized_pnl"], 480.0)
        self.assertEqual(serialized["unrealized_pnl"], 120.0)
        self.assertEqual(serialized["total_pnl"], 600.0)
        self.assertIsNone(serialized["result"])
        self.assertIsNone(serialized["r_multiple"])


if __name__ == "__main__":
    unittest.main()
