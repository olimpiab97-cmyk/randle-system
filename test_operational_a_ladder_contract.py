"""Operational A-R2 isolated contract, transport, replay, and failure tests."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
import requests


ROOT = Path(__file__).resolve().parent
ENTRY_AGENT = ROOT / "EntryAgent"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ENTRY_AGENT) not in sys.path:
    sys.path.insert(0, str(ENTRY_AGENT))

import entry_agent
import tv_context_server as receiver
from blueprint_rules import side_for_level_price
from tests.pine_runtime_string_semantics import production_pine_json_dumps


LEVELS = ("PMH", "PML", "LH", "LL", "ONH", "ONL", "YH", "YL")
FIXED_HIGH = {"PMH", "LH", "ONH"}
FIXED_LOW = {"PML", "LL", "ONL"}
ROAMING = {"YH", "YL"}
VECTORS_PATH = ROOT / "tests" / "fixtures" / "operational_a" / "operational_a_r1_test_vectors.json"
R4C_BRIDGE_VECTOR_PATH = ROOT / "tests" / "fixtures" / "operational_a" / "r4c_live_ym_bridge_vector.json"
PINE_PATH = ROOT / "TradingView" / "indicators" / "Randle_AI_Level_Map_Helper.pine"


def canonical_payload(
    levels: dict[str, float | None],
    *,
    timestamp: str = "2026-08-09T13:16:00Z",
    session_date: str = "2026-08-09",
    reference: float = 100.0,
) -> dict[str, object]:
    rows = []
    nested = {}
    for name in LEVELS:
        price = levels.get(name)
        status = "ACTIVE" if price is not None else "INACTIVE"
        detail = {
            "price": price,
            "status": status,
            "stack_group": "NONE",
            "stack_groups": [],
            "stack_display": "NONE",
        }
        nested[name] = copy.deepcopy(detail)
        rows.append({"name": name, **copy.deepcopy(detail)})
    return {
        "source": "tradingview_level_helper",
        "version": "v14_canonical_liquidity_sender",
        "context_mode": "locked_levels_session_snapshot",
        "timestamp": timestamp,
        "session_date": session_date,
        "session_locked": True,
        "locked": True,
        "is_premarket_end": False,
        "is_recurring_update": False,
        "price_is_true_level": True,
        "display_offsets_applied_to_chart_only": True,
        "symbol": "YM1!",
        "time_zone": "America/Los_Angeles",
        "timeframe": "1",
        "atr_1m_14": 2.0,
        "daily_atr14": 20.0,
        "stack_threshold": 0.5,
        "stack_threshold_pct": 10.0,
        "session_lock_price": reference,
        "pm_atr_pct": 30.0,
        "daily_range_pct": 70.0,
        "levels": nested,
        "stacks": [],
        "liquidity_map": {"levels": rows, "stacks": []},
        "midpoints": {},
        "exhaustion_boundaries": {},
    }


def ladder_projection(levels: dict[str, float | None], reference: float) -> dict[str, list[str]]:
    candidates = []
    for ordinal, name in enumerate(LEVELS):
        price = levels.get(name)
        side = side_for_level_price(name, price, reference)
        if price is not None and side in {"upper", "lower"}:
            candidates.append((name, float(price), side, ordinal))
    high = [row[0] for row in sorted((row for row in candidates if row[2] == "upper"), key=lambda row: (row[1], row[3]))]
    low = [row[0] for row in sorted((row for row in candidates if row[2] == "lower"), key=lambda row: (-row[1], row[3]))]
    return {"high_nearest_to_farthest": high, "low_nearest_to_farthest": low}


def load_manager(module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "Engines" / "trade_manager.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FlaskResponseAdapter:
    def __init__(self, response):
        self.status_code = response.status_code
        self.text = response.get_data(as_text=True)
        self._json = response.get_json()

    def json(self):
        return self._json


def bind_receiver_to_temp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime = tmp_path / "receiver"
    runtime.mkdir(parents=True, exist_ok=True)
    for name, filename in (
        ("LEVELS_PATH", "levels.json"),
        ("LEVELS_BY_SYMBOL_PATH", "levels_by_symbol.json"),
        ("TV_CONTEXT_PATH", "tv_context.json"),
        ("TV_CONTEXT_BY_SYMBOL_PATH", "tv_context_by_symbol.json"),
        ("TV_CONTEXT_EVENTS_PATH", "events.jsonl"),
        ("ENTRY_AGENT_STATE_PATH", "entry_state.json"),
    ):
        monkeypatch.setattr(receiver, name, runtime / filename)
    monkeypatch.setattr(receiver, "run_once", lambda *_args, **_kwargs: {})
    receiver.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
    receiver.TV_LADDER_VALIDATION_BY_SYMBOL.clear()
    monkeypatch.setenv("TV_CONTEXT_INTERNAL_RELAY_TOKEN", "internal-test-token")
    monkeypatch.setenv("TV_CONTEXT_ACCEPTANCE_LEDGER_PATH", str(runtime / "acceptance.json"))


def bind_manager_to_receiver(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, receiver_calls: list[dict] | None = None):
    monkeypatch.setenv("TV_WEBHOOK_INGRESS_TOKEN", "public-test-token")
    monkeypatch.setenv("TV_CONTEXT_INTERNAL_RELAY_TOKEN", "internal-test-token")
    monkeypatch.setenv("TV_CONTEXT_SPOOL_DIR", str(tmp_path / "spool"))
    monkeypatch.setenv("TV_CONTEXT_RELAY_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("TV_CONTEXT_RELAY_BACKOFF_SECONDS", "0")
    manager = load_manager(f"oa_r2_manager_{tmp_path.name}_{id(tmp_path)}")
    receiver_client = receiver.app.test_client()

    def local_post(_url, json=None, headers=None, timeout=None):
        if receiver_calls is not None:
            receiver_calls.append({"json": copy.deepcopy(json), "headers": dict(headers or {}), "timeout": timeout})
        response = receiver_client.post("/webhook/tv-context", json=json, headers=headers or {})
        return FlaskResponseAdapter(response)

    monkeypatch.setattr(manager.requests, "post", local_post)
    return manager


def test_final_pine_preserves_roaming_and_has_single_touch_contract() -> None:
    source = PINE_PATH.read_text(encoding="utf-8")
    assert source.startswith('//@version=6\nindicator("Randle AI - Level Map Helper v14 Canonical"')
    for name in ("YH", "YL"):
        assert f'addHighLevel("{name}"' in source
        assert f'addLowLevel ("{name}"' in source
    assert 'tableSide(float price) =>' in source
    assert 'sameLevel(price, close) ? "TOUCH"' in source
    assert 'if tableSide(pr) == "ABOVE"' in source
    assert 'if tableSide(pr) == "BELOW"' in source
    assert source.count('if tableSide(pr) == "TOUCH"') == 1
    assert "if pr >= close" not in source
    assert "if pr <= close" not in source
    assert "TV_WEBHOOK_INGRESS_TOKEN" not in source
    assert "v14_canonical_liquidity_sender" in source
    assert "table.new(position.top_right, 6, 15" in source
    assert all(f'+ "\\\"{name}\\\":" + payloadLevelJson' in source for name in LEVELS)
    assert source.count("+ payloadLiquidityMapLevelJson(") == 8


@pytest.mark.parametrize("name", LEVELS)
@pytest.mark.parametrize(("relation", "price"), (("above", 101.0), ("below", 99.0), ("equal", 100.0), ("null", None)))
def test_complete_32_placement_matrix(name: str, relation: str, price: float | None) -> None:
    side = side_for_level_price(name, price, 100.0)
    if relation == "null":
        expected = None
    elif relation == "equal":
        expected = "touch"
    elif name in FIXED_HIGH:
        expected = "upper" if relation == "above" else None
    elif name in FIXED_LOW:
        expected = "lower" if relation == "below" else None
    else:
        expected = "upper" if relation == "above" else "lower"
    assert side == expected
    context = {
        "session_lock_price": 100.0,
        "levels": {
            name: {
                "price": price,
                "status": "ACTIVE" if price is not None else "INACTIVE",
                "stack_group": "NONE",
                "stack_groups": [],
            }
        },
    }
    groups = entry_agent.active_liquidity_groups_from_context(context)
    if expected in {"upper", "lower"}:
        assert len(groups) == 1
        assert groups[0]["name"] == name
        assert groups[0]["side"] == expected
    else:
        assert groups == []


def test_exact_r1_vector_inventory_and_end_to_end_contract(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    artifact = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    pine_source = PINE_PATH.read_text(encoding="utf-8")
    assert artifact["vector_count"] == 18
    assert [item["id"] for item in artifact["vectors"]] == [f"OA-TV-{index:03d}" for index in range(1, 19)]
    accounted = []
    for vector in artifact["vectors"]:
        case_root = tmp_path / vector["id"]
        case_root.mkdir()
        bind_receiver_to_temp(monkeypatch, case_root)
        calls: list[dict] = []
        manager = bind_manager_to_receiver(monkeypatch, case_root, calls)
        payload = canonical_payload(vector["levels"], reference=float(vector["reference_price"]))
        # Each R1 vector first traverses the corrected production Pine string
        # semantics before any receiver-negative mutation is introduced.
        encoded_payload = production_pine_json_dumps(payload, pine_source)
        assert r"\r" not in encoded_payload
        payload = json.loads(encoded_payload)
        assert payload["source"] == "tradingview_level_helper"
        assert payload["version"] == "v14_canonical_liquidity_sender"
        assert payload["context_mode"] == "locked_levels_session_snapshot"
        assert payload["time_zone"] == "America/Los_Angeles"
        assert payload["timeframe"] == "1"
        assert tuple(payload["levels"]) == LEVELS
        assert tuple(row["name"] for row in payload["liquidity_map"]["levels"]) == LEVELS
        assert all(
            payload["levels"][row["name"]]
            == {key: value for key, value in row.items() if key != "name"}
            for row in payload["liquidity_map"]["levels"]
        )
        if vector["id"] == "OA-TV-013":
            payload["levels"].pop("YH")
            payload["liquidity_map"]["levels"] = [row for row in payload["liquidity_map"]["levels"] if row["name"] != "YH"]
        elif vector["id"] == "OA-TV-015":
            payload["liquidity_map"]["levels"].reverse()
        elif vector["id"] == "OA-TV-016":
            newer = canonical_payload(vector["levels"], timestamp="2026-08-09T13:17:00Z", session_date="2026-08-09")
            seed = manager.app.test_client().post("/webhook/tv-context?token=public-test-token", json=newer)
            assert seed.status_code == 200
            payload["timestamp"] = "2026-08-08T13:16:00Z"
            payload["session_date"] = "2026-08-08"
        elif vector["id"] == "OA-TV-018":
            payload["version"] = "legacy"
            payload["time_zone"] = "America/New_York"

        response = manager.app.test_client().post("/webhook/tv-context?token=public-test-token", json=payload)
        if vector["id"] in {"OA-TV-013", "OA-TV-018"}:
            assert response.status_code == 400
            assert calls == []
        elif vector["id"] == "OA-TV-016":
            assert response.status_code == 409
            assert response.get_json()["delivery_state"] == "REJECTED"
            rejected_identity = response.get_json()["message_identity"]
            rejected_record = json.loads(
                (Path(os.environ["TV_CONTEXT_SPOOL_DIR"]) / f"{rejected_identity}.json").read_text(encoding="utf-8")
            )
            assert rejected_record["state"] == "REJECTED"
            accepted = json.loads(Path(os.environ["TV_CONTEXT_ACCEPTANCE_LEDGER_PATH"]).read_text(encoding="utf-8"))
            assert accepted["symbols"]["YM"]["timestamp"] == "2026-08-09T13:17:00Z"
        else:
            assert response.status_code == 200, (vector["id"], response.get_json())
            response_body = response.get_json()
            assert response_body["durably_accepted"] is True
            assert response_body["delivery_state"] == "DELIVERED"
            assert len(response_body["message_identity"]) == 64
            assert len(calls) == 1
            assert calls[0]["headers"] == {"X-Randle-Relay-Token": "internal-test-token"}
            assert calls[0]["json"] == payload
            spool_record = json.loads(
                (
                    Path(os.environ["TV_CONTEXT_SPOOL_DIR"])
                    / f"{response_body['message_identity']}.json"
                ).read_text(encoding="utf-8")
            )
            assert spool_record["state"] == "DELIVERED"
            assert spool_record["payload"] == payload
            assert spool_record["message_identity"] == response_body["message_identity"]
            acceptance = json.loads(Path(os.environ["TV_CONTEXT_ACCEPTANCE_LEDGER_PATH"]).read_text(encoding="utf-8"))
            assert acceptance["symbols"]["YM"]["message_identity"] == response_body["message_identity"]
            if vector["id"] == "OA-TV-017":
                before = len(calls)
                repeated = manager.app.test_client().post("/webhook/tv-context?token=public-test-token", json=payload)
                assert repeated.status_code == 200
                assert repeated.get_json()["delivery_state"] == "DUPLICATE_NOOP"
                assert len(calls) == before
            context, error = receiver.build_context(payload)
            assert error is None
            assert context is not None
            assert tuple(context["levels"]) == LEVELS
            assert all(context["levels"][name]["price"] == vector["levels"][name] for name in LEVELS)
            assert context["canonical_validation"] == "PASS"
            assert context["session_lock_price"] == vector["reference_price"]
            assert {
                name: context["levels"][name]["side"]
                for name in LEVELS
            } == {
                name: side_for_level_price(name, vector["levels"][name], vector["reference_price"])
                for name in LEVELS
            }
            stored = json.loads(receiver.TV_CONTEXT_BY_SYMBOL_PATH.read_text(encoding="utf-8"))["symbols"]["YM"]
            assert tuple(stored["levels"]) == LEVELS
            assert all(stored["levels"][name]["price"] == vector["levels"][name] for name in LEVELS)
            assert stored["canonical_payload_sha256"] == spool_record["canonical_payload_sha256"]
            projection = ladder_projection(vector["levels"], float(vector["reference_price"]))
            intended = vector["intended_tv_ladder"]
            if vector["id"] != "OA-TV-011":
                assert projection == intended
            else:
                assert set(projection["high_nearest_to_farthest"]) == set(intended["high_nearest_to_farthest"])
                assert set(projection["low_nearest_to_farthest"]) == set(intended["low_nearest_to_farthest"])
                assert projection == ladder_projection(vector["levels"], float(vector["reference_price"]))
        accounted.append(vector["id"])
        monkeypatch.undo()
    assert len(accounted) == 18


def test_r4c_live_ym_bridge_is_nineteenth_end_to_end_vector(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = json.loads(R4C_BRIDGE_VECTOR_PATH.read_text(encoding="utf-8"))
    prices = {name: None for name in LEVELS}
    prices.update(fixture["levels"])
    payload = canonical_payload(prices, reference=54000.0)
    payload["stack_threshold"] = fixture["stack_threshold"]
    payload["daily_atr14"] = fixture["stack_threshold"] * 10

    expected = fixture["expected_membership"]
    map_rows = {row["name"]: row for row in payload["liquidity_map"]["levels"]}
    for name in LEVELS:
        memberships = expected.get(name, [])
        update = {
            "stack_group": memberships[0] if memberships else "NONE",
            "stack_groups": memberships,
            "stack_display": " + ".join(memberships) if memberships else "NONE",
        }
        payload["levels"][name].update(copy.deepcopy(update))
        map_rows[name].update(copy.deepcopy(update))

    stacks = [
        {
            "id": stack["id"],
            "side": "HIGH",
            "members": stack["members"],
            "innermost_price": min(prices[name] for name in stack["members"]),
            "outermost_price": max(prices[name] for name in stack["members"]),
        }
        for stack in fixture["expected_stacks"]
    ]
    payload["stacks"] = copy.deepcopy(stacks)
    payload["liquidity_map"]["stacks"] = copy.deepcopy(stacks)
    payload = json.loads(production_pine_json_dumps(payload, PINE_PATH.read_text(encoding="utf-8")))

    bind_receiver_to_temp(monkeypatch, tmp_path)
    calls: list[dict] = []
    manager = bind_manager_to_receiver(monkeypatch, tmp_path, calls)
    response = manager.app.test_client().post("/webhook/tv-context?token=public-test-token", json=payload)
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["delivery_state"] == "DELIVERED"
    assert len(calls) == 1 and calls[0]["json"] == payload

    context, error = receiver.build_context(copy.deepcopy(payload))
    assert error is None and context is not None
    frozen = entry_agent.build_session_locked_tv_context(copy.deepcopy(context))
    assert frozen is not None and frozen["locked"] is True
    for name, memberships in expected.items():
        display = " + ".join(memberships) if memberships else "NONE"
        for surface in (
            payload["levels"][name],
            map_rows[name],
            context["levels"][name],
            frozen["active_levels"][name],
            frozen["tv_context"]["levels"][name],
        ):
            assert surface["stack_group"] == (memberships[0] if memberships else "NONE")
            assert surface["stack_groups"] == memberships
            assert surface["stack_display"] == display
    assert [group["name"] for group in frozen["active_groups"]] == ["HIGH 1", "HIGH 2"]


def test_strict_duplicate_parity_and_internal_auth_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bind_receiver_to_temp(monkeypatch, tmp_path)
    payload = canonical_payload({"PMH": 110, "PML": 90, "LH": 108, "LL": 92, "ONH": 106, "ONL": 94, "YH": 104, "YL": 96})
    duplicated = copy.deepcopy(payload)
    duplicated["liquidity_map"]["levels"][-1]["name"] = "YH"
    context, error = receiver.build_context(duplicated)
    assert context is None and "duplicate name YH" in error["error"]
    mismatch = copy.deepcopy(payload)
    mismatch["liquidity_map"]["levels"][0]["price"] = 999
    context, error = receiver.build_context(mismatch)
    assert context is None and error["error"] == "levels/liquidity_map parity mismatch for PMH"

    client = receiver.app.test_client()
    monkeypatch.delenv("TV_CONTEXT_INTERNAL_RELAY_TOKEN")
    assert client.post("/webhook/tv-context", json=payload).status_code == 503
    monkeypatch.setenv("TV_CONTEXT_INTERNAL_RELAY_TOKEN", "internal-test-token")
    assert client.post("/webhook/tv-context", json=payload).status_code == 401
    assert client.post("/webhook/tv-context", json=payload, headers={"X-Randle-Relay-Token": "wrong"}).status_code == 401


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    (
        ("wrong_price_type", "levels.YH.price must be a finite number or null"),
        ("unknown_name", "levels must contain each canonical name exactly once"),
        ("malformed_stack", "levels.YH.stack_groups must be an array"),
        ("invalid_timezone", "time_zone must equal America/Los_Angeles"),
        ("invalid_version", "version must equal v14_canonical_liquidity_sender"),
    ),
)
def test_malformed_canonical_vector_covers_each_r1_failure_class(mutation: str, expected_error: str) -> None:
    payload = canonical_payload({"PMH": 110, "PML": 90, "LH": 108, "LL": 92, "ONH": 106, "ONL": 94, "YH": 104, "YL": 96})
    if mutation == "wrong_price_type":
        payload["levels"]["YH"]["price"] = "104"
        payload["liquidity_map"]["levels"][6]["price"] = "104"
    elif mutation == "unknown_name":
        payload["levels"]["UNKNOWN"] = payload["levels"].pop("YH")
    elif mutation == "malformed_stack":
        payload["levels"]["YH"]["stack_groups"] = "NONE"
        payload["liquidity_map"]["levels"][6]["stack_groups"] = "NONE"
    elif mutation == "invalid_timezone":
        payload["time_zone"] = "America/New_York"
    elif mutation == "invalid_version":
        payload["version"] = "legacy"
    context, error = receiver.build_context(payload)
    assert context is None
    assert expected_error in error["error"]


def test_public_auth_durable_retry_restart_and_canonical_rejection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bind_receiver_to_temp(monkeypatch, tmp_path)
    manager = bind_manager_to_receiver(monkeypatch, tmp_path)
    payload = canonical_payload({"PMH": 110, "PML": 90, "LH": 108, "LL": 92, "ONH": 106, "ONL": 94, "YH": 104, "YL": 96})
    client = manager.app.test_client()
    assert client.post("/webhook/tv-context", json=payload).status_code == 401
    assert client.post("/webhook/tv-context?token=wrong", json=payload).status_code == 401
    monkeypatch.delenv("TV_WEBHOOK_INGRESS_TOKEN")
    assert client.post("/webhook/tv-context?token=public-test-token", json=payload).status_code == 503
    monkeypatch.setenv("TV_WEBHOOK_INGRESS_TOKEN", "public-test-token")
    redacted = manager._redact_tv_access_requestline("POST /webhook/tv-context?token=raw-secret&probe=1 HTTP/1.1")
    assert "raw-secret" not in redacted
    assert "token=<REDACTED>&probe=<REDACTED>" in redacted

    def unavailable(*_args, **_kwargs):
        raise requests.ConnectionError("isolated receiver unavailable")

    monkeypatch.setattr(manager.requests, "post", unavailable)
    queued = client.post("/webhook/tv-context?token=public-test-token", json=payload)
    assert queued.status_code == 202
    queued_body = queued.get_json()
    assert queued_body["durably_accepted"] is True and queued_body["delivery_state"] == "PENDING"
    spool_path = Path(os.environ["TV_CONTEXT_SPOOL_DIR"]) / f"{queued_body['message_identity']}.json"
    assert json.loads(spool_path.read_text(encoding="utf-8"))["state"] == "PENDING"

    receiver_client = receiver.app.test_client()
    restarted_manager = load_manager("oa_r2_manager_after_restart")
    monkeypatch.setattr(
        restarted_manager.requests,
        "post",
        lambda _url, json=None, headers=None, timeout=None: FlaskResponseAdapter(
            receiver_client.post("/webhook/tv-context", json=json, headers=headers or {})
        ),
    )
    recovered = restarted_manager.recover_pending_tv_context_deliveries()
    assert recovered == {"attempted": 1, "delivered": 1, "pending": 0, "rejected": 0}
    assert json.loads(spool_path.read_text(encoding="utf-8"))["state"] == "DELIVERED"
    repeated_after_restart = restarted_manager.app.test_client().post(
        "/webhook/tv-context?token=public-test-token",
        json=payload,
    )
    assert repeated_after_restart.status_code == 200
    assert repeated_after_restart.get_json()["delivery_state"] == "DUPLICATE_NOOP"

    invalid = copy.deepcopy(payload)
    invalid["levels"].pop("YH")
    invalid["liquidity_map"]["levels"] = [row for row in invalid["liquidity_map"]["levels"] if row["name"] != "YH"]
    rejected = client.post("/webhook/tv-context?token=public-test-token", json=invalid)
    assert rejected.status_code == 400


def test_transient_retry_and_receiver_rejection_are_distinct(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bind_receiver_to_temp(monkeypatch, tmp_path)
    manager = bind_manager_to_receiver(monkeypatch, tmp_path)
    payload = canonical_payload({"PMH": 110, "PML": 90, "LH": 108, "LL": 92, "ONH": 106, "ONL": 94, "YH": 104, "YL": 96})

    class Response:
        text = ""

        def __init__(self, status_code, body):
            self.status_code = status_code
            self.body = body

        def json(self):
            return self.body

    calls = []

    def transient_then_success(*_args, **_kwargs):
        calls.append(1)
        return Response(503, {"error": "temporary"}) if len(calls) == 1 else Response(200, {"ok": True})

    monkeypatch.setattr(manager.requests, "post", transient_then_success)
    result = manager.app.test_client().post("/webhook/tv-context?token=public-test-token", json=payload)
    assert result.status_code == 200 and len(calls) == 2

    rejection_payload = copy.deepcopy(payload)
    rejection_payload["timestamp"] = "2026-08-09T06:16:00-07:00"
    reject_calls = []

    def canonical_rejection(*_args, **_kwargs):
        reject_calls.append(1)
        return Response(400, {"error": "timestamp must be a valid UTC timestamp"})

    monkeypatch.setattr(manager.requests, "post", canonical_rejection)
    rejected = manager.app.test_client().post("/webhook/tv-context?token=public-test-token", json=rejection_payload)
    assert rejected.status_code == 400 and len(reject_calls) == 1
    assert rejected.get_json()["delivery_state"] == "REJECTED"

    timed_out_payload = copy.deepcopy(payload)
    timed_out_payload["timestamp"] = "2026-08-09T13:18:00Z"
    timeout_calls = []

    def always_timeout(*_args, **_kwargs):
        timeout_calls.append(1)
        raise requests.Timeout("bounded isolated timeout")

    monkeypatch.setattr(manager.requests, "post", always_timeout)
    timed_out = manager.app.test_client().post(
        "/webhook/tv-context?token=public-test-token",
        json=timed_out_payload,
    )
    assert timed_out.status_code == 202
    assert timed_out.get_json()["delivery_state"] == "PENDING"
    assert len(timeout_calls) == 2


def test_malformed_json_and_duplicate_json_key_fail_before_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bind_receiver_to_temp(monkeypatch, tmp_path)
    client = receiver.app.test_client()
    headers = {"X-Randle-Relay-Token": "internal-test-token", "Content-Type": "application/json"}
    malformed = client.post("/webhook/tv-context", data="{bad", headers=headers)
    assert malformed.status_code == 400
    duplicate = client.post(
        "/webhook/tv-context",
        data='{"source":"tradingview_level_helper","source":"forged"}',
        headers=headers,
    )
    assert duplicate.status_code == 400
    assert "duplicate JSON key: source" in duplicate.get_json()["error"]

    manager = bind_manager_to_receiver(monkeypatch, tmp_path / "manager-malformed")
    public_malformed = manager.app.test_client().post(
        "/webhook/tv-context?token=public-test-token",
        data="{bad",
        content_type="application/json",
    )
    assert public_malformed.status_code == 400


def test_order_replay_and_altered_timestamp_survive_ledger_reload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bind_receiver_to_temp(monkeypatch, tmp_path)
    client = receiver.app.test_client()
    headers = {"X-Randle-Relay-Token": "internal-test-token"}
    levels = {"PMH": 110, "PML": 90, "LH": 108, "LL": 92, "ONH": 106, "ONL": 94, "YH": 104, "YL": 96}
    newest = canonical_payload(levels, timestamp="2026-08-09T13:17:00Z")
    first = client.post("/webhook/tv-context", json=newest, headers=headers)
    assert first.status_code == 200 and first.get_json()["delivery_disposition"] == "ACCEPTED"
    state_before_duplicate = receiver.TV_CONTEXT_BY_SYMBOL_PATH.read_bytes()
    ledger_before_duplicate = Path(os.environ["TV_CONTEXT_ACCEPTANCE_LEDGER_PATH"]).read_bytes()
    duplicate = client.post("/webhook/tv-context", json=newest, headers=headers)
    assert duplicate.status_code == 200 and duplicate.get_json()["delivery_disposition"] == "DUPLICATE_NOOP"
    assert receiver.TV_CONTEXT_BY_SYMBOL_PATH.read_bytes() == state_before_duplicate
    assert Path(os.environ["TV_CONTEXT_ACCEPTANCE_LEDGER_PATH"]).read_bytes() == ledger_before_duplicate

    Path(os.environ["TV_CONTEXT_ACCEPTANCE_LEDGER_PATH"]).unlink()
    duplicate_after_ledger_loss = client.post("/webhook/tv-context", json=newest, headers=headers)
    assert duplicate_after_ledger_loss.status_code == 200
    assert duplicate_after_ledger_loss.get_json()["delivery_disposition"] == "DUPLICATE_NOOP"
    assert receiver.TV_CONTEXT_BY_SYMBOL_PATH.read_bytes() == state_before_duplicate

    older = canonical_payload(levels, timestamp="2026-08-09T13:16:00Z")
    out_of_order = client.post("/webhook/tv-context", json=older, headers=headers)
    assert out_of_order.status_code == 409 and out_of_order.get_json()["disposition"] == "OUT_OF_ORDER"
    altered = copy.deepcopy(newest)
    altered["levels"]["YH"]["price"] = 105
    for row in altered["liquidity_map"]["levels"]:
        if row["name"] == "YH":
            row["price"] = 105
    conflict = client.post("/webhook/tv-context", json=altered, headers=headers)
    assert conflict.status_code == 409 and conflict.get_json()["disposition"] == "ALTERED_SAME_TIMESTAMP"


def test_downstream_roaming_ownership_uses_frozen_reference() -> None:
    assert entry_agent.side_for_level("YH") is None
    assert entry_agent.side_for_level("YL") is None
    assert entry_agent.side_for_level("YH", 96, 100) == "lower"
    assert entry_agent.side_for_level("YH", 104, 100) == "upper"
    assert entry_agent.side_for_level("YL", 96, 100) == "lower"
    assert entry_agent.side_for_level("YL", 104, 100) == "upper"
    assert entry_agent.side_for_level("YH", 100, 100) == "touch"
    context = {
        "session_lock_price": 100,
        "levels": {
            "YH": {"price": 96, "status": "ACTIVE", "stack_group": "NONE", "stack_groups": []},
            "YL": {"price": 104, "status": "ACTIVE", "stack_group": "NONE", "stack_groups": []},
        },
    }
    groups = entry_agent.active_liquidity_groups_from_context(context)
    assert {group["name"]: group["side"] for group in groups} == {"YH": "lower", "YL": "upper"}
