from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import entry_agent


def read_session_archive_bars(path: Path, symbol: str, start: str, end: str) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if str(record.get("root_symbol") or "").upper() != symbol.upper():
            continue
        candle_time = record.get("timestamp")
        if not isinstance(candle_time, str) or not (start <= candle_time <= end):
            continue
        if record.get("open") is None:
            continue
        rows.setdefault(
            candle_time,
            {
                "timestamp": candle_time,
                "open": record.get("open"),
                "high": record.get("high"),
                "low": record.get("low"),
                "close": record.get("close"),
            },
        )
    return [rows[key] for key in sorted(rows)]


def lane_view(lane: dict[str, Any] | None) -> dict[str, Any]:
    lane = lane if isinstance(lane, dict) else {}
    return {
        "lane_status": lane.get("lane_status"),
        "step2_status": lane.get("step2_status"),
        "step2_confirmed_at": lane.get("step2_confirmed_at"),
        "step2_candle_count": lane.get("step2_candle_count"),
        "step2_reason": lane.get("step2_reason"),
        "step2_owner_frozen_display": lane.get("step2_owner_frozen_display"),
        "step4_status": lane.get("step4_status"),
        "step4_reason": lane.get("step4_reason"),
        "step4_confirmed_at": lane.get("step4_confirmed_at"),
        "step4_candle_count": lane.get("step4_candle_count"),
        "active_liquidity_name": lane.get("active_liquidity_name"),
        "active_liquidity_price": lane.get("active_liquidity_price"),
        "liquidity_level_name": lane.get("liquidity_level_name"),
        "liquidity_level_price": lane.get("liquidity_level_price"),
        "rejection_boundary": lane.get("rejection_boundary"),
        "continuation_boundary": lane.get("continuation_boundary"),
        "continuation_type": lane.get("continuation_type"),
    }


