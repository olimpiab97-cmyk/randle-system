"""Focused replay tests for Step 5 only."""

from __future__ import annotations

from step5_engine import apply_candle_b_reference_upgrade, evaluate_step5


def candle(open_price: float, high: float, low: float, close: float, **extra) -> dict:
    payload = {"open": open_price, "high": high, "low": low, "close": close}
    payload.update(extra)
    return payload


def base_interaction(direction: str = "SHORT", owner: str = "Candle A") -> dict:
    return {
        "system_state": "REJECTION MODE ON",
        "trade_mode": "ON",
        "rejection_mode": "ON",
        "interaction_state": "ACTIVE",
        "setup_direction": direction,
        "leg1_status": "VALID",
        "leg1_reference": 100.0,
        "leg1_extreme": 101.0 if direction == "SHORT" else 99.0,
        "leg1_extreme_owner": owner,
        "anchor_extreme": 95.0 if direction == "SHORT" else 105.0,
        "nearest_opposing_liquidity": {"price": 105.0 if direction == "SHORT" else 95.0},
        "atr_1m_14": 10.0,
        "tick_size": 0.25,
        "events": [],
    }


def candle_b_reference_upgrade_interaction(direction: str = "SHORT") -> dict:
    interaction = base_interaction(direction=direction, owner="Candle A")
    if direction == "SHORT":
        interaction.update({
            "tick_size": 1.0,
            "leg1_reference": 50093.0,
            "leg1_extreme": 50109.0,
            "anchor_extreme": 50080.0,
            "nearest_opposing_liquidity": {"price": 50150.0},
            "atr_1m_14": 100.0,
            "candle_a": candle(50090.0, 50109.0, 50088.0, 50093.0),
            "candle_b": candle(50092.0, 50106.0, 50091.0, 50094.0),
        })
    else:
        interaction.update({
            "tick_size": 1.0,
            "leg1_reference": 50093.0,
            "leg1_extreme": 50077.0,
            "anchor_extreme": 50120.0,
            "nearest_opposing_liquidity": {"price": 50020.0},
            "atr_1m_14": 100.0,
            "candle_a": candle(50096.0, 50102.0, 50077.0, 50093.0),
            "candle_b": candle(50094.0, 50099.0, 50086.0, 50092.0),
        })
    return interaction


def assert_reason(result: dict) -> None:
    assert result.get("reason"), result


def participation_handoff(state: dict, candle4: dict | None = None) -> dict:
    result = state
    for item in [
        candle(100.0, 100.5, 99.5, 100.25),
        candle(100.0, 100.5, 99.5, 100.25),
        candle(100.0, 100.5, 99.5, 100.25),
        candle4 or candle(100.25, 100.5, 99.5, 99.75),
    ]:
        result = evaluate_step5(result["state"], item)
    return result


def structurally_confirmed_state() -> dict:
    result = evaluate_step5(base_interaction(), candle(100.0, 101.25, 99.75, 100.25))
    assert result["status"] == "WAIT"
    assert result["next_step"] == "Step 5"
    assert result["state"]["leg2_status"] == "CONFIRMED"
    return result


def test_standard_close_beyond_reference_and_sweep_confirms_leg2_candle_a() -> None:
    result = structurally_confirmed_state()
    assert result["state"]["active_step5_path"] == "5.1"
    assert result["state"]["step5_participation_window_active"] is True
    assert_reason(result)


def test_candle_b_reference_upgrade_uses_candle_b_close() -> None:
    state = candle_b_reference_upgrade_interaction("SHORT")
    reference = apply_candle_b_reference_upgrade(state, "SHORT")
    assert reference == 50094.0
    assert state["active_reference"] == 50094.0
    assert state["leg1_extreme"] == 50109.0
    assert state["leg1_extreme_owner"] == "Candle A"
    assert state["leg1_reference_owner"] == "Candle B"

    result = evaluate_step5(state, candle(50094.0, 50123.0, 50091.0, 50107.0))
    assert result["status"] == "WAIT"
    assert result["state"]["active_reference"] == 50094.0
    assert result["state"]["active_step5_path"] == "5.1"
    assert_reason(result)


def test_candle_b_extreme_override_requires_close_beyond_candle_b_extreme() -> None:
    fail = evaluate_step5(base_interaction(owner="Candle B"), candle(100.0, 101.5, 99.75, 101.0))
    assert fail["step"] == "Step 7"
    assert fail["status"] == "TERMINATED"

    ok = evaluate_step5(base_interaction(owner="Candle B"), candle(100.0, 101.0, 99.75, 101.25))
    assert ok["status"] == "WAIT"
    assert ok["state"]["active_step5_path"] == "5.3A"
    assert_reason(ok)


