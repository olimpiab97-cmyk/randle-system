"""Dry-run candle injector for Entry Agent classification testing.

This tool injects synthetic closed candles through the same Entry Agent
classification path used by /entry/status while redirecting persistence to an
isolated temporary state file. It never submits trades or calls executor/order
routes.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import entry_agent  # noqa: E402


SCENARIOS = {
    "pmh_rejection_to_entry",
    "pml_rejection_to_entry",
    "rs_continuation_641_647",
    "rs_continuation_to_entry",
    "sr_continuation_to_entry",
}

STATUS_FIELDS = [
    "active_liquidity_name",
    "active_liquidity_price",
    "liquidity_group",
    "current_pathway_control",
    "selected_pathway",
    "sr_rs_context",
    "setup_direction",
    "current_step",
    "current_step_status",
    "leg1_state",
    "leg1_locked",
    "step4_proximity_distance",
    "step4_proximity_daily_atr",
    "step4_proximity_atr_threshold",
    "step4_proximity_atr_threshold_percent",
    "leg2_state",
    "entry_status",
    "entry_type_number",
    "entry_type_name",
    "entry_model",
    "entry_model_reason",
    "step6_window_active",
    "step6_window_started_at",
    "step6_window_candle_index",
    "step6_window_remaining",
    "step6_window_expires_at",
    "wait_reason",
    "invalidation_reason",
]


def _read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def root(symbol: str) -> str:
    return entry_agent.root_symbol(symbol).upper()


def sanitize_state_for_symbol(state: dict[str, Any], symbol: str) -> dict[str, Any]:
    """Copy live state, but remove the simulated symbol's active lifecycle."""
    symbol_key = root(symbol)
    sanitized = copy.deepcopy(state)
    state_by_symbol = sanitized.get("state_by_symbol")
    if isinstance(state_by_symbol, dict):
        state_by_symbol.pop(symbol_key, None)
        sanitized["state_by_symbol"] = state_by_symbol
    if root(str(sanitized.get("normalized_symbol") or sanitized.get("requested_symbol") or "")) == symbol_key:
        for key in (
            "step_2_1a",
            "step2_locked_owner",
            "last_interacted_liquidity",
            "consumed_liquidity_levels",
            "rejection",
            "step25",
            "step3",
            "step4",
            "step5",
            "step6",
            "gateway",
        ):
            sanitized.pop(key, None)
    return sanitized


@contextmanager
def isolated_entry_agent_state(symbol: str):
    """Redirect Entry Agent persistence to temp state and restore module globals."""
    original_state_path = entry_agent.STATE_PATH
    original_persistence_path = entry_agent.PERSISTENCE_STATE_PATH
    original_executor_state_path = entry_agent.EXECUTOR_STATE_PATH
    original_get_snapshot = entry_agent.get_latest_market_snapshot
    original_recent_closed_bars = entry_agent.recent_closed_bars
    original_live_state_bytes = _read_bytes(original_state_path)

    with tempfile.TemporaryDirectory(prefix="entry_agent_dry_run_") as temp_dir:
        temp_state_path = Path(temp_dir) / "entry_agent_state.json"
        temp_persistence_path = Path(temp_dir) / "persistence_state.json"
        temp_executor_state_path = Path(temp_dir) / "executor_state.json"
        _write_json(temp_state_path, sanitize_state_for_symbol(_read_json(original_state_path), symbol))
        _write_json(temp_persistence_path, {})
        _write_json(temp_executor_state_path, {})
        entry_agent.STATE_PATH = temp_state_path
        entry_agent.PERSISTENCE_STATE_PATH = temp_persistence_path
        entry_agent.EXECUTOR_STATE_PATH = temp_executor_state_path
        try:
            yield temp_state_path
        finally:
            entry_agent.STATE_PATH = original_state_path
            entry_agent.PERSISTENCE_STATE_PATH = original_persistence_path
            entry_agent.EXECUTOR_STATE_PATH = original_executor_state_path
            entry_agent.get_latest_market_snapshot = original_get_snapshot
            entry_agent.recent_closed_bars = original_recent_closed_bars
            if original_live_state_bytes != _read_bytes(original_state_path):
                raise RuntimeError(f"DRY-RUN SAFETY STOP: live state changed: {original_state_path}")


