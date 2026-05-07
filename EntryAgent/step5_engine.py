"""Step 5 Leg 2 confirmation decision engine."""

from __future__ import annotations

from typing import Any

from step7_engine import terminate_interaction


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def result(status: str, state: dict[str, Any], next_step: str, reason: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    return {"step": "Step 5", "status": status, "state": state, "next_step": next_step, "reason": reason, "events": events}


def close_beyond_reference(candle: dict[str, Any], reference: float, direction: str, tick_size: float) -> bool:
    close = as_float(candle.get("close"))
    if close is None:
        return False
    if direction == "SHORT":
        return close >= reference + tick_size
    if direction == "LONG":
        return close <= reference - tick_size
    return False


def sweeps_extreme(candle: dict[str, Any], extreme: float, direction: str, tick_size: float) -> bool:
    if direction == "SHORT":
        high = as_float(candle.get("high"))
        return high is not None and high >= extreme + tick_size
    if direction == "LONG":
        low = as_float(candle.get("low"))
        return low is not None and low <= extreme - tick_size
    return False


def closes_beyond_extreme(candle: dict[str, Any], extreme: float, direction: str, tick_size: float) -> bool:
    close = as_float(candle.get("close"))
    if close is None:
        return False
    if direction == "SHORT":
        return close >= extreme + tick_size
    if direction == "LONG":
        return close <= extreme - tick_size
    return False


def closes_against_anchor(candle: dict[str, Any], anchor_extreme: float, direction: str, tick_size: float) -> bool:
    close = as_float(candle.get("close"))
    if close is None:
        return False
    if direction == "SHORT":
        return close <= anchor_extreme - tick_size
    if direction == "LONG":
        return close >= anchor_extreme + tick_size
    return False


def candle_close(candle: dict[str, Any]) -> float | None:
    return as_float(candle.get("close"))


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


def step5_participation_valid(candle: dict[str, Any], direction: str) -> bool:
    if candle.get("step5_participation") is True or candle.get("opposite_participation") is True:
        return True
    return body_opposite_color(candle, direction) or wick_participation(candle, direction)


def liquidity_price(liquidity: Any) -> float | None:
    if isinstance(liquidity, dict):
        return as_float(liquidity.get("price"))
    return as_float(liquidity)


def leg2_proximity_distance(state: dict[str, Any], leg2_candle: dict[str, Any]) -> tuple[float | None, float | None]:
    close = candle_close(leg2_candle)
    nearest = liquidity_price(state.get("nearest_opposing_liquidity") or state.get("nearest_opposing_liquidity_price"))
    atr = as_float(state.get("atr_1m_14") or state.get("atr"))
    if close is None or nearest is None or atr is None:
        return None, None
    return abs(close - nearest), atr * 0.025


def leg2_extension_percent(state: dict[str, Any], candle: dict[str, Any], direction: str) -> float | None:
    """Measure Leg 2 extension beyond Leg 1 extreme as percent of Leg 1 structure."""
    reference = as_float(state.get("active_leg1_reference") or state.get("leg1_reference"))
    extreme = as_float(state.get("leg1_extreme"))
    if reference is None or extreme is None:
        return None
    structure_range = abs(extreme - reference)
    if structure_range <= 0:
        return None
    if direction == "SHORT":
        high = as_float(candle.get("high"))
        if high is None:
            return None
        extension = high - extreme
    elif direction == "LONG":
        low = as_float(candle.get("low"))
        if low is None:
            return None
        extension = extreme - low
    else:
        return None
    return max(0.0, extension / structure_range * 100.0)


def apply_leg2_25_percent_rule(state: dict[str, Any], candle: dict[str, Any], direction: str) -> bool | None:
    """Store and evaluate the blueprint 25% Leg 2 extension rule."""
    percent = leg2_extension_percent(state, candle, direction)
    state["leg2_formed_at_percent"] = percent
    if percent is None:
        state["leg2_25_percent_rule_passed"] = None
        return None
    passed = percent <= 25.0
    state["leg2_25_percent_rule_passed"] = passed
    return passed


def locked_leg1_reference_ready(state: dict[str, Any]) -> bool:
    """Return True only when the current locked Leg 1 snapshot is complete."""
    if state.get("leg1_state_locked") is not True:
        return False
    if state.get("leg1_reference_price") is None and state.get("leg1_reference") is None:
        return False
    if not state.get("leg1_reference_candle_time"):
        return False
    if state.get("leg1_direction") not in ("LONG", "SHORT") and state.get("setup_direction") not in ("LONG", "SHORT"):
        return False
    if not isinstance(state.get("active_liquidity"), dict):
        return False
    if not state.get("leg1_completed_at"):
        return False
    sequence_started_at = state.get("current_active_sequence_started_at")
    if sequence_started_at and str(state.get("leg1_completed_at")) < str(sequence_started_at):
        return False
    return True


def dynamic_stack_boundary_swept(state: dict[str, Any], candle: dict[str, Any], direction: str, tick_size: float) -> bool:
    if state.get("dynamic_stack_active") is not True:
        return True
    boundary = as_float(state.get("next_liquidity_extreme_boundary") or state.get("extreme_boundary"))
    if boundary is None:
        return False
    if direction == "SHORT":
        high = as_float(candle.get("high"))
        return high is not None and high >= boundary + tick_size
    if direction == "LONG":
        low = as_float(candle.get("low"))
        return low is not None and low <= boundary - tick_size
    return False


def opposite_liquidity_break(state: dict[str, Any], candle: dict[str, Any], direction: str, tick_size: float) -> bool:
    if candle.get("opposite_liquidity_break") is True or state.get("opposite_liquidity_break") is True:
        return True
    close = candle_close(candle)
    price = liquidity_price(state.get("opposite_liquidity") or state.get("opposite_liquidity_price"))
    if close is None or price is None:
        return False
    if direction == "SHORT":
        return close <= price - tick_size
    if direction == "LONG":
        return close >= price + tick_size
    return False


def apply_candle_b_reference_upgrade(state: dict[str, Any], direction: str) -> float | None:
    candle_a = state.get("candle_a")
    candle_b = state.get("candle_b")
    reference = as_float(state.get("leg1_reference"))
    if not isinstance(candle_a, dict) or not isinstance(candle_b, dict):
        return reference

    candle_a_close = as_float(candle_a.get("close"))
    candle_b_close = as_float(candle_b.get("close"))
    if candle_a_close is None or candle_b_close is None:
        return reference

    upgraded = False
    if direction == "SHORT":
        candle_b_high = as_float(candle_b.get("high"))
        upgraded = candle_b_high is not None and candle_b_high > candle_a_close
    elif direction == "LONG":
        candle_b_low = as_float(candle_b.get("low"))
        upgraded = candle_b_low is not None and candle_b_low < candle_a_close

    if upgraded:
        state["leg1_reference"] = candle_b_close
        state["active_leg1_reference"] = candle_b_close
        state["active_reference"] = candle_b_close
        state["leg1_reference_owner"] = "Candle B"
        state["candle_b_reference_upgrade_active"] = True
        return candle_b_close

    state["active_leg1_reference"] = reference
    state["active_reference"] = reference
    state["leg1_reference_owner"] = state.get("leg1_reference_owner") or "Candle A"
    state["candle_b_reference_upgrade_active"] = False
    return reference


def wick_probe_threshold(state: dict[str, Any], direction: str) -> float | None:
    if direction == "SHORT":
        return as_float(state.get("probe_high"))
    if direction == "LONG":
        return as_float(state.get("probe_low"))
    return None


def update_wick_probe(state: dict[str, Any], candle: dict[str, Any], direction: str) -> None:
    state["wick_probe_active"] = True
    if direction == "SHORT":
        high = as_float(candle.get("high"))
        current = as_float(state.get("probe_high"))
        if high is not None and (current is None or high > current):
            state["probe_high"] = high
    if direction == "LONG":
        low = as_float(candle.get("low"))
        current = as_float(state.get("probe_low"))
        if low is not None and (current is None or low < current):
            state["probe_low"] = low


def confirm_step5(state: dict[str, Any], candle: dict[str, Any], path: str, reason: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    direction = state.get("setup_direction")
    if state.get("enforce_leg2_25_percent_rule") is True and direction in ("LONG", "SHORT"):
        if not locked_leg1_reference_ready(state):
            state["leg2_status"] = "WAIT"
            state["leg2_formed_at_percent"] = None
            state["leg2_25_percent_rule_passed"] = None
            return result("WAIT", state, "Step 5", "Waiting for valid locked Leg 1 reference", events)
        leg2_25_passed = apply_leg2_25_percent_rule(state, candle, direction)
        if leg2_25_passed is False:
            state["leg2_status"] = "INVALID"
            state["structure_status"] = "INVALID"
            return terminate_interaction(state, "Step 5", "Leg 2 invalid: extension beyond Leg 1 structure exceeded 25%.")
    else:
        state.setdefault("leg2_formed_at_percent", None)
        state.setdefault("leg2_25_percent_rule_passed", None)

    distance, threshold = leg2_proximity_distance(state, candle)
    if distance is None or threshold is None:
        return terminate_interaction(state, "Step 5", "Step 5 post-confirmation proximity filter requires ATR and nearest opposing liquidity.")
    state["step5_proximity_distance"] = distance
    state["step5_proximity_atr_threshold"] = threshold
    if distance <= threshold:
        state["leg2_status"] = "DISQUALIFIED"
        state["structure_status"] = "INVALID"
        return terminate_interaction(state, "Step 5", "Step 5 post-confirmation proximity filter failed: Leg 2 Candle A close is <= 2.5% ATR from nearest opposing liquidity.")

    state["leg2_status"] = "CONFIRMED"
    state["leg2_candle"] = candle
    state["active_step5_path"] = path
    state["step5_confirmed"] = True
    state["structure_status"] = "VALID"
    state["step5_participation_window_active"] = True
    state["step5_participation_candle_count"] = 0
    events.append({"event": "step5_confirmed", "path": path, "reason": reason})
    return result("WAIT", state, "Step 5", reason, events)


def validate_participation_window(state: dict[str, Any], candle: dict[str, Any], direction: str, tick_size: float, events: list[dict[str, Any]]) -> dict[str, Any]:
    anchor_extreme = as_float(state.get("anchor_extreme"))
    if anchor_extreme is None:
        return terminate_interaction(state, "Step 5", "Step 5 participation window requires Anchor Extreme.")
    if closes_against_anchor(candle, anchor_extreme, direction, tick_size):
        return terminate_interaction(state, "Step 5", "Anchor Extreme close invalidation occurred before Step 6 entry.")

    count = int(state.get("step5_participation_candle_count") or 0) + 1
    state["step5_participation_candle_count"] = count
    state["step5_participation_timer"] = {
        "active": True,
        "candle_number": count,
        "final_candle_number": 4,
    }

    if count < 4:
        reason = f"Step 5 participation window Candle {count}: waiting for required Candle 4 participation."
        events.append({"event": "step5_participation_window_wait", "candle_number": count, "reason": reason})
        return result("WAIT", state, "Step 5", reason, events)

    if count > 4:
        return terminate_interaction(state, "Step 5", "Step 5 participation window expired; no late validation allowed.")

    if step5_participation_valid(candle, direction):
        state["leg2_status"] = "VALIDATED"
        state["two_leg_structure_status"] = "COMPLETE"
        state["structure_status"] = "COMPLETE"
        state["step5_participation_window_active"] = False
        state["step5_participation_validated"] = True
        state["step6_active"] = True
        reason = "Step 5 Candle 4 participation validated; 2-Leg Structure complete and Step 6 active."
        events.append({"event": "step5_participation_validated", "candle_number": count, "reason": reason})
        return result("READY", state, "Step 6", reason, events)

    state["leg2_status"] = "INVALID"
    state["structure_status"] = "INVALID"
    state["interaction_state"] = "FAILED"
    return terminate_interaction(state, "Step 5", "Step 5 Candle 4 did not show valid participation; structure invalid.")


def evaluate_step5(interaction: dict[str, Any], leg2_candle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Confirm Leg 2 by strict Step 5 priority order."""
    state = dict(interaction)
    events = list(state.get("events") or [])
    candle = leg2_candle or state.get("leg2_candle") or state.get("latest_candle")
    direction = state.get("setup_direction")
    tick_size = as_float(state.get("tick_size")) or 0.25
    extreme = as_float(state.get("leg1_extreme"))
    anchor_extreme = as_float(state.get("anchor_extreme"))

    if state.get("rejection_mode") != "ON":
        return terminate_interaction(state, "Step 5", "Step 5 requires Rejection Mode = ON.")
    if state.get("interaction_state") != "ACTIVE":
        return terminate_interaction(state, "Step 5", "Step 5 requires Interaction = ACTIVE.")
    if state.get("leg1_status") not in {"COMPLETE", "VALID"}:
        return terminate_interaction(state, "Step 5", "Step 5 requires valid Leg 1.")
    if direction not in ("LONG", "SHORT"):
        return terminate_interaction(state, "Step 5", "Step 5 requires setup_direction LONG or SHORT.")
    if not isinstance(candle, dict):
        return terminate_interaction(state, "Step 5", "Step 5 requires a Leg 2 candidate candle.")
    reference = apply_candle_b_reference_upgrade(state, direction)
    if reference is None or extreme is None or anchor_extreme is None:
        return terminate_interaction(state, "Step 5", "Step 5 requires one active Leg 1 reference, Leg 1 extreme, and Anchor Extreme.")

    if closes_against_anchor(candle, anchor_extreme, direction, tick_size):
        return terminate_interaction(state, "Step 5", "Anchor Extreme close invalidation occurred before Step 6 entry.")

    if state.get("step5_confirmed") is True and state.get("leg2_status") == "CONFIRMED":
        return validate_participation_window(state, candle, direction, tick_size, events)

    # 5.3B Wick Probe Override has highest priority.
    if state.get("wick_probe_active"):
        state["active_step5_path"] = "5.3B"
        threshold = wick_probe_threshold(state, direction)
        if threshold is None:
            return terminate_interaction(state, "Step 5", "Active Wick Probe is missing its probe threshold.")
        if close_beyond_reference(candle, reference, direction, tick_size) and closes_beyond_extreme(candle, threshold, direction, tick_size):
            if not dynamic_stack_boundary_swept(state, candle, direction, tick_size):
                return terminate_interaction(state, "Step 5", "Dynamic Stack Routing active: Leg 2 Candle A did not sweep next liquidity Extreme Boundary.")
            reason = "5.3B Wick Probe Override confirmed: close beyond Leg 1 reference and active probe threshold."
            return confirm_step5(state, candle, "5.3B", reason, events)
        update_wick_probe(state, candle, direction)
        reason = "5.3B Wick Probe Override remains active; Leg 2 has not closed beyond both reference and probe threshold."
        events.append({"event": "step5_wick_probe_wait", "reason": reason})
        return result("WAIT", state, "Step 5", reason, events)

    if sweeps_extreme(candle, extreme, direction, tick_size) and not close_beyond_reference(candle, reference, direction, tick_size):
        if opposite_liquidity_break(state, candle, direction, tick_size):
            state["step9_eligible"] = True
            state["rejection_mode"] = "OFF"
            state["interaction_state"] = "TERMINATED"
            return terminate_interaction(state, "Step 5", "Failed Leg 2 swept extreme without reference close, then broke opposite liquidity; Step 9 may become eligible.")
        update_wick_probe(state, candle, direction)
        state["active_step5_path"] = "5.3B"
        state["failed_leg2_sweep_seen"] = True
        reason = "5.3B Wick Probe Override activated: wick swept Leg 1 extreme without valid Leg 2 close."
        events.append({"event": "step5_wick_probe_activated", "reason": reason})
        return result("WAIT", state, "Step 5", reason, events)

    # 5.3A Candle B Extreme Override is second priority.
    if state.get("leg1_extreme_owner") == "Candle B":
        if closes_beyond_extreme(candle, extreme, direction, tick_size):
            if not dynamic_stack_boundary_swept(state, candle, direction, tick_size):
                return terminate_interaction(state, "Step 5", "Dynamic Stack Routing active: Leg 2 Candle A did not sweep next liquidity Extreme Boundary.")
            reason = "5.3A Candle B Extreme Override confirmed: close beyond Candle B extreme."
            return confirm_step5(state, candle, "5.3A", reason, events)
        return terminate_interaction(state, "Step 5", "5.3A active because Candle B owns Leg 1 extreme, but Leg 2 did not close beyond Candle B extreme.")

    # 5.1 Core Requirement is last priority.
    if close_beyond_reference(candle, reference, direction, tick_size) and sweeps_extreme(candle, extreme, direction, tick_size):
        if not dynamic_stack_boundary_swept(state, candle, direction, tick_size):
            return terminate_interaction(state, "Step 5", "Dynamic Stack Routing active: Leg 2 Candle A did not sweep next liquidity Extreme Boundary.")
        reason = "5.1 Core Requirement confirmed: Leg 2 closed beyond Leg 1 reference and swept Leg 1 extreme."
        return confirm_step5(state, candle, "5.1", reason, events)

    return terminate_interaction(state, "Step 5", "Leg 2 failed active Step 5 confirmation path.")
