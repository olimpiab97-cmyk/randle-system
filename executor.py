import tempfile
from pathlib import Path
import uuid
import json
import os
import hmac
import math
import requests
import subprocess
from collections import defaultdict, deque
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS
from symbol_resolution import (
    build_symbol_candidates,
    canonicalize_symbol_input,
    get_tick_size,
    normalize_symbol_root,
    resolve_execution_symbol,
)

app = Flask(__name__)
CORS(app)


def is_local_request():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        remote = forwarded_for.split(",", 1)[0].strip().lower()
    else:
        remote = (request.remote_addr or "").strip().lower()
    return remote in {"127.0.0.1", "::1", "localhost", "0:0:0:0:0:0:0:1", "::ffff:127.0.0.1"}


def token_matches(env_name, header_name):
    expected = os.getenv(env_name, "")
    if not expected:
        return None
    supplied = request.headers.get(header_name, "")
    return hmac.compare_digest(str(supplied), str(expected))


def reject_auth(error, status_code):
    return jsonify({"ok": False, "error": error}), status_code


def require_internal_token():
    matched = token_matches("RANDLE_INTERNAL_TOKEN", "X-RANDLE-INTERNAL-TOKEN")
    if matched is None:
        return reject_auth("auth_not_configured", 503)
    if not matched:
        return reject_auth("unauthorized", 401)
    return None


def internal_auth_headers():
    token = os.getenv("RANDLE_INTERNAL_TOKEN", "")
    return {"X-RANDLE-INTERNAL-TOKEN": token} if token else None


@app.before_request
def enforce_endpoint_auth():
    path = request.path or ""
    if is_local_request():
        return None

    if path in {"/execute", "/price", "/sync_snapshot"}:
        return require_internal_token()

    if path in {"/health", "/orders", "/positions"} or path.startswith("/debug/"):
        return reject_auth("localhost_required", 403)

    return None

# =========================
# SIMPLE IN-MEMORY ORDER STORE
# =========================
ORDERS = {}
POSITIONS = {}
LAST_PRICES = {}
LAST_PRICE_TIMESTAMPS = {}
LAST_PRICE_LISTENER_TICK_IDS = {}
LAST_PRICE_LISTENER_SEQUENCES = {}
LAST_PRICE_EXECUTOR_SEQUENCES = {}
EXECUTOR_PRICE_SEQUENCE_BY_ALIAS = defaultdict(int)
EXECUTOR_ACCEPTED_PRICE_HISTORY = defaultdict(lambda: deque(maxlen=10))
EXECUTOR_REJECT_HISTORY = defaultdict(lambda: deque(maxlen=10))
CURRENT_1M_BARS = {}
COMPLETED_1M_BARS = {}
ATR_PERIOD = 14
MAX_COMPLETED_1M_BARS = 200
WORKING_ORDER_STATUSES = {"active", "open", "working", "submitted", "accepted"}
INACTIVE_ORDER_STATUSES = {"closed", "cancelled", "canceled", "rejected", "filled", "expired"}
LISTENER_LAST_TICK_MAX_AGE_SECONDS = 5
LISTENER_TICK_FUTURE_TOLERANCE_SECONDS = 2
WATCHDOG_STALE_AFTER_SECONDS = 10
AUTO_RESTART_ENABLED = True
AUTO_RESTART_STALE_THRESHOLD_SECONDS = 30
AUTO_RESTART_COOLDOWN_SECONDS = 120
LISTENER_AUTO_RESTART_EXECUTION_ENABLED = True
LISTENER_SCRIPT_NAME = "rithmic_live_listener.py"
LISTENER_RESTART_COMMAND = ["python", "rithmic_live_listener.py"]
LISTENER_CURRENT_BAR_MAX_AGE_SECONDS = 90
ENTRY_FILL_LAST_TICK_MAX_AGE_SECONDS = {
    "NQ": 2.0,
    "RTY": 2.0,
    "YM": 2.0,
}
ENTRY_FILL_DEFAULT_LAST_TICK_MAX_AGE_SECONDS = 2.0

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "Data"
EXECUTOR_STATE_FILE = DATA_DIR / "executor_state.json"
TRADE_MANAGER_PERSISTENCE_FILE = DATA_DIR / "persistence_state.json"
RITHMIC_FEED_HEALTH_FILE = DATA_DIR / "rithmic_feed_health.json"
TRADE_MANAGER_PRICE_URL = os.getenv("TRADE_MANAGER_PRICE_URL", "http://127.0.0.1:7001/price").strip() or "http://127.0.0.1:7001/price"
STATE_VERSION = 1
EXECUTOR_STATE_LOADED = False
EXECUTOR_STATE_SAVED_AT = None
TRADINGVIEW_ATR_MAX_AGE_SECONDS = 180
WATCHDOG_LAST_VALID_TICK_TIMESTAMP = None
WATCHDOG_LAST_VALID_TICK_SYMBOL = None
WATCHDOG_STATUS = "STALE"
WATCHDOG_BLOCKED_OPENING_ACTIONS = {"submit_entry"}
LAST_RESTART_ATTEMPT_TIMESTAMP = None


class EntryFillRejected(ValueError):
    def __init__(self, reason, audit):
        super().__init__(reason)
        self.reason = reason
        self.audit = audit

# =========================
# HELPERS
# =========================
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def price_pipeline_timestamp(value):
    if isinstance(value, datetime):
        suffix = "" if value.tzinfo is not None else "Z"
        return value.isoformat() + suffix
    return value


def log_price_pipeline(
    stage,
    symbol=None,
    price=None,
    tick_timestamp=None,
    received_at=None,
    http_status=None,
    reject_reason=None,
    target_url=None,
    listener_tick_id=None,
    executor_tick_id=None,
    listener_sequence=None,
    executor_sequence=None,
):
    symbol_text = str(symbol or "").strip().upper()
    normalized_alias = normalize_symbol_root(symbol_text) or symbol_text
    log(
        "PRICE PIPELINE|"
        f"{stage}|"
        f"symbol={symbol_text}|"
        f"normalized_alias={normalized_alias}|"
        f"price={price}|"
        f"tick_timestamp={price_pipeline_timestamp(tick_timestamp)}|"
        f"received_at={price_pipeline_timestamp(received_at)}|"
        f"http_status={http_status}|"
        f"reject_reason={reject_reason}|"
        f"target_url={target_url}|"
        f"listener_tick_id={listener_tick_id}|"
        f"executor_tick_id={executor_tick_id}|"
        f"listener_sequence={listener_sequence}|"
        f"executor_sequence={executor_sequence}"
    )


SAFE_EXECUTION_MODES = {"paper", "sim", "simulation", "qa"}
PAPER_ACCOUNT_MARKERS = ("paper", "sim", "simulation", "qa", "test", "demo")
ACCOUNT_IDENTIFIER_KEYS = (
    "account",
    "account_id",
    "accountId",
    "account_name",
    "accountName",
    "broker_account",
    "rithmic_account",
)
ORDER_RISK_CAPPED_ACTIONS = {
    "submit_entry",
    "submit_stop",
    "submit_limit",
    "modify_stop",
    "move_stop_to_be",
    "reset_stop_to_original",
}
SUPPORTED_EXECUTION_ROOTS = set(ENTRY_FILL_LAST_TICK_MAX_AGE_SECONDS.keys())


def get_execution_safety_context(payload=None):
    payload = payload if isinstance(payload, dict) else {}
    mode = str(os.getenv("RANDLE_EXECUTION_MODE", "paper") or "paper").strip().lower()
    allow_live = str(os.getenv("RANDLE_ALLOW_LIVE_TRADING", "") or "").strip() == "true"
    approved_substring = str(os.getenv("RANDLE_APPROVED_ACCOUNT_SUBSTRING", "") or "")

    account_value = None
    for key in ACCOUNT_IDENTIFIER_KEYS:
        value = payload.get(key)
        if value not in (None, ""):
            account_value = str(value)
            break

    return {
        "mode": mode,
        "allow_live_trading": allow_live,
        "account_present": bool(account_value),
        "account_matches_paper_pattern": (
            not account_value
            or any(marker in account_value.lower() for marker in PAPER_ACCOUNT_MARKERS)
        ),
        "approved_account_substring_configured": bool(approved_substring),
        "account_matches_approved_substring": (
            not approved_substring
            or bool(account_value and approved_substring in account_value)
        ),
    }


def validate_execution_safety(payload=None):
    context = get_execution_safety_context(payload)
    mode = context["mode"]

    if mode not in SAFE_EXECUTION_MODES and not (mode == "live" and context["allow_live_trading"]):
        return {
            "ok": False,
            "reason": "execution_mode_not_paper_safe",
            "context": context,
        }

    if context["account_present"] and not context["account_matches_paper_pattern"]:
        return {
            "ok": False,
            "reason": "account_not_approved_paper_pattern",
            "context": context,
        }

    if not context["account_matches_approved_substring"]:
        return {
            "ok": False,
            "reason": "account_missing_approved_substring",
            "context": context,
        }

    return {
        "ok": True,
        "reason": "execution_safety_approved",
        "context": context,
    }


def get_float_env(name, default):
    try:
        value = float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)
    return value if value > 0 else float(default)


def parse_positive_qty(payload):
    if not isinstance(payload, dict) or "qty" not in payload:
        return None, "missing_qty"
    try:
        qty = float(payload.get("qty"))
    except (TypeError, ValueError):
        return None, "invalid_qty"
    if not math.isfinite(qty):
        return None, "invalid_qty"
    if qty <= 0:
        return None, "qty_must_be_positive"
    return qty, None


def validate_order_risk_caps(payload):
    payload = payload if isinstance(payload, dict) else {}
    action = payload.get("action")
    if action not in ORDER_RISK_CAPPED_ACTIONS:
        return {"ok": True, "reason": "order_risk_cap_not_applicable"}

    qty, qty_error = parse_positive_qty(payload)
    if qty_error:
        return {"ok": False, "reason": qty_error}

    max_order_qty = get_float_env("RANDLE_MAX_ORDER_QTY", 2)
    if qty > max_order_qty:
        return {"ok": False, "reason": "max_order_qty_exceeded"}

    raw_symbol = str(payload.get("symbol") or "").strip().upper()
    if not raw_symbol:
        return {"ok": False, "reason": "missing_symbol"}

    root_symbol = normalize_symbol_root(raw_symbol)
    if root_symbol not in SUPPORTED_EXECUTION_ROOTS:
        return {"ok": False, "reason": "unknown_symbol"}

    if action != "submit_entry":
        return {"ok": True, "reason": "order_risk_cap_approved"}

    direction = str(payload.get("direction") or "").strip().lower()
    if direction not in {"long", "short"}:
        return {"ok": False, "reason": "invalid_direction"}

    resolved_symbol, _ = resolve_execution_symbol(raw_symbol)
    position_symbol = raw_symbol if raw_symbol in POSITIONS else resolved_symbol
    current_qty = float((POSITIONS.get(position_symbol) or {}).get("qty", 0) or 0)
    signed_qty = qty if direction == "long" else -qty
    projected_qty = current_qty + signed_qty
    max_position_qty = get_float_env("RANDLE_MAX_POSITION_QTY", 2)
    if abs(projected_qty) > max_position_qty:
        return {"ok": False, "reason": "max_position_qty_exceeded"}

    return {"ok": True, "reason": "order_risk_cap_approved"}


def utc_now_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def make_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def normalize_order_status(status):
    return str(status or "").strip().lower()


def is_working_order(order):
    status = normalize_order_status(order.get("status"))
    if status in INACTIVE_ORDER_STATUSES:
        return False
    return status in WORKING_ORDER_STATUSES


def floor_to_minute(timestamp):
    return timestamp.replace(second=0, microsecond=0)


