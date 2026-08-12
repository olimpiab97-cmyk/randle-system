from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from command_center_service_control import CONTROL_VERSION, ControlManager
from test_command_center_r1e_full_integration import ProductionShapedLifecycle


ROOT = Path(__file__).resolve().parent


class FakeClock:
    def __init__(self) -> None:
        self.value = 10_000.0
        self.lock = threading.Lock()

    def monotonic(self) -> float:
        with self.lock:
            return self.value

    def advance(self, seconds: float) -> None:
        with self.lock:
            self.value += float(seconds)


class TimingAdapter:
    def __init__(self, clock: FakeClock, delay_seconds: float = 0.0) -> None:
        self.clock = clock
        self.delay_seconds = delay_seconds
        self.preflight_calls = 0
        self.start_calls = 0
        self.shutdown_calls = 0
        self.shutdown_live_rechecks = 0
        self.fail_preflight = False
        self.invalid_preflight = False
        self.ladder = {"state": "READY", "label": "TV LADDER — READY"}
        self.services = [
            {"name": "executor", "classification": "STOPPED", "identity": "TRUSTED", "readiness": "STOPPED"},
            {"name": "entry_agent", "classification": "RUNNING_NOT_READY", "identity": "TRUSTED", "readiness": "NOT_READY", "execution_identity": "GOVERNED_WRAPPED_TRANSITIONAL"},
            {"name": "trade_manager", "classification": "RUNNING_READY", "identity": "TRUSTED", "readiness": "READY", "execution_identity": "GOVERNED_WRAPPED_TRANSITIONAL"},
            {"name": "rithmic_listener", "classification": "STOPPED", "identity": "TRUSTED", "readiness": "STOPPED"},
            {"name": "ngrok", "classification": "RUNNING_READY", "identity": "TRUSTED", "readiness": "READY"},
        ]

    def snapshot(self) -> dict:
        return {"services": [dict(row) for row in self.services]}

    def prearm_snapshot(self) -> dict:
        self.preflight_calls += 1
        self.clock.advance(self.delay_seconds)
        if self.fail_preflight:
            raise TimeoutError("isolated_preflight_unavailable")
        if self.invalid_preflight:
            return {"services": "invalid"}
        return self.snapshot()

    def start_stack(self) -> dict:
        self.start_calls += 1
        self.services = [
            {**row, "classification": "RUNNING_READY", "identity": "TRUSTED", "readiness": "READY"}
            for row in self.services
        ]
        return {"ok": True, "message": "SYSTEM READY", "post_confirm_safety_gate": "PASS"}

    def shutdown_stack(self) -> dict:
        self.shutdown_calls += 1
        self.shutdown_live_rechecks += 1
        self.services = [
            {**row, "classification": "STOPPED", "identity": "TRUSTED", "readiness": "STOPPED"}
            for row in self.services
        ]
        return {"ok": True, "message": "SYSTEM OFFLINE", "safety": {"safe": True, "authority": "fresh_post_confirm_live"}}

    def ladder_status(self) -> dict:
        return dict(self.ladder)


