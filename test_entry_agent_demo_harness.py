import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent
ENTRY_AGENT = ROOT / "EntryAgent"
if str(ENTRY_AGENT) not in sys.path:
    sys.path.insert(0, str(ENTRY_AGENT))


class EntryAgentDemoHarnessTests(unittest.TestCase):
    def setUp(self):
        self.harness = importlib.import_module("demo_harness")

    def test_fixture_set_loads_required_rejection_and_continuation_cases(self):
        names = self.harness.list_fixtures()
        self.assertGreaterEqual(len(names), 6)
        scenarios = [self.harness.load_fixture(name) for name in names]
        self.assertGreaterEqual(sum(1 for item in scenarios if item["scenario_type"] == "rejection"), 3)
        self.assertGreaterEqual(sum(1 for item in scenarios if item["scenario_type"] == "continuation"), 3)
        self.assertTrue(any(item.get("stacks") for item in scenarios if item["scenario_type"] == "rejection"))
        self.assertTrue(any(item.get("stacks") for item in scenarios if item["scenario_type"] == "continuation"))

    def test_candle_stepping_reset_and_run_full_are_deterministic(self):
        fixture = self.harness.load_fixture("clean_rejection_long")
        runner = self.harness.ScenarioRunner.from_fixture(fixture)
        first = runner.current()
        self.assertEqual(first["index"], 0)
        second = runner.next()
        self.assertEqual(second["index"], 1)
        self.assertEqual(runner.previous()["index"], 0)
        self.assertEqual(runner.next()["index"], 1)
        self.assertEqual(runner.reset()["index"], 0)
        full = runner.run_full()
        self.assertTrue(full["overall_pass"])
        self.assertEqual(len(full["frames"]), len(fixture["candles"]))

    def test_expected_vs_actual_comparison_reports_pass_and_fail(self):
        comparison = self.harness.compare_expected_actual({"step": "Step 4"}, {"step": "Step 4"})
        self.assertTrue(comparison["pass"])
        comparison = self.harness.compare_expected_actual({"step": "Step 5"}, {"step": "Step 4"})
        self.assertFalse(comparison["pass"])
        self.assertEqual(comparison["diffs"][0]["field"], "step")

    def test_all_initial_fixtures_match_expected_outputs(self):
        for name in self.harness.list_fixtures():
            with self.subTest(name=name):
                result = self.harness.evaluate_fixture_file(name)
                self.assertTrue(result["overall_pass"], result["frames"])

    def test_no_broker_executor_imports_or_live_calls_required(self):
        forbidden = {
            "executor",
            "integration_executor",
            "rithmic_executor",
            "rithmic_live_listener",
            "rithmic_listener",
        }
        for module_name in forbidden:
            sys.modules.pop(module_name, None)

        with patch("urllib.request.urlopen", side_effect=AssertionError("live service called")):
            for name in self.harness.list_fixtures():
                self.harness.evaluate_fixture_file(name)

        self.assertTrue(forbidden.isdisjoint(sys.modules))


if __name__ == "__main__":
    unittest.main()
