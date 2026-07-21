import json
from datetime import date, datetime
from pathlib import Path
import re
from data_paths import data_path, get_data_root, log_active_data_root


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = get_data_root()
ATR_SNAPSHOT_PATH = data_path("rithmic_atr_snapshot.json")
RECENT_BARS_PATH = data_path("rithmic_recent_bars.json")
REFERENCE_DATE_OVERRIDE = None
log_active_data_root("symbol_resolution")


INSTRUMENT_CONFIG = {
    "NQ": {
        "root_symbol": "NQ",
        "exchange": "CME",
        "front_month_symbol": "NQM6",
        "tick_size": 0.25,
        "tick_value": 5.0,
        "point_value": 20.0,
        "aliases": ("NQ", "NQ1!", "NQM6"),
        "listener_enabled": True,
        "ui_enabled": True,
        "active_contract_resolver": None,
    },
    "RTY": {
        "root_symbol": "RTY",
        "exchange": "CME",
        "front_month_symbol": "RTYM6",
        "tick_size": 0.10,
        "tick_value": 5.0,
        "point_value": 50.0,
        "aliases": ("RTY", "RTY1!", "RTYM6"),
        # Retained for historical symbol resolution only. RTY is not an active
        # listener or UI market; production market data is NQ/YM only.
        "listener_enabled": False,
        "ui_enabled": False,
        "active_contract_resolver": None,
    },
    "YM": {
        "root_symbol": "YM",
        "exchange": "CBOT",
        "front_month_symbol": "YMM6",
        "tick_size": 1.0,
        "tick_value": 5.0,
        "point_value": 5.0,
        "aliases": ("YM", "YM1!", "YMM6"),
        "listener_enabled": True,
        "ui_enabled": True,
        "active_contract_resolver": None,
    },
    "ES": {
        "root_symbol": "ES",
        "exchange": "CME",
        "front_month_symbol": "ES",
        "tick_size": 0.25,
        "tick_value": 12.5,
        "point_value": 50.0,
        "aliases": ("ES", "ES1!"),
        "listener_enabled": False,
        "ui_enabled": False,
        "active_contract_resolver": None,
    },
    "GC": {
        "root_symbol": "GC",
        "exchange": "COMEX",
        "front_month_symbol": "GC",
        "tick_size": 0.10,
        "tick_value": 10.0,
        "point_value": 100.0,
        "aliases": ("GC", "GC1!"),
        "listener_enabled": False,
        "ui_enabled": False,
        "active_contract_resolver": None,
    },
}

MONTH_CODES = set("FGHJKMNQUVXZ")
QUARTERLY_CONTRACT_MONTHS = (3, 6, 9, 12)
QUARTERLY_MONTH_CODES = {
    3: "H",
    6: "M",
    9: "U",
    12: "Z",
}


def _normalize_raw_symbol(symbol):
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol:
        return ""
    if ":" in normalized_symbol:
        normalized_symbol = normalized_symbol.rsplit(":", 1)[1]
    normalized_symbol = normalized_symbol.replace("!", "")
    normalized_symbol = re.sub(r"[^A-Z0-9]", "", normalized_symbol)
    return normalized_symbol


def _strip_contract_suffix(symbol):
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol:
        return ""

    idx = len(normalized_symbol)
    had_trailing_digits = False
    while idx > 0 and normalized_symbol[idx - 1].isdigit():
        had_trailing_digits = True
        idx -= 1

    if had_trailing_digits and idx > 0 and normalized_symbol[idx - 1] in MONTH_CODES:
        root_symbol = normalized_symbol[:idx - 1]
        if root_symbol:
            return root_symbol

    return normalized_symbol


def _build_alias_map():
    alias_map = {}
    for root_symbol, config in INSTRUMENT_CONFIG.items():
        aliases = list(config.get("aliases", ()))
        aliases.append(root_symbol)
        front_month_symbol = str(config.get("front_month_symbol", "")).upper()
        if front_month_symbol:
            aliases.append(front_month_symbol)
        for alias in aliases:
            normalized_alias = _normalize_raw_symbol(alias)
            if normalized_alias:
                alias_map[normalized_alias] = root_symbol
    return alias_map


ALIAS_TO_ROOT = _build_alias_map()


def _coerce_reference_date(reference_date=None):
    if reference_date is None and REFERENCE_DATE_OVERRIDE is not None:
        reference_date = REFERENCE_DATE_OVERRIDE
    if reference_date is None:
        return datetime.now().date()
    if isinstance(reference_date, datetime):
        return reference_date.date()
    if isinstance(reference_date, date):
        return reference_date
    raise TypeError(f"Unsupported reference_date type: {type(reference_date)!r}")