def replay_runtime_path(
    *,
    symbol: str,
    bars: list[dict[str, Any]],
    checkpoints: set[str],
) -> list[dict[str, Any]]:
    tv_context = entry_agent.load_tv_context(symbol)
    original_state_path = entry_agent.STATE_PATH
    original_get_latest = entry_agent.get_latest_market_snapshot
    original_load_tv = entry_agent.load_tv_context
    original_recent = entry_agent.recent_closed_bars
    original_load_atr = entry_agent.load_rithmic_atr_snapshot
    original_append_audit = entry_agent.append_entry_agent_audit_row
    results: list[dict[str, Any]] = []
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry_agent.STATE_PATH = Path(temp_dir) / "entry_agent_state.json"
            entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
            entry_agent.load_tv_context = lambda _symbol=None: tv_context
            entry_agent.load_rithmic_atr_snapshot = lambda _symbol=symbol: {"atr_1m_14": (tv_context or {}).get("atr_1m_14") or 10.0}
            replay_bars: list[dict[str, Any]] = []
            index = {"value": 0}

            def market_snapshot(_symbol: str = symbol) -> dict[str, Any]:
                current = bars[index["value"]]
                return {
                    "symbol": symbol,
                    "normalized_symbol": symbol,
                    "latest_price": current["close"],
                    "latest_bar_time": current["timestamp"],
                    "ohlc_is_closed": True,
                    "liquidity": {
                        "nearest_level_above": None,
                        "nearest_level_below": None,
                        "tick_size": 0.25,
                    },
                    "atr": {"atr_1m_14": (tv_context or {}).get("atr_1m_14") or 10.0},
                    "ohlc": {
                        "open": current["open"],
                        "high": current["high"],
                        "low": current["low"],
                        "close": current["close"],
                    },
                }

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol=symbol, limit=120: list(replay_bars)[-limit:]

            for i, bar in enumerate(bars):
                index["value"] = i
                replay_bars.append(dict(bar))
                entry_agent.run_once(symbol, persist=True)
                status = entry_agent.build_entry_status(symbol)
                state = entry_agent.load_entry_state()
                symbol_state = state.get("state_by_symbol", {}).get(symbol, state)
                if bar["timestamp"] not in checkpoints:
                    continue
                step2_state = symbol_state.get("step_2_1a") if isinstance(symbol_state.get("step_2_1a"), dict) else {}
                step4_state = ((symbol_state.get("step4") or {}).get("state") or {}) if isinstance(((symbol_state.get("step4") or {}).get("state") or {}), dict) else {}
                step25_state = ((symbol_state.get("step25") or {}).get("state") or {}) if isinstance(((symbol_state.get("step25") or {}).get("state") or {}), dict) else {}
                results.append(
                    {
                        "time": bar["timestamp"],
                        "ohlc": dict(bar),
                        "runtime_step2": {
                            "step_2_activated": step2_state.get("step_2_activated"),
                            "step2_activated_at": step2_state.get("step2_activated_at"),
                            "step2_owner_seeded_at": step2_state.get("step2_owner_seeded_at"),
                            "candle_a_time": ((step2_state.get("candle_a") or {}).get("timestamp") if isinstance(step2_state.get("candle_a"), dict) else None),
                            "active_level": step2_state.get("active_level"),
                            "level_price": step2_state.get("level_price"),
                        },
                        "runtime_step4": {
                            "status": (symbol_state.get("step4") or {}).get("status"),
                            "candle_a_time": ((step4_state.get("candle_a") or {}).get("timestamp") if isinstance(step4_state.get("candle_a"), dict) else None),
                            "candle_b_time": ((step4_state.get("candle_b") or {}).get("timestamp") if isinstance(step4_state.get("candle_b"), dict) else None),
                            "leg1_status": step4_state.get("leg1_status"),
                            "leg1_completed_at": step4_state.get("leg1_completed_at"),
                        },
                        "runtime_step25": {
                            "status": (symbol_state.get("step25") or {}).get("status"),
                            "controlling_mode": step25_state.get("controlling_mode"),
                            "continuation_step2_activated": step25_state.get("continuation_step2_activated"),
                            "reclaim_candle_a_time": ((step25_state.get("reclaim_candle_a") or {}).get("timestamp") if isinstance(step25_state.get("reclaim_candle_a"), dict) else None),
                        },
                        "status": {
                            "selected_pathway": status.get("selected_pathway"),
                            "current_pathway_control": status.get("current_pathway_control"),
                            "current_controlling_mode": status.get("current_controlling_mode"),
                            "liquidity_level_name": status.get("liquidity_level_name"),
                            "liquidity_level_price": status.get("liquidity_level_price"),
                            "rejection_boundary": status.get("rejection_boundary"),
                            "continuation_boundary": status.get("continuation_boundary"),
                            "step2_status": status.get("step2_status"),
                            "step2_confirmed_at": status.get("step2_confirmed_at"),
                            "step2_candle_count": status.get("step2_candle_count"),
                            "step4_status": status.get("step4_status"),
                            "step4_confirmed_at": status.get("step4_confirmed_at"),
                            "step4_candle_a_time": status.get("step4_candle_a_time"),
                            "step4_candle_b_time": status.get("step4_candle_b_time"),
                            "wait_reason": status.get("wait_reason"),
                            "rejection_lane": lane_view(status.get("rejection_lane")),
                            "continuation_lane": lane_view(status.get("continuation_lane")),
                        },
                    }
                )
    finally:
        entry_agent.STATE_PATH = original_state_path
        entry_agent.get_latest_market_snapshot = original_get_latest
        entry_agent.load_tv_context = original_load_tv
        entry_agent.recent_closed_bars = original_recent
        entry_agent.load_rithmic_atr_snapshot = original_load_atr
        entry_agent.append_entry_agent_audit_row = original_append_audit
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay Entry Agent through archived session bars.")
    parser.add_argument("--archive-path", required=True)
    parser.add_argument("--symbol", default="NQ")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--checkpoints", nargs="+", required=True)
    args = parser.parse_args()

    bars = read_session_archive_bars(Path(args.archive_path), args.symbol.upper(), args.start, args.end)
    results = replay_runtime_path(
        symbol=args.symbol.upper(),
        bars=bars,
        checkpoints=set(args.checkpoints),
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
