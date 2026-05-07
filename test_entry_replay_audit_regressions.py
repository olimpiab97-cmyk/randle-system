import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENTRY_AGENT_DIR = ROOT / "EntryAgent"


def load_replay_audit():
    sys.path.insert(0, str(ENTRY_AGENT_DIR))
    try:
        spec = importlib.util.spec_from_file_location(
            "entry_replay_audit_under_test",
            ENTRY_AGENT_DIR / "replay_audit.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        try:
            sys.path.remove(str(ENTRY_AGENT_DIR))
        except ValueError:
            pass


def load_entry_agent():
    sys.path.insert(0, str(ENTRY_AGENT_DIR))
    try:
        spec = importlib.util.spec_from_file_location(
            "entry_agent_under_replay_audit_test",
            ENTRY_AGENT_DIR / "entry_agent.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        try:
            sys.path.remove(str(ENTRY_AGENT_DIR))
        except ValueError:
            pass


class EntryReplayAuditRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit_module = load_replay_audit()
        cls.audit = cls.audit_module.build_audit("2026-05-07")
        cls.case_types = {case["case_type"] for case in cls.audit["cases"]}

    def test_leg1_does_not_publish_complete_before_participation_close(self):
        entry_agent = load_entry_agent()
        setup_candle = {"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5, "timestamp": "2026-05-07T13:30:00Z"}
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
        snapshot = {
            "latest_price": setup_candle["close"],
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

        result = entry_agent.evaluate_live_step4(
            snapshot,
            {"rejection_mode": "ON", "watch_side": "SHORT"},
            step25,
            step3,
            {},
        )

        self.assertEqual(result["status"], "WAIT")
        self.assertEqual(result["next_step"], "Step 4")
        self.assertNotEqual(result["state"].get("leg1_status"), "COMPLETE")

    def test_step5_does_not_publish_before_prior_confirmed_leg1(self):
        entry_agent = load_entry_agent()
        setup_candle = {"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5, "timestamp": "2026-05-07T13:30:00Z"}
        snapshot = {
            "latest_price": setup_candle["close"],
            "latest_bar_time": setup_candle["timestamp"],
            "ohlc": setup_candle,
            "ohlc_is_closed": True,
            "step25": {"status": "READY"},
            "step3": {"status": "ALLOW_STEP_4"},
            "step4": {
                "status": "READY",
                "next_step": "Step 5",
                "state": {
                    "leg1_status": "COMPLETE",
                    "leg1_state_locked": True,
                    "leg1_reference_price": 100.5,
                    "leg1_reference_candle_time": setup_candle["timestamp"],
                    "leg1_direction": "SHORT",
                    "setup_direction": "SHORT",
                    "active_liquidity": {"name": "PMH", "price": 100.0},
                    "leg1_completed_at": setup_candle["timestamp"],
                    "candle_a": setup_candle,
                },
            },
            "step5": {"status": "WAIT"},
            "step6": {"status": "WAIT"},
            "rejection": {"rejection_mode": "ON"},
        }

        self.assertEqual(entry_agent.current_step_from_snapshot(snapshot), "Step 4")
        self.assertIsNone(entry_agent.build_step5_interaction(snapshot, snapshot["step4"], {}))

    def test_active_liquidity_switches_to_expected_close_confirmed_level(self):
        entry_agent = load_entry_agent()
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
        self.assertEqual(result["last_interacted_liquidity"]["name"], "ONL")

    def test_nq_does_not_rearm_and_overfire_multiple_entries(self):
        entry_agent = load_entry_agent()
        signature_time = "2026-05-07T07:11:00Z"
        snapshot = {
            "requested_symbol": "NQM6",
            "normalized_symbol": "NQ",
            "latest_price": 28840.0,
            "latest_bar_time": "2026-05-07T07:11:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 28838.0, "high": 28844.0, "low": 28836.0, "close": 28840.0},
            "step_2_1a": {
                "active_level": "PMH",
                "level_price": 28795.0,
                "last_interacted_liquidity": {"name": "PMH", "price": 28795.0, "side": "upper"},
            },
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT"},
            "step4": {
                "status": "READY",
                "state": {
                    "setup_direction": "SHORT",
                    "leg1_status": "COMPLETE",
                    "leg1_completed_at": "2026-05-07T06:49:00Z",
                    "leg1_reference_price": 28818.0,
                },
            },
            "step5": {
                "status": "READY",
                "state": {
                    "setup_direction": "SHORT",
                    "leg2_status": "COMPLETE",
                    "leg2_candidate_candle_time": signature_time,
                    "leg2_reference_price": 28840.0,
                    "leg2_candle": {"timestamp": signature_time, "open": 28838.0, "high": 28844.0, "low": 28836.0, "close": 28840.0},
                },
            },
            "step6": {
                "status": "ENTRY_CONFIRMED",
                "state": {
                    "setup_direction": "SHORT",
                    "entry_triggered": True,
                    "entry_candle": {"timestamp": signature_time, "open": 28838.0, "high": 28844.0, "low": 28836.0, "close": 28840.0},
                },
            },
        }

        original_state_path = entry_agent.STATE_PATH
        original_persistence_path = entry_agent.PERSISTENCE_STATE_PATH
        original_executor_path = entry_agent.EXECUTOR_STATE_PATH
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.PERSISTENCE_STATE_PATH = temp_path / "persistence_state.json"
            entry_agent.EXECUTOR_STATE_PATH = temp_path / "executor_state.json"
            entry_agent.STATE_PATH.write_text(json.dumps({"state_by_symbol": {"NQ": {}}}), encoding="utf-8")
            entry_agent.PERSISTENCE_STATE_PATH.write_text(
                json.dumps(
                    {
                        "trades": {
                            "T-820f152c": {
                                "trade_id": "T-820f152c",
                                "symbol": "NQM6",
                                "direction": "short",
                                "status": "closed",
                                "created_at": "2026-05-07T07:11:14.071881Z",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            entry_agent.EXECUTOR_STATE_PATH.write_text(json.dumps({"orders": {}}), encoding="utf-8")

            entry_agent.apply_consumed_entry_setup_guard(snapshot)
            self.assertEqual(entry_agent.decision_status(snapshot["step6"]), "WAIT")
            self.assertTrue(snapshot["step6"]["state"]["entry_setup_consumed"])

            rearmed_same_context = dict(snapshot)
            rearmed_same_context["step6"] = {
                "status": "ENTRY_CONFIRMED",
                "state": {
                    "setup_direction": "SHORT",
                    "entry_triggered": True,
                    "entry_candle": {"timestamp": signature_time, "open": 28838.0, "high": 28844.0, "low": 28836.0, "close": 28840.0},
                },
            }
            entry_agent.apply_consumed_entry_setup_guard(rearmed_same_context)
            self.assertEqual(entry_agent.decision_status(rearmed_same_context["step6"]), "WAIT")

            new_structure = dict(snapshot)
            new_structure["step4"] = {
                **snapshot["step4"],
                "state": {**snapshot["step4"]["state"], "leg1_completed_at": "2026-05-07T07:30:00Z"},
            }
            new_structure["step5"] = {
                **snapshot["step5"],
                "state": {**snapshot["step5"]["state"], "leg2_candidate_candle_time": "2026-05-07T07:35:00Z"},
            }
            new_structure["step6"] = {
                "status": "ENTRY_CONFIRMED",
                "state": {
                    "setup_direction": "SHORT",
                    "entry_triggered": True,
                    "entry_candle": {"timestamp": "2026-05-07T07:35:00Z", "open": 28850.0, "high": 28854.0, "low": 28846.0, "close": 28849.25},
                },
            }
            entry_agent.apply_consumed_entry_setup_guard(new_structure)
            self.assertEqual(entry_agent.decision_status(new_structure["step6"]), "CONFIRM")

        entry_agent.STATE_PATH = original_state_path
        entry_agent.PERSISTENCE_STATE_PATH = original_persistence_path
        entry_agent.EXECUTOR_STATE_PATH = original_executor_path

    def test_advanced_status_is_close_confirmed_only(self):
        entry_agent = load_entry_agent()
        current_time = "2026-05-07T13:45:00Z"
        current_candle = {
            "open": 50000.0,
            "high": 50020.0,
            "low": 49995.0,
            "close": 50015.0,
            "timestamp": current_time,
        }
        snapshot = {
            "latest_price": current_candle["close"],
            "latest_bar_time": current_time,
            "ohlc": current_candle,
            "ohlc_is_closed": False,
            "step_2_1a": {
                "active_level": "PMH",
                "level_price": 50000.0,
                "last_interacted_liquidity": {"name": "PMH", "price": 50000.0},
            },
            "step3": {"status": "ALLOW_STEP_4"},
            "step4": {
                "status": "READY",
                "next_step": "Step 5",
                "state": {
                    "setup_direction": "SHORT",
                    "leg1_status": "COMPLETE",
                    "leg1_state_locked": True,
                    "leg1_completed_at": current_time,
                    "leg1_reference_candle_time": current_time,
                    "latest_candle": current_candle,
                },
            },
            "step5": {
                "status": "READY",
                "next_step": "Step 6",
                "state": {
                    "setup_direction": "SHORT",
                    "leg2_status": "COMPLETE",
                    "leg2_candidate_candle_time": current_time,
                    "latest_candle": current_candle,
                },
            },
            "step6": {
                "status": "ENTRY_CONFIRMED",
                "state": {
                    "setup_direction": "SHORT",
                    "entry_triggered": True,
                    "entry_candidate": current_candle,
                    "entry_candle": current_candle,
                },
            },
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT"},
        }

        entry_agent.hide_unconfirmed_current_candle_advancement(snapshot)

        self.assertNotIn(entry_agent.current_step_from_snapshot(snapshot), {"Step 5", "Step 6"})
        self.assertEqual(entry_agent.decision_status(snapshot["step6"]), "WAIT")
        self.assertEqual(snapshot["step4"]["state"], {})
        self.assertEqual(snapshot["step5"]["state"], {})
        self.assertEqual(snapshot["step6"]["state"], {})


if __name__ == "__main__":
    unittest.main()
