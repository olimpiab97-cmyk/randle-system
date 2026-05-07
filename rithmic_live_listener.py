import os
import subprocess
import sys
import tempfile
import textwrap
import time
import zipfile
import json
import math
import queue
import threading
import urllib.error
import urllib.request
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from symbol_resolution import (
    canonicalize_symbol_input,
    get_default_listener_subscriptions,
    normalize_symbol_root,
)


BASE_DIR = Path(__file__).resolve().parent
RITHMIC_ZIP_PATH = BASE_DIR / "Rithmic API" / "RApiPlus.NET.13.7.0.0.zip"
RITHMIC_CACHE_DIR = Path(tempfile.gettempdir()) / "rithmic_phase_a"
RITHMIC_RUNTIME_DIR = RITHMIC_CACHE_DIR / "runtime"
RAPIPLUS_DLL_PATH = RITHMIC_RUNTIME_DIR / "rapiplus.dll"
POWERSHELL_BRIDGE_PATH = RITHMIC_CACHE_DIR / "rithmic_phase_a_login.ps1"
ENGINE_CREATION_TIMEOUT_SECONDS = 20
DEFAULT_RITHMIC_SUBSCRIPTIONS = tuple(get_default_listener_subscriptions())
RITHMIC_SUBSCRIPTIONS_ENV = "RITHMIC_LIVE_SUBSCRIPTIONS"
RITHMIC_SECONDARY_DIAGNOSTIC_SUBSCRIPTION_ENV = "RITHMIC_RTY_DIAGNOSTIC_SUBSCRIPTION"
RTY_DIAGNOSTIC_CANDIDATES = (
    ("CME", "RTYM6"),
    ("CME", "RTY"),
)
ATR_SNAPSHOT_PATH = BASE_DIR / "Data" / "rithmic_atr_snapshot.json"
RECENT_BARS_PATH = BASE_DIR / "Data" / "rithmic_recent_bars.json"
FEED_HEALTH_PATH = BASE_DIR / "Data" / "rithmic_feed_health.json"
ATR_SHADOW_COMPARISON_PATH = BASE_DIR / "Data" / "rithmic_atr_shadow_comparison.json"
TRADE_MANAGER_PERSISTENCE_PATH = BASE_DIR / "Data" / "persistence_state.json"
MAX_PERSISTED_BARS = 30
ATR_PERIOD = 14
ATR_SEED_BAR_COUNT = ATR_PERIOD + 1
ATR_MAX_BAR_GAP_SECONDS = 60
FEED_QUIET_SECONDS_BY_ROOT = {
    "NQ": float(os.getenv("RITHMIC_NQ_QUIET_SECONDS", "2.0") or "2.0"),
    "YM": float(os.getenv("RITHMIC_YM_QUIET_SECONDS", "3.0") or "3.0"),
    "RTY": float(os.getenv("RITHMIC_RTY_QUIET_SECONDS", "3.0") or "3.0"),
}
FEED_STALE_SECONDS_BY_ROOT = {
    "NQ": float(os.getenv("RITHMIC_NQ_STALE_SECONDS", "3.0") or "3.0"),
    "YM": float(os.getenv("RITHMIC_YM_STALE_SECONDS", "10.0") or "10.0"),
    "RTY": float(os.getenv("RITHMIC_RTY_STALE_SECONDS", "10.0") or "10.0"),
}
FEED_DISCONNECTED_SECONDS_BY_ROOT = {
    "NQ": float(os.getenv("RITHMIC_NQ_DISCONNECTED_SECONDS", "10.0") or "10.0"),
    "YM": float(os.getenv("RITHMIC_YM_DISCONNECTED_SECONDS", "30.0") or "30.0"),
    "RTY": float(os.getenv("RITHMIC_RTY_DISCONNECTED_SECONDS", "30.0") or "30.0"),
}
FEED_RECOVERY_TICK_CONFIRMATIONS = int(os.getenv("RITHMIC_FEED_RECOVERY_TICK_CONFIRMATIONS", "2") or "2")
FEED_QUIET_SECONDS = FEED_QUIET_SECONDS_BY_ROOT["NQ"]
FEED_STALE_SECONDS = FEED_STALE_SECONDS_BY_ROOT["NQ"]
FEED_DISCONNECTED_SECONDS = FEED_DISCONNECTED_SECONDS_BY_ROOT["NQ"]
ALL_PRICES_FROZEN_SECONDS = float(os.getenv("RITHMIC_ALL_PRICES_FROZEN_SECONDS", "10.0") or "10.0")
PRICE_SANITY_MAX_MOVE_BY_ROOT = {
    "NQ": float(os.getenv("RITHMIC_NQ_PRICE_SANITY_MAX_MOVE", "250.0") or "250.0"),
    "YM": float(os.getenv("RITHMIC_YM_PRICE_SANITY_MAX_MOVE", "1000.0") or "1000.0"),
    "RTY": float(os.getenv("RITHMIC_RTY_PRICE_SANITY_MAX_MOVE", "100.0") or "100.0"),
}
TICK_QUEUE_MAX_SIZE = int(os.getenv("RITHMIC_TICK_QUEUE_MAX_SIZE", "5000") or "5000")
PRICE_POST_MIN_INTERVAL_SECONDS = 1.0
EXECUTOR_PRICE_POST_TIMEOUT_SECONDS = min(float(os.getenv("RITHMIC_EXECUTOR_PRICE_POST_TIMEOUT_SECONDS", "0.05") or "0.05"), 0.05)
LISTENER_DOWNSTREAM_FORWARD_ENABLED = os.getenv("RITHMIC_ENABLE_DOWNSTREAM_PRICE_POSTS", "0").strip().lower() in {"1", "true", "yes", "on"}
FEED_HEALTH_WRITE_MIN_INTERVAL_SECONDS = float(os.getenv("RITHMIC_FEED_HEALTH_WRITE_MIN_INTERVAL_SECONDS", "1.0") or "1.0")
LISTENER_SUMMARY_HEARTBEAT_SECONDS = float(os.getenv("RITHMIC_SUMMARY_HEARTBEAT_SECONDS", "30.0") or "30.0")
VERBOSE_TICKS = os.getenv("RITHMIC_VERBOSE_TICKS", "false").strip().lower() in {"1", "true", "yes", "on"}
LOG_RAW_TICKS = VERBOSE_TICKS
HISTORICAL_SEED_LOOKBACK_MINUTES = 30
RECONNECT_BASE_DELAY_SECONDS = 2
RECONNECT_MAX_DELAY_SECONDS = 30
RESTART_DEAD_THRESHOLD_SECONDS = 25
RESTART_COOLDOWN_SECONDS = 60
MAX_RESTART_ATTEMPTS = 3
EXECUTOR_PRICE_URL = os.getenv("EXECUTOR_PRICE_URL", "http://127.0.0.1:6001/price").strip() or "http://127.0.0.1:6001/price"
LIVE_TICK_SYMBOLS = set()
DEAD_RESTART_ATTEMPTS = defaultdict(int)
DEAD_RESTART_LAST_TIMES = {}
latest_price_lock = threading.Lock()
latest_price_by_symbol = {}
latest_tick_time_by_symbol = {}
latest_tick_monotonic_by_symbol = {}
latest_dirty_by_symbol = set()
latest_published_tick_time_by_symbol = {}
raw_callback_count = defaultdict(int)

# Credentials are read only from environment variables and must never be printed
# or included raw in diagnostics/errors.
RITHMIC_USER = os.getenv("RITHMIC_USER", "").strip()
RITHMIC_PASSWORD = os.getenv("RITHMIC_PASSWORD", "").strip()
RITHMIC_MD_CONNECTION_POINT = os.getenv("RITHMIC_MD_CONNECTION_POINT", "login_agent_tp_paper_sumc").strip() or "login_agent_tp_paper_sumc"
RITHMIC_TS_CONNECTION_POINT = os.getenv("RITHMIC_TS_CONNECTION_POINT", "login_agent_op_paperc").strip() or "login_agent_op_paperc"
RITHMIC_REPOSITORY_CONNECTION_POINT = os.getenv("RITHMIC_REPOSITORY_CONNECTION_POINT", "login_agent_repositoryc").strip() or "login_agent_repositoryc"


def redact_secret(value):
    raw_value = str(value or "")
    if not raw_value:
        return "missing"
    if len(raw_value) <= 2:
        return "<redacted>"
    return f"{raw_value[0]}...{raw_value[-1]} (redacted)"


def credential_presence_status():
    return {
        "RITHMIC_USER": "present" if RITHMIC_USER else "missing",
        "RITHMIC_PASSWORD": "present" if RITHMIC_PASSWORD else "missing",
    }


def sanitize_log_message(message):
    sanitized = str(message)
    secret_values = [
        RITHMIC_USER,
        RITHMIC_PASSWORD,
        os.getenv("RANDLE_INTERNAL_TOKEN", ""),
    ]
    for secret in secret_values:
        if secret:
            sanitized = sanitized.replace(secret, redact_secret(secret))
    return sanitized


def ensure_runtime_files():
    if not RITHMIC_ZIP_PATH.exists():
        raise FileNotFoundError(f"Missing Rithmic API zip: {RITHMIC_ZIP_PATH}")

    RITHMIC_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    if not RAPIPLUS_DLL_PATH.exists():
        with zipfile.ZipFile(RITHMIC_ZIP_PATH) as archive:
            runtime_prefix = "13.7.0.0/win10/lib_472/"
            for member in archive.infolist():
                if not member.filename.startswith(runtime_prefix) or member.is_dir():
                    continue

                relative_path = member.filename[len(runtime_prefix):]
                target_path = RITHMIC_RUNTIME_DIR / relative_path
                target_path.parent.mkdir(parents=True, exist_ok=True)

                with archive.open(member) as src, target_path.open("wb") as dst:
                    dst.write(src.read())

    return RAPIPLUS_DLL_PATH


def parse_rithmic_subscriptions():
    raw_value = os.getenv(RITHMIC_SUBSCRIPTIONS_ENV, "").strip()
    if not raw_value:
        subscriptions = list(DEFAULT_RITHMIC_SUBSCRIPTIONS)
    else:
        subscriptions = []
        for item in raw_value.split(","):
            item = item.strip()
            if not item:
                continue
            if ":" not in item:
                raise ValueError(
                    f"Invalid {RITHMIC_SUBSCRIPTIONS_ENV} entry '{item}'. Expected EXCHANGE:SYMBOL."
                )
            exchange_code, symbol_code = item.split(":", 1)
            exchange_code = exchange_code.strip().upper()
            symbol_code = str(symbol_code or "").strip().upper()
            if not exchange_code or not symbol_code:
                raise ValueError(
                    f"Invalid {RITHMIC_SUBSCRIPTIONS_ENV} entry '{item}'. Expected EXCHANGE:SYMBOL."
                )
            subscriptions.append((exchange_code, symbol_code))

    diagnostic_override = os.getenv(RITHMIC_SECONDARY_DIAGNOSTIC_SUBSCRIPTION_ENV, "").strip()
    if diagnostic_override:
        if ":" not in diagnostic_override:
            raise ValueError(
                f"Invalid {RITHMIC_SECONDARY_DIAGNOSTIC_SUBSCRIPTION_ENV} entry '{diagnostic_override}'. Expected EXCHANGE:SYMBOL."
            )
        exchange_code, symbol_code = diagnostic_override.split(":", 1)
        exchange_code = exchange_code.strip().upper()
        symbol_code = str(symbol_code or "").strip().upper()
        if not exchange_code or not symbol_code:
            raise ValueError(
                f"Invalid {RITHMIC_SECONDARY_DIAGNOSTIC_SUBSCRIPTION_ENV} entry '{diagnostic_override}'. Expected EXCHANGE:SYMBOL."
            )
        subscriptions = [
            (existing_exchange, existing_symbol)
            for existing_exchange, existing_symbol in subscriptions
            if normalize_symbol_root(existing_symbol) != "RTY"
        ]
        subscriptions.append((exchange_code, symbol_code))

    if not subscriptions:
        raise ValueError(f"{RITHMIC_SUBSCRIPTIONS_ENV} did not contain any subscriptions")

    return subscriptions


