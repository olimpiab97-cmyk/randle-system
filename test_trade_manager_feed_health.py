import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class FrozenDateTime(datetime):
    current = datetime(2026, 5, 4, 5, 22, 35, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls.current.replace(tzinfo=None)
        return cls.current.astimezone(tz)


class TradeManagerFeedHealthTests(unittest.TestCase):
    def setUp(self):
        sys.dont_write_bytecode = True
        FrozenDateTime.current = datetime(2026, 5, 4, 5, 22, 35, tzinfo=timezone.utc)
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.manager = self._load_trade_manager()
        self.feed_health_file = self.tmp_path / "rithmic_feed_health.json"
        self.persistence_file = self.tmp_path / "persistence_state.json"
        self.atr_snapshot_file = self.tmp_path / "rithmic_atr_snapshot.json"
        self.recent_bars_file = self.tmp_path / "rithmic_recent_bars.json"
        self.manager.RITHMIC_FEED_HEALTH_FILE = str(self.feed_health_file)
        self.manager.PERSISTENCE_FILE = str(self.persistence_file)
        self.manager.RITHMIC_ATR_SNAPSHOT_FILE = str(self.atr_snapshot_file)
        self.manager.RITHMIC_RECENT_BARS_FILE = str(self.recent_bars_file)
        self.manager.datetime = FrozenDateTime
        self.manager.TRADINGVIEW_ATR_CACHE.clear()
        self.manager.RISK_STATE.update({
            "kill_switch_active": False,
            "kill_switch_reason": None,
            "daily_trade_count": 0,
            "daily_loss_count": 0,
            "max_daily_trades": 10,
            "max_daily_losses": 10,
            "kill_switch_drawdown_pct": 11.0,
            "current_drawdown_pct": 0.0,
            "trading_halted": False,
            "last_reset_date": FrozenDateTime.current.date().isoformat(),
        })
        self.manager.FAILURE_STATE.update({
            "execution_failure_count": 0,
            "qa_critical_count": 0,
            "max_execution_failures": 10,
            "max_qa_critical": 10,
            "last_failure_at": None,
            "halt_reason": None,
        })
        self.manager.FEED_REJECTION_COUNTS.clear()
        self.manager.QA_LOGS.clear()
        self.manager.PRICE_INTEGRITY_DEGRADED_STATE.clear()
        self._original_mode_env = os.environ.pop("RANDLE_TRADE_MANAGER_MODE", None)

    def tearDown(self):
        if self._original_mode_env is None:
            os.environ.pop("RANDLE_TRADE_MANAGER_MODE", None)
        else:
            os.environ["RANDLE_TRADE_MANAGER_MODE"] = self._original_mode_env
        self.tmp.cleanup()

    def _load_trade_manager(self):
        spec = importlib.util.spec_from_file_location(
            "feed_health_trade_manager",
            ROOT / "Engines" / "trade_manager.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _write_feed_health(self, symbol="NQM6", tick_timestamp="2026-05-04T05:22:33Z"):
        payload = {
            "symbols": {
                symbol: {
                    "feed_status": "QUIET",
                    "feed_age_seconds": 2.1,
                    "feed_quiet_seconds": 2.0,
                    "feed_stale_seconds": 3.0,
                    "feed_disconnected_seconds": 10.0,
                    "last_tick_timestamp_utc": tick_timestamp,
                    "last_bridge_post_timestamp_utc": tick_timestamp,
                    "last_successful_executor_price_post_timestamp_utc": tick_timestamp,
                },
                "NQ": {
                    "feed_status": "QUIET",
                    "feed_age_seconds": 2.1,
                    "feed_quiet_seconds": 2.0,
                    "feed_stale_seconds": 3.0,
                    "feed_disconnected_seconds": 10.0,
                    "last_tick_timestamp_utc": tick_timestamp,
                    "last_bridge_post_timestamp_utc": tick_timestamp,
                    "last_successful_executor_price_post_timestamp_utc": tick_timestamp,
                },
            },
            "system_state_feed": "STALE",
            "warning": "RITHMIC FEED STALE  EXECUTION ONLY MODE",
            "updated_at_utc": "2026-05-04T05:22:35Z",
        }
        self.feed_health_file.write_text(json.dumps(payload), encoding="utf-8")

    def _write_live_feed_health(self, tick_timestamp="2026-05-04T05:22:34Z"):
        self._write_feed_health_status("LIVE", tick_timestamp=tick_timestamp)

    def _write_feed_health_status(
        self,
        status,
        tick_timestamp=None,
        age_seconds=None,
        quiet_seconds=None,
        stale_seconds=None,
        disconnected_seconds=None,
    ):
        status = str(status).upper()
        if tick_timestamp is None:
            age_by_status = {
                "LIVE": 1,
                "QUIET": 3,
                "STALE": 31,
                "DEAD": 61,
                "INVALID": 1,
            }
            if age_seconds is None:
                age_seconds = age_by_status.get(status, 1)
            tick_timestamp = (
                FrozenDateTime.current - timedelta(seconds=age_seconds)
            ).isoformat()
        symbols = {}
        for symbol in ("NQM6", "NQ"):
            symbol_quiet_seconds = quiet_seconds
            symbol_stale_seconds = stale_seconds
            symbol_disconnected_seconds = disconnected_seconds
            if status == "INVALID":
                symbol_quiet_seconds = None
                symbol_stale_seconds = None
                symbol_disconnected_seconds = None
            else:
                symbol_quiet_seconds = 2.0 if symbol_quiet_seconds is None else symbol_quiet_seconds
                symbol_stale_seconds = 30.0 if symbol_stale_seconds is None else symbol_stale_seconds
                symbol_disconnected_seconds = 60.0 if symbol_disconnected_seconds is None else symbol_disconnected_seconds
            symbols[symbol] = {
                "feed_status": status,
                "feed_age_seconds": 1.0,
                "feed_quiet_seconds": symbol_quiet_seconds,
                "feed_stale_seconds": symbol_stale_seconds,
                "feed_disconnected_seconds": symbol_disconnected_seconds,
                "last_tick_timestamp_utc": tick_timestamp,
                "last_bridge_post_timestamp_utc": tick_timestamp,
                "last_successful_executor_price_post_timestamp_utc": tick_timestamp,
            }
            if status in {"LIVE", "QUIET"}:
                symbols[symbol].update({
                    "last_price": 27000.25,
                    "last_price_source": "trade_manager_price_route",
                    "feed_health_source": "trade_manager_price_route",
                })
        self.feed_health_file.write_text(json.dumps({
            "symbols": symbols,
            "system_state_feed": status,
            "updated_at_utc": tick_timestamp,
        }), encoding="utf-8")

    def _write_active_trade_state(self):
        timestamp = FrozenDateTime.current.isoformat()
        trade = {
            "trade_id": "TRADE-FEED-1",
            "created_at": timestamp,
            "updated_at": timestamp,
            "symbol": "NQM6",
            "requested_symbol": "NQM6",
            "execution_symbol": "NQM6",
            "direction": "long",
            "status": "active",
            "entry_price": 27000.0,
            "original_stop": 26900.0,
            "current_stop": 26900.0,
            "be_trigger": 27050.0,
            "tp1_price": 27100.0,
            "position_size": 2,
            "remaining_size": 2,
            "moved_to_be": False,
            "tp1_hit": False,
            "stop_state": "original",
            "stop_order_id": "STOP-1",
            "tp1_order_id": "LIMIT-1",
            "locked": False,
        }
        self.persistence_file.write_text(json.dumps({
            "trades": {trade["trade_id"]: trade},
            "event_log": [],
            "system": {"last_update_at": timestamp},
            "tradingview_atr": {},
        }), encoding="utf-8")
        return trade

    def _run_price_update_with_feed_status(self, status, price=27010.0, **feed_kwargs):
        self._write_feed_health_status(status, **feed_kwargs)
        self._write_active_trade_state()
        self.manager.fetch_executor_orders = lambda *args, **kwargs: []
        self.manager.run_qa_checks = lambda *args, **kwargs: None
        self.manager.run_noon_runner_flatten_if_due = lambda *args, **kwargs: None

        self.manager.on_price("NQM6", price, tick_timestamp=FrozenDateTime.current.isoformat())

        state = json.loads(self.persistence_file.read_text(encoding="utf-8"))
        return state["trades"]["TRADE-FEED-1"]

    def _write_entry_atr(self):
        timestamp = FrozenDateTime.current.isoformat()
        self.persistence_file.write_text(json.dumps({
            "trades": {},
            "event_log": [],
            "system": {"last_update_at": timestamp},
            "tradingview_atr": {
                "NQ": {
                    "symbol": "NQ",
                    "atr_period": 14,
                    "atr_value": 10.0,
                    "timeframe": "1",
                    "source": "tradingview",
                    "received_at": timestamp,
                    "raw_event": "tv_atr_update",
                },
                "NQM6": {
                    "symbol": "NQM6",
                    "atr_period": 14,
                    "atr_value": 10.0,
                    "timeframe": "1",
                    "source": "tradingview",
                    "received_at": timestamp,
                    "raw_event": "tv_atr_update",
                },
            },
        }), encoding="utf-8")
        self.atr_snapshot_file.write_text(json.dumps({
            "symbols": {
                "NQM6": {
                    "atr_value": 10.0,
                    "atr_bar_timestamp": timestamp,
                    "atr_source": "test",
                }
            }
        }), encoding="utf-8")
        self.recent_bars_file.write_text(json.dumps({"symbols": {"NQM6": []}}), encoding="utf-8")

    def _executor_snapshot(
        self,
        *,
        price=27000.25,
        age=1.0,
        last_price_at=None,
        symbol="NQM6",
        listener_tick_id=None,
        listener_sequence=None,
        executor_sequence=None,
    ):
        if last_price_at is None:
            last_price_at = FrozenDateTime.current - timedelta(seconds=age)
        return {
            symbol: {
                "last_price": price,
                "last_price_at": last_price_at.isoformat(),
                "listener_tick_id": listener_tick_id,
                "executor_tick_id": listener_tick_id,
                "listener_sequence": listener_sequence,
                "executor_sequence": executor_sequence,
                "last_tick_age_seconds": age,
                "listener_last_tick_max_age_seconds": 5.0,
                "listener_status": "non_authoritative",
                "listener_status_reason": "executor_snapshot_is_not_feed_authority",
            }
        }

    def _post_trade_manager_price(
        self,
        symbol,
        tick_timestamp=None,
        price=27000.25,
        listener_tick_id=None,
        listener_sequence=None,
        executor_sequence=None,
    ):
        if tick_timestamp is None:
            tick_timestamp = FrozenDateTime.current.isoformat()
        client = self.manager.app.test_client()
        response = client.post("/price", json={
            "symbol": symbol,
            "price": price,
            "tick_timestamp_utc": tick_timestamp,
            "feed_status": "LIVE",
            "listener_tick_id": listener_tick_id,
            "executor_tick_id": listener_tick_id,
            "listener_sequence": listener_sequence,
            "executor_sequence": executor_sequence,
        })
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()

    def test_active_nqm6_tick_updates_nq_feed_health(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 12, 22, 35, tzinfo=timezone.utc)

        self._post_trade_manager_price("NQM6")
        health = self.manager.get_rithmic_feed_health_for_symbol("NQ")

        self.assertEqual(health["feed_status"], "LIVE")
        self.assertEqual(health["normalized_root_symbol"], "NQ")
        self.assertEqual(health["execution_symbol"], "NQM6")
        self.assertAlmostEqual(health["feed_age_seconds"], 0.0, places=3)
        payload = json.loads(self.feed_health_file.read_text(encoding="utf-8"))
        self.assertIn("NQ", payload["symbols"])
        self.assertIn("NQM6", payload["symbols"])

    def test_active_nq_tick_updates_nqm6_feed_health(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 12, 22, 35, tzinfo=timezone.utc)

        self._post_trade_manager_price("NQ")
        health = self.manager.get_rithmic_feed_health_for_symbol("NQM6")

        self.assertEqual(health["feed_status"], "LIVE")
        self.assertEqual(health["normalized_root_symbol"], "NQ")
        self.assertEqual(health["execution_symbol"], "NQM6")
        self.assertAlmostEqual(health["feed_age_seconds"], 0.0, places=3)

    def test_active_ymm6_tick_updates_ym_feed_health(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 12, 22, 35, tzinfo=timezone.utc)

        self._post_trade_manager_price("YMM6", price=42000.0)
        health = self.manager.get_rithmic_feed_health_for_symbol("YM")

        self.assertEqual(health["feed_status"], "LIVE")
        self.assertEqual(health["normalized_root_symbol"], "YM")
        self.assertEqual(health["execution_symbol"], "YMM6")
        self.assertAlmostEqual(health["feed_age_seconds"], 0.0, places=3)

    def test_timezone_aware_tick_timestamp_does_not_falsely_stale(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 12, 22, 35, tzinfo=timezone.utc)

        self._post_trade_manager_price("NQM6", tick_timestamp="2026-05-04T05:22:35-07:00")
        health = self.manager.get_rithmic_feed_health_for_symbol("NQ")

        self.assertEqual(health["feed_status"], "LIVE")
        self.assertAlmostEqual(health["feed_age_seconds"], 0.0, places=3)

    def test_persisted_stale_snapshot_cannot_override_fresh_live_alias_tick(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 12, 22, 35, tzinfo=timezone.utc)
        stale_timestamp = (FrozenDateTime.current - timedelta(seconds=30)).isoformat()
        live_timestamp = FrozenDateTime.current.isoformat()
        self.feed_health_file.write_text(json.dumps({
            "symbols": {
                "NQ": {
                    "feed_status": "STALE",
                    "feed_age_seconds": 30.0,
                    "feed_quiet_seconds": 2.0,
                    "feed_stale_seconds": 3.0,
                    "feed_disconnected_seconds": 60.0,
                    "last_tick_timestamp_utc": stale_timestamp,
                },
                "NQM6": {
                    "feed_status": "LIVE",
                    "feed_age_seconds": 0.0,
                    "feed_quiet_seconds": 2.0,
                    "feed_stale_seconds": 3.0,
                    "feed_disconnected_seconds": 60.0,
                    "last_tick_timestamp_utc": live_timestamp,
                },
            }
        }), encoding="utf-8")

        health = self.manager.get_rithmic_feed_health_for_symbol("NQ")

        self.assertEqual(health["feed_status"], "LIVE")
        self.assertAlmostEqual(health["feed_age_seconds"], 0.0, places=3)

    def test_background_stale_monitor_cannot_overwrite_fresh_accepted_tick(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 12, 22, 35, tzinfo=timezone.utc)

        self._post_trade_manager_price("NQM6")
        stale_timestamp = (FrozenDateTime.current - timedelta(seconds=30)).isoformat()
        self.manager.save_rithmic_feed_health({
            "symbols": {
                "NQ": {
                    "feed_status": "STALE",
                    "feed_age_seconds": 30.0,
                    "feed_quiet_seconds": 2.0,
                    "feed_stale_seconds": 3.0,
                    "feed_disconnected_seconds": 10.0,
                    "last_tick_timestamp_utc": stale_timestamp,
                },
                "NQM6": {
                    "feed_status": "STALE",
                    "feed_age_seconds": 30.0,
                    "feed_quiet_seconds": 2.0,
                    "feed_stale_seconds": 3.0,
                    "feed_disconnected_seconds": 10.0,
                    "last_tick_timestamp_utc": stale_timestamp,
                },
            }
        })

        health = self.manager.get_rithmic_feed_health_for_symbol("NQ")

        self.assertEqual(health["feed_status"], "LIVE")
        self.assertAlmostEqual(health["feed_age_seconds"], 0.0, places=3)

    def test_stale_only_happens_when_no_accepted_tick_is_inside_threshold(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 12, 22, 35, tzinfo=timezone.utc)
        old_timestamp = (FrozenDateTime.current - timedelta(seconds=11)).isoformat()

        self.feed_health_file.write_text(json.dumps({
            "symbols": {
                "NQM6": {
                    "feed_status": "LIVE",
                    "feed_age_seconds": 11.0,
                    "feed_quiet_seconds": 2.0,
                    "feed_stale_seconds": self.manager.RITHMIC_TM_ACCEPTED_PRICE_FRESH_SECONDS,
                    "feed_disconnected_seconds": self.manager.RITHMIC_TM_ACCEPTED_PRICE_DEAD_SECONDS,
                    "last_tick_timestamp_utc": old_timestamp,
                    "last_bridge_post_timestamp_utc": old_timestamp,
                    "last_successful_executor_price_post_timestamp_utc": old_timestamp,
                    "last_price": 27000.25,
                    "last_price_source": "trade_manager_price_route",
                    "feed_health_source": "trade_manager_price_route",
                }
            }
        }), encoding="utf-8")
        health = self.manager.get_rithmic_feed_health_for_symbol("NQ")

        self.assertEqual(health["feed_status"], "STALE")
        self.assertGreater(health["feed_age_seconds"], self.manager.RITHMIC_TM_ACCEPTED_PRICE_FRESH_SECONDS)

    def test_accepted_price_inside_executor_window_is_quiet_not_stale(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 12, 22, 35, tzinfo=timezone.utc)
        quiet_timestamp = (FrozenDateTime.current - timedelta(seconds=4)).isoformat()

        self._post_trade_manager_price("NQM6", tick_timestamp=quiet_timestamp)
        health = self.manager.get_rithmic_feed_health_for_symbol("NQ")

        self.assertEqual(health["feed_status"], "QUIET")
        self.assertAlmostEqual(health["feed_age_seconds"], 4.0, places=3)

    def test_price_integrity_same_price_ok(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 14, 0, 0, tzinfo=timezone.utc)
        self._post_trade_manager_price("NQM6", price=27000.25)

        integrity = self.manager.build_price_integrity_payload(
            "NQ",
            executor_snapshot=self._executor_snapshot(price=27000.25, age=1.0),
        )

        self.assertEqual(integrity["integrity_status"], "OK")
        self.assertFalse(integrity["blocks_new_entries"])
        self.assertEqual(integrity["price_diff_ticks"], 0.0)

    def test_price_integrity_one_tick_difference_ok(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 14, 0, 0, tzinfo=timezone.utc)
        self._post_trade_manager_price("NQM6", price=27000.25)

        integrity = self.manager.build_price_integrity_payload(
            "NQ",
            executor_snapshot=self._executor_snapshot(price=27000.50, age=1.0),
        )

        self.assertEqual(integrity["integrity_status"], "OK")
        self.assertFalse(integrity["blocks_new_entries"])
        self.assertEqual(integrity["price_diff_ticks"], 1.0)

    def test_price_integrity_two_tick_difference_degraded_no_initial_block(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 14, 0, 0, tzinfo=timezone.utc)
        self._post_trade_manager_price("NQM6", price=27000.25)

        integrity = self.manager.build_price_integrity_payload(
            "NQ",
            executor_snapshot=self._executor_snapshot(price=27000.75, age=1.0),
        )

        self.assertEqual(integrity["integrity_status"], "DEGRADED_PRICE_SYNC")
        self.assertEqual(integrity["executor_price_status"], "DEGRADED")
        self.assertFalse(integrity["blocks_new_entries"])
        self.assertEqual(integrity["price_diff_ticks"], 2.0)

    def test_price_integrity_two_tick_difference_persistent_blocks(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 14, 0, 0, tzinfo=timezone.utc)
        self._post_trade_manager_price("NQM6", price=27000.25)

        first = self.manager.build_price_integrity_payload(
            "NQ",
            executor_snapshot=self._executor_snapshot(price=27000.75, age=1.0),
        )
        second = self.manager.build_price_integrity_payload(
            "NQ",
            executor_snapshot=self._executor_snapshot(price=27000.75, age=1.0),
        )

        self.assertEqual(first["integrity_status"], "DEGRADED_PRICE_SYNC")
        self.assertFalse(first["blocks_new_entries"])
        self.assertEqual(second["integrity_status"], "DEGRADED_PRICE_SYNC")
        self.assertTrue(second["blocks_new_entries"])
        self.assertEqual(second["reason"], "two_tick_price_difference_persistent")

    def test_price_integrity_three_tick_difference_blocks(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 14, 0, 0, tzinfo=timezone.utc)
        self._post_trade_manager_price("NQM6", price=27000.25)

        integrity = self.manager.build_price_integrity_payload(
            "NQ",
            executor_snapshot=self._executor_snapshot(price=27001.00, age=1.0),
        )

        self.assertEqual(integrity["integrity_status"], "PRICE_MISMATCH")
        self.assertEqual(integrity["executor_price_status"], "MISMATCH")
        self.assertTrue(integrity["blocks_new_entries"])
        self.assertEqual(integrity["price_diff_ticks"], 3.0)

    def test_price_integrity_executor_lagging_by_multiple_ticks(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 14, 0, 0, tzinfo=timezone.utc)
        self._post_trade_manager_price(
            "NQM6",
            price=27000.25,
            listener_tick_id="NQM6:TICK:12",
            listener_sequence=12,
            executor_sequence=12,
        )

        integrity = self.manager.build_price_integrity_payload(
            "NQ",
            executor_snapshot=self._executor_snapshot(
                price=26997.75,
                age=1.0,
                listener_tick_id="NQM6:TICK:2",
                listener_sequence=2,
                executor_sequence=2,
            ),
        )

        self.assertEqual(integrity["integrity_status"], "EXECUTOR_LAGGING")
        self.assertEqual(integrity["executor_price_status"], "LAGGING")
        self.assertEqual(integrity["executor_lag_ticks"], 10)
        self.assertTrue(integrity["blocks_new_entries"])

    def test_price_integrity_same_tick_id_different_price_is_mismatch(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 14, 0, 0, tzinfo=timezone.utc)
        self._post_trade_manager_price(
            "NQM6",
            price=27000.25,
            listener_tick_id="NQM6:SAME:1",
            listener_sequence=1,
            executor_sequence=1,
        )

        integrity = self.manager.build_price_integrity_payload(
            "NQ",
            executor_snapshot=self._executor_snapshot(
                price=27000.50,
                age=1.0,
                listener_tick_id="NQM6:SAME:1",
                listener_sequence=1,
                executor_sequence=1,
            ),
        )

        self.assertEqual(integrity["integrity_status"], "PRICE_MISMATCH")
        self.assertEqual(integrity["reason"], "same_tick_id_different_price")
        self.assertTrue(integrity["blocks_new_entries"])

    def test_price_integrity_missing_executor_price_blocks(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 14, 0, 0, tzinfo=timezone.utc)
        self._post_trade_manager_price("NQM6", price=27000.25)

        integrity = self.manager.build_price_integrity_payload(
            "NQ",
            executor_snapshot=self._executor_snapshot(price=None, age=1.0),
        )

        self.assertEqual(integrity["integrity_status"], "MISSING_EXECUTOR_PRICE")
        self.assertTrue(integrity["blocks_new_entries"])

    def test_price_integrity_stale_executor_vs_listener_blocks(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 14, 0, 0, tzinfo=timezone.utc)
        self._post_trade_manager_price("NQM6", price=27000.25)

        integrity = self.manager.build_price_integrity_payload(
            "NQ",
            executor_snapshot=self._executor_snapshot(price=27000.25, age=4.0),
        )

        self.assertEqual(integrity["integrity_status"], "STALE_EXECUTOR")
        self.assertEqual(integrity["executor_price_status"], "STALE")
        self.assertTrue(integrity["blocks_new_entries"])

    def test_price_integrity_alias_mismatch_nq_vs_nqm6_compares(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 14, 0, 0, tzinfo=timezone.utc)
        self._post_trade_manager_price("NQ", price=27000.25)

        integrity = self.manager.build_price_integrity_payload(
            "NQM6",
            executor_snapshot=self._executor_snapshot(price=27000.25, age=1.0, symbol="NQM6"),
        )

        self.assertEqual(integrity["integrity_status"], "OK")
        self.assertEqual(integrity["selected_executor_alias"], "NQM6")
        self.assertFalse(integrity["blocks_new_entries"])

    def test_price_integrity_listener_stale_remains_listener_stale_not_mismatch(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 14, 0, 0, tzinfo=timezone.utc)
        stale_timestamp = (FrozenDateTime.current - timedelta(seconds=20)).isoformat()
        self.feed_health_file.write_text(json.dumps({
            "symbols": {
                "NQM6": {
                    "feed_status": "STALE",
                    "feed_age_seconds": 20.0,
                    "feed_quiet_seconds": 2.0,
                    "feed_stale_seconds": 3.0,
                    "feed_disconnected_seconds": 60.0,
                    "last_tick_timestamp_utc": stale_timestamp,
                    "last_price": 27000.25,
                    "last_price_source": "trade_manager_price_route",
                    "feed_health_source": "trade_manager_price_route",
                }
            }
        }), encoding="utf-8")

        integrity = self.manager.build_price_integrity_payload(
            "NQ",
            executor_snapshot=self._executor_snapshot(price=27010.25, age=1.0),
        )

        self.assertEqual(integrity["listener_feed_status"], "STALE")
        self.assertEqual(integrity["integrity_status"], "FEED_NOT_USABLE")
        self.assertTrue(integrity["blocks_new_entries"])
        self.assertNotEqual(integrity["executor_price_status"], "MISMATCH")

    def test_price_integrity_matching_but_dead_listener_blocks(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 14, 0, 0, tzinfo=timezone.utc)
        dead_timestamp = (FrozenDateTime.current - timedelta(seconds=92)).isoformat()
        self.feed_health_file.write_text(json.dumps({
            "symbols": {
                "NQM6": {
                    "feed_status": "LIVE",
                    "feed_age_seconds": 92.0,
                    "feed_quiet_seconds": 2.0,
                    "feed_stale_seconds": 10.0,
                    "feed_disconnected_seconds": 30.0,
                    "last_tick_timestamp_utc": dead_timestamp,
                    "last_price": 27000.25,
                    "last_price_source": "trade_manager_price_route",
                    "feed_health_source": "trade_manager_price_route",
                }
            }
        }), encoding="utf-8")

        integrity = self.manager.build_price_integrity_payload(
            "NQ",
            executor_snapshot=self._executor_snapshot(price=27000.25, age=92.0),
        )

        self.assertEqual(integrity["listener_feed_status"], "DEAD")
        self.assertNotEqual(integrity["integrity_status"], "OK")
        self.assertEqual(integrity["integrity_status"], "LISTENER_FEED_DEAD")
        self.assertTrue(integrity["blocks_new_entries"])
        self.assertEqual(integrity["reason"], "listener_feed_not_usable:DEAD")

    def test_symbol_feed_health_debug_endpoint_returns_authority_details(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 12, 22, 35, tzinfo=timezone.utc)

        self._post_trade_manager_price("NQM6")
        response = self.manager.app.test_client().get("/debug/feed_health/NQ")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["symbol_requested"], "NQ")
        self.assertEqual(data["final_status"], "LIVE")
        self.assertEqual(data["selected_alias"], "NQ")
        self.assertIn("NQM6", data["alias_group"])
        self.assertEqual(data["selected_last_price"], 27000.25)
        self.assertEqual(data["source"], "trade_manager_price_route")
        self.assertIn("all_alias_records", data)

    def test_fresh_live_price_recovers_old_persisted_dead_snapshot(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 12, 22, 35, tzinfo=timezone.utc)
        dead_timestamp = (FrozenDateTime.current - timedelta(seconds=90)).isoformat()
        self.feed_health_file.write_text(json.dumps({
            "symbols": {
                "NQ": {
                    "feed_status": "DEAD",
                    "feed_age_seconds": 90.0,
                    "feed_quiet_seconds": 2.0,
                    "feed_stale_seconds": 3.0,
                    "feed_disconnected_seconds": 10.0,
                    "last_tick_timestamp_utc": dead_timestamp,
                },
                "NQM6": {
                    "feed_status": "DEAD",
                    "feed_age_seconds": 90.0,
                    "feed_quiet_seconds": 2.0,
                    "feed_stale_seconds": 3.0,
                    "feed_disconnected_seconds": 10.0,
                    "last_tick_timestamp_utc": dead_timestamp,
                },
            }
        }), encoding="utf-8")

        self._post_trade_manager_price("NQM6")
        health = self.manager.get_rithmic_feed_health_for_symbol("NQ")

        self.assertEqual(health["feed_status"], "LIVE")
        self.assertAlmostEqual(health["feed_age_seconds"], 0.0, places=3)

    def test_debug_feed_health_recomputes_age_on_each_call(self):
        self._write_feed_health()

        FrozenDateTime.current = datetime(2026, 5, 4, 5, 22, 36, tzinfo=timezone.utc)
        first = self.manager.build_rithmic_feed_health_payload()
        FrozenDateTime.current = datetime(2026, 5, 4, 5, 22, 40, tzinfo=timezone.utc)
        second = self.manager.build_rithmic_feed_health_payload()

        first_age = first["symbols"]["NQM6"]["feed_age_seconds"]
        second_age = second["symbols"]["NQM6"]["feed_age_seconds"]
        self.assertAlmostEqual(first_age, 3.0, places=3)
        self.assertAlmostEqual(second_age, 7.0, places=3)
        self.assertGreater(second_age, first_age)

    def test_debug_feed_health_decays_status_from_timestamp_not_cached_status(self):
        self._write_feed_health()

        FrozenDateTime.current = datetime(2026, 5, 4, 5, 22, 34, tzinfo=timezone.utc)
        recent = self.manager.build_rithmic_feed_health_payload()
        FrozenDateTime.current = datetime(2026, 5, 4, 5, 22, 37, tzinfo=timezone.utc)
        stale = self.manager.build_rithmic_feed_health_payload()
        FrozenDateTime.current = datetime(2026, 5, 4, 5, 22, 45, tzinfo=timezone.utc)
        dead = self.manager.build_rithmic_feed_health_payload()

        self.assertEqual(recent["symbols"]["NQM6"]["feed_status"], "LIVE")
        self.assertEqual(stale["symbols"]["NQM6"]["feed_status"], "STALE")
        self.assertEqual(dead["symbols"]["NQM6"]["feed_status"], "DEAD")

    def test_symbol_feed_health_lookup_uses_dynamic_recompute(self):
        self._write_feed_health()

        FrozenDateTime.current = datetime(2026, 5, 4, 5, 22, 45, tzinfo=timezone.utc)
        health = self.manager.get_rithmic_feed_health_for_symbol("NQ")

        self.assertEqual(health["feed_status"], "DEAD")
        self.assertAlmostEqual(health["feed_age_seconds"], 12.0, places=3)

    def test_execution_price_retry_accepts_non_authoritative_executor_listener_status(self):
        self._write_live_feed_health()

        price, price_at = self.manager.get_fresh_execution_price_with_retry(
            "NQM6",
            lambda: self._executor_snapshot(price=27000.25, age=1.0),
            max_attempts=1,
            delay_seconds=0,
        )

        self.assertEqual(price, 27000.25)
        self.assertIsNotNone(price_at)

    def test_price_lifecycle_accepts_live_feed(self):
        trade = self._run_price_update_with_feed_status("LIVE", price=27010.0)

        self.assertEqual(trade["last_price"], 27010.0)
        self.assertEqual(self.manager.FAILURE_STATE["qa_critical_count"], 0)

    def test_price_lifecycle_accepts_quiet_feed_without_qa_critical(self):
        trade = self._run_price_update_with_feed_status("QUIET", price=27011.0)

        self.assertEqual(trade["last_price"], 27011.0)
        self.assertEqual(self.manager.FAILURE_STATE["qa_critical_count"], 0)

    def test_preopen_stale_feed_with_fresh_sane_price_is_accepted(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 13, 10, 0, tzinfo=timezone.utc)
        trade = self._run_price_update_with_feed_status(
            "STALE",
            price=27012.0,
            age_seconds=60,
            disconnected_seconds=300,
        )

        self.assertEqual(trade["last_price"], 27012.0)
        self.assertEqual(self.manager.FAILURE_STATE["qa_critical_count"], 0)

    def test_preopen_stale_feed_older_than_120_seconds_is_rejected(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 13, 10, 0, tzinfo=timezone.utc)
        trade = self._run_price_update_with_feed_status(
            "STALE",
            price=27012.0,
            age_seconds=121,
            disconnected_seconds=300,
        )

        self.assertNotIn("last_price", trade)
        self.assertEqual(self.manager.FAILURE_STATE["qa_critical_count"], 0)

    def test_preopen_dead_feed_is_rejected(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 13, 10, 0, tzinfo=timezone.utc)
        trade = self._run_price_update_with_feed_status(
            "DEAD",
            price=27013.0,
            age_seconds=301,
            disconnected_seconds=300,
        )

        self.assertNotIn("last_price", trade)
        self.assertEqual(self.manager.FAILURE_STATE["qa_critical_count"], 1)

    def test_preopen_invalid_feed_is_rejected(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 13, 10, 0, tzinfo=timezone.utc)
        trade = self._run_price_update_with_feed_status("INVALID", price=27014.0)

        self.assertNotIn("last_price", trade)
        self.assertEqual(self.manager.FAILURE_STATE["qa_critical_count"], 1)

    def test_regular_session_stale_feed_is_still_rejected(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 21, 0, 0, tzinfo=timezone.utc)
        trade = self._run_price_update_with_feed_status(
            "STALE",
            price=27012.0,
            age_seconds=60,
            disconnected_seconds=300,
        )

        self.assertNotIn("last_price", trade)
        self.assertEqual(self.manager.FAILURE_STATE["qa_critical_count"], 0)

    def test_absurd_lifecycle_price_jump_is_rejected(self):
        FrozenDateTime.current = datetime(2026, 5, 4, 13, 10, 0, tzinfo=timezone.utc)
        trade = self._run_price_update_with_feed_status(
            "STALE",
            price=100000.0,
            age_seconds=60,
            disconnected_seconds=300,
        )

        self.assertNotIn("last_price", trade)
        self.assertEqual(self.manager.FAILURE_STATE["qa_critical_count"], 0)

    def test_price_lifecycle_rejects_first_stale_feed_without_qa_critical(self):
        trade = self._run_price_update_with_feed_status("STALE", price=27012.0)

        self.assertNotIn("last_price", trade)
        self.assertEqual(self.manager.FAILURE_STATE["qa_critical_count"], 0)

    def test_price_lifecycle_repeated_stale_feed_escalates_qa_critical(self):
        first_trade = self._run_price_update_with_feed_status("STALE", price=27012.0)
        second_trade = self._run_price_update_with_feed_status("STALE", price=27012.5)

        self.assertNotIn("last_price", first_trade)
        self.assertNotIn("last_price", second_trade)
        self.assertEqual(self.manager.FAILURE_STATE["qa_critical_count"], 1)

    def test_price_lifecycle_rejects_dead_feed_and_escalates_qa_critical(self):
        trade = self._run_price_update_with_feed_status("DEAD", price=27013.0)

        self.assertNotIn("last_price", trade)
        self.assertEqual(self.manager.FAILURE_STATE["qa_critical_count"], 1)

    def test_price_lifecycle_rejects_invalid_feed_and_escalates_qa_critical(self):
        trade = self._run_price_update_with_feed_status("INVALID", price=27014.0)

        self.assertNotIn("last_price", trade)
        self.assertEqual(self.manager.FAILURE_STATE["qa_critical_count"], 1)

    def test_submit_trade_reaches_executor_fill_when_feed_health_live_and_snapshot_listener_non_authoritative(self):
        self._write_live_feed_health()
        self._write_entry_atr()
        calls = []

        self.manager.fetch_executor_snapshot = lambda: self._executor_snapshot(price=27000.25, age=1.0)
        self.manager.place_entry_order = lambda **kwargs: calls.append(("submit_entry", kwargs)) or {
            "ok": True,
            "broker_order_id": "ENTRY-1",
            "fill_price": 27000.25,
            "fill_price_source": "executor_actual_fill",
            "order": {
                "order_id": "ENTRY-1",
                "status": "filled",
                "filled_price": 27000.25,
            },
        }
        self.manager.place_stop_order = lambda **kwargs: {
            "ok": True,
            "broker_order_id": "STOP-1",
        }
        self.manager.place_limit_order = lambda **kwargs: {
            "ok": True,
            "broker_order_id": "LIMIT-1",
        }

        trade = self.manager.submit_trade({
            "event": "enter_trade",
            "symbol": "NQM6",
            "direction": "long",
            "position_size": 2,
        })

        self.assertEqual(calls[0][0], "submit_entry")
        self.assertEqual(trade["entry_price"], 27000.25)
        self.assertEqual(trade["fill_price_source"], "executor_actual_fill")
        self.assertEqual(trade["status"], "active")

    def test_execution_price_retry_rejects_missing_or_stale_executor_price(self):
        missing_price, missing_price_at = self.manager.get_fresh_execution_price_with_retry(
            "NQM6",
            lambda: {"NQM6": {
                "last_price": None,
                "last_price_at": FrozenDateTime.current.isoformat(),
                "last_tick_age_seconds": 1.0,
                "listener_last_tick_max_age_seconds": 5.0,
                "listener_status": "non_authoritative",
            }},
            max_attempts=1,
            delay_seconds=0,
        )
        stale_price, stale_price_at = self.manager.get_fresh_execution_price_with_retry(
            "NQM6",
            lambda: self._executor_snapshot(price=27000.25, age=10.0),
            max_attempts=1,
            delay_seconds=0,
        )

        self.assertIsNone(missing_price)
        self.assertIsNone(missing_price_at)
        self.assertIsNone(stale_price)
        self.assertIsNone(stale_price_at)


if __name__ == "__main__":
    unittest.main()
