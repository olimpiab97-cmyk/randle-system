import importlib.util
import json
import inspect
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
from pathlib import Path
from unittest import mock


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
        self.listener.FEED_HEALTH_TRANSITIONS_PATH = self.tmp_path / "rithmic_feed_health_transitions.jsonl"
        self.listener.ATR_SHADOW_COMPARISON_PATH = self.tmp_path / "rithmic_atr_shadow_comparison.json"
        self.listener.TRADE_MANAGER_PERSISTENCE_PATH = self.tmp_path / "persistence_state.json"
        self.listener.RAW_TICK_ROOT = self.tmp_path / "rithmic_ticks"
        self.listener.DATA_AUTHORITY_INCIDENTS_PATH = self.tmp_path / "rithmic_data_authority_incidents.jsonl"
        self.listener.BAR_PUBLICATION_LATENCY_PATH = self.tmp_path / "rithmic_bar_publication_latency.jsonl"
        self.listener.ATR_TRANSITION_LATENCY_PATH = self.tmp_path / "rithmic_atr_transition_latency.jsonl"
        self.listener.PRICE_DELIVERY_FAILURES_PATH = self.tmp_path / "rithmic_price_delivery_failures.jsonl"
        self.listener.LOCAL_RUNTIME_DATA_ROOT = self.tmp_path / "local_runtime"
        self.listener.LOCAL_FINALIZED_BAR_JOURNAL_PATH = (
            self.listener.LOCAL_RUNTIME_DATA_ROOT / "rithmic_authoritative" / "finalized_bars.jsonl"
        )
        self.listener._LOCAL_FINALIZED_BAR_JOURNAL_INDEX_PATH = None
        self.listener._LOCAL_FINALIZED_BAR_JOURNAL_BY_ID.clear()
        self.listener.session_bar_path = (
            lambda root_symbol, session_date: self.tmp_path / "rithmic_session_bars" / session_date / f"{root_symbol}_1m.jsonl"
        )
        self.listener.LIVE_TICK_SYMBOLS.clear()
        self.listener.DEAD_RESTART_ATTEMPTS.clear()
        self.listener.DEAD_RESTART_LAST_TIMES.clear()
        self.listener.latest_price_by_symbol.clear()
        self.listener.latest_tick_time_by_symbol.clear()
        self.listener.latest_tick_monotonic_by_symbol.clear()
        self.listener.raw_callback_count.clear()
        self.listener.SUBSCRIPTION_STATE_BY_SYMBOL.clear()
        self.listener.LAST_LOGGED_FEED_TRANSITION_STATE.clear()
        self.listener._RUNTIME_SOURCE_HASHES.clear()
        self.listener.BRIDGE_CONNECTION_HEALTH.update({
            "md_logged_in": True,
            "ts_logged_in": True,
            "market_data_closed": False,
            "trading_system_closed": False,
            "last_heartbeat_timestamp_utc": None,
        })
        self._original_subscriptions_env = os.environ.get(self.listener.RITHMIC_SUBSCRIPTIONS_ENV)
        self._original_secondary_diagnostic_env = os.environ.get(
            self.listener.RITHMIC_SECONDARY_DIAGNOSTIC_SUBSCRIPTION_ENV
        )

    def tearDown(self):
        self.listener.close_local_finalized_bar_journal()
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

    def _delivery_tick(self, symbol, sequence, price, timestamp=None):
        timestamp = timestamp or f"2026-07-14T18:30:{sequence % 60:02d}.000000000Z"
        return {
            "symbol": symbol,
            "exchange": "CME" if symbol.startswith("NQ") else "CBOT",
            "price": float(price),
            "timestamp": timestamp,
            "exchange_timestamp_utc": timestamp,
            "callback_type": "Update",
            "callback_sequence": int(sequence),
            "bridge_generation": 1,
            "callback_receipt_timestamp_utc": timestamp,
            "python_receipt_timestamp_utc": timestamp,
            "python_receipt_monotonic_ns": time.perf_counter_ns(),
            "source_ssboe": 1784053800 + int(sequence),
            "source_nsecs": 0,
            "source_usecs": 0,
        }

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

    def _canonical_tick(
        self,
        source_time,
        sequence,
        price,
        *,
        symbol="NQM6",
        exchange="CME",
        size=1,
        callback_type="Update",
        receipt_time=None,
        generation=0,
    ):
        source_dt = datetime.fromisoformat(str(source_time).replace("Z", "+00:00"))
        receipt_dt = datetime.fromisoformat(str(receipt_time or source_time).replace("Z", "+00:00"))
        source_ssboe = int(source_dt.timestamp())
        source_nsecs = source_dt.microsecond * 1_000
        callback_receipt_unix_ns = int(receipt_dt.timestamp() * self.listener.NANOSECONDS_PER_SECOND)
        return {
            "exchange": exchange,
            "symbol": symbol,
            "price": float(price),
            "size": int(size),
            "callback_type": callback_type,
            "source_ssboe": source_ssboe,
            "source_nsecs": source_nsecs,
            "source_usecs": source_dt.microsecond,
            "rithmic_ssboe": source_ssboe,
            "rithmic_usecs": source_dt.microsecond,
            "jop_ssboe": source_ssboe,
            "jop_nsecs": source_nsecs,
            "callback_receipt_timestamp_utc": receipt_dt.isoformat().replace("+00:00", "Z"),
            "callback_receipt_unix_ns": callback_receipt_unix_ns,
            "callback_receipt_stopwatch_ticks": sequence,
            "python_receipt_timestamp_utc": receipt_dt.isoformat().replace("+00:00", "Z"),
            "python_receipt_monotonic_ns": time.perf_counter_ns(),
            "callback_sequence": int(sequence),
            "bridge_generation": int(generation),
            "condition": "",
            "exchange_order_id": "",
            "aggressor_exchange_order_id": "",
        }

    def _finalized_bar(self, *, timestamp="2026-07-14T14:14:00Z", bar_id="bar-1"):
        minute_start = int(
            datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
            * self.listener.NANOSECONDS_PER_SECOND
        )
        return {
            "session_date": "2026-07-14",
            "root_symbol": "YM",
            "exchange": "CBOT",
            "contract_symbol": "YMU6",
            "symbol": "YMU6",
            "timestamp": timestamp,
            "exchange_minute_start_ns": minute_start,
            "exchange_minute_end_ns": minute_start + self.listener.NANOSECONDS_PER_MINUTE,
            "open": 52854.0,
            "high": 52905.0,
            "low": 52836.0,
            "close": 52905.0,
            "tick_count": 5,
            "tick_stream_sha256": "tick-stream",
            "first_callback_sequence": 1,
            "last_callback_sequence": 5,
            "finalized_by_callback_sequence": 6,
            "transition_callback_receipt_unix_ns": time.time_ns(),
            "transition_python_receipt_monotonic_ns": time.perf_counter_ns(),
            "status": "FINAL",
            "source": "rithmic_live_listener_exchange_time",
            "timestamp_policy": self.listener.RITHMIC_TIMESTAMP_POLICY,
            "builder_contract_version": self.listener.BAR_BUILDER_CONTRACT_VERSION,
            "bar_id": bar_id,
            "recorded_at": self.listener.utc_now_precise_iso(),
        }

    def _authoritative_history(self, *, symbol="YMU6", exchange="CBOT", start=None, count=14):
        start = start or datetime(2026, 7, 14, 13, 30, tzinfo=timezone.utc)
        bars = []
        for index in range(count):
            timestamp = (start + timedelta(minutes=index)).strftime("%Y-%m-%dT%H:%M:00Z")
            bar = self._finalized_bar(timestamp=timestamp, bar_id=f"history-{symbol}-{index}")
            base = 100.0 + index
            bar.update({
                "symbol": symbol,
                "contract_symbol": symbol,
                "root_symbol": "NQ" if symbol.startswith("NQ") else "YM",
                "exchange": exchange,
                "open": base,
                "high": base + (1.0 + (index % 3)),
                "low": base - (0.5 + (index % 2)),
                "close": base + 0.25,
            })
            bars.append(bar)
        return bars

    def test_production_atr_is_wilder_rma14_reference(self):
        bars = self._contiguous_bars(count=24, start_minute=20)
        true_ranges = []
        for index in range(1, len(bars)):
            bar = bars[index]
            previous_close = bars[index - 1]["close"]
            true_ranges.append(max(
                bar["high"] - bar["low"],
                abs(bar["high"] - previous_close),
                abs(bar["low"] - previous_close),
            ))
        expected = sum(true_ranges[:14]) / 14.0
        for true_range in true_ranges[14:]:
            expected = ((expected * 13.0) + true_range) / 14.0
        self.assertAlmostEqual(self.listener.compute_atr(bars), expected, places=12)
        self.assertAlmostEqual(self.listener.compute_rma_atr(bars), expected, places=12)

    def test_canonical_atr_initial_seed_and_first_rma_update_are_exact(self):
        bars = self._authoritative_history(count=15)
        expected_seed = sum(
            self.listener.true_range_for_bar(bars[index], bars[index - 1]["close"])
            for index in range(1, 15)
        ) / 14.0
        seed_record = self.listener.build_canonical_atr_record(bars, bars[-1])
        self.assertTrue(seed_record["ready"])
        self.assertEqual(seed_record["warmup_status"], "ready_initial_seed")
        self.assertIsNone(seed_record["previous_atr"])
        self.assertAlmostEqual(seed_record["updated_raw_atr"], expected_seed, places=12)

        bars[-1]["canonical_atr"] = seed_record
        next_bar = self._finalized_bar(
            timestamp="2026-07-14T13:45:00Z",
            bar_id="history-YMU6-next",
        )
        next_bar.update({
            "symbol": "YMU6",
            "contract_symbol": "YMU6",
            "root_symbol": "YM",
            "exchange": "CBOT",
            "open": 115.0,
            "high": 119.0,
            "low": 113.0,
            "close": 118.0,
        })
        expected_tr = self.listener.true_range_for_bar(next_bar, bars[-1]["close"])
        expected_update = ((expected_seed * 13.0) + expected_tr) / 14.0
        update_record = self.listener.build_canonical_atr_record(bars + [next_bar], next_bar)
        self.assertEqual(update_record["warmup_status"], "ready_continuation")
        self.assertAlmostEqual(update_record["previous_atr"], expected_seed, places=12)
        self.assertAlmostEqual(update_record["updated_raw_atr"], expected_update, places=12)

    def test_transition_tick_is_released_only_after_matching_rma_record_is_exposed(self):
        history = self._authoritative_history(count=14)
        bar_cache = {"YMU6": self.listener.deque(history, maxlen=self.listener.MAX_PERSISTED_BARS)}
        observations = []

        class InspectingPublisher:
            def enqueue_tick(inner_self, tick):
                payload = json.loads(self.listener.RECENT_BARS_PATH.read_text(encoding="utf-8"))
                finalized = payload["symbols"]["YMU6"][-1]
                observations.append({
                    "tick_time": tick["exchange_timestamp_utc"],
                    "bar_id": finalized["bar_id"],
                    "bar_time": finalized["timestamp"],
                    "canonical_atr": finalized.get("canonical_atr"),
                })

        worker = self.listener.TickWorker(bar_cache, price_publisher=InspectingPublisher())
        worker.process_tick(self._canonical_tick("2026-07-14T13:44:00Z", 1, 114.0, symbol="YMU6", exchange="CBOT"))
        worker.process_tick(self._canonical_tick("2026-07-14T13:44:59.900Z", 2, 116.0, symbol="YMU6", exchange="CBOT"))
        worker.process_tick(self._canonical_tick("2026-07-14T13:45:00.200Z", 3, 115.0, symbol="YMU6", exchange="CBOT"))

        transition = observations[-1]
        record = transition["canonical_atr"]
        self.assertEqual(transition["bar_time"], "2026-07-14T13:44:00Z")
        self.assertTrue(record["ready"])
        self.assertEqual(record["bar_id"], transition["bar_id"])
        self.assertEqual(record["last_included_bar"], "2026-07-14T13:44:00Z")
        self.assertEqual(record["formula"], "wilder_rma_14")
        self.assertEqual(record["formula_version"], "wilder_rma_14_v1")
        self.assertIsNotNone(record["atr_record_id"])

        pinned = json.dumps(record, sort_keys=True)
        worker.process_tick(self._canonical_tick("2026-07-14T13:45:30Z", 4, 130.0, symbol="YMU6", exchange="CBOT"))
        latest = json.loads(self.listener.RECENT_BARS_PATH.read_text(encoding="utf-8"))["symbols"]["YMU6"][-1]
        self.assertEqual(json.dumps(latest["canonical_atr"], sort_keys=True), pinned)
        self.assertEqual(worker.ticks_processed["YMU6"], 4)
        self.assertEqual(len(worker.atr_transition_latencies), 1)
        self.assertLess(worker.atr_transition_latencies[0]["total_transition_tick_hold_ms"], 25.0)

    def test_atr_transition_latency_load_target(self):
        history = self._authoritative_history(count=14)
        bar_cache = {"YMU6": self.listener.deque(history, maxlen=self.listener.MAX_PERSISTED_BARS)}

        class NoopReconciler:
            def submit(self, _bar):
                return None

        worker = self.listener.TickWorker(
            bar_cache,
            archive_reconciler=NoopReconciler(),
        )
        worker.publish_atr_mirrors = lambda *args, **kwargs: None
        self.listener.update_latest_price_from_tick = lambda *args, **kwargs: True
        self.listener.write_raw_tick_evidence = lambda *args, **kwargs: None

        start = datetime(2026, 7, 14, 13, 44, tzinfo=timezone.utc)
        for index in range(101):
            timestamp = (start + timedelta(minutes=index, milliseconds=200)).isoformat().replace("+00:00", "Z")
            worker.process_tick(
                self._canonical_tick(
                    timestamp,
                    index + 1,
                    52000.0 + (index % 17),
                    symbol="YMU6",
                    exchange="CBOT",
                )
            )

        self.assertEqual(len(worker.atr_transition_latencies), 100)
        phase_keys = (
            "transition_tick_received_to_prior_bar_finalized_ms",
            "prior_bar_finalized_to_atr_durably_ready_ms",
            "atr_durably_ready_to_transition_tick_released_ms",
            "total_transition_tick_hold_ms",
        )
        report = {
            key: self._latency_stats([
                float(record[key]) for record in worker.atr_transition_latencies
            ])
            for key in phase_keys
        }
        print("RITHMIC TEST|atr_transition_latency|" + json.dumps(report, sort_keys=True))
        self.assertLess(report["total_transition_tick_hold_ms"]["p95"], 10.0)
        self.assertLess(report["total_transition_tick_hold_ms"]["p99"], 25.0)

    @staticmethod
    def _latency_stats(values):
        ordered = sorted(values)
        return {
            "p50": ordered[max(0, int(len(ordered) * 0.50) - 1)],
            "p95": ordered[max(0, int(len(ordered) * 0.95) - 1)],
            "p99": ordered[max(0, int(len(ordered) * 0.99) - 1)],
            "max": ordered[-1],
        }

    def test_build_command_subscribes_only_nq_and_ym_contracts(self):
        self.listener.ensure_runtime_files = lambda: Path(r"C:\fake\rapiplus.dll")
        self.listener.write_powershell_bridge = lambda: Path(r"C:\fake\bridge.ps1")
        self.listener.RITHMIC_USER = "user"
        self.listener.RITHMIC_PASSWORD = "pass"

        command = self.listener.build_command()

        self.assertIn("-Subscriptions", command)
        subscriptions = command[command.index("-Subscriptions") + 1]
        self.assertEqual(subscriptions, "CME:NQU6,CBOT:YMU6")
        self.assertNotIn("NQM6", subscriptions)
        self.assertNotIn("RTY", subscriptions)
        self.assertNotIn("RTYM6", subscriptions)
        self.assertNotIn("YMM6", subscriptions)

    def test_listener_authority_guard_allows_only_one_live_owner(self):
        mutex_name = (
            r"Local\RandleSystem_RithmicLiveListener_Test_"
            f"{os.getpid()}_{time.time_ns()}"
        )
        owner = self.listener.ListenerAuthorityGuard(mutex_name)
        contender = self.listener.ListenerAuthorityGuard(mutex_name)
        successor = self.listener.ListenerAuthorityGuard(mutex_name)
        try:
            self.assertTrue(owner.acquire())
            self.assertFalse(contender.acquire())
            owner.release()
            self.assertTrue(successor.acquire())
        finally:
            contender.release()
            successor.release()
            owner.release()

    def test_second_listener_launch_exits_before_service_or_bridge_start(self):
        authority = mock.Mock()
        authority.name = r"Local\RandleSystem_RithmicLiveListener_Test_Owned"
        authority.acquire.return_value = False
        output = StringIO()

        with mock.patch.object(self.listener, "ListenerAuthorityGuard", return_value=authority), mock.patch.object(
            self.listener,
            "run_listener_service",
        ) as run_service, redirect_stdout(output):
            result = self.listener.main()

        self.assertFalse(result)
        run_service.assert_not_called()
        authority.release.assert_not_called()
        self.assertIn("listener_authority_already_owned", output.getvalue())
        self.assertIn("bridge_started=false", output.getvalue())
        self.assertIn("subscriptions_created=false", output.getvalue())

    def test_official_startup_waits_for_executor_and_checks_authority_mutex(self):
        source = (ROOT / "launch_all.ps1").read_text(encoding="utf-8")

        self.assertIn("Invoke-RestMethod -Uri $ExecutorHealthUrl", source)
        self.assertIn("Wait-ExecutorHealthy", source)
        self.assertIn("[System.Threading.Mutex]::OpenExisting($ListenerAuthorityMutexName)", source)
        self.assertIn("Test-ListenerAuthorityHealthy", source)
        self.assertIn("Healthy active Rithmic listener already owns authority", source)
        health_confirmation = source.index("if (-not (Wait-ExecutorHealthy))")
        listener_start = source.index('Start-RandleWindow "Randle Rithmic Listener"')
        self.assertLess(health_confirmation, listener_start)

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

    def test_retired_rty_diagnostic_override_is_rejected(self):
        os.environ[self.listener.RITHMIC_SECONDARY_DIAGNOSTIC_SUBSCRIPTION_ENV] = "CME:RTY"

        with self.assertRaisesRegex(ValueError, "is retired"):
            self.listener.parse_rithmic_subscriptions()

    def test_explicit_rty_live_subscription_is_rejected(self):
        os.environ[self.listener.RITHMIC_SUBSCRIPTIONS_ENV] = "CME:NQU6,CME:RTYU6,CBOT:YMU6"

        with self.assertRaisesRegex(ValueError, "unsupported live roots: RTY"):
            self.listener.parse_rithmic_subscriptions()

    def test_explicit_live_subscriptions_must_include_both_nq_and_ym(self):
        os.environ[self.listener.RITHMIC_SUBSCRIPTIONS_ENV] = "CME:NQU6"

        with self.assertRaisesRegex(ValueError, "exactly the active roots NQ,YM"):
            self.listener.parse_rithmic_subscriptions()

    def test_live_default_subscriptions_never_use_stale_expired_m_contracts_after_rollover(self):
        subscriptions = self.listener.parse_rithmic_subscriptions()

        self.assertEqual(subscriptions, [("CME", "NQU6"), ("CBOT", "YMU6")])
        self.assertTrue(all(symbol not in {"NQM6", "RTYM6", "YMM6"} for _, symbol in subscriptions))

    def test_startup_prunes_rty_from_mutable_live_projections_only(self):
        nq_bar = {"timestamp": "2026-07-14T17:00:00Z", "symbol": "NQU6", "open": 1, "high": 2, "low": 1, "close": 2}
        rty_bar = {"timestamp": "2026-07-14T17:00:00Z", "symbol": "RTYU6", "open": 3, "high": 4, "low": 3, "close": 4}
        bar_cache = {
            "NQU6": self.listener.deque([nq_bar], maxlen=self.listener.MAX_PERSISTED_BARS),
            "RTYU6": self.listener.deque([rty_bar], maxlen=self.listener.MAX_PERSISTED_BARS),
        }
        for path in (self.listener.ATR_SNAPSHOT_PATH, self.listener.ATR_SHADOW_COMPARISON_PATH):
            path.write_text(json.dumps({"symbols": {"NQ": {"value": 1}, "RTY": {"value": 2}, "RTYU6": {"value": 2}}}), encoding="utf-8")
        self.listener.FEED_HEALTH_PATH.write_text(json.dumps({
            "symbols": {"NQ": {"resolved_contract": "NQU6"}, "RTY": {"resolved_contract": "RTYU6"}, "RTYU6": {"resolved_contract": "RTYU6"}},
            "frozen_price_symbols": ["NQU6", "RTYU6"],
            "listener_runtime": {"subscribed_contracts": [
                {"exchange": "CME", "contract_symbol": "NQU6"},
                {"exchange": "CME", "contract_symbol": "RTYU6"},
            ]},
        }), encoding="utf-8")

        removed = self.listener.prune_retired_live_runtime_state(bar_cache)

        self.assertEqual(removed["recent_bars"], ["RTYU6"])
        self.assertEqual(set(bar_cache), {"NQU6"})
        recent = json.loads(self.listener.RECENT_BARS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(set(recent["symbols"]), {"NQU6"})
        for path in (self.listener.ATR_SNAPSHOT_PATH, self.listener.ATR_SHADOW_COMPARISON_PATH):
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(payload["symbols"]), {"NQ"})
        health = json.loads(self.listener.FEED_HEALTH_PATH.read_text(encoding="utf-8"))
        self.assertEqual(set(health["symbols"]), {"NQ"})
        self.assertNotIn("RTYU6", health["frozen_price_symbols"])
        self.assertEqual(
            health["listener_runtime"]["subscribed_contracts"],
            [{"exchange": "CME", "contract_symbol": "NQU6"}],
        )

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

    def test_atomic_replace_retries_transient_permission_error_without_sleep(self):
        target = self.tmp_path / "atomic.json"
        real_replace = os.replace
        attempts = []

        def transient_replace(source, destination):
            attempts.append((source, destination))
            if len(attempts) == 1:
                raise PermissionError("simulated sharing violation")
            return real_replace(source, destination)

        with mock.patch.object(self.listener.os, "replace", side_effect=transient_replace):
            self.listener.atomic_write_json(target, {"ok": True}, durable=False)

        self.assertEqual(len(attempts), 2)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"ok": True})

    def test_failed_recent_cache_replace_rolls_back_unpublished_in_memory_bar(self):
        bar_cache = {}
        bar = {
            "session_date": "2026-07-14",
            "root_symbol": "YM",
            "exchange": "CBOT",
            "contract_symbol": "YMU6",
            "timestamp": "2026-07-14T17:00:00Z",
            "symbol": "YMU6",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "status": "FINAL",
            "source": "rithmic_live_listener_exchange_time",
            "bar_id": "test-finalized-bar-id",
        }

        with mock.patch.object(self.listener, "persist_recent_bars", side_effect=PermissionError("locked")):
            with self.assertRaises(self.listener.FinalizedBarExposureError):
                self.listener.update_recent_bars(bar_cache, bar)

        self.assertNotIn("YMU6", bar_cache)
        self.assertFalse(self.listener.RECENT_BARS_PATH.exists())
        journal_records = self.listener.load_local_finalized_bar_journal()
        self.assertEqual(journal_records, [bar])

    def test_post_publication_atr_failure_does_not_retract_finalized_bar(self):
        bar_cache = {}
        bar = {
            "session_date": "2026-07-14",
            "root_symbol": "YM",
            "exchange": "CBOT",
            "contract_symbol": "YMU6",
            "timestamp": "2026-07-14T17:00:00Z",
            "symbol": "YMU6",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "status": "FINAL",
            "source": "rithmic_live_listener_exchange_time",
            "bar_id": "test-finalized-bar-id",
        }

        with mock.patch.object(self.listener, "write_atr_snapshot", side_effect=PermissionError("locked")):
            _, _, _, publication = self.listener.update_recent_bars(bar_cache, bar)

        self.assertIn("atr_error", publication)
        cached = json.loads(self.listener.RECENT_BARS_PATH.read_text(encoding="utf-8"))["symbols"]["YMU6"][-1]
        self.assertEqual(cached, bar)
        journaled = json.loads(
            self.listener.LOCAL_FINALIZED_BAR_JOURNAL_PATH.read_text(encoding="utf-8").splitlines()[-1]
        )
        self.assertEqual(cached, journaled)

    def test_finalized_bar_is_fsynced_locally_before_entry_agent_cache_exposure(self):
        bar = self._finalized_bar()
        bar_cache = {}
        events = []
        real_fsync = self.listener.os.fsync
        real_persist = self.listener.persist_recent_bars

        def observed_fsync(file_descriptor):
            events.append("fsync")
            if "cache_exposure" not in events:
                self.assertFalse(self.listener.RECENT_BARS_PATH.exists())
            return real_fsync(file_descriptor)

        def observed_persist(cache):
            events.append("cache_exposure")
            journaled = self.listener.load_local_finalized_bar_journal()
            self.assertEqual(journaled, [bar])
            return real_persist(cache)

        with mock.patch.object(self.listener.os, "fsync", side_effect=observed_fsync):
            with mock.patch.object(self.listener, "persist_recent_bars", side_effect=observed_persist):
                self.listener.update_recent_bars(bar_cache, bar)

        self.assertLess(events.index("fsync"), events.index("cache_exposure"))
        cached = json.loads(self.listener.RECENT_BARS_PATH.read_text(encoding="utf-8"))["symbols"]["YMU6"][-1]
        self.assertEqual(cached, bar)

    def test_local_journal_fsync_failure_preserves_prior_cache_and_records_fail_closed_incident(self):
        prior = self._finalized_bar(timestamp="2026-07-14T14:13:00Z", bar_id="prior")
        bar_cache = {"YMU6": self.listener.deque([prior], maxlen=self.listener.MAX_PERSISTED_BARS)}
        self.listener.persist_recent_bars(bar_cache)
        before = self.listener.RECENT_BARS_PATH.read_bytes()
        worker = self.listener.TickWorker(bar_cache)

        with mock.patch.object(
            self.listener,
            "commit_finalized_bar_to_local_journal",
            side_effect=self.listener.FinalizedBarLocalCommitError("fsync failed"),
        ):
            published = worker.process_completed_bar(self._finalized_bar(), source="test")

        self.assertFalse(published)
        self.assertEqual(self.listener.RECENT_BARS_PATH.read_bytes(), before)
        self.assertEqual(list(bar_cache["YMU6"]), [prior])
        self.assertTrue(any(
            incident["incident_type"] == "finalized_bar_local_commit_failed_before_publication"
            for incident in worker.authority_incidents
        ))

    def test_actual_local_journal_fsync_error_cannot_expose_bar(self):
        bar = self._finalized_bar()
        with mock.patch.object(self.listener.os, "fsync", side_effect=OSError("disk flush failed")):
            with self.assertRaises(self.listener.FinalizedBarLocalCommitError):
                self.listener.update_recent_bars({}, bar)

        self.assertFalse(self.listener.RECENT_BARS_PATH.exists())
        if self.listener.LOCAL_FINALIZED_BAR_JOURNAL_PATH.exists():
            self.assertEqual(self.listener.LOCAL_FINALIZED_BAR_JOURNAL_PATH.read_bytes(), b"")

    def test_cache_failure_after_local_commit_leaves_one_durable_unexposed_bar(self):
        bar = self._finalized_bar()
        bar_cache = {}
        with mock.patch.object(self.listener, "persist_recent_bars", side_effect=PermissionError("locked")):
            with self.assertRaises(self.listener.FinalizedBarExposureError) as raised:
                self.listener.update_recent_bars(bar_cache, bar)

        self.assertEqual(raised.exception.local_commit["local_journal_path"], str(self.listener.LOCAL_FINALIZED_BAR_JOURNAL_PATH.resolve()))
        self.assertEqual(self.listener.load_local_finalized_bar_journal(), [bar])
        self.assertFalse(self.listener.RECENT_BARS_PATH.exists())
        self.assertNotIn("YMU6", bar_cache)

    def test_cache_publication_retry_reuses_bar_id_without_duplicate_journal_record(self):
        bar = self._finalized_bar()
        real_persist = self.listener.persist_recent_bars
        attempts = 0

        def fail_once(cache):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise PermissionError("locked once")
            return real_persist(cache)

        worker = self.listener.TickWorker({})
        with mock.patch.object(self.listener, "persist_recent_bars", side_effect=fail_once):
            published = worker.process_completed_bar(bar, source="test")

        self.assertTrue(published)
        self.assertEqual(attempts, 2)
        journal_records = self.listener.load_local_finalized_bar_journal()
        self.assertEqual(len(journal_records), 1)
        self.assertEqual(journal_records[0]["bar_id"], bar["bar_id"])
        cached = json.loads(self.listener.RECENT_BARS_PATH.read_text(encoding="utf-8"))["symbols"]["YMU6"][-1]
        self.assertEqual(cached, journal_records[0])
        self.assertTrue(any(
            incident["incident_type"] == "finalized_bar_committed_but_not_exposed"
            for incident in worker.authority_incidents
        ))
        worker.archive_reconciler.wait_for_idle()
        worker.archive_reconciler.stop()

    def test_downstream_archive_failure_does_not_block_or_alter_published_bar(self):
        bar = self._finalized_bar()
        attempts = []

        def failing_archive(completed_bar):
            attempts.append(completed_bar["bar_id"])
            raise OSError("replica unavailable")

        reconciler = self.listener.SessionArchiveReconciler(append_function=failing_archive)
        worker = self.listener.TickWorker({}, archive_reconciler=reconciler)
        published = worker.process_completed_bar(bar, source="test")
        reconciler.wait_for_idle()

        self.assertTrue(published)
        self.assertEqual(attempts, [bar["bar_id"]])
        self.assertEqual(self.listener.load_local_finalized_bar_journal(), [bar])
        cached = json.loads(self.listener.RECENT_BARS_PATH.read_text(encoding="utf-8"))["symbols"]["YMU6"][-1]
        self.assertEqual(cached, bar)
        self.assertFalse(self.listener.session_bar_path("YM", "2026-07-14").exists())
        self.assertTrue(any(
            incident["incident_type"] == "finalized_bar_archive_reconciliation_failed"
            for incident in reconciler.incidents
        ))
        reconciler.append_function = self.listener.append_session_bar_record
        reconciler.submit(bar)
        reconciler.wait_for_idle()
        archived_lines = self.listener.session_bar_path("YM", "2026-07-14").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(archived_lines), 1)
        self.assertEqual(json.loads(archived_lines[0]), bar)
        reconciler.stop()

    def test_crash_recovery_reconciles_but_never_exposes_stale_committed_bar(self):
        bar = self._finalized_bar()
        self.listener.commit_finalized_bar_to_local_journal(bar)
        submitted = []

        class CollectingReconciler:
            def submit(self, completed_bar):
                submitted.append(completed_bar)

        empty_cache = {}
        recovery = self.listener.recover_local_finalized_bar_journal(empty_cache, CollectingReconciler())

        self.assertEqual(recovery["committed_but_unexposed_count"], 1)
        self.assertEqual(submitted, [bar])
        self.assertEqual(empty_cache, {})
        self.assertFalse(self.listener.RECENT_BARS_PATH.exists())
        incidents = [
            json.loads(line)
            for line in self.listener.DATA_AUTHORITY_INCIDENTS_PATH.read_text(encoding="utf-8").splitlines()
        ]
        recovered = [
            incident for incident in incidents
            if incident["incident_type"] == "finalized_bar_committed_but_not_exposed_recovery"
        ]
        self.assertEqual(len(recovered), 1)
        self.assertFalse(recovered[0]["live_cache_exposure"])

    def test_journal_cache_and_reconciled_archive_have_identical_bar_and_bar_id(self):
        bar = self._finalized_bar()
        bar_cache = {}
        self.listener.update_recent_bars(bar_cache, bar)
        reconciler = self.listener.SessionArchiveReconciler()
        reconciler.submit(bar)
        reconciler.wait_for_idle()

        journaled = self.listener.load_local_finalized_bar_journal()[0]
        cached = json.loads(self.listener.RECENT_BARS_PATH.read_text(encoding="utf-8"))["symbols"]["YMU6"][-1]
        archived = json.loads(
            self.listener.session_bar_path("YM", "2026-07-14").read_text(encoding="utf-8").splitlines()[-1]
        )
        self.assertEqual(journaled, cached)
        self.assertEqual(cached, archived)
        self.assertEqual({journaled["bar_id"], cached["bar_id"], archived["bar_id"]}, {bar["bar_id"]})
        reconciler.stop()

    def test_authoritative_journal_uses_local_runtime_root_not_synchronized_data_root(self):
        production_root = self.listener.resolve_local_durable_runtime_root().resolve()
        production_path = (
            production_root / "rithmic_authoritative" / "finalized_bars.jsonl"
        ).resolve()

        self.assertTrue(production_path.is_relative_to(production_root))
        self.assertNotIn("onedrive", str(production_path).lower())
        self.assertNotEqual(production_root, self.listener.get_data_root().resolve())

    def test_session_archive_is_absent_from_pre_decision_publication_function(self):
        source = inspect.getsource(self.listener.update_recent_bars)
        self.assertIn("commit_finalized_bar_to_local_journal", source)
        self.assertIn("persist_recent_bars", source)
        self.assertLess(
            source.index("commit_finalized_bar_to_local_journal"),
            source.index("persist_recent_bars"),
        )
        self.assertNotIn("append_session_bar_record", source)
        self.assertNotIn("sleep", source.lower())

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
        self.assertIn("Interlocked.Increment(ref CallbackSequence)", callback_source)
        self.assertIn("SourceSsboe = info.SourceSsboe", callback_source)
        self.assertIn("SourceNsecs = info.SourceNsecs", callback_source)
        self.assertIn("SourceUsecs = info.SourceUsecs", callback_source)
        self.assertIn("CallbackReceiptUtc = callbackReceiptUtc", callback_source)
        self.assertIn("EnqueueTick(tick);", callback_source)
        self.assertNotIn("Console.WriteLine", callback_source)
        self.assertNotIn("PrintTick", callback_source)
        self.assertNotIn("Url", callback_source)
        self.assertNotIn("Request", callback_source)
        self.assertNotIn("json", callback_source.lower())

    def test_canonical_bridge_queue_is_lossless_and_has_no_coalescing(self):
        bridge_source = self.listener.build_powershell_bridge()

        self.assertIn("new BlockingCollection<TickEvent>()", bridge_source)
        self.assertIn("TickQueue.Add(tick)", bridge_source)
        self.assertIn("FlushContiguousTicks", bridge_source)
        self.assertNotIn("CoalescedTicks", bridge_source)
        self.assertNotIn("TryAdd(tick)", bridge_source)
        self.assertNotIn("MaxTickQueueSize", bridge_source)

    def test_listener_stall_marks_feed_stale_after_relaxed_threshold(self):
        reference_time = self.listener.datetime(2026, 4, 30, 13, 31, 31)
        entry = {"last_tick_timestamp_utc": "2026-04-30T13:31:00Z"}

        status = self.listener.calculate_feed_status(entry, reference_time=reference_time)

        self.assertEqual(status, "STALE")

    def test_two_to_three_second_quiet_does_not_become_stale(self):
        entry = {"last_tick_timestamp_utc": "2026-04-30T13:31:00Z"}

        two_second_status = self.listener.calculate_feed_status(
            entry,
            reference_time=self.listener.datetime(2026, 4, 30, 13, 31, 2),
            symbol="NQM6",
        )
        three_second_status = self.listener.calculate_feed_status(
            entry,
            reference_time=self.listener.datetime(2026, 4, 30, 13, 31, 3),
            symbol="NQM6",
        )

        self.assertNotEqual(two_second_status, "STALE")
        self.assertNotEqual(three_second_status, "STALE")

    def test_ym_and_rty_activity_can_be_quiet_while_feed_remains_live(self):
        reference_time = self.listener.datetime(2026, 4, 30, 13, 31, 16)
        entry = {"last_tick_timestamp_utc": "2026-04-30T13:31:00Z"}

        self.assertEqual(
            self.listener.calculate_feed_status(entry, reference_time=reference_time, symbol="YMM6"),
            "LIVE",
        )
        self.assertEqual(
            self.listener.calculate_feed_status(entry, reference_time=reference_time, symbol="RTYM6"),
            "LIVE",
        )
        self.assertEqual(self.listener.calculate_activity_status(entry, reference_time=reference_time), "QUIET")

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
        worker = self.listener.TickWorker({})
        first_source_time = self.listener.utc_now_iso()
        worker.process_tick(self._canonical_tick(first_source_time, 1, 19000.0))
        worker.flush_feed_health(force=True)
        second_source_time = self.listener.utc_now_iso()
        worker.process_tick(self._canonical_tick(second_source_time, 2, 19000.25))
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

    def test_price_sanity_warning_does_not_remove_canonical_trade(self):
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
        worker = self.listener.TickWorker({})
        worker.latest_prices["NQM6"] = 19000.0

        worker.process_tick(self._canonical_tick("2026-04-30T13:31:30Z", 1, 50000.0))
        worker.flush_feed_health(force=True)
        payload = json.loads(self.listener.FEED_HEALTH_PATH.read_text(encoding="utf-8"))
        self.assertTrue(payload["symbols"]["NQM6"]["last_tick_timestamp_utc"].startswith("2026-04-30T13:31:30"))
        self.assertEqual(worker.ticks_processed["NQM6"], 1)

        worker.process_tick(self._canonical_tick(accepted_tick, 2, 19000.25))
        worker.flush_feed_health(force=True)
        payload = json.loads(self.listener.FEED_HEALTH_PATH.read_text(encoding="utf-8"))
        self.assertTrue(payload["symbols"]["NQM6"]["last_tick_timestamp_utc"].startswith("2026-04-30T13:32:00"))

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
        quiet_activity = self.listener.refresh_feed_health_statuses(
            json.loads(json.dumps(live)),
            reference_time=self.listener.datetime(2026, 4, 30, 13, 31, 16),
        )
        stale = self.listener.refresh_feed_health_statuses(
            json.loads(json.dumps(quiet_activity)),
            reference_time=self.listener.datetime(2026, 4, 30, 13, 31, 31),
        )
        dead = self.listener.refresh_feed_health_statuses(
            json.loads(json.dumps(stale)),
            reference_time=self.listener.datetime(2026, 4, 30, 13, 32, 31),
        )
        still_dead = self.listener.refresh_feed_health_statuses(
            json.loads(json.dumps(dead)),
            reference_time=self.listener.datetime(2026, 4, 30, 13, 32, 40),
        )

        self.assertEqual(live["symbols"]["NQM6"]["feed_status"], "LIVE")
        self.assertEqual(quiet_activity["symbols"]["NQM6"]["feed_status"], "LIVE")
        self.assertEqual(quiet_activity["symbols"]["NQM6"]["activity_status"], "QUIET")
        self.assertEqual(stale["symbols"]["NQM6"]["feed_status"], "STALE")
        self.assertEqual(dead["symbols"]["NQM6"]["feed_status"], "DEAD")
        self.assertEqual(still_dead["symbols"]["NQM6"]["feed_status"], "DEAD")
        self.assertEqual(still_dead["symbols"]["NQM6"]["last_tick_timestamp_utc"], tick_time)

    def test_dead_restart_recovered_does_not_make_atr_ready(self):
        self.listener.forward_price_to_executor = lambda *args, **kwargs: None
        self.listener.DEAD_RESTART_ATTEMPTS["NQM6"] = 2
        self.listener.DEAD_RESTART_LAST_TIMES["NQM6"] = time.monotonic()
        worker = self.listener.TickWorker({})

        worker.process_tick(self._canonical_tick("2026-04-30T13:31:00Z", 1, 19000.0))
        worker.process_tick(self._canonical_tick("2026-04-30T13:32:00Z", 2, 19000.5))
        worker.flush_feed_health(force=True)

        self.assertNotIn("NQM6", self.listener.DEAD_RESTART_ATTEMPTS)
        self.assertNotIn("NQM6", self.listener.DEAD_RESTART_LAST_TIMES)
        atr_payload = (
            json.loads(self.listener.ATR_SNAPSHOT_PATH.read_text(encoding="utf-8"))
            if self.listener.ATR_SNAPSHOT_PATH.exists()
            else {"symbols": {}}
        )
        self.assertFalse(atr_payload.get("symbols", {}).get("NQM6", {}).get("ready"))
        self.assertLess(len(worker.bar_cache.get("NQM6", [])), self.listener.ATR_SEED_BAR_COUNT)

    def test_quiet_activity_does_not_degrade_live_system_state(self):
        reference_time = self.listener.datetime(2026, 4, 30, 13, 31, 16)
        payload = {
            "symbols": {
                "YMM6": {"last_tick_timestamp_utc": "2026-04-30T13:31:00Z"},
            }
        }

        refreshed = self.listener.refresh_feed_health_statuses(payload, reference_time=reference_time)

        self.assertEqual(refreshed["symbols"]["YMM6"]["feed_status"], "LIVE")
        self.assertEqual(refreshed["symbols"]["YMM6"]["activity_status"], "QUIET")
        self.assertEqual(refreshed["system_state_feed"], "LIVE")
        self.assertIsNone(refreshed["warning"])

    def test_phase1_feed_and_activity_thresholds_are_independent(self):
        entry = {"last_tick_timestamp_utc": "2026-04-30T13:31:00Z"}

        at_fifteen = self.listener.datetime(2026, 4, 30, 13, 31, 15)
        after_fifteen = self.listener.datetime(2026, 4, 30, 13, 31, 16)
        at_thirty = self.listener.datetime(2026, 4, 30, 13, 31, 30)
        after_thirty = self.listener.datetime(2026, 4, 30, 13, 31, 31)
        at_ninety = self.listener.datetime(2026, 4, 30, 13, 32, 30)
        after_ninety = self.listener.datetime(2026, 4, 30, 13, 32, 31)

        self.assertEqual(self.listener.calculate_activity_status(entry, at_fifteen), "ACTIVE")
        self.assertEqual(self.listener.calculate_activity_status(entry, after_fifteen), "QUIET")
        self.assertEqual(self.listener.calculate_feed_status(entry, at_thirty), "LIVE")
        self.assertEqual(self.listener.calculate_feed_status(entry, after_thirty), "STALE")
        self.assertEqual(self.listener.calculate_feed_status(entry, at_ninety), "STALE")
        self.assertEqual(self.listener.calculate_feed_status(entry, after_ninety), "DEAD")

    def test_explicit_disconnect_and_invalid_data_remain_blocking_feed_states(self):
        entry = {"last_tick_timestamp_utc": "2026-04-30T13:31:00Z"}
        reference_time = self.listener.datetime(2026, 4, 30, 13, 31, 1)

        self.assertEqual(
            self.listener.calculate_feed_status({**entry, "connection_state": "DISCONNECTED"}, reference_time),
            "DISCONNECTED",
        )
        self.assertEqual(
            self.listener.calculate_feed_status({**entry, "subscription_state": "FAILED"}, reference_time),
            "DISCONNECTED",
        )
        self.assertEqual(
            self.listener.calculate_feed_status({**entry, "price_sanity_status": "INVALID_PRICE"}, reference_time),
            "INVALID",
        )
        self.assertEqual(
            self.listener.calculate_feed_status({"last_tick_timestamp_utc": "not-a-time"}, reference_time),
            "INVALID",
        )

    def test_bridge_login_and_subscription_events_drive_explicit_connection_state(self):
        self.listener.update_bridge_connection_health_from_line(
            "STATUS|subscription_call_returned|CME|NQM6|flags=Prints"
        )
        self.assertEqual(self.listener.SUBSCRIPTION_STATE_BY_SYMBOL["NQM6"], "ACTIVE")

        self.listener.update_bridge_connection_health_from_line("STATUS|market_data_connection_closed_unexpected")
        payload = {
            "symbols": {
                "NQM6": {
                    "resolved_contract": "NQM6",
                    "last_tick_timestamp_utc": "2026-04-30T13:31:00Z",
                }
            }
        }
        refreshed = self.listener.refresh_feed_health_statuses(payload)
        self.assertEqual(refreshed["symbols"]["NQM6"]["feed_status"], "DISCONNECTED")
        self.assertEqual(refreshed["symbols"]["NQM6"]["subscription_state"], "ACTIVE")

        self.listener.update_bridge_connection_health_from_line("STATUS|market_data_login_complete")
        refreshed = self.listener.refresh_feed_health_statuses(
            payload,
            reference_time=self.listener.datetime(2026, 4, 30, 13, 31, 1),
        )
        self.assertEqual(refreshed["symbols"]["NQM6"]["connection_state"], "CONNECTED")

    def test_transition_log_writes_only_meaningful_state_changes(self):
        self.listener.SUBSCRIPTION_STATE_BY_SYMBOL["NQM6"] = "ACTIVE"
        self.listener.BRIDGE_CONNECTION_HEALTH["last_heartbeat_timestamp_utc"] = "2026-04-30T13:31:15Z"
        payload = {
            "symbols": {
                "NQM6": {
                    "resolved_contract": "NQM6",
                    "feed_status": "LIVE",
                    "activity_status": "ACTIVE",
                    "last_tick_timestamp_utc": "2026-04-30T13:31:00Z",
                    "recovery_tick_confirmations": self.listener.FEED_RECOVERY_TICK_CONFIRMATIONS,
                }
            }
        }

        self.listener.refresh_feed_health_statuses(
            payload,
            reference_time=self.listener.datetime(2026, 4, 30, 13, 31, 10),
        )
        self.assertFalse(self.listener.FEED_HEALTH_TRANSITIONS_PATH.exists())

        self.listener.refresh_feed_health_statuses(
            payload,
            reference_time=self.listener.datetime(2026, 4, 30, 13, 31, 16),
        )
        duplicate_stale_read = {
            "symbols": {
                "NQM6": {
                    "resolved_contract": "NQM6",
                    "feed_status": "LIVE",
                    "activity_status": "ACTIVE",
                    "last_tick_timestamp_utc": "2026-04-30T13:31:00Z",
                    "recovery_tick_confirmations": self.listener.FEED_RECOVERY_TICK_CONFIRMATIONS,
                }
            }
        }
        self.listener.refresh_feed_health_statuses(
            duplicate_stale_read,
            reference_time=self.listener.datetime(2026, 4, 30, 13, 31, 16),
        )
        self.listener.refresh_feed_health_statuses(
            payload,
            reference_time=self.listener.datetime(2026, 4, 30, 13, 31, 20),
        )
        self.listener.refresh_feed_health_statuses(
            payload,
            reference_time=self.listener.datetime(2026, 4, 30, 13, 31, 31),
        )

        records = [
            json.loads(line)
            for line in self.listener.FEED_HEALTH_TRANSITIONS_PATH.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["previous_activity_status"], "ACTIVE")
        self.assertEqual(records[0]["new_activity_status"], "QUIET")
        self.assertEqual(records[0]["previous_feed_status"], "LIVE")
        self.assertEqual(records[0]["new_feed_status"], "LIVE")
        self.assertEqual(records[1]["previous_feed_status"], "LIVE")
        self.assertEqual(records[1]["new_feed_status"], "STALE")
        self.assertEqual(records[1]["symbol"], "NQ")
        self.assertEqual(records[1]["resolved_contract"], "NQM6")
        self.assertIn("No accepted market-data event", records[1]["reason"])

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
        def failing_forward(symbol, price, update_health=True, tick_timestamp_utc=None, timeout_seconds=None, **kwargs):
            return False, "stale_tick_timestamp_utc"

        original_forward = self.listener.forward_price_to_executor
        try:
            self.listener.forward_price_to_executor = failing_forward
            publisher = self.listener.PricePublisher(["NQM6"])
            self.listener.update_latest_price_from_tick({
                "symbol": "NQM6",
                "price": 19000.25,
                "timestamp": "2026-05-04T05:00:00Z",
            }, price_publisher=publisher)
            publisher.publish_once()
        finally:
            self.listener.forward_price_to_executor = original_forward

        payload = json.loads(self.listener.FEED_HEALTH_PATH.read_text(encoding="utf-8"))
        entry = payload["symbols"]["NQM6"]
        self.assertEqual(entry["executor_price_post_failure_count"], 1)
        self.assertEqual(entry["last_executor_price_post_failure_reason"], "stale_tick_timestamp_utc")
        self.assertNotIn("last_bridge_post_timestamp_utc", entry)
        self.assertNotIn("last_successful_executor_price_post_timestamp_utc", entry)

    def test_fresh_price_publisher_tick_with_missing_cached_feed_status_posts_live(self):
        captured_payloads = []

        class SuccessfulResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def fake_urlopen(request, timeout):
            payload = json.loads(request.data.decode("utf-8"))
            captured_payloads.append(payload)
            if not payload.get("feed_status"):
                raise self._http_error(409, {
                    "ok": False,
                    "error": "missing_feed_status",
                    "reason": "missing_feed_status",
                    "symbol": payload.get("symbol"),
                })
            return SuccessfulResponse()

        original_urlopen = self.listener.urllib.request.urlopen
        try:
            self.listener.urllib.request.urlopen = fake_urlopen
            publisher = self.listener.PricePublisher(["NQM6"])
            self.listener.update_latest_price_from_tick({
                "symbol": "NQM6",
                "price": 19000.25,
                "timestamp": self.listener.utc_now_iso(),
            }, price_publisher=publisher)
            publisher.publish_once()
        finally:
            self.listener.urllib.request.urlopen = original_urlopen

        payload = json.loads(self.listener.FEED_HEALTH_PATH.read_text(encoding="utf-8"))
        entry = payload["symbols"]["NQM6"]
        self.assertEqual(captured_payloads[0]["feed_status"], "LIVE")
        self.assertNotEqual(entry.get("last_executor_price_post_failure_reason"), "missing_feed_status")
        self.assertIn("last_successful_executor_price_post_timestamp_utc", entry)
        self.assertIn("last_bridge_post_timestamp_utc", entry)
        self.assertEqual(entry["last_bridge_post_age_seconds"], 0.0)

    def test_later_successful_price_post_sets_bridge_post_timestamp_after_failure(self):
        results = [(False, "stale_tick_timestamp_utc"), (True, None)]

        def scripted_forward(symbol, price, update_health=True, tick_timestamp_utc=None, timeout_seconds=None, **kwargs):
            return results.pop(0)

        original_forward = self.listener.forward_price_to_executor
        try:
            self.listener.forward_price_to_executor = scripted_forward
            publisher = self.listener.PricePublisher(["NQM6"])
            self.listener.update_latest_price_from_tick({
                "symbol": "NQM6",
                "price": 19000.25,
                "timestamp": "2026-05-04T05:00:00Z",
            }, price_publisher=publisher)
            publisher.publish_once()
            self.listener.update_latest_price_from_tick({
                "symbol": "NQM6",
                "price": 19000.50,
                "timestamp": "2026-05-04T05:00:01Z",
            }, price_publisher=publisher)
            publisher.publish_once()
        finally:
            self.listener.forward_price_to_executor = original_forward

        payload = json.loads(self.listener.FEED_HEALTH_PATH.read_text(encoding="utf-8"))
        entry = payload["symbols"]["NQM6"]
        self.assertEqual(entry["executor_price_post_failure_count"], 1)
        self.assertIsNone(entry["last_executor_price_post_failure_reason"])
        self.assertIn("last_bridge_post_timestamp_utc", entry)
        self.assertIn("last_successful_executor_price_post_timestamp_utc", entry)
        self.assertEqual(entry["last_bridge_post_age_seconds"], 0.0)

    def test_timeout_does_not_prevent_next_successful_price_post(self):
        results = [(False, "timed out"), (True, None)]

        def scripted_forward(symbol, price, update_health=True, tick_timestamp_utc=None, timeout_seconds=None, **kwargs):
            return results.pop(0)

        original_forward = self.listener.forward_price_to_executor
        try:
            self.listener.forward_price_to_executor = scripted_forward
            publisher = self.listener.PricePublisher(["NQM6"])
            self.listener.update_latest_price_from_tick({
                "symbol": "NQM6",
                "price": 19000.25,
                "timestamp": "2026-05-04T05:00:00Z",
            }, price_publisher=publisher)
            publisher.publish_once()
            self.listener.update_latest_price_from_tick({
                "symbol": "NQM6",
                "price": 19000.50,
                "timestamp": "2026-05-04T05:00:01Z",
            }, price_publisher=publisher)
            publisher.publish_once()
        finally:
            self.listener.forward_price_to_executor = original_forward

        payload = json.loads(self.listener.FEED_HEALTH_PATH.read_text(encoding="utf-8"))
        entry = payload["symbols"]["NQM6"]
        self.assertEqual(entry["executor_price_post_failure_count"], 1)
        self.assertIsNone(entry["last_executor_price_post_failure_reason"])
        self.assertIn("last_successful_executor_price_post_timestamp_utc", entry)
        self.assertEqual(entry["latest_price"], 19000.50)

    def test_burst_exceeding_previous_queue_capacity_loses_zero_canonical_trades(self):
        previous_capacity = self.listener.TICK_QUEUE_MAX_SIZE
        worker = self.listener.TickWorker({})
        worker.start()
        burst_count = previous_capacity + 1
        try:
            for index in range(burst_count):
                source_time = f"2026-04-30T13:31:00.{index:06d}Z"
                worker.enqueue_tick(self._canonical_tick(source_time, index + 1, 19000.0 + (index % 2) * 0.25))
            worker.events.join()
        finally:
            worker.stop()

        self.assertEqual(worker.ticks_processed["NQM6"], burst_count)
        self.assertEqual(worker.current_tick_bars["NQM6"]["tick_count"], burst_count)
        self.assertEqual(sum(worker.ticks_dropped.values()), 0)
        self.assertEqual(sum(worker.ticks_coalesced_count.values()), 0)
        self.assertEqual(sum(worker.queue_overflow_count.values()), 0)

    def test_tick_worker_drains_queue_and_feed_health_stays_live(self):
        self.listener.forward_price_to_executor = lambda *args, **kwargs: None
        worker = self.listener.TickWorker({})
        worker.start()
        try:
            for index in range(20):
                worker.enqueue_tick(self._canonical_tick(self.listener.utc_now_iso(), index + 1, 19000.0 + index))
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
        worker = self.listener.TickWorker({})

        worker.process_tick(self._canonical_tick("2026-04-30T13:31:00Z", 1, 100.0))
        worker.process_tick(self._canonical_tick("2026-04-30T13:31:30Z", 2, 101.0))
        worker.process_tick(self._canonical_tick("2026-04-30T13:32:00Z", 3, 102.0))

        payload = json.loads(self.listener.RECENT_BARS_PATH.read_text(encoding="utf-8"))
        bar = payload["symbols"]["NQM6"][-1]
        self.assertEqual(bar["timestamp"], "2026-04-30T13:31:00Z")
        self.assertEqual(bar["open"], 100.0)
        self.assertEqual(bar["high"], 101.0)
        self.assertEqual(bar["low"], 100.0)
        self.assertEqual(bar["close"], 101.0)

    def test_july_14_receipt_time_bar_differs_from_exchange_time_bar(self):
        rows = [
            ("2026-07-14T14:14:00.050Z", "2026-07-14T14:13:58.639Z", 52854.0),
            ("2026-07-14T14:14:01.500Z", "2026-07-14T14:14:00.089Z", 52849.0),
            ("2026-07-14T14:14:10.000Z", "2026-07-14T14:14:08.589Z", 52836.0),
            ("2026-07-14T14:14:30.000Z", "2026-07-14T14:14:28.589Z", 52905.0),
            ("2026-07-14T14:14:59.900Z", "2026-07-14T14:14:58.489Z", 52905.0),
            ("2026-07-14T14:15:00.200Z", "2026-07-14T14:14:58.789Z", 52889.0),
        ]

        legacy_minute = [
            price
            for _, receipt_time, price in rows
            if receipt_time.startswith("2026-07-14T14:14:")
        ]
        self.assertEqual(
            (legacy_minute[0], max(legacy_minute), min(legacy_minute), legacy_minute[-1]),
            (52849.0, 52905.0, 52836.0, 52889.0),
        )

        worker = self.listener.TickWorker({})
        for sequence, (source_time, receipt_time, price) in enumerate(rows, start=1):
            worker.process_tick(self._canonical_tick(
                source_time,
                sequence,
                price,
                symbol="YMU6",
                exchange="CBOT",
                receipt_time=receipt_time,
            ))

        self.assertEqual(len(worker.finalized_bars), 1)
        corrected = worker.finalized_bars[0]
        self.assertEqual(corrected["timestamp"], "2026-07-14T14:14:00Z")
        self.assertEqual(
            (corrected["open"], corrected["high"], corrected["low"], corrected["close"]),
            (52854.0, 52905.0, 52836.0, 52905.0),
        )
        self.assertEqual(worker.current_tick_bars["YMU6"]["timestamp"], "2026-07-14T14:15:00Z")
        self.assertEqual(worker.current_tick_bars["YMU6"]["open"], 52889.0)
        self.assertEqual(corrected["finalized_by_callback_sequence"], 6)

        cache = json.loads(self.listener.RECENT_BARS_PATH.read_text(encoding="utf-8"))
        cached_bar = cache["symbols"]["YMU6"][-1]
        archive_path = self.listener.session_bar_path("YM", "2026-07-14")
        worker.archive_reconciler.wait_for_idle()
        archived_bar = json.loads(archive_path.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(archived_bar, cached_bar)
        self.assertEqual(archived_bar, corrected)
        self.assertEqual(archived_bar["bar_id"], cached_bar["bar_id"])

        raw_records = []
        for path in self.listener.RAW_TICK_ROOT.rglob("YMU6_trades.jsonl"):
            raw_records.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
        self.assertEqual(len(raw_records), 6)
        self.assertTrue(all(record["exchange"] == "CBOT" for record in raw_records))
        self.assertTrue(all(record["callback_sequence"] is not None for record in raw_records))
        self.assertTrue(all(record["candle_assignment"] is not None for record in raw_records))

    def test_source_time_out_of_order_before_transition_sets_open_and_close_by_exchange_order(self):
        worker = self.listener.TickWorker({})
        worker.process_tick(self._canonical_tick("2026-07-14T14:14:10Z", 1, 100.0))
        worker.process_tick(self._canonical_tick("2026-07-14T14:14:00Z", 2, 99.0))
        worker.process_tick(self._canonical_tick("2026-07-14T14:14:59Z", 3, 105.0))
        worker.process_tick(self._canonical_tick("2026-07-14T14:15:00Z", 4, 101.0))

        bar = worker.finalized_bars[0]
        self.assertEqual((bar["open"], bar["high"], bar["low"], bar["close"]), (99.0, 105.0, 99.0, 105.0))
        self.assertEqual(bar["open_callback_sequence"], 2)
        self.assertEqual(bar["close_callback_sequence"], 3)

    def test_equal_exchange_timestamps_use_callback_sequence_as_open_close_tiebreaker(self):
        worker = self.listener.TickWorker({})
        worker.process_tick(self._canonical_tick("2026-07-14T14:14:00.500Z", 1, 100.0))
        worker.process_tick(self._canonical_tick("2026-07-14T14:14:00.500Z", 2, 102.0))
        worker.process_tick(self._canonical_tick("2026-07-14T14:15:00Z", 3, 101.0))

        bar = worker.finalized_bars[0]
        self.assertEqual((bar["open"], bar["close"]), (100.0, 102.0))
        self.assertEqual((bar["open_callback_sequence"], bar["close_callback_sequence"]), (1, 2))

    def test_internal_sequence_gap_blocks_transition_publication(self):
        worker = self.listener.TickWorker({})
        worker.process_tick(self._canonical_tick("2026-07-14T14:14:00Z", 1, 100.0))
        worker.process_tick(self._canonical_tick("2026-07-14T14:15:00Z", 3, 101.0))

        self.assertFalse(self.listener.RECENT_BARS_PATH.exists())
        self.assertEqual(worker.expected_callback_sequence, 2)
        self.assertIn(3, worker.pending_sequence_ticks)
        self.assertTrue(any(
            incident["incident_type"] == "internal_callback_sequence_gap"
            for incident in worker.authority_incidents
        ))

    def test_trading_facing_tick_projection_cannot_bypass_canonical_sequence_barrier(self):
        worker = self.listener.TickWorker({})
        worker.process_tick(self._canonical_tick("2026-07-14T14:14:01Z", 2, 101.0))

        self.assertNotIn("NQM6", self.listener.latest_price_by_symbol)
        self.assertIsNone(self.listener.build_step6_intrabar_path_payload("NQM6"))

        worker.process_tick(self._canonical_tick("2026-07-14T14:14:00Z", 1, 100.0))

        self.assertEqual(self.listener.latest_price_by_symbol["NQM6"], 101.0)
        path = self.listener.build_step6_intrabar_path_payload("NQM6")
        self.assertEqual(path["current_minute"]["points"], [
            ["2026-07-14T14:14:00.000000000Z", 100.0],
            ["2026-07-14T14:14:01.000000000Z", 101.0],
        ])

    def test_image_callback_cannot_create_or_finalize_live_candle(self):
        worker = self.listener.TickWorker({})
        worker.process_tick(self._canonical_tick("2026-07-14T14:14:00Z", 1, 100.0, callback_type="Image"))
        worker.process_tick(self._canonical_tick("2026-07-14T14:15:00Z", 2, 101.0, callback_type="Image"))

        self.assertEqual(worker.current_tick_bars, {})
        self.assertEqual(worker.finalized_bars, [])
        self.assertFalse(self.listener.RECENT_BARS_PATH.exists())

    def test_late_prior_minute_trade_records_incident_without_revising_bar(self):
        worker = self.listener.TickWorker({})
        worker.process_tick(self._canonical_tick("2026-07-14T14:14:00Z", 1, 100.0))
        worker.process_tick(self._canonical_tick("2026-07-14T14:14:59Z", 2, 105.0))
        worker.process_tick(self._canonical_tick("2026-07-14T14:15:00Z", 3, 101.0))
        original_bar = dict(worker.finalized_bars[0])

        worker.process_tick(self._canonical_tick("2026-07-14T14:14:30Z", 4, 99.0))

        cache = json.loads(self.listener.RECENT_BARS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(cache["symbols"]["NQM6"][-1], original_bar)
        self.assertEqual(worker.finalized_bars[0], original_bar)
        late_incidents = [
            incident for incident in worker.authority_incidents
            if incident["incident_type"] == "late_trade_after_publication"
        ]
        self.assertEqual(len(late_incidents), 1)
        self.assertEqual(late_incidents[0]["published_bar_id"], original_bar["bar_id"])

    def test_missing_source_timestamp_never_falls_back_to_receipt_time(self):
        worker = self.listener.TickWorker({})
        tick = self._canonical_tick("2026-07-14T14:14:00Z", 1, 100.0)
        tick.update({
            "source_ssboe": 0,
            "source_nsecs": 0,
            "source_usecs": 0,
            "exchange_time_ns": None,
            "timestamp": "2026-07-14T14:14:00Z",
        })

        worker.process_tick(tick)

        self.assertEqual(worker.current_tick_bars, {})
        self.assertFalse(self.listener.RECENT_BARS_PATH.exists())
        self.assertTrue(any(
            incident["incident_type"] == "missing_or_invalid_rithmic_source_timestamp"
            for incident in worker.authority_incidents
        ))

    def test_identical_source_ticks_replay_identically_despite_workstation_timing(self):
        source_rows = [
            ("2026-07-14T14:14:00.100Z", 100.0),
            ("2026-07-14T14:14:30.200Z", 101.0),
            ("2026-07-14T14:15:00.100Z", 102.0),
        ]

        first_worker = self.listener.TickWorker({})
        for sequence, (source_time, price) in enumerate(source_rows, start=1):
            first_worker.process_tick(self._canonical_tick(source_time, sequence, price, receipt_time=source_time))
        first_worker.archive_reconciler.wait_for_idle()
        first_worker.archive_reconciler.stop()

        self.listener.LOCAL_FINALIZED_BAR_JOURNAL_PATH = self.tmp_path / "second_replay" / "finalized_bars.jsonl"
        self.listener.RECENT_BARS_PATH = self.tmp_path / "second_replay" / "rithmic_recent_bars.json"
        self.listener.session_bar_path = (
            lambda root_symbol, session_date: self.tmp_path / "second_replay" / "rithmic_session_bars"
            / session_date / f"{root_symbol}_1m.jsonl"
        )
        self.listener._LOCAL_FINALIZED_BAR_JOURNAL_INDEX_PATH = None
        self.listener._LOCAL_FINALIZED_BAR_JOURNAL_BY_ID.clear()
        second_worker = self.listener.TickWorker({})
        for sequence, (source_time, price) in enumerate(source_rows, start=1):
            delayed_receipt = (
                datetime.fromisoformat(source_time.replace("Z", "+00:00")) + timedelta(seconds=17)
            ).isoformat().replace("+00:00", "Z")
            second_worker.process_tick(self._canonical_tick(source_time, sequence, price, receipt_time=delayed_receipt))

        first_bar = first_worker.finalized_bars[0]
        second_bar = second_worker.finalized_bars[0]
        market_fields = (
            "timestamp", "open", "high", "low", "close", "tick_count", "tick_stream_sha256", "bar_id"
        )
        self.assertEqual(
            {field: first_bar[field] for field in market_fields},
            {field: second_bar[field] for field in market_fields},
        )
        second_worker.archive_reconciler.wait_for_idle()
        second_worker.archive_reconciler.stop()

    def test_no_grace_timer_or_fixed_delay_exists_in_canonical_finalization(self):
        source = "\n".join([
            inspect.getsource(self.listener.atomic_replace_immediate),
            inspect.getsource(self.listener.TickWorker.process_tick),
            inspect.getsource(self.listener.TickWorker.process_contiguous_tick),
            inspect.getsource(self.listener.TickWorker.update_tick_bar),
        ]).lower()

        self.assertNotIn("sleep", source)
        self.assertNotIn("debounce", source)
        self.assertNotIn("grace", source)
        self.assertNotIn("wait(", source)

    def test_startup_minute_is_incomplete_and_next_full_minute_can_publish(self):
        worker = self.listener.TickWorker({}, enforce_startup_warmup=True)
        worker.process_tick(self._canonical_tick("2026-07-14T14:14:30Z", 1, 100.0))
        worker.process_tick(self._canonical_tick("2026-07-14T14:15:00Z", 2, 101.0))
        self.assertEqual(worker.finalized_bars, [])

        worker.process_tick(self._canonical_tick("2026-07-14T14:15:59Z", 3, 102.0))
        worker.process_tick(self._canonical_tick("2026-07-14T14:16:00Z", 4, 103.0))

        self.assertEqual(len(worker.finalized_bars), 1)
        self.assertEqual(worker.finalized_bars[0]["timestamp"], "2026-07-14T14:15:00Z")
        self.assertFalse(worker.finalized_bars[0]["canonical_atr"]["ready"])
        self.assertIsNone(worker.finalized_bars[0]["canonical_atr"]["updated_raw_atr"])

    def test_listener_publication_latency_load_target(self):
        worker = self.listener.TickWorker({})
        base = datetime(2026, 7, 14, 14, 0, tzinfo=timezone.utc)
        bar_count = 100
        with redirect_stdout(StringIO()):
            for index in range(bar_count + 1):
                source_time = (base + timedelta(minutes=index, milliseconds=1)).isoformat().replace("+00:00", "Z")
                worker.process_tick(self._canonical_tick(
                    source_time,
                    index + 1,
                    52000.0 + (index % 10),
                    symbol="YMU6",
                    exchange="CBOT",
                    receipt_time=self.listener.utc_now_precise_iso(),
                ))

        latencies = sorted(
            record["next_minute_trade_receipt_to_entry_agent_availability_ms"]
            for record in worker.publication_latencies
        )
        self.assertEqual(len(latencies), bar_count)
        p50 = latencies[max(0, int(len(latencies) * 0.50) - 1)]
        p95 = latencies[max(0, int(len(latencies) * 0.95) - 1)]
        p99 = latencies[max(0, int(len(latencies) * 0.99) - 1)]
        maximum = latencies[-1]
        commit_latencies = sorted(
            record["next_minute_trade_receipt_to_local_durable_commit_ms"]
            for record in worker.publication_latencies
        )
        exposure_latencies = sorted(
            record["local_durable_commit_to_entry_agent_availability_ms"]
            for record in worker.publication_latencies
        )
        commit_stats = self._latency_stats(commit_latencies)
        exposure_stats = self._latency_stats(exposure_latencies)
        print(
            "RITHMIC TEST|publication_latency_normal|"
            f"bars={bar_count}|p50_ms={p50}|p95_ms={p95}|p99_ms={p99}|max_ms={maximum}|"
            f"commit_stats_ms={commit_stats}|exposure_stats_ms={exposure_stats}"
        )
        self.assertTrue(all(
            record["next_minute_trade_receipt_to_local_durable_commit_ms"] is not None
            and record["local_durable_commit_to_entry_agent_availability_ms"] is not None
            for record in worker.publication_latencies
        ))
        self.assertLess(p95, 10.0)
        self.assertLess(p99, 25.0)
        worker.archive_reconciler.wait_for_idle()
        worker.archive_reconciler.stop()

    def test_listener_publication_latency_burst_target_and_lossless_canonical_ticks(self):
        worker = self.listener.TickWorker({})
        base = datetime(2026, 7, 14, 14, 0, tzinfo=timezone.utc)
        bar_count = 30
        ticks_per_minute = 100
        sequence = 0
        with redirect_stdout(StringIO()):
            for minute_index in range(bar_count + 1):
                for tick_index in range(ticks_per_minute):
                    sequence += 1
                    source_time = (
                        base
                        + timedelta(minutes=minute_index, milliseconds=tick_index * 500)
                    ).isoformat().replace("+00:00", "Z")
                    worker.process_tick(self._canonical_tick(
                        source_time,
                        sequence,
                        52000.0 + (tick_index % 17),
                        symbol="YMU6",
                        exchange="CBOT",
                        receipt_time=self.listener.utc_now_precise_iso(),
                    ))

        latencies = sorted(
            record["next_minute_trade_receipt_to_entry_agent_availability_ms"]
            for record in worker.publication_latencies
        )
        self.assertEqual(len(latencies), bar_count)
        self.assertEqual(worker.ticks_processed["YMU6"], (bar_count + 1) * ticks_per_minute)
        self.assertEqual(sum(worker.ticks_dropped.values()), 0)
        self.assertEqual(sum(worker.ticks_coalesced_count.values()), 0)
        self.assertEqual(sum(worker.queue_overflow_count.values()), 0)
        p50 = latencies[max(0, int(len(latencies) * 0.50) - 1)]
        p95 = latencies[max(0, int(len(latencies) * 0.95) - 1)]
        p99 = latencies[max(0, int(len(latencies) * 0.99) - 1)]
        maximum = latencies[-1]
        commit_latencies = sorted(
            record["next_minute_trade_receipt_to_local_durable_commit_ms"]
            for record in worker.publication_latencies
        )
        exposure_latencies = sorted(
            record["local_durable_commit_to_entry_agent_availability_ms"]
            for record in worker.publication_latencies
        )
        commit_stats = self._latency_stats(commit_latencies)
        exposure_stats = self._latency_stats(exposure_latencies)
        print(
            "RITHMIC TEST|publication_latency_burst|"
            f"bars={bar_count}|ticks={sequence}|p50_ms={p50}|"
            f"p95_ms={p95}|p99_ms={p99}|max_ms={maximum}|"
            f"commit_stats_ms={commit_stats}|exposure_stats_ms={exposure_stats}"
        )
        self.assertLess(p95, 10.0)
        self.assertLess(p99, 25.0)
        worker.archive_reconciler.wait_for_idle()
        worker.archive_reconciler.stop()

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
            "callback_sequence": 42,
            "bridge_generation": 3,
            "callback_receipt_timestamp_utc": "2026-04-30T13:31:00.001Z",
            "python_receipt_timestamp_utc": "2026-04-30T13:31:00.002Z",
            "source_ssboe": 1777555860,
            "source_nsecs": 0,
            "source_usecs": 0,
        }, price_publisher=publisher)
        publisher.publish_once()

        self.assertEqual(len(forwarded), 1)
        self.assertEqual(forwarded[0][0], ("NQM6", 100.0))
        self.assertFalse(forwarded[0][1]["update_health"])
        self.assertEqual(forwarded[0][1]["tick_timestamp_utc"], "2026-04-30T13:31:00Z")
        self.assertEqual(forwarded[0][1]["listener_sequence"], 42)
        self.assertEqual(forwarded[0][1]["listener_tick_id"], "3:42")
        self.assertEqual(
            forwarded[0][1]["callback_receipt_timestamp_utc"],
            "2026-04-30T13:31:00.001Z",
        )

    def test_listener_requests_executor_issued_generation(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({
                    "ok": True,
                    "authority": "executor_durable_listener_generation",
                    "generation": 5,
                }).encode("utf-8")

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse()

        with mock.patch.object(self.listener.urllib.request, "urlopen", side_effect=fake_urlopen):
            generation = self.listener.allocate_executor_listener_generation()

        self.assertEqual(generation, 5)
        self.assertEqual(captured["url"], self.listener.EXECUTOR_LISTENER_GENERATION_URL)
        self.assertEqual(captured["payload"]["authority_mutex"], self.listener.LISTENER_AUTHORITY_MUTEX_NAME)
        self.assertEqual(captured["payload"]["symbols"], ["NQ", "YM"])

    def test_executor_issued_generation_is_used_for_nq_and_ym_publication(self):
        forwarded = []
        self.listener.forward_price_to_executor = (
            lambda *args, **kwargs: forwarded.append((args, kwargs)) or (True, None)
        )
        publisher = self.listener.PricePublisher(["NQU6", "YMU6"])
        for symbol, exchange, sequence, price in (
            ("NQU6", "CME", 41, 30000.0),
            ("YMU6", "CBOT", 42, 53000.0),
        ):
            self.listener.update_latest_price_from_tick({
                "timestamp": f"2026-07-15T14:30:{sequence:02d}Z",
                "symbol": symbol,
                "exchange": exchange,
                "price": price,
                "callback_sequence": sequence,
                "bridge_generation": 5,
                "callback_receipt_timestamp_utc": "2026-07-15T14:30:00.001Z",
                "python_receipt_timestamp_utc": "2026-07-15T14:30:00.002Z",
                "source_ssboe": 1784125800 + sequence,
                "source_nsecs": 0,
                "source_usecs": 0,
            }, price_publisher=publisher)
        publisher.publish_once()

        identities = {args[0]: kwargs["listener_tick_id"] for args, kwargs in forwarded}
        self.assertEqual(identities, {"NQU6": "5:41", "YMU6": "5:42"})

    def test_nq_full_timeout_does_not_delay_ym_delivery(self):
        nq_started = threading.Event()
        nq_finished = threading.Event()
        ym_delivered = threading.Event()
        observed = []

        def delayed_forward(symbol, price, **kwargs):
            observed.append((symbol, kwargs["listener_sequence"], time.monotonic()))
            if symbol == "NQU6":
                nq_started.set()
                time.sleep(0.5)
                nq_finished.set()
                return False, "timed out"
            ym_delivered.set()
            return True, None

        publisher = self.listener.PricePublisher(["NQU6", "YMU6"])
        publisher.persist_delivery_audit = lambda record: None
        with mock.patch.object(self.listener, "forward_price_to_executor", side_effect=delayed_forward):
            publisher.start()
            try:
                self.listener.update_latest_price_from_tick(
                    self._delivery_tick("NQU6", 1, 19000.25),
                    price_publisher=publisher,
                )
                self.assertTrue(nq_started.wait(0.2))
                ym_enqueued_at = time.monotonic()
                self.listener.update_latest_price_from_tick(
                    self._delivery_tick("YMU6", 2, 52000),
                    price_publisher=publisher,
                )
                self.assertTrue(ym_delivered.wait(0.1))
                self.assertLess(time.monotonic() - ym_enqueued_at, 0.1)
                self.assertFalse(nq_finished.is_set())
                publisher.wait_for_idle()
            finally:
                publisher.stop()

        self.assertEqual([item[0] for item in observed], ["NQU6", "YMU6"])
        self.assertEqual(publisher.metrics_snapshot("NQU6")["timeouts"], 1)
        self.assertEqual(publisher.metrics_snapshot("YMU6")["successes"], 1)
        failure = json.loads(
            self.listener.PRICE_DELIVERY_FAILURES_PATH.read_text(encoding="utf-8").splitlines()[-1]
        )
        self.assertEqual(failure["symbol"], "NQU6")
        self.assertEqual(failure["callback_sequence"], 1)
        self.assertEqual(failure["rithmic_source_timestamp_utc"], "2026-07-14T18:30:01.000000000Z")
        self.assertEqual(failure["destination"], self.listener.EXECUTOR_PRICE_URL)
        self.assertGreaterEqual(failure["post_duration_ms"], 500.0)
        self.assertEqual(failure["failure"], "timed out")

    def test_ym_full_timeout_does_not_delay_nq_delivery(self):
        ym_started = threading.Event()
        ym_finished = threading.Event()
        nq_delivered = threading.Event()

        def delayed_forward(symbol, price, **kwargs):
            if symbol == "YMU6":
                ym_started.set()
                time.sleep(0.5)
                ym_finished.set()
                return False, "timed out"
            nq_delivered.set()
            return True, None

        publisher = self.listener.PricePublisher(["NQU6", "YMU6"])
        publisher.persist_delivery_audit = lambda record: None
        with mock.patch.object(self.listener, "forward_price_to_executor", side_effect=delayed_forward):
            publisher.start()
            try:
                self.listener.update_latest_price_from_tick(
                    self._delivery_tick("YMU6", 1, 52000),
                    price_publisher=publisher,
                )
                self.assertTrue(ym_started.wait(0.2))
                nq_enqueued_at = time.monotonic()
                self.listener.update_latest_price_from_tick(
                    self._delivery_tick("NQU6", 2, 19000.25),
                    price_publisher=publisher,
                )
                self.assertTrue(nq_delivered.wait(0.1))
                self.assertLess(time.monotonic() - nq_enqueued_at, 0.1)
                self.assertFalse(ym_finished.is_set())
                publisher.wait_for_idle()
            finally:
                publisher.stop()

        self.assertEqual(publisher.metrics_snapshot("YMU6")["timeouts"], 1)
        self.assertEqual(publisher.metrics_snapshot("NQU6")["successes"], 1)

    def test_symbol_fifos_preserve_order_during_other_symbol_timeout(self):
        ym_started = threading.Event()
        delivered = {"NQU6": [], "YMU6": []}

        def delayed_forward(symbol, price, **kwargs):
            if symbol == "YMU6":
                ym_started.set()
                time.sleep(0.5)
                return False, "timed out"
            delivered[symbol].append(kwargs["listener_sequence"])
            return True, None

        publisher = self.listener.PricePublisher(["NQU6", "YMU6"])
        publisher.persist_delivery_audit = lambda record: None
        with mock.patch.object(self.listener, "forward_price_to_executor", side_effect=delayed_forward):
            publisher.start()
            try:
                self.listener.update_latest_price_from_tick(
                    self._delivery_tick("YMU6", 1, 52000),
                    price_publisher=publisher,
                )
                self.assertTrue(ym_started.wait(0.2))
                for sequence in range(2, 22):
                    self.listener.update_latest_price_from_tick(
                        self._delivery_tick("NQU6", sequence, 19000 + sequence / 4),
                        price_publisher=publisher,
                    )
                publisher.wait_for_idle()
            finally:
                publisher.stop()

        self.assertEqual(delivered["NQU6"], list(range(2, 22)))

    def test_ym_fifo_preserves_order_during_nq_timeout(self):
        nq_started = threading.Event()
        delivered = []

        def delayed_forward(symbol, price, **kwargs):
            if symbol == "NQU6":
                nq_started.set()
                time.sleep(0.5)
                return False, "timed out"
            delivered.append(kwargs["listener_sequence"])
            return True, None

        publisher = self.listener.PricePublisher(["NQU6", "YMU6"])
        publisher.persist_delivery_audit = lambda record: None
        with mock.patch.object(self.listener, "forward_price_to_executor", side_effect=delayed_forward):
            publisher.start()
            try:
                self.listener.update_latest_price_from_tick(
                    self._delivery_tick("NQU6", 1, 19000.25),
                    price_publisher=publisher,
                )
                self.assertTrue(nq_started.wait(0.2))
                for sequence in range(2, 22):
                    self.listener.update_latest_price_from_tick(
                        self._delivery_tick("YMU6", sequence, 52000 + sequence),
                        price_publisher=publisher,
                    )
                publisher.wait_for_idle()
            finally:
                publisher.stop()

        self.assertEqual(delivered, list(range(2, 22)))

    def test_same_symbol_requests_cannot_overtake(self):
        first_started = threading.Event()
        release_first = threading.Event()
        second_started = threading.Event()
        delivered = []

        def ordered_forward(symbol, price, **kwargs):
            sequence = kwargs["listener_sequence"]
            delivered.append(sequence)
            if sequence == 1:
                first_started.set()
                release_first.wait(1)
            else:
                second_started.set()
            return True, None

        publisher = self.listener.PricePublisher(["NQU6", "YMU6"])
        publisher.persist_delivery_audit = lambda record: None
        with mock.patch.object(self.listener, "forward_price_to_executor", side_effect=ordered_forward):
            publisher.start()
            try:
                self.listener.update_latest_price_from_tick(
                    self._delivery_tick("NQU6", 1, 19000.25),
                    price_publisher=publisher,
                )
                self.assertTrue(first_started.wait(0.2))
                self.listener.update_latest_price_from_tick(
                    self._delivery_tick("NQU6", 2, 19000.50),
                    price_publisher=publisher,
                )
                self.assertFalse(second_started.wait(0.1))
                release_first.set()
                publisher.wait_for_idle()
                self.assertTrue(second_started.is_set())
            finally:
                release_first.set()
                publisher.stop()

        self.assertEqual(delivered, [1, 2])

    def test_price_delivery_burst_over_previous_capacity_is_lossless_without_coalescing(self):
        first_started = threading.Event()
        release_first = threading.Event()
        delivered = []
        tick_count = 5_201

        def blocked_first_forward(symbol, price, **kwargs):
            sequence = kwargs["listener_sequence"]
            if sequence == 1:
                first_started.set()
                release_first.wait(2)
            delivered.append((sequence, price))
            return True, None

        publisher = self.listener.PricePublisher(["NQU6", "YMU6"])
        publisher.process_audit_record = lambda record: None
        with mock.patch.object(
            self.listener,
            "forward_price_to_executor",
            side_effect=blocked_first_forward,
        ):
            publisher.start()
            try:
                self.listener.update_latest_price_from_tick(
                    self._delivery_tick("NQU6", 1, 19000.25),
                    price_publisher=publisher,
                )
                self.assertTrue(first_started.wait(0.2))
                for sequence in range(2, tick_count + 1):
                    self.listener.update_latest_price_from_tick(
                        self._delivery_tick("NQU6", sequence, 19000.25),
                        price_publisher=publisher,
                    )
                queued_metrics = publisher.metrics_snapshot("NQU6")
                self.assertEqual(queued_metrics["enqueued"], tick_count)
                self.assertGreaterEqual(queued_metrics["max_queue_depth"], 5_000)
                release_first.set()
                publisher.wait_for_idle()
            finally:
                release_first.set()
                publisher.stop()

        self.assertEqual([item[0] for item in delivered], list(range(1, tick_count + 1)))
        self.assertEqual({item[1] for item in delivered}, {19000.25})
        final_metrics = publisher.metrics_snapshot("NQU6")
        self.assertEqual(final_metrics["enqueued"], tick_count)
        self.assertEqual(final_metrics["completed"], tick_count)
        self.assertEqual(final_metrics["successes"], tick_count)
        self.assertEqual(final_metrics["queue_depth"], 0)

    def test_rapid_alternating_ticks_are_lossless_and_independently_ordered(self):
        delivered = {"NQU6": [], "YMU6": []}

        def successful_forward(symbol, price, **kwargs):
            delivered[symbol].append((kwargs["listener_sequence"], kwargs["tick_timestamp_utc"]))
            return True, None

        publisher = self.listener.PricePublisher(["NQU6", "YMU6"])
        publisher.persist_delivery_audit = lambda record: None
        with mock.patch.object(self.listener, "forward_price_to_executor", side_effect=successful_forward):
            publisher.start()
            try:
                for sequence in range(1, 41):
                    symbol = "NQU6" if sequence % 2 else "YMU6"
                    timestamp = f"2026-07-14T18:30:{sequence // 100:02d}.{sequence:09d}Z"
                    self.listener.update_latest_price_from_tick(
                        self._delivery_tick(symbol, sequence, 19000 + sequence / 4, timestamp),
                        price_publisher=publisher,
                    )
                publisher.wait_for_idle()
            finally:
                publisher.stop()

        self.assertEqual([item[0] for item in delivered["NQU6"]], list(range(1, 41, 2)))
        self.assertEqual([item[0] for item in delivered["YMU6"]], list(range(2, 41, 2)))
        for symbol in ("NQU6", "YMU6"):
            timestamps = [item[1] for item in delivered[symbol]]
            self.assertEqual(timestamps, sorted(timestamps))
            metrics = publisher.metrics_snapshot(symbol)
            self.assertEqual(metrics["enqueued"], 20)
            self.assertEqual(metrics["attempts"], 20)
            self.assertEqual(metrics["successes"], 20)
            self.assertEqual(metrics["completed"], 20)
            self.assertEqual(metrics["timeouts"], 0)
            self.assertEqual(metrics["other_failures"], 0)
            self.assertEqual(metrics["queue_depth"], 0)

    def test_blocked_price_post_does_not_delay_other_symbol_canonical_candle(self):
        nq_started = threading.Event()
        nq_finished = threading.Event()

        def delayed_forward(symbol, price, **kwargs):
            if symbol == "NQU6":
                nq_started.set()
                time.sleep(0.5)
                nq_finished.set()
                return False, "timed out"
            return True, None

        publisher = self.listener.PricePublisher(["NQU6", "YMU6"])
        publisher.persist_delivery_audit = lambda record: None
        worker = self.listener.TickWorker(
            {},
            subscribed_symbols=["NQU6", "YMU6"],
            price_publisher=publisher,
        )
        with mock.patch.object(self.listener, "forward_price_to_executor", side_effect=delayed_forward):
            publisher.start()
            try:
                self.assertTrue(worker.process_tick(self._canonical_tick(
                    "2026-07-14T18:30:00.050Z",
                    1,
                    19000.25,
                    symbol="NQU6",
                    exchange="CME",
                )))
                self.assertTrue(nq_started.wait(0.2))

                canonical_started = time.monotonic()
                self.assertTrue(worker.process_tick(self._canonical_tick(
                    "2026-07-14T18:30:00.100Z",
                    2,
                    52000,
                    symbol="YMU6",
                    exchange="CBOT",
                )))
                self.assertTrue(worker.process_tick(self._canonical_tick(
                    "2026-07-14T18:31:00.100Z",
                    3,
                    52001,
                    symbol="YMU6",
                    exchange="CBOT",
                )))
                canonical_duration = time.monotonic() - canonical_started

                self.assertFalse(nq_finished.is_set())
                self.assertLess(canonical_duration, 0.25)
                self.assertEqual(len(worker.finalized_bars), 1)
                finalized = worker.finalized_bars[0]
                self.assertEqual(finalized["symbol"], "YMU6")
                self.assertEqual(finalized["timestamp"], "2026-07-14T18:30:00Z")
                self.assertEqual(
                    (finalized["open"], finalized["high"], finalized["low"], finalized["close"]),
                    (52000.0, 52000.0, 52000.0, 52000.0),
                )
                publisher.wait_for_idle()
            finally:
                publisher.stop()
                worker.stop()

    def test_price_workers_have_no_shared_timer_or_coalescing_state(self):
        module_source = (ROOT / "rithmic_live_listener.py").read_text(encoding="utf-8")
        publisher_start = module_source.index("class PricePublisher:")
        publisher_end = module_source.index("\ndef minute_timestamp_from_tick", publisher_start)
        publisher_source = module_source[publisher_start:publisher_end]
        worker_start = module_source.index("class SymbolPriceWorker:")
        worker_end = module_source.index("\nclass PricePublisher:", worker_start)
        worker_source = module_source[worker_start:worker_end]

        self.assertNotIn("PRICE_POST_MIN_INTERVAL_SECONDS", module_source)
        self.assertNotIn("latest_dirty_by_symbol", module_source)
        self.assertNotIn("latest_published_tick_time_by_symbol", module_source)
        self.assertNotIn("time.sleep", publisher_source)
        self.assertIn("queue.Queue()", publisher_source)
        self.assertIn("self.events.get()", worker_source)
        self.assertIn("rithmic_price_publisher_", worker_source)

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

    def test_disconnect_watchdog_skips_symbol_only_dead_when_another_symbol_live(self):
        payload = {
            "symbols": {
                "NQM6": {"last_tick_timestamp_utc": self._iso_seconds_ago(1)},
                "YMM6": {"last_tick_timestamp_utc": self._iso_seconds_ago(91)},
            }
        }
        self.listener.write_feed_health(payload)
        fake_process = self._fake_process()
        output = StringIO()

        enabled_event = self.listener.threading.Event()
        with redirect_stdout(output):
            stop_event, thread = self.listener.start_disconnect_watchdog(fake_process, ["NQM6", "YMM6"], enabled_event)
            try:
                enabled_event.set()
                time.sleep(1.2)
            finally:
                stop_event.set()
                thread.join(timeout=2)

        self.assertFalse(fake_process.terminated)
        self.assertIn("dead_restart_skipped_symbol_only", output.getvalue())
        self.assertIn("symbol=YMM6", output.getvalue())
        self.assertIn("live_or_quiet_symbols=1", output.getvalue())

    def test_disconnect_watchdog_reconnects_when_all_tracked_symbols_dead(self):
        payload = {
            "symbols": {
                "NQM6": {"last_tick_timestamp_utc": self._iso_seconds_ago(91)},
                "YMM6": {"last_tick_timestamp_utc": self._iso_seconds_ago(91)},
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
        self.listener.DEAD_RESTART_ATTEMPTS["NQM6"] = 2
        self.listener.DEAD_RESTART_LAST_TIMES["NQM6"] = time.monotonic()
        worker = self.listener.TickWorker({})

        worker.process_tick(self._canonical_tick("2026-04-30T13:31:00Z", 1, 100.0))

        self.assertNotIn("NQM6", self.listener.DEAD_RESTART_ATTEMPTS)
        self.assertNotIn("NQM6", self.listener.DEAD_RESTART_LAST_TIMES)


if __name__ == "__main__":
    unittest.main()
