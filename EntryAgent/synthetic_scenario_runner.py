"""Isolated synthetic Step 2 / Step 2.5 scenario runner.

This runner never reads live feeds, writes Entry Agent state, or calls execution
services. It builds synthetic context in memory and calls production Step 2,
Step 2.5, and active-liquidity selection helpers.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from blueprint_rules import evaluate_step_2_1a_candle, step_2_1a_initial_state
from entry_agent import (
    active_stack_from_context,
    selected_active_liquidity_from_context,
    side_for_level,
)
from step25_engine import evaluate_step25


def load_scenario(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Scenario root must be a JSON object.")
    if not isinstance(data.get("levels"), list):
        raise ValueError("Scenario must include a levels list.")
    if not isinstance(data.get("candles"), list):
        raise ValueError("Scenario must include a candles list.")
    return data


def normalize_candle(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": raw.get("timestamp") or raw.get("time"),
        "open": float(raw["open"]),
        "high": float(raw["high"]),
        "low": float(raw["low"]),
        "close": float(raw["close"]),
    }


def normalize_group_name(value: Any) -> str:
    text = str(value or "NONE").strip()
    return text if text else "NONE"


def build_tv_context(scenario: dict[str, Any]) -> dict[str, Any]:
    levels: dict[str, dict[str, Any]] = {}
    for item in scenario.get("levels") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip().upper()
        if not name:
            continue
        levels[name] = {
            "price": float(item["price"]),
            "status": str(item.get("status") or "ACTIVE").upper(),
            "stack_group": normalize_group_name(item.get("stack_group") or item.get("group")),
        }
    context = {
        "normalized_symbol": str(scenario.get("symbol") or "NQ").upper(),
        "daily_atr14": scenario.get("daily_atr"),
        "session_lock_price": scenario.get("session_lock_price", scenario.get("reference_price")),
        "levels": levels,
    }
    return context


def level_price_map(tv_context: dict[str, Any]) -> dict[str, float]:
    return {
        name: float(details["price"])
        for name, details in tv_context.get("levels", {}).items()
        if isinstance(details, dict) and details.get("price") is not None
    }


def side_level_type(level_name: str | None, side: str | None = None) -> str | None:
    side = side or side_for_level(str(level_name or ""))
    if side == "upper":
        return "LH"
    if side == "lower":
        return "LL"
    return None


def rejection_payload(step2_state: dict[str, Any]) -> dict[str, Any]:
    if step2_state.get("step_2_activated") is not True:
        return {
            "rejection_mode": "OFF",
            "watch_side": None,
            "trigger_level": None,
            "trigger_price": None,
            "reason_text": step2_state.get("reason") or "Step 2 has not activated.",
        }
    side = step2_state.get("side")
    return {
        "rejection_mode": "ON",
        "watch_side": "SHORT" if side == "upper" else "LONG",
        "trigger_level": step2_state.get("active_level"),
        "trigger_price": step2_state.get("level_price"),
        "reason_text": "Step 2 activated synthetic liquidity.",
    }


def stack_actionable_liquidity(liquidity: dict[str, Any]) -> dict[str, Any]:
    group = liquidity.get("group") if isinstance(liquidity.get("group"), dict) else None
    if not group:
        return liquidity
    prices = group.get("prices") if isinstance(group.get("prices"), dict) else {}
    side = group.get("side") or liquidity.get("side")
    if not prices or side not in {"upper", "lower"}:
        return liquidity
    if side == "upper":
        name, price = max(prices.items(), key=lambda item: (float(item[1]), str(item[0])))
    else:
        name, price = min(prices.items(), key=lambda item: (float(item[1]), str(item[0])))
    actionable = dict(liquidity)
    actionable["name"] = str(name)
    actionable["price"] = float(price)
    actionable["side"] = side
    actionable["display_name"] = group.get("display_name") or liquidity.get("display_name")
    actionable["actionable_stack_reference"] = True
    actionable["actionable_stack_reference_name"] = str(name)
    actionable["actionable_stack_reference_price"] = float(price)
    return actionable


def current_step(step2_state: dict[str, Any], step25: dict[str, Any]) -> str:
    if step25.get("status") == "READY":
        return "Step 2.5"
    return "Step 2"


def decision_status(step2_state: dict[str, Any], step25: dict[str, Any]) -> str:
    if step2_state.get("blocked") is True:
        return "INVALIDATE"
    if step25.get("status") == "READY":
        return "CONFIRM"
    return "WAIT"


def build_step25_interaction(
    step2_state: dict[str, Any],
    step25_state: dict[str, Any],
    active_liquidity: dict[str, Any] | None,
    previous_candle: dict[str, Any] | None,
    current_candle: dict[str, Any],
) -> dict[str, Any] | None:
    rejection = rejection_payload(step2_state)
    if rejection.get("rejection_mode") != "ON":
        return None
    active_level = step2_state.get("active_level")
    level_price = step2_state.get("level_price")
    level_type = side_level_type(str(active_level or ""), str(step2_state.get("side") or "") or None)
    if level_price is None or level_type is None:
        return None
    prev = previous_candle or step2_state.get("candle_a") or current_candle
    return {
        "system_state": "REJECTION MODE ON",
        "trade_mode": "ON",
        "rejection_mode": "ON",
        "interaction_state": "ACTIVE",
        "initial_candle_a": step2_state.get("candle_a"),
        "candidate_modes": step25_state.get("candidate_modes"),
        "controlling_mode": step25_state.get("controlling_mode"),
        "structure_side_requirement": step25_state.get("structure_side_requirement"),
        "reclaim_candle_a": step25_state.get("reclaim_candle_a"),
        "pathway_activation_type": step25_state.get("pathway_activation_type"),
        "continuation_step2_activated": step25_state.get("continuation_step2_activated"),
        "continuation_pending_boundary": step25_state.get("continuation_pending_boundary"),
        "continuation_step2_pending": step25_state.get("continuation_step2_pending"),
        "pathway_level": step25_state.get("pathway_level") or level_price,
        "active_liquidity_selected": active_liquidity is not None or step2_state.get("step_2_activated") is True,
        "rejection_step2_confirmed": step2_state.get("step_2_activated") is True,
        "prev_candle": prev,
        "last_candle": current_candle,
        "level": level_price,
        "level_type": level_type,
        "stack_extreme": None,
        "events": list(step25_state.get("events") or []),
    }


def snapshot_state(
    candle_number: int,
    candle: dict[str, Any],
    active_liquidity: dict[str, Any] | None,
    step2_state: dict[str, Any],
    step25_result: dict[str, Any],
) -> dict[str, Any]:
    step25_state = step25_result.get("state") if isinstance(step25_result.get("state"), dict) else {}
    probe = step2_state.get("pre_activation_probe_boundary") if isinstance(step2_state.get("pre_activation_probe_boundary"), dict) else {}
    decision = decision_status(step2_state, step25_result)
    step2_confirmed = step2_state.get("step_2_activated") is True
    raw_touch_probe = probe.get("active") is True and probe.get("boundary_price") is not None
    wait_reason = (
        step25_result.get("reason")
        if step25_result.get("status") != "READY"
        else None
    )
    if raw_touch_probe and not step2_confirmed and step2_state.get("blocked") is not True:
        wait_reason = "Wick-only interaction does not confirm close-based Step 2."
    if step2_state.get("blocked") is True:
        wait_reason = None
    pathway = step25_state.get("controlling_mode")
    active_name = (active_liquidity or {}).get("display_name") or (active_liquidity or {}).get("name") or step2_state.get("active_level")
    active_price = (active_liquidity or {}).get("price") or step2_state.get("level_price")
    return {
        "candle_number": candle_number,
        "candle_time": candle.get("timestamp"),
        "current_step": current_step(step2_state, step25_result),
        "active_liquidity_name": active_name,
        "active_liquidity_price": active_price,
        "pathway": pathway,
        "entry_status": decision,
        "last_decision": f"{decision}: {step25_result.get('reason') or step2_state.get('reason') or 'Synthetic Step 2/2.5 evaluated.'}",
        "wait_reason": wait_reason,
        "invalidation_reason": "Step 2 blocked." if step2_state.get("blocked") is True else None,
        "continuation_step2_activated": step25_state.get("continuation_step2_activated") is True,
        "candle_a": step2_state.get("candle_a"),
        "candle_b": step25_state.get("reclaim_candle_a"),
        "step2_side": step2_state.get("side"),
        "step2_confirmed": step2_confirmed,
        "step2_activated": step2_confirmed,
        "step2_blocked": step2_state.get("blocked") is True,
        "raw_touch_probe": raw_touch_probe,
        "raw_touch_boundary": deepcopy(probe),
        "step2_probe": deepcopy(probe),
        "step2_events": list(step2_state.get("events") or []),
        "step25_status": step25_result.get("status"),
        "step25_reason": step25_result.get("reason"),
        "step25_state": {
            "controlling_mode": step25_state.get("controlling_mode"),
            "candidate_modes": step25_state.get("candidate_modes"),
            "pathway_activation_type": step25_state.get("pathway_activation_type"),
            "continuation_pending_boundary": step25_state.get("continuation_pending_boundary"),
            "continuation_step2_pending": step25_state.get("continuation_step2_pending"),
            "structure_side_requirement": step25_state.get("structure_side_requirement"),
        },
    }


class SyntheticScenarioRunner:
    def __init__(self, scenario: dict[str, Any]):
        self.scenario = scenario
        self.symbol = str(scenario.get("symbol") or "NQ").upper()
        self.tv_context = build_tv_context(scenario)
        self.tick_size = float(scenario.get("tick_size") or 0.25)
        self.step2_state: dict[str, Any] | None = None
        self.step25_state: dict[str, Any] = {}
        self.previous_candle: dict[str, Any] | None = None
        self.snapshots: list[dict[str, Any]] = []

    def select_active_liquidity(self, candle: dict[str, Any]) -> dict[str, Any] | None:
        selected = selected_active_liquidity_from_context(self.tv_context, candle.get("close"), candle, self.tick_size)
        if selected and not selected.get("group"):
            selected["group"] = active_stack_from_context(self.tv_context, selected.get("name"))
        return stack_actionable_liquidity(selected) if selected else None

    def ensure_step2_state(self, active_liquidity: dict[str, Any] | None) -> dict[str, Any] | None:
        if active_liquidity is None:
            return self.step2_state
        name = active_liquidity.get("name")
        price = active_liquidity.get("price")
        side = active_liquidity.get("side") or side_for_level(
            str(name or ""),
            price,
            self.tv_context.get("session_lock_price"),
        )
        if name is None or price is None or side is None:
            return self.step2_state
        if self.step2_state is None or self.step2_state.get("active_level") != name:
            self.step2_state = step_2_1a_initial_state(str(name), float(price), side, self.tick_size)
        return self.step2_state

    def process_candle(self, raw_candle: dict[str, Any], index: int) -> dict[str, Any]:
        candle = normalize_candle(raw_candle)
        active_liquidity = self.select_active_liquidity(candle)
        step2_state = self.ensure_step2_state(active_liquidity)
        if step2_state is not None and active_liquidity is not None:
            step2_candle = dict(candle)
            step2_candle["active_level"] = active_liquidity.get("name")
            step2_candle["level_price"] = active_liquidity.get("price")
            evaluate_step_2_1a_candle(step2_state, step2_candle, index)
            step2_state["active_liquidity_group"] = active_liquidity.get("group")
        elif step2_state is None:
            step2_state = {
                "step_2_activated": False,
                "blocked": False,
                "active_level": None,
                "level_price": None,
                "side": None,
                "candle_a": None,
                "events": [],
                "reason": "No active liquidity selected.",
                "pre_activation_probe_boundary": {},
            }

        interaction = build_step25_interaction(
            step2_state,
            self.step25_state,
            active_liquidity,
            self.previous_candle,
            candle,
        )
        if interaction is None:
            step25_result = {
                "step": "Step 2.5",
                "status": "WAIT",
                "state": self.step25_state,
                "next_step": "Step 2",
                "reason": "Step 2.5 requires a Step 2 liquidity-close pathway activation.",
                "events": [],
            }
        else:
            step25_result = evaluate_step25(interaction)
            self.step25_state = step25_result.get("state") if isinstance(step25_result.get("state"), dict) else {}

        snapshot = snapshot_state(index + 1, candle, active_liquidity, step2_state, step25_result)
        self.snapshots.append(snapshot)
        self.previous_candle = candle
        return snapshot

    def run(self) -> list[dict[str, Any]]:
        for index, candle in enumerate(self.scenario.get("candles") or []):
            self.process_candle(candle, index)
        return self.snapshots


def render_value(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def render_snapshot(snapshot: dict[str, Any]) -> str:
    lines = [
        "=" * 50,
        f"CANDLE {snapshot['candle_number']}",
        "=" * 8,
        f"Time: {snapshot.get('candle_time')}",
        f"Step: {snapshot.get('current_step')}",
        f"Liquidity: {render_value(snapshot.get('active_liquidity_name'))} {render_value(snapshot.get('active_liquidity_price'))}",
        f"Pathway: {render_value(snapshot.get('pathway'))}",
        f"Decision: {snapshot.get('entry_status')}",
        f"Reason: {render_value(snapshot.get('wait_reason') or snapshot.get('step25_reason') or snapshot.get('last_decision'))}",
        f"Step 2 confirmed: {snapshot.get('step2_confirmed')}",
        f"Raw touch/probe: {snapshot.get('raw_touch_probe')}",
        f"Continuation Step 2: {snapshot.get('continuation_step2_activated')}",
        f"Step 2 side: {render_value(snapshot.get('step2_side'))}",
        f"Candle A: {render_value(snapshot.get('candle_a'))}",
        f"Candle B: {render_value(snapshot.get('candle_b'))}",
        f"Invalidation: {render_value(snapshot.get('invalidation_reason'))}",
        f"Raw touch boundary: {render_value(snapshot.get('raw_touch_boundary'))}",
    ]
    return "\n".join(lines)


def run_file(path: str | Path) -> list[dict[str, Any]]:
    runner = SyntheticScenarioRunner(load_scenario(path))
    return runner.run()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python EntryAgent/synthetic_scenario_runner.py EntryAgent/scenarios/example.json")
        return 2
    snapshots = run_file(argv[1])
    for snapshot in snapshots:
        print(render_snapshot(snapshot))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
