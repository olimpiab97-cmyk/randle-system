import copy
import importlib.util
import sys
import json
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent
ENTRY_AGENT_DIR = ROOT / "EntryAgent"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ENTRY_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(ENTRY_AGENT_DIR))

import entry_agent


def load_listener():
    spec = importlib.util.spec_from_file_location(
        "rithmic_live_listener_nq_0716_test",
        ROOT / "rithmic_live_listener.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NQ_LEVELS = {
    "PMH": {"price": 29457.25, "status": "ACTIVE", "stack_group": "NONE"},
    "PML": {"price": 29363.50, "status": "ACTIVE", "stack_group": "LOW 1"},
    "LH": {"price": 29645.25, "status": "ACTIVE", "stack_group": "NONE"},
    "LL": {"price": 29361.00, "status": "ACTIVE", "stack_group": "LOW 1"},
    "ONH": {"price": 29797.00, "status": "ACTIVE", "stack_group": "NONE"},
    "ONL": {"price": 29361.00, "status": "ACTIVE", "stack_group": "LOW 1"},
    "YH": {"price": 29977.50, "status": "ACTIVE", "stack_group": "NONE"},
    "YL": {"price": 29397.00, "status": "INACTIVE", "stack_group": "NONE"},
}


# Captured NQ minute bars reconstructed from the 2026-07-16 local authority
# evidence. The original source path/hash manifest was not retained; see
# DEBT-2026-07-16-002. 13:15 and 13:20 were locally committed live but
# initially absent from the shared recent-bar projection after WinError 5.
NQ_0716_BARS = [
    ("2026-07-16T13:15:00Z", 29451.50, 29452.75, 29441.75, 29445.75),
    ("2026-07-16T13:16:00Z", 29446.50, 29455.50, 29446.00, 29451.25),
    ("2026-07-16T13:17:00Z", 29451.00, 29459.75, 29449.00, 29451.75),
    ("2026-07-16T13:18:00Z", 29451.00, 29460.00, 29450.50, 29452.75),
    ("2026-07-16T13:19:00Z", 29452.00, 29459.00, 29449.25, 29457.75),
    ("2026-07-16T13:20:00Z", 29457.25, 29465.25, 29456.25, 29459.25),
    ("2026-07-16T13:21:00Z", 29458.75, 29477.75, 29455.75, 29473.50),
    ("2026-07-16T13:22:00Z", 29473.50, 29473.50, 29461.00, 29471.25),
    ("2026-07-16T13:23:00Z", 29470.75, 29481.50, 29468.50, 29479.75),
    ("2026-07-16T13:24:00Z", 29479.75, 29488.50, 29477.50, 29484.25),
    ("2026-07-16T13:25:00Z", 29484.00, 29484.00, 29456.25, 29457.00),
    ("2026-07-16T13:26:00Z", 29459.00, 29463.25, 29456.25, 29461.50),
    ("2026-07-16T13:27:00Z", 29463.00, 29470.00, 29448.00, 29462.25),
    ("2026-07-16T13:28:00Z", 29462.75, 29465.75, 29447.50, 29453.50),
    ("2026-07-16T13:29:00Z", 29453.75, 29472.00, 29453.25, 29465.75),
    ("2026-07-16T13:30:00Z", 29466.00, 29532.00, 29460.25, 29504.75),
    ("2026-07-16T13:31:00Z", 29505.00, 29529.50, 29478.25, 29523.25),
    ("2026-07-16T13:32:00Z", 29522.50, 29529.00, 29475.00, 29485.50),
    ("2026-07-16T13:33:00Z", 29485.00, 29501.25, 29458.50, 29475.75),
    ("2026-07-16T13:34:00Z", 29475.25, 29482.25, 29429.75, 29433.50),
    ("2026-07-16T13:35:00Z", 29435.50, 29448.25, 29399.75, 29417.25),
    ("2026-07-16T13:36:00Z", 29418.75, 29437.50, 29402.00, 29425.50),
    ("2026-07-16T13:37:00Z", 29425.50, 29471.00, 29425.50, 29439.25),
    ("2026-07-16T13:38:00Z", 29439.75, 29440.00, 29395.75, 29407.25),
    ("2026-07-16T13:39:00Z", 29407.25, 29420.75, 29378.50, 29384.75),
    ("2026-07-16T13:40:00Z", 29387.25, 29434.50, 29373.50, 29399.75),
    ("2026-07-16T13:41:00Z", 29399.00, 29401.50, 29346.75, 29350.50),
]


def nq_context():
    return {
        "symbol": "CME_MINI:NQ1!",
        "normalized_symbol": "NQ",
        "source": "tradingview_level_helper",
        "received_at": "2026-07-16T13:15:04.726871Z",
        "session_date": "2026-07-16",
        "time_zone": "America/Los_Angeles",
        "locked": True,
        "context_locked": True,
        "locked_for_day": True,
        "liquidity_context_locked": True,
        "liquidity_context_locked_at": "2026-07-16T13:15:04.726871Z",
        "daily_atr14": 500.0,
        "levels": copy.deepcopy(NQ_LEVELS),
    }


def market_snapshot(row):
    timestamp, open_price, high, low, close = row
    return {
        "symbol": "NQ",
        "normalized_symbol": "NQ",
        "latest_price": close,
        "latest_bar_time": timestamp,
        "ohlc_is_closed": True,
        "ohlc": {
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
        },
    }


def replay_nq_0716(tmp_path):
    original_paths = (
        entry_agent.STATE_PATH,
        entry_agent.PERSISTENCE_STATE_PATH,
        entry_agent.EXECUTOR_STATE_PATH,
    )
    replay_rows = []
    index = {"value": 0}
    states = {}
    snapshots = {}
    statuses = {}

    def snapshot_for_index(_symbol="NQ"):
        return market_snapshot(NQ_0716_BARS[index["value"]])

    try:
        entry_agent.STATE_PATH = tmp_path / "entry_agent_state.json"
        entry_agent.PERSISTENCE_STATE_PATH = tmp_path / "persistence_state.json"
        entry_agent.EXECUTOR_STATE_PATH = tmp_path / "executor_state.json"
        with (
            patch.object(entry_agent, "get_latest_market_snapshot", side_effect=snapshot_for_index),
            patch.object(entry_agent, "load_raw_tv_context", return_value=nq_context()),
            patch.object(entry_agent, "load_tv_context", return_value=nq_context()),
            patch.object(entry_agent, "recent_closed_bars", side_effect=lambda _symbol="NQ", limit=120: list(replay_rows)[-limit:]),
            patch.object(entry_agent, "load_rithmic_atr_snapshot", return_value=None),
            patch.object(entry_agent, "append_entry_agent_audit_row", return_value=None),
        ):
            for current_index, row in enumerate(NQ_0716_BARS):
                index["value"] = current_index
                replay_rows.append(
                    {
                        "timestamp": row[0],
                        "open": row[1],
                        "high": row[2],
                        "low": row[3],
                        "close": row[4],
                    }
                )
                snapshot = entry_agent.run_once("NQ", persist=True)
                snapshots[row[0]] = copy.deepcopy(snapshot)
                states[row[0]] = copy.deepcopy(
                    entry_agent.load_entry_state().get("state_by_symbol", {}).get("NQ", {})
                )
                if row[0] == "2026-07-16T13:41:00Z":
                    statuses[row[0]] = copy.deepcopy(entry_agent.build_entry_status("NQ"))
    finally:
        (
            entry_agent.STATE_PATH,
            entry_agent.PERSISTENCE_STATE_PATH,
            entry_agent.EXECUTOR_STATE_PATH,
        ) = original_paths
    return snapshots, states, statuses


