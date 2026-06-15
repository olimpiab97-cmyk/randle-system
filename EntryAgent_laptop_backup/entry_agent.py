"""Entry agent command line entry point."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from blueprint_rules import (
    LOWER_LIQUIDITY_LEVELS,
    UPPER_LIQUIDITY_LEVELS,
    detect_rejection_mode,
    evaluate_step_2_1a_candle,
    optional_float,
    step_2_1a_initial_state,
)
from gateway_engine import evaluate_gateway
from levels import classify_liquidity_location, root_symbol
from market_feed import get_latest_market_snapshot, recent_closed_bars
from step25_engine import evaluate_step25
from step3_engine import evaluate_step3
from step4_engine import evaluate_step4, initialize_leg1_window
from step5_engine import evaluate_step5
from step6_engine import evaluate_step6

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "Data"
STATE_PATH = BASE_DIR / "entry_agent_state.json"
SIGNALS_PATH = BASE_DIR / "signals.json"
TV_CONTEXT_PATH = BASE_DIR / "tv_context.json"
TV_CONTEXT_BY_SYMBOL_PATH = BASE_DIR / "tv_context_by_symbol.json"
STEP2_OWNER_DIAGNOSTICS_PATH = DATA_DIR / "entry_step2_owner_diagnostics.jsonl"
RITHMIC_ATR_SNAPSHOT_PATH = DATA_DIR / "rithmic_atr_snapshot.json"
PERSISTENCE_STATE_PATH = DATA_DIR / "persistence_state.json"
EXECUTOR_STATE_PATH = DATA_DIR / "executor_state.json"
ACTIVE_LIQUIDITY_PRIORITY = {
    "YH": 0,
    "YL": 0,
    "ONH": 1,
    "ONL": 1,
    "LH": 2,
    "LL": 2,
    "PMH": 3,
    "PML": 3,
}
LOCAL_MARKET_TIMEZONE = ZoneInfo("America/Los_Angeles")
OBSERVATION_RESET_HOUR = 6
OBSERVATION_RESET_MINUTE = 15
ENTRY_AUTHORIZATION_HOUR = 6
ENTRY_AUTHORIZATION_MINUTE = 30
STEP_LABELS = {
    "PRE_RTH_LOCK": "Pre-RTH Lock",
    "SESSION_CLOSED": "Session Closed",
    "Step 1": "Step 1 (Session / Level Prep)",
    "Step 2": "Step 2 (Liquidity Close / Pathway Activation)",
    "Step 2.5": "Step 2.5 (S/R-R/S Continuation Logic)",
    "Step 3": "Step 3 (Participation)",
    "Step 4": "Step 4 (Leg 1 Formation)",
    "Step 5": "Step 5 (Leg 2 Confirmation)",
    "Step 6": "Step 6 (Entry Trigger)",
    "Step 7": "Step 7 (Invalidation / Reset)",
}


def current_step_label(current_step: Any) -> str | None:
    """Return the operator-facing label for a blueprint step."""
    return STEP_LABELS.get(str(current_step))


def entry_window_lock_for_snapshot(snapshot: dict[str, Any]) -> tuple[str, str] | None:
    market_time = local_market_time(snapshot.get("latest_bar_time"))
    if market_time is None:
        return None
    if (market_time.hour, market_time.minute) < (OBSERVATION_RESET_HOUR, OBSERVATION_RESET_MINUTE):
        return "PRE_RTH_LOCK", "Awaiting 6:15 RTH activation line."
    if (market_time.hour, market_time.minute) >= (8, 0):
        return "SESSION_CLOSED", "Entry window closed at 8:00 AM PT."
    return None


def has_stale_session_lifecycle(persisted_state: dict[str, Any], symbol: str, snapshot: dict[str, Any]) -> bool:
    symbol_state = symbol_scoped_persisted_state(persisted_state, symbol)
    if not isinstance(symbol_state, dict):
        return False
    if not any(isinstance(symbol_state.get(key), dict) for key in ("step4", "step5", "step6")):
        return False
    session_date = local_session_date(snapshot.get("latest_bar_time"))
    recorded_date = symbol_state.get("observation_reset_session_date")
    if recorded_date == session_date:
        return False
    tv_context = load_tv_context(symbol)
    levels = tv_context.get("levels") if isinstance(tv_context, dict) else {}
    return any(
        isinstance(level, dict) and str(level.get("status") or "").upper() == "ACTIVE"
        for level in (levels.values() if isinstance(levels, dict) else [])
    )


def load_entry_state() -> dict[str, Any]:
    """Load persisted EntryAgent state if available."""
    if not STATE_PATH.exists():
        return {}
    try:
        with STATE_PATH.open("r", encoding="utf-8") as file:
            state = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}
    return state if isinstance(state, dict) else {}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def compact_candle(candle: Any) -> dict[str, Any] | None:
    if not isinstance(candle, dict):
        return None
    return {key: candle.get(key) for key in ("timestamp", "open", "high", "low", "close", "active_level", "level_price")}


def compact_liquidity(liquidity: Any) -> dict[str, Any] | None:
    if not isinstance(liquidity, dict):
        return None
    group = liquidity.get("group") if isinstance(liquidity.get("group"), dict) else None
    return {
        "name": liquidity.get("name"),
        "price": liquidity.get("price"),
        "display_name": liquidity.get("display_name"),
        "side": liquidity.get("side"),
        "group_name": group.get("name") if isinstance(group, dict) else liquidity.get("liquidity_group"),
        "group_components": group.get("components") if isinstance(group, dict) else None,
        "close_boundary": group.get("close_boundary") if isinstance(group, dict) else liquidity.get("close_boundary"),
        "extreme_boundary": group.get("extreme_boundary") if isinstance(group, dict) else liquidity.get("extreme_boundary"),
    }


def compact_owner(owner: Any) -> dict[str, Any] | None:
    if not isinstance(owner, dict):
        return None
    return {
        "pathway": owner.get("pathway"),
        "active_liquidity": compact_liquidity(owner.get("active_liquidity")),
        "active_liquidity_name": owner.get("active_liquidity_name"),
        "active_liquidity_price": owner.get("active_liquidity_price"),
        "active_liquidity_display_name": owner.get("active_liquidity_display_name"),
        "liquidity_group": owner.get("liquidity_group"),
        "stack_components": owner.get("stack_components"),
        "close_boundary": owner.get("close_boundary"),
        "extreme_boundary": owner.get("extreme_boundary"),
        "setup_direction": owner.get("setup_direction"),
        "side": owner.get("side"),
        "activated_at": owner.get("activated_at"),
        "candle_a": compact_candle(owner.get("candle_a")),
    }


def step2_owner_lookup_diagnostics(persisted_state: dict[str, Any], selected_liquidity: dict[str, Any] | None) -> dict[str, Any]:
    step2_state = persisted_state.get("step_2_1a") if isinstance(persisted_state.get("step_2_1a"), dict) else {}
    direct_owner = persisted_state.get("step2_locked_owner")
    nested_owner = step2_state.get("step2_locked_owner")
    owner = direct_owner if isinstance(direct_owner, dict) else nested_owner
    step4 = persisted_state.get("step4") if isinstance(persisted_state.get("step4"), dict) else {}
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    step5 = persisted_state.get("step5") if isinstance(persisted_state.get("step5"), dict) else {}
    step5_state = step5.get("state") if isinstance(step5.get("state"), dict) else {}
    invalidation_seen = step2_owner_invalidation_seen(persisted_state)
    rejection_reasons: list[str] = []
    if invalidation_seen:
        rejection_reasons.append("step2_owner_invalidation_seen")
    if not isinstance(owner, dict):
        rejection_reasons.append("no_step2_locked_owner")
    elif owner.get("pathway") != "rejection":
        rejection_reasons.append("owner_pathway_not_rejection")
    else:
        active = owner.get("active_liquidity")
        if not (
            isinstance(active, dict)
            and valid_active_liquidity_selection(active.get("name"), active.get("price"))
        ) and not valid_active_liquidity_selection(owner.get("active_liquidity_name"), owner.get("active_liquidity_price")):
            rejection_reasons.append("owner_active_liquidity_invalid")
    previous_step25 = persisted_state.get("step25") if isinstance(persisted_state.get("step25"), dict) else {}
    step25_state = previous_step25.get("state") if isinstance(previous_step25.get("state"), dict) else {}
    previous_step4 = persisted_state.get("step4") if isinstance(persisted_state.get("step4"), dict) else {}
    previous_step4_state = previous_step4.get("state") if isinstance(previous_step4.get("state"), dict) else {}
    previous_liquidity = previous_step4_state.get("active_liquidity") if isinstance(previous_step4_state.get("active_liquidity"), dict) else None
    if not isinstance(previous_liquidity, dict):
        previous_liquidity = step25_state.get("active_liquidity") if isinstance(step25_state.get("active_liquidity"), dict) else None
    pending_reasons: list[str] = []
    if step25_state.get("step25_pathway_selection_complete") is not True:
        pending_reasons.append("previous_step25_not_complete")
    if normalized_pathway_name(step25_state.get("controlling_mode")) != "Normal":
        pending_reasons.append("previous_controlling_mode_not_normal")
    if previous_step4_state.get("leg1_state_locked") is True or previous_step4_state.get("leg1_status") == "COMPLETE":
        pending_reasons.append("previous_leg1_complete")
    if previous_step4_state.get("leg1_window_invalidated") is True or previous_step4_state.get("leg1_window_remaining") == 0:
        pending_reasons.append("previous_leg1_window_inactive_or_expired")
    if not previous_step4_state.get("leg1_window_started_at"):
        pending_reasons.append("previous_leg1_window_missing_start")
    if not same_active_liquidity(previous_liquidity, selected_liquidity):
        pending_reasons.append("previous_active_liquidity_not_same")
    return {
        "direct_owner": compact_owner(direct_owner),
        "nested_owner": compact_owner(nested_owner),
        "locked_owner_rejection_reasons": rejection_reasons,
        "step4_invalidation_fields": {
            "leg1_window_invalidated": step4_state.get("leg1_window_invalidated"),
            "invalidation_source": step4_state.get("invalidation_source"),
            "invalidated_at": step4_state.get("invalidated_at"),
        },
        "step5_invalidation_fields": {
            "invalidated_at": step5_state.get("invalidated_at"),
            "invalidation_source": step5_state.get("invalidation_source"),
            "invalidated_liquidity": step5_state.get("invalidated_liquidity"),
        },
        "pending_recovery": {
            "rejection_reasons": pending_reasons,
            "previous_active_liquidity": compact_liquidity(previous_liquidity),
            "previous_controlling_mode": step25_state.get("controlling_mode"),
            "previous_initial_candle_a": compact_candle(step25_state.get("initial_candle_a")),
            "previous_leg1_window_started_at": previous_step4_state.get("leg1_window_started_at"),
            "previous_leg1_window_candle_index": previous_step4_state.get("leg1_window_candle_index"),
            "previous_leg1_window_remaining": previous_step4_state.get("leg1_window_remaining"),
        },
    }


def log_step2_owner_diagnostic(event: str, payload: dict[str, Any]) -> None:
    if os.environ.get("ENTRY_STEP2_OWNER_DIAGNOSTICS") != "1":
        return
    try:
        record = {
            "logged_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event": event,
            **payload,
        }
        with STEP2_OWNER_DIAGNOSTICS_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
    except OSError:
        return


def load_tv_context(symbol: str | None = None) -> dict[str, Any] | None:
    """Load optional TradingView context for the requested root only."""
    requested_root = root_symbol(symbol) if symbol else None
    if requested_root:
        by_symbol = _read_json(TV_CONTEXT_BY_SYMBOL_PATH).get("symbols")
        if isinstance(by_symbol, dict):
            context = by_symbol.get(requested_root)
            if isinstance(context, dict):
                return context
            for stored_symbol, stored_context in by_symbol.items():
                if root_symbol(str(stored_symbol)) == requested_root and isinstance(stored_context, dict):
                    return stored_context
                if isinstance(stored_context, dict) and root_symbol(str(stored_context.get("symbol") or "")) == requested_root:
                    return stored_context

    context = _read_json(TV_CONTEXT_PATH)
    if not context:
        return None
    context_symbol = context.get("normalized_symbol") or context.get("symbol")
    if requested_root and root_symbol(str(context_symbol or "")) != requested_root:
        return None
    return context


def tv_context_freshness_status(tv_context: dict[str, Any] | None, max_age_seconds: int = 90) -> str:
    """Return the TradingView context freshness status."""
    if not isinstance(tv_context, dict) or not tv_context.get("received_at"):
        return "TV_CONTEXT_MISSING"

    try:
        received_at = datetime.fromisoformat(str(tv_context["received_at"]).replace("Z", "+00:00"))
    except ValueError:
        return "TV_CONTEXT_MISSING"

    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=timezone.utc)

    age_seconds = (datetime.now(timezone.utc) - received_at.astimezone(timezone.utc)).total_seconds()
    return "TV_CONTEXT_LIVE" if age_seconds <= max_age_seconds else "TV_CONTEXT_STALE"


def side_for_level(level_name: str | None) -> str | None:
    """Return Step 2.1A side for a named liquidity level."""
    if level_name in UPPER_LIQUIDITY_LEVELS:
        return "upper"
    if level_name in LOWER_LIQUIDITY_LEVELS:
        return "lower"
    return None


def active_levels_from_tv_context(tv_context: dict[str, Any] | None) -> dict[str, float]:
    """Return only ACTIVE TradingView helper levels as a flat name/price mapping."""
    if not isinstance(tv_context, dict) or not isinstance(tv_context.get("levels"), dict):
        return {}

    active: dict[str, float] = {}
    for name, details in tv_context["levels"].items():
        if name not in ACTIVE_LIQUIDITY_PRIORITY or not isinstance(details, dict):
            continue
        if str(details.get("status") or "").upper() != "ACTIVE":
            continue
        try:
            active[name] = float(details.get("price"))
        except (TypeError, ValueError):
            continue
    return active


def selected_active_liquidity_from_context(
    tv_context: dict[str, Any] | None,
    latest_price: Any,
    latest_ohlc: dict[str, Any] | None = None,
    tick_size: float = 0.25,
) -> dict[str, Any] | None:
    """Select ACTIVE rejection liquidity after a close or wick raid reaches the level."""
    if not isinstance(tv_context, dict) or not isinstance(tv_context.get("levels"), dict):
        return None
    try:
        current_price = float(latest_price)
    except (TypeError, ValueError):
        return None
    ohlc = latest_ohlc if isinstance(latest_ohlc, dict) else {}

    def level_interacted(level_name: str, level_price: float) -> bool:
        close = optional_float(ohlc.get("close"))
        high = optional_float(ohlc.get("high"))
        low = optional_float(ohlc.get("low"))
        side = side_for_level(level_name)
        if side == "upper":
            return (close is not None and close >= level_price) or (high is not None and high >= level_price + tick_size)
        if side == "lower":
            return (close is not None and close <= level_price) or (low is not None and low <= level_price - tick_size)
        return False

    def stack_close_beyond_close_boundary(side: str | None, close_boundary: float) -> bool:
        close = optional_float(ohlc.get("close"))
        if close is None:
            return False
        if side == "upper":
            return close >= close_boundary + tick_size
        if side == "lower":
            return close <= close_boundary - tick_size
        return False

    def component_priority(name: Any) -> int:
        return ACTIVE_LIQUIDITY_PRIORITY.get(str(name), 999)

    def close_component_for_stack(components: list[dict[str, Any]], side: str | None) -> dict[str, Any]:
        if side == "upper":
            close_price = min(float(component["price"]) for component in components)
        elif side == "lower":
            close_price = max(float(component["price"]) for component in components)
        else:
            return min(components, key=lambda item: (component_priority(item["name"]), str(item["name"])))
        close_components = [component for component in components if float(component["price"]) == close_price]
        preferred_prefix = "PM" if side in {"upper", "lower"} else ""
        return min(
            close_components,
            key=lambda item: (
                0 if str(item["name"]).startswith(preferred_prefix) else 1,
                component_priority(item["name"]),
                str(item["name"]),
            ),
        )

    def combined_stack_name(components: list[dict[str, Any]], side: str | None) -> str:
        close_component = close_component_for_stack(components, side)
        if side == "lower":
            ordered = sorted(
                components,
                key=lambda item: (
                    -float(item["price"]),
                    0 if item["name"] == close_component["name"] else 1,
                    component_priority(item["name"]),
                    str(item["name"]),
                ),
            )
        elif side == "upper":
            ordered = sorted(
                components,
                key=lambda item: (
                    float(item["price"]),
                    0 if item["name"] == close_component["name"] else 1,
                    component_priority(item["name"]),
                    str(item["name"]),
                ),
            )
        else:
            ordered = sorted(components, key=lambda item: (component_priority(item["name"]), str(item["name"])))
        return f"{'/'.join(str(component['name']) for component in ordered)} Liquidity"

    grouped: dict[str, dict[str, Any]] = {}
    for name, details in tv_context["levels"].items():
        if name not in ACTIVE_LIQUIDITY_PRIORITY or not isinstance(details, dict):
            continue
        if str(details.get("status") or "").upper() != "ACTIVE":
            continue
        try:
            price = float(details.get("price"))
        except (TypeError, ValueError):
            continue

        stack_group = str(details.get("stack_group") or "NONE").strip()
        group_key = f"stack:{stack_group}" if stack_group and stack_group.upper() != "NONE" else f"level:{name}"
        group = grouped.setdefault(
            group_key,
            {
                "stack_group": stack_group if stack_group and stack_group.upper() != "NONE" else None,
                "components": [],
            },
        )
        group["components"].append(
            {
                "name": name,
                "price": price,
                "priority": ACTIVE_LIQUIDITY_PRIORITY[name],
                "side": side_for_level(name),
            }
        )

    candidates: list[dict[str, Any]] = []
    for group in grouped.values():
        components = sorted(group["components"], key=lambda item: (item["priority"], item["name"]))
        if not components:
            continue
        prices = [component["price"] for component in components]
        low = min(prices)
        high = max(prices)
        priority_component = components[0]
        side = priority_component.get("side")
        group_payload = None
        if group.get("stack_group"):
            extreme_boundary = high if side == "upper" else low
            close_boundary = low if side == "upper" else high
            if not stack_close_beyond_close_boundary(side, close_boundary):
                continue
            extreme_component = max(components, key=lambda item: item["price"]) if side == "upper" else min(components, key=lambda item: item["price"])
            close_component = close_component_for_stack(components, side)
            group_payload = {
                "name": group["stack_group"],
                "components": [component["name"] for component in components],
                "prices": {component["name"]: component["price"] for component in components},
                "side": side,
                "display_name": combined_stack_name(components, side),
                "close_boundary": close_boundary,
                "extreme_boundary": extreme_boundary,
                "low": low,
                "high": high,
            }
            group_payload["extreme_component"] = extreme_component["name"]
            group_payload["close_component"] = close_component["name"]
            closest_component = extreme_component
            distance = 0.0 if low <= current_price <= high else abs(current_price - close_boundary)
        else:
            interacted_components = [
                component
                for component in components
                if level_interacted(str(component["name"]), float(component["price"]))
            ]
            if not interacted_components:
                continue
            distance = 0.0 if low <= current_price <= high else min(abs(current_price - low), abs(current_price - high))
            closest_component = min(interacted_components, key=lambda item: (abs(item["price"] - current_price), item["priority"]))
            side = priority_component.get("side") or closest_component.get("side")
        candidates.append(
            {
                "name": closest_component["name"],
                "price": closest_component["price"],
                "display_name": (group_payload or {}).get("display_name"),
                "priority": priority_component["priority"],
                "distance": distance,
                "side": side,
                "group": group_payload,
            }
        )

    if not candidates:
        return None
    selected = min(candidates, key=lambda item: (item["distance"], item["priority"], item["name"]))
    return {
        "name": selected["name"],
        "price": selected["price"],
        "display_name": selected.get("display_name"),
        "side": selected["side"],
        "group": selected["group"],
    }


def rotated_active_liquidity_after_inactive_acceptance(
    tv_context: dict[str, Any] | None,
    persisted_liquidity: dict[str, Any] | None,
    latest_ohlc: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Rotate from an accepted inactive level to the next active same-side target."""
    if not isinstance(tv_context, dict) or not isinstance(tv_context.get("levels"), dict):
        return None
    if not isinstance(persisted_liquidity, dict):
        return None
    previous_name = str(persisted_liquidity.get("name") or "").strip()
    previous_side = side_for_level(previous_name)
    previous_price = optional_float(persisted_liquidity.get("price"))
    close = optional_float((latest_ohlc or {}).get("close") if isinstance(latest_ohlc, dict) else None)
    if previous_side is None or previous_price is None or close is None:
        return None

    previous_details = tv_context["levels"].get(previous_name)
    if isinstance(previous_details, dict) and str(previous_details.get("status") or "").upper() == "ACTIVE":
        return None
    previous_stack_group = None
    if isinstance(previous_details, dict):
        stack_text = str(previous_details.get("stack_group") or "NONE").strip()
        if stack_text and stack_text.upper() != "NONE":
            previous_stack_group = stack_text
    if previous_side == "lower" and close > previous_price:
        return None
    if previous_side == "upper" and close < previous_price:
        return None

    candidates: list[dict[str, Any]] = []
    for name, details in tv_context["levels"].items():
        if name not in ACTIVE_LIQUIDITY_PRIORITY or not isinstance(details, dict):
            continue
        if str(details.get("status") or "").upper() != "ACTIVE":
            continue
        if side_for_level(name) != previous_side:
            continue
        price = optional_float(details.get("price"))
        if price is None:
            continue
        if previous_side == "lower" and price >= previous_price:
            continue
        if previous_side == "upper" and price <= previous_price:
            continue
        stack_text = str(details.get("stack_group") or "NONE").strip()
        same_stack = bool(previous_stack_group and stack_text == previous_stack_group)
        candidates.append(
            {
                "name": name,
                "price": price,
                "side": previous_side,
                "priority": ACTIVE_LIQUIDITY_PRIORITY[name],
                "distance": abs(price - previous_price),
                "same_stack": same_stack,
            }
        )

    if not candidates:
        return None
    same_stack_candidates = [candidate for candidate in candidates if candidate.get("same_stack")]
    if same_stack_candidates and previous_side == "lower":
        selected = min(same_stack_candidates, key=lambda item: (item["price"], item["priority"], item["name"]))
    elif same_stack_candidates and previous_side == "upper":
        selected = max(same_stack_candidates, key=lambda item: (item["price"], -item["priority"], item["name"]))
    else:
        selected = min(candidates, key=lambda item: (item["priority"], item["distance"], item["name"]))
    selected["group"] = active_stack_from_context(tv_context, str(selected["name"]))
    selected.pop("priority", None)
    selected.pop("distance", None)
    selected.pop("same_stack", None)
    return selected


def build_step_2_1a_candle(snapshot: dict[str, Any], active_level: str, level_price: float) -> dict[str, Any] | None:
    """Build the live completed candle payload consumed by the replay evaluator."""
    if not candle_close_confirmed(snapshot):
        return None
    ohlc = snapshot.get("ohlc")
    if not isinstance(ohlc, dict):
        return None
    candle = {
        "open": ohlc.get("open"),
        "high": ohlc.get("high"),
        "low": ohlc.get("low"),
        "close": ohlc.get("close"),
        "timestamp": snapshot.get("latest_bar_time"),
        "active_level": active_level,
        "level_price": level_price,
    }
    if any(candle.get(key) is None for key in ("open", "high", "low", "close", "timestamp")):
        return None
    return candle


def candle_close_confirmed(snapshot: dict[str, Any]) -> bool:
    """Return False only when the feed explicitly marks the OHLC as a live forming bar."""
    return snapshot.get("ohlc_is_closed") is not False


def local_market_time(value: Any) -> datetime | None:
    """Parse a timestamp and return it in the local market timezone."""
    parsed = parse_candle_time(value)
    return parsed.astimezone(LOCAL_MARKET_TIMEZONE) if parsed else None


def local_session_date(value: Any) -> str | None:
    """Return the local trading date for a candle/timestamp."""
    local_time = local_market_time(value)
    return local_time.date().isoformat() if local_time else None


def at_or_after_local_time(value: Any, hour: int, minute: int) -> bool:
    local_time = local_market_time(value)
    if not local_time:
        return False
    boundary = local_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return local_time >= boundary


def before_entry_authorization(snapshot: dict[str, Any]) -> bool:
    """Return True during the 6:15-6:30 observation-only window."""
    return at_or_after_local_time(snapshot.get("latest_bar_time"), OBSERVATION_RESET_HOUR, OBSERVATION_RESET_MINUTE) and not at_or_after_local_time(
        snapshot.get("latest_bar_time"),
        ENTRY_AUTHORIZATION_HOUR,
        ENTRY_AUTHORIZATION_MINUTE,
    )


def valid_locked_tv_context(tv_context: dict[str, Any] | None) -> bool:
    """Return True when the TradingView level map is usable for the session reset."""
    if not isinstance(tv_context, dict) or not isinstance(tv_context.get("levels"), dict):
        return False
    explicit_locked = (
        tv_context.get("locked")
        if tv_context.get("locked") is not None
        else tv_context.get("context_locked")
        if tv_context.get("context_locked") is not None
        else tv_context.get("locked_for_day")
    )
    if explicit_locked is not True:
        return False
    return bool(tv_context["levels"])