def serialize_bar(bar):
    return {
        "bar_timestamp": bar["bar_timestamp"].isoformat(),
        "open": float(bar["open"]),
        "high": float(bar["high"]),
        "low": float(bar["low"]),
        "close": float(bar["close"]),
    }


def parse_iso_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def seconds_since(timestamp, reference_time):
    parsed = parse_iso_datetime(timestamp)
    if parsed is None:
        return None
    return max(0.0, (reference_time - parsed).total_seconds())


def parse_listener_tick_timestamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def reject_price_tick(symbol, reason, **details):
    payload = {
        "ok": False,
        "error": "stale_or_invalid_market_data",
        "reason": reason,
    }
    if symbol:
        payload["symbol"] = symbol
    payload.update(details)
    return jsonify(payload), 409


def executor_alias_key(symbol):
    return normalize_symbol_root(symbol) or str(symbol or "").strip().upper()


def append_executor_reject(symbol, reason, price=None, tick_timestamp=None, listener_tick_id=None, listener_sequence=None):
    key = executor_alias_key(symbol)
    if not key:
        return
    EXECUTOR_REJECT_HISTORY[key].append({
        "symbol": str(symbol or "").strip().upper(),
        "normalized_alias": key,
        "price": price,
        "tick_timestamp": tick_timestamp,
        "listener_tick_id": listener_tick_id,
        "listener_sequence": listener_sequence,
        "reason": reason,
        "received_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    })


def append_executor_accept(symbol, price, tick_timestamp, listener_tick_id, listener_sequence, executor_sequence):
    key = executor_alias_key(symbol)
    EXECUTOR_ACCEPTED_PRICE_HISTORY[key].append({
        "symbol": str(symbol or "").strip().upper(),
        "normalized_alias": key,
        "price": float(price),
        "tick_timestamp": tick_timestamp,
        "listener_tick_id": listener_tick_id,
        "executor_tick_id": listener_tick_id,
        "listener_sequence": listener_sequence,
        "executor_sequence": executor_sequence,
        "received_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    })


def executor_history_for_symbol(symbol, history):
    key = executor_alias_key(symbol)
    return list(history.get(key) or [])


def seconds_until_restart(watchdog_state, reference_time=None):
    if reference_time is None:
        reference_time = utc_now_naive()

    if not AUTO_RESTART_ENABLED or watchdog_state.get("status") != "STALE":
        return None

    seconds_since_last_tick = watchdog_state.get("seconds_since_last_valid_tick")
    if seconds_since_last_tick is None:
        return None

    threshold_remaining = max(
        0.0,
        AUTO_RESTART_STALE_THRESHOLD_SECONDS - float(seconds_since_last_tick),
    )
    cooldown_remaining = 0.0
    if LAST_RESTART_ATTEMPT_TIMESTAMP is not None:
        cooldown_remaining = max(
            0.0,
            AUTO_RESTART_COOLDOWN_SECONDS - (reference_time - LAST_RESTART_ATTEMPT_TIMESTAMP).total_seconds(),
        )

    return round(max(threshold_remaining, cooldown_remaining), 3)


def should_trigger_restart(watchdog_state):
    if not AUTO_RESTART_ENABLED:
        return False
    if watchdog_state.get("status") != "STALE":
        return False

    seconds_since_last_tick = watchdog_state.get("seconds_since_last_valid_tick")
    if seconds_since_last_tick is None:
        return False
    if float(seconds_since_last_tick) < AUTO_RESTART_STALE_THRESHOLD_SECONDS:
        return False

    if LAST_RESTART_ATTEMPT_TIMESTAMP is None:
        return True

    return (utc_now_naive() - LAST_RESTART_ATTEMPT_TIMESTAMP).total_seconds() >= AUTO_RESTART_COOLDOWN_SECONDS


def find_listener_process(process_iter=None):
    if process_iter is None:
        try:
            import psutil
        except Exception:
            return None
        process_iter = psutil.process_iter(["pid", "name", "cmdline"])

    matches = []
    for process in process_iter:
        try:
            info = getattr(process, "info", process)
            name = str(info.get("name") or "").lower()
            if "python" not in name:
                continue

            cmdline_value = info.get("cmdline") or []
            if isinstance(cmdline_value, (list, tuple)):
                command_line = " ".join(str(part) for part in cmdline_value)
            else:
                command_line = str(cmdline_value)

            if LISTENER_SCRIPT_NAME not in command_line:
                continue

            matches.append({
                "pid": int(info.get("pid")),
                "command_line": command_line,
            })
        except Exception:
            continue

    if len(matches) != 1:
        return None
    return matches[0]


def stop_listener_process(listener_process):
    try:
        pid = int(listener_process.get("pid"))
        command_line = str(listener_process.get("command_line") or "")
    except Exception:
        return {"stopped": False, "reason": "invalid_listener_process"}

    if pid <= 0 or LISTENER_SCRIPT_NAME not in command_line:
        return {"stopped": False, "reason": "invalid_listener_process"}

    try:
        import psutil
    except Exception:
        return {"stopped": False, "reason": "psutil_unavailable"}

    try:
        process = psutil.Process(pid)
        process.terminate()
        process.wait(timeout=10)
    except Exception as exc:
        return {"stopped": False, "reason": str(exc)}

    return {"stopped": True, "pid": pid}


def start_listener_process():
    try:
        subprocess.Popen(
            LISTENER_RESTART_COMMAND,
            cwd=str(BASE_DIR),
            shell=False,
        )
    except Exception as exc:
        return {"started": False, "reason": str(exc)}

    return {"started": True}


def execute_listener_restart():
    if not LISTENER_AUTO_RESTART_EXECUTION_ENABLED:
        log("WATCHDOG RESTART SKIPPED: execution disabled")
        return {"executed": False, "reason": "execution_disabled"}

    listener_process = find_listener_process()
    if listener_process is None:
        log("WATCHDOG RESTART SKIPPED: listener process not uniquely identified")
        return {"executed": False, "reason": "listener_not_identified"}

    pid = listener_process["pid"]
    stop_result = stop_listener_process(listener_process)
    if not stop_result.get("stopped"):
        return {
            "executed": False,
            "reason": "stop_failed",
            "stopped_pid": pid,
            "stop_result": stop_result,
        }

    start_result = start_listener_process()
    if not start_result.get("started"):
        return {
            "executed": False,
            "reason": "start_failed",
            "stopped_pid": pid,
            "start_result": start_result,
        }

    log(f"WATCHDOG RESTART EXECUTED: stopped_pid={pid}")
    return {
        "executed": True,
        "reason": "listener_restarted",
        "stopped_pid": pid,
        "start_result": start_result,
    }


def build_watchdog_state(reference_time=None, emit_transition_log=True):
    global WATCHDOG_STATUS, LAST_RESTART_ATTEMPT_TIMESTAMP

    if reference_time is None:
        reference_time = utc_now_naive()

    last_timestamp = WATCHDOG_LAST_VALID_TICK_TIMESTAMP
    parsed = parse_listener_tick_timestamp(last_timestamp)
    seconds_since_last_tick = None
    if parsed is not None:
        seconds_since_last_tick = (reference_time - parsed).total_seconds()

    status = (
        "LIVE"
        if seconds_since_last_tick is not None
        and seconds_since_last_tick <= WATCHDOG_STALE_AFTER_SECONDS
        else "STALE"
    )

    if emit_transition_log and status == "STALE" and WATCHDOG_STATUS != "STALE" and seconds_since_last_tick is not None:
        log(
            f"WATCHDOG STALE: no valid LIVE ticks for {seconds_since_last_tick:.3f} seconds "
            f"| last_symbol={WATCHDOG_LAST_VALID_TICK_SYMBOL}"
        )

    WATCHDOG_STATUS = status
    watchdog_state = {
        "status": status,
        "last_valid_tick_timestamp": last_timestamp,
        "last_valid_tick_symbol": WATCHDOG_LAST_VALID_TICK_SYMBOL,
        "seconds_since_last_valid_tick": (
            round(seconds_since_last_tick, 3)
            if seconds_since_last_tick is not None
            else None
        ),
    }
    restart_eligible = should_trigger_restart(watchdog_state)
    watchdog_state["auto_restart_enabled"] = AUTO_RESTART_ENABLED
    watchdog_state["restart_eligible"] = restart_eligible
    watchdog_state["seconds_until_restart"] = seconds_until_restart(watchdog_state, reference_time=reference_time)

    if restart_eligible:
        LAST_RESTART_ATTEMPT_TIMESTAMP = reference_time
        watchdog_state["seconds_until_restart"] = AUTO_RESTART_COOLDOWN_SECONDS
        watchdog_state["restart_action"] = execute_listener_restart()

    return watchdog_state


def record_valid_watchdog_tick(symbol, tick_timestamp_utc):
    global WATCHDOG_LAST_VALID_TICK_TIMESTAMP, WATCHDOG_LAST_VALID_TICK_SYMBOL, WATCHDOG_STATUS

    previous = build_watchdog_state(emit_transition_log=False)
    WATCHDOG_LAST_VALID_TICK_TIMESTAMP = tick_timestamp_utc
    WATCHDOG_LAST_VALID_TICK_SYMBOL = symbol
    WATCHDOG_STATUS = "LIVE"

    if previous["status"] == "STALE" and previous["last_valid_tick_timestamp"] is not None:
        log(f"WATCHDOG RECOVERED: valid LIVE ticks resumed | symbol={symbol}")


def reject_if_watchdog_blocks_action(action):
    if action not in WATCHDOG_BLOCKED_OPENING_ACTIONS:
        return None

    if WATCHDOG_LAST_VALID_TICK_TIMESTAMP is None and not LAST_PRICE_TIMESTAMPS:
        return None

    watchdog = build_watchdog_state()
    if watchdog["status"] != "STALE":
        return None

    log("ORDER BLOCKED: watchdog STALE")
    return jsonify({
        "ok": False,
        "error": "watchdog_stale",
        "watchdog": watchdog,
    }), 409


def isoformat_or_none(value):
    parsed = parse_iso_datetime(value)
    if parsed is None:
        return None
    return parsed.isoformat()


def get_entry_fill_last_tick_max_age_seconds(symbol):
    root_symbol = normalize_symbol_root(symbol)
    return float(
        ENTRY_FILL_LAST_TICK_MAX_AGE_SECONDS.get(
            root_symbol,
            ENTRY_FILL_DEFAULT_LAST_TICK_MAX_AGE_SECONDS,
        )
    )


def is_valid_entry_execution_price(symbol, reference_time, max_tick_age_seconds=None):
    if symbol not in LAST_PRICES:
        return False, build_listener_freshness(symbol, reference_time)

    freshness = build_listener_freshness(symbol, reference_time)
    if not LAST_PRICE_TIMESTAMPS:
        return True, freshness

    listener_status = freshness.get("listener_status")
    last_tick_age = freshness.get("last_tick_age_seconds")
    max_tick_age = max_tick_age_seconds
    if max_tick_age is None:
        max_tick_age = freshness.get("listener_last_tick_max_age_seconds")
    last_price_at = freshness.get("last_price_at")

    if last_tick_age is not None:
        try:
            return float(last_tick_age) <= float(max_tick_age), freshness
        except (TypeError, ValueError):
            return False, freshness

    if listener_status == "fresh":
        return True, freshness

    return last_price_at is not None, freshness


def build_fill_audit(
    *,
    requested_symbol,
    execution_symbol,
    direction,
    selected_fill_price,
    fill_price_source,
    last_prices_lookup_key,
    order_id,
    trade_id,
    fallback_used,
    resolution_source,
    rejected_reason=None,
    reference_time=None,
):
    if reference_time is None:
        reference_time = datetime.now()

    current_bar = CURRENT_1M_BARS.get(execution_symbol)
    current_bar_timestamp = current_bar.get("bar_timestamp") if current_bar else None
    current_bar_age = seconds_since(current_bar_timestamp, reference_time)
    last_price_timestamp = LAST_PRICE_TIMESTAMPS.get(last_prices_lookup_key)
    last_tick_age = seconds_since(last_price_timestamp, reference_time)

    audit = {
        "timestamp": reference_time.isoformat(),
        "requested_symbol": requested_symbol,
        "execution_symbol": execution_symbol,
        "symbol_resolution_source": resolution_source,
        "direction": direction,
        "selected_fill_price": float(selected_fill_price) if selected_fill_price is not None else None,
        "fill_price_source": fill_price_source,
        "LAST_PRICES_lookup_key_used": last_prices_lookup_key,
        "LAST_PRICES_value": (
            float(LAST_PRICES[last_prices_lookup_key])
            if last_prices_lookup_key in LAST_PRICES
            else None
        ),
        "LAST_PRICES_timestamp": isoformat_or_none(last_price_timestamp),
        "last_tick_age_seconds": round(last_tick_age, 3) if last_tick_age is not None else None,
        "current_1m_bar_open": float(current_bar["open"]) if current_bar else None,
        "current_1m_bar_high": float(current_bar["high"]) if current_bar else None,
        "current_1m_bar_low": float(current_bar["low"]) if current_bar else None,
        "current_1m_bar_close": float(current_bar["close"]) if current_bar else None,
        "current_1m_bar_timestamp": isoformat_or_none(current_bar_timestamp),
        "current_1m_bar_age_seconds": round(current_bar_age, 3) if current_bar_age is not None else None,
        "order_id": order_id,
        "trade_id": trade_id,
        "fallback_used": bool(fallback_used),
        "rejected": rejected_reason is not None,
        "reject_reason": rejected_reason,
    }
    return audit


def persist_fill_audit(audit):
    payload = json.dumps(audit, sort_keys=True)
    print(f"FILL_AUDIT|{payload}")

    audit_path = Path(DATA_DIR) / "fill_audit_log.jsonl"
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
    except Exception as exc:
        log(f"FILL_AUDIT_WRITE_FAILED path={audit_path} error={exc}")


def read_rithmic_feed_health():
    try:
        with Path(RITHMIC_FEED_HEALTH_FILE).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return {"symbols": {}, "system_state_feed": "STALE"}
    return payload if isinstance(payload, dict) else {"symbols": {}, "system_state_feed": "STALE"}


def build_listener_freshness(symbol, reference_time):
    last_price_at = LAST_PRICE_TIMESTAMPS.get(symbol)
    last_tick_age = seconds_since(last_price_at, reference_time)
    current_bar = CURRENT_1M_BARS.get(symbol)
    current_bar_timestamp = current_bar.get("bar_timestamp") if current_bar else None
    current_bar_age = seconds_since(current_bar_timestamp, reference_time)

    if symbol not in LAST_PRICES or last_tick_age is None:
        status = "missing"
        reason = "last_price_missing"
    elif last_tick_age > LISTENER_LAST_TICK_MAX_AGE_SECONDS:
        status = "stale"
        reason = "last_tick_stale"
    elif current_bar_age is None:
        status = "stale"
        reason = "current_1m_bar_missing"
    elif current_bar_age > LISTENER_CURRENT_BAR_MAX_AGE_SECONDS:
        status = "stale"
        reason = "current_1m_bar_stale"
    else:
        status = "fresh"
        reason = None

    return {
        "last_price_at": last_price_at,
        "last_tick_age_seconds": round(last_tick_age, 3) if last_tick_age is not None else None,
        "current_1m_bar_timestamp": current_bar_timestamp.isoformat() if isinstance(current_bar_timestamp, datetime) else None,
        "current_1m_bar_age_seconds": round(current_bar_age, 3) if current_bar_age is not None else None,
        "listener_status": status,
        "listener_status_reason": reason,
        "listener_last_tick_max_age_seconds": LISTENER_LAST_TICK_MAX_AGE_SECONDS,
        "listener_current_bar_max_age_seconds": LISTENER_CURRENT_BAR_MAX_AGE_SECONDS,
    }


def append_completed_bar(symbol, bar):
    bars = COMPLETED_1M_BARS.setdefault(symbol, [])
    bars.append({
        "bar_timestamp": bar["bar_timestamp"],
        "open": float(bar["open"]),
        "high": float(bar["high"]),
        "low": float(bar["low"]),
        "close": float(bar["close"]),
    })

    if len(bars) > MAX_COMPLETED_1M_BARS:
        del bars[:-MAX_COMPLETED_1M_BARS]


def finalize_completed_bar_if_closed(symbol, reference_time):
    current_bar = CURRENT_1M_BARS.get(symbol)

    if current_bar is None:
        return

    current_minute = floor_to_minute(reference_time)

    if current_bar["bar_timestamp"] < current_minute:
        append_completed_bar(symbol, current_bar)
        CURRENT_1M_BARS.pop(symbol, None)


def update_1m_bar(symbol, price, timestamp):
    bar_timestamp = floor_to_minute(timestamp)
    current_bar = CURRENT_1M_BARS.get(symbol)

    if current_bar is None:
        CURRENT_1M_BARS[symbol] = {
            "bar_timestamp": bar_timestamp,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
        }
        return

    if current_bar["bar_timestamp"] == bar_timestamp:
        current_bar["high"] = max(float(current_bar["high"]), price)
        current_bar["low"] = min(float(current_bar["low"]), price)
        current_bar["close"] = price
        return

    append_completed_bar(symbol, current_bar)

    CURRENT_1M_BARS[symbol] = {
        "bar_timestamp": bar_timestamp,
        "open": price,
        "high": price,
        "low": price,
        "close": price,
    }


def compute_atr_14(symbol, reference_time=None):
    if reference_time is None:
        reference_time = datetime.now()

    finalize_completed_bar_if_closed(symbol, reference_time)
    bars = COMPLETED_1M_BARS.get(symbol, [])

    if symbol not in CURRENT_1M_BARS and not bars:
        return {
            "ok": False,
            "error": "SYMBOL_NOT_STREAMING",
            "atr_source": "live_executor_1m14",
        }

    if len(bars) < ATR_PERIOD:
        return {
            "ok": False,
            "error": "INSUFFICIENT_1M_HISTORY",
            "atr_source": "live_executor_1m14",
            "completed_bars": len(bars),
        }

    true_ranges = []

    for idx, bar in enumerate(bars):
        high = float(bar["high"])
        low = float(bar["low"])

        if idx == 0:
            tr = high - low
        else:
            prev_close = float(bars[idx - 1]["close"])
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close),
            )

        true_ranges.append(tr)

    if len(true_ranges) < ATR_PERIOD:
        return {
            "ok": False,
            "error": "ATR_NOT_READY",
            "atr_source": "live_executor_1m14",
            "completed_bars": len(bars),
        }

    atr_value = sum(true_ranges[-ATR_PERIOD:]) / ATR_PERIOD
    latest_bar = bars[-1]

    return {
        "ok": True,
        "symbol": symbol,
        "atr_source": "live_executor_1m14",
        "atr_value": round(float(atr_value), 4),
        "bar_timestamp": latest_bar["bar_timestamp"].isoformat(),
        "completed_bars": len(bars),
    }


def parse_iso_timestamp(timestamp_value):
    if not timestamp_value:
        return None
    try:
        return datetime.fromisoformat(str(timestamp_value).replace("Z", "+00:00"))
    except Exception:
        return None


def load_trade_manager_state():
    if not TRADE_MANAGER_PERSISTENCE_FILE.exists():
        return {}

    try:
        with TRADE_MANAGER_PERSISTENCE_FILE.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return {}

    return payload if isinstance(payload, dict) else {}


def build_tradingview_atr_candidates(symbol):
    candidates = []
    for candidate in build_symbol_candidates(symbol):
        normalized_candidate = canonicalize_symbol_input(candidate) or str(candidate or "").upper()
        for item in (candidate, normalized_candidate, normalize_symbol_root(candidate)):
            normalized_item = str(item or "").strip().upper()
            if normalized_item and normalized_item not in candidates:
                candidates.append(normalized_item)
    return candidates


def fetch_tradingview_atr_snapshot(symbol, reference_time=None):
    if reference_time is None:
        reference_time = datetime.now()

    state = load_trade_manager_state()
    tradingview_atr = state.get("tradingview_atr") or {}
    if not isinstance(tradingview_atr, dict):
        return None

    atr_record = None
    for candidate in build_tradingview_atr_candidates(symbol):
        candidate_record = tradingview_atr.get(candidate)
        if isinstance(candidate_record, dict):
            atr_record = candidate_record
            break

    if not atr_record:
        return None

    atr_value = atr_record.get("atr_value")
    received_at = atr_record.get("received_at")
    received_at_dt = parse_iso_timestamp(received_at)
    if atr_value is None or received_at_dt is None:
        return None

    age_seconds = (reference_time.replace(tzinfo=received_at_dt.tzinfo) - received_at_dt).total_seconds()
    if age_seconds > TRADINGVIEW_ATR_MAX_AGE_SECONDS:
        return None

    try:
        atr_value = float(atr_value)
    except (TypeError, ValueError):
        return None

    if atr_value <= 0:
        return None

    return {
        "ok": True,
        "symbol": str(symbol or "").upper(),
        "atr_source": "tradingview_atr_relay",
        "atr_value": atr_value,
        "bar_timestamp": received_at,
        "completed_bars": len(COMPLETED_1M_BARS.get(str(symbol or "").upper(), [])),
    }


def select_snapshot_atr(symbol, reference_time=None):
    tradingview_snapshot = fetch_tradingview_atr_snapshot(symbol, reference_time=reference_time)
    if tradingview_snapshot:
        return tradingview_snapshot
    return compute_atr_14(symbol, reference_time=reference_time)


def resolve_fill_price(symbol, *, direction=None, order_id=None, trade_id=None):
    submitted_symbol = str(symbol or "").upper()
    resolved_symbol, resolution_source = resolve_execution_symbol(submitted_symbol)
    normalized_requested_symbol = str(submitted_symbol or "").strip().upper()
    if (
        normalized_requested_symbol in LAST_PRICES
        and normalized_requested_symbol != normalize_symbol_root(normalized_requested_symbol)
    ):
        resolved_symbol = normalized_requested_symbol
        resolution_source = "exact_last_price_symbol"

    log(f"SUBMIT FLOW fill_lookup_symbol submitted={submitted_symbol} resolved={resolved_symbol} source={resolution_source}")
    log(
        "SUBMIT FLOW "
        f"live_price_cache_present={resolved_symbol in LAST_PRICES} "
        f"current_bar_present={resolved_symbol in CURRENT_1M_BARS}"
    )

    reference_time = datetime.now()
    lookup_key = resolved_symbol
    last_price_timestamp = LAST_PRICE_TIMESTAMPS.get(lookup_key)
    last_tick_age = seconds_since(last_price_timestamp, reference_time)
    max_tick_age = get_entry_fill_last_tick_max_age_seconds(resolved_symbol)
    price_is_valid, listener_freshness = is_valid_entry_execution_price(
        lookup_key,
        reference_time,
        max_tick_age_seconds=max_tick_age,
    )

    if not price_is_valid:
        audit = build_fill_audit(
            requested_symbol=submitted_symbol,
            execution_symbol=resolved_symbol,
            direction=direction,
            selected_fill_price=None,
            fill_price_source=None,
            last_prices_lookup_key=lookup_key,
            order_id=order_id,
            trade_id=trade_id,
            fallback_used=False,
            resolution_source=resolution_source,
            rejected_reason="stale_or_missing_execution_price",
            reference_time=reference_time,
        )
        audit["entry_fill_last_tick_max_age_seconds"] = max_tick_age
        audit["listener_last_tick_max_age_seconds"] = listener_freshness.get("listener_last_tick_max_age_seconds")
        audit["listener_status"] = listener_freshness.get("listener_status")
        audit["listener_status_reason"] = listener_freshness.get("listener_status_reason")
        persist_fill_audit(audit)
        log(
            f"ENTRY FILL REJECTED [{trade_id}] {submitted_symbol} "
            f"resolved_symbol={resolved_symbol} reason=stale_or_missing_execution_price "
            f"last_tick_age_seconds={audit['last_tick_age_seconds']} "
            f"max_age_seconds={max_tick_age}"
        )
        raise EntryFillRejected("stale_or_missing_execution_price", audit)

    live_price = float(LAST_PRICES[lookup_key])
    fill_price_source = "executor_actual_fill"
    current_bar = CURRENT_1M_BARS.get(resolved_symbol)
    current_bar_age = seconds_since(
        current_bar.get("bar_timestamp") if current_bar else None,
        reference_time,
    )

    if current_bar and current_bar_age is not None and current_bar_age <= LISTENER_CURRENT_BAR_MAX_AGE_SECONDS:
        tolerance = float(get_tick_size(resolved_symbol))
        bar_low = float(current_bar["low"])
        bar_high = float(current_bar["high"])
        if live_price < bar_low - tolerance or live_price > bar_high + tolerance:
            audit = build_fill_audit(
                requested_symbol=submitted_symbol,
                execution_symbol=resolved_symbol,
                direction=direction,
                selected_fill_price=live_price,
                fill_price_source=fill_price_source,
                last_prices_lookup_key=lookup_key,
                order_id=order_id,
                trade_id=trade_id,
                fallback_used=False,
                resolution_source=resolution_source,
                rejected_reason="fill_price_outside_current_bar_range",
                reference_time=reference_time,
            )
            audit["current_bar_range_tolerance"] = tolerance
            persist_fill_audit(audit)
            log(
                f"ENTRY FILL REJECTED [{trade_id}] {submitted_symbol} "
                f"resolved_symbol={resolved_symbol} reason=fill_price_outside_current_bar_range "
                f"fill_price={live_price} low={bar_low} high={bar_high} tolerance={tolerance}"
            )
            raise EntryFillRejected("fill_price_outside_current_bar_range", audit)

    audit = build_fill_audit(
        requested_symbol=submitted_symbol,
        execution_symbol=resolved_symbol,
        direction=direction,
        selected_fill_price=live_price,
        fill_price_source=fill_price_source,
        last_prices_lookup_key=lookup_key,
        order_id=order_id,
        trade_id=trade_id,
        fallback_used=False,
        resolution_source=resolution_source,
        reference_time=reference_time,
    )
    audit["entry_fill_last_tick_max_age_seconds"] = max_tick_age
    audit["listener_last_tick_max_age_seconds"] = listener_freshness.get("listener_last_tick_max_age_seconds")
    audit["listener_status"] = listener_freshness.get("listener_status")
    audit["listener_status_reason"] = listener_freshness.get("listener_status_reason")
    persist_fill_audit(audit)
    log(f"SUBMIT FLOW live_price_found symbol={resolved_symbol} source=last_price_cache price={live_price}")
    return live_price, fill_price_source, resolved_symbol


def build_executor_state():
    return {
        "version": STATE_VERSION,
        "saved_at": datetime.now().isoformat(),
        "orders": ORDERS,
        "positions": POSITIONS,
    }


def atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            delete=False
        ) as tmp_file:
            json.dump(payload, tmp_file, indent=2)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
            temp_path = Path(tmp_file.name)

        os.replace(temp_path, path)

    except Exception:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise


def save_executor_state():
    global EXECUTOR_STATE_SAVED_AT

    payload = build_executor_state()

    try:
        atomic_write_json(EXECUTOR_STATE_FILE, payload)
        EXECUTOR_STATE_SAVED_AT = payload["saved_at"]

        log(
            f"STATE SAVED file={EXECUTOR_STATE_FILE} "
            f"orders={len(ORDERS)} "
            f"positions={len(POSITIONS)} "
            f"saved_at={EXECUTOR_STATE_SAVED_AT}"
        )

        return True

    except Exception as e:
        log(f"STATE SAVE FAILED file={EXECUTOR_STATE_FILE} error={e}")
        return False


def load_executor_state():
    global EXECUTOR_STATE_LOADED, EXECUTOR_STATE_SAVED_AT

    if not EXECUTOR_STATE_FILE.exists():
        ORDERS.clear()
        POSITIONS.clear()
        EXECUTOR_STATE_LOADED = True
        EXECUTOR_STATE_SAVED_AT = None

        log(f"NO PERSISTED EXECUTOR STATE file={EXECUTOR_STATE_FILE}")
        return

    try:
        with EXECUTOR_STATE_FILE.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        orders = payload.get("orders", {})
        positions = payload.get("positions", {})

        if not isinstance(orders, dict):
            raise ValueError("Persisted orders must be dict")

        if not isinstance(positions, dict):
            raise ValueError("Persisted positions must be dict")

        ORDERS.clear()
        ORDERS.update(orders)

        POSITIONS.clear()
        POSITIONS.update(positions)

        EXECUTOR_STATE_LOADED = True
        EXECUTOR_STATE_SAVED_AT = payload.get("saved_at")

        log(
            f"STATE LOADED file={EXECUTOR_STATE_FILE} "
            f"orders={len(ORDERS)} "
            f"positions={len(POSITIONS)} "
            f"saved_at={EXECUTOR_STATE_SAVED_AT}"
        )

    except Exception as e:
        ORDERS.clear()
        POSITIONS.clear()
        EXECUTOR_STATE_LOADED = False
        EXECUTOR_STATE_SAVED_AT = None

        log(f"STATE LOAD FAILED file={EXECUTOR_STATE_FILE} error={e}")


def active_orders_for_trade(trade_id, order_type=None):
    results = []
    for order in ORDERS.values():
        if order.get("trade_id") != trade_id:
            continue
        if order_type and order.get("type") != order_type:
            continue
        if not is_working_order(order):
            continue
        results.append(order)
    return results


def active_orders_for_symbol(symbol):
    symbol = str(symbol or "").upper()
    results = []
    for order in ORDERS.values():
        if str(order.get("symbol", "")).upper() != symbol:
            continue
        if not is_working_order(order):
            continue
        results.append(order)
    return results


def stop_prices_match(left, right, tolerance=0.01):
    try:
        return abs(round(float(left), 2) - round(float(right), 2)) <= tolerance
    except (TypeError, ValueError):
        return False


def active_stop_matches_request(order, trade_id, symbol, qty, stop_price):
    if not order:
        return False
    if order.get("trade_id") != trade_id:
        return False
    if order.get("type") != "stop":
        return False
    if not is_working_order(order):
        return False
    if str(order.get("symbol", "")).upper() != str(symbol or "").upper():
        return False

    try:
        existing_qty = float(order.get("qty", 0) or 0)
        requested_qty = float(qty or 0)
    except (TypeError, ValueError):
        return False

    return existing_qty == requested_qty and stop_prices_match(order.get("stop_price"), stop_price)


def default_oco_group(trade_id):
    trade_text = str(trade_id or "").strip()
    return f"OCO-{trade_text}-PROTECTIVE" if trade_text else None


def order_oco_group(order):
    if not isinstance(order, dict):
        return None
    group = order.get("oco_group") or order.get("oco_group_id")
    return str(group).strip() if group else None


def cancel_oco_peers(trigger_order, timestamp, reason):
    group = order_oco_group(trigger_order)
    if not group:
        return []

    affected = []
    trigger_order_id = trigger_order.get("order_id")
    for order in active_orders_for_trade(trigger_order.get("trade_id")):
        if order.get("order_id") == trigger_order_id:
            continue
        if order_oco_group(order) != group:
            continue
        order["status"] = "cancelled"
        order["cancelled_at"] = timestamp
        order["closed_reason"] = reason
        order["oco_cancelled_by"] = trigger_order_id
        affected.append(order["order_id"])
    return affected


def clear_working_orders_for_flat_symbol(symbol, reason):
    symbol = str(symbol or "").upper()
    if not symbol:
        return []

    position_qty = float((POSITIONS.get(symbol) or {}).get("qty", 0) or 0)
    if position_qty != 0:
        return []

    timestamp = datetime.now().isoformat()
    affected = []
    for order in active_orders_for_symbol(symbol):
        order["status"] = "cancelled"
        order["cancelled_at"] = timestamp
        order["closed_reason"] = reason
        affected.append(order["order_id"])

    if affected:
        log(f"ORPHAN WORKING ORDERS CLEARED symbol={symbol} reason={reason} orders={affected}")

    return affected


def stop_triggered_for_position(position_qty, price, stop_price):
    position_qty = float(position_qty or 0)
    price = float(price)
    stop_price = float(stop_price)

    if position_qty < 0:
        return price >= stop_price

    if position_qty > 0:
        return price <= stop_price

    return False


def limit_triggered_for_position(position_qty, price, limit_price):
    position_qty = float(position_qty or 0)
    price = float(price)
    limit_price = float(limit_price)

    if position_qty < 0:
        return price <= limit_price

    if position_qty > 0:
        return price >= limit_price

    return False


def resize_active_stops_for_trade_symbol(trade_id, symbol, remaining_qty, timestamp):
    affected = []
    remaining_qty = float(remaining_qty or 0)

    for order in active_orders_for_trade(trade_id, "stop"):
        if str(order.get("symbol", "")).upper() != symbol:
            continue

        if remaining_qty <= 0:
            order["status"] = "closed"
            order["closed_at"] = timestamp
            order["closed_reason"] = "closed_after_limit_flat"
        else:
            order["qty"] = remaining_qty
            order["updated_at"] = timestamp
            order["update_reason"] = "resized_after_limit_fill"
            if order.get("oco_role") == "protective_stop":
                order["oco_parent_group"] = order_oco_group(order)
                order["oco_group"] = None
                order["oco_role"] = "runner_stop"

        affected.append(order["order_id"])

    return affected


def close_active_orders_for_trade_symbol(trade_id, symbol, timestamp, reason):
    affected = []
    for order in active_orders_for_trade(trade_id):
        if str(order.get("symbol", "")).upper() != symbol:
            continue
        order["status"] = "closed"
        order["closed_at"] = timestamp
        order["closed_reason"] = reason
        affected.append(order["order_id"])
    return affected


def flatten_all_positions_and_cancel_working_orders(reason):
    timestamp = datetime.now().isoformat()
    reason = str(reason or "global_flatten")
    flattened_symbols = []
    cancelled_order_ids = []

    log(f"kill_switch_global_flatten_started reason={reason}")

    for symbol, position in list(POSITIONS.items()):
        qty = float((position or {}).get("qty", 0) or 0)
        if qty == 0:
            continue

        POSITIONS[symbol] = {
            "qty": 0.0,
            "avg_entry_price": 0.0,
            "updated_at": timestamp,
            "closed_reason": reason,
        }
        flattened_symbols.append(symbol)
        log(f"kill_switch_symbol_flattened symbol={symbol} previous_qty={qty}")

    for order in list(ORDERS.values()):
        if not is_working_order(order):
            continue

        order["status"] = "cancelled"
        order["cancelled_at"] = timestamp
        order["closed_reason"] = reason
        cancelled_order_ids.append(order["order_id"])
        log(
            "kill_switch_active_order_cancelled "
            f"order_id={order.get('order_id')} trade_id={order.get('trade_id')} "
            f"symbol={order.get('symbol')} type={order.get('type')}"
        )

    log(
        "kill_switch_global_flatten_complete "
        f"flattened_symbols={flattened_symbols} cancelled_order_ids={cancelled_order_ids}"
    )

    return {
        "flattened_symbols": flattened_symbols,
        "cancelled_order_ids": cancelled_order_ids,
        "timestamp": timestamp,
    }


def evaluate_stop_fills_for_symbol(symbol, price):
    symbol = str(symbol or "").upper()
    if not symbol:
        return []

    position = POSITIONS.get(symbol, {})
    position_qty = float(position.get("qty", 0) or 0)
    if position_qty == 0:
        return []

    triggered = []
    timestamp = datetime.now().isoformat()

    for order in list(active_orders_for_symbol(symbol)):
        if order.get("type") != "stop":
            continue

        stop_price = float(order.get("stop_price", 0))
        if not stop_triggered_for_position(position_qty, price, stop_price):
            continue

        trade_id = order.get("trade_id")
        order["status"] = "closed"
        order["closed_at"] = timestamp
        order["filled_at"] = timestamp
        order["filled_price"] = float(stop_price)
        order["fill_trigger_price"] = float(price)
        order["closed_reason"] = "stop_triggered"

        affected = cancel_oco_peers(order, timestamp, "oco_cancel_after_stop_fill")
        if not affected:
            affected = close_active_orders_for_trade_symbol(
                trade_id,
                symbol,
                timestamp,
                "closed_after_stop_trigger",
            )
            if order["order_id"] in affected:
                affected.remove(order["order_id"])

        affected.append(order["order_id"])

        POSITIONS[symbol] = {
            "qty": 0.0,
            "avg_entry_price": 0.0,
            "updated_at": timestamp,
        }
        orphan_orders = clear_working_orders_for_flat_symbol(symbol, "cleared_after_stop_flat")
        for orphan_order_id in orphan_orders:
            if orphan_order_id not in affected:
                affected.append(orphan_order_id)

        triggered.append({
            "trade_id": trade_id,
            "stop_order_id": order["order_id"],
            "symbol": symbol,
            "stop_price": stop_price,
            "trigger_price": float(price),
            "affected_orders": affected,
        })

        position_qty = 0.0
        break

    return triggered


def evaluate_limit_fills_for_symbol(symbol, price):
    symbol = str(symbol or "").upper()
    if not symbol:
        return []

    position = POSITIONS.get(symbol, {})
    position_qty = float(position.get("qty", 0) or 0)
    if position_qty == 0:
        return []

    triggered = []
    timestamp = datetime.now().isoformat()

    for order in list(active_orders_for_symbol(symbol)):
        if order.get("type") != "limit":
            continue

        current_position = POSITIONS.get(symbol, {})
        position_qty = float(current_position.get("qty", 0) or 0)
        if position_qty == 0:
            break

        limit_price = float(order.get("limit_price", 0))
        if not limit_triggered_for_position(position_qty, price, limit_price):
            continue

        trade_id = order.get("trade_id")
        requested_qty = abs(float(order.get("qty", 0) or 0))
        filled_qty = min(requested_qty, abs(position_qty))

        if position_qty < 0:
            new_qty = position_qty + filled_qty
        else:
            new_qty = position_qty - filled_qty

        if abs(new_qty) < 1e-9:
            new_qty = 0.0

        order["status"] = "closed"
        order["closed_at"] = timestamp
        order["filled_at"] = timestamp
        order["filled_price"] = limit_price
        order["fill_trigger_price"] = float(price)
        order["filled_qty"] = filled_qty
        order["closed_reason"] = "limit_triggered"

        if new_qty == 0:
            POSITIONS[symbol] = {
                "qty": 0.0,
                "avg_entry_price": 0.0,
                "updated_at": timestamp,
            }
            clear_working_orders_for_flat_symbol(symbol, "cleared_after_limit_flat")
        else:
            POSITIONS[symbol] = {
                "qty": new_qty,
                "avg_entry_price": float(current_position.get("avg_entry_price", 0) or 0),
                "updated_at": timestamp,
            }

        remaining_qty = abs(new_qty)
        resized_stops = resize_active_stops_for_trade_symbol(
            trade_id,
            symbol,
            remaining_qty,
            timestamp,
        )

        triggered.append({
            "trade_id": trade_id,
            "limit_order_id": order["order_id"],
            "symbol": symbol,
            "limit_price": limit_price,
            "trigger_price": float(price),
            "filled_qty": filled_qty,
            "remaining_qty": remaining_qty,
            "resized_stop_orders": resized_stops,
        })

    return triggered


# =========================
# HEALTH / DEBUG
# =========================
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "service": "executor",
        "active_orders": len([o for o in ORDERS.values() if o.get("status") == "active"])
    })


