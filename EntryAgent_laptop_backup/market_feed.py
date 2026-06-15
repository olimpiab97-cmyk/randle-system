"""Market feed helpers for the entry agent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

DATA_DIR = Path(__file__).resolve().parents[1] / "Data"
RITHMIC_BARS_PATH = DATA_DIR / "rithmic_recent_bars.json"
EXECUTOR_STATE_PATH = DATA_DIR / "executor_state.json"
TRADE_MANAGER_SNAPSHOT_URL = "http://localhost:6001/sync_snapshot"


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _matches_symbol(candidate: str | None, root_symbol: str) -> bool:
    if not candidate:
        return False
    return candidate.upper().startswith(root_symbol.upper())


def _snapshot_timestamp(symbol_snapshot: dict[str, Any], fallback: Any = None) -> Any:
    for key in (
        "last_price_at",
        "listener_timestamp",
        "tick_timestamp",
        "timestamp",
        "atr_bar_timestamp",
    ):
        value = symbol_snapshot.get(key)
        if value:
            return value
    current_bar = symbol_snapshot.get("current_1m_bar")
    if isinstance(current_bar, dict) and current_bar.get("timestamp"):
        return current_bar.get("timestamp")
    return fallback


def _ohlc_from_symbol_snapshot(symbol_snapshot: dict[str, Any]) -> dict[str, Any] | None:
    current_bar = symbol_snapshot.get("current_1m_bar")
    if not isinstance(current_bar, dict):
        return None
    if any(current_bar.get(key) is None for key in ("open", "high", "low", "close")):
        return None
    return {
        "open": current_bar.get("open"),
        "high": current_bar.get("high"),
        "low": current_bar.get("low"),
        "close": current_bar.get("close"),
    }


def _snapshot_from_trade_manager(root_symbol: str) -> dict[str, Any] | None:
    try:
        with urlopen(TRADE_MANAGER_SNAPSHOT_URL, timeout=0.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError):
        return None

    symbols = payload.get("symbols", {}) if isinstance(payload, dict) else {}
    if not isinstance(symbols, dict):
        return None

    candidates = [
        (str(symbol), snapshot)
        for symbol, snapshot in symbols.items()
        if _matches_symbol(str(symbol), root_symbol) and isinstance(snapshot, dict)
    ]
    if not candidates:
        return None

    symbol, symbol_snapshot = max(
        candidates,
        key=lambda item: str(_snapshot_timestamp(item[1], payload.get("timestamp") or payload.get("saved_at")) or ""),
    )
    latest_price = _optional_float(symbol_snapshot.get("last_price"))
    if latest_price is None:
        return None

    return {
        "source": TRADE_MANAGER_SNAPSHOT_URL,
        "symbol": symbol,
        "latest_price": latest_price,
        "latest_bar_time": _snapshot_timestamp(symbol_snapshot, payload.get("timestamp") or payload.get("saved_at")),
        "ohlc": _ohlc_from_symbol_snapshot(symbol_snapshot),
        "ohlc_is_closed": False,
    }


def _latest_matching_bar(data: Any, root_symbol: str) -> dict[str, Any] | None:
    symbols = data.get("symbols", {}) if isinstance(data, dict) else {}
    latest_bar: dict[str, Any] | None = None

    for symbol, bars in symbols.items():
        if not _matches_symbol(str(symbol), root_symbol) or not isinstance(bars, list):
            continue
        for bar in bars:
            if not isinstance(bar, dict):
                continue
            if latest_bar is None or str(bar.get("timestamp", "")) > str(latest_bar.get("timestamp", "")):
                latest_bar = bar

    return latest_bar


def recent_closed_bars(root_symbol: str, limit: int = 2) -> list[dict[str, Any]]:
    """Return recent closed bars for live Step 2.5 candle-pair qualification."""
    if not RITHMIC_BARS_PATH.exists():
        return []

    data = _read_json(RITHMIC_BARS_PATH)
    symbols = data.get("symbols", {}) if isinstance(data, dict) else {}
    bars: list[dict[str, Any]] = []
    for symbol, symbol_bars in symbols.items():
        if not _matches_symbol(str(symbol), root_symbol) or not isinstance(symbol_bars, list):
            continue
        for bar in symbol_bars:
            if not isinstance(bar, dict):
                continue
            if any(bar.get(key) is None for key in ("open", "high", "low", "close", "timestamp")):
                continue
            bars.append(
                {
                    "open": bar.get("open"),
                    "high": bar.get("high"),
                    "low": bar.get("low"),
                    "close": bar.get("close"),
                    "timestamp": bar.get("timestamp"),
                }
            )

    bars = sorted(bars, key=lambda item: str(item.get("timestamp") or ""))
    return bars[-limit:]


def _snapshot_from_bars(root_symbol: str) -> dict[str, Any] | None:
    if not RITHMIC_BARS_PATH.exists():
        return None

    latest_bar = _latest_matching_bar(_read_json(RITHMIC_BARS_PATH), root_symbol)
    if latest_bar is None:
        return None

    return {
        "source": str(RITHMIC_BARS_PATH),
        "symbol": latest_bar.get("symbol") or root_symbol,
        "latest_price": latest_bar.get("close"),
        "latest_bar_time": latest_bar.get("timestamp"),
        "ohlc": {
            "open": latest_bar.get("open"),
            "high": latest_bar.get("high"),
            "low": latest_bar.get("low"),
            "close": latest_bar.get("close"),
        },
        "ohlc_is_closed": True,
    }


def _event_time(order: dict[str, Any]) -> str:
    for key in ("filled_at", "closed_at", "updated_at", "created_at"):
        value = order.get(key)
        if value:
            return str(value)
    return ""


def _event_price(order: dict[str, Any]) -> Any:
    for key in ("filled_price", "fill_trigger_price", "limit_price", "stop_price"):
        if order.get(key) is not None:
            return order[key]
    return None


def _snapshot_from_executor_state(root_symbol: str) -> dict[str, Any] | None:
    if not EXECUTOR_STATE_PATH.exists():
        return None

    data = _read_json(EXECUTOR_STATE_PATH)
    orders = data.get("orders", {}) if isinstance(data, dict) else {}
    if not isinstance(orders, dict):
        return None

    latest_order: dict[str, Any] | None = None
    for order in orders.values():
        if not isinstance(order, dict) or not _matches_symbol(str(order.get("symbol", "")), root_symbol):
            continue
        if latest_order is None or _event_time(order) > _event_time(latest_order):
            latest_order = order

    if latest_order is None:
        return None

    return {
        "source": str(EXECUTOR_STATE_PATH),
        "symbol": latest_order.get("resolved_symbol") or latest_order.get("symbol") or root_symbol,
        "latest_price": _event_price(latest_order),
        "latest_bar_time": _event_time(latest_order) or data.get("saved_at"),
        "ohlc": None,
        "ohlc_is_closed": None,
    }


def _with_live_trade_manager_price(decision_snapshot: dict[str, Any], live_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Attach forming-bar live price fields without replacing confirmed decision OHLC."""
    if not isinstance(live_snapshot, dict):
        return decision_snapshot
    snapshot = dict(decision_snapshot)
    snapshot["decision_source"] = decision_snapshot.get("source")
    snapshot["live_source"] = live_snapshot.get("source")
    snapshot["live_price"] = live_snapshot.get("latest_price")
    snapshot["live_bar_time"] = live_snapshot.get("latest_bar_time")
    snapshot["live_ohlc"] = live_snapshot.get("ohlc")
    snapshot["live_ohlc_is_closed"] = live_snapshot.get("ohlc_is_closed")
    return snapshot


def get_latest_market_snapshot(symbol: str = "NQ") -> dict[str, Any]:
    """Read the latest one-shot decision snapshot from confirmed bars, preserving live price separately."""
    closed_bar_snapshot = _snapshot_from_bars(symbol)
    trade_manager_snapshot = _snapshot_from_trade_manager(symbol)
    if closed_bar_snapshot:
        return _with_live_trade_manager_price(closed_bar_snapshot, trade_manager_snapshot)
    return trade_manager_snapshot or _snapshot_from_executor_state(symbol) or {
        "source": None,
        "symbol": symbol,
        "latest_price": None,
        "latest_bar_time": None,
        "ohlc": None,
        "ohlc_is_closed": None,
    }


if __name__ == "__main__":
    print(get_latest_market_snapshot())
