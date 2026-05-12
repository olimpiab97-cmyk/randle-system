"""Focused replay tests for Step 2.5 pathway selection."""

from __future__ import annotations

from step25_engine import evaluate_step25, select_pathway


def candle(open_price: float, high: float, low: float, close: float) -> dict:
    return {"open": open_price, "high": high, "low": low, "close": close}


def base_interaction() -> dict:
    return {
        "system_state": "REJECTION MODE ON",
        "trade_mode": "ON",
        "rejection_mode": "ON",
        "interaction_state": "ACTIVE",
        "initial_candle_a": candle(100.0, 101.0, 99.5, 100.5),
        "events": [],
    }


def test_normal_rejection_selects_initial_candle_a() -> None:
    result = evaluate_step25(base_interaction())
    assert result["status"] == "READY"
    assert result["next_step"] == "Step 3"
    state = result["state"]
    assert state["step25_pathway_selection_complete"] is True
    assert state["controlling_mode"] == "Normal Rejection Mode"
    assert state["initial_candle_a"]["close"] == 100.5


def test_sr_close_based_selection_sets_reclaim_candle() -> None:
    interaction = base_interaction()
    interaction.update(
        {
            "candidate_modes": ["S/R"],
            "controlling_mode": "S/R",
            "pathway_activation_type": "close",
            "pathway_level": 100.0,
            "reclaim_candle_a": candle(99.0, 101.0, 98.5, 100.5),
        }
    )
    result = evaluate_step25(interaction)
    state = result["state"]
    assert result["status"] == "READY"
    assert state["controlling_mode"] == "S/R"
    assert state["structure_side_requirement"] == "ABOVE_LEVEL"
    assert state["reclaim_candle_a"]["close"] == 100.5


def test_rs_close_based_selection_sets_reclaim_candle() -> None:
    interaction = base_interaction()
    interaction.update(
        {
            "candidate_modes": ["R/S"],
            "controlling_mode": "R/S",
            "pathway_activation_type": "close",
            "pathway_level": 100.0,
            "reclaim_candle_a": candle(101.0, 101.5, 99.0, 99.5),
        }
    )
    result = evaluate_step25(interaction)
    state = result["state"]
    assert result["status"] == "READY"
    assert state["controlling_mode"] == "R/S"
    assert state["structure_side_requirement"] == "BELOW_LEVEL"
    assert state["reclaim_candle_a"]["close"] == 99.5


def test_rejection_off_waits() -> None:
    interaction = base_interaction()
    interaction["rejection_mode"] = "OFF"
    result = evaluate_step25(interaction)
    assert result["status"] == "WAIT"
    assert result["next_step"] == "Step 2"
    assert result["state"]["step25_pathway_selection_complete"] is False


def test_wick_below_ll_green_close_selects_sr() -> None:
    previous = candle(100.5, 100.75, 99.75, 100.4)
    current = candle(99.8, 100.4, 99.4, 100.1)
    result = select_pathway(current, previous, 100.0, "LL")

    assert result["status"] == "READY"
    assert result["controlling_mode"] == "S/R"
    assert result["activation_type"] == "close"
    assert result["candle_a"] == current
    assert result["provisional_candle_a"] is None
    assert result["structure_side_requirement"] == "ABOVE_LEVEL"


def test_stacked_low_sr_requires_wick_through_stack_extreme() -> None:
    previous = candle(101.0, 101.5, 99.5, 100.5)
    current = candle(99.5, 100.75, 98.75, 100.25)
    result = select_pathway(current, previous, 100.0, "LL", stack_extreme=99.0)

    assert result["status"] == "READY"
    assert result["controlling_mode"] == "S/R"
    assert result["activation_type"] == "close"
    assert result["candle_a"] == current
    assert result["structure_side_requirement"] == "ABOVE_LEVEL"


def test_stacked_low_sr_does_not_arm_from_middle_without_extreme_wick() -> None:
    previous = candle(101.0, 101.5, 99.5, 100.5)
    current = candle(99.5, 100.75, 99.25, 100.25)
    result = select_pathway(current, previous, 100.0, "LL", stack_extreme=99.0)

    assert result["status"] == "WAIT"
    assert result["controlling_mode"] is None
    assert result["candle_a"] is None


