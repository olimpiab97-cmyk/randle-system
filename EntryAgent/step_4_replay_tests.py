"""Focused replay tests for Step 4 only."""

from __future__ import annotations

from entry_agent import build_step4_interaction, evaluate_live_step_2_1a, evaluate_live_step4, evaluate_live_step25, rejection_from_step2_activation
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


def test_close_based_participation_passes_and_assigns_leg1() -> None:
    interaction = base_interaction("SHORT")
    result = evaluate_step4(interaction, candle(100.5, 100.75, 99.0, 100.75))
    assert result["status"] == "READY"
    assert result["next_step"] == "Step 5"
    assert_reason(result)
    state = result["state"]
    assert state["leg1_status"] == "COMPLETE"
    assert state["leg1_reference"] == 100.5
    assert state["leg1_extreme"] == 101.0
    assert state["leg1_extreme_owner"] == "Candle A"
    assert state["anchor_extreme"] == 101.0
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


def test_no_participation_by_candle_4_sets_gateway_without_leg1() -> None:
    first = evaluate_step4(base_interaction("SHORT"), failed_short_participation_candle(1))
    second = evaluate_step4(first["state"], failed_short_participation_candle(2))
    third = evaluate_step4(second["state"], failed_short_participation_candle(3))
    fourth = evaluate_step4(third["state"], failed_short_participation_candle(4))

    assert fourth["step"] == "Step 7"
    assert fourth["status"] == "TERMINATED"
    assert fourth["next_step"] == "Step 1"
    assert fourth["reason"] == "Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation."
    assert fourth["state"]["level_state"] == "GATEWAY"
    assert fourth["state"]["liquidity_state"] == "GATEWAY"
    assert fourth["state"]["opposite_participation"] == "NOT_PRESENT"
    assert fourth["state"].get("leg1_status") is None
    assert fourth["next_step"] != "Step 5"


def test_failed_participation_wait_does_not_proceed_to_step5() -> None:
    result = evaluate_step4(base_interaction("SHORT"), failed_short_participation_candle(1))
    assert result["status"] == "WAIT"
    assert result["next_step"] == "Step 4"
    assert "leg1_status" not in result["state"]


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
            "tv_context": {"atr_1m_14": 10.0},
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
    result = evaluate_step4(interaction, candle(100.5, 100.75, 100.1, 100.25))
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
    result = evaluate_step4(interaction, candle(99.5, 99.75, 98.75, 99.25))
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
    result = evaluate_step4(interaction, candle(99.8, 100.5, 99.25, 99.75))
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
    assert result["state"]["leg1_extreme_owner"] == "Candle B"


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
    fail = evaluate_step4(fail_interaction, candle(99.0, 99.67, 98.67, 99.0))
    assert fail["status"] == "WAIT"
    assert fail["next_step"] == "Step 4"
    assert fail["state"]["step3_close_participation_pass"] is False
    assert fail["state"]["step3_wick_participation_pct"] == 33.0
    assert fail["state"]["step3_wick_participation_pass"] is False

    pass_interaction = base_interaction("LONG")
    pass_interaction["nearest_opposing_liquidity"] = {"name": "PMH", "price": 105.0}
    passed = evaluate_step4(pass_interaction, candle(99.0, 99.66, 98.66, 99.0))
    assert passed["status"] == "READY"
    assert passed["next_step"] == "Step 5"
    assert passed["state"]["step3_close_participation_pass"] is False
    assert passed["state"]["step3_wick_participation_pct"] == 34.0
    assert passed["state"]["step3_wick_participation_pass"] is True
    assert passed["events"][-1]["step3_participation_rule_certification"] == "CERTIFIED"


def test_certified_equal_close_fails_and_beyond_extreme_close_passes() -> None:
    short_equal = evaluate_step4(base_interaction("SHORT"), candle(101.25, 101.25, 100.75, 101.0))
    assert short_equal["status"] == "WAIT"
    assert short_equal["state"]["step3_participation_candle_a_extreme"] == 101.0
    assert short_equal["state"]["step3_close_participation_pass"] is False
    short_beyond = evaluate_step4(base_interaction("SHORT"), candle(101.25, 101.25, 100.25, 100.75))
    assert short_beyond["status"] == "READY"
    assert short_beyond["state"]["step3_close_participation_pass"] is True

    long_equal_interaction = base_interaction("LONG")
    long_equal_interaction["nearest_opposing_liquidity"] = {"name": "PMH", "price": 105.0}
    long_equal = evaluate_step4(long_equal_interaction, candle(99.5, 100.0, 99.5, 99.5))
    assert long_equal["status"] == "WAIT"
    assert long_equal["state"]["step3_participation_candle_a_extreme"] == 99.5
    assert long_equal["state"]["step3_close_participation_pass"] is False
    long_beyond_interaction = base_interaction("LONG")
    long_beyond_interaction["nearest_opposing_liquidity"] = {"name": "PMH", "price": 105.0}
    long_beyond = evaluate_step4(long_beyond_interaction, candle(99.5, 100.0, 99.25, 99.75))
    assert long_beyond["status"] == "READY"
    assert long_beyond["state"]["step3_close_participation_pass"] is True


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
    result = evaluate_step4(interaction, candle(100.25, 101.0, 99.0, 99.75))
    assert result["status"] == "READY"
    assert result["state"]["leg1_extreme"] == 99.0
    assert result["state"]["leg1_extreme_owner"] == "Candle B"
    assert result["state"]["anchor_extreme"] == 99.0


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
    result = evaluate_step4(interaction, candle(100.5, 101.5, 100.0, 100.75))
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
    result = evaluate_step4(interaction, candle(99.5, 100.0, 98.8, 99.25))
    assert result["status"] == "WAIT"
    assert result["next_step"] == "Step 4"
    assert "leg1_status" not in result["state"]
    assert "close-boundary Leg 1 is not tradable" in result["reason"]


