"""Step 7 interaction termination helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


STRUCTURE_FIELDS = (
    "candle_a",
    "candle_b",
    "leg1_status",
    "leg1_reference",
    "leg1_extreme",
    "leg1_extreme_owner",
    "anchor_extreme",
    "leg2_status",
    "leg2_candle",
    "active_step5_path",
    "wick_probe_active",
    "probe_high",
    "probe_low",
    "active_sc",
    "current_sc",
    "sc",
    "sc2",
    "sc3",
    "sc_progression_count",
    "sc_decision_pass_output",
    "entry_triggered",
    "entry_model_triggered",
    "structure_locked",
    "participation_timer",
    "sweep_extreme_boundary_seen",
)

STEP7_TERMINATION_FIELDS = STRUCTURE_FIELDS + (
    "controlling_mode",
    "candidate_modes",
    "structure_side_requirement",
    "pathway_level",
    "pathway_activation_type",
    "reclaim_candle_a",
    "provisional_candle_a",
)

# Step 8 same-liquidity re-entry will need an active-interaction close history.
# Minimal upstream contract to add before live Step 8 activation:
# interaction_close_history = [{"timestamp": str | None, "close": float}, ...]
# Step 7 consumes that field only if present; it does not infer missing closes.


def cleared_probe_state() -> dict[str, Any]:
    return {
        "active": False,
        "side": None,
        "source_level": None,
        "boundary_price": None,
        "detected_at_index": None,
    }


def as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def close_history_values(interaction: dict[str, Any]) -> list[float]:
    history = interaction.get("interaction_close_history")
    if not isinstance(history, list):
        return []

    values = []
    for item in history:
        if isinstance(item, dict):
            close = as_float(item.get("close"))
        else:
            close = as_float(item)
        if close is not None:
            values.append(close)
    return values


def terminated_liquidity_fields(interaction: dict[str, Any]) -> tuple[Any, Any, Any]:
    active_liquidity = interaction.get("active_liquidity")
    if not isinstance(active_liquidity, dict):
        active_liquidity = {}

    liquidity_id = (
        interaction.get("active_liquidity_id")
        or interaction.get("liquidity_id")
        or active_liquidity.get("id")
    )
    liquidity_name = active_liquidity.get("name") or interaction.get("active_level") or interaction.get("trigger_level")
    liquidity_price = active_liquidity.get("price") or interaction.get("level_price") or interaction.get("trigger_price")
    return liquidity_id, liquidity_name, as_float(liquidity_price)


def build_terminated_interaction_snapshot(interaction: dict[str, Any], reason: str) -> dict[str, Any]:
    close_values = close_history_values(interaction)
    liquidity_id, liquidity_name, liquidity_price = terminated_liquidity_fields(interaction)
    return {
        "terminated_liquidity_id": liquidity_id,
        "terminated_liquidity_name": liquidity_name,
        "terminated_liquidity_price": liquidity_price,
        "prior_interaction_highest_close": max(close_values) if close_values else None,
        "prior_interaction_lowest_close": min(close_values) if close_values else None,
        "terminated_interaction_direction": interaction.get("setup_direction"),
        "terminated_interaction_reason": reason,
    }


def terminate_interaction(interaction: dict[str, Any] | None, source_step: str, reason: str) -> dict[str, Any]:
    """Route invalidation through Step 7 and clear reusable structure."""
    state = deepcopy(interaction) if isinstance(interaction, dict) else {}
    events = list(state.get("events") or [])
    terminated_snapshot = build_terminated_interaction_snapshot(state, reason)

    for field in STEP7_TERMINATION_FIELDS:
        state[field] = None

    state["system_state"] = "NEUTRAL RESET"
    state["trade_mode"] = "OFF"
    state["rejection_mode"] = "OFF"
    state["interaction_state"] = "TERMINATED"
    state["pre_activation_probe_boundary"] = cleared_probe_state()
    state["terminated_by"] = source_step
    state["termination_reason"] = reason
    state["reason"] = reason
    state["terminated_interaction_snapshot"] = terminated_snapshot
    state.update(terminated_snapshot)
    events.append({"event": "step7_interaction_terminated", "source_step": source_step, "reason": reason})

    return {
        "step": "Step 7",
        "status": "TERMINATED",
        "state": state,
        "next_step": "Step 1",
        "reason": reason,
        "events": events,
    }