@app.route("/orders", methods=["GET"])
def orders():
    return jsonify({
        "ok": True,
        "orders": list(ORDERS.values())
    })


@app.route("/positions", methods=["GET"])
def positions():
    return jsonify({
        "ok": True,
        "positions": POSITIONS
    })


@app.route("/debug/live_prices", methods=["GET"])
def debug_live_prices():
    return jsonify({
        "ok": True,
        "cached_symbols": sorted(LAST_PRICES.keys()),
        "last_prices": {symbol: float(price) for symbol, price in LAST_PRICES.items()},
        "current_1m_bars": {
            symbol: serialize_bar(bar)
            for symbol, bar in CURRENT_1M_BARS.items()
        }
    })


@app.route("/debug/feed_health", methods=["GET"])
def debug_feed_health():
    payload = read_rithmic_feed_health()
    symbols = payload.get("symbols") or {}
    return jsonify({
        "ok": True,
        "warning": payload.get("warning"),
        "system_state_feed": payload.get("system_state_feed"),
        "symbols": {
            symbol: {
                "feed_status": entry.get("feed_status"),
                "last_tick_timestamp": entry.get("last_tick_timestamp_utc"),
                "last_bar_timestamp": entry.get("last_bar_timestamp_utc"),
                "last_atr_timestamp": entry.get("last_atr_timestamp_utc"),
                "last_bridge_post_timestamp": entry.get("last_bridge_post_timestamp_utc"),
            }
            for symbol, entry in symbols.items()
            if isinstance(entry, dict)
        },
    })


