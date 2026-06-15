"""Simplified Step 5 Leg 2 confirmation engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from step6_engine import evaluate_entry_models
from step7_engine import terminate_interaction


FINAL_CONFIRMATION_CANDLE_NUMBER = 4


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def result(status: str, state: dict[str, Any], next_step: str, reason: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    return {"step": "Step 5", "status": status, "state": state, "next_step": next_step, "reason": reason, "events": events}


def parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def add_minutes_iso(value: Any, minutes: int) -> str | None:
    parsed = parse_timestamp(value)
    if parsed is None:
        return None
    return (parsed + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def minute_index(start: Any, current: Any) -> int | None:
    start_time = parse_timestamp(start)
    current_time = parse_timestamp(current)
    if start_time is None or current_time is None:
        return None
    return max(0, int((current_time - start_time).total_seconds() // 60))


def seed_step6_window(state: dict[str, Any], candle_time: Any, index: int = 0) -> None:
    started_at = state.get("step6_window_started_at") or candle_time
    state["step6_window_active"] = True
    state["step6_window_started_at"] = started_at
    state["step6_window_candle_index"] = index
    state["step6_window_remaining"] = max(0, FINAL_CONFIRMATION_CANDLE_NUMBER - index)
    state["step6_window_expires_at"] = state.get("step6_window_expires_at") or add_minutes_iso(started_at, FINAL_CONFIRMATION_CANDLE_NUMBER)


def candle_close(candle: dict[str, Any]) -> float | None:
    return as_float(candle.get("close"))


def body_high(candle: dict[str, Any]) -> float | None:
    open_price = as_float(candle.get("open"))
    close = candle_close(candle)
    if open_price is None or close is None:
        return None
    return max(open_price, close)


def body_low(candle: dict[str, Any]) -> float | None:
    open_price = as_float(candle.get("open"))
    close = candle_close(candle)
    if open_price is None or close is None:
        return None
    return min(open_price, close)


def candle_range(candle: dict[str, Any]) -> float | None:
    high = as_float(candle.get("high"))
    low = as_float(candle.get("low"))
    if high is None or low is None:
        return None
    value = high - low
    return value if value > 0 else None


def wick_participation(candle: dict[str, Any], direction: str) -> bool:
    full_range = candle_range(candle)
    high = as_float(candle.get("high"))
    low = as_float(candle.get("low"))
    if full_range is None or high is None or low is None:
        return False
    if direction == "SHORT":
        top_body = body_high(candle)
        wick = high - top_body if top_body is not None else None
    elif direction == "LONG":
        bottom_body = body_low(candle)
        wick = bottom_body - low if bottom_body is not None else None
    else:
        wick = None
    return wick is not None and wick / full_range >= 0.34


def body_opposite_color(candle: dict[str, Any], direction: str) -> bool:
    open_price = as_float(candle.get("open"))
    close = candle_close(candle)
    if open_price is None or close is None:
        return False
    if direction == "SHORT":
        return close < open_price
    if direction == "LONG":
        return close > open_price
    return False


def normalize_mode(mode: Any) -> str:
    value = str(mode or "").strip().upper().replace(" ", "")
    if value in {"S/R", "SR", "S/RPULLBACKCONTINUATION"}:
        return "S/R"
    if value in {"R/S", "RS", "R/SPULLBACKCONTINUATION"}:
        return "R/S"
    return "Normal Rejection Mode"


def update_continuation_acceptance_probe(state: dict[str, Any], candle: dict[str, Any]) -> None:
    if state.get("continuation_acceptance_required") is not True or state.get("continuation_acceptance_confirmed") is True:
        return
    mode = normalize_mode(state.get("controlling_mode"))
    threshold = as_float(state.get("continuation_acceptance_threshold"))
    if mode == "S/R":
        high = as_float(candle.get("high"))
        if high is not None:
            state["continuation_acceptance_threshold"] = max(value for value in (threshold, high) if value is not None)
    elif mode == "R/S":
        low = as_float(candle.get("low"))
        if low is not None:
            state["continuation_acceptance_threshold"] = min(value for value in (threshold, low) if value is not None)


def continuation_acceptance_satisfied(state: dict[str, Any], candle: dict[str, Any]) -> bool:
    if state.get("continuation_acceptance_required") is not True or state.get("continuation_acceptance_confirmed") is True:
        return True
    mode = normalize_mode(state.get("controlling_mode"))
    threshold = as_float(state.get("continuation_acceptance_threshold"))
    close = candle_close(candle)
    if threshold is None or close is None:
        return False
    if mode == "S/R" and close > threshold:
        state["continuation_acceptance_confirmed"] = True
        state["continuation_acceptance_confirmed_at"] = candle.get("timestamp")
        state["continuation_acceptance_source"] = "step5_close_above_threshold"
        return True
    if mode == "R/S" and close < threshold:
        state["continuation_acceptance_confirmed"] = True
        state["continuation_acceptance_confirmed_at"] = candle.get("timestamp")
        state["continuation_acceptance_source"] = "step5_close_below_threshold"
        return True
    return False


def apply_candle_b_reference_upgrade(state: dict[str, Any], direction: str) -> float | None:
    """Deprecated compatibility shim; Step 5 now uses fixed Candle A close."""
    reference = leg1_candle_a_close(state)
    state["active_leg1_reference"] = reference
    state["active_reference"] = reference
    state["leg1_reference_owner"] = "Candle A"
    state["candle_b_reference_upgrade_active"] = False
    return reference


def leg1_candle_a_close(state: dict[str, Any]) -> float | None:
    candle_a = state.get("candle_a")
    if isinstance(candle_a, dict):
        close = as_float(candle_a.get("close"))
        if close is not None:
            return close
    return as_float(state.get("leg1_reference_price") or state.get("leg1_reference"))


def close_beyond_reference(candle: dict[str, Any], reference: float, direction: str, tick_size: float) -> bool:
    close = candle_close(candle)
    if close is None:
        return False
    if direction == "SHORT":
        return close >= reference + tick_size
    if direction == "LONG":
        return close <= reference - tick_size
    return False


def sweeps_anchor_extreme(candle: dict[str, Any], anchor_extreme: float, direction: str, tick_size: float) -> bool:
    if direction == "SHORT":
        high = as_float(candle.get("high"))
        return high is not None and high >= anchor_extreme + tick_size
    if direction == "LONG":
        low = as_float(candle.get("low"))
        return low is not None and low <= anchor_extreme - tick_size
    return False


def closes_through_anchor_extreme(candle: dict[str, Any], anchor_extreme: float, direction: str, tick_size: float) -> bool:
    close = candle_close(candle)
    if close is None:
        return False
    if direction == "SHORT":
        return close >= anchor_extreme + tick_size
    if direction == "LONG":
        return close <= anchor_extreme - tick_size
    return False


def trigger_flag_present(candle: dict[str, Any], state: dict[str, Any]) -> bool:
    for source in (candle, state):
        if not isinstance(source, dict):
            continue
        for field in (
            "step5_entry_trigger",
            "valid_entry_trigger",
            "entry_trigger",
            "double_wick_entry",
            "sweep_entry_condition",
            "step5_participation",
            "opposite_participation",
        ):
            if source.get(field) is True:
                return True
    return False


def step6_trigger_supported(state: dict[str, Any], candle: dict[str, Any], direction: str, tick_size: float) -> tuple[bool, str | None]:
    anchor = state.get("leg2_candle")
    if not isinstance(anchor, dict):
        return False, None
    probe_state = dict(state)
    events: list[dict[str, Any]] = []
    outcome = evaluate_entry_models(probe_state, events, anchor, candle, direction, tick_size)
    if isinstance(outcome, dict) and outcome.get("status") == "ENTRY_CONFIRMED":
        return True, str(outcome.get("reason") or "Existing Step 6 trigger model qualified.")
    return False, None


def valid_participation_or_trigger(state: dict[str, Any], candle: dict[str, Any], direction: str, tick_size: float) -> tuple[bool, str]:
    if trigger_flag_present(candle, state):
        return True, "Explicit valid entry/participation trigger flag present."
    step6_ok, step6_reason = step6_trigger_supported(state, candle, direction, tick_size)
    if step6_ok:
        return True, step6_reason or "Existing Step 6 entry trigger model qualified."
    if body_opposite_color(candle, direction):
        return True, "Opposite-side body participation qualified."
    if wick_participation(candle, direction):
        return True, "34% wick participation qualified."
    return False, "No valid opposite-side participation or entry trigger."


def preconditions_valid(state: dict[str, Any]) -> tuple[bool, str]:
    if state.get("rejection_mode") != "ON":
        return False, "Step 5 requires Rejection Mode = ON."
    if state.get("interaction_state") != "ACTIVE":
        return False, "Step 5 requires Interaction = ACTIVE."
    if state.get("leg1_status") not in {"COMPLETE", "VALID"}:
        return False, "Step 5 requires valid Leg 1."
    if state.get("setup_direction") not in {"LONG", "SHORT"}:
        return False, "Step 5 requires setup_direction LONG or SHORT."
    if as_float(state.get("anchor_extreme")) is None:
        return False, "Step 5 requires Anchor Extreme assigned."
    return True, ""


def lock_leg2_candle_a(state: dict[str, Any], candle: dict[str, Any], reference: float, events: list[dict[str, Any]]) -> dict[str, Any]:
    state["leg2_status"] = "CONFIRMED"
    state["leg2_candle"] = candle
    state["leg2_candle_a"] = candle
    state["leg2_candle_a_time"] = candle.get("timestamp")
    state["active_leg1_reference"] = reference
    state["active_reference"] = reference
    state["active_step5_path"] = "5.1_LOCKED_LEG2"
    state["step5_confirmed"] = True
    state["structure_status"] = "VALID"
    state["step5_confirmation_window_active"] = True
    state["step5_participation_window_active"] = True
    state["step5_confirmation_candle_count"] = 0
    state["step5_participation_candle_count"] = 0
    state["anchor_extreme_swept"] = False
    state["step5_trigger_valid"] = False
    seed_step6_window(state, candle.get("timestamp"), 0)
    reason = "Leg 2 Candle A locked: close beyond fixed Leg 1 Candle A reference; 4-candle confirmation window started."
    events.append({"event": "step5_leg2_candle_a_locked", "reason": reason, "leg1_reference": reference})
    return result("WAIT", state, "Step 5", reason, events)


def validate_confirmation_window(state: dict[str, Any], candle: dict[str, Any], direction: str, tick_size: float, events: list[dict[str, Any]]) -> dict[str, Any]:
    anchor_extreme = as_float(state.get("anchor_extreme"))
    if anchor_extreme is None:
        return terminate_interaction(state, "Step 5", "Step 5 confirmation requires Anchor Extreme.")

    if closes_through_anchor_extreme(candle, anchor_extreme, direction, tick_size):
        state["leg2_status"] = "INVALID"
        state["structure_status"] = "INVALID"
        state["interaction_state"] = "CONSUMED"
        return terminate_interaction(state, "Step 5", "Anchor Extreme close invalidation occurred before Leg 2 validation.")
    if not continuation_acceptance_satisfied(state, candle):
        update_continuation_acceptance_probe(state, candle)
        reason = "Step 5 waiting: provisional continuation requires acceptance close beyond the active wick threshold."
        events.append({"event": "step5_continuation_acceptance_wait", "reason": reason, "threshold": state.get("continuation_acceptance_threshold")})
        return result("WAIT", state, "Step 5", reason, events)

    count = int(state.get("step5_confirmation_candle_count") or state.get("step5_participation_candle_count") or 0) + 1
    state["step5_confirmation_candle_count"] = count
    state["step5_participation_candle_count"] = count
    state["step5_confirmation_timer"] = {
        "active": True,
        "candle_number": count,
        "final_candle_number": FINAL_CONFIRMATION_CANDLE_NUMBER,
    }
    state["step5_participation_timer"] = state["step5_confirmation_timer"]

    swept_now = sweeps_anchor_extreme(candle, anchor_extreme, direction, tick_size)
    state["anchor_extreme_swept"] = bool(state.get("anchor_extreme_swept") or swept_now)
    trigger_ok, trigger_reason = valid_participation_or_trigger(state, candle, direction, tick_size)
    state["step5_trigger_valid"] = bool(state.get("step5_trigger_valid") or trigger_ok)
    if swept_now:
        state["anchor_extreme_sweep_candle"] = candle
    if trigger_ok:
        state["step5_trigger_candle"] = candle
        state["step5_trigger_reason"] = trigger_reason

    if state["anchor_extreme_swept"] and state["step5_trigger_valid"]:
        state["leg2_status"] = "VALIDATED"
        state["two_leg_structure_status"] = "COMPLETE"
        state["structure_status"] = "COMPLETE"
        state["step5_confirmation_window_active"] = False
        state["step5_participation_window_active"] = False
        state["step5_participation_validated"] = True
        state["step6_active"] = True
        index = minute_index(state.get("step6_window_started_at") or state.get("leg2_candle_a_time"), candle.get("timestamp"))
        seed_step6_window(state, state.get("step6_window_started_at") or state.get("leg2_candle_a_time") or candle.get("timestamp"), index if index is not None else count)
        reason = f"Leg 2 validated: Anchor Extreme swept and valid trigger occurred within Candle {count} of 4."
        events.append(
            {
                "event": "step5_leg2_validated",
                "reason": reason,
                "candle_number": count,
                "anchor_extreme_swept": state["anchor_extreme_swept"],
                "trigger_reason": trigger_reason,
            }
        )
        return result("READY", state, "Step 6", reason, events)

    if count >= FINAL_CONFIRMATION_CANDLE_NUMBER:
        state["leg2_status"] = "INVALID"
        state["structure_status"] = "INVALID"
        state["interaction_state"] = "CONSUMED"
        reason = "Leg 2 invalid: 4-candle window expired without Anchor Extreme sweep and valid trigger."
        events.append(
            {
                "event": "step5_leg2_window_expired",
                "reason": reason,
                "anchor_extreme_swept": state["anchor_extreme_swept"],
                "trigger_valid": state["step5_trigger_valid"],
            }
        )
        return terminate_interaction(state, "Step 5", reason)

    reason = (
        f"Step 5 confirmation window Candle {count}: waiting for Anchor Extreme sweep and valid trigger "
        f"(sweep={state['anchor_extreme_swept']}, trigger={state['step5_trigger_valid']})."
    )
    events.append(
        {
            "event": "step5_confirmation_window_wait",
            "reason": reason,
            "candle_number": count,
            "anchor_extreme_swept": state["anchor_extreme_swept"],
            "trigger_valid": state["step5_trigger_valid"],
        }
    )
    return result("WAIT", state, "Step 5", reason, events)


def evaluate_step5(interaction: dict[str, Any], leg2_candle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Confirm Leg 2 with fixed Candle A, 4-candle window, and Anchor Extreme rules."""
    state = dict(interaction)
    events = list(state.get("events") or [])
    candle = leg2_candle or state.get("latest_candle") or state.get("leg2_candle")
    direction = state.get("setup_direction")
    tick_size = as_float(state.get("tick_size")) or 0.25

    ok, reason = preconditions_valid(state)
    if not ok:
        return terminate_interaction(state, "Step 5", reason)
    if not isinstance(candle, dict):
        return terminate_interaction(state, "Step 5", "Step 5 requires a candle.")

    if state.get("leg2_status") == "VALIDATED" or state.get("step5_participation_validated") is True:
        index = minute_index(state.get("step6_window_started_at") or state.get("leg2_candle_a_time"), candle.get("timestamp"))
        if index is not None:
            seed_step6_window(state, state.get("step6_window_started_at") or state.get("leg2_candle_a_time") or candle.get("timestamp"), index)
        reason = "Leg 2 already validated; Step 6 handoff remains active."
        events.append({"event": "step5_already_validated", "reason": reason})
        return result("READY", state, "Step 6", reason, events)

    reference = leg1_candle_a_close(state)
    anchor_extreme = as_float(state.get("anchor_extreme"))
    if reference is None or anchor_extreme is None:
        return terminate_interaction(state, "Step 5", "Step 5 requires fixed Leg 1 Candle A reference and Anchor Extreme.")

    if state.get("step5_confirmed") is True and state.get("leg2_status") == "CONFIRMED":
        return validate_confirmation_window(state, candle, str(direction), tick_size, events)

    if closes_through_anchor_extreme(candle, anchor_extreme, str(direction), tick_size):
        state["leg2_status"] = "INVALID"
        state["structure_status"] = "INVALID"
        state["interaction_state"] = "CONSUMED"
        return terminate_interaction(state, "Step 5", "Anchor Extreme close invalidation occurred before Leg 2 activation.")
    if not continuation_acceptance_satisfied(state, candle):
        update_continuation_acceptance_probe(state, candle)
        reason = "Step 5 waiting: provisional continuation requires acceptance close beyond the active wick threshold."
        events.append({"event": "step5_continuation_acceptance_wait", "reason": reason, "threshold": state.get("continuation_acceptance_threshold")})
        return result("WAIT", state, "Step 5", reason, events)

    if not close_beyond_reference(candle, reference, str(direction), tick_size):
        reason = "Step 5 waiting: Leg 2 Candle A requires close beyond fixed Leg 1 Candle A reference."
        events.append({"event": "step5_waiting_for_leg2_candle_a", "reason": reason, "leg1_reference": reference})
        return result("WAIT", state, "Step 5", reason, events)

    return lock_leg2_candle_a(state, candle, reference, events)
