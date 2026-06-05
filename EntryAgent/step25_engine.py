"""Step 2.5 rejection pathway selector."""

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


def _optional_price(candle: dict[str, Any], field: str) -> float | None:
    try:
        value = candle.get(field)
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def continuation_step2_boundary(level: float, stack_extreme: float | None = None) -> float:
    """Return the approved Step 2 continuation qualification boundary."""
    return float(stack_extreme) if stack_extreme is not None else float(level)


def active_continuation_boundary(
    level: float,
    stack_extreme: float | None = None,
    continuation_probe_boundary: dict[str, Any] | None = None,
) -> tuple[float, bool]:
    probe = continuation_probe_boundary if isinstance(continuation_probe_boundary, dict) else {}
    if probe.get("active") is True and probe.get("boundary_price") is not None:
        return float(probe["boundary_price"]), True
    return continuation_step2_boundary(level, stack_extreme), False


def continuation_step2_close_back_across(
    last_candle: dict[str, Any],
    prev_candle: dict[str, Any],
    level: float,
    level_type: str,
    stack_extreme: float | None = None,
    continuation_probe_boundary: dict[str, Any] | None = None,
) -> bool:
    """Return True when the completed close is beyond the continuation boundary."""
    normalized_level_type = str(level_type or "").strip().upper()
    boundary, _used_probe = active_continuation_boundary(level, stack_extreme, continuation_probe_boundary)
    last_close = _price(last_candle, "close")
    if normalized_level_type == "LL":
        return last_close > boundary
    if normalized_level_type == "LH":
        return last_close < boundary
    return False


def continuation_probe_side(level_type: str) -> str | None:
    normalized_level_type = str(level_type or "").strip().upper()
    if normalized_level_type == "LL":
        return "upper"
    if normalized_level_type == "LH":
        return "lower"
    return None