@app.route("/listener_feed_health", methods=["GET"])
def listener_feed_health():
    try:
        path = "C:\\Webhook\\RandleSystem\\Data\\rithmic_feed_health.json"

        if not os.path.exists(path):
            return {"ok": False, "status": "missing"}

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return {"ok": True, "data": data}

    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.route("/debug/watchdog", methods=["GET"])
def debug_watchdog():
    return jsonify(build_watchdog_state())


@app.route("/debug/watchdog_alert", methods=["GET"])
def debug_watchdog_alert():
    state = build_watchdog_state()
    return jsonify({
        "status": state["status"],
        "last_valid_tick_timestamp": state["last_valid_tick_timestamp"],
        "last_valid_tick_symbol": state["last_valid_tick_symbol"],
        "seconds_since_last_valid_tick": state["seconds_since_last_valid_tick"],
        "is_stale": state["status"] == "STALE",
        "auto_restart_enabled": state["auto_restart_enabled"],
        "restart_eligible": state["restart_eligible"],
        "seconds_until_restart": state["seconds_until_restart"],
        "restart_action": state.get("restart_action"),
    })


@app.route("/sync_snapshot", methods=["GET"])
def sync_snapshot():
    snapshot_time = datetime.now()
    symbols = set(POSITIONS.keys())
    symbols.update(LAST_PRICES.keys())
    symbols.update(LAST_PRICE_TIMESTAMPS.keys())
    symbols.update(CURRENT_1M_BARS.keys())
    symbols.update(COMPLETED_1M_BARS.keys())

    for order in ORDERS.values():
        sym = str(order.get("symbol", "")).upper()
        if sym:
            symbols.add(sym)

    cleared_orphans = []
    for symbol in sorted(symbols):
        cleared_orphans.extend(
            clear_working_orders_for_flat_symbol(symbol, "cleared_before_flat_snapshot")
        )
    if cleared_orphans:
        save_executor_state()

    snapshot = {}

    for symbol in sorted(symbols):
        pos = POSITIONS.get(symbol, {
            "qty": 0.0,
            "avg_entry_price": 0.0
        })

        working_orders = []
        stop_order = None

        for order in ORDERS.values():
            if str(order.get("symbol", "")).upper() != symbol:
                continue
            if not is_working_order(order):
                continue

            normalized = {
                "order_id": order.get("order_id"),
                "trade_id": order.get("trade_id"),
                "type": order.get("type"),
                "symbol": symbol,
                "qty": float(order.get("qty", 0))
            }

            if order.get("type") == "stop":
                normalized["stop_price"] = float(order.get("stop_price", 0))
                if stop_order is None:
                    stop_order = normalized

            if order.get("type") == "limit":
                normalized["limit_price"] = float(order.get("limit_price", 0))

            if order.get("tag"):
                normalized["tag"] = order.get("tag")

            working_orders.append(normalized)

        snapshot[symbol] = {
            "position_qty": float(pos.get("qty", 0)),
            "avg_entry_price": float(pos.get("avg_entry_price", 0)),
            "is_flat": float(pos.get("qty", 0)) == 0,
            "working_orders": working_orders,
            "has_stop": stop_order is not None,
            "stop_order": stop_order
        }

        atr_snapshot = select_snapshot_atr(symbol, reference_time=snapshot_time)
        snapshot[symbol]["last_price"] = float(LAST_PRICES.get(symbol, 0)) if symbol in LAST_PRICES else None
        snapshot[symbol]["listener_tick_id"] = LAST_PRICE_LISTENER_TICK_IDS.get(symbol)
        snapshot[symbol]["executor_tick_id"] = LAST_PRICE_LISTENER_TICK_IDS.get(symbol)
        snapshot[symbol]["listener_sequence"] = LAST_PRICE_LISTENER_SEQUENCES.get(symbol)
        snapshot[symbol]["executor_sequence"] = LAST_PRICE_EXECUTOR_SEQUENCES.get(symbol)
        snapshot[symbol]["last_10_executor_accepted_prices"] = executor_history_for_symbol(symbol, EXECUTOR_ACCEPTED_PRICE_HISTORY)
        snapshot[symbol]["last_10_executor_reject_reasons"] = executor_history_for_symbol(symbol, EXECUTOR_REJECT_HISTORY)
        listener_copy = build_listener_freshness(symbol, snapshot_time)
        snapshot[symbol].update(listener_copy)
        snapshot[symbol]["executor_listener_status_copy"] = listener_copy.get("listener_status")
        snapshot[symbol]["executor_listener_status_reason_copy"] = listener_copy.get("listener_status_reason")
        snapshot[symbol]["listener_status"] = "non_authoritative"
        snapshot[symbol]["listener_status_reason"] = "executor_snapshot_is_not_feed_authority"
        snapshot[symbol]["listener_fields_authority"] = "non_authoritative_executor_copy"
        snapshot[symbol]["listener_fields_note"] = (
            "last_tick_age_seconds and listener_last_tick_max_age_seconds are copied diagnostics only; "
            "executor_listener_status_copy is executor-local state only; use listener/feed-health for market liveness"
        )
        snapshot[symbol]["current_1m_bar"] = serialize_bar(CURRENT_1M_BARS[symbol]) if symbol in CURRENT_1M_BARS else None
        snapshot[symbol]["completed_1m_bars"] = int(atr_snapshot.get("completed_bars", len(COMPLETED_1M_BARS.get(symbol, []))))

        if atr_snapshot.get("ok"):
            snapshot[symbol]["atr_1m_14"] = float(atr_snapshot["atr_value"])
            snapshot[symbol]["atr_source"] = atr_snapshot["atr_source"]
            snapshot[symbol]["atr_bar_timestamp"] = atr_snapshot["bar_timestamp"]
            snapshot[symbol]["atr_status"] = "ready"
            snapshot[symbol]["atr_error"] = None
            snapshot[symbol]["atr_trade_approved"] = atr_snapshot["atr_source"] == "tradingview_atr_relay"
            snapshot[symbol]["atr_policy"] = (
                "trade_entry_approved"
                if snapshot[symbol]["atr_trade_approved"]
                else "diagnostic_only_not_trade_approved"
            )
        else:
            snapshot[symbol]["atr_1m_14"] = None
            snapshot[symbol]["atr_source"] = atr_snapshot.get("atr_source", "live_executor_1m14")
            snapshot[symbol]["atr_bar_timestamp"] = None
            snapshot[symbol]["atr_status"] = "not_ready"
            snapshot[symbol]["atr_error"] = atr_snapshot.get("error", "ATR_NOT_READY")
            snapshot[symbol]["atr_trade_approved"] = False
            snapshot[symbol]["atr_policy"] = "diagnostic_only_not_trade_approved"

    return jsonify({
        "ok": True,
        "snapshot_scope": "execution_state_only",
        "market_liveness_authority": "listener_feed_health",
        "listener_fields_authority": "non_authoritative_executor_copy",
        "listener_fields_note": (
            "Per-symbol listener_status is a non-authoritative marker; "
            "executor_listener_status_copy, last_tick_age_seconds, and "
            "listener_last_tick_max_age_seconds remain for legacy diagnostics only"
        ),
        "symbols": snapshot
    })


