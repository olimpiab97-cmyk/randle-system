"""Step 6 entry decision engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from step7_engine import STRUCTURE_FIELDS, terminate_interaction


STEP6_PHASE_WINDOW_CANDLES = 4


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def result(status: str, state: dict[str, Any], next_step: str, reason: str, events: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    payload = {"step": "Step 6", "status": status, "state": state, "next_step": next_step, "reason": reason, "events": events}
    payload.update(extra)
    return payload


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


def candle_timestamp(candle: Any) -> Any:
    return candle.get("timestamp") if isinstance(candle, dict) else None


def update_step6_window(state: dict[str, Any], candidate: dict[str, Any], count: int, *, active: bool = True) -> None:
    started_at = (
        state.get("step6_window_started_at")
        or state.get("leg2_candle_a_time")
        or candle_timestamp(state.get("leg2_candle_a"))
        or candle_timestamp(state.get("leg2_candle"))
        or candle_timestamp(candidate)
    )
    state["step6_window_active"] = active
    state["step6_window_started_at"] = started_at
    state["step6_window_candle_index"] = count
    state["step6_window_remaining"] = max(0, STEP6_PHASE_WINDOW_CANDLES - count)
    state["step6_window_expires_at"] = state.get("step6_window_expires_at") or add_minutes_iso(started_at, STEP6_PHASE_WINDOW_CANDLES)


def carried_phase1_count(state: dict[str, Any]) -> int:
    phase_count = int(state.get("phase1_candle_count") or 0)
    window_count = int(state.get("step6_window_candle_index") or 0)
    return max(phase_count, window_count)


def minute_index(start: Any, current: Any) -> int | None:
    start_time = parse_timestamp(start)
    current_time = parse_timestamp(current)
    if start_time is None or current_time is None:
        return None
    return max(0, int((current_time - start_time).total_seconds() // 60))


def next_phase1_count(state: dict[str, Any], candidate: dict[str, Any]) -> int:
    carried = carried_phase1_count(state)
    elapsed = minute_index(state.get("step6_window_started_at"), candle_timestamp(candidate))
    if elapsed is not None and elapsed > 0:
        return max(carried, elapsed)
    if elapsed is None:
        return carried + 1
    return carried if carried > 0 else 1


def close_step6_window(state: dict[str, Any], candidate: dict[str, Any], count: int = STEP6_PHASE_WINDOW_CANDLES) -> None:
    update_step6_window(state, candidate, count, active=False)
    state["step6_window_candle_index"] = count
    state["step6_window_remaining"] = 0


def body_high(candle: dict[str, Any]) -> float | None:
    open_price = as_float(candle.get("open"))
    close = as_float(candle.get("close"))
    if open_price is None or close is None:
        return None
    return max(open_price, close)


def body_low(candle: dict[str, Any]) -> float | None:
    open_price = as_float(candle.get("open"))
    close = as_float(candle.get("close"))
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


def sc_wick(candle: dict[str, Any], direction: str) -> float | None:
    high = as_float(candle.get("high"))
    low = as_float(candle.get("low"))
    if high is None or low is None:
        return None
    if direction == "SHORT":
        top_body = body_high(candle)
        return high - top_body if top_body is not None else None
    if direction == "LONG":
        bottom_body = body_low(candle)
        return bottom_body - low if bottom_body is not None else None
    return None


def sc_decision_pass(sc: dict[str, Any], direction: str) -> dict[str, Any] | None:
    full_range = candle_range(sc)
    wick = sc_wick(sc, direction)
    if full_range is None or wick is None:
        return None
    wick_percent = wick / full_range
    large = wick_percent >= 0.20
    return {
        "wick_percent": wick_percent,
        "sweep_entry_path": "Large Wick" if large else "Small Wick",
        "double_wick_state": "ACTIVE" if large else "ELIMINATED",
    }


def sweep_extreme(entry_candle: dict[str, Any], sc: dict[str, Any], direction: str, tick_size: float) -> bool:
    if direction == "SHORT":
        entry_high = as_float(entry_candle.get("high"))
        sc_high = as_float(sc.get("high"))
        return entry_high is not None and sc_high is not None and entry_high >= sc_high + tick_size
    if direction == "LONG":
        entry_low = as_float(entry_candle.get("low"))
        sc_low = as_float(sc.get("low"))
        return entry_low is not None and sc_low is not None and entry_low <= sc_low - tick_size
    return False


def large_wick_reclaim_level(sc: dict[str, Any], direction: str) -> float | None:
    wick = sc_wick(sc, direction)
    high = as_float(sc.get("high"))
    low = as_float(sc.get("low"))
    if wick is None or high is None or low is None:
        return None
    if direction == "SHORT":
        return high - (wick * 0.60)
    if direction == "LONG":
        return low + (wick * 0.60)
    return None


def close_reclaims(entry_candle: dict[str, Any], level: float, direction: str, tick_size: float) -> bool:
    close = as_float(entry_candle.get("close"))
    if close is None:
        return False
    if direction == "SHORT":
        return close <= level - tick_size
    if direction == "LONG":
        return close >= level + tick_size
    return False


def evaluate_large_wick_sweep(sc: dict[str, Any], entry_candle: dict[str, Any], direction: str, tick_size: float) -> tuple[bool, float | None, str]:
    reclaim_level = large_wick_reclaim_level(sc, direction)
    if reclaim_level is None:
        return False, None, "Large Wick Sweep requires SC wick measurement."
    if sweep_extreme(entry_candle, sc, direction, tick_size) and close_reclaims(entry_candle, reclaim_level, direction, tick_size):
        return True, reclaim_level, "Large Wick Sweep triggered: SC extreme swept by 1 tick and 60% wick reclaim exceeded by 1 tick."
    return False, None, "Large Wick Sweep did not trigger."


def small_wick_body_level(sc: dict[str, Any], direction: str) -> float | None:
    if direction == "SHORT":
        return body_high(sc)
    if direction == "LONG":
        return body_low(sc)
    return None


def evaluate_small_wick_sweep(sc: dict[str, Any], entry_candle: dict[str, Any], direction: str, tick_size: float) -> tuple[bool, float | None, str]:
    body_level = small_wick_body_level(sc, direction)
    if body_level is None:
        return False, None, "Small Wick Sweep requires SC body level."
    if sweep_extreme(entry_candle, sc, direction, tick_size) and close_reclaims(entry_candle, body_level, direction, tick_size):
        return True, body_level, "Small Wick Sweep triggered: SC extreme swept by 1 tick and SC body level reclaimed by 1 tick."
    return False, None, "Small Wick Sweep did not trigger."


def evaluate_double_wick(sc: dict[str, Any], entry_candle: dict[str, Any], direction: str, tick_size: float) -> tuple[bool, float | None, str]:
    wick = sc_wick(sc, direction)
    if wick is None:
        return False, None, "Double Wick requires SC wick measurement."
    if direction == "SHORT":
        top_body = body_high(sc)
        entry_high = as_float(entry_candle.get("high"))
        reclaim = top_body
        penetrated = entry_high is not None and top_body is not None and entry_high >= top_body + (wick * 0.50)
    elif direction == "LONG":
        bottom_body = body_low(sc)
        entry_low = as_float(entry_candle.get("low"))
        reclaim = bottom_body
        penetrated = entry_low is not None and bottom_body is not None and entry_low <= bottom_body - (wick * 0.50)
    else:
        reclaim = None
        penetrated = False
    if reclaim is not None and penetrated and close_reclaims(entry_candle, reclaim, direction, tick_size):
        return True, reclaim, "Double Wick Rejection triggered: entry penetrated 50% of SC wick and reclaimed opposite side."
    return False, None, "Double Wick Rejection did not trigger."


def close_beyond_sc_close(candle: dict[str, Any], sc: dict[str, Any], direction: str, tick_size: float) -> bool:
    close = as_float(candle.get("close"))
    sc_close = as_float(sc.get("close"))
    if close is None or sc_close is None:
        return False
    if direction == "LONG":
        return close >= sc_close + tick_size
    if direction == "SHORT":
        return close <= sc_close - tick_size
    return False


def is_continuation_mode(mode: Any) -> bool:
    normalized = str(mode or "").strip().upper().replace(" ", "")
    return normalized in {"S/R", "SR", "R/S", "RS"}


def required_leg_in_liquidity_swept(state: dict[str, Any]) -> bool:
    for field in (
        "required_leg_in_liquidity_swept",
        "required_liquidity_swept",
        "leg_in_liquidity_swept",
    ):
        if state.get(field) is True:
            return True
    return False


def required_leg_in_liquidity_gate_active(state: dict[str, Any]) -> bool:
    # Step 6 only consumes these flags. Step 5 / setup qualification must produce them
    # before live 6.3X gating can activate.
    if not is_continuation_mode(state.get("controlling_mode")):
        return False
    if state.get("required_leg_in_liquidity_exists") is not True:
        return False
    return not required_leg_in_liquidity_swept(state)


def close_beyond_anchor_extreme(candle: dict[str, Any], direction: str, anchor_extreme: Any) -> bool:
    close = as_float(candle.get("close"))
    anchor = as_float(anchor_extreme)
    if close is None or anchor is None:
        return False
    if direction == "SHORT":
        return close > anchor
    if direction == "LONG":
        return close < anchor
    return False


def transfer_to_opposing_setup(state: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    for field in STRUCTURE_FIELDS:
        state[field] = None
    state["original_setup_status"] = "INVALID"
    state["original_structures_discarded"] = True
    state["control_transferred_to_opposing_setup"] = True
    state["active_setup"] = "opposing"
    state["current_sc"] = None
    state["sc"] = None
    state["sc2"] = None
    state["sc3"] = None
    state["sc_progression_count"] = None
    state["entry_triggered"] = False
    state["interaction_state"] = "ACTIVE"
    reason = "Opposing setup completed Leg 1 before current Step 6 entry triggered; control transferred to opposing setup."
    events.append({"event": "step6_opposing_setup_override", "reason": reason})
    return result("WAIT", state, "Step 4", reason, events)


def entry_confirmed(state: dict[str, Any], events: list[dict[str, Any]], entry_type: str, entry_price: float, reason: str) -> dict[str, Any]:
    state["entry_triggered"] = True
    state["entry_model_triggered"] = entry_type
    state["entry_price"] = entry_price
    state["entry_time"] = (state.get("latest_candle") or {}).get("timestamp")
    state["structure_locked"] = True
    state["interaction_state"] = "CONSUMED"
    state["rejection_mode"] = "OFF"
    state["trade_mode"] = "OFF"
    state["structure_status"] = "LOCKED"
    events.append({"event": "step6_entry_confirmed", "entry_type": entry_type, "entry_price": entry_price, "reason": reason})
    return result(
        "ENTRY_CONFIRMED",
        state,
        "Step 10",
        reason,
        events,
        entry_type=entry_type,
        entry_price=entry_price,
        active_step5_path=state.get("active_step5_path"),
    )


def active_anchor_state(state: dict[str, Any]) -> dict[str, Any] | None:
    phase = state.get("step6_phase") or "PHASE1"
    if phase == "PHASE2":
        anchor = state.get("phase2_active_a")
        return anchor if isinstance(anchor, dict) else None
    anchor = state.get("phase1_anchor") or state.get("leg2_candle")
    if isinstance(anchor, dict):
        state["phase1_anchor"] = anchor
        state["sc"] = anchor
        state["current_sc"] = anchor
        return anchor
    return None


def evaluate_entry_models(
    state: dict[str, Any],
    events: list[dict[str, Any]],
    anchor: dict[str, Any],
    candidate: dict[str, Any],
    direction: str,
    tick_size: float,
) -> dict[str, Any] | None:
    decision = sc_decision_pass(anchor, direction)
    if decision is None:
        return terminate_interaction(state, "Step 6", "Active anchor Decision Pass could not be computed.")
    state["active_entry_anchor"] = anchor
    state["sc_decision_pass_output"] = decision
    state["sweep_entry_path"] = decision["sweep_entry_path"]
    state["double_wick_state"] = decision["double_wick_state"]

    if decision["sweep_entry_path"] == "Large Wick":
        ok, price, reason = evaluate_large_wick_sweep(anchor, candidate, direction, tick_size)
        if ok and price is not None:
            return entry_confirmed(state, events, "Large Wick Sweep", price, reason)
    else:
        ok, price, reason = evaluate_small_wick_sweep(anchor, candidate, direction, tick_size)
        if ok and price is not None:
            return entry_confirmed(state, events, "Small Wick Sweep", price, reason)

    if decision["double_wick_state"] == "ACTIVE":
        ok, price, reason = evaluate_double_wick(anchor, candidate, direction, tick_size)
        if ok and price is not None:
            return entry_confirmed(state, events, "Double Wick Rejection", price, reason)
    return None


def failed_entry_participation_exists(state: dict[str, Any], candidate: dict[str, Any]) -> bool:
    for source in (candidate, state):
        for field in (
            "failed_entry_participation",
            "opposite_participation",
            "failed_entry_opposite_participation",
            "phase2_activation",
        ):
            if isinstance(source, dict) and source.get(field) is True:
                return True
    return False


def wait_for_required_leg_in_liquidity_sweep(state: dict[str, Any], events: list[dict[str, Any]], reason: str) -> dict[str, Any]:
    state["entry_triggered"] = False
    state["interaction_state"] = "ACTIVE"
    state["structure_status"] = state.get("structure_status") or "VALID"
    state["structure_valid"] = state.get("structure_valid", True)
    events.append({"event": "step6_required_leg_in_liquidity_gate_wait", "reason": reason})
    return result("WAIT", state, "Step 6", reason, events)


def activate_phase2(state: dict[str, Any], events: list[dict[str, Any]], candidate: dict[str, Any]) -> dict[str, Any]:
    state["step6_phase"] = "PHASE2"
    state["phase1_failed"] = True
    state["phase2_active"] = True
    state["phase2_attempt_used"] = True
    state["phase2_candle_count"] = 0
    state["phase2_failed_entry_candle"] = candidate
    state["phase2_active_a"] = None
    state["phase2_active_a_candle_number"] = None
    reason = "Phase 1 failed on Candle 4; failed-entry participation activated Phase 2 rolling A/B window."
    events.append({"event": "step6_phase2_activated", "reason": reason})
    return result("WAIT", state, "Step 6", reason, events)


def phase2_new_a(candidate: dict[str, Any], active_a: dict[str, Any] | None, direction: str) -> bool:
    if direction == "SHORT":
        high = as_float(candidate.get("high"))
        active_high = as_float(active_a.get("high")) if isinstance(active_a, dict) else None
        return high is not None and (active_high is None or high > active_high)
    if direction == "LONG":
        low = as_float(candidate.get("low"))
        active_low = as_float(active_a.get("low")) if isinstance(active_a, dict) else None
        return low is not None and (active_low is None or low < active_low)
    return False


def evaluate_phase1(state: dict[str, Any], events: list[dict[str, Any]], candidate: dict[str, Any], direction: str, tick_size: float) -> dict[str, Any]:
    anchor = active_anchor_state(state)
    if not isinstance(anchor, dict):
        return terminate_interaction(state, "Step 6", "Step 6 requires Leg 2 Candle A as Phase 1 anchor.")

    count = next_phase1_count(state, candidate)
    state["step6_phase"] = "PHASE1"
    state["phase1_candle_count"] = count
    update_step6_window(state, candidate, count)

    if count < 4:
        reason = f"Phase 1 Candle {count}: entry blocked until required Candle 4."
        events.append({"event": "step6_phase1_wait", "phase1_candle_count": count, "reason": reason})
        return result("WAIT", state, "Step 6", reason, events)

    if count > 4:
        close_step6_window(state, candidate, count)
        return terminate_interaction(state, "Step 6", "Phase 1 timing expired; no late entry after Candle 4.")

    if required_leg_in_liquidity_gate_active(state):
        close_step6_window(state, candidate)
        return terminate_interaction(state, "Step 6", "Required leg-in liquidity gate blocked entry until Phase 1 timing expired.")

    entry = evaluate_entry_models(state, events, anchor, candidate, direction, tick_size)
    if entry is not None:
        return entry

    if failed_entry_participation_exists(state, candidate) and state.get("phase2_attempt_used") is not True:
        return activate_phase2(state, events, candidate)

    close_step6_window(state, candidate)
    return terminate_interaction(state, "Step 6", "Phase 1 failed on Candle 4 with no valid Phase 2 failed-entry participation.")


def evaluate_phase2(state: dict[str, Any], events: list[dict[str, Any]], candidate: dict[str, Any], direction: str, tick_size: float) -> dict[str, Any]:
    count = int(state.get("phase2_candle_count") or 0) + 1
    state["step6_phase"] = "PHASE2"
    state["phase2_candle_count"] = count
    if count > 4:
        return terminate_interaction(state, "Step 6", "Phase 2 timing expired; no late entries.")

    active_a = state.get("phase2_active_a")
    if not isinstance(active_a, dict) and phase2_new_a(candidate, None, direction):
        state["phase2_active_a"] = candidate
        state["phase2_active_a_candle_number"] = count
        state["active_entry_anchor"] = candidate
        reason = f"Phase 2 Candle {count}: new rolling A replaced prior active anchor."
        events.append({"event": "step6_phase2_new_a", "phase2_candle_count": count, "reason": reason})
        if count >= 4:
            return terminate_interaction(state, "Step 6", "Phase 2 Candle 4 became A only; no valid B entry occurred.")
        return result("WAIT", state, "Step 6", reason, events)

    active_a = state.get("phase2_active_a")
    if not isinstance(active_a, dict):
        reason = f"Phase 2 Candle {count}: waiting for rolling A."
        events.append({"event": "step6_phase2_waiting_for_a", "phase2_candle_count": count, "reason": reason})
        if count >= 4:
            return terminate_interaction(state, "Step 6", "Phase 2 expired without a valid A/B entry.")
        return result("WAIT", state, "Step 6", reason, events)

    if required_leg_in_liquidity_gate_active(state):
        if count >= 4:
            return terminate_interaction(state, "Step 6", "Required leg-in liquidity gate blocked entry until Phase 2 timing expired.")
        return wait_for_required_leg_in_liquidity_sweep(
            state,
            events,
            f"Phase 2 Candle {count}: required leg-in liquidity sweep gate active; entry evaluation blocked while timing continues.",
        )

    entry = evaluate_entry_models(state, events, active_a, candidate, direction, tick_size)
    if entry is not None:
        state["phase2_b_candle"] = candidate
        state["phase2_b_candle_number"] = count
        return entry

    if phase2_new_a(candidate, active_a, direction):
        state["phase2_active_a"] = candidate
        state["phase2_active_a_candle_number"] = count
        state["active_entry_anchor"] = candidate
        reason = f"Phase 2 Candle {count}: new rolling A replaced prior active anchor."
        events.append({"event": "step6_phase2_new_a", "phase2_candle_count": count, "reason": reason})
        if count >= 4:
            return terminate_interaction(state, "Step 6", "Phase 2 Candle 4 became A only; no valid B entry occurred.")
        return result("WAIT", state, "Step 6", reason, events)

    if count >= 4:
        return terminate_interaction(state, "Step 6", "Phase 2 expired without a valid B entry by Candle 4.")

    reason = f"Phase 2 Candle {count}: no valid B entry against active rolling A."
    events.append({"event": "step6_phase2_waiting_for_b", "phase2_candle_count": count, "reason": reason})
    return result("WAIT", state, "Step 6", reason, events)


def evaluate_step6(interaction: dict[str, Any], entry_candle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Evaluate Step 6 entry models without live order execution."""
    state = dict(interaction)
    events = list(state.get("events") or [])
    direction = state.get("setup_direction")
    tick_size = as_float(state.get("tick_size")) or 0.25
    candidate = entry_candle or state.get("entry_candle") or state.get("latest_candle")

    if state.get("step5_confirmed") is not True:
        return terminate_interaction(state, "Step 6", "Step 6 requires confirmed Step 5 structure.")
    if direction not in ("LONG", "SHORT"):
        return terminate_interaction(state, "Step 6", "Step 6 requires setup_direction LONG or SHORT.")
    if not isinstance(candidate, dict):
        return terminate_interaction(state, "Step 6", "Step 6 requires an entry candidate candle.")
    if state.get("entry_triggered") is True:
        return terminate_interaction(state, "Step 6", "Step 6 allows only one entry per interaction.")

    if state.get("opposing_setup_leg1_complete") is True:
        return transfer_to_opposing_setup(state, events)

    if close_beyond_anchor_extreme(candidate, direction, state.get("anchor_extreme")):
        count = next_phase1_count(state, candidate)
        state["step6_phase"] = state.get("step6_phase") or "PHASE1"
        state["phase1_candle_count"] = count
        close_step6_window(state, candidate, count)
        return terminate_interaction(state, "Step 6", "Price closed beyond Anchor Extreme before entry.")

    phase = state.get("step6_phase") or "PHASE1"
    if phase == "PHASE2" or state.get("phase2_active") is True:
        return evaluate_phase2(state, events, candidate, direction, tick_size)
    return evaluate_phase1(state, events, candidate, direction, tick_size)