def _nth_weekday_of_month(year, month, weekday, occurrence):
    current = date(year, month, 1)
    hits = 0
    while current.month == month:
        if current.weekday() == weekday:
            hits += 1
            if hits == occurrence:
                return current
        current = date.fromordinal(current.toordinal() + 1)
    raise ValueError(f"Could not find occurrence={occurrence} weekday={weekday} in {year}-{month:02d}")


def _equity_index_roll_date(year, contract_month):
    # Roll on the second Thursday of the quarterly expiry month so Monday June 15, 2026
    # resolves to the September contract instead of the stale June contract.
    return _nth_weekday_of_month(year, contract_month, weekday=3, occurrence=2)


def _next_quarter_month_year(year, month):
    idx = QUARTERLY_CONTRACT_MONTHS.index(month)
    if idx == len(QUARTERLY_CONTRACT_MONTHS) - 1:
        return year + 1, QUARTERLY_CONTRACT_MONTHS[0]
    return year, QUARTERLY_CONTRACT_MONTHS[idx + 1]


def _active_quarter_month_year(reference_date=None):
    current_date = _coerce_reference_date(reference_date)
    year = current_date.year
    month = current_date.month

    for contract_month in QUARTERLY_CONTRACT_MONTHS:
        if month < contract_month:
            return year, contract_month
        if month == contract_month:
            roll_date = _equity_index_roll_date(year, contract_month)
            if current_date < roll_date:
                return year, contract_month
            return _next_quarter_month_year(year, contract_month)

    return year + 1, QUARTERLY_CONTRACT_MONTHS[0]


def active_front_month_symbol(symbol, reference_date=None):
    root_symbol = normalize_symbol_root(symbol)
    year, contract_month = _active_quarter_month_year(reference_date=reference_date)
    month_code = QUARTERLY_MONTH_CODES[contract_month]
    return f"{root_symbol}{month_code}{year % 10}"


def _read_json(path):
    target = Path(path)
    if not target.exists():
        return {}

    try:
        with target.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
            return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _discover_live_symbols():
    discovered = []
    recent_bars_symbols = []
    atr_snapshot_symbols = []

    recent_bars_payload = _read_json(RECENT_BARS_PATH)
    for symbol in (recent_bars_payload.get("symbols") or {}).keys():
        normalized_symbol = str(symbol or "").upper()
        if normalized_symbol and normalized_symbol not in discovered:
            discovered.append(normalized_symbol)
        if normalized_symbol and normalized_symbol not in recent_bars_symbols:
            recent_bars_symbols.append(normalized_symbol)

    atr_snapshot_payload = _read_json(ATR_SNAPSHOT_PATH)
    for symbol in (atr_snapshot_payload.get("symbols") or {}).keys():
        normalized_symbol = str(symbol or "").upper()
        if normalized_symbol and normalized_symbol not in discovered:
            discovered.append(normalized_symbol)
        if normalized_symbol and normalized_symbol not in atr_snapshot_symbols:
            atr_snapshot_symbols.append(normalized_symbol)

    print(
        "SYMBOL RESOLUTION discovered_live_symbols|"
        f"recent_bars={recent_bars_symbols}|"
        f"atr_snapshot={atr_snapshot_symbols}|"
        f"all={discovered}|"
        f"recent_bars_path={RECENT_BARS_PATH}|"
        f"atr_snapshot_path={ATR_SNAPSHOT_PATH}"
    )

    return discovered, set(recent_bars_symbols), set(atr_snapshot_symbols)


def _resolve_active_contract_from_live_data(config, requested_symbol=None):
    root_symbol = str(config.get("root_symbol", "")).upper()
    live_symbols, recent_symbols, atr_symbols = _discover_live_symbols()
    matching_candidates = []

    for candidate in live_symbols:
        if candidate == root_symbol:
            continue
        if normalize_symbol_root(candidate) == root_symbol:
            matching_candidates.append(candidate)

    active_contract = active_front_month_symbol(root_symbol)
    if active_contract in matching_candidates:
        source = "recent_bars" if active_contract in recent_symbols else "atr_snapshot"
        return active_contract, source

    for candidate in matching_candidates:
        source = "recent_bars" if candidate in recent_symbols else "atr_snapshot"
        return candidate, source

    front_month_symbol = active_front_month_symbol(root_symbol)
    if front_month_symbol:
        return front_month_symbol, "registry_default"

    return root_symbol, "fallback"


for _config in INSTRUMENT_CONFIG.values():
    _config["active_contract_resolver"] = _resolve_active_contract_from_live_data


