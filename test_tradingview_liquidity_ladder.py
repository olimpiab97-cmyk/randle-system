"""Deterministic verification of the canonical full-span Liquidity Level rule.

The grouping model is intentionally non-Pine. It mirrors the governed Pine
algorithm but does not replace source-linked TradingView compilation.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest


ROOT = Path(__file__).resolve().parent
ENTRY_AGENT_DIR = ROOT / "EntryAgent"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ENTRY_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(ENTRY_AGENT_DIR))

import entry_agent
import tv_context_server
try:
    from liquidity_stack_validation import stack_threshold_from_context, validate_liquidity_stack_structure
except ModuleNotFoundError:
    stack_threshold_from_context = None
    validate_liquidity_stack_structure = None


CANONICAL_STACK_RUNTIME_AVAILABLE = (
    callable(stack_threshold_from_context)
    and callable(validate_liquidity_stack_structure)
    and hasattr(tv_context_server, "_rebuild_frozen_lock_from_latest_tv")
    and hasattr(entry_agent, "valid_locked_tv_context")
)
requires_canonical_stack_runtime = pytest.mark.skipif(
    not CANONICAL_STACK_RUNTIME_AVAILABLE,
    reason="canonical stack receiver/runtime implementation is outside this source-only commit",
)


LEVEL_ORDER = ("YH", "YL", "ONH", "ONL", "LH", "LL", "PMH", "PML")
DISPLAY_PRIORITY = {"YH": 0, "ONH": 1, "LH": 2, "PMH": 3, "PML": 4, "LL": 5, "ONL": 6, "YL": 7}

GOVERNED_PINE = ROOT / "TradingView" / "indicators" / "Randle_AI_Level_Map_Helper.pine"
EVIDENCE_DIR = ROOT / "Architecture" / "Impact_Assessments" / "Evidence" / "2026-07-16_TradingView_Liquidity_Ladder"
HISTORICAL_CATEGORICAL_PINE = EVIDENCE_DIR / "Randle_AI_Level_Map_Helper_7-16_Erroneous_Categorical_Exclusion_0543DD45.pine"
GOVERNED_FULL_SPAN_PINE_SHA256 = "1C795076B9463B3F567366851EDA4914D2248F1B4B5A7B1155C8E26CEF961D70"
HISTORICAL_CATEGORICAL_PINE_SHA256 = "0543DD45B92AC50B30A099AE13D97CDAA4406B1DFBDDEACA4EC14456B874F497"
REPLACEMENT_SECTION_SHA256 = "36D16D4F50742DA3FDA4A8580D3E2EA099DD2344306D58DAEFE6DC4E21F179BA"
CORRECTED_SCREENSHOT_SHA256 = "EDEC2CE7703C32552AF5CAC94497662FC5CB5A4F893DC8AA265CF89E9DC3DF4B"
HISTORICAL_EVIDENCE_AVAILABLE = all(
    path.exists()
    for path in (
        HISTORICAL_CATEGORICAL_PINE,
        EVIDENCE_DIR / "REPLACE_STACK_GROUP_SECTION.pine",
        EVIDENCE_DIR / "YM1!_2026-07-16_21-01-55.png",
    )
)
requires_historical_evidence = pytest.mark.skipif(
    not HISTORICAL_EVIDENCE_AVAILABLE,
    reason="historical July 16 evidence package is not part of this source-only commit",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def active_level(price: float, stack_group: str = "NONE", status: str = "ACTIVE") -> dict[str, object]:
    return {"price": price, "status": status, "stack_group": stack_group}


def calculate_full_span_stacks(
    levels: dict[str, dict[str, object]],
    *,
    current_price: float,
    threshold: float,
) -> tuple[dict[str, str], list[dict[str, object]]]:
    """Model Pine's deterministic innermost-to-outermost full-span grouping."""
    labels = {name: "NONE" for name in LEVEL_ORDER if name in levels}
    candidates = []
    for name in LEVEL_ORDER:
        details = levels.get(name)
        if not isinstance(details, dict):
            continue
        if str(details.get("status") or "").upper() not in {"ACTIVE", "REACTIVATED"}:
            continue
        price = details.get("price")
        if not isinstance(price, (int, float)) or float(price) == current_price:
            continue
        candidates.append({"name": name, "price": float(price), "side": "high" if float(price) > current_price else "low"})

    components: list[dict[str, object]] = []
    for side in ("high", "low"):
        side_candidates = [item for item in candidates if item["side"] == side]
        side_candidates.sort(
            key=lambda item: (float(item["price"]), LEVEL_ORDER.index(str(item["name"]))),
            reverse=side == "low",
        )
        pending: list[dict[str, object]] = []

        def finalize() -> None:
            if len(pending) < 2:
                return
            prices = [float(item["price"]) for item in pending]
            components.append(
                {
                    "members": [str(item["name"]) for item in pending],
                    "side": side,
                    "innermost_liquidity_level": min(prices) if side == "high" else max(prices),
                    "outermost_liquidity_level": max(prices) if side == "high" else min(prices),
                    "span": max(prices) - min(prices),
                }
            )

        for candidate in side_candidates:
            proposed = pending + [candidate]
            prices = [float(item["price"]) for item in proposed]
            if not pending or max(prices) - min(prices) <= threshold:
                pending.append(candidate)
            else:
                finalize()
                pending = [candidate]
        finalize()

    for side in ("high", "low"):
        side_components = [item for item in components if item["side"] == side]
        side_components.sort(
            key=lambda item: float(item["innermost_liquidity_level"]),
            reverse=side == "low",
        )
        for ordinal, component in enumerate(side_components, start=1):
            label = f"{side.upper()} {ordinal}"
            component["label"] = label
            for name in component["members"]:
                labels[str(name)] = label
    return labels, components