def seed_completed_pmh_rejection_state(state_path: Path, symbol: str, pmh: float) -> None:
    symbol_key = root(symbol)
    step2_candle = {"timestamp": "2026-05-19T13:32:00Z", "open": 28940.75, "high": 28981.75, "low": 28930.25, "close": 28969.75}
    leg1_candle = {"timestamp": "2026-05-19T13:33:00Z", "open": 28970.25, "high": 28999.0, "low": 28964.5, "close": 28977.25}
    leg2_candle = {"timestamp": "2026-05-19T13:35:00Z", "open": 28980.0, "high": 28986.0, "low": 28970.0, "close": 28981.0}
    entry_candle = {"timestamp": "2026-05-19T13:37:00Z", "open": 29042.5, "high": 29068.0, "low": 29041.0, "close": 29052.5}
    active_liquidity = {"name": "PMH", "display_name": "PMH", "price": pmh, "side": "upper", "group": None}
    locked_owner = {
        "symbol": symbol_key,
        "active_liquidity": active_liquidity,
        "active_liquidity_name": "PMH",
        "active_liquidity_display_name": "PMH",
        "active_liquidity_price": pmh,
        "active_liquidity_group": None,
        "liquidity_group": None,
        "stack_components": [],
        "close_boundary": pmh,
        "extreme_boundary": pmh,
        "setup_direction": "SHORT",
        "pathway": "rejection",
        "active_pathway": "rejection",
        "step2_confirmed_at": step2_candle["timestamp"],
        "reference_candle_time": "2026-05-19T13:31:00Z",
    }
    symbol_state = {
        "observation_reset_session_date": "2026-05-19",
        "observation_reset_bar_time": "2026-05-19T13:30:00Z",
        "last_interacted_liquidity": active_liquidity,
        "step_2_1a_candle_index": 8,
        "step_2_1a_last_evaluated_bar_time": entry_candle["timestamp"],
        "step2_locked_owner": locked_owner,
        "step_2_1a": {
            "available": True,
            "active_level": "PMH",
            "level_price": pmh,
            "side": "upper",
            "tick_size": 0.25,
            "step_2_activated": True,
            "candle_a": step2_candle,
            "step2_locked_owner": locked_owner,
            "pre_activation_probe_boundary": {"active": False, "side": "upper", "boundary_price": 28960.0},
            "active_liquidity_group": None,
            "last_interacted_liquidity": active_liquidity,
        },
        "rejection": {
            "rejection_mode": "ON",
            "watch_side": "SHORT",
            "trigger_level": "PMH",
            "trigger_price": pmh,
            "active_liquidity": active_liquidity,
        },
        "step25": {
            "step": "Step 2.5",
            "status": "READY",
            "next_step": "Step 3",
            "reason": "Seeded completed PMH rejection interaction.",
            "state": {
                "rejection_mode": "ON",
                "initial_candle_a": step2_candle,
                "candidate_modes": ["Normal Rejection Mode"],
                "controlling_mode": "Normal Rejection Mode",
                "pathway_level": pmh,
                "pathway_activation_type": "normal",
                "step25_pathway_selection_complete": True,
            },
            "events": [],
        },
        "step3": {
            "step": "Step 3",
            "status": "ALLOW_STEP_4",
            "next_step": "Step 4",
            "reason": "Seeded completed PMH rejection interaction.",
            "state": {
                "active_liquidity": active_liquidity,
                "active_level": "PMH",
                "level_price": pmh,
                "liquidity_type": "STATIC_SINGLE",
                "step3_permission": "ALLOW_STEP_4",
            },
            "events": [],
        },
        "step4": {
            "step": "Step 4",
            "status": "READY",
            "next_step": "Step 5",
            "reason": "Seeded prior Leg 1 complete.",
            "state": {
                "rejection_mode": "ON",
                "interaction_state": "FINALIZED",
                "pathway_lifecycle_status": "ENTERED",
                "pathway_finalized": True,
                "controlling_mode": "Normal Rejection Mode",
                "current_pathway_control": "rejection",
                "setup_direction": "SHORT",
                "active_liquidity": active_liquidity,
                "initial_candle_a": step2_candle,
                "candle_a": step2_candle,
                "candle_b": leg1_candle,
                "leg1_status": "COMPLETE",
                "leg1_state_locked": True,
                "leg1_completed_at": leg1_candle["timestamp"],
                "leg1_reference_price": leg1_candle["close"],
                "leg1_reference_candle_time": leg1_candle["timestamp"],
                "anchor_extreme": leg1_candle["high"],
            },
            "events": [],
        },
        "step5": {
            "step": "Step 5",
            "status": "READY",
            "next_step": "Step 6",
            "reason": "Seeded prior Leg 2 complete.",
            "state": {
                "rejection_mode": "ON",
                "interaction_state": "FINALIZED",
                "pathway_lifecycle_status": "ENTERED",
                "pathway_finalized": True,
                "controlling_mode": "Normal Rejection Mode",
                "current_pathway_control": "rejection",
                "setup_direction": "SHORT",
                "active_liquidity": active_liquidity,
                "leg1_status": "COMPLETE",
                "leg1_state_locked": True,
                "leg2_status": "VALIDATED",
                "step5_confirmed": True,
                "step5_participation_validated": True,
                "leg2_candle": leg2_candle,
                "leg2_candle_a": leg2_candle,
                "leg2_candle_a_time": leg2_candle["timestamp"],
                "anchor_extreme": leg1_candle["high"],
            },
            "events": [],
        },
        "step6": {
            "step": "Step 6",
            "status": "ENTRY_CONFIRMED",
            "next_step": "Step 10",
            "entry_type": "Extended Retrace Entry",
            "entry_price": 29055.75,
            "reason": "Seeded completed prior PMH rejection entry.",
            "state": {
                "entry_triggered": True,
                "entry_model_triggered": "Extended Retrace Entry",
                "entry_price": 29055.75,
                "entry_time": entry_candle["timestamp"],
                "interaction_state": "FINALIZED",
                "pathway_lifecycle_status": "ENTERED",
                "pathway_finalized": True,
                "setup_direction": "SHORT",
                "controlling_mode": "Normal Rejection Mode",
                "current_pathway_control": "rejection",
                "active_liquidity": active_liquidity,
                "leg2_candle": leg2_candle,
                "entry_candle": entry_candle,
            },
            "events": [],
        },
    }
    state = _read_json(state_path)
    by_symbol = dict(state.get("state_by_symbol") or {})
    by_symbol[symbol_key] = symbol_state
    state["state_by_symbol"] = by_symbol
    state["last_interacted_liquidity_by_symbol"] = {**dict(state.get("last_interacted_liquidity_by_symbol") or {}), symbol_key: active_liquidity}
    _write_json(state_path, state)


