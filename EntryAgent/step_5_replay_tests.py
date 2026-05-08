"""Focused replay tests for simplified Step 5 only."""

from __future__ import annotations

from step5_engine import evaluate_step5


def candle(open_price: float, high: float, low: float, close: float, **extra) -> dict:
    payload = {"open": open_price, "high": high, "low": low, "close": close, "timestamp": extra.pop("timestamp", "t")}
    payload.update(extra)
    return payload


def base_interaction(direction: str = "SHORT") -> dict:
    if direction == "SHORT":
        candle_a = candle(99.0, 100.5, 98.5, 100.0, timestamp="a")
        anchor_extreme = 105.0
    else:
        candle_a = candle(101.0, 101.5, 99.5, 100.0, timestamp="a")
        anchor_extreme = 95.0
    return {
        "rejection_mode": "ON",
        "interaction_state": "ACTIVE",
        "setup_direction": direction,
        "leg1_status": "VALID",
        "leg1_state_locked": True,
        "leg1_completed_at": "b",
        "candle_a": candle_a,
        "leg1_reference": candle_a["close"],
        "leg1_reference_price": candle_a["close"],
        "leg1_reference_candle_time": "a",
        "leg1_extreme": anchor_extreme,
        "anchor_extreme": anchor_extreme,
        "tick_size": 0.25,
        "active_liquidity": {"name": "PMH" if direction == "SHORT" else "PML", "price": 100.0},
        "events": [],
    }


def lock_leg2(direction: str = "SHORT") -> dict:
    activation = candle(100.0, 101.0, 99.5, 100.5, timestamp="leg2a") if direction == "SHORT" else candle(100.0, 100.5, 99.0, 99.5, timestamp="leg2a")
    result = evaluate_step5(base_interaction(direction), activation)
    assert result["status"] == "WAIT"
    assert result["state"]["leg2_status"] == "CONFIRMED"
    assert result["state"]["leg2_candle_a"] == activation
    return result


def test_short_leg2_locks_and_validates_with_sweep_and_short_trigger() -> None:
    locked = lock_leg2("SHORT")
    trigger = candle(104.0, 105.5, 103.0, 103.5, timestamp="c1", valid_entry_trigger=True)

    result = evaluate_step5(locked["state"], trigger)

    assert result["status"] == "READY"
    assert result["next_step"] == "Step 6"
    assert result["state"]["leg2_status"] == "VALIDATED"
    assert result["state"]["anchor_extreme_swept"] is True
    assert result["state"]["step5_trigger_valid"] is True


def test_long_leg2_locks_and_validates_with_sweep_and_long_trigger() -> None:
    locked = lock_leg2("LONG")
    trigger = candle(96.0, 97.0, 94.5, 96.5, timestamp="c1", valid_entry_trigger=True)

    result = evaluate_step5(locked["state"], trigger)

    assert result["status"] == "READY"
    assert result["next_step"] == "Step 6"
    assert result["state"]["leg2_status"] == "VALIDATED"
    assert result["state"]["anchor_extreme_swept"] is True
    assert result["state"]["step5_trigger_valid"] is True


def test_four_candle_window_expires_without_sweep_and_trigger() -> None:
    result = lock_leg2("LONG")
    for index in range(1, 5):
        result = evaluate_step5(result["state"], candle(99.5, 100.0, 98.0, 98.5, timestamp=f"c{index}"))

    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert "4-candle window expired" in result["state"]["termination_reason"]
    assert result["state"]["interaction_state"] == "TERMINATED"


def test_short_close_above_anchor_extreme_invalidates() -> None:
    locked = lock_leg2("SHORT")
    result = evaluate_step5(locked["state"], candle(104.0, 106.0, 103.5, 105.5, timestamp="bad"))

    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert "Anchor Extreme" in result["reason"]


def test_long_close_below_anchor_extreme_invalidates() -> None:
    locked = lock_leg2("LONG")
    result = evaluate_step5(locked["state"], candle(96.0, 96.5, 94.0, 94.5, timestamp="bad"))

    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert "Anchor Extreme" in result["reason"]


def test_nq_2026_05_07_onl_sequence_qualifies_at_1021_not_1024() -> None:
    state = base_interaction("LONG")
    state.update(
        {
            "candle_a": candle(28644.75, 28649.0, 28625.0, 28629.75, timestamp="2026-05-07T10:18:00"),
            "leg1_reference": 28629.75,
            "leg1_reference_price": 28629.75,
            "anchor_extreme": 28614.0,
            "leg1_extreme": 28614.0,
            "active_liquidity": {"name": "ONL", "price": 28637.0},
        }
    )

    leg2 = evaluate_step5(state, candle(28627.25, 28627.75, 28611.5, 28615.5, timestamp="2026-05-07T10:20:00"))
    assert leg2["state"]["leg2_status"] == "CONFIRMED"

    entry = evaluate_step5(
        leg2["state"],
        candle(28616.25, 28630.75, 28613.75, 28629.5, timestamp="2026-05-07T10:21:00", double_wick_entry=True),
    )

    assert entry["status"] == "READY"
    assert entry["next_step"] == "Step 6"
    assert entry["state"]["leg2_status"] == "VALIDATED"
    assert entry["state"]["step5_confirmation_candle_count"] == 1
    assert entry["state"]["step5_trigger_candle"]["timestamp"] == "2026-05-07T10:21:00"


def run_tests() -> None:
    tests = [
        test_short_leg2_locks_and_validates_with_sweep_and_short_trigger,
        test_long_leg2_locks_and_validates_with_sweep_and_long_trigger,
        test_four_candle_window_expires_without_sweep_and_trigger,
        test_short_close_above_anchor_extreme_invalidates,
        test_long_close_below_anchor_extreme_invalidates,
        test_nq_2026_05_07_onl_sequence_qualifies_at_1021_not_1024,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} Step 5 replay tests passed")


if __name__ == "__main__":
    run_tests()
