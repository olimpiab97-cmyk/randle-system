import importlib.util
import os
import sys
import tempfile
import unittest
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent


class ExecutorLimitRegressionTests(unittest.TestCase):
    def setUp(self):
        sys.dont_write_bytecode = True
        self.env_patcher = patch.dict(os.environ, {}, clear=False)
        self.env_patcher.start()
        for key in (
            "RANDLE_EXECUTION_MODE",
            "RANDLE_ALLOW_LIVE_TRADING",
            "RANDLE_APPROVED_ACCOUNT_SUBSTRING",
            "RANDLE_MAX_ORDER_QTY",
            "RANDLE_MAX_POSITION_QTY",
        ):
            os.environ.pop(key, None)
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.executor = self._load_executor()
        self.executor.EXECUTOR_STATE_FILE = self.tmp_path / "executor_state.json"
        self.executor.TRADE_MANAGER_PERSISTENCE_FILE = self.tmp_path / "persistence_state.json"
        self.executor.DATA_DIR = self.tmp_path
        self.executor.ORDERS.clear()
        self.executor.POSITIONS.clear()
        self.executor.LAST_PRICES.clear()
        self.executor.LAST_PRICE_TIMESTAMPS.clear()
        self.executor.CURRENT_1M_BARS.clear()
        self.executor.COMPLETED_1M_BARS.clear()
        self.executor.EXECUTOR_STATE_LOADED = True
        self.executor.EXECUTOR_STATE_SAVED_AT = None
        self.executor.WATCHDOG_LAST_VALID_TICK_TIMESTAMP = None
        self.executor.WATCHDOG_LAST_VALID_TICK_SYMBOL = None
        self.executor.WATCHDOG_STATUS = "STALE"
        self.executor.AUTO_RESTART_ENABLED = False
        self.executor.LISTENER_AUTO_RESTART_EXECUTION_ENABLED = False
        self.executor.LAST_RESTART_ATTEMPT_TIMESTAMP = None
        self.executor.log = lambda msg: None

    def tearDown(self):
        self.tmp.cleanup()
        self.env_patcher.stop()

    def _load_executor(self):
        spec = importlib.util.spec_from_file_location("executor_limit_regression", ROOT / "executor.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _price_payload(self, *, symbol="NQM6", price=27000.25, tick_timestamp_utc=None, feed_status="LIVE"):
        if tick_timestamp_utc is None:
            tick_timestamp_utc = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
        return {
            "symbol": symbol,
            "price": price,
            "tick_timestamp_utc": tick_timestamp_utc,
            "feed_status": feed_status,
        }

    def _submit_limit_payload(self, **overrides):
        payload = {
            "action": "submit_limit",
            "trade_id": "T-SAFETY",
            "symbol": "NQM6",
            "limit_price": 26740.0,
            "qty": 1,
        }
        payload.update(overrides)
        return payload

    def _submit_entry_payload(self, **overrides):
        payload = {
            "action": "submit_entry",
            "trade_id": "T-RISK-CAP",
            "symbol": "NQM6",
            "direction": "long",
            "qty": 1,
        }
        payload.update(overrides)
        return payload

    def _assert_order_risk_cap_rejected(self, response, reason):
        data = response.get_json()
        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "order_risk_cap_rejected")
        self.assertEqual(data["reason"], reason)

    def test_order_risk_cap_qty_above_max_order_rejects(self):
        os.environ["RANDLE_MAX_ORDER_QTY"] = "1"

        response = self.executor.app.test_client().post(
            "/execute",
            json=self._submit_limit_payload(qty=2),
        )

        self._assert_order_risk_cap_rejected(response, "max_order_qty_exceeded")
        self.assertEqual(self.executor.ORDERS, {})

    def test_order_risk_cap_missing_and_invalid_qty_reject(self):
        missing_qty = self._submit_limit_payload()
        missing_qty.pop("qty")
        missing_response = self.executor.app.test_client().post(
            "/execute",
            json=missing_qty,
        )
        self._assert_order_risk_cap_rejected(missing_response, "missing_qty")

        invalid_response = self.executor.app.test_client().post(
            "/execute",
            json=self._submit_limit_payload(qty="not-a-number"),
        )
        self._assert_order_risk_cap_rejected(invalid_response, "invalid_qty")

        zero_response = self.executor.app.test_client().post(
            "/execute",
            json=self._submit_limit_payload(qty=0),
        )
        self._assert_order_risk_cap_rejected(zero_response, "qty_must_be_positive")
        self.assertEqual(self.executor.ORDERS, {})

    def test_order_risk_cap_projected_position_above_max_rejects(self):
        os.environ["RANDLE_MAX_POSITION_QTY"] = "2"
        self.executor.POSITIONS["NQM6"] = {
            "qty": 2.0,
            "avg_entry_price": 27000.0,
        }

        response = self.executor.app.test_client().post(
            "/execute",
            json=self._submit_entry_payload(direction="long", qty=1),
        )

        self._assert_order_risk_cap_rejected(response, "max_position_qty_exceeded")
        self.assertEqual(self.executor.POSITIONS["NQM6"]["qty"], 2.0)
        self.assertEqual(self.executor.ORDERS, {})

    def test_order_risk_cap_valid_qty_within_caps_allows(self):
        os.environ["RANDLE_MAX_ORDER_QTY"] = "2"

        response = self.executor.app.test_client().post(
            "/execute",
            json=self._submit_limit_payload(qty=2),
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(len(self.executor.ORDERS), 1)

    def test_order_risk_cap_rejection_does_not_create_order_or_mutate_positions(self):
        os.environ["RANDLE_MAX_ORDER_QTY"] = "1"
        self.executor.POSITIONS["NQM6"] = {
            "qty": 1.0,
            "avg_entry_price": 27000.0,
        }
        before_positions = json.loads(json.dumps(self.executor.POSITIONS))

        response = self.executor.app.test_client().post(
            "/execute",
            json=self._submit_entry_payload(qty=2),
        )

        self._assert_order_risk_cap_rejected(response, "max_order_qty_exceeded")
        self.assertEqual(self.executor.ORDERS, {})
        self.assertEqual(self.executor.POSITIONS, before_positions)

    def test_order_risk_cap_unknown_symbol_rejects(self):
        response = self.executor.app.test_client().post(
            "/execute",
            json=self._submit_limit_payload(symbol="ESM6"),
        )

        self._assert_order_risk_cap_rejected(response, "unknown_symbol")
        self.assertEqual(self.executor.ORDERS, {})

    def test_execution_safety_default_missing_env_allows_paper_execution(self):
        response = self.executor.app.test_client().post(
            "/execute",
            json=self._submit_limit_payload(),
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(len(self.executor.ORDERS), 1)

    def test_execution_safety_paper_mode_allows(self):
        os.environ["RANDLE_EXECUTION_MODE"] = "paper"

        response = self.executor.app.test_client().post(
            "/execute",
            json=self._submit_limit_payload(),
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])

    def test_execution_safety_sim_mode_allows(self):
        os.environ["RANDLE_EXECUTION_MODE"] = "sim"

        response = self.executor.app.test_client().post(
            "/execute",
            json=self._submit_limit_payload(),
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])

    def test_execution_safety_live_mode_rejects_unless_explicitly_allowed(self):
        os.environ["RANDLE_EXECUTION_MODE"] = "live"

        rejected = self.executor.app.test_client().post(
            "/execute",
            json=self._submit_limit_payload(),
        )
        rejected_data = rejected.get_json()

        self.assertEqual(rejected.status_code, 409)
        self.assertFalse(rejected_data["ok"])
        self.assertEqual(rejected_data["error"], "execution_safety_rejected")
        self.assertEqual(self.executor.ORDERS, {})

        os.environ["RANDLE_ALLOW_LIVE_TRADING"] = "true"
        allowed = self.executor.app.test_client().post(
            "/execute",
            json=self._submit_limit_payload(trade_id="T-SAFETY-LIVE-ALLOWED"),
        )
        allowed_data = allowed.get_json()

        self.assertEqual(allowed.status_code, 200)
        self.assertTrue(allowed_data["ok"])
        self.assertEqual(len(self.executor.ORDERS), 1)

    def test_execution_safety_approved_account_substring_rejects_mismatch(self):
        os.environ["RANDLE_EXECUTION_MODE"] = "paper"
        os.environ["RANDLE_APPROVED_ACCOUNT_SUBSTRING"] = "APPROVED-PAPER"

        response = self.executor.app.test_client().post(
            "/execute",
            json=self._submit_limit_payload(account_id="PAPER-UNAPPROVED"),
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "execution_safety_rejected")
        self.assertEqual(data["reason"], "account_missing_approved_substring")
        self.assertTrue(data["context"]["account_present"])
        self.assertNotIn("PAPER-UNAPPROVED", json.dumps(data))
        self.assertEqual(self.executor.ORDERS, {})

    def test_execution_safety_rejection_does_not_create_order_or_mutate_state(self):
        os.environ["RANDLE_EXECUTION_MODE"] = "live"
        self.executor.POSITIONS["NQM6"] = {
            "qty": 1.0,
            "avg_entry_price": 27000.0,
        }
        before_orders = dict(self.executor.ORDERS)
        before_positions = json.loads(json.dumps(self.executor.POSITIONS))

        response = self.executor.app.test_client().post(
            "/execute",
            json=self._submit_limit_payload(),
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "execution_safety_rejected")
        self.assertEqual(self.executor.ORDERS, before_orders)
        self.assertEqual(self.executor.POSITIONS, before_positions)

    def _seed_trade_with_limit_and_stop(
        self,
        *,
        trade_id,
        position_qty,
        avg_entry_price,
        limit_price,
        stop_price,
        stop_tag=None,
    ):
        oco_group = f"OCO-{trade_id}-PROTECTIVE"
        self.executor.POSITIONS["NQM6"] = {
            "qty": float(position_qty),
            "avg_entry_price": float(avg_entry_price),
        }
        self.executor.ORDERS[f"LIMIT-{trade_id}"] = {
            "order_id": f"LIMIT-{trade_id}",
            "trade_id": trade_id,
            "type": "limit",
            "symbol": "NQM6",
            "limit_price": float(limit_price),
            "qty": 1.0,
            "status": "active",
            "tag": "tp1",
            "oco_group": oco_group,
            "oco_role": "tp1_limit",
        }
        self.executor.ORDERS[f"STOP-{trade_id}"] = {
            "order_id": f"STOP-{trade_id}",
            "trade_id": trade_id,
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": float(stop_price),
            "qty": abs(float(position_qty)),
            "status": "active",
            "tag": stop_tag,
            "oco_group": oco_group,
            "oco_role": "protective_stop",
        }

    def _write_tradingview_atr_state(self, records):
        payload = {
            "system": {
                "version": "v1",
                "engine_status": "running",
                "last_update_at": datetime.now().isoformat(),
            },
            "trades": {},
            "orders": {},
            "tradingview_atr": records,
            "risk_state": {},
            "event_log": [],
            "failure_state": {},
        }
        self.executor.TRADE_MANAGER_PERSISTENCE_FILE.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def _seed_completed_bars(self, symbol, closes, *, start=None):
        if start is None:
            start = datetime(2026, 4, 23, 9, 30, 0)
        bars = []
        for index, close in enumerate(closes):
            close = float(close)
            bars.append({
                "bar_timestamp": start + timedelta(minutes=index),
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
            })
        self.executor.COMPLETED_1M_BARS[symbol] = bars

    def _seed_last_price_and_current_bar(
        self,
        symbol,
        *,
        price,
        timestamp=None,
        bar_open=None,
        bar_high=None,
        bar_low=None,
        bar_close=None,
        bar_timestamp=None,
    ):
        if timestamp is None:
            timestamp = datetime.now()
        if bar_timestamp is None:
            bar_timestamp = datetime.now()
        self.executor.LAST_PRICES[symbol] = float(price)
        self.executor.LAST_PRICE_TIMESTAMPS[symbol] = timestamp.isoformat()
        self.executor.CURRENT_1M_BARS[symbol] = {
            "bar_timestamp": bar_timestamp,
            "open": float(price if bar_open is None else bar_open),
            "high": float(price if bar_high is None else bar_high),
            "low": float(price if bar_low is None else bar_low),
            "close": float(price if bar_close is None else bar_close),
        }
        watchdog_timestamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
        self.executor.WATCHDOG_LAST_VALID_TICK_TIMESTAMP = watchdog_timestamp
        self.executor.WATCHDOG_LAST_VALID_TICK_SYMBOL = symbol
        self.executor.WATCHDOG_STATUS = "LIVE"

    def _assert_tp1_limit_fill(self, response, *, trade_id, expected_position_qty):
        data = response.get_json()
        limit_id = f"LIMIT-{trade_id}"
        stop_id = f"STOP-{trade_id}"

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["limit_fills"]), 1)
        self.assertEqual(data["limit_fills"][0]["limit_order_id"], limit_id)
        self.assertEqual(self.executor.ORDERS[limit_id]["status"], "closed")
        self.assertEqual(self.executor.ORDERS[limit_id]["closed_reason"], "limit_triggered")
        self.assertEqual(self.executor.POSITIONS["NQM6"]["qty"], expected_position_qty)
        self.assertEqual(self.executor.ORDERS[stop_id]["status"], "active")
        self.assertEqual(self.executor.ORDERS[stop_id]["qty"], abs(expected_position_qty))
        self.assertIsNone(self.executor.ORDERS[stop_id].get("oco_group"))
        self.assertEqual(self.executor.ORDERS[stop_id].get("oco_parent_group"), f"OCO-{trade_id}-PROTECTIVE")
        self.assertEqual(self.executor.ORDERS[stop_id].get("oco_role"), "runner_stop")

    def test_closed_limit_for_same_trade_does_not_block_new_limit(self):
        trade_id = "T-4bcb7c2f"
        old_limit_id = "LIMIT-a1af6b8a"
        self.executor.ORDERS[old_limit_id] = {
            "order_id": old_limit_id,
            "trade_id": trade_id,
            "type": "limit",
            "tag": None,
            "symbol": "NQM6",
            "limit_price": 26748.0,
            "qty": 1.0,
            "status": "closed",
            "created_at": "2026-04-21T06:45:47.728257",
            "closed_at": "2026-04-21T06:53:53.909426",
        }

        self.assertEqual(self.executor.active_orders_for_trade(trade_id, "limit"), [])

        client = self.executor.app.test_client()
        response = client.post("/execute", json={
            "action": "submit_limit",
            "trade_id": trade_id,
            "symbol": "NQM6",
            "limit_price": 26740.0,
            "qty": 1,
            "tag": "tp1",
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertNotEqual(data["broker_order_id"], old_limit_id)
        self.assertEqual(data["order"]["status"], "active")
        self.assertEqual(self.executor.ORDERS[old_limit_id]["status"], "closed")

        active_limits = self.executor.active_orders_for_trade(trade_id, "limit")
        self.assertEqual(len(active_limits), 1)
        self.assertEqual(active_limits[0]["order_id"], data["broker_order_id"])

    def test_price_update_triggers_short_stop_when_price_is_above_stop(self):
        trade_id = "T-stop-short"
        self.executor.POSITIONS["NQM6"] = {
            "qty": -2.0,
            "avg_entry_price": 26975.75,
        }
        self.executor.ORDERS["STOP-short"] = {
            "order_id": "STOP-short",
            "trade_id": trade_id,
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 26975.75,
            "qty": 2.0,
            "status": "active",
        }
        self.executor.ORDERS["LIMIT-short"] = {
            "order_id": "LIMIT-short",
            "trade_id": trade_id,
            "type": "limit",
            "symbol": "NQM6",
            "limit_price": 26959.75,
            "qty": 1.0,
            "status": "active",
        }

        client = self.executor.app.test_client()
        response = client.post("/price", json=self._price_payload(
            symbol="NQM6",
            price=26996.75,
        ))
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["stop_fills"]), 1)
        self.assertEqual(data["stop_fills"][0]["stop_order_id"], "STOP-short")
        self.assertEqual(self.executor.ORDERS["STOP-short"]["status"], "closed")
        self.assertEqual(self.executor.ORDERS["STOP-short"]["filled_price"], 26975.75)
        self.assertEqual(self.executor.ORDERS["STOP-short"]["fill_trigger_price"], 26996.75)
        self.assertEqual(self.executor.ORDERS["LIMIT-short"]["status"], "closed")
        self.assertEqual(self.executor.POSITIONS["NQM6"]["qty"], 0.0)

    def test_oco_stop_fill_cancels_tp1_limit_peer(self):
        trade_id = "T-oco-stop-first"
        oco_group = f"OCO-{trade_id}-PROTECTIVE"
        self.executor.POSITIONS["NQM6"] = {
            "qty": -2.0,
            "avg_entry_price": 26975.75,
        }
        self.executor.ORDERS["STOP-oco"] = {
            "order_id": "STOP-oco",
            "trade_id": trade_id,
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 26980.0,
            "qty": 2.0,
            "status": "active",
            "oco_group": oco_group,
            "oco_role": "protective_stop",
        }
        self.executor.ORDERS["LIMIT-oco"] = {
            "order_id": "LIMIT-oco",
            "trade_id": trade_id,
            "type": "limit",
            "symbol": "NQM6",
            "limit_price": 26960.0,
            "qty": 1.0,
            "status": "active",
            "tag": "tp1",
            "oco_group": oco_group,
            "oco_role": "tp1_limit",
        }

        response = self.executor.app.test_client().post("/price", json=self._price_payload(
            symbol="NQM6",
            price=26981.0,
        ))
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["stop_fills"]), 1)
        self.assertEqual(self.executor.ORDERS["STOP-oco"]["status"], "closed")
        self.assertEqual(self.executor.ORDERS["LIMIT-oco"]["status"], "cancelled")
        self.assertEqual(self.executor.ORDERS["LIMIT-oco"]["closed_reason"], "oco_cancel_after_stop_fill")
        self.assertEqual(self.executor.ORDERS["LIMIT-oco"]["oco_cancelled_by"], "STOP-oco")
        self.assertEqual(self.executor.active_orders_for_trade(trade_id, "limit"), [])

    def test_submit_stop_immediately_triggers_when_latest_price_already_beyond_short_stop(self):
        trade_id = "T-immediate-short"
        self.executor.LAST_PRICES["NQM6"] = 26996.75
        self.executor.POSITIONS["NQM6"] = {
            "qty": -2.0,
            "avg_entry_price": 26975.75,
        }

        client = self.executor.app.test_client()
        response = client.post("/execute", json={
            "action": "submit_stop",
            "trade_id": trade_id,
            "symbol": "NQM6",
            "stop_price": 26975.75,
            "qty": 2,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["stop_fills"]), 1)
        self.assertEqual(data["order"]["status"], "closed")
        self.assertEqual(data["order"]["filled_price"], 26975.75)
        self.assertEqual(data["order"]["fill_trigger_price"], 26996.75)
        self.assertEqual(self.executor.POSITIONS["NQM6"]["qty"], 0.0)

    def test_sync_snapshot_clears_orphan_working_orders_when_symbol_flat(self):
        self.executor.POSITIONS["NQM6"] = {
            "qty": 0.0,
            "avg_entry_price": 0.0,
        }
        self.executor.ORDERS["STOP-orphan"] = {
            "order_id": "STOP-orphan",
            "trade_id": "T-orphan",
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 27137.0,
            "qty": 1.0,
            "status": "active",
        }
        self.executor.ORDERS["LIMIT-orphan"] = {
            "order_id": "LIMIT-orphan",
            "trade_id": "T-orphan",
            "type": "limit",
            "symbol": "NQM6",
            "limit_price": 27109.0,
            "qty": 1.0,
            "status": "active",
        }

        client = self.executor.app.test_client()
        response = client.get("/sync_snapshot")
        data = response.get_json()
        snapshot = data["symbols"]["NQM6"]

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertTrue(snapshot["is_flat"])
        self.assertEqual(snapshot["position_qty"], 0.0)
        self.assertFalse(snapshot["has_stop"])
        self.assertEqual(snapshot["working_orders"], [])
        self.assertEqual(self.executor.ORDERS["STOP-orphan"]["status"], "cancelled")
        self.assertEqual(self.executor.ORDERS["LIMIT-orphan"]["status"], "cancelled")
        self.assertEqual(
            self.executor.ORDERS["STOP-orphan"]["closed_reason"],
            "cleared_before_flat_snapshot",
        )

    def test_price_update_for_ym_does_not_modify_nq_orders(self):
        self.executor.POSITIONS["NQM6"] = {
            "qty": -1.0,
            "avg_entry_price": 100.0,
        }
        self.executor.POSITIONS["RTYM6"] = {
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
        self.executor.ORDERS["STOP-RTY"] = {
            "order_id": "STOP-RTY",
            "trade_id": "T-RTY",
            "type": "stop",
            "symbol": "RTYM6",
            "stop_price": 42010.0,
            "qty": 1.0,
            "status": "active",
        }

        response = self.executor.app.test_client().post("/price", json=self._price_payload(
            symbol="RTYM6",
            price=42011.0,
        ))
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["stop_fills"]), 1)
        self.assertEqual(data["stop_fills"][0]["stop_order_id"], "STOP-RTY")
        self.assertEqual(self.executor.ORDERS["STOP-RTY"]["status"], "closed")
        self.assertEqual(self.executor.ORDERS["STOP-NQ"]["status"], "active")
        self.assertEqual(self.executor.POSITIONS["NQM6"]["qty"], -1.0)

    def test_price_update_records_listener_timestamp_without_claiming_authoritative_listener_status(self):
        response = self.executor.app.test_client().post("/price", json=self._price_payload(
            symbol="NQM6",
            price=27000.25,
        ))
        self.assertEqual(response.status_code, 200)
        self.assertIn("NQM6", self.executor.LAST_PRICE_TIMESTAMPS)

        snapshot_response = self.executor.app.test_client().get("/sync_snapshot")
        snapshot = snapshot_response.get_json()["symbols"]["NQM6"]

        self.assertEqual(snapshot["last_price"], 27000.25)
        self.assertIsNotNone(snapshot["last_price_at"])
        self.assertIsNotNone(snapshot["last_tick_age_seconds"])
        self.assertIsNotNone(snapshot["current_1m_bar"])
        self.assertIsNotNone(snapshot["current_1m_bar_timestamp"])
        self.assertIsNotNone(snapshot["current_1m_bar_age_seconds"])
        self.assertEqual(snapshot["listener_status"], "non_authoritative")
        self.assertEqual(
            snapshot["listener_status_reason"],
            "executor_snapshot_is_not_feed_authority",
        )
        self.assertEqual(snapshot["executor_listener_status_copy"], "fresh")
        self.assertIsNone(snapshot["executor_listener_status_reason_copy"])

    def test_price_update_rejects_stale_forwarded_tick_before_fill_evaluation(self):
        stale_timestamp = (
            datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)
        ).isoformat() + "Z"
        self._seed_trade_with_limit_and_stop(
            trade_id="stale-tick",
            position_qty=-1,
            avg_entry_price=27000.0,
            limit_price=26990.0,
            stop_price=27010.0,
        )

        response = self.executor.app.test_client().post("/price", json={
            "symbol": "NQM6",
            "price": 27011.0,
            "tick_timestamp_utc": stale_timestamp,
            "feed_status": "LIVE",
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(data["error"], "stale_or_invalid_market_data")
        self.assertNotIn("NQM6", self.executor.LAST_PRICES)
        self.assertEqual(self.executor.ORDERS["STOP-stale-tick"]["status"], "active")

    def test_price_update_rejects_non_live_tick_before_state_mutation(self):
        self._seed_trade_with_limit_and_stop(
            trade_id="non-live-tick",
            position_qty=-1,
            avg_entry_price=27000.0,
            limit_price=26990.0,
            stop_price=27010.0,
        )

        response = self.executor.app.test_client().post("/price", json=self._price_payload(
            price=27011.0,
            feed_status="STALE",
        ))
        data = response.get_json()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(data["reason"], "feed_status_not_live")
        self.assertNotIn("NQM6", self.executor.LAST_PRICES)
        self.assertEqual(self.executor.ORDERS["STOP-non-live-tick"]["status"], "active")

    def test_price_update_rejects_missing_timestamp_before_state_mutation(self):
        self._seed_trade_with_limit_and_stop(
            trade_id="missing-ts-tick",
            position_qty=-1,
            avg_entry_price=27000.0,
            limit_price=26990.0,
            stop_price=27010.0,
        )
        payload = self._price_payload(price=27011.0)
        payload.pop("tick_timestamp_utc")

        response = self.executor.app.test_client().post("/price", json=payload)
        data = response.get_json()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(data["reason"], "missing_tick_timestamp_utc")
        self.assertNotIn("NQM6", self.executor.LAST_PRICES)
        self.assertEqual(self.executor.ORDERS["STOP-missing-ts-tick"]["status"], "active")

    def test_price_update_rejects_future_tick_before_state_mutation(self):
        future_timestamp = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            + timedelta(seconds=self.executor.LISTENER_TICK_FUTURE_TOLERANCE_SECONDS + 5)
        ).isoformat() + "Z"
        self._seed_trade_with_limit_and_stop(
            trade_id="future-tick",
            position_qty=-1,
            avg_entry_price=27000.0,
            limit_price=26990.0,
            stop_price=27010.0,
        )

        response = self.executor.app.test_client().post("/price", json=self._price_payload(
            price=27011.0,
            tick_timestamp_utc=future_timestamp,
        ))
        data = response.get_json()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(data["reason"], "future_tick_timestamp_utc")
        self.assertNotIn("NQM6", self.executor.LAST_PRICES)
        self.assertEqual(self.executor.ORDERS["STOP-future-tick"]["status"], "active")

    def test_price_update_rejects_invalid_price_before_state_mutation(self):
        self._seed_trade_with_limit_and_stop(
            trade_id="invalid-price-tick",
            position_qty=-1,
            avg_entry_price=27000.0,
            limit_price=26990.0,
            stop_price=27010.0,
        )

        response = self.executor.app.test_client().post("/price", json=self._price_payload(
            price="NaN",
        ))
        data = response.get_json()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(data["reason"], "invalid_price")
        self.assertNotIn("NQM6", self.executor.LAST_PRICES)
        self.assertEqual(self.executor.ORDERS["STOP-invalid-price-tick"]["status"], "active")

    def test_price_update_accepts_live_tick_and_forwards_metadata_unchanged(self):
        tick_timestamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"

        with patch("requests.post") as post_mock:
            response = self.executor.app.test_client().post("/price", json=self._price_payload(
                symbol="NQM6",
                price=27000.25,
                tick_timestamp_utc=tick_timestamp,
                feed_status="LIVE",
            ))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.executor.LAST_PRICES["NQM6"], 27000.25)
        self.assertEqual(self.executor.LAST_PRICE_TIMESTAMPS["NQM6"], tick_timestamp)
        post_mock.assert_called_once()
        forwarded = post_mock.call_args.kwargs["json"]
        self.assertEqual(forwarded["symbol"], "NQM6")
        self.assertEqual(forwarded["price"], 27000.25)
        self.assertEqual(forwarded["feed_status"], "LIVE")
        self.assertEqual(forwarded["tick_timestamp_utc"], tick_timestamp)

    def test_watchdog_valid_ticks_keep_status_live(self):
        tick_timestamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"

        with patch("requests.post"):
            response = self.executor.app.test_client().post("/price", json=self._price_payload(
                tick_timestamp_utc=tick_timestamp,
            ))
        watchdog = self.executor.app.test_client().get("/debug/watchdog").get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(watchdog["status"], "LIVE")
        self.assertEqual(watchdog["last_valid_tick_timestamp"], tick_timestamp)
        self.assertEqual(watchdog["last_valid_tick_symbol"], "NQM6")
        self.assertLessEqual(
            watchdog["seconds_since_last_valid_tick"],
            self.executor.WATCHDOG_STALE_AFTER_SECONDS,
        )

    def test_watchdog_marks_stale_after_valid_ticks_stop(self):
        old_timestamp = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(seconds=self.executor.WATCHDOG_STALE_AFTER_SECONDS + 1)
        ).isoformat() + "Z"
        messages = []
        self.executor.log = messages.append
        self.executor.WATCHDOG_LAST_VALID_TICK_TIMESTAMP = old_timestamp
        self.executor.WATCHDOG_LAST_VALID_TICK_SYMBOL = "NQM6"
        self.executor.WATCHDOG_STATUS = "LIVE"

        watchdog = self.executor.app.test_client().get("/debug/watchdog").get_json()

        self.assertEqual(watchdog["status"], "STALE")
        self.assertEqual(watchdog["last_valid_tick_timestamp"], old_timestamp)
        self.assertGreater(
            watchdog["seconds_since_last_valid_tick"],
            self.executor.WATCHDOG_STALE_AFTER_SECONDS,
        )
        stale_messages = [msg for msg in messages if msg.startswith("WATCHDOG STALE:")]
        self.assertEqual(len(stale_messages), 1)
        self.assertIn("| last_symbol=NQM6", stale_messages[0])

        self.executor.app.test_client().get("/debug/watchdog")
        self.assertEqual(len([msg for msg in messages if msg.startswith("WATCHDOG STALE:")]), 1)

    def test_watchdog_recovery_tick_returns_to_live(self):
        old_timestamp = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(seconds=self.executor.WATCHDOG_STALE_AFTER_SECONDS + 1)
        ).isoformat() + "Z"
        new_timestamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
        messages = []
        self.executor.log = messages.append
        self.executor.WATCHDOG_LAST_VALID_TICK_TIMESTAMP = old_timestamp
        self.executor.WATCHDOG_LAST_VALID_TICK_SYMBOL = "NQM6"
        self.executor.WATCHDOG_STATUS = "STALE"

        with patch("requests.post"):
            response = self.executor.app.test_client().post("/price", json=self._price_payload(
                tick_timestamp_utc=new_timestamp,
            ))
        watchdog = self.executor.app.test_client().get("/debug/watchdog").get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(watchdog["status"], "LIVE")
        self.assertEqual(watchdog["last_valid_tick_timestamp"], new_timestamp)
        recovery_messages = [msg for msg in messages if msg.startswith("WATCHDOG RECOVERED:")]
        self.assertEqual(recovery_messages, ["WATCHDOG RECOVERED: valid LIVE ticks resumed | symbol=NQM6"])

        with patch("requests.post"):
            self.executor.app.test_client().post("/price", json=self._price_payload())
        recovery_messages = [msg for msg in messages if msg.startswith("WATCHDOG RECOVERED:")]
        self.assertEqual(len(recovery_messages), 1)

    def test_watchdog_alert_endpoint_returns_current_state(self):
        old_timestamp = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(seconds=self.executor.WATCHDOG_STALE_AFTER_SECONDS + 1)
        ).isoformat() + "Z"
        self.executor.WATCHDOG_LAST_VALID_TICK_TIMESTAMP = old_timestamp
        self.executor.WATCHDOG_LAST_VALID_TICK_SYMBOL = "NQM6"
        self.executor.WATCHDOG_STATUS = "LIVE"

        alert = self.executor.app.test_client().get("/debug/watchdog_alert").get_json()

        self.assertEqual(alert["status"], "STALE")
        self.assertEqual(alert["last_valid_tick_timestamp"], old_timestamp)
        self.assertEqual(alert["last_valid_tick_symbol"], "NQM6")
        self.assertGreater(
            alert["seconds_since_last_valid_tick"],
            self.executor.WATCHDOG_STALE_AFTER_SECONDS,
        )
        self.assertTrue(alert["is_stale"])
        self.assertFalse(alert["auto_restart_enabled"])
        self.assertFalse(alert["restart_eligible"])
        self.assertIsNone(alert["seconds_until_restart"])

    def test_watchdog_restart_eligible_when_stale_threshold_exceeded(self):
        old_timestamp = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(seconds=self.executor.AUTO_RESTART_STALE_THRESHOLD_SECONDS + 1)
        ).isoformat() + "Z"
        messages = []
        self.executor.log = messages.append
        self.executor.AUTO_RESTART_ENABLED = True
        self.executor.stop_listener_process = lambda listener: self.fail("stop should not be called")
        self.executor.start_listener_process = lambda: self.fail("start should not be called")
        self.executor.WATCHDOG_LAST_VALID_TICK_TIMESTAMP = old_timestamp
        self.executor.WATCHDOG_LAST_VALID_TICK_SYMBOL = "NQM6"
        self.executor.WATCHDOG_STATUS = "STALE"

        alert = self.executor.app.test_client().get("/debug/watchdog_alert").get_json()

        self.assertTrue(alert["auto_restart_enabled"])
        self.assertTrue(alert["restart_eligible"])
        self.assertEqual(alert["seconds_until_restart"], self.executor.AUTO_RESTART_COOLDOWN_SECONDS)
        self.assertEqual(alert["restart_action"], {"executed": False, "reason": "execution_disabled"})
        self.assertEqual(messages, ["WATCHDOG RESTART SKIPPED: execution disabled"])
        self.assertIsNotNone(self.executor.LAST_RESTART_ATTEMPT_TIMESTAMP)

        self.executor.app.test_client().get("/debug/watchdog_alert")
        self.assertEqual(messages, ["WATCHDOG RESTART SKIPPED: execution disabled"])

    def test_watchdog_restart_eligible_with_no_listener_match(self):
        old_timestamp = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(seconds=self.executor.AUTO_RESTART_STALE_THRESHOLD_SECONDS + 1)
        ).isoformat() + "Z"
        messages = []
        self.executor.log = messages.append
        self.executor.AUTO_RESTART_ENABLED = True
        self.executor.LISTENER_AUTO_RESTART_EXECUTION_ENABLED = True
        self.executor.find_listener_process = lambda: None
        self.executor.WATCHDOG_LAST_VALID_TICK_TIMESTAMP = old_timestamp
        self.executor.WATCHDOG_LAST_VALID_TICK_SYMBOL = "NQM6"
        self.executor.WATCHDOG_STATUS = "STALE"

        alert = self.executor.app.test_client().get("/debug/watchdog_alert").get_json()

        self.assertTrue(alert["restart_eligible"])
        self.assertEqual(alert["restart_action"], {"executed": False, "reason": "listener_not_identified"})
        self.assertEqual(messages, ["WATCHDOG RESTART SKIPPED: listener process not uniquely identified"])

    def test_watchdog_restart_eligible_with_no_listener_match_does_not_stop_or_start(self):
        old_timestamp = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(seconds=self.executor.AUTO_RESTART_STALE_THRESHOLD_SECONDS + 1)
        ).isoformat() + "Z"
        self.executor.AUTO_RESTART_ENABLED = True
        self.executor.LISTENER_AUTO_RESTART_EXECUTION_ENABLED = True
        self.executor.find_listener_process = lambda: None
        self.executor.stop_listener_process = lambda listener: self.fail("stop should not be called")
        self.executor.start_listener_process = lambda: self.fail("start should not be called")
        self.executor.WATCHDOG_LAST_VALID_TICK_TIMESTAMP = old_timestamp
        self.executor.WATCHDOG_LAST_VALID_TICK_SYMBOL = "NQM6"
        self.executor.WATCHDOG_STATUS = "STALE"

        alert = self.executor.app.test_client().get("/debug/watchdog_alert").get_json()

        self.assertEqual(alert["restart_action"], {"executed": False, "reason": "listener_not_identified"})

    def test_watchdog_restart_eligible_with_multiple_listener_matches(self):
        old_timestamp = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(seconds=self.executor.AUTO_RESTART_STALE_THRESHOLD_SECONDS + 1)
        ).isoformat() + "Z"
        messages = []
        original_find_listener_process = self.executor.find_listener_process
        fake_processes = [
            {"pid": 101, "name": "python.exe", "cmdline": ["python", "rithmic_live_listener.py"]},
            {"pid": 202, "name": "python.exe", "cmdline": ["python", "rithmic_live_listener.py"]},
        ]
        self.executor.log = messages.append
        self.executor.AUTO_RESTART_ENABLED = True
        self.executor.LISTENER_AUTO_RESTART_EXECUTION_ENABLED = True
        self.executor.find_listener_process = lambda: original_find_listener_process(fake_processes)
        self.executor.stop_listener_process = lambda listener: self.fail("stop should not be called")
        self.executor.start_listener_process = lambda: self.fail("start should not be called")
        self.executor.WATCHDOG_LAST_VALID_TICK_TIMESTAMP = old_timestamp
        self.executor.WATCHDOG_LAST_VALID_TICK_SYMBOL = "NQM6"
        self.executor.WATCHDOG_STATUS = "STALE"

        alert = self.executor.app.test_client().get("/debug/watchdog_alert").get_json()

        self.assertTrue(alert["restart_eligible"])
        self.assertEqual(alert["restart_action"], {"executed": False, "reason": "listener_not_identified"})
        self.assertEqual(messages, ["WATCHDOG RESTART SKIPPED: listener process not uniquely identified"])

    def test_watchdog_restart_eligible_with_single_listener_match_restarts(self):
        old_timestamp = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(seconds=self.executor.AUTO_RESTART_STALE_THRESHOLD_SECONDS + 1)
        ).isoformat() + "Z"
        messages = []
        calls = []
        listener_process = {
            "pid": 303,
            "command_line": "python rithmic_live_listener.py",
        }
        self.executor.log = messages.append
        self.executor.AUTO_RESTART_ENABLED = True
        self.executor.LISTENER_AUTO_RESTART_EXECUTION_ENABLED = True
        self.executor.find_listener_process = lambda: listener_process
        self.executor.stop_listener_process = lambda process: calls.append(("stop", process)) or {"stopped": True, "pid": process["pid"]}
        self.executor.start_listener_process = lambda: calls.append(("start", self.executor.LISTENER_RESTART_COMMAND, str(self.executor.BASE_DIR))) or {"started": True}
        self.executor.WATCHDOG_LAST_VALID_TICK_TIMESTAMP = old_timestamp
        self.executor.WATCHDOG_LAST_VALID_TICK_SYMBOL = "NQM6"
        self.executor.WATCHDOG_STATUS = "STALE"

        alert = self.executor.app.test_client().get("/debug/watchdog_alert").get_json()

        self.assertTrue(alert["restart_eligible"])
        self.assertEqual(alert["restart_action"], {
            "executed": True,
            "reason": "listener_restarted",
            "stopped_pid": 303,
            "start_result": {"started": True},
        })
        self.assertEqual(calls, [
            ("stop", listener_process),
            ("start", ["python", "rithmic_live_listener.py"], "C:\\Webhook\\RandleSystem"),
        ])
        self.assertEqual(messages, ["WATCHDOG RESTART EXECUTED: stopped_pid=303"])

    def test_watchdog_restart_start_failure_returns_structured_failure(self):
        old_timestamp = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(seconds=self.executor.AUTO_RESTART_STALE_THRESHOLD_SECONDS + 1)
        ).isoformat() + "Z"
        listener_process = {
            "pid": 404,
            "command_line": "python rithmic_live_listener.py",
        }
        self.executor.AUTO_RESTART_ENABLED = True
        self.executor.LISTENER_AUTO_RESTART_EXECUTION_ENABLED = True
        self.executor.find_listener_process = lambda: listener_process
        self.executor.stop_listener_process = lambda process: {"stopped": True, "pid": process["pid"]}
        self.executor.start_listener_process = lambda: {"started": False, "reason": "start_failed_for_test"}
        self.executor.WATCHDOG_LAST_VALID_TICK_TIMESTAMP = old_timestamp
        self.executor.WATCHDOG_LAST_VALID_TICK_SYMBOL = "NQM6"
        self.executor.WATCHDOG_STATUS = "STALE"

        alert = self.executor.app.test_client().get("/debug/watchdog_alert").get_json()

        self.assertEqual(alert["restart_action"], {
            "executed": False,
            "reason": "start_failed",
            "stopped_pid": 404,
            "start_result": {"started": False, "reason": "start_failed_for_test"},
        })

    def test_watchdog_restart_stop_failure_does_not_start(self):
        old_timestamp = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(seconds=self.executor.AUTO_RESTART_STALE_THRESHOLD_SECONDS + 1)
        ).isoformat() + "Z"
        listener_process = {
            "pid": 505,
            "command_line": "python rithmic_live_listener.py",
        }
        self.executor.AUTO_RESTART_ENABLED = True
        self.executor.LISTENER_AUTO_RESTART_EXECUTION_ENABLED = True
        self.executor.find_listener_process = lambda: listener_process
        self.executor.stop_listener_process = lambda process: {"stopped": False, "reason": "stop_failed_for_test"}
        self.executor.start_listener_process = lambda: self.fail("start should not be called after stop failure")
        self.executor.WATCHDOG_LAST_VALID_TICK_TIMESTAMP = old_timestamp
        self.executor.WATCHDOG_LAST_VALID_TICK_SYMBOL = "NQM6"
        self.executor.WATCHDOG_STATUS = "STALE"

        alert = self.executor.app.test_client().get("/debug/watchdog_alert").get_json()

        self.assertEqual(alert["restart_action"], {
            "executed": False,
            "reason": "stop_failed",
            "stopped_pid": 505,
            "stop_result": {"stopped": False, "reason": "stop_failed_for_test"},
        })

    def test_start_listener_process_uses_configured_command_and_project_cwd(self):
        calls = []

        def fake_popen(command, cwd, shell):
            calls.append((command, cwd, shell))

        with patch.object(self.executor.subprocess, "Popen", fake_popen):
            result = self.executor.start_listener_process()

        self.assertEqual(result, {"started": True})
        self.assertEqual(calls, [(["python", "rithmic_live_listener.py"], "C:\\Webhook\\RandleSystem", False)])

    def test_watchdog_restart_not_eligible_below_threshold(self):
        old_timestamp = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(seconds=self.executor.AUTO_RESTART_STALE_THRESHOLD_SECONDS - 1)
        ).isoformat() + "Z"
        self.executor.AUTO_RESTART_ENABLED = True
        self.executor.WATCHDOG_LAST_VALID_TICK_TIMESTAMP = old_timestamp
        self.executor.WATCHDOG_LAST_VALID_TICK_SYMBOL = "NQM6"
        self.executor.WATCHDOG_STATUS = "STALE"

        alert = self.executor.app.test_client().get("/debug/watchdog_alert").get_json()

        self.assertEqual(alert["status"], "STALE")
        self.assertFalse(alert["restart_eligible"])
        self.assertGreater(alert["seconds_until_restart"], 0)
        self.assertIsNone(self.executor.LAST_RESTART_ATTEMPT_TIMESTAMP)

    def test_watchdog_restart_not_eligible_when_cooldown_active(self):
        old_timestamp = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(seconds=self.executor.AUTO_RESTART_STALE_THRESHOLD_SECONDS + 1)
        ).isoformat() + "Z"
        messages = []
        self.executor.log = messages.append
        self.executor.AUTO_RESTART_ENABLED = True
        self.executor.WATCHDOG_LAST_VALID_TICK_TIMESTAMP = old_timestamp
        self.executor.WATCHDOG_LAST_VALID_TICK_SYMBOL = "NQM6"
        self.executor.WATCHDOG_STATUS = "STALE"
        self.executor.LAST_RESTART_ATTEMPT_TIMESTAMP = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(seconds=self.executor.AUTO_RESTART_COOLDOWN_SECONDS - 1)
        )

        alert = self.executor.app.test_client().get("/debug/watchdog_alert").get_json()

        self.assertEqual(alert["status"], "STALE")
        self.assertFalse(alert["restart_eligible"])
        self.assertGreater(alert["seconds_until_restart"], 0)
        self.assertEqual(messages, [])

    def test_watchdog_restart_not_eligible_when_live(self):
        tick_timestamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
        self.executor.AUTO_RESTART_ENABLED = True
        self.executor.WATCHDOG_LAST_VALID_TICK_TIMESTAMP = tick_timestamp
        self.executor.WATCHDOG_LAST_VALID_TICK_SYMBOL = "NQM6"
        self.executor.WATCHDOG_STATUS = "LIVE"

        alert = self.executor.app.test_client().get("/debug/watchdog_alert").get_json()

        self.assertEqual(alert["status"], "LIVE")
        self.assertFalse(alert["restart_eligible"])
        self.assertIsNone(alert["seconds_until_restart"])
        self.assertIsNone(alert["restart_action"])
        self.assertIsNone(self.executor.LAST_RESTART_ATTEMPT_TIMESTAMP)

    def test_watchdog_restart_not_eligible_does_not_call_restart_helper(self):
        tick_timestamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
        self.executor.AUTO_RESTART_ENABLED = True
        self.executor.LISTENER_AUTO_RESTART_EXECUTION_ENABLED = True
        self.executor.execute_listener_restart = lambda: self.fail("restart helper should not be called")
        self.executor.WATCHDOG_LAST_VALID_TICK_TIMESTAMP = tick_timestamp
        self.executor.WATCHDOG_LAST_VALID_TICK_SYMBOL = "NQM6"
        self.executor.WATCHDOG_STATUS = "LIVE"

        alert = self.executor.app.test_client().get("/debug/watchdog_alert").get_json()

        self.assertEqual(alert["status"], "LIVE")
        self.assertFalse(alert["restart_eligible"])
        self.assertIsNone(alert["restart_action"])

    def test_watchdog_rejected_ticks_do_not_reset_timer(self):
        old_timestamp = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(seconds=self.executor.WATCHDOG_STALE_AFTER_SECONDS + 1)
        ).isoformat() + "Z"
        self.executor.WATCHDOG_LAST_VALID_TICK_TIMESTAMP = old_timestamp
        self.executor.WATCHDOG_LAST_VALID_TICK_SYMBOL = "NQM6"
        self.executor.WATCHDOG_STATUS = "STALE"

        response = self.executor.app.test_client().post("/price", json=self._price_payload(
            price=27011.0,
            feed_status="STALE",
        ))
        watchdog = self.executor.app.test_client().get("/debug/watchdog").get_json()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(watchdog["status"], "STALE")
        self.assertEqual(watchdog["last_valid_tick_timestamp"], old_timestamp)
        self.assertEqual(watchdog["last_valid_tick_symbol"], "NQM6")

    def test_submit_entry_rejected_while_watchdog_stale(self):
        self.executor.LAST_PRICES["NQM6"] = 27000.25
        self.executor.LAST_PRICE_TIMESTAMPS["NQM6"] = datetime.now().isoformat()
        self.executor.WATCHDOG_STATUS = "STALE"

        response = self.executor.app.test_client().post("/execute", json={
            "action": "submit_entry",
            "trade_id": "T-WATCHDOG-STALE",
            "symbol": "NQM6",
            "direction": "long",
            "qty": 1,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "watchdog_stale")
        self.assertEqual(data["watchdog"]["status"], "STALE")
        self.assertEqual(self.executor.ORDERS, {})
        self.assertEqual(self.executor.POSITIONS, {})

    def test_submit_entry_allowed_while_watchdog_live(self):
        self._seed_last_price_and_current_bar(
            "NQM6",
            price=27000.25,
            bar_low=26999.75,
            bar_high=27000.50,
            bar_close=27000.25,
        )

        response = self.executor.app.test_client().post("/execute", json={
            "action": "submit_entry",
            "trade_id": "T-WATCHDOG-LIVE",
            "symbol": "NQM6",
            "direction": "long",
            "qty": 1,
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        self.assertEqual(self.executor.POSITIONS["NQM6"]["qty"], 1.0)

    def test_submit_stop_allowed_while_watchdog_stale(self):
        response = self.executor.app.test_client().post("/execute", json={
            "action": "submit_stop",
            "trade_id": "T-PROTECT-STOP",
            "symbol": "NQM6",
            "stop_price": 26990.0,
            "qty": 1,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["order"]["type"], "stop")
        self.assertEqual(data["order"]["status"], "active")

    def test_submit_limit_allowed_while_watchdog_stale(self):
        response = self.executor.app.test_client().post("/execute", json={
            "action": "submit_limit",
            "trade_id": "T-PROTECT-LIMIT",
            "symbol": "NQM6",
            "limit_price": 27010.0,
            "qty": 1,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["order"]["type"], "limit")
        self.assertEqual(data["order"]["status"], "active")

    def test_modify_stop_updates_existing_active_stop_order(self):
        self.executor.POSITIONS["NQM6"] = {
            "qty": -2.0,
            "avg_entry_price": 27020.0,
        }
        self.executor.ORDERS["STOP-MODIFY"] = {
            "order_id": "STOP-MODIFY",
            "trade_id": "T-MODIFY",
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 27010.0,
            "qty": 2.0,
            "status": "active",
            "oco_group": "OCO-T-MODIFY-PROTECTIVE",
            "oco_role": "protective_stop",
            "created_at": datetime.now().isoformat(),
        }
        self.executor.ORDERS["LIMIT-MODIFY"] = {
            "order_id": "LIMIT-MODIFY",
            "trade_id": "T-MODIFY",
            "type": "limit",
            "symbol": "NQM6",
            "limit_price": 26980.0,
            "qty": 1.0,
            "status": "active",
            "tag": "tp1",
            "oco_group": "OCO-T-MODIFY-PROTECTIVE",
            "oco_role": "tp1_limit",
        }

        response = self.executor.app.test_client().post("/execute", json={
            "action": "modify_stop",
            "trade_id": "T-MODIFY",
            "symbol": "NQM6",
            "order_id": "STOP-MODIFY",
            "stop_price": 27000.0,
            "qty": 1,
            "tag": "breakeven",
            "oco_group": "OCO-SHOULD-NOT-REPLACE",
            "oco_role": "wrong_role",
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["broker_order_id"], "STOP-MODIFY")
        self.assertEqual(data["order_id"], "STOP-MODIFY")
        self.assertEqual(data["stop_fills"], [])
        self.assertNotIn("error", data)
        self.assertEqual(self.executor.ORDERS["STOP-MODIFY"]["order_id"], "STOP-MODIFY")
        self.assertEqual(self.executor.ORDERS["STOP-MODIFY"]["trade_id"], "T-MODIFY")
        self.assertEqual(self.executor.ORDERS["STOP-MODIFY"]["status"], "active")
        self.assertEqual(self.executor.ORDERS["STOP-MODIFY"]["stop_price"], 27000.0)
        self.assertEqual(self.executor.ORDERS["STOP-MODIFY"]["qty"], 2.0)
        self.assertEqual(self.executor.ORDERS["STOP-MODIFY"]["tag"], "breakeven")
        self.assertEqual(self.executor.ORDERS["STOP-MODIFY"]["oco_group"], "OCO-T-MODIFY-PROTECTIVE")
        self.assertEqual(self.executor.ORDERS["STOP-MODIFY"]["oco_role"], "protective_stop")
        self.assertTrue(self.executor.ORDERS["STOP-MODIFY"]["modify_history"])
        self.assertEqual(self.executor.ORDERS["LIMIT-MODIFY"]["status"], "active")
        self.assertEqual(self.executor.ORDERS["LIMIT-MODIFY"]["limit_price"], 26980.0)
        self.assertEqual(self.executor.POSITIONS["NQM6"]["qty"], -2.0)
        self.assertFalse(any(
            order.get("closed_reason") in {"flatten_trade", "flatten_symbol", "global_flatten"}
            for order in self.executor.ORDERS.values()
        ))

    def test_modify_stop_missing_order_id_rejects_safely(self):
        response = self.executor.app.test_client().post("/execute", json={
            "action": "modify_stop",
            "trade_id": "T-MODIFY",
            "symbol": "NQM6",
            "stop_price": 27000.0,
            "qty": 1,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "modify_stop_missing_order_id")
        self.assertEqual(self.executor.ORDERS, {})
        self.assertEqual(self.executor.POSITIONS, {})

    def test_modify_stop_unknown_order_id_rejects_safely(self):
        self.executor.POSITIONS["NQM6"] = {
            "qty": -2.0,
            "avg_entry_price": 27020.0,
        }
        self.executor.ORDERS["LIMIT-MODIFY"] = {
            "order_id": "LIMIT-MODIFY",
            "trade_id": "T-MODIFY",
            "type": "limit",
            "symbol": "NQM6",
            "limit_price": 26980.0,
            "qty": 1.0,
            "status": "active",
            "tag": "tp1",
            "oco_group": "OCO-T-MODIFY-PROTECTIVE",
        }

        response = self.executor.app.test_client().post("/execute", json={
            "action": "modify_stop",
            "trade_id": "T-MODIFY",
            "symbol": "NQM6",
            "order_id": "STOP-UNKNOWN",
            "stop_price": 27000.0,
            "qty": 1,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 404)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "modify_stop_order_not_found")
        self.assertEqual(self.executor.ORDERS["LIMIT-MODIFY"]["status"], "active")
        self.assertEqual(self.executor.POSITIONS["NQM6"]["qty"], -2.0)

    def test_modify_stop_trade_id_mismatch_rejects_safely(self):
        self.executor.ORDERS["STOP-MODIFY"] = {
            "order_id": "STOP-MODIFY",
            "trade_id": "T-MODIFY",
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 27010.0,
            "qty": 2.0,
            "status": "active",
        }

        response = self.executor.app.test_client().post("/execute", json={
            "action": "modify_stop",
            "trade_id": "T-OTHER",
            "symbol": "NQM6",
            "order_id": "STOP-MODIFY",
            "stop_price": 27000.0,
            "qty": 1,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "modify_stop_trade_id_mismatch")
        self.assertEqual(self.executor.ORDERS["STOP-MODIFY"]["stop_price"], 27010.0)

    def test_supported_executor_actions_startup_diagnostic_includes_modify_stop(self):
        messages = []
        self.executor.log = messages.append

        self.executor.log_supported_executor_actions()

        self.assertIn("modify_stop", self.executor.SUPPORTED_EXECUTOR_ACTIONS)
        self.assertEqual(len(messages), 1)
        self.assertIn("SUPPORTED_EXECUTOR_ACTIONS", messages[0])
        self.assertIn("modify_stop", messages[0])

    def test_modify_stop_scoped_to_order_id_does_not_trigger_other_same_symbol_stop(self):
        self.executor.POSITIONS["NQM6"] = {
            "qty": -4.0,
            "avg_entry_price": 100.0,
        }
        self.executor.LAST_PRICES["NQM6"] = 99.0
        self.executor.ORDERS["STOP-A"] = {
            "order_id": "STOP-A",
            "trade_id": "T-A",
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 110.0,
            "qty": 2.0,
            "status": "active",
            "oco_group": "OCO-T-A-PROTECTIVE",
        }
        self.executor.ORDERS["STOP-B"] = {
            "order_id": "STOP-B",
            "trade_id": "T-B",
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 98.0,
            "qty": 2.0,
            "status": "active",
            "oco_group": "OCO-T-B-PROTECTIVE",
        }

        response = self.executor.app.test_client().post("/execute", json={
            "action": "modify_stop",
            "trade_id": "T-A",
            "symbol": "NQM6",
            "broker_order_id": "STOP-A",
            "stop_price": 100.0,
            "qty": 2.0,
            "tag": "breakeven",
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["stop_fills"], [])
        self.assertEqual(self.executor.ORDERS["STOP-A"]["status"], "active")
        self.assertEqual(self.executor.ORDERS["STOP-A"]["stop_price"], 100.0)
        self.assertEqual(self.executor.ORDERS["STOP-B"]["status"], "active")
        self.assertEqual(self.executor.ORDERS["STOP-B"]["stop_price"], 98.0)
        self.assertEqual(self.executor.POSITIONS["NQM6"]["qty"], -4.0)

    def test_tp1_fill_scoped_to_trade_keeps_other_same_symbol_trade_protected(self):
        self.executor.POSITIONS["NQM6"] = {
            "qty": -4.0,
            "avg_entry_price": 100.0,
        }
        self.executor.ORDERS["LIMIT-A"] = {
            "order_id": "LIMIT-A",
            "trade_id": "T-A",
            "type": "limit",
            "symbol": "NQM6",
            "limit_price": 90.0,
            "qty": 1.0,
            "status": "active",
            "tag": "tp1",
            "oco_group": "OCO-T-A-PROTECTIVE",
        }
        self.executor.ORDERS["STOP-A"] = {
            "order_id": "STOP-A",
            "trade_id": "T-A",
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 110.0,
            "qty": 2.0,
            "status": "active",
            "oco_group": "OCO-T-A-PROTECTIVE",
            "oco_role": "protective_stop",
        }
        self.executor.ORDERS["LIMIT-B"] = {
            "order_id": "LIMIT-B",
            "trade_id": "T-B",
            "type": "limit",
            "symbol": "NQM6",
            "limit_price": 80.0,
            "qty": 1.0,
            "status": "active",
            "tag": "tp1",
            "oco_group": "OCO-T-B-PROTECTIVE",
        }
        self.executor.ORDERS["STOP-B"] = {
            "order_id": "STOP-B",
            "trade_id": "T-B",
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 112.0,
            "qty": 2.0,
            "status": "active",
            "oco_group": "OCO-T-B-PROTECTIVE",
            "oco_role": "protective_stop",
        }

        response = self.executor.app.test_client().post("/price", json=self._price_payload(
            symbol="NQM6",
            price=90.0,
        ))
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["limit_fills"]), 1)
        self.assertEqual(data["limit_fills"][0]["trade_id"], "T-A")
        self.assertEqual(self.executor.POSITIONS["NQM6"]["qty"], -3.0)
        self.assertEqual(self.executor.ORDERS["LIMIT-A"]["status"], "closed")
        self.assertEqual(self.executor.ORDERS["STOP-A"]["status"], "active")
        self.assertEqual(self.executor.ORDERS["STOP-A"]["qty"], 1.0)
        self.assertEqual(self.executor.ORDERS["LIMIT-B"]["status"], "active")
        self.assertEqual(self.executor.ORDERS["STOP-B"]["status"], "active")
        self.assertEqual(self.executor.ORDERS["STOP-B"]["qty"], 2.0)

    def test_nq_stop_event_does_not_touch_ym_trade(self):
        self.executor.POSITIONS["NQM6"] = {
            "qty": -2.0,
            "avg_entry_price": 100.0,
        }
        self.executor.POSITIONS["YMM6"] = {
            "qty": -2.0,
            "avg_entry_price": 40000.0,
        }
        self.executor.ORDERS["STOP-NQ"] = {
            "order_id": "STOP-NQ",
            "trade_id": "T-NQ",
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 105.0,
            "qty": 2.0,
            "status": "active",
            "oco_group": "OCO-T-NQ-PROTECTIVE",
        }
        self.executor.ORDERS["STOP-YM"] = {
            "order_id": "STOP-YM",
            "trade_id": "T-YM",
            "type": "stop",
            "symbol": "YMM6",
            "stop_price": 40020.0,
            "qty": 2.0,
            "status": "active",
            "oco_group": "OCO-T-YM-PROTECTIVE",
        }

        response = self.executor.app.test_client().post("/price", json=self._price_payload(
            symbol="NQM6",
            price=106.0,
        ))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.executor.ORDERS["STOP-NQ"]["status"], "closed")
        self.assertEqual(self.executor.POSITIONS["NQM6"]["qty"], 0.0)
        self.assertEqual(self.executor.ORDERS["STOP-YM"]["status"], "active")
        self.assertEqual(self.executor.POSITIONS["YMM6"]["qty"], -2.0)

    def test_symbol_flatten_rejects_ambiguous_multi_trade_scope(self):
        self.executor.POSITIONS["NQM6"] = {
            "qty": -4.0,
            "avg_entry_price": 100.0,
        }
        for trade_id in ("T-A", "T-B"):
            self.executor.ORDERS[f"STOP-{trade_id}"] = {
                "order_id": f"STOP-{trade_id}",
                "trade_id": trade_id,
                "type": "stop",
                "symbol": "NQM6",
                "stop_price": 110.0,
                "qty": 2.0,
                "status": "active",
            }

        response = self.executor.app.test_client().post("/execute", json={
            "action": "flatten_symbol",
            "symbol": "NQM6",
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "ambiguous_trade_scope")
        self.assertEqual(self.executor.POSITIONS["NQM6"]["qty"], -4.0)
        self.assertEqual(self.executor.ORDERS["STOP-T-A"]["status"], "active")
        self.assertEqual(self.executor.ORDERS["STOP-T-B"]["status"], "active")

    def test_cancel_order_allowed_while_watchdog_stale(self):
        self.executor.ORDERS["LIMIT-CANCEL"] = {
            "order_id": "LIMIT-CANCEL",
            "trade_id": "T-CANCEL",
            "type": "limit",
            "symbol": "NQM6",
            "limit_price": 27010.0,
            "qty": 1.0,
            "status": "active",
        }

        response = self.executor.app.test_client().post("/execute", json={
            "action": "cancel_order",
            "broker_order_id": "LIMIT-CANCEL",
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(self.executor.ORDERS["LIMIT-CANCEL"]["status"], "cancelled")

    def test_flatten_symbol_allowed_while_watchdog_stale(self):
        self.executor.POSITIONS["NQM6"] = {
            "qty": 1.0,
            "avg_entry_price": 27000.0,
        }
        self.executor.ORDERS["STOP-FLATTEN"] = {
            "order_id": "STOP-FLATTEN",
            "trade_id": "T-FLATTEN",
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 26990.0,
            "qty": 1.0,
            "status": "active",
        }

        response = self.executor.app.test_client().post("/execute", json={
            "action": "flatten_symbol",
            "symbol": "NQM6",
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(self.executor.POSITIONS["NQM6"]["qty"], 0.0)
        self.assertEqual(self.executor.ORDERS["STOP-FLATTEN"]["status"], "closed")

    def test_sync_snapshot_marks_executor_listener_copy_stale_when_last_tick_is_old(self):
        old_timestamp = datetime.now() - timedelta(
            seconds=self.executor.LISTENER_LAST_TICK_MAX_AGE_SECONDS + 1
        )
        self.executor.LAST_PRICES["NQM6"] = 27000.25
        self.executor.LAST_PRICE_TIMESTAMPS["NQM6"] = old_timestamp.isoformat()
        self.executor.CURRENT_1M_BARS["NQM6"] = {
            "bar_timestamp": datetime.now(),
            "open": 27000.25,
            "high": 27000.25,
            "low": 27000.25,
            "close": 27000.25,
        }

        response = self.executor.app.test_client().get("/sync_snapshot")
        snapshot = response.get_json()["symbols"]["NQM6"]

        self.assertEqual(snapshot["listener_status"], "non_authoritative")
        self.assertEqual(
            snapshot["listener_status_reason"],
            "executor_snapshot_is_not_feed_authority",
        )
        self.assertEqual(snapshot["executor_listener_status_copy"], "stale")
        self.assertEqual(snapshot["executor_listener_status_reason_copy"], "last_tick_stale")
        self.assertGreater(
            snapshot["last_tick_age_seconds"],
            self.executor.LISTENER_LAST_TICK_MAX_AGE_SECONDS,
        )

    def test_sync_snapshot_marks_executor_listener_copy_missing_without_tick_timestamp(self):
        self.executor.LAST_PRICES["NQM6"] = 27000.25

        response = self.executor.app.test_client().get("/sync_snapshot")
        snapshot = response.get_json()["symbols"]["NQM6"]

        self.assertEqual(snapshot["listener_status"], "non_authoritative")
        self.assertEqual(
            snapshot["listener_status_reason"],
            "executor_snapshot_is_not_feed_authority",
        )
        self.assertEqual(snapshot["executor_listener_status_copy"], "missing")
        self.assertEqual(snapshot["executor_listener_status_reason_copy"], "last_price_missing")
        self.assertIsNone(snapshot["last_price_at"])
        self.assertIsNone(snapshot["last_tick_age_seconds"])

    def test_rty_stale_last_price_rejects_entry_without_position(self):
        old_timestamp = datetime.now() - timedelta(
            seconds=self.executor.LISTENER_LAST_TICK_MAX_AGE_SECONDS + 1
        )
        self._seed_last_price_and_current_bar(
            "RTYM6",
            price=2756.4,
            timestamp=old_timestamp,
            bar_low=2755.8,
            bar_high=2757.5,
            bar_close=2756.4,
        )

        response = self.executor.app.test_client().post("/execute", json={
            "action": "submit_entry",
            "trade_id": "T-RTY-STALE",
            "symbol": "RTY",
            "direction": "long",
            "qty": 1,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["ok"])
        self.assertEqual(data["reject_reason"], "stale_or_missing_execution_price")
        self.assertEqual(self.executor.POSITIONS, {})
        self.assertEqual(data["order"]["status"], "rejected")
        self.assertEqual(data["fill_audit"]["LAST_PRICES_lookup_key_used"], "RTYM6")
        self.assertTrue((self.tmp_path / "fill_audit_log.jsonl").exists())

    def test_rty_entry_rejects_price_older_than_entry_fill_max_age(self):
        old_timestamp = datetime.now() - timedelta(seconds=3)
        self._seed_last_price_and_current_bar(
            "RTYM6",
            price=2756.4,
            timestamp=old_timestamp,
            bar_low=2755.8,
            bar_high=2757.5,
            bar_close=2756.4,
        )

        response = self.executor.app.test_client().post("/execute", json={
            "action": "submit_entry",
            "trade_id": "T-RTY-ENTRY-MAX-AGE",
            "symbol": "RTY",
            "direction": "long",
            "qty": 1,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["ok"])
        self.assertEqual(data["reject_reason"], "stale_or_missing_execution_price")
        self.assertEqual(self.executor.POSITIONS, {})
        self.assertEqual(data["order"]["status"], "rejected")
        self.assertEqual(data["fill_audit"]["LAST_PRICES_lookup_key_used"], "RTYM6")
        self.assertEqual(data["fill_audit"]["entry_fill_last_tick_max_age_seconds"], 2.0)
        self.assertEqual(
            data["fill_audit"]["listener_last_tick_max_age_seconds"],
            self.executor.LISTENER_LAST_TICK_MAX_AGE_SECONDS,
        )
        self.assertGreaterEqual(data["fill_audit"]["last_tick_age_seconds"], 3.0)

    def test_rty_fill_outside_fresh_current_bar_range_rejects_entry(self):
        self._seed_last_price_and_current_bar(
            "RTYM6",
            price=2757.9,
            bar_low=2755.8,
            bar_high=2757.5,
            bar_close=2756.4,
        )

        response = self.executor.app.test_client().post("/execute", json={
            "action": "submit_entry",
            "trade_id": "T-RTY-RANGE",
            "symbol": "RTY",
            "direction": "long",
            "qty": 1,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["ok"])
        self.assertEqual(data["reject_reason"], "fill_price_outside_current_bar_range")
        self.assertEqual(self.executor.POSITIONS, {})
        self.assertEqual(data["order"]["status"], "rejected")

    def test_nq_fresh_price_inside_current_bar_range_allows_entry(self):
        self._seed_last_price_and_current_bar(
            "NQM6",
            price=27000.25,
            bar_low=26999.75,
            bar_high=27000.50,
            bar_close=27000.25,
        )

        response = self.executor.app.test_client().post("/execute", json={
            "action": "submit_entry",
            "trade_id": "T-NQ-FRESH",
            "symbol": "NQ",
            "direction": "long",
            "qty": 1,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["fill_price"], 27000.25)
        self.assertEqual(data["fill_price_source"], "executor_actual_fill")
        self.assertEqual(data["resolved_symbol"], "NQM6")
        self.assertEqual(self.executor.POSITIONS["NQM6"]["qty"], 1.0)

    def test_ym_fill_within_one_tick_outside_current_bar_range_allows_entry(self):
        self._seed_last_price_and_current_bar(
            "YMM6",
            price=42001.0,
            bar_low=41998.0,
            bar_high=42000.0,
            bar_close=42000.0,
        )

        response = self.executor.app.test_client().post("/execute", json={
            "action": "submit_entry",
            "trade_id": "T-YM-WITHIN-TICK",
            "symbol": "YMM6",
            "direction": "long",
            "qty": 1,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["fill_price"], 42001.0)
        self.assertEqual(data["resolved_symbol"], "YMM6")
        self.assertEqual(self.executor.POSITIONS["YMM6"]["qty"], 1.0)

    def test_ym_fill_more_than_one_tick_outside_current_bar_range_rejects_entry(self):
        self._seed_last_price_and_current_bar(
            "YMM6",
            price=42001.25,
            bar_low=41998.0,
            bar_high=42000.0,
            bar_close=42000.0,
        )

        response = self.executor.app.test_client().post("/execute", json={
            "action": "submit_entry",
            "trade_id": "T-YM-OUTSIDE-TICK",
            "symbol": "YMM6",
            "direction": "long",
            "qty": 1,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["ok"])
        self.assertEqual(data["reject_reason"], "fill_price_outside_current_bar_range")
        self.assertEqual(self.executor.POSITIONS, {})
        self.assertEqual(data["fill_audit"]["current_bar_range_tolerance"], 1.0)

    def test_exact_requested_contract_last_price_is_preferred_over_alias_resolution(self):
        self.executor.resolve_execution_symbol = lambda symbol: ("NQU6", "test_alias_fallback")
        self._seed_last_price_and_current_bar(
            "NQM6",
            price=27000.25,
            bar_low=26999.75,
            bar_high=27000.50,
            bar_close=27000.25,
        )
        self._seed_last_price_and_current_bar(
            "NQU6",
            price=27100.25,
            bar_low=27100.00,
            bar_high=27100.50,
            bar_close=27100.25,
        )

        response = self.executor.app.test_client().post("/execute", json={
            "action": "submit_entry",
            "trade_id": "T-NQ-EXACT",
            "symbol": "NQM6",
            "direction": "long",
            "qty": 1,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["fill_price"], 27000.25)
        self.assertEqual(data["resolved_symbol"], "NQM6")
        self.assertEqual(self.executor.POSITIONS["NQM6"]["qty"], 1.0)

    def test_short_tp1_limit_fills_before_be_and_resizes_stop_to_runner(self):
        trade_id = "T-short-before-be"
        self._seed_trade_with_limit_and_stop(
            trade_id=trade_id,
            position_qty=-2,
            avg_entry_price=26996.5,
            limit_price=26984.5,
            stop_price=27008.5,
        )

        client = self.executor.app.test_client()
        response = client.post("/price", json=self._price_payload(
            symbol="NQM6",
            price=26984.5,
        ))

        self._assert_tp1_limit_fill(response, trade_id=trade_id, expected_position_qty=-1.0)
        self.assertEqual(self.executor.ORDERS[f"STOP-{trade_id}"]["stop_price"], 27008.5)

    def test_short_tp1_limit_fills_after_be_and_resizes_be_stop_to_runner(self):
        trade_id = "T-short-after-be"
        self._seed_trade_with_limit_and_stop(
            trade_id=trade_id,
            position_qty=-2,
            avg_entry_price=26996.5,
            limit_price=26984.5,
            stop_price=26996.5,
            stop_tag="breakeven",
        )

        client = self.executor.app.test_client()
        response = client.post("/price", json=self._price_payload(
            symbol="NQM6",
            price=26977.5,
        ))

        self._assert_tp1_limit_fill(response, trade_id=trade_id, expected_position_qty=-1.0)
        self.assertEqual(self.executor.ORDERS[f"STOP-{trade_id}"]["stop_price"], 26996.5)
        self.assertEqual(self.executor.ORDERS[f"STOP-{trade_id}"]["tag"], "breakeven")

    def test_long_tp1_limit_fills_before_be_and_resizes_stop_to_runner(self):
        trade_id = "T-long-before-be"
        self._seed_trade_with_limit_and_stop(
            trade_id=trade_id,
            position_qty=2,
            avg_entry_price=100.0,
            limit_price=112.0,
            stop_price=88.0,
        )

        client = self.executor.app.test_client()
        response = client.post("/price", json=self._price_payload(
            symbol="NQM6",
            price=112.0,
        ))

        self._assert_tp1_limit_fill(response, trade_id=trade_id, expected_position_qty=1.0)
        self.assertEqual(self.executor.ORDERS[f"STOP-{trade_id}"]["stop_price"], 88.0)

    def test_long_tp1_limit_fills_after_be_and_resizes_be_stop_to_runner(self):
        trade_id = "T-long-after-be"
        self._seed_trade_with_limit_and_stop(
            trade_id=trade_id,
            position_qty=2,
            avg_entry_price=100.0,
            limit_price=112.0,
            stop_price=100.0,
            stop_tag="breakeven",
        )

        client = self.executor.app.test_client()
        response = client.post("/price", json=self._price_payload(
            symbol="NQM6",
            price=120.0,
        ))

        self._assert_tp1_limit_fill(response, trade_id=trade_id, expected_position_qty=1.0)
        self.assertEqual(self.executor.ORDERS[f"STOP-{trade_id}"]["stop_price"], 100.0)
        self.assertEqual(self.executor.ORDERS[f"STOP-{trade_id}"]["tag"], "breakeven")

    def test_reset_stop_to_original_uses_requested_runner_qty(self):
        trade_id = "T-reset-runner"
        self.executor.POSITIONS["NQM6"] = {
            "qty": -1.0,
            "avg_entry_price": 27040.5,
        }
        self.executor.ORDERS["STOP-BE"] = {
            "order_id": "STOP-BE",
            "trade_id": trade_id,
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 27040.5,
            "qty": 2.0,
            "status": "active",
            "tag": "breakeven",
        }

        client = self.executor.app.test_client()
        response = client.post("/execute", json={
            "action": "reset_stop_to_original",
            "trade_id": trade_id,
            "symbol": "NQM6",
            "stop_price": 27049.5,
            "qty": 1,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(self.executor.ORDERS["STOP-BE"]["status"], "cancelled")
        new_stop = self.executor.ORDERS[data["new_stop_id"]]
        self.assertEqual(new_stop["status"], "active")
        self.assertEqual(new_stop["stop_price"], 27049.5)
        self.assertEqual(new_stop["qty"], 1.0)
        self.assertEqual(new_stop["tag"], "runner_reset")

    def test_submit_stop_duplicate_matching_existing_stop_is_idempotent(self):
        trade_id = "T-idempotent-stop"
        self.executor.ORDERS["STOP-existing"] = {
            "order_id": "STOP-existing",
            "trade_id": trade_id,
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 27049.5,
            "qty": 1.0,
            "status": "active",
        }

        response = self.executor.app.test_client().post("/execute", json={
            "action": "submit_stop",
            "trade_id": trade_id,
            "symbol": "NQM6",
            "stop_price": 27049.504,
            "qty": 1,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertTrue(data["idempotent"])
        self.assertEqual(data["message"], "duplicate_stop_idempotent")
        self.assertEqual(data["broker_order_id"], "STOP-existing")
        self.assertEqual(len(self.executor.active_orders_for_trade(trade_id, "stop")), 1)

    def test_submit_stop_duplicate_conflicting_existing_stop_still_rejects(self):
        trade_id = "T-conflicting-stop"
        self.executor.ORDERS["STOP-existing"] = {
            "order_id": "STOP-existing",
            "trade_id": trade_id,
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 27049.5,
            "qty": 1.0,
            "status": "active",
        }

        response = self.executor.app.test_client().post("/execute", json={
            "action": "submit_stop",
            "trade_id": trade_id,
            "symbol": "NQM6",
            "stop_price": 27051.0,
            "qty": 1,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Active stop already exists for this trade")
        self.assertEqual(len(self.executor.active_orders_for_trade(trade_id, "stop")), 1)

    def test_submit_stop_duplicate_check_is_trade_and_symbol_scoped(self):
        self.executor.ORDERS["STOP-NQ"] = {
            "order_id": "STOP-NQ",
            "trade_id": "T-NQ",
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 27049.5,
            "qty": 1.0,
            "status": "active",
        }
        self.executor.ORDERS["STOP-RTY"] = {
            "order_id": "STOP-RTY",
            "trade_id": "T-RTY",
            "type": "stop",
            "symbol": "RTYM6",
            "stop_price": 42010.0,
            "qty": 1.0,
            "status": "active",
        }

        response = self.executor.app.test_client().post("/execute", json={
            "action": "submit_stop",
            "trade_id": "T-RTY",
            "symbol": "RTYM6",
            "stop_price": 42010.0,
            "qty": 1,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertTrue(data["idempotent"])
        self.assertEqual(data["broker_order_id"], "STOP-RTY")
        self.assertEqual(self.executor.ORDERS["STOP-NQ"]["status"], "active")
        self.assertEqual(len(self.executor.active_orders_for_trade("T-NQ", "stop")), 1)
        self.assertEqual(len(self.executor.active_orders_for_trade("T-RTY", "stop")), 1)

    def test_reset_stop_to_original_duplicate_matching_runner_stop_is_idempotent(self):
        trade_id = "T-runner-reset-race"
        self.executor.ORDERS["STOP-runner"] = {
            "order_id": "STOP-runner",
            "trade_id": trade_id,
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 27049.5,
            "qty": 1.0,
            "status": "active",
            "tag": "runner_reset",
        }

        response = self.executor.app.test_client().post("/execute", json={
            "action": "reset_stop_to_original",
            "trade_id": trade_id,
            "symbol": "NQM6",
            "stop_price": 27049.5,
            "qty": 1,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertTrue(data["idempotent"])
        self.assertEqual(data["message"], "duplicate_stop_idempotent")
        self.assertEqual(data["new_stop_id"], "STOP-runner")
        self.assertEqual(self.executor.ORDERS["STOP-runner"]["status"], "active")
        self.assertEqual(len(self.executor.active_orders_for_trade(trade_id, "stop")), 1)

    def test_flatten_all_flattens_every_symbol_and_cancels_all_working_orders(self):
        self.executor.POSITIONS["NQM6"] = {
            "qty": -1.0,
            "avg_entry_price": 27403.25,
        }
        self.executor.POSITIONS["RTYM6"] = {
            "qty": 1.0,
            "avg_entry_price": 49276.0,
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
        self.executor.ORDERS["STOP-RTY"] = {
            "order_id": "STOP-RTY",
            "trade_id": "T-RTY",
            "type": "stop",
            "symbol": "RTYM6",
            "stop_price": 49271.0,
            "qty": 1.0,
            "status": "active",
        }

        response = self.executor.app.test_client().post("/execute", json={
            "action": "flatten_all",
            "reason": "qa critical escalation: test",
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertCountEqual(data["flattened_symbols"], ["NQM6", "RTYM6"])
        self.assertCountEqual(data["cancelled_order_ids"], ["STOP-NQ", "STOP-RTY"])
        self.assertEqual(self.executor.POSITIONS["NQM6"]["qty"], 0.0)
        self.assertEqual(self.executor.POSITIONS["RTYM6"]["qty"], 0.0)
        self.assertEqual(self.executor.ORDERS["STOP-NQ"]["status"], "cancelled")
        self.assertEqual(self.executor.ORDERS["STOP-RTY"]["status"], "cancelled")
        self.assertEqual(self.executor.active_orders_for_trade("T-nq", "stop"), [])
        self.assertEqual(self.executor.active_orders_for_trade("T-RTY", "stop"), [])

    def test_sync_snapshot_prefers_tradingview_atr_for_nq_alias(self):
        now = datetime.now().isoformat()
        self.executor.LAST_PRICES["NQM6"] = 27000.0
        self._write_tradingview_atr_state({
            "NQ": {
                "symbol": "NQ",
                "atr_period": 14,
                "atr_value": 23.5,
                "timeframe": "1m",
                "source": "tradingview",
                "received_at": now,
            }
        })

        response = self.executor.app.test_client().get("/sync_snapshot")
        snapshot = response.get_json()["symbols"]["NQM6"]

        self.assertEqual(snapshot["atr_1m_14"], 23.5)
        self.assertEqual(snapshot["atr_source"], "tradingview_atr_relay")
        self.assertEqual(snapshot["atr_status"], "ready")
        self.assertEqual(snapshot["atr_bar_timestamp"], now)
        self.assertTrue(snapshot["atr_trade_approved"])
        self.assertEqual(snapshot["atr_policy"], "trade_entry_approved")

    def test_sync_snapshot_prefers_tradingview_atr_for_ym_alias(self):
        now = datetime.now().isoformat()
        self.executor.LAST_PRICES["RTYM6"] = 42000.0
        self._write_tradingview_atr_state({
            "RTY": {
                "symbol": "RTY",
                "atr_period": 14,
                "atr_value": 81.0,
                "timeframe": "1m",
                "source": "tradingview",
                "received_at": now,
            }
        })

        response = self.executor.app.test_client().get("/sync_snapshot")
        snapshot = response.get_json()["symbols"]["RTYM6"]

        self.assertEqual(snapshot["atr_1m_14"], 81.0)
        self.assertEqual(snapshot["atr_source"], "tradingview_atr_relay")
        self.assertEqual(snapshot["atr_status"], "ready")
        self.assertEqual(snapshot["atr_bar_timestamp"], now)
        self.assertTrue(snapshot["atr_trade_approved"])
        self.assertEqual(snapshot["atr_policy"], "trade_entry_approved")

    def test_sync_snapshot_falls_back_to_live_executor_atr_when_tradingview_stale(self):
        stale_time = (datetime.now() - timedelta(seconds=self.executor.TRADINGVIEW_ATR_MAX_AGE_SECONDS + 30)).isoformat()
        self.executor.LAST_PRICES["NQM6"] = 27000.0
        self._write_tradingview_atr_state({
            "NQ": {
                "symbol": "NQ",
                "atr_period": 14,
                "atr_value": 99.0,
                "timeframe": "1m",
                "source": "tradingview",
                "received_at": stale_time,
            }
        })
        self._seed_completed_bars("NQM6", range(100, 115))

        response = self.executor.app.test_client().get("/sync_snapshot")
        snapshot = response.get_json()["symbols"]["NQM6"]

        self.assertNotEqual(snapshot["atr_1m_14"], 99.0)
        self.assertEqual(snapshot["atr_source"], "live_executor_1m14")
        self.assertEqual(snapshot["atr_status"], "ready")
        self.assertFalse(snapshot["atr_trade_approved"])
        self.assertEqual(snapshot["atr_policy"], "diagnostic_only_not_trade_approved")

    def test_sync_snapshot_keeps_symbol_tradingview_atr_isolated(self):
        now = datetime.now().isoformat()
        self.executor.LAST_PRICES["NQM6"] = 27000.0
        self.executor.LAST_PRICES["RTYM6"] = 42000.0
        self._write_tradingview_atr_state({
            "RTY": {
                "symbol": "RTY",
                "atr_period": 14,
                "atr_value": 77.0,
                "timeframe": "1m",
                "source": "tradingview",
                "received_at": now,
            }
        })
        self._seed_completed_bars("NQM6", range(200, 215))

        response = self.executor.app.test_client().get("/sync_snapshot")
        snapshots = response.get_json()["symbols"]

        self.assertEqual(snapshots["RTYM6"]["atr_1m_14"], 77.0)
        self.assertEqual(snapshots["RTYM6"]["atr_source"], "tradingview_atr_relay")
        self.assertEqual(snapshots["NQM6"]["atr_source"], "live_executor_1m14")
        self.assertNotEqual(snapshots["NQM6"]["atr_1m_14"], 77.0)
        self.assertTrue(snapshots["RTYM6"]["atr_trade_approved"])
        self.assertFalse(snapshots["NQM6"]["atr_trade_approved"])

    def test_set_manual_exit_limit_creates_reduce_only_limit_and_replaces_tp(self):
        self.executor.POSITIONS["NQM6"] = {
            "qty": 2.0,
            "avg_entry_price": 27000.0,
        }
        self.executor.ORDERS["LIMIT-TP1"] = {
            "order_id": "LIMIT-TP1",
            "trade_id": "T-MANUAL",
            "type": "limit",
            "symbol": "NQM6",
            "limit_price": 27020.0,
            "qty": 1.0,
            "status": "active",
            "tag": "tp1",
            "oco_group": "OCO-T-MANUAL-PROTECTIVE",
            "oco_role": "tp1_limit",
        }
        self.executor.ORDERS["STOP-PROTECTIVE"] = {
            "order_id": "STOP-PROTECTIVE",
            "trade_id": "T-MANUAL",
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 26980.0,
            "qty": 2.0,
            "status": "active",
            "oco_group": "OCO-T-MANUAL-PROTECTIVE",
            "oco_role": "protective_stop",
        }

        response = self.executor.app.test_client().post("/execute", json={
            "action": "set_manual_exit_limit",
            "trade_id": "T-MANUAL",
            "symbol": "NQM6",
            "limit_price": 27025.0,
            "qty": 1,
            "manual_confirmation": True,
            "intent": "manual_exit_limit",
            "replace_existing_tp": True,
            "level_label": "YL",
            "oco_group": "OCO-T-MANUAL-PROTECTIVE",
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(self.executor.ORDERS["LIMIT-TP1"]["status"], "cancelled")
        self.assertEqual(self.executor.ORDERS["LIMIT-TP1"]["closed_reason"], "manual_exit_limit_replaced")
        order = data["order"]
        self.assertEqual(order["type"], "limit")
        self.assertEqual(order["tag"], "manual_exit_limit")
        self.assertEqual(order["oco_role"], "manual_exit_limit")
        self.assertEqual(order["oco_group"], "OCO-T-MANUAL-PROTECTIVE")
        self.assertTrue(order["reduce_only"])
        self.assertEqual(order["side"], "sell")
        self.assertEqual(order["tif"], "DAY")
        self.assertEqual(order["limit_price"], 27025.0)
        self.assertEqual(order["qty"], 1.0)
        self.assertEqual(order["level_label"], "YL")
        self.assertEqual(self.executor.POSITIONS["NQM6"]["qty"], 2.0)

    def test_set_manual_exit_limit_rejects_without_manual_confirmation(self):
        self.executor.POSITIONS["NQM6"] = {
            "qty": -1.0,
            "avg_entry_price": 27000.0,
        }

        response = self.executor.app.test_client().post("/execute", json={
            "action": "set_manual_exit_limit",
            "trade_id": "T-MANUAL",
            "symbol": "NQM6",
            "limit_price": 26980.0,
            "qty": 1,
            "intent": "manual_exit_limit",
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "manual_confirmation_required")
        self.assertEqual(self.executor.ORDERS, {})

    def test_set_manual_exit_limit_rejects_quantity_above_position(self):
        self.executor.POSITIONS["NQM6"] = {
            "qty": 1.0,
            "avg_entry_price": 27000.0,
        }

        response = self.executor.app.test_client().post("/execute", json={
            "action": "set_manual_exit_limit",
            "trade_id": "T-MANUAL",
            "symbol": "NQM6",
            "limit_price": 27020.0,
            "qty": 2,
            "manual_confirmation": True,
            "intent": "manual_exit_limit",
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "manual_exit_qty_exceeds_position")
        self.assertEqual(self.executor.ORDERS, {})

    def test_set_manual_exit_limit_rejects_invalid_tick_increment(self):
        self.executor.POSITIONS["NQM6"] = {
            "qty": 1.0,
            "avg_entry_price": 27000.0,
        }

        response = self.executor.app.test_client().post("/execute", json={
            "action": "set_manual_exit_limit",
            "trade_id": "T-MANUAL",
            "symbol": "NQM6",
            "limit_price": 27020.13,
            "qty": 1,
            "manual_confirmation": True,
            "intent": "manual_exit_limit",
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "invalid_tick_increment")
        self.assertEqual(self.executor.ORDERS, {})

    def test_set_manual_exit_limit_rejects_active_limit_without_replace(self):
        self.executor.POSITIONS["NQM6"] = {
            "qty": -1.0,
            "avg_entry_price": 27000.0,
        }
        self.executor.ORDERS["STOP-PROTECTIVE"] = {
            "order_id": "STOP-PROTECTIVE",
            "trade_id": "T-MANUAL",
            "type": "stop",
            "symbol": "NQM6",
            "stop_price": 27010.0,
            "qty": 1.0,
            "status": "active",
            "oco_group": "OCO-T-MANUAL-PROTECTIVE",
            "oco_role": "protective_stop",
        }
        self.executor.ORDERS["LIMIT-EXISTING"] = {
            "order_id": "LIMIT-EXISTING",
            "trade_id": "T-MANUAL",
            "type": "limit",
            "symbol": "NQM6",
            "limit_price": 26980.0,
            "qty": 1.0,
            "status": "active",
            "tag": "tp1",
            "oco_group": "OCO-T-MANUAL-PROTECTIVE",
        }

        response = self.executor.app.test_client().post("/execute", json={
            "action": "set_manual_exit_limit",
            "trade_id": "T-MANUAL",
            "symbol": "NQM6",
            "limit_price": 26975.0,
            "qty": 1,
            "manual_confirmation": True,
            "intent": "manual_exit_limit",
            "replace_existing_tp": False,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "active_limit_exists")
        self.assertEqual(self.executor.ORDERS["LIMIT-EXISTING"]["status"], "active")

    def test_set_manual_exit_limit_rejects_when_oco_linkage_not_confirmed(self):
        self.executor.POSITIONS["NQM6"] = {
            "qty": 1.0,
            "avg_entry_price": 27000.0,
        }

        response = self.executor.app.test_client().post("/execute", json={
            "action": "set_manual_exit_limit",
            "trade_id": "T-MANUAL",
            "symbol": "NQM6",
            "limit_price": 27020.0,
            "qty": 1,
            "manual_confirmation": True,
            "intent": "manual_exit_limit",
            "oco_group": "OCO-T-MANUAL-PROTECTIVE",
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "oco_linkage_not_confirmed")
        self.assertEqual(self.executor.ORDERS, {})

    def test_day_manual_exit_limit_expires_after_session_date(self):
        self.executor.ORDERS["LIMIT-DAY"] = {
            "order_id": "LIMIT-DAY",
            "trade_id": "T-MANUAL",
            "type": "limit",
            "symbol": "NQM6",
            "limit_price": 27020.0,
            "qty": 1.0,
            "status": "active",
            "tag": "manual_exit_limit",
            "oco_group": "OCO-T-MANUAL-PROTECTIVE",
            "oco_role": "manual_exit_limit",
            "reduce_only": True,
            "tif": "DAY",
            "session_date": "2026-05-01",
        }

        expired = self.executor.expire_stale_day_manual_exit_orders(reference_date="2026-05-02")

        self.assertEqual(expired, ["LIMIT-DAY"])
        self.assertEqual(self.executor.ORDERS["LIMIT-DAY"]["status"], "cancelled")
        self.assertEqual(self.executor.ORDERS["LIMIT-DAY"]["closed_reason"], "day_manual_exit_expired")


if __name__ == "__main__":
    unittest.main()