def test_actual_0716_replay_rotates_high_owner_to_low_stack_on_0641_close(tmp_path):
    snapshots, states, statuses = replay_nq_0716(tmp_path)
    final_snapshot = snapshots["2026-07-16T13:41:00Z"]
    final_step2 = final_snapshot["step_2_1a"]
    active_group = final_step2.get("active_liquidity_group") or {}

    assert final_snapshot["ohlc"]["close"] == 29350.50
    assert final_snapshot["ohlc"]["close"] < 29363.50
    assert final_step2["state_transition_reason"] == entry_agent.OPPOSITE_SIDE_LIQUIDITY_BREACH_RELEASE
    assert active_group["name"] == "LOW 1"
    assert set(active_group["components"]) == {"PML", "LL", "ONL"}
    assert active_group["close_boundary"] == 29363.50
    assert active_group["extreme_boundary"] == 29361.00
    assert states["2026-07-16T13:41:00Z"]["step2_locked_owner"]["active_liquidity"]["side"] == "lower"
    assert final_snapshot.get("owner_rotation_released") is True
    public_status = statuses["2026-07-16T13:41:00Z"]
    assert public_status["active_liquidity_group"]["name"] == "LOW 1"
    assert public_status["active_liquidity_price"] == 29361.00


def test_actual_0716_pre_step2_boundary_never_retracts(tmp_path):
    snapshots, states, _statuses = replay_nq_0716(tmp_path)
    expected_running_highs = {
        "2026-07-16T13:15:00Z": None,
        "2026-07-16T13:16:00Z": None,
        "2026-07-16T13:17:00Z": 29459.75,
        "2026-07-16T13:18:00Z": 29460.00,
        "2026-07-16T13:19:00Z": 29460.00,
        "2026-07-16T13:20:00Z": 29465.25,
        "2026-07-16T13:21:00Z": 29477.75,
        "2026-07-16T13:22:00Z": 29477.75,
        "2026-07-16T13:23:00Z": 29481.50,
        "2026-07-16T13:24:00Z": 29488.50,
        "2026-07-16T13:25:00Z": 29488.50,
        "2026-07-16T13:26:00Z": 29488.50,
        "2026-07-16T13:27:00Z": 29488.50,
        "2026-07-16T13:28:00Z": 29488.50,
        "2026-07-16T13:29:00Z": 29488.50,
        "2026-07-16T13:30:00Z": 29488.50,
    }
    observed = {}
    for timestamp, expected in expected_running_highs.items():
        observed_extreme = snapshots[timestamp].get("pre_open_observed_extreme") or {}
        observed[timestamp] = observed_extreme.get("price")
        assert observed[timestamp] == expected
        assert (states[timestamp].get("pre_open_observed_extreme") or {}).get("price") == expected
    running_values = [value for value in observed.values() if value is not None]
    assert running_values == sorted(running_values)

    # These are the raw inward highs that appeared live. Neither the changed
    # 06:25 close nor the later candle may replace the accepted 06:24 extreme.
    assert entry_agent.observed_pre_open_extreme_from_snapshot(
        snapshots["2026-07-16T13:25:00Z"], 0.25
    )["price"] == 29484.00
    assert entry_agent.observed_pre_open_extreme_from_snapshot(
        snapshots["2026-07-16T13:26:00Z"], 0.25
    )["price"] == 29463.25
    for timestamp in expected_running_highs:
        if timestamp < "2026-07-16T13:30:00Z":
            assert snapshots[timestamp]["step_2_1a"]["step_2_activated"] is False

    open_step2 = snapshots["2026-07-16T13:30:00Z"]["step_2_1a"]
    assert open_step2["step_2_activated"] is True
    assert open_step2["pre_activation_probe_boundary"]["boundary_price"] == 29488.50


def test_pre_open_observed_extreme_requires_same_identity_and_strict_outward_move():
    upper = {
        "side": "upper",
        "price": 29488.50,
        "source_level": "PMH",
        "locked_boundary_price": 29457.25,
        "session_date": "2026-07-16",
        "timestamp": "2026-07-16T13:24:00Z",
    }

    higher = {**upper, "price": 29490.00, "timestamp": "2026-07-16T13:25:00Z"}
    assert entry_agent.merged_pre_open_observed_extreme(upper, higher) == higher

    for candidate in (
        {**upper, "price": 29488.50, "timestamp": "2026-07-16T13:25:00Z"},
        {**upper, "price": 29484.00, "close": 29500.00, "timestamp": "2026-07-16T13:25:00Z"},
        {**upper, "side": "lower", "price": 29350.00, "source_level": "PML"},
        {**upper, "source_level": "LH", "locked_boundary_price": 29645.25, "price": 29650.00},
        {**upper, "session_date": "2026-07-17", "price": 29500.00},
    ):
        assert entry_agent.merged_pre_open_observed_extreme(upper, candidate) == upper

    lower = {
        "side": "lower",
        "price": 29350.00,
        "stack_group": "LOW 1",
        "locked_boundary_price": 29361.00,
        "session_date": "2026-07-16",
    }
    farther_lower = {**lower, "price": 29345.00}
    assert entry_agent.merged_pre_open_observed_extreme(lower, farther_lower) == farther_lower
    assert entry_agent.merged_pre_open_observed_extreme(lower, {**lower, "price": 29355.00}) == lower


def test_percentage_anchors_use_nearest_same_side_liquidity_and_stay_frozen():
    context = nq_context()
    active = {"name": "PMH", "price": 29457.25, "side": "upper"}
    target = entry_agent.next_same_side_liquidity_target(context, active)
    assert target["name"] == "LH"
    assert target["price"] == 29645.25

    step2 = {
        "active_level": "PMH",
        "level_price": 29457.25,
        "side": "upper",
        "next_same_side_liquidity": copy.deepcopy(target),
    }
    step4_state = {"leg1_window_active": True, "leg1_status": "PENDING"}
    before = entry_agent.step4_participation_line_payload(
        {"tv_context": context, "latest_price": 29400.0},
        step2,
        step4_state,
        rejection_active=True,
        selected_pathway="rejection",
        setup_direction="SHORT",
        leg1_published=False,
        invalidated=False,
    )
    after = entry_agent.step4_participation_line_payload(
        {"tv_context": context, "latest_price": 29350.5},
        step2,
        step4_state,
        rejection_active=True,
        selected_pathway="rejection",
        setup_direction="SHORT",
        leg1_published=False,
        invalidated=False,
    )
    assert before["line_50"] == after["line_50"] == 29551.25
    assert before["line_75"] == after["line_75"] == 29598.25


def test_nq_percentage_anchor_correction_does_not_change_ym_target_priority():
    context = nq_context()
    context["symbol"] = "CBOT_MINI:YM1!"
    context["normalized_symbol"] = "YM"
    target = entry_agent.next_same_side_liquidity_target(
        context,
        {"name": "PMH", "price": 29457.25, "side": "upper"},
    )
    assert target["name"] == "YH"
    assert target["price"] == 29977.50


