"""Internal continuation pathway engine for the public two-lane Step 2 contract."""

from __future__ import annotations

from typing import Any


NORMAL_MODE = "Normal Rejection Mode"
SR_MODE = "S/R"
RS_MODE = "R/S"


def result(status: str, state: dict[str, Any], next_step: str, reason: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "step": "Step 2.5",
        "status": status,
        "state": state,
        "next_step": next_step,
        "reason": reason,
        "events": events,
    }


def normalize_mode(mode: Any) -> str | None:
    value = str(mode or "").strip().upper().replace(" ", "")
    if value in {"S/R", "SR", "S/RPULLBACKCONTINUATION"}:
        return SR_MODE
    if value in {"R/S", "RS", "R/SPULLBACKCONTINUATION"}:
        return RS_MODE
    if value in {"NORMAL", "NORMALREJECTION", "NORMALREJECTIONMODE"}:
        return NORMAL_MODE
    return None


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if value is None:
        return []
    return [value]


def _price(candle: dict[str, Any], field: str) -> float:
    return float(candle[field])


#
# INTERNAL CONTINUATION CONTRACT
#
# Public model:
# - Operators see two public lanes only: rejection and continuation.
# - The historical "Step 2.5" label remains internal engine terminology only.
#
# Continuation eligibility:
# - Continuation becomes eligible after either:
#   1. rejection Step 4 completes, or
#   2. rejection invalidates before Step 4 completes.
# - Eligibility immediately instantiates the continuation owner, establishes the
#   continuation boundary bundle, and begins wick tracking.
# - Eligibility alone does not confirm continuation and does not make the
#   continuation lane controlling.
#
# Boundary contract:
# - extreme_boundary remains the structural continuation extreme.
# - wick_boundary_extreme tracks the farthest continuation wick probe beyond that
#   structural extreme while continuation is eligible or controlling.
# - SHORT continuation ratchets wick_boundary_extreme downward.
# - LONG continuation ratchets wick_boundary_extreme upward.
#
# Continuation confirmation:
# - confirmation_boundary = wick_boundary_extreme if present else extreme_boundary.
# - SHORT continuation confirms on close below the carried confirmation boundary.
# - LONG continuation confirms on close above the carried confirmation boundary.
# - The carried boundary must be consumed before any same-candle wick mutation
#   would move that threshold farther away.
#
# Step 4 handoff:
# - The continuation confirmation / reclaim candle becomes Candle A for
#   continuation Step 4.
# - Step 4 evaluates only on the next candle.
#
# Reference YM replay:
# - 2026-06-24 PMH/LH/ONH structural extreme = 52176.0
# - 06:55 PT: low 52171.0, close 52180.0 -> eligible, wick boundary = 52171.0
# - 06:56 PT: low 52165.0 -> deeper wick boundary = 52165.0
# - 06:57 PT: close 52146.0 consumes the carried 52165.0 boundary and confirms
#   continuation, which then becomes the controlling lane.
#
def continuation_step2_boundary(
    level: float,
    stack_extreme: float | None = None,
    current_boundary: float | None = None,
) -> float:
    """Return the approved Step 2 continuation qualification boundary."""
    if current_boundary is not None:
        return float(current_boundary)
    return float(stack_extreme) if stack_extreme is not None else float(level)


def continuation_step2_close_back_across(
    last_candle: dict[str, Any],
    prev_candle: dict[str, Any],
    level: float,
    level_type: str,
    stack_extreme: float | None = None,
    current_boundary: float | None = None,
    tick_size: float = 0.25,
) -> bool:
    """Return True when the reclaim candle closes beyond the active continuation boundary."""
    normalized_level_type = str(level_type or "").strip().upper()
    boundary = continuation_step2_boundary(level, stack_extreme, current_boundary)
    last_close = _price(last_candle, "close")
    if current_boundary is None:
        if normalized_level_type == "LL":
            return last_close > boundary
        if normalized_level_type == "LH":
            return last_close < boundary
        return False
    if normalized_level_type == "LL":
        return last_close > boundary
    if normalized_level_type == "LH":
        return last_close < boundary
    return False


