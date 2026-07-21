import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class SymbolResolutionRegistryTests(unittest.TestCase):
    def setUp(self):
        sys.dont_write_bytecode = True
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.symbols = self._load_module()
        self.symbols.REFERENCE_DATE_OVERRIDE = date(2026, 6, 15)
        self.symbols.ATR_SNAPSHOT_PATH = self.tmp_path / "rithmic_atr_snapshot.json"
        self.symbols.RECENT_BARS_PATH = self.tmp_path / "rithmic_recent_bars.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _load_module(self):
        spec = importlib.util.spec_from_file_location("symbol_resolution_under_test", ROOT / "symbol_resolution.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _write_recent_bars(self, *symbols):
        payload = {"symbols": {symbol: [] for symbol in symbols}}
        self.symbols.RECENT_BARS_PATH.write_text(json.dumps(payload), encoding="utf-8")

    def test_registry_helpers_keep_active_front_month_defaults_after_june_2026_roll(self):
        self.assertEqual(
            self.symbols.get_default_listener_subscriptions(reference_date=date(2026, 6, 15)),
            [("CME", "NQU6"), ("CBOT", "YMU6")],
        )
        self.assertEqual(self.symbols.get_ui_roots(), ["NQ", "YM"])
        self.assertEqual(self.symbols.get_tick_size("NQ"), 0.25)
        self.assertEqual(self.symbols.get_tick_value("NQU6"), 5.0)
        self.assertEqual(self.symbols.get_tick_size("RTY"), 0.10)
        self.assertEqual(self.symbols.get_tick_value("RTYU6"), 5.0)
        self.assertEqual(self.symbols.get_point_value("RTY"), 50.0)
        self.assertEqual(self.symbols.get_tick_size("YM"), 1.0)
        self.assertEqual(self.symbols.get_tick_value("YMU6"), 5.0)
        self.assertEqual(self.symbols.get_point_value("YM"), 5.0)
        self.assertEqual(self.symbols.active_front_month_symbol("NQ", reference_date=date(2026, 6, 15)), "NQU6")
        self.assertEqual(self.symbols.active_front_month_symbol("RTY", reference_date=date(2026, 6, 15)), "RTYU6")
        self.assertEqual(self.symbols.active_front_month_symbol("YM", reference_date=date(2026, 6, 15)), "YMU6")

    def test_registry_helpers_keep_pre_rollover_june_2026_contracts_before_second_thursday(self):
        self.assertEqual(self.symbols.active_front_month_symbol("NQ", reference_date=date(2026, 6, 10)), "NQM6")
        self.assertEqual(self.symbols.active_front_month_symbol("RTY", reference_date=date(2026, 6, 10)), "RTYM6")
        self.assertEqual(self.symbols.active_front_month_symbol("YM", reference_date=date(2026, 6, 10)), "YMM6")
        self.assertEqual(
            self.symbols.get_default_listener_subscriptions(reference_date=date(2026, 6, 10)),
            [("CME", "NQM6"), ("CBOT", "YMM6")],
        )

    def test_backward_compatible_symbol_normalization_functions(self):
        self.assertEqual(self.symbols.canonicalize_symbol_input("CME_MINI:NQ1!"), "NQ")
        self.assertEqual(self.symbols.canonicalize_symbol_input("RTYM6"), "RTY")
        self.assertEqual(self.symbols.normalize_symbol_root("NQM6"), "NQ")
        self.assertEqual(self.symbols.normalize_symbol_root("RTY1!"), "RTY")

    def test_resolve_execution_symbol_uses_live_contracts_from_recent_bars(self):
        self._write_recent_bars("NQM6", "RTYM6")

        self.assertEqual(self.symbols.resolve_execution_symbol("NQ"), ("NQM6", "recent_bars"))
        self.assertEqual(self.symbols.resolve_execution_symbol("RTY"), ("RTYM6", "recent_bars"))

    def test_resolve_execution_symbol_prefers_active_ym_front_month_when_m_and_u_exist(self):
        self._write_recent_bars("YMM6", "YMU6")

        self.assertEqual(self.symbols.resolve_execution_symbol("YM"), ("YMU6", "recent_bars"))

    def test_resolve_execution_symbol_prefers_active_nq_front_month_when_m_and_u_exist(self):
        self._write_recent_bars("NQM6", "NQU6")

        self.assertEqual(self.symbols.resolve_execution_symbol("NQ"), ("NQU6", "recent_bars"))

    def test_resolve_execution_symbol_single_contract_recent_bars_behavior_is_unchanged(self):
        self._write_recent_bars("YMM6", "RTYM6")

        self.assertEqual(self.symbols.resolve_execution_symbol("YM"), ("YMM6", "recent_bars"))
        self.assertEqual(self.symbols.resolve_execution_symbol("RTY"), ("RTYM6", "recent_bars"))

    def test_explicit_replay_contract_request_preserves_historical_m_contract(self):
        self._write_recent_bars("NQM6", "YMM6")

        self.assertEqual(self.symbols.resolve_execution_symbol("NQM6"), ("NQM6", "recent_bars"))
        self.assertEqual(self.symbols.resolve_execution_symbol("YMM6"), ("YMM6", "recent_bars"))

    def test_resolve_execution_symbol_falls_back_to_live_front_month_after_rollover(self):
        self.assertEqual(self.symbols.resolve_execution_symbol("NQ"), ("NQU6", "registry_default"))
        self.assertEqual(self.symbols.resolve_execution_symbol("RTY"), ("RTYU6", "registry_default"))
        self.assertEqual(self.symbols.resolve_execution_symbol("YM"), ("YMU6", "registry_default"))
        self.assertNotEqual(self.symbols.resolve_execution_symbol("NQ")[0], "NQM6")
        self.assertNotEqual(self.symbols.resolve_execution_symbol("RTY")[0], "RTYM6")
        self.assertNotEqual(self.symbols.resolve_execution_symbol("YM")[0], "YMM6")

    def test_build_symbol_candidates_includes_root_and_contract_aliases(self):
        self._write_recent_bars("NQM6", "RTYM6")

        nq_candidates = self.symbols.build_symbol_candidates("NQ1!")
        rty_candidates = self.symbols.build_symbol_candidates("RTYM6")

        self.assertIn("NQ", nq_candidates)
        self.assertIn("NQM6", nq_candidates)
        self.assertIn("RTY", rty_candidates)
        self.assertIn("RTYM6", rty_candidates)

    def test_live_default_listener_subscriptions_match_expected_post_restart_cache_keys(self):
        subscriptions = self.symbols.get_default_listener_subscriptions(reference_date=date(2026, 6, 15))
        self.assertEqual([symbol for _, symbol in subscriptions], ["NQU6", "YMU6"])


if __name__ == "__main__":
    unittest.main()
