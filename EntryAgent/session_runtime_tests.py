from __future__ import annotations

import copy
import importlib
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch


def _valid_webhook_payload(symbol: str = "CME_MINI:NQ1!", timestamp: str = "2026-06-22T13:15:00Z") -> dict:
    return {
        "source": "randle_taylor_map",
        "symbol": symbol,
        "timestamp": timestamp,
        "session_date": "2026-06-22",
        "time_zone": "America/Los_Angeles",
        "locked": True,
        "session_lock_price": 100.0,
        "atr_1m_14": 10.0,
        "daily_atr14": 100.0,
        "liquidity_map": {
            "levels": [
                {"name": "PMH", "price": 100.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                {"name": "ONH", "price": 101.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                {"name": "PML", "price": 90.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                {"name": "ONL", "price": 89.0, "status": "ACTIVE", "stack_group": "LOW 1"},
            ],
            "stacks": [
                {
                    "name": "HIGH 1",
                    "members": ["PMH", "ONH"],
                    "close_boundary_name": "PMH",
                    "close_boundary_price": 100.0,
                    "extreme_boundary_name": "ONH",
                    "extreme_boundary_price": 101.0,
                },
                {
                    "name": "LOW 1",
                    "members": ["PML", "ONL"],
                    "close_boundary_name": "PML",
                    "close_boundary_price": 90.0,
                    "extreme_boundary_name": "ONL",
                    "extreme_boundary_price": 89.0,
                },
            ],
        },
        "midpoints": {"PML_ONL": 89.5},
        "exhaustion_boundaries": {"PML_ONL": {"side": "lower", "mid_50": 89.5, "remaining_25": 89.25}},
        "taylor_context": {"t_plus": {"state": "UP"}},
    }


def test_tv_context_server_and_entry_agent_share_runtime_tv_context_paths() -> None:
    original_root = os.environ.get("RANDLE_DATA_ROOT")
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["RANDLE_DATA_ROOT"] = temp_dir
            entry_agent = importlib.reload(importlib.import_module("entry_agent"))
            tv_context_server = importlib.reload(importlib.import_module("tv_context_server"))

            expected_root = Path(temp_dir) / "entry_agent"
            expected_context = expected_root / "tv_context.json"
            expected_context_by_symbol = expected_root / "tv_context_by_symbol.json"
            expected_events = expected_root / "tv_context_events.jsonl"

            assert entry_agent.TV_CONTEXT_PATH == expected_context
            assert entry_agent.TV_CONTEXT_BY_SYMBOL_PATH == expected_context_by_symbol
            assert tv_context_server.TV_CONTEXT_PATH == expected_context
            assert tv_context_server.TV_CONTEXT_BY_SYMBOL_PATH == expected_context_by_symbol
            assert tv_context_server.TV_CONTEXT_EVENTS_PATH == expected_events
            assert tv_context_server.TV_CONTEXT_PATH != Path(tv_context_server.BASE_DIR) / "tv_context.json"
            assert tv_context_server.TV_CONTEXT_BY_SYMBOL_PATH != Path(tv_context_server.BASE_DIR) / "tv_context_by_symbol.json"
            assert tv_context_server.TV_CONTEXT_EVENTS_PATH != Path(tv_context_server.BASE_DIR) / "tv_context_events.jsonl"
    finally:
        if original_root is None:
            os.environ.pop("RANDLE_DATA_ROOT", None)
        else:
            os.environ["RANDLE_DATA_ROOT"] = original_root
        importlib.reload(importlib.import_module("entry_agent"))
        importlib.reload(importlib.import_module("tv_context_server"))


def test_tv_context_webhook_rejects_rty_symbol() -> None:
    import tv_context_server

    original_levels = tv_context_server.LEVELS_PATH
    original_levels_by_symbol = tv_context_server.LEVELS_BY_SYMBOL_PATH
    original_context = tv_context_server.TV_CONTEXT_PATH
    original_context_by_symbol = tv_context_server.TV_CONTEXT_BY_SYMBOL_PATH
    original_events = tv_context_server.TV_CONTEXT_EVENTS_PATH
    original_log_dir = tv_context_server.ENTRY_LOG_DIR
    original_log_path = tv_context_server.ENTRY_DECISIONS_LOG_PATH
    original_latest = dict(tv_context_server.LATEST_TV_CONTEXT_BY_SYMBOL)
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            tv_context_server.LEVELS_PATH = temp_root / "levels.json"
            tv_context_server.LEVELS_BY_SYMBOL_PATH = temp_root / "levels_by_symbol.json"
            tv_context_server.TV_CONTEXT_PATH = temp_root / "tv_context.json"
            tv_context_server.TV_CONTEXT_BY_SYMBOL_PATH = temp_root / "tv_context_by_symbol.json"
            tv_context_server.TV_CONTEXT_EVENTS_PATH = temp_root / "tv_context_events.jsonl"
            tv_context_server.ENTRY_LOG_DIR = temp_root / "logs"
            tv_context_server.ENTRY_LOG_DIR.mkdir(parents=True, exist_ok=True)
            tv_context_server.ENTRY_DECISIONS_LOG_PATH = tv_context_server.ENTRY_LOG_DIR / "entry_decisions.jsonl"
            tv_context_server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()

            with patch.dict(os.environ, {"TV_CONTEXT_INTERNAL_RELAY_TOKEN": "session-runtime-test-token"}, clear=False):
                with tv_context_server.app.test_client() as client:
                    response = client.post(
                        "/webhook/tv-context",
                        json=_valid_webhook_payload(symbol="RTY1!"),
                        headers={"X-Randle-Relay-Token": "session-runtime-test-token"},
                    )
                assert response.status_code == 400
                assert response.get_json()["error"] == "unsupported symbol"
    finally:
        tv_context_server.LEVELS_PATH = original_levels
        tv_context_server.LEVELS_BY_SYMBOL_PATH = original_levels_by_symbol
        tv_context_server.TV_CONTEXT_PATH = original_context
        tv_context_server.TV_CONTEXT_BY_SYMBOL_PATH = original_context_by_symbol
        tv_context_server.TV_CONTEXT_EVENTS_PATH = original_events
        tv_context_server.ENTRY_LOG_DIR = original_log_dir
        tv_context_server.ENTRY_DECISIONS_LOG_PATH = original_log_path
        tv_context_server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
        tv_context_server.LATEST_TV_CONTEXT_BY_SYMBOL.update(original_latest)


def test_tv_context_webhook_rejects_missing_required_fields() -> None:
    import tv_context_server

    payload = _valid_webhook_payload()
    payload.pop("timestamp")

    with patch.dict(os.environ, {"TV_CONTEXT_INTERNAL_RELAY_TOKEN": "session-runtime-test-token"}, clear=False):
        with tv_context_server.app.test_client() as client:
            response = client.post(
                "/webhook/tv-context",
                json=payload,
                headers={"X-Randle-Relay-Token": "session-runtime-test-token"},
            )
        assert response.status_code == 400
        assert response.get_json()["error"] == "timestamp is required"


def test_observation_window_creates_no_step2_state_and_persists_pre_open_extreme() -> None:
    import entry_agent

    original_state_path = entry_agent.STATE_PATH
    original_get_latest = entry_agent.get_latest_market_snapshot
    original_load_tv = entry_agent.load_tv_context
    original_recent = entry_agent.recent_closed_bars
    original_load_atr = entry_agent.load_rithmic_atr_snapshot
    original_append_audit = entry_agent.append_entry_agent_audit_row
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry_agent.STATE_PATH = Path(temp_dir) / "entry_agent_state.json"
            entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
            entry_agent.load_tv_context = lambda _symbol=None: {
                "symbol": "NQ",
                "normalized_symbol": "NQ",
                "source": "randle_taylor_map",
                "received_at": "2026-06-22T13:15:00Z",
                "session_date": "2026-06-22",
                "time_zone": "America/Los_Angeles",
                "locked": True,
                "context_locked": True,
                "locked_for_day": True,
                "liquidity_context_locked": True,
                "liquidity_context_locked_at": "2026-06-22T13:15:00Z",
                "session_lock_price": 100.0,
                "atr_1m_14": 10.0,
                "daily_atr14": 100.0,
                "levels": {
                    "PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "ONH": {"price": 101.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "PML": {"price": 90.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                    "ONL": {"price": 89.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                },
            }
            bars: list[dict] = []

            def market_snapshot(_symbol: str = "NQ") -> dict:
                return {
                    "symbol": "NQ",
                    "normalized_symbol": "NQ",
                    "latest_price": 102.0,
                    "latest_bar_time": "2026-06-22T13:25:00Z",
                    "ohlc_is_closed": True,
                    "ohlc": {"open": 99.5, "high": 103.0, "low": 99.0, "close": 102.0},
                }

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol="NQ", limit=120: list(bars)[-limit:]
            entry_agent.load_rithmic_atr_snapshot = lambda _symbol="NQ": {"atr_1m_14": 10.0}

            snapshot = entry_agent.run_once("NQ", persist=True)
            state = entry_agent.load_entry_state()
            symbol_state = state.get("state_by_symbol", {}).get("NQ", state)

            assert snapshot["step_2_1a"]["step_2_activated"] is False
            assert snapshot["step_2_1a"]["active_level"] is None
            assert snapshot["rejection"]["rejection_mode"] == "OFF"
            assert symbol_state["step_2_1a"]["step2_locked_owner"] is None
            assert symbol_state["pre_open_observed_extreme"]["side"] == "upper"
            assert symbol_state["pre_open_observed_extreme"]["price"] == 103.0
            assert symbol_state["pre_open_observed_extreme"]["source"] == "observation_window"
    finally:
        entry_agent.STATE_PATH = original_state_path
        entry_agent.get_latest_market_snapshot = original_get_latest
        entry_agent.load_tv_context = original_load_tv
        entry_agent.recent_closed_bars = original_recent
        entry_agent.load_rithmic_atr_snapshot = original_load_atr
        entry_agent.append_entry_agent_audit_row = original_append_audit


def test_first_post_open_step2_starts_clean_from_pre_open_extreme() -> None:
    import entry_agent

    original_state_path = entry_agent.STATE_PATH
    original_get_latest = entry_agent.get_latest_market_snapshot
    original_load_tv = entry_agent.load_tv_context
    original_recent = entry_agent.recent_closed_bars
    original_load_atr = entry_agent.load_rithmic_atr_snapshot
    original_append_audit = entry_agent.append_entry_agent_audit_row
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry_agent.STATE_PATH = Path(temp_dir) / "entry_agent_state.json"
            entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
            entry_agent.load_tv_context = lambda _symbol=None: {
                "symbol": "NQ",
                "normalized_symbol": "NQ",
                "source": "randle_taylor_map",
                "received_at": "2026-06-22T13:15:00Z",
                "session_date": "2026-06-22",
                "time_zone": "America/Los_Angeles",
                "locked": True,
                "context_locked": True,
                "locked_for_day": True,
                "liquidity_context_locked": True,
                "liquidity_context_locked_at": "2026-06-22T13:15:00Z",
                "session_lock_price": 100.0,
                "atr_1m_14": 10.0,
                "daily_atr14": 100.0,
                "levels": {
                    "PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "ONH": {"price": 101.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "PML": {"price": 90.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                    "ONL": {"price": 89.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                },
            }
            bars: list[dict] = []
            snapshots = [
                {
                    "symbol": "NQ",
                    "normalized_symbol": "NQ",
                    "latest_price": 102.0,
                    "latest_bar_time": "2026-06-22T13:25:00Z",
                    "ohlc_is_closed": True,
                    "ohlc": {"open": 99.5, "high": 103.0, "low": 99.0, "close": 102.0},
                },
                {
                    "symbol": "NQ",
                    "normalized_symbol": "NQ",
                    "latest_price": 102.5,
                    "latest_bar_time": "2026-06-22T13:30:00Z",
                    "ohlc_is_closed": True,
                    "ohlc": {"open": 101.5, "high": 102.75, "low": 101.25, "close": 102.5},
                },
            ]
            index = {"value": 0}

            def market_snapshot(_symbol: str = "NQ") -> dict:
                current = snapshots[index["value"]]
                return dict(current)

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol="NQ", limit=120: list(bars)[-limit:]
            entry_agent.load_rithmic_atr_snapshot = lambda _symbol="NQ": {"atr_1m_14": 10.0}

            first = entry_agent.run_once("NQ", persist=True)
            bars.append({"timestamp": first["latest_bar_time"], **first["ohlc"]})
            index["value"] = 1
            second = entry_agent.run_once("NQ", persist=True)

            assert first["step_2_1a"]["active_level"] is None
            assert second["step_2_1a"]["blocked"] is False
            assert second["step_2_1a"]["step_2_activated"] is False
            assert second["step_2_1a"]["active_level"] == "ONH"
            assert second["step_2_1a"]["pre_activation_probe_boundary"]["active"] is True
            assert second["step_2_1a"]["pre_activation_probe_boundary"]["boundary_price"] == 103.0
            assert any(
                event.get("event") == "pre_open_observed_extreme_seeded"
                for event in second["step_2_1a"]["events"]
                if isinstance(event, dict)
            )
    finally:
        entry_agent.STATE_PATH = original_state_path
        entry_agent.get_latest_market_snapshot = original_get_latest
        entry_agent.load_tv_context = original_load_tv
        entry_agent.recent_closed_bars = original_recent
        entry_agent.load_rithmic_atr_snapshot = original_load_atr
        entry_agent.append_entry_agent_audit_row = original_append_audit


def test_ym_pre_open_observed_extreme_carries_from_1329_to_1330_status_refresh() -> None:
    import entry_agent

    original_state_path = entry_agent.STATE_PATH
    original_get_latest = entry_agent.get_latest_market_snapshot
    original_load_tv = entry_agent.load_tv_context
    original_load_raw_tv = entry_agent.load_raw_tv_context
    original_recent = entry_agent.recent_closed_bars
    original_load_atr = entry_agent.load_rithmic_atr_snapshot
    original_append_audit = entry_agent.append_entry_agent_audit_row
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry_agent.STATE_PATH = Path(temp_dir) / "entry_agent_state.json"
            entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
            levels = {
                "PMH": {"price": 52945.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "PML": {"price": 52712.0, "status": "ACTIVE", "stack_group": "NONE"},
                "LH": {"price": 52781.0, "status": "INACTIVE", "stack_group": "NONE"},
                "LL": {"price": 52616.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "ONH": {"price": 52945.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "ONL": {"price": 52551.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "YH": {"price": 53105.0, "status": "ACTIVE", "stack_group": "NONE"},
                "YL": {"price": 52381.0, "status": "ACTIVE", "stack_group": "NONE"},
            }
            raw_tv_context = {
                "symbol": "YM1!",
                "normalized_symbol": "YM",
                "source": "tradingview_level_helper",
                "received_at": "2026-07-02T13:15:07.659783Z",
                "session_date": "2026-07-02",
                "time_zone": "America/Los_Angeles",
                "locked": True,
                "context_locked": True,
                "locked_for_day": True,
                "liquidity_context_locked": True,
                "liquidity_context_locked_at": "2026-07-02T13:15:07.659783Z",
                "session_lock_price": None,
                "daily_atr14": 667.3870239408,
                "levels": levels,
                "liquidity_map": {"levels": [], "stacks": []},
                "locked_liquidity_context": {
                    "levels": levels,
                    "liquidity_map": {"levels": [], "stacks": []},
                    "session_date": "2026-07-02",
                    "locked_at": "2026-07-02T13:15:07.659783Z",
                    "source": "tradingview_level_helper",
                    "session_lock_price": None,
                    "daily_atr14": 667.3870239408,
                    "midpoints": {},
                    "exhaustion_boundaries": {},
                },
            }
            entry_agent.load_tv_context = lambda _symbol=None: dict(raw_tv_context)
            entry_agent.load_raw_tv_context = lambda _symbol=None: dict(raw_tv_context)
            entry_agent.recent_closed_bars = lambda _symbol="YM", limit=120: []
            entry_agent.load_rithmic_atr_snapshot = lambda _symbol="YM": {"atr_1m_14": 66.0}

            snapshots = [
                {
                    "symbol": "YM",
                    "normalized_symbol": "YM",
                    "latest_price": 52950.0,
                    "latest_bar_time": "2026-07-02T13:29:00Z",
                    "ohlc_is_closed": True,
                    "ohlc": {"open": 52914.0, "high": 52967.0, "low": 52905.0, "close": 52950.0},
                },
                {
                    "symbol": "YM",
                    "normalized_symbol": "YM",
                    "latest_price": 52904.0,
                    "latest_bar_time": "2026-07-02T13:30:00Z",
                    "ohlc_is_closed": True,
                    "ohlc": {"open": 52956.0, "high": 52984.0, "low": 52875.0, "close": 52904.0},
                },
            ]
            index = {"value": 0}

            def market_snapshot(_symbol: str = "YM") -> dict:
                return dict(snapshots[index["value"]])

            entry_agent.get_latest_market_snapshot = market_snapshot

            status_1329 = entry_agent.build_entry_status("YM")
            persisted_after_1329 = entry_agent.load_entry_state()["state_by_symbol"]["YM"]["pre_open_observed_extreme"]
            index["value"] = 1
            status_1330 = entry_agent.build_entry_status("YM")

            expected_extreme = {
                "symbol": "YM",
                "side": "upper",
                "price": 52967.0,
                "timestamp": "2026-07-02T13:29:00Z",
                "source": "observation_window",
                "session_date": "2026-07-02",
                "time_zone": "America/Los_Angeles",
                "source_level": "ONH",
                "stack_group": "HIGH 1",
                "stack_components": ["ONH", "PMH"],
                "locked_boundary_price": 52945.0,
                "session_lock_price": None,
                "liquidity_context_locked_at": "2026-07-02T13:15:07.659783Z",
            }

            assert status_1329["pre_open_observed_extreme"] == expected_extreme
            assert persisted_after_1329 == expected_extreme
            assert status_1330["pre_open_observed_extreme"] == expected_extreme
            assert status_1330["active_liquidity_name"] == "PMH/ONH"
            assert status_1330["liquidity_price"] == 52945.0
            assert status_1330["frozen_tv_level"] == 52945.0
            assert status_1330["wick_boundary_extreme"] == 52984.0
            assert status_1330["wait_reason"] == "Step 2 pending: waiting for a later candle close above raid boundary 52984.0."
    finally:
        entry_agent.STATE_PATH = original_state_path
        entry_agent.get_latest_market_snapshot = original_get_latest
        entry_agent.load_tv_context = original_load_tv
        entry_agent.load_raw_tv_context = original_load_raw_tv
        entry_agent.recent_closed_bars = original_recent
        entry_agent.load_rithmic_atr_snapshot = original_load_atr
        entry_agent.append_entry_agent_audit_row = original_append_audit


def test_pending_step2_owner_same_side_wick_releases_a_and_starts_b() -> None:
    import entry_agent

    original_state_path = entry_agent.STATE_PATH
    original_get_latest = entry_agent.get_latest_market_snapshot
    original_load_tv = entry_agent.load_tv_context
    original_recent = entry_agent.recent_closed_bars
    original_load_atr = entry_agent.load_rithmic_atr_snapshot
    original_append_audit = entry_agent.append_entry_agent_audit_row
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry_agent.STATE_PATH = Path(temp_dir) / "entry_agent_state.json"
            entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
            entry_agent.load_tv_context = lambda _symbol=None: {
                "symbol": "NQ",
                "normalized_symbol": "NQ",
                "source": "randle_taylor_map",
                "received_at": "2026-07-02T13:15:00Z",
                "session_date": "2026-07-02",
                "time_zone": "America/Los_Angeles",
                "locked": True,
                "context_locked": True,
                "locked_for_day": True,
                "liquidity_context_locked": True,
                "liquidity_context_locked_at": "2026-07-02T13:15:00Z",
                "session_lock_price": 100.0,
                "atr_1m_14": 10.0,
                "daily_atr14": 100.0,
                "levels": {
                    "ONH": {"price": 101.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "YH": {"price": 104.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "PML": {"price": 90.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "YL": {"price": 86.0, "status": "ACTIVE", "stack_group": "NONE"},
                },
            }
            bars: list[dict] = []
            snapshots = [
                {
                    "symbol": "NQ",
                    "normalized_symbol": "NQ",
                    "latest_price": 100.0,
                    "latest_bar_time": "2026-07-02T13:30:00Z",
                    "ohlc_is_closed": True,
                    "ohlc": {"open": 100.0, "high": 103.0, "low": 99.75, "close": 100.0},
                },
                {
                    "symbol": "NQ",
                    "normalized_symbol": "NQ",
                    "latest_price": 104.0,
                    "latest_bar_time": "2026-07-02T13:31:00Z",
                    "ohlc_is_closed": True,
                    "ohlc": {"open": 100.0, "high": 104.5, "low": 99.75, "close": 102.0},
                },
            ]
            index = {"value": 0}

            def market_snapshot(_symbol: str = "NQ") -> dict:
                return dict(snapshots[index["value"]])

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol="NQ", limit=120: list(bars)[-limit:]
            entry_agent.load_rithmic_atr_snapshot = lambda _symbol="NQ": {"atr_1m_14": 10.0}

            first = entry_agent.run_once("NQ", persist=True)
            bars.append({"timestamp": first["latest_bar_time"], **first["ohlc"]})
            index["value"] = 1
            second = entry_agent.run_once("NQ", persist=True)

            assert first["step_2_1a"]["step_2_activated"] is False
            assert first["step_2_1a"]["active_level"] == "ONH"
            assert first["step_2_1a"]["pending_step2_owner"]["active_liquidity_name"] == "ONH"
            assert second["step_2_1a"]["step_2_activated"] is False
            assert second["step_2_1a"]["active_level"] == "YH"
            assert second["step_2_1a"]["level_price"] == 104.0
            assert second["step_2_1a"]["pending_step2_owner"]["active_liquidity_name"] == "YH"
            assert second["step_2_1a"]["pending_step2_owner"]["active_liquidity_price"] == 104.0
            assert second["step_2_1a"]["last_interacted_liquidity"]["name"] == "YH"
            assert second["step_2_1a"]["pre_activation_probe_boundary"]["boundary_price"] == 104.5
    finally:
        entry_agent.STATE_PATH = original_state_path
        entry_agent.get_latest_market_snapshot = original_get_latest
        entry_agent.load_tv_context = original_load_tv
        entry_agent.recent_closed_bars = original_recent
        entry_agent.load_rithmic_atr_snapshot = original_load_atr
        entry_agent.append_entry_agent_audit_row = original_append_audit


def test_pending_step2_owner_opposite_side_wick_releases_a_and_starts_b() -> None:
    import entry_agent

    original_state_path = entry_agent.STATE_PATH
    original_get_latest = entry_agent.get_latest_market_snapshot
    original_load_tv = entry_agent.load_tv_context
    original_recent = entry_agent.recent_closed_bars
    original_load_atr = entry_agent.load_rithmic_atr_snapshot
    original_append_audit = entry_agent.append_entry_agent_audit_row
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry_agent.STATE_PATH = Path(temp_dir) / "entry_agent_state.json"
            entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
            entry_agent.load_tv_context = lambda _symbol=None: {
                "symbol": "NQ",
                "normalized_symbol": "NQ",
                "source": "randle_taylor_map",
                "received_at": "2026-07-02T13:15:00Z",
                "session_date": "2026-07-02",
                "time_zone": "America/Los_Angeles",
                "locked": True,
                "context_locked": True,
                "locked_for_day": True,
                "liquidity_context_locked": True,
                "liquidity_context_locked_at": "2026-07-02T13:15:00Z",
                "session_lock_price": 100.0,
                "atr_1m_14": 10.0,
                "daily_atr14": 100.0,
                "levels": {
                    "ONH": {"price": 101.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "YH": {"price": 104.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "PML": {"price": 90.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "YL": {"price": 86.0, "status": "ACTIVE", "stack_group": "NONE"},
                },
            }
            bars: list[dict] = []
            snapshots = [
                {
                    "symbol": "NQ",
                    "normalized_symbol": "NQ",
                    "latest_price": 100.0,
                    "latest_bar_time": "2026-07-02T13:30:00Z",
                    "ohlc_is_closed": True,
                    "ohlc": {"open": 100.0, "high": 103.0, "low": 99.75, "close": 100.0},
                },
                {
                    "symbol": "NQ",
                    "normalized_symbol": "NQ",
                    "latest_price": 89.5,
                    "latest_bar_time": "2026-07-02T13:31:00Z",
                    "ohlc_is_closed": True,
                    "ohlc": {"open": 100.0, "high": 100.25, "low": 89.0, "close": 100.0},
                },
            ]
            index = {"value": 0}

            def market_snapshot(_symbol: str = "NQ") -> dict:
                return dict(snapshots[index["value"]])

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol="NQ", limit=120: list(bars)[-limit:]
            entry_agent.load_rithmic_atr_snapshot = lambda _symbol="NQ": {"atr_1m_14": 10.0}

            first = entry_agent.run_once("NQ", persist=True)
            bars.append({"timestamp": first["latest_bar_time"], **first["ohlc"]})
            index["value"] = 1
            second = entry_agent.run_once("NQ", persist=True)

            assert first["step_2_1a"]["step_2_activated"] is False
            assert first["step_2_1a"]["active_level"] == "ONH"
            assert second["step_2_1a"]["step_2_activated"] is False
            assert second["step_2_1a"]["active_level"] == "PML"
            assert second["step_2_1a"]["level_price"] == 90.0
            assert second["step_2_1a"]["pending_step2_owner"]["active_liquidity_name"] == "PML"
            assert second["step_2_1a"]["last_interacted_liquidity"]["name"] == "PML"
            assert second["step_2_1a"]["pre_activation_probe_boundary"]["boundary_price"] == 89.0
    finally:
        entry_agent.STATE_PATH = original_state_path
        entry_agent.get_latest_market_snapshot = original_get_latest
        entry_agent.load_tv_context = original_load_tv
        entry_agent.recent_closed_bars = original_recent
        entry_agent.load_rithmic_atr_snapshot = original_load_atr
        entry_agent.append_entry_agent_audit_row = original_append_audit


def test_pending_step2_owner_close_through_releases_a_and_starts_b() -> None:
    import entry_agent

    original_state_path = entry_agent.STATE_PATH
    original_get_latest = entry_agent.get_latest_market_snapshot
    original_load_tv = entry_agent.load_tv_context
    original_recent = entry_agent.recent_closed_bars
    original_load_atr = entry_agent.load_rithmic_atr_snapshot
    original_append_audit = entry_agent.append_entry_agent_audit_row
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry_agent.STATE_PATH = Path(temp_dir) / "entry_agent_state.json"
            entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
            entry_agent.load_tv_context = lambda _symbol=None: {
                "symbol": "NQ",
                "normalized_symbol": "NQ",
                "source": "randle_taylor_map",
                "received_at": "2026-07-02T13:15:00Z",
                "session_date": "2026-07-02",
                "time_zone": "America/Los_Angeles",
                "locked": True,
                "context_locked": True,
                "locked_for_day": True,
                "liquidity_context_locked": True,
                "liquidity_context_locked_at": "2026-07-02T13:15:00Z",
                "session_lock_price": 100.0,
                "atr_1m_14": 10.0,
                "daily_atr14": 100.0,
                "levels": {
                    "ONH": {"price": 101.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "YH": {"price": 104.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "PML": {"price": 90.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "YL": {"price": 86.0, "status": "ACTIVE", "stack_group": "NONE"},
                },
            }
            bars: list[dict] = []
            snapshots = [
                {
                    "symbol": "NQ",
                    "normalized_symbol": "NQ",
                    "latest_price": 100.0,
                    "latest_bar_time": "2026-07-02T13:30:00Z",
                    "ohlc_is_closed": True,
                    "ohlc": {"open": 100.0, "high": 103.0, "low": 99.75, "close": 100.0},
                },
                {
                    "symbol": "NQ",
                    "normalized_symbol": "NQ",
                    "latest_price": 104.25,
                    "latest_bar_time": "2026-07-02T13:31:00Z",
                    "ohlc_is_closed": True,
                    "ohlc": {"open": 100.0, "high": 104.25, "low": 99.75, "close": 104.0},
                },
            ]
            index = {"value": 0}

            def market_snapshot(_symbol: str = "NQ") -> dict:
                return dict(snapshots[index["value"]])

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol="NQ", limit=120: list(bars)[-limit:]
            entry_agent.load_rithmic_atr_snapshot = lambda _symbol="NQ": {"atr_1m_14": 10.0}

            first = entry_agent.run_once("NQ", persist=True)
            bars.append({"timestamp": first["latest_bar_time"], **first["ohlc"]})
            index["value"] = 1
            second = entry_agent.run_once("NQ", persist=True)

            assert first["step_2_1a"]["active_level"] == "ONH"
            assert second["step_2_1a"]["step_2_activated"] is False
            assert second["step_2_1a"]["active_level"] == "YH"
            assert second["step_2_1a"]["level_price"] == 104.0
            assert second["step_2_1a"]["pending_step2_owner"]["active_liquidity_name"] == "YH"
            assert second["step_2_1a"]["pending_step2_owner"]["owner_source"] == "probe"
            assert second["step_2_1a"]["last_interacted_liquidity"]["name"] == "YH"
    finally:
        entry_agent.STATE_PATH = original_state_path
        entry_agent.get_latest_market_snapshot = original_get_latest
        entry_agent.load_tv_context = original_load_tv
        entry_agent.recent_closed_bars = original_recent
        entry_agent.load_rithmic_atr_snapshot = original_load_atr
        entry_agent.append_entry_agent_audit_row = original_append_audit


def test_pending_step2_owner_non_qualifying_touch_does_not_release_a() -> None:
    import entry_agent

    original_state_path = entry_agent.STATE_PATH
    original_get_latest = entry_agent.get_latest_market_snapshot
    original_load_tv = entry_agent.load_tv_context
    original_recent = entry_agent.recent_closed_bars
    original_load_atr = entry_agent.load_rithmic_atr_snapshot
    original_append_audit = entry_agent.append_entry_agent_audit_row
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry_agent.STATE_PATH = Path(temp_dir) / "entry_agent_state.json"
            entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
            entry_agent.load_tv_context = lambda _symbol=None: {
                "symbol": "NQ",
                "normalized_symbol": "NQ",
                "source": "randle_taylor_map",
                "received_at": "2026-07-02T13:15:00Z",
                "session_date": "2026-07-02",
                "time_zone": "America/Los_Angeles",
                "locked": True,
                "context_locked": True,
                "locked_for_day": True,
                "liquidity_context_locked": True,
                "liquidity_context_locked_at": "2026-07-02T13:15:00Z",
                "session_lock_price": 100.0,
                "atr_1m_14": 10.0,
                "daily_atr14": 100.0,
                "levels": {
                    "ONH": {"price": 101.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "YH": {"price": 104.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "PML": {"price": 90.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "YL": {"price": 86.0, "status": "ACTIVE", "stack_group": "NONE"},
                },
            }
            bars: list[dict] = []
            snapshots = [
                {
                    "symbol": "NQ",
                    "normalized_symbol": "NQ",
                    "latest_price": 100.0,
                    "latest_bar_time": "2026-07-02T13:30:00Z",
                    "ohlc_is_closed": True,
                    "ohlc": {"open": 100.0, "high": 101.5, "low": 99.75, "close": 100.0},
                },
                {
                    "symbol": "NQ",
                    "normalized_symbol": "NQ",
                    "latest_price": 103.9,
                    "latest_bar_time": "2026-07-02T13:31:00Z",
                    "ohlc_is_closed": True,
                    "ohlc": {"open": 100.0, "high": 104.0, "low": 99.75, "close": 101.0},
                },
            ]
            index = {"value": 0}

            def market_snapshot(_symbol: str = "NQ") -> dict:
                return dict(snapshots[index["value"]])

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol="NQ", limit=120: list(bars)[-limit:]
            entry_agent.load_rithmic_atr_snapshot = lambda _symbol="NQ": {"atr_1m_14": 10.0}

            first = entry_agent.run_once("NQ", persist=True)
            bars.append({"timestamp": first["latest_bar_time"], **first["ohlc"]})
            index["value"] = 1
            second = entry_agent.run_once("NQ", persist=True)

            assert first["step_2_1a"]["active_level"] == "ONH"
            assert second["step_2_1a"]["step_2_activated"] is False
            assert second["step_2_1a"]["active_level"] == "ONH"
            assert second["step_2_1a"]["level_price"] == 101.0
            assert second["step_2_1a"]["pending_step2_owner"]["active_liquidity_name"] == "ONH"
            assert second["step_2_1a"]["last_interacted_liquidity"]["name"] == "ONH"
    finally:
        entry_agent.STATE_PATH = original_state_path
        entry_agent.get_latest_market_snapshot = original_get_latest
        entry_agent.load_tv_context = original_load_tv
        entry_agent.recent_closed_bars = original_recent
        entry_agent.load_rithmic_atr_snapshot = original_load_atr
        entry_agent.append_entry_agent_audit_row = original_append_audit


def _nq_20260630_confirmed_rejection_symbol_state() -> dict:
    return {
        "step_2_1a": {
            "step_2_activated": True,
            "active_level": "PMH",
            "level_price": 30217.0,
            "side": "upper",
            "available": True,
            "reason": "Step 2 already locked for this liquidity/pathway; preserving original activation owner.",
            "state_transition_reason": "Step 2 already locked for this liquidity/pathway; preserving original activation owner.",
            "step2_activated_at": "2026-06-30T13:35:00Z",
            "step2_owner_seeded_at": "2026-06-30T13:35:00Z",
            "last_evaluated_bar_time": "2026-06-30T13:36:00Z",
            "active_liquidity_group": {
                "name": "HIGH 1",
                "display_name": "PMH/LH/ONH",
                "components": ["PMH", "LH", "ONH"],
                "side": "upper",
                "close_boundary": 30142.75,
                "extreme_boundary": 30217.0,
                "wick_boundary_extreme": 30251.0,
                "stack_extreme": 30217.0,
            },
            "last_interacted_liquidity": {
                "name": "PMH",
                "price": 30217.0,
                "display_name": "PMH/LH/ONH",
                "side": "upper",
                "group": {
                    "name": "HIGH 1",
                    "display_name": "PMH/LH/ONH",
                    "components": ["PMH", "LH", "ONH"],
                    "side": "upper",
                    "close_boundary": 30142.75,
                    "extreme_boundary": 30217.0,
                    "wick_boundary_extreme": 30251.0,
                    "stack_extreme": 30217.0,
                },
            },
            "step2_locked_owner": {
                "pathway": "rejection",
                "activated_at": "2026-06-30T13:35:00Z",
                "setup_direction": "SHORT",
                "side": "upper",
                "active_liquidity_name": "PMH/LH/ONH",
                "active_liquidity_price": 30217.0,
                "close_boundary": 30142.75,
                "extreme_boundary": 30217.0,
                "wick_boundary_extreme": 30251.0,
                "active_liquidity": {
                    "name": "PMH",
                    "price": 30217.0,
                    "display_name": "PMH/LH/ONH",
                },
                "active_liquidity_group": {
                    "name": "HIGH 1",
                    "display_name": "PMH/LH/ONH",
                    "components": ["PMH", "LH", "ONH"],
                    "side": "upper",
                    "close_boundary": 30142.75,
                    "extreme_boundary": 30217.0,
                    "wick_boundary_extreme": 30251.0,
                    "stack_extreme": 30217.0,
                },
            },
        },
        "step25": {
            "status": "READY",
            "next_step": "Step 3",
            "state": {
                "step25_pathway_selection_complete": True,
                "controlling_mode": "Normal Rejection Mode",
                "setup_direction": "SHORT",
                "active_liquidity": {"name": "PMH", "price": 30217.0, "display_name": "PMH/LH/ONH"},
            },
        },
        "step3": {
            "status": "ALLOW_STEP_4",
            "next_step": "Step 4",
            "state": {
                "setup_direction": "SHORT",
            },
        },
        "step4": {
            "step": "Step 4",
            "status": "READY",
            "next_step": "Step 5",
            "reason": "Leg 1 complete: Candle B satisfied Candle A participation; Anchor Extreme assigned; proximity distance > 10% daily ATR.",
            "state": {
                "setup_direction": "SHORT",
                "controlling_mode": "Normal Rejection Mode",
                "active_liquidity": {"name": "PMH", "price": 30217.0, "display_name": "PMH/LH/ONH", "side": "upper"},
                "leg1_status": "COMPLETE",
                "leg1_state_locked": True,
                "leg1_completed_at": "2026-06-30T13:36:00Z",
                "leg1_reference": 30247.5,
                "leg1_reference_price": 30247.5,
                "leg1_reference_candle_time": "2026-06-30T13:36:00Z",
                "leg1_direction": "SHORT",
                "candle_a": {
                    "timestamp": "2026-06-30T13:35:00Z",
                    "open": 30180.25,
                    "high": 30251.0,
                    "low": 30156.75,
                    "close": 30247.5,
                },
                "candle_b": {
                    "timestamp": "2026-06-30T13:36:00Z",
                    "open": 30248.25,
                    "high": 30253.75,
                    "low": 30212.0,
                    "close": 30215.5,
                },
                "leg1_window_started_at": "2026-06-30T13:35:00Z",
                "leg1_window_candle_index": 1,
                "leg1_window_remaining": 3,
                "leg1_window_active": True,
                "leg1_window_expires_at": "2026-06-30T13:39:00Z",
            },
        },
        "step5": {
            "step": "Step 5",
            "status": "WAIT",
            "next_step": "Step 5",
            "reason": "Step 5 waiting for a separate future Leg 2 candle after locked Leg 1.",
            "state": {
                "setup_direction": "SHORT",
                "leg1_status": "COMPLETE",
                "leg1_state_locked": True,
                "leg1_completed_at": "2026-06-30T13:36:00Z",
                "active_liquidity": {"name": "PMH", "price": 30217.0, "display_name": "PMH/LH/ONH", "side": "upper"},
            },
        },
        "rejection_lane": {
            "lane_name": "rejection",
            "lane_status": "frozen",
            "pathway_status": "frozen",
            "active_liquidity_name": "PMH/LH/ONH",
            "liquidity_group": "HIGH 1",
            "active_liquidity_price": 30217.0,
            "close_boundary": 30142.75,
            "extreme_boundary": 30217.0,
            "wick_boundary_extreme": 30251.0,
            "step2_candle_count": None,
            "step4_candle_count": 1,
            "step2_status": "CONFIRMED",
            "step25_status": "READY",
            "step4_status": "CONFIRMED",
            "step2_step4_50_line": None,
            "step4_step5_75_line": None,
            "invalidation_reason": None,
        },
    }


def _nq_20260630_0637_refresh_snapshot() -> dict:
    return {
        "symbol": "NQ",
        "normalized_symbol": "NQ",
        "requested_symbol": "NQ",
        "latest_price": 30258.75,
        "latest_bar_time": "2026-06-30T13:37:00Z",
        "ohlc_is_closed": True,
        "ohlc": {
            "open": 30215.0,
            "high": 30264.0,
            "low": 30210.0,
            "close": 30258.75,
        },
        "tv_context": {
            "levels": {
                "PMH": {"price": 30217.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "LH": {"price": 30190.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "ONH": {"price": 30217.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "PML": {"price": 30000.0, "status": "ACTIVE", "stack_group": "LOW 1"},
            }
        },
        "liquidity": {"tick_size": 0.25},
        "rejection": {"rejection_mode": "ON", "watch_side": "SHORT"},
    }


def _nq_20260630_0635_seeded_symbol_state() -> dict:
    state = _nq_20260630_confirmed_rejection_symbol_state()
    state["step_2_1a"]["last_evaluated_bar_time"] = "2026-06-30T13:35:00Z"
    state["step25"] = {
        "status": "READY",
        "next_step": "Step 3",
        "reason": "Normal Rejection Mode selected.",
        "state": {
            "step25_pathway_selection_complete": True,
            "controlling_mode": "Normal Rejection Mode",
            "candidate_modes": ["Normal Rejection Mode"],
            "setup_direction": "SHORT",
            "initial_candle_a": {
                "timestamp": "2026-06-30T13:35:00Z",
                "open": 30180.25,
                "high": 30251.0,
                "low": 30156.75,
                "close": 30247.5,
            },
            "active_liquidity": {"name": "PMH", "price": 30217.0, "display_name": "PMH/LH/ONH"},
            "active_liquidity_name": "PMH",
            "active_liquidity_price": 30217.0,
        },
        "events": [],
    }
    state["step3"] = {
        "status": "ALLOW_STEP_4",
        "next_step": "Step 4",
        "reason": "Step 3 permits Leg 1 formation.",
        "state": {
            "setup_direction": "SHORT",
            "controlling_mode": "Normal Rejection Mode",
            "active_liquidity": {"name": "PMH", "price": 30217.0, "display_name": "PMH/LH/ONH", "side": "upper"},
        },
        "events": [],
    }
    state["step4"] = {
        "step": "Step 4",
        "status": "WAIT",
        "next_step": "Step 4",
        "reason": "Step 4 seeded: Candle A / index 0 is the 06:35 PT Step 2 confirmation candle. Waiting for a future Candle B.",
        "state": {
            "setup_direction": "SHORT",
            "controlling_mode": "Normal Rejection Mode",
            "active_liquidity": {"name": "PMH", "price": 30217.0, "display_name": "PMH/LH/ONH", "side": "upper"},
            "initial_candle_a": {
                "timestamp": "2026-06-30T13:35:00Z",
                "open": 30180.25,
                "high": 30251.0,
                "low": 30156.75,
                "close": 30247.5,
            },
            "candle_a": {
                "timestamp": "2026-06-30T13:35:00Z",
                "open": 30180.25,
                "high": 30251.0,
                "low": 30156.75,
                "close": 30247.5,
            },
            "leg1_status": "WAIT",
            "leg1_state_locked": False,
            "leg1_window_active": True,
            "leg1_window_started_at": "2026-06-30T13:35:00Z",
            "leg1_window_candle_index": 0,
            "leg1_window_remaining": 4,
            "leg1_window_expires_at": "2026-06-30T13:39:00Z",
        },
        "events": [],
    }
    state["step5"] = {}
    state["rejection_lane"] = {
        "lane_name": "rejection",
        "lane_status": "controlling",
        "pathway_status": "controlling",
        "active_liquidity_name": "PMH/LH/ONH",
        "liquidity_group": "HIGH 1",
        "active_liquidity_price": 30217.0,
        "close_boundary": 30142.75,
        "extreme_boundary": 30217.0,
        "wick_boundary_extreme": 30251.0,
        "step2_candle_count": 0,
        "step4_candle_count": 0,
        "step2_status": "CONFIRMED",
        "step25_status": "READY",
        "step4_status": "WAIT",
        "step2_step4_50_line": None,
        "step4_step5_75_line": None,
        "invalidation_reason": None,
    }
    return state


def _nq_20260630_0636_snapshot() -> dict:
    return {
        "symbol": "NQ",
        "normalized_symbol": "NQ",
        "requested_symbol": "NQ",
        "latest_price": 30215.5,
        "latest_bar_time": "2026-06-30T13:36:00Z",
        "ohlc_is_closed": True,
        "ohlc": {
            "open": 30248.25,
            "high": 30253.75,
            "low": 30212.0,
            "close": 30215.5,
        },
        "tv_context": {
            "levels": {
                "PMH": {"price": 30217.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "LH": {"price": 30142.75, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "ONH": {"price": 30217.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "PML": {"price": 30000.0, "status": "ACTIVE", "stack_group": "LOW 1"},
            }
        },
        "liquidity": {"tick_size": 0.25},
    }


def test_nq_20260630_same_candle_rejection_step4_blocks_continuation_step2_and_seeds_boundary() -> None:
    import copy
    import entry_agent

    original_recent = entry_agent.recent_closed_bars
    try:
        prior_state = _nq_20260630_0635_seeded_symbol_state()
        rejection = {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 30217.0}
        step2 = copy.deepcopy(prior_state["step_2_1a"])
        step3 = copy.deepcopy(prior_state["step3"])
        snapshot_0636 = _nq_20260630_0636_snapshot()
        candle_0635 = {
            "timestamp": "2026-06-30T13:35:00Z",
            "open": 30180.25,
            "high": 30251.0,
            "low": 30156.75,
            "close": 30247.5,
        }
        candle_0636 = {
            "timestamp": "2026-06-30T13:36:00Z",
            "open": 30248.25,
            "high": 30253.75,
            "low": 30212.0,
            "close": 30215.5,
        }

        entry_agent.recent_closed_bars = lambda _symbol="NQ", limit=120: [candle_0635][-limit:]

        step25_0636 = entry_agent.evaluate_live_step25(snapshot_0636, rejection, step2, prior_state)
        assert step25_0636["state"].get("continuation_step2_activated") is not True
        assert step25_0636["state"].get("reclaim_candle_a") is None
        assert "same candle" in str(step25_0636["state"].get("step25_block_reason") or "").lower()

        persisted_same_candle = copy.deepcopy(prior_state)
        persisted_same_candle["step25"] = step25_0636
        persisted_same_candle["step4"] = copy.deepcopy(_nq_20260630_confirmed_rejection_symbol_state()["step4"])
        entry_agent.recent_closed_bars = lambda _symbol="NQ", limit=120: [candle_0635, candle_0636][-limit:]

        same_candle_refresh = entry_agent.evaluate_live_step25(snapshot_0636, rejection, step2, persisted_same_candle)
        assert same_candle_refresh["state"].get("continuation_step2_activated") is not True
        assert same_candle_refresh["state"].get("current_boundary") == 30212.0
        assert same_candle_refresh["state"].get("continuation_probe_boundary", {}).get("boundary_price") == 30212.0
        assert same_candle_refresh["state"].get("continuation_seeded_from_rejection_step4") is True

        continuation_snapshot = {
            **snapshot_0636,
            "latest_price": 30210.0,
            "latest_bar_time": "2026-06-30T13:37:00Z",
            "ohlc": {
                "open": 30214.5,
                "high": 30215.0,
                "low": 30205.0,
                "close": 30210.0,
            },
        }
        later_step2 = copy.deepcopy(step2)
        later_step2["last_evaluated_bar_time"] = "2026-06-30T13:37:00Z"
        persisted_same_candle["step25"] = same_candle_refresh
        later_step25 = entry_agent.evaluate_live_step25(continuation_snapshot, rejection, later_step2, persisted_same_candle)
        assert later_step25["state"].get("current_boundary") == 30212.0
        assert later_step25["state"].get("continuation_step2_activated") is True
        assert later_step25["status"] == "READY"
        assert later_step25["state"].get("controlling_mode") == "R/S"
        assert later_step25["state"].get("reclaim_candle_a", {}).get("timestamp") == "2026-06-30T13:37:00Z"

        published_snapshot = copy.deepcopy(continuation_snapshot)
        published_snapshot["rejection"] = rejection
        published_snapshot["step_2_1a"] = later_step2
        published_snapshot["step25"] = later_step25
        published_snapshot["step3"] = step3
        published_snapshot["step4"] = copy.deepcopy(_nq_20260630_confirmed_rejection_symbol_state()["step4"])
        published_snapshot["step5"] = copy.deepcopy(_nq_20260630_confirmed_rejection_symbol_state()["step5"])
        published_snapshot["step6"] = entry_agent.no_active_liquidity_result("Step 6", "Step 5 waiting for a separate future Leg 2 candle after locked Leg 1.")
        rejection_lane, continuation_lane = entry_agent.snapshot_lane_statuses(published_snapshot, persisted_same_candle)
        published_snapshot["rejection_lane"] = rejection_lane
        published_snapshot["continuation_lane"] = continuation_lane

        with patch.object(entry_agent, "get_latest_market_snapshot", return_value=published_snapshot), \
             patch.object(entry_agent, "load_entry_state", return_value={"symbols": {"NQ": persisted_same_candle}}), \
             patch.object(entry_agent, "run_once", return_value=published_snapshot):
            status = entry_agent.build_entry_status("NQ")

        assert status["continuation_eligible"] is False
        assert status["continuation_lane"]["step2_status"] == "CONFIRMED"
        assert status["continuation_lane"]["step2_confirmed_at"] == "2026-06-30T13:37:00Z"
        assert status["continuation_lane"]["step2_confirmed_at"] != "2026-06-30T13:36:00Z"
    finally:
        entry_agent.recent_closed_bars = original_recent


def test_nq_20260630_step4_restart_reconstructs_candle_a_and_accepts_0636_candle_b() -> None:
    import copy
    import entry_agent

    original_recent = entry_agent.recent_closed_bars
    try:
        prior_state = _nq_20260630_0635_seeded_symbol_state()
        rejection = {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 30217.0}
        step2 = copy.deepcopy(prior_state["step_2_1a"])
        snapshot_0636 = _nq_20260630_0636_snapshot()
        candle_0635 = {
            "timestamp": "2026-06-30T13:35:00Z",
            "open": 30180.25,
            "high": 30251.0,
            "low": 30156.75,
            "close": 30247.5,
        }
        candle_0636 = {
            "timestamp": "2026-06-30T13:36:00Z",
            "open": 30248.25,
            "high": 30253.75,
            "low": 30212.0,
            "close": 30215.5,
        }

        restarted_state = copy.deepcopy(prior_state)
        restarted_state["step4"] = copy.deepcopy(prior_state["step4"])
        restarted_state["step4"]["state"].pop("stack_step4_candle_a_assigned", None)
        restarted_state["step4"]["state"].pop("candle_a", None)

        entry_agent.recent_closed_bars = lambda _symbol="NQ", limit=120: [candle_0635, candle_0636][-limit:]
        step25 = entry_agent.evaluate_live_step25(snapshot_0636, rejection, step2, restarted_state)
        step3 = entry_agent.evaluate_live_step3(snapshot_0636, rejection, step25, step2, restarted_state)
        interaction_0636 = entry_agent.build_step4_interaction(snapshot_0636, rejection, step25, step3, restarted_state)
        step4_0636 = entry_agent.evaluate_live_step4(snapshot_0636, rejection, step25, step3, restarted_state)

        assert interaction_0636 is not None
        assert interaction_0636.get("candle_a", {}).get("timestamp") == "2026-06-30T13:35:00Z"
        assert interaction_0636.get("candle_b", {}).get("timestamp") == "2026-06-30T13:36:00Z"
        assert interaction_0636.get("latest_candle", {}).get("timestamp") == "2026-06-30T13:36:00Z"
        assert step4_0636["reason"] != "Step 4 waiting: final Candle A assignment and Candle B are required."
        assert not any(
            isinstance(event, dict) and event.get("event") == "step4_waiting_for_candles"
            for event in (step4_0636.get("events") or [])
        )
    finally:
        entry_agent.recent_closed_bars = original_recent


def test_nq_20260630_rejection_context_persists_across_0637_refresh_resets() -> None:
    import entry_agent

    previous_symbol_state = _nq_20260630_confirmed_rejection_symbol_state()
    reset_variants = [
        {
            "label": "no_active_liquidity_selected",
            "step_2_1a": {
                "step_2_activated": False,
                "available": False,
                "reason": "No active liquidity selected.",
                "state_transition_reason": "No active liquidity selected.",
                "active_level": None,
                "level_price": None,
                "active_liquidity_group": None,
                "last_interacted_liquidity": None,
            },
            "step25": entry_agent.no_active_liquidity_result("Step 2.5", "No active liquidity selected."),
            "step3": entry_agent.no_active_liquidity_result("Step 3", "No active liquidity selected."),
            "step4": entry_agent.no_active_liquidity_result("Step 4", "No active liquidity selected."),
            "step5": entry_agent.no_active_liquidity_result("Step 5", "No active liquidity selected."),
        },
        {
            "label": "full_step2_reset",
            "step_2_1a": {
                "step_2_activated": False,
                "available": True,
                "reason": "Step 2 waiting for a valid liquidity-close activation.",
                "state_transition_reason": "Step 2 waiting for a valid liquidity-close activation.",
                "active_level": None,
                "level_price": None,
                "active_liquidity_group": None,
                "last_interacted_liquidity": None,
            },
            "step25": entry_agent.no_active_liquidity_result("Step 2.5", "Step 2 waiting for a valid liquidity-close activation."),
            "step3": entry_agent.no_active_liquidity_result("Step 3", "Step 2 waiting for a valid liquidity-close activation."),
            "step4": entry_agent.no_active_liquidity_result("Step 4", "Step 2 waiting for a valid liquidity-close activation."),
            "step5": entry_agent.no_active_liquidity_result("Step 5", "Step 2 waiting for a valid liquidity-close activation."),
        },
    ]

    for variant in reset_variants:
        snapshot = _nq_20260630_0637_refresh_snapshot()
        snapshot.update(
            {
                "step_2_1a": variant["step_2_1a"],
                "step25": variant["step25"],
                "step3": variant["step3"],
                "step4": variant["step4"],
                "step5": variant["step5"],
                "step6": entry_agent.no_active_liquidity_result("Step 6", "No active liquidity selected."),
            }
        )

        restored = entry_agent.restore_rejection_context_without_active_liquidity(snapshot, previous_symbol_state)

        assert restored is True, variant["label"]
        assert snapshot["step_2_1a"]["step_2_activated"] is True, variant["label"]
        assert snapshot["step_2_1a"].get("reason") != "No active liquidity selected.", variant["label"]
        assert snapshot["step4"]["status"] == "READY", variant["label"]
        assert snapshot["step4"]["state"].get("leg1_status") == "COMPLETE", variant["label"]

        rejection_lane, continuation_lane = entry_agent.snapshot_lane_statuses(snapshot, previous_symbol_state)

        assert rejection_lane["lane_status"] in {"controlling", "frozen"}, variant["label"]
        assert rejection_lane["step2_status"] == "CONFIRMED", variant["label"]
        assert rejection_lane["step4_status"] in {"READY", "CONFIRMED"}, variant["label"]
        assert rejection_lane["active_liquidity_name"] == "PMH/LH/ONH", variant["label"]
        assert rejection_lane["close_boundary"] == 30142.75, variant["label"]
        assert rejection_lane["extreme_boundary"] == 30217.0, variant["label"]
        assert rejection_lane["step4_candle_count"] == 1, variant["label"]
        assert rejection_lane["invalidation_reason"] is None, variant["label"]
        assert continuation_lane["lane_status"] in {"idle", "eligible", "controlling"}, variant["label"]


def test_authoritative_rejection_anchor_commit_preserves_20260707_nq_0634_anchor_into_0635() -> None:
    import entry_agent

    original_state_path = entry_agent.STATE_PATH
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry_agent.STATE_PATH = Path(temp_dir) / "entry_agent_state.json"
            active_group = {
                "name": "LOW 1",
                "display_name": "PML/LL/ONL Liquidity",
                "side": "lower",
                "components": ["ONL", "LL", "PML"],
                "prices": {"ONL": 29558.5, "LL": 29591.25, "PML": 29610.5},
                "liquidity_level_name": "PML/LL/ONL",
                "liquidity_level_price": 29558.5,
                "close_boundary": 29558.5,
                "extreme_boundary": 29558.5,
            }
            stale_pending_state = {
                "normalized_symbol": "NQ",
                "requested_symbol": "NQ",
                "step_2_1a": {
                    "step_2_activated": False,
                    "active_level": "PML/LL/ONL",
                    "level_price": 29558.5,
                    "side": "lower",
                    "tick_size": 0.25,
                    "expiration_candles": 5,
                    "pre_activation_probe_boundary": {
                        "active": True,
                        "side": "lower",
                        "source_level": "PML/LL/ONL",
                        "boundary_price": 29552.0,
                        "detected_at_index": 0,
                    },
                    "last_evaluated_bar_time": "2026-07-07T13:33:00Z",
                    "next_candle_index": 1,
                    "active_liquidity_group": dict(active_group),
                    "last_interacted_liquidity": {
                        "name": "PML/LL/ONL",
                        "price": 29558.5,
                        "display_name": "PML/LL/ONL",
                        "side": "lower",
                        "group": dict(active_group),
                    },
                },
                "step_2_1a_last_evaluated_bar_time": "2026-07-07T13:33:00Z",
                "last_interacted_liquidity": {
                    "name": "PML/LL/ONL",
                    "price": 29558.5,
                    "display_name": "PML/LL/ONL",
                    "side": "lower",
                    "group": dict(active_group),
                },
                "last_interacted_liquidity_by_symbol": {
                    "NQ": {
                        "name": "PML/LL/ONL",
                        "price": 29558.5,
                        "display_name": "PML/LL/ONL",
                        "side": "lower",
                        "group": dict(active_group),
                    }
                },
                "state_by_symbol": {},
            }
            stale_pending_state["state_by_symbol"]["NQ"] = copy.deepcopy(stale_pending_state)
            entry_agent.STATE_PATH.write_text(json.dumps(stale_pending_state, indent=2) + "\n", encoding="utf-8")

            candle_0634 = {
                "timestamp": "2026-07-07T13:34:00Z",
                "open": 29562.5,
                "high": 29569.75,
                "low": 29515.25,
                "close": 29526.75,
            }
            snapshot_0634 = {
                "symbol": "NQU6",
                "normalized_symbol": "NQ",
                "requested_symbol": "NQ",
                "latest_price": 29526.75,
                "latest_bar_time": "2026-07-07T13:34:00Z",
                "step_2_1a": {
                    "step_2_activated": True,
                    "candle_a": dict(candle_0634),
                    "active_level": "PML/LL/ONL",
                    "level_price": 29558.5,
                    "side": "lower",
                    "tick_size": 0.25,
                    "expiration_candles": 5,
                    "step2_owner_seeded_at": "2026-07-07T13:34:00Z",
                    "step2_activated_at": "2026-07-07T13:34:00Z",
                    "step2_activation_candle_index": 0,
                    "active_liquidity_group": dict(active_group),
                    "last_interacted_liquidity": {
                        "name": "PML/LL/ONL",
                        "price": 29558.5,
                        "display_name": "PML/LL/ONL",
                        "side": "lower",
                        "group": dict(active_group),
                    },
                    "step2_locked_owner": {
                        "pathway": "rejection",
                        "active_liquidity": {
                            "name": "PML/LL/ONL",
                            "price": 29558.5,
                            "display_name": "PML/LL/ONL",
                            "side": "lower",
                            "group": dict(active_group),
                        },
                        "active_liquidity_name": "PML/LL/ONL",
                        "active_liquidity_price": 29558.5,
                        "active_liquidity_display_name": "PML/LL/ONL",
                        "active_liquidity_group": dict(active_group),
                        "liquidity_group": "LOW 1",
                        "close_boundary": 29558.5,
                        "extreme_boundary": 29558.5,
                        "wick_boundary_extreme": None,
                        "setup_direction": "LONG",
                        "side": "lower",
                        "candle_a": dict(candle_0634),
                        "owner_seeded_at": "2026-07-07T13:34:00Z",
                        "activated_at": "2026-07-07T13:34:00Z",
                        "step2_activation_candle_index": 0,
                    },
                    "last_evaluated_bar_time": "2026-07-07T13:34:00Z",
                    "candle_index": 1,
                    "next_candle_index": 2,
                    "reason": "Step 2.1A evaluated from live completed candle.",
                    "available": True,
                },
                "step4": {
                    "step": "Step 4",
                    "status": "WAIT",
                    "next_step": "Step 4",
                    "reason": "Step 4 seeded: the participation window is anchored at the 06:34 PT Step 2 confirmation candle. Waiting for a qualifying participation candle.",
                    "state": {
                        "leg1_window_active": True,
                        "leg1_window_started_at": "2026-07-07T13:34:00Z",
                        "leg1_window_candle_index": 0,
                        "leg1_window_remaining": 4,
                        "leg1_window_expires_at": "2026-07-07T13:38:00Z",
                        "leg1_window_invalidated": False,
                        "leg1_window_invalidation_reason": None,
                        "leg1_status": "WAIT",
                        "leg1_state_locked": False,
                        "active_liquidity": {
                            "name": "PML/LL/ONL",
                            "price": 29558.5,
                            "display_name": "PML/LL/ONL",
                            "side": "lower",
                            "group": dict(active_group),
                        },
                        "initial_candle_a": dict(candle_0634),
                        "candle_a": dict(candle_0634),
                        "setup_direction": "LONG",
                        "current_pathway_control": "rejection",
                        "current_controlling_mode": "Normal Rejection Mode",
                    },
                },
                "rejection_lane": {
                    "lane_name": "rejection",
                    "lane_status": "controlling",
                    "pathway_status": "controlling",
                    "active_liquidity_name": "PML/LL/ONL",
                    "active_liquidity_group": dict(active_group),
                    "liquidity_group": "LOW 1",
                    "active_liquidity_price": 29558.5,
                    "close_boundary": 29558.5,
                    "extreme_boundary": 29558.5,
                    "wick_boundary_extreme": None,
                    "step2_candle_count": 0,
                    "step4_candle_count": 0,
                    "step2_status": "CONFIRMED",
                    "step2_confirmed_at": "2026-07-07T13:34:00Z",
                    "step4_status": "WAIT",
                    "step2_reason": "Step 2.1A evaluated from live completed candle.",
                    "step4_reason": "Step 4 seeded: the participation window is anchored at the 06:34 PT Step 2 confirmation candle. Waiting for a qualifying participation candle.",
                    "invalidation_reason": None,
                },
            }
            status_0634 = {
                "step2_status": "CONFIRMED",
                "step2_confirmed_at": "2026-07-07T13:34:00Z",
                "rejection_lane": {
                    "step2_status": "CONFIRMED",
                    "step2_confirmed_at": "2026-07-07T13:34:00Z",
                },
            }

            assert entry_agent.persist_confirmed_rejection_anchor_from_authoritative_snapshot(snapshot_0634, status_0634) is True

            persisted = entry_agent.load_entry_state()
            persisted_symbol_state = persisted.get("state_by_symbol", {}).get("NQ", persisted)
            assert persisted_symbol_state["step_2_1a"]["step2_activated_at"] == "2026-07-07T13:34:00Z"
            assert persisted_symbol_state["step4"]["state"]["leg1_window_started_at"] == "2026-07-07T13:34:00Z"
            assert persisted_symbol_state["rejection_lane"]["step2_confirmed_at"] == "2026-07-07T13:34:00Z"

            snapshot_0635 = {
                "latest_bar_time": "2026-07-07T13:35:00Z",
            }
            projected_step4 = entry_agent.projected_pending_rejection_step4_state(
                snapshot_0635,
                persisted_symbol_state,
                rejection_group=dict(active_group),
                rejection_active_price=29558.5,
            )
            assert projected_step4 is not None
            assert projected_step4["leg1_window_started_at"] == "2026-07-07T13:34:00Z"
            assert projected_step4["leg1_window_candle_index"] == 1
            assert projected_step4["leg1_window_remaining"] == 3

            carried_lane = entry_agent.carry_forward_pending_rejection_lane(
                snapshot_0635,
                persisted_symbol_state,
                rejection_group=dict(active_group),
                rejection_active_price=29558.5,
            )
            assert carried_lane is not None
            assert carried_lane["step2_confirmed_at"] == "2026-07-07T13:34:00Z"
            assert carried_lane["step4_candle_count"] == 1
            assert carried_lane["step2_candle_count"] == 1
    finally:
        entry_agent.STATE_PATH = original_state_path


def test_nq_20260630_build_entry_status_blocks_same_candle_continuation_publish() -> None:
    import copy
    from unittest.mock import patch

    import entry_agent

    original_recent = entry_agent.recent_closed_bars
    try:
        prior_state = _nq_20260630_0635_seeded_symbol_state()
        confirmed_state = _nq_20260630_confirmed_rejection_symbol_state()
        rejection = {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 30217.0}
        step2 = copy.deepcopy(prior_state["step_2_1a"])
        snapshot_0636 = _nq_20260630_0636_snapshot()
        candle_0635 = {
            "timestamp": "2026-06-30T13:35:00Z",
            "open": 30180.25,
            "high": 30251.0,
            "low": 30156.75,
            "close": 30247.5,
        }
        candle_0636 = {
            "timestamp": "2026-06-30T13:36:00Z",
            "open": 30248.25,
            "high": 30253.75,
            "low": 30212.0,
            "close": 30215.5,
        }

        entry_agent.recent_closed_bars = lambda _symbol="NQ", limit=120: [candle_0635, candle_0636][-limit:]
        persisted_same_candle = copy.deepcopy(prior_state)
        persisted_same_candle["step4"] = copy.deepcopy(confirmed_state["step4"])
        same_candle_step25 = entry_agent.evaluate_live_step25(snapshot_0636, rejection, step2, persisted_same_candle)

        publish_snapshot = copy.deepcopy(snapshot_0636)
        publish_snapshot["step_2_1a"] = step2
        publish_snapshot["rejection"] = rejection
        publish_snapshot["step25"] = same_candle_step25
        publish_snapshot["step3"] = copy.deepcopy(prior_state["step3"])
        publish_snapshot["step4"] = copy.deepcopy(confirmed_state["step4"])
        publish_snapshot["step5"] = copy.deepcopy(confirmed_state["step5"])
        publish_snapshot["step6"] = entry_agent.no_active_liquidity_result("Step 6", "Step 5 waiting for a separate future Leg 2 candle after locked Leg 1.")
        rejection_lane, continuation_lane = entry_agent.snapshot_lane_statuses(publish_snapshot, prior_state)
        publish_snapshot["rejection_lane"] = rejection_lane
        publish_snapshot["continuation_lane"] = continuation_lane

        persisted_state = {"symbols": {"NQ": prior_state}}
        with patch.object(entry_agent, "get_latest_market_snapshot", return_value=publish_snapshot), \
             patch.object(entry_agent, "load_entry_state", return_value=persisted_state), \
             patch.object(entry_agent, "run_once", return_value=publish_snapshot):
            status = entry_agent.build_entry_status("NQ")

        assert status["selected_pathway"] == "rejection"
        assert status["continuation_eligible"] is True
        assert status["continuation_lane"]["lane_status"] == "eligible"
        assert status["continuation_lane"]["step2_status"] == "WAIT"
        assert status["continuation_lane"]["wick_boundary_extreme"] == 30212.0
        assert status["wait_reason"] != "No active liquidity selected."
        assert status["active_liquidity_name"] == "PMH/LH/ONH"
    finally:
        entry_agent.recent_closed_bars = original_recent


def test_nq_20260630_snapshot_lane_statuses_seed_and_preserve_continuation_boundary_from_step4() -> None:
    import copy
    import entry_agent

    prior_state = _nq_20260630_0635_seeded_symbol_state()
    confirmed_state = _nq_20260630_confirmed_rejection_symbol_state()

    same_candle_snapshot = _nq_20260630_0636_snapshot()
    same_candle_snapshot["step_2_1a"] = copy.deepcopy(prior_state["step_2_1a"])
    same_candle_snapshot["rejection"] = {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 30217.0}
    same_candle_snapshot["step25"] = copy.deepcopy(prior_state["step25"])
    same_candle_snapshot["step3"] = copy.deepcopy(prior_state["step3"])
    same_candle_snapshot["step4"] = copy.deepcopy(confirmed_state["step4"])
    same_candle_snapshot["step5"] = copy.deepcopy(confirmed_state["step5"])
    same_candle_snapshot["step6"] = entry_agent.no_active_liquidity_result("Step 6", "Step 5 waiting for a separate future Leg 2 candle after locked Leg 1.")

    rejection_lane, continuation_lane = entry_agent.snapshot_lane_statuses(same_candle_snapshot, prior_state)
    assert rejection_lane["step4_status"] in {"READY", "CONFIRMED"}
    assert continuation_lane["lane_status"] == "eligible"
    assert continuation_lane["step2_status"] == "WAIT"
    assert continuation_lane["wick_boundary_extreme"] == 30212.0

    persisted_after_0636 = copy.deepcopy(confirmed_state)
    persisted_after_0636["continuation_lane"] = copy.deepcopy(continuation_lane)
    persisted_after_0636["step25"] = copy.deepcopy(same_candle_snapshot["step25"])

    reset_snapshot = _nq_20260630_0637_refresh_snapshot()
    reset_snapshot.update(
        {
            "step_2_1a": {
                "step_2_activated": False,
                "available": False,
                "reason": "No active liquidity selected.",
                "state_transition_reason": "No active liquidity selected.",
                "active_level": None,
                "level_price": None,
                "active_liquidity_group": None,
                "last_interacted_liquidity": None,
            },
            "rejection": {"rejection_mode": "OFF", "reason_text": "No active liquidity selected."},
            "step25": entry_agent.no_active_liquidity_result("Step 2.5", "No active liquidity selected."),
            "step3": entry_agent.no_active_liquidity_result("Step 3", "No active liquidity selected."),
            "step4": entry_agent.no_active_liquidity_result("Step 4", "No active liquidity selected."),
            "step5": entry_agent.no_active_liquidity_result("Step 5", "No active liquidity selected."),
            "step6": entry_agent.no_active_liquidity_result("Step 6", "No active liquidity selected."),
        }
    )
    assert entry_agent.restore_rejection_context_without_active_liquidity(reset_snapshot, persisted_after_0636) is True
    rejection_lane_0637, continuation_lane_0637 = entry_agent.snapshot_lane_statuses(reset_snapshot, persisted_after_0636)
    assert continuation_lane_0637["wick_boundary_extreme"] == 30212.0


def test_lower_side_rejection_step4_seeds_continuation_boundary_from_candle_b_high() -> None:
    import entry_agent

    step4 = {
        "status": "READY",
        "state": {
            "leg1_state_locked": True,
            "leg1_status": "COMPLETE",
            "candle_b": {
                "timestamp": "2026-06-30T13:36:00Z",
                "open": 100.0,
                "high": 101.75,
                "low": 99.5,
                "close": 100.25,
            },
        },
    }

    boundary = entry_agent.continuation_seed_boundary_from_rejection_step4(step4, previous_symbol_state=None, side="lower")
    assert boundary == 101.75


def test_nq_20260630_build_entry_status_preserves_seeded_context_after_0637_reset() -> None:
    import copy
    from unittest.mock import patch

    import entry_agent

    original_recent = entry_agent.recent_closed_bars
    try:
        prior_state = _nq_20260630_0635_seeded_symbol_state()
        confirmed_state = _nq_20260630_confirmed_rejection_symbol_state()
        rejection = {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 30217.0}
        step2 = copy.deepcopy(prior_state["step_2_1a"])
        snapshot_0636 = _nq_20260630_0636_snapshot()
        candle_0635 = {
            "timestamp": "2026-06-30T13:35:00Z",
            "open": 30180.25,
            "high": 30251.0,
            "low": 30156.75,
            "close": 30247.5,
        }
        candle_0636 = {
            "timestamp": "2026-06-30T13:36:00Z",
            "open": 30248.25,
            "high": 30253.75,
            "low": 30212.0,
            "close": 30215.5,
        }

        entry_agent.recent_closed_bars = lambda _symbol="NQ", limit=120: [candle_0635, candle_0636][-limit:]
        persisted_same_candle = copy.deepcopy(prior_state)
        persisted_same_candle["step4"] = copy.deepcopy(confirmed_state["step4"])
        same_candle_step25 = entry_agent.evaluate_live_step25(snapshot_0636, rejection, step2, persisted_same_candle)

        previous_symbol_state = copy.deepcopy(confirmed_state)
        previous_symbol_state["step25"] = same_candle_step25
        previous_symbol_state["continuation_lane"] = {
            "lane_name": "continuation",
            "lane_status": "eligible",
            "pathway_status": "eligible",
            "active_liquidity_name": "PMH/LH/ONH",
            "liquidity_group": "HIGH 1",
            "active_liquidity_price": 30217.0,
            "close_boundary": 30142.75,
            "extreme_boundary": 30217.0,
            "wick_boundary_extreme": 30212.0,
            "step2_candle_count": None,
            "step4_candle_count": None,
            "step2_status": "WAIT",
            "step25_status": "WAIT",
            "step4_status": "WAIT",
            "step2_step4_50_line": None,
            "step4_step5_75_line": None,
            "invalidation_reason": None,
            "continuation_type": "R/S",
        }

        reset_snapshot = _nq_20260630_0637_refresh_snapshot()
        reset_snapshot.update(
            {
                "step_2_1a": {
                    "step_2_activated": False,
                    "available": False,
                    "reason": "No active liquidity selected.",
                    "state_transition_reason": "No active liquidity selected.",
                    "active_level": None,
                    "level_price": None,
                    "active_liquidity_group": None,
                    "last_interacted_liquidity": None,
                },
                "rejection": {"rejection_mode": "OFF", "reason_text": "No active liquidity selected."},
                "step25": entry_agent.no_active_liquidity_result("Step 2.5", "No active liquidity selected."),
                "step3": entry_agent.no_active_liquidity_result("Step 3", "No active liquidity selected."),
                "step4": entry_agent.no_active_liquidity_result("Step 4", "No active liquidity selected."),
                "step5": entry_agent.no_active_liquidity_result("Step 5", "No active liquidity selected."),
                "step6": entry_agent.no_active_liquidity_result("Step 6", "No active liquidity selected."),
            }
        )
        assert entry_agent.restore_rejection_context_without_active_liquidity(reset_snapshot, previous_symbol_state) is True
        rejection_lane, continuation_lane = entry_agent.snapshot_lane_statuses(reset_snapshot, previous_symbol_state)
        reset_snapshot["rejection_lane"] = rejection_lane
        reset_snapshot["continuation_lane"] = continuation_lane

        persisted_state = {"symbols": {"NQ": previous_symbol_state}}
        with patch.object(entry_agent, "get_latest_market_snapshot", return_value=reset_snapshot), \
             patch.object(entry_agent, "load_entry_state", return_value=persisted_state), \
             patch.object(entry_agent, "run_once", return_value=reset_snapshot):
            status = entry_agent.build_entry_status("NQ")

        assert status["active_liquidity_name"] == "PMH/LH/ONH"
        assert status["wait_reason"] != "No active liquidity selected."
        assert status["rejection_lane"]["lane_status"] in {"controlling", "frozen"}
        assert status["rejection_lane"]["step2_status"] == "CONFIRMED"
        assert status["continuation_eligible"] is True
        assert status["continuation_lane"]["lane_status"] == "eligible"
        assert status["continuation_lane"]["wick_boundary_extreme"] == 30212.0
    finally:
        entry_agent.recent_closed_bars = original_recent


def test_same_stack_rotation_keeps_frozen_rejection_handoff_and_continuation_owner_match() -> None:
    import entry_agent

    active_group = {
        "name": "HIGH 1",
        "display_name": "PMH/LH/ONH",
        "side": "upper",
        "close_boundary": 30142.75,
        "extreme_boundary": 30217.0,
    }
    previous_symbol_state = {
        "trade_state": {
            "active": True,
            "lane_name": "rejection",
            "selected_pathway": "rejection",
            "selected_liquidity_name": "PMH",
            "active_liquidity_name": "PMH/LH/ONH",
            "active_liquidity_price": 30217.0,
            "active_liquidity_group": dict(active_group),
            "close_boundary": 30142.75,
            "step4": {"confirmed_at": "2026-07-03T13:31:00Z"},
        },
        "continuation_lane": {
            "lane_status": "controlling",
            "step2_status": "CONFIRMED",
            "step4_status": "WAIT",
            "active_liquidity_name": "PMH/LH/ONH",
            "active_liquidity_price": 30217.0,
            "active_liquidity_group": dict(active_group),
            "liquidity_group": "HIGH 1",
            "close_boundary": 30120.0,
            "extreme_boundary": 30217.0,
            "wick_boundary_extreme": 30120.0,
        },
    }

    frozen_reference = entry_agent.frozen_rejection_trade_state_reference(
        previous_symbol_state,
        "ONH",
        30217.0,
        dict(active_group),
    )
    assert frozen_reference is not None
    assert frozen_reference["boundary_price"] == 30142.75
    assert entry_agent.continuation_lane_matches_active_owner(
        previous_symbol_state["continuation_lane"],
        dict(active_group),
        30217.0,
    ) is True


def test_restore_continuation_context_without_active_liquidity_preserves_controlling_lane() -> None:
    import entry_agent

    active_group = {
        "name": "HIGH 1",
        "display_name": "PMH/LH/ONH",
        "side": "upper",
        "close_boundary": 30142.75,
        "extreme_boundary": 30217.0,
        "wick_boundary_extreme": 30120.0,
    }
    previous_symbol_state = {
        "step_2_1a": {"step_2_activated": True, "active_level": "PMH", "level_price": 30217.0, "active_liquidity_group": dict(active_group)},
        "step25": {
            "status": "READY",
            "state": {
                "continuation_step2_activated": True,
                "continuation_eligible_source": "frozen_rejection_trade_state",
                "continuation_active_boundary_price": 30120.0,
            },
        },
        "step3": {"status": "WAIT", "state": {}},
        "step4": {"status": "WAIT", "state": {"lane_id": "continuation|HIGH 1|30217.0"}},
        "step5": {"status": "WAIT", "state": {}},
        "step6": {"status": "WAIT", "state": {}},
        "continuation_lane": {
            "lane_status": "controlling",
            "step2_status": "CONFIRMED",
            "step4_status": "WAIT",
            "active_liquidity_name": "PMH/LH/ONH",
            "active_liquidity_price": 30217.0,
            "active_liquidity_group": dict(active_group),
            "liquidity_group": "HIGH 1",
            "close_boundary": 30120.0,
            "extreme_boundary": 30217.0,
            "wick_boundary_extreme": 30120.0,
        },
        "trade_state": {"active": True, "selected_pathway": "continuation"},
    }
    snapshot = {
        "step_2_1a": entry_agent.no_active_liquidity_result("Step 2"),
        "step25": entry_agent.no_active_liquidity_result("Step 2.5"),
        "step3": entry_agent.no_active_liquidity_result("Step 3"),
        "step4": entry_agent.no_active_liquidity_result("Step 4"),
        "step5": entry_agent.no_active_liquidity_result("Step 5"),
        "step6": entry_agent.no_active_liquidity_result("Step 6"),
    }

    assert entry_agent.restore_continuation_context_without_active_liquidity(snapshot, previous_symbol_state) is True
    assert snapshot["suppress_active_liquidity"] is False
    assert snapshot["step25"]["state"]["continuation_step2_activated"] is True
    assert snapshot["step4"]["state"]["lane_id"] == "continuation|HIGH 1|30217.0"
    assert snapshot["trade_state"]["selected_pathway"] == "continuation"
    assert snapshot["continuation_lane"]["lane_status"] == "controlling"
    assert snapshot["continuation_lane"]["step2_status"] == "CONFIRMED"


def test_active_step4_candle_b_reservation_ignores_continuation_lane_window() -> None:
    import entry_agent

    persisted_state = {
        "step4": {
            "state": {
                "lane_id": "continuation|2026-07-03T13:37:00Z|ONH|LONG|29924.25|29924.25",
                "controlling_mode": "R/S",
                "leg1_window_active": True,
                "leg1_window_candle_index": 0,
                "leg1_status": None,
                "leg1_state_locked": False,
                "leg1_window_invalidated": False,
                "leg1_window_started_at": "2026-07-03T13:37:00Z",
                "active_liquidity": {"name": "ONH", "price": 29924.25},
                "candle_a": {"timestamp": "2026-07-03T13:37:00Z"},
            }
        }
    }

    reservation = entry_agent.active_step4_candle_b_reservation(
        persisted_state,
        {"timestamp": "2026-07-03T13:38:00Z"},
        expected_active_liquidity={"name": "ONH", "price": 29924.25},
    )

    assert reservation is None


def test_snapshot_lane_statuses_reports_continuation_step4_termination_on_continuation_lane_only() -> None:
    import entry_agent

    active_group = {
        "name": "HIGH 1",
        "display_name": "PMH/ONH Liquidity",
        "side": "upper",
        "close_boundary": 29924.25,
        "extreme_boundary": 29924.25,
        "wick_boundary_extreme": 29948.75,
        "components": ["ONH", "PMH"],
        "prices": {"ONH": 29924.25, "PMH": 29924.25},
    }
    snapshot = {
        "latest_bar_time": "2026-07-03T13:39:00Z",
        "latest_price": 29913.0,
        "normalized_symbol": "NQ",
        "symbol": "NQ",
        "liquidity": {"tick_size": 0.25},
        "tv_context": {"levels": {"PML": {"price": 29875.5}}, "daily_atr14": 745.1751981854},
        "step_2_1a": {
            "step_2_activated": True,
            "step2_locked_owner": {
                "setup_direction": "SHORT",
                "active_liquidity": {"name": "ONH", "price": 29924.25, "group": dict(active_group)},
            },
            "active_level": "ONH",
            "level_price": 29924.25,
            "active_liquidity_group": dict(active_group),
            "step2_activated_at": "2026-07-03T13:30:00Z",
        },
        "step25": {
            "status": "READY",
            "state": {
                "controlling_mode": "Normal Rejection Mode",
                "continuation_step2_activated": None,
                "continuation_active_boundary_price": 29924.25,
                "continuation_reference_boundary_price": 29924.25,
                "continuation_probe_boundary": {
                    "active": True,
                    "side": "upper",
                    "boundary_price": 29924.25,
                    "source": "frozen_rejection_trade_state",
                },
                "continuation_evaluation_started_at": "2026-07-03T13:37:00Z",
                "step25_block_reason": "Reserved Step 4 Candle B has priority; continuation cannot activate on the same candle.",
            },
        },
        "step4": {
            "step": "Step 4",
            "status": "TERMINATED",
            "reason": "Step 4 proximity filter hard bypass: distance from Anchor Extreme to nearest opposing liquidity is <= 10% daily ATR.",
            "state": {
                "lane_id": "continuation|2026-07-03T13:37:00Z|ONH|LONG|29924.25|29924.25",
                "controlling_mode": "R/S",
                "active_liquidity": {"name": "ONH", "price": 29924.25},
                "close_boundary": 29924.25,
                "extreme_boundary": 29924.25,
                "leg1_window_started_at": "2026-07-03T13:37:00Z",
                "leg1_window_invalidated": False,
                "invalidated_at": "2026-07-03T13:39:30Z",
                "invalidation_source": "step4",
                "invalidation_source_step": "Step 4",
                "setup_direction": "LONG",
            },
        },
        "step5": {"status": "WAIT", "state": {}},
        "step6": {"status": "WAIT", "state": {}},
    }
    previous_symbol_state = {
        "continuation_lane": {
            "lane_status": "controlling",
            "step2_status": "CONFIRMED",
            "step4_status": "WAIT",
            "active_liquidity_name": "ONH",
            "active_liquidity_price": 29924.25,
            "active_liquidity_group": dict(active_group),
            "liquidity_group": "HIGH 1",
            "close_boundary": 29924.25,
            "extreme_boundary": 29924.25,
            "wick_boundary_extreme": 29948.75,
        },
        "rejection_lane": {
            "lane_status": "frozen",
            "step2_status": "CONFIRMED",
            "step4_status": "CONFIRMED",
            "step2_confirmed_at": "2026-07-03T13:30:00Z",
            "active_liquidity_name": "ONH",
            "active_liquidity_price": 29924.25,
            "active_liquidity_group": dict(active_group),
            "liquidity_group": "HIGH 1",
            "close_boundary": 29924.25,
            "extreme_boundary": 29924.25,
            "wick_boundary_extreme": 29948.75,
        },
    }

    rejection_lane, continuation_lane = entry_agent.snapshot_lane_statuses(snapshot, previous_symbol_state)

    assert rejection_lane["lane_status"] == "controlling"
    assert rejection_lane["step4_status"] == "CONFIRMED"
    assert rejection_lane["invalidation_reason"] is None
    assert continuation_lane["lane_status"] == "invalidated"
    assert continuation_lane["step2_status"] == "CONFIRMED"
    assert continuation_lane["step2_confirmed_at"] == "2026-07-03T13:37:00Z"
    assert continuation_lane["step4_status"] == "TERMINATED"
    assert continuation_lane["invalidation_reason"] == "Step 4 proximity filter hard bypass: distance from Anchor Extreme to nearest opposing liquidity is <= 10% daily ATR."


def test_continuation_step4_skips_proximity_termination_and_confirms_on_valid_participation() -> None:
    from step4_engine import evaluate_step4

    result = evaluate_step4(
        {
            "rejection_mode": "ON",
            "step25_pathway_selection_complete": True,
            "step3_allows_structure": True,
            "interaction_state": "ACTIVE",
            "setup_direction": "LONG",
            "controlling_mode": "R/S",
            "structure_side_requirement": "BELOW_LEVEL",
            "pathway_level": 29924.25,
            "tick_size": 0.25,
            "daily_atr14": 745.1751981854,
            "nearest_opposing_liquidity": {"name": "PML", "price": 29875.5},
            "next_break_side_liquidity": {"name": "PML", "price": 29875.5},
            "active_liquidity": {"name": "ONH", "price": 29924.25},
            "initial_candle_a": {
                "timestamp": "2026-07-03T13:37:00Z",
                "open": 29928.0,
                "high": 29929.75,
                "low": 29922.0,
                "close": 29922.75,
            },
            "reclaim_candle_a": {
                "timestamp": "2026-07-03T13:37:00Z",
                "open": 29928.0,
                "high": 29929.75,
                "low": 29922.0,
                "close": 29922.75,
            },
            "candle_a": {
                "timestamp": "2026-07-03T13:37:00Z",
                "open": 29928.0,
                "high": 29929.75,
                "low": 29922.0,
                "close": 29922.75,
            },
            "candle_b": {
                "timestamp": "2026-07-03T13:39:00Z",
                "open": 29909.5,
                "high": 29914.5,
                "low": 29903.5,
                "close": 29913.0,
            },
            "latest_candle": {
                "timestamp": "2026-07-03T13:39:00Z",
                "open": 29909.5,
                "high": 29914.5,
                "low": 29903.5,
                "close": 29913.0,
            },
            "step4_window_candles": [
                {
                    "timestamp": "2026-07-03T13:37:00Z",
                    "open": 29928.0,
                    "high": 29929.75,
                    "low": 29922.0,
                    "close": 29922.75,
                }
            ],
            "leg1_window_started_at": "2026-07-03T13:37:00Z",
            "leg1_window_active": True,
            "lane_id": "continuation|2026-07-03T13:37:00Z|ONH|LONG|29924.25|29924.25",
            "events": [],
        }
    )

    assert result["status"] == "READY"
    assert result["reason"] != "Step 4 proximity filter hard bypass: distance from Anchor Extreme to nearest opposing liquidity is <= 10% daily ATR."
    assert result["state"]["step4_confirmed_at"] == "2026-07-03T13:39:00Z"


def test_carry_forward_seeded_continuation_lane_rejects_stale_owner() -> None:
    import entry_agent

    previous_symbol_state = {
        "continuation_lane": {
            "lane_status": "eligible",
            "step2_status": "WAIT",
            "active_liquidity_name": "PMH/LH/ONH",
            "active_liquidity_price": 30217.0,
            "active_liquidity_group": {
                "name": "HIGH 1",
                "display_name": "PMH/LH/ONH",
                "side": "upper",
                "close_boundary": 30142.75,
                "extreme_boundary": 30217.0,
            },
            "liquidity_group": "HIGH 1",
            "close_boundary": 30142.75,
            "extreme_boundary": 30217.0,
            "wick_boundary_extreme": 30212.0,
        }
    }

    assert entry_agent.carry_forward_seeded_continuation_lane(
        previous_symbol_state,
        continuation_group={
            "name": "LOW 1",
            "display_name": "PML/ONL",
            "side": "lower",
            "close_boundary": 30010.0,
            "extreme_boundary": 29980.0,
        },
        active_price=29980.0,
    ) is None


def test_existing_615_lock_freeze_behavior_still_holds() -> None:
    import tv_context_server

    original_levels = tv_context_server.LEVELS_PATH
    original_levels_by_symbol = tv_context_server.LEVELS_BY_SYMBOL_PATH
    original_context = tv_context_server.TV_CONTEXT_PATH
    original_context_by_symbol = tv_context_server.TV_CONTEXT_BY_SYMBOL_PATH
    original_events = tv_context_server.TV_CONTEXT_EVENTS_PATH
    original_log_dir = tv_context_server.ENTRY_LOG_DIR
    original_log_path = tv_context_server.ENTRY_DECISIONS_LOG_PATH
    original_latest = dict(tv_context_server.LATEST_TV_CONTEXT_BY_SYMBOL)
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            tv_context_server.LEVELS_PATH = temp_root / "levels.json"
            tv_context_server.LEVELS_BY_SYMBOL_PATH = temp_root / "levels_by_symbol.json"
            tv_context_server.TV_CONTEXT_PATH = temp_root / "tv_context.json"
            tv_context_server.TV_CONTEXT_BY_SYMBOL_PATH = temp_root / "tv_context_by_symbol.json"
            tv_context_server.TV_CONTEXT_EVENTS_PATH = temp_root / "tv_context_events.jsonl"
            tv_context_server.ENTRY_LOG_DIR = temp_root / "logs"
            tv_context_server.ENTRY_LOG_DIR.mkdir(parents=True, exist_ok=True)
            tv_context_server.ENTRY_DECISIONS_LOG_PATH = tv_context_server.ENTRY_LOG_DIR / "entry_decisions.jsonl"
            tv_context_server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()

            first_payload = _valid_webhook_payload(timestamp="2026-06-22T13:15:00Z")
            second_payload = _valid_webhook_payload(timestamp="2026-06-22T13:20:00Z")
            second_payload["force"] = True
            second_payload["liquidity_map"]["levels"][0]["price"] = 111.0
            second_payload["liquidity_map"]["levels"][1]["price"] = 112.0

            with tv_context_server.app.test_client() as client:
                first = client.post("/webhook/tv-context", json=first_payload)
                second = client.post("/webhook/tv-context", json=second_payload)

                assert first.status_code == 200
                assert second.status_code == 200
                second_context = second.get_json()["context"]
                assert second_context["liquidity_context_locked"] is True
                assert second_context["levels"]["PMH"]["price"] == 100.0
                assert second_context["levels"]["ONH"]["price"] == 101.0
                assert second_context["locked_liquidity_context"]["midpoints"]["PML_ONL"] == 89.5
                assert second_context["locked_liquidity_context"]["exhaustion_boundaries"]["PML_ONL"]["remaining_25"] == 89.25
    finally:
        tv_context_server.LEVELS_PATH = original_levels
        tv_context_server.LEVELS_BY_SYMBOL_PATH = original_levels_by_symbol
        tv_context_server.TV_CONTEXT_PATH = original_context
        tv_context_server.TV_CONTEXT_BY_SYMBOL_PATH = original_context_by_symbol
        tv_context_server.TV_CONTEXT_EVENTS_PATH = original_events
        tv_context_server.ENTRY_LOG_DIR = original_log_dir
        tv_context_server.ENTRY_DECISIONS_LOG_PATH = original_log_path
        tv_context_server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
        tv_context_server.LATEST_TV_CONTEXT_BY_SYMBOL.update(original_latest)


def test_public_liquidity_lock_payload_exposes_full_frozen_session_contract() -> None:
    import entry_agent

    snapshot = {
        "latest_bar_time": "2026-06-22T13:30:00Z",
        "session_liquidity_context": {
            "locked": True,
            "disabled": False,
            "active_levels": {
                "PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "ONH": {"price": 101.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "PML": {"price": 90.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "ONL": {"price": 89.0, "status": "ACTIVE", "stack_group": "LOW 1"},
            },
            "active_groups": [
                {
                    "name": "HIGH 1",
                    "display_name": "PMH/ONH Liquidity",
                    "components": ["PMH", "ONH"],
                    "close_boundary": 100.0,
                    "extreme_boundary": 101.0,
                    "close_component": "PMH",
                    "extreme_component": "ONH",
                },
                {
                    "name": "LOW 1",
                    "display_name": "PML/ONL Liquidity",
                    "components": ["PML", "ONL"],
                    "close_boundary": 90.0,
                    "extreme_boundary": 89.0,
                    "close_component": "PML",
                    "extreme_component": "ONL",
                },
            ],
            "tv_context": {
                "session_date": "2026-06-22",
                "liquidity_context_locked_at": "2026-06-22T13:15:00Z",
            },
        },
        "raw_tv_context": {
            "received_at": "2026-06-22T13:40:00Z",
            "last_tv_context_received_at": "2026-06-22T13:40:00Z",
            "last_tv_context_session_date": "2026-06-22",
            "last_tv_context_levels": {
                "PMH": {"price": 111.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
            },
            "locked_liquidity_context": {
                "liquidity_map": {
                    "levels": [
                        {"name": "PMH", "price": 100.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                        {"name": "ONH", "price": 101.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                        {"name": "PML", "price": 90.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                        {"name": "ONL", "price": 89.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                        {"name": "YL", "price": 80.0, "status": "INACTIVE", "stack_group": "NONE"},
                    ],
                    "stacks": [
                        {
                            "name": "HIGH 1",
                            "members": ["PMH", "ONH"],
                            "close_boundary_name": "PMH",
                            "close_boundary_price": 100.0,
                            "extreme_boundary_name": "ONH",
                            "extreme_boundary_price": 101.0,
                        },
                        {
                            "name": "LOW 1",
                            "members": ["PML", "ONL"],
                            "close_boundary_name": "PML",
                            "close_boundary_price": 90.0,
                            "extreme_boundary_name": "ONL",
                            "extreme_boundary_price": 89.0,
                        },
                    ],
                },
                "midpoints": {"PML_ONL": 89.5},
                "exhaustion_boundaries": {"PML_ONL": {"side": "lower", "mid_50": 89.5, "remaining_25": 89.25}},
            },
        },
    }

    payload = entry_agent.public_liquidity_lock_payload(
        snapshot=snapshot,
        active_name="PML",
        active_price=90.0,
        active_group=snapshot["session_liquidity_context"]["active_groups"][1],
    )

    contract = payload["frozen_session_contract"]
    assert payload["locked"] is True
    assert contract["midpoints"]["PML_ONL"] == 89.5
    assert contract["exhaustion_boundaries"]["PML_ONL"]["side"] == "lower"
    assert contract["exhaustion_boundaries"]["PML_ONL"]["mid_50"] == 89.5
    assert contract["exhaustion_boundaries"]["PML_ONL"]["remaining_25"] == 89.25
    assert contract["levels"][0]["name"] == "PMH"
    assert contract["levels"][0]["close_boundary_name"] == "PMH"
    assert contract["levels"][0]["extreme_boundary_name"] == "ONH"
    assert contract["levels"][2]["is_active_owner"] is True
    assert contract["levels"][3]["is_active_owner"] is True
    assert contract["levels"][4]["status"] == "INACTIVE"
    assert contract["levels"][4]["stack_group"] is None


def test_frozen_session_contract_projects_same_side_level_into_stack_within_daily_atr_threshold() -> None:
    entry_agent = importlib.import_module("entry_agent")

    snapshot = {
        "session_liquidity_context": {
            "locked": True,
            "disabled": False,
            "active_levels": {
                "LH": {"price": 52714.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "ONH": {"price": 52714.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
            },
            "active_groups": [
                {
                    "name": "HIGH 1",
                    "display_name": "LH/ONH Liquidity",
                    "components": ["LH", "ONH"],
                    "prices": {"LH": 52714.0, "ONH": 52714.0},
                    "side": "upper",
                    "close_boundary": 52714.0,
                    "extreme_boundary": 52714.0,
                }
            ],
            "tv_context": {
                "session_date": "2026-06-30",
                "liquidity_context_locked_at": "2026-06-30T13:15:00Z",
                "daily_atr14": 736.0,
            },
        },
        "raw_tv_context": {
            "locked_liquidity_context": {
                "daily_atr14": 736.0,
                "levels": {
                    "LH": {"price": 52714.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "ONH": {"price": 52714.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "YH": {"price": 52700.0, "status": "ACTIVE", "stack_group": "NONE"},
                },
                "liquidity_map": {
                    "levels": [
                        {"name": "LH", "price": 52714.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                        {"name": "ONH", "price": 52714.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                        {"name": "YH", "price": 52700.0, "status": "ACTIVE", "stack_group": "NONE"},
                    ],
                    "stacks": [
                        {
                            "name": "HIGH 1",
                            "members": ["LH", "ONH"],
                            "close_boundary_name": "LH",
                            "close_boundary_price": 52714.0,
                            "extreme_boundary_name": "ONH",
                            "extreme_boundary_price": 52714.0,
                        }
                    ],
                },
            }
        },
    }

    payload = entry_agent.public_liquidity_lock_payload(
        snapshot=snapshot,
        active_name="LH",
        active_price=52714.0,
        active_group=snapshot["session_liquidity_context"]["active_groups"][0],
    )

    contract = payload["frozen_session_contract"]
    level_rows = {row["name"]: row for row in contract["levels"]}
    assert level_rows["YH"]["stack_group"] == "HIGH 1"
    assert contract["stacks"][0]["name"] == "HIGH 1"
    assert contract["stacks"][0]["members"] == ["LH", "ONH", "YH"]


def test_entry_status_endpoint_includes_frozen_session_contract() -> None:
    import tv_context_server

    original_build = tv_context_server.build_entry_status
    original_append_decision = tv_context_server.append_entry_decision_log
    original_append_reasoning = tv_context_server.append_entry_reasoning_log
    original_context_by_root = tv_context_server.stored_context_by_root
    try:
        tv_context_server.build_entry_status = lambda symbol: {
            "symbol": symbol,
            "current_step": "Step 2",
            "current_step_label": "Step 2",
            "active_liquidity_name": "PML/ONL",
            "setup_direction": None,
            "leg1_status": None,
            "leg2_status": None,
            "entry_status": "WAIT",
            "wait_reason": "test",
            "invalidation_reason": None,
            "last_decision": "WAIT",
            "liquidity_lock": {
                "locked": True,
                "session_date": "2026-06-25",
                "lock_time": "06:15:00 PT",
                "lock_source": "TradingView",
                "active_liquidity_name": "PML/ONL",
                "liquidity_group": "LOW 1",
                "close_boundary": 90.0,
                "extreme_boundary": 89.0,
                "frozen_stack_names": ["PML/ONL Liquidity"],
                "last_tv_context_received_time": "06:20:00 PT",
                "last_tv_context_session_date": "2026-06-25",
                "last_tv_context_matches_frozen": False,
                "frozen_session_contract": {
                    "levels": [
                        {
                            "name": "PML",
                            "price": 90.0,
                            "status": "ACTIVE",
                            "stack_group": "LOW 1",
                            "side": "lower",
                            "close_boundary_name": "PML",
                            "close_boundary": 90.0,
                            "extreme_boundary_name": "ONL",
                            "extreme_boundary": 89.0,
                            "is_active_owner": True,
                        }
                    ],
                    "midpoints": {"PML_ONL": 89.5},
                    "exhaustion_boundaries": {
                        "PML_ONL": {"side": "lower", "mid_50": 89.5, "remaining_25": 89.25}
                    },
                },
            },
        }
        tv_context_server.append_entry_decision_log = lambda records: None
        tv_context_server.append_entry_reasoning_log = lambda records: None
        tv_context_server.stored_context_by_root = lambda: {}

        with tv_context_server.app.test_client() as client:
            response = client.get("/entry/status?symbols=NQ")
            assert response.status_code == 200
            payload = response.get_json()
    finally:
        tv_context_server.build_entry_status = original_build
        tv_context_server.append_entry_decision_log = original_append_decision
        tv_context_server.append_entry_reasoning_log = original_append_reasoning
        tv_context_server.stored_context_by_root = original_context_by_root

    symbol_payload = payload["symbols"][0]
    lock = symbol_payload["liquidity_lock"]
    assert "frozen_session_contract" in lock
    assert lock["frozen_session_contract"]["levels"][0]["name"] == "PML"
    assert lock["frozen_session_contract"]["exhaustion_boundaries"]["PML_ONL"]["remaining_25"] == 89.25


def test_build_entry_status_observation_window_uses_frozen_display_level_and_blocks_public_steps() -> None:
    import entry_agent

    original_run_once = entry_agent.run_once
    try:
        entry_agent.run_once = lambda symbol, persist=True: {
            "requested_symbol": symbol,
            "normalized_symbol": "NQ",
            "latest_price": 29688.75,
            "latest_bar_time": "2026-06-23T13:27:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 29709.5, "high": 29714.25, "low": 29682.0, "close": 29688.75},
            "tv_context": {
                "symbol": "NQ",
                "normalized_symbol": "NQ",
                "locked": True,
                "context_locked": True,
                "locked_for_day": True,
                "liquidity_context_locked": True,
                "liquidity_context_locked_at": "2026-06-23T13:15:00Z",
                "levels": {
                    "PML": {"price": 29691.75, "status": "ACTIVE", "stack_group": "LOW 1"},
                    "ONL": {"price": 29690.25, "status": "ACTIVE", "stack_group": "LOW 1"},
                },
            },
            "liquidity": {"tick_size": 0.25},
            "pre_open_observed_extreme": {"side": "lower", "price": 29682.0, "source_level": "PML", "stack_group": "LOW 1"},
            "step_2_1a": {"step_2_activated": False, "blocked": True, "reason": "observation"},
            "rejection": {"rejection_mode": "OFF", "reason_text": "observation"},
            "step25": {"status": "WAIT", "reason": "observation", "state": {}},
            "step3": {"status": "WAIT", "reason": "observation", "state": {}},
            "step4": {"status": "WAIT", "reason": "observation", "state": {}},
            "step5": {"status": "WAIT", "reason": "observation", "state": {}},
            "step6": {"status": "WAIT", "reason": "observation", "state": {}},
        }

        status = entry_agent.build_entry_status("NQ")
    finally:
        entry_agent.run_once = original_run_once

    assert status["active_liquidity_name"] == "PML/ONL"
    assert status["active_liquidity_price"] == 29691.75
    assert status["frozen_tv_level"] == 29691.75
    assert status["pre_open_observed_extreme"]["price"] == 29682.0
    assert status["wick_boundary_extreme"] == 29682.0
    assert status["current_pathway_control"] == "OBSERVATION_ONLY"
    assert status["control_state"] == "OBSERVATION_ONLY"
    assert status["step2_status"] == "WAIT"
    assert status.get("step25_status") is None
    assert status["step4_status"] == "WAIT"
    assert status["step5_status"] == "BLOCKED_PREOPEN_OBSERVATION"
    assert status["step6_status"] == "BLOCKED_PREOPEN_OBSERVATION"
    assert status["conflict_state"] == "NONE_PREOPEN"
    assert "06:15-06:29 PT is observation-only" in status["wait_reason"]