class ArchiveSink:
    def __init__(self):
        self.rows = []

    def submit(self, row):
        self.rows.append(copy.deepcopy(row))


def authoritative_bar(listener, minute_index, symbol="NQU6"):
    timestamp = datetime(2026, 7, 16, 12, 45, tzinfo=timezone.utc) + timedelta(minutes=minute_index)
    base = 29400.0 + minute_index
    return {
        "session_date": "2026-07-16",
        "root_symbol": "NQ",
        "exchange": "CME",
        "contract_symbol": symbol,
        "symbol": symbol,
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "open": base,
        "high": base + 4.0,
        "low": base - 3.0,
        "close": base + 1.0,
        "status": "FINAL",
        "builder_contract_version": listener.BAR_BUILDER_CONTRACT_VERSION,
        "bar_id": f"{symbol}-bar-{minute_index}",
    }


def local_commit(bar):
    return {
        "local_commit_completed_at_utc": "2026-07-16T13:00:00Z",
        "local_commit_completed_unix_ns": 1,
        "local_commit_completed_monotonic_ns": 1,
        "local_journal_path": "test-finalized-bars.jsonl",
        "idempotent": False,
    }


def test_nq_projection_failure_reconciles_without_rma_or_ym_reset():
    listener = load_listener()
    cache = {}
    with (
        patch.object(listener, "commit_finalized_bar_to_local_journal", side_effect=local_commit),
        patch.object(listener, "persist_recent_bars", return_value=None),
        patch.object(listener, "update_atr_shadow_comparison", return_value={}),
    ):
        for index in range(29):
            listener.update_recent_bars(
                cache,
                authoritative_bar(listener, index),
                publish_shadow=False,
                publish_atr_mirror=False,
            )
    nq_before = copy.deepcopy(cache["NQU6"][-1]["canonical_atr"])
    assert nq_before["ready"] is True
    assert nq_before["warmup_true_range_count"] == 28

    ym_record = {"ready": True, "updated_raw_atr": 42.0, "warmup_true_range_count": 28}
    cache["YMU6"] = deque(
        [{"timestamp": "2026-07-16T13:13:00Z", "symbol": "YMU6", "canonical_atr": ym_record}],
        maxlen=listener.MAX_PERSISTED_BARS,
    )
    archive = ArchiveSink()
    worker = listener.TickWorker(cache, archive_reconciler=archive)
    failed_bar = authoritative_bar(listener, 29)
    exposure_attempts = {"count": 0}

    def fail_twice_then_succeed(_cache):
        exposure_attempts["count"] += 1
        if exposure_attempts["count"] <= 2:
            raise PermissionError("simulated OneDrive sharing violation")

    incident_counter = {"value": 0}

    def incident(_incident_type, tick=None, **details):
        incident_counter["value"] += 1
        return {"incident_id": f"test-{incident_counter['value']}", "recorded_at_utc": "2026-07-16T13:15:00Z"}

    with (
        patch.object(listener, "commit_finalized_bar_to_local_journal", side_effect=local_commit),
        patch.object(listener, "persist_recent_bars", side_effect=fail_twice_then_succeed),
        patch.object(listener, "append_data_authority_incident", side_effect=incident),
        patch.object(worker, "publish_atr_mirrors", return_value=None),
    ):
        assert worker.process_completed_bar(failed_bar, "test") is False
        assert failed_bar["canonical_atr"]["ready"] is True
        assert failed_bar["canonical_atr"]["warmup_true_range_count"] == 29
        assert worker.pending_exposure_bars["NQU6"]
        assert cache["YMU6"][-1]["canonical_atr"] == ym_record

        assert worker.retry_pending_exposure("NQU6") is True

    assert not worker.pending_exposure_bars.get("NQU6")
    assert cache["NQU6"][-1]["canonical_atr"]["warmup_true_range_count"] == 29
    assert cache["NQU6"][-1]["canonical_atr"]["updated_raw_atr"] is not None
    assert cache["YMU6"][-1]["canonical_atr"] == ym_record
    assert any(row.get("bar_id") == failed_bar["bar_id"] for row in archive.rows)


def test_reconnect_incomplete_minute_preserves_completed_rma():
    listener = load_listener()
    ready_record = {"ready": True, "updated_raw_atr": 11.5, "warmup_true_range_count": 29}
    cache = {
        "NQU6": deque(
            [{"timestamp": "2026-07-16T13:14:00Z", "symbol": "NQU6", "canonical_atr": ready_record}],
            maxlen=listener.MAX_PERSISTED_BARS,
        )
    }
    worker = listener.TickWorker(cache, archive_reconciler=ArchiveSink())
    worker.current_tick_bars["NQU6"] = {
        "timestamp": "2026-07-16T13:15:00Z",
        "minute_start_ns": 1_752_672_900_000_000_000,
        "incomplete": True,
    }
    next_tick = {
        "symbol": "NQU6",
        "exchange_time_ns": worker.current_tick_bars["NQU6"]["minute_start_ns"] + listener.NANOSECONDS_PER_MINUTE,
        "callback_sequence": 2,
        "exchange_timestamp_utc": "2026-07-16T13:16:00Z",
        "exchange": "CME",
        "price": 29450.0,
        "size": 1,
        "callback_type": "Update",
        "source_ssboe": 1,
        "source_nsecs": 0,
        "source_usecs": 0,
    }
    with (
        patch.object(listener, "clear_atr_snapshot") as clear_snapshot,
        patch.object(worker, "record_authority_incident", return_value={}),
    ):
        result = worker.update_tick_bar(next_tick)
    assert result["transition_published"] is False
    clear_snapshot.assert_not_called()
    assert cache["NQU6"][-1]["canonical_atr"] == ready_record


def test_entry_status_is_not_live_until_canonical_state_rehydrated():
    import tv_context_server

    base_status = {
        "symbol": "NQ",
        "current_step": "Step 2",
        "current_step_label": "Step 2",
        "canonical_state_rehydrated": False,
        "canonical_state_rehydration_reason": "canonical_candle_atr_identity_mismatch",
    }
    with (
        patch.object(tv_context_server, "build_entry_status", return_value=base_status),
        patch.object(tv_context_server, "stored_context_by_root", return_value={}),
        patch.object(tv_context_server, "append_entry_decision_log", return_value=None),
        patch.object(tv_context_server, "append_entry_reasoning_log", return_value=None),
    ):
        with tv_context_server.app.test_client() as client:
            response = client.get("/entry/status?symbols=NQ")
    assert response.status_code == 503
    assert response.get_json()["service_status"] == "REHYDRATING"
    assert response.get_json()["ok"] is False

    live_status = {**base_status, "canonical_state_rehydrated": True, "canonical_state_rehydration_reason": None}
    with (
        patch.object(tv_context_server, "build_entry_status", return_value=live_status),
        patch.object(tv_context_server, "stored_context_by_root", return_value={}),
        patch.object(tv_context_server, "append_entry_decision_log", return_value=None),
        patch.object(tv_context_server, "append_entry_reasoning_log", return_value=None),
    ):
        with tv_context_server.app.test_client() as client:
            response = client.get("/entry/status?symbols=NQ")
    assert response.status_code == 200
    assert response.get_json()["service_status"] == "LIVE"
    assert response.get_json()["ok"] is True


