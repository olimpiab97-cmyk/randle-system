"""Gateway Engine for EntryAgent.

Rules are derived from blueprint_spec.md, gateway_rules_extracted.md, and
gateway_decisions.md. This module does not infer GH/GL when a pre-built
gateway object is missing.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
OPENING_START = time(6, 30)
MIDDLE_START = time(7, 0)
CUTOFF = time(12, 0)
LEVEL_KEYS = ("PMH", "PML", "LH", "LL", "ONH", "ONL", "YH", "YL")


def as_float(value: Any) -> float | None:
    """Return value as float, preserving null/invalid values."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_session_phase(tv_context: dict[str, Any] | None, now: datetime | None = None) -> str:
    """Return operational session phase from gateway_decisions.md."""
    context = tv_context if isinstance(tv_context, dict) else {}
    session_context = context.get("session_context")

    if isinstance(session_context, dict) and session_context.get("premarket_locked") is False:
        return "PREMARKET"

    current = now.astimezone(PT) if now is not None else datetime.now(PT)
    current_time = current.time()

    if current_time >= CUTOFF:
        return "CLOSED"
    if OPENING_START <= current_time < MIDDLE_START:
        return "OPENING_WINDOW"
    if MIDDLE_START <= current_time < CUTOFF:
        return "MIDSESSION"
    return "PREMARKET"


def non_null_levels(levels: dict[str, Any]) -> dict[str, float]:
    """Return active short-term flat levels from current level map."""
    active: dict[str, float] = {}
    for key in LEVEL_KEYS:
        value = as_float(levels.get(key))
        if value is not None:
            active[key] = value
    return active


def nearest_from_context(tv_context: dict[str, Any] | None, latest_price: float | None) -> str | None:
    """Prefer nearest newly relevant liquidity from full premarket context."""
    if not isinstance(tv_context, dict):
        return None

    next_liquidity = tv_context.get("next_liquidity")
    if not isinstance(next_liquidity, dict):
        return None

    candidates = []
    for side in ("above", "below"):
        item = next_liquidity.get(side)
        if isinstance(item, dict) and item.get("name") is not None:
            price = as_float(item.get("price"))
            candidates.append({"name": item.get("name"), "price": price})

    if not candidates:
        return None
    if latest_price is None:
        return str(candidates[0]["name"])

    nearest = min(
        candidates,
        key=lambda item: abs((item["price"] if item["price"] is not None else latest_price) - latest_price),
    )
    return str(nearest["name"])


def nearest_from_levels(levels: dict[str, Any], latest_price: float | None) -> str | None:
    """Short-term fallback: closest active level from current level map."""
    active = non_null_levels(levels)
    if not active:
        return None
    if latest_price is None:
        return next(iter(active))
    return min(active, key=lambda name: abs(active[name] - latest_price))


def get_nearest_level(
    tv_context: dict[str, Any] | None,
    levels: dict[str, Any],
    latest_price: Any,
) -> str | None:
    """Return nearest level per gateway_decisions.md."""
    price = as_float(latest_price)
    return nearest_from_context(tv_context, price) or nearest_from_levels(levels, price)


def is_inside_active_stack(tv_context: dict[str, Any] | None, latest_price: Any) -> bool:
    """Detect explicit stack/zone containment when full context provides boundaries."""
    if not isinstance(tv_context, dict):
        return False

    price = as_float(latest_price)
    if price is None:
        return False

    for side in ("high_side", "low_side"):
        side_context = tv_context.get(side)
        if not isinstance(side_context, dict) or side_context.get("type") != "STACK":
            continue

        close_boundary = as_float(side_context.get("close_boundary"))
        extreme_boundary = as_float(side_context.get("extreme_boundary"))
        if close_boundary is None or extreme_boundary is None:
            continue

        lower = min(close_boundary, extreme_boundary)
        upper = max(close_boundary, extreme_boundary)
        if lower <= price <= upper:
            return True

    return False


def is_near_liquidity(
    liquidity: dict[str, Any] | None,
    tv_context: dict[str, Any] | None,
    latest_price: Any,
) -> bool:
    """Return true only at/touching liquidity or inside an active stack/zone."""
    if isinstance(liquidity, dict) and liquidity.get("current_location") == "AT_LIQUIDITY":
        return True
    return is_inside_active_stack(tv_context, latest_price)


def gateway_state_from_context(tv_context: dict[str, Any] | None) -> str | None:
    """Read explicit pre-built gateway state from context."""
    if not isinstance(tv_context, dict):
        return None
    gateway = tv_context.get("gateway")
    if not isinstance(gateway, dict):
        return None
    state = gateway.get("state")
    return str(state).upper() if state is not None else None


def allowed_sides(gateway_status: str, gateway_state: str | None, rejection_state: dict[str, Any] | None) -> str:
    """Return allowed sides per gateway_decisions.md."""
    if gateway_status != "OPEN" or gateway_state != "ARMED":
        return "NONE"

    if isinstance(rejection_state, dict) and rejection_state.get("rejection_mode") == "ON":
        watch_side = rejection_state.get("watch_side")
        if watch_side in ("LONG", "SHORT"):
            return str(watch_side)

    return "BOTH"


def evaluate_gateway(
    latest_snapshot: dict[str, Any],
    tv_context: dict[str, Any] | None,
    levels: dict[str, Any],
    rejection_state: dict[str, Any] | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate Gateway permission and diagnostics."""
    phase = get_session_phase(tv_context, now)
    liquidity = latest_snapshot.get("liquidity")
    latest_price = latest_snapshot.get("latest_price")
    nearest_level = get_nearest_level(tv_context, levels, latest_price)
    near_liquidity = is_near_liquidity(liquidity, tv_context, latest_price)
    state = gateway_state_from_context(tv_context)

    if phase == "CLOSED":
        status = "BLOCKED"
        reason = "CLOSED after 12:00 PM PT hard cutoff; no new trades allowed."
    elif phase == "PREMARKET":
        status = "BLOCKED"
        reason = "PREMARKET before premarket lock; Gateway permission is not active."
    elif state is None:
        status = "BLOCKED"
        reason = "Missing pre-built gateway object; Entry Engine must not infer GH/GL."
    elif state == "OFF":
        status = "BLOCKED"
        reason = "Gateway OFF: inside gateway/no engagement."
    elif state == "ARMED":
        status = "OPEN"
        reason = "Gateway ARMED: outside gateway and Step 2 may evaluate."
    else:
        status = "BLOCKED"
        reason = f"Unsupported gateway state: {state}."

    return {
        "gateway_status": status,
        "gateway_reason": reason,
        "allowed_sides": allowed_sides(status, state, rejection_state),
        "session_phase": phase,
        "near_liquidity": near_liquidity,
        "nearest_level": nearest_level,
    }
