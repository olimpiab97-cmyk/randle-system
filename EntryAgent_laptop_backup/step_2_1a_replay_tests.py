"""Targeted replay tests for Step 2.1A pre-activation probe behavior."""

from __future__ import annotations

from copy import deepcopy

from blueprint_rules import replay_step_2_1a, step_2_1a_initial_state


def candle(open_price: float, high: float, low: float, close: float, timestamp: str, **overrides: object) -> dict:
    payload = {
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "timestamp": timestamp,
    }
    payload.update(overrides)
    return payload


def final_snapshot(state: dict) -> dict:
    probe = state["pre_activation_probe_boundary"]
    return {
        "step_2_activated": state["step_2_activated"],
        "blocked": state["blocked"],
        "candle_a_timestamp": (state["candle_a"] or {}).get("timestamp"),
        "active_level": state["active_level"],
        "level_price": state["level_price"],
        "probe": {
            "active": probe["active"],
            "side": probe["side"],
            "source_level": probe["source_level"],
            "boundary_price": probe["boundary_price"],
        },
    }


def event_names(state: dict) -> list[str]:
    return [event["event"] for event in state["events"]]


def run_scenario(name: str, state: dict, candles: list[dict], expected: dict) -> dict:
    result = replay_step_2_1a(candles, deepcopy(state))
    snapshot = final_snapshot(result)
    actual = {
        "events": event_names(result),
        "final_state": snapshot,
    }
    assert actual == expected, f"{name}\nexpected={expected}\nactual={actual}"
    return {
        "scenario": name,
        "status": "PASS",
        "logged_events": result["events"],
        "final_state": snapshot,
    }


def scenario_1_wick_beyond_no_close() -> dict:
    return run_scenario(
        "1. Wick beyond level, no close: probe set, no activation",
        step_2_1a_initial_state("PMH", 100.0, "upper"),
        [candle(99.5, 100.5, 99.25, 100.0, "2026-04-28T08:31:00-07:00")],
        {
            "events": ["pre_activation_probe_detected"],
            "final_state": {
                "step_2_activated": False,
                "blocked": False,
                "candle_a_timestamp": None,
                "active_level": "PMH",
                "level_price": 100.0,
                "probe": {"active": True, "side": "upper", "source_level": "PMH", "boundary_price": 100.5},
            },
        },
    )


def scenario_2_later_close_beyond_wick() -> dict:
    return run_scenario(
        "2. Wick beyond level, then later close beyond wick: activation occurs correctly",
        step_2_1a_initial_state("PMH", 100.0, "upper"),
        [
            candle(99.5, 100.5, 99.25, 100.0, "2026-04-28T08:31:00-07:00"),
            candle(100.25, 100.75, 100.0, 100.75, "2026-04-28T08:32:00-07:00"),
        ],
        {
            "events": ["pre_activation_probe_detected", "pre_activation_probe_consumed", "step_2_activated"],
            "final_state": {
                "step_2_activated": True,
                "blocked": False,
                "candle_a_timestamp": "2026-04-28T08:32:00-07:00",
                "active_level": "PMH",
                "level_price": 100.0,
                "probe": {"active": False, "side": "upper", "source_level": "PMH", "boundary_price": 100.5},
            },
        },
    )


def scenario_3_same_candle_wick_and_close() -> dict:
    return run_scenario(
        "3. Same candle wick + close: activation only, no probe",
        step_2_1a_initial_state("PMH", 100.0, "upper"),
        [candle(99.75, 100.5, 99.5, 100.25, "2026-04-28T08:31:00-07:00")],
        {
            "events": ["step_2_activated"],
            "final_state": {
                "step_2_activated": True,
                "blocked": False,
                "candle_a_timestamp": "2026-04-28T08:31:00-07:00",
                "active_level": "PMH",
                "level_price": 100.0,
                "probe": {"active": False, "side": "upper", "source_level": "PMH", "boundary_price": None},
            },
        },
    )


def scenario_4_multiple_probes_extremes_retained() -> dict:
    upper = run_scenario(
        "4a. Multiple upper probes: highest retained correctly",
        step_2_1a_initial_state("PMH", 100.0, "upper"),
        [
            candle(99.75, 100.25, 99.5, 100.0, "2026-04-28T08:31:00-07:00"),
            candle(100.0, 100.75, 99.75, 100.0, "2026-04-28T08:32:00-07:00"),
        ],
        {
            "events": ["pre_activation_probe_detected", "pre_activation_probe_updated"],
            "final_state": {
                "step_2_activated": False,
                "blocked": False,
                "candle_a_timestamp": None,
                "active_level": "PMH",
                "level_price": 100.0,
                "probe": {"active": True, "side": "upper", "source_level": "PMH", "boundary_price": 100.75},
            },
        },
    )
    lower = run_scenario(
        "4b. Multiple lower probes: lowest retained correctly",
        step_2_1a_initial_state("PML", 100.0, "lower"),
        [
            candle(100.25, 100.5, 99.75, 100.0, "2026-04-28T08:31:00-07:00"),
            candle(100.0, 100.25, 99.25, 100.0, "2026-04-28T08:32:00-07:00"),
        ],
        {
            "events": ["pre_activation_probe_detected", "pre_activation_probe_updated"],
            "final_state": {
                "step_2_activated": False,
                "blocked": False,
                "candle_a_timestamp": None,
                "active_level": "PML",
                "level_price": 100.0,
                "probe": {"active": True, "side": "lower", "source_level": "PML", "boundary_price": 99.25},
            },
        },
    )
    return {
        "scenario": "4. Multiple probes: highest/lowest retained correctly",
        "status": "PASS",
        "logged_events": {"upper": upper["logged_events"], "lower": lower["logged_events"]},
        "final_state": {"upper": upper["final_state"], "lower": lower["final_state"]},
    }