def canonical_recent_bar_record():
    bar_id = "NQU6-20260716-1341"
    canonical = {
        "record_type": "canonical_rithmic_atr",
        "symbol_root": "NQ",
        "contract_symbol": "NQU6",
        "timeframe": "1m",
        "period": 14,
        "formula": entry_agent.CANONICAL_ATR_FORMULA,
        "formula_version": entry_agent.CANONICAL_ATR_FORMULA_VERSION,
        "atr_source": entry_agent.CANONICAL_ATR_SOURCE,
        "atr_record_id": "atr-NQU6-20260716-1341",
        "bar_id": bar_id,
        "finalized_candle_bar_id": bar_id,
        "last_included_bar_id": bar_id,
        "candle_minute": "2026-07-16T13:41:00Z",
        "last_included_bar": "2026-07-16T13:41:00Z",
        "builder_contract_version": "exchange_time_v1",
        "ready": True,
        "updated_raw_atr": 37.91864926764981,
        "warmup_status": "ready_continuation",
        "warmup_true_range_count": 29,
        "warmup_required_true_range_count": 14,
    }
    return {
        "timestamp": "2026-07-16T13:41:00Z",
        "session_date": "2026-07-16",
        "symbol": "NQU6",
        "status": "FINAL",
        "bar_id": bar_id,
        "builder_contract_version": "exchange_time_v1",
        "canonical_atr": canonical,
    }


def test_completed_nq_rma_survives_entry_agent_reconnect(tmp_path):
    original_recent = entry_agent.RITHMIC_RECENT_BARS_PATH
    original_health = entry_agent.RITHMIC_FEED_HEALTH_PATH
    original_state = entry_agent.STATE_PATH
    try:
        entry_agent.RITHMIC_RECENT_BARS_PATH = tmp_path / "rithmic_recent_bars.json"
        entry_agent.RITHMIC_FEED_HEALTH_PATH = tmp_path / "rithmic_feed_health.json"
        entry_agent.STATE_PATH = tmp_path / "entry_agent_state.json"
        entry_agent.RITHMIC_RECENT_BARS_PATH.write_text(
            json.dumps({"symbols": {"NQU6": [canonical_recent_bar_record()]}}),
            encoding="utf-8",
        )
        entry_agent.RITHMIC_FEED_HEALTH_PATH.write_text(json.dumps({"symbols": {}}), encoding="utf-8")
        entry_agent.STATE_PATH.write_text(json.dumps({"state_by_symbol": {"NQ": {"step4": {}}}}), encoding="utf-8")
        before = entry_agent.load_rithmic_atr_observation(
            "NQ", reference_time=datetime(2026, 7, 16, 14, 0, tzinfo=timezone.utc)
        )

        # Entry Agent process state is disposable across reconnect; listener
        # recent-bar/ATR authority is not.
        entry_agent.STATE_PATH.unlink()
        after = entry_agent.load_rithmic_atr_observation(
            "NQ", reference_time=datetime(2026, 7, 16, 14, 0, tzinfo=timezone.utc)
        )
    finally:
        entry_agent.RITHMIC_RECENT_BARS_PATH = original_recent
        entry_agent.RITHMIC_FEED_HEALTH_PATH = original_health
        entry_agent.STATE_PATH = original_state
    assert before == after
    assert after["ready"] is True
    assert after["warmup_true_range_count"] == 29


def test_command_center_projection_refresh_cannot_mutate_nq_rma(tmp_path):
    import tv_context_server

    recent_path = tmp_path / "rithmic_recent_bars.json"
    recent_path.write_text(
        json.dumps({"symbols": {"NQU6": [canonical_recent_bar_record()]}}),
        encoding="utf-8",
    )
    before = recent_path.read_bytes()
    live_status = {
        "symbol": "NQ",
        "current_step": "Step 2",
        "current_step_label": "Step 2",
        "canonical_state_rehydrated": True,
        "canonical_state_rehydration_reason": None,
        "canonical_atr_status": canonical_recent_bar_record()["canonical_atr"],
    }
    with (
        patch.object(tv_context_server, "build_entry_status", return_value=live_status),
        patch.object(tv_context_server, "stored_context_by_root", return_value={}),
        patch.object(tv_context_server, "append_entry_decision_log", return_value=None),
        patch.object(tv_context_server, "append_entry_reasoning_log", return_value=None),
    ):
        with tv_context_server.app.test_client() as client:
            for _ in range(5):
                assert client.get("/entry/status?symbols=NQ").status_code == 200
    assert recent_path.read_bytes() == before


