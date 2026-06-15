"""Focused replay tests for Step 7 termination cleanup."""

from __future__ import annotations

from step7_engine import terminate_interaction


def candle(open_price: float, high: float, low: float, close: float) -> dict:
    return {"open": open_price, "high": high, "low": low, "close": close}


def test_terminate_interaction_full_reset_contract() -> None:
    interaction = {
        "events": [{"event": "existing_event"}],
        "system_state": "REJECTION MODE ON",
        "trade_mode": "ON",
        "rejection_mode": "ON",
        "interaction_state": "ACTIVE",
        "active_liquidity": {"name": "PMH", "price": 100.0},
        "setup_direction": "SHORT",
        "pre_activation_probe_boundary": {
            "active": True,
            "side": "HIGH",
            "source_level": "PMH",
            "boundary_price": 100.0,
            "detected_at_index": 12,
        },
        "current_sc": candle(100.0, 101.0, 99.0, 100.0),
        "sc": candle(100.0, 101.0, 99.0, 100.0),
        "sc2": candle(99.5, 100.0, 99.0, 99.25),
        "sc3": candle(99.0, 99.5, 98.5, 98.75),
        "sc_progression_count": 3,
        "controlling_mode": "S/R",
        "candidate_modes": ["S/R"],
        "structure_side_requirement": "ABOVE_LEVEL",
        "pathway_level": 100.0,
        "pathway_activation_type": "close",
        "reclaim_candle_a": candle(99.0, 101.0, 98.5, 100.5),
        "provisional_candle_a": candle(99.0, 100.0, 98.5, 99.5),
    }

    result = terminate_interaction(interaction, "Step 6", "Replay termination.")
    state = result["state"]

    assert result["step"] == "Step 7"
    assert result["status"] == "TERMINATED"
    assert result["next_step"] == "Step 1"
    assert state["system_state"] == "NEUTRAL RESET"
    assert state["trade_mode"] == "OFF"
    assert state["rejection_mode"] == "OFF"
    assert state["interaction_state"] == "TERMINATED"
    assert state["pre_activation_probe_boundary"] == {
        "active": False,
        "side": None,
        "source_level": None,
        "boundary_price": None,
        "detected_at_index": None,
    }
    assert state["current_sc"] is None
    assert state["sc"] is None
    assert state["sc2"] is None
    assert state["sc3"] is None
    assert state["sc_progression_count"] is None
    assert state["controlling_mode"] is None
    assert state["candidate_modes"] is None
    assert state["structure_side_requirement"] is None
    assert state["pathway_level"] is None
    assert state["pathway_activation_type"] is None
    assert state["reclaim_candle_a"] is None
    assert state["provisional_candle_a"] is None
    assert state["terminated_interaction_snapshot"] == {
        "terminated_liquidity_id": None,
        "terminated_liquidity_name": "PMH",
        "terminated_liquidity_price": 100.0,
        "prior_interaction_highest_close": None,
        "prior_interaction_lowest_close": None,
        "terminated_interaction_direction": "SHORT",
        "terminated_interaction_reason": "Replay termination.",
    }
    assert state["terminated_liquidity_id"] is None
    assert state["terminated_liquidity_name"] == "PMH"
    assert state["terminated_liquidity_price"] == 100.0
    assert state["prior_interaction_highest_close"] is None
    assert state["prior_interaction_lowest_close"] is None
    assert state["terminated_interaction_direction"] == "SHORT"
    assert state["terminated_interaction_reason"] == "Replay termination."
    assert result["events"][0]["event"] == "existing_event"
    assert result["events"][-1]["event"] == "step7_interaction_terminated"
    assert result["events"][-1]["source_step"] == "Step 6"
    assert result["events"][-1]["reason"] == "Replay termination."


def test_terminate_interaction_uses_explicit_close_history_only() -> None:
    interaction = {
        "active_liquidity": {"id": "PMH:100.0", "name": "PMH", "price": 100.0},
        "setup_direction": "LONG",
        "interaction_close_history": [
            {"timestamp": "2026-04-30T08:00:00-07:00", "close": 99.75},
            {"timestamp": "2026-04-30T08:01:00-07:00", "close": 100.5},
            {"timestamp": "2026-04-30T08:02:00-07:00", "close": 100.25},
        ],
    }

    result = terminate_interaction(interaction, "Step 5", "Replay close history.")
    state = result["state"]

    assert state["terminated_interaction_snapshot"]["terminated_liquidity_id"] == "PMH:100.0"
    assert state["terminated_interaction_snapshot"]["prior_interaction_highest_close"] == 100.5
    assert state["terminated_interaction_snapshot"]["prior_interaction_lowest_close"] == 99.75
    assert state["terminated_interaction_snapshot"]["terminated_interaction_direction"] == "LONG"


def run_tests() -> None:
    tests = [
        test_terminate_interaction_full_reset_contract,
        test_terminate_interaction_uses_explicit_close_history_only,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} Step 7 replay tests passed")


if __name__ == "__main__":
    run_tests()