def build_snapshot_symbol_aliases(symbol):
    normalized_symbol = str(symbol or "").strip().upper()
    canonical_symbol = canonicalize_symbol_input(normalized_symbol)
    root_symbol = normalize_symbol_root(normalized_symbol)
    aliases = []

    if normalized_symbol:
        aliases.append(normalized_symbol)

    if canonical_symbol and canonical_symbol not in aliases:
        aliases.append(canonical_symbol)

    if root_symbol and root_symbol not in aliases:
        aliases.append(root_symbol)

    return aliases


def atomic_write_json(path, payload):
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=target_path.parent,
        delete=False,
    ) as tmp_file:
        json.dump(payload, tmp_file, indent=2)
        tmp_file.flush()
        os.fsync(tmp_file.fileno())
        temp_path = Path(tmp_file.name)

    os.replace(temp_path, target_path)


def utc_now_iso():
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat() + "Z"


def parse_utc_timestamp(value):
    try:
        text = str(value).replace("Z", "+00:00")
        if "." in text:
            head, tail = text.split(".", 1)
            fraction = tail
            suffix = ""
            for marker in ("+", "-"):
                if marker in tail:
                    fraction, suffix = tail.split(marker, 1)
                    suffix = marker + suffix
                    break
            if len(fraction) > 6:
                text = head + "." + fraction[:6] + suffix
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except Exception:
        return None


def get_feed_thresholds(symbol):
    root_symbol = normalize_symbol_root(symbol)
    return {
        "quiet_seconds": FEED_QUIET_SECONDS_BY_ROOT.get(root_symbol, FEED_QUIET_SECONDS),
        "stale_seconds": FEED_STALE_SECONDS_BY_ROOT.get(root_symbol, FEED_STALE_SECONDS),
        "disconnected_seconds": FEED_DISCONNECTED_SECONDS_BY_ROOT.get(root_symbol, FEED_DISCONNECTED_SECONDS),
    }


def get_price_sanity_max_move(symbol):
    return PRICE_SANITY_MAX_MOVE_BY_ROOT.get(normalize_symbol_root(symbol), float(os.getenv("RITHMIC_PRICE_SANITY_MAX_MOVE", "250.0") or "250.0"))


def validate_tick_price_sanity(symbol, price, previous_price=None):
    try:
        current = float(price)
    except (TypeError, ValueError):
        return False, "price_not_numeric"
    if not math.isfinite(current) or current <= 0:
        return False, "price_not_positive"
    if previous_price is None:
        return True, None
    try:
        previous = float(previous_price)
    except (TypeError, ValueError):
        return True, None
    if not math.isfinite(previous) or previous <= 0:
        return True, None
    max_move = get_price_sanity_max_move(symbol)
    if abs(current - previous) > max_move:
        return False, f"price_jump_exceeds_{max_move}"
    return True, None


def calculate_feed_status(entry, reference_time=None, symbol=None):
    if reference_time is None:
        reference_time = datetime.now(timezone.utc).replace(tzinfo=None)
    last_tick = parse_utc_timestamp(entry.get("last_tick_timestamp_utc"))
    if last_tick is None:
        return "STALE"
    thresholds = get_feed_thresholds(symbol)
    age_seconds = max(0.0, (reference_time - last_tick).total_seconds())
    if age_seconds > thresholds["disconnected_seconds"]:
        return "DEAD"
    if age_seconds > thresholds["stale_seconds"]:
        return "STALE"
    if age_seconds > thresholds["quiet_seconds"]:
        return "QUIET"
    return "LIVE"


def refresh_feed_health_statuses(payload, reference_time=None):
    symbols = payload.setdefault("symbols", {})
    any_stale = not symbols
    bridge_post_ages = []
    frozen_price_symbols = []
    for symbol, entry in symbols.items():
        if isinstance(entry, dict):
            had_previous_status = "feed_status" in entry
            previous_status = str(entry.get("feed_status") or "STALE").upper()
            next_status = calculate_feed_status(entry, reference_time=reference_time, symbol=symbol)
            if str(entry.get("price_sanity_status") or "").upper() == "INVALID_PRICE":
                next_status = "INVALID"
            if next_status == "LIVE" and had_previous_status and previous_status in {"STALE", "DEAD", "DISCONNECTED", "INVALID"}:
                confirmations = int(entry.get("recovery_tick_confirmations", 0) or 0)
                if confirmations < FEED_RECOVERY_TICK_CONFIRMATIONS:
                    next_status = "STALE"
            entry["feed_status"] = next_status
            thresholds = get_feed_thresholds(symbol)
            entry["feed_quiet_seconds"] = thresholds["quiet_seconds"]
            entry["feed_stale_seconds"] = thresholds["stale_seconds"]
            entry["feed_disconnected_seconds"] = thresholds["disconnected_seconds"]
            last_tick = parse_utc_timestamp(entry.get("last_tick_timestamp_utc"))
            if last_tick is not None:
                reference_for_tick = reference_time if reference_time is not None else datetime.now(timezone.utc).replace(tzinfo=None)
                entry["feed_age_seconds"] = round(max(0.0, (reference_for_tick - last_tick).total_seconds()), 3)
            else:
                entry["feed_age_seconds"] = None
            bridge_post_at = parse_utc_timestamp(
                entry.get("last_successful_executor_price_post_timestamp_utc")
                or entry.get("last_bridge_post_timestamp_utc")
            )
            if bridge_post_at is not None:
                if reference_time is None:
                    reference_for_bridge = datetime.now(timezone.utc).replace(tzinfo=None)
                else:
                    reference_for_bridge = reference_time
                bridge_age = max(0.0, (reference_for_bridge - bridge_post_at).total_seconds())
                entry["last_bridge_post_age_seconds"] = round(bridge_age, 3)
                bridge_post_ages.append(bridge_age)
                if bridge_age > ALL_PRICES_FROZEN_SECONDS:
                    entry["price_bridge_status"] = "FROZEN"
                    frozen_price_symbols.append(symbol)
                else:
                    entry["price_bridge_status"] = "LIVE"
            else:
                entry["last_bridge_post_age_seconds"] = None
                entry["price_bridge_status"] = "MISSING"
            if entry["feed_status"] != "LIVE":
                any_stale = True
    all_prices_frozen = bool(bridge_post_ages) and all(age > ALL_PRICES_FROZEN_SECONDS for age in bridge_post_ages)
    payload["all_prices_frozen"] = all_prices_frozen
    payload["critical_status"] = "all_prices_frozen" if all_prices_frozen else None
    payload["frozen_price_symbols"] = sorted(set(frozen_price_symbols))
    payload["all_prices_frozen_threshold_seconds"] = ALL_PRICES_FROZEN_SECONDS
    payload["updated_at_utc"] = utc_now_iso()
    payload["system_state_feed"] = "CRITICAL" if all_prices_frozen else "STALE" if any_stale else "LIVE"
    payload["warning"] = (
        "RITHMIC FEED CRITICAL  ALL EXECUTOR PRICES FROZEN"
        if all_prices_frozen
        else "RITHMIC FEED STALE  EXECUTION ONLY MODE"
        if any_stale
        else None
    )
    return payload


def read_feed_health():
    return read_json_file(FEED_HEALTH_PATH, {"symbols": {}})


def write_feed_health(payload):
    atomic_write_json(FEED_HEALTH_PATH, payload)


def update_feed_health(symbol, field, timestamp_utc=None, force_status=None):
    normalized_symbol = str(symbol or "").upper()
    if not normalized_symbol:
        return
    if field == "last_tick_timestamp_utc":
        return
    timestamp_utc = timestamp_utc or utc_now_iso()
    payload = read_feed_health()
    symbols = payload.setdefault("symbols", {})
    for alias in build_snapshot_symbol_aliases(normalized_symbol):
        entry = symbols.setdefault(alias, {})
        previous_status = str(entry.get("feed_status") or "STALE").upper()
        entry[field] = timestamp_utc
        if field == "last_tick_timestamp_utc":
            if previous_status in {"STALE", "DEAD", "DISCONNECTED", "INVALID"}:
                entry["recovery_tick_confirmations"] = int(entry.get("recovery_tick_confirmations", 0) or 0) + 1
            else:
                entry["recovery_tick_confirmations"] = FEED_RECOVERY_TICK_CONFIRMATIONS
        if force_status:
            entry["feed_status"] = force_status
    if force_status:
        payload["updated_at_utc"] = utc_now_iso()
    else:
        refresh_feed_health_statuses(payload)
    try:
        write_feed_health(payload)
    except Exception as e:
        print(f"RITHMIC WARNING|feed_health_write_failed|{sanitize_log_message(e)}")


def mark_symbols_feed_status(symbols, status):
    payload = read_feed_health()
    entries = payload.setdefault("symbols", {})
    timestamp_utc = utc_now_iso()
    clear_tick_state = status in {"STALE", "DEAD", "DISCONNECTED"}
    for symbol in symbols:
        for alias in build_snapshot_symbol_aliases(symbol):
            entry = entries.setdefault(alias, {})
            entry["feed_status"] = status
            if clear_tick_state:
                entry["last_tick_timestamp_utc"] = None
                entry["recovery_tick_confirmations"] = 0
                entry["last_bridge_post_timestamp_utc"] = None
                entry["last_successful_executor_price_post_timestamp_utc"] = None
                entry["last_bridge_post_age_seconds"] = None
            else:
                entry.setdefault("last_tick_timestamp_utc", None)
                entry.setdefault("recovery_tick_confirmations", 0)
            entry["status_updated_at_utc"] = timestamp_utc
    payload["updated_at_utc"] = timestamp_utc
    payload["system_state_feed"] = "LIVE" if status == "LIVE" else "STALE"
    payload["warning"] = None if status == "LIVE" else "RITHMIC FEED STALE  EXECUTION ONLY MODE"
    write_feed_health(payload)


def write_atr_snapshot(symbol, atr_bar_timestamp, atr_value):
    if str(symbol).upper() not in LIVE_TICK_SYMBOLS:
        update_feed_health(symbol, "last_atr_timestamp_utc", str(atr_bar_timestamp), force_status="STALE")
        return

    snapshot_entry = {
        "atr_value": float(atr_value),
        "atr_bar_timestamp": str(atr_bar_timestamp),
        "atr_source": "rithmic_live_listener_1m14",
    }

    payload = read_json_file(ATR_SNAPSHOT_PATH, {"symbols": {}})
    symbols = payload.setdefault("symbols", {})
    for alias in build_snapshot_symbol_aliases(symbol):
        symbols[alias] = snapshot_entry.copy()

    atomic_write_json(ATR_SNAPSHOT_PATH, payload)
    update_feed_health(symbol, "last_atr_timestamp_utc", str(atr_bar_timestamp))


def clear_atr_snapshot(symbol):
    payload = read_json_file(ATR_SNAPSHOT_PATH, {"symbols": {}})
    symbols = payload.setdefault("symbols", {})
    removed = False

    for alias in build_snapshot_symbol_aliases(symbol):
        if alias in symbols:
            del symbols[alias]
            removed = True

    if removed:
        atomic_write_json(ATR_SNAPSHOT_PATH, payload)


def read_json_file(path, default):
    target_path = Path(path)
    if not target_path.exists():
        return default

    try:
        return json.loads(target_path.read_text(encoding="utf-8"))
    except Exception:
        return default


def get_feed_status(symbol):
    payload = read_feed_health()
    symbols = payload.get("symbols") if isinstance(payload, dict) else {}
    if not isinstance(symbols, dict):
        return None
    for alias in build_snapshot_symbol_aliases(symbol):
        entry = symbols.get(alias)
        if isinstance(entry, dict) and entry.get("feed_status"):
            return str(entry.get("feed_status")).upper()
    return None


