"""Operational A-R4C bridge-stack source, topology, and downstream parity gates."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent
ENTRY_AGENT_DIR = ROOT / "EntryAgent"
for path in (ROOT, ENTRY_AGENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import entry_agent
import tv_context_server as receiver


PINE = ROOT / "TradingView" / "indicators" / "Randle_AI_Level_Map_Helper.pine"
LIVE_FIXTURE = ROOT / "tests" / "fixtures" / "operational_a" / "r4c_live_ym_bridge_vector.json"
LIVE_FIXTURE_SHA256 = "5e8d7485eb45f4e9a5b6f40af50ed6d3e703a3986c1bebffe21d2751c8a20b11"
LEVEL_ORDER = ("YH", "YL", "ONH", "ONL", "LH", "LL", "PMH", "PML")
WIRE_ORDER = ("PMH", "PML", "LH", "LL", "ONH", "ONL", "YH", "YL")
ACTIVE_STATUSES = {"ACTIVE", "REACTIVATED"}


def _manager_module():
    spec = importlib.util.spec_from_file_location("r4c_trade_manager", ROOT / "Engines" / "trade_manager.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def manager():
    return _manager_module()


def bridge_stacks(
    active_levels: dict[str, float], *, reference: float, threshold: float
) -> tuple[dict[str, dict[str, object]], list[dict[str, object]]]:
    """Independent executable model of the corrected Pine bridge algorithm."""
    candidates = [
        {"name": name, "price": float(price), "side": "HIGH" if float(price) > reference else "LOW"}
        for name, price in active_levels.items()
        if float(price) != reference
    ]
    groups: list[dict[str, object]] = []

    for side in ("HIGH", "LOW"):
        ordered = [row for row in candidates if row["side"] == side]
        ordered.sort(
            key=lambda row: (float(row["price"]), LEVEL_ORDER.index(str(row["name"]))),
            reverse=side == "LOW",
        )
        pending: list[dict[str, object]] = []

        def commit() -> None:
            if len(pending) < 2:
                return
            prices = [float(row["price"]) for row in pending]
            groups.append(
                {
                    "side": side,
                    "members": [str(row["name"]) for row in pending],
                    "innermost_price": prices[0],
                    "outermost_price": prices[-1],
                }
            )

        for row in ordered:
            proposed = pending + [row]
            prices = [float(item["price"]) for item in proposed]
            if not pending or max(prices) - min(prices) <= threshold:
                pending.append(row)
                continue

            boundary_price = float(pending[-1]["price"])
            bridge_members = [item for item in pending if float(item["price"]) == boundary_price]
            commit()
            pending = bridge_members + [row] if abs(float(row["price"]) - boundary_price) <= threshold else [row]

        commit()

    side_ordinals = {"HIGH": 0, "LOW": 0}
    memberships = {name: [] for name in WIRE_ORDER}
    explicit: list[dict[str, object]] = []
    for group in groups:
        side = str(group["side"])
        side_ordinals[side] += 1
        label = f"{side} {side_ordinals[side]}"
        members = list(group["members"])
        for name in members:
            memberships[name].append(label)
        explicit.append({"id": label, **group})

    semantics: dict[str, dict[str, object]] = {}
    for name in WIRE_ORDER:
        labels = memberships[name]
        semantics[name] = {
            "price": active_levels.get(name),
            "status": "ACTIVE" if name in active_levels else "INACTIVE",
            "stack_group": labels[0] if labels else "NONE",
            "stack_groups": labels,
            "stack_display": " + ".join(labels) if labels else "NONE",
        }
    return semantics, explicit


def canonical_payload(
    active_levels: dict[str, float], *, reference: float, threshold: float, symbol: str = "YM1!"
) -> tuple[dict[str, object], dict[str, dict[str, object]], list[dict[str, object]]]:
    semantics, stacks = bridge_stacks(active_levels, reference=reference, threshold=threshold)
    rows = [{"name": name, **copy.deepcopy(semantics[name])} for name in WIRE_ORDER]
    payload: dict[str, object] = {
        "source": "tradingview_level_helper",
        "version": "v14_canonical_liquidity_sender",
        "context_mode": "locked_levels_session_snapshot",
        "timestamp": "2026-08-10T13:15:00Z",
        "session_date": "2026-08-10",
        "session_locked": True,
        "locked": True,
        "is_premarket_end": True,
        "is_recurring_update": False,
        "price_is_true_level": True,
        "display_offsets_applied_to_chart_only": True,
        "symbol": symbol,
        "time_zone": "America/Los_Angeles",
        "timeframe": "1",
        "atr_1m_14": 5.0,
        "daily_atr14": threshold * 10,
        "stack_threshold": threshold,
        "stack_threshold_pct": 10.0,
        "session_lock_price": reference,
        "pm_atr_pct": 10.0,
        "daily_range_pct": 20.0,
        "levels": copy.deepcopy(semantics),
        "stacks": copy.deepcopy(stacks),
        "liquidity_map": {"levels": rows, "stacks": copy.deepcopy(stacks)},
        "midpoints": {},
        "exhaustion_boundaries": {},
    }
    return payload, semantics, stacks


CASES = (
    ("H01_simple_pair", {"PMH": 110, "LH": 115}, 100, 5, [["PMH", "LH"]]),
    ("H02_dense_cluster", {"PMH": 110, "LH": 112, "ONH": 114, "YH": 115}, 100, 5, [["PMH", "LH", "ONH", "YH"]]),
    ("H03_live_bridge", {"PMH": 54125, "LH": 54152, "ONH": 54170, "YH": 54199}, 54000, 69, [["PMH", "LH", "ONH"], ["ONH", "YH"]]),
    ("H04_chained_overlap", {"PMH": 110, "LH": 114, "ONH": 118, "YH": 126, "YL": 134}, 100, 8, [["PMH", "LH", "ONH"], ["ONH", "YH"], ["YH", "YL"]]),
    ("H05_disjoint", {"PMH": 110, "LH": 114, "ONH": 130, "YH": 134}, 100, 4, [["PMH", "LH"], ["ONH", "YH"]]),
    ("H06_exact_threshold", {"PMH": 110, "LH": 120}, 100, 10, [["PMH", "LH"]]),
    ("H07_threshold_plus_tick_bridge", {"PMH": 110, "LH": 120, "ONH": 121}, 100, 10, [["PMH", "LH"], ["LH", "ONH"]]),
    ("H08_yh_roaming", {"PMH": 110, "YH": 115}, 100, 5, [["PMH", "YH"]]),
    ("H09_yl_roaming", {"PMH": 110, "YL": 115}, 100, 5, [["PMH", "YL"]]),
    ("L10_simple_pair", {"PML": 190, "LL": 185}, 200, 5, [["PML", "LL"]]),
    ("L11_dense_cluster", {"PML": 190, "LL": 188, "ONL": 186, "YL": 185}, 200, 5, [["PML", "LL", "ONL", "YL"]]),
    ("L12_bridge", {"PML": 54199, "LL": 54172, "ONL": 54154, "YL": 54125}, 55000, 69, [["PML", "LL", "ONL"], ["ONL", "YL"]]),
    ("L13_chained_overlap", {"PML": 190, "LL": 186, "ONL": 182, "YL": 174, "YH": 166}, 200, 8, [["PML", "LL", "ONL"], ["ONL", "YL"], ["YL", "YH"]]),
    ("L14_disjoint", {"PML": 190, "LL": 186, "ONL": 170, "YL": 166}, 200, 4, [["PML", "LL"], ["ONL", "YL"]]),
    ("L15_exact_threshold", {"PML": 190, "LL": 180}, 200, 10, [["PML", "LL"]]),
    ("L16_threshold_plus_tick_bridge", {"PML": 190, "LL": 180, "ONL": 179}, 200, 10, [["PML", "LL"], ["LL", "ONL"]]),
    ("L17_yh_roaming", {"PML": 190, "YH": 185}, 200, 5, [["PML", "YH"]]),
    ("L18_yl_roaming", {"PML": 190, "YL": 185}, 200, 5, [["PML", "YL"]]),
)


def expected_memberships(expected_groups: list[list[str]], side: str) -> dict[str, list[str]]:
    result = {name: [] for name in WIRE_ORDER}
    for ordinal, members in enumerate(expected_groups, start=1):
        for name in members:
            result[name].append(f"{side} {ordinal}")
    return result


def assert_six_surface_parity(payload, semantics, context, session) -> None:
    map_rows = {row["name"]: row for row in payload["liquidity_map"]["levels"]}
    normalized_rows = {row["name"]: row for row in receiver.public_liquidity_map(context)["levels"]}
    frozen = session["tv_context"]["levels"]
    for name in WIRE_ORDER:
        expected = {field: semantics[name][field] for field in ("stack_group", "stack_groups", "stack_display")}
        assert {field: payload["levels"][name][field] for field in expected} == expected
        assert {field: map_rows[name][field] for field in expected} == expected
        assert {field: context["levels"][name][field] for field in expected} == expected
        assert {field: normalized_rows[name][field] for field in expected} == expected
        if semantics[name]["status"] == "ACTIVE":
            assert {field: frozen[name][field] for field in expected} == expected


def test_corrected_pine_source_contract_and_frozen_recovery_cadence() -> None:
    source = PINE.read_text(encoding="utf-8")
    for token in (
        "stackLevelBridgeGroups",
        "bridgeSpanValid",
        "Every active level at the preceding outer boundary carries",
        'primaryLabel + " + " + bridgeLabel',
        'str.split(displayLabel, " + ")',
        "array.size(labels) >= 1 ? f_json_str(array.get(labels, 0))",
        "for stackNumber = 1 to 7",
    ):
        assert token in source
    assert "canonicalSnapshotReady = canonicalPayloadReady and str.length(frozenCanonicalPayload) == 0" in source
    assert source.count("alert(frozenCanonicalPayload, alert.freq_once_per_bar_close)") == 1
    assert "OPERATIONAL_A_CADENCE=FROZEN_SNAPSHOT_5_MINUTE_RECOVERY" in source
    assert '"context_mode":"locked_levels_session_snapshot"' not in source
    assert '\\"context_mode\\":\\"locked_levels_session_snapshot\\"' in source
    assert '\\"version\\":\\"v14_canonical_liquidity_sender\\"' in source
    assert "stackEligibleIndex" not in source
    assert "sideAtIndex(int idx) =>\n    groupLabel(priceAtIndex(idx))" in source.replace("\r\n", "\n")
    assert "sessionLockPrice_lock := close" in source
    assert "array.push(stacksArr, stackLabel)" in source
    assert "array.get(stacksArr, i))" in source
    assert 'addLevelRow(int row, string name, float truePrice, float visPrice, string state, string status, string stackLabel)' in source


def test_authenticated_live_fixture_is_permanent_and_exact() -> None:
    assert hashlib.sha256(LIVE_FIXTURE.read_bytes()).hexdigest() == LIVE_FIXTURE_SHA256
    fixture = json.loads(LIVE_FIXTURE.read_text(encoding="utf-8"))
    payload, semantics, stacks = canonical_payload(
        {name: float(price) for name, price in fixture["levels"].items()},
        reference=54000,
        threshold=float(fixture["stack_threshold"]),
    )
    actual = {name: semantics[name]["stack_groups"] for name in fixture["levels"]}
    assert actual == fixture["expected_membership"]
    assert [stack["members"] for stack in stacks] == [["PMH", "LH", "ONH"], ["ONH", "YH"]]
    assert payload["levels"]["ONH"]["stack_group"] == "HIGH 1"
    assert payload["levels"]["ONH"]["stack_display"] == "HIGH 1 + HIGH 2"


@pytest.mark.parametrize("case_id,active,reference,threshold,expected", CASES, ids=[case[0] for case in CASES])
def test_stack_topology_matrix_and_six_surface_downstream_parity(
    case_id, active, reference, threshold, expected, manager
) -> None:
    payload, semantics, stacks = canonical_payload(active, reference=reference, threshold=threshold)
    side = "HIGH" if case_id.startswith("H") else "LOW"
    assert [stack["members"] for stack in stacks] == expected
    expected_by_level = expected_memberships(expected, side)
    assert {name: semantics[name]["stack_groups"] for name in WIRE_ORDER} == expected_by_level
    for details in semantics.values():
        memberships = details["stack_groups"]
        assert details["stack_group"] == (memberships[0] if memberships else "NONE")
        assert details["stack_display"] == (" + ".join(memberships) if memberships else "NONE")

    assert manager._validate_tv_context_envelope(copy.deepcopy(payload)) == "YM"
    context, error = receiver.build_context(copy.deepcopy(payload))
    assert error is None, (case_id, error)
    assert context is not None
    session = entry_agent.build_session_locked_tv_context(copy.deepcopy(context))
    assert session is not None and session["locked"] is True, (case_id, session)
    assert_six_surface_parity(payload, semantics, context, session)


def test_isolated_pair_inside_and_outside_threshold() -> None:
    inside, groups = bridge_stacks({"PMH": 110, "LH": 115}, reference=100, threshold=5)
    assert [group["members"] for group in groups] == [["PMH", "LH"]]
    assert inside["PMH"]["stack_groups"] == ["HIGH 1"]
    outside, groups = bridge_stacks({"PMH": 110, "LH": 116}, reference=100, threshold=5)
    assert groups == []
    assert outside["PMH"]["stack_group"] == outside["LH"]["stack_group"] == "NONE"


def test_simultaneous_high_low_overlap_namespaces_and_downstream(manager) -> None:
    active = {
        "PMH": 110,
        "LH": 114,
        "ONH": 118,
        "YH": 126,
        "PML": 90,
        "LL": 86,
        "ONL": 82,
        "YL": 74,
    }
    payload, semantics, stacks = canonical_payload(active, reference=100, threshold=8)
    assert [stack["id"] for stack in stacks] == ["HIGH 1", "HIGH 2", "LOW 1", "LOW 2"]
    assert semantics["ONH"]["stack_groups"] == ["HIGH 1", "HIGH 2"]
    assert semantics["ONL"]["stack_groups"] == ["LOW 1", "LOW 2"]
    assert manager._validate_tv_context_envelope(copy.deepcopy(payload)) == "YM"
    context, error = receiver.build_context(copy.deepcopy(payload))
    assert error is None
    session = entry_agent.build_session_locked_tv_context(context)
    assert session and session["locked"] is True
    assert_six_surface_parity(payload, semantics, context, session)


def test_eight_level_boundary_chain_has_all_seven_explicit_groups() -> None:
    active = dict(zip(WIRE_ORDER, (110, 118, 126, 134, 142, 150, 158, 166)))
    _payload, semantics, stacks = canonical_payload(active, reference=100, threshold=8)
    assert [stack["id"] for stack in stacks] == [f"HIGH {number}" for number in range(1, 8)]
    assert semantics["ONH"]["stack_groups"] == ["HIGH 4", "HIGH 5"]
    assert all(len(details["stack_groups"]) <= 2 for details in semantics.values())


def test_version_identity_remains_unambiguous_without_schema_version_change(manager) -> None:
    corrected, _, _ = canonical_payload(
        {"PMH": 54125, "LH": 54152, "ONH": 54170, "YH": 54199}, reference=54000, threshold=69
    )
    defective = copy.deepcopy(corrected)
    for name in ("PMH", "LH", "ONH"):
        defective["levels"][name].update(
            {"stack_group": "HIGH 1", "stack_groups": ["HIGH 1"], "stack_display": "HIGH 1"}
        )
    defective["levels"]["YH"].update({"stack_group": "NONE", "stack_groups": [], "stack_display": "NONE"})
    defective["stacks"] = [copy.deepcopy(corrected["stacks"][0])]
    defective["liquidity_map"]["stacks"] = copy.deepcopy(defective["stacks"])
    defective["liquidity_map"]["levels"] = [
        {"name": name, **copy.deepcopy(defective["levels"][name])} for name in WIRE_ORDER
    ]
    corrected_identity = manager._tv_message_identity(corrected, "YM")
    defective_identity = manager._tv_message_identity(defective, "YM")
    assert corrected["version"] == defective["version"] == "v14_canonical_liquidity_sender"
    assert corrected_identity != defective_identity


def test_matrix_contract_has_at_least_nine_high_and_nine_low_cases() -> None:
    assert len(CASES) >= 18
    assert sum(case[0].startswith("H") for case in CASES) >= 9
    assert sum(case[0].startswith("L") for case in CASES) >= 9
