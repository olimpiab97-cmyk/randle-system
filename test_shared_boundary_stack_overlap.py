from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENTRY_AGENT_DIR = ROOT / "EntryAgent"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ENTRY_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(ENTRY_AGENT_DIR))

import entry_agent
import tv_context_server
from liquidity_stack_validation import validate_liquidity_stack_structure


def level(price: float, *stack_groups: str) -> dict[str, object]:
    memberships = list(stack_groups)
    return {
        "price": price,
        "status": "ACTIVE",
        "stack_group": memberships[0] if len(memberships) == 1 else None,
        "stack_groups": memberships,
        "stack_display": " / ".join(memberships) if memberships else "NONE",
    }


def overlapping_payload(
    *,
    symbol: str,
    reference: float,
    threshold: float,
    levels: dict[str, dict[str, object]],
    stacks: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "source": "tradingview_level_helper",
        "version": "v14_overlapping_stack_smoke",
        "symbol": symbol,
        "timestamp": "2026-07-17T13:15:00Z",
        "session_date": "2026-07-17",
        "time_zone": "America/Los_Angeles",
        "locked": True,
        "session_locked": True,
        "session_lock_price": reference,
        "stack_threshold": threshold,
        "daily_atr14": threshold * 10,
        "levels": levels,
        "stacks": copy.deepcopy(stacks),
        "liquidity_map": {"stacks": copy.deepcopy(stacks)},
        "midpoints": {},
        "exhaustion_boundaries": {},
    }