def load_recent_bars():
    payload = read_json_file(RECENT_BARS_PATH, {"symbols": {}})
    loaded = {}

    for symbol, entries in payload.get("symbols", {}).items():
        bars = deque(maxlen=MAX_PERSISTED_BARS)
        for entry in entries:
            try:
                bars.append(
                    {
                        "timestamp": str(entry["timestamp"]),
                        "symbol": str(entry["symbol"]).upper(),
                        "open": float(entry["open"]),
                        "high": float(entry["high"]),
                        "low": float(entry["low"]),
                        "close": float(entry["close"]),
                    }
                )
            except Exception:
                continue

        if bars:
            loaded[str(symbol).upper()] = bars

    return loaded


def get_symbol_bar_count(bar_cache, symbol):
    return len(bar_cache.get(str(symbol).upper(), ()))


def persist_recent_bars(bar_cache):
    payload = {"symbols": {}}
    for symbol, bars in bar_cache.items():
        payload["symbols"][symbol] = list(bars)
    atomic_write_json(RECENT_BARS_PATH, payload)


def parse_key_value_field(field):
    key, value = field.split("=", 1)
    return key, float(value)


def parse_completed_bar_line(line):
    _, bar_timestamp, symbol, open_field, high_field, low_field, close_field = line.split("|", 6)
    parsed = dict(
        parse_key_value_field(field)
        for field in (open_field, high_field, low_field, close_field)
    )
    return {
        "timestamp": bar_timestamp,
        "symbol": symbol.upper(),
        "open": parsed["O"],
        "high": parsed["H"],
        "low": parsed["L"],
        "close": parsed["C"],
    }


