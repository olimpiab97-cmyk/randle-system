"""Focused replay tests for Step 6 only."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from step6_engine import (
    STEP6_NEXT_SAME_SIDE_LIQUIDITY_CLOSE_TOUCHED,
    active_anchor_state,
    evaluate_extended_retrace,
    evaluate_step6,
)


def candle(open_price: float, high: float, low: float, close: float, **extra) -> dict:
    payload = {"open": open_price, "high": high, "low": low, "close": close}
    payload.update(extra)
    return payload


def base_interaction(direction: str = "SHORT", anchor: dict | None = None) -> dict:
    anchor_candle = anchor or candle(98.5, 100.0, 98.0, 98.5)
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


def with_next_same_side_liquidity(state: dict, price: float) -> dict:
    updated = dict(state)
    updated["next_break_side_liquidity"] = {"name": "NEXT", "price": price}
    return updated


def with_intrabar_path(state: dict, minute: str, points: list[list]) -> dict:
    updated = dict(state)
    updated["step6_intrabar_previous_minute_path"] = {
        "minute": minute,
        "points": points,
        "truncated": False,
        "price_change_only": True,
        "max_points": 512,
    }
    updated["step6_intrabar_previous_minute_path_available"] = True
    return updated


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
            candle(98.25, 99.0, 98.0, 98.25),
            candle(98.25, 99.0, 98.0, 98.25),
            candle(98.25, 99.0, 98.0, 98.25),
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
    result = apply_candles(
        base_interaction("SHORT", anchor=candle(100.0, 102.0, 99.0, 100.0)),
        [
            candle(100.0, 100.5, 99.75, 100.0),
            candle(100.0, 100.5, 99.75, 100.0),
            candle(100.0, 100.5, 99.75, 100.0),
            candle(100.0, 102.25, 99.5, 100.25),
        ],
    )
    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["entry_type"] == "Large Wick Sweep"
    assert result["state"]["interaction_state"] == "CONSUMED"
    assert result["state"]["structure_status"] == "LOCKED"
    assert_reason(result)


def test_phase1_entry_can_trigger_on_candle1() -> None:
    result = evaluate_step6(
        base_interaction("SHORT", anchor=candle(100.0, 102.0, 99.0, 100.0)),
        candle(100.0, 102.25, 99.5, 100.25),
    )
    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["entry_type"] == "Large Wick Sweep"
    assert result["state"]["phase1_candle_count"] == 1
    assert result["state"]["step6_window_active"] is True
    assert result["state"]["step6_window_candle_index"] == 1
    assert result["state"]["step6_window_remaining"] == 3
    assert result["state"].get("entry_triggered") is True
    assert_reason(result)


def test_step6_short_invalidates_when_high_touches_next_upper_same_side_close() -> None:
    state = with_next_same_side_liquidity(
        base_interaction("SHORT", anchor=candle(100.0, 102.0, 99.0, 100.0)),
        102.25,
    )
    result = evaluate_step6(state, candle(100.0, 102.25, 99.5, 100.25, timestamp="2026-06-24T13:51:00Z"))
    assert result["status"] == "TERMINATED"
    assert result["reason"] == STEP6_NEXT_SAME_SIDE_LIQUIDITY_CLOSE_TOUCHED
    assert result["state"]["invalidation_source"] == "step6_next_same_side_liquidity_close"


def test_step6_long_invalidates_when_low_touches_next_lower_same_side_close() -> None:
    state = with_next_same_side_liquidity(
        base_interaction("LONG", anchor=candle(100.0, 101.0, 98.0, 100.0)),
        97.75,
    )
    result = evaluate_step6(state, candle(100.0, 100.5, 97.75, 99.75, timestamp="2026-06-24T13:51:00Z"))
    assert result["status"] == "TERMINATED"
    assert result["reason"] == STEP6_NEXT_SAME_SIDE_LIQUIDITY_CLOSE_TOUCHED
    assert result["state"]["invalidation_source"] == "step6_next_same_side_liquidity_close"


def test_step6_does_not_invalidate_when_next_same_side_close_not_touched() -> None:
    state = with_next_same_side_liquidity(
        base_interaction("SHORT", anchor=candle(100.0, 102.0, 99.0, 100.0)),
        103.0,
    )
    result = evaluate_step6(state, candle(100.0, 102.25, 99.5, 100.25))
    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["entry_type"] == "Large Wick Sweep"


def test_existing_step6_entry_still_confirms_when_no_next_level_touch_occurs() -> None:
    state = with_next_same_side_liquidity(
        base_interaction("SHORT", anchor=candle(100.0, 102.0, 99.0, 100.0)),
        103.0,
    )
    result = evaluate_step6(state, candle(100.0, 102.25, 99.5, 100.25))
    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["reason"] == "Large Wick Sweep triggered: SC extreme swept by 1 tick and 60% wick reclaim exceeded by 1 tick."


def test_large_wick_sweep_uses_intrabar_reclaim_not_close() -> None:
    result = evaluate_step6(
        base_interaction("SHORT", anchor=candle(100.0, 102.0, 99.0, 100.0)),
        candle(100.0, 102.25, 99.0, 101.9),
    )
    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["entry_type"] == "Large Wick Sweep"
    assert result["entry_price"] == 100.8
    assert_reason(result)


def test_step6_large_wick_real_nq_704_705_intrabar_reclaim_contract() -> None:
    candle_a = candle(
        30671.75,
        30680.5,
        30671.25,
        30677.75,
        timestamp="2026-06-19T14:04:00Z",
    )
    candle_b = candle(
        30679.25,
        30682.0,
        30669.0,
        30669.75,
        timestamp="2026-06-19T14:05:00Z",
    )

    result = evaluate_step6(base_interaction("SHORT", anchor=candle_a), candle_b)

    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["entry_type"] == "Large Wick Sweep"
    assert result["entry_price"] == 30678.85
    assert result["reason"] == "Large Wick Sweep triggered: SC extreme swept by 1 tick and 60% wick reclaim exceeded by 1 tick."
    assert_reason(result)


def test_small_wick_sweep_conservative_ohlc_short_contract() -> None:
    candle_a = candle(100.0, 100.5, 99.0, 100.4)
    candle_b = candle(100.0, 100.75, 100.25, 100.6)
    result = evaluate_step6(base_interaction("SHORT", anchor=candle_a), candle_b)
    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["entry_type"] == "Small Wick Sweep"
    assert result["entry_price"] == 100.4
    assert result["reason"] == "Small Wick Sweep triggered: conservative OHLC body acceptance, 1-tick sweep, and intrabar reclaim at SC body level."
    assert_reason(result)


def test_small_wick_sweep_uses_ordered_intrabar_sequence_when_path_present() -> None:
    candle_a = candle(100.0, 100.5, 99.0, 100.4)
    candle_b = candle(100.0, 100.75, 100.25, 100.6, timestamp="2026-06-20T13:35:00Z")
    state = with_intrabar_path(
        base_interaction("SHORT", anchor=candle_a),
        "2026-06-20T13:35:00Z",
        [
            ["2026-06-20T13:35:05.000Z", 100.1],
            ["2026-06-20T13:35:18.000Z", 100.8],
            ["2026-06-20T13:35:37.000Z", 100.4],
        ],
    )

    result = evaluate_step6(state, candle_b)

    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["entry_type"] == "Small Wick Sweep"
    assert result["entry_price"] == 100.4
    assert result["reason"] == "Small Wick Sweep triggered: ordered intrabar sequence confirmed body acceptance, 1-tick sweep, and reclaim at SC body level."
    assert_reason(result)


def test_small_wick_sweep_rejects_open_without_body_acceptance() -> None:
    candle_a = candle(100.0, 100.5, 99.0, 100.4)
    candle_b = candle(100.25, 100.75, 100.25, 100.6)
    result = evaluate_step6(base_interaction("SHORT", anchor=candle_a), candle_b)
    assert result["status"] == "WAIT"
    models = result["state"]["step6_entry_models"]
    assert models["small_wick_sweep"]["eligible"] is True
    assert models["small_wick_sweep"]["passed"] is False
    assert models["small_wick_sweep"]["reason"] == "Small Wick Sweep did not trigger."
    assert_reason(result)


def test_small_wick_sweep_path_requires_body_acceptance_before_sweep() -> None:
    candle_a = candle(100.0, 100.5, 99.0, 100.4)
    candle_b = candle(100.3, 100.75, 100.1, 100.6, timestamp="2026-06-20T13:35:00Z")
    state = with_intrabar_path(
        base_interaction("SHORT", anchor=candle_a),
        "2026-06-20T13:35:00Z",
        [
            ["2026-06-20T13:35:05.000Z", 100.8],
            ["2026-06-20T13:35:18.000Z", 100.1],
            ["2026-06-20T13:35:37.000Z", 100.4],
        ],
    )

    result = evaluate_step6(state, candle_b)

    assert result["status"] == "WAIT"
    models = result["state"]["step6_entry_models"]
    assert models["small_wick_sweep"]["eligible"] is True
    assert models["small_wick_sweep"]["passed"] is False
    assert models["small_wick_sweep"]["reason"] == "Small Wick Sweep did not trigger: intrabar path did not complete body acceptance -> sweep -> reclaim in order."
    assert_reason(result)


def test_small_wick_sweep_path_missing_preserves_ohlc_fallback() -> None:
    candle_a = candle(100.0, 100.5, 99.0, 100.4)
    candle_b = candle(100.0, 100.75, 100.25, 100.6)
    state = dict(base_interaction("SHORT", anchor=candle_a))
    state["step6_intrabar_previous_minute_path"] = None
    state["step6_intrabar_previous_minute_path_available"] = False

    result = evaluate_step6(state, candle_b)

    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["entry_type"] == "Small Wick Sweep"
    assert result["entry_price"] == 100.4
    assert result["reason"] == "Small Wick Sweep triggered: conservative OHLC body acceptance, 1-tick sweep, and intrabar reclaim at SC body level."
    assert_reason(result)


def test_step6_small_wick_real_nq_628_629_short_contract() -> None:
    # Direct-model fixture only: validates the Small Wick OHLC approximation for SHORT.
    candle_a = candle(
        30642.25,
        30642.75,
        30639.5,
        30640.0,
        timestamp="2026-06-19T13:28:00Z",
    )
    candle_b = candle(
        30640.25,
        30648.5,
        30636.75,
        30645.5,
        timestamp="2026-06-19T13:29:00Z",
    )

    result = evaluate_step6(base_interaction("SHORT", anchor=candle_a), candle_b)

    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["entry_type"] == "Small Wick Sweep"
    assert result["entry_price"] == 30642.25
    assert result["reason"] == "Small Wick Sweep triggered: conservative OHLC body acceptance, 1-tick sweep, and intrabar reclaim at SC body level."
    assert_reason(result)


def test_step6_small_wick_real_nq_628_629_long_contract() -> None:
    # Direct-model fixture only: validates the Small Wick OHLC approximation for LONG.
    candle_a = candle(
        30642.25,
        30642.75,
        30639.5,
        30640.0,
        timestamp="2026-06-19T13:28:00Z",
    )
    candle_b = candle(
        30640.25,
        30648.5,
        30636.75,
        30645.5,
        timestamp="2026-06-19T13:29:00Z",
    )

    result = evaluate_step6(base_interaction("LONG", anchor=candle_a), candle_b)

    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["entry_type"] == "Small Wick Sweep"
    assert result["entry_price"] == 30640.0
    assert result["reason"] == "Small Wick Sweep triggered: conservative OHLC body acceptance, 1-tick sweep, and intrabar reclaim at SC body level."
    assert_reason(result)


def test_zero_directional_wick_does_not_qualify_as_small_wick_anchor() -> None:
    candle_a = candle(100.0, 100.0, 99.0, 99.5, timestamp="2026-06-19T13:39:00Z")
    candle_b = candle(99.0, 100.25, 99.0, 99.5, timestamp="2026-06-19T13:40:00Z")

    result = evaluate_step6(base_interaction("SHORT", anchor=candle_a), candle_b)

    assert result["status"] == "WAIT"
    models = result["state"]["step6_entry_models"]
    assert models["small_wick_sweep"]["eligible"] is False
    assert models["small_wick_sweep"]["passed"] is False
    assert models["small_wick_sweep"]["reason"] == (
        "Small Wick Sweep requires a positive SC directional wick. "
        "Ineligible because Active anchor has no directional wick; wick-sweep models require a positive directional wick."
    )
    assert_reason(result)


def test_double_wick_uses_intrabar_reclaim_not_close() -> None:
    candle_a = candle(100.0, 102.0, 99.0, 100.0)
    candle_b = candle(101.0, 101.25, 99.75, 101.1)
    result = evaluate_step6(base_interaction("SHORT", anchor=candle_a), candle_b)
    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["entry_type"] == "Double Wick Rejection"
    assert result["entry_price"] == 100.0
    assert result["reason"] == "Double Wick Rejection triggered: entry penetrated 50% of SC wick and reclaimed the SC body level intrabar."
    assert_reason(result)


def test_step6_double_wick_real_nq_656_657_short_contract() -> None:
    candle_a = candle(
        30675.25,
        30695.75,
        30675.25,
        30686.25,
        timestamp="2026-06-19T13:56:00Z",
    )
    candle_b = candle(
        30685.0,
        30693.5,
        30683.0,
        30686.75,
        timestamp="2026-06-19T13:57:00Z",
    )

    result = evaluate_step6(base_interaction("SHORT", anchor=candle_a), candle_b)

    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["entry_type"] == "Double Wick Rejection"
    assert result["entry_price"] == 30686.25
    assert result["reason"] == "Double Wick Rejection triggered: entry penetrated 50% of SC wick and reclaimed the SC body level intrabar."
    assert_reason(result)


def test_step6_extended_retrace_real_nq_633_634_long_contract() -> None:
    candle_a = candle(
        30651.75,
        30651.75,
        30637.75,
        30642.75,
        timestamp="2026-06-19T13:33:00Z",
    )
    candle_b = candle(
        30642.25,
        30646.75,
        30631.75,
        30645.75,
        timestamp="2026-06-19T13:34:00Z",
    )

    passed, entry_price, reason = evaluate_extended_retrace(
        {"atr_1m_14": 10.6964, "tick_size": 0.25},
        candle_a,
        candle_b,
        "LONG",
    )

    assert passed is True
    assert entry_price == 30634.75
    assert reason == "Extended Retrace triggered: extension reached 0.50 x ATR(14) and retraced 50% intrabar."


def test_step6_extended_retrace_short_contract() -> None:
    candle_a = candle(100.0, 100.0, 95.0, 97.0)
    candle_b = candle(97.25, 106.0, 102.5, 105.75)

    passed, entry_price, reason = evaluate_extended_retrace(
        {"atr_1m_14": 10.0, "tick_size": 0.25},
        candle_a,
        candle_b,
        "SHORT",
    )

    assert passed is True
    assert entry_price == 103.0
    assert reason == "Extended Retrace triggered: extension reached 0.50 x ATR(14) and retraced 50% intrabar."


def test_step6_extended_retrace_exact_half_atr_threshold_passes() -> None:
    candle_a = candle(100.0, 100.0, 95.0, 97.0)
    candle_b = candle(97.25, 105.0, 102.5, 104.0)

    passed, entry_price, reason = evaluate_extended_retrace(
        {"atr_1m_14": 10.0, "tick_size": 0.25},
        candle_a,
        candle_b,
        "SHORT",
    )

    assert passed is True
    assert entry_price == 102.5
    assert reason == "Extended Retrace triggered: extension reached 0.50 x ATR(14) and retraced 50% intrabar."


def test_step6_extended_retrace_below_threshold_fails() -> None:
    candle_a = candle(100.0, 100.0, 95.0, 97.0)
    candle_b = candle(97.25, 104.75, 101.5, 104.0)

    passed, entry_price, reason = evaluate_extended_retrace(
        {"atr_1m_14": 10.0, "tick_size": 0.25},
        candle_a,
        candle_b,
        "SHORT",
    )

    assert passed is False
    assert entry_price is None
    assert reason == "Extended Retrace did not trigger: extension stayed below 0.50 x ATR(14)."


def test_step6_extended_retrace_requires_intrabar_fill_and_not_close() -> None:
    candle_a = candle(100.0, 100.0, 95.0, 97.0)
    no_fill = candle(97.25, 106.0, 103.25, 102.0)
    close_only = candle(97.25, 106.0, 103.25, 101.0)

    no_fill_passed, no_fill_entry, no_fill_reason = evaluate_extended_retrace(
        {"atr_1m_14": 10.0, "tick_size": 0.25},
        candle_a,
        no_fill,
        "SHORT",
    )
    close_only_passed, close_only_entry, close_only_reason = evaluate_extended_retrace(
        {"atr_1m_14": 10.0, "tick_size": 0.25},
        candle_a,
        close_only,
        "SHORT",
    )

    assert no_fill_passed is False
    assert no_fill_entry is None
    assert no_fill_reason == "Extended Retrace did not trigger: extension qualified but intrabar retrace fill did not occur."
    assert close_only_passed is False
    assert close_only_entry is None
    assert close_only_reason == "Extended Retrace did not trigger: extension qualified but intrabar retrace fill did not occur."


def test_phase1_candles_1_to_4_each_evaluate_entry_models_before_expiration() -> None:
    state = base_interaction(
        "SHORT",
        anchor=candle(98.5, 100.0, 98.0, 98.5, timestamp="2026-05-28T13:45:00Z"),
    )
    state.update(
        {
            "tick_size": 0.25,
            "leg2_candle_a_time": "2026-05-28T13:45:00Z",
            "step6_window_started_at": "2026-05-28T13:45:00Z",
            "step6_window_active": True,
            "step6_window_candle_index": 0,
            "step6_window_remaining": 4,
            "step6_window_expires_at": "2026-05-28T13:49:00Z",
        }
    )
    sequence = [
        candle(98.25, 99.0, 98.0, 98.25, timestamp="2026-05-28T13:46:00Z"),
        candle(98.25, 99.0, 98.0, 98.25, timestamp="2026-05-28T13:47:00Z"),
        candle(98.25, 99.0, 98.0, 98.25, timestamp="2026-05-28T13:48:00Z"),
        candle(98.25, 99.0, 98.0, 98.25, timestamp="2026-05-28T13:49:00Z"),
    ]

    current = state
    for expected_index, item in enumerate(sequence, start=1):
        result = evaluate_step6(current, item)
        current = result["state"]
        models = current["step6_entry_models"]
        assert current["step6_window_candle_index"] == expected_index
        assert models["large_wick_sweep"]["evaluated"] is True
        assert models["small_wick_sweep"]["evaluated"] is True
        assert models["double_wick_rejection"]["evaluated"] is True
        if expected_index < 4:
            assert current["phase1_candle_count"] == expected_index
            assert result["status"] == "WAIT"
            assert result["reason"] == f"Phase 1 Candle {expected_index}: entry models evaluated; no valid entry yet."
        else:
            assert result["status"] == "TERMINATED"
            assert result["reason"] == "Phase 1 failed on Candle 4 with no valid Phase 2 failed-entry participation."
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
        ],
    )
    # Large Wick now reclaims intrabar, so this sequence triggers on Candle 2 instead of waiting for Candle 3 close.
    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["state"]["phase2_active_a_candle_number"] == 1
    assert result["state"]["phase2_b_candle_number"] == 2
    assert_reason(result)


def test_phase2_c3_a_c4_b_triggers_entry() -> None:
    state = phase2_ready_state()
    result = apply_candles(
        state,
        [
            candle(100.5, 101.0, 98.5, 100.0),
            candle(100.0, 100.5, 99.75, 100.0),
            candle(100.0, 101.0, 100.0, 100.25),
        ],
    )
    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["state"]["phase2_active_a_candle_number"] == 1
    assert result["state"]["phase2_b_candle_number"] == 3
    assert_reason(result)


def test_phase2_c4_as_a_only_invalid() -> None:
    state = phase2_ready_state()
    result = apply_candles(
        state,
        [
            candle(100.0, 102.0, 98.5, 100.0),
            candle(100.0, 100.5, 99.75, 100.0),
            candle(100.0, 100.5, 99.75, 100.0),
            candle(100.0, 102.25, 100.25, 101.0),
        ],
    )
    assert result["step"] == "Step 6"
    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["entry_type"] == "Large Wick Sweep"


def test_phase2_no_b_by_c4_invalid() -> None:
    state = phase2_ready_state()
    result = apply_candles(
        state,
        [
            candle(100.5, 101.0, 98.5, 100.0),
            candle(100.0, 100.5, 99.75, 100.0),
            candle(100.0, 100.5, 99.75, 100.0),
            candle(100.0, 100.5, 99.75, 100.0),
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
    # Candle 2 now triggers immediately from intrabar Large Wick reclaim before replacement can matter.
    assert result["status"] == "ENTRY_CONFIRMED"
    assert result["entry_type"] == "Large Wick Sweep"
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
    # Intrabar Large Wick reclaim triggers on Candle 2, so the prior-A reuse question no longer remains unresolved in this fixture.
    assert result["status"] == "TERMINATED"
    assert "only one entry per interaction" in result["reason"]
    assert_reason(result)


def test_required_sr_leg_in_liquidity_blocks_entry_while_timing_continues() -> None:
    state = base_interaction("SHORT", anchor=candle(100.0, 102.0, 99.0, 100.0))
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
    state = base_interaction("SHORT", anchor=candle(100.0, 102.0, 99.0, 100.0))
    state["anchor_extreme"] = 102.0
    wick_result = evaluate_step6(state, candle(99.5, 100.5, 99.25, 99.5))
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
        candle(50591.0, 50592.0, 50588.0, 50592.0, timestamp="2026-05-28T13:46:00Z"),
        candle(50592.0, 50592.0, 50589.0, 50592.0, timestamp="2026-05-28T13:47:00Z"),
        candle(50592.0, 50592.0, 50590.0, 50592.0, timestamp="2026-05-28T13:48:00Z"),
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


def test_phase1_newer_anchor_replaces_a_without_resetting_window() -> None:
    state = base_interaction(
        "SHORT",
        anchor=candle(100.0, 102.0, 99.0, 100.0, timestamp="2026-05-28T13:45:00Z"),
    )
    state.update(
        {
            "tick_size": 0.25,
            "leg2_candle_a_time": "2026-05-28T13:45:00Z",
            "step6_window_started_at": "2026-05-28T13:45:00Z",
            "step6_window_active": True,
            "step6_window_candle_index": 0,
            "step6_window_remaining": 4,
            "step6_window_expires_at": "2026-05-28T13:49:00Z",
        }
    )

    candle1 = candle(100.0, 100.25, 99.75, 100.0, timestamp="2026-05-28T13:46:00Z")
    candle2 = candle(100.0, 100.25, 99.75, 100.0, timestamp="2026-05-28T13:47:00Z")
    candle3 = candle(100.0, 102.0, 100.0, 101.0, timestamp="2026-05-28T13:48:00Z")
    candle4 = candle(101.5, 102.25, 101.0, 101.75, timestamp="2026-05-28T13:49:00Z")

    current = state
    current = evaluate_step6(current, candle1)["state"]
    current = evaluate_step6(current, candle2)["state"]
    result3 = evaluate_step6(current, candle3)
    state3 = result3["state"]

    assert result3["status"] == "WAIT"
    assert "newer qualifying anchor adopted" in result3["reason"]
    assert state3["phase1_anchor"]["timestamp"] == "2026-05-28T13:48:00Z"
    assert state3["active_entry_anchor"]["timestamp"] == "2026-05-28T13:48:00Z"
    assert state3["step6_window_started_at"] == "2026-05-28T13:45:00Z"
    assert state3["step6_window_candle_index"] == 3
    assert state3["step6_window_remaining"] == 1

    result4 = evaluate_step6(state3, candle4)

    assert result4["status"] == "ENTRY_CONFIRMED"
    assert result4["entry_type"] == "Large Wick Sweep"
    assert result4["entry_price"] == 101.4
    assert result4["state"]["step6_window_started_at"] == "2026-05-28T13:45:00Z"
    assert result4["state"]["step6_window_candle_index"] == 4
    assert result4["state"]["active_entry_anchor"]["timestamp"] == "2026-05-28T13:48:00Z"
    assert_reason(result4)


def test_step6_fixed_window_uses_candle3_anchor_without_clock_reset_conceptual_example() -> None:
    a0 = candle(100.0, 100.5, 99.5, 100.0, timestamp="2026-05-28T13:45:00Z")
    state = base_interaction("LONG", anchor=a0)
    state.update(
        {
            "tick_size": 0.25,
            "leg2_candle_a_time": "2026-05-28T13:45:00Z",
            "step6_window_started_at": "2026-05-28T13:45:00Z",
            "step6_window_active": True,
            "step6_window_candle_index": 0,
            "step6_window_remaining": 4,
            "step6_window_expires_at": "2026-05-28T13:49:00Z",
        }
    )

    candle1 = candle(100.25, 101.0, 100.75, 101.0, timestamp="2026-05-28T13:46:00Z")
    candle2 = candle(101.25, 102.0, 101.75, 102.0, timestamp="2026-05-28T13:47:00Z")
    candle3 = candle(100.25, 100.5, 97.5, 99.0, timestamp="2026-05-28T13:48:00Z")
    candle4 = candle(98.0, 99.25, 97.25, 98.75, timestamp="2026-05-28T13:49:00Z")

    current = state
    result1 = evaluate_step6(current, candle1)
    current = result1["state"]
    result2 = evaluate_step6(current, candle2)
    current = result2["state"]
    result3 = evaluate_step6(current, candle3)
    state3 = result3["state"]
    result4 = evaluate_step6(state3, candle4)

    assert active_anchor_state(result2["state"])["timestamp"] == "2026-05-28T13:45:00Z"
    assert result3["status"] == "WAIT"
    assert "newer qualifying anchor adopted" in result3["reason"]
    assert active_anchor_state(state3)["timestamp"] == "2026-05-28T13:48:00Z"
    assert result4["status"] == "ENTRY_CONFIRMED"
    assert result4["entry_type"] == "Large Wick Sweep"
    assert result4["entry_price"] == 98.4
    assert result4["state"]["active_entry_anchor"]["timestamp"] == "2026-05-28T13:48:00Z"
    assert result4["state"]["step6_window_candle_index"] == 4
    assert result4["state"]["step6_window_started_at"] == "2026-05-28T13:45:00Z"
    assert result4["state"]["step6_window_expires_at"] == "2026-05-28T13:49:00Z"
    assert_reason(result4)


def test_step6_real_nq_0639_0642_long_uses_0641_replacement_anchor_and_enters_0642() -> None:
    a0 = candle(30667.75, 30667.75, 30659.0, 30663.75, timestamp="2026-06-19T13:39:00Z")
    state = base_interaction("LONG", anchor=a0)
    state.update(
        {
            "tick_size": 0.25,
            "leg2_candle_a_time": "2026-06-19T13:39:00Z",
            "step6_window_started_at": "2026-06-19T13:39:00Z",
            "step6_window_active": True,
            "step6_window_candle_index": 0,
            "step6_window_remaining": 4,
            "step6_window_expires_at": "2026-06-19T13:43:00Z",
        }
    )

    candle1 = candle(30663.75, 30673.0, 30663.5, 30667.0, timestamp="2026-06-19T13:40:00Z")
    candle2 = candle(30666.5, 30668.0, 30655.75, 30658.75, timestamp="2026-06-19T13:41:00Z")
    candle3 = candle(30659.25, 30660.75, 30651.25, 30659.75, timestamp="2026-06-19T13:42:00Z")

    result1 = evaluate_step6(state, candle1)
    state1 = result1["state"]
    result2 = evaluate_step6(state1, candle2)
    state2 = result2["state"]
    result3 = evaluate_step6(state2, candle3)

    assert result1["status"] == "WAIT"
    assert active_anchor_state(state1)["timestamp"] == "2026-06-19T13:39:00Z"
    assert result2["status"] == "WAIT"
    assert "newer qualifying anchor adopted" in result2["reason"]
    assert active_anchor_state(state2)["timestamp"] == "2026-06-19T13:41:00Z"
    assert result3["status"] == "ENTRY_CONFIRMED"
    assert result3["entry_type"] == "Large Wick Sweep"
    assert result3["entry_price"] == 30657.55
    assert result3["state"]["active_entry_anchor"]["timestamp"] == "2026-06-19T13:41:00Z"
    assert result3["state"]["step6_window_candle_index"] == 3
    assert result3["state"]["step6_window_started_at"] == "2026-06-19T13:39:00Z"
    assert result3["state"]["step6_window_expires_at"] == "2026-06-19T13:43:00Z"
    assert_reason(result3)


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
        test_phase1_entry_can_trigger_on_candle1,
        test_large_wick_sweep_uses_intrabar_reclaim_not_close,
        test_step6_large_wick_real_nq_704_705_intrabar_reclaim_contract,
        test_small_wick_sweep_conservative_ohlc_short_contract,
        test_small_wick_sweep_uses_ordered_intrabar_sequence_when_path_present,
        test_small_wick_sweep_rejects_open_without_body_acceptance,
        test_small_wick_sweep_path_requires_body_acceptance_before_sweep,
        test_small_wick_sweep_path_missing_preserves_ohlc_fallback,
        test_step6_small_wick_real_nq_628_629_short_contract,
        test_step6_small_wick_real_nq_628_629_long_contract,
        test_double_wick_uses_intrabar_reclaim_not_close,
        test_step6_double_wick_real_nq_656_657_short_contract,
        test_step6_extended_retrace_real_nq_633_634_long_contract,
        test_step6_extended_retrace_short_contract,
        test_step6_extended_retrace_exact_half_atr_threshold_passes,
        test_step6_extended_retrace_below_threshold_fails,
        test_step6_extended_retrace_requires_intrabar_fill_and_not_close,
        test_phase1_candles_1_to_4_each_evaluate_entry_models_before_expiration,
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
        test_phase1_newer_anchor_replaces_a_without_resetting_window,
        test_step6_fixed_window_uses_candle3_anchor_without_clock_reset_conceptual_example,
        test_opposing_setup_override_invalidates_current_setup,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} Step 6 replay tests passed")


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for test in (
        test_phase1_entry_triggers_on_candle4_valid,
        test_phase1_entry_can_trigger_on_candle1,
        test_large_wick_sweep_uses_intrabar_reclaim_not_close,
        test_step6_large_wick_real_nq_704_705_intrabar_reclaim_contract,
        test_small_wick_sweep_conservative_ohlc_short_contract,
        test_small_wick_sweep_uses_ordered_intrabar_sequence_when_path_present,
        test_small_wick_sweep_rejects_open_without_body_acceptance,
        test_small_wick_sweep_path_requires_body_acceptance_before_sweep,
        test_small_wick_sweep_path_missing_preserves_ohlc_fallback,
        test_step6_small_wick_real_nq_628_629_short_contract,
        test_step6_small_wick_real_nq_628_629_long_contract,
        test_double_wick_uses_intrabar_reclaim_not_close,
        test_step6_double_wick_real_nq_656_657_short_contract,
        test_step6_extended_retrace_real_nq_633_634_long_contract,
        test_step6_extended_retrace_short_contract,
        test_step6_extended_retrace_exact_half_atr_threshold_passes,
        test_step6_extended_retrace_below_threshold_fails,
        test_step6_extended_retrace_requires_intrabar_fill_and_not_close,
        test_phase1_candles_1_to_4_each_evaluate_entry_models_before_expiration,
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
        test_phase1_newer_anchor_replaces_a_without_resetting_window,
        test_step6_fixed_window_uses_candle3_anchor_without_clock_reset_conceptual_example,
        test_opposing_setup_override_invalidates_current_setup,
    ):
        suite.addTest(unittest.FunctionTestCase(test))
    return suite


if __name__ == "__main__":
    run_tests()