def level_price(tv_context: dict[str, Any], level_name: str) -> float:
    levels = tv_context.get("levels") if isinstance(tv_context, dict) else None
    level = levels.get(level_name) if isinstance(levels, dict) else None
    if not isinstance(level, dict):
        raise ValueError(f"TradingView context is missing level {level_name}")
    if str(level.get("status") or "").upper() != "ACTIVE":
        raise ValueError(f"TradingView level {level_name} is not ACTIVE")
    try:
        return float(level["price"])
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError(f"TradingView level {level_name} has no numeric price") from exc


def candle_at(base_time: datetime, index: int, open_: float, high: float, low: float, close: float) -> dict[str, Any]:
    timestamp = (base_time + timedelta(minutes=index)).isoformat().replace("+00:00", "Z")
    return {
        "timestamp": timestamp,
        "open": round(open_, 2),
        "high": round(high, 2),
        "low": round(low, 2),
        "close": round(close, 2),
    }


def upper_rejection_candles(level: float, base_time: datetime) -> list[dict[str, Any]]:
    candles = [
        (0, (-5.00, 5.75, -10.00, -1.00)),
        (1, (-23.50, 22.25, -36.50, 0.75)),
        (2, (3.00, 44.00, -7.50, 32.00)),
        (3, (32.50, 61.25, 26.75, 39.50)),
        (4, (39.25, 46.25, 22.25, 39.25)),
        (5, (42.25, 48.25, 32.25, 43.25)),
        (6, (43.50, 107.00, 43.50, 105.75)),
        (7, (104.75, 130.25, 103.25, 114.75)),
    ]
    return [candle_at(base_time, minute, *(level + value for value in values)) for minute, values in candles]


def lower_rejection_candles(level: float, base_time: datetime) -> list[dict[str, Any]]:
    return [mirror_candle(candle, level) for candle in upper_rejection_candles(level, base_time)]


