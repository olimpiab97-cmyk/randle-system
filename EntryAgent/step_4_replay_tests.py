"""Focused replay tests for Step 4 only."""

from __future__ import annotations

from entry_agent import (
    apply_confirmed_lifecycle_invariants,
    build_entry_status,
    build_step4_interaction,
    evaluate_live_step_2_1a,
    evaluate_live_step3,
    evaluate_live_step4,
    evaluate_live_step5,
    evaluate_live_step6,
    evaluate_live_step25,
    rejection_from_step2_activation,
)
from step4_engine import evaluate_step4


def candle(open_price: float, high: float, low: float, close: float, timestamp: str | None = None) -> dict:
    payload = {"open": open_price, "high": high, "low": low, "close": close}
    if timestamp is not None:
        payload["timestamp"] = timestamp
    return payload


def base_interaction(direction: str = "SHORT") -> dict:
    return {
        "system_state": "REJECTION MODE ON",
        "trade_mode": "ON",
        "rejection_mode": "ON",
        "interaction_state": "ACTIVE",
        "setup_direction": direction,
        "step25_pathway_selection_complete": True,
        "step3_allows_structure": True,
        "controlling_mode": "Normal Rejection Mode",
        "candidate_modes": ["Normal Rejection Mode"],
        "initial_candle_a": candle(100.0, 101.0, 99.5, 100.5),
        "nearest_opposing_liquidity": {"name": "PML", "price": 95.0},
        "atr_1m_14": 10.0,
        "daily_atr14": 10.0,
        "events": [],
    }


def assert_reason(result: dict) -> None:
    assert result.get("reason"), result


def failed_short_participation_candle(index: int) -> dict:
    base = 101.0 + (index * 0.2)
    return candle(base, base, base - 0.5, max(101.0, base - 0.2))


def valid_short_participation_candle(index: int) -> dict:
    base = 101.0 + (index * 0.2)
    return candle(base, base + 0.4, base - 0.1, 100.75)


def failed_long_extension_candle(index: int) -> dict:
    base = 99.5 - (index * 0.2)
    return candle(base, base + 0.5, base, min(99.5, base + 0.1))


def step4_count1_wait(interaction: dict, first_candle: dict) -> dict:
    result = evaluate_step4(interaction, first_candle)
    assert result["status"] == "WAIT"
    assert result["next_step"] == "Step 4"
    assert result["state"]["leg1_window_candle_index"] == 1
    return result["state"]


def test_close_based_participation_passes_and_assigns_leg1() -> None:
    interaction = base_interaction("SHORT")
    result = evaluate_step4(interaction, candle(100.5, 100.75, 99.0, 100.75))
    assert result["status"] == "READY"
    assert result["next_step"] == "Step 5"
    assert_reason(result)
    assert result["reason"] == "Step 4 confirmed: participation qualified inside the Step 2 window; Leg 2 / Step 5 structure frozen from the 5-candle participation window."
    state = result["state"]
    assert state["leg1_status"] == "COMPLETE"
    assert state["leg1_reference"] == state["step5_close_boundary"]
    assert state["leg1_extreme"] == state["leg2_sweep_extreme"]
    assert state["leg1_extreme_owner"] == "step4_window"
    assert state["anchor_extreme"] == state["leg2_sweep_extreme"]
    assert state["candle_a_source"] == "initial_candle_a"


def test_participation_on_candle_1_is_valid() -> None:
    result = evaluate_step4(base_interaction("SHORT"), valid_short_participation_candle(1))
    assert result["status"] == "READY"
    assert result["next_step"] == "Step 5"
    assert result["state"]["leg1_status"] == "COMPLETE"
    assert result["state"]["participation_candle_number"] == 1


def test_participation_on_candle_2_is_valid() -> None:
    first = evaluate_step4(base_interaction("SHORT"), failed_short_participation_candle(1))
    assert first["status"] == "WAIT"
    assert first["next_step"] == "Step 4"
    assert "leg1_status" not in first["state"]

    second = evaluate_step4(first["state"], valid_short_participation_candle(2))
    assert second["status"] == "READY"
    assert second["next_step"] == "Step 5"
    assert second["state"]["leg1_status"] == "COMPLETE"
    assert second["state"]["participation_candle_number"] == 2


def test_participation_on_candle_3_is_valid() -> None:
    first = evaluate_step4(base_interaction("SHORT"), failed_short_participation_candle(1))
    second_wait = evaluate_step4(first["state"], failed_short_participation_candle(2))
    assert second_wait["status"] == "WAIT"
    assert second_wait["next_step"] == "Step 4"
    assert "leg1_status" not in second_wait["state"]

    third = evaluate_step4(second_wait["state"], valid_short_participation_candle(3))
    assert third["status"] == "READY"
    assert third["next_step"] == "Step 5"
    assert third["state"]["leg1_status"] == "COMPLETE"
    assert third["state"]["participation_candle_number"] == 3


def test_participation_on_candle_4_is_valid() -> None:
    first = evaluate_step4(base_interaction("SHORT"), failed_short_participation_candle(1))
    second_wait = evaluate_step4(first["state"], failed_short_participation_candle(2))
    third_wait = evaluate_step4(second_wait["state"], failed_short_participation_candle(3))
    assert third_wait["status"] == "WAIT"
    assert third_wait["next_step"] == "Step 4"
    assert "leg1_status" not in third_wait["state"]

    fourth = evaluate_step4(third_wait["state"], valid_short_participation_candle(4))
    assert fourth["status"] == "READY"
    assert fourth["next_step"] == "Step 5"
    assert fourth["state"]["leg1_status"] == "COMPLETE"
    assert fourth["state"]["participation_candle_number"] == 4


def test_rejection_candle_a_replaces_on_stronger_short_extension_inside_fixed_window() -> None:
    first = evaluate_step4(base_interaction("SHORT"), failed_short_participation_candle(1))
    assert first["status"] == "WAIT"
    assert first["state"]["leg1_window_candle_index"] == 1

    second = evaluate_step4(first["state"], failed_short_participation_candle(2))
    assert second["status"] == "WAIT"
    assert second["state"]["candle_a"]["high"] == failed_short_participation_candle(2)["high"]
    assert second["state"]["candle_a_source"] == "rolling_participation_extreme"
    assert second["state"]["leg1_window_candle_index"] == 2

    third = evaluate_step4(second["state"], failed_short_participation_candle(3))
    assert third["status"] == "WAIT"
    assert third["state"]["candle_a"]["high"] == failed_short_participation_candle(3)["high"]
    assert third["state"]["leg1_window_candle_index"] == 3


def test_rejection_candle_b_can_complete_on_final_fourth_candle_against_latest_short_anchor() -> None:
    first = evaluate_step4(base_interaction("SHORT"), failed_short_participation_candle(1))
    second = evaluate_step4(first["state"], failed_short_participation_candle(2))
    third = evaluate_step4(second["state"], failed_short_participation_candle(3))

    final_candidate = valid_short_participation_candle(4)
    fourth = evaluate_step4(third["state"], final_candidate)

    assert fourth["status"] == "READY"
    assert fourth["next_step"] == "Step 5"
    assert fourth["state"]["participation_candle_number"] == 4
    assert fourth["state"]["candle_a"]["high"] == failed_short_participation_candle(3)["high"]
    assert fourth["state"]["candle_b"] == final_candidate
    assert fourth["state"]["leg1_status"] == "COMPLETE"


def test_no_participation_by_candle_4_sets_gateway_without_leg1() -> None:
    first = evaluate_step4(base_interaction("SHORT"), failed_short_participation_candle(1))
    second = evaluate_step4(first["state"], failed_short_participation_candle(2))
    third = evaluate_step4(second["state"], failed_short_participation_candle(3))
    fourth = evaluate_step4(third["state"], failed_short_participation_candle(4))

    assert fourth["step"] == "Step 7"
    assert fourth["status"] == "TERMINATED"
    assert fourth["next_step"] == "Step 1"
    assert fourth["reason"] == "Step 4 invalid: no valid participation formed within 4 candles after Step 2 confirmation."
    assert fourth["state"]["level_state"] == "GATEWAY"
    assert fourth["state"]["liquidity_state"] == "GATEWAY"
    assert fourth["state"]["opposite_participation"] == "NOT_PRESENT"
    assert fourth["state"].get("leg1_status") is None
    assert fourth["next_step"] != "Step 5"


def test_long_rejection_candle_a_replaces_on_lower_extension_and_completes_on_future_b() -> None:
    interaction = base_interaction("LONG")
    interaction["nearest_opposing_liquidity"] = {"name": "PMH", "price": 105.0}

    first = evaluate_step4(interaction, failed_long_extension_candle(1))
    assert first["status"] == "WAIT"
    assert first["state"]["leg1_window_candle_index"] == 1

    second = evaluate_step4(first["state"], failed_long_extension_candle(2))
    assert second["status"] == "WAIT"
    assert second["state"]["candle_a"]["low"] == failed_long_extension_candle(2)["low"]
    assert second["state"]["candle_a_source"] == "rolling_participation_extreme"
    assert second["state"]["leg1_window_candle_index"] == 2

    candidate_b = candle(99.2, 100.0, 99.1, 99.5)
    third = evaluate_step4(second["state"], candidate_b)
    assert third["status"] == "READY"
    assert third["next_step"] == "Step 5"
    assert third["state"]["candle_a"]["low"] == failed_long_extension_candle(2)["low"]
    assert third["state"]["candle_b"] == candidate_b
    assert third["state"]["leg1_status"] == "COMPLETE"


def test_failed_participation_wait_does_not_proceed_to_step5() -> None:
    result = evaluate_step4(base_interaction("SHORT"), failed_short_participation_candle(1))
    assert result["status"] == "WAIT"
    assert result["next_step"] == "Step 4"
    assert "leg1_status" not in result["state"]


def test_count1_can_confirm_step4_immediately() -> None:
    result = evaluate_step4(base_interaction("SHORT"), valid_short_participation_candle(1))
    assert result["status"] == "READY"
    assert result["next_step"] == "Step 5"
    assert result["state"]["leg1_status"] == "COMPLETE"
    assert result["state"]["leg1_window_candle_index"] == 1
    assert result["state"]["step4_window_count"] == 1


def test_failed_participation_clears_stale_leg1_lock_fields() -> None:
    interaction = base_interaction("SHORT")
    interaction.update(
        {
            "leg1_status": "COMPLETE",
            "leg1_state_locked": True,
            "leg1_completed_at": "2026-05-28T13:30:00Z",
            "leg1_reference_price": 100.5,
            "leg1_reference_candle_time": "2026-05-28T13:30:00Z",
            "opposite_participation": "PRESENT",
        }
    )

    result = evaluate_step4(interaction, failed_short_participation_candle(1))

    assert result["status"] == "WAIT"
    assert result["next_step"] == "Step 4"
    assert result["state"]["leg1_window_active"] is True
    assert result["state"]["leg1_window_candle_index"] == 1
    assert result["state"].get("leg1_state_locked") is not True
    assert result["state"].get("leg1_status") != "COMPLETE"


def test_live_step4_uses_current_candle_not_prior_failed_candle_b() -> None:
    first_failed = failed_short_participation_candle(1)
    next_current = valid_short_participation_candle(2)
    previous = evaluate_step4(base_interaction("SHORT"), first_failed)
    stale_candle_b = candle(200.0, 201.0, 199.0, 200.5)
    previous["state"]["candle_b"] = stale_candle_b

    interaction = build_step4_interaction(
        {
            "ohlc": next_current,
            "latest_bar_time": "2026-05-01T09:32:00Z",
            "liquidity": {"nearest_level_below": {"name": "PML", "price": 95.0}},
            "tv_context": {"atr_1m_14": 10.0, "daily_atr14": 10.0},
        },
        {"watch_side": "SHORT"},
        {"status": "READY", "state": previous["state"]},
        {"status": "ALLOW_STEP_4", "next_step": "Step 4", "state": previous["state"]},
        {"step4": previous},
    )

    assert interaction["candle_b"] == {
        **next_current,
        "timestamp": "2026-05-01T09:32:00Z",
    }
    assert interaction["candle_b"] != stale_candle_b
    assert interaction["participation_candidate_count"] == 1

    result = evaluate_step4(interaction)
    assert result["status"] == "READY"
    assert result["next_step"] == "Step 5"
    assert result["state"]["participation_candle_number"] == 2


def test_step3_blocked_does_not_build_leg1() -> None:
    interaction = base_interaction("SHORT")
    interaction["step3_allows_structure"] = False
    interaction["step3_block_reason"] = "Step 3 blocks structure."
    result = evaluate_step4(interaction, candle(100.5, 100.75, 99.0, 100.75))
    assert result["status"] == "WAIT"
    assert result["next_step"] == "Step 3"
    assert "leg1_status" not in result["state"]


def test_step25_incomplete_does_not_build_leg1() -> None:
    interaction = base_interaction("SHORT")
    interaction["step25_pathway_selection_complete"] = False
    result = evaluate_step4(interaction, candle(100.5, 100.75, 99.0, 100.75))
    assert result["status"] == "WAIT"
    assert result["next_step"] == "Step 2.5"
    assert "leg1_status" not in result["state"]


def test_sr_close_based_reclaim_candle_becomes_candle_a() -> None:
    failure = candle(99.5, 100.0, 98.5, 99.0)
    reclaim = candle(99.0, 101.0, 98.75, 100.5)
    interaction = base_interaction("SHORT")
    interaction.update(
        {
            "controlling_mode": "S/R",
            "candidate_modes": ["S/R"],
            "pathway_activation_type": "close",
            "pathway_level": 100.0,
            "structure_side_requirement": "ABOVE_LEVEL",
            "failure_candle": failure,
            "reclaim_candle_a": reclaim,
            "initial_candle_a": failure,
        }
    )
    result = evaluate_step4(interaction, candle(100.25, 100.5, 99.75, 100.0))
    assert result["status"] == "READY"
    assert result["state"]["candle_a"] == reclaim
    assert result["state"]["candle_a"] != failure
    assert result["state"]["candle_a_source"] == "reclaim_candle_a"


