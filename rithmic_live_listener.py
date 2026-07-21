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
import urllib.parse
import urllib.request
import hashlib
import copy
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from data_paths import (
    data_path,
    directory_is_writable,
    feed_health_data_path,
    get_data_root,
    get_local_runtime_data_root,
    log_active_data_root,
)
from symbol_resolution import (
    canonicalize_symbol_input,
    get_default_listener_subscriptions,
    normalize_symbol_root,
)


BASE_DIR = Path(__file__).resolve().parent


def resolve_local_durable_runtime_root():
    configured_root = str(os.getenv("RITHMIC_LOCAL_DURABLE_ROOT", "") or "").strip()
    if configured_root:
        candidate = Path(configured_root).expanduser()
    elif os.name == "nt":
        candidate = Path.home() / "AppData" / "Local" / "RandleRuntimeData"
    else:
        candidate = get_local_runtime_data_root()

    synchronized_markers = {"onedrive", "dropbox", "google drive", "icloud drive"}
    if any(
        marker in part.strip().lower()
        for part in candidate.parts
        for marker in synchronized_markers
    ):
        raise ValueError("local_durable_runtime_root_must_not_be_synchronized")
    if directory_is_writable(candidate):
        return candidate.resolve()
    return get_local_runtime_data_root()


RITHMIC_ZIP_PATH = BASE_DIR / "Rithmic API" / "RApiPlus.NET.13.7.0.0.zip"
RITHMIC_CACHE_DIR = Path(tempfile.gettempdir()) / "rithmic_phase_a"
RITHMIC_RUNTIME_DIR = RITHMIC_CACHE_DIR / "runtime"
RAPIPLUS_DLL_PATH = RITHMIC_RUNTIME_DIR / "rapiplus.dll"
POWERSHELL_BRIDGE_PATH = RITHMIC_CACHE_DIR / "rithmic_phase_a_login.ps1"
ENGINE_CREATION_TIMEOUT_SECONDS = 20
RITHMIC_LOGIN_TIMEOUT_SECONDS = int(os.getenv("RITHMIC_LOGIN_TIMEOUT_SECONDS", "45") or "45")
RITHMIC_DIAGNOSTIC_DURATION_SECONDS = int(os.getenv("RITHMIC_DIAGNOSTIC_DURATION_SECONDS", "0") or "0")
RITHMIC_DIAGNOSTIC_ONESHOT = os.getenv("RITHMIC_DIAGNOSTIC_ONESHOT", "0").strip().lower() in {"1", "true", "yes", "on"}
DEFAULT_RITHMIC_SUBSCRIPTIONS = tuple(get_default_listener_subscriptions())
RITHMIC_SUBSCRIPTIONS_ENV = "RITHMIC_LIVE_SUBSCRIPTIONS"
RITHMIC_SECONDARY_DIAGNOSTIC_SUBSCRIPTION_ENV = "RITHMIC_RTY_DIAGNOSTIC_SUBSCRIPTION"
LISTENER_AUTHORITY_MUTEX_NAME = os.getenv(
    "RITHMIC_LISTENER_AUTHORITY_MUTEX_NAME",
    r"Local\RandleSystem_RithmicLiveListener_Authority_v1",
).strip() or r"Local\RandleSystem_RithmicLiveListener_Authority_v1"
ACTIVE_LIVE_MARKET_ROOTS = frozenset({"NQ", "YM"})
RETIRED_LIVE_MARKET_ROOTS = frozenset({"RTY"})
DATA_ROOT = get_data_root()
LOCAL_RUNTIME_DATA_ROOT = resolve_local_durable_runtime_root()
ATR_SNAPSHOT_PATH = data_path("rithmic_atr_snapshot.json")
RECENT_BARS_PATH = data_path("rithmic_recent_bars.json")
FEED_HEALTH_PATH = feed_health_data_path()
FEED_HEALTH_TRANSITIONS_PATH = data_path("rithmic_feed_health_transitions.jsonl")
ATR_SHADOW_COMPARISON_PATH = data_path("rithmic_atr_shadow_comparison.json")
TRADE_MANAGER_PERSISTENCE_PATH = data_path("persistence_state.json")
MAX_PERSISTED_BARS = 30
ATR_PERIOD = 14
ATR_SEED_BAR_COUNT = ATR_PERIOD + 1
ATR_MAX_BAR_GAP_SECONDS = 60
SESSION_BAR_ROOTS = {"YM", "NQ", "RTY"}
SESSION_BAR_TIMEZONE = ZoneInfo("America/Los_Angeles")
RAW_TICK_ROOT = data_path("rithmic_ticks")
DATA_AUTHORITY_INCIDENTS_PATH = data_path("rithmic_data_authority_incidents.jsonl")
BAR_PUBLICATION_LATENCY_PATH = data_path("rithmic_bar_publication_latency.jsonl")
ATR_TRANSITION_LATENCY_PATH = data_path("rithmic_atr_transition_latency.jsonl")
PRICE_DELIVERY_FAILURES_PATH = data_path("rithmic_price_delivery_failures.jsonl")
LOCAL_FINALIZED_BAR_JOURNAL_PATH = (
    LOCAL_RUNTIME_DATA_ROOT / "rithmic_authoritative" / "finalized_bars.jsonl"
)
# The canonical ATR record is nested in the exact finalized-bar object, so one
# fsync commits both identities without a second hot-path disk flush.
LOCAL_ATR_AUTHORITY_JOURNAL_PATH = LOCAL_FINALIZED_BAR_JOURNAL_PATH
BAR_BUILDER_CONTRACT_VERSION = "exchange_time_v1"
ATR_FORMULA = "wilder_rma_14"
ATR_FORMULA_VERSION = "wilder_rma_14_v1"
ATR_AUTHORITY_SOURCE = "rithmic_exchange_time_rma14"
RITHMIC_TIMESTAMP_POLICY = "TradeInfo.SourceSsboe+SourceNsecs/SourceUsecs"
NANOSECONDS_PER_SECOND = 1_000_000_000
NANOSECONDS_PER_MINUTE = 60 * NANOSECONDS_PER_SECOND
ATOMIC_REPLACE_IMMEDIATE_ATTEMPTS = 32
ACTIVITY_ACTIVE_SECONDS = float(os.getenv("RITHMIC_ACTIVITY_ACTIVE_SECONDS", "15.0") or "15.0")
FEED_STALE_SECONDS = float(os.getenv("RITHMIC_FEED_STALE_SECONDS", "30.0") or "30.0")
FEED_DEAD_SECONDS = float(os.getenv("RITHMIC_FEED_DEAD_SECONDS", "90.0") or "90.0")
FEED_TIMESTAMP_FUTURE_TOLERANCE_SECONDS = float(
    os.getenv("RITHMIC_FEED_TIMESTAMP_FUTURE_TOLERANCE_SECONDS", "2.0") or "2.0"
)
# Compatibility aliases remain in the payload for older diagnostic readers. Phase 1
# uses one threshold set for every root and never emits QUIET as a feed status.
FEED_QUIET_SECONDS_BY_ROOT = {root: ACTIVITY_ACTIVE_SECONDS for root in ("NQ", "YM", "RTY")}
FEED_STALE_SECONDS_BY_ROOT = {root: FEED_STALE_SECONDS for root in ("NQ", "YM", "RTY")}
FEED_DISCONNECTED_SECONDS_BY_ROOT = {root: FEED_DEAD_SECONDS for root in ("NQ", "YM", "RTY")}
FEED_RECOVERY_TICK_CONFIRMATIONS = int(os.getenv("RITHMIC_FEED_RECOVERY_TICK_CONFIRMATIONS", "2") or "2")
FEED_QUIET_SECONDS = ACTIVITY_ACTIVE_SECONDS
FEED_DISCONNECTED_SECONDS = FEED_DEAD_SECONDS
ALL_PRICES_FROZEN_SECONDS = float(os.getenv("RITHMIC_ALL_PRICES_FROZEN_SECONDS", "10.0") or "10.0")
PRICE_SANITY_MAX_MOVE_BY_ROOT = {
    "NQ": float(os.getenv("RITHMIC_NQ_PRICE_SANITY_MAX_MOVE", "250.0") or "250.0"),
    "YM": float(os.getenv("RITHMIC_YM_PRICE_SANITY_MAX_MOVE", "1000.0") or "1000.0"),
    "RTY": float(os.getenv("RITHMIC_RTY_PRICE_SANITY_MAX_MOVE", "100.0") or "100.0"),
}
TICK_QUEUE_MAX_SIZE = int(os.getenv("RITHMIC_TICK_QUEUE_MAX_SIZE", "5000") or "5000")
STEP6_INTRABAR_PATH_MAX_POINTS = int(os.getenv("RITHMIC_STEP6_INTRABAR_PATH_MAX_POINTS", "512") or "512")
EXECUTOR_PRICE_POST_TIMEOUT_SECONDS = min(float(os.getenv("RITHMIC_EXECUTOR_PRICE_POST_TIMEOUT_SECONDS", "0.5") or "0.5"), 0.5)
LISTENER_DOWNSTREAM_FORWARD_ENABLED = os.getenv("RITHMIC_ENABLE_DOWNSTREAM_PRICE_POSTS", "0").strip().lower() in {"1", "true", "yes", "on"}
FEED_HEALTH_WRITE_MIN_INTERVAL_SECONDS = float(os.getenv("RITHMIC_FEED_HEALTH_WRITE_MIN_INTERVAL_SECONDS", "1.0") or "1.0")
FEED_HEALTH_WRITE_WARNING_INTERVAL_SECONDS = float(os.getenv("RITHMIC_FEED_HEALTH_WRITE_WARNING_INTERVAL_SECONDS", "30.0") or "30.0")
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
EXECUTOR_LISTENER_GENERATION_URL = os.getenv(
    "EXECUTOR_LISTENER_GENERATION_URL",
    "http://127.0.0.1:6001/listener_generation/allocate",
).strip() or "http://127.0.0.1:6001/listener_generation/allocate"
LIVE_TICK_SYMBOLS = set()
DEAD_RESTART_ATTEMPTS = defaultdict(int)
DEAD_RESTART_LAST_TIMES = {}
latest_price_lock = threading.Lock()
feed_health_transition_lock = threading.Lock()
LAST_LOGGED_FEED_TRANSITION_STATE = {}
latest_price_by_symbol = {}
latest_tick_time_by_symbol = {}
latest_tick_monotonic_by_symbol = {}
step6_intrabar_paths_by_symbol = {}
raw_callback_count = defaultdict(int)
BRIDGE_CONNECTION_HEALTH = {
    "md_logged_in": False,
    "ts_logged_in": False,
    "market_data_closed": False,
    "trading_system_closed": False,
    "last_heartbeat_timestamp_utc": None,
}
SUBSCRIPTION_STATE_BY_SYMBOL = {}
FEED_HEALTH_WRITE_WARNING_STATE = {
    "last_logged_monotonic": 0.0,
    "last_signature": None,
}
_RUNTIME_SOURCE_HASHES = {}
LISTENER_AUTHORITY_EPOCH_ID = uuid.uuid4().hex
_LOCAL_FINALIZED_BAR_JOURNAL_LOCK = threading.RLock()
_LOCAL_FINALIZED_BAR_JOURNAL_INDEX_PATH = None
_LOCAL_FINALIZED_BAR_JOURNAL_BY_ID = {}
_LOCAL_FINALIZED_BAR_JOURNAL_HANDLE = None
_LOCAL_FINALIZED_BAR_JOURNAL_HANDLE_PATH = None
log_active_data_root("rithmic_live_listener")

# Credentials are read only from environment variables and must never be printed
# or included raw in diagnostics/errors.
RITHMIC_USER = os.getenv("RITHMIC_USER", "").strip()
RITHMIC_PASSWORD = os.getenv("RITHMIC_PASSWORD", "").strip()
RITHMIC_MD_CONNECTION_POINT = os.getenv("RITHMIC_MD_CONNECTION_POINT", "login_agent_tp_paper_sumc").strip() or "login_agent_tp_paper_sumc"
RITHMIC_TS_CONNECTION_POINT = os.getenv("RITHMIC_TS_CONNECTION_POINT", "login_agent_op_paperc").strip() or "login_agent_op_paperc"


class ListenerAuthorityGuard:
    """Process-lifetime ownership for the one permitted live Rithmic listener."""

    ERROR_ALREADY_EXISTS = 183

    def __init__(self, name=None):
        self.name = str(name or LISTENER_AUTHORITY_MUTEX_NAME)
        self._acquired = False
        self._windows_handle = None
        self._fallback_handle = None

    def acquire(self):
        if self._acquired:
            return True
        if os.name == "nt":
            return self._acquire_windows_mutex()
        return self._acquire_fallback_file_lock()

    def _acquire_windows_mutex(self):
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
        kernel32.ReleaseMutex.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(None, True, self.name)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == self.ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False

        self._windows_handle = (kernel32, handle)
        self._acquired = True
        return True

    def _acquire_fallback_file_lock(self):
        import fcntl

        lock_path = LOCAL_RUNTIME_DATA_ROOT / "rithmic_listener_authority.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+b")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False
        self._fallback_handle = handle
        self._acquired = True
        return True

    def release(self):
        if not self._acquired:
            return
        if self._windows_handle is not None:
            kernel32, handle = self._windows_handle
            kernel32.ReleaseMutex(handle)
            kernel32.CloseHandle(handle)
            self._windows_handle = None
        if self._fallback_handle is not None:
            import fcntl

            fcntl.flock(self._fallback_handle.fileno(), fcntl.LOCK_UN)
            self._fallback_handle.close()
            self._fallback_handle = None
        self._acquired = False
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
    if os.getenv(RITHMIC_SECONDARY_DIAGNOSTIC_SUBSCRIPTION_ENV, "").strip():
        raise ValueError(
            f"{RITHMIC_SECONDARY_DIAGNOSTIC_SUBSCRIPTION_ENV} is retired; "
            "the live listener supports only NQ and YM"
        )

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

    if not subscriptions:
        raise ValueError(f"{RITHMIC_SUBSCRIPTIONS_ENV} did not contain any subscriptions")

    configured_roots = [normalize_symbol_root(symbol) for _, symbol in subscriptions]
    unsupported_roots = sorted({root for root in configured_roots if root not in ACTIVE_LIVE_MARKET_ROOTS})
    if unsupported_roots:
        raise ValueError(
            f"{RITHMIC_SUBSCRIPTIONS_ENV} contains unsupported live roots: "
            f"{','.join(unsupported_roots)}; allowed roots are NQ,YM"
        )
    if set(configured_roots) != ACTIVE_LIVE_MARKET_ROOTS:
        raise ValueError(
            f"{RITHMIC_SUBSCRIPTIONS_ENV} must contain exactly the active roots NQ,YM"
        )

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


def atomic_replace_immediate(temp_path, target_path):
    """Retry transient Windows sharing violations immediately without waiting."""
    for attempt in range(ATOMIC_REPLACE_IMMEDIATE_ATTEMPTS):
        try:
            os.replace(temp_path, target_path)
            return
        except PermissionError:
            if attempt + 1 >= ATOMIC_REPLACE_IMMEDIATE_ATTEMPTS:
                raise


def atomic_write_json(path, payload, durable=True, compact=False):
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=target_path.parent,
        delete=False,
    ) as tmp_file:
        if compact:
            tmp_file.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        else:
            json.dump(payload, tmp_file, indent=2)
        tmp_file.flush()
        if durable:
            os.fsync(tmp_file.fileno())
        temp_path = Path(tmp_file.name)

    try:
        atomic_replace_immediate(temp_path, target_path)
    finally:
        temp_path.unlink(missing_ok=True)


def atomic_write_text(path, text):
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=target_path.parent,
        delete=False,
    ) as tmp_file:
        tmp_file.write(text)
        tmp_file.flush()
        os.fsync(tmp_file.fileno())
        temp_path = Path(tmp_file.name)

    try:
        atomic_replace_immediate(temp_path, target_path)
    finally:
        temp_path.unlink(missing_ok=True)


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_source_hashes(refresh=False):
    if refresh or not _RUNTIME_SOURCE_HASHES:
        listener_path = Path(__file__).resolve()
        bridge_text = build_powershell_bridge()
        _RUNTIME_SOURCE_HASHES.clear()
        _RUNTIME_SOURCE_HASHES.update({
            "listener_source_sha256": sha256_file(listener_path),
            "generated_bridge_sha256": sha256_bytes(bridge_text.encode("utf-8")),
        })
    return dict(_RUNTIME_SOURCE_HASHES)


def publish_listener_runtime_metadata(subscriptions, started_at_utc=None):
    hashes = runtime_source_hashes(refresh=True)
    payload = read_feed_health()
    payload["listener_runtime"] = {
        "pid": os.getpid(),
        "started_at_utc": started_at_utc or utc_now_precise_iso(),
        "source_path": str(Path(__file__).resolve()),
        **hashes,
        "timestamp_policy": RITHMIC_TIMESTAMP_POLICY,
        "bar_builder_contract_version": BAR_BUILDER_CONTRACT_VERSION,
        "canonical_queue_policy": "lossless_fifo_no_coalescing",
        "price_delivery_policy": "independent_symbol_fifo_lossless_no_coalescing",
        "price_delivery_symbols": sorted({
            str(symbol).upper()
            for _, symbol in subscriptions
        }),
        "executor_price_post_timeout_seconds": EXECUTOR_PRICE_POST_TIMEOUT_SECONDS,
        "finalization_policy": "first_next_exchange_minute_update_no_delay",
        "finalized_bar_publication_policy": "local_bar_and_atr_journal_fsync_then_atomic_bar_atr_cache_exposure",
        "local_authoritative_journal_path": str(LOCAL_FINALIZED_BAR_JOURNAL_PATH.resolve()),
        "local_atr_authority_journal_path": str(LOCAL_ATR_AUTHORITY_JOURNAL_PATH.resolve()),
        "atr_formula": ATR_FORMULA,
        "atr_formula_version": ATR_FORMULA_VERSION,
        "atr_transition_policy": "finalize_prior_bar_and_publish_atr_before_transition_tick_release",
        "atr_authority_epoch_id": LISTENER_AUTHORITY_EPOCH_ID,
        "subscribed_contracts": [
            {"exchange": str(exchange).upper(), "contract_symbol": str(symbol).upper()}
            for exchange, symbol in subscriptions
        ],
    }
    write_feed_health(payload)
    return dict(payload["listener_runtime"])


