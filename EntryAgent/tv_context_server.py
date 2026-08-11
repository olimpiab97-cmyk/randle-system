"""TradingView context feed server for EntryAgent.

PowerShell test example:
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:7002/webhook/tv-context `
  -ContentType 'application/json' `
  -Body '{"symbol":"CME_MINI:NQ1!","PMH":27390,"PML":27380,"LH":null,"LL":null,"ONH":27395,"ONL":27375,"YH":null,"YL":null,"time_zone":"America/New_York","pm_atr_pct":0.42,"daily_range_pct":0.88}'
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import math
import os
import shutil
import sys
import tempfile
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, request
from flask_cors import CORS

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from data_paths import data_path, local_or_shared_path
from blueprint_rules import side_for_level_price
from liquidity_stack_validation import (
    normalize_stack_group_label,
    stack_group_side,
    stack_reference_price_from_context,
    stack_threshold_from_context,
    validate_liquidity_stack_structure,
)
from entry_agent import (
    ENTRY_AGENT_RUNTIME_DIR,
    ENTRY_STATE_LOCK,
    STATE_PATH as ENTRY_AGENT_STATE_PATH,
    _read_json,
    _write_json,
    build_entry_status,
    build_session_locked_tv_context,
    current_step_label,
    entry_state_transaction,
    frozen_session_contract_payload,
    run_once,
)

ENTRY_REASONING_DIR = data_path()
LEVELS_PATH = BASE_DIR / "levels.json"
LEVELS_BY_SYMBOL_PATH = BASE_DIR / "levels_by_symbol.json"
TV_CONTEXT_PATH = local_or_shared_path(BASE_DIR, "tv_context.json", shared_prefix="entry_agent")
TV_CONTEXT_BY_SYMBOL_PATH = local_or_shared_path(BASE_DIR, "tv_context_by_symbol.json", shared_prefix="entry_agent")
TV_CONTEXT_EVENTS_PATH = local_or_shared_path(BASE_DIR, "tv_context_events.jsonl", shared_prefix="entry_agent")
ENTRY_LOG_DIR = BASE_DIR / "logs"
ENTRY_DECISIONS_LOG_PATH = ENTRY_LOG_DIR / "entry_decisions.jsonl"
OPERATOR_AUDIT_LOG_PATH = ENTRY_LOG_DIR / "operator_actions.jsonl"

LEVEL_FIELDS = ("PMH", "PML", "LH", "LL", "ONH", "ONL", "YH", "YL")
NUMERIC_FIELDS = LEVEL_FIELDS + ("pm_atr_pct", "daily_range_pct")
CONTEXT_FIELDS = NUMERIC_FIELDS + ("symbol", "time_zone")
LEVELS_SCHEMA_KEYS = ("PMH", "PML", "LH", "LL", "ONH", "ONL", "YH", "YL", "RTHH", "RTHL")

SYMBOL_ALIASES = {
    "NQ": "NQ",
    "NQM6": "NQ",
    "NQ1!": "NQ",
    "CME_MINI:NQ1!": "NQ",
    "YM": "YM",
    "YMM6": "YM",
    "YM1!": "YM",
    "CBOT_MINI:YM1!": "YM",
}
RANDLE_TAYLOR_MAP_SOURCE = "randle_taylor_map"
CANONICAL_LIQUIDITY_SOURCE = "tradingview_level_helper"
CANONICAL_LIQUIDITY_VERSION = "v14_canonical_liquidity_sender"
CANONICAL_LIQUIDITY_CONTEXT_MODE = "locked_levels_session_snapshot"
CANONICAL_LIQUIDITY_TIMEZONE = "America/Los_Angeles"
CANONICAL_LIQUIDITY_TIMEFRAME = "1"
CANONICAL_LEVEL_STATUSES = {"ACTIVE", "INACTIVE", "REACTIVATED"}
ISOLATED_LEGACY_LIQUIDITY_VERSIONS = {
    None,
    "",
    "v14_overlapping_stack_smoke",
    "preopen",
    "locked-1",
    "later",
}
INTERNAL_RELAY_TOKEN_ENV = "TV_CONTEXT_INTERNAL_RELAY_TOKEN"
INTERNAL_RELAY_HEADER = "X-Randle-Relay-Token"
CANONICAL_LOCK_RECONSTRUCTION_REASON = "legacy_lock_missing_canonical_frozen_reference"
CANONICAL_LOCK_RECONSTRUCTION_MAX_AGE_SECONDS = 180
TAYLOR_CONTEXT_KEYS = ("t_plus", "yesterday_close", "t_minus")
LOCAL_MARKET_TIMEZONE = ZoneInfo("America/Los_Angeles")
SESSION_LIQUIDITY_LOCK_HOUR = 6
SESSION_LIQUIDITY_LOCK_MINUTE = 15
EXECUTOR_SYNC_SNAPSHOT_URL = "http://127.0.0.1:6001/sync_snapshot"
EXECUTOR_ORDERS_URL = "http://127.0.0.1:6001/orders"
EXECUTOR_ACCOUNT_SNAPSHOT_URL = "http://127.0.0.1:6001/account_snapshot"

app = Flask(__name__)
CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", INTERNAL_RELAY_HEADER],
    send_wildcard=True,
)
LATEST_TV_CONTEXT_BY_SYMBOL: dict[str, dict[str, Any]] = {}
TV_LADDER_VALIDATION_BY_SYMBOL: dict[str, dict[str, Any]] = {}
TV_LADDER_VALIDATION_LABEL = "TEST / UNVERIFIED OVERLAPPING STACK PAYLOAD"
ENTRY_DECISION_LOG_THROTTLE_SECONDS = 5.0
ENTRY_DECISION_LAST_LOGGED: dict[str, dict[str, Any]] = {}
ENTRY_REASONING_LAST_LOGGED: dict[str, dict[str, Any]] = {}


@app.after_request
def add_entry_status_cors_headers(response: Any) -> Any:
    """Keep Entry Agent read-only status fetchable from Command Center."""
    if request.path in {"/entry/status", "/entry/executor_status", "/debug/tv-ladder-validation"}:
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
    return response


def fetch_local_json(url: str, timeout: float = 1.0) -> dict[str, Any]:
    """Fetch a localhost JSON endpoint for read-only UI visibility bridges."""
    try:
        with urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def summarize_active_execution_state(sync_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Summarize only active/open execution state from executor sync snapshot."""
    symbols = sync_snapshot.get("symbols") if isinstance(sync_snapshot.get("symbols"), dict) else {}
    active_symbols = []
    active_positions = []
    active_orders = []

    for symbol, symbol_snapshot in symbols.items():
        if not isinstance(symbol_snapshot, dict):
            continue
        position_qty = _to_float(symbol_snapshot.get("position_qty")) or 0.0
        working_orders = symbol_snapshot.get("working_orders") if isinstance(symbol_snapshot.get("working_orders"), list) else []
        has_open_state = abs(position_qty) > 0 or bool(working_orders)
        if not has_open_state:
            continue
        active_symbols.append(str(symbol))
        if abs(position_qty) > 0:
            active_positions.append({
                "symbol": str(symbol),
                "position_qty": position_qty,
                "avg_entry_price": _to_float(symbol_snapshot.get("avg_entry_price")),
                "last_price": _to_float(symbol_snapshot.get("last_price")),
                "last_price_at": symbol_snapshot.get("last_price_at"),
            })
        for order in working_orders:
            if not isinstance(order, dict):
                continue
            active_orders.append({
                "symbol": str(symbol),
                "order_id": order.get("order_id"),
                "trade_id": order.get("trade_id"),
                "type": order.get("type"),
                "qty": order.get("qty"),
                "stop_price": order.get("stop_price"),
                "limit_price": order.get("limit_price"),
                "status": order.get("status"),
            })

    return {
        "has_open_execution_state": bool(active_symbols),
        "message": None if active_symbols else "No Active Execution",
        "active_symbol_count": len(active_symbols),
        "active_symbols": active_symbols,
        "active_position_count": len(active_positions),
        "active_order_count": len(active_orders),
        "active_positions": active_positions,
        "active_orders": active_orders,
    }


def utc_timestamp() -> str:
    """Return an ISO UTC timestamp for persisted context."""
    return datetime.now(timezone.utc).isoformat()


def normalize_symbol(symbol: Any) -> str | None:
    """Normalize supported TradingView or contract symbols to EntryAgent roots."""
    if symbol is None:
        return None

    symbol_text = str(symbol).strip().upper()
    if symbol_text in SYMBOL_ALIASES:
        return SYMBOL_ALIASES[symbol_text]

    if ":" in symbol_text:
        symbol_text = symbol_text.split(":", 1)[1]

    if symbol_text.startswith("NQ"):
        return "NQ"
    if symbol_text.startswith("YM"):
        return "YM"
    return None


def parse_optional_number(value: Any, field_name: str) -> tuple[float | None, str | None]:
    """Parse a nullable numeric field."""
    if value is None or value == "":
        return None, None
    try:
        return float(value), None
    except (TypeError, ValueError):
        return None, f"{field_name} must be numeric or null"


def safe_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON via same-directory temp file, then atomically replace."""
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temp_path, path)


def upsert_symbol_json(path: Path, symbol: str, payload: dict[str, Any]) -> None:
    """Persist the latest payload per root symbol while keeping legacy flat files."""
    store: dict[str, Any] = {"symbols": {}}
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as file:
                existing = json.load(file)
            if isinstance(existing, dict) and isinstance(existing.get("symbols"), dict):
                store = existing
        except (json.JSONDecodeError, OSError):
            store = {"symbols": {}}
    store["symbols"][symbol] = payload
    safe_write_json(path, store)


def timestamped_backup(path: Path, stamp: str | None = None) -> str | None:
    """Create a timestamped sibling backup before operator overrides."""
    if not path.exists():
        return None
    backup_stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = path.with_name(f"{path.name}.bak_{backup_stamp}")
    shutil.copy2(path, backup_path)
    return str(backup_path)


def _target_symbol_state(state: dict[str, Any], symbol: str) -> dict[str, Any] | None:
    by_symbol = state.get("state_by_symbol")
    if isinstance(by_symbol, dict) and isinstance(by_symbol.get(symbol), dict):
        return by_symbol[symbol]
    if str(state.get("normalized_symbol") or "").upper() == symbol:
        return state
    return None


def _stack_labels(levels: dict[str, Any] | None) -> dict[str, str | None]:
    if not isinstance(levels, dict):
        return {}
    labels: dict[str, str | None] = {}
    for name, details in levels.items():
        if isinstance(details, dict):
            labels[str(name)] = details.get("stack_group")
    return labels


def _apply_stack_group_labels(target_levels: dict[str, Any] | None, source_levels: dict[str, Any] | None) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    if not isinstance(target_levels, dict) or not isinstance(source_levels, dict):
        return changes
    for name, target_details in target_levels.items():
        source_details = source_levels.get(name)
        if not isinstance(target_details, dict) or not isinstance(source_details, dict):
            continue
        before = target_details.get("stack_group")
        after = source_details.get("stack_group")
        if before != after:
            target_details["stack_group"] = after
            changes.append({"name": str(name), "before": before, "after": after})
    return changes


def _apply_stack_group_rows(liquidity_map: dict[str, Any] | None, source_levels: dict[str, Any] | None) -> None:
    if not isinstance(liquidity_map, dict) or not isinstance(source_levels, dict):
        return
    rows = liquidity_map.get("levels")
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").upper()
        source_details = source_levels.get(name)
        if isinstance(source_details, dict):
            row["stack_group"] = source_details.get("stack_group")


def _apply_latest_level_details(target_levels: dict[str, Any] | None, source_levels: dict[str, Any] | None) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    if not isinstance(target_levels, dict) or not isinstance(source_levels, dict):
        return changes
    for name, target_details in target_levels.items():
        source_details = source_levels.get(name)
        if not isinstance(target_details, dict) or not isinstance(source_details, dict):
            continue
        before = {
            "price": target_details.get("price"),
            "status": target_details.get("status"),
            "stack_group": target_details.get("stack_group"),
        }
        after = {
            "price": source_details.get("price"),
            "status": source_details.get("status"),
            "stack_group": source_details.get("stack_group"),
        }
        if before != after:
            target_details["price"] = source_details.get("price")
            target_details["status"] = source_details.get("status")
            target_details["stack_group"] = source_details.get("stack_group")
            changes.append({"name": str(name), "before": before, "after": after})
    return changes


def _apply_latest_level_rows(liquidity_map: dict[str, Any] | None, source_levels: dict[str, Any] | None) -> None:
    if not isinstance(liquidity_map, dict) or not isinstance(source_levels, dict):
        return
    rows = liquidity_map.get("levels")
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").upper()
        source_details = source_levels.get(name)
        if isinstance(source_details, dict):
            row["price"] = source_details.get("price")
            row["status"] = source_details.get("status")
            row["stack_group"] = source_details.get("stack_group")


def _rebuild_frozen_lock_from_latest_tv(
    symbol: str,
    context: dict[str, Any],
    session_lock: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    latest_levels = context.get("last_tv_context_levels")
    if not isinstance(latest_levels, dict):
        return None, {"error": "latest_tv_context_levels_missing"}
    locked_tv_context = session_lock.get("tv_context")
    if not isinstance(locked_tv_context, dict):
        return None, {"error": "session_liquidity_context_missing_tv_context"}
    locked_levels = locked_tv_context.get("levels")
    if not isinstance(locked_levels, dict) or not locked_levels:
        return None, {"error": "session_liquidity_context_missing_levels"}
    missing_levels = sorted(
        name
        for name, details in locked_levels.items()
        if isinstance(details, dict) and not isinstance(latest_levels.get(name), dict)
    )
    if missing_levels:
        return None, {
            "error": "latest_tv_context_levels_incomplete",
            "missing_levels": missing_levels,
        }
    latest_session_date = str(context.get("last_tv_context_session_date") or context.get("session_date") or "")
    locked_session_date = str(locked_tv_context.get("session_date") or "")
    current_session_date = datetime.now(LOCAL_MARKET_TIMEZONE).date().isoformat()
    if latest_session_date != locked_session_date:
        return None, {
            "error": "session_date_mismatch",
            "latest_tv_context_session_date": latest_session_date,
            "locked_session_date": locked_session_date,
        }
    if locked_session_date != current_session_date:
        return None, {
            "error": "not_current_session",
            "current_session_date": current_session_date,
            "locked_session_date": locked_session_date,
        }
    if session_lock.get("locked") is not True or session_lock.get("disabled") is True:
        return None, {"error": "frozen_lock_not_locked"}

    updated_tv_context = copy.deepcopy(locked_tv_context)
    _apply_latest_level_details(updated_tv_context.get("levels"), latest_levels)
    updated_tv_context["received_at"] = context.get("last_tv_context_received_at") or context.get("received_at") or updated_tv_context.get("received_at")
    updated_tv_context["source"] = context.get("last_tv_context_source") or context.get("source") or updated_tv_context.get("source")
    rebuilt = build_session_locked_tv_context(updated_tv_context)
    if not isinstance(rebuilt, dict) or rebuilt.get("locked") is not True:
        return None, {"error": "rebuilt_frozen_lock_invalid"}
    return rebuilt, None


def _reconstruct_frozen_lock_from_latest_canonical(
    symbol: str,
    context: dict[str, Any],
    session_lock: dict[str, Any],
    *,
    reconstructed_at: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Build a new lock only from a complete, validated, current-session v14 candidate."""
    candidate = context.get("last_tv_context_candidate")
    if not isinstance(candidate, dict):
        return None, {"error": "latest_canonical_candidate_missing"}
    if str(candidate.get("source") or "") != CANONICAL_LIQUIDITY_SOURCE:
        return None, {"error": "latest_canonical_candidate_source_invalid"}
    if str(candidate.get("version") or "") != CANONICAL_LIQUIDITY_VERSION:
        return None, {"error": "latest_canonical_candidate_version_invalid"}
    if normalize_symbol(candidate.get("symbol")) != symbol:
        return None, {"error": "latest_canonical_candidate_symbol_mismatch"}

    locked_tv_context = session_lock.get("tv_context")
    if not isinstance(locked_tv_context, dict):
        return None, {"error": "session_liquidity_context_missing_tv_context"}
    if frozen_liquidity_authority_error(locked_tv_context) is None:
        return None, {"error": "valid_frozen_reference_already_present"}

    current_session_date = datetime.now(LOCAL_MARKET_TIMEZONE).date().isoformat()
    candidate_session_date = str(candidate.get("session_date") or "")
    locked_session_date = str(locked_tv_context.get("session_date") or "")
    if candidate_session_date != locked_session_date:
        return None, {
            "error": "session_date_mismatch",
            "latest_tv_context_session_date": candidate_session_date,
            "locked_session_date": locked_session_date,
        }
    if candidate_session_date != current_session_date:
        return None, {
            "error": "not_current_session",
            "current_session_date": current_session_date,
            "locked_session_date": locked_session_date,
        }

    source_timestamp = parse_timestamp_value(candidate.get("timestamp"))
    source_received_at = parse_timestamp_value(candidate.get("received_at"))
    if source_timestamp is None or source_received_at is None:
        return None, {"error": "latest_canonical_candidate_time_invalid"}
    if context_session_date(candidate.get("timestamp"), fallback=source_timestamp) != candidate_session_date:
        return None, {"error": "latest_canonical_candidate_timestamp_session_mismatch"}
    now_utc = datetime.now(timezone.utc)
    if source_timestamp > now_utc + timedelta(minutes=2):
        return None, {"error": "latest_canonical_candidate_timestamp_in_future"}
    source_age_seconds = (now_utc - source_timestamp).total_seconds()
    receipt_age_seconds = (now_utc - source_received_at).total_seconds()
    if source_age_seconds > CANONICAL_LOCK_RECONSTRUCTION_MAX_AGE_SECONDS:
        return None, {
            "error": "latest_canonical_candidate_stale",
            "source_age_seconds": round(source_age_seconds, 3),
            "maximum_age_seconds": CANONICAL_LOCK_RECONSTRUCTION_MAX_AGE_SECONDS,
        }
    if receipt_age_seconds < -5 or receipt_age_seconds > CANONICAL_LOCK_RECONSTRUCTION_MAX_AGE_SECONDS:
        return None, {
            "error": "latest_canonical_candidate_receipt_stale",
            "receipt_age_seconds": round(receipt_age_seconds, 3),
            "maximum_age_seconds": CANONICAL_LOCK_RECONSTRUCTION_MAX_AGE_SECONDS,
        }

    levels = candidate.get("levels")
    if not isinstance(levels, dict):
        return None, {"error": "latest_canonical_candidate_levels_missing"}
    missing_levels = sorted(name for name in LEVEL_FIELDS if not isinstance(levels.get(name), dict))
    if missing_levels:
        return None, {
            "error": "latest_canonical_candidate_levels_incomplete",
            "missing_levels": missing_levels,
        }
    for field_name in ("session_lock_price", "stack_threshold", "daily_atr14"):
        if _to_float(candidate.get(field_name)) is None:
            return None, {"error": f"latest_canonical_candidate_{field_name}_invalid"}
    structure_error = liquidity_stack_structure_error(candidate)
    if structure_error is not None:
        return None, {**structure_error, "stage": "canonical_lock_reconstruction"}

    transaction_time = reconstructed_at or utc_timestamp()
    if parse_timestamp_value(transaction_time) is None:
        return None, {"error": "reconstruction_timestamp_invalid"}
    reconstructed_context = copy.deepcopy(candidate)
    reconstructed_context["locked"] = True
    reconstructed_context["context_locked"] = True
    reconstructed_context["locked_for_day"] = True
    reconstructed_context["liquidity_context_locked"] = True
    reconstructed_context["liquidity_context_locked_at"] = transaction_time
    reconstructed_context["liquidity_context_source"] = CANONICAL_LIQUIDITY_SOURCE
    reconstructed_context["lock_reconstruction"] = {
        "reason": CANONICAL_LOCK_RECONSTRUCTION_REASON,
        "performed_at": transaction_time,
        "source_timestamp": candidate.get("timestamp"),
        "source_received_at": candidate.get("received_at"),
        "previous_locked_at": locked_tv_context.get("liquidity_context_locked_at") or locked_tv_context.get("received_at"),
        "previous_session_lock_price": locked_tv_context.get("session_lock_price"),
    }
    rebuilt = build_session_locked_tv_context(reconstructed_context)
    if not isinstance(rebuilt, dict) or rebuilt.get("locked") is not True or rebuilt.get("disabled") is True:
        return None, {
            "error": "rebuilt_frozen_lock_invalid",
            "detail": rebuilt.get("error") if isinstance(rebuilt, dict) else None,
        }
    return rebuilt, None


