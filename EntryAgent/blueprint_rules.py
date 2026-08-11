"""Blueprint rule helpers for the entry agent."""

from __future__ import annotations

from typing import Any

UPPER_LIQUIDITY_LEVELS = {
    "ONH": 2,
    "LH": 3,
    "PMH": 4,
}
LOWER_LIQUIDITY_LEVELS = {
    "ONL": 2,
    "LL": 3,
    "PML": 4,
}
ROAMING_LIQUIDITY_LEVELS = {"YH", "YL"}
ROAMING_LIQUIDITY_PRIORITY = {"YH": 1, "YL": 1}
TICK_SIZES = {"NQ": 0.25, "RTY": 0.10}


def load_blueprint_rules() -> dict:
    """Return starter blueprint rules."""
    return {"enabled": True, "rules": []}


def root_symbol(symbol: str) -> str:
    """Return the supported root symbol for a contract or root."""
    upper_symbol = symbol.upper()
    for root in TICK_SIZES:
        if upper_symbol.startswith(root):
            return root
    return upper_symbol


def tick_size_for_symbol(symbol: str) -> float:
    """Return the configured tick size for a symbol root."""
    return TICK_SIZES.get(root_symbol(symbol), 0.25)


def rejection_off(reason_text: str) -> dict[str, Any]:
    """Return the standard Rejection Mode OFF payload."""
    return {
        "rejection_mode": "OFF",
        "watch_side": None,
        "trigger_level": None,
        "trigger_price": None,
        "trigger_priority": None,
        "reason_text": reason_text,
    }