def parse_bar_timestamp(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def get_contiguous_bar_tail(bars, max_gap_seconds=ATR_MAX_BAR_GAP_SECONDS):
    ordered_bars = list(bars)
    if not ordered_bars:
        return []

    tail = [ordered_bars[-1]]
    newer_timestamp = parse_bar_timestamp(ordered_bars[-1].get("timestamp"))

    for index in range(len(ordered_bars) - 2, -1, -1):
        older_bar = ordered_bars[index]
        older_timestamp = parse_bar_timestamp(older_bar.get("timestamp"))
        if newer_timestamp is None or older_timestamp is None:
            break

        gap_seconds = (newer_timestamp - older_timestamp).total_seconds()
        if gap_seconds <= 0 or gap_seconds > max_gap_seconds:
            break

        tail.append(older_bar)
        newer_timestamp = older_timestamp

    return list(reversed(tail))


def find_gap_before_contiguous_tail(bars, max_gap_seconds=ATR_MAX_BAR_GAP_SECONDS):
    ordered_bars = list(bars)
    tail = get_contiguous_bar_tail(ordered_bars, max_gap_seconds=max_gap_seconds)
    if not tail or len(tail) >= len(ordered_bars):
        return None

    older_bar = ordered_bars[-len(tail) - 1]
    newer_bar = tail[0]
    older_timestamp = parse_bar_timestamp(older_bar.get("timestamp"))
    newer_timestamp = parse_bar_timestamp(newer_bar.get("timestamp"))
    if older_timestamp is None or newer_timestamp is None:
        return {
            "older_timestamp": older_bar.get("timestamp"),
            "newer_timestamp": newer_bar.get("timestamp"),
            "gap_seconds": None,
        }

    return {
        "older_timestamp": older_bar.get("timestamp"),
        "newer_timestamp": newer_bar.get("timestamp"),
        "gap_seconds": (newer_timestamp - older_timestamp).total_seconds(),
    }


def build_contiguous_atr_skip_log(symbol, bars):
    tail_count = len(get_contiguous_bar_tail(bars))
    gap = find_gap_before_contiguous_tail(bars)
    if gap is None:
        return (
            f"STATUS|atr_skipped_contiguous_bars_insufficient|{symbol}|"
            f"required={ATR_SEED_BAR_COUNT}|available={tail_count}"
        )

    return (
        f"STATUS|atr_skipped_contiguous_bars_insufficient_after_gap|{symbol}|"
        f"required={ATR_SEED_BAR_COUNT}|available={tail_count}|"
        f"gap_seconds={gap['gap_seconds']}|"
        f"older={gap['older_timestamp']}|newer={gap['newer_timestamp']}"
    )


def compute_atr(bars, period=ATR_PERIOD):
    contiguous_bars = get_contiguous_bar_tail(bars)
    if len(contiguous_bars) < period + 1:
        return None

    relevant_bars = contiguous_bars[-(period + 1):]
    tr_values = []

    for index in range(1, len(relevant_bars)):
        bar = relevant_bars[index]
        prev_close = relevant_bars[index - 1]["close"]
        tr_values.append(
            max(
                bar["high"] - bar["low"],
                abs(bar["high"] - prev_close),
                abs(bar["low"] - prev_close),
            )
        )

    return sum(tr_values) / float(period)


def compute_rma_atr(bars, period=ATR_PERIOD):
    contiguous_bars = get_contiguous_bar_tail(bars)
    if len(contiguous_bars) < period + 1:
        return None

    tr_values = []
    for index in range(1, len(contiguous_bars)):
        bar = contiguous_bars[index]
        prev_close = contiguous_bars[index - 1]["close"]
        tr_values.append(
            max(
                bar["high"] - bar["low"],
                abs(bar["high"] - prev_close),
                abs(bar["low"] - prev_close),
            )
        )

    if len(tr_values) < period:
        return None

    atr_value = sum(tr_values[:period]) / float(period)
    for true_range in tr_values[period:]:
        atr_value = ((atr_value * (period - 1)) + true_range) / float(period)

    return atr_value


def find_tradingview_atr_record(symbol):
    payload = read_json_file(TRADE_MANAGER_PERSISTENCE_PATH, {})
    tradingview_atr = payload.get("tradingview_atr") if isinstance(payload, dict) else {}
    if not isinstance(tradingview_atr, dict):
        return None

    for alias in build_snapshot_symbol_aliases(symbol):
        record = tradingview_atr.get(alias)
        if isinstance(record, dict):
            return record

    return None


def build_atr_shadow_comparison(symbol, bars, feed_status=None):
    normalized_symbol = str(symbol or "").strip().upper()
    persisted_bars = list(bars or [])
    contiguous_bars = get_contiguous_bar_tail(persisted_bars)
    gap = find_gap_before_contiguous_tail(persisted_bars)
    gap_detected = gap is not None
    rithmic_atr = compute_rma_atr(persisted_bars)
    rithmic_timestamp = contiguous_bars[-1]["timestamp"] if rithmic_atr is not None and contiguous_bars else None
    tv_record = find_tradingview_atr_record(normalized_symbol)
    tv_atr = None
    tv_timestamp = None
    if tv_record is not None:
        try:
            tv_atr = float(tv_record.get("atr_value"))
        except (TypeError, ValueError):
            tv_atr = None
        tv_timestamp = tv_record.get("received_at") or tv_record.get("atr_bar_timestamp")

    delta_abs = None
    delta_pct = None
    if rithmic_atr is not None and tv_atr is not None and tv_atr > 0:
        delta_abs = abs(float(rithmic_atr) - float(tv_atr))
        delta_pct = (delta_abs / float(tv_atr)) * 100.0

    if gap_detected and len(contiguous_bars) < ATR_SEED_BAR_COUNT:
        atr_status = "GAP_INVALID"
    elif rithmic_atr is None:
        atr_status = "INSUFFICIENT_BARS"
    elif tv_atr is None:
        atr_status = "RITHMIC_ONLY_SHADOW"
    else:
        atr_status = "OK"

    return {
        "symbol": normalized_symbol,
        "timestamp": utc_now_iso(),
        "tv_atr": round(tv_atr, 6) if tv_atr is not None else None,
        "tv_atr_timestamp": tv_timestamp,
        "rithmic_atr": round(float(rithmic_atr), 6) if rithmic_atr is not None else None,
        "rithmic_atr_timestamp": rithmic_timestamp,
        "delta_abs": round(delta_abs, 6) if delta_abs is not None else None,
        "delta_pct": round(delta_pct, 6) if delta_pct is not None else None,
        "completed_bar_count": len(persisted_bars),
        "contiguous_bar_count": len(contiguous_bars),
        "gap_detected": bool(gap_detected),
        "atr_status": atr_status,
        "feed_status": feed_status,
        "source": "rithmic_worker_atr_shadow",
    }


def write_atr_shadow_comparison(symbol, comparison):
    payload = read_json_file(ATR_SHADOW_COMPARISON_PATH, {"symbols": {}})
    payload["updated_at"] = comparison["timestamp"]
    symbols = payload.setdefault("symbols", {})
    for alias in build_snapshot_symbol_aliases(symbol):
        alias_record = comparison.copy()
        alias_record["symbol"] = alias
        symbols[alias] = alias_record
    atomic_write_json(ATR_SHADOW_COMPARISON_PATH, payload)


def update_atr_shadow_comparison(symbol, bars, feed_status=None):
    comparison = build_atr_shadow_comparison(symbol, bars, feed_status=feed_status)
    write_atr_shadow_comparison(symbol, comparison)
    return comparison


def read_atr_shadow_comparison(symbol):
    payload = read_json_file(ATR_SHADOW_COMPARISON_PATH, {"symbols": {}})
    symbols = payload.get("symbols") if isinstance(payload, dict) else {}
    if not isinstance(symbols, dict):
        return None
    for alias in build_snapshot_symbol_aliases(symbol):
        record = symbols.get(alias)
        if isinstance(record, dict):
            return record
    return None


def build_atr_shadow_log_line(comparison):
    return (
        "ATR SHADOW|"
        f"symbol={comparison['symbol']}|"
        f"tv={comparison['tv_atr']}|"
        f"rithmic={comparison['rithmic_atr']}|"
        f"delta={comparison['delta_abs']}|"
        f"delta_pct={comparison['delta_pct']}|"
        f"bars={comparison['contiguous_bar_count']}|"
        f"status={comparison['atr_status']}"
    )


def build_atr_line(symbol, bar_timestamp, atr_value):
    return (
        "ATR|"
        f"{bar_timestamp}|"
        f"{symbol}|"
        f"{ATR_PERIOD}|"
        f"{atr_value}"
    )


def replace_recent_bars_for_symbol(bar_cache, symbol, bars):
    normalized_symbol = str(symbol).upper()
    deduped = {}
    for bar in bars:
        deduped[bar["timestamp"]] = {
            "timestamp": str(bar["timestamp"]),
            "symbol": normalized_symbol,
            "open": float(bar["open"]),
            "high": float(bar["high"]),
            "low": float(bar["low"]),
            "close": float(bar["close"]),
        }

    ordered_bars = [deduped[timestamp] for timestamp in sorted(deduped.keys())]
    bar_cache[normalized_symbol] = deque(ordered_bars[-MAX_PERSISTED_BARS:], maxlen=MAX_PERSISTED_BARS)
    persist_recent_bars(bar_cache)


def seed_atr_from_historical_bars(bar_cache, symbol, historical_bars):
    normalized_symbol = str(symbol).upper()
    bars = [
        {
            "timestamp": str(bar["timestamp"]),
            "symbol": normalized_symbol,
            "open": float(bar["open"]),
            "high": float(bar["high"]),
            "low": float(bar["low"]),
            "close": float(bar["close"]),
        }
        for bar in historical_bars
        if str(bar.get("symbol", "")).upper() == normalized_symbol
    ]

    if len(bars) < ATR_SEED_BAR_COUNT:
        return None

    replace_recent_bars_for_symbol(bar_cache, normalized_symbol, bars)
    restored_bars = list(bar_cache[normalized_symbol])
    atr_value = compute_atr(restored_bars)
    if atr_value is None:
        return None

    atr_bar_timestamp = restored_bars[-1]["timestamp"]
    write_atr_snapshot(normalized_symbol, atr_bar_timestamp, atr_value)
    return {
        "count": len(restored_bars),
        "bar_timestamp": atr_bar_timestamp,
        "atr_value": atr_value,
        "atr_line": build_atr_line(normalized_symbol, atr_bar_timestamp, atr_value),
    }


def seed_atr_from_persisted_bars(bar_cache, symbol):
    normalized_symbol = str(symbol).upper()
    bars = list(bar_cache.get(normalized_symbol, ()))
    bar_count = len(bars)
    log_lines = [f"STATUS|recent_bars_loaded|{normalized_symbol}|count={bar_count}"]

    if bar_count < ATR_SEED_BAR_COUNT:
        clear_atr_snapshot(normalized_symbol)
        log_lines.append(
            f"STATUS|recent_bars_insufficient|{normalized_symbol}|required={ATR_SEED_BAR_COUNT}|available={bar_count}"
        )
        return log_lines, None

    atr_value = compute_atr(bars)
    if atr_value is None:
        clear_atr_snapshot(normalized_symbol)
        log_lines.append(build_contiguous_atr_skip_log(normalized_symbol, bars))
        return log_lines, None

    atr_bar_timestamp = bars[-1]["timestamp"]
    write_atr_snapshot(normalized_symbol, atr_bar_timestamp, atr_value)
    log_lines.append(f"STATUS|recent_bars_ready|{normalized_symbol}|count={bar_count}")
    log_lines.append(f"STATUS|atr_seeded_from_persisted_bars|{normalized_symbol}|bar_timestamp={atr_bar_timestamp}")
    log_lines.append(f"STATUS|atr_seed_value|{normalized_symbol}|value={atr_value}")
    return log_lines, build_atr_line(normalized_symbol, atr_bar_timestamp, atr_value)


def update_recent_bars(bar_cache, completed_bar):
    symbol = completed_bar["symbol"]
    bars = bar_cache.setdefault(symbol, deque(maxlen=MAX_PERSISTED_BARS))

    if bars and bars[-1]["timestamp"] == completed_bar["timestamp"]:
        bars[-1] = completed_bar
    elif bars and completed_bar["timestamp"] < bars[-1]["timestamp"]:
        return None, len(bars), None
    else:
        bars.append(completed_bar)

    persist_recent_bars(bar_cache)
    persisted_count = len(bars)
    persisted_bars = list(bars)
    try:
        update_atr_shadow_comparison(
            symbol,
            persisted_bars,
            feed_status=get_feed_status(symbol),
        )
    except Exception as e:
        print(f"RITHMIC WARNING|atr_shadow_update_failed|{symbol}|{sanitize_log_message(e)}")

    atr_value = compute_atr(persisted_bars)
    if atr_value is None:
        clear_atr_snapshot(symbol)
        return None, persisted_count, build_contiguous_atr_skip_log(symbol, persisted_bars)

    write_atr_snapshot(symbol, completed_bar["timestamp"], atr_value)
    return build_atr_line(symbol, completed_bar["timestamp"], atr_value), persisted_count, None


def build_powershell_bridge():
    return textwrap.dedent(
        r"""
        param(
            [string]$DllPath,
            [string]$UserName,
            [string]$Password,
            [string]$MdConnectionPoint,
            [string]$TsConnectionPoint,
            [string]$RepositoryConnectionPoint,
            [string]$Subscriptions
        )

        $ErrorActionPreference = "Stop"

        Add-Type -Path $DllPath

        Add-Type -ReferencedAssemblies @($DllPath) -TypeDefinition @"
        using System;
        using System.Collections.Concurrent;
        using System.Collections.Generic;
        using System.Text;
        using System.Threading;
        using System.Threading.Tasks;
        using com.omnesys.omne.om;
        using com.omnesys.rapi;

        public enum BridgeLoginStatus
        {
            NotLoggedIn,
            LoginInProgress,
            LoginFailed,
            LoggedIn
        }

        public class BridgeAdmCallbacks : AdmCallbacks
        {
            public override void Alert(AlertInfo info)
            {
                var sb = new StringBuilder();
                info.Dump(sb);
                Console.WriteLine("ADM|" + sb.ToString().Replace("\r", " ").Replace("\n", " "));
            }
        }

        public class BridgeCallbacks : RCallbacks
        {
            private class TickEvent
            {
                public DateTime Timestamp;
                public string Symbol;
                public double Price;
            }

            public BridgeLoginStatus RepositoryLoginStatus = BridgeLoginStatus.NotLoggedIn;
            public bool ReceivedAgreementList = false;
            public int UnacceptedMandatoryAgreementCount = 0;
            public bool LoggedIntoMd = false;
            public bool LoggedIntoTs = false;
            public bool MarketDataClosedUnexpectedly = false;
            public bool TradingSystemClosedUnexpectedly = false;
            public bool ShutdownRequested = false;
            public bool HistoricalReplayRequested = false;
            public bool HistoricalReplayStarted = false;
            public bool HistoricalReplayTimedOut = false;
            public int HistoricalBarsReceived = 0;
            public DateTime LastHistoricalReplayEventUtc = DateTime.MinValue;
            private const int MaxTickQueueSize = """ + str(TICK_QUEUE_MAX_SIZE) + r""";
            private readonly BlockingCollection<TickEvent> TickQueue = new BlockingCollection<TickEvent>(MaxTickQueueSize);
            private readonly ConcurrentDictionary<string, TickEvent> CoalescedTicks = new ConcurrentDictionary<string, TickEvent>(StringComparer.OrdinalIgnoreCase);
            private readonly Thread TickWriterThread;
            private long QueueOverflowCount = 0;
            private long TicksCoalescedCount = 0;

            public BridgeCallbacks()
            {
                TickWriterThread = new Thread(DrainTicks);
                TickWriterThread.IsBackground = true;
                TickWriterThread.Name = "rithmic_tick_writer";
                TickWriterThread.Start();
            }

            private static DateTime BuildBarTimestamp(BarInfo info)
            {
                DateTime baseDate;
                if (!String.IsNullOrWhiteSpace(info.SpecifiedDate) &&
                    DateTime.TryParseExact(
                        info.SpecifiedDate,
                        "yyyyMMdd",
                        System.Globalization.CultureInfo.InvariantCulture,
                        System.Globalization.DateTimeStyles.AssumeUniversal | System.Globalization.DateTimeStyles.AdjustToUniversal,
                        out baseDate))
                {
                    return baseDate.Date.AddSeconds(info.StartSsboe);
                }

                return DateTimeOffset.FromUnixTimeSeconds(info.StartSsboe).UtcDateTime;
            }

            private static void PrintHistoricalBar(BarInfo info)
            {
                DateTime timestamp = BuildBarTimestamp(info);
                Console.WriteLine(
                    "HISTBAR|" +
                    timestamp.ToString("yyyy-MM-ddTHH:mm:00Z") + "|" +
                    (String.IsNullOrWhiteSpace(info.Symbol) ? String.Empty : info.Symbol.Trim().ToUpperInvariant()) + "|" +
                    "O=" + info.OpenPrice.ToString(System.Globalization.CultureInfo.InvariantCulture) + "|" +
                    "H=" + info.HighPrice.ToString(System.Globalization.CultureInfo.InvariantCulture) + "|" +
                    "L=" + info.LowPrice.ToString(System.Globalization.CultureInfo.InvariantCulture) + "|" +
                    "C=" + info.ClosePrice.ToString(System.Globalization.CultureInfo.InvariantCulture)
                );
            }

            public void FinalizeCurrentBars()
            {
                TickQueue.CompleteAdding();
                TickWriterThread.Join(1000);
            }

            public void RequestShutdown()
            {
                ShutdownRequested = true;
            }

            public void ResetHistoricalReplayState()
            {
                HistoricalReplayRequested = false;
                HistoricalReplayStarted = false;
                HistoricalReplayTimedOut = false;
                HistoricalBarsReceived = 0;
                LastHistoricalReplayEventUtc = DateTime.MinValue;
            }

            private void EnqueueTick(string symbol, double price, DateTime timestamp)
            {
                var tick = new TickEvent { Timestamp = timestamp, Symbol = symbol, Price = price };
                if (!TickQueue.TryAdd(tick))
                {
                    CoalescedTicks[symbol] = tick;
                    Interlocked.Increment(ref QueueOverflowCount);
                    Interlocked.Increment(ref TicksCoalescedCount);
                }
            }

            private void DrainTicks()
            {
                while (!TickQueue.IsCompleted)
                {
                    TickEvent tick = null;
                    try
                    {
                        if (!TickQueue.TryTake(out tick, 100))
                        {
                            FlushCoalescedTicks();
                            continue;
                        }
                    }
                    catch
                    {
                        continue;
                    }

                    PrintTick(tick);
                    if (TickQueue.Count == 0)
                    {
                        FlushCoalescedTicks();
                    }
                }
                FlushCoalescedTicks();
            }

            private void FlushCoalescedTicks()
            {
                foreach (var entry in CoalescedTicks.ToArray())
                {
                    TickEvent tick = null;
                    if (CoalescedTicks.TryRemove(entry.Key, out tick))
                    {
                        PrintTick(tick);
                    }
                }
            }

            private void PrintTick(TickEvent tick)
            {
                Console.WriteLine(
                    "TICK|" +
                    tick.Timestamp.ToString("o") + "|" +
                    tick.Symbol + "|" +
                    tick.Price.ToString(System.Globalization.CultureInfo.InvariantCulture)
                );
            }

            public override void TradePrint(TradeInfo info)
            {
                // Callback-safe only: normalize symbol/price/timestamp, enqueue TickEvent, and return.
                // Logging, network posting, file writes, ATR/bar work, feed health, and summaries run in worker loops.
                string normalizedSymbol = String.IsNullOrWhiteSpace(info.Symbol) ? String.Empty : info.Symbol.Trim().ToUpperInvariant();
                if (String.IsNullOrWhiteSpace(normalizedSymbol) || Double.IsNaN(info.Price))
                {
                    return;
                }

                EnqueueTick(normalizedSymbol, info.Price, DateTime.UtcNow);
            }

            public override void Alert(AlertInfo info)
            {
                var sb = new StringBuilder();
                info.Dump(sb);
                string alertText = sb.ToString().Replace("\r", " ").Replace("\n", " ");
                Console.WriteLine("ALERT|" + alertText);
                Console.WriteLine(
                    "STATUS|alert_summary|connection=" + info.ConnectionId.ToString() +
                    "|type=" + info.AlertType.ToString()
                );

                if (info.ConnectionId == ConnectionId.Repository)
                {
                    if (info.AlertType == AlertType.LoginComplete)
                    {
                        RepositoryLoginStatus = BridgeLoginStatus.LoggedIn;
                        Console.WriteLine("STATUS|repository_login_complete");
                    }
                    else if (info.AlertType == AlertType.LoginFailed)
                    {
                        RepositoryLoginStatus = BridgeLoginStatus.LoginFailed;
                        Console.WriteLine("STATUS|repository_login_failed");
                    }
                }

                if (info.ConnectionId == ConnectionId.MarketData &&
                    info.AlertType == AlertType.LoginComplete)
                {
                    LoggedIntoMd = true;
                    Console.WriteLine("STATUS|market_data_login_complete");
                    Console.WriteLine("STATUS|market_data_connected");
                }

                if (info.ConnectionId == ConnectionId.TradingSystem &&
                    info.AlertType == AlertType.LoginComplete)
                {
                    LoggedIntoTs = true;
                    Console.WriteLine("STATUS|trading_system_login_complete");
                    Console.WriteLine("STATUS|trading_system_connected");
                }

                if (!ShutdownRequested && alertText.IndexOf("Market Data Connection Closed", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    MarketDataClosedUnexpectedly = true;
                    Console.WriteLine("STATUS|market_data_connection_closed_unexpected");
                }

                if (!ShutdownRequested && alertText.IndexOf("Trading System Connection Closed", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    TradingSystemClosedUnexpectedly = true;
                    Console.WriteLine("STATUS|trading_system_connection_closed_unexpected");
                }
            }

            public override void AgreementList(AgreementListInfo info)
            {
                foreach (AgreementInfo agreement in info.Agreements)
                {
                    if (agreement.Mandatory && agreement.Status == "active")
                    {
                        UnacceptedMandatoryAgreementCount++;
                    }
                }

                ReceivedAgreementList = true;
                Console.WriteLine("STATUS|agreement_list_received|" + UnacceptedMandatoryAgreementCount);
            }

            public override void Bar(BarInfo info)
            {
                if (info.Type != BarType.Minute || info.SpecifiedMinutes != 1)
                {
                    return;
                }

                HistoricalReplayStarted = true;
                HistoricalBarsReceived++;
                LastHistoricalReplayEventUtc = DateTime.UtcNow;
                PrintHistoricalBar(info);
            }

            public override void BarReplay(BarReplayInfo info)
            {
                HistoricalReplayStarted = true;
                LastHistoricalReplayEventUtc = DateTime.UtcNow;
                Console.WriteLine("STATUS|historical_replay_event|rp_code=" + info.RpCode.ToString());
            }
        }

        public static class BridgeRunner
        {
            public static int Run(
                string userName,
                string password,
                string mdConnectionPoint,
                string tsConnectionPoint,
                string repositoryConnectionPoint,
                string subscriptions)
            {
                BridgeCallbacks callbacks = new BridgeCallbacks();
                REngineParams engineParams = new REngineParams();
                REngine engine = null;
                List<Tuple<string, string>> subscriptionList = new List<Tuple<string, string>>();
                Console.WriteLine("STATUS|callback_registered|BridgeCallbacks");

                engineParams.AppName = "RithmicLiveListenerPhaseA";
                engineParams.AppVersion = "1.0.0.0";
                engineParams.AdmCallbacks = new BridgeAdmCallbacks();
                engineParams.DmnSrvrAddr = "ritpz01004.01.rithmic.com:65000~ritpz04063.04.rithmic.com:65000~ritpz01004.01.rithmic.net:65000~ritpz04063.04.rithmic.net:65000~ritpz01004.01.theomne.net:65000~ritpz04063.04.theomne.net:65000~ritpz01004.01.theomne.com:65000~ritpz04063.04.theomne.com:65000";
                engineParams.DomainName = "rithmic_paper_prod_domain";
                engineParams.LicSrvrAddr = "ritpz04063.04.rithmic.com:56000~ritpz01004.01.rithmic.com:56000~ritpz04063.04.rithmic.net:56000~ritpz04063.04.theomne.net:56000~ritpz04063.04.theomne.com:56000~ritpz01000.01.rithmic.com:56000~ritpz01001.01.rithmic.com:56000~ritpz01000.01.rithmic.net:56000~ritpz01001.01.rithmic.net:56000~ritpz01000.01.theomne.net:56000~ritpz01001.01.theomne.net:56000~ritpz01000.01.theomne.com:56000~ritpz01001.01.theomne.com:56000~ritpz24050.rithmic.com:56000~ritpz24050.rithmic.net:56000~ritpz24050.theomne.net:56000~ritpz24050.theomne.com:56000~ritpz23010.rithmic.com:56000~ritpz23010.rithmic.net:56000~ritpz23010.theomne.net:56000~ritpz23010.theomne.com:56000~ritpz23011.rithmic.com:56000~ritpz23011.rithmic.net:56000~ritpz23011.theomne.net:56000~ritpz23011.theomne.com:56000~ritpz24013.rithmic.com:56000~ritpz24013.rithmic.net:56000~ritpz24013.theomne.net:56000~ritpz24013.theomne.com:56000";
                engineParams.LocBrokAddr = "ritpz04063.04.rithmic.com:64100";
                engineParams.LoggerAddr = "ritpz04063.04.rithmic.com:45454~ritpz01004.01.rithmic.com:45454~ritpz04063.04.rithmic.net:45454~ritpz01004.01.rithmic.net:45454~ritpz04063.04.theomne.net:45454~ritpz01004.01.theomne.net:45454~ritpz04063.04.theomne.com:45454~ritpz01004.01.theomne.com:45454";
                engineParams.LogFilePath = "rithmic_live_listener_phase_a.log";

                try
                {
                    int historicalSeedLookbackMinutes = """ + str(HISTORICAL_SEED_LOOKBACK_MINUTES) + r""";
                    int historicalSeedTimeoutSeconds = 10;

                    foreach (string rawSubscription in subscriptions.Split(','))
                    {
                        string subscription = rawSubscription == null ? String.Empty : rawSubscription.Trim();
                        if (String.IsNullOrWhiteSpace(subscription))
                        {
                            continue;
                        }

                        string[] parts = subscription.Split(new[] { ':' }, 2);
                        if (parts.Length != 2 ||
                            String.IsNullOrWhiteSpace(parts[0]) ||
                            String.IsNullOrWhiteSpace(parts[1]))
                        {
                            Console.WriteLine("ERROR|invalid_subscription|" + subscription);
                            return 13;
                        }

                        subscriptionList.Add(
                            Tuple.Create(
                                parts[0].Trim().ToUpperInvariant(),
                                parts[1].Trim().ToUpperInvariant()
                            )
                        );
                    }

                    if (subscriptionList.Count == 0)
                    {
                        Console.WriteLine("ERROR|missing_subscriptions");
                        return 14;
                    }

                    Console.CancelKeyPress += (sender, args) =>
                    {
                        args.Cancel = true;
                        callbacks.RequestShutdown();
                        Console.WriteLine("STATUS|manual_shutdown_requested");
                    };

                    Console.WriteLine("STATUS|creating_engine");
                    var engineTask = Task.Run(() => new REngine(engineParams));
                    if (!engineTask.Wait(TimeSpan.FromSeconds(""" + str(ENGINE_CREATION_TIMEOUT_SECONDS) + r""")))
                    {
                        Console.WriteLine("ERROR|engine_creation_timeout");
                        return 12;
                    }

                    engine = engineTask.Result;
                    Console.WriteLine("STATUS|dll_loaded");

                    callbacks.RepositoryLoginStatus = BridgeLoginStatus.LoginInProgress;
                    Console.WriteLine("STATUS|repository_login_start");
                    engine.loginRepository(
                        callbacks,
                        String.Empty,
                        userName,
                        password,
                        repositoryConnectionPoint
                    );
                    Console.WriteLine("STATUS|repository_login_call_returned");

                    DateTime repositoryLoginStartedUtc = DateTime.UtcNow;
                    while (callbacks.RepositoryLoginStatus != BridgeLoginStatus.LoggedIn &&
                           callbacks.RepositoryLoginStatus != BridgeLoginStatus.LoginFailed)
                    {
                        if (callbacks.ShutdownRequested)
                        {
                            return 0;
                        }
                        Console.WriteLine(
                            "STATUS|repository_login_wait|elapsed_seconds=" +
                            ((int)DateTime.UtcNow.Subtract(repositoryLoginStartedUtc).TotalSeconds).ToString() +
                            "|status=" + callbacks.RepositoryLoginStatus.ToString()
                        );
                        Thread.Sleep(1000);
                    }
                    Console.WriteLine("STATUS|repository_login_final_status|" + callbacks.RepositoryLoginStatus.ToString());

                    if (callbacks.RepositoryLoginStatus == BridgeLoginStatus.LoginFailed)
                    {
                        Console.WriteLine("ERROR|repository_login_failed");
                        engine.shutdown();
                        return 2;
                    }

                    Console.WriteLine("STATUS|requesting_agreements");
                    engine.listAgreements(false, null);

                    while (!callbacks.ReceivedAgreementList)
                    {
                        if (callbacks.ShutdownRequested)
                        {
                            return 0;
                        }
                        Thread.Sleep(1000);
                    }

                    if (callbacks.UnacceptedMandatoryAgreementCount > 0)
                    {
                        Console.WriteLine("ERROR|mandatory_agreements_unaccepted");
                        engine.logoutRepository();
                        engine.shutdown();
                        return 3;
                    }

                    Console.WriteLine("STATUS|repository_logout");
                    engine.logoutRepository();

                    Console.WriteLine("STATUS|market_data_login_start");
                    engine.login(
                        callbacks,
                        String.Empty,
                        userName,
                        password,
                        mdConnectionPoint,
                        Constants.DEFAULT_ENVIRONMENT_KEY,
                        userName,
                        password,
                        tsConnectionPoint,
                        String.Empty,
                        String.Empty,
                        String.Empty,
                        String.Empty,
                        String.Empty
                    );

                    while (!callbacks.LoggedIntoMd || !callbacks.LoggedIntoTs)
                    {
                        if (callbacks.ShutdownRequested)
                        {
                            return 0;
                        }
                        Thread.Sleep(1000);
                    }

                    Console.WriteLine("STATUS|phase_b_login_success");
                    foreach (var subscriptionItem in subscriptionList)
                    {
                        string exchangeCode = subscriptionItem.Item1;
                        string symbolCode = subscriptionItem.Item2;

                        callbacks.ResetHistoricalReplayState();
                        callbacks.HistoricalReplayRequested = true;
                        Console.WriteLine("STATUS|historical_replay_request_start|" + exchangeCode + "|" + symbolCode);

                        try
                        {
                            DateTime replayEnd = DateTime.UtcNow;
                            DateTime replayStart = replayEnd.AddMinutes(-historicalSeedLookbackMinutes);
                            ReplayBarParams replayParams = new ReplayBarParams();
                            replayParams.Exchange = exchangeCode;
                            replayParams.Symbol = symbolCode;
                            replayParams.Type = BarType.Minute;
                            replayParams.SpecifiedMinutes = 1;
                            replayParams.StartCcyymmdd = replayStart.ToString("yyyyMMdd");
                            replayParams.StartSsboe = (int)(replayStart - replayStart.Date).TotalSeconds;
                            replayParams.StartUsecs = 0;
                            replayParams.EndCcyymmdd = replayEnd.ToString("yyyyMMdd");
                            replayParams.EndSsboe = (int)(replayEnd - replayEnd.Date).TotalSeconds;
                            replayParams.EndUsecs = 0;
                            replayParams.Context = "historical_seed_" + symbolCode;

                            engine.replayBars(replayParams);

                            DateTime replayDeadline = DateTime.UtcNow.AddSeconds(historicalSeedTimeoutSeconds);
                            while (DateTime.UtcNow < replayDeadline)
                            {
                                if (callbacks.ShutdownRequested)
                                {
                                    return 0;
                                }

                                if (callbacks.HistoricalReplayStarted &&
                                    callbacks.LastHistoricalReplayEventUtc != DateTime.MinValue &&
                                    DateTime.UtcNow.Subtract(callbacks.LastHistoricalReplayEventUtc).TotalMilliseconds >= 1500)
                                {
                                    break;
                                }

                                Thread.Sleep(200);
                            }

                            if (callbacks.HistoricalBarsReceived > 0)
                            {
                                Console.WriteLine("STATUS|historical_replay_request_complete|" + symbolCode + "|bars_received=" + callbacks.HistoricalBarsReceived.ToString());
                            }
                            else
                            {
                                callbacks.HistoricalReplayTimedOut = true;
                                Console.WriteLine("STATUS|historical_replay_request_timeout|" + symbolCode + "|bars_received=0");
                            }
                        }
                        catch (Exception ex)
                        {
                            Console.WriteLine("STATUS|historical_replay_request_failed|" + symbolCode + "|" + ex.Message.Replace("\r", " ").Replace("\n", " "));
                        }
                    }

                    foreach (var subscriptionItem in subscriptionList)
                    {
                        string exchangeCode = subscriptionItem.Item1;
                        string symbolCode = subscriptionItem.Item2;

                        Console.WriteLine("STATUS|subscribing|" + exchangeCode + "|" + symbolCode);
                        try
                        {
                            engine.subscribe(
                                exchangeCode,
                                symbolCode,
                                SubscriptionFlags.Prints,
                                null
                            );
                            Console.WriteLine("STATUS|subscription_call_returned|" + exchangeCode + "|" + symbolCode + "|flags=Prints");
                        }
                        catch (Exception ex)
                        {
                            Console.WriteLine("ERROR|subscription_call_failed|" + exchangeCode + "|" + symbolCode + "|" + ex.Message.Replace("\r", " ").Replace("\n", " "));
                            throw;
                        }
                    }

                    Console.WriteLine("STATUS|listener_service_running");
                    DateTime lastHeartbeatUtc = DateTime.MinValue;
                    while (!callbacks.ShutdownRequested &&
                           !callbacks.MarketDataClosedUnexpectedly &&
                           !callbacks.TradingSystemClosedUnexpectedly)
                    {
                        if (lastHeartbeatUtc == DateTime.MinValue ||
                            DateTime.UtcNow.Subtract(lastHeartbeatUtc).TotalSeconds >= 5)
                        {
                            lastHeartbeatUtc = DateTime.UtcNow;
                            Console.WriteLine(
                                "STATUS|listener_heartbeat|" +
                                "md_logged_in=" + callbacks.LoggedIntoMd.ToString() +
                                "|ts_logged_in=" + callbacks.LoggedIntoTs.ToString() +
                                "|shutdown_requested=" + callbacks.ShutdownRequested.ToString() +
                                "|market_data_closed=" + callbacks.MarketDataClosedUnexpectedly.ToString() +
                                "|trading_system_closed=" + callbacks.TradingSystemClosedUnexpectedly.ToString()
                            );
                        }
                        Thread.Sleep(500);
                    }

                    callbacks.FinalizeCurrentBars();

                    if (callbacks.ShutdownRequested)
                    {
                        Console.WriteLine("STATUS|manual_shutdown");
                        return 0;
                    }

                    Console.WriteLine("STATUS|connection_closed_unexpected");
                    return 20;
                }
                catch (OMException ex)
                {
                    Console.WriteLine("ERROR|" + ex.Message.Replace("\r", " ").Replace("\n", " "));
                    return 10;
                }
                catch (Exception ex)
                {
                    Console.WriteLine("ERROR|" + ex.Message.Replace("\r", " ").Replace("\n", " "));
                    return 11;
                }
                finally
                {
                    if (engine != null)
                    {
                        try
                        {
                            engine.logout();
                        }
                        catch
                        {
                        }

                        try
                        {
                            engine.shutdown();
                        }
                        catch
                        {
                        }
                    }
                }
            }
        }
"@

        $exitCode = [BridgeRunner]::Run(
            $UserName,
            $Password,
            $MdConnectionPoint,
            $TsConnectionPoint,
            $RepositoryConnectionPoint,
            $Subscriptions
        )

        exit $exitCode
        """
    ).strip()


def write_powershell_bridge():
    RITHMIC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    POWERSHELL_BRIDGE_PATH.write_text(
        build_powershell_bridge(),
        encoding="utf-8",
    )
    return POWERSHELL_BRIDGE_PATH


def validate_env():
    missing = []
    if not RITHMIC_USER:
        missing.append("RITHMIC_USER")
    if not RITHMIC_PASSWORD:
        missing.append("RITHMIC_PASSWORD")
    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing)
        )