def rs_continuation_tail(level: float, base_time: datetime, start_index: int = 11) -> list[dict[str, Any]]:
    candles = [
        (start_index, (15.25, 27.75, -9.75, -8.50)),
        (start_index + 1, (-8.75, 14.50, -18.50, 6.75)),
        (start_index + 2, (6.75, 13.50, -34.00, -24.50)),
        (start_index + 3, (-24.25, 2.25, -40.00, -15.50)),
    ]
    return [candle_at(base_time, minute, *(level + value for value in values)) for minute, values in candles]


def rs_continuation_641_647_candles(_level: float) -> list[dict[str, Any]]:
    rows = [
        ("2026-05-19T13:41:00Z", 28960.0, 28970.0, 28930.0, 28953.0),
        ("2026-05-19T13:42:00Z", 28953.0, 28965.5, 28928.0, 28929.25),
        ("2026-05-19T13:43:00Z", 28929.0, 28952.25, 28919.25, 28944.5),
        ("2026-05-19T13:44:00Z", 28944.5, 28951.25, 28903.75, 28913.25),
        ("2026-05-19T13:45:00Z", 28913.5, 28940.0, 28903.5, 28922.25),
        ("2026-05-19T13:46:00Z", 28922.25, 28935.0, 28895.0, 28905.0),
        ("2026-05-19T13:47:00Z", 28905.0, 28920.0, 28890.0, 28900.0),
    ]
    return [
        {"timestamp": ts, "open": open_, "high": high, "low": low, "close": close}
        for ts, open_, high, low, close in rows
    ]


def sr_continuation_tail(level: float, base_time: datetime, start_index: int = 5) -> list[dict[str, Any]]:
    return [mirror_candle(candle, level) for candle in rs_continuation_tail(level, base_time, start_index)]


def mirror_candle(candle: dict[str, Any], level: float) -> dict[str, Any]:
    mirrored_open = level - (float(candle["open"]) - level)
    mirrored_high = level - (float(candle["low"]) - level)
    mirrored_low = level - (float(candle["high"]) - level)
    mirrored_close = level - (float(candle["close"]) - level)
    return {
        **candle,
        "open": round(mirrored_open, 2),
        "high": round(max(mirrored_high, mirrored_low), 2),
        "low": round(min(mirrored_high, mirrored_low), 2),
        "close": round(mirrored_close, 2),
    }


def build_scenario(symbol: str, scenario: str, tv_context: dict[str, Any]) -> list[dict[str, Any]]:
    base_time = datetime(2026, 5, 19, 13, 30, tzinfo=timezone.utc)
    if scenario == "pmh_rejection_to_entry":
        return upper_rejection_candles(level_price(tv_context, "PMH"), base_time)
    if scenario == "pml_rejection_to_entry":
        return lower_rejection_candles(level_price(tv_context, "PML"), base_time)
    if scenario == "rs_continuation_641_647":
        return rs_continuation_641_647_candles(level_price(tv_context, "PMH"))
    if scenario == "rs_continuation_to_entry":
        level = level_price(tv_context, "PMH")
        return upper_rejection_candles(level, base_time) + rs_continuation_tail(level, base_time, start_index=12)
    if scenario == "sr_continuation_to_entry":
        level = level_price(tv_context, "PML")
        return lower_rejection_candles(level, base_time) + sr_continuation_tail(level, base_time, start_index=12)
    raise ValueError(f"Unknown scenario: {scenario}")