def _historical_status_route_mutation_harness(tmp_path):
    """Preserve the pre-guard incident reconstruction source; do not collect it.

    The incident process access log shows status polls at 06:25:56, 06:25:58,
    and 06:26:00 before the first poll exposing the completed 06:25 candle at
    06:26:02.  The reasoning journal proves that response changed the public
    top-level boundary from 29488.50 to 29484.00 while the pre-open rejection
    lane itself remained idle/null.  This was the executable reconstruction
    before projection-mode writer guards made the illegal path unreachable.
    It remains non-collected historical source; the current-route conformance
    test below is the executable proof for the repaired architecture.
    """
    import tv_context_server

    nq_0624 = NQ_0716_BARS[9]
    nq_0625 = NQ_0716_BARS[10]

    def run_status_sequence(case_path, legacy_replace):
        original_paths = (
            entry_agent.STATE_PATH,
            entry_agent.PERSISTENCE_STATE_PATH,
            entry_agent.EXECUTOR_STATE_PATH,
        )
        current_row = {"value": nq_0624}
        route_trace = []
        real_run_once = entry_agent.run_once
        real_persist_observation = entry_agent.persist_pre_open_observed_extreme
        real_persist_state = entry_agent.persist_state

        def snapshot_for_symbol(symbol="NQ"):
            snapshot = market_snapshot(current_row["value"])
            snapshot["symbol"] = str(symbol).upper()
            snapshot["normalized_symbol"] = str(symbol).upper()
            return snapshot

        def context_for_symbol(symbol="NQ"):
            context = nq_context()
            root = str(symbol).upper()
            context["normalized_symbol"] = root
            context["symbol"] = "CME_MINI:NQ1!" if root == "NQ" else "CBOT_MINI:YM1!"
            return context

        def atr_for_symbol(symbol="NQ"):
            root = str(symbol).upper()
            timestamp = current_row["value"][0]
            record = copy.deepcopy(canonical_recent_bar_record()["canonical_atr"])
            record["symbol_root"] = root
            record["contract_symbol"] = "NQU6" if root == "NQ" else "YMU6"
            record["candle_minute"] = timestamp
            record["last_included_bar"] = timestamp
            return record

        def traced_run_once(symbol="NQ", persist=True):
            route_trace.append(("run_once", str(symbol).upper(), persist, current_row["value"][0]))
            return real_run_once(symbol, persist=persist)

        def traced_persist(snapshot, symbol, extreme):
            before = entry_agent.pre_open_observed_extreme(entry_agent.load_entry_state(), symbol)
            real_persist_observation(snapshot, symbol, extreme)
            after = entry_agent.pre_open_observed_extreme(entry_agent.load_entry_state(), symbol)
            route_trace.append(
                (
                    "observation_write",
                    str(symbol).upper(),
                    (before or {}).get("price"),
                    (extreme or {}).get("price"),
                    (after or {}).get("price"),
                )
            )

        def capture_reasoning(records, date_text=None):
            route_trace.append(
                (
                    "reasoning_projection",
                    tuple(
                        (
                            record.get("symbol"),
                            record.get("candle_time"),
                            record.get("rejection_boundary"),
                        )
                        for record in records
                    ),
                )
            )

        try:
            entry_agent.STATE_PATH = case_path / "entry_agent_state.json"
            entry_agent.PERSISTENCE_STATE_PATH = case_path / "persistence_state.json"
            entry_agent.EXECUTOR_STATE_PATH = case_path / "executor_state.json"
            case_path.mkdir(parents=True, exist_ok=True)
            merge_patch = (
                patch.object(
                    entry_agent,
                    "merged_pre_open_observed_extreme",
                    side_effect=lambda current, candidate: (
                        copy.deepcopy(candidate) if isinstance(candidate, dict) else copy.deepcopy(current)
                    ),
                )
                if legacy_replace
                else patch.object(
                    entry_agent,
                    "merged_pre_open_observed_extreme",
                    wraps=entry_agent.merged_pre_open_observed_extreme,
                )
            )
            with (
                patch.object(entry_agent, "get_latest_market_snapshot", side_effect=snapshot_for_symbol),
                patch.object(entry_agent, "load_raw_tv_context", side_effect=context_for_symbol),
                patch.object(entry_agent, "load_tv_context", side_effect=context_for_symbol),
                patch.object(entry_agent, "recent_closed_bars", return_value=[]),
                patch.object(entry_agent, "load_rithmic_atr_snapshot", side_effect=atr_for_symbol),
                patch.object(entry_agent, "load_rithmic_atr_observation", side_effect=atr_for_symbol),
                patch.object(entry_agent, "run_once", side_effect=traced_run_once),
                patch.object(entry_agent, "persist_pre_open_observed_extreme", side_effect=traced_persist),
                patch.object(entry_agent, "persist_state", wraps=real_persist_state) as full_state_writer,
                patch.object(tv_context_server, "stored_context_by_root", return_value={
                    "NQ": context_for_symbol("NQ"),
                    "YM": context_for_symbol("YM"),
                }),
                patch.object(tv_context_server, "append_entry_decision_log", return_value=None),
                patch.object(tv_context_server, "append_entry_reasoning_log", side_effect=capture_reasoning),
                merge_patch,
            ):
                with tv_context_server.app.test_client() as client:
                    # Same completed 06:24 candle across the last three live
                    # polls before the minute transition.
                    responses = [
                        client.get("/entry/status?symbols=NQ,YM")
                        for _ in range(3)
                    ]
                    current_row["value"] = nq_0625
                    responses.append(client.get("/entry/status?symbols=NQ,YM"))

            nq_statuses = [response.get_json()["symbols"][0] for response in responses]
            state = entry_agent.load_entry_state()["state_by_symbol"]["NQ"]
            full_state_call_count = full_state_writer.call_count
        finally:
            (
                entry_agent.STATE_PATH,
                entry_agent.PERSISTENCE_STATE_PATH,
                entry_agent.EXECUTOR_STATE_PATH,
            ) = original_paths
        return responses, nq_statuses, state, route_trace, full_state_call_count

    legacy_responses, legacy_statuses, legacy_state, legacy_trace, legacy_full_state_calls = run_status_sequence(
        tmp_path / "legacy",
        legacy_replace=True,
    )
    fixed_responses, fixed_statuses, fixed_state, fixed_trace, fixed_full_state_calls = run_status_sequence(
        tmp_path / "fixed",
        legacy_replace=False,
    )

    assert all(response.status_code == 200 for response in legacy_responses + fixed_responses)
    assert [status["rejection_boundary"] for status in legacy_statuses] == [
        29488.50,
        29488.50,
        29488.50,
        29484.00,
    ]
    assert legacy_statuses[-1]["pre_open_observed_extreme"]["price"] == 29484.00
    assert legacy_statuses[-1]["rejection_lane"]["rejection_boundary"] is None
    assert legacy_statuses[-1]["active_liquidity_name"] == "PMH"
    assert legacy_statuses[-1]["liquidity_level_price"] == 29457.25
    assert legacy_state["pre_open_observed_extreme"]["price"] == 29484.00

    assert [status["rejection_boundary"] for status in fixed_statuses] == [
        29488.50,
        29488.50,
        29488.50,
        29488.50,
    ]
    assert fixed_statuses[-1]["pre_open_observed_extreme"]["price"] == 29488.50
    assert fixed_statuses[-1]["rejection_lane"]["rejection_boundary"] is None
    assert fixed_statuses[-1]["active_liquidity_name"] == "PMH"
    assert fixed_statuses[-1]["liquidity_level_price"] == 29457.25
    assert fixed_state["pre_open_observed_extreme"]["price"] == 29488.50

    # Historical assertion: persist=False still reached the narrow observation
    # writer, while no persist_state/full-state write participated.
    assert all(event[2] is False for event in legacy_trace if event[0] == "run_once")
    assert all(event[2] is False for event in fixed_trace if event[0] == "run_once")
    assert legacy_full_state_calls == 0
    assert fixed_full_state_calls == 0
    assert ("observation_write", "NQ", 29488.50, 29484.00, 29484.00) in legacy_trace
    assert ("observation_write", "NQ", 29488.50, 29488.50, 29488.50) in fixed_trace
    assert any(
        event[0] == "reasoning_projection"
        and ("NQ", "2026-07-16T13:25:00Z", 29484.00) in event[1]
        for event in legacy_trace
    )
    assert any(
        event[0] == "reasoning_projection"
        and ("NQ", "2026-07-16T13:25:00Z", 29488.50) in event[1]
        for event in fixed_trace
    )


