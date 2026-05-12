"""Focused replay tests for Step 4 only."""

from __future__ import annotations

from entry_agent import build_step4_interaction, evaluate_live_step4
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
    return candle(base, base + 0.4, base - 0.1, base + 0.3)


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


def test_participation_on_candle_2_is_valid() -> None:
    result = evaluate_step4(base_interaction("SHORT"), valid_short_participation_candle(1))
    assert result["status"] == "READY"
    assert result["next_step"] == "Step 5"
    assert result["state"]["leg1_status"] == "COMPLETE"
    assert result["state"]["participation_candle_number"] == 2


def test_participation_on_candle_3_is_valid() -> None:
    first = evaluate_step4(base_interaction("SHORT"), failed_short_participation_candle(1))
    assert first["status"] == "WAIT"
    assert first["next_step"] == "Step 4"
    assert "leg1_status" not in first["state"]

    second = evaluate_step4(first["state"], valid_short_participation_candle(2))
    assert second["status"] == "READY"
    assert second["next_step"] == "Step 5"
    assert second["state"]["leg1_status"] == "COMPLETE"
    assert second["state"]["participation_candle_number"] == 3


def test_participation_on_candle_4_is_valid() -> None:
    first = evaluate_step4(base_interaction("SHORT"), failed_short_participation_candle(1))
    second_wait = evaluate_step4(first["state"], failed_short_participation_candle(2))
    assert second_wait["status"] == "WAIT"
    assert second_wait["next_step"] == "Step 4"
    assert "leg1_status" not in second_wait["state"]

    third = evaluate_step4(second_wait["state"], valid_short_participation_candle(3))
    assert third["status"] == "READY"
    assert third["next_step"] == "Step 5"
    assert third["state"]["leg1_status"] == "COMPLETE"
    assert third["state"]["participation_candle_number"] == 4


def test_no_participation_by_candle_4_sets_gateway_without_leg1() -> None:
    first = evaluate_step4(base_interaction("SHORT"), failed_short_participation_candle(1))
    second = evaluate_step4(first["state"], failed_short_participation_candle(2))
    third = evaluate_step4(second["state"], failed_short_participation_candle(3))

    assert third["step"] == "Step 7"
    assert third["status"] == "TERMINATED"
    assert third["next_step"] == "Step 1"
    assert third["state"]["level_state"] == "GATEWAY"
    assert third["state"]["liquidity_state"] == "GATEWAY"
    assert third["state"]["opposite_participation"] == "NOT_PRESENT"
    assert third["state"].get("leg1_status") is None
    assert third["next_step"] != "Step 5"


def test_failed_participation_wait_does_not_proceed_to_step5() -> None:
    result = evaluate_step4(base_interaction("SHORT"), failed_short_participation_candle(1))
    assert result["status"] == "WAIT"
    assert result["next_step"] == "Step 4"
    assert "leg1_status" not in result["state"]


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
    assert result["state"]["participation_candle_number"] == 3


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
    failed_b = candle(29274.0, 29285.75, 29263.25, 29285.0, "2026-05-12T13:44:00Z")
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
        test_participation_on_candle_2_is_valid,
        test_participation_on_candle_3_is_valid,
        test_participation_on_candle_4_is_valid,
        test_no_participation_by_candle_4_sets_gateway_without_leg1,
        test_failed_participation_wait_does_not_proceed_to_step5,
        test_live_step4_uses_current_candle_not_prior_failed_candle_b,
        test_step3_blocked_does_not_build_leg1,
        test_step25_incomplete_does_not_build_leg1,
        test_sr_close_based_reclaim_candle_becomes_candle_a,
        test_rs_close_based_reclaim_candle_becomes_candle_a,
        test_sr_wrong_side_structure_blocks,
        test_sr_provisional_leg1_does_not_require_close_back_above_stack_extreme,
        test_rs_wrong_side_structure_blocks,
        test_wick_based_participation_passes_when_close_fails,
        test_both_participation_paths_fail_routes_step7,
        test_long_assigns_low_extreme,
        test_upper_static_stack_rejects_close_boundary_only_leg1,
        test_lower_static_stack_rejects_close_boundary_only_leg1,
        test_live_static_stack_assigns_post_extreme_candle_a_then_locks_leg1_on_future_b,
        test_proximity_hard_bypass_routes_step7,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} Step 4 replay tests passed")


if __name__ == "__main__":
    run_tests()
