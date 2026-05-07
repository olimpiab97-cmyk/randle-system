import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
from datetime import timedelta, timezone
from io import BytesIO
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class RithmicLiveListenerTests(unittest.TestCase):
    def setUp(self):
        sys.dont_write_bytecode = True
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.listener = self._load_listener()
        self.listener.ATR_SNAPSHOT_PATH = self.tmp_path / "rithmic_atr_snapshot.json"
        self.listener.RECENT_BARS_PATH = self.tmp_path / "rithmic_recent_bars.json"
        self.listener.FEED_HEALTH_PATH = self.tmp_path / "rithmic_feed_health.json"
        self.listener.ATR_SHADOW_COMPARISON_PATH = self.tmp_path / "rithmic_atr_shadow_comparison.json"
        self.listener.TRADE_MANAGER_PERSISTENCE_PATH = self.tmp_path / "persistence_state.json"
        self.listener.LIVE_TICK_SYMBOLS.clear()
        self.listener.DEAD_RESTART_ATTEMPTS.clear()
        self.listener.DEAD_RESTART_LAST_TIMES.clear()
        self.listener.latest_price_by_symbol.clear()
        self.listener.latest_tick_time_by_symbol.clear()
        self.listener.latest_tick_monotonic_by_symbol.clear()
        self.listener.latest_dirty_by_symbol.clear()
        self.listener.latest_published_tick_time_by_symbol.clear()
        self.listener.raw_callback_count.clear()
        self._original_subscriptions_env = os.environ.get(self.listener.RITHMIC_SUBSCRIPTIONS_ENV)
        self._original_secondary_diagnostic_env = os.environ.get(
            self.listener.RITHMIC_SECONDARY_DIAGNOSTIC_SUBSCRIPTION_ENV
        )

    def tearDown(self):
        if self._original_subscriptions_env is None:
            os.environ.pop(self.listener.RITHMIC_SUBSCRIPTIONS_ENV, None)
        else:
            os.environ[self.listener.RITHMIC_SUBSCRIPTIONS_ENV] = self._original_subscriptions_env
        if self._original_secondary_diagnostic_env is None:
            os.environ.pop(self.listener.RITHMIC_SECONDARY_DIAGNOSTIC_SUBSCRIPTION_ENV, None)
        else:
            os.environ[self.listener.RITHMIC_SECONDARY_DIAGNOSTIC_SUBSCRIPTION_ENV] = (
                self._original_secondary_diagnostic_env
            )
        self.tmp.cleanup()

    def _load_listener(self):
        spec = importlib.util.spec_from_file_location("listener_under_test", ROOT / "rithmic_live_listener.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _iso_seconds_ago(self, seconds):
        return (self.listener.datetime.now(timezone.utc) - timedelta(seconds=seconds)).replace(tzinfo=None, microsecond=0).isoformat() + "Z"

    def _fake_process(self):
        class FakeProcess:
            def __init__(self):
                self.terminated = False

            def poll(self):
                return 1 if self.terminated else None

            def terminate(self):
                self.terminated = True

            def wait(self, timeout=None):
                return 1

            def kill(self):
                self.terminated = True

        return FakeProcess()

    def _wait_for_termination(self, process, timeout=3):
        deadline = time.monotonic() + timeout
        while not process.terminated and time.monotonic() < deadline:
            time.sleep(0.05)

    def _http_error(self, status, payload):
        return urllib.error.HTTPError(
            url=str(self.listener.EXECUTOR_PRICE_URL),
            code=status,
            msg="CONFLICT",
            hdrs={},
            fp=BytesIO(json.dumps(payload).encode("utf-8")),
        )

    def _contiguous_bars(self, symbol="NQM6", count=15, start_minute=31):
        bars = []
        for index in range(count):
            minute = start_minute + index
            price = 19000.0 + index
            bars.append({
                "timestamp": f"2026-04-30T13:{minute:02d}:00Z",
                "symbol": symbol,
                "open": price,
                "high": price + 1.0,
                "low": price - 1.0,
                "close": price + 0.25,
            })
        return bars

    def test_build_command_subscribes_nq_and_rty_contracts(self):
        self.listener.ensure_runtime_files = lambda: Path(r"C:\fake\rapiplus.dll")
        self.listener.write_powershell_bridge = lambda: Path(r"C:\fake\bridge.ps1")
        self.listener.RITHMIC_USER = "user"
        self.listener.RITHMIC_PASSWORD = "pass"

        command = self.listener.build_command()

        self.assertIn("-Subscriptions", command)
        subscriptions = command[command.index("-Subscriptions") + 1]
        self.assertEqual(subscriptions, "CME:NQM6,CME:RTYM6,CBOT:YMM6")

    def test_redact_secret_never_returns_full_secret(self):
        secret = "super-secret-password"

        redacted = self.listener.redact_secret(secret)

        self.assertNotEqual(redacted, secret)
        self.assertNotIn(secret, redacted)
        self.assertIn("redacted", redacted)

    def test_missing_credential_error_does_not_include_raw_secret(self):
        old_user = self.listener.RITHMIC_USER
        old_password = self.listener.RITHMIC_PASSWORD
        try:
            self.listener.RITHMIC_USER = ""
            self.listener.RITHMIC_PASSWORD = "super-secret-password"

            with self.assertRaises(RuntimeError) as raised:
                self.listener.validate_env()
        finally:
            self.listener.RITHMIC_USER = old_user
            self.listener.RITHMIC_PASSWORD = old_password

        message = str(raised.exception)
        self.assertIn("RITHMIC_USER", message)
        self.assertNotIn("super-secret-password", message)

    def test_credential_diagnostics_are_presence_only_and_sanitized(self):
        old_user = self.listener.RITHMIC_USER
        old_password = self.listener.RITHMIC_PASSWORD
        try:
            self.listener.RITHMIC_USER = "user-secret-value"
            self.listener.RITHMIC_PASSWORD = "password-secret-value"

            status = self.listener.credential_presence_status()
            sanitized = self.listener.sanitize_log_message(
                "login failed for user-secret-value using password-secret-value"
            )
        finally:
            self.listener.RITHMIC_USER = old_user
            self.listener.RITHMIC_PASSWORD = old_password

        self.assertEqual(status, {"RITHMIC_USER": "present", "RITHMIC_PASSWORD": "present"})
        self.assertNotIn("user-secret-value", sanitized)
        self.assertNotIn("password-secret-value", sanitized)
        self.assertIn("redacted", sanitized)

    def test_diagnostic_rty_subscription_override_keeps_nq_unchanged(self):
        os.environ[self.listener.RITHMIC_SECONDARY_DIAGNOSTIC_SUBSCRIPTION_ENV] = "CME:RTY"

        subscriptions = self.listener.parse_rithmic_subscriptions()

        self.assertEqual(subscriptions, [("CME", "NQM6"), ("CBOT", "YMM6"), ("CME", "RTY")])

    def test_write_atr_snapshot_preserves_other_symbol_entries(self):
        self.listener.LIVE_TICK_SYMBOLS.update({"NQM6", "RTYM6"})
        self.listener.write_atr_snapshot("NQM6", "2026-01-01T09:29:00Z", 10.0)
        self.listener.write_atr_snapshot("RTYM6", "2026-01-01T09:29:00Z", 25.0)

        payload = json.loads(self.listener.ATR_SNAPSHOT_PATH.read_text(encoding="utf-8"))

        self.assertEqual(payload["symbols"]["NQM6"]["atr_value"], 10.0)
        self.assertEqual(payload["symbols"]["NQ"]["atr_value"], 10.0)
        self.assertEqual(payload["symbols"]["RTYM6"]["atr_value"], 25.0)
        self.assertEqual(payload["symbols"]["RTY"]["atr_value"], 25.0)

    def test_update_recent_bars_keeps_symbol_state_separate(self):
        self.listener.LIVE_TICK_SYMBOLS.update({"NQM6", "RTYM6"})
        nq_bar = {
            "timestamp": "2026-01-01T09:30:00Z",
            "symbol": "NQM6",
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
        }
        ym_bar = {
            "timestamp": "2026-01-01T09:30:00Z",
            "symbol": "RTYM6",
            "open": 42000.0,
            "high": 42010.0,
            "low": 41990.0,
            "close": 42005.0,
        }

        bar_cache = {}
        self.listener.update_recent_bars(bar_cache, nq_bar)
        self.listener.update_recent_bars(bar_cache, ym_bar)

        self.assertEqual(len(bar_cache["NQM6"]), 1)
        self.assertEqual(len(bar_cache["RTYM6"]), 1)
        payload = json.loads(self.listener.RECENT_BARS_PATH.read_text(encoding="utf-8"))
        self.assertIn("NQM6", payload["symbols"])
        self.assertIn("RTYM6", payload["symbols"])

    def test_atr_shadow_computes_after_15_contiguous_bars_and_compares_tv(self):
        self.listener.TRADE_MANAGER_PERSISTENCE_PATH.write_text(json.dumps({
            "tradingview_atr": {
                "NQ": {
                    "atr_value": 2.5,
                    "received_at": "2026-04-30T13:45:05Z",
                }
            }
        }), encoding="utf-8")
        bar_cache = {}

        for bar in self._contiguous_bars(count=self.listener.ATR_SEED_BAR_COUNT):
            self.listener.update_recent_bars(bar_cache, bar)

        payload = json.loads(self.listener.ATR_SHADOW_COMPARISON_PATH.read_text(encoding="utf-8"))
        record = payload["symbols"]["NQM6"]
        self.assertEqual(record["source"], "rithmic_worker_atr_shadow")
        self.assertEqual(record["atr_status"], "OK")
        self.assertEqual(record["completed_bar_count"], self.listener.ATR_SEED_BAR_COUNT)
        self.assertEqual(record["contiguous_bar_count"], self.listener.ATR_SEED_BAR_COUNT)
        self.assertFalse(record["gap_detected"])
        self.assertEqual(record["rithmic_atr"], 2.0)
        self.assertEqual(record["tv_atr"], 2.5)
        self.assertEqual(record["delta_abs"], 0.5)
        self.assertEqual(record["delta_pct"], 20.0)
        self.assertIn("NQ", payload["symbols"])

    def test_atr_shadow_does_not_compute_before_15_contiguous_bars(self):
        bar_cache = {}

        for bar in self._contiguous_bars(count=self.listener.ATR_SEED_BAR_COUNT - 1):
            self.listener.update_recent_bars(bar_cache, bar)

        payload = json.loads(self.listener.ATR_SHADOW_COMPARISON_PATH.read_text(encoding="utf-8"))
        record = payload["symbols"]["NQM6"]
        self.assertIsNone(record["rithmic_atr"])
        self.assertEqual(record["atr_status"], "INSUFFICIENT_BARS")
        self.assertEqual(record["contiguous_bar_count"], self.listener.ATR_SEED_BAR_COUNT - 1)

    def test_atr_shadow_gap_invalidates_continuity(self):
        bar_cache = {}
        bars = self._contiguous_bars(count=10, start_minute=31)
        bars.extend(self._contiguous_bars(count=5, start_minute=50))

        for bar in bars:
            self.listener.update_recent_bars(bar_cache, bar)

        payload = json.loads(self.listener.ATR_SHADOW_COMPARISON_PATH.read_text(encoding="utf-8"))
        record = payload["symbols"]["NQM6"]
        self.assertIsNone(record["rithmic_atr"])
        self.assertTrue(record["gap_detected"])
        self.assertEqual(record["contiguous_bar_count"], 5)
        self.assertEqual(record["atr_status"], "GAP_INVALID")

    def test_atr_shadow_tv_missing_keeps_rithmic_shadow_only(self):
        bar_cache = {}

        for bar in self._contiguous_bars(count=self.listener.ATR_SEED_BAR_COUNT):
            self.listener.update_recent_bars(bar_cache, bar)

        payload = json.loads(self.listener.ATR_SHADOW_COMPARISON_PATH.read_text(encoding="utf-8"))
        record = payload["symbols"]["NQM6"]
        self.assertEqual(record["rithmic_atr"], 2.0)
        self.assertIsNone(record["tv_atr"])
        self.assertIsNone(record["delta_abs"])
        self.assertIsNone(record["delta_pct"])
        self.assertEqual(record["atr_status"], "RITHMIC_ONLY_SHADOW")

    def test_callback_price_update_does_not_write_atr_shadow_or_bars(self):
        updated = self.listener.update_latest_price_from_tick({
            "timestamp": "2026-04-30T13:31:00Z",
            "symbol": "NQM6",
            "price": 19000.25,
        })

        self.assertTrue(updated)
        self.assertFalse(self.listener.ATR_SHADOW_COMPARISON_PATH.exists())
        self.assertFalse(self.listener.RECENT_BARS_PATH.exists())

    def test_rithmic_trade_print_callback_only_enqueues_tick(self):
        bridge_source = self.listener.build_powershell_bridge()
        callback_start = bridge_source.index("public override void TradePrint")
        callback_end = bridge_source.index("public override void Alert", callback_start)
        callback_source = bridge_source[callback_start:callback_end]

        self.assertIn("Callback-safe only", callback_source)
        self.assertIn("EnqueueTick(normalizedSymbol, info.Price, DateTime.UtcNow);", callback_source)
        self.assertNotIn("Console.WriteLine", callback_source)
        self.assertNotIn("PrintTick", callback_source)
        self.assertNotIn("Url", callback_source)
        self.assertNotIn("Request", callback_source)
        self.assertNotIn("json", callback_source.lower())

    def test_listener_stall_marks_feed_stale(self):
        reference_time = self.listener.datetime(2026, 4, 30, 13, 31, 5)
        entry = {"last_tick_timestamp_utc": "2026-04-30T13:31:00Z"}

        status = self.listener.calculate_feed_status(entry, reference_time=reference_time)

        self.assertEqual(status, "STALE")

    def test_ym_and_rty_enter_quiet_before_stale(self):
        reference_time = self.listener.datetime(2026, 4, 30, 13, 31, 5)
        entry = {"last_tick_timestamp_utc": "2026-04-30T13:31:00Z"}

        self.assertEqual(
            self.listener.calculate_feed_status(entry, reference_time=reference_time, symbol="YMM6"),
            "QUIET",
        )
        self.assertEqual(
            self.listener.calculate_feed_status(entry, reference_time=reference_time, symbol="RTYM6"),
            "QUIET",
        )

    def test_dotnet_fractional_timestamp_parses_for_feed_health(self):
        parsed = self.listener.parse_utc_timestamp("2026-05-01T14:00:50.7436316Z")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.microsecond, 743631)

    def test_all_prices_frozen_sets_critical_status(self):
        payload = {
            "symbols": {
                "NQM6": {
                    "last_tick_timestamp_utc": "2026-04-30T13:31:20Z",
                    "last_bridge_post_timestamp_utc": "2026-04-30T13:31:00Z",
                },
                "YMM6": {
                    "last_tick_timestamp_utc": "2026-04-30T13:31:20Z",
                    "last_bridge_post_timestamp_utc": "2026-04-30T13:31:00Z",
                },
            }
        }

        refreshed = self.listener.refresh_feed_health_statuses(
            payload,
            reference_time=self.listener.datetime(2026, 4, 30, 13, 31, 12),
        )

        self.assertTrue(refreshed["all_prices_frozen"])
        self.assertEqual(refreshed["critical_status"], "all_prices_frozen")
        self.assertEqual(refreshed["system_state_feed"], "CRITICAL")

    def test_single_symbol_price_bridge_frozen_is_visible_without_all_prices_frozen(self):
        reference_time = self.listener.datetime(2026, 4, 30, 13, 31, 12)
        payload = {
            "symbols": {
                "NQM6": {
                    "last_tick_timestamp_utc": "2026-04-30T13:31:12Z",
                    "last_bridge_post_timestamp_utc": "2026-04-30T13:31:12Z",
                },
                "YMM6": {
                    "last_tick_timestamp_utc": "2026-04-30T13:31:12Z",
                    "last_bridge_post_timestamp_utc": "2026-04-30T13:31:00Z",
                },
            }
        }

        refreshed = self.listener.refresh_feed_health_statuses(payload, reference_time=reference_time)

        self.assertFalse(refreshed["all_prices_frozen"])
        self.assertIsNone(refreshed["critical_status"])
        self.assertEqual(refreshed["symbols"]["YMM6"]["price_bridge_status"], "FROZEN")
        self.assertEqual(refreshed["frozen_price_symbols"], ["YMM6"])

    def test_listener_restart_stays_stale_until_first_tick(self):
        self.listener.mark_symbols_feed_status(["NQM6"], "STALE")
        payload = json.loads(self.listener.FEED_HEALTH_PATH.read_text(encoding="utf-8"))

        self.assertEqual(payload["symbols"]["NQM6"]["feed_status"], "STALE")
        self.assertEqual(payload["symbols"]["NQ"]["feed_status"], "STALE")

        self.listener.forward_price_to_executor = lambda *args, **kwargs: None
        self.listener.PRICE_POST_MIN_INTERVAL_SECONDS = 999
        worker = self.listener.TickWorker({})
        worker.process_tick({
            "timestamp": self.listener.utc_now_iso(),
            "symbol": "NQM6",
            "price": 19000.0,
        })
        worker.flush_feed_health(force=True)
        worker.process_tick({
            "timestamp": self.listener.utc_now_iso(),
            "symbol": "NQM6",
            "price": 19000.25,
        })
        worker.flush_feed_health(force=True)
        payload = json.loads(self.listener.FEED_HEALTH_PATH.read_text(encoding="utf-8"))

        self.assertEqual(payload["symbols"]["NQM6"]["feed_status"], "LIVE")

    def test_last_tick_timestamp_never_moves_forward_without_accepted_tick(self):
        original_tick = "2026-04-30T13:31:00Z"
        self.listener.write_feed_health({
            "symbols": {
                "NQM6": {
                    "feed_status": "STALE",
                    "last_tick_timestamp_utc": original_tick,
                    "recovery_tick_confirmations": 0,
                },
                "NQ": {
                    "feed_status": "STALE",
                    "last_tick_timestamp_utc": original_tick,
                    "recovery_tick_confirmations": 0,
                },
            }
        })

        self.listener.update_feed_health("NQM6", "last_tick_timestamp_utc")
        self.listener.update_feed_health("NQM6", "last_tick_timestamp_utc", "2026-04-30T13:32:00Z")

        payload = json.loads(self.listener.FEED_HEALTH_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["symbols"]["NQM6"]["last_tick_timestamp_utc"], original_tick)
        self.assertEqual(payload["symbols"]["NQ"]["last_tick_timestamp_utc"], original_tick)

    def test_non_tick_health_paths_do_not_advance_last_tick_timestamp(self):
        original_tick = "2026-04-30T13:31:00Z"
        self.listener.write_feed_health({
            "symbols": {
                "NQM6": {
                    "feed_status": "LIVE",
                    "last_tick_timestamp_utc": original_tick,
                    "recovery_tick_confirmations": self.listener.FEED_RECOVERY_TICK_CONFIRMATIONS,
                }
            }
        })
        worker = self.listener.TickWorker({})

        worker.process_completed_bar({
            "timestamp": "2026-04-30T13:32:00Z",
            "symbol": "NQM6",
            "open": 19000.0,
            "high": 19001.0,
            "low": 18999.0,
            "close": 19000.5,
        }, source="rithmic_bar")
        worker.flush_feed_health(force=True)
        self.listener.update_feed_health("NQM6", "last_bridge_post_timestamp_utc", "2026-04-30T13:32:05Z")
        self.listener.update_feed_health("NQM6", "last_executor_price_post_failure_timestamp_utc", "2026-04-30T13:32:06Z")
        self.listener.refresh_feed_health_statuses(self.listener.read_feed_health())

        payload = json.loads(self.listener.FEED_HEALTH_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["symbols"]["NQM6"]["last_tick_timestamp_utc"], original_tick)

    def test_atr_and_bar_seed_paths_do_not_advance_last_tick_timestamp(self):
        original_tick = "2026-04-30T13:31:00Z"
        self.listener.write_feed_health({
            "symbols": {
                "NQM6": {
                    "feed_status": "LIVE",
                    "last_tick_timestamp_utc": original_tick,
                    "recovery_tick_confirmations": self.listener.FEED_RECOVERY_TICK_CONFIRMATIONS,
                }
            }
        })
        historical_bars = self._contiguous_bars(count=self.listener.ATR_SEED_BAR_COUNT)
        persisted_cache = {"NQM6": self.listener.deque(historical_bars, maxlen=self.listener.MAX_PERSISTED_BARS)}

        self.listener.seed_atr_from_historical_bars({}, "NQM6", historical_bars)
        self.listener.seed_atr_from_persisted_bars(persisted_cache, "NQM6")
        self.listener.write_atr_snapshot("NQM6", "2026-04-30T13:45:00Z", 12.5)
        self.listener.update_recent_bars({}, {
            "timestamp": "2026-04-30T13:46:00Z",
            "symbol": "NQM6",
            "open": 19015.0,
            "high": 19016.0,
            "low": 19014.0,
            "close": 19015.25,
        })

        payload = json.loads(self.listener.FEED_HEALTH_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["symbols"]["NQM6"]["last_tick_timestamp_utc"], original_tick)

    def test_only_accepted_valid_tick_advances_last_tick_timestamp(self):
        original_tick = "2026-04-30T13:31:00Z"
        accepted_tick = "2026-04-30T13:32:00Z"
        self.listener.write_feed_health({
            "symbols": {
                "NQM6": {
                    "feed_status": "LIVE",
                    "last_tick_timestamp_utc": original_tick,
                    "recovery_tick_confirmations": self.listener.FEED_RECOVERY_TICK_CONFIRMATIONS,
                }
            }
        })
        self.listener.forward_price_to_executor = lambda *args, **kwargs: None
        self.listener.PRICE_POST_MIN_INTERVAL_SECONDS = 999
        worker = self.listener.TickWorker({})
        worker.latest_prices["NQM6"] = 19000.0

        worker.process_tick({
            "timestamp": "2026-04-30T13:31:30Z",
            "symbol": "NQM6",
            "price": 50000.0,
        })
        worker.flush_feed_health(force=True)
        payload = json.loads(self.listener.FEED_HEALTH_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["symbols"]["NQM6"]["last_tick_timestamp_utc"], original_tick)

        worker.process_tick({
            "timestamp": accepted_tick,
            "symbol": "NQM6",
            "price": 19000.25,
        })
        worker.flush_feed_health(force=True)
        payload = json.loads(self.listener.FEED_HEALTH_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["symbols"]["NQM6"]["last_tick_timestamp_utc"], accepted_tick)

    def test_feed_status_only_decays_without_new_accepted_ticks(self):
        tick_time = "2026-04-30T13:31:00Z"
        payload = {
            "symbols": {
                "NQM6": {
                    "feed_status": "LIVE",
                    "last_tick_timestamp_utc": tick_time,
                    "recovery_tick_confirmations": self.listener.FEED_RECOVERY_TICK_CONFIRMATIONS,
                }
            }
        }

        live = self.listener.refresh_feed_health_statuses(
            json.loads(json.dumps(payload)),
            reference_time=self.listener.datetime(2026, 4, 30, 13, 31, 1),
        )
        quiet = self.listener.refresh_feed_health_statuses(
            json.loads(json.dumps(live)),
            reference_time=self.listener.datetime(2026, 4, 30, 13, 31, 2, 500000),
        )
        stale = self.listener.refresh_feed_health_statuses(
            json.loads(json.dumps(quiet)),
            reference_time=self.listener.datetime(2026, 4, 30, 13, 31, 5),
        )
        dead = self.listener.refresh_feed_health_statuses(
            json.loads(json.dumps(stale)),
            reference_time=self.listener.datetime(2026, 4, 30, 13, 31, 30),
        )
        still_dead = self.listener.refresh_feed_health_statuses(
            json.loads(json.dumps(dead)),
            reference_time=self.listener.datetime(2026, 4, 30, 13, 31, 40),
        )

        self.assertEqual(live["symbols"]["NQM6"]["feed_status"], "LIVE")
        self.assertEqual(quiet["symbols"]["NQM6"]["feed_status"], "QUIET")
        self.assertEqual(stale["symbols"]["NQM6"]["feed_status"], "STALE")
        self.assertEqual(dead["symbols"]["NQM6"]["feed_status"], "DEAD")
        self.assertEqual(still_dead["symbols"]["NQM6"]["feed_status"], "DEAD")
        self.assertEqual(still_dead["symbols"]["NQM6"]["last_tick_timestamp_utc"], tick_time)

    def test_dead_restart_recovered_does_not_make_atr_ready(self):
        self.listener.forward_price_to_executor = lambda *args, **kwargs: None
        self.listener.PRICE_POST_MIN_INTERVAL_SECONDS = 999
        self.listener.DEAD_RESTART_ATTEMPTS["NQM6"] = 2
        self.listener.DEAD_RESTART_LAST_TIMES["NQM6"] = time.monotonic()
        worker = self.listener.TickWorker({})

        worker.process_tick({"timestamp": "2026-04-30T13:31:00Z", "symbol": "NQM6", "price": 19000.0})
        worker.process_tick({"timestamp": "2026-04-30T13:32:00Z", "symbol": "NQM6", "price": 19000.5})
        worker.flush_feed_health(force=True)

        self.assertNotIn("NQM6", self.listener.DEAD_RESTART_ATTEMPTS)
        self.assertNotIn("NQM6", self.listener.DEAD_RESTART_LAST_TIMES)
        atr_payload = (
            json.loads(self.listener.ATR_SNAPSHOT_PATH.read_text(encoding="utf-8"))
            if self.listener.ATR_SNAPSHOT_PATH.exists()
            else {"symbols": {}}
        )
        self.assertNotIn("NQM6", atr_payload.get("symbols", {}))
        self.assertLess(len(worker.bar_cache.get("NQM6", [])), self.listener.ATR_SEED_BAR_COUNT)

    def test_quiet_feed_is_not_trusted_as_live_system_state(self):
        reference_time = self.listener.datetime(2026, 4, 30, 13, 31, 5)
        payload = {
            "symbols": {
                "YMM6": {"last_tick_timestamp_utc": "2026-04-30T13:31:00Z"},
            }
        }

        refreshed = self.listener.refresh_feed_health_statuses(payload, reference_time=reference_time)

        self.assertEqual(refreshed["symbols"]["YMM6"]["feed_status"], "QUIET")
        self.assertEqual(refreshed["system_state_feed"], "STALE")
        self.assertIn("STALE", refreshed["warning"])

    def test_executor_price_409_records_json_reason_instead_of_generic_conflict(self):
        def failing_urlopen(request, timeout):
            raise self._http_error(409, {
                "ok": False,
                "error": "stale_or_invalid_market_data",
                "reason": "stale_tick_timestamp_utc",
                "symbol": "NQM6",
            })

        original_urlopen = self.listener.urllib.request.urlopen
        try:
            self.listener.urllib.request.urlopen = failing_urlopen
            ok, reason = self.listener.forward_price_to_executor(
                "NQM6",
                19000.25,
                tick_timestamp_utc="2026-05-04T05:00:00Z",
            )
        finally:
            self.listener.urllib.request.urlopen = original_urlopen

        payload = json.loads(self.listener.FEED_HEALTH_PATH.read_text(encoding="utf-8"))
        self.assertFalse(ok)
        self.assertEqual(reason, "stale_tick_timestamp_utc")
        self.assertEqual(
            payload["symbols"]["NQM6"]["last_executor_price_post_failure_timestamp_utc"],
            payload["symbols"]["NQ"]["last_executor_price_post_failure_timestamp_utc"],
        )
        self.assertNotIn("last_bridge_post_timestamp_utc", payload["symbols"]["NQM6"])

    def test_failed_price_publisher_post_does_not_set_bridge_post_timestamp(self):
        def failing_forward(symbol, price, update_health=True, tick_timestamp_utc=None, timeout_seconds=None):
            return False, "stale_tick_timestamp_utc"

        original_forward = self.listener.forward_price_to_executor
        try:
            self.listener.forward_price_to_executor = failing_forward
            publisher = self.listener.PricePublisher(["NQM6"])
            self.listener.update_latest_price_from_tick({
                "symbol": "NQM6",
                "price": 19000.25,
                "timestamp": "2026-05-04T05:00:00Z",
            })
            publisher.publish_once()
        finally:
            self.listener.forward_price_to_executor = original_forward

        payload = json.loads(self.listener.FEED_HEALTH_PATH.read_text(encoding="utf-8"))
        entry = payload["symbols"]["NQM6"]
        self.assertEqual(entry["executor_price_post_failure_count"], 1)
        self.assertEqual(entry["last_executor_price_post_failure_reason"], "stale_tick_timestamp_utc")
        self.assertNotIn("last_bridge_post_timestamp_utc", entry)
        self.assertNotIn("last_successful_executor_price_post_timestamp_utc", entry)

    def test_later_successful_price_post_sets_bridge_post_timestamp_after_failure(self):
        results = [(False, "stale_tick_timestamp_utc"), (True, None)]

        def scripted_forward(symbol, price, update_health=True, tick_timestamp_utc=None, timeout_seconds=None):
            return results.pop(0)

        original_forward = self.listener.forward_price_to_executor
        try:
            self.listener.forward_price_to_executor = scripted_forward
            publisher = self.listener.PricePublisher(["NQM6"])
            self.listener.update_latest_price_from_tick({
                "symbol": "NQM6",
                "price": 19000.25,
                "timestamp": "2026-05-04T05:00:00Z",
            })
            publisher.publish_once()
            self.listener.update_latest_price_from_tick({
                "symbol": "NQM6",
                "price": 19000.50,
                "timestamp": "2026-05-04T05:00:01Z",
            })
            publisher.publish_once()
        finally:
            self.listener.forward_price_to_executor = original_forward

        payload = json.loads(self.listener.FEED_HEALTH_PATH.read_text(encoding="utf-8"))
        entry = payload["symbols"]["NQM6"]
        self.assertEqual(entry["executor_price_post_failure_count"], 1)
        self.assertEqual(entry["last_executor_price_post_failure_reason"], "stale_tick_timestamp_utc")
        self.assertIn("last_bridge_post_timestamp_utc", entry)
        self.assertIn("last_successful_executor_price_post_timestamp_utc", entry)

    def test_burst_tick_enqueue_does_not_block_and_drops_safely(self):
        self.listener.TICK_QUEUE_MAX_SIZE = 5
        worker = self.listener.TickWorker({})

        start = time.monotonic()
        for index in range(250):
            worker.enqueue_tick({
                "timestamp": f"2026-04-30T13:31:{index % 60:02d}Z",
                "symbol": "NQM6" if index % 2 == 0 else "RTYM6",
                "price": 19000.0 + index,
            })
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 0.5)
        self.assertLessEqual(worker.events.qsize(), self.listener.TICK_QUEUE_MAX_SIZE)
        self.assertGreater(sum(worker.ticks_dropped.values()) + len(worker.latest_overflow_ticks), 0)

    def test_tick_worker_drains_queue_and_feed_health_stays_live(self):
        self.listener.forward_price_to_executor = lambda *args, **kwargs: None
        self.listener.PRICE_POST_MIN_INTERVAL_SECONDS = 999
        worker = self.listener.TickWorker({})
        worker.start()
        try:
            for index in range(20):
                worker.enqueue_tick({
                    "timestamp": self.listener.utc_now_iso(),
                    "symbol": "NQM6",
                    "price": 19000.0 + index,
                })
            worker.events.join()
            worker.flush_feed_health(force=True)
        finally:
            worker.stop()

        payload = json.loads(self.listener.FEED_HEALTH_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["symbols"]["NQM6"]["feed_status"], "LIVE")
        self.assertEqual(payload["symbols"]["NQ"]["feed_status"], "LIVE")
        self.assertGreaterEqual(worker.ticks_processed["NQM6"], 1)

    def test_tick_worker_builds_completed_minute_bar(self):
        self.listener.forward_price_to_executor = lambda *args, **kwargs: None
        self.listener.PRICE_POST_MIN_INTERVAL_SECONDS = 999
        worker = self.listener.TickWorker({})

        worker.process_tick({"timestamp": "2026-04-30T13:31:00Z", "symbol": "NQM6", "price": 100.0})
        worker.process_tick({"timestamp": "2026-04-30T13:31:30Z", "symbol": "NQM6", "price": 101.0})
        worker.process_tick({"timestamp": "2026-04-30T13:32:00Z", "symbol": "NQM6", "price": 102.0})

        payload = json.loads(self.listener.RECENT_BARS_PATH.read_text(encoding="utf-8"))
        bar = payload["symbols"]["NQM6"][-1]
        self.assertEqual(bar["timestamp"], "2026-04-30T13:31:00Z")
        self.assertEqual(bar["open"], 100.0)
        self.assertEqual(bar["high"], 101.0)
        self.assertEqual(bar["low"], 100.0)
        self.assertEqual(bar["close"], 101.0)

    def test_price_publisher_forwards_original_tick_timestamp(self):
        forwarded = []
        self.listener.forward_price_to_executor = (
            lambda *args, **kwargs: forwarded.append((args, kwargs)) or (True, None)
        )
        publisher = self.listener.PricePublisher(["NQM6"])

        self.listener.update_latest_price_from_tick({
            "timestamp": "2026-04-30T13:31:00Z",
            "symbol": "NQM6",
            "price": 100.0,
        })
        publisher.publish_once()

        self.assertEqual(len(forwarded), 1)
        self.assertEqual(forwarded[0][0], ("NQM6", 100.0))
        self.assertFalse(forwarded[0][1]["update_health"])
        self.assertEqual(forwarded[0][1]["tick_timestamp_utc"], "2026-04-30T13:31:00Z")

    def test_disconnect_watchdog_requests_reconnect_when_all_tracked_symbols_disconnected(self):
        payload = {
            "symbols": {
                "NQM6": {"last_tick_timestamp_utc": "2026-04-30T13:31:00Z"},
            }
        }
        self.listener.write_feed_health(payload)
        fake_process = self._fake_process()

        enabled_event = self.listener.threading.Event()
        stop_event, thread = self.listener.start_disconnect_watchdog(fake_process, ["NQM6"], enabled_event)
        try:
            time.sleep(1.2)
            self.assertFalse(fake_process.terminated)
            enabled_event.set()
            self._wait_for_termination(fake_process)
        finally:
            stop_event.set()
            thread.join(timeout=2)

        self.assertTrue(fake_process.terminated)

    def test_disconnect_watchdog_reconnects_when_all_tracked_symbols_are_stale(self):
        payload = {
            "symbols": {
                "NQM6": {"last_tick_timestamp_utc": self._iso_seconds_ago(5)},
                "YMM6": {"last_tick_timestamp_utc": self._iso_seconds_ago(11)},
            }
        }
        self.listener.write_feed_health(payload)
        fake_process = self._fake_process()

        enabled_event = self.listener.threading.Event()
        stop_event, thread = self.listener.start_disconnect_watchdog(fake_process, ["NQM6", "YMM6"], enabled_event)
        try:
            enabled_event.set()
            self._wait_for_termination(fake_process)
        finally:
            stop_event.set()
            thread.join(timeout=2)

        self.assertFalse(fake_process.terminated)

    def test_disconnect_watchdog_reconnects_when_one_tracked_symbol_disconnects(self):
        payload = {
            "symbols": {
                "NQM6": {"last_tick_timestamp_utc": self._iso_seconds_ago(1)},
                "YMM6": {"last_tick_timestamp_utc": self._iso_seconds_ago(31)},
            }
        }
        self.listener.write_feed_health(payload)
        fake_process = self._fake_process()

        enabled_event = self.listener.threading.Event()
        stop_event, thread = self.listener.start_disconnect_watchdog(fake_process, ["NQM6", "YMM6"], enabled_event)
        try:
            enabled_event.set()
            self._wait_for_termination(fake_process)
        finally:
            stop_event.set()
            thread.join(timeout=2)

        self.assertTrue(fake_process.terminated)

    def test_disconnect_watchdog_reconnects_when_one_symbol_price_bridge_freezes(self):
        payload = {
            "symbols": {
                "NQM6": {
                    "last_tick_timestamp_utc": self._iso_seconds_ago(1),
                    "last_bridge_post_timestamp_utc": self._iso_seconds_ago(1),
                },
                "YMM6": {
                    "last_tick_timestamp_utc": self._iso_seconds_ago(1),
                    "last_bridge_post_timestamp_utc": self._iso_seconds_ago(12),
                },
            }
        }
        self.listener.write_feed_health(payload)
        fake_process = self._fake_process()

        enabled_event = self.listener.threading.Event()
        stop_event, thread = self.listener.start_disconnect_watchdog(fake_process, ["NQM6", "YMM6"], enabled_event)
        try:
            enabled_event.set()
            self._wait_for_termination(fake_process)
        finally:
            stop_event.set()
            thread.join(timeout=2)

        self.assertFalse(fake_process.terminated)

    def test_dead_beyond_threshold_triggers_restart(self):
        reference_time = self.listener.datetime(2026, 4, 30, 13, 31, 30)
        fake_process = self._fake_process()
        health = {
            "feed_status": "DEAD",
            "last_tick_timestamp_utc": "2026-04-30T13:31:00Z",
        }

        restarted = self.listener.maybe_restart_listener("NQM6", health, fake_process, reference_time=reference_time)

        self.assertTrue(restarted)
        self.assertTrue(fake_process.terminated)
        self.assertEqual(self.listener.DEAD_RESTART_ATTEMPTS["NQM6"], 1)

    def test_dead_within_threshold_does_not_restart(self):
        reference_time = self.listener.datetime(2026, 4, 30, 13, 31, 20)
        fake_process = self._fake_process()
        health = {
            "feed_status": "DEAD",
            "last_tick_timestamp_utc": "2026-04-30T13:31:00Z",
        }

        restarted = self.listener.maybe_restart_listener("NQM6", health, fake_process, reference_time=reference_time)

        self.assertFalse(restarted)
        self.assertFalse(fake_process.terminated)
        self.assertEqual(self.listener.DEAD_RESTART_ATTEMPTS["NQM6"], 0)

    def test_stale_does_not_restart(self):
        fake_process = self._fake_process()
        health = {
            "feed_status": "STALE",
            "last_tick_timestamp_utc": "2026-04-30T13:31:00Z",
        }

        restarted = self.listener.maybe_restart_listener(
            "NQM6",
            health,
            fake_process,
            reference_time=self.listener.datetime(2026, 4, 30, 13, 32, 0),
        )

        self.assertFalse(restarted)
        self.assertFalse(fake_process.terminated)

    def test_quiet_does_not_restart(self):
        fake_process = self._fake_process()
        health = {
            "feed_status": "QUIET",
            "last_tick_timestamp_utc": "2026-04-30T13:31:00Z",
        }

        restarted = self.listener.maybe_restart_listener(
            "NQM6",
            health,
            fake_process,
            reference_time=self.listener.datetime(2026, 4, 30, 13, 32, 0),
        )

        self.assertFalse(restarted)
        self.assertFalse(fake_process.terminated)

    def test_invalid_does_not_restart(self):
        fake_process = self._fake_process()
        health = {
            "feed_status": "INVALID",
            "last_tick_timestamp_utc": "2026-04-30T13:31:00Z",
        }

        restarted = self.listener.maybe_restart_listener(
            "NQM6",
            health,
            fake_process,
            reference_time=self.listener.datetime(2026, 4, 30, 13, 32, 0),
        )

        self.assertFalse(restarted)
        self.assertFalse(fake_process.terminated)

    def test_dead_without_prior_tick_does_not_restart_low_volume_symbol(self):
        fake_process = self._fake_process()
        health = {
            "feed_status": "DEAD",
            "last_tick_timestamp_utc": None,
        }

        restarted = self.listener.maybe_restart_listener(
            "YMM6",
            health,
            fake_process,
            reference_time=self.listener.datetime(2026, 4, 30, 13, 32, 0),
        )

        self.assertFalse(restarted)
        self.assertFalse(fake_process.terminated)

    def test_cooldown_blocks_repeated_dead_restart(self):
        fake_process = self._fake_process()
        health = {
            "feed_status": "DEAD",
            "last_tick_timestamp_utc": "2026-04-30T13:31:00Z",
        }
        self.listener.DEAD_RESTART_LAST_TIMES["NQM6"] = time.monotonic()
        self.listener.DEAD_RESTART_ATTEMPTS["NQM6"] = 1

        restarted = self.listener.maybe_restart_listener(
            "NQM6",
            health,
            fake_process,
            reference_time=self.listener.datetime(2026, 4, 30, 13, 32, 0),
        )

        self.assertFalse(restarted)
        self.assertFalse(fake_process.terminated)
        self.assertEqual(self.listener.DEAD_RESTART_ATTEMPTS["NQM6"], 1)

    def test_max_attempts_blocks_dead_restart_loop(self):
        fake_process = self._fake_process()
        health = {
            "feed_status": "DEAD",
            "last_tick_timestamp_utc": "2026-04-30T13:31:00Z",
        }
        self.listener.DEAD_RESTART_ATTEMPTS["NQM6"] = self.listener.MAX_RESTART_ATTEMPTS

        restarted = self.listener.maybe_restart_listener(
            "NQM6",
            health,
            fake_process,
            reference_time=self.listener.datetime(2026, 4, 30, 13, 32, 0),
        )

        self.assertFalse(restarted)
        self.assertFalse(fake_process.terminated)
        self.assertEqual(self.listener.DEAD_RESTART_ATTEMPTS["NQM6"], self.listener.MAX_RESTART_ATTEMPTS)

    def test_recovery_tick_resets_dead_restart_attempts(self):
        self.listener.forward_price_to_executor = lambda *args, **kwargs: None
        self.listener.PRICE_POST_MIN_INTERVAL_SECONDS = 999
        self.listener.DEAD_RESTART_ATTEMPTS["NQM6"] = 2
        self.listener.DEAD_RESTART_LAST_TIMES["NQM6"] = time.monotonic()
        worker = self.listener.TickWorker({})

        worker.process_tick({"timestamp": "2026-04-30T13:31:00Z", "symbol": "NQM6", "price": 100.0})

        self.assertNotIn("NQM6", self.listener.DEAD_RESTART_ATTEMPTS)
        self.assertNotIn("NQM6", self.listener.DEAD_RESTART_LAST_TIMES)


if __name__ == "__main__":
    unittest.main()
