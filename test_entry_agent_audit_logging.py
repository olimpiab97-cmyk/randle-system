import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENTRY_AGENT_DIR = ROOT / "EntryAgent"


REQUIRED_AUDIT_FIELDS = {
    "received_at",
    "symbol",
    "normalized_symbol",
    "requested_symbol",
    "candle_time",
    "candle_index",
    "step2_candle_count",
    "open",
    "high",
    "low",
    "close",
    "active_liquidity_name",
    "active_liquidity_display_name",
    "active_liquidity_side",
    "active_liquidity_components",
    "close_boundary",
    "extreme_boundary",
    "wick_boundary_extreme",
    "frozen_tv_level",
    "pre_open_observed_extreme",
    "control_state",
    "conflict_state",
    "step2_status",
    "nearest_level_above",
    "nearest_level_below",
    "step2_before_active",
    "step2_after_active",
    "step2_owner_seeded_at",
    "step2_event",
    "step2_reason",
    "step2_pathway",
    "step2_owner_name",
    "step2_direction",
    "step2_setup_direction",
    "step2_activated_at",
    "step2_confirmed_at",
    "step2_invalidated_at",
    "step25_status",
    "step25_reason",
    "step25_activated_at",
    "step3_status",
    "step3_reason",
    "step3_activated_at",
    "step4_status",
    "step4_event",
    "step4_reason",
    "step4_activated_at",
    "step4_candle_a_time",
    "step4_candle_b_time",
    "step4_rejection_completed_at",
    "step4_invalidated_at",
    "step4_owner_name",
    "step4_direction",
    "step2_step4_50_line",
    "step4_step5_75_line",
    "step4_participation_50_line",
    "step4_participation_75_line",
    "rejection_lane",
    "continuation_lane",
    "step5_status",
    "step5_reason",
    "step5_activated_at",
    "step6_status",
    "step6_reason",
    "step6_activated_at",
}