class CommandCenterR1FConfirmationTimingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="cc-r1f-timing-", ignore_cleanup_errors=True)
        self.root = Path(self.directory.name)
        self.clock = FakeClock()
        self.adapter = TimingAdapter(self.clock)
        self.manager = ControlManager(self.adapter, self.root / "audit.jsonl", confirmation_window=5.0)
        self.session = "isolated-session-a"

    def tearDown(self) -> None:
        try:
            self.manager.wait_for_idle(2)
        except TimeoutError:
            pass
        self.directory.cleanup()

    def arm(self, action: str = "START") -> dict:
        return self.manager.arm(action, source="r1f_isolated", session_id=self.session)

    def confirm(self, armed: dict, action: str | None = None, session: str | None = None, version: str = CONTROL_VERSION) -> dict:
        return self.manager.confirm(
            armed["request_id"],
            session_id=session or self.session,
            action=action or armed["action"],
            control_version=version,
        )

    def assert_window_after_preflight(self, delay_ms: int) -> None:
        self.adapter.delay_seconds = delay_ms / 1000.0
        with patch("command_center_service_control.time.monotonic", self.clock.monotonic):
            started = self.clock.monotonic()
            armed = self.arm()
            response_ready = self.clock.monotonic()
            row = self.manager._arms[armed["request_id"]]
            self.assertAlmostEqual(response_ready - started, delay_ms / 1000.0, places=6)
            self.assertAlmostEqual(row["expires_at"] - response_ready, 5.0, places=6)
            self.assertAlmostEqual(armed["preflight_duration_seconds"], delay_ms / 1000.0, places=6)
            self.assertEqual(armed["expires_in_seconds"], 5.0)
            self.assertEqual(self.adapter.start_calls, 0)

    def test_01_exact_prestate_latency_regression_timer_starts_after_snapshot(self) -> None:
        self.assert_window_after_preflight(5156)

    def test_02_zero_ms_preflight_preserves_window(self) -> None:
        self.assert_window_after_preflight(0)

    def test_03_500_ms_preflight_preserves_window(self) -> None:
        self.assert_window_after_preflight(500)

    def test_04_2000_ms_preflight_preserves_window(self) -> None:
        self.assert_window_after_preflight(2000)

    def test_05_2140_ms_preflight_preserves_window(self) -> None:
        self.assert_window_after_preflight(2140)

    def test_06_3000_ms_preflight_preserves_window(self) -> None:
        self.assert_window_after_preflight(3000)

    def test_07_5000_ms_preflight_preserves_window(self) -> None:
        self.assert_window_after_preflight(5000)

    def test_08_7500_ms_preflight_preserves_window(self) -> None:
        self.assert_window_after_preflight(7500)

    def test_09_immediate_confirmation_is_accepted(self) -> None:
        self.adapter.delay_seconds = 5.156
        with patch("command_center_service_control.time.monotonic", self.clock.monotonic):
            armed = self.arm()
            confirmed = self.confirm(armed)
            self.assertTrue(confirmed["accepted"])
            self.assertTrue(confirmed.get("operation_id"))
            self.manager.wait_for_idle(1)
        self.assertEqual(self.adapter.start_calls, 1)

    def test_10_confirmation_at_four_point_five_seconds_is_accepted(self) -> None:
        with patch("command_center_service_control.time.monotonic", self.clock.monotonic):
            armed = self.arm()
            self.clock.advance(4.5)
            self.assertTrue(self.confirm(armed)["accepted"])

    def test_11_confirmation_after_five_seconds_is_rejected(self) -> None:
        with patch("command_center_service_control.time.monotonic", self.clock.monotonic):
            armed = self.arm()
            self.clock.advance(5.001)
            result = self.confirm(armed)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "confirmation_missing_or_expired")
        self.assertEqual(self.adapter.start_calls, 0)

    def test_12_expired_start_creates_no_operation_or_mutation(self) -> None:
        with patch("command_center_service_control.time.monotonic", self.clock.monotonic):
            armed = self.arm("START")
            self.clock.advance(5.1)
            self.manager.expire_arms()
        self.assertEqual(self.adapter.start_calls, 0)
        self.assertIsNone(self.manager._operation)
        self.assertNotIn(armed["request_id"], self.manager._arms)

    def test_13_expired_shutdown_creates_no_operation_or_mutation(self) -> None:
        with patch("command_center_service_control.time.monotonic", self.clock.monotonic):
            armed = self.arm("SHUTDOWN")
            self.clock.advance(5.1)
            self.manager.expire_arms()
        self.assertEqual(self.adapter.shutdown_calls, 0)
        self.assertIsNone(self.manager._operation)
        self.assertNotIn(armed["request_id"], self.manager._arms)

    def test_14_double_confirmation_accepts_exactly_one_operation(self) -> None:
        armed = self.arm()
        first = self.confirm(armed)
        second = self.confirm(armed)
        self.manager.wait_for_idle(2)
        self.assertTrue(first["accepted"])
        self.assertFalse(second["ok"])
        self.assertEqual(second["error"], "confirmation_already_used")
        self.assertEqual(self.adapter.start_calls, 1)

    def test_15_conflicting_arms_fail_closed(self) -> None:
        first = self.arm("START")
        second = self.arm("SHUTDOWN")
        self.assertTrue(first["ok"])
        self.assertFalse(second["ok"])
        self.assertEqual(second["error"], "control_confirmation_already_armed")

    def test_16_wrong_session_cannot_confirm_arm(self) -> None:
        armed = self.arm()
        rejected = self.confirm(armed, session="other-session")
        self.assertEqual(rejected["error"], "confirmation_authority_mismatch")
        self.assertTrue(self.confirm(armed)["accepted"])

    def test_17_wrong_action_cannot_confirm_arm(self) -> None:
        armed = self.arm("START")
        rejected = self.confirm(armed, action="SHUTDOWN")
        self.assertEqual(rejected["error"], "confirmation_authority_mismatch")
        self.assertTrue(self.confirm(armed, action="START")["accepted"])

    def test_18_old_control_version_cannot_confirm_arm(self) -> None:
        armed = self.arm()
        rejected = self.confirm(armed, version="command_center_service_controls_r1d")
        self.assertEqual(rejected["error"], "confirmation_authority_mismatch")
        self.assertTrue(self.confirm(armed)["accepted"])

    def test_19_preflight_failure_creates_no_arm(self) -> None:
        self.adapter.fail_preflight = True
        result = self.arm()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "prearm_preflight_unavailable")
        self.assertFalse(self.manager._arms)
        self.assertEqual(self.adapter.start_calls, 0)

    def test_20_prestate_audit_links_preflight_arm_and_operation(self) -> None:
        armed = self.arm()
        confirmed = self.confirm(armed)
        self.manager.wait_for_idle(2)
        rows = [json.loads(line) for line in (self.root / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
        preflight = next(row for row in rows if row["event"] == "control_preflight_started")
        arm = next(row for row in rows if row["event"] == "control_armed")
        confirm = next(row for row in rows if row["event"] == "control_confirmed")
        self.assertEqual({preflight["preflight_id"], arm["preflight_id"], confirm["preflight_id"]}, {armed["preflight_id"]})
        self.assertEqual(confirm["operation_id"], confirmed["operation_id"])
        self.assertNotIn(self.session, (self.root / "audit.jsonl").read_text(encoding="utf-8"))

    def test_21_start_real_safety_path_runs_only_after_confirmation(self) -> None:
        armed = self.arm()
        self.assertEqual(self.adapter.start_calls, 0)
        self.confirm(armed)
        self.manager.wait_for_idle(2)
        self.assertEqual(self.adapter.start_calls, 1)

    def test_22_shutdown_fresh_live_recheck_runs_only_after_confirmation(self) -> None:
        armed = self.arm("SHUTDOWN")
        self.assertEqual(self.adapter.shutdown_live_rechecks, 0)
        self.confirm(armed)
        self.manager.wait_for_idle(2)
        self.assertEqual(self.adapter.shutdown_live_rechecks, 1)

    def test_23_frontend_countdown_uses_backend_arm_response(self) -> None:
        source = (ROOT / "command_center.html").read_text(encoding="utf-8")
        self.assertIn("armed.expires_in_seconds", source)
        self.assertIn("performance.now() + (expiresInSeconds * 1000)", source)
        self.assertIn("request_id: requestId, action: normalized", source)
        self.assertNotIn("setTimeout(clearSystemControlArm, CONTROL_CONFIRMATION_MS + 100)", source)

    def test_24_monotonic_expiry_and_utc_audit_are_distinct(self) -> None:
        source = (ROOT / "command_center_service_control.py").read_text(encoding="utf-8")
        self.assertIn("armed_at = time.monotonic()", source)
        self.assertIn("armed_wall = datetime.now(ZoneInfo(\"UTC\"))", source)
        self.assertIn("expires_at = armed_at + self.confirmation_window", source)

    def test_25_stale_ladder_projection_is_retained_without_start_mutation(self) -> None:
        self.adapter.ladder = {"state": "STALE", "label": "TV LADDER — STALE"}
        armed = self.arm()
        self.confirm(armed)
        final = self.manager.wait_for_idle(2)
        self.assertEqual(final["state"], "DEGRADED")
        self.assertIn("TV LADDER STALE", final["message"])
        self.assertEqual(self.adapter.start_calls, 1)


class CommandCenterR1FFullCycleClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.harness = ProductionShapedLifecycle()
        cls.result = cls.harness.run()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.harness.temp, ignore_errors=True)

    def test_26_slow_production_topology_full_cycle(self) -> None:
        first = self.result["cycles"][0]
        self.assertTrue(first["shutdown_pass"] and first["restart_pass"])
        self.assertGreaterEqual(self.result["run1_start"]["preflight_elapsed_ms"], 2000)
        self.assertEqual(self.result["run1_start"]["operator_window_seconds"], 5.0)
        self.assertGreaterEqual(self.result["run1_start"]["operator_visible_window_seconds"], 4.75)

    def test_27_three_cycle_repeatability_is_retained(self) -> None:
        self.assertEqual(self.result["full_cycle_pass_count"], 3)
        self.assertTrue(all(row["shutdown_pass"] and row["restart_pass"] for row in self.result["cycles"]))

    def test_28_all_f001_through_f005_are_closed_together(self) -> None:
        self.assertTrue(self.result["known_failure_combination_f001_f005"])
        self.assertEqual(self.result["final"]["duplicate_count"], 0)
        self.assertEqual(self.result["final"]["orphan_count"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