def test_stacked_low_sr_uses_extreme_not_internal_close_boundary() -> None:
    previous = candle(100.5, 100.75, 99.5, 99.4)
    current = candle(99.6, 100.25, 99.25, 99.8)
    result = select_pathway(current, previous, 100.0, "LL", stack_extreme=99.0)

    assert result["status"] == "WAIT"
    assert result["controlling_mode"] is None


def test_close_below_ll_then_close_above_selects_sr() -> None:
    previous = candle(100.2, 100.4, 99.4, 99.7)
    current = candle(99.8, 100.5, 99.6, 100.2)
    result = select_pathway(current, previous, 100.0, "LL")

    assert result["status"] == "READY"
    assert result["controlling_mode"] == "S/R"
    assert result["activation_type"] == "close"
    assert result["candle_a"] == current
    assert result["structure_side_requirement"] == "ABOVE_LEVEL"


def test_close_below_ll_then_wick_into_level_selects_sr_provisional() -> None:
    previous = candle(99.2, 99.8, 98.9, 99.4)
    current = candle(99.6, 100.0, 99.2, 99.8)
    result = select_pathway(current, previous, 100.0, "LL")

    assert result["status"] == "READY"
    assert result["controlling_mode"] == "S/R"
    assert result["activation_type"] == "wick"
    assert result["candle_a"] is None
    assert result["provisional_candle_a"] == current
    assert result["structure_side_requirement"] == "ABOVE_LEVEL"


def test_wick_above_lh_red_close_selects_rs() -> None:
    previous = candle(99.5, 100.3, 99.2, 99.7)
    current = candle(100.2, 100.6, 99.7, 99.9)
    result = select_pathway(current, previous, 100.0, "LH")

    assert result["status"] == "READY"
    assert result["controlling_mode"] == "R/S"
    assert result["activation_type"] == "close"
    assert result["candle_a"] == current
    assert result["provisional_candle_a"] is None
    assert result["structure_side_requirement"] == "BELOW_LEVEL"


def test_close_above_lh_then_close_below_selects_rs() -> None:
    previous = candle(99.8, 100.6, 99.6, 100.3)
    current = candle(100.2, 100.4, 99.4, 99.8)
    result = select_pathway(current, previous, 100.0, "LH")

    assert result["status"] == "READY"
    assert result["controlling_mode"] == "R/S"
    assert result["activation_type"] == "close"
    assert result["candle_a"] == current
    assert result["structure_side_requirement"] == "BELOW_LEVEL"


def test_close_above_lh_then_wick_into_level_selects_rs_provisional() -> None:
    previous = candle(100.8, 101.1, 100.3, 100.6)
    current = candle(100.4, 100.8, 100.1, 100.2)
    result = select_pathway(current, previous, 100.0, "LH")

    assert result["status"] == "READY"
    assert result["controlling_mode"] == "R/S"
    assert result["activation_type"] == "wick"
    assert result["candle_a"] is None
    assert result["provisional_candle_a"] == current
    assert result["structure_side_requirement"] == "BELOW_LEVEL"


def test_no_step25_condition_waits() -> None:
    previous = candle(99.8, 100.2, 99.6, 100.0)
    current = candle(100.0, 100.3, 99.8, 100.0)
    result = select_pathway(current, previous, 100.0, "LL")

    assert result == {
        "status": "WAIT",
        "controlling_mode": None,
        "activation_type": None,
        "candle_a": None,
        "provisional_candle_a": None,
        "structure_side_requirement": None,
        "continuation_uses_stack_extreme": False,
        "continuation_acceptance_required": False,
        "continuation_acceptance_threshold": None,
    }


def run_tests() -> None:
    tests = [
        test_normal_rejection_selects_initial_candle_a,
        test_sr_close_based_selection_sets_reclaim_candle,
        test_rs_close_based_selection_sets_reclaim_candle,
        test_rejection_off_waits,
        test_wick_below_ll_green_close_selects_sr,
        test_stacked_low_sr_requires_wick_through_stack_extreme,
        test_stacked_low_sr_does_not_arm_from_middle_without_extreme_wick,
        test_stacked_low_sr_uses_extreme_not_internal_close_boundary,
        test_close_below_ll_then_close_above_selects_sr,
        test_close_below_ll_then_wick_into_level_selects_sr_provisional,
        test_wick_above_lh_red_close_selects_rs,
        test_close_above_lh_then_close_below_selects_rs,
        test_close_above_lh_then_wick_into_level_selects_rs_provisional,
        test_no_step25_condition_waits,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} Step 2.5 replay tests passed")


if __name__ == "__main__":
    run_tests()
