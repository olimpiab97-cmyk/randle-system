"""R4E byte identity, recovery cadence, failure, and downstream authority gates."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parent
ENTRY_AGENT_DIR = ROOT / "EntryAgent"
for candidate in (ROOT, ENTRY_AGENT_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import entry_agent
import tv_context_server as receiver
from test_operational_a_cadence import CADENCE, END_MINUTE, LOCK_MINUTE, SenderState
from test_operational_a_ladder_contract import bind_manager_to_receiver, bind_receiver_to_temp
from test_operational_a_r4c_overlapping_stacks import canonical_payload
from tests.pine_runtime_string_semantics import production_pine_json_dumps


PINE = ROOT / "TradingView" / "indicators" / "Randle_AI_Level_Map_Helper.pine"
STARTS = (376, 379, 380, 381, 384, 386, 404, 697)
EXPECTED_DELAYS = (4, 1, 0, 4, 1, 4, 1, 3)
RECOVERY_VECTORS = json.loads(
    (ROOT / "tests" / "fixtures" / "operational_a" / "r4e_recovery_vectors.json").read_text(encoding="utf-8")
)


def corrected_payload(symbol: str = "YM1!", session_date: str = "2026-08-10") -> dict[str, object]:
    payload, _semantics, _stacks = canonical_payload(
        {
            "PMH": 54125,
            "LH": 54152,
            "ONH": 54170,
            "YH": 54199,
            "PML": 53900,
            "LL": 53873,
            "ONL": 53855,
            "YL": 53826,
        },
        reference=54000,
        threshold=69,
        symbol=symbol,
    )
    payload["session_date"] = session_date
    payload["timestamp"] = f"{session_date}T13:15:00Z"
    payload["is_premarket_end"] = True
    payload["is_recurring_update"] = False
    payload["midpoints"] = {"ONH_ONL": 54012.5}
    payload["exhaustion_boundaries"] = {
        "ONH_ONL": {"side": "high", "mid_50": 54012.5, "remaining_25": 53933.75}
    }
    return payload


def pine_payload_bytes(payload: dict[str, object]) -> bytes:
    return production_pine_json_dumps(payload, PINE.read_text(encoding="utf-8")).encode("utf-8")


def schedule() -> list[int]:
    return [LOCK_MINUTE, *range(LOCK_MINUTE + CADENCE, END_MINUTE + 1, CADENCE)]


def next_attempt(start_minute: int) -> int:
    return min(item for item in schedule() if item >= start_minute)


def bind(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, calls: list[dict] | None = None):
    bind_receiver_to_temp(monkeypatch, tmp_path)
    return bind_manager_to_receiver(monkeypatch, tmp_path, calls)


def assert_bridges(context: dict[str, object]) -> None:
    levels = context["levels"]
    assert levels["PMH"]["stack_groups"] == ["HIGH 1"]
    assert levels["LH"]["stack_groups"] == ["HIGH 1"]
    assert levels["ONH"]["stack_groups"] == ["HIGH 1", "HIGH 2"]
    assert levels["YH"]["stack_groups"] == ["HIGH 2"]
    assert levels["PML"]["stack_groups"] == ["LOW 1"]
    assert levels["LL"]["stack_groups"] == ["LOW 1"]
    assert levels["ONL"]["stack_groups"] == ["LOW 1", "LOW 2"]
    assert levels["YL"]["stack_groups"] == ["LOW 2"]


def test_exact_payload_bytes_and_sha_equal_for_94_attempts() -> None:
    frozen = pine_payload_bytes(corrected_payload())
    attempts = [frozen for _minute in schedule()]
    assert len(attempts) == 94
    assert all(item == attempts[0] for item in attempts)
    hashes = [hashlib.sha256(item).hexdigest() for item in attempts]
    assert len(set(hashes)) == 1
    assert hashes[0] == hashlib.sha256(attempts[0]).hexdigest()


def test_mutable_telemetry_cannot_change_frozen_recovery_bytes() -> None:
    payload = corrected_payload()
    frozen = pine_payload_bytes(payload)
    mutable_fields = (
        "timestamp",
        "is_premarket_end",
        "is_recurring_update",
        "atr_1m_14",
        "daily_atr14",
        "pm_atr_pct",
        "daily_range_pct",
    )
    live = copy.deepcopy(payload)
    for index, field in enumerate(mutable_fields, start=1):
        live[field] = index * 999
    assert pine_payload_bytes(live) != frozen
    replay_attempts = [frozen] * 10
    assert all(item == frozen for item in replay_attempts)


def test_ten_successive_replays_have_one_identity_and_duplicate_noop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict] = []
    manager = bind(monkeypatch, tmp_path, calls)
    payload = corrected_payload()
    client = manager.app.test_client()
    responses = [client.post("/webhook/tv-context?token=public-test-token", json=payload) for _ in range(11)]
    bodies = [response.get_json() for response in responses]
    assert responses[0].status_code == 200
    assert bodies[0]["delivery_state"] == "DELIVERED"
    assert all(response.status_code == 200 for response in responses[1:])
    assert all(body["delivery_state"] == "DUPLICATE_NOOP" for body in bodies[1:])
    assert len({body["message_identity"] for body in bodies}) == 1
    assert len(calls) == 1
    assert len(list(Path(os.environ["TV_CONTEXT_SPOOL_DIR"]).glob("*.json"))) == 1


def test_duplicate_replays_do_not_mutate_ledger_normalized_state_or_bridges(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager = bind(monkeypatch, tmp_path)
    payload = corrected_payload()
    client = manager.app.test_client()
    first = client.post("/webhook/tv-context?token=public-test-token", json=payload)
    assert first.status_code == 200
    context_before = receiver.TV_CONTEXT_BY_SYMBOL_PATH.read_bytes()
    ledger_path = Path(os.environ["TV_CONTEXT_ACCEPTANCE_LEDGER_PATH"])
    ledger_before = ledger_path.read_bytes()
    for _ in range(20):
        duplicate = client.post("/webhook/tv-context?token=public-test-token", json=payload)
        assert duplicate.get_json()["delivery_state"] == "DUPLICATE_NOOP"
    assert receiver.TV_CONTEXT_BY_SYMBOL_PATH.read_bytes() == context_before
    assert ledger_path.read_bytes() == ledger_before
    stored = json.loads(context_before)["symbols"]["YM"]
    assert_bridges(stored)
    assert entry_agent.tv_context_actionable_for_session(stored, "2026-08-10") is True


@pytest.mark.parametrize(("start_minute", "expected_delay"), zip(STARTS, EXPECTED_DELAYS))
def test_offline_then_online_first_copy_recovers_within_5_minutes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    start_minute: int,
    expected_delay: int,
) -> None:
    manager = bind(monkeypatch, tmp_path)
    payload = corrected_payload()
    assert entry_agent.tv_context_actionable_for_session(None, "2026-08-10") is False
    recovery_minute = next_attempt(start_minute)
    assert recovery_minute - start_minute == expected_delay <= CADENCE
    accepted = manager.app.test_client().post("/webhook/tv-context?token=public-test-token", json=payload)
    assert accepted.status_code == 200 and accepted.get_json()["delivery_state"] == "DELIVERED"
    stored = json.loads(receiver.TV_CONTEXT_BY_SYMBOL_PATH.read_text(encoding="utf-8"))["symbols"]["YM"]
    assert entry_agent.tv_context_actionable_for_session(stored, "2026-08-10") is True
    later = manager.app.test_client().post("/webhook/tv-context?token=public-test-token", json=payload)
    assert later.get_json()["delivery_state"] == "DUPLICATE_NOOP"


def test_late_alert_creation_catchup_then_aligned_duplicate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sender = SenderState()
    assert sender.bar(trading_day="2026-08-10", minute=375, realtime=False) is None
    catchup = sender.bar(trading_day="2026-08-10", minute=382)
    assert catchup is not None
    assert sender.bar(trading_day="2026-08-10", minute=383) is None
    assert sender.bar(trading_day="2026-08-10", minute=385) == catchup
    manager = bind(monkeypatch, tmp_path)
    payload = corrected_payload()
    first = manager.app.test_client().post("/webhook/tv-context?token=public-test-token", json=payload)
    replay = manager.app.test_client().post("/webhook/tv-context?token=public-test-token", json=payload)
    assert first.get_json()["delivery_state"] == "DELIVERED"
    assert replay.get_json()["delivery_state"] == "DUPLICATE_NOOP"


def test_same_day_restart_reads_current_identity_without_waiting_for_replay(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager = bind(monkeypatch, tmp_path)
    payload = corrected_payload()
    first = manager.app.test_client().post("/webhook/tv-context?token=public-test-token", json=payload)
    identity = first.get_json()["message_identity"]
    receiver.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
    receiver.TV_LADDER_VALIDATION_BY_SYMBOL.clear()
    restored = receiver.persisted_canonical_acceptance("YM")
    assert restored is not None
    assert restored["message_identity"] == identity
    assert restored["session_date"] == "2026-08-10"


def test_prior_none_and_pending_readiness_are_false() -> None:
    payload = corrected_payload()
    context, error = receiver.build_context(payload)
    assert error is None and context is not None
    assert entry_agent.tv_context_actionable_for_session(context, "2026-08-10") is True
    assert entry_agent.tv_context_actionable_for_session(context, "2026-08-11") is False
    assert entry_agent.tv_context_actionable_for_session(None, "2026-08-10") is False
    recovery_pending = None
    assert entry_agent.tv_context_actionable_for_session(recovery_pending, "2026-08-10") is False


def test_next_day_identity_differs_and_prior_day_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager = bind(monkeypatch, tmp_path)
    current = corrected_payload(session_date="2026-08-10")
    next_day = corrected_payload(session_date="2026-08-11")
    client = manager.app.test_client()
    first = client.post("/webhook/tv-context?token=public-test-token", json=current)
    second = client.post("/webhook/tv-context?token=public-test-token", json=next_day)
    stale = client.post("/webhook/tv-context?token=public-test-token", json=current)
    assert first.status_code == second.status_code == 200
    assert first.get_json()["message_identity"] != second.get_json()["message_identity"]
    assert stale.status_code == 200 and stale.get_json()["delivery_state"] == "DUPLICATE_NOOP"
    stored = json.loads(receiver.TV_CONTEXT_BY_SYMBOL_PATH.read_text(encoding="utf-8"))["symbols"]["YM"]
    assert stored["session_date"] == "2026-08-11"


def test_ym_nq_independent_snapshot_identity_and_storage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager = bind(monkeypatch, tmp_path)
    client = manager.app.test_client()
    ym = client.post("/webhook/tv-context?token=public-test-token", json=corrected_payload("YM1!"))
    nq = client.post("/webhook/tv-context?token=public-test-token", json=corrected_payload("NQ1!"))
    assert ym.status_code == nq.status_code == 200
    assert ym.get_json()["message_identity"] != nq.get_json()["message_identity"]
    stored = json.loads(receiver.TV_CONTEXT_BY_SYMBOL_PATH.read_text(encoding="utf-8"))["symbols"]
    assert set(stored) == {"YM", "NQ"}
    assert_bridges(stored["YM"])
    assert_bridges(stored["NQ"])


def test_failure_injection_all_ten_classes_fail_closed_or_recover(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict] = []
    manager = bind(monkeypatch, tmp_path, calls)
    client = manager.app.test_client()
    payload = corrected_payload()

    # 1-3: lock and multiple recovery packets can be lost before ingress; the
    # next reachable identical attempt is still accepted.
    offline_attempts = [375, 380, 385]
    assert len(offline_attempts) == 3 and not receiver.TV_CONTEXT_BY_SYMBOL_PATH.exists()
    accepted = client.post("/webhook/tv-context?token=public-test-token", json=payload)
    assert accepted.status_code == 200

    # 4: Entry unavailable after Trade Manager ingress remains durably pending.
    second_payload = corrected_payload("NQ1!")
    original_post = manager.requests.post
    monkeypatch.setattr(
        manager.requests,
        "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(requests.ConnectionError("isolated unavailable")),
    )
    pending = client.post("/webhook/tv-context?token=public-test-token", json=second_payload)
    assert pending.status_code == 202 and pending.get_json()["delivery_state"] == "PENDING"
    monkeypatch.setattr(manager.requests, "post", original_post)
    recovered = client.post("/webhook/tv-context?token=public-test-token", json=second_payload)
    assert recovered.status_code == 200 and recovered.get_json()["delivery_state"] == "DELIVERED"

    # 5: transport duplicate is a no-op.
    duplicate = client.post("/webhook/tv-context?token=public-test-token", json=payload)
    assert duplicate.get_json()["delivery_state"] == "DUPLICATE_NOOP"

    # 6: prior-day recovery cannot replace current authority.
    prior = corrected_payload(session_date="2026-08-09")
    stale = client.post("/webhook/tv-context?token=public-test-token", json=prior)
    assert stale.status_code == 409 and stale.get_json()["delivery_state"] == "REJECTED"

    # 7: altered bytes at the same timestamp are rejected downstream.
    altered = copy.deepcopy(payload)
    altered["levels"]["YH"]["price"] += 1
    next(row for row in altered["liquidity_map"]["levels"] if row["name"] == "YH")["price"] += 1
    conflict = client.post("/webhook/tv-context?token=public-test-token", json=altered)
    assert conflict.status_code == 409 and conflict.get_json()["delivery_state"] == "REJECTED"

    # 8: malformed canonical payload is rejected before spool.
    malformed = copy.deepcopy(payload)
    malformed["levels"].pop("YH")
    malformed["liquidity_map"]["levels"] = [
        row for row in malformed["liquidity_map"]["levels"] if row["name"] != "YH"
    ]
    assert client.post("/webhook/tv-context?token=public-test-token", json=malformed).status_code == 400

    # 9: wrong public credential never reaches downstream.
    assert client.post("/webhook/tv-context?token=wrong", json=payload).status_code == 401

    # 10: wrong internal relay credential is rejected by Entry Agent.
    wrong_internal = receiver.app.test_client().post(
        "/webhook/tv-context", json=payload, headers={"X-Randle-Relay-Token": "wrong"}
    )
    assert wrong_internal.status_code == 401


def test_source_has_no_security_or_python_scope_change() -> None:
    source = PINE.read_text(encoding="utf-8")
    assert "TV_WEBHOOK_INGRESS_TOKEN" not in source
    assert "TV_CONTEXT_INTERNAL_RELAY_TOKEN" not in source
    assert "alert(frozenCanonicalPayload, alert.freq_once_per_bar_close)" in source
    assert source.count("alert(frozenCanonicalPayload, alert.freq_once_per_bar_close)") == 1


@pytest.mark.parametrize("vector", RECOVERY_VECTORS, ids=lambda row: row["id"])
def test_r4e_five_recovery_end_to_end_vectors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, vector: dict[str, str]
) -> None:
    manager = bind(monkeypatch, tmp_path)
    client = manager.app.test_client()
    payload = corrected_payload()
    case = vector["case"]

    if case == "initial_lock_delivery":
        response = client.post("/webhook/tv-context?token=public-test-token", json=payload)
        assert response.status_code == 200 and response.get_json()["delivery_state"] == vector["expected"]
    elif case == "byte_identical_replay":
        assert client.post("/webhook/tv-context?token=public-test-token", json=payload).status_code == 200
        response = client.post("/webhook/tv-context?token=public-test-token", json=payload)
        assert response.get_json()["delivery_state"] == vector["expected"]
    elif case == "offline_at_lock_recovery":
        assert not receiver.TV_CONTEXT_BY_SYMBOL_PATH.exists()
        response = client.post("/webhook/tv-context?token=public-test-token", json=payload)
        assert response.status_code == 200 and response.get_json()["delivery_state"] == vector["expected"]
    elif case == "same_day_restart":
        accepted = client.post("/webhook/tv-context?token=public-test-token", json=payload)
        receiver.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
        restored = receiver.persisted_canonical_acceptance("YM")
        assert restored and restored["message_identity"] == accepted.get_json()["message_identity"]
        assert vector["expected"] == "RESTORED"
    elif case == "prior_day_rejection":
        assert client.post("/webhook/tv-context?token=public-test-token", json=payload).status_code == 200
        prior = corrected_payload(session_date="2026-08-09")
        response = client.post("/webhook/tv-context?token=public-test-token", json=prior)
        assert response.status_code == 409 and response.get_json()["delivery_state"] == vector["expected"]
    else:
        raise AssertionError(f"unaccounted vector: {vector}")
