"""Read-only Entry Agent demo harness for deterministic Step 2-5 scenarios."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from blueprint_rules import evaluate_step_2_1a_candle, step_2_1a_initial_state
from step25_engine import evaluate_step25
from step3_engine import evaluate_step3
from step4_engine import evaluate_step4, initialize_leg1_window
from step5_engine import evaluate_step5


ROOT_DIR = Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT_DIR / "Data" / "entry_agent_demo_cases"
LIBRARY_FOLDERS = ("known_good", "regressions", "investigations")
KEY_LEVELS = ("PMH", "PML", "LH", "LL", "ONH", "ONL", "YH", "YL")
OUTPUT_FIELDS = (
    "step",
    "pathway_type",
    "continuation_type",
    "rejection_mode_entered",
    "sr_rs_context",
    "active_liquidity_name",
    "liquidity_price",
    "setup_direction",
    "current_pathway_control",
    "current_controlling_mode",
    "current_continuation_type",
    "leg1_state",
    "leg1_reference",
    "leg1_extreme",
    "leg1_completed_at",
    "leg1_window_candle_index",
    "leg1_window_remaining",
    "rejection_leg1_progress_pct",
    "rejection_leg1_50_reached",
    "leg2_state",
    "leg2_candidate_candle",
    "leg2_reference_price",
    "rejection_leg2_progress_pct",
    "rejection_leg2_75_reached",
    "step5_confirmed",
    "invalidation_reason",
    "wait_reason",
    "last_decision",
)
EMPTY_CANDLE_SLOT = {
    "time": None,
    "open": None,
    "high": None,
    "low": None,
    "close": None,
    "state_note": None,
    "through": None,
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fixture_path(name: str) -> Path:
    normalized = name.replace("\\", "/").strip("/")
    safe_name = normalized if normalized.endswith(".json") else f"{normalized}.json"
    path = (FIXTURE_DIR / safe_name).resolve()
    fixture_root = FIXTURE_DIR.resolve()
    if fixture_root not in path.parents and path != fixture_root:
        raise FileNotFoundError(f"Entry Agent demo fixture not found: {name}")
    if not path.exists():
        raise FileNotFoundError(f"Entry Agent demo fixture not found: {path}")
    return path


def list_fixtures() -> list[str]:
    if not FIXTURE_DIR.exists():
        return []
    names: list[str] = []
    for path in FIXTURE_DIR.rglob("*.json"):
        if path.name == "index.json":
            continue
        names.append(path.relative_to(FIXTURE_DIR).with_suffix("").as_posix())
    return sorted(names)


def list_fixture_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for fixture_id in list_fixtures():
        fixture = load_fixture(fixture_id)
        folder = fixture_id.split("/", 1)[0] if "/" in fixture_id else "root"
        review_status = fixture_review_status(fixture)
        entries.append(
            {
                "id": fixture_id,
                "folder": folder if folder in LIBRARY_FOLDERS else "known_good",
                "case_name": fixture.get("case_name"),
                "case_type": fixture.get("case_type"),
                "review_status": review_status,
                "user_review": fixture.get("user_review"),
                "status": fixture.get("status"),
                "review_label": fixture_review_label(fixture_id, fixture, review_status),
                "scenario_type": fixture.get("scenario_type"),
                "continuation_type": fixture.get("continuation_type"),
                "issue": fixture.get("issue"),
                "expected_result": fixture.get("expected_result"),
                "deprecated": bool(fixture.get("deprecated")),
                "hidden_from_review": bool(fixture.get("hidden_from_review")),
            }
        )
    return entries


def fixture_review_status(fixture: dict[str, Any]) -> str:
    if fixture.get("deprecated") or fixture.get("hidden_from_review"):
        return str(fixture.get("review_status") or "RETRACTED / NOT APPROVED")
    for key in ("review_status", "user_review", "status"):
        value = fixture.get(key)
        if value:
            return str(value)
    if fixture.get("case_type") == "investigation":
        return "INVESTIGATION"
    return "PENDING REVIEW"


def fixture_review_label(fixture_id: str, fixture: dict[str, Any], review_status: str | None = None) -> str:
    status = str(review_status or fixture_review_status(fixture)).upper()
    short_id = fixture_id.replace("known_good/step2_rejection/", "")
    if "APPROVED" in status and "NOT APPROVED" not in status and "RETRACTED" not in status:
        return f"[APPROVED] {short_id}"
    if "RETRACTED" in status or "NOT APPROVED" in status:
        return f"[RETRACTED] {short_id}"
    if "INVESTIGATION" in status:
        return f"[INVESTIGATION] {short_id}"
    return f"[PENDING] {short_id}"


def load_fixture(name: str) -> dict[str, Any]:
    fixture = read_json(fixture_path(name))
    validate_fixture(fixture)
    return fixture


def validate_fixture(fixture: dict[str, Any]) -> None:
    for key in ("case_name", "scenario_type", "symbol", "date", "levels", "candles", "expected"):
        if key not in fixture:
            raise ValueError(f"Fixture missing required field: {key}")
    if fixture["scenario_type"] not in {"rejection", "continuation"}:
        raise ValueError("scenario_type must be rejection or continuation")
    if fixture["scenario_type"] == "continuation" and fixture.get("continuation_type") not in {"R/S", "S/R"}:
        raise ValueError("continuation fixtures require continuation_type R/S or S/R")
    if len(fixture["candles"]) != len(fixture["expected"]):
        raise ValueError("candles and expected must have the same length")


def normalize_candle(candle: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(candle)
    normalized["timestamp"] = normalized.get("timestamp") or normalized.get("time")
    return normalized


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def level_side(level: dict[str, Any]) -> str:
    side = str(level.get("side") or "").upper()
    if side in {"HIGH", "UPPER"}:
        return "upper"
    if side in {"LOW", "LOWER"}:
        return "lower"
    raise ValueError(f"Unsupported liquidity side: {side}")


def stack_analysis(fixture: dict[str, Any]) -> dict[str, Any]:
    daily_atr = as_float(fixture.get("simulated_daily_atr"))
    threshold = None if daily_atr is None else round(daily_atr * 0.10, 10)
    level_rows: list[dict[str, Any]] = []
    for name, level in dict(fixture.get("levels") or {}).items():
        price = as_float(level.get("price"))
        side = str(level.get("side") or "").upper()
        if price is None or side not in {"HIGH", "LOW"}:
            continue
        level_rows.append({"name": name, "price": price, "side": side})

    distances: list[dict[str, Any]] = []
    detected_groups: list[dict[str, Any]] = []
    group_counts = {"HIGH": 0, "LOW": 0}

    for side in ("HIGH", "LOW"):
        rows = sorted([row for row in level_rows if row["side"] == side], key=lambda row: row["price"])
        for left_index, left in enumerate(rows):
            for right in rows[left_index + 1 :]:
                distance = round(abs(right["price"] - left["price"]), 10)
                distances.append(
                    {
                        "levels": [left["name"], right["name"]],
                        "side": side,
                        "distance": distance,
                        "within_threshold": None if threshold is None else distance <= threshold,
                    }
                )
        if threshold is None:
            for row in rows:
                group_counts[side] += 1
                detected_groups.append(stack_group([row], side, group_counts[side], False))
            continue

        stacked_level_names: set[str] = set()
        for start_index, start in enumerate(rows):
            current = [start]
            for candidate in rows[start_index + 1 :]:
                if abs(candidate["price"] - start["price"]) <= threshold:
                    current.append(candidate)
                    continue
                break
            if len(current) > 1:
                group_counts[side] += 1
                detected_groups.append(stack_group(current, side, group_counts[side], True))
                stacked_level_names.update(row["name"] for row in current)

        for row in rows:
            if row["name"] in stacked_level_names:
                continue
            group_counts[side] += 1
            detected_groups.append(stack_group([row], side, group_counts[side], True))

    manual_stacks = [normalize_stack(stack) for stack in fixture.get("stacks") or []]
    detected_stacks = [group for group in detected_groups if len(group["components"]) > 1]
    non_stacked = [group for group in detected_groups if len(group["components"]) == 1]
    return {
        "simulated_daily_atr": daily_atr,
        "stack_threshold": threshold,
        "rule": "distance <= simulated_daily_atr * 0.10 stacks; distance > threshold splits",
        "distances": distances,
        "detected_groups": detected_groups,
        "detected_stacks": detected_stacks,
        "non_stacked_levels": non_stacked,
        "manual_stacks": manual_stacks,
        "using_manual_stacks": bool(manual_stacks),
    }


def stack_group(rows: list[dict[str, Any]], side: str, number: int, atr_detected: bool) -> dict[str, Any]:
    prices = [row["price"] for row in rows]
    display_rows = sorted(rows, key=lambda row: row["price"], reverse=(side == "LOW"))
    components = [row["name"] for row in display_rows]
    if side == "HIGH":
        close_row = min(rows, key=lambda row: row["price"])
        extreme_row = max(rows, key=lambda row: row["price"])
    else:
        close_row = max(rows, key=lambda row: row["price"])
        extreme_row = min(rows, key=lambda row: row["price"])
    qualification_boundary = extreme_row["price"]
    return {
        "name": "/".join(components),
        "display_name": f"{'/'.join(components)} Liquidity",
        "components": components,
        "price": qualification_boundary,
        "side": side,
        "liquidity_group": f"{side} {number}",
        "close_boundary_level": close_row["name"],
        "close_boundary_price": close_row["price"],
        "extreme_boundary_level": extreme_row["name"],
        "extreme_boundary_price": extreme_row["price"],
        "qualification_boundary_price": qualification_boundary,
        "outer_distance": round(max(prices) - min(prices), 10) if prices else None,
        "atr_detected": atr_detected,
        "level_type": "stacked" if len(components) > 1 else "regular",
    }


def normalize_stack(stack: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(stack)
    components = list(normalized.get("components") or [normalized.get("name")])
    normalized["components"] = components
    normalized["name"] = str(normalized.get("name") or "/".join(str(item) for item in components))
    normalized["display_name"] = normalized["name"] if normalized["name"].endswith(" Liquidity") else f"{normalized['name']} Liquidity"
    normalized["price"] = as_float(normalized.get("price"))
    normalized["side"] = str(normalized.get("side") or "").upper()
    normalized["close_boundary_level"] = normalized.get("close_boundary_level") or (components[0] if components else normalized["name"])
    normalized["close_boundary_price"] = as_float(normalized.get("close_boundary_price")) or normalized["price"]
    normalized["extreme_boundary_level"] = normalized.get("extreme_boundary_level") or (components[-1] if components else normalized["name"])
    normalized["extreme_boundary_price"] = as_float(normalized.get("extreme_boundary_price")) or normalized["price"]
    normalized["qualification_boundary_price"] = as_float(normalized.get("qualification_boundary_price")) or normalized["price"]
    normalized["liquidity_group"] = normalized.get("liquidity_group") or "fixture-defined"
    normalized["level_type"] = "stacked" if len(components) > 1 else "regular"
    return normalized


def detected_group_for_active(fixture: dict[str, Any], active_name: str | None) -> dict[str, Any] | None:
    if not active_name:
        return None
    analysis = stack_analysis(fixture)
    for group in analysis["detected_groups"]:
        if active_name == group["name"] or active_name in group["components"]:
            return group
    return None


def setup_direction_for_side(side: str) -> str:
    return "SHORT" if side == "upper" else "LONG"


def active_liquidity_config(fixture: dict[str, Any]) -> dict[str, Any]:
    analysis = stack_analysis(fixture)
    if isinstance(fixture.get("active_liquidity"), dict):
        active = dict(fixture["active_liquidity"])
        if not fixture.get("stacks") and analysis.get("simulated_daily_atr") is not None:
            active_name = str(active.get("name") or "")
            detected = detected_group_for_active(fixture, active_name)
            if detected is not None:
                active = dict(detected)
    elif fixture.get("stacks"):
        active = normalize_stack(fixture["stacks"][0])
    elif analysis["detected_stacks"]:
        active = dict(analysis["detected_stacks"][0])
    else:
        name, level = next(iter(dict(fixture["levels"]).items()))
        active = {**dict(level), "name": name, "components": [name]}
    active["price"] = as_float(active.get("price"))
    active["side"] = str(active.get("side") or "").upper()
    components = active.get("components") or [str(active.get("name"))]
    active["components"] = list(components)
    display_name = str(active.get("display_name") or active.get("name") or "/".join(active["components"]))
    active["display_name"] = display_name if display_name.endswith(" Liquidity") else f"{display_name} Liquidity"
    inferred = infer_stack_boundaries(fixture, active)
    active["close_boundary_level"] = active.get("close_boundary_level") or inferred.get("close_boundary_level") or (active["components"][0] if active["components"] else active.get("name"))
    active["close_boundary_price"] = first_number(active.get("close_boundary_price"), inferred.get("close_boundary_price"), active["price"])
    active["extreme_boundary_level"] = active.get("extreme_boundary_level") or inferred.get("extreme_boundary_level") or (active["components"][-1] if active["components"] else active.get("name"))
    active["extreme_boundary_price"] = first_number(active.get("extreme_boundary_price"), inferred.get("extreme_boundary_price"), active["price"])
    active["qualification_boundary_price"] = first_number(active.get("qualification_boundary_price"), inferred.get("qualification_boundary_price"), active["price"])
    active["liquidity_group"] = active.get("liquidity_group") or "fixture-defined"
    active["level_type"] = active.get("level_type") or ("stacked" if len(active["components"]) > 1 else "regular")
    return active


def first_number(*values: Any) -> float | None:
    for value in values:
        number = as_float(value)
        if number is not None:
            return number
    return None


def infer_stack_boundaries(fixture: dict[str, Any], active: dict[str, Any]) -> dict[str, Any]:
    components = [str(component) for component in active.get("components") or []]
    levels = dict(fixture.get("levels") or {})
    rows: list[dict[str, Any]] = []
    for component in components:
        level = levels.get(component)
        if not isinstance(level, dict):
            continue
        price = as_float(level.get("price"))
        if price is None:
            continue
        rows.append({"name": component, "price": price, "side": str(level.get("side") or active.get("side") or "").upper()})
    if not rows:
        return {}
    side = str(active.get("side") or rows[0].get("side") or "").upper()
    if side == "HIGH":
        close_row = min(rows, key=lambda row: row["price"])
        extreme_row = max(rows, key=lambda row: row["price"])
    elif side == "LOW":
        close_row = max(rows, key=lambda row: row["price"])
        extreme_row = min(rows, key=lambda row: row["price"])
    else:
        return {}
    return {
        "close_boundary_level": close_row["name"],
        "close_boundary_price": close_row["price"],
        "extreme_boundary_level": extreme_row["name"],
        "extreme_boundary_price": extreme_row["price"],
        "qualification_boundary_price": extreme_row["price"],
    }


def continuation_level_type(fixture: dict[str, Any], active: dict[str, Any]) -> str:
    if fixture.get("continuation_type") == "R/S":
        return "LH"
    if fixture.get("continuation_type") == "S/R":
        return "LL"
    components = [str(item).upper() for item in active.get("components") or []]
    if "LH" in components:
        return "LH"
    if "LL" in components:
        return "LL"
    return "LH" if str(active.get("side")).upper() == "HIGH" else "LL"


def nearest_opposing_liquidity(fixture: dict[str, Any], direction: str, fallback_price: float) -> float:
    prices: list[float] = []
    for level in dict(fixture.get("levels") or {}).values():
        price = as_float(level.get("price"))
        side = str(level.get("side") or "").upper()
        if price is None:
            continue
        if direction == "LONG" and side == "HIGH":
            prices.append(price)
        elif direction == "SHORT" and side == "LOW":
            prices.append(price)
    if prices:
        return min(prices) if direction == "LONG" else max(prices)
    return fallback_price + 100.0 if direction == "LONG" else fallback_price - 100.0


def next_same_side_liquidity(fixture: dict[str, Any], active: dict[str, Any]) -> dict[str, Any] | None:
    configured = fixture.get("next_same_side_liquidity")
    if isinstance(configured, dict):
        price = as_float(configured.get("price"))
        if price is not None:
            return {**configured, "price": price}

    active_price = as_float(active.get("price"))
    active_side = str(active.get("side") or "").upper()
    active_components = {str(item) for item in active.get("components") or []}
    if active_price is None or active_side not in {"HIGH", "LOW"}:
        return None

    candidates: list[dict[str, Any]] = []
    for name, level in dict(fixture.get("levels") or {}).items():
        if name in active_components:
            continue
        price = as_float(level.get("price"))
        side = str(level.get("side") or "").upper()
        if price is None or side != active_side:
            continue
        if active_side == "LOW" and price < active_price:
            candidates.append({"name": name, "price": price, "side": side})
        elif active_side == "HIGH" and price > active_price:
            candidates.append({"name": name, "price": price, "side": side})
    if not candidates:
        return None
    return max(candidates, key=lambda item: item["price"]) if active_side == "LOW" else min(candidates, key=lambda item: item["price"])


def side_travel_probe(candle: dict[str, Any], side: str) -> float | None:
    if str(side).upper() == "LOW":
        return as_float(candle.get("low"))
    if str(side).upper() == "HIGH":
        return as_float(candle.get("high"))
    return None


def travel_progress_percent(start: Any, target: Any, probe: Any) -> int | None:
    start_price = as_float(start)
    target_price = as_float(target)
    probe_price = as_float(probe)
    if start_price is None or target_price is None or probe_price is None or start_price == target_price:
        return None
    total = abs(target_price - start_price)
    traveled = abs(probe_price - start_price)
    if total <= 0:
        return None
    return int(round(max(0.0, min(100.0, traveled / total * 100.0))))


def liquidity_travel_progress(
    *,
    fixture: dict[str, Any],
    active: dict[str, Any],
    candle: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    if fixture.get("scenario_type") != "rejection":
        return {}
    target = next_same_side_liquidity(fixture, active)
    target_price = target.get("price") if target else None
    side = str(active.get("side") or "").upper()
    probe = side_travel_probe(candle, side)
    leg1_progress = travel_progress_percent(active.get("price"), target_price, probe)

    leg2_start = (
        state.get("leg2_start_price")
        or state.get("active_leg1_reference")
        or state.get("active_reference")
        or state.get("leg1_reference")
        or state.get("leg1_reference_price")
    )
    leg2_progress = travel_progress_percent(leg2_start, target_price, probe)
    return {
        "rejection_leg1_progress_pct": leg1_progress,
        "rejection_leg1_50_reached": "YES" if leg1_progress is not None and leg1_progress >= 50 else "NO",
        "rejection_leg2_progress_pct": leg2_progress,
        "rejection_leg2_75_reached": "YES" if leg2_progress is not None and leg2_progress >= 75 else "NO",
    }


def current_pathway_fields(mode: str | None, scenario_type: str, continuation_type: str | None) -> dict[str, Any]:
    if scenario_type == "continuation" or mode in {"R/S", "S/R"}:
        active_type = continuation_type or mode or "none"
        return {
            "current_pathway_control": "continuation",
            "current_controlling_mode": active_type,
            "current_continuation_type": active_type,
            "sr_rs_context": active_type,
        }
    return {
        "current_pathway_control": "rejection",
        "current_controlling_mode": "Normal Rejection Mode",
        "current_continuation_type": "none",
        "sr_rs_context": None,
    }


def status_from_state(
    *,
    fixture: dict[str, Any],
    candle: dict[str, Any],
    step: str,
    active: dict[str, Any],
    state: dict[str, Any],
    reason: str,
    invalidation_reason: str | None = None,
) -> dict[str, Any]:
    scenario_type = fixture["scenario_type"]
    continuation_type = fixture.get("continuation_type") if scenario_type == "continuation" else "none"
    mode = state.get("controlling_mode")
    pathway = current_pathway_fields(mode, scenario_type, continuation_type)
    leg1_state = "COMPLETE" if state.get("leg1_status") in {"COMPLETE", "VALID"} else "WAIT"
    leg2_state = "COMPLETE" if state.get("leg2_status") == "VALIDATED" else state.get("leg2_status") or "WAIT"
    step5_confirmed = bool(state.get("step5_participation_validated") or state.get("leg2_status") == "VALIDATED")
    wait_reason = None if step5_confirmed else reason
    actual = {
        "time": candle.get("timestamp"),
        "step": step,
        "pathway_type": scenario_type.capitalize(),
        "continuation_type": continuation_type,
        "rejection_mode_entered": bool(state.get("rejection_mode") == "ON" or state.get("step_2_activated")),
        "active_liquidity_name": active["display_name"] if state.get("step_2_activated") or step != "Step 1" else None,
        "liquidity_price": active.get("price") if state.get("step_2_activated") or step != "Step 1" else None,
        "setup_direction": state.get("setup_direction"),
        "leg1_state": leg1_state,
        "leg1_reference": state.get("leg1_reference") or state.get("leg1_reference_price"),
        "leg1_extreme": state.get("leg1_extreme") or state.get("anchor_extreme"),
        "leg1_completed_at": state.get("leg1_completed_at") or (state.get("candle_b") or {}).get("timestamp"),
        "leg1_window_candle_index": state.get("leg1_window_candle_index"),
        "leg1_window_remaining": state.get("leg1_window_remaining"),
        "leg2_state": "WAIT" if leg2_state in {"WAIT", None} else leg2_state,
        "leg2_candidate_candle": (state.get("leg2_candle") or {}).get("timestamp"),
        "leg2_reference_price": state.get("active_leg1_reference") or state.get("active_reference"),
        "step5_confirmed": step5_confirmed,
        "invalidation_reason": invalidation_reason,
        "wait_reason": wait_reason,
        "last_decision": f"{'FAIL' if invalidation_reason else 'PASS' if step5_confirmed else 'WAIT'}: {reason}",
    }
    actual.update(liquidity_travel_progress(fixture=fixture, active=active, candle=candle, state=state))
    actual.update(pathway)
    return actual


def step2_only_status(
    *,
    fixture: dict[str, Any],
    candle: dict[str, Any],
    active: dict[str, Any],
    state: dict[str, Any],
    direction: str,
) -> dict[str, Any]:
    scenario_type = fixture["scenario_type"]
    activated = bool(state.get("step_2_activated"))
    actual = {
        "time": candle.get("timestamp"),
        "step": "Step 2" if activated else "Step 1",
        "pathway_type": scenario_type.capitalize(),
        "continuation_type": "none",
        "rejection_mode_entered": activated,
        "active_liquidity_name": active["display_name"] if activated else None,
        "liquidity_price": active.get("price") if activated else None,
        "setup_direction": direction if activated else None,
        "leg1_state": "WAIT",
        "leg1_reference": None,
        "leg1_extreme": None,
        "leg1_completed_at": None,
        "leg1_window_candle_index": None,
        "leg1_window_remaining": None,
        "leg2_state": "WAIT",
        "leg2_candidate_candle": None,
        "leg2_reference_price": None,
        "step5_confirmed": False,
        "invalidation_reason": None,
        "wait_reason": None if activated else "Waiting for Step 2 liquidity close-through.",
        "last_decision": "PASS: Step 2 activated." if activated else "WAIT: close did not qualify for Step 2.",
    }
    actual.update(liquidity_travel_progress(fixture=fixture, active=active, candle=candle, state=state))
    actual.update(current_pathway_fields("Normal Rejection Mode", scenario_type, "none"))
    return actual


def compare_expected_actual(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    diffs = []
    for key, expected_value in expected.items():
        if key == "notes":
            continue
        actual_value = actual.get(key)
        if actual_value != expected_value:
            diffs.append({"field": key, "expected": expected_value, "actual": actual_value})
    return {"pass": not diffs, "diffs": diffs}


def evaluate_continuation_controlling_structure_fixture(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    validate_fixture(fixture)
    continuation_type = fixture.get("continuation_type")
    level = active_liquidity_config(fixture)
    level_price = float(level["price"])
    shared_leg1_valid = bool(fixture.get("shared_leg1_valid"))
    shared_leg2_valid = bool(fixture.get("shared_leg2_valid"))
    candles = [normalize_candle(candle) for candle in fixture["candles"]]
    controlling: dict[str, Any] | None = None
    old_structures: list[dict[str, Any]] = []
    reset_candle: dict[str, Any] | None = None
    was_reset = False
    reclaim_candle: dict[str, Any] | None = None
    sweep_occurred = False
    push_start_index: int | None = None
    push_high: float | None = None
    push_low: float | None = None
    frames: list[dict[str, Any]] = []

    for index, candle in enumerate(candles):
        close = as_float(candle.get("close"))
        open_price = as_float(candle.get("open"))
        high = as_float(candle.get("high"))
        low = as_float(candle.get("low"))

        if continuation_type == "S/R":
            close_through = close is not None and open_price is not None and close < level_price and close < open_price
            reclaim_now = controlling is not None and close is not None and close >= level_price and not close_through
            reset_now = (
                controlling is not None
                and close is not None
                and open_price is not None
                and close > open_price
                and close > float(controlling["close"])
                and close < level_price
                and reclaim_candle is None
            )
            sweep_now = reclaim_candle is not None and controlling is not None and high is not None and high > float(controlling["high"])
            required_sweep_direction = "ABOVE_CONTROLLING_STRUCTURE_HIGH"
        else:
            close_through = close is not None and open_price is not None and close > level_price and close > open_price
            reclaim_now = controlling is not None and close is not None and close <= level_price and not close_through
            reset_now = (
                controlling is not None
                and close is not None
                and open_price is not None
                and close < open_price
                and close < float(controlling["close"])
                and close > level_price
                and reclaim_candle is None
            )
            sweep_now = reclaim_candle is not None and controlling is not None and low is not None and low < float(controlling["low"])
            required_sweep_direction = "BELOW_CONTROLLING_STRUCTURE_LOW"

        if reset_now and controlling is not None:
            old_structures.append({**controlling, "active": False})
            controlling = None
            reset_candle = candle
            was_reset = True
            reclaim_candle = None
            sweep_occurred = False
            push_start_index = None
            push_high = None
            push_low = None

        if close_through:
            if push_start_index is None:
                push_start_index = index
                push_high = high
                push_low = low
            else:
                push_high = max(value for value in (push_high, high) if value is not None)
                push_low = min(value for value in (push_low, low) if value is not None)
            controlling = {
                "high": push_high if push_high is not None else high,
                "low": push_low if push_low is not None else low,
                "close": close,
                "start_index": push_start_index,
                "end_index": index,
                "time": candle.get("timestamp"),
                "source": "last_uninterrupted_close_through_push",
                "active": True,
            }
            reclaim_candle = None
            sweep_occurred = False
        elif not reset_now:
            push_start_index = None
            push_high = None
            push_low = None

        if reclaim_now and reclaim_candle is None:
            reclaim_candle = candle

        if sweep_now:
            sweep_occurred = True

        entry_permission = (
            "CONTINUATION_ENTRY_ALLOWED_AFTER_SWEEP"
            if shared_leg1_valid and shared_leg2_valid and sweep_occurred
            else "WAIT_BLOCKED_NO_CONTROLLING_STRUCTURE_SWEEP"
        )
        active_structure = controlling or {}
        actual = {
            "time": candle.get("timestamp"),
            "rule": fixture.get("rule"),
            "scope": fixture.get("scope"),
            "case_type": fixture.get("case_type"),
            "continuation_type": continuation_type,
            "liquidity_name": level["display_name"],
            "liquidity_price": level.get("price"),
            "close_through_candle": candle.get("timestamp") if close_through else None,
            "reclaim_close_candle": (reclaim_candle or {}).get("timestamp"),
            "controlling_structure_high": active_structure.get("high"),
            "controlling_structure_low": active_structure.get("low"),
            "controlling_structure_close": active_structure.get("close"),
            "controlling_structure_candle_range": [active_structure.get("start_index"), active_structure.get("end_index")]
            if active_structure
            else None,
            "controlling_structure_time": active_structure.get("time"),
            "controlling_structure_reset": was_reset,
            "reset_candle": (reset_candle or {}).get("timestamp"),
            "required_sweep_direction": required_sweep_direction,
            "sweep_occurred": sweep_occurred,
            "shared_leg1_valid": shared_leg1_valid,
            "shared_leg2_valid": shared_leg2_valid,
            "entry_permission": entry_permission,
        }
        expected = dict(fixture["expected"][index])
        comparison = compare_expected_actual(expected, actual)
        frames.append(
            {
                "index": index,
                "candle": candle,
                "expected": expected,
                "actual": actual,
                "debug": {
                    "continuation_controlling_structure": {
                        **actual,
                        "current_controlling_structure": deepcopy(active_structure) if active_structure else None,
                        "old_structures": deepcopy(old_structures),
                    }
                },
                "pass": comparison["pass"],
                "diffs": comparison["diffs"],
            }
        )

    return frames


def close_through_price(candle: dict[str, Any], price: Any, side: str, tick_size: float) -> bool | None:
    close = as_float(candle.get("close"))
    level = as_float(price)
    if close is None or level is None:
        return None
    if str(side).upper() in {"LOW", "LOWER"}:
        return close <= level - tick_size
    if str(side).upper() in {"HIGH", "UPPER"}:
        return close >= level + tick_size
    return None


def wick_beyond_price(candle: dict[str, Any], price: Any, side: str, tick_size: float) -> bool | None:
    level = as_float(price)
    if level is None:
        return None
    if str(side).upper() in {"LOW", "LOWER"}:
        low = as_float(candle.get("low"))
        return None if low is None else low <= level - tick_size
    if str(side).upper() in {"HIGH", "UPPER"}:
        high = as_float(candle.get("high"))
        return None if high is None else high >= level + tick_size
    return None


def distance_beyond_boundary(candle: dict[str, Any], price: Any, side: str) -> float | None:
    close = as_float(candle.get("close"))
    level = as_float(price)
    if close is None or level is None:
        return None
    if str(side).upper() in {"LOW", "LOWER"}:
        return round(level - close, 10)
    if str(side).upper() in {"HIGH", "UPPER"}:
        return round(close - level, 10)
    return None


def step2_qualification_debug(
    *,
    fixture: dict[str, Any],
    active: dict[str, Any],
    candle: dict[str, Any],
    actual: dict[str, Any],
    tick_size: float,
) -> dict[str, Any]:
    close_beyond = close_through_price(candle, active.get("price"), active.get("side"), tick_size)
    expected_result = fixture.get("expected_result")
    actual_result = "valid_step2" if actual.get("rejection_mode_entered") else "ignored"
    pre_close_structure = fixture.get("pre_close_structure") if isinstance(fixture.get("pre_close_structure"), dict) else {}
    inactive = fixture.get("inactive_liquidity") if isinstance(fixture.get("inactive_liquidity"), dict) else {}
    close_through_inactive = close_through_price(candle, inactive.get("price"), inactive.get("side"), tick_size) if inactive else None
    return {
        "active_liquidity": active["display_name"],
        "liquidity_price": active.get("price"),
        "liquidity_type": active.get("level_type") or fixture.get("level_type") or ("stacked" if len(active.get("components") or []) > 1 else "regular"),
        "liquidity_group": active.get("liquidity_group"),
        "stack_components": active.get("components") or [],
        "controlling_boundary": active.get("price"),
        "close_boundary_level": active.get("close_boundary_level"),
        "close_boundary_price": active.get("close_boundary_price"),
        "extreme_boundary_level": active.get("extreme_boundary_level"),
        "extreme_boundary_price": active.get("extreme_boundary_price"),
        "qualification_boundary_price": active.get("qualification_boundary_price"),
        "close_price": candle.get("close"),
        "distance_beyond_boundary": distance_beyond_boundary(candle, active.get("price"), active.get("side")),
        "wick_beyond_boundary": wick_beyond_price(candle, active.get("price"), active.get("side"), tick_size),
        "close_beyond_boundary": close_beyond,
        "expected_result": expected_result,
        "actual_result": actual_result,
        "inactive_reason": inactive.get("inactive_reason"),
        "inactive_level_name": inactive.get("name"),
        "inactive_level_price": inactive.get("price"),
        "is_active_liquidity": inactive.get("is_active_liquidity"),
        "close_through_inactive_level": close_through_inactive,
        "expected_close_through_inactive_level": inactive.get("expected_close_through_inactive_level"),
        "inactive_close_through_note": inactive.get("why_close_through_should_matter"),
        "review_status": "INVESTIGATION" if fixture.get("case_type") == "investigation" else "APPROVED_OR_STANDARD",
        "pass": expected_result == actual_result,
        "why": fixture.get("why"),
        "close_through_candle": candle,
        "pre_close_structure": {
            "controlling_boundary_level": pre_close_structure.get("controlling_boundary_level"),
            "controlling_boundary_price": pre_close_structure.get("controlling_boundary_price"),
            "controlling_boundary_time": pre_close_structure.get("controlling_boundary_time"),
            "controlling_boundary_candle_index": pre_close_structure.get("controlling_boundary_candle_index"),
            "source": pre_close_structure.get("source"),
        },
    }


def chart_line_style(level_name: str) -> dict[str, Any]:
    styles = {
        "PML": {"color": "black", "width": 1, "dash": "dotted"},
        "PMH": {"color": "black", "width": 1, "dash": "dotted"},
        "ONL": {"color": "red", "width": 1, "dash": "solid"},
        "ONH": {"color": "green", "width": 1, "dash": "solid"},
        "YL": {"color": "red", "width": 3, "dash": "solid"},
        "YH": {"color": "green", "width": 3, "dash": "solid"},
        "LH": {"color": "green", "width": 1, "dash": "dotted"},
        "LL": {"color": "red", "width": 1, "dash": "dotted"},
    }
    return dict(styles.get(level_name, {"color": "gray", "width": 1, "dash": "solid"}))


def step2_chart_lines(fixture: dict[str, Any], active: dict[str, Any]) -> list[dict[str, Any]]:
    levels = dict(fixture.get("levels") or {})
    active_components = set(active.get("components") or [])
    lines: list[dict[str, Any]] = []
    for level_name, level in levels.items():
        price = as_float(level.get("price"))
        if price is None:
            continue
        style = chart_line_style(level_name)
        lines.append(
            {
                "name": level_name,
                "price": price,
                "side": level.get("side"),
                "is_stack_component": level_name in active_components,
                "is_qualification_boundary": price == active.get("qualification_boundary_price"),
                **style,
            }
        )
    return lines


def close_through_leg_reference(candle: dict[str, Any], reference: Any, direction: str, tick_size: float) -> bool | None:
    close = as_float(candle.get("close"))
    level = as_float(reference)
    if close is None or level is None:
        return None
    if direction == "LONG":
        return close <= level - tick_size
    if direction == "SHORT":
        return close >= level + tick_size
    return None


def candle_slot(candle: dict[str, Any] | None, note: str | None, through: bool | None) -> dict[str, Any]:
    if not isinstance(candle, dict):
        return dict(EMPTY_CANDLE_SLOT)
    return {
        "time": candle.get("timestamp") or candle.get("time"),
        "open": candle.get("open"),
        "high": candle.get("high"),
        "low": candle.get("low"),
        "close": candle.get("close"),
        "state_note": note,
        "through": through,
    }


def padded_slots(slots: list[dict[str, Any]], size: int = 4) -> list[dict[str, Any]]:
    return (slots + [dict(EMPTY_CANDLE_SLOT) for _ in range(size)])[:size]


def continuation_structure_debug(fixture: dict[str, Any], active: dict[str, Any], candles: list[dict[str, Any]], activation_index: int | None) -> dict[str, Any]:
    if fixture.get("scenario_type") != "continuation":
        return {"high": None, "low": None, "time": None, "candle": None}
    source_index = max(0, (activation_index or 0) - 1)
    candle = candles[source_index] if candles else None
    if not isinstance(candle, dict):
        return {"high": None, "low": None, "time": None, "candle": None}
    return {
        "high": candle.get("high"),
        "low": candle.get("low"),
        "time": candle.get("timestamp"),
        "candle": candle,
    }


def build_debug_payload(
    *,
    fixture: dict[str, Any],
    active: dict[str, Any],
    candles: list[dict[str, Any]],
    current_index: int,
    activation_index: int | None,
    step4_ready_index: int | None,
    state: dict[str, Any],
    direction: str,
    tick_size: float,
) -> dict[str, Any]:
    leg1_reference = state.get("leg1_reference") or state.get("leg1_reference_price")
    structure = continuation_structure_debug(fixture, active, candles, activation_index)

    step24_slots: list[dict[str, Any]] = []
    if activation_index is not None:
        for offset, candle in enumerate(candles[activation_index : current_index + 1][:4], start=1):
            note = "Step 2 activation" if offset == 1 else f"Leg 1 window C{offset - 1}"
            step24_slots.append(candle_slot(candle, note, close_through_price(candle, active.get("price"), active.get("side"), tick_size)))

    step56_slots: list[dict[str, Any]] = []
    if state.get("leg1_status") in {"COMPLETE", "VALID"} and step4_ready_index is not None:
        first_leg2_index = min(current_index, step4_ready_index + 2)
        for offset, candle in enumerate(candles[first_leg2_index : current_index + 1][:4], start=1):
            note = "Leg 2 candidate" if offset == 1 else f"Leg 2 window C{offset}"
            step56_slots.append(candle_slot(candle, note, close_through_leg_reference(candle, leg1_reference, direction, tick_size)))

    return {
        "step2_qualification": step2_qualification_debug(
            fixture=fixture,
            active=active,
            candle=candles[current_index],
            actual=status_from_state(
                fixture=fixture,
                candle=candles[current_index],
                step="Step 2" if state.get("step_2_activated") else "Step 1",
                active=active,
                state=state,
                reason="Step 2 qualification debug.",
            )
            if fixture.get("scope") != "step2_rejection_only"
            else step2_only_status(
                fixture=fixture,
                candle=candles[current_index],
                active=active,
                state=state,
                direction=direction,
            ),
            tick_size=tick_size,
        ),
        "step2_chart_lines": step2_chart_lines(fixture, active),
        "controlling_structure": structure,
        "rejection_step24_candles": padded_slots(step24_slots),
        "rejection_step56_candles": padded_slots(step56_slots),
        "continuation_step24_candles": padded_slots(step24_slots),
        "continuation_step56_candles": padded_slots(step56_slots),
    }


@dataclass
class ScenarioRunner:
    fixture: dict[str, Any]
    frames: list[dict[str, Any]]
    index: int = 0

    @classmethod
    def from_fixture(cls, fixture: dict[str, Any]) -> "ScenarioRunner":
        return cls(fixture=fixture, frames=evaluate_fixture(fixture))

    def current(self) -> dict[str, Any]:
        return self.frames[self.index]

    def next(self) -> dict[str, Any]:
        self.index = min(self.index + 1, len(self.frames) - 1)
        return self.current()

    def previous(self) -> dict[str, Any]:
        self.index = max(self.index - 1, 0)
        return self.current()

    def reset(self) -> dict[str, Any]:
        self.index = 0
        return self.current()

    def run_full(self) -> dict[str, Any]:
        self.index = len(self.frames) - 1
        return {"overall_pass": all(frame["pass"] for frame in self.frames), "frames": self.frames}


def evaluate_fixture(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    validate_fixture(fixture)
    if fixture.get("scope") == "continuation_controlling_structure":
        return evaluate_continuation_controlling_structure_fixture(fixture)
    active = active_liquidity_config(fixture)
    side = level_side(active)
    direction = setup_direction_for_side(side)
    tick_size = as_float(fixture.get("tick_size")) or 0.25
    atr = as_float(fixture.get("atr_1m_14")) or 20.0
    nearest = as_float(fixture.get("nearest_opposing_liquidity")) or nearest_opposing_liquidity(fixture, direction, float(active["price"]))
    candles = [normalize_candle(candle) for candle in fixture["candles"]]
    step2_state = step_2_1a_initial_state("/".join(active["components"]), float(active["price"]), side, tick_size)
    lifecycle: dict[str, Any] = {}
    step4_state: dict[str, Any] | None = None
    step5_state: dict[str, Any] | None = None
    step4_ready_index: int | None = None
    activation_index: int | None = None
    frames: list[dict[str, Any]] = []
    step2_only = fixture.get("scope") == "step2_rejection_only"

    for index, candle in enumerate(candles):
        candle = {**candle, "active_level": "/".join(active["components"]), "level_price": active["price"]}
        expected = dict(fixture["expected"][index])
        invalidation_reason = None
        step = "Step 1"
        reason = "Waiting for Step 2 liquidity close-through."

        if not step2_state.get("step_2_activated") and not step2_state.get("blocked"):
            evaluate_step_2_1a_candle(step2_state, candle, index)
        lifecycle.update(step2_state)

        if step2_state.get("step_2_activated"):
            if activation_index is None:
                activation_index = index
            if step2_only:
                lifecycle.update(step2_state)
                lifecycle.update(
                    {
                        "setup_direction": direction,
                        "active_liquidity": {"name": active["display_name"], "price": active["price"], "components": active["components"]},
                        "active_level": "/".join(active["components"]),
                        "level_price": active["price"],
                        "controlling_mode": "Normal Rejection Mode",
                    }
                )
                actual = step2_only_status(fixture=fixture, candle=candle, active=active, state=lifecycle, direction=direction)
                comparison = compare_expected_actual(expected, actual)
                debug = build_debug_payload(
                    fixture=fixture,
                    active=active,
                    candles=candles,
                    current_index=index,
                    activation_index=activation_index,
                    step4_ready_index=step4_ready_index,
                    state=lifecycle,
                    direction=direction,
                    tick_size=tick_size,
                )
                frames.append(
                    {
                        "index": index,
                        "candle": candle,
                        "expected": expected,
                        "actual": actual,
                        "debug": debug,
                        "pass": comparison["pass"],
                        "diffs": comparison["diffs"],
                    }
                )
                continue
            step = "Step 2"
            activation_candle = step2_state.get("candle_a")
            lifecycle.update(
                {
                    "rejection_mode": "ON",
                    "interaction_state": "ACTIVE",
                    "setup_direction": direction,
                    "active_liquidity": {"name": active["display_name"], "price": active["price"], "components": active["components"]},
                    "active_level": "/".join(active["components"]),
                    "level_price": active["price"],
                    "initial_candle_a": activation_candle,
                    "candle_a": activation_candle,
                    "tick_size": tick_size,
                    "atr_1m_14": atr,
                    "nearest_opposing_liquidity": {"price": nearest},
                    "events": list(lifecycle.get("events") or []),
                }
            )
            reason = "Step 2 activated liquidity interaction."

            if fixture["scenario_type"] == "continuation":
                prev_candle = candles[index - 1] if index > 0 else activation_candle
                lifecycle.update(
                    {
                        "prev_candle": prev_candle,
                        "last_candle": candle,
                        "level": active["price"],
                        "level_type": continuation_level_type(fixture, active),
                        "candidate_modes": [fixture.get("continuation_type")],
                        "rejection_step2_confirmed": True,
                        "active_liquidity_selected": True,
                        "controlling_mode": fixture.get("continuation_type"),
                        "pathway_mode": fixture.get("continuation_type"),
                    }
                )
            else:
                lifecycle.update({"controlling_mode": "Normal Rejection Mode"})

            step25 = evaluate_step25(lifecycle)
            lifecycle.update(step25["state"])
            if step25["status"] == "READY":
                step = "Step 2.5"
                reason = step25["reason"]

                active_stack = active if len(active.get("components") or []) > 1 else None
                step3_input = {
                    **lifecycle,
                    "active_stack": active_stack,
                    "active_liquidity": lifecycle.get("active_liquidity"),
                    "stack_side": side,
                    "side": side,
                    "extreme_boundary": active.get("price"),
                    "latest_candle": candle,
                    "recent_candles": candles[: index + 1],
                }
                step3 = evaluate_step3(step3_input, candles[: index + 1])
                lifecycle.update(step3["state"])
                if step3.get("next_step") == "Step 4":
                    step = "Step 4"
                    reason = step3["reason"]
                    if step4_ready_index is None:
                        step4_ready_index = index
                        initialize_leg1_window(lifecycle, candle.get("timestamp"))

            if step4_ready_index is not None and index > step4_ready_index and not step5_state:
                step4_input = {**lifecycle, **(step4_state or {})}
                step4 = evaluate_step4(step4_input, candle)
                lifecycle.update(step4["state"])
                step4_state = dict(step4["state"])
                step = "Step 4"
                reason = step4["reason"]
                if step4["status"] == "READY":
                    step = "Step 5"
                    step5_state = dict(step4["state"])
                elif step4["status"] == "TERMINATED":
                    invalidation_reason = step4["reason"]

            if step5_state and not invalidation_reason:
                step5 = evaluate_step5({**lifecycle, **step5_state}, candle)
                lifecycle.update(step5["state"])
                step5_state = dict(step5["state"])
                step = "Step 5"
                reason = step5["reason"]
                if step5["status"] == "TERMINATED":
                    invalidation_reason = step5["reason"]

        if step2_only:
            actual = step2_only_status(fixture=fixture, candle=candle, active=active, state=lifecycle, direction=direction)
        else:
            actual = status_from_state(
                fixture=fixture,
                candle=candle,
                step=step,
                active=active,
                state=lifecycle,
                reason=reason,
                invalidation_reason=invalidation_reason,
            )
        comparison = compare_expected_actual(expected, actual)
        debug = build_debug_payload(
            fixture=fixture,
            active=active,
            candles=candles,
            current_index=index,
            activation_index=activation_index,
            step4_ready_index=step4_ready_index,
            state=lifecycle,
            direction=direction,
            tick_size=tick_size,
        )
        frames.append(
            {
                "index": index,
                "candle": candle,
                "expected": expected,
                "actual": actual,
                "debug": debug,
                "pass": comparison["pass"],
                "diffs": comparison["diffs"],
            }
        )

    return frames


def evaluate_fixture_file(name: str) -> dict[str, Any]:
    fixture = load_fixture(name)
    frames = evaluate_fixture(fixture)
    return {
        "fixture": fixture,
        "stack_analysis": stack_analysis(fixture),
        "frames": frames,
        "overall_pass": all(frame["pass"] for frame in frames),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate read-only Entry Agent demo fixtures.")
    parser.add_argument("fixture", nargs="?", help="Fixture name from Data/entry_agent_demo_cases")
    parser.add_argument("--list", action="store_true", help="List available fixtures")
    args = parser.parse_args(argv)
    if args.list:
        print(json.dumps(list_fixtures(), indent=2))
        return 0
    if not args.fixture:
        parser.error("fixture is required unless --list is used")
    print(json.dumps(evaluate_fixture_file(args.fixture), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