def build_command():
    dll_path = ensure_runtime_files()
    bridge_path = write_powershell_bridge()
    subscriptions = parse_rithmic_subscriptions()
    subscription_arg = ",".join(f"{exchange}:{symbol}" for exchange, symbol in subscriptions)

    return [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(bridge_path),
        "-DllPath",
        str(dll_path),
        "-UserName",
        RITHMIC_USER,
        "-Password",
        RITHMIC_PASSWORD,
        "-MdConnectionPoint",
        RITHMIC_MD_CONNECTION_POINT,
        "-TsConnectionPoint",
        RITHMIC_TS_CONNECTION_POINT,
        "-RepositoryConnectionPoint",
        RITHMIC_REPOSITORY_CONNECTION_POINT,
        "-Subscriptions",
        subscription_arg,
    ]


def terminate_process(process):
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def reset_dead_restart_guard(symbol):
    normalized_symbol = str(symbol).upper()
    if DEAD_RESTART_ATTEMPTS.get(normalized_symbol, 0) or normalized_symbol in DEAD_RESTART_LAST_TIMES:
        DEAD_RESTART_ATTEMPTS.pop(normalized_symbol, None)
        DEAD_RESTART_LAST_TIMES.pop(normalized_symbol, None)
        print(f"RITHMIC STATUS|dead_restart_recovered|symbol={normalized_symbol}|attempts_reset=True")


