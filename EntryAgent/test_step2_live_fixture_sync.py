"""Live Step 2 sync tests for approved demo fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import entry_agent
import demo_harness
from step25_engine import select_pathway


ROOT = Path(__file__).resolve().parent.parent
REJECTION_DIR = ROOT / "Data" / "entry_agent_demo_cases" / "known_good" / "step2_rejection"
CONTINUATION_DIR = ROOT / "Data" / "entry_agent_demo_cases" / "known_good" / "step2_continuation"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def approved_fixtures(base: Path) -> list[Path]:
    output = []
    for path in sorted(base.rglob("*.json")):
        fixture = load_json(path)
        if fixture.get("hidden_from_review") or fixture.get("deprecated"):
            continue
        if fixture.get("review_status") == "APPROVED" and fixture.get("user_review") == "APPROVED":
            output.append(path)
    return output


def fixture_tv_context(fixture: dict[str, Any]) -> dict[str, Any]:
    stack_by_component: dict[str, str] = {}
    active = fixture.get("active_liquidity") if isinstance(fixture.get("active_liquidity"), dict) else {}
    active_names = {str(component) for component in active.get("components") or [active.get("name")] if component}
    original_active_names = set(active_names)
    expected = fixture.get("expected") or []
    expected_name = expected[0].get("active_liquidity_name") if expected and isinstance(expected[0], dict) else None
    if expected_name and "/" in expected_name:
        group_name = str(expected_name).replace(" Liquidity", "")
        for component in group_name.split("/"):
            stack_by_component[component] = group_name
            active_names.add(component)
    for stack in fixture.get("stacks") or []:
        for component in stack.get("components") or []:
            stack_by_component.setdefault(str(component), str(stack.get("name")))
    analysis = demo_harness.stack_analysis(fixture)
    for stack in analysis.get("detected_stacks") or []:
        if fixture.get("level_type") == "stacked" and original_active_names and original_active_names.intersection(set(stack.get("components") or [])):
            for component in stack.get("components") or []:
                stack_by_component.setdefault(str(component), str(stack.get("name")))
                active_names.add(str(component))
        for component in stack.get("components") or []:
            stack_by_component.setdefault(str(component), str(stack.get("name")))
    return {
        "levels": {
            name: {
                "price": details["price"],
                "status": "ACTIVE" if name in active_names else "INACTIVE",
                "stack_group": stack_by_component.get(name, "NONE"),
            }
            for name, details in (fixture.get("levels") or {}).items()
        }
    }


def live_snapshot(fixture: dict[str, Any], candle: dict[str, Any] | None = None) -> dict[str, Any]:
    candle = candle or fixture["candles"][0]
    return {
        "normalized_symbol": fixture.get("symbol") or "NQ",
        "symbol": fixture.get("symbol") or "NQ",
        "latest_price": candle["close"],
        "latest_bar_time": candle["time"],
        "ohlc_is_closed": True,
        "ohlc": {
            "open": candle["open"],
            "high": candle["high"],
            "low": candle["low"],
            "close": candle["close"],
        },
        "tv_context": fixture_tv_context(fixture),
        "liquidity": {"tick_size": fixture.get("tick_size", 0.25)},
    }


def expected_rejection_owner(fixture: dict[str, Any]) -> tuple[str | None, float | None]:
    active = fixture.get("active_liquidity") if isinstance(fixture.get("active_liquidity"), dict) else {}
    components = active.get("components") or [active.get("name")]
    levels = fixture.get("levels") or {}
    side = str(active.get("side") or "").upper()
    if len([component for component in components if component]) > 1:
        prices = {
            component: float(levels[component]["price"])
            for component in components
            if component in levels
        }
        if side == "LOW":
            name = min(prices, key=prices.get)
        else:
            name = max(prices, key=prices.get)
        return name, prices[name]
    name = active.get("name")
    price = active.get("price")
    return str(name) if name else None, float(price) if price is not None else None


def expected_rejection_display_name(fixture: dict[str, Any]) -> str | None:
    expected = fixture.get("expected") or []
    if expected and isinstance(expected[0], dict):
        return expected[0].get("active_liquidity_name")
    return None


def continuation_boundary(fixture: dict[str, Any]) -> float:
    active = fixture["active_liquidity"]
    if len(active.get("components") or []) > 1:
        if active.get("extreme_boundary_price") is not None:
            return float(active["extreme_boundary_price"])
        for stack in fixture.get("stacks") or []:
            if stack.get("name") == active.get("name") or set(stack.get("components") or []) == set(active.get("components") or []):
                return float(stack["extreme_boundary_price"])
        return float(active["extreme_boundary_price"])
    return float(active.get("close_boundary_price") or active["price"])


def continuation_live_type(fixture: dict[str, Any]) -> str:
    return "LH" if fixture["continuation_type"] == "R/S" else "LL"


def test_live_step2_rejection_matches_all_approved_fixtures() -> None:
    fixtures = [path for path in approved_fixtures(REJECTION_DIR) if len(load_json(path).get("candles") or []) == 1]
    assert len(fixtures) == 51
    for path in fixtures:
        fixture = load_json(path)
        result = entry_agent.evaluate_live_step_2_1a(
            live_snapshot(fixture),
            {},
            {"tick_size": fixture.get("tick_size", 0.25)},
            {},
        )
        expected_active = fixture.get("expected_result") == "valid_step2"
        assert bool(result.get("step_2_activated")) is expected_active, path
        if expected_active:
            expected_name, expected_price = expected_rejection_owner(fixture)
            expected_display_name = expected_rejection_display_name(fixture)
            group = result.get("active_liquidity_group") if isinstance(result.get("active_liquidity_group"), dict) else None
            if expected_display_name and "/" in expected_display_name:
                assert (group or {}).get("display_name") == expected_display_name, path
            else:
                assert result["active_level"] == expected_name, path
                assert result["level_price"] == expected_price, path


def test_live_step2_rejection_wick_reset_sequences_match_approved_fixtures() -> None:
    fixtures = [
        path
        for path in approved_fixtures(REJECTION_DIR)
        if path.parent.name == "wick_reset"
    ]
    assert len(fixtures) == 6
    for path in fixtures:
        fixture = load_json(path)
        persisted_state: dict[str, Any] = {"normalized_symbol": fixture.get("symbol") or "NQ"}
        result: dict[str, Any] = {}
        for index, candle in enumerate(fixture["candles"]):
            result = entry_agent.evaluate_live_step_2_1a(
                live_snapshot(fixture, candle),
                {},
                {"tick_size": fixture.get("tick_size", 0.25)},
                persisted_state,
            )
            expected = fixture["expected"][index]
            expected_active = expected.get("step") == "Step 2"
            assert bool(result.get("step_2_activated")) is expected_active, (path, index)
            persisted_state.update(
                {
                    "step_2_1a": result,
                    "step_2_1a_candle_index": result.get("next_candle_index"),
                    "step_2_1a_last_evaluated_bar_time": result.get("last_evaluated_bar_time"),
                    "last_interacted_liquidity": result.get("last_interacted_liquidity"),
                }
            )
        expected_final_active = fixture.get("expected_result") == "valid_step2"
        assert bool(result.get("step_2_activated")) is expected_final_active, path
        if expected_final_active:
            expected_name, expected_price = expected_rejection_owner(fixture)
            assert result["active_level"] == expected_name, path
            assert result["level_price"] == expected_price, path
            events = result.get("events") or []
            assert any(event.get("event") == "pre_activation_probe_consumed" for event in events), path
            assert any(event.get("event") == "step_2_activated" and event.get("source") == "probe" for event in events), path
        else:
            probe = result.get("pre_activation_probe_boundary") or {}
            assert probe.get("active") is True, path
            assert probe.get("boundary_price") == fixture["wick_reset"]["reset_boundary"], path


def test_live_step2_continuation_matches_all_approved_fixtures() -> None:
    fixtures = [
        path
        for path in approved_fixtures(CONTINUATION_DIR)
        if path.parent.name != "wick_reset"
    ]
    assert len(fixtures) == 12
    for path in fixtures:
        fixture = load_json(path)
        candle = fixture["candles"][0]
        boundary = continuation_boundary(fixture)
        result = select_pathway(
            candle,
            candle,
            boundary,
            continuation_live_type(fixture),
            stack_extreme=boundary if len(fixture["active_liquidity"].get("components") or []) > 1 else None,
            active_liquidity_selected=True,
            rejection_step2_confirmed=True,
        )
        actual_state = "ACTIVE" if result["continuation_step2_activated"] else "WAIT"
        expected_state = fixture["expected"][0]["expected_step2_state"]
        assert actual_state == expected_state, path


def test_live_step2_continuation_wick_reset_sequences_match_approved_fixtures() -> None:
    fixtures = [
        path
        for path in approved_fixtures(CONTINUATION_DIR)
        if path.parent.name == "wick_reset"
    ]
    assert len(fixtures) == 6
    for path in fixtures:
        fixture = load_json(path)
        persisted_state: dict[str, Any] = {"normalized_symbol": fixture.get("symbol") or "NQ"}
        result: dict[str, Any] = {}
        for index, candle in enumerate(fixture["candles"]):
            result = entry_agent.evaluate_live_step_2_1a(
                live_snapshot(fixture, candle),
                {},
                {"tick_size": fixture.get("tick_size", 0.25)},
                persisted_state,
            )
            expected_state = fixture["expected"][index]["expected_step2_state"]
            assert bool(result.get("step_2_activated")) is (expected_state == "ACTIVE"), (path, index)
            persisted_state.update(
                {
                    "step_2_1a": result,
                    "step_2_1a_candle_index": result.get("next_candle_index"),
                    "step_2_1a_last_evaluated_bar_time": result.get("last_evaluated_bar_time"),
                    "last_interacted_liquidity": result.get("last_interacted_liquidity"),
                }
            )
        expected_final_active = fixture.get("expected_result") == "ACTIVE"
        assert bool(result.get("step_2_activated")) is expected_final_active, path
        if expected_final_active:
            expected_name, expected_price = expected_rejection_owner(fixture)
            assert result["active_level"] == expected_name, path
            assert result["level_price"] == expected_price, path
            events = result.get("events") or []
            assert any(event.get("event") == "pre_activation_probe_consumed" for event in events), path
            assert any(event.get("event") == "step_2_activated" and event.get("source") == "probe" for event in events), path
        else:
            probe = result.get("pre_activation_probe_boundary") or {}
            assert probe.get("active") is True, path
            assert probe.get("boundary_price") == fixture["wick_reset"]["reset_boundary"], path
