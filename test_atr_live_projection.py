import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
EPOCH = "live-projection-epoch"


def load_module(name, path):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class AtrLiveProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manager = load_module("trade_manager_atr_projection_test", ROOT / "Engines" / "trade_manager.py")
        sys.path.insert(0, str(ROOT / "EntryAgent"))
        cls.entry = load_module("entry_agent_atr_projection_test", ROOT / "EntryAgent" / "entry_agent.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.recent = root / "rithmic_recent_bars.json"
        self.health = root / "rithmic_feed_health.json"
        self.manager.RITHMIC_RECENT_BARS_FILE = str(self.recent)
        self.manager.RITHMIC_FEED_HEALTH_FILE = str(self.health)
        self.entry.RITHMIC_RECENT_BARS_PATH = self.recent
        self.entry.RITHMIC_FEED_HEALTH_PATH = self.health
        self.now = datetime(2026, 7, 15, 19, 30, tzinfo=timezone.utc)

    def record(self, minute="2026-07-15T19:29:00Z", *, ready=False, count=8, value=None, contract="NQU6"):
        bar_id = f"bar-{contract}-{minute}"
        return {
            "record_type": "canonical_rithmic_atr",
            "symbol_root": "NQ",
            "contract_symbol": contract,
            "timeframe": "1m",
            "period": 14,
            "formula": "wilder_rma_14",
            "formula_version": "wilder_rma_14_v1",
            "atr_source": "rithmic_exchange_time_rma14",
            "atr_record_id": f"atr-{contract}-{minute}",
            "bar_id": bar_id,
            "finalized_candle_bar_id": bar_id,
            "last_included_bar_id": bar_id,
            "candle_minute": minute,
            "last_included_bar": minute,
            "builder_contract_version": "exchange_time_v1",
            "atr_authority_epoch_id": EPOCH,
            "ready": ready,
            "updated_raw_atr": value,
            "atr_value": value,
            "warmup_status": "ready_continuation" if ready else "insufficient_authoritative_finalized_history",
            "warmup_true_range_count": count,
            "warmup_required_true_range_count": 14,
        }

    def write(self, record, *, session="2026-07-15", key=None, subscribed="NQU6", tv_atr=None):
        contract = key or record["contract_symbol"]
        bar = {
            "timestamp": record["candle_minute"],
            "symbol": contract,
            "contract_symbol": contract,
            "session_date": session,
            "status": "FINAL",
            "bar_id": record["bar_id"],
            "builder_contract_version": "exchange_time_v1",
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "canonical_atr": record,
        }
        self.recent.write_text(json.dumps({"symbols": {contract: [bar]}, "tradingview_atr": tv_atr}), encoding="utf-8")
        self.health.write_text(json.dumps({"listener_runtime": {
            "atr_authority_epoch_id": EPOCH,
            "subscribed_contracts": [{"contract_symbol": subscribed}],
        }}), encoding="utf-8")

    def test_current_contract_warmup_projects_through_manager_and_entry(self):
        record = self.record(count=8)
        self.write(record)
        manager = self.manager.build_canonical_atr_status_for_symbol("NQ", reference_time=self.now)
        entry_record = self.entry.load_rithmic_atr_observation("NQ", reference_time=self.now)
        entry = self.entry.canonical_atr_status_projection(entry_record)
        self.assertEqual(manager["contract_symbol"], "NQU6")
        self.assertEqual(manager["included_bar_count"], 8)
        self.assertEqual(manager["last_included_bar"], record["last_included_bar"])
        self.assertEqual(entry["atr_included_bar_count"], manager["included_bar_count"])
        self.assertEqual(entry["atr_observation_last_included_bar"], manager["last_included_bar"])

    def test_locked_entry_status_keeps_current_atr_projection(self):
        record = self.record(ready=True, count=14, value=12.5)
        original = self.entry.load_rithmic_atr_observation
        self.entry.load_rithmic_atr_observation = lambda _symbol: record
        try:
            status = self.entry.locked_entry_status(
                "NQ",
                {"requested_symbol": "NQ", "ohlc": {}, "atr": {"canonical_atr": record}},
                "SESSION_CLOSED",
                "closed",
            )
        finally:
            self.entry.load_rithmic_atr_observation = original
        self.assertTrue(status["canonical_atr_ready"])
        self.assertEqual(status["atr_1m_14"], 12.5)
        self.assertEqual(status["atr_contract_symbol"], "NQU6")
        self.assertEqual(status["atr_included_bar_count"], 14)

    def test_completed_minute_advances_projection(self):
        first = self.record(count=8)
        self.write(first)
        before = self.manager.build_canonical_atr_status_for_symbol("NQ", reference_time=self.now)
        second = self.record("2026-07-15T19:30:00Z", count=9)
        self.write(second)
        after = self.manager.build_canonical_atr_status_for_symbol("NQ", reference_time=self.now + timedelta(minutes=1))
        self.assertEqual(before["included_bar_count"], 8)
        self.assertEqual(after["included_bar_count"], 9)
        self.assertGreater(after["last_included_bar"], before["last_included_bar"])

    def test_stale_prior_session_is_rejected(self):
        self.write(self.record(), session="2026-07-14")
        status = self.manager.build_canonical_atr_status_for_symbol("NQ", reference_time=self.now)
        self.assertEqual(status["error"], "CANONICAL_RITHMIC_ATR_STALE_SESSION")
        self.assertIsNone(self.entry.load_rithmic_atr_observation("NQ", reference_time=self.now))

    def test_stale_prior_contract_is_rejected(self):
        record = self.record(contract="NQM6")
        self.write(record, key="NQM6", subscribed="NQU6")
        status = self.manager.build_canonical_atr_status_for_symbol("NQ", reference_time=self.now)
        self.assertEqual(status["status"], "not_ready")
        self.assertIsNone(status["contract_symbol"])
        self.assertIsNone(self.entry.load_rithmic_atr_observation("NQ", reference_time=self.now))

    def test_no_tradingview_fallback_and_null_before_threshold(self):
        self.write(self.record(count=13), tv_atr={"NQ": {"atr_value": 999.0}})
        status = self.manager.build_canonical_atr_status_for_symbol("NQ", reference_time=self.now)
        self.assertFalse(status["ready"])
        self.assertIsNone(status["atr_value"])
        self.assertEqual(status["included_bar_count"], 13)
        self.assertEqual(status["required_bar_count"], 14)

    def test_ready_value_continues_updating_after_threshold(self):
        seeded = self.record(ready=True, count=14, value=12.5)
        self.write(seeded)
        first = self.manager.build_canonical_atr_status_for_symbol("NQ", reference_time=self.now)
        continued = self.record("2026-07-15T19:30:00Z", ready=True, count=15, value=12.75)
        self.write(continued)
        second = self.manager.build_canonical_atr_status_for_symbol("NQ", reference_time=self.now + timedelta(minutes=1))
        self.assertEqual(first["atr_value"], 12.5)
        self.assertEqual(second["atr_value"], 12.75)
        self.assertEqual(second["readiness_reason"], "ready_continuation")

    def test_command_center_maps_canonical_progress_fields(self):
        source = (ROOT / "command_center.html").read_text(encoding="utf-8")
        self.assertIn("/debug/canonical/atr_status", source)
        self.assertIn("item.included_bar_count", source)
        self.assertIn("item.required_bar_count", source)
        self.assertIn("item.readiness_reason", source)
        refresh = source[source.index("async function refreshTvAtrStatuses"):]
        self.assertNotIn("/debug/tradingview/atr_status", refresh[:800])


if __name__ == "__main__":
    unittest.main()
