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

    def test_investigation_fixtures_are_archived_out_of_active_demo_flow(self):
        fixture_id = "investigations/step2_multicandle_controlling_boundary_low_stack"
        self.assertNotIn(fixture_id, self.harness.list_fixtures())
        self.assertIn(fixture_id, self.harness.list_fixtures(include_archived=True))
        entries = self.harness.list_fixture_entries(include_archived=True)
        entry = next(item for item in entries if item["id"] == fixture_id)
        self.assertEqual(entry["folder"], "investigations")
        self.assertEqual(entry["case_type"], "investigation")
        result = self.harness.evaluate_fixture_file(fixture_id)
        self.assertTrue(result["overall_pass"], result["frames"])
        self.assertEqual(result["fixture"]["case_type"], "investigation")
        active_entries = self.harness.list_fixture_entries()
        self.assertFalse(any(item["id"].startswith("investigations/") for item in active_entries))

    def test_fixture_index_entries_cover_each_demo_selector_category(self):
        entries = self.harness.list_fixture_entries()
        ids = {entry["id"] for entry in entries}
        root_ids = {entry["id"] for entry in entries if "/" not in entry["id"]}
        step2_ids = {entry["id"] for entry in entries if entry["id"].startswith("known_good/step2_rejection/")}
        step2_continuation_ids = {entry["id"] for entry in entries if entry["id"].startswith("known_good/step2_continuation/")}
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
        self.assertIn("known_good/step2_continuation/regular/rs_close_below_pmh_active", step2_continuation_ids)
        self.assertIn("regressions/replay_suppression_leg1_window_candle_index", regression_ids)
        self.assertFalse(investigation_ids)
        self.assertEqual(ids, root_ids | step2_ids | step2_continuation_ids | regression_ids | (ids - root_ids - step2_ids - step2_continuation_ids - regression_ids))

    def test_retracted_stale_inactive_fixture_is_hidden_from_step2_review_selector(self):
        fixture_id = "known_good/step2_rejection/edge_cases/close_through_stale_inactive_level"
        entries = self.harness.list_fixture_entries(include_archived=True)
        entry = next(item for item in entries if item["id"] == fixture_id)
        self.assertEqual(entry["review_status"], "RETRACTED / NOT APPROVED")
        self.assertTrue(entry["review_label"].startswith("[RETRACTED]"))
        self.assertTrue(entry["deprecated"])
        self.assertTrue(entry["hidden_from_review"])

        visible_step2_ids = {
            item["id"]
            for item in self.harness.list_fixture_entries()
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
            "known_good/step2_rejection/edge_cases/equal_price_stack_components",
            "known_good/step2_rejection/edge_cases/gaps_through_level",
        ]
        for fixture_id in approved_ids:
            with self.subTest(fixture_id=fixture_id):
                entry = entries[fixture_id]
                self.assertEqual(entry["review_status"], "APPROVED")
                self.assertEqual(entry["user_review"], "APPROVED")
                self.assertTrue(entry["review_label"].startswith("[APPROVED]"))

        archived_entries = {entry["id"]: entry for entry in self.harness.list_fixture_entries(include_archived=True)}
        investigation_id = "investigations/step2_inactive_liquidity/close_through_consumed_level"
        investigation = archived_entries[investigation_id]
        self.assertEqual(investigation["review_status"], "INVESTIGATION")
        self.assertTrue(investigation["review_label"].startswith("[INVESTIGATION]"))

    def test_step2_wick_reset_review_queue_statuses(self):
        entries = self.harness.list_fixture_entries()
        wick_reset_entries = [
            entry
            for entry in entries
            if entry.get("review_group") == "Step 2 Wick Reset"
        ]
        self.assertEqual(len(wick_reset_entries), 12)
        self.assertEqual(
            sum(1 for entry in wick_reset_entries if entry.get("review_section") == "Rejection Wick Reset"),
            6,
        )
        self.assertEqual(
            sum(1 for entry in wick_reset_entries if entry.get("review_section") == "Continuation Wick Reset"),
            6,
        )
        for entry in wick_reset_entries:
            with self.subTest(fixture_id=entry["id"]):
                self.assertEqual(entry["review_status"], "APPROVED")
                self.assertEqual(entry["user_review"], "APPROVED")
                self.assertTrue(entry["review_label"].startswith("[APPROVED]"))
                self.assertFalse(entry["hidden_from_review"])
                self.assertFalse(entry["deprecated"])

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

    def test_gold_standard_2026_06_04_nq_level_lifecycle(self):
        result = self.harness.evaluate_fixture_file("regressions/gold_standard_2026_06_04_nq_level_lifecycle")
        self.assertTrue(result["overall_pass"], result["frames"])
        first_rows = {row["level_name"]: row for row in result["frames"][0]["actual"]["level_lifecycle"]}
        rows = {row["level_name"]: row for row in result["frames"][-1]["actual"]["level_lifecycle"]}

        self.assertEqual(first_rows["PMH"]["level_status"], "CONSUMED")
        self.assertEqual(first_rows["PML/LL/ONL"]["rejection_status"], "WAIT")
        self.assertEqual(first_rows["PML/LL/ONL"]["continuation_status"], "WAIT")
        self.assertEqual(first_rows["PML/LL/ONL"]["level_status"], "WAIT")

        self.assertEqual(rows["PMH"]["rejection_status"], "INVALIDATED")
        self.assertEqual(rows["PMH"]["rejection_invalidation_reason"], "STEP6_ENTRY_TRIGGERED")
        self.assertEqual(rows["PMH"]["continuation_status"], "INVALIDATED")
        self.assertEqual(rows["PMH"]["continuation_invalidation_reason"], "NEXT_LEVEL_TOUCH")
        self.assertEqual(rows["PMH"]["level_status"], "CONSUMED")

        self.assertNotIn("PML", rows)
        self.assertNotIn("LL/ONL", rows)
        self.assertEqual(rows["PML/LL/ONL"]["rejection_status"], "WAIT")
        self.assertIsNone(rows["PML/LL/ONL"]["rejection_invalidation_reason"])
        self.assertEqual(rows["PML/LL/ONL"]["continuation_status"], "WAIT")
        self.assertIsNone(rows["PML/LL/ONL"]["continuation_invalidation_reason"])
        self.assertEqual(rows["PML/LL/ONL"]["level_status"], "WAIT")

    def test_step2_continuation_suite_wait_active_only(self):
        cases = {
            "known_good/step2_continuation/regular/rs_close_below_pmh_active": ("R/S", "ACTIVE"),
            "known_good/step2_continuation/regular/rs_wick_below_pmh_wait": ("R/S", "WAIT"),
            "known_good/step2_continuation/regular/rs_close_at_pmh_wait": ("R/S", "WAIT"),
            "known_good/step2_continuation/regular/rs_close_above_pmh_wait": ("R/S", "WAIT"),
            "known_good/step2_continuation/regular/sr_close_above_pml_active": ("S/R", "ACTIVE"),
            "known_good/step2_continuation/regular/sr_wick_above_pml_wait": ("S/R", "WAIT"),
            "known_good/step2_continuation/regular/sr_close_at_pml_wait": ("S/R", "WAIT"),
            "known_good/step2_continuation/regular/sr_close_below_pml_wait": ("S/R", "WAIT"),
            "known_good/step2_continuation/stacked/rs_high_stack_close_below_boundary_active": ("R/S", "ACTIVE"),
            "known_good/step2_continuation/stacked/rs_high_stack_wick_below_boundary_wait": ("R/S", "WAIT"),
            "known_good/step2_continuation/stacked/sr_low_stack_close_above_boundary_active": ("S/R", "ACTIVE"),
            "known_good/step2_continuation/stacked/sr_low_stack_wick_above_boundary_wait": ("S/R", "WAIT"),
        }
        for fixture_id, (continuation_type, expected_state) in cases.items():
            with self.subTest(fixture_id=fixture_id):
                result = self.harness.evaluate_fixture_file(fixture_id)
                self.assertTrue(result["overall_pass"], result["frames"])
                actual = result["frames"][0]["actual"]
                self.assertEqual(actual["continuation_type"], continuation_type)
                self.assertEqual(actual["expected_step2_state"], expected_state)
                self.assertEqual(actual["actual_step2_state"], expected_state)
                self.assertIn(actual["actual_step2_state"], {"WAIT", "ACTIVE"})
                self.assertNotIn("level_lifecycle", actual)
                self.assertNotIn("level_status", actual)
                fixture = result["fixture"]
                fixture_chart_candles = fixture.get("chart_context_candles") or []
                self.assertEqual(len(fixture_chart_candles), 10)
                chart_candles = result["frames"][0]["debug"]["step2_chart_candles"]
                self.assertEqual(len(chart_candles), 10)
                labels = {candle.get("highlight_label") for candle in chart_candles}
                self.assertIn("Prior rejection Step 2 activation", labels)
                self.assertIn("Continuation validation", labels)
                boundary = actual["qualification_boundary"]
                active = fixture["active_liquidity"]
                extreme = active.get("extreme_boundary_price", active.get("price", boundary))
                activation_boundary = max(boundary, extreme) if continuation_type == "R/S" else min(boundary, extreme)
                prior_activation = next(candle for candle in chart_candles if candle.get("highlight_label") == "Prior rejection Step 2 activation")
                validation = chart_candles[-1]
                self.assertEqual(validation.get("highlight_label"), "Continuation validation")
                self.assertEqual(validation["time"], fixture["candles"][0]["time"])
                self.assertEqual(validation["close"], fixture["candles"][0]["close"])
                if continuation_type == "R/S":
                    self.assertLess(chart_candles[0]["close"], boundary)
                    self.assertGreater(prior_activation["close"], activation_boundary)
                else:
                    self.assertGreater(chart_candles[0]["close"], boundary)
                    self.assertLess(prior_activation["close"], activation_boundary)
                for forbidden in ("leg1_state", "leg2_state", "step5_confirmed", "invalidation_reason"):
                    self.assertNotIn(forbidden, result["frames"][0]["expected"])

    def test_step2_continuation_stacked_cases_use_extreme_boundary(self):
        cases = {
            "known_good/step2_continuation/stacked/rs_high_stack_close_below_boundary_active": 101.0,
            "known_good/step2_continuation/stacked/rs_high_stack_wick_below_boundary_wait": 101.0,
            "known_good/step2_continuation/stacked/sr_low_stack_close_above_boundary_active": 89.0,
            "known_good/step2_continuation/stacked/sr_low_stack_wick_above_boundary_wait": 89.0,
        }
        for fixture_id, boundary in cases.items():
            with self.subTest(fixture_id=fixture_id):
                result = self.harness.evaluate_fixture_file(fixture_id)
                self.assertTrue(result["overall_pass"], result["frames"])
                frame = result["frames"][0]
                self.assertEqual(frame["expected"]["qualification_boundary"], boundary)
                self.assertEqual(frame["actual"]["qualification_boundary"], boundary)
                self.assertEqual(frame["debug"]["step2_qualification"]["qualification_boundary_price"], boundary)

    def test_gold_standard_2026_06_04_nq_step2_zone_transition(self):
        result = self.harness.evaluate_fixture_file("regressions/gold_standard_2026_06_04_nq_step2_zone_transition")
        self.assertTrue(result["overall_pass"], result["frames"])
        self.assertEqual(result["fixture"]["case_name"], "Gold Standard STEP 2 - 2026-06-04 NQ Zone Transition")
        first = result["frames"][0]["actual"]
        second = result["frames"][1]["actual"]

        self.assertEqual(first["step2_evaluation_target"], "PMH Liquidity")
        self.assertTrue(first["rejection_mode_entered"])
        self.assertFalse(first["zone_transition"])
        self.assertEqual(first["stack_level_status"], "ACTIVE")

        self.assertEqual(second["prior_step2_focus"], "PMH Liquidity")
        self.assertEqual(second["current_step2_focus"], "PML/LL/ONL Liquidity")
        self.assertEqual(second["step2_evaluation_target"], "PML/LL/ONL Liquidity")
        self.assertEqual(second["stack_components"], ["PML", "LL", "ONL"])
        self.assertTrue(second["zone_transition"])
        self.assertFalse(second["rejection_mode_entered"])
        self.assertEqual(second["step"], "Step 1")
        self.assertEqual(second["stack_level_status"], "WAIT")
        self.assertEqual(second["rejection_opportunity_status"], "WAIT")
        self.assertEqual(second["continuation_opportunity_status"], "WAIT")
        cards = {card["level_name"]: card for card in second["level_status_cards"]}
        self.assertEqual(cards["PMH"]["level_status"], "CONSUMED")
        self.assertEqual(cards["PMH"]["rejection_status"], "INVALIDATED")
        self.assertEqual(cards["PMH"]["rejection_invalidation_reason"], "STEP6_ENTRY_TRIGGERED")
        self.assertEqual(cards["PMH"]["continuation_status"], "INVALIDATED")
        self.assertEqual(cards["PMH"]["continuation_invalidation_reason"], "NEXT_LEVEL_TOUCH")
        self.assertEqual(cards["PML/LL/ONL"]["level_status"], "WAIT")
        self.assertEqual(cards["PML/LL/ONL"]["rejection_status"], "WAIT")
        self.assertEqual(cards["PML/LL/ONL"]["continuation_status"], "WAIT")
        self.assertEqual(cards["PML/LL/ONL"]["components"], ["PML", "LL", "ONL"])
        self.assertNotIn("level_lifecycle", second)
        qualification = result["frames"][1]["debug"]["step2_qualification"]
        self.assertEqual(qualification["active_liquidity"], "PML/LL/ONL Liquidity")
        self.assertEqual(qualification["close_boundary_level"], "PML")
        self.assertEqual(qualification["close_boundary_price"], 90.0)
        self.assertEqual(qualification["extreme_boundary_level"], "LL/ONL")
        self.assertEqual(qualification["extreme_boundary_price"], 88.0)
        self.assertEqual(qualification["stack_level_status"], "WAIT")
        self.assertEqual(qualification["rejection_opportunity_status"], "WAIT")
        self.assertEqual(qualification["continuation_opportunity_status"], "WAIT")
        self.assertEqual(
            qualification["step2_scenario_text"],
            "PMH is the prior working zone. Price wicks/reaches into PML/LL/ONL. The watched zone shifts to PML/LL/ONL. PML/LL/ONL is a stack with components PML, LL, ONL. PML/LL/ONL remains WAIT until a qualifying close below the stack. It is not ACTIVE from wick-only reach.",
        )
        step_logic = qualification["step_logic_scenarios"]
        self.assertEqual(len(step_logic), 2)
        explicit_entry = step_logic[0]
        no_entry = step_logic[1]
        self.assertEqual(explicit_entry["expected_state"]["level_status"], "CONSUMED")
        self.assertEqual(explicit_entry["expected_state"]["rejection_reason"], "EXPLICIT_ENTRY_TRIGGERED / STEP6_ENTRY_TRIGGERED")
        self.assertEqual(no_entry["expected_state"]["level_status"], "ACTIVE")
        self.assertEqual(no_entry["expected_state"]["rejection_reason"], "NO_ENTRY_REACTION / STEP6_NO_ENTRY_REACTION")
        self.assertIn("PMH level is NOT consumed because no explicit trade entry occurred.", no_entry["steps"])
        self.assertIn("R/S Continuation becomes ACTIVE", " ".join(no_entry["steps"]))
        chart_lines = result["frames"][1]["debug"]["step2_chart_lines"]
        self.assertTrue({"PML", "LL", "ONL"}.issubset({line["name"] for line in chart_lines}))
        self.assertEqual(len(result["frames"][1]["debug"]["step2_chart_candles"]), 10)
        self.assertEqual(
            len([candle for candle in result["frames"][1]["debug"]["step2_chart_candles"] if candle.get("display_only_history")]),
            8,
        )

    def test_level_is_not_consumed_until_both_opportunities_are_invalidated(self):
        state = self.harness.initialize_level_lifecycle({
            "levels": {"PML": {"price": 100.0, "side": "LOW"}}
        })
        self.harness.invalidate_opportunity(state, "PML", "rejection", "EXHAUSTION_50_LEG1")
        self.assertEqual(state["PML"]["level_status"], "ACTIVE")
        self.harness.invalidate_opportunity(state, "PML", "continuation", "CONTINUATION_FAILURE")
        self.assertEqual(state["PML"]["level_status"], "CONSUMED")

    def test_wait_invalidated_level_without_active_opportunity_remains_focus(self):
        state = self.harness.initialize_level_lifecycle({
            "levels": {"PML": {"price": 100.0, "side": "LOW"}},
            "level_lifecycle_initial": {
                "PML": {"rejection_status": "WAIT", "continuation_status": "WAIT"}
            },
        })
        self.harness.invalidate_opportunity(state, "PML", "rejection", "EXHAUSTION_50_LEG1")
        self.assertEqual(state["PML"]["rejection_status"], "INVALIDATED")
        self.assertEqual(state["PML"]["continuation_status"], "WAIT")
        self.assertEqual(state["PML"]["level_status"], "WAIT")

    def test_demo_lifecycle_renderer_does_not_default_focus_rows_to_active(self):
        html = (ROOT / "entry_agent_demo.html").read_text(encoding="utf-8")
        self.assertIn('const levelStatus = row.level_status || "WAIT";', html)
        self.assertIn('const rejectionStatus = row.rejection_status || (levelStatus === "WAIT" ? "WAIT" : "ACTIVE");', html)
        self.assertIn('const continuationStatus = row.continuation_status || (levelStatus === "WAIT" ? "WAIT" : "ACTIVE");', html)
        self.assertNotIn('row.level_status || "ACTIVE"', html)

    def test_step2_zone_transition_uses_step2_ui_mode_not_lifecycle_or_monitoring(self):
        html = (ROOT / "entry_agent_demo.html").read_text(encoding="utf-8")
        self.assertIn('fixture.scope === "step2_zone_transition_only"', html)
        self.assertIn('fixture.scope === "step2_continuation_only"', html)
        self.assertIn('known_good/step2_continuation/', html)
        self.assertIn('["Actual Step 2 State", "actual_step2_state"]', html)
        self.assertIn('renderStep2Comparison(frame);', html)
        self.assertIn('renderStep2ScenarioText(qualification);', html)
        self.assertIn('renderStepLogicScenarios(qualification);', html)
        self.assertIn('stepLogicScenarios', html)
        self.assertIn('step2_chart_candles', html)
        self.assertIn('step2-chart-panel', html)
        self.assertIn('level_status_cards', html)
        self.assertIn('const MIN_CHART_CANDLES = 10;', html)
        self.assertIn('function chartDisplayCandles(candles)', html)
        self.assertIn('const showLifecycle = fixture && fixture.scope !== "step2_zone_transition_only" && rows.length > 0;', html)

    def test_step2_continuation_has_dedicated_ui_section_and_selector(self):
        html = (ROOT / "entry_agent_demo.html").read_text(encoding="utf-8")
        self.assertIn('id="step2ContinuationSelect"', html)
        self.assertIn('id="step2ContinuationLayout"', html)
        self.assertIn('<h2>STEP 2 CONTINUATION</h2>', html)
        self.assertIn('renderStep2Continuation(frame);', html)
        self.assertIn('drawStep2Chart(frame, "step2ContinuationChart");', html)
        self.assertIn('fixture.scope === "step2_continuation_only"', html)
        self.assertIn("fixture.chart_context_candles", html)
        self.assertIn("step2ChartCandleSource(frame, candle)", html)
        self.assertIn('function isStep2ContinuationFixture()', html)
        self.assertIn('function renderStep2Continuation(frame)', html)
        self.assertIn('item.highlight_label', html)
        self.assertIn('["Continuation Type", actual.continuation_type]', html)
        self.assertIn('["Expected State", actual.expected_step2_state]', html)
        self.assertIn('["Actual State", actual.actual_step2_state]', html)
        self.assertIn('["Reason", actual.reason]', html)

    def test_step2_continuation_payload_uses_fixture_chart_context_for_ui(self):
        result = self.harness.evaluate_fixture_file("known_good/step2_continuation/regular/rs_close_below_pmh_active")
        fixture_chart_candles = result["fixture"]["chart_context_candles"]
        frame_chart_candles = result["frames"][0]["debug"]["step2_chart_candles"]

        self.assertEqual(len(fixture_chart_candles), 10)
        self.assertEqual(len(frame_chart_candles), 10)
        for fixture_candle, frame_candle in zip(fixture_chart_candles, frame_chart_candles):
            for key in ("time", "open", "high", "low", "close", "highlight_label"):
                self.assertEqual(fixture_candle.get(key), frame_candle.get(key))
        self.assertEqual(fixture_chart_candles[0]["close"], 98.9)
        self.assertEqual(fixture_chart_candles[3]["close"], 100.25)
        self.assertEqual(fixture_chart_candles[3]["highlight_label"], "Prior rejection Step 2 activation")
        self.assertEqual(fixture_chart_candles[8]["close"], 100.05)
        self.assertEqual(fixture_chart_candles[9]["close"], 99.75)
        self.assertEqual(fixture_chart_candles[9]["highlight_label"], "Continuation validation")

    def test_continuation_wick_touch_next_same_side_level_invalidates_only_continuation(self):
        fixture = {
            "case_name": "Continuation next-level wick touch",
            "scenario_type": "continuation",
            "continuation_type": "R/S",
            "symbol": "NQ",
            "date": "2026-06-04",
            "levels": {
                "LH": {"price": 100.0, "side": "HIGH"},
                "PMH": {"price": 101.0, "side": "HIGH"},
                "PML": {"price": 90.0, "side": "LOW"},
            },
            "active_liquidity": {"name": "LH", "components": ["LH"], "price": 100.0, "side": "HIGH"},
            "candles": [{"time": "2026-06-04T13:30:00Z", "open": 99.5, "high": 101.0, "low": 99.0, "close": 100.5}],
            "expected": [{}],
        }
        frame = self.harness.evaluate_fixture(fixture)[0]
        rows = {row["level_name"]: row for row in frame["actual"]["level_lifecycle"]}
        self.assertEqual(rows["LH"]["continuation_status"], "INVALIDATED")
        self.assertEqual(rows["LH"]["continuation_invalidation_reason"], "NEXT_LEVEL_TOUCH")
        self.assertEqual(rows["LH"]["rejection_status"], "ACTIVE")
        self.assertEqual(rows["LH"]["level_status"], "ACTIVE")

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