# =========================
# EXECUTION ENDPOINT
# =========================
@app.route("/execute", methods=["POST"])
def execute():
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"ok": False, "message": "Invalid execution payload"}), 400

    action = data.get("action")
    trade_id = data.get("trade_id")
    symbol = str(data.get("symbol", "")).upper() if data.get("symbol") else None

    safety = validate_execution_safety(data)
    if not safety["ok"]:
        context = safety["context"]
        log(
            "EXECUTION SAFETY REJECTED "
            f"reason={safety['reason']} "
            f"mode={context['mode']} "
            f"allow_live_trading={context['allow_live_trading']} "
            f"account_present={context['account_present']} "
            f"approved_account_substring_configured={context['approved_account_substring_configured']}"
        )
        return jsonify({
            "ok": False,
            "error": "execution_safety_rejected",
            "reason": safety["reason"],
            "context": context,
        }), 409

    risk_caps = validate_order_risk_caps(data)
    if not risk_caps["ok"]:
        log(
            "ORDER RISK CAP REJECTED "
            f"reason={risk_caps['reason']} action={action} symbol={symbol}"
        )
        return jsonify({
            "ok": False,
            "error": "order_risk_cap_rejected",
            "reason": risk_caps["reason"],
        }), 409

    log(
        "EXECUTOR RECEIVED "
        f"action={action} trade_id={trade_id} symbol={symbol} "
        f"safety_context={safety['context']}"
    )

    if not action:
        return jsonify({"ok": False, "message": "Missing action"}), 400

    watchdog_rejection = reject_if_watchdog_blocks_action(action)
    if watchdog_rejection:
        return watchdog_rejection

    # =========================
    # ENTRY
    # =========================
    if action == "submit_entry":
        if not trade_id or not symbol:
            return jsonify({"ok": False, "message": "Missing trade_id or symbol"}), 400

        order_id = make_id("ENTRY")

        ORDERS[order_id] = {
            "order_id": order_id,
            "trade_id": trade_id,
            "type": "entry",
            "symbol": symbol,
            "direction": data.get("direction"),
            "qty": float(data.get("qty", 0)),
            "status": "filled",
            "filled_at": datetime.now().isoformat()
        }

        qty = float(data.get("qty", 0))
        direction = str(data.get("direction", "")).lower()
        submitted_symbol = symbol
        resolved_symbol, resolution_source = resolve_execution_symbol(submitted_symbol)
        log(
            f"SUBMIT FLOW submit_symbol_received symbol={submitted_symbol}"
        )
        log(
            f"SUBMIT FLOW submit_symbol_resolved submitted={submitted_symbol} "
            f"resolved={resolved_symbol} source={resolution_source}"
        )
        try:
            entry_price, fill_price_source, fill_lookup_symbol = resolve_fill_price(
                submitted_symbol,
                direction=direction,
                order_id=order_id,
                trade_id=trade_id,
            )
        except EntryFillRejected as exc:
            log(f"ENTRY REJECTED [{trade_id}] {submitted_symbol} reason={exc.reason}")
            ORDERS[order_id]["status"] = "rejected"
            ORDERS[order_id]["rejected_at"] = datetime.now().isoformat()
            ORDERS[order_id]["reject_reason"] = exc.reason
            ORDERS[order_id]["resolved_symbol"] = resolved_symbol
            save_executor_state()
            return jsonify({
                "ok": False,
                "message": "Entry rejected",
                "error": exc.reason,
                "reject_reason": exc.reason,
                "fill_audit": exc.audit,
                "broker_order_id": order_id,
                "order": ORDERS[order_id]
            }), 409
        except ValueError as exc:
            log(f"ENTRY REJECTED [{trade_id}] {submitted_symbol} reason={exc}")
            ORDERS[order_id]["status"] = "rejected"
            ORDERS[order_id]["rejected_at"] = datetime.now().isoformat()
            ORDERS[order_id]["reject_reason"] = str(exc)
            ORDERS[order_id]["resolved_symbol"] = resolved_symbol
            save_executor_state()
            return jsonify({
                "ok": False,
                "message": "Live fill price unavailable",
                "error": str(exc),
                "broker_order_id": order_id,
                "order": ORDERS[order_id]
            }), 409

        ORDERS[order_id]["filled_price"] = entry_price
        ORDERS[order_id]["fill_price_source"] = fill_price_source
        ORDERS[order_id]["resolved_symbol"] = fill_lookup_symbol

        signed_qty = qty if direction == "long" else -qty

        current = POSITIONS.get(fill_lookup_symbol, {
            "qty": 0.0,
            "avg_entry_price": 0.0
        })

        new_qty = current["qty"] + signed_qty

        log(
            f"📌 POSITION UPDATE {fill_lookup_symbol} "
            f"current_qty={current['qty']} "
            f"signed_qty={signed_qty} "
            f"new_qty={new_qty} "
            f"entry_price={entry_price}"
        )

        if new_qty == 0:
            POSITIONS[fill_lookup_symbol] = {
                "qty": 0.0,
                "avg_entry_price": 0.0,
                "updated_at": datetime.now().isoformat()
            }

        elif current["qty"] == 0 or (
            current["qty"] > 0 and new_qty > 0
        ) or (
            current["qty"] < 0 and new_qty < 0
        ):
            old_abs = abs(current["qty"])
            add_abs = abs(signed_qty)

            avg = (
                (old_abs * current["avg_entry_price"]) +
                (add_abs * entry_price)
            ) / (old_abs + add_abs)

            POSITIONS[fill_lookup_symbol] = {
                "qty": new_qty,
                "avg_entry_price": avg,
                "updated_at": datetime.now().isoformat()
            }

        else:
            POSITIONS[fill_lookup_symbol] = {
                "qty": new_qty,
                "avg_entry_price": entry_price,
                "updated_at": datetime.now().isoformat()
            }

        log(
            f"✅ ENTRY FILLED [{trade_id}] {submitted_symbol} resolved_symbol={fill_lookup_symbol} "
            f"qty={ORDERS[order_id]['qty']} fill_price={entry_price} "
            f"fill_price_source={fill_price_source}"
        )

        save_executor_state()

        return jsonify({
            "ok": True,
            "message": "Entry filled",
            "broker_order_id": order_id,
            "fill_price": entry_price,
            "fill_price_source": fill_price_source,
            "resolved_symbol": fill_lookup_symbol,
            "order": ORDERS[order_id]
        })

    # =========================
    # STOP
    # =========================
    if action == "submit_stop":
        log("🔥 STOP PROTECTION CHECK RUNNING")

        if not trade_id or not symbol:
            return jsonify({"ok": False, "message": "Missing trade_id or symbol"}), 400

        stop_price = data.get("stop_price")
        if stop_price is None:
            return jsonify({"ok": False, "message": "Missing stop_price"}), 400

        requested_qty = data.get("qty", 0)
        existing_stops = active_orders_for_trade(trade_id, "stop")
        replacement_for_order_id = data.get("replacement_for_order_id")
        is_stop_replacement = bool(replacement_for_order_id) or data.get("tag") in {
            "be_replacement",
            "stop_replacement",
        }
        if existing_stops:
            for existing_stop in existing_stops:
                if active_stop_matches_request(existing_stop, trade_id, symbol, requested_qty, stop_price):
                    log(
                        "duplicate_stop_idempotent "
                        f"trade_id={trade_id} symbol={symbol} "
                        f"stop_price={existing_stop.get('stop_price')} qty={existing_stop.get('qty')} "
                        f"order_id={existing_stop.get('order_id')}"
                    )
                    return jsonify({
                        "ok": True,
                        "message": "duplicate_stop_idempotent",
                        "broker_order_id": existing_stop["order_id"],
                        "order": existing_stop,
                        "idempotent": True,
                        "existing_stop_ids": [existing_stop["order_id"]],
                        "stop_fills": []
                    })

            if not is_stop_replacement:
                return jsonify({
                    "ok": False,
                    "message": "Active stop already exists for this trade",
                    "existing_stop_ids": [o["order_id"] for o in existing_stops]
                }), 400

        order_id = make_id("STOP")

        ORDERS[order_id] = {
            "order_id": order_id,
            "trade_id": trade_id,
            "type": "stop",
            "tag": data.get("tag"),
            "replacement_for_order_id": replacement_for_order_id,
            "oco_group": data.get("oco_group") or default_oco_group(trade_id),
            "oco_role": data.get("oco_role") or "protective_stop",
            "symbol": symbol,
            "stop_price": float(stop_price),
            "qty": float(requested_qty),
            "status": "active",
            "created_at": datetime.now().isoformat()
        }

        log(
            f"🛑 STOP PLACED [{trade_id}] {symbol} "
            f"stop={ORDERS[order_id]['stop_price']} qty={ORDERS[order_id]['qty']}"
        )

        stop_fills = []
        if symbol in LAST_PRICES:
            stop_fills = evaluate_stop_fills_for_symbol(symbol, LAST_PRICES[symbol])
            if stop_fills:
                log(f"STOP FILLED IMMEDIATELY [{trade_id}] fills={stop_fills}")

        save_executor_state()

        return jsonify({
            "ok": True,
            "message": "Stop submitted",
            "broker_order_id": order_id,
            "order": ORDERS[order_id],
            "stop_fills": stop_fills
        })

    # =========================
    # LIMIT
    # =========================
    if action == "submit_limit":
        if not trade_id or not symbol:
            return jsonify({"ok": False, "message": "Missing trade_id or symbol"}), 400

        existing_limits = active_orders_for_trade(trade_id, "limit")
        if existing_limits:
            return jsonify({
                "ok": False,
                "message": "Active limit already exists for this trade",
                "existing_limit_ids": [o["order_id"] for o in existing_limits]
            }), 400

        order_id = make_id("LIMIT")

        ORDERS[order_id] = {
            "order_id": order_id,
            "trade_id": trade_id,
            "type": "limit",
            "tag": data.get("tag"),
            "oco_group": data.get("oco_group") or default_oco_group(trade_id),
            "oco_role": data.get("oco_role") or "tp1_limit",
            "symbol": symbol,
            "limit_price": float(data.get("limit_price")),
            "qty": float(data.get("qty", 0)),
            "status": "active",
            "created_at": datetime.now().isoformat()
        }

        log(
            f"🎯 LIMIT PLACED [{trade_id}] {symbol} "
            f"limit={ORDERS[order_id]['limit_price']} qty={ORDERS[order_id]['qty']}"
        )

        limit_fills = []
        if symbol in LAST_PRICES:
            limit_fills = evaluate_limit_fills_for_symbol(symbol, LAST_PRICES[symbol])
            if limit_fills:
                log(f"LIMIT FILLED IMMEDIATELY [{trade_id}] fills={limit_fills}")

        save_executor_state()

        return jsonify({
            "ok": True,
            "message": "Limit submitted",
            "broker_order_id": order_id,
            "order": ORDERS[order_id],
            "limit_fills": limit_fills
        })

    # =========================
    # MODIFY ACTIVE STOP
    # =========================
    if action == "modify_stop":
        if not trade_id or not symbol:
            return jsonify({"ok": False, "message": "Missing trade_id or symbol"}), 400

        broker_order_id = data.get("broker_order_id")
        stop_price = data.get("stop_price")
        if not broker_order_id:
            return jsonify({"ok": False, "message": "Missing broker_order_id"}), 400
        if stop_price is None:
            return jsonify({"ok": False, "message": "Missing stop_price"}), 400

        order = ORDERS.get(broker_order_id)
        if not order:
            return jsonify({"ok": False, "message": "Order not found"}), 404
        if order.get("trade_id") != trade_id or str(order.get("symbol", "")).upper() != symbol:
            return jsonify({"ok": False, "message": "Order scope mismatch"}), 409
        if order.get("type") != "stop" or order.get("status") != "active":
            return jsonify({"ok": False, "message": "Order is not an active stop"}), 409

        requested_qty = float(data.get("qty", order.get("qty", 0)) or 0)
        if requested_qty <= 0:
            return jsonify({"ok": False, "message": "qty_must_be_positive"}), 400

        previous_stop_price = order.get("stop_price")
        previous_qty = order.get("qty")
        order["stop_price"] = float(stop_price)
        order["qty"] = requested_qty
        order["tag"] = data.get("tag") or order.get("tag") or "modified_stop"
        if data.get("oco_group") is not None:
            order["oco_group"] = data.get("oco_group")
        if data.get("oco_role") is not None:
            order["oco_role"] = data.get("oco_role")
        order["modified_at"] = datetime.now().isoformat()
        order.setdefault("modify_history", []).append({
            "modified_at": order["modified_at"],
            "previous_stop_price": previous_stop_price,
            "previous_qty": previous_qty,
            "new_stop_price": order["stop_price"],
            "new_qty": order["qty"],
            "tag": order.get("tag"),
        })

        log(
            f"STOP MODIFIED [{trade_id}] {symbol} order_id={broker_order_id} "
            f"stop={order['stop_price']} qty={order['qty']}"
        )

        stop_fills = []
        if symbol in LAST_PRICES:
            stop_fills = evaluate_stop_fills_for_symbol(symbol, LAST_PRICES[symbol])
            if stop_fills:
                log(f"MODIFIED STOP FILLED IMMEDIATELY [{trade_id}] fills={stop_fills}")

        save_executor_state()

        return jsonify({
            "ok": True,
            "message": "Stop modified",
            "broker_order_id": broker_order_id,
            "order": order,
            "stop_fills": stop_fills,
        })

    # =========================
    # CANCEL SINGLE ORDER
    # =========================
    if action == "cancel_order":
        broker_order_id = data.get("broker_order_id")

        if not broker_order_id:
            return jsonify({"ok": False, "message": "Missing broker_order_id"}), 400

        order = ORDERS.get(broker_order_id)
        if not order:
            return jsonify({"ok": False, "message": "Order not found"}), 404

        order["status"] = "cancelled"
        order["cancelled_at"] = datetime.now().isoformat()

        log(f"🚫 ORDER CANCELLED {broker_order_id}")

        save_executor_state()

        return jsonify({
            "ok": True,
            "message": "Order cancelled",
            "broker_order_id": broker_order_id,
            "order": order
        })

    # =========================
    # FLATTEN BY TRADE
    # =========================
    if action == "flatten_trade":
        if not trade_id:
            return jsonify({"ok": False, "message": "Missing trade_id"}), 400

        affected = []
        timestamp = datetime.now().isoformat()

        for order in active_orders_for_trade(trade_id):
            order["status"] = "closed"
            order["closed_at"] = timestamp
            order["closed_reason"] = "flatten_trade"
            affected.append(order["order_id"])

        log(f"📉 TRADE FLATTENED [{trade_id}] orders={affected}")

        save_executor_state()

        return jsonify({
            "ok": True,
            "message": "Trade flattened",
            "trade_id": trade_id,
            "affected_orders": affected
        })

    # =========================
    # FLATTEN BY SYMBOL
    # =========================
    if action == "flatten_symbol":
        if not symbol:
            return jsonify({"ok": False, "message": "Missing symbol"}), 400

        affected = []
        timestamp = datetime.now().isoformat()

        if trade_id:
            for order in active_orders_for_trade(trade_id):
                if str(order.get("symbol", "")).upper() != symbol:
                    continue
                order["status"] = "closed"
                order["closed_at"] = timestamp
                order["closed_reason"] = "flatten_symbol"
                affected.append(order["order_id"])
            log(f"📉 SYMBOL FLATTENED [{trade_id}] {symbol} orders={affected}")
        else:
            for order in active_orders_for_symbol(symbol):
                order["status"] = "closed"
                order["closed_at"] = timestamp
                order["closed_reason"] = "flatten_symbol"
                affected.append(order["order_id"])
            log(f"📉 SYMBOL FLATTENED [NO TRADE_ID] {symbol} orders={affected}")

        if symbol in POSITIONS:
            POSITIONS[symbol] = {
                "qty": 0.0,
                "avg_entry_price": 0.0,
                "updated_at": datetime.now().isoformat()
            }

        save_executor_state()

        return jsonify({
            "ok": True,
            "message": "Symbol flattened",
            "trade_id": trade_id,
            "symbol": symbol,
            "affected_orders": affected
        })

    # =========================
    # GLOBAL FLATTEN / EMERGENCY HALT
    # =========================
    if action == "flatten_all":
        reason = data.get("reason") or "global_flatten"
        result = flatten_all_positions_and_cancel_working_orders(reason)
        save_executor_state()

        return jsonify({
            "ok": True,
            "message": "Global flatten complete",
            "reason": reason,
            "flattened_symbols": result["flattened_symbols"],
            "cancelled_order_ids": result["cancelled_order_ids"],
            "timestamp": result["timestamp"],
        })

    # =========================
    # MOVE STOP TO BREAKEVEN
    # =========================
    if action == "move_stop_to_be":
        if not trade_id or not symbol:
            return jsonify({"ok": False, "message": "Missing trade_id or symbol"}), 400

        be_price = data.get("be_price")
        if be_price is None:
            return jsonify({"ok": False, "message": "Missing be_price"}), 400

        requested_qty = float(data.get("qty", 0))
        active_stops = active_orders_for_trade(trade_id, "stop")

        if active_stops:
            old_stop = active_stops[0]
            old_stop["status"] = "cancelled"
            old_stop["cancelled_at"] = datetime.now().isoformat()
            qty = float(old_stop.get("qty", 0))
            log(f"🚫 STOP CANCELLED [{trade_id}] {old_stop['order_id']}")
        else:
            qty = requested_qty
            log(f"⚠️ NO ACTIVE STOP FOUND [{trade_id}] rebuilding BE stop from request")

        if qty <= 0:
            return jsonify({
                "ok": False,
                "message": "No active stop found and no qty provided to rebuild stop"
            }), 400

        new_order_id = make_id("STOP")
        ORDERS[new_order_id] = {
            "order_id": new_order_id,
            "trade_id": trade_id,
            "type": "stop",
            "symbol": symbol,
            "stop_price": float(be_price),
            "qty": qty,
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "tag": "breakeven",
            "oco_group": data.get("oco_group") or default_oco_group(trade_id),
            "oco_role": data.get("oco_role") or "protective_stop",
        }

        log(
            f"🟦 STOP MOVED TO BE [{trade_id}] {symbol} "
            f"new={be_price} qty={qty}"
        )

        stop_fills = []
        if symbol in LAST_PRICES:
            stop_fills = evaluate_stop_fills_for_symbol(symbol, LAST_PRICES[symbol])
            if stop_fills:
                log(f"BE STOP FILLED IMMEDIATELY [{trade_id}] fills={stop_fills}")

        save_executor_state()

        return jsonify({
            "ok": True,
            "message": "Stop moved to breakeven",
            "trade_id": trade_id,
            "new_stop_id": new_order_id,
            "be_price": be_price,
            "stop_fills": stop_fills
        })

    # =========================
    # RESET STOP TO ORIGINAL
    # =========================
    if action == "reset_stop_to_original":
        if not trade_id or not symbol:
            return jsonify({"ok": False, "message": "Missing trade_id or symbol"}), 400

        stop_price = data.get("stop_price")
        if stop_price is None:
            return jsonify({"ok": False, "message": "Missing stop_price"}), 400

        requested_qty = float(data.get("qty", 0))
        active_stops = active_orders_for_trade(trade_id, "stop")

        for active_stop in active_stops:
            if active_stop_matches_request(active_stop, trade_id, symbol, requested_qty, stop_price):
                log(
                    "duplicate_stop_idempotent "
                    f"action=reset_stop_to_original trade_id={trade_id} symbol={symbol} "
                    f"stop_price={active_stop.get('stop_price')} qty={active_stop.get('qty')} "
                    f"order_id={active_stop.get('order_id')}"
                )
                return jsonify({
                    "ok": True,
                    "message": "duplicate_stop_idempotent",
                    "trade_id": trade_id,
                    "new_stop_id": active_stop["order_id"],
                    "broker_order_id": active_stop["order_id"],
                    "order": active_stop,
                    "idempotent": True,
                    "stop_fills": []
                })

        if active_stops:
            old_stop = active_stops[0]
            old_stop["status"] = "cancelled"
            old_stop["cancelled_at"] = datetime.now().isoformat()
            qty = requested_qty if requested_qty > 0 else float(old_stop.get("qty", 0))
            log(f"🚫 STOP CANCELLED [{trade_id}] {old_stop['order_id']}")
        else:
            qty = requested_qty
            log(f"⚠️ NO ACTIVE STOP FOUND [{trade_id}] rebuilding original stop from request")

        if qty <= 0:
            return jsonify({
                "ok": False,
                "message": "No active stop found and no qty provided to rebuild stop"
            }), 400

        new_order_id = make_id("STOP")

        ORDERS[new_order_id] = {
            "order_id": new_order_id,
            "trade_id": trade_id,
            "type": "stop",
            "symbol": symbol,
            "stop_price": float(stop_price),
            "qty": qty,
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "tag": "runner_reset",
            "oco_group": data.get("oco_group"),
            "oco_parent_group": data.get("oco_parent_group"),
            "oco_role": "runner_stop",
        }

        log(f"🟧 STOP RESET [{trade_id}] {symbol} → {stop_price} qty={qty}")

        stop_fills = []
        if symbol in LAST_PRICES:
            stop_fills = evaluate_stop_fills_for_symbol(symbol, LAST_PRICES[symbol])
            if stop_fills:
                log(f"RESET STOP FILLED IMMEDIATELY [{trade_id}] fills={stop_fills}")

        save_executor_state()

        return jsonify({
            "ok": True,
            "message": "Stop reset to original",
            "trade_id": trade_id,
            "new_stop_id": new_order_id,
            "stop_fills": stop_fills
        })

    return jsonify({"ok": False, "message": f"Unknown action: {action}"}), 400