def test_actual_0716_status_route_projects_0625_without_mutating_authority(tmp_path):
    """Replay the exact live route after an authorized 06:24 canonical commit.

    Historically, the first status poll over the completed 06:25 candle called
    run_once(False), rewrote the observed wick to 29484, and journaled that
    projection.  The corrected route must project the committed 29488.50 wick
    while every evaluator and writer remains unreachable.
    """
    import tv_context_server

    nq_0624 = NQ_0716_BARS[9]
    nq_0625 = NQ_0716_BARS[10]
    current_row = {"value": nq_0624}
    original_paths = (
        entry_agent.STATE_PATH,
        entry_agent.PERSISTENCE_STATE_PATH,
        entry_agent.EXECUTOR_STATE_PATH,
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH,
        entry_agent.RITHMIC_RECENT_BARS_PATH,
        tv_context_server.ENTRY_DECISIONS_LOG_PATH,
        tv_context_server.ENTRY_REASONING_DIR,
    )

    def snapshot_for_symbol(symbol="NQ"):
        root = str(symbol).upper()
        snapshot = market_snapshot(current_row["value"])
        snapshot["symbol"] = root
        snapshot["normalized_symbol"] = root
        return snapshot

    def context_for_symbol(symbol="NQ"):
        root = str(symbol).upper()
        context = nq_context()
        context["normalized_symbol"] = root
        context["symbol"] = "CME_MINI:NQ1!" if root == "NQ" else "CBOT_MINI:YM1!"
        return context

    def atr_for_symbol(symbol="NQ"):
        root = str(symbol).upper()
        timestamp = current_row["value"][0]
        record = copy.deepcopy(canonical_recent_bar_record()["canonical_atr"])
        record["symbol_root"] = root
        record["contract_symbol"] = "NQU6" if root == "NQ" else "YMU6"
        record["candle_minute"] = timestamp
        record["last_included_bar"] = timestamp
        return record

    def forbidden(name):
        def fail(*_args, **_kwargs):
            raise AssertionError(f"status route reached forbidden mutation path: {name}")
        return fail

    try:
        entry_agent.STATE_PATH = tmp_path / "entry_agent_state.json"
        entry_agent.PERSISTENCE_STATE_PATH = tmp_path / "persistence_state.json"
        entry_agent.EXECUTOR_STATE_PATH = tmp_path / "executor_state.json"
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = tmp_path / "rithmic_atr_snapshot.json"
        entry_agent.RITHMIC_RECENT_BARS_PATH = tmp_path / "rithmic_recent_bars.json"
        tv_context_server.ENTRY_DECISIONS_LOG_PATH = tmp_path / "entry_decisions.jsonl"
        tv_context_server.ENTRY_REASONING_DIR = tmp_path / "reasoning"
        atr_authority_bytes = b'{"authority":"atr-rma-sentinel","completed_bars":29}\n'
        recent_bar_bytes = b'{"authority":"recent-bars-sentinel","completed_bars":29}\n'
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH.write_bytes(atr_authority_bytes)
        entry_agent.RITHMIC_RECENT_BARS_PATH.write_bytes(recent_bar_bytes)

        with (
            patch.object(entry_agent, "get_latest_market_snapshot", side_effect=snapshot_for_symbol),
            patch.object(entry_agent, "load_raw_tv_context", side_effect=context_for_symbol),
            patch.object(entry_agent, "load_tv_context", side_effect=context_for_symbol),
            patch.object(entry_agent, "recent_closed_bars", return_value=[]),
            patch.object(entry_agent, "load_rithmic_atr_snapshot", side_effect=atr_for_symbol),
            patch.object(entry_agent, "load_rithmic_atr_observation", side_effect=atr_for_symbol),
            patch.object(entry_agent, "append_entry_agent_audit_row", return_value=None),
        ):
            # This is the authorized completed-candle mutation path.  It commits
            # the 06:24 running extreme before status is allowed to read it.
            entry_agent.run_once("NQ", persist=True)
            entry_agent.run_once("YM", persist=True)

            committed = entry_agent.load_entry_state()
            assert committed["state_by_symbol"]["NQ"]["pre_open_observed_extreme"]["price"] == 29488.50
            state_before = entry_agent.STATE_PATH.read_bytes()
            decision_cache_before = copy.deepcopy(tv_context_server.ENTRY_DECISION_LAST_LOGGED)
            reasoning_cache_before = copy.deepcopy(tv_context_server.ENTRY_REASONING_LAST_LOGGED)
            context_cache_before = copy.deepcopy(tv_context_server.LATEST_TV_CONTEXT_BY_SYMBOL)
            real_run_once = entry_agent.run_once
            projection_calls = []

            def traced_projection(symbol="NQ", persist=True):
                projection_calls.append((str(symbol).upper(), persist))
                assert persist is False
                return real_run_once(symbol, persist=persist)

            with (
                patch.object(entry_agent, "run_once", side_effect=traced_projection),
                patch.object(entry_agent, "persist_pre_open_observed_extreme", side_effect=forbidden("persist_pre_open_observed_extreme")),
                patch.object(entry_agent, "persist_state", side_effect=forbidden("persist_state")),
                patch.object(entry_agent, "record_consumed_entry_setup", side_effect=forbidden("record_consumed_entry_setup")),
                patch.object(entry_agent, "record_submitted_entry_setup", side_effect=forbidden("record_submitted_entry_setup")),
                patch.object(entry_agent, "persist_confirmed_rejection_anchor_from_authoritative_snapshot", side_effect=forbidden("persist_confirmed_rejection_anchor_from_authoritative_snapshot")),
                patch.object(entry_agent, "append_entry_agent_audit_row", side_effect=forbidden("append_entry_agent_audit_row")),
                patch.object(entry_agent, "log_step2_owner_diagnostic", side_effect=forbidden("log_step2_owner_diagnostic")),
                patch.object(tv_context_server, "stored_context_by_root", return_value={
                    "NQ": context_for_symbol("NQ"),
                    "YM": context_for_symbol("YM"),
                }),
                patch.object(tv_context_server, "append_entry_decision_log", side_effect=forbidden("append_entry_decision_log")),
                patch.object(tv_context_server, "append_entry_reasoning_log", side_effect=forbidden("append_entry_reasoning_log")),
            ):
                with tv_context_server.app.test_client() as client:
                    responses = [client.get("/entry/status?symbols=NQ,YM") for _ in range(3)]
                    current_row["value"] = nq_0625
                    responses.append(client.get("/entry/status?symbols=NQ,YM"))
                    debug_response = client.get("/debug/entry-liquidity?symbols=NQ,YM")
                with ThreadPoolExecutor(max_workers=8) as executor:
                    concurrent_responses = list(
                        executor.map(
                            lambda _index: tv_context_server.app.test_client().get(
                                "/entry/status?symbols=NQ,YM"
                            ),
                            range(20),
                        )
                    )

            nq_statuses = [response.get_json()["symbols"][0] for response in responses]
            ym_statuses = [response.get_json()["symbols"][1] for response in responses]
            assert all(response.status_code == 200 for response in responses)
            assert [status["rejection_boundary"] for status in nq_statuses] == [29488.50] * 4
            assert nq_statuses[-1]["pre_open_observed_extreme"]["price"] == 29488.50
            assert nq_statuses[-1]["rejection_lane"]["rejection_boundary"] is None
            assert nq_statuses[-1]["active_liquidity_name"] == "PMH"
            assert nq_statuses[-1]["liquidity_level_price"] == 29457.25
            assert len(ym_statuses) == 4
            assert debug_response.status_code == 200
            assert all(response.status_code == 200 for response in concurrent_responses)
            assert entry_agent.STATE_PATH.read_bytes() == state_before
            assert entry_agent.RITHMIC_ATR_SNAPSHOT_PATH.read_bytes() == atr_authority_bytes
            assert entry_agent.RITHMIC_RECENT_BARS_PATH.read_bytes() == recent_bar_bytes
            assert tv_context_server.ENTRY_DECISION_LAST_LOGGED == decision_cache_before
            assert tv_context_server.ENTRY_REASONING_LAST_LOGGED == reasoning_cache_before
            assert tv_context_server.LATEST_TV_CONTEXT_BY_SYMBOL == context_cache_before
            assert projection_calls.count(("NQ", False)) == 25
            assert projection_calls.count(("YM", False)) == 25
            assert not tv_context_server.ENTRY_DECISIONS_LOG_PATH.exists()
            assert not tv_context_server.ENTRY_REASONING_DIR.exists()
    finally:
        (
            entry_agent.STATE_PATH,
            entry_agent.PERSISTENCE_STATE_PATH,
            entry_agent.EXECUTOR_STATE_PATH,
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH,
            entry_agent.RITHMIC_RECENT_BARS_PATH,
            tv_context_server.ENTRY_DECISIONS_LOG_PATH,
            tv_context_server.ENTRY_REASONING_DIR,
        ) = original_paths