def optional_float(value: Any) -> float | None:
    """Convert numeric-like values to float while preserving nulls."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def side_for_level_price(
    level_name: str | None,
    level_price: Any = None,
    session_lock_price: Any = None,
    *,
    tolerance: float = 0.0,
) -> str | None:
    """Return frozen liquidity ownership without name-only roaming assumptions."""
    normalized_name = str(level_name or "").strip().upper()
    price = optional_float(level_price)
    reference = optional_float(session_lock_price)
    if normalized_name in UPPER_LIQUIDITY_LEVELS:
        if price is None:
            return "upper" if reference is None else None
        if reference is None:
            return "upper"
        if abs(price - reference) <= max(0.0, float(tolerance)):
            return "touch"
        return "upper" if price > reference else None
    if normalized_name in LOWER_LIQUIDITY_LEVELS:
        if price is None:
            return "lower" if reference is None else None
        if reference is None:
            return "lower"
        if abs(price - reference) <= max(0.0, float(tolerance)):
            return "touch"
        return "lower" if price < reference else None
    if normalized_name not in ROAMING_LIQUIDITY_LEVELS:
        return None
    if price is None or reference is None:
        return None
    if abs(price - reference) <= max(0.0, float(tolerance)):
        return "touch"
    return "upper" if price > reference else "lower"


def detect_rejection_mode(
    latest_bar: dict[str, Any] | None,
    levels: dict[str, Any],
    symbol: str = "NQ",
    session_lock_price: Any = None,
) -> dict[str, Any]:
    """Detect Rejection Mode Engine v1 from a completed 1-minute bar close."""
    if not isinstance(latest_bar, dict):
        return rejection_off("No latest completed 1-minute bar available.")

    close = optional_float(latest_bar.get("close"))
    if close is None:
        return rejection_off("No latest completed 1-minute bar close available.")

    tick_size = tick_size_for_symbol(symbol)
    qualified: list[dict[str, Any]] = []

    for level_name, priority in UPPER_LIQUIDITY_LEVELS.items():
        level_price = optional_float(levels.get(level_name))
        if (
            level_price is not None
            and side_for_level_price(level_name, level_price, session_lock_price) == "upper"
            and close >= level_price + tick_size
        ):
            qualified.append(
                {
                    "watch_side": "SHORT",
                    "trigger_level": level_name,
                    "trigger_price": level_price,
                    "trigger_priority": priority,
                    "distance": abs(close - level_price),
                }
            )

    for level_name, priority in LOWER_LIQUIDITY_LEVELS.items():
        level_price = optional_float(levels.get(level_name))
        if (
            level_price is not None
            and side_for_level_price(level_name, level_price, session_lock_price) == "lower"
            and close <= level_price - tick_size
        ):
            qualified.append(
                {
                    "watch_side": "LONG",
                    "trigger_level": level_name,
                    "trigger_price": level_price,
                    "trigger_priority": priority,
                    "distance": abs(close - level_price),
                }
            )

    for level_name, priority in ROAMING_LIQUIDITY_PRIORITY.items():
        level_price = optional_float(levels.get(level_name))
        side = side_for_level_price(level_name, level_price, session_lock_price)
        if level_price is not None and side == "upper" and close >= level_price + tick_size:
            qualified.append(
                {
                    "watch_side": "SHORT",
                    "trigger_level": level_name,
                    "trigger_price": level_price,
                    "trigger_priority": priority,
                    "distance": abs(close - level_price),
                }
            )
        elif level_price is not None and side == "lower" and close <= level_price - tick_size:
            qualified.append(
                {
                    "watch_side": "LONG",
                    "trigger_level": level_name,
                    "trigger_price": level_price,
                    "trigger_priority": priority,
                    "distance": abs(close - level_price),
                }
            )

    if not qualified:
        return rejection_off("Close has not crossed a key liquidity level by at least 1 tick.")

    trigger = min(qualified, key=lambda item: (item["trigger_priority"], item["distance"]))
    return {
        "rejection_mode": "ON",
        "watch_side": trigger["watch_side"],
        "trigger_level": trigger["trigger_level"],
        "trigger_price": trigger["trigger_price"],
        "trigger_priority": trigger["trigger_priority"],
        "reason_text": (
            f"Close {close} crossed {trigger['trigger_level']} {trigger['trigger_price']} "
            f"by at least 1 tick; watching {trigger['watch_side']} participation."
        ),
    }


def _tick_normalized(value: float, tick_size: float) -> float:
    """Normalize price comparisons to tick precision."""
    return round(round(value / tick_size) * tick_size, 10)


def _close_beyond_boundary(close: float, boundary_price: float, side: str, tick_size: float) -> bool:
    close = _tick_normalized(close, tick_size)
    boundary_price = _tick_normalized(boundary_price, tick_size)
    if side == "upper":
        return close >= _tick_normalized(boundary_price + tick_size, tick_size)
    if side == "lower":
        return close <= _tick_normalized(boundary_price - tick_size, tick_size)
    raise ValueError(f"unsupported side: {side}")


def _wick_crosses_boundary(candle: dict[str, Any], boundary_price: float, side: str, tick_size: float) -> bool:
    boundary_price = _tick_normalized(boundary_price, tick_size)
    if side == "upper":
        high = optional_float(candle.get("high"))
        return high is not None and high >= _tick_normalized(boundary_price + tick_size, tick_size)
    if side == "lower":
        low = optional_float(candle.get("low"))
        return low is not None and low <= _tick_normalized(boundary_price - tick_size, tick_size)
    raise ValueError(f"unsupported side: {side}")


def _wick_extreme(candle: dict[str, Any], side: str) -> float | None:
    if side == "upper":
        return optional_float(candle.get("high"))
    if side == "lower":
        return optional_float(candle.get("low"))
    raise ValueError(f"unsupported side: {side}")


def _more_extreme(candidate: float, current: float | None, side: str) -> bool:
    if current is None:
        return True
    if side == "upper":
        return candidate > current
    if side == "lower":
        return candidate < current
    raise ValueError(f"unsupported side: {side}")


def _close_back_across_level(close: float, level_price: float, side: str, tick_size: float) -> bool:
    close = _tick_normalized(close, tick_size)
    level_price = _tick_normalized(level_price, tick_size)
    if side == "upper":
        return close <= _tick_normalized(level_price - tick_size, tick_size)
    if side == "lower":
        return close >= _tick_normalized(level_price + tick_size, tick_size)
    raise ValueError(f"unsupported side: {side}")


def _gap_only_candle(candle: dict[str, Any], boundary_price: float, side: str, tick_size: float) -> bool:
    open_price = optional_float(candle.get("open"))
    if open_price is None:
        return False
    return _close_beyond_boundary(open_price, boundary_price, side, tick_size)


def step_2_1a_initial_state(
    source_level: str,
    level_price: float,
    side: str = "upper",
    tick_size: float = 0.25,
    expiration_candles: int = 5,
) -> dict[str, Any]:
    """Return an initial Step 2.1A replay state."""
    return {
        "step_2_activated": False,
        "blocked": False,
        "candle_a": None,
        "active_level": source_level,
        "level_price": float(level_price),
        "side": side,
        "tick_size": tick_size,
        "expiration_candles": expiration_candles,
        "persist_pending_owner_until_resolution": False,
        "pre_activation_probe_boundary": {
            "active": False,
            "side": side,
            "source_level": source_level,
            "boundary_price": None,
            "detected_at_index": None,
        },
        "events": [],
    }


def evaluate_step_2_1a_candle(state: dict[str, Any], candle: dict[str, Any], index: int) -> dict[str, Any]:
    """Evaluate one completed candle against Step 2.1A replay rules."""
    # STEP 2 BOUNDARY CONTRACT
    # close_boundary:
    # - informational/reference only
    # - never activates Step 2
    # - never confirms rejection
    # - never confirms continuation
    # extreme_boundary:
    # - sole activation trigger
    # - rejection and continuation decisions are based on closes beyond the active extreme_boundary
    # - active extreme_boundary may move only in the raid direction while owner is active
    events = state.setdefault("events", [])
    probe = state["pre_activation_probe_boundary"]
    tick_size = float(state["tick_size"])
    side = str(state["side"])
    close = optional_float(candle.get("close"))
    timestamp = candle.get("timestamp")

    next_level = candle.get("active_level")
    next_level_price = optional_float(candle.get("level_price"))
    if next_level and next_level != state["active_level"]:
        if probe.get("active"):
            events.append({"event": "probe_cleared_level_transition", "timestamp": timestamp})
        state["active_level"] = next_level
        if next_level_price is not None:
            state["level_price"] = next_level_price
        probe.update(
            {
                "active": False,
                "side": side,
                "source_level": state["active_level"],
                "boundary_price": None,
                "detected_at_index": None,
            }
        )

    if state.get("step_2_activated") or state.get("blocked"):
        return state

    if probe.get("active") and probe.get("boundary_price") is None:
        state["blocked"] = True
        events.append({"event": "probe_state_invalid_missing_boundary", "timestamp": timestamp})
        return state

    if (
        probe.get("active")
        and probe.get("detected_at_index") is not None
        and not state.get("persist_pending_owner_until_resolution")
        and index - int(probe["detected_at_index"]) >= int(state["expiration_candles"])
    ):
        probe.update({"active": False, "boundary_price": None, "detected_at_index": None})
        events.append({"event": "probe_expired_timeout", "timestamp": timestamp})

    activation_boundary = probe.get("boundary_price") if probe.get("active") else state["level_price"]
    used_probe = bool(probe.get("active"))

    if (
        probe.get("active")
        and candle.get("force_original_level_activation")
        and close is not None
        and _close_beyond_boundary(close, float(state["level_price"]), side, tick_size)
    ):
        state["blocked"] = True
        events.append({"event": "probe_override_violation", "timestamp": timestamp})
        return state

    if close is not None and activation_boundary is not None and _close_beyond_boundary(close, float(activation_boundary), side, tick_size):
        state["step_2_activated"] = True
        state["candle_a"] = candle
        if used_probe:
            probe["active"] = False
            events.append({"event": "pre_activation_probe_consumed", "timestamp": timestamp})
        events.append(
            {
                "event": "step_2_activated",
                "timestamp": timestamp,
                "boundary_price": activation_boundary,
                "source": "probe" if used_probe else "level",
            }
        )
        return state

    if _gap_only_candle(candle, state["level_price"], side, tick_size):
        events.append({"event": "gap_evaluated_without_probe", "timestamp": timestamp})
        return state

    if close is not None and _wick_crosses_boundary(candle, state["level_price"], side, tick_size):
        extreme = _wick_extreme(candle, side)
        if extreme is not None:
            if not probe.get("active"):
                probe.update(
                    {
                        "active": True,
                        "side": side,
                        "source_level": state["active_level"],
                        "boundary_price": extreme,
                        "detected_at_index": index,
                    }
                )
                events.append(
                    {
                        "event": "pre_activation_probe_detected",
                        "level_name": state["active_level"],
                        "side": side,
                        "boundary_price": extreme,
                        "timestamp": timestamp,
                    }
                )
            elif _more_extreme(extreme, optional_float(probe.get("boundary_price")), side):
                probe["boundary_price"] = extreme
                events.append(
                    {
                        "event": "pre_activation_probe_updated",
                        "level_name": state["active_level"],
                        "side": side,
                        "boundary_price": extreme,
                        "timestamp": timestamp,
                    }
                )

    return state


def replay_step_2_1a(candles: list[dict[str, Any]], initial_state: dict[str, Any]) -> dict[str, Any]:
    """Replay completed candles and return final Step 2.1A state."""
    state = initial_state
    for index, candle in enumerate(candles):
        evaluate_step_2_1a_candle(state, candle, index)
    return state


if __name__ == "__main__":
    print(load_blueprint_rules())
