"""Step 4 participation / Leg 1 decision engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from step7_engine import terminate_interaction

FINAL_PARTICIPATION_CANDLE_NUMBER = 4
LEG1_WINDOW_INVALIDATION_REASON = "Step 4 invalid: no valid participation formed within 4 candles after Step 2 confirmation."
STEP2_STEP4_50_LINE_TOUCHED = "STEP2_STEP4_50_LINE_TOUCHED"

#
# STEP 4 CONTRACT (LEG 1)
#
# Candle roles:
# - Candle A = Step 2 confirmation / activation candle.
# - Candle B = next future candle.
#
# Participation rules:
# - SHORT passes if Candle B has 34% wick-high rejection or closes beneath Candle A high.
#   Wick-high rejection is measured from the candle body:
#   upper_wick = high - body_high, where body_high = max(open, close).
# - LONG passes if Candle B has 34% wick-low rejection or closes above Candle A low.
#   Wick-low rejection is measured from the candle body:
#   lower_wick = body_low - low, where body_low = min(open, close).
#
# Timing:
# - Step 4 / Leg 1 must complete within 4 future candles after Step 2.
# - The first Step 4 evaluation may occur only on Candle Count 2.
#   Count 0 is the Step 2 confirmation candle, Count 1 is observation only,
#   and Count 2 is the first candle that may confirm or invalidate Step 4.
# - The 4-candle window belongs to the original Step 2 confirmation and never
#   resets when rejection Candle A rolls to a newer extension candle.
# - Rejection Candle A may update inside that fixed window when a later candle
#   pushes farther in the rejection direction without yet satisfying Leg 1
#   participation. Candle B must then be a later future candle relative to the
#   current active Candle A.
#
# Pathway note:
# - Rejection and continuation share the same Step 4 formulas.
# - Their Candle A/B context and direction are pathway-specific.
#
# Invalidation line terminology:
# - step2_step4_50_line = frozen-table 50% invalidation line from the active
#   liquidity extreme to the next same-side liquidity close level.
# - step4_step5_75_line = frozen-table 75% invalidation line from the active
#   liquidity extreme to the next same-side liquidity close level.
# - These lines are not derived from candle OHLC.
#
# Sequencing priority:
# - step2_step4_50_line remains the normal Step 2/4 invalidation rule.
# - But if Step 4 already owns Candle A and is evaluating its first valid future
#   Candle B inside the protected seeded handoff window, Candle B handoff
#   evaluation has priority for that first owned Candle B only if that same
#   Candle B actually completes the Step 4 handoff to READY.
# - The protected first Candle B window is not a blanket bypass of
#   step2_step4_50_line.
# - If Candle Count 1 touches step2_step4_50_line and does not complete a valid
#   Step 4 handoff to READY, the setup must terminate with
#   STEP2_STEP4_50_LINE_TOUCHED.
# - After that protected handoff case fails or the protected window is gone,
#   step2_step4_50_line applies normally.
#
# Canonical replay examples:
# - 2026-06-19 rejection SHORT: 06:56 Candle A, 06:57 Candle B, Leg 1 complete.
# - 2026-06-19 continuation LONG: 07:00 Candle A, 07:01 Candle B, Leg 1 complete.
#

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


def close_based_participation(reference_extreme: float | None, candle: dict[str, Any], direction: str) -> bool:
    epsilon = 1e-9
    close_value = as_float(candle.get("close"))
    if close_value is None or reference_extreme is None:
        return False
    if direction == "SHORT":
        return close_value < (reference_extreme - epsilon)
    if direction == "LONG":
        return close_value > (reference_extreme + epsilon)
    return False


def wick_participation_percent(candle_b: dict[str, Any], direction: str) -> float | None:
    full_range = candle_range(candle_b)
    if full_range is None:
        return None
    high = as_float(candle_b.get("high"))
    low = as_float(candle_b.get("low"))
    if high is None or low is None:
        return None
    if direction == "SHORT":
        wick_body_high = body_high(candle_b)
        if wick_body_high is None:
            return None
        wick = high - wick_body_high
    elif direction == "LONG":
        wick_body_low = body_low(candle_b)
        if wick_body_low is None:
            return None
        wick = wick_body_low - low
    else:
        return None
    if wick < 0:
        return 0.0
    return wick / full_range * 100.0


def wick_participation_size(candle_b: dict[str, Any], direction: str) -> float | None:
    high = as_float(candle_b.get("high"))
    low = as_float(candle_b.get("low"))
    if high is None or low is None:
        return None
    if direction == "SHORT":
        wick_body_high = body_high(candle_b)
        if wick_body_high is None:
            return None
        wick = high - wick_body_high
    elif direction == "LONG":
        wick_body_low = body_low(candle_b)
        if wick_body_low is None:
            return None
        wick = wick_body_low - low
    else:
        return None
    return wick if wick >= 0 else 0.0


def wick_participation(candle_b: dict[str, Any], direction: str) -> bool:
    percent = wick_participation_percent(candle_b, direction)
    return bool(percent is not None and percent >= 34.0)


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
    if normalize_mode(state.get("controlling_mode")) in {"S/R", "R/S"}:
        state["fifty_percent_rule_phase"] = None
        state["leg1_formed_at_percent"] = None
        state["leg1_50_percent_rule_passed"] = None
        return None
    state["fifty_percent_rule_phase"] = "pre_leg1_only"
    percent = leg1_penetration_percent(state, extreme, direction)
    state["leg1_formed_at_percent"] = percent
    if percent is None:
        state["leg1_50_percent_rule_passed"] = None
        return None
    passed = percent <= 50.0
    state["leg1_50_percent_rule_passed"] = passed
    return passed


def step2_step4_reference_liquidity(state: dict[str, Any]) -> dict[str, Any] | None:
    reference = state.get("step2_step4_reference_liquidity")
    if isinstance(reference, dict):
        return reference
    reference = state.get("next_break_side_liquidity")
    if isinstance(reference, dict):
        return reference
    return None


def step2_step4_50_line(state: dict[str, Any]) -> float | None:
    active = state.get("active_liquidity")
    reference = step2_step4_reference_liquidity(state)
    if not isinstance(active, dict) or reference is None:
        return None
    active_price = as_float(active.get("price"))
    reference_price = as_float(reference.get("price"))
    if active_price is None or reference_price is None or active_price == reference_price:
        return None
    return (active_price + reference_price) / 2.0


def candle_touches_step2_step4_50_line(state: dict[str, Any], candle: dict[str, Any], direction: str | None) -> bool:
    active = state.get("active_liquidity")
    reference = step2_step4_reference_liquidity(state)
    if not isinstance(active, dict) or reference is None:
        return False
    active_price = as_float(active.get("price"))
    reference_price = as_float(reference.get("price"))
    line = step2_step4_50_line(state)
    if active_price is None or reference_price is None or line is None:
        return False
    high = as_float(candle.get("high"))
    low = as_float(candle.get("low"))
    if direction == "SHORT":
        return high is not None and high >= line
    if direction == "LONG":
        return low is not None and low <= line
    if reference_price > active_price:
        return high is not None and high >= line
    if reference_price < active_price:
        return low is not None and low <= line
    return False


def structure_touches_step2_step4_50_line(
    state: dict[str, Any],
    candle_a: dict[str, Any] | None,
    candle_b: dict[str, Any] | None,
    direction: str | None,
) -> tuple[bool, dict[str, Any] | None]:
    """Return whether the Candle A / Candle B Leg 1 structure touched the Step 2 -> Step 4 50% line."""
    if isinstance(candle_a, dict) and candle_touches_step2_step4_50_line(state, candle_a, direction):
        return True, candle_a
    if isinstance(candle_b, dict) and candle_touches_step2_step4_50_line(state, candle_b, direction):
        return True, candle_b
    return False, None


def invalidate_step2_step4_50_line_touch(
    state: dict[str, Any],
    candle: dict[str, Any],
    candidate_count: int,
) -> dict[str, Any]:
    reason = STEP2_STEP4_50_LINE_TOUCHED
    apply_leg1_window_fields(state, candle, candidate_count, invalidated=True, invalidation_reason=reason)
    state["leg1_window_remaining"] = 0
    state["leg1_window_active"] = False
    state["step2_step4_50_line"] = step2_step4_50_line(state)
    state["step2_step4_50_line_touched_at"] = candle.get("timestamp")
    state["invalidation_source"] = "step2_step4_50_line"
    state["invalidation_source_step"] = "Step 4"
    state["invalidation_source_candle_time"] = candle.get("timestamp")
    return terminate_interaction(state, "Step 4", reason)


def continuation_next_liquidity_breached(
    state: dict[str, Any],
    candle: dict[str, Any],
) -> tuple[bool, str | None]:
    if normalize_mode(state.get("controlling_mode")) not in {"S/R", "R/S"}:
        return False, None
    active = state.get("active_liquidity")
    boundary = state.get("next_break_side_liquidity")
    if not isinstance(active, dict) or not isinstance(boundary, dict):
        return False, None
    active_price = as_float(active.get("price"))
    boundary_price = as_float(boundary.get("price"))
    if active_price is None or boundary_price is None or active_price == boundary_price:
        return False, None
    high = as_float(candle.get("high"))
    low = as_float(candle.get("low"))
    close = as_float(candle.get("close"))
    if boundary_price > active_price:
        if close is not None and close >= boundary_price:
            return True, "close"
        if high is not None and high >= boundary_price:
            return True, "wick"
        return False, None
    if close is not None and close <= boundary_price:
        return True, "close"
    if low is not None and low <= boundary_price:
        return True, "wick"
    return False, None


def invalidate_continuation_next_liquidity_touch(
    state: dict[str, Any],
    candle: dict[str, Any],
    candidate_count: int,
    breach_type: str,
) -> dict[str, Any]:
    reason = "CONTINUATION_NEXT_LIQUIDITY_TOUCHED"
    apply_leg1_window_fields(state, candle, candidate_count, invalidated=True, invalidation_reason=reason)
    state["leg1_window_remaining"] = 0
    state["leg1_window_active"] = False
    state["step2_step4_50_line"] = None
    state["step4_step5_75_line"] = None
    state["leg1_50_percent_rule_passed"] = None
    state["leg1_formed_at_percent"] = None
    state["fifty_percent_rule_phase"] = None
    state["invalidation_source"] = f"continuation_next_liquidity_{breach_type}"
    state["invalidation_source_step"] = "Step 4"
    state["invalidation_source_candle_time"] = candle.get("timestamp")
    return terminate_interaction(state, "Step 4", reason)


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
            candidate = state.get("provisional_candle_a")
            if isinstance(candidate, dict):
                return candidate, "provisional_candle_a"
        candidate = state.get("reclaim_candle_a")
        if isinstance(candidate, dict):
            return candidate, "reclaim_candle_a"
        if isinstance(state.get("candle_a"), dict):
            return state.get("candle_a"), state.get("candle_a_source") or "candle_a"
        return state.get("initial_candle_a"), "initial_candle_a"
    if mode == "R/S":
        if activation_type == "wick":
            candidate = state.get("provisional_candle_a")
            if isinstance(candidate, dict):
                return candidate, "provisional_candle_a"
        candidate = state.get("reclaim_candle_a")
        if isinstance(candidate, dict):
            return candidate, "reclaim_candle_a"
        if isinstance(state.get("candle_a"), dict):
            return state.get("candle_a"), state.get("candle_a_source") or "candle_a"
        return state.get("initial_candle_a"), "initial_candle_a"
    if isinstance(state.get("candle_a"), dict):
        return state.get("candle_a"), state.get("candle_a_source") or "candle_a"
    return state.get("initial_candle_a"), "initial_candle_a"


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


def leg1_window_expires_at(started_at: Any, *, started_at_is_confirmation: bool = False) -> str | None:
    parsed = parse_candle_time(started_at)
    if parsed is None:
        return None
    offset = FINAL_PARTICIPATION_CANDLE_NUMBER if started_at_is_confirmation else FINAL_PARTICIPATION_CANDLE_NUMBER - 1
    return format_candle_time(parsed + timedelta(minutes=offset))


def initialize_leg1_window(state: dict[str, Any], confirmation_time: Any) -> None:
    """Start the Leg 1 window from Step 2 confirmation without counting that candle."""
    if not confirmation_time or state.get("leg1_window_started_at") or state.get("leg1_window_invalidated") is True:
        return
    state["leg1_window_active"] = True
    state["leg1_window_started_at"] = confirmation_time
    state["leg1_window_candle_index"] = 0
    state["leg1_window_remaining"] = FINAL_PARTICIPATION_CANDLE_NUMBER
    state["leg1_window_expires_at"] = leg1_window_expires_at(confirmation_time, started_at_is_confirmation=True)
    state["leg1_window_invalidated"] = False
    state["leg1_window_invalidation_reason"] = None


def apply_leg1_window_fields(
    state: dict[str, Any],
    candle: dict[str, Any],
    candle_index: int,
    *,
    invalidated: bool = False,
    invalidation_reason: str | None = None,
    complete: bool = False,
) -> None:
    if state.get("leg1_window_invalidated") is True and not invalidated and not complete:
        return
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


def clear_unconfirmed_leg1_fields(state: dict[str, Any]) -> None:
    """Remove stale Leg 1 completion fields while Step 4 remains in WAIT."""
    for key in (
        "leg1_status",
        "leg1_state_locked",
        "leg1_completed_at",
        "leg1_reference_price",
        "leg1_reference_candle_time",
        "leg1_direction",
        "leg1_reference",
        "leg1_extreme",
        "leg1_extreme_owner",
        "anchor_extreme",
        "opposite_participation",
    ):
        state.pop(key, None)


def rejection_candle_a_replacement_candidate(
    state: dict[str, Any],
    candle_a: dict[str, Any],
    candidate_b: dict[str, Any],
    direction: str,
) -> bool:
    """Allow rejection Candle A to roll deeper inside the fixed Step 4 window.

    Continuation pathways keep their own Candle A semantics. This replacement
    contract applies only to rejection Leg 1 tracking after Step 2 confirms.
    """
    if normalize_mode(state.get("controlling_mode")) in {"S/R", "R/S"}:
        return False
    # Keep the original Step 2 anchor through the first failed participation
    # candle. Rolling the rejection anchor is only valid once the window has
    # already consumed at least one failed participation attempt.
    if int(state.get("participation_candidate_count") or 0) <= 1:
        return False
    if direction == "SHORT":
        high_a = as_float(candle_a.get("high"))
        high_b = as_float(candidate_b.get("high"))
        return high_a is not None and high_b is not None and high_b > high_a
    if direction == "LONG":
        low_a = as_float(candle_a.get("low"))
        low_b = as_float(candidate_b.get("low"))
        return low_a is not None and low_b is not None and low_b < low_a
    return False


def ensure_step4_window_candles(state: dict[str, Any], confirmation_candle: dict[str, Any] | None) -> list[dict[str, Any]]:
    candles = [dict(candle) for candle in (state.get("step4_window_candles") or []) if isinstance(candle, dict)]
    if not candles and isinstance(confirmation_candle, dict):
        candles.append(dict(confirmation_candle))
    return candles


def append_step4_window_candle(
    state: dict[str, Any],
    confirmation_candle: dict[str, Any] | None,
    candidate_candle: dict[str, Any],
) -> list[dict[str, Any]]:
    candles = ensure_step4_window_candles(state, confirmation_candle)
    key = candle_key(candidate_candle)
    if key not in {candle_key(item) for item in candles}:
        candles.append(dict(candidate_candle))
    state["step4_window_candles"] = candles[-5:]
    return state["step4_window_candles"]


def participation_extreme_for_direction(candle: dict[str, Any], direction: str) -> float | None:
    if direction == "SHORT":
        return as_float(candle.get("high"))
    if direction == "LONG":
        return as_float(candle.get("low"))
    return None


def update_participation_extreme(
    state: dict[str, Any],
    candidate_candle: dict[str, Any],
    direction: str,
) -> tuple[float | None, bool]:
    previous_extreme = as_float(state.get("step4_participation_extreme"))
    candidate_extreme = participation_extreme_for_direction(candidate_candle, direction)
    if candidate_extreme is None:
        return previous_extreme, False
    if previous_extreme is None:
        state["step4_participation_extreme"] = candidate_extreme
        state["step4_participation_seed_time"] = candidate_candle.get("timestamp")
        return candidate_extreme, True
    replaced = False
    if direction == "SHORT" and candidate_extreme > previous_extreme:
        replaced = True
    elif direction == "LONG" and candidate_extreme < previous_extreme:
        replaced = True
    if replaced:
        state["step4_participation_extreme"] = candidate_extreme
        state["step4_participation_seed_time"] = candidate_candle.get("timestamp")
        return candidate_extreme, True
    return previous_extreme, False


def frozen_leg2_structure(window_candles: list[dict[str, Any]], direction: str) -> tuple[float | None, float | None]:
    if not window_candles:
        return None, None
    extremes: list[float] = []
    closes: list[float] = []
    for candle in window_candles:
        close_value = as_float(candle.get("close"))
        if close_value is not None:
            closes.append(close_value)
        extreme_value = participation_extreme_for_direction(candle, direction)
        if extreme_value is not None:
            extremes.append(extreme_value)
    if not extremes or not closes:
        return None, None
    if direction == "SHORT":
        return max(extremes), max(closes)
    if direction == "LONG":
        return min(extremes), min(closes)
    return None, None


def evaluate_step4(interaction: dict[str, Any], candle_b: dict[str, Any] | None = None) -> dict[str, Any]:
    """Confirm Step 4 participation inside the fixed Step 2 window and freeze Step 5 structure."""
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
        reason = "Step 4 waiting: Step 2 confirmation anchor and a participation candle are required."
        events.append({"event": "step4_waiting_for_candles", "reason": reason})
        return result("WAIT", state, "Step 4", reason, events)

    side_violation = side_requirement_violated(state, candidate_b)
    if side_violation:
        return terminate_interaction(state, "Step 4", side_violation)

    state.setdefault("step4_window_anchor_time", candle_a.get("timestamp"))
    state.setdefault("step4_participation_extreme", participation_extreme_for_direction(candle_a, direction))
    state.setdefault("step4_participation_seed_time", candle_a.get("timestamp"))
    window_candles = append_step4_window_candle(state, candle_a, candidate_b)
    candidate_count = register_participation_candidate(state, candidate_b)
    state["step4_window_count"] = candidate_count
    continuation_touched_next_liquidity, continuation_breach_type = continuation_next_liquidity_breached(state, candidate_b)
    if continuation_touched_next_liquidity:
        return invalidate_continuation_next_liquidity_touch(
            state,
            candidate_b,
            candidate_count,
            continuation_breach_type or "wick",
        )
    structure_touched_50_line, source_candle = structure_touches_step2_step4_50_line(state, candle_a, candidate_b, direction)
    protected_first_candle_b = (
        state.get("reserved_rejection_candle_b_evaluation") is True and candidate_count == 1
    )
    if structure_touched_50_line and not protected_first_candle_b:
        return invalidate_step2_step4_50_line_touch(state, source_candle or candidate_b, candidate_count)
    protected_touched_50_line = bool(structure_touched_50_line and protected_first_candle_b)

    reference_extreme = as_float(state.get("step4_participation_extreme"))
    close_pass = close_based_participation(reference_extreme, candidate_b, direction)
    wick_pct = wick_participation_percent(candidate_b, direction)
    tick_size = as_float(state.get("tick_size")) or 0.25
    wick_pass = bool(wick_pct is not None and wick_pct >= 34.0)
    relaxed_first_candle_wick_pass = (
        state.get("opening_post_confirmation_relaxed_wick") is True
        and candidate_count == 1
        and wick_pct is not None
        and (wick_pct + 1e-9) >= 20.0
    )
    candle_a_extreme = reference_extreme
    state["step3_participation_rule_certification"] = "CERTIFIED"
    state["step3_participation_direction"] = direction
    state["step3_participation_candle_a_extreme"] = candle_a_extreme
    state["step3_close_participation_pass"] = close_pass
    state["step3_wick_participation_pct"] = round(wick_pct, 2) if wick_pct is not None else None
    state["step3_wick_participation_pass"] = (wick_pass or relaxed_first_candle_wick_pass)
    if not (close_pass or wick_pass or relaxed_first_candle_wick_pass):
        if protected_touched_50_line:
            return invalidate_step2_step4_50_line_touch(state, source_candle or candidate_b, candidate_count)
        reason = "Participation candle failed both close-based participation and 34% wick-based participation."
        replaced_candle_a = rejection_candle_a_replacement_candidate(state, candle_a, candidate_b, direction)
        if replaced_candle_a:
            updated_extreme, _ = update_participation_extreme(state, candidate_b, direction)
            state["awaiting_future_candle_b"] = True
            state["candle_a"] = dict(candidate_b)
            state["candle_a_source"] = "rolling_participation_extreme"
            state.pop("candle_b", None)
            reason = (
                "Participation failed and the Step 4 rolling participation extreme extended; "
                "waiting for a later participation candle inside the original 4-candle Step 4 window."
            )
            state["step3_participation_candle_a_extreme"] = updated_extreme
        if candidate_count < FINAL_PARTICIPATION_CANDLE_NUMBER:
            clear_unconfirmed_leg1_fields(state)
            events.append(
                {
                    "event": "step4_participation_window_wait",
                    "reason": reason,
                    "candle_a_replaced": replaced_candle_a,
                    "candidate_count": candidate_count,
                    "candle_number": candidate_count,
                    "window_label": f"Candle {candidate_count} of {FINAL_PARTICIPATION_CANDLE_NUMBER}",
                    "remaining": state.get("leg1_window_remaining"),
                    "expires_at": state.get("leg1_window_expires_at"),
                    "final_candle_number": FINAL_PARTICIPATION_CANDLE_NUMBER,
                }
            )
            return result("WAIT", state, "Step 4", reason, events)
        reason = LEG1_WINDOW_INVALIDATION_REASON
        apply_leg1_window_fields(state, candidate_b, candidate_count, invalidated=True, invalidation_reason=reason)
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

    leg2_sweep_extreme, step5_close_boundary = frozen_leg2_structure(window_candles, direction)
    if leg2_sweep_extreme is None or step5_close_boundary is None:
        return terminate_interaction(state, "Step 4", "Step 4 could not freeze the Leg 2 / Step 5 structure from the participation window.")
    if not stack_leg1_extreme_confirmed(state, leg2_sweep_extreme, direction):
        if protected_touched_50_line:
            return invalidate_step2_step4_50_line_touch(state, source_candle or candidate_b, candidate_count)
        reason = "Step 4 waiting: static stack Leg 1 requires HH/LL beyond the Extreme Boundary; close-boundary Leg 1 is not tradable."
        state["step4_block_reason"] = reason
        clear_unconfirmed_leg1_fields(state)
        events.append({"event": "step4_stack_extreme_required", "reason": reason})
        return result("WAIT", state, "Step 4", reason, events)
    update_continuation_acceptance_after_leg1(state, candidate_b, leg2_sweep_extreme)
    leg1_50_passed = apply_leg1_50_percent_rule(state, leg2_sweep_extreme, direction)
    if (
        leg1_50_passed is False
        and state.get("reserved_rejection_candle_b_evaluation") is True
        and candidate_count == 1
    ):
        leg1_50_passed = None
        state["leg1_50_percent_rule_passed"] = None
        state["fifty_percent_rule_phase"] = "reserved_candle_b_bypass"
    if leg1_50_passed is False:
        reason = "Leg 1 invalid: active liquidity was penetrated beyond 50% before Leg 1 formed."
        state["leg1_status"] = "INVALID"
        state["liquidity_state"] = "CONSUMED"
        state["level_state"] = "CONSUMED"
        state["invalidation_source"] = "leg1_50_percent_rule"
        state["invalidation_source_step"] = "Step 4"
        return terminate_interaction(state, "Step 4", reason)

    mode = normalize_mode(state.get("controlling_mode"))
    daily_atr = as_float(state.get("daily_atr14") or state.get("daily_atr"))
    distance = proximity_distance(leg2_sweep_extreme, state.get("nearest_opposing_liquidity"))
    threshold_percent = 10.0
    threshold = daily_atr * (threshold_percent / 100.0) if daily_atr is not None else None
    state["proximity_distance"] = distance
    state["proximity_daily_atr"] = daily_atr
    state["proximity_atr_threshold"] = threshold
    state["proximity_atr_threshold_percent"] = threshold_percent if threshold is not None else None

    if mode not in {"S/R", "R/S"}:
        if daily_atr is None:
            return terminate_interaction(state, "Step 4", "Step 4 proximity filter requires daily ATR14.")
        if distance is None:
            return terminate_interaction(state, "Step 4", "Step 4 proximity filter requires nearest opposing liquidity level.")
        if distance <= threshold:
            if protected_touched_50_line:
                return invalidate_step2_step4_50_line_touch(state, source_candle or candidate_b, candidate_count)
            reason = "Step 4 proximity filter hard bypass: distance from Anchor Extreme to nearest opposing liquidity is <= 10% daily ATR."
            return terminate_interaction(state, "Step 4", reason)

    state["candle_b"] = candidate_b
    state["candle_a"] = candle_a
    state["candle_a_source"] = candle_a_source
    state["awaiting_future_candle_b"] = False
    state["leg1_status"] = "COMPLETE"
    apply_leg1_window_fields(state, candidate_b, candidate_count, complete=True)
    state["step4_confirmed_at"] = candidate_b.get("timestamp")
    state["step4_window_count"] = candidate_count
    state["leg2_sweep_extreme"] = leg2_sweep_extreme
    state["step5_close_boundary"] = step5_close_boundary
    state["leg1_reference"] = step5_close_boundary
    state["leg1_extreme"] = leg2_sweep_extreme
    state["leg1_extreme_owner"] = "step4_window"
    state["anchor_extreme"] = leg2_sweep_extreme
    state["opposite_participation"] = "PRESENT"
    state["participation_timer"] = {
        **dict(state.get("participation_timer") or {}),
        "active": False,
        "completed": True,
        "remaining": 0,
        "completed_at": candidate_b.get("timestamp"),
    }

    reason = "Step 4 confirmed: participation qualified inside the Step 2 window; Leg 2 / Step 5 structure frozen from the 5-candle participation window."
    events.append(
        {
            "event": "step4_leg1_complete",
            "reason": reason,
            "close_based_participation": close_pass,
            "wick_based_participation": wick_pass,
            "step3_participation_rule_certification": "CERTIFIED",
            "step3_participation_candle_a_extreme": candle_a_extreme,
            "step3_wick_participation_pct": state.get("step3_wick_participation_pct"),
            "step4_confirmed_at": state.get("step4_confirmed_at"),
            "step4_window_count": state.get("step4_window_count"),
            "step5_close_boundary": step5_close_boundary,
            "leg2_sweep_extreme": leg2_sweep_extreme,
            "leg1_reference": step5_close_boundary,
            "leg1_extreme": leg2_sweep_extreme,
            "leg1_extreme_owner": "step4_window",
            "anchor_extreme": leg2_sweep_extreme,
            "candle_a_source": candle_a_source,
            "controlling_mode": state.get("controlling_mode"),
        }
    )
    return result("READY", state, "Step 5", reason, events)
