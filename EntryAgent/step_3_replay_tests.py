"""Focused replay tests for Step 3 only."""

from __future__ import annotations

from step3_engine import evaluate_step3


def candle(open_price: float, high: float, low: float, close: float) -> dict:
    return {"open": open_price, "high": high, "low": low, "close": close}


def base_interaction() -> dict:
    return {
        "system_state": "REJECTION MODE ON",
        "trade_mode": "ON",
        "rejection_mode": "ON",
        "interaction_state": "ACTIVE",
        "active_liquidity": {"name": "PMH", "price": 100.0},
        "tick_size": 0.25,
        "events": [],
    }


def assert_result(name: str, result: dict, status: str, next_step: str, event_name: str) -> None:
    assert result["status"] == status, f"{name}: {result}"
    assert result["next_step"] == next_step, f"{name}: {result}"
    assert result["reason"], f"{name}: missing reason"
    assert any(event["event"] == event_name for event in result["events"]), f"{name}: {result['events']}"


def test_normal_level_allows_step4() -> None:
    result = evaluate_step3(base_interaction())
    assert_result("normal level", result, "ALLOW_STEP_4", "Step 4", "step3_structure_allowed")
    assert result["state"]["liquidity_type"] == "NORMAL_LEVEL"
    assert result["state"]["step3_allows_structure"] is True
    assert result["state"]["step3_block_reason"] is None


def test_static_stack_waits_for_extreme_confirmation() -> None:
    interaction = base_interaction()
    interaction.update(
        {
            "active_stack": {"name": "PMH_ONH_STACK"},
            "extreme_boundary": 101.0,
            "stack_side": "upper",
            "latest_candle": candle(99.5, 100.5, 99.25, 100.0),
        }
    )
    result = evaluate_step3(interaction)
    assert_result("stack wait", result, "WAIT", "Step 3", "step3_structure_blocked")
    assert result["state"]["step3_allows_structure"] is False
    assert result["state"]["step3_block_reason"]


def test_upper_static_stack_allows_step4_after_hh_beyond_extreme() -> None:
    interaction = base_interaction()
    interaction.update(
        {
            "active_stack": {"name": "PMH_ONH_STACK"},
            "extreme_boundary": 101.0,
            "stack_side": "upper",
            "latest_candle": candle(100.0, 101.25, 99.75, 100.5),
        }
    )
    result = evaluate_step3(interaction)
    assert_result("stack confirmed", result, "ALLOW_STEP_4", "Step 4", "step3_structure_allowed")
    assert result["state"]["stack_extreme_confirmation_seen"] is True
    assert result["state"]["sweep_extreme_boundary_seen"] is True
    assert result["state"]["step3_allows_structure"] is True
    assert result["state"]["candle_a_source"] == "stack_extreme_confirmation_candle"


def test_lower_static_stack_waits_until_ll_beyond_extreme() -> None:
    interaction = base_interaction()
    interaction.update(
        {
            "active_stack": {"name": "PML_ONL_STACK"},
            "active_liquidity": {"name": "PML", "price": 99.0},
            "extreme_boundary": 98.0,
            "stack_side": "lower",
            "latest_candle": candle(99.0, 99.5, 98.0, 98.5),
        }
    )
    result = evaluate_step3(interaction)
    assert_result("lower stack wait", result, "WAIT", "Step 3", "step3_structure_blocked")
    assert result["state"]["step3_allows_structure"] is False


def test_lower_static_stack_allows_step4_after_ll_beyond_extreme() -> None:
    interaction = base_interaction()
    interaction.update(
        {
            "active_stack": {"name": "PML_ONL_STACK"},
            "active_liquidity": {"name": "PML", "price": 99.0},
            "extreme_boundary": 98.0,
            "stack_side": "lower",
            "latest_candle": candle(99.0, 99.5, 97.75, 98.5),
        }
    )
    result = evaluate_step3(interaction)
    assert_result("lower stack confirmed", result, "ALLOW_STEP_4", "Step 4", "step3_structure_allowed")
    assert result["state"]["stack_extreme_confirmation_seen"] is True


def test_rotation_filter_does_not_downgrade_stack_to_normal_structure() -> None:
    interaction = base_interaction()
    interaction.update(
        {
            "active_stack": {"name": "PMH_ONH_STACK"},
            "extreme_boundary": 101.0,
            "stack_side": "upper",
        }
    )
    recent = [
        candle(100.0, 100.5, 99.75, 100.25),
        candle(100.25, 100.5, 99.75, 100.0),
        candle(100.0, 100.5, 99.75, 100.25),
    ]
    result = evaluate_step3(interaction, recent)
    assert_result("rotation", result, "WAIT", "Step 3", "step3_structure_blocked")
    assert result["state"]["liquidity_type"] == "STATIC_STACK"
    assert result["state"]["step3_allows_structure"] is False


def test_rejection_off_routes_through_step7() -> None:
    interaction = base_interaction()
    interaction["rejection_mode"] = "OFF"
    result = evaluate_step3(interaction)
    assert result["step"] == "Step 7"
    assert_result("rejection off", result, "TERMINATED", "Step 1", "step7_interaction_terminated")
    assert result["state"]["interaction_state"] == "TERMINATED"
    assert result["state"]["pre_activation_probe_boundary"]["active"] is False


def run_tests() -> None:
    tests = [
        test_normal_level_allows_step4,
        test_static_stack_waits_for_extreme_confirmation,
        test_upper_static_stack_allows_step4_after_hh_beyond_extreme,
        test_lower_static_stack_waits_until_ll_beyond_extreme,
        test_lower_static_stack_allows_step4_after_ll_beyond_extreme,
        test_rotation_filter_does_not_downgrade_stack_to_normal_structure,
        test_rejection_off_routes_through_step7,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} Step 3 replay tests passed")


if __name__ == "__main__":
    run_tests()