def canonicalize_symbol_input(symbol):
    normalized_symbol = _normalize_raw_symbol(symbol)
    if not normalized_symbol:
        return ""

    if normalized_symbol in ALIAS_TO_ROOT:
        return ALIAS_TO_ROOT[normalized_symbol]

    root_symbol = _strip_contract_suffix(normalized_symbol)
    if root_symbol in ALIAS_TO_ROOT:
        return ALIAS_TO_ROOT[root_symbol]

    return root_symbol or normalized_symbol


def normalize_symbol_root(symbol):
    normalized_symbol = _normalize_raw_symbol(symbol)
    if not normalized_symbol:
        return ""

    if normalized_symbol in ALIAS_TO_ROOT:
        return ALIAS_TO_ROOT[normalized_symbol]

    root_symbol = _strip_contract_suffix(normalized_symbol)
    if root_symbol in ALIAS_TO_ROOT:
        return ALIAS_TO_ROOT[root_symbol]

    return root_symbol or normalized_symbol


def get_instrument_spec(symbol):
    root_symbol = normalize_symbol_root(symbol)
    config = INSTRUMENT_CONFIG.get(root_symbol)
    if config:
        spec = dict(config)
        if spec.get("listener_enabled"):
            spec["front_month_symbol"] = active_front_month_symbol(root_symbol)
        return spec

    return {
        "root_symbol": root_symbol,
        "exchange": None,
        "front_month_symbol": root_symbol,
        "tick_size": 0.01,
        "tick_value": 0.01,
        "point_value": 1.0,
        "aliases": (root_symbol,),
        "listener_enabled": False,
        "ui_enabled": False,
        "active_contract_resolver": _resolve_active_contract_from_live_data,
    }


def get_default_listener_subscriptions(reference_date=None):
    subscriptions = []
    for root_symbol, config in INSTRUMENT_CONFIG.items():
        if not config.get("listener_enabled"):
            continue
        exchange = str(config.get("exchange", "")).upper()
        contract = str(active_front_month_symbol(root_symbol, reference_date=reference_date)).upper()
        if exchange and contract:
            subscriptions.append((exchange, contract))
    return subscriptions


def get_ui_roots():
    return [
        root_symbol
        for root_symbol, config in INSTRUMENT_CONFIG.items()
        if config.get("ui_enabled")
    ]


def get_tick_size(symbol):
    return float(get_instrument_spec(symbol).get("tick_size", 0.01))


def get_tick_value(symbol):
    return float(get_instrument_spec(symbol).get("tick_value", get_tick_size(symbol)))


def get_point_value(symbol):
    return float(get_instrument_spec(symbol).get("point_value", 1.0))


def resolve_execution_symbol(symbol):
    raw_symbol = str(symbol or "").strip().upper()
    root_symbol = canonicalize_symbol_input(raw_symbol)
    if not root_symbol:
        print("SYMBOL RESOLUTION resolve_execution_symbol|requested=|resolved=|symbol_resolution_source=empty_symbol")
        return "", "empty_symbol"

    config = INSTRUMENT_CONFIG.get(root_symbol)
    if config:
        resolved_symbol, source = config["active_contract_resolver"](config, requested_symbol=raw_symbol)
        print(
            "SYMBOL RESOLUTION resolve_execution_symbol|"
            f"requested={raw_symbol}|resolved={resolved_symbol}|"
            f"symbol_resolution_source={source}"
        )
        return str(resolved_symbol or root_symbol).upper(), source

    live_symbols, recent_symbols, atr_symbols = _discover_live_symbols()
    for candidate in live_symbols:
        if normalize_symbol_root(candidate) == root_symbol and candidate != root_symbol:
            source = "recent_bars" if candidate in recent_symbols else "atr_snapshot"
            print(
                "SYMBOL RESOLUTION resolve_execution_symbol|"
                f"requested={raw_symbol}|resolved={candidate}|"
                f"symbol_resolution_source={source}"
            )
            return candidate, source

    print(
        "SYMBOL RESOLUTION resolve_execution_symbol|"
        f"requested={raw_symbol}|resolved={root_symbol}|"
        "symbol_resolution_source=fallback"
    )
    return root_symbol, "fallback"


def build_symbol_candidates(symbol):
    raw_symbol = str(symbol or "").strip().upper()
    canonical_symbol = canonicalize_symbol_input(raw_symbol) or raw_symbol
    resolved_symbol, _ = resolve_execution_symbol(canonical_symbol)
    root_symbol = normalize_symbol_root(canonical_symbol)
    spec = get_instrument_spec(root_symbol)

    candidates = []
    for candidate in (
        raw_symbol,
        canonical_symbol,
        resolved_symbol,
        root_symbol,
        str(spec.get("front_month_symbol", "")).upper(),
        *[str(alias or "").upper() for alias in spec.get("aliases", ())],
    ):
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    return candidates
