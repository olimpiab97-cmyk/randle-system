"""Focused tests for the isolated pre-open TradingView ladder projection."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent
ENTRY_AGENT_DIR = ROOT / "EntryAgent"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ENTRY_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(ENTRY_AGENT_DIR))

import tv_context_server as server


def active_level(
    price: float,
    stack_group: str | None = "NONE",
    stack_groups: list[str] | None = None,
    stack_display: str | None = None,
) -> dict[str, object]:
    return {
        "price": price,
        "status": "ACTIVE",
        "stack_group": stack_group,
        "stack_groups": list(stack_groups or []),
        "stack_display": stack_display if stack_display is not None else stack_group or "NONE",
    }


def valid_distinct_owner_payload(*, version: str = "locked-1", timestamp: str = "2026-07-17T13:15:00Z") -> dict[str, object]:
    return {
        "source": "tradingview_level_helper",
        "version": version,
        "symbol": "NQ1!",
        "timestamp": timestamp,
        "session_date": "2026-07-17",
        "session_locked": True,
        "session_lock_price": 90,
        "stack_threshold": 2,
        "daily_atr14": 20,
        "levels": {
            "PMH": active_level(100, "HIGH 1", ["HIGH 1"]),
            "LH": active_level(101, "HIGH 1", ["HIGH 1"]),
            "ONH": active_level(110, "HIGH 2", ["HIGH 2"]),
            "YH": active_level(111, "HIGH 2", ["HIGH 2"]),
        },
        "liquidity_map": {
            "stacks": [
                {"name": "HIGH 1", "side": "HIGH", "members": ["PMH", "LH"]},
                {"name": "HIGH 2", "side": "HIGH", "members": ["ONH", "YH"]},
            ]
        },
        "midpoints": {"HIGH 2_HIGH 1": 105.5},
        "exhaustion_boundaries": {
            "HIGH 2_HIGH 1": {"side": "high", "mid_50": 105.5, "remaining_25": 108.25}
        },
    }


class PreopenLadderProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        server.TV_LADDER_VALIDATION_BY_SYMBOL.clear()

    def tearDown(self) -> None:
        server.TV_LADDER_VALIDATION_BY_SYMBOL.clear()

    def test_exact_captured_finalized_payload_is_preserved_and_resolved_without_writes(self) -> None:
        payload_path = ROOT / "tradingview_overlap_finalized_table_state_payload_2026-07-17_003304_PT.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))

        with (
            mock.patch.object(server, "safe_write_json", side_effect=AssertionError("test projection attempted persistence")),
            mock.patch.object(server, "run_once", side_effect=AssertionError("test projection attempted lifecycle processing")),
        ):
            projection = server.build_tv_ladder_validation_projection(payload)

        self.assertEqual(projection["label"], "TEST / UNVERIFIED OVERLAPPING STACK PAYLOAD")
        self.assertEqual(projection["received_payload"], payload)
        self.assertEqual(projection["version"], "v14_overlapping_stack_smoke")
        self.assertIsNone(projection["source_payload_timestamp"])
        self.assertTrue(projection["entry_agent_processing"]["accepted"])
        self.assertEqual(projection["comparisons"]["received_payload_to_entry_agent"]["status"], "MATCH")
        self.assertFalse(projection["authorizes_entries"])
        self.assertFalse(projection["alters_live_trade_state"])
        self.assertFalse(projection["writes_canonical_persistence"])
        self.assertFalse(projection["trade_ready"])
        resolved_levels = projection["entry_agent_resolved"]["contract"]["levels"]
        self.assertEqual(len(resolved_levels), len(payload["levels"]))
        self.assertEqual([row["price"] for row in resolved_levels], sorted((row["price"] for row in payload["levels"].values()), reverse=True))

    def test_normal_entry_path_keeps_distinct_high_owners_and_complete_contract(self) -> None:
        projection = server.build_tv_ladder_validation_projection(valid_distinct_owner_payload())

        self.assertTrue(projection["entry_agent_processing"]["accepted"])
        resolved = projection["entry_agent_resolved"]
        self.assertEqual([owner["name"] for owner in resolved["resolved_owners"]], ["HIGH 2", "HIGH 1"])
        self.assertNotIn("HIGH 1 / HIGH 2", [owner["name"] for owner in resolved["resolved_owners"]])
        self.assertEqual([stack["name"] for stack in resolved["contract"]["stacks"]], ["HIGH 1", "HIGH 2"])
        self.assertEqual(resolved["contract"]["midpoints"], {"HIGH 2_HIGH 1": 105.5})
        self.assertEqual(
            resolved["contract"]["exhaustion_boundaries"]["HIGH 2_HIGH 1"]["remaining_25"],
            108.25,
        )
        rows = {row["name"]: row for row in resolved["contract"]["levels"]}
        self.assertEqual(rows["PMH"]["stack_groups"], ["HIGH 1"])
        self.assertEqual(rows["ONH"]["stack_groups"], ["HIGH 2"])

    def test_multi_membership_payload_renders_distinct_received_and_production_resolved_owners(self) -> None:
        payload = {
            "source": "tradingview_level_helper",
            "version": "v14_overlapping_stack_smoke",
            "symbol": "YM1!",
            "timestamp": "2026-07-17T13:15:00Z",
            "session_date": "2026-07-17",
            "session_locked": True,
            "session_lock_price": 90,
            "stack_threshold": 20,
            "daily_atr14": 200,
            "levels": {
                "PMH": active_level(100, "HIGH 1", ["HIGH 1"], "HIGH 1"),
                "LH": active_level(105, None, ["HIGH 1", "HIGH 2"], "HIGH 1 / HIGH 2"),
                "ONH": active_level(110, "HIGH 2", ["HIGH 2"], "HIGH 2"),
            },
            "stacks": [
                {"id": "HIGH 1", "side": "HIGH", "members": ["PMH", "LH"], "innermost_price": 100, "outermost_price": 105},
                {"id": "HIGH 2", "side": "HIGH", "members": ["LH", "ONH"], "innermost_price": 105, "outermost_price": 110},
            ],
            "liquidity_map": {
                "stacks": [
                    {"id": "HIGH 1", "side": "HIGH", "members": ["PMH", "LH"], "innermost_price": 100, "outermost_price": 105},
                    {"id": "HIGH 2", "side": "HIGH", "members": ["LH", "ONH"], "innermost_price": 105, "outermost_price": 110},
                ]
            },
            "midpoints": {},
            "exhaustion_boundaries": {},
        }

        projection = server.build_tv_ladder_validation_projection(payload)

        self.assertTrue(projection["entry_agent_processing"]["accepted"])
        self.assertEqual(projection["comparisons"]["received_payload_to_entry_agent"]["status"], "MATCH")
        self.assertIsNone(projection["first_divergence"])
        received_owners = projection["received_table"]["resolved_owner_ladder"]
        self.assertEqual([owner["name"] for owner in received_owners], ["HIGH 2", "HIGH 1"])
        self.assertNotIn("HIGH 1 / HIGH 2", [owner["name"] for owner in received_owners])
        self.assertEqual(projection["received_payload"], payload)
        resolved_owners = projection["entry_agent_resolved"]["resolved_owners"]
        self.assertEqual([owner["name"] for owner in resolved_owners], ["HIGH 2", "HIGH 1"])
        self.assertNotIn("HIGH 1 / HIGH 2", [owner["name"] for owner in resolved_owners])
        self.assertFalse(projection["trade_ready"])

    def test_first_locked_payload_is_frozen_for_test_display_while_latest_receipts_continue(self) -> None:
        preopen = valid_distinct_owner_payload(version="preopen", timestamp="2026-07-17T12:00:00Z")
        preopen["session_locked"] = False
        locked = valid_distinct_owner_payload(version="locked-1", timestamp="2026-07-17T13:15:00Z")
        later = valid_distinct_owner_payload(version="later", timestamp="2026-07-17T13:16:00Z")
        later["levels"]["YH"]["price"] = 112

        for payload in (preopen, locked, later):
            context, error = server.build_context(copy.deepcopy(payload))
            self.assertIsNone(error)
            server.capture_tv_ladder_validation_projection(payload, context=context)

        response = server.app.test_client().get("/debug/tv-ladder-validation")
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        nq = next(item for item in result["symbols"] if item["symbol"] == "NQ")
        self.assertTrue(nq["first_locked_captured"])
        self.assertEqual(nq["capture_phase"], "FIRST_LOCKED")
        self.assertEqual(nq["version"], "locked-1")
        self.assertFalse(result["authorizes_entries"])
        self.assertFalse(result["writes_canonical_persistence"])

    def test_command_center_uses_direct_test_projection_and_never_coalesces_owner_labels(self) -> None:
        page = (ROOT / "command_center.html").read_text(encoding="utf-8")

        self.assertIn("TEST / UNVERIFIED OVERLAPPING STACK PAYLOAD", page)
        self.assertIn("/debug/tv-ladder-validation", page)
        self.assertIn('get("tv_ladder_test") === "1"', page)
        self.assertIn("Exact Received Explicit Stack Objects - Distinct Owners", page)
        self.assertIn("Entry Agent Resolved Owners / Ladder Order", page)
        self.assertIn('members.join(", ")', page)
        self.assertNotIn('members.join(" / ")', page)
        self.assertIn("NOT TRADE READY", page)


if __name__ == "__main__":
    unittest.main()
