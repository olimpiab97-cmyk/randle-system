import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
import symbol_resolution


ROOT = Path(__file__).resolve().parent


class OfflineReplayTests(unittest.TestCase):
    def setUp(self):
        sys.dont_write_bytecode = True
        self._original_mode_env = self._clear_mode_env()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.manager = self._load_module("offline_trade_manager", ROOT / "Engines" / "trade_manager.py")
        self.executor = self._load_module("offline_executor", ROOT / "executor.py")
        self._patch_state_paths()
        self._reset_runtime()
        self._wire_manager_to_executor()

    def tearDown(self):
        self.tmp.cleanup()
        self._restore_mode_env()

    def _clear_mode_env(self):
        return __import__("os").environ.pop("RANDLE_TRADE_MANAGER_MODE", None)

    def _restore_mode_env(self):
        import os
        if self._original_mode_env is None:
            os.environ.pop("RANDLE_TRADE_MANAGER_MODE", None)
        else:
            os.environ["RANDLE_TRADE_MANAGER_MODE"] = self._original_mode_env

    def _load_module(self, name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _patch_state_paths(self):
        self.persistence_file = self.tmp_path / "persistence_state.json"
        self.executor_state_file = self.tmp_path / "executor_state.json"
        self.atr_snapshot_file = self.tmp_path / "rithmic_atr_snapshot.json"
        self.recent_bars_file = self.tmp_path / "rithmic_recent_bars.json"
        self.atr_shadow_file = self.tmp_path / "rithmic_atr_shadow_comparison.json"

        self.manager.PERSISTENCE_FILE = str(self.persistence_file)
        self.manager.EXECUTOR_STATE_FILE = str(self.executor_state_file)
        self.manager.RITHMIC_ATR_SNAPSHOT_FILE = str(self.atr_snapshot_file)
        self.manager.RITHMIC_RECENT_BARS_FILE = str(self.recent_bars_file)
        self.manager.RITHMIC_ATR_SHADOW_COMPARISON_FILE = str(self.atr_shadow_file)
        self.manager.TRADE_MANAGER_CONFIG_FILE = str(self.tmp_path / "trade_manager_config.json")
        symbol_resolution.ATR_SNAPSHOT_PATH = self.atr_snapshot_file
        symbol_resolution.RECENT_BARS_PATH = self.recent_bars_file

        self.executor.EXECUTOR_STATE_FILE = self.executor_state_file
        self.executor.DATA_DIR = self.tmp_path

    def _reset_runtime(self):
        self.manager.PROCESSED_EVENTS.clear()
        self.manager.COMMAND_LOG.clear()
        self.manager.QA_LOGS.clear()
        self.manager.TRADINGVIEW_ATR_CACHE.clear()
        self.manager.OPERATING_MODE = self.manager.OPERATING_MODE_PRODUCTION
        self.manager.ENABLE_NOON_RUNNER_FLATTEN = False
        self.manager.RISK_STATE.update({
            "kill_switch_active": False,
            "kill_switch_reason": None,
            "daily_trade_count": 0,
            "daily_loss_count": 0,
            "max_daily_trades": 2,
            "max_daily_losses": 1,
            "kill_switch_drawdown_pct": 11.0,
            "current_drawdown_pct": 0.0,
            "trading_halted": False,
            "last_reset_date": datetime.now().date().isoformat(),
        })
        self.manager.FAILURE_STATE.update({
            "execution_failure_count": 0,
            "qa_critical_count": 0,
            "max_execution_failures": 3,
            "max_qa_critical": 3,
            "last_failure_at": None,
            "halt_reason": None,
        })

        self.executor.ORDERS.clear()
        self.executor.POSITIONS.clear()
        self.executor.LAST_PRICES.clear()
        self.executor.CURRENT_1M_BARS.clear()
        self.executor.COMPLETED_1M_BARS.clear()
        self.executor.EXECUTOR_STATE_LOADED = True
        self.executor.EXECUTOR_STATE_SAVED_AT = None
        self.executor.log = lambda msg: None

        self._write_atr_snapshot(10.0)

    def _set_noon_runner_flatten_enabled(self, enabled):
        Path(self.manager.TRADE_MANAGER_CONFIG_FILE).write_text(
            json.dumps({"ENABLE_NOON_RUNNER_FLATTEN": bool(enabled)}),
            encoding="utf-8",
        )

    def _save_clean_manager_state(self):
        self.manager.save_state(self.manager.build_default_state())

    def _set_mode(self, mode):
        self.manager.OPERATING_MODE = mode

    def test_resolve_operating_mode_defaults_to_production(self):
        self.assertEqual(
            self.manager.resolve_operating_mode(),
            self.manager.OPERATING_MODE_PRODUCTION,
        )

    def test_resolve_operating_mode_reads_config_and_env_overrides_config(self):
        import os

        Path(self.manager.TRADE_MANAGER_CONFIG_FILE).write_text(
            json.dumps({"operating_mode": "qa_stability"}),
            encoding="utf-8",
        )
        self.assertEqual(
            self.manager.resolve_operating_mode(),
            self.manager.OPERATING_MODE_QA_STABILITY,
        )

        os.environ[self.manager.OPERATING_MODE_ENV_VAR] = "production"
        self.assertEqual(
            self.manager.resolve_operating_mode(),
            self.manager.OPERATING_MODE_PRODUCTION,
        )

    def test_production_blocks_when_daily_trade_count_reaches_max(self):
        self._save_clean_manager_state()
        self._set_mode(self.manager.OPERATING_MODE_PRODUCTION)
        self.manager.RISK_STATE["daily_trade_count"] = self.manager.RISK_STATE["max_daily_trades"]

        allowed, reason = self.manager.can_execute_trade()

        self.assertFalse(allowed)
        self.assertEqual(reason, "max_daily_trades_reached")
        self.assertTrue(self.manager.RISK_STATE["trading_halted"])

    def test_production_blocks_when_daily_loss_count_reaches_max(self):
        self._save_clean_manager_state()
        self._set_mode(self.manager.OPERATING_MODE_PRODUCTION)
        self.manager.RISK_STATE["daily_loss_count"] = self.manager.RISK_STATE["max_daily_losses"]

        allowed, reason = self.manager.can_execute_trade()

        self.assertFalse(allowed)
        self.assertEqual(reason, "max_daily_losses_reached")
        self.assertTrue(self.manager.RISK_STATE["trading_halted"])

    def test_production_blocks_when_trading_halted_is_true(self):
        self._save_clean_manager_state()
        self._set_mode(self.manager.OPERATING_MODE_PRODUCTION)
        self.manager.RISK_STATE["trading_halted"] = True

        allowed, reason = self.manager.can_execute_trade()

        self.assertFalse(allowed)
        self.assertEqual(reason, "trading_halted")

    def test_qa_stability_bypasses_trading_halted_daily_lockout(self):
        self._save_clean_manager_state()
        self._set_mode(self.manager.OPERATING_MODE_QA_STABILITY)
        self.manager.RISK_STATE["trading_halted"] = True

        allowed, reason = self.manager.can_execute_trade()

        self.assertTrue(allowed)
        self.assertEqual(reason, "allowed")

    def test_qa_stability_bypasses_max_daily_trades(self):
        self._save_clean_manager_state()
        self._set_mode(self.manager.OPERATING_MODE_QA_STABILITY)
        self.manager.RISK_STATE["daily_trade_count"] = self.manager.RISK_STATE["max_daily_trades"]

        allowed, reason = self.manager.can_execute_trade()

        self.assertTrue(allowed)
        self.assertEqual(reason, "allowed")
        self.assertFalse(self.manager.RISK_STATE["trading_halted"])

    def test_qa_stability_bypasses_max_daily_losses(self):
        self._save_clean_manager_state()
        self._set_mode(self.manager.OPERATING_MODE_QA_STABILITY)
        self.manager.RISK_STATE["daily_loss_count"] = self.manager.RISK_STATE["max_daily_losses"]

        allowed, reason = self.manager.can_execute_trade()

        self.assertTrue(allowed)
        self.assertEqual(reason, "allowed")
        self.assertFalse(self.manager.RISK_STATE["trading_halted"])

    def test_qa_stability_still_blocks_when_kill_switch_active(self):
        self._save_clean_manager_state()
        self._set_mode(self.manager.OPERATING_MODE_QA_STABILITY)
        self.manager.RISK_STATE["kill_switch_active"] = True
        self.manager.RISK_STATE["kill_switch_reason"] = "critical error"
        self.manager.RISK_STATE["daily_trade_count"] = 999
        self.manager.RISK_STATE["daily_loss_count"] = 999
        self.manager.RISK_STATE["trading_halted"] = True

        allowed, reason = self.manager.can_execute_trade()

        self.assertFalse(allowed)
        self.assertEqual(reason, "kill_switch_active: critical error")

    def test_qa_critical_kill_switch_globally_flattens_executor_exposure(self):
        self._save_clean_manager_state()
        self.executor.POSITIONS["NQM6"] = {
            "qty": -1.0,
            "avg_entry_price": 27403.25,
            "updated_at": "2026-04-26T17:06:34.767604",
        }
        self.executor.POSITIONS["YMM6"] = {
            "qty": 1.0,
            "avg_entry_price": 49276.0,
            "updated_at": "2026-04-26T17:00:43.350647",
        }
        self.executor.ORDERS["STOP-NQ"] = {
            "order_id": "STOP-NQ",
            "trade_id": "T-nq",
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 27410.25,
            "qty": 1.0,
            "status": "active",
        }
        self.executor.ORDERS["STOP-YM"] = {
            "order_id": "STOP-YM",
            "trade_id": "T-ym",
            "type": "stop",
            "symbol": "YMM6",
            "stop_price": 49271.0,
            "qty": 1.0,
            "status": "active",
        }

        self.manager.register_qa_critical_failure("critical_test_1")
        self.manager.register_qa_critical_failure("critical_test_2")
        self.manager.register_qa_critical_failure("critical_test_3")

        active_orders = [
            order for order in self.executor.ORDERS.values()
            if self.executor.is_working_order(order)
        ]
        state = self.manager.load_state()

        self.assertTrue(self.manager.RISK_STATE["kill_switch_active"])
        self.assertTrue(self.manager.RISK_STATE["trading_halted"])
        self.assertTrue(state["risk_state"]["kill_switch_active"])
        self.assertTrue(state["risk_state"]["trading_halted"])
        self.assertEqual(self.executor.POSITIONS["NQM6"]["qty"], 0.0)
        self.assertEqual(self.executor.POSITIONS["YMM6"]["qty"], 0.0)
        self.assertEqual(active_orders, [])
        self.assertEqual(self.executor.ORDERS["STOP-NQ"]["status"], "cancelled")
        self.assertEqual(self.executor.ORDERS["STOP-YM"]["status"], "cancelled")
        self.assertEqual(self.executor.ORDERS["STOP-NQ"]["closed_reason"], "qa critical escalation: critical_test_3")
        self.assertEqual(self.executor.ORDERS["STOP-YM"]["closed_reason"], "qa critical escalation: critical_test_3")

    def test_qa_stability_still_blocks_same_symbol_active_trade(self):
        state = self.manager.build_default_state()
        state["trades"]["T-active"] = {
            "trade_id": "T-active",
            "symbol": "NQM6",
            "execution_symbol": "NQM6",
            "requested_symbol": "NQ",
            "status": "active",
        }
        self.manager.save_state(state)
        self._set_mode(self.manager.OPERATING_MODE_QA_STABILITY)

        allowed, reason = self.manager.can_execute_trade(symbol="NQ")

        self.assertFalse(allowed)
        self.assertEqual(reason, "active_trade_exists_for_symbol:NQM6")

    def test_existing_contract_symbol_blocks_root_symbol(self):
        state = self.manager.build_default_state()
        state["trades"]["T-active"] = {
            "trade_id": "T-active",
            "symbol": "NQM6",
            "execution_symbol": "NQM6",
            "requested_symbol": "NQ",
            "status": "active",
        }
        self.manager.save_state(state)

        allowed, reason = self.manager.can_execute_trade(symbol="NQ")

        self.assertFalse(allowed)
        self.assertEqual(reason, "active_trade_exists_for_symbol:NQM6")

    def test_existing_root_symbol_blocks_continuous_symbol(self):
        state = self.manager.build_default_state()
        state["trades"]["T-active"] = {
            "trade_id": "T-active",
            "symbol": "NQ",
            "execution_symbol": "NQ",
            "requested_symbol": "NQ",
            "status": "active",
        }
        self.manager.save_state(state)

        allowed, reason = self.manager.can_execute_trade(symbol="NQ1!")

        self.assertFalse(allowed)
        self.assertEqual(reason, "active_trade_exists_for_symbol:NQM6")

    def test_existing_different_symbol_does_not_block_nq(self):
        state = self.manager.build_default_state()
        state["trades"]["T-active"] = {
            "trade_id": "T-active",
            "symbol": "YM",
            "execution_symbol": "YM",
            "requested_symbol": "YM",
            "status": "active",
        }
        self.manager.save_state(state)

        allowed, reason = self.manager.can_execute_trade(symbol="NQ")

        self.assertTrue(allowed)
        self.assertEqual(reason, "allowed")

    def test_existing_ym_contract_blocks_root_symbol(self):
        state = self.manager.build_default_state()
        state["trades"]["T-active"] = {
            "trade_id": "T-active",
            "symbol": "YMM6",
            "execution_symbol": "YMM6",
            "requested_symbol": "YM",
            "status": "active",
        }
        self.manager.save_state(state)

        allowed, reason = self.manager.can_execute_trade(symbol="YM")

        self.assertFalse(allowed)
        self.assertEqual(reason, "active_trade_exists_for_symbol:YMM6")

    def test_existing_root_symbol_blocks_ym_continuous_symbol(self):
        state = self.manager.build_default_state()
        state["trades"]["T-active"] = {
            "trade_id": "T-active",
            "symbol": "YM",
            "execution_symbol": "YM",
            "requested_symbol": "YM",
            "status": "active",
        }
        self.manager.save_state(state)

        allowed, reason = self.manager.can_execute_trade(symbol="YM1!")

        self.assertFalse(allowed)
        self.assertEqual(reason, "active_trade_exists_for_symbol:YMM6")

    def test_active_nq_does_not_block_ym(self):
        state = self.manager.build_default_state()
        state["trades"]["T-nq"] = {
            "trade_id": "T-nq",
            "symbol": "NQM6",
            "execution_symbol": "NQM6",
            "requested_symbol": "NQ",
            "status": "active",
        }
        self.manager.save_state(state)

        allowed, reason = self.manager.can_execute_trade(symbol="YM")

        self.assertTrue(allowed)
        self.assertEqual(reason, "allowed")

    def test_active_ym_does_not_block_nq(self):
        state = self.manager.build_default_state()
        state["trades"]["T-ym"] = {
            "trade_id": "T-ym",
            "symbol": "YMM6",
            "execution_symbol": "YMM6",
            "requested_symbol": "YM",
            "status": "active",
        }
        self.manager.save_state(state)

        allowed, reason = self.manager.can_execute_trade(symbol="NQ")

        self.assertTrue(allowed)
        self.assertEqual(reason, "allowed")

    def test_reserved_active_trade_blocks_duplicate_same_symbol(self):
        state = self.manager.build_default_state()
        state["trades"]["T-reserved"] = {
            "trade_id": "T-reserved",
            "symbol": "NQM6",
            "execution_symbol": "NQM6",
            "requested_symbol": "NQ",
            "status": "active",
            "entry_price": None,
            "stop_order_id": None,
            "tp1_order_id": None,
        }
        self.manager.save_state(state)

        allowed, reason = self.manager.can_execute_trade(symbol="NQ")

        self.assertFalse(allowed)
        self.assertEqual(reason, "active_trade_exists_for_symbol:NQM6")

    def test_external_paper_reset_blocks_stale_trade_and_risk_rewrite(self):
        stale_trade = self.manager.create_trade_state({
            "symbol": "NQ",
            "direction": "long",
            "position_size": 2,
        }, {
            "atr_value": 10.0,
            "atr_source": "offline_replay",
            "atr_bar_timestamp": "2026-01-01T09:29:00Z",
        }, "NQ", "NQM6")
        stale_trade.update(self.manager.derive_trade_levels(100.0, "NQM6", "long", 10.0))
        stale_trade["created_at"] = "2026-01-01T09:30:00"

        reset_state = self.manager.build_default_state()
        reset_state["system"]["paper_reset_at"] = "2026-01-01T09:31:00"
        reset_state["trades"] = {}
        reset_state["orders"] = {}
        reset_state["event_log"] = []
        reset_state["risk_state"]["daily_loss_count"] = 0
        reset_state["risk_state"]["daily_trade_count"] = 0
        reset_state["risk_state"]["trading_halted"] = False
        reset_state["failure_state"]["qa_critical_count"] = 0
        self.persistence_file.write_text(json.dumps(reset_state), encoding="utf-8")

        self.manager.RUNTIME_PAPER_RESET_AT = None
        self.manager.RISK_STATE["daily_loss_count"] = 9
        self.manager.RISK_STATE["daily_trade_count"] = 2
        self.manager.RISK_STATE["trading_halted"] = True
        self.manager.FAILURE_STATE["qa_critical_count"] = 3

        self.manager.persist_trade_state(stale_trade)

        persisted = self.manager.load_state()
        self.assertEqual(persisted["trades"], {})
        self.assertEqual(persisted["event_log"], [])
        self.assertEqual(persisted["risk_state"]["daily_loss_count"], 0)
        self.assertEqual(persisted["risk_state"]["daily_trade_count"], 0)
        self.assertFalse(persisted["risk_state"]["trading_halted"])
        self.assertEqual(persisted["failure_state"]["qa_critical_count"], 0)

        self.manager.persist_trade_state(stale_trade)
        self.assertEqual(self.manager.load_state()["trades"], {})

    def test_production_trade_rejection_still_escalates_to_qa_critical(self):
        self._set_mode(self.manager.OPERATING_MODE_PRODUCTION)

        self.assertTrue(
            self.manager.should_escalate_trade_rejection_to_qa_critical("trading_halted")
        )

    def test_qa_stability_daily_lockout_rejection_does_not_escalate_to_qa_critical(self):
        self._set_mode(self.manager.OPERATING_MODE_QA_STABILITY)

        for reason in ("trading_halted", "max_daily_trades_reached", "max_daily_losses_reached"):
            with self.subTest(reason=reason):
                self.assertFalse(
                    self.manager.should_escalate_trade_rejection_to_qa_critical(reason)
                )

    def test_qa_stability_non_daily_rejection_still_escalates_to_qa_critical(self):
        self._set_mode(self.manager.OPERATING_MODE_QA_STABILITY)

        self.assertTrue(
            self.manager.should_escalate_trade_rejection_to_qa_critical(
                "active_trade_exists_for_symbol:NQ"
            )
        )

    def test_error_trade_closes_from_executor_sync_when_executor_is_flat(self):
        trade = {
            "trade_id": "T-error-flat",
            "symbol": "NQM6",
            "requested_symbol": "NQ",
            "execution_symbol": "NQM6",
            "direction": "short",
            "status": "error",
            "remaining_size": 2,
            "closed_at": None,
            "exit_reason": None,
            "error_reason": "stop_sync_failed",
        }
        executor_orders = [
            {
                "order_id": "STOP-old",
                "trade_id": "T-error-flat",
                "type": "stop",
                "symbol": "NQM6",
                "status": "closed",
            }
        ]
        executor_snapshot = {
            "NQM6": {
                "position_qty": 0.0,
                "avg_entry_price": 0.0,
            }
        }

        updated = self.manager.sync_trade_protection(
            trade,
            executor_orders,
            executor_snapshot,
        )

        self.assertEqual(updated["status"], "closed")
        self.assertEqual(updated["remaining_size"], 0)
        self.assertEqual(updated["exit_reason"], "executor_flat_sync")
        self.assertEqual(updated["recovery_status"], "closed_from_executor_sync")
        self.assertIsNone(updated["error_reason"])

    def test_error_trade_does_not_close_from_executor_sync_with_active_executor_order(self):
        trade = {
            "trade_id": "T-error-live",
            "symbol": "NQM6",
            "requested_symbol": "NQ",
            "execution_symbol": "NQM6",
            "direction": "short",
            "status": "error",
            "remaining_size": 2,
            "closed_at": None,
            "exit_reason": None,
            "error_reason": "stop_sync_failed",
        }
        executor_orders = [
            {
                "order_id": "STOP-live",
                "trade_id": "T-error-live",
                "type": "stop",
                "symbol": "NQM6",
                "status": "active",
            }
        ]
        executor_snapshot = {
            "NQM6": {
                "position_qty": 0.0,
                "avg_entry_price": 0.0,
            }
        }

        updated = self.manager.sync_trade_protection(
            trade,
            executor_orders,
            executor_snapshot,
        )

        self.assertEqual(updated["status"], "error")
        self.assertEqual(updated["remaining_size"], 2)
        self.assertEqual(updated["error_reason"], "stop_sync_failed")

    def _write_atr_snapshot(self, atr_value, ym_atr_value=None):
        if ym_atr_value is None:
            ym_atr_value = atr_value
        self.atr_snapshot_file.write_text(
            json.dumps({
                "symbols": {
                    "NQM6": {
                        "atr_value": atr_value,
                        "atr_bar_timestamp": "2026-01-01T09:29:00Z",
                        "atr_source": "offline_replay",
                    },
                    "NQ": {
                        "atr_value": atr_value,
                        "atr_bar_timestamp": "2026-01-01T09:29:00Z",
                        "atr_source": "offline_replay",
                    },
                    "YMM6": {
                        "atr_value": ym_atr_value,
                        "atr_bar_timestamp": "2026-01-01T09:29:00Z",
                        "atr_source": "offline_replay",
                    },
                    "YM": {
                        "atr_value": ym_atr_value,
                        "atr_bar_timestamp": "2026-01-01T09:29:00Z",
                        "atr_source": "offline_replay",
                    },
                }
            }),
            encoding="utf-8",
        )
        self.recent_bars_file.write_text(
            json.dumps({"symbols": {"NQM6": [], "YMM6": []}}),
            encoding="utf-8",
        )

    class _Response:
        def __init__(self, data, status_code=200):
            self._data = data
            self.status_code = status_code

        def json(self):
            return self._data

    def _wire_manager_to_executor(self):
        executor_client = self.executor.app.test_client()

        def fake_post(url, json=None, **kwargs):
            if url == self.manager.EXECUTOR_URL:
                response = executor_client.post("/execute", json=json)
                return self._Response(response.get_json(), response.status_code)
            raise AssertionError(f"unexpected POST url: {url}")

        def fake_get(url, **kwargs):
            if url == self.manager.EXECUTOR_ORDERS_URL:
                response = executor_client.get("/orders")
                return self._Response(response.get_json(), response.status_code)
            if url == self.manager.EXECUTOR_SNAPSHOT_URL:
                response = executor_client.get("/sync_snapshot")
                return self._Response(response.get_json(), response.status_code)
            raise AssertionError(f"unexpected GET url: {url}")

        self.manager.requests.post = fake_post
        self.manager.requests.get = fake_get

    def _new_trade(self, symbol="NQM6", direction="short", position_size=2, price=100.0):
        execution_symbol, _ = self.manager.resolve_execution_symbol(symbol)
        self.executor.LAST_PRICES[execution_symbol] = float(price)
        symbol_root = self.manager.normalize_symbol_root(symbol)
        if not self.manager.find_tradingview_atr_record(symbol_root):
            atr_value = 10.0 if symbol_root == "NQ" else 25.0
            state = self.manager.load_state()
            state.setdefault("tradingview_atr", {})[symbol_root] = {
                "symbol": symbol_root,
                "atr_period": 14,
                "atr_value": atr_value,
                "timeframe": "1",
                "source": "tradingview",
                "received_at": datetime.now().isoformat(),
                "raw_event": "tv_atr_update",
            }
            self.manager.save_state(state)
            self.manager.TRADINGVIEW_ATR_CACHE.clear()
        return self.manager.submit_trade({
            "event": "enter_trade",
            "symbol": symbol,
            "direction": direction,
            "position_size": position_size,
        })

    def _new_short_trade(self):
        return self._new_trade()

    def _timestamps(self, count):
        base = datetime(2026, 1, 1, 9, 30, 0)
        return [base + timedelta(minutes=i) for i in range(count)]

    def _public_trade(self, trade_id):
        client = self.manager.app.test_client()
        data = client.get("/trades").get_json()
        self.assertTrue(data["ok"])
        return data["trades"][trade_id]

    def _replay(self, trade_id):
        client = self.manager.app.test_client()
        data = client.get(f"/replay/{trade_id}").get_json()
        self.assertTrue(data["ok"])
        return data

    def _events(self, trade_id):
        return [
            event for event in self.manager.load_state()["event_log"]
            if event["trade_id"] == trade_id
        ]

    def _event_types(self, trade_id):
        return [event["event_type"] for event in self._events(trade_id)]

    def _assert_event_sequence(self, trade_id, required):
        event_types = self._event_types(trade_id)
        cursor = 0
        for expected_type in required:
            try:
                cursor = event_types.index(expected_type, cursor) + 1
            except ValueError:
                self.fail(f"missing event {expected_type}; got {event_types}")

    def _executor_orders(self, trade_id):
        return [
            order for order in self.executor.ORDERS.values()
            if order.get("trade_id") == trade_id
        ]

    def _assert_flat_reconciled(self, trade):
        orders = self._executor_orders(trade["trade_id"])
        self.assertTrue(orders)
        self.assertFalse([order for order in orders if order.get("status") == "active"])
        self.assertEqual(self.executor.POSITIONS[trade["symbol"]]["qty"], 0.0)
        persisted = self.manager.get_trade(trade["trade_id"])
        self.assertEqual(persisted["remaining_size"], 0)
        self.assertEqual(persisted["status"], "closed")

    def _assert_profit_breakdown(self, trade_id, tp1_profit, runner_profit, total_profit):
        persisted = self.manager.get_trade(trade_id)
        public = self._public_trade(trade_id)

        self.assertEqual(persisted["tp1_profit"], tp1_profit)
        self.assertEqual(persisted["runner_profit"], runner_profit)
        self.assertEqual(persisted["total_profit"], total_profit)
        self.assertEqual(persisted["realized_pnl"], total_profit)

        self.assertEqual(public["tp1_profit"], tp1_profit)
        self.assertEqual(public["runner_profit"], runner_profit)
        self.assertEqual(public["total_profit"], total_profit)
        self.assertEqual(public["realized_pnl"], total_profit)

    def test_scenario_a_be_only_then_scratch(self):
        trade = self._new_short_trade()
        self.assertEqual(trade["entry_price"], 100.0)
        self.assertEqual(trade["original_stop"], 110.0)
        self.assertEqual(trade["be_trigger"], 95.0)
        self.assertEqual(trade["tp1_price"], 90.0)

        self.manager.simulate_prices_for_trade(
            trade["trade_id"],
            [99, 97, 95, 100],
            self._timestamps(4),
        )

        public = self._public_trade(trade["trade_id"])
        self.assertTrue(public["moved_to_be"])
        self.assertEqual(public["current_stop"], 100.0)
        self.assertEqual(public["stop_state"], "break_even")
        self.assertEqual(public["exit_reason"], "stop_hit")
        self.assertEqual(public["exit_price"], 100.0)
        self.assertEqual(public["realized_pnl"], 0.0)
        self.assertFalse(public["tp1_hit"])
        self.assertEqual(public["remaining_size"], 0)
        self.assertIsNotNone(self._replay(trade["trade_id"])["final_trade_persistence_snapshot"])
        self._assert_event_sequence(trade["trade_id"], [
            "submit_accepted",
            "entry_filled",
            "original_stop_placed",
            "tp1_order_active",
            "be_trigger_hit",
            "be_stop_modified",
            "stop_hit_close",
            "final_trade_persistence_snapshot",
        ])
        self._assert_flat_reconciled(trade)

    def test_scenario_b_tp1_then_runner_stop(self):
        trade = self._new_short_trade()
        snapshots = self.manager.simulate_prices_for_trade(
            trade["trade_id"],
            [99, 95, 90, 100, 110],
            self._timestamps(5),
        )

        after_tp1 = snapshots[2]
        self.assertEqual(after_tp1["status"], "active")
        self.assertTrue(after_tp1["tp1_hit"])
        self.assertEqual(after_tp1["remaining_size"], 1.0)
        self.assertIsNotNone(after_tp1["tp1_hit_at"])
        self.assertEqual(after_tp1["current_stop"], 110.0)
        self.assertEqual(after_tp1["stop_state"], "runner_original")
        self.assertEqual(after_tp1["tp1_profit"], 200.0)
        self.assertIsNone(after_tp1["runner_profit"])
        self.assertEqual(after_tp1["total_profit"], 200.0)

        after_be_retest = snapshots[3]
        self.assertEqual(after_be_retest["status"], "active")
        self.assertEqual(after_be_retest["remaining_size"], 1.0)

        public = self._public_trade(trade["trade_id"])
        self.assertTrue(public["moved_to_be"])
        self.assertTrue(public["tp1_hit"])
        self.assertEqual(public["exit_reason"], "stop_hit")
        self.assertEqual(public["exit_price"], 110.0)
        self.assertEqual(public["realized_pnl"], 0.0)
        self.assertEqual(public["remaining_size"], 0)
        self._assert_event_sequence(trade["trade_id"], [
            "submit_accepted",
            "entry_filled",
            "original_stop_placed",
            "tp1_order_active",
            "be_trigger_hit",
            "be_stop_modified",
            "tp1_filled",
            "runner_stop_reset_to_original",
            "stop_hit_close",
            "final_trade_persistence_snapshot",
        ])
        replay = self._replay(trade["trade_id"])
        self.assertEqual(replay["trade"]["realized_pnl"], 0.0)
        self._assert_profit_breakdown(trade["trade_id"], 200.0, -200.0, 0.0)
        self._assert_flat_reconciled(trade)

    def test_profit_breakdown_tp1_then_runner_be(self):
        trade = self._new_short_trade()
        after_tp1 = self.manager.process_price_update_by_id(
            trade["trade_id"],
            90,
            self._timestamps(1)[0],
        )
        self.assertEqual(after_tp1["tp1_profit"], 200.0)
        self.assertIsNone(after_tp1["runner_profit"])
        self.assertEqual(after_tp1["total_profit"], 200.0)

        after_tp1["current_stop"] = after_tp1["entry_price"]
        after_tp1["stop_state"] = "break_even"
        after_tp1["moved_to_be"] = True
        self.manager.persist_trade_state(after_tp1)
        self.manager.handle_stop_hit(after_tp1, self._timestamps(2)[1])

        self._assert_profit_breakdown(trade["trade_id"], 200.0, 0.0, 200.0)

    def test_profit_breakdown_tp1_then_runner_original_stop(self):
        trade = self._new_short_trade()
        self.manager.simulate_prices_for_trade(
            trade["trade_id"],
            [90, 110],
            self._timestamps(2),
        )

        self._assert_profit_breakdown(trade["trade_id"], 200.0, -200.0, 0.0)

    def test_profit_breakdown_tp1_then_runner_profit_exit(self):
        trade = self._new_short_trade()
        after_tp1 = self.manager.process_price_update_by_id(
            trade["trade_id"],
            90,
            self._timestamps(1)[0],
        )
        after_tp1["current_stop"] = 80.0
        after_tp1["stop_state"] = "runner_profit"
        self.manager.persist_trade_state(after_tp1)
        self.manager.handle_stop_hit(after_tp1, self._timestamps(2)[1])

        self._assert_profit_breakdown(trade["trade_id"], 200.0, 400.0, 600.0)

    def test_be_trigger_moves_stop_without_reducing_position_before_tp1(self):
        trade = self._new_short_trade()

        after_be = self.manager.process_price_update_by_id(
            trade["trade_id"],
            95,
            self._timestamps(1)[0],
        )

        self.assertEqual(after_be["status"], "active")
        self.assertTrue(after_be["moved_to_be"])
        self.assertFalse(after_be["tp1_hit"])
        self.assertEqual(after_be["current_stop"], after_be["entry_price"])
        self.assertEqual(after_be["remaining_size"], 2)

        self.assertEqual(after_be["stop_order_id"], trade["stop_order_id"])
        replacement_stop = self.executor.ORDERS[after_be["stop_order_id"]]
        self.assertEqual(replacement_stop["qty"], 2.0)
        self.assertEqual(replacement_stop["stop_price"], after_be["entry_price"])
        self.assertEqual(replacement_stop["tag"], "breakeven")
        self.assertEqual(replacement_stop["oco_group"], trade["oco_group"])
        self.assertEqual(replacement_stop["oco_role"], "protective_stop")
        self.assertTrue(replacement_stop.get("modify_history"))

    def test_entry_fill_creates_resting_stop_and_tp1_limit_immediately(self):
        trade = self._new_short_trade()

        active_stops = [
            order for order in self.executor.ORDERS.values()
            if order.get("trade_id") == trade["trade_id"]
            and order.get("type") == "stop"
            and order.get("status") == "active"
        ]
        active_limits = [
            order for order in self.executor.ORDERS.values()
            if order.get("trade_id") == trade["trade_id"]
            and order.get("type") == "limit"
            and order.get("tag") == "tp1"
            and order.get("status") == "active"
        ]

        self.assertEqual(len(active_stops), 1)
        self.assertEqual(active_stops[0]["order_id"], trade["stop_order_id"])
        self.assertEqual(active_stops[0]["stop_price"], trade["original_stop"])
        self.assertEqual(active_stops[0]["qty"], float(trade["position_size"]))
        self.assertEqual(active_stops[0]["oco_group"], trade["oco_group"])
        self.assertEqual(active_stops[0]["oco_role"], "protective_stop")
        self.assertEqual(len(active_limits), 1)
        self.assertEqual(active_limits[0]["order_id"], trade["tp1_order_id"])
        self.assertEqual(active_limits[0]["limit_price"], trade["tp1_price"])
        self.assertEqual(active_limits[0]["qty"], float(trade["position_size"]) / 2)
        self.assertEqual(active_limits[0]["oco_group"], trade["oco_group"])
        self.assertEqual(active_limits[0]["oco_role"], "tp1_limit")

    def test_executor_keeps_stop_and_tp1_if_trade_manager_stops_polling_after_entry(self):
        trade = self._new_short_trade()
        manager_snapshot = dict(trade)

        active_orders = [
            order for order in self.executor.ORDERS.values()
            if order.get("trade_id") == manager_snapshot["trade_id"]
            and order.get("status") == "active"
        ]

        self.assertEqual(manager_snapshot["status"], "active")
        self.assertCountEqual([order["type"] for order in active_orders], ["stop", "limit"])
        self.assertTrue(any(order["order_id"] == manager_snapshot["stop_order_id"] for order in active_orders))
        self.assertTrue(any(order["order_id"] == manager_snapshot["tp1_order_id"] for order in active_orders))

    def test_restart_reconcile_preserves_existing_broker_native_protection(self):
        trade = self._new_short_trade()
        state = self.manager.load_state()
        state["trades"][trade["trade_id"]]["stop_order_id"] = None
        state["trades"][trade["trade_id"]]["tp1_order_id"] = None
        state["trades"][trade["trade_id"]]["current_stop"] = None
        self.manager.save_state(state)

        recovered = self.manager.reconcile_on_startup()
        persisted = self.manager.get_trade(trade["trade_id"])

        self.assertEqual(persisted["status"], "active")
        self.assertEqual(persisted["stop_order_id"], trade["stop_order_id"])
        self.assertEqual(persisted["tp1_order_id"], trade["tp1_order_id"])
        self.assertEqual(persisted["current_stop"], trade["original_stop"])
        self.assertEqual(persisted["oco_group"], trade["oco_group"])
        self.assertTrue(any(item["trade_id"] == trade["trade_id"] for item in recovered))

    def test_noon_cutoff_contingency_is_documented(self):
        doc = (ROOT / "docs" / "architecture" / "broker_native_protective_orders.md").read_text(encoding="utf-8")

        self.assertIn("Noon cutoff fallback", doc)
        self.assertIn("independent of Trade Manager", doc)
        self.assertIn("Rithmic-native deployment", doc)

    def test_nq_short_be_triggers_from_contract_price_tick_below_trigger(self):
        trade = self._new_trade(symbol="NQM6", direction="short", position_size=2, price=28992.0)
        trade.update(
            {
                "trade_id": "T-64adb60f",
                "entry_price": 28992.0,
                "original_stop": 29002.0,
                "current_stop": 29002.0,
                "be_trigger": 28981.0,
                "tp1_price": 28960.0,
                "symbol": "NQM6",
                "requested_symbol": "NQ",
                "execution_symbol": "NQM6",
            }
        )
        self.manager.persist_trade_state(trade)

        after_be = self.manager.process_price_update_by_id(
            "T-64adb60f",
            28970.25,
            datetime.now() + timedelta(seconds=1),
        )

        self.assertEqual(after_be["current_stop"], 28992.0)
        self.assertEqual(after_be["stop_state"], "break_even")
        self.assertTrue(after_be["moved_to_be"])

    def test_nq_short_be_triggers_from_live_bar_low_when_latest_tick_recovers(self):
        trade = self._new_trade(symbol="NQM6", direction="short", position_size=2, price=28992.0)
        trade.update(
            {
                "trade_id": "T-64adb60f",
                "entry_price": 28992.0,
                "original_stop": 29002.0,
                "current_stop": 29002.0,
                "be_trigger": 28981.0,
                "tp1_price": 28960.0,
                "symbol": "NQM6",
                "requested_symbol": "NQ",
                "execution_symbol": "NQM6",
            }
        )
        self.manager.persist_trade_state(trade)

        self.manager.on_price(
            "NQ",
            28990.0,
            timestamp=datetime.now() + timedelta(seconds=1),
            bar={"open": 28992.0, "high": 28994.0, "low": 28970.25, "close": 28990.0},
        )
        after_be = self.manager.get_trade("T-64adb60f")

        self.assertEqual(after_be["current_stop"], 28992.0)
        self.assertEqual(after_be["stop_state"], "break_even")
        self.assertTrue(after_be["moved_to_be"])

    def test_long_trades_payload_preserves_tp1_and_be_levels_after_submit(self):
        trade = self._new_trade(symbol="NQ", direction="long", position_size=2, price=27458.25)
        client = self.manager.app.test_client()

        data = client.get("/trades").get_json()

        self.assertTrue(data["ok"])
        active_trade = data["trades"][trade["trade_id"]]
        entry = active_trade["entry_price"]
        tp1 = active_trade["tp1_price"]
        be = active_trade["be_trigger"]
        stop = active_trade["current_stop"]
        original_stop = active_trade["original_stop"]

        self.assertIsNotNone(entry)
        self.assertIsNotNone(tp1)
        self.assertIsNotNone(be)
        self.assertIsNotNone(stop)
        self.assertIsNotNone(original_stop)
        self.assertNotEqual(tp1, 0)
        self.assertNotEqual(be, 0)
        self.assertEqual(active_trade["direction"], "long")
        self.assertGreater(tp1, entry)
        self.assertGreater(be, entry)
        self.assertLess(be, tp1)
        self.assertLess(stop, entry)
        self.assertLess(original_stop, entry)

    def test_stale_active_trade_save_cannot_drop_tp1_and_be_levels(self):
        trade = self._new_trade(symbol="NQ", direction="long", position_size=2, price=27458.25)
        stale_trade = dict(trade)
        stale_trade["tp1_price"] = None
        stale_trade["be_trigger"] = None

        self.manager.persist_trade_state(stale_trade)

        active_trade = self._public_trade(trade["trade_id"])
        self.assertEqual(active_trade["entry_price"], trade["entry_price"])
        self.assertEqual(active_trade["tp1_price"], trade["tp1_price"])
        self.assertEqual(active_trade["be_trigger"], trade["be_trigger"])
        self.assertNotEqual(active_trade["tp1_price"], 0)
        self.assertNotEqual(active_trade["be_trigger"], 0)

    def test_long_be_hit_keeps_trade_active_then_entry_return_closes_at_be(self):
        trade = self._new_trade(symbol="NQ", direction="long", position_size=2, price=100.0)

        self.executor.LAST_PRICES["NQM6"] = 105.0
        after_be = self.manager.process_price_update_by_id(
            trade["trade_id"],
            105.0,
            self._timestamps(1)[0],
        )

        self.assertEqual(after_be["status"], "active")
        self.assertTrue(after_be["moved_to_be"])
        self.assertFalse(after_be["tp1_hit"])
        self.assertEqual(after_be["current_stop"], after_be["entry_price"])
        self.assertEqual(after_be["remaining_size"], 2)
        self.assertEqual(after_be["stop_order_id"], trade["stop_order_id"])
        be_stop = self.executor.ORDERS[after_be["stop_order_id"]]
        self.assertEqual(be_stop["status"], "active")
        self.assertEqual(be_stop["stop_price"], 100.0)
        self.assertEqual(be_stop["qty"], 2.0)
        self.assertTrue(be_stop.get("modify_history"))

        self.executor.LAST_PRICES["NQM6"] = 100.0
        after_return = self.manager.process_price_update_by_id(
            trade["trade_id"],
            100.0,
            self._timestamps(2)[1],
        )

        self.assertEqual(after_return["status"], "closed")
        self.assertEqual(after_return["exit_reason"], "stop_hit")
        self.assertEqual(after_return["exit_price"], after_return["entry_price"])
        self.assertEqual(after_return["remaining_size"], 0)
        self.assertEqual(after_return["realized_pnl"], 0.0)
        self.assertFalse(after_return["tp1_hit"])
        self.assertEqual(self.manager.RISK_STATE["daily_loss_count"], 0)

    def test_repeated_be_trigger_is_idempotent_and_tp1_resets_runner_stop(self):
        trade = self._new_short_trade()
        stale_before_be = dict(trade)
        self.executor.LAST_PRICES["NQM6"] = 95.0

        first_be = self.manager.process_price_update_by_id(
            trade["trade_id"],
            95,
            self._timestamps(1)[0],
        )
        self.assertEqual(first_be["status"], "active")
        self.assertTrue(first_be["moved_to_be"])
        self.assertEqual(first_be["current_stop"], 100.0)

        commands_after_first_be = len(self.manager.COMMAND_LOG)
        duplicate_be = self.manager.process_price_update(
            stale_before_be,
            94,
            self._timestamps(2)[1],
        )
        self.assertEqual(duplicate_be["status"], "active")
        self.assertTrue(duplicate_be["moved_to_be"])
        self.assertEqual(duplicate_be["current_stop"], 100.0)
        self.assertEqual(duplicate_be["stop_state"], "break_even")
        self.assertEqual(self.manager.FAILURE_STATE["execution_failure_count"], 0)
        self.assertEqual(self.manager.FAILURE_STATE["qa_critical_count"], 0)
        self.assertEqual(len(self.manager.COMMAND_LOG), commands_after_first_be)

        state = self.manager.load_state()
        state["trades"][trade["trade_id"]] = self.manager.serialize_trade(duplicate_be)
        self.manager.save_state(state)

        after_tp1 = self.manager.process_price_update_by_id(
            trade["trade_id"],
            90,
            self._timestamps(3)[2],
        )

        self.assertEqual(after_tp1["status"], "active")
        self.assertTrue(after_tp1["tp1_hit"])
        self.assertEqual(after_tp1["remaining_size"], 1.0)
        self.assertEqual(after_tp1["current_stop"], 110.0)
        self.assertEqual(after_tp1["stop_state"], "runner_original")
        self.assertIn("reset_stop_to_original", [cmd["action"] for cmd in self.manager.COMMAND_LOG])

        active_stops = [
            order for order in self.executor.ORDERS.values()
            if order.get("trade_id") == trade["trade_id"]
            and order.get("type") == "stop"
            and order.get("status") == "active"
        ]
        self.assertEqual(len(active_stops), 1)
        self.assertEqual(active_stops[0]["stop_price"], 110.0)
        self.assertEqual(active_stops[0]["qty"], 1.0)
        self.assertEqual(active_stops[0]["tag"], "runner_reset")

        self._assert_event_sequence(trade["trade_id"], [
            "be_stop_modified",
            "tp1_filled",
            "runner_stop_reset_to_original",
        ])
        event_types = self._event_types(trade["trade_id"])
        self.assertEqual(event_types.count("be_trigger_hit"), 1)
        self.assertNotIn("be_trigger_duplicate_noop", event_types)

    def test_be_trigger_hit_event_and_stop_replacement_are_once_per_trade(self):
        trade = self._new_short_trade()

        after_be = self.manager.process_price_update_by_id(
            trade["trade_id"],
            95,
            self._timestamps(1)[0],
        )
        commands_after_first_be = list(self.manager.COMMAND_LOG)

        self.manager.process_price_update_by_id(
            trade["trade_id"],
            94,
            self._timestamps(2)[1],
        )
        final_trade = self.manager.process_price_update_by_id(
            trade["trade_id"],
            93,
            self._timestamps(3)[2],
        )

        event_types = self._event_types(trade["trade_id"])
        self.assertEqual(event_types.count("be_trigger_hit"), 1)
        self.assertEqual(self.manager.COMMAND_LOG, commands_after_first_be)
        self.assertTrue(final_trade["be_state_locked"])
        self.assertIsNotNone(final_trade["be_trigger_processed_at"])
        self.assertEqual(final_trade["be_duplicate_trigger_suppressed_count"], 2)
        self.assertTrue(after_be["moved_to_be"])
        self.assertEqual(after_be["stop_state"], "break_even")

    def test_runner_original_permanently_skips_be_logic(self):
        trade = self._new_short_trade()
        trade["tp1_hit"] = True
        trade["tp1_hit_at"] = self._timestamps(1)[0].isoformat()
        trade["remaining_size"] = 1.0
        trade["current_stop"] = trade["original_stop"]
        trade["stop_state"] = "runner_original"
        trade["moved_to_be"] = False
        trade["be_hit_at"] = None
        trade["be_state_locked"] = False
        trade["be_trigger_processed_at"] = None
        self.manager.persist_trade_state(trade)
        commands_before = list(self.manager.COMMAND_LOG)

        updated = self.manager.process_price_update_by_id(
            trade["trade_id"],
            94,
            self._timestamps(2)[1],
        )

        event_types = self._event_types(trade["trade_id"])
        self.assertEqual(event_types.count("be_trigger_hit"), 0)
        self.assertEqual(self.manager.COMMAND_LOG, commands_before)
        self.assertTrue(updated["be_state_locked"])
        self.assertEqual(updated["stop_state"], "runner_original")
        self.assertEqual(updated["be_duplicate_trigger_suppressed_count"], 1)

    def test_long_tp1_fill_leaves_exactly_one_runner_stop_for_remaining_size(self):
        trade = self._new_trade(symbol="NQ", direction="long", position_size=2, price=100.0)
        after_be = self.manager.process_price_update_by_id(
            trade["trade_id"],
            trade["be_trigger"],
            self._timestamps(1)[0],
        )
        be_stop = self.executor.ORDERS[after_be["stop_order_id"]]
        self.executor.ORDERS["STOP-DUPLICATE-QTY2"] = {
            "order_id": "STOP-DUPLICATE-QTY2",
            "trade_id": trade["trade_id"],
            "type": "stop",
            "symbol": trade["symbol"],
            "stop_price": be_stop["stop_price"],
            "qty": 2.0,
            "status": "active",
            "created_at": datetime.now().isoformat(),
        }

        after_tp1 = self.manager.process_price_update_by_id(
            trade["trade_id"],
            trade["tp1_price"],
            self._timestamps(2)[1],
        )

        active_stops = [
            order for order in self.executor.ORDERS.values()
            if order.get("trade_id") == trade["trade_id"]
            and order.get("type") == "stop"
            and order.get("status") == "active"
        ]

        self.assertEqual(after_tp1["status"], "active")
        self.assertTrue(after_tp1["tp1_hit"])
        self.assertEqual(after_tp1["remaining_size"], 1.0)
        self.assertEqual(len(active_stops), 1)
        self.assertEqual(active_stops[0]["qty"], after_tp1["remaining_size"])
        self.assertEqual(
            sum(float(order["qty"]) for order in active_stops),
            after_tp1["remaining_size"],
        )
        self.assertEqual(active_stops[0]["stop_price"], after_tp1["original_stop"])
        self.assertEqual(after_tp1["stop_order_id"], active_stops[0]["order_id"])

    def test_active_trade_price_update_refreshes_last_price_fields(self):
        trade = self._new_trade(symbol="NQ", direction="long", position_size=2, price=100.0)

        first_update = self.manager.process_price_update_by_id(
            trade["trade_id"],
            101.25,
            self._timestamps(1)[0],
        )
        second_update = self.manager.process_price_update_by_id(
            trade["trade_id"],
            101.25,
            self._timestamps(2)[1],
        )
        public_trade = self.manager.public_trade_dict(second_update)

        self.assertEqual(first_update["last_price"], 101.25)
        self.assertEqual(second_update["last_price"], 101.25)
        self.assertNotEqual(first_update["last_price_at"], second_update["last_price_at"])
        self.assertEqual(public_trade["last_price"], 101.25)
        self.assertEqual(public_trade["last_price_at"], second_update["last_price_at"])

    def test_tp1_runner_reset_reconciliation_sets_runner_original_stop_state(self):
        trade = self._new_short_trade()

        after_be = self.manager.process_price_update_by_id(
            trade["trade_id"],
            95,
            self._timestamps(1)[0],
        )
        after_tp1 = self.manager.process_price_update_by_id(
            trade["trade_id"],
            90,
            self._timestamps(2)[1],
        )

        persisted = self.manager.get_trade(trade["trade_id"])
        persisted["stop_state"] = "break_even"
        persisted["current_stop"] = persisted["original_stop"]
        self.manager.persist_trade_state(persisted)

        active_stop = self.executor.ORDERS[after_tp1["stop_order_id"]]
        active_stop["stop_price"] = after_tp1["original_stop"]
        active_stop["qty"] = 1.0
        active_stop["tag"] = "runner_reset"
        active_stop["status"] = "active"

        reconciled = self.manager.process_price_update_by_id(
            trade["trade_id"],
            91,
            self._timestamps(3)[2],
        )

        self.assertEqual(after_be["stop_state"], "break_even")
        self.assertTrue(after_tp1["tp1_hit"])
        self.assertEqual(reconciled["remaining_size"], 1.0)
        self.assertEqual(reconciled["current_stop"], reconciled["original_stop"])
        self.assertEqual(reconciled["stop_state"], "runner_original")

    def test_tp1_runner_transition_accepts_existing_valid_stop_without_kill_switch(self):
        trade = self._new_short_trade()
        self.manager.process_price_update_by_id(
            trade["trade_id"],
            95,
            self._timestamps(1)[0],
        )

        existing_be_stop_id = self.manager.get_trade(trade["trade_id"])["stop_order_id"]
        existing_be_stop = self.executor.ORDERS[existing_be_stop_id]
        existing_be_stop["status"] = "cancelled"
        existing_be_stop["cancelled_at"] = self._timestamps(2)[1].isoformat()

        runner_stop_id = "STOP-runner-existing"
        self.executor.ORDERS[runner_stop_id] = {
            "order_id": runner_stop_id,
            "trade_id": trade["trade_id"],
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 110.0,
            "qty": 1.0,
            "status": "active",
            "created_at": self._timestamps(2)[1].isoformat(),
            "tag": "runner_reset",
        }

        original_reset = self.manager.reset_stop_to_original
        self.manager.reset_stop_to_original = lambda *args, **kwargs: {
            "ok": False,
            "message": "Active stop already exists for this trade",
            "existing_stop_ids": [runner_stop_id],
        }
        try:
            after_tp1 = self.manager.process_price_update_by_id(
                trade["trade_id"],
                90,
                self._timestamps(3)[2],
            )
        finally:
            self.manager.reset_stop_to_original = original_reset

        self.assertEqual(after_tp1["status"], "active")
        self.assertTrue(after_tp1["tp1_hit"])
        self.assertEqual(after_tp1["remaining_size"], 1.0)
        self.assertEqual(after_tp1["current_stop"], 110.0)
        self.assertEqual(after_tp1["stop_state"], "runner_original")
        self.assertEqual(after_tp1["stop_order_id"], runner_stop_id)
        self.assertEqual(after_tp1.get("error_reason"), None)
        self.assertEqual(self.manager.FAILURE_STATE["execution_failure_count"], 0)
        self.assertEqual(self.manager.FAILURE_STATE["qa_critical_count"], 0)
        self.assertFalse(self.manager.RISK_STATE["kill_switch_active"])
        self.assertFalse(self.manager.RISK_STATE["trading_halted"])

        persisted = self.manager.get_trade(trade["trade_id"])
        self.assertEqual(persisted["status"], "active")
        self.assertEqual(persisted["remaining_size"], 1.0)
        self.assertEqual(persisted["stop_state"], "runner_original")
        self.assertEqual(persisted["stop_order_id"], runner_stop_id)

    def test_refresh_recovers_missing_active_runner_trade_from_event_snapshot_and_executor(self):
        trade = self._new_short_trade()
        self.manager.process_price_update_by_id(
            trade["trade_id"],
            95,
            self._timestamps(1)[0],
        )
        self.manager.process_price_update_by_id(
            trade["trade_id"],
            90,
            self._timestamps(2)[1],
        )

        state = self.manager.load_state()
        state["trades"].pop(trade["trade_id"], None)
        self.manager.save_state(state)

        payload = self.manager.app.test_client().get("/trades").get_json()
        recovered = payload["trades"][trade["trade_id"]]

        self.assertEqual(recovered["status"], "active")
        self.assertEqual(recovered["remaining_size"], 1.0)
        self.assertEqual(recovered["stop_state"], "runner_original")
        self.assertTrue(recovered["moved_to_be"])
        self.assertEqual(recovered["symbol"], "NQM6")

    def test_refresh_recovers_tp1_runner_divergence_from_executor_truth(self):
        self._save_clean_manager_state()
        state = self.manager.load_state()
        trade = self.manager.create_trade_state(
            {
                "event": "enter_trade",
                "symbol": "YM",
                "direction": "short",
                "position_size": 2,
            },
            {
                "atr_value": 13.0,
                "atr_source": "tradingview_atr_relay",
                "atr_bar_timestamp": "2026-01-01T09:29:00Z",
            },
            requested_symbol="YM",
            execution_symbol="YMM6",
        )
        trade.update({
            "trade_id": "T-80d66481",
            "symbol": "YMM6",
            "execution_symbol": "YMM6",
            "requested_symbol": "YM",
            "direction": "short",
            "status": "error",
            "entry_price": 49684.0,
            "tp1_price": 49671.0,
            "original_stop": 49697.0,
            "current_stop": 49697.0,
            "be_trigger": 49677.5,
            "remaining_size": 2,
            "tp1_hit": False,
            "tp1_filled_qty": None,
            "stop_order_id": "STOP-5a579192",
            "error_reason": "runner_reconcile_divergence",
        })
        state["trades"][trade["trade_id"]] = self.manager.serialize_trade(trade)
        self.manager.save_state(state)

        self.executor.POSITIONS["YMM6"] = {
            "symbol": "YMM6",
            "qty": -1.0,
            "avg_entry_price": 49684.0,
        }
        self.executor.ORDERS["STOP-5a579192"] = {
            "order_id": "STOP-5a579192",
            "trade_id": "T-80d66481",
            "symbol": "YMM6",
            "type": "stop",
            "status": "active",
            "qty": 1.0,
            "stop_price": 49697.0,
            "tag": "runner_reset",
            "oco_parent_group": "OCO-T-80d66481-PROTECTIVE",
        }

        payload = self.manager.app.test_client().get("/trades").get_json()
        recovered = payload["trades"]["T-80d66481"]
        persisted = self.manager.get_trade("T-80d66481")

        self.assertFalse(payload["orphan_exposure"]["has_orphans"])
        self.assertFalse(payload["orphan_exposure"]["has_manager_state_issue"])
        self.assertEqual(recovered["status"], "active")
        self.assertEqual(recovered["remaining_size"], 1.0)
        self.assertEqual(persisted["stop_order_id"], "STOP-5a579192")
        self.assertEqual(persisted["current_stop"], 49697.0)
        self.assertTrue(persisted["tp1_hit"])
        self.assertEqual(persisted["tp1_filled_qty"], 1.0)
        self.assertEqual(persisted["recovery_status"], "reconciled_from_executor_truth")
        self.assertIsNone(persisted.get("error_reason"))

    def test_matching_active_trade_with_protective_stop_is_not_orphan_exposure(self):
        self._save_clean_manager_state()
        state = self.manager.load_state()
        trade = self.manager.create_trade_state(
            {
                "event": "enter_trade",
                "symbol": "YM",
                "direction": "short",
                "position_size": 2,
            },
            {
                "atr_value": 13.0,
                "atr_source": "tradingview_atr_relay",
                "atr_bar_timestamp": "2026-01-01T09:29:00Z",
            },
            requested_symbol="YM",
            execution_symbol="YMM6",
        )
        trade.update({
            "trade_id": "T-managed-runner",
            "symbol": "YMM6",
            "execution_symbol": "YMM6",
            "requested_symbol": "YM",
            "status": "active",
            "entry_price": 49684.0,
            "original_stop": 49697.0,
            "current_stop": 49697.0,
            "tp1_price": 49671.0,
            "tp1_hit": True,
            "tp1_filled_qty": 1.0,
            "remaining_size": 2,
            "stop_order_id": "STOP-managed-runner",
        })
        state["trades"][trade["trade_id"]] = self.manager.serialize_trade(trade)
        self.manager.save_state(state)

        self.executor.POSITIONS["YMM6"] = {
            "symbol": "YMM6",
            "qty": -1.0,
            "avg_entry_price": 49684.0,
        }
        self.executor.ORDERS["STOP-managed-runner"] = {
            "order_id": "STOP-managed-runner",
            "trade_id": "T-managed-runner",
            "symbol": "YMM6",
            "type": "stop",
            "status": "active",
            "qty": 1.0,
            "stop_price": 49697.0,
            "tag": "runner_reset",
        }

        payload = self.manager.app.test_client().get("/trades").get_json()
        recovered = payload["trades"]["T-managed-runner"]
        persisted = self.manager.get_trade("T-managed-runner")

        self.assertFalse(payload["orphan_exposure"]["has_orphans"])
        self.assertFalse(payload["orphan_exposure"]["has_manager_state_issue"])
        self.assertEqual(recovered["status"], "active")
        self.assertEqual(recovered["remaining_size"], 1.0)
        self.assertEqual(persisted["recovery_status"], "reconciled_from_executor_truth")

    def test_refresh_flags_orphan_executor_exposure_when_manager_trades_missing(self):
        self._save_clean_manager_state()
        self.executor.POSITIONS["NQM6"] = {
            "symbol": "NQM6",
            "qty": 1.0,
            "avg_entry_price": 27435.25,
        }
        self.executor.POSITIONS["YMM6"] = {
            "symbol": "YMM6",
            "qty": -1.0,
            "avg_entry_price": 49276.0,
        }
        self.executor.ORDERS["STOP-NQ-ORPHAN"] = {
            "order_id": "STOP-NQ-ORPHAN",
            "trade_id": "T-orphan-nq",
            "symbol": "NQM6",
            "type": "stop",
            "status": "active",
            "qty": 1.0,
            "stop_price": 27429.25,
            "tag": "runner_reset",
        }
        self.executor.ORDERS["STOP-YM-ORPHAN"] = {
            "order_id": "STOP-YM-ORPHAN",
            "trade_id": "T-orphan-ym",
            "symbol": "YMM6",
            "type": "stop",
            "status": "active",
            "qty": 1.0,
            "stop_price": 49282.0,
            "tag": "runner_reset",
        }

        payload = self.manager.app.test_client().get("/trades").get_json()

        self.assertEqual(payload["trades"], {})
        self.assertTrue(payload["orphan_exposure"]["has_orphans"])
        self.assertEqual(payload["orphan_exposure"]["severity"], "critical")
        self.assertEqual(payload["orphan_exposure"]["message"], "CRITICAL UNSUPERVISED EXPOSURE")
        by_symbol = {
            item["symbol"]: item
            for item in payload["orphan_exposure"]["items"]
        }
        self.assertEqual(set(by_symbol.keys()), {"NQM6", "YMM6"})
        self.assertEqual(by_symbol["NQM6"]["position_qty"], 1.0)
        self.assertEqual(by_symbol["YMM6"]["position_qty"], -1.0)
        self.assertEqual(by_symbol["NQM6"]["active_order_ids"], ["STOP-NQ-ORPHAN"])
        self.assertEqual(by_symbol["YMM6"]["active_order_ids"], ["STOP-YM-ORPHAN"])
        debug_payload = self.manager.app.test_client().get("/debug/risk_state").get_json()
        self.assertTrue(debug_payload["orphan_exposure"]["has_orphans"])
        self.assertEqual(debug_payload["orphan_exposure"]["severity"], "critical")
        events = self.manager.load_state()["event_log"]
        self.assertTrue(any(
            event.get("event_type") == "critical_orphan_executor_exposure"
            for event in events
        ))

    def test_refresh_recovers_reserved_trade_from_executor_submit_evidence(self):
        self._save_clean_manager_state()
        state = self.manager.load_state()
        trade = self.manager.create_trade_state(
            {
                "event": "enter_trade",
                "symbol": "NQ",
                "direction": "long",
                "position_size": 2,
            },
            {
                "atr_value": 10.0,
                "atr_source": "tradingview_atr_relay",
                "atr_bar_timestamp": "2026-01-01T09:29:00Z",
            },
            requested_symbol="NQ",
            execution_symbol="NQM6",
        )
        trade["trade_id"] = "T-reserved-live"
        state["trades"][trade["trade_id"]] = self.manager.serialize_trade(trade)
        self.manager.save_state(state)
        self.executor.POSITIONS["NQM6"] = {
            "symbol": "NQM6",
            "qty": 2.0,
            "avg_entry_price": 100.0,
        }
        self.executor.ORDERS["ENTRY-reserved-live"] = {
            "order_id": "ENTRY-reserved-live",
            "trade_id": trade["trade_id"],
            "symbol": "NQM6",
            "resolved_symbol": "NQM6",
            "type": "entry",
            "status": "filled",
            "direction": "long",
            "qty": 2.0,
            "filled_price": 100.0,
            "fill_price_source": "executor_actual_fill",
        }
        self.executor.ORDERS["STOP-reserved-live"] = {
            "order_id": "STOP-reserved-live",
            "trade_id": trade["trade_id"],
            "symbol": "NQM6",
            "type": "stop",
            "status": "active",
            "qty": 2.0,
            "stop_price": 90.0,
        }
        self.executor.ORDERS["LIMIT-reserved-live"] = {
            "order_id": "LIMIT-reserved-live",
            "trade_id": trade["trade_id"],
            "symbol": "NQM6",
            "type": "limit",
            "status": "active",
            "qty": 1.0,
            "limit_price": 110.0,
            "tag": "tp1",
        }

        payload = self.manager.app.test_client().get("/trades").get_json()
        recovered = payload["trades"][trade["trade_id"]]

        self.assertFalse(payload["orphan_exposure"]["has_orphans"])
        self.assertEqual(recovered["status"], "active")
        self.assertEqual(recovered["entry_price"], 100.0)
        self.assertEqual(recovered["current_stop"], 90.0)
        self.assertEqual(recovered["tp1_price"], 110.0)
        self.assertEqual(recovered["be_trigger"], 105.0)
        persisted = self.manager.get_trade(trade["trade_id"])
        self.assertEqual(persisted["recovery_status"], "recovered_reserved_submit_from_executor")

    def test_save_state_prevents_stale_active_trade_downgrade(self):
        self._save_clean_manager_state()
        active_state = self.manager.load_state()
        active_trade = self.manager.create_trade_state(
            {
                "event": "enter_trade",
                "symbol": "NQ",
                "direction": "long",
                "position_size": 2,
            },
            {
                "atr_value": 10.0,
                "atr_source": "tradingview_atr_relay",
                "atr_bar_timestamp": "2026-01-01T09:29:00Z",
            },
            requested_symbol="NQ",
            execution_symbol="NQM6",
        )
        active_trade.update({
            "trade_id": "T-stale-save",
            "status": "active",
            "entry_price": 100.0,
            "original_stop": 90.0,
            "current_stop": 90.0,
            "tp1_price": 110.0,
            "be_trigger": 105.0,
            "stop_order_id": "STOP-stale-save",
        })
        active_state["trades"][active_trade["trade_id"]] = self.manager.serialize_trade(active_trade)
        self.manager.save_state(active_state)

        stale_state = self.manager.load_state()
        stale_trade = dict(active_trade)
        stale_trade.update({
            "status": "reserved",
            "entry_price": None,
            "original_stop": None,
            "current_stop": None,
            "tp1_price": None,
            "be_trigger": None,
            "stop_order_id": None,
        })
        stale_state["trades"][active_trade["trade_id"]] = self.manager.serialize_trade(stale_trade)
        self.manager.save_state(stale_state, reason="test_stale_writer")

        persisted = self.manager.get_trade(active_trade["trade_id"])
        self.assertEqual(persisted["status"], "active")
        self.assertEqual(persisted["entry_price"], 100.0)
        events = self.manager.load_state()["event_log"]
        self.assertTrue(any(
            event.get("event_type") == "prevented_active_trade_downgrade"
            for event in events
        ))

    def test_refresh_restores_be_evidence_for_active_runner_from_executor_history(self):
        trade = self._new_short_trade()
        self.manager.process_price_update_by_id(
            trade["trade_id"],
            95,
            self._timestamps(1)[0],
        )
        self.manager.process_price_update_by_id(
            trade["trade_id"],
            90,
            self._timestamps(2)[1],
        )

        persisted = self.manager.get_trade(trade["trade_id"])
        persisted["moved_to_be"] = False
        persisted["be_hit_at"] = None
        self.manager.persist_trade_state(persisted)

        payload = self.manager.app.test_client().get("/trades").get_json()
        recovered = payload["trades"][trade["trade_id"]]

        self.assertEqual(recovered["status"], "active")
        self.assertEqual(recovered["remaining_size"], 1.0)
        self.assertEqual(recovered["stop_state"], "runner_original")
        self.assertTrue(recovered["moved_to_be"])
        self.assertIsNotNone(recovered["be_hit_at"])

    def test_noon_runner_flatten_flattens_active_runner_only(self):
        self._set_noon_runner_flatten_enabled(True)
        trade = self._new_short_trade()
        self.manager.process_price_update_by_id(trade["trade_id"], 95, self._timestamps(1)[0])
        after_tp1 = self.manager.process_price_update_by_id(
            trade["trade_id"],
            90,
            self._timestamps(2)[1],
        )
        self.executor.LAST_PRICES["NQM6"] = 91.0

        result = self.manager.run_noon_runner_flatten_if_due(datetime(2026, 1, 1, 12, 0, 0))

        persisted = self.manager.get_trade(trade["trade_id"])
        self.assertTrue(result["ran"])
        self.assertEqual(result["flattened_trades"], [trade["trade_id"]])
        self.assertEqual(after_tp1["stop_state"], "runner_original")
        self.assertEqual(persisted["status"], "closed")
        self.assertEqual(persisted["exit_reason"], "noon_runner_flatten")
        self.assertEqual(persisted["remaining_size"], 0)
        self.assertEqual(persisted["exit_price"], 91.0)
        self.assertEqual(persisted["tp1_profit"], 200.0)
        self.assertEqual(persisted["runner_profit"], 180.0)
        self.assertEqual(persisted["total_profit"], 380.0)

    def test_noon_runner_flatten_does_not_flatten_full_size_trade_before_tp1(self):
        self._set_noon_runner_flatten_enabled(True)
        trade = self._new_short_trade()

        result = self.manager.run_noon_runner_flatten_if_due(datetime(2026, 1, 1, 12, 0, 0))

        persisted = self.manager.get_trade(trade["trade_id"])
        self.assertTrue(result["ran"])
        self.assertEqual(result["flattened_trades"], [])
        self.assertEqual(persisted["status"], "active")
        self.assertEqual(persisted["remaining_size"], 2)
        self.assertIsNone(persisted["exit_reason"])

    def test_noon_runner_flatten_ignores_closed_trade(self):
        self._set_noon_runner_flatten_enabled(True)
        trade = self._new_short_trade()
        self.manager.simulate_prices_for_trade(
            trade["trade_id"],
            [95, 100],
            self._timestamps(2),
        )

        result = self.manager.run_noon_runner_flatten_if_due(datetime(2026, 1, 1, 12, 0, 0))

        persisted = self.manager.get_trade(trade["trade_id"])
        self.assertTrue(result["ran"])
        self.assertEqual(result["flattened_trades"], [])
        self.assertEqual(persisted["status"], "closed")
        self.assertEqual(persisted["exit_reason"], "stop_hit")

    def test_noon_runner_flatten_non_noon_time_does_nothing(self):
        self._set_noon_runner_flatten_enabled(True)
        trade = self._new_short_trade()
        self.manager.process_price_update_by_id(trade["trade_id"], 95, self._timestamps(1)[0])
        self.manager.process_price_update_by_id(trade["trade_id"], 90, self._timestamps(2)[1])

        result = self.manager.run_noon_runner_flatten_if_due(datetime(2026, 1, 1, 11, 59, 0))

        persisted = self.manager.get_trade(trade["trade_id"])
        self.assertFalse(result["ran"])
        self.assertEqual(result["reason"], "before_noon")
        self.assertEqual(persisted["status"], "active")
        self.assertEqual(persisted["remaining_size"], 1.0)

    def test_debug_risk_state_includes_noon_runner_flatten_status(self):
        self._set_noon_runner_flatten_enabled(True)

        payload = self.manager.app.test_client().get("/debug/risk_state").get_json()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["noon_runner_flatten"]["enabled"])
        self.assertEqual(payload["noon_runner_flatten"]["timezone"], "America/Los_Angeles")

    def test_modified_be_stop_fill_closes_trade_on_reconciliation(self):
        trade = self._new_short_trade()

        after_be = self.manager.process_price_update_by_id(
            trade["trade_id"],
            95,
            self._timestamps(1)[0],
        )
        replacement_stop_id = after_be["stop_order_id"]
        self.assertEqual(replacement_stop_id, trade["stop_order_id"])

        replacement_stop = self.executor.ORDERS[replacement_stop_id]
        replacement_stop["status"] = "closed"
        replacement_stop["filled_at"] = self._timestamps(2)[1].isoformat()
        replacement_stop["filled_price"] = 100.0
        replacement_stop["closed_reason"] = "stop_triggered"
        replacement_stop["fill_trigger_price"] = 100.25
        self.executor.POSITIONS["NQM6"]["qty"] = 0.0
        self.executor.POSITIONS["NQM6"]["avg_entry_price"] = 0.0
        self.executor.save_executor_state()

        public = self._public_trade(trade["trade_id"])
        self.assertEqual(public["status"], "closed")
        self.assertEqual(public["exit_reason"], "stop_hit")
        self.assertEqual(public["exit_price"], 100.0)
        self.assertEqual(public["remaining_size"], 0)

        persisted = self.manager.get_trade(trade["trade_id"])
        self.assertEqual(persisted["status"], "closed")
        self.assertEqual(persisted["recovery_status"], "closed_from_executor_stop_fill")
        self.assertEqual(persisted["stop_order_id"], replacement_stop_id)
        self.assertEqual(persisted["runner_profit"], 0.0)
        self.assertEqual(persisted["total_profit"], 0.0)

    def test_reserved_trade_does_not_receive_price_management_before_levels_are_persisted(self):
        original_place_entry_order = self.manager.place_entry_order
        injected = {"done": False}

        def place_entry_order_with_price_callback(*args, **kwargs):
            response = original_place_entry_order(*args, **kwargs)
            if not injected["done"]:
                injected["done"] = True
                self.manager.on_price("NQM6", 99.0)
            return response

        self.manager.place_entry_order = place_entry_order_with_price_callback
        try:
            trade = self._new_short_trade()
        finally:
            self.manager.place_entry_order = original_place_entry_order

        self.assertEqual(trade["status"], "active")
        self.assertEqual(trade["entry_price"], 100.0)
        self.assertEqual(trade["original_stop"], 110.0)
        self.assertEqual(trade["tp1_price"], 90.0)
        self.assertEqual(trade["be_trigger"], 95.0)

        persisted = self.manager.get_trade(trade["trade_id"])
        self.assertEqual(persisted["status"], "active")
        self.assertEqual(persisted["entry_price"], 100.0)
        self.assertEqual(persisted["original_stop"], 110.0)
        self.assertEqual(persisted["tp1_price"], 90.0)
        self.assertEqual(persisted["be_trigger"], 95.0)
        self.assertEqual(
            [
                event["event_type"]
                for event in self._events(trade["trade_id"])
                if event["event_type"] == "price_update_received"
            ],
            [],
        )

    def test_trades_payload_repairs_missing_be_trigger_from_entry_and_tp1(self):
        trade = self._new_short_trade()
        state = self.manager.load_state()
        state["trades"][trade["trade_id"]]["be_trigger"] = None
        self.manager.save_state(state)

        payload = self.manager.app.test_client().get("/trades").get_json()
        public_trade = payload["trades"][trade["trade_id"]]

        self.assertEqual(public_trade["status"], "active")
        self.assertEqual(public_trade["entry_price"], 100.0)
        self.assertEqual(public_trade["tp1_price"], 90.0)
        self.assertEqual(public_trade["be_trigger"], 95.0)
        self.assertEqual(self.manager.get_trade(trade["trade_id"])["be_trigger"], 95.0)

    def test_modified_be_stop_fill_does_not_close_concurrent_ym_trade(self):
        nq_trade = self._new_short_trade()
        ym_trade = self._new_trade(symbol="YMM6", price=40000.0)

        after_be = self.manager.process_price_update_by_id(
            nq_trade["trade_id"],
            95,
            self._timestamps(1)[0],
        )
        replacement_stop_id = after_be["stop_order_id"]

        replacement_stop = self.executor.ORDERS[replacement_stop_id]
        replacement_stop["status"] = "closed"
        replacement_stop["filled_at"] = self._timestamps(2)[1].isoformat()
        replacement_stop["filled_price"] = 100.0
        replacement_stop["closed_reason"] = "stop_triggered"
        replacement_stop["fill_trigger_price"] = 100.25
        self.executor.POSITIONS["NQM6"]["qty"] = 0.0
        self.executor.POSITIONS["NQM6"]["avg_entry_price"] = 0.0
        self.executor.save_executor_state()

        client = self.manager.app.test_client()
        data = client.get("/trades").get_json()
        self.assertTrue(data["ok"])

        nq_public = data["trades"][nq_trade["trade_id"]]
        ym_public = data["trades"][ym_trade["trade_id"]]

        self.assertEqual(nq_public["status"], "closed")
        self.assertEqual(self.manager.get_trade(nq_trade["trade_id"])["stop_order_id"], replacement_stop_id)
        self.assertEqual(ym_public["status"], "active")
        self.assertEqual(ym_public["symbol"], "YMM6")
        self.assertGreater(ym_public["remaining_size"], 0)

    def test_scenario_c_full_stop_loss(self):
        trade = self._new_short_trade()
        self.manager.simulate_prices_for_trade(
            trade["trade_id"],
            [101, 105, 110],
            self._timestamps(3),
        )

        public = self._public_trade(trade["trade_id"])
        self.assertFalse(public["moved_to_be"])
        self.assertFalse(public["tp1_hit"])
        self.assertEqual(public["exit_reason"], "stop_hit")
        self.assertEqual(public["exit_price"], 110.0)
        self.assertEqual(public["realized_pnl"], -400.0)
        self.assertEqual(public["remaining_size"], 0)
        self._assert_event_sequence(trade["trade_id"], [
            "submit_accepted",
            "entry_filled",
            "original_stop_placed",
            "tp1_order_active",
            "stop_hit_close",
            "final_trade_persistence_snapshot",
        ])
        self._assert_flat_reconciled(trade)

    def test_stop_hit_close_is_persisted_immediately(self):
        class FakeUuid:
            hex = "e2fca719000000000000000000000000"

        original_uuid4 = self.manager.uuid.uuid4
        try:
            self.manager.uuid.uuid4 = lambda: FakeUuid()
            trade = self._new_short_trade()
        finally:
            self.manager.uuid.uuid4 = original_uuid4
        trade["last_price"] = 110.0
        self.assertEqual(trade["trade_id"], "T-e2fca719")

        timestamp = datetime(2026, 4, 23, 9, 45, 0)
        self.manager.handle_stop_hit(trade, timestamp)

        persisted_state = json.loads(self.persistence_file.read_text(encoding="utf-8"))
        self.assertIn("T-e2fca719", persisted_state["trades"])
        persisted = persisted_state["trades"]["T-e2fca719"]
        self.assertEqual(persisted["status"], "closed")
        self.assertEqual(persisted["closed_at"], timestamp.isoformat())
        self.assertEqual(persisted["exit_reason"], "stop_hit")
        self.assertEqual(persisted["exit_price"], 110.0)
        self.assertEqual(persisted["realized_pnl"], -400.0)
        self.assertEqual(persisted["remaining_size"], 0)

        public = self._public_trade("T-e2fca719")
        self.assertEqual(public["status"], "closed")
        self.assertEqual(public["exit_reason"], "stop_hit")
        self.assertEqual(public["remaining_size"], 0)

    def test_realized_pnl_is_signed_dollars(self):
        cases = [
            ({"symbol": "NQM6", "direction": "short", "entry_price": 100, "exit_price": 99.5, "position_size": 2}, 20.0),
            ({"symbol": "NQM6", "direction": "short", "entry_price": 100, "exit_price": 100.5, "position_size": 2}, -20.0),
            ({"symbol": "NQM6", "direction": "short", "entry_price": 100, "exit_price": 100, "position_size": 2, "tp1_hit": True, "tp1_filled_qty": 1, "tp1_exit_price": 90}, 200.0),
            ({"symbol": "NQM6", "direction": "long", "entry_price": 100, "exit_price": 100.5, "position_size": 2}, 20.0),
            ({"symbol": "NQM6", "direction": "long", "entry_price": 100, "exit_price": 99.5, "position_size": 2}, -20.0),
            ({"symbol": "NQM6", "direction": "long", "entry_price": 100, "exit_price": 100, "position_size": 2, "tp1_hit": True, "tp1_filled_qty": 1, "tp1_exit_price": 110}, 200.0),
        ]
        for trade, expected in cases:
            with self.subTest(trade=trade):
                self.assertEqual(self.manager.calculate_realized_pnl(trade), expected)

    def test_atr_derived_distances_are_ceiled_independently(self):
        self.assertEqual(self.manager.calculate_atr_distance(10.1), 11.0)
        self.assertEqual(self.manager.calculate_atr_distance(10.1, 0.5), 6.0)

        long_levels = self.manager.derive_trade_levels(100, "NQM6", "long", 10.1)
        self.assertEqual(long_levels["original_stop"], 89.0)
        self.assertEqual(long_levels["current_stop"], 89.0)
        self.assertEqual(long_levels["tp1_price"], 111.0)
        self.assertEqual(long_levels["be_trigger"], 106.0)

        short_levels = self.manager.derive_trade_levels(100, "NQM6", "short", 10.1)
        self.assertEqual(short_levels["original_stop"], 111.0)
        self.assertEqual(short_levels["current_stop"], 111.0)
        self.assertEqual(short_levels["tp1_price"], 89.0)
        self.assertEqual(short_levels["be_trigger"], 94.0)

        trade = self.manager.create_trade_state({
            "symbol": "NQ",
            "direction": "short",
            "position_size": 2,
        }, {
            "atr_value": 10.1,
            "atr_source": "offline_replay",
            "atr_bar_timestamp": "2026-01-01T09:29:00Z",
        }, "NQ", "NQM6")
        self.assertEqual(trade["atr_value"], 10.1)

    def test_tradingview_webhook_normalizes_and_submits_trade(self):
        self.assertEqual(self.manager.normalize_tradingview_symbol("CME_MINI:NQ1!"), "NQ")
        self.assertEqual(self.manager.normalize_tradingview_direction("sell"), "short")

        self.executor.LAST_PRICES["NQM6"] = 100.0
        client = self.manager.app.test_client()
        atr_response = client.post("/webhook/tradingview/atr", json={
            "event": "tv_atr_update",
            "symbol": "NQ",
            "atr_period": 14,
            "atr_value": 10.1,
            "timeframe": "1",
            "source": "tradingview",
        })
        self.assertEqual(atr_response.status_code, 200)
        response = client.post("/webhook/tradingview", json={
            "event": "tv_enter_trade",
            "symbol": "CME_MINI:NQM6",
            "direction": "sell",
            "position_size": 2,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["source"], "tradingview")
        self.assertEqual(data["trade"]["symbol"], "NQM6")
        self.assertEqual(data["trade"]["direction"], "short")
        self.assertEqual(data["trade"]["remaining_size"], 2)
        self.assertEqual(data["trade"]["original_stop"], 111.0)
        self.assertEqual(data["trade"]["tp1_price"], 89.0)
        self._assert_event_sequence(data["trade_id"], [
            "submit_accepted",
            "entry_filled",
            "original_stop_placed",
            "tp1_order_active",
            "final_trade_persistence_snapshot",
        ])

    def test_tradingview_atr_webhook_stores_atr_without_submitting_trade(self):
        client = self.manager.app.test_client()
        response = client.post("/webhook/tradingview/atr", json={
            "event": "tv_atr_update",
            "symbol": "CME_MINI:NQ1!",
            "atr_period": 14,
            "atr_value": 23.5,
            "timeframe": "1",
            "source": "tradingview",
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["atr"]["symbol"], "NQ")
        self.assertEqual(data["atr"]["atr_period"], 14)
        self.assertEqual(data["atr"]["atr_value"], 23.5)
        self.assertEqual(data["atr"]["timeframe"], "1")
        self.assertEqual(data["atr"]["source"], "tradingview")

        state = self.manager.load_state()
        self.assertEqual(state["trades"], {})
        self.assertEqual(state["tradingview_atr"]["NQ"]["atr_value"], 23.5)
        self.assertEqual(self.manager.TRADINGVIEW_ATR_CACHE["NQ"]["atr_value"], 23.5)

        lookup = client.get("/debug/tradingview/atr/NQ").get_json()
        self.assertTrue(lookup["ok"])
        self.assertEqual(lookup["atr"]["atr_value"], 23.5)

        bad_response = client.post("/webhook/tradingview/atr", json={
            "event": "tv_enter_trade",
            "symbol": "NQ",
            "atr_period": 14,
            "atr_value": 23.5,
            "timeframe": "1",
            "source": "tradingview",
        })
        self.assertEqual(bad_response.status_code, 400)
        self.assertEqual(self.manager.load_state()["trades"], {})

    def test_tradingview_atr_status_reports_fresh_records(self):
        client = self.manager.app.test_client()
        now = datetime.now()
        state = self.manager.load_state()
        state["tradingview_atr"] = {
            "NQ": {
                "symbol": "NQ",
                "atr_period": 14,
                "atr_value": 10.5,
                "timeframe": "1",
                "source": "tradingview",
                "received_at": (now - timedelta(seconds=30)).isoformat(),
                "raw_event": "tv_atr_update",
            },
            "YM": {
                "symbol": "YM",
                "atr_period": 14,
                "atr_value": 20.25,
                "timeframe": "1",
                "source": "tradingview",
                "received_at": (now - timedelta(seconds=45)).isoformat(),
                "raw_event": "tv_atr_update",
            },
        }
        self.manager.save_state(state)
        self.manager.TRADINGVIEW_ATR_CACHE.clear()

        response = client.get("/debug/tradingview/atr_status")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        statuses = {item["symbol"]: item for item in data["symbols"]}
        self.assertEqual(statuses["NQ"]["status"], "fresh")
        self.assertEqual(statuses["YM"]["status"], "fresh")
        self.assertEqual(statuses["NQ"]["atr_value"], 10.5)
        self.assertEqual(statuses["YM"]["atr_value"], 20.25)
        self.assertLessEqual(statuses["NQ"]["age_seconds"], 180)
        self.assertLessEqual(statuses["YM"]["age_seconds"], 180)

    def test_tradingview_atr_status_reports_stale_records(self):
        client = self.manager.app.test_client()
        now = datetime.now()
        state = self.manager.load_state()
        state["tradingview_atr"] = {
            "NQ": {
                "symbol": "NQ",
                "atr_period": 14,
                "atr_value": 9.75,
                "timeframe": "1",
                "source": "tradingview",
                "received_at": (now - timedelta(seconds=181)).isoformat(),
                "raw_event": "tv_atr_update",
            },
            "YM": {
                "symbol": "YM",
                "atr_period": 14,
                "atr_value": 18.0,
                "timeframe": "1",
                "source": "tradingview",
                "received_at": (now - timedelta(seconds=247)).isoformat(),
                "raw_event": "tv_atr_update",
            },
        }
        self.manager.save_state(state)
        self.manager.TRADINGVIEW_ATR_CACHE.clear()

        response = client.get("/debug/tradingview/atr_status")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        statuses = {item["symbol"]: item for item in data["symbols"]}
        self.assertEqual(statuses["NQ"]["status"], "stale")
        self.assertEqual(statuses["YM"]["status"], "stale")
        self.assertGreater(statuses["NQ"]["age_seconds"], 180)
        self.assertGreater(statuses["YM"]["age_seconds"], 180)

    def test_tradingview_atr_status_reports_missing_records(self):
        client = self.manager.app.test_client()
        self.manager.save_state(self.manager.build_default_state())
        self.manager.TRADINGVIEW_ATR_CACHE.clear()

        response = client.get("/debug/tradingview/atr_status")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        statuses = {item["symbol"]: item for item in data["symbols"]}
        self.assertEqual(statuses["NQ"]["status"], "missing")
        self.assertEqual(statuses["YM"]["status"], "missing")
        self.assertIsNone(statuses["NQ"]["atr_value"])
        self.assertIsNone(statuses["YM"]["atr_value"])
        self.assertIsNone(statuses["NQ"]["received_at"])
        self.assertIsNone(statuses["YM"]["received_at"])

    def test_atr_shadow_debug_endpoint_returns_latest_comparison(self):
        self.atr_shadow_file.write_text(json.dumps({
            "updated_at": "2026-04-30T13:45:05Z",
            "symbols": {
                "NQM6": {
                    "symbol": "NQM6",
                    "timestamp": "2026-04-30T13:45:05Z",
                    "tv_atr": 22.73,
                    "tv_atr_timestamp": "2026-04-30T13:45:00Z",
                    "rithmic_atr": 22.55,
                    "rithmic_atr_timestamp": "2026-04-30T13:45:00Z",
                    "delta_abs": 0.18,
                    "delta_pct": 0.791905,
                    "completed_bar_count": 15,
                    "contiguous_bar_count": 15,
                    "gap_detected": False,
                    "atr_status": "OK",
                    "feed_status": "LIVE",
                    "source": "rithmic_worker_atr_shadow",
                },
                "NQ": {
                    "symbol": "NQ",
                    "timestamp": "2026-04-30T13:45:05Z",
                    "tv_atr": 22.73,
                    "rithmic_atr": 22.55,
                    "delta_abs": 0.18,
                    "delta_pct": 0.791905,
                    "completed_bar_count": 15,
                    "contiguous_bar_count": 15,
                    "gap_detected": False,
                    "atr_status": "OK",
                    "feed_status": "LIVE",
                    "source": "rithmic_worker_atr_shadow",
                },
            },
        }), encoding="utf-8")

        client = self.manager.app.test_client()
        all_payload = client.get("/debug/atr_shadow").get_json()
        symbol_payload = client.get("/debug/atr_shadow/NQ").get_json()

        self.assertTrue(all_payload["ok"])
        self.assertEqual(all_payload["symbols"]["NQM6"]["source"], "rithmic_worker_atr_shadow")
        self.assertTrue(symbol_payload["ok"])
        self.assertEqual(symbol_payload["atr_shadow"]["atr_status"], "OK")
        self.assertEqual(symbol_payload["atr_shadow"]["rithmic_atr"], 22.55)

    def test_submit_trade_uses_tradingview_atr_when_rithmic_not_ready(self):
        if self.atr_snapshot_file.exists():
            self.atr_snapshot_file.unlink()

        self.executor.LAST_PRICES["NQM6"] = 100.0
        client = self.manager.app.test_client()

        atr_response = client.post("/webhook/tradingview/atr", json={
            "event": "tv_atr_update",
            "symbol": "NQ",
            "atr_period": 14,
            "atr_value": 10.1,
            "timeframe": "1",
            "source": "tradingview",
        })
        self.assertEqual(atr_response.status_code, 200)

        submit_response = client.post("/submit_trade", json={
            "event": "enter_trade",
            "symbol": "NQ",
            "direction": "short",
            "position_size": 2,
        })
        data = submit_response.get_json()

        self.assertEqual(submit_response.status_code, 200)
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["symbol"], "NQM6")
        self.assertEqual(data["requested_symbol"], "NQ")
        self.assertEqual(data["atr_source"], "tradingview_atr_relay")
        self.assertEqual(data["atr_value"], 10.1)
        self.assertEqual(data["original_stop"], 111.0)
        self.assertEqual(data["tp1_price"], 89.0)
        self.assertEqual(data["be_trigger"], 94.0)
        self._assert_event_sequence(data["trade_id"], [
            "submit_accepted",
            "entry_filled",
            "original_stop_placed",
            "tp1_order_active",
            "final_trade_persistence_snapshot",
        ])

    def test_submit_trade_requires_fresh_tradingview_atr(self):
        client = self.manager.app.test_client()
        self.executor.LAST_PRICES["YMM6"] = 42000.0
        atr_response = client.post("/webhook/tradingview/atr", json={
            "event": "tv_atr_update",
            "symbol": "YM",
            "atr_period": 14,
            "atr_value": 25.0,
            "timeframe": "1",
            "source": "tradingview",
        })
        self.assertEqual(atr_response.status_code, 200)

        submit_response = client.post("/submit_trade", json={
            "event": "enter_trade",
            "symbol": "YM",
            "direction": "short",
            "position_size": 2,
        })
        data = submit_response.get_json()

        self.assertEqual(submit_response.status_code, 200)
        self.assertEqual(data["atr_source"], "tradingview_atr_relay")
        self.assertEqual(data["atr_value"], 25.0)

    def test_submit_trade_blocks_when_tradingview_atr_stale(self):
        self._write_atr_snapshot(10.0, ym_atr_value=25.0)
        self.executor.LAST_PRICES["YMM6"] = 42000.0
        state = self.manager.load_state()
        state["tradingview_atr"]["YM"] = {
            "symbol": "YM",
            "atr_period": 14,
            "atr_value": 25.0,
            "timeframe": "1",
            "source": "tradingview",
            "received_at": (datetime.now() - timedelta(seconds=self.manager.TRADINGVIEW_ATR_MAX_AGE_SECONDS + 5)).isoformat(),
            "raw_event": "tv_atr_update",
        }
        self.manager.save_state(state)
        self.manager.TRADINGVIEW_ATR_CACHE.clear()

        client = self.manager.app.test_client()
        response = client.post("/submit_trade", json={
            "event": "enter_trade",
            "symbol": "YM",
            "direction": "short",
            "position_size": 2,
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "TV_ATR_STALE")

    def test_submit_trade_blocks_when_tradingview_atr_missing(self):
        self._write_atr_snapshot(10.0, ym_atr_value=25.0)
        self.executor.LAST_PRICES["NQM6"] = 100.0
        self.manager.save_state(self.manager.build_default_state())
        self.manager.TRADINGVIEW_ATR_CACHE.clear()

        client = self.manager.app.test_client()
        response = client.post("/submit_trade", json={
            "event": "enter_trade",
            "symbol": "NQ",
            "direction": "short",
            "position_size": 2,
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "TV_ATR_MISSING")

    def test_rithmic_atr_present_but_tradingview_stale_still_blocks_submit(self):
        self._write_atr_snapshot(10.0, ym_atr_value=25.0)
        self.executor.LAST_PRICES["NQM6"] = 100.0
        state = self.manager.load_state()
        state["tradingview_atr"]["NQ"] = {
            "symbol": "NQ",
            "atr_period": 14,
            "atr_value": 10.1,
            "timeframe": "1",
            "source": "tradingview",
            "received_at": (datetime.now() - timedelta(seconds=self.manager.TRADINGVIEW_ATR_MAX_AGE_SECONDS + 30)).isoformat(),
            "raw_event": "tv_atr_update",
        }
        self.manager.save_state(state)
        self.manager.TRADINGVIEW_ATR_CACHE.clear()

        client = self.manager.app.test_client()
        response = client.post("/submit_trade", json={
            "event": "enter_trade",
            "symbol": "NQ",
            "direction": "short",
            "position_size": 2,
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "TV_ATR_STALE")

    def test_submit_trade_creates_ym_trade_only(self):
        self._write_atr_snapshot(10.0, ym_atr_value=25.0)
        trade = self._new_trade(symbol="YM", price=42000.0)

        self.assertEqual(trade["symbol"], "YMM6")
        self.assertEqual(trade["requested_symbol"], "YM")
        self.assertEqual(trade["execution_symbol"], "YMM6")
        self.assertEqual(trade["atr_value"], 25.0)
        self.assertEqual(self.executor.POSITIONS["YMM6"]["qty"], -2.0)
        self.assertNotIn("NQM6", [order.get("symbol") for order in self._executor_orders(trade["trade_id"])])

    def test_one_symbol_management_event_does_not_modify_other_trade(self):
        self._write_atr_snapshot(10.0, ym_atr_value=25.0)
        nq_trade = self._new_trade(symbol="NQ", price=100.0)
        ym_trade = self._new_trade(symbol="YM", price=42000.0)
        self.executor.LAST_PRICES["YMM6"] = 41975.0

        self.manager.process_price_update_by_id(
            ym_trade["trade_id"],
            41975.0,
            self._timestamps(1)[0],
        )

        nq_public = self._public_trade(nq_trade["trade_id"])
        ym_public = self._public_trade(ym_trade["trade_id"])

        self.assertFalse(nq_public["tp1_hit"])
        self.assertEqual(nq_public["remaining_size"], 2)
        self.assertIn("NQM6", self.executor.POSITIONS)
        self.assertEqual(self.executor.POSITIONS["NQM6"]["qty"], -2.0)
        self.assertTrue(ym_public["tp1_hit"])
        self.assertEqual(ym_public["remaining_size"], 1.0)

    def test_flat_cleanup_only_clears_orders_for_flat_symbol(self):
        self.executor.POSITIONS["NQM6"] = {
            "qty": 0.0,
            "avg_entry_price": 0.0,
        }
        self.executor.POSITIONS["YMM6"] = {
            "qty": -1.0,
            "avg_entry_price": 42000.0,
        }
        self.executor.ORDERS["STOP-NQ"] = {
            "order_id": "STOP-NQ",
            "trade_id": "T-nq",
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 101.0,
            "qty": 1.0,
            "status": "active",
        }
        self.executor.ORDERS["STOP-YM"] = {
            "order_id": "STOP-YM",
            "trade_id": "T-ym",
            "type": "stop",
            "symbol": "YMM6",
            "stop_price": 42025.0,
            "qty": 1.0,
            "status": "active",
        }

        data = self.executor.app.test_client().get("/sync_snapshot").get_json()

        self.assertEqual(data["symbols"]["NQM6"]["working_orders"], [])
        self.assertEqual(len(data["symbols"]["YMM6"]["working_orders"]), 1)
        self.assertEqual(self.executor.ORDERS["STOP-NQ"]["status"], "cancelled")
        self.assertEqual(self.executor.ORDERS["STOP-YM"]["status"], "active")

    def test_regression_t_4bcb7c2f_reconstructed_bug_is_detected(self):
        bad_trade = {
            "trade_id": "T-4bcb7c2f",
            "symbol": "NQM6",
            "direction": "short",
            "entry_price": 26774.25,
            "original_stop": 26800.5,
            "current_stop": 26800.5,
            "tp1_price": 26748.0,
            "be_trigger": 26761.0,
            "position_size": 2,
            "remaining_size": 0,
            "status": "closed",
            "tp1_hit": False,
            "moved_to_be": False,
            "stop_state": "original",
            "created_at": "2026-04-21T06:45:12.158918",
            "exit_price": None,
            "exit_reason": "stop_hit",
            "closed_at": "2026-04-21T06:53:53.742416",
        }
        state = self.manager.build_default_state()
        state["trades"][bad_trade["trade_id"]] = bad_trade
        self.manager.save_state(state)

        self.executor.ORDERS.update({
            "ENTRY-93cc7730": {
                "order_id": "ENTRY-93cc7730",
                "trade_id": "T-4bcb7c2f",
                "type": "entry",
                "symbol": "NQM6",
                "status": "filled",
                "filled_at": "2026-04-21T06:45:14.182848",
                "filled_price": 26774.25,
                "qty": 2.0,
            },
            "STOP-f5b4ad2c": {
                "order_id": "STOP-f5b4ad2c",
                "trade_id": "T-4bcb7c2f",
                "type": "stop",
                "symbol": "NQM6",
                "stop_price": 26800.5,
                "qty": 2.0,
                "status": "cancelled",
                "created_at": "2026-04-21T06:45:16.218379",
                "cancelled_at": "2026-04-21T06:45:57.702066",
            },
            "STOP-4549a4fa": {
                "order_id": "STOP-4549a4fa",
                "trade_id": "T-4bcb7c2f",
                "type": "stop",
                "symbol": "NQM6",
                "stop_price": 26774.25,
                "qty": 2.0,
                "status": "closed",
                "created_at": "2026-04-21T06:45:24.770966",
                "closed_at": "2026-04-21T06:53:53.909426",
            },
            "LIMIT-a1af6b8a": {
                "order_id": "LIMIT-a1af6b8a",
                "trade_id": "T-4bcb7c2f",
                "type": "limit",
                "symbol": "NQM6",
                "limit_price": 26748.0,
                "qty": 1.0,
                "status": "closed",
                "created_at": "2026-04-21T06:45:47.728257",
                "closed_at": "2026-04-21T06:53:53.909426",
            },
        })
        self.executor.save_executor_state()

        replay = self._replay("T-4bcb7c2f")
        self.assertIn("executor_has_be_stop_but_persistence_lost_be_state", replay["audit"]["observed_inconsistencies"])
        self.assertIn("executor_has_tp1_limit_but_persistence_has_tp1_hit_false", replay["audit"]["observed_inconsistencies"])
        self.assertIn("closed_trade_missing_exit_price", replay["audit"]["observed_inconsistencies"])


if __name__ == "__main__":
    unittest.main()
