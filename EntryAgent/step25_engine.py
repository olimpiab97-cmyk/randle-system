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


def select_pathway(
    last_candle: dict[str, Any],
    prev_candle: dict[str, Any],
    level: float,
    level_type: str,
    stack_extreme: float | None = None,
) -> dict[str, Any]:
    level_value = float(stack_extreme) if stack_extreme is not None else float(level)
    wick_level = level_value
    normalized_level_type = str(level_type or "").strip().upper()
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
    }

    if normalized_level_type == "LL":
        if (
            _price(last_candle, "low") < wick_level
            and _price(last_candle, "close") >= level_value
            and _price(last_candle, "close") > _price(last_candle, "open")
        ):
            output.update(
                {
                    "status": "READY",
                    "controlling_mode": SR_MODE,
                    "activation_type": "close",
                    "candle_a": last_candle,
                    "structure_side_requirement": "ABOVE_LEVEL",
                }
            )
            return output

        if _price(prev_candle, "close") < level_value:
            if _price(last_candle, "close") > level_value:
                output.update(
                    {
                        "status": "READY",
                        "controlling_mode": SR_MODE,
                        "activation_type": "close",
                        "candle_a": last_candle,
                        "structure_side_requirement": "ABOVE_LEVEL",
                    }
                )
                return output

            if (
                _price(last_candle, "low") <= wick_level
                and _price(last_candle, "close") <= level_value
                and _price(last_candle, "close") > _price(last_candle, "open")
            ):
                output.update(
                    {
                        "status": "READY",
                        "controlling_mode": SR_MODE,
                        "activation_type": "wick",
                        "provisional_candle_a": last_candle,
                        "structure_side_requirement": "ABOVE_LEVEL",
                        "continuation_acceptance_required": True,
                        "continuation_acceptance_threshold": _price(last_candle, "high"),
                    }
                )
                return output

    if normalized_level_type == "LH":
        if (
            _price(last_candle, "high") > wick_level
            and _price(last_candle, "close") <= level_value
            and _price(last_candle, "close") < _price(last_candle, "open")
        ):
            output.update(
                {
                    "status": "READY",
                    "controlling_mode": RS_MODE,
                    "activation_type": "close",
                    "candle_a": last_candle,
                    "structure_side_requirement": "BELOW_LEVEL",
                }
            )
            return output

        if _price(prev_candle, "close") > level_value:
            if _price(last_candle, "close") < level_value:
                output.update(
                    {
                        "status": "READY",
                        "controlling_mode": RS_MODE,
                        "activation_type": "close",
                        "candle_a": last_candle,
                        "structure_side_requirement": "BELOW_LEVEL",
                    }
                )
                return output

            if (
                _price(last_candle, "high") >= wick_level
                and _price(last_candle, "close") >= level_value
                and _price(last_candle, "close") < _price(last_candle, "open")
            ):
                output.update(
                    {
                        "status": "READY",
                        "controlling_mode": RS_MODE,
                        "activation_type": "wick",
                        "provisional_candle_a": last_candle,
                        "structure_side_requirement": "BELOW_LEVEL",
                        "continuation_acceptance_required": True,
                        "continuation_acceptance_threshold": _price(last_candle, "low"),
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
        )

    requested_mode = normalize_mode(state.get("controlling_mode") or state.get("pathway_mode"))
    candidate_modes = [normalize_mode(mode) for mode in as_list(state.get("candidate_modes"))]
    candidate_modes = [mode for mode in candidate_modes if mode]

    reclaim_candle_a = state.get("reclaim_candle_a")
    provisional_candle_a = state.get("provisional_candle_a")
    activation_type = state.get("pathway_activation_type")
    if activation_type is not None:
        activation_type = str(activation_type).strip().lower()

    if isinstance(live_selection, dict) and live_selection.get("status") == "READY":
        controlling_mode = normalize_mode(live_selection.get("controlling_mode"))
        activation_type = live_selection.get("activation_type")
        state["pathway_level"] = state.get("level")
        state["structure_side_requirement"] = live_selection.get("structure_side_requirement")
        state["continuation_uses_stack_extreme"] = live_selection.get("continuation_uses_stack_extreme")
        state["continuation_acceptance_required"] = live_selection.get("continuation_acceptance_required")
        state["continuation_acceptance_threshold"] = live_selection.get("continuation_acceptance_threshold")
        if activation_type == "wick":
            provisional_candle_a = live_selection.get("provisional_candle_a")
            reclaim_candle_a = None
        else:
            reclaim_candle_a = live_selection.get("candle_a")
            provisional_candle_a = None
        candidate_modes = [controlling_mode] if controlling_mode else []
    elif requested_mode in (SR_MODE, RS_MODE):
        controlling_mode = requested_mode
    elif SR_MODE in candidate_modes and (isinstance(reclaim_candle_a, dict) or isinstance(provisional_candle_a, dict)):
        controlling_mode = SR_MODE
    elif RS_MODE in candidate_modes and (isinstance(reclaim_candle_a, dict) or isinstance(provisional_candle_a, dict)):
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
        candidate_modes = candidate_modes or [NORMAL_MODE]
        structure_side_requirement = state.get("structure_side_requirement")
    else:
        if not activation_type:
            activation_type = "close" if isinstance(reclaim_candle_a, dict) else "wick"
        required_candle = reclaim_candle_a if activation_type == "close" else provisional_candle_a
        if not isinstance(required_candle, dict):
            state["step25_pathway_selection_complete"] = False
            state["step25_block_reason"] = f"{controlling_mode} requires Candle A for {activation_type}-based activation."
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
    state["provisional_candle_a"] = provisional_candle_a
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