def ordered_table_names(levels: dict[str, dict[str, object]], current_price: float) -> tuple[list[str], list[str]]:
    active = [
        name
        for name, details in levels.items()
        if str(details.get("status") or "").upper() in {"ACTIVE", "REACTIVATED"}
        and isinstance(details.get("price"), (int, float))
    ]
    high = sorted(
        (name for name in active if float(levels[name]["price"]) >= current_price),
        key=lambda name: (-float(levels[name]["price"]), DISPLAY_PRIORITY[name]),
    )
    low = sorted(
        (name for name in active if float(levels[name]["price"]) <= current_price),
        key=lambda name: (-float(levels[name]["price"]), DISPLAY_PRIORITY[name]),
    )
    return high, low


def target_anchors(
    levels: dict[str, dict[str, object]],
    labels: dict[str, str],
    components: list[dict[str, object]],
    current_price: float,
) -> tuple[list[float], list[float]]:
    component_by_label = {str(component["label"]): component for component in components}
    seen_groups: set[str] = set()
    high: set[float] = set()
    low: set[float] = set()
    for name, details in levels.items():
        if str(details.get("status") or "").upper() not in {"ACTIVE", "REACTIVATED"}:
            continue
        price = float(details["price"])
        label = labels.get(name, "NONE")
        anchor = price
        if label != "NONE":
            if label in seen_groups:
                continue
            seen_groups.add(label)
            anchor = float(component_by_label[label]["outermost_liquidity_level"])
        if anchor > current_price:
            high.add(anchor)
        elif anchor < current_price:
            low.add(anchor)
    return sorted(high), sorted(low, reverse=True)


def project_levels(levels: dict[str, dict[str, object]], labels: dict[str, str]) -> dict[str, dict[str, object]]:
    return {name: {**copy.deepcopy(details), "stack_group": labels.get(name, "NONE")} for name, details in levels.items()}


def receiver_payload(
    levels: dict[str, dict[str, object]],
    *,
    symbol: str = "YM",
    reference: float = 90,
    threshold: float = 5,
    stacks: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "source": "tradingview_level_helper",
        "symbol": symbol,
        "timestamp": "2026-07-16T06:15:00-07:00",
        "session_date": "2026-07-16",
        "time_zone": "America/Los_Angeles",
        "locked": True,
        "session_lock_price": reference,
        "stack_threshold": threshold,
        "daily_atr14": threshold * 10,
        "levels": copy.deepcopy(levels),
    }
    if stacks is not None:
        payload["liquidity_map"] = {"stacks": copy.deepcopy(stacks)}
    return payload