class SharedBoundaryStackOverlapTests(unittest.TestCase):
    def test_exact_ym_overlap_builds_separate_production_owners_and_command_center_projection(self) -> None:
        levels = {
            "PMH": level(53002, "HIGH 1"),
            "LH": level(53057, "HIGH 1", "HIGH 2"),
            "ONH": level(53057, "HIGH 1", "HIGH 2"),
            "YH": level(53108, "HIGH 2"),
        }
        stacks = [
            {"id": "HIGH 1", "side": "HIGH", "members": ["PMH", "LH", "ONH"], "innermost_price": 53002, "outermost_price": 53057},
            {"id": "HIGH 2", "side": "HIGH", "members": ["LH", "ONH", "YH"], "innermost_price": 53057, "outermost_price": 53108},
        ]
        payload = overlapping_payload(
            symbol="YM1!",
            reference=52900,
            threshold=60,
            levels=levels,
            stacks=stacks,
        )

        context, error = tv_context_server.build_context(copy.deepcopy(payload))
        self.assertIsNone(error)
        self.assertIsNotNone(context)
        session = entry_agent.build_session_locked_tv_context(context)
        self.assertIsNotNone(session)
        self.assertTrue(session["locked"])
        owners = {group["name"]: group for group in session["active_groups"]}
        self.assertEqual(set(owners), {"HIGH 1", "HIGH 2"})
        self.assertEqual(owners["HIGH 1"]["components"], ["ONH", "LH", "PMH"])
        self.assertEqual(owners["HIGH 2"]["components"], ["YH", "ONH", "LH"])

        projection = tv_context_server.build_tv_ladder_validation_projection(copy.deepcopy(payload))
        self.assertTrue(projection["entry_agent_processing"]["accepted"])
        self.assertIsNone(projection["first_divergence"])
        self.assertEqual(
            [owner["name"] for owner in projection["entry_agent_resolved"]["resolved_owners"]],
            ["HIGH 2", "HIGH 1"],
        )
        self.assertNotIn(
            "HIGH 1 / HIGH 2",
            [owner["name"] for owner in projection["entry_agent_resolved"]["resolved_owners"]],
        )
        resolved_groups = {
            group["name"]: group["components"]
            for group in projection["entry_agent_resolved"]["session_lock"]["active_groups"]
        }
        self.assertEqual(resolved_groups["HIGH 1"], ["ONH", "LH", "PMH"])
        self.assertEqual(resolved_groups["HIGH 2"], ["YH", "ONH", "LH"])
        resolved_stacks = {
            stack.get("stack_group") or stack.get("id") or stack.get("name"): stack["members"]
            for stack in projection["entry_agent_resolved"]["contract"]["stacks"]
        }
        self.assertEqual(resolved_stacks["HIGH 1"], ["PMH", "LH", "ONH"])
        self.assertEqual(resolved_stacks["HIGH 2"], ["LH", "ONH", "YH"])

    def test_low_side_equivalent_is_valid(self) -> None:
        levels = {
            "PML": level(52900, "LOW 1"),
            "LL": level(52850, "LOW 1", "LOW 2"),
            "ONL": level(52850, "LOW 1", "LOW 2"),
            "YL": level(52800, "LOW 2"),
        }
        stacks = [
            {"id": "LOW 1", "side": "LOW", "members": ["PML", "LL", "ONL"]},
            {"id": "LOW 2", "side": "LOW", "members": ["LL", "ONL", "YL"]},
        ]
        payload = overlapping_payload(
            symbol="YM1!",
            reference=53000,
            threshold=50,
            levels=levels,
            stacks=stacks,
        )

        context, error = tv_context_server.build_context(payload)
        self.assertIsNone(error)
        session = entry_agent.build_session_locked_tv_context(context)
        self.assertTrue(session["locked"])
        self.assertEqual({group["name"] for group in session["active_groups"]}, {"LOW 1", "LOW 2"})

    def test_overlap_across_different_prices_is_rejected(self) -> None:
        levels = {
            "PMH": level(100, "HIGH 1"),
            "LH": level(105, "HIGH 1", "HIGH 2"),
            "ONH": level(106, "HIGH 1", "HIGH 2"),
            "YH": level(111, "HIGH 2"),
        }
        stacks = [
            {"id": "HIGH 1", "side": "HIGH", "members": ["PMH", "LH", "ONH"]},
            {"id": "HIGH 2", "side": "HIGH", "members": ["LH", "ONH", "YH"]},
        ]
        _, error = tv_context_server.build_context(
            overlapping_payload(symbol="YM1!", reference=90, threshold=10, levels=levels, stacks=stacks)
        )
        self.assertEqual(error["code"], "STACK_MEMBER_OVERLAP")

    def test_arbitrary_interior_overlap_is_rejected(self) -> None:
        levels = {
            "PMH": level(100, "HIGH 1"),
            "LH": level(105, "HIGH 1", "HIGH 2"),
            "ONH": level(110, "HIGH 1"),
            "YH": level(115, "HIGH 2"),
        }
        stacks = [
            {"id": "HIGH 1", "side": "HIGH", "members": ["PMH", "LH", "ONH"]},
            {"id": "HIGH 2", "side": "HIGH", "members": ["LH", "YH"]},
        ]
        _, error = tv_context_server.build_context(
            overlapping_payload(symbol="YM1!", reference=90, threshold=10, levels=levels, stacks=stacks)
        )
        self.assertEqual(error["code"], "STACK_MEMBER_OVERLAP")

    def test_missing_reciprocal_boundary_member_is_rejected(self) -> None:
        levels = {
            "PMH": level(100, "HIGH 1"),
            "LH": level(105, "HIGH 1", "HIGH 2"),
            "ONH": level(105, "HIGH 1"),
            "YH": level(110, "HIGH 2"),
        }
        stacks = [
            {"id": "HIGH 1", "side": "HIGH", "members": ["PMH", "LH", "ONH"]},
            {"id": "HIGH 2", "side": "HIGH", "members": ["LH", "YH"]},
        ]
        _, error = tv_context_server.build_context(
            overlapping_payload(symbol="YM1!", reference=90, threshold=5, levels=levels, stacks=stacks)
        )
        self.assertEqual(error["code"], "STACK_BOUNDARY_RECIPROCAL_MEMBERS_MISSING")

    def test_single_stack_no_stack_and_full_span_rejection_are_unchanged(self) -> None:
        single = {
            "PMH": {"price": 100, "status": "ACTIVE", "stack_group": "HIGH 1"},
            "LH": {"price": 105, "status": "ACTIVE", "stack_group": "HIGH 1"},
        }
        self.assertIsNone(
            validate_liquidity_stack_structure(single, stack_threshold=5, session_reference_price=90)
        )
        self.assertIsNone(
            validate_liquidity_stack_structure(
                {"PMH": {"price": 100, "status": "ACTIVE", "stack_group": "NONE"}},
                stack_threshold=None,
                session_reference_price=90,
            )
        )

        merged = {
            "PMH": level(100, "HIGH 1"),
            "LH": level(105, "HIGH 1"),
            "ONH": level(105, "HIGH 1"),
            "YH": level(110, "HIGH 1"),
        }
        error = validate_liquidity_stack_structure(
            merged,
            stack_threshold=5,
            session_reference_price=90,
        )
        self.assertEqual(error["code"], "STACK_FULL_SPAN_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