def test_wick_probe_override_requires_reference_and_probe_threshold_close() -> None:
    first = evaluate_step5(base_interaction(), candle(100.0, 101.5, 99.75, 100.0))
    assert first["status"] == "WAIT"
    assert first["state"]["wick_probe_active"] is True
    assert first["state"]["probe_high"] == 101.5

    second = evaluate_step5(first["state"], candle(100.0, 102.0, 99.75, 101.25))
    assert second["status"] == "WAIT"
    assert second["state"]["active_step5_path"] == "5.3B"
    assert second["state"]["probe_high"] == 102.0

    third = evaluate_step5(second["state"], candle(100.0, 102.25, 99.75, 102.25))
    assert third["status"] == "WAIT"
    assert third["state"]["leg2_status"] == "CONFIRMED"
    assert third["state"]["active_step5_path"] == "5.3B"
    assert_reason(third)


def test_dynamic_stack_requires_next_liquidity_boundary_sweep() -> None:
    state = base_interaction()
    state.update({"dynamic_stack_active": True, "extreme_boundary": 102.0})
    fail = evaluate_step5(state, candle(100.0, 101.25, 99.75, 100.25))
    assert fail["step"] == "Step 7"
    assert "Dynamic Stack" in fail["reason"]

    ok_state = base_interaction()
    ok_state.update({"dynamic_stack_active": True, "extreme_boundary": 102.0})
    ok = evaluate_step5(ok_state, candle(100.0, 102.25, 99.75, 100.25))
    assert ok["status"] == "WAIT"
    assert ok["state"]["leg2_status"] == "CONFIRMED"
    assert_reason(ok)


def test_candle4_participation_hands_off_to_step6() -> None:
    result = participation_handoff(structurally_confirmed_state())
    assert result["status"] == "READY"
    assert result["next_step"] == "Step 6"
    assert result["state"]["leg2_status"] == "VALIDATED"
    assert result["state"]["two_leg_structure_status"] == "COMPLETE"
    assert_reason(result)


def test_candle4_no_participation_routes_step7() -> None:
    result = participation_handoff(
        structurally_confirmed_state(),
        candle4=candle(100.0, 100.5, 99.75, 100.25),
    )
    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert_reason(result)


def test_candles_1_to_3_do_not_require_participation_if_anchor_intact() -> None:
    result = structurally_confirmed_state()
    for item in [
        candle(100.0, 100.5, 99.5, 100.25),
        candle(100.0, 100.5, 99.5, 100.25),
        candle(100.0, 100.5, 99.5, 100.25),
    ]:
        result = evaluate_step5(result["state"], item)
        assert result["status"] == "WAIT"
        assert result["next_step"] == "Step 5"
    assert result["state"]["step5_participation_candle_count"] == 3


def test_lh_hl_not_required_for_step5_validation() -> None:
    result = participation_handoff(
        structurally_confirmed_state(),
        candle4=candle(101.0, 102.0, 100.5, 100.75),
    )
    assert result["status"] == "READY"
    assert result["next_step"] == "Step 6"
    assert_reason(result)


def test_proximity_filter_failure_invalidates() -> None:
    state = base_interaction()
    state["nearest_opposing_liquidity"] = {"price": 100.4}
    result = evaluate_step5(state, candle(100.0, 101.25, 99.75, 100.25))
    assert result["step"] == "Step 7"
    assert "proximity" in result["reason"]


def test_anchor_extreme_close_violation_invalidates() -> None:
    result = evaluate_step5(base_interaction(), candle(96.0, 97.0, 94.5, 94.75))
    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert "Anchor Extreme" in result["reason"]


def test_failed_sweep_without_reference_close_can_terminate_on_opposite_liquidity_break() -> None:
    result = evaluate_step5(
        base_interaction(),
        candle(100.0, 101.5, 99.75, 100.0, opposite_liquidity_break=True),
    )
    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert result["state"]["step9_eligible"] is True
    assert_reason(result)


def test_long_reference_upgrade_without_extreme_ownership() -> None:
    state = candle_b_reference_upgrade_interaction("LONG")
    reference = apply_candle_b_reference_upgrade(state, "LONG")
    assert reference == 50092.0
    assert state["active_reference"] == 50092.0
    assert state["leg1_extreme"] == 50077.0
    assert state["leg1_extreme_owner"] == "Candle A"
    assert state["leg1_reference_owner"] == "Candle B"


def run_tests() -> None:
    tests = [
        test_standard_close_beyond_reference_and_sweep_confirms_leg2_candle_a,
        test_candle_b_reference_upgrade_uses_candle_b_close,
        test_candle_b_extreme_override_requires_close_beyond_candle_b_extreme,
        test_wick_probe_override_requires_reference_and_probe_threshold_close,
        test_dynamic_stack_requires_next_liquidity_boundary_sweep,
        test_candle4_participation_hands_off_to_step6,
        test_candle4_no_participation_routes_step7,
        test_candles_1_to_3_do_not_require_participation_if_anchor_intact,
        test_lh_hl_not_required_for_step5_validation,
        test_proximity_filter_failure_invalidates,
        test_anchor_extreme_close_violation_invalidates,
        test_failed_sweep_without_reference_close_can_terminate_on_opposite_liquidity_break,
        test_long_reference_upgrade_without_extreme_ownership,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} Step 5 replay tests passed")


if __name__ == "__main__":
    run_tests()
