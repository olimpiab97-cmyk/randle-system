"""TradingView context feed server for EntryAgent.

PowerShell test example:
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:7002/webhook/tv-context `
  -ContentType 'application/json' `
  -Body '{"symbol":"CME_MINI:NQ1!","PMH":27390,"PML":27380,"LH":null,"LL":null,"ONH":27395,"ONL":27375,"YH":null,"YL":null,"time_zone":"America/New_York","pm_atr_pct":0.42,"daily_range_pct":0.88}'
"""

from __future__ import annotations

import json
import os
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request
from flask_cors import CORS

from entry_agent import build_entry_status, current_step_label

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "Data"
LEVELS_PATH = BASE_DIR / "levels.json"
LEVELS_BY_SYMBOL_PATH = BASE_DIR / "levels_by_symbol.json"
TV_CONTEXT_PATH = BASE_DIR / "tv_context.json"
TV_CONTEXT_BY_SYMBOL_PATH = BASE_DIR / "tv_context_by_symbol.json"
TV_CONTEXT_EVENTS_PATH = BASE_DIR / "tv_context_events.jsonl"
ENTRY_LOG_DIR = BASE_DIR / "logs"
ENTRY_DECISIONS_LOG_PATH = ENTRY_LOG_DIR / "entry_decisions.jsonl"

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
    "RTY": "RTY",
    "RTYM6": "RTY",
    "RTY1!": "RTY",
    "CME_MINI:RTY1!": "RTY",
}

app = Flask(__name__)
CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    send_wildcard=True,
)
LATEST_TV_CONTEXT_BY_SYMBOL: dict[str, dict[str, Any]] = {}
ENTRY_DECISION_LOG_THROTTLE_SECONDS = 5.0
ENTRY_DECISION_LAST_LOGGED: dict[str, dict[str, Any]] = {}
ENTRY_REASONING_LAST_LOGGED: dict[str, dict[str, Any]] = {}


@app.after_request
def add_entry_status_cors_headers(response: Any) -> Any:
    """Keep Entry Agent read-only status fetchable from Command Center."""
    if request.path == "/entry/status":
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
    return response


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
    if symbol_text.startswith("RTY"):
        return "RTY"
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


def append_context_event(context: dict[str, Any], remote_addr: str | None) -> None:
    """Append one successful TradingView context webhook event."""
    event = {
        "received_at": context.get("received_at"),
        "normalized_symbol": context.get("normalized_symbol"),
        "levels": {field: context.get(field) for field in LEVEL_FIELDS},
        "pm_atr_pct": context.get("pm_atr_pct"),
        "daily_range_pct": context.get("daily_range_pct"),
        "time_zone": context.get("time_zone"),
        "remote_addr": remote_addr,
    }
    with TV_CONTEXT_EVENTS_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, separators=(",", ":")) + "\n")


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
    return DATA_DIR / f"entry_reasoning_{date_value}.jsonl"


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
        "liquidity_group": status.get("liquidity_group"),
        "close_vs_level": status.get("close_vs_level"),
        "step": status.get("current_step"),
        "current_step_label": status.get("current_step_label"),
        "setup_direction": status.get("setup_direction"),
        "rejection_mode_entered": bool(status.get("rejection_mode_entered")),
        "sr_rs_context": status.get("sr_rs_context"),
        "leg1_state": status.get("leg1_state") or status.get("leg1_status"),
        "leg1_locked": status.get("leg1_locked") or status.get("leg1_state_locked"),
        "leg1_reference_price": status.get("leg1_reference_price"),
        "leg1_completed_at": status.get("leg1_completed_at"),
        "fifty_percent_rule_phase": status.get("fifty_percent_rule_phase"),
        "leg2_state": status.get("leg2_state") or status.get("leg2_status"),
        "leg2_candidate_candle_time": status.get("leg2_candidate_candle_time"),
        "leg2_reference_price": status.get("leg2_reference_price"),
        "leg2_25_percent_rule_passed": status.get("leg2_25_percent_rule_passed"),
        "entry_status": status.get("entry_status"),
        "invalidation_source": status.get("invalidation_source"),
        "invalidation_reason": status.get("invalidation_reason"),
        "wait_reason": status.get("wait_reason"),
        "last_decision": status.get("last_decision"),
    }


