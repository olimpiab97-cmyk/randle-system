"""Step 4 participation / Leg 1 decision engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from step7_engine import terminate_interaction

FINAL_PARTICIPATION_CANDLE_NUMBER = 4


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def result(status: str, state: dict[str, Any], next_step: str, reason: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    return {"step": "Step 4", "status": status, "state": state, "next_step": next_step, "reason": reason, "events": events}


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


def close_based_participation(candle_a: dict[str, Any], candle_b: dict[str, Any], direction: str) -> bool:
    close_b = as_float(candle_b.get("close"))
    if close_b is None:
        return False
    if direction == "SHORT":
        high_a = as_float(candle_a.get("high"))
        return high_a is not None and close_b <= high_a
    if direction == "LONG":
        low_a = as_float(candle_a.get("low"))
        return low_a is not None and close_b >= low_a
    return False


def wick_participation(candle_b: dict[str, Any], direction: str) -> bool:
    full_range = candle_range(candle_b)
    if full_range is None:
        return False
    high = as_float(candle_b.get("high"))
    low = as_float(candle_b.get("low"))
    if high is None or low is None:
        return False
    if direction == "SHORT":
        top_body = body_high(candle_b)
        wick = high - top_body if top_body is not None else None
    elif direction == "LONG":
        bottom_body = body_low(candle_b)
        wick = bottom_body - low if bottom_body is not None else None
    else:
        wick = None
    return wick is not None and wick / full_range >= 0.34


def leg1_extreme(candle_a: dict[str, Any], candle_b: dict[str, Any], direction: str) -> tuple[float | None, str | None]:
    if direction == "SHORT":
        high_a = as_float(candle_a.get("high"))
        high_b = as_float(candle_b.get("high"))
        if high_a is None or high_b is None:
            return None, None
        return (high_b, "Candle B") if high_b > high_a else (high_a, "Candle A")
    if direction == "LONG":
        low_a = as_float(candle_a.get("low"))
        low_b = as_float(candle_b.get("low"))
        if low_a is None or low_b is None:
            return None, None
        return (low_b, "Candle B") if low_b < low_a else (low_a, "Candle A")
    return None, None


def stack_leg1_extreme_confirmed(state: dict[str, Any], extreme: float | None, direction: str) -> bool:
    """Require static stack Leg 1 to remain beyond the stack extreme boundary."""
    if not state.get("active_stack"):
        return True
    if extreme is None:
        return False
    tick_size = as_float(state.get("tick_size")) or 0.25
    extreme_boundary = as_float(state.get("extreme_boundary"))
    if extreme_boundary is None:
        return False
    if direction == "SHORT":
        return extreme >= extreme_boundary + tick_size
    if direction == "LONG":
        return extreme <= extreme_boundary - tick_size
    return False


def proximity_distance(anchor_extreme: float, opposing_liquidity: dict[str, Any] | None) -> float | None:
    if not isinstance(opposing_liquidity, dict):
        return None
    price = as_float(opposing_liquidity.get("price"))
    if price is None:
        return None
    return abs(anchor_extreme - price)


def leg1_penetration_percent(state: dict[str, Any], extreme: float | None, direction: str) -> float | None:
    """Measure Leg 1 penetration from active liquidity toward the next break-side level."""
    if extreme is None:
        return None
    active_liquidity = state.get("active_liquidity")
    if not isinstance(active_liquidity, dict):
        return None
    active_price = as_float(active_liquidity.get("price"))
    boundary = state.get("next_break_side_liquidity")
    if isinstance(boundary, dict):
        boundary_price = as_float(boundary.get("price"))
    else:
        boundary_price = as_float(boundary)
    if active_price is None or boundary_price is None or boundary_price == active_price:
        return None
    if direction == "SHORT":
        zone = boundary_price - active_price
        penetration = extreme - active_price
    elif direction == "LONG":
        zone = active_price - boundary_price
        penetration = active_price - extreme
    else:
        return None
    if zone <= 0:
        return None
    return max(0.0, penetration / zone * 100.0)


def apply_leg1_50_percent_rule(state: dict[str, Any], extreme: float | None, direction: str) -> bool | None:
    """Store and evaluate the blueprint 50% active-liquidity penetration rule."""
    state["fifty_percent_rule_phase"] = "pre_leg1_only"
    percent = leg1_penetration_percent(state, extreme, direction)
    state["leg1_formed_at_percent"] = percent
    if percent is None:
        state["leg1_50_percent_rule_passed"] = None
        return None
    passed = percent <= 50.0
    state["leg1_50_percent_rule_passed"] = passed
    return passed


def normalize_mode(mode: Any) -> str:
    value = str(mode or "").strip().upper().replace(" ", "")
    if value in {"S/R", "SR", "S/RPULLBACKCONTINUATION"}:
        return "S/R"
    if value in {"R/S", "RS", "R/SPULLBACKCONTINUATION"}:
        return "R/S"
    return "Normal Rejection Mode"


def continuation_acceptance_close_satisfied(state: dict[str, Any], candle: dict[str, Any]) -> bool:
    mode = normalize_mode(state.get("controlling_mode"))
    threshold = as_float(state.get("continuation_acceptance_threshold"))
    close = as_float(candle.get("close"))
    if threshold is None or close is None:
        return False
    if mode == "S/R":
        return close > threshold
    if mode == "R/S":
        return close < threshold
    return False


def update_continuation_acceptance_after_leg1(state: dict[str, Any], candle_b: dict[str, Any], extreme: float | None) -> None:
    if state.get("continuation_acceptance_required") is not True:
        return
    if continuation_acceptance_close_satisfied(state, candle_b):
        state["continuation_acceptance_confirmed"] = True
        state["continuation_acceptance_confirmed_at"] = candle_b.get("timestamp")
        state["continuation_acceptance_source"] = "step4_candle_b_close"
        return
    mode = normalize_mode(state.get("controlling_mode"))
    threshold = as_float(state.get("continuation_acceptance_threshold"))
    if extreme is None:
        return
    if mode == "S/R":
        state["continuation_acceptance_threshold"] = max(value for value in (threshold, extreme) if value is not None)
    elif mode == "R/S":
        state["continuation_acceptance_threshold"] = min(value for value in (threshold, extreme) if value is not None)


def select_final_candle_a(state: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    mode = normalize_mode(state.get("controlling_mode"))
    activation_type = str(state.get("pathway_activation_type") or "normal").strip().lower()
    if mode == "S/R":
        if activation_type == "wick":
            return state.get("provisional_candle_a"), "provisional_candle_a"
        return state.get("reclaim_candle_a"), "reclaim_candle_a"
    if mode == "R/S":
        if activation_type == "wick":
            return state.get("provisional_candle_a"), "provisional_candle_a"
        return state.get("reclaim_candle_a"), "reclaim_candle_a"
    return state.get("initial_candle_a") or state.get("candle_a"), "initial_candle_a"


def side_requirement_violated(state: dict[str, Any], candle: dict[str, Any]) -> str | None:
    if (
        normalize_mode(state.get("controlling_mode")) in {"S/R", "R/S"}
        and state.get("pathway_activation_type") == "wick"
        and state.get("continuation_acceptance_confirmed") is not True
    ):
        return None
    requirement = state.get("structure_side_requirement")
    if requirement not in ("ABOVE_LEVEL", "BELOW_LEVEL"):
        return None
    level = state.get("pathway_level")
    if isinstance(level, dict):
        level_price = as_float(level.get("price"))
    else:
        level_price = as_float(level)
    close = as_float(candle.get("close"))
    if level_price is None or close is None:
        return "Step 4 side enforcement requires pathway_level and Candle B close."
    if requirement == "ABOVE_LEVEL" and close < level_price:
        return "Step 4 blocked: structure_side_requirement ABOVE_LEVEL was violated by Candle B close below pathway_level."
    if requirement == "BELOW_LEVEL" and close > level_price:
        return "Step 4 blocked: structure_side_requirement BELOW_LEVEL was violated by Candle B close above pathway_level."
    return None


def candle_key(candle: dict[str, Any]) -> tuple:
    return (
        candle.get("timestamp"),
        candle.get("open"),
        candle.get("high"),
        candle.get("low"),
        candle.get("close"),
    )


def parse_candle_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_candle_time(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def leg1_window_expires_at(started_at: Any) -> str | None:
    parsed = parse_candle_time(started_at)
    if parsed is None:
        return None
    return format_candle_time(parsed + timedelta(minutes=FINAL_PARTICIPATION_CANDLE_NUMBER - 1))


def apply_leg1_window_fields(
    state: dict[str, Any],
    candle: dict[str, Any],
    candle_index: int,
    *,
    invalidated: bool = False,
    invalidation_reason: str | None = None,
    complete: bool = False,
) -> None:
    started_at = state.get("leg1_window_started_at") or candle.get("timestamp")
    state["leg1_window_started_at"] = started_at
    state["leg1_window_candle_index"] = candle_index
    state["leg1_window_remaining"] = max(0, FINAL_PARTICIPATION_CANDLE_NUMBER - candle_index)
    state["leg1_window_expires_at"] = state.get("leg1_window_expires_at") or leg1_window_expires_at(started_at)
    state["leg1_window_invalidated"] = bool(invalidated)
    state["leg1_window_invalidation_reason"] = invalidation_reason
    state["leg1_window_active"] = not complete and not invalidated and candle_index < FINAL_PARTICIPATION_CANDLE_NUMBER


def register_participation_candidate(state: dict[str, Any], candle: dict[str, Any]) -> int:
    keys = list(state.get("participation_candidate_keys") or [])
    key = candle_key(candle)
    if key not in keys:
        keys.append(key)
    state["participation_candidate_keys"] = keys
    state["participation_candidate_count"] = len(keys)
    state["participation_candle_number"] = len(keys)
    apply_leg1_window_fields(state, candle, len(keys))
    state["participation_timer"] = {
        "active": True,
        "candidate_count": len(keys),
        "candle_number": len(keys),
        "final_candle_number": FINAL_PARTICIPATION_CANDLE_NUMBER,
        "started_at": state.get("leg1_window_started_at"),
        "remaining": state.get("leg1_window_remaining"),
        "expires_at": state.get("leg1_window_expires_at"),
    }
    return len(keys)


def mark_gateway_no_participation(state: dict[str, Any], reason: str) -> None:
    state["level_state"] = "GATEWAY"
    state["liquidity_state"] = "GATEWAY"
    state["opposite_participation"] = "NOT_PRESENT"
    state["step4_block_reason"] = reason
    state["participation_window_failed"] = True
    state["leg1_window_invalidated"] = True
    state["leg1_window_invalidation_reason"] = reason
    state["leg1_window_active"] = False
    state["leg1_window_remaining"] = 0
    state.pop("leg1_status", None)
    state.pop("leg1_reference", None)
    state.pop("leg1_extreme", None)
    state.pop("leg1_extreme_owner", None)
    state.pop("anchor_extreme", None)


def evaluate_step4(interaction: dict[str, Any], candle_b: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build Leg 1 from Candle A + Candle B and route to Step 5 or Step 7."""
    state = dict(interaction)
    events = list(state.get("events") or [])
    direction = state.get("setup_direction")
    candle_a, candle_a_source = select_final_candle_a(state)
    candidate_b = candle_b or state.get("candle_b") or state.get("latest_candle")

    if state.get("rejection_mode") != "ON":
        reason = "Step 4 waiting: Rejection Mode must be ON."
        events.append({"event": "step4_waiting_for_preconditions", "reason": reason})
        return result("WAIT", state, "Step 2", reason, events)
    if state.get("step25_pathway_selection_complete") is not True:
        reason = "Step 4 waiting: Step 2.5 pathway selection is not complete."
        events.append({"event": "step4_waiting_for_preconditions", "reason": reason})
        return result("WAIT", state, "Step 2.5", reason, events)
    if state.get("step3_allows_structure") is not True:
        reason = state.get("step3_block_reason") or "Step 4 waiting: Step 3 has not allowed structure."
        events.append({"event": "step4_waiting_for_preconditions", "reason": reason})
        return result("WAIT", state, "Step 3", reason, events)
    if state.get("interaction_state") != "ACTIVE":
        return terminate_interaction(state, "Step 4", "Step 4 requires Interaction = ACTIVE.")
    if direction not in ("LONG", "SHORT"):
        return terminate_interaction(state, "Step 4", "Step 4 requires setup_direction LONG or SHORT.")
    if not isinstance(candle_a, dict) or not isinstance(candidate_b, dict):
        reason = "Step 4 waiting: final Candle A assignment and Candle B are required."
        events.append({"event": "step4_waiting_for_candles", "reason": reason})
        return result("WAIT", state, "Step 4", reason, events)

    side_violation = side_requirement_violated(state, candidate_b)
    if side_violation:
        return terminate_interaction(state, "Step 4", side_violation)

    candidate_count = register_participation_candidate(state, candidate_b)
    close_pass = close_based_participation(candle_a, candidate_b, direction)
    wick_pass = wick_participation(candidate_b, direction)
    if not (close_pass or wick_pass):
        reason = "Candle B failed both close-based participation and 34% wick-based participation."
        if candidate_count < FINAL_PARTICIPATION_CANDLE_NUMBER:
            events.append(
                {
                    "event": "step4_participation_window_wait",
                    "reason": reason,
                    "candidate_count": candidate_count,
                    "candle_number": candidate_count,
                    "window_label": f"Candle {candidate_count} of {FINAL_PARTICIPATION_CANDLE_NUMBER}",
                    "remaining": state.get("leg1_window_remaining"),
                    "expires_at": state.get("leg1_window_expires_at"),
                    "final_candle_number": FINAL_PARTICIPATION_CANDLE_NUMBER,
                }
            )
            return result("WAIT", state, "Step 4", reason, events)
        mark_gateway_no_participation(state, reason)
        events.append(
            {
                "event": "step4_participation_window_failed",
                "reason": reason,
                "candidate_count": candidate_count,
                "candle_number": candidate_count,
                "window_label": f"Candle {candidate_count} of {FINAL_PARTICIPATION_CANDLE_NUMBER}",
                "level_state": "GATEWAY",
            }
        )
        state["events"] = events
        return terminate_interaction(state, "Step 4", reason)

    extreme, owner = leg1_extreme(candle_a, candidate_b, direction)
    reference = as_float(candle_a.get("close"))
    if extreme is None or owner is None or reference is None:
        return terminate_interaction(state, "Step 4", "Step 4 could not assign Leg 1 reference or extreme from Candle A + Candle B.")
    if not stack_leg1_extreme_confirmed(state, extreme, direction):
        reason = "Step 4 waiting: static stack Leg 1 requires HH/LL beyond the Extreme Boundary; close-boundary Leg 1 is not tradable."
        state["step4_block_reason"] = reason
        state.pop("leg1_status", None)
        events.append({"event": "step4_stack_extreme_required", "reason": reason})
        return result("WAIT", state, "Step 4", reason, events)
    update_continuation_acceptance_after_leg1(state, candidate_b, extreme)
    leg1_50_passed = apply_leg1_50_percent_rule(state, extreme, direction)
    if leg1_50_passed is False:
        reason = "Leg 1 invalid: active liquidity was penetrated beyond 50% before Leg 1 formed."
        state["leg1_status"] = "INVALID"
        state["liquidity_state"] = "CONSUMED"
        state["level_state"] = "CONSUMED"
        state["invalidation_source"] = "leg1_50_percent_rule"
        state["invalidation_source_step"] = "Step 4"
        return terminate_interaction(state, "Step 4", reason)

    state["candle_b"] = candidate_b
    state["candle_a"] = candle_a
    state["candle_a_source"] = candle_a_source
    state["leg1_status"] = "COMPLETE"
    apply_leg1_window_fields(state, candidate_b, candidate_count, complete=True)
    state["leg1_reference"] = reference
    state["leg1_extreme"] = extreme
    state["leg1_extreme_owner"] = owner
    state["anchor_extreme"] = extreme
    state["opposite_participation"] = "PRESENT"
    state["participation_timer"] = {
        **dict(state.get("participation_timer") or {}),
        "active": False,
        "completed": True,
        "remaining": 0,
        "completed_at": candidate_b.get("timestamp"),
    }

    atr = as_float(state.get("atr_1m_14") or state.get("atr"))
    distance = proximity_distance(extreme, state.get("nearest_opposing_liquidity"))
    if atr is None:
        return terminate_interaction(state, "Step 4", "Step 4 proximity filter requires ATR.")
    if distance is None:
        return terminate_interaction(state, "Step 4", "Step 4 proximity filter requires nearest opposing liquidity level.")

    threshold = atr * 0.05
    state["proximity_distance"] = distance
    state["proximity_atr_threshold"] = threshold

    if distance <= threshold:
        reason = "Step 4 proximity filter hard bypass: distance from Anchor Extreme to nearest opposing liquidity is <= 5% ATR."
        return terminate_interaction(state, "Step 4", reason)

    reason = "Leg 1 complete: Candle B participation valid; Anchor Extreme assigned; proximity distance > 5% ATR."
    events.append(
        {
            "event": "step4_leg1_complete",
            "reason": reason,
            "close_based_participation": close_pass,
            "wick_based_participation": wick_pass,
            "leg1_reference": reference,
            "leg1_extreme": extreme,
            "leg1_extreme_owner": owner,
            "anchor_extreme": extreme,
            "candle_a_source": candle_a_source,
            "controlling_mode": state.get("controlling_mode"),
        }
    )
    return result("READY", state, "Step 5", reason, events)
