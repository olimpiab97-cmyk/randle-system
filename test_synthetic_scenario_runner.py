import sys
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENTRY_AGENT_DIR = ROOT / "EntryAgent"
if str(ENTRY_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(ENTRY_AGENT_DIR))

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
