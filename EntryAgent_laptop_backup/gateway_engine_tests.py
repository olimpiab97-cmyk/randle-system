"""Unit tests for gateway_engine.py."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from gateway_engine import evaluate_gateway

PT = ZoneInfo("America/Los_Angeles")


def at_pt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 4, 27, hour, minute, tzinfo=PT)


def base_snapshot(price: float = 100.0, current_location: str = "BETWEEN_LEVELS") -> dict:
    return {
        "latest_price": price,
        "liquidity": {
            "current_location": current_location,
        },
    }


def test_premarket_blocks_before_premarket_locked() -> None:
    result = evaluate_gateway(
        base_snapshot(),
        {"session_context": {"premarket_locked": False}, "gateway": {"state": "ARMED"}},
        {"PMH": 101},
        {},
        at_pt(8),
    )
    assert result["session_phase"] == "PREMARKET"
    assert result["gateway_status"] == "BLOCKED"


def test_closed_blocks_after_noon_pt() -> None:
    result = evaluate_gateway(base_snapshot(), {"gateway": {"state": "ARMED"}}, {"PMH": 101}, {}, at_pt(12, 1))
    assert result["session_phase"] == "CLOSED"
    assert result["gateway_status"] == "BLOCKED"


def test_missing_gateway_object_blocks() -> None:
    result = evaluate_gateway(base_snapshot(), {}, {"PMH": 101}, {}, at_pt(8))
    assert result["gateway_status"] == "BLOCKED"
    assert "Missing pre-built gateway object" in result["gateway_reason"]


def test_gateway_state_off_blocks() -> None:
    result = evaluate_gateway(base_snapshot(), {"gateway": {"state": "OFF"}}, {"PMH": 101}, {}, at_pt(8))
    assert result["gateway_status"] == "BLOCKED"
    assert result["allowed_sides"] == "NONE"


def test_gateway_state_armed_opens() -> None:
    result = evaluate_gateway(base_snapshot(), {"gateway": {"state": "ARMED"}}, {"PMH": 101}, {}, at_pt(8))
    assert result["gateway_status"] == "OPEN"


def test_armed_with_no_rejection_allows_both() -> None:
    result = evaluate_gateway(base_snapshot(), {"gateway": {"state": "ARMED"}}, {"PMH": 101}, {}, at_pt(8))
    assert result["allowed_sides"] == "BOTH"


def test_armed_with_long_rejection_allows_long_only() -> None:
    result = evaluate_gateway(
        base_snapshot(),
        {"gateway": {"state": "ARMED"}},
        {"PMH": 101},
        {"rejection_mode": "ON", "watch_side": "LONG"},
        at_pt(8),
    )
    assert result["allowed_sides"] == "LONG"


def test_armed_with_short_rejection_allows_short_only() -> None:
    result = evaluate_gateway(
        base_snapshot(),
        {"gateway": {"state": "ARMED"}},
        {"PMH": 101},
        {"rejection_mode": "ON", "watch_side": "SHORT"},
        at_pt(8),
    )
    assert result["allowed_sides"] == "SHORT"


def test_at_liquidity_sets_near_liquidity_true() -> None:
    result = evaluate_gateway(
        base_snapshot(current_location="AT_LIQUIDITY"),
        {"gateway": {"state": "ARMED"}},
        {"PMH": 101},
        {},
        at_pt(8),
    )
    assert result["near_liquidity"] is True


def test_active_stack_containment_sets_near_liquidity_true() -> None:
    result = evaluate_gateway(
        base_snapshot(price=105, current_location="BETWEEN_LEVELS"),
        {
            "gateway": {"state": "ARMED"},
            "high_side": {
                "type": "STACK",
                "close_boundary": 100,
                "extreme_boundary": 110,
            },
        },
        {"PMH": 101},
        {},
        at_pt(8),
    )
    assert result["near_liquidity"] is True


def test_nearest_level_prefers_tv_context_next_liquidity() -> None:
    result = evaluate_gateway(
        base_snapshot(price=100),
        {
            "gateway": {"state": "ARMED"},
            "next_liquidity": {
                "above": {"name": "ONH", "price": 150},
                "below": {"name": "ONL", "price": 50},
            },
        },
        {"PMH": 101},
        {},
        at_pt(8),
    )
    assert result["nearest_level"] == "ONH"


def test_fallback_nearest_level_when_next_liquidity_missing() -> None:
    result = evaluate_gateway(
        base_snapshot(price=100),
        {"gateway": {"state": "ARMED"}},
        {"PMH": 110, "PML": 99, "ONH": 130},
        {},
        at_pt(8),
    )
    assert result["nearest_level"] == "PML"


def run_tests() -> None:
    tests = [
        test_premarket_blocks_before_premarket_locked,
        test_closed_blocks_after_noon_pt,
        test_missing_gateway_object_blocks,
        test_gateway_state_off_blocks,
        test_gateway_state_armed_opens,
        test_armed_with_no_rejection_allows_both,
        test_armed_with_long_rejection_allows_long_only,
        test_armed_with_short_rejection_allows_short_only,
        test_at_liquidity_sets_near_liquidity_true,
        test_active_stack_containment_sets_near_liquidity_true,
        test_nearest_level_prefers_tv_context_next_liquidity,
        test_fallback_nearest_level_when_next_liquidity_missing,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} gateway_engine tests passed")


if __name__ == "__main__":
    run_tests()
