"""Level loading and classification helpers for the entry agent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
LEVELS_PATH = BASE_DIR / "levels.json"
LEVELS_BY_SYMBOL_PATH = BASE_DIR / "levels_by_symbol.json"
TV_CONTEXT_PATH = BASE_DIR / "tv_context.json"
LEVEL_KEYS = ("PMH", "PML", "LH", "LL", "ONH", "ONL", "YH", "YL", "RTHH", "RTHL")
TICK_SIZES = {"NQ": 0.25, "YM": 1.0, "RTY": 0.10}


def root_symbol(symbol: str) -> str:
    """Return the supported root symbol for a contract or root."""
    upper_symbol = str(symbol).strip().upper()
    if ":" in upper_symbol:
        upper_symbol = upper_symbol.split(":", 1)[1]
    for root in TICK_SIZES:
        if upper_symbol.startswith(root):
            return root
    return upper_symbol


def _empty_levels() -> dict[str, Any]:
    return {key: None for key in LEVEL_KEYS}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _levels_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload.get(key) for key in LEVEL_KEYS}


def _legacy_levels_match_requested_root(requested_root: str) -> bool:
    context = _read_json(TV_CONTEXT_PATH)
    context_root = context.get("normalized_symbol")
    if context_root is None:
        return True
    return str(context_root).upper() == requested_root


def load_levels(symbol: str | None = None) -> dict:
    """Load levels for the requested symbol without reusing another root's context."""
    requested_root = root_symbol(symbol) if symbol else None
    if requested_root:
        by_symbol = _read_json(LEVELS_BY_SYMBOL_PATH).get("symbols")
        if isinstance(by_symbol, dict):
            symbol_levels = by_symbol.get(requested_root)
            if isinstance(symbol_levels, dict):
                return _levels_from_payload(symbol_levels)

    legacy_levels = _read_json(LEVELS_PATH)
    if requested_root and not _legacy_levels_match_requested_root(requested_root):
        return _empty_levels()
    if not legacy_levels:
        return _empty_levels()
    return _levels_from_payload(legacy_levels)


def tick_size_for_symbol(symbol: str) -> float:
    """Return the configured tick size for a symbol root."""
    return TICK_SIZES.get(root_symbol(symbol), 0.25)


def active_levels(levels: dict[str, Any]) -> dict[str, float]:
    """Return non-null flat schema levels as floats."""
    active: dict[str, float] = {}
    for key in LEVEL_KEYS:
        value = levels.get(key)
        if value is None:
            continue
        try:
            active[key] = float(value)
        except (TypeError, ValueError):
            continue
    return active


def _nearest_level(candidates: dict[str, float], price: float, above: bool) -> dict[str, Any] | None:
    filtered = [
        {"name": name, "price": level_price}
        for name, level_price in candidates.items()
        if (level_price > price and above) or (level_price < price and not above)
    ]
    if not filtered:
        return None
    return min(filtered, key=lambda level: abs(level["price"] - price))


def classify_liquidity_location(
    latest_price: Any,
    levels: dict[str, Any],
    symbol: str = "NQ",
) -> dict[str, Any]:
    """Classify the latest price relative to configured liquidity levels."""
    try:
        price = float(latest_price)
    except (TypeError, ValueError):
        price = None

    configured_levels = active_levels(levels)
    tick_size = tick_size_for_symbol(symbol)

    if price is None or not configured_levels:
        return {
            "nearest_level_above": None,
            "nearest_level_below": None,
            "touched_levels": [],
            "current_location": "NO_LEVELS",
            "tick_size": tick_size,
        }

    touched_levels = [
        {"name": name, "price": level_price}
        for name, level_price in configured_levels.items()
        if abs(price - level_price) <= tick_size
    ]
    nearest_level_above = _nearest_level(configured_levels, price, above=True)
    nearest_level_below = _nearest_level(configured_levels, price, above=False)

    if touched_levels:
        current_location = "AT_LIQUIDITY"
    elif nearest_level_above is None:
        current_location = "ABOVE_ALL_LEVELS"
    elif nearest_level_below is None:
        current_location = "BELOW_ALL_LEVELS"
    else:
        current_location = "BETWEEN_LEVELS"

    return {
        "nearest_level_above": nearest_level_above,
        "nearest_level_below": nearest_level_below,
        "touched_levels": touched_levels,
        "current_location": current_location,
        "tick_size": tick_size,
    }


if __name__ == "__main__":
    print(load_levels())
