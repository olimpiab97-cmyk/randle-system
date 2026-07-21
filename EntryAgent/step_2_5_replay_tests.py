"""Focused replay tests for Step 2.5 pathway selection."""

from __future__ import annotations

import json
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
    previous = candle(100.5, 100.75, 98.75, 99.5)
    current = candle(99.5, 100.75, 99.25, 100.25)
    result = select_pathway(current, previous, 100.0, "LL", stack_extreme=99.0)

    assert result["status"] == "READY"
    assert result["controlling_mode"] == "S/R"
    assert result["candle_a"] == current


def test_stacked_low_sr_uses_extreme_as_continuation_boundary() -> None:
    previous = candle(100.5, 100.75, 98.75, 99.4)
    current = candle(99.6, 100.25, 99.25, 99.8)
    result = select_pathway(current, previous, 100.0, "LL", stack_extreme=99.0)

    assert result["status"] == "READY"
    assert result["controlling_mode"] == "S/R"
    assert result["candle_a"] == current


def test_stacked_high_rs_waits_without_prior_close_above_upper_liquidity() -> None:
    previous = candle(30673.0, 30678.25, 30671.0, 30673.5)
    current = candle(30673.5, 30675.75, 30670.5, 30672.0)
    result = select_pathway(current, previous, 30674.0, "LH", stack_extreme=30678.25)

    assert result["status"] == "WAIT"
    assert result["controlling_mode"] is None
    assert result["continuation_step2_activated"] is False


def test_stacked_low_sr_waits_without_prior_close_below_lower_liquidity() -> None:
    previous = candle(100.5, 100.75, 99.5, 100.25)
    current = candle(100.0, 100.25, 98.75, 100.1)
    result = select_pathway(current, previous, 100.0, "LL", stack_extreme=99.0)

    assert result["status"] == "WAIT"
    assert result["controlling_mode"] is None
    assert result["continuation_step2_activated"] is False


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
    }


def test_frozen_rejection_continuation_confirms_immediately_on_close_through_active_boundary() -> None:
    interaction = base_interaction()
    interaction.update(
        {
            "candidate_modes": ["Normal Rejection Mode"],
            "controlling_mode": None,
            "continuation_eligibility_open": True,
            "continuation_eligible_source": "frozen_rejection_trade_state",
            "continuation_reference_boundary_type": "frozen_rejection_close_boundary",
            "continuation_reference_boundary_price": 52763.0,
            "continuation_active_boundary_price": 52763.0,
            "current_boundary": 52763.0,
            "continuation_seeded_from_rejection_step4": True,
            "active_liquidity_selected": True,
            "rejection_step2_confirmed": True,
            "active_liquidity": {"name": "YH", "price": 52763.0, "side": "upper"},
            "active_liquidity_name": "YH",
            "active_liquidity_price": 52763.0,
            "level": 52763.0,
            "level_type": "LH",
            "last_candle": candle(52768.0, 52770.0, 52737.0, 52739.0),
            "prev_candle": candle(52781.0, 52800.0, 52764.0, 52766.0),
        }
    )
    result = evaluate_step25(interaction)
    assert result["status"] == "READY"
    assert result["next_step"] == "Step 3"
    assert result["state"]["continuation_step2_activated"] is True
    assert result["state"]["continuation_active_boundary_price"] == 52763.0
    assert result["state"]["reclaim_candle_a"]["close"] == 52739.0


