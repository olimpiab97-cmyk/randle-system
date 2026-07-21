import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FORMULA = "wilder_rma_14"
FORMULA_VERSION = "wilder_rma_14_v1"
EPOCH = "test-listener-epoch"
BAR_ID = "bar-0644"
ATR_ID = "atr-0644"


def load_module(name, path):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def canonical_record(value=12.345678901234):
    return {
        "record_type": "canonical_rithmic_atr",
        "atr_record_id": ATR_ID,
        "symbol_root": "NQ",
        "contract_symbol": "NQU6",
        "timeframe": "1m",
        "period": 14,
        "formula": FORMULA,
        "formula_version": FORMULA_VERSION,
        "bar_id": BAR_ID,
        "finalized_candle_bar_id": BAR_ID,
        "candle_minute": "2026-07-14T13:44:00Z",
        "previous_close": 52840.0,
        "high": 52860.0,
        "low": 52830.0,
        "true_range": 30.0,
        "previous_atr": 11.0,
        "updated_raw_atr": value,
        "atr_value": value,
        "atr_source": "rithmic_exchange_time_rma14",
        "atr_bar_timestamp": "2026-07-14T13:44:00Z",
        "last_included_bar": "2026-07-14T13:44:00Z",
        "last_included_bar_id": BAR_ID,
        "ready": True,
        "warmup_status": "ready_continuation",
        "warmup_true_range_count": 30,
        "warmup_required_true_range_count": 14,
        "durable_commit_timestamp_utc": "2026-07-14T13:45:00.001Z",
        "trading_availability_timestamp_utc": "2026-07-14T13:45:00.002Z",
        "listener_source_sha256": "listener-hash",
        "builder_contract_version": "exchange_time_v1",
        "atr_authority_epoch_id": EPOCH,
    }


def canonical_bar(record=None):
    return {
        "symbol": "NQU6",
        "contract_symbol": "NQU6",
        "timestamp": "2026-07-14T13:44:00Z",
        "open": 52840.0,
        "high": 52860.0,
        "low": 52830.0,
        "close": 52855.0,
        "status": "FINAL",
        "bar_id": BAR_ID,
        "builder_contract_version": "exchange_time_v1",
        "canonical_atr": copy.deepcopy(record or canonical_record()),
    }


class CanonicalAtrAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        entry_agent_dir = str(ROOT / "EntryAgent")
        if entry_agent_dir not in sys.path:
            sys.path.insert(0, entry_agent_dir)
        cls.entry_agent = load_module(
            "entry_agent_atr_authority_under_test",
            ROOT / "EntryAgent" / "entry_agent.py",
        )
        cls.executor = load_module(
            "executor_atr_authority_under_test",
            ROOT / "executor.py",
        )
        cls.manager = load_module(
            "trade_manager_atr_authority_under_test",
            ROOT / "Engines" / "trade_manager.py",
        )

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        root = Path(self.tempdir.name)
        self.recent_path = root / "rithmic_recent_bars.json"
        self.health_path = root / "rithmic_feed_health.json"
        self.write_authority()
        self.entry_agent.RITHMIC_RECENT_BARS_PATH = self.recent_path
        self.entry_agent.RITHMIC_FEED_HEALTH_PATH = self.health_path
        self.executor.RITHMIC_RECENT_BARS_FILE = self.recent_path
        self.executor.RITHMIC_FEED_HEALTH_FILE = self.health_path
        self.manager.RITHMIC_RECENT_BARS_FILE = self.recent_path
        self.manager.RITHMIC_FEED_HEALTH_FILE = self.health_path

    def write_authority(self, record=None):
        self.recent_path.write_text(
            json.dumps({"symbols": {"NQU6": [canonical_bar(record)]}}),
            encoding="utf-8",
        )
        self.health_path.write_text(
            json.dumps({"listener_runtime": {"atr_authority_epoch_id": EPOCH}}),
            encoding="utf-8",
        )

    def test_entry_agent_executor_and_trade_manager_read_identical_identity(self):
        entry = self.entry_agent.load_rithmic_atr_snapshot("NQ")
        executor = self.executor.fetch_canonical_rithmic_atr_snapshot("NQ")
        manager = self.manager.fetch_trade_entry_atr_snapshot("NQ")

        for snapshot in (entry, executor, manager):
            self.assertEqual(snapshot["atr_value"], canonical_record()["updated_raw_atr"])
            self.assertEqual(snapshot["atr_record_id"], ATR_ID)
            self.assertEqual(snapshot.get("atr_bar_id", snapshot.get("bar_id")), BAR_ID)
            self.assertEqual(snapshot["canonical_atr"], canonical_record())

    def test_no_tradingview_atr_fallback_in_any_selection_path(self):
        self.assertIsNone(
            self.entry_agent.atr_from_snapshot(
                {"atr": None, "tv_context": {"atr_1m_14": 999.0}}
            )
        )
        original_executor_tv = self.executor.fetch_tradingview_atr_snapshot
        original_manager_tv = self.manager.fetch_tradingview_atr_snapshot
        self.executor.fetch_tradingview_atr_snapshot = lambda *args, **kwargs: self.fail(
            "Executor consulted TradingView ATR"
        )
        self.manager.fetch_tradingview_atr_snapshot = lambda *args, **kwargs: self.fail(
            "Trade Manager consulted TradingView ATR"
        )
        try:
            self.assertEqual(self.executor.select_snapshot_atr("NQ")["atr_record_id"], ATR_ID)
            self.assertEqual(self.manager.select_atr_snapshot("NQ")["atr_record_id"], ATR_ID)
        finally:
            self.executor.fetch_tradingview_atr_snapshot = original_executor_tv
            self.manager.fetch_tradingview_atr_snapshot = original_manager_tv

    def test_missing_or_wrong_epoch_canonical_record_fails_closed(self):
        self.health_path.write_text(
            json.dumps({"listener_runtime": {"atr_authority_epoch_id": "new-epoch"}}),
            encoding="utf-8",
        )
        self.assertIsNone(self.entry_agent.load_rithmic_atr_snapshot("NQ"))
        self.assertFalse(self.executor.fetch_canonical_rithmic_atr_snapshot("NQ")["ok"])
        with self.assertRaisesRegex(ValueError, "CANONICAL_RITHMIC_ATR_NOT_READY"):
            self.manager.fetch_trade_entry_atr_snapshot("NQ")

    def test_trade_manager_requires_exact_supplied_identity_and_pins_it(self):
        authority = self.manager.fetch_trade_entry_atr_snapshot("NQ")
        packet = {
            "symbol": "NQ",
            "direction": "long",
            "position_size": 2,
            "canonical_atr": copy.deepcopy(authority["canonical_atr"]),
        }
        self.manager.validate_supplied_canonical_atr(packet, authority)
        trade = self.manager.create_trade_state(packet, authority, "NQ", "NQU6")
        self.assertEqual(trade["atr_record_id"], ATR_ID)
        self.assertEqual(trade["atr_bar_id"], BAR_ID)
        self.assertEqual(trade["atr_value"], canonical_record()["updated_raw_atr"])
        self.assertEqual(trade["canonical_atr"], canonical_record())

        changed_packet = copy.deepcopy(packet)
        changed_packet["canonical_atr"]["atr_record_id"] = "different"
        with self.assertRaisesRegex(ValueError, "ATR_IDENTITY_MISMATCH"):
            self.manager.validate_supplied_canonical_atr(changed_packet, authority)

        previous = {"trades": {"T-1": {**trade, "trade_id": "T-1", "status": "active"}}}
        next_trade = copy.deepcopy(previous["trades"]["T-1"])
        next_trade["atr_value"] = 999.0
        next_trade["atr_record_id"] = "replacement"
        next_state = {"trades": {"T-1": next_trade}, "event_log": []}
        self.assertTrue(
            self.manager.merge_trade_state_for_persistence(previous, next_state, "test")
        )
        self.assertEqual(next_state["trades"]["T-1"]["atr_value"], trade["atr_value"])
        self.assertEqual(next_state["trades"]["T-1"]["atr_record_id"], ATR_ID)

        closed_previous = copy.deepcopy(previous)
        closed_previous["trades"]["T-1"]["status"] = "closed"
        closed_next = copy.deepcopy(next_state)
        closed_next["trades"]["T-1"]["status"] = "closed"
        closed_next["trades"]["T-1"]["canonical_atr"] = None
        self.assertTrue(
            self.manager.merge_trade_state_for_persistence(
                closed_previous, closed_next, "closed-trade-test"
            )
        )
        self.assertEqual(
            closed_next["trades"]["T-1"]["canonical_atr"],
            trade["canonical_atr"],
        )

    def test_existing_risk_distance_and_tick_rounding_formulas_are_unchanged(self):
        raw_atr = 26.72450295
        self.assertEqual(self.manager.calculate_atr_distance(raw_atr), 27.0)
        self.assertEqual(self.manager.calculate_atr_distance(raw_atr, 0.5), 14.0)
        levels = self.manager.derive_trade_levels(30352.0, "NQU6", "long", raw_atr)
        self.assertEqual(levels["original_stop"], 30325.0)
        self.assertEqual(levels["tp1_price"], 30379.0)
        self.assertEqual(levels["be_trigger"], 30366.0)

    def test_command_center_uses_canonical_readiness_endpoint(self):
        source = (ROOT / "command_center.html").read_text(encoding="utf-8")
        self.assertIn('/debug/canonical/atr_status', source)
        self.assertIn('CANONICAL_RITHMIC_ATR_NOT_READY', source)
        self.assertIn('canonical_atr: item && item.canonical_atr', source)


if __name__ == "__main__":
    unittest.main()