def scenario_5_probe_expires_activation_reverts_to_level() -> dict:
    return run_scenario(
        "5. Probe expires after N candles: activation reverts to level",
        step_2_1a_initial_state("PMH", 100.0, "upper", expiration_candles=2),
        [
            candle(99.75, 100.5, 99.5, 100.0, "2026-04-28T08:31:00-07:00"),
            candle(100.0, 100.0, 99.75, 100.0, "2026-04-28T08:32:00-07:00"),
            candle(100.0, 100.0, 99.75, 100.0, "2026-04-28T08:33:00-07:00"),
            candle(100.0, 100.25, 99.75, 100.25, "2026-04-28T08:34:00-07:00"),
        ],
        {
            "events": ["pre_activation_probe_detected", "probe_expired_timeout", "step_2_activated"],
            "final_state": {
                "step_2_activated": True,
                "blocked": False,
                "candle_a_timestamp": "2026-04-28T08:34:00-07:00",
                "active_level": "PMH",
                "level_price": 100.0,
                "probe": {"active": False, "side": "upper", "source_level": "PMH", "boundary_price": None},
            },
        },
    )


def scenario_6_gap_beyond_level_activation_without_probe() -> dict:
    return run_scenario(
        "6. Gap beyond level: activation handled without probe",
        step_2_1a_initial_state("PMH", 100.0, "upper"),
        [candle(100.5, 100.75, 100.25, 100.5, "2026-04-28T08:31:00-07:00")],
        {
            "events": ["step_2_activated"],
            "final_state": {
                "step_2_activated": True,
                "blocked": False,
                "candle_a_timestamp": "2026-04-28T08:31:00-07:00",
                "active_level": "PMH",
                "level_price": 100.0,
                "probe": {"active": False, "side": "upper", "source_level": "PMH", "boundary_price": None},
            },
        },
    )


def scenario_7_new_liquidity_clears_probe() -> dict:
    return run_scenario(
        "7. Probe formed, then new liquidity becomes nearest: probe cleared",
        step_2_1a_initial_state("PMH", 100.0, "upper"),
        [
            candle(99.75, 100.5, 99.5, 100.0, "2026-04-28T08:31:00-07:00"),
            candle(
                100.0,
                101.5,
                99.75,
                101.0,
                "2026-04-28T08:32:00-07:00",
                active_level="ONH",
                level_price=102.0,
            ),
        ],
        {
            "events": ["pre_activation_probe_detected", "probe_cleared_level_transition"],
            "final_state": {
                "step_2_activated": False,
                "blocked": False,
                "candle_a_timestamp": None,
                "active_level": "ONH",
                "level_price": 102.0,
                "probe": {"active": False, "side": "upper", "source_level": "ONH", "boundary_price": None},
            },
        },
    )


def scenario_8_original_level_activation_blocked() -> dict:
    return run_scenario(
        "8. Probe active but activation tries original level: blocked",
        step_2_1a_initial_state("PMH", 100.0, "upper"),
        [
            candle(99.75, 100.75, 99.5, 100.0, "2026-04-28T08:31:00-07:00"),
            candle(
                100.0,
                100.5,
                99.75,
                100.25,
                "2026-04-28T08:32:00-07:00",
                force_original_level_activation=True,
            ),
        ],
        {
            "events": ["pre_activation_probe_detected", "probe_override_violation"],
            "final_state": {
                "step_2_activated": False,
                "blocked": True,
                "candle_a_timestamp": None,
                "active_level": "PMH",
                "level_price": 100.0,
                "probe": {"active": True, "side": "upper", "source_level": "PMH", "boundary_price": 100.75},
            },
        },
    )


def run_tests() -> list[dict]:
    scenarios = [
        scenario_1_wick_beyond_no_close,
        scenario_2_later_close_beyond_wick,
        scenario_3_same_candle_wick_and_close,
        scenario_4_multiple_probes_extremes_retained,
        scenario_5_probe_expires_activation_reverts_to_level,
        scenario_6_gap_beyond_level_activation_without_probe,
        scenario_7_new_liquidity_clears_probe,
        scenario_8_original_level_activation_blocked,
    ]
    report = []
    for scenario in scenarios:
        try:
            report.append(scenario())
        except AssertionError as error:
            report.append({"scenario": scenario.__name__, "status": "FAIL", "error": str(error)})
            raise
    return report


if __name__ == "__main__":
    for item in run_tests():
        print(f"{item['status']}: {item['scenario']}")
        print(f"  logged_events: {item['logged_events']}")
        print(f"  final_state: {item['final_state']}")