@requires_historical_evidence
def test_evidence_history_is_preserved_and_current_source_has_new_identity() -> None:
    assert sha256(HISTORICAL_CATEGORICAL_PINE) == HISTORICAL_CATEGORICAL_PINE_SHA256
    assert sha256(EVIDENCE_DIR / "REPLACE_STACK_GROUP_SECTION.pine") == REPLACEMENT_SECTION_SHA256
    assert sha256(EVIDENCE_DIR / "YM1!_2026-07-16_21-01-55.png") == CORRECTED_SCREENSHOT_SHA256
    assert sha256(GOVERNED_PINE) == GOVERNED_FULL_SPAN_PINE_SHA256
    assert sha256(GOVERNED_PINE) != HISTORICAL_CATEGORICAL_PINE_SHA256


def test_governed_pine_structurally_uses_full_span_and_all_liquidity_levels() -> None:
    source = GOVERNED_PINE.read_text(encoding="utf-8")
    assert source.startswith('//@version=6\nindicator("Randle AI - Level Map Helper v14 Canonical"')
    assert '\\"version\\":\\"v14_canonical_liquidity_sender\\"' in source
    assert "stackEligibleIndex" not in source
    assert "ufUnion" not in source
    assert "ufFind" not in source
    assert "buildFullSpanSide" in source
    assert "proposedHighest - proposedLowest <= stackThreshold" in source
    assert "commitFullSpanCandidate" in source
    assert 'yhStackGroup_lock  := yhStackGroup_raw' in source
    assert 'ylStackGroup_lock  := ylStackGroup_raw' in source
    assert 'string yhStackGroup  = sessionLocked ? yhStackGroup_lock  : yhStackGroup_raw' in source
    assert 'string ylStackGroup  = sessionLocked ? ylStackGroup_lock  : ylStackGroup_raw' in source
    assert 'pushLevel("YH",  YH_eff,  YH_live,  "PRIOR RTH", yhStatus_eff,  yhStackGroup)' in source
    assert 'pushLevel("YL",  YL_eff,  YL_live,  "PRIOR RTH", ylStatus_eff,  ylStackGroup)' in source
    assert '+ "\\\"YH\\\":" + payloadLevelJson(0)' in source
    assert '+ "\\\"YL\\\":" + payloadLevelJson(1)' in source
    assert 'input.float(10.0, "Stack Group Threshold % of Daily ATR"' in source
    assert '+ "\\\"session_lock_price\\\":" + f_json_num(sessionLockPrice_eff)' in source
    assert '+ "\\\"stack_threshold\\\":" + f_json_num(stackThreshold_eff)' in source
    assert '+ "\\\"timestamp\\\":" + f_json_str(canonicalSourceTimestamp)' in source
    assert '+ "\\\"session_date\\\":" + f_json_str(canonicalSessionDate)' in source


@requires_historical_evidence
def test_historical_replacement_is_evidence_not_current_authority() -> None:
    historical = HISTORICAL_CATEGORICAL_PINE.read_text(encoding="utf-8")
    replacement = (EVIDENCE_DIR / "REPLACE_STACK_GROUP_SECTION.pine").read_text(encoding="utf-8")
    assert "stackEligibleIndex" in historical
    assert 'string yhStackGroup  = "NONE"' in historical
    assert "stackEligibleIndex" in replacement
    assert "stackEligibleIndex" not in GOVERNED_PINE.read_text(encoding="utf-8")


def test_yh_joins_when_complete_high_span_is_within_threshold() -> None:
    levels = {"PMH": active_level(100), "LH": active_level(103), "ONH": active_level(104), "YH": active_level(105)}
    labels, components = calculate_full_span_stacks(levels, current_price=90, threshold=5)
    assert {labels[name] for name in levels} == {"HIGH 1"}
    assert components[0]["innermost_liquidity_level"] == 100
    assert components[0]["outermost_liquidity_level"] == 105
    assert components[0]["span"] == 5