def continuation_step2_has_true_close_beyond_liquidity(
    last_candle: dict[str, Any],
    prev_candle: dict[str, Any],
    liquidity_boundary: float,
    level_type: str,
) -> bool:
    """Require a real close beyond the active continuation boundary before the reclaim can activate continuation."""
    normalized_level_type = str(level_type or "").strip().upper()
    prior_close = _price(prev_candle, "close")
    last_close = _price(last_candle, "close")
    if normalized_level_type == "LL":
        return prior_close < liquidity_boundary or last_close < liquidity_boundary
    if normalized_level_type == "LH":
        return prior_close > liquidity_boundary or last_close > liquidity_boundary
    return False


def continuation_step2_has_required_reclaim_body(last_candle: dict[str, Any], level_type: str) -> bool:
    """Require continuation reclaim candles to close in the reclaim direction."""
    normalized_level_type = str(level_type or "").strip().upper()
    last_open = _price(last_candle, "open")
    last_close = _price(last_candle, "close")
    if normalized_level_type == "LL":
        return last_close > last_open
    if normalized_level_type == "LH":
        return last_close < last_open
    return False


def select_pathway(
    last_candle: dict[str, Any],
    prev_candle: dict[str, Any],
    level: float,
    level_type: str,
    stack_extreme: float | None = None,
    current_boundary: float | None = None,
    tick_size: float = 0.25,
    active_liquidity_selected: bool = True,
    rejection_step2_confirmed: bool | None = None,
    seeded_from_rejection_step4: bool = False,
) -> dict[str, Any]:
    level_value = float(level)
    normalized_level_type = str(level_type or "").strip().upper()
    rejection_confirmed = active_liquidity_selected if rejection_step2_confirmed is None else bool(rejection_step2_confirmed)
    output = {
        "status": "WAIT",
        "controlling_mode": None,
        "activation_type": None,
        "candle_a": None,
        "provisional_candle_a": None,
        "structure_side_requirement": None,
        "continuation_uses_stack_extreme": stack_extreme is not None,
        "continuation_acceptance_required": False,
        "continuation_acceptance_threshold": None,
        "continuation_step2_activated": False,
        "continuation_rejection_step2_required": True,
    }

    if not active_liquidity_selected or not rejection_confirmed:
        return output

    boundary = continuation_step2_boundary(level_value, stack_extreme, current_boundary)
    if not seeded_from_rejection_step4 and not continuation_step2_has_true_close_beyond_liquidity(last_candle, prev_candle, level_value, normalized_level_type):
        return output
    if not continuation_step2_has_required_reclaim_body(last_candle, normalized_level_type):
        return output
    if normalized_level_type == "LL":
        if continuation_step2_close_back_across(last_candle, prev_candle, level_value, normalized_level_type, stack_extreme, current_boundary, tick_size):
            output.update(
                {
                    "status": "READY",
                    "controlling_mode": SR_MODE,
                    "activation_type": "close",
                    "candle_a": last_candle,
                    "pathway_level": boundary,
                    "structure_side_requirement": "ABOVE_LEVEL",
                    "continuation_step2_activated": True,
                }
            )
            return output

    if normalized_level_type == "LH":
        if continuation_step2_close_back_across(last_candle, prev_candle, level_value, normalized_level_type, stack_extreme, current_boundary, tick_size):
            output.update(
                {
                    "status": "READY",
                    "controlling_mode": RS_MODE,
                    "activation_type": "close",
                    "candle_a": last_candle,
                    "pathway_level": boundary,
                    "structure_side_requirement": "BELOW_LEVEL",
                    "continuation_step2_activated": True,
                }
            )
            return output

    return output