def test_live_static_stack_assigns_post_extreme_candle_a_then_locks_leg1_on_future_b() -> None:
    confirmation = candle(29233.0, 29265.75, 29231.25, 29262.75, "2026-05-12T13:42:00Z")
    candle_a = candle(29262.5, 29284.5, 29258.5, 29274.5, "2026-05-12T13:43:00Z")
    failed_b = candle(29285.5, 29285.75, 29284.75, 29285.0, "2026-05-12T13:44:00Z")
    valid_b = candle(29285.5, 29296.0, 29266.0, 29273.0, "2026-05-12T13:45:00Z")
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
            "active_liquidity": {"name": "PMH", "price": 29237.0},
            "active_stack": {"name": "HIGH 1"},
            "stack_side": "upper",
            "extreme_boundary": 29250.25,
            "close_boundary": 29237.0,
            "tick_size": 0.25,
            "stack_extreme_confirmation_seen": True,
            "stack_extreme_confirmation_candle": confirmation,
            "initial_candle_a": confirmation,
            "candle_a": confirmation,
        },
        "events": [],
    }
    rejection = {"watch_side": "SHORT"}
    liquidity = {"nearest_level_below": {"name": "PML", "price": 29113.0}, "tick_size": 0.25}

    def snapshot(latest: dict) -> dict:
        return {
            "latest_bar_time": latest["timestamp"],
            "ohlc": latest,
            "ohlc_is_closed": True,
            "liquidity": liquidity,
            "atr": {"atr_1m_14": 31.25827865},
        }

    first = evaluate_live_step4(snapshot(candle_a), rejection, step25, step3, {})
    assert first["status"] == "WAIT"
    assert first["next_step"] == "Step 4"
    assert first["state"]["candle_a"]["timestamp"] == "2026-05-12T13:43:00Z"
    assert first["state"]["stack_step4_candle_a_assigned"] is True

    second = evaluate_live_step4(snapshot(failed_b), rejection, step25, step3, {"step4": first})
    assert second["status"] == "WAIT"
    assert second["state"]["candle_a"]["timestamp"] == "2026-05-12T13:43:00Z"
    assert second["state"]["participation_candidate_count"] == 1
    assert second["state"].get("leg1_status") is None

    third = evaluate_live_step4(snapshot(valid_b), rejection, step25, step3, {"step4": second})
    assert third["status"] == "READY"
    assert third["next_step"] == "Step 5"
    assert third["state"]["leg1_status"] == "COMPLETE"
    assert third["state"]["candle_a"]["timestamp"] == "2026-05-12T13:43:00Z"
    assert third["state"]["candle_b"]["timestamp"] == "2026-05-12T13:45:00Z"


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


def test_proximity_hard_bypass_routes_step7() -> None:
    interaction = base_interaction("SHORT")
    interaction["nearest_opposing_liquidity"] = {"name": "PML", "price": 100.8}
    interaction["atr_1m_14"] = 10.0
    result = evaluate_step4(interaction, candle(100.5, 100.75, 99.0, 100.75))
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
        test_upper_static_stack_rejects_close_boundary_only_leg1,
        test_lower_static_stack_rejects_close_boundary_only_leg1,
        test_live_static_stack_assigns_post_extreme_candle_a_then_locks_leg1_on_future_b,
        test_ym_2026_05_28_failed_c1_keeps_rejection_window_for_c2_wick,
        test_ym_2026_05_29_same_pml_close_through_does_not_recreate_step2_window,
        test_nq_2026_05_29_stack_step2_owner_survives_repeated_close_through,
        test_sanitize_preserves_current_day_step2_owner_with_old_consumed_history,
        test_proximity_hard_bypass_routes_step7,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} Step 4 replay tests passed")


if __name__ == "__main__":
    run_tests()