def test_yh_remains_independent_when_complete_high_span_exceeds_threshold() -> None:
    levels = {"PMH": active_level(100), "LH": active_level(103), "ONH": active_level(104), "YH": active_level(106)}
    labels, _ = calculate_full_span_stacks(levels, current_price=90, threshold=5)
    assert labels["PMH"] == labels["LH"] == labels["ONH"] == "HIGH 1"
    assert labels["YH"] == "NONE"


def test_yl_joins_and_splits_by_complete_low_span() -> None:
    joining = {"PML": active_level(80), "LL": active_level(78), "ONL": active_level(77), "YL": active_level(75)}
    labels, _ = calculate_full_span_stacks(joining, current_price=90, threshold=5)
    assert {labels[name] for name in joining} == {"LOW 1"}

    split = copy.deepcopy(joining)
    split["YL"]["price"] = 74
    labels, _ = calculate_full_span_stacks(split, current_price=90, threshold=5)
    assert labels["PML"] == labels["LL"] == labels["ONL"] == "LOW 1"
    assert labels["YL"] == "NONE"


def test_pairwise_adjacency_cannot_create_transitive_over_span_stack() -> None:
    high = {"PMH": active_level(100), "ONH": active_level(104), "YH": active_level(108)}
    labels, components = calculate_full_span_stacks(high, current_price=90, threshold=5)
    assert labels["PMH"] == labels["ONH"] == "HIGH 1"
    assert labels["YH"] == "NONE"
    assert max(component["span"] for component in components) <= 5

    low = {"PML": active_level(100), "ONL": active_level(96), "YL": active_level(92)}
    labels, components = calculate_full_span_stacks(low, current_price=110, threshold=5)
    assert labels["PML"] == labels["ONL"] == "LOW 1"
    assert labels["YL"] == "NONE"
    assert max(component["span"] for component in components) <= 5


def test_equal_price_yh_and_yl_may_stack() -> None:
    levels = {
        "YH": active_level(100),
        "ONH": active_level(100),
        "YL": active_level(80),
        "ONL": active_level(80),
    }
    labels, _ = calculate_full_span_stacks(levels, current_price=90, threshold=0)
    assert labels["YH"] == labels["ONH"] == "HIGH 1"
    assert labels["YL"] == labels["ONL"] == "LOW 1"


def test_multiple_independent_stacks_keep_nearest_outward_numbering() -> None:
    high = {"PMH": active_level(100), "LH": active_level(101), "ONH": active_level(110), "YH": active_level(111)}
    labels, _ = calculate_full_span_stacks(high, current_price=90, threshold=2)
    assert labels["PMH"] == labels["LH"] == "HIGH 1"
    assert labels["ONH"] == labels["YH"] == "HIGH 2"

    low = {"PML": active_level(110), "LL": active_level(109), "ONL": active_level(100), "YL": active_level(99)}
    labels, _ = calculate_full_span_stacks(low, current_price=120, threshold=2)
    assert labels["PML"] == labels["LL"] == "LOW 1"
    assert labels["ONL"] == labels["YL"] == "LOW 2"


def test_next_member_is_checked_against_complete_candidate_span() -> None:
    levels = {"PMH": active_level(100), "LH": active_level(105), "YH": active_level(110)}
    labels, _ = calculate_full_span_stacks(levels, current_price=90, threshold=6)
    assert labels["PMH"] == labels["LH"] == "HIGH 1"
    assert labels["YH"] == "NONE"