def evaluate_step25(interaction: dict[str, Any]) -> dict[str, Any]:
    """Select the active rejection pathway after Step 2 activates Rejection Mode."""
    state = dict(interaction)
    events = list(state.get("events") or [])

    if state.get("rejection_mode") != "ON":
        state["step25_pathway_selection_complete"] = False
        state["step25_block_reason"] = "Step 2 Continuation requires Rejection Mode = ON."
        reason = state["step25_block_reason"]
        events.append({"event": "step25_waiting_for_rejection_mode", "reason": reason})
        return result("WAIT", state, "Step 2", reason, events)

    initial_candle_a = state.get("initial_candle_a") or state.get("candle_a")
    rejection_step4_conflict = state.get("continuation_step2_conflict_with_rejection_step4") is True
    continuation_eligibility_open = state.get("continuation_eligibility_open") is True
    live_selection = None
    if not rejection_step4_conflict and {"last_candle", "prev_candle", "level", "level_type"}.issubset(state):
        live_selection = select_pathway(
            state["last_candle"],
            state["prev_candle"],
            state["level"],
            state["level_type"],
            state.get("stack_extreme"),
            state.get("current_boundary"),
            float(state.get("tick_size") or 0.25),
            bool(state.get("active_liquidity_selected")),
            bool(state.get("rejection_step2_confirmed")),
            bool(state.get("continuation_seeded_from_rejection_step4")),
        )

    requested_mode = normalize_mode(state.get("controlling_mode") or state.get("pathway_mode"))
    candidate_modes = [normalize_mode(mode) for mode in as_list(state.get("candidate_modes"))]
    candidate_modes = [mode for mode in candidate_modes if mode]

    reclaim_candle_a = state.get("reclaim_candle_a")
    activation_type = state.get("pathway_activation_type")
    if activation_type is not None:
        activation_type = str(activation_type).strip().lower()
    if activation_type == "wick":
        activation_type = None
        state["pathway_activation_type"] = None

    if rejection_step4_conflict:
        controlling_mode = NORMAL_MODE
        candidate_modes = [NORMAL_MODE]
        reclaim_candle_a = None
        activation_type = "normal"
        state["continuation_step2_activated"] = None
        state["step25_block_reason"] = "Reserved Step 4 Candle B has priority; continuation cannot activate on the same candle."
    elif isinstance(live_selection, dict) and live_selection.get("status") == "READY":
        controlling_mode = normalize_mode(live_selection.get("controlling_mode"))
        activation_type = live_selection.get("activation_type")
        state["pathway_level"] = live_selection.get("pathway_level", state.get("level"))
        state["current_boundary"] = live_selection.get("pathway_level", state.get("current_boundary"))
        state["continuation_active_boundary_price"] = live_selection.get("pathway_level", state.get("continuation_active_boundary_price"))
        state["structure_side_requirement"] = live_selection.get("structure_side_requirement")
        state["continuation_uses_stack_extreme"] = live_selection.get("continuation_uses_stack_extreme")
        state["continuation_acceptance_required"] = live_selection.get("continuation_acceptance_required")
        state["continuation_acceptance_threshold"] = live_selection.get("continuation_acceptance_threshold")
        state["continuation_step2_activated"] = live_selection.get("continuation_step2_activated")
        reclaim_candle_a = live_selection.get("candle_a")
        candidate_modes = [controlling_mode] if controlling_mode else []
    elif (
        requested_mode in (SR_MODE, RS_MODE)
        and state.get("continuation_step2_activated") is True
        and activation_type == "close"
        and isinstance(reclaim_candle_a, dict)
    ):
        controlling_mode = requested_mode
    elif (
        state.get("continuation_step2_activated") is True
        and SR_MODE in candidate_modes
        and activation_type == "close"
        and isinstance(reclaim_candle_a, dict)
    ):
        controlling_mode = SR_MODE
    elif (
        state.get("continuation_step2_activated") is True
        and RS_MODE in candidate_modes
        and activation_type == "close"
        and isinstance(reclaim_candle_a, dict)
    ):
        controlling_mode = RS_MODE
    else:
        controlling_mode = NORMAL_MODE

    if (
        continuation_eligibility_open
        and state.get("continuation_eligible_source") == "frozen_rejection_trade_state"
        and controlling_mode == NORMAL_MODE
        and not rejection_step4_conflict
    ):
        state["initial_candle_a"] = initial_candle_a
        state["candidate_modes"] = candidate_modes or [NORMAL_MODE]
        state["controlling_mode"] = None
        state["structure_side_requirement"] = None
        state["reclaim_candle_a"] = None
        state["provisional_candle_a"] = None
        state["pathway_activation_type"] = None
        state["step25_pathway_selection_complete"] = False
        boundary = state.get("continuation_active_boundary_price") or state.get("continuation_reference_boundary_price")
        reason = (
            f"Continuation eligible from frozen rejection trade_state; waiting for a close through "
            f"active continuation boundary {boundary}."
        )
        state["step25_block_reason"] = reason
        events.append({"event": "step25_frozen_rejection_continuation_wait", "reason": reason})
        return result("WAIT", state, "Step 2.5", reason, events)

    if continuation_eligibility_open and controlling_mode == NORMAL_MODE and not rejection_step4_conflict:
        state["initial_candle_a"] = initial_candle_a
        state["candidate_modes"] = candidate_modes or [NORMAL_MODE]
        state["controlling_mode"] = None
        state["structure_side_requirement"] = None
        state["reclaim_candle_a"] = None
        state["provisional_candle_a"] = None
        state["pathway_activation_type"] = None
        state["continuation_acceptance_required"] = bool(state.get("continuation_acceptance_required"))
        state["continuation_acceptance_threshold"] = state.get("continuation_acceptance_threshold")
        state["step25_pathway_selection_complete"] = False
        state["step25_block_reason"] = "Step 2 Continuation is eligible after rejection invalidation; waiting for an independent continuation confirmation candle."
        reason = state["step25_block_reason"]
        events.append({"event": "step25_continuation_eligible_waiting_for_confirmation", "reason": reason})
        return result("WAIT", state, "Step 2.5", reason, events)

    if controlling_mode == NORMAL_MODE:
        if not isinstance(initial_candle_a, dict):
            state["step25_pathway_selection_complete"] = False
            state["step25_block_reason"] = "Normal Rejection Mode requires initial_candle_a from Step 2."
            reason = state["step25_block_reason"]
            events.append({"event": "step25_waiting_for_initial_candle_a", "reason": reason})
            return result("WAIT", state, "Step 2.5", reason, events)
        candidate_modes = [NORMAL_MODE]
        structure_side_requirement = state.get("structure_side_requirement")
    else:
        activation_type = "close"
        if not isinstance(reclaim_candle_a, dict):
            state["step25_pathway_selection_complete"] = False
            state["step25_block_reason"] = f"{controlling_mode} requires a closed Candle A reclaim; wick continuation activation is disabled."
            reason = state["step25_block_reason"]
            events.append({"event": "step25_waiting_for_pathway_candle_a", "reason": reason})
            return result("WAIT", state, "Step 2.5", reason, events)
        if controlling_mode not in candidate_modes:
            candidate_modes.append(controlling_mode)
        structure_side_requirement = state.get("structure_side_requirement")
        if not structure_side_requirement:
            structure_side_requirement = "ABOVE_LEVEL" if controlling_mode == SR_MODE else "BELOW_LEVEL"

    state["initial_candle_a"] = initial_candle_a
    state["candidate_modes"] = candidate_modes
    state["controlling_mode"] = controlling_mode
    state["structure_side_requirement"] = structure_side_requirement
    state["reclaim_candle_a"] = reclaim_candle_a
    state["provisional_candle_a"] = None
    state["pathway_level"] = state.get("pathway_level")
    state["pathway_activation_type"] = activation_type or "normal"
    state["continuation_acceptance_required"] = bool(state.get("continuation_acceptance_required"))
    state["continuation_acceptance_threshold"] = state.get("continuation_acceptance_threshold")
    state["step25_pathway_selection_complete"] = True
    if not rejection_step4_conflict:
        state["step25_block_reason"] = None

    reason = f"Step 2 Continuation pathway selection complete: {controlling_mode}."
    events.append(
        {
            "event": "step25_pathway_selected",
            "reason": reason,
            "controlling_mode": controlling_mode,
            "candidate_modes": candidate_modes,
            "structure_side_requirement": structure_side_requirement,
            "pathway_activation_type": state["pathway_activation_type"],
        }
    )
    return result("READY", state, "Step 3", reason, events)