def maybe_restart_listener(symbol, health, process, reference_time=None):
    normalized_symbol = str(symbol).upper()
    status = str((health or {}).get("feed_status") or "").upper()
    if status != "DEAD":
        print(f"RITHMIC STATUS|dead_restart_skipped|symbol={normalized_symbol}|status={status}|reason=status_not_dead")
        return False

    if reference_time is None:
        reference_time = datetime.now(timezone.utc).replace(tzinfo=None)
    age_seconds = None
    try:
        age_seconds = float((health or {}).get("feed_age_seconds"))
    except (TypeError, ValueError):
        last_tick = parse_utc_timestamp((health or {}).get("last_tick_timestamp_utc"))
        if last_tick is not None:
            age_seconds = max(0.0, (reference_time - last_tick).total_seconds())

    if age_seconds is None:
        print(f"RITHMIC STATUS|dead_restart_skipped|symbol={normalized_symbol}|status={status}|reason=no_valid_tick_timestamp")
        return False

    if age_seconds <= RESTART_DEAD_THRESHOLD_SECONDS:
        print(
            "RITHMIC STATUS|dead_restart_skipped|"
            f"symbol={normalized_symbol}|status=DEAD|reason=below_threshold|age_seconds={age_seconds:.3f}"
        )
        return False

    now = time.monotonic()
    last_restart_time = DEAD_RESTART_LAST_TIMES.get(normalized_symbol)
    if last_restart_time is not None and now - last_restart_time < RESTART_COOLDOWN_SECONDS:
        remaining = RESTART_COOLDOWN_SECONDS - (now - last_restart_time)
        print(
            "RITHMIC STATUS|dead_restart_skipped|"
            f"symbol={normalized_symbol}|status=DEAD|reason=cooldown|seconds_remaining={remaining:.3f}"
        )
        return False

    attempts = DEAD_RESTART_ATTEMPTS[normalized_symbol]
    if attempts >= MAX_RESTART_ATTEMPTS:
        print(
            "RITHMIC STATUS|dead_restart_skipped|"
            f"symbol={normalized_symbol}|status=DEAD|reason=max_attempts|attempts={attempts}"
        )
        return False

    try:
        DEAD_RESTART_ATTEMPTS[normalized_symbol] = attempts + 1
        DEAD_RESTART_LAST_TIMES[normalized_symbol] = now
        print(
            "RITHMIC WARNING|dead_restart_triggered|"
            f"symbol={normalized_symbol}|age_seconds={age_seconds:.3f}|attempt={attempts + 1}"
        )
        terminate_process(process)
        return True
    except Exception as exc:
        print(f"RITHMIC ERROR|dead_restart_failed|symbol={normalized_symbol}|error={sanitize_log_message(exc)}")
        return False