def test_ym_20260716_result_and_target_anchors_are_correct_for_full_span_reason() -> None:
    levels = {
        "YH": active_level(53088),
        "ONH": active_level(53057),
        "LH": active_level(53057),
        "PMH": active_level(53002),
        "PML": active_level(52880),
        "LL": active_level(52835),
        "ONL": active_level(52832),
        "YL": active_level(52680),
    }
    labels, components = calculate_full_span_stacks(levels, current_price=52950, threshold=60)
    assert labels == {
        "YH": "NONE",
        "YL": "NONE",
        "ONH": "HIGH 1",
        "ONL": "LOW 1",
        "LH": "HIGH 1",
        "LL": "LOW 1",
        "PMH": "HIGH 1",
        "PML": "LOW 1",
    }
    assert 53088 - 53002 > 60
    assert 53057 - 53002 <= 60
    assert ordered_table_names(levels, 52950) == (["YH", "ONH", "LH", "PMH"], ["PML", "LL", "ONL", "YL"])
    assert target_anchors(levels, labels, components, 52950) == ([53057.0, 53088.0], [52832.0, 52680.0])
    assert (53057 + 53088) / 2 == 53072.5
    assert 53057 + (53088 - 53057) * 0.75 == 53080.25


def test_nq_equivalent_high_and_low_prior_rth_membership() -> None:
    levels = {
        "PMH": active_level(29457.25),
        "LH": active_level(29459.00),
        "YH": active_level(29461.00),
        "PML": active_level(29363.50),
        "LL": active_level(29361.00),
        "ONL": active_level(29361.00),
        "YL": active_level(29360.00),
    }
    labels, _ = calculate_full_span_stacks(levels, current_price=29400, threshold=4)
    assert labels["PMH"] == labels["LH"] == labels["YH"] == "HIGH 1"
    assert labels["PML"] == labels["LL"] == labels["ONL"] == labels["YL"] == "LOW 1"

    levels["YH"]["price"] = 29463.00
    labels, _ = calculate_full_span_stacks(levels, current_price=29400, threshold=4)
    assert labels["YH"] == "NONE"


def test_existing_valid_stacks_without_prior_rth_are_unchanged() -> None:
    levels = {"PMH": active_level(100), "LH": active_level(102), "ONH": active_level(103)}
    labels, components = calculate_full_span_stacks(levels, current_price=90, threshold=3)
    assert labels == {"ONH": "HIGH 1", "LH": "HIGH 1", "PMH": "HIGH 1"}
    assert components[0]["span"] == 3


@requires_canonical_stack_runtime
def test_frozen_threshold_is_preferred_and_legacy_daily_atr_fallback_keeps_tick_normalization() -> None:
    assert stack_threshold_from_context({"symbol": "NQ1!", "stack_threshold": 60, "daily_atr14": 1}) == 60
    assert stack_threshold_from_context({"symbol": "NQ1!", "daily_atr14": 312.75}) == 31.25
    assert stack_threshold_from_context({"symbol": "YM1!", "daily_atr14": 605}) == 61.0


@requires_canonical_stack_runtime
def test_freeze_restore_late_start_table_and_webhook_preserve_valid_yh_yl_membership() -> None:
    levels = {
        "YH": active_level(105),
        "ONH": active_level(102),
        "PMH": active_level(100),
        "YL": active_level(75),
        "ONL": active_level(78),
        "PML": active_level(80),
    }
    labels, _ = calculate_full_span_stacks(levels, current_price=90, threshold=5)
    frozen_levels = json.loads(json.dumps(project_levels(levels, labels)))
    context = receiver_payload(frozen_levels, reference=90, threshold=5)
    built, error = tv_context_server.build_context(context)
    assert error is None
    assert built is not None
    assert built["levels"]["YH"]["stack_group"] == "HIGH 1"
    assert built["levels"]["YL"]["stack_group"] == "LOW 1"
    assert {row["name"] for row in built["liquidity_map"]["stacks"]} == {"HIGH 1", "LOW 1"}

    frozen = entry_agent.build_session_locked_tv_context(copy.deepcopy(built))
    late_start = entry_agent.build_session_locked_tv_context(copy.deepcopy(built))
    assert frozen is not None and frozen["locked"] is True
    assert late_start == frozen
    assert frozen["active_levels"]["YH"]["stack_group"] == "HIGH 1"
    assert frozen["active_levels"]["YL"]["stack_group"] == "LOW 1"


