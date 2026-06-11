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
    "nearest_level_above",
    "nearest_level_below",
    "step2_before_active",
    "step2_after_active",
    "step2_event",
    "step2_reason",
    "step2_pathway",
    "step2_setup_direction",
    "step2_activated_at",
    "step25_status",
    "step25_reason",
    "step25_activated_at",
    "step3_status",
    "step3_reason",
    "step3_activated_at",
    "step4_status",
    "step4_reason",
    "step4_activated_at",
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

    def _snapshot(self, candle_time="2026-06-09T13:27:00Z", close=34990.0):
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
                "active_level": "PML",
                "level_price": 35000.0,
                "active_liquidity_group": group,
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
        self.assertEqual(row["candle_time"], "2026-06-09T13:27:00Z")
        self.assertEqual(row["active_liquidity_name"], "PML")
        self.assertEqual(row["active_liquidity_display_name"], "PML/ONL Liquidity")
        self.assertEqual(row["active_liquidity_components"], ["PML", "ONL"])
        self.assertEqual(row["close_boundary"], 35000.0)
        self.assertEqual(row["extreme_boundary"], 34980.0)
        self.assertEqual(row["step2_reason"], "Step 2.1A evaluated from live completed candle.")

    def test_activation_timestamps_are_preserved_when_present(self):
        entry_agent = self._load_entry_agent()
        row = entry_agent.build_entry_agent_audit_row(self._snapshot())
        self.assertEqual(row["step2_activated_at"], "2026-06-09T13:27:00Z")
        self.assertEqual(row["step25_activated_at"], "2026-06-09T13:28:00Z")
        self.assertEqual(row["step3_activated_at"], "2026-06-09T13:29:00Z")
        self.assertEqual(row["step4_activated_at"], "2026-06-09T13:30:00Z")
        self.assertEqual(row["step5_activated_at"], "2026-06-09T13:31:00Z")
        self.assertEqual(row["step6_activated_at"], "2026-06-09T13:32:00Z")

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


if __name__ == "__main__":
    unittest.main()