def utc_now_precise_iso():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def exchange_time_ns_from_fields(source_ssboe, source_nsecs=0, source_usecs=0):
    try:
        seconds = int(source_ssboe)
        nanoseconds = int(source_nsecs or 0)
        microseconds = int(source_usecs or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_rithmic_source_timestamp") from exc

    if seconds <= 0:
        raise ValueError("missing_rithmic_source_ssboe")
    if not 0 <= nanoseconds < NANOSECONDS_PER_SECOND:
        raise ValueError("invalid_rithmic_source_nsecs")
    if not 0 <= microseconds < 1_000_000:
        raise ValueError("invalid_rithmic_source_usecs")

    subsecond_ns = nanoseconds if nanoseconds != 0 or microseconds == 0 else microseconds * 1_000
    return seconds * NANOSECONDS_PER_SECOND + subsecond_ns


def exchange_time_iso_from_ns(exchange_time_ns):
    value = int(exchange_time_ns)
    seconds, nanoseconds = divmod(value, NANOSECONDS_PER_SECOND)
    timestamp = datetime.fromtimestamp(seconds, timezone.utc)
    return timestamp.strftime("%Y-%m-%dT%H:%M:%S") + f".{nanoseconds:09d}Z"


def minute_start_ns_from_exchange_time(exchange_time_ns):
    value = int(exchange_time_ns)
    return (value // NANOSECONDS_PER_MINUTE) * NANOSECONDS_PER_MINUTE


def minute_timestamp_from_exchange_ns(exchange_time_ns):
    minute_start_ns = minute_start_ns_from_exchange_time(exchange_time_ns)
    seconds = minute_start_ns // NANOSECONDS_PER_SECOND
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:00Z")


def append_jsonl_record(path, record, durable=False):
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        if durable:
            os.fsync(handle.fileno())


class FinalizedBarLocalCommitError(RuntimeError):
    pass


class FinalizedBarExposureError(RuntimeError):
    def __init__(self, message, local_commit=None):
        super().__init__(message)
        self.local_commit = dict(local_commit or {})


def canonical_finalized_bar_json(completed_bar):
    return json.dumps(completed_bar, sort_keys=True, separators=(",", ":"))


def load_local_finalized_bar_journal(path=None):
    target_path = Path(path or LOCAL_FINALIZED_BAR_JOURNAL_PATH).resolve()
    records = []
    if not target_path.exists():
        return records

    with target_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                record = json.loads(text)
            except Exception as exc:
                raise FinalizedBarLocalCommitError(
                    f"invalid_local_finalized_bar_journal_record:{line_number}"
                ) from exc
            if not isinstance(record, dict) or not record.get("bar_id"):
                raise FinalizedBarLocalCommitError(
                    f"invalid_local_finalized_bar_journal_identity:{line_number}"
                )
            records.append(record)
    return records


def _load_local_finalized_bar_journal_index_locked(target_path):
    global _LOCAL_FINALIZED_BAR_JOURNAL_INDEX_PATH
    resolved_path = Path(target_path).resolve()
    if _LOCAL_FINALIZED_BAR_JOURNAL_INDEX_PATH == resolved_path:
        return

    loaded = {}
    for record in load_local_finalized_bar_journal(resolved_path):
        bar_id = str(record["bar_id"])
        serialized = canonical_finalized_bar_json(record)
        existing = loaded.get(bar_id)
        if existing is not None and existing != serialized:
            raise FinalizedBarLocalCommitError("conflicting_local_finalized_bar_identity")
        loaded[bar_id] = serialized

    _LOCAL_FINALIZED_BAR_JOURNAL_BY_ID.clear()
    _LOCAL_FINALIZED_BAR_JOURNAL_BY_ID.update(loaded)
    _LOCAL_FINALIZED_BAR_JOURNAL_INDEX_PATH = resolved_path


def close_local_finalized_bar_journal():
    global _LOCAL_FINALIZED_BAR_JOURNAL_HANDLE
    global _LOCAL_FINALIZED_BAR_JOURNAL_HANDLE_PATH
    with _LOCAL_FINALIZED_BAR_JOURNAL_LOCK:
        if _LOCAL_FINALIZED_BAR_JOURNAL_HANDLE is not None:
            _LOCAL_FINALIZED_BAR_JOURNAL_HANDLE.close()
        _LOCAL_FINALIZED_BAR_JOURNAL_HANDLE = None
        _LOCAL_FINALIZED_BAR_JOURNAL_HANDLE_PATH = None


def _local_finalized_bar_journal_handle_locked(target_path):
    global _LOCAL_FINALIZED_BAR_JOURNAL_HANDLE
    global _LOCAL_FINALIZED_BAR_JOURNAL_HANDLE_PATH
    resolved_path = Path(target_path).resolve()
    if (
        _LOCAL_FINALIZED_BAR_JOURNAL_HANDLE is not None
        and _LOCAL_FINALIZED_BAR_JOURNAL_HANDLE_PATH == resolved_path
    ):
        return _LOCAL_FINALIZED_BAR_JOURNAL_HANDLE
    close_local_finalized_bar_journal()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    _LOCAL_FINALIZED_BAR_JOURNAL_HANDLE = resolved_path.open("a+b")
    _LOCAL_FINALIZED_BAR_JOURNAL_HANDLE_PATH = resolved_path
    return _LOCAL_FINALIZED_BAR_JOURNAL_HANDLE


def commit_finalized_bar_to_local_journal(completed_bar, path=None):
    if completed_bar.get("status") != "FINAL" or not completed_bar.get("bar_id"):
        raise FinalizedBarLocalCommitError("finalized_bar_missing_status_or_bar_id")

    target_path = Path(path or LOCAL_FINALIZED_BAR_JOURNAL_PATH).resolve()
    serialized = canonical_finalized_bar_json(completed_bar)
    encoded_record = (serialized + "\n").encode("utf-8")
    bar_id = str(completed_bar["bar_id"])

    with _LOCAL_FINALIZED_BAR_JOURNAL_LOCK:
        _load_local_finalized_bar_journal_index_locked(target_path)
        existing = _LOCAL_FINALIZED_BAR_JOURNAL_BY_ID.get(bar_id)
        if existing is not None:
            if existing != serialized:
                raise FinalizedBarLocalCommitError("conflicting_local_finalized_bar_identity")
            completed_unix_ns = time.time_ns()
            completed_monotonic_ns = time.perf_counter_ns()
            return {
                "local_commit_completed_at_utc": utc_now_precise_iso(),
                "local_commit_completed_unix_ns": completed_unix_ns,
                "local_commit_completed_monotonic_ns": completed_monotonic_ns,
                "local_journal_path": str(target_path),
                "idempotent": True,
            }

        try:
            handle = _local_finalized_bar_journal_handle_locked(target_path)
            handle.seek(0, os.SEEK_END)
            original_size = handle.tell()
            try:
                handle.write(encoded_record)
                handle.flush()
                os.fsync(handle.fileno())
                completed_unix_ns = time.time_ns()
                completed_monotonic_ns = time.perf_counter_ns()
            except Exception:
                handle.seek(original_size)
                handle.truncate()
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except Exception:
                    pass
                raise
        except Exception as exc:
            raise FinalizedBarLocalCommitError(sanitize_log_message(exc)) from exc

        _LOCAL_FINALIZED_BAR_JOURNAL_BY_ID[bar_id] = serialized
        return {
            "local_commit_completed_at_utc": utc_now_precise_iso(),
            "local_commit_completed_unix_ns": completed_unix_ns,
            "local_commit_completed_monotonic_ns": completed_monotonic_ns,
            "local_journal_path": str(target_path),
            "idempotent": False,
        }


def raw_tick_path(tick):
    exchange_time_ns = tick.get("exchange_time_ns")
    if exchange_time_ns is None:
        session_date = "invalid_source_time"
    else:
        timestamp = datetime.fromtimestamp(
            int(exchange_time_ns) / NANOSECONDS_PER_SECOND,
            timezone.utc,
        )
        session_date = timestamp.astimezone(SESSION_BAR_TIMEZONE).date().isoformat()
    raw_symbol = str(tick.get("symbol") or "UNKNOWN").upper()
    safe_symbol = "".join(character for character in raw_symbol if character.isalnum() or character in {"-", "_"})
    return RAW_TICK_ROOT / session_date / f"{safe_symbol or 'UNKNOWN'}_trades.jsonl"


def write_raw_tick_evidence(tick):
    record = {
        "record_type": "rithmic_trade_callback",
        "exchange": tick.get("exchange"),
        "contract_symbol": tick.get("symbol"),
        "price": tick.get("price"),
        "size": tick.get("size"),
        "callback_type": tick.get("callback_type"),
        "source_ssboe": tick.get("source_ssboe"),
        "source_nsecs": tick.get("source_nsecs"),
        "source_usecs": tick.get("source_usecs"),
        "rithmic_ssboe": tick.get("rithmic_ssboe"),
        "rithmic_usecs": tick.get("rithmic_usecs"),
        "jop_ssboe": tick.get("jop_ssboe"),
        "jop_nsecs": tick.get("jop_nsecs"),
        "exchange_time_ns": tick.get("exchange_time_ns"),
        "exchange_timestamp_utc": tick.get("exchange_timestamp_utc"),
        "callback_receipt_timestamp_utc": tick.get("callback_receipt_timestamp_utc"),
        "callback_receipt_unix_ns": tick.get("callback_receipt_unix_ns"),
        "callback_receipt_stopwatch_ticks": tick.get("callback_receipt_stopwatch_ticks"),
        "python_receipt_timestamp_utc": tick.get("python_receipt_timestamp_utc"),
        "python_receipt_monotonic_ns": tick.get("python_receipt_monotonic_ns"),
        "callback_sequence": tick.get("callback_sequence"),
        "bridge_generation": tick.get("bridge_generation"),
        "candle_assignment": tick.get("candle_assignment"),
        "condition": tick.get("condition"),
        "exchange_order_id": tick.get("exchange_order_id"),
        "aggressor_exchange_order_id": tick.get("aggressor_exchange_order_id"),
        "listener_source_sha256": tick.get("listener_source_sha256"),
        "generated_bridge_sha256": tick.get("generated_bridge_sha256"),
        "timestamp_policy": RITHMIC_TIMESTAMP_POLICY,
        "builder_contract_version": BAR_BUILDER_CONTRACT_VERSION,
    }
    append_jsonl_record(raw_tick_path(tick), record)
    return record


def append_data_authority_incident(incident_type, tick=None, **details):
    hashes = runtime_source_hashes()
    record = {
        "record_type": "market_data_authority_incident",
        "incident_type": str(incident_type),
        "recorded_at_utc": utc_now_precise_iso(),
        "timestamp_policy": RITHMIC_TIMESTAMP_POLICY,
        "builder_contract_version": BAR_BUILDER_CONTRACT_VERSION,
        **hashes,
    }
    if isinstance(tick, dict):
        record["tick"] = {
            key: tick.get(key)
            for key in (
                "exchange",
                "symbol",
                "price",
                "size",
                "callback_type",
                "source_ssboe",
                "source_nsecs",
                "source_usecs",
                "exchange_time_ns",
                "exchange_timestamp_utc",
                "callback_receipt_timestamp_utc",
                "python_receipt_timestamp_utc",
                "callback_sequence",
                "bridge_generation",
                "candle_assignment",
            )
        }
    record.update(details)
    identity_payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    record["incident_id"] = sha256_bytes(identity_payload)
    append_jsonl_record(DATA_AUTHORITY_INCIDENTS_PATH, record, durable=True)
    return record


def log_feed_health_write_warning(reason, error):
    signature = f"{reason}|{type(error).__name__}|{sanitize_log_message(error)}"
    now = time.monotonic()
    last_logged = float(FEED_HEALTH_WRITE_WARNING_STATE.get("last_logged_monotonic") or 0.0)
    last_signature = FEED_HEALTH_WRITE_WARNING_STATE.get("last_signature")
    if signature == last_signature and (now - last_logged) < FEED_HEALTH_WRITE_WARNING_INTERVAL_SECONDS:
        return
    FEED_HEALTH_WRITE_WARNING_STATE["last_logged_monotonic"] = now
    FEED_HEALTH_WRITE_WARNING_STATE["last_signature"] = signature
    print(
        f"RITHMIC WARNING|{reason}|"
        f"path={FEED_HEALTH_PATH}|error={sanitize_log_message(error)}"
    )


def local_session_date_from_timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    return parsed.astimezone(SESSION_BAR_TIMEZONE).date().isoformat()


def session_bar_path(root_symbol, session_date):
    return data_path("rithmic_session_bars", session_date, f"{root_symbol}_1m.jsonl")


def build_session_bar_record(completed_bar):
    if completed_bar.get("bar_id") and completed_bar.get("status") == "FINAL":
        return completed_bar

    contract_symbol = str(completed_bar.get("symbol") or "").strip().upper()
    root_symbol = normalize_symbol_root(contract_symbol)
    if root_symbol not in SESSION_BAR_ROOTS:
        return None

    timestamp = str(completed_bar.get("timestamp") or "").strip()
    session_date = local_session_date_from_timestamp(timestamp)
    if not session_date:
        return None

    try:
        return {
            "session_date": session_date,
            "root_symbol": root_symbol,
            "contract_symbol": contract_symbol,
            "timestamp": timestamp,
            "open": float(completed_bar["open"]),
            "high": float(completed_bar["high"]),
            "low": float(completed_bar["low"]),
            "close": float(completed_bar["close"]),
            "source": "rithmic_live_listener",
            "recorded_at": utc_now_precise_iso(),
        }
    except Exception:
        return None


def last_jsonl_record(path):
    target_path = Path(path)
    if not target_path.exists():
        return None
    try:
        lines = target_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return None
    for line in reversed(lines):
        text = str(line).strip()
        if not text:
            continue
        try:
            record = json.loads(text)
        except Exception:
            return None
        return record if isinstance(record, dict) else None
    return None


def append_session_bar_record(completed_bar):
    record = build_session_bar_record(completed_bar)
    if not isinstance(record, dict):
        return None

    target_path = session_bar_path(record["root_symbol"], record["session_date"])
    if target_path.exists():
        with target_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    existing_record = json.loads(text)
                except Exception:
                    continue
                if not isinstance(existing_record, dict):
                    continue
                if record.get("bar_id") and existing_record.get("bar_id") == record.get("bar_id"):
                    if canonical_finalized_bar_json(existing_record) != canonical_finalized_bar_json(record):
                        raise RuntimeError("conflicting_finalized_bar_identity")
                    return target_path
                same_identity = (
                    str(existing_record.get("timestamp") or "") == record["timestamp"]
                    and str(existing_record.get("contract_symbol") or existing_record.get("symbol") or "").upper()
                    == str(record.get("contract_symbol") or record.get("symbol") or "").upper()
                )
                if same_identity:
                    if record.get("bar_id"):
                        raise RuntimeError("conflicting_finalized_bar_identity")
                    return target_path

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        file.flush()
        os.fsync(file.fileno())
    return target_path


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


def update_bridge_connection_health_from_line(line):
    text = str(line or "")
    if text in {"STATUS|market_data_login_complete", "STATUS|market_data_connected"}:
        BRIDGE_CONNECTION_HEALTH["md_logged_in"] = True
        BRIDGE_CONNECTION_HEALTH["market_data_closed"] = False
        BRIDGE_CONNECTION_HEALTH["last_heartbeat_timestamp_utc"] = utc_now_iso()
        return
    if (
        text.startswith("STATUS|market_data_login_failed|")
        or text == "STATUS|market_data_connection_closed_unexpected"
        or text.startswith("STATUS|forced_logout|connection=MarketData")
    ):
        BRIDGE_CONNECTION_HEALTH["md_logged_in"] = False
        BRIDGE_CONNECTION_HEALTH["market_data_closed"] = True
        BRIDGE_CONNECTION_HEALTH["last_heartbeat_timestamp_utc"] = utc_now_iso()
        return
    if text.startswith("STATUS|subscribing|"):
        parts = text.split("|")
        if len(parts) >= 4:
            SUBSCRIPTION_STATE_BY_SYMBOL[parts[3].strip().upper()] = "PENDING"
        return
    if text.startswith("STATUS|subscription_call_returned|"):
        parts = text.split("|")
        if len(parts) >= 4:
            SUBSCRIPTION_STATE_BY_SYMBOL[parts[3].strip().upper()] = "ACTIVE"
        return
    if text.startswith("ERROR|subscription_call_failed|"):
        parts = text.split("|")
        if len(parts) >= 4:
            SUBSCRIPTION_STATE_BY_SYMBOL[parts[3].strip().upper()] = "FAILED"
        return
    if not text.startswith("STATUS|listener_heartbeat|"):
        return
    BRIDGE_CONNECTION_HEALTH["last_heartbeat_timestamp_utc"] = utc_now_iso()
    parts = text.split("|")[2:]
    for part in parts:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        normalized_key = key.strip()
        if normalized_key in BRIDGE_CONNECTION_HEALTH:
            BRIDGE_CONNECTION_HEALTH[normalized_key] = str(value).strip().lower() == "true"


def get_feed_thresholds(symbol):
    return {
        "activity_active_seconds": ACTIVITY_ACTIVE_SECONDS,
        "feed_live_seconds": FEED_STALE_SECONDS,
        "feed_stale_seconds": FEED_STALE_SECONDS,
        "feed_dead_seconds": FEED_DEAD_SECONDS,
        # Legacy diagnostic names retained for compatible readers.
        "quiet_seconds": ACTIVITY_ACTIVE_SECONDS,
        "stale_seconds": FEED_STALE_SECONDS,
        "disconnected_seconds": FEED_DEAD_SECONDS,
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


def feed_reference_time(reference_time=None):
    if reference_time is None:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    if getattr(reference_time, "tzinfo", None):
        return reference_time.astimezone(timezone.utc).replace(tzinfo=None)
    return reference_time


def feed_age_seconds(entry, reference_time=None):
    reference = feed_reference_time(reference_time)
    last_tick = parse_utc_timestamp((entry or {}).get("last_tick_timestamp_utc"))
    if last_tick is None:
        return None
    return (reference - last_tick).total_seconds()


def calculate_activity_status(entry, reference_time=None, symbol=None):
    age_seconds = feed_age_seconds(entry, reference_time=reference_time)
    if age_seconds is None:
        return "QUIET"
    return "ACTIVE" if max(0.0, age_seconds) <= ACTIVITY_ACTIVE_SECONDS else "QUIET"


def calculate_feed_status(entry, reference_time=None, symbol=None):
    entry = entry if isinstance(entry, dict) else {}
    if str(entry.get("price_sanity_status") or "").upper() == "INVALID_PRICE":
        return "INVALID"
    if str(entry.get("connection_state") or "").upper() == "DISCONNECTED":
        return "DISCONNECTED"
    if str(entry.get("subscription_state") or "").upper() == "FAILED":
        return "DISCONNECTED"

    raw_last_tick = entry.get("last_tick_timestamp_utc")
    last_tick = parse_utc_timestamp(raw_last_tick)
    if last_tick is None:
        return "INVALID" if raw_last_tick not in (None, "") else "STALE"

    age_seconds = feed_age_seconds(entry, reference_time=reference_time)
    if age_seconds is None:
        return "STALE"
    if age_seconds < -FEED_TIMESTAMP_FUTURE_TOLERANCE_SECONDS:
        return "INVALID"
    age_seconds = max(0.0, age_seconds)
    if age_seconds > FEED_DEAD_SECONDS:
        return "DEAD"
    if age_seconds > FEED_STALE_SECONDS:
        return "STALE"
    return "LIVE"


def bridge_health_for_entry(entry, symbol, reference_time=None):
    resolved_contract = str((entry or {}).get("resolved_contract") or symbol or "").strip().upper()
    heartbeat_timestamp = BRIDGE_CONNECTION_HEALTH.get("last_heartbeat_timestamp_utc")
    heartbeat_at = parse_utc_timestamp(heartbeat_timestamp)
    reference = feed_reference_time(reference_time)
    heartbeat_age = max(0.0, (reference - heartbeat_at).total_seconds()) if heartbeat_at is not None else None

    existing_connection = str((entry or {}).get("connection_state") or "").strip().upper()
    if BRIDGE_CONNECTION_HEALTH.get("market_data_closed"):
        connection_state = "DISCONNECTED"
    elif heartbeat_timestamp and not BRIDGE_CONNECTION_HEALTH.get("md_logged_in"):
        connection_state = "DISCONNECTED"
    elif BRIDGE_CONNECTION_HEALTH.get("md_logged_in"):
        connection_state = "CONNECTED"
    else:
        connection_state = existing_connection or "UNKNOWN"

    existing_subscription = str((entry or {}).get("subscription_state") or "").strip().upper()
    subscription_state = (
        SUBSCRIPTION_STATE_BY_SYMBOL.get(resolved_contract)
        or SUBSCRIPTION_STATE_BY_SYMBOL.get(normalize_symbol_root(resolved_contract))
        or existing_subscription
        or ("ACTIVE" if (entry or {}).get("last_tick_timestamp_utc") else "UNKNOWN")
    )
    return connection_state, subscription_state, heartbeat_timestamp, heartbeat_age


def connection_reason_suffix(connection_state, subscription_state, heartbeat_age):
    connection_text = "Connection healthy." if connection_state == "CONNECTED" else f"Connection {connection_state.lower()}."
    if heartbeat_age is None:
        heartbeat_text = "Heartbeat unavailable."
    elif heartbeat_age <= 15.0:
        heartbeat_text = "Heartbeat healthy."
    else:
        heartbeat_text = f"Heartbeat age {heartbeat_age:.1f} seconds."
    subscription_text = (
        "Subscription active."
        if subscription_state == "ACTIVE"
        else f"Subscription {str(subscription_state or 'unknown').lower()}."
    )
    return f"{connection_text} {heartbeat_text} {subscription_text}"


def build_feed_reasons(entry):
    feed_status = str(entry.get("feed_status") or "STALE").upper()
    activity_status = str(entry.get("activity_status") or "QUIET").upper()
    age_seconds = entry.get("feed_age_seconds")
    connection_state = str(entry.get("connection_state") or "UNKNOWN").upper()
    subscription_state = str(entry.get("subscription_state") or "UNKNOWN").upper()
    heartbeat_age = entry.get("heartbeat_age_seconds")
    suffix = connection_reason_suffix(connection_state, subscription_state, heartbeat_age)
    age_text = "unknown" if age_seconds is None else f"{float(age_seconds):.1f}"

    if feed_status == "DISCONNECTED":
        feed_reason = "Market Data login or subscription lost. " + suffix
    elif feed_status == "INVALID":
        detail = entry.get("price_sanity_reason") or "Invalid or impossible market-data timestamp/value."
        feed_reason = f"Market data invalid: {detail} {suffix}"
    elif feed_status == "DEAD":
        feed_reason = f"No accepted market-data event for {age_text} seconds. {suffix}"
    elif feed_status == "STALE":
        feed_reason = f"No accepted market-data event for {age_text} seconds. {suffix}"
    else:
        feed_reason = f"Market data usable. Last accepted TradePrint {age_text} seconds ago. {suffix}"

    activity_reason = (
        f"Accepted TradePrint {age_text} seconds ago."
        if activity_status == "ACTIVE"
        else f"No accepted TradePrint for {age_text} seconds. {suffix}"
    )
    reason = activity_reason if feed_status == "LIVE" and activity_status == "QUIET" else feed_reason
    return feed_reason, activity_reason, reason


def transition_timestamp(reference_time=None):
    reference = feed_reference_time(reference_time).replace(tzinfo=timezone.utc)
    return reference.isoformat().replace("+00:00", "Z")


def append_feed_health_transition(symbol, entry, previous_feed_status, previous_activity_status, reference_time=None):
    new_feed_status = str(entry.get("feed_status") or "").upper() or None
    new_activity_status = str(entry.get("activity_status") or "").upper() or None
    feed_changed = previous_feed_status is not None and previous_feed_status != new_feed_status
    activity_changed = previous_activity_status is not None and previous_activity_status != new_activity_status
    if not feed_changed and not activity_changed:
        return False

    resolved_contract = str(entry.get("resolved_contract") or symbol or "").strip().upper()
    normalized_symbol = str(symbol or "").strip().upper()
    if resolved_contract and normalized_symbol != resolved_contract:
        return False

    record = {
        "timestamp_utc": transition_timestamp(reference_time),
        "symbol": normalize_symbol_root(normalized_symbol) or normalized_symbol,
        "resolved_contract": resolved_contract or normalized_symbol,
        "previous_feed_status": previous_feed_status,
        "new_feed_status": new_feed_status,
        "previous_activity_status": previous_activity_status,
        "new_activity_status": new_activity_status,
        "reason": entry.get("reason"),
        "elapsed_age_seconds": entry.get("feed_age_seconds"),
        "last_accepted_trade_print_timestamp_utc": entry.get("last_tick_timestamp_utc"),
        "heartbeat_age_seconds": entry.get("heartbeat_age_seconds"),
        "connection_state": entry.get("connection_state"),
        "subscription_state": entry.get("subscription_state"),
    }
    with feed_health_transition_lock:
        transition_key = resolved_contract or normalized_symbol
        transition_signature = (
            new_feed_status,
            new_activity_status,
            entry.get("last_tick_timestamp_utc"),
            entry.get("connection_state"),
            entry.get("subscription_state"),
        )
        if LAST_LOGGED_FEED_TRANSITION_STATE.get(transition_key) == transition_signature:
            return False
        FEED_HEALTH_TRANSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with FEED_HEALTH_TRANSITIONS_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        LAST_LOGGED_FEED_TRANSITION_STATE[transition_key] = transition_signature
    return True


def derive_executor_price_feed_status(symbol, tick_timestamp_utc=None, reference_time=None):
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol:
        return None

    entry = {}
    try:
        payload = read_feed_health()
        symbols = payload.get("symbols", {}) if isinstance(payload, dict) else {}
        for alias in build_snapshot_symbol_aliases(normalized_symbol):
            candidate = symbols.get(alias)
            if isinstance(candidate, dict):
                entry = dict(candidate)
                break
    except Exception:
        entry = {}

    if tick_timestamp_utc:
        entry["last_tick_timestamp_utc"] = tick_timestamp_utc

    if entry.get("last_tick_timestamp_utc"):
        return calculate_feed_status(entry, reference_time=reference_time, symbol=normalized_symbol)

    status = str(entry.get("feed_status") or "").strip().upper()
    return status or None


def refresh_feed_health_statuses(payload, reference_time=None):
    symbols = payload.setdefault("symbols", {})
    any_stale = not symbols
    bridge_post_ages = []
    frozen_price_symbols = []
    for symbol, entry in symbols.items():
        if isinstance(entry, dict):
            had_previous_status = "feed_status" in entry
            previous_status = str(entry.get("feed_status") or "STALE").upper() if had_previous_status else None
            previous_activity_status = (
                str(entry.get("activity_status") or "QUIET").upper()
                if "activity_status" in entry
                else None
            )
            connection_state, subscription_state, heartbeat_timestamp, heartbeat_age = bridge_health_for_entry(
                entry,
                symbol,
                reference_time=reference_time,
            )
            entry["connection_state"] = connection_state
            entry["subscription_state"] = subscription_state
            entry["last_heartbeat_timestamp_utc"] = heartbeat_timestamp
            entry["heartbeat_age_seconds"] = round(heartbeat_age, 3) if heartbeat_age is not None else None
            next_status = calculate_feed_status(entry, reference_time=reference_time, symbol=symbol)
            if next_status == "LIVE" and had_previous_status and previous_status in {"STALE", "DEAD", "DISCONNECTED", "INVALID"}:
                confirmations = int(entry.get("recovery_tick_confirmations", 0) or 0)
                if confirmations < FEED_RECOVERY_TICK_CONFIRMATIONS:
                    next_status = "STALE"
            entry["feed_status"] = next_status
            entry["activity_status"] = calculate_activity_status(entry, reference_time=reference_time, symbol=symbol)
            thresholds = get_feed_thresholds(symbol)
            entry["feed_quiet_seconds"] = thresholds["quiet_seconds"]
            entry["feed_stale_seconds"] = thresholds["stale_seconds"]
            entry["feed_disconnected_seconds"] = thresholds["disconnected_seconds"]
            entry["activity_active_seconds"] = thresholds["activity_active_seconds"]
            entry["feed_live_seconds"] = thresholds["feed_live_seconds"]
            entry["feed_dead_seconds"] = thresholds["feed_dead_seconds"]
            last_tick = parse_utc_timestamp(entry.get("last_tick_timestamp_utc"))
            if last_tick is not None:
                reference_for_tick = feed_reference_time(reference_time)
                entry["feed_age_seconds"] = round(max(0.0, (reference_for_tick - last_tick).total_seconds()), 3)
            else:
                entry["feed_age_seconds"] = None
            entry["activity_age_seconds"] = entry["feed_age_seconds"]
            feed_reason, activity_reason, reason = build_feed_reasons(entry)
            entry["feed_reason"] = feed_reason
            entry["activity_reason"] = activity_reason
            entry["reason"] = reason
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
            append_feed_health_transition(
                symbol,
                entry,
                previous_status,
                previous_activity_status,
                reference_time=reference_time,
            )
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
    try:
        serialized_text = json.dumps(payload, indent=2)
        atomic_write_text(FEED_HEALTH_PATH, serialized_text + "\n")
    except Exception as exc:
        log_feed_health_write_warning("feed_health_write_failed", exc)


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
        entry["resolved_contract"] = normalized_symbol
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


def record_executor_price_post_success(symbol, price, tick_timestamp_utc, post_timestamp_utc, latency_ms=None):
    normalized_symbol = str(symbol or "").upper()
    if not normalized_symbol:
        return
    payload = read_feed_health()
    symbols = payload.setdefault("symbols", {})
    for alias in build_snapshot_symbol_aliases(normalized_symbol):
        entry = symbols.setdefault(alias, {})
        entry["resolved_contract"] = normalized_symbol
        entry["latest_price"] = float(price)
        entry["latest_listener_price"] = float(price)
        entry["last_listener_price_timestamp_utc"] = tick_timestamp_utc
        entry["last_bridge_post_timestamp_utc"] = post_timestamp_utc
        entry["last_successful_executor_price_post_timestamp_utc"] = post_timestamp_utc
        entry["last_executor_publish_at"] = post_timestamp_utc
        entry["last_executor_price_post_failure_reason"] = None
        if latency_ms is not None:
            entry["executor_publish_latency_ms"] = latency_ms
    refresh_feed_health_statuses(payload, reference_time=parse_utc_timestamp(post_timestamp_utc))
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
            previous_feed_status = str(entry.get("feed_status") or "").upper() or None
            previous_activity_status = str(entry.get("activity_status") or "").upper() or None
            entry["resolved_contract"] = str(symbol or "").upper()
            entry["feed_status"] = status
            entry["activity_status"] = "QUIET"
            entry["activity_active_seconds"] = ACTIVITY_ACTIVE_SECONDS
            entry["feed_live_seconds"] = FEED_STALE_SECONDS
            entry["feed_stale_seconds"] = FEED_STALE_SECONDS
            entry["feed_dead_seconds"] = FEED_DEAD_SECONDS
            entry["feed_quiet_seconds"] = ACTIVITY_ACTIVE_SECONDS
            entry["feed_disconnected_seconds"] = FEED_DEAD_SECONDS
            if clear_tick_state:
                entry["last_tick_timestamp_utc"] = None
                entry["feed_age_seconds"] = None
                entry["activity_age_seconds"] = None
                entry["recovery_tick_confirmations"] = 0
                entry["last_bridge_post_timestamp_utc"] = None
                entry["last_successful_executor_price_post_timestamp_utc"] = None
                entry["last_bridge_post_age_seconds"] = None
            else:
                entry.setdefault("last_tick_timestamp_utc", None)
                entry.setdefault("recovery_tick_confirmations", 0)
            if status == "DISCONNECTED":
                entry["connection_state"] = "DISCONNECTED"
            else:
                connection_state, subscription_state, heartbeat_timestamp, heartbeat_age = bridge_health_for_entry(
                    entry,
                    alias,
                    reference_time=parse_utc_timestamp(timestamp_utc),
                )
                entry["connection_state"] = connection_state
                entry["subscription_state"] = subscription_state
                entry["last_heartbeat_timestamp_utc"] = heartbeat_timestamp
                entry["heartbeat_age_seconds"] = round(heartbeat_age, 3) if heartbeat_age is not None else None
            feed_reason, activity_reason, reason = build_feed_reasons(entry)
            entry["feed_reason"] = feed_reason
            entry["activity_reason"] = activity_reason
            entry["reason"] = reason
            entry["status_updated_at_utc"] = timestamp_utc
            append_feed_health_transition(
                alias,
                entry,
                previous_feed_status,
                previous_activity_status,
                reference_time=parse_utc_timestamp(timestamp_utc),
            )
    payload["updated_at_utc"] = timestamp_utc
    payload["system_state_feed"] = "LIVE" if status == "LIVE" else "STALE"
    payload["warning"] = None if status == "LIVE" else "RITHMIC FEED STALE  EXECUTION ONLY MODE"
    write_feed_health(payload)


def write_atr_snapshot(symbol, atr_record, atr_value=None):
    if str(symbol).upper() not in LIVE_TICK_SYMBOLS:
        timestamp = (atr_record or {}).get("candle_minute") if isinstance(atr_record, dict) else atr_record
        update_feed_health(symbol, "last_atr_timestamp_utc", str(timestamp), force_status="STALE")
        return

    if isinstance(atr_record, dict):
        snapshot_entry = copy.deepcopy(atr_record)
    else:
        # Legacy diagnostic callers may still exercise this function, but such
        # records are explicitly non-canonical and cannot authorize a trade.
        snapshot_entry = {
            "atr_value": float(atr_value),
            "updated_raw_atr": float(atr_value),
            "atr_bar_timestamp": str(atr_record),
            "candle_minute": str(atr_record),
            "atr_source": "legacy_noncanonical_rithmic_atr",
            "ready": False,
            "warmup_status": "legacy_noncanonical",
        }

    payload = read_json_file(ATR_SNAPSHOT_PATH, {"symbols": {}})
    symbols = payload.setdefault("symbols", {})
    for alias in build_snapshot_symbol_aliases(symbol):
        symbols[alias] = copy.deepcopy(snapshot_entry)

    # This is an atomic availability cache. Durability was already established
    # by fsync of the combined finalized-bar/canonical-ATR authority record.
    atomic_write_json(ATR_SNAPSHOT_PATH, payload, durable=False, compact=True)
    update_feed_health(symbol, "last_atr_timestamp_utc", str(snapshot_entry.get("candle_minute")))


def clear_atr_snapshot(symbol, reason="unspecified_authority_reset"):
    payload = read_json_file(ATR_SNAPSHOT_PATH, {"symbols": {}})
    symbols = payload.setdefault("symbols", {})
    removed = False

    for alias in build_snapshot_symbol_aliases(symbol):
        if alias in symbols:
            del symbols[alias]
            removed = True

    if removed:
        atomic_write_json(ATR_SNAPSHOT_PATH, payload)
        append_data_authority_incident(
            "canonical_atr_reset",
            symbol=str(symbol or "").upper(),
            reason=str(reason),
            atr_authority_epoch_id=LISTENER_AUTHORITY_EPOCH_ID,
        )


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
                normalized_entry = dict(entry)
                normalized_entry.update({
                    "timestamp": str(entry["timestamp"]),
                    "symbol": str(entry["symbol"]).upper(),
                    "open": float(entry["open"]),
                    "high": float(entry["high"]),
                    "low": float(entry["low"]),
                    "close": float(entry["close"]),
                })
                bars.append(normalized_entry)
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
    # os.replace is the availability boundary for Entry Agent. Finalized live
    # bars reach this function only after their exact object and bar_id have
    # been flushed and fsynced to the local authoritative journal.
    atomic_write_json(RECENT_BARS_PATH, payload, durable=False, compact=True)


def is_retired_live_symbol(symbol):
    return normalize_symbol_root(str(symbol or "").strip().upper()) in RETIRED_LIVE_MARKET_ROOTS


def remove_retired_symbol_entries(symbols):
    if not isinstance(symbols, dict):
        return []
    removed = []
    for symbol in list(symbols):
        if is_retired_live_symbol(symbol):
            removed.append(str(symbol).upper())
            symbols.pop(symbol, None)
    return sorted(set(removed))


def prune_retired_live_runtime_state(bar_cache):
    """Remove retired markets from mutable live projections, never audit history."""
    removed = {
        "recent_bars": remove_retired_symbol_entries(bar_cache),
        "atr_snapshot": [],
        "atr_shadow": [],
        "feed_health": [],
    }
    if removed["recent_bars"]:
        persist_recent_bars(bar_cache)

    for name, path in (
        ("atr_snapshot", ATR_SNAPSHOT_PATH),
        ("atr_shadow", ATR_SHADOW_COMPARISON_PATH),
    ):
        target_path = Path(path)
        if not target_path.exists():
            continue
        payload = read_json_file(target_path, {"symbols": {}})
        removed[name] = remove_retired_symbol_entries(payload.get("symbols"))
        if removed[name]:
            atomic_write_json(target_path, payload)

    if Path(FEED_HEALTH_PATH).exists():
        payload = read_feed_health()
        removed["feed_health"] = remove_retired_symbol_entries(payload.get("symbols"))
        payload["frozen_price_symbols"] = [
            symbol for symbol in payload.get("frozen_price_symbols", [])
            if not is_retired_live_symbol(symbol)
        ]
        runtime = payload.get("listener_runtime")
        if isinstance(runtime, dict):
            runtime["subscribed_contracts"] = [
                subscription for subscription in runtime.get("subscribed_contracts", [])
                if not is_retired_live_symbol(subscription.get("contract_symbol"))
            ]
        if removed["feed_health"]:
            refresh_feed_health_statuses(payload)
            write_feed_health(payload)

    for mapping in (
        latest_price_by_symbol,
        latest_tick_time_by_symbol,
        latest_tick_monotonic_by_symbol,
        step6_intrabar_paths_by_symbol,
        raw_callback_count,
        SUBSCRIPTION_STATE_BY_SYMBOL,
        DEAD_RESTART_ATTEMPTS,
        DEAD_RESTART_LAST_TIMES,
    ):
        remove_retired_symbol_entries(mapping)
    for symbol in list(LIVE_TICK_SYMBOLS):
        if is_retired_live_symbol(symbol):
            LIVE_TICK_SYMBOLS.discard(symbol)
    return removed


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


def true_range_for_bar(bar, previous_close):
    high = float(bar["high"])
    low = float(bar["low"])
    return max(high - low, abs(high - float(previous_close)), abs(low - float(previous_close)))


def compute_sma_atr(bars, period=ATR_PERIOD):
    contiguous_bars = get_contiguous_bar_tail(bars)
    if len(contiguous_bars) < period + 1:
        return None

    relevant_bars = contiguous_bars[-(period + 1):]
    tr_values = []

    for index in range(1, len(relevant_bars)):
        tr_values.append(true_range_for_bar(relevant_bars[index], relevant_bars[index - 1]["close"]))

    return sum(tr_values) / float(period)


def compute_rma_atr(bars, period=ATR_PERIOD):
    contiguous_bars = get_contiguous_bar_tail(bars)
    if len(contiguous_bars) < period + 1:
        return None

    tr_values = []
    for index in range(1, len(contiguous_bars)):
        tr_values.append(true_range_for_bar(contiguous_bars[index], contiguous_bars[index - 1]["close"]))

    if len(tr_values) < period:
        return None

    atr_value = sum(tr_values[:period]) / float(period)
    for true_range in tr_values[period:]:
        atr_value = ((atr_value * (period - 1)) + true_range) / float(period)

    return atr_value


def compute_atr(bars, period=ATR_PERIOD):
    """Canonical production ATR: Wilder RMA over finalized one-minute bars."""
    return compute_rma_atr(bars, period=period)


def is_authoritative_finalized_bar(bar):
    return bool(
        isinstance(bar, dict)
        and bar.get("status") == "FINAL"
        and bar.get("bar_id")
        and bar.get("builder_contract_version") == BAR_BUILDER_CONTRACT_VERSION
    )


def canonical_atr_identity_payload(record):
    keys = (
        "symbol_root",
        "contract_symbol",
        "timeframe",
        "period",
        "formula",
        "formula_version",
        "bar_id",
        "candle_minute",
        "previous_close",
        "high",
        "low",
        "true_range",
        "previous_atr",
        "updated_raw_atr",
        "ready",
        "warmup_status",
        "warmup_true_range_count",
    )
    return {key: record.get(key) for key in keys}


def build_canonical_atr_record(bars, completed_bar):
    authoritative = [bar for bar in bars if is_authoritative_finalized_bar(bar)]
    contiguous = get_contiguous_bar_tail(authoritative)
    current = completed_bar
    previous_bar = contiguous[-2] if len(contiguous) >= 2 else None
    previous_close = float(previous_bar["close"]) if previous_bar is not None else None
    true_range = true_range_for_bar(current, previous_close) if previous_close is not None else None
    previous_atr = None
    updated_atr = None
    warmup_status = "insufficient_authoritative_finalized_history"
    true_range_count = max(0, len(contiguous) - 1)

    previous_record = previous_bar.get("canonical_atr") if isinstance(previous_bar, dict) else None
    previous_record_ready = bool(
        isinstance(previous_record, dict)
        and previous_record.get("ready") is True
        and previous_record.get("formula_version") == ATR_FORMULA_VERSION
        and previous_record.get("bar_id") == previous_bar.get("bar_id")
        and previous_record.get("updated_raw_atr") is not None
    )
    if true_range is not None and previous_record_ready:
        previous_atr = float(previous_record["updated_raw_atr"])
        updated_atr = ((previous_atr * (ATR_PERIOD - 1)) + true_range) / float(ATR_PERIOD)
        warmup_status = "ready_continuation"
    elif true_range_count >= ATR_PERIOD:
        tr_values = [
            true_range_for_bar(contiguous[index], contiguous[index - 1]["close"])
            for index in range(1, len(contiguous))
        ]
        running_atr = sum(tr_values[:ATR_PERIOD]) / float(ATR_PERIOD)
        if len(tr_values) == ATR_PERIOD:
            previous_atr = None
            updated_atr = running_atr
            warmup_status = "ready_initial_seed"
        else:
            for value in tr_values[ATR_PERIOD:-1]:
                running_atr = ((running_atr * (ATR_PERIOD - 1)) + value) / float(ATR_PERIOD)
            previous_atr = running_atr
            updated_atr = ((previous_atr * (ATR_PERIOD - 1)) + tr_values[-1]) / float(ATR_PERIOD)
            warmup_status = "ready_seeded_from_authoritative_history"

    ready = updated_atr is not None and math.isfinite(float(updated_atr)) and float(updated_atr) > 0
    prepared_at = utc_now_precise_iso()
    hashes = runtime_source_hashes()
    record = {
        "record_type": "canonical_rithmic_atr",
        "symbol_root": normalize_symbol_root(current.get("contract_symbol") or current.get("symbol")),
        "contract_symbol": str(current.get("contract_symbol") or current.get("symbol") or "").upper(),
        "timeframe": "1m",
        "period": ATR_PERIOD,
        "formula": ATR_FORMULA,
        "formula_version": ATR_FORMULA_VERSION,
        "bar_id": current.get("bar_id"),
        "finalized_candle_bar_id": current.get("bar_id"),
        "candle_minute": current.get("timestamp"),
        "previous_close": previous_close,
        "high": float(current["high"]),
        "low": float(current["low"]),
        "true_range": true_range,
        "previous_atr": previous_atr,
        "updated_raw_atr": float(updated_atr) if ready else None,
        "atr_value": float(updated_atr) if ready else None,
        "atr_source": ATR_AUTHORITY_SOURCE,
        "atr_bar_timestamp": current.get("timestamp"),
        "last_included_bar": current.get("timestamp"),
        "last_included_bar_id": current.get("bar_id"),
        "ready": bool(ready),
        "warmup_status": warmup_status,
        "warmup_true_range_count": true_range_count,
        "warmup_required_true_range_count": ATR_PERIOD,
        "durable_commit_timestamp_utc": prepared_at,
        "trading_availability_timestamp_utc": prepared_at,
        "listener_source_sha256": hashes.get("listener_source_sha256"),
        "builder_contract_version": current.get("builder_contract_version"),
        "atr_authority_epoch_id": LISTENER_AUTHORITY_EPOCH_ID,
    }
    identity = canonical_atr_identity_payload(record)
    record["atr_record_id"] = sha256_bytes(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return record


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
    rithmic_sma_atr = compute_sma_atr(persisted_bars)
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
        "tv_raw_ticker": tv_record.get("raw_ticker") if isinstance(tv_record, dict) else None,
        "rithmic_atr": round(float(rithmic_atr), 6) if rithmic_atr is not None else None,
        "rithmic_rma_atr": round(float(rithmic_atr), 6) if rithmic_atr is not None else None,
        "rithmic_sma_atr": round(float(rithmic_sma_atr), 6) if rithmic_sma_atr is not None else None,
        "rithmic_atr_timestamp": rithmic_timestamp,
        "delta_abs": round(delta_abs, 6) if delta_abs is not None else None,
        "delta_pct": round(delta_pct, 6) if delta_pct is not None else None,
        "completed_bar_count": len(persisted_bars),
        "contiguous_bar_count": len(contiguous_bars),
        "gap_detected": bool(gap_detected),
        "atr_status": atr_status,
        "feed_status": feed_status,
        "source": "rithmic_worker_atr_shadow",
        "alignment_confidence": "unverified_no_tv_source_bar_identity" if tv_atr is not None else "not_available",
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
    # RAPI historical aggregate bars have no canonical tick-built bar_id. They
    # remain useful diagnostics but may not seed trading-authoritative ATR.
    return None


def seed_atr_from_persisted_bars(bar_cache, symbol):
    normalized_symbol = str(symbol).upper()
    bars = list(bar_cache.get(normalized_symbol, ()))
    bar_count = len(bars)
    log_lines = [f"STATUS|recent_bars_loaded|{normalized_symbol}|count={bar_count}"]

    clear_atr_snapshot(
        normalized_symbol,
        reason="listener_authority_epoch_change_startup",
    )
    authoritative_count = sum(1 for bar in bars if is_authoritative_finalized_bar(bar))
    log_lines.append(
        "STATUS|canonical_atr_startup_fail_closed|"
        f"{normalized_symbol}|authoritative_finalized_bars={authoritative_count}|"
        "reason=await_first_full_post_start_finalized_bar"
    )
    return log_lines, None


def update_recent_bars(bar_cache, completed_bar, publish_shadow=True, publish_atr_mirror=True):
    symbol = completed_bar["symbol"]
    symbol_previously_present = symbol in bar_cache
    original_bars = bar_cache.get(symbol, deque(maxlen=MAX_PERSISTED_BARS))
    bars = deque(original_bars, maxlen=MAX_PERSISTED_BARS)
    requires_local_commit = bool(
        completed_bar.get("status") == "FINAL" and completed_bar.get("bar_id")
    )

    if bars and bars[-1]["timestamp"] == completed_bar["timestamp"]:
        existing_bar_id = bars[-1].get("bar_id")
        incoming_bar_id = completed_bar.get("bar_id")
        if existing_bar_id and incoming_bar_id:
            if existing_bar_id != incoming_bar_id:
                raise RuntimeError("conflicting_recent_finalized_bar_identity")
            completed_bar.clear()
            completed_bar.update(copy.deepcopy(bars[-1]))
            local_commit = commit_finalized_bar_to_local_journal(completed_bar)
            atr_commit = {
                "atr_local_commit_completed_at_utc": local_commit.get("local_commit_completed_at_utc"),
                "atr_local_commit_completed_unix_ns": local_commit.get("local_commit_completed_unix_ns"),
                "atr_local_commit_completed_monotonic_ns": local_commit.get("local_commit_completed_monotonic_ns"),
                "atr_local_journal_path": local_commit.get("local_journal_path"),
                "atr_commit_idempotent": local_commit.get("idempotent"),
            }
            return None, len(bars), None, {
                "entry_agent_available_at_utc": utc_now_precise_iso(),
                "entry_agent_available_unix_ns": time.time_ns(),
                "entry_agent_available_monotonic_ns": time.perf_counter_ns(),
                "idempotent": True,
                "already_exposed": True,
                **local_commit,
                **atr_commit,
            }
        bars[-1] = completed_bar
    elif bars and completed_bar["timestamp"] < bars[-1]["timestamp"]:
        return None, len(bars), None, None
    else:
        bars.append(completed_bar)

    if requires_local_commit:
        existing_atr_record = completed_bar.get("canonical_atr")
        if (
            isinstance(existing_atr_record, dict)
            and existing_atr_record.get("bar_id") == completed_bar.get("bar_id")
            and existing_atr_record.get("formula_version") == ATR_FORMULA_VERSION
        ):
            atr_record = copy.deepcopy(existing_atr_record)
        else:
            atr_record = build_canonical_atr_record(list(bars), completed_bar)
        authoritative_bar = copy.deepcopy(completed_bar)
        authoritative_bar["canonical_atr"] = copy.deepcopy(atr_record)
        completed_bar.clear()
        completed_bar.update(authoritative_bar)
        bars[-1] = completed_bar
    else:
        atr_record = None

    local_commit = {}
    atr_commit = {}
    if requires_local_commit:
        local_commit = commit_finalized_bar_to_local_journal(completed_bar)
        atr_commit = {
            "atr_local_commit_completed_at_utc": local_commit.get("local_commit_completed_at_utc"),
            "atr_local_commit_completed_unix_ns": local_commit.get("local_commit_completed_unix_ns"),
            "atr_local_commit_completed_monotonic_ns": local_commit.get("local_commit_completed_monotonic_ns"),
            "atr_local_journal_path": local_commit.get("local_journal_path"),
            "atr_commit_idempotent": local_commit.get("idempotent"),
        }

    bar_cache[symbol] = bars
    try:
        persist_recent_bars(bar_cache)
    except Exception as exc:
        # A bar that was not atomically exposed must not leak into a later
        # cache write as an old, newly visible decision candle.
        if symbol_previously_present:
            bar_cache[symbol] = original_bars
        else:
            bar_cache.pop(symbol, None)
        if requires_local_commit:
            raise FinalizedBarExposureError(
                sanitize_log_message(exc),
                local_commit=local_commit,
            ) from exc
        raise
    publication = {
        "entry_agent_available_at_utc": utc_now_precise_iso(),
        "entry_agent_available_unix_ns": time.time_ns(),
        "entry_agent_available_monotonic_ns": time.perf_counter_ns(),
        "idempotent": False,
        "already_exposed": False,
        **local_commit,
        **atr_commit,
    }
    persisted_count = len(bars)
    persisted_bars = list(bars)
    if publish_shadow:
        try:
            update_atr_shadow_comparison(
                symbol,
                persisted_bars,
                feed_status=get_feed_status(symbol),
            )
        except Exception as exc:
            print(f"RITHMIC WARNING|atr_shadow_update_failed|{symbol}|{sanitize_log_message(exc)}")
    try:
        if not isinstance(atr_record, dict):
            return None, persisted_count, "STATUS|atr_skipped_noncanonical_bar", publication
        if publish_atr_mirror:
            write_atr_snapshot(symbol, atr_record)
        publication.update({
            "entry_agent_available_at_utc": utc_now_precise_iso(),
            "entry_agent_available_unix_ns": time.time_ns(),
            "entry_agent_available_monotonic_ns": time.perf_counter_ns(),
        })
        if not atr_record.get("ready"):
            return None, persisted_count, build_contiguous_atr_skip_log(symbol, persisted_bars), publication
        return (
            build_atr_line(symbol, completed_bar["timestamp"], atr_record["updated_raw_atr"]),
            persisted_count,
            None,
            publication,
        )
    except Exception as exc:
        publication["atr_error"] = sanitize_log_message(exc)
        return None, persisted_count, None, publication


def build_powershell_bridge():
    return textwrap.dedent(
        r"""
        param(
            [string]$DllPath,
            [string]$MdConnectionPoint,
            [string]$TsConnectionPoint,
            [string]$RepositoryConnectionPoint,
            [int]$LoginTimeoutSeconds,
            [int]$DiagnosticDurationSeconds,
            [string]$Subscriptions
        )

        $ErrorActionPreference = "Stop"
        $UserName = [Environment]::GetEnvironmentVariable("RITHMIC_USER")
        $Password = [Environment]::GetEnvironmentVariable("RITHMIC_PASSWORD")
        if ([string]::IsNullOrWhiteSpace($UserName) -or [string]::IsNullOrWhiteSpace($Password)) {
            throw "Missing required Rithmic credentials in inherited environment"
        }

        Add-Type -Path $DllPath

        Add-Type -ReferencedAssemblies @($DllPath) -TypeDefinition @"
        using System;
        using System.Collections.Concurrent;
        using System.Collections.Generic;
        using System.Diagnostics;
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
            LoggedIn,
            ConnectionOpened,
            ConnectionBroken,
            ConnectionClosed
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
                public long CallbackSequence;
                public string Exchange;
                public string Symbol;
                public double Price;
                public long Size;
                public CallbackType CallbackType;
                public int SourceSsboe;
                public int SourceNsecs;
                public int SourceUsecs;
                public int Ssboe;
                public int Usecs;
                public int JopSsboe;
                public int JopNsecs;
                public DateTime CallbackReceiptUtc;
                public long CallbackReceiptUnixNs;
                public long CallbackReceiptStopwatchTicks;
                public string Condition;
                public string ExchOrdId;
                public string AggressorExchOrdId;
            }

            public BridgeLoginStatus RepositoryLoginStatus = BridgeLoginStatus.NotLoggedIn;
            public BridgeLoginStatus MarketDataLoginStatus = BridgeLoginStatus.NotLoggedIn;
            public BridgeLoginStatus TradingSystemLoginStatus = BridgeLoginStatus.NotLoggedIn;
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
            private readonly BlockingCollection<TickEvent> TickQueue = new BlockingCollection<TickEvent>();
            private readonly SortedDictionary<long, TickEvent> PendingTicks = new SortedDictionary<long, TickEvent>();
            private readonly Thread TickWriterThread;
            private long CallbackSequence = 0;
            private long NextSequenceToWrite = 1;

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
                TickWriterThread.Join();
            }

            public void RequestShutdown()
            {
                ShutdownRequested = true;
            }

            private BridgeLoginStatus GetStatus(ConnectionId connectionId)
            {
                if (connectionId == ConnectionId.Repository)
                {
                    return RepositoryLoginStatus;
                }
                if (connectionId == ConnectionId.MarketData)
                {
                    return MarketDataLoginStatus;
                }
                if (connectionId == ConnectionId.TradingSystem)
                {
                    return TradingSystemLoginStatus;
                }
                return BridgeLoginStatus.NotLoggedIn;
            }

            private void SetStatus(ConnectionId connectionId, BridgeLoginStatus status)
            {
                if (connectionId == ConnectionId.Repository)
                {
                    RepositoryLoginStatus = status;
                }
                else if (connectionId == ConnectionId.MarketData)
                {
                    MarketDataLoginStatus = status;
                }
                else if (connectionId == ConnectionId.TradingSystem)
                {
                    TradingSystemLoginStatus = status;
                }
            }

            public void ResetHistoricalReplayState()
            {
                HistoricalReplayRequested = false;
                HistoricalReplayStarted = false;
                HistoricalReplayTimedOut = false;
                HistoricalBarsReceived = 0;
                LastHistoricalReplayEventUtc = DateTime.MinValue;
            }

            private void EnqueueTick(TickEvent tick)
            {
                TickQueue.Add(tick);
            }

            private void DrainTicks()
            {
                foreach (TickEvent tick in TickQueue.GetConsumingEnumerable())
                {
                    PendingTicks[tick.CallbackSequence] = tick;
                    FlushContiguousTicks();
                }
                FlushContiguousTicks();
                if (PendingTicks.Count > 0)
                {
                    Console.WriteLine(
                        "AUTHORITY|bridge_sequence_gap|expected=" + NextSequenceToWrite.ToString() +
                        "|pending=" + PendingTicks.Count.ToString()
                    );
                }
            }

            private void FlushContiguousTicks()
            {
                TickEvent tick = null;
                while (PendingTicks.TryGetValue(NextSequenceToWrite, out tick))
                {
                    PendingTicks.Remove(NextSequenceToWrite);
                    PrintTick(tick);
                    NextSequenceToWrite++;
                }
            }

            private static string EscapeField(string value)
            {
                return Uri.EscapeDataString(value ?? String.Empty);
            }

            private void PrintTick(TickEvent tick)
            {
                Console.WriteLine(
                    "TICK|" +
                    tick.CallbackSequence.ToString() + "|" +
                    EscapeField(tick.Exchange) + "|" +
                    EscapeField(tick.Symbol) + "|" +
                    tick.Price.ToString(System.Globalization.CultureInfo.InvariantCulture) + "|" +
                    tick.Size.ToString() + "|" +
                    tick.CallbackType.ToString() + "|" +
                    tick.SourceSsboe.ToString() + "|" +
                    tick.SourceNsecs.ToString() + "|" +
                    tick.SourceUsecs.ToString() + "|" +
                    tick.Ssboe.ToString() + "|" +
                    tick.Usecs.ToString() + "|" +
                    tick.JopSsboe.ToString() + "|" +
                    tick.JopNsecs.ToString() + "|" +
                    tick.CallbackReceiptUtc.ToString("o") + "|" +
                    tick.CallbackReceiptUnixNs.ToString() + "|" +
                    tick.CallbackReceiptStopwatchTicks.ToString() + "|" +
                    EscapeField(tick.Condition) + "|" +
                    EscapeField(tick.ExchOrdId) + "|" +
                    EscapeField(tick.AggressorExchOrdId)
                );
            }

            public override void TradePrint(TradeInfo info)
            {
                long callbackSequence = Interlocked.Increment(ref CallbackSequence);
                DateTime callbackReceiptUtc = DateTime.UtcNow;
                long callbackReceiptUnixNs = (callbackReceiptUtc.Ticks - 621355968000000000L) * 100L;
                long callbackReceiptStopwatchTicks = Stopwatch.GetTimestamp();
                // Callback-safe only: copy immutable TradeInfo evidence, enqueue it losslessly, and return.
                // Logging, network posting, file writes, ATR/bar work, feed health, and summaries run in worker loops.
                string normalizedSymbol = String.IsNullOrWhiteSpace(info.Symbol) ? String.Empty : info.Symbol.Trim().ToUpperInvariant();
                string normalizedExchange = String.IsNullOrWhiteSpace(info.Exchange) ? String.Empty : info.Exchange.Trim().ToUpperInvariant();
                var tick = new TickEvent
                {
                    CallbackSequence = callbackSequence,
                    Exchange = normalizedExchange,
                    Symbol = normalizedSymbol,
                    Price = info.Price,
                    Size = info.Size,
                    CallbackType = info.CallbackType,
                    SourceSsboe = info.SourceSsboe,
                    SourceNsecs = info.SourceNsecs,
                    SourceUsecs = info.SourceUsecs,
                    Ssboe = info.Ssboe,
                    Usecs = info.Usecs,
                    JopSsboe = info.JopSsboe,
                    JopNsecs = info.JopNsecs,
                    CallbackReceiptUtc = callbackReceiptUtc,
                    CallbackReceiptUnixNs = callbackReceiptUnixNs,
                    CallbackReceiptStopwatchTicks = callbackReceiptStopwatchTicks,
                    Condition = info.Condition,
                    ExchOrdId = info.ExchOrdId,
                    AggressorExchOrdId = info.AggressorExchOrdId,
                };
                EnqueueTick(tick);
            }

            public override void Alert(AlertInfo info)
            {
                var sb = new StringBuilder();
                info.Dump(sb);
                string alertText = sb.ToString().Replace("\r", " ").Replace("\n", " ");
                string connection = info.ConnectionId.ToString();
                string alertType = info.AlertType.ToString();
                BridgeLoginStatus stateBefore = GetStatus(info.ConnectionId);
                BridgeLoginStatus stateAfter = stateBefore;

                if (alertType == "LoginComplete")
                {
                    stateAfter = BridgeLoginStatus.LoggedIn;
                }
                else if (alertType == "LoginFailed")
                {
                    stateAfter = BridgeLoginStatus.LoginFailed;
                }
                else if (alertType == "ConnectionOpened")
                {
                    stateAfter = BridgeLoginStatus.ConnectionOpened;
                }
                else if (alertType == "ConnectionBroken")
                {
                    stateAfter = BridgeLoginStatus.ConnectionBroken;
                }
                else if (alertType == "ConnectionClosed")
                {
                    stateAfter = BridgeLoginStatus.ConnectionClosed;
                }

                SetStatus(info.ConnectionId, stateAfter);
                Console.WriteLine("ALERT|" + alertText);
                Console.WriteLine(
                    "STATUS|connection_event|utc=" + DateTime.UtcNow.ToString("o") +
                    "|process_id=" + Process.GetCurrentProcess().Id.ToString() +
                    "|thread_id=" + Thread.CurrentThread.ManagedThreadId.ToString() +
                    "|connection=" + connection +
                    "|event=" + alertType +
                    "|state_before=" + stateBefore.ToString() +
                    "|state_after=" + stateAfter.ToString() +
                    "|rp_code=" + info.RpCode.ToString() +
                    "|request_id=unavailable_in_rapi_alert" +
                    "|shutdown_requested=" + ShutdownRequested.ToString()
                );

                if (info.ConnectionId == ConnectionId.Repository)
                {
                    if (alertType == "LoginComplete")
                    {
                        Console.WriteLine("STATUS|repository_login_complete");
                    }
                    else if (alertType == "LoginFailed")
                    {
                        Console.WriteLine("STATUS|repository_login_failed");
                    }
                }

                if (info.ConnectionId == ConnectionId.MarketData && alertType == "LoginComplete")
                {
                    LoggedIntoMd = true;
                    Console.WriteLine("STATUS|market_data_login_complete");
                    Console.WriteLine("STATUS|market_data_connected");
                }
                else if (info.ConnectionId == ConnectionId.MarketData && alertType == "LoginFailed")
                {
                    Console.WriteLine("STATUS|market_data_login_failed|rp_code=" + info.RpCode.ToString());
                }

                if (info.ConnectionId == ConnectionId.TradingSystem && alertType == "LoginComplete")
                {
                    LoggedIntoTs = true;
                    Console.WriteLine("STATUS|trading_system_login_complete");
                    Console.WriteLine("STATUS|trading_system_connected");
                }
                else if (info.ConnectionId == ConnectionId.TradingSystem && alertType == "LoginFailed")
                {
                    Console.WriteLine("STATUS|trading_system_login_failed|rp_code=" + info.RpCode.ToString());
                }

                if (alertType == "ForcedLogout")
                {
                    Console.WriteLine(
                        "STATUS|forced_logout|connection=" + connection +
                        "|rp_code=" + info.RpCode.ToString()
                    );
                }

                if (!ShutdownRequested && info.ConnectionId == ConnectionId.MarketData && alertType == "ConnectionClosed")
                {
                    MarketDataClosedUnexpectedly = true;
                    Console.WriteLine("STATUS|market_data_connection_closed_unexpected");
                }

                if (!ShutdownRequested && info.ConnectionId == ConnectionId.TradingSystem && alertType == "ConnectionClosed")
                {
                    TradingSystemClosedUnexpectedly = true;
                    Console.WriteLine("STATUS|trading_system_connection_closed_unexpected");
                }

                if (info.ConnectionId == ConnectionId.MarketData && alertType == "ConnectionBroken")
                {
                    Console.WriteLine("STATUS|market_data_connection_broken|sdk_recovery=owned_by_rapi");
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
                int loginTimeoutSeconds,
                int diagnosticDurationSeconds,
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
                    DateTime lastRepositoryLoginWaitUtc = DateTime.MinValue;
                    while (callbacks.RepositoryLoginStatus != BridgeLoginStatus.LoggedIn &&
                           callbacks.RepositoryLoginStatus != BridgeLoginStatus.LoginFailed)
                    {
                        if (callbacks.ShutdownRequested)
                        {
                            return 0;
                        }
                        if (DateTime.UtcNow.Subtract(repositoryLoginStartedUtc).TotalSeconds >= loginTimeoutSeconds)
                        {
                            Console.WriteLine("ERROR|repository_login_timeout|status=" + callbacks.RepositoryLoginStatus.ToString());
                            return 2;
                        }
                        if (lastRepositoryLoginWaitUtc == DateTime.MinValue ||
                            DateTime.UtcNow.Subtract(lastRepositoryLoginWaitUtc).TotalSeconds >= 5)
                        {
                            lastRepositoryLoginWaitUtc = DateTime.UtcNow;
                            Console.WriteLine(
                                "STATUS|repository_login_wait|elapsed_seconds=" +
                                ((int)DateTime.UtcNow.Subtract(repositoryLoginStartedUtc).TotalSeconds).ToString() +
                                "|status=" + callbacks.RepositoryLoginStatus.ToString()
                            );
                        }
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
                    callbacks.MarketDataLoginStatus = BridgeLoginStatus.LoginInProgress;
                    callbacks.TradingSystemLoginStatus = BridgeLoginStatus.LoginInProgress;
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

                    DateTime connectionLoginStartedUtc = DateTime.UtcNow;
                    DateTime lastConnectionLoginWaitUtc = DateTime.MinValue;
                    while (!callbacks.LoggedIntoMd || !callbacks.LoggedIntoTs)
                    {
                        if (callbacks.ShutdownRequested)
                        {
                            return 0;
                        }
                        if (callbacks.MarketDataLoginStatus == BridgeLoginStatus.LoginFailed ||
                            callbacks.TradingSystemLoginStatus == BridgeLoginStatus.LoginFailed ||
                            callbacks.MarketDataLoginStatus == BridgeLoginStatus.ConnectionClosed ||
                            callbacks.TradingSystemLoginStatus == BridgeLoginStatus.ConnectionClosed)
                        {
                            Console.WriteLine(
                                "ERROR|connection_login_failed|md_status=" + callbacks.MarketDataLoginStatus.ToString() +
                                "|ts_status=" + callbacks.TradingSystemLoginStatus.ToString()
                            );
                            return 4;
                        }
                        if (DateTime.UtcNow.Subtract(connectionLoginStartedUtc).TotalSeconds >= loginTimeoutSeconds)
                        {
                            Console.WriteLine(
                                "ERROR|connection_login_timeout|md_status=" + callbacks.MarketDataLoginStatus.ToString() +
                                "|ts_status=" + callbacks.TradingSystemLoginStatus.ToString()
                            );
                            return 4;
                        }
                        if (lastConnectionLoginWaitUtc == DateTime.MinValue ||
                            DateTime.UtcNow.Subtract(lastConnectionLoginWaitUtc).TotalSeconds >= 5)
                        {
                            lastConnectionLoginWaitUtc = DateTime.UtcNow;
                            Console.WriteLine(
                                "STATUS|connection_login_wait|elapsed_seconds=" +
                                ((int)DateTime.UtcNow.Subtract(connectionLoginStartedUtc).TotalSeconds).ToString() +
                                "|md_status=" + callbacks.MarketDataLoginStatus.ToString() +
                                "|ts_status=" + callbacks.TradingSystemLoginStatus.ToString()
                            );
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

                    Console.WriteLine("STATUS|subscription_generation|generation=1|count=" + subscriptionList.Count.ToString());

                    Console.WriteLine("STATUS|listener_service_running");
                    DateTime listenerServiceStartedUtc = DateTime.UtcNow;
                    DateTime lastHeartbeatUtc = DateTime.MinValue;
                    while (!callbacks.ShutdownRequested &&
                           !callbacks.MarketDataClosedUnexpectedly &&
                           !callbacks.TradingSystemClosedUnexpectedly)
                    {
                        if (diagnosticDurationSeconds > 0 &&
                            DateTime.UtcNow.Subtract(listenerServiceStartedUtc).TotalSeconds >= diagnosticDurationSeconds)
                        {
                            callbacks.RequestShutdown();
                            Console.WriteLine("STATUS|bounded_diagnostic_shutdown_requested|duration_seconds=" + diagnosticDurationSeconds.ToString());
                            break;
                        }
                        if (lastHeartbeatUtc == DateTime.MinValue ||
                            DateTime.UtcNow.Subtract(lastHeartbeatUtc).TotalSeconds >= 5)
                        {
                            lastHeartbeatUtc = DateTime.UtcNow;
                            Console.WriteLine(
                                "STATUS|listener_heartbeat|" +
                                "md_logged_in=" + callbacks.LoggedIntoMd.ToString() +
                                "|ts_logged_in=" + callbacks.LoggedIntoTs.ToString() +
                                "|md_state=" + callbacks.MarketDataLoginStatus.ToString() +
                                "|ts_state=" + callbacks.TradingSystemLoginStatus.ToString() +
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
            $LoginTimeoutSeconds,
            $DiagnosticDurationSeconds,
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
        newline="\n",
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
        "-MdConnectionPoint",
        RITHMIC_MD_CONNECTION_POINT,
        "-TsConnectionPoint",
        RITHMIC_TS_CONNECTION_POINT,
        "-RepositoryConnectionPoint",
        RITHMIC_REPOSITORY_CONNECTION_POINT,
        "-LoginTimeoutSeconds",
        str(RITHMIC_LOGIN_TIMEOUT_SECONDS),
        "-DiagnosticDurationSeconds",
        str(RITHMIC_DIAGNOSTIC_DURATION_SECONDS),
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


def allocate_executor_listener_generation(timeout_seconds=3.0):
    payload = {
        "listener_pid": os.getpid(),
        "authority_mutex": LISTENER_AUTHORITY_MUTEX_NAME,
        "symbols": sorted(ACTIVE_LIVE_MARKET_ROOTS),
    }
    request = urllib.request.Request(
        EXECUTOR_LISTENER_GENERATION_URL,
        data=json.dumps(payload, sort_keys=True).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=float(timeout_seconds)) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"executor_generation_allocation_http_{exc.code}:{details}") from exc
    except Exception as exc:
        raise RuntimeError(f"executor_generation_allocation_failed:{exc}") from exc

    if not isinstance(body, dict) or body.get("ok") is not True:
        raise RuntimeError(f"executor_generation_allocation_invalid_response:{body}")
    try:
        generation = int(body.get("generation"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("executor_generation_allocation_missing_generation") from exc
    if generation < 1:
        raise RuntimeError("executor_generation_allocation_invalid_generation")
    return generation


def forward_price_to_executor(
    symbol,
    price,
    update_health=True,
    tick_timestamp_utc=None,
    timeout_seconds=None,
    step6_intrabar_path=None,
    listener_sequence=None,
    listener_tick_id=None,
    callback_receipt_timestamp_utc=None,
    python_receipt_timestamp_utc=None,
    source_ssboe=None,
    source_nsecs=None,
    source_usecs=None,
    log_failure=True,
):
    timestamp_utc = utc_now_iso()

    def reject(reason):
        if update_health and str(symbol or "").strip():
            update_feed_health(symbol, "last_executor_price_post_failure_timestamp_utc", timestamp_utc)
        return False, reason

    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol:
        return False, "missing_symbol"
    try:
        normalized_price = float(price)
    except (TypeError, ValueError):
        return reject("price_not_numeric")
    if not math.isfinite(normalized_price):
        return reject("non_finite_price")
    if normalized_price <= 0:
        return reject("price_not_positive")

    feed_status = derive_executor_price_feed_status(normalized_symbol, tick_timestamp_utc=tick_timestamp_utc)
    if not feed_status:
        return reject("missing_feed_status")
    if feed_status in {"STALE", "DEAD", "DISCONNECTED"}:
        return reject("stale_tick_timestamp_utc")

    payload = json.dumps({
        "symbol": normalized_symbol,
        "price": normalized_price,
        "tick_timestamp_utc": tick_timestamp_utc or timestamp_utc,
        "feed_status": feed_status,
        "step6_intrabar_path": step6_intrabar_path,
        "listener_sequence": listener_sequence,
        "listener_tick_id": listener_tick_id,
        "callback_receipt_timestamp_utc": callback_receipt_timestamp_utc,
        "python_receipt_timestamp_utc": python_receipt_timestamp_utc,
        "source_ssboe": source_ssboe,
        "source_nsecs": source_nsecs,
        "source_usecs": source_usecs,
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
                if log_failure:
                    print(
                        "RITHMIC WARNING|executor_price_forward_failed|"
                        f"symbol={symbol}|price={price}|status={response.status}"
                    )
                if update_health:
                    update_feed_health(symbol, "last_executor_price_post_failure_timestamp_utc", timestamp_utc)
                return False, reason
            else:
                if update_health:
                    record_executor_price_post_success(
                        normalized_symbol,
                        normalized_price,
                        tick_timestamp_utc or timestamp_utc,
                        timestamp_utc,
                    )
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
        if log_failure:
            print(
                "RITHMIC WARNING|executor_price_forward_failed|"
                f"symbol={symbol}|price={price}|status={exc.code}|reason={sanitize_log_message(reason)}"
            )
        if update_health:
            update_feed_health(symbol, "last_executor_price_post_failure_timestamp_utc", timestamp_utc)
        return False, reason
    except TimeoutError:
        reason = "timed out"
        if log_failure:
            print(
                "RITHMIC WARNING|executor_price_forward_failed|"
                f"symbol={symbol}|price={price}|error={reason}"
            )
        if update_health:
            update_feed_health(symbol, "last_executor_price_post_failure_timestamp_utc", timestamp_utc)
        return False, reason
    except urllib.error.URLError as exc:
        reason = str(exc.reason if hasattr(exc, "reason") else exc)
        if log_failure:
            print(
                "RITHMIC WARNING|executor_price_forward_failed|"
                f"symbol={symbol}|price={price}|error={exc}"
            )
        if update_health:
            update_feed_health(symbol, "last_executor_price_post_failure_timestamp_utc", timestamp_utc)
        return False, reason


def parse_tick_line(line, bridge_generation=0):
    parts = line.split("|", 19)
    if len(parts) != 20 or parts[0] != "TICK":
        raise ValueError("invalid_canonical_tick_line")

    hashes = runtime_source_hashes()
    tick = {
        "callback_sequence": int(parts[1]),
        "exchange": urllib.parse.unquote(parts[2]).strip().upper(),
        "symbol": urllib.parse.unquote(parts[3]).strip().upper(),
        "price": float(parts[4]),
        "size": int(parts[5]),
        "callback_type": parts[6],
        "source_ssboe": int(parts[7]),
        "source_nsecs": int(parts[8]),
        "source_usecs": int(parts[9]),
        "rithmic_ssboe": int(parts[10]),
        "rithmic_usecs": int(parts[11]),
        "jop_ssboe": int(parts[12]),
        "jop_nsecs": int(parts[13]),
        "callback_receipt_timestamp_utc": parts[14],
        "callback_receipt_unix_ns": int(parts[15]),
        "callback_receipt_stopwatch_ticks": int(parts[16]),
        "condition": urllib.parse.unquote(parts[17]),
        "exchange_order_id": urllib.parse.unquote(parts[18]),
        "aggressor_exchange_order_id": urllib.parse.unquote(parts[19]),
        "python_receipt_timestamp_utc": utc_now_precise_iso(),
        "python_receipt_monotonic_ns": time.perf_counter_ns(),
        "bridge_generation": int(bridge_generation),
        **hashes,
    }
    try:
        exchange_time_ns = exchange_time_ns_from_fields(
            tick["source_ssboe"],
            tick["source_nsecs"],
            tick["source_usecs"],
        )
        tick["exchange_time_ns"] = exchange_time_ns
        tick["exchange_timestamp_utc"] = exchange_time_iso_from_ns(exchange_time_ns)
        tick["candle_assignment"] = minute_timestamp_from_exchange_ns(exchange_time_ns)
        tick["timestamp"] = tick["exchange_timestamp_utc"]
        tick["source_timestamp_error"] = None
    except ValueError as exc:
        tick["exchange_time_ns"] = None
        tick["exchange_timestamp_utc"] = None
        tick["candle_assignment"] = None
        tick["timestamp"] = None
        tick["source_timestamp_error"] = str(exc)
    return tick


def _intrabar_bucket(minute_timestamp):
    return {
        "minute": minute_timestamp,
        "points": deque(maxlen=STEP6_INTRABAR_PATH_MAX_POINTS),
        "truncated": False,
    }


def append_step6_intrabar_price_point(symbol, tick_timestamp, price):
    normalized_symbol = str(symbol or "").upper()
    if not normalized_symbol:
        return
    minute_timestamp = minute_timestamp_from_tick(tick_timestamp)
    state = step6_intrabar_paths_by_symbol.get(normalized_symbol)
    current_bucket = state.get("current_minute") if isinstance(state, dict) else None

    if not isinstance(current_bucket, dict) or current_bucket.get("minute") != minute_timestamp:
        previous_bucket = current_bucket if isinstance(current_bucket, dict) else None
        state = {
            "current_minute": _intrabar_bucket(minute_timestamp),
            "previous_minute": previous_bucket,
        }
        step6_intrabar_paths_by_symbol[normalized_symbol] = state
        current_bucket = state["current_minute"]

    points = current_bucket["points"]
    if points and points[-1][1] == float(price):
        return
    if len(points) >= STEP6_INTRABAR_PATH_MAX_POINTS:
        current_bucket["truncated"] = True
    points.append((str(tick_timestamp), float(price)))


def serialize_step6_intrabar_bucket(bucket):
    if not isinstance(bucket, dict):
        return None
    points = bucket.get("points")
    if not isinstance(points, deque):
        return None
    return {
        "minute": bucket.get("minute"),
        "points": [[timestamp, float(price)] for timestamp, price in points],
        "truncated": bool(bucket.get("truncated")),
        "price_change_only": True,
        "max_points": STEP6_INTRABAR_PATH_MAX_POINTS,
    }


def build_step6_intrabar_path_payload(symbol):
    state = step6_intrabar_paths_by_symbol.get(str(symbol or "").upper())
    if not isinstance(state, dict):
        return None
    current_bucket = serialize_step6_intrabar_bucket(state.get("current_minute"))
    previous_bucket = serialize_step6_intrabar_bucket(state.get("previous_minute"))
    if current_bucket is None and previous_bucket is None:
        return None
    return {
        "current_minute": current_bucket,
        "previous_minute": previous_bucket,
    }


@dataclass(frozen=True)
class PriceDeliveryEvent:
    symbol: str
    price: float
    tick_timestamp_utc: str
    callback_sequence: object
    listener_tick_id: object
    callback_receipt_timestamp_utc: object
    python_receipt_timestamp_utc: object
    python_receipt_monotonic_ns: int
    enqueued_monotonic_ns: int
    source_ssboe: object
    source_nsecs: object
    source_usecs: object
    step6_intrabar_path: object


PRICE_DELIVERY_STOP = object()


def update_latest_price_from_tick(tick, price_publisher=None):
    symbol = str(tick.get("symbol") or "").upper()
    if not symbol:
        return False
    timestamp = tick.get("exchange_timestamp_utc") or tick.get("timestamp")
    if not timestamp or str(tick.get("callback_type") or "Update") != "Update":
        return False
    price = float(tick["price"])
    now = time.monotonic()
    with latest_price_lock:
        latest_price_by_symbol[symbol] = price
        latest_tick_time_by_symbol[symbol] = timestamp
        latest_tick_monotonic_by_symbol[symbol] = now
        raw_callback_count[symbol] += 1
        append_step6_intrabar_price_point(symbol, timestamp, price)
    LIVE_TICK_SYMBOLS.add(symbol)
    if price_publisher is not None:
        try:
            price_publisher.enqueue_tick(tick)
        except Exception as exc:
            print(
                "RITHMIC ERROR|price_delivery_enqueue_failed|"
                f"symbol={symbol}|price={price}|source_timestamp={timestamp}|"
                f"callback_sequence={tick.get('callback_sequence')}|"
                f"error={sanitize_log_message(exc)}"
            )
    return True


def new_price_delivery_metrics():
    return {
        "enqueued": 0,
        "attempts": 0,
        "successes": 0,
        "timeouts": 0,
        "other_failures": 0,
        "completed": 0,
        "in_flight": 0,
        "queue_depth": 0,
        "max_queue_depth": 0,
        "receipt_to_post_start_total_ms": 0.0,
        "receipt_to_post_start_max_ms": 0.0,
        "post_duration_total_ms": 0.0,
        "post_duration_max_ms": 0.0,
        "last_receipt_to_post_start_ms": None,
        "last_post_duration_ms": None,
        "last_callback_sequence": None,
        "last_source_timestamp_utc": None,
        "last_failure": None,
    }


class SymbolPriceWorker:
    def __init__(self, publisher, symbol):
        self.publisher = publisher
        self.symbol = str(symbol).upper()
        self.events = queue.Queue()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(
            target=self.run,
            name=f"rithmic_price_publisher_{self.symbol}",
            daemon=True,
        )
        self.thread.start()

    def enqueue(self, event):
        self.events.put_nowait(event)

    def run(self):
        while True:
            event = self.events.get()
            try:
                if event is PRICE_DELIVERY_STOP:
                    return
                self.publisher.deliver_event(self, event)
            finally:
                self.events.task_done()

    def process_one_nowait(self):
        try:
            event = self.events.get_nowait()
        except queue.Empty:
            return False
        try:
            if event is PRICE_DELIVERY_STOP:
                return False
            self.publisher.deliver_event(self, event)
            return True
        finally:
            self.events.task_done()

    def stop(self):
        self.events.put_nowait(PRICE_DELIVERY_STOP)
        if self.thread is not None:
            self.thread.join()


class PricePublisher:
    def __init__(self, subscribed_symbols=None):
        self.subscribed_symbols = sorted({
            str(symbol or "").upper()
            for symbol in (subscribed_symbols or [])
            if symbol
        })
        self.workers = {
            symbol: SymbolPriceWorker(self, symbol)
            for symbol in self.subscribed_symbols
        }
        self.metrics_lock = threading.Lock()
        self.delivery_metrics = {
            symbol: new_price_delivery_metrics()
            for symbol in self.subscribed_symbols
        }
        self.audit_events = queue.Queue()
        self.audit_thread = None
        self.started = False

    def start(self):
        if self.started:
            return
        self.started = True
        self.audit_thread = threading.Thread(
            target=self.run_audit,
            name="rithmic_price_delivery_audit",
            daemon=True,
        )
        self.audit_thread.start()
        for worker in self.workers.values():
            worker.start()

    def stop(self):
        for worker in self.workers.values():
            worker.stop()
        self.audit_events.put_nowait(PRICE_DELIVERY_STOP)
        if self.audit_thread is not None:
            self.audit_thread.join()
        self.started = False

    def enqueue_tick(self, tick):
        symbol = str(tick.get("symbol") or "").upper()
        worker = self.workers.get(symbol)
        if worker is None:
            raise ValueError(f"price_delivery_symbol_not_subscribed:{symbol or 'UNKNOWN'}")
        tick_timestamp = tick.get("exchange_timestamp_utc") or tick.get("timestamp")
        if not tick_timestamp:
            raise ValueError("price_delivery_missing_source_timestamp")
        if str(tick.get("callback_type") or "Update") != "Update":
            return False
        callback_sequence = tick.get("callback_sequence")
        bridge_generation = int(tick.get("bridge_generation") or 0)
        listener_tick_id = (
            f"{bridge_generation}:{int(callback_sequence)}"
            if callback_sequence is not None
            else None
        )
        now_ns = time.perf_counter_ns()
        with latest_price_lock:
            step6_intrabar_path = copy.deepcopy(build_step6_intrabar_path_payload(symbol))
        event = PriceDeliveryEvent(
            symbol=symbol,
            price=float(tick["price"]),
            tick_timestamp_utc=str(tick_timestamp),
            callback_sequence=callback_sequence,
            listener_tick_id=listener_tick_id,
            callback_receipt_timestamp_utc=tick.get("callback_receipt_timestamp_utc"),
            python_receipt_timestamp_utc=tick.get("python_receipt_timestamp_utc"),
            python_receipt_monotonic_ns=int(tick.get("python_receipt_monotonic_ns") or now_ns),
            enqueued_monotonic_ns=now_ns,
            source_ssboe=tick.get("source_ssboe"),
            source_nsecs=tick.get("source_nsecs"),
            source_usecs=tick.get("source_usecs"),
            step6_intrabar_path=step6_intrabar_path,
        )
        with self.metrics_lock:
            metrics = self.delivery_metrics[symbol]
            metrics["enqueued"] += 1
        worker.enqueue(event)
        with self.metrics_lock:
            metrics = self.delivery_metrics[symbol]
            metrics["queue_depth"] = worker.events.qsize()
            metrics["max_queue_depth"] = max(metrics["max_queue_depth"], metrics["queue_depth"])
        return True

    def deliver_event(self, worker, event):
        post_started_ns = time.perf_counter_ns()
        receipt_to_start_ms = round(
            max(0, post_started_ns - event.python_receipt_monotonic_ns) / 1_000_000.0,
            3,
        )
        with self.metrics_lock:
            metrics = self.delivery_metrics[event.symbol]
            metrics["attempts"] += 1
            metrics["in_flight"] += 1
            metrics["queue_depth"] = worker.events.qsize()

        try:
            result = forward_price_to_executor(
                event.symbol,
                event.price,
                update_health=False,
                tick_timestamp_utc=event.tick_timestamp_utc,
                timeout_seconds=EXECUTOR_PRICE_POST_TIMEOUT_SECONDS,
                step6_intrabar_path=event.step6_intrabar_path,
                listener_sequence=event.callback_sequence,
                listener_tick_id=event.listener_tick_id,
                callback_receipt_timestamp_utc=event.callback_receipt_timestamp_utc,
                python_receipt_timestamp_utc=event.python_receipt_timestamp_utc,
                source_ssboe=event.source_ssboe,
                source_nsecs=event.source_nsecs,
                source_usecs=event.source_usecs,
                log_failure=False,
            )
        except Exception as exc:
            result = False, sanitize_log_message(exc)

        post_duration_ms = round((time.perf_counter_ns() - post_started_ns) / 1_000_000.0, 3)
        ok, reason = (True, None) if result is None else result
        reason = None if ok else str(reason or "unknown_price_post_failure")
        completed_at_utc = utc_now_precise_iso()

        with self.metrics_lock:
            metrics = self.delivery_metrics[event.symbol]
            metrics["in_flight"] -= 1
            metrics["completed"] += 1
            metrics["queue_depth"] = worker.events.qsize()
            metrics["last_receipt_to_post_start_ms"] = receipt_to_start_ms
            metrics["last_post_duration_ms"] = post_duration_ms
            metrics["last_callback_sequence"] = event.callback_sequence
            metrics["last_source_timestamp_utc"] = event.tick_timestamp_utc
            metrics["receipt_to_post_start_total_ms"] += receipt_to_start_ms
            metrics["receipt_to_post_start_max_ms"] = max(
                metrics["receipt_to_post_start_max_ms"],
                receipt_to_start_ms,
            )
            metrics["post_duration_total_ms"] += post_duration_ms
            metrics["post_duration_max_ms"] = max(metrics["post_duration_max_ms"], post_duration_ms)
            if ok:
                metrics["successes"] += 1
                metrics["last_failure"] = None
            elif "timed out" in reason.lower() or "timeout" in reason.lower():
                metrics["timeouts"] += 1
                metrics["last_failure"] = reason
            else:
                metrics["other_failures"] += 1
                metrics["last_failure"] = reason
            metrics_snapshot = self.metrics_snapshot_locked(event.symbol)

        audit_record = {
            "record_type": "rithmic_price_delivery",
            "symbol": event.symbol,
            "price": event.price,
            "rithmic_source_timestamp_utc": event.tick_timestamp_utc,
            "callback_sequence": event.callback_sequence,
            "listener_tick_id": event.listener_tick_id,
            "callback_receipt_timestamp_utc": event.callback_receipt_timestamp_utc,
            "python_receipt_timestamp_utc": event.python_receipt_timestamp_utc,
            "destination": EXECUTOR_PRICE_URL,
            "receipt_to_post_start_ms": receipt_to_start_ms,
            "post_duration_ms": post_duration_ms,
            "completed_at_utc": completed_at_utc,
            "success": bool(ok),
            "failure": reason,
            "metrics": metrics_snapshot,
        }
        self.audit_events.put_nowait(audit_record)

    def metrics_snapshot_locked(self, symbol):
        metrics = dict(self.delivery_metrics[symbol])
        attempts = int(metrics["attempts"])
        metrics["receipt_to_post_start_average_ms"] = round(
            metrics["receipt_to_post_start_total_ms"] / attempts,
            3,
        ) if attempts else 0.0
        metrics["post_duration_average_ms"] = round(
            metrics["post_duration_total_ms"] / attempts,
            3,
        ) if attempts else 0.0
        metrics.pop("receipt_to_post_start_total_ms", None)
        metrics.pop("post_duration_total_ms", None)
        return metrics

    def metrics_snapshot(self, symbol=None):
        with self.metrics_lock:
            if symbol is not None:
                return self.metrics_snapshot_locked(str(symbol).upper())
            return {
                key: self.metrics_snapshot_locked(key)
                for key in self.subscribed_symbols
            }

    def run_audit(self):
        while True:
            record = self.audit_events.get()
            try:
                if record is PRICE_DELIVERY_STOP:
                    return
                self.process_audit_record(record)
            except Exception as exc:
                print(f"RITHMIC WARNING|price_delivery_audit_failed|{sanitize_log_message(exc)}")
            finally:
                self.audit_events.task_done()

    def process_audit_record(self, record):
        if record["success"]:
            print(
                f"PRICE|{record['symbol']}|{record['price']}|"
                f"source_ts={record['rithmic_source_timestamp_utc']}|"
                f"callback_sequence={record['callback_sequence']}|"
                f"receipt_to_post_start_ms={record['receipt_to_post_start_ms']}|"
                f"post_duration_ms={record['post_duration_ms']}"
            )
        else:
            failure_record = dict(record)
            failure_record["record_type"] = "rithmic_price_delivery_failure"
            try:
                append_jsonl_record(PRICE_DELIVERY_FAILURES_PATH, failure_record)
            except Exception as exc:
                print(
                    "RITHMIC ERROR|price_delivery_failure_audit_write_failed|"
                    f"symbol={record['symbol']}|callback_sequence={record['callback_sequence']}|"
                    f"error={sanitize_log_message(exc)}"
                )
            print(
                "RITHMIC WARNING|executor_price_delivery_failed|"
                f"symbol={record['symbol']}|price={record['price']}|"
                f"source_timestamp={record['rithmic_source_timestamp_utc']}|"
                f"callback_sequence={record['callback_sequence']}|"
                f"destination={record['destination']}|"
                f"receipt_to_post_start_ms={record['receipt_to_post_start_ms']}|"
                f"post_duration_ms={record['post_duration_ms']}|"
                f"failure={sanitize_log_message(record['failure'])}"
            )
        self.persist_delivery_audit(record)

    @staticmethod
    def persist_delivery_audit(record):
        symbol = str(record["symbol"]).upper()
        payload = read_feed_health()
        symbols = payload.setdefault("symbols", {})
        for alias in build_snapshot_symbol_aliases(symbol):
            entry = symbols.setdefault(alias, {})
            entry["resolved_contract"] = symbol
            entry["price_delivery"] = dict(record["metrics"])
            entry["executor_publish_latency_ms"] = record["post_duration_ms"]
            if record["success"]:
                entry["latest_price"] = float(record["price"])
                entry["latest_listener_price"] = float(record["price"])
                entry["last_listener_price_timestamp_utc"] = record["rithmic_source_timestamp_utc"]
                entry["last_bridge_post_timestamp_utc"] = record["completed_at_utc"]
                entry["last_successful_executor_price_post_timestamp_utc"] = record["completed_at_utc"]
                entry["last_executor_publish_at"] = record["completed_at_utc"]
                entry["last_executor_price_post_failure_reason"] = None
            else:
                entry["last_executor_price_post_failure_timestamp_utc"] = record["completed_at_utc"]
                entry["last_executor_price_post_failure_reason"] = record["failure"]
                entry["executor_price_post_failure_count"] = (
                    int(record["metrics"]["timeouts"])
                    + int(record["metrics"]["other_failures"])
                )
        refresh_feed_health_statuses(
            payload,
            reference_time=parse_utc_timestamp(record["completed_at_utc"]),
        )
        write_feed_health(payload)

    def publish_once(self, symbol=None):
        selected = [str(symbol).upper()] if symbol is not None else self.subscribed_symbols
        processed = 0
        for selected_symbol in selected:
            worker = self.workers.get(selected_symbol)
            if worker is not None and worker.process_one_nowait():
                processed += 1
        while True:
            try:
                record = self.audit_events.get_nowait()
            except queue.Empty:
                break
            try:
                if record is not PRICE_DELIVERY_STOP:
                    self.process_audit_record(record)
            finally:
                self.audit_events.task_done()
        return processed

    def wait_for_idle(self):
        for worker in self.workers.values():
            worker.events.join()
        self.audit_events.join()


def minute_timestamp_from_tick(tick_timestamp):
    parsed = parse_utc_timestamp(tick_timestamp)
    if parsed is None:
        raise ValueError("missing_exchange_tick_timestamp")
    minute = parsed.replace(second=0, microsecond=0)
    return minute.isoformat() + "Z"


def session_archive_contains_finalized_bar(completed_bar):
    record = build_session_bar_record(completed_bar)
    if not isinstance(record, dict):
        return False
    target_path = session_bar_path(record["root_symbol"], record["session_date"])
    if not target_path.exists():
        return False
    expected = canonical_finalized_bar_json(record)
    with target_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                existing = json.loads(text)
            except Exception:
                continue
            if isinstance(existing, dict) and existing.get("bar_id") == record.get("bar_id"):
                if canonical_finalized_bar_json(existing) != expected:
                    raise RuntimeError("conflicting_finalized_bar_identity")
                return True
    return False


class SessionArchiveReconciler:
    def __init__(self, incident_callback=None, append_function=None):
        self.incident_callback = incident_callback
        self.append_function = append_function or append_session_bar_record
        self.events = queue.Queue()
        self.thread = None
        self.lock = threading.Lock()
        self.pending = {}
        self.queued = set()
        self.completed = {}
        self.incidents = []

    def start(self):
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                return
            self.thread = threading.Thread(
                target=self.run,
                name="rithmic_session_archive_reconciler",
                daemon=True,
            )
            self.thread.start()

    def submit(self, completed_bar):
        bar_id = str(completed_bar.get("bar_id") or "")
        if not bar_id:
            raise ValueError("archive_reconciliation_missing_bar_id")
        self.start()
        with self.lock:
            existing = self.pending.get(bar_id)
            if existing is not None:
                if canonical_finalized_bar_json(existing) != canonical_finalized_bar_json(completed_bar):
                    raise RuntimeError("conflicting_archive_reconciliation_identity")
            elif bar_id in self.completed:
                if self.completed[bar_id] != canonical_finalized_bar_json(completed_bar):
                    raise RuntimeError("conflicting_archive_reconciliation_identity")
            else:
                self.pending[bar_id] = completed_bar
            for pending_bar_id in tuple(self.pending):
                if pending_bar_id not in self.queued:
                    self.queued.add(pending_bar_id)
                    self.events.put_nowait(pending_bar_id)
        return bar_id

    def run(self):
        while True:
            bar_id = self.events.get()
            try:
                if bar_id is None:
                    return
                with self.lock:
                    completed_bar = self.pending.get(bar_id)
                if completed_bar is None:
                    continue
                try:
                    self.append_function(completed_bar)
                except Exception as exc:
                    self.record_incident(
                        "finalized_bar_archive_reconciliation_failed",
                        symbol=completed_bar.get("symbol"),
                        bar_id=bar_id,
                        minute=completed_bar.get("timestamp"),
                        error=sanitize_log_message(exc),
                    )
                else:
                    with self.lock:
                        self.pending.pop(bar_id, None)
                        self.completed[bar_id] = canonical_finalized_bar_json(completed_bar)
            finally:
                with self.lock:
                    self.queued.discard(bar_id)
                self.events.task_done()

    def record_incident(self, incident_type, **details):
        try:
            if self.incident_callback is not None:
                record = self.incident_callback(incident_type, **details)
            else:
                record = append_data_authority_incident(incident_type, **details)
        except Exception as exc:
            record = {
                "record_type": "market_data_authority_incident",
                "incident_type": str(incident_type),
                "recorded_at_utc": utc_now_precise_iso(),
                "incident_persistence_error": sanitize_log_message(exc),
                **details,
            }
            print(
                "RITHMIC ERROR|archive_reconciliation_incident_persistence_failed|"
                f"type={incident_type}|error={sanitize_log_message(exc)}"
            )
        self.incidents.append(record)
        return record

    def wait_for_idle(self):
        self.events.join()

    def stop(self):
        if self.thread is None:
            return
        self.wait_for_idle()
        self.events.put_nowait(None)
        self.events.join()
        self.thread.join(timeout=30)
        self.thread = None


def recover_local_finalized_bar_journal(bar_cache, archive_reconciler):
    cached_bar_ids = {
        str(bar.get("bar_id"))
        for bars in bar_cache.values()
        for bar in bars
        if bar.get("bar_id")
    }
    recovered = {
        "journal_record_count": 0,
        "committed_but_unexposed_count": 0,
        "submitted_for_reconciliation_count": 0,
    }
    for record in load_local_finalized_bar_journal():
        recovered["journal_record_count"] += 1
        bar_id = str(record["bar_id"])
        already_archived = session_archive_contains_finalized_bar(record)
        if bar_id not in cached_bar_ids and not already_archived:
            append_data_authority_incident(
                "finalized_bar_committed_but_not_exposed_recovery",
                symbol=record.get("symbol"),
                bar_id=bar_id,
                minute=record.get("timestamp"),
                recovery_action="historical_archive_reconciliation_only",
                live_cache_exposure=False,
            )
            recovered["committed_but_unexposed_count"] += 1
        if not already_archived:
            archive_reconciler.submit(record)
            recovered["submitted_for_reconciliation_count"] += 1
    return recovered


class TickWorker:
    def __init__(
        self,
        bar_cache,
        subscribed_symbols=None,
        enforce_startup_warmup=False,
        archive_reconciler=None,
        price_publisher=None,
    ):
        self.bar_cache = bar_cache
        self.subscribed_symbols = [str(symbol or "").upper() for symbol in (subscribed_symbols or []) if symbol]
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = None
        self.latest_prices = {}
        self.current_tick_bars = {}
        self.published_minutes = defaultdict(dict)
        self.enforce_startup_warmup = bool(enforce_startup_warmup)
        self.bridge_generation = 0
        self.expected_callback_sequence = 1
        self.pending_sequence_ticks = {}
        self.authority_incidents = []
        self.publication_latencies = []
        self.atr_transition_latencies = []
        self.finalized_bars = []
        self.atr_authority_blocked_symbols = set()
        self.pending_exposure_bars = defaultdict(dict)
        self.pending_exposure_retry_failures = defaultdict(int)
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
        self.price_publisher = price_publisher
        self.archive_reconciler = archive_reconciler or SessionArchiveReconciler(
            incident_callback=self.record_authority_incident,
        )
        self.owns_archive_reconciler = archive_reconciler is None
        for symbol, bars in self.bar_cache.items():
            for bar in bars:
                if bar.get("status") == "FINAL" and bar.get("bar_id"):
                    self.published_minutes[str(symbol).upper()][str(bar.get("timestamp"))] = bar.get("bar_id")

    def retain_committed_unexposed_bar(self, completed_bar):
        """Keep an exact locally committed bar in canonical memory until shared exposure succeeds."""
        symbol = str(completed_bar.get("symbol") or "").upper()
        bar_id = str(completed_bar.get("bar_id") or "")
        if not symbol or not bar_id:
            return
        retained = copy.deepcopy(completed_bar)
        bars_by_timestamp = {
            str(bar.get("timestamp")): copy.deepcopy(bar)
            for bar in self.bar_cache.get(symbol, ())
            if isinstance(bar, dict) and bar.get("timestamp")
        }
        existing = bars_by_timestamp.get(str(retained.get("timestamp")))
        if existing and existing.get("bar_id") not in {None, bar_id}:
            raise RuntimeError("conflicting_pending_finalized_bar_identity")
        bars_by_timestamp[str(retained["timestamp"])] = retained
        ordered = [bars_by_timestamp[key] for key in sorted(bars_by_timestamp)]
        self.bar_cache[symbol] = deque(
            ordered[-MAX_PERSISTED_BARS:],
            maxlen=MAX_PERSISTED_BARS,
        )
        self.pending_exposure_bars[symbol][bar_id] = retained

    def complete_pending_exposure(self, symbol, publication_source):
        """Publish mirrors and archive rows after retained bars become atomically visible."""
        symbol = str(symbol or "").upper()
        pending = self.pending_exposure_bars.get(symbol)
        if not pending:
            return 0
        retained = sorted(
            pending.values(),
            key=lambda bar: (str(bar.get("timestamp") or ""), str(bar.get("bar_id") or "")),
        )
        for bar in retained:
            self.archive_reconciler.submit(bar)
            self.published_minutes[symbol][str(bar.get("timestamp"))] = bar.get("bar_id")
            if not any(existing.get("bar_id") == bar.get("bar_id") for existing in self.finalized_bars):
                self.finalized_bars.append(copy.deepcopy(bar))
        self.pending_exposure_bars.pop(symbol, None)
        self.pending_exposure_retry_failures.pop(symbol, None)
        bars = list(self.bar_cache.get(symbol, ()))
        latest_atr = bars[-1].get("canonical_atr") if bars else None
        self.publish_atr_mirrors(symbol, latest_atr, bars)
        self.record_authority_incident(
            "committed_finalized_bar_exposure_reconciled",
            symbol=symbol,
            recovered_bar_ids=[bar.get("bar_id") for bar in retained],
            recovered_minutes=[bar.get("timestamp") for bar in retained],
            publication_source=publication_source,
            atr_reset=False,
        )
        return len(retained)

    def retry_pending_exposure(self, symbol):
        """Retry the shared availability projection without discarding canonical history."""
        symbol = str(symbol or "").upper()
        if not self.pending_exposure_bars.get(symbol):
            return True
        try:
            persist_recent_bars(self.bar_cache)
        except Exception as exc:
            self.pending_exposure_retry_failures[symbol] += 1
            self.queue_feed_health(
                symbol,
                "canonical_exposure_retry_error",
                sanitize_log_message(exc),
            )
            return False
        self.complete_pending_exposure(symbol, "subsequent_same_symbol_tick")
        return True

    def start(self):
        self.thread = threading.Thread(target=self.run, name="rithmic_tick_worker", daemon=True)
        self.thread.start()

    def stop(self):
        if self.thread is not None:
            self.events.join()
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=30)
            if self.thread.is_alive():
                self.record_authority_incident("canonical_worker_shutdown_timeout")
        self.flush_feed_health(force=True)
        if self.owns_archive_reconciler:
            self.archive_reconciler.stop()

    def begin_bridge_generation(self, generation):
        normalized_generation = int(generation)
        if normalized_generation == self.bridge_generation and self.expected_callback_sequence == 1:
            return
        if self.current_tick_bars:
            for symbol, state in list(self.current_tick_bars.items()):
                self.record_authority_incident(
                    "bridge_generation_changed_with_incomplete_minute",
                    symbol=symbol,
                    incomplete_minute=state.get("timestamp"),
                    previous_generation=self.bridge_generation,
                    new_generation=normalized_generation,
                )
        self.current_tick_bars.clear()
        self.pending_sequence_ticks.clear()
        self.expected_callback_sequence = 1
        self.bridge_generation = normalized_generation

    def invalidate_current_bars(self, reason):
        for symbol, state in self.current_tick_bars.items():
            state["incomplete"] = True
            self.record_authority_incident(
                "canonical_stream_interruption",
                symbol=symbol,
                incomplete_minute=state.get("timestamp"),
                reason=str(reason),
                bridge_generation=self.bridge_generation,
            )

    def enqueue_tick(self, tick):
        canonical_tick = dict(tick)
        symbol = str(canonical_tick.get("symbol") or "").upper()
        canonical_tick["symbol"] = symbol
        if symbol:
            LIVE_TICK_SYMBOLS.add(symbol)
        self.events.put_nowait({"type": "tick", "tick": canonical_tick})
        return True

    def enqueue_completed_bar(self, completed_bar):
        return self.enqueue_event({"type": "bar", "bar": completed_bar})

    def enqueue_event(self, event):
        self.events.put_nowait(event)
        return True

    def run(self):
        while not self.stop_event.is_set() or not self.events.empty():
            try:
                event = self.events.get(timeout=0.1)
            except queue.Empty:
                if self.stop_event.is_set():
                    break
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

            try:
                self.flush_feed_health_if_due()
            except Exception as e:
                print(f"RITHMIC WARNING|feed_health_flush_failed|{sanitize_log_message(e)}")
            self.print_summary_if_due()

    def process_tick(self, tick):
        canonical_tick = self.prepare_canonical_tick(tick)
        sequence = canonical_tick.get("callback_sequence")
        if sequence is None:
            write_raw_tick_evidence(canonical_tick)
            self.record_authority_incident("missing_internal_callback_sequence", canonical_tick)
            return False

        generation = int(canonical_tick.get("bridge_generation") or 0)
        if generation != self.bridge_generation:
            self.begin_bridge_generation(generation)

        sequence = int(sequence)
        if sequence < self.expected_callback_sequence:
            write_raw_tick_evidence(canonical_tick)
            self.record_authority_incident(
                "duplicate_or_regressed_internal_callback_sequence",
                canonical_tick,
                expected_sequence=self.expected_callback_sequence,
            )
            return False
        if sequence > self.expected_callback_sequence:
            write_raw_tick_evidence(canonical_tick)
            canonical_tick["_raw_evidence_written"] = True
            self.pending_sequence_ticks[sequence] = canonical_tick
            self.record_authority_incident(
                "internal_callback_sequence_gap",
                canonical_tick,
                expected_sequence=self.expected_callback_sequence,
                observed_sequence=sequence,
            )
            return False

        self.process_contiguous_tick(canonical_tick)
        self.expected_callback_sequence += 1
        while self.expected_callback_sequence in self.pending_sequence_ticks:
            pending = self.pending_sequence_ticks.pop(self.expected_callback_sequence)
            self.process_contiguous_tick(pending)
            self.expected_callback_sequence += 1
        return True

    def prepare_canonical_tick(self, tick):
        canonical_tick = dict(tick)
        canonical_tick["symbol"] = str(canonical_tick.get("symbol") or "").upper()
        canonical_tick["exchange"] = str(canonical_tick.get("exchange") or "").upper()
        canonical_tick.setdefault("bridge_generation", self.bridge_generation)
        canonical_tick.setdefault("callback_type", "Update")
        canonical_tick.setdefault("python_receipt_timestamp_utc", utc_now_precise_iso())
        canonical_tick.setdefault("python_receipt_monotonic_ns", time.perf_counter_ns())
        canonical_tick.update({
            key: canonical_tick.get(key) or value
            for key, value in runtime_source_hashes().items()
        })
        if canonical_tick.get("exchange_time_ns") is None:
            try:
                canonical_tick["exchange_time_ns"] = exchange_time_ns_from_fields(
                    canonical_tick.get("source_ssboe"),
                    canonical_tick.get("source_nsecs"),
                    canonical_tick.get("source_usecs"),
                )
                canonical_tick["source_timestamp_error"] = None
            except ValueError as exc:
                canonical_tick["source_timestamp_error"] = str(exc)
        if canonical_tick.get("exchange_time_ns") is not None:
            exchange_time_ns = int(canonical_tick["exchange_time_ns"])
            canonical_tick["exchange_timestamp_utc"] = exchange_time_iso_from_ns(exchange_time_ns)
            canonical_tick["candle_assignment"] = minute_timestamp_from_exchange_ns(exchange_time_ns)
            canonical_tick["timestamp"] = canonical_tick["exchange_timestamp_utc"]
        else:
            canonical_tick["exchange_timestamp_utc"] = None
            canonical_tick["candle_assignment"] = None
            canonical_tick["timestamp"] = None
        return canonical_tick

    def process_contiguous_tick(self, tick):
        if not tick.get("_raw_evidence_written"):
            write_raw_tick_evidence(tick)

        if str(tick.get("callback_type") or "") != "Update":
            return False
        if tick.get("exchange_time_ns") is None:
            self.record_authority_incident(
                "missing_or_invalid_rithmic_source_timestamp",
                tick,
                reason=tick.get("source_timestamp_error"),
            )
            return False

        symbol = tick.get("symbol")
        if not symbol or not tick.get("exchange"):
            self.record_authority_incident("missing_exchange_or_contract", tick)
            return False
        try:
            price = float(tick["price"])
        except (TypeError, ValueError):
            self.record_authority_incident("invalid_trade_price", tick)
            return False
        if not math.isfinite(price):
            self.record_authority_incident("invalid_trade_price", tick)
            return False

        timestamp = tick["exchange_timestamp_utc"]
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
            self.record_authority_incident("price_sanity_warning_canonical_trade_retained", tick, reason=price_reason)
        else:
            self.queue_feed_health(symbol, "price_sanity_status", "OK")
            self.queue_feed_health(symbol, "price_sanity_reason", None)
        tick_count = self.ticks_processed[symbol] + 1
        self.latest_prices[symbol] = price
        self.ticks_processed[symbol] = tick_count
        self.last_tick_timestamps[symbol] = timestamp
        reset_dead_restart_guard(symbol)
        self.queue_feed_health(symbol, "last_tick_timestamp_utc", timestamp)
        if self.pending_exposure_bars.get(symbol):
            if self.retry_pending_exposure(symbol):
                self.atr_authority_blocked_symbols.discard(symbol)
            else:
                self.atr_authority_blocked_symbols.add(symbol)
        # Candle ownership is resolved before the tick can reach any trading
        # consumer. On a minute transition this synchronously finalizes and
        # durably exposes the prior bar plus its matching canonical ATR.
        bar_result = self.update_tick_bar(tick)
        if bar_result.get("suppress_trading_release"):
            return False
        if bar_result.get("authority_failed"):
            self.atr_authority_blocked_symbols.add(symbol)
            return False
        if bar_result.get("transition_published"):
            self.atr_authority_blocked_symbols.discard(symbol)

        # The outbound event is copied to a lossless symbol FIFO; network work
        # remains outside this canonical worker and candle construction.
        if symbol in self.atr_authority_blocked_symbols:
            self.record_authority_incident(
                "trading_tick_withheld_atr_authority_blocked",
                tick,
                reason="prior_finalized_bar_or_atr_not_durably_exposed",
            )
            return False
        update_latest_price_from_tick(tick, price_publisher=self.price_publisher)
        released_monotonic_ns = time.perf_counter_ns()
        if bar_result.get("is_transition"):
            publication = bar_result.get("publication") or {}
            received_monotonic_ns = tick.get("python_receipt_monotonic_ns")
            finalized_monotonic_ns = bar_result.get("prior_bar_finalized_monotonic_ns")
            atr_ready_monotonic_ns = publication.get("atr_local_commit_completed_monotonic_ns")

            def elapsed_ms(start, end):
                if start is None or end is None:
                    return None
                return round((int(end) - int(start)) / 1_000_000.0, 3)

            latency = {
                "record_type": "rithmic_atr_transition_latency",
                "symbol_root": normalize_symbol_root(symbol),
                "contract_symbol": symbol,
                "transition_tick_id": tick.get("listener_tick_id"),
                "transition_callback_sequence": tick.get("callback_sequence"),
                "transition_exchange_timestamp_utc": tick.get("exchange_timestamp_utc"),
                "prior_bar_id": bar_result.get("prior_bar_id"),
                "atr_record_id": bar_result.get("atr_record_id"),
                "transition_tick_received_to_prior_bar_finalized_ms": elapsed_ms(
                    received_monotonic_ns, finalized_monotonic_ns
                ),
                "prior_bar_finalized_to_atr_durably_ready_ms": elapsed_ms(
                    finalized_monotonic_ns, atr_ready_monotonic_ns
                ),
                "atr_durably_ready_to_transition_tick_released_ms": elapsed_ms(
                    atr_ready_monotonic_ns, released_monotonic_ns
                ),
                "total_transition_tick_hold_ms": elapsed_ms(
                    received_monotonic_ns, released_monotonic_ns
                ),
                "recorded_at_utc": utc_now_precise_iso(),
                **runtime_source_hashes(),
            }
            append_jsonl_record(ATR_TRANSITION_LATENCY_PATH, latency, durable=False)
            self.atr_transition_latencies.append(latency)
            print(
                "RITHMIC LATENCY|atr_transition|"
                f"symbol={symbol}|bar_id={latency['prior_bar_id']}|"
                f"atr_record_id={latency['atr_record_id']}|"
                f"finalize_ms={latency['transition_tick_received_to_prior_bar_finalized_ms']}|"
                f"atr_durable_ms={latency['prior_bar_finalized_to_atr_durably_ready_ms']}|"
                f"release_ms={latency['atr_durably_ready_to_transition_tick_released_ms']}|"
                f"total_hold_ms={latency['total_transition_tick_hold_ms']}"
            )
            bars_for_shadow = list(self.bar_cache.get(symbol, ()))
            canonical_atr = None
            if bars_for_shadow:
                canonical_atr = bars_for_shadow[-1].get("canonical_atr")
            self.publish_atr_mirrors(symbol, canonical_atr, bars_for_shadow)
        return True

    def publish_atr_mirrors(self, symbol, canonical_atr, bars):
        try:
            if isinstance(canonical_atr, dict):
                write_atr_snapshot(symbol, canonical_atr)
        except Exception as exc:
            print(f"RITHMIC WARNING|atr_snapshot_mirror_failed|{symbol}|{sanitize_log_message(exc)}")
        try:
            comparison = update_atr_shadow_comparison(
                symbol,
                bars,
                feed_status=get_feed_status(symbol),
            )
            print(f"RITHMIC {build_atr_shadow_log_line(comparison)}")
        except Exception as exc:
            print(f"RITHMIC WARNING|atr_shadow_update_failed|{symbol}|{sanitize_log_message(exc)}")

    @staticmethod
    def tick_order_key(tick):
        return int(tick["exchange_time_ns"]), int(tick["callback_sequence"])

    @staticmethod
    def tick_digest_payload(tick):
        return json.dumps({
            "exchange": tick.get("exchange"),
            "symbol": tick.get("symbol"),
            "price": float(tick["price"]),
            "size": int(tick.get("size") or 0),
            "callback_type": tick.get("callback_type"),
            "source_ssboe": int(tick.get("source_ssboe") or 0),
            "source_nsecs": int(tick.get("source_nsecs") or 0),
            "source_usecs": int(tick.get("source_usecs") or 0),
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def new_tick_bar(self, tick, incomplete=False):
        minute_start_ns = minute_start_ns_from_exchange_time(tick["exchange_time_ns"])
        digest = hashlib.sha256()
        state = {
            "timestamp": minute_timestamp_from_exchange_ns(minute_start_ns),
            "minute_start_ns": minute_start_ns,
            "minute_end_ns": minute_start_ns + NANOSECONDS_PER_MINUTE,
            "symbol": tick["symbol"],
            "exchange": tick["exchange"],
            "incomplete": bool(incomplete),
            "tick_count": 0,
            "tick_digest": digest,
        }
        self.apply_tick_to_bar(state, tick)
        return state

    def apply_tick_to_bar(self, state, tick):
        price = float(tick["price"])
        order_key = self.tick_order_key(tick)
        state["tick_digest"].update(self.tick_digest_payload(tick))
        state["tick_count"] += 1
        if state["tick_count"] == 1:
            state.update({
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "open_key": order_key,
                "close_key": order_key,
                "open_tick": tick,
                "close_tick": tick,
                "first_callback_sequence": int(tick["callback_sequence"]),
                "last_callback_sequence": int(tick["callback_sequence"]),
            })
            return
        state["high"] = max(state["high"], price)
        state["low"] = min(state["low"], price)
        if order_key < state["open_key"]:
            state["open"] = price
            state["open_key"] = order_key
            state["open_tick"] = tick
        if order_key > state["close_key"]:
            state["close"] = price
            state["close_key"] = order_key
            state["close_tick"] = tick
        state["first_callback_sequence"] = min(state["first_callback_sequence"], int(tick["callback_sequence"]))
        state["last_callback_sequence"] = max(state["last_callback_sequence"], int(tick["callback_sequence"]))

    def update_tick_bar(self, tick):
        symbol = tick["symbol"]
        minute_start_ns = minute_start_ns_from_exchange_time(tick["exchange_time_ns"])
        minute_timestamp = minute_timestamp_from_exchange_ns(minute_start_ns)
        current = self.current_tick_bars.get(symbol)
        if current is None:
            self.current_tick_bars[symbol] = self.new_tick_bar(
                tick,
                incomplete=self.enforce_startup_warmup,
            )
            return {"is_transition": False, "transition_published": False, "authority_failed": False}

        if minute_start_ns < current["minute_start_ns"]:
            published_bar_id = self.published_minutes[symbol].get(minute_timestamp)
            self.record_authority_incident(
                "late_trade_after_publication",
                tick,
                published_bar_id=published_bar_id,
                active_minute=current["timestamp"],
            )
            return {
                "is_transition": False,
                "transition_published": False,
                "authority_failed": False,
                "suppress_trading_release": True,
            }

        if minute_start_ns == current["minute_start_ns"]:
            self.apply_tick_to_bar(current, tick)
            return {"is_transition": False, "transition_published": False, "authority_failed": False}

        publication = None
        completed = None
        finalized_monotonic_ns = None
        authority_failed = False
        if current.get("incomplete"):
            self.record_authority_incident(
                "startup_or_reconnect_incomplete_minute_not_published",
                tick,
                incomplete_minute=current["timestamp"],
            )
            self.record_authority_incident(
                "canonical_atr_continuity_preserved_across_incomplete_reconnect_minute",
                symbol=symbol,
                incomplete_minute=current["timestamp"],
                reason="transient_bridge_generation_change_does_not_invalidate_completed_history",
                atr_reset=False,
            )
        else:
            completed = self.build_finalized_bar(current, transition_tick=tick)
            finalized_monotonic_ns = time.perf_counter_ns()
            publication = self.process_completed_bar(completed, source="tick_derived_exchange_time")
            if publication:
                self.published_minutes[symbol][completed["timestamp"]] = completed["bar_id"]
                self.finalized_bars.append(completed)
            else:
                authority_failed = True

        self.current_tick_bars[symbol] = self.new_tick_bar(tick, incomplete=False)
        canonical_atr = completed.get("canonical_atr") if isinstance(completed, dict) else None
        return {
            "is_transition": completed is not None,
            "transition_published": publication is not None,
            "authority_failed": authority_failed,
            "publication": publication,
            "prior_bar_finalized_monotonic_ns": finalized_monotonic_ns,
            "prior_bar_id": completed.get("bar_id") if isinstance(completed, dict) else None,
            "atr_record_id": canonical_atr.get("atr_record_id") if isinstance(canonical_atr, dict) else None,
        }

    def build_finalized_bar(self, state, transition_tick):
        hashes = runtime_source_hashes()
        timestamp = state["timestamp"]
        session_date = local_session_date_from_timestamp(timestamp)
        open_tick = state["open_tick"]
        close_tick = state["close_tick"]
        market_identity = {
            "builder_contract_version": BAR_BUILDER_CONTRACT_VERSION,
            "exchange": state["exchange"],
            "contract_symbol": state["symbol"],
            "exchange_minute_start_ns": state["minute_start_ns"],
            "open": float(state["open"]),
            "high": float(state["high"]),
            "low": float(state["low"]),
            "close": float(state["close"]),
            "tick_count": int(state["tick_count"]),
            "tick_stream_sha256": state["tick_digest"].hexdigest(),
        }
        bar_id = sha256_bytes(json.dumps(market_identity, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        return {
            "session_date": session_date,
            "root_symbol": normalize_symbol_root(state["symbol"]),
            "exchange": state["exchange"],
            "contract_symbol": state["symbol"],
            "symbol": state["symbol"],
            "timestamp": timestamp,
            "exchange_minute_start_ns": state["minute_start_ns"],
            "exchange_minute_end_ns": state["minute_end_ns"],
            "open": float(state["open"]),
            "high": float(state["high"]),
            "low": float(state["low"]),
            "close": float(state["close"]),
            "tick_count": int(state["tick_count"]),
            "tick_stream_sha256": state["tick_digest"].hexdigest(),
            "open_exchange_time_ns": int(open_tick["exchange_time_ns"]),
            "open_exchange_timestamp_utc": open_tick["exchange_timestamp_utc"],
            "open_callback_sequence": int(open_tick["callback_sequence"]),
            "close_exchange_time_ns": int(close_tick["exchange_time_ns"]),
            "close_exchange_timestamp_utc": close_tick["exchange_timestamp_utc"],
            "close_callback_sequence": int(close_tick["callback_sequence"]),
            "first_callback_sequence": int(state["first_callback_sequence"]),
            "last_callback_sequence": int(state["last_callback_sequence"]),
            "finalized_by_callback_sequence": int(transition_tick["callback_sequence"]),
            "transition_exchange_time_ns": int(transition_tick["exchange_time_ns"]),
            "transition_exchange_timestamp_utc": transition_tick["exchange_timestamp_utc"],
            "transition_callback_receipt_timestamp_utc": transition_tick.get("callback_receipt_timestamp_utc"),
            "transition_callback_receipt_unix_ns": transition_tick.get("callback_receipt_unix_ns"),
            "transition_python_receipt_timestamp_utc": transition_tick.get("python_receipt_timestamp_utc"),
            "transition_python_receipt_monotonic_ns": transition_tick.get("python_receipt_monotonic_ns"),
            "status": "FINAL",
            "source": "rithmic_live_listener_exchange_time",
            "timestamp_policy": RITHMIC_TIMESTAMP_POLICY,
            "builder_contract_version": BAR_BUILDER_CONTRACT_VERSION,
            "bar_id": bar_id,
            "recorded_at": utc_now_precise_iso(),
            **hashes,
        }

    def process_completed_bar(self, completed_bar, source):
        symbol = completed_bar["symbol"]
        self.queue_feed_health(symbol, "last_bar_timestamp_utc", completed_bar["timestamp"])
        print(
            "RITHMIC STATUS|completed_1m_bar|"
            f"{completed_bar['timestamp']}|{symbol}|source={source}"
        )
        try:
            atr_line, persisted_count, atr_skip_log, publication = update_recent_bars(
                self.bar_cache,
                completed_bar,
                publish_shadow=False,
                publish_atr_mirror=False,
            )
        except FinalizedBarLocalCommitError as exc:
            self.record_authority_incident(
                "finalized_bar_local_commit_failed_before_publication",
                symbol=symbol,
                bar_id=completed_bar.get("bar_id"),
                minute=completed_bar.get("timestamp"),
                error=sanitize_log_message(exc),
            )
            return False
        except FinalizedBarExposureError as exc:
            self.record_authority_incident(
                "finalized_bar_committed_but_not_exposed",
                symbol=symbol,
                bar_id=completed_bar.get("bar_id"),
                minute=completed_bar.get("timestamp"),
                local_journal_path=exc.local_commit.get("local_journal_path"),
                error=sanitize_log_message(exc),
            )
            try:
                atr_line, persisted_count, atr_skip_log, publication = update_recent_bars(
                    self.bar_cache,
                    completed_bar,
                    publish_shadow=False,
                    publish_atr_mirror=False,
                )
                publication["cache_publication_retried"] = True
            except Exception as retry_exc:
                self.record_authority_incident(
                    "finalized_bar_committed_but_not_exposed_retry_failed",
                    symbol=symbol,
                    bar_id=completed_bar.get("bar_id"),
                    minute=completed_bar.get("timestamp"),
                    error=sanitize_log_message(retry_exc),
                )
                self.retain_committed_unexposed_bar(completed_bar)
                return False
        except Exception as exc:
            self.record_authority_incident(
                "finalized_bar_publication_failed",
                symbol=symbol,
                bar_id=completed_bar.get("bar_id"),
                minute=completed_bar.get("timestamp"),
                error=sanitize_log_message(exc),
            )
            return False
        if self.pending_exposure_bars.get(symbol):
            self.complete_pending_exposure(symbol, "later_finalized_bar_atomic_projection")
        if completed_bar.get("status") == "FINAL" and completed_bar.get("bar_id"):
            self.archive_reconciler.submit(completed_bar)
        if publication and publication.get("atr_error"):
            print(
                "RITHMIC WARNING|post_publication_atr_update_failed|"
                f"{symbol}|bar_id={completed_bar.get('bar_id')}|"
                f"error={publication['atr_error']}"
            )
            self.record_authority_incident(
                "canonical_atr_exposure_failed_transition_tick_withheld",
                symbol=symbol,
                bar_id=completed_bar.get("bar_id"),
                atr_record_id=(completed_bar.get("canonical_atr") or {}).get("atr_record_id"),
                error=publication["atr_error"],
            )
            return False
        print("RITHMIC STATUS|recent_bars_persisted|" f"{symbol}|count={persisted_count}")
        if completed_bar.get("bar_id") and publication:
            receipt_unix_ns = completed_bar.get("transition_callback_receipt_unix_ns")
            available_unix_ns = publication.get("entry_agent_available_unix_ns")
            available_monotonic_ns = publication.get("entry_agent_available_monotonic_ns")
            python_receipt_monotonic_ns = completed_bar.get("transition_python_receipt_monotonic_ns")
            local_commit_unix_ns = publication.get("local_commit_completed_unix_ns")
            local_commit_monotonic_ns = publication.get("local_commit_completed_monotonic_ns")
            boundary_to_receipt_ms = None
            receipt_to_local_commit_ms = None
            local_commit_to_availability_ms = None
            receipt_to_availability_ms = None
            python_receipt_to_local_commit_ms = None
            python_receipt_to_availability_ms = None
            if receipt_unix_ns is not None:
                boundary_to_receipt_ms = round(
                    (int(receipt_unix_ns) - int(completed_bar["exchange_minute_end_ns"])) / 1_000_000.0,
                    3,
                )
                receipt_to_availability_ms = round(
                    (int(available_unix_ns) - int(receipt_unix_ns)) / 1_000_000.0,
                    3,
                )
                if local_commit_unix_ns is not None:
                    receipt_to_local_commit_ms = round(
                        (int(local_commit_unix_ns) - int(receipt_unix_ns)) / 1_000_000.0,
                        3,
                    )
                    local_commit_to_availability_ms = round(
                        (int(available_unix_ns) - int(local_commit_unix_ns)) / 1_000_000.0,
                        3,
                    )
            if python_receipt_monotonic_ns is not None and available_monotonic_ns is not None:
                python_receipt_to_availability_ms = round(
                    (int(available_monotonic_ns) - int(python_receipt_monotonic_ns)) / 1_000_000.0,
                    3,
                )
                if local_commit_monotonic_ns is not None:
                    python_receipt_to_local_commit_ms = round(
                        (int(local_commit_monotonic_ns) - int(python_receipt_monotonic_ns)) / 1_000_000.0,
                        3,
                    )
            latency_record = {
                "record_type": "rithmic_bar_publication_latency",
                "bar_id": completed_bar["bar_id"],
                "exchange": completed_bar.get("exchange"),
                "contract_symbol": completed_bar.get("contract_symbol"),
                "bar_timestamp": completed_bar["timestamp"],
                "exchange_minute_end_ns": completed_bar["exchange_minute_end_ns"],
                "transition_callback_sequence": completed_bar["finalized_by_callback_sequence"],
                "transition_callback_receipt_timestamp_utc": completed_bar.get("transition_callback_receipt_timestamp_utc"),
                "local_commit_completed_at_utc": publication.get("local_commit_completed_at_utc"),
                "entry_agent_available_at_utc": publication["entry_agent_available_at_utc"],
                "exchange_boundary_to_first_next_minute_trade_receipt_ms": boundary_to_receipt_ms,
                "next_minute_trade_receipt_to_local_durable_commit_ms": receipt_to_local_commit_ms,
                "local_durable_commit_to_entry_agent_availability_ms": local_commit_to_availability_ms,
                "next_minute_trade_receipt_to_entry_agent_availability_ms": receipt_to_availability_ms,
                "python_receipt_to_local_durable_commit_ms": python_receipt_to_local_commit_ms,
                "python_receipt_to_entry_agent_availability_ms": python_receipt_to_availability_ms,
                "local_authoritative_journal_path": publication.get("local_journal_path"),
                "canonical_queue_depth_at_publication": self.events.qsize(),
                "recorded_at_utc": utc_now_precise_iso(),
                "listener_source_sha256": completed_bar.get("listener_source_sha256"),
                "generated_bridge_sha256": completed_bar.get("generated_bridge_sha256"),
            }
            append_jsonl_record(BAR_PUBLICATION_LATENCY_PATH, latency_record, durable=True)
            self.publication_latencies.append(latency_record)
            self.queue_feed_health(symbol, "last_bar_id", completed_bar["bar_id"])
            self.queue_feed_health(symbol, "last_bar_entry_agent_available_at_utc", publication["entry_agent_available_at_utc"])
            self.queue_feed_health(symbol, "last_bar_publication_latency_ms", receipt_to_availability_ms)
            print(
                "RITHMIC LATENCY|completed_1m_bar|"
                f"symbol={symbol}|bar_id={completed_bar['bar_id']}|"
                f"boundary_to_receipt_ms={boundary_to_receipt_ms}|"
                f"receipt_to_local_commit_ms={receipt_to_local_commit_ms}|"
                f"local_commit_to_entry_agent_ms={local_commit_to_availability_ms}|"
                f"receipt_to_entry_agent_ms={receipt_to_availability_ms}"
            )
        if atr_line is not None:
            print(f"RITHMIC {atr_line}")
            print("RITHMIC STATUS|atr_published|" f"{completed_bar['timestamp']}|{symbol}")
        elif atr_skip_log is not None:
            print(f"RITHMIC {atr_skip_log}")
        return publication

    def record_authority_incident(self, incident_type, tick=None, **details):
        record = append_data_authority_incident(incident_type, tick=tick, **details)
        self.authority_incidents.append(record)
        symbol = str((tick or {}).get("symbol") or details.get("symbol") or "").upper()
        if symbol:
            self.queue_feed_health(symbol, "last_data_authority_incident_type", str(incident_type))
            self.queue_feed_health(symbol, "last_data_authority_incident_at_utc", record["recorded_at_utc"])
        print(
            "RITHMIC AUTHORITY|incident|"
            f"type={incident_type}|incident_id={record['incident_id']}|symbol={symbol or 'UNKNOWN'}"
        )
        return record

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
                entry["resolved_contract"] = symbol
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
            live_or_quiet = [
                symbol for symbol in subscribed_symbols
                if entries.get(symbol, {}).get("feed_status") in {"LIVE", "QUIET"}
            ]
            terminal_symbols = sorted(set(disconnected) | set(frozen_bridge))
            connection_closed = (
                bool(BRIDGE_CONNECTION_HEALTH.get("market_data_closed"))
                or bool(BRIDGE_CONNECTION_HEALTH.get("trading_system_closed"))
            )
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
            if connection_closed and not terminal_symbols:
                print(
                    "RITHMIC WARNING|bridge_connection_closed_reconnect|"
                    f"market_data_closed={BRIDGE_CONNECTION_HEALTH.get('market_data_closed')}|"
                    f"trading_system_closed={BRIDGE_CONNECTION_HEALTH.get('trading_system_closed')}"
                )
                terminate_process(process)
                return
            if live_or_quiet and not connection_closed:
                for symbol in disconnected:
                    entry = entries.get(symbol, {})
                    age_seconds = entry.get("feed_age_seconds")
                    if age_seconds is None:
                        last_tick = parse_utc_timestamp(entry.get("last_tick_timestamp_utc"))
                        if last_tick is not None:
                            reference_time = datetime.now(timezone.utc).replace(tzinfo=None)
                            age_seconds = max(0.0, (reference_time - last_tick).total_seconds())
                    age_text = "unknown" if age_seconds is None else f"{float(age_seconds):.3f}"
                    print(
                        "RITHMIC STATUS|dead_restart_skipped_symbol_only|"
                        f"symbol={symbol}|age_seconds={age_text}|"
                        f"live_or_quiet_symbols={len(live_or_quiet)}"
                    )
                continue
            if not connection_closed and len(terminal_symbols) < len(tracked):
                continue
            restart_candidates = terminal_symbols
            for symbol in restart_candidates:
                entry = entries.get(symbol, {})
                if symbol in frozen_bridge and str(entry.get("feed_status") or "").upper() != "DEAD":
                    entry = {
                        "feed_status": "DEAD",
                        "last_tick_timestamp_utc": entry.get("last_tick_timestamp_utc"),
                        "feed_age_seconds": RESTART_DEAD_THRESHOLD_SECONDS + 1,
                    }
                if maybe_restart_listener(symbol, entry, process):
                    return
    thread = threading.Thread(target=watch, name="rithmic_disconnect_watchdog", daemon=True)
    thread.start()
    return stop_event, thread


def run_listener_service():
    validate_env()
    listener_started_at_utc = utc_now_precise_iso()
    subscriptions = parse_rithmic_subscriptions()
    command = build_command()
    bar_cache = load_recent_bars()
    retired_cleanup = prune_retired_live_runtime_state(bar_cache)
    runtime_metadata = publish_listener_runtime_metadata(subscriptions, started_at_utc=listener_started_at_utc)
    archive_reconciler = SessionArchiveReconciler()
    recovery = recover_local_finalized_bar_journal(bar_cache, archive_reconciler)
    persisted_bar_count = sum(len(bars) for bars in bar_cache.values())
    subscribed_symbols = [symbol.upper() for _, symbol in subscriptions]
    print("RITHMIC STATUS|startup_begin")
    print(f"RITHMIC STATUS|dll_path|{RAPIPLUS_DLL_PATH}")
    print(f"RITHMIC STATUS|listener_process_id|{os.getpid()}")
    print(f"RITHMIC STATUS|listener_started_at_utc|{listener_started_at_utc}")
    print(f"RITHMIC STATUS|listener_source_sha256|{runtime_metadata['listener_source_sha256']}")
    print(f"RITHMIC STATUS|generated_bridge_sha256|{runtime_metadata['generated_bridge_sha256']}")
    print(f"RITHMIC STATUS|timestamp_policy|{RITHMIC_TIMESTAMP_POLICY}")
    print(f"RITHMIC STATUS|bar_builder_contract_version|{BAR_BUILDER_CONTRACT_VERSION}")
    print("RITHMIC STATUS|price_delivery_policy|independent_symbol_fifo_lossless_no_coalescing")
    print(
        "RITHMIC STATUS|local_authoritative_journal_path|"
        f"{LOCAL_FINALIZED_BAR_JOURNAL_PATH.resolve()}"
    )
    print(
        "RITHMIC STATUS|local_atr_authority_journal_path|"
        f"{LOCAL_ATR_AUTHORITY_JOURNAL_PATH.resolve()}"
    )
    print(
        "RITHMIC STATUS|atr_authority_policy|"
        f"formula={ATR_FORMULA}|version={ATR_FORMULA_VERSION}|"
        "transition_tick_release=after_prior_bar_and_atr_authority_exposure"
    )
    print(
        "RITHMIC STATUS|local_authoritative_journal_recovery|"
        f"records={recovery['journal_record_count']}|"
        f"committed_but_unexposed={recovery['committed_but_unexposed_count']}|"
        f"submitted_for_reconciliation={recovery['submitted_for_reconciliation_count']}"
    )
    print(
        "RITHMIC STATUS|retired_live_market_cleanup|"
        + "|".join(
            f"{store}={','.join(symbols) or 'none'}"
            for store, symbols in retired_cleanup.items()
        )
    )
    print(f"RITHMIC STATUS|md_connection_point|{RITHMIC_MD_CONNECTION_POINT}")
    print(f"RITHMIC STATUS|ts_connection_point|{RITHMIC_TS_CONNECTION_POINT}")
    print(f"RITHMIC STATUS|repository_connection_point|{RITHMIC_REPOSITORY_CONNECTION_POINT}")
    print(f"RITHMIC STATUS|login_timeout_seconds|{RITHMIC_LOGIN_TIMEOUT_SECONDS}")
    if RITHMIC_DIAGNOSTIC_DURATION_SECONDS > 0:
        print(f"RITHMIC STATUS|bounded_diagnostic_duration_seconds|{RITHMIC_DIAGNOSTIC_DURATION_SECONDS}")
    if RITHMIC_DIAGNOSTIC_ONESHOT:
        print("RITHMIC STATUS|diagnostic_oneshot_enabled")
    for exchange_code, symbol_code in subscriptions:
        print(f"RITHMIC STATUS|subscribed_symbol|{exchange_code}|{symbol_code}")
    print(f"RITHMIC STATUS|executor_price_bridge|{EXECUTOR_PRICE_URL}")
    print(f"RITHMIC STATUS|atr_seed_bars_loaded_total|{persisted_bar_count}")
    LIVE_TICK_SYMBOLS.clear()
    mark_symbols_feed_status(subscribed_symbols, "STALE")
    for subscribed_symbol in subscribed_symbols:
        clear_atr_snapshot(
            subscribed_symbol,
            reason="listener_authority_epoch_change_startup",
        )
    price_publisher = PricePublisher(subscribed_symbols=subscribed_symbols)
    price_publisher.start()
    tick_worker = TickWorker(
        bar_cache,
        subscribed_symbols=subscribed_symbols,
        enforce_startup_warmup=True,
        archive_reconciler=archive_reconciler,
        price_publisher=price_publisher,
    )
    archive_reconciler.incident_callback = tick_worker.record_authority_incident
    tick_worker.start()
    reconnect_attempt = 0

    try:
        while True:
            try:
                bridge_generation = allocate_executor_listener_generation()
            except Exception as exc:
                reconnect_attempt += 1
                delay_seconds = min(
                    RECONNECT_BASE_DELAY_SECONDS * (2 ** max(reconnect_attempt - 1, 0)),
                    RECONNECT_MAX_DELAY_SECONDS,
                )
                print(
                    "RITHMIC WARNING|listener_generation_allocation_failed|"
                    f"attempt={reconnect_attempt}|delay_seconds={delay_seconds}|"
                    f"error={sanitize_log_message(exc)}"
                )
                time.sleep(delay_seconds)
                continue

            tick_worker.begin_bridge_generation(bridge_generation)
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
            print(
                "RITHMIC STATUS|bridge_started|"
                f"process_id={process.pid}|reconnect_attempt={reconnect_attempt}|"
                f"publication_generation={bridge_generation}"
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
                    update_bridge_connection_health_from_line(line)
                    if line.startswith("STATUS|market_data_connection_broken|") or line == "STATUS|market_data_connection_closed_unexpected":
                        tick_worker.invalidate_current_bars(line)
                    if line.startswith("AUTHORITY|bridge_sequence_gap|"):
                        tick_worker.record_authority_incident(
                            "bridge_sequence_gap",
                            bridge_generation=bridge_generation,
                            bridge_report=line,
                        )

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
                            tick = parse_tick_line(line, bridge_generation=bridge_generation)
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

            if RITHMIC_DIAGNOSTIC_ONESHOT:
                print("RITHMIC STATUS|bounded_diagnostic_bridge_exit")
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
        tick_worker.stop()
        price_publisher.stop()
        archive_reconciler.stop()
        close_local_finalized_bar_journal()


def main():
    authority = ListenerAuthorityGuard()
    if not authority.acquire():
        print(
            "RITHMIC STATUS|listener_authority_already_owned|"
            f"mutex={authority.name}|second_launch_exit=true|"
            "bridge_started=false|subscriptions_created=false"
        )
        return False

    print(
        "RITHMIC STATUS|listener_authority_acquired|"
        f"pid={os.getpid()}|mutex={authority.name}"
    )
    try:
        run_listener_service()
        return True
    finally:
        authority.release()
        print(
            "RITHMIC STATUS|listener_authority_released|"
            f"pid={os.getpid()}|mutex={authority.name}"
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("RITHMIC STATUS|manual_shutdown")
    except Exception as exc:
        print(f"RITHMIC listener failed: {sanitize_log_message(exc)}")
        sys.exit(1)
