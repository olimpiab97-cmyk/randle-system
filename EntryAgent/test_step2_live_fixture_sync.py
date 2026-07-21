"""Live Step 2 sync tests for approved demo fixtures."""

from __future__ import annotations

import json
import copy
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


def fixture_finishes_active(expected_result: Any) -> bool:
    return str(expected_result or "").strip().upper() in {"VALID_STEP2", "ACTIVE", "WAIT_THEN_ACTIVE"}


def prior_context_candle(fixture: dict[str, Any], candle: dict[str, Any]) -> dict[str, Any]:
    context_candles = fixture.get("chart_context_candles") or []
    earlier = [item for item in context_candles if item.get("time") != candle.get("time")]
    return earlier[-1] if earlier else (context_candles[-1] if context_candles else candle)


def test_live_step2_rejection_matches_all_approved_fixtures() -> None:
    fixtures = [path for path in approved_fixtures(REJECTION_DIR) if len(load_json(path).get("candles") or []) == 1]
    assert len(fixtures) == 49
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
        expected_final_active = fixture_finishes_active(fixture.get("expected_result"))
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
        previous_context = prior_context_candle(fixture, candle)
        boundary = continuation_boundary(fixture)
        result = select_pathway(
            candle,
            {
                "open": previous_context["open"],
                "high": previous_context["high"],
                "low": previous_context["low"],
                "close": previous_context["close"],
            },
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
        expected_final_active = fixture_finishes_active(fixture.get("expected_result"))
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


def test_live_step2_upper_stack_extreme_stays_monotonic_and_blocks_wick_only_rs() -> None:
    fixture = {
        "symbol": "NQ",
        "tick_size": 0.25,
        "levels": {
            "LH": {"price": 30674.0},
            "PMH": {"price": 30675.75},
        },
        "stacks": [{"name": "HIGH 1", "components": ["LH", "PMH"], "extreme_boundary_price": 30675.75}],
        "active_liquidity": {
            "name": "LH",
            "components": ["LH", "PMH"],
            "price": 30674.0,
            "side": "HIGH",
        },
        "candles": [
            {"time": "2026-06-19T13:30:00Z", "open": 30672.0, "high": 30678.25, "low": 30671.0, "close": 30673.5},
            {"time": "2026-06-19T13:37:00Z", "open": 30673.5, "high": 30675.75, "low": 30670.5, "close": 30672.0},
        ],
    }
    persisted_state: dict[str, Any] = {"normalized_symbol": "NQ"}
    observed: list[dict[str, Any]] = []
    for candle in fixture["candles"]:
        result = entry_agent.evaluate_live_step_2_1a(
            live_snapshot(fixture, candle),
            {},
            {"tick_size": fixture["tick_size"]},
            persisted_state,
        )
        observed.append(copy.deepcopy(result))
        persisted_state.update(
            {
                "step_2_1a": result,
                "step_2_1a_candle_index": result.get("next_candle_index"),
                "step_2_1a_last_evaluated_bar_time": result.get("last_evaluated_bar_time"),
                "last_interacted_liquidity": result.get("last_interacted_liquidity"),
            }
        )

    first_group = observed[0]["active_liquidity_group"]
    second_group = observed[1]["active_liquidity_group"]
    assert first_group["extreme_boundary"] == 30678.25
    assert second_group["extreme_boundary"] == 30678.25
    assert second_group["close_boundary"] == 30674.0

    continuation = select_pathway(
        {
            "open": fixture["candles"][1]["open"],
            "high": fixture["candles"][1]["high"],
            "low": fixture["candles"][1]["low"],
            "close": fixture["candles"][1]["close"],
        },
        {
            "open": fixture["candles"][0]["open"],
            "high": fixture["candles"][0]["high"],
            "low": fixture["candles"][0]["low"],
            "close": fixture["candles"][0]["close"],
        },
        30674.0,
        "LH",
        stack_extreme=30678.25,
        active_liquidity_selected=True,
        rejection_step2_confirmed=True,
    )
    assert continuation["status"] == "WAIT"
    assert continuation["controlling_mode"] is None


def test_live_step2_upper_stack_owner_persists_across_non_interaction_candles_and_weaker_retests() -> None:
    fixture = {
        "symbol": "NQ",
        "tick_size": 0.25,
        "levels": {
            "LH": {"price": 30666.0},
            "PMH": {"price": 30670.0},
            "ONH": {"price": 30770.75},
            "YH": {"price": 30783.25},
        },
        "stacks": [
            {"name": "HIGH 1", "components": ["LH", "PMH"], "extreme_boundary_price": 30670.0},
            {"name": "HIGH 2", "components": ["ONH", "YH"], "extreme_boundary_price": 30783.25},
        ],
        "active_liquidity": {
            "name": "LH",
            "components": ["LH", "PMH"],
            "price": 30666.0,
            "side": "HIGH",
        },
        "candles": [
            {"time": "2026-06-19T13:30:00Z", "open": 30644.0, "high": 30678.25, "low": 30640.75, "close": 30659.75},
            {"time": "2026-06-19T13:31:00Z", "open": 30659.0, "high": 30661.25, "low": 30646.5, "close": 30660.25},
            {"time": "2026-06-19T13:36:00Z", "open": 30661.75, "high": 30670.5, "low": 30657.25, "close": 30666.5},
            {"time": "2026-06-19T13:37:00Z", "open": 30667.25, "high": 30675.75, "low": 30664.5, "close": 30664.5},
        ],
    }
    persisted_state: dict[str, Any] = {"normalized_symbol": "NQ"}
    observed: list[dict[str, Any]] = []
    for candle in fixture["candles"]:
        result = entry_agent.evaluate_live_step_2_1a(
            live_snapshot(fixture, candle),
            {},
            {"tick_size": fixture["tick_size"]},
            persisted_state,
        )
        observed.append(copy.deepcopy(result))
        persisted_state.update(
            {
                "step_2_1a": result,
                "step_2_1a_candle_index": result.get("next_candle_index"),
                "step_2_1a_last_evaluated_bar_time": result.get("last_evaluated_bar_time"),
                "last_interacted_liquidity": result.get("last_interacted_liquidity"),
            }
        )

    first = observed[0]
    second = observed[1]
    third = observed[2]
    fourth = observed[3]

    assert first["active_level"] == "PMH"
    assert first["active_liquidity_group"]["extreme_boundary"] == 30678.25

    # The same Step 2 raid owner must persist even when the next candle does not freshly interact.
    assert second["active_level"] == "PMH"
    assert second["last_interacted_liquidity"]["name"] == "PMH"
    assert second["active_liquidity_group"]["extreme_boundary"] == 30678.25

    # Weaker later wicks cannot reconstruct a lower raid boundary while the same owner is active.
    assert third["active_liquidity_group"]["extreme_boundary"] == 30678.25

    assert fourth["active_liquidity_group"]["extreme_boundary"] == 30678.25
    assert second["active_liquidity_group"]["extreme_boundary"] >= first["active_liquidity_group"]["extreme_boundary"]
    assert third["active_liquidity_group"]["extreme_boundary"] >= second["active_liquidity_group"]["extreme_boundary"]
    assert fourth["active_liquidity_group"]["extreme_boundary"] >= third["active_liquidity_group"]["extreme_boundary"]


def test_live_step2_upper_stack_wick_only_raid_does_not_confirm_on_close_back_below_stack() -> None:
    fixture = {
        "symbol": "NQ",
        "tick_size": 0.25,
        "levels": {
            "LH": {"price": 30666.0},
            "PMH": {"price": 30670.0},
        },
        "stacks": [{"name": "HIGH 1", "components": ["LH", "PMH"], "extreme_boundary_price": 30670.0}],
        "active_liquidity": {
            "name": "LH",
            "components": ["LH", "PMH"],
            "price": 30666.0,
            "side": "HIGH",
        },
        "candles": [
            {"time": "2026-06-19T13:30:00Z", "open": 30644.0, "high": 30678.25, "low": 30640.75, "close": 30659.75},
            {"time": "2026-06-19T13:31:00Z", "open": 30659.0, "high": 30661.25, "low": 30646.5, "close": 30660.25},
        ],
    }
    persisted_state: dict[str, Any] = {"normalized_symbol": "NQ"}
    observed: list[dict[str, Any]] = []
    for candle in fixture["candles"]:
        result = entry_agent.evaluate_live_step_2_1a(
            live_snapshot(fixture, candle),
            {},
            {"tick_size": fixture["tick_size"]},
            persisted_state,
        )
        observed.append(result)
        persisted_state.update(
            {
                "step_2_1a": result,
                "step_2_1a_candle_index": result.get("next_candle_index"),
                "step_2_1a_last_evaluated_bar_time": result.get("last_evaluated_bar_time"),
                "last_interacted_liquidity": result.get("last_interacted_liquidity"),
            }
        )

    first = observed[0]
    second = observed[1]
    assert first["step_2_activated"] is False
    assert first["pre_activation_probe_boundary"]["active"] is True
    assert first["pre_activation_probe_boundary"]["boundary_price"] == 30678.25
    assert first["active_liquidity_group"]["extreme_boundary"] == 30678.25

    # Close back below LH/PMH does not confirm Step 2 until a later candle closes above the raid extreme.
    assert second["step_2_activated"] is False
    assert second["pre_activation_probe_boundary"]["active"] is True
    assert second["pre_activation_probe_boundary"]["boundary_price"] == 30678.25
    assert second["active_liquidity_group"]["extreme_boundary"] == 30678.25
    assert not any(event.get("event") == "step_2_activated" for event in (second.get("events") or []))


def test_live_step2_upper_stack_pending_owner_persists_past_timeout_and_keeps_extreme_trigger() -> None:
    fixture = {
        "symbol": "NQ",
        "tick_size": 0.25,
        "levels": {
            "LH": {"price": 30666.0},
            "PMH": {"price": 30670.0},
        },
        "stacks": [{"name": "HIGH 1", "components": ["LH", "PMH"], "extreme_boundary_price": 30670.0}],
        "active_liquidity": {
            "name": "LH",
            "components": ["LH", "PMH"],
            "price": 30666.0,
            "side": "HIGH",
        },
        "candles": [
            {"time": "2026-06-19T13:30:00Z", "open": 30644.0, "high": 30678.25, "low": 30640.75, "close": 30659.75},
            {"time": "2026-06-19T13:31:00Z", "open": 30659.0, "high": 30661.25, "low": 30646.5, "close": 30660.25},
            {"time": "2026-06-19T13:32:00Z", "open": 30661.0, "high": 30661.0, "low": 30648.0, "close": 30653.0},
            {"time": "2026-06-19T13:33:00Z", "open": 30651.75, "high": 30651.75, "low": 30637.75, "close": 30642.75},
            {"time": "2026-06-19T13:34:00Z", "open": 30642.25, "high": 30646.75, "low": 30631.75, "close": 30645.75},
            {"time": "2026-06-19T13:35:00Z", "open": 30647.0, "high": 30663.5, "low": 30645.75, "close": 30660.25},
            {"time": "2026-06-19T13:36:00Z", "open": 30661.75, "high": 30670.5, "low": 30657.25, "close": 30666.5},
            {"time": "2026-06-19T13:37:00Z", "open": 30667.25, "high": 30675.75, "low": 30664.5, "close": 30664.5},
            {"time": "2026-06-19T13:38:00Z", "open": 30663.75, "high": 30675.0, "low": 30657.25, "close": 30667.75},
            {"time": "2026-06-19T13:39:00Z", "open": 30667.75, "high": 30667.75, "low": 30659.0, "close": 30663.75},
            {"time": "2026-06-19T13:40:00Z", "open": 30663.75, "high": 30673.0, "low": 30663.5, "close": 30667.0},
            {"time": "2026-06-19T13:41:00Z", "open": 30666.75, "high": 30668.5, "low": 30660.25, "close": 30662.25},
            {"time": "2026-06-19T13:42:00Z", "open": 30662.25, "high": 30667.25, "low": 30658.5, "close": 30660.75},
            {"time": "2026-06-19T13:43:00Z", "open": 30660.75, "high": 30664.0, "low": 30655.25, "close": 30658.0},
            {"time": "2026-06-19T13:44:00Z", "open": 30658.0, "high": 30669.0, "low": 30654.5, "close": 30663.5},
            {"time": "2026-06-19T13:45:00Z", "open": 30663.5, "high": 30667.0, "low": 30659.25, "close": 30661.5},
            {"time": "2026-06-19T13:46:00Z", "open": 30661.5, "high": 30670.0, "low": 30659.5, "close": 30666.75},
            {"time": "2026-06-19T13:47:00Z", "open": 30666.75, "high": 30680.0, "low": 30665.25, "close": 30677.75},
        ],
    }
    persisted_state: dict[str, Any] = {"normalized_symbol": "NQ"}
    observed: list[dict[str, Any]] = []
    for candle in fixture["candles"]:
        result = entry_agent.evaluate_live_step_2_1a(
            live_snapshot(fixture, candle),
            {},
            {"tick_size": fixture["tick_size"]},
            persisted_state,
        )
        observed.append(copy.deepcopy(result))
        persisted_state.update(
            {
                "step_2_1a": result,
                "step_2_1a_candle_index": result.get("next_candle_index"),
                "step_2_1a_last_evaluated_bar_time": result.get("last_evaluated_bar_time"),
                "last_interacted_liquidity": result.get("last_interacted_liquidity"),
            }
        )

    minute_0642 = observed[12]
    minute_0647 = observed[17]

    # The original 06:30 owner must survive well past the old timeout window.
    assert minute_0642["active_level"] == "PMH"
    assert minute_0642["step_2_activated"] is False
    assert minute_0642["pre_activation_probe_boundary"]["active"] is True
    assert minute_0642["pre_activation_probe_boundary"]["boundary_price"] == 30678.25
    assert minute_0642["active_liquidity_group"]["extreme_boundary"] == 30678.25

    # A later stronger wick can extend the same pending raid, but still cannot confirm without a close above it.
    assert minute_0647["active_level"] == "PMH"
    assert minute_0647["step_2_activated"] is False
    assert minute_0647["pre_activation_probe_boundary"]["active"] is True
    assert minute_0647["pre_activation_probe_boundary"]["boundary_price"] == 30680.0
    assert minute_0647["active_liquidity_group"]["extreme_boundary"] == 30680.0
    assert not any(event.get("event") == "step_2_activated" for event in (minute_0647.get("events") or []))


def test_live_step2_lower_stack_extreme_stays_monotonic_and_blocks_wick_only_sr() -> None:
    fixture = {
        "symbol": "NQ",
        "tick_size": 0.25,
        "levels": {
            "PML": {"price": 100.0},
            "LL": {"price": 99.0},
        },
        "stacks": [{"name": "LOW 1", "components": ["PML", "LL"], "extreme_boundary_price": 99.0}],
        "active_liquidity": {
            "name": "LL",
            "components": ["PML", "LL"],
            "price": 99.0,
            "side": "LOW",
        },
        "candles": [
            {"time": "2026-06-19T13:30:00Z", "open": 100.5, "high": 100.75, "low": 98.75, "close": 100.0},
            {"time": "2026-06-19T13:37:00Z", "open": 100.0, "high": 100.25, "low": 99.25, "close": 99.8},
        ],
    }
    persisted_state: dict[str, Any] = {"normalized_symbol": "NQ"}
    observed: list[dict[str, Any]] = []
    for candle in fixture["candles"]:
        result = entry_agent.evaluate_live_step_2_1a(
            live_snapshot(fixture, candle),
            {},
            {"tick_size": fixture["tick_size"]},
            persisted_state,
        )
        observed.append(result)
        persisted_state.update(
            {
                "step_2_1a": result,
                "step_2_1a_candle_index": result.get("next_candle_index"),
                "step_2_1a_last_evaluated_bar_time": result.get("last_evaluated_bar_time"),
                "last_interacted_liquidity": result.get("last_interacted_liquidity"),
            }
        )

    first_group = observed[0]["active_liquidity_group"]
    second_group = observed[1]["active_liquidity_group"]
    assert first_group["extreme_boundary"] == 98.75
    assert second_group["extreme_boundary"] == 98.75
    assert second_group["close_boundary"] == 100.0

    continuation = select_pathway(
        {
            "open": fixture["candles"][1]["open"],
            "high": fixture["candles"][1]["high"],
            "low": fixture["candles"][1]["low"],
            "close": fixture["candles"][1]["close"],
        },
        {
            "open": fixture["candles"][0]["open"],
            "high": fixture["candles"][0]["high"],
            "low": fixture["candles"][0]["low"],
            "close": fixture["candles"][0]["close"],
        },
        100.0,
        "LL",
        stack_extreme=98.75,
        active_liquidity_selected=True,
        rejection_step2_confirmed=True,
    )
    assert continuation["status"] == "WAIT"
    assert continuation["controlling_mode"] is None