class EntryAgentAuditLoggingTests(unittest.TestCase):
    def _load_entry_agent(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            spec = importlib.util.spec_from_file_location(
                "entry_agent_audit_under_test",
                ENTRY_AGENT_DIR / "entry_agent.py",
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

    def _snapshot(self, candle_time="2026-06-09T13:37:00Z", close=34990.0):
        group = {
            "name": "PML/ONL",
            "components": ["PML", "ONL"],
            "side": "lower",
            "display_name": "PML/ONL Liquidity",
            "close_boundary": 35000.0,
            "extreme_boundary": 34980.0,
        }
        active = {
            "name": "PML",
            "price": 35000.0,
            "display_name": "PML/ONL Liquidity",
            "side": "lower",
            "group": group,
        }
        return {
            "symbol": "YMM6",
            "normalized_symbol": "YM",
            "requested_symbol": "YM",
            "latest_price": close,
            "latest_bar_time": candle_time,
            "ohlc_is_closed": True,
            "ohlc": {
                "open": 35020.0,
                "high": 35030.0,
                "low": 34985.0,
                "close": close,
            },
            "liquidity": {
                "nearest_level_above": {"name": "ONH", "price": 35200.0},
                "nearest_level_below": {"name": "ONL", "price": 34980.0},
                "tick_size": 1.0,
            },
            "step_2_1a": {
                "step_2_activated": True,
                "audit_step2_before_active": False,
                "audit_step2_event": "step_2_activated",
                "reason": "Step 2.1A evaluated from live completed candle.",
                "candle_index": 12,
                "step2_activation_candle_index": 10,
                "active_level": "PML",
                "level_price": 35000.0,
                  "active_liquidity_group": group,
                  "next_same_side_liquidity": {"name": "ONL", "price": 34980.0},
                  "last_interacted_liquidity": active,
                  "step2_locked_owner": {
                    "pathway": "rejection",
                    "active_liquidity": active,
                    "active_liquidity_name": "PML",
                    "active_liquidity_display_name": "PML/ONL Liquidity",
                    "active_liquidity_group": group,
                    "stack_components": ["PML", "ONL"],
                    "close_boundary": 35000.0,
                    "extreme_boundary": 34980.0,
                    "setup_direction": "LONG",
                    "side": "lower",
                    "activated_at": "2026-06-09T13:27:00Z",
                },
            },
            "step25": {
                "status": "READY",
                "reason": "Step 2.5 pathway selection complete: Normal.",
                "state": {"setup_direction": "LONG", "step25_activated_at": "2026-06-09T13:28:00Z"},
            },
            "step3": {
                "status": "ALLOW_STEP_4",
                "reason": "Step 3 allows structure.",
                "state": {"step3_activated_at": "2026-06-09T13:29:00Z"},
            },
            "step4": {
                "status": "READY",
                "reason": "Leg 1 complete.",
                "state": {"step4_activated_at": "2026-06-09T13:30:00Z"},
            },
            "step5": {
                "status": "READY",
                "reason": "Leg 2 validated.",
                "state": {"step5_activated_at": "2026-06-09T13:31:00Z"},
            },
            "step6": {
                "status": "WAIT",
                "reason": "Entry candidate waiting.",
                "state": {"step6_activated_at": "2026-06-09T13:32:00Z"},
            },
        }

    def test_audit_row_contains_every_required_field(self):
        entry_agent = self._load_entry_agent()
        row = entry_agent.build_entry_agent_audit_row(self._snapshot())
        self.assertTrue(REQUIRED_AUDIT_FIELDS <= set(row))

    def test_step2_activation_row_contains_required_investigation_context(self):
        entry_agent = self._load_entry_agent()
        row = entry_agent.build_entry_agent_audit_row(self._snapshot())
        self.assertEqual(row["candle_time"], "2026-06-09T13:37:00Z")
        self.assertEqual(row["active_liquidity_name"], "PML/ONL Liquidity")
        self.assertEqual(row["active_liquidity_display_name"], "PML/ONL Liquidity")
        self.assertEqual(row["active_liquidity_components"], ["PML", "ONL"])
        self.assertEqual(row["close_boundary"], 35000.0)
        self.assertEqual(row["extreme_boundary"], 34980.0)
        self.assertEqual(row["step2_candle_count"], 2)
        self.assertEqual(row["step2_reason"], "Step 2.1A evaluated from live completed candle.")
        self.assertEqual(row["step2_step4_50_line"], 34990.0)
        self.assertEqual(row["step4_step5_75_line"], 34985.0)
        self.assertEqual(row["rejection_lane"]["lane_status"], "controlling")
        self.assertEqual(row["rejection_lane"]["step2_status"], "CONFIRMED")
        self.assertEqual(row["continuation_lane"]["lane_status"], "idle")

    def test_activation_timestamps_are_preserved_when_present(self):
        entry_agent = self._load_entry_agent()
        row = entry_agent.build_entry_agent_audit_row(self._snapshot())
        self.assertEqual(row["step2_owner_seeded_at"], "2026-06-09T13:27:00Z")
        self.assertEqual(row["step2_activated_at"], "2026-06-09T13:27:00Z")
        self.assertEqual(row["step2_confirmed_at"], "2026-06-09T13:27:00Z")
        self.assertEqual(row["step25_activated_at"], "2026-06-09T13:28:00Z")
        self.assertEqual(row["step3_activated_at"], "2026-06-09T13:29:00Z")
        self.assertEqual(row["step4_activated_at"], "2026-06-09T13:30:00Z")
        self.assertEqual(row["step5_activated_at"], "2026-06-09T13:31:00Z")
        self.assertEqual(row["step6_activated_at"], "2026-06-09T13:32:00Z")
        self.assertEqual(row["step2_owner_name"], "PML/ONL")
        self.assertEqual(row["step2_direction"], "LONG")

    def test_seeded_step4_is_exposed_immediately_after_step2_confirmation(self):
        entry_agent = self._load_entry_agent()
        snapshot = {
            "symbol": "NQM6",
            "requested_symbol": "NQ",
            "normalized_symbol": "NQ",
            "latest_price": 29648.0,
            "latest_bar_time": "2026-06-23T13:30:00Z",
            "ohlc_is_closed": True,
            "ohlc": {
                "open": 29714.75,
                "high": 29717.25,
                "low": 29638.75,
                "close": 29648.0,
                "timestamp": "2026-06-23T13:30:00Z",
            },
            "liquidity": {
                "nearest_level_above": {"name": "PMH", "price": 29740.0},
                "nearest_level_below": {"name": "LL", "price": 29620.0},
                "tick_size": 0.25,
            },
            "step_2_1a": {
                "step_2_activated": True,
                "audit_step2_before_active": False,
                "audit_step2_event": "step_2_activated",
                "reason": "Close below observed extreme confirmed Step 2 LONG rejection pathway.",
                "candle_index": 0,
                "active_level": "PML",
                "level_price": 29691.75,
                "step2_locked_owner": {
                    "pathway": "rejection",
                    "setup_direction": "LONG",
                    "side": "lower",
                    "active_liquidity_name": "PML/ONL Liquidity",
                    "active_liquidity_display_name": "PML/ONL Liquidity",
                    "stack_components": ["PML", "ONL"],
                    "close_boundary": 29691.75,
                    "extreme_boundary": 29675.75,
                    "activated_at": "2026-06-23T13:30:00Z",
                    "active_liquidity": {
                        "name": "PML",
                        "price": 29691.75,
                        "display_name": "PML/ONL Liquidity",
                        "side": "lower",
                    },
                },
                "last_interacted_liquidity": {
                    "name": "PML",
                    "price": 29691.75,
                    "display_name": "PML/ONL Liquidity",
                    "side": "lower",
                },
                "next_same_side_liquidity": {"name": "LL", "price": 29620.0},
            },
            "step25": {
                "status": "READY",
                "reason": "Step 2.5 pathway selection complete: Normal.",
                "state": {"setup_direction": "LONG", "step25_activated_at": "2026-06-23T13:30:00Z"},
            },
            "step3": {
                "status": "ALLOW_STEP_4",
                "reason": "Step 3 allows structure.",
                "state": {"step3_activated_at": "2026-06-23T13:30:00Z"},
            },
            "step4": {
                "status": "WAIT",
                "reason": "Step 4 waiting: Leg 1 window started after Step 2 confirmation; Candle 1 is the next candle.",
                "state": {
                    "step4_activated_at": "2026-06-23T13:30:00Z",
                    "setup_direction": "LONG",
                    "leg1_window_active": True,
                    "leg1_window_started_at": "2026-06-23T13:30:00Z",
                    "leg1_window_candle_index": 0,
                    "leg1_window_remaining": 3,
                    "initial_candle_a": {
                        "open": 29714.75,
                        "high": 29717.25,
                        "low": 29638.75,
                        "close": 29648.0,
                        "timestamp": "2026-06-23T13:30:00Z",
                    },
                },
            },
            "step5": {"status": "WAIT", "reason": "Waiting for Leg 1 completion.", "state": {}},
            "step6": {"status": "WAIT", "reason": "Waiting for Leg 2 completion.", "state": {}},
            "rejection": {"rejection_mode": "ON", "watch_side": "LONG"},
            "pre_open_observed_extreme": {"price": 29675.75, "side": "lower"},
        }

        row = entry_agent.build_entry_agent_audit_row(snapshot)
        self.assertEqual(row["step2_status"], "CONFIRMED")
        self.assertEqual(row["step4_status"], "WAIT")
        self.assertIn("Candle A / index 0", row["step4_reason"])
        self.assertIn("06:30 PT", row["step4_reason"])
        self.assertEqual(row["step4_candle_a_time"], "2026-06-23T13:30:00Z")
        self.assertIsNone(row["step4_candle_b_time"])
        self.assertEqual(row["step4_owner_name"], "PML/ONL")
        self.assertEqual(row["step4_direction"], "LONG")
        self.assertEqual(row["step2_step4_50_line"], 29655.875)
        self.assertEqual(row["step4_step5_75_line"], 29637.9375)

        original_get_latest_market_snapshot = entry_agent.get_latest_market_snapshot
        original_load_entry_state = entry_agent.load_entry_state
        original_run_once = entry_agent.run_once
        original_hide_unconfirmed_current_candle_advancement = entry_agent.hide_unconfirmed_current_candle_advancement
        original_apply_consumed_entry_setup_guard = entry_agent.apply_consumed_entry_setup_guard
        original_active_liquidity_from_snapshot = entry_agent.active_liquidity_from_snapshot
        original_active_liquidity_group_from_snapshot = entry_agent.active_liquidity_group_from_snapshot
        try:
            entry_agent.get_latest_market_snapshot = lambda _symbol: None
            entry_agent.load_entry_state = lambda: {}
            entry_agent.run_once = lambda _symbol, persist=True: snapshot
            entry_agent.hide_unconfirmed_current_candle_advancement = lambda _snapshot: None
            entry_agent.apply_consumed_entry_setup_guard = lambda _snapshot: None
            entry_agent.active_liquidity_from_snapshot = lambda _snapshot: ("PML/ONL Liquidity", 29691.75)
            entry_agent.active_liquidity_group_from_snapshot = lambda _snapshot: {
                "name": "LOW 1",
                "display_name": "PML/ONL Liquidity",
                "components": ["PML", "ONL"],
                "side": "lower",
                "close_boundary": 29691.75,
                "extreme_boundary": 29675.75,
            }

            status = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.get_latest_market_snapshot = original_get_latest_market_snapshot
            entry_agent.load_entry_state = original_load_entry_state
            entry_agent.run_once = original_run_once
            entry_agent.hide_unconfirmed_current_candle_advancement = original_hide_unconfirmed_current_candle_advancement
            entry_agent.apply_consumed_entry_setup_guard = original_apply_consumed_entry_setup_guard
            entry_agent.active_liquidity_from_snapshot = original_active_liquidity_from_snapshot
            entry_agent.active_liquidity_group_from_snapshot = original_active_liquidity_group_from_snapshot

        self.assertEqual(status["step2_status"], "CONFIRMED")
        self.assertEqual(status["step4_status"], "WAIT")
        self.assertEqual(status["step2_step4_50_line"], status["step4_participation_50_line"])
        self.assertEqual(status["step4_step5_75_line"], status["step4_participation_75_line"])
        self.assertEqual(status["step2_owner_name"], "PML/ONL")
        self.assertEqual(status["step2_direction"], "LONG")
        self.assertEqual(status["step2_confirmed_at"], "2026-06-23T13:30:00Z")
        self.assertEqual(status["step4_candle_a_time"], "2026-06-23T13:30:00Z")
        self.assertIsNone(status["step4_candle_b_time"])
        self.assertEqual(status["step4_owner_name"], "PML/ONL")
        self.assertEqual(status["step4_direction"], "LONG")
        self.assertEqual(status["leg1_window_candle_index"], 0)
        self.assertEqual(status["step5_status"], "WAIT")
        self.assertEqual(status["step6_status"], "WAIT")
        self.assertIn("06:30 PT", status["step4_reason"])
        self.assertIn("future Candle B", status["step4_reason"])
        self.assertEqual(status["wait_reason"], status["step4_reason"])

    def test_audit_directory_file_append_and_historical_rows_are_preserved(self):
        entry_agent = self._load_entry_agent()
        with tempfile.TemporaryDirectory() as temp_dir:
            entry_agent.ENTRY_AGENT_AUDIT_DIR = Path(temp_dir)
            first = self._snapshot()
            second = self._snapshot("2026-06-09T13:28:00Z", close=34970.0)
            second["ohlc"]["open"] = 34990.0

            entry_agent.append_entry_agent_audit_row(first)
            audit_path = Path(temp_dir) / "2026-06-09" / "YM_step_audit.jsonl"
            self.assertTrue(audit_path.parent.exists())
            self.assertTrue(audit_path.exists())
            entry_agent.append_entry_agent_audit_row(first)
            self.assertEqual(len(audit_path.read_text(encoding="utf-8").splitlines()), 1)
            original_first_row = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[0])

            entry_agent.append_entry_agent_audit_row(second)
            rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["candle_time"], original_first_row["candle_time"])
            self.assertEqual(rows[0]["open"], original_first_row["open"])
            self.assertEqual(rows[0]["high"], original_first_row["high"])
            self.assertEqual(rows[0]["low"], original_first_row["low"])
            self.assertEqual(rows[0]["close"], original_first_row["close"])
        self.assertEqual(rows[1]["candle_time"], "2026-06-09T13:28:00Z")
        self.assertEqual(rows[1]["open"], 34990.0)

    def test_same_candle_audit_append_repairs_missing_step2_fields(self):
        entry_agent = self._load_entry_agent()
        with tempfile.TemporaryDirectory() as temp_dir:
            entry_agent.ENTRY_AGENT_AUDIT_DIR = Path(temp_dir)
            snapshot = self._snapshot()
            snapshot["step_2_1a"]["step2_activation_candle_index"] = 12
            expected_row = entry_agent.build_entry_agent_audit_row(snapshot)
            candle_date = entry_agent.local_session_date(expected_row["candle_time"])
            audit_path = Path(temp_dir) / candle_date / "YM_step_audit.jsonl"
            audit_path.parent.mkdir(parents=True, exist_ok=True)

            stale_row = dict(expected_row)
            stale_row.pop("step2_candle_count", None)
            stale_row["step2_step4_50_line"] = None
            stale_row["step4_step5_75_line"] = None
            audit_path.write_text(json.dumps(stale_row) + "\n", encoding="utf-8")

            appended = entry_agent.append_entry_agent_audit_row(snapshot)
            repaired = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[0])

            self.assertIsNone(appended)
            self.assertEqual(len(audit_path.read_text(encoding="utf-8").splitlines()), 1)
            self.assertEqual(repaired["candle_time"], expected_row["candle_time"])
            self.assertEqual(repaired["step2_candle_count"], 0)
            self.assertEqual(repaired["step2_step4_50_line"], expected_row["step2_step4_50_line"])
            self.assertEqual(repaired["step4_step5_75_line"], expected_row["step4_step5_75_line"])
            self.assertEqual(repaired["rejection_lane"]["lane_status"], expected_row["rejection_lane"]["lane_status"])

    def test_audit_row_propagates_step2_lines_from_step2_owner_when_step4_state_is_sparse(self):
        entry_agent = self._load_entry_agent()
        snapshot = {
            "symbol": "YMU6",
            "requested_symbol": "YM",
            "normalized_symbol": "YM",
            "latest_price": 52234.0,
            "latest_bar_time": "2026-06-24T13:51:00Z",
            "ohlc_is_closed": True,
            "ohlc": {
                "open": 52204.0,
                "high": 52238.0,
                "low": 52189.0,
                "close": 52234.0,
                "timestamp": "2026-06-24T13:51:00Z",
            },
            "tv_context": {
                "levels": {
                    "PMH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "LH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "ONH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "YH": {"price": 52281.0, "status": "ACTIVE", "stack_group": "NONE"},
                }
            },
            "liquidity": {
                "nearest_level_above": {"name": "YH", "price": 52281.0},
                "nearest_level_below": {"name": "PMH", "price": 52176.0},
                "tick_size": 1.0,
            },
            "step_2_1a": {
                "step_2_activated": True,
                "active_level": "PMH",
                "level_price": 52176.0,
                "side": "upper",
                "step2_activated_at": "2026-06-24T13:50:00Z",
                "step2_locked_owner": {
                    "pathway": "rejection",
                    "setup_direction": "SHORT",
                    "side": "upper",
                    "close_boundary": 52176.0,
                    "extreme_boundary": 52176.0,
                },
            },
            "step25": {
                "status": "READY",
                "reason": "Step 2.5 pathway selection complete: Normal Rejection Mode.",
                "state": {"setup_direction": "SHORT"},
            },
            "step3": {"status": "ALLOW_STEP_4", "reason": "Step 3 allows structure.", "state": {}},
            "step4": {"status": "WAIT", "reason": "Awaiting Candle B.", "state": {}},
            "step5": {"status": "WAIT", "reason": "Waiting.", "state": {}},
            "step6": {"status": "WAIT", "reason": "Waiting.", "state": {}},
        }

        row = entry_agent.build_entry_agent_audit_row(snapshot)

        self.assertEqual(row["step2_candle_count"], 1)
        self.assertEqual(row["step2_step4_50_line"], 52228.5)
        self.assertEqual(row["step4_step5_75_line"], 52254.75)
        self.assertEqual(row["rejection_lane"]["lane_status"], "controlling")
        self.assertEqual(row["continuation_lane"]["lane_status"], "idle")

    def test_audit_row_persists_step4_invalidation_reason_when_50_line_is_touched(self):
        entry_agent = self._load_entry_agent()
        snapshot = self._snapshot()
        snapshot["step4"] = {
            "status": "TERMINATED",
            "reason": "STEP2_STEP4_50_LINE_TOUCHED",
            "events": [{"event": "step7_interaction_terminated", "source_step": "Step 4", "reason": "STEP2_STEP4_50_LINE_TOUCHED"}],
            "state": {
                "invalidation_source": "step2_step4_50_line",
                "invalidation_source_step": "Step 4",
                "invalidation_source_candle_time": "2026-06-09T13:37:00Z",
                "leg1_window_invalidation_reason": "STEP2_STEP4_50_LINE_TOUCHED",
            },
        }
        row = entry_agent.build_entry_agent_audit_row(snapshot)
        self.assertEqual(row["step4_status"], "TERMINATED")
        self.assertEqual(row["step4_event"], "step7_interaction_terminated")
        self.assertEqual(row["invalidation_reason"], "STEP2_STEP4_50_LINE_TOUCHED")
        self.assertEqual(row["rejection_lane"]["lane_status"], "invalidated")
        self.assertEqual(row["rejection_lane"]["invalidation_reason"], "STEP2_STEP4_50_LINE_TOUCHED")

    def test_observation_window_audit_row_uses_frozen_display_level_and_blocked_statuses(self):
        entry_agent = self._load_entry_agent()
        snapshot = self._snapshot("2026-06-09T13:27:00Z", close=34978.0)
        snapshot["latest_bar_time"] = "2026-06-09T13:27:00Z"
        snapshot["ohlc"] = {"open": 35005.0, "high": 35006.0, "low": 34970.0, "close": 34978.0}
        snapshot["liquidity"] = {"tick_size": 1.0}
        snapshot["tv_context"] = {
            "locked": True,
            "context_locked": True,
            "locked_for_day": True,
            "levels": {
                "PML": {"price": 35000.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "ONL": {"price": 34980.0, "status": "ACTIVE", "stack_group": "LOW 1"},
            },
        }
        snapshot["pre_open_observed_extreme"] = {"side": "lower", "price": 34970.0, "source_level": "PML", "stack_group": "LOW 1"}
        snapshot["step_2_1a"] = {"step_2_activated": False, "blocked": True, "reason": "observation", "events": []}
        snapshot["step25"] = {"status": "WAIT", "reason": "observation", "state": {}}
        snapshot["step3"] = {"status": "WAIT", "reason": "observation", "state": {}}
        snapshot["step4"] = {"status": "WAIT", "reason": "observation", "state": {}}
        snapshot["step5"] = {"status": "WAIT", "reason": "observation", "state": {}}
        snapshot["step6"] = {"status": "WAIT", "reason": "observation", "state": {}}

        row = entry_agent.build_entry_agent_audit_row(snapshot)

        self.assertEqual(row["active_liquidity_name"], "PML/ONL Liquidity")
        self.assertEqual(row["close_boundary"], 35000.0)
        self.assertEqual(row["extreme_boundary"], 34980.0)
        self.assertEqual(row["wick_boundary_extreme"], 34970.0)
        self.assertEqual(row["frozen_tv_level"], 35000.0)
        self.assertEqual(row["pre_open_observed_extreme"], 34970.0)
        self.assertNotIn("actionable_boundary_price", row)
        self.assertEqual(row["control_state"], "OBSERVATION_ONLY")
        self.assertEqual(row["conflict_state"], "NONE_PREOPEN")
        self.assertEqual(row["step2_status"], "WAIT")
        self.assertEqual(row["step25_status"], "BLOCKED_PREOPEN_OBSERVATION")
        self.assertEqual(row["step4_status"], "WAIT")
        self.assertEqual(row["step5_status"], "BLOCKED_PREOPEN_OBSERVATION")
        self.assertEqual(row["step6_status"], "BLOCKED_PREOPEN_OBSERVATION")


if __name__ == "__main__":
    unittest.main()
