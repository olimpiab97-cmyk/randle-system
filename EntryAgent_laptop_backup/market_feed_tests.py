"""Targeted tests for Entry Agent market snapshot selection."""

from __future__ import annotations

import market_feed
from entry_agent import active_levels_from_tv_context, evaluate_live_step_2_1a
from levels import classify_liquidity_location


def test_closed_bar_preferred_over_trade_manager_forming_bar() -> None:
    original_bars = market_feed._snapshot_from_bars
    original_trade_manager = market_feed._snapshot_from_trade_manager
    try:
        market_feed._snapshot_from_bars = lambda _symbol: {
            "source": "closed-bars",
            "symbol": "NQM6",
            "latest_price": 100.25,
            "latest_bar_time": "2026-05-12T13:40:00Z",
            "ohlc": {"open": 99.5, "high": 100.5, "low": 99.25, "close": 100.25},
            "ohlc_is_closed": True,
        }
        market_feed._snapshot_from_trade_manager = lambda _symbol: {
            "source": "trade-manager",
            "symbol": "NQM6",
            "latest_price": 101.75,
            "latest_bar_time": "2026-05-12T13:40:23Z",
            "ohlc": {"open": 100.25, "high": 101.75, "low": 100.25, "close": 101.75},
            "ohlc_is_closed": False,
        }

        snapshot = market_feed.get_latest_market_snapshot("NQ")
    finally:
        market_feed._snapshot_from_bars = original_bars
        market_feed._snapshot_from_trade_manager = original_trade_manager

    assert snapshot["source"] == "closed-bars"
    assert snapshot["latest_price"] == 100.25
    assert snapshot["ohlc"]["close"] == 100.25
    assert snapshot["ohlc_is_closed"] is True
    assert snapshot["decision_source"] == "closed-bars"
    assert snapshot["live_source"] == "trade-manager"
    assert snapshot["live_price"] == 101.75
    assert snapshot["live_ohlc_is_closed"] is False

    tv_context = {
        "normalized_symbol": "NQ",
        "levels": {
            "PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"},
            "PML": {"price": 95.0, "status": "ACTIVE", "stack_group": "NONE"},
        },
    }
    decision_snapshot = {
        **snapshot,
        "requested_symbol": "NQ",
        "normalized_symbol": "NQ",
        "tv_context": tv_context,
    }
    levels = active_levels_from_tv_context(tv_context)
    liquidity = classify_liquidity_location(decision_snapshot["latest_price"], levels, "NQ")
    step_2_1a = evaluate_live_step_2_1a(decision_snapshot, levels, liquidity, {})

    assert step_2_1a["available"] is True
    assert step_2_1a["active_level"] == "PMH"
    assert step_2_1a["level_price"] == 100.0
    assert step_2_1a["step_2_activated"] is True


def run_tests() -> list[dict[str, str]]:
    test_closed_bar_preferred_over_trade_manager_forming_bar()
    return [{"scenario": "closed bar preferred over forming Trade Manager snapshot", "status": "PASS"}]


if __name__ == "__main__":
    for item in run_tests():
        print(f"{item['status']}: {item['scenario']}")