def test_rs_close_based_reclaim_candle_becomes_candle_a() -> None:
    failure = candle(100.5, 101.5, 100.25, 101.0)
    reclaim = candle(101.0, 101.25, 99.0, 99.5)
    interaction = base_interaction("LONG")
    interaction["nearest_opposing_liquidity"] = {"name": "PMH", "price": 105.0}
    interaction.update(
        {
            "controlling_mode": "R/S",
            "candidate_modes": ["R/S"],
            "pathway_activation_type": "close",
            "pathway_level": 100.0,
            "structure_side_requirement": "BELOW_LEVEL",
            "failure_candle": failure,
            "reclaim_candle_a": reclaim,
            "initial_candle_a": failure,
        }
    )
    result = evaluate_step4(interaction, candle(99.25, 99.5, 98.5, 99.0))
    assert result["status"] == "READY"
    assert result["state"]["candle_a"] == reclaim
    assert result["state"]["candle_a"] != failure
    assert result["state"]["candle_a_source"] == "reclaim_candle_a"


def test_sr_wrong_side_structure_blocks() -> None:
    interaction = base_interaction("SHORT")
    interaction.update(
        {
            "controlling_mode": "S/R",
            "candidate_modes": ["S/R"],
            "pathway_activation_type": "close",
            "pathway_level": 100.0,
            "structure_side_requirement": "ABOVE_LEVEL",
            "reclaim_candle_a": candle(99.0, 101.0, 98.75, 100.5),
        }
    )
    result = evaluate_step4(interaction, candle(100.5, 100.75, 99.0, 99.75))
    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert "ABOVE_LEVEL" in result["reason"]


def test_sr_provisional_leg1_does_not_require_close_back_above_stack_extreme() -> None:
    provisional = candle(99.6, 100.0, 98.75, 99.8)
    interaction = base_interaction("SHORT")
    interaction.update(
        {
            "controlling_mode": "S/R",
            "candidate_modes": ["S/R"],
            "pathway_activation_type": "wick",
            "pathway_level": 100.0,
            "structure_side_requirement": "ABOVE_LEVEL",
            "provisional_candle_a": provisional,
            "initial_candle_a": candle(100.5, 100.75, 99.5, 99.4),
            "active_stack": {"name": "LOW_STACK"},
            "extreme_boundary": 100.0,
            "stack_side": "lower",
            "liquidity_type": "STATIC_STACK",
            "continuation_acceptance_required": True,
            "continuation_acceptance_threshold": 100.0,
        }
    )
    result = evaluate_step4(interaction, candle(99.75, 100.25, 99.4, 99.8))
    assert result["status"] == "READY"
    assert result["next_step"] == "Step 5"
    assert result["state"]["leg1_status"] == "COMPLETE"
    assert result["state"].get("continuation_acceptance_confirmed") is not True


def test_rs_wrong_side_structure_blocks() -> None:
    interaction = base_interaction("LONG")
    interaction["nearest_opposing_liquidity"] = {"name": "PMH", "price": 105.0}
    interaction.update(
        {
            "controlling_mode": "R/S",
            "candidate_modes": ["R/S"],
            "pathway_activation_type": "close",
            "pathway_level": 100.0,
            "structure_side_requirement": "BELOW_LEVEL",
            "reclaim_candle_a": candle(101.0, 101.25, 99.0, 99.5),
        }
    )
    result = evaluate_step4(interaction, candle(99.5, 100.5, 99.25, 100.25))
    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert "BELOW_LEVEL" in result["reason"]


def test_wick_based_participation_passes_when_close_fails() -> None:
    interaction = base_interaction("SHORT")
    result = evaluate_step4(interaction, candle(100.75, 104.0, 100.5, 102.0))
    assert result["status"] == "READY"
    assert result["next_step"] == "Step 5"
    assert_reason(result)
    event = result["events"][-1]
    assert event["close_based_participation"] is False
    assert event["wick_based_participation"] is True
    assert result["state"]["leg1_extreme_owner"] == "step4_window"


def test_certified_short_wick_33_fails_and_34_passes_with_close_disqualified() -> None:
    fail = evaluate_step4(base_interaction("SHORT"), candle(102.0, 102.33, 101.33, 102.0))
    assert fail["status"] == "WAIT"
    assert fail["next_step"] == "Step 4"
    assert fail["state"]["step3_close_participation_pass"] is False
    assert fail["state"]["step3_wick_participation_pct"] == 33.0
    assert fail["state"]["step3_wick_participation_pass"] is False

    passed = evaluate_step4(base_interaction("SHORT"), candle(102.0, 102.34, 101.34, 102.0))
    assert passed["status"] == "READY"
    assert passed["next_step"] == "Step 5"
    assert passed["state"]["step3_close_participation_pass"] is False
    assert passed["state"]["step3_wick_participation_pct"] == 34.0
    assert passed["state"]["step3_wick_participation_pass"] is True
    assert passed["events"][-1]["step3_participation_rule_certification"] == "CERTIFIED"


def test_certified_long_wick_33_fails_and_34_passes_with_close_disqualified() -> None:
    fail_interaction = base_interaction("LONG")
    fail_interaction["nearest_opposing_liquidity"] = {"name": "PMH", "price": 105.0}
    fail = evaluate_step4(step4_count1_wait(fail_interaction, failed_long_extension_candle(1)), candle(99.0, 99.67, 98.67, 99.0))
    assert fail["status"] == "WAIT"
    assert fail["next_step"] == "Step 4"
    assert fail["state"]["step3_close_participation_pass"] is False
    assert fail["state"]["step3_wick_participation_pct"] == 33.0
    assert fail["state"]["step3_wick_participation_pass"] is False

    pass_interaction = base_interaction("LONG")
    pass_interaction["nearest_opposing_liquidity"] = {"name": "PMH", "price": 105.0}
    passed = evaluate_step4(step4_count1_wait(pass_interaction, failed_long_extension_candle(1)), candle(99.0, 99.66, 98.66, 99.0))
    assert passed["status"] == "READY"
    assert passed["next_step"] == "Step 5"
    assert passed["state"]["step3_close_participation_pass"] is False
    assert passed["state"]["step3_wick_participation_pct"] == 34.0
    assert passed["state"]["step3_wick_participation_pass"] is True
    assert passed["events"][-1]["step3_participation_rule_certification"] == "CERTIFIED"


def test_certified_equal_close_fails_and_beyond_extreme_close_passes() -> None:
    short_equal = evaluate_step4(step4_count1_wait(base_interaction("SHORT"), failed_short_participation_candle(1)), candle(101.25, 101.25, 100.75, 101.2))
    assert short_equal["status"] == "WAIT"
    assert short_equal["state"]["step3_close_participation_pass"] is False
    short_beyond = evaluate_step4(step4_count1_wait(base_interaction("SHORT"), failed_short_participation_candle(1)), candle(101.25, 101.25, 100.25, 100.75))
    assert short_beyond["status"] == "READY"
    assert short_beyond["state"]["step3_close_participation_pass"] is True

    long_equal_interaction = base_interaction("LONG")
    long_equal_interaction["nearest_opposing_liquidity"] = {"name": "PMH", "price": 105.0}
    long_equal = evaluate_step4(step4_count1_wait(long_equal_interaction, failed_long_extension_candle(1)), candle(99.5, 100.0, 99.5, 99.3))
    assert long_equal["status"] == "WAIT"
    assert long_equal["state"]["step3_close_participation_pass"] is False
    long_beyond_interaction = base_interaction("LONG")
    long_beyond_interaction["nearest_opposing_liquidity"] = {"name": "PMH", "price": 105.0}
    long_beyond = evaluate_step4(step4_count1_wait(long_beyond_interaction, failed_long_extension_candle(1)), candle(99.5, 100.0, 99.25, 99.75))
    assert long_beyond["status"] == "READY"
    assert long_beyond["state"]["step3_close_participation_pass"] is True


def test_real_nq_0715_sequence_0746_does_not_participate_and_0747_locks_leg1() -> None:
    interaction = base_interaction("SHORT")
    interaction["initial_candle_a"] = candle(30572.0, 30597.0, 30571.25, 30594.5, "2026-06-18T14:45:00Z")
    interaction["nearest_opposing_liquidity"] = {"name": "PML", "price": 30400.0}
    interaction["atr_1m_14"] = 20.0
    interaction["daily_atr14"] = 20.0

    c1 = candle(30593.25, 30624.5, 30591.25, 30619.0, "2026-06-18T14:46:00Z")
    first = evaluate_step4(interaction, c1)
    assert first["status"] == "WAIT"
    assert first["state"]["step3_close_participation_pass"] is False
    assert first["state"]["step3_wick_participation_pct"] == 16.54
    assert first["state"]["step3_wick_participation_pass"] is False
    assert first["state"]["leg1_window_candle_index"] == 1

    c2 = candle(30619.5, 30641.5, 30611.0, 30631.0, "2026-06-18T14:47:00Z")
    second = evaluate_step4(first["state"], c2)
    assert second["status"] == "READY"
    assert second["next_step"] == "Step 5"
    assert second["state"]["step3_close_participation_pass"] is False
    assert second["state"]["step3_wick_participation_pct"] == 34.43
    assert second["state"]["step3_wick_participation_pass"] is True
    assert second["state"]["candle_a"]["timestamp"] == "2026-06-18T14:45:00Z"
    assert second["state"]["candle_b"]["timestamp"] == "2026-06-18T14:47:00Z"
    assert second["state"]["leg1_status"] == "COMPLETE"


def test_both_participation_paths_fail_routes_step7() -> None:
    interaction = base_interaction("SHORT")
    result = evaluate_step4(interaction, candle(101.5, 101.5, 101.0, 101.25))
    assert result["step"] == "Step 4"
    assert result["status"] == "WAIT"
    assert result["next_step"] == "Step 4"
    assert_reason(result)
    assert result["state"]["interaction_state"] == "ACTIVE"
    assert "leg1_status" not in result["state"]


def test_long_assigns_low_extreme() -> None:
    interaction = base_interaction("LONG")
    interaction["nearest_opposing_liquidity"] = {"name": "PMH", "price": 105.0}
    result = evaluate_step4(step4_count1_wait(interaction, failed_long_extension_candle(1)), candle(100.25, 101.0, 99.0, 99.75))
    assert result["status"] == "READY"
    assert result["state"]["leg1_extreme"] == result["state"]["leg2_sweep_extreme"]
    assert result["state"]["leg1_extreme_owner"] == "step4_window"
    assert result["state"]["anchor_extreme"] == result["state"]["leg2_sweep_extreme"]


def test_step2_step4_50_line_touch_invalidates_before_leg1_participation() -> None:
    interaction = base_interaction("LONG")
    interaction.update(
        {
            "active_liquidity": {"name": "PML", "price": 100.0, "side": "LOW"},
            "next_break_side_liquidity": {"name": "ONL", "price": 50.0, "side": "LOW"},
            "nearest_opposing_liquidity": {"name": "PMH", "price": 120.0},
            "atr_1m_14": 20.0,
        }
    )

    result = evaluate_step4(interaction, candle(99.5, 99.5, 75.0, 99.0, "2026-06-11T14:11:00Z"))

    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert result["reason"] == "STEP2_STEP4_50_LINE_TOUCHED"
    assert result["state"]["leg1_window_invalidated"] is True
    assert result["state"]["leg1_window_invalidation_reason"] == "STEP2_STEP4_50_LINE_TOUCHED"
    assert result["state"]["leg1_window_remaining"] == 0
    assert result["state"]["invalidation_source"] == "step2_step4_50_line"
    assert result["state"]["invalidation_source_step"] == "Step 4"
    assert result["state"]["step2_step4_50_line"] == 75.0
    assert "EXHAUSTION_50_LEG1" not in result["reason"]


def test_nq_2026_06_12_step2_step4_50_line_touch_invalidates_rejection() -> None:
    activation = candle(29383.0, 29392.5, 29316.25, 29322.5, "2026-06-12T13:33:00Z")
    touch = candle(29325.0, 29355.75, 29303.0, 29333.0, "2026-06-12T13:34:00Z")
    interaction = base_interaction("LONG")
    interaction.update(
        {
            "initial_candle_a": activation,
            "candle_a": activation,
            "active_liquidity": {"name": "PML", "price": 29354.0, "side": "lower"},
            "next_break_side_liquidity": {"name": "ONL", "price": 29260.0},
            "nearest_opposing_liquidity": {"name": "PMH", "price": 29646.0},
            "atr_1m_14": 20.0,
            "leg1_window_started_at": "2026-06-12T13:33:00Z",
            "leg1_window_candle_index": 0,
            "leg1_window_remaining": 4,
            "leg1_window_active": True,
        }
    )

    result = evaluate_step4(interaction, touch)

    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert result["reason"] == "STEP2_STEP4_50_LINE_TOUCHED"
    assert result["state"]["step2_step4_50_line"] == 29307.0
    assert touch["low"] <= result["state"]["step2_step4_50_line"]
    assert result["state"].get("leg1_status") is None


def test_short_step2_step4_50_line_touch_uses_candle_high() -> None:
    activation = candle(29640.0, 29683.75, 29635.0, 29678.0, "2026-06-12T13:33:00Z")
    touch = candle(29696.0, 29700.0, 29694.0, 29695.0, "2026-06-12T13:34:00Z")
    interaction = base_interaction("SHORT")
    interaction.update(
        {
            "initial_candle_a": activation,
            "candle_a": activation,
            "active_liquidity": {"name": "PMH", "price": 29646.0, "side": "upper"},
            "next_break_side_liquidity": {"name": "ONH", "price": 29740.0},
            "nearest_opposing_liquidity": {"name": "PML", "price": 29354.0},
            "atr_1m_14": 20.0,
            "leg1_window_started_at": "2026-06-12T13:33:00Z",
            "leg1_window_candle_index": 0,
            "leg1_window_remaining": 4,
            "leg1_window_active": True,
        }
    )

    result = evaluate_step4(interaction, touch)

    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert result["reason"] == "STEP2_STEP4_50_LINE_TOUCHED"
    assert result["state"]["step2_step4_50_line"] == 29693.0
    assert touch["high"] >= result["state"]["step2_step4_50_line"]
    assert touch["low"] > result["state"]["step2_step4_50_line"]


