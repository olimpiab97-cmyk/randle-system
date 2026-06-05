import sys
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENTRY_AGENT_DIR = ROOT / "EntryAgent"
if str(ENTRY_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(ENTRY_AGENT_DIR))

from entry_agent import active_stack_from_context, selected_active_liquidity_from_context
from synthetic_scenario_runner import SyntheticScenarioRunner, load_scenario, run_file


def scenario(levels, candles):
    return {
        "symbol": "NQ",
        "daily_atr": 500,
        "tick_size": 0.25,
        "levels": levels,
        "candles": candles,
    }


class SyntheticScenarioRunnerTests(unittest.TestCase):
    def test_active_liquidity_selection_and_step2_activation(self):
        data = scenario(
            [{"name": "PMH", "price": 29200, "status": "ACTIVE", "group": "NONE"}],
            [
                {"time": "2026-05-20T13:30:00Z", "open": 29195, "high": 29203, "low": 29194, "close": 29201},
                {"time": "2026-05-20T13:31:00Z", "open": 29201, "high": 29208, "low": 29200, "close": 29206},
            ],
        )

        snapshots = SyntheticScenarioRunner(data).run()

        self.assertEqual(snapshots[0]["active_liquidity_name"], "PMH")
        self.assertEqual(snapshots[-1]["active_liquidity_name"], "PMH")
        self.assertTrue(snapshots[-1]["step2_activated"])
        self.assertEqual(snapshots[-1]["step2_side"], "upper")

    def test_wick_only_upper_does_not_activate_step2(self):
        data = scenario(
            [{"name": "PMH", "price": 29200, "status": "ACTIVE", "group": "NONE"}],
            [
                {"time": "2026-05-20T13:30:00Z", "open": 29195, "high": 29202, "low": 29194, "close": 29199},
            ],
        )

        snapshots = SyntheticScenarioRunner(data).run()

        self.assertFalse(snapshots[-1]["step2_activated"])
        self.assertFalse(snapshots[-1]["step2_confirmed"])
        self.assertEqual(snapshots[-1]["current_step"], "Step 2")
        self.assertEqual(snapshots[-1]["entry_status"], "WAIT")
        self.assertTrue(snapshots[-1]["raw_touch_probe"])
        self.assertEqual(snapshots[-1]["raw_touch_boundary"]["boundary_price"], 29202.0)
        self.assertEqual(snapshots[-1]["wait_reason"], "Wick-only interaction does not confirm close-based Step 2.")

    def test_lower_wick_reset_blocks_false_step2_activation(self):
        snapshots = run_file(ENTRY_AGENT_DIR / "scenarios" / "lower_wick_reset_blocks_false_step2_activation.json")

        self.assertFalse(snapshots[0]["step2_activated"])
        self.assertEqual(snapshots[0]["raw_touch_boundary"]["boundary_price"], 99.5)
        self.assertFalse(snapshots[-1]["step2_activated"])
        self.assertEqual(snapshots[-1]["current_step"], "Step 2")
        self.assertEqual(snapshots[-1]["entry_status"], "WAIT")
        self.assertTrue(snapshots[-1]["raw_touch_probe"])
        self.assertEqual(snapshots[-1]["raw_touch_boundary"]["boundary_price"], 99.5)
        self.assertEqual(snapshots[-1]["step2_events"], [{"event": "pre_activation_probe_detected", "level_name": "PML", "side": "lower", "boundary_price": 99.5, "timestamp": "2026-06-05T13:30:00Z"}])

    def test_lower_later_close_beyond_reset_boundary_activates_step2(self):
        snapshots = run_file(ENTRY_AGENT_DIR / "scenarios" / "lower_wick_reset_later_close_beyond_reset_boundary_activates.json")

        self.assertFalse(snapshots[1]["step2_activated"])
        self.assertEqual(snapshots[1]["raw_touch_boundary"]["boundary_price"], 99.5)
        self.assertTrue(snapshots[-1]["step2_activated"])
        self.assertEqual(snapshots[-1]["candle_a"]["timestamp"], "2026-06-05T13:32:00Z")
        self.assertEqual(snapshots[-1]["step2_events"][-2]["event"], "pre_activation_probe_consumed")
        self.assertEqual(snapshots[-1]["step2_events"][-1]["event"], "step_2_activated")
        self.assertEqual(snapshots[-1]["step2_events"][-1]["boundary_price"], 99.5)
        self.assertEqual(snapshots[-1]["step2_events"][-1]["source"], "probe")

    def test_upper_wick_reset_blocks_false_step2_activation(self):
        snapshots = run_file(ENTRY_AGENT_DIR / "scenarios" / "upper_wick_reset_blocks_false_step2_activation.json")

        self.assertFalse(snapshots[0]["step2_activated"])
        self.assertEqual(snapshots[0]["raw_touch_boundary"]["boundary_price"], 100.5)
        self.assertFalse(snapshots[-1]["step2_activated"])
        self.assertEqual(snapshots[-1]["current_step"], "Step 2")
        self.assertEqual(snapshots[-1]["entry_status"], "WAIT")
        self.assertTrue(snapshots[-1]["raw_touch_probe"])
        self.assertEqual(snapshots[-1]["raw_touch_boundary"]["boundary_price"], 100.5)
        self.assertEqual(snapshots[-1]["step2_events"], [{"event": "pre_activation_probe_detected", "level_name": "PMH", "side": "upper", "boundary_price": 100.5, "timestamp": "2026-06-05T13:30:00Z"}])

    def test_upper_later_close_beyond_reset_boundary_activates_step2(self):
        snapshots = run_file(ENTRY_AGENT_DIR / "scenarios" / "upper_wick_reset_later_close_beyond_reset_boundary_activates.json")

        self.assertFalse(snapshots[1]["step2_activated"])
        self.assertEqual(snapshots[1]["raw_touch_boundary"]["boundary_price"], 100.5)
        self.assertTrue(snapshots[-1]["step2_activated"])
        self.assertEqual(snapshots[-1]["candle_a"]["timestamp"], "2026-06-05T13:32:00Z")
        self.assertEqual(snapshots[-1]["step2_events"][-2]["event"], "pre_activation_probe_consumed")
        self.assertEqual(snapshots[-1]["step2_events"][-1]["event"], "step_2_activated")
        self.assertEqual(snapshots[-1]["step2_events"][-1]["boundary_price"], 100.5)
        self.assertEqual(snapshots[-1]["step2_events"][-1]["source"], "probe")

    def test_stack_components_display_order_preserves_close_boundary_owner(self):
        tv_context = {
            "levels": {
                "ONH": {"price": 101.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "ONL": {"price": 99.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "PML": {"price": 100.0, "status": "ACTIVE", "stack_group": "LOW 1"},
            }
        }

        upper = selected_active_liquidity_from_context(
            tv_context,
            101.25,
            {"open": 100.25, "high": 101.5, "low": 100.0, "close": 101.25},
            0.25,
        )
        lower = selected_active_liquidity_from_context(
            tv_context,
            98.75,
            {"open": 99.75, "high": 100.0, "low": 98.5, "close": 98.75},
            0.25,
        )

        self.assertEqual(upper["group"]["components"], ["PMH", "ONH"])
        self.assertEqual(upper["group"]["display_name"], "PMH/ONH Liquidity")
        self.assertEqual(upper["group"]["close_boundary"], 100.0)
        self.assertEqual(upper["group"]["extreme_boundary"], 101.0)
        self.assertEqual(upper["name"], "ONH")
        self.assertEqual(upper["price"], 101.0)
        self.assertEqual(lower["group"]["components"], ["PML", "ONL"])
        self.assertEqual(lower["group"]["display_name"], "PML/ONL Liquidity")
        self.assertEqual(lower["group"]["close_boundary"], 100.0)
        self.assertEqual(lower["group"]["extreme_boundary"], 99.0)
        self.assertEqual(lower["name"], "ONL")
        self.assertEqual(lower["price"], 99.0)

    def test_active_stack_context_display_order_preserves_boundary_math(self):
        tv_context = {
            "levels": {
                "ONL": {"price": 99.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "PML": {"price": 100.0, "status": "ACTIVE", "stack_group": "LOW 1"},
            }
        }

        group = active_stack_from_context(tv_context, "ONL")

        self.assertEqual(group["components"], ["PML", "ONL"])
        self.assertEqual(group["display_name"], "PML/ONL Liquidity")
        self.assertEqual(group["extreme_boundary"], 99.0)

    def test_rs_continuation_activation_assigns_pathway(self):
        snapshots = run_file(ENTRY_AGENT_DIR / "scenarios" / "rs_continuation_activation.json")

        self.assertTrue(snapshots[-1]["continuation_step2_activated"])
        self.assertEqual(snapshots[-1]["pathway"], "R/S")
        self.assertEqual(snapshots[-1]["current_step"], "Step 2.5")

    def test_sr_continuation_activation_assigns_pathway(self):
        snapshots = run_file(ENTRY_AGENT_DIR / "scenarios" / "sr_continuation_activation.json")

        self.assertTrue(snapshots[-1]["continuation_step2_activated"])
        self.assertEqual(snapshots[-1]["pathway"], "S/R")
        self.assertEqual(snapshots[-1]["current_step"], "Step 2.5")

    def test_stacked_liquidity_selects_group_active_owner(self):
        snapshots = run_file(ENTRY_AGENT_DIR / "scenarios" / "stacked_upper_liquidity.json")

        self.assertEqual(snapshots[0]["active_liquidity_name"], "PMH/ONH Liquidity")
        self.assertEqual(snapshots[0]["active_liquidity_price"], 29205.0)
        self.assertEqual(snapshots[-1]["candle_a"]["active_level"], "ONH")
        self.assertEqual(snapshots[-1]["candle_a"]["level_price"], 29205.0)

    def test_runs_are_isolated_without_persistence_leakage(self):
        data = load_scenario(ENTRY_AGENT_DIR / "scenarios" / "wick_only_upper_no_step2.json")
        first = SyntheticScenarioRunner(deepcopy(data)).run()
        second = SyntheticScenarioRunner(deepcopy(data)).run()

        self.assertEqual(first, second)
        self.assertFalse(second[-1]["step2_activated"])


if __name__ == "__main__":
    unittest.main()