def apply_observation_cycle_reset(
    persisted_state: dict[str, Any],
    symbol: str,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Clear stale per-symbol setup state once per symbol/session after the 6:15 TV lock."""
    session_date = local_session_date(snapshot.get("latest_bar_time"))
    if (
        not symbol
        or not session_date
        or not at_or_after_local_time(snapshot.get("latest_bar_time"), OBSERVATION_RESET_HOUR, OBSERVATION_RESET_MINUTE)
        or not valid_locked_tv_context(snapshot.get("tv_context"))
    ):
        return persisted_state

    symbol_key = root_symbol(symbol)
    symbol_state = symbol_scoped_persisted_state(persisted_state, symbol_key)
    if symbol_state.get("observation_reset_session_date") == session_date:
        return persisted_state

    reset_symbol_state = {
        "symbol": symbol_state.get("symbol"),
        "normalized_symbol": symbol_key,
        "requested_symbol": symbol_state.get("requested_symbol") or symbol,
        "latest_price": snapshot.get("latest_price"),
        "latest_bar_time": snapshot.get("latest_bar_time"),
        "tv_context": snapshot.get("tv_context"),
        "tv_context_status": snapshot.get("tv_context_status"),
        "observation_reset_session_date": session_date,
        "observation_reset_bar_time": snapshot.get("latest_bar_time"),
        "observation_reset_at": datetime.now(timezone.utc).isoformat(),
    }
    state = dict(persisted_state)
    state_by_symbol = dict(state.get("state_by_symbol") or {})
    state_by_symbol[symbol_key] = reset_symbol_state
    state["state_by_symbol"] = state_by_symbol
    last_by_symbol = dict(state.get("last_interacted_liquidity_by_symbol") or {})
    last_by_symbol.pop(symbol_key, None)
    state["last_interacted_liquidity_by_symbol"] = last_by_symbol
    if root_symbol(str(state.get("normalized_symbol") or "")) == symbol_key:
        state.update(reset_symbol_state)
        state["last_interacted_liquidity"] = None
    snapshot["observation_reset_applied"] = True
    snapshot["observation_reset_session_date"] = session_date
    snapshot["observation_reset_bar_time"] = snapshot.get("latest_bar_time")
    snapshot["observation_reset_at"] = reset_symbol_state["observation_reset_at"]
    return state


def initial_or_persisted_step_2_1a_state(
    persisted_state: dict[str, Any],
    active_level: str,
    level_price: float,
    side: str,
    tick_size: float,
) -> dict[str, Any]:
    """Load persisted Step 2.1A state or create the replay engine state model."""
    step_state = persisted_state.get("step_2_1a")
    if isinstance(step_state, dict) and isinstance(step_state.get("pre_activation_probe_boundary"), dict):
        try:
            persisted_level_price = float(step_state.get("level_price"))
        except (TypeError, ValueError):
            persisted_level_price = None
        if (
            step_state.get("active_level") != active_level
            or persisted_level_price != level_price
            or step_state.get("side") != side
        ):
            return step_2_1a_initial_state(active_level, level_price, side, tick_size)
        step_state.setdefault("events", [])
        step_state.setdefault("step_2_activated", False)
        step_state.setdefault("blocked", False)
        step_state.setdefault("candle_a", None)
        step_state.setdefault("active_level", active_level)
        step_state.setdefault("level_price", level_price)
        step_state.setdefault("side", side)
        step_state.setdefault("tick_size", tick_size)
        step_state.setdefault("expiration_candles", 5)
        return step_state
    return step_2_1a_initial_state(active_level, level_price, side, tick_size)


def symbol_scoped_persisted_state(persisted_state: dict[str, Any], symbol: str | None) -> dict[str, Any]:
    """Return persisted Entry Agent state scoped to one normalized root."""
    symbol_key = root_symbol(symbol) if symbol else None
    by_symbol = persisted_state.get("state_by_symbol")
    if symbol_key and isinstance(by_symbol, dict) and isinstance(by_symbol.get(symbol_key), dict):
        return by_symbol[symbol_key]

    if symbol_key and str(persisted_state.get("normalized_symbol") or "").upper() == symbol_key:
        return persisted_state
    return {}


SESSION_SCOPED_STEP_KEYS = ("step_2_1a", "step2_locked_owner", "step25", "step3", "step4", "step5", "step6", "rejection", "gateway")
SESSION_SCOPED_TIME_KEYS = {
    "latest_bar_time",
    "step_2_1a_last_evaluated_bar_time",
    "leg1_completed_at",
    "leg1_confirmed_at",
    "leg1_reference_candle_time",
    "leg1_window_started_at",
    "leg1_window_expires_at",
    "leg2_completed_at",
    "leg2_confirmed_at",
    "leg2_candidate_candle_time",
    "entry_status_confirmed_at",
    "entry_confirmed_at",
    "invalidated_at",
    "invalidation_source_candle_time",
    "last_evaluated_candle_time",
    "current_active_sequence_started_at",
}
SESSION_HISTORY_COLLECTION_KEYS = {
    "consumed_liquidity_levels",
    "consumed_entry_setups",
    "events",
    "event_log",
    "publication_gate_debug",
}


def _collect_session_dates(value: Any, dates: set[str]) -> None:
    """Collect PT session dates from persisted state timestamps."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in SESSION_HISTORY_COLLECTION_KEYS:
                continue
            if key in SESSION_SCOPED_TIME_KEYS:
                session_date = local_session_date(item)
                if session_date:
                    dates.add(session_date)
            elif key in {"timestamp", "time"}:
                session_date = local_session_date(item)
                if session_date:
                    dates.add(session_date)
            _collect_session_dates(item, dates)
    elif isinstance(value, list):
        for item in value:
            _collect_session_dates(item, dates)


def persisted_step_state_session_stale(symbol_state: dict[str, Any], session_date: str | None) -> bool:
    """Return True when persisted leg/step timestamps belong to another PT session."""
    if not session_date:
        return False
    dates: set[str] = set()
    for key in SESSION_SCOPED_STEP_KEYS:
        if key in symbol_state:
            _collect_session_dates(symbol_state.get(key), dates)
    for key in SESSION_SCOPED_TIME_KEYS:
        if key in symbol_state:
            found = local_session_date(symbol_state.get(key))
            if found:
                dates.add(found)
    return any(date != session_date for date in dates)


def sanitize_stale_session_state(
    persisted_state: dict[str, Any],
    symbol: str | None,
    session_date: str | None,
) -> dict[str, Any]:
    """Ignore prior-session Entry Agent step state before display or calculation."""
    symbol_key = root_symbol(symbol) if symbol else None
    symbol_state = symbol_scoped_persisted_state(persisted_state, symbol_key)
    if not symbol_key or not symbol_state or not persisted_step_state_session_stale(symbol_state, session_date):
        return persisted_state

    stale_dates: set[str] = set()
    for key in SESSION_SCOPED_STEP_KEYS:
        if key in symbol_state:
            _collect_session_dates(symbol_state.get(key), stale_dates)
    for key in SESSION_SCOPED_TIME_KEYS:
        if key in symbol_state:
            found = local_session_date(symbol_state.get(key))
            if found:
                stale_dates.add(found)
    log_step2_owner_diagnostic(
        "session_state_sanitized_before_step2",
        {
            "symbol": symbol_key,
            "target_session_date": session_date,
            "collected_session_dates": sorted(stale_dates),
            "removed_step_keys": [key for key in SESSION_SCOPED_STEP_KEYS if key in symbol_state],
            "prior_owner": compact_owner(symbol_state.get("step2_locked_owner")),
            "prior_nested_owner": compact_owner((symbol_state.get("step_2_1a") or {}).get("step2_locked_owner") if isinstance(symbol_state.get("step_2_1a"), dict) else None),
            "prior_step4_window": {
                "started_at": (((symbol_state.get("step4") or {}).get("state") or {}).get("leg1_window_started_at") if isinstance((symbol_state.get("step4") or {}).get("state"), dict) else None),
                "candle_index": (((symbol_state.get("step4") or {}).get("state") or {}).get("leg1_window_candle_index") if isinstance((symbol_state.get("step4") or {}).get("state"), dict) else None),
                "remaining": (((symbol_state.get("step4") or {}).get("state") or {}).get("leg1_window_remaining") if isinstance((symbol_state.get("step4") or {}).get("state"), dict) else None),
            },
        },
    )

    cleaned_symbol_state = dict(symbol_state)
    for key in SESSION_SCOPED_STEP_KEYS:
        cleaned_symbol_state.pop(key, None)
    cleaned_symbol_state.pop("last_interacted_liquidity", None)
    cleaned_symbol_state.pop("step_2_1a_candle_index", None)
    cleaned_symbol_state.pop("step_2_1a_last_evaluated_bar_time", None)

    cleaned = dict(persisted_state)
    by_symbol = dict(cleaned.get("state_by_symbol") or {})
    by_symbol[symbol_key] = cleaned_symbol_state
    cleaned["state_by_symbol"] = by_symbol
    last_by_symbol = dict(cleaned.get("last_interacted_liquidity_by_symbol") or {})
    last_by_symbol.pop(symbol_key, None)
    cleaned["last_interacted_liquidity_by_symbol"] = last_by_symbol

    if root_symbol(str(cleaned.get("normalized_symbol") or "")) == symbol_key:
        for key in SESSION_SCOPED_STEP_KEYS:
            cleaned.pop(key, None)
        cleaned.pop("last_interacted_liquidity", None)
        cleaned.pop("step_2_1a_candle_index", None)
        cleaned.pop("step_2_1a_last_evaluated_bar_time", None)
    return cleaned


def context_price_for_level(tv_context: dict[str, Any] | None, level_name: str | None) -> float | None:
    """Return the current TradingView table price for one level name."""
    if not isinstance(tv_context, dict) or not level_name:
        return None
    levels = tv_context.get("levels")
    if not isinstance(levels, dict):
        return None
    details = levels.get(level_name)
    if not isinstance(details, dict):
        return None
    try:
        return float(details.get("price"))
    except (TypeError, ValueError):
        return None


def persisted_liquidity_matches_context(
    liquidity: dict[str, Any] | None,
    tv_context: dict[str, Any] | None,
    symbol: str | None = None,
) -> bool:
    """Return True only when persisted liquidity belongs to the current root table."""
    if not valid_active_liquidity_name(liquidity.get("name") if isinstance(liquidity, dict) else None):
        return False
    if not isinstance(liquidity, dict) or liquidity.get("price") is None:
        return False
    if not isinstance(tv_context, dict):
        return False
    context_symbol = tv_context.get("normalized_symbol") or tv_context.get("symbol")
    if symbol and context_symbol and root_symbol(str(context_symbol)) != root_symbol(symbol):
        return False
    levels = tv_context.get("levels")
    if not isinstance(levels, dict):
        return False
    details = levels.get(str(liquidity.get("name")))
    if not isinstance(details, dict) or str(details.get("status") or "").upper() != "ACTIVE":
        return False
    context_price = context_price_for_level(tv_context, str(liquidity.get("name")))
    if context_price is None:
        return False
    try:
        persisted_price = float(liquidity.get("price"))
    except (TypeError, ValueError):
        return False
    return persisted_price == context_price


def valid_active_liquidity_name(name: Any) -> bool:
    """Return True only for a real active-liquidity level name."""
    if name is None:
        return False
    text = str(name).strip()
    return bool(text and text.lower() not in {"n/a", "na", "none", "null"})


def valid_active_liquidity_selection(name: Any, price: Any) -> bool:
    """Return True when active liquidity has a real level name and numeric price."""
    if not valid_active_liquidity_name(name):
        return False
    try:
        float(price)
    except (TypeError, ValueError):
        return False
    return True


def no_active_liquidity_result(step: str, reason: str = "No active liquidity selected.") -> dict[str, Any]:
    """Return a cleared WAIT result for downstream internal evaluators while no liquidity is active."""
    return {
        "step": step,
        "status": "WAIT",
        "state": {},
        "next_step": "Step 2",
        "reason": reason,
        "events": [{"event": "no_active_liquidity_selected", "reason": reason}],
    }


def unconfirmed_current_candle_result(step: str, next_step: str, reason: str) -> dict[str, Any]:
    """Return a cleared WAIT result for status fields sourced from the live candle."""
    return {
        "step": step,
        "status": "WAIT",
        "state": {},
        "next_step": next_step,
        "reason": reason,
        "events": [{"event": "current_candle_unconfirmed", "reason": reason}],
    }


def unconfirmed_step4_invalidation_result(step4: dict[str, Any], reason: str) -> dict[str, Any]:
    """Return Step 4 WAIT while preserving public Leg 1 window countdown fields."""
    state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    allowed_keys = {
        "leg1_window_active",
        "leg1_window_started_at",
        "leg1_window_candle_index",
        "leg1_window_remaining",
        "leg1_window_expires_at",
        "participation_timer",
        "participation_candidate_count",
        "participation_candle_number",
    }
    masked_state = {key: state.get(key) for key in allowed_keys if key in state}
    masked_state["leg1_status"] = "WAIT"
    masked_state["leg1_state_locked"] = False
    masked_state["state_transition_reason"] = reason
    return {
        "step": "Step 4",
        "status": "WAIT",
        "state": masked_state,
        "next_step": "Step 4",
        "reason": reason,
        "events": list(step4.get("events") or []) + [{"event": "current_candle_step4_invalidation_masked", "reason": reason}],
    }


def clear_downstream_state_without_active_liquidity(snapshot: dict[str, Any]) -> None:
    """Clear stale downstream state when no close-confirmed liquidity activation is public."""
    reason = "No active liquidity selected."
    snapshot["suppress_active_liquidity"] = True
    snapshot["step_2_1a"] = {
        **dict(snapshot.get("step_2_1a") or {}),
        "available": False,
        "reason": reason,
        "active_level": None,
        "level_price": None,
        "active_liquidity_group": None,
        "last_interacted_liquidity": None,
        "state_transition_reason": reason,
    }
    snapshot["step25"] = no_active_liquidity_result("Step 2.5", reason)
    snapshot["step3"] = no_active_liquidity_result("Step 3", reason)
    snapshot["step4"] = no_active_liquidity_result("Step 4", reason)
    snapshot["step5"] = no_active_liquidity_result("Step 5", reason)
    snapshot["step6"] = no_active_liquidity_result("Step 6", reason)


def nested_value(data: Any, path: tuple[str, ...]) -> Any:
    """Return a nested dict value without treating missing keys as meaningful."""
    current = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def state_touches_candle_time(state: dict[str, Any], latest_time: Any, paths: tuple[tuple[str, ...], ...]) -> bool:
    """Return True when a published state field is tied to the provided candle time."""
    return any(same_candle_time(nested_value(state, path), latest_time) for path in paths)


def step4_leg1_invalidation_attempt(step4: dict[str, Any]) -> bool:
    """Return True for Step 4/Leg 1 invalidations that must wait for a closed candle."""
    if not isinstance(step4, dict) or decision_status(step4) != "INVALIDATE":
        return False
    state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    source = str(state.get("invalidation_source") or state.get("invalidation_source_step") or state.get("terminated_by") or "")
    reason = result_reason(step4, "")
    reason_lower = reason.lower()
    return (
        source in {"Step 4", "step4", "leg1_50_percent_rule"}
        or "candle b failed" in reason_lower
        or "step 4" in reason_lower
        or "leg 1 invalid" in reason_lower
        or "leg1" in reason_lower
        or "active liquidity was penetrated beyond 50%" in reason_lower
    )


def mask_unconfirmed_step4_leg1_invalidation(snapshot: dict[str, Any], reason: str) -> bool:
    """Mask live-candle Step 4/Leg 1 invalidation publication; return True when masked."""
    latest_time = snapshot.get("latest_bar_time")
    if candle_close_confirmed(snapshot) or not latest_time:
        return False
    step4 = snapshot.get("step4") if isinstance(snapshot.get("step4"), dict) else {}
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    step4_unconfirmed = state_touches_candle_time(
        step4_state,
        latest_time,
        (
            ("invalidation_source_candle_time",),
            ("invalidated_at",),
            ("leg1_completed_at",),
            ("leg1_reference_candle_time",),
            ("last_evaluated_candle_time",),
            ("candle_b", "timestamp"),
            ("latest_candle", "timestamp"),
        ),
    )
    if not step4_unconfirmed or not step4_leg1_invalidation_attempt(step4):
        return False
    snapshot["step4"] = unconfirmed_step4_invalidation_result(step4, reason)
    snapshot["step5"] = unconfirmed_current_candle_result("Step 5", "Step 4", reason)
    snapshot["step6"] = unconfirmed_current_candle_result("Step 6", "Step 4", reason)
    return True


def hide_unconfirmed_current_candle_advancement(snapshot: dict[str, Any]) -> None:
    """Hide non-Step-6 state advancement tied to the live forming candle from operator status."""
    if candle_close_confirmed(snapshot):
        return
    latest_time = snapshot.get("latest_bar_time")
    if not latest_time:
        return

    reason = "Monitoring current 1-minute candle until close confirmation."
    if mask_unconfirmed_step4_leg1_invalidation(snapshot, reason):
        return
    step4 = snapshot.get("step4") if isinstance(snapshot.get("step4"), dict) else {}
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    step4_unconfirmed = state_touches_candle_time(
        step4_state,
        latest_time,
        (
            ("leg1_completed_at",),
            ("leg1_reference_candle_time",),
            ("last_evaluated_candle_time",),
            ("candle_b", "timestamp"),
            ("latest_candle", "timestamp"),
        ),
    )
    if step4_unconfirmed and (
        step4.get("status") == "READY"
        or step4_state.get("leg1_status") == "COMPLETE"
        or step4_state.get("setup_direction") in {"LONG", "SHORT"}
        or step4_state.get("leg1_direction") in {"LONG", "SHORT"}
    ):
        snapshot["step4"] = unconfirmed_current_candle_result("Step 4", "Step 4", reason)
        snapshot["step5"] = unconfirmed_current_candle_result("Step 5", "Step 4", reason)
        snapshot["step6"] = unconfirmed_current_candle_result("Step 6", "Step 4", reason)
        return

    step5 = snapshot.get("step5") if isinstance(snapshot.get("step5"), dict) else {}
    step5_state = step5.get("state") if isinstance(step5.get("state"), dict) else {}
    step5_unconfirmed = state_touches_candle_time(
        step5_state,
        latest_time,
        (
            ("leg2_candidate_candle_time",),
            ("leg2_completed_at",),
            ("last_evaluated_candle_time",),
            ("leg2_candle", "timestamp"),
            ("latest_candle", "timestamp"),
        ),
    )
    if step5_unconfirmed and (
        step5.get("status") == "READY"
        or step5_state.get("leg2_status") == "COMPLETE"
        or step5_state.get("setup_direction") in {"LONG", "SHORT"}
    ):
        snapshot["step5"] = unconfirmed_current_candle_result("Step 5", "Step 5", reason)
        snapshot["step6"] = unconfirmed_current_candle_result("Step 6", "Step 5", reason)
        return

def persisted_active_liquidity(
    persisted_state: dict[str, Any],
    symbol: str | None = None,
    tv_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return the last interacted liquidity persisted from a prior status pass."""
    symbol_key = root_symbol(symbol) if symbol else None
    by_symbol = persisted_state.get("last_interacted_liquidity_by_symbol")
    if symbol_key and isinstance(by_symbol, dict):
        liquidity = by_symbol.get(symbol_key)
        if persisted_liquidity_matches_context(liquidity, tv_context, symbol_key):
            return liquidity
    scoped_state = symbol_scoped_persisted_state(persisted_state, symbol_key)
    liquidity = scoped_state.get("last_interacted_liquidity")
    if persisted_liquidity_matches_context(liquidity, tv_context, symbol_key):
        return liquidity
    return None


def persisted_liquidity_candidate(persisted_state: dict[str, Any], symbol: str | None = None) -> dict[str, Any] | None:
    """Return persisted liquidity without requiring it to still be active in TV context."""
    symbol_key = root_symbol(symbol) if symbol else None
    by_symbol = persisted_state.get("last_interacted_liquidity_by_symbol")
    if symbol_key and isinstance(by_symbol, dict) and isinstance(by_symbol.get(symbol_key), dict):
        return by_symbol[symbol_key]
    scoped_state = symbol_scoped_persisted_state(persisted_state, symbol_key)
    liquidity = scoped_state.get("last_interacted_liquidity")
    return liquidity if isinstance(liquidity, dict) else None


def pending_leg1_window_liquidity(persisted_state: dict[str, Any], current_candle: dict[str, Any] | None) -> dict[str, Any] | None:
    """Keep Step 2 liquidity available while Step 4 is waiting for Candle B."""
    if not isinstance(current_candle, dict):
        return None
    step4 = persisted_state.get("step4") if isinstance(persisted_state.get("step4"), dict) else {}
    state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    if state.get("leg1_window_active") is not True:
        return None
    if state.get("leg1_status") == "COMPLETE" or state.get("leg1_state_locked") is True:
        return None
    if state.get("leg1_window_invalidated") is True:
        return None
    started_at = state.get("leg1_window_started_at")
    if started_at and not candle_is_after(current_candle, started_at):
        return None
    active = state.get("active_liquidity")
    if not isinstance(active, dict) or not active.get("name") or active.get("price") is None:
        return None
    return active


def step2_owner_invalidation_seen(persisted_state: dict[str, Any]) -> bool:
    """Return True when a persisted Step 2 owner has an explicit downstream reset."""
    step4 = persisted_state.get("step4") if isinstance(persisted_state.get("step4"), dict) else {}
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    if step4_state.get("leg1_window_invalidated") is True:
        return True
    if step4_state.get("invalidation_source") or step4_state.get("invalidated_at"):
        return True

    step5 = persisted_state.get("step5") if isinstance(persisted_state.get("step5"), dict) else {}
    step5_state = step5.get("state") if isinstance(step5.get("state"), dict) else {}
    if step5_state.get("invalidated_at"):
        return True
    if step5_state.get("invalidation_source") or step5_state.get("invalidated_liquidity"):
        return True
    return False


def locked_step2_owner(persisted_state: dict[str, Any]) -> dict[str, Any] | None:
    """Return the rejection owner locked by Step 2 confirmation, if still in lifecycle."""
    if step2_owner_invalidation_seen(persisted_state):
        return None
    owner = persisted_state.get("step2_locked_owner")
    if not isinstance(owner, dict):
        step2_state = persisted_state.get("step_2_1a") if isinstance(persisted_state.get("step_2_1a"), dict) else {}
        owner = step2_state.get("step2_locked_owner")
    if not isinstance(owner, dict) or owner.get("pathway") != "rejection":
        return None
    active = owner.get("active_liquidity")
    if isinstance(active, dict) and valid_active_liquidity_selection(active.get("name"), active.get("price")):
        return owner
    if valid_active_liquidity_selection(owner.get("active_liquidity_name"), owner.get("active_liquidity_price")):
        return owner
    return None


def locked_step2_active_liquidity(persisted_state: dict[str, Any]) -> dict[str, Any] | None:
    """Return the active-liquidity object owned by a locked Step 2 rejection setup."""
    owner = locked_step2_owner(persisted_state)
    if not isinstance(owner, dict):
        return None
    active = owner.get("active_liquidity")
    if isinstance(active, dict):
        return active
    return {
        "name": owner.get("active_liquidity_name"),
        "price": owner.get("active_liquidity_price"),
        "display_name": owner.get("active_liquidity_display_name"),
        "side": "lower" if owner.get("setup_direction") == "LONG" else "upper" if owner.get("setup_direction") == "SHORT" else None,
        "group": owner.get("active_liquidity_group"),
    }


def build_step2_locked_owner(step_state: dict[str, Any], selected_liquidity: dict[str, Any] | None) -> dict[str, Any] | None:
    """Build the durable Step 2 rejection owner consumed by downstream steps."""
    if step_state.get("step_2_activated") is not True:
        return None
    if not isinstance(selected_liquidity, dict):
        return None
    active_name = selected_liquidity.get("name") or step_state.get("active_level")
    active_price = selected_liquidity.get("price") if selected_liquidity.get("price") is not None else step_state.get("level_price")
    if not valid_active_liquidity_selection(active_name, active_price):
        return None
    side = selected_liquidity.get("side") or step_state.get("side") or side_for_level(str(active_name))
    setup_direction = "LONG" if side == "lower" else "SHORT" if side == "upper" else None
    group = selected_liquidity.get("group") if isinstance(selected_liquidity.get("group"), dict) else step_state.get("active_liquidity_group")
    active = {
        "name": active_name,
        "price": active_price,
        "display_name": selected_liquidity.get("display_name") or (group or {}).get("display_name") if isinstance(group, dict) else selected_liquidity.get("display_name"),
        "side": side,
        "group": group,
    }
    return {
        "pathway": "rejection",
        "active_liquidity": active,
        "active_liquidity_name": active_name,
        "active_liquidity_price": active_price,
        "active_liquidity_display_name": active.get("display_name"),
        "active_liquidity_group": group,
        "liquidity_group": (group or {}).get("name") if isinstance(group, dict) else None,
        "stack_components": (group or {}).get("components") if isinstance(group, dict) else None,
        "close_boundary": (group or {}).get("close_boundary") if isinstance(group, dict) else None,
        "extreme_boundary": (group or {}).get("extreme_boundary") if isinstance(group, dict) else None,
        "setup_direction": setup_direction,
        "side": side,
        "candle_a": step_state.get("candle_a"),
        "activated_at": candle_timestamp(step_state.get("candle_a") if isinstance(step_state.get("candle_a"), dict) else None) or step_state.get("last_evaluated_bar_time"),
        "continuation_controlling_structure_high": step_state.get("continuation_controlling_structure_high"),
        "continuation_controlling_structure_low": step_state.get("continuation_controlling_structure_low"),
        "continuation_controlling_structure_start_time": step_state.get("continuation_controlling_structure_start_time"),
        "continuation_controlling_structure_end_time": step_state.get("continuation_controlling_structure_end_time"),
        "continuation_controlling_structure_source_step": step_state.get("continuation_controlling_structure_source_step"),
    }


def pending_normal_rejection_step2_owner(
    persisted_state: dict[str, Any],
    selected_liquidity: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Recover Step 2 ownership from a pending same-liquidity Normal Rejection window."""
    if not isinstance(selected_liquidity, dict):
        return None
    previous_step25 = persisted_state.get("step25") if isinstance(persisted_state.get("step25"), dict) else {}
    step25_state = previous_step25.get("state") if isinstance(previous_step25.get("state"), dict) else {}
    previous_step4 = persisted_state.get("step4") if isinstance(persisted_state.get("step4"), dict) else {}
    step4_state = previous_step4.get("state") if isinstance(previous_step4.get("state"), dict) else {}
    if step25_state.get("step25_pathway_selection_complete") is not True:
        return None
    if normalized_pathway_name(step25_state.get("controlling_mode")) != "Normal":
        return None
    if step4_state.get("leg1_state_locked") is True or step4_state.get("leg1_status") == "COMPLETE":
        return None
    if step4_state.get("leg1_window_invalidated") is True or step4_state.get("leg1_window_remaining") == 0:
        return None
    if not step4_state.get("leg1_window_started_at"):
        return None

    previous_liquidity = step4_state.get("active_liquidity") if isinstance(step4_state.get("active_liquidity"), dict) else None
    if not isinstance(previous_liquidity, dict):
        previous_liquidity = step25_state.get("active_liquidity") if isinstance(step25_state.get("active_liquidity"), dict) else None
    if not same_active_liquidity(previous_liquidity, selected_liquidity):
        return None

    candle_a = step25_state.get("initial_candle_a") if isinstance(step25_state.get("initial_candle_a"), dict) else None
    if candle_a is None:
        candle_a = step4_state.get("initial_candle_a") if isinstance(step4_state.get("initial_candle_a"), dict) else None
    activated_at = candle_timestamp(candle_a) or step4_state.get("leg1_window_started_at")
    if not activated_at:
        return None

    side = selected_liquidity.get("side") or previous_liquidity.get("side") or side_for_level(str(selected_liquidity.get("name") or ""))
    group = selected_liquidity.get("group") if isinstance(selected_liquidity.get("group"), dict) else previous_liquidity.get("group")
    display_name = selected_liquidity.get("display_name") or previous_liquidity.get("display_name")
    if not display_name and isinstance(group, dict):
        display_name = group.get("display_name")
    active = {
        "name": selected_liquidity.get("name"),
        "price": selected_liquidity.get("price"),
        "display_name": display_name,
        "side": side,
        "group": group,
    }
    return {
        "pathway": "rejection",
        "active_liquidity": active,
        "active_liquidity_name": active.get("name"),
        "active_liquidity_price": active.get("price"),
        "active_liquidity_display_name": active.get("display_name"),
        "active_liquidity_group": group,
        "liquidity_group": (group or {}).get("name") if isinstance(group, dict) else None,
        "stack_components": (group or {}).get("components") if isinstance(group, dict) else None,
        "close_boundary": (group or {}).get("close_boundary") if isinstance(group, dict) else None,
        "extreme_boundary": (group or {}).get("extreme_boundary") if isinstance(group, dict) else None,
        "setup_direction": "SHORT" if side == "upper" else "LONG" if side == "lower" else step4_state.get("setup_direction"),
        "side": side,
        "candle_a": candle_a,
        "activated_at": activated_at,
    }


def latest_terminated_interaction_snapshot(persisted_state: dict[str, Any]) -> dict[str, Any] | None:
    """Return the latest Step 7 terminated interaction snapshot persisted for a symbol."""
    for step_name in ("step6", "step5", "step4", "step3"):
        step = persisted_state.get(step_name) if isinstance(persisted_state.get(step_name), dict) else {}
        state = step.get("state") if isinstance(step.get("state"), dict) else {}
        snapshot = state.get("terminated_interaction_snapshot")
        if isinstance(snapshot, dict):
            return snapshot
    return None


def same_liquidity_reactivation_blocked(
    selected_liquidity: dict[str, Any] | None,
    persisted_state: dict[str, Any],
    current_candle: dict[str, Any] | None,
) -> bool:
    """Implement Step 8 same-liquidity reactivation proof without reusing structure."""
    if not isinstance(selected_liquidity, dict) or not isinstance(current_candle, dict):
        return False
    terminated = latest_terminated_interaction_snapshot(persisted_state)
    if not isinstance(terminated, dict):
        return False

    selected_name = selected_liquidity.get("name")
    selected_price = optional_float(selected_liquidity.get("price"))
    terminated_name = terminated.get("terminated_liquidity_name")
    terminated_price = optional_float(terminated.get("terminated_liquidity_price"))
    if selected_name != terminated_name or selected_price is None or terminated_price != selected_price:
        return False

    close = optional_float(current_candle.get("close"))
    highest_close = optional_float(terminated.get("prior_interaction_highest_close"))
    lowest_close = optional_float(terminated.get("prior_interaction_lowest_close"))
    direction = str(terminated.get("terminated_interaction_direction") or "").upper()
    if close is None:
        return True
    if direction == "LONG" and highest_close is not None:
        return close <= highest_close
    if direction == "SHORT" and lowest_close is not None:
        return close >= lowest_close
    return highest_close is not None or lowest_close is not None


def same_liquidity_reactivation_allowed(
    selected_liquidity: dict[str, Any] | None,
    persisted_state: dict[str, Any],
    current_candle: dict[str, Any] | None,
) -> bool:
    """Return True only when Step 8 same-liquidity reactivation proof exists."""
    if not isinstance(selected_liquidity, dict) or not isinstance(current_candle, dict):
        return False
    terminated = latest_terminated_interaction_snapshot(persisted_state)
    if not isinstance(terminated, dict):
        return False

    selected_name = selected_liquidity.get("name")
    selected_price = optional_float(selected_liquidity.get("price"))
    terminated_name = terminated.get("terminated_liquidity_name")
    terminated_price = optional_float(terminated.get("terminated_liquidity_price"))
    if selected_name != terminated_name or selected_price is None or terminated_price != selected_price:
        return False

    close = optional_float(current_candle.get("close"))
    highest_close = optional_float(terminated.get("prior_interaction_highest_close"))
    lowest_close = optional_float(terminated.get("prior_interaction_lowest_close"))
    direction = str(terminated.get("terminated_interaction_direction") or "").upper()
    if close is None:
        return False
    if direction == "LONG" and highest_close is not None:
        return close > highest_close
    if direction == "SHORT" and lowest_close is not None:
        return close < lowest_close
    return False


def liquidity_stack_group(tv_context: dict[str, Any] | None, level_name: Any) -> str | None:
    if not isinstance(tv_context, dict) or not level_name:
        return None
    levels = tv_context.get("levels")
    if not isinstance(levels, dict):
        return None
    details = levels.get(str(level_name))
    if not isinstance(details, dict):
        return None
    stack_group = str(details.get("stack_group") or "NONE").strip()
    return stack_group if stack_group and stack_group.upper() != "NONE" else None


def same_stack_owner(
    tv_context: dict[str, Any] | None,
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> bool:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    left_group = liquidity_stack_group(tv_context, left.get("name"))
    right_group = liquidity_stack_group(tv_context, right.get("name"))
    return bool(left_group and left_group == right_group)


def current_candle_supports_persisted_liquidity(
    persisted_liquidity: dict[str, Any] | None,
    tv_context: dict[str, Any] | None,
    latest_price: Any,
    current_candle: dict[str, Any] | None,
    tick_size: float,
) -> bool:
    """Require current closed-candle ownership proof before reusing persisted liquidity."""
    if not isinstance(persisted_liquidity, dict) or not isinstance(current_candle, dict):
        return False
    selected = selected_active_liquidity_from_context(tv_context, latest_price, current_candle, tick_size)
    if not isinstance(selected, dict):
        return False
    return same_active_liquidity(selected, persisted_liquidity) or same_stack_owner(tv_context, selected, persisted_liquidity)


def normalized_signature_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    return str(value)


def entry_setup_signature(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Build a stable signature for one completed active-liquidity Leg 1/Leg 2 setup."""
    step4 = snapshot.get("step4") if isinstance(snapshot.get("step4"), dict) else {}
    step5 = snapshot.get("step5") if isinstance(snapshot.get("step5"), dict) else {}
    step6 = snapshot.get("step6") if isinstance(snapshot.get("step6"), dict) else {}
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    step5_state = step5.get("state") if isinstance(step5.get("state"), dict) else {}
    step6_state = step6.get("state") if isinstance(step6.get("state"), dict) else {}
    active_name, active_price = active_liquidity_from_snapshot(snapshot)
    setup_direction = step6_state.get("setup_direction") or step5_state.get("setup_direction") or step4_state.get("setup_direction")
    leg1_time = step4_state.get("leg1_completed_at") or step4_state.get("leg1_reference_candle_time")
    leg2_time = (
        step5_state.get("leg2_candidate_candle_time")
        or candle_timestamp(step5_state.get("leg2_candle") if isinstance(step5_state.get("leg2_candle"), dict) else None)
        or candle_timestamp(step6_state.get("entry_candle") if isinstance(step6_state.get("entry_candle"), dict) else None)
    )
    if not active_name or active_price is None or not setup_direction or not leg1_time or not leg2_time:
        return None

    fields = {
        "active_liquidity_name": str(active_name),
        "active_liquidity_price": normalized_signature_value(active_price),
        "setup_direction": str(setup_direction),
        "leg1_completed_at": str(leg1_time),
        "leg1_reference_price": normalized_signature_value(step4_state.get("leg1_reference_price") or step4_state.get("leg1_reference")),
        "leg2_completed_at": str(leg2_time),
        "leg2_reference_price": normalized_signature_value(step5_state.get("leg2_reference_price") or step5_state.get("leg2_reference")),
    }
    key = "|".join(f"{name}={fields[name]}" for name in sorted(fields))
    return {**fields, "key": key}


def consumed_entry_setups(persisted_state: dict[str, Any]) -> list[dict[str, Any]]:
    consumed = persisted_state.get("consumed_entry_setups")
    return consumed if isinstance(consumed, list) else []


def setup_signature_consumed(persisted_state: dict[str, Any], signature: dict[str, Any] | None) -> bool:
    if not signature:
        return False
    key = signature.get("key")
    return any(isinstance(record, dict) and record.get("key") == key for record in consumed_entry_setups(persisted_state))


def submitted_trade_times_for_symbol(symbol: str) -> list[str]:
    """Return submitted/filled trade timestamps from persistence and executor evidence."""
    symbol_key = root_symbol(symbol)
    times: list[str] = []
    persistence = _read_json(PERSISTENCE_STATE_PATH)
    for trade in (persistence.get("trades") or {}).values():
        if not isinstance(trade, dict):
            continue
        trade_symbol = root_symbol(str(trade.get("symbol") or trade.get("execution_symbol") or ""))
        if trade_symbol != symbol_key:
            continue
        if str(trade.get("status") or "").lower() in {"rejected", "cancelled"}:
            continue
        timestamp = trade.get("created_at") or trade.get("filled_at") or trade.get("submitted_at")
        if timestamp:
            times.append(str(timestamp))

    executor = _read_json(EXECUTOR_STATE_PATH)
    for order in (executor.get("orders") or {}).values():
        if not isinstance(order, dict) or order.get("type") != "entry":
            continue
        if root_symbol(str(order.get("symbol") or order.get("resolved_symbol") or "")) != symbol_key:
            continue
        if str(order.get("status") or "").lower() in {"rejected", "cancelled"}:
            continue
        timestamp = order.get("filled_at") or order.get("created_at") or order.get("submitted_at")
        if timestamp:
            times.append(str(timestamp))
    return times


def submitted_trade_exists_after_setup(symbol: str, signature: dict[str, Any]) -> bool:
    setup_time = parse_candle_time(signature.get("leg2_completed_at") or signature.get("leg1_completed_at"))
    if setup_time is None:
        return False
    for value in submitted_trade_times_for_symbol(symbol):
        trade_time = parse_candle_time(value)
        if trade_time and trade_time >= setup_time:
            return True
    return False


def record_consumed_entry_setup(symbol: str, signature: dict[str, Any], reason: str) -> None:
    """Persist consumed setup context without changing execution state."""
    state = load_entry_state()
    symbol_key = root_symbol(symbol)
    state_by_symbol = state.get("state_by_symbol")
    if not isinstance(state_by_symbol, dict):
        state_by_symbol = {}
    symbol_state = symbol_scoped_persisted_state(state, symbol_key)
    symbol_state = dict(symbol_state)
    consumed = list(consumed_entry_setups(symbol_state))
    if not any(isinstance(record, dict) and record.get("key") == signature.get("key") for record in consumed):
        consumed.append({**signature, "consumed_reason": reason, "consumed_at": datetime.now(timezone.utc).isoformat()})
    symbol_state["consumed_entry_setups"] = consumed
    state_by_symbol[symbol_key] = symbol_state
    state["state_by_symbol"] = state_by_symbol
    if root_symbol(str(state.get("normalized_symbol") or "")) == symbol_key or not state.get("normalized_symbol"):
        state["consumed_entry_setups"] = consumed
    _write_json(STATE_PATH, state)


def apply_consumed_entry_setup_guard(snapshot: dict[str, Any]) -> None:
    """Suppress duplicate CONFIRM publication for a setup that already submitted."""
    step6 = snapshot.get("step6") if isinstance(snapshot.get("step6"), dict) else {}
    if decision_status(step6) != "CONFIRM":
        return
    signature = entry_setup_signature(snapshot)
    if not signature:
        return
    symbol_key = str(snapshot.get("normalized_symbol") or root_symbol(str(snapshot.get("requested_symbol") or snapshot.get("symbol") or ""))).upper()
    persisted_state = load_entry_state()
    symbol_state = symbol_scoped_persisted_state(persisted_state, symbol_key)
    consumed = setup_signature_consumed(symbol_state, signature)
    submitted = submitted_trade_exists_after_setup(symbol_key, signature)
    if submitted and not consumed:
        record_consumed_entry_setup(symbol_key, signature, "Submitted trade consumed this Entry Agent setup context.")
        consumed = True
    if not consumed:
        return
    reason = "Setup context already consumed by a submitted trade."
    snapshot["step6"] = {
        "step": "Step 6",
        "status": "WAIT",
        "state": {
            **(step6.get("state") if isinstance(step6.get("state"), dict) else {}),
            "entry_triggered": False,
            "consumed_entry_setup_key": signature.get("key"),
            "entry_setup_consumed": True,
        },
        "next_step": "Step 6",
        "reason": reason,
        "events": list(step6.get("events") or []) + [{"event": "entry_setup_already_consumed", "reason": reason}],
    }


def build_last_interacted_liquidity(selected_liquidity: dict[str, Any] | None) -> dict[str, Any] | None:
    """Build the persisted active-liquidity record for a newly interacted level."""
    if not selected_liquidity:
        return None
    if not selected_liquidity.get("name") or selected_liquidity.get("price") is None:
        return None
    return {
        "name": selected_liquidity.get("name"),
        "price": selected_liquidity.get("price"),
        "display_name": selected_liquidity.get("display_name") or (selected_liquidity.get("group") or {}).get("display_name"),
        "side": selected_liquidity.get("side"),
        "group": selected_liquidity.get("group"),
        "interacted_at": datetime.now(timezone.utc).isoformat(),
    }


def stack_group_with_dynamic_extreme(
    group: dict[str, Any] | None,
    candle: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return stack group with wick-only sweep extreme migrated when close reclaims the stack."""
    if not isinstance(group, dict) or not isinstance(candle, dict):
        return group
    side = group.get("side")
    extreme_boundary = optional_float(group.get("extreme_boundary"))
    close = optional_float(candle.get("close"))
    high = optional_float(candle.get("high"))
    low = optional_float(candle.get("low"))
    if side not in {"upper", "lower"} or extreme_boundary is None or close is None:
        return group

    updated_extreme = None
    if side == "lower" and low is not None and low < extreme_boundary and close > extreme_boundary:
        updated_extreme = low
    elif side == "upper" and high is not None and high > extreme_boundary and close < extreme_boundary:
        updated_extreme = high
    if updated_extreme is None:
        return group

    updated = dict(group)
    updated["extreme_boundary"] = updated_extreme
    if side == "lower":
        updated["low"] = updated_extreme
    else:
        updated["high"] = updated_extreme
    return updated


def evaluate_live_step_2_1a(
    snapshot: dict[str, Any],
    _levels: dict[str, Any],
    liquidity: dict[str, Any],
    persisted_state: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate live Step 2.1A by calling the replay evaluator directly."""
    symbol_key = str(snapshot.get("normalized_symbol") or snapshot.get("symbol") or "")
    symbol_state = symbol_scoped_persisted_state(persisted_state, symbol_key)
    persisted_candle_index = int(symbol_state.get("step_2_1a_candle_index") or 0)
    selected_liquidity = None
    current_candle = build_current_candle(snapshot)
    previous_liquidity = persisted_liquidity_candidate(persisted_state, symbol_key)
    step2_locked_liquidity = locked_step2_active_liquidity(symbol_state)
    locked_liquidity = locked_leg1_active_liquidity(symbol_state)
    tick_size = float(liquidity.get("tick_size") or 0.25)
    if isinstance(locked_liquidity, dict):
        selected_liquidity = locked_liquidity
        previous_liquidity = locked_liquidity
    elif isinstance(step2_locked_liquidity, dict):
        selected_liquidity = step2_locked_liquidity
        previous_liquidity = step2_locked_liquidity
    elif candle_close_confirmed(snapshot):
        selected_liquidity = selected_active_liquidity_from_context(
            snapshot.get("tv_context"),
            snapshot.get("latest_price"),
            snapshot.get("ohlc") if isinstance(snapshot.get("ohlc"), dict) else None,
            tick_size,
        )
        if not selected_liquidity:
            selected_liquidity = rotated_active_liquidity_after_inactive_acceptance(
                snapshot.get("tv_context"),
                previous_liquidity,
                snapshot.get("ohlc") if isinstance(snapshot.get("ohlc"), dict) else None,
            )
    consumed_levels = list(consumed_liquidity_levels(symbol_state))
    threshold_record, threshold_target = threshold_liquidity_exhaustion(
        symbol_state,
        previous_liquidity,
        snapshot.get("tv_context"),
        current_candle,
    )
    lifecycle_locked = isinstance(locked_liquidity, dict) or isinstance(step2_locked_liquidity, dict)
    if threshold_record and not lifecycle_locked:
        consumed_levels = merge_consumed_liquidity_levels(consumed_levels, [threshold_record])
        if threshold_target and (
            not isinstance(selected_liquidity, dict)
            or same_active_liquidity(selected_liquidity, previous_liquidity)
            or consumed_liquidity_blocks(
                {**symbol_state, "consumed_liquidity_levels": consumed_levels},
                selected_liquidity.get("name"),
                selected_liquidity.get("price"),
                current_candle,
            )
        ):
            selected_liquidity = threshold_target
    symbol_state_with_consumed = {**symbol_state, "consumed_liquidity_levels": consumed_levels}
    if selected_liquidity and not lifecycle_locked and consumed_liquidity_blocks(
        symbol_state_with_consumed,
        selected_liquidity.get("name"),
        selected_liquidity.get("price"),
        current_candle,
    ):
        selected_liquidity = None
    if not lifecycle_locked and same_liquidity_reactivation_blocked(selected_liquidity, symbol_state, current_candle):
        selected_liquidity = None
    if not lifecycle_locked:
        consumed_levels = merge_consumed_liquidity_levels(
            consumed_levels,
            record_exhausted_liquidity(
                symbol_state_with_consumed,
                previous_liquidity,
                selected_liquidity,
                current_candle,
            ),
        )
    active_level = selected_liquidity.get("name") if selected_liquidity else None
    level_price = selected_liquidity.get("price") if selected_liquidity else None
    if not selected_liquidity:
        pending_liquidity = pending_leg1_window_liquidity(symbol_state, current_candle)
        if pending_liquidity and persisted_liquidity_matches_context(pending_liquidity, snapshot.get("tv_context"), symbol_key):
            active_level = pending_liquidity.get("name")
            level_price = pending_liquidity.get("price")
            selected_liquidity = pending_liquidity
    if not selected_liquidity:
        persisted_liquidity = persisted_active_liquidity(persisted_state, symbol_key, snapshot.get("tv_context"))
        if persisted_liquidity and not (
            current_candle_supports_persisted_liquidity(
                persisted_liquidity,
                snapshot.get("tv_context"),
                snapshot.get("latest_price"),
                current_candle,
                tick_size,
            )
            or same_liquidity_reactivation_allowed(persisted_liquidity, symbol_state, current_candle)
        ):
            persisted_liquidity = None
        if persisted_liquidity and consumed_liquidity_blocks(
            {**symbol_state, "consumed_liquidity_levels": consumed_levels},
            persisted_liquidity.get("name"),
            persisted_liquidity.get("price"),
            current_candle,
        ):
            persisted_liquidity = None
        if persisted_liquidity:
            active_level = persisted_liquidity.get("name")
            level_price = persisted_liquidity.get("price")
            selected_liquidity = persisted_liquidity
    side = side_for_level(active_level)
    if not active_level or level_price is None or side is None:
        return {
            "available": False,
            "reason": "No active Step 2 liquidity level available.",
            "events": [],
            "next_candle_index": persisted_candle_index,
            "active_level": None,
            "level_price": None,
            "active_liquidity_group": None,
            "last_interacted_liquidity": None,
        }

    locked_owner_before = locked_step2_owner(symbol_state)
    pending_owner_before = None if isinstance(locked_owner_before, dict) else pending_normal_rejection_step2_owner(symbol_state, selected_liquidity)
    recovered_locked_owner = locked_owner_before or pending_owner_before
    owner_lookup_debug = step2_owner_lookup_diagnostics(symbol_state, selected_liquidity)
    log_step2_owner_diagnostic(
        "step2_owner_lookup",
        {
            "symbol": symbol_key,
            "candle_time": candle_timestamp(current_candle),
            "latest_price": snapshot.get("latest_price"),
            "selected_liquidity": compact_liquidity(selected_liquidity),
            "locked_owner_found": isinstance(locked_owner_before, dict),
            "pending_owner_found": isinstance(pending_owner_before, dict),
            "recovered_owner_found": isinstance(recovered_locked_owner, dict),
            "recovered_owner": compact_owner(recovered_locked_owner),
            "lookup": owner_lookup_debug,
        },
    )
    step_state = initial_or_persisted_step_2_1a_state(
        symbol_state,
        str(active_level),
        level_price,
        side,
        tick_size,
    )
    pre_confirmation_target = next_same_side_liquidity_target(snapshot.get("tv_context"), selected_liquidity)
    if pre_confirmation_target:
        step_state["next_same_side_liquidity"] = pre_confirmation_target
        step_state["pre_confirmation_50_percent_target_price"] = pre_confirmation_target.get("price")
    candle = build_step_2_1a_candle(snapshot, str(active_level), level_price)
    if candle is None:
        step_state["available"] = False
        step_state["reason"] = "No completed OHLC candle available for Step 2.1A."
        step_state["next_candle_index"] = persisted_candle_index
        return step_state

    if isinstance(recovered_locked_owner, dict):
        owner_candle = recovered_locked_owner.get("candle_a") if isinstance(recovered_locked_owner.get("candle_a"), dict) else None
        step_state["step_2_activated"] = True
        step_state["blocked"] = False
        step_state["candle_a"] = owner_candle or step_state.get("candle_a")
        step_state["step2_locked_owner"] = recovered_locked_owner
        step_state["active_liquidity_group"] = recovered_locked_owner.get("active_liquidity_group")
        step_state["last_interacted_liquidity"] = build_last_interacted_liquidity(
            recovered_locked_owner.get("active_liquidity") if isinstance(recovered_locked_owner.get("active_liquidity"), dict) else selected_liquidity
        )
        step_state["available"] = True
        step_state["reason"] = "Step 2 already locked for this liquidity/pathway; preserving original activation owner."
        step_state["last_evaluated_bar_time"] = candle["timestamp"]
        step_state["candle_index"] = persisted_candle_index
        step_state["next_candle_index"] = persisted_candle_index + 1
        step_state["consumed_liquidity_levels"] = consumed_levels
        log_step2_owner_diagnostic(
            "step2_owner_reused",
            {
                "symbol": symbol_key,
                "candle_time": candle.get("timestamp"),
                "selected_liquidity": compact_liquidity(selected_liquidity),
                "reused_owner": compact_owner(recovered_locked_owner),
                "step_state_candle_a": compact_candle(step_state.get("candle_a")),
                "reason": step_state.get("reason"),
            },
        )
        return step_state

    last_evaluated_bar_time = symbol_state.get("step_2_1a_last_evaluated_bar_time")
    if last_evaluated_bar_time == candle["timestamp"]:
        step_state["available"] = True
        step_state["reason"] = "Step 2.1A already evaluated this completed candle."
        step_state["next_candle_index"] = persisted_candle_index
        return step_state

    candle_index = persisted_candle_index
    evaluate_step_2_1a_candle(step_state, candle, candle_index)
    step_state["available"] = True
    step_state["reason"] = "Step 2.1A evaluated from live completed candle."
    step_state["last_evaluated_bar_time"] = candle["timestamp"]
    step_state["candle_index"] = candle_index
    step_state["next_candle_index"] = candle_index + 1
    selected_group = selected_liquidity.get("group") if selected_liquidity else None
    selected_group = stack_group_with_dynamic_extreme(selected_group, candle)
    if selected_liquidity and isinstance(selected_group, dict):
        selected_liquidity = {**selected_liquidity, "group": selected_group}
    step_state["active_liquidity_group"] = selected_group
    if step_state.get("step_2_activated") is True:
        structure_bars = unique_bars_by_time(
            recent_closed_bars(symbol_key, 120),
            candle,
        )
        apply_step2_continuation_structure_fields(
            step_state,
            step2_continuation_controlling_structure(side, structure_bars, candle_timestamp(candle)),
        )
    step_state["last_interacted_liquidity"] = (
        build_last_interacted_liquidity(selected_liquidity)
        or persisted_active_liquidity(persisted_state, symbol_key, snapshot.get("tv_context"))
    )
    new_owner_candidate = build_step2_locked_owner(step_state, selected_liquidity)
    if isinstance(new_owner_candidate, dict):
        log_step2_owner_diagnostic(
            "step2_owner_created",
            {
                "symbol": symbol_key,
                "candle_time": candle.get("timestamp"),
                "selected_liquidity": compact_liquidity(selected_liquidity),
                "new_owner": compact_owner(new_owner_candidate),
                "step_state_candle_a": compact_candle(step_state.get("candle_a")),
                "step_state_reason": step_state.get("reason"),
                "step_state_events": step_state.get("events"),
                "lookup_before_creation": owner_lookup_debug,
            },
        )
    locked_owner = recovered_locked_owner or new_owner_candidate
    if locked_owner:
        step_state["step2_locked_owner"] = locked_owner
    step_state["consumed_liquidity_levels"] = consumed_levels
    return step_state


def build_current_candle(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Build a completed candle payload for downstream decision engines."""
    if not candle_close_confirmed(snapshot):
        return None
    return build_snapshot_candle(snapshot)


def build_snapshot_candle(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Build a candle payload from the current snapshot, whether closed or live."""
    ohlc = snapshot.get("ohlc")
    if not isinstance(ohlc, dict):
        return None
    candle = {
        "open": ohlc.get("open"),
        "high": ohlc.get("high"),
        "low": ohlc.get("low"),
        "close": ohlc.get("close"),
        "timestamp": snapshot.get("latest_bar_time"),
    }
    if any(candle.get(key) is None for key in ("open", "high", "low", "close", "timestamp")):
        return None
    return candle


def candle_timestamp(candle: dict[str, Any] | None) -> str | None:
    """Return a comparable candle timestamp string."""
    if not isinstance(candle, dict):
        return None
    value = candle.get("timestamp")
    return str(value) if value else None


def parse_candle_time(value: Any) -> datetime | None:
    """Parse candle timestamps and normalize to UTC for ordering."""
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_MARKET_TIMEZONE)
    return parsed.astimezone(timezone.utc)


def candle_is_after(candle: dict[str, Any] | None, timestamp: Any) -> bool:
    """Return True when candle timestamp is strictly after timestamp."""
    candle_time = parse_candle_time(candle_timestamp(candle))
    reference_time = parse_candle_time(timestamp)
    if not candle_time or not reference_time:
        return False
    return candle_time > reference_time


def same_candle_time(left: Any, right: Any) -> bool:
    """Return True when two candle timestamps represent the same instant."""
    left_time = parse_candle_time(left)
    right_time = parse_candle_time(right)
    return bool(left_time and right_time and left_time == right_time)


def leg2_candidate_same_sequence(state: dict[str, Any], candidate_candle: dict[str, Any] | None) -> bool:
    """Return True when a Leg 2 candidate belongs to the locked Leg 1 formation sequence."""
    candidate_time = candle_timestamp(candidate_candle)
    if not candidate_time:
        return True
    sequence_times = (
        candle_timestamp(state.get("candle_a") if isinstance(state.get("candle_a"), dict) else None),
        candle_timestamp(state.get("candle_b") if isinstance(state.get("candle_b"), dict) else None),
        state.get("leg1_reference_candle_time"),
        state.get("leg1_completed_at"),
    )
    return any(sequence_time and same_candle_time(candidate_time, sequence_time) for sequence_time in sequence_times)


def waiting_for_future_leg2_result(
    step4: dict[str, Any],
    candidate_candle: dict[str, Any] | None,
    reason: str = "Step 5 waiting for a separate future Leg 2 candle after locked Leg 1.",
) -> dict[str, Any]:
    """Return Step 5 WAIT when the candidate is not a separate future candle."""
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    state = dict(step4_state)
    state["leg2_status"] = "WAIT"
    state["leg2_candidate_candle_time"] = candle_timestamp(candidate_candle)
    state["leg2_same_sequence_rejected"] = True
    state["leg2_wait_reason"] = reason
    state["leg2_formed_at_percent"] = None
    state["leg2_25_percent_rule_passed"] = None
    state["last_evaluated_candle_time"] = candle_timestamp(candidate_candle) or state.get("last_evaluated_candle_time")
    state["state_transition_reason"] = reason
    return {
        "step": "Step 5",
        "status": "WAIT",
        "state": state,
        "next_step": "Step 5",
        "reason": reason,
        "events": [{"event": "step5_same_sequence_leg2_rejected", "reason": reason}],
    }



def active_liquidity_identity(liquidity: Any) -> tuple[Any, float | None]:
    """Return stable active-liquidity identity for state matching."""
    if not isinstance(liquidity, dict):
        return None, None
    try:
        price = float(liquidity.get("price"))
    except (TypeError, ValueError):
        price = None
    return liquidity.get("name"), price


def same_active_liquidity(left: Any, right: Any) -> bool:
    """Return True when two active-liquidity records identify the same level."""
    left_name, left_price = active_liquidity_identity(left)
    right_name, right_price = active_liquidity_identity(right)
    return bool(left_name and left_name == right_name and left_price is not None and left_price == right_price)


def locked_leg1_active_liquidity(persisted_state: dict[str, Any]) -> dict[str, Any] | None:
    """Return the active liquidity owned by a valid locked Leg 1 state."""
    step4 = persisted_state.get("step4") if isinstance(persisted_state.get("step4"), dict) else {}
    state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    locked_ok, _reason = valid_participation_locked_leg1_state(state)
    if not locked_ok:
        return None
    active = state.get("active_liquidity")
    return active if isinstance(active, dict) else None


def pathway_control_from_price(active_liquidity: dict[str, Any] | None, price: Any) -> dict[str, Any]:
    """Return live pathway control without changing confirmed structure state."""
    if not isinstance(active_liquidity, dict):
        return {"current_pathway_control": "inactive", "current_controlling_mode": None, "current_continuation_type": "none"}
    level_name = active_liquidity.get("name")
    level_price = optional_float(active_liquidity.get("price"))
    latest_price = optional_float(price)
    side = active_liquidity.get("side") or side_for_level(str(level_name or ""))
    if level_price is None or latest_price is None or side not in {"upper", "lower"}:
        return {"current_pathway_control": "inactive", "current_controlling_mode": None, "current_continuation_type": "none"}
    if side == "upper":
        rejection_controls = latest_price >= level_price
        continuation_type = "R/S"
    else:
        rejection_controls = latest_price <= level_price
        continuation_type = "S/R"
    if rejection_controls:
        return {
            "current_pathway_control": "rejection",
            "current_controlling_mode": "Normal Rejection Mode",
            "current_continuation_type": continuation_type,
        }
    return {
        "current_pathway_control": "continuation",
        "current_controlling_mode": continuation_type,
        "current_continuation_type": continuation_type,
    }


def valid_locked_leg1_state(
    state: dict[str, Any],
    current_active_liquidity: dict[str, Any] | None = None,
    current_sequence_started_at: Any = None,
) -> tuple[bool, str | None]:
    """Validate the locked Leg 1 contract required before Step 5 can evaluate."""
    if state.get("leg1_state_locked") is not True:
        return False, "Waiting for valid locked Leg 1 reference"
    if state.get("leg1_status") != "COMPLETE":
        return False, "Waiting for valid locked Leg 1 reference"
    if state.get("leg1_reference_price") is None and state.get("leg1_reference") is None:
        return False, "Waiting for valid locked Leg 1 reference"
    if not state.get("leg1_reference_candle_time"):
        return False, "Waiting for valid locked Leg 1 reference"
    if state.get("leg1_direction") not in ("LONG", "SHORT") and state.get("setup_direction") not in ("LONG", "SHORT"):
        return False, "Waiting for valid locked Leg 1 reference"
    if not isinstance(state.get("active_liquidity"), dict):
        return False, "Waiting for valid locked Leg 1 reference"
    if not state.get("leg1_completed_at"):
        return False, "Waiting for valid locked Leg 1 reference"
    sequence_started_at = current_sequence_started_at or state.get("current_active_sequence_started_at")
    if (
        sequence_started_at
        and not candle_is_after({"timestamp": state.get("leg1_completed_at")}, sequence_started_at)
        and not same_candle_time(state.get("leg1_completed_at"), sequence_started_at)
    ):
        return False, "Waiting for valid locked Leg 1 reference"
    if current_active_liquidity is not None and not same_active_liquidity(state.get("active_liquidity"), current_active_liquidity):
        return False, "Waiting for valid locked Leg 1 reference"
    return True, None


def valid_participation_locked_leg1_state(
    state: dict[str, Any],
    current_active_liquidity: dict[str, Any] | None = None,
    current_sequence_started_at: Any = None,
) -> tuple[bool, str | None]:
    """Validate locked Leg 1 and require a distinct participation Candle B."""
    locked_ok, reason = valid_locked_leg1_state(state, current_active_liquidity, current_sequence_started_at)
    if not locked_ok:
        return False, reason
    candle_b = state.get("candle_b") if isinstance(state.get("candle_b"), dict) else None
    candle_b_time = candle_timestamp(candle_b)
    if not candle_b_time:
        return False, "Waiting for valid participation Candle B"
    if not same_candle_time(candle_b_time, state.get("leg1_completed_at")):
        return False, "Waiting for valid participation Candle B"
    candle_a = state.get("candle_a") if isinstance(state.get("candle_a"), dict) else None
    if same_candle_time(candle_timestamp(candle_a), candle_b_time):
        return False, "Waiting for participation candle after setup Candle A"
    return True, None


def waiting_for_locked_leg1_result(
    step4: dict[str, Any] | None,
    reason: str = "Waiting for valid locked Leg 1 reference",
) -> dict[str, Any]:
    """Return a stable Step 5 WAIT state with Leg 2 percentage fields cleared."""
    step4_state = step4.get("state") if isinstance(step4, dict) and isinstance(step4.get("state"), dict) else {}
    state = dict(step4_state)
    state["leg2_status"] = "WAIT"
    state["leg2_candidate_candle_time"] = None
    state["leg2_same_sequence_rejected"] = None
    state["leg2_wait_reason"] = reason
    state["leg2_formed_at_percent"] = None
    state["leg2_25_percent_rule_passed"] = None
    state["state_transition_reason"] = reason
    return {
        "step": "Step 5",
        "status": "WAIT",
        "state": state,
        "next_step": "Step 4",
        "reason": reason,
        "events": [{"event": "step5_waiting_for_locked_leg1", "reason": reason}],
    }


def liquidity_key(name: Any, price: Any) -> str | None:
    """Build a stable key for consumed liquidity guards."""
    if not name or price is None:
        return None
    try:
        normalized_price = float(price)
    except (TypeError, ValueError):
        return None
    return f"{name}:{normalized_price}"


def consumed_liquidity_levels(persisted_state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return consumed liquidity guard records from persisted symbol state."""
    consumed = persisted_state.get("consumed_liquidity_levels")
    return consumed if isinstance(consumed, list) else []


def merge_consumed_liquidity_levels(*sources: Any) -> list[dict[str, Any]]:
    """Merge consumed liquidity records without dropping records from later steps."""
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        if not isinstance(source, list):
            continue
        for record in source:
            if not isinstance(record, dict):
                continue
            key = record.get("key") or liquidity_key(record.get("name"), record.get("price"))
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(record)
    return merged


def consumed_liquidity_blocks(
    persisted_state: dict[str, Any],
    name: Any,
    price: Any,
    current_candle: dict[str, Any] | None,
) -> bool:
    """Block reactivation from the same candle sequence after invalidation."""
    key = liquidity_key(name, price)
    current_time = candle_timestamp(current_candle)
    if not key or not current_time:
        return False
    for record in consumed_liquidity_levels(persisted_state):
        if not isinstance(record, dict):
            continue
        record_key = record.get("key") or liquidity_key(record.get("name"), record.get("price"))
        if record_key == key and record.get("exhaustion_type") in {
            "next_liquidity_reached",
            "same_side_next_liquidity_reached",
            "no_leg1_50_percent_exhaustion",
            "leg1_no_leg2_25_percent_exhaustion",
        }:
            return True
        source_time = record.get("invalidation_source_candle_time")
        if record_key == key and source_time and current_time <= str(source_time):
            return True
    return False


def reached_next_same_side_liquidity(previous: dict[str, Any], selected: dict[str, Any]) -> bool:
    """Return True when selection moves from a spent level to the next same-side target."""
    previous_name = previous.get("name")
    selected_name = selected.get("name")
    previous_side = previous.get("side") or side_for_level(str(previous_name or ""))
    selected_side = selected.get("side") or side_for_level(str(selected_name or ""))
    previous_price = optional_float(previous.get("price"))
    selected_price = optional_float(selected.get("price"))
    if (
        not previous_name
        or not selected_name
        or previous_name == selected_name
        or previous_side not in {"lower", "upper"}
        or selected_side != previous_side
        or previous_price is None
        or selected_price is None
    ):
        return False
    if previous_side == "lower":
        return selected_price < previous_price
    return selected_price > previous_price


def next_same_side_liquidity_target(
    tv_context: dict[str, Any] | None,
    previous: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return the next active same-side target beyond the previous liquidity."""
    if not isinstance(tv_context, dict) or not isinstance(tv_context.get("levels"), dict):
        return None
    if not isinstance(previous, dict):
        return None
    previous_name = str(previous.get("name") or "").strip()
    previous_side = previous.get("side") or side_for_level(previous_name)
    previous_price = optional_float(previous.get("price"))
    if previous_side not in {"lower", "upper"} or previous_price is None:
        return None

    previous_details = tv_context["levels"].get(previous_name)
    previous_stack_group = None
    if isinstance(previous_details, dict):
        stack_text = str(previous_details.get("stack_group") or "NONE").strip()
        if stack_text and stack_text.upper() != "NONE":
            previous_stack_group = stack_text

    candidates: list[dict[str, Any]] = []
    for name, details in tv_context["levels"].items():
        if name not in ACTIVE_LIQUIDITY_PRIORITY or not isinstance(details, dict):
            continue
        if str(details.get("status") or "").upper() != "ACTIVE":
            continue
        if side_for_level(name) != previous_side:
            continue
        price = optional_float(details.get("price"))
        if price is None:
            continue
        if previous_side == "lower" and price >= previous_price:
            continue
        if previous_side == "upper" and price <= previous_price:
            continue
        stack_text = str(details.get("stack_group") or "NONE").strip()
        if previous_stack_group and stack_text == previous_stack_group:
            continue
        candidates.append(
            {
                "name": name,
                "price": price,
                "side": previous_side,
                "priority": ACTIVE_LIQUIDITY_PRIORITY[name],
                "distance": abs(price - previous_price),
            }
        )
    if not candidates:
        return None
    selected = min(candidates, key=lambda item: (item["priority"], item["distance"], item["name"]))
    return {
        "name": selected["name"],
        "price": selected["price"],
        "side": selected["side"],
        "group": active_stack_from_context(tv_context, str(selected["name"])),
    }


def has_valid_leg1_without_valid_leg2(persisted_state: dict[str, Any]) -> bool:
    """Return True once Leg 1 is locked but Step 5 has not validated Leg 2."""
    step4 = persisted_state.get("step4") if isinstance(persisted_state.get("step4"), dict) else {}
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    locked_ok, _reason = valid_participation_locked_leg1_state(step4_state)
    if not locked_ok:
        return False
    step5 = persisted_state.get("step5") if isinstance(persisted_state.get("step5"), dict) else {}
    step5_state = step5.get("state") if isinstance(step5.get("state"), dict) else {}
    if step5.get("status") == "READY" or step5.get("next_step") == "Step 6":
        return False
    if step5_state.get("leg2_status") in {"VALIDATED", "COMPLETE"} or step5_state.get("step5_participation_validated") is True:
        return False
    return True


def has_no_valid_leg1(persisted_state: dict[str, Any]) -> bool:
    """Return True while the active liquidity has not produced a valid locked Leg 1."""
    step4 = persisted_state.get("step4") if isinstance(persisted_state.get("step4"), dict) else {}
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    locked_ok, _reason = valid_participation_locked_leg1_state(step4_state)
    return not locked_ok


def liquidity_progression_fraction(
    previous: dict[str, Any],
    target: dict[str, Any],
    candle: dict[str, Any] | None,
    *,
    use_reach: bool,
) -> float | None:
    """Return progress from previous liquidity toward the next same-side target."""
    previous_side = previous.get("side") or side_for_level(str(previous.get("name") or ""))
    previous_price = optional_float(previous.get("price"))
    target_price = optional_float(target.get("price"))
    if not isinstance(candle, dict) or previous_side not in {"lower", "upper"}:
        return None
    if previous_price is None or target_price is None or previous_price == target_price:
        return None
    if previous_side == "lower":
        progress_price = optional_float(candle.get("low") if use_reach else candle.get("close"))
        distance = previous_price - target_price
        progressed = previous_price - progress_price if progress_price is not None else None
    else:
        progress_price = optional_float(candle.get("high") if use_reach else candle.get("close"))
        distance = target_price - previous_price
        progressed = progress_price - previous_price if progress_price is not None else None
    if progress_price is None or progressed is None or distance <= 0:
        return None
    return progressed / distance


def threshold_liquidity_exhaustion(
    persisted_state: dict[str, Any],
    previous: dict[str, Any] | None,
    tv_context: dict[str, Any] | None,
    current_candle: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return a spent-liquidity record and rotation target when a threshold rule fires."""
    if not isinstance(previous, dict):
        return None, None
    key = liquidity_key(previous.get("name"), previous.get("price"))
    if not key or any(
        isinstance(record, dict) and (record.get("key") or liquidity_key(record.get("name"), record.get("price"))) == key
        for record in consumed_liquidity_levels(persisted_state)
    ):
        return None, None
    target = next_same_side_liquidity_target(tv_context, previous)
    if not target:
        return None, None

    exhaustion_type = None
    threshold = None
    progress = None
    reason = None
    if has_no_valid_leg1(persisted_state):
        progress = liquidity_progression_fraction(previous, target, current_candle, use_reach=False)
        threshold = 0.50
        if progress is not None and progress >= threshold:
            exhaustion_type = "no_leg1_50_percent_exhaustion"
            reason = "No valid Leg 1 formed and close progressed beyond 50% of the distance to the next same-side liquidity target."
    elif has_valid_leg1_without_valid_leg2(persisted_state):
        progress = liquidity_progression_fraction(previous, target, current_candle, use_reach=True)
        threshold = 0.75
        if progress is not None and progress >= threshold:
            exhaustion_type = "leg1_no_leg2_25_percent_exhaustion"
            reason = "Valid Leg 1 formed without valid Leg 2 and price reached 25% or less remaining distance to the next same-side liquidity target."

    if not exhaustion_type:
        return None, None
    return (
        {
            "key": key,
            "name": previous.get("name"),
            "price": previous.get("price"),
            "side": previous.get("side") or side_for_level(str(previous.get("name") or "")),
            "exhaustion_type": exhaustion_type,
            "exhausted_by": target.get("name"),
            "exhausted_by_price": target.get("price"),
            "exhausted_at_candle_time": candle_timestamp(current_candle),
            "progress_fraction": progress,
            "threshold_fraction": threshold,
            "reason": reason,
        },
        target,
    )


def record_exhausted_liquidity(
    persisted_state: dict[str, Any],
    previous: dict[str, Any] | None,
    selected: dict[str, Any] | None,
    current_candle: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Mark a prior same-stack liquidity level spent once the next target is reached."""
    consumed = list(consumed_liquidity_levels(persisted_state))
    if not isinstance(previous, dict) or not isinstance(selected, dict):
        return consumed
    if not reached_next_same_side_liquidity(previous, selected):
        return consumed
    key = liquidity_key(previous.get("name"), previous.get("price"))
    if not key:
        return consumed
    if any(isinstance(record, dict) and (record.get("key") or liquidity_key(record.get("name"), record.get("price"))) == key for record in consumed):
        return consumed
    consumed.append(
        {
            "key": key,
            "name": previous.get("name"),
            "price": previous.get("price"),
            "side": previous.get("side") or side_for_level(str(previous.get("name") or "")),
            "exhaustion_type": "same_side_next_liquidity_reached",
            "exhausted_by": selected.get("name"),
            "exhausted_by_price": selected.get("price"),
            "exhausted_at_candle_time": candle_timestamp(current_candle),
            "reason": "Active liquidity progressed to the next same-side target; prior level is spent for this sequence.",
        }
    )
    return consumed


def active_stack_from_context(tv_context: dict[str, Any] | None, active_level: str | None) -> dict[str, Any] | None:
    """Return active stack context when the prebuilt TV context says the active level belongs to a stack."""
    if not isinstance(tv_context, dict) or not active_level:
        return None
    levels = tv_context.get("levels")
    if isinstance(levels, dict):
        details = levels.get(active_level)
        if isinstance(details, dict) and str(details.get("status") or "").upper() == "ACTIVE":
            stack_group = str(details.get("stack_group") or "NONE").strip()
            if stack_group and stack_group.upper() != "NONE":
                components = []
                for name, component_details in levels.items():
                    if name not in ACTIVE_LIQUIDITY_PRIORITY or not isinstance(component_details, dict):
                        continue
                    if str(component_details.get("status") or "").upper() != "ACTIVE":
                        continue
                    if str(component_details.get("stack_group") or "").strip() != stack_group:
                        continue
                    try:
                        price = float(component_details.get("price"))
                    except (TypeError, ValueError):
                        continue
                    components.append(
                        {
                            "name": name,
                            "price": price,
                            "priority": ACTIVE_LIQUIDITY_PRIORITY[name],
                            "side": side_for_level(name),
                        }
                    )
                components = sorted(components, key=lambda item: (item["priority"], item["name"]))
                if components:
                    try:
                        active_price = float(details.get("price"))
                    except (TypeError, ValueError):
                        return None
                    prices = [component["price"] for component in components]
                    side = components[0].get("side") or side_for_level(active_level)
                    return {
                        "name": stack_group,
                        "components": [component["name"] for component in components],
                        "prices": {component["name"]: component["price"] for component in components},
                        "side": side,
                        "close_boundary": active_price,
                        "extreme_boundary": max(prices) if side == "upper" else min(prices),
                        "low": min(prices),
                        "high": max(prices),
                    }
    for key in ("high_side", "low_side"):
        side_context = tv_context.get(key)
        if not isinstance(side_context, dict) or side_context.get("type") != "STACK":
            continue
        components = side_context.get("components") or side_context.get("levels") or []
        if active_level in components or side_context.get("target_name") == active_level:
            return side_context
    return None


def rejection_from_step2_activation(step_2_1a: dict[str, Any], symbol: str = "NQ") -> dict[str, Any]:
    """Build Rejection ON only from the Step 2 interaction activation owner."""
    if step_2_1a.get("step_2_activated") is not True:
        return {
            "rejection_mode": "OFF",
            "reason_text": step_2_1a.get("reason") or "Step 2 has not activated a liquidity interaction.",
        }
    active_level = step_2_1a.get("active_level")
    level_price = optional_float(step_2_1a.get("level_price"))
    side = step_2_1a.get("side") or side_for_level(str(active_level or ""))
    if active_level is None or level_price is None or side not in {"upper", "lower"}:
        return {
            "rejection_mode": "OFF",
            "reason_text": "Step 2 activation missing active liquidity identity.",
        }
    watch_side = "SHORT" if side == "upper" else "LONG"
    priority = ACTIVE_LIQUIDITY_PRIORITY.get(str(active_level), 999)
    return {
        "rejection_mode": "ON",
        "watch_side": watch_side,
        "trigger_level": active_level,
        "trigger_price": level_price,
        "trigger_priority": priority,
        "reason_text": f"Step 2 activated {active_level} {level_price}; watching {watch_side} participation.",
    }


def build_step3_interaction(
    snapshot: dict[str, Any],
    rejection: dict[str, Any],
    step25: dict[str, Any],
    step_2_1a: dict[str, Any],
    persisted_state: dict[str, Any],
) -> dict[str, Any] | None:
    """Build the Step 3 interaction object from existing Step 2 state without changing Step 2 logic."""
    if rejection.get("rejection_mode") != "ON":
        return None
    if step25.get("status") != "READY":
        return None
    step25_state = step25.get("state")
    if not isinstance(step25_state, dict):
        return None

    active_level = step_2_1a.get("active_level") or rejection.get("trigger_level")
    active_price = step_2_1a.get("level_price") or rejection.get("trigger_price")
    current_candle = build_current_candle(snapshot)
    if not active_level or active_price is None or current_candle is None:
        return None

    previous_step3 = persisted_state.get("step3") if isinstance(persisted_state.get("step3"), dict) else {}
    previous_state = previous_step3.get("state") if isinstance(previous_step3.get("state"), dict) else {}
    tv_context = snapshot.get("tv_context")
    locked_owner = step_2_1a.get("step2_locked_owner") if isinstance(step_2_1a.get("step2_locked_owner"), dict) else locked_step2_owner(persisted_state)
    active_stack = (
        (locked_owner or {}).get("active_liquidity_group")
        if isinstance((locked_owner or {}).get("active_liquidity_group"), dict)
        else active_stack_from_context(tv_context, str(active_level))
    )
    probe = step_2_1a.get("pre_activation_probe_boundary")

    interaction = dict(step25_state)
    pathway_candle_a = (
        step25_state.get("reclaim_candle_a")
        if normalized_pathway_name(step25_state.get("controlling_mode")) in {"S/R", "R/S"}
        and isinstance(step25_state.get("reclaim_candle_a"), dict)
        else step_2_1a.get("candle_a") or current_candle
    )
    interaction.update({
        "system_state": "REJECTION MODE ON",
        "trade_mode": "ON",
        "rejection_mode": "ON",
        "interaction_state": "ACTIVE",
        "active_liquidity": {"name": active_level, "price": active_price},
        "active_stack": active_stack,
        "close_boundary": (active_stack or {}).get("close_boundary"),
        "extreme_boundary": (active_stack or {}).get("extreme_boundary"),
        "stack_side": (active_stack or {}).get("side") or step_2_1a.get("side"),
        "tick_size": (snapshot.get("liquidity") or {}).get("tick_size"),
        "candle_a": pathway_candle_a,
        "latest_candle": current_candle,
        "pre_activation_probe_boundary": probe,
        "stack_extreme_confirmation_seen": previous_state.get("stack_extreme_confirmation_seen"),
        "stack_extreme_confirmation_candle": previous_state.get("stack_extreme_confirmation_candle"),
        "sweep_extreme_boundary_seen": previous_state.get("sweep_extreme_boundary_seen"),
        "events": list(previous_step3.get("events") or []),
    })
    return interaction


def build_step25_interaction(
    snapshot: dict[str, Any],
    rejection: dict[str, Any],
    step_2_1a: dict[str, Any],
    persisted_state: dict[str, Any],
) -> dict[str, Any] | None:
    """Build Step 2.5 input from Step 2 activation state."""
    if rejection.get("rejection_mode") != "ON":
        return None

    current_candle = build_current_candle(snapshot)
    initial_candle_a = step_2_1a.get("candle_a")
    active_group = step_2_1a.get("active_liquidity_group")
    active_level = step_2_1a.get("active_level") or rejection.get("trigger_level")
    level_price = step_2_1a.get("level_price") or rejection.get("trigger_price")
    side = step_2_1a.get("side") or side_for_level(str(active_level or ""))
    pathway_level_type = "LH" if side == "upper" else "LL" if side == "lower" else None
    pathway_level = level_price
    pathway_stack_extreme = (active_group or {}).get("extreme_boundary") if isinstance(active_group, dict) else None
    bars = recent_closed_bars(str(snapshot.get("normalized_symbol") or snapshot.get("symbol") or "NQ"), 2)
    previous_step25 = persisted_state.get("step25") if isinstance(persisted_state.get("step25"), dict) else {}
    previous_state = previous_step25.get("state") if isinstance(previous_step25.get("state"), dict) else {}
    previous_initial = previous_state.get("initial_candle_a") if isinstance(previous_state, dict) else None
    previous_liquidity = previous_state.get("active_liquidity") if isinstance(previous_state.get("active_liquidity"), dict) else None
    previous_same_rejection_liquidity = (
        previous_state.get("step25_pathway_selection_complete") is True
        and normalized_pathway_name(previous_state.get("controlling_mode")) == "Normal"
        and normalized_pathway_name(rejection.get("controlling_mode") or previous_state.get("controlling_mode")) == "Normal"
        and valid_active_liquidity_selection((previous_liquidity or {}).get("name") or previous_state.get("active_liquidity_name"), (previous_liquidity or {}).get("price") or previous_state.get("active_liquidity_price"))
        and same_active_liquidity(
            {
                "name": (previous_liquidity or {}).get("name") or previous_state.get("active_liquidity_name"),
                "price": (previous_liquidity or {}).get("price") or previous_state.get("active_liquidity_price"),
            },
            {"name": active_level, "price": level_price},
        )
    )
    if previous_same_rejection_liquidity and isinstance(previous_initial, dict):
        initial_candle_a = previous_initial
    previous_continuation_locked = (
        previous_state.get("continuation_step2_activated") is True
        and normalized_pathway_name(previous_state.get("controlling_mode")) in {"S/R", "R/S"}
        and isinstance(previous_state.get("reclaim_candle_a"), dict)
    )
    previous_locked = previous_continuation_locked or (
        previous_state.get("step25_pathway_selection_complete") is True
        and same_candle_time((previous_initial or {}).get("timestamp") if isinstance(previous_initial, dict) else None, (initial_candle_a or {}).get("timestamp") if isinstance(initial_candle_a, dict) else None)
    )

    interaction = {
        "system_state": "REJECTION MODE ON",
        "trade_mode": "ON",
        "rejection_mode": "ON",
        "interaction_state": "ACTIVE",
        "initial_candle_a": initial_candle_a,
        "candidate_modes": previous_state.get("candidate_modes") if previous_locked else None,
        "controlling_mode": previous_state.get("controlling_mode") if previous_locked else None,
        "structure_side_requirement": previous_state.get("structure_side_requirement") if previous_locked else None,
        "reclaim_candle_a": previous_state.get("reclaim_candle_a") if previous_locked else None,
        "provisional_candle_a": None,
        "pathway_level": previous_state.get("pathway_level") if previous_locked else pathway_level,
        "pathway_activation_type": previous_state.get("pathway_activation_type") if previous_locked and previous_state.get("pathway_activation_type") != "wick" else None,
        "continuation_step2_activated": previous_state.get("continuation_step2_activated") if previous_locked else None,
        "continuation_pending_boundary": previous_state.get("continuation_pending_boundary"),
        "continuation_step2_pending": previous_state.get("continuation_step2_pending"),
        "active_liquidity_selected": active_level is not None and level_price is not None,
        "active_liquidity": {"name": active_level, "price": level_price, "side": side},
        "active_liquidity_name": active_level,
        "active_liquidity_price": level_price,
        "rejection_step2_confirmed": step_2_1a.get("step_2_activated") is True,
        "events": list(previous_step25.get("events") or []) if previous_locked else [],
    }
    if len(bars) >= 1 and pathway_level is not None and pathway_level_type:
        prev_candle = bars[-2] if len(bars) >= 2 else bars[-1]
        interaction.update(
            {
                "prev_candle": prev_candle,
                "last_candle": bars[-1],
                "level": pathway_level,
                "level_type": pathway_level_type,
                "stack_extreme": pathway_stack_extreme,
            }
        )
    return interaction


def evaluate_live_step25(
    snapshot: dict[str, Any],
    rejection: dict[str, Any],
    step_2_1a: dict[str, Any],
    persisted_state: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate Step 2.5 after Step 2 activates Rejection Mode."""
    interaction = build_step25_interaction(snapshot, rejection, step_2_1a, persisted_state)
    if interaction is None:
        reason = "Step 2.5 requires a Step 2 liquidity-close pathway activation."
        return {
            "step": "Step 2.5",
            "status": "WAIT",
            "state": {},
            "next_step": "Step 2",
            "reason": reason,
            "events": [{"event": "step25_waiting_for_step2", "reason": reason}],
        }
    return evaluate_step25(interaction)


def evaluate_live_step3(
    snapshot: dict[str, Any],
    rejection: dict[str, Any],
    step25: dict[str, Any],
    step_2_1a: dict[str, Any],
    persisted_state: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate Step 3 after existing Step 2 / 2.1A outputs are available."""
    interaction = build_step3_interaction(snapshot, rejection, step25, step_2_1a, persisted_state)
    if interaction is None:
        reason = "Step 3 requires Step 2 liquidity-close activation, Step 2.5 selection, Candle A, and active liquidity."
        return {
            "step": "Step 3",
            "status": "WAIT",
            "state": {},
            "next_step": "Step 2",
            "reason": reason,
            "events": [{"event": "step3_waiting_for_step2", "reason": reason}],
        }
    return evaluate_step3(interaction)


def nearest_opposing_liquidity(liquidity: dict[str, Any], setup_direction: str | None) -> dict[str, Any] | None:
    """Return the nearest opposing liquidity for the Step 4 proximity filter."""
    if setup_direction == "SHORT":
        return liquidity.get("nearest_level_below")
    if setup_direction == "LONG":
        return liquidity.get("nearest_level_above")
    return None


def setup_direction_from_pathway(step25_state: dict[str, Any], rejection: dict[str, Any]) -> str | None:
    """Return shared-engine direction after Step 2.5 pathway selection."""
    mode = normalized_pathway_name(step25_state.get("controlling_mode"))
    if mode == "S/R":
        return "SHORT"
    if mode == "R/S":
        return "LONG"
    return rejection.get("watch_side")


def next_break_side_liquidity(liquidity: dict[str, Any], setup_direction: str | None) -> dict[str, Any] | None:
    """Return next liquidity in the break direction for penetration measurement."""
    if setup_direction == "SHORT":
        return liquidity.get("nearest_level_above")
    if setup_direction == "LONG":
        return liquidity.get("nearest_level_below")
    return None


def atr_from_context(tv_context: dict[str, Any] | None) -> float | None:
    """Return available 1-minute ATR from context without inferring missing ATR."""
    if not isinstance(tv_context, dict):
        return None
    for key in ("atr_1m_14", "current_1m_atr", "atr_1m"):
        value = tv_context.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def daily_atr_from_context(tv_context: dict[str, Any] | None) -> float | None:
    """Return available daily ATR from TradingView context without using 1-minute ATR."""
    if not isinstance(tv_context, dict):
        return None
    for key in ("daily_atr14", "daily_atr_14", "daily_atr", "atr_daily_14", "atr_daily"):
        value = tv_context.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def load_rithmic_atr_snapshot(symbol: str) -> dict[str, Any] | None:
    """Load the listener-built 1-minute ATR for a contract/root alias."""
    payload = _read_json(RITHMIC_ATR_SNAPSHOT_PATH)
    symbols = payload.get("symbols")
    if not isinstance(symbols, dict):
        return None

    symbol_text = str(symbol).upper()
    aliases = (symbol_text, root_symbol(symbol_text))
    for alias in aliases:
        record = symbols.get(alias)
        if not isinstance(record, dict):
            continue
        value = record.get("atr_value")
        try:
            atr_value = float(value)
        except (TypeError, ValueError):
            continue
        return {
            "atr_1m_14": atr_value,
            "atr_bar_timestamp": record.get("atr_bar_timestamp"),
            "atr_source": record.get("atr_source"),
            "symbol": alias,
        }
    return None


def atr_from_snapshot(snapshot: dict[str, Any]) -> float | None:
    """Prefer Rithmic listener ATR, then fall back to TradingView context ATR."""
    atr = snapshot.get("atr")
    if isinstance(atr, dict):
        try:
            return float(atr.get("atr_1m_14"))
        except (TypeError, ValueError):
            pass
    return atr_from_context(snapshot.get("tv_context"))


def daily_atr_from_snapshot(snapshot: dict[str, Any]) -> float | None:
    """Return TradingView daily ATR for structure filters."""
    return daily_atr_from_context(snapshot.get("tv_context"))


def setup_candle_times_for_step4(step25_state: dict[str, Any], step3_state: dict[str, Any]) -> set[str]:
    """Return candle times that are setup/probe candles, not participation candidates."""
    times: set[str] = set()
    for state in (step25_state, step3_state):
        for key in (
            "initial_candle_a",
            "candle_a",
            "reclaim_candle_a",
            "provisional_candle_a",
            "stack_extreme_confirmation_candle",
        ):
            timestamp = candle_timestamp(state.get(key) if isinstance(state.get(key), dict) else None)
            if timestamp:
                times.add(timestamp)
    return times


def is_setup_candle_reused_as_participation(
    current_candle: dict[str, Any],
    step25_state: dict[str, Any],
    step3_state: dict[str, Any],
) -> bool:
    """Return True when Step 4 would evaluate the setup candle as Candle B."""
    current_time = candle_timestamp(current_candle)
    return bool(current_time and current_time in setup_candle_times_for_step4(step25_state, step3_state))


def continuation_reclaim_starts_new_sequence(step25_state: dict[str, Any], previous_state: dict[str, Any]) -> bool:
    """Return True when a continuation reclaim should supersede a completed prior sequence."""
    if normalized_pathway_name(step25_state.get("controlling_mode")) not in {"S/R", "R/S"}:
        return False
    reclaim_time = candle_timestamp(step25_state.get("reclaim_candle_a") if isinstance(step25_state.get("reclaim_candle_a"), dict) else None)
    if not reclaim_time:
        return False
    previous_leg1_time = previous_state.get("leg1_completed_at")
    if previous_leg1_time and candle_is_after({"timestamp": reclaim_time}, previous_leg1_time):
        return True
    previous_candle_a = candle_timestamp(previous_state.get("candle_a") if isinstance(previous_state.get("candle_a"), dict) else None)
    return bool(previous_candle_a and not same_candle_time(reclaim_time, previous_candle_a))


def build_step4_interaction(
    snapshot: dict[str, Any],
    rejection: dict[str, Any],
    step25: dict[str, Any],
    step3: dict[str, Any],
    persisted_state: dict[str, Any],
) -> dict[str, Any] | None:
    """Build Step 4 input only after Step 2.5 and Step 3 allow structure."""
    if step25.get("status") != "READY":
        return None
    if step3.get("status") != "ALLOW_STEP_4" or step3.get("next_step") != "Step 4":
        return None
    step25_state = step25.get("state")
    step3_state = step3.get("state")
    if not isinstance(step25_state, dict) or not isinstance(step3_state, dict):
        return None

    current_candle = build_current_candle(snapshot)
    if current_candle is None:
        return None
    continuation_mode = normalized_pathway_name(step25_state.get("controlling_mode")) in {"S/R", "R/S"}
    continuation_candle_a = step25_state.get("reclaim_candle_a") if isinstance(step25_state.get("reclaim_candle_a"), dict) else None
    step4_candle_a = continuation_candle_a if continuation_mode and continuation_candle_a is not None else (
        step25_state.get("initial_candle_a") if isinstance(step25_state.get("initial_candle_a"), dict) else None
    )
    step2_confirmation_time = candle_timestamp(step4_candle_a)
    current_is_step2_confirmation_candle = bool(step2_confirmation_time and same_candle_time(candle_timestamp(current_candle), step2_confirmation_time))
    current_is_setup_candle = (
        current_is_step2_confirmation_candle
        or is_setup_candle_reused_as_participation(current_candle, step25_state, step3_state)
    )

    previous_step4 = persisted_state.get("step4") if isinstance(persisted_state.get("step4"), dict) else {}
    previous_state = previous_step4.get("state") if isinstance(previous_step4.get("state"), dict) else {}
    if continuation_reclaim_starts_new_sequence(step25_state, previous_state):
        previous_state = {}
        previous_step4 = {}
    setup_direction = setup_direction_from_pathway(step25_state, rejection)
    active_liquidity = step3_state.get("active_liquidity") if isinstance(step3_state.get("active_liquidity"), dict) else {}
    if consumed_liquidity_blocks(
        persisted_state,
        active_liquidity.get("name"),
        active_liquidity.get("price"),
        current_candle,
    ):
        return None

    interaction = dict(step25_state)
    interaction.update(step3_state)
    if continuation_mode and continuation_candle_a is not None:
        interaction["initial_candle_a"] = continuation_candle_a
        interaction["reclaim_candle_a"] = continuation_candle_a
    interaction.update(
        {
            "setup_direction": setup_direction,
            "candle_b": None if current_is_setup_candle else current_candle,
            "latest_candle": None if current_is_setup_candle else current_candle,
            "shared_leg1_uses_initial_candle_a": continuation_mode,
            "participation_candidate_keys": previous_state.get("participation_candidate_keys") or [],
            "participation_candidate_count": previous_state.get("participation_candidate_count") or 0,
            "participation_timer": previous_state.get("participation_timer"),
            "leg1_window_active": previous_state.get("leg1_window_active"),
            "leg1_window_started_at": previous_state.get("leg1_window_started_at"),
            "leg1_window_candle_index": previous_state.get("leg1_window_candle_index"),
            "leg1_window_remaining": previous_state.get("leg1_window_remaining"),
            "leg1_window_expires_at": previous_state.get("leg1_window_expires_at"),
            "leg1_window_invalidated": previous_state.get("leg1_window_invalidated"),
            "leg1_window_invalidation_reason": previous_state.get("leg1_window_invalidation_reason"),
            "nearest_opposing_liquidity": nearest_opposing_liquidity(snapshot.get("liquidity") or {}, setup_direction),
            "step4_proximity_reference_liquidity": active_liquidity if continuation_mode else None,
            "next_break_side_liquidity": next_break_side_liquidity(snapshot.get("liquidity") or {}, setup_direction),
            "atr_1m_14": atr_from_snapshot(snapshot),
            "daily_atr14": daily_atr_from_snapshot(snapshot),
            "events": list(previous_step4.get("events") or step3.get("events") or []),
        }
    )
    initialize_leg1_window(interaction, step2_confirmation_time)
    if interaction.get("liquidity_type") == "STATIC_STACK":
        previous_candle_a = previous_state.get("candle_a") if isinstance(previous_state.get("candle_a"), dict) else None
        confirmation_candle = step3_state.get("stack_extreme_confirmation_candle") if isinstance(step3_state.get("stack_extreme_confirmation_candle"), dict) else None
        if previous_state.get("stack_step4_candle_a_assigned") is True and previous_candle_a is not None:
            interaction["candle_a"] = previous_candle_a
            interaction["initial_candle_a"] = previous_candle_a
            interaction["candle_a_source"] = previous_state.get("candle_a_source") or "step4_stack_post_extreme_candle_a"
            interaction["stack_step4_candle_a_assigned"] = True
        elif candle_is_after(current_candle, candle_timestamp(confirmation_candle)):
            interaction["candle_a"] = current_candle
            interaction["initial_candle_a"] = current_candle
            interaction["candle_a_source"] = "step4_stack_post_extreme_candle_a"
            interaction["stack_step4_candle_a_assigned"] = True
            interaction["awaiting_stack_candle_b"] = True
            interaction.pop("candle_b", None)
    return interaction


def evaluate_live_step4(
    snapshot: dict[str, Any],
    rejection: dict[str, Any],
    step25: dict[str, Any],
    step3: dict[str, Any],
    persisted_state: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate Step 4 after Step 3 is ready; do not implement Step 5."""
    previous_step4 = persisted_state.get("step4") if isinstance(persisted_state.get("step4"), dict) else {}
    previous_state = previous_step4.get("state") if isinstance(previous_step4.get("state"), dict) else {}
    step3_state = step3.get("state") if isinstance(step3.get("state"), dict) else {}
    step25_state = step25.get("state") if isinstance(step25.get("state"), dict) else {}
    initial_candle_a = step25_state.get("initial_candle_a") if isinstance(step25_state.get("initial_candle_a"), dict) else None
    current_sequence_started_at = candle_timestamp(initial_candle_a)
    current_active_liquidity = step3_state.get("active_liquidity") if isinstance(step3_state.get("active_liquidity"), dict) else None
    locked_ok, _locked_reason = valid_participation_locked_leg1_state(previous_state, current_active_liquidity, current_sequence_started_at)
    if (
        finalized_rejection_entry_state(persisted_state)
        and previous_state.get("leg1_state_locked") is True
        and previous_state.get("leg1_status") == "COMPLETE"
        and not continuation_reclaim_starts_new_sequence(step25_state, previous_state)
    ):
        return mark_finalized_rejection_state(previous_step4)
    if (
        previous_state.get("leg1_state_locked") is True
        and previous_state.get("leg1_status") == "COMPLETE"
        and not continuation_reclaim_starts_new_sequence(step25_state, previous_state)
    ):
        state = dict(previous_state)
        current_candle = build_current_candle(snapshot)
        if current_candle is not None:
            state["latest_candle"] = current_candle
        control = pathway_control_from_price(
            state.get("active_liquidity") if isinstance(state.get("active_liquidity"), dict) else None,
            (current_candle or {}).get("close") if isinstance(current_candle, dict) else snapshot.get("latest_price"),
        )
        state.update(control)
        state["last_evaluated_candle_time"] = candle_timestamp(current_candle) or state.get("last_evaluated_candle_time")
        state["state_transition_reason"] = "Leg 1 locked; Step 4 not re-evaluated on status refresh."
        state["fifty_percent_rule_phase"] = "skipped_leg1_locked"
        return {
            "step": "Step 4",
            "status": "READY",
            "state": state,
            "next_step": "Step 5",
            "reason": state["state_transition_reason"],
            "events": list(previous_step4.get("events") or []),
        }

    interaction = build_step4_interaction(snapshot, rejection, step25, step3, persisted_state)
    if interaction is None:
        if step25.get("status") == "READY" and step3.get("status") == "ALLOW_STEP_4":
            state = {}
            if isinstance(step25_state, dict):
                state.update(step25_state)
            if isinstance(step3_state, dict):
                state.update(step3_state)
            step2_confirmation_time = candle_timestamp(state.get("initial_candle_a") if isinstance(state.get("initial_candle_a"), dict) else None)
            initialize_leg1_window(state, step2_confirmation_time)
            if state.get("leg1_window_active") is True:
                reason = "Step 4 waiting: Leg 1 window started after Step 2 confirmation; Candle 1 is the next candle."
                state["state_transition_reason"] = reason
                return {
                    "step": "Step 4",
                    "status": "WAIT",
                    "state": state,
                    "next_step": "Step 4",
                    "reason": reason,
                    "events": [{"event": "step4_leg1_window_started", "reason": reason}],
                }
        reason = "Step 4 waiting for Step 2.5 selection, Step 3 permission, Candle A, Candle B, setup direction, ATR, and opposing liquidity."
        return {
            "step": "Step 4",
            "status": "WAIT",
            "state": {},
            "next_step": step3.get("next_step") or step25.get("next_step") or "Step 3",
            "reason": reason,
            "events": [{"event": "step4_waiting_for_inputs", "reason": reason}],
        }
    if interaction.get("awaiting_stack_candle_b") is True:
        state = dict(interaction)
        state["last_evaluated_candle_time"] = candle_timestamp(state.get("candle_a") if isinstance(state.get("candle_a"), dict) else None)
        reason = "Step 4 assigned stack Candle A after Extreme Boundary proof; waiting for future Candle B participation."
        state["state_transition_reason"] = reason
        return {
            "step": "Step 4",
            "status": "WAIT",
            "state": state,
            "next_step": "Step 4",
            "reason": reason,
            "events": list(interaction.get("events") or []) + [{"event": "step4_stack_candle_a_assigned", "reason": reason}],
        }
    result = evaluate_step4(interaction)
    if result.get("status") == "READY" and isinstance(result.get("state"), dict):
        state = result["state"]
        if normalized_pathway_name(state.get("controlling_mode")) in {"S/R", "R/S"} and isinstance(state.get("reclaim_candle_a"), dict):
            state["candle_a"] = state["reclaim_candle_a"]
            state["candle_a_source"] = "reclaim_candle_a"
        completed_at = candle_timestamp(state.get("candle_b")) or candle_timestamp(state.get("latest_candle"))
        reference = state.get("active_leg1_reference") or state.get("leg1_reference")
        reference_candle = state.get("candle_b") if state.get("leg1_reference_owner") == "Candle B" else state.get("candle_a")
        state["leg1_state_locked"] = True
        state["leg1_completed_at"] = completed_at
        state["leg1_reference_price"] = reference
        state["leg1_reference_candle_time"] = candle_timestamp(reference_candle)
        state["leg1_direction"] = state.get("setup_direction")
        state["current_active_sequence_started_at"] = candle_timestamp(state.get("candle_a"))
        state["last_evaluated_candle_time"] = completed_at
        state["leg1_reference_extreme"] = state.get("anchor_extreme") or state.get("leg1_extreme")
        state["fifty_percent_rule_phase"] = state.get("fifty_percent_rule_phase") or "pre_leg1_only"
        state["state_transition_reason"] = "Leg 1 completed and locked."
    elif result.get("status") == "TERMINATED" and isinstance(result.get("state"), dict):
        result["state"].setdefault("invalidation_source", "step4")
        result["state"].setdefault("invalidation_source_step", "Step 4")
    return result


def build_step5_interaction(
    snapshot: dict[str, Any],
    step4: dict[str, Any],
    persisted_state: dict[str, Any],
) -> dict[str, Any] | None:
    """Build Step 5 input only after Step 4 confirms Leg 1."""
    if step4.get("status") != "READY" or step4.get("next_step") != "Step 5":
        return None
    step4_state = step4.get("state")
    if not isinstance(step4_state, dict):
        return None
    locked_ok, _locked_reason = valid_participation_locked_leg1_state(step4_state)
    if not locked_ok:
        return None

    current_candle = build_current_candle(snapshot)
    if current_candle is None:
        return None

    previous_step5 = persisted_state.get("step5") if isinstance(persisted_state.get("step5"), dict) else {}
    previous_state = previous_step5.get("state") if isinstance(previous_step5.get("state"), dict) else {}

    interaction = dict(step4_state)
    interaction.update(
        {
            "latest_candle": current_candle,
            "active_step5_path": previous_state.get("active_step5_path"),
            "leg2_status": previous_state.get("leg2_status"),
            "leg2_candle": previous_state.get("leg2_candle") or previous_state.get("leg2_candle_a") or current_candle,
            "leg2_candle_a": previous_state.get("leg2_candle_a") or previous_state.get("leg2_candle"),
            "leg2_candle_a_time": previous_state.get("leg2_candle_a_time"),
            "step5_confirmed": previous_state.get("step5_confirmed"),
            "step5_confirmation_window_active": previous_state.get("step5_confirmation_window_active"),
            "step5_participation_window_active": previous_state.get("step5_participation_window_active"),
            "step5_confirmation_candle_count": previous_state.get("step5_confirmation_candle_count"),
            "step5_participation_candle_count": previous_state.get("step5_participation_candle_count"),
            "anchor_extreme_swept": previous_state.get("anchor_extreme_swept"),
            "anchor_extreme_sweep_candle": previous_state.get("anchor_extreme_sweep_candle"),
            "step5_trigger_valid": previous_state.get("step5_trigger_valid"),
            "step5_trigger_candle": previous_state.get("step5_trigger_candle"),
            "step5_trigger_reason": previous_state.get("step5_trigger_reason"),
            "events": list(previous_step5.get("events") or step4.get("events") or []),
        }
    )
    return interaction


def step5_anchor_invalidation(result: dict[str, Any]) -> bool:
    """Return True when Step 5 invalidated the locked Leg 1 anchor."""
    if not isinstance(result, dict) or result.get("status") != "TERMINATED":
        return False
    reason = str(result.get("reason") or "")
    return "Anchor Extreme close invalidation" in reason


def reset_after_leg1_invalidation(
    snapshot: dict[str, Any],
    step4: dict[str, Any],
    step5_result: dict[str, Any],
    persisted_state: dict[str, Any],
) -> dict[str, Any]:
    """Clear active structure after a new candle invalidates locked Leg 1."""
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    active_liquidity = step4_state.get("active_liquidity") if isinstance(step4_state.get("active_liquidity"), dict) else {}
    source_candle = build_current_candle(snapshot)
    invalidated_at = datetime.now(timezone.utc).isoformat()
    invalidated = {
        "name": active_liquidity.get("name"),
        "price": active_liquidity.get("price"),
        "key": liquidity_key(active_liquidity.get("name"), active_liquidity.get("price")),
        "invalidated_at": invalidated_at,
        "invalidation_source_candle_time": candle_timestamp(source_candle),
        "reason": step5_result.get("reason"),
    }
    consumed = [
        record
        for record in consumed_liquidity_levels(persisted_state)
        if isinstance(record, dict) and record.get("key") != invalidated.get("key")
    ]
    if invalidated.get("key"):
        consumed.append(invalidated)

    state = {
        "leg1_state_locked": False,
        "leg1_completed_at": step4_state.get("leg1_completed_at"),
        "last_evaluated_candle_time": candle_timestamp(source_candle),
        "invalidated_at": invalidated_at,
        "invalidated_liquidity": invalidated,
        "invalidation_source_candle_time": invalidated.get("invalidation_source_candle_time"),
        "invalidation_source": "anchor_extreme_close",
        "invalidation_source_step": "Step 5",
        "consumed_liquidity_levels": consumed,
        "state_transition_reason": "Leg 1 invalidated by a new candle; active liquidity cleared until a fresh future interaction.",
        "active_liquidity": None,
        "leg1_status": "WAIT",
        "leg2_status": "WAIT",
    }
    return {
        "step": "Step 5",
        "status": "WAIT",
        "state": state,
        "next_step": "Step 2",
        "reason": state["state_transition_reason"],
        "events": [{"event": "leg1_invalidated_and_reset", "reason": state["state_transition_reason"]}],
    }


def evaluate_live_step5(snapshot: dict[str, Any], step4: dict[str, Any], persisted_state: dict[str, Any]) -> dict[str, Any]:
    """Evaluate Step 5 after Step 4 is ready; do not implement Step 6."""
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    if finalized_rejection_entry_state(persisted_state):
        previous_step5 = persisted_state.get("step5") if isinstance(persisted_state.get("step5"), dict) else {}
        previous_state = previous_step5.get("state") if isinstance(previous_step5.get("state"), dict) else {}
        if (
            step4_state.get("pathway_finalized") is True
            and previous_state.get("leg2_status") in {"CONFIRMED", "VALIDATED"}
            and normalized_pathway_name(previous_state.get("controlling_mode")) not in {"S/R", "R/S"}
        ):
            return mark_finalized_rejection_state(previous_step5)
    current_candle = build_current_candle(snapshot)
    locked_ok, locked_reason = valid_locked_leg1_state(step4_state)
    if step4.get("status") == "READY" and not locked_ok:
        return waiting_for_locked_leg1_result(step4, locked_reason or "Waiting for valid locked Leg 1 reference")
    if step4.get("status") == "READY" and locked_ok:
        completed_at = step4_state.get("leg1_completed_at")
        if current_candle is None or not candle_is_after(current_candle, completed_at) or leg2_candidate_same_sequence(step4_state, current_candle):
            return waiting_for_future_leg2_result(step4, current_candle)

    interaction = build_step5_interaction(snapshot, step4, persisted_state)
    if interaction is None:
        reason = "Step 5 waiting for Step 4 Leg 1 completion and a Leg 2 candidate candle."
        return {
            "step": "Step 5",
            "status": "WAIT",
            "state": {},
            "next_step": step4.get("next_step") or "Step 4",
            "reason": reason,
            "events": [{"event": "step5_waiting_for_inputs", "reason": reason}],
        }
    result = evaluate_step5(interaction)
    if isinstance(result.get("state"), dict):
        result["state"]["leg2_candidate_candle_time"] = candle_timestamp(current_candle)
        result["state"]["leg2_same_sequence_rejected"] = False
        result["state"].setdefault("leg2_wait_reason", None)
    if step5_anchor_invalidation(result):
        return reset_after_leg1_invalidation(snapshot, step4, result, persisted_state)
    return result


def build_step6_interaction(
    snapshot: dict[str, Any],
    step5: dict[str, Any],
    persisted_state: dict[str, Any],
) -> dict[str, Any] | None:
    """Build Step 6 input only after Step 5 confirms structure."""
    if step5.get("status") != "READY" or step5.get("next_step") != "Step 6":
        return None
    step5_state = step5.get("state")
    if not isinstance(step5_state, dict):
        return None

    current_candle = build_snapshot_candle(snapshot)
    if current_candle is None:
        return None

    previous_step6 = persisted_state.get("step6") if isinstance(persisted_state.get("step6"), dict) else {}
    previous_state = previous_step6.get("state") if isinstance(previous_step6.get("state"), dict) else {}

    interaction = dict(step5_state)
    for key in (
        "extended_retrace_entry_valid",
        "extended_retrace_entry_price",
        "extended_retrace_entry_active",
        "extended_retrace_pending",
        "extended_retrace_blocked_immediate_entry",
        "extended_retrace_block_reason",
        "extended_retrace_extension_ticks",
        "extended_retrace_extension_atr_percent",
        "extended_retrace_expires_at_candle",
        "extended_retrace_invalidation_price",
        "extended_retrace_intrabar_fill",
        "extended_retrace_step6_extreme",
        "extended_retrace_step6_candle",
        "extended_retrace_step6_candle_time",
        "extended_retrace_origin_leg2_close",
        "extended_retrace_candles_elapsed",
        "extended_retrace_expired",
        "extended_retrace_invalidated",
        "extended_retrace_entry_triggered",
        "extended_retrace_intrabar_fill",
        "extended_retrace_blocked_entry_type",
        "extended_retrace_blocked_entry_price",
        "step6_sequence_candle_count",
        "phase1_candle_count",
        "last_step6_sequence_candle_time",
        "step6_window_active",
        "step6_window_started_at",
        "step6_window_candle_index",
        "step6_window_remaining",
        "step6_window_expires_at",
        "phase1_anchor",
        "active_entry_anchor",
    ):
        if key in previous_state:
            interaction[key] = previous_state.get(key)
    interaction.update(
        {
            "entry_candle": current_candle,
            "latest_candle": current_candle,
            "sc": previous_state.get("sc") or step5_state.get("leg2_candle"),
            "sc2": previous_state.get("sc2"),
            "sc3": previous_state.get("sc3"),
            "current_sc": previous_state.get("current_sc"),
            "sc_progression_count": previous_state.get("sc_progression_count") or 1,
            "events": list(previous_step6.get("events") or step5.get("events") or []),
        }
    )
    interaction["step6_window_active"] = True
    interaction["step6_window_started_at"] = interaction.get("step6_window_started_at") or step5_state.get("step6_window_started_at") or step5_state.get("leg2_candle_a_time")
    interaction["step6_window_candle_index"] = interaction.get("step6_window_candle_index") or step5_state.get("step6_window_candle_index") or 0
    interaction["step6_window_remaining"] = interaction.get("step6_window_remaining") if interaction.get("step6_window_remaining") is not None else step5_state.get("step6_window_remaining", 4)
    interaction["step6_window_expires_at"] = interaction.get("step6_window_expires_at") or step5_state.get("step6_window_expires_at")
    return interaction


def unique_bars_by_time(*sources: Any) -> list[dict[str, Any]]:
    """Return candles with timestamps, sorted by parsed candle time."""
    by_time: dict[str, dict[str, Any]] = {}
    for source in sources:
        items = source if isinstance(source, list) else [source]
        for item in items:
            if not isinstance(item, dict):
                continue
            timestamp = candle_timestamp(item)
            if not timestamp:
                continue
            if all(item.get(key) is not None for key in ("open", "high", "low", "close")):
                by_time[timestamp] = item
    return sorted(by_time.values(), key=lambda item: parse_candle_time(candle_timestamp(item)) or datetime.min.replace(tzinfo=timezone.utc))


def step2_continuation_controlling_structure(
    side: Any,
    bars: list[dict[str, Any]],
    confirmation_time: Any,
) -> dict[str, Any] | None:
    """Return the opposing control extreme that preceded the Step 2 rejection drive."""
    confirmation_dt = parse_candle_time(confirmation_time)
    if not confirmation_dt:
        return None
    ordered_bars = unique_bars_by_time(bars)
    prior_bars = [candle for candle in ordered_bars if (parse_candle_time(candle_timestamp(candle)) or confirmation_dt) < confirmation_dt]
    confirmation_candle = next(
        (candle for candle in ordered_bars if same_candle_time(candle_timestamp(candle), confirmation_time)),
        None,
    )
    if not prior_bars:
        return None

    def candle_prices(candle: dict[str, Any]) -> tuple[float | None, float | None, float | None, float | None]:
        return (
            optional_float(candle.get("open")),
            optional_float(candle.get("high")),
            optional_float(candle.get("low")),
            optional_float(candle.get("close")),
        )

    def structure_from(candle: dict[str, Any]) -> dict[str, Any] | None:
        _open, high, low, close = candle_prices(candle)
        if high is None or low is None:
            return None
        return {
            "high": high,
            "low": low,
            "start_time": candle_timestamp(candle),
            "end_time": candle_timestamp(candle),
            "last_directional_close": close,
            "source_step": "Step 2",
        }

    def extend_structure(structure: dict[str, Any], candle: dict[str, Any]) -> None:
        _open, high, low, close = candle_prices(candle)
        if high is not None:
            structure["high"] = max(float(structure["high"]), high)
        if low is not None:
            structure["low"] = min(float(structure["low"]), low)
        structure["end_time"] = candle_timestamp(candle)
        structure["last_directional_close"] = close

    def public_structure(structure: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(structure, dict):
            return None
        return {
            "high": structure.get("high"),
            "low": structure.get("low"),
            "start_time": structure.get("start_time"),
            "end_time": structure.get("end_time"),
            "source_step": "Step 2",
        }

    if side == "lower":
        active: dict[str, Any] | None = None
        last_completed: dict[str, Any] | None = None
        previous: dict[str, Any] | None = None
        for candle in prior_bars:
            open_price, _high, _low, close = candle_prices(candle)
            _prev_open, prev_high, _prev_low, _prev_close = candle_prices(previous) if previous else (None, None, None, None)
            if close is None:
                previous = candle
                continue
            if active is not None and optional_float(active.get("low")) is not None and close < float(active["low"]):
                last_completed = active
                active = None
            if (
                active is None
                and previous is not None
                and open_price is not None
                and prev_high is not None
                and close > open_price
                and close > prev_high
            ):
                active = structure_from(candle)
            elif active is not None:
                extend_structure(active, candle)
            previous = candle
        confirmation_close = optional_float(confirmation_candle.get("close")) if isinstance(confirmation_candle, dict) else None
        if active is not None and confirmation_close is not None and optional_float(active.get("low")) is not None and confirmation_close < float(active["low"]):
            last_completed = active
        return public_structure(last_completed)
    if side == "upper":
        active = None
        last_completed = None
        previous = None
        for candle in prior_bars:
            open_price, _high, _low, close = candle_prices(candle)
            _prev_open, _prev_high, prev_low, _prev_close = candle_prices(previous) if previous else (None, None, None, None)
            if close is None:
                previous = candle
                continue
            if active is not None and optional_float(active.get("high")) is not None and close > float(active["high"]):
                last_completed = active
                active = None
            if (
                active is None
                and previous is not None
                and open_price is not None
                and prev_low is not None
                and close < open_price
                and close < prev_low
            ):
                active = structure_from(candle)
            elif active is not None:
                extend_structure(active, candle)
            previous = candle
        confirmation_close = optional_float(confirmation_candle.get("close")) if isinstance(confirmation_candle, dict) else None
        if active is not None and confirmation_close is not None and optional_float(active.get("high")) is not None and confirmation_close > float(active["high"]):
            last_completed = active
        return public_structure(last_completed)
    return None


def apply_step2_continuation_structure_fields(step_state: dict[str, Any], structure: dict[str, Any] | None) -> None:
    if not isinstance(structure, dict):
        return
    step_state["continuation_controlling_structure_high"] = structure.get("high")
    step_state["continuation_controlling_structure_low"] = structure.get("low")
    step_state["continuation_controlling_structure_start_time"] = structure.get("start_time")
    step_state["continuation_controlling_structure_end_time"] = structure.get("end_time")
    step_state["continuation_controlling_structure_source_step"] = structure.get("source_step") or "Step 2"


def continuation_structure_condition(mode: str, candle: dict[str, Any], level: float) -> bool:
    close = optional_float(candle.get("close"))
    if close is None:
        return False
    if mode == "S/R":
        return close < level
    if mode == "R/S":
        return close > level
    return False


def continuation_controlling_structure_from_bars(
    mode: str,
    level: float,
    bars: list[dict[str, Any]],
    reclaim_time: Any,
) -> dict[str, Any] | None:
    """Find the final uninterrupted close-through push before the continuation reclaim."""
    reclaim_dt = parse_candle_time(reclaim_time)
    if not reclaim_dt:
        return None
    active: dict[str, Any] | None = None
    for candle in bars:
        candle_time = parse_candle_time(candle_timestamp(candle))
        if not candle_time or candle_time >= reclaim_dt:
            continue
        if continuation_structure_condition(mode, candle, level):
            high = optional_float(candle.get("high"))
            low = optional_float(candle.get("low"))
            open_price = optional_float(candle.get("open"))
            close_price = optional_float(candle.get("close"))
            if high is None or low is None:
                continue
            if (
                active is not None
                and mode == "S/R"
                and open_price is not None
                and close_price is not None
                and close_price > open_price
                and close_price > optional_float(active.get("last_directional_close"))
            ):
                active = None
                continue
            if (
                active is not None
                and mode == "R/S"
                and open_price is not None
                and close_price is not None
                and close_price < open_price
                and close_price < optional_float(active.get("last_directional_close"))
            ):
                active = None
                continue
            if active is None:
                active = {
                    "high": high,
                    "low": low,
                    "start_time": candle_timestamp(candle),
                    "end_time": candle_timestamp(candle),
                    "last_directional_close": close_price,
                }
            else:
                active["high"] = max(float(active["high"]), high)
                active["low"] = min(float(active["low"]), low)
                active["end_time"] = candle_timestamp(candle)
                active["last_directional_close"] = close_price
        else:
            active = None
    return active


def continuation_structure_swept(
    mode: str,
    structure: dict[str, Any],
    bars: list[dict[str, Any]],
    reclaim_time: Any,
    tick_size: Any,
) -> bool:
    reclaim_dt = parse_candle_time(reclaim_time)
    if not reclaim_dt:
        return False
    tick = optional_float(tick_size)
    high = optional_float(structure.get("high"))
    low = optional_float(structure.get("low"))
    for candle in bars:
        candle_time = parse_candle_time(candle_timestamp(candle))
        if not candle_time or candle_time <= reclaim_dt:
            continue
        candle_high = optional_float(candle.get("high"))
        candle_low = optional_float(candle.get("low"))
        if mode == "S/R" and high is not None and candle_high is not None:
            if candle_high >= high + tick if tick is not None else candle_high > high:
                return True
        if mode == "R/S" and low is not None and candle_low is not None:
            if candle_low <= low - tick if tick is not None else candle_low < low:
                return True
    return False


def continuation_controlling_structure_status(
    snapshot: dict[str, Any],
    interaction: dict[str, Any],
) -> dict[str, Any]:
    """Return continuation controlling-structure sweep status for S/R or R/S."""
    mode = normalized_pathway_name(interaction.get("controlling_mode") or interaction.get("current_controlling_mode"))
    if mode not in {"S/R", "R/S"}:
        return {"required": False}
    level = optional_float(interaction.get("pathway_level") or interaction.get("level"))
    reclaim = interaction.get("reclaim_candle_a") if isinstance(interaction.get("reclaim_candle_a"), dict) else None
    reclaim_time = candle_timestamp(reclaim)
    if level is None or not reclaim_time:
        reason = "Continuation controlling-structure sweep requires a pathway level and reclaim candle."
        return {
            "required": True,
            "swept": False,
            "wait_reason": reason,
            "events": [{"event": "continuation_controlling_structure_missing", "reason": reason}],
        }
    symbol = str(snapshot.get("normalized_symbol") or snapshot.get("symbol") or "NQ")
    history = recent_closed_bars(symbol, 120)
    current_candle = build_snapshot_candle(snapshot)
    bars = unique_bars_by_time(
        history,
        interaction.get("initial_candle_a") if isinstance(interaction.get("initial_candle_a"), dict) else None,
        reclaim,
        interaction.get("candle_a") if isinstance(interaction.get("candle_a"), dict) else None,
        interaction.get("candle_b") if isinstance(interaction.get("candle_b"), dict) else None,
        interaction.get("leg2_candle") if isinstance(interaction.get("leg2_candle"), dict) else None,
        current_candle,
    )
    structure = continuation_controlling_structure_from_bars(mode, level, bars, reclaim_time)
    if not structure:
        reason = "Continuation controlling-structure sweep requires a close-through structure before the reclaim candle."
        return {
            "required": True,
            "swept": False,
            "wait_reason": reason,
            "events": [{"event": "continuation_controlling_structure_not_found", "reason": reason}],
        }
    swept = continuation_structure_swept(mode, structure, bars, reclaim_time, interaction.get("tick_size") or (snapshot.get("liquidity") or {}).get("tick_size"))
    reason = None if swept else (
        "S/R continuation entry requires a wick sweep above the continuation controlling-structure high."
        if mode == "S/R"
        else "R/S continuation entry requires a wick sweep below the continuation controlling-structure low."
    )
    return {
        "required": True,
        "swept": swept,
        "high": structure.get("high"),
        "low": structure.get("low"),
        "start_time": structure.get("start_time"),
        "end_time": structure.get("end_time"),
        "wait_reason": reason,
        "events": [] if swept else [{"event": "continuation_controlling_structure_sweep_required", "reason": reason}],
    }


def apply_continuation_structure_fields(state: dict[str, Any], status: dict[str, Any]) -> None:
    if status.get("required") is not True:
        return
    state["continuation_controlling_structure_high"] = status.get("high")
    state["continuation_controlling_structure_low"] = status.get("low")
    state["continuation_controlling_structure_start_time"] = status.get("start_time")
    state["continuation_controlling_structure_end_time"] = status.get("end_time")
    state["continuation_controlling_structure_swept"] = status.get("swept") is True
    state["continuation_controlling_structure_wait_reason"] = status.get("wait_reason")


def evaluate_live_step6(snapshot: dict[str, Any], step5: dict[str, Any], persisted_state: dict[str, Any]) -> dict[str, Any]:
    """Evaluate Step 6 after Step 5 is ready; do not place orders."""
    previous_step6 = persisted_state.get("step6") if isinstance(persisted_state.get("step6"), dict) else {}
    previous_step6_state = previous_step6.get("state") if isinstance(previous_step6.get("state"), dict) else {}
    step5_state = step5.get("state") if isinstance(step5.get("state"), dict) else {}
    if decision_status(previous_step6) == "CONFIRM":
        previous_control = previous_step6_state.get("current_pathway_control")
        current_control = step5_state.get("current_pathway_control")
        previous_mode = normalized_pathway_name(previous_step6_state.get("current_controlling_mode") or previous_step6_state.get("controlling_mode"))
        current_mode = normalized_pathway_name(step5_state.get("current_controlling_mode") or step5_state.get("controlling_mode"))
        if previous_control == current_control and previous_mode == current_mode:
            return previous_step6
    if finalized_rejection_entry_state(persisted_state):
        if (
            step5_state.get("pathway_finalized") is True
            and normalized_pathway_name(step5_state.get("controlling_mode")) not in {"S/R", "R/S"}
        ):
            return mark_finalized_rejection_state(previous_step6)
    interaction = build_step6_interaction(snapshot, step5, persisted_state)
    if interaction is None:
        reason = "Step 6 waiting for Step 5 confirmation and an entry candidate candle."
        return {
            "step": "Step 6",
            "status": "WAIT",
            "state": {},
            "next_step": step5.get("next_step") or "Step 5",
            "reason": reason,
            "events": [{"event": "step6_waiting_for_inputs", "reason": reason}],
        }
    continuation_status = continuation_controlling_structure_status(snapshot, interaction)
    if continuation_status.get("required") is True:
        apply_continuation_structure_fields(interaction, continuation_status)
        if continuation_status.get("swept") is not True:
            reason = str(continuation_status.get("wait_reason") or "Continuation controlling-structure sweep is required before Step 6 entry.")
            return {
                "step": "Step 6",
                "status": "WAIT",
                "state": interaction,
                "next_step": "Step 6",
                "reason": reason,
                "events": list(interaction.get("events") or []) + list(continuation_status.get("events") or []),
            }
    result = evaluate_step6(interaction)
    if continuation_status.get("required") is True and isinstance(result.get("state"), dict):
        apply_continuation_structure_fields(result["state"], continuation_status)
    return result


def run_once(symbol: str = "NQ", persist: bool = True) -> dict[str, Any]:
    """Return a one-shot market snapshot. No trading logic is run."""
    persisted_state = load_entry_state()
    requested_symbol = str(symbol or "NQ").strip().upper()
    normalized_symbol = root_symbol(requested_symbol)
    snapshot = get_latest_market_snapshot(normalized_symbol)
    snapshot["requested_symbol"] = requested_symbol
    snapshot["normalized_symbol"] = normalized_symbol
    snapshot["tv_context"] = load_tv_context(normalized_symbol)
    snapshot["tv_context_status"] = tv_context_freshness_status(snapshot["tv_context"])
    persisted_state = sanitize_stale_session_state(
        persisted_state,
        normalized_symbol,
        local_session_date(snapshot.get("latest_bar_time")),
    )
    persisted_state = apply_observation_cycle_reset(persisted_state, normalized_symbol, snapshot)
    symbol_persisted_state = symbol_scoped_persisted_state(persisted_state, normalized_symbol)
    levels = active_levels_from_tv_context(snapshot["tv_context"])
    liquidity = classify_liquidity_location(
        snapshot.get("latest_price"),
        levels,
        normalized_symbol,
    )
    snapshot["liquidity"] = liquidity
    step_2_1a = evaluate_live_step_2_1a(snapshot, levels, liquidity, persisted_state)
    rejection = rejection_from_step2_activation(step_2_1a, normalized_symbol)
    snapshot["step_2_1a"] = step_2_1a
    snapshot["rejection"] = rejection
    snapshot["atr"] = load_rithmic_atr_snapshot(normalized_symbol)
    snapshot["step25"] = evaluate_live_step25(snapshot, rejection, step_2_1a, symbol_persisted_state)
    snapshot["step3"] = evaluate_live_step3(snapshot, rejection, snapshot["step25"], step_2_1a, symbol_persisted_state)
    snapshot["step4"] = evaluate_live_step4(snapshot, rejection, snapshot["step25"], snapshot["step3"], symbol_persisted_state)
    snapshot["step5"] = evaluate_live_step5(snapshot, snapshot["step4"], symbol_persisted_state)
    active_name, active_price = active_liquidity_from_snapshot(snapshot)
    step4_state = snapshot["step4"].get("state") if isinstance(snapshot["step4"].get("state"), dict) else {}
    prior_locked_leg1, _prior_locked_reason = valid_participation_locked_leg1_state(step4_state)
    if (
        snapshot.get("latest_price") is not None
        and not valid_active_liquidity_selection(active_name, active_price)
        and (candle_close_confirmed(snapshot) or not prior_locked_leg1)
    ):
        clear_downstream_state_without_active_liquidity(snapshot)
    else:
        snapshot["step6"] = evaluate_live_step6(snapshot, snapshot["step5"], symbol_persisted_state)
    if isinstance(snapshot["step5"].get("state"), dict) and snapshot["step5"]["state"].get("invalidated_at"):
        snapshot["suppress_active_liquidity"] = True
        snapshot["step_2_1a"] = {
            **dict(snapshot.get("step_2_1a") or {}),
            "active_level": None,
            "level_price": None,
            "active_liquidity_group": None,
            "last_interacted_liquidity": None,
            "state_transition_reason": snapshot["step5"]["state"].get("state_transition_reason"),
        }
        snapshot["step4"] = {
            "step": "Step 4",
            "status": "WAIT",
            "state": dict(snapshot["step5"]["state"]),
            "next_step": "Step 2",
            "reason": snapshot["step5"]["state"].get("state_transition_reason"),
            "events": snapshot["step5"].get("events") or [],
        }
        snapshot["step6"] = evaluate_live_step6(snapshot, snapshot["step5"], symbol_persisted_state)
    snapshot["gateway"] = evaluate_gateway(
        snapshot,
        snapshot["tv_context"],
        levels,
        rejection,
    )
    mask_unconfirmed_step4_leg1_invalidation(
        snapshot,
        "Monitoring current 1-minute candle until close confirmation.",
    )
    if persist:
        persist_state(snapshot)
    return snapshot


def result_reason(result: dict[str, Any] | None, fallback: str) -> str:
    """Return a deterministic human-readable reason for a step result."""
    if not isinstance(result, dict):
        return fallback
    reason = result.get("reason")
    if reason:
        return str(reason)
    events = result.get("events")
    if isinstance(events, list) and events:
        last_event = events[-1]
        if isinstance(last_event, dict) and last_event.get("reason"):
            return str(last_event["reason"])
    return fallback


def decision_status(result: dict[str, Any] | None) -> str:
    """Map engine result status to WAIT / CONFIRM / INVALIDATE for operator status."""
    if not isinstance(result, dict):
        return "WAIT"
    status = str(result.get("status") or "").upper()
    state = result.get("state") if isinstance(result.get("state"), dict) else {}
    if status in {"ENTRY_CONFIRMED", "CONFIRMED"} or state.get("entry_triggered") is True:
        return "CONFIRM"
    if status in {"TERMINATED", "INVALID", "BLOCKED"}:
        return "INVALIDATE"
    if status == "READY":
        return "CONFIRM"
    return "WAIT"


def finalized_rejection_entry_state(persisted_state: dict[str, Any]) -> bool:
    """Return True when a prior rejection entry is complete and no longer live."""
    step6 = persisted_state.get("step6") if isinstance(persisted_state.get("step6"), dict) else {}
    state = step6.get("state") if isinstance(step6.get("state"), dict) else {}
    if decision_status(step6) != "CONFIRM":
        return False
    control = state.get("current_pathway_control")
    mode = normalized_pathway_name(state.get("current_controlling_mode") or state.get("controlling_mode"))
    if control == "continuation" or mode in {"S/R", "R/S"}:
        return False
    return control in {None, "rejection"} or mode in {None, "Normal Rejection Mode"}


def mark_finalized_rejection_state(step_result: dict[str, Any]) -> dict[str, Any]:
    """Mark a persisted rejection result as historical rather than a live handoff."""
    result = dict(step_result)
    state = dict(result.get("state") if isinstance(result.get("state"), dict) else {})
    state["interaction_state"] = "FINALIZED"
    state["pathway_lifecycle_status"] = state.get("pathway_lifecycle_status") or "ENTERED"
    state["pathway_finalized"] = True
    result["state"] = state
    result["events"] = list(result.get("events") or [])
    return result


def active_liquidity_from_snapshot(snapshot: dict[str, Any]) -> tuple[Any, Any]:
    """Return active liquidity only when the current snapshot is interacting with it."""
    if snapshot.get("suppress_active_liquidity") is True:
        return None, None
    step_2_1a = snapshot.get("step_2_1a") if isinstance(snapshot.get("step_2_1a"), dict) else {}
    rejection = snapshot.get("rejection") if isinstance(snapshot.get("rejection"), dict) else {}
    liquidity = snapshot.get("liquidity") if isinstance(snapshot.get("liquidity"), dict) else {}

    locked_owner = step_2_1a.get("step2_locked_owner") if isinstance(step_2_1a.get("step2_locked_owner"), dict) else {}
    locked_active = locked_owner.get("active_liquidity") if isinstance(locked_owner.get("active_liquidity"), dict) else {}
    if (
        step_2_1a.get("step_2_activated") is True
        and locked_owner.get("pathway") == "rejection"
        and valid_active_liquidity_selection(locked_active.get("name"), locked_active.get("price"))
    ):
        return locked_active.get("display_name") or locked_active.get("name"), locked_active.get("price")

    last_interacted = step_2_1a.get("last_interacted_liquidity")
    name = (
        step_2_1a.get("active_level")
        or (last_interacted or {}).get("name")
        or rejection.get("trigger_level")
    )
    price = (
        step_2_1a.get("level_price")
        or (last_interacted or {}).get("price")
        or rejection.get("trigger_price")
    )
    if valid_active_liquidity_selection(name, price):
        display_name = (last_interacted or {}).get("display_name") if isinstance(last_interacted, dict) else None
        group = step_2_1a.get("active_liquidity_group")
        if not display_name and isinstance(group, dict):
            display_name = group.get("display_name")
        return display_name or name, price

    selected_liquidity = None
    if candle_close_confirmed(snapshot):
        selected_liquidity = selected_active_liquidity_from_context(
            snapshot.get("tv_context"),
            snapshot.get("latest_price"),
            snapshot.get("ohlc") if isinstance(snapshot.get("ohlc"), dict) else None,
            float((liquidity or {}).get("tick_size") or 0.25),
        )
    if selected_liquidity and valid_active_liquidity_selection(selected_liquidity.get("name"), selected_liquidity.get("price")):
        return selected_liquidity.get("display_name") or selected_liquidity.get("name"), selected_liquidity.get("price")

    return None, None


def active_liquidity_group_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Return selected ACTIVE stack group details when the selected liquidity is stacked."""
    if snapshot.get("suppress_active_liquidity") is True:
        return None
    step_2_1a = snapshot.get("step_2_1a") if isinstance(snapshot.get("step_2_1a"), dict) else {}
    locked_owner = step_2_1a.get("step2_locked_owner") if isinstance(step_2_1a.get("step2_locked_owner"), dict) else {}
    locked_group = locked_owner.get("active_liquidity_group") if isinstance(locked_owner.get("active_liquidity_group"), dict) else None
    if step_2_1a.get("step_2_activated") is True and locked_owner.get("pathway") == "rejection" and locked_group:
        return locked_group
    group = step_2_1a.get("active_liquidity_group")
    if isinstance(group, dict):
        return group
    last_interacted = step_2_1a.get("last_interacted_liquidity")
    group = (last_interacted or {}).get("group") if isinstance(last_interacted, dict) else None
    if isinstance(group, dict):
        return group
    liquidity = snapshot.get("liquidity") if isinstance(snapshot.get("liquidity"), dict) else {}
    selected_liquidity = selected_active_liquidity_from_context(
        snapshot.get("tv_context"),
        snapshot.get("latest_price"),
        snapshot.get("ohlc") if isinstance(snapshot.get("ohlc"), dict) else None,
        float((liquidity or {}).get("tick_size") or 0.25),
    )
    group = selected_liquidity.get("group") if selected_liquidity else None
    return group if isinstance(group, dict) else None


def first_invalidation_reason(*results: dict[str, Any]) -> str | None:
    """Return the first invalidation reason from evaluated steps."""
    for result in results:
        if decision_status(result) == "INVALIDATE":
            return result_reason(result, "Invalidated by EntryAgent rule.")
    return None


def step_order(step: Any) -> float:
    """Return blueprint step order for public consistency checks."""
    text = str(step or "").strip()
    if not text.startswith("Step "):
        return 0.0
    try:
        return float(text.replace("Step ", "", 1))
    except ValueError:
        return 0.0


def result_invalidation_source_step(result: dict[str, Any]) -> str | None:
    """Return the invalidating step from an engine result."""
    if not isinstance(result, dict) or decision_status(result) != "INVALIDATE":
        return None
    state = result.get("state") if isinstance(result.get("state"), dict) else {}
    source_step = state.get("invalidation_source_step") or state.get("terminated_by") or result.get("step")
    return str(source_step) if source_step else None


def public_invalidation_from_results(current_step: str, *results: dict[str, Any]) -> dict[str, Any]:
    """Expose invalidation only when its source step is not ahead of public current_step."""
    public_order = step_order(current_step)
    for result in results:
        if decision_status(result) != "INVALIDATE":
            continue
        source_step = result_invalidation_source_step(result)
        step6_window_expired = (
            current_step == "Step 5"
            and source_step == "Step 6"
            and isinstance(result.get("state"), dict)
            and result["state"].get("step6_window_candle_index") is not None
            and result["state"].get("step6_window_remaining") == 0
        )
        if step_order(source_step) <= public_order or step6_window_expired:
            state = result.get("state") if isinstance(result.get("state"), dict) else {}
            return {
                "reason": result_reason(result, "Invalidated by EntryAgent rule."),
                "source_step": source_step,
                "source": state.get("invalidation_source"),
                "source_candle_time": state.get("invalidation_source_candle_time"),
                "invalidated_at": state.get("invalidated_at"),
                "invalidated_liquidity": state.get("invalidated_liquidity"),
            }
    return {
        "reason": None,
        "source_step": None,
        "source": None,
        "source_candle_time": None,
        "invalidated_at": None,
        "invalidated_liquidity": None,
    }


def is_atr_required_reason(reason: str | None) -> bool:
    """Return True when a setup is waiting on ATR data, not structurally invalid."""
    return bool(reason and "requires ATR" in reason)


def publication_gate_enabled(snapshot: dict[str, Any]) -> bool:
    """Return True when current-step publication gating should be enforced."""
    return True


def add_publication_gate_debug(
    snapshot: dict[str, Any],
    attempted_step: str,
    published_step: str,
    reason: str,
) -> None:
    """Record why a downstream current_step promotion was blocked."""
    events = snapshot.setdefault("publication_gate_debug", [])
    if not isinstance(events, list):
        events = []
        snapshot["publication_gate_debug"] = events
    event = {
        "event": "current_step_promotion_blocked",
        "attempted_step": attempted_step,
        "published_step": published_step,
        "reason": reason,
    }
    if event not in events:
        events.append(event)


def step3_publication_passed(step3: dict[str, Any]) -> bool:
    """Return True only when Step 3 officially authorizes Step 4 publication."""
    return step3.get("status") == "ALLOW_STEP_4" and step3.get("next_step") == "Step 4"


def milestone_closed_or_prior(snapshot: dict[str, Any], state: dict[str, Any], paths: tuple[tuple[str, ...], ...]) -> bool:
    """Return True when a milestone is not sourced from the current live candle."""
    if candle_close_confirmed(snapshot):
        return True
    latest_time = snapshot.get("latest_bar_time")
    return not latest_time or not state_touches_candle_time(state, latest_time, paths)


def leg1_publication_locked(snapshot: dict[str, Any], step4: dict[str, Any]) -> bool:
    """Return True only when Leg 1 is a publishable closed-candle milestone."""
    state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    locked_ok, _reason = valid_participation_locked_leg1_state(state)
    return locked_ok and milestone_closed_or_prior(
        snapshot,
        state,
        (
            ("leg1_completed_at",),
            ("leg1_reference_candle_time",),
            ("last_evaluated_candle_time",),
            ("candle_b", "timestamp"),
            ("latest_candle", "timestamp"),
        ),
    )


def leg2_publication_locked(snapshot: dict[str, Any], step5: dict[str, Any]) -> bool:
    """Return True only when Step 5 has locked/validated Leg 2 for Step 6 publication."""
    if step5.get("status") != "READY" or step5.get("next_step") != "Step 6":
        return False
    state = step5.get("state") if isinstance(step5.get("state"), dict) else {}
    locked = state.get("leg2_status") in {"VALIDATED", "COMPLETE"} or state.get("step5_participation_validated") is True
    return locked and milestone_closed_or_prior(
        snapshot,
        state,
        (
            ("leg2_candidate_candle_time",),
            ("leg2_completed_at",),
            ("last_evaluated_candle_time",),
            ("leg2_candle", "timestamp"),
            ("latest_candle", "timestamp"),
        ),
    )


def ungated_current_step_from_snapshot(snapshot: dict[str, Any]) -> str:
    """Return the legacy current step before NQ publication gating is applied."""
    if snapshot.get("latest_price") is None:
        return "WAIT_FOR_MARKET_DATA"
    if snapshot.get("suppress_active_liquidity") is True:
        return "Step 2"
    step6 = snapshot.get("step6") if isinstance(snapshot.get("step6"), dict) else {}
    step5 = snapshot.get("step5") if isinstance(snapshot.get("step5"), dict) else {}
    step4 = snapshot.get("step4") if isinstance(snapshot.get("step4"), dict) else {}
    step3 = snapshot.get("step3") if isinstance(snapshot.get("step3"), dict) else {}
    step25 = snapshot.get("step25") if isinstance(snapshot.get("step25"), dict) else {}
    rejection = snapshot.get("rejection") if isinstance(snapshot.get("rejection"), dict) else {}
    step6_state = step6.get("state") if isinstance(step6.get("state"), dict) else {}

    if decision_status(step6) == "CONFIRM" or step6_state.get("extended_retrace_pending") is True:
        return "Step 6"
    if step5.get("status") == "READY":
        return "Step 6"
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    step4_leg1_ready, _step4_leg1_reason = valid_participation_locked_leg1_state(step4_state)
    if step4.get("status") == "READY" and step4_leg1_ready:
        return "Step 5"
    if not candle_close_confirmed(snapshot):
        return "Step 2"
    if step3.get("status") == "ALLOW_STEP_4":
        return "Step 4"
    if step25.get("status") == "READY":
        return "Step 3"
    if candle_close_confirmed(snapshot) and rejection.get("rejection_mode") == "ON":
        return "Step 2.5"
    return "Step 2"


def current_step_from_snapshot(snapshot: dict[str, Any]) -> str:
    """Return the last public milestone; Step 2 is close-confirmed pathway activation."""
    if not publication_gate_enabled(snapshot):
        return ungated_current_step_from_snapshot(snapshot)
    if snapshot.get("latest_price") is None:
        return "WAIT_FOR_MARKET_DATA"
    if snapshot.get("suppress_active_liquidity") is True:
        return "Step 2"
    step6 = snapshot.get("step6") if isinstance(snapshot.get("step6"), dict) else {}
    step5 = snapshot.get("step5") if isinstance(snapshot.get("step5"), dict) else {}
    step4 = snapshot.get("step4") if isinstance(snapshot.get("step4"), dict) else {}
    step3 = snapshot.get("step3") if isinstance(snapshot.get("step3"), dict) else {}
    leg1_ready = leg1_publication_locked(snapshot, step4)
    leg2_ready = leg2_publication_locked(snapshot, step5)
    step5_state = step5.get("state") if isinstance(step5.get("state"), dict) else {}
    step6_state = step6.get("state") if isinstance(step6.get("state"), dict) else {}

    if (
        decision_status(step6) == "CONFIRM"
        or step6_state.get("extended_retrace_pending") is True
        or step5.get("status") == "READY"
        or step5.get("next_step") == "Step 6"
    ):
        if leg1_ready and leg2_ready:
            if decision_status(step6) == "CONFIRM" or step6_state.get("extended_retrace_pending") is True:
                return "Step 6"
            return "Step 5"
        reason = "Step 6 publication blocked until Leg 1 and Leg 2 are close-confirmed."
        published = "Step 4" if leg1_ready else "Step 2"
        add_publication_gate_debug(snapshot, "Step 6", published, reason)
        if published == "Step 4":
            return "Step 4"
        return "Step 2"

    if step5_state.get("leg2_status") == "CONFIRMED" and leg1_ready:
        return "Step 5"

    if step4.get("status") == "READY" or step4.get("next_step") == "Step 5":
        if leg1_ready:
            return "Step 4"
        reason = "Step 4 publication blocked until Leg 1 is close-confirmed."
        published = "Step 2"
        add_publication_gate_debug(snapshot, "Step 4", published, reason)
        return "Step 2"

    if step4.get("next_step") == "Step 4" and not step3_publication_passed(step3):
        reason = "Step 4 publication blocked until Step 3 officially passes."
        add_publication_gate_debug(snapshot, "Step 4", "Step 2", reason)
        return "Step 2"
    return "Step 2"


def wait_reason_for_current_step(
    current_step: str,
    active_name: Any,
    step4: dict[str, Any],
    step5: dict[str, Any],
    step6: dict[str, Any],
) -> str:
    """Return operator-facing text without redefining current_step as the next watched step."""
    if current_step == "Step 2" and not active_name:
        return "No active liquidity selected."
    if current_step == "Step 2":
        return "Step 2 confirmed: liquidity close activated a valid pathway; public state holds at this milestone until Step 4 confirms."
    if current_step in {"Step 2.5", "Step 3", "Step 4"}:
        return result_reason(step4, "Leg 1 waiting for Step 4 requirements.")
    if current_step == "Step 5":
        return result_reason(step5, "Leg 2 waiting for Step 5 requirements.")
    if current_step == "Step 6":
        step6_state = step6.get("state") if isinstance(step6.get("state"), dict) else {}
        if step6_state.get("extended_retrace_pending") is True and step6_state.get("extended_retrace_block_reason"):
            return str(step6_state.get("extended_retrace_block_reason"))
        return result_reason(step6, "Entry candidate waiting for Step 6 requirements.")
    return result_reason(step6, result_reason(step5, result_reason(step4, "Waiting for EntryAgent setup requirements.")))


def current_step_public_status(current_step: str, active_name: Any, rejection_active: bool) -> str:
    """Return the public milestone status used by UI surfaces."""
    if current_step == "Step 2" and active_name and rejection_active:
        return "CONFIRMED"
    if current_step in {"Step 4", "Step 5", "Step 6"}:
        return "CONFIRMED"
    return "WAIT"


def confirmed_time_from_candle(candle: Any) -> str | None:
    """Return a candle close timestamp from a candle-like dict."""
    return candle_timestamp(candle if isinstance(candle, dict) else None)


def step2_confirmed_at(snapshot: dict[str, Any], step_2_1a: dict[str, Any], current_step_status: str) -> str | None:
    """Return the Step 2 liquidity-close confirmation candle time."""
    if current_step_status != "CONFIRMED" or step_2_1a.get("step_2_activated") is not True:
        return None
    locked_owner = step_2_1a.get("step2_locked_owner") if isinstance(step_2_1a.get("step2_locked_owner"), dict) else None
    if isinstance(locked_owner, dict) and locked_owner.get("pathway") == "rejection" and locked_owner.get("activated_at"):
        return str(locked_owner.get("activated_at"))
    return (
        confirmed_time_from_candle(step_2_1a.get("candle_a"))
        or step_2_1a.get("last_evaluated_bar_time")
        or (snapshot.get("latest_bar_time") if candle_close_confirmed(snapshot) else None)
    )


def leg1_confirmed_at(step4_state: dict[str, Any], leg1_published: bool) -> str | None:
    """Return the public Leg 1 confirmation candle time."""
    if not leg1_published:
        return None
    return step4_state.get("leg1_completed_at") or confirmed_time_from_candle(step4_state.get("candle_b"))


def leg2_confirmed_at(step5_state: dict[str, Any], leg2_published: bool) -> str | None:
    """Return the public Leg 2 validation candle time."""
    if not leg2_published:
        return None
    return (
        step5_state.get("leg2_candidate_candle_time")
        or step5_state.get("leg2_completed_at")
        or confirmed_time_from_candle(step5_state.get("leg2_candle"))
    )


def entry_confirmed_at(snapshot: dict[str, Any], step6_state: dict[str, Any], entry_status: str) -> str | None:
    """Return the public entry trigger candle time, never sourced from a live forming candle."""
    if entry_status != "CONFIRM":
        return None
    entry_time = (
        confirmed_time_from_candle(step6_state.get("entry_candle"))
        or step6_state.get("entry_confirmed_at")
        or step6_state.get("last_evaluated_candle_time")
    )
    if not entry_time:
        return None
    if not candle_close_confirmed(snapshot) and same_candle_time(entry_time, snapshot.get("latest_bar_time")):
        return None
    return entry_time


def current_step_confirmed_at(
    current_step: str,
    step2_time: str | None,
    leg1_time: str | None,
    leg2_time: str | None,
    entry_time: str | None,
) -> str | None:
    """Return the candle time for the currently public milestone."""
    if current_step == "Step 2":
        return step2_time
    if current_step == "Step 4":
        return leg1_time
    if current_step == "Step 5":
        return leg2_time
    if current_step == "Step 6":
        return entry_time or leg2_time
    return None


def normalized_pathway_name(value: Any) -> str:
    """Return a display-only pathway name from existing evaluated status fields."""
    text = str(value or "").strip().upper().replace(" ", "")
    if text in {"S/R", "SR", "S/RPULLBACKCONTINUATION"}:
        return "S/R"
    if text in {"R/S", "RS", "R/SPULLBACKCONTINUATION"}:
        return "R/S"
    if text and ("NORMAL" in text or "REJECTION" in text):
        return "Normal"
    return "none"


def continuation_type_from_state(step25_state: dict[str, Any], controlling_mode: Any) -> str:
    """Return S/R, R/S, or none for visibility without changing pathway control."""
    controlling = normalized_pathway_name(controlling_mode)
    if controlling in {"S/R", "R/S"}:
        return controlling
    candidate_modes = step25_state.get("candidate_modes")
    if isinstance(candidate_modes, list):
        for mode in candidate_modes:
            normalized = normalized_pathway_name(mode)
            if normalized in {"S/R", "R/S"}:
                return normalized
    return "none"


def selected_pathway_from_mode(controlling_mode: Any) -> str | None:
    controlling = normalized_pathway_name(controlling_mode)
    if controlling == "Normal":
        return "rejection"
    if controlling in {"S/R", "R/S"}:
        return "continuation"
    return None


def pathway_visibility_status(
    side: str,
    rejection_active: bool,
    controlling_mode: Any,
    continuation_type: str,
    invalidated: bool,
    step25_ready: bool,
) -> str:
    """Return display-only pathway status for Rejection or Continuation side."""
    if invalidated:
        if side == "rejection" or continuation_type != "none":
            return "invalidated"
        return "inactive"
    if not rejection_active:
        return "inactive"

    controlling = normalized_pathway_name(controlling_mode)
    if side == "rejection":
        if controlling == "Normal":
            return "controlling"
        if controlling in {"S/R", "R/S"}:
            return "frozen"
        return "active" if step25_ready else "candidate"

    if continuation_type == "none":
        return "inactive"
    if controlling == continuation_type:
        return "controlling"
    if controlling == "Normal":
        return "candidate"
    return "candidate" if step25_ready else "active"


def locked_entry_status(symbol: str, snapshot: dict[str, Any], current_step: str, reason: str) -> dict[str, Any]:
    side = {
        "pathway_status": "inactive",
        "current_pathway_control": None,
        "current_controlling_mode": None,
        "current_step": None,
        "current_step_label": None,
        "current_step_status": None,
        "current_step_confirmed_at": None,
        "selected_pathway": None,
        "setup_direction": None,
        "leg1_status": "WAIT",
        "leg1_state": "WAIT",
        "leg2_status": "WAIT",
        "leg2_state": "WAIT",
        "entry_status": "WAIT",
        "leg1_confirmed_at": None,
        "leg2_confirmed_at": None,
        "entry_status_confirmed_at": None,
    }
    ohlc = snapshot.get("ohlc") if isinstance(snapshot.get("ohlc"), dict) else {}
    return {
        "symbol": str(snapshot.get("requested_symbol") or snapshot.get("symbol") or symbol).upper(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "candle_time": snapshot.get("latest_bar_time"),
        "candle_open": ohlc.get("open"),
        "candle_high": ohlc.get("high"),
        "candle_low": ohlc.get("low"),
        "candle_close": ohlc.get("close"),
        "current_step": current_step,
        "current_step_label": current_step_label(current_step),
        "current_step_status": "WAIT",
        "current_step_confirmed_at": None,
        "selected_pathway": None,
        "active_liquidity_name": None,
        "active_liquidity_price": None,
        "active_liquidity_group": None,
        "liquidity_price": None,
        "liquidity_group": None,
        "close_vs_level": None,
        "next_liquidity_above": None,
        "next_liquidity_below": None,
        "setup_direction": None,
        "rejection_mode_entered": False,
        "sr_rs_context": None,
        "continuation_type": "none",
        "current_pathway_control": None,
        "current_controlling_mode": None,
        "current_continuation_type": "none",
        "rejection_pathway_status": "inactive",
        "continuation_pathway_status": "inactive",
        "rejection_side": dict(side),
        "continuation_side": {**side, "continuation_type": "none"},
        "leg1_status": "WAIT",
        "leg1_state": "WAIT",
        "leg1_confirmed_at": None,
        "leg1_locked": False,
        "leg1_state_locked": False,
        "leg2_status": "WAIT",
        "leg2_state": "WAIT",
        "entry_status": "WAIT",
        "wait_reason": reason,
        "last_decision": f"WAIT: {reason}",
        "invalidation_reason": None,
        "internal_invalidation_reason": None,
        "invalidation_source_candle_time": None,
        "invalidation_source": None,
        "invalidation_source_step": None,
        "invalidated_at": None,
        "invalidated_liquidity": None,
        "publication_gate_debug": [],
        "consumed_liquidity_levels": [],
        "step6_window_active": False,
        "step6_window_started_at": None,
        "step6_window_candle_index": None,
        "step6_window_remaining": None,
        "step6_window_expires_at": None,
    }


def build_entry_status(symbol: str = "NQ") -> dict[str, Any]:
    """Build the minimal read-only Entry Manager status for one symbol."""
    requested_symbol = str(symbol or "NQ").strip().upper()
    normalized_symbol = root_symbol(requested_symbol)
    try:
        pre_snapshot = get_latest_market_snapshot(normalized_symbol)
    except Exception:
        pre_snapshot = None
    if isinstance(pre_snapshot, dict):
        lock = entry_window_lock_for_snapshot(pre_snapshot)
        if lock is not None and has_stale_session_lifecycle(load_entry_state(), normalized_symbol, pre_snapshot):
            current_step, reason = lock
            pre_snapshot["requested_symbol"] = requested_symbol
            return locked_entry_status(symbol, pre_snapshot, current_step, reason)
    snapshot = run_once(symbol, persist=True)
    hide_unconfirmed_current_candle_advancement(snapshot)
    apply_consumed_entry_setup_guard(snapshot)
    step4 = snapshot.get("step4") if isinstance(snapshot.get("step4"), dict) else {}
    step5 = snapshot.get("step5") if isinstance(snapshot.get("step5"), dict) else {}
    step6 = snapshot.get("step6") if isinstance(snapshot.get("step6"), dict) else {}
    step_2_1a = snapshot.get("step_2_1a") if isinstance(snapshot.get("step_2_1a"), dict) else {}
    rejection = snapshot.get("rejection") if isinstance(snapshot.get("rejection"), dict) else {}
    step25_state = ((snapshot.get("step25") or {}).get("state") or {}) if isinstance((snapshot.get("step25") or {}).get("state"), dict) else {}
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    step5_state = step5.get("state") if isinstance(step5.get("state"), dict) else {}
    step6_state = step6.get("state") if isinstance(step6.get("state"), dict) else {}
    step2_owner_state = step_2_1a.get("step2_locked_owner") if isinstance(step_2_1a.get("step2_locked_owner"), dict) else {}
    liquidity = snapshot.get("liquidity") if isinstance(snapshot.get("liquidity"), dict) else {}
    ohlc = snapshot.get("ohlc") if isinstance(snapshot.get("ohlc"), dict) else {}
    active_name, active_price = active_liquidity_from_snapshot(snapshot)
    active_group = active_liquidity_group_from_snapshot(snapshot)
    no_active_liquidity = snapshot.get("latest_price") is not None and not valid_active_liquidity_selection(active_name, active_price)
    current_step = current_step_from_snapshot(snapshot)
    step_label = current_step_label(current_step)
    raw_invalidation_reason = first_invalidation_reason(step4, step5, step6)
    public_invalidation = public_invalidation_from_results(current_step, step4, step5, step6)
    invalidation_reason = public_invalidation["reason"]
    atr_required_reason = invalidation_reason if is_atr_required_reason(invalidation_reason) else None
    raw_entry_status = decision_status(step6)
    if raw_entry_status == "INVALIDATE" and not invalidation_reason:
        raw_entry_status = "WAIT"
    entry_status = "WAIT_ATR_REQUIRED" if atr_required_reason else ("INVALIDATE" if invalidation_reason else raw_entry_status)
    if atr_required_reason:
        invalidation_reason = None
    entry_authorization_blocked = entry_status == "CONFIRM" and before_entry_authorization(snapshot)
    if entry_authorization_blocked:
        entry_status = "WAIT"

    if snapshot.get("latest_price") is None:
        wait_reason = "No market price available."
    elif atr_required_reason:
        wait_reason = atr_required_reason
    elif entry_authorization_blocked:
        wait_reason = "Observation window active until 06:30 PT; entry authorization is blocked."
    elif entry_status == "WAIT" and not invalidation_reason and not candle_close_confirmed(snapshot):
        live_mask_reason = result_reason(step4, "")
        wait_reason = live_mask_reason if "current 1-minute candle" in live_mask_reason else wait_reason_for_current_step(current_step, active_name, step4, step5, step6)
    elif entry_status == "WAIT" and not invalidation_reason:
        wait_reason = wait_reason_for_current_step(current_step, active_name, step4, step5, step6)
    else:
        wait_reason = None
    probe = step_2_1a.get("pre_activation_probe_boundary") if isinstance(step_2_1a.get("pre_activation_probe_boundary"), dict) else {}
    if (
        current_step == "Step 2"
        and step_2_1a.get("step_2_activated") is not True
        and probe.get("active") is True
        and probe.get("boundary_price") is not None
    ):
        direction_text = "above" if probe.get("side") == "upper" else "below"
        wait_reason = f"Step 2 pending: waiting for a later candle close {direction_text} raid boundary {probe.get('boundary_price')}."

    if entry_status == "CONFIRM":
        last_decision = f"CONFIRM: {result_reason(step6, 'Entry setup confirmed.')}"
    elif atr_required_reason:
        last_decision = f"WAIT_ATR_REQUIRED: {atr_required_reason}"
    elif invalidation_reason:
        last_decision = f"INVALIDATE: {invalidation_reason}"
    else:
        last_decision = f"WAIT: {wait_reason or result_reason(step4, 'Waiting for EntryAgent setup requirements.')}"

    close_vs_level = None
    try:
        if active_price is not None and ohlc.get("close") is not None:
            close_vs_level = float(ohlc.get("close")) - float(active_price)
    except (TypeError, ValueError):
        close_vs_level = None

    structure_active_liquidity = step4_state.get("active_liquidity") if isinstance(step4_state.get("active_liquidity"), dict) else None
    structure_control = pathway_control_from_price(
        structure_active_liquidity,
        ohlc.get("close") if ohlc.get("close") is not None else snapshot.get("latest_price"),
    )
    locked_structure = step4_state.get("leg1_state_locked") is True and step4_state.get("leg1_status") == "COMPLETE"
    if locked_structure and no_active_liquidity and structure_active_liquidity:
        active_name = structure_active_liquidity.get("display_name") or structure_active_liquidity.get("name")
        active_price = structure_active_liquidity.get("price")
        no_active_liquidity = snapshot.get("latest_price") is not None and not valid_active_liquidity_selection(active_name, active_price)
        try:
            if active_price is not None and ohlc.get("close") is not None:
                close_vs_level = float(ohlc.get("close")) - float(active_price)
        except (TypeError, ValueError):
            close_vs_level = None
    current_pathway_control = (
        step6_state.get("current_pathway_control")
        or step5_state.get("current_pathway_control")
        or step4_state.get("current_pathway_control")
        or (structure_control.get("current_pathway_control") if locked_structure else None)
    )
    current_controlling_mode = (
        step6_state.get("current_controlling_mode")
        or step5_state.get("current_controlling_mode")
        or step4_state.get("current_controlling_mode")
        or (structure_control.get("current_controlling_mode") if locked_structure else None)
    )
    current_continuation_type = (
        step6_state.get("current_continuation_type")
        or step5_state.get("current_continuation_type")
        or step4_state.get("current_continuation_type")
        or (structure_control.get("current_continuation_type") if locked_structure else None)
    )

    authoritative_controlling_mode = (
        step25_state.get("controlling_mode")
        or step4_state.get("controlling_mode")
        or step5_state.get("controlling_mode")
        or step6_state.get("controlling_mode")
        or current_controlling_mode
    )
    sr_rs_context = None if no_active_liquidity and not locked_structure else authoritative_controlling_mode
    setup_direction = None if no_active_liquidity and not locked_structure else (
        step6_state.get("setup_direction")
        or step5_state.get("setup_direction")
        or step4_state.get("setup_direction")
        or (rejection.get("watch_side") if candle_close_confirmed(snapshot) else None)
    )
    raw_leg1_status = "WAIT_ATR_REQUIRED" if atr_required_reason else (step4_state.get("leg1_status") or decision_status(step4))
    raw_leg2_status = step5_state.get("leg2_status") or decision_status(step5)
    leg1_published = current_step in {"Step 4", "Step 5", "Step 6"}
    leg2_published = current_step in {"Step 5", "Step 6"}
    leg1_status = raw_leg1_status if leg1_published else "WAIT"
    leg2_status = raw_leg2_status if leg2_published else "WAIT"
    if current_step == "Step 4" and leg1_status == "COMPLETE":
        step_label = "Shared Leg 1 Confirmed"
    step2_rejection_confirmed = (
        current_step == "Step 2"
        and valid_active_liquidity_selection(active_name, active_price)
        and rejection.get("rejection_mode") == "ON"
        and candle_close_confirmed(snapshot)
    )
    step2_pathway_confirmed = step_2_1a.get("step_2_activated") is True or step2_rejection_confirmed
    public_setup_direction = setup_direction if leg1_published or current_step == "Step 6" or step2_rejection_confirmed else None
    rejection_active = False if (no_active_liquidity and not locked_structure) or not candle_close_confirmed(snapshot) else step2_pathway_confirmed or locked_structure
    selected_pathway = selected_pathway_from_mode(sr_rs_context)
    continuation_type = (
        normalized_pathway_name(sr_rs_context)
        if selected_pathway == "continuation"
        else continuation_type_from_state(step25_state, sr_rs_context)
    )
    if selected_pathway == "rejection":
        current_pathway_control = "rejection"
        current_controlling_mode = "Normal Rejection Mode"
        current_continuation_type = continuation_type if continuation_type in {"S/R", "R/S"} else "none"
    elif selected_pathway == "continuation":
        current_pathway_control = "continuation"
        current_controlling_mode = continuation_type if continuation_type in {"S/R", "R/S"} else sr_rs_context
        current_continuation_type = continuation_type
    elif rejection.get("rejection_mode") == "ON" and candle_close_confirmed(snapshot):
        current_pathway_control = "rejection"
        current_controlling_mode = "Normal Rejection Mode"
        current_continuation_type = continuation_type if continuation_type in {"S/R", "R/S"} else "none"
        selected_pathway = "rejection"
    if current_step == "Step 2" and not step2_pathway_confirmed and not locked_structure:
        sr_rs_context = None
        selected_pathway = None
        continuation_type = "none"
        current_pathway_control = "inactive"
        current_controlling_mode = None
        current_continuation_type = "none"
        public_setup_direction = None
    shared_leg1_with_continuation = (
        current_step == "Step 4"
        and leg1_status == "COMPLETE"
        and continuation_type in {"S/R", "R/S"}
        and step4_state.get("shared_leg1_uses_initial_candle_a") is True
    )
    if shared_leg1_with_continuation:
        selected_pathway = "continuation"
        current_pathway_control = "continuation"
        current_controlling_mode = continuation_type
        current_continuation_type = continuation_type
    invalidated = bool(invalidation_reason)
    step25_ready = (snapshot.get("step25") or {}).get("status") == "READY"
    current_step_status = current_step_public_status(current_step, active_name, rejection_active)
    step2_time = step2_confirmed_at(snapshot, step_2_1a, current_step_status)
    if selected_pathway == "continuation":
        continuation_step2_time = candle_timestamp(step25_state.get("reclaim_candle_a") if isinstance(step25_state.get("reclaim_candle_a"), dict) else None)
        if continuation_step2_time:
            step2_time = continuation_step2_time
    leg1_time = leg1_confirmed_at(step4_state, leg1_published)
    leg2_time = leg2_confirmed_at(step5_state, leg2_published)
    entry_time = entry_confirmed_at(snapshot, step6_state, entry_status)
    current_step_time = current_step_confirmed_at(current_step, step2_time, leg1_time, leg2_time, entry_time)
    finalized_rejection_projection = (
        selected_pathway == "rejection"
        and entry_status == "CONFIRM"
        and (
            step6_state.get("pathway_finalized") is True
            or step6_state.get("pathway_lifecycle_status") in {"ENTERED", "CONSUMED"}
            or step6_state.get("interaction_state") == "FINALIZED"
        )
    )
    continuation_selected = selected_pathway == "continuation"
    rejection_side = {
        "pathway_status": (
            "entered"
            if finalized_rejection_projection
            else "frozen"
            if continuation_selected
            else
            "controlling"
            if shared_leg1_with_continuation and rejection_active and not invalidated
            else pathway_visibility_status("rejection", rejection_active, sr_rs_context, continuation_type, invalidated, step25_ready)
        ),
        "current_pathway_control": None if continuation_selected else current_pathway_control,
        "current_controlling_mode": None if continuation_selected else current_controlling_mode,
        "current_step": None if continuation_selected else current_step,
        "current_step_label": None if continuation_selected else step_label,
        "current_step_status": None if continuation_selected else current_step_status,
        "current_step_confirmed_at": None if continuation_selected else current_step_time,
        "selected_pathway": None if continuation_selected else selected_pathway,
        "setup_direction": None if selected_pathway == "continuation" else (rejection.get("watch_side") if rejection_active and leg1_published else public_setup_direction),
        "leg1_status": None if continuation_selected else leg1_status,
        "leg2_status": None if continuation_selected else leg2_status,
        "entry_status": None if continuation_selected else entry_status,
        "leg1_confirmed_at": None if continuation_selected else leg1_time,
        "leg2_confirmed_at": None if continuation_selected else leg2_time,
        "entry_status_confirmed_at": None if continuation_selected else entry_time,
    }
    continuation_side = {
        "continuation_type": continuation_type,
        "pathway_status": (
            "controlling"
            if continuation_selected
            else pathway_visibility_status("continuation", rejection_active, sr_rs_context, continuation_type, invalidated, step25_ready)
        ),
        "current_pathway_control": current_pathway_control,
        "current_controlling_mode": current_controlling_mode,
        "current_step": current_step if continuation_selected else None,
        "current_step_label": step_label if continuation_selected else None,
        "current_step_status": current_step_status if continuation_selected else None,
        "current_step_confirmed_at": current_step_time if continuation_selected else None,
        "selected_pathway": selected_pathway if continuation_selected else None,
        "setup_direction": "SHORT" if continuation_type == "S/R" else "LONG" if continuation_type == "R/S" else None,
        "leg1_status": leg1_status if continuation_selected else None,
        "leg2_status": leg2_status if continuation_selected else None,
        "entry_status": entry_status if continuation_selected else None,
        "leg1_confirmed_at": leg1_time if continuation_selected else None,
        "leg2_confirmed_at": leg2_time if continuation_selected else None,
        "entry_status_confirmed_at": entry_time if continuation_selected else None,
    }
    return {
        "symbol": str(snapshot.get("requested_symbol") or symbol).upper(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "candle_time": snapshot.get("latest_bar_time"),
        "candle_open": ohlc.get("open"),
        "candle_high": ohlc.get("high"),
        "candle_low": ohlc.get("low"),
        "candle_close": ohlc.get("close"),
        "current_step": current_step,
        "current_step_label": step_label,
        "current_step_status": current_step_status,
        "current_step_confirmed_at": current_step_time,
        "selected_pathway": selected_pathway,
        "active_liquidity_name": active_name,
        "active_liquidity_price": active_price,
        "active_liquidity_group": active_group,
        "liquidity_price": active_price,
        "liquidity_group": (active_group or {}).get("name") if isinstance(active_group, dict) else None,
        "close_vs_level": close_vs_level,
        "next_liquidity_above": liquidity.get("nearest_level_above"),
        "next_liquidity_below": liquidity.get("nearest_level_below"),
        "setup_direction": public_setup_direction,
        "rejection_mode_entered": rejection_active,
        "sr_rs_context": sr_rs_context,
        "continuation_type": continuation_type,
        "current_pathway_control": current_pathway_control,
        "current_controlling_mode": current_controlling_mode,
        "current_continuation_type": continuation_type,
        "rejection_pathway_status": rejection_side["pathway_status"],
        "continuation_pathway_status": continuation_side["pathway_status"],
        "rejection_side": rejection_side,
        "continuation_side": continuation_side,
        "leg1_status": leg1_status,
        "leg1_state": leg1_status,
        "leg1_confirmed_at": leg1_time,
        "leg2_status": leg2_status,
        "leg2_state": leg2_status,
        "leg2_confirmed_at": leg2_time,
        "leg2_reference_price": (step5_state.get("active_leg1_reference") or step5_state.get("leg1_reference")) if leg2_published else None,
        "entry_status": entry_status,
        "entry_status_confirmed_at": entry_time,
        "entry_type_number": step6_state.get("entry_type_number"),
        "entry_type_name": step6_state.get("entry_type_name"),
        "entry_model": step6_state.get("entry_model"),
        "entry_model_reason": step6_state.get("entry_model_reason"),
        "wait_reason": wait_reason,
        "invalidation_reason": invalidation_reason,
        "internal_invalidation_reason": raw_invalidation_reason,
        "last_decision": last_decision,
        "publication_gate_debug": snapshot.get("publication_gate_debug") if isinstance(snapshot.get("publication_gate_debug"), list) else [],
        "leg1_state_locked": step4_state.get("leg1_state_locked"),
        "leg1_locked": step4_state.get("leg1_state_locked"),
        "leg1_completed_at": step4_state.get("leg1_completed_at") if leg1_published else None,
        "leg1_reference_price": (step4_state.get("leg1_reference_price") or step4_state.get("leg1_reference")) if leg1_published else None,
        "leg1_reference_candle_time": step4_state.get("leg1_reference_candle_time") if leg1_published else None,
        "leg1_direction": (step4_state.get("leg1_direction") or step4_state.get("setup_direction")) if leg1_published else None,
        "last_evaluated_candle_time": (step4_state.get("last_evaluated_candle_time") if leg1_published else None) or (step5_state.get("last_evaluated_candle_time") if leg2_published else None),
        "invalidated_at": public_invalidation["invalidated_at"],
        "invalidated_liquidity": public_invalidation["invalidated_liquidity"],
        "invalidation_source_candle_time": public_invalidation["source_candle_time"],
        "invalidation_source": public_invalidation["source"],
        "invalidation_source_step": public_invalidation["source_step"],
        "consumed_liquidity_levels": step4_state.get("consumed_liquidity_levels") or step5_state.get("consumed_liquidity_levels") or [],
        "state_transition_reason": step4_state.get("state_transition_reason") or step5_state.get("state_transition_reason"),
        "leg1_formed_at_percent": step4_state.get("leg1_formed_at_percent") if leg1_published else None,
        "leg1_50_percent_rule_passed": step4_state.get("leg1_50_percent_rule_passed") if leg1_published else None,
        "step4_proximity_distance": step4_state.get("proximity_distance") if leg1_published else None,
        "step4_proximity_daily_atr": step4_state.get("proximity_daily_atr") if leg1_published else None,
        "step4_proximity_atr_threshold": step4_state.get("proximity_atr_threshold") if leg1_published else None,
        "step4_proximity_atr_threshold_percent": step4_state.get("proximity_atr_threshold_percent") if leg1_published else None,
        "fifty_percent_rule_phase": step4_state.get("fifty_percent_rule_phase") if leg1_published else None,
        "leg1_window_active": step4_state.get("leg1_window_active") is True,
        "leg1_window_started_at": step4_state.get("leg1_window_started_at"),
        "leg1_window_candle_index": step4_state.get("leg1_window_candle_index"),
        "leg1_window_remaining": step4_state.get("leg1_window_remaining"),
        "leg1_window_expires_at": step4_state.get("leg1_window_expires_at"),
        "leg1_window_invalidated": step4_state.get("leg1_window_invalidated") is True,
        "leg1_window_invalidation_reason": step4_state.get("leg1_window_invalidation_reason"),
        "leg2_formed_at_percent": step5_state.get("leg2_formed_at_percent") if leg2_published else None,
        "leg2_25_percent_rule_passed": step5_state.get("leg2_25_percent_rule_passed") if leg2_published else None,
        "leg2_candidate_candle_time": step5_state.get("leg2_candidate_candle_time") if leg2_published else None,
        "leg2_same_sequence_rejected": step5_state.get("leg2_same_sequence_rejected") if leg2_published else None,
        "leg2_wait_reason": step5_state.get("leg2_wait_reason") if leg1_published else None,
        "step6_window_active": bool(step6_state.get("step6_window_active") or step5_state.get("step6_window_active")),
        "step6_window_started_at": step6_state.get("step6_window_started_at") or step5_state.get("step6_window_started_at"),
        "step6_window_candle_index": step6_state.get("step6_window_candle_index") if step6_state.get("step6_window_candle_index") is not None else step5_state.get("step6_window_candle_index"),
        "step6_window_remaining": step6_state.get("step6_window_remaining") if step6_state.get("step6_window_remaining") is not None else step5_state.get("step6_window_remaining"),
        "step6_window_expires_at": step6_state.get("step6_window_expires_at") or step5_state.get("step6_window_expires_at"),
        "continuation_controlling_structure_high": step6_state.get("continuation_controlling_structure_high") or step5_state.get("continuation_controlling_structure_high") or step2_owner_state.get("continuation_controlling_structure_high") or step_2_1a.get("continuation_controlling_structure_high"),
        "continuation_controlling_structure_low": step6_state.get("continuation_controlling_structure_low") or step5_state.get("continuation_controlling_structure_low") or step2_owner_state.get("continuation_controlling_structure_low") or step_2_1a.get("continuation_controlling_structure_low"),
        "continuation_controlling_structure_start_time": step6_state.get("continuation_controlling_structure_start_time") or step5_state.get("continuation_controlling_structure_start_time") or step2_owner_state.get("continuation_controlling_structure_start_time") or step_2_1a.get("continuation_controlling_structure_start_time"),
        "continuation_controlling_structure_end_time": step6_state.get("continuation_controlling_structure_end_time") or step5_state.get("continuation_controlling_structure_end_time") or step2_owner_state.get("continuation_controlling_structure_end_time") or step_2_1a.get("continuation_controlling_structure_end_time"),
        "continuation_controlling_structure_source_step": step6_state.get("continuation_controlling_structure_source_step") or step5_state.get("continuation_controlling_structure_source_step") or step2_owner_state.get("continuation_controlling_structure_source_step") or step_2_1a.get("continuation_controlling_structure_source_step"),
        "continuation_controlling_structure_swept": step6_state.get("continuation_controlling_structure_swept"),
        "continuation_controlling_structure_wait_reason": step6_state.get("continuation_controlling_structure_wait_reason"),
        "extended_retrace_entry_valid": step6_state.get("extended_retrace_entry_valid"),
        "extended_retrace_entry_price": step6_state.get("extended_retrace_entry_price"),
        "extended_retrace_entry_active": step6_state.get("extended_retrace_entry_active"),
        "extended_retrace_pending": step6_state.get("extended_retrace_pending"),
        "extended_retrace_blocked_immediate_entry": step6_state.get("extended_retrace_blocked_immediate_entry"),
        "extended_retrace_block_reason": step6_state.get("extended_retrace_block_reason"),
        "extended_retrace_extension_ticks": step6_state.get("extended_retrace_extension_ticks"),
        "extended_retrace_extension_atr_percent": step6_state.get("extended_retrace_extension_atr_percent"),
        "extended_retrace_expires_at_candle": step6_state.get("extended_retrace_expires_at_candle"),
        "extended_retrace_invalidation_price": step6_state.get("extended_retrace_invalidation_price"),
        "extended_retrace_intrabar_fill": step6_state.get("extended_retrace_intrabar_fill"),
    }


def persist_state(snapshot: dict[str, Any]) -> None:
    """Persist the latest one-shot snapshot state."""
    previous_state = load_entry_state()
    symbol_key = str(snapshot.get("normalized_symbol") or root_symbol(str(snapshot.get("symbol") or ""))).upper()
    previous_state_by_symbol = previous_state.get("state_by_symbol")
    state_by_symbol = dict(previous_state_by_symbol) if isinstance(previous_state_by_symbol, dict) else {}
    previous_last_by_symbol = previous_state.get("last_interacted_liquidity_by_symbol")
    last_by_symbol = dict(previous_last_by_symbol) if isinstance(previous_last_by_symbol, dict) else {}
    last_interacted = (snapshot.get("step_2_1a") or {}).get("last_interacted_liquidity")
    step2_locked_owner = (snapshot.get("step_2_1a") or {}).get("step2_locked_owner")
    step5_state_for_reset = ((snapshot.get("step5") or {}).get("state") or {}) if isinstance((snapshot.get("step5") or {}).get("state"), dict) else {}
    if step5_state_for_reset.get("invalidated_at"):
        step2_locked_owner = None
        if isinstance(snapshot.get("step_2_1a"), dict):
            snapshot["step_2_1a"].pop("step2_locked_owner", None)
    if symbol_key and isinstance(last_interacted, dict) and last_interacted.get("name"):
        last_by_symbol[symbol_key] = last_interacted
    elif symbol_key:
        last_by_symbol.pop(symbol_key, None)
    consumed_records = merge_consumed_liquidity_levels(
        ((snapshot.get("step_2_1a") or {}).get("consumed_liquidity_levels")),
        (((snapshot.get("step4") or {}).get("state") or {}).get("consumed_liquidity_levels")),
        (((snapshot.get("step5") or {}).get("state") or {}).get("consumed_liquidity_levels")),
        consumed_liquidity_levels(symbol_scoped_persisted_state(previous_state, symbol_key)),
    )
    previous_symbol_state = symbol_scoped_persisted_state(previous_state, symbol_key)
    symbol_state = {
        "symbol": snapshot.get("symbol"),
        "normalized_symbol": snapshot.get("normalized_symbol"),
        "requested_symbol": snapshot.get("requested_symbol"),
        "latest_price": snapshot.get("latest_price"),
        "latest_bar_time": snapshot.get("latest_bar_time"),
        "liquidity": snapshot.get("liquidity"),
        "step_2_1a": snapshot.get("step_2_1a"),
        "step2_locked_owner": step2_locked_owner,
        "last_interacted_liquidity": last_interacted,
        "last_interacted_liquidity_by_symbol": last_by_symbol,
        "consumed_liquidity_levels": consumed_records,
        "consumed_entry_setups": consumed_entry_setups(symbol_scoped_persisted_state(previous_state, symbol_key)),
        "step_2_1a_last_evaluated_bar_time": (snapshot.get("step_2_1a") or {}).get("last_evaluated_bar_time"),
        "step_2_1a_candle_index": (snapshot.get("step_2_1a") or {}).get("next_candle_index", 0),
        "rejection": snapshot.get("rejection"),
        "step25": snapshot.get("step25"),
        "step3": snapshot.get("step3"),
        "step4": snapshot.get("step4"),
        "step5": snapshot.get("step5"),
        "step6": snapshot.get("step6"),
        "gateway": snapshot.get("gateway"),
        "tv_context": snapshot.get("tv_context"),
        "tv_context_status": snapshot.get("tv_context_status"),
        "observation_reset_session_date": snapshot.get("observation_reset_session_date") or previous_symbol_state.get("observation_reset_session_date"),
        "observation_reset_bar_time": snapshot.get("observation_reset_bar_time") or previous_symbol_state.get("observation_reset_bar_time"),
        "observation_reset_at": snapshot.get("observation_reset_at") or previous_symbol_state.get("observation_reset_at"),
    }
    if symbol_key:
        state_by_symbol[symbol_key] = symbol_state

    state = dict(symbol_state)
    state["state_by_symbol"] = state_by_symbol
    state["last_interacted_liquidity_by_symbol"] = last_by_symbol
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def format_snapshot(snapshot: dict[str, Any]) -> str:
    lines = [
        f"symbol: {snapshot.get('symbol')}",
        f"latest price: {snapshot.get('latest_price')}",
        f"latest bar time: {snapshot.get('latest_bar_time')}",
    ]

    ohlc = snapshot.get("ohlc")
    if isinstance(ohlc, dict):
        lines.append(
            "latest bar OHLC: "
            f"O={ohlc.get('open')} H={ohlc.get('high')} "
            f"L={ohlc.get('low')} C={ohlc.get('close')}"
        )
    else:
        lines.append("latest bar OHLC: unavailable")

    liquidity = snapshot.get("liquidity") or {}
    step_2_1a = snapshot.get("step_2_1a") or {}
    probe = step_2_1a.get("pre_activation_probe_boundary") or {}
    rejection = snapshot.get("rejection") or {}
    step25 = snapshot.get("step25") or {}
    step3 = snapshot.get("step3") or {}
    step4 = snapshot.get("step4") or {}
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    step5 = snapshot.get("step5") or {}
    step6 = snapshot.get("step6") or {}
    lines.extend(
        [
            f"nearest_level_above: {liquidity.get('nearest_level_above')}",
            f"nearest_level_below: {liquidity.get('nearest_level_below')}",
            f"touched_levels: {liquidity.get('touched_levels')}",
            f"current_location: {liquidity.get('current_location')}",
            f"step_2_1a_available: {step_2_1a.get('available')}",
            f"step_2_1a_active_level: {step_2_1a.get('active_level')}",
            f"step_2_1a_activated: {step_2_1a.get('step_2_activated')}",
            f"step_2_1a_blocked: {step_2_1a.get('blocked')}",
            f"pre_activation_probe_boundary: {probe}",
            f"step_2_1a_events: {step_2_1a.get('events')}",
            f"rejection_mode: {rejection.get('rejection_mode')}",
            f"watch_side: {rejection.get('watch_side')}",
            f"trigger_level: {rejection.get('trigger_level')}",
            f"trigger_price: {rejection.get('trigger_price')}",
            f"trigger_priority: {rejection.get('trigger_priority')}",
            f"reason_text: {rejection.get('reason_text')}",
            f"step25_status: {step25.get('status')}",
            f"step25_next_step: {step25.get('next_step')}",
            f"step25_reason: {step25.get('reason')}",
            f"step3_status: {step3.get('status')}",
            f"step3_next_step: {step3.get('next_step')}",
            f"step3_reason: {step3.get('reason')}",
            f"step4_status: {step4.get('status')}",
            f"step4_next_step: {step4.get('next_step')}",
            f"step4_reason: {step4.get('reason')}",
            f"leg1_window_active: {step4_state.get('leg1_window_active')}",
            f"leg1_window_started_at: {step4_state.get('leg1_window_started_at')}",
            f"leg1_window_candle_index: {step4_state.get('leg1_window_candle_index')}",
            f"leg1_window_remaining: {step4_state.get('leg1_window_remaining')}",
            f"leg1_window_expires_at: {step4_state.get('leg1_window_expires_at')}",
            f"leg1_window_invalidated: {step4_state.get('leg1_window_invalidated')}",
            f"leg1_window_invalidation_reason: {step4_state.get('leg1_window_invalidation_reason')}",
            f"step5_status: {step5.get('status')}",
            f"step5_next_step: {step5.get('next_step')}",
            f"step5_reason: {step5.get('reason')}",
            f"step6_status: {step6.get('status')}",
            f"step6_next_step: {step6.get('next_step')}",
            f"step6_reason: {step6.get('reason')}",
        ]
    )

    gateway = snapshot.get("gateway") or {}
    lines.extend(
        [
            f"gateway_status: {gateway.get('gateway_status')}",
            f"gateway_reason: {gateway.get('gateway_reason')}",
            f"allowed_sides: {gateway.get('allowed_sides')}",
            f"session_phase: {gateway.get('session_phase')}",
            f"near_liquidity: {gateway.get('near_liquidity')}",
            f"nearest_level: {gateway.get('nearest_level')}",
        ]
    )

    tv_context = snapshot.get("tv_context")
    if isinstance(tv_context, dict):
        lines.extend(
            [
                f"tv_context_status: {snapshot.get('tv_context_status')}",
                f"normalized_symbol: {tv_context.get('normalized_symbol')}",
                f"time_zone: {tv_context.get('time_zone')}",
                f"pm_atr_pct: {tv_context.get('pm_atr_pct')}",
                f"daily_range_pct: {tv_context.get('daily_range_pct')}",
                f"received_at: {tv_context.get('received_at')}",
            ]
        )
    else:
        lines.append(f"tv_context_status: {snapshot.get('tv_context_status')}")
        lines.append("tv_context: unavailable")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="EntryAgent market snapshot utility.")
    parser.add_argument("--symbol", default="NQ", help="Root symbol to read, default: NQ")
    parser.add_argument("--once", action="store_true", help="Print one market snapshot and exit")
    parser.add_argument("--watch", action="store_true", help="Refresh the market snapshot every 5 seconds")
    return parser.parse_args()


def clear_screen() -> None:
    """Clear the console for watch mode readability."""
    os.system("cls" if os.name == "nt" else "clear")


def run_watch(symbol: str, refresh_seconds: int = 5) -> None:
    """Refresh the current EntryAgent diagnostics until interrupted."""
    try:
        while True:
            clear_screen()
            print(format_snapshot(run_once(symbol)))
            print()
            print("Press Ctrl+C to exit.")
            time.sleep(refresh_seconds)
    except KeyboardInterrupt:
        print("\nwatch stopped")


def main() -> int:
    args = parse_args()
    if args.once:
        print(format_snapshot(run_once(args.symbol)))
        return 0

    if args.watch:
        run_watch(args.symbol)
        return 0

    raise SystemExit("Use --once or --watch.")


if __name__ == "__main__":
    raise SystemExit(main())
