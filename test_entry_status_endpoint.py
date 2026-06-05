import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENTRY_AGENT_DIR = ROOT / "EntryAgent"


class EntryStatusEndpointTests(unittest.TestCase):
    def _load_server(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            spec = importlib.util.spec_from_file_location(
                "entry_status_server_under_test",
                ENTRY_AGENT_DIR / "tv_context_server.py",
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

    def _assert_clean_locked_status(self, status, step, reason):
        self.assertEqual(status["current_step"], step)
        self.assertEqual(status["current_step_status"], "WAIT")
        self.assertEqual(status["wait_reason"], reason)
        self.assertEqual(status["last_decision"], f"WAIT: {reason}")
        for field in (
            "active_liquidity_name",
            "active_liquidity_price",
            "active_liquidity_group",
            "liquidity_price",
            "liquidity_group",
            "selected_pathway",
            "setup_direction",
            "current_pathway_control",
            "current_controlling_mode",
            "leg1_confirmed_at",
            "leg1_completed_at",
            "leg1_reference_price",
            "leg1_reference_candle_time",
            "leg2_confirmed_at",
            "leg2_candidate_candle_time",
            "leg2_reference_price",
            "entry_status_confirmed_at",
            "invalidated_at",
            "invalidated_liquidity",
            "invalidation_reason",
            "internal_invalidation_reason",
            "invalidation_source_candle_time",
            "invalidation_source",
            "invalidation_source_step",
        ):
            self.assertIsNone(status.get(field), field)
        self.assertFalse(status["rejection_mode_entered"])
        self.assertEqual(status["rejection_pathway_status"], "inactive")
        self.assertEqual(status["continuation_pathway_status"], "inactive")
        self.assertEqual(status["current_continuation_type"], "none")
        self.assertEqual(status["continuation_type"], "none")
        self.assertEqual(status["leg1_status"], "WAIT")
        self.assertEqual(status["leg1_state"], "WAIT")
        self.assertIn(status.get("leg1_locked"), (None, False))
        self.assertIn(status.get("leg1_state_locked"), (None, False))
        self.assertEqual(status["leg2_status"], "WAIT")
        self.assertEqual(status["leg2_state"], "WAIT")
        self.assertEqual(status["entry_status"], "WAIT")
        for side_name in ("rejection_side", "continuation_side"):
            side = status[side_name]
            self.assertEqual(side["pathway_status"], "inactive")
            self.assertIsNone(side["current_pathway_control"])
            self.assertIsNone(side["current_controlling_mode"])
            self.assertIsNone(side["selected_pathway"])
            self.assertIsNone(side["setup_direction"])
            self.assertEqual(side["leg1_status"], "WAIT")
            self.assertEqual(side["leg1_state"], "WAIT")
            self.assertEqual(side["leg2_status"], "WAIT")
            self.assertEqual(side["leg2_state"], "WAIT")
            self.assertEqual(side["entry_status"], "WAIT")

    def _prior_date_step5_state(self):
        return {
            "state_by_symbol": {
                "NQ": {
                    "last_interacted_liquidity": {"name": "PMH", "price": 100.0, "side": "upper"},
                    "step25": {"status": "READY", "state": {"controlling_mode": "Normal Rejection Mode"}},
                    "step4": {
                        "status": "READY",
                        "next_step": "Step 5",
                        "state": {
                            "leg1_status": "COMPLETE",
                            "leg1_state_locked": True,
                            "active_liquidity": {"name": "PMH", "price": 100.0, "side": "upper"},
                            "leg1_completed_at": "2026-05-15T13:28:00Z",
                            "leg1_reference_price": 101.0,
                            "leg1_reference_candle_time": "2026-05-15T13:27:00Z",
                            "setup_direction": "SHORT",
                            "current_pathway_control": "rejection",
                            "current_controlling_mode": "Normal Rejection Mode",
                            "candle_b": {"timestamp": "2026-05-15T13:28:00Z"},
                        },
                    },
                    "step5": {
                        "status": "WAIT",
                        "next_step": "Step 5",
                        "state": {"leg2_status": "WAIT", "leg2_candidate_candle_time": "2026-05-15T13:29:00Z"},
                    },
                    "step6": {"status": "WAIT", "state": {}},
                }
            },
            "last_interacted_liquidity_by_symbol": {
                "NQ": {"name": "PMH", "price": 100.0, "side": "upper"}
            },
        }

    def test_entry_status_is_read_only_decision_status(self):
        server = self._load_server()
        server.build_entry_status = lambda symbol: {
            "symbol": symbol,
            "timestamp": "2026-05-05T00:00:00+00:00",
            "current_step": "Step 2",
            "active_liquidity_name": "PMH",
            "active_liquidity_price": 100.0,
            "setup_direction": "SHORT",
            "leg1_status": "WAIT",
            "leg2_status": "WAIT",
            "entry_status": "WAIT",
            "wait_reason": "Step 2 milestone confirmed.",
            "invalidation_reason": None,
            "last_decision": "WAIT: Step 2 milestone confirmed.",
        }

        response = server.app.test_client().get("/entry/status?symbols=NQ,YM")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "read_only")
        self.assertEqual(payload["execution_truth"], "Trade Manager")
        self.assertEqual(payload["decision_truth"], "Entry Manager")
        self.assertEqual([item["symbol"] for item in payload["symbols"]], ["NQ", "YM"])
        self.assertEqual(payload["symbols"][0]["entry_status"], "WAIT")
        self.assertEqual(payload["symbols"][0]["wait_reason"], "Step 2 milestone confirmed.")
        self.assertEqual(payload["symbols"][0]["current_step"], "Step 2")
        self.assertEqual(payload["symbols"][0]["current_step_label"], "Step 2 (Liquidity Close / Pathway Activation)")

    def test_entry_status_step_labels_cover_public_blueprint_steps(self):
        server = self._load_server()
        expected = {
            "Step 1": "Step 1 (Session / Level Prep)",
            "Step 2": "Step 2 (Liquidity Close / Pathway Activation)",
            "Step 2.5": "Step 2.5 (S/R-R/S Continuation Logic)",
            "Step 4": "Step 4 (Leg 1 Formation)",
            "Step 5": "Step 5 (Leg 2 Confirmation)",
            "Step 6": "Step 6 (Entry Trigger)",
            "Step 7": "Step 7 (Invalidation / Reset)",
        }

        for step, label in expected.items():
            with self.subTest(step=step):
                server.build_entry_status = lambda symbol, step=step: {
                    "symbol": symbol,
                    "timestamp": "2026-05-05T00:00:00+00:00",
                    "current_step": step,
                    "entry_status": "WAIT",
                }

                response = server.app.test_client().get("/entry/status?symbols=NQ")
                status = response.get_json()["symbols"][0]

                self.assertEqual(status["current_step"], step)
                self.assertEqual(status["current_step_label"], label)

    def test_legacy_levels_are_not_reused_for_other_roots(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import levels
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_levels_path = levels.LEVELS_PATH
        original_by_symbol_path = levels.LEVELS_BY_SYMBOL_PATH
        original_context_path = levels.TV_CONTEXT_PATH
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            levels.LEVELS_PATH = temp_path / "levels.json"
            levels.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            levels.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            levels.LEVELS_PATH.write_text(json.dumps({"ONH": 27542.5}), encoding="utf-8")
            levels.TV_CONTEXT_PATH.write_text(json.dumps({"normalized_symbol": "NQ"}), encoding="utf-8")

            self.assertEqual(levels.load_levels("NQM6")["ONH"], 27542.5)
            self.assertIsNone(levels.load_levels("YMM6")["ONH"])
        levels.LEVELS_PATH = original_levels_path
        levels.LEVELS_BY_SYMBOL_PATH = original_by_symbol_path
        levels.TV_CONTEXT_PATH = original_context_path

    def test_symbol_root_normalization_supports_contract_and_tv_symbols(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import levels
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        self.assertEqual(levels.root_symbol("NQM6"), "NQ")
        self.assertEqual(levels.root_symbol("YMM6"), "YM")
        self.assertEqual(levels.root_symbol("RTYM6"), "RTY")
        self.assertEqual(levels.root_symbol("YM1!"), "YM")
        self.assertEqual(levels.root_symbol("RTY1!"), "RTY")

    def test_rithmic_atr_snapshot_is_available_by_alias(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        with tempfile.TemporaryDirectory() as temp_dir:
            atr_path = Path(temp_dir) / "rithmic_atr_snapshot.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = atr_path
            atr_path.write_text(
                json.dumps({
                    "symbols": {
                        "YM": {
                            "atr_value": 6.25,
                            "atr_bar_timestamp": "2026-05-05T18:26:00Z",
                            "atr_source": "test",
                        }
                    }
                }),
                encoding="utf-8",
            )

            atr = entry_agent.load_rithmic_atr_snapshot("YMM6")
            self.assertIsNotNone(atr)
            self.assertEqual(atr["atr_1m_14"], 6.25)
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path

    def test_step2_without_active_liquidity_has_step2_wait_reason(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        reason = entry_agent.wait_reason_for_current_step(
            "Step 2",
            None,
            {"status": "WAIT", "reason": "Step 4 waiting."},
            {"status": "WAIT", "reason": "Step 5 waiting."},
            {"status": "WAIT", "reason": "Step 6 waiting."},
        )
        self.assertEqual(reason, "No active liquidity selected.")

    def test_nq_publication_gate_blocks_step4_until_step3_passes(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        snapshot = {
            "normalized_symbol": "NQ",
            "latest_price": 29192.5,
            "ohlc_is_closed": True,
            "rejection": {"rejection_mode": "ON"},
            "step25": {"status": "READY"},
            "step3": {"status": "WAIT", "next_step": "Step 3"},
            "step4": {"status": "WAIT", "next_step": "Step 4"},
            "step5": {"status": "WAIT"},
            "step6": {"status": "WAIT"},
        }

        self.assertEqual(entry_agent.current_step_from_snapshot(snapshot), "Step 2")
        self.assertEqual(snapshot["publication_gate_debug"][0]["attempted_step"], "Step 4")
        self.assertIn("Step 3 officially passes", snapshot["publication_gate_debug"][0]["reason"])

    def test_nq_publication_gate_blocks_step5_until_leg1_locked(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        snapshot = {
            "normalized_symbol": "NQ",
            "latest_price": 29192.5,
            "ohlc_is_closed": True,
            "rejection": {"rejection_mode": "ON"},
            "step25": {"status": "READY"},
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4"},
            "step4": {
                "status": "READY",
                "next_step": "Step 5",
                "state": {"leg1_status": "WAIT", "leg1_state_locked": False},
            },
            "step5": {"status": "WAIT"},
            "step6": {"status": "WAIT"},
        }

        self.assertEqual(entry_agent.current_step_from_snapshot(snapshot), "Step 2")
        self.assertEqual(snapshot["publication_gate_debug"][0]["attempted_step"], "Step 4")
        self.assertIn("Leg 1 is close-confirmed", snapshot["publication_gate_debug"][0]["reason"])

    def test_nq_publication_gate_blocks_step6_until_leg2_locked(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        leg1_state = {
            "leg1_status": "COMPLETE",
            "leg1_state_locked": True,
            "leg1_reference_price": 29171.5,
            "leg1_reference_candle_time": "2026-05-13T13:56:00Z",
            "leg1_direction": "SHORT",
            "active_liquidity": {"name": "PML", "price": 29200.0},
            "leg1_completed_at": "2026-05-13T13:56:00Z",
            "current_active_sequence_started_at": "2026-05-13T13:55:00Z",
            "candle_a": {"timestamp": "2026-05-13T13:55:00Z"},
            "candle_b": {"timestamp": "2026-05-13T13:56:00Z"},
        }
        snapshot = {
            "normalized_symbol": "NQ",
            "latest_price": 29160.75,
            "ohlc_is_closed": True,
            "rejection": {"rejection_mode": "ON"},
            "step25": {"status": "READY"},
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4"},
            "step4": {"status": "READY", "next_step": "Step 5", "state": leg1_state},
            "step5": {"status": "READY", "next_step": "Step 6", "state": {"leg2_status": "WAIT"}},
            "step6": {"status": "ENTRY_CONFIRMED"},
        }

        self.assertEqual(entry_agent.current_step_from_snapshot(snapshot), "Step 4")
        self.assertEqual(snapshot["publication_gate_debug"][0]["attempted_step"], "Step 6")
        self.assertIn("Leg 2 are close-confirmed", snapshot["publication_gate_debug"][0]["reason"])

    def test_nq_publication_gate_allows_step6_after_leg2_validated(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        leg1_state = {
            "leg1_status": "COMPLETE",
            "leg1_state_locked": True,
            "leg1_reference_price": 29171.5,
            "leg1_reference_candle_time": "2026-05-13T13:56:00Z",
            "leg1_direction": "SHORT",
            "active_liquidity": {"name": "PML", "price": 29200.0},
            "leg1_completed_at": "2026-05-13T13:56:00Z",
            "current_active_sequence_started_at": "2026-05-13T13:55:00Z",
            "candle_a": {"timestamp": "2026-05-13T13:55:00Z"},
            "candle_b": {"timestamp": "2026-05-13T13:56:00Z"},
        }
        snapshot = {
            "normalized_symbol": "NQ",
            "latest_price": 29160.75,
            "ohlc_is_closed": True,
            "rejection": {"rejection_mode": "ON"},
            "step25": {"status": "READY"},
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4"},
            "step4": {"status": "READY", "next_step": "Step 5", "state": leg1_state},
            "step5": {"status": "READY", "next_step": "Step 6", "state": {"leg2_status": "VALIDATED"}},
            "step6": {"status": "ENTRY_CONFIRMED"},
        }

        self.assertEqual(entry_agent.current_step_from_snapshot(snapshot), "Step 6")
        self.assertNotIn("publication_gate_debug", snapshot)

    def test_continuation_step2_sr_requires_bullish_close_back_across_lower_liquidity(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step25_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        prev_candle = {"open": 29204.0, "high": 29205.0, "low": 29190.0, "close": 29192.5}
        bullish_reclaim = {"open": 29191.0, "high": 29208.0, "low": 29188.0, "close": 29206.0}
        bearish_reclaim = {"open": 29208.0, "high": 29210.0, "low": 29188.0, "close": 29206.0}

        valid = step25_engine.select_pathway(bullish_reclaim, prev_candle, 29200.0, "LL", active_liquidity_selected=True)
        invalid = step25_engine.select_pathway(bearish_reclaim, prev_candle, 29200.0, "LL", active_liquidity_selected=True)

        self.assertEqual(valid["status"], "READY")
        self.assertEqual(valid["controlling_mode"], "S/R")
        self.assertEqual(valid["activation_type"], "close")
        self.assertEqual(invalid["status"], "WAIT")

    def test_continuation_step2_rs_requires_bearish_close_back_across_upper_liquidity(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step25_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        prev_candle = {"open": 29402.0, "high": 29415.0, "low": 29401.0, "close": 29408.0}
        bearish_reclaim = {"open": 29409.0, "high": 29412.0, "low": 29390.0, "close": 29396.0}
        bullish_reclaim = {"open": 29394.0, "high": 29412.0, "low": 29390.0, "close": 29396.0}

        valid = step25_engine.select_pathway(bearish_reclaim, prev_candle, 29400.0, "LH", active_liquidity_selected=True)
        invalid = step25_engine.select_pathway(bullish_reclaim, prev_candle, 29400.0, "LH", active_liquidity_selected=True)

        self.assertEqual(valid["status"], "READY")
        self.assertEqual(valid["controlling_mode"], "R/S")
        self.assertEqual(valid["activation_type"], "close")
        self.assertEqual(invalid["status"], "WAIT")

    def test_continuation_step2_does_not_activate_on_wick_without_close_back_across(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step25_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        prev_candle = {"open": 29204.0, "high": 29206.0, "low": 29190.0, "close": 29192.5}
        wick_only = {"open": 29191.0, "high": 29205.0, "low": 29180.0, "close": 29196.0}

        result = step25_engine.select_pathway(wick_only, prev_candle, 29200.0, "LL", active_liquidity_selected=True)

        self.assertEqual(result["status"], "WAIT")
        self.assertIsNone(result["controlling_mode"])

    def test_same_candle_wick_reclaim_does_not_activate_continuation(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step25_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        candle = {"open": 29196.0, "high": 29208.0, "low": 29188.0, "close": 29198.0}
        result = step25_engine.evaluate_step25(
            {
                "rejection_mode": "ON",
                "initial_candle_a": candle,
                "controlling_mode": "S/R",
                "candidate_modes": ["S/R"],
                "provisional_candle_a": candle,
                "pathway_activation_type": "wick",
                "continuation_step2_activated": True,
                "events": [],
            }
        )

        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["state"]["controlling_mode"], "Normal Rejection Mode")
        self.assertEqual(result["state"]["pathway_activation_type"], "normal")
        self.assertIsNone(result["state"]["provisional_candle_a"])

    def test_continuation_step2_requires_active_liquidity_selected(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step25_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        prev_candle = {"open": 29204.0, "high": 29205.0, "low": 29190.0, "close": 29192.5}
        bullish_reclaim = {"open": 29191.0, "high": 29208.0, "low": 29188.0, "close": 29206.0}

        result = step25_engine.select_pathway(bullish_reclaim, prev_candle, 29200.0, "LL", active_liquidity_selected=False)

        self.assertEqual(result["status"], "WAIT")
        self.assertIsNone(result["controlling_mode"])

    def test_continuation_step2_requires_rejection_step2_confirmed(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step25_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        prev_candle = {"open": 29204.0, "high": 29205.0, "low": 29190.0, "close": 29192.5}
        bullish_reclaim = {"open": 29191.0, "high": 29208.0, "low": 29188.0, "close": 29206.0}

        result = step25_engine.select_pathway(
            bullish_reclaim,
            prev_candle,
            29200.0,
            "LL",
            active_liquidity_selected=True,
            rejection_step2_confirmed=False,
        )

        self.assertEqual(result["status"], "WAIT")
        self.assertIsNone(result["controlling_mode"])

    def test_continuation_step25_does_not_honor_requested_mode_without_step2_activation(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step25_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        candle = {"open": 29191.0, "high": 29208.0, "low": 29188.0, "close": 29206.0}
        result = step25_engine.evaluate_step25(
            {
                "rejection_mode": "ON",
                "initial_candle_a": candle,
                "controlling_mode": "S/R",
                "candidate_modes": ["S/R"],
                "reclaim_candle_a": candle,
                "continuation_step2_activated": False,
                "events": [],
            }
        )

        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["state"]["controlling_mode"], "Normal Rejection Mode")
        self.assertNotIn("S/R", result["state"]["candidate_modes"])

    def test_active_liquidity_selection_uses_active_tv_stack_zone(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        tv_context = {
            "levels": {
                "YH": {"price": 105.0, "status": "INACTIVE", "stack_group": "HIGH 1"},
                "ONH": {"price": 101.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "LH": {"price": 99.0, "status": "ACTIVE", "stack_group": "NONE"},
                "YL": {"price": 90.0, "status": "ACTIVE", "stack_group": "NONE"},
            }
        }

        selected = entry_agent.selected_active_liquidity_from_context(
            tv_context,
            100.25,
            {"open": 99.75, "high": 100.5, "low": 99.5, "close": 100.25},
        )

        self.assertEqual(selected["name"], "ONH")
        self.assertEqual(selected["price"], 101.0)
        self.assertEqual(selected["group"]["name"], "HIGH 1")
        self.assertEqual(selected["group"]["components"], ["ONH", "PMH"])
        self.assertEqual(selected["group"]["extreme_component"], "ONH")
        self.assertEqual(selected["group"]["close_component"], "PMH")
        self.assertNotIn("YH", selected["group"]["components"])

    def test_active_liquidity_upper_stack_selects_highest_actionable_component(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        selected = entry_agent.selected_active_liquidity_from_context(
            {
                "levels": {
                    "PMH": {"price": 29200.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "ONH": {"price": 29205.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                }
            },
            29209.0,
            {"open": 29206.0, "high": 29210.0, "low": 29204.0, "close": 29209.0},
        )

        self.assertEqual(selected["display_name"], "PMH/ONH Liquidity")
        self.assertEqual(selected["name"], "ONH")
        self.assertEqual(selected["price"], 29205.0)
        self.assertEqual(selected["group"]["extreme_component"], "ONH")
        self.assertEqual(selected["group"]["close_component"], "PMH")

    def test_active_liquidity_lower_stack_selects_lowest_actionable_component(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        selected = entry_agent.selected_active_liquidity_from_context(
            {
                "levels": {
                    "PML": {"price": 29000.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                    "ONL": {"price": 28995.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                }
            },
            28991.0,
            {"open": 28994.0, "high": 28996.0, "low": 28990.0, "close": 28991.0},
        )

        self.assertEqual(selected["display_name"], "PML/ONL Liquidity")
        self.assertEqual(selected["name"], "ONL")
        self.assertEqual(selected["price"], 28995.0)
        self.assertEqual(selected["group"]["extreme_component"], "ONL")
        self.assertEqual(selected["group"]["close_component"], "PML")

    def test_ym_equal_price_pml_onl_stack_displays_close_boundary_owner_first(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        selected = entry_agent.selected_active_liquidity_from_context(
            {
                "levels": {
                    "ONL": {"price": 50576.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                    "PML": {"price": 50576.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                }
            },
            50574.0,
            {"open": 50578.0, "high": 50579.0, "low": 50572.0, "close": 50574.0},
            tick_size=1.0,
        )

        self.assertEqual(selected["display_name"], "PML/ONL Liquidity")
        self.assertEqual(selected["group"]["display_name"], "PML/ONL Liquidity")
        self.assertEqual(selected["group"]["close_boundary"], 50576.0)
        self.assertEqual(selected["group"]["extreme_boundary"], 50576.0)
        self.assertEqual(selected["group"]["name"], "LOW 1")
        self.assertEqual(selected["group"]["close_component"], "PML")

    def test_lower_stack_exact_one_tick_beyond_close_boundary_activates(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        selected = entry_agent.selected_active_liquidity_from_context(
            {
                "levels": {
                    "PML": {"price": 100.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                    "ONL": {"price": 99.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                }
            },
            99.75,
            {"open": 100.25, "high": 100.5, "low": 99.5, "close": 99.75},
            tick_size=0.25,
        )

        self.assertEqual(selected["display_name"], "PML/ONL Liquidity")
        self.assertEqual(selected["name"], "ONL")
        self.assertEqual(selected["group"]["close_boundary"], 100.0)
        self.assertEqual(selected["group"]["extreme_boundary"], 99.0)
        self.assertEqual(selected["group"]["close_component"], "PML")

    def test_inactive_broken_pml_rotates_to_onl_same_stack_target(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        snapshot = {
            "normalized_symbol": "YM",
            "latest_price": 50070.0,
            "latest_bar_time": "2026-05-07T14:00:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 50100.0, "high": 50110.0, "low": 50060.0, "close": 50070.0},
            "tv_context": {
                "levels": {
                    "PML": {"price": 50082.0, "status": "INACTIVE", "stack_group": "LOW 1"},
                    "LL": {"price": 50018.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                    "ONL": {"price": 49984.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                    "YL": {"price": 49806.0, "status": "ACTIVE", "stack_group": "NONE"},
                }
            },
        }
        persisted_state = {
            "state_by_symbol": {
                "YM": {
                    "last_interacted_liquidity": {"name": "PML", "price": 50082.0, "side": "lower"},
                }
            },
            "last_interacted_liquidity_by_symbol": {
                "YM": {"name": "PML", "price": 50082.0, "side": "lower"},
            },
        }

        result = entry_agent.evaluate_live_step_2_1a(snapshot, {}, {"tick_size": 1.0}, persisted_state)

        self.assertEqual(result["active_level"], "ONL")
        self.assertEqual(result["level_price"], 49984.0)
        self.assertEqual(result["last_interacted_liquidity"]["name"], "ONL")
        self.assertEqual(result["active_liquidity_group"]["name"], "LOW 1")

    def test_nq_ll_exhaustion_rotates_to_onl_and_does_not_flip_back(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        market = {
            "latest_price": 28655.5,
            "latest_bar_time": "2026-05-07T16:15:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 28670.0, "high": 28670.25, "low": 28648.5, "close": 28655.5},
        }

        def fake_market_snapshot(_root):
            return {
                "source": "test",
                "symbol": "NQM6",
                "latest_price": market["latest_price"],
                "latest_bar_time": market["latest_bar_time"],
                "ohlc_is_closed": market["ohlc_is_closed"],
                "ohlc": dict(market["ohlc"]),
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = fake_market_snapshot
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "levels": {
                                    "LL": {"price": 28690.25, "status": "ACTIVE", "stack_group": "LOW 1"},
                                    "ONL": {"price": 28637.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "PML": {"price": 28717.0, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            ll_close = entry_agent.build_entry_status("NQM6")
            self.assertEqual(ll_close["active_liquidity_name"], "LL")
            self.assertEqual(ll_close["active_liquidity_price"], 28690.25)
            self.assertNotEqual(ll_close["leg1_status"], "COMPLETE")

            market.update(
                {
                    "latest_price": 28629.75,
                    "latest_bar_time": "2026-05-07T16:18:00Z",
                    "ohlc": {"open": 28644.75, "high": 28649.0, "low": 28625.0, "close": 28629.75},
                }
            )
            onl_reached = entry_agent.build_entry_status("NQM6")
            self.assertEqual(onl_reached["active_liquidity_name"], "ONL")
            self.assertEqual(onl_reached["active_liquidity_price"], 28637.0)

            state = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))
            consumed = ((state.get("state_by_symbol") or {}).get("NQ") or {}).get("consumed_liquidity_levels") or []
            self.assertTrue(
                any(
                    record.get("name") == "LL"
                    and record.get("price") == 28690.25
                    and record.get("exhaustion_type")
                    in {"same_side_next_liquidity_reached", "no_leg1_50_percent_exhaustion"}
                    for record in consumed
                )
            )

            market.update(
                {
                    "latest_price": 28658.5,
                    "latest_bar_time": "2026-05-07T16:22:00Z",
                    "ohlc": {"open": 28628.75, "high": 28660.0, "low": 28627.0, "close": 28658.5},
                }
            )
            after_onl_touch = entry_agent.build_entry_status("NQM6")
            self.assertEqual(after_onl_touch["active_liquidity_name"], "ONL")
            self.assertEqual(after_onl_touch["active_liquidity_price"], 28637.0)
            self.assertNotEqual(after_onl_touch["active_liquidity_name"], "LL")

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_no_leg1_50_percent_exhaustion_rotates_to_next_same_side_target(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        persisted_liquidity = {"name": "LL", "price": 100.0, "side": "lower"}
        persisted_state = {
            "last_interacted_liquidity_by_symbol": {"NQ": persisted_liquidity},
            "state_by_symbol": {
                "NQ": {
                    "last_interacted_liquidity": persisted_liquidity,
                    "step4": {"status": "WAIT", "state": {}},
                    "consumed_liquidity_levels": [],
                }
            },
        }
        snapshot = {
            "symbol": "NQM6",
            "normalized_symbol": "NQ",
            "latest_price": 95.0,
            "latest_bar_time": "2026-05-07T16:16:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 100.5, "high": 101.0, "low": 94.75, "close": 95.0},
            "tv_context": {
                "levels": {
                    "LL": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "ONL": {"price": 90.0, "status": "ACTIVE", "stack_group": "NONE"},
                }
            },
        }

        result = entry_agent.evaluate_live_step_2_1a(snapshot, {}, {"tick_size": 0.25}, persisted_state)

        self.assertEqual(result["active_level"], "ONL")
        self.assertEqual(result["level_price"], 90.0)
        self.assertTrue(
            any(
                record.get("name") == "LL"
                and record.get("exhaustion_type") == "no_leg1_50_percent_exhaustion"
                and record.get("exhausted_by") == "ONL"
                for record in result["consumed_liquidity_levels"]
            )
        )

    def test_leg1_lock_prevents_rotation_to_next_same_side_target(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        candle_a = {"timestamp": "2026-05-07T16:18:00Z", "open": 101.0, "high": 101.5, "low": 99.0, "close": 99.5}
        candle_b = {"timestamp": "2026-05-07T16:19:00Z", "open": 99.5, "high": 100.0, "low": 98.5, "close": 100.0}
        persisted_liquidity = {"name": "LL", "price": 100.0, "side": "lower"}
        step4_state = {
            "leg1_state_locked": True,
            "leg1_status": "COMPLETE",
            "active_liquidity": persisted_liquidity,
            "candle_a": candle_a,
            "candle_b": candle_b,
            "leg1_completed_at": candle_b["timestamp"],
            "leg1_reference_price": candle_a["close"],
            "leg1_reference_candle_time": candle_a["timestamp"],
            "leg1_direction": "LONG",
            "setup_direction": "LONG",
            "current_active_sequence_started_at": candle_a["timestamp"],
        }
        persisted_state = {
            "last_interacted_liquidity_by_symbol": {"NQ": persisted_liquidity},
            "state_by_symbol": {
                "NQ": {
                    "last_interacted_liquidity": persisted_liquidity,
                    "step4": {"status": "READY", "state": step4_state, "next_step": "Step 5"},
                    "step5": {"status": "WAIT", "state": {"leg2_status": "WAIT"}, "next_step": "Step 5"},
                    "consumed_liquidity_levels": [],
                }
            },
        }
        snapshot = {
            "symbol": "NQM6",
            "normalized_symbol": "NQ",
            "latest_price": 96.0,
            "latest_bar_time": "2026-05-07T16:20:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 99.0, "high": 99.25, "low": 92.5, "close": 96.0},
            "tv_context": {
                "levels": {
                    "LL": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "ONL": {"price": 90.0, "status": "ACTIVE", "stack_group": "NONE"},
                }
            },
        }

        result = entry_agent.evaluate_live_step_2_1a(snapshot, {}, {"tick_size": 0.25}, persisted_state)

        self.assertEqual(result["active_level"], "LL")
        self.assertEqual(result["level_price"], 100.0)
        self.assertFalse(
            any(
                record.get("name") == "LL"
                and record.get("exhausted_by") == "ONL"
                for record in result["consumed_liquidity_levels"]
            )
        )

    def test_current_step_remains_step2_when_active_liquidity_selected(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        snapshot = {
            "latest_price": 101.0,
            "ohlc": {"open": 100.5, "high": 101.0, "low": 100.25, "close": 101.0},
            "tv_context": {
                "levels": {
                    "ONH": {"price": 101.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "PMH": {"price": 100.0, "status": "INACTIVE", "stack_group": "NONE"},
                }
            },
            "rejection": {"rejection_mode": "OFF"},
            "step25": {"status": "WAIT"},
            "step3": {"status": "WAIT"},
            "step4": {"status": "WAIT"},
            "step5": {"status": "WAIT"},
            "step6": {"status": "WAIT"},
        }

        self.assertEqual(entry_agent.current_step_from_snapshot(snapshot), "Step 2")

    def test_observation_reset_clears_prior_day_leg1_state_and_confirms_step2(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        def fake_market_snapshot(_root):
            return {
                "source": "test",
                "symbol": "NQM6",
                "latest_price": 21425.0,
                "latest_bar_time": "2026-05-15T13:29:00Z",
                "ohlc_is_closed": True,
                "ohlc": {"open": 21410.0, "high": 21430.0, "low": 21408.0, "close": 21425.0},
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = fake_market_snapshot
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "locked": True,
                                "levels": {
                                    "PMH": {"price": 21420.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "PML": {"price": 21320.0, "status": "INACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            entry_agent.STATE_PATH.write_text(
                json.dumps(
                    {
                        "state_by_symbol": {
                            "NQ": {
                                "observation_reset_session_date": "2026-05-14",
                                "last_interacted_liquidity": {"name": "PML", "price": 21320.0, "side": "lower"},
                                "step25": {"status": "READY", "state": {"controlling_mode": "R/S"}},
                                "step4": {
                                    "status": "READY",
                                    "state": {
                                        "leg1_state_locked": True,
                                        "leg1_status": "COMPLETE",
                                        "leg1_completed_at": "2026-05-14T13:42:00Z",
                                        "leg1_reference_price": 21310.0,
                                        "leg1_reference_candle_time": "2026-05-14T13:41:00Z",
                                        "leg1_direction": "LONG",
                                        "active_liquidity": {"name": "PML", "price": 21320.0, "side": "lower"},
                                        "candle_a": {"timestamp": "2026-05-14T13:41:00Z"},
                                        "candle_b": {"timestamp": "2026-05-14T13:42:00Z"},
                                    },
                                },
                            }
                        },
                        "last_interacted_liquidity_by_symbol": {
                            "NQ": {"name": "PML", "price": 21320.0, "side": "lower"}
                        },
                    }
                ),
                encoding="utf-8",
            )

            status = entry_agent.build_entry_status("NQM6")
            state = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

        self.assertEqual(status["active_liquidity_name"], "PMH")
        self.assertEqual(status["current_step"], "Step 2")
        self.assertEqual(status["current_step_status"], "CONFIRMED")
        self.assertEqual(status["rejection_pathway_status"], "controlling")
        self.assertEqual(status["current_pathway_control"], "rejection")
        self.assertEqual(status["selected_pathway"], "rejection")
        self.assertIsNone(status["leg1_completed_at"])
        self.assertEqual(state["state_by_symbol"]["NQ"]["observation_reset_session_date"], "2026-05-15")

    def test_observation_window_blocks_entry_authorization_until_0630(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        entry_agent.run_once = lambda symbol, persist=True: {
            "requested_symbol": symbol,
            "normalized_symbol": "NQ",
            "latest_price": 100.0,
            "latest_bar_time": "2026-05-15T13:29:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
            "liquidity": {},
            "step_2_1a": {"step_2_activated": True, "active_level": "PMH", "level_price": 100.0, "side": "upper"},
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 100.0},
            "step25": {"status": "READY", "state": {"controlling_mode": "Normal Rejection Mode"}},
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4", "state": {}},
            "step4": {"status": "WAIT", "next_step": "Step 4", "state": {}},
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "ENTRY_CONFIRMED", "next_step": "Step 6", "state": {"entry_triggered": True}, "reason": "ready"},
        }
        try:
            status = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(status["entry_status"], "WAIT")
        self.assertIn("06:30 PT", status["wait_reason"])

    def test_entry_status_pre_rth_lock_blocks_step_progression_with_context(self):
        server = self._load_server()
        entry_agent = sys.modules["entry_agent"]

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot
        original_selected_liquidity = entry_agent.selected_active_liquidity_from_context
        self.addCleanup(setattr, entry_agent, "STATE_PATH", original_state_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_PATH", original_context_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_BY_SYMBOL_PATH", original_by_symbol_path)
        self.addCleanup(setattr, entry_agent, "get_latest_market_snapshot", original_market_snapshot)
        self.addCleanup(setattr, entry_agent, "selected_active_liquidity_from_context", original_selected_liquidity)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.get_latest_market_snapshot = lambda _symbol: {
                "source": "test",
                "symbol": "NQM6",
                "latest_price": 101.0,
                "latest_bar_time": "2026-05-18T13:04:00Z",
                "ohlc_is_closed": True,
                "ohlc": {"open": 99.0, "high": 102.0, "low": 98.5, "close": 101.0},
            }
            entry_agent.selected_active_liquidity_from_context = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("pre-RTH lock must run before active liquidity selection")
            )
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "locked": True,
                                "levels": {
                                    "PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "PML": {"price": 95.0, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            poisoned_state = {
                "state_by_symbol": {
                    "NQ": {
                        "last_interacted_liquidity": {"name": "PMH", "price": 100.0, "side": "upper"},
                        "step25": {"status": "READY", "state": {"controlling_mode": "Normal Rejection Mode"}},
                        "step4": {"status": "READY", "next_step": "Step 5", "state": {"leg1_status": "COMPLETE"}},
                        "step5": {"status": "READY", "next_step": "Step 6", "state": {"leg2_status": "COMPLETE"}},
                        "step6": {"status": "ENTRY_CONFIRMED", "state": {"entry_triggered": True}},
                    }
                },
                "last_interacted_liquidity_by_symbol": {
                    "NQ": {"name": "PMH", "price": 100.0, "side": "upper"}
                },
            }
            entry_agent.STATE_PATH.write_text(json.dumps(poisoned_state), encoding="utf-8")

            response = server.app.test_client().get("/entry/status?symbols=NQ")
            status = response.get_json()["symbols"][0]
            persisted_after = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot
        entry_agent.selected_active_liquidity_from_context = original_selected_liquidity

        self.assertEqual(response.status_code, 200)
        self.assertEqual(status["entry_status"], "WAIT")
        self.assertEqual(status["current_step"], "PRE_RTH_LOCK")
        self.assertEqual(status["wait_reason"], "Awaiting 6:15 RTH activation line.")
        self.assertEqual(status["last_decision"], "WAIT: Awaiting 6:15 RTH activation line.")
        self.assertIsNone(status["active_liquidity_name"])
        self.assertIsNone(status["selected_pathway"])
        self.assertEqual(status["rejection_pathway_status"], "inactive")
        self.assertEqual(status["continuation_pathway_status"], "inactive")
        self.assertEqual(status["continuation_type"], "none")
        self.assertNotIn(status["current_step"], {"Step 2", "Step 2.5", "Step 4", "Step 5", "Step 6"})
        self.assertEqual(persisted_after, poisoned_state)

    def test_entry_status_session_closed_blocks_new_setup_calculation(self):
        server = self._load_server()
        entry_agent = sys.modules["entry_agent"]

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot
        original_selected_liquidity = entry_agent.selected_active_liquidity_from_context
        self.addCleanup(setattr, entry_agent, "STATE_PATH", original_state_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_PATH", original_context_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_BY_SYMBOL_PATH", original_by_symbol_path)
        self.addCleanup(setattr, entry_agent, "get_latest_market_snapshot", original_market_snapshot)
        self.addCleanup(setattr, entry_agent, "selected_active_liquidity_from_context", original_selected_liquidity)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.get_latest_market_snapshot = lambda _symbol: {
                "source": "test",
                "symbol": "NQM6",
                "latest_price": 101.0,
                "latest_bar_time": "2026-05-18T15:00:00Z",
                "ohlc_is_closed": True,
                "ohlc": {"open": 99.0, "high": 102.0, "low": 98.5, "close": 101.0},
            }
            entry_agent.selected_active_liquidity_from_context = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("session-closed lock must run before active liquidity selection")
            )
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "locked": True,
                                "levels": {
                                    "PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "PML": {"price": 95.0, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            poisoned_state = {
                "state_by_symbol": {
                    "NQ": {
                        "last_interacted_liquidity": {"name": "PMH", "price": 100.0, "side": "upper"},
                        "step25": {"status": "READY", "state": {"controlling_mode": "Normal Rejection Mode"}},
                        "step4": {"status": "READY", "next_step": "Step 5", "state": {"leg1_status": "COMPLETE"}},
                        "step5": {"status": "READY", "next_step": "Step 6", "state": {"leg2_status": "COMPLETE"}},
                        "step6": {"status": "ENTRY_CONFIRMED", "state": {"entry_triggered": True}},
                    }
                },
                "last_interacted_liquidity_by_symbol": {
                    "NQ": {"name": "PMH", "price": 100.0, "side": "upper"}
                },
            }
            entry_agent.STATE_PATH.write_text(json.dumps(poisoned_state), encoding="utf-8")

            response = server.app.test_client().get("/entry/status?symbols=NQ")
            status = response.get_json()["symbols"][0]
            persisted_after = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot
        entry_agent.selected_active_liquidity_from_context = original_selected_liquidity

        self.assertEqual(response.status_code, 200)
        self.assertEqual(status["entry_status"], "WAIT")
        self.assertEqual(status["current_step"], "SESSION_CLOSED")
        self.assertEqual(status["wait_reason"], "Entry window closed at 8:00 AM PT.")
        self.assertEqual(status["last_decision"], "WAIT: Entry window closed at 8:00 AM PT.")
        self.assertIsNone(status["active_liquidity_name"])
        self.assertIsNone(status["selected_pathway"])
        self.assertEqual(status["rejection_pathway_status"], "inactive")
        self.assertEqual(status["continuation_pathway_status"], "inactive")
        self.assertEqual(status["continuation_type"], "none")
        self.assertNotIn(status["current_step"], {"Step 2", "Step 2.5", "Step 4", "Step 5", "Step 6"})
        self.assertEqual(persisted_after, poisoned_state)

    def test_pre_615_prior_date_step5_state_returns_clean_pre_rth_lock(self):
        server = self._load_server()
        entry_agent = sys.modules["entry_agent"]

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot
        self.addCleanup(setattr, entry_agent, "STATE_PATH", original_state_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_PATH", original_context_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_BY_SYMBOL_PATH", original_by_symbol_path)
        self.addCleanup(setattr, entry_agent, "get_latest_market_snapshot", original_market_snapshot)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.get_latest_market_snapshot = lambda _symbol: {
                "source": "test",
                "symbol": "NQM6",
                "latest_price": 101.0,
                "latest_bar_time": "2026-05-18T13:04:00Z",
                "ohlc_is_closed": True,
                "ohlc": {"open": 99.0, "high": 102.0, "low": 98.5, "close": 101.0},
            }
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps({"symbols": {"NQ": {"symbol": "NQ1!", "locked": True, "levels": {"PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"}}}}}),
                encoding="utf-8",
            )
            prior_state = self._prior_date_step5_state()
            entry_agent.STATE_PATH.write_text(json.dumps(prior_state), encoding="utf-8")

            response = server.app.test_client().get("/entry/status?symbols=NQ")
            status = response.get_json()["symbols"][0]
            persisted_after = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(status["current_step_label"], "Pre-RTH Lock")
        self._assert_clean_locked_status(status, "PRE_RTH_LOCK", "Awaiting 6:15 RTH activation line.")
        self.assertEqual(persisted_after, prior_state)

    def test_inside_window_prior_date_step5_state_is_ignored(self):
        server = self._load_server()
        entry_agent = sys.modules["entry_agent"]

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot
        self.addCleanup(setattr, entry_agent, "STATE_PATH", original_state_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_PATH", original_context_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_BY_SYMBOL_PATH", original_by_symbol_path)
        self.addCleanup(setattr, entry_agent, "get_latest_market_snapshot", original_market_snapshot)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.get_latest_market_snapshot = lambda _symbol: {
                "source": "test",
                "symbol": "NQM6",
                "latest_price": 99.0,
                "latest_bar_time": "2026-05-18T13:20:00Z",
                "ohlc_is_closed": True,
                "ohlc": {"open": 99.5, "high": 99.75, "low": 98.5, "close": 99.0},
            }
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "locked": True,
                                "levels": {
                                    "PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "PML": {"price": 95.0, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            entry_agent.STATE_PATH.write_text(json.dumps(self._prior_date_step5_state()), encoding="utf-8")

            response = server.app.test_client().get("/entry/status?symbols=NQ")
            status = response.get_json()["symbols"][0]

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(status["current_step"], "Step 5")
        self.assertIsNone(status["active_liquidity_name"])
        self.assertIsNone(status["active_liquidity_price"])
        self.assertIsNone(status["selected_pathway"])
        self.assertIsNone(status["setup_direction"])
        self.assertEqual(status["leg1_status"], "WAIT")
        self.assertEqual(status["leg1_state"], "WAIT")
        self.assertIsNone(status["leg1_completed_at"])
        self.assertIsNone(status["leg1_reference_price"])
        self.assertIsNone(status["leg1_reference_candle_time"])
        self.assertEqual(status["leg2_status"], "WAIT")
        self.assertIsNone(status["leg2_candidate_candle_time"])

    def test_at_or_after_800_prior_date_step5_state_returns_clean_session_closed(self):
        server = self._load_server()
        entry_agent = sys.modules["entry_agent"]

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot
        self.addCleanup(setattr, entry_agent, "STATE_PATH", original_state_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_PATH", original_context_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_BY_SYMBOL_PATH", original_by_symbol_path)
        self.addCleanup(setattr, entry_agent, "get_latest_market_snapshot", original_market_snapshot)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.get_latest_market_snapshot = lambda _symbol: {
                "source": "test",
                "symbol": "NQM6",
                "latest_price": 101.0,
                "latest_bar_time": "2026-05-18T15:00:00Z",
                "ohlc_is_closed": True,
                "ohlc": {"open": 99.0, "high": 102.0, "low": 98.5, "close": 101.0},
            }
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps({"symbols": {"NQ": {"symbol": "NQ1!", "locked": True, "levels": {"PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"}}}}}),
                encoding="utf-8",
            )
            prior_state = self._prior_date_step5_state()
            entry_agent.STATE_PATH.write_text(json.dumps(prior_state), encoding="utf-8")

            response = server.app.test_client().get("/entry/status?symbols=NQ")
            status = response.get_json()["symbols"][0]
            persisted_after = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(status["current_step_label"], "Session Closed")
        self._assert_clean_locked_status(status, "SESSION_CLOSED", "Entry window closed at 8:00 AM PT.")
        self.assertEqual(persisted_after, prior_state)

    def test_locked_leg1_prevents_active_liquidity_rotation(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        locked_liquidity = {"name": "LL", "price": 100.0, "side": "lower"}
        persisted_state = {
            "state_by_symbol": {
                "NQ": {
                    "last_interacted_liquidity": locked_liquidity,
                    "step4": {
                        "status": "READY",
                        "next_step": "Step 5",
                        "state": {
                            "leg1_state_locked": True,
                            "leg1_status": "COMPLETE",
                            "active_liquidity": locked_liquidity,
                            "candle_a": {"timestamp": "2026-05-15T13:25:00Z"},
                            "candle_b": {"timestamp": "2026-05-15T13:26:00Z"},
                            "leg1_completed_at": "2026-05-15T13:26:00Z",
                            "leg1_reference_price": 101.0,
                            "leg1_reference_candle_time": "2026-05-15T13:25:00Z",
                            "leg1_direction": "LONG",
                            "setup_direction": "LONG",
                        },
                    },
                    "consumed_liquidity_levels": [],
                }
            },
            "last_interacted_liquidity_by_symbol": {"NQ": locked_liquidity},
        }
        snapshot = {
            "symbol": "NQM6",
            "normalized_symbol": "NQ",
            "latest_price": 89.0,
            "latest_bar_time": "2026-05-15T13:29:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 96.0, "high": 97.0, "low": 88.0, "close": 89.0},
            "tv_context": {
                "levels": {
                    "LL": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "ONL": {"price": 90.0, "status": "ACTIVE", "stack_group": "NONE"},
                }
            },
        }

        result = entry_agent.evaluate_live_step_2_1a(snapshot, {}, {"tick_size": 0.25}, persisted_state)

        self.assertEqual(result["active_level"], "LL")
        self.assertEqual(result["level_price"], 100.0)

    def test_non_selected_pathway_cannot_overwrite_public_shared_state(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        entry_agent.run_once = lambda symbol, persist=True: {
            "requested_symbol": symbol,
            "normalized_symbol": "NQ",
            "latest_price": 99.0,
            "latest_bar_time": "2026-05-15T13:31:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 101.0, "high": 102.0, "low": 98.0, "close": 99.0},
            "liquidity": {},
            "step_2_1a": {"step_2_activated": True, "active_level": "PMH", "level_price": 100.0, "side": "upper"},
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 100.0},
            "step25": {
                "status": "READY",
                "state": {"controlling_mode": "Normal Rejection Mode", "candidate_modes": ["Normal Rejection Mode", "R/S"]},
            },
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4", "state": {}},
            "step4": {
                "status": "READY",
                "next_step": "Step 5",
                "state": {
                    "current_pathway_control": "continuation",
                    "current_controlling_mode": "R/S",
                    "current_continuation_type": "R/S",
                    "leg1_state_locked": True,
                    "leg1_status": "COMPLETE",
                    "active_liquidity": {"name": "PMH", "price": 100.0, "side": "upper"},
                    "candle_a": {"timestamp": "2026-05-15T13:27:00Z"},
                    "candle_b": {"timestamp": "2026-05-15T13:28:00Z"},
                    "leg1_completed_at": "2026-05-15T13:28:00Z",
                    "leg1_reference_price": 101.0,
                    "leg1_reference_candle_time": "2026-05-15T13:27:00Z",
                    "leg1_direction": "SHORT",
                    "setup_direction": "SHORT",
                },
            },
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        try:
            status = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(status["selected_pathway"], "rejection")
        self.assertEqual(status["current_pathway_control"], "rejection")
        self.assertEqual(status["current_controlling_mode"], "Normal Rejection Mode")
        self.assertIsNone(status["continuation_side"]["current_step"])

    def test_step4_invalidation_is_not_public_while_current_step_is_step2(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        entry_agent.run_once = lambda symbol, persist=True: {
            "requested_symbol": symbol,
            "normalized_symbol": "NQ",
            "latest_price": 100.0,
            "latest_bar_time": "2026-05-15T13:31:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
            "liquidity": {},
            "step_2_1a": {"step_2_activated": True, "active_level": "PMH", "level_price": 100.0, "side": "upper"},
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 100.0},
            "step25": {"status": "READY", "state": {"controlling_mode": "Normal Rejection Mode"}},
            "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
            "step4": {
                "step": "Step 4",
                "status": "TERMINATED",
                "next_step": "Step 2",
                "reason": "Active liquidity was penetrated beyond 50%.",
                "state": {
                    "invalidation_source": "leg1_50_percent_rule",
                    "invalidation_source_step": "Step 4",
                    "invalidation_source_candle_time": "2026-05-15T13:31:00Z",
                    "invalidated_at": "2026-05-15T13:31:00Z",
                    "active_liquidity": {"name": "PMH", "price": 100.0, "side": "upper"},
                },
            },
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        try:
            status = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(status["current_step"], "Step 2")
        self.assertEqual(status["current_step_status"], "CONFIRMED")
        self.assertEqual(status["entry_status"], "WAIT")
        self.assertIsNone(status["invalidation_reason"])
        self.assertIsNone(status["invalidation_source"])
        self.assertIsNone(status["invalidation_source_step"])
        self.assertEqual(status["internal_invalidation_reason"], "Active liquidity was penetrated beyond 50%.")
        self.assertTrue(status["last_decision"].startswith("WAIT:"))

    def test_step2_confirmed_at_uses_activation_candle_time_and_is_stable(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        activation_time = "2026-05-15T13:45:00Z"
        original_run_once = entry_agent.run_once
        entry_agent.run_once = lambda symbol, persist=True: {
            "requested_symbol": symbol,
            "normalized_symbol": "NQ",
            "latest_price": 100.0,
            "latest_bar_time": activation_time,
            "ohlc_is_closed": True,
            "ohlc": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
            "liquidity": {},
            "step_2_1a": {
                "step_2_activated": True,
                "active_level": "PMH",
                "level_price": 100.0,
                "side": "upper",
                "candle_a": {"timestamp": activation_time, "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
            },
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 100.0},
            "step25": {"status": "READY", "state": {"controlling_mode": "Normal Rejection Mode"}},
            "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
            "step4": {"status": "WAIT", "next_step": "Step 4", "state": {}},
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        try:
            first = entry_agent.build_entry_status("NQ")
            second = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(first["current_step"], "Step 2")
        self.assertEqual(first["current_step_confirmed_at"], activation_time)
        self.assertEqual(second["current_step_confirmed_at"], activation_time)

    def test_leg1_leg2_and_entry_confirmed_at_use_confirmation_candle_times(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        leg1_time = "2026-05-15T13:47:00Z"
        leg2_time = "2026-05-15T13:52:00Z"
        entry_time = "2026-05-15T13:53:00Z"
        original_run_once = entry_agent.run_once
        original_consumed_guard = entry_agent.apply_consumed_entry_setup_guard
        entry_agent.run_once = lambda symbol, persist=True: {
            "requested_symbol": symbol,
            "normalized_symbol": "NQ",
            "latest_price": 101.0,
            "latest_bar_time": entry_time,
            "ohlc_is_closed": True,
            "ohlc": {"open": 100.5, "high": 101.5, "low": 100.0, "close": 101.0},
            "liquidity": {},
            "step_2_1a": {"step_2_activated": True, "active_level": "PMH", "level_price": 100.0, "side": "upper", "candle_a": {"timestamp": "2026-05-15T13:45:00Z"}},
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 100.0},
            "step25": {"status": "READY", "state": {"controlling_mode": "Normal Rejection Mode"}},
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4", "state": {}},
            "step4": {
                "status": "READY",
                "next_step": "Step 5",
                "state": {
                    "leg1_state_locked": True,
                    "leg1_status": "COMPLETE",
                    "leg1_completed_at": leg1_time,
                    "leg1_reference_price": 100.0,
                    "leg1_reference_candle_time": "2026-05-15T13:46:00Z",
                    "leg1_direction": "SHORT",
                    "setup_direction": "SHORT",
                    "active_liquidity": {"name": "PMH", "price": 100.0, "side": "upper"},
                    "candle_a": {"timestamp": "2026-05-15T13:46:00Z"},
                    "candle_b": {"timestamp": leg1_time},
                },
            },
            "step5": {
                "status": "READY",
                "next_step": "Step 6",
                "state": {
                    "leg2_status": "VALIDATED",
                    "leg2_candidate_candle_time": leg2_time,
                    "leg2_candle": {"timestamp": leg2_time},
                    "setup_direction": "SHORT",
                    "active_liquidity": {"name": "PMH", "price": 100.0, "side": "upper"},
                    "leg1_state_locked": True,
                    "leg1_status": "COMPLETE",
                    "leg1_completed_at": leg1_time,
                    "leg1_reference_price": 100.0,
                    "leg1_reference_candle_time": "2026-05-15T13:46:00Z",
                    "leg1_direction": "SHORT",
                    "candle_a": {"timestamp": "2026-05-15T13:46:00Z"},
                    "candle_b": {"timestamp": leg1_time},
                },
            },
            "step6": {
                "status": "ENTRY_CONFIRMED",
                "next_step": "Step 6",
                "state": {
                    "entry_triggered": True,
                    "entry_candle": {"timestamp": entry_time},
                    "setup_direction": "SHORT",
                },
                "reason": "entry confirmed",
            },
        }
        entry_agent.apply_consumed_entry_setup_guard = lambda _snapshot: None
        try:
            status = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once
            entry_agent.apply_consumed_entry_setup_guard = original_consumed_guard

        self.assertEqual(status["current_step"], "Step 6")
        self.assertEqual(status["leg1_confirmed_at"], leg1_time)
        self.assertEqual(status["leg2_confirmed_at"], leg2_time)
        self.assertEqual(status["entry_status_confirmed_at"], entry_time)
        self.assertEqual(status["current_step_confirmed_at"], entry_time)

    def test_reset_clears_confirmed_at_fields(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        entry_agent.run_once = lambda symbol, persist=True: {
            "requested_symbol": symbol,
            "normalized_symbol": "NQ",
            "latest_price": 99.0,
            "latest_bar_time": "2026-05-15T14:00:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 99.0, "high": 99.5, "low": 98.5, "close": 99.0},
            "liquidity": {},
            "step_2_1a": {"step_2_activated": False},
            "rejection": {"rejection_mode": "OFF"},
            "step25": {"status": "WAIT", "state": {}},
            "step3": {"status": "WAIT", "state": {}},
            "step4": {"status": "WAIT", "state": {}},
            "step5": {"status": "WAIT", "state": {}},
            "step6": {"status": "WAIT", "state": {}},
        }
        try:
            status = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once

        self.assertIsNone(status["current_step_confirmed_at"])
        self.assertIsNone(status["leg1_confirmed_at"])
        self.assertIsNone(status["leg2_confirmed_at"])
        self.assertIsNone(status["entry_status_confirmed_at"])

    def test_sr_continuation_waits_for_controlling_structure_sweep(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_recent = entry_agent.recent_closed_bars
        original_step6 = entry_agent.evaluate_step6
        entry_agent.recent_closed_bars = lambda _symbol, _limit: [
            {"timestamp": "2026-05-15T13:20:00Z", "open": 100.25, "high": 100.50, "low": 98.75, "close": 99.00},
            {"timestamp": "2026-05-15T13:21:00Z", "open": 99.00, "high": 101.00, "low": 98.90, "close": 100.50},
            {"timestamp": "2026-05-15T13:22:00Z", "open": 100.50, "high": 100.60, "low": 99.50, "close": 100.00},
        ]
        entry_agent.evaluate_step6 = lambda _interaction: self.fail("Step 6 should not evaluate before continuation structure sweep")
        snapshot = {
            "normalized_symbol": "NQ",
            "latest_bar_time": "2026-05-15T13:22:00Z",
            "ohlc": {"open": 100.50, "high": 100.60, "low": 99.50, "close": 100.00},
            "liquidity": {"tick_size": 0.25},
        }
        step5 = {
            "status": "READY",
            "next_step": "Step 6",
            "state": {
                "controlling_mode": "S/R",
                "pathway_level": 100.0,
                "tick_size": 0.25,
                "reclaim_candle_a": {"timestamp": "2026-05-15T13:21:00Z", "open": 99.0, "high": 101.0, "low": 98.9, "close": 100.5},
                "leg2_status": "VALIDATED",
                "leg2_candle": {"timestamp": "2026-05-15T13:22:00Z", "open": 100.5, "high": 100.6, "low": 99.5, "close": 100.0},
            },
        }
        try:
            result = entry_agent.evaluate_live_step6(snapshot, step5, {})
        finally:
            entry_agent.recent_closed_bars = original_recent
            entry_agent.evaluate_step6 = original_step6

        self.assertEqual(result["status"], "WAIT")
        self.assertFalse(result["state"]["continuation_controlling_structure_swept"])
        self.assertIn("sweep", result["reason"])

    def test_sr_continuation_sweep_allows_step6_evaluation(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_recent = entry_agent.recent_closed_bars
        original_step6 = entry_agent.evaluate_step6
        entry_agent.recent_closed_bars = lambda _symbol, _limit: [
            {"timestamp": "2026-05-15T13:20:00Z", "open": 100.25, "high": 100.50, "low": 98.75, "close": 99.00},
            {"timestamp": "2026-05-15T13:21:00Z", "open": 99.00, "high": 101.00, "low": 98.90, "close": 100.50},
        ]
        entry_agent.evaluate_step6 = lambda interaction: {
            "step": "Step 6",
            "status": "ENTRY_CONFIRMED",
            "next_step": "Step 6",
            "state": dict(interaction, entry_triggered=True),
            "reason": "entry allowed",
            "events": [],
        }
        snapshot = {
            "normalized_symbol": "NQ",
            "latest_bar_time": "2026-05-15T13:22:00Z",
            "ohlc": {"open": 100.50, "high": 100.75, "low": 99.50, "close": 100.00},
            "liquidity": {"tick_size": 0.25},
        }
        step5 = {
            "status": "READY",
            "next_step": "Step 6",
            "state": {
                "controlling_mode": "S/R",
                "pathway_level": 100.0,
                "tick_size": 0.25,
                "reclaim_candle_a": {"timestamp": "2026-05-15T13:21:00Z", "open": 99.0, "high": 101.0, "low": 98.9, "close": 100.5},
                "leg2_status": "VALIDATED",
                "leg2_candle": {"timestamp": "2026-05-15T13:22:00Z", "open": 100.5, "high": 100.75, "low": 99.5, "close": 100.0},
            },
        }
        try:
            result = entry_agent.evaluate_live_step6(snapshot, step5, {})
        finally:
            entry_agent.recent_closed_bars = original_recent
            entry_agent.evaluate_step6 = original_step6

        self.assertEqual(result["status"], "ENTRY_CONFIRMED")
        self.assertTrue(result["state"]["continuation_controlling_structure_swept"])

    def test_sr_continuation_reset_uses_next_bearish_close_through_push(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        bars = [
            {"timestamp": "2026-05-15T13:18:00Z", "open": 100.25, "high": 100.40, "low": 98.50, "close": 99.00},
            {"timestamp": "2026-05-15T13:19:00Z", "open": 98.90, "high": 99.70, "low": 98.80, "close": 99.50},
            {"timestamp": "2026-05-15T13:20:00Z", "open": 99.50, "high": 99.60, "low": 98.60, "close": 98.80},
            {"timestamp": "2026-05-15T13:21:00Z", "open": 98.80, "high": 100.50, "low": 98.70, "close": 100.25},
        ]

        structure = entry_agent.continuation_controlling_structure_from_bars("S/R", 100.0, bars, "2026-05-15T13:21:00Z")

        self.assertEqual(structure["start_time"], "2026-05-15T13:20:00Z")
        self.assertEqual(structure["end_time"], "2026-05-15T13:20:00Z")
        self.assertEqual(structure["low"], 98.60)

    def test_rs_continuation_waits_for_controlling_structure_sweep(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_recent = entry_agent.recent_closed_bars
        original_step6 = entry_agent.evaluate_step6
        entry_agent.recent_closed_bars = lambda _symbol, _limit: [
            {"timestamp": "2026-05-15T13:20:00Z", "open": 99.75, "high": 101.25, "low": 99.50, "close": 101.00},
            {"timestamp": "2026-05-15T13:21:00Z", "open": 101.00, "high": 101.10, "low": 99.00, "close": 99.50},
            {"timestamp": "2026-05-15T13:22:00Z", "open": 99.50, "high": 100.50, "low": 99.40, "close": 100.00},
        ]
        entry_agent.evaluate_step6 = lambda _interaction: self.fail("Step 6 should not evaluate before continuation structure sweep")
        snapshot = {
            "normalized_symbol": "NQ",
            "latest_bar_time": "2026-05-15T13:22:00Z",
            "ohlc": {"open": 99.50, "high": 100.50, "low": 99.40, "close": 100.00},
            "liquidity": {"tick_size": 0.25},
        }
        step5 = {
            "status": "READY",
            "next_step": "Step 6",
            "state": {
                "controlling_mode": "R/S",
                "pathway_level": 100.0,
                "tick_size": 0.25,
                "reclaim_candle_a": {"timestamp": "2026-05-15T13:21:00Z", "open": 101.0, "high": 101.1, "low": 99.0, "close": 99.5},
                "leg2_status": "VALIDATED",
                "leg2_candle": {"timestamp": "2026-05-15T13:22:00Z", "open": 99.5, "high": 100.5, "low": 99.4, "close": 100.0},
            },
        }
        try:
            result = entry_agent.evaluate_live_step6(snapshot, step5, {})
        finally:
            entry_agent.recent_closed_bars = original_recent
            entry_agent.evaluate_step6 = original_step6

        self.assertEqual(result["status"], "WAIT")
        self.assertFalse(result["state"]["continuation_controlling_structure_swept"])
        self.assertIn("controlling-structure low", result["reason"])

    def test_rs_continuation_sweep_allows_step6_evaluation(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_recent = entry_agent.recent_closed_bars
        original_step6 = entry_agent.evaluate_step6
        entry_agent.recent_closed_bars = lambda _symbol, _limit: [
            {"timestamp": "2026-05-15T13:20:00Z", "open": 99.75, "high": 101.25, "low": 99.50, "close": 101.00},
            {"timestamp": "2026-05-15T13:21:00Z", "open": 101.00, "high": 101.10, "low": 99.00, "close": 99.50},
        ]
        entry_agent.evaluate_step6 = lambda interaction: {
            "step": "Step 6",
            "status": "ENTRY_CONFIRMED",
            "next_step": "Step 6",
            "state": dict(interaction, entry_triggered=True),
            "reason": "entry allowed",
            "events": [],
        }
        snapshot = {
            "normalized_symbol": "NQ",
            "latest_bar_time": "2026-05-15T13:22:00Z",
            "ohlc": {"open": 99.50, "high": 100.50, "low": 99.25, "close": 100.00},
            "liquidity": {"tick_size": 0.25},
        }
        step5 = {
            "status": "READY",
            "next_step": "Step 6",
            "state": {
                "controlling_mode": "R/S",
                "pathway_level": 100.0,
                "tick_size": 0.25,
                "reclaim_candle_a": {"timestamp": "2026-05-15T13:21:00Z", "open": 101.0, "high": 101.1, "low": 99.0, "close": 99.5},
                "leg2_status": "VALIDATED",
                "leg2_candle": {"timestamp": "2026-05-15T13:22:00Z", "open": 99.5, "high": 100.5, "low": 99.25, "close": 100.0},
            },
        }
        try:
            result = entry_agent.evaluate_live_step6(snapshot, step5, {})
        finally:
            entry_agent.recent_closed_bars = original_recent
            entry_agent.evaluate_step6 = original_step6

        self.assertEqual(result["status"], "ENTRY_CONFIRMED")
        self.assertTrue(result["state"]["continuation_controlling_structure_swept"])

    def test_rs_continuation_reset_uses_next_bullish_close_through_push(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        bars = [
            {"timestamp": "2026-05-15T13:18:00Z", "open": 99.75, "high": 101.50, "low": 99.60, "close": 101.00},
            {"timestamp": "2026-05-15T13:19:00Z", "open": 101.10, "high": 101.20, "low": 100.40, "close": 100.50},
            {"timestamp": "2026-05-15T13:20:00Z", "open": 100.50, "high": 101.40, "low": 100.40, "close": 101.20},
            {"timestamp": "2026-05-15T13:21:00Z", "open": 101.20, "high": 101.30, "low": 99.50, "close": 99.75},
        ]

        structure = entry_agent.continuation_controlling_structure_from_bars("R/S", 100.0, bars, "2026-05-15T13:21:00Z")

        self.assertEqual(structure["start_time"], "2026-05-15T13:20:00Z")
        self.assertEqual(structure["end_time"], "2026-05-15T13:20:00Z")
        self.assertEqual(structure["high"], 101.40)

    def test_step2_wick_touch_selects_liquidity_but_waits_for_boundary_close(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        tv_context = {
            "levels": {
                "PMH": {"price": 49307, "status": "ACTIVE", "stack_group": "NONE"}
            }
        }

        selected = entry_agent.selected_active_liquidity_from_context(
            tv_context,
            49300,
            {"open": 49290, "high": 49310, "low": 49280, "close": 49300},
            tick_size=1.0,
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected["name"], "PMH")

        upper = entry_agent.step_2_1a_initial_state("PMH", 49307.0, "upper", tick_size=1.0)
        entry_agent.evaluate_step_2_1a_candle(
            upper,
            {"timestamp": "2026-05-19T13:30:00Z", "open": 49290, "high": 49310, "low": 49280, "close": 49300},
            0,
        )
        self.assertFalse(upper["step_2_activated"])
        self.assertTrue(upper["pre_activation_probe_boundary"]["active"])
        self.assertEqual(upper["pre_activation_probe_boundary"]["boundary_price"], 49310)
        entry_agent.evaluate_step_2_1a_candle(
            upper,
            {"timestamp": "2026-05-19T13:31:00Z", "open": 49302, "high": 49320, "low": 49298, "close": 49309},
            1,
        )
        self.assertFalse(upper["step_2_activated"])
        self.assertEqual(upper["pre_activation_probe_boundary"]["boundary_price"], 49320)
        entry_agent.evaluate_step_2_1a_candle(
            upper,
            {"timestamp": "2026-05-19T13:32:00Z", "open": 49310, "high": 49322, "low": 49308, "close": 49321},
            2,
        )
        self.assertTrue(upper["step_2_activated"])

        lower = entry_agent.step_2_1a_initial_state("PML", 100.0, "lower", tick_size=0.25)
        entry_agent.evaluate_step_2_1a_candle(
            lower,
            {"timestamp": "2026-05-19T13:30:00Z", "open": 100.5, "high": 100.75, "low": 99.5, "close": 100.1},
            0,
        )
        self.assertFalse(lower["step_2_activated"])
        self.assertTrue(lower["pre_activation_probe_boundary"]["active"])
        self.assertEqual(lower["pre_activation_probe_boundary"]["boundary_price"], 99.5)
        entry_agent.evaluate_step_2_1a_candle(
            lower,
            {"timestamp": "2026-05-19T13:31:00Z", "open": 100.0, "high": 100.25, "low": 99.0, "close": 99.6},
            1,
        )
        self.assertFalse(lower["step_2_activated"])
        self.assertEqual(lower["pre_activation_probe_boundary"]["boundary_price"], 99.0)
        entry_agent.evaluate_step_2_1a_candle(
            lower,
            {"timestamp": "2026-05-19T13:32:00Z", "open": 99.6, "high": 99.8, "low": 98.75, "close": 98.75},
            2,
        )
        self.assertTrue(lower["step_2_activated"])

    def test_ym_pml_ll_low_stack_waits_until_close_beyond_extreme_and_displays_combined(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        tv_context = {
            "levels": {
                "PML": {"price": 49731.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "LL": {"price": 49730.0, "status": "ACTIVE", "stack_group": "LOW 1"},
            }
        }

        inside = entry_agent.selected_active_liquidity_from_context(
            tv_context,
            49730.5,
            {"open": 49732.0, "high": 49733.0, "low": 49730.25, "close": 49730.5},
            tick_size=1.0,
        )
        exact_ll = entry_agent.selected_active_liquidity_from_context(
            tv_context,
            49730.0,
            {"open": 49731.0, "high": 49732.0, "low": 49729.0, "close": 49730.0},
            tick_size=1.0,
        )
        beyond_ll = entry_agent.selected_active_liquidity_from_context(
            tv_context,
            49729.0,
            {"open": 49731.0, "high": 49732.0, "low": 49728.0, "close": 49729.0},
            tick_size=1.0,
        )

        self.assertIsNone(inside)
        self.assertEqual(exact_ll["name"], "LL")
        self.assertEqual(exact_ll["display_name"], "PML/LL Liquidity")
        self.assertEqual(beyond_ll["name"], "LL")
        self.assertEqual(beyond_ll["display_name"], "PML/LL Liquidity")
        self.assertEqual(beyond_ll["group"]["display_name"], "PML/LL Liquidity")
        self.assertEqual(
            entry_agent.active_liquidity_from_snapshot(
                {
                    "latest_price": 49729.0,
                    "ohlc_is_closed": True,
                    "ohlc": {"open": 49731.0, "high": 49732.0, "low": 49728.0, "close": 49729.0},
                    "tv_context": tv_context,
                    "liquidity": {"tick_size": 1.0},
                    "step_2_1a": {
                        "active_level": "LL",
                        "level_price": 49730.0,
                        "active_liquidity_group": beyond_ll["group"],
                        "last_interacted_liquidity": {
                            "name": "LL",
                            "price": 49730.0,
                            "display_name": "PML/LL Liquidity",
                            "group": beyond_ll["group"],
                        },
                    },
                }
            ),
            ("PML/LL Liquidity", 49730.0),
        )

    def test_ym_below_pmh_does_not_mark_pmh_active_liquidity(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = lambda _symbol: {
                "source": "test",
                "symbol": "YMM6",
                "latest_price": 49200,
                "latest_bar_time": "2026-05-06T15:00:00Z",
                "ohlc": {"open": 49195, "high": 49205, "low": 49190, "close": 49200},
            }
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "YM": {
                                "symbol": "YM1!",
                                "levels": {
                                    "PMH": {"price": 49307, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            status = entry_agent.build_entry_status("YMM6")
            self.assertIsNone(status["active_liquidity_name"])
            self.assertIsNone(status["active_liquidity_price"])
            self.assertEqual(status["next_liquidity_above"], {"name": "PMH", "price": 49307.0})

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_ym_touching_pmh_marks_pmh_active_liquidity(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = lambda _symbol: {
                "source": "test",
                "symbol": "YMM6",
                "latest_price": 49307,
                "latest_bar_time": "2026-05-06T15:00:00Z",
                "ohlc": {"open": 49300, "high": 49307, "low": 49295, "close": 49307},
            }
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "YM": {
                                "symbol": "YM1!",
                                "levels": {
                                    "PMH": {"price": 49307, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            status = entry_agent.build_entry_status("YMM6")
            self.assertEqual(status["active_liquidity_name"], "PMH")
            self.assertEqual(status["active_liquidity_price"], 49307.0)

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_active_liquidity_persists_after_rejection_and_updates_on_new_interaction(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        market = {
            "latest_price": 49200,
            "latest_bar_time": "2026-05-06T15:00:00Z",
            "ohlc": {"open": 49195, "high": 49205, "low": 49190, "close": 49200},
        }

        def fake_market_snapshot(_symbol):
            return {
                "source": "test",
                "symbol": "YMM6",
                "latest_price": market["latest_price"],
                "latest_bar_time": market["latest_bar_time"],
                "ohlc": dict(market["ohlc"]),
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = fake_market_snapshot
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "YM": {
                                "symbol": "YM1!",
                                "levels": {
                                    "PMH": {"price": 49307, "status": "ACTIVE", "stack_group": "NONE"},
                                    "ONH": {"price": 49400, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            below = entry_agent.build_entry_status("YMM6")
            self.assertIsNone(below["active_liquidity_name"])

            market.update(
                {
                    "latest_price": 49307,
                    "latest_bar_time": "2026-05-06T15:01:00Z",
                    "ohlc": {"open": 49300, "high": 49307, "low": 49295, "close": 49307},
                }
            )
            touch = entry_agent.build_entry_status("YMM6")
            self.assertEqual(touch["active_liquidity_name"], "PMH")
            self.assertEqual(touch["active_liquidity_price"], 49307.0)

            market.update(
                {
                    "latest_price": 49280,
                    "latest_bar_time": "2026-05-06T15:02:00Z",
                    "ohlc": {"open": 49300, "high": 49302, "low": 49275, "close": 49280},
                }
            )
            reject_away = entry_agent.build_entry_status("YMM6")
            self.assertEqual(reject_away["active_liquidity_name"], "PMH")
            self.assertEqual(reject_away["active_liquidity_price"], 49307.0)

            market.update(
                {
                    "latest_price": 49400,
                    "latest_bar_time": "2026-05-06T15:03:00Z",
                    "ohlc": {"open": 49390, "high": 49400, "low": 49385, "close": 49400},
                }
            )
            new_level = entry_agent.build_entry_status("YMM6")
            self.assertEqual(new_level["active_liquidity_name"], "ONH")
            self.assertEqual(new_level["active_liquidity_price"], 49400.0)

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_stale_step5_state_is_cleared_when_active_liquidity_becomes_na(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = lambda symbol: {
                "source": "test",
                "symbol": symbol,
                "latest_price": 49280,
                "latest_bar_time": "2026-05-06T15:02:00Z",
                "ohlc": {"open": 49300, "high": 49302, "low": 49275, "close": 49280},
            }
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "YM": {
                                "symbol": "YM1!",
                                "levels": {
                                    "PMH": {"price": 49307, "status": "n/a", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            stale_state = {
                "state_by_symbol": {
                    "YM": {
                        "normalized_symbol": "YM",
                        "step_2_1a": {
                            "active_level": "PMH",
                            "level_price": 49307.0,
                            "last_interacted_liquidity": {"name": "PMH", "price": 49307.0},
                        },
                        "last_interacted_liquidity": {"name": "PMH", "price": 49307.0},
                        "step4": {
                            "status": "READY",
                            "state": {
                                "setup_direction": "SHORT",
                                "leg1_status": "COMPLETE",
                                "leg1_state_locked": True,
                                "leg1_completed_at": "2026-05-06T15:01:00Z",
                                "leg1_reference_price": 49307.0,
                                "active_liquidity": {"name": "PMH", "price": 49307.0},
                            },
                        },
                        "step5": {
                            "status": "READY",
                            "state": {
                                "setup_direction": "SHORT",
                                "leg2_status": "CONFIRMED",
                                "leg2_candidate_candle_time": "2026-05-06T15:02:00Z",
                                "leg2_reference_price": 49307.0,
                                "invalidation_source": "stale",
                            },
                        },
                    }
                },
                "last_interacted_liquidity_by_symbol": {
                    "YM": {"name": "PMH", "price": 49307.0},
                },
            }
            entry_agent.STATE_PATH.write_text(json.dumps(stale_state), encoding="utf-8")

            status = entry_agent.build_entry_status("YMM6")
            persisted = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))["state_by_symbol"]["YM"]

            self.assertEqual(status["current_step"], "Step 2")
            self.assertEqual(status["current_step_label"], "Step 2 (Liquidity Close / Pathway Activation)")
            self.assertEqual(status["entry_status"], "WAIT")
            self.assertEqual(status["wait_reason"], "No active liquidity selected.")
            self.assertIsNone(status["active_liquidity_name"])
            self.assertIsNone(status["active_liquidity_price"])
            self.assertIsNone(status["setup_direction"])
            self.assertFalse(status["rejection_mode_entered"])
            self.assertEqual(status["leg1_status"], "WAIT")
            self.assertEqual(status["leg2_status"], "WAIT")
            self.assertIsNone(status["leg1_completed_at"])
            self.assertIsNone(status["leg1_reference_price"])
            self.assertIsNone(status["leg2_candidate_candle_time"])
            self.assertIsNone(status["leg2_reference_price"])
            self.assertIsNone(status["invalidation_source"])
            self.assertIsNone(status["invalidation_reason"])
            self.assertIsNone(persisted["step_2_1a"]["last_interacted_liquidity"])
            self.assertEqual(persisted["step5"]["state"], {})
            self.assertNotIn("YM", persisted["last_interacted_liquidity_by_symbol"])

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_intrabar_poke_does_not_publish_leg1_complete_until_close_confirmed(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        market = {
            "ohlc_is_closed": False,
            "ohlc": {"open": 50000.0, "high": 50012.0, "low": 49996.0, "close": 50008.0},
        }

        def fake_market_snapshot(symbol):
            return {
                "source": "test",
                "symbol": symbol,
                "latest_price": market["ohlc"]["close"],
                "latest_bar_time": "2026-05-06T15:02:00Z",
                "ohlc": dict(market["ohlc"]),
                "ohlc_is_closed": market["ohlc_is_closed"],
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = fake_market_snapshot
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "levels": {
                                    "PMH": {"price": 50000.0, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            entry_agent.STATE_PATH.write_text(
                json.dumps(
                    {
                        "state_by_symbol": {
                            "NQ": {
                                "normalized_symbol": "NQ",
                                "last_interacted_liquidity": {"name": "PMH", "price": 50000.0, "side": "upper"},
                                "step_2_1a": {
                                    "active_level": "PMH",
                                    "level_price": 50000.0,
                                    "last_interacted_liquidity": {"name": "PMH", "price": 50000.0, "side": "upper"},
                                },
                                "step4": {
                                    "status": "READY",
                                    "next_step": "Step 5",
                                    "state": {
                                        "setup_direction": "SHORT",
                                        "leg1_status": "COMPLETE",
                                        "leg1_state_locked": True,
                                        "leg1_completed_at": "2026-05-06T15:02:00Z",
                                        "leg1_reference_price": 50010.0,
                                        "leg1_reference_candle_time": "2026-05-06T15:02:00Z",
                                        "leg1_direction": "SHORT",
                                        "active_liquidity": {"name": "PMH", "price": 50000.0},
                                        "candle_a": {"timestamp": "2026-05-06T15:01:00Z"},
                                        "candle_b": {"timestamp": "2026-05-06T15:02:00Z"},
                                    },
                                },
                            }
                        },
                        "last_interacted_liquidity_by_symbol": {
                            "NQ": {"name": "PMH", "price": 50000.0, "side": "upper"},
                        },
                    }
                ),
                encoding="utf-8",
            )

            intrabar = entry_agent.build_entry_status("NQM6")
            self.assertEqual(intrabar["entry_status"], "WAIT")
            self.assertNotIn(intrabar["current_step"], {"Step 5", "Step 6"})
            self.assertEqual(intrabar["leg1_status"], "WAIT")
            self.assertIsNone(intrabar["setup_direction"])
            self.assertIsNone(intrabar["leg1_completed_at"])
            self.assertIn(
                intrabar["wait_reason"],
                {
                    "Monitoring current 1-minute candle until close confirmation.",
                    "No active liquidity selected.",
                },
            )

            market["ohlc_is_closed"] = True
            confirmed = entry_agent.build_entry_status("NQM6")
            self.assertEqual(confirmed["current_step"], "Step 4")
            self.assertEqual(confirmed["leg1_status"], "COMPLETE")
            self.assertNotEqual(confirmed["wait_reason"], "Monitoring current 1-minute candle until close confirmation.")

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_unclosed_current_candle_does_not_publish_advanced_status_fields(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        current_time = "2026-05-07T13:45:00Z"
        current_candle = {
            "open": 50000.0,
            "high": 50020.0,
            "low": 49995.0,
            "close": 50015.0,
            "timestamp": current_time,
        }

        def fake_run_once(symbol, persist=True):
            return {
                "requested_symbol": symbol,
                "normalized_symbol": "NQ",
                "latest_price": current_candle["close"],
                "latest_bar_time": current_time,
                "ohlc": dict(current_candle),
                "ohlc_is_closed": False,
                "liquidity": {"tick_size": 0.25},
                "step_2_1a": {
                    "active_level": "PMH",
                    "level_price": 50000.0,
                    "last_interacted_liquidity": {"name": "PMH", "price": 50000.0},
                },
                "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 50000.0},
                "step25": {"status": "READY"},
                "step3": {"status": "ALLOW_STEP_4"},
                "step4": {
                    "status": "READY",
                    "next_step": "Step 5",
                    "state": {
                        "setup_direction": "SHORT",
                        "leg1_direction": "SHORT",
                        "leg1_status": "COMPLETE",
                        "leg1_state_locked": True,
                        "leg1_completed_at": current_time,
                        "leg1_reference_candle_time": current_time,
                        "latest_candle": dict(current_candle),
                    },
                },
                "step5": {
                    "status": "READY",
                    "next_step": "Step 6",
                    "state": {
                        "setup_direction": "SHORT",
                        "leg2_status": "COMPLETE",
                        "leg2_candidate_candle_time": current_time,
                        "latest_candle": dict(current_candle),
                    },
                },
                "step6": {
                    "status": "ENTRY_CONFIRMED",
                    "state": {
                        "setup_direction": "SHORT",
                        "entry_triggered": True,
                        "entry_candidate": dict(current_candle),
                        "entry_candle": dict(current_candle),
                    },
                },
            }

        entry_agent.run_once = fake_run_once
        try:
            status = entry_agent.build_entry_status("NQM6")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(status["entry_status"], "WAIT")
        self.assertNotIn(status["current_step"], {"Step 5", "Step 6"})
        self.assertEqual(status["leg1_status"], "WAIT")
        self.assertEqual(status["leg2_status"], "WAIT")
        self.assertIsNone(status["setup_direction"])
        self.assertFalse(status["rejection_mode_entered"])
        self.assertIsNone(status["leg1_completed_at"])
        self.assertIsNone(status["leg2_candidate_candle_time"])
        self.assertEqual(status["wait_reason"], "Monitoring current 1-minute candle until close confirmation.")

    def test_unclosed_leg1_candle1_masks_step4_invalidation_publication(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        current_time = "2026-05-14T13:39:00Z"
        current_candle = {
            "open": 21420.0,
            "high": 21424.0,
            "low": 21410.0,
            "close": 21418.0,
            "timestamp": current_time,
        }

        def fake_run_once(symbol, persist=True):
            return {
                "requested_symbol": symbol,
                "normalized_symbol": "NQ",
                "latest_price": current_candle["close"],
                "latest_bar_time": current_time,
                "ohlc": dict(current_candle),
                "ohlc_is_closed": False,
                "liquidity": {"tick_size": 0.25},
                "step_2_1a": {
                    "active_level": "ONH",
                    "level_price": 21400.0,
                    "last_interacted_liquidity": {"name": "ONH", "price": 21400.0},
                },
                "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "ONH", "trigger_price": 21400.0},
                "step25": {"status": "READY"},
                "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4"},
                "step4": {
                    "status": "TERMINATED",
                    "next_step": "Step 1",
                    "reason": "Candle B failed both close-based participation and 34% wick-based participation.",
                    "state": {
                        "latest_candle": dict(current_candle),
                        "candle_b": dict(current_candle),
                        "leg1_status": "INVALID",
                        "leg1_window_active": True,
                        "leg1_window_started_at": current_time,
                        "leg1_window_candle_index": 1,
                        "leg1_window_remaining": 3,
                        "leg1_window_expires_at": "2026-05-14T13:42:00Z",
                        "invalidation_source": "step4",
                        "invalidation_source_step": "Step 4",
                    },
                },
                "step5": {"status": "WAIT", "state": {}, "next_step": "Step 4"},
                "step6": {"status": "WAIT", "state": {}, "next_step": "Step 4"},
            }

        entry_agent.run_once = fake_run_once
        try:
            status = entry_agent.build_entry_status("NQM6")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(status["current_step"], "Step 2")
        self.assertEqual(status["entry_status"], "WAIT")
        self.assertEqual(status["leg1_state"], "WAIT")
        self.assertIsNone(status["invalidation_reason"])
        self.assertIsNone(status["invalidation_source"])
        self.assertTrue(status["leg1_window_active"])
        self.assertEqual(status["leg1_window_candle_index"], 1)

    def test_unclosed_leg1_50_percent_invalidation_source_is_not_public(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        current_time = "2026-05-14T13:39:00Z"
        snapshot = {
            "latest_price": 21418.0,
            "latest_bar_time": current_time,
            "ohlc": {"open": 21420.0, "high": 21428.0, "low": 21370.0, "close": 21418.0},
            "ohlc_is_closed": False,
            "step4": {
                "status": "TERMINATED",
                "reason": "Leg 1 invalid: active liquidity was penetrated beyond 50% before Leg 1 formed.",
                "state": {
                    "latest_candle": {"timestamp": current_time},
                    "leg1_status": "INVALID",
                    "leg1_window_active": True,
                    "leg1_window_candle_index": 1,
                    "invalidation_source": "leg1_50_percent_rule",
                    "invalidation_source_step": "Step 4",
                },
            },
            "step5": {"status": "WAIT", "state": {}},
            "step6": {"status": "WAIT", "state": {}},
        }

        entry_agent.hide_unconfirmed_current_candle_advancement(snapshot)

        self.assertEqual(snapshot["step4"]["status"], "WAIT")
        self.assertEqual(snapshot["step4"]["state"]["leg1_status"], "WAIT")
        self.assertIsNone(snapshot["step4"]["state"].get("invalidation_source"))
        self.assertEqual(snapshot["step4"]["state"]["leg1_window_candle_index"], 1)

    def test_leg1_window_starts_on_step2_confirmation_without_counting_confirmation_candle(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        confirmation = {
            "open": 100.0,
            "high": 101.0,
            "low": 99.5,
            "close": 100.5,
            "timestamp": "2026-05-15T13:40:00Z",
        }
        candle1_fail = {
            "open": 101.2,
            "high": 101.6,
            "low": 101.1,
            "close": 101.5,
            "timestamp": "2026-05-15T13:41:00Z",
        }
        candle1_valid = {
            "open": 101.2,
            "high": 101.6,
            "low": 100.6,
            "close": 100.75,
            "timestamp": "2026-05-15T13:41:00Z",
        }
        step25 = {
            "status": "READY",
            "state": {
                "rejection_mode": "ON",
                "interaction_state": "ACTIVE",
                "step25_pathway_selection_complete": True,
                "controlling_mode": "Normal Rejection Mode",
                "candidate_modes": ["Normal Rejection Mode"],
                "initial_candle_a": confirmation,
            },
        }
        step3 = {
            "status": "ALLOW_STEP_4",
            "next_step": "Step 4",
            "state": {
                "step3_allows_structure": True,
                "active_liquidity": {"name": "PMH", "price": 100.0},
            },
        }
        rejection = {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 100.0}

        def snapshot(candle):
            return {
                "latest_bar_time": candle["timestamp"],
                "ohlc": candle,
                "ohlc_is_closed": True,
                "liquidity": {"nearest_level_below": {"name": "PML", "price": 95.0}, "tick_size": 0.25},
                "atr": {"atr_1m_14": 10.0},
                "tv_context": {"daily_atr14": 40.0},
            }

        confirmation_result = entry_agent.evaluate_live_step4(snapshot(confirmation), rejection, step25, step3, {})
        self.assertEqual(confirmation_result["status"], "WAIT")
        self.assertTrue(confirmation_result["state"]["leg1_window_active"])
        self.assertEqual(confirmation_result["state"]["leg1_window_started_at"], confirmation["timestamp"])
        self.assertEqual(confirmation_result["state"]["leg1_window_candle_index"], 0)
        self.assertEqual(confirmation_result["state"]["leg1_window_remaining"], 4)
        self.assertEqual(confirmation_result["state"]["leg1_window_expires_at"], "2026-05-15T13:44:00Z")

        candle1_result = entry_agent.evaluate_live_step4(
            snapshot(candle1_fail),
            rejection,
            step25,
            step3,
            {"step4": confirmation_result},
        )
        self.assertEqual(candle1_result["status"], "WAIT")
        self.assertEqual(candle1_result["state"]["leg1_window_candle_index"], 1)
        self.assertEqual(candle1_result["state"]["leg1_window_remaining"], 3)

        complete_result = entry_agent.evaluate_live_step4(
            snapshot(candle1_valid),
            rejection,
            step25,
            step3,
            {"step4": confirmation_result},
        )
        self.assertEqual(complete_result["status"], "READY")
        self.assertEqual(complete_result["state"]["leg1_status"], "COMPLETE")
        self.assertFalse(complete_result["state"]["leg1_window_active"])
        self.assertFalse(complete_result["state"]["leg1_window_invalidated"])

    def test_leg1_window_candle4_invalidates_and_reasoning_includes_count(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step4_engine
            server = self._load_server()
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        state = {
            "system_state": "REJECTION MODE ON",
            "trade_mode": "ON",
            "rejection_mode": "ON",
            "interaction_state": "ACTIVE",
            "setup_direction": "SHORT",
            "step25_pathway_selection_complete": True,
            "step3_allows_structure": True,
            "controlling_mode": "Normal Rejection Mode",
            "candidate_modes": ["Normal Rejection Mode"],
            "initial_candle_a": {"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5, "timestamp": "2026-05-15T13:40:00Z"},
            "nearest_opposing_liquidity": {"name": "PML", "price": 95.0},
            "atr_1m_14": 10.0,
            "daily_atr14": 40.0,
            "events": [],
        }
        step4_engine.initialize_leg1_window(state, "2026-05-15T13:40:00Z")

        for minute in range(41, 45):
            result = step4_engine.evaluate_step4(
                state,
                {"open": 101.2, "high": 101.6, "low": 101.1, "close": 101.5, "timestamp": f"2026-05-15T13:{minute}:00Z"},
            )
            state = result["state"]

        expected_reason = "Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation."
        self.assertEqual(result["step"], "Step 7")
        self.assertEqual(result["status"], "TERMINATED")
        self.assertEqual(result["reason"], expected_reason)
        self.assertFalse(result["state"]["leg1_window_active"])
        self.assertTrue(result["state"]["leg1_window_invalidated"])
        self.assertEqual(result["state"]["leg1_window_invalidation_reason"], expected_reason)
        self.assertEqual(result["state"]["leg1_window_candle_index"], 4)
        self.assertEqual(result["state"]["leg1_window_remaining"], 0)

        reasoning = server.entry_reasoning_record(
            {
                "symbol": "NQ",
                "leg1_window_active": result["state"]["leg1_window_active"],
                "leg1_window_started_at": result["state"]["leg1_window_started_at"],
                "leg1_window_candle_index": result["state"]["leg1_window_candle_index"],
                "leg1_window_remaining": result["state"]["leg1_window_remaining"],
                "leg1_window_expires_at": result["state"]["leg1_window_expires_at"],
                "leg1_window_invalidated": result["state"]["leg1_window_invalidated"],
                "leg1_window_invalidation_reason": result["state"]["leg1_window_invalidation_reason"],
            }
        )
        self.assertFalse(reasoning["leg1_window_active"])
        self.assertEqual(reasoning["leg1_window_candle_index"], 4)
        self.assertEqual(reasoning["leg1_window_remaining"], 0)
        self.assertEqual(reasoning["leg1_window_invalidation_reason"], expected_reason)

    def test_locked_leg1_survives_rejection_to_continuation_control_toggle(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        current_close = {"value": 21395.0}
        leg1_time = "2026-05-14T13:40:00Z"
        locked_leg1 = {
            "setup_direction": "SHORT",
            "leg1_direction": "SHORT",
            "leg1_status": "COMPLETE",
            "leg1_state_locked": True,
            "leg1_completed_at": leg1_time,
            "leg1_reference_price": 21408.0,
            "leg1_reference_candle_time": "2026-05-14T13:38:00Z",
            "active_liquidity": {"name": "PMH", "price": 21400.0, "side": "upper"},
            "candle_a": {"timestamp": "2026-05-14T13:38:00Z"},
            "candle_b": {"timestamp": leg1_time},
        }

        def fake_run_once(symbol, persist=True):
            close = current_close["value"]
            return {
                "requested_symbol": symbol,
                "normalized_symbol": "NQ",
                "latest_price": close,
                "latest_bar_time": "2026-05-14T13:41:00Z",
                "ohlc": {"open": close, "high": close + 2.0, "low": close - 2.0, "close": close},
                "ohlc_is_closed": True,
                "liquidity": {"tick_size": 0.25},
                "step_2_1a": {},
                "rejection": {"rejection_mode": "OFF"},
                "step25": {"status": "WAIT", "state": {}},
                "step3": {"status": "WAIT", "state": {}},
                "step4": {"status": "READY", "next_step": "Step 5", "state": dict(locked_leg1)},
                "step5": {"status": "WAIT", "state": dict(locked_leg1), "next_step": "Step 5"},
                "step6": {"status": "WAIT", "state": {}, "next_step": "Step 5"},
            }

        entry_agent.run_once = fake_run_once
        try:
            status = entry_agent.build_entry_status("NQM6")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(status["current_step"], "Step 4")
        self.assertEqual(status["leg1_state"], "COMPLETE")
        self.assertTrue(status["leg1_locked"])
        self.assertEqual(status["leg1_reference_price"], 21408.0)
        self.assertEqual(status["leg1_completed_at"], leg1_time)
        self.assertEqual(status["active_liquidity_name"], "PMH")
        self.assertEqual(status["current_pathway_control"], "continuation")
        self.assertEqual(status["current_controlling_mode"], "R/S")
        self.assertEqual(status["continuation_pathway_status"], "controlling")
        self.assertNotEqual(status["current_step"], "Step 2")

    def test_locked_leg1_survives_continuation_back_to_rejection_control_toggle(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        leg1_time = "2026-05-14T13:40:00Z"

        def fake_run_once(symbol, persist=True):
            return {
                "requested_symbol": symbol,
                "normalized_symbol": "NQ",
                "latest_price": 21406.0,
                "latest_bar_time": "2026-05-14T13:42:00Z",
                "ohlc": {"open": 21396.0, "high": 21408.0, "low": 21394.0, "close": 21406.0},
                "ohlc_is_closed": True,
                "liquidity": {"tick_size": 0.25},
                "step_2_1a": {},
                "rejection": {"rejection_mode": "OFF"},
                "step25": {"status": "WAIT", "state": {}},
                "step3": {"status": "WAIT", "state": {}},
                "step4": {
                    "status": "READY",
                    "next_step": "Step 5",
                    "state": {
                        "setup_direction": "SHORT",
                        "leg1_direction": "SHORT",
                        "leg1_status": "COMPLETE",
                        "leg1_state_locked": True,
                        "leg1_completed_at": leg1_time,
                        "leg1_reference_price": 21408.0,
                        "leg1_reference_candle_time": "2026-05-14T13:38:00Z",
                        "active_liquidity": {"name": "PMH", "price": 21400.0, "side": "upper"},
                        "candle_a": {"timestamp": "2026-05-14T13:38:00Z"},
                        "candle_b": {"timestamp": leg1_time},
                    },
                },
                "step5": {"status": "WAIT", "state": {}, "next_step": "Step 5"},
                "step6": {"status": "WAIT", "state": {}, "next_step": "Step 5"},
            }

        entry_agent.run_once = fake_run_once
        try:
            status = entry_agent.build_entry_status("NQM6")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(status["current_step"], "Step 4")
        self.assertEqual(status["leg1_state"], "COMPLETE")
        self.assertTrue(status["leg1_locked"])
        self.assertEqual(status["leg1_reference_price"], 21408.0)
        self.assertEqual(status["leg1_completed_at"], leg1_time)
        self.assertEqual(status["current_pathway_control"], "rejection")
        self.assertEqual(status["current_controlling_mode"], "Normal Rejection Mode")
        self.assertEqual(status["rejection_pathway_status"], "controlling")

    def test_step6_can_publish_live_after_prior_closed_leg2(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        current_time = "2026-05-07T13:45:00Z"
        leg1_time = "2026-05-07T13:42:00Z"
        leg2_time = "2026-05-07T13:44:00Z"
        current_candle = {
            "open": 50010.0,
            "high": 50020.0,
            "low": 49995.0,
            "close": 50005.0,
            "timestamp": current_time,
        }

        def fake_run_once(symbol, persist=True):
            return {
                "requested_symbol": symbol,
                "normalized_symbol": "NQ",
                "latest_price": current_candle["close"],
                "latest_bar_time": current_time,
                "ohlc": dict(current_candle),
                "ohlc_is_closed": False,
                "step_2_1a": {"active_level": "PMH", "level_price": 50000.0},
                "rejection": {"rejection_mode": "ON", "watch_side": "SHORT"},
                "step25": {"status": "READY"},
                "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4"},
                "step4": {
                    "status": "READY",
                    "next_step": "Step 5",
                    "state": {
                        "setup_direction": "SHORT",
                        "leg1_direction": "SHORT",
                        "leg1_status": "COMPLETE",
                        "leg1_state_locked": True,
                        "leg1_completed_at": leg1_time,
                        "leg1_reference_price": 50008.0,
                        "leg1_reference_candle_time": leg1_time,
                        "active_liquidity": {"name": "PMH", "price": 50000.0},
                        "candle_a": {"timestamp": "2026-05-07T13:41:00Z"},
                        "candle_b": {"timestamp": leg1_time},
                    },
                },
                "step5": {
                    "status": "READY",
                    "next_step": "Step 6",
                    "state": {
                        "setup_direction": "SHORT",
                        "leg2_status": "VALIDATED",
                        "step5_participation_validated": True,
                        "leg2_candidate_candle_time": leg2_time,
                        "leg2_candle": {"timestamp": leg2_time},
                    },
                },
                "step6": {
                    "status": "ENTRY_CONFIRMED",
                    "state": {
                        "setup_direction": "SHORT",
                        "entry_triggered": True,
                        "entry_candidate": dict(current_candle),
                        "entry_candle": dict(current_candle),
                    },
                },
            }

        entry_agent.run_once = fake_run_once
        try:
            status = entry_agent.build_entry_status("NQM6")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(status["current_step"], "Step 6")
        self.assertEqual(status["entry_status"], "CONFIRM")
        self.assertEqual(status["leg1_status"], "COMPLETE")
        self.assertEqual(status["leg2_status"], "VALIDATED")

    def test_active_liquidity_persistence_is_scoped_per_root_symbol(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        prices = {"NQ": 28392.0, "YM": 49730.0, "RTY": 2878.9}

        def fake_market_snapshot(root):
            price = prices[root]
            return {
                "source": "test",
                "symbol": f"{root}M6",
                "latest_price": price,
                "latest_bar_time": f"2026-05-06T15:0{len(str(price))}:00Z",
                "ohlc": {"open": price, "high": price, "low": price, "close": price},
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = fake_market_snapshot
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "levels": {
                                    "PML": {"price": 28392.0, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                            "YM": {
                                "symbol": "YM1!",
                                "levels": {
                                    "PML": {"price": 49730.0, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                            "RTY": {
                                "symbol": "RTY1!",
                                "levels": {
                                    "PML": {"price": 2878.9, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            nq = entry_agent.build_entry_status("NQM6")
            ym = entry_agent.build_entry_status("YMM6")
            rty = entry_agent.build_entry_status("RTYM6")

            self.assertEqual(nq["active_liquidity_name"], "PML")
            self.assertEqual(ym["active_liquidity_name"], "PML")
            self.assertEqual(rty["active_liquidity_name"], "PML")
            self.assertEqual(nq["active_liquidity_price"], 28392.0)
            self.assertEqual(ym["active_liquidity_price"], 49730.0)
            self.assertEqual(rty["active_liquidity_price"], 2878.9)
            self.assertNotEqual(nq["active_liquidity_price"], ym["active_liquidity_price"])
            self.assertNotEqual(ym["active_liquidity_price"], rty["active_liquidity_price"])

            persisted = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))
            self.assertEqual(
                persisted["last_interacted_liquidity_by_symbol"]["YM"]["price"],
                49730.0,
            )
            self.assertEqual(
                persisted["last_interacted_liquidity_by_symbol"]["RTY"]["price"],
                2878.9,
            )

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_one_symbols_last_interacted_liquidity_does_not_bleed_to_another_symbol(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        prices = {"RTY": 2878.9, "YM": 49800.0}

        def fake_market_snapshot(root):
            price = prices[root]
            return {
                "source": "test",
                "symbol": f"{root}M6",
                "latest_price": price,
                "latest_bar_time": f"2026-05-06T16:00:00Z",
                "ohlc": {"open": price, "high": price, "low": price, "close": price},
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = fake_market_snapshot
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "RTY": {
                                "symbol": "RTY1!",
                                "levels": {
                                    "PML": {"price": 2878.9, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                            "YM": {
                                "symbol": "YM1!",
                                "levels": {
                                    "PML": {"price": 49730.0, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            rty = entry_agent.build_entry_status("RTYM6")
            ym = entry_agent.build_entry_status("YMM6")

            self.assertEqual(rty["active_liquidity_name"], "PML")
            self.assertEqual(rty["active_liquidity_price"], 2878.9)
            self.assertIsNone(ym["active_liquidity_name"])
            self.assertIsNone(ym["active_liquidity_price"])

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_step2_state_resets_when_selected_liquidity_price_changes(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        state = entry_agent.initial_or_persisted_step_2_1a_state(
            {
                "step_2_1a": {
                    "active_level": "ONH",
                    "level_price": 27542.5,
                    "side": "upper",
                    "pre_activation_probe_boundary": {"active": False},
                    "events": [{"event": "old_state"}],
                }
            },
            "ONH",
            28008.5,
            "upper",
            0.25,
        )

        self.assertEqual(state["active_level"], "ONH")
        self.assertEqual(state["level_price"], 28008.5)
        self.assertEqual(state["events"], [])

    def test_load_tv_context_matches_contract_to_tv_symbol_key(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "YM1!": {
                                "symbol": "YM1!",
                                "levels": {
                                    "ONH": {"price": 50100, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                            "RTY1!": {
                                "symbol": "RTY1!",
                                "levels": {
                                    "ONH": {"price": 2830.2, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(entry_agent.load_tv_context("YMM6")["symbol"], "YM1!")
            self.assertEqual(entry_agent.load_tv_context("RTYM6")["symbol"], "RTY1!")
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.TV_CONTEXT_PATH = original_context_path

    def test_build_entry_status_selects_active_liquidity_for_contract_symbols(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        def fake_market_snapshot(root_symbol):
            prices = {"NQ": 28008.5, "YM": 50100.0, "RTY": 2830.2}
            price = prices[root_symbol]
            return {
                "source": "test",
                "symbol": f"{root_symbol}M6",
                "latest_price": price,
                "latest_bar_time": "2026-05-05T18:26:00Z",
                "ohlc": {"open": price, "high": price, "low": price, "close": price},
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = fake_market_snapshot
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ",
                                "levels": {
                                    "ONH": {"price": 28008.5, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                            "YM1!": {
                                "symbol": "YM1!",
                                "levels": {
                                    "ONH": {"price": 50100, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                            "RTY1!": {
                                "symbol": "RTY1!",
                                "levels": {
                                    "ONH": {"price": 2830.2, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            for requested_symbol in ("NQM6", "YMM6", "RTYM6"):
                status = entry_agent.build_entry_status(requested_symbol)
                self.assertEqual(status["symbol"], requested_symbol)
                self.assertEqual(status["current_step"], "Step 2")
                self.assertEqual(status["active_liquidity_name"], "ONH")
                self.assertIsNotNone(status["active_liquidity_price"])

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_stale_persisted_liquidity_price_must_match_current_root_table(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = lambda symbol: {
                "source": "test",
                "symbol": "NQM6",
                "latest_price": 28480.0,
                "latest_bar_time": "2026-05-05T18:26:00Z",
                "ohlc": {"open": 28479.0, "high": 28481.0, "low": 28478.0, "close": 28480.0},
            }
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "levels": {
                                    "PML": {"price": 28392.0, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            entry_agent.STATE_PATH.write_text(
                json.dumps(
                    {
                        "state_by_symbol": {
                            "NQ": {
                                "normalized_symbol": "NQ",
                                "last_interacted_liquidity": {
                                    "name": "PML",
                                    "price": 2878.9,
                                    "side": "lower",
                                },
                            }
                        },
                        "last_interacted_liquidity_by_symbol": {
                            "NQ": {
                                "name": "PML",
                                "price": 2878.9,
                                "side": "lower",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            status = entry_agent.build_entry_status("NQM6")

            self.assertIsNone(status["active_liquidity_name"])
            self.assertIsNone(status["active_liquidity_price"])
            state = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))
            self.assertNotEqual(
                ((state.get("last_interacted_liquidity_by_symbol") or {}).get("NQ") or {}).get("price"),
                2878.9,
            )

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_leg1_lock_invalidation_and_consumed_liquidity_guard_are_monotonic(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        candle_a = {"open": 100.8, "high": 101.0, "low": 99.8, "close": 100.5, "timestamp": "2026-05-05T18:25:00Z"}
        candle_b = {"open": 100.2, "high": 100.7, "low": 99.5, "close": 100.1, "timestamp": "2026-05-05T18:26:00Z"}
        invalidating_candle = {"open": 99.7, "high": 100.3, "low": 98.8, "close": 99.0, "timestamp": "2026-05-05T18:27:00Z"}
        same_invalidating_snapshot = {
            "latest_price": 99.0,
            "latest_bar_time": invalidating_candle["timestamp"],
            "ohlc": invalidating_candle,
            "liquidity": {
                "tick_size": 0.25,
                "nearest_level_above": {"name": "PMH", "price": 110.0},
                "nearest_level_below": None,
            },
        }
        step25 = {
            "status": "READY",
            "next_step": "Step 3",
            "state": {
                "system_state": "REJECTION MODE ON",
                "trade_mode": "ON",
                "rejection_mode": "ON",
                "interaction_state": "ACTIVE",
                "initial_candle_a": candle_a,
                "step25_pathway_selection_complete": True,
                "controlling_mode": "Normal Rejection Mode",
            },
            "events": [],
        }
        step3 = {
            "status": "ALLOW_STEP_4",
            "next_step": "Step 4",
            "state": {
                "step3_allows_structure": True,
                "interaction_state": "ACTIVE",
                "active_liquidity": {"name": "PML", "price": 100.0},
                "tick_size": 0.25,
            },
            "events": [],
        }
        snapshot = {
            "latest_price": 100.1,
            "latest_bar_time": candle_b["timestamp"],
            "ohlc": candle_b,
            "liquidity": {
                "tick_size": 0.25,
                "nearest_level_above": {"name": "PMH", "price": 110.0},
                "nearest_level_below": None,
            },
            "atr": {"atr_1m_14": 1.0},
            "tv_context": {"daily_atr14": 40.0},
        }
        rejection = {"rejection_mode": "ON", "watch_side": "LONG"}

        leg1 = entry_agent.evaluate_live_step4(snapshot, rejection, step25, step3, {})
        repeated_leg1 = entry_agent.evaluate_live_step4(
            snapshot,
            rejection,
            step25,
            step3,
            {"step4": leg1},
        )
        same_candle_step5 = entry_agent.evaluate_live_step5(snapshot, repeated_leg1, {"step4": repeated_leg1})
        invalidated = entry_agent.evaluate_live_step5(
            same_invalidating_snapshot,
            repeated_leg1,
            {"step4": repeated_leg1},
        )
        repeated_step4_after_invalidation = entry_agent.evaluate_live_step4(
            same_invalidating_snapshot,
            rejection,
            step25,
            step3,
            {"step4": invalidated, "consumed_liquidity_levels": invalidated["state"]["consumed_liquidity_levels"]},
        )

        self.assertEqual(leg1["status"], "READY")
        self.assertTrue(leg1["state"]["leg1_state_locked"])
        self.assertEqual(leg1["state"]["leg1_completed_at"], candle_b["timestamp"])
        self.assertEqual(repeated_leg1["status"], "READY")
        self.assertEqual(repeated_leg1["state"]["leg1_completed_at"], candle_b["timestamp"])
        self.assertEqual(same_candle_step5["status"], "WAIT")
        self.assertTrue(same_candle_step5["state"]["leg2_same_sequence_rejected"])
        self.assertEqual(invalidated["status"], "WAIT")
        self.assertFalse(invalidated["state"]["leg1_state_locked"])
        self.assertEqual(invalidated["state"]["invalidated_liquidity"]["name"], "PML")
        self.assertEqual(invalidated["state"]["invalidation_source_candle_time"], invalidating_candle["timestamp"])
        self.assertEqual(repeated_step4_after_invalidation["status"], "WAIT")

    def test_live_step4_waits_for_participation_after_setup_candle(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        setup_candle = {
            "open": 100.0,
            "high": 101.0,
            "low": 99.5,
            "close": 100.5,
            "timestamp": "2026-05-07T13:30:00Z",
        }
        participation_candle = {
            "open": 100.4,
            "high": 100.8,
            "low": 99.7,
            "close": 100.2,
            "timestamp": "2026-05-07T13:31:00Z",
        }
        step25 = {
            "status": "READY",
            "next_step": "Step 3",
            "state": {
                "system_state": "REJECTION MODE ON",
                "trade_mode": "ON",
                "rejection_mode": "ON",
                "interaction_state": "ACTIVE",
                "initial_candle_a": setup_candle,
                "step25_pathway_selection_complete": True,
                "controlling_mode": "Normal Rejection Mode",
            },
            "events": [],
        }
        step3 = {
            "status": "ALLOW_STEP_4",
            "next_step": "Step 4",
            "state": {
                "step3_allows_structure": True,
                "interaction_state": "ACTIVE",
                "active_liquidity": {"name": "PMH", "price": 100.0},
                "tick_size": 0.25,
            },
            "events": [],
        }
        base_snapshot = {
            "latest_price": 100.5,
            "latest_bar_time": setup_candle["timestamp"],
            "ohlc": setup_candle,
            "ohlc_is_closed": True,
            "liquidity": {
                "tick_size": 0.25,
                "nearest_level_above": {"name": "ONH", "price": 110.0},
                "nearest_level_below": {"name": "PML", "price": 90.0},
            },
            "atr": {"atr_1m_14": 1.0},
            "tv_context": {"daily_atr14": 40.0},
        }
        rejection = {"rejection_mode": "ON", "watch_side": "SHORT"}

        setup_result = entry_agent.evaluate_live_step4(base_snapshot, rejection, step25, step3, {})
        self.assertEqual(setup_result["status"], "WAIT")
        self.assertEqual(setup_result["next_step"], "Step 4")
        self.assertNotEqual(setup_result["state"].get("leg1_status"), "COMPLETE")

        participation_snapshot = {
            **base_snapshot,
            "latest_price": participation_candle["close"],
            "latest_bar_time": participation_candle["timestamp"],
            "ohlc": participation_candle,
        }
        participation_result = entry_agent.evaluate_live_step4(
            participation_snapshot,
            rejection,
            step25,
            step3,
            {"step4": setup_result},
        )
        self.assertEqual(participation_result["status"], "READY")
        self.assertEqual(participation_result["next_step"], "Step 5")
        self.assertEqual(participation_result["state"]["leg1_status"], "COMPLETE")
        self.assertEqual(participation_result["state"]["leg1_completed_at"], participation_candle["timestamp"])

    def test_nq_lower_liquidity_reclaim_confirms_shared_leg1_and_keeps_entry_waiting(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        step2_candle = {
            "open": 100.4,
            "high": 100.5,
            "low": 99.4,
            "close": 99.7,
            "timestamp": "2026-05-18T13:44:00Z",
        }
        participation_candle = {
            "open": 99.65,
            "high": 100.7,
            "low": 99.1,
            "close": 100.25,
            "timestamp": "2026-05-18T13:45:00Z",
        }
        step25 = {
            "status": "READY",
            "next_step": "Step 3",
            "state": {
                "system_state": "REJECTION MODE ON",
                "trade_mode": "ON",
                "rejection_mode": "ON",
                "interaction_state": "ACTIVE",
                "initial_candle_a": step2_candle,
                "reclaim_candle_a": participation_candle,
                "step25_pathway_selection_complete": True,
                "controlling_mode": "S/R",
                "candidate_modes": ["S/R"],
                "pathway_activation_type": "close",
                "structure_side_requirement": "ABOVE_LEVEL",
                "pathway_level": 100.0,
                "continuation_step2_activated": True,
            },
            "events": [],
        }
        step3 = {
            "status": "ALLOW_STEP_4",
            "next_step": "Step 4",
            "state": {
                "step3_allows_structure": True,
                "interaction_state": "ACTIVE",
                "active_liquidity": {"name": "PML", "price": 100.0, "side": "lower"},
                "tick_size": 0.25,
            },
            "events": [],
        }
        rejection = {
            "rejection_mode": "ON",
            "watch_side": "LONG",
            "trigger_level": "PML",
            "trigger_price": 100.0,
        }

        def snapshot(candle):
            return {
                "requested_symbol": "NQ",
                "normalized_symbol": "NQ",
                "latest_price": candle["close"],
                "latest_bar_time": candle["timestamp"],
                "ohlc": candle,
                "ohlc_is_closed": True,
                "liquidity": {
                    "tick_size": 0.25,
                    "nearest_level_above": {"name": "PMH", "price": 110.0},
                    "nearest_level_below": {"name": "ONL", "price": 90.0},
                },
                "atr": {"atr_1m_14": 4.0},
                "tv_context": {"daily_atr14": 40.0},
            }

        step2_hold = entry_agent.evaluate_live_step4(snapshot(step2_candle), rejection, step25, step3, {})
        self.assertEqual(step2_hold["status"], "WAIT")
        self.assertNotEqual(step2_hold["state"].get("leg1_status"), "COMPLETE")

        leg1 = entry_agent.evaluate_live_step4(
            snapshot(participation_candle),
            rejection,
            step25,
            step3,
            {"step4": step2_hold},
        )
        self.assertEqual(leg1["status"], "READY")
        self.assertEqual(leg1["state"]["setup_direction"], "LONG")
        self.assertEqual(leg1["state"]["leg1_status"], "COMPLETE")
        self.assertTrue(leg1["state"]["leg1_state_locked"])
        self.assertEqual(leg1["state"]["leg1_completed_at"], participation_candle["timestamp"])

        public_snapshot = {
            **snapshot(participation_candle),
            "step_2_1a": {
                "step_2_activated": True,
                "active_level": "PML",
                "level_price": 100.0,
                "side": "lower",
                "candle_a": step2_candle,
            },
            "rejection": rejection,
            "step25": step25,
            "step3": step3,
            "step4": leg1,
            "step5": {"step": "Step 5", "status": "WAIT", "state": {}, "next_step": "Step 5"},
            "step6": {"step": "Step 6", "status": "WAIT", "state": {}, "next_step": "Step 5"},
        }
        original_run_once = entry_agent.run_once
        entry_agent.run_once = lambda _symbol, persist=True: public_snapshot
        try:
            status = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(status["current_step"], "Step 4")
        self.assertEqual(status["current_step_label"], "Shared Leg 1 Confirmed")
        self.assertEqual(status["current_step_status"], "CONFIRMED")
        self.assertEqual(status["leg1_status"], "COMPLETE")
        self.assertEqual(status["leg1_state"], "COMPLETE")
        self.assertTrue(status["leg1_locked"])
        self.assertTrue(status["leg1_state_locked"])
        self.assertEqual(status["leg1_confirmed_at"], participation_candle["timestamp"])
        self.assertEqual(status["leg1_completed_at"], participation_candle["timestamp"])
        self.assertEqual(status["rejection_pathway_status"], "controlling")
        self.assertEqual(status["rejection_side"]["pathway_status"], "controlling")
        self.assertEqual(status["rejection_side"]["setup_direction"], "LONG")
        self.assertEqual(status["continuation_pathway_status"], "active")
        self.assertEqual(status["continuation_side"]["pathway_status"], "active")
        self.assertEqual(status["continuation_side"]["continuation_type"], "S/R")
        self.assertEqual(status["continuation_side"]["setup_direction"], "SHORT")
        self.assertEqual(status["leg2_status"], "WAIT")
        self.assertEqual(status["entry_status"], "WAIT")

    def test_step2_locked_owner_persists_stacked_low_rejection_when_tv_active_stack_clears(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot
        original_recent_closed_bars = entry_agent.recent_closed_bars
        self.addCleanup(setattr, entry_agent, "STATE_PATH", original_state_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_PATH", original_context_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_BY_SYMBOL_PATH", original_by_symbol_path)
        self.addCleanup(setattr, entry_agent, "RITHMIC_ATR_SNAPSHOT_PATH", original_atr_path)
        self.addCleanup(setattr, entry_agent, "get_latest_market_snapshot", original_market_snapshot)
        self.addCleanup(setattr, entry_agent, "recent_closed_bars", original_recent_closed_bars)

        step2_candle = {
            "open": 50095.0,
            "high": 50102.0,
            "low": 49790.0,
            "close": 50010.0,
            "timestamp": "2026-05-19T13:20:00Z",
        }
        confirm_candle = {
            "open": 50012.0,
            "high": 50020.0,
            "low": 49770.0,
            "close": 49780.0,
            "timestamp": "2026-05-19T13:21:00Z",
        }
        participation_candle = {
            "open": 50104.0,
            "high": 50125.0,
            "low": 50030.0,
            "close": 50055.0,
            "timestamp": "2026-05-19T13:22:00Z",
        }
        candles = [step2_candle, confirm_candle, participation_candle]

        def context_payload(active):
            status = "ACTIVE" if active else "INACTIVE"
            return {
                "symbol": "NQ1!",
                "normalized_symbol": "NQ",
                "locked": True,
                "levels": {
                    "PML": {"price": 50082.0, "status": status, "stack_group": "LOW 1"},
                    "LL": {"price": 50018.0, "status": status, "stack_group": "LOW 1"},
                    "ONL": {"price": 49984.0, "status": status, "stack_group": "LOW 1"},
                    "YL": {"price": 49806.0, "status": status, "stack_group": "LOW 1"},
                    "PMH": {"price": 50600.0, "status": "ACTIVE", "stack_group": "NONE"},
                },
                "atr_1m_14": 80.0,
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "atr.json"
            cursor = {"index": 0}

            def market_snapshot(_symbol):
                candle = candles[cursor["index"]]
                return {
                    "source": "test",
                    "symbol": "NQM6",
                    "latest_price": candle["close"],
                    "latest_bar_time": candle["timestamp"],
                    "ohlc_is_closed": True,
                    "ohlc": candle,
                }

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol, limit=2: candles[: cursor["index"] + 1][-limit:]
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps({"symbols": {"NQ": context_payload(True)}}),
                encoding="utf-8",
            )

            step2_status = entry_agent.build_entry_status("NQ")

            cursor["index"] = 1
            step2_status = entry_agent.build_entry_status("NQ")

            cursor["index"] = 2
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps({"symbols": {"NQ": context_payload(False)}}),
                encoding="utf-8",
            )
            leg1_status = entry_agent.build_entry_status("NQ")
            persisted = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))["state_by_symbol"]["NQ"]

        self.assertEqual(step2_status["current_step"], "Step 2")
        self.assertEqual(step2_status["current_step_status"], "CONFIRMED")
        self.assertEqual(step2_status["active_liquidity_name"], "PML/LL/ONL/YL Liquidity")
        self.assertEqual(step2_status["active_liquidity_price"], 50082.0)
        self.assertEqual(step2_status["active_liquidity_group"]["components"], ["PML", "LL", "ONL", "YL"])
        self.assertEqual(step2_status["active_liquidity_group"]["display_name"], "PML/LL/ONL/YL Liquidity")
        self.assertEqual(step2_status["active_liquidity_group"]["close_boundary"], 50082.0)
        self.assertEqual(step2_status["active_liquidity_group"]["extreme_boundary"], 49806.0)
        self.assertEqual(step2_status["liquidity_group"], "LOW 1")
        self.assertEqual(step2_status["setup_direction"], "LONG")
        self.assertEqual(step2_status["rejection_pathway_status"], "controlling")

        self.assertEqual(leg1_status["active_liquidity_name"], "PML/LL/ONL/YL Liquidity")
        self.assertEqual(leg1_status["active_liquidity_price"], 50082.0)
        self.assertEqual(leg1_status["active_liquidity_group"]["components"], ["PML", "LL", "ONL", "YL"])
        self.assertEqual(leg1_status["active_liquidity_group"]["display_name"], "PML/LL/ONL/YL Liquidity")
        self.assertEqual(leg1_status["active_liquidity_group"]["close_boundary"], 50082.0)
        self.assertEqual(leg1_status["active_liquidity_group"]["extreme_boundary"], 49806.0)
        self.assertEqual(leg1_status["liquidity_group"], "LOW 1")
        self.assertEqual(leg1_status["current_pathway_control"], "continuation")
        self.assertEqual(leg1_status["rejection_pathway_status"], "frozen")
        self.assertEqual(leg1_status["continuation_pathway_status"], "controlling")
        self.assertEqual(leg1_status["continuation_type"], "S/R")
        self.assertIsNotNone(leg1_status["active_liquidity_name"])
        self.assertEqual(persisted["step4"]["next_step"], "Step 4")
        self.assertEqual(persisted["step4"]["state"]["active_liquidity"]["name"], "YL")
        self.assertEqual(persisted["step4"]["state"]["active_liquidity"]["price"], 49806.0)
        self.assertEqual(persisted["step2_locked_owner"]["pathway"], "rejection")
        self.assertEqual(persisted["step2_locked_owner"]["liquidity_group"], "LOW 1")
        self.assertEqual(persisted["step2_locked_owner"]["setup_direction"], "LONG")
        self.assertEqual(persisted["step2_locked_owner"]["stack_components"], ["PML", "LL", "ONL", "YL"])
        self.assertEqual(persisted["step2_locked_owner"]["extreme_boundary"], 49806.0)

    def test_nq_2026_05_19_replay_step2_to_step6_contract(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        originals = {
            "STATE_PATH": entry_agent.STATE_PATH,
            "TV_CONTEXT_PATH": entry_agent.TV_CONTEXT_PATH,
            "TV_CONTEXT_BY_SYMBOL_PATH": entry_agent.TV_CONTEXT_BY_SYMBOL_PATH,
            "RITHMIC_ATR_SNAPSHOT_PATH": entry_agent.RITHMIC_ATR_SNAPSHOT_PATH,
            "PERSISTENCE_STATE_PATH": entry_agent.PERSISTENCE_STATE_PATH,
            "EXECUTOR_STATE_PATH": entry_agent.EXECUTOR_STATE_PATH,
            "get_latest_market_snapshot": entry_agent.get_latest_market_snapshot,
            "recent_closed_bars": entry_agent.recent_closed_bars,
        }
        for name, value in originals.items():
            self.addCleanup(setattr, entry_agent, name, value)

        candle_rows = [
            ("2026-05-19T13:30:00Z", 28932.75, 28943.5, 28927.75, 28936.75),
            ("2026-05-19T13:31:00Z", 28914.25, 28960.0, 28901.25, 28938.5),
            ("2026-05-19T13:32:00Z", 28940.75, 28981.75, 28930.25, 28969.75),
            ("2026-05-19T13:33:00Z", 28970.25, 28999.0, 28964.5, 28977.25),
            ("2026-05-19T13:34:00Z", 28977.0, 28984.0, 28960.0, 28977.0),
            ("2026-05-19T13:35:00Z", 28980.0, 28986.0, 28970.0, 28981.0),
            ("2026-05-19T13:36:00Z", 28981.25, 29044.75, 28981.25, 29043.5),
            ("2026-05-19T13:37:00Z", 29042.5, 29068.0, 29041.0, 29052.5),
            ("2026-05-19T13:38:00Z", 29052.0, 29056.0, 28980.0, 28990.0),
            ("2026-05-19T13:39:00Z", 28990.0, 29005.0, 28950.0, 28970.0),
            ("2026-05-19T13:40:00Z", 28970.0, 28980.0, 28945.0, 28960.0),
            ("2026-05-19T13:41:00Z", 28960.0, 28970.0, 28945.0, 28953.0),
            ("2026-05-19T13:42:00Z", 28953.0, 28965.5, 28928.0, 28929.25),
            ("2026-05-19T13:43:00Z", 28929.0, 28952.25, 28919.25, 28944.5),
            ("2026-05-19T13:44:00Z", 28944.5, 28951.25, 28903.75, 28913.25),
            ("2026-05-19T13:45:00Z", 28913.5, 28940.0, 28903.5, 28922.25),
        ]
        candles = [
            {"timestamp": ts, "open": open_, "high": high, "low": low, "close": close}
            for ts, open_, high, low, close in candle_rows
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "atr.json"
            entry_agent.PERSISTENCE_STATE_PATH = temp_path / "persistence_state.json"
            entry_agent.EXECUTOR_STATE_PATH = temp_path / "executor_state.json"
            entry_agent.PERSISTENCE_STATE_PATH.write_text(json.dumps({"trades": {}}), encoding="utf-8")
            entry_agent.EXECUTOR_STATE_PATH.write_text(json.dumps({"orders": {}}), encoding="utf-8")
            cursor = {"index": 0}

            def market_snapshot(_symbol):
                candle = candles[cursor["index"]]
                return {
                    "source": "test",
                    "symbol": "NQM6",
                    "latest_price": candle["close"],
                    "latest_bar_time": candle["timestamp"],
                    "ohlc_is_closed": True,
                    "ohlc": candle,
                }

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol, limit=2: candles[: cursor["index"] + 1][-limit:]
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "normalized_symbol": "NQ",
                                "locked": True,
                                "atr_1m_14": 40.0,
                                "daily_atr14": 500.0,
                                "levels": {
                                    "PMH": {"price": 28937.75, "status": "ACTIVE", "stack_group": "NONE"},
                                    "PML": {"price": 28700.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "ONH": {"price": 29150.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "ONL": {"price": 28600.0, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            observed = {}
            for index, candle in enumerate(candles):
                cursor["index"] = index
                status = entry_agent.build_entry_status("NQ")
                persisted = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))["state_by_symbol"]["NQ"]
                observed[candle["timestamp"]] = (status, persisted)

        status, persisted = observed["2026-05-19T13:30:00Z"]
        self.assertEqual(status["active_liquidity_name"], "PMH")
        self.assertFalse(status["rejection_mode_entered"])
        self.assertFalse(persisted["step_2_1a"]["step_2_activated"])
        self.assertTrue(persisted["step_2_1a"]["pre_activation_probe_boundary"]["active"])
        self.assertEqual(persisted["step_2_1a"]["pre_activation_probe_boundary"]["boundary_price"], 28943.5)

        status, persisted = observed["2026-05-19T13:31:00Z"]
        self.assertEqual(status["active_liquidity_name"], "PMH")
        self.assertEqual(status["current_step_status"], "WAIT")
        self.assertFalse(status["rejection_mode_entered"])
        self.assertFalse(persisted["step_2_1a"]["step_2_activated"])
        self.assertTrue(persisted["step_2_1a"]["pre_activation_probe_boundary"]["active"])
        self.assertEqual(persisted["step_2_1a"]["pre_activation_probe_boundary"]["boundary_price"], 28960.0)

        status, persisted = observed["2026-05-19T13:32:00Z"]
        self.assertEqual(status["current_step_status"], "CONFIRMED")
        self.assertTrue(status["rejection_mode_entered"])
        self.assertEqual(status["setup_direction"], "SHORT")
        self.assertEqual(status["active_liquidity_name"], "PMH")
        self.assertEqual(persisted["step2_locked_owner"]["active_liquidity_name"], "PMH")

        status, persisted = observed["2026-05-19T13:33:00Z"]
        self.assertEqual(persisted["step4"]["status"], "READY")
        self.assertEqual(persisted["step4"]["state"]["leg1_status"], "COMPLETE")
        self.assertEqual(persisted["step4"]["state"]["leg1_completed_at"], "2026-05-19T13:33:00Z")

        _status, persisted = observed["2026-05-19T13:35:00Z"]
        self.assertEqual(persisted["step5"]["state"]["leg2_status"], "CONFIRMED")
        self.assertEqual(persisted["step5"]["state"]["leg2_candle_a_time"], "2026-05-19T13:35:00Z")

        _status, persisted = observed["2026-05-19T13:36:00Z"]
        self.assertEqual(persisted["step5"]["state"]["leg2_status"], "VALIDATED")
        self.assertEqual(persisted["step6"]["state"]["current_sc"]["timestamp"], "2026-05-19T13:36:00Z")
        self.assertEqual(persisted["step6"]["state"]["phase1_candle_count"], 1)
        self.assertEqual(persisted["step6"]["status"], "WAIT")

        status, persisted = observed["2026-05-19T13:37:00Z"]
        self.assertEqual(persisted["step6"]["state"]["phase1_candle_count"], 2)
        self.assertEqual(persisted["step6"]["state"]["extended_retrace_step6_candle_time"], "2026-05-19T13:37:00Z")
        self.assertFalse(status["extended_retrace_pending"])
        self.assertTrue(status["extended_retrace_blocked_immediate_entry"])
        self.assertEqual(status["entry_status"], "CONFIRM")
        self.assertEqual(persisted["step6"]["status"], "ENTRY_CONFIRMED")
        self.assertEqual(persisted["step6"]["entry_type"], "Extended Retrace Entry")
        self.assertTrue(persisted["step6"]["state"]["extended_retrace_intrabar_fill"])

        status, persisted = observed["2026-05-19T13:42:00Z"]
        self.assertEqual(status["active_liquidity_name"], "PMH")
        self.assertEqual(status["sr_rs_context"], "R/S")
        self.assertEqual(status["current_pathway_control"], "continuation")
        self.assertEqual(status["setup_direction"], "LONG")
        self.assertEqual(persisted["step25"]["state"]["reclaim_candle_a"]["timestamp"], "2026-05-19T13:42:00Z")

        _status, persisted = observed["2026-05-19T13:43:00Z"]
        self.assertEqual(persisted["step4"]["status"], "READY")
        self.assertEqual(persisted["step4"]["state"]["setup_direction"], "LONG")
        self.assertEqual(persisted["step4"]["state"]["leg1_completed_at"], "2026-05-19T13:43:00Z")
        self.assertEqual(persisted["step4"]["state"]["candle_a"]["timestamp"], "2026-05-19T13:42:00Z")

        _status, persisted = observed["2026-05-19T13:44:00Z"]
        self.assertEqual(persisted["step5"]["state"]["leg2_status"], "CONFIRMED")
        self.assertEqual(persisted["step5"]["state"]["leg2_candle_a_time"], "2026-05-19T13:44:00Z")

        _status, persisted = observed["2026-05-19T13:45:00Z"]
        self.assertEqual(persisted["step5"]["state"]["leg2_status"], "VALIDATED")
        self.assertEqual(persisted["step6"]["status"], "ENTRY_CONFIRMED")

    def test_ym_2026_06_05_step4_post_step2_live_path_diagnostics(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
            import step4_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        originals = {
            "STATE_PATH": entry_agent.STATE_PATH,
            "TV_CONTEXT_PATH": entry_agent.TV_CONTEXT_PATH,
            "TV_CONTEXT_BY_SYMBOL_PATH": entry_agent.TV_CONTEXT_BY_SYMBOL_PATH,
            "RITHMIC_ATR_SNAPSHOT_PATH": entry_agent.RITHMIC_ATR_SNAPSHOT_PATH,
            "PERSISTENCE_STATE_PATH": entry_agent.PERSISTENCE_STATE_PATH,
            "EXECUTOR_STATE_PATH": entry_agent.EXECUTOR_STATE_PATH,
            "get_latest_market_snapshot": entry_agent.get_latest_market_snapshot,
            "recent_closed_bars": entry_agent.recent_closed_bars,
        }
        for name, value in originals.items():
            self.addCleanup(setattr, entry_agent, name, value)

        candle_rows = [
            ("2026-06-05T13:32:00Z", 51631.0, 51666.0, 51613.0, 51647.0),
            ("2026-06-05T13:33:00Z", 51648.0, 51686.0, 51629.0, 51651.0),
            ("2026-06-05T13:34:00Z", 51650.0, 51671.0, 51612.0, 51646.0),
            ("2026-06-05T13:35:00Z", 51645.0, 51651.0, 51620.0, 51622.0),
            ("2026-06-05T13:36:00Z", 51624.0, 51635.0, 51588.0, 51590.0),
            ("2026-06-05T13:37:00Z", 51589.0, 51626.0, 51581.0, 51585.0),
            ("2026-06-05T13:38:00Z", 51583.0, 51592.0, 51562.0, 51576.0),
            ("2026-06-05T13:39:00Z", 51572.0, 51591.0, 51538.0, 51540.0),
            ("2026-06-05T13:40:00Z", 51540.0, 51567.0, 51524.0, 51563.0),
            ("2026-06-05T13:41:00Z", 51563.0, 51570.0, 51533.0, 51541.0),
            ("2026-06-05T13:42:00Z", 51543.0, 51549.0, 51499.0, 51505.0),
            ("2026-06-05T13:43:00Z", 51507.0, 51516.0, 51479.0, 51481.0),
        ]
        candles = [
            {"timestamp": ts, "open": open_, "high": high, "low": low, "close": close}
            for ts, open_, high, low, close in candle_rows
        ]
        levels = {
            "PMH": {"price": 51849.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
            "LH": {"price": 51849.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
            "ONH": {"price": 51849.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
            "YH": {"price": 51752.0, "status": "ACTIVE", "stack_group": "NONE"},
            "LL": {"price": 51639.0, "status": "ACTIVE", "stack_group": "LOW 1"},
            "PML": {"price": 51632.0, "status": "ACTIVE", "stack_group": "LOW 1"},
            "ONL": {"price": 51585.0, "status": "ACTIVE", "stack_group": "LOW 1"},
            "YL": {"price": 51256.0, "status": "ACTIVE", "stack_group": "NONE"},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "atr.json"
            entry_agent.PERSISTENCE_STATE_PATH = temp_path / "persistence_state.json"
            entry_agent.EXECUTOR_STATE_PATH = temp_path / "executor_state.json"
            entry_agent.PERSISTENCE_STATE_PATH.write_text(json.dumps({"trades": {}}), encoding="utf-8")
            entry_agent.EXECUTOR_STATE_PATH.write_text(json.dumps({"orders": {}}), encoding="utf-8")
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH.write_text(
                json.dumps({"symbols": {"YM": {"atr_value": 38.92857142857143}, "YMM6": {"atr_value": 38.92857142857143}}}),
                encoding="utf-8",
            )
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "YM": {
                                "symbol": "YM1!",
                                "normalized_symbol": "YM",
                                "locked": True,
                                "atr_1m_14": 38.92857142857143,
                                "daily_atr14": 600.0,
                                "levels": levels,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            cursor = {"index": 0}

            def market_snapshot(_symbol):
                candle = candles[cursor["index"]]
                return {
                    "source": "test",
                    "symbol": "YMM6",
                    "latest_price": candle["close"],
                    "latest_bar_time": candle["timestamp"],
                    "ohlc_is_closed": True,
                    "ohlc": candle,
                }

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol, limit=120: candles[: cursor["index"] + 1][-limit:]

            diagnostics = []
            observed = {}
            diagnostic_times = {
                "2026-06-05T13:39:00Z",
                "2026-06-05T13:40:00Z",
                "2026-06-05T13:41:00Z",
            }

            def append_diagnostic(status, persisted, candle, refresh_number):
                step4 = persisted.get("step4") or {}
                step4_state = step4.get("state") if isinstance(step4.get("state"), dict) else {}
                candle_a = step4_state.get("candle_a") if isinstance(step4_state.get("candle_a"), dict) else None
                close_candidate = (
                    step4_engine.close_based_participation(candle_a, candle, step4_state.get("setup_direction"))
                    if isinstance(candle_a, dict)
                    else None
                )
                wick_candidate = (
                    step4_engine.wick_participation(candle, step4_state.get("setup_direction"))
                    if isinstance(candle_a, dict)
                    else None
                )
                diagnostics.append(
                    {
                        "timestamp": candle["timestamp"],
                        "same_closed_candle_refresh": refresh_number,
                        "ohlc": {key: candle[key] for key in ("open", "high", "low", "close")},
                        "public_step": status.get("current_step"),
                        "public_wait_reason": status.get("wait_reason"),
                        "step2_direction": ((persisted.get("step2_locked_owner") or {}).get("setup_direction")),
                        "step2_setup": (persisted.get("rejection") or {}).get("watch_side"),
                        "locked_owner": {
                            key: (persisted.get("step2_locked_owner") or {}).get(key)
                            for key in ("active_liquidity_name", "active_liquidity_price", "liquidity_group")
                        },
                        "locked_boundary_extreme": {
                            "close_boundary": (persisted.get("step2_locked_owner") or {}).get("close_boundary"),
                            "extreme_boundary": (persisted.get("step2_locked_owner") or {}).get("extreme_boundary"),
                        },
                        "step4_status": step4.get("status"),
                        "step4_next_step": step4.get("next_step"),
                        "step4_reason": step4.get("reason"),
                        "step4_state_transition_reason": step4_state.get("state_transition_reason"),
                        "candle_a_timestamp": (candle_a or {}).get("timestamp") if isinstance(candle_a, dict) else None,
                        "candle_b_timestamp": (
                            (step4_state.get("candle_b") or {}).get("timestamp")
                            if isinstance(step4_state.get("candle_b"), dict)
                            else None
                        ),
                        "leg1_candidate": bool(close_candidate or wick_candidate) if close_candidate is not None else None,
                        "close_participation": close_candidate,
                        "wick_participation": wick_candidate,
                        "leg1_status": step4_state.get("leg1_status"),
                        "leg1_state_locked": step4_state.get("leg1_state_locked"),
                        "leg1_completed_at": step4_state.get("leg1_completed_at"),
                        "leg1_window_candle_index": step4_state.get("leg1_window_candle_index"),
                        "leg1_window_remaining": step4_state.get("leg1_window_remaining"),
                        "rejection_reason": step4_state.get("step4_block_reason") or step4.get("reason"),
                    }
                )

            for index, candle in enumerate(candles):
                cursor["index"] = index
                status = entry_agent.build_entry_status("YM")
                persisted = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))["state_by_symbol"]["YM"]
                observed[candle["timestamp"]] = (status, persisted)
                if candle["timestamp"] in diagnostic_times:
                    append_diagnostic(status, persisted, candle, 1)
                if candle["timestamp"] == "2026-06-05T13:39:00Z":
                    status = entry_agent.build_entry_status("YM")
                    persisted = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))["state_by_symbol"]["YM"]
                    observed[candle["timestamp"]] = (status, persisted)
                    append_diagnostic(status, persisted, candle, 2)

        print("\nYM 2026-06-05 live Step 4 diagnostics:")
        print(json.dumps(diagnostics, indent=2))
        self.assertEqual(observed["2026-06-05T13:38:00Z"][1]["step2_locked_owner"]["setup_direction"], "LONG")
        self.assertEqual(len(diagnostics), 4)
        first_1339, duplicate_1339, first_1340, first_1341 = diagnostics
        self.assertEqual(first_1339["timestamp"], "2026-06-05T13:39:00Z")
        self.assertEqual(first_1339["step4_status"], "WAIT")
        self.assertEqual(first_1339["candle_a_timestamp"], "2026-06-05T13:39:00Z")
        self.assertIsNone(first_1339["candle_b_timestamp"])

        self.assertEqual(duplicate_1339["timestamp"], "2026-06-05T13:39:00Z")
        self.assertEqual(duplicate_1339["same_closed_candle_refresh"], 2)
        self.assertEqual(duplicate_1339["step4_status"], "WAIT")
        self.assertEqual(duplicate_1339["candle_a_timestamp"], "2026-06-05T13:39:00Z")
        self.assertIsNone(duplicate_1339["candle_b_timestamp"])
        self.assertIsNone(duplicate_1339["leg1_status"])
        self.assertIsNone(duplicate_1339["leg1_state_locked"])
        self.assertIsNone(duplicate_1339["leg1_completed_at"])

        self.assertEqual(first_1340["timestamp"], "2026-06-05T13:40:00Z")
        self.assertEqual(first_1340["step4_status"], "READY")
        self.assertEqual(first_1340["candle_a_timestamp"], "2026-06-05T13:39:00Z")
        self.assertEqual(first_1340["candle_b_timestamp"], "2026-06-05T13:40:00Z")
        self.assertTrue(first_1340["leg1_candidate"])
        self.assertEqual(first_1340["leg1_status"], "COMPLETE")
        self.assertIs(first_1340["leg1_state_locked"], True)
        self.assertEqual(first_1340["leg1_completed_at"], "2026-06-05T13:40:00Z")
        self.assertEqual(first_1341["step4_reason"], "Leg 1 locked; Step 4 not re-evaluated on status refresh.")

    def test_rs_continuation_projection_has_one_authoritative_long_direction(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        original_state_path = entry_agent.STATE_PATH
        self.addCleanup(setattr, entry_agent, "run_once", original_run_once)
        self.addCleanup(setattr, entry_agent, "STATE_PATH", original_state_path)

        active_liquidity = {"name": "PMH", "display_name": "PMH", "price": 28937.75, "side": "upper"}
        reclaim = {"timestamp": "2026-05-19T13:42:00Z", "open": 28953.0, "high": 28965.5, "low": 28928.0, "close": 28929.25}
        leg1 = {"timestamp": "2026-05-19T13:43:00Z", "open": 28929.0, "high": 28952.25, "low": 28919.25, "close": 28944.5}
        snapshot = {
            "requested_symbol": "NQ",
            "normalized_symbol": "NQ",
            "latest_price": 28944.5,
            "latest_bar_time": leg1["timestamp"],
            "ohlc_is_closed": True,
            "ohlc": {key: leg1[key] for key in ("open", "high", "low", "close")},
            "liquidity": {
                "active_level": "PMH",
                "active_price": 28937.75,
                "nearest_level_above": {"name": "LH", "price": 29117.0},
                "nearest_level_below": {"name": "PMH", "price": 28937.75},
                "tick_size": 0.25,
            },
            "step_2_1a": {
                "step_2_activated": True,
                "active_level": "PMH",
                "level_price": 28937.75,
                "candle_a": {"timestamp": "2026-05-19T13:32:00Z", "open": 28940.75, "high": 28981.75, "low": 28930.25, "close": 28969.75},
                "step2_locked_owner": {
                    "pathway": "rejection",
                    "active_liquidity": active_liquidity,
                    "active_liquidity_name": "PMH",
                    "active_liquidity_price": 28937.75,
                    "setup_direction": "SHORT",
                },
            },
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 28937.75},
            "step25": {
                "status": "READY",
                "next_step": "Step 3",
                "state": {
                    "controlling_mode": "R/S",
                    "candidate_modes": ["R/S"],
                    "continuation_step2_activated": True,
                    "pathway_activation_type": "close",
                    "reclaim_candle_a": reclaim,
                    "initial_candle_a": reclaim,
                    "pathway_level": 28937.75,
                    "step25_pathway_selection_complete": True,
                },
            },
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4", "state": {"active_liquidity": active_liquidity}},
            "step4": {
                "status": "READY",
                "next_step": "Step 5",
                "reason": "Leg 1 complete.",
                "state": {
                    "controlling_mode": "R/S",
                    "current_pathway_control": "continuation",
                    "current_controlling_mode": "R/S",
                    "current_continuation_type": "R/S",
                    "shared_leg1_uses_initial_candle_a": True,
                    "setup_direction": "LONG",
                    "active_liquidity": active_liquidity,
                    "initial_candle_a": reclaim,
                    "candle_a": reclaim,
                    "candle_b": leg1,
                    "leg1_status": "COMPLETE",
                    "leg1_state_locked": True,
                    "leg1_completed_at": leg1["timestamp"],
                    "leg1_reference_price": reclaim["close"],
                    "leg1_reference_candle_time": reclaim["timestamp"],
                },
            },
            "step5": {"status": "WAIT", "state": {}, "next_step": "Step 5", "reason": "Waiting."},
            "step6": {"status": "WAIT", "state": {}, "next_step": "Step 6", "reason": "Waiting."},
        }
        entry_agent.run_once = lambda _symbol="NQ", persist=True: copy.deepcopy(snapshot)

        with tempfile.TemporaryDirectory() as temp_dir:
            entry_agent.STATE_PATH = Path(temp_dir) / "entry_agent_state.json"
            entry_agent.STATE_PATH.write_text(
                json.dumps({"state_by_symbol": {"NQ": {"consumed_liquidity_levels": [], "consumed_entry_setups": []}}}),
                encoding="utf-8",
            )
            status = entry_agent.build_entry_status("NQ")
            persisted_symbol_state = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))["state_by_symbol"]["NQ"]

        self.assertEqual(persisted_symbol_state["consumed_liquidity_levels"], [])
        self.assertEqual(persisted_symbol_state["consumed_entry_setups"], [])

        self.assertEqual(status["selected_pathway"], "continuation")
        self.assertEqual(status["current_pathway_control"], "continuation")
        self.assertEqual(status["sr_rs_context"], "R/S")
        self.assertEqual(status["setup_direction"], "LONG")
        self.assertEqual(status["continuation_side"]["setup_direction"], "LONG")
        self.assertEqual(status["continuation_side"]["selected_pathway"], "continuation")
        self.assertEqual(status["continuation_side"]["pathway_status"], "controlling")
        self.assertNotEqual(status["rejection_side"]["setup_direction"], "SHORT")
        self.assertIsNone(status["rejection_side"]["entry_status"])
        self.assertIsNone(status["rejection_side"]["current_step"])
        self.assertEqual(status["rejection_side"]["pathway_status"], "frozen")

    def test_rs_continuation_641_647_root_brain_contract(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import dry_run_injector
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        symbol = "NQ"
        tv_context = {
            "symbol": "NQ1!",
            "normalized_symbol": "NQ",
            "locked": True,
            "atr_1m_14": 40.0,
            "daily_atr14": 500.0,
            "levels": {
                "PMH": {"price": 28937.75, "status": "ACTIVE", "stack_group": "NONE"},
                "PML": {"price": 28700.0, "status": "ACTIVE", "stack_group": "NONE"},
                "ONH": {"price": 29150.0, "status": "ACTIVE", "stack_group": "NONE"},
                "ONL": {"price": 28600.0, "status": "ACTIVE", "stack_group": "NONE"},
            },
        }
        candles = dry_run_injector.build_scenario(symbol, "rs_continuation_641_647", tv_context)

        original_context = dry_run_injector.entry_agent.load_tv_context
        self.addCleanup(setattr, dry_run_injector.entry_agent, "load_tv_context", original_context)
        dry_run_injector.entry_agent.load_tv_context = lambda _symbol="NQ": copy.deepcopy(tv_context)

        with dry_run_injector.isolated_entry_agent_state(symbol) as state_path:
            dry_run_injector.seed_completed_pmh_rejection_state(state_path, symbol, 28937.75)
            statuses = dry_run_injector.run_dry_run(symbol, candles, scenario=None)

        status_1341 = statuses[0]
        self.assertEqual(status_1341["selected_pathway"], "rejection")
        self.assertEqual(status_1341["sr_rs_context"], "Normal Rejection Mode")
        self.assertEqual(status_1341["current_step"], "Step 6")
        self.assertEqual(status_1341["entry_status"], "CONFIRM")
        self.assertEqual(status_1341["rejection_side"]["entry_status"], "CONFIRM")
        self.assertEqual(status_1341["rejection_side"]["pathway_status"], "entered")
        self.assertNotEqual(status_1341["rejection_side"]["current_step"], "Step 5")
        self.assertNotEqual(status_1341["wait_reason"], "Leg 2 already validated; Step 6 handoff remains active.")
        self.assertIsNone(status_1341["continuation_side"]["current_step"])
        self.assertNotEqual(status_1341["selected_pathway"], "continuation")

        status_1342 = statuses[1]
        self.assertEqual(status_1342["selected_pathway"], "continuation")
        self.assertEqual(status_1342["sr_rs_context"], "R/S")
        self.assertEqual(status_1342["setup_direction"], "LONG")
        self.assertEqual(status_1342["continuation_side"]["pathway_status"], "controlling")
        self.assertEqual(status_1342["rejection_side"]["pathway_status"], "frozen")
        self.assertIsNone(status_1342["rejection_side"]["entry_status"])
        self.assertIsNone(status_1342["rejection_side"]["current_step"])
        self.assertEqual(status_1342["consumed_liquidity_levels"], [])
        self.assertEqual(status_1342["current_step_confirmed_at"], "2026-05-19T13:42:00Z")
        self.assertEqual(status_1342["leg1_window_started_at"], "2026-05-19T13:42:00Z")
        self.assertEqual(status_1342["leg1_window_candle_index"], 0)
        self.assertNotEqual(status_1342["leg1_window_started_at"], "2026-05-19T13:32:00Z")

        status_1343 = statuses[2]
        self.assertEqual(status_1343["current_step"], "Step 4")
        self.assertEqual(status_1343["leg1_state"], "COMPLETE")
        self.assertEqual(status_1343["selected_pathway"], "continuation")
        self.assertNotEqual(status_1343["rejection_side"]["setup_direction"], "SHORT")
        self.assertIsNone(status_1343["rejection_side"]["current_step"])
        self.assertEqual(status_1343["leg1_window_started_at"], "2026-05-19T13:42:00Z")
        self.assertEqual(status_1343["leg1_window_candle_index"], 1)
        self.assertEqual(status_1343["leg1_reference_candle_time"], "2026-05-19T13:42:00Z")
        self.assertNotEqual(status_1343["leg1_reference_price"], 28969.75)
        self.assertEqual(status_1343["step4_proximity_distance"], 6.75)
        self.assertEqual(status_1343["step4_proximity_atr_threshold"], 50.0)

        status_1344 = statuses[3]
        self.assertEqual(status_1344["current_step"], "Step 5")
        self.assertIn(status_1344["leg2_state"], {"CONFIRMED", "VALIDATED"})
        self.assertEqual(status_1344["setup_direction"], "LONG")
        self.assertTrue(status_1344["step6_window_active"])
        self.assertEqual(status_1344["step6_window_started_at"], "2026-05-19T13:44:00Z")
        self.assertEqual(status_1344["step6_window_candle_index"], 0)
        self.assertEqual(status_1344["step6_window_remaining"], 4)
        self.assertEqual(status_1344["step6_window_expires_at"], "2026-05-19T13:48:00Z")

        status_1345 = statuses[4]
        self.assertEqual(status_1345["current_step"], "Step 6")
        self.assertEqual(status_1345["entry_status"], "CONFIRM")
        self.assertEqual(status_1345["entry_type_number"], 1)
        self.assertEqual(status_1345["entry_type_name"], "Sweep Entry")
        self.assertEqual(status_1345["entry_model"], "small_wick_reclaim")
        self.assertIn("Small Wick Reclaim", status_1345["last_decision"])
        self.assertTrue(status_1345["step6_window_active"])
        self.assertEqual(status_1345["step6_window_started_at"], "2026-05-19T13:44:00Z")
        self.assertEqual(status_1345["step6_window_candle_index"], 1)
        self.assertEqual(status_1345["step6_window_remaining"], 3)
        self.assertEqual(status_1345["selected_pathway"], "continuation")
        self.assertEqual(status_1345["setup_direction"], "LONG")
        self.assertNotEqual(status_1345["rejection_side"]["setup_direction"], "SHORT")
        self.assertIsNone(status_1345["rejection_side"]["entry_status"])
        self.assertIsNone(status_1345["rejection_side"]["current_step"])

    def test_step6_window_expiration_publishes_past_step5_gate(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        snapshot = {
            "latest_price": 50611.0,
            "latest_bar_time": "2026-05-28T13:49:00Z",
            "ohlc_is_closed": True,
            "step6": {
                "step": "Step 7",
                "status": "TERMINATED",
                "reason": "Phase 1 failed on Candle 4 with no valid Phase 2 failed-entry participation.",
                "state": {
                    "terminated_by": "Step 6",
                    "step6_window_active": False,
                    "step6_window_started_at": "2026-05-28T13:45:00Z",
                    "step6_window_candle_index": 4,
                    "step6_window_remaining": 0,
                    "step6_window_expires_at": "2026-05-28T13:49:00Z",
                },
            },
            "step5": {
                "step": "Step 5",
                "status": "READY",
                "next_step": "Step 6",
                "state": {
                    "leg2_status": "VALIDATED",
                    "step5_participation_validated": True,
                    "leg2_candidate_candle_time": "2026-05-28T13:46:00Z",
                    "step6_window_active": True,
                    "step6_window_started_at": "2026-05-28T13:45:00Z",
                    "step6_window_candle_index": 4,
                    "step6_window_remaining": 0,
                    "step6_window_expires_at": "2026-05-28T13:49:00Z",
                },
            },
            "step4": {
                "step": "Step 4",
                "status": "READY",
                "next_step": "Step 5",
                "state": {
                    "leg1_status": "COMPLETE",
                    "leg1_state_locked": True,
                    "setup_direction": "SHORT",
                    "active_liquidity": {"name": "ONL", "price": 50576.0, "side": "lower"},
                    "leg1_reference_price": 50578.0,
                    "leg1_reference_candle_time": "2026-05-28T13:43:00Z",
                    "leg1_completed_at": "2026-05-28T13:44:00Z",
                    "candle_a": {"timestamp": "2026-05-28T13:43:00Z"},
                    "candle_b": {"timestamp": "2026-05-28T13:44:00Z"},
                },
            },
            "step3": {},
        }

        self.assertEqual(entry_agent.current_step_from_snapshot(snapshot), "Step 5")
        public_invalidation = entry_agent.public_invalidation_from_results(
            "Step 6",
            snapshot["step4"],
            snapshot["step5"],
            snapshot["step6"],
        )
        self.assertEqual(public_invalidation["source_step"], "Step 6")
        self.assertIn("Candle 4", public_invalidation["reason"])

    def test_step4_proximity_threshold_uses_daily_atr_not_one_minute_atr(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            from step4_engine import evaluate_step4
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        interaction = {
            "system_state": "REJECTION MODE ON",
            "trade_mode": "ON",
            "rejection_mode": "ON",
            "interaction_state": "ACTIVE",
            "setup_direction": "SHORT",
            "step25_pathway_selection_complete": True,
            "step3_allows_structure": True,
            "controlling_mode": "Normal Rejection Mode",
            "candidate_modes": ["Normal Rejection Mode"],
            "initial_candle_a": {"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5},
            "nearest_opposing_liquidity": {"name": "PML", "price": 95.0},
            "atr_1m_14": 10.0,
            "daily_atr14": 100.0,
            "events": [],
        }
        candle_b = {"open": 100.5, "high": 100.75, "low": 99.0, "close": 100.75}

        result = evaluate_step4(interaction, candle_b)

        self.assertEqual(result["step"], "Step 7")
        self.assertEqual(result["status"], "TERMINATED")
        self.assertEqual(result["state"]["proximity_daily_atr"], 100.0)
        self.assertEqual(result["state"]["proximity_atr_threshold"], 10.0)
        self.assertEqual(result["state"]["proximity_atr_threshold_percent"], 10.0)
        self.assertIn("10% daily ATR", result["reason"])

    def test_nq_644_645_live_status_replay_confirms_shared_leg1(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot
        original_recent_closed_bars = entry_agent.recent_closed_bars
        self.addCleanup(setattr, entry_agent, "STATE_PATH", original_state_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_PATH", original_context_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_BY_SYMBOL_PATH", original_by_symbol_path)
        self.addCleanup(setattr, entry_agent, "RITHMIC_ATR_SNAPSHOT_PATH", original_atr_path)
        self.addCleanup(setattr, entry_agent, "get_latest_market_snapshot", original_market_snapshot)
        self.addCleanup(setattr, entry_agent, "recent_closed_bars", original_recent_closed_bars)

        step2_candle = {
            "open": 100.4,
            "high": 100.5,
            "low": 99.4,
            "close": 99.7,
            "timestamp": "2026-05-18T13:44:00Z",
        }
        participation_candle = {
            "open": 99.65,
            "high": 100.7,
            "low": 99.1,
            "close": 100.25,
            "timestamp": "2026-05-18T13:45:00Z",
        }
        candles = [step2_candle, participation_candle]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "atr.json"
            cursor = {"index": 0}

            def market_snapshot(_symbol):
                candle = candles[cursor["index"]]
                return {
                    "source": "test",
                    "symbol": "NQM6",
                    "latest_price": candle["close"],
                    "latest_bar_time": candle["timestamp"],
                    "ohlc_is_closed": True,
                    "ohlc": candle,
                }

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol, limit=2: candles[: cursor["index"] + 1][-limit:]
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "normalized_symbol": "NQ",
                                "locked": True,
                                "levels": {
                                    "PML": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "PMH": {"price": 110.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "ONL": {"price": 90.0, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                                "atr_1m_14": 4.0,
                                "daily_atr14": 40.0,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            step2_status = entry_agent.build_entry_status("NQ")
            cursor["index"] = 1
            leg1_status = entry_agent.build_entry_status("NQ")

        self.assertEqual(step2_status["current_step"], "Step 2")
        self.assertEqual(step2_status["current_step_status"], "CONFIRMED")
        self.assertEqual(step2_status["setup_direction"], "LONG")
        self.assertEqual(step2_status["rejection_side"]["setup_direction"], "LONG")
        self.assertIsNone(step2_status["continuation_side"]["setup_direction"])
        self.assertEqual(step2_status["leg1_status"], "WAIT")
        self.assertEqual(step2_status["leg2_status"], "WAIT")
        self.assertEqual(step2_status["entry_status"], "WAIT")

        self.assertEqual(leg1_status["current_step"], "Step 4")
        self.assertEqual(leg1_status["current_step_label"], "Shared Leg 1 Confirmed")
        self.assertEqual(leg1_status["current_step_status"], "CONFIRMED")
        self.assertEqual(leg1_status["leg1_status"], "COMPLETE")
        self.assertEqual(leg1_status["leg1_state"], "COMPLETE")
        self.assertTrue(leg1_status["leg1_locked"])
        self.assertTrue(leg1_status["leg1_state_locked"])
        self.assertEqual(leg1_status["leg1_confirmed_at"], "2026-05-18T13:45:00Z")
        self.assertEqual(leg1_status["leg1_completed_at"], "2026-05-18T13:45:00Z")
        self.assertEqual(leg1_status["rejection_pathway_status"], "controlling")
        self.assertEqual(leg1_status["rejection_side"]["pathway_status"], "controlling")
        self.assertEqual(leg1_status["rejection_side"]["setup_direction"], "LONG")
        self.assertEqual(leg1_status["continuation_pathway_status"], "active")
        self.assertEqual(leg1_status["continuation_side"]["pathway_status"], "active")
        self.assertEqual(leg1_status["continuation_side"]["continuation_type"], "S/R")
        self.assertEqual(leg1_status["continuation_side"]["setup_direction"], "SHORT")
        self.assertEqual(leg1_status["leg2_status"], "WAIT")
        self.assertEqual(leg1_status["entry_status"], "WAIT")

    def test_leg1_50_percent_penetration_rule_fields_and_invalidation(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        candle_a = {"open": 100.2, "high": 100.3, "low": 99.9, "close": 100.1, "timestamp": "2026-05-05T18:25:00Z"}
        valid_b = {"open": 100.0, "high": 100.2, "low": 99.6, "close": 100.0, "timestamp": "2026-05-05T18:26:00Z"}
        invalid_b = {"open": 100.0, "high": 100.2, "low": 94.8, "close": 100.0, "timestamp": "2026-05-05T18:27:00Z"}
        step25 = {
            "status": "READY",
            "state": {
                "rejection_mode": "ON",
                "interaction_state": "ACTIVE",
                "initial_candle_a": candle_a,
                "step25_pathway_selection_complete": True,
            },
            "events": [],
        }
        step3 = {
            "status": "ALLOW_STEP_4",
            "next_step": "Step 4",
            "state": {
                "step3_allows_structure": True,
                "interaction_state": "ACTIVE",
                "active_liquidity": {"name": "PML", "price": 100.0},
                "tick_size": 0.25,
            },
            "events": [],
        }

        def snapshot(candle):
            return {
                "latest_price": candle["close"],
                "latest_bar_time": candle["timestamp"],
                "ohlc": candle,
                "liquidity": {
                    "tick_size": 0.25,
                    "nearest_level_below": {"name": "LL", "price": 90.0},
                    "nearest_level_above": {"name": "PMH", "price": 110.0},
                },
                "atr": {"atr_1m_14": 1.0},
                "tv_context": {"daily_atr14": 40.0},
            }

        valid = entry_agent.evaluate_live_step4(snapshot(valid_b), {"rejection_mode": "ON", "watch_side": "LONG"}, step25, step3, {})
        invalid = entry_agent.evaluate_live_step4(snapshot(invalid_b), {"rejection_mode": "ON", "watch_side": "LONG"}, step25, step3, {})

        self.assertEqual(valid["status"], "READY")
        self.assertAlmostEqual(valid["state"]["leg1_formed_at_percent"], 4.0)
        self.assertTrue(valid["state"]["leg1_50_percent_rule_passed"])
        self.assertEqual(invalid["status"], "TERMINATED")
        self.assertFalse(invalid["state"]["leg1_50_percent_rule_passed"])
        self.assertIn("50%", invalid["reason"])

    def test_locked_leg1_skips_50_percent_rule_on_later_retracement(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        locked_state = {
            "rejection_mode": "ON",
            "interaction_state": "ACTIVE",
            "leg1_status": "COMPLETE",
            "leg1_state_locked": True,
            "setup_direction": "SHORT",
            "leg1_direction": "SHORT",
            "active_liquidity": {"name": "ONH", "price": 50000.0},
            "candle_a": {"open": 49980.0, "high": 50020.0, "low": 49970.0, "close": 50005.0, "timestamp": "2026-05-06T06:38:00-07:00"},
            "candle_b": {"open": 50003.0, "high": 50010.0, "low": 49980.0, "close": 49990.0, "timestamp": "2026-05-06T06:39:00-07:00"},
            "leg1_completed_at": "2026-05-06T06:39:00-07:00",
            "leg1_reference": 50005.0,
            "leg1_reference_price": 50005.0,
            "leg1_reference_candle_time": "2026-05-06T06:38:00-07:00",
            "leg1_extreme": 50020.0,
            "anchor_extreme": 50020.0,
            "current_active_sequence_started_at": "2026-05-06T06:38:00-07:00",
            "leg1_formed_at_percent": 10.0,
            "leg1_50_percent_rule_passed": True,
        }
        step25 = {
            "status": "READY",
            "next_step": "Step 3",
            "state": {
                "rejection_mode": "ON",
                "interaction_state": "ACTIVE",
                "initial_candle_a": locked_state["candle_a"],
                "step25_pathway_selection_complete": True,
            },
            "events": [],
        }
        step3 = {
            "status": "ALLOW_STEP_4",
            "next_step": "Step 4",
            "state": {
                "step3_allows_structure": True,
                "interaction_state": "ACTIVE",
                "active_liquidity": {"name": "ONH", "price": 50000.0},
            },
            "events": [],
        }
        retracement_snapshot = {
            "latest_price": 50060.0,
            "latest_bar_time": "2026-05-06T06:45:00-07:00",
            "ohlc": {"open": 50020.0, "high": 50070.0, "low": 50010.0, "close": 50060.0},
            "liquidity": {
                "tick_size": 1.0,
                "nearest_level_above": {"name": "YH", "price": 50100.0},
                "nearest_level_below": {"name": "ONH", "price": 50000.0},
            },
            "atr": {"atr_1m_14": 10.0},
            "tv_context": {"daily_atr14": 400.0},
        }

        result = entry_agent.evaluate_live_step4(
            retracement_snapshot,
            {"rejection_mode": "ON", "watch_side": "SHORT"},
            step25,
            step3,
            {"step4": {"status": "READY", "next_step": "Step 5", "state": locked_state, "events": []}},
        )

        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["next_step"], "Step 5")
        self.assertEqual(result["state"]["fifty_percent_rule_phase"], "skipped_leg1_locked")
        self.assertTrue(result["state"]["leg1_state_locked"])
        self.assertEqual(result["state"]["leg1_completed_at"], "2026-05-06T06:39:00-07:00")
        self.assertIsNone(result["state"].get("invalidation_source"))

    def test_leg2_25_percent_extension_rule_fields_and_invalidation(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step5_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        base_state = {
            "rejection_mode": "ON",
            "interaction_state": "ACTIVE",
            "leg1_status": "COMPLETE",
            "leg1_state_locked": True,
            "setup_direction": "LONG",
            "leg1_direction": "LONG",
            "tick_size": 0.25,
            "leg1_reference": 100.0,
            "leg1_reference_price": 100.0,
            "leg1_reference_candle_time": "2026-05-05T18:25:00Z",
            "leg1_extreme": 96.0,
            "anchor_extreme": 96.0,
            "leg1_completed_at": "2026-05-05T18:26:00Z",
            "current_active_sequence_started_at": "2026-05-05T18:25:00Z",
            "active_liquidity": {"name": "PML", "price": 100.0},
            "candle_a": {"open": 100.5, "high": 101.0, "low": 96.0, "close": 100.0},
            "candle_b": {"open": 99.8, "high": 100.1, "low": 96.5, "close": 99.5},
            "nearest_opposing_liquidity": {"name": "PMH", "price": 110.0},
            "atr_1m_14": 1.0,
            "enforce_leg2_25_percent_rule": True,
            "events": [],
        }

        valid = step5_engine.evaluate_step5(
            {**base_state, "latest_candle": {"open": 99.0, "high": 99.5, "low": 95.2, "close": 95.8}}
        )
        invalid = step5_engine.evaluate_step5(
            {**base_state, "latest_candle": {"open": 99.0, "high": 99.5, "low": 94.8, "close": 95.8}}
        )

        self.assertEqual(valid["status"], "WAIT")
        self.assertAlmostEqual(valid["state"]["leg2_formed_at_percent"], 22.857142857142776)
        self.assertTrue(valid["state"]["leg2_25_percent_rule_passed"])
        self.assertEqual(invalid["status"], "TERMINATED")
        self.assertAlmostEqual(invalid["state"]["leg2_formed_at_percent"], 34.285714285714285)
        self.assertFalse(invalid["state"]["leg2_25_percent_rule_passed"])
        self.assertIn("25%", invalid["reason"])

    def test_leg2_25_percent_waits_without_current_locked_leg1(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
            import step5_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        candle = {"open": 99.0, "high": 99.5, "low": 94.8, "close": 95.8, "timestamp": "2026-05-05T18:27:00Z"}
        base_state = {
            "rejection_mode": "ON",
            "interaction_state": "ACTIVE",
            "leg1_status": "COMPLETE",
            "setup_direction": "LONG",
            "tick_size": 0.25,
            "leg1_reference": 100.0,
            "leg1_extreme": 96.0,
            "anchor_extreme": 96.0,
            "candle_a": {"open": 100.5, "high": 101.0, "low": 96.0, "close": 100.0},
            "candle_b": {"open": 99.8, "high": 100.1, "low": 96.5, "close": 99.5},
            "nearest_opposing_liquidity": {"name": "PMH", "price": 110.0},
            "atr_1m_14": 1.0,
            "enforce_leg2_25_percent_rule": True,
            "latest_candle": candle,
            "events": [],
        }

        no_lock = step5_engine.evaluate_step5(base_state)
        stale_lock = step5_engine.evaluate_step5(
            {
                **base_state,
                "leg1_state_locked": True,
                "leg1_reference_price": 100.0,
                "leg1_reference_candle_time": "2026-05-05T13:38:00-07:00",
                "leg1_direction": "LONG",
                "active_liquidity": {"name": "PML", "price": 100.0},
                "leg1_completed_at": "2026-05-05T13:39:00-07:00",
                "current_active_sequence_started_at": "2026-05-05T18:25:00Z",
            }
        )
        live_wait = entry_agent.evaluate_live_step5(
            {"latest_price": 95.8, "latest_bar_time": candle["timestamp"], "ohlc": candle},
            {
                "status": "READY",
                "next_step": "Step 5",
                "state": {**base_state, "leg1_state_locked": False},
            },
            {},
        )

        self.assertEqual(no_lock["status"], "WAIT")
        self.assertIsNone(no_lock["state"]["leg2_formed_at_percent"])
        self.assertIsNone(no_lock["state"]["leg2_25_percent_rule_passed"])
        self.assertEqual(no_lock["reason"], "Waiting for valid locked Leg 1 reference")
        self.assertEqual(stale_lock["status"], "WAIT")
        self.assertIsNone(stale_lock["state"]["leg2_formed_at_percent"])
        self.assertIsNone(stale_lock["state"]["leg2_25_percent_rule_passed"])
        self.assertEqual(stale_lock["reason"], "Waiting for valid locked Leg 1 reference")
        self.assertEqual(live_wait["status"], "WAIT")
        self.assertEqual(live_wait["reason"], "Waiting for valid locked Leg 1 reference")

    def test_step5_rejects_same_sequence_leg2_candidate_after_locked_leg1(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        step4 = {
            "status": "READY",
            "next_step": "Step 5",
            "state": {
                "rejection_mode": "ON",
                "interaction_state": "ACTIVE",
                "leg1_status": "COMPLETE",
                "leg1_state_locked": True,
                "setup_direction": "LONG",
                "leg1_direction": "LONG",
                "tick_size": 0.25,
                "leg1_reference": 100.0,
                "leg1_reference_price": 100.0,
                "leg1_reference_candle_time": "2026-05-06T07:59:00-07:00",
                "leg1_extreme": 96.0,
                "anchor_extreme": 96.0,
                "leg1_completed_at": "2026-05-06T08:00:00-07:00",
                "current_active_sequence_started_at": "2026-05-06T07:59:00-07:00",
                "active_liquidity": {"name": "ONH", "price": 100.0},
                "candle_a": {
                    "open": 100.5,
                    "high": 101.0,
                    "low": 96.0,
                    "close": 100.0,
                    "timestamp": "2026-05-06T07:59:00-07:00",
                },
                "candle_b": {
                    "open": 99.8,
                    "high": 100.1,
                    "low": 96.5,
                    "close": 99.5,
                    "timestamp": "2026-05-06T08:00:00-07:00",
                },
                "nearest_opposing_liquidity": {"name": "PMH", "price": 110.0},
                "atr_1m_14": 1.0,
            },
        }
        same_candle = {
            "latest_price": 95.8,
            "latest_bar_time": "2026-05-06T15:00:00Z",
            "ohlc": {"open": 99.0, "high": 99.5, "low": 95.2, "close": 95.8},
        }
        later_candle = {
            "latest_price": 95.8,
            "latest_bar_time": "2026-05-06T15:01:00Z",
            "ohlc": {"open": 99.0, "high": 99.5, "low": 95.2, "close": 95.8},
        }

        same_result = entry_agent.evaluate_live_step5(same_candle, step4, {})
        later_result = entry_agent.evaluate_live_step5(later_candle, step4, {})

        self.assertEqual(same_result["status"], "WAIT")
        self.assertEqual(same_result["state"]["leg2_candidate_candle_time"], "2026-05-06T15:00:00Z")
        self.assertTrue(same_result["state"]["leg2_same_sequence_rejected"])
        self.assertEqual(
            same_result["state"]["leg2_wait_reason"],
            "Step 5 waiting for a separate future Leg 2 candle after locked Leg 1.",
        )
        self.assertEqual(later_result["status"], "WAIT")
        self.assertEqual(later_result["state"]["leg2_status"], "CONFIRMED")
        self.assertEqual(later_result["state"]["leg2_candidate_candle_time"], "2026-05-06T15:01:00Z")
        self.assertFalse(later_result["state"]["leg2_same_sequence_rejected"])

    def test_leg1_window_counts_next_four_closed_candles_after_step2(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step4_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        state = {
            "rejection_mode": "ON",
            "step25_pathway_selection_complete": True,
            "step3_allows_structure": True,
            "interaction_state": "ACTIVE",
            "setup_direction": "SHORT",
            "initial_candle_a": {"timestamp": "2026-05-14T13:38:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
            "active_liquidity": {"name": "PMH", "price": 100.0},
            "nearest_opposing_liquidity": {"name": "PML", "price": 90.0},
            "atr_1m_14": 1.0,
            "daily_atr14": 40.0,
            "events": [],
        }
        no_participation = [
            {"timestamp": "2026-05-14T13:39:00Z", "open": 102.0, "high": 102.75, "low": 102.0, "close": 102.5},
            {"timestamp": "2026-05-14T13:40:00Z", "open": 102.5, "high": 103.25, "low": 102.5, "close": 103.0},
            {"timestamp": "2026-05-14T13:41:00Z", "open": 103.0, "high": 103.75, "low": 103.0, "close": 103.5},
            {"timestamp": "2026-05-14T13:42:00Z", "open": 103.5, "high": 104.25, "low": 103.5, "close": 104.0},
        ]
        step4_engine.initialize_leg1_window(state, "2026-05-14T13:38:00Z")

        for index, candle in enumerate(no_participation, start=1):
            result = step4_engine.evaluate_step4({**state, "candle_b": candle})
            state = result["state"]
            self.assertEqual(state["leg1_window_candle_index"], index)
            self.assertEqual(state["leg1_window_started_at"], "2026-05-14T13:38:00Z")
            self.assertEqual(state["leg1_window_expires_at"], "2026-05-14T13:42:00Z")
            self.assertEqual(state["leg1_window_remaining"], 4 - index)
            if index < 4:
                self.assertEqual(result["status"], "WAIT")
                self.assertTrue(state["leg1_window_active"])
                self.assertFalse(state["leg1_window_invalidated"])
            else:
                self.assertEqual(result["status"], "TERMINATED")
                self.assertFalse(state["leg1_window_active"])
                self.assertTrue(state["leg1_window_invalidated"])
                self.assertEqual(
                    state["leg1_window_invalidation_reason"],
                    "Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation.",
                )

    def test_leg1_window_accepts_participation_on_candles_1_through_4(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step4_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        def base_state():
            return {
                "rejection_mode": "ON",
                "step25_pathway_selection_complete": True,
                "step3_allows_structure": True,
                "interaction_state": "ACTIVE",
                "setup_direction": "SHORT",
                "initial_candle_a": {"timestamp": "2026-05-14T13:38:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
                "active_liquidity": {"name": "PMH", "price": 100.0},
                "nearest_opposing_liquidity": {"name": "PML", "price": 90.0},
                "atr_1m_14": 1.0,
                "daily_atr14": 40.0,
                "events": [],
            }

        no_participation = [
            {"timestamp": "2026-05-14T13:39:00Z", "open": 102.0, "high": 102.75, "low": 102.0, "close": 102.5},
            {"timestamp": "2026-05-14T13:40:00Z", "open": 102.5, "high": 103.25, "low": 102.5, "close": 103.0},
            {"timestamp": "2026-05-14T13:41:00Z", "open": 103.0, "high": 103.75, "low": 103.0, "close": 103.5},
        ]
        participation = {"open": 102.0, "high": 102.5, "low": 100.0, "close": 100.75}

        for participation_index in (1, 2, 3, 4):
            with self.subTest(participation_index=participation_index):
                state = base_state()
                step4_engine.initialize_leg1_window(state, "2026-05-14T13:38:00Z")
                for candle in no_participation[: participation_index - 1]:
                    result = step4_engine.evaluate_step4({**state, "candle_b": candle})
                    self.assertEqual(result["status"], "WAIT")
                    state = result["state"]
                candle = {**participation, "timestamp": f"2026-05-14T13:{38 + participation_index:02d}:00Z"}
                result = step4_engine.evaluate_step4({**state, "candle_b": candle})

                self.assertEqual(result["status"], "READY")
                self.assertEqual(result["next_step"], "Step 5")
                self.assertEqual(result["state"]["leg1_status"], "COMPLETE")
                self.assertEqual(result["state"]["leg1_window_candle_index"], participation_index)
                self.assertFalse(result["state"]["leg1_window_active"])
                self.assertFalse(result["state"]["leg1_window_invalidated"])

    def test_market_feed_uses_trade_manager_last_price_snapshot(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import market_feed
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_urlopen = market_feed.urlopen

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _traceback):
                return False

            def read(self):
                return json.dumps(
                    {
                        "timestamp": "2026-05-05T18:26:00Z",
                        "symbols": {
                            "YMM6": {
                                "last_price": 50101,
                                "last_price_at": "2026-05-05T18:26:01Z",
                                "current_1m_bar": {
                                    "open": 50100,
                                    "high": 50102,
                                    "low": 50099,
                                    "close": 50101,
                                    "timestamp": "2026-05-05T18:26:00Z",
                                },
                            }
                        },
                    }
                ).encode("utf-8")

        market_feed.urlopen = lambda _url, timeout=0.5: FakeResponse()
        try:
            snapshot = market_feed.get_latest_market_snapshot("YM")
        finally:
            market_feed.urlopen = original_urlopen

        self.assertEqual(snapshot["symbol"], "YMM6")
        self.assertEqual(snapshot["latest_price"], 50101.0)
        self.assertEqual(snapshot["ohlc"]["close"], 50101)

    def test_build_entry_status_waits_when_market_price_missing(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = lambda symbol: {
                "source": "test",
                "symbol": symbol,
                "latest_price": None,
                "latest_bar_time": None,
                "ohlc": None,
            }
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ",
                                "levels": {
                                    "ONH": {"price": 28008.5, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            status = entry_agent.build_entry_status("NQM6")
            self.assertEqual(status["wait_reason"], "No market price available.")
            self.assertIsNone(status["active_liquidity_name"])
            self.assertIsNone(status["active_liquidity_price"])

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_tv_context_receiver_accepts_payload_without_strict_source(self):
        server = self._load_server()
        response = server.app.test_client().post(
            "/webhook/tv-context",
            json={"source": "wrong", "symbol": "NQ"},
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["context"]["source"], "wrong")

    def test_entry_status_preserves_requested_contract_symbol(self):
        server = self._load_server()
        server.build_entry_status = lambda symbol: {
            "symbol": symbol,
            "timestamp": "2026-05-05T00:00:00+00:00",
            "current_step": "Step 3",
            "active_liquidity_name": "ONH",
            "active_liquidity_price": 50100,
            "setup_direction": None,
            "leg1_status": "WAIT",
            "leg2_status": "WAIT",
            "entry_status": "WAIT",
            "wait_reason": "Leg 1 waiting.",
            "invalidation_reason": None,
            "last_decision": "WAIT: Leg 1 waiting.",
        }

        response = server.app.test_client().get("/entry/status?symbols=NQM6,YMM6,RTYM6")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["symbol"] for item in payload["symbols"]], ["NQM6", "YMM6", "RTYM6"])
        self.assertTrue(all(item["current_step"] == "Step 2" for item in payload["symbols"]))

    def test_entry_status_cors_preflight_returns_allow_headers(self):
        server = self._load_server()
        response = server.app.test_client().options(
            "/entry/status?symbols=NQ,YM,RTY",
            headers={
                "Origin": "http://localhost:7001",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "*")
        self.assertIn("GET", response.headers.get("Access-Control-Allow-Methods", ""))
        self.assertEqual(response.headers.get("Access-Control-Allow-Headers"), "*")

    def test_entry_status_get_returns_cors_header(self):
        server = self._load_server()
        server.build_entry_status = lambda symbol: {
            "symbol": symbol,
            "timestamp": "2026-05-05T00:00:00+00:00",
            "current_step": "Step 3",
            "active_liquidity_name": "ONH",
            "active_liquidity_price": 50100,
            "setup_direction": None,
            "leg1_status": "WAIT",
            "leg2_status": "WAIT",
            "entry_status": "WAIT",
            "wait_reason": "Leg 1 waiting.",
            "invalidation_reason": None,
            "last_decision": "WAIT: Leg 1 waiting.",
        }

        response = server.app.test_client().get(
            "/entry/status?symbols=NQ",
            headers={"Origin": "http://localhost:7001"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "*")

    def test_entry_status_appends_throttled_decision_log(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.ENTRY_LOG_DIR = temp_path / "logs"
            server.ENTRY_DECISIONS_LOG_PATH = server.ENTRY_LOG_DIR / "entry_decisions.jsonl"
            server.ENTRY_DECISION_LAST_LOGGED.clear()
            state = {"step": "Step 3"}

            def fake_status(symbol):
                return {
                    "symbol": symbol,
                    "timestamp": "2026-05-05T00:00:00+00:00",
                    "current_step": state["step"],
                    "active_liquidity_name": "ONH",
                    "active_liquidity_price": 50100,
                    "setup_direction": "SHORT",
                    "leg1_status": "WAIT",
                    "leg2_status": "WAIT",
                    "entry_status": "WAIT",
                    "wait_reason": "Leg 1 waiting.",
                    "invalidation_reason": None,
                    "last_decision": f"WAIT: {state['step']}",
                }

            server.build_entry_status = fake_status
            client = server.app.test_client()

            first = client.get("/entry/status?symbols=NQ")
            second = client.get("/entry/status?symbols=NQ")
            state["step"] = "Step 4"
            third = client.get("/entry/status?symbols=NQ")

            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(third.status_code, 200)
            lines = server.ENTRY_DECISIONS_LOG_PATH.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            records = [json.loads(line) for line in lines]
            self.assertEqual(records[0]["current_step"], "Step 2")
            self.assertEqual(records[1]["current_step"], "Step 4")
            self.assertEqual(records[0]["active_liquidity_name"], "ONH")

    def test_entry_log_debug_endpoint_returns_tail_limit(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.ENTRY_LOG_DIR = temp_path / "logs"
            server.ENTRY_DECISIONS_LOG_PATH = server.ENTRY_LOG_DIR / "entry_decisions.jsonl"
            server.ENTRY_LOG_DIR.mkdir(parents=True, exist_ok=True)
            server.ENTRY_DECISIONS_LOG_PATH.write_text(
                "\n".join(
                    json.dumps({"timestamp": f"t{i}", "symbol": "NQ", "current_step": f"Step {i}"})
                    for i in range(3)
                ) + "\n",
                encoding="utf-8",
            )

            response = server.app.test_client().get("/debug/entry-log?limit=2")
            payload = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["count"], 2)
            self.assertEqual([record["current_step"] for record in payload["records"]], ["Step 1", "Step 2"])

    def test_entry_status_appends_daily_reasoning_log_on_transition_or_new_candle(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.DATA_DIR = temp_path / "Data"
            server.ENTRY_REASONING_LAST_LOGGED.clear()
            state = {"step": "Step 3", "candle_time": "2026-05-06T13:00:00Z"}

            def fake_status(symbol):
                return {
                    "symbol": symbol,
                    "timestamp": "2026-05-06T13:00:01+00:00",
                    "candle_time": state["candle_time"],
                    "candle_open": 50000,
                    "candle_high": 50010,
                    "candle_low": 49990,
                    "candle_close": 50005,
                    "current_step": state["step"],
                    "active_liquidity_name": "ONH",
                    "liquidity_price": 50000,
                    "liquidity_group": None,
                    "close_vs_level": 5,
                    "setup_direction": "SHORT",
                    "rejection_mode_entered": True,
                    "sr_rs_context": "Normal Rejection Mode",
                    "leg1_state": "WAIT",
                    "leg1_locked": False,
                    "leg1_reference_price": None,
                    "leg1_completed_at": None,
                    "fifty_percent_rule_phase": "pre_leg1_only",
                    "leg2_state": "WAIT",
                    "leg2_candidate_candle_time": None,
                    "leg2_reference_price": None,
                    "leg2_25_percent_rule_passed": None,
                    "entry_status": "WAIT",
                    "invalidation_source": None,
                    "invalidation_reason": None,
                    "wait_reason": "Leg 1 waiting.",
                    "last_decision": f"WAIT: {state['step']}",
                }

            server.build_entry_status = fake_status
            client = server.app.test_client()
            first = client.get("/entry/status?symbols=YM")
            duplicate = client.get("/entry/status?symbols=YM")
            state["step"] = "Step 4"
            transition = client.get("/entry/status?symbols=YM")
            state["candle_time"] = "2026-05-06T13:01:00Z"
            new_candle = client.get("/entry/status?symbols=YM")

            self.assertEqual(first.status_code, 200)
            self.assertEqual(duplicate.status_code, 200)
            self.assertEqual(transition.status_code, 200)
            self.assertEqual(new_candle.status_code, 200)

            path = server.reasoning_log_path("2026-05-06")
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 3)
            self.assertEqual(records[0]["symbol"], "YM")
            self.assertEqual(records[0]["candle_open"], 50000)
            self.assertEqual(records[0]["active_liquidity_name"], "ONH")
            self.assertEqual(records[0]["step"], "Step 2")
            self.assertEqual(records[0]["current_step_label"], "Step 2 (Liquidity Close / Pathway Activation)")
            self.assertEqual(records[1]["step"], "Step 4")
            self.assertEqual(records[1]["current_step_label"], "Step 4 (Leg 1 Formation)")
            self.assertEqual(records[2]["candle_time"], "2026-05-06T13:01:00Z")

    def test_entry_reasoning_log_endpoint_filters_symbols_and_date(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.DATA_DIR = temp_path / "Data"
            server.DATA_DIR.mkdir(parents=True, exist_ok=True)
            server.reasoning_log_path("2026-05-06").write_text(
                "\n".join(
                    [
                        json.dumps({"timestamp": "t1", "symbol": "NQ", "step": "Step 2"}),
                        json.dumps({"timestamp": "t2", "symbol": "YM", "step": "Step 4"}),
                        json.dumps({"timestamp": "t3", "symbol": "RTY", "step": "Step 5"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            one = server.app.test_client().get("/entry/reasoning_log?symbols=YM&date=2026-05-06")
            many = server.app.test_client().get("/entry/reasoning_log?symbols=NQ,YM,RTY&date=2026-05-06")

            self.assertEqual(one.status_code, 200)
            self.assertEqual(one.get_json()["count"], 1)
            self.assertEqual(one.get_json()["records"][0]["symbol"], "YM")
            self.assertEqual(many.status_code, 200)
            self.assertEqual(many.get_json()["count"], 3)

    def test_command_center_entry_agent_fetch_is_simple_get(self):
        html = (ROOT / "command_center.html").read_text(encoding="utf-8")
        marker = "async function refreshEntryAgentStatus()"
        start = html.index(marker)
        end = html.index("async function forceRefreshAll", start)
        snippet = html[start:end]

        self.assertIn('const ENTRY_AGENT_BASE = "http://127.0.0.1:7002";', html)
        self.assertIn('method: "GET"', snippet)
        self.assertIn('mode: "cors"', snippet)
        self.assertNotIn("fetchJson", snippet)
        self.assertNotIn("headers", snippet)
        self.assertNotIn("Content-Type", snippet)
        self.assertNotIn("Authorization", snippet)

    def test_tv_context_receiver_stores_context_by_symbol_and_debug_returns_it(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.LEVELS_PATH = temp_path / "levels.json"
            server.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.TV_CONTEXT_EVENTS_PATH = temp_path / "tv_context_events.jsonl"
            server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()

            response = server.app.test_client().post(
                "/webhook/tv-context",
                json={
                    "source": "tradingview_level_helper",
                    "symbol": "CBOT_MINI:YM1!",
                    "ONH_price": 50100,
                    "ONL_price": 49900,
                },
            )
            payload = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["normalized_symbol"], "YM")
            self.assertEqual(payload["context"]["source"], "tradingview_level_helper")

            debug_response = server.app.test_client().get("/debug/tv-context?symbol=YMM6")
            debug_payload = debug_response.get_json()

            self.assertEqual(debug_response.status_code, 200)
            self.assertEqual(debug_payload["price_truth"], "Rithmic")
            self.assertEqual(debug_payload["symbols"]["YM"]["ONH_price"], 50100)
            self.assertEqual(debug_payload["symbols"]["YM"]["normalized_symbol"], "YM")

            levels_payload = json.loads(server.LEVELS_BY_SYMBOL_PATH.read_text(encoding="utf-8"))
            self.assertEqual(levels_payload["symbols"]["YM"]["ONH"], 50100.0)

    def test_tv_context_receiver_keeps_nested_level_tables_isolated_by_ingest_order(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.LEVELS_PATH = temp_path / "levels.json"
            server.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.TV_CONTEXT_EVENTS_PATH = temp_path / "tv_context_events.jsonl"
            server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
            client = server.app.test_client()

            client.post(
                "/webhook/tv-context",
                json={
                    "source": "tradingview_level_helper",
                    "symbol": "NQ1!",
                    "levels": {
                        "PML": {"price": 28392.0, "status": "ACTIVE", "stack_group": "NONE"}
                    },
                },
            )
            client.post(
                "/webhook/tv-context",
                json={
                    "source": "tradingview_level_helper",
                    "symbol": "RTY1!",
                    "levels": {
                        "PML": {"price": 2878.9, "status": "ACTIVE", "stack_group": "NONE"}
                    },
                },
            )
            levels_payload = json.loads(server.LEVELS_BY_SYMBOL_PATH.read_text(encoding="utf-8"))
            self.assertEqual(levels_payload["symbols"]["NQ"]["PML"], 28392.0)
            self.assertEqual(levels_payload["symbols"]["RTY"]["PML"], 2878.9)

            client.post(
                "/webhook/tv-context",
                json={
                    "source": "tradingview_level_helper",
                    "symbol": "NQ1!",
                    "levels": {
                        "PML": {"price": 28393.0, "status": "ACTIVE", "stack_group": "NONE"}
                    },
                },
            )
            levels_payload = json.loads(server.LEVELS_BY_SYMBOL_PATH.read_text(encoding="utf-8"))
            self.assertEqual(levels_payload["symbols"]["NQ"]["PML"], 28393.0)
            self.assertEqual(levels_payload["symbols"]["RTY"]["PML"], 2878.9)

    def test_debug_entry_liquidity_reports_per_root_pml_and_active_price(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.LEVELS_PATH = temp_path / "levels.json"
            server.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.TV_CONTEXT_EVENTS_PATH = temp_path / "tv_context_events.jsonl"
            server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
            server.build_entry_status = lambda symbol: {
                "symbol": symbol,
                "active_liquidity_name": "PML",
                "active_liquidity_price": {"NQ": 28392.0, "YM": 49730.0, "RTY": 2878.9}[server.normalize_symbol(symbol)],
            }
            server.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "ticker": "NQ1!",
                                "levels": {"PML": {"price": 28392.0}},
                            },
                            "YM": {
                                "symbol": "YM1!",
                                "ticker": "YM1!",
                                "levels": {"PML": {"price": 49730.0}},
                            },
                            "RTY": {
                                "symbol": "RTY1!",
                                "ticker": "RTY1!",
                                "levels": {"PML": {"price": 2878.9}},
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            response = server.app.test_client().get("/debug/entry-liquidity?symbols=NQM6,YMM6,RTYM6")
            payload = response.get_json()

            self.assertEqual(response.status_code, 200)
            by_root = {record["normalized_root"]: record for record in payload["symbols"]}
            self.assertEqual(by_root["NQ"]["stored_pml"], 28392.0)
            self.assertEqual(by_root["YM"]["stored_pml"], 49730.0)
            self.assertEqual(by_root["RTY"]["stored_pml"], 2878.9)
            self.assertEqual(by_root["NQ"]["active_liquidity_price"], 28392.0)
            self.assertEqual(by_root["YM"]["active_liquidity_price"], 49730.0)
            self.assertEqual(by_root["RTY"]["active_liquidity_price"], 2878.9)


if __name__ == "__main__":
    unittest.main()
