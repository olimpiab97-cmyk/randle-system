import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class SymbolResolutionRegistryTests(unittest.TestCase):
    def setUp(self):
        sys.dont_write_bytecode = True
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.symbols = self._load_module()
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

    def test_registry_helpers_keep_current_nq_and_rty_defaults(self):
        self.assertEqual(
            self.symbols.get_default_listener_subscriptions(),
            [("CME", "NQM6"), ("CME", "RTYM6"), ("CBOT", "YMM6")],
        )
        self.assertEqual(self.symbols.get_ui_roots(), ["NQ", "RTY", "YM"])
        self.assertEqual(self.symbols.get_tick_size("NQ"), 0.25)
        self.assertEqual(self.symbols.get_tick_value("NQM6"), 5.0)
        self.assertEqual(self.symbols.get_tick_size("RTY"), 0.10)
        self.assertEqual(self.symbols.get_tick_value("RTYM6"), 5.0)
        self.assertEqual(self.symbols.get_point_value("RTY"), 50.0)
        self.assertEqual(self.symbols.get_tick_size("YM"), 1.0)
        self.assertEqual(self.symbols.get_tick_value("YMM6"), 5.0)
        self.assertEqual(self.symbols.get_point_value("YM"), 5.0)

    def test_backward_compatible_symbol_normalization_functions(self):
        self.assertEqual(self.symbols.canonicalize_symbol_input("CME_MINI:NQ1!"), "NQ")
        self.assertEqual(self.symbols.canonicalize_symbol_input("RTYM6"), "RTY")
        self.assertEqual(self.symbols.normalize_symbol_root("NQM6"), "NQ")
        self.assertEqual(self.symbols.normalize_symbol_root("RTY1!"), "RTY")

    def test_resolve_execution_symbol_uses_live_contracts_from_recent_bars(self):
        self._write_recent_bars("NQM6", "RTYM6")

        self.assertEqual(self.symbols.resolve_execution_symbol("NQ"), ("NQM6", "recent_bars"))
        self.assertEqual(self.symbols.resolve_execution_symbol("RTY"), ("RTYM6", "recent_bars"))

    def test_build_symbol_candidates_includes_root_and_contract_aliases(self):
        self._write_recent_bars("NQM6", "RTYM6")

        nq_candidates = self.symbols.build_symbol_candidates("NQ1!")
        rty_candidates = self.symbols.build_symbol_candidates("RTYM6")

        self.assertIn("NQ", nq_candidates)
        self.assertIn("NQM6", nq_candidates)
        self.assertIn("RTY", rty_candidates)
        self.assertIn("RTYM6", rty_candidates)


if __name__ == "__main__":
    unittest.main()