def append_operator_audit_event(state: dict[str, Any], symbol: str, event: dict[str, Any]) -> None:
    """Append operator audit events to per-symbol persisted state."""
    symbol_state = _target_symbol_state(state, symbol)
    if not isinstance(symbol_state, dict):
        return
    event_log = symbol_state.get("event_log")
    if not isinstance(event_log, list):
        event_log = []
        symbol_state["event_log"] = event_log
    event_log.append(event)


def append_operator_route_audit(event: dict[str, Any]) -> None:
    """Append one operator-route audit record to the shared operator audit log."""
    ENTRY_LOG_DIR.mkdir(parents=True, exist_ok=True)
    with OPERATOR_AUDIT_LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, separators=(",", ":")) + "\n")


def append_context_event(
    context: dict[str, Any],
    remote_addr: str | None,
    received_payload: dict[str, Any] | None = None,
) -> None:
    """Append one successful TradingView context webhook event."""
    event = {
        "schema_version": "tv_context_receipt_v2",
        "acceptance_result": "accepted",
        "received_at": context.get("received_at"),
        "source": context.get("source"),
        "symbol": context.get("symbol"),
        "normalized_symbol": context.get("normalized_symbol"),
        "session_date": context.get("session_date"),
        "levels": copy.deepcopy(context.get("levels")) if isinstance(context.get("levels"), dict) else None,
        "liquidity_map": copy.deepcopy(public_liquidity_map(context)),
        "locked_liquidity_context": copy.deepcopy(locked_liquidity_context(context)),
        "pm_atr_pct": context.get("pm_atr_pct"),
        "daily_range_pct": context.get("daily_range_pct"),
        "time_zone": context.get("time_zone"),
        "received_payload": copy.deepcopy(received_payload) if isinstance(received_payload, dict) else None,
        "remote_addr": remote_addr,
    }
    with TV_CONTEXT_EVENTS_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, separators=(",", ":")) + "\n")


def append_rejected_context_event(
    payload: dict[str, Any],
    remote_addr: str | None,
    error: dict[str, Any],
) -> None:
    """Archive a complete semantically rejected TradingView payload."""
    event = {
        "schema_version": "tv_context_receipt_v2",
        "received_at": utc_timestamp(),
        "acceptance_result": "rejected",
        "rejection": copy.deepcopy(error),
        "source": payload.get("source"),
        "symbol": payload.get("symbol"),
        "normalized_symbol": normalize_symbol(payload.get("symbol")),
        "session_date": payload.get("session_date"),
        "received_payload": copy.deepcopy(payload),
        "remote_addr": remote_addr,
    }
    TV_CONTEXT_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TV_CONTEXT_EVENTS_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, separators=(",", ":")) + "\n")


def _normalized_level_snapshot(levels: Any) -> dict[str, dict[str, Any]]:
    """Return a stable comparison view for level payloads."""
    snapshot: dict[str, dict[str, Any]] = {}
    if not isinstance(levels, dict):
        return snapshot
    for name, details in levels.items():
        if not isinstance(details, dict):
            continue
        snapshot[str(name).upper()] = {
            "price": details.get("price"),
            "status": details.get("status"),
            "stack_group": details.get("stack_group"),
        }
    return snapshot


def _context_lock_timestamp(context: dict[str, Any] | None) -> datetime | None:
    """Return the effective liquidity-lock timestamp for a stored context."""
    if not isinstance(context, dict):
        return None
    locked = locked_liquidity_context(context)
    return (
        parse_timestamp_value(context.get("liquidity_context_locked_at"))
        or parse_timestamp_value((locked or {}).get("locked_at") if isinstance(locked, dict) else None)
        or parse_timestamp_value(context.get("received_at"))
    )


def _context_session_date(context: dict[str, Any] | None) -> str:
    """Return the effective stored session date for a context."""
    if not isinstance(context, dict):
        return ""
    locked = locked_liquidity_context(context)
    return str(
        context.get("session_date")
        or ((locked or {}).get("session_date") if isinstance(locked, dict) else "")
        or ""
    )


def should_replace_stale_locked_liquidity_context(
    existing_context: dict[str, Any] | None,
    incoming_context: dict[str, Any],
) -> bool:
    """Replace only a prior-session lock; same-session repair requires an operator transaction."""
    if not isinstance(existing_context, dict):
        return False
    existing_locked = locked_liquidity_context(existing_context)
    if not isinstance(existing_locked, dict):
        return False
    incoming_explicit_locked = (
        incoming_context.get("liquidity_context_locked") is True
        or incoming_context.get("locked") is True
        or incoming_context.get("context_locked") is True
        or incoming_context.get("locked_for_day") is True
        or incoming_context.get("session_locked") is True
        or incoming_context.get("liquidity_context_locked_at") is not None
    )
    if not incoming_explicit_locked:
        return False
    existing_session = _context_session_date(existing_context)
    incoming_session = str(incoming_context.get("session_date") or "")
    incoming_time = (
        parse_timestamp_value(incoming_context.get("liquidity_context_locked_at"))
        or parse_timestamp_value(incoming_context.get("received_at"))
    )
    existing_time = _context_lock_timestamp(existing_context)
    if incoming_time is None or existing_time is None:
        return False
    if incoming_time <= existing_time:
        return False
    if not existing_session or not incoming_session or incoming_session == existing_session:
        return False
    return incoming_session > existing_session


def clear_symbol_pathway_state(state: dict[str, Any], symbol: str) -> tuple[dict[str, Any], list[str]]:
    """Clear symbol-scoped persisted pathway state before replacing a stale session lock."""
    cleared: list[str] = []
    target = _target_symbol_state(state, symbol)
    if isinstance(target, dict):
        for key in (
            "step_2_1a",
            "step2_locked_owner",
            "rejection",
            "step25",
            "step3",
            "step4",
            "step5",
            "step6",
            "rejection_lane",
            "continuation_lane",
            "gateway",
            "session_liquidity_context",
            "trade_state",
            "market_state",
            "last_interacted_liquidity",
            "consumed_liquidity_levels",
            "consumed_entry_setups",
            "step_2_1a_last_evaluated_bar_time",
            "step_2_1a_candle_index",
        ):
            if key in target:
                target.pop(key, None)
                cleared.append(key)
    by_symbol = state.get("state_by_symbol")
    if isinstance(by_symbol, dict):
        symbol_state = by_symbol.get(symbol)
        if isinstance(symbol_state, dict):
            by_symbol[symbol] = target if isinstance(target, dict) else symbol_state
    last_by_symbol = state.get("last_interacted_liquidity_by_symbol")
    if isinstance(last_by_symbol, dict) and symbol in last_by_symbol:
        last_by_symbol.pop(symbol, None)
        cleared.append("last_interacted_liquidity_by_symbol")
    return state, cleared


def entry_decision_record(status: dict[str, Any], timestamp: str | None = None) -> dict[str, Any]:
    """Return the persisted read-only Entry Agent decision record."""
    return {
        "timestamp": timestamp or utc_timestamp(),
        "symbol": status.get("symbol"),
        "current_step": status.get("current_step"),
        "current_step_label": status.get("current_step_label"),
        "active_liquidity_name": status.get("active_liquidity_name"),
        "setup_direction": status.get("setup_direction"),
        "leg1_status": status.get("leg1_status"),
        "leg2_status": status.get("leg2_status"),
        "entry_status": status.get("entry_status"),
        "wait_reason": status.get("wait_reason"),
        "invalidation_reason": status.get("invalidation_reason"),
        "last_decision": status.get("last_decision"),
    }


def entry_decision_state_key(record: dict[str, Any]) -> tuple[Any, ...]:
    """Return fields that define a meaningful Entry Agent state change."""
    return (
        record.get("current_step"),
        record.get("active_liquidity_name"),
        record.get("setup_direction"),
        record.get("leg1_status"),
        record.get("leg2_status"),
        record.get("entry_status"),
        record.get("wait_reason"),
        record.get("invalidation_reason"),
        record.get("last_decision"),
    )


def should_log_entry_decision(record: dict[str, Any], now_monotonic: float | None = None) -> bool:
    """Throttle Entry Agent decision logging per symbol."""
    symbol = str(record.get("symbol") or "").upper()
    if not symbol:
        return False
    now = time.monotonic() if now_monotonic is None else now_monotonic
    state_key = entry_decision_state_key(record)
    previous = ENTRY_DECISION_LAST_LOGGED.get(symbol)
    if not previous:
        ENTRY_DECISION_LAST_LOGGED[symbol] = {"state_key": state_key, "monotonic": now}
        return True
    if previous.get("state_key") != state_key:
        ENTRY_DECISION_LAST_LOGGED[symbol] = {"state_key": state_key, "monotonic": now}
        return True
    if now - float(previous.get("monotonic") or 0.0) >= ENTRY_DECISION_LOG_THROTTLE_SECONDS:
        ENTRY_DECISION_LAST_LOGGED[symbol] = {"state_key": state_key, "monotonic": now}
        return True
    return False


def append_entry_decision_log(records: list[dict[str, Any]]) -> None:
    """Append throttled Entry Agent decision records; never fail the status request."""
    to_write = [record for record in records if should_log_entry_decision(record)]
    if not to_write:
        return
    try:
        ENTRY_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with ENTRY_DECISIONS_LOG_PATH.open("a", encoding="utf-8") as file:
            for record in to_write:
                file.write(json.dumps(record, separators=(",", ":")) + "\n")
    except OSError as exc:
        print(f"ENTRY DECISION LOG write_error={exc}")


def reasoning_log_path(date_text: str | None = None) -> Path:
    """Return the daily Entry Agent reasoning log path."""
    date_value = date_text or datetime.now(timezone.utc).date().isoformat()
    return ENTRY_REASONING_DIR / f"entry_reasoning_{date_value}.jsonl"


def sanitize_public_entry_status(status: dict[str, Any]) -> dict[str, Any]:
    """Prevent internal-only Step 3 from reaching Command Center status output."""
    if not isinstance(status, dict):
        return status
    if status.get("current_step") != "Step 3":
        return status
    sanitized = dict(status)
    sanitized["current_step"] = "Step 2"
    sanitized["current_step_label"] = current_step_label("Step 2")
    return sanitized


def entry_reasoning_record(status: dict[str, Any], timestamp: str | None = None) -> dict[str, Any]:
    """Return a chart-review reasoning record from a status payload."""
    return {
        "timestamp": timestamp or utc_timestamp(),
        "symbol": status.get("symbol"),
        "candle_time": status.get("candle_time"),
        "candle_open": status.get("candle_open"),
        "candle_high": status.get("candle_high"),
        "candle_low": status.get("candle_low"),
        "candle_close": status.get("candle_close"),
        "active_liquidity_name": status.get("active_liquidity_name"),
        "liquidity_price": status.get("liquidity_price") or status.get("active_liquidity_price"),
        "liquidity_level_name": status.get("liquidity_level_name"),
        "liquidity_level_price": status.get("liquidity_level_price"),
        "rejection_boundary": status.get("rejection_boundary"),
        "continuation_boundary": status.get("continuation_boundary"),
        "liquidity_group": status.get("liquidity_group"),
        "frozen_tv_level": status.get("frozen_tv_level"),
        "pre_open_observed_extreme": status.get("pre_open_observed_extreme"),
        "close_vs_level": status.get("close_vs_level"),
        "step": status.get("current_step"),
        "current_step_label": status.get("current_step_label"),
        "step2_candle_count": status.get("step2_candle_count"),
        "setup_direction": status.get("setup_direction"),
        "rejection_mode_entered": bool(status.get("rejection_mode_entered")),
        "sr_rs_context": status.get("sr_rs_context"),
        "current_pathway_control": status.get("current_pathway_control"),
        "control_state": status.get("control_state"),
        "conflict_state": status.get("conflict_state"),
        "step2_status": status.get("step2_status"),
        "step25_status": status.get("step25_status"),
        "step3_status": status.get("step3_status"),
        "step4_status": status.get("step4_status"),
        "step4_reason": status.get("step4_reason"),
        "step4_confirmed_at": status.get("step4_confirmed_at") or status.get("step4_rejection_completed_at"),
        "step4_window_count": status.get("step4_window_count"),
        "leg2_sweep_extreme": status.get("leg2_sweep_extreme"),
        "step5_close_boundary": status.get("step5_close_boundary"),
        "step5_status": status.get("step5_status"),
        "step6_status": status.get("step6_status"),
        "rejection_lane": status.get("rejection_lane"),
        "continuation_lane": status.get("continuation_lane"),
        "current_controlling_mode": status.get("current_controlling_mode"),
        "current_continuation_type": status.get("current_continuation_type"),
        "leg1_state": status.get("leg1_state") or status.get("leg1_status"),
        "leg1_locked": status.get("leg1_locked") or status.get("leg1_state_locked"),
        "leg1_reference_price": status.get("leg1_reference_price"),
        "leg1_completed_at": status.get("leg1_completed_at"),
        "leg1_window_active": status.get("leg1_window_active"),
        "leg1_window_started_at": status.get("leg1_window_started_at"),
        "leg1_window_candle_index": status.get("leg1_window_candle_index"),
        "leg1_window_remaining": status.get("leg1_window_remaining"),
        "leg1_window_expires_at": status.get("leg1_window_expires_at"),
        "leg1_window_invalidated": status.get("leg1_window_invalidated"),
        "leg1_window_invalidation_reason": status.get("leg1_window_invalidation_reason"),
        "fifty_percent_rule_phase": status.get("fifty_percent_rule_phase"),
        "step2_step4_50_line": status.get("step2_step4_50_line") or status.get("step4_participation_50_line"),
        "step4_step5_75_line": status.get("step4_step5_75_line") or status.get("step4_participation_75_line"),
        "step4_participation_50_line": status.get("step4_participation_50_line"),
        "step4_participation_75_line": status.get("step4_participation_75_line"),
        "step4_participation_lines_visible": status.get("step4_participation_lines_visible"),
        "leg2_state": status.get("leg2_state") or status.get("leg2_status"),
        "leg2_candidate_candle_time": status.get("leg2_candidate_candle_time"),
        "leg2_reference_price": status.get("leg2_reference_price"),
        "leg2_25_percent_rule_passed": status.get("leg2_25_percent_rule_passed"),
        "continuation_controlling_structure_high": status.get("continuation_controlling_structure_high"),
        "continuation_controlling_structure_low": status.get("continuation_controlling_structure_low"),
        "continuation_controlling_structure_start_time": status.get("continuation_controlling_structure_start_time"),
        "continuation_controlling_structure_end_time": status.get("continuation_controlling_structure_end_time"),
        "continuation_controlling_structure_source_step": status.get("continuation_controlling_structure_source_step"),
        "entry_status": status.get("entry_status"),
        "invalidation_source": status.get("invalidation_source"),
        "invalidation_reason": status.get("invalidation_reason"),
        "wait_reason": status.get("wait_reason"),
        "last_decision": status.get("last_decision"),
        "publication_gate_debug": status.get("publication_gate_debug"),
    }