def test_table_and_webhook_rows_use_the_same_full_span_assignments() -> None:
    levels = {
        "YH": active_level(105),
        "ONH": active_level(103),
        "PMH": active_level(100),
        "YL": active_level(74),
        "ONL": active_level(78),
        "PML": active_level(80),
    }
    labels, _ = calculate_full_span_stacks(levels, current_price=90, threshold=5)
    table_rows = {name: labels[name] for name in levels}
    webhook_rows = {
        name: details["stack_group"]
        for name, details in project_levels(levels, labels).items()
    }
    assert table_rows == webhook_rows
    assert table_rows["YH"] == "HIGH 1"
    assert table_rows["YL"] == "NONE"


@requires_canonical_stack_runtime
def test_receiver_and_session_lock_accept_valid_prior_rth_membership() -> None:
    levels = {"PMH": active_level(100, "HIGH 1"), "ONH": active_level(103, "HIGH 1"), "YH": active_level(105, "HIGH 1")}
    context, error = tv_context_server.build_context(receiver_payload(levels, reference=90, threshold=5))
    assert error is None and context is not None
    assert context["liquidity_map"]["stacks"][0]["components"] == ["PMH", "ONH", "YH"]
    groups = entry_agent.active_liquidity_groups_from_context(context)
    assert entry_agent.validate_session_liquidity_lock(
        levels,
        groups,
        stack_threshold=5,
        session_reference_price=90,
    ) is None

    explicit_payload = receiver_payload(
        levels,
        reference=90,
        threshold=5,
        stacks=[{"name": "PMH/ONH/YH Stack", "members": ["PMH", "ONH", "YH"]}],
    )
    explicit_context, explicit_error = tv_context_server.build_context(explicit_payload)
    assert explicit_error is None and explicit_context is not None


@requires_canonical_stack_runtime
def test_receiver_and_session_lock_reject_full_span_violation() -> None:
    levels = {"PMH": active_level(100, "HIGH 1"), "ONH": active_level(104, "HIGH 1"), "YH": active_level(108, "HIGH 1")}
    context, error = tv_context_server.build_context(receiver_payload(levels, reference=90, threshold=5))
    assert context is None
    assert error is not None and error["code"] == "STACK_FULL_SPAN_EXCEEDED"
    groups = [{"stack_group": "HIGH 1", "components": ["PMH", "ONH", "YH"]}]
    lock_error = entry_agent.validate_session_liquidity_lock(
        levels,
        groups,
        stack_threshold=5,
        session_reference_price=90,
    )
    assert lock_error is not None and "STACK_FULL_SPAN_EXCEEDED" in lock_error


@requires_canonical_stack_runtime
def test_receiver_rejects_mixed_side_and_row_explicit_mismatch() -> None:
    mixed = {"YH": active_level(95, "HIGH 1"), "ONL": active_level(85, "HIGH 1")}
    _, error = tv_context_server.build_context(receiver_payload(mixed, reference=90, threshold=20))
    assert error is not None and error["code"] == "STACK_MEMBER_SIDE_MISMATCH"

    levels = {"PMH": active_level(100, "HIGH 1"), "YH": active_level(105, "HIGH 1")}
    payload = receiver_payload(
        levels,
        reference=90,
        threshold=5,
        stacks=[{"name": "HIGH 1", "members": ["PMH"]}],
    )
    _, error = tv_context_server.build_context(payload)
    assert error is not None and error["code"] == "STACK_MEMBERSHIP_MISMATCH"


@pytest.mark.parametrize(
    ("levels", "stacks", "code"),
    [
        (
            {"PMH": active_level(100, "HIGH 1"), "YH": active_level(101, "HIGH 1")},
            [{"name": "HIGH 1", "members": ["PMH", "BAD"]}],
            "STACK_MEMBER_UNKNOWN",
        ),
        (
            {"PMH": active_level(100, "HIGH 1"), "YH": active_level(101, "HIGH 1")},
            [{"name": "HIGH 1", "members": ["PMH", "PMH"]}],
            "STACK_MEMBER_DUPLICATE",
        ),
        (
            {
                "PMH": active_level(100, "HIGH 1"),
                "LH": active_level(101, "HIGH 1"),
                "ONH": active_level(102, "HIGH 2"),
                "YH": active_level(103, "HIGH 2"),
            },
            [
                {"name": "HIGH 1", "members": ["PMH", "LH"]},
                {"name": "HIGH 2", "members": ["LH", "ONH", "YH"]},
            ],
            "STACK_MEMBERSHIP_MISMATCH",
        ),
    ],
)
@requires_canonical_stack_runtime
def test_receiver_rejects_unknown_duplicate_and_overlapping_definitions(
    levels: dict[str, dict[str, object]],
    stacks: list[dict[str, object]],
    code: str,
) -> None:
    _, error = tv_context_server.build_context(receiver_payload(levels, reference=90, threshold=10, stacks=stacks))
    assert error is not None and error["code"] == code


