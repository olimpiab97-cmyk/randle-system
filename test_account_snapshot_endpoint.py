import importlib.util
import sys
import tempfile
import unittest
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class AccountSnapshotEndpointTests(unittest.TestCase):
    def setUp(self):
        sys.dont_write_bytecode = True
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.executor = self._load_executor()
        self.executor.DATA_DIR = self.tmp_path
        self.executor.ACCOUNT_SNAPSHOT_FILE = self.tmp_path / "paper_account_snapshot.json"
        self.client = self.executor.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def _load_executor(self):
        spec = importlib.util.spec_from_file_location("executor_account_snapshot_under_test", ROOT / "executor.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_account_snapshot_unavailable_returns_safe_false_payload(self):
        response = self.client.get("/account_snapshot")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["ok"], False)
        self.assertEqual(data["source"], "paper_account")
        self.assertEqual(data["reason"], "paper_account_snapshot_unavailable")
        self.assertIsNone(data["balance"])
        self.assertIsNone(data["cash_balance"])
        self.assertIsNone(data["net_liq"])
        self.assertIsNone(data["unrealized_pnl"])
        self.assertIsNone(data["realized_pnl"])
        self.assertIsNone(data["updated_at"])

    def test_account_snapshot_returns_only_safe_telemetry_fields(self):
        self.executor.ACCOUNT_SNAPSHOT_FILE.write_text(
            json.dumps({
                "balance": "25000.50",
                "cash_balance": 24900,
                "net_liq": 25125.25,
                "unrealized_pnl": 125.25,
                "realized_pnl": -10,
                "updated_at": "2026-05-23T12:00:00Z",
                "account_id": "SHOULD_NOT_LEAK",
            }),
            encoding="utf-8",
        )

        response = self.client.get("/account_snapshot")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data, {
            "ok": True,
            "source": "paper_account",
            "balance": 25000.5,
            "cash_balance": 24900.0,
            "net_liq": 25125.25,
            "unrealized_pnl": 125.25,
            "realized_pnl": -10.0,
            "updated_at": "2026-05-23T12:00:00Z",
        })


if __name__ == "__main__":
    unittest.main()