def reasoning_state_key(record: dict[str, Any]) -> tuple[Any, ...]:
    """Return fields that define a reasoning transition."""
    return (
        record.get("candle_time"),
        record.get("step"),
        record.get("step2_candle_count"),
        record.get("active_liquidity_name"),
        record.get("liquidity_price"),
        record.get("frozen_tv_level"),
        record.get("pre_open_observed_extreme"),
        record.get("setup_direction"),
        record.get("rejection_mode_entered"),
        record.get("sr_rs_context"),
        record.get("current_pathway_control"),
        record.get("control_state"),
        record.get("conflict_state"),
        record.get("step2_status"),
        record.get("step25_status"),
        record.get("step3_status"),
        record.get("step4_status"),
        record.get("step4_reason"),
        record.get("step5_status"),
        record.get("step6_status"),
        json.dumps(record.get("rejection_lane"), sort_keys=True, default=str),
        json.dumps(record.get("continuation_lane"), sort_keys=True, default=str),
        record.get("current_controlling_mode"),
        record.get("current_continuation_type"),
        record.get("leg1_state"),
        record.get("leg1_locked"),
        record.get("leg1_reference_price"),
        record.get("leg1_completed_at"),
        record.get("leg1_window_active"),
        record.get("leg1_window_started_at"),
        record.get("leg1_window_candle_index"),
        record.get("leg1_window_remaining"),
        record.get("leg1_window_expires_at"),
        record.get("leg1_window_invalidated"),
        record.get("leg1_window_invalidation_reason"),
        record.get("fifty_percent_rule_phase"),
        record.get("step2_step4_50_line"),
        record.get("step4_step5_75_line"),
        record.get("step4_participation_50_line"),
        record.get("step4_participation_75_line"),
        record.get("step4_participation_lines_visible"),
        record.get("leg2_state"),
        record.get("leg2_candidate_candle_time"),
        record.get("leg2_reference_price"),
        record.get("leg2_25_percent_rule_passed"),
        record.get("continuation_controlling_structure_high"),
        record.get("continuation_controlling_structure_low"),
        record.get("continuation_controlling_structure_start_time"),
        record.get("continuation_controlling_structure_end_time"),
        record.get("continuation_controlling_structure_source_step"),
        record.get("entry_status"),
        record.get("invalidation_source"),
        record.get("invalidation_reason"),
        record.get("wait_reason"),
        record.get("last_decision"),
    )


def last_reasoning_record_for_symbol(symbol: str, path: Path) -> dict[str, Any] | None:
    """Read the latest reasoning record for one symbol from a daily file."""
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict) and str(record.get("symbol") or "").upper() == symbol:
                    latest = record
    except OSError:
        return None
    return latest if "latest" in locals() else None


def should_log_entry_reasoning(record: dict[str, Any], path: Path) -> bool:
    """Append only on state transition or new closed candle, scoped per symbol."""
    symbol = str(record.get("symbol") or "").upper()
    if not symbol:
        return False
    state_key = reasoning_state_key(record)
    previous = ENTRY_REASONING_LAST_LOGGED.get(symbol)
    if not previous:
        previous_record = last_reasoning_record_for_symbol(symbol, path)
        if previous_record:
            previous = {
                "state_key": reasoning_state_key(previous_record),
                "candle_time": previous_record.get("candle_time"),
            }
            ENTRY_REASONING_LAST_LOGGED[symbol] = previous
    if not previous:
        ENTRY_REASONING_LAST_LOGGED[symbol] = {"state_key": state_key, "candle_time": record.get("candle_time")}
        return True
    if previous.get("candle_time") != record.get("candle_time") or previous.get("state_key") != state_key:
        ENTRY_REASONING_LAST_LOGGED[symbol] = {"state_key": state_key, "candle_time": record.get("candle_time")}
        return True
    return False


def append_entry_reasoning_log(records: list[dict[str, Any]], date_text: str | None = None) -> None:
    """Append daily reasoning records without logging every tick."""
    path = reasoning_log_path(date_text)
    to_write = [record for record in records if should_log_entry_reasoning(record, path)]
    if not to_write:
        return
    try:
        ENTRY_REASONING_DIR.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            for record in to_write:
                file.write(json.dumps(record, separators=(",", ":")) + "\n")
    except OSError as exc:
        print(f"ENTRY REASONING LOG write_error={exc}")


def read_entry_reasoning_log(symbols: set[str], date_text: str | None, limit: int = 2000) -> list[dict[str, Any]]:
    """Read daily reasoning log records filtered by normalized requested roots."""
    path = reasoning_log_path(date_text)
    if not path.exists():
        return []
    rows: deque[dict[str, Any]] = deque(maxlen=limit)
    try:
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                record_root = normalize_symbol(record.get("symbol"))
                if isinstance(record, dict) and record_root in symbols:
                    rows.append(record)
    except OSError:
        return []
    return list(rows)


def tail_entry_decision_log(limit: int) -> list[dict[str, Any]]:
    """Read the latest Entry Agent decision log records."""
    if not ENTRY_DECISIONS_LOG_PATH.exists():
        return []
    lines: deque[str] = deque(maxlen=limit)
    try:
        with ENTRY_DECISIONS_LOG_PATH.open("r", encoding="utf-8") as file:
            for line in file:
                if line.strip():
                    lines.append(line)
    except OSError:
        return []

    records = []
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def parse_boolish(value: Any) -> bool:
    """Parse a webhook force flag from query string or JSON."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def parse_timestamp_value(value: Any) -> datetime | None:
    """Parse inbound timestamps from ISO strings or epoch values."""
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 1_000_000_000_000:
            timestamp /= 1000.0
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.isdigit():
        return parse_timestamp_value(int(text))
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


REQUIRED_CONTEXT_FIELDS = (
    "source",
    "timestamp",
    "session_date",
    "time_zone",
    "locked",
    "session_lock_price",
    "atr_1m_14",
    "daily_atr14",
    "taylor_context",
)


def missing_required_context_field(payload: dict[str, Any]) -> str | None:
    """Return the first missing required webhook field."""
    for field_name in REQUIRED_CONTEXT_FIELDS:
        if field_name not in payload:
            return field_name
        value = payload.get(field_name)
        if value is None:
            return field_name
        if isinstance(value, str) and not value.strip():
            return field_name
    return None


def context_session_date(timestamp_value: Any, fallback: datetime | None = None) -> str:
    """Resolve the market-local session date for a context payload."""
    parsed = parse_timestamp_value(timestamp_value) or fallback or datetime.now(timezone.utc)
    return parsed.astimezone(LOCAL_MARKET_TIMEZONE).date().isoformat()


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    converted = float(value)
    return converted if math.isfinite(converted) else None


def canonical_payload_bytes(payload: dict[str, Any]) -> bytes:
    """Return deterministic immutable sender bytes for delivery identity."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_message_identity(payload: dict[str, Any], normalized_symbol: str) -> tuple[str, str]:
    payload_sha = hashlib.sha256(canonical_payload_bytes(payload)).hexdigest()
    authority = "|".join(
        (
            normalized_symbol,
            str(payload.get("session_date") or ""),
            str(payload.get("timestamp") or ""),
            payload_sha,
        )
    ).encode("utf-8")
    return hashlib.sha256(authority).hexdigest(), payload_sha