def test_step2_step4_50_line_touch_invalidates_when_candle_a_already_crossed_line_long() -> None:
    activation = candle(100.5, 100.75, 85.0, 99.5, "2026-06-19T14:10:00Z")
    candidate_b = candle(99.5, 100.0, 95.0, 99.75, "2026-06-19T14:11:00Z")
    interaction = base_interaction("LONG")
    interaction.update(
        {
            "initial_candle_a": activation,
            "candle_a": activation,
            "active_liquidity": {"name": "PML", "price": 100.0, "side": "lower"},
            "next_break_side_liquidity": {"name": "ONL", "price": 80.0, "side": "lower"},
            "nearest_opposing_liquidity": {"name": "PMH", "price": 120.0},
            "atr_1m_14": 20.0,
            "leg1_window_started_at": "2026-06-19T14:10:00Z",
            "leg1_window_candle_index": 0,
            "leg1_window_remaining": 4,
            "leg1_window_active": True,
        }
    )

    result = evaluate_step4(interaction, candidate_b)

    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert result["reason"] == "STEP2_STEP4_50_LINE_TOUCHED"
    assert result["state"]["step2_step4_50_line"] == 90.0
    assert result["state"]["step2_step4_50_line_touched_at"] == activation["timestamp"]
    assert result["state"]["invalidation_source"] == "step2_step4_50_line"
    assert result["state"]["invalidation_source_step"] == "Step 4"
    assert result["state"].get("leg1_status") is None


def test_step2_step4_50_line_touch_invalidates_when_candle_a_already_crossed_line_short() -> None:
    activation = candle(99.5, 115.0, 99.25, 100.5, "2026-06-19T14:10:00Z")
    candidate_b = candle(100.5, 105.0, 100.0, 100.25, "2026-06-19T14:11:00Z")
    interaction = base_interaction("SHORT")
    interaction.update(
        {
            "initial_candle_a": activation,
            "candle_a": activation,
            "active_liquidity": {"name": "PMH", "price": 100.0, "side": "upper"},
            "next_break_side_liquidity": {"name": "ONH", "price": 120.0, "side": "upper"},
            "nearest_opposing_liquidity": {"name": "PML", "price": 80.0},
            "atr_1m_14": 20.0,
            "leg1_window_started_at": "2026-06-19T14:10:00Z",
            "leg1_window_candle_index": 0,
            "leg1_window_remaining": 4,
            "leg1_window_active": True,
        }
    )

    result = evaluate_step4(interaction, candidate_b)

    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert result["reason"] == "STEP2_STEP4_50_LINE_TOUCHED"
    assert result["state"]["step2_step4_50_line"] == 110.0
    assert result["state"]["step2_step4_50_line_touched_at"] == activation["timestamp"]
    assert result["state"]["invalidation_source"] == "step2_step4_50_line"


def test_continuation_rs_next_liquidity_wick_invalidates_without_50_percent_fields() -> None:
    interaction = base_interaction("LONG")
    interaction["nearest_opposing_liquidity"] = {"name": "PMH", "price": 105.0}
    interaction.update(
        {
            "controlling_mode": "R/S",
            "candidate_modes": ["R/S"],
            "pathway_activation_type": "close",
            "pathway_level": 100.0,
            "structure_side_requirement": "BELOW_LEVEL",
            "reclaim_candle_a": candle(101.0, 101.25, 99.0, 99.5, "2026-07-02T13:33:00Z"),
            "initial_candle_a": candle(100.5, 101.5, 100.25, 101.0, "2026-07-02T13:32:00Z"),
            "active_liquidity": {"name": "PMH", "price": 100.0, "side": "upper"},
            "next_break_side_liquidity": {"name": "ONL", "price": 95.0, "side": "lower"},
        }
    )

    result = evaluate_step4(interaction, candle(99.25, 99.5, 95.0, 99.0, "2026-07-02T13:34:00Z"))

    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert result["reason"] == "CONTINUATION_NEXT_LIQUIDITY_TOUCHED"
    assert result["state"]["invalidation_source"] == "continuation_next_liquidity_wick"
    assert result["state"]["step2_step4_50_line"] is None
    assert result["state"]["step4_step5_75_line"] is None
    assert result["state"]["leg1_50_percent_rule_passed"] is None


def test_continuation_sr_next_liquidity_close_invalidates_without_50_percent_fields() -> None:
    interaction = base_interaction("SHORT")
    interaction.update(
        {
            "controlling_mode": "S/R",
            "candidate_modes": ["S/R"],
            "pathway_activation_type": "close",
            "pathway_level": 100.0,
            "structure_side_requirement": "ABOVE_LEVEL",
            "reclaim_candle_a": candle(99.0, 101.0, 98.75, 100.5, "2026-07-02T13:33:00Z"),
            "initial_candle_a": candle(99.5, 100.0, 98.5, 99.0, "2026-07-02T13:32:00Z"),
            "active_liquidity": {"name": "PML", "price": 100.0, "side": "lower"},
            "next_break_side_liquidity": {"name": "ONH", "price": 105.0, "side": "upper"},
            "nearest_opposing_liquidity": {"name": "PML", "price": 95.0},
        }
    )

    result = evaluate_step4(interaction, candle(100.5, 105.25, 100.25, 105.0, "2026-07-02T13:34:00Z"))

    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert result["reason"] == "CONTINUATION_NEXT_LIQUIDITY_TOUCHED"
    assert result["state"]["invalidation_source"] == "continuation_next_liquidity_close"
    assert result["state"]["step2_step4_50_line"] is None
    assert result["state"]["step4_step5_75_line"] is None
    assert result["state"]["invalidation_source_step"] == "Step 4"
    assert result["state"].get("leg1_status") is None


def test_upper_static_stack_rejects_close_boundary_only_leg1() -> None:
    interaction = base_interaction("SHORT")
    interaction.update(
        {
            "active_stack": {"name": "HIGH 1"},
            "stack_side": "upper",
            "extreme_boundary": 102.0,
            "close_boundary": 100.0,
            "tick_size": 0.25,
            "initial_candle_a": candle(100.0, 101.0, 99.75, 100.5),
            "stack_extreme_confirmation_seen": False,
        }
    )
    first = step4_count1_wait(interaction, failed_short_participation_candle(1))
    result = evaluate_step4(first, candle(100.5, 101.5, 100.0, 100.75))
    assert result["status"] == "WAIT"
    assert result["next_step"] == "Step 4"
    assert "leg1_status" not in result["state"]
    assert "close-boundary Leg 1 is not tradable" in result["reason"]


def test_lower_static_stack_rejects_close_boundary_only_leg1() -> None:
    interaction = base_interaction("LONG")
    interaction["nearest_opposing_liquidity"] = {"name": "PMH", "price": 105.0}
    interaction.update(
        {
            "active_stack": {"name": "LOW 1"},
            "stack_side": "lower",
            "extreme_boundary": 98.0,
            "close_boundary": 100.0,
            "tick_size": 0.25,
            "initial_candle_a": candle(100.0, 100.5, 99.0, 99.5),
            "stack_extreme_confirmation_seen": False,
        }
    )
    first = step4_count1_wait(interaction, failed_long_extension_candle(1))
    result = evaluate_step4(first, candle(99.5, 100.0, 98.8, 99.25))
    assert result["status"] == "WAIT"
    assert result["next_step"] == "Step 4"
    assert "leg1_status" not in result["state"]
    assert "close-boundary Leg 1 is not tradable" in result["reason"]


def test_live_static_stack_keeps_step2_activation_as_candle_a_until_explicit_replacement() -> None:
    confirmation = candle(100.0, 101.0, 99.5, 100.5, "2026-05-12T13:42:00Z")
    failed_b = candle(100.6, 101.5, 100.4, 101.3, "2026-05-12T13:43:00Z")
    valid_b = candle(101.3, 101.4, 100.0, 100.0, "2026-05-12T13:44:00Z")
    step25 = {
        "status": "READY",
        "next_step": "Step 3",
        "state": {
            "rejection_mode": "ON",
            "interaction_state": "ACTIVE",
            "step25_pathway_selection_complete": True,
            "controlling_mode": "Normal Rejection Mode",
            "candidate_modes": ["Normal Rejection Mode"],
            "initial_candle_a": confirmation,
        },
        "events": [],
    }
    step3 = {
        "status": "ALLOW_STEP_4",
        "next_step": "Step 4",
        "state": {
            "step3_allows_structure": True,
            "liquidity_type": "STATIC_STACK",
            "active_liquidity": {"name": "PMH", "price": 100.0},
            "active_stack": {"name": "HIGH 1"},
            "stack_side": "upper",
            "extreme_boundary": 101.25,
            "close_boundary": 100.0,
            "tick_size": 0.25,
            "stack_extreme_confirmation_seen": True,
            "stack_extreme_confirmation_candle": confirmation,
            "initial_candle_a": confirmation,
            "candle_a": confirmation,
        },
        "events": [],
    }
    rejection = {"watch_side": "SHORT"}
    liquidity = {"nearest_level_below": {"name": "PML", "price": 95.0}, "tick_size": 0.25}

    def snapshot(latest: dict) -> dict:
        return {
            "latest_bar_time": latest["timestamp"],
            "ohlc": latest,
            "ohlc_is_closed": True,
            "liquidity": liquidity,
            "atr": {"atr_1m_14": 31.25827865},
            "tv_context": {"daily_atr14": 31.25827865},
        }

    interaction = build_step4_interaction(snapshot(failed_b), rejection, step25, step3, {})
    assert interaction is not None
    assert interaction["candle_a"]["timestamp"] == "2026-05-12T13:42:00Z"
    assert interaction["candle_b"]["timestamp"] == "2026-05-12T13:43:00Z"
    assert interaction["candle_a_source"] == "initial_candle_a"
    assert interaction.get("awaiting_stack_candle_b") is not True

    first = evaluate_live_step4(snapshot(failed_b), rejection, step25, step3, {})
    assert first["status"] == "WAIT"
    assert first["next_step"] == "Step 4"
    assert first["state"]["leg1_window_candle_index"] == 1
    assert first["state"]["candle_a"]["timestamp"] == "2026-05-12T13:42:00Z"
    assert first["state"]["candle_a_source"] == "initial_candle_a"

    second = evaluate_live_step4(snapshot(valid_b), rejection, step25, step3, {"step4": first})
    assert second["status"] == "READY"
    assert second["next_step"] == "Step 5"
    assert second["state"]["candle_a"]["timestamp"] == "2026-05-12T13:42:00Z"
    assert second["state"]["candle_b"]["timestamp"] == "2026-05-12T13:44:00Z"
    assert second["state"]["step4_confirmed_at"] == "2026-05-12T13:44:00Z"


def test_nq_2026_06_18_stacked_rs_reclaim_uses_existing_stack_confirmation_for_step4() -> None:
    confirmation = candle(30512.0, 30547.0, 30509.75, 30544.25, "2026-06-18T14:34:00Z")
    reclaim = candle(30543.5, 30548.25, 30523.25, 30531.5, "2026-06-18T14:35:00Z")
    step25 = {
        "status": "READY",
        "next_step": "Step 3",
        "state": {
            "rejection_mode": "ON",
            "interaction_state": "ACTIVE",
            "step25_pathway_selection_complete": True,
            "controlling_mode": "R/S",
            "candidate_modes": ["R/S"],
            "initial_candle_a": reclaim,
            "reclaim_candle_a": reclaim,
            "pathway_activation_type": "close",
            "pathway_level": 30538.0,
            "structure_side_requirement": "BELOW_LEVEL",
            "continuation_step2_activated": True,
            "active_liquidity": {"name": "YH", "price": 30545.75, "side": "upper"},
        },
        "events": [],
    }
    step3 = {
        "status": "ALLOW_STEP_4",
        "next_step": "Step 4",
        "state": {
            "step3_allows_structure": True,
            "liquidity_type": "STATIC_STACK",
            "active_liquidity": {
                "name": "YH",
                "price": 30545.75,
                "display_name": "PMH/ONH/YH Liquidity",
                "side": "upper",
            },
            "active_stack": {"name": "HIGH 1"},
            "stack_side": "upper",
            "extreme_boundary": 30545.75,
            "close_boundary": 30538.0,
            "tick_size": 0.25,
            "stack_extreme_confirmation_seen": True,
            "stack_extreme_confirmation_candle": confirmation,
        },
        "events": [],
    }
    snapshot = {
        "normalized_symbol": "NQ",
        "latest_bar_time": reclaim["timestamp"],
        "latest_price": reclaim["close"],
        "ohlc": reclaim,
        "ohlc_is_closed": True,
        "liquidity": {
            "tick_size": 0.25,
            "nearest_level_above": {"name": "PMH", "price": 30538.0},
            "nearest_level_below": {"name": "PML", "price": 30397.0},
        },
        "atr": {"atr_1m_14": 20.0},
        "tv_context": {"daily_atr14": 20.0},
    }

    interaction = build_step4_interaction(
        snapshot,
        {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "YH", "trigger_price": 30545.75},
        step25,
        step3,
        {},
    )
    assert interaction is not None
    # Continuation Step 4 uses the reclaim candle as Candle A and waits for the next candle.
    assert interaction["controlling_mode"] == "R/S"
    assert interaction["setup_direction"] == "LONG"
    assert interaction["candle_a"]["timestamp"] == "2026-06-18T14:35:00Z"
    assert interaction.get("candle_b") is None
    assert interaction.get("awaiting_stack_candle_b") is not True

    result = evaluate_live_step4(
        snapshot,
        {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "YH", "trigger_price": 30545.75},
        step25,
        step3,
        {},
    )
    assert result["status"] == "WAIT"
    assert result["next_step"] == "Step 4"
    assert result["state"]["candle_a"]["timestamp"] == "2026-06-18T14:35:00Z"
    assert result["state"]["setup_direction"] == "LONG"
    assert result["reason"] == "Step 4 waiting: Step 2 confirmation anchor and a participation candle are required."