@app.route("/price", methods=["POST"])
def receive_price():
    data = request.get_json(force=True)
    received_at = utc_now_naive()
    raw_symbol = data.get("symbol") if isinstance(data, dict) else None
    raw_price = data.get("price") if isinstance(data, dict) else None
    raw_tick_timestamp = data.get("tick_timestamp_utc") if isinstance(data, dict) else None
    raw_listener_tick_id = data.get("listener_tick_id") if isinstance(data, dict) else None
    raw_listener_sequence = data.get("listener_sequence") if isinstance(data, dict) else None
    log_price_pipeline(
        "executor_receive_price",
        symbol=raw_symbol,
        price=raw_price,
        tick_timestamp=raw_tick_timestamp,
        received_at=received_at,
        target_url=request.path,
        listener_tick_id=raw_listener_tick_id,
        listener_sequence=raw_listener_sequence,
    )
    if not isinstance(data, dict):
        append_executor_reject(raw_symbol, "invalid_price_payload", raw_price, raw_tick_timestamp, raw_listener_tick_id, raw_listener_sequence)
        log_price_pipeline("executor_reject_price", symbol=raw_symbol, price=raw_price, tick_timestamp=raw_tick_timestamp, received_at=received_at, http_status=409, reject_reason="invalid_price_payload", target_url=request.path)
        return reject_price_tick(None, "invalid_price_payload")

    symbol = str(data.get("symbol") or "").strip().upper()
    if not symbol:
        append_executor_reject(symbol, "missing_symbol", raw_price, raw_tick_timestamp, raw_listener_tick_id, raw_listener_sequence)
        log_price_pipeline("executor_reject_price", symbol=symbol, price=raw_price, tick_timestamp=raw_tick_timestamp, received_at=received_at, http_status=409, reject_reason="missing_symbol", target_url=request.path)
        return reject_price_tick(symbol, "missing_symbol")

    raw_feed_status = data.get("feed_status")
    if raw_feed_status is None:
        append_executor_reject(symbol, "missing_feed_status", raw_price, raw_tick_timestamp, raw_listener_tick_id, raw_listener_sequence)
        log_price_pipeline("executor_reject_price", symbol=symbol, price=raw_price, tick_timestamp=raw_tick_timestamp, received_at=received_at, http_status=409, reject_reason="missing_feed_status", target_url=request.path)
        return reject_price_tick(symbol, "missing_feed_status")

    if raw_feed_status != "LIVE":
        append_executor_reject(symbol, "feed_status_not_live", raw_price, raw_tick_timestamp, raw_listener_tick_id, raw_listener_sequence)
        log_price_pipeline("executor_reject_price", symbol=symbol, price=raw_price, tick_timestamp=raw_tick_timestamp, received_at=received_at, http_status=409, reject_reason="feed_status_not_live", target_url=request.path)
        log(f"PRICE UPDATE REJECTED {symbol} feed_status={raw_feed_status}")
        return reject_price_tick(symbol, "feed_status_not_live", feed_status=raw_feed_status)

    tick_timestamp_utc = data.get("tick_timestamp_utc")
    if not tick_timestamp_utc:
        append_executor_reject(symbol, "missing_tick_timestamp_utc", raw_price, tick_timestamp_utc, raw_listener_tick_id, raw_listener_sequence)
        log_price_pipeline("executor_reject_price", symbol=symbol, price=raw_price, tick_timestamp=tick_timestamp_utc, received_at=received_at, http_status=409, reject_reason="missing_tick_timestamp_utc", target_url=request.path)
        return reject_price_tick(symbol, "missing_tick_timestamp_utc")

    tick_timestamp = parse_listener_tick_timestamp(tick_timestamp_utc)
    if tick_timestamp is None:
        append_executor_reject(symbol, "invalid_tick_timestamp_utc", raw_price, tick_timestamp_utc, raw_listener_tick_id, raw_listener_sequence)
        log_price_pipeline("executor_reject_price", symbol=symbol, price=raw_price, tick_timestamp=tick_timestamp_utc, received_at=received_at, http_status=409, reject_reason="invalid_tick_timestamp_utc", target_url=request.path)
        return reject_price_tick(symbol, "invalid_tick_timestamp_utc")

    tick_age = (received_at - tick_timestamp).total_seconds()
    if tick_age > LISTENER_LAST_TICK_MAX_AGE_SECONDS:
        append_executor_reject(symbol, "stale_tick_timestamp_utc", raw_price, tick_timestamp_utc, raw_listener_tick_id, raw_listener_sequence)
        log_price_pipeline("executor_reject_price", symbol=symbol, price=raw_price, tick_timestamp=tick_timestamp_utc, received_at=received_at, http_status=409, reject_reason="stale_tick_timestamp_utc", target_url=request.path)
        log(
            f"PRICE UPDATE REJECTED {symbol} stale_tick_age={tick_age} "
            f"max_age={LISTENER_LAST_TICK_MAX_AGE_SECONDS}"
        )
        return reject_price_tick(
            symbol,
            "stale_tick_timestamp_utc",
            last_tick_age_seconds=tick_age,
            listener_last_tick_max_age_seconds=LISTENER_LAST_TICK_MAX_AGE_SECONDS,
        )
    if tick_age < -LISTENER_TICK_FUTURE_TOLERANCE_SECONDS:
        append_executor_reject(symbol, "future_tick_timestamp_utc", raw_price, tick_timestamp_utc, raw_listener_tick_id, raw_listener_sequence)
        log_price_pipeline("executor_reject_price", symbol=symbol, price=raw_price, tick_timestamp=tick_timestamp_utc, received_at=received_at, http_status=409, reject_reason="future_tick_timestamp_utc", target_url=request.path)
        log(
            f"PRICE UPDATE REJECTED {symbol} future_tick_age={tick_age} "
            f"tolerance={LISTENER_TICK_FUTURE_TOLERANCE_SECONDS}"
        )
        return reject_price_tick(
            symbol,
            "future_tick_timestamp_utc",
            last_tick_age_seconds=tick_age,
            listener_tick_future_tolerance_seconds=LISTENER_TICK_FUTURE_TOLERANCE_SECONDS,
        )

    try:
        price = float(data.get("price"))
    except (TypeError, ValueError):
        append_executor_reject(symbol, "invalid_price", raw_price, tick_timestamp_utc, raw_listener_tick_id, raw_listener_sequence)
        log_price_pipeline("executor_reject_price", symbol=symbol, price=raw_price, tick_timestamp=tick_timestamp_utc, received_at=received_at, http_status=409, reject_reason="invalid_price", target_url=request.path)
        return reject_price_tick(symbol, "invalid_price")

    if not math.isfinite(price) or price <= 0:
        append_executor_reject(symbol, "invalid_price", raw_price, tick_timestamp_utc, raw_listener_tick_id, raw_listener_sequence)
        log_price_pipeline("executor_reject_price", symbol=symbol, price=raw_price, tick_timestamp=tick_timestamp_utc, received_at=received_at, http_status=409, reject_reason="invalid_price", target_url=request.path)
        return reject_price_tick(symbol, "invalid_price")

    normalized_alias = executor_alias_key(symbol)
    EXECUTOR_PRICE_SEQUENCE_BY_ALIAS[normalized_alias] += 1
    executor_sequence = EXECUTOR_PRICE_SEQUENCE_BY_ALIAS[normalized_alias]
    log_price_pipeline("executor_accept_price", symbol=symbol, price=raw_price, tick_timestamp=tick_timestamp_utc, received_at=received_at, http_status=200, target_url=request.path, listener_tick_id=raw_listener_tick_id, executor_tick_id=raw_listener_tick_id, listener_sequence=raw_listener_sequence, executor_sequence=executor_sequence)
    record_valid_watchdog_tick(symbol, tick_timestamp_utc)
    LAST_PRICES[symbol] = price
    LAST_PRICE_TIMESTAMPS[symbol] = tick_timestamp_utc
    LAST_PRICE_LISTENER_TICK_IDS[symbol] = raw_listener_tick_id
    LAST_PRICE_LISTENER_SEQUENCES[symbol] = raw_listener_sequence
    LAST_PRICE_EXECUTOR_SEQUENCES[symbol] = executor_sequence
    append_executor_accept(symbol, price, tick_timestamp_utc, raw_listener_tick_id, raw_listener_sequence, executor_sequence)
    log_price_pipeline("executor_update_last_prices", symbol=symbol, price=price, tick_timestamp=tick_timestamp_utc, received_at=received_at, http_status=200, listener_tick_id=raw_listener_tick_id, executor_tick_id=raw_listener_tick_id, listener_sequence=raw_listener_sequence, executor_sequence=executor_sequence)
    update_1m_bar(symbol, price, tick_timestamp)
    current_1m_bar = serialize_bar(CURRENT_1M_BARS[symbol]) if symbol in CURRENT_1M_BARS else None

    log(f"📊 PRICE UPDATE {symbol} @ {price}")

    limit_fills = evaluate_limit_fills_for_symbol(symbol, price)
    if limit_fills:
        log(f"LIMIT FILLED ON PRICE [{symbol}] fills={limit_fills}")

    stop_fills = evaluate_stop_fills_for_symbol(symbol, price)
    if stop_fills:
        log(f"STOP FILLED ON PRICE [{symbol}] fills={stop_fills}")

    if limit_fills or stop_fills:
        save_executor_state()

    # Forward to Trade Manager
    try:
        kwargs = {
            "json": {
                "symbol": symbol,
                "price": price,
                "tick_timestamp_utc": tick_timestamp_utc,
                "feed_status": raw_feed_status,
                "listener_tick_id": raw_listener_tick_id,
                "executor_tick_id": raw_listener_tick_id,
                "listener_sequence": raw_listener_sequence,
                "executor_sequence": executor_sequence,
                "current_1m_bar": current_1m_bar,
            },
            "timeout": 0.2
        }
        headers = internal_auth_headers()
        if headers:
            kwargs["headers"] = headers
        log_price_pipeline(
            "executor_post_tm_begin",
            symbol=symbol,
            price=price,
            tick_timestamp=tick_timestamp_utc,
            received_at=utc_now_naive(),
            target_url=TRADE_MANAGER_PRICE_URL,
            listener_tick_id=raw_listener_tick_id,
            executor_tick_id=raw_listener_tick_id,
            listener_sequence=raw_listener_sequence,
            executor_sequence=executor_sequence,
        )
        response = requests.post(TRADE_MANAGER_PRICE_URL, **kwargs)
        reject_reason = response.text[:300] if response.status_code >= 400 else None
        log_price_pipeline(
            "executor_post_tm_result",
            symbol=symbol,
            price=price,
            tick_timestamp=tick_timestamp_utc,
            received_at=utc_now_naive(),
            http_status=response.status_code,
            reject_reason=reject_reason,
            target_url=TRADE_MANAGER_PRICE_URL,
            listener_tick_id=raw_listener_tick_id,
            executor_tick_id=raw_listener_tick_id,
            listener_sequence=raw_listener_sequence,
            executor_sequence=executor_sequence,
        )
    except Exception as e:
        log_price_pipeline(
            "executor_post_tm_result",
            symbol=symbol,
            price=price,
            tick_timestamp=tick_timestamp_utc,
            received_at=utc_now_naive(),
            reject_reason=str(e),
            target_url=TRADE_MANAGER_PRICE_URL,
            listener_tick_id=raw_listener_tick_id,
            executor_tick_id=raw_listener_tick_id,
            listener_sequence=raw_listener_sequence,
            executor_sequence=executor_sequence,
        )
        log(f"⚠️ FORWARD TO TRADE MANAGER FAILED: {e}")

    return jsonify({
        "ok": True,
        "limit_fills": limit_fills,
        "stop_fills": stop_fills
    })


if __name__ == "__main__":
    load_executor_state()
    log("🚀 Executor running on http://127.0.0.1:6001")
    app.run(host="0.0.0.0", port=6001, debug=True, use_reloader=False)