def load_manual_candles(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candles = payload.get("candles") if isinstance(payload, dict) else payload
    if not isinstance(candles, list):
        raise ValueError("Manual candle file must be a list or an object with a candles list")
    normalized = []
    for index, candle in enumerate(candles):
        if not isinstance(candle, dict):
            raise ValueError(f"Candle #{index + 1} is not an object")
        missing = [key for key in ("open", "high", "low", "close") if candle.get(key) is None]
        if missing:
            raise ValueError(f"Candle #{index + 1} missing fields: {', '.join(missing)}")
        timestamp = candle.get("timestamp") or candle.get("time") or (
            datetime(2026, 5, 19, 13, 31, tzinfo=timezone.utc) + timedelta(minutes=index)
        ).isoformat().replace("+00:00", "Z")
        normalized.append(
            {
                "timestamp": timestamp,
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"]),
            }
        )
    return normalized


def snapshot_for_candle(symbol: str, candle: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "EntryAgent/dry_run_injector.py",
        "symbol": symbol,
        "latest_price": candle["close"],
        "latest_bar_time": candle["timestamp"],
        "ohlc": {
            "open": candle["open"],
            "high": candle["high"],
            "low": candle["low"],
            "close": candle["close"],
        },
        "ohlc_is_closed": True,
        "dry_run": True,
    }


def expected_for_index(scenario: str | None, index: int, total: int) -> Callable[[dict[str, Any]], tuple[bool, str]] | None:
    if not scenario:
        return None
    if scenario == "rs_continuation_641_647":
        checks = [
            lambda status: (status.get("sr_rs_context") == "Normal Rejection Mode" and status.get("selected_pathway") == "rejection", "R/S wick boundary pending; continuation Step 2 WAIT"),
            lambda status: (
                status.get("selected_pathway") == "continuation"
                and status.get("sr_rs_context") == "R/S"
                and status.get("setup_direction") == "LONG",
                "R/S continuation Step 2 active with LONG ownership",
            ),
            lambda status: (
                status.get("selected_pathway") == "continuation"
                and status.get("sr_rs_context") == "R/S"
                and status.get("setup_direction") == "LONG",
                "R/S continuation ownership retained",
            ),
            lambda status: (
                status.get("selected_pathway") == "continuation"
                and status.get("sr_rs_context") == "R/S"
                and status.get("setup_direction") == "LONG"
                and status.get("rejection_side", {}).get("setup_direction") != "SHORT"
                and status.get("leg2_state") in {"CONFIRMED", "VALIDATED"},
                "R/S continuation Step 5 confirms without stale rejection SHORT",
            ),
            lambda status: (
                status.get("selected_pathway") == "continuation"
                and status.get("sr_rs_context") == "R/S"
                and status.get("entry_status") == "CONFIRM",
                "R/S continuation Step 6 entry confirms",
            ),
        ]
        if index >= len(checks):
            return None
        return checks[index]
    continuation = scenario in {"rs_continuation_to_entry", "sr_continuation_to_entry"}
    checks: list[Callable[[dict[str, Any]], tuple[bool, str]]] = [
        lambda status: (status.get("current_step_status") != "CONFIRMED", "WAIT / initial raid boundary only"),
        lambda status: (status.get("current_step_status") != "CONFIRMED", "WAIT / close below pending boundary"),
        lambda status: (status.get("current_step_status") == "CONFIRMED", "Step 2 confirmed"),
        lambda status: (status.get("leg1_state") != "WAIT", "Step 4 Leg 1"),
        lambda status: (status.get("leg1_locked") is True, "Leg 1 locked; Step 5 handoff armed"),
        lambda status: (status.get("leg2_state") in {"CONFIRMED", "VALIDATED"}, "Step 5 Leg 2 locked"),
        lambda status: (status.get("leg2_state") == "VALIDATED" and status.get("entry_status") != "CONFIRM", "Step 6 first eligible candle assigned as SC"),
        lambda status: (
            status.get("extended_retrace_blocked_immediate_entry") is True
            and status.get("entry_status") == "CONFIRM",
            "Extended Retrace intrabar ENTRY_CONFIRMED",
        ),
    ]
    if continuation:
        checks.extend(
            [
                lambda status: (status.get("sr_rs_context") in {"R/S", "S/R"}, "Continuation Step 2 active"),
                lambda status: (status.get("sr_rs_context") in {"R/S", "S/R"} and status.get("leg1_state") != "WAIT", "Continuation Step 4 Leg 1"),
                lambda status: (status.get("sr_rs_context") in {"R/S", "S/R"} and status.get("leg1_locked") is True, "Continuation Leg 1 locked; Step 5 handoff armed"),
                lambda status: (status.get("sr_rs_context") in {"R/S", "S/R"} and status.get("leg2_state") == "VALIDATED", "Continuation Step 5 Leg 2"),
            ]
        )
    if index >= len(checks):
        return None
    return checks[index]


def print_status(index: int, candle: dict[str, Any], status: dict[str, Any], expected: Callable[[dict[str, Any]], tuple[bool, str]] | None, show_cc_json: bool) -> bool:
    passed = True
    expected_text = "n/a"
    if expected is not None:
        passed, expected_text = expected(status)
    result_text = "PASS" if passed else "FAIL"
    print(f"\n[{index + 1}] injected {candle['timestamp']} O={candle['open']} H={candle['high']} L={candle['low']} C={candle['close']}")
    for field in STATUS_FIELDS:
        print(f"  {field}: {status.get(field)}")
    print(f"  expected: {expected_text}")
    print(f"  result: {result_text}")
    if show_cc_json:
        print("  cc_json:")
        print(json.dumps(status, indent=2, sort_keys=True))
    return passed


def run_dry_run(
    symbol: str,
    candles: Iterable[dict[str, Any]],
    scenario: str | None = None,
    pause: bool = False,
    show_cc_json: bool = False,
) -> list[dict[str, Any]]:
    symbol_key = root(symbol)
    candles = list(candles)
    statuses: list[dict[str, Any]] = []
    closed_bars: list[dict[str, Any]] = []
    current_snapshot: dict[str, Any] | None = None

    def fake_snapshot(_symbol: str = symbol_key) -> dict[str, Any]:
        if current_snapshot is None:
            return {
                "source": "EntryAgent/dry_run_injector.py",
                "symbol": symbol_key,
                "latest_price": None,
                "latest_bar_time": None,
                "ohlc": None,
                "ohlc_is_closed": None,
                "dry_run": True,
            }
        return copy.deepcopy(current_snapshot)

    def fake_recent_closed_bars(_symbol: str, limit: int = 2) -> list[dict[str, Any]]:
        return copy.deepcopy(closed_bars[-limit:])

    entry_agent.get_latest_market_snapshot = fake_snapshot
    entry_agent.recent_closed_bars = fake_recent_closed_bars

    for index, candle in enumerate(candles):
        current_snapshot = snapshot_for_candle(symbol_key, candle)
        closed_bars.append(copy.deepcopy(current_snapshot["ohlc"] | {"timestamp": candle["timestamp"]}))
        status = entry_agent.build_entry_status(symbol_key)
        statuses.append(status)
        check = expected_for_index(scenario, index, len(candles))
        passed = print_status(index, candle, status, check, show_cc_json)
        if not passed:
            print("  stopping_on_failure: true")
            break
        if pause and index < len(candles) - 1:
            input("Press Enter to inject next candle...")
    return statuses


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run Entry Agent closed-candle injector.")
    parser.add_argument("--symbol", default="NQ", help="Root symbol to simulate, e.g. NQ/YM/RTY.")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), help="Built-in synthetic scenario.")
    parser.add_argument("--candles", type=Path, help="Manual candle JSON file.")
    parser.add_argument("--pause", action="store_true", help="Wait for Enter between injected candles.")
    parser.add_argument("--show-cc-json", action="store_true", help="Print exact Command Center /entry/status payload after each candle.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if bool(args.scenario) == bool(args.candles):
        print("Provide exactly one of --scenario or --candles.", file=sys.stderr)
        return 2

    symbol_key = root(args.symbol)
    tv_context = entry_agent.load_tv_context(symbol_key)
    if not isinstance(tv_context, dict):
        print(f"No live TradingView context found for {symbol_key}.", file=sys.stderr)
        return 1

    try:
        candles = build_scenario(symbol_key, args.scenario, tv_context) if args.scenario else load_manual_candles(args.candles)
    except Exception as exc:
        print(f"Could not build dry-run candles: {exc}", file=sys.stderr)
        return 1

    print("Entry Agent DRY-RUN candle injector")
    print(f"symbol: {symbol_key}")
    print(f"scenario: {args.scenario or args.candles}")
    print(f"tv_context_status: {entry_agent.tv_context_freshness_status(tv_context)}")
    print("safety: isolated temp state, no executor/order/webhook calls")

    try:
        with isolated_entry_agent_state(symbol_key) as temp_state_path:
            if args.scenario == "rs_continuation_641_647":
                seed_completed_pmh_rejection_state(temp_state_path, symbol_key, level_price(tv_context, "PMH"))
            statuses = run_dry_run(
                symbol_key,
                candles,
                scenario=args.scenario,
                pause=args.pause,
                show_cc_json=args.show_cc_json,
            )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    final_status = statuses[-1] if statuses else {}
    final_confirmed = final_status.get("entry_status") == "CONFIRM"
    print(f"\nfinal_entry_status: {'ENTRY_CONFIRMED' if final_confirmed else final_status.get('entry_status')}")
    print(f"dry_run_result: {'PASS' if final_confirmed else 'CHECK_OUTPUT'}")
    return 0 if statuses else 1


if __name__ == "__main__":
    raise SystemExit(main())