def test_ym_2026_05_28_failed_c1_keeps_rejection_window_for_c2_wick() -> None:
    activation = candle(50582.0, 50590.0, 50570.0, 50576.0, "2026-05-28T13:29:00Z")
    c1_failed = candle(50562.0, 50570.0, 50560.0, 50561.0, "2026-05-28T13:30:00Z")
    c2_wick_valid = candle(50568.0, 50570.0, 50550.0, 50566.0, "2026-05-28T13:31:00Z")
    step25 = {
        "status": "READY",
        "next_step": "Step 3",
        "state": {
            "rejection_mode": "ON",
            "interaction_state": "ACTIVE",
            "step25_pathway_selection_complete": True,
            "controlling_mode": "Normal Rejection Mode",
            "candidate_modes": ["Normal Rejection Mode"],
            "initial_candle_a": activation,
        },
        "events": [],
    }
    step3 = {
        "status": "ALLOW_STEP_4",
        "next_step": "Step 4",
        "state": {
            "step3_allows_structure": True,
            "active_liquidity": {
                "name": "PML",
                "price": 50576.0,
                "display_name": "PML/ONL Liquidity",
                "side": "lower",
            },
        },
        "events": [],
    }
    rejection = {"rejection_mode": "ON", "watch_side": "LONG", "trigger_level": "PML", "trigger_price": 50576.0}
    liquidity = {"nearest_level_above": {"name": "PMH", "price": 50650.0}, "nearest_level_below": {"name": "LL", "price": 50500.0}, "tick_size": 1.0}

    def snapshot(latest: dict) -> dict:
        return {
            "normalized_symbol": "YM",
            "latest_bar_time": latest["timestamp"],
            "latest_price": latest["close"],
            "ohlc": latest,
            "ohlc_is_closed": True,
            "liquidity": liquidity,
            "atr": {"atr_1m_14": 10.0},
            "tv_context": {"daily_atr14": 10.0},
        }

    started = evaluate_live_step4(snapshot(activation), rejection, step25, step3, {})
    assert started["status"] == "WAIT"
    assert started["state"]["leg1_window_candle_index"] == 0
    assert started["state"]["leg1_window_active"] is True

    first = evaluate_live_step4(snapshot(c1_failed), rejection, step25, step3, {"step4": started})
    assert first["status"] == "WAIT"
    assert first["next_step"] == "Step 4"
    assert first["state"]["leg1_window_candle_index"] == 1
    assert first["state"]["leg1_window_active"] is True
    assert first["state"].get("leg1_state_locked") is not True
    assert first["state"].get("leg1_status") != "COMPLETE"

    second = evaluate_live_step4(snapshot(c2_wick_valid), rejection, step25, step3, {"step4": first})
    assert second["status"] == "READY"
    assert second["next_step"] == "Step 5"
    assert second["state"]["leg1_window_candle_index"] == 2
    assert second["state"]["leg1_status"] == "COMPLETE"
    assert second["state"]["leg1_state_locked"] is True
    assert second["state"]["opposite_participation"] == "PRESENT"
    assert second["state"]["participation_candle_number"] == 2


def test_ym_2026_05_29_same_pml_close_through_does_not_recreate_step2_window() -> None:
    pml = 50836.0
    candles = [
        candle(50840.0, 50842.0, 50820.0, 50835.0, "2026-05-29T13:15:00Z"),
        candle(50811.0, 50835.0, 50810.0, 50811.0, "2026-05-29T13:16:00Z"),
        candle(50801.0, 50813.0, 50800.0, 50801.0, "2026-05-29T13:17:00Z"),
        candle(50791.0, 50803.0, 50790.0, 50791.0, "2026-05-29T13:18:00Z"),
        candle(50781.0, 50793.0, 50780.0, 50781.0, "2026-05-29T13:19:00Z"),
        candle(50771.0, 50783.0, 50770.0, 50771.0, "2026-05-29T13:20:00Z"),
        candle(50761.0, 50773.0, 50760.0, 50761.0, "2026-05-29T13:21:00Z"),
    ]
    rejection = {"rejection_mode": "ON", "watch_side": "LONG", "trigger_level": "PML", "trigger_price": pml}
    step3 = {
        "status": "ALLOW_STEP_4",
        "next_step": "Step 4",
        "state": {
            "step3_allows_structure": True,
            "active_liquidity": {"name": "PML", "price": pml, "display_name": "PML", "side": "lower"},
        },
        "events": [],
    }
    liquidity = {"nearest_level_above": {"name": "PMH", "price": 50950.0}, "nearest_level_below": {"name": "LL", "price": 50700.0}, "tick_size": 1.0}

    def snapshot(latest: dict) -> dict:
        return {
            "normalized_symbol": "YM",
            "latest_bar_time": latest["timestamp"],
            "latest_price": latest["close"],
            "ohlc": latest,
            "ohlc_is_closed": True,
            "liquidity": liquidity,
            "atr": {"atr_1m_14": 10.0},
            "tv_context": {"daily_atr14": 10.0},
        }

    persisted: dict = {}
    observed = []
    for current in candles:
        step_2_1a = {
            "step_2_activated": True,
            "candle_a": current,
            "active_level": "PML",
            "level_price": pml,
            "side": "lower",
        }
        step25 = evaluate_live_step25(snapshot(current), rejection, step_2_1a, persisted)
        step4 = evaluate_live_step4(snapshot(current), rejection, step25, step3, persisted)
        observed.append(step4["state"])
        persisted = {"step25": step25, "step4": step4}

    assert observed[0]["leg1_window_started_at"] == "2026-05-29T13:15:00Z"
    assert observed[0]["leg1_window_candle_index"] == 0
    for state in observed[1:]:
        assert state["initial_candle_a"]["timestamp"] == "2026-05-29T13:15:00Z"
        assert state["leg1_window_started_at"] == "2026-05-29T13:15:00Z"
        assert state["leg1_window_candle_index"] != 0
    assert [state["leg1_window_candle_index"] for state in observed[1:4]] == [1, 2, 3]


def test_nq_2026_05_29_stack_step2_owner_survives_repeated_close_through() -> None:
    close_boundary = 30363.75
    extreme_boundary = 30372.25
    candles = [
        candle(30360.0, 30375.0, 30358.0, 30373.0, "2026-05-29T13:33:00Z"),
        candle(30379.0, 30380.0, 30370.0, 30379.0, "2026-05-29T13:34:00Z"),
        candle(30380.0, 30381.0, 30374.0, 30380.0, "2026-05-29T13:35:00Z"),
        candle(30381.0, 30382.0, 30375.0, 30381.0, "2026-05-29T13:36:00Z"),
    ]
    tv_context = {
        "daily_atr14": 20.0,
        "levels": {
            "ONH": {"status": "ACTIVE", "price": close_boundary, "stack_group": "HIGH 1"},
            "LH": {"status": "ACTIVE", "price": 30368.0, "stack_group": "HIGH 1"},
            "PMH": {"status": "ACTIVE", "price": extreme_boundary, "stack_group": "HIGH 1"},
        }
    }
    liquidity = {"nearest_level_above": {"name": "YH", "price": 30450.0}, "nearest_level_below": {"name": "PML", "price": 30200.0}, "tick_size": 0.25}

    def snapshot(latest: dict) -> dict:
        return {
            "normalized_symbol": "NQ",
            "latest_bar_time": latest["timestamp"],
            "latest_price": latest["close"],
            "ohlc": latest,
            "ohlc_is_closed": True,
            "liquidity": liquidity,
            "tv_context": tv_context,
            "atr": {"atr_1m_14": 20.0},
        }

    persisted: dict = {}
    observed = []
    for index, current in enumerate(candles):
        step2 = evaluate_live_step_2_1a(snapshot(current), {}, liquidity, persisted)
        rejection = rejection_from_step2_activation(step2, "NQ")
        symbol_persisted = persisted.get("state_by_symbol", {}).get("NQ", {}) if isinstance(persisted.get("state_by_symbol"), dict) else {}
        step25 = evaluate_live_step25(snapshot(current), rejection, step2, symbol_persisted)
        step3 = {
            "status": "ALLOW_STEP_4",
            "next_step": "Step 4",
            "state": {
                "step3_allows_structure": True,
                "active_liquidity": {
                    "name": step2["active_level"],
                    "price": step2["level_price"],
                    "display_name": (step2.get("active_liquidity_group") or {}).get("display_name"),
                    "side": "upper",
                    "group": step2.get("active_liquidity_group"),
                },
            },
            "events": [],
        }
        step4 = evaluate_live_step4(snapshot(current), rejection, step25, step3, symbol_persisted)
        observed.append((step2, step25, step4))
        symbol_state = {"normalized_symbol": "NQ", "step25": step25, "step4": step4}
        if index == 0:
            symbol_state["step_2_1a"] = step2
            symbol_state["step2_locked_owner"] = step2.get("step2_locked_owner")
        persisted = {"state_by_symbol": {"NQ": symbol_state}}

    assert observed[0][0]["active_liquidity_group"]["name"] == "HIGH 1"
    assert observed[0][0]["active_liquidity_group"]["close_boundary"] == close_boundary
    assert observed[0][0]["active_liquidity_group"]["extreme_boundary"] == extreme_boundary
    assert observed[0][2]["state"]["setup_direction"] == "SHORT"
    assert observed[0][2]["state"]["leg1_window_started_at"] == "2026-05-29T13:33:00Z"
    assert observed[0][2]["state"]["leg1_window_candle_index"] == 0

    for step2, step25, step4 in observed[1:]:
        assert step2["candle_a"]["timestamp"] == "2026-05-29T13:33:00Z"
        assert step25["state"]["initial_candle_a"]["timestamp"] == "2026-05-29T13:33:00Z"
        assert step4["state"]["leg1_window_started_at"] == "2026-05-29T13:33:00Z"
        assert step4["state"]["leg1_window_candle_index"] != 0
        assert step4["state"]["leg1_window_expires_at"] == "2026-05-29T13:37:00Z"
    assert [step4["state"]["leg1_window_candle_index"] for _, _, step4 in observed[1:]] == [1, 2, 3]


def test_nq_2026_06_23_rejection_candle_b_has_priority_over_release_reseed_and_continuation() -> None:
    bars = [
        candle(29705.0, 29708.0, 29680.0, 29693.0, "2026-06-23T13:29:00Z"),
        candle(29714.75, 29717.25, 29638.75, 29648.0, "2026-06-23T13:30:00Z"),
        candle(29649.25, 29740.0, 29616.5, 29730.5, "2026-06-23T13:31:00Z"),
    ]
    tv_context = {
        "daily_atr14": 728.7349411605,
        "levels": {
            "PML": {"status": "ACTIVE", "price": 29691.75, "stack_group": "LOW 1"},
            "ONL": {"status": "ACTIVE", "price": 29690.25, "stack_group": "LOW 1"},
            "LL": {"status": "ACTIVE", "price": 29616.5, "stack_group": "NONE"},
            "ONH": {"status": "ACTIVE", "price": 29720.25, "stack_group": "HIGH 1"},
            "PMH": {"status": "ACTIVE", "price": 29721.75, "stack_group": "HIGH 1"},
            "LH": {"status": "INACTIVE", "price": 29731.25, "stack_group": "NONE"},
        },
    }
    liquidity = {
        "nearest_level_above": {"name": "ONH", "price": 29720.25},
        "nearest_level_below": {"name": "LL", "price": 29616.5},
        "tick_size": 0.25,
    }

    def snapshot(latest: dict) -> dict:
        return {
            "normalized_symbol": "NQ",
            "requested_symbol": "NQ",
            "latest_bar_time": latest["timestamp"],
            "latest_price": latest["close"],
            "ohlc": latest,
            "ohlc_is_closed": True,
            "liquidity": liquidity,
            "tv_context": tv_context,
            "atr": {"atr_1m_14": 20.0},
            "pre_open_observed_extreme": {
                "side": "lower",
                "price": 29675.75,
                "source_level": "PML",
                "stack_group": "LOW 1",
            },
        }

    original_recent_closed_bars = evaluate_live_step_2_1a.__globals__["recent_closed_bars"]
    evaluate_live_step_2_1a.__globals__["recent_closed_bars"] = lambda symbol, limit: bars[-limit:]
    try:
        persisted: dict = {
            "state_by_symbol": {
                "NQ": {
                    "pre_open_observed_extreme": {
                        "side": "lower",
                        "price": 29675.75,
                        "source_level": "PML",
                        "stack_group": "LOW 1",
                    }
                }
            }
        }
        observed = []
        for index, current in enumerate(bars[1:]):
            current_snapshot = snapshot(current)
            symbol_persisted = (
                persisted.get("state_by_symbol", {}).get("NQ", {})
                if isinstance(persisted.get("state_by_symbol"), dict)
                else {}
            )
            step2 = evaluate_live_step_2_1a(current_snapshot, {}, liquidity, persisted)
            rejection = rejection_from_step2_activation(step2, "NQ")
            step25 = evaluate_live_step25(current_snapshot, rejection, step2, symbol_persisted)
            step3 = evaluate_live_step3(current_snapshot, rejection, step25, step2, symbol_persisted)
            step4 = evaluate_live_step4(current_snapshot, rejection, step25, step3, symbol_persisted)
            step5 = evaluate_live_step5(current_snapshot, step4, symbol_persisted)
            step6 = evaluate_live_step6(current_snapshot, step5, symbol_persisted)
            observed.append((step2, step25, step3, step4, step5, step6))
            persisted = {
                "state_by_symbol": {
                    "NQ": {
                        "normalized_symbol": "NQ",
                        "pre_open_observed_extreme": current_snapshot["pre_open_observed_extreme"],
                        "step_2_1a": step2,
                        "step25": step25,
                        "step3": step3,
                        "step4": step4,
                        "step5": step5,
                        "step6": step6,
                        "step2_locked_owner": step2.get("step2_locked_owner"),
                        "last_interacted_liquidity": step2.get("last_interacted_liquidity"),
                        "step_2_1a_last_evaluated_bar_time": step2.get("last_evaluated_bar_time"),
                        "step_2_1a_candle_index": step2.get("next_candle_index"),
                    }
                }
            }
            if index == 0:
                assert step2["step_2_activated"] is True
                assert step2["step2_locked_owner"]["setup_direction"] == "LONG"
                assert step4["status"] == "WAIT"
                assert step4["state"]["candle_a"]["timestamp"] == "2026-06-23T13:30:00Z"
                assert step4["state"]["leg1_window_candle_index"] == 0

        step2_0631, step25_0631, step3_0631, step4_0631, step5_0631, step6_0631 = observed[1]
        assert step2_0631["step_2_activated"] is True
        assert step2_0631["audit_step2_event"] == "already_active"
        assert step2_0631["active_level"] == "ONL"
        assert step2_0631["candle_a"]["timestamp"] == "2026-06-23T13:30:00Z"
        assert step25_0631["state"]["controlling_mode"] == "Normal Rejection Mode"
        assert step25_0631["state"].get("continuation_step2_activated") is not True
        assert step25_0631["state"].get("reclaim_candle_a") is None
        assert step3_0631["status"] == "ALLOW_STEP_4"
        assert step4_0631["status"] == "READY"
        assert step4_0631["next_step"] == "Step 5"
        assert step4_0631["state"]["leg1_window_candle_index"] == 1
        assert step4_0631["state"].get("leg1_status") == "COMPLETE"
        assert step5_0631["status"] == "WAIT"
        assert step6_0631["status"] == "WAIT"
    finally:
        evaluate_live_step_2_1a.__globals__["recent_closed_bars"] = original_recent_closed_bars


