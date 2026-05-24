import contextlib
import io
import unittest
from pathlib import Path
from unittest.mock import patch

from EntryAgent import dry_run_injector


ROOT = Path(__file__).resolve().parent
LIVE_STATE_PATH = ROOT / "EntryAgent" / "entry_agent_state.json"


class EntryAgentDryRunInjectorTests(unittest.TestCase):
    def _run_scenario(self, scenario: str):
        tv_context = dry_run_injector.entry_agent.load_tv_context("NQ")
        self.assertIsInstance(tv_context, dict)
        candles = dry_run_injector.build_scenario("NQ", scenario, tv_context)
        with dry_run_injector.isolated_entry_agent_state("NQ"):
            with contextlib.redirect_stdout(io.StringIO()):
                return dry_run_injector.run_dry_run("NQ", candles, scenario=scenario)

    def test_dry_run_never_calls_executor_routes(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("executor route called")):
            statuses = self._run_scenario("pmh_rejection_to_entry")
        self.assertEqual(statuses[-1]["entry_status"], "CONFIRM")

    def test_dry_run_restores_original_state_after_exit(self):
        before = LIVE_STATE_PATH.read_bytes() if LIVE_STATE_PATH.exists() else None
        self._run_scenario("pmh_rejection_to_entry")
        after = LIVE_STATE_PATH.read_bytes() if LIVE_STATE_PATH.exists() else None
        self.assertEqual(before, after)

    def test_pmh_rejection_to_entry_reaches_entry_confirmed(self):
        statuses = self._run_scenario("pmh_rejection_to_entry")
        self.assertEqual(statuses[-1]["entry_status"], "CONFIRM")
        self.assertEqual(statuses[-1]["current_step"], "Step 6")
        self.assertNotEqual(statuses[-1]["leg2_state"], "WAIT")

    def test_rs_continuation_to_entry_reaches_entry_confirmed(self):
        statuses = self._run_scenario("rs_continuation_to_entry")
        self.assertEqual(statuses[-1]["entry_status"], "CONFIRM")
        self.assertEqual(statuses[-1]["sr_rs_context"], "R/S")
        self.assertNotEqual(statuses[-1]["leg2_state"], "WAIT")

    def test_live_state_file_unchanged_after_dry_run(self):
        before = LIVE_STATE_PATH.read_bytes() if LIVE_STATE_PATH.exists() else None
        dry_run_injector.main(["--symbol", "NQ", "--scenario", "pmh_rejection_to_entry"])
        after = LIVE_STATE_PATH.read_bytes() if LIVE_STATE_PATH.exists() else None
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