def forward_price_to_executor(
    symbol,
    price,
    update_health=True,
    tick_timestamp_utc=None,
    timeout_seconds=None,
):
    timestamp_utc = utc_now_iso()
    payload = json.dumps({
        "symbol": str(symbol).upper(),
        "price": float(price),
        "tick_timestamp_utc": tick_timestamp_utc or timestamp_utc,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    internal_token = os.getenv("RANDLE_INTERNAL_TOKEN", "")
    if internal_token:
        headers["X-RANDLE-INTERNAL-TOKEN"] = internal_token
    request = urllib.request.Request(
        EXECUTOR_PRICE_URL,
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        timeout = EXECUTOR_PRICE_POST_TIMEOUT_SECONDS if timeout_seconds is None else float(timeout_seconds)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                reason = f"http_status_{response.status}"
                print(
                    "RITHMIC WARNING|executor_price_forward_failed|"
                    f"symbol={symbol}|price={price}|status={response.status}"
                )
                if update_health:
                    update_feed_health(symbol, "last_executor_price_post_failure_timestamp_utc", timestamp_utc)
                return False, reason
            else:
                if update_health:
                    update_feed_health(symbol, "last_bridge_post_timestamp_utc", timestamp_utc)
                    update_feed_health(symbol, "last_successful_executor_price_post_timestamp_utc", timestamp_utc)
                return True, None
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        reason = f"http_status_{exc.code}"
        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                reason = str(payload.get("reason") or payload.get("error") or reason)
        except Exception:
            pass
        print(
            "RITHMIC WARNING|executor_price_forward_failed|"
            f"symbol={symbol}|price={price}|status={exc.code}|reason={sanitize_log_message(reason)}"
        )
        if update_health:
            update_feed_health(symbol, "last_executor_price_post_failure_timestamp_utc", timestamp_utc)
        return False, reason
    except urllib.error.URLError as exc:
        reason = str(exc.reason if hasattr(exc, "reason") else exc)
        print(
            "RITHMIC WARNING|executor_price_forward_failed|"
            f"symbol={symbol}|price={price}|error={exc}"
        )
        if update_health:
            update_feed_health(symbol, "last_executor_price_post_failure_timestamp_utc", timestamp_utc)
        return False, reason


def parse_tick_line(line):
    _, tick_timestamp, symbol, price = line.split("|", 3)
    return {
        "timestamp": tick_timestamp,
        "symbol": str(symbol).upper(),
        "price": float(price),
    }


def update_latest_price_from_tick(tick):
    symbol = str(tick.get("symbol") or "").upper()
    if not symbol:
        return False
    timestamp = tick.get("timestamp") or utc_now_iso()
    price = float(tick["price"])
    now = time.monotonic()
    with latest_price_lock:
        latest_price_by_symbol[symbol] = price
        latest_tick_time_by_symbol[symbol] = timestamp
        latest_tick_monotonic_by_symbol[symbol] = now
        latest_dirty_by_symbol.add(symbol)
        raw_callback_count[symbol] += 1
    LIVE_TICK_SYMBOLS.add(symbol)
    return True


class PricePublisher:
    def __init__(self, subscribed_symbols=None):
        self.subscribed_symbols = [str(symbol or "").upper() for symbol in (subscribed_symbols or []) if symbol]
        self.stop_event = threading.Event()
        self.thread = None
        self.post_failures = defaultdict(int)
        self.last_publish_times = {}
        self.last_latency_log_times = {}
        self.executor_publish_latency_ms = {}
        self.last_post_failure_reasons = {}

    def start(self):
        self.thread = threading.Thread(target=self.run, name="rithmic_price_publisher", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=2)

    def run(self):
        next_publish_time = time.monotonic() + PRICE_POST_MIN_INTERVAL_SECONDS
        while not self.stop_event.is_set():
            wait_seconds = max(0.0, next_publish_time - time.monotonic())
            if self.stop_event.wait(wait_seconds):
                break
            now = time.monotonic()
            if now - next_publish_time >= PRICE_POST_MIN_INTERVAL_SECONDS:
                next_publish_time = now + PRICE_POST_MIN_INTERVAL_SECONDS
                continue
            self.publish_once()
            next_publish_time += PRICE_POST_MIN_INTERVAL_SECONDS
            if time.monotonic() >= next_publish_time:
                next_publish_time = time.monotonic() + PRICE_POST_MIN_INTERVAL_SECONDS

    def publish_once(self):
        with latest_price_lock:
            candidates = []
            for symbol in sorted(set(self.subscribed_symbols) | set(latest_dirty_by_symbol)):
                tick_timestamp = latest_tick_time_by_symbol.get(symbol)
                if not tick_timestamp:
                    continue
                if latest_published_tick_time_by_symbol.get(symbol) == tick_timestamp:
                    continue
                candidates.append((symbol, latest_price_by_symbol.get(symbol), tick_timestamp))

        for symbol, price, tick_timestamp in candidates:
            if price is None:
                continue
            started = time.monotonic()
            timestamp_utc = utc_now_iso()
            try:
                result = forward_price_to_executor(
                    symbol,
                    price,
                    update_health=False,
                    tick_timestamp_utc=tick_timestamp,
                    timeout_seconds=EXECUTOR_PRICE_POST_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                result = False, sanitize_log_message(exc)
            latency_ms = round((time.monotonic() - started) * 1000.0, 3)
            ok, reason = (True, None) if result is None else result
            self.executor_publish_latency_ms[symbol] = latency_ms
            now = time.monotonic()
            if now - self.last_latency_log_times.get(symbol, 0.0) >= 1.0:
                print(f"PUBLISH_LATENCY|{symbol}|{latency_ms}")
                self.last_latency_log_times[symbol] = now

            if ok:
                with latest_price_lock:
                    latest_published_tick_time_by_symbol[symbol] = tick_timestamp
                    latest_dirty_by_symbol.discard(symbol)
                print(f"PRICE|{symbol}|{price}|ts={timestamp_utc}")
                update_feed_health(symbol, "latest_price", float(price))
                update_feed_health(symbol, "latest_listener_price", float(price))
                update_feed_health(symbol, "last_listener_price_timestamp_utc", tick_timestamp)
                update_feed_health(symbol, "last_bridge_post_timestamp_utc", timestamp_utc)
                try:
                    update_feed_health(symbol, "last_executor_publish_at", timestamp_utc)
                except Exception as e:
                    print(f"RITHMIC WARNING|feed_health_update_failed|{sanitize_log_message(e)}")
                update_feed_health(symbol, "last_successful_executor_price_post_timestamp_utc", timestamp_utc)
                update_feed_health(symbol, "executor_publish_latency_ms", latency_ms)
                continue

            self.post_failures[symbol] += 1
            self.last_post_failure_reasons[symbol] = reason
            update_feed_health(symbol, "last_executor_price_post_failure_timestamp_utc", timestamp_utc)
            update_feed_health(symbol, "last_executor_price_post_failure_reason", reason)
            update_feed_health(symbol, "executor_price_post_failure_count", self.post_failures[symbol])
            update_feed_health(symbol, "executor_publish_latency_ms", latency_ms)


def minute_timestamp_from_tick(tick_timestamp):
    parsed = parse_utc_timestamp(tick_timestamp)
    if parsed is None:
        parsed = datetime.now(timezone.utc).replace(tzinfo=None)
    minute = parsed.replace(second=0, microsecond=0)
    return minute.isoformat() + "Z"


class TickWorker:
    def __init__(self, bar_cache, subscribed_symbols=None):
        self.bar_cache = bar_cache
        self.subscribed_symbols = [str(symbol or "").upper() for symbol in (subscribed_symbols or []) if symbol]
        self.events = queue.Queue(maxsize=TICK_QUEUE_MAX_SIZE)
        self.stop_event = threading.Event()
        self.thread = None
        self.latest_overflow_ticks = {}
        self.latest_prices = {}
        self.current_tick_bars = {}
        self.last_feed_health_flush_time = 0.0
        self.last_summary_time = 0.0
        self.pending_feed_health = {}
        self.ticks_processed = defaultdict(int)
        self.ticks_dropped = defaultdict(int)
        self.queue_overflow_count = defaultdict(int)
        self.ticks_coalesced_count = defaultdict(int)
        self.executor_price_post_failures = defaultdict(int)
        self.last_executor_price_post_failures = {}
        self.last_tick_timestamps = {}

    def start(self):
        self.thread = threading.Thread(target=self.run, name="rithmic_tick_worker", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=5)
        self.flush_feed_health(force=True)

    def enqueue_tick(self, tick):
        symbol = str(tick.get("symbol") or "").upper()
        if not symbol:
            return False
        tick["symbol"] = symbol
        LIVE_TICK_SYMBOLS.add(symbol)
        self.last_tick_timestamps[symbol] = tick.get("timestamp")
        return self.enqueue_event({"type": "tick", "tick": tick})

    def enqueue_completed_bar(self, completed_bar):
        return self.enqueue_event({"type": "bar", "bar": completed_bar})

    def enqueue_event(self, event):
        try:
            self.events.put_nowait(event)
            return True
        except queue.Full:
            if event.get("type") == "tick":
                tick = event["tick"]
                self.latest_overflow_ticks[tick["symbol"]] = tick
                self.ticks_dropped[tick["symbol"]] += 1
                self.queue_overflow_count[tick["symbol"]] += 1
                self.ticks_coalesced_count[tick["symbol"]] += 1
                return False

            for _ in range(100):
                try:
                    dropped = self.events.get_nowait()
                    if dropped.get("type") == "tick":
                        self.ticks_dropped[dropped["tick"]["symbol"]] += 1
                except queue.Empty:
                    break
                try:
                    self.events.put_nowait(event)
                    return True
                except queue.Full:
                    continue
            return False

    def run(self):
        while not self.stop_event.is_set():
            try:
                event = self.events.get(timeout=0.1)
            except queue.Empty:
                self.process_overflow_ticks()
                try:
                    self.flush_feed_health_if_due()
                except Exception as e:
                    print(f"RITHMIC WARNING|feed_health_flush_failed|{sanitize_log_message(e)}")
                self.print_summary_if_due()
                continue

            try:
                if event.get("type") == "tick":
                    self.process_tick(event["tick"])
                elif event.get("type") == "bar":
                    self.process_completed_bar(event["bar"], source="rithmic_bar")
            except Exception as exc:
                print(f"RITHMIC ERROR|tick_worker_processing_failed|{sanitize_log_message(exc)}")
            finally:
                self.events.task_done()

            if self.events.empty():
                self.process_overflow_ticks()
            try:
                self.flush_feed_health_if_due()
            except Exception as e:
                print(f"RITHMIC WARNING|feed_health_flush_failed|{sanitize_log_message(e)}")
            self.print_summary_if_due()

    def process_overflow_ticks(self):
        if not self.latest_overflow_ticks:
            return
        overflow = list(self.latest_overflow_ticks.values())
        self.latest_overflow_ticks.clear()
        for tick in overflow:
            self.process_tick(tick)

    def process_tick(self, tick):
        symbol = tick["symbol"]
        price = float(tick["price"])
        timestamp = tick["timestamp"]
        LIVE_TICK_SYMBOLS.add(symbol)
        price_ok, price_reason = validate_tick_price_sanity(symbol, price, self.latest_prices.get(symbol))
        if not price_ok:
            print(
                "RITHMIC CRITICAL|INVALID_PRICE|"
                f"symbol={symbol}|price={price}|previous={self.latest_prices.get(symbol)}|reason={price_reason}"
            )
            self.queue_feed_health(symbol, "last_invalid_price_timestamp_utc", timestamp)
            self.queue_feed_health(symbol, "price_sanity_status", "INVALID_PRICE")
            self.queue_feed_health(symbol, "price_sanity_reason", price_reason)
            self.queue_feed_health(symbol, "feed_status", "INVALID")
            return
        tick_count = self.ticks_processed[symbol] + 1
        self.queue_feed_health(symbol, "price_sanity_status", "OK")
        self.queue_feed_health(symbol, "price_sanity_reason", None)
        self.latest_prices[symbol] = price
        self.ticks_processed[symbol] = tick_count
        self.last_tick_timestamps[symbol] = timestamp
        reset_dead_restart_guard(symbol)
        self.queue_feed_health(symbol, "last_tick_timestamp_utc", timestamp)
        completed_bar = self.update_tick_bar(symbol, timestamp, price)
        if completed_bar is not None:
            self.process_completed_bar(completed_bar, source="tick_derived")

    def update_tick_bar(self, symbol, tick_timestamp, price):
        minute_timestamp = minute_timestamp_from_tick(tick_timestamp)
        current = self.current_tick_bars.get(symbol)
        if current is None:
            self.current_tick_bars[symbol] = {
                "timestamp": minute_timestamp,
                "symbol": symbol,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
            }
            return None

        if current["timestamp"] != minute_timestamp:
            completed = current
            self.current_tick_bars[symbol] = {
                "timestamp": minute_timestamp,
                "symbol": symbol,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
            }
            return completed

        current["high"] = max(current["high"], price)
        current["low"] = min(current["low"], price)
        current["close"] = price
        return None

    def process_completed_bar(self, completed_bar, source):
        symbol = completed_bar["symbol"]
        self.queue_feed_health(symbol, "last_bar_timestamp_utc", completed_bar["timestamp"])
        print(
            "RITHMIC STATUS|completed_1m_bar|"
            f"{completed_bar['timestamp']}|{symbol}|source={source}"
        )
        atr_line, persisted_count, atr_skip_log = update_recent_bars(self.bar_cache, completed_bar)
        print("RITHMIC STATUS|recent_bars_persisted|" f"{symbol}|count={persisted_count}")
        atr_shadow_comparison = read_atr_shadow_comparison(symbol)
        if atr_shadow_comparison is not None:
            print(f"RITHMIC {build_atr_shadow_log_line(atr_shadow_comparison)}")
        if atr_line is not None:
            print(f"RITHMIC {atr_line}")
            print("RITHMIC STATUS|atr_published|" f"{completed_bar['timestamp']}|{symbol}")
        elif atr_skip_log is not None:
            print(f"RITHMIC {atr_skip_log}")

    def queue_feed_health(self, symbol, field, timestamp_utc):
        fields = self.pending_feed_health.setdefault(str(symbol).upper(), {})
        fields[field] = timestamp_utc

    def flush_feed_health_if_due(self):
        now = time.monotonic()
        if now - self.last_feed_health_flush_time >= FEED_HEALTH_WRITE_MIN_INTERVAL_SECONDS:
            self.flush_feed_health()

    def flush_feed_health(self, force=False):
        now = time.monotonic()
        if not force and now - self.last_feed_health_flush_time < FEED_HEALTH_WRITE_MIN_INTERVAL_SECONDS:
            return
        payload = read_feed_health()
        symbols = payload.setdefault("symbols", {})
        pending = self.pending_feed_health
        self.pending_feed_health = {}
        for symbol, fields in pending.items():
            for alias in build_snapshot_symbol_aliases(symbol):
                entry = symbols.setdefault(alias, {})
                previous_status = str(entry.get("feed_status") or "STALE").upper()
                for field, timestamp_utc in fields.items():
                    entry[field] = timestamp_utc
                    if field == "last_tick_timestamp_utc":
                        if previous_status in {"STALE", "DEAD", "DISCONNECTED", "INVALID"}:
                            entry["recovery_tick_confirmations"] = int(entry.get("recovery_tick_confirmations", 0) or 0) + 1
                        else:
                            entry["recovery_tick_confirmations"] = FEED_RECOVERY_TICK_CONFIRMATIONS
        refresh_feed_health_statuses(payload)
        try:
            write_feed_health(payload)
        except Exception as e:
            print(f"RITHMIC WARNING|feed_health_write_failed|{sanitize_log_message(e)}")
        self.last_feed_health_flush_time = now

    def print_summary_if_due(self):
        now = time.monotonic()
        if now - self.last_summary_time < LISTENER_SUMMARY_HEARTBEAT_SECONDS:
            return
        self.last_summary_time = now
        payload = refresh_feed_health_statuses(read_feed_health())
        symbols = sorted(set(self.subscribed_symbols) | set(self.ticks_processed) | set(self.last_tick_timestamps))
        for symbol in symbols:
            entry = payload.get("symbols", {}).get(symbol, {})
            print(
                "RITHMIC SUMMARY|"
                f"symbol={symbol}|ticks_processed={self.ticks_processed[symbol]}|"
                f"ticks_dropped={self.ticks_dropped[symbol]}|queue_depth={self.events.qsize()}|"
                f"queue_overflow_count={self.queue_overflow_count[symbol]}|"
                f"ticks_coalesced_count={self.ticks_coalesced_count[symbol]}|"
                f"last_tick={self.last_tick_timestamps.get(symbol)}|"
                f"feed_status={entry.get('feed_status', 'STALE')}|"
                f"last_bridge_post={entry.get('last_bridge_post_timestamp_utc')}|"
                f"bridge_post_age={entry.get('last_bridge_post_age_seconds')}|"
                f"post_failures={self.executor_price_post_failures[symbol]}|"
                f"last_post_failure={self.last_executor_price_post_failures.get(symbol)}"
            )
        if payload.get("critical_status") == "all_prices_frozen":
            print(
                "RITHMIC CRITICAL|all_prices_frozen|"
                f"threshold_seconds={payload.get('all_prices_frozen_threshold_seconds')}|"
                f"symbols={','.join(symbols)}"
            )


def start_disconnect_watchdog(process, subscribed_symbols, enabled_event):
    stop_event = threading.Event()

    def watch():
        last_status_log = 0.0
        while not stop_event.wait(1.0):
            if process.poll() is not None:
                return
            if not enabled_event.is_set():
                continue
            payload = refresh_feed_health_statuses(read_feed_health())
            entries = payload.get("symbols", {})
            now = time.monotonic()
            if payload.get("critical_status") == "all_prices_frozen":
                print(
                    "RITHMIC STATUS|dead_restart_skipped|"
                    f"symbols={','.join(subscribed_symbols)}|"
                    "reason=all_prices_frozen_status_not_dead"
                )
            tracked = [
                entries.get(symbol, {})
                for symbol in subscribed_symbols
                if entries.get(symbol, {}).get("last_tick_timestamp_utc")
            ]
            if not tracked:
                if now - last_status_log >= LISTENER_SUMMARY_HEARTBEAT_SECONDS:
                    last_status_log = now
                    print(
                        "RITHMIC WATCHDOG|waiting_for_first_tick|"
                        f"symbols={','.join(subscribed_symbols)}|"
                        f"process_alive={process.poll() is None}|"
                        "reason=no_last_tick_timestamp"
                    )
                continue
            disconnected = [
                symbol for symbol in subscribed_symbols
                if entries.get(symbol, {}).get("feed_status") in {"DEAD", "DISCONNECTED"}
            ]
            stale = [
                symbol for symbol in subscribed_symbols
                if entries.get(symbol, {}).get("feed_status") == "STALE"
            ]
            frozen_bridge = [
                symbol for symbol in subscribed_symbols
                if entries.get(symbol, {}).get("price_bridge_status") == "FROZEN"
            ]
            if now - last_status_log >= LISTENER_SUMMARY_HEARTBEAT_SECONDS:
                last_status_log = now
                print(
                    "RITHMIC WATCHDOG|status|"
                    f"process_alive={process.poll() is None}|"
                    f"tracked={len(tracked)}|"
                    f"stale={','.join(stale)}|"
                    f"disconnected={','.join(disconnected)}|"
                    f"frozen_bridge={','.join(frozen_bridge)}"
                )
            for symbol in subscribed_symbols:
                entry = entries.get(symbol, {})
                if maybe_restart_listener(symbol, entry, process):
                    return
    thread = threading.Thread(target=watch, name="rithmic_disconnect_watchdog", daemon=True)
    thread.start()
    return stop_event, thread


def main():
    validate_env()
    command = build_command()
    subscriptions = parse_rithmic_subscriptions()
    bar_cache = load_recent_bars()
    persisted_bar_count = sum(len(bars) for bars in bar_cache.values())
    subscribed_symbols = [symbol.upper() for _, symbol in subscriptions]
    LIVE_TICK_SYMBOLS.clear()
    mark_symbols_feed_status(subscribed_symbols, "STALE")
    tick_worker = TickWorker(bar_cache, subscribed_symbols=subscribed_symbols)
    tick_worker.start()
    price_publisher = PricePublisher(subscribed_symbols=subscribed_symbols)
    price_publisher.start()
    reconnect_attempt = 0

    print("RITHMIC STATUS|startup_begin")
    print(f"RITHMIC STATUS|dll_path|{RAPIPLUS_DLL_PATH}")
    print(f"RITHMIC STATUS|md_connection_point|{RITHMIC_MD_CONNECTION_POINT}")
    print(f"RITHMIC STATUS|ts_connection_point|{RITHMIC_TS_CONNECTION_POINT}")
    for exchange_code, symbol_code in subscriptions:
        print(f"RITHMIC STATUS|subscribed_symbol|{exchange_code}|{symbol_code}")
    print(f"RITHMIC STATUS|executor_price_bridge|{EXECUTOR_PRICE_URL}")
    print(f"RITHMIC STATUS|atr_seed_bars_loaded_total|{persisted_bar_count}")

    try:
        while True:
            if reconnect_attempt > 0:
                print(f"RITHMIC STATUS|reconnect_attempt|{reconnect_attempt}")
                LIVE_TICK_SYMBOLS.clear()
                mark_symbols_feed_status(subscribed_symbols, "STALE")

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                cwd=str(RITHMIC_RUNTIME_DIR),
            )

            assert process.stdout is not None
            watchdog_enabled = threading.Event()
            watchdog_stop, watchdog_thread = start_disconnect_watchdog(process, subscribed_symbols, watchdog_enabled)
            manual_shutdown_seen = False
            reconnect_success_logged = False
            service_running_seen = False
            historical_seed_bars = {symbol: [] for symbol in subscribed_symbols}
            historical_fallback_reason = {
                symbol: "historical_replay_unavailable"
                for symbol in subscribed_symbols
            }

            try:
                for raw_line in process.stdout:
                    line = raw_line.strip()
                    if not line:
                        continue

                    safe_line = sanitize_log_message(line)
                    if LOG_RAW_TICKS or not line.startswith("TICK|"):
                        print(f"RITHMIC {safe_line}")

                    if line == "STATUS|manual_shutdown":
                        manual_shutdown_seen = True

                    if (
                        reconnect_attempt > 0
                        and not reconnect_success_logged
                        and line == "STATUS|listener_service_running"
                    ):
                        print("RITHMIC STATUS|reconnect_success")
                        reconnect_success_logged = True

                    if line == "STATUS|listener_service_running":
                        service_running_seen = True
                        print(
                            "RITHMIC STATUS|bridge_process_alive_after_subscription|"
                            f"alive={process.poll() is None}"
                        )
                        watchdog_enabled.set()
                        for subscribed_symbol in subscribed_symbols:
                            historical_seed = seed_atr_from_historical_bars(
                                bar_cache,
                                subscribed_symbol,
                                historical_seed_bars.get(subscribed_symbol, []),
                            )
                            if historical_seed is not None:
                                print(
                                    "RITHMIC STATUS|historical_bars_loaded|"
                                    f"{subscribed_symbol}|count={historical_seed['count']}"
                                )
                                print(
                                    "RITHMIC STATUS|atr_seeded_from_historical_bars|"
                                    f"{subscribed_symbol}|bar_timestamp={historical_seed['bar_timestamp']}"
                                )
                                print(
                                    "RITHMIC STATUS|atr_seed_value|"
                                    f"{subscribed_symbol}|value={historical_seed['atr_value']}"
                                )
                                print(f"RITHMIC {historical_seed['atr_line']}")
                                continue

                            if (
                                len(historical_seed_bars.get(subscribed_symbol, [])) > 0
                                and len(historical_seed_bars.get(subscribed_symbol, [])) < ATR_SEED_BAR_COUNT
                            ):
                                historical_fallback_reason[subscribed_symbol] = (
                                    f"historical_replay_insufficient_{len(historical_seed_bars[subscribed_symbol])}"
                                )

                            print(
                                "RITHMIC STATUS|fallback_to_persisted_bars|"
                                f"{subscribed_symbol}|reason={historical_fallback_reason[subscribed_symbol]}"
                            )
                            seed_logs, atr_line = seed_atr_from_persisted_bars(bar_cache, subscribed_symbol)
                            for seed_log in seed_logs:
                                print(f"RITHMIC {seed_log}")
                            if atr_line is not None:
                                print(f"RITHMIC {atr_line}")

                    if line.startswith("HISTBAR|"):
                        try:
                            completed_bar = parse_completed_bar_line(line.replace("HISTBAR|", "BAR|", 1))
                            historical_seed_bars.setdefault(completed_bar["symbol"], []).append(completed_bar)
                        except Exception as exc:
                            print(f"RITHMIC ERROR|historical_bar_processing_failed|{sanitize_log_message(exc)}")
                        continue

                    if line.startswith("STATUS|historical_replay_request_failed|"):
                        parts = line.split("|", 3)
                        if len(parts) >= 3:
                            historical_fallback_reason[parts[2].upper()] = "historical_replay_failed"
                    elif line.startswith("STATUS|historical_replay_request_timeout|"):
                        parts = line.split("|", 3)
                        if len(parts) >= 3:
                            historical_fallback_reason[parts[2].upper()] = "historical_replay_timeout"
                    elif line.startswith("STATUS|historical_replay_request_complete|"):
                        parts = line.split("|", 3)
                        symbol = parts[2].upper() if len(parts) >= 3 else ""
                        try:
                            bar_count = int(line.rsplit("=", 1)[1])
                        except Exception:
                            bar_count = 0
                        if symbol and bar_count < ATR_SEED_BAR_COUNT:
                            historical_fallback_reason[symbol] = f"historical_replay_insufficient_{bar_count}"

                    if line.startswith("TICK|"):
                        try:
                            watchdog_enabled.set()
                            tick = parse_tick_line(line)
                            update_latest_price_from_tick(tick)
                            tick_worker.enqueue_tick(tick)
                        except Exception as exc:
                            print(
                                "RITHMIC WARNING|tick_enqueue_failed|"
                                f"line={safe_line}|error={sanitize_log_message(exc)}"
                            )
                        continue

                    if line.startswith("BAR|"):
                        try:
                            tick_worker.enqueue_completed_bar(parse_completed_bar_line(line))
                        except Exception as exc:
                            print(f"RITHMIC ERROR|bar_enqueue_failed|{sanitize_log_message(exc)}")
                        continue
            except KeyboardInterrupt:
                print("RITHMIC STATUS|manual_shutdown")
                terminate_process(process)
                return
            finally:
                watchdog_stop.set()
                watchdog_thread.join(timeout=2)

            return_code = process.wait()
            if manual_shutdown_seen:
                print("RITHMIC STATUS|manual_shutdown")
                return

            if not service_running_seen:
                for subscribed_symbol in subscribed_symbols:
                    current_bar_count = get_symbol_bar_count(bar_cache, subscribed_symbol)
                    print(f"RITHMIC STATUS|recent_bars_loaded|{subscribed_symbol}|count={current_bar_count}")
                    if current_bar_count < ATR_SEED_BAR_COUNT:
                        print(
                            "RITHMIC STATUS|recent_bars_insufficient|"
                            f"{subscribed_symbol}|required={ATR_SEED_BAR_COUNT}|available={current_bar_count}"
                        )

            reconnect_attempt += 1

            if return_code == 0:
                print("RITHMIC STATUS|bridge_stopped")
            else:
                print(f"RITHMIC STATUS|bridge_exit_code|{return_code}")

            delay_seconds = min(
                RECONNECT_BASE_DELAY_SECONDS * (2 ** max(reconnect_attempt - 1, 0)),
                RECONNECT_MAX_DELAY_SECONDS,
            )
            print(f"RITHMIC STATUS|reconnect_backoff|attempt={reconnect_attempt}|delay_seconds={delay_seconds}")
            time.sleep(delay_seconds)
    finally:
        price_publisher.stop()
        tick_worker.stop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("RITHMIC STATUS|manual_shutdown")
    except Exception as exc:
        print(f"RITHMIC listener failed: {sanitize_log_message(exc)}")
        sys.exit(1)
