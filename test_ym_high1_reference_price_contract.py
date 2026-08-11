"""Regression coverage for the YM HIGH 1 frozen-reference incident."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import pytest


ROOT = Path(__file__).resolve().parent
ENTRY_AGENT_DIR = ROOT / "EntryAgent"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ENTRY_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(ENTRY_AGENT_DIR))

import tv_context_server as server


FINALIZED_SENDER = ROOT / "REPLACE_ENTRY_AGENT_WEBHOOK_OVERLAPPING_FINALIZED_TABLE_STATE.pine"
LAUNCHER = ROOT / "launch_all.ps1"


def _level(price: float, stack_group: str = "NONE") -> dict[str, object]:
    memberships = [] if stack_group == "NONE" else [stack_group]
    return {
        "price": price,
        "status": "ACTIVE",
        "stack_group": stack_group,
        "stack_groups": memberships,
        "stack_display": stack_group,
    }


def captured_ym_payload(*, symbol: str = "YM1!", include_reference: bool = False) -> dict[str, object]:
    """Return the exact structurally relevant fields from the live rejected body."""
    stacks = [
        {
            "id": "HIGH 1",
            "side": "HIGH",
            "members": ["ONH", "YH"],
            "innermost_price": 52789,
            "outermost_price": 52835,
        },
        {
            "id": "LOW 1",
            "side": "LOW",
            "members": ["PML", "ONL"],
            "innermost_price": 52262,
            "outermost_price": 52262,
        },
    ]
    payload: dict[str, object] = {
        "source": "tradingview_level_helper",
        "version": "v14_overlapping_stack_smoke",
        "context_mode": "locked_levels_session_snapshot",
        "session_locked": True,
        "is_premarket_end": False,
        "is_recurring_update": False,
        "price_is_true_level": True,
        "display_offsets_applied_to_chart_only": True,
        "symbol": symbol,
        "time_zone": "America/Los_Angeles",
        "timeframe": "1",
        "daily_atr14": 586.2378162661,
        "stack_threshold": 59,
        "stack_threshold_pct": 10,
        "pm_atr_pct": 43.3271264583,
        "daily_range_pct": 28.1455742741,
        "levels": {
            "PMH": _level(52516),
            "PML": _level(52262, "LOW 1"),
            "LH": {**_level(52574), "status": "INACTIVE"},
            "LL": {**_level(52368), "status": "INACTIVE"},
            "ONH": _level(52789, "HIGH 1"),
            "ONL": _level(52262, "LOW 1"),
            "YH": _level(52835, "HIGH 1"),
            "YL": _level(52174),
        },
        "stacks": copy.deepcopy(stacks),
        "liquidity_map": {"stacks": copy.deepcopy(stacks)},
        "midpoints": {"PMH_HIGH 1": 52675.5, "LOW 1_YL": 52218},
        "exhaustion_boundaries": {},
    }
    if include_reference:
        # Synthetic verification value only: below both HIGH 1 members and above LOW 1.
        payload["session_lock_price"] = 52500
    return payload


def test_finalized_sender_serializes_the_existing_frozen_reference_authority() -> None:
    source = FINALIZED_SENDER.read_text(encoding="utf-8")
    field = '+ "\\\"session_lock_price\\\":" + f_json_num(sessionLockPrice_eff) + ","'

    assert source.count(field) == 1
    assert source.index(field) < source.index("+ levelsJson")
    assert '0 => yhStackGroup' in source
    assert "payloadExplicitStackObjectJson" in source
    assert '"version":"v14_overlapping_stack_smoke"' not in source  # Pine source escapes JSON quotes.
    assert '\\"version\\":\\"v14_overlapping_stack_smoke\\"' in source


@pytest.mark.parametrize("symbol", ["YM1!", "NQ1!"])
def test_prior_rth_stack_without_frozen_reference_fails_identically_for_nq_and_ym(symbol: str) -> None:
    context, error = server.build_context(captured_ym_payload(symbol=symbol))

    assert context is None
    assert error == {
        "error": "a frozen market reference is required to validate YH in HIGH 1",
        "code": "STACK_REFERENCE_PRICE_MISSING",
        "stack_group": "HIGH 1",
        "level": "YH",
    }


@pytest.mark.parametrize("symbol", ["YM1!", "NQ1!"])
def test_valid_high1_uses_separate_reference_authority_and_preserves_membership(symbol: str) -> None:
    payload = captured_ym_payload(symbol=symbol, include_reference=True)
    context, error = server.build_context(payload)

    assert error is None
    assert context is not None
    assert context["session_lock_price"] == 52500
    assert "session_lock_price" not in context["levels"]["YH"]
    assert context["levels"]["YH"]["stack_group"] == "HIGH 1"
    assert context["liquidity_map"]["stacks"][0]["members"] == ["ONH", "YH"]
    assert 52835 - 52789 <= context["stack_threshold"]


def test_unstacked_yh_does_not_require_a_reference() -> None:
    payload = captured_ym_payload()
    payload["levels"]["ONH"] = _level(52789)
    payload["levels"]["YH"] = _level(52835)
    payload["stacks"] = payload["stacks"][1:]
    payload["liquidity_map"] = {"stacks": copy.deepcopy(payload["stacks"])}

    context, error = server.build_context(payload)

    assert error is None
    assert context is not None
    assert context["levels"]["YH"]["stack_group"] == "NONE"


def test_stale_persisted_context_cannot_contaminate_premerge_rejection(tmp_path: Path) -> None:
    stale_store_path = tmp_path / "tv_context_by_symbol.json"
    stale_context_path = tmp_path / "tv_context.json"
    stale_state_path = tmp_path / "entry_agent_state.json"
    receipt_path = tmp_path / "tv_context_events.jsonl"
    stale_bytes = json.dumps(
        {
            "symbols": {
                "YM": {
                    "session_date": "2026-07-16",
                    "levels": {"YH": _level(53088, "HIGH 1")},
                }
            }
        },
        separators=(",", ":"),
    ).encode()
    for path in (stale_store_path, stale_context_path, stale_state_path):
        path.write_bytes(stale_bytes)
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (stale_store_path, stale_context_path, stale_state_path)}

    with (
        mock.patch.object(server, "TV_CONTEXT_BY_SYMBOL_PATH", stale_store_path),
        mock.patch.object(server, "TV_CONTEXT_PATH", stale_context_path),
        mock.patch.object(server, "ENTRY_AGENT_STATE_PATH", stale_state_path),
        mock.patch.object(server, "TV_CONTEXT_EVENTS_PATH", receipt_path),
        mock.patch.object(server, "stored_context_by_root", side_effect=AssertionError("stale state was consulted")),
        mock.patch.object(server, "safe_write_json", side_effect=AssertionError("authority write attempted")),
        mock.patch.object(server, "run_once", side_effect=AssertionError("lifecycle processing attempted")),
    ):
        response = server.app.test_client().post("/webhook/tv-context", json=captured_ym_payload())

    assert response.status_code == 400
    assert response.get_json()["code"] == "STACK_REFERENCE_PRICE_MISSING"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["acceptance_result"] == "rejected"
    assert receipt["received_payload"]["levels"]["YH"]["stack_group"] == "HIGH 1"
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before}
    assert after == before


def test_rehydration_rejects_a_lock_without_current_session_identity() -> None:
    current_session = datetime.now(ZoneInfo("America/Los_Angeles")).date()
    stale_session = (current_session - timedelta(days=1)).isoformat()
    payload = captured_ym_payload(include_reference=True)
    payload["session_date"] = stale_session
    session_lock = {"locked": True, "disabled": False, "tv_context": payload}
    context = {
        "last_tv_context_levels": copy.deepcopy(payload["levels"]),
        "last_tv_context_session_date": stale_session,
        "session_date": stale_session,
    }

    rebuilt, error = server._rebuild_frozen_lock_from_latest_tv("YM", context, session_lock)

    assert rebuilt is None
    assert error == {
        "error": "not_current_session",
        "current_session_date": current_session.isoformat(),
        "locked_session_date": stale_session,
    }


def test_launcher_keeps_exact_fail_closed_readiness_reason_and_dependency_result() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")

    assert '$status.service_status -eq "REHYDRATING"' in source
    assert '$status.rehydration_failures' in source
    assert 'entry_agent_fail_closed_rehydrating:{0}' in source
    assert 'Set-ComponentResult "TradingViewRelay" "FAILED" "dependency_failed:EntryAgent"' in source