def reasoning_state_key(record: dict[str, Any]) -> tuple[Any, ...]:
    """Return fields that define a reasoning transition."""
    return (
        record.get("candle_time"),
        record.get("step"),
        record.get("active_liquidity_name"),
        record.get("liquidity_price"),
        record.get("setup_direction"),
        record.get("rejection_mode_entered"),
        record.get("sr_rs_context"),
        record.get("leg1_state"),
        record.get("leg1_locked"),
        record.get("leg1_reference_price"),
        record.get("leg1_completed_at"),
        record.get("fifty_percent_rule_phase"),
        record.get("leg2_state"),
        record.get("leg2_candidate_candle_time"),
        record.get("leg2_reference_price"),
        record.get("leg2_25_percent_rule_passed"),
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
        DATA_DIR.mkdir(parents=True, exist_ok=True)
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


def build_context(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Normalize an inbound TradingView context payload without strict validation."""
    normalized_symbol = normalize_symbol(payload.get("symbol"))
    if normalized_symbol is None:
        normalized_symbol = str(payload.get("symbol") or "UNKNOWN").strip().upper() or "UNKNOWN"

    context: dict[str, Any] = dict(payload)
    context["received_at"] = utc_timestamp()
    context["normalized_symbol"] = normalized_symbol
    return context, None


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


@app.post("/webhook/tv-context")
def receive_tv_context() -> tuple[Any, int]:
    """Receive full TradingView table context for EntryAgent."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid JSON object"}), 400

    preview = {key: payload.get(key) for key in list(payload)[:2]}
    print(f"ENTRY TV CONTEXT incoming_preview={preview}")

    context, error = build_context(payload)
    if error is not None:
        return jsonify(error), 400

    levels = build_levels(context)
    stored_payload = dict(context)
    LATEST_TV_CONTEXT_BY_SYMBOL[str(context["normalized_symbol"])] = stored_payload
    persistence_error = None
    try:
        safe_write_json(LEVELS_PATH, levels)
        safe_write_json(TV_CONTEXT_PATH, context)
        upsert_symbol_json(LEVELS_BY_SYMBOL_PATH, str(context["normalized_symbol"]), levels)
        upsert_symbol_json(TV_CONTEXT_BY_SYMBOL_PATH, str(context["normalized_symbol"]), stored_payload)
        append_context_event(context, request.remote_addr)
    except OSError as exc:
        persistence_error = str(exc)
        print(f"ENTRY TV CONTEXT persistence_error={persistence_error}")
    return jsonify({
        "ok": True,
        "normalized_symbol": context["normalized_symbol"],
        "context": stored_payload,
        "persistence_error": persistence_error,
    }), 200


@app.get("/context")
def get_context() -> tuple[Any, int]:
    """Return the latest persisted TradingView context."""
    if not TV_CONTEXT_PATH.exists():
        return jsonify({"context": None}), 200

    try:
        with TV_CONTEXT_PATH.open("r", encoding="utf-8") as file:
            return jsonify(json.load(file)), 200
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
    raw_symbols = request.args.get("symbols") or request.args.get("symbol") or "NQ,YM,RTY"
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
    raw_symbols = request.args.get("symbols") or request.args.get("symbol") or "NQ,YM,RTY"
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


@app.route("/entry/status", methods=["GET", "OPTIONS"])
def get_entry_status() -> tuple[Any, int]:
    """Return read-only Entry Manager decision status; no orders are routed."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200

    raw_symbols = request.args.get("symbols") or request.args.get("symbol") or "NQ,YM,RTY"
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

    statuses = [build_entry_status(symbol) for symbol in symbols]
    for status in statuses:
        if isinstance(status, dict) and not status.get("current_step_label"):
            status["current_step_label"] = current_step_label(status.get("current_step"))
    log_timestamp = utc_timestamp()
    append_entry_decision_log([entry_decision_record(status, log_timestamp) for status in statuses])
    append_entry_reasoning_log([entry_reasoning_record(status, log_timestamp) for status in statuses])
    return jsonify({
        "ok": True,
        "mode": "read_only",
        "execution_truth": "Trade Manager",
        "decision_truth": "Entry Manager",
        "symbols": statuses,
    }), 200


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=7002)
