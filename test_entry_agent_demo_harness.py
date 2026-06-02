import importlib
import sys
import unittest
from copy import deepcopy
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

    def test_investigation_fixture_is_discoverable_and_loadable(self):
        fixture_id = "investigations/step2_multicandle_controlling_boundary_low_stack"
        self.assertIn(fixture_id, self.harness.list_fixtures())
        entries = self.harness.list_fixture_entries()
        entry = next(item for item in entries if item["id"] == fixture_id)
        self.assertEqual(entry["folder"], "investigations")
        self.assertEqual(entry["case_type"], "investigation")
        result = self.harness.evaluate_fixture_file(fixture_id)
        self.assertTrue(result["overall_pass"], result["frames"])
        self.assertEqual(result["fixture"]["case_type"], "investigation")

    def test_fixture_index_entries_cover_each_demo_selector_category(self):
        entries = self.harness.list_fixture_entries()
        ids = {entry["id"] for entry in entries}
        root_ids = {entry["id"] for entry in entries if "/" not in entry["id"]}
        step2_ids = {entry["id"] for entry in entries if entry["id"].startswith("known_good/step2_rejection/")}
        regression_ids = {entry["id"] for entry in entries if entry["folder"] == "regressions"}
        investigation_ids = {entry["id"] for entry in entries if entry["folder"] == "investigations" or entry.get("case_type") == "investigation"}

        self.assertTrue(
            {
                "clean_rejection_long",
                "clean_rs_continuation",
                "failed_rejection_leg1",
                "failed_rs_continuation",
                "stacked_rejection_pml_onl",
                "stacked_rs_continuation",
            }.issubset(root_ids)
        )
        self.assertIn("known_good/step2_rejection/atr_stack/exact_threshold_distance_stacks", step2_ids)
        self.assertIn("regressions/replay_suppression_leg1_window_candle_index", regression_ids)
        self.assertIn("investigations/step2_multicandle_controlling_boundary_low_stack", investigation_ids)
        self.assertEqual(ids, root_ids | step2_ids | regression_ids | investigation_ids | (ids - root_ids - step2_ids - regression_ids - investigation_ids))

    def test_retracted_stale_inactive_fixture_is_hidden_from_step2_review_selector(self):
        fixture_id = "known_good/step2_rejection/edge_cases/close_through_stale_inactive_level"
        entries = self.harness.list_fixture_entries()
        entry = next(item for item in entries if item["id"] == fixture_id)
        self.assertEqual(entry["review_status"], "RETRACTED / NOT APPROVED")
        self.assertTrue(entry["review_label"].startswith("[RETRACTED]"))
        self.assertTrue(entry["deprecated"])
        self.assertTrue(entry["hidden_from_review"])

        visible_step2_ids = {
            item["id"]
            for item in entries
            if item["id"].startswith("known_good/step2_rejection/")
            and not item.get("hidden_from_review")
            and not item.get("deprecated")
        }
        self.assertNotIn(fixture_id, visible_step2_ids)

    def test_fixture_index_review_status_and_dropdown_label_prefixes(self):
        entries = {entry["id"]: entry for entry in self.harness.list_fixture_entries()}
        approved_ids = [
            "known_good/step2_rejection/atr_stack/exact_threshold_distance_stacks",
            "known_good/step2_rejection/atr_stack/high_within_10pct_atr_valid",
            "known_good/step2_rejection/atr_stack/levels_outside_10pct_atr_do_not_stack",
            "known_good/step2_rejection/atr_stack/low_within_10pct_atr_close_inside_invalid",
            "known_good/step2_rejection/atr_stack/low_within_10pct_atr_valid",
            "known_good/step2_rejection/atr_stack/triple_high_outer_distance_splits",
            "known_good/step2_rejection/atr_stack/high_three_levels_split_overlap",
            "known_good/step2_rejection/atr_stack/low_three_levels_split_overlap",
            "known_good/step2_rejection/edge_cases/active_liquidity_name_ordered_correctly",
            "known_good/step2_rejection/edge_cases/close_through_wrong_side_level",
        ]
        for fixture_id in approved_ids:
            with self.subTest(fixture_id=fixture_id):
                entry = entries[fixture_id]
                self.assertEqual(entry["review_status"], "APPROVED")
                self.assertEqual(entry["user_review"], "APPROVED")
                self.assertTrue(entry["review_label"].startswith("[APPROVED]"))

        pending_id = "known_good/step2_rejection/edge_cases/equal_price_stack_components"
        pending = entries[pending_id]
        self.assertEqual(pending["review_status"], "PENDING REVIEW")
        self.assertTrue(pending["review_label"].startswith("[PENDING]"))

        investigation_id = "investigations/step2_inactive_liquidity/close_through_consumed_level"
        investigation = entries[investigation_id]
        self.assertEqual(investigation["review_status"], "INVESTIGATION")
        self.assertTrue(investigation["review_label"].startswith("[INVESTIGATION]"))

    def test_all_initial_fixtures_match_expected_outputs(self):
        for name in self.harness.list_fixtures():
            with self.subTest(name=name):
                result = self.harness.evaluate_fixture_file(name)
                self.assertTrue(result["overall_pass"], result["frames"])

    def test_rejection_liquidity_travel_progress_fields_are_exposed(self):
        result = self.harness.evaluate_fixture_file("regressions/rejection_liquidity_travel_progress")
        self.assertTrue(result["overall_pass"], result["frames"])

        expected_fields = {
            "rejection_leg1_progress_pct",
            "rejection_leg1_50_reached",
            "rejection_leg2_progress_pct",
            "rejection_leg2_75_reached",
        }
        for frame in result["frames"]:
            with self.subTest(index=frame["index"]):
                self.assertTrue(expected_fields.issubset(frame["actual"]))

    def test_rejection_liquidity_travel_progress_milestones_use_distinct_thresholds(self):
        result = self.harness.evaluate_fixture_file("regressions/rejection_liquidity_travel_progress")
        self.assertTrue(result["overall_pass"], result["frames"])

        actual = [frame["actual"] for frame in result["frames"]]

        candle0 = result["frames"][0]["candle"]
        close_based_leg1_frame0 = self.harness.travel_progress_percent(100.0, 90.0, candle0["close"])
        self.assertEqual(actual[0]["leg1_state"], "WAIT")
        self.assertLess(close_based_leg1_frame0, 50)
        self.assertEqual(actual[0]["rejection_leg1_progress_pct"], 50)
        self.assertEqual(actual[0]["rejection_leg1_50_reached"], "YES")
        self.assertLess(actual[0]["rejection_leg1_progress_pct"], 75)

        self.assertEqual(actual[1]["rejection_leg1_progress_pct"], 80)
        self.assertEqual(actual[1]["rejection_leg1_50_reached"], "YES")

        candle1 = result["frames"][1]["candle"]
        close_based_leg2_frame1 = self.harness.travel_progress_percent(99.5, 90.0, candle1["close"])
        self.assertEqual(actual[1]["leg2_state"], "WAIT")
        self.assertLess(close_based_leg2_frame1, 75)
        self.assertEqual(actual[1]["rejection_leg2_progress_pct"], 79)
        self.assertEqual(actual[1]["rejection_leg2_75_reached"], "YES")
        self.assertEqual(actual[2]["rejection_leg2_progress_pct"], 79)
        self.assertEqual(actual[2]["rejection_leg2_75_reached"], "YES")

    def test_rejection_liquidity_travel_progress_is_display_only_for_state_transitions(self):
        fixture = self.harness.load_fixture("regressions/rejection_liquidity_travel_progress")
        without_same_side_target = deepcopy(fixture)
        without_same_side_target["levels"].pop("YL")
        for expected in without_same_side_target["expected"]:
            for field in (
                "rejection_leg1_progress_pct",
                "rejection_leg1_50_reached",
                "rejection_leg2_progress_pct",
                "rejection_leg2_75_reached",
            ):
                expected.pop(field, None)

        with_progress = self.harness.evaluate_fixture(fixture)
        without_progress_target = self.harness.evaluate_fixture(without_same_side_target)
        state_fields = (
            "step",
            "pathway_type",
            "current_pathway_control",
            "active_liquidity_name",
            "setup_direction",
            "leg1_state",
            "leg2_state",
            "step5_confirmed",
            "invalidation_reason",
        )

        self.assertEqual(len(with_progress), len(without_progress_target))
        for left, right in zip(with_progress, without_progress_target):
            with self.subTest(index=left["index"]):
                for field in state_fields:
                    self.assertEqual(left["actual"].get(field), right["actual"].get(field), field)

        actual = [frame["actual"] for frame in with_progress]
        self.assertEqual(actual[0]["leg1_state"], "WAIT")
        self.assertEqual(actual[1]["leg1_state"], "COMPLETE")
        self.assertEqual(actual[2]["leg2_state"], "CONFIRMED")
        self.assertEqual(actual[3]["leg2_state"], "COMPLETE")

    def test_continuation_outputs_do_not_include_rejection_progress_thresholds(self):
        progress_fields = {
            "rejection_leg1_progress_pct",
            "rejection_leg1_progress_percent",
            "rejection_leg1_50_reached",
            "rejection_leg2_progress_pct",
            "rejection_leg2_progress_percent",
            "rejection_leg2_75_reached",
        }
        for name in ("clean_rs_continuation", "stacked_rs_continuation"):
            with self.subTest(name=name):
                result = self.harness.evaluate_fixture_file(name)
                self.assertTrue(result["overall_pass"], result["frames"])
                for frame in result["frames"]:
                    self.assertTrue(progress_fields.isdisjoint(frame["actual"]))

    def test_step2_rejection_known_good_close_qualification_suite(self):
        names = [
            name
            for name in self.harness.list_fixtures()
            if name.startswith("known_good/step2_rejection/")
        ]
        self.assertGreaterEqual(len(names), 42)

        required_fragments = [
            "regular_long/wick_touches_liquidity_close_not_beyond",
            "regular_long/body_close_beyond_liquidity_no_stack",
            "regular_short/wick_beyond_close_back_inside",
            "regular_short/body_close_beyond_liquidity",
            "stacked_low/close_inside_stack_not_through_extreme",
            "stacked_low/close_beyond_extreme_boundary",
            "stacked_high/close_inside_stack_not_through_extreme",
            "stacked_high/close_beyond_extreme_boundary",
        ]
        for fragment in required_fragments:
            self.assertTrue(any(name.endswith(fragment) for name in names), fragment)

        for name in names:
            with self.subTest(name=name):
                result = self.harness.evaluate_fixture_file(name)
                self.assertTrue(result["overall_pass"], result["frames"])
                fixture = result["fixture"]
                actual = result["frames"][-1]["actual"]
                expected_valid = fixture["expected_result"] == "valid_step2"

                self.assertEqual(actual["rejection_mode_entered"], expected_valid)
                self.assertEqual(actual["leg1_state"], "WAIT")
                self.assertEqual(actual["leg2_state"], "WAIT")
                self.assertFalse(actual["step5_confirmed"])

                if expected_valid:
                    expected_name = result["frames"][-1]["expected"].get("active_liquidity_name")
                    self.assertEqual(actual["active_liquidity_name"], expected_name)
                    self.assertEqual(actual["setup_direction"], fixture["direction"])
                    self.assertEqual(actual["step"], "Step 2")
                else:
                    self.assertFalse(actual["rejection_mode_entered"])
                    self.assertIsNone(actual["active_liquidity_name"])
                    self.assertIsNone(actual["setup_direction"])
                    self.assertEqual(actual["step"], "Step 1")

    def test_simulated_daily_atr_stack_detection_for_step2_rejection(self):
        cases = {
            "known_good/step2_rejection/atr_stack/low_within_10pct_atr_valid": ("PML/ONL Liquidity", True, 10.0),
            "known_good/step2_rejection/atr_stack/high_within_10pct_atr_valid": ("PMH/ONH Liquidity", True, 10.0),
            "known_good/step2_rejection/atr_stack/levels_outside_10pct_atr_do_not_stack": ("PML Liquidity", False, 10.0),
            "known_good/step2_rejection/atr_stack/triple_high_outer_distance_splits": ("PMH/ONH Liquidity", True, 10.0),
            "known_good/step2_rejection/atr_stack/exact_threshold_distance_stacks": ("PML/ONL Liquidity", True, 10.0),
        }
        for name, (expected_owner, expects_stack, expected_threshold) in cases.items():
            with self.subTest(name=name):
                result = self.harness.evaluate_fixture_file(name)
                self.assertTrue(result["overall_pass"], result["frames"])
                analysis = result["stack_analysis"]
                self.assertEqual(analysis["simulated_daily_atr"], 100.0)
                self.assertEqual(analysis["stack_threshold"], expected_threshold)
                actual = result["frames"][-1]["actual"]
                self.assertEqual(actual["active_liquidity_name"], expected_owner)
                detected_names = {stack["display_name"] for stack in analysis["detected_stacks"]}
                if expects_stack:
                    self.assertIn(expected_owner, detected_names)
                else:
                    self.assertNotIn("PML/ONL Liquidity", detected_names)

        split = self.harness.evaluate_fixture_file("known_good/step2_rejection/atr_stack/triple_high_outer_distance_splits")
        detected = {stack["display_name"] for stack in split["stack_analysis"]["detected_stacks"]}
        non_stacked = {level["name"] for level in split["stack_analysis"]["non_stacked_levels"]}
        self.assertIn("PMH/ONH Liquidity", detected)
        self.assertIn("YH", non_stacked)

    def test_step2_atr_low_stack_boundary_debug_fields_are_explicit(self):
        result = self.harness.evaluate_fixture_file("known_good/step2_rejection/atr_stack/low_within_10pct_atr_valid")
        qualification = result["frames"][0]["debug"]["step2_qualification"]
        self.assertEqual(qualification["close_boundary_level"], "PML")
        self.assertEqual(qualification["close_boundary_price"], 100.0)
        self.assertEqual(qualification["extreme_boundary_level"], "ONL")
        self.assertEqual(qualification["extreme_boundary_price"], 95.0)
        self.assertEqual(qualification["qualification_boundary_price"], 95.0)

    def test_step2_manual_high_stack_boundary_debug_fields_are_inferred_from_components(self):
        result = self.harness.evaluate_fixture_file("known_good/step2_rejection/edge_cases/active_liquidity_name_ordered_correctly")
        qualification = result["frames"][0]["debug"]["step2_qualification"]
        self.assertEqual(qualification["close_boundary_level"], "PMH")
        self.assertEqual(qualification["close_boundary_price"], 100.0)
        self.assertEqual(qualification["extreme_boundary_level"], "ONH")
        self.assertEqual(qualification["extreme_boundary_price"], 101.0)
        self.assertEqual(qualification["qualification_boundary_price"], 101.0)

    def test_step2_inactive_liquidity_investigations_have_explicit_reasons(self):
        cases = {
            "close_through_consumed_level": "consumed_level",
            "close_through_session_expired_level": "session_expiration",
            "close_through_stack_owner_replaced_level": "stack_ownership_transfer",
            "close_through_opposite_side_control_inactivated_level": "opposite_side_control",
            "close_through_continuation_reset_inactivated_structure": "continuation_reset",
        }
        base = "investigations/step2_inactive_liquidity"
        for name, inactive_reason in cases.items():
            with self.subTest(name=name):
                result = self.harness.evaluate_fixture_file(f"{base}/{name}")
                self.assertTrue(result["overall_pass"], result["frames"])
                self.assertEqual(result["fixture"]["case_type"], "investigation")
                self.assertEqual(result["fixture"]["inactive_liquidity"]["inactive_reason"], inactive_reason)

                actual = result["frames"][0]["actual"]
                qualification = result["frames"][0]["debug"]["step2_qualification"]
                self.assertFalse(actual["rejection_mode_entered"])
                self.assertEqual(actual["step"], "Step 1")
                self.assertEqual(qualification["inactive_reason"], inactive_reason)
                self.assertFalse(qualification["is_active_liquidity"])
                self.assertTrue(qualification["close_through_inactive_level"])
                self.assertEqual(qualification["expected_result"], "ignored")
                self.assertEqual(qualification["actual_result"], "ignored")
                self.assertEqual(qualification["review_status"], "INVESTIGATION")

    def test_step2_chart_payload_includes_stacked_component_lines_and_styles(self):
        result = self.harness.evaluate_fixture_file("known_good/step2_rejection/atr_stack/low_within_10pct_atr_valid")
        lines = {line["name"]: line for line in result["frames"][0]["debug"]["step2_chart_lines"]}

        self.assertEqual(lines["PML"]["price"], 100.0)
        self.assertTrue(lines["PML"]["is_stack_component"])
        self.assertEqual(lines["PML"]["color"], "black")
        self.assertEqual(lines["PML"]["dash"], "dotted")

        self.assertEqual(lines["ONL"]["price"], 95.0)
        self.assertTrue(lines["ONL"]["is_stack_component"])
        self.assertEqual(lines["ONL"]["color"], "red")
        self.assertEqual(lines["ONL"]["width"], 1)
        self.assertEqual(lines["ONL"]["dash"], "solid")

        high_result = self.harness.evaluate_fixture_file("known_good/step2_rejection/atr_stack/high_within_10pct_atr_valid")
        high_lines = {line["name"]: line for line in high_result["frames"][0]["debug"]["step2_chart_lines"]}
        self.assertEqual(high_lines["PMH"]["color"], "black")
        self.assertEqual(high_lines["PMH"]["dash"], "dotted")
        self.assertEqual(high_lines["ONH"]["color"], "green")
        self.assertEqual(high_lines["ONH"]["width"], 1)

    def test_step2_atr_split_overlap_pair_stacks_without_triples(self):
        cases = {
            "known_good/step2_rejection/atr_stack/high_three_levels_split_overlap": {
                "expected_stacks": {"PMH/ONH Liquidity", "ONH/YH Liquidity"},
                "forbidden_stack": "PMH/ONH/YH Liquidity",
                "middle": "ONH",
                "outer_distance": ("PMH", "YH", 16.0),
            },
            "known_good/step2_rejection/atr_stack/low_three_levels_split_overlap": {
                "expected_stacks": {"PML/ONL Liquidity", "ONL/YL Liquidity"},
                "forbidden_stack": "PML/ONL/YL Liquidity",
                "middle": "ONL",
                "outer_distance": ("YL", "PML", 16.0),
            },
        }
        for fixture_id, spec in cases.items():
            with self.subTest(fixture_id=fixture_id):
                result = self.harness.evaluate_fixture_file(fixture_id)
                self.assertTrue(result["overall_pass"], result["frames"])
                analysis = result["stack_analysis"]
                detected_stacks = analysis["detected_stacks"]
                detected_names = {stack["display_name"] for stack in detected_stacks}

                self.assertTrue(spec["expected_stacks"].issubset(detected_names))
                self.assertNotIn(spec["forbidden_stack"], detected_names)
                self.assertGreaterEqual(len(detected_names & spec["expected_stacks"]), 2)

                middle_count = sum(1 for stack in detected_stacks if spec["middle"] in stack["components"])
                self.assertGreaterEqual(middle_count, 2)

                left, right, expected_distance = spec["outer_distance"]
                outer = next(
                    distance
                    for distance in analysis["distances"]
                    if set(distance["levels"]) == {left, right}
                )
                self.assertEqual(outer["distance"], expected_distance)
                self.assertFalse(outer["within_threshold"])

    def test_continuation_controlling_structure_investigation_suite(self):
        base = "investigations/continuation_controlling_structure"
        expected_permissions = {
            "sr_no_sweep_blocks_entry": "WAIT_BLOCKED_NO_CONTROLLING_STRUCTURE_SWEEP",
            "sr_sweep_allows_entry": "CONTINUATION_ENTRY_ALLOWED_AFTER_SWEEP",
            "rs_no_sweep_blocks_entry": "WAIT_BLOCKED_NO_CONTROLLING_STRUCTURE_SWEEP",
            "rs_sweep_allows_entry": "CONTINUATION_ENTRY_ALLOWED_AFTER_SWEEP",
            "sr_old_structure_swept_after_reset_does_not_allow_entry": "WAIT_BLOCKED_NO_CONTROLLING_STRUCTURE_SWEEP",
            "sr_new_structure_swept_after_reset_allows_entry": "CONTINUATION_ENTRY_ALLOWED_AFTER_SWEEP",
            "rs_old_structure_swept_after_reset_does_not_allow_entry": "WAIT_BLOCKED_NO_CONTROLLING_STRUCTURE_SWEEP",
            "rs_new_structure_swept_after_reset_allows_entry": "CONTINUATION_ENTRY_ALLOWED_AFTER_SWEEP",
        }
        for name, permission in expected_permissions.items():
            with self.subTest(name=name):
                result = self.harness.evaluate_fixture_file(f"{base}/{name}")
                self.assertTrue(result["overall_pass"], result["frames"])
                actual = result["frames"][-1]["actual"]
                self.assertEqual(actual["entry_permission"], permission)
                self.assertTrue(actual["shared_leg1_valid"])
                self.assertTrue(actual["shared_leg2_valid"])

        reset_cases = {
            "sr_reset_on_bull_close_above_prior_bear_close": "controlling_structure_high",
            "rs_reset_on_bear_close_below_prior_bull_close": "controlling_structure_low",
        }
        for name, inactive_field in reset_cases.items():
            result = self.harness.evaluate_fixture_file(f"{base}/{name}")
            actual = result["frames"][-1]["actual"]
            self.assertTrue(actual["controlling_structure_reset"])
            self.assertIsNone(actual[inactive_field])

        new_structure_cases = {
            "sr_new_bear_push_after_reset_becomes_controlling": ("controlling_structure_high", 100),
            "rs_new_bull_push_after_reset_becomes_controlling": ("controlling_structure_low", 100),
        }
        for name, (field, value) in new_structure_cases.items():
            result = self.harness.evaluate_fixture_file(f"{base}/{name}")
            actual = result["frames"][-1]["actual"]
            self.assertTrue(actual["controlling_structure_reset"])
            self.assertEqual(actual[field], value)

        multi_cases = {
            "sr_multi_candle_bear_push_last_uninterrupted_push_controls": ([0, 1], 98),
            "rs_multi_candle_bull_push_last_uninterrupted_push_controls": ([0, 1], 102),
        }
        for name, (candle_range, close_value) in multi_cases.items():
            result = self.harness.evaluate_fixture_file(f"{base}/{name}")
            actual = result["frames"][-1]["actual"]
            self.assertEqual(actual["controlling_structure_candle_range"], candle_range)
            self.assertEqual(actual["controlling_structure_close"], close_value)

        open_question_cases = [
            "sr_exact_touch_of_controlling_high",
            "rs_exact_touch_of_controlling_low",
            "sr_wick_sweep_before_reclaim_does_not_count",
            "rs_wick_sweep_before_reclaim_does_not_count",
            "sr_body_close_without_wick_sweep_does_not_count",
            "rs_body_close_without_wick_sweep_does_not_count",
        ]
        for name in open_question_cases:
            result = self.harness.evaluate_fixture_file(f"{base}/{name}")
            actual = result["frames"][-1]["actual"]
            self.assertEqual(result["fixture"]["case_type"], "investigation")
            self.assertEqual(actual["entry_permission"], "WAIT_BLOCKED_NO_CONTROLLING_STRUCTURE_SWEEP")

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