@requires_canonical_stack_runtime
def test_receiver_rejects_nondeterministic_numbering() -> None:
    levels = {
        "PMH": active_level(100, "HIGH 2"),
        "LH": active_level(101, "HIGH 2"),
        "ONH": active_level(110, "HIGH 1"),
        "YH": active_level(111, "HIGH 1"),
    }
    _, error = tv_context_server.build_context(receiver_payload(levels, reference=90, threshold=2))
    assert error is not None and error["code"] == "STACK_NUMBERING_INVALID"


@requires_canonical_stack_runtime
def test_missing_frozen_threshold_or_reference_fails_closed_for_prior_rth_membership() -> None:
    levels = {"PMH": active_level(100, "HIGH 1"), "YH": active_level(101, "HIGH 1")}
    assert validate_liquidity_stack_structure(levels, stack_threshold=None, session_reference_price=90)["code"] == "STACK_THRESHOLD_MISSING"
    assert validate_liquidity_stack_structure(levels, stack_threshold=2, session_reference_price=None)["code"] == "STACK_REFERENCE_PRICE_MISSING"


@requires_canonical_stack_runtime
def test_exact_invalid_route_is_archived_without_mutating_authority(tmp_path: Path) -> None:
    original_path = tv_context_server.TV_CONTEXT_EVENTS_PATH
    tv_context_server.TV_CONTEXT_EVENTS_PATH = tmp_path / "tv_context_events.jsonl"
    try:
        levels = {"PMH": active_level(100, "HIGH 1"), "ONH": active_level(104, "HIGH 1"), "YH": active_level(108, "HIGH 1")}
        payload = receiver_payload(levels, reference=90, threshold=5)
        response = tv_context_server.app.test_client().post("/webhook/tv-context", json=payload)
        assert response.status_code == 400
        receipt = json.loads(tv_context_server.TV_CONTEXT_EVENTS_PATH.read_text(encoding="utf-8"))
        assert receipt["schema_version"] == "tv_context_receipt_v2"
        assert receipt["acceptance_result"] == "rejected"
        assert receipt["rejection"]["code"] == "STACK_FULL_SPAN_EXCEEDED"
        assert receipt["received_payload"] == payload
    finally:
        tv_context_server.TV_CONTEXT_EVENTS_PATH = original_path