def test_ym_2026_07_01_replay_freezes_step2_identity_and_step4_after_confirmation() -> None:
    import entry_agent

    bars = [
        candle(52737.0, 52776.0, 52733.0, 52772.0, "2026-07-01T14:13:00Z"),
        candle(52770.0, 52802.0, 52760.0, 52794.0, "2026-07-01T14:14:00Z"),
        candle(52794.0, 52805.0, 52781.0, 52781.0, "2026-07-01T14:15:00Z"),
        candle(52781.0, 52800.0, 52764.0, 52766.0, "2026-07-01T14:16:00Z"),
        candle(52768.0, 52770.0, 52737.0, 52739.0, "2026-07-01T14:17:00Z"),
        candle(52739.0, 52741.0, 52718.0, 52726.0, "2026-07-01T14:18:00Z"),
        candle(52730.0, 52754.0, 52725.0, 52752.0, "2026-07-01T14:19:00Z"),
    ]
    tv_context = {
        "daily_atr14": 712.0,
        "levels": {
            "PMH": {"status": "ACTIVE", "price": 52570.0, "stack_group": "HIGH 1"},
            "PML": {"status": "ACTIVE", "price": 52461.0, "stack_group": "LOW 1"},
            "LH": {"status": "ACTIVE", "price": 52586.0, "stack_group": "HIGH 1"},
            "LL": {"status": "ACTIVE", "price": 52478.0, "stack_group": "NONE"},
            "ONH": {"status": "ACTIVE", "price": 52625.0, "stack_group": "HIGH 1"},
            "ONL": {"status": "ACTIVE", "price": 52427.0, "stack_group": "LOW 1"},
            "YH": {"status": "ACTIVE", "price": 52763.0, "stack_group": "NONE"},
            "YL": {"status": "ACTIVE", "price": 52383.0, "stack_group": "LOW 1"},
        },
    }
    liquidity = {
        "nearest_level_above": {"name": None, "price": None},
        "nearest_level_below": {"name": "YH", "price": 52763.0},
        "tick_size": 1.0,
    }

    def snapshot(latest: dict) -> dict:
        return {
            "normalized_symbol": "YM",
            "requested_symbol": "YM",
            "latest_bar_time": latest["timestamp"],
            "latest_price": latest["close"],
            "ohlc": latest,
            "ohlc_is_closed": True,
            "liquidity": liquidity,
            "tv_context": tv_context,
            "atr": {"atr_1m_14": 20.0},
            "pre_open_observed_extreme": {
                "side": "upper",
                "price": 52763.0,
                "source_level": "YH",
                "stack_group": "NONE",
            },
        }

    def persist_symbol_state(current_snapshot: dict) -> dict:
        return {
            "normalized_symbol": "YM",
            "pre_open_observed_extreme": current_snapshot["pre_open_observed_extreme"],
            "step_2_1a": current_snapshot["step_2_1a"],
            "step25": current_snapshot["step25"],
            "step3": current_snapshot["step3"],
            "step4": current_snapshot["step4"],
            "step5": current_snapshot["step5"],
            "step6": current_snapshot["step6"],
            "step2_locked_owner": current_snapshot["step_2_1a"].get("step2_locked_owner"),
            "last_interacted_liquidity": current_snapshot["step_2_1a"].get("last_interacted_liquidity"),
            "step_2_1a_last_evaluated_bar_time": current_snapshot["step_2_1a"].get("last_evaluated_bar_time"),
            "step_2_1a_candle_index": current_snapshot["step_2_1a"].get("next_candle_index"),
            "rejection_lane": current_snapshot.get("rejection_lane"),
            "continuation_lane": current_snapshot.get("continuation_lane"),
            "trade_state": current_snapshot.get("trade_state"),
            "market_state": current_snapshot.get("market_state"),
        }

    original_recent_closed_bars = evaluate_live_step_2_1a.__globals__["recent_closed_bars"]
    original_run_once = entry_agent.run_once
    original_load_entry_state = entry_agent.load_entry_state
    evaluate_live_step_2_1a.__globals__["recent_closed_bars"] = lambda symbol, limit: bars[-limit:]
    try:
        persisted: dict = {"state_by_symbol": {"YM": {"pre_open_observed_extreme": snapshot(bars[0])["pre_open_observed_extreme"]}}}
        frozen_step2_anchor: dict | None = None
        frozen_step4_anchor: dict | None = None
        step4_confirmed_at: str | None = None
        public_statuses: list[dict[str, object]] = []

        for index, current in enumerate(bars):
            evaluate_live_step_2_1a.__globals__["recent_closed_bars"] = lambda symbol, limit, _bars=bars[: index + 1]: _bars[-limit:]
            current_snapshot = snapshot(current)
            symbol_persisted = (
                persisted.get("state_by_symbol", {}).get("YM", {})
                if isinstance(persisted.get("state_by_symbol"), dict)
                else {}
            )
            step2 = evaluate_live_step_2_1a(current_snapshot, {}, liquidity, persisted)
            rejection = rejection_from_step2_activation(step2, "YM")
            step25 = evaluate_live_step25(current_snapshot, rejection, step2, symbol_persisted)
            step3 = evaluate_live_step3(current_snapshot, rejection, step25, step2, symbol_persisted)
            step4 = evaluate_live_step4(current_snapshot, rejection, step25, step3, symbol_persisted)
            step5 = evaluate_live_step5(current_snapshot, step4, symbol_persisted)
            step6 = evaluate_live_step6(current_snapshot, step5, symbol_persisted)
            current_snapshot.update(
                {
                    "step_2_1a": step2,
                    "rejection": rejection,
                    "step25": step25,
                    "step3": step3,
                    "step4": step4,
                    "step5": step5,
                    "step6": step6,
                }
            )
            current_snapshot = apply_confirmed_lifecycle_invariants(current_snapshot, symbol_persisted)
            current_snapshot["rejection_lane"], current_snapshot["continuation_lane"] = entry_agent.snapshot_lane_statuses(current_snapshot, symbol_persisted)
            current_snapshot["trade_state"] = entry_agent.build_trade_state_snapshot(current_snapshot)
            current_snapshot["market_state"] = entry_agent.build_market_state_snapshot(current_snapshot)
            step2 = current_snapshot["step_2_1a"]
            step4 = current_snapshot["step4"]

            if frozen_step2_anchor is None and step2.get("step_2_activated") is True:
                frozen_step2_anchor = {
                    "step2_confirmed_at": current_snapshot.get("frozen_step2_anchor_time") or step2.get("step2_activated_at"),
                    "step2_owner_seeded_at": step2.get("step2_owner_seeded_at"),
                    "step2_activated_at": step2.get("step2_activated_at"),
                    "step2_owner_name": (step2.get("step2_locked_owner") or {}).get("active_liquidity_name"),
                    "step2_direction": (step2.get("step2_locked_owner") or {}).get("setup_direction"),
                    "active_liquidity": (step2.get("step2_locked_owner") or {}).get("active_liquidity"),
                    "close_boundary": (step2.get("step2_locked_owner") or {}).get("close_boundary"),
                    "extreme_boundary": (step2.get("step2_locked_owner") or {}).get("extreme_boundary"),
                }
            elif frozen_step2_anchor is not None:
                assert step2.get("step2_owner_seeded_at") == frozen_step2_anchor["step2_owner_seeded_at"]
                assert step2.get("step2_activated_at") == frozen_step2_anchor["step2_activated_at"]
                assert current_snapshot.get("frozen_step2_anchor_time") == frozen_step2_anchor["step2_confirmed_at"]
                assert (step2.get("step2_locked_owner") or {}).get("active_liquidity_name") == frozen_step2_anchor["step2_owner_name"]
                assert (step2.get("step2_locked_owner") or {}).get("setup_direction") == frozen_step2_anchor["step2_direction"]
                assert (step2.get("step2_locked_owner") or {}).get("active_liquidity") == frozen_step2_anchor["active_liquidity"]
                assert (step2.get("step2_locked_owner") or {}).get("close_boundary") == frozen_step2_anchor["close_boundary"]
                assert (step2.get("step2_locked_owner") or {}).get("extreme_boundary") == frozen_step2_anchor["extreme_boundary"]

            step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
            if (
                frozen_step4_anchor is None
                and step4.get("status") == "READY"
                and step4_state.get("step4_confirmed_at")
            ):
                step4_confirmed_at = step4_state.get("step4_confirmed_at")
                frozen_step4_anchor = {
                    "step4_confirmed_at": step4_state.get("step4_confirmed_at"),
                    "step4_window_count": step4_state.get("step4_window_count"),
                    "step4_direction": step4_state.get("setup_direction"),
                    "step4_owner_name": ((step4_state.get("active_liquidity") or {}).get("name")),
                    "step4_status": step4.get("status"),
                    "leg2_sweep_extreme": step4_state.get("leg2_sweep_extreme"),
                    "step5_close_boundary": step4_state.get("step5_close_boundary"),
                    "step4_participation_50_line": step4_state.get("step2_step4_50_line"),
                    "step4_participation_75_line": step4_state.get("step4_step5_75_line"),
                    "step4_step5_75_line": step4_state.get("step4_step5_75_line"),
                    "setup_direction": step4_state.get("setup_direction"),
                    "selected_pathway": current_snapshot.get("frozen_step4_selected_pathway"),
                }
            elif frozen_step4_anchor is not None and current_snapshot.get("latest_bar_time") < "2026-07-01T14:17:00Z":
                assert step4_state.get("step4_confirmed_at") == frozen_step4_anchor["step4_confirmed_at"]
                assert step4_state.get("step4_window_count") == frozen_step4_anchor["step4_window_count"]
                assert step4_state.get("setup_direction") == frozen_step4_anchor["step4_direction"]
                assert ((step4_state.get("active_liquidity") or {}).get("name")) == frozen_step4_anchor["step4_owner_name"]
                assert step4.get("status") == frozen_step4_anchor["step4_status"]
                assert step4_state.get("leg2_sweep_extreme") == frozen_step4_anchor["leg2_sweep_extreme"]
                assert step4_state.get("step5_close_boundary") == frozen_step4_anchor["step5_close_boundary"]
                assert step4_state.get("step2_step4_50_line") == frozen_step4_anchor["step4_participation_50_line"]
                assert step4_state.get("step4_step5_75_line") == frozen_step4_anchor["step4_step5_75_line"]
                assert current_snapshot.get("frozen_step4_selected_pathway") == frozen_step4_anchor["selected_pathway"]

            persisted = {"state_by_symbol": {"YM": persist_symbol_state(current_snapshot)}}
            entry_agent.run_once = lambda symbol="YM", persist=False, _snapshot=current_snapshot: _snapshot
            entry_agent.load_entry_state = lambda _persisted=persisted: _persisted
            public_statuses.append(build_entry_status("YM"))

        assert frozen_step2_anchor is not None
        assert frozen_step2_anchor["step2_confirmed_at"] == "2026-07-01T14:13:00Z"
        assert step4_confirmed_at is not None
        statuses_by_time = {str(status.get("candle_time")): status for status in public_statuses}
        assert statuses_by_time["2026-07-01T14:13:00Z"]["step2_candle_count"] == 0
        assert statuses_by_time["2026-07-01T14:14:00Z"]["step2_candle_count"] == 1
        assert statuses_by_time["2026-07-01T14:15:00Z"]["step2_candle_count"] == 2
        assert statuses_by_time["2026-07-01T14:16:00Z"]["step2_candle_count"] == 2
        assert statuses_by_time["2026-07-01T14:13:00Z"]["continuation_eligible"] is False
        assert statuses_by_time["2026-07-01T14:14:00Z"]["continuation_eligible"] is False
        assert statuses_by_time["2026-07-01T14:15:00Z"]["continuation_eligible"] is True
        assert statuses_by_time["2026-07-01T14:15:00Z"]["continuation_eligible_at"] == "2026-07-01T14:15:00Z"
        assert statuses_by_time["2026-07-01T14:15:00Z"]["continuation_evaluation_started_at"] is None
        assert statuses_by_time["2026-07-01T14:15:00Z"]["continuation_reference_boundary_type"] == "frozen_rejection_close_boundary"
        assert statuses_by_time["2026-07-01T14:15:00Z"]["continuation_reference_boundary_price"] == 52763.0
        assert statuses_by_time["2026-07-01T14:17:00Z"]["continuation_eligible"] is False
        assert statuses_by_time["2026-07-01T14:17:00Z"]["continuation_active_boundary_price"] == 52763.0
        assert statuses_by_time["2026-07-01T14:17:00Z"]["continuation_evaluation_started_at"] == "2026-07-01T14:17:00Z"
        assert statuses_by_time["2026-07-01T14:17:00Z"]["continuation_evaluation_reason"] == (
            "Continuation Step 2 confirmed; lane frozen and controlling. Waiting for Step 4 participation."
        )
        assert (statuses_by_time["2026-07-01T14:17:00Z"]["continuation_lane"] or {}).get("step2_status") == "CONFIRMED"
        assert (statuses_by_time["2026-07-01T14:17:00Z"]["continuation_lane"] or {}).get("step2_confirmed_at") == "2026-07-01T14:17:00Z"
        assert (statuses_by_time["2026-07-01T14:18:00Z"]["continuation_lane"] or {}).get("step2_confirmed_at") == "2026-07-01T14:17:00Z"
        assert (statuses_by_time["2026-07-01T14:19:00Z"]["continuation_lane"] or {}).get("step2_confirmed_at") == "2026-07-01T14:17:00Z"
        assert (statuses_by_time["2026-07-01T14:17:00Z"]["continuation_lane"] or {}).get("close_boundary") == 52763.0
        assert (statuses_by_time["2026-07-01T14:17:00Z"]["continuation_lane"] or {}).get("step2_candle_count") == 0
        assert (statuses_by_time["2026-07-01T14:18:00Z"]["continuation_lane"] or {}).get("step2_candle_count") == 1
        assert (statuses_by_time["2026-07-01T14:19:00Z"]["continuation_lane"] or {}).get("step2_candle_count") == 2
        assert (statuses_by_time["2026-07-01T14:17:00Z"]["continuation_lane"] or {}).get("step4_status") == "WAIT"
        assert (statuses_by_time["2026-07-01T14:18:00Z"]["continuation_lane"] or {}).get("step4_status") == "CONFIRMED"
        assert (statuses_by_time["2026-07-01T14:19:00Z"]["continuation_lane"] or {}).get("step4_status") == "CONFIRMED"
        assert statuses_by_time["2026-07-01T14:13:00Z"]["current_pathway_control"] == "rejection"
        assert statuses_by_time["2026-07-01T14:14:00Z"]["current_pathway_control"] == "rejection"
        assert statuses_by_time["2026-07-01T14:15:00Z"]["current_pathway_control"] == "rejection"
        assert statuses_by_time["2026-07-01T14:16:00Z"]["current_pathway_control"] == "rejection"
        assert statuses_by_time["2026-07-01T14:17:00Z"]["current_pathway_control"] == "continuation"
        assert statuses_by_time["2026-07-01T14:18:00Z"]["current_pathway_control"] == "continuation"
        assert statuses_by_time["2026-07-01T14:19:00Z"]["current_pathway_control"] == "continuation"
        post_confirmation = [status for status in public_statuses if status.get("candle_time") >= "2026-07-01T14:15:00Z"]
        assert post_confirmation
        frozen_trade_state = None
        for status in post_confirmation:
            if status.get("candle_time") < "2026-07-01T14:17:00Z":
                assert status["active_liquidity_name"] == "YH"
                assert status["selected_liquidity_name"] == "YH"
                assert status["step2_owner_name"] == "YH"
                assert status["close_boundary"] == 52763.0
                assert status["extreme_boundary"] == 52763.0
                assert status["leg2_sweep_extreme"] == 52805.0
                assert status["step5_close_boundary"] == 52794.0
            trade_state = status.get("trade_state") or {}
            market_state = status.get("market_state") or {}
            if status.get("candle_time") < "2026-07-01T14:17:00Z":
                assert trade_state.get("active") is True
                assert trade_state.get("active_liquidity_name") == "YH"
                assert trade_state.get("selected_liquidity_name") == "YH"
                assert trade_state.get("close_boundary") == 52763.0
                assert trade_state.get("extreme_boundary") == 52763.0
                assert (trade_state.get("step4") or {}).get("leg2_sweep_extreme") == 52805.0
                assert (trade_state.get("step4") or {}).get("step5_close_boundary") == 52794.0
            assert market_state.get("active_liquidity_name") is not None
            if status.get("candle_time") < "2026-07-01T14:17:00Z" and frozen_trade_state is None:
                frozen_trade_state = trade_state
            elif status.get("candle_time") < "2026-07-01T14:17:00Z":
                assert trade_state == frozen_trade_state
            continuation_lane = status.get("continuation_lane") or {}
            if status.get("candle_time") >= "2026-07-01T14:17:00Z":
                assert continuation_lane.get("step2_status") == "CONFIRMED"
                assert continuation_lane.get("step2_confirmed_at") == "2026-07-01T14:17:00Z"
            else:
                assert continuation_lane.get("step2_status") != "CONFIRMED"
    finally:
        evaluate_live_step_2_1a.__globals__["recent_closed_bars"] = original_recent_closed_bars
        entry_agent.run_once = original_run_once
        entry_agent.load_entry_state = original_load_entry_state


