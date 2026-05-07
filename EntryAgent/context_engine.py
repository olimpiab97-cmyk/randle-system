"""Context Engine helpers for EntryAgent."""

from __future__ import annotations

from typing import Any


def as_float(value: Any) -> float | None:
    """Convert numeric-like input to float while preserving null/invalid values."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def percent_of_atr(value_range: float | None, atr: float | None) -> float | None:
    """Return range as a percent of ATR."""
    if value_range is None or atr is None or atr == 0:
        return None
    return (value_range / atr) * 100.0


def calculate_pm_percent(pmh: Any, pml: Any, atr_daily: Any) -> float | None:
    """Calculate premarket range as percent of daily ATR."""
    high = as_float(pmh)
    low = as_float(pml)
    atr = as_float(atr_daily)
    if high is None or low is None:
        return None
    return percent_of_atr(abs(high - low), atr)


def calculate_dr_percent(current_high: Any, current_low: Any, atr_daily: Any) -> float | None:
    """Calculate current day range as percent of daily ATR."""
    high = as_float(current_high)
    low = as_float(current_low)
    atr = as_float(atr_daily)
    if high is None or low is None:
        return None
    return percent_of_atr(abs(high - low), atr)


def detect_london_bias(london_high: Any, london_low: Any, london_close: Any) -> str:
    """Classify London close location inside its range."""
    high = as_float(london_high)
    low = as_float(london_low)
    close = as_float(london_close)
    if high is None or low is None or close is None or high == low:
        return "UNKNOWN"

    midpoint = (high + low) / 2.0
    if close > midpoint:
        return "BULLISH"
    if close < midpoint:
        return "BEARISH"
    return "NEUTRAL"


def detect_volatility_state(current_1m_atr: Any, atr_daily: Any) -> str:
    """Classify current 1-minute ATR against daily ATR context."""
    one_min_atr = as_float(current_1m_atr)
    daily_atr = as_float(atr_daily)
    if one_min_atr is None or daily_atr is None or daily_atr == 0:
        return "UNKNOWN"

    atr_ratio_pct = (one_min_atr / daily_atr) * 100.0
    if atr_ratio_pct < 0.10:
        return "COMPRESSED"
    if atr_ratio_pct > 0.35:
        return "EXPANDED"
    return "NORMAL"


def detect_day_profile(pm_percent: float | None, dr_percent: float | None, london_bias: str) -> str:
    """Classify broad day profile from range context."""
    if pm_percent is None or dr_percent is None:
        return "UNKNOWN"
    if dr_percent >= 100:
        return "FULL_ATR_DAY"
    if pm_percent >= 50 and london_bias in ("BULLISH", "BEARISH"):
        return "DIRECTIONAL_PREMARKET"
    if pm_percent < 25 and dr_percent < 50:
        return "BALANCED"
    return "DEVELOPING"


def evaluate_context(
    pmh: Any,
    pml: Any,
    current_high: Any,
    current_low: Any,
    atr_daily: Any,
    london_high: Any,
    london_low: Any,
    london_close: Any,
    current_1m_atr: Any,
) -> dict[str, Any]:
    """Build EntryAgent context outputs from market/session inputs."""
    pm_percent = calculate_pm_percent(pmh, pml, atr_daily)
    dr_percent = calculate_dr_percent(current_high, current_low, atr_daily)
    london_bias = detect_london_bias(london_high, london_low, london_close)
    volatility_state = detect_volatility_state(current_1m_atr, atr_daily)
    day_profile = detect_day_profile(pm_percent, dr_percent, london_bias)

    return {
        "pm_percent": pm_percent,
        "dr_percent": dr_percent,
        "london_bias": london_bias,
        "volatility_state": volatility_state,
        "day_profile": day_profile,
    }
