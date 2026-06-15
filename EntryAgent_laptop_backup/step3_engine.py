"""Step 3 liquidity type decision engine."""

from __future__ import annotations

from typing import Any

from step7_engine import terminate_interaction


def result(status: str, state: dict[str, Any], next_step: str, reason: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "step": "Step 3",
        "status": status,
        "state": state,
        "next_step": next_step,
        "reason": reason,
        "events": events,
    }


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def candle_direction(candle: dict[str, Any]) -> str | None:
    open_price = as_float(candle.get("open"))
    close = as_float(candle.get("close"))
    if open_price is None or close is None or close == open_price:
        return None
    return "up" if close > open_price else "down"


def has_three_alternating_candles(candles: list[dict[str, Any]]) -> bool:
    directions = [candle_direction(candle) for candle in candles[-3:]]
    return len(directions) == 3 and None not in directions and directions[0] != directions[1] != directions[2]


def has_overlapping_bodies(candles: list[dict[str, Any]]) -> bool:
    if len(candles) < 2:
        return False
    bodies = []
    for candle in candles[-3:]:
        open_price = as_float(candle.get("open"))
        close = as_float(candle.get("close"))
        if open_price is None or close is None:
            return False
        bodies.append((min(open_price, close), max(open_price, close)))
    overlap_low = max(body[0] for body in bodies)
    overlap_high = min(body[1] for body in bodies)
    return overlap_low <= overlap_high


def has_micro_hh_ll_sequence(candles: list[dict[str, Any]]) -> bool:
    if len(candles) < 3:
        return False
    recent = candles[-3:]
    highs = [as_float(candle.get("high")) for candle in recent]
    lows = [as_float(candle.get("low")) for candle in recent]
    if any(value is None for value in highs + lows):
        return False
    return bool(highs[0] < highs[1] < highs[2] and lows[0] > lows[1] > lows[2])


def has_visible_consolidation_cluster(candles: list[dict[str, Any]]) -> bool:
    if len(candles) < 3:
        return False
    recent = candles[-3:]
    highs = [as_float(candle.get("high")) for candle in recent]
    lows = [as_float(candle.get("low")) for candle in recent]
    if any(value is None for value in highs + lows):
        return False
    total_range = max(highs) - min(lows)
    candle_ranges = [high - low for high, low in zip(highs, lows)]
    average_range = sum(candle_ranges) / len(candle_ranges)
    return total_range <= average_range * 1.5


def rotation_filter_active(candles: list[dict[str, Any]]) -> bool:
    return (
        has_three_alternating_candles(candles)
        or has_overlapping_bodies(candles)
        or has_micro_hh_ll_sequence(candles)
        or has_visible_consolidation_cluster(candles)
    )


def stack_extreme_confirmed(interaction: dict[str, Any], candle: dict[str, Any] | None) -> bool:
    """Return True only after price proves excess beyond the stack extreme."""
    if interaction.get("stack_extreme_confirmation_seen") is True:
        return True
    if not isinstance(candle, dict):
        return False

    side = interaction.get("stack_side") or interaction.get("side")
    tick_size = as_float(interaction.get("tick_size")) or 0.25
    extreme_boundary = as_float(interaction.get("extreme_boundary"))
    if side == "upper" and extreme_boundary is not None:
        high = as_float(candle.get("high"))
        return high is not None and high >= extreme_boundary + tick_size
    if side == "lower" and extreme_boundary is not None:
        low = as_float(candle.get("low"))
        return low is not None and low <= extreme_boundary - tick_size
    return False


def evaluate_step3(interaction: dict[str, Any], recent_candles: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Gate whether Step 4 structure is allowed to begin."""
    state = dict(interaction)
    events = list(state.get("events") or [])
    candles = list(recent_candles or state.get("recent_candles") or [])

    if state.get("rejection_mode") != "ON":
        return terminate_interaction(state, "Step 3", "Step 3 is valid only when Rejection Mode = ON.")

    active_stack = state.get("active_stack")
    active_liquidity = state.get("active_liquidity")
    latest_candle = candles[-1] if candles else state.get("latest_candle")

    if not active_stack:
        state["liquidity_type"] = "NORMAL_LEVEL"
        state["step3_allows_structure"] = True
        state["step3_block_reason"] = None
        reason = "Step 3 allows structure: normal level is eligible for Step 4."
        events.append({"event": "step3_structure_allowed", "reason": reason, "liquidity_type": "NORMAL_LEVEL"})
        return result("ALLOW_STEP_4", state, "Step 4", reason, events)

    if not active_liquidity:
        return terminate_interaction(state, "Step 3", "Static Stack requires active liquidity before classification.")

    state["liquidity_type"] = "STATIC_STACK"

    if not stack_extreme_confirmed(state, latest_candle):
        state["stack_extreme_confirmation_seen"] = False
        state["sweep_extreme_boundary_seen"] = False
        state["step3_allows_structure"] = False
        reason = "Step 3 blocks structure: static stack requires HH/LL beyond the Extreme Boundary; close-boundary interaction is not tradable."
        state["step3_block_reason"] = reason
        events.append({"event": "step3_structure_blocked", "reason": reason, "liquidity_type": "STATIC_STACK"})
        return result("WAIT", state, "Step 3", reason, events)

    previous_confirmation_seen = state.get("stack_extreme_confirmation_seen") is True
    previous_confirmation_candle = state.get("stack_extreme_confirmation_candle")
    state["stack_extreme_confirmation_seen"] = True
    state["stack_extreme_confirmation_candle"] = previous_confirmation_candle if previous_confirmation_seen and isinstance(previous_confirmation_candle, dict) else latest_candle
    state["sweep_extreme_boundary_seen"] = True
    state["step3_allows_structure"] = True
    state["step3_block_reason"] = None
    if previous_confirmation_seen and isinstance(previous_confirmation_candle, dict):
        state["initial_candle_a"] = state.get("initial_candle_a") if isinstance(state.get("initial_candle_a"), dict) else previous_confirmation_candle
        state["candle_a"] = state.get("candle_a") if isinstance(state.get("candle_a"), dict) else previous_confirmation_candle
        state["candle_a_source"] = state.get("candle_a_source") or "stack_extreme_confirmation_candle"
    elif isinstance(latest_candle, dict):
        state["initial_candle_a"] = latest_candle
        state["candle_a"] = latest_candle
        state["candle_a_source"] = "stack_extreme_confirmation_candle"
    reason = "Step 3 allows structure: static stack has HH/LL confirmation beyond the Extreme Boundary."
    events.append({"event": "step3_structure_allowed", "reason": reason, "liquidity_type": "STATIC_STACK"})
    return result("ALLOW_STEP_4", state, "Step 4", reason, events)
