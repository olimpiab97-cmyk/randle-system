import uuid
from datetime import datetime, timezone
import math
import requests
import os
import json
import sys
import shutil
import re
import threading
import tempfile
from zoneinfo import ZoneInfo
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
SUBMIT_TRADE_LOCK = threading.Lock()
PERSISTENCE_LOCK = threading.RLock()
TRADE_MANAGER_PROCESS_STARTED_AT = datetime.now(timezone.utc).isoformat()
RUNNER_ENTRY_PROTECTION_PATCH_MARKER = "runner_original_after_tp1_2026_05_12_v3"

# =========================
# PATH CONFIG
# =========================

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from symbol_resolution import (
    build_symbol_candidates,
    canonicalize_symbol_input,
    get_default_listener_subscriptions,
    get_instrument_spec,
    get_point_value,
    get_tick_size,
    get_ui_roots,
    normalize_symbol_root,
    resolve_execution_symbol,
)

PERSISTENCE_FILE = os.path.join(BASE_DIR, "Data", "persistence_state.json")
EXECUTOR_STATE_FILE = os.path.join(BASE_DIR, "Data", "executor_state.json")
TRADE_MANAGEMENT_RESEARCH_FILE = os.path.join(BASE_DIR, "Data", "trade_management_research.jsonl")
TRADE_SCREENSHOT_DIR = os.path.join(BASE_DIR, "Data", "trade_screenshots")
RITHMIC_ATR_SNAPSHOT_FILE = os.path.join(BASE_DIR, "Data", "rithmic_atr_snapshot.json")
RITHMIC_RECENT_BARS_FILE = os.path.join(BASE_DIR, "Data", "rithmic_recent_bars.json")
RITHMIC_ATR_SHADOW_COMPARISON_FILE = os.path.join(BASE_DIR, "Data", "rithmic_atr_shadow_comparison.json")
ENTRY_AGENT_TV_CONTEXT_URL = os.getenv(
    "ENTRY_AGENT_TV_CONTEXT_URL",
    "http://127.0.0.1:7002/webhook/tv-context",
).strip() or "http://127.0.0.1:7002/webhook/tv-context"
RITHMIC_ATR_SNAPSHOT_MAX_AGE_SECONDS = 180
TRADINGVIEW_ATR_MAX_AGE_SECONDS = 180
ATR_PERIOD = 14
ATR_MAX_SANITY_VALUE = 100.0
TRADE_MANAGER_CONFIG_FILE = os.path.join(BASE_DIR, "Data", "trade_manager_config.json")
OPERATING_MODE_ENV_VAR = "RANDLE_TRADE_MANAGER_MODE"
OPERATING_MODE_PRODUCTION = "production"
OPERATING_MODE_QA_STABILITY = "qa_stability"
VALID_OPERATING_MODES = {
    OPERATING_MODE_PRODUCTION,
    OPERATING_MODE_QA_STABILITY,
}
ENABLE_NOON_RUNNER_FLATTEN = False
NOON_RUNNER_FLATTEN_TIMEZONE = "America/Los_Angeles"
NOON_RUNNER_FLATTEN_HOUR = 12
NOON_RUNNER_FLATTEN_ZONE = ZoneInfo(NOON_RUNNER_FLATTEN_TIMEZONE)
RUNTIME_PAPER_RESET_AT = None
TV_CONTEXT_PROXY_STATE = {
    "last_forwarded_at": None,
    "last_status_code": None,
    "last_ok": None,
    "last_error": None,
    "last_symbol": None,
    "target_url": ENTRY_AGENT_TV_CONTEXT_URL,
}


def load_trade_manager_config():
    if not os.path.exists(TRADE_MANAGER_CONFIG_FILE):
        return {}

    try:
        with open(TRADE_MANAGER_CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as exc:
        print(f"CONFIG WARNING trade_manager_config_load_failed path={TRADE_MANAGER_CONFIG_FILE} error={exc}")
        return {}

    if not isinstance(config, dict):
        print(f"CONFIG WARNING trade_manager_config_ignored path={TRADE_MANAGER_CONFIG_FILE} reason=not_json_object")
        return {}

    return config


def resolve_operating_mode():
    config = load_trade_manager_config()
    raw_mode = os.environ.get(OPERATING_MODE_ENV_VAR) or config.get("operating_mode")
    mode = str(raw_mode or OPERATING_MODE_PRODUCTION).strip().lower()

    if mode not in VALID_OPERATING_MODES:
        print(
            "CONFIG WARNING invalid_operating_mode "
            f"value={mode} fallback={OPERATING_MODE_PRODUCTION}"
        )
        return OPERATING_MODE_PRODUCTION

    return mode


OPERATING_MODE = resolve_operating_mode()


def is_qa_stability_mode():
    return OPERATING_MODE == OPERATING_MODE_QA_STABILITY


def parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def is_noon_runner_flatten_enabled():
    config = load_trade_manager_config()
    return parse_bool(
        config.get("ENABLE_NOON_RUNNER_FLATTEN"),
        default=ENABLE_NOON_RUNNER_FLATTEN,
    )

# =========================
# BROKER ADAPTER CONFIG
# =========================

BROKER_NAME = "local_executor"
EXECUTOR_URL = "http://127.0.0.1:6001/execute"
EXECUTOR_ORDERS_URL = "http://127.0.0.1:6001/orders"
EXECUTOR_SNAPSHOT_URL = "http://127.0.0.1:6001/sync_snapshot"

# =========================
# PHASE 7 CONNECTION PREP
# =========================

SYSTEM_CONNECTION = {
    "connected": False,
    "broker": BROKER_NAME,
    "session_token": None,
    "last_heartbeat": None,
    "auth_status": "disconnected"
}


def authenticate():
    SYSTEM_CONNECTION["session_token"] = "mock_token"
    SYSTEM_CONNECTION["connected"] = True
    SYSTEM_CONNECTION["auth_status"] = "authenticated"
    SYSTEM_CONNECTION["last_heartbeat"] = datetime.now().isoformat()
    print(f"AUTH: connected to {BROKER_NAME}")
    return SYSTEM_CONNECTION.copy()


def disconnect():
    SYSTEM_CONNECTION["connected"] = False
    SYSTEM_CONNECTION["session_token"] = None
    SYSTEM_CONNECTION["auth_status"] = "disconnected"
    print(f"AUTH: disconnected from {BROKER_NAME}")
    return SYSTEM_CONNECTION.copy()


def heartbeat():
    if not SYSTEM_CONNECTION["connected"]:
        print("HEARTBEAT FAILED: not connected")
        return False

    SYSTEM_CONNECTION["last_heartbeat"] = datetime.now().isoformat()
    print(f"HEARTBEAT OK: {SYSTEM_CONNECTION['last_heartbeat']}")
    return True


def ensure_connection():
    if not SYSTEM_CONNECTION["connected"]:
        authenticate()
    return heartbeat()


# =========================
# PERSISTENCE FUNCTIONS
# =========================


def build_default_state():
    return {
        "system": {
            "version": "v1",
            "engine_status": "running",
            "last_update_at": None,
            "last_noon_runner_flatten_date": None,
            "last_noon_runner_flatten_at": None,
        },
        "trades": {},
        "orders": {},
        "tradingview_atr": {},
        "risk_state": {
            "kill_switch_active": False,
            "kill_switch_reason": None,
            "daily_trade_count": 0,
            "daily_loss_count": 0,
            "max_daily_trades": 2,
            "max_daily_losses": 1,
            "kill_switch_drawdown_pct": 11.0,
            "current_drawdown_pct": 0.0,
            "trading_halted": False,
            "last_reset_date": datetime.now().date().isoformat(),
        },
        "event_log": [],
        "failure_state": {
            "execution_failure_count": 0,
            "qa_critical_count": 0,
            "max_execution_failures": 3,
            "max_qa_critical": 3,
            "last_failure_at": None,
            "halt_reason": None,
        },
    }


def backup_bad_persistence_file(reason):
    if not os.path.exists(PERSISTENCE_FILE):
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{PERSISTENCE_FILE}.{reason}.{timestamp}.bak"
    try:
        shutil.copy2(PERSISTENCE_FILE, backup_path)
        print(f"PERSISTENCE WARNING backup_created={backup_path}")
        return backup_path
    except Exception as exc:
        print(f"PERSISTENCE WARNING backup_failed path={backup_path} error={exc}")
        return None


def active_trade_count(state):
    return sum(
        1
        for trade in (state.get("trades") or {}).values()
        if trade.get("status") == "active"
    )


def managed_open_trade_count(state):
    return sum(
        1
        for trade in (state.get("trades") or {}).values()
        if trade.get("status") not in ("closed", "error")
    )


def summarize_open_trades(state):
    return [
        {
            "trade_id": trade_id,
            "status": trade.get("status"),
            "symbol": trade.get("symbol"),
            "remaining_size": trade.get("remaining_size"),
        }
        for trade_id, trade in (state.get("trades") or {}).items()
        if trade.get("status") not in ("closed", "error")
    ]


def audit_active_trade_count_drop(previous_state, next_state, reason):
    previous_active = {
        trade_id: trade
        for trade_id, trade in (previous_state.get("trades") or {}).items()
        if trade.get("status") == "active"
    }
    next_trades = next_state.get("trades") or {}
    unexpected = []
    for trade_id, trade in previous_active.items():
        next_trade = next_trades.get(trade_id)
        if not next_trade:
            unexpected.append({
                "trade_id": trade_id,
                "previous_status": "active",
                "next_status": "missing",
                "symbol": trade.get("symbol"),
            })
            continue
        next_status = next_trade.get("status")
        if next_status not in ("active", "closed", "error"):
            unexpected.append({
                "trade_id": trade_id,
                "previous_status": "active",
                "next_status": next_status,
                "symbol": trade.get("symbol"),
            })

    if not unexpected:
        return False

    append_event(
        next_state,
        "SYSTEM",
        "active_trade_count_decreased",
        "Active Trade Manager count decreased during persistence write",
        details={
            "reason": reason,
            "previous_active_count": active_trade_count(previous_state),
            "next_active_count": active_trade_count(next_state),
            "unexpected_changes": unexpected,
            "previous_open_trades": summarize_open_trades(previous_state),
            "next_open_trades": summarize_open_trades(next_state),
        },
    )
    print(
        "PERSISTENCE AUDIT active_trade_count_decreased "
        f"reason={reason} previous={active_trade_count(previous_state)} "
        f"next={active_trade_count(next_state)} unexpected={unexpected}"
    )
    return True


def merge_trade_state_for_persistence(previous_state, next_state, reason):
    previous_trades = previous_state.get("trades") or {}
    next_trades = next_state.setdefault("trades", {})
    changed = False
    protected_level_fields = (
        "entry_price",
        "tp1_price",
        "be_trigger",
        "current_stop",
        "original_stop",
        "direction",
    )

    for trade_id, previous_trade in previous_trades.items():
        previous_status = previous_trade.get("status")
        if previous_status in ("closed", "error"):
            continue

        next_trade = next_trades.get(trade_id)
        if not next_trade:
            next_trades[trade_id] = previous_trade
            append_event(
                next_state,
                "SYSTEM",
                "prevented_open_trade_persistence_loss",
                "Prevented stale persistence write from removing open manager trade",
                details={
                    "reason": reason,
                    "trade_id": trade_id,
                    "previous_status": previous_status,
                },
            )
            changed = True
            continue

        next_status = next_trade.get("status")
        if previous_status == "active" and next_status not in ("active", "closed", "error"):
            next_trades[trade_id] = previous_trade
            append_event(
                next_state,
                "SYSTEM",
                "prevented_active_trade_downgrade",
                "Prevented stale persistence write from downgrading active manager trade",
                details={
                    "reason": reason,
                    "trade_id": trade_id,
                    "previous_status": previous_status,
                    "next_status": next_status,
                },
            )
            changed = True
            continue

        previous_has_execution = previous_trade.get("entry_price") is not None or previous_trade.get("stop_order_id")
        next_missing_execution = next_trade.get("entry_price") is None and not next_trade.get("stop_order_id")
        if previous_has_execution and next_missing_execution and next_status not in ("closed", "error"):
            next_trades[trade_id] = previous_trade
            append_event(
                next_state,
                "SYSTEM",
                "prevented_trade_execution_evidence_loss",
                "Prevented stale persistence write from dropping manager trade execution fields",
                details={
                    "reason": reason,
                    "trade_id": trade_id,
                    "previous_status": previous_status,
                    "next_status": next_status,
                },
            )
            changed = True

        if next_status not in ("closed", "error"):
            restored_fields = []
            for field in protected_level_fields:
                previous_value = previous_trade.get(field)
                next_value = next_trade.get(field)
                if previous_value is not None and next_value in (None, ""):
                    next_trade[field] = previous_value
                    restored_fields.append(field)
            if restored_fields:
                append_event(
                    next_state,
                    "SYSTEM",
                    "prevented_trade_level_field_loss",
                    "Prevented stale persistence write from dropping active trade level fields",
                    details={
                        "reason": reason,
                        "trade_id": trade_id,
                        "restored_fields": restored_fields,
                    },
                )
                changed = True

    return changed


def normalize_loaded_state(state):
    default_state = build_default_state()
    normalized_state = default_state.copy()
    normalized_state["system"] = dict(default_state["system"])
    normalized_state["trades"] = {}
    normalized_state["orders"] = {}
    normalized_state["tradingview_atr"] = {}
    normalized_state["event_log"] = []
    normalized_state["risk_state"] = dict(default_state["risk_state"])
    normalized_state["failure_state"] = dict(default_state["failure_state"])

    if isinstance(state, dict):
        if isinstance(state.get("system"), dict):
            normalized_state["system"].update(state["system"])
        if isinstance(state.get("trades"), dict):
            normalized_state["trades"] = state["trades"]
        if isinstance(state.get("orders"), dict):
            normalized_state["orders"] = state["orders"]
        if isinstance(state.get("tradingview_atr"), dict):
            normalized_state["tradingview_atr"] = state["tradingview_atr"]
        if isinstance(state.get("event_log"), list):
            normalized_state["event_log"] = state["event_log"]
        if isinstance(state.get("risk_state"), dict):
            normalized_state["risk_state"].update(state["risk_state"])
        if isinstance(state.get("failure_state"), dict):
            normalized_state["failure_state"].update(state["failure_state"])

    return normalized_state


def get_paper_reset_at(state):
    system_state = state.get("system") if isinstance(state, dict) else {}
    value = system_state.get("paper_reset_at") if isinstance(system_state, dict) else None
    return str(value).strip() if value else None


def is_trade_older_than_reset(trade, paper_reset_at):
    if not paper_reset_at or not isinstance(trade, dict):
        return False

    created_at = trade.get("created_at") or trade.get("last_price_at")
    if not created_at:
        return False

    try:
        return coerce_datetime(created_at) < coerce_datetime(paper_reset_at)
    except Exception:
        return False


def apply_external_paper_reset_if_needed(previous_state, normalized_state):
    global RUNTIME_PAPER_RESET_AT

    paper_reset_at = get_paper_reset_at(previous_state)
    if not paper_reset_at:
        return

    normalized_state.setdefault("system", {})["paper_reset_at"] = paper_reset_at
    existing_trade_ids = set((previous_state.get("trades") or {}).keys())
    stale_trade_ids = [
        trade_id
        for trade_id, trade in (normalized_state.get("trades") or {}).items()
        if trade_id not in existing_trade_ids and is_trade_older_than_reset(trade, paper_reset_at)
    ]
    for trade_id in stale_trade_ids:
        normalized_state["trades"].pop(trade_id, None)

    if stale_trade_ids:
        print(
            "PERSISTENCE RESET GUARD dropped_stale_trades "
            f"paper_reset_at={paper_reset_at} trade_ids={stale_trade_ids}"
        )

    if paper_reset_at == RUNTIME_PAPER_RESET_AT:
        return

    persisted_risk = previous_state.get("risk_state") or {}
    persisted_failure = previous_state.get("failure_state") or {}

    if "RISK_STATE" in globals():
        for key in RISK_STATE.keys():
            if key in persisted_risk:
                RISK_STATE[key] = persisted_risk[key]
    if "FAILURE_STATE" in globals():
        for key in FAILURE_STATE.keys():
            if key in persisted_failure:
                FAILURE_STATE[key] = persisted_failure[key]

    RUNTIME_PAPER_RESET_AT = paper_reset_at


def load_state():
    with PERSISTENCE_LOCK:
        if not os.path.exists(PERSISTENCE_FILE):
            print(f"PERSISTENCE WARNING persistence_state_missing path={PERSISTENCE_FILE}")
            print("PERSISTENCE WARNING persistence_state_defaulted reason=missing")
            return build_default_state()

        last_error = None
        for attempt in range(3):
            try:
                with open(PERSISTENCE_FILE, "r", encoding="utf-8") as f:
                    raw_contents = f.read()
            except Exception as exc:
                last_error = exc
                print(f"PERSISTENCE WARNING persistence_state_read_failed path={PERSISTENCE_FILE} error={exc}")
                continue

            if not raw_contents.strip():
                last_error = "empty"
                print(f"PERSISTENCE WARNING persistence_state_empty path={PERSISTENCE_FILE} attempt={attempt + 1}")
                continue

            try:
                loaded_state = json.loads(raw_contents)
            except json.JSONDecodeError as exc:
                last_error = exc
                print(
                    f"PERSISTENCE WARNING persistence_state_invalid_json "
                    f"path={PERSISTENCE_FILE} attempt={attempt + 1} error={exc}"
                )
                continue

            normalized_state = normalize_loaded_state(loaded_state)
            if normalized_state != loaded_state:
                print("PERSISTENCE WARNING persistence_state_defaulted reason=schema_normalized")
            return normalized_state

        backup_bad_persistence_file("unreadable")
        print(f"PERSISTENCE WARNING persistence_state_defaulted reason=unreadable error={last_error}")
        return build_default_state()


def save_state(state, reason="unspecified"):
    with PERSISTENCE_LOCK:
        previous_state = load_state() if os.path.exists(PERSISTENCE_FILE) else build_default_state()
        normalized_state = normalize_loaded_state(state)
        apply_external_paper_reset_if_needed(previous_state, normalized_state)
        if "RISK_STATE" in globals():
            normalized_state["risk_state"] = serialize_trade(RISK_STATE)
        if "FAILURE_STATE" in globals():
            normalized_state["failure_state"] = serialize_trade(FAILURE_STATE)
        merge_trade_state_for_persistence(previous_state, normalized_state, reason)
        audit_active_trade_count_drop(previous_state, normalized_state, reason)
        normalized_state["system"]["last_update_at"] = datetime.now().isoformat()

        target_dir = os.path.dirname(PERSISTENCE_FILE)
        os.makedirs(target_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target_dir,
            delete=False,
        ) as tmp_file:
            json.dump(normalized_state, tmp_file, indent=2)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
            temp_path = tmp_file.name

        os.replace(temp_path, PERSISTENCE_FILE)


def serialize_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def serialize_trade(trade):
    return {k: serialize_value(v) for k, v in trade.items()}


def normalize_timestamp(timestamp):
    if isinstance(timestamp, datetime):
        return timestamp.isoformat()
    return timestamp


def coerce_datetime(value):
    if isinstance(value, datetime):
        return value
    if value is None:
        return datetime.now(NOON_RUNNER_FLATTEN_ZONE)

    raw_value = str(value).strip()
    if raw_value.endswith("Z"):
        raw_value = raw_value[:-1] + "+00:00"
    return datetime.fromisoformat(raw_value)


def as_los_angeles_time(value=None):
    dt_value = coerce_datetime(value)
    if dt_value.tzinfo is None:
        return dt_value.replace(tzinfo=NOON_RUNNER_FLATTEN_ZONE)
    return dt_value.astimezone(NOON_RUNNER_FLATTEN_ZONE)


def get_contract_spec(symbol):
    return get_instrument_spec(symbol)


TRADE_PUBLIC_FIELDS = [
    "trade_id",
    "status",
    "symbol",
    "created_at",
    "opened_at",
    "entry_time",
    "submitted_at",
    "direction",
    "entry_price",
    "original_stop",
    "current_stop",
    "stop_state",
    "be_trigger",
    "tp1_price",
    "tp1_hit",
    "tp1_hit_at",
    "moved_to_be",
    "be_hit_at",
    "be_state_locked",
    "be_trigger_processed_at",
    "be_duplicate_trigger_suppressed_count",
    "remaining_size",
    "exit_price",
    "exit_reason",
    "closed_at",
    "last_price",
    "last_price_at",
    "realized_pnl",
    "unrealized_pnl",
    "total_pnl",
    "tp1_profit",
    "runner_profit",
    "total_profit",
    "result",
    "r_multiple",
    "screenshot",
    "screenshot_filename",
    "screenshot_path",
    "screenshot_url",
    "screenshot_uploaded_at",
]


def primitive_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): primitive_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [primitive_value(item) for item in value]
    return str(value)


def calculate_realized_pnl(trade):
    entry_price = trade.get("entry_price")
    position_size = trade.get("position_size")

    if entry_price is None or position_size is None:
        return None

    try:
        entry = float(entry_price)
        size = float(position_size)
    except (TypeError, ValueError):
        return None

    direction = str(trade.get("direction")).lower()
    realized = 0.0
    realized_qty = 0.0

    if trade.get("tp1_hit") and trade.get("tp1_filled_qty") is not None and trade.get("tp1_exit_price") is not None:
        try:
            tp1_qty = float(trade["tp1_filled_qty"])
            tp1_exit = float(trade["tp1_exit_price"])
        except (TypeError, ValueError):
            tp1_qty = 0.0
            tp1_exit = entry

        if tp1_qty > 0:
            realized += calculate_trade_leg_profit(trade, tp1_exit, tp1_qty)
            realized_qty += tp1_qty

    if trade.get("exit_price") is not None:
        try:
            exit_ = float(trade["exit_price"])
        except (TypeError, ValueError):
            return round(realized, 2) if realized_qty > 0 else None

        remaining_exit_qty = max(size - realized_qty, 0.0)
        if remaining_exit_qty > 0:
            realized += calculate_trade_leg_profit(trade, exit_, remaining_exit_qty)
            realized_qty += remaining_exit_qty

    if realized_qty <= 0:
        return None

    return round(realized, 2)


def calculate_trade_leg_profit(trade, exit_price, qty):
    try:
        entry = float(trade.get("entry_price"))
        exit_ = float(exit_price)
        size = float(qty)
    except (TypeError, ValueError):
        return 0.0

    direction = str(trade.get("direction")).lower()
    point_value = get_point_value(trade.get("symbol"))
    if direction == "short":
        return round((entry - exit_) * point_value * size, 2)
    return round((exit_ - entry) * point_value * size, 2)


def calculate_unrealized_pnl(trade, current_price=None):
    if trade.get("status") != "active":
        return 0.0

    try:
        remaining_size = float(trade.get("remaining_size") or 0)
    except (TypeError, ValueError):
        return 0.0

    if remaining_size <= 0:
        return 0.0

    price = current_price
    if price is None:
        price = trade.get("last_price")
    if price is None:
        return 0.0

    return calculate_trade_leg_profit(trade, price, remaining_size)


def update_pnl_totals(trade, current_price=None):
    realized = trade.get("realized_pnl")
    if realized is None:
        realized = calculate_realized_pnl(trade)
    if realized is None:
        realized = 0.0

    trade["realized_pnl"] = round(float(realized), 2)
    trade["unrealized_pnl"] = round(calculate_unrealized_pnl(trade, current_price=current_price), 2)
    trade["total_pnl"] = round(trade["realized_pnl"] + trade["unrealized_pnl"], 2)
    return trade


def apply_closed_trade_accounting(trade):
    status = str(trade.get("status") or "").lower()
    if status not in {"closed", "archived"} and trade.get("archived") is not True:
        return trade
    update_profit_breakdown(trade, include_runner=trade.get("exit_price") is not None)
    total = coerce_float(trade.get("total_profit"))
    if total is None:
        total = coerce_float(trade.get("realized_pnl"))
    if total is None:
        total = 0.0
    trade["realized_pnl"] = round(total, 2)
    trade["total_pnl"] = round(total, 2)
    trade["unrealized_pnl"] = 0.0
    if total > 0:
        trade["result"] = "WIN"
    elif total < 0:
        trade["result"] = "LOSS"
    else:
        trade["result"] = "BE"

    risk = first_present_float(
        trade.get("initial_risk_dollars"),
        trade.get("risk_dollars"),
        trade.get("initial_risk"),
        trade.get("risk_amount"),
        trade.get("dollar_risk"),
    )
    if risk is None:
        try:
            entry = float(trade.get("entry_price"))
            stop = float(trade.get("original_stop"))
            size = float(trade.get("position_size"))
            risk = abs(entry - stop) * get_point_value(trade.get("symbol")) * size
        except (TypeError, ValueError):
            risk = None
    if risk is not None and risk != 0:
        trade["r_multiple"] = round(total / risk, 4)
    return trade