def _canonical_level_semantics(raw: Any, field: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not isinstance(raw, dict):
        return None, {"error": f"{field} must be an object"}
    price = raw.get("price")
    if price is not None and _finite_number(price) is None:
        return None, {"error": f"{field}.price must be a finite number or null"}
    status = str(raw.get("status") or "").strip().upper()
    if status not in CANONICAL_LEVEL_STATUSES:
        return None, {"error": f"{field}.status is invalid"}
    stack_group = str(raw.get("stack_group") or "").strip()
    if not stack_group:
        return None, {"error": f"{field}.stack_group is required"}
    stack_groups = raw.get("stack_groups")
    if not isinstance(stack_groups, list) or any(not isinstance(value, str) or not value.strip() for value in stack_groups):
        return None, {"error": f"{field}.stack_groups must be an array of non-empty strings"}
    if len(stack_groups) != len(set(stack_groups)):
        return None, {"error": f"{field}.stack_groups contains duplicates"}
    stack_display = raw.get("stack_display")
    if not isinstance(stack_display, str) or not stack_display.strip():
        return None, {"error": f"{field}.stack_display is required"}
    return {
        "price": None if price is None else float(price),
        "status": status,
        "stack_group": stack_group,
        "stack_groups": list(stack_groups),
        "stack_display": stack_display,
    }, None


def validate_canonical_liquidity_payload(
    payload: dict[str, Any],
    normalized_symbol: str,
) -> tuple[dict[str, dict[str, Any]] | None, dict[str, Any] | None]:
    """Fail closed on the exact canonical v14 sender and duplicate/parity contract."""
    exact_fields = {
        "source": CANONICAL_LIQUIDITY_SOURCE,
        "version": CANONICAL_LIQUIDITY_VERSION,
        "context_mode": CANONICAL_LIQUIDITY_CONTEXT_MODE,
        "time_zone": CANONICAL_LIQUIDITY_TIMEZONE,
        "timeframe": CANONICAL_LIQUIDITY_TIMEFRAME,
    }
    for field, expected in exact_fields.items():
        if payload.get(field) != expected:
            return None, {"error": f"{field} must equal {expected}"}
    timestamp = payload.get("timestamp")
    parsed_timestamp = parse_timestamp_value(timestamp)
    try:
        source_timestamp = datetime.fromisoformat(str(timestamp).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        source_timestamp = None
    if (
        not isinstance(timestamp, str)
        or parsed_timestamp is None
        or source_timestamp is None
        or source_timestamp.tzinfo is None
        or source_timestamp.utcoffset() != timedelta(0)
    ):
        return None, {"error": "timestamp must be a valid UTC timestamp"}
    session_date = payload.get("session_date")
    try:
        parsed_session_date = datetime.strptime(str(session_date), "%Y-%m-%d").date().isoformat()
    except (TypeError, ValueError):
        return None, {"error": "session_date must be a valid YYYY-MM-DD date"}
    if str(session_date) != parsed_session_date:
        return None, {"error": "session_date must be canonical YYYY-MM-DD"}
    for field in ("session_locked", "locked", "price_is_true_level", "display_offsets_applied_to_chart_only"):
        if payload.get(field) is not True:
            return None, {"error": f"{field} must be true"}
    if not str(payload.get("symbol") or "").strip() or normalized_symbol not in {"NQ", "YM"}:
        return None, {"error": "symbol must normalize to NQ or YM"}
    for field in ("session_lock_price", "stack_threshold"):
        if _finite_number(payload.get(field)) is None:
            return None, {"error": f"{field} must be a finite number"}

    raw_levels = payload.get("levels")
    if not isinstance(raw_levels, dict):
        return None, {"error": "levels must be an object"}
    level_names = set(raw_levels)
    expected_names = set(LEVEL_FIELDS)
    if level_names != expected_names:
        return None, {
            "error": "levels must contain each canonical name exactly once",
            "missing": sorted(expected_names - level_names),
            "unknown": sorted(level_names - expected_names),
        }
    normalized: dict[str, dict[str, Any]] = {}
    for name in LEVEL_FIELDS:
        row, row_error = _canonical_level_semantics(raw_levels.get(name), f"levels.{name}")
        if row_error is not None:
            return None, row_error
        normalized[name] = row or {}

    liquidity_map = payload.get("liquidity_map")
    if not isinstance(liquidity_map, dict):
        return None, {"error": "liquidity_map is required"}
    if not isinstance(payload.get("stacks"), list) or not isinstance(liquidity_map.get("stacks"), list):
        return None, {"error": "stacks and liquidity_map.stacks must be arrays"}
    if payload.get("stacks") != liquidity_map.get("stacks"):
        return None, {"error": "stacks/liquidity_map.stacks parity mismatch"}
    map_rows = liquidity_map.get("levels")
    if not isinstance(map_rows, list) or len(map_rows) != len(LEVEL_FIELDS):
        return None, {"error": "liquidity_map.levels must contain exactly eight rows"}
    mapped: dict[str, dict[str, Any]] = {}
    for index, raw_row in enumerate(map_rows):
        if not isinstance(raw_row, dict):
            return None, {"error": f"liquidity_map.levels[{index}] must be an object"}
        name = str(raw_row.get("name") or "").strip().upper()
        if name not in expected_names:
            return None, {"error": f"liquidity_map.levels[{index}].name is unknown"}
        if name in mapped:
            return None, {"error": f"liquidity_map.levels contains duplicate name {name}"}
        row, row_error = _canonical_level_semantics(raw_row, f"liquidity_map.levels[{index}]")
        if row_error is not None:
            return None, row_error
        mapped[name] = row or {}
    if set(mapped) != expected_names:
        return None, {"error": "liquidity_map.levels is missing canonical names"}
    for name in LEVEL_FIELDS:
        if normalized[name] != mapped[name]:
            return None, {"error": f"levels/liquidity_map parity mismatch for {name}"}

    reference = float(payload["session_lock_price"])
    for name, row in normalized.items():
        row["side"] = side_for_level_price(name, row.get("price"), reference)
    return normalized, None


def _duplicate_rejecting_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def derived_liquidity_stacks(levels: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Derive the frozen stack ladder from authoritative level labels."""
    if not isinstance(levels, dict):
        return []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for name, details in levels.items():
        if not isinstance(details, dict):
            continue
        normalized_name = str(name).upper()
        group_name = normalize_stack_group_label(details.get("stack_group"))
        status = str(details.get("status") or "").strip().upper()
        price = _to_float(details.get("price"))
        if group_name in {None, "NONE"} or status not in {"ACTIVE", "REACTIVATED"} or price is None:
            continue
        side = "upper" if stack_group_side(group_name) == "high" else "lower"
        grouped.setdefault(group_name, []).append(
            {"name": normalized_name, "price": price, "side": side}
        )
    stacks: list[dict[str, Any]] = []
    for group_name, components in sorted(grouped.items()):
        side = components[0]["side"]
        components.sort(
            key=lambda item: (item["price"], item["name"]),
            reverse=side == "lower",
        )
        prices = [item["price"] for item in components]
        stacks.append(
            {
                "name": group_name,
                "side": side,
                "components": [item["name"] for item in components],
                "prices": {item["name"]: item["price"] for item in components},
                "close_boundary": min(prices) if side == "upper" else max(prices),
                "extreme_boundary": max(prices) if side == "upper" else min(prices),
            }
        )
    return stacks


def public_liquidity_map(context: dict[str, Any]) -> dict[str, Any] | None:
    """Return a display-safe liquidity map from stored context."""
    liquidity_map = context.get("liquidity_map")
    if isinstance(liquidity_map, dict):
        projected = copy.deepcopy(liquidity_map)
        if not projected.get("stacks"):
            projected["stacks"] = derived_liquidity_stacks(context.get("levels"))
        return projected
    levels = context.get("levels")
    if not isinstance(levels, dict):
        return None
    level_rows = []
    for name in LEVEL_FIELDS:
        details = levels.get(name)
        if not isinstance(details, dict):
            continue
        level_rows.append(
            {
                "name": name,
                "price": details.get("price"),
                "status": details.get("status"),
                "stack_group": details.get("stack_group"),
            }
        )
    return {"levels": level_rows, "stacks": derived_liquidity_stacks(levels)}


def normalize_levels_from_liquidity_map(liquidity_map: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Normalize list-based liquidity-map rows into the legacy nested levels dict."""
    levels_payload = liquidity_map.get("levels")
    if not isinstance(levels_payload, list) or not levels_payload:
        return None, {"error": "liquidity_map.levels must be a non-empty array"}
    normalized_levels: dict[str, Any] = {}
    for index, raw_level in enumerate(levels_payload):
        if not isinstance(raw_level, dict):
            return None, {"error": f"liquidity_map.levels[{index}] must be an object"}
        name = str(raw_level.get("name") or "").strip().upper()
        if name not in LEVEL_FIELDS:
            return None, {"error": f"liquidity_map.levels[{index}].name must be one of {', '.join(LEVEL_FIELDS)}"}
        price, price_error = parse_optional_number(raw_level.get("price"), f"liquidity_map.levels[{index}].price")
        if price_error is not None:
            return None, {"error": price_error}
        status = str(raw_level.get("status") or "").strip().upper()
        if not status:
            return None, {"error": f"liquidity_map.levels[{index}].status is required"}
        stack_group = str(raw_level.get("stack_group") or "NONE").strip() or "NONE"
        normalized_levels[name] = {"price": price, "status": status, "stack_group": stack_group}
    return normalized_levels, None


def liquidity_stack_structure_error(context: dict[str, Any]) -> dict[str, Any] | None:
    """Validate sender rows and optional explicit groups using frozen authority."""
    liquidity_map = context.get("liquidity_map")
    explicit_stacks = None
    if isinstance(liquidity_map, dict) and "stacks" in liquidity_map:
        explicit_stacks = liquidity_map.get("stacks")
    return validate_liquidity_stack_structure(
        context.get("levels"),
        explicit_stacks,
        stack_threshold=stack_threshold_from_context(context),
        session_reference_price=stack_reference_price_from_context(context),
    )


def has_valid_liquidity_levels(context: dict[str, Any]) -> bool:
    """Return True when the payload includes a usable nested levels table."""
    if not isinstance(context, dict):
        return False
    levels = context.get("levels")
    if not isinstance(levels, dict):
        return False
    return any(name in LEVEL_FIELDS and isinstance(details, dict) for name, details in levels.items())


def has_valid_taylor_context(context: dict[str, Any]) -> bool:
    """Return True when the payload includes a usable Taylor context block."""
    if not isinstance(context, dict):
        return False
    taylor_context = context.get("taylor_context")
    if not isinstance(taylor_context, dict):
        return False
    return any(key in TAYLOR_CONTEXT_KEYS and isinstance(taylor_context.get(key), dict) for key in TAYLOR_CONTEXT_KEYS)


def frozen_liquidity_authority_error(context: dict[str, Any] | None) -> str | None:
    """Return the canonical authority defect for an otherwise preserved frozen block."""
    if not isinstance(context, dict):
        return "SESSION_LOCK_CONTEXT_MISSING"
    if _to_float(context.get("session_lock_price")) is None:
        return "SESSION_LOCK_REFERENCE_PRICE_MISSING"
    return None


def locked_liquidity_context(context: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the immutable session liquidity block if one exists."""
    if not isinstance(context, dict):
        return None
    existing = context.get("locked_liquidity_context")
    if isinstance(existing, dict) and has_valid_liquidity_levels(existing):
        projected = copy.deepcopy(existing)
        projected["liquidity_map"] = public_liquidity_map(projected)
        authority_error = frozen_liquidity_authority_error(projected)
        projected["authoritative"] = authority_error is None
        projected["authority_error"] = authority_error
        return projected
    if context.get("liquidity_context_locked") is not True or not has_valid_liquidity_levels(context):
        return None
    projected = {
        "levels": copy.deepcopy(context.get("levels")),
        "liquidity_map": public_liquidity_map(context),
        "session_date": context.get("session_date"),
        "locked_at": context.get("liquidity_context_locked_at") or context.get("received_at"),
        "source": context.get("liquidity_context_source") or context.get("source"),
        "session_lock_price": context.get("session_lock_price"),
        "stack_threshold": context.get("stack_threshold"),
        "daily_atr14": context.get("daily_atr14"),
        "midpoints": copy.deepcopy(context.get("midpoints")) if isinstance(context.get("midpoints"), dict) else None,
        "exhaustion_boundaries": copy.deepcopy(context.get("exhaustion_boundaries")) if isinstance(context.get("exhaustion_boundaries"), dict) else None,
    }
    authority_error = frozen_liquidity_authority_error(projected)
    projected["authoritative"] = authority_error is None
    projected["authority_error"] = authority_error
    return projected


def locked_taylor_context(context: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the immutable session Taylor block if one exists."""
    if not isinstance(context, dict):
        return None
    existing = context.get("locked_taylor_context")
    if isinstance(existing, dict) and has_valid_taylor_context(existing):
        return existing
    if context.get("taylor_context_locked") is not True or not has_valid_taylor_context(context):
        return None
    return {
        "taylor_context": copy.deepcopy(context.get("taylor_context")),
        "session_date": context.get("session_date"),
        "locked_at": context.get("taylor_context_locked_at") or context.get("received_at"),
        "source": context.get("taylor_context_source") or context.get("source"),
    }


def public_market_context(context: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the public market-context block for status and snapshot APIs."""
    if not isinstance(context, dict):
        return None
    locked_liquidity = locked_liquidity_context(context)
    locked_taylor = locked_taylor_context(context)
    return {
        "source": context.get("source"),
        "symbol": context.get("symbol"),
        "normalized_symbol": context.get("normalized_symbol"),
        "session_date": context.get("session_date"),
        "received_at": context.get("received_at"),
        "locked": context.get("locked"),
        "liquidity_context_locked": context.get("liquidity_context_locked"),
        "liquidity_context_locked_at": context.get("liquidity_context_locked_at"),
        "liquidity_context_source": context.get("liquidity_context_source"),
        "liquidity_context_authoritative": context.get("liquidity_context_authoritative"),
        "liquidity_context_authority_error": context.get("liquidity_context_authority_error"),
        "locked_liquidity_context": copy.deepcopy(locked_liquidity) if isinstance(locked_liquidity, dict) else None,
        "session_lock_price": context.get("session_lock_price"),
        "daily_atr14": context.get("daily_atr14"),
        "levels": copy.deepcopy(context.get("levels")) if isinstance(context.get("levels"), dict) else None,
        "last_tv_context_received_at": context.get("last_tv_context_received_at") or context.get("received_at"),
        "last_tv_context_session_date": context.get("last_tv_context_session_date") or context.get("session_date"),
        "last_tv_context_source": context.get("last_tv_context_source") or context.get("source"),
        "last_tv_context_version": context.get("last_tv_context_version") or context.get("version"),
        "last_tv_context_timestamp": context.get("last_tv_context_timestamp") or context.get("timestamp"),
        "last_tv_context_levels": copy.deepcopy(context.get("last_tv_context_levels")) if isinstance(context.get("last_tv_context_levels"), dict) else None,
        "liquidity_map": public_liquidity_map(context),
        "taylor_context_locked": context.get("taylor_context_locked"),
        "taylor_context_locked_at": context.get("taylor_context_locked_at"),
        "taylor_context_source": context.get("taylor_context_source"),
        "locked_taylor_context": copy.deepcopy(locked_taylor) if isinstance(locked_taylor, dict) else None,
        "taylor_context": (
            copy.deepcopy(locked_taylor.get("taylor_context"))
            if isinstance(locked_taylor, dict)
            else copy.deepcopy(context.get("taylor_context"))
            if isinstance(context.get("taylor_context"), dict)
            else None
        ),
    }


def context_market_time(context: dict[str, Any]) -> datetime | None:
    """Return the best-known market-local timestamp for a stored context payload."""
    if not isinstance(context, dict):
        return None
    parsed = parse_timestamp_value(context.get("timestamp"))
    if parsed is None:
        parsed = parse_timestamp_value(context.get("received_at"))
    if parsed is None:
        return None
    return parsed.astimezone(LOCAL_MARKET_TIMEZONE)


def should_lock_session_liquidity_context(context: dict[str, Any], existing_context: dict[str, Any] | None) -> bool:
    """Lock the first valid 6:15 AM PT-or-later session liquidity table."""
    if not has_valid_liquidity_levels(context):
        return False
    existing_locked = locked_liquidity_context(existing_context)
    if isinstance(existing_locked, dict) and str(existing_context.get("session_date") or "") == str(context.get("session_date") or ""):
        return False
    market_time = context_market_time(context)
    if market_time is None:
        return False
    return (market_time.hour, market_time.minute) >= (SESSION_LIQUIDITY_LOCK_HOUR, SESSION_LIQUIDITY_LOCK_MINUTE)


def should_lock_session_taylor_context(context: dict[str, Any], existing_context: dict[str, Any] | None) -> bool:
    """Lock the first valid 6:15 AM PT-or-later Taylor context for the session."""
    if not has_valid_taylor_context(context):
        return False
    existing_locked = locked_taylor_context(existing_context)
    if isinstance(existing_locked, dict) and str(existing_context.get("session_date") or "") == str(context.get("session_date") or ""):
        return False
    market_time = context_market_time(context)
    if market_time is None:
        return False
    return (market_time.hour, market_time.minute) >= (SESSION_LIQUIDITY_LOCK_HOUR, SESSION_LIQUIDITY_LOCK_MINUTE)


def merge_session_liquidity_context(existing_context: dict[str, Any] | None, incoming_context: dict[str, Any]) -> dict[str, Any]:
    """Preserve the first locked 6:15 liquidity table and later locked Taylor context."""
    merged = dict(incoming_context)
    merged["last_tv_context_received_at"] = incoming_context.get("received_at")
    merged["last_tv_context_session_date"] = incoming_context.get("session_date")
    merged["last_tv_context_source"] = incoming_context.get("source")
    merged["last_tv_context_version"] = incoming_context.get("version")
    merged["last_tv_context_timestamp"] = incoming_context.get("timestamp")
    merged["last_tv_context_candidate"] = copy.deepcopy(incoming_context)
    if isinstance(incoming_context.get("levels"), dict):
        merged["last_tv_context_levels"] = copy.deepcopy(incoming_context.get("levels"))
    existing_locked = locked_liquidity_context(existing_context)
    existing_locked_taylor = locked_taylor_context(existing_context)
    same_session = isinstance(existing_context, dict) and str(existing_context.get("session_date") or "") == str(incoming_context.get("session_date") or "")

    if isinstance(existing_locked, dict) and same_session:
        merged["levels"] = copy.deepcopy(existing_locked.get("levels"))
        liquidity_map = existing_locked.get("liquidity_map")
        if isinstance(liquidity_map, dict):
            merged["liquidity_map"] = copy.deepcopy(liquidity_map)
        midpoints = existing_locked.get("midpoints")
        if isinstance(midpoints, dict):
            merged["midpoints"] = copy.deepcopy(midpoints)
        exhaustion_boundaries = existing_locked.get("exhaustion_boundaries")
        if isinstance(exhaustion_boundaries, dict):
            merged["exhaustion_boundaries"] = copy.deepcopy(exhaustion_boundaries)
        merged["locked_liquidity_context"] = copy.deepcopy(existing_locked)
        merged["liquidity_context_locked"] = True
        merged["liquidity_context_locked_at"] = existing_context.get("liquidity_context_locked_at") or existing_locked.get("locked_at") or incoming_context.get("received_at")
        merged["liquidity_context_source"] = existing_context.get("liquidity_context_source") or existing_locked.get("source") or incoming_context.get("source")
        merged["session_lock_price"] = existing_locked.get("session_lock_price")
        merged["stack_threshold"] = existing_locked.get("stack_threshold")
        merged["daily_atr14"] = existing_locked.get("daily_atr14")
        authority_error = frozen_liquidity_authority_error(existing_locked)
        merged["liquidity_context_authoritative"] = authority_error is None
        merged["liquidity_context_authority_error"] = authority_error
        merged["locked_liquidity_context"]["authoritative"] = authority_error is None
        merged["locked_liquidity_context"]["authority_error"] = authority_error
        merged["locked"] = True
        if (
            incoming_context.get("force") is True
            and str(incoming_context.get("source") or "") == RANDLE_TAYLOR_MAP_SOURCE
            and has_valid_taylor_context(incoming_context)
        ):
            replacement = {
                "taylor_context": copy.deepcopy(incoming_context.get("taylor_context")),
                "session_date": incoming_context.get("session_date"),
                "locked_at": incoming_context.get("received_at"),
                "source": incoming_context.get("source") or RANDLE_TAYLOR_MAP_SOURCE,
            }
            merged["taylor_context"] = copy.deepcopy(replacement["taylor_context"])
            merged["locked_taylor_context"] = replacement
            merged["taylor_context_locked"] = True
            merged["taylor_context_locked_at"] = replacement["locked_at"]
            merged["taylor_context_source"] = replacement["source"]
        elif isinstance(existing_locked_taylor, dict):
            merged["taylor_context"] = copy.deepcopy(existing_locked_taylor.get("taylor_context"))
            merged["locked_taylor_context"] = copy.deepcopy(existing_locked_taylor)
            merged["taylor_context_locked"] = True
            merged["taylor_context_locked_at"] = existing_context.get("taylor_context_locked_at") or existing_locked_taylor.get("locked_at") or incoming_context.get("received_at")
            merged["taylor_context_source"] = existing_context.get("taylor_context_source") or existing_locked_taylor.get("source") or incoming_context.get("source")
        elif has_valid_taylor_context(incoming_context):
            merged["locked_taylor_context"] = {
                "taylor_context": copy.deepcopy(incoming_context.get("taylor_context")),
                "session_date": incoming_context.get("session_date"),
                "locked_at": incoming_context.get("received_at"),
                "source": incoming_context.get("source") or RANDLE_TAYLOR_MAP_SOURCE,
            }
            merged["taylor_context"] = copy.deepcopy(merged["locked_taylor_context"]["taylor_context"])
            merged["taylor_context_locked"] = True
            merged["taylor_context_locked_at"] = merged["locked_taylor_context"]["locked_at"]
            merged["taylor_context_source"] = merged["locked_taylor_context"]["source"]
        return merged

    if should_lock_session_liquidity_context(incoming_context, existing_context):
        merged["locked_liquidity_context"] = {
            "symbol": incoming_context.get("symbol"),
            "normalized_symbol": incoming_context.get("normalized_symbol"),
            "levels": copy.deepcopy(incoming_context.get("levels")),
            "liquidity_map": copy.deepcopy(incoming_context.get("liquidity_map")) if isinstance(incoming_context.get("liquidity_map"), dict) else public_liquidity_map(incoming_context),
            "session_date": incoming_context.get("session_date"),
            "locked_at": incoming_context.get("received_at"),
            "source": incoming_context.get("source") or "tradingview_level_helper",
            "session_lock_price": incoming_context.get("session_lock_price"),
            "stack_threshold": stack_threshold_from_context(incoming_context),
            "daily_atr14": incoming_context.get("daily_atr14"),
            "midpoints": copy.deepcopy(incoming_context.get("midpoints")) if isinstance(incoming_context.get("midpoints"), dict) else None,
            "exhaustion_boundaries": copy.deepcopy(incoming_context.get("exhaustion_boundaries")) if isinstance(incoming_context.get("exhaustion_boundaries"), dict) else None,
        }
        authority_error = frozen_liquidity_authority_error(merged["locked_liquidity_context"])
        merged["locked_liquidity_context"]["authoritative"] = authority_error is None
        merged["locked_liquidity_context"]["authority_error"] = authority_error
        merged["liquidity_context_locked"] = True
        merged["liquidity_context_locked_at"] = incoming_context.get("received_at")
        merged["liquidity_context_source"] = merged["locked_liquidity_context"]["source"]
        merged["session_lock_price"] = merged["locked_liquidity_context"]["session_lock_price"]
        merged["stack_threshold"] = merged["locked_liquidity_context"]["stack_threshold"]
        merged["daily_atr14"] = merged["locked_liquidity_context"]["daily_atr14"]
        merged["liquidity_context_authoritative"] = authority_error is None
        merged["liquidity_context_authority_error"] = authority_error
        merged["locked"] = True
        if has_valid_taylor_context(incoming_context):
            merged["locked_taylor_context"] = {
                "taylor_context": copy.deepcopy(incoming_context.get("taylor_context")),
                "session_date": incoming_context.get("session_date"),
                "locked_at": incoming_context.get("received_at"),
                "source": incoming_context.get("source") or RANDLE_TAYLOR_MAP_SOURCE,
            }
            merged["taylor_context"] = copy.deepcopy(merged["locked_taylor_context"]["taylor_context"])
            merged["taylor_context_locked"] = True
            merged["taylor_context_locked_at"] = incoming_context.get("received_at")
            merged["taylor_context_source"] = merged["locked_taylor_context"]["source"]
    elif should_lock_session_taylor_context(incoming_context, existing_context):
        merged["locked_taylor_context"] = {
            "taylor_context": copy.deepcopy(incoming_context.get("taylor_context")),
            "session_date": incoming_context.get("session_date"),
            "locked_at": incoming_context.get("received_at"),
            "source": incoming_context.get("source") or RANDLE_TAYLOR_MAP_SOURCE,
        }
        merged["taylor_context"] = copy.deepcopy(merged["locked_taylor_context"]["taylor_context"])
        merged["taylor_context_locked"] = True
        merged["taylor_context_locked_at"] = incoming_context.get("received_at")
        merged["taylor_context_source"] = merged["locked_taylor_context"]["source"]
        if merged.get("liquidity_context_locked") is True or isinstance(existing_locked, dict):
            merged["locked"] = True
    return merged


def build_context(payload: dict[str, Any], force: bool = False) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Normalize an inbound TradingView context payload for session-lock persistence."""
    normalized_symbol = normalize_symbol(payload.get("symbol"))
    if normalized_symbol is None:
        if payload.get("symbol") in (None, ""):
            return None, {"error": "symbol is required"}
        return None, {"error": "unsupported symbol"}

    context: dict[str, Any] = copy.deepcopy(payload)
    context["normalized_symbol"] = normalized_symbol
    context["force"] = force
    source = str(context.get("source") or "").strip()

    supplied_version = context.get("version")
    if context.get("version") == CANONICAL_LIQUIDITY_VERSION or (
        source == CANONICAL_LIQUIDITY_SOURCE
        and supplied_version not in ISOLATED_LEGACY_LIQUIDITY_VERSIONS
    ):
        canonical_levels, canonical_error = validate_canonical_liquidity_payload(payload, normalized_symbol)
        if canonical_error is not None:
            return None, canonical_error
        received_at = parse_timestamp_value(payload.get("timestamp"))
        if received_at is None:
            return None, {"error": "timestamp must be a valid UTC timestamp"}
        context["received_at"] = received_at.isoformat().replace("+00:00", "Z")
        context["session_date"] = str(payload.get("session_date"))
        context["levels"] = canonical_levels
        context["liquidity_map"] = copy.deepcopy(payload["liquidity_map"])
        message_identity, payload_sha = canonical_message_identity(payload, normalized_symbol)
        context["message_identity"] = message_identity
        context["canonical_payload_sha256"] = payload_sha
        context["canonical_validation"] = "PASS"
        structure_error = liquidity_stack_structure_error(context)
        if structure_error is not None:
            return None, structure_error
        return context, None

    if source == RANDLE_TAYLOR_MAP_SOURCE:
        missing_field = missing_required_context_field(payload)
        if missing_field is not None:
            return None, {"error": f"{missing_field} is required"}
        received_at = parse_timestamp_value(payload.get("timestamp"))
        if received_at is None:
            return None, {"error": "timestamp must be a valid ISO string or epoch value"}
        context["received_at"] = received_at.isoformat().replace("+00:00", "Z")
        context["session_date"] = str(payload.get("session_date"))
        liquidity_map = context.get("liquidity_map")
        if not isinstance(liquidity_map, dict):
            return None, {"error": "liquidity_map is required"}
        normalized_levels, level_error = normalize_levels_from_liquidity_map(liquidity_map)
        if level_error is not None:
            return None, level_error
        if not isinstance(context.get("taylor_context"), dict):
            return None, {"error": "taylor_context is required"}
        context["levels"] = normalized_levels
        structure_error = liquidity_stack_structure_error(context)
        if structure_error is not None:
            return None, structure_error
        context["liquidity_map"] = public_liquidity_map(context)
        return context, None

    received_at = parse_timestamp_value(payload.get("timestamp")) or datetime.now(timezone.utc)
    context["received_at"] = received_at.isoformat().replace("+00:00", "Z")
    session_date = payload.get("session_date")
    if session_date is None or (isinstance(session_date, str) and not session_date.strip()):
        session_date = context_session_date(payload.get("timestamp"), fallback=received_at)
    context["session_date"] = str(session_date)
    if source == CANONICAL_LIQUIDITY_SOURCE:
        context["receiver_profile"] = "LEGACY_TRADINGVIEW_LEVEL_HELPER_ISOLATED"
        context["canonical_validation"] = "NOT_CLAIMED"

    if not isinstance(context.get("levels"), dict):
        return None, {"error": "levels is required"}
    structure_error = liquidity_stack_structure_error(context)
    if structure_error is not None:
        return None, structure_error
    context["liquidity_map"] = public_liquidity_map(context)
    return context, None


def _test_payload_level_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return exact received table rows plus an explicit top-to-bottom order."""
    levels = payload.get("levels") if isinstance(payload.get("levels"), dict) else {}
    rows: list[dict[str, Any]] = []
    for payload_index, (raw_name, raw_details) in enumerate(levels.items()):
        if not isinstance(raw_details, dict):
            continue
        name = str(raw_name).strip().upper()
        stack_group = raw_details.get("stack_group")
        stack_groups = raw_details.get("stack_groups")
        if not isinstance(stack_groups, list):
            normalized_group = str(stack_group or "").strip()
            stack_groups = [] if not normalized_group or normalized_group.upper() == "NONE" else [normalized_group]
        rows.append({
            "name": name,
            "price": raw_details.get("price"),
            "status": raw_details.get("status"),
            "stack_group": copy.deepcopy(stack_group),
            "stack_groups": copy.deepcopy(stack_groups),
            "stack_display": raw_details.get("stack_display"),
            "payload_index": payload_index,
        })
    rows.sort(
        key=lambda row: (
            -(_to_float(row.get("price")) if _to_float(row.get("price")) is not None else float("-inf")),
            int(row.get("payload_index") or 0),
            str(row.get("name") or ""),
        )
    )
    for ladder_index, row in enumerate(rows, start=1):
        row["ladder_index"] = ladder_index
    return rows


def _test_explicit_stack_objects(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """Preserve sender-supplied stack objects without normalizing their schema."""
    liquidity_map = payload.get("liquidity_map")
    if isinstance(liquidity_map, dict) and "stacks" in liquidity_map:
        stacks = liquidity_map.get("stacks")
        return (copy.deepcopy(stacks) if isinstance(stacks, list) else []), True
    if "stacks" in payload:
        stacks = payload.get("stacks")
        return (copy.deepcopy(stacks) if isinstance(stacks, list) else []), True
    return [], False


def _test_stack_owner_name(stack: dict[str, Any], index: int) -> str:
    for field in ("id", "stack_group", "name"):
        value = str(stack.get(field) or "").strip()
        if value:
            return value
    return f"STACK {index + 1}"


def _test_stack_members(stack: dict[str, Any]) -> list[str]:
    raw_members = stack.get("members") if isinstance(stack.get("members"), list) else stack.get("components")
    if not isinstance(raw_members, list):
        return []
    return [str(member).strip().upper() for member in raw_members if str(member).strip()]


def _test_payload_owner_ladder(
    rows: list[dict[str, Any]],
    explicit_stacks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Project distinct sender owners for display, including overlapping memberships."""
    rows_by_name = {str(row.get("name") or ""): row for row in rows}
    owners: list[dict[str, Any]] = []
    covered_members: set[str] = set()
    known_owner_names: set[str] = set()

    for index, stack in enumerate(explicit_stacks):
        if not isinstance(stack, dict):
            continue
        owner_name = _test_stack_owner_name(stack, index)
        members = _test_stack_members(stack)
        covered_members.update(members)
        known_owner_names.add(owner_name)
        member_prices = {
            name: rows_by_name[name].get("price")
            for name in members
            if name in rows_by_name
        }
        prices = [value for value in (_to_float(price) for price in member_prices.values()) if value is not None]
        owners.append({
            "name": owner_name,
            "side": stack.get("side"),
            "members": members,
            "prices": member_prices,
            "innermost_price": stack.get("innermost_price"),
            "outermost_price": stack.get("outermost_price"),
            "sort_price": max(prices) if prices else None,
            "source": "explicit_stack",
        })

    row_groups: dict[str, list[str]] = {}
    for row in rows:
        if str(row.get("status") or "").strip().upper() not in {"ACTIVE", "REACTIVATED"}:
            continue
        name = str(row.get("name") or "")
        memberships = row.get("stack_groups") if isinstance(row.get("stack_groups"), list) else []
        if not memberships:
            single = str(row.get("stack_group") or "").strip()
            memberships = [] if not single or single.upper() == "NONE" else [single]
        for membership in memberships:
            label = str(membership or "").strip()
            if label:
                row_groups.setdefault(label, []).append(name)

    for label, members in row_groups.items():
        if label in known_owner_names:
            continue
        member_prices = {
            name: rows_by_name[name].get("price")
            for name in members
            if name in rows_by_name
        }
        prices = [value for value in (_to_float(price) for price in member_prices.values()) if value is not None]
        owners.append({
            "name": label,
            "side": "HIGH" if label.upper().startswith("HIGH ") else "LOW" if label.upper().startswith("LOW ") else None,
            "members": members,
            "prices": member_prices,
            "innermost_price": None,
            "outermost_price": None,
            "sort_price": max(prices) if prices else None,
            "source": "level_stack_groups",
        })
        covered_members.update(members)

    for row in rows:
        name = str(row.get("name") or "")
        if name in covered_members or str(row.get("status") or "").strip().upper() not in {"ACTIVE", "REACTIVATED"}:
            continue
        owners.append({
            "name": name,
            "side": None,
            "members": [name],
            "prices": {name: row.get("price")},
            "innermost_price": row.get("price"),
            "outermost_price": row.get("price"),
            "sort_price": _to_float(row.get("price")),
            "source": "individual_level",
        })

    owners.sort(
        key=lambda owner: (
            -(_to_float(owner.get("sort_price")) if _to_float(owner.get("sort_price")) is not None else float("-inf")),
            str(owner.get("name") or ""),
        )
    )
    for ladder_index, owner in enumerate(owners, start=1):
        owner["ladder_index"] = ladder_index
        owner.pop("sort_price", None)
    return owners


def _test_resolved_owner_ladder(session_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    groups = session_context.get("active_groups") if isinstance(session_context, dict) else None
    if not isinstance(groups, list):
        return []
    owners: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        prices = group.get("prices") if isinstance(group.get("prices"), dict) else {}
        numeric_prices = [value for value in (_to_float(price) for price in prices.values()) if value is not None]
        owners.append({
            "name": group.get("name") or group.get("stack_group"),
            "display_name": group.get("display_name"),
            "stack_group": group.get("stack_group"),
            "side": group.get("side"),
            "members": copy.deepcopy(group.get("components") or []),
            "prices": copy.deepcopy(prices),
            "close_boundary": group.get("close_boundary"),
            "extreme_boundary": group.get("extreme_boundary"),
            "sort_price": max(numeric_prices) if numeric_prices else None,
        })
    owners.sort(
        key=lambda owner: (
            -(_to_float(owner.get("sort_price")) if _to_float(owner.get("sort_price")) is not None else float("-inf")),
            str(owner.get("name") or ""),
        )
    )
    for ladder_index, owner in enumerate(owners, start=1):
        owner["ladder_index"] = ladder_index
        owner.pop("sort_price", None)
    return owners


def _test_semantic_stack_map(stacks: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for index, stack in enumerate(stacks):
        if not isinstance(stack, dict):
            continue
        result[_test_stack_owner_name(stack, index)] = _test_stack_members(stack)
    return result


def _test_payload_to_entry_divergence(
    payload_rows: list[dict[str, Any]],
    explicit_stacks: list[dict[str, Any]],
    explicit_stacks_present: bool,
    contract: dict[str, Any] | None,
    resolved_owners: list[dict[str, Any]],
    processing_error: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if processing_error is not None:
        return {
            "stage": "received_payload_to_entry_agent",
            "path": "normal_entry_agent_ladder_path",
            "reason": processing_error.get("code") or processing_error.get("error") or "entry_agent_rejected_payload",
            "detail": copy.deepcopy(processing_error),
        }
    if not isinstance(contract, dict):
        return {
            "stage": "received_payload_to_entry_agent",
            "path": "entry_agent_resolved_ladder",
            "reason": "resolved_ladder_missing",
        }

    resolved_rows = {
        str(row.get("name") or "").strip().upper(): row
        for row in (contract.get("levels") or [])
        if isinstance(row, dict)
    }
    for source_row in payload_rows:
        name = str(source_row.get("name") or "").strip().upper()
        resolved = resolved_rows.get(name)
        if resolved is None:
            return {
                "stage": "received_payload_to_entry_agent",
                "path": f"levels.{name}",
                "reason": "resolved_level_missing",
            }
        comparisons = {
            "price": (_to_float(source_row.get("price")), _to_float(resolved.get("price"))),
            "status": (str(source_row.get("status") or "").upper(), str(resolved.get("status") or "").upper()),
            "stack_group": (
                str(source_row.get("stack_group") or "NONE").upper(),
                str(resolved.get("stack_group") or "NONE").upper(),
            ),
        }
        for field, (source_value, resolved_value) in comparisons.items():
            if source_value != resolved_value:
                return {
                    "stage": "received_payload_to_entry_agent",
                    "path": f"levels.{name}.{field}",
                    "reason": "value_mismatch",
                    "received_payload": source_value,
                    "entry_agent": resolved_value,
                }

    if explicit_stacks_present:
        received_stack_map = _test_semantic_stack_map(explicit_stacks)
        resolved_stacks = contract.get("stacks") if isinstance(contract.get("stacks"), list) else []
        resolved_stack_map = _test_semantic_stack_map(resolved_stacks)
        if received_stack_map != resolved_stack_map:
            return {
                "stage": "received_payload_to_entry_agent",
                "path": "explicit_stacks",
                "reason": "stack_membership_mismatch",
                "received_payload": received_stack_map,
                "entry_agent": resolved_stack_map,
            }

    for owner in resolved_owners:
        owner_name = str(owner.get("name") or "")
        if " / " in owner_name:
            return {
                "stage": "received_payload_to_entry_agent",
                "path": "resolved_owners",
                "reason": "combined_owner_label",
                "entry_agent": owner_name,
            }
    return None


def build_tv_ladder_validation_projection(
    payload: dict[str, Any],
    context: dict[str, Any] | None = None,
    processing_error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an in-memory, nonauthoritative projection through the normal ladder path."""
    if context is None and processing_error is None:
        context, processing_error = build_context(copy.deepcopy(payload))

    normalized_symbol = normalize_symbol(payload.get("symbol"))
    payload_rows = _test_payload_level_rows(payload)
    explicit_stacks, explicit_stacks_present = _test_explicit_stack_objects(payload)
    payload_owner_ladder = _test_payload_owner_ladder(payload_rows, explicit_stacks)
    session_context: dict[str, Any] | None = None
    contract: dict[str, Any] | None = None
    resolved_owners: list[dict[str, Any]] = []

    if isinstance(context, dict) and processing_error is None:
        test_context = copy.deepcopy(context)
        test_context["locked"] = True
        test_context["context_locked"] = True
        test_context["locked_for_day"] = True
        test_context["liquidity_context_locked"] = True
        test_context["liquidity_context_locked_at"] = context.get("received_at")
        test_context["liquidity_context_source"] = context.get("source")
        session_context = build_session_locked_tv_context(test_context)
        if not isinstance(session_context, dict) or session_context.get("locked") is not True:
            processing_error = {
                "code": "TEST_SESSION_LOCK_PROJECTION_FAILED",
                "error": (
                    session_context.get("error")
                    if isinstance(session_context, dict)
                    else "normal Entry Agent session ladder returned no projection"
                ),
            }
        else:
            locked_liquidity = {
                "levels": copy.deepcopy(test_context.get("levels")),
                "liquidity_map": public_liquidity_map(test_context),
                "session_date": test_context.get("session_date"),
                "locked_at": test_context.get("received_at"),
                "source": test_context.get("source"),
                "session_lock_price": stack_reference_price_from_context(test_context),
                "stack_threshold": stack_threshold_from_context(test_context),
                "daily_atr14": test_context.get("daily_atr14"),
                "midpoints": copy.deepcopy(test_context.get("midpoints")) if isinstance(test_context.get("midpoints"), dict) else {},
                "exhaustion_boundaries": copy.deepcopy(test_context.get("exhaustion_boundaries")) if isinstance(test_context.get("exhaustion_boundaries"), dict) else {},
            }
            raw_context = copy.deepcopy(test_context)
            raw_context["locked_liquidity_context"] = locked_liquidity
            snapshot = {
                "raw_tv_context": raw_context,
                "session_liquidity_context": session_context,
            }
            contract = frozen_session_contract_payload(snapshot, None, None)
            source_levels = payload.get("levels") if isinstance(payload.get("levels"), dict) else {}
            for row in contract.get("levels", []):
                if not isinstance(row, dict):
                    continue
                source_details = source_levels.get(str(row.get("name") or ""))
                if not isinstance(source_details, dict):
                    continue
                row["stack_groups"] = copy.deepcopy(source_details.get("stack_groups")) if isinstance(source_details.get("stack_groups"), list) else []
                row["stack_display"] = source_details.get("stack_display")
            contract_levels = contract.get("levels") if isinstance(contract.get("levels"), list) else []
            contract_levels.sort(
                key=lambda row: (
                    -(_to_float(row.get("price")) if isinstance(row, dict) and _to_float(row.get("price")) is not None else float("-inf")),
                    str(row.get("name") or "") if isinstance(row, dict) else "",
                )
            )
            for ladder_index, row in enumerate(contract_levels, start=1):
                if isinstance(row, dict):
                    row["ladder_index"] = ladder_index
            resolved_owners = _test_resolved_owner_ladder(session_context)

    first_divergence = _test_payload_to_entry_divergence(
        payload_rows,
        explicit_stacks,
        explicit_stacks_present,
        contract,
        resolved_owners,
        processing_error,
    )
    received_at = context.get("received_at") if isinstance(context, dict) else utc_timestamp()
    session_date = (
        context.get("session_date")
        if isinstance(context, dict)
        else payload.get("session_date") or context_session_date(payload.get("timestamp"))
    )
    return {
        "label": TV_LADDER_VALIDATION_LABEL,
        "mode": "test_unverified",
        "symbol": normalized_symbol,
        "session_date": session_date,
        "captured_at": utc_timestamp(),
        "source_payload_timestamp": payload.get("timestamp"),
        "entry_agent_received_at": received_at,
        "source": payload.get("source"),
        "version": payload.get("version"),
        "received_payload": copy.deepcopy(payload),
        "received_table": {
            "levels": payload_rows,
            "explicit_stacks": explicit_stacks,
            "explicit_stacks_present": explicit_stacks_present,
            "resolved_owner_ladder": payload_owner_ladder,
            "midpoints": copy.deepcopy(payload.get("midpoints")) if isinstance(payload.get("midpoints"), dict) else {},
            "exhaustion_boundaries": copy.deepcopy(payload.get("exhaustion_boundaries")) if isinstance(payload.get("exhaustion_boundaries"), dict) else {},
        },
        "entry_agent_processing": {
            "path": "build_context -> build_session_locked_tv_context -> frozen_session_contract_payload",
            "accepted": processing_error is None,
            "error": copy.deepcopy(processing_error),
        },
        "entry_agent_resolved": {
            "session_lock": copy.deepcopy(session_context),
            "contract": copy.deepcopy(contract),
            "resolved_owners": resolved_owners,
            "ladder_order": copy.deepcopy(resolved_owners),
        } if processing_error is None else None,
        "comparisons": {
            "tradingview_table_to_received_payload": {
                "status": "PENDING_OPERATOR_VISUAL_VERIFICATION",
                "reason": "the webhook preserves the exact payload but cannot inspect the TradingView table pixels",
            },
            "received_payload_to_entry_agent": {
                "status": "MATCH" if first_divergence is None else "DIVERGED",
                "first_divergence": copy.deepcopy(first_divergence),
            },
            "entry_agent_to_command_center": {
                "status": "PENDING_CLIENT_RENDER",
                "reason": "Command Center must render entry_agent_resolved directly without owner-label coalescing",
            },
        },
        "first_divergence": copy.deepcopy(first_divergence),
        "authorizes_entries": False,
        "alters_live_trade_state": False,
        "writes_canonical_persistence": False,
        "trade_ready": False,
        "trade_ready_reason": "all three projections require agreement; TradingView table verification is still pending",
    }


def _test_payload_is_locked(payload: dict[str, Any], context: dict[str, Any] | None) -> bool:
    for field in ("session_locked", "is_premarket_end", "liquidity_context_locked", "locked", "context_locked", "locked_for_day"):
        if parse_boolish(payload.get(field)):
            return True
    market_time = context_market_time(context) if isinstance(context, dict) else None
    return bool(
        market_time is not None
        and (market_time.hour, market_time.minute) >= (SESSION_LIQUIDITY_LOCK_HOUR, SESSION_LIQUIDITY_LOCK_MINUTE)
    )


def capture_tv_ladder_validation_projection(
    payload: dict[str, Any],
    context: dict[str, Any] | None = None,
    processing_error: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Capture only an in-memory test view; never write canonical or lifecycle state."""
    if str(payload.get("source") or "").strip() != "tradingview_level_helper":
        return None
    normalized_symbol = normalize_symbol(payload.get("symbol"))
    if normalized_symbol not in {"NQ", "YM"}:
        return None
    projection = build_tv_ladder_validation_projection(payload, context, processing_error)
    is_locked = _test_payload_is_locked(payload, context)
    projection["capture_phase"] = "FIRST_LOCKED" if is_locked else "LATEST_PREOPEN"
    projection["is_locked_payload"] = is_locked
    prior = TV_LADDER_VALIDATION_BY_SYMBOL.get(normalized_symbol)
    record = copy.deepcopy(prior) if isinstance(prior, dict) else {}
    record["latest"] = projection
    first_locked = record.get("first_locked") if isinstance(record.get("first_locked"), dict) else None
    if is_locked and (
        not isinstance(first_locked, dict)
        or str(first_locked.get("session_date") or "") != str(projection.get("session_date") or "")
    ):
        record["first_locked"] = copy.deepcopy(projection)
    TV_LADDER_VALIDATION_BY_SYMBOL[normalized_symbol] = record
    return projection


def build_levels(context: dict[str, Any]) -> dict[str, Any]:
    """Build the flat EntryAgent levels schema from TradingView context."""
    levels = {key: None for key in LEVELS_SCHEMA_KEYS}
    nested_levels = context.get("levels") if isinstance(context.get("levels"), dict) else {}
    for field in LEVEL_FIELDS:
        raw_value = context.get(field)
        if raw_value is None:
            raw_value = context.get(f"{field}_price")
        if raw_value is None:
            nested_value = nested_levels.get(field)
            if isinstance(nested_value, dict):
                raw_value = nested_value.get("price")
        value, _error = parse_optional_number(raw_value, field)
        levels[field] = value
    return levels


TV_CONTEXT_DIAGNOSTIC_RECEIPT: dict[str, Any] = {}


def internal_relay_auth_error() -> tuple[dict[str, Any], int] | None:
    expected = os.getenv(INTERNAL_RELAY_TOKEN_ENV, "")
    if not expected:
        return {"error": "internal relay authentication is not configured"}, 503
    supplied = request.headers.get(INTERNAL_RELAY_HEADER, "")
    if not supplied or not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
        return {"error": "internal relay authentication failed"}, 401
    return None


def canonical_acceptance_ledger_path() -> Path:
    configured = os.getenv("TV_CONTEXT_ACCEPTANCE_LEDGER_PATH", "").strip()
    return Path(configured) if configured else local_or_shared_path(
        BASE_DIR,
        "tv_context_acceptance_ledger.json",
        shared_prefix="entry_agent",
    )


def load_canonical_acceptance_ledger() -> dict[str, Any]:
    path = canonical_acceptance_ledger_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {"schema_version": "tv_context_acceptance_v1", "symbols": {}}
    if not isinstance(data, dict) or not isinstance(data.get("symbols"), dict):
        return {"schema_version": "tv_context_acceptance_v1", "symbols": {}}
    return data


def write_canonical_acceptance_ledger(ledger: dict[str, Any]) -> None:
    path = canonical_acceptance_ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(ledger, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def persisted_canonical_acceptance(symbol: str) -> dict[str, Any] | None:
    """Return the newest ledger or normalized-context identity after a restart."""
    candidates: list[tuple[str, datetime, int, dict[str, Any]]] = []
    ledger = load_canonical_acceptance_ledger()
    ledger_row = ledger.get("symbols", {}).get(symbol)
    if isinstance(ledger_row, dict):
        timestamp = parse_timestamp_value(ledger_row.get("timestamp"))
        if timestamp is not None:
            candidates.append((str(ledger_row.get("session_date") or ""), timestamp, 0, ledger_row))
    try:
        context_store = json.loads(TV_CONTEXT_BY_SYMBOL_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        context_store = {}
    stored = context_store.get("symbols", {}).get(symbol) if isinstance(context_store, dict) else None
    if isinstance(stored, dict) and stored.get("source") == CANONICAL_LIQUIDITY_SOURCE:
        timestamp = parse_timestamp_value(stored.get("timestamp"))
        if timestamp is not None and stored.get("message_identity"):
            candidates.append((str(stored.get("session_date") or ""), timestamp, 1, stored))
    return max(candidates, key=lambda item: item[:3])[3] if candidates else None


def canonical_delivery_disposition(context: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """Enforce identity, replay, session freshness, and source ordering across restarts."""
    if context.get("source") != CANONICAL_LIQUIDITY_SOURCE:
        return "ACCEPT", None
    symbol = str(context.get("normalized_symbol") or "")
    latest = persisted_canonical_acceptance(symbol)
    if not isinstance(latest, dict):
        return "ACCEPT", None
    identity = str(context.get("message_identity") or "")
    payload_sha = str(context.get("canonical_payload_sha256") or "")
    if identity and identity == str(latest.get("message_identity") or ""):
        return "DUPLICATE", None
    incoming_session = str(context.get("session_date") or "")
    latest_session = str(latest.get("session_date") or "")
    if incoming_session < latest_session:
        return "STALE", {"error": "canonical payload belongs to an older session", "disposition": "STALE"}
    incoming_time = parse_timestamp_value(context.get("timestamp"))
    latest_time = parse_timestamp_value(latest.get("timestamp"))
    if incoming_session == latest_session and incoming_time is not None and latest_time is not None:
        if incoming_time < latest_time:
            return "OUT_OF_ORDER", {"error": "canonical payload is older than accepted state", "disposition": "OUT_OF_ORDER"}
        if incoming_time == latest_time and payload_sha != str(latest.get("canonical_payload_sha256") or ""):
            return "ALTERED_SAME_TIMESTAMP", {
                "error": "canonical timestamp was reused with altered payload bytes",
                "disposition": "ALTERED_SAME_TIMESTAMP",
            }
    return "ACCEPT", None


def record_canonical_acceptance(context: dict[str, Any]) -> None:
    if context.get("source") != CANONICAL_LIQUIDITY_SOURCE:
        return
    ledger = load_canonical_acceptance_ledger()
    symbols = ledger.setdefault("symbols", {})
    symbols[str(context["normalized_symbol"])] = {
        "message_identity": context.get("message_identity"),
        "canonical_payload_sha256": context.get("canonical_payload_sha256"),
        "timestamp": context.get("timestamp"),
        "session_date": context.get("session_date"),
        "accepted_at": utc_timestamp(),
    }
    write_canonical_acceptance_ledger(ledger)


@app.post("/webhook/tv-context")
@entry_state_transaction
def receive_tv_context() -> tuple[Any, int]:
    """Receive full TradingView table context for EntryAgent."""
    auth_error = internal_relay_auth_error()
    if auth_error is not None:
        body, status = auth_error
        return jsonify(body), status
    try:
        payload = json.loads(request.get_data(cache=True, as_text=True), object_pairs_hook=_duplicate_rejecting_object)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return jsonify({"error": f"invalid JSON object: {exc}"}), 400
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid JSON object"}), 400

    if str(payload.get("source") or "") == "startup_liquidity_relay_probe":
        receipt_id = str(payload.get("receipt_id") or "").strip()
        if not receipt_id or len(receipt_id) > 128:
            return jsonify({"ok": False, "error": "valid receipt_id is required"}), 400
        receipt = {
            "receipt_id": receipt_id,
            "received_at": utc_timestamp(),
            "sent_at": payload.get("sent_at"),
            "remote_addr": request.remote_addr,
            "source": "startup_liquidity_relay_probe",
        }
        TV_CONTEXT_DIAGNOSTIC_RECEIPT.clear()
        TV_CONTEXT_DIAGNOSTIC_RECEIPT.update(receipt)
        return jsonify({
            "ok": True,
            "source": "startup_liquidity_relay_probe",
            "price_truth": "Rithmic",
            "receipt_id": receipt_id,
            "received_at": receipt["received_at"],
            "liquidity_state_changed": False,
        }), 200

    force = parse_boolish(request.args.get("force"))
    if not force:
        force = parse_boolish(payload.get("force"))

    preview = {key: payload.get(key) for key in list(payload)[:2]}
    print(f"ENTRY TV CONTEXT incoming_preview={preview}")

    context, error = build_context(payload, force=force)
    if error is not None:
        try:
            capture_tv_ladder_validation_projection(payload, processing_error=error)
        except Exception as exc:
            print(f"ENTRY TV LADDER TEST projection_error={type(exc).__name__}: {exc}")
        try:
            append_rejected_context_event(payload, request.remote_addr, error)
        except OSError as exc:
            return jsonify({
                "error": "rejected TradingView payload could not be archived",
                "rejection": error,
                "persistence_error": str(exc),
            }), 503
        return jsonify(error), 400

    delivery_disposition, delivery_error = canonical_delivery_disposition(context)
    if delivery_disposition == "DUPLICATE":
        return jsonify({
            "ok": True,
            "normalized_symbol": context["normalized_symbol"],
            "message_identity": context.get("message_identity"),
            "delivery_disposition": "DUPLICATE_NOOP",
            "liquidity_state_changed": False,
        }), 200
    if delivery_error is not None:
        try:
            append_rejected_context_event(payload, request.remote_addr, delivery_error)
        except OSError as exc:
            return jsonify({"error": "ordering rejection could not be archived", "persistence_error": str(exc)}), 503
        return jsonify(delivery_error), 409

    try:
        capture_tv_ladder_validation_projection(payload, context=context)
    except Exception as exc:
        print(f"ENTRY TV LADDER TEST projection_error={type(exc).__name__}: {exc}")

    existing_context = stored_context_by_root().get(str(context["normalized_symbol"]))
    if (
        str(context.get("source") or "") == RANDLE_TAYLOR_MAP_SOURCE
        and not force
        and isinstance(existing_context, dict)
        and isinstance(locked_taylor_context(existing_context), dict)
        and str(existing_context.get("session_date") or "") == str(context.get("session_date") or "")
    ):
        return jsonify({
            "error": f"session context already stored for {context['normalized_symbol']} on {context.get('session_date')}; resend requires force=true",
            "normalized_symbol": context["normalized_symbol"],
            "session_date": context.get("session_date"),
        }), 409

    replacement_state: dict[str, Any] | None = None
    replacement_event: dict[str, Any] | None = None
    merge_existing_context = existing_context
    if should_replace_stale_locked_liquidity_context(existing_context, context):
        replacement_state = _read_json(ENTRY_AGENT_STATE_PATH)
        replacement_state, cleared_fields = clear_symbol_pathway_state(replacement_state, str(context["normalized_symbol"]))
        previous_locked = locked_liquidity_context(existing_context)
        previous_session_date = _context_session_date(existing_context)
        incoming_session_date = str(context.get("session_date") or "")
        replacement_reason = (
            "newer_locked_session_rollover"
            if previous_session_date and incoming_session_date and previous_session_date != incoming_session_date
            else "newer_locked_material_level_change"
        )
        replacement_event = {
            "timestamp": utc_timestamp(),
            "event": "stale_liquidity_lock_replaced_from_newer_tv_context",
            "symbol": str(context["normalized_symbol"]),
            "session_date": incoming_session_date,
            "previous_session_date": previous_session_date,
            "incoming_session_date": incoming_session_date,
            "replacement_reason": replacement_reason,
            "previous_locked_at": (
                existing_context.get("liquidity_context_locked_at")
                or (previous_locked.get("locked_at") if isinstance(previous_locked, dict) else None)
                or existing_context.get("received_at")
            ),
            "incoming_locked_at": context.get("liquidity_context_locked_at") or context.get("received_at"),
            "cleared_fields": cleared_fields,
            "previous_levels": _normalized_level_snapshot((previous_locked or {}).get("levels") if isinstance(previous_locked, dict) else None),
            "incoming_levels": _normalized_level_snapshot(context.get("levels")),
        }
        append_operator_audit_event(replacement_state, str(context["normalized_symbol"]), replacement_event)
        append_operator_route_audit(copy.deepcopy(replacement_event))
        merge_existing_context = None

    stored_payload = merge_session_liquidity_context(merge_existing_context, context)
    stored_structure_error = liquidity_stack_structure_error(stored_payload)
    if stored_structure_error is not None:
        merged_rejection = {
            **stored_structure_error,
            "stage": "post_merge_locked_context_validation",
        }
        try:
            append_rejected_context_event(payload, request.remote_addr, merged_rejection)
        except OSError as exc:
            return jsonify({
                "error": "invalid merged TradingView authority could not be archived",
                "rejection": merged_rejection,
                "persistence_error": str(exc),
            }), 503
        return jsonify(merged_rejection), 409
    levels = build_levels(stored_payload)
    persistence_error = None
    lifecycle_processing_error = None
    lifecycle_processed_candle = None
    try:
        safe_write_json(LEVELS_PATH, levels)
        safe_write_json(TV_CONTEXT_PATH, stored_payload)
        upsert_symbol_json(LEVELS_BY_SYMBOL_PATH, str(context["normalized_symbol"]), levels)
        upsert_symbol_json(TV_CONTEXT_BY_SYMBOL_PATH, str(context["normalized_symbol"]), stored_payload)
        if isinstance(replacement_state, dict):
            symbol_state = _target_symbol_state(replacement_state, str(context["normalized_symbol"]))
            if isinstance(symbol_state, dict):
                symbol_state["session_liquidity_context"] = build_session_locked_tv_context(stored_payload)
            with ENTRY_STATE_LOCK:
                _write_json(ENTRY_AGENT_STATE_PATH, replacement_state)
        append_context_event(stored_payload, request.remote_addr, received_payload=payload)
        record_canonical_acceptance(context)
        LATEST_TV_CONTEXT_BY_SYMBOL[str(context["normalized_symbol"])] = stored_payload
    except OSError as exc:
        persistence_error = str(exc)
        print(f"ENTRY TV CONTEXT persistence_error={persistence_error}")
    normalized_symbol = str(context["normalized_symbol"])
    if persistence_error is None and normalized_symbol in {"NQ", "YM"}:
        try:
            lifecycle_snapshot = run_once(normalized_symbol, persist=True)
            lifecycle_processed_candle = lifecycle_snapshot.get("latest_bar_time")
        except Exception as exc:
            lifecycle_processing_error = f"{type(exc).__name__}: {exc}"
            print(f"ENTRY TV CONTEXT lifecycle_processing_error={lifecycle_processing_error}")
    return jsonify({
        "ok": True,
        "normalized_symbol": context["normalized_symbol"],
        "context": stored_payload,
        "persistence_error": persistence_error,
        "lifecycle_processed_candle": lifecycle_processed_candle,
        "lifecycle_processing_error": lifecycle_processing_error,
        "message_identity": context.get("message_identity"),
        "delivery_disposition": "ACCEPTED",
    }), 503 if persistence_error or lifecycle_processing_error else 200


@app.get("/debug/tv-context-receipt")
def debug_tv_context_receipt() -> tuple[Any, int]:
    """Expose the last non-state-mutating startup relay receipt."""
    return jsonify({
        "ok": True,
        "source": "startup_liquidity_relay_probe",
        "price_truth": "Rithmic",
        "receipt": dict(TV_CONTEXT_DIAGNOSTIC_RECEIPT),
    }), 200


@app.route("/debug/tv-ladder-validation", methods=["GET", "OPTIONS"])
def debug_tv_ladder_validation() -> tuple[Any, int]:
    """Expose isolated pre-open ladder projections for Command Center test mode."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    symbols = []
    for root in ("YM", "NQ"):
        record = TV_LADDER_VALIDATION_BY_SYMBOL.get(root)
        latest = record.get("latest") if isinstance(record, dict) and isinstance(record.get("latest"), dict) else None
        first_locked = record.get("first_locked") if isinstance(record, dict) and isinstance(record.get("first_locked"), dict) else None
        selected = first_locked if (
            isinstance(first_locked, dict)
            and isinstance(latest, dict)
            and str(first_locked.get("session_date") or "") == str(latest.get("session_date") or "")
        ) else latest
        if not isinstance(selected, dict):
            symbols.append({
                "symbol": root,
                "available": False,
                "label": TV_LADDER_VALIDATION_LABEL,
                "trade_ready": False,
                "trade_ready_reason": "no TradingView level-helper payload captured since Entry Agent start",
            })
            continue
        projected = copy.deepcopy(selected)
        projected["available"] = True
        projected["first_locked_captured"] = isinstance(first_locked, dict)
        symbols.append(projected)
    return jsonify({
        "ok": True,
        "label": TV_LADDER_VALIDATION_LABEL,
        "mode": "test_unverified",
        "authorizes_entries": False,
        "alters_live_trade_state": False,
        "writes_canonical_persistence": False,
        "symbols": symbols,
    }), 200


@app.get("/context")
def get_context() -> tuple[Any, int]:
    """Return the latest persisted TradingView context."""
    requested = request.args.get("symbol")
    if requested:
        normalized = normalize_symbol(requested)
        if not normalized:
            return jsonify({"context": None}), 200
        context = stored_context_by_root().get(normalized)
        return jsonify(public_market_context(context) if isinstance(context, dict) else {"context": None}), 200
    if not TV_CONTEXT_PATH.exists():
        return jsonify({"context": None}), 200

    try:
        with TV_CONTEXT_PATH.open("r", encoding="utf-8") as file:
            payload = json.load(file)
            return jsonify(public_market_context(payload) if isinstance(payload, dict) else payload), 200
    except json.JSONDecodeError:
        return jsonify({"error": "stored context is invalid JSON"}), 500


@app.get("/debug/tv-context")
def debug_tv_context() -> tuple[Any, int]:
    """Return latest TradingView level-helper context by symbol; not price truth."""
    stored = {}
    if TV_CONTEXT_BY_SYMBOL_PATH.exists():
        try:
            with TV_CONTEXT_BY_SYMBOL_PATH.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            if isinstance(payload, dict) and isinstance(payload.get("symbols"), dict):
                stored = payload["symbols"]
        except (json.JSONDecodeError, OSError):
            stored = {}

    symbols = dict(stored)
    symbols.update(LATEST_TV_CONTEXT_BY_SYMBOL)
    requested_symbol = normalize_symbol(request.args.get("symbol"))
    if requested_symbol:
        symbols = {requested_symbol: symbols.get(requested_symbol)}

    return jsonify({
        "ok": True,
        "source": "tradingview_level_helper",
        "price_truth": "Rithmic",
        "symbols": symbols,
    }), 200


def stored_context_by_root() -> dict[str, Any]:
    """Return latest persisted TradingView context by normalized root."""
    stored: dict[str, Any] = {}
    if TV_CONTEXT_BY_SYMBOL_PATH.exists():
        try:
            with TV_CONTEXT_BY_SYMBOL_PATH.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            if isinstance(payload, dict) and isinstance(payload.get("symbols"), dict):
                stored.update(payload["symbols"])
        except (json.JSONDecodeError, OSError):
            pass
    stored.update(LATEST_TV_CONTEXT_BY_SYMBOL)
    return stored


def stored_level_price(context: dict[str, Any] | None, level_name: str) -> Any:
    """Return one nested TradingView level price from stored context."""
    if not isinstance(context, dict):
        return None
    levels = context.get("levels")
    if not isinstance(levels, dict):
        return None
    details = levels.get(level_name)
    if isinstance(details, dict):
        return details.get("price")
    return None


@app.get("/debug/entry-liquidity")
def debug_entry_liquidity() -> tuple[Any, int]:
    """Show per-root TV table and active-liquidity source data for status debugging."""
    raw_symbols = request.args.get("symbols") or request.args.get("symbol") or "NQ,YM"
    stored = stored_context_by_root()
    records = []
    seen_roots: set[str] = set()
    for item in raw_symbols.split(","):
        requested = item.strip().upper()
        if not requested:
            continue
        normalized = normalize_symbol(requested)
        if not normalized or normalized in seen_roots:
            continue
        seen_roots.add(normalized)
        context = stored.get(normalized)
        status = build_entry_status(requested)
        records.append(
            {
                "requested_symbol": requested,
                "normalized_root": normalized,
                "stored_pml": stored_level_price(context, "PML"),
                "source_payload_symbol": context.get("symbol") if isinstance(context, dict) else None,
                "source_payload_ticker": (
                    context.get("ticker")
                    or context.get("tickerid")
                    or context.get("syminfo_ticker")
                    if isinstance(context, dict)
                    else None
                ),
                "active_liquidity_name": status.get("active_liquidity_name"),
                "active_liquidity_price": status.get("active_liquidity_price"),
            }
        )
    return jsonify({"ok": True, "symbols": records}), 200


@app.get("/debug/entry-log")
def debug_entry_log() -> tuple[Any, int]:
    """Return recent read-only Entry Agent decision log records."""
    try:
        limit = int(request.args.get("limit") or 200)
    except (TypeError, ValueError):
        limit = 200
    limit = max(1, min(limit, 1000))
    records = tail_entry_decision_log(limit)
    return jsonify({
        "ok": True,
        "path": str(ENTRY_DECISIONS_LOG_PATH),
        "limit": limit,
        "count": len(records),
        "records": records,
    }), 200


@app.get("/entry/reasoning_log")
def entry_reasoning_log() -> tuple[Any, int]:
    """Return daily Entry Agent reasoning records for chart review."""
    raw_symbols = request.args.get("symbols") or request.args.get("symbol") or "NQ,YM"
    symbols = {
        normalized
        for item in raw_symbols.split(",")
        if (normalized := normalize_symbol(item.strip()))
    }
    if not symbols:
        return jsonify({"ok": False, "error": "no supported symbols requested"}), 400
    date_text = request.args.get("date")
    try:
        limit = int(request.args.get("limit") or 2000)
    except (TypeError, ValueError):
        limit = 2000
    limit = max(1, min(limit, 10000))
    records = read_entry_reasoning_log(symbols, date_text, limit)
    return jsonify({
        "ok": True,
        "path": str(reasoning_log_path(date_text)),
        "symbols": sorted(symbols),
        "limit": limit,
        "count": len(records),
        "records": records,
    }), 200


@app.post("/operator/liquidity-lock/reconstruct-from-latest-canonical")
@entry_state_transaction
def operator_reconstruct_liquidity_lock() -> tuple[Any, int]:
    """Explicitly replace one invalid legacy lock from a validated current-session v14 candidate."""
    payload = request.get_json(silent=True)
    request_timestamp = utc_timestamp()
    raw_symbol = payload.get("symbol") if isinstance(payload, dict) else None
    normalized_symbol = normalize_symbol(raw_symbol)
    reason = str(payload.get("reason") or "") if isinstance(payload, dict) else ""
    request_event = {
        "timestamp": request_timestamp,
        "event": "canonical_liquidity_lock_reconstruction_requested",
        "symbol": normalized_symbol or (str(raw_symbol).upper() if raw_symbol is not None else None),
        "reason": reason or None,
        "status": "received",
    }
    append_operator_route_audit(request_event)

    def fail(error: str, status_code: int, **details: Any) -> tuple[Any, int]:
        append_operator_route_audit({
            "timestamp": utc_timestamp(),
            "event": "canonical_liquidity_lock_reconstruction_completed",
            "symbol": normalized_symbol or (str(raw_symbol).upper() if raw_symbol is not None else None),
            "reason": reason or None,
            "status": "failure",
            "failure_reason": error,
            **copy.deepcopy(details),
        })
        return jsonify({"ok": False, "error": error, **details}), status_code

    if not isinstance(payload, dict):
        return fail("invalid_json_object", 400)
    if normalized_symbol not in {"NQ", "YM"}:
        return fail("unsupported_symbol", 400)
    if reason != CANONICAL_LOCK_RECONSTRUCTION_REASON:
        return fail("governed_reconstruction_reason_required", 400)

    executor_snapshot = fetch_local_json(EXECUTOR_SYNC_SNAPSHOT_URL, timeout=2.0)
    if executor_snapshot.get("ok") is not True or not isinstance(executor_snapshot.get("symbols"), dict):
        return fail("executor_safety_snapshot_unavailable", 503)
    execution_state = summarize_active_execution_state(executor_snapshot)
    if execution_state["has_open_execution_state"]:
        return fail("open_execution_state_present", 409, execution_state=execution_state)

    context_store = _read_json(TV_CONTEXT_BY_SYMBOL_PATH)
    original_context_store = copy.deepcopy(context_store)
    context_symbols = context_store.get("symbols") if isinstance(context_store.get("symbols"), dict) else {}
    stored_symbol_context = context_symbols.get(normalized_symbol)
    if not isinstance(stored_symbol_context, dict):
        return fail("latest_tv_context_missing", 404)

    state = _read_json(ENTRY_AGENT_STATE_PATH)
    original_state = copy.deepcopy(state)
    symbol_state = _target_symbol_state(state, normalized_symbol)
    if not isinstance(symbol_state, dict):
        return fail("entry_agent_state_missing_symbol", 409)
    session_lock = symbol_state.get("session_liquidity_context")
    if not isinstance(session_lock, dict):
        return fail("frozen_lock_missing", 409)

    reconstruction_time = utc_timestamp()
    rebuilt_lock, reconstruction_error = _reconstruct_frozen_lock_from_latest_canonical(
        normalized_symbol,
        stored_symbol_context,
        session_lock,
        reconstructed_at=reconstruction_time,
    )
    if reconstruction_error is not None:
        error_name = str(reconstruction_error.get("error") or "canonical_lock_reconstruction_failed")
        return fail(error_name, 409, detail=reconstruction_error)

    rebuilt_tv_context = rebuilt_lock.get("tv_context")
    candidate = stored_symbol_context.get("last_tv_context_candidate")
    if not isinstance(rebuilt_tv_context, dict) or not isinstance(candidate, dict):
        return fail("rebuilt_canonical_lock_missing_context", 409)

    locked_context = {
        "symbol": rebuilt_tv_context.get("symbol"),
        "normalized_symbol": rebuilt_tv_context.get("normalized_symbol"),
        "levels": copy.deepcopy(rebuilt_tv_context.get("levels")),
        "liquidity_map": public_liquidity_map(rebuilt_tv_context),
        "session_date": rebuilt_tv_context.get("session_date"),
        "locked_at": reconstruction_time,
        "source": rebuilt_tv_context.get("source"),
        "version": rebuilt_tv_context.get("version"),
        "source_timestamp": rebuilt_tv_context.get("timestamp"),
        "source_received_at": rebuilt_tv_context.get("received_at"),
        "session_lock_price": rebuilt_tv_context.get("session_lock_price"),
        "stack_threshold": rebuilt_tv_context.get("stack_threshold"),
        "daily_atr14": rebuilt_tv_context.get("daily_atr14"),
        "midpoints": copy.deepcopy(rebuilt_tv_context.get("midpoints")) if isinstance(rebuilt_tv_context.get("midpoints"), dict) else None,
        "exhaustion_boundaries": copy.deepcopy(rebuilt_tv_context.get("exhaustion_boundaries")) if isinstance(rebuilt_tv_context.get("exhaustion_boundaries"), dict) else None,
        "authoritative": True,
        "authority_error": None,
        "lock_reconstruction": copy.deepcopy(rebuilt_tv_context.get("lock_reconstruction")),
    }
    reconstructed_stored_context = copy.deepcopy(stored_symbol_context)
    reconstructed_stored_context["levels"] = copy.deepcopy(locked_context["levels"])
    reconstructed_stored_context["liquidity_map"] = copy.deepcopy(locked_context["liquidity_map"])
    reconstructed_stored_context["midpoints"] = copy.deepcopy(locked_context["midpoints"])
    reconstructed_stored_context["exhaustion_boundaries"] = copy.deepcopy(locked_context["exhaustion_boundaries"])
    reconstructed_stored_context["locked_liquidity_context"] = locked_context
    reconstructed_stored_context["liquidity_context_locked"] = True
    reconstructed_stored_context["liquidity_context_locked_at"] = reconstruction_time
    reconstructed_stored_context["liquidity_context_source"] = CANONICAL_LIQUIDITY_SOURCE
    reconstructed_stored_context["liquidity_context_authoritative"] = True
    reconstructed_stored_context["liquidity_context_authority_error"] = None
    reconstructed_stored_context["session_lock_price"] = locked_context["session_lock_price"]
    reconstructed_stored_context["stack_threshold"] = locked_context["stack_threshold"]
    reconstructed_stored_context["daily_atr14"] = locked_context["daily_atr14"]
    reconstructed_stored_context["locked"] = True

    state, cleared_fields = clear_symbol_pathway_state(state, normalized_symbol)
    symbol_state = _target_symbol_state(state, normalized_symbol)
    if not isinstance(symbol_state, dict):
        return fail("entry_agent_state_missing_symbol_after_clear", 409)
    symbol_state["session_liquidity_context"] = rebuilt_lock
    audit_event = {
        "timestamp": reconstruction_time,
        "event": "canonical_liquidity_lock_reconstructed",
        "symbol": normalized_symbol,
        "session_date": rebuilt_tv_context.get("session_date"),
        "reason": reason,
        "previous_locked_at": (rebuilt_tv_context.get("lock_reconstruction") or {}).get("previous_locked_at"),
        "source_timestamp": rebuilt_tv_context.get("timestamp"),
        "source_received_at": rebuilt_tv_context.get("received_at"),
        "session_lock_price": rebuilt_tv_context.get("session_lock_price"),
        "stack_threshold": rebuilt_tv_context.get("stack_threshold"),
        "daily_atr14": rebuilt_tv_context.get("daily_atr14"),
        "cleared_fields": cleared_fields,
    }
    append_operator_audit_event(state, normalized_symbol, audit_event)

    context_symbols[normalized_symbol] = reconstructed_stored_context
    context_store["symbols"] = context_symbols
    single_context = _read_json(TV_CONTEXT_PATH)
    original_single_context = copy.deepcopy(single_context)
    write_single_context = (
        isinstance(single_context, dict)
        and str(single_context.get("normalized_symbol") or "").upper() == normalized_symbol
    )
    backup_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backups = {
        "tv_context_by_symbol": timestamped_backup(TV_CONTEXT_BY_SYMBOL_PATH, backup_stamp),
        "entry_agent_state": timestamped_backup(ENTRY_AGENT_STATE_PATH, backup_stamp),
    }
    if write_single_context:
        backups["tv_context"] = timestamped_backup(TV_CONTEXT_PATH, backup_stamp)

    try:
        safe_write_json(TV_CONTEXT_BY_SYMBOL_PATH, context_store)
        if write_single_context:
            safe_write_json(TV_CONTEXT_PATH, reconstructed_stored_context)
        with ENTRY_STATE_LOCK:
            _write_json(ENTRY_AGENT_STATE_PATH, state)
    except OSError as exc:
        restore_errors = []
        try:
            safe_write_json(TV_CONTEXT_BY_SYMBOL_PATH, original_context_store)
        except OSError as restore_exc:
            restore_errors.append(f"tv_context_by_symbol:{restore_exc}")
        if write_single_context:
            try:
                safe_write_json(TV_CONTEXT_PATH, original_single_context)
            except OSError as restore_exc:
                restore_errors.append(f"tv_context:{restore_exc}")
        try:
            with ENTRY_STATE_LOCK:
                _write_json(ENTRY_AGENT_STATE_PATH, original_state)
        except OSError as restore_exc:
            restore_errors.append(f"entry_agent_state:{restore_exc}")
        return fail(
            "canonical_lock_reconstruction_persistence_failed",
            503,
            detail=str(exc),
            restore_errors=restore_errors,
            backups=backups,
        )

    LATEST_TV_CONTEXT_BY_SYMBOL[normalized_symbol] = copy.deepcopy(reconstructed_stored_context)
    append_operator_route_audit({
        "timestamp": utc_timestamp(),
        "event": "canonical_liquidity_lock_reconstruction_completed",
        "symbol": normalized_symbol,
        "reason": reason,
        "status": "success",
        "failure_reason": None,
        "session_date": rebuilt_tv_context.get("session_date"),
        "source_timestamp": rebuilt_tv_context.get("timestamp"),
        "reconstructed_at": reconstruction_time,
    })
    return jsonify({
        "ok": True,
        "symbol": normalized_symbol,
        "session_date": rebuilt_tv_context.get("session_date"),
        "source_timestamp": rebuilt_tv_context.get("timestamp"),
        "source_received_at": rebuilt_tv_context.get("received_at"),
        "reconstructed_at": reconstruction_time,
        "session_lock_price": rebuilt_tv_context.get("session_lock_price"),
        "stack_threshold": rebuilt_tv_context.get("stack_threshold"),
        "daily_atr14": rebuilt_tv_context.get("daily_atr14"),
        "frozen_lock_authoritative": True,
        "cleared_fields": cleared_fields,
        "audit_event": audit_event["event"],
        "backups": backups,
    }), 200


@app.post("/operator/liquidity-lock/override-from-latest-tv")
def operator_override_liquidity_lock() -> tuple[Any, int]:
    """Replace only the frozen stack labels from the latest same-session TV context."""
    payload = request.get_json(silent=True)
    request_timestamp = utc_timestamp()
    raw_symbol = None if not isinstance(payload, dict) else payload.get("symbol")
    normalized_symbol = normalize_symbol(raw_symbol) if isinstance(payload, dict) else None
    append_operator_route_audit(
        {
            "timestamp": request_timestamp,
            "event": "liquidity_lock_override_request_received",
            "symbol": normalized_symbol or (str(raw_symbol).upper() if raw_symbol is not None else None),
            "status": "received",
            "failure_reason": None,
        }
    )
    if not isinstance(payload, dict):
        append_operator_route_audit(
            {
                "timestamp": utc_timestamp(),
                "event": "liquidity_lock_override_request_completed",
                "symbol": None,
                "status": "failure",
                "failure_reason": "invalid_json_object",
            }
        )
        return jsonify({"ok": False, "error": "invalid JSON object"}), 400

    if normalized_symbol not in {"NQ", "YM"}:
        append_operator_route_audit(
            {
                "timestamp": utc_timestamp(),
                "event": "liquidity_lock_override_request_completed",
                "symbol": normalized_symbol or (str(raw_symbol).upper() if raw_symbol is not None else None),
                "status": "failure",
                "failure_reason": "unsupported_symbol",
            }
        )
        return jsonify({"ok": False, "error": "supported symbols are NQ and YM only"}), 400

    stored_contexts = stored_context_by_root()
    context = stored_contexts.get(normalized_symbol)
    if not isinstance(context, dict):
        append_operator_route_audit(
            {
                "timestamp": utc_timestamp(),
                "event": "liquidity_lock_override_request_completed",
                "symbol": normalized_symbol,
                "status": "failure",
                "failure_reason": "latest_tv_context_missing",
            }
        )
        return jsonify({"ok": False, "error": "latest_tv_context_missing", "symbol": normalized_symbol}), 404

    state = _read_json(ENTRY_AGENT_STATE_PATH)
    symbol_state = _target_symbol_state(state, normalized_symbol)
    if not isinstance(symbol_state, dict):
        append_operator_route_audit(
            {
                "timestamp": utc_timestamp(),
                "event": "liquidity_lock_override_request_completed",
                "symbol": normalized_symbol,
                "status": "failure",
                "failure_reason": "entry_agent_state_missing_symbol",
            }
        )
        return jsonify({"ok": False, "error": "entry_agent_state_missing_symbol", "symbol": normalized_symbol}), 409
    session_lock = symbol_state.get("session_liquidity_context")
    if not isinstance(session_lock, dict):
        append_operator_route_audit(
            {
                "timestamp": utc_timestamp(),
                "event": "liquidity_lock_override_request_completed",
                "symbol": normalized_symbol,
                "status": "failure",
                "failure_reason": "frozen_lock_not_locked",
            }
        )
        return jsonify({"ok": False, "error": "frozen_lock_not_locked", "symbol": normalized_symbol}), 409

    rebuilt_lock, error = _rebuild_frozen_lock_from_latest_tv(normalized_symbol, context, session_lock)
    if error is not None:
        append_operator_route_audit(
            {
                "timestamp": utc_timestamp(),
                "event": "liquidity_lock_override_request_completed",
                "symbol": normalized_symbol,
                "status": "failure",
                "failure_reason": error.get("error"),
            }
        )
        return jsonify({"ok": False, "symbol": normalized_symbol, **error}), 409

    before_labels = _stack_labels((session_lock.get("active_levels") if isinstance(session_lock.get("active_levels"), dict) else {}) or ((session_lock.get("tv_context") or {}).get("levels") if isinstance(session_lock.get("tv_context"), dict) else {}))
    after_labels = _stack_labels(rebuilt_lock.get("active_levels"))
    levels_changed = [
        {
            "name": name,
            "before": before_labels.get(name),
            "after": after_labels.get(name),
        }
        for name in sorted(set(before_labels) | set(after_labels))
        if before_labels.get(name) != after_labels.get(name)
    ]

    context_store = _read_json(TV_CONTEXT_BY_SYMBOL_PATH)
    context_symbols = context_store.get("symbols") if isinstance(context_store.get("symbols"), dict) else {}
    stored_symbol_context = copy.deepcopy(context_symbols.get(normalized_symbol)) if isinstance(context_symbols.get(normalized_symbol), dict) else copy.deepcopy(context)
    locked_context = stored_symbol_context.get("locked_liquidity_context")
    if not isinstance(locked_context, dict) or not isinstance(locked_context.get("levels"), dict):
        append_operator_route_audit(
            {
                "timestamp": utc_timestamp(),
                "event": "liquidity_lock_override_request_completed",
                "symbol": normalized_symbol,
                "status": "failure",
                "failure_reason": "stored_locked_context_missing",
            }
        )
        return jsonify({"ok": False, "error": "stored_locked_context_missing", "symbol": normalized_symbol}), 409

    latest_levels = context.get("last_tv_context_levels")
    _apply_latest_level_details(locked_context.get("levels"), latest_levels)
    _apply_latest_level_rows(locked_context.get("liquidity_map"), latest_levels)
    stored_symbol_context["locked_liquidity_context"] = locked_context
    stored_symbol_context["liquidity_context_locked"] = True
    stored_symbol_context["last_tv_context_received_at"] = context.get("last_tv_context_received_at") or context.get("received_at")
    stored_symbol_context["last_tv_context_source"] = context.get("last_tv_context_source") or context.get("source")

    if (
        isinstance(stored_symbol_context.get("normalized_symbol"), str)
        and str(stored_symbol_context.get("normalized_symbol")).upper() == normalized_symbol
        and str(stored_symbol_context.get("session_date") or "") == str(rebuilt_lock["tv_context"].get("session_date") or "")
    ):
        stored_symbol_context["session_lock_price"] = locked_context.get("session_lock_price")

    context_symbols[normalized_symbol] = stored_symbol_context
    context_store["symbols"] = context_symbols

    single_context = _read_json(TV_CONTEXT_PATH)
    write_single_context = (
        isinstance(single_context, dict)
        and str(single_context.get("normalized_symbol") or "").upper() == normalized_symbol
    )
    if write_single_context:
        single_locked = single_context.get("locked_liquidity_context")
        if isinstance(single_locked, dict):
            _apply_latest_level_details(single_locked.get("levels"), latest_levels)
            _apply_latest_level_rows(single_locked.get("liquidity_map"), latest_levels)
            single_context["locked_liquidity_context"] = single_locked

    symbol_state["session_liquidity_context"] = rebuilt_lock
    override_applied_at = utc_timestamp()
    audit_event = {
        "timestamp": override_applied_at,
        "event": "liquidity_lock_manual_override_applied",
        "symbol": normalized_symbol,
        "session_date": rebuilt_lock["tv_context"].get("session_date"),
        "levels_changed": copy.deepcopy(levels_changed),
    }
    append_operator_audit_event(state, normalized_symbol, audit_event)

    backup_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backups = {
        "tv_context_by_symbol": timestamped_backup(TV_CONTEXT_BY_SYMBOL_PATH, backup_stamp),
        "entry_agent_state": timestamped_backup(ENTRY_AGENT_STATE_PATH, backup_stamp),
    }
    if write_single_context:
        backups["tv_context"] = timestamped_backup(TV_CONTEXT_PATH, backup_stamp)

    safe_write_json(TV_CONTEXT_BY_SYMBOL_PATH, context_store)
    if write_single_context:
        safe_write_json(TV_CONTEXT_PATH, single_context)
    with ENTRY_STATE_LOCK:
        _write_json(ENTRY_AGENT_STATE_PATH, state)
    append_operator_route_audit(
        {
            "timestamp": utc_timestamp(),
            "event": "liquidity_lock_override_request_completed",
            "symbol": normalized_symbol,
            "status": "success",
            "failure_reason": None,
        }
    )

    return jsonify({
        "ok": True,
        "symbol": normalized_symbol,
        "session_date": rebuilt_lock["tv_context"].get("session_date"),
        "override_applied_at": override_applied_at,
        "message": "SUCCESS: frozen lock updated from latest TV context",
        "levels_changed": levels_changed,
        "before_stack_labels": before_labels,
        "after_stack_labels": after_labels,
        "frozen_lock_still_locked": rebuilt_lock.get("locked") is True and rebuilt_lock.get("disabled") is not True,
        "audit_event": audit_event["event"],
        "backups": backups,
    }), 200


@app.route("/entry/status", methods=["GET", "OPTIONS"])
def get_entry_status() -> tuple[Any, int]:
    """Return read-only Entry Manager decision status; no orders are routed."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200

    raw_symbols = request.args.get("symbols") or request.args.get("symbol") or "NQ,YM"
    symbols = []
    seen_roots = set()
    for item in raw_symbols.split(","):
        requested = item.strip().upper()
        if not requested:
            continue
        normalized = normalize_symbol(item)
        if normalized and normalized not in seen_roots:
            symbols.append(requested)
            seen_roots.add(normalized)

    if not symbols:
        return jsonify({"ok": False, "error": "no supported symbols requested"}), 400

    stored_context = stored_context_by_root()
    statuses = []
    for symbol in symbols:
        status = sanitize_public_entry_status(build_entry_status(symbol))
        if isinstance(status, dict):
            normalized = normalize_symbol(symbol)
            if normalized:
                status = dict(status)
                status["market_context"] = public_market_context(stored_context.get(normalized))
        statuses.append(status)
    for status in statuses:
        if isinstance(status, dict) and not status.get("current_step_label"):
            status["current_step_label"] = current_step_label(status.get("current_step"))
    rehydration_failures = [
        {
            "symbol": status.get("symbol"),
            "reason": status.get("canonical_state_rehydration_reason"),
        }
        for status in statuses
        if isinstance(status, dict) and status.get("canonical_state_rehydrated") is False
    ]
    if rehydration_failures:
        return jsonify({
            "ok": False,
            "mode": "read_only",
            "service_status": "REHYDRATING",
            "execution_truth": "Trade Manager",
            "decision_truth": "Entry Manager",
            "rehydration_failures": rehydration_failures,
            "symbols": statuses,
        }), 503
    return jsonify({
        "ok": True,
        "mode": "read_only",
        "service_status": "LIVE",
        "execution_truth": "Trade Manager",
        "decision_truth": "Entry Manager",
        "symbols": statuses,
    }), 200


@app.route("/entry/executor_status", methods=["GET", "OPTIONS"])
def get_entry_executor_status() -> tuple[Any, int]:
    """Return a read-only bridge of executor snapshot data for Command Center."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200

    sync_snapshot = fetch_local_json(EXECUTOR_SYNC_SNAPSHOT_URL)
    orders = fetch_local_json(EXECUTOR_ORDERS_URL)
    account_snapshot = fetch_local_json(EXECUTOR_ACCOUNT_SNAPSHOT_URL)
    summary = summarize_active_execution_state(sync_snapshot)

    return jsonify({
        "ok": True,
        "mode": "read_only",
        "execution_truth": "Executor",
        "source": "entry_agent_bridge",
        "sync_snapshot": sync_snapshot,
        "executor_summary": summary,
        "orders": orders if summary["has_open_execution_state"] else {"ok": True, "orders": []},
        "account_snapshot": account_snapshot if summary["has_open_execution_state"] else {
            "ok": True,
            "source": "paper_account",
            "hidden_when_flat": True,
            "reason": "no_active_execution_state",
            "updated_at": None,
        },
        "symbol_count": summary["active_symbol_count"],
        "has_open_execution_state": summary["has_open_execution_state"],
    }), 200


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=7002)