def test_ym_2026_07_01_continuation_step2_creates_clean_downstream_lifecycle() -> None:
    import entry_agent

    bars = [
        candle(52737.0, 52776.0, 52733.0, 52772.0, "2026-07-01T14:13:00Z"),
        candle(52770.0, 52802.0, 52760.0, 52794.0, "2026-07-01T14:14:00Z"),
        candle(52794.0, 52805.0, 52781.0, 52781.0, "2026-07-01T14:15:00Z"),
        candle(52781.0, 52800.0, 52764.0, 52766.0, "2026-07-01T14:16:00Z"),
        candle(52768.0, 52770.0, 52737.0, 52739.0, "2026-07-01T14:17:00Z"),
        candle(52739.0, 52741.0, 52718.0, 52726.0, "2026-07-01T14:18:00Z"),
        candle(52730.0, 52754.0, 52725.0, 52752.0, "2026-07-01T14:19:00Z"),
    ]
    tv_context = {
        "daily_atr14": 712.0,
        "levels": {
            "PMH": {"status": "ACTIVE", "price": 52570.0, "stack_group": "HIGH 1"},
            "PML": {"status": "ACTIVE", "price": 52461.0, "stack_group": "LOW 1"},
            "LH": {"status": "ACTIVE", "price": 52586.0, "stack_group": "HIGH 1"},
            "LL": {"status": "ACTIVE", "price": 52478.0, "stack_group": "NONE"},
            "ONH": {"status": "ACTIVE", "price": 52625.0, "stack_group": "HIGH 1"},
            "ONL": {"status": "ACTIVE", "price": 52427.0, "stack_group": "LOW 1"},
            "YH": {"status": "ACTIVE", "price": 52763.0, "stack_group": "NONE"},
            "YL": {"status": "ACTIVE", "price": 52383.0, "stack_group": "LOW 1"},
        },
    }
    liquidity = {
        "nearest_level_above": {"name": None, "price": None},
        "nearest_level_below": {"name": "YH", "price": 52763.0},
        "tick_size": 1.0,
    }

    def snapshot(latest: dict) -> dict:
        return {
            "normalized_symbol": "YM",
            "requested_symbol": "YM",
            "latest_bar_time": latest["timestamp"],
            "latest_price": latest["close"],
            "ohlc": latest,
            "ohlc_is_closed": True,
            "liquidity": liquidity,
            "tv_context": tv_context,
            "atr": {"atr_1m_14": 20.0},
            "pre_open_observed_extreme": {
                "side": "upper",
                "price": 52763.0,
                "source_level": "YH",
                "stack_group": "NONE",
            },
        }

    def persist_symbol_state(current_snapshot: dict) -> dict:
        return {
            "normalized_symbol": "YM",
            "pre_open_observed_extreme": current_snapshot["pre_open_observed_extreme"],
            "step_2_1a": current_snapshot["step_2_1a"],
            "step25": current_snapshot["step25"],
            "step3": current_snapshot["step3"],
            "step4": current_snapshot["step4"],
            "step5": current_snapshot["step5"],
            "step6": current_snapshot["step6"],
            "step2_locked_owner": current_snapshot["step_2_1a"].get("step2_locked_owner"),
            "last_interacted_liquidity": current_snapshot["step_2_1a"].get("last_interacted_liquidity"),
            "step_2_1a_last_evaluated_bar_time": current_snapshot["step_2_1a"].get("last_evaluated_bar_time"),
            "step_2_1a_candle_index": current_snapshot["step_2_1a"].get("next_candle_index"),
            "rejection_lane": current_snapshot.get("rejection_lane"),
            "continuation_lane": current_snapshot.get("continuation_lane"),
            "trade_state": current_snapshot.get("trade_state"),
            "market_state": current_snapshot.get("market_state"),
        }

    original_recent_closed_bars = evaluate_live_step_2_1a.__globals__["recent_closed_bars"]
    try:
        persisted: dict = {"state_by_symbol": {"YM": {"pre_open_observed_extreme": snapshot(bars[0])["pre_open_observed_extreme"]}}}
        continuation_step4_by_time: dict[str, dict[str, object]] = {}
        continuation_lane_by_time: dict[str, dict[str, object]] = {}

        for index, current in enumerate(bars):
            evaluate_live_step_2_1a.__globals__["recent_closed_bars"] = lambda symbol, limit, _bars=bars[: index + 1]: _bars[-limit:]
            current_snapshot = snapshot(current)
            symbol_persisted = (
                persisted.get("state_by_symbol", {}).get("YM", {})
                if isinstance(persisted.get("state_by_symbol"), dict)
                else {}
            )
            step2 = evaluate_live_step_2_1a(current_snapshot, {}, liquidity, persisted)
            rejection = rejection_from_step2_activation(step2, "YM")
            step25 = evaluate_live_step25(current_snapshot, rejection, step2, symbol_persisted)
            step3 = evaluate_live_step3(current_snapshot, rejection, step25, step2, symbol_persisted)
            step4 = evaluate_live_step4(current_snapshot, rejection, step25, step3, symbol_persisted)
            step5 = evaluate_live_step5(current_snapshot, step4, symbol_persisted)
            step6 = evaluate_live_step6(current_snapshot, step5, symbol_persisted)
            current_snapshot.update(
                {
                    "step_2_1a": step2,
                    "rejection": rejection,
                    "step25": step25,
                    "step3": step3,
                    "step4": step4,
                    "step5": step5,
                    "step6": step6,
                }
            )
            current_snapshot = apply_confirmed_lifecycle_invariants(current_snapshot, symbol_persisted)
            current_snapshot["rejection_lane"], current_snapshot["continuation_lane"] = entry_agent.snapshot_lane_statuses(current_snapshot, symbol_persisted)
            if current["timestamp"] >= "2026-07-01T14:17:00Z":
                state = (current_snapshot.get("step4") or {}).get("state") or {}
                continuation_step4_by_time[current["timestamp"]] = {
                    "status": (current_snapshot.get("step4") or {}).get("status"),
                    "lane_id": state.get("lane_id"),
                    "leg1_window_started_at": state.get("leg1_window_started_at"),
                    "leg1_window_candle_index": state.get("leg1_window_candle_index"),
                    "leg1_completed_at": state.get("leg1_completed_at"),
                    "step4_confirmed_at": state.get("step4_confirmed_at"),
                    "step5_close_boundary": state.get("step5_close_boundary"),
                    "leg2_sweep_extreme": state.get("leg2_sweep_extreme"),
                    "active_liquidity": state.get("active_liquidity"),
                    "close_boundary": state.get("close_boundary"),
                    "extreme_boundary": state.get("extreme_boundary"),
                }
                continuation_lane_by_time[current["timestamp"]] = dict(current_snapshot.get("continuation_lane") or {})
            current_snapshot["trade_state"] = entry_agent.build_trade_state_snapshot(current_snapshot)
            current_snapshot["market_state"] = entry_agent.build_market_state_snapshot(current_snapshot)
            persisted = {"state_by_symbol": {"YM": persist_symbol_state(current_snapshot)}}

        assert continuation_step4_by_time["2026-07-01T14:17:00Z"] == {
            "status": "WAIT",
            "lane_id": "continuation|2026-07-01T14:17:00Z|YH|LONG|52763.0|52763.0",
            "leg1_window_started_at": "2026-07-01T14:17:00Z",
            "leg1_window_candle_index": 0,
            "leg1_completed_at": None,
            "step4_confirmed_at": None,
            "step5_close_boundary": None,
            "leg2_sweep_extreme": None,
            "active_liquidity": {"name": "YH", "price": 52763.0},
            "close_boundary": 52763.0,
            "extreme_boundary": 52763.0,
        }
        assert continuation_step4_by_time["2026-07-01T14:18:00Z"]["lane_id"] == "continuation|2026-07-01T14:17:00Z|YH|LONG|52763.0|52763.0"
        assert continuation_step4_by_time["2026-07-01T14:18:00Z"]["leg1_completed_at"] != "2026-07-01T14:15:00Z"
        assert continuation_step4_by_time["2026-07-01T14:18:00Z"]["step4_confirmed_at"] != "2026-07-01T14:15:00Z"
        assert continuation_step4_by_time["2026-07-01T14:18:00Z"]["step5_close_boundary"] != 52781.0
        assert continuation_step4_by_time["2026-07-01T14:18:00Z"]["leg2_sweep_extreme"] != 52805.0
        assert continuation_step4_by_time["2026-07-01T14:18:00Z"]["status"] == "READY"
        assert continuation_step4_by_time["2026-07-01T14:18:00Z"]["leg1_window_candle_index"] == 1
        assert continuation_step4_by_time["2026-07-01T14:18:00Z"]["active_liquidity"] == {"name": "YH", "price": 52763.0}
        assert continuation_step4_by_time["2026-07-01T14:18:00Z"]["close_boundary"] == 52763.0
        assert continuation_step4_by_time["2026-07-01T14:18:00Z"]["extreme_boundary"] == 52763.0
        assert continuation_step4_by_time["2026-07-01T14:18:00Z"]["leg1_completed_at"] == "2026-07-01T14:18:00Z"
        assert continuation_step4_by_time["2026-07-01T14:18:00Z"]["step4_confirmed_at"] == "2026-07-01T14:18:00Z"
        assert continuation_lane_by_time["2026-07-01T14:18:00Z"]["step2_status"] == "CONFIRMED"
        assert continuation_lane_by_time["2026-07-01T14:18:00Z"]["step2_confirmed_at"] == "2026-07-01T14:17:00Z"
        assert continuation_lane_by_time["2026-07-01T14:18:00Z"]["step2_candle_count"] == 1
        assert continuation_step4_by_time["2026-07-01T14:19:00Z"]["lane_id"] == "continuation|2026-07-01T14:17:00Z|YH|LONG|52763.0|52763.0"
        assert continuation_step4_by_time["2026-07-01T14:19:00Z"]["leg1_completed_at"] != "2026-07-01T14:15:00Z"
        assert continuation_step4_by_time["2026-07-01T14:19:00Z"]["step4_confirmed_at"] != "2026-07-01T14:15:00Z"
        assert continuation_step4_by_time["2026-07-01T14:19:00Z"]["step5_close_boundary"] != 52781.0
        assert continuation_step4_by_time["2026-07-01T14:19:00Z"]["leg2_sweep_extreme"] != 52805.0
        assert continuation_step4_by_time["2026-07-01T14:19:00Z"]["status"] == "READY"
        assert continuation_step4_by_time["2026-07-01T14:19:00Z"]["leg1_window_candle_index"] == 1
        assert continuation_step4_by_time["2026-07-01T14:19:00Z"]["active_liquidity"] == {"name": "YH", "price": 52763.0}
        assert continuation_step4_by_time["2026-07-01T14:19:00Z"]["close_boundary"] == 52763.0
        assert continuation_step4_by_time["2026-07-01T14:19:00Z"]["extreme_boundary"] == 52763.0
        assert continuation_step4_by_time["2026-07-01T14:19:00Z"]["step5_close_boundary"] == 52726.0
        assert continuation_step4_by_time["2026-07-01T14:19:00Z"]["leg2_sweep_extreme"] == 52718.0
        assert continuation_lane_by_time["2026-07-01T14:19:00Z"]["step2_status"] == "CONFIRMED"
        assert continuation_lane_by_time["2026-07-01T14:19:00Z"]["step2_confirmed_at"] == "2026-07-01T14:17:00Z"
        assert continuation_lane_by_time["2026-07-01T14:19:00Z"]["step2_candle_count"] == 2
    finally:
        evaluate_live_step_2_1a.__globals__["recent_closed_bars"] = original_recent_closed_bars


