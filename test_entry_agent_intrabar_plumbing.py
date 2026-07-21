import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent


class EntryAgentIntrabarPlumbingTests(unittest.TestCase):
    def _load_module(self, name, relative_path):
        entry_agent_dir = ROOT / "EntryAgent"
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        if str(entry_agent_dir) not in sys.path:
            sys.path.insert(0, str(entry_agent_dir))
        spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_market_feed_requests_opt_in_snapshot_url_and_preserves_path(self):
        market_feed = self._load_module("entry_agent_market_feed_intrabar", Path("EntryAgent") / "market_feed.py")

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {
                        "symbols": {
                            "NQM6": {
                                "last_price": 27000.25,
                                "current_1m_bar": {
                                    "open": 27000.0,
                                    "high": 27000.5,
                                    "low": 26999.75,
                                    "close": 27000.25,
                                },
                                "step6_intrabar_path": {
                                    "current_minute": {
                                        "minute": "2026-06-20T13:34:00Z",
                                        "points": [["2026-06-20T13:34:01.000Z", 27000.25]],
                                        "truncated": False,
                                        "price_change_only": True,
                                        "max_points": 512,
                                    },
                                    "previous_minute": None,
                                },
                            }
                        }
                    }
                ).encode("utf-8")

        opened = {}

        def fake_urlopen(url, timeout=0):
            opened["url"] = url
            return FakeResponse()

        with patch.object(market_feed, "urlopen", side_effect=fake_urlopen):
            snapshot = market_feed.get_latest_market_snapshot("NQ")

        self.assertEqual(
            opened["url"],
            "http://localhost:6001/sync_snapshot?include_step6_intrabar_path=1",
        )
        self.assertIn("step6_intrabar_path", snapshot)
        self.assertEqual(
            snapshot["step6_intrabar_path"]["current_minute"]["minute"],
            "2026-06-20T13:34:00Z",
        )

    def test_build_step6_interaction_passively_preserves_matching_previous_minute_path(self):
        entry_agent = self._load_module("entry_agent_intrabar_plumbing", Path("EntryAgent") / "entry_agent.py")

        snapshot = {
            "ohlc": {"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.25},
            "latest_bar_time": "2026-06-20T13:34:00Z",
            "ohlc_is_closed": True,
            "step6_intrabar_path": {
                "current_minute": {
                    "minute": "2026-06-20T13:35:00Z",
                    "points": [["2026-06-20T13:35:01.000Z", 100.5]],
                    "truncated": False,
                    "price_change_only": True,
                    "max_points": 512,
                },
                "previous_minute": {
                    "minute": "2026-06-20T13:34:00Z",
                    "points": [["2026-06-20T13:34:01.000Z", 100.0], ["2026-06-20T13:34:20.000Z", 100.5]],
                    "truncated": False,
                    "price_change_only": True,
                    "max_points": 512,
                },
            },
        }
        step5 = {
            "status": "READY",
            "next_step": "Step 6",
            "state": {
                "setup_direction": "SHORT",
                "tick_size": 0.25,
                "step5_confirmed": True,
                "leg2_status": "VALIDATED",
                "leg2_candle": {"timestamp": "2026-06-20T13:30:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
                "leg2_candle_a_time": "2026-06-20T13:30:00Z",
            },
            "events": [],
        }

        interaction = entry_agent.build_step6_interaction(snapshot, step5, {})

        self.assertIsNotNone(interaction)
        self.assertIn("step6_intrabar_path", interaction)
        self.assertTrue(interaction["step6_intrabar_previous_minute_path_available"])
        self.assertEqual(
            interaction["step6_intrabar_previous_minute_path"]["minute"],
            "2026-06-20T13:34:00Z",
        )

    def test_step6_engine_output_is_identical_with_passive_intrabar_path_present(self):
        step6_engine = self._load_module("step6_engine_intrabar_passive", Path("EntryAgent") / "step6_engine.py")

        base_state = {
            "system_state": "REJECTION MODE ON",
            "trade_mode": "ON",
            "rejection_mode": "ON",
            "interaction_state": "ACTIVE",
            "setup_direction": "SHORT",
            "step5_confirmed": True,
            "leg2_status": "CONFIRMED",
            "structure_status": "VALID",
            "structure_valid": True,
            "active_step5_path": "5.1",
            "leg2_candle": {"open": 100.0, "high": 102.0, "low": 99.0, "close": 100.0},
            "tick_size": 0.25,
            "events": [],
        }
        candidate = {"open": 100.0, "high": 102.25, "low": 99.5, "close": 100.25}

        plain = step6_engine.evaluate_step6(dict(base_state), dict(candidate))
        with_path_state = dict(base_state)
        with_path_state["step6_intrabar_path"] = {
            "current_minute": None,
            "previous_minute": {
                "minute": "2026-06-20T13:34:00Z",
                "points": [["2026-06-20T13:34:01.000Z", 100.0]],
                "truncated": False,
                "price_change_only": True,
                "max_points": 512,
            },
        }
        with_path_state["step6_intrabar_previous_minute_path"] = with_path_state["step6_intrabar_path"]["previous_minute"]
        with_path_state["step6_intrabar_previous_minute_path_available"] = True
        with_path = step6_engine.evaluate_step6(with_path_state, dict(candidate))

        self.assertEqual(with_path["status"], plain["status"])
        self.assertEqual(with_path.get("entry_type"), plain.get("entry_type"))
        self.assertEqual(with_path["reason"], plain["reason"])


if __name__ == "__main__":
    unittest.main()