@requires_canonical_stack_runtime
def test_force_and_frozen_rebuild_routes_use_the_same_structural_validation() -> None:
    invalid_levels = {"PMH": active_level(100, "HIGH 1"), "ONH": active_level(104, "HIGH 1"), "YH": active_level(108, "HIGH 1")}
    _, error = tv_context_server.build_context(receiver_payload(invalid_levels, threshold=5), force=True)
    assert error is not None and error["code"] == "STACK_FULL_SPAN_EXCEEDED"

    locked_tv = receiver_payload(
        {"PMH": active_level(100, "HIGH 1"), "ONH": active_level(104, "HIGH 1")},
        threshold=5,
    )
    current_market_time = datetime.now(ZoneInfo("America/Los_Angeles")).replace(
        hour=6,
        minute=15,
        second=0,
        microsecond=0,
    )
    current_session_date = current_market_time.date().isoformat()
    locked_tv["timestamp"] = current_market_time.isoformat()
    locked_tv["session_date"] = current_session_date
    session_lock = {"locked": True, "disabled": False, "tv_context": locked_tv}
    invalid_rebuild_levels = {
        "PMH": active_level(100, "HIGH 1"),
        "ONH": active_level(108, "HIGH 1"),
    }
    route_context = {
        "last_tv_context_levels": invalid_rebuild_levels,
        "last_tv_context_session_date": current_session_date,
        "session_date": current_session_date,
        "received_at": current_market_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    rebuilt, rebuild_error = tv_context_server._rebuild_frozen_lock_from_latest_tv("YM", route_context, session_lock)
    assert rebuilt is None
    assert rebuild_error == {"error": "rebuilt_frozen_lock_invalid"}


@requires_canonical_stack_runtime
def test_valid_locked_context_rehydration_rejects_span_invalid_legacy_authority() -> None:
    valid = receiver_payload({"PMH": active_level(100, "HIGH 1"), "YH": active_level(105, "HIGH 1")}, threshold=5)
    invalid = receiver_payload({"PMH": active_level(100, "HIGH 1"), "YH": active_level(106, "HIGH 1")}, threshold=5)
    assert entry_agent.valid_locked_tv_context(valid) is True
    assert entry_agent.valid_locked_tv_context(invalid) is False


@requires_canonical_stack_runtime
def test_operator_projection_never_repairs_membership_by_nearest_pairwise_distance() -> None:
    rows = [
        {"name": "PMH", **active_level(100, "HIGH 1")},
        {"name": "ONH", **active_level(104, "HIGH 1")},
        {"name": "YH", **active_level(108, "NONE")},
    ]
    locked = [{"name": "HIGH 1", "members": ["PMH", "ONH"]}]
    projected, stacks = entry_agent.projected_frozen_stack_groups(
        rows,
        active_groups=[],
        locked_stacks=locked,
        daily_atr=50,
        stack_threshold=5,
        session_reference_price=90,
    )
    assert projected == {"PMH": "HIGH 1", "ONH": "HIGH 1", "YH": None}
    assert stacks == locked

    invalid_locked = [{"name": "HIGH 1", "members": ["PMH", "ONH", "YH"]}]
    projected, stacks = entry_agent.projected_frozen_stack_groups(
        [{**row, "stack_group": "HIGH 1"} for row in rows],
        active_groups=[],
        locked_stacks=invalid_locked,
        daily_atr=50,
        stack_threshold=5,
        session_reference_price=90,
    )
    assert projected == {"PMH": None, "ONH": None, "YH": None}
    assert stacks == []


@requires_canonical_stack_runtime
def test_persisted_invalid_session_lock_is_disabled_without_mutating_persisted_bytes() -> None:
    invalid_tv = receiver_payload(
        {"PMH": active_level(100, "HIGH 1"), "YH": active_level(108, "HIGH 1")},
        threshold=5,
    )
    persisted = {
        "state_by_symbol": {
            "YM": {
                "session_liquidity_context": {
                    "locked": True,
                    "disabled": False,
                    "active_levels": copy.deepcopy(invalid_tv["levels"]),
                    "active_groups": [{"stack_group": "HIGH 1", "components": ["PMH", "YH"]}],
                    "tv_context": invalid_tv,
                }
            }
        }
    }
    before = json.dumps(persisted, sort_keys=True)
    projected = entry_agent.locked_session_liquidity_context(persisted, "YM")
    assert projected is not None and projected["disabled"] is True and projected["locked"] is False
    assert "STACK_AUTHORITY_INVALID" in projected["error"]
    assert json.dumps(persisted, sort_keys=True) == before


@requires_canonical_stack_runtime
def test_historical_fixture_with_yh_is_judged_by_span_not_identity() -> None:
    levels = {"ONH": active_level(100, "HIGH 1"), "YH": active_level(102, "HIGH 1")}
    assert validate_liquidity_stack_structure(levels, stack_threshold=2, session_reference_price=90) is None
    error = validate_liquidity_stack_structure(levels, stack_threshold=1.99, session_reference_price=90)
    assert error is not None and error["code"] == "STACK_FULL_SPAN_EXCEEDED"
