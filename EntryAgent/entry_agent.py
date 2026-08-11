"""Entry agent command line entry point."""

from __future__ import annotations

import argparse
import copy
import functools
import json
import math
import os
import sys
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from data_paths import data_path, feed_health_data_path, local_or_shared_path, log_active_data_root

from blueprint_rules import (
    detect_rejection_mode,
    evaluate_step_2_1a_candle,
    optional_float,
    side_for_level_price,
    step_2_1a_initial_state,
)
from gateway_engine import evaluate_gateway
from levels import classify_liquidity_location, root_symbol
from liquidity_stack_validation import (
    format_stack_validation_error,
    stack_group_side,
    stack_reference_price_from_context,
    stack_threshold_from_context,
    validate_liquidity_stack_structure,
)
from market_feed import get_latest_market_snapshot, recent_closed_bars
from step25_engine import evaluate_step25, select_pathway
from step3_engine import evaluate_step3
from step4_engine import STEP2_STEP4_50_LINE_TOUCHED, evaluate_step4, initialize_leg1_window
from step5_engine import evaluate_step5
from step6_engine import evaluate_step6

DATA_DIR = data_path()
ENTRY_AGENT_RUNTIME_DIR = local_or_shared_path(BASE_DIR, shared_prefix="entry_agent")
STATE_PATH = local_or_shared_path(BASE_DIR, "entry_agent_state.json", shared_prefix="entry_agent")
SIGNALS_PATH = local_or_shared_path(BASE_DIR, "signals.json", shared_prefix="entry_agent")
TV_CONTEXT_PATH = local_or_shared_path(BASE_DIR, "tv_context.json", shared_prefix="entry_agent")
TV_CONTEXT_BY_SYMBOL_PATH = local_or_shared_path(BASE_DIR, "tv_context_by_symbol.json", shared_prefix="entry_agent")
ENTRY_AGENT_AUDIT_DIR = data_path("entry_agent_audit")
STEP2_OWNER_DIAGNOSTICS_PATH = data_path("entry_step2_owner_diagnostics.jsonl")
RITHMIC_ATR_SNAPSHOT_PATH = data_path("rithmic_atr_snapshot.json")
RITHMIC_RECENT_BARS_PATH = data_path("rithmic_recent_bars.json")
RITHMIC_FEED_HEALTH_PATH = feed_health_data_path()
CANONICAL_ATR_FORMULA = "wilder_rma_14"
CANONICAL_ATR_FORMULA_VERSION = "wilder_rma_14_v1"
CANONICAL_ATR_SOURCE = "rithmic_exchange_time_rma14"
PERSISTENCE_STATE_PATH = data_path("persistence_state.json")
EXECUTOR_STATE_PATH = data_path("executor_state.json")
ENTRY_AGENT_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
log_active_data_root("entry_agent")
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
    "Step 2.5": "Step 2 Continuation (Continuation Logic)",
    "Step 3": "Step 3 (Participation)",
    "Step 4": "Step 4 (Leg 1 Formation)",
    "Step 5": "Step 5 (Leg 2 Confirmation)",
    "Step 6": "Step 6 (Entry Trigger)",
    "Step 7": "Step 7 (Invalidation / Reset)",
}
SUPPORTED_ROOT_SYMBOLS = {"NQ", "YM"}
ENTRY_STATE_LOCK = threading.RLock()
ENTRY_AUTHORITY_MUTATION_ALLOWED: ContextVar[bool] = ContextVar(
    "entry_authority_mutation_allowed",
    default=True,
)


@contextmanager
def entry_authority_mode(*, allow_mutation: bool) -> Any:
    """Bound one evaluation to an authoritative or projection-only context."""
    token = ENTRY_AUTHORITY_MUTATION_ALLOWED.set(bool(allow_mutation))
    try:
        yield
    finally:
        ENTRY_AUTHORITY_MUTATION_ALLOWED.reset(token)


def authoritative_mutation_allowed() -> bool:
    """Return whether the current call context may mutate Entry Agent authority."""
    return ENTRY_AUTHORITY_MUTATION_ALLOWED.get()


def require_authoritative_mutation(operation: str) -> None:
    """Fail closed when a writer is reached from read-side projection code."""
    if not authoritative_mutation_allowed():
        raise RuntimeError(
            f"authoritative Entry Agent mutation is prohibited during read-side projection: {operation}"
        )


def projection_only(function: Any) -> Any:
    """Run one public projection with authoritative writers disabled."""
    @functools.wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        with entry_authority_mode(allow_mutation=False):
            return function(*args, **kwargs)

    return wrapped


def evaluation_mode_from_persist(function: Any) -> Any:
    """Bind legacy run_once(persist=...) calls to an explicit authority mode."""
    @functools.wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        persist = kwargs.get("persist", args[1] if len(args) > 1 else True)
        with entry_authority_mode(allow_mutation=bool(persist)):
            return function(*args, **kwargs)

    return wrapped


def entry_state_transaction(function: Any) -> Any:
    """Serialize one complete Entry Agent state read/modify/write transaction."""
    @functools.wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        with ENTRY_STATE_LOCK:
            return function(*args, **kwargs)

    return wrapped


def public_step_name(current_step: Any) -> Any:
    """Translate deprecated internal step names to operator-facing terminology."""
    text = str(current_step or "").strip()
    if text == "Step 2.5":
        return "Step 2 Continuation"
    return current_step


def translate_public_terminology(text: Any) -> Any:
    """Translate deprecated internal terminology in operator-facing strings."""
    if not isinstance(text, str):
        return text
    translated = text.replace("Step 2.5", "Step 2 Continuation")
    translated = translated.replace("step2.5", "step2 continuation")
    translated = translated.replace("trade-state", "trade_state")
    return translated


def current_step_label(current_step: Any) -> str | None:
    """Return the operator-facing label for a blueprint step."""
    translated = public_step_name(current_step)
    if translated == "Step 2 Continuation":
        return STEP_LABELS.get("Step 2.5")
    return STEP_LABELS.get(str(translated))


def unsupported_symbol_result(requested_symbol: str) -> dict[str, Any]:
    """Return a read-only unsupported-symbol payload without persisting state."""
    return {
        "symbol": requested_symbol,
        "requested_symbol": requested_symbol,
        "normalized_symbol": None,
        "current_step": None,
        "current_step_label": None,
        "step2_lifecycle_window_terminated": False,
        "frozen_active_groups": [],
        "frozen_group_found": False,
        "frozen_group_display_name": None,
        "canonical_group_display_name": None,
        "selected_liquidity_name": None,
        "liquidity_level_name": None,
        "liquidity_level_price": None,
        "rejection_boundary": None,
        "continuation_boundary": None,
        "liquidity_lock": {
            "locked": False,
            "session_date": None,
            "lock_time": None,
            "lock_source": None,
            "active_liquidity_name": None,
            "liquidity_group": None,
            "liquidity_level_name": None,
            "liquidity_level_price": None,
            "rejection_boundary": None,
            "continuation_boundary": None,
        },
        "entry_status": "WAIT",
        "wait_reason": f"Unsupported symbol: {requested_symbol}. Entry Agent supports NQ and YM only.",
        "tv_context_status": "unsupported_symbol",
        "step2_owner_seeded_at": None,
        "step2_activated_at": None,
        "step2_confirmed_at": None,
        "step2_invalidated_at": None,
        "step2_owner_name": None,
        "step2_direction": None,
        "step2_event": None,
        "step2_reason": None,
        "step4_candle_a_time": None,
        "step4_candle_b_time": None,
        "step4_confirmed_at": None,
        "step4_window_count": None,
        "leg2_sweep_extreme": None,
        "step5_close_boundary": None,
        "step4_rejection_completed_at": None,
        "step4_invalidated_at": None,
        "step4_owner_name": None,
        "step4_direction": None,
        "trade_state": {"active": False, "released": False, "release_reason": None, "liquidity_level_name": None, "liquidity_level_price": None, "rejection_boundary": None, "continuation_boundary": None},
        "market_state": {"active_liquidity_name": None, "selected_liquidity_name": None, "liquidity_level_name": None, "liquidity_level_price": None, "rejection_boundary": None, "continuation_boundary": None},
        "step4_event": None,
        "liquidity": {},
        "step_2_1a": {"step_2_activated": False, "blocked": True, "reason": "unsupported_symbol"},
        "rejection": {"rejection_mode": "OFF", "reason_text": "unsupported_symbol"},
        "step25": no_active_liquidity_result("Step 2.5", "Unsupported symbol."),
        "step3": no_active_liquidity_result("Step 3", "Unsupported symbol."),
        "step4": no_active_liquidity_result("Step 4", "Unsupported symbol."),
        "step5": no_active_liquidity_result("Step 5", "Unsupported symbol."),
        "step6": no_active_liquidity_result("Step 6", "Unsupported symbol."),
        "gateway": no_active_liquidity_result("Gateway", "Unsupported symbol."),
    }


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
    session_date = snapshot_session_date(snapshot)
    recorded_date = symbol_state.get("observation_reset_session_date")
    if recorded_date == session_date:
        return False
    tv_context = load_tv_context(symbol)
    levels = tv_context.get("levels") if isinstance(tv_context, dict) else {}
    return any(
        isinstance(level, dict) and str(level.get("status") or "").upper() == "ACTIVE"
        for level in (levels.values() if isinstance(levels, dict) else [])
    )


@entry_state_transaction
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
    require_authoritative_mutation(f"write_json:{path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2) + "\n"
    temporary_path = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as file:
            file.write(serialized)
            file.flush()
            os.fsync(file.fileno())
        for attempt in range(8):
            try:
                os.replace(temporary_path, path)
                return
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(0.01 * (attempt + 1))
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


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
        "stack_extreme": group.get("stack_extreme") if isinstance(group, dict) else liquidity.get("stack_extreme"),
        "extreme_boundary": group.get("extreme_boundary") if isinstance(group, dict) else liquidity.get("extreme_boundary"),
        "wick_boundary_extreme": group.get("wick_boundary_extreme") if isinstance(group, dict) else liquidity.get("wick_boundary_extreme"),
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
        "stack_extreme": owner.get("stack_extreme"),
        "extreme_boundary": owner.get("extreme_boundary"),
        "wick_boundary_extreme": owner.get("wick_boundary_extreme"),
        "setup_direction": owner.get("setup_direction"),
        "side": owner.get("side"),
        "activated_at": owner.get("activated_at"),
        "candle_a": compact_candle(owner.get("candle_a")),
    }


def _normalized_invariant_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalized_invariant_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_normalized_invariant_value(item) for item in value]
    return value


def _invariant_values_differ(current: Any, previous: Any) -> bool:
    return _normalized_invariant_value(current) != _normalized_invariant_value(previous)


def _append_lifecycle_invariant_event(snapshot: dict[str, Any], event: dict[str, Any]) -> None:
    events = snapshot.get("lifecycle_invariant_events")
    if not isinstance(events, list):
        events = []
        snapshot["lifecycle_invariant_events"] = events
    events.append(event)


def _record_invariant_overwrite_attempt(
    snapshot: dict[str, Any],
    scope: str,
    field: str,
    previous: Any,
    current: Any,
) -> None:
    _append_lifecycle_invariant_event(
        snapshot,
        {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event": "lifecycle_anchor_overwrite_rejected",
            "symbol": snapshot.get("normalized_symbol") or snapshot.get("symbol"),
            "scope": scope,
            "field": field,
            "previous": _normalized_invariant_value(previous),
            "attempted": _normalized_invariant_value(current),
            "candle_time": snapshot.get("latest_bar_time"),
        },
    )


def _freeze_snapshot_field(
    snapshot: dict[str, Any],
    target: dict[str, Any],
    scope: str,
    field: str,
    previous: Any,
) -> None:
    if previous is None:
        return
    current = target.get(field)
    if current is not None and _invariant_values_differ(current, previous):
        _record_invariant_overwrite_attempt(snapshot, scope, field, previous, current)
    target[field] = copy.deepcopy(previous)


def _previous_step2_anchor(symbol_state: dict[str, Any]) -> dict[str, Any] | None:
    step2 = symbol_state.get("step_2_1a") if isinstance(symbol_state.get("step_2_1a"), dict) else None
    if not isinstance(step2, dict) or step2.get("step_2_activated") is not True:
        return None
    if step2.get("step2_invalidated_at"):
        return None
    step5_state = ((symbol_state.get("step5") or {}).get("state") or {}) if isinstance(((symbol_state.get("step5") or {}).get("state") or {}), dict) else {}
    step6 = symbol_state.get("step6") if isinstance(symbol_state.get("step6"), dict) else {}
    if step5_state.get("invalidated_at"):
        return None
    if decision_status(step6) == "CONFIRM":
        return None
    return step2


def _previous_step4_anchor(symbol_state: dict[str, Any]) -> dict[str, Any] | None:
    step4 = symbol_state.get("step4") if isinstance(symbol_state.get("step4"), dict) else None
    if not isinstance(step4, dict):
        return None
    state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    if not isinstance(state, dict):
        return None
    if state.get("leg1_state_locked") is not True and str(state.get("leg1_status") or "").upper() != "COMPLETE" and decision_status(step4) != "CONFIRM":
        return None
    return step4


def step2_confirmed_anchor_time(step2: dict[str, Any] | None) -> str | None:
    step2 = step2 if isinstance(step2, dict) else {}
    owner = step2.get("step2_locked_owner") if isinstance(step2.get("step2_locked_owner"), dict) else {}
    return (
        step2.get("step2_activated_at")
        or owner.get("activated_at")
        or candle_timestamp(step2.get("candle_a") if isinstance(step2.get("candle_a"), dict) else None)
    )


def step2_owner_name_from_state(step2: dict[str, Any] | None) -> str | None:
    step2 = step2 if isinstance(step2, dict) else {}
    owner = step2.get("step2_locked_owner") if isinstance(step2.get("step2_locked_owner"), dict) else {}
    active = owner.get("active_liquidity") if isinstance(owner.get("active_liquidity"), dict) else {}
    group = owner.get("active_liquidity_group") if isinstance(owner.get("active_liquidity_group"), dict) else active.get("group") if isinstance(active.get("group"), dict) else None
    explicit_display_name = owner.get("active_liquidity_display_name") or active.get("display_name") or (group.get("display_name") if isinstance(group, dict) else None)
    if isinstance(explicit_display_name, str) and explicit_display_name.strip():
        return public_active_liquidity_name(explicit_display_name)
    active_name = owner.get("active_liquidity_name") or active.get("name") or step2.get("active_level")
    return public_active_liquidity_name(active_name) if isinstance(active_name, str) and active_name.strip() else None


def step4_anchor_selected_pathway(step4: dict[str, Any] | None) -> str | None:
    step4 = step4 if isinstance(step4, dict) else {}
    state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    control = str(state.get("current_pathway_control") or "").lower().strip()
    if control in {"rejection", "continuation"}:
        return control
    mode = normalized_pathway_name(state.get("current_controlling_mode") or state.get("controlling_mode"))
    return selected_pathway_from_mode(mode)


def apply_confirmed_lifecycle_invariants(snapshot: dict[str, Any], previous_symbol_state: dict[str, Any] | None) -> dict[str, Any]:
    """Freeze confirmed Step 2 / Step 4 anchors so later candles cannot rewrite them."""
    previous_symbol_state = previous_symbol_state if isinstance(previous_symbol_state, dict) else {}
    current_step2 = snapshot.get("step_2_1a") if isinstance(snapshot.get("step_2_1a"), dict) else None
    previous_step2 = _previous_step2_anchor(previous_symbol_state)
    if isinstance(current_step2, dict) and current_step2.get("step_2_activated") is True:
        snapshot["frozen_step2_anchor_time"] = snapshot.get("frozen_step2_anchor_time") or step2_confirmed_anchor_time(current_step2)
        snapshot["frozen_step2_owner_name"] = snapshot.get("frozen_step2_owner_name") or step2_owner_name_from_state(current_step2)
        snapshot["frozen_step2_direction"] = snapshot.get("frozen_step2_direction") or (
            ((current_step2.get("step2_locked_owner") or {}).get("setup_direction") if isinstance(current_step2.get("step2_locked_owner"), dict) else None)
        )
    if (
        isinstance(current_step2, dict)
        and isinstance(previous_step2, dict)
        and snapshot.get("owner_rotation_released") is not True
    ):
        for field in ("step2_owner_seeded_at", "step2_activated_at"):
            _freeze_snapshot_field(snapshot, current_step2, "step2", field, previous_step2.get(field))
        if current_step2.get("step2_activation_candle_index") is not None and previous_step2.get("step2_activation_candle_index") is not None and _invariant_values_differ(current_step2.get("step2_activation_candle_index"), previous_step2.get("step2_activation_candle_index")):
            _record_invariant_overwrite_attempt(snapshot, "step2", "step2_activation_candle_index", previous_step2.get("step2_activation_candle_index"), current_step2.get("step2_activation_candle_index"))
            current_step2["step2_activation_candle_index"] = previous_step2.get("step2_activation_candle_index")
        previous_owner = previous_step2.get("step2_locked_owner") if isinstance(previous_step2.get("step2_locked_owner"), dict) else None
        if isinstance(previous_owner, dict):
            current_owner = current_step2.get("step2_locked_owner") if isinstance(current_step2.get("step2_locked_owner"), dict) else {}
            frozen_owner = dict(current_owner)
            for field in (
                "active_liquidity_name",
                "active_liquidity_price",
                "active_liquidity_display_name",
                "active_liquidity_group",
                "liquidity_group",
                "stack_components",
                "close_boundary",
                "stack_extreme",
                "extreme_boundary",
                "wick_boundary_extreme",
                "setup_direction",
                "side",
                "owner_seeded_at",
                "activated_at",
                "next_same_side_liquidity",
                "rejection_boundary",
                "step2_step4_50_line",
            ):
                previous_value = previous_owner.get(field)
                if previous_value is None:
                    continue
                current_value = current_owner.get(field)
                if current_value is not None and _invariant_values_differ(current_value, previous_value):
                    _record_invariant_overwrite_attempt(snapshot, "step2", f"step2_locked_owner.{field}", previous_value, current_value)
                frozen_owner[field] = copy.deepcopy(previous_value)
            previous_active = previous_owner.get("active_liquidity") if isinstance(previous_owner.get("active_liquidity"), dict) else None
            if isinstance(previous_active, dict):
                current_active = current_owner.get("active_liquidity") if isinstance(current_owner.get("active_liquidity"), dict) else {}
                if current_active and _invariant_values_differ(current_active, previous_active):
                    _record_invariant_overwrite_attempt(snapshot, "step2", "step2_locked_owner.active_liquidity", previous_active, current_active)
                frozen_owner["active_liquidity"] = copy.deepcopy(previous_active)
            current_step2["step2_locked_owner"] = frozen_owner
        current_step2["audit_step2_before_active"] = True
        current_step2["audit_step2_event"] = "already_active"
        snapshot["frozen_step2_anchor_time"] = step2_confirmed_anchor_time(previous_step2)
        snapshot["frozen_step2_owner_name"] = step2_owner_name_from_state(previous_step2)
        snapshot["frozen_step2_direction"] = (
            ((previous_step2.get("step2_locked_owner") or {}).get("setup_direction") if isinstance(previous_step2.get("step2_locked_owner"), dict) else None)
        )

    previous_step4 = _previous_step4_anchor(previous_symbol_state)
    current_step4 = snapshot.get("step4") if isinstance(snapshot.get("step4"), dict) else None
    if isinstance(current_step4, dict):
        current_step4_state = current_step4.get("state") if isinstance(current_step4.get("state"), dict) else {}
        if (
            current_step4_state.get("leg1_state_locked") is True
            or str(current_step4_state.get("leg1_status") or "").upper() == "COMPLETE"
            or decision_status(current_step4) == "CONFIRM"
        ):
            snapshot["frozen_step4_selected_pathway"] = snapshot.get("frozen_step4_selected_pathway") or step4_anchor_selected_pathway(current_step4)
            snapshot["frozen_step4_setup_direction"] = snapshot.get("frozen_step4_setup_direction") or current_step4_state.get("setup_direction")
    if isinstance(current_step4, dict) and isinstance(previous_step4, dict):
        previous_state = previous_step4.get("state") if isinstance(previous_step4.get("state"), dict) else {}
        current_state = current_step4.get("state") if isinstance(current_step4.get("state"), dict) else {}
        current_step4["state"] = current_state
        previous_lane_id = previous_state.get("lane_id")
        current_lane_id = current_state.get("lane_id")
        if current_lane_id and str(current_lane_id).startswith("continuation|") and previous_lane_id != current_lane_id:
            return snapshot
        if previous_lane_id and current_lane_id and previous_lane_id != current_lane_id:
            return snapshot
        if current_step4.get("status") is not None and previous_step4.get("status") is not None and _invariant_values_differ(current_step4.get("status"), previous_step4.get("status")):
            _record_invariant_overwrite_attempt(snapshot, "step4", "status", previous_step4.get("status"), current_step4.get("status"))
        current_step4["status"] = previous_step4.get("status")
        for field in (
            "leg1_completed_at",
            "step4_confirmed_at",
            "step4_window_count",
            "leg2_sweep_extreme",
            "step5_close_boundary",
            "candle_a",
            "candle_b",
            "setup_direction",
            "leg1_reference_price",
            "leg1_reference_candle_time",
            "active_liquidity",
            "step2_step4_50_line",
            "step4_step5_75_line",
            "current_pathway_control",
            "current_controlling_mode",
            "current_continuation_type",
        ):
            _freeze_snapshot_field(snapshot, current_state, "step4", field, previous_state.get(field))
        snapshot["frozen_step4_selected_pathway"] = step4_anchor_selected_pathway(previous_step4)
        snapshot["frozen_step4_setup_direction"] = previous_state.get("setup_direction")
    return snapshot


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
    if not same_liquidity_owner(previous_liquidity, selected_liquidity):
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
    if not authoritative_mutation_allowed():
        return
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


def latest_event_name(events: Any) -> str:
    if isinstance(events, list) and events:
        event = events[-1]
        if isinstance(event, dict) and event.get("event"):
            return str(event.get("event"))
    return ""


def audit_step_status(result: dict[str, Any] | None) -> str:
    if not isinstance(result, dict):
        return ""
    status = result.get("status")
    return str(status) if status is not None else ""


def audit_step_reason(result: dict[str, Any] | None) -> str:
    if not isinstance(result, dict):
        return ""
    if result.get("reason"):
        return str(result.get("reason"))
    state = result.get("state") if isinstance(result.get("state"), dict) else {}
    for key in (
        "state_transition_reason",
        "step25_block_reason",
        "step3_block_reason",
        "step4_block_reason",
        "step5_wait_reason",
        "step6_wait_reason",
    ):
        if state.get(key):
            return str(state.get(key))
    return ""


def classify_audit_data_source(snapshot: dict[str, Any]) -> str:
    """Classify the replay/audit source so operator output distinguishes live bars from fixtures or harness data."""
    explicit = str(snapshot.get("audit_source_type") or "").strip().upper()
    if explicit in {"RAW_LIVE_RITHMIC", "CHECKED_IN_FIXTURE", "SYNTHETIC_HARNESS", "HISTORICAL_REASONING_LOG"}:
        return explicit
    source = str(snapshot.get("source") or "").strip().lower()
    if "rithmic" in source:
        return "RAW_LIVE_RITHMIC"
    if "fixture" in source:
        return "CHECKED_IN_FIXTURE"
    if "reasoning" in source or "entry_decisions" in source:
        return "HISTORICAL_REASONING_LOG"
    if source in {"test", "synthetic_harness"} or "harness" in source or "synthetic" in source:
        return "SYNTHETIC_HARNESS"
    return "SYNTHETIC_HARNESS"


def format_public_candle_time_pt(value: Any) -> str | None:
    local_time = local_market_time(value)
    if local_time is None:
        return None
    return f"{local_time.strftime('%H:%M')} PT"


def format_public_time_seconds_pt(value: Any) -> str | None:
    """Return a local PT timestamp string with seconds for operator status panels."""
    local_time = local_market_time(value)
    if local_time is None:
        return None
    return f"{local_time.strftime('%H:%M:%S')} PT"


def projected_seeded_step4_status(snapshot: dict[str, Any], step2: dict[str, Any], step4: dict[str, Any]) -> dict[str, str] | None:
    """Project the Step 4 window state once Step 2 is confirmed and participation tracking has started."""
    if step2.get("step_2_activated") is not True:
        return None
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    if step4_state.get("leg1_window_active") is not True:
        return None
    if step4_state.get("leg1_window_candle_index") != 0:
        return None
    if step4_state.get("leg1_state_locked") is True:
        return None
    if str(step4.get("status") or "").upper() == "READY":
        return None
    candle_a = (
        step4_state.get("initial_candle_a")
        if isinstance(step4_state.get("initial_candle_a"), dict)
        else step4_state.get("candle_a")
        if isinstance(step4_state.get("candle_a"), dict)
        else step2.get("candle_a")
        if isinstance(step2.get("candle_a"), dict)
        else build_snapshot_candle(snapshot)
    )
    candle_a_time = (
        candle_timestamp(candle_a)
        or step4_state.get("leg1_window_started_at")
        or step2.get("step2_activated_at")
        or snapshot.get("latest_bar_time")
    )
    public_time = format_public_candle_time_pt(candle_a_time) or "current"
    return {
        "status": "WAITING_FOR_CANDLE_B",
        "reason": f"Step 4 seeded: the participation window is anchored at the {public_time} Step 2 confirmation candle. Waiting for a qualifying participation candle.",
    }


def seeded_step4_reason_from_anchor(anchor_time: Any) -> str | None:
    """Return the seeded Step 4 public reason text from a frozen anchor time."""
    public_time = format_public_candle_time_pt(anchor_time)
    if not public_time:
        return None
    return (
        "Step 4 seeded: the participation window is anchored at the "
        f"{public_time} Step 2 confirmation candle. Waiting for a qualifying participation candle."
    )


def is_seeded_step4_anchor_reason(reason: Any) -> bool:
    """Return True when the public Step 4 reason is the seeded anchor message."""
    text = str(reason or "").strip()
    return (
        text.startswith("Step 4 seeded: the participation window is anchored at the ")
        and text.endswith("Step 2 confirmation candle. Waiting for a qualifying participation candle.")
    )


def audit_activation_timestamp(step_result: dict[str, Any] | None, *fallbacks: Any) -> Any:
    state = step_result.get("state") if isinstance(step_result, dict) and isinstance(step_result.get("state"), dict) else {}
    for value in (*fallbacks, state.get("activated_at")):
        if value:
            return value
    return None


def audit_active_liquidity_components(group: dict[str, Any] | None, owner: dict[str, Any] | None) -> list[Any]:
    components = owner.get("stack_components") if isinstance(owner, dict) else None
    if components is None and isinstance(group, dict):
        components = group.get("components")
    return components if isinstance(components, list) else []


def audit_boundary_value(
    boundary_name: str,
    group: dict[str, Any] | None,
    owner: dict[str, Any] | None,
    active_liquidity: dict[str, Any] | None,
    step2: dict[str, Any],
) -> Any:
    if isinstance(owner, dict) and owner.get(boundary_name) is not None:
        return owner.get(boundary_name)
    if isinstance(group, dict) and group.get(boundary_name) is not None:
        return group.get(boundary_name)
    if boundary_name in {"close_boundary", "extreme_boundary"}:
        if isinstance(active_liquidity, dict) and active_liquidity.get("price") is not None:
            return active_liquidity.get("price")
        return step2.get("level_price")
    return None


def actionable_boundary_from_group(
    group: dict[str, Any] | None,
    fallback_extreme_boundary: Any = None,
) -> float | None:
    """Return the active actionable boundary, preferring wick boundary when present."""
    wick_boundary_extreme = optional_float((group or {}).get("wick_boundary_extreme"))
    if wick_boundary_extreme is not None:
        return wick_boundary_extreme
    extreme_boundary = optional_float((group or {}).get("extreme_boundary"))
    if extreme_boundary is not None:
        return extreme_boundary
    return optional_float(fallback_extreme_boundary)


def group_with_wick_boundary_candidate(
    group: dict[str, Any] | None,
    candidate_price: Any,
) -> dict[str, Any] | None:
    """Return a copy of the stack with a monotonic wick boundary stored separately from the original extreme."""
    if not isinstance(group, dict):
        return group
    side = str(group.get("side") or "")
    original_extreme = optional_float(group.get("extreme_boundary"))
    wick_boundary_extreme = optional_float(group.get("wick_boundary_extreme"))
    candidate = optional_float(candidate_price)
    if side not in {"upper", "lower"} or original_extreme is None or candidate is None:
        return group
    if not _more_extreme_price(candidate, original_extreme, side):
        return group
    if not _more_extreme_price(candidate, wick_boundary_extreme, side):
        return group

    updated = dict(group)
    updated["wick_boundary_extreme"] = candidate
    if side == "upper":
        updated["high"] = max(optional_float(updated.get("high")) or candidate, candidate)
    else:
        updated["low"] = min(optional_float(updated.get("low")) or candidate, candidate)
    return updated


def stack_group_with_pre_open_wick_boundary(
    group: dict[str, Any] | None,
    observed_extreme: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Seed the persisted wick boundary from a matching pre-open observed extreme."""
    if not isinstance(group, dict) or not isinstance(observed_extreme, dict):
        return group
    side = str(group.get("side") or "")
    if side not in {"upper", "lower"} or str(observed_extreme.get("side") or "") != side:
        return group
    observed_group = str(observed_extreme.get("stack_group") or "")
    if observed_group and observed_group != str(group.get("name") or ""):
        return group
    return group_with_wick_boundary_candidate(group, observed_extreme.get("price"))


def stack_group_with_pending_probe_boundary(
    group: dict[str, Any] | None,
    step_state: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Use an unresolved Step 2 probe as the actionable wick boundary for the active group."""
    if not isinstance(group, dict) or not isinstance(step_state, dict):
        return group
    if step_state.get("step_2_activated") is True:
        return group
    probe = step_state.get("pre_activation_probe_boundary")
    if not isinstance(probe, dict) or probe.get("active") is not True:
        return group
    side = str(group.get("side") or "")
    if side not in {"upper", "lower"} or str(probe.get("side") or "") != side:
        return group
    source_level = str(probe.get("source_level") or step_state.get("active_level") or "")
    components = [str(component) for component in (group.get("components") or [])]
    if source_level and components and source_level not in components:
        return group
    boundary_price = optional_float(probe.get("boundary_price"))
    if boundary_price is None:
        return group

    updated = dict(group)
    current_boundary = optional_float(updated.get("wick_boundary_extreme"))
    if not _more_extreme_price(boundary_price, current_boundary, side):
        return group

    updated["wick_boundary_extreme"] = boundary_price
    if side == "upper":
        updated["high"] = max(optional_float(updated.get("high")) or boundary_price, boundary_price)
    else:
        updated["low"] = min(optional_float(updated.get("low")) or boundary_price, boundary_price)
    return updated


def merge_frozen_group_with_active_boundary(
    frozen_group: dict[str, Any] | None,
    active_group: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Keep frozen ownership/price metadata while exposing the active group's boundary fields."""
    if not isinstance(frozen_group, dict):
        return active_group if isinstance(active_group, dict) else frozen_group
    if not isinstance(active_group, dict):
        return frozen_group
    if frozen_group.get("name") != active_group.get("name") or frozen_group.get("side") != active_group.get("side"):
        return frozen_group

    merged = dict(frozen_group)
    for key in ("wick_boundary_extreme", "high", "low", "extreme_component", "close_component"):
        if active_group.get(key) is not None:
            merged[key] = active_group.get(key)
    return merged


def merge_monotonic_stack_wick_boundary(
    current_group: dict[str, Any] | None,
    persisted_group: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Preserve stack metadata and the farthest wick boundary while the owner remains active."""
    if not isinstance(current_group, dict):
        return persisted_group if isinstance(persisted_group, dict) else current_group
    if not isinstance(persisted_group, dict):
        return current_group
    if current_group.get("name") != persisted_group.get("name") or current_group.get("side") != persisted_group.get("side"):
        return current_group
    if optional_float(current_group.get("close_boundary")) != optional_float(persisted_group.get("close_boundary")):
        return current_group
    if optional_float(current_group.get("extreme_boundary")) != optional_float(persisted_group.get("extreme_boundary")):
        return current_group
    current_components = list(current_group.get("components") or [])
    persisted_components = list(persisted_group.get("components") or [])
    if current_components != persisted_components:
        return current_group

    merged = dict(current_group)
    if merged.get("stack_extreme") is None and persisted_group.get("stack_extreme") is not None:
        merged["stack_extreme"] = persisted_group.get("stack_extreme")
    side = str(merged.get("side") or "")
    current_wick = optional_float(merged.get("wick_boundary_extreme"))
    persisted_wick = optional_float(persisted_group.get("wick_boundary_extreme"))
    if side in {"upper", "lower"} and persisted_wick is not None and _more_extreme_price(persisted_wick, current_wick, side):
        merged["wick_boundary_extreme"] = persisted_wick
    return merged


def build_entry_agent_audit_row(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Build one per-candle audit row from already evaluated Entry Agent state."""
    candle = build_snapshot_candle(snapshot)
    if candle is None or not candle_close_confirmed(snapshot):
        return None

    step2 = snapshot.get("step_2_1a") if isinstance(snapshot.get("step_2_1a"), dict) else {}
    step25 = snapshot.get("step25") if isinstance(snapshot.get("step25"), dict) else {}
    step3 = snapshot.get("step3") if isinstance(snapshot.get("step3"), dict) else {}
    step4 = snapshot.get("step4") if isinstance(snapshot.get("step4"), dict) else {}
    step5 = snapshot.get("step5") if isinstance(snapshot.get("step5"), dict) else {}
    step6 = snapshot.get("step6") if isinstance(snapshot.get("step6"), dict) else {}
    step25_state = step25.get("state") if isinstance(step25.get("state"), dict) else {}
    step3_state = step3.get("state") if isinstance(step3.get("state"), dict) else {}
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    step5_state = step5.get("state") if isinstance(step5.get("state"), dict) else {}
    step6_state = step6.get("state") if isinstance(step6.get("state"), dict) else {}
    owner = step2.get("step2_locked_owner") if isinstance(step2.get("step2_locked_owner"), dict) else {}
    owner_active = owner.get("active_liquidity") if isinstance(owner.get("active_liquidity"), dict) else {}
    last_interacted = step2.get("last_interacted_liquidity") if isinstance(step2.get("last_interacted_liquidity"), dict) else {}
    observation_only = before_entry_authorization(snapshot)
    observation_reason = "06:15-06:29 PT is observation-only. Liquidity and wick-reset/pre-open extremes may be tracked, but Step 2+ activation is disabled until 06:30."
    observation_liquidity = public_observation_liquidity_from_snapshot(snapshot) if observation_only else None
    group = (
        observation_liquidity.get("group")
        if isinstance(observation_liquidity, dict) and isinstance(observation_liquidity.get("group"), dict)
        else active_liquidity_group_from_snapshot(snapshot)
    )
    persisted_group = active_liquidity_group_from_snapshot(snapshot)
    group = merge_monotonic_stack_wick_boundary(group, persisted_group)
    group = stack_group_with_pre_open_wick_boundary(group, snapshot.get("pre_open_observed_extreme") if observation_only else None)
    active_name, _active_price = (
        (observation_liquidity.get("name"), observation_liquidity.get("price"))
        if isinstance(observation_liquidity, dict)
        else active_liquidity_from_snapshot(snapshot)
    )
    active_liquidity = owner_active if owner_active else last_interacted
    active_display_name = (
        owner_active.get("display_name")
        or owner.get("active_liquidity_display_name")
        or last_interacted.get("display_name")
        or (group or {}).get("display_name")
        or active_name
        or ""
    )
    active_side = (
        owner_active.get("side")
        or owner.get("side")
        or last_interacted.get("side")
        or (group or {}).get("side")
        or side_for_level(str(active_name or step2.get("active_level") or ""))
        or ""
    )
    observed_extreme = snapshot.get("pre_open_observed_extreme") if isinstance(snapshot.get("pre_open_observed_extreme"), dict) else {}
    blocked_preopen_status = "BLOCKED_PREOPEN_OBSERVATION" if observation_only else None
    blocked_preopen_reason = observation_reason if observation_only else None
    seeded_step4_projection = projected_seeded_step4_status(snapshot, step2, step4)
    liquidity = snapshot.get("liquidity") if isinstance(snapshot.get("liquidity"), dict) else {}
    audit_setup_direction = (
        owner.get("setup_direction")
        or step25_state.get("setup_direction")
        or step4_state.get("setup_direction")
        or step5_state.get("setup_direction")
        or step6_state.get("setup_direction")
        or None
    )
    participation_lines = step4_participation_line_payload(
        snapshot,
        step2,
        step4_state,
        rejection_active=step2.get("step_2_activated") is True,
        selected_pathway=owner.get("pathway") or ("rejection" if step2.get("step_2_activated") else None),
        setup_direction=audit_setup_direction,
        leg1_published=False,
        invalidated=False,
    )
    previous_symbol_state = symbol_scoped_persisted_state(load_entry_state(), root_symbol(str(snapshot.get("normalized_symbol") or snapshot.get("symbol") or "")))
    rejection_lane = snapshot.get("rejection_lane") if isinstance(snapshot.get("rejection_lane"), dict) else None
    continuation_lane = snapshot.get("continuation_lane") if isinstance(snapshot.get("continuation_lane"), dict) else None
    if not isinstance(rejection_lane, dict) or not isinstance(continuation_lane, dict):
        rejection_lane, continuation_lane = snapshot_lane_statuses(snapshot, previous_symbol_state)
    audit_invalidation_reason = first_invalidation_reason(step4, step5, step6)
    audit_step2_status = public_step_status(
        blocked_preopen_status or ("CONFIRMED" if step2.get("step_2_activated") is True else "WAIT"),
        step_name="Step 2",
    )
    audit_step4_status = public_step_status(
        blocked_preopen_status or ((seeded_step4_projection or {}).get("status")) or audit_step_status(step4),
        step_name="Step 4",
    )
    audit_step2_confirmed_at, audit_step2_anchor_status, audit_step2_anchor_reason = step2_anchor_publication_state(snapshot, step2, audit_step2_status)
    audit_step4_invalidated_at = step4_state.get("invalidated_at") or (
        step5_state.get("invalidated_at")
        if str((step5_state.get("invalidation_source_step") or "")).strip() == "Step 4"
        else None
    )
    return {
        "received_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "data_source_type": classify_audit_data_source(snapshot),
        "symbol": snapshot.get("symbol") or snapshot.get("normalized_symbol"),
        "normalized_symbol": snapshot.get("normalized_symbol"),
        "requested_symbol": snapshot.get("requested_symbol"),
        "candle_time": candle.get("timestamp"),
        "candle_index": step2.get("candle_index"),
        "step2_candle_count": step2_candle_count(snapshot, step2),
        "open": candle.get("open"),
        "high": candle.get("high"),
        "low": candle.get("low"),
        "close": candle.get("close"),
        "active_liquidity_name": active_display_name or owner_active.get("name") or owner.get("active_liquidity_name") or active_name or step2.get("active_level") or "",
        "active_liquidity_display_name": active_display_name,
        "active_liquidity_side": active_side,
        "active_liquidity_components": audit_active_liquidity_components(group, owner),
        "close_boundary": audit_boundary_value("close_boundary", group, owner, active_liquidity, step2),
        "extreme_boundary": audit_boundary_value("extreme_boundary", group, owner, active_liquidity, step2),
        "wick_boundary_extreme": audit_boundary_value("wick_boundary_extreme", group, owner, active_liquidity, step2),
        "frozen_tv_level": _active_price,
        "pre_open_observed_extreme": observed_extreme.get("price"),
        "control_state": "OBSERVATION_ONLY" if observation_only else "",
        "conflict_state": "NONE_PREOPEN" if observation_only else "",
        "step2_status": audit_step2_status,
        "nearest_level_above": liquidity.get("nearest_level_above"),
        "nearest_level_below": liquidity.get("nearest_level_below"),
        "step2_before_active": bool(step2.get("audit_step2_before_active")),
        "step2_after_active": bool(step2.get("step_2_activated")),
        "step2_owner_seeded_at": step2.get("step2_owner_seeded_at") or owner.get("owner_seeded_at") or owner.get("activated_at") or step2.get("step2_activated_at") or step2.get("activated_at"),
        "step2_event": blocked_preopen_status or str(step2.get("audit_step2_event") or latest_event_name(step2.get("events")) or ""),
        "step2_reason": blocked_preopen_reason or str(step2.get("state_transition_reason") or step2.get("reason") or ""),
        "step2_pathway": owner.get("pathway") or ("rejection" if step2.get("step_2_activated") else ""),
        "step2_owner_name": step2_owner_name(snapshot, step2) or "",
        "step2_direction": audit_setup_direction or "",
        "step2_setup_direction": (
            audit_setup_direction
            or ""
        ),
        "step2_activated_at": step2.get("step2_activated_at") or owner.get("activated_at") or step2.get("activated_at"),
        "step2_confirmed_at": audit_step2_confirmed_at,
        "step2_anchor_status": audit_step2_anchor_status,
        "step2_anchor_reason": audit_step2_anchor_reason,
        "step2_invalidated_at": step2.get("step2_invalidated_at"),
        "step25_status": blocked_preopen_status or audit_step_status(step25),
        "step25_reason": blocked_preopen_reason or audit_step_reason(step25),
        "step25_activated_at": audit_activation_timestamp(step25, step25_state.get("step25_activated_at")),
        "step3_status": blocked_preopen_status or audit_step_status(step3),
        "step3_reason": blocked_preopen_reason or audit_step_reason(step3),
        "step3_activated_at": audit_activation_timestamp(step3, step3_state.get("step3_activated_at")),
        "step4_status": audit_step4_status,
        "step4_event": blocked_preopen_status or str(latest_event_name(step4.get("events")) or ""),
        "step4_reason": blocked_preopen_reason or ((seeded_step4_projection or {}).get("reason")) or audit_step_reason(step4),
        "step4_activated_at": audit_activation_timestamp(step4, step4_state.get("step4_activated_at")),
        "step4_confirmed_at": step4_state.get("step4_confirmed_at") or step4_state.get("leg1_completed_at"),
        "step4_window_count": step4_state.get("step4_window_count") or step4_state.get("participation_candidate_count"),
        "leg2_sweep_extreme": step4_state.get("leg2_sweep_extreme"),
        "step5_close_boundary": step4_state.get("step5_close_boundary"),
        "step4_candle_a_time": candle_timestamp(step4_state.get("candle_a") if isinstance(step4_state.get("candle_a"), dict) else None) or candle_timestamp(step4_state.get("initial_candle_a") if isinstance(step4_state.get("initial_candle_a"), dict) else None),
        "step4_candle_b_time": candle_timestamp(step4_state.get("candle_b") if isinstance(step4_state.get("candle_b"), dict) else None),
        "step4_rejection_completed_at": step4_state.get("step4_confirmed_at") or step4_state.get("leg1_completed_at"),
        "step4_invalidated_at": audit_step4_invalidated_at,
        "step4_owner_name": step4_owner_name(snapshot, step4_state) or "",
        "step4_direction": audit_setup_direction or "",
        "step2_step4_50_line": participation_lines["line_50"],
        "step4_step5_75_line": participation_lines["line_75"],
        "step4_participation_50_line": participation_lines["line_50"],
        "step4_participation_75_line": participation_lines["line_75"],
        "invalidation_reason": audit_invalidation_reason,
        "rejection_lane": public_lane_projection(rejection_lane),
        "continuation_lane": public_lane_projection(continuation_lane),
        "step5_status": blocked_preopen_status or audit_step_status(step5),
        "step5_reason": blocked_preopen_reason or audit_step_reason(step5),
        "step5_activated_at": audit_activation_timestamp(step5, step5_state.get("step5_activated_at")),
        "step6_status": blocked_preopen_status or audit_step_status(step6),
        "step6_reason": blocked_preopen_reason or audit_step_reason(step6),
        "step6_activated_at": audit_activation_timestamp(step6, step6_state.get("step6_activated_at")),
    }


def last_audit_candle_time(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return None
    if not lines:
        return None
    try:
        row = json.loads(lines[-1])
    except json.JSONDecodeError:
        return None
    return str(row.get("candle_time")) if row.get("candle_time") else None


def repair_same_candle_audit_row(path: Path, row: dict[str, Any]) -> bool:
    """Backfill missing lifecycle fields on an existing same-candle audit row."""
    require_authoritative_mutation("repair_same_candle_audit_row")
    if not path.exists():
        return False
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return False
    if not lines:
        return False
    try:
        existing = json.loads(lines[-1])
    except json.JSONDecodeError:
        return False
    if str(existing.get("candle_time") or "") != str(row.get("candle_time") or ""):
        return False

    updated = dict(existing)
    changed = False
    for field in ("step2_candle_count", "step2_step4_50_line", "step4_step5_75_line", "invalidation_reason", "rejection_lane", "continuation_lane"):
        if updated.get(field) is None and row.get(field) is not None:
            updated[field] = row.get(field)
            changed = True
    if not changed:
        return False

    lines[-1] = json.dumps(updated, separators=(",", ":"), default=str)
    try:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        return False
    return True


def append_entry_agent_audit_row(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Append one JSONL audit row for a completed candle without overwriting history."""
    require_authoritative_mutation("append_entry_agent_audit_row")
    row = build_entry_agent_audit_row(snapshot)
    if row is None:
        return None
    candle_date = local_session_date(row.get("candle_time")) or datetime.now(LOCAL_MARKET_TIMEZONE).date().isoformat()
    symbol = root_symbol(str(row.get("normalized_symbol") or row.get("symbol") or "UNKNOWN")).upper()
    audit_dir = ENTRY_AGENT_AUDIT_DIR / candle_date
    try:
        audit_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return row
    audit_path = audit_dir / f"{symbol}_step_audit.jsonl"
    if last_audit_candle_time(audit_path) == str(row.get("candle_time")):
        repair_same_candle_audit_row(audit_path, row)
        return None
    try:
        with audit_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
    except OSError:
        return row
    return row


def load_tv_context(symbol: str | None = None) -> dict[str, Any] | None:
    """Load optional TradingView context for the requested root only."""
    def locked_view(context: dict[str, Any]) -> dict[str, Any]:
        locked = context.get("locked_liquidity_context")
        if not isinstance(locked, dict) or not isinstance(locked.get("levels"), dict):
            return context
        effective = dict(context)
        effective["levels"] = copy.deepcopy(locked["levels"])
        liquidity_map = locked.get("liquidity_map")
        if isinstance(liquidity_map, dict):
            effective["liquidity_map"] = copy.deepcopy(liquidity_map)
        effective["liquidity_context_locked"] = True
        effective["liquidity_context_locked_at"] = (
            context.get("liquidity_context_locked_at")
            or locked.get("locked_at")
        )
        return effective

    requested_root = root_symbol(symbol) if symbol else None
    if requested_root:
        by_symbol = _read_json(TV_CONTEXT_BY_SYMBOL_PATH).get("symbols")
        if isinstance(by_symbol, dict):
            context = by_symbol.get(requested_root)
            if isinstance(context, dict):
                return locked_view(context)
            for stored_symbol, stored_context in by_symbol.items():
                if root_symbol(str(stored_symbol)) == requested_root and isinstance(stored_context, dict):
                    return locked_view(stored_context)
                if isinstance(stored_context, dict) and root_symbol(str(stored_context.get("symbol") or "")) == requested_root:
                    return locked_view(stored_context)

    context = _read_json(TV_CONTEXT_PATH)
    if not context:
        return None
    context_symbol = context.get("normalized_symbol") or context.get("symbol")
    if requested_root and root_symbol(str(context_symbol or "")) != requested_root:
        return None
    return locked_view(context)


def load_raw_tv_context(symbol: str | None = None) -> dict[str, Any] | None:
    """Load the latest stored TradingView context without replacing levels with the frozen lock."""
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


def side_for_level(
    level_name: str | None,
    level_price: Any = None,
    session_lock_price: Any = None,
) -> str | None:
    """Return frozen level ownership; YH/YL require price and lock authority."""
    return side_for_level_price(level_name, level_price, session_lock_price)


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
    session_reference_price = stack_reference_price_from_context(tv_context)

    def level_interacted(level_name: str, level_price: float) -> bool:
        close = optional_float(ohlc.get("close"))
        high = optional_float(ohlc.get("high"))
        low = optional_float(ohlc.get("low"))
        side = side_for_level(level_name, level_price, session_reference_price)
        if side == "upper":
            return (close is not None and close >= level_price) or (high is not None and high >= level_price + tick_size)
        if side == "lower":
            return (close is not None and close <= level_price) or (low is not None and low <= level_price - tick_size)
        return False

    def stack_interacted(side: str | None, close_boundary: float) -> bool:
        close = optional_float(ohlc.get("close"))
        high = optional_float(ohlc.get("high"))
        low = optional_float(ohlc.get("low"))
        if side == "upper":
            return (close is not None and close >= close_boundary) or (high is not None and high >= close_boundary)
        if side == "lower":
            return (close is not None and close <= close_boundary) or (low is not None and low <= close_boundary)
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
        if len(components) == 1:
            return str(components[0]["name"])
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
                "side": side_for_level(name, price, session_reference_price),
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
            if not stack_interacted(side, close_boundary):
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
                "stack_extreme": extreme_boundary,
                "extreme_boundary": extreme_boundary,
                "wick_boundary_extreme": None,
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
    selected = min(candidates, key=lambda item: (item["priority"], item["distance"], item["name"]))
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
    previous_price = optional_float(persisted_liquidity.get("price"))
    session_reference_price = stack_reference_price_from_context(tv_context)
    previous_side = (
        str(persisted_liquidity.get("side") or "").strip().lower()
        or side_for_level(previous_name, previous_price, session_reference_price)
    )
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
        price = optional_float(details.get("price"))
        if price is None:
            continue
        if side_for_level(name, price, session_reference_price) != previous_side:
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


def tv_context_session_date(tv_context: dict[str, Any] | None) -> str | None:
    """Return the session date carried by the latest or locked TV context."""
    if not isinstance(tv_context, dict):
        return None
    for key in ("last_tv_context_session_date", "session_date"):
        value = str(tv_context.get(key) or "").strip()
        if value:
            return value
    locked_context = tv_context.get("locked_liquidity_context")
    if isinstance(locked_context, dict):
        value = str(locked_context.get("session_date") or "").strip()
        if value:
            return value
    return None


def snapshot_session_date(snapshot: dict[str, Any]) -> str | None:
    """Return the effective session date for lifecycle authority."""
    effective_session_date, _ = resolve_snapshot_session_authority(snapshot)
    return effective_session_date


def resolve_snapshot_session_authority(snapshot: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (effective_session_date, authority_source)."""
    rithmic_session_date = local_session_date(snapshot.get("latest_bar_time"))
    raw_tv_session_date = tv_context_session_date(snapshot.get("raw_tv_context") if isinstance(snapshot.get("raw_tv_context"), dict) else None)
    live_tv_session_date = tv_context_session_date(snapshot.get("live_tv_context") if isinstance(snapshot.get("live_tv_context"), dict) else None)
    tv_session_date = raw_tv_session_date or live_tv_session_date
    if rithmic_session_date and tv_session_date:
        if tv_session_date > rithmic_session_date:
            return tv_session_date, "tradingview"
        return rithmic_session_date, "rithmic"
    if rithmic_session_date:
        return rithmic_session_date, "rithmic"
    return tv_session_date, "tradingview" if tv_session_date else None


def at_or_after_local_time(value: Any, hour: int, minute: int) -> bool:
    local_time = local_market_time(value)
    if not local_time:
        return False
    boundary = local_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return local_time >= boundary


def authorization_reference_time(snapshot: dict[str, Any]) -> Any:
    """Return the candle time currently being evaluated for entry authorization."""
    latest_bar_time = snapshot.get("latest_bar_time")
    latest_dt = parse_candle_time(latest_bar_time)
    if not latest_dt:
        return latest_bar_time
    if snapshot.get("ohlc_is_closed") is False:
        return (latest_dt + timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    return latest_bar_time


def before_entry_authorization(snapshot: dict[str, Any]) -> bool:
    """Return True during the 6:15-6:30 observation-only window."""
    reference_time = authorization_reference_time(snapshot)
    return at_or_after_local_time(reference_time, OBSERVATION_RESET_HOUR, OBSERVATION_RESET_MINUTE) and not at_or_after_local_time(
        reference_time,
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
    if not tv_context["levels"]:
        return False
    liquidity_map = tv_context.get("liquidity_map")
    explicit_stacks = liquidity_map.get("stacks") if isinstance(liquidity_map, dict) and "stacks" in liquidity_map else None
    return validate_liquidity_stack_structure(
        tv_context["levels"],
        explicit_stacks,
        stack_threshold=stack_threshold_from_context(tv_context),
        session_reference_price=stack_reference_price_from_context(tv_context),
    ) is None


def has_active_tv_levels(tv_context: dict[str, Any] | None) -> bool:
    """Return True when TradingView exposes any ACTIVE level in the given context."""
    if not isinstance(tv_context, dict) or not isinstance(tv_context.get("levels"), dict):
        return False
    return any(
        str(details.get("status") or "").upper() == "ACTIVE"
        for details in tv_context["levels"].values()
        if isinstance(details, dict)
    )


def tv_context_actionable_for_session(tv_context: dict[str, Any] | None, session_date: str | None) -> bool:
    """Return True when the TradingView context matches the effective session."""
    if not session_date:
        return False
    context_date = tv_context_session_date(tv_context)
    return valid_locked_tv_context(tv_context) and context_date == session_date


def active_levels_payload_from_tv_context(tv_context: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Return the active TV levels used to freeze the 06:15 session context."""
    if not isinstance(tv_context, dict) or not isinstance(tv_context.get("levels"), dict):
        return {}
    payload: dict[str, dict[str, Any]] = {}
    for name, details in tv_context["levels"].items():
        if name not in ACTIVE_LIQUIDITY_PRIORITY or not isinstance(details, dict):
            continue
        if str(details.get("status") or "").upper() != "ACTIVE":
            continue
        price = optional_float(details.get("price"))
        if price is None:
            continue
        stack_groups = liquidity_level_stack_groups(details)
        payload[name] = {
            "price": price,
            "status": "ACTIVE",
            # Keep the first canonical membership as the deterministic legacy
            # scalar while stack_groups remains the complete authority.
            "stack_group": stack_groups[0] if stack_groups else "NONE",
            "stack_groups": stack_groups,
            "stack_display": " + ".join(stack_groups) if stack_groups else "NONE",
        }
    return payload


def liquidity_level_stack_groups(details: dict[str, Any] | None) -> list[str]:
    """Return canonical owner memberships while preserving legacy single-owner rows."""
    if not isinstance(details, dict):
        return []
    raw_groups = details.get("stack_groups")
    candidates = raw_groups if isinstance(raw_groups, list) else [details.get("stack_group")]
    groups: list[str] = []
    for candidate in candidates:
        label = str(candidate or "").strip().upper()
        if not label or label == "NONE" or label in groups:
            continue
        groups.append(label)
    return groups


def validate_session_liquidity_lock(
    levels_payload: dict[str, dict[str, Any]],
    groups: list[dict[str, Any]],
    *,
    stack_threshold: Any = None,
    session_reference_price: Any = None,
) -> str | None:
    """Return a stable error when frozen stack authority is structurally invalid."""
    explicit_stacks = [group for group in groups if group.get("stack_group")]
    error = validate_liquidity_stack_structure(
        levels_payload,
        explicit_stacks,
        stack_threshold=stack_threshold,
        session_reference_price=session_reference_price,
    )
    return format_stack_validation_error(error, prefix="SESSION_LOCK_")


def session_lock_reference_authority_error(tv_context: dict[str, Any] | None) -> str | None:
    """Require the separately frozen market reference for an authoritative session lock."""
    if stack_reference_price_from_context(tv_context) is None:
        return (
            "SESSION_LOCK_REFERENCE_PRICE_MISSING "
            "frozen TradingView context has no numeric session_lock_price"
        )
    return None


def build_session_locked_tv_context(tv_context: dict[str, Any] | None) -> dict[str, Any] | None:
    """Freeze the 06:15 active liquidity table for the rest of the session."""
    if not valid_locked_tv_context(tv_context):
        return None
    levels_payload = active_levels_payload_from_tv_context(tv_context)
    locked_context = {
        "symbol": tv_context.get("symbol"),
        "normalized_symbol": tv_context.get("normalized_symbol"),
        "source": tv_context.get("source"),
        "version": tv_context.get("version"),
        "timestamp": tv_context.get("timestamp"),
        "context_mode": tv_context.get("context_mode"),
        "received_at": tv_context.get("received_at"),
        "session_date": tv_context.get("session_date"),
        "time_zone": tv_context.get("time_zone"),
        "locked": True,
        "context_locked": True,
        "locked_for_day": True,
        "liquidity_context_locked": True,
        "liquidity_context_locked_at": tv_context.get("liquidity_context_locked_at") or tv_context.get("received_at"),
        "liquidity_context_source": tv_context.get("liquidity_context_source") or tv_context.get("source"),
        "session_lock_price": stack_reference_price_from_context(tv_context),
        "stack_threshold": stack_threshold_from_context(tv_context),
        "atr_1m_14": tv_context.get("atr_1m_14"),
        "current_1m_atr": tv_context.get("current_1m_atr"),
        "atr_1m": tv_context.get("atr_1m"),
        "daily_atr14": tv_context.get("daily_atr14"),
        "daily_atr_14": tv_context.get("daily_atr_14"),
        "daily_atr": tv_context.get("daily_atr"),
        "atr_daily_14": tv_context.get("atr_daily_14"),
        "atr_daily": tv_context.get("atr_daily"),
        "lock_reconstruction": copy.deepcopy(tv_context.get("lock_reconstruction")) if isinstance(tv_context.get("lock_reconstruction"), dict) else None,
        "levels": levels_payload,
    }
    groups = active_liquidity_groups_from_context(locked_context)
    error = validate_session_liquidity_lock(
        levels_payload,
        groups,
        stack_threshold=locked_context.get("stack_threshold"),
        session_reference_price=locked_context.get("session_lock_price"),
    )
    if error is None:
        error = session_lock_reference_authority_error(locked_context)
    return {
        "locked": error is None,
        "disabled": error is not None,
        "error": error,
        "active_levels": levels_payload,
        "active_groups": groups,
        "tv_context": locked_context,
    }


def locked_session_liquidity_context(persisted_state: dict[str, Any], symbol: str | None) -> dict[str, Any] | None:
    """Return frozen authority or a nonmutating disabled projection when invalid."""
    symbol_state = symbol_scoped_persisted_state(persisted_state, symbol)
    context = symbol_state.get("session_liquidity_context")
    if not isinstance(context, dict):
        return None
    tv_context = context.get("tv_context")
    levels_payload = context.get("active_levels")
    groups = context.get("active_groups")
    error = None
    if not valid_locked_tv_context(tv_context if isinstance(tv_context, dict) else None):
        error = "SESSION_LOCK_STACK_AUTHORITY_INVALID frozen TradingView context failed structural validation"
    elif isinstance(levels_payload, dict) and isinstance(groups, list):
        error = validate_session_liquidity_lock(
            levels_payload,
            groups,
            stack_threshold=stack_threshold_from_context(tv_context),
            session_reference_price=stack_reference_price_from_context(tv_context),
        )
        if error is None:
            error = session_lock_reference_authority_error(tv_context)
    if error is None:
        return context
    disabled = copy.deepcopy(context)
    disabled["locked"] = False
    disabled["disabled"] = True
    disabled["error"] = error
    return disabled


def effective_session_tv_context(
    persisted_state: dict[str, Any],
    symbol: str | None,
    live_tv_context: dict[str, Any] | None,
    effective_session_date: str | None = None,
) -> dict[str, Any] | None:
    """Use the frozen 06:15 liquidity context once it exists and is valid."""
    if effective_session_date is None:
        effective_session_date = local_session_date(
            (persisted_state.get("latest_bar_time") or (live_tv_context or {}).get("latest_bar_time"))
        )
    locked_context = locked_session_liquidity_context(persisted_state, symbol)
    if (
        isinstance(locked_context, dict)
        and locked_context.get("disabled") is not True
        and tv_context_actionable_for_session(locked_context.get("tv_context"), effective_session_date)
    ):
        frozen = locked_context.get("tv_context")
        if isinstance(frozen, dict):
            return frozen
    if effective_session_date is None and isinstance(live_tv_context, dict) and valid_locked_tv_context(live_tv_context):
        return live_tv_context
    return None


def projected_frozen_stack_groups(
    levels_payload: list[dict[str, Any]],
    active_groups: list[dict[str, Any]],
    locked_stacks: list[dict[str, Any]],
    daily_atr: float | None,
    stack_threshold: float | None = None,
    session_reference_price: float | None = None,
) -> tuple[dict[str, str | None], list[dict[str, Any]]]:
    """Validate and project frozen membership without inventing or repairing authority."""
    level_details: dict[str, dict[str, Any]] = {}
    projected: dict[str, str | None] = {}
    for level in levels_payload:
        if not isinstance(level, dict):
            continue
        name = str(level.get("name") or "").strip().upper()
        if not name:
            continue
        details = {
            "price": level.get("price"),
            "status": level.get("status"),
            "stack_group": level.get("stack_group"),
            "stack_groups": copy.deepcopy(level.get("stack_groups")) if isinstance(level.get("stack_groups"), list) else None,
        }
        level_details[name] = details
        memberships = liquidity_level_stack_groups(details)
        projected[name] = memberships[0] if len(memberships) == 1 else None

    if not level_details:
        return projected, []

    explicit_stacks: list[dict[str, Any]] | None
    if locked_stacks:
        explicit_stacks = copy.deepcopy(locked_stacks)
    else:
        explicit_stacks = [
            copy.deepcopy(group)
            for group in active_groups
            if isinstance(group, dict) and group.get("stack_group")
        ] or None

    threshold = optional_float(stack_threshold)
    if threshold is None and daily_atr is not None and daily_atr > 0:
        threshold = daily_atr * 0.10
    error = validate_liquidity_stack_structure(
        level_details,
        explicit_stacks,
        stack_threshold=threshold,
        session_reference_price=session_reference_price,
    )
    if error is not None:
        return {name: None for name in projected}, []
    return projected, copy.deepcopy(explicit_stacks or [])


def session_lock_block_reason(persisted_state: dict[str, Any], symbol: str | None) -> str | None:
    """Return the fail-safe lock error that disables Entry Agent for the session."""
    locked_context = locked_session_liquidity_context(persisted_state, symbol)
    if not isinstance(locked_context, dict) or locked_context.get("disabled") is not True:
        return None
    error = str(locked_context.get("error") or "").strip()
    if not error:
        error = "SESSION_LOCK_DISABLED"
    return f"Session liquidity lock failed at 06:15 PT; Entry Agent disabled. {error}"


def session_authority_block_reason(snapshot: dict[str, Any]) -> str | None:
    """Return a fail-closed block reason when trading context is stale for the effective session."""
    effective_session = snapshot.get("effective_session_date")
    tv_session_date = snapshot.get("tradingview_session_date")
    if (
        isinstance(effective_session, str)
        and isinstance(tv_session_date, str)
        and tv_session_date < effective_session
        and has_active_tv_levels(snapshot.get("raw_tv_context"))
    ):
        return (
            "Awaiting current-session liquidity/observation context. "
            f"TradingView context session {tv_session_date} is stale versus market session {effective_session}."
        )
    return None


def apply_observation_cycle_reset(
    persisted_state: dict[str, Any],
    symbol: str,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Clear stale per-symbol setup state once per symbol/session."""
    session_date = snapshot_session_date(snapshot)
    if not symbol or not session_date:
        return persisted_state

    symbol_key = root_symbol(symbol)
    symbol_state = symbol_scoped_persisted_state(persisted_state, symbol_key)
    if symbol_state.get("observation_reset_session_date") == session_date:
        return persisted_state

    reset_symbol_state = {
        "requested_symbol": symbol_state.get("requested_symbol") or symbol,
        "symbol": symbol_state.get("symbol"),
        "normalized_symbol": symbol_key,
        "latest_price": snapshot.get("latest_price"),
        "latest_bar_time": snapshot.get("latest_bar_time"),
        "tv_context": snapshot.get("tv_context"),
        "tv_context_status": snapshot.get("tv_context_status"),
        "observation_reset_session_date": session_date,
        "observation_reset_bar_time": snapshot.get("latest_bar_time"),
        "observation_reset_at": datetime.now(timezone.utc).isoformat(),
        "pre_open_observed_extreme": None,
        "trade_state": {"active": False, "released": False, "release_reason": None},
        "market_state": {"active_liquidity_name": None, "selected_liquidity_name": None},
        "liquidity": snapshot.get("liquidity") or {},
    }
    reset_symbol_state["step2_1a"] = {
        "step_2_activated": False,
        "blocked": True,
        "candle_a": None,
        "step2_owner_seeded_at": None,
        "step2_invalidated_at": None,
    }
    session_liquidity_context = build_session_locked_tv_context(snapshot.get("tv_context"))
    if isinstance(session_liquidity_context, dict):
        reset_symbol_state["session_liquidity_context"] = session_liquidity_context
        snapshot["session_liquidity_context"] = session_liquidity_context
    else:
        reset_symbol_state["session_liquidity_context"] = None
        snapshot["session_liquidity_context"] = None
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
    selected_liquidity: dict[str, Any] | None = None,
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
            if step_state.get("step_2_activated") is True and step2_state_matches_selected_owner(step_state, selected_liquidity):
                step_state.setdefault("events", [])
                step_state.setdefault("step2_owner_seeded_at", None)
                step_state.setdefault("step2_activated_at", None)
                step_state.setdefault("step2_invalidated_at", None)
                return step_state
            return step_2_1a_initial_state(active_level, level_price, side, tick_size)
        step_state.setdefault("events", [])
        step_state.setdefault("step_2_activated", False)
        step_state.setdefault("blocked", False)
        step_state.setdefault("candle_a", None)
        step_state.setdefault("step2_activation_candle_index", None)
        step_state.setdefault("active_level", active_level)
        step_state.setdefault("level_price", level_price)
        step_state.setdefault("side", side)
        step_state.setdefault("tick_size", tick_size)
        step_state.setdefault("expiration_candles", 5)
        step_state.setdefault("persist_pending_owner_until_resolution", False)
        step_state.setdefault("pending_step2_owner", None)
        step_state.setdefault("step2_owner_seeded_at", None)
        step_state.setdefault("step2_activated_at", None)
        step_state.setdefault("step2_invalidated_at", None)
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


SESSION_SCOPED_STEP_KEYS = (
    "step_2_1a",
    "step2_locked_owner",
    "step25",
    "step3",
    "step4",
    "step5",
    "step6",
    "rejection",
    "rejection_lane",
    "continuation_lane",
    "gateway",
    "trade_state",
    "market_state",
    "pre_open_observed_extreme",
)
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


def blocked_step_2_1a_result(
    tick_size: float,
    reason: str,
    next_candle_index: int = 0,
) -> dict[str, Any]:
    """Return an inactive Step 2 state during the lock window or a fail-safe session block."""
    return {
        "step_2_activated": False,
        "blocked": True,
        "candle_a": None,
        "step2_activation_candle_index": None,
        "active_level": None,
        "level_price": None,
        "side": None,
        "tick_size": tick_size,
        "expiration_candles": 5,
        "pre_activation_probe_boundary": {
            "active": False,
            "side": None,
            "source_level": None,
            "boundary_price": None,
            "detected_at_index": None,
        },
        "events": [{"event": "session_lock_block", "reason": reason}],
        "available": False,
        "reason": reason,
        "last_evaluated_bar_time": None,
        "next_candle_index": next_candle_index,
        "pending_step2_owner": None,
        "active_liquidity_group": None,
        "last_interacted_liquidity": None,
        "step2_locked_owner": None,
        "consumed_liquidity_levels": [],
    }


def pre_open_observed_extreme(persisted_state: dict[str, Any], symbol: str | None) -> dict[str, Any] | None:
    """Return the standalone pre-open observed extreme for one root."""
    symbol_state = symbol_scoped_persisted_state(persisted_state, symbol)
    extreme = symbol_state.get("pre_open_observed_extreme")
    return extreme if isinstance(extreme, dict) else None


@entry_state_transaction
def persist_pre_open_observed_extreme(snapshot: dict[str, Any], symbol: str | None, extreme: dict[str, Any] | None) -> None:
    """Persist the sticky pre-open observed extreme and reset markers for one root without changing other lifecycle state."""
    require_authoritative_mutation("persist_pre_open_observed_extreme")
    symbol_key = root_symbol(symbol)
    if not symbol_key:
        return
    state = load_entry_state()
    state_by_symbol = state.get("state_by_symbol")
    if not isinstance(state_by_symbol, dict):
        state_by_symbol = {}
    symbol_state = dict(symbol_scoped_persisted_state(state, symbol_key))
    current = symbol_state.get("pre_open_observed_extreme")
    observation_session_date = snapshot.get("observation_reset_session_date") or symbol_state.get("observation_reset_session_date")
    observation_bar_time = snapshot.get("observation_reset_bar_time") or symbol_state.get("observation_reset_bar_time")
    observation_reset_at = snapshot.get("observation_reset_at") or symbol_state.get("observation_reset_at")
    session_liquidity_context = (
        copy.deepcopy(snapshot.get("session_liquidity_context"))
        if isinstance(snapshot.get("session_liquidity_context"), dict)
        else symbol_state.get("session_liquidity_context")
    )
    effective_extreme = copy.deepcopy(extreme) if isinstance(extreme, dict) else None
    if symbol_state.get("observation_reset_session_date") == observation_session_date:
        effective_extreme = merged_pre_open_observed_extreme(
            current if isinstance(current, dict) else None,
            effective_extreme,
        )
    if (
        current == effective_extreme
        and symbol_state.get("observation_reset_session_date") == observation_session_date
        and symbol_state.get("observation_reset_bar_time") == observation_bar_time
        and symbol_state.get("observation_reset_at") == observation_reset_at
    ):
        return
    symbol_state["pre_open_observed_extreme"] = copy.deepcopy(effective_extreme)
    symbol_state["observation_reset_session_date"] = observation_session_date
    symbol_state["observation_reset_bar_time"] = observation_bar_time
    symbol_state["observation_reset_at"] = observation_reset_at
    if isinstance(session_liquidity_context, dict):
        symbol_state["session_liquidity_context"] = session_liquidity_context
    state_by_symbol[symbol_key] = symbol_state
    state["state_by_symbol"] = state_by_symbol
    if root_symbol(str(state.get("normalized_symbol") or "")) == symbol_key or not state.get("normalized_symbol"):
        state["pre_open_observed_extreme"] = copy.deepcopy(effective_extreme)
        state["observation_reset_session_date"] = observation_session_date
        state["observation_reset_bar_time"] = observation_bar_time
        state["observation_reset_at"] = observation_reset_at
        if isinstance(session_liquidity_context, dict):
            state["session_liquidity_context"] = copy.deepcopy(session_liquidity_context)
    _write_json(STATE_PATH, state)


def _more_extreme_price(candidate: float, current: float | None, side: str) -> bool:
    if current is None:
        return True
    if side == "upper":
        return candidate > current
    if side == "lower":
        return candidate < current
    return False


def observed_pre_open_extreme_from_snapshot(snapshot: dict[str, Any], tick_size: float) -> dict[str, Any] | None:
    """Build the current observation-window extreme from the locked TV context only."""
    tv_context = snapshot.get("tv_context")
    selected_liquidity = selected_active_liquidity_from_context(
        tv_context,
        snapshot.get("latest_price"),
        snapshot.get("ohlc") if isinstance(snapshot.get("ohlc"), dict) else None,
        tick_size,
    )
    if not isinstance(selected_liquidity, dict):
        return None
    ohlc = snapshot.get("ohlc") if isinstance(snapshot.get("ohlc"), dict) else None
    if not isinstance(ohlc, dict):
        return None
    side = selected_liquidity.get("side")
    source_level = selected_liquidity.get("name")
    group = selected_liquidity.get("group") if isinstance(selected_liquidity.get("group"), dict) else None
    boundary_price = optional_float((group or {}).get("extreme_boundary"))
    if boundary_price is None:
        boundary_price = optional_float(selected_liquidity.get("price"))
    if side not in {"upper", "lower"} or source_level is None or boundary_price is None:
        return None
    candidate_price = optional_float(ohlc.get("high")) if side == "upper" else optional_float(ohlc.get("low"))
    if candidate_price is None or not _more_extreme_price(candidate_price, boundary_price, side):
        return None
    session_context = snapshot.get("session_liquidity_context") if isinstance(snapshot.get("session_liquidity_context"), dict) else {}
    locked_tv_context = session_context.get("tv_context") if isinstance(session_context.get("tv_context"), dict) else tv_context
    return {
        "symbol": snapshot.get("normalized_symbol") or snapshot.get("symbol"),
        "side": side,
        "price": candidate_price,
        "timestamp": snapshot.get("latest_bar_time"),
        "source": "observation_window",
        "session_date": local_session_date(snapshot.get("latest_bar_time")) or (locked_tv_context or {}).get("session_date"),
        "time_zone": (locked_tv_context or {}).get("time_zone") or "America/Los_Angeles",
        "source_level": source_level,
        "stack_group": (group or {}).get("name"),
        "stack_components": list((group or {}).get("components") or []),
        "locked_boundary_price": boundary_price,
        "session_lock_price": (locked_tv_context or {}).get("session_lock_price"),
        "liquidity_context_locked_at": (locked_tv_context or {}).get("liquidity_context_locked_at"),
    }


def _pre_open_observation_owner_identity(extreme: dict[str, Any]) -> tuple[str, str] | None:
    """Return the frozen liquidity identity represented by one observation."""
    stack_group = str(extreme.get("stack_group") or "").strip()
    if stack_group:
        return "stack", stack_group
    source_level = str(extreme.get("source_level") or "").strip()
    if source_level:
        return "level", source_level
    return None


def same_pre_open_observation_identity(
    current_extreme: dict[str, Any],
    candidate_extreme: dict[str, Any],
) -> bool:
    """Require one side, session, and frozen liquidity identity before progression."""
    if str(current_extreme.get("side") or "") != str(candidate_extreme.get("side") or ""):
        return False

    current_owner = _pre_open_observation_owner_identity(current_extreme)
    candidate_owner = _pre_open_observation_owner_identity(candidate_extreme)
    if current_owner != candidate_owner:
        return False

    current_session = str(current_extreme.get("session_date") or "").strip()
    candidate_session = str(candidate_extreme.get("session_date") or "").strip()
    if current_session and candidate_session and current_session != candidate_session:
        return False

    current_boundary = optional_float(current_extreme.get("locked_boundary_price"))
    candidate_boundary = optional_float(candidate_extreme.get("locked_boundary_price"))
    if current_boundary is not None and candidate_boundary is not None and current_boundary != candidate_boundary:
        return False
    return True


def merged_pre_open_observed_extreme(
    current_extreme: dict[str, Any] | None,
    candidate_extreme: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Keep the same-owner running outward extreme for the observation period."""
    if not isinstance(candidate_extreme, dict):
        return current_extreme if isinstance(current_extreme, dict) else None
    if not isinstance(current_extreme, dict):
        return candidate_extreme
    if not same_pre_open_observation_identity(current_extreme, candidate_extreme):
        return current_extreme
    side = str(candidate_extreme.get("side") or "")
    current_price = optional_float(current_extreme.get("price"))
    candidate_price = optional_float(candidate_extreme.get("price"))
    if candidate_price is None:
        return current_extreme
    if _more_extreme_price(candidate_price, current_price, side):
        return candidate_extreme
    return current_extreme


def frozen_session_contract_payload(
    snapshot: dict[str, Any],
    active_name: Any,
    active_group: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return the full frozen 06:15 TradingView contract for operator validation."""
    raw_context = snapshot.get("raw_tv_context") if isinstance(snapshot.get("raw_tv_context"), dict) else {}
    session_context = snapshot.get("session_liquidity_context") if isinstance(snapshot.get("session_liquidity_context"), dict) else {}
    locked_liquidity = raw_context.get("locked_liquidity_context") if isinstance(raw_context.get("locked_liquidity_context"), dict) else {}
    locked_map = locked_liquidity.get("liquidity_map") if isinstance(locked_liquidity.get("liquidity_map"), dict) else {}
    active_groups = session_context.get("active_groups") if isinstance(session_context.get("active_groups"), list) else []
    active_components = set()
    if isinstance(active_group, dict):
        active_components.update(str(component) for component in (active_group.get("components") or []) if component)
    active_name_text = str(active_name or "").strip()
    if active_name_text and not active_components:
        active_components.add(active_name_text)

    locked_stacks = locked_map.get("stacks") if isinstance(locked_map.get("stacks"), list) else []
    daily_atr = (
        daily_atr_from_context(locked_liquidity)
        or daily_atr_from_context(session_context.get("tv_context") if isinstance(session_context.get("tv_context"), dict) else None)
        or daily_atr_from_context(raw_context)
    )

    levels_payload = locked_map.get("levels") if isinstance(locked_map.get("levels"), list) else []
    if not levels_payload:
        locked_levels = locked_liquidity.get("levels") if isinstance(locked_liquidity.get("levels"), dict) else {}
        levels_payload = [
            {
                "name": name,
                "price": details.get("price"),
                "status": details.get("status"),
                "stack_group": details.get("stack_group"),
                "stack_groups": copy.deepcopy(details.get("stack_groups")) if isinstance(details.get("stack_groups"), list) else None,
            }
            for name, details in locked_levels.items()
            if isinstance(details, dict)
        ]

    projected_stack_groups, projected_stacks = projected_frozen_stack_groups(
        levels_payload=levels_payload,
        active_groups=active_groups,
        locked_stacks=locked_stacks,
        daily_atr=daily_atr,
        stack_threshold=stack_threshold_from_context(locked_liquidity),
        session_reference_price=stack_reference_price_from_context(locked_liquidity),
    )

    stack_lookup: dict[str, dict[str, Any]] = {}
    projected_memberships: dict[str, list[str]] = {}
    for stack in projected_stacks:
        if not isinstance(stack, dict):
            continue
        stack_name = str(stack.get("stack_group") or stack.get("id") or stack.get("name") or "").strip()
        if stack_name:
            stack_lookup[stack_name] = copy.deepcopy(stack)
            raw_members = stack.get("members") if isinstance(stack.get("members"), list) else stack.get("components")
            if isinstance(raw_members, list):
                for raw_member in raw_members:
                    member_name = str(raw_member or "").strip().upper()
                    if member_name:
                        projected_memberships.setdefault(member_name, []).append(stack_name)

    group_lookup: dict[str, dict[str, Any]] = {}
    for group in active_groups:
        if not isinstance(group, dict):
            continue
        group_name = str(group.get("name") or group.get("stack_group") or "").strip()
        if group_name:
            group_lookup[group_name] = group

    level_side_by_name: dict[str, str | None] = {}
    rows: list[dict[str, Any]] = []
    for level in levels_payload:
        if not isinstance(level, dict):
            continue
        name = str(level.get("name") or "").strip().upper()
        if not name:
            continue
        stack_groups = projected_memberships.get(name) or liquidity_level_stack_groups(level)
        stack_name = stack_groups[0] if len(stack_groups) == 1 else None
        group = group_lookup.get(stack_name or name) if (stack_name or name) else None
        stack = stack_lookup.get(stack_name or "") if stack_name else None
        level_price = optional_float(level.get("price"))
        if stack_name and isinstance(stack, dict):
            close_boundary = optional_float(stack.get("close_boundary_price"))
            extreme_boundary = optional_float(stack.get("extreme_boundary_price"))
            close_boundary_name = stack.get("close_boundary_name")
            extreme_boundary_name = stack.get("extreme_boundary_name")
        elif isinstance(group, dict):
            close_boundary = optional_float(group.get("close_boundary"))
            extreme_boundary = optional_float(group.get("extreme_boundary"))
            close_boundary_name = group.get("close_component") or name
            extreme_boundary_name = group.get("extreme_component") or name
        else:
            close_boundary = level_price
            extreme_boundary = level_price
            close_boundary_name = name
            extreme_boundary_name = name
        session_reference_price = stack_reference_price_from_context(locked_liquidity)
        side = side_for_level(name, level_price, session_reference_price)
        level_side_by_name[name] = side
        rows.append(
            {
                "name": name,
                "price": level_price,
                "status": str(level.get("status") or "").upper() or None,
                "stack_group": stack_name,
                "stack_groups": copy.deepcopy(stack_groups),
                "side": side,
                "close_boundary": close_boundary,
                "close_boundary_name": str(close_boundary_name or name).strip().upper(),
                "extreme_boundary": extreme_boundary,
                "extreme_boundary_name": str(extreme_boundary_name or name).strip().upper(),
                "is_active_owner": name in active_components,
            }
        )

    midpoints = copy.deepcopy(locked_liquidity.get("midpoints")) if isinstance(locked_liquidity.get("midpoints"), dict) else {}
    raw_exhaustion = locked_liquidity.get("exhaustion_boundaries") if isinstance(locked_liquidity.get("exhaustion_boundaries"), dict) else {}
    exhaustion_boundaries: dict[str, Any] = {}
    for key, value in raw_exhaustion.items():
        pair_key = str(key)
        midpoint_value = optional_float(midpoints.get(pair_key))
        default_side = None
        parts = [part.strip().upper() for part in pair_key.split("_") if part and str(part).strip()]
        for part in parts:
            side_candidate = level_side_by_name.get(part) or side_for_level(part)
            if side_candidate in {"upper", "lower"}:
                default_side = side_candidate
                break
        if isinstance(value, dict):
            exhaustion_boundaries[pair_key] = {
                "side": str(value.get("side") or default_side or "").strip().lower() or None,
                "mid_50": optional_float(value.get("mid_50")) if value.get("mid_50") is not None else midpoint_value,
                "remaining_25": optional_float(value.get("remaining_25")),
            }
            continue
        exhaustion_boundaries[pair_key] = {
            "side": default_side,
            "mid_50": midpoint_value,
            "remaining_25": optional_float(value),
        }

    return {
        "levels": rows,
        "stacks": projected_stacks,
        "midpoints": midpoints,
        "exhaustion_boundaries": exhaustion_boundaries,
    }


def public_liquidity_lock_payload(
    snapshot: dict[str, Any],
    active_name: Any,
    active_price: Any,
    active_group: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a compact public view of the frozen 06:15 liquidity lock."""
    session_context = snapshot.get("session_liquidity_context") if isinstance(snapshot.get("session_liquidity_context"), dict) else {}
    locked_context = session_context.get("tv_context") if isinstance(session_context.get("tv_context"), dict) else {}
    raw_context = snapshot.get("raw_tv_context") if isinstance(snapshot.get("raw_tv_context"), dict) else {}
    locked_at = locked_context.get("liquidity_context_locked_at") or locked_context.get("received_at")
    active_levels = session_context.get("active_levels") if isinstance(session_context.get("active_levels"), dict) else {}
    active_groups = session_context.get("active_groups") if isinstance(session_context.get("active_groups"), list) else []
    last_tv_context_levels = raw_context.get("last_tv_context_levels") if isinstance(raw_context.get("last_tv_context_levels"), dict) else {}
    frozen_stack_names = [
        str(group.get("display_name") or group.get("name"))
        for group in active_groups
        if isinstance(group, dict) and (group.get("display_name") or group.get("name"))
    ]
    session_context_stale = bool(snapshot.get("session_context_stale"))
    is_locked = bool(session_context) and session_context.get("disabled") is not True and session_context.get("locked") is True and not session_context_stale
    if not is_locked:
        return {
            "stale": session_context_stale,
            "stale_reason": (
                "Session liquidity lock is from an older session."
                if session_context_stale
                else None
            ),
            "actionable": False,
            "effective_session_date": snapshot.get("effective_session_date"),
            "tradingview_session_date": snapshot.get("tradingview_session_date"),
            "rithmic_session_date": snapshot.get("rithmic_session_date"),
            "locked": False,
            "session_date": locked_context.get("session_date"),
            "lock_time": format_public_time_seconds_pt(locked_at),
            "lock_source": "TradingView" if locked_context else None,
            "active_liquidity_name": None,
            "liquidity_group": None,
            "liquidity_level_name": None,
            "liquidity_level_price": None,
            "rejection_boundary": None,
            "continuation_boundary": None,
            "frozen_liquidity_levels": {},
            "frozen_stack_names": [],
            "frozen_session_contract": {"levels": [], "stacks": [], "midpoints": {}, "exhaustion_boundaries": {}},
            "last_tv_context_received_time": format_public_time_seconds_pt(
                raw_context.get("last_tv_context_received_at") or raw_context.get("received_at")
            ),
            "last_tv_context_session_date": raw_context.get("last_tv_context_session_date") or raw_context.get("session_date"),
            "last_tv_context_levels": copy.deepcopy(last_tv_context_levels),
            "last_tv_context_matches_frozen": False,
        }
    if session_context.get("disabled") is True:
        return {
            "stale": False,
            "stale_reason": None,
            "actionable": False,
            "effective_session_date": snapshot.get("effective_session_date"),
            "tradingview_session_date": snapshot.get("tradingview_session_date"),
            "rithmic_session_date": snapshot.get("rithmic_session_date"),
            **{
                "locked": True,
                "session_date": locked_context.get("session_date"),
                "lock_time": format_public_time_seconds_pt(locked_at),
                "lock_source": "TradingView" if locked_context else None,
                "active_liquidity_name": None,
                "liquidity_group": None,
                "liquidity_level_name": None,
                "liquidity_level_price": None,
                "rejection_boundary": None,
                "continuation_boundary": None,
                "frozen_liquidity_levels": {},
                "frozen_stack_names": [],
                "frozen_session_contract": {"levels": [], "stacks": [], "midpoints": {}, "exhaustion_boundaries": {}},
                "last_tv_context_received_time": format_public_time_seconds_pt(
                    raw_context.get("last_tv_context_received_at") or raw_context.get("received_at")
                ),
                "last_tv_context_session_date": raw_context.get("last_tv_context_session_date") or raw_context.get("session_date"),
                "last_tv_context_levels": copy.deepcopy(last_tv_context_levels),
                "last_tv_context_matches_frozen": False,
            },
        }

    liquidity_level = public_liquidity_level_payload(active_group, active_name, active_price)
    return {
        "locked": True,
        "session_date": locked_context.get("session_date") or local_session_date(snapshot.get("latest_bar_time")),
        "lock_time": format_public_time_seconds_pt(locked_at),
        "lock_source": "TradingView",
        "active_liquidity_name": public_active_liquidity_display_name(snapshot, active_group, active_name, active_price),
        "liquidity_group": active_group.get("name") if isinstance(active_group, dict) else None,
        "liquidity_level_name": liquidity_level["name"],
        "liquidity_level_price": liquidity_level["price"],
        "rejection_boundary": public_rejection_boundary(
            active_group,
            active_group.get("wick_boundary_extreme") if isinstance(active_group, dict) else None,
            active_group.get("extreme_boundary") if isinstance(active_group, dict) else None,
            active_price,
        ),
        "continuation_boundary": None,
        "frozen_liquidity_levels": copy.deepcopy(active_levels),
        "frozen_stack_names": frozen_stack_names,
        "frozen_session_contract": frozen_session_contract_payload(snapshot, active_name, active_group),
        "last_tv_context_received_time": format_public_time_seconds_pt(
            raw_context.get("last_tv_context_received_at") or raw_context.get("received_at")
        ),
        "last_tv_context_session_date": raw_context.get("last_tv_context_session_date") or raw_context.get("session_date"),
        "last_tv_context_levels": copy.deepcopy(last_tv_context_levels),
        "last_tv_context_matches_frozen": bool(last_tv_context_levels) and last_tv_context_levels == active_levels,
    }


def selected_liquidity_matches_pre_open_extreme(selected_liquidity: dict[str, Any], extreme: dict[str, Any]) -> bool:
    """Return True when the first post-open Step 2 selection matches stored pre-open context."""
    side = str(extreme.get("side") or "")
    if side not in {"upper", "lower"} or selected_liquidity.get("side") != side:
        return False
    group = selected_liquidity.get("group") if isinstance(selected_liquidity.get("group"), dict) else None
    source_level = str(extreme.get("source_level") or "")
    stack_group = str(extreme.get("stack_group") or "")
    if isinstance(group, dict):
        group_name = str(group.get("name") or "")
        components = [str(component) for component in (group.get("components") or [])]
        if stack_group and group_name == stack_group:
            return True
        return bool(source_level and source_level in components)
    return bool(source_level and selected_liquidity.get("name") == source_level)


def seed_step2_probe_from_pre_open_extreme(
    step_state: dict[str, Any],
    observed_extreme: dict[str, Any] | None,
    candle_index: int,
) -> None:
    """Seed the first post-open Step 2 state from standalone pre-open context."""
    if not isinstance(observed_extreme, dict):
        return
    price = optional_float(observed_extreme.get("price"))
    side = str(observed_extreme.get("side") or "")
    if price is None or side not in {"upper", "lower"} or step_state.get("side") != side:
        return
    probe = step_state.get("pre_activation_probe_boundary")
    if not isinstance(probe, dict):
        return
    current_boundary = optional_float(probe.get("boundary_price"))
    if probe.get("active") is True and current_boundary is not None and not _more_extreme_price(price, current_boundary, side):
        return
    probe.update(
        {
            "active": True,
            "side": side,
            "source_level": observed_extreme.get("source_level") or step_state.get("active_level"),
            "boundary_price": price,
            "detected_at_index": candle_index,
        }
    )
    events = step_state.setdefault("events", [])
    if not any(event.get("event") == "pre_open_observed_extreme_seeded" for event in events if isinstance(event, dict)):
        events.append(
            {
                "event": "pre_open_observed_extreme_seeded",
                "timestamp": observed_extreme.get("timestamp"),
                "boundary_price": price,
                "source": "observation_window",
            }
        )


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


def rejection_context_survives_missing_active_liquidity(
    snapshot: dict[str, Any],
    previous_symbol_state: dict[str, Any] | None,
) -> bool:
    """Return True when persisted rejection/Leg 1 context must outlive a transient no-active refresh."""
    previous_symbol_state = previous_symbol_state if isinstance(previous_symbol_state, dict) else {}
    previous_step2 = previous_symbol_state.get("step_2_1a") if isinstance(previous_symbol_state.get("step_2_1a"), dict) else {}
    previous_step4 = previous_symbol_state.get("step4") if isinstance(previous_symbol_state.get("step4"), dict) else {}
    previous_step4_state = previous_step4.get("state") if isinstance(previous_step4.get("state"), dict) else {}
    previous_lane = previous_symbol_state.get("rejection_lane") if isinstance(previous_symbol_state.get("rejection_lane"), dict) else {}
    if previous_step2.get("step_2_activated") is not True:
        return False
    locked_owner = previous_step2.get("step2_locked_owner") if isinstance(previous_step2.get("step2_locked_owner"), dict) else {}
    if locked_owner.get("pathway") not in {None, "rejection"}:
        return False
    if previous_step2.get("step2_invalidated_at"):
        return False
    if previous_step4_state.get("leg1_window_invalidated") is True:
        return False
    if previous_step4_state.get("invalidation_source") or previous_step4_state.get("invalidated_at"):
        return False
    if isinstance(previous_lane, dict) and previous_lane.get("invalidation_reason"):
        return False
    projected_pending = projected_pending_rejection_step4_state(snapshot, previous_symbol_state)
    if isinstance(projected_pending, dict):
        return True
    locked_ok, _reason = valid_participation_locked_leg1_state(previous_step4_state)
    return locked_ok


def restore_rejection_context_without_active_liquidity(
    snapshot: dict[str, Any],
    previous_symbol_state: dict[str, Any] | None,
) -> bool:
    """Restore persisted rejection state when no explicit invalidation/reset exists."""
    previous_symbol_state = previous_symbol_state if isinstance(previous_symbol_state, dict) else {}
    if not rejection_context_survives_missing_active_liquidity(snapshot, previous_symbol_state):
        return False
    previous_step2 = previous_symbol_state.get("step_2_1a") if isinstance(previous_symbol_state.get("step_2_1a"), dict) else {}
    previous_step25 = previous_symbol_state.get("step25") if isinstance(previous_symbol_state.get("step25"), dict) else {}
    previous_step3 = previous_symbol_state.get("step3") if isinstance(previous_symbol_state.get("step3"), dict) else {}
    previous_step4 = previous_symbol_state.get("step4") if isinstance(previous_symbol_state.get("step4"), dict) else {}
    previous_step5 = previous_symbol_state.get("step5") if isinstance(previous_symbol_state.get("step5"), dict) else {}

    restored_step2 = copy.deepcopy(previous_step2)
    restored_step25 = copy.deepcopy(previous_step25)
    restored_step3 = copy.deepcopy(previous_step3)
    restored_step4 = copy.deepcopy(previous_step4)
    restored_step5 = copy.deepcopy(previous_step5)

    projected_pending = projected_pending_rejection_step4_state(snapshot, previous_symbol_state)
    if isinstance(projected_pending, dict):
        restored_step4["state"] = projected_pending
        restored_step4["status"] = "WAIT"
        restored_step4["next_step"] = "Step 4"
        seeded_projection = projected_seeded_step4_status(snapshot, restored_step2, restored_step4)
        if seeded_projection:
            restored_step4["reason"] = seeded_projection.get("reason")

    snapshot["suppress_active_liquidity"] = False
    snapshot["step_2_1a"] = restored_step2
    snapshot["step25"] = restored_step25
    snapshot["step3"] = restored_step3
    snapshot["step4"] = restored_step4
    if restored_step5:
        snapshot["step5"] = restored_step5
    return True


def continuation_context_survives_missing_active_liquidity(
    snapshot: dict[str, Any],
    previous_symbol_state: dict[str, Any] | None,
) -> bool:
    """Return True when active/seeded continuation state must survive a transient no-active refresh."""
    previous_symbol_state = previous_symbol_state if isinstance(previous_symbol_state, dict) else {}
    previous_lane = previous_symbol_state.get("continuation_lane") if isinstance(previous_symbol_state.get("continuation_lane"), dict) else {}
    previous_step25 = previous_symbol_state.get("step25") if isinstance(previous_symbol_state.get("step25"), dict) else {}
    previous_step25_state = previous_step25.get("state") if isinstance(previous_step25.get("state"), dict) else {}
    previous_step5 = previous_symbol_state.get("step5") if isinstance(previous_symbol_state.get("step5"), dict) else {}
    previous_step5_state = previous_step5.get("state") if isinstance(previous_step5.get("state"), dict) else {}
    previous_step6 = previous_symbol_state.get("step6") if isinstance(previous_symbol_state.get("step6"), dict) else {}
    lane_status = str(previous_lane.get("lane_status") or "").strip().lower()
    step2_status = str(previous_lane.get("step2_status") or "").strip().upper()
    if lane_status not in {"eligible", "controlling"}:
        return False
    if previous_lane.get("invalidation_reason"):
        return False
    if previous_step5_state.get("invalidated_at"):
        return False
    if decision_status(previous_step6) == "CONFIRM":
        return False
    if lane_status == "controlling" and step2_status != "CONFIRMED":
        return False
    if lane_status == "eligible" and optional_float(previous_lane.get("wick_boundary_extreme")) is None:
        return False
    lane_owner_name = previous_lane.get("liquidity_level_name") or previous_lane.get("active_liquidity_name")
    lane_owner_price = previous_lane.get("liquidity_level_price")
    if lane_owner_price is None:
        lane_owner_price = previous_lane.get("active_liquidity_price")
    if liquidity_level_consumed(previous_symbol_state, lane_owner_name, lane_owner_price):
        return False
    return (
        previous_step25_state.get("continuation_step2_activated") is True
        or previous_step25_state.get("continuation_eligible_source") == "frozen_rejection_trade_state"
        or lane_status == "eligible"
    )


def restore_continuation_context_without_active_liquidity(
    snapshot: dict[str, Any],
    previous_symbol_state: dict[str, Any] | None,
) -> bool:
    """Restore persisted continuation lifecycle when active liquidity is transiently unavailable."""
    previous_symbol_state = previous_symbol_state if isinstance(previous_symbol_state, dict) else {}
    if not continuation_context_survives_missing_active_liquidity(snapshot, previous_symbol_state):
        return False
    for key in ("step_2_1a", "step25", "step3", "step4", "step5", "step6", "trade_state", "rejection_lane", "continuation_lane"):
        value = previous_symbol_state.get(key)
        if isinstance(value, dict):
            snapshot[key] = copy.deepcopy(value)
    snapshot["suppress_active_liquidity"] = False
    return True


def clear_downstream_state_without_active_liquidity(
    snapshot: dict[str, Any],
    previous_symbol_state: dict[str, Any] | None = None,
) -> None:
    """Clear stale downstream state when no close-confirmed liquidity activation is public."""
    if restore_continuation_context_without_active_liquidity(snapshot, previous_symbol_state):
        return
    if restore_rejection_context_without_active_liquidity(snapshot, previous_symbol_state):
        return
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


def active_step4_candle_b_reservation(
    persisted_state: dict[str, Any],
    current_candle: dict[str, Any] | None,
    *,
    expected_active_liquidity: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return active Step 4 Candle B reservation details when the next future candle is reserved."""
    if not isinstance(current_candle, dict):
        return None
    step4 = persisted_state.get("step4") if isinstance(persisted_state.get("step4"), dict) else {}
    state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    lane_contract = lifecycle_lane_contract(state.get("lane_id"))
    if lane_contract.get("lane_name") == "continuation":
        return None
    if lane_contract.get("lane_name") != "rejection" and normalized_pathway_name(state.get("controlling_mode")) in {"S/R", "R/S"}:
        return None
    if state.get("leg1_window_active") is not True:
        return None
    if state.get("leg1_status") == "COMPLETE" or state.get("leg1_state_locked") is True:
        return None
    if state.get("leg1_window_invalidated") is True:
        return None
    if state.get("leg1_window_candle_index") != 0:
        return None
    started_at = state.get("leg1_window_started_at")
    if not started_at or not candle_is_after(current_candle, started_at):
        return None
    candle_a = state.get("candle_a") if isinstance(state.get("candle_a"), dict) else None
    active = state.get("active_liquidity") if isinstance(state.get("active_liquidity"), dict) else None
    if not isinstance(active, dict) or not active.get("name") or active.get("price") is None:
        return None
    if isinstance(expected_active_liquidity, dict) and not same_liquidity_owner(active, expected_active_liquidity):
        return None
    return {
        "candle_a": candle_a,
        "candle_a_time": candle_timestamp(candle_a) or started_at,
        "active_liquidity": active,
        "setup_direction": state.get("setup_direction"),
        "started_at": started_at,
    }


def pending_step2_probe_liquidity(
    persisted_state: dict[str, Any],
    tv_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    #
    # STEP 2 REJECTION CONTRACT
    #
    # close_boundary:
    # - Reference / display only for the active stack.
    # - Never confirms Step 2 rejection.
    #
    # extreme_boundary:
    # - Sole Step 2 rejection trigger.
    # - Step 2 rejection confirms only on a close beyond the active extreme_boundary.
    #
    # Pending owner lifecycle:
    # - A wick-only raid creates or updates the pending owner, but does not confirm Step 2.
    # - The pending owner persists until confirmation, invalidation, or continuation takeover.
    #
    # Raid-boundary mutation:
    # - High-side raid extreme is monotonic upward while the owner is active.
    # - Low-side raid extreme is monotonic downward while the owner is active.
    #
    # Canonical replay example:
    # - 2026-06-19 LH/PMH
    # - 06:30 wick creates 30678.25
    # - 06:47 wick updates to 30680.0
    # - 06:56 close above 30680.0 confirms Step 2
    #
    """Keep a pre-confirmation Step 2 raid owner alive across candles until confirmation or release."""
    step2 = persisted_state.get("step_2_1a") if isinstance(persisted_state.get("step_2_1a"), dict) else {}
    if step2.get("step_2_activated") is True:
        return None
    probe = step2.get("pre_activation_probe_boundary") if isinstance(step2.get("pre_activation_probe_boundary"), dict) else {}
    active_level = step2.get("active_level")
    level_price = optional_float(step2.get("level_price"))
    if not active_level or level_price is None:
        return None
    side = step2.get("side") or side_for_level(str(active_level))
    if side not in {"upper", "lower"}:
        return None
    group = step2.get("active_liquidity_group") if isinstance(step2.get("active_liquidity_group"), dict) else None
    if not isinstance(group, dict):
        last_interacted = step2.get("last_interacted_liquidity") if isinstance(step2.get("last_interacted_liquidity"), dict) else None
        if isinstance(last_interacted, dict) and isinstance(last_interacted.get("group"), dict):
            group = last_interacted.get("group")
        else:
            group = active_stack_from_context(tv_context, str(active_level))
    if probe.get("active") is not True and actionable_boundary_from_group(group) is None:
        return None
    return {
        "name": active_level,
        "price": level_price,
        "display_name": (
            (step2.get("last_interacted_liquidity") or {}).get("display_name")
            if isinstance(step2.get("last_interacted_liquidity"), dict)
            else (group or {}).get("display_name")
        ),
        "side": side,
        "group": group,
    }


def build_pending_step2_owner(
    step_state: dict[str, Any],
    selected_liquidity: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Capture the controlling unresolved Step 2.1 owner while confirmation is pending."""
    if not isinstance(step_state, dict) or step_state.get("step_2_activated") is True:
        return None
    if not isinstance(selected_liquidity, dict):
        return None
    active_name = step_state.get("active_level") or selected_liquidity.get("name")
    active_price = optional_float(step_state.get("level_price"))
    if active_price is None:
        active_price = optional_float(selected_liquidity.get("price"))
    if not valid_active_liquidity_selection(active_name, active_price):
        return None
    side = step_state.get("side") or selected_liquidity.get("side") or side_for_level(str(active_name or ""))
    group = (
        step_state.get("active_liquidity_group")
        if isinstance(step_state.get("active_liquidity_group"), dict)
        else selected_liquidity.get("group")
        if isinstance(selected_liquidity.get("group"), dict)
        else None
    )
    probe = step_state.get("pre_activation_probe_boundary") if isinstance(step_state.get("pre_activation_probe_boundary"), dict) else {}
    return {
        "active_liquidity_name": active_name,
        "active_liquidity_price": active_price,
        "display_name": selected_liquidity.get("display_name") or (group or {}).get("display_name"),
        "side": side,
        "active_liquidity_group": group,
        "owner_started_at": step_state.get("step2_owner_seeded_at") or step_state.get("last_evaluated_bar_time"),
        "owner_source": "probe" if probe.get("active") is True else "level",
    }


def selected_liquidity_qualifies_by_close(
    selected_liquidity: dict[str, Any] | None,
    current_candle: dict[str, Any] | None,
) -> bool:
    """Return True when the current candle close qualifies the selected liquidity interaction."""
    if not isinstance(selected_liquidity, dict) or not isinstance(current_candle, dict):
        return False
    close = optional_float(current_candle.get("close"))
    if close is None:
        return False
    group = selected_liquidity.get("group") if isinstance(selected_liquidity.get("group"), dict) else None
    side = selected_liquidity.get("side") or side_for_level(str(selected_liquidity.get("name") or ""))
    boundary = (
        optional_float((group or {}).get("close_boundary"))
        if isinstance(group, dict)
        else optional_float(selected_liquidity.get("price"))
    )
    if boundary is None or side not in {"upper", "lower"}:
        return False
    if side == "upper":
        return close >= boundary
    return close <= boundary


def pending_step2_owner_release_reason(
    persisted_state: dict[str, Any],
    current_candle: dict[str, Any] | None,
    *,
    next_selected_liquidity: dict[str, Any] | None = None,
    threshold_record: dict[str, Any] | None = None,
    consumed_levels: list[dict[str, Any]] | None = None,
) -> str | None:
    """Return an explicit release reason when a pending Step 2.1 owner is no longer allowed to control."""
    step2 = persisted_state.get("step_2_1a") if isinstance(persisted_state.get("step_2_1a"), dict) else {}
    owner = step2.get("pending_step2_owner") if isinstance(step2.get("pending_step2_owner"), dict) else None
    if not isinstance(owner, dict):
        return None
    if step2.get("step_2_activated") is True:
        return "NEW_STEP2"

    step4 = persisted_state.get("step4") if isinstance(persisted_state.get("step4"), dict) else {}
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    invalidation_source = str(step4_state.get("invalidation_source") or "").strip()
    if step4_state.get("leg1_window_invalidated") is True and invalidation_source in {
        "step2_step4_50_line",
        "leg1_50_percent_rule",
    }:
        return "STEP2_STEP4_50_PERCENT_INVALIDATION"

    owner_liquidity = {
        "name": owner.get("active_liquidity_name"),
        "price": owner.get("active_liquidity_price"),
        "side": owner.get("side") or side_for_level(str(owner.get("active_liquidity_name") or "")),
        "group": owner.get("active_liquidity_group") if isinstance(owner.get("active_liquidity_group"), dict) else None,
    }
    if (
        isinstance(next_selected_liquidity, dict)
        and not same_liquidity_owner(next_selected_liquidity, owner_liquidity)
    ):
        if selected_liquidity_qualifies_by_close(next_selected_liquidity, current_candle):
            return "NEW_STEP2_DIFFERENT_LIQUIDITY"
        return "NEW_STEP21A_DIFFERENT_LIQUIDITY"

    owner_name = owner.get("active_liquidity_name")
    owner_price = owner.get("active_liquidity_price")
    threshold_key = threshold_record.get("key") if isinstance(threshold_record, dict) else None
    if threshold_key and threshold_key == liquidity_key(owner_name, owner_price):
        return "CURRENT_LEVEL_CONSUMED"
    if consumed_liquidity_blocks(
        {**persisted_state, "consumed_liquidity_levels": list(consumed_levels or consumed_liquidity_levels(persisted_state))},
        owner_name,
        owner_price,
        current_candle,
    ):
        return "CURRENT_LEVEL_CONSUMED"
    return None


def pending_step2_owner_liquidity(
    persisted_state: dict[str, Any],
    tv_context: dict[str, Any] | None,
    current_candle: dict[str, Any] | None,
    *,
    next_selected_liquidity: dict[str, Any] | None = None,
    threshold_record: dict[str, Any] | None = None,
    consumed_levels: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Return the unresolved Step 2.1 owner liquidity when it still controls selection."""
    step2 = persisted_state.get("step_2_1a") if isinstance(persisted_state.get("step_2_1a"), dict) else {}
    owner = step2.get("pending_step2_owner") if isinstance(step2.get("pending_step2_owner"), dict) else None
    if not isinstance(owner, dict):
        return None
    if pending_step2_owner_release_reason(
        persisted_state,
        current_candle,
        next_selected_liquidity=next_selected_liquidity,
        threshold_record=threshold_record,
        consumed_levels=consumed_levels,
    ):
        return None
    liquidity = {
        "name": owner.get("active_liquidity_name"),
        "price": owner.get("active_liquidity_price"),
        "display_name": owner.get("display_name"),
        "side": owner.get("side") or side_for_level(str(owner.get("active_liquidity_name") or "")),
        "group": owner.get("active_liquidity_group"),
    }
    if not persisted_liquidity_matches_context(liquidity, tv_context):
        return None
    if not isinstance(liquidity.get("group"), dict):
        liquidity["group"] = active_stack_from_context(tv_context, str(liquidity.get("name") or ""))
    return liquidity


def restore_pending_step2_probe_owner(step_state: dict[str, Any]) -> None:
    """Preserve an unresolved live Step 2 raid owner until confirmation or explicit release."""
    if not isinstance(step_state, dict) or step_state.get("step_2_activated") is True:
        return
    active_level = step_state.get("active_level")
    side = step_state.get("side") or side_for_level(str(active_level or ""))
    if not active_level or side not in {"upper", "lower"}:
        return
    group = step_state.get("active_liquidity_group") if isinstance(step_state.get("active_liquidity_group"), dict) else None
    boundary = actionable_boundary_from_group(group)
    if boundary is None:
        return

    probe = step_state.get("pre_activation_probe_boundary")
    if not isinstance(probe, dict):
        probe = {}
        step_state["pre_activation_probe_boundary"] = probe

    step_state["persist_pending_owner_until_resolution"] = True
    current_boundary = optional_float(probe.get("boundary_price"))
    boundary_more_extreme = current_boundary is None or (
        boundary > current_boundary if side == "upper" else boundary < current_boundary
    )
    if boundary_more_extreme:
        probe["boundary_price"] = boundary
    probe["active"] = True
    probe["side"] = side
    probe["source_level"] = active_level


OPPOSITE_SIDE_LIQUIDITY_BREACH_RELEASE = "OPPOSITE_SIDE_LIQUIDITY_BREACH_RELEASE"
SAME_SIDE_NEXT_LIQUIDITY_OWNER_ROTATION = "SAME_SIDE_NEXT_LIQUIDITY_OWNER_ROTATION"


def active_liquidity_groups_from_context(tv_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return active liquidity groups with stack boundaries for release and display checks."""
    if not isinstance(tv_context, dict) or not isinstance(tv_context.get("levels"), dict):
        return []

    def stack_display_name(components: list[dict[str, Any]], side: str | None) -> str:
        if len(components) == 1:
            return str(components[0]["name"])
        if side == "lower":
            ordered = sorted(components, key=lambda item: (-item["price"], item["priority"], item["name"]))
        elif side == "upper":
            ordered = sorted(components, key=lambda item: (item["price"], item["priority"], item["name"]))
        else:
            ordered = sorted(components, key=lambda item: (item["priority"], item["name"]))
        return f"{'/'.join(str(component['name']) for component in ordered)} Liquidity"

    reference_price = stack_reference_price_from_context(tv_context)
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

        stack_groups = liquidity_level_stack_groups(details)
        owner_groups = stack_groups or [None]
        for stack_group in owner_groups:
            group_key = f"stack:{stack_group}" if stack_group else f"level:{name}"
            group = grouped.setdefault(
                group_key,
                {
                    "stack_group": stack_group,
                    "components": [],
                },
            )
            declared_stack_side = stack_group_side(stack_group) if stack_group else None
            component_side = side_for_level(name, price, reference_price)
            if component_side not in {"upper", "lower"}:
                continue
            if (
                declared_stack_side in {"high", "low"}
                and component_side != ("upper" if declared_stack_side == "high" else "lower")
            ):
                continue
            group["components"].append(
                {
                    "name": name,
                    "price": price,
                    "priority": ACTIVE_LIQUIDITY_PRIORITY[name],
                    "side": component_side,
                }
            )

    groups: list[dict[str, Any]] = []
    for group in grouped.values():
        components = sorted(group["components"], key=lambda item: (item["priority"], item["name"]))
        if not components:
            continue
        prices = [component["price"] for component in components]
        low = min(prices)
        high = max(prices)
        side = components[0].get("side")
        close_boundary = low if side == "upper" else high if side == "lower" else None
        extreme_boundary = high if side == "upper" else low if side == "lower" else None
        if group.get("stack_group"):
            display_name = stack_display_name(components, side)
        else:
            display_name = components[0]["name"]
        groups.append(
            {
                "name": group.get("stack_group") or components[0]["name"],
                "display_name": display_name,
                "side": side,
                "stack_group": group.get("stack_group"),
                "close_boundary": close_boundary,
                "stack_extreme": extreme_boundary,
                "extreme_boundary": extreme_boundary,
                "wick_boundary_extreme": None,
                "components": [component["name"] for component in components],
                "prices": {component["name"]: component["price"] for component in components},
            }
        )
    return groups


def opposite_side_liquidity_breach_release(
    locked_owner: dict[str, Any] | None,
    tv_context: dict[str, Any] | None,
    current_candle: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return opposite-side breach details when a stale Step 2 owner should be released."""
    if not isinstance(locked_owner, dict) or not isinstance(current_candle, dict):
        return None

    active = locked_owner.get("active_liquidity") if isinstance(locked_owner.get("active_liquidity"), dict) else locked_owner
    owner_side = active.get("side") or side_for_level(str(active.get("name") or ""))
    close = optional_float(current_candle.get("close"))
    if owner_side not in {"lower", "upper"} or close is None:
        return None

    opposite_side = "upper" if owner_side == "lower" else "lower"
    breached: list[dict[str, Any]] = []
    for group in active_liquidity_groups_from_context(tv_context):
        if group.get("side") != opposite_side:
            continue
        boundary = optional_float(group.get("close_boundary"))
        if boundary is None:
            continue
        if opposite_side == "upper" and close >= boundary:
            breached.append(group)
        elif opposite_side == "lower" and close <= boundary:
            breached.append(group)

    if not breached:
        return None

    breached_group = min(
        breached,
        key=lambda item: (
            abs(close - optional_float(item.get("close_boundary"))),
            str(item.get("display_name") or item.get("name") or ""),
        ),
    )
    return {
        "reason_key": OPPOSITE_SIDE_LIQUIDITY_BREACH_RELEASE,
        "locked_side": owner_side,
        "breach_side": opposite_side,
        "breach_close": close,
        "breached_group": breached_group,
    }


def same_side_liquidity_owner_rotation_release(
    locked_owner: dict[str, Any] | None,
    next_selected_liquidity: dict[str, Any] | None,
    current_candle: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return release details when control rotates to the next same-side untouched liquidity."""
    if not isinstance(locked_owner, dict) or not isinstance(next_selected_liquidity, dict):
        return None
    active = locked_owner.get("active_liquidity") if isinstance(locked_owner.get("active_liquidity"), dict) else locked_owner
    if not isinstance(active, dict):
        return None
    if not reached_next_same_side_liquidity(active, next_selected_liquidity):
        return None
    return {
        "reason_key": SAME_SIDE_NEXT_LIQUIDITY_OWNER_ROTATION,
        "locked_side": active.get("side") or side_for_level(str(active.get("name") or "")),
        "breach_close": optional_float((current_candle or {}).get("close")),
        "released_group": ((active.get("group") or {}).get("display_name") if isinstance(active.get("group"), dict) else None) or active.get("display_name") or active.get("name"),
        "next_group": ((next_selected_liquidity.get("group") or {}).get("display_name") if isinstance(next_selected_liquidity.get("group"), dict) else None) or next_selected_liquidity.get("display_name") or next_selected_liquidity.get("name"),
        "next_liquidity": copy.deepcopy(next_selected_liquidity),
    }


def released_step2_lock_result(
    symbol_state: dict[str, Any],
    current_candle: dict[str, Any],
    tick_size: float,
    release: dict[str, Any],
) -> dict[str, Any]:
    """Return a cleared Step 2 state after opposite-side breach releases a stale owner."""
    persisted_candle_index = int(symbol_state.get("step_2_1a_candle_index") or 0)
    invalidated_at = datetime.now(timezone.utc).isoformat()
    step_state = {
        "step_2_activated": False,
        "blocked": False,
        "candle_a": None,
        "step2_activation_candle_index": None,
        "active_level": None,
        "level_price": None,
        "side": None,
        "tick_size": tick_size,
        "expiration_candles": 5,
        "pre_activation_probe_boundary": {
            "active": False,
            "side": None,
            "source_level": None,
            "boundary_price": None,
            "detected_at_index": None,
        },
        "events": [
        {
            "event": "step2_locked_owner_released",
            "reason": release["reason_key"],
            "locked_side": release.get("locked_side"),
            "breach_side": release.get("breach_side"),
            "breach_close": release.get("breach_close"),
            "breached_group": (release.get("breached_group") or {}).get("display_name"),
            "released_group": release.get("released_group"),
            "next_group": release.get("next_group"),
        }
        ],
        "available": True,
        "reason": release["reason_key"],
        "state_transition_reason": release["reason_key"],
        "step2_invalidated_at": invalidated_at,
        "last_evaluated_bar_time": candle_timestamp(current_candle),
        "candle_index": persisted_candle_index,
        "next_candle_index": persisted_candle_index + 1,
        "audit_step2_before_active": True,
        "audit_step2_event": "opposite_side_liquidity_breach_release",
        "active_liquidity_group": None,
        "last_interacted_liquidity": None,
        "step2_locked_owner": None,
        "consumed_liquidity_levels": list(consumed_liquidity_levels(symbol_state)),
    }
    return step_state


def step2_owner_rotation_released(
    step_state: dict[str, Any] | None,
    symbol: str | None = None,
) -> bool:
    """Return True when Step 2 released a prior lifecycle owner."""
    if not isinstance(step_state, dict):
        return False
    release_reasons = {SAME_SIDE_NEXT_LIQUIDITY_OWNER_ROTATION}
    if root_symbol(symbol) == "NQ" and step_state.get("same_candle_owner_handoff") is True:
        release_reasons.add(OPPOSITE_SIDE_LIQUIDITY_BREACH_RELEASE)
    if step_state.get("state_transition_reason") in release_reasons:
        return True
    events = step_state.get("events")
    if not isinstance(events, list):
        return False
    return any(
        isinstance(event, dict)
        and event.get("event") == "step2_locked_owner_released"
        and event.get("reason") in release_reasons
        for event in events
    )


def reset_symbol_state_for_owner_rotation(
    symbol_state: dict[str, Any],
    step2_state: dict[str, Any],
) -> dict[str, Any]:
    """Clear stale downstream lifecycle state once ownership rotates to a new liquidity."""
    reset_state = dict(symbol_state or {})
    reset_state["step_2_1a"] = dict(step2_state or {})
    reset_state["step2_locked_owner"] = None
    reset_state["rejection"] = {}
    reset_state["step25"] = {}
    reset_state["step3"] = {}
    reset_state["step4"] = {}
    reset_state["step5"] = {}
    reset_state["step6"] = {}
    reset_state["rejection_lane"] = {}
    reset_state["continuation_lane"] = {}
    reset_state["gateway"] = {}
    reset_state["last_interacted_liquidity"] = step2_state.get("last_interacted_liquidity")
    reset_state["consumed_liquidity_levels"] = list(
        step2_state.get("consumed_liquidity_levels")
        if isinstance(step2_state.get("consumed_liquidity_levels"), list)
        else consumed_liquidity_levels(symbol_state)
    )
    return reset_state


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
    next_same_side_liquidity = (
        copy.deepcopy(step_state.get("next_same_side_liquidity"))
        if isinstance(step_state.get("next_same_side_liquidity"), dict)
        else None
    )
    rejection_boundary = public_rejection_boundary(
        group,
        (group or {}).get("wick_boundary_extreme") if isinstance(group, dict) else None,
        (group or {}).get("extreme_boundary") if isinstance(group, dict) else None,
        active_price,
        step2_activated=True,
        probe_boundary=((step_state.get("pre_activation_probe_boundary") or {}).get("boundary_price") if isinstance(step_state.get("pre_activation_probe_boundary"), dict) else None),
    )
    step2_step4_50_line = None
    if next_same_side_liquidity is not None:
        next_price = optional_float(next_same_side_liquidity.get("price"))
        if next_price is not None and next_price != active_price:
            step2_step4_50_line = (float(active_price) + next_price) / 2.0
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
        "stack_extreme": (group or {}).get("stack_extreme") if isinstance(group, dict) else None,
        "extreme_boundary": (group or {}).get("extreme_boundary") if isinstance(group, dict) else None,
        "wick_boundary_extreme": (group or {}).get("wick_boundary_extreme") if isinstance(group, dict) else None,
        "setup_direction": setup_direction,
        "side": side,
        "candle_a": step_state.get("candle_a"),
        "owner_seeded_at": (
            step_state.get("step2_owner_seeded_at")
            or candle_timestamp(step_state.get("candle_a") if isinstance(step_state.get("candle_a"), dict) else None)
            or step_state.get("last_evaluated_bar_time")
        ),
        "activated_at": candle_timestamp(step_state.get("candle_a") if isinstance(step_state.get("candle_a"), dict) else None) or step_state.get("last_evaluated_bar_time"),
        "step2_activation_candle_index": step_state.get("step2_activation_candle_index"),
        "next_same_side_liquidity": next_same_side_liquidity,
        "rejection_boundary": rejection_boundary,
        "step2_step4_50_line": step2_step4_50_line,
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
    if not same_liquidity_owner(previous_liquidity, selected_liquidity):
        return None

    candle_a = step25_state.get("initial_candle_a") if isinstance(step25_state.get("initial_candle_a"), dict) else None
    if candle_a is None:
        candle_a = step4_state.get("initial_candle_a") if isinstance(step4_state.get("initial_candle_a"), dict) else None
    activated_at = candle_timestamp(candle_a) or step4_state.get("leg1_window_started_at")
    if not activated_at:
        return None

    preserved_liquidity = previous_liquidity if isinstance(previous_liquidity, dict) else selected_liquidity
    side = preserved_liquidity.get("side") or selected_liquidity.get("side") or side_for_level(str(preserved_liquidity.get("name") or ""))
    group = preserved_liquidity.get("group") if isinstance(preserved_liquidity.get("group"), dict) else selected_liquidity.get("group")
    display_name = preserved_liquidity.get("display_name") or selected_liquidity.get("display_name")
    if not display_name and isinstance(group, dict):
        display_name = group.get("display_name")
    active = {
        "name": preserved_liquidity.get("name"),
        "price": preserved_liquidity.get("price"),
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
        "stack_extreme": (group or {}).get("stack_extreme") if isinstance(group, dict) else None,
        "extreme_boundary": (group or {}).get("extreme_boundary") if isinstance(group, dict) else None,
        "wick_boundary_extreme": (group or {}).get("wick_boundary_extreme") if isinstance(group, dict) else None,
        "setup_direction": "SHORT" if side == "upper" else "LONG" if side == "lower" else step4_state.get("setup_direction"),
        "side": side,
        "candle_a": candle_a,
        "activated_at": activated_at,
        "step2_activation_candle_index": ((persisted_state.get("step_2_1a") or {}).get("step2_activation_candle_index") if isinstance(persisted_state.get("step_2_1a"), dict) else None),
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


@entry_state_transaction
def record_consumed_entry_setup(symbol: str, signature: dict[str, Any], reason: str) -> None:
    """Persist consumed setup context without changing execution state."""
    require_authoritative_mutation("record_consumed_entry_setup")
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


def consumed_entry_setup_projection(
    snapshot: dict[str, Any],
) -> tuple[str, dict[str, Any], bool, bool] | None:
    """Read consumed/submitted evidence for one projected Entry Agent setup."""
    step6 = snapshot.get("step6") if isinstance(snapshot.get("step6"), dict) else {}
    if decision_status(step6) != "CONFIRM":
        return None
    signature = entry_setup_signature(snapshot)
    if not signature:
        return None
    symbol_key = str(snapshot.get("normalized_symbol") or root_symbol(str(snapshot.get("requested_symbol") or snapshot.get("symbol") or ""))).upper()
    persisted_state = load_entry_state()
    symbol_state = symbol_scoped_persisted_state(persisted_state, symbol_key)
    consumed = setup_signature_consumed(symbol_state, signature)
    submitted = submitted_trade_exists_after_setup(symbol_key, signature)
    return symbol_key, signature, consumed, submitted


def record_submitted_entry_setup(snapshot: dict[str, Any]) -> None:
    """Record submitted-setup consumption during an authorized event transaction."""
    require_authoritative_mutation("record_submitted_entry_setup")
    projection = consumed_entry_setup_projection(snapshot)
    if not projection:
        return
    symbol_key, signature, consumed, submitted = projection
    if submitted and not consumed:
        record_consumed_entry_setup(
            symbol_key,
            signature,
            "Submitted trade consumed this Entry Agent setup context.",
        )


def apply_consumed_entry_setup_projection_guard(snapshot: dict[str, Any]) -> None:
    """Suppress duplicate CONFIRM in memory without mutating consumed authority."""
    projection = consumed_entry_setup_projection(snapshot)
    if not projection:
        return
    _symbol_key, signature, consumed, submitted = projection
    if not consumed and not submitted:
        return
    step6 = snapshot.get("step6") if isinstance(snapshot.get("step6"), dict) else {}
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


def stack_group_with_dynamic_wick_boundary(
    group: dict[str, Any] | None,
    candle: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return stack group with wick boundary updated from the farthest wick beyond the original extreme."""
    if not isinstance(group, dict) or not isinstance(candle, dict):
        return group
    high = optional_float(candle.get("high"))
    low = optional_float(candle.get("low"))
    side = str(group.get("side") or "")
    if side == "lower":
        return group_with_wick_boundary_candidate(group, low)
    if side == "upper":
        return group_with_wick_boundary_candidate(group, high)
    return group


def merge_monotonic_stack_extreme(
    current_group: dict[str, Any] | None,
    persisted_group: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Backward-compatible wrapper for monotonic wick-boundary preservation."""
    return merge_monotonic_stack_wick_boundary(current_group, persisted_group)


def evaluate_live_step_2_1a(
    snapshot: dict[str, Any],
    _levels: dict[str, Any],
    liquidity: dict[str, Any],
    persisted_state: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate live Step 2.1A by calling the replay evaluator directly."""
    symbol_key = str(snapshot.get("normalized_symbol") or snapshot.get("symbol") or "")
    locked_tv_context = snapshot.get("tv_context")
    observed_extreme = pre_open_observed_extreme(persisted_state, symbol_key)
    symbol_state = symbol_scoped_persisted_state(persisted_state, symbol_key)
    persisted_candle_index = int(symbol_state.get("step_2_1a_candle_index") or 0)
    selected_liquidity = None
    current_candle = build_current_candle(snapshot)
    previous_liquidity = persisted_liquidity_candidate(persisted_state, symbol_key)
    step2_locked_liquidity = locked_step2_active_liquidity(symbol_state)
    locked_liquidity = locked_leg1_active_liquidity(symbol_state)
    reserved_candle_b = active_step4_candle_b_reservation(symbol_state, current_candle)
    tick_size = float(liquidity.get("tick_size") or 0.25)
    consumed_levels = list(consumed_liquidity_levels(symbol_state))
    next_selected_liquidity = None
    if candle_close_confirmed(snapshot):
        next_selected_liquidity = selected_active_liquidity_from_context(
            locked_tv_context,
            snapshot.get("latest_price"),
            snapshot.get("ohlc") if isinstance(snapshot.get("ohlc"), dict) else None,
            tick_size,
        )
        if not next_selected_liquidity:
            next_selected_liquidity = rotated_active_liquidity_after_inactive_acceptance(
                locked_tv_context,
                previous_liquidity,
                snapshot.get("ohlc") if isinstance(snapshot.get("ohlc"), dict) else None,
            )
    if not isinstance(previous_liquidity, dict):
        nested_step2 = symbol_state.get("step_2_1a") if isinstance(symbol_state.get("step_2_1a"), dict) else {}
        previous_liquidity = (
            nested_step2.get("last_interacted_liquidity")
            if isinstance(nested_step2.get("last_interacted_liquidity"), dict)
            else symbol_state.get("last_interacted_liquidity")
            if isinstance(symbol_state.get("last_interacted_liquidity"), dict)
            else step2_locked_liquidity
        )
    released_for_owner_rotation = None
    locked_owner_for_rotation = locked_step2_owner(symbol_state)
    locked_active_for_rotation = (
        locked_liquidity
        if isinstance(locked_liquidity, dict)
        else step2_locked_liquidity
        if isinstance(step2_locked_liquidity, dict)
        else None
    )
    if (
        isinstance(step2_locked_liquidity, dict)
        and not isinstance(locked_liquidity, dict)
        and reserved_candle_b is None
    ):
        release = opposite_side_liquidity_breach_release(
            locked_owner_for_rotation,
            locked_tv_context,
            current_candle,
        )
        if release:
            return released_step2_lock_result(symbol_state, current_candle, tick_size, release)
    if (
        root_symbol(symbol_key) == "NQ"
        and isinstance(locked_owner_for_rotation, dict)
        and isinstance(locked_liquidity, dict)
        and isinstance(locked_active_for_rotation, dict)
        and isinstance(next_selected_liquidity, dict)
        and reserved_candle_b is None
    ):
        release = opposite_side_liquidity_breach_release(
            locked_owner_for_rotation,
            locked_tv_context,
            current_candle,
        )
        if release:
            breached_group = release.get("breached_group") if isinstance(release.get("breached_group"), dict) else {}
            selected_group = next_selected_liquidity.get("group") if isinstance(next_selected_liquidity.get("group"), dict) else {}
            if (
                release.get("breach_side") == "lower"
                and len(breached_group.get("components") or []) >= 2
                and (
                    selected_group.get("name") == breached_group.get("name")
                    or selected_group.get("display_name") == breached_group.get("display_name")
                )
            ):
                release["released_group"] = (
                    ((locked_active_for_rotation.get("group") or {}).get("display_name"))
                    if isinstance(locked_active_for_rotation.get("group"), dict)
                    else None
                ) or locked_active_for_rotation.get("display_name") or locked_active_for_rotation.get("name")
                release["next_group"] = breached_group.get("display_name") or breached_group.get("name")
                release["next_liquidity"] = copy.deepcopy(next_selected_liquidity)
                released_for_owner_rotation = release
                previous_liquidity = locked_active_for_rotation
                released_state = released_step2_lock_result(
                    symbol_state,
                    current_candle,
                    tick_size,
                    release,
                )
                symbol_state = reset_symbol_state_for_owner_rotation(symbol_state, released_state)
                step2_locked_liquidity = None
                locked_liquidity = None
                locked_owner_for_rotation = None
    if (
        isinstance(locked_owner_for_rotation, dict)
        and isinstance(locked_active_for_rotation, dict)
        and isinstance(next_selected_liquidity, dict)
        and reserved_candle_b is None
    ):
        release = same_side_liquidity_owner_rotation_release(
            locked_owner_for_rotation,
            next_selected_liquidity,
            current_candle,
        )
        if release:
            released_for_owner_rotation = release
            previous_liquidity = locked_active_for_rotation
            step2_locked_liquidity = None
            locked_liquidity = None
    if isinstance(locked_liquidity, dict):
        selected_liquidity = locked_liquidity
        previous_liquidity = locked_liquidity
    elif isinstance(step2_locked_liquidity, dict):
        selected_liquidity = step2_locked_liquidity
        previous_liquidity = step2_locked_liquidity
    elif isinstance((reserved_candle_b or {}).get("active_liquidity"), dict):
        selected_liquidity = reserved_candle_b["active_liquidity"]
        previous_liquidity = reserved_candle_b["active_liquidity"]
    elif candle_close_confirmed(snapshot):
        selected_liquidity = next_selected_liquidity
        if not selected_liquidity:
            selected_liquidity = rotated_active_liquidity_after_inactive_acceptance(
                locked_tv_context,
                previous_liquidity,
                snapshot.get("ohlc") if isinstance(snapshot.get("ohlc"), dict) else None,
            )
    threshold_record, threshold_target = threshold_liquidity_exhaustion(
        symbol_state,
        previous_liquidity,
        locked_tv_context,
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
    pending_owner_liquidity = pending_step2_owner_liquidity(
        symbol_state,
        locked_tv_context,
        current_candle,
        next_selected_liquidity=selected_liquidity or next_selected_liquidity,
        threshold_record=threshold_record,
        consumed_levels=consumed_levels,
    )
    if not isinstance(locked_liquidity, dict) and not isinstance(step2_locked_liquidity, dict) and not isinstance((reserved_candle_b or {}).get("active_liquidity"), dict) and isinstance(pending_owner_liquidity, dict):
        selected_liquidity = pending_owner_liquidity
        previous_liquidity = pending_owner_liquidity
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
    locked_owner_before = locked_step2_owner(symbol_state)
    locked_active_before = (
        locked_owner_before.get("active_liquidity")
        if isinstance(locked_owner_before, dict) and isinstance(locked_owner_before.get("active_liquidity"), dict)
        else None
    )
    active_level = selected_liquidity.get("name") if selected_liquidity else None
    level_price = selected_liquidity.get("price") if selected_liquidity else None
    if not selected_liquidity:
        pending_liquidity = pending_leg1_window_liquidity(symbol_state, current_candle)
        if pending_liquidity and persisted_liquidity_matches_context(pending_liquidity, locked_tv_context, symbol_key):
            active_level = pending_liquidity.get("name")
            level_price = pending_liquidity.get("price")
            selected_liquidity = pending_liquidity
    if not selected_liquidity:
        pending_probe_liquidity = pending_step2_probe_liquidity(symbol_state, locked_tv_context)
        if pending_probe_liquidity and persisted_liquidity_matches_context(pending_probe_liquidity, locked_tv_context, symbol_key):
            active_level = pending_probe_liquidity.get("name")
            level_price = pending_probe_liquidity.get("price")
            selected_liquidity = pending_probe_liquidity
    if not selected_liquidity:
        persisted_liquidity = persisted_active_liquidity(persisted_state, symbol_key, locked_tv_context)
        if persisted_liquidity and not (
            current_candle_supports_persisted_liquidity(
                persisted_liquidity,
                locked_tv_context,
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
    if not selected_liquidity and isinstance(locked_active_before, dict):
        active_level = locked_active_before.get("name")
        level_price = locked_active_before.get("price")
        selected_liquidity = locked_active_before
    if isinstance(selected_liquidity, dict) and isinstance(observed_extreme, dict):
        if selected_liquidity_matches_pre_open_extreme(selected_liquidity, observed_extreme):
            selected_liquidity = dict(selected_liquidity)
            selected_liquidity["pre_open_observed_extreme"] = observed_extreme
            if isinstance(selected_liquidity.get("group"), dict):
                selected_liquidity["group"] = stack_group_with_pre_open_wick_boundary(selected_liquidity.get("group"), observed_extreme)
    side = (
        selected_liquidity.get("side")
        if isinstance(selected_liquidity, dict)
        else None
    ) or side_for_level(
        active_level,
        level_price,
        stack_reference_price_from_context(locked_tv_context),
    )
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
        selected_liquidity=selected_liquidity,
    )
    seed_step2_probe_from_pre_open_extreme(
        step_state,
        selected_liquidity.get("pre_open_observed_extreme") if isinstance(selected_liquidity, dict) else None,
        persisted_candle_index,
    )
    pre_confirmation_target = next_same_side_liquidity_target(locked_tv_context, selected_liquidity)
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
        step_state["step2_owner_seeded_at"] = (
            recovered_locked_owner.get("owner_seeded_at")
            or step_state.get("step2_owner_seeded_at")
            or candle_timestamp(owner_candle)
            or candle.get("timestamp")
        )
        step_state["step2_activated_at"] = (
            recovered_locked_owner.get("activated_at")
            or step_state.get("step2_activated_at")
            or candle_timestamp(owner_candle)
            or candle.get("timestamp")
        )
        step_state["step2_invalidated_at"] = None
        step_state["step2_activation_candle_index"] = (
            recovered_locked_owner.get("step2_activation_candle_index")
            if recovered_locked_owner.get("step2_activation_candle_index") is not None
            else step_state.get("step2_activation_candle_index")
        )
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
        step_state["audit_step2_before_active"] = True
        step_state["audit_step2_event"] = "already_active"
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
    restore_pending_step2_probe_owner(step_state)
    if isinstance(released_for_owner_rotation, dict):
        step_state["events"] = [
            {
                "event": "step2_locked_owner_released",
                "reason": released_for_owner_rotation["reason_key"],
                "locked_side": released_for_owner_rotation.get("locked_side"),
                "breach_close": released_for_owner_rotation.get("breach_close"),
                "released_group": released_for_owner_rotation.get("released_group"),
                "next_group": released_for_owner_rotation.get("next_group"),
            }
        ]
        step_state["state_transition_reason"] = released_for_owner_rotation["reason_key"]
        if released_for_owner_rotation.get("reason_key") == OPPOSITE_SIDE_LIQUIDITY_BREACH_RELEASE:
            step_state["same_candle_owner_handoff"] = True
    step2_before_active = bool(step_state.get("step_2_activated"))
    event_count_before = len(step_state.get("events") or [])
    evaluate_step_2_1a_candle(step_state, candle, candle_index)
    step_state["available"] = True
    step_state["reason"] = "Step 2.1A evaluated from live completed candle."
    step_state["last_evaluated_bar_time"] = candle["timestamp"]
    step_state["candle_index"] = candle_index
    step_state["next_candle_index"] = candle_index + 1
    step2_after_active = bool(step_state.get("step_2_activated"))
    if not step2_before_active and step2_after_active:
        step_state["step2_activation_candle_index"] = candle_index
        step_state["step2_owner_seeded_at"] = step_state.get("step2_owner_seeded_at") or candle["timestamp"]
        step_state["step2_activated_at"] = step_state.get("step2_activated_at") or candle["timestamp"]
        step_state["step2_invalidated_at"] = None
    new_events = list(step_state.get("events") or [])[event_count_before:]
    step_state["audit_step2_before_active"] = step2_before_active
    step_state["audit_step2_event"] = latest_event_name(new_events) or ("already_active" if step2_before_active and step2_after_active else "")
    selected_group = selected_liquidity.get("group") if selected_liquidity else None
    persisted_group = None
    if isinstance(step_state.get("active_liquidity_group"), dict):
        persisted_group = step_state.get("active_liquidity_group")
    elif isinstance(previous_liquidity, dict) and isinstance(previous_liquidity.get("group"), dict):
        persisted_group = previous_liquidity.get("group")
    selected_group = merge_monotonic_stack_extreme(selected_group, persisted_group)
    selected_group = stack_group_with_dynamic_wick_boundary(selected_group, candle)
    selected_group = stack_group_with_pending_probe_boundary(selected_group, step_state)
    if selected_liquidity and isinstance(selected_group, dict):
        selected_liquidity = {**selected_liquidity, "group": selected_group}
    step_state["active_liquidity_group"] = selected_group
    rotated_same_side_target = (
        not lifecycle_locked
        and isinstance(previous_liquidity, dict)
        and isinstance(selected_liquidity, dict)
        and reached_next_same_side_liquidity(previous_liquidity, selected_liquidity)
    )
    if not lifecycle_locked and ((not step2_before_active and step2_after_active) or rotated_same_side_target):
        consumed_levels = merge_consumed_liquidity_levels(
            consumed_levels,
            record_exhausted_liquidity(
                symbol_state_with_consumed,
                previous_liquidity,
                selected_liquidity,
                current_candle,
                snapshot.get("tv_context"),
            ),
        )
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
        or persisted_active_liquidity(persisted_state, symbol_key, locked_tv_context)
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
    step_state["pending_step2_owner"] = (
        None if step_state.get("step_2_activated") is True else build_pending_step2_owner(step_state, selected_liquidity)
    )
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
        state.get("step4_confirmed_at"),
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


def active_liquidity_group_signature(liquidity: Any) -> tuple[Any, Any, Any, Any] | None:
    if not isinstance(liquidity, dict):
        return None
    group = liquidity.get("group") if isinstance(liquidity.get("group"), dict) else None
    if not isinstance(group, dict):
        return None
    return (
        group.get("name"),
        optional_float(group.get("close_boundary")),
        optional_float(group.get("extreme_boundary")),
        group.get("side") or liquidity.get("side"),
    )


def same_liquidity_owner(left: Any, right: Any) -> bool:
    """Return True when two liquidity records belong to the same frozen owner."""
    if same_active_liquidity(left, right):
        return True
    left_signature = active_liquidity_group_signature(left)
    right_signature = active_liquidity_group_signature(right)
    return bool(left_signature and right_signature and left_signature == right_signature)


def liquidity_owner_signature(
    liquidity_name: Any,
    liquidity_price: Any,
    liquidity_group: dict[str, Any] | None,
) -> tuple[Any, float | None, Any, float | None, Any]:
    """Return the stable owner signature used for continuation/rejection identity checks."""
    return (
        str(liquidity_name or "").strip() or None,
        optional_float(liquidity_price),
        (liquidity_group or {}).get("name") if isinstance(liquidity_group, dict) else None,
        optional_float((liquidity_group or {}).get("extreme_boundary")) if isinstance(liquidity_group, dict) else None,
        (liquidity_group or {}).get("side") if isinstance(liquidity_group, dict) else None,
    )


def trade_state_owner_liquidity(trade_state: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a normalized liquidity owner from frozen trade-state fields."""
    trade_state = trade_state if isinstance(trade_state, dict) else {}
    group = trade_state.get("active_liquidity_group") if isinstance(trade_state.get("active_liquidity_group"), dict) else None
    name = trade_state.get("selected_liquidity_name") or trade_state.get("active_liquidity_name")
    price = optional_float(trade_state.get("active_liquidity_price"))
    if not valid_active_liquidity_selection(name, price) and not isinstance(group, dict):
        return None
    return {
        "name": name,
        "price": price,
        "group": group,
        "side": (group or {}).get("side") if isinstance(group, dict) else None,
        "display_name": trade_state.get("owner") or trade_state.get("active_liquidity_name"),
    }


def step2_state_matches_selected_owner(
    step_state: dict[str, Any],
    selected_liquidity: dict[str, Any] | None,
) -> bool:
    if not isinstance(step_state, dict) or not isinstance(selected_liquidity, dict):
        return False
    locked_owner = step_state.get("step2_locked_owner") if isinstance(step_state.get("step2_locked_owner"), dict) else {}
    locked_active = locked_owner.get("active_liquidity") if isinstance(locked_owner.get("active_liquidity"), dict) else None
    if same_liquidity_owner(locked_active, selected_liquidity):
        return True
    last_interacted = step_state.get("last_interacted_liquidity") if isinstance(step_state.get("last_interacted_liquidity"), dict) else None
    if same_liquidity_owner(last_interacted, selected_liquidity):
        return True
    current_state_liquidity = {
        "name": step_state.get("active_level"),
        "price": step_state.get("level_price"),
        "side": step_state.get("side"),
        "group": step_state.get("active_liquidity_group") if isinstance(step_state.get("active_liquidity_group"), dict) else None,
    }
    return same_liquidity_owner(current_state_liquidity, selected_liquidity)


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
    if state.get("step5_close_boundary") is None and state.get("leg1_reference_price") is None and state.get("leg1_reference") is None:
        return False, "Waiting for valid locked Leg 1 reference"
    if not state.get("step4_confirmed_at") and not state.get("leg1_reference_candle_time"):
        return False, "Waiting for valid locked Leg 1 reference"
    if state.get("leg1_direction") not in ("LONG", "SHORT") and state.get("setup_direction") not in ("LONG", "SHORT"):
        return False, "Waiting for valid locked Leg 1 reference"
    if not isinstance(state.get("active_liquidity"), dict):
        return False, "Waiting for valid locked Leg 1 reference"
    if not state.get("step4_confirmed_at") and not state.get("leg1_completed_at"):
        return False, "Waiting for valid locked Leg 1 reference"
    sequence_started_at = current_sequence_started_at or state.get("current_active_sequence_started_at")
    if (
        sequence_started_at
        and not candle_is_after({"timestamp": state.get("step4_confirmed_at") or state.get("leg1_completed_at")}, sequence_started_at)
        and not same_candle_time(state.get("step4_confirmed_at") or state.get("leg1_completed_at"), sequence_started_at)
    ):
        return False, "Waiting for valid locked Leg 1 reference"
    if current_active_liquidity is not None and not same_liquidity_owner(state.get("active_liquidity"), current_active_liquidity):
        return False, "Waiting for valid locked Leg 1 reference"
    return True, None


def valid_participation_locked_leg1_state(
    state: dict[str, Any],
    current_active_liquidity: dict[str, Any] | None = None,
    current_sequence_started_at: Any = None,
) -> tuple[bool, str | None]:
    """Validate locked Step 4 structure and require a distinct future Leg 2 candidate."""
    locked_ok, reason = valid_locked_leg1_state(state, current_active_liquidity, current_sequence_started_at)
    if not locked_ok:
        return False, reason
    if not state.get("step4_confirmed_at") and not state.get("leg1_completed_at"):
        return False, "Waiting for valid Step 4 confirmation"
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


PERMANENT_CONSUMED_LIQUIDITY_TYPES = {
    "next_liquidity_reached",
    "same_side_next_liquidity_reached",
    "no_leg1_50_percent_exhaustion",
    "leg1_no_leg2_25_percent_exhaustion",
    "step2_step4_50_percent_invalidation",
    "step4_step5_75_percent_invalidation",
}


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


def invalidation_consumed_liquidity_record(
    active_liquidity: dict[str, Any] | None,
    *,
    reason: Any,
    exhaustion_type: str,
    invalidation_source: str,
    invalidation_source_step: str,
    source_candle_time: Any,
    invalidated_at: Any = None,
) -> dict[str, Any] | None:
    """Build a permanent consumed-liquidity record for lifecycle invalidation."""
    active_liquidity = active_liquidity if isinstance(active_liquidity, dict) else {}
    key = liquidity_key(active_liquidity.get("name"), active_liquidity.get("price"))
    if not key:
        return None
    return {
        "key": key,
        "name": active_liquidity.get("name"),
        "price": active_liquidity.get("price"),
        "side": active_liquidity.get("side") or side_for_level(str(active_liquidity.get("name") or "")),
        "exhaustion_type": exhaustion_type,
        "invalidated_at": invalidated_at or datetime.now(timezone.utc).isoformat(),
        "invalidation_source": invalidation_source,
        "invalidation_source_step": invalidation_source_step,
        "invalidation_source_candle_time": source_candle_time,
        "exhausted_at_candle_time": source_candle_time,
        "reason": reason,
    }


def liquidity_level_consumed(
    persisted_state: dict[str, Any],
    name: Any,
    price: Any,
) -> bool:
    """Return True when the liquidity level has a permanent consumed record."""
    key = liquidity_key(name, price)
    if not key:
        return False
    for record in consumed_liquidity_levels(persisted_state):
        if not isinstance(record, dict):
            continue
        record_key = record.get("key") or liquidity_key(record.get("name"), record.get("price"))
        if record_key != key:
            continue
        if record.get("exhaustion_type") in PERMANENT_CONSUMED_LIQUIDITY_TYPES:
            return True
    return False


def consumed_liquidity_blocks(
    persisted_state: dict[str, Any],
    name: Any,
    price: Any,
    current_candle: dict[str, Any] | None,
) -> bool:
    """Block reactivation from the same candle sequence after invalidation."""
    key = liquidity_key(name, price)
    current_time = candle_timestamp(current_candle)
    if not key:
        return False
    for record in consumed_liquidity_levels(persisted_state):
        if not isinstance(record, dict):
            continue
        record_key = record.get("key") or liquidity_key(record.get("name"), record.get("price"))
        if record_key == key and record.get("exhaustion_type") in PERMANENT_CONSUMED_LIQUIDITY_TYPES:
            return True
        source_time = record.get("invalidation_source_candle_time")
        if record_key == key and current_time and source_time and current_time <= str(source_time):
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
    previous_price = optional_float(previous.get("price"))
    session_reference_price = stack_reference_price_from_context(tv_context)
    previous_side = previous.get("side") or side_for_level(
        previous_name,
        previous_price,
        session_reference_price,
    )
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
        price = optional_float(details.get("price"))
        if price is None:
            continue
        if side_for_level(name, price, session_reference_price) != previous_side:
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
    context_symbol = root_symbol(
        str(tv_context.get("normalized_symbol") or tv_context.get("symbol") or "")
    )
    if context_symbol == "NQ":
        selected = min(candidates, key=lambda item: (item["distance"], item["priority"], item["name"]))
    else:
        selected = min(candidates, key=lambda item: (item["priority"], item["distance"], item["name"]))
    return {
        "name": selected["name"],
        "price": selected["price"],
        "side": selected["side"],
        "group": active_stack_from_context(tv_context, str(selected["name"])),
    }


def step4_participation_line_payload(
    snapshot: dict[str, Any],
    step_2_1a: dict[str, Any],
    step4_state: dict[str, Any],
    *,
    rejection_active: bool,
    selected_pathway: str | None,
    setup_direction: str | None,
    leg1_published: bool,
    invalidated: bool,
) -> dict[str, Any]:
    """Return frozen-table invalidation lines from active liquidity extreme to next same-side close level."""
    step2_window_terminated = step2_lifecycle_window_terminated(snapshot, step_2_1a, {"state": step4_state} if isinstance(step4_state, dict) else {})
    locked_owner = step_2_1a.get("step2_locked_owner") if isinstance(step_2_1a.get("step2_locked_owner"), dict) else {}
    active_liquidity = step4_state.get("active_liquidity") if isinstance(step4_state.get("active_liquidity"), dict) else None
    if step2_window_terminated:
        active_liquidity = None
    if not active_liquidity:
        locked_active = locked_owner.get("active_liquidity") if isinstance(locked_owner.get("active_liquidity"), dict) else None
        active_liquidity = None if step2_window_terminated else locked_active
    if not active_liquidity:
        if not step2_window_terminated:
            step2_level = str(step_2_1a.get("active_level") or locked_owner.get("active_liquidity_name") or "").strip()
            step2_price = (
                optional_float(step_2_1a.get("level_price"))
                or optional_float(locked_owner.get("close_boundary"))
                or optional_float(locked_owner.get("extreme_boundary"))
            )
            step2_side = step_2_1a.get("side") or locked_owner.get("side") or side_for_level(step2_level)
            if step2_level and step2_price is not None and step2_side in {"lower", "upper"}:
                active_liquidity = {"name": step2_level, "price": step2_price, "side": step2_side}
    if not active_liquidity:
        active_name, active_price = active_liquidity_from_snapshot(snapshot)
        active_liquidity = {"name": active_name, "price": active_price, "side": side_for_level(str(active_name or ""))}

    active_price = optional_float(active_liquidity.get("price") if isinstance(active_liquidity, dict) else None)
    active_side = active_liquidity.get("side") if isinstance(active_liquidity, dict) else None
    active_side = active_side if active_side in {"lower", "upper"} else side_for_level(str((active_liquidity or {}).get("name") or ""))

    reference = step4_state.get("next_break_side_liquidity") if isinstance(step4_state.get("next_break_side_liquidity"), dict) else None
    if step2_window_terminated:
        reference = None
    if not reference:
        reference = None if step2_window_terminated else (step_2_1a.get("next_same_side_liquidity") if isinstance(step_2_1a.get("next_same_side_liquidity"), dict) else None)
    if not reference and isinstance(active_liquidity, dict):
        reference = next_same_side_liquidity_target(snapshot.get("tv_context"), active_liquidity)
    reference_price = optional_float(reference.get("price") if isinstance(reference, dict) else None)

    line_50 = optional_float(step4_state.get("step2_step4_50_line")) if isinstance(step4_state, dict) else None
    line_75 = optional_float(step4_state.get("step4_step5_75_line")) if isinstance(step4_state, dict) else None
    if line_50 is None and active_price is not None and reference_price is not None and active_price != reference_price:
        line_50 = active_price + ((reference_price - active_price) * 0.50)
    if line_75 is None and active_price is not None and reference_price is not None and active_price != reference_price:
        line_75 = active_price + ((reference_price - active_price) * 0.75)

    terminal_window = (
        step4_state.get("leg1_window_invalidated") is True
        or step4_state.get("leg1_window_remaining") == 0
    )
    visible = (
        line_50 is not None
        and line_75 is not None
        and rejection_active
        and selected_pathway == "rejection"
        and setup_direction in {"LONG", "SHORT"}
        and not leg1_published
        and not invalidated
        and step4_state.get("leg1_status") != "COMPLETE"
        and step4_state.get("leg1_state_locked") is not True
        and step4_state.get("leg1_window_active") is True
        and not terminal_window
    )

    return {
        "reference_liquidity": reference,
        "active_liquidity": active_liquidity if isinstance(active_liquidity, dict) else None,
        "active_side": active_side,
        "line_50": line_50,
        "line_75": line_75,
        "visible": visible,
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
    if has_valid_leg1_without_valid_leg2(persisted_state):
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
    tv_context: dict[str, Any] | None = None,
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

    session_reference_price = stack_reference_price_from_context(tv_context)
    previous_side = previous.get("side") or side_for_level(
        str(previous.get("name") or ""),
        previous.get("price"),
        session_reference_price,
    )
    previous_group = previous.get("group") if isinstance(previous.get("group"), dict) else active_stack_from_context(tv_context, str(previous.get("name") or ""))
    selected_group = selected.get("group") if isinstance(selected.get("group"), dict) else active_stack_from_context(tv_context, str(selected.get("name") or ""))
    selected_component_names = set()
    if isinstance(selected_group, dict):
        selected_name = str(selected.get("name") or "")
        group_components = set(selected_group.get("components") or [])
        if selected_name and selected_name in group_components:
            selected_component_names = group_components
    previous_prices = []
    if isinstance(previous_group, dict):
        price_map = previous_group.get("prices")
        if isinstance(price_map, dict):
            previous_prices.extend(
                price
                for price in (
                    optional_float(component_price)
                    for component_price in price_map.values()
                )
                if price is not None
            )
    previous_price = optional_float(previous.get("price"))
    if previous_price is not None:
        previous_prices.append(previous_price)
    selected_price = optional_float(selected.get("price"))
    if previous_side not in {"lower", "upper"} or not previous_prices or selected_price is None:
        return consumed

    lower_bound = min(previous_prices)
    upper_bound = max(previous_prices)
    crossed_levels: list[tuple[str, float]] = []
    if isinstance(tv_context, dict) and isinstance(tv_context.get("levels"), dict):
        for name, details in tv_context["levels"].items():
            if name not in ACTIVE_LIQUIDITY_PRIORITY or not isinstance(details, dict):
                continue
            if str(details.get("status") or "").upper() != "ACTIVE":
                continue
            if name in selected_component_names:
                continue
            level_price = optional_float(details.get("price"))
            if level_price is None:
                continue
            if side_for_level(name, level_price, session_reference_price) != previous_side:
                continue
            if previous_side == "upper":
                if lower_bound <= level_price < selected_price:
                    crossed_levels.append((name, level_price))
            else:
                if upper_bound >= level_price > selected_price:
                    crossed_levels.append((name, level_price))

    if not crossed_levels:
        crossed_levels.append((str(previous.get("name")), previous.get("price")))

    seen_keys = {
        record.get("key") or liquidity_key(record.get("name"), record.get("price"))
        for record in consumed
        if isinstance(record, dict)
    }
    exhausted_at = candle_timestamp(current_candle)
    for level_name, level_price in crossed_levels:
        level_key = liquidity_key(level_name, level_price)
        if not level_key or level_key in seen_keys:
            continue
        seen_keys.add(level_key)
        consumed.append(
            {
                "key": level_key,
                "name": level_name,
                "price": level_price,
                "side": previous_side,
                "exhaustion_type": "same_side_next_liquidity_reached",
                "exhausted_by": selected.get("name"),
                "exhausted_by_price": selected.get("price"),
                "exhausted_at_candle_time": exhausted_at,
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
                            "side": side_for_level(
                                name,
                                price,
                                stack_reference_price_from_context(tv_context),
                            ),
                        }
                    )
                components = sorted(components, key=lambda item: (item["priority"], item["name"]))
                if components:
                    prices = [component["price"] for component in components]
                    side = components[0].get("side") or side_for_level(
                        active_level,
                        components[0].get("price"),
                        stack_reference_price_from_context(tv_context),
                    )
                    if side == "upper":
                        close_boundary = min(prices)
                        extreme_boundary = max(prices)
                    elif side == "lower":
                        close_boundary = max(prices)
                        extreme_boundary = min(prices)
                    else:
                        close_boundary = prices[0]
                        extreme_boundary = prices[0]

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
                        if len(components) == 1:
                            return str(components[0]["name"])
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

                    return {
                        "name": stack_group,
                        "components": [component["name"] for component in components],
                        "prices": {component["name"]: component["price"] for component in components},
                        "side": side,
                        "display_name": combined_stack_name(components, side),
                        "close_boundary": close_boundary,
                        "stack_extreme": extreme_boundary,
                        "extreme_boundary": extreme_boundary,
                        "close_component": close_component_for_stack(components, side)["name"],
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
    tick_size = optional_float(((snapshot.get("liquidity") or {}).get("tick_size"))) or 0.25
    step2_probe = step_2_1a.get("pre_activation_probe_boundary") if isinstance(step_2_1a.get("pre_activation_probe_boundary"), dict) else None
    probe_boundary = step2_probe.get("boundary_price") if isinstance(step2_probe, dict) and step2_probe.get("active") is True else None
    continuation_probe = step2_probe if probe_boundary is not None else None
    if probe_boundary is not None:
        pathway_level = probe_boundary
    # Continuation qualification must use the immutable stack extreme, not the mutable rejection raid boundary.
    pathway_stack_extreme = (
        (active_group or {}).get("stack_extreme")
        if isinstance(active_group, dict) and (active_group or {}).get("stack_extreme") is not None
        else (active_group or {}).get("extreme_boundary")
        if isinstance(active_group, dict)
        else None
    )
    bars = recent_closed_bars(str(snapshot.get("normalized_symbol") or snapshot.get("symbol") or "NQ"), 2)
    if current_candle is not None and candle_close_confirmed(snapshot):
        current_time = candle_timestamp(current_candle)
        last_bar_time = candle_timestamp(bars[-1]) if bars else None
        if current_time and not same_candle_time(current_time, last_bar_time):
            bars = [*bars, current_candle]
        bars = bars[-2:]
    previous_step25 = persisted_state.get("step25") if isinstance(persisted_state.get("step25"), dict) else {}
    previous_state = previous_step25.get("state") if isinstance(previous_step25.get("state"), dict) else {}
    previous_step3 = persisted_state.get("step3") if isinstance(persisted_state.get("step3"), dict) else {}
    previous_step3_state = previous_step3.get("state") if isinstance(previous_step3.get("state"), dict) else {}
    previous_step4 = persisted_state.get("step4") if isinstance(persisted_state.get("step4"), dict) else {}
    previous_step4_state = previous_step4.get("state") if isinstance(previous_step4.get("state"), dict) else {}
    previous_step5 = persisted_state.get("step5") if isinstance(persisted_state.get("step5"), dict) else {}
    previous_step5_state = previous_step5.get("state") if isinstance(previous_step5.get("state"), dict) else {}
    previous_step6 = persisted_state.get("step6") if isinstance(persisted_state.get("step6"), dict) else {}
    previous_step6_state = previous_step6.get("state") if isinstance(previous_step6.get("state"), dict) else {}
    current_candle_time = candle_timestamp(current_candle) if isinstance(current_candle, dict) else None
    consumed_level_blocks_continuation = liquidity_level_consumed(persisted_state, active_level, level_price)
    continuation_eligible_source = None
    continuation_eligible_at = previous_state.get("continuation_eligible_at")
    continuation_evaluation_started_at = previous_state.get("continuation_evaluation_started_at")
    continuation_reference_boundary_type = previous_state.get("continuation_reference_boundary_type")
    continuation_reference_boundary_price = previous_state.get("continuation_reference_boundary_price")
    continuation_evaluation_reason = previous_state.get("continuation_evaluation_reason")
    continuation_active_boundary_price = previous_state.get("continuation_active_boundary_price")
    continuation_seed_boundary = None
    continuation_seeded_from_rejection_step4 = False
    continuation_eligibility_open = False
    frozen_rejection_reference = frozen_rejection_trade_state_reference(
        persisted_state,
        active_level,
        level_price,
        active_group if isinstance(active_group, dict) else None,
    )
    if not consumed_level_blocks_continuation and isinstance(frozen_rejection_reference, dict):
        continuation_eligibility_open = True
        continuation_eligible_source = "frozen_rejection_trade_state"
        continuation_eligible_at = frozen_rejection_reference.get("eligible_at") or continuation_eligible_at
        continuation_reference_boundary_type = frozen_rejection_reference.get("boundary_type") or continuation_reference_boundary_type
        continuation_reference_boundary_price = frozen_rejection_reference.get("boundary_price") if frozen_rejection_reference.get("boundary_price") is not None else continuation_reference_boundary_price
        if continuation_active_boundary_price is None:
            continuation_active_boundary_price = continuation_reference_boundary_price
    reserved_rejection_candle_b = active_step4_candle_b_reservation(
        persisted_state,
        current_candle,
        expected_active_liquidity={"name": active_level, "price": level_price, "side": side, "group": active_group if isinstance(active_group, dict) else None},
    )
    previous_initial = previous_state.get("initial_candle_a") if isinstance(previous_state, dict) else None
    previous_liquidity = previous_state.get("active_liquidity") if isinstance(previous_state.get("active_liquidity"), dict) else None
    previous_same_rejection_liquidity = (
        previous_state.get("step25_pathway_selection_complete") is True
        and normalized_pathway_name(previous_state.get("controlling_mode")) == "Normal"
        and normalized_pathway_name(rejection.get("controlling_mode") or previous_state.get("controlling_mode")) == "Normal"
        and valid_active_liquidity_selection((previous_liquidity or {}).get("name") or previous_state.get("active_liquidity_name"), (previous_liquidity or {}).get("price") or previous_state.get("active_liquidity_price"))
        and same_liquidity_owner(
            {
                "name": (previous_liquidity or {}).get("name") or previous_state.get("active_liquidity_name"),
                "price": (previous_liquidity or {}).get("price") or previous_state.get("active_liquidity_price"),
                "side": (previous_liquidity or {}).get("side") or side_for_level(str((previous_liquidity or {}).get("name") or previous_state.get("active_liquidity_name") or "")),
                "group": (previous_liquidity or {}).get("group") if isinstance((previous_liquidity or {}).get("group"), dict) else previous_state.get("active_liquidity_group") if isinstance(previous_state.get("active_liquidity_group"), dict) else None,
            },
            {
                "name": active_level,
                "price": level_price,
                "side": side,
                "group": active_group if isinstance(active_group, dict) else None,
            },
        )
    )
    if previous_same_rejection_liquidity and isinstance(previous_initial, dict):
        initial_candle_a = previous_initial
    previous_continuation_locked = (
        previous_state.get("continuation_step2_activated") is True
        and normalized_pathway_name(previous_state.get("controlling_mode")) in {"S/R", "R/S"}
        and isinstance(previous_state.get("reclaim_candle_a"), dict)
    )
    downstream_continuation_locked = (
        previous_continuation_locked
        and (
            previous_step5_state.get("leg2_status") in {"CONFIRMED", "VALIDATED", "COMPLETE"}
            or previous_step5_state.get("step5_participation_validated") is True
            or previous_step6_state.get("step6_window_active") is True
        )
    )
    previous_locked = previous_continuation_locked or (
        previous_state.get("step25_pathway_selection_complete") is True
        and same_candle_time((previous_initial or {}).get("timestamp") if isinstance(previous_initial, dict) else None, (initial_candle_a or {}).get("timestamp") if isinstance(initial_candle_a, dict) else None)
    )
    if consumed_level_blocks_continuation:
        continuation_eligibility_open = False
        continuation_eligible_source = None
        continuation_eligible_at = None
        continuation_evaluation_started_at = None
        continuation_reference_boundary_type = None
        continuation_reference_boundary_price = None
        continuation_evaluation_reason = "consumed_liquidity_level"
        continuation_active_boundary_price = None
        continuation_seed_boundary = None
        continuation_seeded_from_rejection_step4 = False
        previous_continuation_locked = False
        downstream_continuation_locked = False
        previous_locked = False
    if probe_boundary is None and isinstance(previous_state.get("continuation_probe_boundary"), dict):
        previous_probe = previous_state["continuation_probe_boundary"]
        if previous_probe.get("active") is True and previous_probe.get("boundary_price") is not None:
            continuation_probe = previous_probe
            probe_boundary = previous_probe.get("boundary_price")
            pathway_level = probe_boundary
    if (
        isinstance(continuation_probe, dict)
        and continuation_probe.get("active") is True
        and continuation_probe.get("boundary_price") is not None
        and bars
        and pathway_level_type in {"LL", "LH"}
    ):
        latest_bar = bars[-1]
        try:
            latest_high = float(latest_bar.get("high"))
            latest_low = float(latest_bar.get("low"))
            latest_close = float(latest_bar.get("close"))
            current_boundary = float(continuation_probe.get("boundary_price"))
        except (TypeError, ValueError):
            latest_high = latest_low = latest_close = current_boundary = None
        if (
            pathway_level_type == "LL"
            and latest_high is not None
            and latest_close is not None
            and current_boundary is not None
            and latest_high > current_boundary
            and latest_close < current_boundary + tick_size
        ):
            probe_boundary = latest_high
            continuation_probe = {
                **continuation_probe,
                "active": True,
                "boundary_price": probe_boundary,
            }
            pathway_level = probe_boundary
        elif (
            pathway_level_type == "LH"
            and latest_low is not None
            and latest_close is not None
            and current_boundary is not None
            and latest_low < current_boundary
            and latest_close > current_boundary - tick_size
        ):
            probe_boundary = latest_low
            continuation_probe = {
                **continuation_probe,
                "active": True,
                "boundary_price": probe_boundary,
            }
            pathway_level = probe_boundary
    if (
        probe_boundary is None
        and (continuation_eligibility_open or previous_same_rejection_liquidity)
        and not previous_continuation_locked
        and not consumed_level_blocks_continuation
        and bars
        and level_price is not None
    ):
        latest_bar = bars[-1]
        try:
            latest_high = float(latest_bar.get("high"))
            latest_low = float(latest_bar.get("low"))
            latest_close = float(latest_bar.get("close"))
            level_value = float(level_price)
        except (TypeError, ValueError):
            latest_high = latest_low = latest_close = level_value = None
        if pathway_level_type == "LL" and latest_high is not None and latest_high > level_value and latest_close <= level_value:
            probe_boundary = latest_high
            continuation_probe = {
                "active": True,
                "side": "lower",
                "source_level": active_level,
                "boundary_price": probe_boundary,
                "detected_at_index": None,
            }
            pathway_level = probe_boundary
        elif pathway_level_type == "LH" and latest_low is not None and latest_low < level_value and latest_close >= level_value:
            probe_boundary = latest_low
            continuation_probe = {
                "active": True,
                "side": "upper",
                "source_level": active_level,
                "boundary_price": probe_boundary,
                "detected_at_index": None,
            }
            pathway_level = probe_boundary

    previous_step4_candle_b = previous_step4_state.get("candle_b") if isinstance(previous_step4_state.get("candle_b"), dict) else None
    previous_step4_completed_same_candle = (
        previous_step4_state.get("leg1_status") == "COMPLETE"
        and previous_step4_state.get("leg1_state_locked") is True
        and current_candle_time
        and same_candle_time(previous_step4_state.get("leg1_completed_at"), current_candle_time)
        and same_candle_time(candle_timestamp(previous_step4_candle_b), current_candle_time)
    )
    if previous_step4_completed_same_candle and not previous_continuation_locked:
        continuation_seed_boundary = optional_float(previous_step4_candle_b.get("low") if side == "upper" else previous_step4_candle_b.get("high"))
        continuation_seeded_from_rejection_step4 = continuation_seed_boundary is not None

    continuation_step2_conflicts_with_rejection_step4 = (
        reserved_rejection_candle_b is not None
        or previous_step4_completed_same_candle
        or (
            normalized_pathway_name(previous_step4_state.get("controlling_mode")) == "Normal"
            and previous_step4_state.get("leg1_window_active") is True
            and previous_step4_state.get("leg1_status") != "COMPLETE"
            and previous_step4_state.get("leg1_state_locked") is not True
            and previous_step4_state.get("leg1_window_invalidated") is not True
            and current_candle is not None
            and candle_is_after(current_candle, previous_step4_state.get("leg1_window_started_at"))
        )
        or (
            previous_step25.get("status") == "READY"
            and previous_step3.get("status") == "ALLOW_STEP_4"
            and normalized_pathway_name(previous_state.get("controlling_mode")) == "Normal"
            and normalized_pathway_name(previous_step3_state.get("controlling_mode")) == "Normal"
            and previous_step4_state.get("leg1_status") != "COMPLETE"
            and previous_step4_state.get("leg1_state_locked") is not True
            and isinstance(previous_initial, dict)
            and current_candle is not None
            and candle_is_after(current_candle, candle_timestamp(previous_initial))
        )
    )
    if continuation_eligibility_open:
        continuation_step2_conflicts_with_rejection_step4 = False
    if previous_continuation_locked:
        continuation_step2_conflicts_with_rejection_step4 = False
    if len(bars) >= 1 and pathway_level is not None and pathway_level_type and not previous_continuation_locked and not consumed_level_blocks_continuation:
        prev_candle = bars[-2] if len(bars) >= 2 else bars[-1]
        live_selection = select_pathway(
            bars[-1],
            prev_candle,
            pathway_level,
            pathway_level_type,
            pathway_stack_extreme,
            current_boundary=probe_boundary,
            tick_size=tick_size,
            active_liquidity_selected=active_level is not None and level_price is not None,
            rejection_step2_confirmed=step_2_1a.get("step_2_activated") is True,
        )
        if (
            live_selection.get("status") == "READY"
            and previous_step25.get("status") == "READY"
            and previous_step3.get("status") == "ALLOW_STEP_4"
            and normalized_pathway_name(previous_state.get("controlling_mode")) == "Normal"
            and previous_step4_state.get("leg1_status") != "COMPLETE"
            and previous_step4_state.get("leg1_state_locked") is not True
        ):
            rejection_step4_interaction = build_step4_interaction(
                snapshot,
                rejection,
                previous_step25,
                previous_step3,
                persisted_state,
            )
            if rejection_step4_interaction is not None:
                rejection_step4_result = evaluate_step4(rejection_step4_interaction)
                rejection_step4_state = (
                    rejection_step4_result.get("state") if isinstance(rejection_step4_result.get("state"), dict) else {}
                )
                rejection_candle_b = (
                    rejection_step4_state.get("candle_b")
                    if isinstance(rejection_step4_state.get("candle_b"), dict)
                    else rejection_step4_interaction.get("candle_b")
                )
                continuation_step2_conflicts_with_rejection_step4 = (
                    continuation_step2_conflicts_with_rejection_step4
                    or (
                        rejection_step4_result.get("status") == "READY"
                        and same_candle_time(
                            candle_timestamp(rejection_candle_b if isinstance(rejection_candle_b, dict) else None),
                            candle_timestamp(bars[-1]),
                        )
                    )
                )
                if (
                    not previous_continuation_locked
                    and rejection_step4_result.get("status") == "READY"
                    and same_candle_time(
                    candle_timestamp(rejection_candle_b if isinstance(rejection_candle_b, dict) else None),
                    candle_timestamp(bars[-1]),
                    )
                ):
                    continuation_seed_boundary = optional_float(
                        (rejection_candle_b if isinstance(rejection_candle_b, dict) else {}).get("low")
                        if side == "upper"
                        else (rejection_candle_b if isinstance(rejection_candle_b, dict) else {}).get("high")
                    )
                    continuation_seeded_from_rejection_step4 = continuation_seed_boundary is not None
                if continuation_eligibility_open:
                    continuation_step2_conflicts_with_rejection_step4 = False

    if continuation_seed_boundary is not None and active_level and side in {"upper", "lower"}:
        probe_boundary = continuation_seed_boundary
        continuation_probe = {
            "active": True,
            "side": side,
            "source_level": active_level,
            "boundary_price": continuation_seed_boundary,
            "detected_at_index": None,
            "source": "rejection_step4_confirmation_close",
        }
        pathway_level = continuation_seed_boundary
        continuation_active_boundary_price = continuation_seed_boundary

    prior_continuation_boundary = continuation_probe_boundary_price(previous_state)
    if continuation_eligible_source == "frozen_rejection_trade_state" and continuation_active_boundary_price is None:
        continuation_active_boundary_price = monotonic_continuation_boundary(
            side,
            prior_continuation_boundary,
            continuation_reference_boundary_price,
        )
    if (
        continuation_eligible_source == "frozen_rejection_trade_state"
        and continuation_active_boundary_price is not None
        and isinstance(current_candle, dict)
        and not continuation_step2_conflicts_with_rejection_step4
        and previous_state.get("continuation_step2_activated") is not True
    ):
        if continuation_close_confirms_active_boundary(side, current_candle.get("close"), continuation_active_boundary_price):
            continuation_evaluation_started_at = candle_timestamp(current_candle) or current_candle_time
            continuation_evaluation_reason = (
                f"Step 2 Continuation confirmed from active continuation boundary {continuation_active_boundary_price}."
            )
        else:
            continuation_active_boundary_price = monotonic_continuation_boundary(
                side,
                prior_continuation_boundary,
                wick_adjusted_continuation_boundary(
                    side,
                    continuation_active_boundary_price,
                    current_candle,
                ),
            )
        if continuation_active_boundary_price is not None:
            probe_boundary = continuation_active_boundary_price
            continuation_probe = {
                "active": True,
                "side": side,
                "source_level": active_level,
                "boundary_price": continuation_active_boundary_price,
                "detected_at_index": None,
                "source": "frozen_rejection_trade_state",
            }
            pathway_level = continuation_active_boundary_price

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
        "pathway_level": pathway_level if probe_boundary is not None else (previous_state.get("pathway_level") if previous_locked else pathway_level),
        "pathway_activation_type": previous_state.get("pathway_activation_type") if previous_locked and previous_state.get("pathway_activation_type") != "wick" else None,
        "continuation_step2_activated": previous_state.get("continuation_step2_activated") if previous_locked else None,
        "continuation_pending_boundary": previous_state.get("continuation_pending_boundary"),
        "continuation_step2_pending": previous_state.get("continuation_step2_pending"),
        "continuation_probe_boundary": continuation_probe if continuation_probe is not None else previous_state.get("continuation_probe_boundary"),
        "continuation_eligibility_open": continuation_eligibility_open,
        "continuation_eligible_source": continuation_eligible_source,
        "continuation_eligible_at": continuation_eligible_at,
        "continuation_evaluation_started_at": continuation_evaluation_started_at,
        "continuation_reference_boundary_type": continuation_reference_boundary_type,
        "continuation_reference_boundary_price": continuation_reference_boundary_price,
        "continuation_active_boundary_price": continuation_active_boundary_price,
        "continuation_evaluation_reason": continuation_evaluation_reason,
        "current_boundary": probe_boundary,
        "continuation_seeded_from_rejection_step4": (
            continuation_seeded_from_rejection_step4
            or bool(previous_state.get("continuation_seeded_from_rejection_step4"))
            or continuation_eligible_source == "frozen_rejection_trade_state"
        ),
        "tick_size": tick_size,
        "active_liquidity_selected": active_level is not None and level_price is not None,
        "active_liquidity": {"name": active_level, "price": level_price, "side": side},
        "active_liquidity_name": active_level,
        "active_liquidity_price": level_price,
        "rejection_step2_confirmed": step_2_1a.get("step_2_activated") is True,
        "continuation_step2_conflict_with_rejection_step4": continuation_step2_conflicts_with_rejection_step4,
        "events": list(previous_step25.get("events") or []) if previous_locked else [],
    }
    if continuation_step2_conflicts_with_rejection_step4 and not previous_continuation_locked:
        interaction["candidate_modes"] = ["Normal Rejection Mode"]
        interaction["controlling_mode"] = "Normal Rejection Mode"
        interaction["reclaim_candle_a"] = None
        interaction["continuation_step2_activated"] = None
        interaction["pathway_activation_type"] = "normal"
    if consumed_level_blocks_continuation:
        interaction["candidate_modes"] = ["Normal Rejection Mode"]
        interaction["controlling_mode"] = "Normal Rejection Mode"
        interaction["reclaim_candle_a"] = None
        interaction["provisional_candle_a"] = None
        interaction["pathway_activation_type"] = "normal"
        interaction["continuation_step2_activated"] = None
        interaction["continuation_probe_boundary"] = None
        interaction["continuation_eligibility_open"] = False
        interaction["continuation_eligible_source"] = None
        interaction["continuation_eligible_at"] = None
        interaction["continuation_reference_boundary_type"] = None
        interaction["continuation_reference_boundary_price"] = None
        interaction["continuation_active_boundary_price"] = None
        interaction["continuation_seeded_from_rejection_step4"] = False
        interaction["continuation_evaluation_reason"] = "consumed_liquidity_level"
        interaction["current_boundary"] = None
    if (
        len(bars) >= 1
        and pathway_level is not None
        and pathway_level_type
        and not continuation_step2_conflicts_with_rejection_step4
        and not previous_continuation_locked
        and not consumed_level_blocks_continuation
    ):
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
    """Evaluate the internal continuation pathway after Step 2 activates Rejection Mode."""
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
        reason = "Step 3 requires Step 2 liquidity-close activation, Step 2 Continuation selection, Candle A, and active liquidity."
        return {
            "step": "Step 3",
            "status": "WAIT",
            "state": {},
            "next_step": "Step 2",
            "reason": reason,
            "events": [{"event": "step3_waiting_for_step2", "reason": reason}],
        }
    return evaluate_step3(interaction)


def nearest_opposing_liquidity(
    liquidity: dict[str, Any],
    setup_direction: str | None,
    active_liquidity: dict[str, Any] | None = None,
    tv_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return the nearest true opposite-side liquidity for the Step 4 proximity filter."""
    desired_side = None
    if isinstance(active_liquidity, dict):
        active_side = str(active_liquidity.get("side") or side_for_level(str(active_liquidity.get("name") or "")) or "").strip().lower()
        if active_side == "upper":
            desired_side = "lower"
        elif active_side == "lower":
            desired_side = "upper"
    if desired_side is None:
        desired_side = "lower" if setup_direction == "SHORT" else "upper" if setup_direction == "LONG" else None
    active_price = optional_float((active_liquidity or {}).get("price")) if isinstance(active_liquidity, dict) else None
    levels = tv_context.get("levels") if isinstance(tv_context, dict) else None
    if desired_side and isinstance(levels, dict):
        candidates: list[dict[str, Any]] = []
        for name, details in levels.items():
            if not isinstance(details, dict):
                continue
            price = optional_float(details.get("price"))
            if price is None:
                continue
            if side_for_level(str(name), price, stack_reference_price_from_context(tv_context)) != desired_side:
                continue
            if desired_side == "lower" and active_price is not None and price >= active_price:
                continue
            if desired_side == "upper" and active_price is not None and price <= active_price:
                continue
            candidates.append({"name": str(name), "price": price})
        if candidates:
            if desired_side == "lower":
                return max(candidates, key=lambda item: item["price"])
            return min(candidates, key=lambda item: item["price"])
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


def load_rithmic_atr_observation(
    symbol: str,
    reference_time: datetime | None = None,
) -> dict[str, Any] | None:
    """Load a current canonical record, including valid not-ready warmup records."""
    symbol_text = str(symbol).upper()
    recent_payload = _read_json(RITHMIC_RECENT_BARS_PATH)
    recent_symbols = recent_payload.get("symbols") if isinstance(recent_payload, dict) else {}
    if not isinstance(recent_symbols, dict):
        return None
    feed_health = _read_json(RITHMIC_FEED_HEALTH_PATH)
    runtime = feed_health.get("listener_runtime") if isinstance(feed_health, dict) else {}
    active_epoch = runtime.get("atr_authority_epoch_id") if isinstance(runtime, dict) else None
    subscribed_contracts = {
        str(item.get("contract_symbol") or "").upper()
        for item in (runtime.get("subscribed_contracts") or [])
        if isinstance(item, dict) and item.get("contract_symbol")
    } if isinstance(runtime, dict) else set()
    candidates = []
    for contract, bars in recent_symbols.items():
        contract_text = str(contract).upper()
        if (
            root_symbol(contract_text) != root_symbol(symbol_text)
            or not isinstance(bars, list)
            or not bars
            or (subscribed_contracts and contract_text not in subscribed_contracts)
        ):
            continue
        candidates.append((str(bars[-1].get("timestamp") or ""), contract_text, bars[-1]))
    for _timestamp, contract, matched_bar in sorted(candidates, reverse=True):
        record = matched_bar.get("canonical_atr") if isinstance(matched_bar, dict) else None
        if not isinstance(record, dict):
            continue
        if (
            record.get("formula") != CANONICAL_ATR_FORMULA
            or record.get("formula_version") != CANONICAL_ATR_FORMULA_VERSION
            or record.get("atr_source") != CANONICAL_ATR_SOURCE
            or record.get("timeframe") != "1m"
            or record.get("period") != 14
            or not record.get("atr_record_id")
            or not record.get("bar_id")
            or record.get("symbol_root") != root_symbol(symbol_text)
            or record.get("contract_symbol") != contract
            or record.get("finalized_candle_bar_id") != record.get("bar_id")
            or record.get("last_included_bar_id") != record.get("bar_id")
            or record.get("candle_minute") != matched_bar.get("timestamp")
            or record.get("builder_contract_version") != matched_bar.get("builder_contract_version")
            or (active_epoch is not None and record.get("atr_authority_epoch_id") != active_epoch)
        ):
            continue
        if matched_bar.get("status") != "FINAL" or matched_bar.get("bar_id") != record.get("bar_id"):
            continue
        session_date = str(matched_bar.get("session_date") or "").strip()
        if session_date:
            now = reference_time or datetime.now(timezone.utc)
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            if session_date != now.astimezone(LOCAL_MARKET_TIMEZONE).date().isoformat():
                continue
        return copy.deepcopy(record)
    return None


def load_rithmic_atr_snapshot(symbol: str) -> dict[str, Any] | None:
    """Load a ready trade-authoritative Rithmic RMA record; never fall back to TV."""
    record = load_rithmic_atr_observation(symbol)
    if not isinstance(record, dict) or record.get("ready") is not True:
        return None
    value = record.get("updated_raw_atr", record.get("atr_value"))
    try:
        atr_value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(atr_value) or atr_value <= 0:
        return None
    return {
        "atr_1m_14": atr_value,
        "atr_value": atr_value,
        "atr_bar_timestamp": record.get("candle_minute") or record.get("atr_bar_timestamp"),
        "atr_source": record.get("atr_source"),
        "atr_record_id": record.get("atr_record_id"),
        "atr_bar_id": record.get("bar_id"),
        "formula": record.get("formula"),
        "formula_version": record.get("formula_version"),
        "last_included_bar": record.get("last_included_bar"),
        "ready": True,
        "symbol": str(record.get("contract_symbol") or "").upper(),
        "canonical_atr": copy.deepcopy(record),
    }


def canonical_atr_status_projection(record: dict[str, Any] | None) -> dict[str, Any]:
    """Build public ATR diagnostics without changing ready-only decision authority."""
    current = record if isinstance(record, dict) else {}
    ready = bool(current.get("ready") is True and current.get("updated_raw_atr") is not None)
    return {
        "canonical_atr_status": copy.deepcopy(current) if current else None,
        "atr_contract_symbol": current.get("contract_symbol"),
        "atr_source": current.get("atr_source") or CANONICAL_ATR_SOURCE,
        "atr_included_bar_count": int(current.get("warmup_true_range_count") or 0),
        "atr_required_bar_count": int(current.get("warmup_required_true_range_count") or 14),
        "atr_readiness_reason": current.get("warmup_status") or "CANONICAL_RITHMIC_ATR_NOT_READY",
        "atr_observation_ready": ready,
        "atr_observation_last_included_bar": current.get("last_included_bar"),
    }


def atr_from_snapshot(snapshot: dict[str, Any]) -> float | None:
    """Return only the canonical Rithmic listener ATR; there is no TV fallback."""
    atr = snapshot.get("atr")
    if isinstance(atr, dict):
        try:
            return float(atr.get("atr_1m_14"))
        except (TypeError, ValueError):
            pass
    return None


def canonical_atr_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    atr = snapshot.get("atr")
    record = atr.get("canonical_atr") if isinstance(atr, dict) else None
    return copy.deepcopy(record) if isinstance(record, dict) and record.get("ready") is True else None


def daily_atr_from_snapshot(snapshot: dict[str, Any]) -> float | None:
    """Return TradingView daily ATR for structure filters."""
    return daily_atr_from_context(snapshot.get("tv_context"))


def actionable_liquidity_boundary_price(
    liquidity: dict[str, Any] | None,
    tv_context: dict[str, Any] | None = None,
) -> float | None:
    """Return the actionable extreme boundary for telemetry and downstream display."""
    if not isinstance(liquidity, dict):
        return None
    group = liquidity.get("group") if isinstance(liquidity.get("group"), dict) else None
    if not isinstance(group, dict):
        group = active_stack_from_context(tv_context, str(liquidity.get("name") or ""))
    boundary = actionable_boundary_from_group(group)
    if boundary is not None:
        return boundary
    for key in ("wick_boundary_extreme", "stack_extreme", "extreme_boundary", "price"):
        boundary = optional_float(liquidity.get(key))
        if boundary is not None:
            return boundary
    return None


def liquidity_leg_atr_telemetry_from_snapshot(
    snapshot: dict[str, Any],
    step_2_1a: dict[str, Any],
    active_name: Any,
    active_price: Any,
    active_group: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build telemetry-only ATR distance for the current liquidity leg."""
    tv_context = snapshot.get("tv_context") if isinstance(snapshot.get("tv_context"), dict) else {}
    latest_price = optional_float(snapshot.get("latest_price"))
    daily_atr14 = daily_atr_from_snapshot(snapshot)
    step2_owner_state = step_2_1a.get("step2_locked_owner") if isinstance(step_2_1a.get("step2_locked_owner"), dict) else {}
    step2_owner_active = step2_owner_state.get("active_liquidity") if isinstance(step2_owner_state.get("active_liquidity"), dict) else {}

    leg_anchor_liquidity = None
    leg_anchor_price = None
    next_target = None

    if (
        step_2_1a.get("step_2_activated") is True
        and valid_active_liquidity_selection(step2_owner_active.get("name"), step2_owner_active.get("price"))
    ):
        leg_anchor_liquidity = step2_owner_active.get("display_name") or step2_owner_active.get("name")
        leg_anchor_price = actionable_liquidity_boundary_price(step2_owner_active, tv_context)
        next_target = step_2_1a.get("next_same_side_liquidity") if isinstance(step_2_1a.get("next_same_side_liquidity"), dict) else None
        if not isinstance(next_target, dict):
            next_target = next_same_side_liquidity_target(tv_context, step2_owner_active)
    elif latest_price is not None and valid_active_liquidity_selection(active_name, active_price):
        leg_anchor_price = latest_price
        next_target = {
            "name": active_name,
            "display_name": active_name,
            "price": active_price,
            "group": active_group if isinstance(active_group, dict) else None,
        }

    next_active_liquidity = None
    next_active_liquidity_price = None
    if isinstance(next_target, dict):
        next_active_liquidity_price = actionable_liquidity_boundary_price(next_target, tv_context)
        target_group = next_target.get("group") if isinstance(next_target.get("group"), dict) else None
        next_active_liquidity = (
            next_target.get("display_name")
            or (target_group or {}).get("display_name")
            or next_target.get("name")
        )
        if not valid_active_liquidity_name(next_active_liquidity) or next_active_liquidity_price is None:
            next_active_liquidity = None
            next_active_liquidity_price = None

    distance_points = None
    liquidity_leg_atr_distance_pct = None
    if leg_anchor_price is not None and next_active_liquidity_price is not None:
        distance_points = round(abs(next_active_liquidity_price - leg_anchor_price), 4)
    if distance_points is not None and daily_atr14 is not None and daily_atr14 > 0:
        liquidity_leg_atr_distance_pct = round(distance_points / daily_atr14 * 100.0, 4)

    return {
        "leg_anchor_liquidity": leg_anchor_liquidity,
        "leg_anchor_price": leg_anchor_price,
        "next_active_liquidity": next_active_liquidity,
        "next_active_liquidity_price": next_active_liquidity_price,
        "daily_atr14": daily_atr14,
        "distance_points": distance_points,
        "liquidity_leg_atr_distance_pct": liquidity_leg_atr_distance_pct,
    }


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


def lifecycle_lane_id(
    lane_name: str,
    confirmed_at: Any,
    owner: Any,
    direction: Any,
    close_boundary: Any,
    extreme_boundary: Any,
) -> str | None:
    """Return a stable lifecycle identity for one confirmed Step 2 lane."""
    confirmed_text = str(confirmed_at or "").strip()
    owner_text = str(owner or "").strip()
    direction_text = str(direction or "").strip().upper()
    close_value = optional_float(close_boundary)
    extreme_value = optional_float(extreme_boundary)
    if not confirmed_text or not owner_text:
        return None
    return "|".join(
        [
            lane_name,
            confirmed_text,
            owner_text,
            direction_text,
            str(close_value),
            str(extreme_value),
        ]
    )


def lifecycle_lane_contract(lane_id: Any) -> dict[str, Any]:
    """Parse a persisted lane id into the immutable Step 2 contract it represents."""
    text = str(lane_id or "").strip()
    if not text:
        return {}
    parts = text.split("|")
    if len(parts) != 6:
        return {}
    lane_name, confirmed_at, owner_name, direction, close_boundary, extreme_boundary = parts
    return {
        "lane_name": lane_name,
        "confirmed_at": confirmed_at,
        "owner_name": owner_name,
        "direction": direction,
        "close_boundary": optional_float(close_boundary),
        "extreme_boundary": optional_float(extreme_boundary),
    }


def candle_for_timestamp(snapshot: dict[str, Any], target_time: Any) -> dict[str, Any] | None:
    """Return the closed candle matching one timestamp from recent bars plus the current snapshot candle."""
    target_text = str(target_time or "").strip()
    if not target_text:
        return None
    symbol = str(snapshot.get("normalized_symbol") or snapshot.get("symbol") or "NQ")
    current_candle = build_current_candle(snapshot)
    bars = unique_bars_by_time(recent_closed_bars(symbol, 20), current_candle)
    for candle in bars:
        if same_candle_time(candle_timestamp(candle), target_text):
            return dict(candle)
    return None


def clear_downstream_lifecycle_fields(state: dict[str, Any]) -> None:
    """Remove all downstream lifecycle outputs so a new Step 2 can start with a clean lifecycle."""
    for key in (
        "candle_a",
        "candle_b",
        "candle_a_source",
        "latest_candle",
        "leg1_status",
        "leg1_state_locked",
        "leg1_completed_at",
        "leg1_reference_price",
        "leg1_reference_candle_time",
        "leg1_direction",
        "leg1_reference",
        "leg1_reference_extreme",
        "leg1_extreme",
        "leg1_extreme_owner",
        "step4_confirmed_at",
        "step4_window_anchor_time",
        "step4_window_count",
        "step4_participation_extreme",
        "step4_participation_seed_time",
        "step4_proximity_distance",
        "step4_proximity_daily_atr",
        "step4_proximity_atr_threshold",
        "step4_proximity_atr_threshold_percent",
        "step4_block_reason",
        "step5_close_boundary",
        "leg2_sweep_extreme",
        "leg2_status",
        "leg2_candle",
        "leg2_candle_a",
        "leg2_candle_a_time",
        "leg2_candidate_candle_time",
        "leg2_same_sequence_rejected",
        "leg2_wait_reason",
        "step5_confirmed",
        "step5_confirmation_window_active",
        "step5_participation_window_active",
        "step5_confirmation_candle_count",
        "step5_participation_candle_count",
        "step5_trigger_valid",
        "step5_trigger_candle",
        "step5_trigger_reason",
        "step6_window_active",
        "step6_window_started_at",
        "step6_window_candle_index",
        "step6_window_remaining",
        "step6_window_expires_at",
        "entry_candle",
        "entry_confirmed_at",
        "entry_triggered",
        "current_active_sequence_started_at",
        "last_evaluated_candle_time",
        "fifty_percent_rule_phase",
        "shared_leg1_uses_initial_candle_a",
        "participation_candidate_keys",
        "participation_candidate_count",
        "participation_timer",
        "step4_window_candles",
        "leg1_window_active",
        "leg1_window_started_at",
        "leg1_window_candle_index",
        "leg1_window_remaining",
        "leg1_window_expires_at",
        "leg1_window_invalidated",
        "leg1_window_invalidation_reason",
    ):
        state.pop(key, None)


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
    # Step 2 -> Step 4 handoff contract:
    # - Step 4 formulas are shared, but Candle A/B context is pathway-specific.
    # - Rejection Step 4 uses the Step 2 rejection confirmation candle as Candle A and the next candle as Candle B.
    #   Upper-liquidity rejection direction is SHORT; lower-liquidity rejection direction is LONG.
    # - Continuation Step 4 uses the Step 2 continuation activation/reclaim candle as Candle A and the next candle as Candle B.
    #   R/S after upper liquidity is LONG; S/R after lower liquidity is SHORT.
    # - When continuation takes control, stale rejection Candle A/B and direction must not leak across the pathway transition.
    #   Seed continuation Candle A from the continuation activation candle and do not evaluate Step 4 until the next candle.
    # - A Step 4 COMPLETE from the previous pathway cannot be reused as a Step 4 COMPLETE for a new pathway.
    previous_step4 = persisted_state.get("step4") if isinstance(persisted_state.get("step4"), dict) else {}
    previous_state = previous_step4.get("state") if isinstance(previous_step4.get("state"), dict) else {}
    previous_lane_contract = lifecycle_lane_contract(previous_state.get("lane_id"))
    continuation_mode = (
        normalized_pathway_name(step25_state.get("controlling_mode")) in {"S/R", "R/S"}
        or step25_state.get("continuation_step2_activated") is True
        or previous_lane_contract.get("lane_name") == "continuation"
    )
    continuation_candle_a = step25_state.get("reclaim_candle_a") if isinstance(step25_state.get("reclaim_candle_a"), dict) else None
    initial_candle_a = step25_state.get("initial_candle_a") if isinstance(step25_state.get("initial_candle_a"), dict) else None
    stack_confirmation_candle = (
        step3_state.get("stack_extreme_confirmation_candle")
        if isinstance(step3_state.get("stack_extreme_confirmation_candle"), dict)
        else None
    )
    continuation_candle_time = candle_timestamp(continuation_candle_a)
    current_candle_time = candle_timestamp(current_candle)
    continuation_candle_available = bool(
        continuation_mode
        and continuation_candle_a is not None
        and current_candle_time
        and continuation_candle_time
        and not candle_is_after({"timestamp": continuation_candle_time}, current_candle_time)
    )
    same_candle_continuation_reclaim = (
        continuation_mode
        and continuation_candle_available
        and same_candle_time(continuation_candle_time, current_candle_time)
    )
    continuation_lane_id = None
    continuation_contract: dict[str, Any] = {}
    continuation_owner_price = None
    continuation_mode_name = normalized_pathway_name(step25_state.get("controlling_mode"))
    if continuation_mode and step25_state.get("continuation_step2_activated") is True:
        continuation_confirmed_at = continuation_step2_confirmed_at(step25_state)
        continuation_anchor = candle_for_timestamp(snapshot, continuation_confirmed_at)
        if isinstance(continuation_anchor, dict):
            continuation_candle_a = continuation_anchor
            initial_candle_a = continuation_anchor
        previous_contract = lifecycle_lane_contract(previous_state.get("lane_id"))
        active_liquidity = step3_state.get("active_liquidity") if isinstance(step3_state.get("active_liquidity"), dict) else {}
        setup_direction = setup_direction_from_pathway(step25_state, rejection)
        continuation_owner_name = active_liquidity.get("name")
        continuation_close_boundary = step25_state.get("continuation_active_boundary_price") or step25_state.get("continuation_reference_boundary_price") or step3_state.get("pathway_level")
        continuation_extreme_boundary = step3_state.get("extreme_boundary") or step3_state.get("stack_extreme")
        if continuation_extreme_boundary is None:
            continuation_extreme_boundary = step25_state.get("continuation_reference_boundary_price") or continuation_close_boundary
        continuation_owner_price = active_liquidity.get("price")
        if continuation_owner_price is None:
            continuation_owner_price = step25_state.get("continuation_reference_boundary_price") or continuation_close_boundary
        if (
            previous_contract.get("lane_name") == "continuation"
            and previous_contract.get("confirmed_at") == continuation_confirmed_at
        ):
            continuation_owner_name = previous_contract.get("owner_name") or continuation_owner_name
            if previous_contract.get("close_boundary") is not None:
                continuation_close_boundary = previous_contract.get("close_boundary")
            if previous_contract.get("extreme_boundary") is not None:
                continuation_extreme_boundary = previous_contract.get("extreme_boundary")
        continuation_lane_id = lifecycle_lane_id(
            "continuation",
            continuation_confirmed_at,
            continuation_owner_name,
            setup_direction,
            continuation_close_boundary,
            continuation_extreme_boundary,
        )
        continuation_contract = lifecycle_lane_contract(continuation_lane_id)
        previous_mode_name = normalized_pathway_name(previous_state.get("controlling_mode"))
        if previous_mode_name in {"S/R", "R/S"}:
            continuation_mode_name = previous_mode_name
        if previous_state.get("lane_id") != continuation_lane_id:
            previous_state = {}
            previous_step4 = {}
    elif continuation_mode and previous_lane_contract.get("lane_name") == "continuation":
        continuation_lane_id = previous_state.get("lane_id")
        continuation_contract = previous_lane_contract
        continuation_confirmed_at = continuation_contract.get("confirmed_at")
        continuation_anchor = candle_for_timestamp(snapshot, continuation_confirmed_at)
        if isinstance(continuation_anchor, dict):
            continuation_candle_a = continuation_anchor
            initial_candle_a = continuation_anchor
        continuation_owner_price = (
            (step3_state.get("active_liquidity") or {}).get("price")
            if isinstance(step3_state.get("active_liquidity"), dict)
            else None
        )
        if continuation_owner_price is None:
            continuation_owner_price = continuation_contract.get("close_boundary")
        if continuation_owner_price is None:
            continuation_owner_price = continuation_contract.get("extreme_boundary")
        previous_mode_name = normalized_pathway_name(previous_state.get("controlling_mode"))
        if previous_mode_name in {"S/R", "R/S"}:
            continuation_mode_name = previous_mode_name
    if continuation_reclaim_starts_new_sequence(step25_state, previous_state):
        previous_state = {}
        previous_step4 = {}
    shared_leg1_anchor = None
    if continuation_mode:
        previous_candle_a = previous_state.get("candle_a") if isinstance(previous_state.get("candle_a"), dict) else None
        previous_initial_candle_a = previous_state.get("initial_candle_a") if isinstance(previous_state.get("initial_candle_a"), dict) else None
        candidate_anchor = previous_candle_a or previous_initial_candle_a
        candidate_anchor_time = candle_timestamp(candidate_anchor)
        if (
            isinstance(candidate_anchor, dict)
            and current_candle_time
            and candidate_anchor_time
            and candle_is_after(current_candle, candidate_anchor_time)
        ):
            shared_leg1_anchor = candidate_anchor
    step4_candle_a = shared_leg1_anchor or (continuation_candle_a if continuation_candle_available else initial_candle_a)
    step2_confirmation_time = candle_timestamp(step4_candle_a)
    current_is_step2_confirmation_candle = bool(step2_confirmation_time and same_candle_time(candle_timestamp(current_candle), step2_confirmation_time))
    current_is_setup_candle = current_is_step2_confirmation_candle or (
        not continuation_mode
        and not same_candle_continuation_reclaim
        and is_setup_candle_reused_as_participation(current_candle, step25_state, step3_state)
    )
    setup_direction = continuation_contract.get("direction") or setup_direction_from_pathway(step25_state, rejection)
    active_liquidity = step3_state.get("active_liquidity") if isinstance(step3_state.get("active_liquidity"), dict) else {}
    previous_active_liquidity = previous_state.get("active_liquidity") if isinstance(previous_state.get("active_liquidity"), dict) else {}
    frozen_step2_reference = (
        copy.deepcopy(previous_state.get("step2_step4_reference_liquidity"))
        if isinstance(previous_state.get("step2_step4_reference_liquidity"), dict)
        else copy.deepcopy(next_break_side_liquidity(snapshot.get("liquidity") or {}, setup_direction))
    )
    pending_rejection_leg1 = (
        not continuation_mode
        and previous_state.get("leg1_window_started_at")
        and previous_state.get("leg1_state_locked") is not True
        and previous_state.get("leg1_window_invalidated") is not True
        and previous_state.get("leg1_status") != "COMPLETE"
        and same_liquidity_owner(
            {
                "name": previous_active_liquidity.get("name") or previous_state.get("active_liquidity_name"),
                "price": previous_active_liquidity.get("price") or previous_state.get("active_liquidity_price"),
                "side": previous_active_liquidity.get("side") or side_for_level(str(previous_active_liquidity.get("name") or previous_state.get("active_liquidity_name") or "")),
                "group": previous_active_liquidity.get("group") if isinstance(previous_active_liquidity.get("group"), dict) else previous_state.get("active_liquidity_group") if isinstance(previous_state.get("active_liquidity_group"), dict) else None,
            },
            active_liquidity,
        )
    )
    if pending_rejection_leg1:
        preserved_anchor = (
            previous_state.get("initial_candle_a")
            if isinstance(previous_state.get("initial_candle_a"), dict)
            else previous_state.get("candle_a")
            if isinstance(previous_state.get("candle_a"), dict)
            else None
        )
        if isinstance(preserved_anchor, dict):
            initial_candle_a = preserved_anchor
    if continuation_mode and continuation_lane_id:
        if continuation_contract.get("owner_name"):
            active_liquidity = {
                **active_liquidity,
                "name": continuation_contract.get("owner_name"),
                "price": continuation_owner_price,
            }
            step3_state = {
                **step3_state,
                "active_liquidity": active_liquidity,
            }
        if continuation_contract.get("close_boundary") is not None:
            step3_state = {
                **step3_state,
                "close_boundary": continuation_contract.get("close_boundary"),
            }
        if continuation_contract.get("extreme_boundary") is not None:
            step3_state = {
                **step3_state,
                "extreme_boundary": continuation_contract.get("extreme_boundary"),
            }
    if consumed_liquidity_blocks(
        persisted_state,
        active_liquidity.get("name"),
        active_liquidity.get("price"),
        current_candle,
    ):
        return None

    interaction = dict(step25_state)
    interaction.update(step3_state)
    if isinstance(initial_candle_a, dict):
        interaction["initial_candle_a"] = initial_candle_a
    if continuation_mode and step25_state.get("continuation_step2_activated") is True:
        clear_downstream_lifecycle_fields(interaction)
    if continuation_candle_available and continuation_candle_a is not None:
        interaction["initial_candle_a"] = shared_leg1_anchor or continuation_candle_a
        interaction["candle_a"] = shared_leg1_anchor or continuation_candle_a
        interaction["reclaim_candle_a"] = continuation_candle_a
    interaction.update(
        {
            "setup_direction": setup_direction,
            "controlling_mode": continuation_mode_name if continuation_mode else interaction.get("controlling_mode"),
            "active_liquidity": active_liquidity,
            "close_boundary": (
                continuation_contract.get("close_boundary")
                if continuation_contract.get("close_boundary") is not None
                else step3_state.get("close_boundary")
            ),
            "extreme_boundary": (
                continuation_contract.get("extreme_boundary")
                if continuation_contract.get("extreme_boundary") is not None
                else step3_state.get("extreme_boundary")
            ),
            "candle_b": None if current_is_setup_candle else current_candle,
            "latest_candle": None if current_is_setup_candle else current_candle,
            "shared_leg1_uses_initial_candle_a": continuation_mode,
            "participation_candidate_keys": previous_state.get("participation_candidate_keys") or [],
            "participation_candidate_count": previous_state.get("participation_candidate_count") or 0,
            "participation_timer": previous_state.get("participation_timer"),
            "step4_window_candles": [dict(candle) for candle in (previous_state.get("step4_window_candles") or []) if isinstance(candle, dict)],
            "leg1_window_active": previous_state.get("leg1_window_active"),
            "leg1_window_started_at": previous_state.get("leg1_window_started_at"),
            "leg1_window_candle_index": previous_state.get("leg1_window_candle_index"),
            "leg1_window_remaining": previous_state.get("leg1_window_remaining"),
            "leg1_window_expires_at": previous_state.get("leg1_window_expires_at"),
            "leg1_window_invalidated": previous_state.get("leg1_window_invalidated"),
            "leg1_window_invalidation_reason": previous_state.get("leg1_window_invalidation_reason"),
            "nearest_opposing_liquidity": nearest_opposing_liquidity(
                snapshot.get("liquidity") or {},
                setup_direction,
                active_liquidity,
                snapshot.get("tv_context"),
            ),
            "step4_proximity_reference_liquidity": active_liquidity if continuation_mode else None,
            "next_break_side_liquidity": frozen_step2_reference or previous_state.get("step2_step4_reference_liquidity") or next_break_side_liquidity(snapshot.get("liquidity") or {}, setup_direction),
            "step2_step4_reference_liquidity": frozen_step2_reference or previous_state.get("step2_step4_reference_liquidity"),
            "step2_step4_50_line": previous_state.get("step2_step4_50_line"),
            "atr_1m_14": atr_from_snapshot(snapshot),
            "canonical_atr": canonical_atr_from_snapshot(snapshot),
            "atr_record_id": ((snapshot.get("atr") or {}).get("atr_record_id")),
            "atr_bar_id": ((snapshot.get("atr") or {}).get("atr_bar_id")),
            "atr_formula_version": ((snapshot.get("atr") or {}).get("formula_version")),
            "daily_atr14": daily_atr_from_snapshot(snapshot),
            "events": list(previous_step4.get("events") or step3.get("events") or []),
            "lane_id": continuation_lane_id if continuation_mode and step25_state.get("continuation_step2_activated") is True else previous_state.get("lane_id"),
        }
    )
    initialize_leg1_window(interaction, step2_confirmation_time)
    if continuation_mode:
        previous_candle_a = shared_leg1_anchor or (previous_state.get("candle_a") if isinstance(previous_state.get("candle_a"), dict) else None)
        if (
            isinstance(previous_candle_a, dict)
            and current_candle_time
            and candle_is_after(current_candle, candle_timestamp(previous_candle_a))
        ):
            interaction["candle_a"] = previous_candle_a
            interaction["latest_candle"] = current_candle
            interaction["candle_b"] = current_candle
            interaction["shared_leg1_uses_initial_candle_a"] = True
    if interaction.get("liquidity_type") == "STATIC_STACK" and not continuation_mode:
        previous_candle_a = previous_state.get("candle_a") if isinstance(previous_state.get("candle_a"), dict) else None
        confirmation_candle = stack_confirmation_candle
        seeded_candle_a = initial_candle_a if isinstance(initial_candle_a, dict) else confirmation_candle
        seeded_source = "initial_candle_a" if isinstance(initial_candle_a, dict) else "stack_extreme_confirmation_candle"
        if previous_state.get("stack_step4_candle_a_assigned") is True and previous_candle_a is not None:
            interaction["candle_a"] = previous_candle_a
            interaction["initial_candle_a"] = previous_candle_a
            interaction["candle_a_source"] = previous_state.get("candle_a_source") or "initial_candle_a"
            interaction["stack_step4_candle_a_assigned"] = True
            if candle_is_after(current_candle, candle_timestamp(previous_candle_a)):
                interaction["candle_b"] = current_candle
                interaction["latest_candle"] = current_candle
        elif isinstance(seeded_candle_a, dict):
            interaction["candle_a"] = seeded_candle_a
            interaction["initial_candle_a"] = seeded_candle_a
            interaction["candle_a_source"] = seeded_source
            interaction["stack_step4_candle_a_assigned"] = True
            if current_candle_time and candle_is_after(current_candle, candle_timestamp(seeded_candle_a)):
                interaction["candle_b"] = current_candle
                interaction["latest_candle"] = current_candle
        interaction.pop("awaiting_stack_candle_b", None)
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
    previous_sequence_started_at = candle_timestamp(previous_state.get("initial_candle_a") if isinstance(previous_state.get("initial_candle_a"), dict) else None) or previous_state.get("leg1_window_started_at")
    same_rejection_sequence = (
        normalized_pathway_name(previous_state.get("controlling_mode")) == "Normal"
        and previous_state.get("leg1_window_started_at")
        and previous_state.get("leg1_window_invalidated") is True
        and previous_state.get("leg1_state_locked") is not True
        and previous_state.get("leg1_status") != "COMPLETE"
        and same_liquidity_owner(
            previous_state.get("active_liquidity") if isinstance(previous_state.get("active_liquidity"), dict) else None,
            current_active_liquidity,
        )
        and previous_sequence_started_at
        and current_sequence_started_at
        and same_candle_time(previous_sequence_started_at, current_sequence_started_at)
        and not continuation_reclaim_starts_new_sequence(step25_state, previous_state)
    )
    if same_rejection_sequence:
        state = dict(previous_state)
        current_candle = build_current_candle(snapshot)
        if current_candle is not None:
            state["latest_candle"] = current_candle
            state["last_evaluated_candle_time"] = candle_timestamp(current_candle)
        reason = (
            state.get("leg1_window_invalidation_reason")
            or state.get("state_transition_reason")
            or result_reason(previous_step4, "Step 4 invalidated.")
        )
        state["state_transition_reason"] = reason
        return {
            "step": "Step 4",
            "status": "TERMINATED",
            "state": state,
            "next_step": "Step 4",
            "reason": reason,
            "events": list(previous_step4.get("events") or []),
        }
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
                reason = "Step 4 waiting: the participation window started after Step 2 confirmation; Candle 1 is the next future candle."
                state["state_transition_reason"] = reason
                return {
                    "step": "Step 4",
                    "status": "WAIT",
                    "state": state,
                    "next_step": "Step 4",
                    "reason": reason,
                    "events": [{"event": "step4_leg1_window_started", "reason": reason}],
                }
        reason = "Step 4 waiting for Step 2 Continuation selection, Step 3 permission, a Step 2 confirmation anchor, a participation candle, setup direction, ATR, and opposing liquidity."
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
        reason = "Step 4 assigned the stack participation anchor after Extreme Boundary proof; waiting for a future participation candle."
        state["state_transition_reason"] = reason
        return {
            "step": "Step 4",
            "status": "WAIT",
            "state": state,
            "next_step": "Step 4",
            "reason": reason,
            "events": list(interaction.get("events") or []) + [{"event": "step4_stack_candle_a_assigned", "reason": reason}],
        }
    if (
        previous_state.get("leg1_window_active") is True
        and previous_state.get("leg1_window_candle_index") == 0
        and not previous_state.get("participation_candidate_keys")
    ):
        interaction["opening_post_confirmation_relaxed_wick"] = True
        interaction["reserved_rejection_candle_b_evaluation"] = True
    result = evaluate_step4(interaction)
    if isinstance(result.get("state"), dict):
        state = result["state"]
        continuation_contract = lifecycle_lane_contract(state.get("lane_id") or interaction.get("lane_id"))
        if continuation_contract.get("lane_name") == "continuation":
            state["lane_id"] = state.get("lane_id") or interaction.get("lane_id")
            if continuation_contract.get("direction"):
                state["setup_direction"] = continuation_contract.get("direction")
            if continuation_contract.get("close_boundary") is not None:
                state["close_boundary"] = continuation_contract.get("close_boundary")
            if continuation_contract.get("extreme_boundary") is not None:
                state["extreme_boundary"] = continuation_contract.get("extreme_boundary")
            active_liquidity = state.get("active_liquidity") if isinstance(state.get("active_liquidity"), dict) else {}
            if continuation_contract.get("owner_name"):
                state["active_liquidity"] = {
                    **active_liquidity,
                    "name": continuation_contract.get("owner_name"),
                    "price": (
                        active_liquidity.get("price")
                        if active_liquidity.get("price") is not None
                        else continuation_contract.get("close_boundary")
                        if continuation_contract.get("close_boundary") is not None
                        else continuation_contract.get("extreme_boundary")
                    ),
                }
    if result.get("status") == "READY" and isinstance(result.get("state"), dict):
        state = result["state"]
        if (
            normalized_pathway_name(state.get("controlling_mode")) in {"S/R", "R/S"}
            and isinstance(state.get("reclaim_candle_a"), dict)
            and state.get("shared_leg1_uses_initial_candle_a") is True
        ):
            state["candle_a"] = state["reclaim_candle_a"]
            state["candle_a_source"] = "reclaim_candle_a"
        completed_at = state.get("step4_confirmed_at") or candle_timestamp(state.get("candle_b")) or candle_timestamp(state.get("latest_candle"))
        reference = state.get("step5_close_boundary") if state.get("step5_close_boundary") is not None else (state.get("active_leg1_reference") or state.get("leg1_reference"))
        state["leg1_state_locked"] = True
        state["step4_confirmed_at"] = completed_at
        state["leg1_completed_at"] = completed_at
        state["leg1_reference_price"] = reference
        state["leg1_reference_candle_time"] = completed_at
        state["leg1_direction"] = state.get("setup_direction")
        state["current_active_sequence_started_at"] = candle_timestamp(state.get("candle_a"))
        state["last_evaluated_candle_time"] = completed_at
        state["leg1_reference_extreme"] = state.get("leg2_sweep_extreme") or state.get("anchor_extreme") or state.get("leg1_extreme")
        state["fifty_percent_rule_phase"] = state.get("fifty_percent_rule_phase") or "pre_leg1_only"
        state["state_transition_reason"] = "Step 4 confirmed and locked."
    elif result.get("status") == "TERMINATED" and isinstance(result.get("state"), dict):
        result["state"].setdefault("invalidated_at", datetime.now(timezone.utc).isoformat())
        result["state"].setdefault("invalidation_source", "step4")
        result["state"].setdefault("invalidation_source_step", "Step 4")
        if (
            result.get("reason") == STEP2_STEP4_50_LINE_TOUCHED
            or result["state"].get("invalidation_source") == "step2_step4_50_line"
        ):
            source_candle_time = (
                result["state"].get("invalidation_source_candle_time")
                or result["state"].get("step2_step4_50_line_touched_at")
                or candle_timestamp(build_current_candle(snapshot))
            )
            active_liquidity = (
                result["state"].get("active_liquidity")
                if isinstance(result["state"].get("active_liquidity"), dict)
                else interaction.get("active_liquidity")
                if isinstance(interaction.get("active_liquidity"), dict)
                else None
            )
            consumed_record = invalidation_consumed_liquidity_record(
                active_liquidity,
                reason=result.get("reason"),
                exhaustion_type="step2_step4_50_percent_invalidation",
                invalidation_source="step2_step4_50_line",
                invalidation_source_step="Step 4",
                source_candle_time=source_candle_time,
                invalidated_at=result["state"].get("invalidated_at"),
            )
            if isinstance(consumed_record, dict):
                result["state"]["consumed_liquidity_levels"] = merge_consumed_liquidity_levels(
                    consumed_liquidity_levels(persisted_state),
                    result["state"].get("consumed_liquidity_levels"),
                    [consumed_record],
                )
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
    if step4_state.get("lane_id") and previous_state.get("lane_id") != step4_state.get("lane_id"):
        previous_step5 = {}
        previous_state = {}

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
    invalidated = invalidation_consumed_liquidity_record(
        active_liquidity,
        reason=step5_result.get("reason"),
        exhaustion_type="step4_step5_75_percent_invalidation",
        invalidation_source="anchor_extreme_close",
        invalidation_source_step="Step 5",
        source_candle_time=candle_timestamp(source_candle),
        invalidated_at=invalidated_at,
    ) or {
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
    if step5_state.get("lane_id") and previous_state.get("lane_id") != step5_state.get("lane_id"):
        previous_step6 = {}
        previous_state = {}

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
    interaction["step6_intrabar_path"] = snapshot.get("step6_intrabar_path")
    interaction["step6_intrabar_previous_minute_path"] = matching_step6_intrabar_previous_minute_path(snapshot, current_candle)
    interaction["step6_intrabar_previous_minute_path_available"] = interaction["step6_intrabar_previous_minute_path"] is not None
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


def matching_step6_intrabar_previous_minute_path(snapshot: dict[str, Any], candle: dict[str, Any] | None) -> dict[str, Any] | None:
    path = snapshot.get("step6_intrabar_path") if isinstance(snapshot, dict) else None
    if not isinstance(path, dict):
        return None
    previous_minute = path.get("previous_minute")
    if not isinstance(previous_minute, dict):
        return None
    if previous_minute.get("truncated") is True:
        return None
    candle_time = candle_timestamp(candle) if isinstance(candle, dict) else None
    minute = previous_minute.get("minute")
    if not candle_time or not isinstance(minute, str):
        return None
    if not same_candle_time(minute, candle_time):
        return None
    return previous_minute


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


@entry_state_transaction
@evaluation_mode_from_persist
def run_once(symbol: str = "NQ", persist: bool = True) -> dict[str, Any]:
    """Evaluate one symbol in authoritative or projection mode without routing orders."""
    persisted_state = load_entry_state()
    requested_symbol = str(symbol or "NQ").strip().upper()
    normalized_symbol = root_symbol(requested_symbol)
    if normalized_symbol not in SUPPORTED_ROOT_SYMBOLS:
        return unsupported_symbol_result(requested_symbol)
    snapshot = get_latest_market_snapshot(normalized_symbol)
    snapshot["requested_symbol"] = requested_symbol
    snapshot["normalized_symbol"] = normalized_symbol
    snapshot["raw_tv_context"] = load_raw_tv_context(normalized_symbol)
    snapshot["tv_context"] = load_tv_context(normalized_symbol)
    snapshot["live_tv_context"] = snapshot["raw_tv_context"] if isinstance(snapshot.get("raw_tv_context"), dict) else snapshot["tv_context"]
    snapshot["tv_context_status"] = tv_context_freshness_status(snapshot["tv_context"])
    snapshot["effective_session_date"], snapshot["session_authority_source"] = resolve_snapshot_session_authority(snapshot)
    snapshot["rithmic_session_date"] = local_session_date(snapshot.get("latest_bar_time"))
    snapshot["tradingview_session_date"] = tv_context_session_date(snapshot["raw_tv_context"] if isinstance(snapshot.get("raw_tv_context"), dict) else snapshot.get("tv_context"))
    snapshot["session_context_actionable"] = tv_context_actionable_for_session(
        snapshot["live_tv_context"],
        snapshot["effective_session_date"],
    )
    snapshot["session_context_stale"] = (
        isinstance(snapshot.get("tradingview_session_date"), str)
        and isinstance(snapshot.get("effective_session_date"), str)
        and snapshot["tradingview_session_date"] < snapshot["effective_session_date"]
    )
    persisted_state = sanitize_stale_session_state(
        persisted_state,
        normalized_symbol,
        snapshot_session_date(snapshot),
    )
    persisted_state = apply_observation_cycle_reset(persisted_state, normalized_symbol, snapshot)
    snapshot["session_liquidity_context"] = locked_session_liquidity_context(persisted_state, normalized_symbol)
    snapshot["pre_open_observed_extreme"] = pre_open_observed_extreme(persisted_state, normalized_symbol)
    snapshot["tv_context"] = effective_session_tv_context(
        persisted_state,
        normalized_symbol,
        snapshot.get("live_tv_context"),
        snapshot.get("effective_session_date"),
    )
    snapshot["session_context_actionable"] = tv_context_actionable_for_session(
        snapshot["tv_context"],
        snapshot["effective_session_date"],
    )
    symbol_persisted_state = symbol_scoped_persisted_state(persisted_state, normalized_symbol)
    session_lock_reason = session_lock_block_reason(persisted_state, normalized_symbol)
    if not session_lock_reason:
        session_lock_reason = session_authority_block_reason(snapshot)
    if snapshot.get("session_context_stale") and has_active_tv_levels(snapshot.get("raw_tv_context")):
        snapshot["session_context_stale"] = True
    else:
        snapshot["session_context_stale"] = False
    levels = active_levels_from_tv_context(snapshot["tv_context"])
    liquidity = classify_liquidity_location(
        snapshot.get("latest_price"),
        levels,
        normalized_symbol,
    )
    snapshot["liquidity"] = liquidity
    tick_size = float(liquidity.get("tick_size") or 0.25)
    if session_lock_reason:
        snapshot["step_2_1a"] = blocked_step_2_1a_result(tick_size, session_lock_reason)
        snapshot["rejection"] = {"rejection_mode": "OFF", "reason_text": session_lock_reason}
        snapshot["step25"] = no_active_liquidity_result("Step 2.5", session_lock_reason)
        snapshot["step3"] = no_active_liquidity_result("Step 3", session_lock_reason)
        snapshot["step4"] = no_active_liquidity_result("Step 4", session_lock_reason)
        snapshot["step5"] = no_active_liquidity_result("Step 5", session_lock_reason)
        snapshot["step6"] = no_active_liquidity_result("Step 6", session_lock_reason)
        snapshot["gateway"] = no_active_liquidity_result("Gateway", session_lock_reason)
        snapshot["trade_state"] = {"active": False, "released": False, "release_reason": None}
        snapshot["market_state"] = {"active_liquidity_name": None, "selected_liquidity_name": None}
        snapshot["atr"] = load_rithmic_atr_snapshot(normalized_symbol)
        if persist:
            append_entry_agent_audit_row(snapshot)
            persist_state(snapshot)
        return snapshot
    if before_entry_authorization(snapshot):
        observation_reason = "Observation window active until 06:30 PT; session liquidity context is locked and pathway activation is disabled."
        observed_extreme = merged_pre_open_observed_extreme(
            snapshot.get("pre_open_observed_extreme") if isinstance(snapshot.get("pre_open_observed_extreme"), dict) else None,
            observed_pre_open_extreme_from_snapshot(snapshot, tick_size),
        )
        snapshot["pre_open_observed_extreme"] = observed_extreme
        if persist:
            persist_pre_open_observed_extreme(snapshot, normalized_symbol, observed_extreme)
        snapshot["step_2_1a"] = blocked_step_2_1a_result(tick_size, observation_reason)
        snapshot["rejection"] = {"rejection_mode": "OFF", "reason_text": observation_reason}
        snapshot["step25"] = no_active_liquidity_result("Step 2.5", observation_reason)
        snapshot["step3"] = no_active_liquidity_result("Step 3", observation_reason)
        snapshot["step4"] = no_active_liquidity_result("Step 4", observation_reason)
        snapshot["step5"] = no_active_liquidity_result("Step 5", observation_reason)
        snapshot["step6"] = no_active_liquidity_result("Step 6", observation_reason)
        snapshot["gateway"] = no_active_liquidity_result("Gateway", observation_reason)
        snapshot["atr"] = load_rithmic_atr_snapshot(normalized_symbol)
        if persist:
            append_entry_agent_audit_row(snapshot)
            persist_state(snapshot)
        return snapshot
    step_2_1a = evaluate_live_step_2_1a(snapshot, levels, liquidity, persisted_state)
    if step2_owner_rotation_released(step_2_1a, normalized_symbol):
        symbol_persisted_state = reset_symbol_state_for_owner_rotation(symbol_persisted_state, step_2_1a)
        snapshot["owner_rotation_released"] = True
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
        clear_downstream_state_without_active_liquidity(snapshot, symbol_persisted_state)
    else:
        snapshot["step6"] = evaluate_live_step6(snapshot, snapshot["step5"], symbol_persisted_state)
    step4_mode = normalized_pathway_name((step4_state or {}).get("controlling_mode"))
    if (
        isinstance(snapshot["step5"].get("state"), dict)
        and snapshot["step5"]["state"].get("invalidated_at")
        and step4_mode not in {"S/R", "R/S"}
    ):
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
            "next_step": "Step 4",
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
    snapshot = apply_confirmed_lifecycle_invariants(snapshot, symbol_persisted_state)
    mask_unconfirmed_step4_leg1_invalidation(
        snapshot,
        "Monitoring current 1-minute candle until close confirmation.",
    )
    if persist:
        record_submitted_entry_setup(snapshot)
    apply_consumed_entry_setup_projection_guard(snapshot)
    snapshot["rejection_lane"], snapshot["continuation_lane"] = snapshot_lane_statuses(snapshot, symbol_persisted_state)
    snapshot["trade_state"] = build_trade_state_snapshot(snapshot)
    snapshot["market_state"] = build_market_state_snapshot(snapshot)
    if persist:
        persist_confirmed_rejection_anchor_from_authoritative_snapshot(snapshot, {})
        append_entry_agent_audit_row(snapshot)
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
    step2_window_terminated = step2_lifecycle_window_terminated(snapshot, step_2_1a, snapshot.get("step4"))

    locked_owner = step_2_1a.get("step2_locked_owner") if isinstance(step_2_1a.get("step2_locked_owner"), dict) else {}
    locked_active = locked_owner.get("active_liquidity") if isinstance(locked_owner.get("active_liquidity"), dict) else {}
    if (
        not step2_window_terminated
        and
        step_2_1a.get("step_2_activated") is True
        and locked_owner.get("pathway") == "rejection"
        and valid_active_liquidity_selection(locked_active.get("name"), locked_active.get("price"))
    ):
        return locked_active.get("display_name") or locked_active.get("name"), locked_active.get("price")

    last_interacted = step_2_1a.get("last_interacted_liquidity")
    if not step2_window_terminated:
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
        frozen_group = frozen_session_group_for_liquidity(snapshot, selected_liquidity.get("name"), selected_liquidity.get("price"))
        display_name = (
            (frozen_group or {}).get("display_name")
            or selected_liquidity.get("display_name")
            or selected_liquidity.get("name")
        )
        return display_name, selected_liquidity.get("price")

    return None, None


def active_liquidity_group_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Return selected ACTIVE stack group details when the selected liquidity is stacked."""
    if snapshot.get("suppress_active_liquidity") is True:
        return None
    step_2_1a = snapshot.get("step_2_1a") if isinstance(snapshot.get("step_2_1a"), dict) else {}
    step2_window_terminated = step2_lifecycle_window_terminated(snapshot, step_2_1a, snapshot.get("step4"))
    locked_owner = step_2_1a.get("step2_locked_owner") if isinstance(step_2_1a.get("step2_locked_owner"), dict) else {}
    locked_group = locked_owner.get("active_liquidity_group") if isinstance(locked_owner.get("active_liquidity_group"), dict) else None
    if (
        not step2_window_terminated
        and step_2_1a.get("step_2_activated") is True
        and locked_owner.get("pathway") == "rejection"
        and locked_group
    ):
        return locked_group
    if not step2_window_terminated:
        group = step_2_1a.get("active_liquidity_group")
        if isinstance(group, dict):
            frozen_group = frozen_session_group_for_liquidity(
                snapshot,
                step_2_1a.get("active_level"),
                step_2_1a.get("level_price"),
            )
            return merge_frozen_group_with_active_boundary(frozen_group, group) if isinstance(frozen_group, dict) else group
        last_interacted = step_2_1a.get("last_interacted_liquidity")
        group = (last_interacted or {}).get("group") if isinstance(last_interacted, dict) else None
        if isinstance(group, dict):
            frozen_group = frozen_session_group_for_liquidity(
                snapshot,
                (last_interacted or {}).get("name"),
                (last_interacted or {}).get("price"),
            )
            return merge_frozen_group_with_active_boundary(frozen_group, group) if isinstance(frozen_group, dict) else group
    liquidity = snapshot.get("liquidity") if isinstance(snapshot.get("liquidity"), dict) else {}
    selected_liquidity = selected_active_liquidity_from_context(
        snapshot.get("tv_context"),
        snapshot.get("latest_price"),
        snapshot.get("ohlc") if isinstance(snapshot.get("ohlc"), dict) else None,
        float((liquidity or {}).get("tick_size") or 0.25),
    )
    if isinstance(selected_liquidity, dict):
        frozen_group = frozen_session_group_for_liquidity(
            snapshot,
            selected_liquidity.get("name"),
            selected_liquidity.get("price"),
        )
        if isinstance(frozen_group, dict):
            return frozen_group
    group = selected_liquidity.get("group") if selected_liquidity else None
    return group if isinstance(group, dict) else None


def public_observation_liquidity_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Return the observation-window display liquidity from the locked session context only."""
    if not before_entry_authorization(snapshot):
        return None
    liquidity = snapshot.get("liquidity") if isinstance(snapshot.get("liquidity"), dict) else {}
    tick_size = float((liquidity or {}).get("tick_size") or 0.25)
    selected = selected_active_liquidity_from_context(
        snapshot.get("tv_context"),
        snapshot.get("latest_price"),
        snapshot.get("ohlc") if isinstance(snapshot.get("ohlc"), dict) else None,
        tick_size,
    )
    if not isinstance(selected, dict):
        return None
    group = selected.get("group") if isinstance(selected.get("group"), dict) else None
    display_name = (
        (group or {}).get("display_name")
        or selected.get("display_name")
        or selected.get("name")
    )
    display_price = optional_float((group or {}).get("close_boundary"))
    if display_price is None:
        display_price = optional_float(selected.get("price"))
    if display_price is None or not display_name:
        return None
    return {
        "name": display_name,
        "price": display_price,
        "side": selected.get("side"),
        "group": group,
        "source_level": selected.get("name"),
    }


def first_invalidation_reason(*results: dict[str, Any]) -> str | None:
    """Return the first invalidation reason from evaluated steps."""
    for result in results:
        if decision_status(result) == "INVALIDATE":
            return result_reason(result, "Invalidated by EntryAgent rule.")
    return None


def result_lane_name(result: dict[str, Any] | None) -> str | None:
    """Return the lifecycle lane associated with one engine result when available."""
    if not isinstance(result, dict):
        return None
    state = result.get("state") if isinstance(result.get("state"), dict) else {}
    lane_contract = lifecycle_lane_contract(state.get("lane_id"))
    lane_name = str(lane_contract.get("lane_name") or "").strip().lower()
    return lane_name or None


def first_invalidation_reason_for_lane(lane_name: str, *results: dict[str, Any]) -> str | None:
    """Return the first invalidation reason that belongs to the requested lifecycle lane."""
    expected_lane = str(lane_name or "").strip().lower()
    for result in results:
        if decision_status(result) != "INVALIDATE":
            continue
        result_lane = result_lane_name(result)
        if result_lane and result_lane != expected_lane:
            continue
        if not result_lane and expected_lane != "rejection":
            continue
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
        reason = result_reason(result, "Invalidated by EntryAgent rule.")
        step2_step4_guard = reason == STEP2_STEP4_50_LINE_TOUCHED
        step6_window_expired = (
            current_step == "Step 5"
            and source_step == "Step 6"
            and isinstance(result.get("state"), dict)
            and result["state"].get("step6_window_candle_index") is not None
            and result["state"].get("step6_window_remaining") == 0
        )
        if step_order(source_step) <= public_order or step6_window_expired or step2_step4_guard:
            state = result.get("state") if isinstance(result.get("state"), dict) else {}
            return {
                "reason": reason,
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


def public_invalidation_from_results_for_lane(
    current_step: str,
    lane_name: str,
    *results: dict[str, Any],
) -> dict[str, Any]:
    """Expose invalidation only for the requested lifecycle lane."""
    public_order = step_order(current_step)
    expected_lane = str(lane_name or "").strip().lower()
    for result in results:
        if decision_status(result) != "INVALIDATE":
            continue
        result_lane = result_lane_name(result)
        if result_lane and result_lane != expected_lane:
            continue
        if not result_lane and expected_lane != "rejection":
            continue
        source_step = result_invalidation_source_step(result)
        reason = result_reason(result, "Invalidated by EntryAgent rule.")
        step2_step4_guard = reason == STEP2_STEP4_50_LINE_TOUCHED
        step6_window_expired = (
            current_step == "Step 5"
            and source_step == "Step 6"
            and isinstance(result.get("state"), dict)
            and result["state"].get("step6_window_candle_index") is not None
            and result["state"].get("step6_window_remaining") == 0
        )
        if step_order(source_step) <= public_order or step6_window_expired or step2_step4_guard:
            state = result.get("state") if isinstance(result.get("state"), dict) else {}
            return {
                "reason": reason,
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
    step2 = snapshot.get("step_2_1a") if isinstance(snapshot.get("step_2_1a"), dict) else {}
    leg1_ready = leg1_publication_locked(snapshot, step4)
    leg2_ready = leg2_publication_locked(snapshot, step5)
    step5_state = step5.get("state") if isinstance(step5.get("state"), dict) else {}
    step6_state = step6.get("state") if isinstance(step6.get("state"), dict) else {}
    step2_window_terminated = step2_lifecycle_window_terminated(snapshot, step2, step4)

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
    if step2_window_terminated:
        return "Step 1"

    if step4.get("next_step") == "Step 4" and not step3_publication_passed(step3):
        reason = "Step 4 publication blocked until Step 3 officially passes."
        add_publication_gate_debug(snapshot, "Step 4", "Step 2", reason)
        return "Step 2"
    return "Step 2"


def wait_reason_for_current_step(
    current_step: str,
    active_name: Any,
    step2_confirmed: bool,
    step4: dict[str, Any],
    step5: dict[str, Any],
    step6: dict[str, Any],
) -> str:
    """Return operator-facing text without redefining current_step as the next watched step."""
    if current_step == "Step 1":
        return "Waiting for a valid liquidity-close activation."
    if current_step == "Step 2" and not active_name:
        return "No active liquidity selected."
    if current_step == "Step 2":
        if not step2_confirmed:
            return "Step 2 waiting for a valid liquidity-close activation."
        return "Step 2 confirmed: liquidity close activated a valid pathway; public state holds at this milestone until Step 4 confirms."
    if current_step in {"Step 2.5", "Step 3", "Step 4"}:
        return translate_public_terminology(result_reason(step4, "Leg 1 waiting for Step 4 requirements."))
    if current_step == "Step 5":
        return result_reason(step5, "Leg 2 waiting for Step 5 requirements.")
    if current_step == "Step 6":
        step6_state = step6.get("state") if isinstance(step6.get("state"), dict) else {}
        if step6_state.get("extended_retrace_pending") is True and step6_state.get("extended_retrace_block_reason"):
            return str(step6_state.get("extended_retrace_block_reason"))
        return translate_public_terminology(result_reason(step6, "Entry candidate waiting for Step 6 requirements."))
    return translate_public_terminology(result_reason(step6, result_reason(step5, result_reason(step4, "Waiting for EntryAgent setup requirements."))))


def current_step_public_status(current_step: str, active_name: Any, rejection_active: bool) -> str:
    """Return the public milestone status used by UI surfaces."""
    if current_step == "Step 2" and active_name and rejection_active:
        return "CONFIRMED"
    if current_step in {"Step 4", "Step 5", "Step 6"}:
        return "CONFIRMED"
    return "WAIT"


def public_step_status(value: Any, *, step_name: str) -> str:
    """Collapse internal step states into the operator-facing WAIT/CONFIRMED/TERMINATED contract."""
    text = str(value or "").strip().upper()
    if text in {"TERMINATED", "INVALID", "INVALIDATED", "BLOCKED"}:
        return "TERMINATED"
    if text in {"BLOCKED_PREOPEN_OBSERVATION", "WAITING_FOR_CANDLE_B", "WAITING_FOR_STEP_4", "WAIT"}:
        return "WAIT"
    if step_name == "Step 4" and text == "READY":
        return "CONFIRMED"
    if text in {"CONFIRMED", "ENTRY_CONFIRMED"}:
        return "CONFIRMED"
    return "WAIT"


def continuation_public_step2_reason(
    base_reason: Any,
    *,
    controlling: bool,
    invalidation_reason: Any,
    step4_status: Any,
) -> str | None:
    """Return the operator-facing continuation Step 2 reason without stale eligibility text."""
    if invalidation_reason:
        return str(invalidation_reason)
    if not controlling:
        return str(base_reason) if base_reason else None
    if public_step_status(step4_status, step_name="Step 4") == "CONFIRMED":
        return "Continuation Step 2 confirmed; lane frozen and controlling."
    return "Continuation Step 2 confirmed; lane frozen and controlling. Waiting for Step 4 participation."


def continuation_public_step4_reason(
    base_reason: Any,
    *,
    controlling: bool,
    invalidation_reason: Any,
    step4_status: Any,
) -> str | None:
    """Return the operator-facing continuation Step 4 reason aligned to public lifecycle state."""
    if invalidation_reason:
        return str(invalidation_reason)
    public_status = public_step_status(step4_status, step_name="Step 4")
    if public_status == "CONFIRMED":
        if str(base_reason or "").strip() == "Leg 1 locked; Step 4 not re-evaluated on status refresh.":
            return "Step 4 confirmed and locked."
        return str(base_reason) if base_reason else "Step 4 confirmed and locked."
    if controlling:
        return str(base_reason) if base_reason else "Step 4 waiting for participation confirmation."
    return None


def confirmed_time_from_candle(candle: Any) -> str | None:
    """Return a candle close timestamp from a candle-like dict."""
    return candle_timestamp(candle if isinstance(candle, dict) else None)


def step2_confirmed_at(snapshot: dict[str, Any], step_2_1a: dict[str, Any], current_step_status: str) -> str | None:
    """Return the Step 2 liquidity-close confirmation candle time."""
    confirmed_at, _anchor_status, _anchor_reason = step2_anchor_publication_state(snapshot, step_2_1a, current_step_status)
    return confirmed_at


def step2_anchor_publication_state(
    snapshot: dict[str, Any],
    step_2_1a: dict[str, Any],
    current_step_status: str,
) -> tuple[str | None, str | None, str | None]:
    """Return public Step 2 anchor publication data without drifting to the latest candle."""
    if current_step_status != "CONFIRMED" or step_2_1a.get("step_2_activated") is not True:
        return None, None, None
    frozen_anchor_time = snapshot.get("frozen_step2_anchor_time")
    if isinstance(frozen_anchor_time, str) and frozen_anchor_time.strip():
        return frozen_anchor_time, "FROZEN", None
    locked_owner = step_2_1a.get("step2_locked_owner") if isinstance(step_2_1a.get("step2_locked_owner"), dict) else None
    if isinstance(locked_owner, dict) and locked_owner.get("pathway") == "rejection" and locked_owner.get("activated_at"):
        return str(locked_owner.get("activated_at")), "FROZEN", None
    candle_a_time = confirmed_time_from_candle(step_2_1a.get("candle_a"))
    if candle_a_time:
        return candle_a_time, "FROZEN", None
    return None, "UNKNOWN", "MISSING_ANCHOR"


def step2_owner_name(snapshot: dict[str, Any], step_2_1a: dict[str, Any]) -> str | None:
    """Return the public Step 2 owner display name when one exists."""
    frozen_owner_name = snapshot.get("frozen_step2_owner_name")
    if isinstance(frozen_owner_name, str) and frozen_owner_name.strip():
        return frozen_owner_name
    owner = step_2_1a.get("step2_locked_owner") if isinstance(step_2_1a.get("step2_locked_owner"), dict) else {}
    active = owner.get("active_liquidity") if isinstance(owner.get("active_liquidity"), dict) else {}
    group = owner.get("active_liquidity_group") if isinstance(owner.get("active_liquidity_group"), dict) else active.get("group") if isinstance(active.get("group"), dict) else None
    explicit_display_name = (
        owner.get("active_liquidity_display_name")
        or active.get("display_name")
        or (group.get("display_name") if isinstance(group, dict) else None)
    )
    if isinstance(explicit_display_name, str) and explicit_display_name.strip():
        return public_active_liquidity_name(explicit_display_name)
    return public_active_liquidity_display_name(
        snapshot,
        group,
        owner.get("active_liquidity_name") or active.get("name") or step_2_1a.get("active_level"),
        owner.get("active_liquidity_price") if owner.get("active_liquidity_price") is not None else active.get("price") if active.get("price") is not None else step_2_1a.get("level_price"),
    )


def step4_owner_name(snapshot: dict[str, Any], step4_state: dict[str, Any]) -> str | None:
    """Return the public Step 4 owner display name when one exists."""
    active = step4_state.get("active_liquidity") if isinstance(step4_state.get("active_liquidity"), dict) else {}
    group = active.get("group") if isinstance(active.get("group"), dict) else None
    explicit_display_name = active.get("display_name") or (group.get("display_name") if isinstance(group, dict) else None)
    if isinstance(explicit_display_name, str) and explicit_display_name.strip():
        return public_active_liquidity_name(explicit_display_name)
    display_name = public_active_liquidity_display_name(
        snapshot,
        group,
        active.get("name"),
        active.get("price"),
    )
    if display_name:
        return display_name
    step2 = snapshot.get("step_2_1a") if isinstance(snapshot.get("step_2_1a"), dict) else {}
    return step2_owner_name(snapshot, step2)


def locked_trade_lifecycle_owner(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Return the frozen trade owner once Step 4 confirms, keeping market-state owner changes separate."""
    step4 = snapshot.get("step4") if isinstance(snapshot.get("step4"), dict) else {}
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    step5 = snapshot.get("step5") if isinstance(snapshot.get("step5"), dict) else {}
    step5_state = step5.get("state") if isinstance(step5.get("state"), dict) else {}
    step6 = snapshot.get("step6") if isinstance(snapshot.get("step6"), dict) else {}
    confirmed_at = step4_state.get("step4_confirmed_at") or step4_state.get("leg1_completed_at")
    if not confirmed_at:
        return None
    if step5_state.get("invalidated_at"):
        return None
    if decision_status(step6) == "CONFIRM":
        return None
    step2 = snapshot.get("step_2_1a") if isinstance(snapshot.get("step_2_1a"), dict) else {}
    owner = step2.get("step2_locked_owner") if isinstance(step2.get("step2_locked_owner"), dict) else {}
    active = owner.get("active_liquidity") if isinstance(owner.get("active_liquidity"), dict) else {}
    group = (
        owner.get("active_liquidity_group")
        if isinstance(owner.get("active_liquidity_group"), dict)
        else active.get("group")
        if isinstance(active.get("group"), dict)
        else None
    )
    name = owner.get("active_liquidity_name") or active.get("name") or step2.get("active_level")
    price = (
        owner.get("active_liquidity_price")
        if owner.get("active_liquidity_price") is not None
        else active.get("price")
        if active.get("price") is not None
        else step2.get("level_price")
    )
    if not valid_active_liquidity_selection(name, price):
        return None
    return {
        "name": name,
        "display_name": public_active_liquidity_display_name(snapshot, group, name, price),
        "price": price,
        "group": group if isinstance(group, dict) else None,
        "group_name": (group or {}).get("name") if isinstance(group, dict) else owner.get("liquidity_group"),
        "group_display_name": (group or {}).get("display_name") if isinstance(group, dict) else owner.get("active_liquidity_display_name"),
        "close_boundary": owner.get("close_boundary"),
        "extreme_boundary": owner.get("extreme_boundary"),
        "wick_boundary_extreme": owner.get("wick_boundary_extreme"),
        "step2_owner_name": step2_owner_name(snapshot, step2),
    }


def active_trade_lane(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Return the currently active frozen trade lane, keeping market discovery separate."""
    rejection_lane = snapshot.get("rejection_lane") if isinstance(snapshot.get("rejection_lane"), dict) else {}
    continuation_lane = snapshot.get("continuation_lane") if isinstance(snapshot.get("continuation_lane"), dict) else {}
    for lane in (rejection_lane, continuation_lane):
        if lane.get("lane_status") in {"controlling", "frozen", "invalidated"} and valid_active_liquidity_selection(
            lane.get("active_liquidity_name"),
            lane.get("active_liquidity_price"),
        ):
            return lane
    return None


def trade_state_release_reason(snapshot: dict[str, Any]) -> str | None:
    """Return the lifecycle release reason once the frozen trade state should no longer control public output."""
    step2 = snapshot.get("step_2_1a") if isinstance(snapshot.get("step_2_1a"), dict) else {}
    step4 = snapshot.get("step4") if isinstance(snapshot.get("step4"), dict) else {}
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    step5 = snapshot.get("step5") if isinstance(snapshot.get("step5"), dict) else {}
    step5_state = step5.get("state") if isinstance(step5.get("state"), dict) else {}
    step6 = snapshot.get("step6") if isinstance(snapshot.get("step6"), dict) else {}
    step4_confirmed = bool(step4_state.get("step4_confirmed_at") or step4_state.get("leg1_completed_at"))
    if step2_owner_rotation_released(
        step2,
        str(snapshot.get("normalized_symbol") or snapshot.get("symbol") or ""),
    ):
        return str(step2.get("state_transition_reason") or SAME_SIDE_NEXT_LIQUIDITY_OWNER_ROTATION)
    if step2.get("step2_invalidated_at") and not step4_confirmed:
        return "step2_invalidated"
    if step4_state.get("invalidated_at") and not step4_confirmed:
        return "step4_invalidated"
    if step5_state.get("invalidated_at"):
        return "step5_invalidated"
    if decision_status(step6) == "CONFIRM":
        return "trade_completed"
    return None


def build_trade_state_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return the frozen active trade lifecycle independent from the evolving market state."""
    lane = active_trade_lane(snapshot)
    step2 = snapshot.get("step_2_1a") if isinstance(snapshot.get("step_2_1a"), dict) else {}
    step4 = snapshot.get("step4") if isinstance(snapshot.get("step4"), dict) else {}
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    step25 = snapshot.get("step25") if isinstance(snapshot.get("step25"), dict) else {}
    step25_state = step25.get("state") if isinstance(step25.get("state"), dict) else {}
    frozen_owner = locked_trade_lifecycle_owner(snapshot)
    step2_owner = step2.get("step2_locked_owner") if isinstance(step2.get("step2_locked_owner"), dict) else {}
    owner_active = step2_owner.get("active_liquidity") if isinstance(step2_owner.get("active_liquidity"), dict) else {}
    group = (
        frozen_owner.get("group")
        if isinstance(frozen_owner, dict) and isinstance(frozen_owner.get("group"), dict)
        else step2_owner.get("active_liquidity_group")
        if isinstance(step2_owner.get("active_liquidity_group"), dict)
        else owner_active.get("group")
        if isinstance(owner_active.get("group"), dict)
        else None
    )
    lane_name = lane.get("lane_name") if isinstance(lane, dict) else None
    raw_name = (
        frozen_owner.get("name")
        if isinstance(frozen_owner, dict) and frozen_owner.get("name")
        else step2_owner.get("active_liquidity_name")
        or owner_active.get("name")
        or (lane.get("active_liquidity_name") if isinstance(lane, dict) else None)
    )
    raw_price = (
        frozen_owner.get("price")
        if isinstance(frozen_owner, dict) and frozen_owner.get("price") is not None
        else step2_owner.get("active_liquidity_price")
        if step2_owner.get("active_liquidity_price") is not None
        else owner_active.get("price")
        if owner_active.get("price") is not None
        else lane.get("active_liquidity_price")
        if isinstance(lane, dict)
        else None
    )
    release_reason = trade_state_release_reason(snapshot)
    active = bool(
        lane_name in {"rejection", "continuation"}
        and valid_active_liquidity_selection(raw_name, raw_price)
        and release_reason is None
    )
    owner_display = public_active_liquidity_display_name(snapshot, group, raw_name, raw_price)
    selected_pathway = (
        snapshot.get("frozen_step4_selected_pathway")
        if isinstance(snapshot.get("frozen_step4_selected_pathway"), str)
        else lane_name
    )
    return {
        "active": active,
        "released": release_reason is not None,
        "release_reason": release_reason,
        "lane_name": lane_name,
        "selected_pathway": selected_pathway,
        "owner": owner_display,
        "active_liquidity_name": owner_display,
        "selected_liquidity_name": raw_name,
        "active_liquidity_price": raw_price,
        "liquidity_group": (
            frozen_owner.get("group_name")
            if isinstance(frozen_owner, dict) and frozen_owner.get("group_name") is not None
            else (group or {}).get("name") if isinstance(group, dict)
            else (lane.get("liquidity_group") if isinstance(lane, dict) else None)
        ),
        "active_liquidity_group": copy.deepcopy(group) if isinstance(group, dict) else None,
        "close_boundary": (
            frozen_owner.get("close_boundary")
            if isinstance(frozen_owner, dict) and frozen_owner.get("close_boundary") is not None
            else step2_owner.get("close_boundary")
            if step2_owner.get("close_boundary") is not None
            else (lane.get("close_boundary") if isinstance(lane, dict) else None)
        ),
        "extreme_boundary": (
            frozen_owner.get("extreme_boundary")
            if isinstance(frozen_owner, dict) and frozen_owner.get("extreme_boundary") is not None
            else step2_owner.get("extreme_boundary")
            if step2_owner.get("extreme_boundary") is not None
            else (lane.get("extreme_boundary") if isinstance(lane, dict) else None)
        ),
        "wick_boundary_extreme": (
            frozen_owner.get("wick_boundary_extreme")
            if isinstance(frozen_owner, dict) and frozen_owner.get("wick_boundary_extreme") is not None
            else step2_owner.get("wick_boundary_extreme")
            if step2_owner.get("wick_boundary_extreme") is not None
            else (lane.get("wick_boundary_extreme") if isinstance(lane, dict) else None)
        ),
        "step2": {
            "confirmed_at": snapshot.get("frozen_step2_anchor_time") or step2.get("step2_activated_at"),
            "owner_seeded_at": step2.get("step2_owner_seeded_at"),
            "activated_at": step2.get("step2_activated_at"),
            "direction": snapshot.get("frozen_step2_direction") or step2_owner.get("setup_direction") or step25_state.get("setup_direction"),
            "window_started_at": step2.get("step2_activated_at"),
            "owner_name": owner_display,
        },
        "step4": {
            "confirmed_at": step4_state.get("step4_confirmed_at") or step4_state.get("leg1_completed_at"),
            "participation_confirmed": step4_state.get("leg1_state_locked") is True and str(step4_state.get("leg1_status") or "").upper() == "COMPLETE",
            "window_count": public_lifecycle_candle_count(step4_state.get("step4_window_count") or step4_state.get("participation_candidate_count")),
            "leg2_sweep_extreme": step4_state.get("leg2_sweep_extreme"),
            "step5_close_boundary": step4_state.get("step5_close_boundary"),
            "status": step4.get("status"),
            "direction": step4_state.get("setup_direction"),
        },
    }


def build_market_state_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return the evolving market-state view that may rotate independently from the active trade lifecycle."""
    liquidity = snapshot.get("liquidity") if isinstance(snapshot.get("liquidity"), dict) else {}
    ohlc = snapshot.get("ohlc") if isinstance(snapshot.get("ohlc"), dict) else {}
    active_name, active_price = active_liquidity_from_snapshot(snapshot)
    active_group = active_liquidity_group_from_snapshot(snapshot)
    selected_name = None
    if candle_close_confirmed(snapshot):
        selected_debug = selected_active_liquidity_from_context(
            snapshot.get("tv_context"),
            snapshot.get("latest_price"),
            ohlc,
            float((liquidity or {}).get("tick_size") or 0.25),
        )
        if isinstance(selected_debug, dict):
            selected_name = selected_debug.get("name")
    return {
        "active_liquidity_name": public_active_liquidity_display_name(snapshot, active_group, active_name, active_price),
        "selected_liquidity_name": selected_name,
        "active_liquidity_price": active_price,
        "active_liquidity_group": copy.deepcopy(active_group) if isinstance(active_group, dict) else None,
        "liquidity_group": (active_group or {}).get("name") if isinstance(active_group, dict) else None,
        "close_boundary": audit_boundary_value("close_boundary", active_group, None, {"price": active_price}, {}),
        "extreme_boundary": audit_boundary_value("extreme_boundary", active_group, None, {"price": active_price}, {}),
        "wick_boundary_extreme": audit_boundary_value("wick_boundary_extreme", active_group, None, {"price": active_price}, {}),
        "next_liquidity_above": copy.deepcopy(liquidity.get("nearest_level_above")),
        "next_liquidity_below": copy.deepcopy(liquidity.get("nearest_level_below")),
        "latest_price": snapshot.get("latest_price"),
        "candle_time": snapshot.get("latest_bar_time"),
    }


def public_lifecycle_candle_count(value: Any) -> int | None:
    """Return a public lifecycle candle count only when it is inside the 0..4 contract."""
    try:
        count = int(value)
    except (TypeError, ValueError):
        return None
    return count if 0 <= count <= 4 else None


def completed_candle_count_since_confirmation(snapshot: dict[str, Any], confirmed_at: Any) -> int | None:
    """Return completed 1-minute candles strictly after the confirmation candle."""
    confirmed_time = parse_candle_time(confirmed_at)
    current_time = parse_candle_time(snapshot.get("latest_bar_time"))
    if not confirmed_time or not current_time:
        return None
    delta_seconds = int((current_time - confirmed_time).total_seconds())
    if delta_seconds < 0:
        return None
    count = delta_seconds // 60
    if not candle_close_confirmed(snapshot) and not same_candle_time(confirmed_at, snapshot.get("latest_bar_time")):
        count -= 1
    return public_lifecycle_candle_count(max(0, count))


def stable_leg1_window_candle_count(
    snapshot: dict[str, Any],
    step4_state: dict[str, Any] | None,
    confirmed_at: Any,
) -> int | None:
    """Return a non-regressing Step 4 count derived from completed candle timestamps."""
    step4_state = step4_state if isinstance(step4_state, dict) else {}
    stored = public_lifecycle_candle_count(step4_state.get("leg1_window_candle_index"))
    derived = completed_candle_count_since_confirmation(snapshot, confirmed_at)
    if derived is None:
        return stored
    if stored is None:
        return derived
    return max(stored, derived)


def step2_candle_count(snapshot: dict[str, Any], step_2_1a: dict[str, Any]) -> int | None:
    """Return the completed-candle count since Step 2 confirmation, with confirmation candle = 0."""
    step4_state = ((snapshot.get("step4") or {}).get("state") or {}) if isinstance(((snapshot.get("step4") or {}).get("state") or {}), dict) else {}
    frozen_step4_count = public_lifecycle_candle_count(step4_state.get("step4_window_count") or step4_state.get("participation_candidate_count"))
    if (step4_state.get("step4_confirmed_at") or step4_state.get("leg1_completed_at")) and frozen_step4_count is not None:
        return frozen_step4_count
    if step2_lifecycle_window_terminated(snapshot, step_2_1a, snapshot.get("step4")):
        return None
    if step_2_1a.get("step_2_activated") is not True:
        return None
    activation_index = step_2_1a.get("step2_activation_candle_index")
    current_index = step_2_1a.get("candle_index")
    try:
        if activation_index is not None and current_index is not None:
            return public_lifecycle_candle_count(int(current_index) - int(activation_index))
    except (TypeError, ValueError):
        pass
    step4_index = step4_state.get("leg1_window_candle_index")
    try:
        if step4_index is not None:
            return public_lifecycle_candle_count(step4_index)
    except (TypeError, ValueError):
        pass

    confirmed_at = (
        step_2_1a.get("step2_activated_at")
        or ((step_2_1a.get("step2_locked_owner") or {}).get("activated_at") if isinstance(step_2_1a.get("step2_locked_owner"), dict) else None)
        or step2_confirmed_at(snapshot, step_2_1a, "CONFIRMED")
    )
    derived_count = completed_candle_count_since_confirmation(snapshot, confirmed_at)
    if derived_count is not None:
        return derived_count

    if confirmed_at and same_candle_time(confirmed_at, snapshot.get("latest_bar_time")):
        return 0
    return None


def step2_lifecycle_window_terminated(
    snapshot: dict[str, Any],
    step_2_1a: dict[str, Any] | None,
    step4: dict[str, Any] | None,
) -> bool:
    """Return True when the original Step 2 -> Step 4 evaluation window is no longer live."""
    step_2_1a = step_2_1a if isinstance(step_2_1a, dict) else {}
    if step_2_1a.get("step_2_activated") is not True:
        return False
    step4 = step4 if isinstance(step4, dict) else {}
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    locked_leg1_ok, _locked_leg1_reason = valid_participation_locked_leg1_state(step4_state)
    if locked_leg1_ok:
        return False
    if not step4_state.get("leg1_window_started_at"):
        return False
    if step4_state.get("leg1_window_invalidated") is True:
        return True
    if step4_state.get("leg1_window_remaining") == 0:
        return True
    if step4_state.get("leg1_window_active") is False:
        return True
    latest_time = parse_candle_time(snapshot.get("latest_bar_time"))
    expires_at = parse_candle_time(step4_state.get("leg1_window_expires_at"))
    if latest_time and expires_at and latest_time >= expires_at:
        return True
    return False


def lane_signature(lane: dict[str, Any] | None) -> tuple[Any, ...]:
    """Return the owner signature that defines one pathway lifecycle."""
    lane = lane if isinstance(lane, dict) else {}
    return (
        lane.get("liquidity_group"),
        lane.get("active_liquidity_price"),
        lane.get("close_boundary"),
        lane.get("extreme_boundary"),
        lane.get("wick_boundary_extreme"),
    )


def lane_owner_signature(lane: dict[str, Any] | None) -> tuple[Any, ...]:
    """Return the stable owner identity for freeze/carry-forward decisions."""
    lane = lane if isinstance(lane, dict) else {}
    return (
        lane.get("liquidity_group"),
        lane.get("active_liquidity_price"),
        lane.get("close_boundary"),
        lane.get("extreme_boundary"),
    )


def continuation_probe_boundary_price(step25_state: dict[str, Any] | None) -> float | None:
    """Return the carried continuation wick boundary from the internal continuation engine."""
    step25_state = step25_state if isinstance(step25_state, dict) else {}
    probe = step25_state.get("continuation_probe_boundary") if isinstance(step25_state.get("continuation_probe_boundary"), dict) else None
    if isinstance(probe, dict) and probe.get("active") is True:
        boundary = optional_float(probe.get("boundary_price"))
        if boundary is not None:
            return boundary
    return optional_float(step25_state.get("current_boundary"))


def continuation_group_with_probe_boundary(active_group: dict[str, Any] | None, step25_state: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the continuation owner with its public structural plus wick boundary bundle."""
    continuation_group = dict(active_group) if isinstance(active_group, dict) else active_group
    probe_boundary = continuation_probe_boundary_price(step25_state)
    if not isinstance(continuation_group, dict) or probe_boundary is None:
        return continuation_group
    side = str(continuation_group.get("side") or "")
    original_extreme = optional_float(continuation_group.get("extreme_boundary"))
    current_wick = optional_float(continuation_group.get("wick_boundary_extreme"))
    if original_extreme is None:
        return continuation_group
    candidate = optional_float(probe_boundary)
    if candidate is None:
        return continuation_group
    if side == "upper":
        if candidate >= original_extreme or (current_wick is not None and candidate >= current_wick):
            return continuation_group
    elif side == "lower":
        if candidate <= original_extreme or (current_wick is not None and candidate <= current_wick):
            return continuation_group
    else:
        return continuation_group
    updated = dict(continuation_group)
    updated["wick_boundary_extreme"] = candidate
    return updated


def rejection_lane_matches_active_owner(
    previous_lane: dict[str, Any] | None,
    active_group: dict[str, Any] | None,
    active_price: Any,
) -> bool:
    """Return True when a persisted rejection lane belongs to the current active owner."""
    if not isinstance(previous_lane, dict):
        return False
    group_name = (active_group or {}).get("name") if isinstance(active_group, dict) else None
    close_boundary = optional_float((active_group or {}).get("close_boundary")) if isinstance(active_group, dict) else None
    extreme_boundary = optional_float((active_group or {}).get("extreme_boundary")) if isinstance(active_group, dict) else None
    lane_price = optional_float(previous_lane.get("active_liquidity_price"))
    return (
        group_name == previous_lane.get("liquidity_group")
        and optional_float(active_price) == lane_price
        and close_boundary == optional_float(previous_lane.get("close_boundary"))
        and extreme_boundary == optional_float(previous_lane.get("extreme_boundary"))
    )


def rejection_invalidated_before_step4_completion(
    previous_symbol_state: dict[str, Any] | None,
    active_group: dict[str, Any] | None,
    active_price: Any,
) -> bool:
    """Return True when the current owner's rejection lane previously invalidated before a completed Step 4 handoff."""
    previous_symbol_state = previous_symbol_state if isinstance(previous_symbol_state, dict) else {}
    previous_lane = previous_symbol_state.get("rejection_lane") if isinstance(previous_symbol_state.get("rejection_lane"), dict) else None
    if not rejection_lane_matches_active_owner(previous_lane, active_group, active_price):
        return False
    if previous_lane.get("lane_status") != "invalidated":
        return False
    return str(previous_lane.get("step4_status") or "").upper() not in {"READY", "CONFIRMED"}


def rejection_step4_completed_for_owner(
    step4: dict[str, Any] | None,
    previous_symbol_state: dict[str, Any] | None,
    active_group: dict[str, Any] | None,
    active_price: Any,
) -> bool:
    """Return True when the current owner's rejection Step 4 has completed."""
    step4 = step4 if isinstance(step4, dict) else {}
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    current_status = str(step4.get("status") or "").upper()
    if current_status == "READY" or str(step4_state.get("leg1_status") or "").upper() == "COMPLETE":
        return True
    previous_symbol_state = previous_symbol_state if isinstance(previous_symbol_state, dict) else {}
    previous_lane = previous_symbol_state.get("rejection_lane") if isinstance(previous_symbol_state.get("rejection_lane"), dict) else None
    if not rejection_lane_matches_active_owner(previous_lane, active_group, active_price):
        return False
    return str(previous_lane.get("step4_status") or "").upper() in {"READY", "CONFIRMED"}


def frozen_rejection_trade_state_reference(
    previous_symbol_state: dict[str, Any] | None,
    active_level: Any,
    active_price: Any,
    active_group: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return the frozen rejection trade-state reference used to begin continuation evaluation."""
    previous_symbol_state = previous_symbol_state if isinstance(previous_symbol_state, dict) else {}
    trade_state = previous_symbol_state.get("trade_state") if isinstance(previous_symbol_state.get("trade_state"), dict) else {}
    if trade_state.get("active") is not True:
        return None
    if str(trade_state.get("selected_pathway") or trade_state.get("lane_name") or "").strip().lower() != "rejection":
        return None
    trade_owner_liquidity = trade_state_owner_liquidity(trade_state)
    current_owner_liquidity = {
        "name": active_level,
        "price": optional_float(active_price),
        "group": active_group if isinstance(active_group, dict) else None,
        "side": (active_group or {}).get("side") if isinstance(active_group, dict) else side_for_level(str(active_level or "")),
    }
    if isinstance(trade_owner_liquidity, dict) and not same_liquidity_owner(trade_owner_liquidity, current_owner_liquidity):
        return None
    trade_owner = str(trade_state.get("selected_liquidity_name") or trade_state.get("active_liquidity_name") or "").strip()
    current_owner = str(active_level or "").strip()
    boundary_price = optional_float(trade_state.get("close_boundary"))
    if boundary_price is None:
        boundary_price = optional_float(active_price)
    if boundary_price is None:
        return None
    step4 = trade_state.get("step4") if isinstance(trade_state.get("step4"), dict) else {}
    if not step4.get("confirmed_at"):
        return None
    return {
        "owner": trade_owner or current_owner or None,
        "boundary_type": "frozen_rejection_close_boundary",
        "boundary_price": boundary_price,
        "eligible_at": step4.get("confirmed_at"),
    }


def continuation_started_from_frozen_rejection(
    side: Any,
    previous_close: Any,
    current_close: Any,
    boundary_price: Any,
) -> bool:
    """Return True when price first violates the frozen rejection close boundary."""
    side = str(side or "").strip().lower()
    prev_close = optional_float(previous_close)
    close = optional_float(current_close)
    boundary = optional_float(boundary_price)
    if side == "upper":
        return prev_close is not None and close is not None and boundary is not None and prev_close >= boundary and close < boundary
    if side == "lower":
        return prev_close is not None and close is not None and boundary is not None and prev_close <= boundary and close > boundary
    return False


def continuation_close_confirms_active_boundary(
    side: Any,
    current_close: Any,
    boundary_price: Any,
) -> bool:
    """Return True when the latest close confirms Step 2 Continuation through the active boundary."""
    side = str(side or "").strip().lower()
    close = optional_float(current_close)
    boundary = optional_float(boundary_price)
    if close is None or boundary is None:
        return False
    if side == "upper":
        return close < boundary
    if side == "lower":
        return close > boundary
    return False


def wick_adjusted_continuation_boundary(
    side: Any,
    active_boundary: Any,
    candle: dict[str, Any] | None,
) -> float | None:
    """Return a more extreme continuation boundary only for wick-only breaches that fail to close through."""
    candle = candle if isinstance(candle, dict) else {}
    side = str(side or "").strip().lower()
    boundary = optional_float(active_boundary)
    close = optional_float(candle.get("close"))
    if boundary is None or close is None:
        return boundary
    if side == "upper":
        low = optional_float(candle.get("low"))
        if low is not None and low < boundary and close >= boundary:
            return low
        return boundary
    if side == "lower":
        high = optional_float(candle.get("high"))
        if high is not None and high > boundary and close <= boundary:
            return high
        return boundary
    return boundary


def monotonic_continuation_boundary(
    side: Any,
    current_boundary: Any,
    candidate_boundary: Any,
) -> float | None:
    """Preserve the more-extreme continuation boundary after eligibility opens."""
    side = str(side or "").strip().lower()
    current = optional_float(current_boundary)
    candidate = optional_float(candidate_boundary)
    if current is None:
        return candidate
    if candidate is None:
        return current
    if side == "upper":
        return candidate if candidate < current else current
    if side == "lower":
        return candidate if candidate > current else current
    return current


def continuation_lane_matches_active_owner(
    previous_lane: dict[str, Any] | None,
    continuation_group: dict[str, Any] | None,
    active_price: Any,
) -> bool:
    """Return True when a persisted continuation lane belongs to the current active owner."""
    if not isinstance(previous_lane, dict):
        return False
    current_signature = liquidity_owner_signature(
        (continuation_group or {}).get("display_name") or (continuation_group or {}).get("name"),
        active_price,
        continuation_group if isinstance(continuation_group, dict) else None,
    )
    lane_group = previous_lane.get("active_liquidity_group") if isinstance(previous_lane.get("active_liquidity_group"), dict) else None
    lane_signature = liquidity_owner_signature(
        previous_lane.get("active_liquidity_name"),
        previous_lane.get("active_liquidity_price"),
        lane_group
        if isinstance(lane_group, dict)
        else {
            "name": previous_lane.get("liquidity_group"),
            "extreme_boundary": previous_lane.get("extreme_boundary"),
            "side": previous_lane.get("side"),
        },
    )
    return current_signature == lane_signature


def continuation_control_persists(
    previous_symbol_state: dict[str, Any] | None,
    continuation_group: dict[str, Any] | None,
    active_price: Any,
    raw_invalidation_reason: Any,
) -> bool:
    """Carry a controlling continuation lane until a real continuation exit or owner reset occurs."""
    previous_symbol_state = previous_symbol_state if isinstance(previous_symbol_state, dict) else {}
    previous_lane = previous_symbol_state.get("continuation_lane") if isinstance(previous_symbol_state.get("continuation_lane"), dict) else None
    if not continuation_lane_matches_active_owner(previous_lane, continuation_group, active_price):
        return False
    if previous_lane.get("lane_status") != "controlling":
        return False
    if str(previous_lane.get("step2_status") or "").upper() != "CONFIRMED":
        return False
    if str(previous_lane.get("step4_status") or "").upper() == "TERMINATED":
        return False
    if raw_invalidation_reason:
        return False
    return True


def same_candle_rejection_step4_confirmation_active(
    snapshot: dict[str, Any],
    step4: dict[str, Any] | None,
    previous_symbol_state: dict[str, Any] | None = None,
) -> bool:
    """Return True on the candle that confirms rejection Step 4, including same-candle refreshes."""
    latest_time = snapshot.get("latest_bar_time")
    if not latest_time:
        return False
    step4 = step4 if isinstance(step4, dict) else {}
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    if str(step4_state.get("lane_id") or "").startswith("continuation|"):
        return False
    if (
        (str(step4.get("status") or "").upper() == "READY" or str(step4_state.get("leg1_status") or "").upper() == "COMPLETE")
        and same_candle_time(step4_state.get("leg1_completed_at"), latest_time)
    ):
        return True
    previous_symbol_state = previous_symbol_state if isinstance(previous_symbol_state, dict) else {}
    previous_step4 = previous_symbol_state.get("step4") if isinstance(previous_symbol_state.get("step4"), dict) else {}
    previous_state = previous_step4.get("state") if isinstance(previous_step4.get("state"), dict) else {}
    if str(previous_state.get("lane_id") or "").startswith("continuation|"):
        return False
    return (
        previous_state.get("leg1_state_locked") is True
        and str(previous_state.get("leg1_status") or "").upper() == "COMPLETE"
        and same_candle_time(previous_state.get("leg1_completed_at"), latest_time)
    )


def persisted_continuation_wick_boundary(
    previous_symbol_state: dict[str, Any] | None,
    continuation_group: dict[str, Any] | None,
    active_price: Any,
) -> float | None:
    """Return the carried continuation wick boundary for the same seeded or controlling owner."""
    previous_symbol_state = previous_symbol_state if isinstance(previous_symbol_state, dict) else {}
    previous_lane = previous_symbol_state.get("continuation_lane") if isinstance(previous_symbol_state.get("continuation_lane"), dict) else None
    if not continuation_lane_matches_active_owner(previous_lane, continuation_group, active_price):
        return None
    if previous_lane.get("lane_status") not in {"eligible", "controlling"}:
        return None
    return optional_float(previous_lane.get("wick_boundary_extreme"))


def continuation_seed_boundary_from_rejection_step4(
    step4: dict[str, Any] | None,
    previous_symbol_state: dict[str, Any] | None,
    side: Any,
    *,
    rejection_group: dict[str, Any] | None = None,
    rejection_active_price: Any = None,
) -> float | None:
    """Return the continuation wick/reference seeded from a confirmed rejection Step 4 Candle B."""
    side_text = str(side or "")
    if side_text not in {"upper", "lower"}:
        return None

    def boundary_from_state(step4_state: dict[str, Any] | None, lane_owner_matches: bool) -> float | None:
        step4_state = step4_state if isinstance(step4_state, dict) else {}
        if not lane_owner_matches:
            return None
        if step4_state.get("leg1_state_locked") is not True:
            return None
        if str(step4_state.get("leg1_status") or "").upper() != "COMPLETE":
            return None
        candle_b = step4_state.get("candle_b") if isinstance(step4_state.get("candle_b"), dict) else None
        if not isinstance(candle_b, dict):
            return None
        return optional_float(candle_b.get("low") if side_text == "upper" else candle_b.get("high"))

    current_step4 = step4 if isinstance(step4, dict) else {}
    current_state = current_step4.get("state") if isinstance(current_step4.get("state"), dict) else {}
    current_lane = {
        "liquidity_group": current_state.get("liquidity_group") or ((rejection_group or {}).get("name") if isinstance(rejection_group, dict) else None),
        "active_liquidity_price": rejection_active_price,
        "close_boundary": current_state.get("close_boundary") if current_state.get("close_boundary") is not None else ((rejection_group or {}).get("close_boundary") if isinstance(rejection_group, dict) else None),
        "extreme_boundary": current_state.get("extreme_boundary") if current_state.get("extreme_boundary") is not None else ((rejection_group or {}).get("extreme_boundary") if isinstance(rejection_group, dict) else None),
    }
    boundary = boundary_from_state(current_state, rejection_lane_matches_active_owner(current_lane, rejection_group, rejection_active_price))
    if boundary is not None:
        return boundary

    previous_symbol_state = previous_symbol_state if isinstance(previous_symbol_state, dict) else {}
    previous_lane = previous_symbol_state.get("rejection_lane") if isinstance(previous_symbol_state.get("rejection_lane"), dict) else None
    if not rejection_lane_matches_active_owner(previous_lane, rejection_group, rejection_active_price):
        return None
    previous_step4 = previous_symbol_state.get("step4") if isinstance(previous_symbol_state.get("step4"), dict) else {}
    previous_state = previous_step4.get("state") if isinstance(previous_step4.get("state"), dict) else {}
    return boundary_from_state(previous_state, True)


def continuation_step2_candle_count(snapshot: dict[str, Any], step25_state: dict[str, Any]) -> int | None:
    """Return continuation Step 2 candle count with the continuation confirmation candle = 0."""
    if step25_state.get("continuation_step2_activated") is not True:
        return None
    confirmed_at = continuation_step2_confirmed_at(step25_state)
    current_time = parse_candle_time(snapshot.get("latest_bar_time"))
    confirmed_time = parse_candle_time(confirmed_at)
    if confirmed_time and current_time:
        delta_seconds = int((current_time - confirmed_time).total_seconds())
        if delta_seconds >= 0:
            return public_lifecycle_candle_count(delta_seconds // 60)
    if confirmed_at and same_candle_time(confirmed_at, snapshot.get("latest_bar_time")):
        return 0
    return None


def continuation_step2_confirmed_at(step25_state: dict[str, Any] | None) -> str | None:
    """Return the public continuation Step 2 confirmation time from the first controlling close."""
    step25_state = step25_state if isinstance(step25_state, dict) else {}
    if step25_state.get("continuation_step2_activated") is not True:
        return None
    started_at = step25_state.get("continuation_evaluation_started_at")
    if isinstance(started_at, str) and started_at.strip():
        return started_at
    reclaim_candle = step25_state.get("reclaim_candle_a") if isinstance(step25_state.get("reclaim_candle_a"), dict) else None
    return candle_timestamp(reclaim_candle)


def public_pathway_control_from_continuation_boundary(
    close_price: Any,
    boundary_price: Any,
    rejection_direction: Any,
) -> str | None:
    """Route public control between frozen rejection and confirmed continuation from the active continuation boundary."""
    close = optional_float(close_price)
    boundary = optional_float(boundary_price)
    direction = str(rejection_direction or "").upper().strip()
    if close is None or boundary is None:
        return None
    if direction == "SHORT":
        return "continuation" if close < boundary else "rejection"
    if direction == "LONG":
        return "continuation" if close > boundary else "rejection"
    return None


def step4_candle_count(step4_state: dict[str, Any] | None) -> int | None:
    """Return the public Step 4 candle count using the frozen Leg 1 window index."""
    step4_state = step4_state if isinstance(step4_state, dict) else {}
    return public_lifecycle_candle_count(step4_state.get("leg1_window_candle_index"))


def projected_pending_rejection_step4_state(
    snapshot: dict[str, Any],
    previous_symbol_state: dict[str, Any] | None,
    *,
    rejection_group: dict[str, Any] | None = None,
    rejection_active_price: Any = None,
) -> dict[str, Any] | None:
    """Carry a pending rejection Step 4 wait window across refreshes and live polls."""
    previous_symbol_state = previous_symbol_state if isinstance(previous_symbol_state, dict) else {}
    previous_lane = previous_symbol_state.get("rejection_lane") if isinstance(previous_symbol_state.get("rejection_lane"), dict) else None
    if not rejection_lane_matches_active_owner(previous_lane, rejection_group, rejection_active_price):
        return None
    previous_step4 = previous_symbol_state.get("step4") if isinstance(previous_symbol_state.get("step4"), dict) else {}
    previous_state = previous_step4.get("state") if isinstance(previous_step4.get("state"), dict) else {}
    if not previous_state.get("leg1_window_started_at"):
        return None
    if previous_state.get("leg1_state_locked") is True or previous_state.get("leg1_status") == "COMPLETE":
        return None
    if previous_state.get("leg1_window_invalidated") is True:
        return None
    count = stable_leg1_window_candle_count(snapshot, previous_state, previous_state.get("leg1_window_started_at"))
    if count is None:
        return None
    projected = dict(previous_state)
    projected["leg1_window_candle_index"] = count
    projected["leg1_window_remaining"] = max(0, 4 - count)
    projected["leg1_window_active"] = count < 4
    return projected


def carry_forward_confirmed_rejection_lane(
    previous_symbol_state: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Keep a confirmed/frozen rejection lane stable when a later refresh cannot rebuild it."""
    previous_symbol_state = previous_symbol_state if isinstance(previous_symbol_state, dict) else {}
    previous_lane = previous_symbol_state.get("rejection_lane") if isinstance(previous_symbol_state.get("rejection_lane"), dict) else {}
    if previous_lane.get("lane_status") not in {"controlling", "frozen"}:
        return None
    if previous_lane.get("invalidation_reason"):
        return None
    if str(previous_lane.get("step2_status") or "").upper() != "CONFIRMED":
        return None
    if str(previous_lane.get("step4_status") or "").upper() not in {"READY", "CONFIRMED"}:
        return None
    return dict(previous_lane)


def carry_forward_pending_rejection_lane(
    snapshot: dict[str, Any],
    previous_symbol_state: dict[str, Any] | None,
    *,
    rejection_group: dict[str, Any] | None = None,
    rejection_active_price: Any = None,
) -> dict[str, Any] | None:
    """Return the persisted rejection lane while Step 4 is still waiting on completed candles."""
    previous_symbol_state = previous_symbol_state if isinstance(previous_symbol_state, dict) else {}
    previous_lane = previous_symbol_state.get("rejection_lane") if isinstance(previous_symbol_state.get("rejection_lane"), dict) else {}
    if previous_lane.get("lane_status") not in {"controlling", "frozen"}:
        return None
    if previous_lane.get("invalidation_reason"):
        return None
    if not rejection_lane_matches_active_owner(previous_lane, rejection_group, rejection_active_price):
        return None
    projected_step4 = projected_pending_rejection_step4_state(
        snapshot,
        previous_symbol_state,
        rejection_group=rejection_group,
        rejection_active_price=rejection_active_price,
    )
    if not isinstance(projected_step4, dict):
        return None
    confirmed_at = previous_lane.get("step2_confirmed_at") or projected_step4.get("leg1_window_started_at")
    carried = dict(previous_lane)
    carried["step2_status"] = previous_lane.get("step2_status") or "CONFIRMED"
    carried["step4_status"] = previous_lane.get("step4_status") or "WAIT"
    carried["step2_candle_count"] = completed_candle_count_since_confirmation(snapshot, confirmed_at)
    carried["step4_candle_count"] = projected_step4.get("leg1_window_candle_index")
    return carried


def carry_forward_seeded_continuation_lane(
    previous_symbol_state: dict[str, Any] | None,
    *,
    continuation_group: dict[str, Any] | None = None,
    active_price: Any = None,
) -> dict[str, Any] | None:
    """Keep a seeded continuation boundary visible after rejection Step 4 confirmation."""
    previous_symbol_state = previous_symbol_state if isinstance(previous_symbol_state, dict) else {}
    previous_lane = previous_symbol_state.get("continuation_lane") if isinstance(previous_symbol_state.get("continuation_lane"), dict) else {}
    previous_step25 = previous_symbol_state.get("step25") if isinstance(previous_symbol_state.get("step25"), dict) else {}
    previous_step25_state = previous_step25.get("state") if isinstance(previous_step25.get("state"), dict) else {}
    if previous_lane.get("lane_status") not in {"eligible", "controlling"}:
        return None
    if previous_lane.get("invalidation_reason"):
        return None
    if (
        previous_lane.get("lane_status") == "eligible"
        and previous_step25_state.get("continuation_eligible_source") != "frozen_rejection_trade_state"
    ):
        return None
    lane_owner_name = previous_lane.get("liquidity_level_name") or previous_lane.get("active_liquidity_name")
    lane_owner_price = previous_lane.get("liquidity_level_price")
    if lane_owner_price is None:
        lane_owner_price = previous_lane.get("active_liquidity_price")
    if liquidity_level_consumed(previous_symbol_state, lane_owner_name, lane_owner_price):
        return None
    if optional_float(previous_lane.get("wick_boundary_extreme")) is None:
        return None
    if not continuation_lane_matches_active_owner(previous_lane, continuation_group, active_price):
        return None
    carried = dict(previous_lane)
    if str(carried.get("step2_status") or "").upper() != "CONFIRMED":
        carried["step2_status"] = "WAIT"
    return carried


def generic_wait_reset_reason(reason: Any) -> bool:
    """Return True when the public wait reason reflects a raw reset instead of carried lane context."""
    text = str(reason or "").strip().lower()
    return text in {
        "no active liquidity selected.",
        "waiting for a valid liquidity-close activation.",
    }


def raw_pathway_control_from_snapshot(snapshot: dict[str, Any]) -> str | None:
    """Return the currently controlling pathway from raw step state when available."""
    for step_name in ("step6", "step5", "step4"):
        step = snapshot.get(step_name) if isinstance(snapshot.get(step_name), dict) else {}
        state = step.get("state") if isinstance(step.get("state"), dict) else {}
        control = state.get("current_pathway_control")
        if control in {"rejection", "continuation"}:
            return str(control)
    step25 = snapshot.get("step25") if isinstance(snapshot.get("step25"), dict) else {}
    step25_state = step25.get("state") if isinstance(step25.get("state"), dict) else {}
    controlling_mode = normalized_pathway_name(step25_state.get("controlling_mode"))
    if controlling_mode in {"S/R", "R/S"} and (
        step25_state.get("continuation_step2_activated") is True
        or isinstance(step25_state.get("reclaim_candle_a"), dict)
    ):
        return "continuation"
    step2 = snapshot.get("step_2_1a") if isinstance(snapshot.get("step_2_1a"), dict) else {}
    if step2.get("step_2_activated") is True:
        return "rejection"
    return None


def build_lane_status(
    lane_name: str,
    *,
    lane_status: str,
    pathway_status: str,
    active_liquidity_name: Any,
    active_liquidity_group: Any,
    liquidity_group: Any,
    active_liquidity_price: Any,
    close_boundary: Any,
    extreme_boundary: Any,
    wick_boundary_extreme: Any,
    step2_candle_count: Any,
    step4_candle_count: Any,
    step2_status: Any,
    step2_confirmed_at: Any,
    step25_status: Any,
    step4_status: Any,
    step2_step4_50_line: Any,
    step4_step5_75_line: Any,
    step2_reason: Any,
    step4_reason: Any,
    invalidation_reason: Any,
    invalidation_source: Any = None,
    invalidation_source_step: Any = None,
    invalidation_source_candle_time: Any = None,
    leg2_candidate_candle_time: Any = None,
    continuation_type: Any = None,
) -> dict[str, Any]:
    """Return one authoritative lane object before public projection strips internal fields."""
    return {
        "lane_name": lane_name,
        "lane_status": lane_status,
        "pathway_status": pathway_status,
        "active_liquidity_name": active_liquidity_name,
        "active_liquidity_group": copy.deepcopy(active_liquidity_group) if isinstance(active_liquidity_group, dict) else None,
        "liquidity_group": liquidity_group,
        "active_liquidity_price": active_liquidity_price,
        "close_boundary": close_boundary,
        "extreme_boundary": extreme_boundary,
        "wick_boundary_extreme": wick_boundary_extreme,
        "step2_candle_count": step2_candle_count,
        "step4_candle_count": step4_candle_count,
        "step2_status": step2_status,
        "step2_confirmed_at": step2_confirmed_at,
        "step25_status": step25_status,
        "step4_status": step4_status,
        "step2_step4_50_line": step2_step4_50_line,
        "step4_step5_75_line": step4_step5_75_line,
        "step2_reason": step2_reason,
        "step4_reason": step4_reason,
        "invalidation_reason": invalidation_reason,
        "invalidation_source": invalidation_source,
        "invalidation_source_step": invalidation_source_step,
        "invalidation_source_candle_time": invalidation_source_candle_time,
        "leg2_candidate_candle_time": leg2_candidate_candle_time,
        "continuation_type": continuation_type,
    }


def public_lane_projection(lane: dict[str, Any] | None) -> dict[str, Any]:
    """Return the public lane contract with internal Step 2.5 fields removed."""
    lane = dict(lane) if isinstance(lane, dict) else {}
    lane.pop("step25_status", None)
    lane_name = str(lane.get("lane_name") or "").strip().lower()
    lane.update(
        public_boundary_projection_values(
            lane,
            continuation_boundary=lane.get("continuation_active_boundary_price"),
            lane_name=lane_name,
            lane_status=lane.get("lane_status"),
        )
    )
    for retired_field in (
        "close_boundary",
        "extreme_boundary",
        "wick_boundary_extreme",
        "continuation_reference_boundary_type",
        "continuation_reference_boundary_price",
        "continuation_active_boundary_price",
    ):
        lane.pop(retired_field, None)
    lane["step2_status"] = public_step_status(lane.get("step2_status"), step_name="Step 2")
    lane["step4_status"] = public_step_status(lane.get("step4_status"), step_name="Step 4")
    return lane


def apply_frozen_rejection_lane_projection(
    snapshot: dict[str, Any],
    persisted_symbol_state: dict[str, Any] | None,
    rejection_lane: dict[str, Any] | None,
    step4_state: dict[str, Any] | None,
) -> tuple[dict[str, Any], str | None]:
    """Freeze rejection-lane public anchors from the canonical Step 2 owner.

    These are lifecycle invariants from the frozen Step 2 owner, not display
    preferences. Public polling must never drift these anchors to the current
    candle time or rebuild them from refreshed participation state.
    """
    lane = dict(rejection_lane) if isinstance(rejection_lane, dict) else {}
    persisted_symbol_state = persisted_symbol_state if isinstance(persisted_symbol_state, dict) else {}
    previous_lane = persisted_symbol_state.get("rejection_lane") if isinstance(persisted_symbol_state.get("rejection_lane"), dict) else {}
    previous_step4_state = ((persisted_symbol_state.get("step4") or {}).get("state") or {}) if isinstance(((persisted_symbol_state.get("step4") or {}).get("state") or {}), dict) else {}
    previous_terminal = (
        previous_step4_state.get("leg1_window_invalidated") is True
        or str(previous_lane.get("step4_status") or "").strip().upper() == "TERMINATED"
        or bool(previous_lane.get("invalidation_reason"))
    )
    if str(lane.get("step2_status") or "").strip().upper() != "CONFIRMED" and not previous_terminal:
        return lane, None
    step2 = snapshot.get("step_2_1a") if isinstance(snapshot.get("step_2_1a"), dict) else {}
    frozen_step2_time = (
        snapshot.get("frozen_step2_anchor_time")
        or previous_lane.get("step2_confirmed_at")
        or lane.get("step2_confirmed_at")
        or step2_confirmed_anchor_time(step2)
    )
    if isinstance(frozen_step2_time, str) and frozen_step2_time.strip():
        lane["step2_status"] = "CONFIRMED"
        lane["step2_confirmed_at"] = frozen_step2_time
    lane_terminal = (
        str(lane.get("step4_status") or "").strip().upper() == "TERMINATED"
        or bool(lane.get("invalidation_reason"))
    )
    if previous_terminal and previous_lane.get("step2_confirmed_at") == frozen_step2_time and not lane_terminal:
        for field in (
            "lane_status",
            "pathway_status",
            "step4_status",
            "invalidation_reason",
            "step4_reason",
            "step2_step4_50_line",
        ):
            if previous_lane.get(field) is not None:
                lane[field] = copy.deepcopy(previous_lane.get(field))
    frozen_leg1_window_started_at = (
        previous_step4_state.get("leg1_window_started_at")
        or ((step4_state or {}).get("leg1_window_started_at") if isinstance(step4_state, dict) else None)
        or frozen_step2_time
    )
    if isinstance(frozen_leg1_window_started_at, str) and frozen_leg1_window_started_at.strip():
        lane["leg1_window_started_at"] = frozen_leg1_window_started_at
    if is_seeded_step4_anchor_reason(lane.get("step4_reason")):
        frozen_reason = seeded_step4_reason_from_anchor(frozen_leg1_window_started_at or frozen_step2_time)
        if frozen_reason:
            lane["step4_reason"] = frozen_reason
    return lane, frozen_leg1_window_started_at


def public_liquidity_level_payload(
    group: dict[str, Any] | None,
    fallback_name: Any,
    fallback_price: Any,
) -> dict[str, Any]:
    """Return the public actionable liquidity level without exposing stack mechanics."""
    if isinstance(group, dict):
        components = [str(component).strip() for component in (group.get("components") or []) if str(component).strip()]
        if len(components) > 1:
            display_name = canonical_group_display_name(group)
            extreme_price = optional_float(group.get("extreme_boundary"))
            if isinstance(display_name, str) and display_name.strip() and extreme_price is not None:
                text = str(display_name).strip()
                suffix = " Liquidity"
                if text.endswith(suffix):
                    text = text[: -len(suffix)]
                return {"name": text, "price": extreme_price}
        extreme_name = public_active_liquidity_name(group.get("extreme_component"))
        extreme_price = optional_float(group.get("extreme_boundary"))
        if extreme_name and extreme_price is not None:
            return {"name": extreme_name, "price": extreme_price}
    return {
        "name": public_active_liquidity_name(fallback_name),
        "price": optional_float(fallback_price),
    }


def public_rejection_probe_boundary(step2_state: dict[str, Any] | None) -> float | None:
    """Return the rejection probe boundary that must remain public after Step 2."""
    if not isinstance(step2_state, dict):
        return None
    probe = step2_state.get("pre_activation_probe_boundary") if isinstance(step2_state.get("pre_activation_probe_boundary"), dict) else None
    if not isinstance(probe, dict):
        return None
    boundary = optional_float(probe.get("boundary_price"))
    if boundary is None:
        return None
    if step2_state.get("step_2_activated") is True or probe.get("active") is True:
        return boundary
    return None


def public_rejection_boundary(
    group: dict[str, Any] | None,
    wick_boundary_extreme: Any,
    extreme_boundary: Any,
    fallback_price: Any,
    *,
    step2_activated: bool = False,
    probe_boundary: Any = None,
) -> float | None:
    """Return the existing rejection boundary as one public field."""
    probe_value = optional_float(probe_boundary)
    if step2_activated:
        return probe_value
    if probe_value is not None:
        return probe_value
    if isinstance(group, dict):
        projected_group = dict(group)
        if wick_boundary_extreme is not None:
            projected_group["wick_boundary_extreme"] = wick_boundary_extreme
        if extreme_boundary is not None:
            projected_group["extreme_boundary"] = extreme_boundary
        return actionable_boundary_from_group(projected_group, fallback_price)
    if wick_boundary_extreme is not None:
        return optional_float(wick_boundary_extreme)
    if extreme_boundary is not None:
        return optional_float(extreme_boundary)
    return optional_float(fallback_price)


def public_continuation_boundary(
    active_boundary: Any,
    probe_boundary: Any = None,
) -> float | None:
    """Return the existing continuation boundary as one public field."""
    boundary = optional_float(active_boundary)
    if boundary is not None:
        return boundary
    return optional_float(probe_boundary)


def public_active_liquidity_group_projection(group: dict[str, Any] | None) -> dict[str, Any] | None:
    """Strip retired public boundary fields from the exposed liquidity group."""
    if not isinstance(group, dict):
        return None
    projected = copy.deepcopy(group)
    liquidity_level = public_liquidity_level_payload(
        projected,
        projected.get("display_name") or projected.get("name"),
        projected.get("extreme_boundary"),
    )
    projected["liquidity_level_name"] = liquidity_level["name"]
    projected["liquidity_level_price"] = liquidity_level["price"]
    for retired_field in (
        "close_boundary",
        "extreme_boundary",
        "wick_boundary_extreme",
        "stack_extreme",
    ):
        projected.pop(retired_field, None)
    return projected


def public_boundary_model_projection(
    state: dict[str, Any] | None,
    *,
    continuation_boundary: Any = None,
) -> dict[str, Any]:
    """Project the simplified public boundary model onto a status-like payload."""
    projected = dict(state) if isinstance(state, dict) else {}
    projected.update(public_boundary_projection_values(projected, continuation_boundary=continuation_boundary))
    for retired_field in (
        "close_boundary",
        "extreme_boundary",
        "wick_boundary_extreme",
        "continuation_reference_boundary_type",
        "continuation_reference_boundary_price",
        "continuation_active_boundary_price",
        "step2_activated",
        "rejection_probe_boundary",
        "continuation_probe_boundary_price",
    ):
        projected.pop(retired_field, None)
    return projected


def public_boundary_projection_values(
    state: dict[str, Any] | None,
    *,
    continuation_boundary: Any = None,
    lane_name: str | None = None,
    lane_status: str | None = None,
) -> dict[str, Any]:
    """Return the shared public boundary projection used by status, replay, and logs."""
    projected = dict(state) if isinstance(state, dict) else {}
    liquidity_level = public_liquidity_level_payload(
        projected.get("active_liquidity_group"),
        projected.get("active_liquidity_name"),
        projected.get("active_liquidity_price"),
    )
    rejection_boundary = public_rejection_boundary(
        projected.get("active_liquidity_group"),
        projected.get("wick_boundary_extreme"),
        projected.get("extreme_boundary"),
        projected.get("active_liquidity_price"),
        step2_activated=projected.get("step2_activated") is True,
        probe_boundary=projected.get("rejection_probe_boundary"),
    )
    continuation_boundary_value = public_continuation_boundary(
        continuation_boundary,
        projected.get("continuation_probe_boundary_price"),
    )
    normalized_lane_name = str(lane_name or projected.get("lane_name") or "").strip().lower()
    normalized_lane_status = str(lane_status or projected.get("lane_status") or "").strip().lower()
    if normalized_lane_name == "rejection":
        continuation_boundary_value = None
    elif normalized_lane_name == "continuation":
        rejection_boundary = None
        if normalized_lane_status not in {"eligible", "controlling", "invalidated"}:
            continuation_boundary_value = None
    return {
        "liquidity_level_name": liquidity_level["name"],
        "liquidity_level_price": liquidity_level["price"],
        "rejection_boundary": rejection_boundary,
        "continuation_boundary": continuation_boundary_value,
        "active_liquidity_group": public_active_liquidity_group_projection(projected.get("active_liquidity_group")),
    }


def public_active_liquidity_name(value: Any) -> Any:
    """Return the operator-facing active liquidity name without the legacy suffix."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    suffix = " Liquidity"
    if text.endswith(suffix):
        text = text[: -len(suffix)]
    components = [part.strip() for part in text.split("/") if part.strip()]
    ordering = {
        "PMH": 0,
        "PML": 0,
        "LH": 1,
        "LL": 1,
        "ONH": 2,
        "ONL": 2,
        "YH": 3,
        "YL": 3,
    }
    if components and all(component in ordering for component in components):
        return "/".join(sorted(components, key=lambda component: (ordering[component], component)))
    return text


def canonical_group_display_name(group: dict[str, Any] | None) -> str | None:
    """Build a deterministic public stack display name from frozen group components when missing."""
    if not isinstance(group, dict):
        return None
    display_name = group.get("display_name")
    if isinstance(display_name, str) and display_name.strip():
        return str(display_name).strip()
    components = [str(component).strip() for component in (group.get("components") or []) if str(component).strip()]
    if not components:
        return None
    if len(components) == 1:
        return components[0]
    prices = group.get("prices") if isinstance(group.get("prices"), dict) else {}
    side = str(group.get("side") or "")

    def component_priority(name: str) -> int:
        return ACTIVE_LIQUIDITY_PRIORITY.get(name, 999)

    if side == "lower":
        ordered = sorted(
            components,
            key=lambda name: (
                -(optional_float(prices.get(name)) if optional_float(prices.get(name)) is not None else float("-inf")),
                component_priority(name),
                name,
            ),
        )
    elif side == "upper":
        ordered = sorted(
            components,
            key=lambda name: (
                optional_float(prices.get(name)) if optional_float(prices.get(name)) is not None else float("inf"),
                component_priority(name),
                name,
            ),
        )
    else:
        ordered = sorted(components, key=lambda name: (component_priority(name), name))
    return f"{'/'.join(ordered)} Liquidity"


def frozen_session_group_for_liquidity(
    snapshot: dict[str, Any],
    liquidity_name: Any,
    liquidity_price: Any = None,
) -> dict[str, Any] | None:
    """Return the canonical frozen session stack/level group for one active liquidity identity."""
    session_context = snapshot.get("session_liquidity_context") if isinstance(snapshot.get("session_liquidity_context"), dict) else {}
    active_groups = session_context.get("active_groups") if isinstance(session_context.get("active_groups"), list) else []
    if not active_groups:
        return None
    name_text = str(liquidity_name or "").strip()
    price_value = optional_float(liquidity_price)

    if name_text:
        for group in active_groups:
            if not isinstance(group, dict):
                continue
            if group.get("name") == name_text:
                enriched = dict(group)
                enriched["display_name"] = canonical_group_display_name(enriched)
                return enriched
            components = [str(component) for component in (group.get("components") or []) if component]
            if name_text in components:
                enriched = dict(group)
                enriched["display_name"] = canonical_group_display_name(enriched)
                return enriched

    if price_value is not None:
        for group in active_groups:
            if not isinstance(group, dict):
                continue
            group_prices = group.get("prices") if isinstance(group.get("prices"), dict) else {}
            if any(optional_float(component_price) == price_value for component_price in group_prices.values()):
                enriched = dict(group)
                enriched["display_name"] = canonical_group_display_name(enriched)
                return enriched
            if optional_float(group.get("close_boundary")) == price_value or optional_float(group.get("extreme_boundary")) == price_value:
                enriched = dict(group)
                enriched["display_name"] = canonical_group_display_name(enriched)
                return enriched
    return None


def public_active_liquidity_display_name(
    snapshot: dict[str, Any],
    active_group: dict[str, Any] | None,
    fallback_name: Any,
    fallback_price: Any,
) -> Any:
    """Return the public stack identity, preserving full stacked names such as PMH/LH/ONH."""
    group = active_group if isinstance(active_group, dict) else {}
    if not group:
        frozen_group = frozen_session_group_for_liquidity(snapshot, fallback_name, fallback_price)
        if isinstance(frozen_group, dict):
            group = frozen_group
    display_name = canonical_group_display_name(group)
    if isinstance(display_name, str) and display_name.strip():
        return public_active_liquidity_name(display_name)
    fallback_name_text = public_active_liquidity_name(fallback_name)
    if isinstance(fallback_name_text, str) and fallback_name_text in ACTIVE_LIQUIDITY_PRIORITY and "/" not in fallback_name_text:
        return fallback_name_text
    fallback_price_value = optional_float(fallback_price)
    group_name = group.get("name")
    if snapshot.get("tv_context") is not None and fallback_price_value is not None:
        for candidate_group in active_liquidity_groups_from_context(snapshot.get("tv_context")):
            if not isinstance(candidate_group, dict):
                continue
            if group_name and candidate_group.get("name") != group_name:
                continue
            if optional_float(candidate_group.get("close_boundary")) == fallback_price_value or optional_float(candidate_group.get("extreme_boundary")) == fallback_price_value:
                candidate_display_name = candidate_group.get("display_name")
                if isinstance(candidate_display_name, str) and candidate_display_name.strip():
                    return public_active_liquidity_name(candidate_display_name)
    liquidity = snapshot.get("liquidity") if isinstance(snapshot.get("liquidity"), dict) else {}
    selected = selected_active_liquidity_from_context(
        snapshot.get("tv_context"),
        snapshot.get("latest_price"),
        snapshot.get("ohlc") if isinstance(snapshot.get("ohlc"), dict) else None,
        float((liquidity or {}).get("tick_size") or 0.25),
    )
    if (
        isinstance(selected, dict)
        and valid_active_liquidity_selection(selected.get("name"), selected.get("price"))
        and optional_float(selected.get("price")) == optional_float(fallback_price)
    ):
        selected_display_name = selected.get("display_name") or ((selected.get("group") or {}).get("display_name") if isinstance(selected.get("group"), dict) else None)
        if isinstance(selected_display_name, str) and selected_display_name.strip():
            return public_active_liquidity_name(selected_display_name)
    return public_active_liquidity_name(fallback_name)


def preserve_invalidated_lane(candidate: dict[str, Any], previous_lane: dict[str, Any] | None) -> dict[str, Any]:
    """Carry an invalidated lane forward on the same owner until a real reset or owner change."""
    if not isinstance(previous_lane, dict):
        return candidate
    if previous_lane.get("lane_status") != "invalidated":
        return candidate
    if lane_owner_signature(candidate) != lane_owner_signature(previous_lane):
        return candidate
    updated = dict(candidate)
    updated["lane_status"] = "invalidated"
    updated["pathway_status"] = "invalidated"
    updated["step2_status"] = previous_lane.get("step2_status") or updated.get("step2_status")
    updated["step25_status"] = previous_lane.get("step25_status") or updated.get("step25_status")
    updated["step4_status"] = previous_lane.get("step4_status") or updated.get("step4_status") or "TERMINATED"
    updated["invalidation_reason"] = previous_lane.get("invalidation_reason") or updated.get("invalidation_reason")
    updated["candle_count"] = public_lifecycle_candle_count(previous_lane.get("candle_count"))
    updated["wick_boundary_extreme"] = previous_lane.get("wick_boundary_extreme")
    for field in (
        "active_liquidity_group",
        "step2_reason",
        "step4_reason",
        "invalidation_source",
        "invalidation_source_step",
        "invalidation_source_candle_time",
        "leg2_candidate_candle_time",
    ):
        if updated.get(field) is None and previous_lane.get(field) is not None:
            updated[field] = copy.deepcopy(previous_lane.get(field))
    for field in ("step2_step4_50_line", "step4_step5_75_line"):
        if updated.get(field) is None and previous_lane.get(field) is not None:
            updated[field] = previous_lane.get(field)
    return updated


def snapshot_lane_statuses(snapshot: dict[str, Any], previous_symbol_state: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return authoritative rejection and continuation lane objects from the raw snapshot."""
    previous_symbol_state = previous_symbol_state if isinstance(previous_symbol_state, dict) else {}
    step2 = snapshot.get("step_2_1a") if isinstance(snapshot.get("step_2_1a"), dict) else {}
    step25 = snapshot.get("step25") if isinstance(snapshot.get("step25"), dict) else {}
    step4 = snapshot.get("step4") if isinstance(snapshot.get("step4"), dict) else {}
    step5 = snapshot.get("step5") if isinstance(snapshot.get("step5"), dict) else {}
    step6 = snapshot.get("step6") if isinstance(snapshot.get("step6"), dict) else {}
    step25_state = step25.get("state") if isinstance(step25.get("state"), dict) else {}
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    step5_state = step5.get("state") if isinstance(step5.get("state"), dict) else {}
    previous_rejection_lane = previous_symbol_state.get("rejection_lane") if isinstance(previous_symbol_state.get("rejection_lane"), dict) else {}
    observation_only = before_entry_authorization(snapshot)
    observation_liquidity = public_observation_liquidity_from_snapshot(snapshot) if observation_only else None
    active_name, active_price = (
        (observation_liquidity.get("name"), observation_liquidity.get("price"))
        if isinstance(observation_liquidity, dict)
        else active_liquidity_from_snapshot(snapshot)
    )
    active_group = (
        observation_liquidity.get("group")
        if isinstance(observation_liquidity, dict) and isinstance(observation_liquidity.get("group"), dict)
        else active_liquidity_group_from_snapshot(snapshot)
    )
    persisted_group = active_liquidity_group_from_snapshot(snapshot)
    active_group = merge_monotonic_stack_wick_boundary(active_group, persisted_group)
    active_group = stack_group_with_pre_open_wick_boundary(active_group, snapshot.get("pre_open_observed_extreme") if observation_only else None)
    locked_trade_owner = locked_trade_lifecycle_owner(snapshot)
    lifecycle_owner_locked = isinstance(locked_trade_owner, dict)
    if lifecycle_owner_locked:
        active_name = locked_trade_owner.get("name")
        active_price = locked_trade_owner.get("price")
        active_group = locked_trade_owner.get("group") if isinstance(locked_trade_owner.get("group"), dict) else None
    owner = step2.get("step2_locked_owner") if isinstance(step2.get("step2_locked_owner"), dict) else {}
    step2_window_terminated = step2_lifecycle_window_terminated(snapshot, step2, step4)
    boundary_owner = {} if step2_window_terminated else owner
    boundary_active_liquidity = (
        boundary_owner.get("active_liquidity")
        if isinstance(boundary_owner.get("active_liquidity"), dict)
        else (step2.get("last_interacted_liquidity") if isinstance(step2.get("last_interacted_liquidity"), dict) else {"price": active_price})
    )
    if step2_window_terminated:
        boundary_active_liquidity = {"price": active_price}
    close_boundary = audit_boundary_value("close_boundary", active_group, boundary_owner, boundary_active_liquidity, step2)
    extreme_boundary = audit_boundary_value("extreme_boundary", active_group, boundary_owner, boundary_active_liquidity, step2)
    wick_boundary = audit_boundary_value("wick_boundary_extreme", active_group, boundary_owner, boundary_active_liquidity, step2)
    setup_direction = (
        owner.get("setup_direction")
        or step25_state.get("setup_direction")
        or step4_state.get("setup_direction")
        or (((step5.get("state") or {}) if isinstance(step5.get("state"), dict) else {}).get("setup_direction"))
        or (((step6.get("state") or {}) if isinstance(step6.get("state"), dict) else {}).get("setup_direction"))
    )
    rejection_active = step2.get("step_2_activated") is True and not step2_window_terminated
    continuation_type = normalized_pathway_name(step25_state.get("controlling_mode"))
    raw_pathway_control = raw_pathway_control_from_snapshot(snapshot)
    seeded_step4 = projected_seeded_step4_status(snapshot, step2, step4)
    persisted_rejection_invalidated = rejection_invalidated_before_step4_completion(previous_symbol_state, active_group, active_price)
    rejection_step4_completed = rejection_step4_completed_for_owner(step4, previous_symbol_state, active_group, active_price)
    rejection_invalidation_reason = first_invalidation_reason_for_lane("rejection", step4, step5, step6)
    continuation_invalidation_reason = first_invalidation_reason_for_lane("continuation", step4, step5, step6)
    rejection_public_invalidation = public_invalidation_from_results_for_lane(
        current_step_from_snapshot(snapshot),
        "rejection",
        step4,
        step5,
        step6,
    )
    continuation_public_invalidation = public_invalidation_from_results_for_lane(
        current_step_from_snapshot(snapshot),
        "continuation",
        step4,
        step5,
        step6,
    )
    if rejection_invalidation_reason is None and persisted_rejection_invalidated:
        rejection_invalidation_reason = previous_rejection_lane.get("invalidation_reason")
    count = step2_candle_count(snapshot, step2)
    rejection_step2_time = step2_confirmed_at(snapshot, step2, "CONFIRMED")
    continuation_step2_time = continuation_step2_confirmed_at(step25_state)
    continuation_active_boundary_price = optional_float(step25_state.get("continuation_active_boundary_price"))
    # Continuation boundaries become public as soon as eligibility opens. The
    # structural boundaries stay fixed while internal probe state feeds the
    # continuation wick boundary seen in status, audit, and Command Center.
    continuation_group = continuation_group_with_probe_boundary(active_group, step25_state)
    continuation_close_boundary = optional_float((continuation_group or {}).get("close_boundary")) if isinstance(continuation_group, dict) else None
    continuation_extreme_boundary = optional_float((continuation_group or {}).get("extreme_boundary")) if isinstance(continuation_group, dict) else None
    continuation_wick_boundary = optional_float((continuation_group or {}).get("wick_boundary_extreme")) if isinstance(continuation_group, dict) else None
    consumed_records = merge_consumed_liquidity_levels(
        step2.get("consumed_liquidity_levels"),
        step4_state.get("consumed_liquidity_levels"),
        step5_state.get("consumed_liquidity_levels"),
        consumed_liquidity_levels(previous_symbol_state),
    )
    level_consumed = liquidity_level_consumed(
        {"consumed_liquidity_levels": consumed_records},
        active_name,
        active_price,
    )
    # Continuation eligibility opens after a completed rejection Step 4 handoff
    # or after rejection invalidation before Step 4 completion. Eligibility does
    # not make continuation controlling; it only instantiates the owner and
    # starts independent continuation boundary tracking.
    continuation_confirmed = step25_state.get("continuation_step2_activated") is True
    continuation_lane_contract = lifecycle_lane_contract(step4_state.get("lane_id"))
    continuation_step4_window_active = (
        continuation_lane_contract.get("lane_name") == "continuation"
        and bool(step4_state.get("leg1_window_started_at"))
        and step4_state.get("leg1_window_invalidated") is not True
        and not continuation_invalidation_reason
    )
    if continuation_step4_window_active:
        continuation_confirmed = True
        if continuation_step2_time is None:
            continuation_step2_time = continuation_lane_contract.get("confirmed_at")
        if continuation_active_boundary_price is None:
            continuation_active_boundary_price = continuation_lane_contract.get("close_boundary")
        if continuation_close_boundary is None:
            continuation_close_boundary = continuation_lane_contract.get("close_boundary")
        if continuation_extreme_boundary is None:
            continuation_extreme_boundary = continuation_lane_contract.get("extreme_boundary")
    elif continuation_invalidation_reason and continuation_lane_contract.get("lane_name") == "continuation":
        if continuation_step2_time is None:
            continuation_step2_time = continuation_lane_contract.get("confirmed_at")
        if continuation_active_boundary_price is None:
            continuation_active_boundary_price = continuation_lane_contract.get("close_boundary")
        if continuation_close_boundary is None:
            continuation_close_boundary = continuation_lane_contract.get("close_boundary")
        if continuation_extreme_boundary is None:
            continuation_extreme_boundary = continuation_lane_contract.get("extreme_boundary")
    if level_consumed:
        continuation_confirmed = False
        continuation_step4_window_active = False
    if continuation_confirmed and continuation_active_boundary_price is not None:
        continuation_close_boundary = continuation_active_boundary_price
    continuation_controlling = continuation_confirmed or continuation_control_persists(
        previous_symbol_state,
        continuation_group,
        active_price,
        continuation_invalidation_reason,
    )
    if same_candle_rejection_step4_confirmation_active(snapshot, step4, previous_symbol_state):
        continuation_controlling = False
    if (
        lifecycle_owner_locked
        and not continuation_step4_window_active
        and step25_state.get("continuation_step2_activated") is not True
    ):
        continuation_controlling = False
    if continuation_controlling:
        raw_pathway_control = "continuation"
    continuation_eligible = not level_consumed and not continuation_controlling and rejection_step4_completed
    continuation_count = continuation_step2_candle_count(snapshot, step25_state)
    if continuation_count is None and continuation_step4_window_active:
        continuation_count = public_lifecycle_candle_count(step4_state.get("leg1_window_candle_index"))
    continuation_evaluation_reason = step25_state.get("continuation_evaluation_reason") or step25_state.get("step25_block_reason")
    public_step4_count = step4_candle_count(step4_state)
    continuation_contract = lifecycle_lane_contract(step4_state.get("lane_id"))
    if continuation_contract.get("lane_name") == "continuation":
        active_name = continuation_contract.get("owner_name") or active_name
        continuation_close_boundary = continuation_contract.get("close_boundary")
        continuation_extreme_boundary = continuation_contract.get("extreme_boundary")
        continuation_group = frozen_session_group_for_liquidity(
            snapshot,
            continuation_contract.get("owner_name"),
            continuation_contract.get("close_boundary"),
        )
    continuation_step4_status = "WAIT"
    if continuation_contract.get("lane_name") == "continuation":
        if continuation_invalidation_reason:
            continuation_step4_status = "TERMINATED"
        elif step4_state.get("step4_confirmed_at") or step4_state.get("leg1_completed_at") or step4.get("status") == "READY":
            continuation_step4_status = "CONFIRMED"
    continuation_step2_reason = continuation_public_step2_reason(
        continuation_evaluation_reason,
        controlling=continuation_controlling,
        invalidation_reason=continuation_invalidation_reason,
        step4_status=continuation_step4_status,
    )
    continuation_step4_reason = continuation_public_step4_reason(
        result_reason(step4, ""),
        controlling=continuation_controlling,
        invalidation_reason=continuation_invalidation_reason,
        step4_status=continuation_step4_status,
    )
    seeded_continuation_wick = continuation_seed_boundary_from_rejection_step4(
        step4,
        previous_symbol_state,
        (continuation_group or {}).get("side") if isinstance(continuation_group, dict) else None,
        rejection_group=active_group if isinstance(active_group, dict) else None,
        rejection_active_price=active_price,
    )
    if seeded_continuation_wick is not None:
        continuation_wick_boundary = seeded_continuation_wick
    carried_continuation_wick = persisted_continuation_wick_boundary(previous_symbol_state, continuation_group, active_price)
    if (
        seeded_continuation_wick is None
        and (continuation_controlling or continuation_eligible)
        and carried_continuation_wick is not None
    ):
        continuation_wick_boundary = carried_continuation_wick
    participation_lines = step4_participation_line_payload(
        snapshot,
        step2,
        step4_state,
        rejection_active=rejection_active,
        selected_pathway="rejection",
        setup_direction=setup_direction,
        leg1_published=False,
        invalidated=False,
    )
    step4_lane_contract = lifecycle_lane_contract(step4_state.get("lane_id"))
    rejection_step4_status = "TERMINATED" if persisted_rejection_invalidated else (((seeded_step4 or {}).get("status")) or step4.get("status"))
    rejection_step4_reason = rejection_invalidation_reason or ((seeded_step4 or {}).get("reason")) or result_reason(step4, "")
    if step4_lane_contract.get("lane_name") == "continuation":
        rejection_step4_status = previous_rejection_lane.get("step4_status") or ((seeded_step4 or {}).get("status")) or "WAIT"
        rejection_step4_reason = previous_rejection_lane.get("step4_reason") or ((seeded_step4 or {}).get("reason")) or None

    # Rejection remains authoritative for its own lifecycle. Once invalidated on
    # the same owner it must carry forward as invalidated and cannot republish as
    # WAIT, READY, or controlling without a true reset or owner change.
    rejection_lane = build_lane_status(
        "rejection",
        lane_status=(
            "invalidated" if (rejection_active and rejection_invalidation_reason) or persisted_rejection_invalidated
            else "frozen" if continuation_controlling and rejection_active
            else "controlling" if rejection_active
            else "idle"
        ),
        pathway_status=(
            "invalidated" if (rejection_active and rejection_invalidation_reason) or persisted_rejection_invalidated
            else "frozen" if continuation_controlling and rejection_active
            else "controlling" if rejection_active
            else "idle"
        ),
        active_liquidity_name=active_name if rejection_active or rejection_invalidation_reason else None,
        active_liquidity_group=active_group if isinstance(active_group, dict) and (rejection_active or rejection_invalidation_reason) else None,
        liquidity_group=(active_group or {}).get("name") if isinstance(active_group, dict) and (rejection_active or rejection_invalidation_reason) else None,
        active_liquidity_price=active_price if rejection_active or rejection_invalidation_reason else None,
        close_boundary=close_boundary if rejection_active or rejection_invalidation_reason else None,
        extreme_boundary=extreme_boundary if rejection_active or rejection_invalidation_reason else None,
        wick_boundary_extreme=wick_boundary if rejection_active or rejection_invalidation_reason else None,
        step2_candle_count=count if rejection_active or rejection_invalidation_reason else None,
        step4_candle_count=public_step4_count if rejection_active or rejection_invalidation_reason else None,
        step2_status="CONFIRMED" if rejection_active else "WAIT",
        step2_confirmed_at=rejection_step2_time if rejection_active or rejection_invalidation_reason else None,
        step25_status=step25.get("status") if rejection_active or rejection_invalidation_reason else "WAIT",
        step4_status=rejection_step4_status if rejection_active or rejection_invalidation_reason else "WAIT",
        step2_step4_50_line=participation_lines["line_50"] if active_name and active_price is not None else None,
        step4_step5_75_line=participation_lines["line_75"] if active_name and active_price is not None else None,
        step2_reason=translate_public_terminology(step2.get("state_transition_reason") or step2.get("reason")),
        step4_reason=translate_public_terminology(rejection_step4_reason),
        invalidation_reason=rejection_invalidation_reason if rejection_active or rejection_invalidation_reason else None,
        invalidation_source=rejection_public_invalidation.get("source") if rejection_active or rejection_invalidation_reason else None,
        invalidation_source_step=rejection_public_invalidation.get("source_step") if rejection_active or rejection_invalidation_reason else None,
        invalidation_source_candle_time=rejection_public_invalidation.get("source_candle_time") if rejection_active or rejection_invalidation_reason else None,
        leg2_candidate_candle_time=step5_state.get("leg2_candidate_candle_time") if rejection_active or rejection_invalidation_reason else None,
    )
    rejection_lane["step4_confirmed_at"] = step4_state.get("step4_confirmed_at") or step4_state.get("leg1_completed_at")
    rejection_lane["leg2_sweep_extreme"] = step4_state.get("leg2_sweep_extreme")
    rejection_lane["step5_close_boundary"] = step4_state.get("step5_close_boundary")
    rejection_lane["step2_activated"] = step2.get("step_2_activated") is True
    rejection_lane["rejection_probe_boundary"] = public_rejection_probe_boundary(step2)
    rejection_lane = preserve_invalidated_lane(rejection_lane, previous_symbol_state.get("rejection_lane"))
    if continuation_controlling:
        carried_rejection_lane = carry_forward_confirmed_rejection_lane(previous_symbol_state)
        if isinstance(carried_rejection_lane, dict):
            rejection_lane = dict(carried_rejection_lane)
            rejection_lane["lane_status"] = "frozen"
            rejection_lane["pathway_status"] = "frozen"
    if rejection_lane.get("lane_status") == "idle" and rejection_lane.get("invalidation_reason") is None:
        carried_rejection_lane = carry_forward_pending_rejection_lane(
            snapshot,
            previous_symbol_state,
            rejection_group=active_group if isinstance(active_group, dict) else None,
            rejection_active_price=active_price,
        )
        if not isinstance(carried_rejection_lane, dict):
            carried_rejection_lane = carry_forward_confirmed_rejection_lane(previous_symbol_state)
        if isinstance(carried_rejection_lane, dict):
            rejection_lane = carried_rejection_lane

    # Continuation is built every candle. It becomes controlling only after its
    # own Step 2 confirmation; until then the lane can remain idle or eligible
    # while still publishing its structural and wick boundaries.
    continuation_lane = build_lane_status(
        "continuation",
        lane_status="invalidated" if continuation_invalidation_reason else "controlling" if continuation_controlling else "eligible" if continuation_eligible else "idle",
        pathway_status="invalidated" if continuation_invalidation_reason else "controlling" if continuation_controlling else "eligible" if continuation_eligible else "idle",
        active_liquidity_name=active_name if continuation_controlling or continuation_eligible else None,
        active_liquidity_group=continuation_group if isinstance(continuation_group, dict) and (continuation_controlling or continuation_eligible) else None,
        liquidity_group=(continuation_group or {}).get("name") if isinstance(continuation_group, dict) and (continuation_controlling or continuation_eligible) else None,
        active_liquidity_price=active_price if continuation_controlling or continuation_eligible else None,
        close_boundary=continuation_close_boundary if continuation_controlling or continuation_eligible else None,
        extreme_boundary=continuation_extreme_boundary if continuation_controlling or continuation_eligible else None,
        wick_boundary_extreme=continuation_wick_boundary if continuation_controlling or continuation_eligible else None,
        step2_candle_count=continuation_count if continuation_controlling else None,
        step4_candle_count=None,
        step2_status="CONFIRMED" if continuation_controlling or continuation_invalidation_reason else "WAIT",
        step2_confirmed_at=continuation_step2_time if continuation_controlling or continuation_invalidation_reason else None,
        step25_status=step25.get("status") if continuation_controlling or continuation_invalidation_reason else "WAIT",
        step4_status=continuation_step4_status if continuation_controlling or continuation_invalidation_reason else "WAIT",
        step2_step4_50_line=None,
        step4_step5_75_line=None,
        step2_reason=translate_public_terminology(continuation_step2_reason) if continuation_controlling or continuation_eligible or continuation_invalidation_reason else None,
        step4_reason=translate_public_terminology(continuation_step4_reason) if continuation_controlling or continuation_invalidation_reason else None,
        invalidation_reason=continuation_invalidation_reason,
        invalidation_source=continuation_public_invalidation.get("source") if continuation_invalidation_reason else None,
        invalidation_source_step=continuation_public_invalidation.get("source_step") if continuation_invalidation_reason else None,
        invalidation_source_candle_time=continuation_public_invalidation.get("source_candle_time") if continuation_invalidation_reason else None,
        leg2_candidate_candle_time=step5_state.get("leg2_candidate_candle_time") if continuation_controlling or continuation_invalidation_reason else None,
        continuation_type=continuation_type if continuation_type in {"S/R", "R/S"} else "none",
    )
    if (continuation_controlling or continuation_invalidation_reason) and continuation_contract.get("lane_name") == "continuation":
        continuation_lane["active_liquidity_name"] = continuation_contract.get("owner_name")
        continuation_lane["close_boundary"] = continuation_contract.get("close_boundary")
        continuation_lane["extreme_boundary"] = continuation_contract.get("extreme_boundary")
        continuation_lane["liquidity_group"] = (continuation_group or {}).get("name") if isinstance(continuation_group, dict) else None
        continuation_lane["step4_confirmed_at"] = step4_state.get("step4_confirmed_at") or step4_state.get("leg1_completed_at")
        continuation_lane["leg2_sweep_extreme"] = step4_state.get("leg2_sweep_extreme")
        continuation_lane["step5_close_boundary"] = step4_state.get("step5_close_boundary")
    continuation_lane["continuation_probe_boundary_price"] = continuation_probe_boundary_price(step25_state)
    continuation_lane["continuation_active_boundary_price"] = continuation_active_boundary_price
    # Do not allow the Candle B that confirms rejection Step 4 to also confirm
    # continuation Step 2. Continuation may only confirm on a later candle
    # beyond the seeded Candle B wick boundary.
    if same_candle_rejection_step4_confirmation_active(snapshot, step4, previous_symbol_state):
        continuation_lane["step2_status"] = "WAIT"
        continuation_lane["step2_confirmed_at"] = None
        continuation_lane["step2_candle_count"] = None
    continuation_lane = preserve_invalidated_lane(continuation_lane, previous_symbol_state.get("continuation_lane"))
    if continuation_lane.get("lane_status") == "idle" and continuation_lane.get("invalidation_reason") is None:
        carried_continuation_lane = carry_forward_seeded_continuation_lane(
            previous_symbol_state,
            continuation_group=continuation_group if isinstance(continuation_group, dict) else None,
            active_price=active_price,
        )
        if isinstance(carried_continuation_lane, dict):
            continuation_lane = carried_continuation_lane
    return rejection_lane, continuation_lane


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
    reclaim_candle = step25_state.get("reclaim_candle_a") if isinstance(step25_state.get("reclaim_candle_a"), dict) else None
    if step25_state.get("continuation_step2_activated") is True and isinstance(reclaim_candle, dict):
        for key in ("current_continuation_type", "continuation_type", "requested_mode", "pathway_mode"):
            normalized = normalized_pathway_name(step25_state.get(key))
            if normalized in {"S/R", "R/S"}:
                return normalized
    candidate_modes = step25_state.get("candidate_modes")
    if isinstance(candidate_modes, list):
        for mode in candidate_modes:
            normalized = normalized_pathway_name(mode)
            if normalized in {"S/R", "R/S"}:
                return normalized
    return "none"


def setup_direction_for_continuation(continuation_type: str) -> str | None:
    if continuation_type == "S/R":
        return "SHORT"
    if continuation_type == "R/S":
        return "LONG"
    return None


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
    session_context = snapshot.get("session_liquidity_context") if isinstance(snapshot.get("session_liquidity_context"), dict) else {}
    session_context_stale = bool(snapshot.get("session_context_stale"))
    session_lock_status = (
        "stale"
        if session_context_stale
        else "disabled" if session_context.get("disabled") is True else "locked" if session_context else "unlocked"
    )
    public_current_step = public_step_name(current_step)
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
    canonical_atr = canonical_atr_from_snapshot(snapshot)
    canonical_atr_ready = bool(
        isinstance(canonical_atr, dict)
        and canonical_atr.get("ready") is True
        and canonical_atr.get("formula") == CANONICAL_ATR_FORMULA
        and canonical_atr.get("formula_version") == CANONICAL_ATR_FORMULA_VERSION
    )
    canonical_observation = load_rithmic_atr_observation(root_symbol(symbol))
    empty_lane = build_lane_status(
        "rejection",
        lane_status="idle",
        pathway_status="inactive",
        active_liquidity_name=None,
        active_liquidity_group=None,
        liquidity_group=None,
        active_liquidity_price=None,
        close_boundary=None,
        extreme_boundary=None,
        wick_boundary_extreme=None,
        step2_candle_count=None,
        step4_candle_count=None,
        step2_status="WAIT",
        step2_confirmed_at=None,
        step25_status="WAIT",
        step4_status="WAIT",
        step2_step4_50_line=None,
        step4_step5_75_line=None,
        step2_reason=None,
        step4_reason=None,
        invalidation_reason=None,
        invalidation_source=None,
        invalidation_source_step=None,
        invalidation_source_candle_time=None,
        leg2_candidate_candle_time=None,
    )
    return {
        "symbol": str(snapshot.get("requested_symbol") or snapshot.get("symbol") or symbol).upper(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_lock_status": session_lock_status,
        "session_lock_error": session_context.get("error"),
        "session_authority": {
            "effective_session_date": snapshot.get("effective_session_date"),
            "rithmic_session_date": snapshot.get("rithmic_session_date"),
            "tradingview_session_date": snapshot.get("tradingview_session_date"),
            "session_authority_source": snapshot.get("session_authority_source"),
            "session_context_stale": session_context_stale,
        },
        "liquidity_lock": public_liquidity_lock_payload(snapshot, None, None, None),
        "candle_time": snapshot.get("latest_bar_time"),
        "candle_open": ohlc.get("open"),
        "candle_high": ohlc.get("high"),
        "candle_low": ohlc.get("low"),
        "candle_close": ohlc.get("close"),
        "canonical_atr": copy.deepcopy(canonical_atr) if canonical_atr_ready else None,
        "canonical_atr_ready": canonical_atr_ready,
        "atr_1m_14": canonical_atr.get("updated_raw_atr") if canonical_atr_ready else None,
        "atr_record_id": canonical_atr.get("atr_record_id") if canonical_atr_ready else None,
        "atr_bar_id": canonical_atr.get("bar_id") if canonical_atr_ready else None,
        "atr_formula": canonical_atr.get("formula") if canonical_atr_ready else CANONICAL_ATR_FORMULA,
        "atr_formula_version": canonical_atr.get("formula_version") if canonical_atr_ready else CANONICAL_ATR_FORMULA_VERSION,
        "atr_last_included_bar": canonical_atr.get("last_included_bar") if canonical_atr_ready else None,
        **canonical_atr_status_projection(canonical_observation),
        "current_step": public_current_step,
        "current_step_label": current_step_label(public_current_step),
        "step2_lifecycle_window_terminated": False,
        "frozen_active_groups": [],
        "frozen_group_found": False,
        "frozen_group_display_name": None,
        "canonical_group_display_name": None,
        "selected_liquidity_name": None,
        "current_step_status": "WAIT",
        "current_step_confirmed_at": None,
        "step2_candle_count": None,
        "selected_pathway": None,
        "active_liquidity_name": None,
        "active_liquidity_price": None,
        "active_liquidity_group": None,
        "trade_state": {"active": False, "released": False, "release_reason": None},
        "market_state": {"active_liquidity_name": None, "selected_liquidity_name": None},
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
        "rejection_side": {**dict(side), **empty_lane},
        "continuation_side": {**side, **{**empty_lane, "lane_name": "continuation", "continuation_type": "none"}},
        "rejection_lane": dict(empty_lane),
        "continuation_lane": {**empty_lane, "lane_name": "continuation", "continuation_type": "none"},
        "leg1_status": "WAIT",
        "leg1_state": "WAIT",
        "leg1_confirmed_at": None,
        "leg1_locked": False,
        "leg1_state_locked": False,
        "leg2_status": "WAIT",
        "leg2_state": "WAIT",
        "entry_status": "WAIT",
        "wait_reason": translate_public_terminology(reason),
        "last_decision": translate_public_terminology(f"WAIT: {reason}"),
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


@entry_state_transaction
@projection_only
def build_entry_status(symbol: str = "NQ") -> dict[str, Any]:
    """Build the minimal read-only Entry Manager status for one symbol."""
    requested_symbol = str(symbol or "NQ").strip().upper()
    normalized_symbol = root_symbol(requested_symbol)
    if normalized_symbol not in SUPPORTED_ROOT_SYMBOLS:
        return unsupported_symbol_result(requested_symbol)
    persisted_state = load_entry_state()
    persisted_symbol_state = symbol_scoped_persisted_state(persisted_state, normalized_symbol)
    snapshot = run_once(symbol, persist=False)
    lock = entry_window_lock_for_snapshot(snapshot) if isinstance(snapshot, dict) else None
    if isinstance(snapshot, dict) and lock is not None and has_stale_session_lifecycle(persisted_state, normalized_symbol, snapshot):
        current_step, reason = lock
        snapshot["requested_symbol"] = requested_symbol
        return locked_entry_status(symbol, snapshot, current_step, reason)
    hide_unconfirmed_current_candle_advancement(snapshot)
    apply_consumed_entry_setup_projection_guard(snapshot)
    step4 = snapshot.get("step4") if isinstance(snapshot.get("step4"), dict) else {}
    step5 = snapshot.get("step5") if isinstance(snapshot.get("step5"), dict) else {}
    step6 = snapshot.get("step6") if isinstance(snapshot.get("step6"), dict) else {}
    step_2_1a = snapshot.get("step_2_1a") if isinstance(snapshot.get("step_2_1a"), dict) else {}
    rejection = snapshot.get("rejection") if isinstance(snapshot.get("rejection"), dict) else {}
    step25_state = ((snapshot.get("step25") or {}).get("state") or {}) if isinstance((snapshot.get("step25") or {}).get("state"), dict) else {}
    step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
    step5_state = step5.get("state") if isinstance(step5.get("state"), dict) else {}
    step6_state = step6.get("state") if isinstance(step6.get("state"), dict) else {}
    current_canonical_atr = canonical_atr_from_snapshot(snapshot)
    current_canonical_atr_observation = load_rithmic_atr_observation(normalized_symbol)
    step2_owner_state = step_2_1a.get("step2_locked_owner") if isinstance(step_2_1a.get("step2_locked_owner"), dict) else {}
    step2_owner_active = step2_owner_state.get("active_liquidity") if isinstance(step2_owner_state.get("active_liquidity"), dict) else {}
    last_interacted = step_2_1a.get("last_interacted_liquidity") if isinstance(step_2_1a.get("last_interacted_liquidity"), dict) else {}
    liquidity = snapshot.get("liquidity") if isinstance(snapshot.get("liquidity"), dict) else {}
    ohlc = snapshot.get("ohlc") if isinstance(snapshot.get("ohlc"), dict) else {}
    observation_only = before_entry_authorization(snapshot)
    observation_reason = "06:15-06:29 PT is observation-only. Liquidity and wick-reset/pre-open extremes may be tracked, but Step 2+ activation is disabled until 06:30."
    observation_liquidity = public_observation_liquidity_from_snapshot(snapshot) if observation_only else None
    active_name, active_price = (
        (observation_liquidity.get("name"), observation_liquidity.get("price"))
        if isinstance(observation_liquidity, dict)
        else active_liquidity_from_snapshot(snapshot)
    )
    active_group = (
        observation_liquidity.get("group")
        if isinstance(observation_liquidity, dict) and isinstance(observation_liquidity.get("group"), dict)
        else active_liquidity_group_from_snapshot(snapshot)
    )
    persisted_active_group = active_liquidity_group_from_snapshot(snapshot)
    active_group = merge_monotonic_stack_wick_boundary(active_group, persisted_active_group)
    active_group = stack_group_with_pre_open_wick_boundary(active_group, snapshot.get("pre_open_observed_extreme") if observation_only else None)
    session_context = snapshot.get("session_liquidity_context") if isinstance(snapshot.get("session_liquidity_context"), dict) else {}
    frozen_active_groups = [dict(group) for group in (session_context.get("active_groups") or []) if isinstance(group, dict)]
    selected_liquidity_name = None
    if candle_close_confirmed(snapshot):
        selected_liquidity_debug = selected_active_liquidity_from_context(
            snapshot.get("tv_context"),
            snapshot.get("latest_price"),
            snapshot.get("ohlc") if isinstance(snapshot.get("ohlc"), dict) else None,
            float((liquidity or {}).get("tick_size") or 0.25),
        )
        if isinstance(selected_liquidity_debug, dict):
            selected_liquidity_name = selected_liquidity_debug.get("name")
    frozen_group_debug = frozen_session_group_for_liquidity(snapshot, selected_liquidity_name or active_name, active_price)
    frozen_group_found = isinstance(frozen_group_debug, dict)
    frozen_group_display_name = (
        frozen_group_debug.get("display_name")
        if isinstance(frozen_group_debug, dict) and isinstance(frozen_group_debug.get("display_name"), str)
        else None
    )
    canonical_group_name_debug = canonical_group_display_name(active_group if isinstance(active_group, dict) else frozen_group_debug)
    active_name = public_active_liquidity_display_name(snapshot, active_group, active_name, active_price)
    locked_trade_owner = locked_trade_lifecycle_owner(snapshot)
    lifecycle_owner_locked = isinstance(locked_trade_owner, dict)
    if lifecycle_owner_locked:
        active_name = locked_trade_owner.get("display_name") or active_name
        active_price = locked_trade_owner.get("price") if locked_trade_owner.get("price") is not None else active_price
        if isinstance(locked_trade_owner.get("group"), dict):
            active_group = locked_trade_owner.get("group")
        else:
            active_group = None
        selected_liquidity_name = locked_trade_owner.get("name") or selected_liquidity_name
        if locked_trade_owner.get("group_display_name"):
            frozen_group_display_name = locked_trade_owner.get("group_display_name")
        canonical_group_name_debug = canonical_group_display_name(active_group if isinstance(active_group, dict) else frozen_group_debug)
    projected_pending_step4_state = projected_pending_rejection_step4_state(
        snapshot,
        persisted_symbol_state,
        rejection_group=active_group if isinstance(active_group, dict) else None,
        rejection_active_price=active_price,
    )
    if (not step4_state or not step4_state.get("leg1_window_started_at")) and isinstance(projected_pending_step4_state, dict):
        step4_state = projected_pending_step4_state
        step4 = {**step4, "status": step4.get("status") or "WAIT", "next_step": step4.get("next_step") or "Step 4", "state": step4_state}
    step2_window_terminated = step2_lifecycle_window_terminated(snapshot, step_2_1a, step4)
    boundary_owner_state = {} if step2_window_terminated else step2_owner_state
    boundary_active_liquidity = (
        {"price": active_price}
        if step2_window_terminated
        else step2_owner_active or last_interacted or {"price": active_price}
    )
    close_boundary = audit_boundary_value("close_boundary", active_group, boundary_owner_state, boundary_active_liquidity, step_2_1a)
    extreme_boundary = audit_boundary_value("extreme_boundary", active_group, boundary_owner_state, boundary_active_liquidity, step_2_1a)
    wick_boundary_extreme = audit_boundary_value("wick_boundary_extreme", active_group, boundary_owner_state, boundary_active_liquidity, step_2_1a)
    market_active_name = active_name
    market_active_price = active_price
    market_active_group = copy.deepcopy(active_group) if isinstance(active_group, dict) else None
    market_selected_liquidity_name = selected_liquidity_name
    market_close_boundary = close_boundary
    market_extreme_boundary = extreme_boundary
    market_wick_boundary_extreme = wick_boundary_extreme
    if lifecycle_owner_locked:
        close_boundary = locked_trade_owner.get("close_boundary") if locked_trade_owner.get("close_boundary") is not None else close_boundary
        extreme_boundary = locked_trade_owner.get("extreme_boundary") if locked_trade_owner.get("extreme_boundary") is not None else extreme_boundary
        wick_boundary_extreme = locked_trade_owner.get("wick_boundary_extreme") if locked_trade_owner.get("wick_boundary_extreme") is not None else wick_boundary_extreme
    actionable_boundary = actionable_boundary_from_group(active_group, extreme_boundary)
    no_active_liquidity = snapshot.get("latest_price") is not None and not valid_active_liquidity_selection(active_name, active_price)
    current_step = current_step_from_snapshot(snapshot)
    public_current_step = public_step_name(current_step)
    step_label = current_step_label(public_current_step)
    seeded_step4_projection = projected_seeded_step4_status(snapshot, step_2_1a, step4)
    raw_invalidation_reason = first_invalidation_reason(step4, step5, step6)
    public_invalidation = public_invalidation_from_results(current_step, step4, step5, step6)
    invalidation_reason = public_invalidation["reason"]
    atr_required_reason = invalidation_reason if is_atr_required_reason(invalidation_reason) else None
    raw_entry_status = decision_status(step6)
    if raw_entry_status == "INVALIDATE" and not invalidation_reason:
        raw_entry_status = "WAIT"
    entry_status = "WAIT_ATR_REQUIRED" if atr_required_reason else ("INVALIDATE" if invalidation_reason else raw_entry_status)
    # The trade-authoritative ATR is the latest completed-bar record available
    # at the entry decision. A lifecycle may span several minutes, so an older
    # telemetry copy carried by Step 4/5 must never replace the current record.
    selected_canonical_atr = current_canonical_atr
    canonical_atr_ready = bool(
        isinstance(selected_canonical_atr, dict)
        and selected_canonical_atr.get("ready") is True
        and selected_canonical_atr.get("formula") == CANONICAL_ATR_FORMULA
        and selected_canonical_atr.get("formula_version") == CANONICAL_ATR_FORMULA_VERSION
    )
    if raw_entry_status == "CONFIRM" and not canonical_atr_ready:
        atr_required_reason = "Canonical Rithmic Wilder RMA(14) ATR is not ready."
        entry_status = "WAIT_ATR_REQUIRED"
    if atr_required_reason:
        invalidation_reason = None
    entry_authorization_blocked = entry_status == "CONFIRM" and observation_only
    if entry_authorization_blocked:
        entry_status = "WAIT"

    if snapshot.get("latest_price") is None:
        wait_reason = "No market price available."
    elif atr_required_reason:
        wait_reason = atr_required_reason
    elif observation_only:
        wait_reason = observation_reason
    elif current_step == "Step 2" and seeded_step4_projection:
        wait_reason = str(seeded_step4_projection.get("reason"))
    elif entry_status == "WAIT" and not invalidation_reason and not candle_close_confirmed(snapshot):
        live_mask_reason = result_reason(step4, "")
        wait_reason = live_mask_reason if "current 1-minute candle" in live_mask_reason else wait_reason_for_current_step(current_step, active_name, bool(step_2_1a.get("step_2_activated")), step4, step5, step6)
    elif entry_status == "WAIT" and not invalidation_reason:
        wait_reason = wait_reason_for_current_step(current_step, active_name, bool(step_2_1a.get("step_2_activated")), step4, step5, step6)
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
        pending_boundary = actionable_boundary if actionable_boundary is not None else probe.get("boundary_price")
        wait_reason = f"Step 2 pending: waiting for a later candle close {direction_text} raid boundary {pending_boundary}."

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
    leg1_published = current_step in {"Step 4", "Step 5", "Step 6"} or bool(step4_state.get("step4_confirmed_at") or step4_state.get("leg1_completed_at"))
    leg2_published = current_step in {"Step 5", "Step 6"}
    leg1_status = raw_leg1_status if leg1_published else "WAIT"
    leg2_status = raw_leg2_status if leg2_published else "WAIT"
    if current_step == "Step 4" and leg1_status == "COMPLETE":
        step_label = "Leg 1 Complete"
    step2_rejection_confirmed = (
        current_step == "Step 2"
        and valid_active_liquidity_selection(active_name, active_price)
        and rejection.get("rejection_mode") == "ON"
        and candle_close_confirmed(snapshot)
    )
    step2_pathway_confirmed = (step_2_1a.get("step_2_activated") is True and not step2_window_terminated) or step2_rejection_confirmed
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
    continuation_setup_direction = setup_direction_for_continuation(continuation_type)
    if selected_pathway == "continuation" and continuation_setup_direction:
        public_setup_direction = continuation_setup_direction
    if observation_only:
        selected_pathway = None
        sr_rs_context = None
        public_setup_direction = None
        rejection_active = False
        continuation_type = "none"
        current_pathway_control = "OBSERVATION_ONLY"
        current_controlling_mode = None
        current_continuation_type = "none"
    frozen_step4_selected_pathway = snapshot.get("frozen_step4_selected_pathway")
    frozen_step4_setup_direction = snapshot.get("frozen_step4_setup_direction")
    if (
        not observation_only
        and isinstance(frozen_step4_selected_pathway, str)
        and frozen_step4_selected_pathway in {"rejection", "continuation"}
    ):
        selected_pathway = frozen_step4_selected_pathway
        current_pathway_control = frozen_step4_selected_pathway
        if frozen_step4_selected_pathway == "rejection":
            current_controlling_mode = "Normal Rejection Mode"
            current_continuation_type = continuation_type if continuation_type in {"S/R", "R/S"} else "none"
        else:
            current_controlling_mode = continuation_type if continuation_type in {"S/R", "R/S"} else (
                step4_state.get("current_controlling_mode")
                or sr_rs_context
            )
            current_continuation_type = continuation_type
    if isinstance(frozen_step4_setup_direction, str) and frozen_step4_setup_direction.strip():
        public_setup_direction = frozen_step4_setup_direction
    invalidated = bool(invalidation_reason)
    step25_ready = (snapshot.get("step25") or {}).get("status") == "READY"
    continuation_visibility_active = (
        continuation_type in {"S/R", "R/S"}
        and step25_ready
        and step25_state.get("continuation_step2_activated") is True
        and isinstance(step25_state.get("reclaim_candle_a"), dict)
        and not invalidated
    )
    current_step_status = current_step_public_status(current_step, active_name, rejection_active)
    if observation_only:
        current_step_status = "OBSERVATION_ONLY"
    step2_time = step2_confirmed_at(snapshot, step_2_1a, current_step_status)
    rejection_step2_time, step2_anchor_status, step2_anchor_reason = step2_anchor_publication_state(snapshot, step_2_1a, "CONFIRMED")
    if selected_pathway == "continuation":
        continuation_step2_time = continuation_step2_confirmed_at(step25_state)
        if continuation_step2_time:
            step2_time = continuation_step2_time
    step2_owner_display = step2_owner_name(snapshot, step_2_1a)
    step2_owner_seeded_time = (
        step_2_1a.get("step2_owner_seeded_at")
        or step2_owner_state.get("owner_seeded_at")
        or candle_timestamp(step_2_1a.get("candle_a") if isinstance(step_2_1a.get("candle_a"), dict) else None)
    )
    step2_invalidated_time = step_2_1a.get("step2_invalidated_at")
    leg1_time = leg1_confirmed_at(step4_state, leg1_published)
    leg2_time = leg2_confirmed_at(step5_state, leg2_published)
    entry_time = entry_confirmed_at(snapshot, step6_state, entry_status)
    current_step_time = current_step_confirmed_at(current_step, step2_time, leg1_time, leg2_time, entry_time)
    step4_confirmed_at = step4_state.get("step4_confirmed_at") or step4_state.get("leg1_completed_at")
    step4_window_count = public_lifecycle_candle_count(step4_state.get("step4_window_count") or step4_state.get("participation_candidate_count"))
    step4_candle_a_time = (
        candle_timestamp(step4_state.get("candle_a") if isinstance(step4_state.get("candle_a"), dict) else None)
        or candle_timestamp(step4_state.get("initial_candle_a") if isinstance(step4_state.get("initial_candle_a"), dict) else None)
        or step2_time
    )
    step4_candle_b_time = candle_timestamp(step4_state.get("candle_b") if isinstance(step4_state.get("candle_b"), dict) else None) or step4_confirmed_at
    step4_invalidated_time = step4_state.get("invalidated_at") or (
        public_invalidation["invalidated_at"]
        if public_invalidation.get("source_step") == "Step 4"
        else None
    )
    step4_owner_display = step4_owner_name(snapshot, step4_state)
    step4_event = latest_event_name(step4.get("events"))
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
    preserve_rejection_step2_milestone = (
        continuation_selected
        and rejection_active
        and step_2_1a.get("step_2_activated") is True
        and rejection_step2_time is not None
        and not invalidated
    )
    participation_lines = step4_participation_line_payload(
        snapshot,
        step_2_1a,
        step4_state,
        rejection_active=rejection_active,
        selected_pathway=selected_pathway,
        setup_direction=public_setup_direction or setup_direction,
        leg1_published=leg1_published,
        invalidated=invalidated,
    )
    liquidity_leg_telemetry = liquidity_leg_atr_telemetry_from_snapshot(
        snapshot,
        step_2_1a,
        active_name,
        active_price,
        active_group,
    )
    rejection_side = {
        "pathway_status": (
            "entered"
            if finalized_rejection_projection
            else "frozen"
            if continuation_selected
            else
            "controlling"
            if shared_leg1_with_continuation and rejection_active and not invalidated
            else "controlling"
            if current_step == "Step 2" and current_step_status == "CONFIRMED" and selected_pathway == "rejection"
            else pathway_visibility_status("rejection", rejection_active, sr_rs_context, continuation_type, invalidated, step25_ready)
        ),
        "current_pathway_control": None if continuation_selected else current_pathway_control,
        "current_controlling_mode": None if continuation_selected else current_controlling_mode,
        "current_step": "Step 2" if preserve_rejection_step2_milestone else (None if continuation_selected else current_step),
        "current_step_label": current_step_label("Step 2") if preserve_rejection_step2_milestone else (None if continuation_selected else step_label),
        "current_step_status": "CONFIRMED" if preserve_rejection_step2_milestone else (None if continuation_selected else current_step_status),
        "current_step_confirmed_at": rejection_step2_time if preserve_rejection_step2_milestone else (None if continuation_selected else current_step_time),
        "selected_pathway": None if continuation_selected else selected_pathway,
        "setup_direction": None if selected_pathway == "continuation" else (rejection.get("watch_side") if rejection_active and leg1_published else public_setup_direction),
        "step2_status": "CONFIRMED" if preserve_rejection_step2_milestone else None,
        "step2_confirmed_at": rejection_step2_time if preserve_rejection_step2_milestone else None,
        "leg1_status": None if continuation_selected else leg1_status,
        "leg1_state": None if continuation_selected else leg1_status,
        "leg2_status": None if continuation_selected else leg2_status,
        "leg2_state": None if continuation_selected else leg2_status,
        "entry_status": None if continuation_selected else entry_status,
        "leg1_confirmed_at": None if continuation_selected else leg1_time,
        "leg2_confirmed_at": None if continuation_selected else leg2_time,
        "entry_status_confirmed_at": None if continuation_selected else entry_time,
        "step4_participation_reference_liquidity": None if continuation_selected else participation_lines["reference_liquidity"],
        "step2_step4_50_line": None if continuation_selected else participation_lines["line_50"],
        "step4_step5_75_line": None if continuation_selected else participation_lines["line_75"],
        "step4_participation_50_line": None if continuation_selected else participation_lines["line_50"],
        "step4_participation_75_line": None if continuation_selected else participation_lines["line_75"],
        "step4_participation_lines_visible": False if continuation_selected else participation_lines["visible"],
    }
    continuation_side = {
        "continuation_type": continuation_type,
        "pathway_status": (
            "controlling"
            if continuation_selected
            else "active"
            if continuation_visibility_active
            else pathway_visibility_status("continuation", rejection_active, sr_rs_context, continuation_type, invalidated, step25_ready)
        ),
        "current_pathway_control": current_pathway_control,
        "current_controlling_mode": current_controlling_mode,
        "current_step": current_step if continuation_selected else None,
        "current_step_label": step_label if continuation_selected else None,
        "current_step_status": current_step_status if continuation_selected else None,
        "current_step_confirmed_at": current_step_time if continuation_selected else None,
        "selected_pathway": selected_pathway if continuation_selected else None,
        "setup_direction": continuation_setup_direction,
        "leg1_status": leg1_status if continuation_selected else None,
        "leg1_state": leg1_status if continuation_selected else None,
        "leg2_status": leg2_status if continuation_selected else None,
        "leg2_state": leg2_status if continuation_selected else None,
        "entry_status": entry_status if continuation_selected else None,
        "leg1_confirmed_at": leg1_time if continuation_selected else None,
        "leg2_confirmed_at": leg2_time if continuation_selected else None,
        "entry_status_confirmed_at": entry_time if continuation_selected else None,
    }
    session_context = snapshot.get("session_liquidity_context") if isinstance(snapshot.get("session_liquidity_context"), dict) else {}
    observed_extreme = snapshot.get("pre_open_observed_extreme") if isinstance(snapshot.get("pre_open_observed_extreme"), dict) else {}
    blocked_preopen_status = "BLOCKED_PREOPEN_OBSERVATION" if observation_only else None
    blocked_preopen_reason = observation_reason if observation_only else None
    step2_count = step2_candle_count(snapshot, step_2_1a)
    rejection_lane = snapshot.get("rejection_lane") if isinstance(snapshot.get("rejection_lane"), dict) else None
    continuation_lane = snapshot.get("continuation_lane") if isinstance(snapshot.get("continuation_lane"), dict) else None
    if not isinstance(rejection_lane, dict) or not isinstance(continuation_lane, dict):
        rejection_lane, continuation_lane = snapshot_lane_statuses(snapshot, persisted_symbol_state)
        snapshot["rejection_lane"] = rejection_lane
        snapshot["continuation_lane"] = continuation_lane
    same_candle_rejection_step4 = same_candle_rejection_step4_confirmation_active(snapshot, step4, persisted_symbol_state)
    if step2_time is None and isinstance(rejection_lane, dict):
        step2_time = rejection_lane.get("step2_confirmed_at") or step2_time
    if step2_count is None and isinstance(rejection_lane, dict):
        step2_count = public_lifecycle_candle_count(rejection_lane.get("step2_candle_count"))
    projected_lane = (
        rejection_lane if same_candle_rejection_step4 and rejection_lane.get("lane_status") in {"controlling", "frozen", "invalidated"}
        else continuation_lane if continuation_lane.get("lane_status") == "controlling"
        else rejection_lane if rejection_lane.get("lane_status") == "controlling"
        else rejection_lane if rejection_lane.get("lane_status") == "frozen"
        else rejection_lane if rejection_lane.get("lane_status") == "invalidated"
        else continuation_lane if continuation_lane.get("lane_status") == "eligible"
        else continuation_lane if continuation_lane.get("lane_status") == "invalidated"
        else None
    )
    projected_selected_pathway = (
        "rejection" if same_candle_rejection_step4 and rejection_lane.get("lane_status") in {"controlling", "frozen", "invalidated"}
        else "continuation" if continuation_lane.get("lane_status") == "controlling"
        else "rejection" if rejection_lane.get("lane_status") == "frozen"
        else "rejection" if rejection_lane.get("lane_status") == "controlling"
        else None
    )
    if isinstance(projected_lane, dict) and not observation_only:
        active_name = projected_lane.get("active_liquidity_name") or active_name
        active_price = projected_lane.get("active_liquidity_price") if projected_lane.get("active_liquidity_price") is not None else active_price
        if step2_count is None:
            step2_count = public_lifecycle_candle_count(projected_lane.get("candle_count"))
        invalidation_reason = projected_lane.get("invalidation_reason") or invalidation_reason
        if invalidation_reason:
            entry_status = "INVALIDATE"
            last_decision = f"INVALIDATE: {invalidation_reason}"
        if projected_lane.get("step4_status") is not None:
            snapshot["step4"] = {
                **dict(snapshot.get("step4") or {}),
                "status": projected_lane.get("step4_status"),
                "reason": projected_lane.get("invalidation_reason") or (snapshot.get("step4") or {}).get("reason"),
            }
        selected_pathway = projected_selected_pathway
        if projected_selected_pathway is not None:
            current_pathway_control = projected_selected_pathway
    if lifecycle_owner_locked:
        active_name = locked_trade_owner.get("display_name") or active_name
        active_price = locked_trade_owner.get("price") if locked_trade_owner.get("price") is not None else active_price
        if isinstance(locked_trade_owner.get("group"), dict):
            active_group = locked_trade_owner.get("group")
        else:
            active_group = None
        selected_liquidity_name = locked_trade_owner.get("name") or selected_liquidity_name
        close_boundary = locked_trade_owner.get("close_boundary") if locked_trade_owner.get("close_boundary") is not None else close_boundary
        extreme_boundary = locked_trade_owner.get("extreme_boundary") if locked_trade_owner.get("extreme_boundary") is not None else extreme_boundary
        wick_boundary_extreme = locked_trade_owner.get("wick_boundary_extreme") if locked_trade_owner.get("wick_boundary_extreme") is not None else wick_boundary_extreme
        if continuation_lane.get("lane_status") != "controlling":
            projected_lane = rejection_lane if isinstance(rejection_lane, dict) else projected_lane
            projected_selected_pathway = "rejection"
            selected_pathway = "rejection"
            current_pathway_control = "rejection"
    if same_candle_rejection_step4:
        selected_pathway = "rejection"
        current_pathway_control = "rejection"
    if (
        not observation_only
        and isinstance(frozen_step4_selected_pathway, str)
        and frozen_step4_selected_pathway in {"rejection", "continuation"}
        and continuation_lane.get("lane_status") != "controlling"
    ):
        selected_pathway = frozen_step4_selected_pathway
        projected_selected_pathway = frozen_step4_selected_pathway
        current_pathway_control = frozen_step4_selected_pathway
    if continuation_lane.get("lane_status") == "controlling":
        continuation_boundary_for_control = optional_float(step25_state.get("continuation_active_boundary_price"))
        if continuation_boundary_for_control is None:
            continuation_boundary_for_control = optional_float(step25_state.get("continuation_reference_boundary_price"))
        routed_control = public_pathway_control_from_continuation_boundary(
            ohlc.get("close"),
            continuation_boundary_for_control,
            snapshot.get("frozen_step2_direction") or public_setup_direction or step2_owner_state.get("setup_direction"),
        )
        if routed_control in {"rejection", "continuation"}:
            current_pathway_control = routed_control
            selected_pathway = routed_control
            projected_selected_pathway = routed_control
            if routed_control == "continuation":
                current_controlling_mode = continuation_type if continuation_type in {"S/R", "R/S"} else current_controlling_mode
            else:
                current_controlling_mode = "Normal Rejection Mode"
    if (
        isinstance(projected_lane, dict)
        and generic_wait_reset_reason(wait_reason)
        and not invalidation_reason
        and not atr_required_reason
    ):
        if same_candle_rejection_step4:
            wait_reason = result_reason(step4, wait_reason)
        elif continuation_lane.get("lane_status") == "eligible":
            continuation_wait_reason = (
                step25_state.get("step25_block_reason")
                or step25.get("reason")
                or "Continuation seeded from rejection Step 4. Waiting for a later candle close through the continuation boundary."
            )
            wait_reason = str(continuation_wait_reason)
        elif rejection_lane.get("lane_status") in {"controlling", "frozen"}:
            wait_reason = result_reason(step4, wait_reason)
        last_decision = f"WAIT: {wait_reason}"
    if step2_window_terminated and current_step == "Step 2" and projected_selected_pathway is None:
        current_step = "Step 1"
        public_current_step = public_step_name(current_step)
        step_label = current_step_label(public_current_step)
        current_step_status = "WAIT"
        current_step_time = None
        wait_reason = wait_reason_for_current_step(current_step, active_name, False, step4, step5, step6)
        if entry_status == "CONFIRM":
            last_decision = f"CONFIRM: {result_reason(step6, 'Entry setup confirmed.')}"
        elif atr_required_reason:
            last_decision = f"WAIT_ATR_REQUIRED: {atr_required_reason}"
        elif invalidation_reason:
            last_decision = f"INVALIDATE: {invalidation_reason}"
        else:
            last_decision = f"WAIT: {wait_reason}"
    public_rejection_lane = public_lane_projection(rejection_lane)
    public_continuation_lane = public_lane_projection(continuation_lane)
    rejection_lane_group = frozen_session_group_for_liquidity(
        snapshot,
        public_rejection_lane.get("active_liquidity_name"),
        public_rejection_lane.get("active_liquidity_price"),
    )
    continuation_lane_group = frozen_session_group_for_liquidity(
        snapshot,
        public_continuation_lane.get("active_liquidity_name"),
        public_continuation_lane.get("active_liquidity_price"),
    )
    public_rejection_lane["active_liquidity_name"] = public_active_liquidity_display_name(
        snapshot,
        rejection_lane_group,
        public_rejection_lane.get("active_liquidity_name"),
        public_rejection_lane.get("active_liquidity_price"),
    )
    public_continuation_lane["active_liquidity_name"] = public_active_liquidity_display_name(
        snapshot,
        continuation_lane_group,
        public_continuation_lane.get("active_liquidity_name"),
        public_continuation_lane.get("active_liquidity_price"),
    )
    trade_state_snapshot = snapshot.get("trade_state") if isinstance(snapshot.get("trade_state"), dict) else build_trade_state_snapshot(snapshot)
    trade_state = {
        "active": trade_state_snapshot.get("active") is True,
        "released": trade_state_snapshot.get("released") is True,
        "release_reason": trade_state_snapshot.get("release_reason"),
        "lane_name": trade_state_snapshot.get("lane_name"),
        "selected_pathway": trade_state_snapshot.get("selected_pathway") or (projected_selected_pathway if trade_state_snapshot.get("active") is True else None),
        "owner": trade_state_snapshot.get("owner") or step2_owner_display,
        "active_liquidity_name": trade_state_snapshot.get("active_liquidity_name") or public_active_liquidity_display_name(snapshot, active_group, active_name, active_price),
        "selected_liquidity_name": trade_state_snapshot.get("selected_liquidity_name") or selected_liquidity_name,
        "active_liquidity_price": trade_state_snapshot.get("active_liquidity_price") if trade_state_snapshot.get("active_liquidity_price") is not None else active_price,
        "active_liquidity_group": copy.deepcopy(trade_state_snapshot.get("active_liquidity_group")) if isinstance(trade_state_snapshot.get("active_liquidity_group"), dict) else (copy.deepcopy(active_group) if trade_state_snapshot.get("active") is True and isinstance(active_group, dict) else None),
        "liquidity_group": trade_state_snapshot.get("liquidity_group") if trade_state_snapshot.get("liquidity_group") is not None else ((active_group or {}).get("name") if isinstance(active_group, dict) else None),
        "close_boundary": trade_state_snapshot.get("close_boundary") if trade_state_snapshot.get("close_boundary") is not None else close_boundary,
        "extreme_boundary": trade_state_snapshot.get("extreme_boundary") if trade_state_snapshot.get("extreme_boundary") is not None else extreme_boundary,
        "wick_boundary_extreme": trade_state_snapshot.get("wick_boundary_extreme") if trade_state_snapshot.get("wick_boundary_extreme") is not None else wick_boundary_extreme,
        "step2": {
            "confirmed_at": (trade_state_snapshot.get("step2") or {}).get("confirmed_at") or step2_time,
            "owner_seeded_at": (trade_state_snapshot.get("step2") or {}).get("owner_seeded_at") or step2_owner_seeded_time,
            "activated_at": (trade_state_snapshot.get("step2") or {}).get("activated_at") or step_2_1a.get("step2_activated_at") or step2_owner_state.get("activated_at"),
            "direction": (trade_state_snapshot.get("step2") or {}).get("direction") or snapshot.get("frozen_step2_direction") or public_setup_direction or step2_owner_state.get("setup_direction") or step25_state.get("setup_direction"),
            "window_started_at": (trade_state_snapshot.get("step2") or {}).get("window_started_at") or step_2_1a.get("step2_activated_at") or step2_owner_state.get("activated_at"),
            "owner_name": (trade_state_snapshot.get("step2") or {}).get("owner_name") or step2_owner_display,
        },
        "step4": {
            "confirmed_at": (trade_state_snapshot.get("step4") or {}).get("confirmed_at") or step4_confirmed_at,
            "participation_confirmed": (trade_state_snapshot.get("step4") or {}).get("participation_confirmed") is True or bool(step4_confirmed_at),
            "window_count": (trade_state_snapshot.get("step4") or {}).get("window_count") if (trade_state_snapshot.get("step4") or {}).get("window_count") is not None else step4_window_count,
            "leg2_sweep_extreme": (trade_state_snapshot.get("step4") or {}).get("leg2_sweep_extreme") if (trade_state_snapshot.get("step4") or {}).get("leg2_sweep_extreme") is not None else step4_state.get("leg2_sweep_extreme"),
            "step5_close_boundary": (trade_state_snapshot.get("step4") or {}).get("step5_close_boundary") if (trade_state_snapshot.get("step4") or {}).get("step5_close_boundary") is not None else step4_state.get("step5_close_boundary"),
        },
    }
    continuation_lane_status = str((public_continuation_lane or {}).get("lane_status") or "").strip().lower()
    continuation_eligible = (
        continuation_lane_status == "eligible"
        or (
            continuation_lane_status != "controlling"
            and trade_state["active"]
            and str(trade_state.get("selected_pathway") or "").strip().lower() == "rejection"
            and step4_confirmed_at is not None
        )
    )
    continuation_eligible_at = step25_state.get("continuation_eligible_at") or (step4_confirmed_at if continuation_eligible else None)
    continuation_evaluation_started_at = step25_state.get("continuation_evaluation_started_at")
    continuation_reference_boundary_type = step25_state.get("continuation_reference_boundary_type")
    continuation_reference_boundary_price = step25_state.get("continuation_reference_boundary_price")
    continuation_active_boundary_price = optional_float(step25_state.get("continuation_active_boundary_price"))
    continuation_probe_boundary_value = continuation_probe_boundary_price(step25_state)
    continuation_evaluation_reason = step25_state.get("continuation_evaluation_reason") or step25_state.get("step25_block_reason")
    if continuation_eligible and continuation_reference_boundary_price is None:
        continuation_reference_boundary_type = "frozen_rejection_close_boundary"
        continuation_reference_boundary_price = trade_state.get("close_boundary")
    if continuation_active_boundary_price is None:
        continuation_active_boundary_price = continuation_reference_boundary_price
    governing_continuation_boundary = continuation_active_boundary_price
    if governing_continuation_boundary is None:
        governing_continuation_boundary = continuation_probe_boundary_value
    if continuation_eligible and continuation_evaluation_reason is None and continuation_reference_boundary_price is not None:
        if continuation_evaluation_started_at:
            continuation_evaluation_reason = (
                f"Continuation evaluation began from active continuation boundary {governing_continuation_boundary}; "
                "waiting for continuation confirmation rules."
            )
        else:
            if governing_continuation_boundary is not None:
                continuation_evaluation_reason = (
                    "Continuation eligible from frozen rejection trade_state; waiting for a close through "
                    f"active continuation boundary {governing_continuation_boundary}."
                )
            else:
                continuation_evaluation_reason = (
                    f"Continuation eligible from frozen rejection trade_state; waiting for a close through "
                    f"frozen rejection boundary {continuation_reference_boundary_price}."
                )
    public_rejection_lane["active_liquidity_group"] = public_active_liquidity_group_projection(rejection_lane_group) if isinstance(rejection_lane_group, dict) else public_rejection_lane.get("active_liquidity_group")
    public_continuation_lane["active_liquidity_group"] = public_active_liquidity_group_projection(continuation_lane_group) if isinstance(continuation_lane_group, dict) else public_continuation_lane.get("active_liquidity_group")
    public_rejection_lane["step2_reason"] = translate_public_terminology(
        public_rejection_lane.get("step2_reason") or step_2_1a.get("state_transition_reason") or step_2_1a.get("reason")
    )
    public_rejection_lane["step4_reason"] = translate_public_terminology(
        public_rejection_lane.get("step4_reason")
        or public_rejection_lane.get("invalidation_reason")
        or ((seeded_step4_projection or {}).get("reason"))
        or result_reason(step4, "")
    )
    # Public status must project the same frozen rejection owner lifecycle that
    # runtime uses internally. These anchor fields are invariants, not
    # poll-time display values.
    public_rejection_lane, frozen_rejection_leg1_window_started_at = apply_frozen_rejection_lane_projection(
        snapshot,
        persisted_symbol_state,
        public_rejection_lane,
        step4_state,
    )
    if public_rejection_lane.get("step2_confirmed_at"):
        step2_time = public_rejection_lane.get("step2_confirmed_at") or step2_time
    if isinstance(rejection_lane, dict):
        rejection_lane["step2_confirmed_at"] = public_rejection_lane.get("step2_confirmed_at")
        rejection_lane["lane_status"] = public_rejection_lane.get("lane_status")
        rejection_lane["pathway_status"] = public_rejection_lane.get("pathway_status")
        rejection_lane["step4_status"] = public_rejection_lane.get("step4_status")
        rejection_lane["step4_reason"] = public_rejection_lane.get("step4_reason")
        rejection_lane["invalidation_reason"] = public_rejection_lane.get("invalidation_reason")
        rejection_lane["step2_step4_50_line"] = public_rejection_lane.get("step2_step4_50_line")
        rejection_lane["leg1_window_started_at"] = public_rejection_lane.get("leg1_window_started_at")
    public_continuation_lane["step2_reason"] = translate_public_terminology(
        public_continuation_lane.get("step2_reason")
        or continuation_public_step2_reason(
            continuation_evaluation_reason,
            controlling=public_continuation_lane.get("lane_status") == "controlling",
            invalidation_reason=public_continuation_lane.get("invalidation_reason"),
            step4_status=public_continuation_lane.get("step4_status"),
        )
    )
    public_continuation_lane["step4_reason"] = translate_public_terminology(
        public_continuation_lane.get("step4_reason")
        or continuation_public_step4_reason(
            result_reason(step4, ""),
            controlling=public_continuation_lane.get("lane_status") == "controlling",
            invalidation_reason=public_continuation_lane.get("invalidation_reason"),
            step4_status=public_continuation_lane.get("step4_status"),
        )
    )
    if public_continuation_lane.get("lane_status") in {"controlling", "invalidated"}:
        wait_reason = (
            public_continuation_lane.get("step4_reason")
            or public_continuation_lane.get("step2_reason")
            or wait_reason
        )
    for lane in (public_rejection_lane, public_continuation_lane):
        if lane.get("invalidation_reason"):
            lane["invalidation_source"] = lane.get("invalidation_source") or public_invalidation.get("source")
            lane["invalidation_source_step"] = lane.get("invalidation_source_step") or public_invalidation.get("source_step")
            lane["invalidation_source_candle_time"] = lane.get("invalidation_source_candle_time") or public_invalidation.get("source_candle_time")
    if public_continuation_lane.get("lane_status") == "controlling":
        selected_pathway = "continuation"
        projected_selected_pathway = "continuation"
        current_pathway_control = "continuation"
        if continuation_type in {"S/R", "R/S"}:
            current_controlling_mode = continuation_type
    if public_rejection_lane.get("step4_status") != "WAIT" and public_rejection_lane.get("leg2_candidate_candle_time") is None:
        public_rejection_lane["leg2_candidate_candle_time"] = step5_state.get("leg2_candidate_candle_time")
    if public_continuation_lane.get("step4_status") != "WAIT" and public_continuation_lane.get("leg2_candidate_candle_time") is None:
        public_continuation_lane["leg2_candidate_candle_time"] = step5_state.get("leg2_candidate_candle_time")

    def lane_selected_display(lane: dict[str, Any]) -> str:
        lane_name = str(lane.get("lane_name") or "").strip().lower()
        selected_lane = str(selected_pathway or projected_selected_pathway or trade_state.get("selected_pathway") or trade_state.get("lane_name") or "").strip().lower()
        if not lane_name or lane_name != selected_lane:
            return "N/A"
        return "YES"

    def lane_step2_owner_frozen_display(lane: dict[str, Any]) -> str:
        if str(lane.get("step2_status") or "").strip().upper() != "CONFIRMED":
            return "N/A"
        if str(lane.get("lane_name") or "").strip().lower() == "rejection" and step2_anchor_status == "UNKNOWN":
            return "UNKNOWN"
        return "YES" if lane.get("step2_confirmed_at") else "UNKNOWN"

    def lane_frozen_by_continuation_handoff_display(lane: dict[str, Any]) -> str:
        return "YES" if str(lane.get("lane_status") or "").strip().lower() == "frozen" else "N/A"

    public_rejection_lane["selected_lane_display"] = lane_selected_display(public_rejection_lane)
    public_continuation_lane["selected_lane_display"] = lane_selected_display(public_continuation_lane)
    public_rejection_lane["step2_owner_frozen_display"] = lane_step2_owner_frozen_display(public_rejection_lane)
    public_continuation_lane["step2_owner_frozen_display"] = lane_step2_owner_frozen_display(public_continuation_lane)
    public_rejection_lane["lane_frozen_by_continuation_handoff_display"] = lane_frozen_by_continuation_handoff_display(public_rejection_lane)
    public_continuation_lane["lane_frozen_by_continuation_handoff_display"] = lane_frozen_by_continuation_handoff_display(public_continuation_lane)
    rejection_side = public_boundary_model_projection({**rejection_side, **public_rejection_lane})
    continuation_side = public_boundary_model_projection(
        {**continuation_side, **public_continuation_lane},
        continuation_boundary=public_continuation_lane.get("continuation_boundary"),
    )
    market_state_snapshot = snapshot.get("market_state") if isinstance(snapshot.get("market_state"), dict) else build_market_state_snapshot(snapshot)
    market_state = {
        "active_liquidity_name": public_active_liquidity_display_name(snapshot, market_active_group, market_active_name, market_active_price),
        "selected_liquidity_name": market_selected_liquidity_name if market_selected_liquidity_name is not None else market_state_snapshot.get("selected_liquidity_name"),
        "active_liquidity_price": market_active_price,
        "active_liquidity_group": copy.deepcopy(market_active_group) if isinstance(market_active_group, dict) else None,
        "liquidity_group": (market_active_group or {}).get("name") if isinstance(market_active_group, dict) else market_state_snapshot.get("liquidity_group"),
        "close_boundary": market_close_boundary,
        "extreme_boundary": market_extreme_boundary,
        "wick_boundary_extreme": market_wick_boundary_extreme,
        "next_liquidity_above": market_state_snapshot.get("next_liquidity_above") or copy.deepcopy(liquidity.get("nearest_level_above")),
        "next_liquidity_below": market_state_snapshot.get("next_liquidity_below") or copy.deepcopy(liquidity.get("nearest_level_below")),
        "latest_price": market_state_snapshot.get("latest_price") if market_state_snapshot.get("latest_price") is not None else snapshot.get("latest_price"),
        "candle_time": market_state_snapshot.get("candle_time") or snapshot.get("latest_bar_time"),
    }
    if trade_state["active"]:
        active_name = trade_state["active_liquidity_name"] or active_name
        active_price = trade_state["active_liquidity_price"] if trade_state["active_liquidity_price"] is not None else active_price
        active_group = trade_state["active_liquidity_group"] if isinstance(trade_state["active_liquidity_group"], dict) else None
        selected_liquidity_name = trade_state["selected_liquidity_name"] or selected_liquidity_name
        close_boundary = trade_state["close_boundary"] if trade_state["close_boundary"] is not None else close_boundary
        extreme_boundary = trade_state["extreme_boundary"] if trade_state["extreme_boundary"] is not None else extreme_boundary
        wick_boundary_extreme = trade_state["wick_boundary_extreme"] if trade_state["wick_boundary_extreme"] is not None else wick_boundary_extreme
        if continuation_lane.get("lane_status") != "controlling":
            projected_selected_pathway = trade_state["selected_pathway"] or projected_selected_pathway
            selected_pathway = trade_state["selected_pathway"] or selected_pathway
            current_pathway_control = trade_state["selected_pathway"] or current_pathway_control
    public_continuation_boundary_value = public_continuation_boundary(
        continuation_active_boundary_price,
        continuation_probe_boundary_price(step25_state),
    )
    if public_continuation_lane.get("lane_status") not in {"eligible", "controlling", "invalidated"}:
        public_continuation_boundary_value = None
    public_boundary_source = {
        "active_liquidity_name": active_name,
        "active_liquidity_price": active_price,
        "active_liquidity_group": active_group,
        "wick_boundary_extreme": wick_boundary_extreme,
        "extreme_boundary": extreme_boundary,
        "step2_activated": step_2_1a.get("step_2_activated") is True,
        "rejection_probe_boundary": public_rejection_probe_boundary(step_2_1a),
        "continuation_probe_boundary_price": continuation_probe_boundary_price(step25_state),
    }
    public_boundary_projection = public_boundary_projection_values(
        public_boundary_source,
        continuation_boundary=public_continuation_boundary_value,
    )
    public_liquidity_level = {
        "name": public_boundary_projection.get("liquidity_level_name"),
        "price": public_boundary_projection.get("liquidity_level_price"),
    }
    public_rejection_boundary_value = public_boundary_projection.get("rejection_boundary")
    public_trade_state = public_boundary_model_projection(
        {
            **trade_state,
            "step2_activated": step_2_1a.get("step_2_activated") is True,
            "rejection_probe_boundary": public_rejection_probe_boundary(step_2_1a),
            "continuation_probe_boundary_price": continuation_probe_boundary_price(step25_state),
        },
        continuation_boundary=public_continuation_boundary_value if trade_state.get("selected_pathway") == "continuation" else None,
    )
    public_market_state = public_boundary_model_projection(
        {
            **market_state,
            "step2_activated": step_2_1a.get("step_2_activated") is True,
            "rejection_probe_boundary": public_rejection_probe_boundary(step_2_1a),
            "continuation_probe_boundary_price": continuation_probe_boundary_price(step25_state),
        },
        continuation_boundary=public_continuation_boundary_value,
    )
    if entry_status == "CONFIRM" and not canonical_atr_ready:
        entry_status = "WAIT_ATR_REQUIRED"
        wait_reason = "Canonical Rithmic Wilder RMA(14) ATR is not ready."
        last_decision = f"WAIT_ATR_REQUIRED: {wait_reason}"
    session_context_stale = bool(snapshot.get("session_context_stale"))
    session_lock_status = (
        "stale" if session_context_stale else "disabled" if session_context.get("disabled") is True else "locked" if session_context else "unlocked"
    )
    canonical_observation_minute = (
        current_canonical_atr_observation.get("candle_minute")
        if isinstance(current_canonical_atr_observation, dict)
        else None
    )
    canonical_state_rehydration_reason = None
    if not snapshot.get("latest_bar_time"):
        canonical_state_rehydration_reason = "canonical_completed_candle_unavailable"
    elif not isinstance(current_canonical_atr_observation, dict):
        canonical_state_rehydration_reason = "canonical_atr_observation_unavailable"
    elif canonical_observation_minute != snapshot.get("latest_bar_time"):
        canonical_state_rehydration_reason = "canonical_candle_atr_identity_mismatch"
    elif session_context_stale:
        canonical_state_rehydration_reason = "frozen_session_context_stale"
    elif not session_context:
        canonical_state_rehydration_reason = "frozen_session_context_unavailable"
    canonical_state_rehydrated = canonical_state_rehydration_reason is None
    status = {
        "symbol": str(snapshot.get("requested_symbol") or symbol).upper(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_lock_status": session_lock_status,
        "session_lock_error": session_context.get("error"),
        "session_authority": {
            "effective_session_date": snapshot.get("effective_session_date"),
            "rithmic_session_date": snapshot.get("rithmic_session_date"),
            "tradingview_session_date": snapshot.get("tradingview_session_date"),
            "session_authority_source": snapshot.get("session_authority_source"),
            "session_context_stale": session_context_stale,
        },
        "liquidity_lock": public_liquidity_lock_payload(snapshot, active_name, active_price, active_group),
        "candle_time": snapshot.get("latest_bar_time"),
        "candle_open": ohlc.get("open"),
        "candle_high": ohlc.get("high"),
        "candle_low": ohlc.get("low"),
        "candle_close": ohlc.get("close"),
        "canonical_state_rehydrated": canonical_state_rehydrated,
        "canonical_state_rehydration_reason": canonical_state_rehydration_reason,
        "canonical_state_rehydrated_at": datetime.now(timezone.utc).isoformat() if canonical_state_rehydrated else None,
        "canonical_atr": copy.deepcopy(selected_canonical_atr) if canonical_atr_ready else None,
        "canonical_atr_ready": canonical_atr_ready,
        "atr_1m_14": selected_canonical_atr.get("updated_raw_atr") if canonical_atr_ready else None,
        "atr_record_id": selected_canonical_atr.get("atr_record_id") if canonical_atr_ready else None,
        "atr_bar_id": selected_canonical_atr.get("bar_id") if canonical_atr_ready else None,
        "atr_formula": selected_canonical_atr.get("formula") if canonical_atr_ready else CANONICAL_ATR_FORMULA,
        "atr_formula_version": selected_canonical_atr.get("formula_version") if canonical_atr_ready else CANONICAL_ATR_FORMULA_VERSION,
        "atr_last_included_bar": selected_canonical_atr.get("last_included_bar") if canonical_atr_ready else None,
        **canonical_atr_status_projection(current_canonical_atr_observation),
        "current_step": current_step,
        "current_step_label": step_label,
        "step2_lifecycle_window_terminated": step2_window_terminated,
        "frozen_active_groups": frozen_active_groups,
        "frozen_group_found": frozen_group_found,
        "frozen_group_display_name": frozen_group_display_name,
        "canonical_group_display_name": canonical_group_name_debug,
        "selected_liquidity_name": selected_liquidity_name,
        "trade_state": public_trade_state,
        "market_state": public_market_state,
        "current_step_status": current_step_status,
        "current_step_confirmed_at": current_step_time,
        "step2_candle_count": step2_count,
        "step2_owner_seeded_at": step2_owner_seeded_time,
        "step2_activated_at": step_2_1a.get("step2_activated_at") or step2_owner_state.get("activated_at"),
        "step2_confirmed_at": step2_time,
        "step2_anchor_status": step2_anchor_status,
        "step2_anchor_reason": step2_anchor_reason,
        "step2_invalidated_at": step2_invalidated_time,
        "step2_owner_name": step2_owner_display,
        "step2_direction": snapshot.get("frozen_step2_direction") or public_setup_direction or (
            step2_owner_state.get("setup_direction")
            or step25_state.get("setup_direction")
        ),
        "step2_event": blocked_preopen_status or str(step_2_1a.get("audit_step2_event") or latest_event_name(step_2_1a.get("events")) or ""),
        "step2_reason": blocked_preopen_reason or str(step_2_1a.get("state_transition_reason") or step_2_1a.get("reason") or ""),
        "selected_pathway": projected_selected_pathway if projected_selected_pathway is not None else selected_pathway,
        "active_liquidity_name": trade_state["active_liquidity_name"] if trade_state["active"] else public_active_liquidity_display_name(snapshot, active_group, active_name, active_price),
        "active_liquidity_price": active_price,
        "active_liquidity_group": public_active_liquidity_group_projection(active_group),
        "liquidity_level_name": public_liquidity_level["name"],
        "liquidity_level_price": public_liquidity_level["price"],
        "rejection_boundary": public_rejection_boundary_value,
        "continuation_boundary": public_continuation_boundary_value,
        "wick_boundary_extreme": wick_boundary_extreme,
        "frozen_tv_level": active_price,
        "pre_open_observed_extreme": observed_extreme,
        "liquidity_price": active_price,
        "liquidity_group": (active_group or {}).get("name") if isinstance(active_group, dict) else None,
        "leg_anchor_liquidity": liquidity_leg_telemetry["leg_anchor_liquidity"],
        "leg_anchor_price": liquidity_leg_telemetry["leg_anchor_price"],
        "next_active_liquidity": liquidity_leg_telemetry["next_active_liquidity"],
        "next_active_liquidity_price": liquidity_leg_telemetry["next_active_liquidity_price"],
        "daily_atr14": liquidity_leg_telemetry["daily_atr14"],
        "distance_points": liquidity_leg_telemetry["distance_points"],
        "liquidity_leg_atr_distance_pct": liquidity_leg_telemetry["liquidity_leg_atr_distance_pct"],
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
        "control_state": "OBSERVATION_ONLY" if observation_only else current_pathway_control,
        "conflict_state": "NONE_PREOPEN" if observation_only else None,
        "step2_status": public_step_status(
            blocked_preopen_status or ((public_lane_projection(projected_lane) if isinstance(projected_lane, dict) else {}).get("step2_status")) or current_step_status,
            step_name="Step 2",
        ),
        "step3_status": blocked_preopen_status or ((snapshot.get("step3") or {}).get("status")),
        "step4_status": public_step_status(
            blocked_preopen_status or ((public_lane_projection(projected_lane) if isinstance(projected_lane, dict) else {}).get("step4_status")) or ((seeded_step4_projection or {}).get("status")) or ((snapshot.get("step4") or {}).get("status")),
            step_name="Step 4",
        ),
        "step4_event": blocked_preopen_status or step4_event,
        "step4_reason": translate_public_terminology(
            blocked_preopen_reason
            or ((public_lane_projection(projected_lane) if isinstance(projected_lane, dict) else {}).get("step4_reason"))
            or ((projected_lane or {}).get("invalidation_reason"))
            or ((seeded_step4_projection or {}).get("reason"))
            or result_reason(step4, "")
        ),
        "step4_confirmed_at": step4_confirmed_at,
        "step4_window_count": step4_window_count,
        "step4_candle_a_time": step4_candle_a_time,
        "step4_candle_b_time": step4_candle_b_time,
        "step4_rejection_completed_at": step4_confirmed_at,
        "step4_invalidated_at": step4_invalidated_time,
        "step4_owner_name": step4_owner_display,
        "step4_direction": public_setup_direction or step4_state.get("setup_direction"),
        "continuation_eligible": continuation_eligible,
        "continuation_eligible_at": continuation_eligible_at,
        "continuation_evaluation_started_at": continuation_evaluation_started_at,
        "continuation_evaluation_reason": translate_public_terminology(
            public_continuation_lane.get("step2_reason") or continuation_evaluation_reason
        ),
        "leg2_sweep_extreme": step4_state.get("leg2_sweep_extreme") if leg1_published else None,
        "step5_close_boundary": step4_state.get("step5_close_boundary") if leg1_published else None,
        "step5_status": blocked_preopen_status or ((snapshot.get("step5") or {}).get("status")),
        "step6_status": blocked_preopen_status or ((snapshot.get("step6") or {}).get("status")),
        "rejection_pathway_status": rejection_side["pathway_status"],
        "continuation_pathway_status": continuation_side["pathway_status"],
        "rejection_side": rejection_side,
        "continuation_side": continuation_side,
        "rejection_lane": public_rejection_lane,
        "continuation_lane": public_continuation_lane,
        "leg1_status": leg1_status,
        "leg1_state": leg1_status,
        "leg1_confirmed_at": leg1_time,
        "step4_participation_reference_liquidity": participation_lines["reference_liquidity"],
        "step4_participation_active_liquidity": participation_lines["active_liquidity"],
        "step4_participation_active_side": participation_lines["active_side"],
        "step2_step4_50_line": None if continuation_selected else (((projected_lane or {}).get("step2_step4_50_line")) if isinstance(projected_lane, dict) else participation_lines["line_50"]),
        "step4_step5_75_line": None if continuation_selected else (((projected_lane or {}).get("step4_step5_75_line")) if isinstance(projected_lane, dict) else participation_lines["line_75"]),
        "step4_participation_50_line": None if continuation_selected else participation_lines["line_50"],
        "step4_participation_75_line": None if continuation_selected else participation_lines["line_75"],
        "step4_participation_lines_visible": False if continuation_selected else participation_lines["visible"],
        "leg2_status": leg2_status,
        "leg2_state": leg2_status,
        "leg2_confirmed_at": leg2_time,
        "leg2_reference_price": (step5_state.get("step5_close_boundary") or step5_state.get("active_leg1_reference") or step5_state.get("leg1_reference")) if leg2_published else None,
        "entry_status": entry_status,
        "entry_status_confirmed_at": entry_time,
        "entry_type_number": step6_state.get("entry_type_number"),
        "entry_type_name": step6_state.get("entry_type_name"),
        "entry_model": step6_state.get("entry_model"),
        "entry_model_reason": step6_state.get("entry_model_reason"),
        "wait_reason": translate_public_terminology(wait_reason),
        "invalidation_reason": ((projected_lane or {}).get("invalidation_reason")) if isinstance(projected_lane, dict) else invalidation_reason,
        "internal_invalidation_reason": raw_invalidation_reason,
        "last_decision": translate_public_terminology(last_decision),
        "publication_gate_debug": snapshot.get("publication_gate_debug") if isinstance(snapshot.get("publication_gate_debug"), list) else [],
        "leg1_state_locked": step4_state.get("leg1_state_locked"),
        "leg1_locked": step4_state.get("leg1_state_locked"),
        "leg1_completed_at": step4_confirmed_at if leg1_published else None,
        "leg1_reference_price": (step4_state.get("step5_close_boundary") or step4_state.get("leg1_reference_price") or step4_state.get("leg1_reference")) if leg1_published else None,
        "leg1_reference_candle_time": (step4_state.get("step4_confirmed_at") or step4_state.get("leg1_reference_candle_time")) if leg1_published else None,
        "leg1_direction": (step4_state.get("leg1_direction") or step4_state.get("setup_direction")) if leg1_published else None,
        "last_evaluated_candle_time": (step4_state.get("last_evaluated_candle_time") if leg1_published else None) or (step5_state.get("last_evaluated_candle_time") if leg2_published else None),
        "invalidated_at": public_invalidation["invalidated_at"],
        "invalidated_liquidity": public_invalidation["invalidated_liquidity"],
        "invalidation_source_candle_time": public_invalidation["source_candle_time"],
        "invalidation_source": public_invalidation["source"],
        "invalidation_source_step": public_invalidation["source_step"],
        "consumed_liquidity_levels": step4_state.get("consumed_liquidity_levels") or step5_state.get("consumed_liquidity_levels") or [],
        "state_transition_reason": step4_state.get("state_transition_reason") or step5_state.get("state_transition_reason"),
        "leg1_formed_at_percent": None if continuation_selected else (step4_state.get("leg1_formed_at_percent") if leg1_published else None),
        "leg1_50_percent_rule_passed": None if continuation_selected else (step4_state.get("leg1_50_percent_rule_passed") if leg1_published else None),
        "step4_proximity_distance": step4_state.get("proximity_distance") if leg1_published else None,
        "step4_proximity_daily_atr": step4_state.get("proximity_daily_atr") if leg1_published else None,
        "step4_proximity_atr_threshold": step4_state.get("proximity_atr_threshold") if leg1_published else None,
        "step4_proximity_atr_threshold_percent": step4_state.get("proximity_atr_threshold_percent") if leg1_published else None,
        "fifty_percent_rule_phase": None if continuation_selected else (step4_state.get("fifty_percent_rule_phase") if leg1_published else None),
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
    if isinstance(frozen_rejection_leg1_window_started_at, str) and frozen_rejection_leg1_window_started_at.strip():
        status["leg1_window_started_at"] = frozen_rejection_leg1_window_started_at
    if is_seeded_step4_anchor_reason(status.get("step4_reason")):
        frozen_step4_reason = seeded_step4_reason_from_anchor(
            frozen_rejection_leg1_window_started_at or step2_time
        )
        if frozen_step4_reason:
            status["step4_reason"] = frozen_step4_reason
    return status


@entry_state_transaction
def persist_state(snapshot: dict[str, Any]) -> None:
    """Persist the latest one-shot snapshot state."""
    require_authoritative_mutation("persist_state")
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
    previous_event_log = list(previous_symbol_state.get("event_log") or []) if isinstance(previous_symbol_state.get("event_log"), list) else []
    invariant_events = [dict(item) for item in (snapshot.get("lifecycle_invariant_events") or []) if isinstance(item, dict)]
    observation_session_date = snapshot.get("observation_reset_session_date") or previous_symbol_state.get("observation_reset_session_date")
    snapshot_observed_extreme = snapshot.get("pre_open_observed_extreme") if isinstance(snapshot.get("pre_open_observed_extreme"), dict) else None
    if previous_symbol_state.get("observation_reset_session_date") == observation_session_date:
        persisted_observed_extreme = merged_pre_open_observed_extreme(
            previous_symbol_state.get("pre_open_observed_extreme") if isinstance(previous_symbol_state.get("pre_open_observed_extreme"), dict) else None,
            snapshot_observed_extreme,
        )
    else:
        persisted_observed_extreme = snapshot_observed_extreme
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
        "rejection_lane": snapshot.get("rejection_lane"),
        "continuation_lane": snapshot.get("continuation_lane"),
        "gateway": snapshot.get("gateway"),
        "tv_context": snapshot.get("tv_context"),
        "live_tv_context": snapshot.get("live_tv_context") or previous_symbol_state.get("live_tv_context"),
        "tv_context_status": snapshot.get("tv_context_status"),
        "session_liquidity_context": snapshot.get("session_liquidity_context") or previous_symbol_state.get("session_liquidity_context"),
        "trade_state": snapshot.get("trade_state") or previous_symbol_state.get("trade_state"),
        "market_state": snapshot.get("market_state") or previous_symbol_state.get("market_state"),
        "pre_open_observed_extreme": copy.deepcopy(persisted_observed_extreme),
        "observation_reset_session_date": observation_session_date,
        "observation_reset_bar_time": snapshot.get("observation_reset_bar_time") or previous_symbol_state.get("observation_reset_bar_time"),
        "observation_reset_at": snapshot.get("observation_reset_at") or previous_symbol_state.get("observation_reset_at"),
        "event_log": previous_event_log + invariant_events,
    }
    if symbol_key:
        state_by_symbol[symbol_key] = symbol_state

    state = dict(symbol_state)
    state["state_by_symbol"] = state_by_symbol
    state["last_interacted_liquidity_by_symbol"] = last_by_symbol
    _write_json(STATE_PATH, state)


@entry_state_transaction
def persist_confirmed_rejection_anchor_from_authoritative_snapshot(
    snapshot: dict[str, Any],
    status: dict[str, Any],
) -> bool:
    """Commit confirmed rejection fields inside the authoritative event transaction."""
    require_authoritative_mutation("persist_confirmed_rejection_anchor_from_authoritative_snapshot")
    if not isinstance(snapshot, dict) or not isinstance(status, dict):
        return False
    step2 = snapshot.get("step_2_1a") if isinstance(snapshot.get("step_2_1a"), dict) else {}
    if step2.get("step_2_activated") is not True:
        return False

    public_rejection_lane = status.get("rejection_lane") if isinstance(status.get("rejection_lane"), dict) else {}
    public_step2_status = str(public_rejection_lane.get("step2_status") or status.get("step2_status") or "").strip().upper()
    public_confirmed_at = (
        public_rejection_lane.get("step2_confirmed_at")
        or status.get("step2_confirmed_at")
        or snapshot.get("frozen_step2_anchor_time")
        or step2_confirmed_anchor_time(step2)
    )
    if not isinstance(public_confirmed_at, str) or not public_confirmed_at.strip():
        return False
    public_terminal = (
        str(public_rejection_lane.get("step4_status") or "").strip().upper() == "TERMINATED"
        or bool(public_rejection_lane.get("invalidation_reason"))
        or (((snapshot.get("step4") or {}).get("state") or {}).get("leg1_window_invalidated") is True)
    )
    if public_step2_status != "CONFIRMED" and not public_terminal:
        return False

    symbol_key = str(snapshot.get("normalized_symbol") or root_symbol(str(snapshot.get("symbol") or ""))).upper()
    if not symbol_key:
        return False

    previous_state = load_entry_state()
    previous_symbol_state = symbol_scoped_persisted_state(previous_state, symbol_key)
    previous_step2 = previous_symbol_state.get("step_2_1a") if isinstance(previous_symbol_state.get("step_2_1a"), dict) else {}
    previous_lane = previous_symbol_state.get("rejection_lane") if isinstance(previous_symbol_state.get("rejection_lane"), dict) else {}
    previous_step4 = previous_symbol_state.get("step4") if isinstance(previous_symbol_state.get("step4"), dict) else {}
    previous_step4_state = previous_step4.get("state") if isinstance(previous_step4.get("state"), dict) else {}
    previous_confirmed_at = previous_lane.get("step2_confirmed_at") or step2_confirmed_anchor_time(previous_step2)
    live_step4 = snapshot.get("step4") if isinstance(snapshot.get("step4"), dict) else {}
    live_step4_state = live_step4.get("state") if isinstance(live_step4.get("state"), dict) else {}
    live_rejection_lane = snapshot.get("rejection_lane") if isinstance(snapshot.get("rejection_lane"), dict) else {}
    same_anchor = isinstance(previous_confirmed_at, str) and previous_confirmed_at == public_confirmed_at
    anchor_newer_or_missing = not isinstance(previous_confirmed_at, str) or previous_confirmed_at < public_confirmed_at
    previous_terminal = (
        previous_step4_state.get("leg1_window_invalidated") is True
        or str(previous_lane.get("step4_status") or "").strip().upper() == "TERMINATED"
        or bool(previous_lane.get("invalidation_reason"))
    )
    live_terminal = (
        live_step4_state.get("leg1_window_invalidated") is True
        or str(live_rejection_lane.get("step4_status") or "").strip().upper() == "TERMINATED"
        or bool(live_rejection_lane.get("invalidation_reason"))
    )
    previous_step4_completed = bool(
        previous_step4_state.get("leg1_state_locked") is True
        and str(previous_step4_state.get("leg1_status") or "").strip().upper() == "COMPLETE"
        and (previous_step4_state.get("step4_confirmed_at") or previous_step4_state.get("leg1_completed_at"))
    )
    live_step4_lane = lifecycle_lane_contract(live_step4_state.get("lane_id")).get("lane_name")
    live_step4_pathway = step4_anchor_selected_pathway(live_step4)
    live_rejection_step4_completed = bool(
        not live_terminal
        and live_step4_lane != "continuation"
        and live_step4_pathway != "continuation"
        and live_step4_state.get("leg1_state_locked") is True
        and str(live_step4_state.get("leg1_status") or "").strip().upper() == "COMPLETE"
        and (live_step4_state.get("step4_confirmed_at") or live_step4_state.get("leg1_completed_at"))
        and str(live_rejection_lane.get("step4_status") or "").strip().upper() in {"READY", "CONFIRMED"}
    )
    first_completed_rejection_snapshot = bool(
        live_rejection_step4_completed and (not same_anchor or not previous_step4_completed)
    )
    if same_anchor and previous_terminal and not live_terminal:
        return False
    lifecycle_refresh_needed = False
    if same_anchor:
        if (
            live_step4_state.get("leg1_window_started_at")
            and (
                previous_step4_state.get("leg1_window_started_at") != live_step4_state.get("leg1_window_started_at")
                or previous_step4_state.get("leg1_window_candle_index") != live_step4_state.get("leg1_window_candle_index")
                or previous_step4_state.get("leg1_window_remaining") != live_step4_state.get("leg1_window_remaining")
                or previous_step4_state.get("leg1_window_invalidated") != live_step4_state.get("leg1_window_invalidated")
                or previous_step4_state.get("leg1_window_invalidation_reason") != live_step4_state.get("leg1_window_invalidation_reason")
                or previous_step4_state.get("step2_step4_50_line") != live_step4_state.get("step2_step4_50_line")
            )
        ):
            lifecycle_refresh_needed = True
        if (
            isinstance(live_rejection_lane, dict)
            and (
                previous_lane.get("step4_status") != live_rejection_lane.get("step4_status")
                or previous_lane.get("invalidation_reason") != live_rejection_lane.get("invalidation_reason")
                or previous_lane.get("step2_step4_50_line") != live_rejection_lane.get("step2_step4_50_line")
            )
        ):
            lifecycle_refresh_needed = True
    if first_completed_rejection_snapshot:
        lifecycle_refresh_needed = True
    if not anchor_newer_or_missing and not lifecycle_refresh_needed:
        return False

    state_by_symbol = dict(previous_state.get("state_by_symbol") or {}) if isinstance(previous_state.get("state_by_symbol"), dict) else {}
    last_by_symbol = dict(previous_state.get("last_interacted_liquidity_by_symbol") or {}) if isinstance(previous_state.get("last_interacted_liquidity_by_symbol"), dict) else {}
    symbol_state = dict(previous_symbol_state) if isinstance(previous_symbol_state, dict) else {}

    checkpoint_step2 = dict(previous_step2)
    for field in (
        "step_2_activated",
        "candle_a",
        "active_level",
        "level_price",
        "side",
        "tick_size",
        "expiration_candles",
        "step2_owner_seeded_at",
        "step2_activated_at",
        "step2_activation_candle_index",
        "active_liquidity_group",
        "last_interacted_liquidity",
        "step2_locked_owner",
        "last_evaluated_bar_time",
        "candle_index",
        "next_candle_index",
        "reason",
        "available",
        "continuation_controlling_structure_high",
        "continuation_controlling_structure_low",
        "continuation_controlling_structure_start_time",
        "continuation_controlling_structure_end_time",
        "continuation_controlling_structure_source_step",
    ):
        if field in step2:
            checkpoint_step2[field] = copy.deepcopy(step2.get(field))
    checkpoint_step2["step_2_activated"] = True
    checkpoint_step2["step2_invalidated_at"] = None

    checkpoint_step4 = copy.deepcopy(previous_step4)
    checkpoint_step4_state = dict(checkpoint_step4.get("state") or {}) if isinstance(checkpoint_step4.get("state"), dict) else {}
    if first_completed_rejection_snapshot:
        # Persist the complete first Leg 1 identity atomically.  Later status
        # evaluations load this object and apply_confirmed_lifecycle_invariants
        # freezes every completed field before a new candle can recompute it.
        checkpoint_step4 = copy.deepcopy(live_step4)
        checkpoint_step4_state = checkpoint_step4.get("state") if isinstance(checkpoint_step4.get("state"), dict) else {}
    elif (
        live_step4_state.get("leg1_window_started_at")
        and live_step4_state.get("leg1_state_locked") is not True
        and str(live_step4_state.get("leg1_status") or "").upper() != "COMPLETE"
    ):
        for field in (
            "leg1_window_active",
            "leg1_window_started_at",
            "leg1_window_candle_index",
            "leg1_window_remaining",
            "leg1_window_expires_at",
            "leg1_window_invalidated",
            "leg1_window_invalidation_reason",
            "leg1_status",
            "leg1_state_locked",
            "active_liquidity",
            "initial_candle_a",
            "candle_a",
            "setup_direction",
            "controlling_mode",
            "current_pathway_control",
            "current_controlling_mode",
            "current_continuation_type",
            "lane_id",
            "step2_step4_reference_liquidity",
            "next_break_side_liquidity",
            "step2_step4_50_line",
            "step2_step4_50_line_touched_at",
            "step4_step5_75_line",
            "invalidated_at",
            "invalidation_source",
            "invalidation_source_step",
            "invalidation_source_candle_time",
        ):
            if field in live_step4_state:
                checkpoint_step4_state[field] = copy.deepcopy(live_step4_state.get(field))
        checkpoint_step4["step"] = "Step 4"
        checkpoint_step4["status"] = live_step4.get("status") or checkpoint_step4.get("status") or "WAIT"
        checkpoint_step4["next_step"] = live_step4.get("next_step") or checkpoint_step4.get("next_step") or "Step 4"
        checkpoint_step4["reason"] = live_step4.get("reason")
        checkpoint_step4["state"] = checkpoint_step4_state

    checkpoint_rejection_lane = copy.deepcopy(previous_lane)
    if first_completed_rejection_snapshot:
        checkpoint_rejection_lane = copy.deepcopy(live_rejection_lane)
    elif isinstance(live_rejection_lane, dict):
        for field in (
            "lane_name",
            "lane_status",
            "pathway_status",
            "active_liquidity_name",
            "active_liquidity_group",
            "liquidity_group",
            "active_liquidity_price",
            "close_boundary",
            "extreme_boundary",
            "wick_boundary_extreme",
            "step2_candle_count",
            "step4_candle_count",
            "step2_status",
            "step2_confirmed_at",
            "step4_status",
            "step2_step4_50_line",
            "step2_reason",
            "step4_reason",
            "invalidation_reason",
        ):
            if field in live_rejection_lane:
                checkpoint_rejection_lane[field] = copy.deepcopy(live_rejection_lane.get(field))

    last_interacted = checkpoint_step2.get("last_interacted_liquidity")
    if symbol_key and isinstance(last_interacted, dict) and last_interacted.get("name"):
        last_by_symbol[symbol_key] = copy.deepcopy(last_interacted)

    symbol_state.update(
        {
            "symbol": snapshot.get("symbol"),
            "normalized_symbol": snapshot.get("normalized_symbol"),
            "requested_symbol": snapshot.get("requested_symbol"),
            "latest_price": snapshot.get("latest_price"),
            "latest_bar_time": snapshot.get("latest_bar_time"),
            "step_2_1a": checkpoint_step2,
            "step2_locked_owner": copy.deepcopy(checkpoint_step2.get("step2_locked_owner")),
            "last_interacted_liquidity": copy.deepcopy(last_interacted),
            "step_2_1a_last_evaluated_bar_time": checkpoint_step2.get("last_evaluated_bar_time"),
            "step_2_1a_candle_index": checkpoint_step2.get("next_candle_index", previous_symbol_state.get("step_2_1a_candle_index", 0)),
            "step4": checkpoint_step4,
            "rejection_lane": checkpoint_rejection_lane,
        }
    )
    state_by_symbol[symbol_key] = symbol_state

    checkpoint_state = dict(previous_state)
    checkpoint_state.update(symbol_state)
    checkpoint_state["state_by_symbol"] = state_by_symbol
    checkpoint_state["last_interacted_liquidity_by_symbol"] = last_by_symbol
    _write_json(STATE_PATH, checkpoint_state)
    return True


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
    active_group = step_2_1a.get("active_liquidity_group") if isinstance(step_2_1a.get("active_liquidity_group"), dict) else None
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
            f"step2_candle_count: {step2_candle_count(snapshot, step_2_1a)}",
            f"step_2_1a_blocked: {step_2_1a.get('blocked')}",
            f"close_boundary: {(active_group or {}).get('close_boundary')}",
            f"extreme_boundary: {(active_group or {}).get('extreme_boundary')}",
            f"wick_boundary_extreme: {(active_group or {}).get('wick_boundary_extreme')}",
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
    """Refresh read-only EntryAgent diagnostics until interrupted."""
    try:
        while True:
            clear_screen()
            print(format_snapshot(run_once(symbol, persist=False)))
            print()
            print("Press Ctrl+C to exit.")
            time.sleep(refresh_seconds)
    except KeyboardInterrupt:
        print("\nwatch stopped")


def main() -> int:
    args = parse_args()
    if args.once:
        print(format_snapshot(run_once(args.symbol, persist=False)))
        return 0

    if args.watch:
        run_watch(args.symbol)
        return 0

    raise SystemExit("Use --once or --watch.")


if __name__ == "__main__":
    raise SystemExit(main())