def coerce_float(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def first_present_float(*values):
    for value in values:
        result = coerce_float(value)
        if result is not None:
            return result
    return None


def collect_entry_leg_extremes_from_source(source):
    if not isinstance(source, dict):
        return None, None, None

    high = first_present_float(
        source.get("entry_leg_high"),
        source.get("entry_bar_high"),
        source.get("current_1m_bar_high"),
        source.get("bar_high"),
        source.get("high"),
    )
    low = first_present_float(
        source.get("entry_leg_low"),
        source.get("entry_bar_low"),
        source.get("current_1m_bar_low"),
        source.get("bar_low"),
        source.get("low"),
    )
    timestamp = (
        source.get("entry_leg_timestamp")
        or source.get("entry_bar_timestamp")
        or source.get("current_1m_bar_timestamp")
        or source.get("bar_timestamp")
        or source.get("timestamp")
    )
    if high is not None or low is not None:
        return high, low, timestamp

    for key in ("entry_context", "entry_bar", "bar", "order", "fill_context"):
        nested_high, nested_low, nested_timestamp = collect_entry_leg_extremes_from_source(source.get(key))
        if nested_high is not None or nested_low is not None:
            return nested_high, nested_low, nested_timestamp

    bars = source.get("atr_completed_bars")
    if isinstance(bars, list) and bars:
        return collect_entry_leg_extremes_from_source(bars[-1])

    return None, None, None


def capture_entry_leg_extremes(trade, *sources):
    if trade.get("entry_leg_high") is not None and trade.get("entry_leg_low") is not None:
        return trade

    for source in sources:
        high, low, timestamp = collect_entry_leg_extremes_from_source(source)
        if high is None and low is None:
            continue
        if trade.get("entry_leg_high") is None and high is not None:
            trade["entry_leg_high"] = round_price(high)
        if trade.get("entry_leg_low") is None and low is not None:
            trade["entry_leg_low"] = round_price(low)
        if timestamp and not trade.get("entry_leg_timestamp"):
            trade["entry_leg_timestamp"] = normalize_timestamp(timestamp)
        if not trade.get("entry_leg_source"):
            trade["entry_leg_source"] = "entry_context"
        return trade

    return trade


def structural_dynamic_research_levels(trade):
    entry_price = coerce_float(trade.get("entry_price"))
    tick_size = coerce_float(get_tick_size(trade.get("symbol")))
    if entry_price is None or tick_size is None or tick_size <= 0:
        return None, None, None

    if trade.get("direction") == "short":
        entry_leg_high = coerce_float(trade.get("entry_leg_high"))
        if entry_leg_high is None:
            return None, None, None
        stop_price = round_to_nearest_tick(entry_leg_high + tick_size, trade.get("symbol"))
        distance = stop_price - entry_price
        if distance <= 0:
            return None, None, None
        tp1_price = round_to_nearest_tick(entry_price - distance, trade.get("symbol"))
        return stop_price, tp1_price, round(distance, 4)

    if trade.get("direction") == "long":
        entry_leg_low = coerce_float(trade.get("entry_leg_low"))
        if entry_leg_low is None:
            return None, None, None
        stop_price = round_to_nearest_tick(entry_leg_low - tick_size, trade.get("symbol"))
        distance = entry_price - stop_price
        if distance <= 0:
            return None, None, None
        tp1_price = round_to_nearest_tick(entry_price + distance, trade.get("symbol"))
        return stop_price, tp1_price, round(distance, 4)

    return None, None, None


def fixed_research_distance_points(symbol, distance_id):
    symbol_root = normalize_symbol_root(symbol)
    tick_size = coerce_float(get_tick_size(symbol))
    if symbol_root == "NQ" and tick_size and tick_size > 0:
        return float(distance_id) * tick_size
    if symbol_root == "YM":
        return float(distance_id)
    return None


def fixed_research_levels(trade, distance_id):
    entry_price = coerce_float(trade.get("entry_price"))
    distance = fixed_research_distance_points(trade.get("symbol"), distance_id)
    if entry_price is None or distance is None:
        return None, None, None

    if trade.get("direction") == "short":
        return (
            round_to_nearest_tick(entry_price + distance, trade.get("symbol")),
            round_to_nearest_tick(entry_price - distance, trade.get("symbol")),
            round(distance, 4),
        )
    if trade.get("direction") == "long":
        return (
            round_to_nearest_tick(entry_price - distance, trade.get("symbol")),
            round_to_nearest_tick(entry_price + distance, trade.get("symbol")),
            round(distance, 4),
        )
    return None, None, None


def update_research_model_hits(trade, price, timestamp, prefix, stop_price, tp1_price, distance_points):
    if stop_price is None or tp1_price is None:
        return

    trade[f"{prefix}_stop_price"] = stop_price
    trade[f"{prefix}_tp1_price"] = tp1_price
    if distance_points is not None:
        trade[f"{prefix}_stop_distance_points"] = distance_points

    direction = trade.get("direction")
    tp1_hit = False
    stop_hit = False
    if direction == "short":
        tp1_hit = price <= tp1_price
        stop_hit = price >= stop_price
    elif direction == "long":
        tp1_hit = price >= tp1_price
        stop_hit = price <= stop_price

    if tp1_hit and not trade.get(f"{prefix}_tp1_first_hit_at"):
        trade[f"{prefix}_tp1_first_hit_at"] = timestamp
        trade[f"{prefix}_tp1_would_hit"] = True
        if not trade.get(f"{prefix}_model_first_hit"):
            trade[f"{prefix}_model_first_hit"] = "tp1"

    if stop_hit and not trade.get(f"{prefix}_stop_first_hit_at"):
        trade[f"{prefix}_stop_first_hit_at"] = timestamp
        trade[f"{prefix}_stop_would_hit"] = True
        if not trade.get(f"{prefix}_model_first_hit"):
            trade[f"{prefix}_model_first_hit"] = "stop"


def update_research_models(trade, price, timestamp):
    structural_stop, structural_tp1, structural_distance = structural_dynamic_research_levels(trade)
    update_research_model_hits(
        trade,
        price,
        timestamp,
        "structural_dynamic",
        structural_stop,
        structural_tp1,
        structural_distance,
    )

    for distance_id in (8, 12, 16):
        stop_price, tp1_price, distance = fixed_research_levels(trade, distance_id)
        update_research_model_hits(
            trade,
            price,
            timestamp,
            f"fixed_{distance_id}",
            stop_price,
            tp1_price,
            distance,
        )


def update_post_be_analytics(trade, price, timestamp):
    if not trade.get("moved_to_be"):
        return trade

    current_price = coerce_float(price)
    entry_price = coerce_float(trade.get("entry_price"))
    if current_price is None or entry_price is None:
        return trade

    timestamp = normalize_timestamp(timestamp) or datetime.now().isoformat()
    if not trade.get("post_be_first_seen_at"):
        trade["post_be_first_seen_at"] = trade.get("be_hit_at") or timestamp

    previous_best = coerce_float(trade.get("post_be_best_price"))
    previous_worst = coerce_float(trade.get("post_be_worst_price"))
    direction = trade.get("direction")

    if direction == "short":
        best_price = current_price if previous_best is None else min(previous_best, current_price)
        worst_price = current_price if previous_worst is None else max(previous_worst, current_price)
        mfe_points = max(0.0, entry_price - best_price)
        mae_points = max(0.0, worst_price - entry_price)
    elif direction == "long":
        best_price = current_price if previous_best is None else max(previous_best, current_price)
        worst_price = current_price if previous_worst is None else min(previous_worst, current_price)
        mfe_points = max(0.0, best_price - entry_price)
        mae_points = max(0.0, entry_price - worst_price)
    else:
        return trade

    tick_size = coerce_float(get_tick_size(trade.get("symbol")))
    trade["post_be_best_price"] = round_price(best_price)
    trade["post_be_worst_price"] = round_price(worst_price)
    trade["post_be_mfe_points"] = round(mfe_points, 4)
    trade["post_be_mae_points"] = round(mae_points, 4)
    if tick_size and tick_size > 0:
        trade["post_be_mfe_ticks"] = round(mfe_points / tick_size, 4)
        trade["post_be_mae_ticks"] = round(mae_points / tick_size, 4)
    trade["post_be_last_updated_at"] = timestamp
    update_research_models(trade, current_price, timestamp)
    return trade


def actual_trade_result(trade):
    apply_closed_trade_accounting(trade)
    profit = coerce_float(trade.get("total_profit"))
    if profit is None:
        profit = coerce_float(trade.get("total_pnl"))
    if profit is None:
        return None
    if profit > 0:
        return "win"
    if profit < 0:
        return "loss"
    return "flat"


def research_model_result(trade, prefix):
    first_hit = trade.get(f"{prefix}_model_first_hit")
    if first_hit == "tp1":
        return "tp1"
    if first_hit == "stop":
        return "stop"
    if trade.get(f"{prefix}_tp1_would_hit") and trade.get(f"{prefix}_stop_would_hit"):
        return "both_hit_order_unknown"
    if trade.get(f"{prefix}_tp1_would_hit"):
        return "tp1"
    if trade.get(f"{prefix}_stop_would_hit"):
        return "stop"
    return "no_hit"


def fixed_research_row_fields(trade):
    fields = {}
    for distance_id in (8, 12, 16):
        prefix = f"fixed_{distance_id}"
        stop_price, tp1_price, distance = fixed_research_levels(trade, distance_id)
        fields.update({
            f"{prefix}_stop_price": trade.get(f"{prefix}_stop_price") or stop_price,
            f"{prefix}_tp1_price": trade.get(f"{prefix}_tp1_price") or tp1_price,
            f"{prefix}_stop_distance_points": trade.get(f"{prefix}_stop_distance_points") or distance,
            f"{prefix}_tp1_would_hit": bool(trade.get(f"{prefix}_tp1_would_hit")),
            f"{prefix}_stop_would_hit": bool(trade.get(f"{prefix}_stop_would_hit")),
            f"{prefix}_model_result": research_model_result(trade, prefix),
        })
    return fields


def build_trade_management_research_row(trade):
    structural_stop_price, structural_tp1_price, structural_distance = structural_dynamic_research_levels(trade)
    row = {
        "trade_id": trade.get("trade_id"),
        "symbol": trade.get("symbol"),
        "direction": trade.get("direction"),
        "entry_price": trade.get("entry_price"),
        "original_stop": trade.get("original_stop"),
        "original_tp1_price": trade.get("original_tp1_price") or trade.get("tp1_price"),
        "be_trigger": trade.get("be_trigger"),
        "be_hit_at": trade.get("be_hit_at"),
        "closed_at": trade.get("closed_at"),
        "actual_exit_price": trade.get("exit_price"),
        "actual_exit_reason": trade.get("exit_reason"),
        "actual_result": actual_trade_result(trade),
        "post_be_best_price": trade.get("post_be_best_price"),
        "post_be_worst_price": trade.get("post_be_worst_price"),
        "post_be_mfe_points": trade.get("post_be_mfe_points"),
        "post_be_mae_points": trade.get("post_be_mae_points"),
        "post_be_mfe_ticks": trade.get("post_be_mfe_ticks"),
        "post_be_mae_ticks": trade.get("post_be_mae_ticks"),
        "post_be_first_seen_at": trade.get("post_be_first_seen_at"),
        "post_be_last_updated_at": trade.get("post_be_last_updated_at"),
        "entry_leg_high": trade.get("entry_leg_high"),
        "entry_leg_low": trade.get("entry_leg_low"),
        "structural_dynamic_stop_price": trade.get("structural_dynamic_stop_price") or structural_stop_price,
        "structural_dynamic_tp1_price": trade.get("structural_dynamic_tp1_price") or structural_tp1_price,
        "structural_dynamic_stop_distance_points": (
            trade.get("structural_dynamic_stop_distance_points") or structural_distance
        ),
        "structural_dynamic_tp1_would_hit": bool(trade.get("structural_dynamic_tp1_would_hit")),
        "structural_dynamic_stop_would_hit": bool(trade.get("structural_dynamic_stop_would_hit")),
        "structural_dynamic_model_result": research_model_result(trade, "structural_dynamic"),
    }
    row.update(fixed_research_row_fields(trade))
    return row


def append_trade_management_research_row(row):
    target_dir = os.path.dirname(TRADE_MANAGEMENT_RESEARCH_FILE)
    os.makedirs(target_dir, exist_ok=True)
    with open(TRADE_MANAGEMENT_RESEARCH_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def record_trade_management_research_if_closed(trade):
    if trade.get("status") != "closed" or not trade.get("moved_to_be"):
        return False
    if trade.get("post_be_research_logged_at"):
        return False

    try:
        row = build_trade_management_research_row(trade)
        append_trade_management_research_row(row)
        trade["post_be_research_logged_at"] = datetime.now().isoformat()
        return True
    except Exception as exc:
        print(
            "RESEARCH WARNING trade_management_research_write_failed "
            f"trade_id={trade.get('trade_id')} path={TRADE_MANAGEMENT_RESEARCH_FILE} error={exc}"
        )
        return False


def safe_screenshot_filename(trade_id, filename):
    base_name = os.path.basename(str(filename or "screenshot.png"))
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", base_name).strip("._")
    if not safe_name:
        safe_name = "screenshot.png"
    stem, ext = os.path.splitext(safe_name)
    if ext.lower() not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        ext = ".png"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{trade_id}_{timestamp}_{stem[:80]}{ext}"


def trade_screenshot_url(filename):
    if not filename:
        return None
    return f"/trade_screenshots/{filename}"


def repair_missing_be_trigger(trade):
    if trade.get("be_trigger") is not None:
        return False
    if trade.get("entry_price") is None or trade.get("tp1_price") is None:
        return False

    try:
        entry_price = float(trade.get("entry_price"))
        tp1_price = float(trade.get("tp1_price"))
    except (TypeError, ValueError):
        return False

    if not math.isfinite(entry_price) or not math.isfinite(tp1_price):
        return False
    if entry_price == tp1_price:
        return False

    trade["be_trigger"] = round_to_nearest_tick(
        entry_price + ((tp1_price - entry_price) / 2),
        trade.get("symbol"),
    )
    return True


def calculate_tp1_profit(trade):
    if trade.get("tp1_filled_qty") is None or trade.get("tp1_exit_price") is None:
        return None
    return calculate_trade_leg_profit(
        trade,
        trade.get("tp1_exit_price"),
        trade.get("tp1_filled_qty"),
    )


def calculate_runner_profit(trade):
    if trade.get("exit_price") is None:
        return None

    try:
        position_size = float(trade.get("position_size", 0))
        tp1_qty = float(trade.get("tp1_filled_qty") or 0)
    except (TypeError, ValueError):
        return None

    runner_qty = max(position_size - tp1_qty, 0.0)
    if runner_qty <= 0:
        return 0.0

    return calculate_trade_leg_profit(trade, trade.get("exit_price"), runner_qty)


def resolve_runner_flatten_exit_price(trade, evidence_order):
    """Return the price to use for a runner closed by flatten evidence."""
    for field in (
        "filled_price",
        "fill_price",
        "avg_fill_price",
        "average_fill_price",
        "closed_price",
        "exit_price",
        "last_price",
        "stop_price",
        "limit_price",
    ):
        value = evidence_order.get(field)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue

    for field in ("last_price", "exit_price", "current_stop"):
        value = trade.get(field)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def update_profit_breakdown(trade, include_runner=False):
    tp1_profit = calculate_tp1_profit(trade)
    if tp1_profit is not None:
        trade["tp1_profit"] = tp1_profit

    if include_runner:
        trade["runner_profit"] = calculate_runner_profit(trade)

    total = 0.0
    has_profit = False
    for value in (trade.get("tp1_profit"), trade.get("runner_profit")):
        if value is not None:
            total += float(value)
            has_profit = True

    trade["total_profit"] = round(total, 2) if has_profit else None
    trade["realized_pnl"] = trade["total_profit"] if trade["total_profit"] is not None else 0.0
    update_pnl_totals(trade)
    return trade


BE_LOCKED_STOP_STATES = {"break_even", "runner_entry", "runner_original"}


def backfill_be_lock_fields(trade):
    trade.setdefault("be_state_locked", False)
    trade.setdefault("be_trigger_processed_at", None)
    trade.setdefault("be_duplicate_trigger_suppressed_count", 0)
    return trade


def is_be_state_locked(trade):
    backfill_be_lock_fields(trade)
    locked = (
        bool(trade.get("be_hit_at"))
        or trade.get("moved_to_be") is True
        or trade.get("be_state_locked") is True
        or trade.get("stop_state") in BE_LOCKED_STOP_STATES
    )
    if locked:
        return True

    persisted = (load_state().get("trades") or {}).get(trade.get("trade_id"))
    if not persisted:
        return False

    backfill_be_lock_fields(persisted)
    persisted_locked = (
        bool(persisted.get("be_hit_at"))
        or persisted.get("moved_to_be") is True
        or persisted.get("be_state_locked") is True
        or persisted.get("stop_state") in BE_LOCKED_STOP_STATES
    )
    if persisted_locked:
        for field in (
            "moved_to_be",
            "be_hit_at",
            "be_state_locked",
            "be_trigger_processed_at",
            "be_duplicate_trigger_suppressed_count",
            "stop_state",
            "current_stop",
            "stop_order_id",
        ):
            if field in persisted:
                trade[field] = persisted[field]
    return persisted_locked


def lock_be_state(trade, timestamp):
    backfill_be_lock_fields(trade)
    trade["be_state_locked"] = True
    if not trade.get("be_trigger_processed_at"):
        trade["be_trigger_processed_at"] = normalize_timestamp(timestamp) or datetime.now().isoformat()
    if not trade.get("be_hit_at") and trade.get("stop_state") == "break_even":
        trade["be_hit_at"] = trade["be_trigger_processed_at"]
    return trade


def be_trigger_crossed(trade, price):
    if trade.get("be_trigger") is None:
        return False
    if trade["direction"] == "long":
        return price >= trade["be_trigger"]
    if trade["direction"] == "short":
        return price <= trade["be_trigger"]
    return False


def suppress_duplicate_be_trigger(trade, timestamp):
    backfill_be_lock_fields(trade)
    trade["be_state_locked"] = True
    if not trade.get("be_trigger_processed_at"):
        trade["be_trigger_processed_at"] = trade.get("be_hit_at") or normalize_timestamp(timestamp) or datetime.now().isoformat()
    trade["be_duplicate_trigger_suppressed_count"] = int(
        trade.get("be_duplicate_trigger_suppressed_count") or 0
    ) + 1
    return trade


def is_runner_trade_eligible_for_noon_flatten(trade):
    if trade.get("status") != "active":
        return False
    if not trade.get("tp1_hit"):
        return False

    remaining_size = float(trade.get("remaining_size", 0) or 0)
    position_size = float(trade.get("position_size", 0) or 0)
    if remaining_size <= 0 or position_size <= 0:
        return False

    return (
        trade.get("stop_state") == "runner_original"
        or remaining_size < position_size
    )


def public_trade_dict(trade):
    normalized = dict(trade or {})
    backfill_be_lock_fields(normalized)
    repair_missing_be_trigger(normalized)
    if (
        normalized.get("tp1_hit")
        and float(normalized.get("remaining_size", 0) or 0) > 0
        and normalized.get("entry_price") is not None
        and normalized.get("current_stop") is not None
        and normalized.get("original_stop") is None
        and round_to_nearest_tick(normalized.get("current_stop"), normalized.get("symbol"))
        == round_to_nearest_tick(normalized.get("entry_price"), normalized.get("symbol"))
    ):
        normalized["moved_to_be"] = True
        normalized["stop_state"] = "runner_entry"
    elif (
        normalized.get("tp1_hit")
        and float(normalized.get("remaining_size", 0) or 0) > 0
        and normalized.get("original_stop") is not None
        and normalized.get("current_stop") is not None
        and round_to_nearest_tick(normalized.get("current_stop"), normalized.get("symbol"))
        == round_to_nearest_tick(normalized.get("original_stop"), normalized.get("symbol"))
    ):
        normalized["stop_state"] = "runner_original"
    if normalized.get("realized_pnl") is None:
        normalized["realized_pnl"] = calculate_realized_pnl(normalized)
    if normalized.get("tp1_profit") is None:
        tp1_profit = calculate_tp1_profit(normalized)
        if tp1_profit is not None:
            normalized["tp1_profit"] = tp1_profit
    if normalized.get("runner_profit") is None and normalized.get("exit_price") is not None:
        normalized["runner_profit"] = calculate_runner_profit(normalized)
    if normalized.get("total_profit") is None:
        total = 0.0
        has_profit = False
        for value in (normalized.get("tp1_profit"), normalized.get("runner_profit")):
            if value is not None:
                total += float(value)
                has_profit = True
        if has_profit:
            normalized["total_profit"] = round(total, 2)
    status = str(normalized.get("status") or "").lower()
    if status in {"closed", "archived"} or normalized.get("archived") is True:
        apply_closed_trade_accounting(normalized)
    else:
        update_pnl_totals(normalized)

    return {
        field: primitive_value(normalized.get(field))
        for field in TRADE_PUBLIC_FIELDS
    }


def append_event(state, trade_id, event_type, message=None, details=None, snapshot=None, timestamp=None):
    event = {
        "timestamp": normalize_timestamp(timestamp) or datetime.now().isoformat(),
        "trade_id": primitive_value(trade_id),
        "event_type": primitive_value(event_type),
        "message": primitive_value(message),
        "details": {
            str(key): primitive_value(value)
            for key, value in (details or {}).items()
        },
    }

    if snapshot is not None:
        event["snapshot"] = public_trade_dict(snapshot)

    state.setdefault("event_log", []).append(event)
    return event


def log_trade_event(trade_id, event_type, message=None, details=None, snapshot=None, timestamp=None):
    state = load_state()
    event = append_event(state, trade_id, event_type, message, details, snapshot, timestamp)
    state["system"]["last_update_at"] = datetime.now().isoformat()
    save_state(state, reason=f"log_trade_event:{event_type}")
    print(f"EVENT LOG {event_type} trade_id={trade_id} details={event['details']}")
    return event


def load_executor_state_store():
    if not os.path.exists(EXECUTOR_STATE_FILE):
        return {"orders": {}, "positions": {}}
    try:
        with open(EXECUTOR_STATE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return {"orders": {}, "positions": {}}
    if not isinstance(payload, dict):
        return {"orders": {}, "positions": {}}
    return payload


def reconstruct_trade_replay(trade):
    if not trade:
        return []

    executor_state = load_executor_state_store()
    orders = [
        order for order in (executor_state.get("orders") or {}).values()
        if order.get("trade_id") == trade.get("trade_id")
    ]
    orders.sort(key=lambda order: str(order.get("filled_at") or order.get("created_at") or order.get("cancelled_at") or ""))

    replay = []

    def add(event_type, timestamp, message, details=None):
        replay.append({
            "timestamp": timestamp or trade.get("created_at"),
            "trade_id": trade.get("trade_id"),
            "event_type": event_type,
            "message": message,
            "details": details or {},
        })

    add("submit_accepted", trade.get("created_at"), "Trade accepted by manager", {
        "symbol": trade.get("symbol"),
        "direction": trade.get("direction"),
        "position_size": trade.get("position_size"),
    })

    entry_order = next((order for order in orders if order.get("type") == "entry"), None)
    if entry_order:
        add("entry_filled", entry_order.get("filled_at"), "Executor entry filled", {
            "order_id": entry_order.get("order_id"),
            "filled_price": entry_order.get("filled_price"),
            "qty": entry_order.get("qty"),
        })

    original_stop = next(
        (order for order in orders if order.get("type") == "stop" and float(order.get("stop_price", 0)) == float(trade.get("original_stop") or 0)),
        None,
    )
    if original_stop:
        add("original_stop_placed", original_stop.get("created_at"), "Original stop placed", {
            "order_id": original_stop.get("order_id"),
            "stop_price": original_stop.get("stop_price"),
            "qty": original_stop.get("qty"),
        })

    be_stop = next(
        (order for order in orders if order.get("type") == "stop" and float(order.get("stop_price", 0)) == float(trade.get("entry_price") or 0)),
        None,
    )
    if be_stop:
        add("be_trigger_hit", be_stop.get("created_at"), "BE trigger inferred from BE stop creation", {
            "be_trigger": trade.get("be_trigger"),
            "entry_price": trade.get("entry_price"),
        })
        add("be_stop_placed", be_stop.get("created_at"), "BE stop placed", {
            "order_id": be_stop.get("order_id"),
            "stop_price": be_stop.get("stop_price"),
            "qty": be_stop.get("qty"),
        })

    if original_stop and original_stop.get("cancelled_at"):
        add("original_stop_canceled", original_stop.get("cancelled_at"), "Original stop canceled", {
            "order_id": original_stop.get("order_id"),
        })

    tp1_order = next((order for order in orders if order.get("type") == "limit"), None)
    if tp1_order:
        add("tp1_order_active", tp1_order.get("created_at"), "TP1 order created and active", {
            "order_id": tp1_order.get("order_id"),
            "limit_price": tp1_order.get("limit_price"),
            "qty": tp1_order.get("qty"),
            "status": tp1_order.get("status"),
        })
        add("tp1_fill_check", tp1_order.get("created_at"), "TP1 fill check event", {
            "direction": trade.get("direction"),
            "comparison": "short price <= tp1_price" if trade.get("direction") == "short" else "long price >= tp1_price",
            "tp1_price": trade.get("tp1_price"),
            "tp1_hit": trade.get("tp1_hit"),
        })

    add("stop_hit_close", trade.get("closed_at"), "Stop hit / close event", {
        "exit_reason": trade.get("exit_reason"),
        "exit_price": trade.get("exit_price"),
        "persisted_current_stop": trade.get("current_stop"),
        "executor_be_stop_id": be_stop.get("order_id") if be_stop else None,
    })
    add("final_trade_persistence_snapshot", trade.get("closed_at"), "Final trade persistence snapshot", public_trade_dict(trade))

    return replay


def audit_trade_lifecycle(trade):
    executor_state = load_executor_state_store()
    orders = [
        order for order in (executor_state.get("orders") or {}).values()
        if order.get("trade_id") == trade.get("trade_id")
    ]
    be_stop = next(
        (
            order for order in orders
            if order.get("type") == "stop"
            and trade.get("entry_price") is not None
            and float(order.get("stop_price", 0)) == float(trade.get("entry_price"))
        ),
        None,
    )
    tp1_order = next((order for order in orders if order.get("type") == "limit"), None)

    return {
        "tp1_short_comparison_correct": trade.get("direction") != "short" or (
            trade.get("tp1_price") is not None and float(trade["tp1_price"]) < float(trade["entry_price"])
        ),
        "tp1_order_active_before_close": bool(tp1_order and tp1_order.get("created_at") and trade.get("closed_at") and tp1_order["created_at"] <= trade["closed_at"]),
        "tp1_partial_reduced_remaining_size": bool(trade.get("tp1_hit") and float(trade.get("remaining_size", 0)) == float(trade.get("position_size", 0)) / 2),
        "be_executor_order_exists": bool(be_stop),
        "be_persisted_matches_executor": bool(
            be_stop
            and trade.get("moved_to_be") is True
            and trade.get("current_stop") is not None
            and float(trade["current_stop"]) == float(be_stop["stop_price"])
            and trade.get("stop_state") == "break_even"
        ),
        "pnl_signed": calculate_realized_pnl(trade),
        "observed_inconsistencies": [
            item for item in [
                "executor_has_be_stop_but_persistence_lost_be_state" if be_stop and not trade.get("moved_to_be") else None,
                "executor_has_tp1_limit_but_persistence_has_tp1_hit_false" if tp1_order and not trade.get("tp1_hit") else None,
                "closed_trade_missing_exit_price" if trade.get("status") == "closed" and trade.get("exit_price") is None else None,
            ]
            if item
        ],
    }


# =========================
# RECOVERY / RESTART RULES
# =========================


def set_engine_status(status):
    state = load_state()
    state["system"]["engine_status"] = status
    state["system"]["last_update_at"] = datetime.now().isoformat()
    save_state(state, reason=f"set_engine_status:{status}")


def get_active_trades():
    state = load_state()
    return [
        trade for trade in state["trades"].values()
        if trade.get("status") not in ["closed", "error"]
    ]


# =========================
# PHASE 4 RECONCILIATION RULES
# =========================

# These rules define how the system reconciles INTERNAL STATE
# on restart BEFORE any broker/API verification exists.
#
# Scope:
# - File-based truth only (persistence_state.json)
# - No external broker validation
# - No order re-submission
#
# RULE SET:
#
# 1. CLOSED / ERROR TRADES
# - No action taken
# - Tagged as: "no_action"
#
# 2. ZERO POSITION SIZE
# - If remaining_size <= 0
# - Force status = "closed"
# - Tagged as: "closed_on_restart"
#
# 3. MISSING STOP PROTECTION
# - If stop_order_id is None
# - Trade remains ACTIVE
# - Tagged as: "missing_stop_protection"
# - NO automatic fix (handled in Phase 5)
#
# 4. RUNNER STATE (TP1 HIT)
# - If tp1_hit == True
# - Tagged as: "runner_recovered"
#
# 5. ACTIVE BASE TRADE
# - All other active trades
# - Tagged as: "active_recovered"
#
# GUARANTEES:
# - Every trade is classified on restart
# - No duplicate execution occurs
# - System state becomes consistent internally
#
# NON-GUARANTEES (Handled Later):
# - Broker position sync
# - Stop order verification
# - Order re-creation
# - Duplicate fill detection
#
# Phase 4 = INTERNAL CONSISTENCY ONLY
# Phase 5 = EXTERNAL (BROKER) VALIDATION
#
# =========================


def recover_trade_state(trade):
    # Clear stale lock on restart
    trade["locked"] = False

    if trade["status"] in ["closed", "error"]:
        trade["recovery_status"] = "no_action"
        return trade

    if trade["remaining_size"] <= 0:
        trade["status"] = "closed"
        trade["recovery_status"] = "closed_on_restart"
        return trade

    if not trade["stop_order_id"]:
        trade["recovery_status"] = "missing_stop_protection"
        return trade

    if trade["tp1_hit"]:
        trade["recovery_status"] = "runner_recovered"
    else:
        trade["recovery_status"] = "active_recovered"

    return trade


def reconcile_on_startup():
    set_engine_status("restarting")

    state = load_state()
    executor_orders = fetch_executor_orders()
    executor_snapshot = fetch_executor_snapshot()
    recovered = []

    for trade_id, trade in state["trades"].items():
        updated_trade = recover_trade_state(trade)
        updated_trade = reconcile_trade_with_executor_activity(
            updated_trade,
            executor_orders,
            executor_snapshot,
        )
        state["trades"][trade_id] = serialize_trade(updated_trade)
        recovered.append({
            "trade_id": trade_id,
            "status": updated_trade.get("status"),
            "recovery_status": updated_trade.get("recovery_status"),
            "locked": updated_trade.get("locked"),
            "stop_order_id": updated_trade.get("stop_order_id"),
            "tp1_order_id": updated_trade.get("tp1_order_id"),
            "current_stop": updated_trade.get("current_stop"),
        })

    known_trade_ids = set(state["trades"].keys())
    executor_trade_ids = {
        order.get("trade_id")
        for order in executor_orders
        if order.get("trade_id") and order.get("status") == "active"
    }
    for trade_id in sorted(executor_trade_ids - known_trade_ids):
        recovered_trade = recover_missing_trade_from_executor_activity(
            state,
            trade_id,
            executor_orders,
            executor_snapshot,
        )
        if recovered_trade:
            state["trades"][trade_id] = serialize_trade(recovered_trade)
            recovered.append({
                "trade_id": trade_id,
                "status": recovered_trade.get("status"),
                "recovery_status": recovered_trade.get("recovery_status"),
                "locked": recovered_trade.get("locked"),
                "stop_order_id": recovered_trade.get("stop_order_id"),
                "tp1_order_id": recovered_trade.get("tp1_order_id"),
                "current_stop": recovered_trade.get("current_stop"),
            })

    orphan_exposure = build_orphan_executor_exposure(state, executor_orders, executor_snapshot)
    persist_orphan_exposure_event_if_needed(state, orphan_exposure)
    state["orphan_exposure"] = orphan_exposure

    state["system"]["engine_status"] = "running"
    state["system"]["last_update_at"] = datetime.now().isoformat()
    save_state(state, reason="reconcile_on_startup")

    return recovered


# =========================
# SYNC LAYER
# =========================

def fetch_executor_orders():
    try:
        response = requests.get(EXECUTOR_ORDERS_URL, timeout=1.0)
        data = response.json()
        if data.get("ok"):
            return data.get("orders", [])
        return []
    except Exception as e:
        print(f"SYNC: failed to fetch executor orders: {e}")
        return []

def fetch_executor_snapshot():
    try:
        response = requests.get(EXECUTOR_SNAPSHOT_URL, timeout=1.0)
        data = response.json()

        if data.get("ok"):
            return merge_rithmic_atr_into_symbol_snapshot(data.get("symbols", {}))

        return merge_rithmic_atr_into_symbol_snapshot({})

    except Exception as e:
        print(f"SYNC: failed to fetch executor snapshot: {e}")
        return merge_rithmic_atr_into_symbol_snapshot({})


def normalize_atr_symbol(symbol):
    return normalize_symbol_root(symbol)


def load_rithmic_atr_snapshot_store():
    print(f"ATR DEBUG path={RITHMIC_ATR_SNAPSHOT_FILE}")
    print(f"ATR DEBUG exists={os.path.exists(RITHMIC_ATR_SNAPSHOT_FILE)}")

    if not os.path.exists(RITHMIC_ATR_SNAPSHOT_FILE):
        raise ValueError("ATR_NOT_READY")

    file_age_seconds = datetime.now().timestamp() - os.path.getmtime(RITHMIC_ATR_SNAPSHOT_FILE)
    print(f"ATR DEBUG file_age_seconds={file_age_seconds}")
    if file_age_seconds > RITHMIC_ATR_SNAPSHOT_MAX_AGE_SECONDS:
        raise ValueError("ATR_NOT_READY")

    with open(RITHMIC_ATR_SNAPSHOT_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)

    print(f"ATR DEBUG payload={payload}")

    if not isinstance(payload, dict):
        raise ValueError("ATR_NOT_READY")

    return payload


def load_rithmic_atr_snapshot_store_raw():
    if not os.path.exists(RITHMIC_ATR_SNAPSHOT_FILE):
        return {"symbols": {}}
    try:
        with open(RITHMIC_ATR_SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return {"symbols": {}}
    if not isinstance(payload, dict):
        return {"symbols": {}}
    return payload


def load_rithmic_recent_bars_store():
    if not os.path.exists(RITHMIC_RECENT_BARS_FILE):
        return {"symbols": {}}

    try:
        with open(RITHMIC_RECENT_BARS_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        print(f"ATR DEBUG recent_bars_load_failed={repr(exc)}")
        return {"symbols": {}}

    if not isinstance(payload, dict):
        return {"symbols": {}}
    return payload


def get_atr_completed_bars(symbol, atr_bar_timestamp, period=ATR_PERIOD):
    payload = load_rithmic_recent_bars_store()
    entries = find_rithmic_symbol_snapshot(payload, symbol)
    if not isinstance(entries, list):
        entries = (payload.get("symbols") or {}).get(str(symbol).upper(), [])

    bars = []
    for entry in entries or []:
        try:
            if str(entry.get("timestamp")) <= str(atr_bar_timestamp):
                bars.append({
                    "timestamp": str(entry["timestamp"]),
                    "symbol": str(entry.get("symbol") or symbol).upper(),
                    "open": float(entry["open"]),
                    "high": float(entry["high"]),
                    "low": float(entry["low"]),
                    "close": float(entry["close"]),
                })
        except Exception:
            continue

    bars.sort(key=lambda item: item["timestamp"])
    return bars[-period:]


def compute_simple_atr_from_completed_bars(bars):
    if len(bars) < ATR_PERIOD:
        return None

    true_ranges = []
    previous_close = None
    for bar in bars:
        high = float(bar["high"])
        low = float(bar["low"])
        if previous_close is None:
            true_range = high - low
        else:
            true_range = max(high - low, abs(high - previous_close), abs(low - previous_close))
        true_ranges.append(true_range)
        previous_close = float(bar["close"])

    return sum(true_ranges[-ATR_PERIOD:]) / float(ATR_PERIOD)


def find_abnormal_atr_bar(bars):
    if not bars:
        return None

    ranges = [
        {
            "timestamp": bar["timestamp"],
            "range": round(float(bar["high"]) - float(bar["low"]), 4),
            "open": bar["open"],
            "high": bar["high"],
            "low": bar["low"],
            "close": bar["close"],
        }
        for bar in bars
    ]
    sorted_ranges = sorted(ranges, key=lambda item: item["range"])
    median_range = sorted_ranges[len(sorted_ranges) // 2]["range"]
    largest = sorted_ranges[-1]

    if median_range > 0 and largest["range"] >= median_range * 3:
        return largest
    return None


def validate_atr_sanity(symbol, atr_snapshot):
    atr_value = float(atr_snapshot["atr_value"])
    completed_bars = get_atr_completed_bars(symbol, atr_snapshot["atr_bar_timestamp"])
    recomputed_atr = compute_simple_atr_from_completed_bars(completed_bars)
    abnormal_bar = find_abnormal_atr_bar(completed_bars)

    atr_snapshot["atr_completed_bars"] = completed_bars
    atr_snapshot["atr_recomputed_simple"] = recomputed_atr
    atr_snapshot["atr_abnormal_bar"] = abnormal_bar

    if atr_value <= 0 or atr_value > ATR_MAX_SANITY_VALUE:
        raise ValueError(f"ATR_ABNORMAL value={atr_value}")

    if abnormal_bar and abnormal_bar["range"] > max(atr_value * 2, 50):
        raise ValueError(f"ATR_ABNORMAL malformed_bar={abnormal_bar['timestamp']}")


def merge_rithmic_atr_into_symbol_snapshot(symbol_snapshot):
    merged_snapshot = {}

    for symbol, snapshot in (symbol_snapshot or {}).items():
        merged_snapshot[str(symbol).upper()] = dict(snapshot or {})

    try:
        atr_payload = load_rithmic_atr_snapshot_store()
    except ValueError:
        print("ATR DEBUG load_failed=ValueError('ATR_NOT_READY')")
        return merged_snapshot
    except Exception as e:
        print(f"ATR DEBUG load_failed={repr(e)}")
        print(f"SYNC: failed to load rithmic ATR snapshot: {e}")
        return merged_snapshot

    atr_symbols = atr_payload.get("symbols", {})
    if not isinstance(atr_symbols, dict):
        return merged_snapshot

    for symbol, atr_snapshot in atr_symbols.items():
        normalized_symbol = str(symbol or "").upper()
        if not normalized_symbol or not isinstance(atr_snapshot, dict):
            continue

        target_snapshot = merged_snapshot.setdefault(normalized_symbol, {})
        target_snapshot["atr_1m_14"] = atr_snapshot.get("atr_value")
        target_snapshot["atr_source"] = atr_snapshot.get("atr_source", "rithmic_live_listener_1m14")
        target_snapshot["atr_bar_timestamp"] = atr_snapshot.get("atr_bar_timestamp")

        if atr_snapshot.get("atr_value") is not None and atr_snapshot.get("atr_bar_timestamp"):
            target_snapshot["atr_status"] = "ready"
            target_snapshot["atr_error"] = None
        else:
            target_snapshot.setdefault("atr_status", "not_ready")
            target_snapshot.setdefault("atr_error", "ATR_NOT_READY")

    return merged_snapshot


def find_rithmic_symbol_snapshot(payload, symbol):
    candidates = build_symbol_candidates(symbol)

    collections = []
    if isinstance(payload.get("symbols"), dict):
        collections.append(payload["symbols"])
    collections.append(payload)

    for collection in collections:
        for candidate in candidates:
            symbol_snapshot = collection.get(candidate)
            if isinstance(symbol_snapshot, dict):
                return symbol_snapshot

    return None


def fetch_live_atr_snapshot(symbol):
    payload = load_rithmic_atr_snapshot_store()
    symbol_snapshot = find_rithmic_symbol_snapshot(payload, symbol)

    if not symbol_snapshot:
        raise ValueError("ATR_NOT_READY")

    atr_value = symbol_snapshot.get("atr_value", symbol_snapshot.get("atr_1m_14"))
    atr_source = symbol_snapshot.get("atr_source") or "rithmic_live_listener_1m14"
    atr_bar_timestamp = (
        symbol_snapshot.get("atr_bar_timestamp")
        or symbol_snapshot.get("bar_timestamp")
        or symbol_snapshot.get("timestamp")
    )

    if atr_value is None or not atr_bar_timestamp:
        raise ValueError("ATR_NOT_READY")

    atr_snapshot = {
        "atr_value": float(atr_value),
        "atr_source": atr_source,
        "atr_bar_timestamp": atr_bar_timestamp,
    }
    validate_atr_sanity(symbol, atr_snapshot)
    return atr_snapshot


def find_tradingview_atr_record(symbol):
    candidates = []
    for candidate in build_symbol_candidates(symbol):
        try:
            normalized_candidate = normalize_tradingview_symbol(candidate)
        except ValueError:
            normalized_candidate = str(candidate or "").upper()
        for item in (candidate, normalized_candidate, normalize_symbol_root(candidate)):
            item = str(item or "").upper()
            if item and item not in candidates:
                candidates.append(item)

    for candidate in candidates:
        if candidate in TRADINGVIEW_ATR_CACHE:
            return TRADINGVIEW_ATR_CACHE[candidate].copy()

    state = load_state()
    tradingview_atr = state.get("tradingview_atr") or {}
    if not isinstance(tradingview_atr, dict):
        return None

    for candidate in candidates:
        atr_record = tradingview_atr.get(candidate)
        if isinstance(atr_record, dict):
            TRADINGVIEW_ATR_CACHE[candidate] = atr_record.copy()
            return atr_record.copy()

    return None


def parse_iso_timestamp(timestamp_value):
    if not timestamp_value:
        return None
    try:
        return datetime.fromisoformat(str(timestamp_value).replace("Z", "+00:00"))
    except Exception:
        return None


def fetch_tradingview_atr_snapshot(symbol):
    atr_record = find_tradingview_atr_record(symbol)
    if not atr_record:
        raise ValueError("ATR_NOT_READY")

    atr_value = atr_record.get("atr_value")
    received_at = atr_record.get("received_at")
    received_at_dt = parse_iso_timestamp(received_at)
    if atr_value is None or received_at_dt is None:
        raise ValueError("ATR_NOT_READY")

    age_seconds = (datetime.now(received_at_dt.tzinfo) - received_at_dt).total_seconds()
    if age_seconds > TRADINGVIEW_ATR_MAX_AGE_SECONDS:
        raise ValueError("ATR_NOT_READY")

    atr_snapshot = {
        "atr_value": float(atr_value),
        "atr_source": "tradingview_atr_relay",
        "atr_bar_timestamp": received_at,
        "atr_period": int(atr_record.get("atr_period", ATR_PERIOD)),
        "atr_timeframe": str(atr_record.get("timeframe", "")),
        "atr_received_at": received_at,
    }

    if not math.isfinite(atr_snapshot["atr_value"]) or atr_snapshot["atr_value"] <= 0:
        raise ValueError("ATR_NOT_READY")

    return atr_snapshot


def fetch_trade_entry_atr_snapshot(symbol):
    status = build_tradingview_atr_status_for_symbol(symbol)
    if status["status"] == "missing":
        raise ValueError("TV_ATR_MISSING")
    if status["status"] == "stale":
        raise ValueError("TV_ATR_STALE")
    return fetch_tradingview_atr_snapshot(symbol)


def build_tradingview_atr_status_for_symbol(symbol, reference_time=None):
    normalized_symbol = normalize_symbol_root(symbol)
    status_payload = {
        "symbol": normalized_symbol,
        "atr_value": None,
        "received_at": None,
        "age_seconds": None,
        "status": "missing",
    }

    atr_record = find_tradingview_atr_record(normalized_symbol)
    if not atr_record:
        return status_payload

    received_at = atr_record.get("received_at")
    received_at_dt = parse_iso_timestamp(received_at)
    atr_value = atr_record.get("atr_value")

    status_payload["atr_value"] = float(atr_value) if atr_value is not None else None
    status_payload["received_at"] = received_at

    if received_at_dt is None:
        status_payload["status"] = "missing"
        return status_payload

    if reference_time is None:
        reference_time = datetime.now(received_at_dt.tzinfo)
    elif reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=received_at_dt.tzinfo)
    else:
        reference_time = reference_time.astimezone(received_at_dt.tzinfo)

    age_seconds = max(0, int((reference_time - received_at_dt).total_seconds()))
    status_payload["age_seconds"] = age_seconds
    status_payload["status"] = "fresh" if age_seconds <= TRADINGVIEW_ATR_MAX_AGE_SECONDS else "stale"
    return status_payload


def build_tradingview_atr_status_payload(reference_time=None):
    statuses = [
        build_tradingview_atr_status_for_symbol(root_symbol, reference_time=reference_time)
        for root_symbol in get_ui_roots()
    ]
    return {
        "ok": True,
        "threshold_seconds": TRADINGVIEW_ATR_MAX_AGE_SECONDS,
        "symbols": statuses,
    }


def select_atr_snapshot(symbol):
    try:
        atr_snapshot = fetch_tradingview_atr_snapshot(symbol)
        print(
            "ATR SOURCE selected=tradingview "
            f"symbol={symbol} raw_value={atr_snapshot['atr_value']} "
            f"received_at={atr_snapshot.get('atr_received_at')}"
        )
        return atr_snapshot
    except ValueError as tv_error:
        print(f"ATR SOURCE tradingview_unavailable symbol={symbol} error={tv_error}")

    atr_snapshot = fetch_live_atr_snapshot(symbol)
    print(
        "ATR SOURCE selected=rithmic "
        f"symbol={symbol} raw_value={atr_snapshot['atr_value']} "
        f"bar_timestamp={atr_snapshot.get('atr_bar_timestamp')}"
    )
    return atr_snapshot


def find_executor_stop_for_trade(executor_orders, trade_id):
    matches = []
    for order in executor_orders:
        if order.get("trade_id") != trade_id:
            continue
        if order.get("type") != "stop":
            continue
        if order.get("status") != "active":
            continue
        matches.append(order)
    return matches


def find_executor_active_orders_for_trade(executor_orders, trade_id):
    matches = []
    for order in executor_orders:
        if order.get("trade_id") != trade_id:
            continue
        if order.get("status") != "active":
            continue
        matches.append(order)
    return matches


def find_executor_order_by_id(executor_orders, order_id):
    if not order_id:
        return None
    for order in executor_orders:
        if order.get("order_id") == order_id:
            return order
    return None


def find_matching_active_stop_from_response(executor_orders, response, trade_id, symbol, stop_price, qty):
    for order_id in response.get("existing_stop_ids") or []:
        order = find_executor_order_by_id(executor_orders, order_id)
        if active_stop_matches_request(order, trade_id, symbol, stop_price, qty):
            return order
    return None


def has_executor_tp1_fill_evidence(executor_orders, trade_id):
    for order in executor_orders:
        if order.get("trade_id") != trade_id:
            continue
        if order.get("type") != "limit":
            continue
        closed_reason = str(order.get("closed_reason") or "").strip().lower()
        if order.get("filled_at") or closed_reason == "limit_triggered" or float(order.get("filled_qty", 0) or 0) > 0:
            return True
    return False


def is_executor_stop_fill(order):
    if not isinstance(order, dict):
        return False
    if order.get("type") != "stop":
        return False
    status = str(order.get("status", "")).lower()
    if status == "filled":
        return True
    if status != "closed":
        return False
    closed_reason = str(order.get("closed_reason") or "").strip().lower()
    return bool(order.get("filled_at")) or closed_reason == "stop_triggered"


def find_recent_filled_stop_for_trade(executor_orders, trade):
    current_stop = find_executor_order_by_id(executor_orders, trade.get("stop_order_id"))
    if is_executor_stop_fill(current_stop):
        return current_stop

    filled_stops = [
        order for order in executor_orders
        if order.get("trade_id") == trade.get("trade_id")
        and is_executor_stop_fill(order)
    ]
    if not filled_stops:
        return None

    filled_stops.sort(key=lambda order: str(order.get("filled_at") or order.get("closed_at") or ""))
    return filled_stops[-1]


def is_executor_manual_exit_limit_fill(order):
    if not isinstance(order, dict):
        return False
    if order.get("type") != "limit":
        return False
    if order.get("oco_role") != "manual_exit_limit" and order.get("tag") != "manual_exit_limit":
        return False
    status = str(order.get("status", "")).lower()
    if status == "filled":
        return True
    if status != "closed":
        return False
    closed_reason = str(order.get("closed_reason") or "").strip().lower()
    return bool(order.get("filled_at")) or closed_reason == "limit_triggered"


def find_recent_filled_manual_exit_limit_for_trade(executor_orders, trade):
    manual_exit_order = find_executor_order_by_id(executor_orders, trade.get("manual_exit_order_id"))
    if is_executor_manual_exit_limit_fill(manual_exit_order):
        return manual_exit_order

    filled_limits = [
        order for order in executor_orders
        if order.get("trade_id") == trade.get("trade_id")
        and is_executor_manual_exit_limit_fill(order)
    ]
    if not filled_limits:
        return None

    filled_limits.sort(key=lambda order: str(order.get("filled_at") or order.get("closed_at") or ""))
    return filled_limits[-1]


def apply_manual_exit_limit_fill_from_executor(trade, manual_order, live_qty):
    filled_at = manual_order.get("filled_at") or manual_order.get("closed_at") or datetime.now().isoformat()
    filled_price = manual_order.get("filled_price")
    if filled_price is None:
        filled_price = manual_order.get("limit_price")
    filled_qty = float(manual_order.get("filled_qty") or manual_order.get("qty") or 0)
    live_abs_qty = abs(float(live_qty or 0))

    trade["manual_exit_order_id"] = manual_order.get("order_id") or trade.get("manual_exit_order_id")
    trade["manual_exit_price"] = filled_price
    trade["manual_exit_filled_at"] = filled_at
    trade["manual_exit_filled_qty"] = filled_qty
    trade["manual_exit_hit"] = True
    trade["tp1_hit"] = True
    trade["tp1_hit_at"] = trade.get("tp1_hit_at") or filled_at
    trade["tp1_filled_qty"] = filled_qty
    trade["tp1_exit_price"] = filled_price
    trade["tp1_order_id"] = trade.get("tp1_order_id") or manual_order.get("order_id")
    trade["tp1_price"] = filled_price
    trade["remaining_size"] = live_abs_qty
    trade["error_reason"] = None

    if live_abs_qty <= 0:
        trade["status"] = "closed"
        trade["remaining_size"] = 0
        trade["closed_at"] = filled_at
        trade["exit_reason"] = "manual_exit_limit"
        trade["exit_price"] = filled_price
        trade["stop_state"] = "flat"
        trade["recovery_status"] = "closed_from_manual_exit_limit"
    else:
        trade["status"] = "active"
        trade["recovery_status"] = "partial_manual_exit_limit_reconciled"

    update_profit_breakdown(trade, include_runner=False)
    if trade.get("status") == "closed":
        apply_closed_trade_accounting(trade)
    return trade


def find_executor_flatten_evidence_for_trade(executor_orders, trade):
    flattened_orders = []
    for order in executor_orders:
        if order.get("trade_id") != trade.get("trade_id"):
            continue
        if str(order.get("status", "")).lower() != "closed":
            continue
        if order.get("filled_at"):
            continue

        closed_reason = str(order.get("closed_reason") or "").strip().lower()
        if closed_reason and closed_reason not in {
            "flatten_symbol",
            "flatten_trade",
            "closed_after_limit_flat",
        }:
            continue

        flattened_orders.append(order)

    if not flattened_orders:
        return None

    flattened_orders.sort(key=lambda order: str(order.get("closed_at") or order.get("created_at") or ""))
    return flattened_orders[-1]


def active_stop_matches_request(order, trade_id, symbol, stop_price, qty):
    if not order:
        return False
    if order.get("trade_id") != trade_id:
        return False
    if order.get("type") != "stop" or order.get("status") != "active":
        return False
    if str(order.get("symbol", "")).upper() != str(symbol or "").upper():
        return False

    if round_to_nearest_tick(order.get("stop_price"), symbol) != round_to_nearest_tick(stop_price, symbol):
        return False

    requested_qty = float(qty or 0)
    if requested_qty > 0 and float(order.get("qty", 0) or 0) != requested_qty:
        return False

    return True


def find_matching_active_stop(executor_orders, trade_id, symbol, stop_price, qty):
    for order in executor_orders:
        if active_stop_matches_request(order, trade_id, symbol, stop_price, qty):
            return order
    return None


def find_executor_be_stop_for_trade(executor_orders, trade):
    return find_matching_active_stop(
        executor_orders,
        trade["trade_id"],
        trade.get("symbol"),
        trade.get("entry_price"),
        trade.get("remaining_size"),
    )


def find_executor_be_stop_history_for_trade(executor_orders, trade):
    entry_price = trade.get("entry_price")
    if entry_price is None:
        return None

    matches = []
    for order in executor_orders:
        if order.get("trade_id") != trade.get("trade_id"):
            continue
        if order.get("type") != "stop":
            continue
        if round_to_nearest_tick(order.get("stop_price"), trade.get("symbol")) != round_to_nearest_tick(entry_price, trade.get("symbol")):
            continue
        matches.append(order)

    if not matches:
        return None

    matches.sort(key=lambda order: str(order.get("created_at") or order.get("filled_at") or order.get("closed_at") or order.get("cancelled_at") or ""))
    return matches[0]


def apply_be_evidence_from_executor_history(trade, executor_orders):
    be_stop = find_executor_be_stop_history_for_trade(executor_orders, trade)
    if not be_stop:
        return trade

    trade["moved_to_be"] = True
    trade["stop_state"] = "break_even"
    if not trade.get("be_hit_at"):
        trade["be_hit_at"] = (
            be_stop.get("created_at")
            or be_stop.get("filled_at")
            or be_stop.get("closed_at")
            or be_stop.get("cancelled_at")
            or datetime.now().isoformat()
        )
    lock_be_state(trade, trade.get("be_hit_at"))
    return trade


def response_is_active_stop_exists(response):
    return (
        not response.get("ok")
        and response.get("message") == "Active stop already exists for this trade"
    )


def round_price(value):
    return round(float(value), 2)


def get_symbol_tick_size(symbol):
    return get_tick_size(symbol)


def round_to_nearest_tick(value, symbol):
    tick_size = get_symbol_tick_size(symbol)
    ticks = round(float(value) / tick_size)
    return round_price(ticks * tick_size)


def round_up_to_tick(value, symbol):
    tick_size = get_symbol_tick_size(symbol)
    ticks = int(-(-float(value) // tick_size))
    return round_price(ticks * tick_size)


def round_down_to_tick(value, symbol):
    tick_size = get_symbol_tick_size(symbol)
    ticks = int(float(value) // tick_size)
    return round_price(ticks * tick_size)


def normalize_atr_value_for_symbol(symbol, atr_value):
    return float(atr_value)


def calculate_atr_distance(atr_value, multiple=1.0):
    return float(math.ceil(float(atr_value) * float(multiple)))


def derive_trade_levels(fill_price, symbol, direction, atr_value):
    fill = round_to_nearest_tick(fill_price, symbol)
    stop_distance = calculate_atr_distance(atr_value)
    tp1_distance = calculate_atr_distance(atr_value)
    be_distance = calculate_atr_distance(atr_value, 0.5)

    if direction == "long":
        return {
            "entry_price": fill,
            "original_stop": round_down_to_tick(fill - stop_distance, symbol),
            "current_stop": round_down_to_tick(fill - stop_distance, symbol),
            "tp1_price": round_to_nearest_tick(fill + tp1_distance, symbol),
            "be_trigger": round_up_to_tick(fill + be_distance, symbol),
        }

    return {
        "entry_price": fill,
        "original_stop": round_up_to_tick(fill + stop_distance, symbol),
        "current_stop": round_up_to_tick(fill + stop_distance, symbol),
        "tp1_price": round_to_nearest_tick(fill - tp1_distance, symbol),
        "be_trigger": round_down_to_tick(fill - be_distance, symbol),
    }


def validate_derived_levels(direction, levels):
    entry_price = float(levels["entry_price"])
    original_stop = float(levels["original_stop"])
    current_stop = float(levels["current_stop"])
    tp1_price = float(levels["tp1_price"])
    be_trigger = float(levels["be_trigger"])

    if direction == "long":
        if not (original_stop < entry_price and current_stop < entry_price):
            raise ValueError("invalid_long_stop_alignment")
        if not (tp1_price > entry_price and be_trigger > entry_price):
            raise ValueError("invalid_long_target_alignment")
        return

    if not (original_stop > entry_price and current_stop > entry_price):
        raise ValueError("invalid_short_stop_alignment")
    if not (tp1_price < entry_price and be_trigger < entry_price):
        raise ValueError("invalid_short_target_alignment")


def update_stop_state_from_active_stop(trade):
    current_stop = trade.get("current_stop")
    entry_price = trade.get("entry_price")
    original_stop = trade.get("original_stop")

    if current_stop is None:
        return trade

    if (
        trade.get("tp1_hit")
        and float(trade.get("remaining_size", 0) or 0) > 0
        and entry_price is not None
        and float(current_stop) == float(entry_price)
    ):
        trade["moved_to_be"] = True
        if original_stop is not None:
            trade["current_stop"] = original_stop
            trade["stop_state"] = "runner_original"
        else:
            trade["stop_state"] = "runner_entry"
        if not trade.get("be_hit_at"):
            trade["be_hit_at"] = datetime.now().isoformat()
        lock_be_state(trade, trade.get("tp1_hit_at") or trade.get("be_hit_at"))
        return trade

    if entry_price is not None and float(current_stop) == float(entry_price):
        trade["moved_to_be"] = True
        trade["stop_state"] = "break_even"
        if not trade.get("be_hit_at"):
            trade["be_hit_at"] = datetime.now().isoformat()
        lock_be_state(trade, trade.get("be_hit_at"))
        return trade

    if (
        trade.get("tp1_hit")
        and trade.get("remaining_size", 0) > 0
        and original_stop is not None
        and float(current_stop) == float(original_stop)
    ):
        trade["stop_state"] = "runner_original"
        lock_be_state(trade, trade.get("tp1_hit_at") or datetime.now().isoformat())
        return trade

    if not trade.get("moved_to_be"):
        trade["stop_state"] = "original"

    return trade


def runner_original_stop_required_after_tp1(trade):
    if not trade.get("tp1_hit"):
        return False
    if float(trade.get("remaining_size", 0) or 0) <= 0:
        return False
    if trade.get("original_stop") is None:
        return False
    return True


def enforce_runner_original_stop_after_tp1(trade, active_stop=None, live_qty=None):
    if not runner_original_stop_required_after_tp1(trade):
        return False

    original_stop = trade.get("original_stop")
    if original_stop is None:
        return False

    if active_stop:
        trade["stop_order_id"] = active_stop.get("order_id") or trade.get("stop_order_id")
        if active_stop.get("oco_group"):
            trade["oco_group"] = active_stop.get("oco_group")
        elif active_stop.get("oco_parent_group") and not trade.get("oco_group"):
            trade["oco_group"] = active_stop.get("oco_parent_group")
        active_qty = float(active_stop.get("qty", 0) or 0)
        if active_qty > 0:
            trade["remaining_size"] = active_qty

    live_abs_qty = abs(float(live_qty or 0))
    if live_abs_qty > 0:
        trade["remaining_size"] = live_abs_qty

    trade["current_stop"] = original_stop
    trade["moved_to_be"] = True
    trade["stop_state"] = "runner_original"
    lock_be_state(trade, trade.get("tp1_hit_at") or trade.get("be_hit_at") or datetime.now().isoformat())

    if not active_stop:
        return True

    active_stop_price = active_stop.get("stop_price")
    active_stop_qty = float(active_stop.get("qty", 0) or 0)
    remaining_size = float(trade.get("remaining_size", 0) or 0)
    if (
        active_stop_price is None
        or active_stop_qty <= 0
        or remaining_size <= 0
        or round_to_nearest_tick(active_stop_price, trade.get("symbol"))
        == round_to_nearest_tick(original_stop, trade.get("symbol"))
    ):
        return True

    response = reset_stop_to_original(
        trade_id=trade["trade_id"],
        symbol=trade["symbol"],
        stop_price=original_stop,
        qty=remaining_size,
        watch_failures=False,
        oco_parent_group=protective_oco_group(trade),
    )
    if response.get("ok"):
        trade["stop_order_id"] = (
            response.get("broker_order_id")
            or response.get("new_stop_id")
            or trade.get("stop_order_id")
        )
        trade["recovery_status"] = "runner_original_stop_reissued"
    else:
        trade["recovery_status"] = "runner_original_stop_reissue_failed"
        log_trade_event(
            trade["trade_id"],
            "runner_original_reconcile_reset_failed",
            "Runner original stop reset failed after TP1",
            {"error": response.get("error") or response.get("message")},
            snapshot=trade,
            timestamp=datetime.now().isoformat(),
        )
    return True


def close_trade_from_executor_stop_fill(trade, stop_order):
    filled_at = stop_order.get("filled_at") or stop_order.get("closed_at") or datetime.now().isoformat()
    filled_price = stop_order.get("filled_price")
    if filled_price is None:
        filled_price = stop_order.get("stop_price")

    trade["stop_order_id"] = stop_order.get("order_id") or trade.get("stop_order_id")
    trade["status"] = "closed"
    trade["remaining_size"] = 0
    trade["closed_at"] = filled_at
    trade["exit_reason"] = "stop_hit"
    trade["exit_price"] = filled_price
    trade["error_reason"] = None
    trade["recovery_status"] = "closed_from_executor_stop_fill"

    if (
        trade.get("entry_price") is not None
        and filled_price is not None
        and float(filled_price) == float(trade["entry_price"])
    ):
        trade["moved_to_be"] = True
        trade["stop_state"] = "break_even"
        if not trade.get("be_hit_at"):
            trade["be_hit_at"] = filled_at
        lock_be_state(trade, trade.get("be_hit_at"))

    update_post_be_analytics(trade, trade.get("exit_price"), filled_at)
    update_profit_breakdown(trade, include_runner=True)
    apply_closed_trade_accounting(trade)
    print(
        f"SYNC: trade closed from executor stop fill [{trade['trade_id']}] "
        f"stop_id={trade.get('stop_order_id')} exit_price={trade.get('exit_price')}"
    )
    return trade


def close_trade_from_executor_flatten_evidence(trade, evidence_order):
    closed_at = evidence_order.get("closed_at") or datetime.now().isoformat()
    closed_reason = str(evidence_order.get("closed_reason") or "").strip().lower()

    trade["status"] = "closed"
    trade["remaining_size"] = 0
    trade["closed_at"] = closed_at
    trade["error_reason"] = None
    trade["recovery_status"] = "closed_from_executor_flatten_evidence"

    if evidence_order.get("type") == "stop":
        trade["stop_order_id"] = evidence_order.get("order_id") or trade.get("stop_order_id")

    if closed_reason == "closed_after_limit_flat":
        trade["exit_reason"] = "target_filled"
    elif closed_reason in {"flatten_symbol", "flatten_trade"}:
        trade["exit_reason"] = closed_reason
    else:
        trade["exit_reason"] = "executor_flatten"

    if trade.get("exit_reason") == "target_filled":
        trade["exit_price"] = resolve_runner_flatten_exit_price(trade, evidence_order) or trade.get("tp1_price")
    else:
        exit_price = resolve_runner_flatten_exit_price(trade, evidence_order)
        if exit_price is not None:
            trade["exit_price"] = exit_price

    update_post_be_analytics(trade, trade.get("exit_price"), closed_at)
    update_profit_breakdown(trade, include_runner=trade.get("exit_price") is not None)
    apply_closed_trade_accounting(trade)
    print(
        f"SYNC: trade closed from executor flatten evidence [{trade['trade_id']}] "
        f"reason={trade.get('exit_reason')} order_id={evidence_order.get('order_id')}"
    )
    return trade


def find_latest_trade_snapshot_from_events(state, trade_id):
    latest_snapshot = None
    latest_timestamp = ""
    for event in state.get("event_log", []):
        if event.get("trade_id") != trade_id:
            continue
        snapshot = event.get("snapshot")
        if not isinstance(snapshot, dict):
            continue
        timestamp = str(event.get("timestamp") or "")
        if timestamp >= latest_timestamp:
            latest_timestamp = timestamp
            latest_snapshot = dict(snapshot)
    return latest_snapshot


def trade_has_event_evidence(state, trade_id, event_types):
    wanted = {str(event_type or "").strip() for event_type in event_types if event_type}
    if not wanted:
        return False
    for event in state.get("event_log", []):
        if event.get("trade_id") != trade_id:
            continue
        if str(event.get("event_type") or "").strip() in wanted:
            return True
    return False


def recover_missing_trade_from_executor_activity(state, trade_id, executor_orders, executor_snapshot):
    snapshot_trade = find_latest_trade_snapshot_from_events(state, trade_id)
    if not snapshot_trade:
        return None

    active_orders = find_executor_active_orders_for_trade(executor_orders, trade_id)
    if not active_orders:
        return None

    trade = dict(snapshot_trade)
    trade["trade_id"] = trade_id
    trade["status"] = "active"
    trade["error_reason"] = None
    trade["recovery_status"] = "recovered_from_event_snapshot"
    if has_executor_tp1_fill_evidence(executor_orders, trade_id) or trade_has_event_evidence(
        state,
        trade_id,
        {"tp1_filled", "runner_stop_reset_to_original"},
    ):
        trade["tp1_hit"] = True

    active_stop = next((order for order in active_orders if order.get("type") == "stop"), None)
    if active_stop:
        trade["symbol"] = active_stop.get("symbol") or trade.get("symbol")
        trade["stop_order_id"] = active_stop.get("order_id")
        trade["remaining_size"] = float(active_stop.get("qty", 0) or 0)
        position_size = float(trade.get("position_size", 0) or 0)
        if runner_original_stop_required_after_tp1(trade):
            trade["current_stop"] = trade["original_stop"]
            trade["moved_to_be"] = True
            trade["stop_state"] = "runner_original"
        elif trade.get("tp1_hit"):
            trade["current_stop"] = active_stop.get("stop_price")
            if trade.get("original_stop") is None:
                trade["original_stop"] = active_stop.get("stop_price")
            trade["stop_state"] = "runner_original"
        elif position_size > 0 and float(active_stop.get("qty", 0) or 0) < position_size:
            trade["current_stop"] = active_stop.get("stop_price")
            trade["tp1_hit"] = True
            if trade.get("original_stop") is None:
                trade["original_stop"] = active_stop.get("stop_price")
            trade["stop_state"] = "runner_original"
        else:
            trade["current_stop"] = active_stop.get("stop_price")
    elif active_orders:
        trade["symbol"] = active_orders[0].get("symbol") or trade.get("symbol")

    symbol_snapshot = executor_snapshot.get(trade.get("symbol"), {})
    live_qty = abs(float(symbol_snapshot.get("position_qty", 0) or 0))
    if live_qty > 0 and not active_stop:
        trade["remaining_size"] = live_qty
    elif trade.get("remaining_size") in (None, 0):
        trade["remaining_size"] = live_qty

    if symbol_snapshot.get("avg_entry_price") and not trade.get("entry_price"):
        trade["entry_price"] = float(symbol_snapshot.get("avg_entry_price"))
    if symbol_snapshot.get("last_price") is not None:
        trade["last_price"] = symbol_snapshot.get("last_price")

    apply_be_evidence_from_executor_history(trade, executor_orders)
    if not enforce_runner_original_stop_after_tp1(trade, active_stop, live_qty):
        update_stop_state_from_active_stop(trade)
    if (
        trade.get("tp1_hit")
        and float(trade.get("remaining_size", 0) or 0) > 0
        and trade.get("stop_state") != "runner_original"
        and trade.get("original_stop") is not None
        and trade.get("current_stop") is not None
        and round_to_nearest_tick(trade.get("current_stop"), trade.get("symbol"))
        == round_to_nearest_tick(trade.get("original_stop"), trade.get("symbol"))
    ):
        trade["stop_state"] = "runner_original"
    return trade


def is_executor_working_order(order):
    return str(order.get("status") or "").lower() == "active"


def build_orphan_executor_exposure(state, executor_orders, executor_snapshot):
    active_trades = {
        trade_id: trade
        for trade_id, trade in (state.get("trades") or {}).items()
        if trade.get("status") == "active"
    }
    managed_open_trades = {
        trade_id: trade
        for trade_id, trade in (state.get("trades") or {}).items()
        if trade.get("status") not in ("closed", "error")
    }
    active_trade_ids = set(active_trades.keys())
    managed_open_trade_ids = set(managed_open_trades.keys())
    active_trade_symbols = {
        str(trade.get("symbol") or "").upper()
        for trade in active_trades.values()
        if trade.get("symbol")
    }
    managed_open_trade_symbols = {
        str(trade.get("symbol") or "").upper()
        for trade in managed_open_trades.values()
        if trade.get("symbol")
    }

    working_orders_by_symbol = {}
    for order in executor_orders or []:
        if not is_executor_working_order(order):
            continue
        symbol = str(order.get("symbol") or "").upper()
        if not symbol:
            continue
        working_orders_by_symbol.setdefault(symbol, []).append(order)

    symbols = set(working_orders_by_symbol.keys())
    symbols.update(str(symbol or "").upper() for symbol in (executor_snapshot or {}).keys())
    items = []
    manager_state_issues = []

    for symbol in sorted(symbol for symbol in symbols if symbol):
        symbol_snapshot = (executor_snapshot or {}).get(symbol, {}) or {}
        position_qty = float(symbol_snapshot.get("position_qty", 0) or 0)
        working_orders = working_orders_by_symbol.get(symbol, [])
        executor_trade_ids = sorted({
            order.get("trade_id")
            for order in working_orders
            if order.get("trade_id")
        })
        has_executor_exposure = abs(position_qty) > 0 or bool(working_orders)
        if not has_executor_exposure:
            continue

        matched_by_trade_id = any(trade_id in active_trade_ids for trade_id in executor_trade_ids)
        matched_by_symbol = not executor_trade_ids and symbol in active_trade_symbols
        if matched_by_trade_id or matched_by_symbol:
            continue

        managed_by_trade_id = any(trade_id in managed_open_trade_ids for trade_id in executor_trade_ids)
        managed_by_symbol = not executor_trade_ids and symbol in managed_open_trade_symbols
        if managed_by_trade_id or managed_by_symbol:
            matching_manager_trades = [
                {
                    "trade_id": trade_id,
                    "status": trade.get("status"),
                    "symbol": trade.get("symbol"),
                    "remaining_size": trade.get("remaining_size"),
                    "created_at": trade.get("created_at"),
                }
                for trade_id, trade in managed_open_trades.items()
                if trade_id in executor_trade_ids or str(trade.get("symbol") or "").upper() == symbol
            ]
            manager_state_issues.append({
                "symbol": symbol,
                "position_qty": position_qty,
                "avg_entry_price": symbol_snapshot.get("avg_entry_price"),
                "last_price": symbol_snapshot.get("last_price"),
                "executor_trade_ids": executor_trade_ids,
                "active_order_ids": [
                    order.get("order_id")
                    for order in working_orders
                    if order.get("order_id")
                ],
                "manager_trades": matching_manager_trades,
                "reason": "executor_exposure_matches_non_active_manager_trade",
            })
            continue

        stop_order = symbol_snapshot.get("stop_order")
        if not stop_order:
            stop_order = next((order for order in working_orders if order.get("type") == "stop"), None)

        items.append({
            "symbol": symbol,
            "position_qty": position_qty,
            "avg_entry_price": symbol_snapshot.get("avg_entry_price"),
            "last_price": symbol_snapshot.get("last_price"),
            "executor_trade_ids": executor_trade_ids,
            "active_order_ids": [
                order.get("order_id")
                for order in working_orders
                if order.get("order_id")
            ],
            "working_orders": [
                {
                    "order_id": order.get("order_id"),
                    "trade_id": order.get("trade_id"),
                    "symbol": order.get("symbol"),
                    "type": order.get("type"),
                    "status": order.get("status"),
                    "qty": order.get("qty"),
                    "stop_price": order.get("stop_price"),
                    "limit_price": order.get("limit_price"),
                    "tag": order.get("tag"),
                }
                for order in working_orders
            ],
            "stop_order": stop_order,
            "reason": "executor_exposure_without_active_manager_trade",
        })

    return {
        "has_orphans": bool(items),
        "has_manager_state_issue": bool(manager_state_issues),
        "severity": "critical" if items or manager_state_issues else "none",
        "message": (
            "CRITICAL UNSUPERVISED EXPOSURE"
            if items
            else (
                "CRITICAL MANAGER TRADE STATE DESYNC"
                if manager_state_issues
                else None
            )
        ),
        "items": items,
        "manager_state_issues": manager_state_issues,
    }


def persist_orphan_exposure_event_if_needed(state, orphan_exposure):
    system_state = state.setdefault("system", {})
    signature_items = orphan_exposure.get("items", []) or orphan_exposure.get("manager_state_issues", [])
    signature = "|".join(
        f"{item.get('symbol')}:{item.get('position_qty')}:{','.join(item.get('active_order_ids') or [])}"
        for item in signature_items
    )
    if not orphan_exposure.get("has_orphans") and not orphan_exposure.get("has_manager_state_issue"):
        if system_state.get("orphan_exposure_signature"):
            system_state["orphan_exposure_signature"] = None
            return True
        return False

    if system_state.get("orphan_exposure_signature") == signature:
        return False

    event_type = "critical_orphan_executor_exposure"
    message = "CRITICAL UNSUPERVISED EXPOSURE: executor has exposure with no active manager trade"
    details_source = orphan_exposure.get("items", [])
    if orphan_exposure.get("has_manager_state_issue") and not orphan_exposure.get("has_orphans"):
        event_type = "critical_manager_trade_state_desync"
        message = "CRITICAL MANAGER TRADE STATE DESYNC: executor exposure matches a non-active manager trade"
        details_source = orphan_exposure.get("manager_state_issues", [])

    append_event(
        state,
        "SYSTEM",
        event_type,
        message,
        details={
            "symbols": [item.get("symbol") for item in details_source],
            "positions": {
                item.get("symbol"): item.get("position_qty")
                for item in details_source
            },
            "active_order_ids": [
                order_id
                for item in details_source
                for order_id in (item.get("active_order_ids") or [])
            ],
        },
    )
    system_state["orphan_exposure_signature"] = signature
    return True


def reconcile_trade_with_executor_activity(trade, executor_orders, executor_snapshot):
    if trade.get("status") == "reserved":
        active_orders = find_executor_active_orders_for_trade(executor_orders, trade["trade_id"])
        entry_order = next(
            (
                order for order in executor_orders
                if order.get("trade_id") == trade["trade_id"]
                and order.get("type") == "entry"
                and order.get("status") == "filled"
            ),
            None,
        )
        symbol = trade.get("symbol")
        symbol_snapshot = executor_snapshot.get(symbol, {}) if symbol else {}
        live_qty = abs(float(symbol_snapshot.get("position_qty", 0) or 0))
        active_stop = next((order for order in active_orders if order.get("type") == "stop"), None)
        active_tp1 = next((order for order in active_orders if order.get("type") == "limit" and order.get("tag") == "tp1"), None)

        if entry_order or active_orders or live_qty > 0:
            if entry_order:
                trade["symbol"] = entry_order.get("symbol") or trade.get("symbol")
                trade["execution_symbol"] = entry_order.get("resolved_symbol") or entry_order.get("symbol") or trade.get("execution_symbol")
                if entry_order.get("filled_price") is not None:
                    trade["entry_price"] = float(entry_order.get("filled_price"))
                trade["fill_price_source"] = entry_order.get("fill_price_source") or trade.get("fill_price_source")
            elif symbol_snapshot.get("avg_entry_price"):
                trade["entry_price"] = float(symbol_snapshot.get("avg_entry_price"))

            capture_entry_leg_extremes(trade, entry_order, symbol_snapshot, trade)

            if active_stop:
                trade["stop_order_id"] = active_stop.get("order_id")
                trade["original_stop"] = active_stop.get("stop_price")
                trade["current_stop"] = active_stop.get("stop_price")
                if active_stop.get("oco_group"):
                    trade["oco_group"] = active_stop.get("oco_group")
                trade["remaining_size"] = float(active_stop.get("qty", 0) or live_qty or trade.get("remaining_size", 0))
            elif live_qty > 0:
                trade["remaining_size"] = live_qty

            if active_tp1:
                trade["tp1_order_id"] = active_tp1.get("order_id")
                trade["tp1_price"] = active_tp1.get("limit_price")
                if active_tp1.get("oco_group"):
                    trade["oco_group"] = active_tp1.get("oco_group")

            if trade.get("entry_price") is not None and trade.get("original_stop") is not None and trade.get("tp1_price") is not None:
                try:
                    entry = float(trade["entry_price"])
                    tp1 = float(trade["tp1_price"])
                    trade["be_trigger"] = round_to_nearest_tick(
                        entry + ((tp1 - entry) / 2),
                        trade.get("symbol"),
                    )
                except (TypeError, ValueError):
                    pass

            trade["status"] = "active"
            trade["recovery_status"] = "recovered_reserved_submit_from_executor"
            update_stop_state_from_active_stop(trade)
            return trade

    if trade.get("status") == "error":
        symbol_snapshot = executor_snapshot.get(trade.get("symbol"), {}) if trade.get("symbol") else {}
        live_qty = float(symbol_snapshot.get("position_qty", 0) or 0)
        active_orders = find_executor_active_orders_for_trade(executor_orders, trade["trade_id"])
        active_stop = next((order for order in active_orders if order.get("type") == "stop"), None)
        if live_qty != 0 and active_stop:
            trade["stop_order_id"] = active_stop.get("order_id")
            trade["current_stop"] = active_stop.get("stop_price")
            if active_stop.get("oco_group"):
                trade["oco_group"] = active_stop.get("oco_group")
            elif active_stop.get("oco_parent_group") and not trade.get("oco_group"):
                trade["oco_group"] = active_stop.get("oco_parent_group")
            reconcile_tp1_runner_from_executor_truth(trade, active_stop, live_qty)
            update_stop_state_from_active_stop(trade)
        return trade

    if trade.get("status") != "active":
        return trade

    symbol_snapshot = executor_snapshot.get(trade["symbol"], {})
    live_qty = float(symbol_snapshot.get("position_qty", 0) or 0)
    apply_be_evidence_from_executor_history(trade, executor_orders)

    manual_exit_fill = find_recent_filled_manual_exit_limit_for_trade(executor_orders, trade)
    if manual_exit_fill:
        return apply_manual_exit_limit_fill_from_executor(trade, manual_exit_fill, live_qty)

    active_stops = find_executor_stop_for_trade(executor_orders, trade["trade_id"])
    active_tp1 = next(
        (
            order for order in find_executor_active_orders_for_trade(executor_orders, trade["trade_id"])
            if order.get("type") == "limit" and order.get("tag") == "tp1"
        ),
        None,
    )
    if active_stops:
        active_stop = active_stops[0]
        trade["stop_order_id"] = active_stop.get("order_id")
        if active_stop.get("oco_group"):
            trade["oco_group"] = active_stop.get("oco_group")
        elif active_stop.get("oco_parent_group") and not trade.get("oco_group"):
            trade["oco_group"] = active_stop.get("oco_parent_group")
        active_stop_qty = float(active_stop.get("qty", 0) or 0)
        position_size = float(trade.get("position_size", 0) or 0)
        if active_stop_qty > 0:
            trade["remaining_size"] = active_stop_qty
        if position_size > 0 and active_stop_qty > 0 and active_stop_qty < position_size:
            trade["tp1_hit"] = True
        reconcile_tp1_runner_from_executor_truth(trade, active_stop, live_qty)
        if not enforce_runner_original_stop_after_tp1(trade, active_stop, live_qty):
            trade["current_stop"] = active_stop.get("stop_price")
            update_stop_state_from_active_stop(trade)
    if active_tp1 and not trade.get("tp1_hit"):
        trade["tp1_order_id"] = active_tp1.get("order_id")
        if active_tp1.get("oco_group"):
            trade["oco_group"] = active_tp1.get("oco_group")
        if trade.get("tp1_price") in (None, ""):
            trade["tp1_price"] = active_tp1.get("limit_price")
        repair_missing_be_trigger(trade)

    filled_stop = find_recent_filled_stop_for_trade(executor_orders, trade)
    if filled_stop and live_qty == 0 and not active_stops:
        return close_trade_from_executor_stop_fill(trade, filled_stop)

    flatten_evidence = find_executor_flatten_evidence_for_trade(executor_orders, trade)
    if flatten_evidence and live_qty == 0 and not active_stops:
        return close_trade_from_executor_flatten_evidence(trade, flatten_evidence)

    return trade


def reconcile_tp1_runner_from_executor_truth(trade, active_stop, live_qty):
    if not active_stop:
        return False

    live_abs_qty = abs(float(live_qty or 0))
    stop_qty = float(active_stop.get("qty", 0) or 0)
    protected_qty = stop_qty if stop_qty > 0 else live_abs_qty
    position_size = float(trade.get("position_size", 0) or 0)

    if protected_qty <= 0:
        return False

    changed = False
    if live_abs_qty > 0 and abs(protected_qty - live_abs_qty) > 1e-9:
        protected_qty = live_abs_qty

    if position_size > 0 and protected_qty < position_size:
        filled_qty = max(position_size - protected_qty, 0)
        if not trade.get("tp1_hit"):
            trade["tp1_hit"] = True
            changed = True
        if trade.get("tp1_filled_qty") in (None, ""):
            trade["tp1_filled_qty"] = filled_qty
            changed = True
        if not trade.get("tp1_hit_at"):
            trade["tp1_hit_at"] = active_stop.get("updated_at") or active_stop.get("created_at") or datetime.now().isoformat()
            changed = True

    if trade.get("remaining_size") != protected_qty:
        trade["remaining_size"] = protected_qty
        changed = True

    if trade.get("status") != "active":
        trade["status"] = "active"
        changed = True

    if trade.get("error_reason") is not None:
        trade["error_reason"] = None
        changed = True

    if changed:
        trade["recovery_status"] = "reconciled_from_executor_truth"
    return changed


def sync_trade_protection(trade, executor_orders, executor_snapshot):
    symbol_snapshot = executor_snapshot.get(trade["symbol"], {})
    live_qty = float(symbol_snapshot.get("position_qty", 0))

    if trade.get("status") == "error":
        active_executor_orders = find_executor_active_orders_for_trade(
            executor_orders,
            trade["trade_id"],
        )
        active_stops = [
            order for order in active_executor_orders
            if order.get("type") == "stop"
        ]
        if live_qty != 0 and active_stops:
            stop_order = active_stops[0]
            trade["stop_order_id"] = stop_order.get("order_id")
            if stop_order.get("oco_group"):
                trade["oco_group"] = stop_order.get("oco_group")
            elif stop_order.get("oco_parent_group") and not trade.get("oco_group"):
                trade["oco_group"] = stop_order.get("oco_parent_group")
            reconcile_tp1_runner_from_executor_truth(trade, stop_order, live_qty)
            if not enforce_runner_original_stop_after_tp1(trade, stop_order, live_qty):
                trade["current_stop"] = stop_order.get("stop_price")
                update_stop_state_from_active_stop(trade)
            print(
                f"SYNC: error trade recovered from protected executor state "
                f"[{trade['trade_id']}] symbol={trade['symbol']} "
                f"qty={trade.get('remaining_size')} stop_id={trade.get('stop_order_id')}"
            )
            return trade
        if live_qty == 0 and not active_executor_orders:
            trade["status"] = "closed"
            trade["remaining_size"] = 0
            trade["closed_at"] = trade.get("closed_at") or datetime.now().isoformat()
            trade["exit_reason"] = trade.get("exit_reason") or "executor_flat_sync"
            trade["recovery_status"] = "closed_from_executor_sync"
            trade["error_reason"] = None
            print(
                f"SYNC: error trade closed from executor flat state "
                f"[{trade['trade_id']}] symbol={trade['symbol']}"
            )
        return trade

    if trade.get("status") != "active":
        return trade

    if trade.get("remaining_size", 0) <= 0:
        return trade

    trade = reconcile_trade_with_executor_activity(trade, executor_orders, executor_snapshot)
    if trade.get("status") != "active":
        return trade

    live_entry_price = float(symbol_snapshot.get("avg_entry_price", 0) or 0)

    if live_entry_price > 0 and not trade.get("entry_price"):
        if not trade.get("atr_value"):
            trade["recovery_status"] = "missing_atr_value"
            trade["error_reason"] = "persisted_atr_missing_for_entry_restore"
            print(f"SYNC: missing persisted ATR [{trade['trade_id']}] symbol={trade['symbol']}")
            return trade

        derived_levels = derive_trade_levels(
            fill_price=live_entry_price,
            symbol=trade["symbol"],
            direction=trade["direction"],
            atr_value=trade["atr_value"]
        )
        trade.update(derived_levels)
        trade["fill_price_source"] = "executor_snapshot_sync"
        print(
            f"SYNC: entry restored [{trade['trade_id']}] "
            f"entry={trade['entry_price']} atr={trade.get('atr_value')}"
        )

    if live_qty == 0:
        trade["recovery_status"] = "flat_without_close_evidence"
        trade["error_reason"] = "executor_flat_without_fill_evidence"
        print(
            f"SYNC: trade remains active without close evidence "
            f"[{trade['trade_id']}] symbol={trade['symbol']}"
        )
        return trade

    active_stops = find_executor_stop_for_trade(executor_orders, trade["trade_id"])

    if active_stops:
        stop_order = active_stops[0]
        trade["stop_order_id"] = stop_order.get("order_id")
        trade["current_stop"] = stop_order.get("stop_price")
        if stop_order.get("oco_group"):
            trade["oco_group"] = stop_order.get("oco_group")
        elif stop_order.get("oco_parent_group") and not trade.get("oco_group"):
            trade["oco_group"] = stop_order.get("oco_parent_group")
        reconcile_tp1_runner_from_executor_truth(trade, stop_order, live_qty)
        update_stop_state_from_active_stop(trade)
        if trade.get("recovery_status") != "reconciled_from_executor_truth":
            trade["recovery_status"] = "protection_synced"
        print(
            f"SYNC: stop linked [{trade['trade_id']}] "
            f"stop_id={trade['stop_order_id']} stop={trade['current_stop']}"
        )
        return trade

    if not trade.get("current_stop") or trade.get("remaining_size", 0) <= 0:
        trade["recovery_status"] = "missing_stop_protection"
        trade["error_reason"] = "stop_sync_failed"
        print(
            f"SYNC: missing stop rebuild inputs [{trade['trade_id']}] "
            f"stop={trade.get('current_stop')} qty={trade.get('remaining_size')}"
        )
        return trade

    response = place_stop_order(
        trade_id=trade["trade_id"],
        symbol=trade["symbol"],
        stop_price=trade["current_stop"],
        qty=trade["remaining_size"],
        watch_failures=False,
    )

    if response.get("ok"):
        trade["stop_order_id"] = response.get("broker_order_id")
        trade["recovery_status"] = "protection_rebuilt"
        trade["error_reason"] = None
        print(
            f"SYNC: stop rebuilt [{trade['trade_id']}] "
            f"stop_id={trade['stop_order_id']} stop={trade['current_stop']} qty={trade['remaining_size']}"
        )
    else:
        matching_stop = None
        if response_is_active_stop_exists(response):
            matching_stop = find_matching_active_stop(
                fetch_executor_orders(),
                trade["trade_id"],
                trade["symbol"],
                trade["current_stop"],
                trade["remaining_size"],
            )

        if matching_stop:
            trade["stop_order_id"] = matching_stop.get("order_id")
            trade["recovery_status"] = "protection_synced"
            trade["error_reason"] = None
            print(
                f"SYNC: stop rebuild already protected [{trade['trade_id']}] "
                f"stop_id={trade['stop_order_id']} stop={trade['current_stop']} qty={trade['remaining_size']}"
            )
            return trade

        register_execution_failure(response.get("error", response.get("message", "submit_stop_failed")))
        execution_watcher(response, "submit_stop")
        trade["recovery_status"] = "missing_stop_protection"
        trade["error_reason"] = response.get("error") or response.get("message") or "stop_sync_failed"
        print(f"SYNC: stop rebuild failed [{trade['trade_id']}] -> {trade['error_reason']}")

    return trade


def place_entry_order(trade_id, symbol, direction, qty):
    return dispatch_execution(
        "submit_entry",
        {
            "trade_id": trade_id,
            "symbol": symbol,
            "direction": direction,
            "qty": qty
        }
    )


def sync_all_active_trades():
    run_noon_runner_flatten_if_due()
    state = load_state()
    executor_orders = fetch_executor_orders()
    executor_snapshot = fetch_executor_snapshot()
    print("SYNC SNAPSHOT:", executor_snapshot)
    sync_results = []

    for trade_id, trade in state["trades"].items():
        updated_trade = sync_trade_protection(trade, executor_orders, executor_snapshot)
        state["trades"][trade_id] = serialize_trade(updated_trade)
        sync_results.append({
            "trade_id": trade_id,
            "status": updated_trade.get("status"),
            "recovery_status": updated_trade.get("recovery_status"),
            "stop_order_id": updated_trade.get("stop_order_id"),
            "current_stop": updated_trade.get("current_stop")
        })

    state["system"]["last_update_at"] = datetime.now().isoformat()
    save_state(state, reason="sync_all_active_trades")
    print("SYNC SUMMARY:", sync_results)
    return sync_results


def build_noon_runner_flatten_status_payload(reference_time=None):
    local_time = as_los_angeles_time(reference_time)
    state = load_state()
    system_state = state.get("system", {})
    return {
        "ok": True,
        "enabled": is_noon_runner_flatten_enabled(),
        "timezone": NOON_RUNNER_FLATTEN_TIMEZONE,
        "local_time": local_time.isoformat(),
        "local_date": local_time.date().isoformat(),
        "target_hour": NOON_RUNNER_FLATTEN_HOUR,
        "last_run_date": system_state.get("last_noon_runner_flatten_date"),
        "last_run_at": system_state.get("last_noon_runner_flatten_at"),
    }


def run_noon_runner_flatten_if_due(reference_time=None):
    local_time = as_los_angeles_time(reference_time)
    state = load_state()
    system_state = state.setdefault("system", {})

    if not is_noon_runner_flatten_enabled():
        return {"ok": True, "ran": False, "reason": "disabled", "flattened_trades": []}

    if local_time.hour < NOON_RUNNER_FLATTEN_HOUR:
        return {"ok": True, "ran": False, "reason": "before_noon", "flattened_trades": []}

    local_date = local_time.date().isoformat()
    if system_state.get("last_noon_runner_flatten_date") == local_date:
        return {"ok": True, "ran": False, "reason": "already_ran_today", "flattened_trades": []}

    executor_snapshot = fetch_executor_snapshot()
    flattened_trades = []

    for trade_id, trade in state.get("trades", {}).items():
        if not is_runner_trade_eligible_for_noon_flatten(trade):
            continue

        symbol_snapshot = (executor_snapshot or {}).get(trade.get("symbol"), {})
        exit_price = symbol_snapshot.get("last_price")
        if exit_price is None:
            exit_price = trade.get("last_price")
        if exit_price is None:
            exit_price = trade.get("current_stop")

        flatten_trade_symbol(trade_id=trade["trade_id"], symbol=trade["symbol"])
        trade["status"] = "closed"
        trade["exit_reason"] = "noon_runner_flatten"
        trade["closed_at"] = local_time.isoformat()
        trade["remaining_size"] = 0
        trade["stop_state"] = "flat"
        if exit_price is not None:
            trade["exit_price"] = float(exit_price)
        update_profit_breakdown(trade, include_runner=True)
        apply_closed_trade_accounting(trade)
        state["trades"][trade_id] = serialize_trade(trade)
        flattened_trades.append(trade_id)
        log_trade_event(
            trade["trade_id"],
            "noon_runner_flatten",
            "Noon PT runner flatten applied",
            {
                "exit_price": trade.get("exit_price"),
                "remaining_size": trade.get("remaining_size"),
                "tp1_profit": trade.get("tp1_profit"),
                "runner_profit": trade.get("runner_profit"),
                "total_profit": trade.get("total_profit"),
            },
            snapshot=trade,
            timestamp=local_time.isoformat(),
        )

    system_state["last_noon_runner_flatten_date"] = local_date
    system_state["last_noon_runner_flatten_at"] = local_time.isoformat()
    system_state["last_update_at"] = datetime.now().isoformat()
    save_state(state, reason="run_noon_runner_flatten_if_due")
    return {
        "ok": True,
        "ran": True,
        "reason": "noon_window",
        "flattened_trades": flattened_trades,
    }


def refresh_trades_from_executor_activity():
    run_noon_runner_flatten_if_due()
    state = load_state()
    executor_orders = fetch_executor_orders()
    executor_snapshot = fetch_executor_snapshot()
    changed = False

    for trade_id, trade in state["trades"].items():
        before = serialize_trade(dict(trade))
        if repair_missing_be_trigger(trade):
            state["trades"][trade_id] = serialize_trade(trade)
        updated_trade = reconcile_trade_with_executor_activity(trade, executor_orders, executor_snapshot)
        after = serialize_trade(updated_trade)
        if after != before:
            state["trades"][trade_id] = serialize_trade(updated_trade)
            changed = True

    known_trade_ids = set(state["trades"].keys())
    executor_trade_ids = {
        order.get("trade_id")
        for order in executor_orders
        if order.get("trade_id") and order.get("status") == "active"
    }
    for trade_id in sorted(executor_trade_ids - known_trade_ids):
        recovered_trade = recover_missing_trade_from_executor_activity(
            state,
            trade_id,
            executor_orders,
            executor_snapshot,
        )
        if recovered_trade:
            state["trades"][trade_id] = serialize_trade(recovered_trade)
            changed = True

    orphan_exposure = build_orphan_executor_exposure(state, executor_orders, executor_snapshot)
    if persist_orphan_exposure_event_if_needed(state, orphan_exposure):
        changed = True
    state["orphan_exposure"] = orphan_exposure

    if changed:
        state["system"]["last_update_at"] = datetime.now().isoformat()
        save_state(state, reason="refresh_trades_from_executor_activity")

    return state


def bootstrap_trade_manager():
    print(
        "TRADE MANAGER MODE "
        f"MODE={OPERATING_MODE} "
        f"env_var={OPERATING_MODE_ENV_VAR} "
        f"config_file={TRADE_MANAGER_CONFIG_FILE}"
    )
    print(f"ATR DEBUG startup_path={RITHMIC_ATR_SNAPSHOT_FILE}")
    print(f"ATR DEBUG startup_exists={os.path.exists(RITHMIC_ATR_SNAPSHOT_FILE)}")
    load_risk_state_from_persistence()
    reset_daily_risk_state_if_needed()
    ensure_connection()
    recovered = reconcile_on_startup()
    synced = sync_all_active_trades()
    persist_risk_state()
    print("RECOVERY SUMMARY:", recovered)
    return {
        "recovered": recovered,
        "synced": synced
    }


@app.route("/reset_qa_state", methods=["POST"])
def reset_qa_state_route():
    payload = request.get_json(silent=True) or {}
    clear_failed_test_trades = bool(payload.get("clear_failed_test_trades", True))
    result = reset_qa_escalation_state(
        clear_failed_test_trades=clear_failed_test_trades
    )
    return jsonify({
        "ok": True,
        "reset": result,
    })


# =========================
# PHASE 8 — ADVANCED QA LAYER
# Read-Only QA Agents (Observer System)
# =========================

@app.route("/debug/risk_state", methods=["GET"])
def debug_risk_state_route():
    state = load_state()
    executor_orders = fetch_executor_orders()
    executor_snapshot = fetch_executor_snapshot()
    orphan_exposure = build_orphan_executor_exposure(state, executor_orders, executor_snapshot)
    if persist_orphan_exposure_event_if_needed(state, orphan_exposure):
        state["system"]["last_update_at"] = datetime.now().isoformat()
        save_state(state, reason="debug_risk_state_orphan_exposure")
    return jsonify({
        "ok": True,
        "operating_mode": OPERATING_MODE,
        "risk_state": serialize_trade(RISK_STATE),
        "failure_state": serialize_trade(FAILURE_STATE),
        "noon_runner_flatten": build_noon_runner_flatten_status_payload(),
        "orphan_exposure": orphan_exposure,
    })


@app.route("/debug/instruments", methods=["GET"])
def debug_instruments_route():
    instruments = []
    default_listener_subscriptions = {
        root_symbol: {"exchange": exchange, "symbol": symbol}
        for exchange, symbol in get_default_listener_subscriptions()
        for root_symbol in [normalize_symbol_root(symbol)]
    }

    for root_symbol in get_ui_roots():
        spec = get_instrument_spec(root_symbol)
        listener_subscription = default_listener_subscriptions.get(root_symbol, {})
        instruments.append({
            "root_symbol": spec.get("root_symbol"),
            "exchange": spec.get("exchange") or listener_subscription.get("exchange"),
            "active_contract_hint": spec.get("front_month_symbol") or listener_subscription.get("symbol"),
            "tick_size": spec.get("tick_size"),
            "tick_value": spec.get("tick_value"),
            "point_value": spec.get("point_value"),
            "aliases": list(spec.get("aliases", ())),
        })

    return jsonify({
        "ok": True,
        "instruments": instruments,
    })


QA_LOGS = []


def qa_event(watcher, level, message, trade_id=None):
    event = {
        "timestamp": datetime.now().isoformat(),
        "watcher": watcher,
        "level": level,
        "trade_id": trade_id,
        "message": message
    }

    QA_LOGS.append(event)

    if level == "CRITICAL":
        register_qa_critical_failure(f"{watcher}: {message}")

    print(f"[{level}] [{watcher}] [{trade_id}] {message}")


# -------------------------
# TRADE INTEGRITY WATCHER
# -------------------------
def trade_integrity_watcher(trade):
    trade_id = trade.get("trade_id")

    if trade["status"] == "active" and trade["remaining_size"] <= 0:
        qa_event("TRADE_INTEGRITY", "CRITICAL",
                 "Active trade with zero size", trade_id)

    if (
        trade["moved_to_be"]
        and trade.get("stop_state") == "break_even"
        and trade["current_stop"] != trade["entry_price"]
    ):
        qa_event("TRADE_INTEGRITY", "WARNING",
                 "BE flag set but stop not at entry", trade_id)

    if trade["tp1_hit"] and trade["remaining_size"] >= trade["position_size"]:
        qa_event("TRADE_INTEGRITY", "WARNING",
                 "TP1 hit but size not reduced", trade_id)

    if trade["status"] == "error" and not trade.get("error_reason"):
        qa_event("TRADE_INTEGRITY", "CRITICAL",
                 "Error state without reason", trade_id)


# -------------------------
# PERFORMANCE WATCHER
# -------------------------
def performance_watcher(start_time, label):
    duration = (datetime.now() - start_time).total_seconds()

    if duration > 0.5:
        qa_event("PERFORMANCE", "WARNING",
                 f"{label} took {duration:.3f}s")


# -------------------------
# BUG WATCHER
# -------------------------
def bug_watcher(context, error):
    qa_event("BUG", "CRITICAL", f"{context}: {error}")


# -------------------------
# EXECUTION WATCHER
# -------------------------
def execution_watcher(response, action):
    if not response.get("ok"):
        error_text = str(response.get("error") or response.get("message") or "")
        if action == "submit_entry" and is_non_latching_paper_test_failure(error_text):
            qa_event("EXECUTION", "WARNING",
                     f"{action} failed (non-latching paper test): {response}")
            return
        qa_event("EXECUTION", "CRITICAL",
                 f"{action} failed: {response}")


# -------------------------
# SYSTEM HEALTH WATCHER
# -------------------------
def system_health_watcher():
    if not SYSTEM_CONNECTION["connected"]:
        qa_event("SYSTEM", "CRITICAL", "Disconnected from broker")

    if SYSTEM_CONNECTION["last_heartbeat"]:
        last = datetime.fromisoformat(SYSTEM_CONNECTION["last_heartbeat"])
        delta = (datetime.now() - last).total_seconds()

        if delta > 5:
            qa_event("SYSTEM", "WARNING",
                     f"Heartbeat stale ({delta:.1f}s)")
        else:
            qa_event("SYSTEM", "INFO",
                     f"Heartbeat OK ({delta:.1f}s)")


# -------------------------
# QA DISPATCHER (CORE)
# -------------------------
def run_qa_checks(trade=None, start_time=None, label=None):
    """
    Central QA dispatcher.
    Keeps QA layer fully modular and scalable.
    """

    try:
        if trade:
            trade_integrity_watcher(trade)

        if start_time and label:
            performance_watcher(start_time, label)

        system_health_watcher()

    except Exception as e:
        bug_watcher("run_qa_checks", e)


# =========================
# TRADE MANAGER ENGINE
# =========================

COMMAND_LOG = []
TRADINGVIEW_ATR_CACHE = {}

# =========================
# PHASE 9 — SELF-PROTECTION LAYER
# =========================

RISK_STATE = {
    "kill_switch_active": False,
    "kill_switch_reason": None,
    "daily_trade_count": 0,
    "daily_loss_count": 0,
    "max_daily_trades": 2,
    "max_daily_losses": 1,
    "kill_switch_drawdown_pct": 11.0,
    "current_drawdown_pct": 0.0,
    "trading_halted": False,
    "last_reset_date": datetime.now().date().isoformat()
}

# -------------------------
# FAILURE ESCALATION STATE
# -------------------------

FAILURE_STATE = {
    "execution_failure_count": 0,
    "qa_critical_count": 0,
    "max_execution_failures": 3,
    "max_qa_critical": 3,
    "last_failure_at": None,
    "halt_reason": None
}

NON_LATCHING_PAPER_TEST_ERROR_PREFIXES = (
    "no_live_fill_price_available_for_",
)


# -------------------------
# RISK STATE PERSISTENCE
# -------------------------

def load_risk_state_from_persistence():
    global RUNTIME_PAPER_RESET_AT
    state = load_state()
    RUNTIME_PAPER_RESET_AT = get_paper_reset_at(state)

    persisted_risk = state.get("risk_state")
    if persisted_risk:
        for key in RISK_STATE.keys():
            if key in persisted_risk:
                RISK_STATE[key] = persisted_risk[key]

    persisted_failure = state.get("failure_state")
    if persisted_failure:
        for key in FAILURE_STATE.keys():
            if key in persisted_failure:
                FAILURE_STATE[key] = persisted_failure[key]

    print(
        "STARTUP RISK STATE "
        f"kill_switch_active={RISK_STATE['kill_switch_active']} "
        f"kill_switch_reason={RISK_STATE['kill_switch_reason']} "
        f"daily_trade_count={RISK_STATE['daily_trade_count']} "
        f"daily_loss_count={RISK_STATE['daily_loss_count']} "
        f"last_reset_date={RISK_STATE['last_reset_date']}"
    )
    print(
        "STARTUP QA ESCALATION "
        f"qa_critical_count={FAILURE_STATE['qa_critical_count']} "
        f"execution_failure_count={FAILURE_STATE['execution_failure_count']} "
        f"halt_reason={FAILURE_STATE['halt_reason']}"
    )


def persist_risk_state():
    state = load_state()
    state["risk_state"] = serialize_trade(RISK_STATE)
    state["failure_state"] = serialize_trade(FAILURE_STATE)
    state["system"]["last_update_at"] = datetime.now().isoformat()
    save_state(state, reason="persist_risk_state")


def is_non_latching_paper_test_failure(reason):
    normalized_reason = str(reason or "")
    return any(
        prefix in normalized_reason
        for prefix in NON_LATCHING_PAPER_TEST_ERROR_PREFIXES
    )


def reset_qa_escalation_state(clear_failed_test_trades=False):
    state = load_state()

    RISK_STATE["kill_switch_active"] = False
    RISK_STATE["kill_switch_reason"] = None
    RISK_STATE["daily_trade_count"] = 0
    RISK_STATE["daily_loss_count"] = 0
    RISK_STATE["current_drawdown_pct"] = 0.0
    RISK_STATE["trading_halted"] = False
    RISK_STATE["last_reset_date"] = datetime.now().date().isoformat()

    FAILURE_STATE["execution_failure_count"] = 0
    FAILURE_STATE["qa_critical_count"] = 0
    FAILURE_STATE["last_failure_at"] = None
    FAILURE_STATE["halt_reason"] = None

    removed_trade_ids = []
    if clear_failed_test_trades:
        remaining_trades = {}
        for trade_id, trade in state.get("trades", {}).items():
            if (
                trade.get("status") == "error"
                and is_non_latching_paper_test_failure(trade.get("error_reason"))
            ):
                removed_trade_ids.append(trade_id)
                continue
            remaining_trades[trade_id] = trade
        state["trades"] = remaining_trades

    state["risk_state"] = serialize_trade(RISK_STATE)
    state["failure_state"] = serialize_trade(FAILURE_STATE)
    state["system"]["last_update_at"] = datetime.now().isoformat()
    save_state(state, reason="reset_qa_escalation_state")

    print(
        "STARTUP QA RESET "
        f"kill_switch_active={RISK_STATE['kill_switch_active']} "
        f"qa_critical_count={FAILURE_STATE['qa_critical_count']} "
        f"execution_failure_count={FAILURE_STATE['execution_failure_count']} "
        f"removed_failed_test_trades={removed_trade_ids}"
    )

    return {
        "kill_switch_active": RISK_STATE["kill_switch_active"],
        "qa_critical_count": FAILURE_STATE["qa_critical_count"],
        "execution_failure_count": FAILURE_STATE["execution_failure_count"],
        "removed_failed_test_trades": removed_trade_ids,
    }


def reset_daily_risk_state_if_needed():
    today = datetime.now().date().isoformat()
    if RISK_STATE["last_reset_date"] != today:
        RISK_STATE["daily_trade_count"] = 0
        RISK_STATE["daily_loss_count"] = 0
        RISK_STATE["trading_halted"] = False
        RISK_STATE["last_reset_date"] = today
        persist_risk_state()


def global_flatten_executor_exposure(reason):
    command = map_execution_command("flatten_all", {"reason": reason})
    COMMAND_LOG.append(command)
    print(f"kill_switch_global_flatten_started reason={reason}")

    try:
        response = requests.post(EXECUTOR_URL, json=command, timeout=2.0)
        response_data = response.json()
    except Exception as exc:
        print(f"kill_switch_global_flatten_failed error={exc}")
        return {"ok": False, "error": str(exc)}

    for symbol in response_data.get("flattened_symbols") or []:
        print(f"kill_switch_symbol_flattened symbol={symbol}")

    for order_id in response_data.get("cancelled_order_ids") or []:
        print(f"kill_switch_active_order_cancelled order_id={order_id}")

    print(
        "kill_switch_global_flatten_complete "
        f"ok={response_data.get('ok')} "
        f"flattened_symbols={response_data.get('flattened_symbols') or []} "
        f"cancelled_order_ids={response_data.get('cancelled_order_ids') or []}"
    )
    return response_data


def activate_kill_switch(reason):
    if RISK_STATE["kill_switch_active"] and RISK_STATE["kill_switch_reason"] == reason:
        global_flatten_executor_exposure(reason)
        return

    RISK_STATE["kill_switch_active"] = True
    RISK_STATE["kill_switch_reason"] = reason
    RISK_STATE["trading_halted"] = True
    FAILURE_STATE["halt_reason"] = reason
    persist_risk_state()
    print(f"[CRITICAL] [RISK] [None] Kill switch activated: {reason}")
    global_flatten_executor_exposure(reason)


def set_current_drawdown(drawdown_pct):
    RISK_STATE["current_drawdown_pct"] = float(drawdown_pct)
    persist_risk_state()
    if RISK_STATE["current_drawdown_pct"] >= RISK_STATE["kill_switch_drawdown_pct"]:
        activate_kill_switch(
            f"drawdown {RISK_STATE['current_drawdown_pct']:.2f}% >= {RISK_STATE['kill_switch_drawdown_pct']:.2f}%"
        )


def can_execute_trade(symbol=None):
    reset_daily_risk_state_if_needed()

    if RISK_STATE["kill_switch_active"]:
        return False, f"kill_switch_active: {RISK_STATE['kill_switch_reason']}"

    if RISK_STATE["trading_halted"] and not is_qa_stability_mode():
        return False, "trading_halted"

    if (
        not is_qa_stability_mode()
        and RISK_STATE["daily_trade_count"] >= RISK_STATE["max_daily_trades"]
    ):
        RISK_STATE["trading_halted"] = True
        return False, "max_daily_trades_reached"

    if (
        not is_qa_stability_mode()
        and RISK_STATE["daily_loss_count"] >= RISK_STATE["max_daily_losses"]
    ):
        RISK_STATE["trading_halted"] = True
        return False, "max_daily_losses_reached"

    if symbol:
        state = load_state()
        target_symbol = canonical_execution_symbol(symbol)
        for trade in state["trades"].values():
            trade_symbol = canonical_execution_symbol(
                trade.get("execution_symbol") or trade.get("symbol") or trade.get("requested_symbol")
            )
            if trade_symbol == target_symbol and trade.get("status") not in ["closed", "error"]:
                return False, f"active_trade_exists_for_symbol:{target_symbol}"

    return True, "allowed"


def canonical_execution_symbol(symbol):
    normalized = canonicalize_symbol_input(symbol)
    if not normalized:
        return normalized
    resolved_symbol, _ = resolve_execution_symbol(normalized)
    return str(resolved_symbol or normalized).upper()


def should_escalate_trade_rejection_to_qa_critical(reason):
    if not is_qa_stability_mode():
        return True

    daily_lockout_reasons = {
        "trading_halted",
        "max_daily_trades_reached",
        "max_daily_losses_reached",
    }
    return str(reason or "") not in daily_lockout_reasons


def reset_failure_state():
    FAILURE_STATE["execution_failure_count"] = 0
    FAILURE_STATE["qa_critical_count"] = 0
    FAILURE_STATE["last_failure_at"] = None
    FAILURE_STATE["halt_reason"] = None
    persist_risk_state()


def register_execution_failure(reason):
    if is_non_latching_paper_test_failure(reason):
        print(f"EXECUTION FAILURE NON-LATCHING reason={reason}")
        return

    FAILURE_STATE["execution_failure_count"] += 1
    FAILURE_STATE["last_failure_at"] = datetime.now().isoformat()
    persist_risk_state()

    if FAILURE_STATE["execution_failure_count"] >= FAILURE_STATE["max_execution_failures"]:
        activate_kill_switch(f"execution failure escalation: {reason}")


def register_qa_critical_failure(reason):
    FAILURE_STATE["qa_critical_count"] += 1
    FAILURE_STATE["last_failure_at"] = datetime.now().isoformat()
    persist_risk_state()

    if FAILURE_STATE["qa_critical_count"] >= FAILURE_STATE["max_qa_critical"]:
        activate_kill_switch(f"qa critical escalation: {reason}")


def register_new_trade():
    reset_daily_risk_state_if_needed()
    RISK_STATE["daily_trade_count"] += 1
    reset_failure_state()
    persist_risk_state()


def register_trade_loss():
    reset_daily_risk_state_if_needed()
    RISK_STATE["daily_loss_count"] += 1
    if not is_qa_stability_mode():
        RISK_STATE["trading_halted"] = True
    print(
        "RISK daily_loss_incremented "
        f"MODE={OPERATING_MODE} "
        f"daily_loss_count={RISK_STATE['daily_loss_count']}"
    )
    persist_risk_state()
    if is_qa_stability_mode():
        qa_event("RISK", "INFO", "Daily loss recorded; qa_stability mode kept trading enabled")
    else:
        qa_event("RISK", "WARNING", "Daily loss limit reached; trading halted")


def register_trade_breakeven():
    reset_daily_risk_state_if_needed()
    if (
        not is_qa_stability_mode()
        and RISK_STATE["daily_trade_count"] >= RISK_STATE["max_daily_trades"]
    ):
        RISK_STATE["trading_halted"] = True
        persist_risk_state()
        qa_event("RISK", "INFO", "Daily trade limit reached after breakeven; trading halted")

# =========================
# PHASE 5 QA LAYER
# =========================

PROCESSED_EVENTS = set()


def generate_event_id(trade_id, event_type, price):
    return f"{trade_id}:{event_type}:{price}"


def is_duplicate_event(event_id):
    if event_id in PROCESSED_EVENTS:
        print(f"QA: DUPLICATE EVENT BLOCKED -> {event_id}")
        return True
    PROCESSED_EVENTS.add(event_id)
    return False


def lock_trade(trade):
    if trade.get("locked"):
        print(f"QA: TRADE LOCKED -> {trade['trade_id']}")
        return False
    trade["locked"] = True
    return True


def unlock_trade(trade):
    trade["locked"] = False


def qa_log(trade, message):
    print(f"QA LOG [{trade['trade_id']}]: {message}")


# =========================
# PHASE 6 BROKER ADAPTER
# =========================

# Trade manager speaks in generic execution intents.
# Adapter layer translates those intents into broker/executor-specific commands.
# Current adapter target: local_executor


def map_execution_command(action, payload):
    if BROKER_NAME == "local_executor":
        command = {"action": action}
        command.update(payload)
        return command

    raise ValueError(f"Unsupported broker adapter: {BROKER_NAME}")


def dispatch_execution(action, payload, watch_failures=True):
    if not ensure_connection():
        failure = {"ok": False, "error": "connection_failed"}
        register_execution_failure("connection_failed")
        execution_watcher(failure, action)
        return failure

    command = map_execution_command(action, payload)
    COMMAND_LOG.append(command)
    print("EXECUTOR COMMAND:", command)

    try:
        response = requests.post(EXECUTOR_URL, json=command)
        response_data = response.json()

        if response_data.get("ok"):
            if FAILURE_STATE["execution_failure_count"] > 0:
                FAILURE_STATE["execution_failure_count"] = 0
                FAILURE_STATE["last_failure_at"] = None
                persist_risk_state()
        elif watch_failures:
            register_execution_failure(response_data.get("error", response_data.get("message", f"{action}_failed")))

        if watch_failures or response_data.get("ok"):
            execution_watcher(response_data, action)
        run_qa_checks(label=f"execution_{action}")
        return response_data
    except Exception as e:
        failure = {"ok": False, "error": str(e)}
        print("EXECUTOR ERROR:", e)
        register_execution_failure(str(e))
        bug_watcher("dispatch_execution", e)
        execution_watcher(failure, action)
        return failure


def protective_oco_group(trade):
    if isinstance(trade, dict) and trade.get("oco_group"):
        return trade.get("oco_group")
    trade_id = trade.get("trade_id") if isinstance(trade, dict) else trade
    return f"OCO-{trade_id}-PROTECTIVE" if trade_id else None


def place_stop_order(trade_id, symbol, stop_price, qty, watch_failures=True, oco_group=None, oco_role="protective_stop"):
    return dispatch_execution(
        "submit_stop",
        {
            "trade_id": trade_id,
            "symbol": symbol,
            "stop_price": stop_price,
            "qty": qty,
            "oco_group": oco_group or protective_oco_group(trade_id),
            "oco_role": oco_role,
        },
        watch_failures=watch_failures,
    )


def place_limit_order(trade_id, symbol, limit_price, qty, tag=None, oco_group=None, oco_role="tp1_limit"):
    payload = {
        "trade_id": trade_id,
        "symbol": symbol,
        "limit_price": round_to_nearest_tick(limit_price, symbol),
        "qty": qty,
        "oco_group": oco_group or protective_oco_group(trade_id),
        "oco_role": oco_role,
    }
    if tag:
        payload["tag"] = tag

    return dispatch_execution(
        "submit_limit",
        payload
    )


def price_is_valid_tick(value, symbol, tolerance=1e-9):
    try:
        price = float(value)
        tick_size = float(get_symbol_tick_size(symbol))
    except (TypeError, ValueError):
        return False
    if not math.isfinite(price) or not math.isfinite(tick_size) or tick_size <= 0:
        return False
    ticks = round(price / tick_size)
    return abs((ticks * tick_size) - price) <= tolerance


def find_executor_symbol_snapshot(executor_snapshot, symbol):
    if not isinstance(executor_snapshot, dict):
        return None, {}
    raw_symbol = str(symbol or "").strip().upper()
    if raw_symbol in executor_snapshot:
        return raw_symbol, executor_snapshot[raw_symbol] or {}
    raw_root = normalize_symbol_root(raw_symbol)
    for candidate, snapshot in executor_snapshot.items():
        if normalize_symbol_root(candidate) == raw_root:
            return candidate, snapshot or {}
    return raw_symbol, {}


def executor_order_oco_group(order):
    if not isinstance(order, dict):
        return None
    group = order.get("oco_group") or order.get("oco_group_id")
    return str(group).strip() if group else None


def executor_order_is_working(order):
    status = str((order or {}).get("status") or "").strip().lower()
    return status in {"active", "open", "working", "submitted", "accepted"}


def manual_exit_oco_link_confirmed(executor_orders, trade_id, symbol, oco_group):
    expected_group = protective_oco_group(trade_id)
    if not oco_group or oco_group != expected_group:
        return False
    symbol_root = normalize_symbol_root(symbol)
    for order in executor_orders or []:
        if order.get("trade_id") != trade_id:
            continue
        if order.get("type") != "stop":
            continue
        if not executor_order_is_working(order):
            continue
        if normalize_symbol_root(order.get("symbol")) != symbol_root:
            continue
        if executor_order_oco_group(order) == oco_group:
            return True
    return False


def set_manual_exit_limit_order(trade_id, symbol, limit_price, qty, *, replace_existing_tp=False, level_label=None, oco_group=None):
    payload = {
        "trade_id": trade_id,
        "symbol": symbol,
        "limit_price": limit_price,
        "qty": qty,
        "manual_confirmation": True,
        "intent": "manual_exit_limit",
        "replace_existing_tp": bool(replace_existing_tp),
        "oco_group": oco_group or protective_oco_group(trade_id),
    }
    if level_label:
        payload["level_label"] = level_label
    return dispatch_execution(
        "set_manual_exit_limit",
        payload,
        watch_failures=False,
    )


def cancel_existing_order(trade_id, symbol, broker_order_id, watch_failures=True):
    return dispatch_execution(
        "cancel_order",
        {
            "trade_id": trade_id,
            "symbol": symbol,
            "broker_order_id": broker_order_id
        },
        watch_failures=watch_failures,
    )


def modify_stop_order(trade_id, symbol, broker_order_id, stop_price, qty, tag=None, watch_failures=True, oco_group=None, oco_role=None):
    payload = {
        "trade_id": trade_id,
        "symbol": symbol,
        "broker_order_id": broker_order_id,
        "stop_price": stop_price,
        "qty": qty,
    }
    if tag:
        payload["tag"] = tag
    if oco_group is not None:
        payload["oco_group"] = oco_group
    if oco_role is not None:
        payload["oco_role"] = oco_role
    return dispatch_execution(
        "modify_stop",
        payload,
        watch_failures=watch_failures,
    )


def reset_stop_to_original(trade_id, symbol, stop_price, qty, watch_failures=True, oco_parent_group=None):
    return dispatch_execution(
        "reset_stop_to_original",
        {
            "trade_id": trade_id,
            "symbol": symbol,
            "stop_price": stop_price,
            "qty": qty,
            "oco_parent_group": oco_parent_group,
        },
        watch_failures=watch_failures,
    )


def flatten_trade_symbol(trade_id, symbol):
    return dispatch_execution(
        "flatten_symbol",
        {
            "trade_id": trade_id,
            "symbol": symbol
        }
    )


def normalize_tradingview_symbol(symbol):
    raw_symbol = canonicalize_symbol_input(symbol)
    if not raw_symbol:
        raise ValueError("Missing required field: symbol")
    return raw_symbol


def normalize_tradingview_direction(direction):
    normalized_direction = str(direction or "").strip().lower()
    direction_map = {
        "long": "long",
        "buy": "long",
        "b": "long",
        "short": "short",
        "sell": "short",
        "s": "short",
    }

    if normalized_direction not in direction_map:
        raise ValueError("Direction must be one of: long, short, buy, sell")

    return direction_map[normalized_direction]


def build_trade_packet_from_tradingview(payload):
    if not isinstance(payload, dict):
        raise ValueError("TradingView payload must be a JSON object")

    event = str(payload.get("event", "")).strip().lower()
    if event not in ("tv_enter_trade", "enter_trade"):
        raise ValueError("Invalid TradingView event; expected tv_enter_trade")

    try:
        position_size = float(payload["position_size"])
    except KeyError:
        raise ValueError("Missing required field: position_size")
    except (TypeError, ValueError):
        raise ValueError("position_size must be numeric")

    if position_size <= 0:
        raise ValueError("Position size must be greater than 0")

    if position_size.is_integer():
        position_size = int(position_size)

    return {
        "event": "enter_trade",
        "symbol": normalize_tradingview_symbol(payload.get("symbol")),
        "direction": normalize_tradingview_direction(payload.get("direction")),
        "position_size": position_size,
        "source": "tradingview",
        "raw_tradingview_event": event,
    }


def build_tradingview_atr_record(payload):
    if not isinstance(payload, dict):
        raise ValueError("TradingView ATR payload must be a JSON object")

    event = str(payload.get("event", "")).strip().lower()
    if event != "tv_atr_update":
        raise ValueError("Invalid TradingView ATR event; expected tv_atr_update")

    symbol = normalize_tradingview_symbol(payload.get("symbol"))

    try:
        atr_period = int(payload["atr_period"])
    except KeyError:
        raise ValueError("Missing required field: atr_period")
    except (TypeError, ValueError):
        raise ValueError("atr_period must be an integer")

    try:
        atr_value = float(payload["atr_value"])
    except KeyError:
        raise ValueError("Missing required field: atr_value")
    except (TypeError, ValueError):
        raise ValueError("atr_value must be numeric")

    timeframe = str(payload.get("timeframe", "")).strip()
    source = str(payload.get("source", "")).strip().lower()

    if atr_period <= 0:
        raise ValueError("atr_period must be greater than 0")
    if not math.isfinite(atr_value) or atr_value <= 0:
        raise ValueError("atr_value must be a positive finite number")
    if not timeframe:
        raise ValueError("Missing required field: timeframe")
    if source != "tradingview":
        raise ValueError("source must be tradingview")

    received_at = datetime.now().isoformat()
    return {
        "symbol": symbol,
        "atr_period": atr_period,
        "atr_value": atr_value,
        "timeframe": timeframe,
        "source": "tradingview",
        "received_at": received_at,
        "raw_event": event,
    }


def store_tradingview_atr(payload):
    atr_record = build_tradingview_atr_record(payload)
    state = load_state()
    state.setdefault("tradingview_atr", {})
    state["tradingview_atr"][atr_record["symbol"]] = atr_record
    state["system"]["last_update_at"] = datetime.now().isoformat()
    save_state(state, reason="store_tradingview_atr")

    TRADINGVIEW_ATR_CACHE[atr_record["symbol"]] = atr_record.copy()
    print(
        "TRADINGVIEW ATR stored "
        f"symbol={atr_record['symbol']} period={atr_record['atr_period']} "
        f"timeframe={atr_record['timeframe']} value={atr_record['atr_value']} "
        f"received_at={atr_record['received_at']}"
    )
    return atr_record


def get_tradingview_atr(symbol):
    normalized_symbol = normalize_tradingview_symbol(symbol)
    if normalized_symbol in TRADINGVIEW_ATR_CACHE:
        return TRADINGVIEW_ATR_CACHE[normalized_symbol].copy()

    state = load_state()
    atr_record = (state.get("tradingview_atr") or {}).get(normalized_symbol)
    if isinstance(atr_record, dict):
        TRADINGVIEW_ATR_CACHE[normalized_symbol] = atr_record.copy()
        return atr_record.copy()

    return None


def validate_trade_packet(packet):
    required_fields = [
        "event",
        "symbol",
        "direction",
        "position_size"
    ]

    for field in required_fields:
        if field not in packet:
            raise ValueError(f"Missing required field: {field}")

    if packet["event"] != "enter_trade":
        raise ValueError("Invalid event type")

    if packet["direction"] not in ["long", "short"]:
        raise ValueError("Direction must be 'long' or 'short'")

    if packet["position_size"] <= 0:
        raise ValueError("Position size must be greater than 0")

    return True


def create_trade_state(packet, atr_snapshot, requested_symbol, execution_symbol):
    normalized_symbol = str(execution_symbol).upper()
    normalized_atr_value = normalize_atr_value_for_symbol(
        normalized_symbol,
        atr_snapshot["atr_value"]
    )
    trade_id = f"T-{uuid.uuid4().hex[:8]}"

    return {
        "trade_id": trade_id,
        "symbol": normalized_symbol,
        "requested_symbol": str(requested_symbol).upper(),
        "direction": packet["direction"],
        "entry_price": None,
        "original_stop": None,
        "current_stop": None,
        "tp1_price": None,
        "be_trigger": None,
        "position_size": packet["position_size"],
        "remaining_size": packet["position_size"],
        "atr_value": normalized_atr_value,
        "atr_source": atr_snapshot["atr_source"],
        "atr_bar_timestamp": atr_snapshot["atr_bar_timestamp"],
        "atr_completed_bars": atr_snapshot.get("atr_completed_bars", []),
        "atr_recomputed_simple": atr_snapshot.get("atr_recomputed_simple"),
        "atr_abnormal_bar": atr_snapshot.get("atr_abnormal_bar"),
        "entry_leg_high": None,
        "entry_leg_low": None,
        "entry_leg_timestamp": None,
        "entry_leg_source": None,
        "execution_symbol": normalized_symbol,
        "fill_price_source": None,
        "status": "reserved",
        "tp1_hit": False,
        "tp1_filled_qty": None,
        "tp1_exit_price": None,
        "moved_to_be": False,
        "be_then_tp1_same_update": False,
        "stop_state": "original",
        "be_state_locked": False,
        "be_trigger_processed_at": None,
        "be_duplicate_trigger_suppressed_count": 0,
        "created_at": datetime.now().isoformat(),
        "last_price": None,
        "last_price_at": None,
        "be_hit_at": None,
        "tp1_hit_at": None,
        "exit_price": None,
        "exit_reason": None,
        "closed_at": None,
        "realized_pnl": None,
        "unrealized_pnl": 0.0,
        "total_pnl": 0.0,
        "tp1_profit": None,
        "runner_profit": None,
        "total_profit": None,
        "stop_order_id": None,
        "tp1_order_id": None,
        "oco_group": f"OCO-{trade_id}-PROTECTIVE",
        "error_reason": None,
        "recovery_status": None,
        "locked": False,
        "broker_adapter": BROKER_NAME
    }


def persist_trade_state(trade):
    record_trade_management_research_if_closed(trade)
    state = load_state()
    state["trades"][trade["trade_id"]] = serialize_trade(trade)
    state["system"]["last_update_at"] = datetime.now().isoformat()
    save_state(state, reason=f"persist_trade_state:{trade.get('trade_id')}:{trade.get('status')}")


def mark_reserved_trade_error(trade, reason):
    trade["status"] = "error"
    trade["error_reason"] = reason
    trade["recovery_status"] = "submit_failed_reservation_released"
    persist_trade_state(trade)
    return trade


def submit_trade(packet):
    validate_trade_packet(packet)
    submitted_symbol = str(packet["symbol"]).upper()
    execution_symbol, resolution_source = resolve_execution_symbol(submitted_symbol)
    print(
        f"SUBMIT FLOW submit_received symbol={submitted_symbol} "
        f"direction={packet['direction']} qty={packet['position_size']} "
        f"MODE={OPERATING_MODE}"
    )
    print(f"SUBMIT FLOW submit_symbol_received symbol={submitted_symbol}")
    print(
        f"SUBMIT FLOW submit_symbol_resolved submitted={submitted_symbol} "
        f"resolved={execution_symbol} source={resolution_source}"
    )

    with SUBMIT_TRADE_LOCK:
        allowed, reason = can_execute_trade(symbol=execution_symbol)
        if not allowed:
            if should_escalate_trade_rejection_to_qa_critical(reason):
                qa_event("RISK", "CRITICAL", f"Trade rejected before execution: {reason}")
            else:
                qa_event("RISK", "INFO", f"Trade rejected before execution: {reason}")
            raise ValueError(f"Trade blocked: {reason}")

        atr_snapshot = fetch_trade_entry_atr_snapshot(execution_symbol)
        trade = create_trade_state(
            packet,
            atr_snapshot,
            requested_symbol=submitted_symbol,
            execution_symbol=execution_symbol,
        )
        persist_trade_state(trade)

    log_trade_event(
        trade["trade_id"],
        "submit_accepted",
        "Trade accepted by manager before executor entry",
        {
            "requested_symbol": submitted_symbol,
            "execution_symbol": execution_symbol,
            "direction": trade["direction"],
            "position_size": trade["position_size"],
            "atr_value": trade["atr_value"],
            "atr_bar_timestamp": trade["atr_bar_timestamp"],
        },
        snapshot=trade,
    )

    print(
        f"SUBMIT FLOW atr_snapshot_used requested_symbol={submitted_symbol} "
        f"lookup_symbol={execution_symbol} symbol={trade['symbol']} "
        f"atr_source={trade['atr_source']} "
        f"atr_value={trade['atr_value']} "
        f"bar_timestamp={trade['atr_bar_timestamp']}"
    )

    entry_response = place_entry_order(
        trade_id=trade["trade_id"],
        symbol=trade["symbol"],
        direction=trade["direction"],
        qty=trade["position_size"]
    )

    if not entry_response.get("ok"):
        return mark_reserved_trade_error(
            trade,
            entry_response.get("error") or entry_response.get("message") or "Initial entry placement failed",
        )

    fill_price = entry_response.get("fill_price")
    if fill_price is None:
        fill_price = ((entry_response.get("order") or {}).get("filled_price"))

    if fill_price is None:
        return mark_reserved_trade_error(trade, "Entry fill price missing from executor response")

    fill_price = float(fill_price)
    fill_price_source = entry_response.get("fill_price_source", "executor_actual_fill")
    print(
        f"SUBMIT FLOW executor_fill_received trade_id={trade['trade_id']} "
        f"symbol={trade['symbol']} source={fill_price_source}"
    )
    print(
        f"SUBMIT FLOW actual_fill_price trade_id={trade['trade_id']} "
        f"symbol={trade['symbol']} price={fill_price}"
    )

    derived_levels = derive_trade_levels(
        fill_price=fill_price,
        symbol=trade["symbol"],
        direction=trade["direction"],
        atr_value=trade["atr_value"]
    )
    validate_derived_levels(trade["direction"], derived_levels)
    trade.update(derived_levels)
    trade["fill_price_source"] = fill_price_source
    capture_entry_leg_extremes(trade, packet, entry_response, atr_snapshot)
    log_trade_event(
        trade["trade_id"],
        "entry_filled",
        "Executor entry filled",
        {
            "entry_price": trade["entry_price"],
            "fill_price_source": fill_price_source,
            "executor_order_id": entry_response.get("broker_order_id"),
        },
        snapshot=trade,
    )
    print(
        f"SUBMIT FLOW derived_levels_computed trade_id={trade['trade_id']} "
        f"entry={trade['entry_price']} stop={trade['original_stop']} "
        f"be_trigger={trade['be_trigger']} tp1={trade['tp1_price']}"
    )
    print(
        "ATR DISTANCES "
        f"trade_id={trade['trade_id']} raw_atr={trade['atr_value']} "
        f"stop_distance={calculate_atr_distance(trade['atr_value'])} "
        f"tp1_distance={calculate_atr_distance(trade['atr_value'])} "
        f"be_distance={calculate_atr_distance(trade['atr_value'], 0.5)} "
        f"source={trade['atr_source']}"
    )

    stop_response = place_stop_order(
        trade_id=trade["trade_id"],
        symbol=trade["symbol"],
        stop_price=trade["original_stop"],
        qty=trade["position_size"],
        watch_failures=False,
    )

    if stop_response.get("ok"):
        trade["stop_order_id"] = stop_response.get("broker_order_id")
        log_trade_event(
            trade["trade_id"],
            "original_stop_placed",
            "Original protective stop placed",
            {
                "stop_order_id": trade["stop_order_id"],
                "original_stop": trade["original_stop"],
                "qty": trade["position_size"],
            },
            snapshot=trade,
        )
    else:
        matching_stop = None
        if response_is_active_stop_exists(stop_response):
            matching_stop = find_matching_active_stop(
                fetch_executor_orders(),
                trade["trade_id"],
                trade["symbol"],
                trade["original_stop"],
                trade["position_size"],
            )

        if matching_stop:
            trade["stop_order_id"] = matching_stop.get("order_id")
            log_trade_event(
                trade["trade_id"],
                "original_stop_duplicate_noop",
                "Original protective stop already active; duplicate placement ignored",
                {
                    "stop_order_id": trade["stop_order_id"],
                    "original_stop": trade["original_stop"],
                    "qty": trade["position_size"],
                },
                snapshot=trade,
            )
        else:
            register_execution_failure(stop_response.get("error", stop_response.get("message", "submit_stop_failed")))
            execution_watcher(stop_response, "submit_stop")
            trade["status"] = "error"
            trade["error_reason"] = "Initial stop placement failed"

    if trade["status"] != "error":
        tp1_qty = float(trade["position_size"]) / 2
        tp1_response = place_limit_order(
            trade_id=trade["trade_id"],
            symbol=trade["symbol"],
            limit_price=trade["tp1_price"],
            qty=tp1_qty,
            tag="tp1",
        )

        if tp1_response.get("ok"):
            trade["tp1_order_id"] = tp1_response.get("broker_order_id")
            log_trade_event(
                trade["trade_id"],
                "tp1_order_active",
                "TP1 limit order created and active before target touch",
                {
                    "tp1_order_id": trade["tp1_order_id"],
                    "tp1_price": trade["tp1_price"],
                    "qty": tp1_qty,
                },
                snapshot=trade,
            )
        else:
            trade["status"] = "error"
            trade["error_reason"] = tp1_response.get("error") or tp1_response.get("message") or "TP1 limit placement failed"

    if trade["status"] != "error":
        trade["status"] = "active"
        register_new_trade()

    update_pnl_totals(trade)
    persist_trade_state(trade)
    log_trade_event(
        trade["trade_id"],
        "final_trade_persistence_snapshot",
        "Trade persisted after submit flow",
        snapshot=trade,
    )
    return trade


def process_price_update(trade, price, timestamp):
    start_time = datetime.now()
    timestamp = normalize_timestamp(timestamp)
    event_id = generate_event_id(trade["trade_id"], "price_update", price)

    if is_duplicate_event(event_id):
        trade["last_price"] = price
        trade["last_price_at"] = timestamp
        update_pnl_totals(trade, current_price=price)
        update_post_be_analytics(trade, price, timestamp)
        return trade

    if not lock_trade(trade):
        return trade

    try:
        backfill_be_lock_fields(trade)
        trade["last_price"] = price
        trade["last_price_at"] = timestamp
        update_pnl_totals(trade, current_price=price)
        update_post_be_analytics(trade, price, timestamp)
        update_stop_state_from_active_stop(trade)

        if trade["status"] in ["closed", "error"]:
            run_qa_checks(trade=trade, start_time=start_time, label="process_price_update")
            return trade

        be_triggered = False
        tp1_triggered = False
        log_trade_event(
            trade["trade_id"],
            "price_update_received",
            "Price update accepted for lifecycle checks",
            {"price": price},
            snapshot=trade,
            timestamp=timestamp,
        )

        if trade["direction"] == "long" and price <= trade["current_stop"]:
            log_trade_event(
                trade["trade_id"],
                "stop_fill_check",
                "Long stop check matched",
                {"price": price, "current_stop": trade["current_stop"]},
                snapshot=trade,
                timestamp=timestamp,
            )
            handle_stop_hit(trade, timestamp)
            run_qa_checks(trade=trade, start_time=start_time, label="process_price_update")
            return trade

        if trade["direction"] == "short" and price >= trade["current_stop"]:
            log_trade_event(
                trade["trade_id"],
                "stop_fill_check",
                "Short stop check matched",
                {"price": price, "current_stop": trade["current_stop"]},
                snapshot=trade,
                timestamp=timestamp,
            )
            handle_stop_hit(trade, timestamp)
            run_qa_checks(trade=trade, start_time=start_time, label="process_price_update")
            return trade

        if be_trigger_crossed(trade, price):
            if is_be_state_locked(trade):
                suppress_duplicate_be_trigger(trade, timestamp)
            elif trade["direction"] == "long":
                log_trade_event(
                    trade["trade_id"],
                    "be_trigger_hit",
                    "Long BE trigger matched",
                    {"price": price, "be_trigger": trade["be_trigger"]},
                    snapshot=trade,
                    timestamp=timestamp,
                )
                handle_be_trigger(trade, timestamp)
                update_post_be_analytics(trade, price, timestamp)
                be_triggered = True
            elif trade["direction"] == "short":
                log_trade_event(
                    trade["trade_id"],
                    "be_trigger_hit",
                    "Short BE trigger matched",
                    {"price": price, "be_trigger": trade["be_trigger"]},
                    snapshot=trade,
                    timestamp=timestamp,
                )
                handle_be_trigger(trade, timestamp)
                update_post_be_analytics(trade, price, timestamp)
                be_triggered = True

        if not trade["tp1_hit"]:
            log_trade_event(
                trade["trade_id"],
                "tp1_fill_check",
                "TP1 price comparison evaluated",
                {
                    "price": price,
                    "tp1_price": trade["tp1_price"],
                    "direction": trade["direction"],
                    "tp1_order_id": trade.get("tp1_order_id"),
                },
                snapshot=trade,
                timestamp=timestamp,
            )
            if trade["direction"] == "long" and price >= trade["tp1_price"]:
                handle_tp1_hit(trade, timestamp)
                tp1_triggered = True
            elif trade["direction"] == "short" and price <= trade["tp1_price"]:
                handle_tp1_hit(trade, timestamp)
                tp1_triggered = True

        if be_triggered and tp1_triggered:
            trade["be_then_tp1_same_update"] = True

        run_qa_checks(trade=trade, start_time=start_time, label="process_price_update")
        return trade

    finally:
        unlock_trade(trade)


def trade_created_before_timestamp(trade, timestamp):
    created_at = trade.get("created_at")
    if not created_at or not timestamp:
        return True
    try:
        return as_los_angeles_time(created_at) <= as_los_angeles_time(timestamp)
    except Exception:
        return True


def be_probe_price_from_bar(trade, bar):
    if not isinstance(bar, dict) or is_be_state_locked(trade):
        return None
    if trade.get("be_trigger") is None:
        return None
    try:
        if trade.get("direction") == "short" and bar.get("low") is not None:
            low = float(bar.get("low"))
            return low if be_trigger_crossed(trade, low) else None
        if trade.get("direction") == "long" and bar.get("high") is not None:
            high = float(bar.get("high"))
            return high if be_trigger_crossed(trade, high) else None
    except (TypeError, ValueError):
        return None
    return None


def process_be_probe_update(trade, price, timestamp):
    if price is None or is_be_state_locked(trade) or not be_trigger_crossed(trade, price):
        return trade
    if not lock_trade(trade):
        return trade
    try:
        backfill_be_lock_fields(trade)
        if is_be_state_locked(trade):
            suppress_duplicate_be_trigger(trade, timestamp)
            return trade
        log_trade_event(
            trade["trade_id"],
            "be_trigger_hit",
            "BE trigger matched from live bar extreme",
            {"price": price, "be_trigger": trade["be_trigger"], "source": "bar_extreme"},
            snapshot=trade,
            timestamp=timestamp,
        )
        handle_be_trigger(trade, timestamp)
        update_post_be_analytics(trade, price, timestamp)
        return trade
    finally:
        unlock_trade(trade)


def on_price(symbol, price, timestamp=None, bar=None):
    run_noon_runner_flatten_if_due()
    state = load_state()
    timestamp = normalize_timestamp(timestamp) or datetime.now().isoformat()
    resolved_symbol, resolution_source = resolve_execution_symbol(symbol)
    print(
        f"ON_PRICE RECEIVED: symbol={symbol} resolved_symbol={resolved_symbol} "
        f"source={resolution_source} price={price}"
    )

    for trade_id, trade in state["trades"].items():
        trade_candidates = build_symbol_candidates(
            trade.get("execution_symbol") or trade.get("symbol") or trade.get("requested_symbol")
        )
        if resolved_symbol in trade_candidates and trade.get("status") == "active":
            if not trade_created_before_timestamp(trade, timestamp):
                log_trade_event(
                    trade_id,
                    "price_update_ignored_before_trade_creation",
                    "Price update timestamp precedes trade creation",
                    {"price": price, "price_timestamp": timestamp, "created_at": trade.get("created_at")},
                    snapshot=trade,
                    timestamp=timestamp,
                )
                continue
            if trade.get("locked"):
                print(f"STALE LOCK CLEARED: {trade_id}")
                trade["locked"] = False

            print(
                f"MATCHED TRADE: {trade_id} symbol={trade.get('symbol')} "
                f"requested_symbol={trade.get('requested_symbol')} status={trade.get('status')}"
            )
            updated_trade = process_price_update(
                trade,
                price,
                timestamp
            )
            if updated_trade.get("status") == "active":
                be_probe_price = be_probe_price_from_bar(updated_trade, bar)
                if be_probe_price is not None:
                    updated_trade = process_be_probe_update(updated_trade, be_probe_price, timestamp)

            print(
                f"UPDATED TRADE: trade_id={trade_id} "
                f"last_price={updated_trade.get('last_price')} "
                f"tp1_hit={updated_trade.get('tp1_hit')} "
                f"remaining_size={updated_trade.get('remaining_size')} "
                f"locked={updated_trade.get('locked')}"
            )

            state["trades"][trade_id] = serialize_trade(updated_trade)

    save_state(state, reason=f"on_price:{resolved_symbol}")

@app.route("/submit_trade", methods=["POST"])
def submit_trade_route():
    try:
        packet = request.get_json(force=True)
        result = submit_trade(packet)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/webhook/tradingview", methods=["POST"])
@app.route("/tv/webhook", methods=["POST"])
def tradingview_webhook_route():
    try:
        payload = request.get_json(force=True)
        print(f"TRADINGVIEW WEBHOOK raw_payload={payload}")
        packet = build_trade_packet_from_tradingview(payload)
        print(
            "TRADINGVIEW WEBHOOK normalized_packet "
            f"symbol={packet['symbol']} direction={packet['direction']} "
            f"position_size={packet['position_size']}"
        )
        trade = submit_trade(packet)
        status_code = 200 if trade.get("status") != "error" else 502
        return jsonify({
            "ok": trade.get("status") != "error",
            "source": "tradingview",
            "trade": public_trade_dict(trade),
            "trade_id": trade.get("trade_id"),
            "status": trade.get("status"),
            "error": trade.get("error_reason"),
        }), status_code
    except ValueError as e:
        print(f"TRADINGVIEW WEBHOOK rejected error={e}")
        return jsonify({"ok": False, "source": "tradingview", "error": str(e)}), 400
    except Exception as e:
        print(f"TRADINGVIEW WEBHOOK failed error={e}")
        return jsonify({"ok": False, "source": "tradingview", "error": str(e)}), 500


@app.route("/webhook/tv-context", methods=["POST"])
def tradingview_context_proxy_route():
    """Forward TradingView level/context payloads to EntryAgent; not price truth."""
    try:
        payload = request.get_json(force=True)
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")

        response = requests.post(ENTRY_AGENT_TV_CONTEXT_URL, json=payload, timeout=1.0)
        try:
            response_payload = response.json()
        except ValueError:
            response_payload = {"raw_response": response.text}

        ok = 200 <= response.status_code < 300
        TV_CONTEXT_PROXY_STATE.update({
            "last_forwarded_at": datetime.now(timezone.utc).isoformat(),
            "last_status_code": response.status_code,
            "last_ok": ok,
            "last_error": None if ok else response_payload,
            "last_symbol": payload.get("symbol"),
            "target_url": ENTRY_AGENT_TV_CONTEXT_URL,
        })
        print(
            "TV CONTEXT PROXY "
            f"symbol={payload.get('symbol')} status={response.status_code} "
            f"target={ENTRY_AGENT_TV_CONTEXT_URL}"
        )
        return jsonify({
            "ok": ok,
            "source": "tradingview_level_context_proxy",
            "price_truth": "Rithmic",
            "target_url": ENTRY_AGENT_TV_CONTEXT_URL,
            "entry_agent_status_code": response.status_code,
            "entry_agent_response": response_payload,
        }), response.status_code
    except ValueError as e:
        TV_CONTEXT_PROXY_STATE.update({
            "last_forwarded_at": datetime.now(timezone.utc).isoformat(),
            "last_status_code": None,
            "last_ok": False,
            "last_error": str(e),
            "target_url": ENTRY_AGENT_TV_CONTEXT_URL,
        })
        return jsonify({"ok": False, "source": "tradingview_level_context_proxy", "error": str(e)}), 400
    except requests.RequestException as e:
        TV_CONTEXT_PROXY_STATE.update({
            "last_forwarded_at": datetime.now(timezone.utc).isoformat(),
            "last_status_code": None,
            "last_ok": False,
            "last_error": str(e),
            "last_symbol": (payload or {}).get("symbol") if isinstance(locals().get("payload"), dict) else None,
            "target_url": ENTRY_AGENT_TV_CONTEXT_URL,
        })
        print(f"TV CONTEXT PROXY failed target={ENTRY_AGENT_TV_CONTEXT_URL} error={e}")
        return jsonify({
            "ok": False,
            "source": "tradingview_level_context_proxy",
            "price_truth": "Rithmic",
            "target_url": ENTRY_AGENT_TV_CONTEXT_URL,
            "error": str(e),
        }), 502


@app.route("/debug/tv-context-proxy", methods=["GET"])
def debug_tv_context_proxy_route():
    return jsonify({
        "ok": True,
        "source": "tradingview_level_context_proxy",
        "price_truth": "Rithmic",
        "state": TV_CONTEXT_PROXY_STATE,
    })


@app.route("/webhook/tradingview/atr", methods=["POST"])
def tradingview_atr_webhook_route():
    try:
        payload = request.get_json(force=True)
        print(f"TRADINGVIEW ATR raw_payload={payload}")
        atr_record = store_tradingview_atr(payload)
        return jsonify({
            "ok": True,
            "source": "tradingview",
            "atr": atr_record,
        })
    except ValueError as e:
        print(f"TRADINGVIEW ATR rejected error={e}")
        return jsonify({"ok": False, "source": "tradingview", "error": str(e)}), 400
    except Exception as e:
        print(f"TRADINGVIEW ATR failed error={e}")
        return jsonify({"ok": False, "source": "tradingview", "error": str(e)}), 500


@app.route("/debug/tradingview/atr/<symbol>", methods=["GET"])
def get_tradingview_atr_route(symbol):
    try:
        atr_record = get_tradingview_atr(symbol)
        if atr_record is None:
            return jsonify({
                "ok": False,
                "source": "tradingview",
                "symbol": normalize_tradingview_symbol(symbol),
                "error": "ATR_NOT_FOUND",
            }), 404

        return jsonify({
            "ok": True,
            "source": "tradingview",
            "atr": atr_record,
        })
    except ValueError as e:
        return jsonify({"ok": False, "source": "tradingview", "error": str(e)}), 400


@app.route("/debug/tradingview/atr_status", methods=["GET"])
def get_tradingview_atr_status_route():
    return jsonify(build_tradingview_atr_status_payload())


def load_atr_shadow_comparison_payload():
    try:
        if not os.path.exists(RITHMIC_ATR_SHADOW_COMPARISON_FILE):
            return {"updated_at": None, "symbols": {}}
        with open(RITHMIC_ATR_SHADOW_COMPARISON_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            return {"updated_at": None, "symbols": {}}
        payload.setdefault("symbols", {})
        if not isinstance(payload["symbols"], dict):
            payload["symbols"] = {}
        return payload
    except Exception as exc:
        return {"updated_at": None, "symbols": {}, "error": str(exc)}


@app.route("/debug/atr_shadow", methods=["GET"])
def get_atr_shadow_route():
    payload = load_atr_shadow_comparison_payload()
    return jsonify({
        "ok": "error" not in payload,
        "source": "rithmic_worker_atr_shadow",
        "updated_at": payload.get("updated_at"),
        "symbols": payload.get("symbols", {}),
        "error": payload.get("error"),
    })


@app.route("/debug/atr_shadow/<symbol>", methods=["GET"])
def get_atr_shadow_symbol_route(symbol):
    payload = load_atr_shadow_comparison_payload()
    normalized_symbol = canonicalize_symbol_input(symbol) or str(symbol or "").strip().upper()
    root_symbol = normalize_symbol_root(normalized_symbol)
    symbols = payload.get("symbols", {})
    record = None
    for candidate in (normalized_symbol, root_symbol, str(symbol or "").strip().upper()):
        if candidate and candidate in symbols:
            record = symbols[candidate]
            break

    if record is None:
        return jsonify({
            "ok": False,
            "source": "rithmic_worker_atr_shadow",
            "symbol": normalized_symbol,
            "error": payload.get("error") or "ATR_SHADOW_NOT_FOUND",
        }), 404

    return jsonify({
        "ok": True,
        "source": "rithmic_worker_atr_shadow",
        "symbol": normalized_symbol,
        "atr_shadow": record,
    })


@app.route("/debug/noon_runner_flatten", methods=["GET"])
def debug_noon_runner_flatten_route():
    return jsonify(build_noon_runner_flatten_status_payload())


@app.route("/price", methods=["POST"])
def receive_price():
    try:
        data = request.get_json(force=True)

        symbol = str(data.get("symbol", "")).upper()
        price = float(data.get("price"))
        timestamp = data.get("tick_timestamp_utc") or data.get("timestamp")
        bar = data.get("current_1m_bar") if isinstance(data, dict) else None

        on_price(symbol, price, timestamp=timestamp, bar=bar)

        return jsonify({"ok": True, "symbol": symbol, "price": price})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/trades/<trade_id>/manual_exit_limit", methods=["POST"])
def manual_exit_limit_route(trade_id):
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "invalid_payload", "message": "invalid_payload"}), 400

    if data.get("manual_confirmation") is not True:
        return jsonify({
            "ok": False,
            "error": "manual_confirmation_required",
            "message": "manual_confirmation_required",
        }), 400
    if data.get("intent") != "manual_exit_limit":
        return jsonify({"ok": False, "error": "invalid_intent", "message": "invalid_intent"}), 400

    state = load_state()
    trade = (state.get("trades") or {}).get(trade_id)
    if not trade:
        return jsonify({"ok": False, "error": "trade_not_found", "message": "trade_not_found"}), 404
    if str(trade.get("status") or "").lower() != "active":
        return jsonify({"ok": False, "error": "trade_not_active", "message": "trade_not_active"}), 409

    requested_symbol = str(data.get("symbol") or "").strip().upper()
    trade_symbol = str(trade.get("symbol") or "").strip().upper()
    if not requested_symbol:
        return jsonify({"ok": False, "error": "missing_symbol", "message": "missing_symbol"}), 400
    if normalize_symbol_root(requested_symbol) != normalize_symbol_root(trade_symbol):
        return jsonify({"ok": False, "error": "symbol_mismatch", "message": "symbol_mismatch"}), 409

    try:
        quantity = float(data.get("quantity"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid_quantity", "message": "invalid_quantity"}), 400
    if not math.isfinite(quantity) or quantity <= 0:
        return jsonify({"ok": False, "error": "quantity_must_be_positive", "message": "quantity_must_be_positive"}), 400

    try:
        limit_price = float(data.get("price"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid_price", "message": "invalid_price"}), 400
    if not math.isfinite(limit_price):
        return jsonify({"ok": False, "error": "invalid_price", "message": "invalid_price"}), 400
    if not price_is_valid_tick(limit_price, trade_symbol):
        return jsonify({
            "ok": False,
            "error": "invalid_tick_increment",
            "message": "invalid_tick_increment",
        }), 400

    executor_snapshot = fetch_executor_snapshot()
    executor_symbol, symbol_snapshot = find_executor_symbol_snapshot(executor_snapshot, trade_symbol)
    position_qty = float((symbol_snapshot or {}).get("position_qty", 0) or 0)
    if position_qty == 0:
        return jsonify({"ok": False, "error": "position_flat_or_missing", "message": "position_flat_or_missing"}), 409
    if quantity > abs(position_qty):
        return jsonify({
            "ok": False,
            "error": "manual_exit_qty_exceeds_position",
            "message": "manual_exit_qty_exceeds_position",
        }), 409

    current_price = (symbol_snapshot or {}).get("last_price")
    try:
        current_price = float(current_price)
    except (TypeError, ValueError):
        current_price = None
    if current_price is None or not math.isfinite(current_price):
        return jsonify({"ok": False, "error": "current_price_unavailable", "message": "current_price_unavailable"}), 409
    if position_qty > 0 and limit_price <= current_price:
        return jsonify({
            "ok": False,
            "error": "invalid_exit_limit_direction",
            "message": "long_exit_limit_must_be_above_current_price",
        }), 409
    if position_qty < 0 and limit_price >= current_price:
        return jsonify({
            "ok": False,
            "error": "invalid_exit_limit_direction",
            "message": "short_exit_limit_must_be_below_current_price",
        }), 409

    oco_group = trade.get("oco_group") or protective_oco_group(trade)
    if not manual_exit_oco_link_confirmed(fetch_executor_orders(), trade_id, executor_symbol or trade_symbol, oco_group):
        return jsonify({
            "ok": False,
            "error": "oco_linkage_not_confirmed",
            "message": "oco_linkage_not_confirmed",
        }), 409

    level_label = str(data.get("level_label") or "").strip()
    response = set_manual_exit_limit_order(
        trade_id=trade_id,
        symbol=executor_symbol or trade_symbol,
        limit_price=limit_price,
        qty=quantity,
        replace_existing_tp=data.get("replace_existing_tp") is True,
        level_label=level_label or None,
        oco_group=oco_group,
    )
    if response.get("ok"):
        trade["manual_exit_order_id"] = response.get("broker_order_id")
        trade["manual_exit_price"] = limit_price
        trade["manual_exit_qty"] = quantity
        trade["manual_exit_level_label"] = level_label or None
        trade["manual_exit_set_at"] = datetime.now().isoformat()
        trade["manual_exit_replace_existing_tp"] = data.get("replace_existing_tp") is True
        trade["manual_exit_oco_group"] = oco_group
        if data.get("replace_existing_tp") is True:
            trade["tp1_order_id"] = response.get("broker_order_id") or trade.get("tp1_order_id")
            trade["tp1_price"] = limit_price
        state["trades"][trade_id] = trade
        save_state(state, reason="manual_exit_limit_set")
    status_code = 200 if response.get("ok") else 409
    return jsonify({
        "ok": bool(response.get("ok")),
        "message": response.get("message"),
        "trade_id": trade_id,
        "symbol": executor_symbol or trade_symbol,
        "broker_order_id": response.get("broker_order_id"),
        "order": response.get("order"),
        "executor_response": response,
    }), status_code


@app.route("/trades", methods=["GET"])
def get_trades():
    state = refresh_trades_from_executor_activity()
    return jsonify({
        "ok": True,
        "orphan_exposure": state.get("orphan_exposure") or {
            "has_orphans": False,
            "has_manager_state_issue": False,
            "severity": "none",
            "message": None,
            "items": [],
            "manager_state_issues": [],
        },
        "trades": {
            trade_id: public_trade_dict(trade)
            for trade_id, trade in state.get("trades", {}).items()
        }
    })


@app.route("/trade_screenshots/<path:filename>", methods=["GET"])
def get_trade_screenshot(filename):
    return send_from_directory(TRADE_SCREENSHOT_DIR, filename)


@app.route("/trades/<trade_id>/screenshot", methods=["POST"])
def attach_trade_screenshot(trade_id):
    print(
        "KPI SCREENSHOT upload_received "
        f"trade_id={trade_id} files={list(request.files.keys())}"
    )
    uploaded = request.files.get("screenshot") or request.files.get("file")
    if not uploaded or not uploaded.filename:
        print(f"KPI SCREENSHOT missing_file trade_id={trade_id}")
        return jsonify({"ok": False, "error": "missing_screenshot"}), 400

    content_type = str(uploaded.content_type or "").lower()
    if content_type and not content_type.startswith("image/"):
        print(f"KPI SCREENSHOT invalid_file_type trade_id={trade_id} content_type={uploaded.content_type}")
        return jsonify({"ok": False, "error": "invalid_file_type"}), 400

    state = load_state()
    trade = state.get("trades", {}).get(trade_id)
    if not trade:
        print(f"KPI SCREENSHOT trade_not_found trade_id={trade_id}")
        return jsonify({"ok": False, "error": "trade_not_found"}), 404

    os.makedirs(TRADE_SCREENSHOT_DIR, exist_ok=True)
    filename = safe_screenshot_filename(trade_id, uploaded.filename)
    target_path = os.path.join(TRADE_SCREENSHOT_DIR, filename)
    uploaded.save(target_path)
    file_written = os.path.exists(target_path)

    screenshot = {
        "filename": filename,
        "original_filename": uploaded.filename,
        "path": target_path,
        "url": trade_screenshot_url(filename),
        "content_type": uploaded.content_type,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    trade["screenshot"] = screenshot
    trade["screenshot_filename"] = filename
    trade["screenshot_path"] = target_path
    trade["screenshot_url"] = screenshot["url"]
    trade["screenshot_uploaded_at"] = screenshot["uploaded_at"]
    state["trades"][trade_id] = serialize_trade(trade)
    save_state(state, reason=f"attach_trade_screenshot:{trade_id}")
    print(
        "KPI SCREENSHOT saved "
        f"trade_id={trade_id} path={target_path} file_written={file_written} url={screenshot['url']}"
    )

    return jsonify({
        "ok": True,
        "trade_id": trade_id,
        "screenshot": screenshot,
        "file_written": file_written,
        "trade": public_trade_dict(trade),
    })


@app.route("/events", methods=["GET"])
def get_events():
    state = load_state()
    trade_id = request.args.get("trade_id")
    events = state.get("event_log", [])
    if trade_id:
        events = [event for event in events if event.get("trade_id") == trade_id]
    return jsonify({
        "ok": True,
        "events": events,
    })


@app.route("/debug/version", methods=["GET"])
def debug_version():
    try:
        file_mtime = datetime.fromtimestamp(os.path.getmtime(__file__), timezone.utc).isoformat()
    except OSError:
        file_mtime = None
    return jsonify({
        "ok": True,
        "process_started_at": TRADE_MANAGER_PROCESS_STARTED_AT,
        "file_path": os.path.abspath(__file__),
        "trade_manager_py_mtime": file_mtime,
        "patch_marker": RUNNER_ENTRY_PROTECTION_PATCH_MARKER,
    })


@app.route("/replay/<trade_id>", methods=["GET"])
def replay_trade(trade_id):
    state = refresh_trades_from_executor_activity()
    trade = state.get("trades", {}).get(trade_id)
    events = [event for event in state.get("event_log", []) if event.get("trade_id") == trade_id]
    reconstructed_events = reconstruct_trade_replay(trade)
    return jsonify({
        "ok": trade is not None,
        "trade": public_trade_dict(trade) if trade else None,
        "events": events,
        "reconstructed_events": reconstructed_events,
        "audit": audit_trade_lifecycle(trade) if trade else None,
        "final_trade_persistence_snapshot": public_trade_dict(trade) if trade else None,
    })


@app.route("/debug/atr/<symbol>", methods=["GET"])
def debug_atr(symbol):
    payload = load_rithmic_atr_snapshot_store_raw()
    snapshot = find_rithmic_symbol_snapshot(payload, symbol)
    if not isinstance(snapshot, dict):
        return jsonify({"ok": False, "error": "ATR_NOT_READY"}), 404

    atr_bar_timestamp = snapshot.get("atr_bar_timestamp")
    completed_bars = get_atr_completed_bars(symbol, atr_bar_timestamp)
    recomputed_atr = compute_simple_atr_from_completed_bars(completed_bars)
    abnormal_bar = find_abnormal_atr_bar(completed_bars)
    return jsonify({
        "ok": True,
        "symbol": str(symbol).upper(),
        "atr_value": float(snapshot.get("atr_value")),
        "atr_bar_timestamp": atr_bar_timestamp,
        "atr_formula": "simple average of 14 true ranges: max(high-low, abs(high-prev_close), abs(low-prev_close))",
        "bar_inclusion_rule": "uses the 14 completed 1-minute bars at or before atr_bar_timestamp",
        "completed_bars_used": completed_bars,
        "recomputed_atr": recomputed_atr,
        "abnormal_bar": abnormal_bar,
        "sanity_guard": {
            "max_atr": ATR_MAX_SANITY_VALUE,
            "blocks_auto_submit": True,
        },
    })


@app.route("/debug/atr_trade/<trade_id>", methods=["GET"])
def debug_atr_for_trade(trade_id):
    state = load_state()
    trade = state.get("trades", {}).get(trade_id)
    if not trade:
        return jsonify({"ok": False, "error": "trade_not_found"}), 404

    atr_bar_timestamp = trade.get("atr_bar_timestamp")
    completed_bars = get_atr_completed_bars(trade.get("symbol"), atr_bar_timestamp)
    recomputed_atr = compute_simple_atr_from_completed_bars(completed_bars)
    abnormal_bar = find_abnormal_atr_bar(completed_bars)
    return jsonify({
        "ok": True,
        "trade_id": trade_id,
        "symbol": trade.get("symbol"),
        "atr_value": trade.get("atr_value"),
        "atr_bar_timestamp": atr_bar_timestamp,
        "atr_formula": "listener computes simple ATR(14) from true ranges over completed 1-minute bars",
        "bar_inclusion_rule": "entry used the latest ATR snapshot from the listener; audit returns retained bars at or before that timestamp",
        "completed_bars_used": completed_bars,
        "completed_bars_available": len(completed_bars),
        "exact_14_available": len(completed_bars) == ATR_PERIOD,
        "recomputed_atr": recomputed_atr,
        "abnormal_bar": abnormal_bar,
        "audit_note": None if len(completed_bars) == ATR_PERIOD else "Only retained recent bars are available for this historical entry; the exact 14-bar input set was not fully persisted before this fix.",
    })



def handle_stop_hit(trade, timestamp):
    was_break_even = trade.get("moved_to_be") and trade.get("current_stop") == trade.get("entry_price")

    flatten_trade_symbol(
        trade_id=trade["trade_id"],
        symbol=trade["symbol"]
    )

    trade["remaining_size"] = 0
    trade["status"] = "closed"
    trade["exit_reason"] = "stop_hit"
    trade["exit_price"] = trade.get("current_stop")
    trade["closed_at"] = timestamp
    update_post_be_analytics(trade, trade.get("exit_price"), timestamp)
    update_profit_breakdown(trade, include_runner=True)
    apply_closed_trade_accounting(trade)
    print(
        f"TRADE CLOSED trade_id={trade['trade_id']} "
        f"trade_closed_exit_reason={trade['exit_reason']} "
        f"remaining_size={trade['remaining_size']}"
    )
    persist_trade_state(trade)
    log_trade_event(
        trade["trade_id"],
        "stop_hit_close",
        "Stop hit and trade closed",
        {
            "exit_price": trade.get("exit_price"),
            "realized_pnl": trade.get("realized_pnl"),
            "tp1_profit": trade.get("tp1_profit"),
            "runner_profit": trade.get("runner_profit"),
            "total_profit": trade.get("total_profit"),
            "was_break_even": was_break_even,
        },
        snapshot=trade,
        timestamp=timestamp,
    )

    if was_break_even:
        register_trade_breakeven()
    else:
        register_trade_loss()


def handle_be_trigger(trade, timestamp):
    if is_be_state_locked(trade):
        if trade.get("stop_state") == "break_even":
            trade["moved_to_be"] = True
            trade["current_stop"] = trade["entry_price"]
            if not trade.get("be_hit_at"):
                trade["be_hit_at"] = timestamp
        suppress_duplicate_be_trigger(trade, timestamp)
        persist_trade_state(trade)
        return

    if (
        trade.get("entry_price") is not None
        and trade.get("current_stop") is not None
        and round_to_nearest_tick(trade["current_stop"], trade["symbol"])
        == round_to_nearest_tick(trade["entry_price"], trade["symbol"])
    ):
        trade["moved_to_be"] = True
        trade["current_stop"] = trade["entry_price"]
        trade["stop_state"] = "break_even"
        if not trade.get("be_hit_at"):
            trade["be_hit_at"] = timestamp
        lock_be_state(trade, timestamp)
        persist_trade_state(trade)
        return

    active_be_stop = find_executor_be_stop_for_trade(fetch_executor_orders(), trade)
    if active_be_stop:
        trade["stop_order_id"] = active_be_stop.get("order_id")
        trade["current_stop"] = trade["entry_price"]
        trade["moved_to_be"] = True
        trade["stop_state"] = "break_even"
        if not trade.get("be_hit_at"):
            trade["be_hit_at"] = timestamp
        lock_be_state(trade, timestamp)
        persist_trade_state(trade)
        return

    if not trade["stop_order_id"]:
        trade["status"] = "error"
        trade["error_reason"] = "Missing stop_order_id"
        log_trade_event(
            trade["trade_id"],
            "be_stop_error",
            "Cannot move stop to BE without current stop order",
            {"error_reason": trade["error_reason"]},
            snapshot=trade,
            timestamp=timestamp,
        )
        return

    response = modify_stop_order(
        trade_id=trade["trade_id"],
        symbol=trade["symbol"],
        broker_order_id=trade["stop_order_id"],
        stop_price=trade["entry_price"],
        qty=trade["remaining_size"],
        tag="breakeven",
        watch_failures=False,
        oco_group=protective_oco_group(trade),
        oco_role="protective_stop",
    )

    if response.get("ok"):
        trade["stop_order_id"] = response.get("broker_order_id") or trade["stop_order_id"]
        trade["current_stop"] = trade["entry_price"]
        trade["moved_to_be"] = True
        trade["stop_state"] = "break_even"
        trade["be_hit_at"] = timestamp
        lock_be_state(trade, timestamp)
        log_trade_event(
            trade["trade_id"],
            "be_stop_modified",
            "Break-even modified existing active stop",
            {
                "stop_order_id": trade["stop_order_id"],
                "current_stop": trade["current_stop"],
                "remaining_size": trade["remaining_size"],
            },
            snapshot=trade,
            timestamp=timestamp,
        )
        persist_trade_state(trade)
        return

    else:
        active_be_stop = find_executor_be_stop_for_trade(fetch_executor_orders(), trade)
        if active_be_stop:
            trade["stop_order_id"] = active_be_stop.get("order_id")
            trade["current_stop"] = trade["entry_price"]
            trade["moved_to_be"] = True
            trade["stop_state"] = "break_even"
            if not trade.get("be_hit_at"):
                trade["be_hit_at"] = timestamp
            lock_be_state(trade, timestamp)
            log_trade_event(
                trade["trade_id"],
                "be_trigger_duplicate_noop",
                "BE cancel failure reconciled from active executor BE stop",
                {
                    "stop_order_id": trade["stop_order_id"],
                    "current_stop": trade["current_stop"],
                    "modify_response": response.get("message") or response.get("error"),
                },
                snapshot=trade,
                timestamp=timestamp,
            )
            persist_trade_state(trade)
            return

        register_execution_failure(response.get("error", response.get("message", "modify_stop_failed")))
        execution_watcher(response, "modify_stop")
        trade["status"] = "error"
        trade["error_reason"] = response.get("error") or response.get("message") or "BE stop modification failed"
        log_trade_event(
            trade["trade_id"],
            "be_stop_error",
            "BE stop modification failed",
            {"error_reason": trade["error_reason"]},
            snapshot=trade,
            timestamp=timestamp,
        )
        return


def handle_tp1_hit(trade, timestamp):
    tp1_qty = float(trade["position_size"]) / 2

    if not trade.get("tp1_order_id"):
        response = place_limit_order(
            trade_id=trade["trade_id"],
            symbol=trade["symbol"],
            limit_price=trade["tp1_price"],
            qty=tp1_qty,
            tag="tp1",
        )

        if response.get("ok"):
            trade["tp1_order_id"] = response.get("broker_order_id")
            log_trade_event(
                trade["trade_id"],
                "tp1_order_active",
                "Late TP1 limit order created before simulated fill",
                {
                    "tp1_order_id": trade["tp1_order_id"],
                    "tp1_price": trade["tp1_price"],
                    "qty": tp1_qty,
                },
                snapshot=trade,
                timestamp=timestamp,
            )
        else:
            trade["status"] = "error"
            trade["error_reason"] = response.get("error") or response.get("message") or "TP1 order missing and placement failed"
            log_trade_event(
                trade["trade_id"],
                "tp1_error",
                "TP1 fill reached but no active TP1 order could be reconciled",
                {"error_reason": trade["error_reason"]},
                snapshot=trade,
                timestamp=timestamp,
            )
            return

    previous_remaining = float(trade["remaining_size"])
    trade["tp1_hit"] = True
    trade["tp1_hit_at"] = timestamp
    trade["tp1_filled_qty"] = tp1_qty
    trade["tp1_exit_price"] = trade["tp1_price"]
    trade["remaining_size"] = max(previous_remaining - tp1_qty, 0)
    update_profit_breakdown(trade, include_runner=False)
    if trade["remaining_size"] <= 0:
        trade["stop_state"] = "flat"

    persist_trade_state(trade)
    log_trade_event(
        trade["trade_id"],
        "tp1_filled",
        "TP1 simulated partial fill applied",
        {
            "tp1_order_id": trade.get("tp1_order_id"),
            "tp1_price": trade["tp1_price"],
            "filled_qty": tp1_qty,
            "tp1_exit_price": trade["tp1_exit_price"],
            "tp1_profit": trade.get("tp1_profit"),
            "runner_profit": trade.get("runner_profit"),
            "total_profit": trade.get("total_profit"),
            "previous_remaining_size": previous_remaining,
            "remaining_size": trade["remaining_size"],
            "runner_active": trade["remaining_size"] > 0,
        },
        snapshot=trade,
        timestamp=timestamp,
    )

    if trade["remaining_size"] > 0 and trade.get("original_stop") is not None:
        executor_orders = fetch_executor_orders()
        matching_runner_stop = find_matching_active_stop(
            executor_orders,
            trade["trade_id"],
            trade["symbol"],
            trade["original_stop"],
            trade["remaining_size"],
        )

        if matching_runner_stop:
            trade["stop_order_id"] = matching_runner_stop.get("order_id")
            trade["current_stop"] = trade["original_stop"]
            trade["moved_to_be"] = True
            trade["stop_state"] = "runner_original"
            lock_be_state(trade, timestamp)
            log_trade_event(
                trade["trade_id"],
                "runner_stop_original_duplicate_noop",
                "Runner stop already at original stop after TP1 fill",
                {
                    "stop_order_id": trade["stop_order_id"],
                    "original_stop": trade["original_stop"],
                    "remaining_size": trade["remaining_size"],
                },
                snapshot=trade,
                timestamp=timestamp,
            )
            persist_trade_state(trade)
            return

        reset_response = reset_stop_to_original(
            trade_id=trade["trade_id"],
            symbol=trade["symbol"],
            stop_price=trade["original_stop"],
            qty=trade["remaining_size"],
            watch_failures=False,
            oco_parent_group=protective_oco_group(trade),
        )

        if not reset_response.get("ok"):
            matching_runner_stop = find_matching_active_stop(
                fetch_executor_orders(),
                trade["trade_id"],
                trade["symbol"],
                trade["original_stop"],
                trade["remaining_size"],
            )
            if not matching_runner_stop and response_is_active_stop_exists(reset_response):
                matching_runner_stop = find_matching_active_stop_from_response(
                    fetch_executor_orders(),
                    reset_response,
                    trade["trade_id"],
                    trade["symbol"],
                    trade["original_stop"],
                    trade["remaining_size"],
                )

        if reset_response.get("ok") or matching_runner_stop:
            trade["stop_order_id"] = (
                reset_response.get("broker_order_id")
                or reset_response.get("new_stop_id")
                or (matching_runner_stop or {}).get("order_id")
                or trade.get("stop_order_id")
            )
            trade["current_stop"] = trade["original_stop"]
            trade["moved_to_be"] = True
            trade["stop_state"] = "runner_original"
            lock_be_state(trade, timestamp)
            log_trade_event(
                trade["trade_id"],
                "runner_stop_reset_to_original",
                "Runner stop reset to original stop after TP1 fill",
                {
                    "stop_order_id": trade["stop_order_id"],
                    "original_stop": trade["original_stop"],
                    "remaining_size": trade["remaining_size"],
                },
                snapshot=trade,
                timestamp=timestamp,
            )
            persist_trade_state(trade)
        else:
            register_execution_failure(reset_response.get("error", reset_response.get("message", "runner_stop_original_reset_failed")))
            execution_watcher(reset_response, "reset_stop_to_original")
            trade["status"] = "error"
            trade["error_reason"] = reset_response.get("error") or reset_response.get("message") or "runner stop original reset failed"
            log_trade_event(
                trade["trade_id"],
                "runner_stop_original_reset_error",
                "Runner stop reset to original failed after TP1 fill",
                {"error_reason": trade["error_reason"]},
                snapshot=trade,
                timestamp=timestamp,
            )
            return


def get_trade(trade_id):
    state = load_state()
    return state["trades"].get(trade_id)


def process_price_update_by_id(trade_id, price, timestamp):
    run_noon_runner_flatten_if_due(reference_time=timestamp)
    trade = get_trade(trade_id)

    if not trade:
        raise ValueError(f"Trade not found: {trade_id}")

    updated_trade = process_price_update(trade, price, timestamp)
    persist_trade_state(updated_trade)
    return updated_trade


def simulate_prices_for_trade(trade_id, prices, timestamps=None):
    if timestamps is None:
        base = datetime(2026, 1, 1, 9, 30, 0)
        timestamps = [
            base.replace(minute=base.minute + index)
            for index, _ in enumerate(prices)
        ]

    if len(prices) != len(timestamps):
        raise ValueError("prices and timestamps must have the same length")

    snapshots = []
    for price, timestamp in zip(prices, timestamps):
        snapshots.append(process_price_update_by_id(trade_id, float(price), timestamp))

    final_trade = get_trade(trade_id)
    log_trade_event(
        trade_id,
        "final_trade_persistence_snapshot",
        "Final trade persistence snapshot after simulated price sequence",
        snapshot=final_trade,
        timestamp=timestamps[-1] if timestamps else None,
    )
    return snapshots


# =========================
# PHASE 6 — QA HARNESS
# Repeatable Scenario Testing
# =========================

QA_RESULTS = []
MISMATCH_LOG = []


def reset_runtime_state():
    global QA_LOGS, QA_RESULTS, MISMATCH_LOG, COMMAND_LOG, PROCESSED_EVENTS
    QA_LOGS.clear()
    QA_RESULTS.clear()
    MISMATCH_LOG.clear()
    COMMAND_LOG.clear()
    PROCESSED_EVENTS.clear()

    RISK_STATE["kill_switch_active"] = False
    RISK_STATE["kill_switch_reason"] = None
    RISK_STATE["daily_trade_count"] = 0
    RISK_STATE["daily_loss_count"] = 0
    RISK_STATE["current_drawdown_pct"] = 0.0
    RISK_STATE["trading_halted"] = False
    RISK_STATE["last_reset_date"] = datetime.now().date().isoformat()

    FAILURE_STATE["execution_failure_count"] = 0
    FAILURE_STATE["qa_critical_count"] = 0
    FAILURE_STATE["last_failure_at"] = None
    FAILURE_STATE["halt_reason"] = None

    persist_risk_state()


class MockResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def mock_executor_response(action, payload):
    if action == "submit_entry":
        fill_price = round_price(payload.get("fill_price_override", 100))
        return {
            "ok": True,
            "broker_order_id": f"ENTRY-{uuid.uuid4().hex[:8]}",
            "fill_price": fill_price,
            "fill_price_source": "mock_executor",
            "order": {
                "trade_id": payload.get("trade_id"),
                "symbol": payload.get("symbol"),
                "direction": payload.get("direction"),
                "qty": payload.get("qty"),
                "filled_price": fill_price,
                "status": "filled",
            }
        }
    if action == "submit_stop":
        return {"ok": True, "broker_order_id": f"STOP-{uuid.uuid4().hex[:8]}"}
    if action == "submit_limit":
        return {"ok": True, "broker_order_id": f"LIMIT-{uuid.uuid4().hex[:8]}"}
    if action == "cancel_order":
        return {"ok": True, "broker_order_id": payload.get("broker_order_id")}
    if action == "flatten_symbol":
        return {"ok": True, "message": "flattened"}
    if action == "flatten_all":
        return {
            "ok": True,
            "message": "Global flatten complete",
            "flattened_symbols": [],
            "cancelled_order_ids": [],
        }
    return {"ok": False, "error": f"unknown_action:{action}"}


def run_with_mock_executor(test_fn):
    original_post = requests.post
    original_get = requests.get

    def fake_post(url, json, **kwargs):
        action = json.get("action")
        payload = {k: v for k, v in json.items() if k != "action"}
        return MockResponse(mock_executor_response(action, payload))

    def fake_get(url, timeout=1.0):
        if url == EXECUTOR_ORDERS_URL:
            return MockResponse({"ok": True, "orders": []})

        if url == EXECUTOR_SNAPSHOT_URL:
            return MockResponse({
                "ok": True,
                "symbols": {
                    "NQ": {
                        "position_qty": 0.0,
                        "avg_entry_price": 0.0,
                        "is_flat": True,
                        "working_orders": [],
                        "has_stop": False,
                        "stop_order": None,
                        "atr_1m_14": 10.0,
                        "atr_source": "live_executor_1m14",
                        "atr_bar_timestamp": "2026-04-19T06:14:00-07:00",
                        "atr_status": "ready",
                        "atr_error": None,
                    },
                    "ES": {
                        "position_qty": 0.0,
                        "avg_entry_price": 0.0,
                        "is_flat": True,
                        "working_orders": [],
                        "has_stop": False,
                        "stop_order": None,
                        "atr_1m_14": 10.0,
                        "atr_source": "live_executor_1m14",
                        "atr_bar_timestamp": "2026-04-19T06:14:00-07:00",
                        "atr_status": "ready",
                        "atr_error": None,
                    }
                }
            })

        return MockResponse({"ok": False, "error": f"unknown_get:{url}"})

    requests.post = fake_post
    requests.get = fake_get
    try:
        return test_fn()
    finally:
        requests.post = original_post
        requests.get = original_get


def record_mismatch(scenario_name, field, expected, actual):
    entry = {
        "scenario": scenario_name,
        "field": field,
        "expected": expected,
        "actual": actual,
        "timestamp": datetime.now().isoformat()
    }
    MISMATCH_LOG.append(entry)
    return entry


def evaluate_scenario(scenario_name, expected, actual):
    mismatches = []

    for field, expected_value in expected.items():
        actual_value = actual.get(field)
        if actual_value != expected_value:
            mismatches.append(record_mismatch(scenario_name, field, expected_value, actual_value))

    result = {
        "scenario": scenario_name,
        "passed": len(mismatches) == 0,
        "expected": expected,
        "actual": actual,
        "mismatches": mismatches,
        "timestamp": datetime.now().isoformat()
    }

    QA_RESULTS.append(result)
    status = "PASS" if result["passed"] else "FAIL"
    print(f"QA HARNESS [{status}] {scenario_name}")
    return result


def scenario_be_trigger():
    reset_runtime_state()
    bootstrap_trade_manager()

    packet = {
        "event": "enter_trade",
        "symbol": "NQ",
        "direction": "long",
        "position_size": 2
    }

    trade = submit_trade(packet)
    trade = process_price_update_by_id(trade["trade_id"], 105, datetime.now())

    actual = {
        "status": trade["status"],
        "moved_to_be": trade["moved_to_be"],
        "current_stop": trade["current_stop"],
        "stop_state": trade["stop_state"]
    }

    expected = {
        "status": "active",
        "moved_to_be": True,
        "current_stop": 100,
        "stop_state": "break_even"
    }

    return evaluate_scenario("be_trigger", expected, actual)


def scenario_tp1_hit():
    reset_runtime_state()
    bootstrap_trade_manager()

    packet = {
        "event": "enter_trade",
        "symbol": "NQ",
        "direction": "long",
        "position_size": 2
    }

    trade = submit_trade(packet)
    trade = process_price_update_by_id(trade["trade_id"], 110, datetime.now())

    actual = {
        "status": trade["status"],
        "tp1_hit": trade["tp1_hit"],
        "remaining_size": trade["remaining_size"],
        "be_then_tp1_same_update": trade["be_then_tp1_same_update"]
    }

    expected = {
        "status": "active",
        "tp1_hit": True,
        "remaining_size": 1.0,
        "be_then_tp1_same_update": True
    }

    return evaluate_scenario("tp1_hit_same_update", expected, actual)


def scenario_stop_hit():
    reset_runtime_state()
    bootstrap_trade_manager()

    packet = {
        "event": "enter_trade",
        "symbol": "NQ",
        "direction": "long",
        "position_size": 2
    }

    trade = submit_trade(packet)
    trade = process_price_update_by_id(trade["trade_id"], 90, datetime.now())

    actual = {
        "status": trade["status"],
        "remaining_size": trade["remaining_size"],
        "exit_reason": trade["exit_reason"]
    }

    expected = {
        "status": "closed",
        "remaining_size": 0,
        "exit_reason": "stop_hit"
    }

    return evaluate_scenario("stop_hit", expected, actual)


def scenario_duplicate_event_blocked():
    reset_runtime_state()
    bootstrap_trade_manager()

    packet = {
        "event": "enter_trade",
        "symbol": "NQ",
        "direction": "long",
        "position_size": 2
    }

    trade = submit_trade(packet)
    ts = datetime.now()
    trade = process_price_update_by_id(trade["trade_id"], 105, ts)
    first_command_count = len(COMMAND_LOG)
    trade = process_price_update_by_id(trade["trade_id"], 105, ts)
    second_command_count = len(COMMAND_LOG)

    actual = {
        "first_command_count": first_command_count,
        "second_command_count": second_command_count,
        "moved_to_be": trade["moved_to_be"]
    }

    expected = {
        "first_command_count": 4,
        "second_command_count": 4,
        "moved_to_be": False
    }

    return evaluate_scenario("duplicate_event_blocked", expected, actual)


def scenario_missing_stop_sets_error():
    reset_runtime_state()
    bootstrap_trade_manager()

    trade = create_trade_state({
        "symbol": "NQ",
        "direction": "long",
        "position_size": 2
    }, {
        "atr_value": 10.0,
        "atr_source": "live_executor_1m14",
        "atr_bar_timestamp": "2026-04-19T06:14:00-07:00",
    })
    trade.update(derive_trade_levels(100, "long", trade["atr_value"]))
    persist_trade_state(trade)

    trade = process_price_update_by_id(trade["trade_id"], 105, datetime.now())

    actual = {
        "status": trade["status"],
        "error_reason": trade["error_reason"]
    }

    expected = {
        "status": "error",
        "error_reason": "Missing stop_order_id"
    }

    return evaluate_scenario("missing_stop_sets_error", expected, actual)


def scenario_trade_blocked_after_daily_limit():
    reset_runtime_state()
    bootstrap_trade_manager()
    RISK_STATE["kill_switch_active"] = False
    RISK_STATE["kill_switch_reason"] = None
    RISK_STATE["daily_trade_count"] = 2
    RISK_STATE["daily_loss_count"] = 0
    RISK_STATE["trading_halted"] = False
    RISK_STATE["last_reset_date"] = datetime.now().date().isoformat()

    blocked = False
    reason = None

    try:
        submit_trade({
            "event": "enter_trade",
            "symbol": "NQ",
            "direction": "long",
            "position_size": 2
        })
    except ValueError as e:
        blocked = True
        reason = str(e)

    actual = {
        "blocked": blocked,
        "reason_contains": "max_daily_trades_reached" in (reason or "")
    }

    expected = {
        "blocked": True,
        "reason_contains": True
    }

    return evaluate_scenario("trade_blocked_after_daily_limit", expected, actual)


def scenario_kill_switch_blocks_trade():
    reset_runtime_state()
    bootstrap_trade_manager()
    RISK_STATE["kill_switch_active"] = False
    RISK_STATE["kill_switch_reason"] = None
    RISK_STATE["daily_trade_count"] = 0
    RISK_STATE["daily_loss_count"] = 0
    RISK_STATE["trading_halted"] = False
    RISK_STATE["last_reset_date"] = datetime.now().date().isoformat()

    set_current_drawdown(11.0)

    blocked = False
    reason = None

    try:
        submit_trade({
            "event": "enter_trade",
            "symbol": "NQ",
            "direction": "long",
            "position_size": 2
        })
    except ValueError as e:
        blocked = True
        reason = str(e)

    actual = {
        "kill_switch_active": RISK_STATE["kill_switch_active"],
        "blocked": blocked,
        "reason_contains": "kill_switch_active" in (reason or "")
    }

    expected = {
        "kill_switch_active": True,
        "blocked": True,
        "reason_contains": True
    }

    return evaluate_scenario("kill_switch_blocks_trade", expected, actual)


def scenario_one_loss_halts_trading():
    reset_runtime_state()
    bootstrap_trade_manager()

    packet = {
        "event": "enter_trade",
        "symbol": "NQ",
        "direction": "long",
        "position_size": 2
    }

    trade = submit_trade(packet)
    trade = process_price_update_by_id(trade["trade_id"], 90, datetime.now())

    blocked = False
    reason = None
    try:
        submit_trade({
            "event": "enter_trade",
            "symbol": "ES",
            "direction": "long",
            "position_size": 2
        })
    except ValueError as e:
        blocked = True
        reason = str(e)

    actual = {
        "daily_loss_count": RISK_STATE["daily_loss_count"],
        "trading_halted": RISK_STATE["trading_halted"],
        "blocked": blocked,
        "reason_contains": "trading_halted" in (reason or "") or "max_daily_losses_reached" in (reason or "")
    }

    expected = {
        "daily_loss_count": 1,
        "trading_halted": True,
        "blocked": True,
        "reason_contains": True
    }

    return evaluate_scenario("one_loss_halts_trading", expected, actual)


def scenario_active_symbol_blocked():
    reset_runtime_state()
    bootstrap_trade_manager()

    first_trade = submit_trade({
        "event": "enter_trade",
        "symbol": "NQ",
        "direction": "long",
        "position_size": 2
    })

    blocked = False
    reason = None
    try:
        submit_trade({
            "event": "enter_trade",
            "symbol": "NQ",
            "direction": "long",
            "position_size": 2
        })
    except ValueError as e:
        blocked = True
        reason = str(e)

    actual = {
        "first_trade_active": first_trade["status"] == "active",
        "blocked": blocked,
        "reason_contains": "active_trade_exists_for_symbol:NQ" in (reason or "")
    }

    expected = {
        "first_trade_active": True,
        "blocked": True,
        "reason_contains": True
    }

    return evaluate_scenario("active_symbol_blocked", expected, actual)


def scenario_execution_failure_escalates_kill_switch():
    reset_runtime_state()
    bootstrap_trade_manager()

    register_execution_failure("test_failure_1")
    register_execution_failure("test_failure_2")
    register_execution_failure("test_failure_3")

    actual = {
        "execution_failure_count": FAILURE_STATE["execution_failure_count"],
        "kill_switch_active": RISK_STATE["kill_switch_active"],
        "halt_reason_contains": "execution failure escalation" in (RISK_STATE["kill_switch_reason"] or "")
    }

    expected = {
        "execution_failure_count": 3,
        "kill_switch_active": True,
        "halt_reason_contains": True
    }

    return evaluate_scenario("execution_failure_escalates_kill_switch", expected, actual)


def scenario_qa_critical_escalates_kill_switch():
    reset_runtime_state()
    bootstrap_trade_manager()

    register_qa_critical_failure("critical_test_1")
    register_qa_critical_failure("critical_test_2")
    register_qa_critical_failure("critical_test_3")

    actual = {
        "qa_critical_count": FAILURE_STATE["qa_critical_count"],
        "kill_switch_active": RISK_STATE["kill_switch_active"],
        "halt_reason_contains": "qa critical escalation" in (RISK_STATE["kill_switch_reason"] or "")
    }

    expected = {
        "qa_critical_count": 3,
        "kill_switch_active": True,
        "halt_reason_contains": True
    }

    return evaluate_scenario("qa_critical_escalates_kill_switch", expected, actual)


def run_qa_harness():
    scenarios = [
        scenario_be_trigger,
        scenario_tp1_hit,
        scenario_stop_hit,
        scenario_duplicate_event_blocked,
        scenario_missing_stop_sets_error,
        scenario_trade_blocked_after_daily_limit,
        scenario_kill_switch_blocks_trade,
        scenario_one_loss_halts_trading,
        scenario_active_symbol_blocked,
        scenario_execution_failure_escalates_kill_switch,
        scenario_qa_critical_escalates_kill_switch
    ]

    results = []

    def runner():
        for scenario in scenarios:
            results.append(scenario())
        return results

    run_with_mock_executor(runner)

    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed

    summary = {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
        "mismatch_log": MISMATCH_LOG.copy(),
        "timestamp": datetime.now().isoformat()
    }

    print("QA HARNESS SUMMARY:", {
        "total": summary["total"],
        "passed": summary["passed"],
        "failed": summary["failed"]
    })

    return summary


if __name__ == "__main__":
    bootstrap_trade_manager()
    run_qa_checks(label="startup")
    print("TRADE MANAGER PRICE SERVER RUNNING ON http://127.0.0.1:7001")
    app.run(host="127.0.0.1", port=7001, debug=False, use_reloader=False)
