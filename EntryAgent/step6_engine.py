"""Step 6 entry decision engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from step7_engine import STRUCTURE_FIELDS, terminate_interaction


STEP6_PHASE_WINDOW_CANDLES = 4
STEP6_NEXT_SAME_SIDE_LIQUIDITY_CLOSE_TOUCHED = "STEP6_NEXT_SAME_SIDE_LIQUIDITY_CLOSE_TOUCHED"

# STEP 6 CONTRACT
#
# Entry models are evaluated inside a fixed 4-candle Step 6 window.
# The first valid Step 6 entry model wins.
#
# STEP 6 EXECUTION WINDOW AND ANCHOR OWNERSHIP
#
# Step 5 confirmation starts one fixed 4-candle Step 6 execution window.
# That window never resets, extends, or rolls forward.
#
# The active Step 6 anchor candle ("A") is the candle currently used by the
# Step 6 entry models. During the fixed window, a newer qualifying anchor may
# replace the current anchor.
#
# Replacement begins no earlier than Candle 2 of the fixed Step 6 window.
# Replacement transfers before entry evaluation against the old anchor.
#
# Anchor progression is adverse/deeper into the setup:
# - LONG replacement requires a close below the current anchor close by at least 1 tick.
# - SHORT replacement requires a close above the current anchor close by at least 1 tick.
#
# Active anchor eligibility:
# - The active anchor must have a positive directional wick.
# - Zero directional wick is not eligible for Small Wick, Large Wick, or Double Wick.
#
# When replacement happens, Step 6 calculations immediately switch to the newer
# anchor, but the original Step 5 execution window remains in force.
#
# Real NQ example — 2026-06-19
#
# 06:39 PT / 13:39Z = A0 / original Step 6 anchor
# O 30667.75 H 30667.75 L 30659.00 C 30663.75
#
# 06:40 PT / 13:40Z = Candle 1
# O 30663.75 H 30673.00 L 30663.50 C 30667.00
# Expected: no entry, no LONG replacement.
#
# 06:41 PT / 13:41Z = Candle 2
# O 30666.50 H 30668.00 L 30655.75 C 30658.75
# Expected: becomes replacement LONG anchor because the close is lower/deeper
# than A0 by at least 1 tick and the candle has a positive lower wick.
#
# 06:42 PT / 13:42Z = Candle 3
# O 30659.25 H 30660.75 L 30651.25 C 30659.75
# Expected: evaluates against the 06:41 anchor and triggers LONG Large Wick Sweep.
#
# Entry math:
# - 06:41 lower wick = 30658.75 - 30655.75 = 3.00
# - 60% reclaim = 30655.75 + (3.00 * 0.60) = 30657.55
# - 06:42 low sweeps below 30655.75
# - 06:42 high reclaims above 30657.55
# - Valid Step 6 entry = 30657.55
#
# Important:
# - 06:42 is evaluated against 06:41, not 06:39 or 06:40.
# - The Step 6 clock remains tied to 06:39.
# - No reset.
# - No extension.
# - No Step 1–5 behavior changes.
#
# STEP 6 EXPIRATION RULE
#
# If no valid Step 6 entry model triggers within the 4-candle Step 6 window:
# - Step 6 expires.
# - The continuation pathway is invalidated.
# - The controlling R/S level is invalidated for continuation purposes.
#
# That continuation level is permanently dead as a continuation level. It may not:
# - restart Step 6
# - reactivate continuation
# - create a new continuation pathway
#
# The only pathway that may remain alive after Step 6 expiry is an already-active
# rejection pathway, if that rejection pathway is still valid on its own contract.
#
# Canonical summary:
# No Step 6 entry by Candle 4
# -> Continuation invalid
# -> Continuation level invalid
# -> Rejection pathway may continue if still valid
#
# Additional invalidation:
# - Before Step 6 entry completes, price must not touch the next same-side
#   liquidity close level.
# - SHORT: candle high touching/exceeding the next upper same-side close
#   invalidates.
# - LONG: candle low touching/falling through the next lower same-side close
#   invalidates.


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
    if wick <= 0:
        return {
            "wick_percent": 0.0,
            "sweep_entry_path": None,
            "double_wick_state": "ELIMINATED",
            "anchor_eligible": False,
            "ineligible_reason": "Active anchor has no directional wick; wick-sweep models require a positive directional wick.",
        }
    wick_percent = wick / full_range
    large = wick_percent >= 0.20
    return {
        "wick_percent": wick_percent,
        "sweep_entry_path": "Large Wick" if large else "Small Wick",
        "double_wick_state": "ACTIVE" if large else "ELIMINATED",
        "anchor_eligible": True,
        "ineligible_reason": None,
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


def intrabar_reclaims(entry_candle: dict[str, Any], level: float, direction: str, tick_size: float) -> bool:
    if direction == "SHORT":
        low = as_float(entry_candle.get("low"))
        return low is not None and low <= level - tick_size
    if direction == "LONG":
        high = as_float(entry_candle.get("high"))
        return high is not None and high >= level + tick_size
    return False


def evaluate_large_wick_sweep(sc: dict[str, Any], entry_candle: dict[str, Any], direction: str, tick_size: float) -> tuple[bool, float | None, str]:
    wick = sc_wick(sc, direction)
    if wick is None or wick <= 0:
        return False, None, "Large Wick Sweep requires a positive SC directional wick."
    reclaim_level = large_wick_reclaim_level(sc, direction)
    if reclaim_level is None:
        return False, None, "Large Wick Sweep requires SC wick measurement."
    if sweep_extreme(entry_candle, sc, direction, tick_size) and intrabar_reclaims(entry_candle, reclaim_level, direction, tick_size):
        return True, reclaim_level, "Large Wick Sweep triggered: SC extreme swept by 1 tick and 60% wick reclaim exceeded by 1 tick."
    return False, None, "Large Wick Sweep did not trigger."


def small_wick_body_level(sc: dict[str, Any], direction: str) -> float | None:
    if direction == "SHORT":
        return body_high(sc)
    if direction == "LONG":
        return body_low(sc)
    return None


def small_wick_open_accepts_body(entry_candle: dict[str, Any], body_level: float, direction: str, tick_size: float) -> bool:
    open_price = as_float(entry_candle.get("open"))
    if open_price is None:
        return False
    if direction == "SHORT":
        return open_price <= body_level - tick_size
    if direction == "LONG":
        return open_price >= body_level + tick_size
    return False


def intrabar_touches_level(entry_candle: dict[str, Any], level: float, direction: str) -> bool:
    if direction == "SHORT":
        low = as_float(entry_candle.get("low"))
        return low is not None and low <= level
    if direction == "LONG":
        high = as_float(entry_candle.get("high"))
        return high is not None and high >= level
    return False


def atr_1m_14_from_state(state: dict[str, Any]) -> float | None:
    direct = as_float(state.get("atr_1m_14") or state.get("current_1m_atr") or state.get("atr_1m"))
    if direct is not None:
        return direct
    atr = state.get("atr")
    if isinstance(atr, dict):
        return as_float(atr.get("atr_1m_14") or atr.get("current_1m_atr") or atr.get("atr_1m"))
    return as_float(atr)


def intrabar_path_points(state: dict[str, Any]) -> list[tuple[datetime | None, float]]:
    bucket = state.get("step6_intrabar_previous_minute_path")
    if not isinstance(bucket, dict) or bucket.get("truncated") is True:
        return []
    raw_points = bucket.get("points")
    if not isinstance(raw_points, list):
        return []
    points: list[tuple[datetime | None, float]] = []
    for item in raw_points:
        if not (isinstance(item, (list, tuple)) and len(item) >= 2):
            continue
        price = as_float(item[1])
        if price is None:
            continue
        points.append((parse_timestamp(item[0]), price))
    points.sort(key=lambda item: (item[0] is None, item[0]))
    return points


def small_wick_sequence_triggered(
    state: dict[str, Any],
    sc: dict[str, Any],
    entry_candle: dict[str, Any],
    direction: str,
    tick_size: float,
) -> tuple[bool, float | None, str] | None:
    points = intrabar_path_points(state)
    if not points:
        return None

    body_level = small_wick_body_level(sc, direction)
    if body_level is None:
        return False, None, "Small Wick Sweep requires SC body level."

    if direction == "SHORT":
        sweep_level = as_float(sc.get("high"))
        accepted = small_wick_open_accepts_body(entry_candle, body_level, direction, tick_size)
        swept = False
        for _, price in points:
            if not accepted and price <= body_level - tick_size:
                accepted = True
                continue
            if accepted and not swept and sweep_level is not None and price >= sweep_level + tick_size:
                swept = True
                continue
            if accepted and swept and price <= body_level:
                return True, body_level, "Small Wick Sweep triggered: ordered intrabar sequence confirmed body acceptance, 1-tick sweep, and reclaim at SC body level."
        return False, None, "Small Wick Sweep did not trigger: intrabar path did not complete body acceptance -> sweep -> reclaim in order."

    if direction == "LONG":
        sweep_level = as_float(sc.get("low"))
        accepted = small_wick_open_accepts_body(entry_candle, body_level, direction, tick_size)
        swept = False
        for _, price in points:
            if not accepted and price >= body_level + tick_size:
                accepted = True
                continue
            if accepted and not swept and sweep_level is not None and price <= sweep_level - tick_size:
                swept = True
                continue
            if accepted and swept and price >= body_level:
                return True, body_level, "Small Wick Sweep triggered: ordered intrabar sequence confirmed body acceptance, 1-tick sweep, and reclaim at SC body level."
        return False, None, "Small Wick Sweep did not trigger: intrabar path did not complete body acceptance -> sweep -> reclaim in order."

    return False, None, "Small Wick Sweep requires setup_direction LONG or SHORT."


def evaluate_small_wick_sweep(state: dict[str, Any], sc: dict[str, Any], entry_candle: dict[str, Any], direction: str, tick_size: float) -> tuple[bool, float | None, str]:
    wick = sc_wick(sc, direction)
    if wick is None or wick <= 0:
        return False, None, "Small Wick Sweep requires a positive SC directional wick."
    sequenced = small_wick_sequence_triggered(state, sc, entry_candle, direction, tick_size)
    if sequenced is not None:
        return sequenced
    body_level = small_wick_body_level(sc, direction)
    if body_level is None:
        return False, None, "Small Wick Sweep requires SC body level."
    if (
        small_wick_open_accepts_body(entry_candle, body_level, direction, tick_size)
        and sweep_extreme(entry_candle, sc, direction, tick_size)
        and intrabar_touches_level(entry_candle, body_level, direction)
    ):
        return True, body_level, "Small Wick Sweep triggered: conservative OHLC body acceptance, 1-tick sweep, and intrabar reclaim at SC body level."
    return False, None, "Small Wick Sweep did not trigger."


def evaluate_double_wick(sc: dict[str, Any], entry_candle: dict[str, Any], direction: str, tick_size: float) -> tuple[bool, float | None, str]:
    wick = sc_wick(sc, direction)
    if wick is None or wick <= 0:
        return False, None, "Double Wick requires a positive SC directional wick."
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
    if reclaim is not None and penetrated and intrabar_touches_level(entry_candle, reclaim, direction):
        return True, reclaim, "Double Wick Rejection triggered: entry penetrated 50% of SC wick and reclaimed the SC body level intrabar."
    return False, None, "Double Wick Rejection did not trigger."


def evaluate_extended_retrace(state: dict[str, Any], sc: dict[str, Any], entry_candle: dict[str, Any], direction: str) -> tuple[bool, float | None, str]:
    atr_1m_14 = atr_1m_14_from_state(state)
    if atr_1m_14 is None:
        return False, None, "Extended Retrace requires 1-minute ATR(14)."

    threshold = atr_1m_14 * 0.50
    entry_price = None
    extension = None
    filled = False

    if direction == "SHORT":
        anchor = as_float(sc.get("high"))
        trigger_extreme = as_float(entry_candle.get("high"))
        low = as_float(entry_candle.get("low"))
        if anchor is not None and trigger_extreme is not None:
            extension = trigger_extreme - anchor
            entry_price = anchor + (extension * 0.50)
            filled = low is not None and entry_price is not None and low <= entry_price
    elif direction == "LONG":
        anchor = as_float(sc.get("low"))
        trigger_extreme = as_float(entry_candle.get("low"))
        high = as_float(entry_candle.get("high"))
        if anchor is not None and trigger_extreme is not None:
            extension = anchor - trigger_extreme
            entry_price = anchor - (extension * 0.50)
            filled = high is not None and entry_price is not None and high >= entry_price
    else:
        return False, None, "Extended Retrace requires setup_direction LONG or SHORT."

    if extension is None or entry_price is None:
        return False, None, "Extended Retrace requires Step 6 Candle A/B extremes."
    if extension < threshold:
        return False, None, "Extended Retrace did not trigger: extension stayed below 0.50 x ATR(14)."
    if not filled:
        return False, None, "Extended Retrace did not trigger: extension qualified but intrabar retrace fill did not occur."
    return True, entry_price, "Extended Retrace triggered: extension reached 0.50 x ATR(14) and retraced 50% intrabar."


def close_beyond_sc_close(candle: dict[str, Any], sc: dict[str, Any], direction: str, tick_size: float) -> bool:
    close = as_float(candle.get("close"))
    sc_close = as_float(sc.get("close"))
    if close is None or sc_close is None:
        return False
    # Step 6 anchor progression moves deeper/adverse into the setup direction.
    if direction == "LONG":
        return close <= sc_close - tick_size
    if direction == "SHORT":
        return close >= sc_close + tick_size
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


def next_same_side_liquidity_close_touched(state: dict[str, Any], candle: dict[str, Any], direction: str) -> bool:
    reference = state.get("next_break_side_liquidity")
    if not isinstance(reference, dict):
        reference = state.get("step2_step4_reference_liquidity")
    if not isinstance(reference, dict):
        reference = state.get("next_same_side_liquidity")
    close_level = as_float(reference.get("price") if isinstance(reference, dict) else None)
    if close_level is None:
        return False
    if direction == "SHORT":
        high = as_float(candle.get("high"))
        return high is not None and high >= close_level
    if direction == "LONG":
        low = as_float(candle.get("low"))
        return low is not None and low <= close_level
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
    ineligible_reason = decision.get("ineligible_reason") or "Decision Pass did not select this model."
    selected_path = decision.get("sweep_entry_path")
    sweep_ineligible_reason = ineligible_reason if selected_path is None else f"Decision Pass selected {selected_path}."
    double_ineligible_reason = ineligible_reason if selected_path is None else "Decision Pass eliminated Double Wick."
    large_ok, large_price, large_reason = evaluate_large_wick_sweep(anchor, candidate, direction, tick_size)
    small_ok, small_price, small_reason = evaluate_small_wick_sweep(state, anchor, candidate, direction, tick_size)
    double_ok, double_price, double_reason = evaluate_double_wick(anchor, candidate, direction, tick_size)
    extended_ok, extended_price, extended_reason = evaluate_extended_retrace(state, anchor, candidate, direction)
    state["step6_entry_models"] = {
        "large_wick_sweep": {
            "evaluated": True,
            "passed": large_ok and decision["sweep_entry_path"] == "Large Wick",
            "eligible": decision["sweep_entry_path"] == "Large Wick",
            "reason": large_reason if decision["sweep_entry_path"] == "Large Wick" else f"{large_reason} Ineligible because {sweep_ineligible_reason}",
        },
        "small_wick_sweep": {
            "evaluated": True,
            "passed": small_ok and decision["sweep_entry_path"] == "Small Wick",
            "eligible": decision["sweep_entry_path"] == "Small Wick",
            "reason": small_reason if decision["sweep_entry_path"] == "Small Wick" else f"{small_reason} Ineligible because {sweep_ineligible_reason}",
        },
        "double_wick_rejection": {
            "evaluated": True,
            "passed": double_ok and decision["double_wick_state"] == "ACTIVE",
            "eligible": decision["double_wick_state"] == "ACTIVE",
            "reason": double_reason if decision["double_wick_state"] == "ACTIVE" else f"{double_reason} Ineligible because {double_ineligible_reason}",
        },
        "extended_retrace": {
            "evaluated": True,
            "passed": extended_ok,
            "eligible": atr_1m_14_from_state(state) is not None,
            "reason": extended_reason,
        },
    }
    state["extended_retrace_entry_valid"] = extended_ok
    state["extended_retrace_entry_price"] = extended_price
    state["extended_retrace_entry_active"] = extended_ok
    state["extended_retrace_pending"] = extended_price is not None and extended_ok is not True
    state["extended_retrace_blocked_immediate_entry"] = False
    state["extended_retrace_block_reason"] = None if extended_ok or extended_price is not None else extended_reason
    state["extended_retrace_intrabar_fill"] = extended_ok
    if extended_price is not None:
        tick_value = tick_size if tick_size > 0 else 0.25
        anchor_extreme = as_float(anchor.get("high")) if direction == "SHORT" else as_float(anchor.get("low"))
        trigger_extreme = as_float(candidate.get("high")) if direction == "SHORT" else as_float(candidate.get("low"))
        if anchor_extreme is not None and trigger_extreme is not None:
            extension_distance = abs(trigger_extreme - anchor_extreme)
            state["extended_retrace_extension_ticks"] = extension_distance / tick_value
            atr_1m_14 = atr_1m_14_from_state(state)
            state["extended_retrace_extension_atr_percent"] = ((extension_distance / atr_1m_14) * 100.0) if atr_1m_14 else None
        state["extended_retrace_step6_extreme"] = trigger_extreme
    else:
        state["extended_retrace_extension_ticks"] = None
        state["extended_retrace_extension_atr_percent"] = None
        state["extended_retrace_step6_extreme"] = None
    state["extended_retrace_step6_candle"] = candidate
    state["extended_retrace_step6_candle_time"] = candle_timestamp(candidate)
    state["extended_retrace_expires_at_candle"] = STEP6_PHASE_WINDOW_CANDLES
    state["extended_retrace_invalidated"] = False
    state["extended_retrace_expired"] = False
    state["extended_retrace_entry_triggered"] = extended_ok

    if decision["sweep_entry_path"] == "Large Wick" and large_ok and large_price is not None:
        return entry_confirmed(state, events, "Large Wick Sweep", large_price, large_reason)
    if decision["sweep_entry_path"] == "Small Wick" and small_ok and small_price is not None:
        return entry_confirmed(state, events, "Small Wick Sweep", small_price, small_reason)
    if decision["double_wick_state"] == "ACTIVE" and double_ok and double_price is not None:
        return entry_confirmed(state, events, "Double Wick Rejection", double_price, double_reason)
    if extended_ok and extended_price is not None:
        return entry_confirmed(state, events, "Extended Retrace", extended_price, extended_reason)
    return None


def qualifies_phase1_anchor(current_anchor: dict[str, Any], candidate: dict[str, Any], direction: str, tick_size: float) -> bool:
    """Return True when the candidate can own the next Step 6 SC anchor."""
    if not close_beyond_sc_close(candidate, current_anchor, direction, tick_size):
        return False
    wick = sc_wick(candidate, direction)
    full_range = candle_range(candidate)
    return wick is not None and full_range is not None and wick > 0


def replace_phase1_anchor(state: dict[str, Any], candidate: dict[str, Any]) -> None:
    progression = int(state.get("sc_progression_count") or 1) + 1
    if progression >= 2 and state.get("sc2") is None:
        state["sc2"] = candidate
    elif progression >= 3:
        state["sc3"] = candidate
    state["sc_progression_count"] = progression
    state["phase1_anchor"] = candidate
    state["active_entry_anchor"] = candidate
    state["sc"] = candidate
    state["current_sc"] = candidate


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

    if count > 4:
        close_step6_window(state, candidate, count)
        return terminate_interaction(state, "Step 6", "Phase 1 timing expired; no late entry after Candle 4.")

    if required_leg_in_liquidity_gate_active(state):
        if count >= 4:
            close_step6_window(state, candidate)
            return terminate_interaction(state, "Step 6", "Required leg-in liquidity gate blocked entry until Phase 1 timing expired.")
        return wait_for_required_leg_in_liquidity_sweep(
            state,
            events,
            f"Phase 1 Candle {count}: required leg-in liquidity sweep gate active; entry evaluation blocked while timing continues.",
        )

    replaced_anchor = False
    prior_anchor_time = candle_timestamp(anchor)
    candidate_time = candle_timestamp(candidate)
    if 2 <= count < STEP6_PHASE_WINDOW_CANDLES and (
        qualifies_phase1_anchor(anchor, candidate, direction, tick_size)
        and (
            candidate_time is None
            or prior_anchor_time is None
            or candidate_time != prior_anchor_time
        )
    ):
        replace_phase1_anchor(state, candidate)
        replaced_anchor = True

    if replaced_anchor:
        reason = f"Phase 1 Candle {count}: newer qualifying anchor adopted for the remaining fixed Step 6 window."
        events.append(
            {
                "event": "step6_phase1_anchor_replaced",
                "phase1_candle_count": count,
                "reason": reason,
                "anchor_timestamp": candle_timestamp(candidate),
            }
        )
        return result("WAIT", state, "Step 6", reason, events)

    entry = evaluate_entry_models(state, events, anchor, candidate, direction, tick_size)
    if entry is not None:
        return entry

    if count < 4:
        reason = f"Phase 1 Candle {count}: entry models evaluated; no valid entry yet."
        events.append({"event": "step6_phase1_wait", "phase1_candle_count": count, "reason": reason})
        return result("WAIT", state, "Step 6", reason, events)

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

    if next_same_side_liquidity_close_touched(state, candidate, direction):
        count = next_phase1_count(state, candidate)
        state["step6_phase"] = state.get("step6_phase") or "PHASE1"
        state["phase1_candle_count"] = count
        close_step6_window(state, candidate, count)
        state["invalidation_source"] = "step6_next_same_side_liquidity_close"
        state["invalidation_source_step"] = "Step 6"
        state["invalidation_source_candle_time"] = candle_timestamp(candidate)
        return terminate_interaction(state, "Step 6", STEP6_NEXT_SAME_SIDE_LIQUIDITY_CLOSE_TOUCHED)

    phase = state.get("step6_phase") or "PHASE1"
    if phase == "PHASE2" or state.get("phase2_active") is True:
        return evaluate_phase2(state, events, candidate, direction, tick_size)
    return evaluate_phase1(state, events, candidate, direction, tick_size)
