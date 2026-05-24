import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENTRY_AGENT = ROOT / "EntryAgent"
if str(ENTRY_AGENT) not in sys.path:
    sys.path.insert(0, str(ENTRY_AGENT))

from step6_engine import evaluate_step6  # noqa: E402


def candle(open_price, high, low, close, **extra):
    payload = {"open": open_price, "high": high, "low": low, "close": close}
    payload.update(extra)
    return payload


def base_interaction(direction="SHORT", anchor=None, atr=10.0):
    return {
        "system_state": "REJECTION MODE ON",
        "trade_mode": "ON",
        "rejection_mode": "ON",
        "interaction_state": "ACTIVE",
        "setup_direction": direction,
        "step5_confirmed": True,
        "leg2_status": "VALIDATED",
        "structure_status": "VALID",
        "structure_valid": True,
        "active_step5_path": "5.1",
        "leg2_candle": anchor or candle(100.0, 100.5, 99.5, 100.0),
        "tick_size": 0.25,
        "atr_1m_14": atr,
        "events": [],
    }


class Step6ExtendedRetraceTests(unittest.TestCase):
    def test_short_extended_retrace_qualifies_and_prices_from_wick_high(self):
        result = evaluate_step6(base_interaction("SHORT"), candle(105.75, 106.0, 104.5, 106.0))
        state = result["state"]
        self.assertEqual(result["status"], "WAIT")
        self.assertTrue(state["extended_retrace_entry_valid"])
        self.assertEqual(state["extended_retrace_entry_price"], 103.0)
        self.assertEqual(state["extended_retrace_extension_ticks"], 24.0)
        self.assertEqual(state["extended_retrace_extension_atr_percent"], 60.0)
        self.assertEqual(state["extended_retrace_expires_at_candle"], 3)
        self.assertEqual(state["extended_retrace_invalidation_price"], 106.0)

    def test_long_extended_retrace_qualifies_and_prices_from_wick_low(self):
        result = evaluate_step6(base_interaction("LONG"), candle(94.25, 95.5, 94.0, 94.0))
        state = result["state"]
        self.assertEqual(result["status"], "WAIT")
        self.assertTrue(state["extended_retrace_entry_valid"])
        self.assertEqual(state["extended_retrace_entry_price"], 97.0)
        self.assertEqual(state["extended_retrace_extension_ticks"], 24.0)
        self.assertEqual(state["extended_retrace_extension_atr_percent"], 60.0)
        self.assertEqual(state["extended_retrace_invalidation_price"], 94.0)

    def test_extension_below_half_atr_does_not_create_extended_retrace(self):
        result = evaluate_step6(base_interaction("SHORT", atr=10.0), candle(104.0, 104.75, 103.0, 104.75))
        state = result["state"]
        self.assertFalse(state["extended_retrace_entry_valid"])
        self.assertIsNone(state["extended_retrace_entry_price"])

    def test_extended_retrace_expires_after_three_candles_without_fill(self):
        first = evaluate_step6(base_interaction("SHORT"), candle(105.75, 106.0, 104.5, 106.0))
        state = first["state"]
        for _ in range(3):
            result = evaluate_step6(state, candle(101.0, 102.75, 100.0, 101.0))
            state = result["state"]
        self.assertEqual(result["status"], "WAIT")
        self.assertFalse(state["extended_retrace_entry_valid"])
        self.assertTrue(state["extended_retrace_expired"])
        self.assertIn("expired after 3 candles", result["reason"])

    def test_extended_retrace_invalidation_remains_step6_wick_extreme(self):
        first = evaluate_step6(base_interaction("SHORT"), candle(105.75, 106.0, 104.5, 106.0))
        result = evaluate_step6(first["state"], candle(105.5, 106.25, 104.0, 106.25))
        state = result["state"]
        self.assertFalse(state["extended_retrace_entry_valid"])
        self.assertTrue(state["extended_retrace_invalidated"])
        self.assertEqual(state["extended_retrace_invalidation_price"], 106.0)
        self.assertIn("Step 6 wick extreme", result["reason"])

    def test_existing_immediate_entry_keeps_first_valid_trigger_priority(self):
        result = evaluate_step6(
            base_interaction("SHORT", anchor=candle(100.0, 102.0, 99.0, 100.0)),
            candle(105.0, 106.0, 99.5, 103.0),
        )
        self.assertEqual(result["status"], "ENTRY_CONFIRMED")
        self.assertEqual(result["entry_type"], "Large Wick Sweep")
        self.assertEqual(result["entry_type_number"], 1)
        self.assertEqual(result["entry_type_name"], "Sweep Entry")
        self.assertEqual(result["entry_model"], "large_wick_sweep")
        self.assertTrue(result["state"]["extended_retrace_entry_valid"])
        self.assertNotEqual(result["entry_type"], "Extended Retrace Entry")

    def test_short_override_blocks_worse_immediate_reclaim_using_dry_run_values(self):
        result = evaluate_step6(
            base_interaction("SHORT", anchor=candle(28981.25, 29044.75, 28981.25, 29043.5), atr=45.642857142857146),
            candle(29042.5, 29068.0, 29041.0, 29052.5),
        )
        state = result["state"]
        self.assertEqual(result["status"], "ENTRY_CONFIRMED")
        self.assertEqual(result["entry_type"], "Extended Retrace Entry")
        self.assertTrue(state["extended_retrace_entry_valid"])
        self.assertEqual(state["extended_retrace_entry_price"], 29055.75)
        self.assertTrue(state["extended_retrace_entry_active"])
        self.assertFalse(state["extended_retrace_pending"])
        self.assertTrue(state["extended_retrace_blocked_immediate_entry"])
        self.assertTrue(state["extended_retrace_intrabar_fill"])
        self.assertIn("worse than retrace entry", state["extended_retrace_block_reason"])
        self.assertTrue(state.get("entry_triggered", False))

    def test_short_override_fill_confirms_extended_retrace_entry_intrabar(self):
        result = evaluate_step6(
            base_interaction("SHORT", anchor=candle(28981.25, 29044.75, 28981.25, 29043.5), atr=45.642857142857146),
            candle(29042.5, 29068.0, 29041.0, 29052.5),
        )
        self.assertEqual(result["status"], "ENTRY_CONFIRMED")
        self.assertEqual(result["entry_type"], "Extended Retrace Entry")
        self.assertEqual(result["entry_price"], 29055.75)

    def test_short_override_expires_after_three_unfilled_candles(self):
        state = base_interaction("SHORT", anchor=candle(28981.25, 29044.75, 28981.25, 29043.5), atr=45.642857142857146)
        state.update(
            {
                "extended_retrace_entry_valid": True,
                "extended_retrace_entry_price": 29055.75,
                "extended_retrace_entry_active": True,
                "extended_retrace_pending": True,
                "extended_retrace_invalidation_price": 29068.0,
                "extended_retrace_candles_elapsed": 0,
                "current_sc": state["leg2_candle"],
            }
        )
        for _ in range(3):
            result = evaluate_step6(state, candle(29050.0, 29054.0, 29030.0, 29040.0))
            state = result["state"]
        self.assertEqual(result["status"], "WAIT")
        self.assertFalse(state["extended_retrace_entry_valid"])
        self.assertTrue(state["extended_retrace_expired"])
        self.assertFalse(state.get("entry_triggered", False))

    def test_long_override_blocks_worse_immediate_reclaim(self):
        result = evaluate_step6(
            base_interaction("LONG", anchor=candle(100.0, 100.5, 99.5, 100.0), atr=10.0),
            candle(94.5, 101.0, 94.0, 98.0),
        )
        state = result["state"]
        self.assertEqual(result["status"], "ENTRY_CONFIRMED")
        self.assertEqual(result["entry_type"], "Extended Retrace Entry")
        self.assertTrue(state["extended_retrace_entry_valid"])
        self.assertEqual(state["extended_retrace_entry_price"], 97.0)
        self.assertTrue(state["extended_retrace_blocked_immediate_entry"])
        self.assertFalse(state["extended_retrace_pending"])
        self.assertTrue(state["extended_retrace_intrabar_fill"])

    def test_immediate_step6_executes_when_reclaim_close_is_at_or_better_than_retrace(self):
        result = evaluate_step6(
            base_interaction("SHORT", anchor=candle(100.0, 102.0, 99.0, 100.0), atr=10.0),
            candle(105.0, 106.0, 99.5, 103.0),
        )
        self.assertEqual(result["status"], "ENTRY_CONFIRMED")
        self.assertEqual(result["entry_type"], "Large Wick Sweep")
        self.assertEqual(result["entry_model"], "large_wick_sweep")
        self.assertFalse(result["state"].get("extended_retrace_blocked_immediate_entry"))

    def test_small_wick_sweep_classifies_as_small_wick_reclaim(self):
        result = evaluate_step6(
            base_interaction("LONG", anchor=candle(100.0, 101.0, 100.0, 100.5), atr=20.0),
            candle(100.0, 102.0, 99.75, 100.5),
        )
        self.assertEqual(result["status"], "ENTRY_CONFIRMED")
        self.assertEqual(result["entry_type_number"], 1)
        self.assertEqual(result["entry_type_name"], "Sweep Entry")
        self.assertEqual(result["entry_type"], "Small Wick Reclaim")
        self.assertEqual(result["entry_model"], "small_wick_reclaim")
        self.assertIn("Small Wick Reclaim", result["reason"])

    def test_large_wick_sweep_requires_sixty_percent_reclaim(self):
        failed = evaluate_step6(
            base_interaction("SHORT", anchor=candle(100.0, 102.0, 99.0, 100.0), atr=20.0),
            candle(105.0, 106.0, 99.5, 104.0),
        )
        passed = evaluate_step6(
            base_interaction("SHORT", anchor=candle(100.0, 102.0, 99.0, 100.0), atr=20.0),
            candle(105.0, 106.0, 99.5, 103.0),
        )
        self.assertNotEqual(failed["status"], "ENTRY_CONFIRMED")
        self.assertEqual(passed["status"], "ENTRY_CONFIRMED")
        self.assertEqual(passed["entry_type"], "Large Wick Sweep")
        self.assertEqual(passed["entry_model"], "large_wick_sweep")

    def test_double_wick_rejection_remains_type_2(self):
        result = evaluate_step6(
            base_interaction("SHORT", anchor=candle(100.0, 105.0, 99.0, 100.0), atr=20.0),
            candle(103.0, 103.0, 99.5, 99.75),
        )
        self.assertEqual(result["status"], "ENTRY_CONFIRMED")
        self.assertEqual(result["entry_type"], "Double Wick Rejection")
        self.assertEqual(result["entry_type_number"], 2)
        self.assertEqual(result["entry_type_name"], "Double Wick Rejection")
        self.assertEqual(result["entry_model"], "double_wick_rejection")

    def test_extended_retrace_remains_type_3(self):
        result = evaluate_step6(
            base_interaction("SHORT", anchor=candle(28981.25, 29044.75, 28981.25, 29043.5), atr=45.642857142857146),
            candle(29042.5, 29068.0, 29041.0, 29052.5),
        )
        self.assertEqual(result["status"], "ENTRY_CONFIRMED")
        self.assertEqual(result["entry_type"], "Extended Retrace Entry")
        self.assertEqual(result["entry_type_number"], 3)
        self.assertEqual(result["entry_type_name"], "Extended Retrace Entry")
        self.assertEqual(result["entry_model"], "extended_retrace_entry")


if __name__ == "__main__":
    unittest.main()