def test_ym_2026_07_01_public_lane_projection_preserves_frozen_lifecycles() -> None:
    import entry_agent

    bars = [
        candle(52737.0, 52776.0, 52733.0, 52772.0, "2026-07-01T14:13:00Z"),
        candle(52770.0, 52802.0, 52760.0, 52794.0, "2026-07-01T14:14:00Z"),
        candle(52794.0, 52805.0, 52781.0, 52781.0, "2026-07-01T14:15:00Z"),
        candle(52781.0, 52800.0, 52764.0, 52766.0, "2026-07-01T14:16:00Z"),
        candle(52768.0, 52770.0, 52737.0, 52739.0, "2026-07-01T14:17:00Z"),
        candle(52739.0, 52741.0, 52718.0, 52726.0, "2026-07-01T14:18:00Z"),
        candle(52730.0, 52754.0, 52725.0, 52752.0, "2026-07-01T14:19:00Z"),
    ]
    tv_context = {
        "daily_atr14": 712.0,
        "levels": {
            "PMH": {"status": "ACTIVE", "price": 52570.0, "stack_group": "HIGH 1"},
            "PML": {"status": "ACTIVE", "price": 52461.0, "stack_group": "LOW 1"},
            "LH": {"status": "ACTIVE", "price": 52586.0, "stack_group": "HIGH 1"},
            "LL": {"status": "ACTIVE", "price": 52478.0, "stack_group": "NONE"},
            "ONH": {"status": "ACTIVE", "price": 52625.0, "stack_group": "HIGH 1"},
            "ONL": {"status": "ACTIVE", "price": 52427.0, "stack_group": "LOW 1"},
            "YH": {"status": "ACTIVE", "price": 52763.0, "stack_group": "NONE"},
            "YL": {"status": "ACTIVE", "price": 52383.0, "stack_group": "LOW 1"},
        },
    }
    liquidity = {
        "nearest_level_above": {"name": None, "price": None},
        "nearest_level_below": {"name": "YH", "price": 52763.0},
        "tick_size": 1.0,
    }

    def snapshot(latest: dict) -> dict:
        return {
            "normalized_symbol": "YM",
            "requested_symbol": "YM",
            "latest_bar_time": latest["timestamp"],
            "latest_price": latest["close"],
            "ohlc": latest,
            "ohlc_is_closed": True,
            "liquidity": liquidity,
            "tv_context": tv_context,
            "atr": {"atr_1m_14": 20.0},
            "pre_open_observed_extreme": {
                "side": "upper",
                "price": 52763.0,
                "source_level": "YH",
                "stack_group": "NONE",
            },
        }

    def persist_symbol_state(current_snapshot: dict) -> dict:
        return {
            "normalized_symbol": "YM",
            "pre_open_observed_extreme": current_snapshot["pre_open_observed_extreme"],
            "step_2_1a": current_snapshot["step_2_1a"],
            "step25": current_snapshot["step25"],
            "step3": current_snapshot["step3"],
            "step4": current_snapshot["step4"],
            "step5": current_snapshot["step5"],
            "step6": current_snapshot["step6"],
            "step2_locked_owner": current_snapshot["step_2_1a"].get("step2_locked_owner"),
            "last_interacted_liquidity": current_snapshot["step_2_1a"].get("last_interacted_liquidity"),
            "step_2_1a_last_evaluated_bar_time": current_snapshot["step_2_1a"].get("last_evaluated_bar_time"),
            "step_2_1a_candle_index": current_snapshot["step_2_1a"].get("next_candle_index"),
            "rejection_lane": current_snapshot.get("rejection_lane"),
            "continuation_lane": current_snapshot.get("continuation_lane"),
            "trade_state": current_snapshot.get("trade_state"),
            "market_state": current_snapshot.get("market_state"),
        }

    original_recent_closed_bars = evaluate_live_step_2_1a.__globals__["recent_closed_bars"]
    original_run_once = entry_agent.run_once
    original_load_entry_state = entry_agent.load_entry_state
    try:
        persisted: dict = {"state_by_symbol": {"YM": {"pre_open_observed_extreme": snapshot(bars[0])["pre_open_observed_extreme"]}}}
        public_statuses: list[dict[str, object]] = []

        for index, current in enumerate(bars):
            evaluate_live_step_2_1a.__globals__["recent_closed_bars"] = lambda symbol, limit, _bars=bars[: index + 1]: _bars[-limit:]
            current_snapshot = snapshot(current)
            symbol_persisted = (
                persisted.get("state_by_symbol", {}).get("YM", {})
                if isinstance(persisted.get("state_by_symbol"), dict)
                else {}
            )
            step2 = evaluate_live_step_2_1a(current_snapshot, {}, liquidity, persisted)
            rejection = rejection_from_step2_activation(step2, "YM")
            step25 = evaluate_live_step25(current_snapshot, rejection, step2, symbol_persisted)
            step3 = evaluate_live_step3(current_snapshot, rejection, step25, step2, symbol_persisted)
            step4 = evaluate_live_step4(current_snapshot, rejection, step25, step3, symbol_persisted)
            step5 = evaluate_live_step5(current_snapshot, step4, symbol_persisted)
            step6 = evaluate_live_step6(current_snapshot, step5, symbol_persisted)
            current_snapshot.update(
                {
                    "step_2_1a": step2,
                    "rejection": rejection,
                    "step25": step25,
                    "step3": step3,
                    "step4": step4,
                    "step5": step5,
                    "step6": step6,
                }
            )
            current_snapshot = apply_confirmed_lifecycle_invariants(current_snapshot, symbol_persisted)
            current_snapshot["rejection_lane"], current_snapshot["continuation_lane"] = entry_agent.snapshot_lane_statuses(current_snapshot, symbol_persisted)
            current_snapshot["trade_state"] = entry_agent.build_trade_state_snapshot(current_snapshot)
            current_snapshot["market_state"] = entry_agent.build_market_state_snapshot(current_snapshot)
            persisted = {"state_by_symbol": {"YM": persist_symbol_state(current_snapshot)}}
            entry_agent.run_once = lambda symbol="YM", persist=False, _snapshot=current_snapshot: _snapshot
            entry_agent.load_entry_state = lambda _persisted=persisted: _persisted
            public_statuses.append(build_entry_status("YM"))

        statuses_by_time = {str(status.get("candle_time")): status for status in public_statuses}
        for candle_time in ("2026-07-01T14:17:00Z", "2026-07-01T14:18:00Z", "2026-07-01T14:19:00Z"):
            status = statuses_by_time[candle_time]
            rejection_lane = status["rejection_lane"] or {}
            continuation_lane = status["continuation_lane"] or {}

            assert rejection_lane.get("active_liquidity_name") == "YH"
            assert rejection_lane.get("close_boundary") == 52763.0
            assert rejection_lane.get("extreme_boundary") == 52763.0
            assert rejection_lane.get("step2_status") == "CONFIRMED"
            assert rejection_lane.get("step2_confirmed_at") == "2026-07-01T14:13:00Z"
            assert rejection_lane.get("step2_candle_count") == 2
            assert rejection_lane.get("step4_status") == "CONFIRMED"
            assert rejection_lane.get("step4_confirmed_at") == "2026-07-01T14:15:00Z"
            assert rejection_lane.get("step5_close_boundary") == 52794.0
            assert rejection_lane.get("leg2_sweep_extreme") == 52805.0

            assert continuation_lane.get("active_liquidity_name") == "YH"
            assert continuation_lane.get("close_boundary") == 52763.0
            assert continuation_lane.get("extreme_boundary") == 52763.0
            assert continuation_lane.get("step2_status") == "CONFIRMED"
            assert continuation_lane.get("step2_confirmed_at") == "2026-07-01T14:17:00Z"

            market_state = status["market_state"] or {}
            assert market_state.get("active_liquidity_name") is not None
            if candle_time == "2026-07-01T14:18:00Z":
                assert market_state.get("active_liquidity_name") == "YH"
                assert market_state.get("close_boundary") == 52763.0
                assert market_state.get("extreme_boundary") == 52763.0

        assert (statuses_by_time["2026-07-01T14:17:00Z"]["continuation_lane"] or {}).get("step2_candle_count") == 0
        assert (statuses_by_time["2026-07-01T14:18:00Z"]["continuation_lane"] or {}).get("step2_candle_count") == 1
        assert (statuses_by_time["2026-07-01T14:19:00Z"]["continuation_lane"] or {}).get("step2_candle_count") == 2
        assert (statuses_by_time["2026-07-01T14:17:00Z"]["continuation_lane"] or {}).get("step4_status") == "WAIT"
        assert (statuses_by_time["2026-07-01T14:18:00Z"]["continuation_lane"] or {}).get("step4_status") == "CONFIRMED"
        assert (statuses_by_time["2026-07-01T14:19:00Z"]["continuation_lane"] or {}).get("step4_status") == "CONFIRMED"
        assert (statuses_by_time["2026-07-01T14:17:00Z"]["continuation_lane"] or {}).get("step5_close_boundary") is None
        assert (statuses_by_time["2026-07-01T14:18:00Z"]["continuation_lane"] or {}).get("step5_close_boundary") == 52726.0
        assert (statuses_by_time["2026-07-01T14:19:00Z"]["continuation_lane"] or {}).get("step5_close_boundary") == 52726.0
        assert (statuses_by_time["2026-07-01T14:17:00Z"]["continuation_lane"] or {}).get("leg2_sweep_extreme") is None
        assert (statuses_by_time["2026-07-01T14:18:00Z"]["continuation_lane"] or {}).get("leg2_sweep_extreme") == 52718.0
        assert (statuses_by_time["2026-07-01T14:19:00Z"]["continuation_lane"] or {}).get("leg2_sweep_extreme") == 52718.0
        assert statuses_by_time["2026-07-01T14:17:00Z"]["current_pathway_control"] == "continuation"
        assert statuses_by_time["2026-07-01T14:18:00Z"]["current_pathway_control"] == "continuation"
        assert statuses_by_time["2026-07-01T14:19:00Z"]["current_pathway_control"] == "continuation"
    finally:
        evaluate_live_step_2_1a.__globals__["recent_closed_bars"] = original_recent_closed_bars
        entry_agent.run_once = original_run_once
        entry_agent.load_entry_state = original_load_entry_state


