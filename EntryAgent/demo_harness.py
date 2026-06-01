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
    "leg2_state",
    "leg2_candidate_candle",
    "leg2_reference_price",
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
        entries.append(
            {
                "id": fixture_id,
                "folder": folder if folder in LIBRARY_FOLDERS else "known_good",
                "case_name": fixture.get("case_name"),
                "scenario_type": fixture.get("scenario_type"),
                "continuation_type": fixture.get("continuation_type"),
                "issue": fixture.get("issue"),
                "expected_result": fixture.get("expected_result"),
            }
        )
    return entries


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


def setup_direction_for_side(side: str) -> str:
    return "SHORT" if side == "upper" else "LONG"


def active_liquidity_config(fixture: dict[str, Any]) -> dict[str, Any]:
    if isinstance(fixture.get("active_liquidity"), dict):
        active = dict(fixture["active_liquidity"])
    elif fixture.get("stacks"):
        active = dict(fixture["stacks"][0])
    else:
        name, level = next(iter(dict(fixture["levels"]).items()))
        active = {**dict(level), "name": name, "components": [name]}
    active["price"] = as_float(active.get("price"))
    active["side"] = str(active.get("side") or "").upper()
    components = active.get("components") or [str(active.get("name"))]
    active["components"] = list(components)
    display_name = str(active.get("display_name") or active.get("name") or "/".join(active["components"]))
    active["display_name"] = display_name if display_name.endswith(" Liquidity") else f"{display_name} Liquidity"
    return active


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
    actual.update(pathway)
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