def test_0641_status_poll_cannot_create_steps_or_rotate_owner_but_authorized_candle_can(tmp_path):
    """Separate the 06:41 read projection from the authorized candle transaction."""
    import tv_context_server

    current_index = {"value": 0}
    replay_rows = []
    original_paths = (
        entry_agent.STATE_PATH,
        entry_agent.PERSISTENCE_STATE_PATH,
        entry_agent.EXECUTOR_STATE_PATH,
    )

    def snapshot_for_symbol(symbol="NQ"):
        root = str(symbol).upper()
        snapshot = market_snapshot(NQ_0716_BARS[current_index["value"]])
        snapshot["symbol"] = root
        snapshot["normalized_symbol"] = root
        return snapshot

    def atr_for_symbol(symbol="NQ"):
        root = str(symbol).upper()
        timestamp = NQ_0716_BARS[current_index["value"]][0]
        record = copy.deepcopy(canonical_recent_bar_record()["canonical_atr"])
        record["symbol_root"] = root
        record["contract_symbol"] = "NQU6" if root == "NQ" else "YMU6"
        record["candle_minute"] = timestamp
        record["last_included_bar"] = timestamp
        return record

    def forbidden(name):
        def fail(*_args, **_kwargs):
            raise AssertionError(f"status poll reached forbidden lifecycle path: {name}")
        return fail

    try:
        entry_agent.STATE_PATH = tmp_path / "entry_agent_state.json"
        entry_agent.PERSISTENCE_STATE_PATH = tmp_path / "persistence_state.json"
        entry_agent.EXECUTOR_STATE_PATH = tmp_path / "executor_state.json"
        with (
            patch.object(entry_agent, "get_latest_market_snapshot", side_effect=snapshot_for_symbol),
            patch.object(entry_agent, "load_raw_tv_context", return_value=nq_context()),
            patch.object(entry_agent, "load_tv_context", return_value=nq_context()),
            patch.object(entry_agent, "recent_closed_bars", side_effect=lambda _symbol="NQ", limit=120: list(replay_rows)[-limit:]),
            patch.object(entry_agent, "load_rithmic_atr_snapshot", side_effect=atr_for_symbol),
            patch.object(entry_agent, "load_rithmic_atr_observation", side_effect=atr_for_symbol),
            patch.object(entry_agent, "append_entry_agent_audit_row", return_value=None),
            patch.object(tv_context_server, "stored_context_by_root", return_value={"NQ": nq_context()}),
        ):
            # Authoritatively process through 06:40, leaving the high-side
            # lifecycle committed before the low-side 06:41 close is observed.
            for index, row in enumerate(NQ_0716_BARS[:-1]):
                current_index["value"] = index
                replay_rows.append({
                    "timestamp": row[0],
                    "open": row[1],
                    "high": row[2],
                    "low": row[3],
                    "close": row[4],
                })
                entry_agent.run_once("NQ", persist=True)

            before_state = entry_agent.load_entry_state()
            before_symbol = copy.deepcopy(before_state["state_by_symbol"]["NQ"])
            before_bytes = entry_agent.STATE_PATH.read_bytes()
            before_owner = before_symbol["step2_locked_owner"]["active_liquidity"]
            assert before_owner["side"] == "upper"

            current_index["value"] = len(NQ_0716_BARS) - 1
            real_run_once = entry_agent.run_once
            projection_calls = []

            def traced_projection(symbol="NQ", persist=True):
                projection_calls.append((str(symbol).upper(), persist))
                assert persist is False
                return real_run_once(symbol, persist=persist)

            with (
                patch.object(entry_agent, "run_once", side_effect=traced_projection),
                patch.object(entry_agent, "persist_pre_open_observed_extreme", side_effect=forbidden("persist_pre_open_observed_extreme")),
                patch.object(entry_agent, "persist_state", side_effect=forbidden("persist_state")),
                patch.object(entry_agent, "record_consumed_entry_setup", side_effect=forbidden("record_consumed_entry_setup")),
                patch.object(entry_agent, "persist_confirmed_rejection_anchor_from_authoritative_snapshot", side_effect=forbidden("persist_confirmed_rejection_anchor_from_authoritative_snapshot")),
                patch.object(tv_context_server, "append_entry_decision_log", side_effect=forbidden("append_entry_decision_log")),
                patch.object(tv_context_server, "append_entry_reasoning_log", side_effect=forbidden("append_entry_reasoning_log")),
            ):
                with tv_context_server.app.test_client() as client:
                    responses = [client.get("/entry/status?symbols=NQ") for _ in range(12)]

            assert all(response.status_code == 200 for response in responses)
            assert projection_calls == [("NQ", False)] * 12
            assert entry_agent.STATE_PATH.read_bytes() == before_bytes
            after_polls = entry_agent.load_entry_state()["state_by_symbol"]["NQ"]
            assert after_polls["step_2_1a"] == before_symbol["step_2_1a"]
            assert after_polls["step4"] == before_symbol["step4"]
            assert after_polls["step2_locked_owner"] == before_symbol["step2_locked_owner"]
            assert after_polls.get("step_2_1a_candle_index") == before_symbol.get("step_2_1a_candle_index")
            assert after_polls.get("latest_bar_time") == before_symbol.get("latest_bar_time")

            # The same completed 06:41 candle is an authorized lifecycle event
            # only when processed by the mutation transaction.
            final_row = NQ_0716_BARS[-1]
            replay_rows.append({
                "timestamp": final_row[0],
                "open": final_row[1],
                "high": final_row[2],
                "low": final_row[3],
                "close": final_row[4],
            })
            entry_agent.run_once("NQ", persist=True)
            after_authorized = entry_agent.load_entry_state()["state_by_symbol"]["NQ"]
            assert entry_agent.STATE_PATH.read_bytes() != before_bytes
            assert after_authorized["step2_locked_owner"]["active_liquidity"]["side"] == "lower"
    finally:
        (
            entry_agent.STATE_PATH,
            entry_agent.PERSISTENCE_STATE_PATH,
            entry_agent.EXECUTOR_STATE_PATH,
        ) = original_paths


