import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class ResetPaperStateTests(unittest.TestCase):
    def setUp(self):
        sys.dont_write_bytecode = True
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.module = self._load_module()
        self.module.DATA_DIR = self.tmp_path
        self.module.BACKUP_DIR = self.tmp_path / "reset_backups"
        self.module.EXECUTOR_STATE_FILE = self.tmp_path / "executor_state.json"
        self.module.TRADE_MANAGER_STATE_FILE = self.tmp_path / "persistence_state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _load_module(self):
        spec = importlib.util.spec_from_file_location("reset_paper_state_test", ROOT / "reset_paper_state.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_reset_clears_executor_and_trade_manager_latches(self):
        self.module.EXECUTOR_STATE_FILE.write_text(json.dumps({
            "version": 1,
            "saved_at": "old",
            "orders": {"LIMIT-a1af6b8a": {"status": "closed"}},
            "positions": {"NQM6": {"qty": 0.0}},
        }), encoding="utf-8")
        self.module.TRADE_MANAGER_STATE_FILE.write_text(json.dumps({
            "system": {"version": "v1"},
            "trades": {"T-old": {"status": "error"}},
            "orders": {},
            "tradingview_atr": {"NQ": {"atr_value": 23.5}},
            "risk_state": {
                "kill_switch_active": True,
                "kill_switch_reason": "qa critical escalation",
                "daily_trade_count": 1,
                "daily_loss_count": 7,
                "trading_halted": True,
            },
            "event_log": [{"event_type": "old"}],
            "failure_state": {
                "qa_critical_count": 97,
                "execution_failure_count": 2,
                "halt_reason": "qa critical escalation",
            },
        }), encoding="utf-8")

        result = self.module.reset_paper_state()

        self.assertTrue(result["ok"])
        self.assertTrue(Path(result["executor_backup"]).exists())
        self.assertTrue(Path(result["trade_manager_backup"]).exists())

        executor_state = json.loads(self.module.EXECUTOR_STATE_FILE.read_text(encoding="utf-8"))
        self.assertEqual(executor_state["orders"], {})
        self.assertEqual(executor_state["positions"], {})

        manager_state = json.loads(self.module.TRADE_MANAGER_STATE_FILE.read_text(encoding="utf-8"))
        self.assertIsNotNone(manager_state["system"]["paper_reset_at"])
        self.assertEqual(manager_state["trades"], {})
        self.assertEqual(manager_state["event_log"], [])
        self.assertEqual(manager_state["tradingview_atr"], {})
        self.assertFalse(manager_state["risk_state"]["kill_switch_active"])
        self.assertFalse(manager_state["risk_state"]["trading_halted"])
        self.assertIsNone(manager_state["risk_state"]["kill_switch_reason"])
        self.assertEqual(manager_state["risk_state"]["daily_trade_count"], 0)
        self.assertEqual(manager_state["risk_state"]["daily_loss_count"], 0)
        self.assertEqual(manager_state["failure_state"]["qa_critical_count"], 0)
        self.assertEqual(manager_state["failure_state"]["execution_failure_count"], 0)
        self.assertIsNone(manager_state["failure_state"]["halt_reason"])


if __name__ == "__main__":
    unittest.main()
