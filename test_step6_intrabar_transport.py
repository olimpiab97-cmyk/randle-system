import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent


class ListenerIntrabarTransportTests(unittest.TestCase):
    def setUp(self):
        sys.dont_write_bytecode = True
        self.env_patcher = patch.dict(os.environ, {}, clear=False)
        self.env_patcher.start()
        self.listener = self._load_listener()
        self.listener.step6_intrabar_paths_by_symbol.clear()
        self.listener.latest_price_by_symbol.clear()
        self.listener.latest_tick_time_by_symbol.clear()
        self.listener.latest_tick_monotonic_by_symbol.clear()

    def tearDown(self):
        self.env_patcher.stop()

    def _load_listener(self):
        spec = importlib.util.spec_from_file_location("rithmic_listener_intrabar_transport", ROOT / "rithmic_live_listener.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_duplicate_price_dedupe(self):
        self.listener.STEP6_INTRABAR_PATH_MAX_POINTS = 512
        self.listener.append_step6_intrabar_price_point("NQ", "2026-06-20T13:34:01.000Z", 100.0)
        self.listener.append_step6_intrabar_price_point("NQ", "2026-06-20T13:34:01.200Z", 100.0)
        self.listener.append_step6_intrabar_price_point("NQ", "2026-06-20T13:34:01.400Z", 100.25)

        payload = self.listener.build_step6_intrabar_path_payload("NQ")
        points = payload["current_minute"]["points"]
        self.assertEqual(points, [["2026-06-20T13:34:01.000Z", 100.0], ["2026-06-20T13:34:01.400Z", 100.25]])

    def test_buffer_cap_sets_truncated_and_stays_bounded(self):
        self.listener.STEP6_INTRABAR_PATH_MAX_POINTS = 3
        for index, price in enumerate((100.0, 100.25, 100.5, 100.75), start=1):
            self.listener.append_step6_intrabar_price_point("NQ", f"2026-06-20T13:34:0{index}.000Z", price)

        payload = self.listener.build_step6_intrabar_path_payload("NQ")
        bucket = payload["current_minute"]
        self.assertTrue(bucket["truncated"])
        self.assertEqual(bucket["max_points"], 3)
        self.assertEqual(len(bucket["points"]), 3)
        self.assertEqual(bucket["points"][-1], ["2026-06-20T13:34:04.000Z", 100.75])

    def test_minute_rollover_retains_current_and_previous_only(self):
        self.listener.append_step6_intrabar_price_point("NQ", "2026-06-20T13:34:01.000Z", 100.0)
        self.listener.append_step6_intrabar_price_point("NQ", "2026-06-20T13:35:00.000Z", 101.0)
        self.listener.append_step6_intrabar_price_point("NQ", "2026-06-20T13:36:00.000Z", 102.0)

        payload = self.listener.build_step6_intrabar_path_payload("NQ")
        self.assertEqual(payload["current_minute"]["minute"], "2026-06-20T13:36:00Z")
        self.assertEqual(payload["previous_minute"]["minute"], "2026-06-20T13:35:00Z")
        self.assertEqual(payload["previous_minute"]["points"], [["2026-06-20T13:35:00.000Z", 101.0]])

    def test_forward_price_to_executor_includes_intrabar_path_payload(self):
        captured = {}

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def fake_urlopen(request, timeout=0):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with patch.object(self.listener, "derive_executor_price_feed_status", return_value="LIVE"):
            with patch.object(self.listener.urllib.request, "urlopen", side_effect=fake_urlopen):
                ok, reason = self.listener.forward_price_to_executor(
                    "NQ",
                    100.25,
                    update_health=False,
                    tick_timestamp_utc="2026-06-20T13:34:01.000Z",
                    step6_intrabar_path={
                        "current_minute": {
                            "minute": "2026-06-20T13:34:00Z",
                            "points": [["2026-06-20T13:34:01.000Z", 100.25]],
                            "truncated": False,
                            "price_change_only": True,
                            "max_points": 512,
                        },
                        "previous_minute": None,
                    },
                )

        self.assertTrue(ok)
        self.assertIsNone(reason)
        self.assertIn("step6_intrabar_path", captured["payload"])
        self.assertEqual(captured["payload"]["step6_intrabar_path"]["current_minute"]["minute"], "2026-06-20T13:34:00Z")


class ExecutorIntrabarTransportTests(unittest.TestCase):
    def setUp(self):
        sys.dont_write_bytecode = True
        self.env_patcher = patch.dict(os.environ, {}, clear=False)
        self.env_patcher.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.executor = self._load_executor()
        self.executor.EXECUTOR_STATE_FILE = self.tmp_path / "executor_state.json"
        self.executor.TRADE_MANAGER_PERSISTENCE_FILE = self.tmp_path / "persistence_state.json"
        self.executor.DATA_DIR = self.tmp_path
        self.executor.ORDERS.clear()
        self.executor.POSITIONS.clear()
        self.executor.LAST_PRICES.clear()
        self.executor.LAST_PRICE_TIMESTAMPS.clear()
        self.executor.LAST_PRICE_LISTENER_TICK_IDS.clear()
        self.executor.LAST_PRICE_LISTENER_SEQUENCES.clear()
        self.executor.LAST_PRICE_EXECUTOR_SEQUENCES.clear()
        self.executor.CURRENT_1M_BARS.clear()
        self.executor.COMPLETED_1M_BARS.clear()
        self.executor.STEP6_INTRABAR_PATHS.clear()
        self.executor.EXECUTOR_STATE_LOADED = True
        self.executor.log = lambda msg: None
        self.executor.AUTO_RESTART_ENABLED = False
        self.executor.LISTENER_AUTO_RESTART_EXECUTION_ENABLED = False

    def tearDown(self):
        self.tmp.cleanup()
        self.env_patcher.stop()

    def _load_executor(self):
        spec = importlib.util.spec_from_file_location("executor_intrabar_transport", ROOT / "executor.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _price_payload(self):
        return {
            "symbol": "NQM6",
            "price": 27000.25,
            "tick_timestamp_utc": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
            "feed_status": "LIVE",
            "step6_intrabar_path": {
                "current_minute": {
                    "minute": "2026-06-20T13:34:00Z",
                    "points": [["2026-06-20T13:34:01.000Z", 27000.25], ["2026-06-20T13:34:02.000Z", 27000.5]],
                    "truncated": False,
                    "price_change_only": True,
                    "max_points": 512,
                },
                "previous_minute": {
                    "minute": "2026-06-20T13:33:00Z",
                    "points": [["2026-06-20T13:33:59.000Z", 26999.75]],
                    "truncated": False,
                    "price_change_only": True,
                    "max_points": 512,
                },
            },
        }

    def test_price_path_payload_does_not_alter_last_price_or_current_bar(self):
        client = self.executor.app.test_client()
        payload = self._price_payload()
        response = client.post("/price", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.executor.LAST_PRICES["NQM6"], 27000.25)
        self.assertIn("NQM6", self.executor.CURRENT_1M_BARS)
        self.assertEqual(self.executor.STEP6_INTRABAR_PATHS["NQM6"]["current_minute"]["minute"], "2026-06-20T13:34:00Z")

    def test_sync_snapshot_excludes_intrabar_path_by_default(self):
        client = self.executor.app.test_client()
        client.post("/price", json=self._price_payload())
        response = client.get("/sync_snapshot")
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("step6_intrabar_path", data["symbols"]["NQM6"])

    def test_sync_snapshot_includes_intrabar_path_only_on_opt_in(self):
        client = self.executor.app.test_client()
        client.post("/price", json=self._price_payload())
        response = client.get("/sync_snapshot?include_step6_intrabar_path=1")
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("step6_intrabar_path", data["symbols"]["NQM6"])
        self.assertEqual(
            data["symbols"]["NQM6"]["step6_intrabar_path"]["previous_minute"]["minute"],
            "2026-06-20T13:33:00Z",
        )


if __name__ == "__main__":
    unittest.main()