def test_status_polling_cannot_extend_canonical_preopen_wick_but_authorized_candle_can(tmp_path):
    """A farther wick may appear in a view but commits only as a candle event."""
    current_row = {"value": NQ_0716_BARS[8]}  # 06:23 high 29481.50
    original_paths = (
        entry_agent.STATE_PATH,
        entry_agent.PERSISTENCE_STATE_PATH,
        entry_agent.EXECUTOR_STATE_PATH,
    )

    def snapshot_for_symbol(_symbol="NQ"):
        return market_snapshot(current_row["value"])

    def forbidden(name):
        def fail(*_args, **_kwargs):
            raise AssertionError(f"projection reached forbidden writer: {name}")
        return fail

    try:
        entry_agent.STATE_PATH = tmp_path / "entry_agent_state.json"
        entry_agent.PERSISTENCE_STATE_PATH = tmp_path / "persistence_state.json"
        entry_agent.EXECUTOR_STATE_PATH = tmp_path / "executor_state.json"
        with (
            patch.object(entry_agent, "get_latest_market_snapshot", side_effect=snapshot_for_symbol),
            patch.object(entry_agent, "load_raw_tv_context", return_value=nq_context()),
            patch.object(entry_agent, "load_tv_context", return_value=nq_context()),
            patch.object(entry_agent, "recent_closed_bars", return_value=[]),
            patch.object(entry_agent, "load_rithmic_atr_snapshot", return_value=None),
            patch.object(entry_agent, "load_rithmic_atr_observation", return_value=None),
            patch.object(entry_agent, "append_entry_agent_audit_row", return_value=None),
        ):
            entry_agent.run_once("NQ", persist=True)
            state_0623 = entry_agent.load_entry_state()["state_by_symbol"]["NQ"]
            assert state_0623["pre_open_observed_extreme"]["price"] == 29481.50
            before_bytes = entry_agent.STATE_PATH.read_bytes()

            current_row["value"] = NQ_0716_BARS[9]  # 06:24 high 29488.50
            with (
                patch.object(entry_agent, "persist_pre_open_observed_extreme", side_effect=forbidden("persist_pre_open_observed_extreme")),
                patch.object(entry_agent, "persist_state", side_effect=forbidden("persist_state")),
                patch.object(entry_agent, "persist_confirmed_rejection_anchor_from_authoritative_snapshot", side_effect=forbidden("persist_confirmed_rejection_anchor_from_authoritative_snapshot")),
                patch.object(entry_agent, "record_consumed_entry_setup", side_effect=forbidden("record_consumed_entry_setup")),
            ):
                projected = [entry_agent.build_entry_status("NQ") for _ in range(10)]

            assert all(status["rejection_boundary"] == 29488.50 for status in projected)
            assert entry_agent.STATE_PATH.read_bytes() == before_bytes
            assert entry_agent.load_entry_state()["state_by_symbol"]["NQ"]["pre_open_observed_extreme"]["price"] == 29481.50

            entry_agent.run_once("NQ", persist=True)
            committed = entry_agent.load_entry_state()["state_by_symbol"]["NQ"]
            assert committed["pre_open_observed_extreme"]["price"] == 29488.50
            assert entry_agent.STATE_PATH.read_bytes() != before_bytes
    finally:
        (
            entry_agent.STATE_PATH,
            entry_agent.PERSISTENCE_STATE_PATH,
            entry_agent.EXECUTOR_STATE_PATH,
        ) = original_paths


def test_concurrent_nq_projection_refresh_preserves_running_extreme_and_ym_state(tmp_path):
    original_state = entry_agent.STATE_PATH
    entry_agent.STATE_PATH = tmp_path / "entry_agent_state.json"
    nq_snapshot = {
        "observation_reset_session_date": "2026-07-16",
        "observation_reset_bar_time": "2026-07-16T13:24:00Z",
        "observation_reset_at": "2026-07-16T13:15:00Z",
    }
    ym_snapshot = {
        "observation_reset_session_date": "2026-07-16",
        "observation_reset_bar_time": "2026-07-16T13:24:00Z",
        "observation_reset_at": "2026-07-16T13:15:00Z",
    }
    nq_extremes = [29488.50, 29484.00, 29463.25] * 20
    ym_extremes = [52010.0, 52012.0, 52011.0] * 20
    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = []
            for price in nq_extremes:
                futures.append(
                    executor.submit(
                        entry_agent.persist_pre_open_observed_extreme,
                        nq_snapshot,
                        "NQ",
                        {"side": "upper", "price": price},
                    )
                )
            for price in ym_extremes:
                futures.append(
                    executor.submit(
                        entry_agent.persist_pre_open_observed_extreme,
                        ym_snapshot,
                        "YM",
                        {"side": "upper", "price": price},
                    )
                )
            for future in futures:
                future.result()
        state = entry_agent.load_entry_state()["state_by_symbol"]
    finally:
        entry_agent.STATE_PATH = original_state
    assert state["NQ"]["pre_open_observed_extreme"]["price"] == 29488.50
    assert state["YM"]["pre_open_observed_extreme"]["price"] == 52012.0


def test_full_state_projection_write_cannot_retract_nq_pre_open_extreme(tmp_path):
    original_state = entry_agent.STATE_PATH
    entry_agent.STATE_PATH = tmp_path / "entry_agent_state.json"

    def projection_snapshot(price):
        return {
            "symbol": "NQ",
            "normalized_symbol": "NQ",
            "requested_symbol": "NQ",
            "latest_price": price,
            "latest_bar_time": "2026-07-16T13:25:00Z",
            "pre_open_observed_extreme": {
                "side": "upper",
                "price": price,
                "source_level": "PMH",
                "locked_boundary_price": 29457.25,
                "session_date": "2026-07-16",
            },
            "observation_reset_session_date": "2026-07-16",
            "observation_reset_bar_time": "2026-07-16T13:15:00Z",
            "step_2_1a": {},
            "step4": {},
            "step5": {},
            "step6": {},
        }

    try:
        prices = [29488.50, 29484.00, 29463.25] * 20
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(entry_agent.persist_state, projection_snapshot(price)) for price in prices]
            for future in futures:
                future.result()
        state = entry_agent.load_entry_state()["state_by_symbol"]["NQ"]
    finally:
        entry_agent.STATE_PATH = original_state

    assert state["pre_open_observed_extreme"]["price"] == 29488.50


def test_tv_context_receipt_archives_exact_nested_ladder_and_derived_stack(tmp_path):
    import tv_context_server

    context = nq_context()
    context["liquidity_map"] = {
        "levels": [
            {"name": name, **details}
            for name, details in context["levels"].items()
        ],
        "stacks": [],
    }
    normalized = tv_context_server.public_liquidity_map(context)
    low_stack = next(stack for stack in normalized["stacks"] if stack["name"] == "LOW 1")
    assert set(low_stack["components"]) == {"PML", "LL", "ONL"}
    assert low_stack["close_boundary"] == 29363.50
    assert low_stack["extreme_boundary"] == 29361.00

    original_path = tv_context_server.TV_CONTEXT_EVENTS_PATH
    try:
        tv_context_server.TV_CONTEXT_EVENTS_PATH = tmp_path / "tv_context_events.jsonl"
        tv_context_server.append_context_event(context, "127.0.0.1", received_payload=context)
        event = __import__("json").loads(tv_context_server.TV_CONTEXT_EVENTS_PATH.read_text(encoding="utf-8"))
    finally:
        tv_context_server.TV_CONTEXT_EVENTS_PATH = original_path
    assert event["schema_version"] == "tv_context_receipt_v2"
    assert event["levels"]["PML"]["stack_group"] == "LOW 1"
    assert event["received_payload"]["levels"]["ONL"]["price"] == 29361.00
    assert event["liquidity_map"]["stacks"][0]