def live_status_sequence(level_name: str, level_price: float, candles: list[dict], initial_state: dict | None = None) -> list[dict]:
    import entry_agent

    original_state_path = entry_agent.STATE_PATH
    original_get_latest = entry_agent.get_latest_market_snapshot
    original_load_tv = entry_agent.load_tv_context
    original_recent = entry_agent.recent_closed_bars
    original_load_atr = entry_agent.load_rithmic_atr_snapshot
    original_append_audit = entry_agent.append_entry_agent_audit_row
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry_agent.STATE_PATH = Path(temp_dir) / "entry_agent_state.json"
            entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
            if isinstance(initial_state, dict):
                entry_agent.STATE_PATH.write_text(json.dumps(initial_state), encoding="utf-8")
            other_level_name = "PMH" if level_name != "PMH" else "PML"
            other_level_price = level_price + 10.0 if level_name != "PMH" else level_price - 10.0
            tv_context = {
                "normalized_symbol": "NQ",
                "received_at": "2026-06-05T13:30:00Z",
                "locked": True,
                "daily_atr14": 100.0,
                "levels": {
                    level_name: {
                        "price": level_price,
                        "status": "ACTIVE",
                        "stack_group": "NONE",
                    },
                    other_level_name: {
                        "price": other_level_price,
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
                    "liquidity": {
                        "nearest_level_above": {"name": "PMH", "price": 110.0},
                        "nearest_level_below": {"name": "PML", "price": 90.0},
                        "tick_size": 0.25,
                    },
                    "atr": {"atr_1m_14": 10.0},
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
            entry_agent.load_rithmic_atr_snapshot = lambda _symbol="NQ": {"atr_1m_14": 10.0}

            observed: list[dict] = []
            for candle_data in candles:
                index["value"] = len(observed)
                bars.append(dict(candle_data))
                current_snapshot = entry_agent.run_once("NQ", persist=True)
                original_run_once = entry_agent.run_once
                try:
                    entry_agent.run_once = lambda symbol="NQ", persist=False, _snapshot=current_snapshot: _snapshot
                    status = entry_agent.build_entry_status("NQ")
                finally:
                    entry_agent.run_once = original_run_once
                state = entry_agent.load_entry_state()
                symbol_state = state.get("state_by_symbol", {}).get("NQ", state)
                step25_state = (symbol_state.get("step25") or {}).get("state") or {}
                step4_state = (symbol_state.get("step4") or {}).get("state") or {}
                observed.append(
                    {
                        "controlling_mode": step25_state.get("controlling_mode"),
                        "continuation_step2_activated": step25_state.get("continuation_step2_activated"),
                        "continuation_probe_boundary": step25_state.get("continuation_probe_boundary"),
                        "reclaim_candle_time": (
                            step25_state.get("reclaim_candle_a") or {}
                        ).get("timestamp") if isinstance(step25_state.get("reclaim_candle_a"), dict) else None,
                        "pathway_level": step25_state.get("pathway_level"),
                        "step4_status": (symbol_state.get("step4") or {}).get("status"),
                        "step4_mode": step4_state.get("controlling_mode"),
                        "step4_setup_direction": step4_state.get("setup_direction"),
                        "step4_leg1_status": step4_state.get("leg1_status"),
                        "step4_leg1_completed_at": step4_state.get("leg1_completed_at"),
                        "step4_candle_a_time": (
                            step4_state.get("candle_a") or {}
                        ).get("timestamp") if isinstance(step4_state.get("candle_a"), dict) else None,
                        "step4_candle_b_time": (
                            step4_state.get("candle_b") or {}
                        ).get("timestamp") if isinstance(step4_state.get("candle_b"), dict) else None,
                        "active_liquidity_name": (status or {}).get("active_liquidity_name"),
                        "current_pathway_control": (status or {}).get("current_pathway_control"),
                        "step2_candle_count": (status or {}).get("step2_candle_count"),
                        "step4_status_public": (status or {}).get("step4_status"),
                        "rejection_lane_status": ((status or {}).get("rejection_lane") or {}).get("lane_status"),
                        "rejection_lane_reason": ((status or {}).get("rejection_lane") or {}).get("invalidation_reason"),
                        "rejection_lane_step4_status": ((status or {}).get("rejection_lane") or {}).get("step4_status"),
                        "rejection_lane_wick_boundary_extreme": ((status or {}).get("rejection_lane") or {}).get("wick_boundary_extreme"),
                        "rejection_lane_candle_count": ((status or {}).get("rejection_lane") or {}).get("candle_count"),
                        "continuation_lane_status": ((status or {}).get("continuation_lane") or {}).get("lane_status"),
                        "continuation_lane_step2_status": ((status or {}).get("continuation_lane") or {}).get("step2_status"),
                        "continuation_lane_step4_status": ((status or {}).get("continuation_lane") or {}).get("step4_status"),
                        "continuation_lane_candle_count": ((status or {}).get("continuation_lane") or {}).get("candle_count"),
                        "continuation_lane_extreme_boundary": ((status or {}).get("continuation_lane") or {}).get("extreme_boundary"),
                        "continuation_lane_wick_boundary_extreme": ((status or {}).get("continuation_lane") or {}).get("wick_boundary_extreme"),
                    }
                )
            return observed
    finally:
        entry_agent.STATE_PATH = original_state_path
        entry_agent.get_latest_market_snapshot = original_get_latest
        entry_agent.load_tv_context = original_load_tv
        entry_agent.recent_closed_bars = original_recent
        entry_agent.load_rithmic_atr_snapshot = original_load_atr
        entry_agent.append_entry_agent_audit_row = original_append_audit


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
    assert observed[2]["controlling_mode"] == "S/R"
    assert observed[2]["continuation_step2_activated"] is True
    assert observed[2]["continuation_probe_boundary"]["boundary_price"] == 100.0
    assert observed[2]["reclaim_candle_time"] == "2026-06-05T13:54:00Z"
    assert observed[2]["pathway_level"] == 100.0
    assert observed[3]["controlling_mode"] == "S/R"
    assert observed[3]["continuation_step2_activated"] is True
    assert observed[3]["reclaim_candle_time"] == "2026-06-05T13:54:00Z"
    assert observed[3]["pathway_level"] == 100.0


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
    assert observed[2]["controlling_mode"] == "R/S"
    assert observed[2]["continuation_step2_activated"] is True
    assert observed[2]["continuation_probe_boundary"]["boundary_price"] == 100.0
    assert observed[2]["reclaim_candle_time"] == "2026-06-05T14:04:00Z"
    assert observed[2]["pathway_level"] == 100.0
    assert observed[3]["controlling_mode"] == "R/S"
    assert observed[3]["continuation_step2_activated"] is True
    assert observed[3]["reclaim_candle_time"] == "2026-06-05T14:04:00Z"
    assert observed[3]["pathway_level"] == 100.0


def test_live_sr_continuation_deeper_wick_resets_boundary_and_requires_close_beyond_latest_high() -> None:
    observed = live_status_sequence(
        "PML",
        100.0,
        [
            {"timestamp": "2026-06-05T13:52:00Z", "open": 100.25, "high": 100.5, "low": 99.25, "close": 99.25},
            {"timestamp": "2026-06-05T13:53:00Z", "open": 99.25, "high": 100.5, "low": 99.0, "close": 99.75},
            {"timestamp": "2026-06-05T13:54:00Z", "open": 99.75, "high": 101.0, "low": 99.5, "close": 100.25},
            {"timestamp": "2026-06-05T13:55:00Z", "open": 100.25, "high": 101.0, "low": 99.75, "close": 100.75},
            {"timestamp": "2026-06-05T13:56:00Z", "open": 101.0, "high": 101.25, "low": 100.75, "close": 101.25},
        ],
    )

    assert observed[1]["controlling_mode"] == "Normal Rejection Mode"
    assert observed[1]["continuation_probe_boundary"]["boundary_price"] == 100.5
    assert observed[2]["controlling_mode"] == "S/R"
    assert observed[2]["continuation_step2_activated"] is True
    assert observed[2]["continuation_probe_boundary"]["boundary_price"] == 100.0
    assert observed[3]["controlling_mode"] == "S/R"
    assert observed[3]["continuation_step2_activated"] is True
    assert observed[3]["continuation_probe_boundary"]["boundary_price"] == 100.0
    assert observed[4]["controlling_mode"] == "S/R"
    assert observed[4]["continuation_step2_activated"] is True
    assert observed[4]["pathway_level"] == 100.0


def test_live_rs_continuation_deeper_wick_resets_boundary_and_requires_close_beyond_latest_low() -> None:
    observed = live_status_sequence(
        "PMH",
        100.0,
        [
            {"timestamp": "2026-06-05T14:02:00Z", "open": 99.75, "high": 100.75, "low": 99.5, "close": 100.75},
            {"timestamp": "2026-06-05T14:03:00Z", "open": 100.75, "high": 101.0, "low": 99.5, "close": 100.25},
            {"timestamp": "2026-06-05T14:04:00Z", "open": 100.25, "high": 100.5, "low": 99.0, "close": 99.75},
            {"timestamp": "2026-06-05T14:05:00Z", "open": 99.75, "high": 100.0, "low": 99.0, "close": 99.25},
            {"timestamp": "2026-06-05T14:06:00Z", "open": 99.0, "high": 99.0, "low": 98.75, "close": 98.75},
        ],
    )

    assert observed[1]["controlling_mode"] == "Normal Rejection Mode"
    assert observed[1]["continuation_probe_boundary"]["boundary_price"] == 99.5
    assert observed[2]["controlling_mode"] == "R/S"
    assert observed[2]["continuation_step2_activated"] is True
    assert observed[2]["continuation_probe_boundary"]["boundary_price"] == 100.0
    assert observed[3]["controlling_mode"] == "R/S"
    assert observed[3]["continuation_step2_activated"] is True
    assert observed[3]["continuation_probe_boundary"]["boundary_price"] == 100.0
    assert observed[4]["controlling_mode"] == "R/S"
    assert observed[4]["continuation_step2_activated"] is True
    assert observed[4]["pathway_level"] == 100.0


def test_rs_continuation_confirms_on_close_beyond_carried_wick_boundary() -> None:
    current = {
        "timestamp": "2026-06-24T13:57:00Z",
        "open": 52181.0,
        "high": 52190.0,
        "low": 52135.0,
        "close": 52146.0,
    }
    previous = {
        "timestamp": "2026-06-24T13:56:00Z",
        "open": 52183.0,
        "high": 52197.0,
        "low": 52165.0,
        "close": 52182.0,
    }

    result = select_pathway(
        current,
        previous,
        52176.0,
        "LH",
        stack_extreme=52176.0,
        current_boundary=52165.0,
        tick_size=1.0,
        active_liquidity_selected=True,
        rejection_step2_confirmed=True,
    )

    assert result["status"] == "READY"
    assert result["controlling_mode"] == "R/S"
    assert result["continuation_step2_activated"] is True
    assert result["pathway_level"] == 52165.0
    assert result["candle_a"]["timestamp"] == "2026-06-24T13:57:00Z"


def test_ym_2026_06_24_continuation_control_persists_on_0658_after_0657_confirmation() -> None:
    observed = live_status_sequence(
        "PMH",
        52176.0,
        [
            {"timestamp": "2026-06-24T13:50:00Z", "open": 52130.0, "high": 52208.0, "low": 52130.0, "close": 52203.0},
            {"timestamp": "2026-06-24T13:51:00Z", "open": 52204.0, "high": 52238.0, "low": 52189.0, "close": 52234.0},
            {"timestamp": "2026-06-24T13:52:00Z", "open": 52233.0, "high": 52258.0, "low": 52217.0, "close": 52226.0},
            {"timestamp": "2026-06-24T13:53:00Z", "open": 52224.0, "high": 52244.0, "low": 52197.0, "close": 52210.0},
            {"timestamp": "2026-06-24T13:54:00Z", "open": 52210.0, "high": 52228.0, "low": 52199.0, "close": 52220.0},
            {"timestamp": "2026-06-24T13:55:00Z", "open": 52218.0, "high": 52233.0, "low": 52171.0, "close": 52180.0},
            {"timestamp": "2026-06-24T13:56:00Z", "open": 52183.0, "high": 52197.0, "low": 52165.0, "close": 52182.0},
            {"timestamp": "2026-06-24T13:57:00Z", "open": 52181.0, "high": 52190.0, "low": 52135.0, "close": 52146.0},
            {"timestamp": "2026-06-24T13:58:00Z", "open": 52148.0, "high": 52159.0, "low": 52143.0, "close": 52150.0},
        ],
    )

    # This simplified replay fixture does not provide a stacked continuation
    # owner or next same-side liquidity ladder, so rejection completes Step 4
    # instead of invalidating and the continuation wick is observed through the
    # internal probe boundary rather than a populated public lane boundary.
    assert observed[5]["continuation_lane_status"] == "eligible"
    assert observed[5]["continuation_lane_step2_status"] == "WAIT"
    assert observed[5]["continuation_probe_boundary"]["boundary_price"] == 52171.0
    assert observed[5]["rejection_lane_status"] == "controlling"
    assert observed[5]["rejection_lane_step4_status"] == "CONFIRMED"
    assert observed[6]["continuation_lane_status"] == "eligible"
    assert observed[6]["continuation_lane_step2_status"] == "WAIT"
    assert observed[6]["continuation_probe_boundary"]["boundary_price"] == 52165.0
    assert observed[6]["rejection_lane_status"] == "controlling"
    assert observed[6]["rejection_lane_step4_status"] == "CONFIRMED"
    assert observed[7]["current_pathway_control"] == "continuation"
    assert observed[7]["rejection_lane_status"] == "frozen"
    assert observed[7]["rejection_lane_reason"] is None
    assert observed[7]["rejection_lane_step4_status"] == "CONFIRMED"
    assert observed[7]["continuation_lane_status"] == "controlling"
    assert observed[7]["continuation_lane_step2_status"] == "CONFIRMED"
    assert observed[7]["continuation_lane_candle_count"] is None

    # By 13:58 this reduced fixture has rotated to a new active liquidity owner
    # without the persisted continuation lane context the full runtime carries
    # forward, so only the historical rejection lane remains projected.
    assert observed[8]["active_liquidity_name"] == "PML"
    assert observed[8]["current_pathway_control"] == "rejection"
    assert observed[8]["rejection_lane_status"] == "frozen"
    assert observed[8]["rejection_lane_step4_status"] == "CONFIRMED"
    assert observed[8]["rejection_lane_reason"] is None
    assert observed[8]["rejection_lane_status"] == observed[7]["rejection_lane_status"]
    assert observed[8]["rejection_lane_reason"] == observed[7]["rejection_lane_reason"]
    assert observed[8]["continuation_lane_status"] == "idle"
    assert observed[8]["continuation_lane_step2_status"] == "WAIT"
    assert observed[8]["continuation_lane_step4_status"] == "WAIT"
    assert observed[8]["step4_status_public"] == observed[8]["rejection_lane_step4_status"]


def test_live_rs_same_candle_rejection_leg1_blocks_same_candle_continuation_activation() -> None:
    observed = live_status_sequence(
        "PMH",
        100.0,
        [
            {"timestamp": "2026-06-10T13:38:00Z", "open": 99.5, "high": 101.0, "low": 99.25, "close": 100.5},
            {"timestamp": "2026-06-10T13:39:00Z", "open": 100.5, "high": 100.75, "low": 99.0, "close": 99.5},
            {"timestamp": "2026-06-10T13:40:00Z", "open": 99.5, "high": 99.75, "low": 98.75, "close": 99.25},
        ],
    )

    assert observed[1]["controlling_mode"] == "Normal Rejection Mode"
    assert observed[1]["continuation_step2_activated"] is None
    assert observed[1]["reclaim_candle_time"] is None
    assert observed[1]["step4_status"] == "READY"
    assert observed[1]["step4_mode"] == "Normal Rejection Mode"
    assert observed[1]["step4_setup_direction"] == "SHORT"
    assert observed[1]["step4_leg1_status"] == "COMPLETE"
    assert observed[1]["step4_leg1_completed_at"] == "2026-06-10T13:39:00Z"
    assert observed[1]["step4_candle_a_time"] == "2026-06-10T13:38:00Z"
    assert observed[1]["step4_candle_b_time"] == "2026-06-10T13:39:00Z"
    assert observed[2]["controlling_mode"] is None
    assert observed[2]["continuation_step2_activated"] is None
    assert observed[2]["reclaim_candle_time"] is None
    assert observed[2]["pathway_level"] == 98.75


def test_live_sr_same_candle_rejection_leg1_blocks_same_candle_continuation_activation() -> None:
    observed = live_status_sequence(
        "PML",
        100.0,
        [
            {"timestamp": "2026-06-10T13:38:00Z", "open": 100.5, "high": 100.75, "low": 99.0, "close": 99.5},
            {"timestamp": "2026-06-10T13:39:00Z", "open": 99.5, "high": 101.0, "low": 99.25, "close": 100.5},
            {"timestamp": "2026-06-10T13:40:00Z", "open": 100.5, "high": 101.25, "low": 100.25, "close": 100.75},
        ],
    )

    assert observed[1]["controlling_mode"] == "Normal Rejection Mode"
    assert observed[1]["continuation_step2_activated"] is None
    assert observed[1]["reclaim_candle_time"] is None
    assert observed[1]["step4_status"] == "READY"
    assert observed[1]["step4_mode"] == "Normal Rejection Mode"
    assert observed[1]["step4_setup_direction"] == "LONG"
    assert observed[1]["step4_leg1_status"] == "COMPLETE"
    assert observed[1]["step4_leg1_completed_at"] == "2026-06-10T13:39:00Z"
    assert observed[1]["step4_candle_a_time"] == "2026-06-10T13:38:00Z"
    assert observed[1]["step4_candle_b_time"] == "2026-06-10T13:39:00Z"
    assert observed[2]["controlling_mode"] is None
    assert observed[2]["continuation_step2_activated"] is None
    assert observed[2]["reclaim_candle_time"] is None
    assert observed[2]["pathway_level"] == 101.25


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


def test_ym_yh_continuation_activation_keeps_spent_pmh_onh_blocked() -> None:
    import copy
    import entry_agent

    original_recent = entry_agent.recent_closed_bars
    try:
        bars = [
            {"open": 52388.0, "high": 52392.0, "low": 52382.0, "close": 52386.0, "timestamp": "2026-06-16T13:53:00Z"},
            {"open": 52386.0, "high": 52391.0, "low": 52381.0, "close": 52384.0, "timestamp": "2026-06-16T13:54:00Z"},
        ]
        entry_agent.recent_closed_bars = lambda _symbol, limit=2: copy.deepcopy(bars[-limit:])

        initial_candle_a = {
            "open": 52310.0,
            "high": 52395.0,
            "low": 52305.0,
            "close": 52390.0,
            "timestamp": "2026-06-16T13:31:00Z",
        }
        owner = {
            "pathway": "rejection",
            "setup_direction": "SHORT",
            "active_liquidity": {"name": "YH", "price": 52380.0, "side": "upper"},
            "active_liquidity_name": "YH",
            "active_liquidity_price": 52380.0,
            "active_liquidity_group": None,
            "candle_a": initial_candle_a,
        }
        consumed = [
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
        snapshot = {
            "normalized_symbol": "YM",
            "symbol": "YM",
            "latest_bar_time": "2026-06-16T13:55:00Z",
            "latest_price": 52343.0,
            "ohlc_is_closed": True,
            "ohlc": {"open": 52383.0, "high": 52387.0, "low": 52343.0, "close": 52343.0},
            "tv_context": {
                "levels": {
                    "PMH": {"price": 52282.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "ONH": {"price": 52282.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "YH": {"price": 52380.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "PML": {"price": 52164.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                    "ONL": {"price": 52080.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "YL": {"price": 52087.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "LL": {"price": 52135.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                },
                "atr_1m_14": 20.0,
            },
            "liquidity": {
                "tick_size": 1.0,
                "nearest_level_below": {"name": "PML", "price": 52164.0},
                "nearest_level_above": None,
            },
            "atr": {"atr_1m_14": 20.0},
        }
        persisted_symbol = {
            "normalized_symbol": "NQ",
            "step_2_1a": {
                "step_2_activated": True,
                "active_level": "YH",
                "level_price": 52380.0,
                "side": "upper",
                "candle_a": initial_candle_a,
                "step2_locked_owner": owner,
            },
            "step2_locked_owner": owner,
            "step4": {
                "status": "READY",
                "state": {
                    "rejection_mode": "ON",
                    "interaction_state": "ACTIVE",
                    "setup_direction": "SHORT",
                    "leg1_status": "COMPLETE",
                    "leg1_state_locked": True,
                    "leg1_reference": 52390.0,
                    "leg1_reference_price": 52390.0,
                    "leg1_reference_candle_time": "2026-06-16T13:34:00Z",
                    "leg1_completed_at": "2026-06-16T13:34:00Z",
                    "anchor_extreme": 52538.0,
                    "active_liquidity": {"name": "YH", "price": 52380.0, "side": "upper"},
                    "candle_b": {
                        "open": 52515.0,
                        "high": 52538.0,
                        "low": 52500.0,
                        "close": 52525.0,
                        "timestamp": "2026-06-16T13:34:00Z",
                    },
                    "controlling_mode": "Normal Rejection Mode",
                    "candidate_modes": ["Normal Rejection Mode"],
                    "initial_candle_a": initial_candle_a,
                },
            },
            "step25": {
                "status": "READY",
                "state": {
                    "step25_pathway_selection_complete": True,
                    "controlling_mode": "Normal Rejection Mode",
                    "candidate_modes": ["Normal Rejection Mode"],
                    "initial_candle_a": initial_candle_a,
                    "active_liquidity": {"name": "YH", "price": 52380.0, "side": "upper"},
                },
            },
            "last_interacted_liquidity": {"name": "YH", "price": 52380.0, "side": "upper"},
            "consumed_liquidity_levels": consumed,
        }

        step2 = entry_agent.evaluate_live_step_2_1a(
            snapshot,
            {},
            {"tick_size": 1.0},
            {"state_by_symbol": {"YM": persisted_symbol}},
        )
        rejection = entry_agent.rejection_from_step2_activation(step2, "YM")
        step25 = entry_agent.evaluate_live_step25(snapshot, rejection, step2, persisted_symbol)
    finally:
        entry_agent.recent_closed_bars = original_recent

    assert step2["step_2_activated"] is True
    assert step2["active_level"] == "YH"
    consumed_names = {(record.get("name"), record.get("price")) for record in step2["consumed_liquidity_levels"]}
    assert ("PMH", 52282.0) in consumed_names
    assert ("ONH", 52282.0) in consumed_names
    assert ("YH", 52380.0) not in consumed_names
    assert rejection["rejection_mode"] == "ON"
    assert rejection["trigger_level"] == "YH"
    assert step25["status"] == "READY"
    assert step25["state"]["controlling_mode"] == "R/S"
    assert step25["state"]["continuation_step2_activated"] is True
    assert step25["state"]["pathway_level"] == 52380.0
    assert step25["state"]["reclaim_candle_a"]["timestamp"] == "2026-06-16T13:55:00Z"


def test_nq_2026_06_18_high1_red_close_below_close_boundary_stays_wait_until_close_above_extreme() -> None:
    import entry_agent

    original_recent = entry_agent.recent_closed_bars
    try:
        probe_candle = {
            "open": 30512.0,
            "high": 30547.0,
            "low": 30509.75,
            "close": 30544.25,
            "timestamp": "2026-06-18T14:34:00Z",
        }
        activation_candle = {
            "open": 30543.5,
            "high": 30548.25,
            "low": 30523.25,
            "close": 30531.5,
            "timestamp": "2026-06-18T14:35:00Z",
        }
        group = {
            "name": "HIGH 1",
            "components": ["YH", "ONH", "PMH"],
            "prices": {"YH": 30545.75, "ONH": 30538.0, "PMH": 30538.0},
            "side": "upper",
            "display_name": "PMH/ONH/YH Liquidity",
            "close_boundary": 30538.0,
            "extreme_boundary": 30545.75,
        }
        snapshot = {
            "normalized_symbol": "NQ",
            "latest_bar_time": activation_candle["timestamp"],
            "latest_price": activation_candle["close"],
            "ohlc_is_closed": True,
            "ohlc": activation_candle,
            "tv_context": {
                "levels": {
                    "PMH": {"price": 30538.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "ONH": {"price": 30538.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "YH": {"price": 30545.75, "status": "ACTIVE", "stack_group": "HIGH 1"},
                }
            },
            "liquidity": {
                "tick_size": 0.25,
                "nearest_level_above": {"name": "PMH", "price": 30538.0},
                "nearest_level_below": {"name": "PML", "price": 30397.0},
            },
            "atr": {"atr_1m_14": 20.0},
        }
        persisted_symbol = {
            "step_2_1a": {
                "step_2_activated": False,
                "blocked": False,
                "candle_a": None,
                "active_level": "YH",
                "level_price": 30545.75,
                "side": "upper",
                "tick_size": 0.25,
                "expiration_candles": 5,
                "active_liquidity_group": group,
                "pre_activation_probe_boundary": {
                    "active": True,
                    "side": "upper",
                    "source_level": "YH",
                    "boundary_price": 30547.0,
                    "detected_at_index": 552,
                },
                "events": [{"event": "pre_activation_probe_detected", "timestamp": "2026-06-18T14:34:00Z"}],
            },
            "last_interacted_liquidity": {
                "name": "YH",
                "price": 30545.75,
                "display_name": "PMH/ONH/YH Liquidity",
                "side": "upper",
                "group": group,
            },
        }
        entry_agent.recent_closed_bars = lambda _symbol, _count: [probe_candle, activation_candle]

        persisted_state = {"state_by_symbol": {"NQ": persisted_symbol}}
        step2 = entry_agent.evaluate_live_step_2_1a(snapshot, {}, {"tick_size": 0.25}, persisted_state)
        rejection = entry_agent.rejection_from_step2_activation(step2, "NQ")
        step25 = entry_agent.evaluate_live_step25(snapshot, rejection, step2, persisted_symbol)
    finally:
        entry_agent.recent_closed_bars = original_recent

    # Under the corrected Step 2 contract, a red close back below the stack does
    # not activate rejection until a later candle closes above the active raid extreme.
    assert step2["step_2_activated"] is False
    assert step2["candle_a"] is None
    assert step2["active_liquidity_group"]["display_name"] == "PMH/ONH/YH Liquidity"
    assert step2["active_liquidity_group"]["close_boundary"] == 30538.0
    assert step2["active_liquidity_group"]["extreme_boundary"] == 30545.75
    assert step2["active_liquidity_group"]["wick_boundary_extreme"] == 30548.25
    assert step2["pre_activation_probe_boundary"]["active"] is True
    assert step2["pre_activation_probe_boundary"]["boundary_price"] == 30548.25
    assert rejection["rejection_mode"] == "OFF"
    assert step25["status"] == "WAIT"
    assert step25["reason"] == "Step 2.5 requires a Step 2 liquidity-close pathway activation."


def test_nq_2026_06_19_high1_rs_continuation_uses_stack_extreme_not_close_boundary() -> None:
    previous = candle(30685.0, 30686.75, 30678.0, 30682.75)
    current = candle(30682.25, 30684.75, 30664.25, 30668.25)

    # HIGH 1 close boundary is 30666, but the operative continuation stack extreme is PMH 30670.
    result = select_pathway(current, previous, 30670.0, "LH", stack_extreme=30670.0)

    assert result["status"] == "READY"
    assert result["controlling_mode"] == "R/S"
    assert result["continuation_step2_activated"] is True
    assert result["pathway_level"] == 30670.0
    assert result["structure_side_requirement"] == "BELOW_LEVEL"
    assert result["candle_a"]["close"] == 30668.25


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
        test_frozen_rejection_continuation_confirms_immediately_on_close_through_active_boundary,
        test_live_sr_continuation_wick_reset_persists_boundary_before_activation,
        test_live_rs_continuation_wick_reset_persists_boundary_before_activation,
        test_live_sr_continuation_deeper_wick_resets_boundary_and_requires_close_beyond_latest_high,
        test_live_rs_continuation_deeper_wick_resets_boundary_and_requires_close_beyond_latest_low,
        test_rs_continuation_confirms_on_close_beyond_carried_wick_boundary,
        test_live_rs_same_candle_rejection_leg1_blocks_same_candle_continuation_activation,
        test_live_sr_same_candle_rejection_leg1_blocks_same_candle_continuation_activation,
        test_sr_continuation_step2_active_still_requires_shelf_sweep,
        test_rs_continuation_step2_active_still_requires_shelf_sweep,
        test_normal_rejection_does_not_require_continuation_shelf_sweep,
        test_ym_2026_05_28_step2_stores_continuation_controlling_high,
        test_upper_liquidity_step2_stores_final_bearish_control_low_not_older_extreme,
        test_ym_yh_continuation_activation_keeps_spent_pmh_onh_blocked,
        test_nq_2026_06_18_high1_red_close_below_close_boundary_stays_wait_until_close_above_extreme,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} Step 2.5 replay tests passed")


if __name__ == "__main__":
    run_tests()