def updated_continuation_probe_boundary(
    *,
    last_candle: dict[str, Any],
    level: float,
    level_type: str,
    stack_extreme: float | None = None,
    continuation_probe_boundary: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    side = continuation_probe_side(level_type)
    if side is None:
        return continuation_probe_boundary, None
    boundary, used_existing_probe = active_continuation_boundary(level, stack_extreme, continuation_probe_boundary)
    close = _optional_price(last_candle, "close")
    high = _optional_price(last_candle, "high")
    low = _optional_price(last_candle, "low")
    if close is None:
        return continuation_probe_boundary, None

    probe_extreme = None
    if side == "upper" and high is not None and high > boundary and close <= boundary:
        probe_extreme = high
    elif side == "lower" and low is not None and low < boundary and close >= boundary:
        probe_extreme = low
    if probe_extreme is None:
        return continuation_probe_boundary, None

    prior = continuation_probe_boundary if isinstance(continuation_probe_boundary, dict) else {}
    event_name = "continuation_probe_updated" if used_existing_probe else "continuation_probe_detected"
    timestamp = last_candle.get("timestamp") or last_candle.get("time")
    probe = {
        "active": True,
        "side": side,
        "level_type": str(level_type or "").strip().upper(),
        "boundary_price": probe_extreme,
        "source": "wick",
        "detected_at": prior.get("detected_at") or timestamp,
        "updated_at": timestamp,
    }
    return probe, {
        "event": event_name,
        "side": side,
        "boundary_price": probe_extreme,
        "timestamp": timestamp,
    }


def select_pathway(
    last_candle: dict[str, Any],
    prev_candle: dict[str, Any],
    level: float,
    level_type: str,
    stack_extreme: float | None = None,
    active_liquidity_selected: bool = True,
    rejection_step2_confirmed: bool | None = None,
    continuation_probe_boundary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    level_value = float(level)
    normalized_level_type = str(level_type or "").strip().upper()
    rejection_confirmed = active_liquidity_selected if rejection_step2_confirmed is None else bool(rejection_step2_confirmed)
    boundary, used_probe = active_continuation_boundary(level_value, stack_extreme, continuation_probe_boundary)
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
        "continuation_probe_boundary": continuation_probe_boundary if isinstance(continuation_probe_boundary, dict) else None,
        "continuation_activation_boundary": boundary,
        "continuation_activation_source": "probe" if used_probe else "level",
    }

    if not active_liquidity_selected or not rejection_confirmed:
        return output

    if normalized_level_type == "LL":
        if continuation_step2_close_back_across(last_candle, prev_candle, level_value, normalized_level_type, stack_extreme, continuation_probe_boundary):
            output.update(
                {
                    "status": "READY",
                    "controlling_mode": SR_MODE,
                    "activation_type": "close",
                    "candle_a": last_candle,
                    "pathway_level": boundary,
                    "structure_side_requirement": "ABOVE_LEVEL",
                    "continuation_step2_activated": True,
                    "continuation_probe_boundary": {
                        **continuation_probe_boundary,
                        "active": False,
                    } if isinstance(continuation_probe_boundary, dict) else None,
                }
            )
            return output

    if normalized_level_type == "LH":
        if continuation_step2_close_back_across(last_candle, prev_candle, level_value, normalized_level_type, stack_extreme, continuation_probe_boundary):
            output.update(
                {
                    "status": "READY",
                    "controlling_mode": RS_MODE,
                    "activation_type": "close",
                    "candle_a": last_candle,
                    "pathway_level": boundary,
                    "structure_side_requirement": "BELOW_LEVEL",
                    "continuation_step2_activated": True,
                    "continuation_probe_boundary": {
                        **continuation_probe_boundary,
                        "active": False,
                    } if isinstance(continuation_probe_boundary, dict) else None,
                }
            )
            return output

    probe, event = updated_continuation_probe_boundary(
        last_candle=last_candle,
        level=level_value,
        level_type=normalized_level_type,
        stack_extreme=stack_extreme,
        continuation_probe_boundary=continuation_probe_boundary,
    )
    output["continuation_probe_boundary"] = probe if isinstance(probe, dict) else None
    if isinstance(event, dict):
        output["continuation_probe_event"] = event
    return output


def evaluate_step25(interaction: dict[str, Any]) -> dict[str, Any]:
    """Select the active rejection pathway after Step 2 activates Rejection Mode."""
    state = dict(interaction)
    events = list(state.get("events") or [])

    if state.get("rejection_mode") != "ON":
        state["step25_pathway_selection_complete"] = False
        state["step25_block_reason"] = "Step 2.5 requires Rejection Mode = ON."
        reason = state["step25_block_reason"]
        events.append({"event": "step25_waiting_for_rejection_mode", "reason": reason})
        return result("WAIT", state, "Step 2", reason, events)

    initial_candle_a = state.get("initial_candle_a") or state.get("candle_a")
    live_selection = None
    if {"last_candle", "prev_candle", "level", "level_type"}.issubset(state):
        live_selection = select_pathway(
            state["last_candle"],
            state["prev_candle"],
            state["level"],
            state["level_type"],
            state.get("stack_extreme"),
            bool(state.get("active_liquidity_selected")),
            bool(state.get("rejection_step2_confirmed")),
            state.get("continuation_probe_boundary") if isinstance(state.get("continuation_probe_boundary"), dict) else None,
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

    if isinstance(live_selection, dict) and live_selection.get("status") == "READY":
        controlling_mode = normalize_mode(live_selection.get("controlling_mode"))
        activation_type = live_selection.get("activation_type")
        state["pathway_level"] = live_selection.get("pathway_level", state.get("level"))
        state["structure_side_requirement"] = live_selection.get("structure_side_requirement")
        state["continuation_uses_stack_extreme"] = live_selection.get("continuation_uses_stack_extreme")
        state["continuation_acceptance_required"] = live_selection.get("continuation_acceptance_required")
        state["continuation_acceptance_threshold"] = live_selection.get("continuation_acceptance_threshold")
        state["continuation_step2_activated"] = live_selection.get("continuation_step2_activated")
        state["continuation_probe_boundary"] = live_selection.get("continuation_probe_boundary")
        state["continuation_activation_boundary"] = live_selection.get("continuation_activation_boundary")
        state["continuation_activation_source"] = live_selection.get("continuation_activation_source")
        reclaim_candle_a = live_selection.get("candle_a")
        candidate_modes = [controlling_mode] if controlling_mode else []
    elif isinstance(live_selection, dict):
        state["continuation_probe_boundary"] = live_selection.get("continuation_probe_boundary")
        state["continuation_activation_boundary"] = live_selection.get("continuation_activation_boundary")
        state["continuation_activation_source"] = live_selection.get("continuation_activation_source")
        if isinstance(live_selection.get("continuation_probe_event"), dict):
            events.append(live_selection["continuation_probe_event"])
        controlling_mode = NORMAL_MODE
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
    state["step25_block_reason"] = None

    reason = f"Step 2.5 pathway selection complete: {controlling_mode}."
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
