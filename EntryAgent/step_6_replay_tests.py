"""Focused replay tests for Step 6 only."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from step6_engine import evaluate_step6


def candle(open_price: float, high: float, low: float, close: float, **extra) -> dict:
    payload = {"open": open_price, "high": high, "low": low, "close": close}
    payload.update(extra)
    return payload


def base_interaction(direction: str = "SHORT", anchor: dict | None = None) -> dict:
    anchor_candle = anchor or candle(100.0, 102.0, 99.0, 100.0)
    return {
        "system_state": "REJECTION MODE ON",
        "trade_mode": "ON",
        "rejection_mode": "ON",
        "interaction_state": "ACTIVE",
        "setup_direction": direction,
        "step5_confirmed": True,
        "leg2_status": "CONFIRMED",
        "structure_status": "VALID",
        "structure_valid": True,
        "active_step5_path": "5.1",
        "leg2_candle": anchor_candle,
        "tick_size": 0.25,
        "events": [],
    }


def assert_reason(result: dict) -> None:
    assert result.get("reason"), result


def apply_candles(state: dict, candles: list[dict]) -> dict:
    result = {}
    current = state
    for item in candles:
        result = evaluate_step6(current, item)
        current = result["state"]
    return result


def phase1_to_candle4(state: dict, candle4: dict) -> dict:
    return apply_candles(
        state,
        [
            candle(100.0, 101.0, 99.5, 100.0),
            candle(100.0, 101.0, 99.5, 100.0),
            candle(100.0, 101.0, 99.5, 100.0),
            candle4,
        ],
    )


def phase2_ready_state() -> dict:
    result = phase1_to_candle4(
        base_interaction("SHORT"),
        candle(100.0, 101.0, 99.5, 100.0, failed_entry_participation=True),
    )
    assert result["status"] == "WAIT"
    assert result["state"]["step6_phase"] == "PHASE2"
    return result["state"]


def test_phase1_entry_triggers_on_candle4_valid() -> None:
    result = phase1_to_candle4(base_interaction("SHORT"), candle(100.0, 102.25, 99.5, 100.25))
    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["entry_type"] == "Large Wick Sweep"
    assert result["state"]["interaction_state"] == "CONSUMED"
    assert result["state"]["structure_status"] == "LOCKED"
    assert_reason(result)


def test_phase1_entry_before_candle4_blocked() -> None:
    result = evaluate_step6(base_interaction("SHORT"), candle(100.0, 102.25, 99.5, 100.25))
    assert result["status"] == "WAIT"
    assert result["next_step"] == "Step 6"
    assert result["state"]["phase1_candle_count"] == 1
    assert result["state"]["step6_window_active"] is True
    assert result["state"]["step6_window_candle_index"] == 1
    assert result["state"]["step6_window_remaining"] == 3
    assert result["state"].get("entry_triggered") is not True
    assert_reason(result)


def test_phase1_no_entry_on_candle4_without_failed_participation_invalid() -> None:
    result = phase1_to_candle4(base_interaction("SHORT"), candle(100.0, 101.0, 99.5, 100.0))
    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert result["state"]["step6_window_active"] is False
    assert result["state"]["step6_window_candle_index"] == 4
    assert result["state"]["step6_window_remaining"] == 0
    assert_reason(result)


def test_phase1_starts_from_carried_step6_window_index() -> None:
    state = base_interaction("SHORT")
    state.update(
        {
            "step6_window_started_at": "2026-05-28T13:45:00Z",
            "step6_window_active": True,
            "step6_window_candle_index": 2,
            "step6_window_remaining": 2,
            "step6_window_expires_at": "2026-05-28T13:49:00Z",
        }
    )

    result = evaluate_step6(state, candle(100.0, 101.0, 99.5, 100.0, timestamp="2026-05-28T13:48:00Z"))

    assert result["status"] == "WAIT"
    assert result["state"]["phase1_candle_count"] == 3
    assert result["state"]["step6_window_candle_index"] == 3
    assert result["state"]["step6_window_remaining"] == 1


def test_phase1_same_run_handoff_does_not_double_count_carried_candle() -> None:
    state = base_interaction("SHORT")
    state.update(
        {
            "step6_window_started_at": "2026-05-28T13:45:00Z",
            "step6_window_active": True,
            "step6_window_candle_index": 1,
            "step6_window_remaining": 3,
            "step6_window_expires_at": "2026-05-28T13:49:00Z",
        }
    )

    result = evaluate_step6(state, candle(100.0, 101.0, 99.5, 100.0, timestamp="2026-05-28T13:46:00Z"))

    assert result["status"] == "WAIT"
    assert result["state"]["phase1_candle_count"] == 1
    assert result["state"]["step6_window_candle_index"] == 1
    assert result["state"]["step6_window_remaining"] == 3


def test_phase1_failed_participation_activates_phase2() -> None:
    result = phase1_to_candle4(
        base_interaction("SHORT"),
        candle(100.0, 101.0, 99.5, 100.0, failed_entry_participation=True),
    )
    assert result["status"] == "WAIT"
    assert result["next_step"] == "Step 6"
    assert result["state"]["step6_phase"] == "PHASE2"
    assert result["state"]["phase2_candle_count"] == 0
    assert_reason(result)


def test_phase2_c1_a_c2_b_triggers_entry() -> None:
    state = phase2_ready_state()
    result = apply_candles(
        state,
        [
            candle(100.0, 101.0, 99.0, 100.0),
            candle(100.0, 101.25, 99.5, 100.0),
        ],
    )
    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["state"]["phase2_active_a_candle_number"] == 1
    assert result["state"]["phase2_b_candle_number"] == 2
    assert_reason(result)


def test_phase2_c2_a_c3_b_triggers_entry() -> None:
    state = phase2_ready_state()
    result = apply_candles(
        state,
        [
            candle(100.0, 100.5, 99.0, 100.0),
            candle(100.0, 101.0, 99.0, 100.0),
            candle(100.0, 101.25, 99.5, 100.0),
        ],
    )
    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["state"]["phase2_active_a_candle_number"] == 2
    assert result["state"]["phase2_b_candle_number"] == 3
    assert_reason(result)


def test_phase2_c3_a_c4_b_triggers_entry() -> None:
    state = phase2_ready_state()
    result = apply_candles(
        state,
        [
            candle(100.0, 100.5, 99.0, 100.0),
            candle(100.0, 100.25, 99.0, 100.0),
            candle(100.0, 101.0, 99.0, 100.0),
            candle(100.0, 101.25, 99.5, 100.0),
        ],
    )
    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["state"]["phase2_active_a_candle_number"] == 3
    assert result["state"]["phase2_b_candle_number"] == 4
    assert_reason(result)


def test_phase2_c4_as_a_only_invalid() -> None:
    state = phase2_ready_state()
    result = apply_candles(
        state,
        [
            candle(100.0, 100.5, 99.0, 100.0),
            candle(100.0, 100.25, 99.0, 100.0),
            candle(100.0, 100.25, 99.0, 100.0),
            candle(100.0, 101.0, 99.0, 101.0),
        ],
    )
    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert "A only" in result["reason"]


def test_phase2_no_b_by_c4_invalid() -> None:
    state = phase2_ready_state()
    result = apply_candles(
        state,
        [
            candle(100.0, 100.5, 99.0, 100.0),
            candle(100.0, 100.25, 99.0, 100.0),
            candle(100.0, 100.25, 99.0, 100.0),
            candle(100.0, 100.25, 99.0, 100.0),
        ],
    )
    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert_reason(result)


def test_phase2_new_a_replaces_prior_a() -> None:
    state = phase2_ready_state()
    result = apply_candles(
        state,
        [
            candle(100.0, 101.0, 99.0, 100.0),
            candle(100.0, 102.0, 99.0, 101.0),
        ],
    )
    assert result["status"] == "WAIT"
    assert result["state"]["phase2_active_a"]["high"] == 102.0
    assert result["state"]["phase2_active_a_candle_number"] == 2
    assert_reason(result)


def test_phase2_prior_a_not_reused_after_replacement() -> None:
    state = phase2_ready_state()
    result = apply_candles(
        state,
        [
            candle(100.0, 101.0, 99.0, 100.0),
            candle(100.0, 102.0, 99.0, 101.0),
            candle(100.0, 101.25, 99.5, 100.0),
        ],
    )
    assert result["status"] == "WAIT"
    assert result["state"].get("entry_triggered") is not True
    assert result["state"]["phase2_active_a"]["high"] == 102.0
    assert_reason(result)


def test_required_sr_leg_in_liquidity_blocks_entry_while_timing_continues() -> None:
    state = base_interaction("SHORT")
    state.update(
        {
            "controlling_mode": "S/R",
            "required_leg_in_liquidity_exists": True,
            "required_leg_in_liquidity_swept": False,
        }
    )
    result = phase1_to_candle4(state, candle(100.0, 102.25, 99.5, 100.25))
    assert result["step"] == "Step 7"
    assert "gate blocked" in result["reason"]
    assert_reason(result)


def test_timing_expiry_before_required_sweep_invalid() -> None:
    state = phase2_ready_state()
    state.update(
        {
            "controlling_mode": "R/S",
            "required_leg_in_liquidity_exists": True,
            "required_leg_in_liquidity_swept": False,
        }
    )
    result = apply_candles(
        state,
        [
            candle(100.0, 101.0, 99.0, 100.0),
            candle(100.0, 100.75, 99.0, 100.0),
            candle(100.0, 100.75, 99.0, 100.0),
            candle(100.0, 100.75, 99.0, 100.0),
        ],
    )
    assert result["step"] == "Step 7"
    assert "gate blocked" in result["reason"]
    assert_reason(result)


def test_anchor_extreme_close_violation_invalidates() -> None:
    state = base_interaction("SHORT")
    state["anchor_extreme"] = 102.0
    wick_result = evaluate_step6(state, candle(99.5, 100.5, 98.5, 99.5))
    assert wick_result["status"] == "WAIT"
    close_result = evaluate_step6(wick_result["state"], candle(101.5, 102.5, 100.5, 102.25))
    assert close_result["step"] == "Step 7"
    assert close_result["status"] == "TERMINATED"
    assert close_result["state"]["step6_window_active"] is False
    assert_reason(close_result)


def test_ym_2026_05_28_step6_window_counts_c1_to_c4_and_invalidates() -> None:
    state = base_interaction(
        "SHORT",
        anchor=candle(50583.0, 50592.0, 50573.0, 50592.0, timestamp="2026-05-28T13:45:00Z"),
    )
    state.update(
        {
            "tick_size": 1.0,
            "anchor_extreme": 50610.0,
            "leg2_candle_a_time": "2026-05-28T13:45:00Z",
            "step6_window_started_at": "2026-05-28T13:45:00Z",
            "step6_window_active": True,
            "step6_window_candle_index": 0,
            "step6_window_remaining": 4,
            "step6_window_expires_at": "2026-05-28T13:49:00Z",
        }
    )
    sequence = [
        candle(50591.0, 50617.0, 50568.0, 50570.0, timestamp="2026-05-28T13:46:00Z"),
        candle(50569.0, 50584.0, 50562.0, 50576.0, timestamp="2026-05-28T13:47:00Z"),
        candle(50576.0, 50585.0, 50564.0, 50579.0, timestamp="2026-05-28T13:48:00Z"),
        candle(50580.0, 50619.0, 50580.0, 50611.0, timestamp="2026-05-28T13:49:00Z"),
    ]

    result = {}
    current = state
    for expected_index, item in enumerate(sequence, start=1):
        result = evaluate_step6(current, item)
        current = result["state"]
        assert current["step6_window_candle_index"] == expected_index
        assert current["step6_window_remaining"] == max(0, 4 - expected_index)
        assert current["step6_window_started_at"] == "2026-05-28T13:45:00Z"
        assert current["step6_window_expires_at"] == "2026-05-28T13:49:00Z"

    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert result["state"].get("entry_triggered") is not True
    assert result["state"]["step6_window_candle_index"] == 4
    assert result["state"]["step6_window_active"] is False
    assert result["state"]["step6_window_remaining"] == 0
    assert_reason(result)


def test_opposing_setup_override_invalidates_current_setup() -> None:
    state = base_interaction("SHORT")
    state.update(
        {
            "opposing_setup_leg1_complete": True,
            "leg1_status": "VALID",
            "leg1_reference": 100.0,
            "leg1_extreme": 102.0,
        }
    )
    result = evaluate_step6(state, candle(100.0, 102.25, 99.5, 100.25))
    assert result["status"] == "WAIT"
    assert result["next_step"] == "Step 4"
    assert result["state"]["original_setup_status"] == "INVALID"
    assert result["state"]["control_transferred_to_opposing_setup"] is True
    assert result["state"]["entry_triggered"] is False
    assert_reason(result)


def run_tests() -> None:
    tests = [
        test_phase1_entry_triggers_on_candle4_valid,
        test_phase1_entry_before_candle4_blocked,
        test_phase1_no_entry_on_candle4_without_failed_participation_invalid,
        test_phase1_starts_from_carried_step6_window_index,
        test_phase1_same_run_handoff_does_not_double_count_carried_candle,
        test_phase1_failed_participation_activates_phase2,
        test_phase2_c1_a_c2_b_triggers_entry,
        test_phase2_c2_a_c3_b_triggers_entry,
        test_phase2_c3_a_c4_b_triggers_entry,
        test_phase2_c4_as_a_only_invalid,
        test_phase2_no_b_by_c4_invalid,
        test_phase2_new_a_replaces_prior_a,
        test_phase2_prior_a_not_reused_after_replacement,
        test_required_sr_leg_in_liquidity_blocks_entry_while_timing_continues,
        test_timing_expiry_before_required_sweep_invalid,
        test_anchor_extreme_close_violation_invalidates,
        test_ym_2026_05_28_step6_window_counts_c1_to_c4_and_invalidates,
        test_opposing_setup_override_invalidates_current_setup,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} Step 6 replay tests passed")


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for test in (
        test_phase1_entry_triggers_on_candle4_valid,
        test_phase1_entry_before_candle4_blocked,
        test_phase1_no_entry_on_candle4_without_failed_participation_invalid,
        test_phase1_starts_from_carried_step6_window_index,
        test_phase1_failed_participation_activates_phase2,
        test_phase2_c1_a_c2_b_triggers_entry,
        test_phase2_c2_a_c3_b_triggers_entry,
        test_phase2_c3_a_c4_b_triggers_entry,
        test_phase2_c4_as_a_only_invalid,
        test_phase2_no_b_by_c4_invalid,
        test_phase2_new_a_replaces_prior_a,
        test_phase2_prior_a_not_reused_after_replacement,
        test_required_sr_leg_in_liquidity_blocks_entry_while_timing_continues,
        test_timing_expiry_before_required_sweep_invalid,
        test_anchor_extreme_close_violation_invalidates,
        test_ym_2026_05_28_step6_window_counts_c1_to_c4_and_invalidates,
        test_opposing_setup_override_invalidates_current_setup,
    ):
        suite.addTest(unittest.FunctionTestCase(test))
    return suite


if __name__ == "__main__":
    run_tests()
