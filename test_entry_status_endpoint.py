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
        self.assertEqual(snapshot["publication_gate_debug"][0]["attempted_step"], "Step 5")
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

        self.assertEqual(selected["name"], "PMH")
        self.assertEqual(selected["price"], 100.0)
        self.assertEqual(selected["group"]["name"], "HIGH 1")
        self.assertEqual(selected["group"]["components"], ["ONH", "PMH"])
        self.assertNotIn("YH", selected["group"]["components"])

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

    def test_step2_wick_touch_without_close_does_not_activate_rejection_liquidity(self):
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
        snapshot = {
            "latest_price": 49300,
            "ohlc": {"open": 49290, "high": 49310, "low": 49280, "close": 49300},
            "tv_context": tv_context,
            "liquidity": {
                "tick_size": 1.0,
                "touched_levels": [{"name": "PMH", "price": 49307.0}],
            },
            "step_2_1a": {},
            "rejection": {},
        }

        self.assertIsNone(selected)
        self.assertEqual(entry_agent.active_liquidity_from_snapshot(snapshot), (None, None))

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
        self.assertIsNone(exact_ll)
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
            "events": [],
        }
        no_participation = [
            {"timestamp": "2026-05-14T13:39:00Z", "open": 102.0, "high": 102.75, "low": 102.0, "close": 102.5},
            {"timestamp": "2026-05-14T13:40:00Z", "open": 102.5, "high": 103.25, "low": 102.5, "close": 103.0},
            {"timestamp": "2026-05-14T13:41:00Z", "open": 103.0, "high": 103.75, "low": 103.0, "close": 103.5},
            {"timestamp": "2026-05-14T13:42:00Z", "open": 103.5, "high": 104.25, "low": 103.5, "close": 104.0},
        ]

        for index, candle in enumerate(no_participation, start=1):
            result = step4_engine.evaluate_step4({**state, "candle_b": candle})
            state = result["state"]
            self.assertEqual(state["leg1_window_candle_index"], index)
            self.assertEqual(state["leg1_window_started_at"], "2026-05-14T13:39:00Z")
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
                    "Candle B failed both close-based participation and 34% wick-based participation.",
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