def test_sanitize_preserves_current_day_step2_owner_with_old_consumed_history() -> None:
    import entry_agent

    owner_candle = candle(30360.0, 30375.0, 30358.0, 30373.0, "2026-05-29T13:33:00Z")
    owner = {
        "pathway": "rejection",
        "active_liquidity": {
            "name": "ONH",
            "price": 30372.25,
            "display_name": "PMH/ONH/LH Liquidity",
            "side": "upper",
            "group": {
                "name": "HIGH 1",
                "components": ["ONH", "LH", "PMH"],
                "close_boundary": 30363.75,
                "extreme_boundary": 30372.25,
            },
        },
        "active_liquidity_name": "ONH",
        "active_liquidity_price": 30372.25,
        "liquidity_group": "HIGH 1",
        "setup_direction": "SHORT",
        "side": "upper",
        "candle_a": owner_candle,
        "activated_at": "2026-05-29T13:33:00Z",
    }
    old_history = {
        "key": "PML:29171.75",
        "name": "PML",
        "price": 29171.75,
        "exhausted_at_candle_time": "2026-05-18T14:33:00Z",
        "reason": "Historical consumed-liquidity record must not stale active state.",
    }
    symbol_state = {
        "normalized_symbol": "NQ",
        "latest_bar_time": "2026-05-29T13:34:00Z",
        "step_2_1a": {
            "step_2_activated": True,
            "candle_a": owner_candle,
            "active_level": "ONH",
            "level_price": 30372.25,
            "side": "upper",
            "pre_activation_probe_boundary": {"active": False, "side": "upper"},
            "step2_locked_owner": owner,
            "consumed_liquidity_levels": [old_history],
        },
        "step2_locked_owner": owner,
        "step25": {
            "status": "READY",
            "state": {
                "step25_pathway_selection_complete": True,
                "controlling_mode": "Normal Rejection Mode",
                "initial_candle_a": owner_candle,
                "active_liquidity": {"name": "ONH", "price": 30372.25},
                "consumed_liquidity_levels": [old_history],
            },
        },
        "step4": {
            "status": "WAIT",
            "state": {
                "initial_candle_a": owner_candle,
                "active_liquidity": {"name": "ONH", "price": 30372.25},
                "leg1_window_active": True,
                "leg1_window_started_at": "2026-05-29T13:33:00Z",
                "leg1_window_candle_index": 1,
                "leg1_window_remaining": 3,
                "leg1_window_expires_at": "2026-05-29T13:37:00Z",
                "consumed_liquidity_levels": [old_history],
            },
        },
        "consumed_liquidity_levels": [old_history],
    }
    persisted = {"state_by_symbol": {"NQ": symbol_state}}

    sanitized = entry_agent.sanitize_stale_session_state(persisted, "NQ", "2026-05-29")
    sanitized_nq = sanitized["state_by_symbol"]["NQ"]

    assert sanitized_nq["step2_locked_owner"]["activated_at"] == "2026-05-29T13:33:00Z"
    assert sanitized_nq["step_2_1a"]["candle_a"]["timestamp"] == "2026-05-29T13:33:00Z"
    assert sanitized_nq["step25"]["state"]["initial_candle_a"]["timestamp"] == "2026-05-29T13:33:00Z"
    assert sanitized_nq["step4"]["state"]["leg1_window_started_at"] == "2026-05-29T13:33:00Z"
    assert sanitized_nq["step4"]["state"]["leg1_window_candle_index"] == 1
    assert sanitized_nq["consumed_liquidity_levels"][0]["exhausted_at_candle_time"] == "2026-05-18T14:33:00Z"


def test_same_side_upper_progression_consumes_crossed_stack_components() -> None:
    previous_group = {
        "name": "HIGH 1",
        "components": ["PMH", "ONH"],
        "prices": {"PMH": 52282.0, "ONH": 52282.0},
        "side": "upper",
        "display_name": "PMH/ONH Liquidity",
        "close_boundary": 52282.0,
        "extreme_boundary": 52282.0,
    }
    persisted_state = {
        "state_by_symbol": {
            "YM": {
                "last_interacted_liquidity": {
                    "name": "ONH",
                    "price": 52282.0,
                    "display_name": "PMH/ONH Liquidity",
                    "side": "upper",
                    "group": previous_group,
                },
                "step4": {"status": "WAIT", "state": {}},
                "consumed_liquidity_levels": [],
            }
        }
    }
    snapshot = {
        "normalized_symbol": "YM",
        "latest_bar_time": "2026-06-16T13:31:00Z",
        "latest_price": 52390.0,
        "ohlc_is_closed": True,
        "ohlc": {"open": 52310.0, "high": 52395.0, "low": 52305.0, "close": 52390.0},
        "tv_context": {
            "levels": {
                "PMH": {"price": 52282.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "ONH": {"price": 52282.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "YH": {"price": 52380.0, "status": "ACTIVE", "stack_group": "NONE"},
                "PML": {"price": 52164.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "ONL": {"price": 52080.0, "status": "ACTIVE", "stack_group": "NONE"},
                "YL": {"price": 52087.0, "status": "ACTIVE", "stack_group": "NONE"},
                "LL": {"price": 52135.0, "status": "ACTIVE", "stack_group": "LOW 1"},
            }
        },
    }

    result = evaluate_live_step_2_1a(snapshot, {}, {"tick_size": 1.0}, persisted_state)

    assert result["active_level"] == "YH"
    consumed = {
        (record.get("name"), record.get("price"))
        for record in result["consumed_liquidity_levels"]
    }
    assert ("PMH", 52282.0) in consumed
    assert ("ONH", 52282.0) in consumed
    assert ("PML", 52164.0) not in consumed
    assert ("ONL", 52080.0) not in consumed
    assert ("YL", 52087.0) not in consumed
    assert ("LL", 52135.0) not in consumed


def test_consumed_upper_liquidity_cannot_regain_ownership_after_reset() -> None:
    consumed_levels = [
        {
            "key": "PMH:52282.0",
            "name": "PMH",
            "price": 52282.0,
            "side": "upper",
            "exhaustion_type": "same_side_next_liquidity_reached",
            "exhausted_by": "YH",
            "exhausted_by_price": 52380.0,
            "exhausted_at_candle_time": "2026-06-16T13:31:00Z",
        },
        {
            "key": "ONH:52282.0",
            "name": "ONH",
            "price": 52282.0,
            "side": "upper",
            "exhaustion_type": "same_side_next_liquidity_reached",
            "exhausted_by": "YH",
            "exhausted_by_price": 52380.0,
            "exhausted_at_candle_time": "2026-06-16T13:31:00Z",
        },
        {
            "key": "YH:52380.0",
            "name": "YH",
            "price": 52380.0,
            "invalidated_at": "2026-06-16T13:55:30Z",
            "invalidation_source_candle_time": "2026-06-16T13:55:00Z",
            "reason": "Anchor Extreme close invalidation occurred before Step 6 entry.",
        },
    ]
    persisted_state = {
        "state_by_symbol": {
            "YM": {
                "last_interacted_liquidity": {"name": "YH", "price": 52380.0, "side": "upper"},
                "step4": {"status": "WAIT", "state": {}},
                "step5": {
                    "status": "WAIT",
                    "state": {
                        "invalidated_at": "2026-06-16T13:55:30Z",
                        "invalidated_liquidity": consumed_levels[-1],
                        "invalidation_source": "anchor_extreme_close",
                        "active_liquidity": None,
                    },
                },
                "consumed_liquidity_levels": consumed_levels,
            }
        }
    }
    snapshot = {
        "normalized_symbol": "YM",
        "latest_bar_time": "2026-06-16T13:56:00Z",
        "latest_price": 52343.0,
        "ohlc_is_closed": True,
        "ohlc": {"open": 52360.0, "high": 52365.0, "low": 52340.0, "close": 52343.0},
        "tv_context": {
            "levels": {
                "PMH": {"price": 52282.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "ONH": {"price": 52282.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "YH": {"price": 52380.0, "status": "ACTIVE", "stack_group": "NONE"},
                "PML": {"price": 52164.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "ONL": {"price": 52080.0, "status": "ACTIVE", "stack_group": "NONE"},
                "YL": {"price": 52087.0, "status": "ACTIVE", "stack_group": "NONE"},
                "LL": {"price": 52135.0, "status": "ACTIVE", "stack_group": "LOW 1"},
            }
        },
    }

    result = evaluate_live_step_2_1a(snapshot, {}, {"tick_size": 1.0}, persisted_state)

    assert result["available"] is False
    assert result["active_level"] is None


def test_consumed_upper_progression_does_not_block_lower_side_eligibility() -> None:
    consumed_levels = [
        {
            "key": "PMH:52282.0",
            "name": "PMH",
            "price": 52282.0,
            "side": "upper",
            "exhaustion_type": "same_side_next_liquidity_reached",
            "exhausted_by": "YH",
            "exhausted_by_price": 52380.0,
            "exhausted_at_candle_time": "2026-06-16T13:31:00Z",
        },
        {
            "key": "ONH:52282.0",
            "name": "ONH",
            "price": 52282.0,
            "side": "upper",
            "exhaustion_type": "same_side_next_liquidity_reached",
            "exhausted_by": "YH",
            "exhausted_by_price": 52380.0,
            "exhausted_at_candle_time": "2026-06-16T13:31:00Z",
        },
    ]
    persisted_state = {
        "state_by_symbol": {
            "YM": {
                "last_interacted_liquidity": {"name": "YH", "price": 52380.0, "side": "upper"},
                "step4": {"status": "WAIT", "state": {}},
                "consumed_liquidity_levels": consumed_levels,
            }
        }
    }
    snapshot = {
        "normalized_symbol": "YM",
        "latest_bar_time": "2026-06-16T14:02:00Z",
        "latest_price": 52070.0,
        "ohlc_is_closed": True,
        "ohlc": {"open": 52110.0, "high": 52115.0, "low": 52065.0, "close": 52070.0},
        "tv_context": {
            "levels": {
                "PMH": {"price": 52282.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "ONH": {"price": 52282.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "YH": {"price": 52380.0, "status": "ACTIVE", "stack_group": "NONE"},
                "PML": {"price": 52164.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "ONL": {"price": 52080.0, "status": "ACTIVE", "stack_group": "NONE"},
                "YL": {"price": 52000.0, "status": "ACTIVE", "stack_group": "NONE"},
                "LL": {"price": 52135.0, "status": "ACTIVE", "stack_group": "LOW 1"},
            }
        },
    }

    result = evaluate_live_step_2_1a(snapshot, {}, {"tick_size": 1.0}, persisted_state)

    assert result["active_level"] == "ONL"
    assert result["level_price"] == 52080.0


def test_proximity_hard_bypass_routes_step7() -> None:
    interaction = base_interaction("SHORT")
    interaction["nearest_opposing_liquidity"] = {"name": "PML", "price": 100.8}
    interaction["atr_1m_14"] = 10.0
    interaction["daily_atr14"] = 10.0
    first = step4_count1_wait(interaction, failed_short_participation_candle(1))
    result = evaluate_step4(first, candle(100.5, 100.75, 99.0, 100.75))
    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert "proximity filter hard bypass" in result["reason"]


def run_tests() -> None:
    tests = [
        test_close_based_participation_passes_and_assigns_leg1,
        test_participation_on_candle_1_is_valid,
        test_participation_on_candle_2_is_valid,
        test_participation_on_candle_3_is_valid,
        test_participation_on_candle_4_is_valid,
        test_no_participation_by_candle_4_sets_gateway_without_leg1,
        test_failed_participation_wait_does_not_proceed_to_step5,
        test_failed_participation_clears_stale_leg1_lock_fields,
        test_live_step4_uses_current_candle_not_prior_failed_candle_b,
        test_step3_blocked_does_not_build_leg1,
        test_step25_incomplete_does_not_build_leg1,
        test_sr_close_based_reclaim_candle_becomes_candle_a,
        test_rs_close_based_reclaim_candle_becomes_candle_a,
        test_sr_wrong_side_structure_blocks,
        test_sr_provisional_leg1_does_not_require_close_back_above_stack_extreme,
        test_rs_wrong_side_structure_blocks,
        test_wick_based_participation_passes_when_close_fails,
        test_certified_short_wick_33_fails_and_34_passes_with_close_disqualified,
        test_certified_long_wick_33_fails_and_34_passes_with_close_disqualified,
        test_certified_equal_close_fails_and_beyond_extreme_close_passes,
        test_both_participation_paths_fail_routes_step7,
        test_long_assigns_low_extreme,
        test_step2_step4_50_line_touch_invalidates_before_leg1_participation,
        test_nq_2026_06_12_step2_step4_50_line_touch_invalidates_rejection,
        test_short_step2_step4_50_line_touch_uses_candle_high,
        test_step2_step4_50_line_touch_invalidates_when_candle_a_already_crossed_line_long,
        test_step2_step4_50_line_touch_invalidates_when_candle_a_already_crossed_line_short,
        test_upper_static_stack_rejects_close_boundary_only_leg1,
        test_lower_static_stack_rejects_close_boundary_only_leg1,
        test_live_static_stack_keeps_step2_activation_as_candle_a_until_explicit_replacement,
        test_nq_2026_06_18_stacked_rs_reclaim_uses_existing_stack_confirmation_for_step4,
        test_ym_2026_05_28_failed_c1_keeps_rejection_window_for_c2_wick,
        test_ym_2026_05_29_same_pml_close_through_does_not_recreate_step2_window,
        test_nq_2026_05_29_stack_step2_owner_survives_repeated_close_through,
        test_sanitize_preserves_current_day_step2_owner_with_old_consumed_history,
        test_same_side_upper_progression_consumes_crossed_stack_components,
        test_consumed_upper_liquidity_cannot_regain_ownership_after_reset,
        test_consumed_upper_progression_does_not_block_lower_side_eligibility,
        test_proximity_hard_bypass_routes_step7,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} Step 4 replay tests passed")


if __name__ == "__main__":
    run_tests()
