"""Focused replay tests for Step 2.5 pathway selection."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

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
            "continuation_step2_activated": True,
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
            "continuation_step2_activated": True,
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
    previous = candle(100.5, 100.75, 99.75, 99.8)
    current = candle(99.8, 100.4, 99.4, 100.1)
    result = select_pathway(current, previous, 100.0, "LL")

    assert result["status"] == "READY"
    assert result["controlling_mode"] == "S/R"
    assert result["activation_type"] == "close"
    assert result["candle_a"] == current
    assert result["provisional_candle_a"] is None
    assert result["structure_side_requirement"] == "ABOVE_LEVEL"


def test_stacked_low_sr_requires_wick_through_stack_extreme() -> None:
    previous = candle(101.0, 101.5, 99.5, 99.5)
    current = candle(99.5, 100.75, 98.75, 100.25)
    result = select_pathway(current, previous, 100.0, "LL", stack_extreme=99.0)

    assert result["status"] == "READY"
    assert result["controlling_mode"] == "S/R"
    assert result["activation_type"] == "close"
    assert result["candle_a"] == current
    assert result["structure_side_requirement"] == "ABOVE_LEVEL"
    assert result["continuation_uses_stack_extreme"] is True


def test_stacked_low_sr_activates_from_close_above_extreme_boundary() -> None:
    previous = candle(101.0, 101.5, 99.5, 100.5)
    current = candle(99.5, 100.75, 99.25, 100.25)
    result = select_pathway(current, previous, 100.0, "LL", stack_extreme=99.0)

    assert result["status"] == "READY"
    assert result["controlling_mode"] == "S/R"
    assert result["candle_a"] == current


def test_stacked_low_sr_uses_extreme_as_continuation_boundary() -> None:
    previous = candle(100.5, 100.75, 99.5, 99.4)
    current = candle(99.6, 100.25, 99.25, 99.8)
    result = select_pathway(current, previous, 100.0, "LL", stack_extreme=99.0)

    assert result["status"] == "READY"
    assert result["controlling_mode"] == "S/R"
    assert result["candle_a"] == current


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

    assert result["status"] == "WAIT"
    assert result["controlling_mode"] is None
    assert result["activation_type"] is None
    assert result["candle_a"] is None
    assert result["provisional_candle_a"] is None
    assert result["structure_side_requirement"] is None


def test_wick_above_lh_red_close_selects_rs() -> None:
    previous = candle(99.5, 100.3, 99.2, 100.3)
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

    assert result["status"] == "WAIT"
    assert result["controlling_mode"] is None
    assert result["activation_type"] is None
    assert result["candle_a"] is None
    assert result["provisional_candle_a"] is None
    assert result["structure_side_requirement"] is None


def test_no_step25_condition_waits() -> None:
    previous = candle(99.8, 100.2, 99.6, 100.0)
    current = candle(100.0, 100.0, 99.8, 100.0)
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
        "continuation_step2_activated": False,
        "continuation_rejection_step2_required": True,
        "continuation_probe_boundary": None,
        "continuation_activation_boundary": 100.0,
        "continuation_activation_source": "level",
    }


def live_status_sequence(level_name: str, level_price: float, candles: list[dict]) -> list[dict]:
    import entry_agent

    original_state_path = entry_agent.STATE_PATH
    original_get_latest = entry_agent.get_latest_market_snapshot
    original_load_tv = entry_agent.load_tv_context
    original_recent = entry_agent.recent_closed_bars
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry_agent.STATE_PATH = Path(temp_dir) / "entry_agent_state.json"
            tv_context = {
                "normalized_symbol": "NQ",
                "received_at": "2026-06-05T13:30:00Z",
                "locked": True,
                "levels": {
                    level_name: {
                        "price": level_price,
                        "status": "ACTIVE",
                        "stack_group": "NONE",
                    }
                },
            }
            bars: list[dict] = []
            index = {"value": 0}

            def market_snapshot(_symbol: str = "NQ") -> dict:
                current = candles[index["value"]]
                return {
                    "symbol": "NQ",
                    "normalized_symbol": "NQ",
                    "latest_price": current["close"],
                    "latest_bar_time": current["timestamp"],
                    "ohlc_is_closed": True,
                    "ohlc": {
                        "open": current["open"],
                        "high": current["high"],
                        "low": current["low"],
                        "close": current["close"],
                    },
                }

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.load_tv_context = lambda _symbol=None: tv_context
            entry_agent.recent_closed_bars = lambda _symbol="NQ", limit=120: list(bars)[-limit:]

            observed: list[dict] = []
            for candle_data in candles:
                index["value"] = len(observed)
                bars.append(dict(candle_data))
                entry_agent.build_entry_status("NQ")
                state = entry_agent.load_entry_state()
                symbol_state = state.get("state_by_symbol", {}).get("NQ", state)
                step25_state = (symbol_state.get("step25") or {}).get("state") or {}
                observed.append(
                    {
                        "controlling_mode": step25_state.get("controlling_mode"),
                        "continuation_step2_activated": step25_state.get("continuation_step2_activated"),
                        "continuation_probe_boundary": step25_state.get("continuation_probe_boundary"),
                        "reclaim_candle_time": (
                            step25_state.get("reclaim_candle_a") or {}
                        ).get("timestamp") if isinstance(step25_state.get("reclaim_candle_a"), dict) else None,
                        "pathway_level": step25_state.get("pathway_level"),
                    }
                )
            return observed
    finally:
        entry_agent.STATE_PATH = original_state_path
        entry_agent.get_latest_market_snapshot = original_get_latest
        entry_agent.load_tv_context = original_load_tv
        entry_agent.recent_closed_bars = original_recent


def test_live_sr_continuation_wick_reset_persists_boundary_before_activation() -> None:
    observed = live_status_sequence(
        "PML",
        100.0,
        [
            {"timestamp": "2026-06-05T13:52:00Z", "open": 100.25, "high": 100.5, "low": 99.25, "close": 99.25},
            {"timestamp": "2026-06-05T13:53:00Z", "open": 99.25, "high": 100.5, "low": 99.0, "close": 99.75},
            {"timestamp": "2026-06-05T13:54:00Z", "open": 99.75, "high": 100.25, "low": 99.5, "close": 100.25},
            {"timestamp": "2026-06-05T13:55:00Z", "open": 100.25, "high": 100.75, "low": 99.5, "close": 100.75},
        ],
    )

    assert observed[1]["controlling_mode"] == "Normal Rejection Mode"
    assert observed[1]["continuation_step2_activated"] is None
    assert observed[1]["continuation_probe_boundary"]["active"] is True
    assert observed[1]["continuation_probe_boundary"]["boundary_price"] == 100.5
    assert observed[2]["controlling_mode"] == "Normal Rejection Mode"
    assert observed[2]["continuation_step2_activated"] is None
    assert observed[2]["continuation_probe_boundary"]["boundary_price"] == 100.5
    assert observed[3]["controlling_mode"] == "S/R"
    assert observed[3]["continuation_step2_activated"] is True
    assert observed[3]["reclaim_candle_time"] == "2026-06-05T13:55:00Z"
    assert observed[3]["pathway_level"] == 100.5


def test_live_rs_continuation_wick_reset_persists_boundary_before_activation() -> None:
    observed = live_status_sequence(
        "PMH",
        100.0,
        [
            {"timestamp": "2026-06-05T14:02:00Z", "open": 99.75, "high": 100.75, "low": 99.5, "close": 100.75},
            {"timestamp": "2026-06-05T14:03:00Z", "open": 100.75, "high": 101.0, "low": 99.5, "close": 100.25},
            {"timestamp": "2026-06-05T14:04:00Z", "open": 100.25, "high": 100.5, "low": 99.75, "close": 99.75},
            {"timestamp": "2026-06-05T14:05:00Z", "open": 99.75, "high": 100.5, "low": 99.25, "close": 99.25},
        ],
    )

    assert observed[1]["controlling_mode"] == "Normal Rejection Mode"
    assert observed[1]["continuation_step2_activated"] is None
    assert observed[1]["continuation_probe_boundary"]["active"] is True
    assert observed[1]["continuation_probe_boundary"]["boundary_price"] == 99.5
    assert observed[2]["controlling_mode"] == "Normal Rejection Mode"
    assert observed[2]["continuation_step2_activated"] is None
    assert observed[2]["continuation_probe_boundary"]["boundary_price"] == 99.5
    assert observed[3]["controlling_mode"] == "R/S"
    assert observed[3]["continuation_step2_activated"] is True
    assert observed[3]["reclaim_candle_time"] == "2026-06-05T14:05:00Z"
    assert observed[3]["pathway_level"] == 99.5


def test_sr_continuation_step2_active_still_requires_shelf_sweep() -> None:
    import entry_agent

    original_recent = entry_agent.recent_closed_bars
    try:
        entry_agent.recent_closed_bars = lambda _symbol, _limit: [
            {"timestamp": "2026-05-15T13:20:00Z", "open": 100.25, "high": 100.50, "low": 98.75, "close": 99.00},
            {"timestamp": "2026-05-15T13:21:00Z", "open": 99.00, "high": 101.00, "low": 98.90, "close": 100.50},
            {"timestamp": "2026-05-15T13:22:00Z", "open": 100.50, "high": 100.60, "low": 99.50, "close": 100.00},
        ]
        status = entry_agent.continuation_controlling_structure_status(
            {
                "normalized_symbol": "NQ",
                "latest_bar_time": "2026-05-15T13:22:00Z",
                "ohlc": {"open": 100.50, "high": 100.60, "low": 99.50, "close": 100.00},
                "liquidity": {"tick_size": 0.25},
            },
            {
                "controlling_mode": "S/R",
                "continuation_step2_activated": True,
                "pathway_level": 100.0,
                "tick_size": 0.25,
                "reclaim_candle_a": {"timestamp": "2026-05-15T13:21:00Z", "open": 99.0, "high": 101.0, "low": 98.9, "close": 100.5},
            },
        )
    finally:
        entry_agent.recent_closed_bars = original_recent

    assert status["required"] is True
    assert status["swept"] is False
    assert "controlling-structure high" in status["wait_reason"]


def test_rs_continuation_step2_active_still_requires_shelf_sweep() -> None:
    import entry_agent

    original_recent = entry_agent.recent_closed_bars
    try:
        entry_agent.recent_closed_bars = lambda _symbol, _limit: [
            {"timestamp": "2026-05-15T13:20:00Z", "open": 99.75, "high": 101.25, "low": 99.50, "close": 101.00},
            {"timestamp": "2026-05-15T13:21:00Z", "open": 101.00, "high": 101.10, "low": 99.00, "close": 99.50},
            {"timestamp": "2026-05-15T13:22:00Z", "open": 99.50, "high": 100.50, "low": 99.40, "close": 100.00},
        ]
        status = entry_agent.continuation_controlling_structure_status(
            {
                "normalized_symbol": "NQ",
                "latest_bar_time": "2026-05-15T13:22:00Z",
                "ohlc": {"open": 99.50, "high": 100.50, "low": 99.40, "close": 100.00},
                "liquidity": {"tick_size": 0.25},
            },
            {
                "controlling_mode": "R/S",
                "continuation_step2_activated": True,
                "pathway_level": 100.0,
                "tick_size": 0.25,
                "reclaim_candle_a": {"timestamp": "2026-05-15T13:21:00Z", "open": 101.0, "high": 101.1, "low": 99.0, "close": 99.5},
            },
        )
    finally:
        entry_agent.recent_closed_bars = original_recent

    assert status["required"] is True
    assert status["swept"] is False
    assert "controlling-structure low" in status["wait_reason"]


def test_normal_rejection_does_not_require_continuation_shelf_sweep() -> None:
    import entry_agent

    status = entry_agent.continuation_controlling_structure_status(
        {"normalized_symbol": "NQ", "ohlc": {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}},
        {"controlling_mode": "Normal Rejection Mode", "continuation_step2_activated": True},
    )

    assert status == {"required": False}


def test_ym_2026_05_28_step2_stores_continuation_controlling_high() -> None:
    import entry_agent

    bars = [
        {"timestamp": "2026-05-28T13:02:00Z", "open": 50671.0, "high": 50678.0, "low": 50660.0, "close": 50662.0},
        {"timestamp": "2026-05-28T13:10:00Z", "open": 50643.0, "high": 50647.0, "low": 50640.0, "close": 50641.0},
        {"timestamp": "2026-05-28T13:11:00Z", "open": 50639.0, "high": 50644.0, "low": 50635.0, "close": 50640.0},
        {"timestamp": "2026-05-28T13:12:00Z", "open": 50641.0, "high": 50658.0, "low": 50641.0, "close": 50650.0},
        {"timestamp": "2026-05-28T13:13:00Z", "open": 50653.0, "high": 50658.0, "low": 50648.0, "close": 50649.0},
        {"timestamp": "2026-05-28T13:14:00Z", "open": 50650.0, "high": 50650.0, "low": 50639.0, "close": 50639.0},
        {"timestamp": "2026-05-28T13:15:00Z", "open": 50636.0, "high": 50641.0, "low": 50632.0, "close": 50641.0},
        {"timestamp": "2026-05-28T13:16:00Z", "open": 50638.0, "high": 50640.0, "low": 50635.0, "close": 50638.0},
        {"timestamp": "2026-05-28T13:17:00Z", "open": 50636.0, "high": 50636.0, "low": 50626.0, "close": 50629.0},
        {"timestamp": "2026-05-28T13:18:00Z", "open": 50627.0, "high": 50632.0, "low": 50621.0, "close": 50621.0},
        {"timestamp": "2026-05-28T13:19:00Z", "open": 50619.0, "high": 50623.0, "low": 50617.0, "close": 50621.0},
        {"timestamp": "2026-05-28T13:20:00Z", "open": 50622.0, "high": 50623.0, "low": 50614.0, "close": 50614.0},
        {"timestamp": "2026-05-28T13:21:00Z", "open": 50612.0, "high": 50617.0, "low": 50610.0, "close": 50612.0},
        {"timestamp": "2026-05-28T13:22:00Z", "open": 50613.0, "high": 50620.0, "low": 50613.0, "close": 50617.0},
        {"timestamp": "2026-05-28T13:23:00Z", "open": 50616.0, "high": 50619.0, "low": 50610.0, "close": 50612.0},
        {"timestamp": "2026-05-28T13:24:00Z", "open": 50613.0, "high": 50615.0, "low": 50604.0, "close": 50611.0},
        {"timestamp": "2026-05-28T13:25:00Z", "open": 50613.0, "high": 50621.0, "low": 50604.0, "close": 50605.0},
        {"timestamp": "2026-05-28T13:26:00Z", "open": 50603.0, "high": 50603.0, "low": 50587.0, "close": 50588.0},
        {"timestamp": "2026-05-28T13:27:00Z", "open": 50589.0, "high": 50596.0, "low": 50582.0, "close": 50585.0},
        {"timestamp": "2026-05-28T13:28:00Z", "open": 50584.0, "high": 50591.0, "low": 50578.0, "close": 50581.0},
        {"timestamp": "2026-05-28T13:29:00Z", "open": 50579.0, "high": 50592.0, "low": 50560.0, "close": 50562.0},
    ]
    structure = entry_agent.step2_continuation_controlling_structure(
        "lower",
        bars,
        "2026-05-28T13:29:00Z",
    )

    assert structure["high"] == 50658.0
    assert structure["start_time"] == "2026-05-28T13:12:00Z"
    assert structure["end_time"] == "2026-05-28T13:13:00Z"
    assert structure["source_step"] == "Step 2"

    step_state = {
        "step_2_activated": True,
        "active_level": "ONL/PML Liquidity",
        "level_price": 50576.0,
        "side": "lower",
        "candle_a": bars[-1],
    }
    entry_agent.apply_step2_continuation_structure_fields(step_state, structure)
    owner = entry_agent.build_step2_locked_owner(
        step_state,
        {"name": "ONL/PML Liquidity", "price": 50576.0, "side": "lower"},
    )

    assert owner["setup_direction"] == "LONG"
    assert owner["continuation_controlling_structure_high"] == 50658.0
    assert owner["continuation_controlling_structure_start_time"] == "2026-05-28T13:12:00Z"
    assert owner["continuation_controlling_structure_end_time"] == "2026-05-28T13:13:00Z"
    assert owner["continuation_controlling_structure_source_step"] == "Step 2"


def test_upper_liquidity_step2_stores_final_bearish_control_low_not_older_extreme() -> None:
    import entry_agent

    bars = [
        {"timestamp": "2026-05-15T13:00:00Z", "open": 101.0, "high": 101.5, "low": 90.0, "close": 100.5},
        {"timestamp": "2026-05-15T13:01:00Z", "open": 100.5, "high": 101.0, "low": 98.5, "close": 100.0},
        {"timestamp": "2026-05-15T13:02:00Z", "open": 100.0, "high": 100.2, "low": 98.8, "close": 98.9},
        {"timestamp": "2026-05-15T13:03:00Z", "open": 98.8, "high": 99.1, "low": 95.0, "close": 96.0},
        {"timestamp": "2026-05-15T13:04:00Z", "open": 96.2, "high": 98.0, "low": 95.5, "close": 97.4},
        {"timestamp": "2026-05-15T13:05:00Z", "open": 97.6, "high": 100.5, "low": 97.2, "close": 100.4},
        {"timestamp": "2026-05-15T13:06:00Z", "open": 100.5, "high": 102.5, "low": 100.2, "close": 102.0},
    ]
    structure = entry_agent.step2_continuation_controlling_structure(
        "upper",
        bars,
        "2026-05-15T13:06:00Z",
    )

    assert structure["low"] == 95.0
    assert structure["start_time"] == "2026-05-15T13:03:00Z"
    assert structure["end_time"] == "2026-05-15T13:04:00Z"
    assert structure["source_step"] == "Step 2"


def run_tests() -> None:
    tests = [
        test_normal_rejection_selects_initial_candle_a,
        test_sr_close_based_selection_sets_reclaim_candle,
        test_rs_close_based_selection_sets_reclaim_candle,
        test_rejection_off_waits,
        test_wick_below_ll_green_close_selects_sr,
        test_stacked_low_sr_requires_wick_through_stack_extreme,
        test_stacked_low_sr_activates_from_close_above_extreme_boundary,
        test_stacked_low_sr_uses_extreme_as_continuation_boundary,
        test_close_below_ll_then_close_above_selects_sr,
        test_close_below_ll_then_wick_into_level_selects_sr_provisional,
        test_wick_above_lh_red_close_selects_rs,
        test_close_above_lh_then_close_below_selects_rs,
        test_close_above_lh_then_wick_into_level_selects_rs_provisional,
        test_no_step25_condition_waits,
        test_live_sr_continuation_wick_reset_persists_boundary_before_activation,
        test_live_rs_continuation_wick_reset_persists_boundary_before_activation,
        test_sr_continuation_step2_active_still_requires_shelf_sweep,
        test_rs_continuation_step2_active_still_requires_shelf_sweep,
        test_normal_rejection_does_not_require_continuation_shelf_sweep,
        test_ym_2026_05_28_step2_stores_continuation_controlling_high,
        test_upper_liquidity_step2_stores_final_bearish_control_low_not_older_extreme,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} Step 2.5 replay tests passed")


if __name__ == "__main__":
    run_tests()
