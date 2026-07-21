import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENTRY_AGENT_DIR = ROOT / "EntryAgent"


class EntryStatusEndpointTests(unittest.TestCase):
    def _load_entry_agent(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            spec = importlib.util.spec_from_file_location(
                "entry_agent_under_test",
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

    def _load_server(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            spec = importlib.util.spec_from_file_location(
                "entry_status_server_under_test",
                ENTRY_AGENT_DIR / "tv_context_server.py",
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

    def _load_runtime_replay_validation(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            spec = importlib.util.spec_from_file_location(
                "runtime_replay_validation_under_test",
                ENTRY_AGENT_DIR / "runtime_replay_validation.py",
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

    def _assert_clean_locked_status(self, status, step, reason):
        self.assertEqual(status["current_step"], step)
        self.assertEqual(status["current_step_status"], "WAIT")
        self.assertEqual(status["wait_reason"], reason)
        self.assertEqual(status["last_decision"], f"WAIT: {reason}")
        for field in (
            "active_liquidity_name",
            "active_liquidity_price",
            "active_liquidity_group",
            "liquidity_price",
            "liquidity_group",
            "selected_pathway",
            "setup_direction",
            "current_pathway_control",
            "current_controlling_mode",
            "leg1_confirmed_at",
            "leg1_completed_at",
            "leg1_reference_price",
            "leg1_reference_candle_time",
            "leg2_confirmed_at",
            "leg2_candidate_candle_time",
            "leg2_reference_price",
            "entry_status_confirmed_at",
            "invalidated_at",
            "invalidated_liquidity",
            "invalidation_reason",
            "internal_invalidation_reason",
            "invalidation_source_candle_time",
            "invalidation_source",
            "invalidation_source_step",
        ):
            self.assertIsNone(status.get(field), field)
        self.assertFalse(status["rejection_mode_entered"])
        self.assertEqual(status["rejection_pathway_status"], "inactive")

    def _load_archived_session_rows(self, entry_agent, session_date, root, start_timestamp, end_timestamp):
        archive_path = entry_agent.data_path("rithmic_session_bars", session_date, f"{root}_1m.jsonl")
        self.assertTrue(archive_path.exists(), f"Missing session archive: {archive_path}")
        rows = []
        for raw in archive_path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            record = json.loads(raw)
            if record.get("root_symbol") != root:
                continue
            timestamp = record["timestamp"]
            if start_timestamp <= timestamp <= end_timestamp:
                rows.append(
                    {
                        "timestamp": timestamp,
                        "open": record["open"],
                        "high": record["high"],
                        "low": record["low"],
                        "close": record["close"],
                    }
                )
        rows.sort(key=lambda row: row["timestamp"])
        return archive_path, rows

    def _replay_archived_ym_2026_07_06_public_window(self):
        entry_agent = self._load_entry_agent()
        return self._replay_archived_public_window(
            entry_agent=entry_agent,
            session_date="2026-07-06",
            root="YM",
            start_timestamp="2026-07-06T13:15:00Z",
            end_timestamp="2026-07-06T13:36:00Z",
            checkpoints={
                "2026-07-06T13:30:00Z",
                "2026-07-06T13:31:00Z",
                "2026-07-06T13:32:00Z",
                "2026-07-06T13:33:00Z",
                "2026-07-06T13:34:00Z",
                "2026-07-06T13:35:00Z",
                "2026-07-06T13:36:00Z",
            },
        )

    def _replay_archived_public_window(self, *, entry_agent, session_date, root, start_timestamp, end_timestamp, checkpoints):
        archive_path, rows = self._load_archived_session_rows(
            entry_agent,
            session_date,
            root,
            start_timestamp,
            end_timestamp,
        )
        recent_cache_path = entry_agent.data_path("rithmic_recent_bars.json")

        original_state_path = entry_agent.STATE_PATH
        original_persistence_path = entry_agent.PERSISTENCE_STATE_PATH
        original_executor_state_path = entry_agent.EXECUTOR_STATE_PATH
        original_get_snapshot = entry_agent.get_latest_market_snapshot
        original_load_tv = entry_agent.load_tv_context
        original_recent_closed_bars = entry_agent.recent_closed_bars
        original_load_atr = entry_agent.load_rithmic_atr_snapshot
        original_append_audit = entry_agent.append_entry_agent_audit_row
        tv_context = entry_agent.load_tv_context(root)

        statuses = {}
        states = {}

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                entry_agent.STATE_PATH = Path(temp_dir) / "entry_agent_state.json"
                entry_agent.PERSISTENCE_STATE_PATH = Path(temp_dir) / "persistence_state.json"
                entry_agent.EXECUTOR_STATE_PATH = Path(temp_dir) / "executor_state.json"
                entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
                entry_agent.load_tv_context = lambda _symbol=None: tv_context
                entry_agent.load_rithmic_atr_snapshot = lambda _symbol=root: {
                    "atr_1m_14": (tv_context or {}).get("atr_1m_14") or 10.0
                }

                replay_bars = []
                index = {"value": 0}

                def market_snapshot(_symbol: str = root) -> dict:
                    current = rows[index["value"]]
                    return {
                        "symbol": root,
                        "normalized_symbol": root,
                        "latest_price": current["close"],
                        "latest_bar_time": current["timestamp"],
                        "ohlc_is_closed": True,
                        "liquidity": {
                            "nearest_level_above": None,
                            "nearest_level_below": None,
                            "tick_size": 1.0 if root == "YM" else 0.25,
                        },
                        "atr": {"atr_1m_14": (tv_context or {}).get("atr_1m_14") or 10.0},
                        "ohlc": {
                            "open": current["open"],
                            "high": current["high"],
                            "low": current["low"],
                            "close": current["close"],
                        },
                    }

                entry_agent.get_latest_market_snapshot = market_snapshot
                entry_agent.recent_closed_bars = lambda _symbol=root, limit=120: list(replay_bars)[-limit:]

                for i, bar in enumerate(rows):
                    index["value"] = i
                    replay_bars.append(dict(bar))
                    entry_agent.run_once(root, persist=True)
                    if bar["timestamp"] not in checkpoints:
                        continue
                    statuses[bar["timestamp"]] = entry_agent.build_entry_status(root)
                    states[bar["timestamp"]] = copy.deepcopy(
                        entry_agent.load_entry_state().get("state_by_symbol", {}).get(root, {})
                    )
        finally:
            entry_agent.STATE_PATH = original_state_path
            entry_agent.PERSISTENCE_STATE_PATH = original_persistence_path
            entry_agent.EXECUTOR_STATE_PATH = original_executor_state_path
            entry_agent.get_latest_market_snapshot = original_get_snapshot
            entry_agent.load_tv_context = original_load_tv
            entry_agent.recent_closed_bars = original_recent_closed_bars
            entry_agent.load_rithmic_atr_snapshot = original_load_atr
            entry_agent.append_entry_agent_audit_row = original_append_audit

        return {
            "entry_agent": entry_agent,
            "archive_path": archive_path,
            "recent_cache_path": recent_cache_path,
            "statuses": statuses,
            "states": states,
        }

    def _replay_archived_status_endpoint_window(
        self,
        *,
        entry_agent,
        session_date,
        root,
        start_timestamp,
        end_timestamp,
        checkpoints,
        extra_polls_by_timestamp=None,
    ):
        archive_path, rows = self._load_archived_session_rows(
            entry_agent,
            session_date,
            root,
            start_timestamp,
            end_timestamp,
        )
        extra_polls_by_timestamp = extra_polls_by_timestamp or {}

        original_state_path = entry_agent.STATE_PATH
        original_persistence_path = entry_agent.PERSISTENCE_STATE_PATH
        original_executor_state_path = entry_agent.EXECUTOR_STATE_PATH
        original_get_snapshot = entry_agent.get_latest_market_snapshot
        original_load_tv = entry_agent.load_tv_context
        original_recent_closed_bars = entry_agent.recent_closed_bars
        original_load_atr = entry_agent.load_rithmic_atr_snapshot
        original_append_audit = entry_agent.append_entry_agent_audit_row
        tv_context = entry_agent.load_tv_context(root)

        statuses = {}
        poll_history = {}
        states = {}

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                entry_agent.STATE_PATH = Path(temp_dir) / "entry_agent_state.json"
                entry_agent.PERSISTENCE_STATE_PATH = Path(temp_dir) / "persistence_state.json"
                entry_agent.EXECUTOR_STATE_PATH = Path(temp_dir) / "executor_state.json"
                entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
                entry_agent.load_tv_context = lambda _symbol=None: tv_context
                entry_agent.load_rithmic_atr_snapshot = lambda _symbol=root: {
                    "atr_1m_14": (tv_context or {}).get("atr_1m_14") or 10.0
                }

                replay_bars = []
                index = {"value": 0}

                def market_snapshot(_symbol: str = root) -> dict:
                    current = rows[index["value"]]
                    return {
                        "symbol": root,
                        "normalized_symbol": root,
                        "latest_price": current["close"],
                        "latest_bar_time": current["timestamp"],
                        "ohlc_is_closed": True,
                        "liquidity": {
                            "nearest_level_above": None,
                            "nearest_level_below": None,
                            "tick_size": 1.0 if root == "YM" else 0.25,
                        },
                        "atr": {"atr_1m_14": (tv_context or {}).get("atr_1m_14") or 10.0},
                        "ohlc": {
                            "open": current["open"],
                            "high": current["high"],
                            "low": current["low"],
                            "close": current["close"],
                        },
                    }

                entry_agent.get_latest_market_snapshot = market_snapshot
                entry_agent.recent_closed_bars = lambda _symbol=root, limit=120: list(replay_bars)[-limit:]

                for i, bar in enumerate(rows):
                    index["value"] = i
                    replay_bars.append(dict(bar))
                    entry_agent.run_once(root, persist=True)
                    status = entry_agent.build_entry_status(root)
                    if bar["timestamp"] in checkpoints:
                        statuses[bar["timestamp"]] = status
                        poll_history.setdefault(bar["timestamp"], []).append(copy.deepcopy(status))
                        for _ in range(int(extra_polls_by_timestamp.get(bar["timestamp"], 0))):
                            status = entry_agent.build_entry_status(root)
                            poll_history[bar["timestamp"]].append(copy.deepcopy(status))
                            statuses[bar["timestamp"]] = status
                        states[bar["timestamp"]] = copy.deepcopy(
                            entry_agent.load_entry_state().get("state_by_symbol", {}).get(root, {})
                        )
        finally:
            entry_agent.STATE_PATH = original_state_path
            entry_agent.PERSISTENCE_STATE_PATH = original_persistence_path
            entry_agent.EXECUTOR_STATE_PATH = original_executor_state_path
            entry_agent.get_latest_market_snapshot = original_get_snapshot
            entry_agent.load_tv_context = original_load_tv
            entry_agent.recent_closed_bars = original_recent_closed_bars
            entry_agent.load_rithmic_atr_snapshot = original_load_atr
            entry_agent.append_entry_agent_audit_row = original_append_audit

        return {
            "entry_agent": entry_agent,
            "archive_path": archive_path,
            "statuses": statuses,
            "poll_history": poll_history,
            "states": states,
        }
        self.assertEqual(status["continuation_pathway_status"], "inactive")
        self.assertEqual(status["current_continuation_type"], "none")
        self.assertEqual(status["continuation_type"], "none")
        self.assertEqual(status["leg1_status"], "WAIT")
        self.assertEqual(status["leg1_state"], "WAIT")
        self.assertIn(status.get("leg1_locked"), (None, False))
        self.assertIn(status.get("leg1_state_locked"), (None, False))
        self.assertEqual(status["leg2_status"], "WAIT")
        self.assertEqual(status["leg2_state"], "WAIT")
        self.assertEqual(status["entry_status"], "WAIT")
        for side_name in ("rejection_side", "continuation_side"):
            side = status[side_name]
            self.assertEqual(side["pathway_status"], "inactive")
            self.assertIsNone(side["current_pathway_control"])
            self.assertIsNone(side["current_controlling_mode"])
            self.assertIsNone(side["selected_pathway"])
            self.assertIsNone(side["setup_direction"])
            self.assertEqual(side["leg1_status"], "WAIT")
            self.assertEqual(side["leg1_state"], "WAIT")
            self.assertEqual(side["leg2_status"], "WAIT")
            self.assertEqual(side["leg2_state"], "WAIT")
            self.assertEqual(side["entry_status"], "WAIT")

    def _valid_randle_taylor_payload(self, symbol="NQ1!"):
        return {
            "source": "randle_taylor_map",
            "symbol": symbol,
            "timestamp": "2026-06-16T06:15:00-07:00",
            "session_date": "2026-06-16",
            "session_lock_price": 29392.0,
            "daily_atr14": 150.0,
            "liquidity_map": {
                "levels": [
                    {"name": "PMH", "price": 29402.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    {"name": "PML", "price": 29354.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                    {"name": "LH", "price": 29418.0, "status": "ACTIVE", "stack_group": "NONE"},
                    {"name": "LL", "price": 29343.0, "status": "ACTIVE", "stack_group": "LOW 1 / LOW 2"},
                    {"name": "ONH", "price": 29410.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    {"name": "ONL", "price": 29330.0, "status": "ACTIVE", "stack_group": "LOW 2"},
                    {"name": "YH", "price": 29445.0, "status": "ACTIVE", "stack_group": "NONE"},
                    {"name": "YL", "price": 29298.0, "status": "ACTIVE", "stack_group": "NONE"},
                ],
                "stacks": [
                    {
                        "name": "PMH/ONH Stack",
                        "members": ["PMH", "ONH"],
                        "close_boundary_name": "PMH",
                        "close_boundary_price": 29402.0,
                        "extreme_boundary_name": "ONH",
                        "extreme_boundary_price": 29410.0,
                    },
                    {
                        "name": "LL/ONL Stack",
                        "members": ["LL", "ONL"],
                        "close_boundary_name": "LL",
                        "close_boundary_price": 29343.0,
                        "extreme_boundary_name": "ONL",
                        "extreme_boundary_price": 29330.0,
                    },
                ],
            },
            "taylor_context": {
                "t_plus": {
                    "price": 29425.0,
                    "associated_liquidity": "PMH/ONH Stack",
                    "associated_extreme_name": "ONH",
                    "associated_extreme_price": 29410.0,
                    "distance_from_extreme": 15.0,
                },
                "yesterday_close": {
                    "price": 29380.0,
                    "associated_liquidity": "PML",
                    "associated_extreme_name": "PML",
                    "associated_extreme_price": 29354.0,
                    "distance_from_extreme": 26.0,
                },
                "t_minus": {
                    "price": 29335.0,
                    "associated_liquidity": "LL/ONL Stack",
                    "associated_extreme_name": "ONL",
                    "associated_extreme_price": 29330.0,
                    "distance_from_extreme": 5.0,
                },
            },
        }

    def _prior_date_step5_state(self):
        return {
            "state_by_symbol": {
                "NQ": {
                    "last_interacted_liquidity": {"name": "PMH", "price": 100.0, "side": "upper"},
                    "step25": {"status": "READY", "state": {"controlling_mode": "Normal Rejection Mode"}},
                    "step4": {
                        "status": "READY",
                        "next_step": "Step 5",
                        "state": {
                            "leg1_status": "COMPLETE",
                            "leg1_state_locked": True,
                            "active_liquidity": {"name": "PMH", "price": 100.0, "side": "upper"},
                            "leg1_completed_at": "2026-05-15T13:28:00Z",
                            "leg1_reference_price": 101.0,
                            "leg1_reference_candle_time": "2026-05-15T13:27:00Z",
                            "setup_direction": "SHORT",
                            "current_pathway_control": "rejection",
                            "current_controlling_mode": "Normal Rejection Mode",
                            "candle_b": {"timestamp": "2026-05-15T13:28:00Z"},
                        },
                    },
                    "step5": {
                        "status": "WAIT",
                        "next_step": "Step 5",
                        "state": {"leg2_status": "WAIT", "leg2_candidate_candle_time": "2026-05-15T13:29:00Z"},
                    },
                    "step6": {"status": "WAIT", "state": {}},
                }
            },
            "last_interacted_liquidity_by_symbol": {
                "NQ": {"name": "PMH", "price": 100.0, "side": "upper"}
            },
        }

    def test_entry_status_is_read_only_decision_status(self):
        server = self._load_server()
        server.build_entry_status = lambda symbol, checkpoint_public_anchor=False: {
            "symbol": symbol,
            "timestamp": "2026-05-05T00:00:00+00:00",
            "current_step": "Step 2",
            "active_liquidity_name": "PMH",
            "active_liquidity_price": 100.0,
            "setup_direction": "SHORT",
            "leg1_status": "WAIT",
            "leg2_status": "WAIT",
            "entry_status": "WAIT",
            "wait_reason": "Step 2 milestone confirmed.",
            "invalidation_reason": None,
            "last_decision": "WAIT: Step 2 milestone confirmed.",
        }

        response = server.app.test_client().get("/entry/status?symbols=NQ,YM")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "read_only")
        self.assertEqual(payload["execution_truth"], "Trade Manager")
        self.assertEqual(payload["decision_truth"], "Entry Manager")
        self.assertEqual([item["symbol"] for item in payload["symbols"]], ["NQ", "YM"])
        self.assertEqual(payload["symbols"][0]["entry_status"], "WAIT")
        self.assertEqual(payload["symbols"][0]["wait_reason"], "Step 2 milestone confirmed.")
        self.assertEqual(payload["symbols"][0]["current_step"], "Step 2")
        self.assertEqual(payload["symbols"][0]["current_step_label"], "Step 2 (Liquidity Close / Pathway Activation)")

    def test_entry_executor_status_returns_bridge_payload(self):
        server = self._load_server()
        original_fetch_local_json = server.fetch_local_json
        self.addCleanup(setattr, server, "fetch_local_json", original_fetch_local_json)

        payloads = {
            server.EXECUTOR_SYNC_SNAPSHOT_URL: {
                "ok": True,
                "symbols": {
                    "NQU6": {
                        "last_price": 29750.25,
                        "position_qty": 1,
                        "working_orders": [{"order_id": "STOP-1", "type": "stop"}],
                    }
                },
            },
            server.EXECUTOR_ORDERS_URL: {
                "ok": True,
                "orders": [{"order_id": "STOP-1", "trade_id": "T-1", "symbol": "NQU6", "type": "stop"}],
            },
            server.EXECUTOR_ACCOUNT_SNAPSHOT_URL: {
                "ok": True,
                "net_liq": 100000.0,
            },
        }
        server.fetch_local_json = lambda url, timeout=1.0: copy.deepcopy(payloads.get(url, {}))

        response = server.app.test_client().get("/entry/executor_status")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["mode"], "read_only")
        self.assertEqual(data["execution_truth"], "Executor")
        self.assertEqual(data["source"], "entry_agent_bridge")
        self.assertEqual(data["symbol_count"], 1)
        self.assertTrue(data["has_open_execution_state"])
        self.assertIn("sync_snapshot", data)
        self.assertIn("orders", data)
        self.assertIn("account_snapshot", data)
        self.assertEqual(data["sync_snapshot"]["symbols"]["NQU6"]["position_qty"], 1)

    def test_entry_executor_status_hides_historical_order_and_account_payloads_when_execution_flat(self):
        server = self._load_server()
        original_fetch_local_json = server.fetch_local_json
        self.addCleanup(setattr, server, "fetch_local_json", original_fetch_local_json)

        payloads = {
            server.EXECUTOR_SYNC_SNAPSHOT_URL: {"ok": True, "symbols": {}},
            server.EXECUTOR_ORDERS_URL: {
                "ok": True,
                "orders": [{"order_id": "OLD-1", "symbol": "YMM6", "status": "filled", "filled_at": "2026-06-01T06:31:34Z"}],
            },
            server.EXECUTOR_ACCOUNT_SNAPSHOT_URL: {
                "ok": True,
                "net_liq": 97275.0,
                "updated_at": "2026-06-18T14:24:15Z",
            },
        }
        server.fetch_local_json = lambda url, timeout=1.0: copy.deepcopy(payloads.get(url, {}))

        response = server.app.test_client().get("/entry/executor_status")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertFalse(data["has_open_execution_state"])
        self.assertEqual(data["executor_summary"]["message"], "No Active Execution")
        self.assertEqual(data["orders"], {"ok": True, "orders": []})
        self.assertEqual(data["account_snapshot"]["reason"], "no_active_execution_state")
        self.assertIsNone(data["account_snapshot"]["updated_at"])

    def test_entry_status_step_labels_cover_public_blueprint_steps(self):
        server = self._load_server()
        expected = {
            "Step 1": "Step 1 (Session / Level Prep)",
            "Step 2": "Step 2 (Liquidity Close / Pathway Activation)",
            "Step 2.5": "Step 2 Continuation (Continuation Logic)",
            "Step 4": "Step 4 (Leg 1 Formation)",
            "Step 5": "Step 5 (Leg 2 Confirmation)",
            "Step 6": "Step 6 (Entry Trigger)",
            "Step 7": "Step 7 (Invalidation / Reset)",
        }

        for step, label in expected.items():
            with self.subTest(step=step):
                server.build_entry_status = lambda symbol, step=step: {
                    "symbol": symbol,
                    "timestamp": "2026-05-05T00:00:00+00:00",
                    "current_step": step,
                    "entry_status": "WAIT",
                }

                response = server.app.test_client().get("/entry/status?symbols=NQ")
                status = response.get_json()["symbols"][0]

                self.assertEqual(status["current_step"], step)
                self.assertEqual(status["current_step_label"], label)

    def test_public_liquidity_lock_payload_uses_frozen_session_context(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        snapshot = {
            "latest_bar_time": "2026-06-26T13:40:00Z",
            "session_liquidity_context": {
                "locked": True,
                "disabled": False,
                "tv_context": {
                    "session_date": "2026-06-26",
                    "received_at": "2026-06-26T13:15:00Z",
                    "liquidity_context_locked_at": "2026-06-26T13:15:00Z",
                },
            },
        }
        active_group = {
            "name": "HIGH 1",
            "close_boundary": 52176.0,
            "extreme_boundary": 52176.0,
            "components": ["PMH", "LH", "ONH"],
        }

        payload = entry_agent.public_liquidity_lock_payload(snapshot, "PMH/LH/ONH", 52176.0, active_group)

        self.assertEqual(
            payload,
            {
                "locked": True,
                "session_date": "2026-06-26",
                "lock_time": "06:15:00 PT",
                "lock_source": "TradingView",
                "active_liquidity_name": "PMH/LH/ONH",
                "liquidity_group": "HIGH 1",
                "close_boundary": 52176.0,
                "extreme_boundary": 52176.0,
                "frozen_liquidity_levels": {},
                "frozen_stack_names": [],
                "last_tv_context_received_time": None,
                "last_tv_context_session_date": None,
                "last_tv_context_levels": {},
                "last_tv_context_matches_frozen": False,
            },
        )

    def test_public_liquidity_lock_payload_includes_frozen_levels_and_latest_tv_metadata(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        snapshot = {
            "latest_bar_time": "2026-06-26T13:40:00Z",
            "raw_tv_context": {
                "received_at": "2026-06-26T13:50:00Z",
                "session_date": "2026-06-26",
                "last_tv_context_levels": {
                    "PMH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "ONH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                },
            },
            "session_liquidity_context": {
                "locked": True,
                "disabled": False,
                "active_levels": {
                    "PMH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "ONH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                },
                "active_groups": [
                    {"name": "HIGH 1", "display_name": "PMH/LH/ONH", "close_boundary": 52176.0, "extreme_boundary": 52176.0}
                ],
                "tv_context": {
                    "session_date": "2026-06-26",
                    "received_at": "2026-06-26T13:15:00Z",
                    "liquidity_context_locked_at": "2026-06-26T13:15:00Z",
                },
            },
        }

        payload = entry_agent.public_liquidity_lock_payload(snapshot, "PMH/LH/ONH", 52176.0, active_group=None)

        self.assertEqual(payload["locked"], True)
        self.assertEqual(payload["frozen_stack_names"], ["PMH/LH/ONH"])
        self.assertEqual(payload["frozen_liquidity_levels"]["PMH"]["price"], 52176.0)
        self.assertEqual(payload["last_tv_context_received_time"], "06:50:00 PT")
        self.assertEqual(payload["last_tv_context_session_date"], "2026-06-26")
        self.assertTrue(payload["last_tv_context_matches_frozen"])

    def test_locked_entry_status_includes_unlocked_liquidity_lock_when_missing(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        status = entry_agent.locked_entry_status(
            "NQ",
            {"requested_symbol": "NQ", "latest_bar_time": "2026-06-26T13:10:00Z", "ohlc": {}},
            "PRE_RTH_LOCK",
            "Awaiting 6:15 RTH activation line.",
        )

        self.assertEqual(
            status["liquidity_lock"],
            {
                "locked": False,
                "session_date": None,
                "lock_time": None,
                "lock_source": None,
                "active_liquidity_name": None,
                "liquidity_group": None,
                "close_boundary": None,
                "extreme_boundary": None,
                "frozen_liquidity_levels": {},
                "frozen_stack_names": [],
                "last_tv_context_received_time": None,
                "last_tv_context_session_date": None,
                "last_tv_context_levels": {},
                "last_tv_context_matches_frozen": False,
            },
        )

    def test_same_side_liquidity_owner_rotation_release_detects_next_lower_owner(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        locked_owner = {
            "active_liquidity": {
                "name": "PML",
                "price": 30117.0,
                "display_name": "PML/LL Liquidity",
                "side": "lower",
                "group": {"display_name": "PML/LL Liquidity"},
            }
        }
        next_liquidity = {
            "name": "ONL",
            "price": 29924.5,
            "display_name": "ONL/YL Liquidity",
            "side": "lower",
            "group": {"display_name": "ONL/YL Liquidity"},
        }

        release = entry_agent.same_side_liquidity_owner_rotation_release(
            locked_owner,
            next_liquidity,
            {"close": 29920.0, "timestamp": "2026-06-25T13:41:00Z"},
        )

        self.assertIsNotNone(release)
        self.assertEqual(release["reason_key"], "SAME_SIDE_NEXT_LIQUIDITY_OWNER_ROTATION")
        self.assertEqual(release["released_group"], "PML/LL Liquidity")
        self.assertEqual(release["next_group"], "ONL/YL Liquidity")

    def test_reset_symbol_state_for_owner_rotation_clears_stale_downstream_lifecycle(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        symbol_state = {
            "step25": {"status": "READY"},
            "step3": {"status": "ALLOW_STEP_4"},
            "step4": {"status": "READY"},
            "step5": {"status": "WAIT"},
            "step6": {"status": "WAIT"},
            "rejection_lane": {"lane_status": "invalidated"},
            "continuation_lane": {"lane_status": "controlling"},
            "consumed_liquidity_levels": [{"key": "PML:30117.0"}],
        }
        step2_state = {
            "last_interacted_liquidity": {"name": "ONL", "price": 29924.5},
            "consumed_liquidity_levels": [{"key": "PML:30117.0"}, {"key": "LL:30099.0"}],
        }

        reset = entry_agent.reset_symbol_state_for_owner_rotation(symbol_state, step2_state)

        self.assertEqual(reset["step25"], {})
        self.assertEqual(reset["step4"], {})
        self.assertEqual(reset["step6"], {})
        self.assertEqual(reset["rejection_lane"], {})
        self.assertEqual(reset["continuation_lane"], {})
        self.assertEqual(reset["last_interacted_liquidity"]["name"], "ONL")
        self.assertEqual(len(reset["consumed_liquidity_levels"]), 2)

    def test_run_once_resets_downstream_persisted_state_after_owner_rotation_release(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_load_entry_state = entry_agent.load_entry_state
        original_get_latest_market_snapshot = entry_agent.get_latest_market_snapshot
        original_load_raw_tv_context = entry_agent.load_raw_tv_context
        original_load_tv_context = entry_agent.load_tv_context
        original_tv_context_freshness_status = entry_agent.tv_context_freshness_status
        original_sanitize_stale_session_state = entry_agent.sanitize_stale_session_state
        original_apply_observation_cycle_reset = entry_agent.apply_observation_cycle_reset
        original_locked_session_liquidity_context = entry_agent.locked_session_liquidity_context
        original_pre_open_observed_extreme = entry_agent.pre_open_observed_extreme
        original_effective_session_tv_context = entry_agent.effective_session_tv_context
        original_active_levels_from_tv_context = entry_agent.active_levels_from_tv_context
        original_classify_liquidity_location = entry_agent.classify_liquidity_location
        original_evaluate_live_step_2_1a = entry_agent.evaluate_live_step_2_1a
        original_rejection_from_step2_activation = entry_agent.rejection_from_step2_activation
        original_load_rithmic_atr_snapshot = entry_agent.load_rithmic_atr_snapshot
        original_evaluate_live_step25 = entry_agent.evaluate_live_step25
        original_evaluate_live_step3 = entry_agent.evaluate_live_step3
        original_evaluate_live_step4 = entry_agent.evaluate_live_step4
        original_evaluate_live_step5 = entry_agent.evaluate_live_step5
        original_evaluate_live_step6 = entry_agent.evaluate_live_step6
        original_evaluate_gateway = entry_agent.evaluate_gateway
        original_mask_unconfirmed_step4_leg1_invalidation = entry_agent.mask_unconfirmed_step4_leg1_invalidation
        original_snapshot_lane_statuses = entry_agent.snapshot_lane_statuses
        original_append_entry_agent_audit_row = entry_agent.append_entry_agent_audit_row
        original_persist_state = entry_agent.persist_state

        persisted_symbol_state_seen = {}
        try:
            entry_agent.load_entry_state = lambda: {
                "state_by_symbol": {
                    "NQ": {
                        "step25": {"status": "READY", "state": {"controlling_mode": "Normal Rejection Mode"}},
                        "step4": {"status": "READY", "state": {"leg1_state_locked": True, "leg1_status": "COMPLETE"}},
                        "step5": {"status": "WAIT"},
                        "step6": {"status": "WAIT"},
                        "rejection_lane": {"lane_status": "controlling"},
                        "continuation_lane": {"lane_status": "eligible"},
                    }
                }
            }
            entry_agent.get_latest_market_snapshot = lambda symbol: {
                "symbol": symbol,
                "latest_price": 29920.0,
                "latest_bar_time": "2026-06-25T13:41:00Z",
                "ohlc": {"open": 29950.0, "high": 29960.0, "low": 29910.0, "close": 29920.0},
                "ohlc_is_closed": True,
            }
            entry_agent.load_raw_tv_context = lambda symbol: {"session_date": "2026-06-25", "levels": {}}
            entry_agent.load_tv_context = lambda symbol: {"session_date": "2026-06-25", "levels": {}}
            entry_agent.tv_context_freshness_status = lambda ctx: "TV_CONTEXT_LIVE"
            entry_agent.sanitize_stale_session_state = lambda state, symbol, session: state
            entry_agent.apply_observation_cycle_reset = lambda state, symbol, snapshot: state
            entry_agent.locked_session_liquidity_context = lambda state, symbol: None
            entry_agent.pre_open_observed_extreme = lambda state, symbol: None
            entry_agent.effective_session_tv_context = lambda state, symbol, ctx: ctx
            entry_agent.active_levels_from_tv_context = lambda ctx: {}
            entry_agent.classify_liquidity_location = lambda latest_price, levels, symbol: {"tick_size": 0.25}
            entry_agent.evaluate_live_step_2_1a = lambda snapshot, levels, liquidity, state: {
                "step_2_activated": False,
                "events": [{"event": "step2_locked_owner_released", "reason": "SAME_SIDE_NEXT_LIQUIDITY_OWNER_ROTATION"}],
                "state_transition_reason": "SAME_SIDE_NEXT_LIQUIDITY_OWNER_ROTATION",
                "last_interacted_liquidity": {"name": "ONL", "price": 29924.5},
                "consumed_liquidity_levels": [{"key": "PML:30117.0"}, {"key": "LL:30099.0"}],
            }
            entry_agent.rejection_from_step2_activation = lambda step2, symbol: {}
            entry_agent.load_rithmic_atr_snapshot = lambda symbol: {}
            def fake_step25(snapshot, rejection, step2, persisted_state):
                persisted_symbol_state_seen["value"] = persisted_state
                return {"status": "WAIT", "state": {}}
            entry_agent.evaluate_live_step25 = fake_step25
            entry_agent.evaluate_live_step3 = lambda *args, **kwargs: {"status": "WAIT", "state": {}}
            entry_agent.evaluate_live_step4 = lambda *args, **kwargs: {"status": "WAIT", "state": {}}
            entry_agent.evaluate_live_step5 = lambda *args, **kwargs: {"status": "WAIT", "state": {}}
            entry_agent.evaluate_live_step6 = lambda *args, **kwargs: {"status": "WAIT", "state": {}}
            entry_agent.evaluate_gateway = lambda *args, **kwargs: {}
            entry_agent.mask_unconfirmed_step4_leg1_invalidation = lambda snapshot, reason: None
            entry_agent.snapshot_lane_statuses = lambda snapshot, persisted_state: ({}, {})
            entry_agent.append_entry_agent_audit_row = lambda snapshot: None
            entry_agent.persist_state = lambda snapshot: None

            entry_agent.run_once("NQ", persist=False)
        finally:
            entry_agent.load_entry_state = original_load_entry_state
            entry_agent.get_latest_market_snapshot = original_get_latest_market_snapshot
            entry_agent.load_raw_tv_context = original_load_raw_tv_context
            entry_agent.load_tv_context = original_load_tv_context
            entry_agent.tv_context_freshness_status = original_tv_context_freshness_status
            entry_agent.sanitize_stale_session_state = original_sanitize_stale_session_state
            entry_agent.apply_observation_cycle_reset = original_apply_observation_cycle_reset
            entry_agent.locked_session_liquidity_context = original_locked_session_liquidity_context
            entry_agent.pre_open_observed_extreme = original_pre_open_observed_extreme
            entry_agent.effective_session_tv_context = original_effective_session_tv_context
            entry_agent.active_levels_from_tv_context = original_active_levels_from_tv_context
            entry_agent.classify_liquidity_location = original_classify_liquidity_location
            entry_agent.evaluate_live_step_2_1a = original_evaluate_live_step_2_1a
            entry_agent.rejection_from_step2_activation = original_rejection_from_step2_activation
            entry_agent.load_rithmic_atr_snapshot = original_load_rithmic_atr_snapshot
            entry_agent.evaluate_live_step25 = original_evaluate_live_step25
            entry_agent.evaluate_live_step3 = original_evaluate_live_step3
            entry_agent.evaluate_live_step4 = original_evaluate_live_step4
            entry_agent.evaluate_live_step5 = original_evaluate_live_step5
            entry_agent.evaluate_live_step6 = original_evaluate_live_step6
            entry_agent.evaluate_gateway = original_evaluate_gateway
            entry_agent.mask_unconfirmed_step4_leg1_invalidation = original_mask_unconfirmed_step4_leg1_invalidation
            entry_agent.snapshot_lane_statuses = original_snapshot_lane_statuses
            entry_agent.append_entry_agent_audit_row = original_append_entry_agent_audit_row
            entry_agent.persist_state = original_persist_state

        self.assertEqual(persisted_symbol_state_seen["value"]["step25"], {})
        self.assertEqual(persisted_symbol_state_seen["value"]["step4"], {})
        self.assertEqual(persisted_symbol_state_seen["value"]["last_interacted_liquidity"]["name"], "ONL")

    def test_step2_lifecycle_window_terminated_after_leg1_window_expires(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        terminated = entry_agent.step2_lifecycle_window_terminated(
            {
                "latest_bar_time": "2026-06-25T13:47:00Z",
            },
            {
                "step_2_activated": True,
            },
            {
                "state": {
                    "leg1_window_started_at": "2026-06-25T13:40:00Z",
                    "leg1_window_active": False,
                    "leg1_window_remaining": 0,
                    "leg1_window_expires_at": "2026-06-25T13:44:00Z",
                    "leg1_state_locked": False,
                    "leg1_status": "WAIT",
                }
            },
        )

        self.assertTrue(terminated)

    def test_step2_lifecycle_window_terminated_when_stale_leg1_locked_flag_survives(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        terminated = entry_agent.step2_lifecycle_window_terminated(
            {
                "latest_bar_time": "2026-06-25T14:47:00Z",
            },
            {
                "step_2_activated": True,
            },
            {
                "state": {
                    "leg1_window_started_at": "2026-06-25T13:40:00Z",
                    "leg1_window_active": False,
                    "leg1_window_remaining": 0,
                    "leg1_window_expires_at": "2026-06-25T13:44:00Z",
                    "leg1_state_locked": True,
                    "leg1_status": "WAIT",
                    "active_liquidity": {"name": "PML", "price": 30117.0},
                }
            },
        )

        self.assertTrue(terminated)

    def test_step2_candle_count_clears_after_leg1_window_expires(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        count = entry_agent.step2_candle_count(
            {
                "latest_bar_time": "2026-06-25T14:47:00Z",
                "step4": {
                    "state": {
                        "leg1_window_started_at": "2026-06-25T13:40:00Z",
                        "leg1_window_active": False,
                        "leg1_window_remaining": 0,
                        "leg1_window_expires_at": "2026-06-25T13:44:00Z",
                        "leg1_state_locked": False,
                        "leg1_status": "WAIT",
                    }
                },
            },
            {
                "step_2_activated": True,
                "step2_activation_candle_index": 0,
                "candle_index": 1554,
            },
        )

        self.assertIsNone(count)

    def test_active_liquidity_from_snapshot_ignores_stale_step2_owner_after_window_expires(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        active_name, active_price = entry_agent.active_liquidity_from_snapshot(
            {
                "latest_price": 29595.75,
                "latest_bar_time": "2026-06-25T14:47:00Z",
                "step_2_1a": {
                    "step_2_activated": True,
                    "step2_locked_owner": {
                        "pathway": "rejection",
                        "active_liquidity": {"name": "PML/LL", "price": 30099.0, "display_name": "PML/LL Liquidity"},
                    },
                },
                "step4": {
                    "state": {
                        "leg1_window_started_at": "2026-06-25T13:40:00Z",
                        "leg1_window_active": False,
                        "leg1_window_remaining": 0,
                        "leg1_window_expires_at": "2026-06-25T13:44:00Z",
                        "leg1_state_locked": False,
                        "leg1_status": "WAIT",
                    }
                },
                "rejection": {},
                "liquidity": {"tick_size": 0.25},
                "tv_context": {"levels": {}},
                "ohlc": {"open": 0, "high": 0, "low": 0, "close": 0},
            }
        )

        self.assertNotEqual(active_name, "PML/LL Liquidity")
        self.assertNotEqual(active_price, 30099.0)

    def test_current_step_from_snapshot_drops_to_step1_after_step2_window_terminates(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        current_step = entry_agent.current_step_from_snapshot(
            {
                "latest_price": 29595.75,
                "latest_bar_time": "2026-06-25T14:47:00Z",
                "step_2_1a": {
                    "step_2_activated": True,
                    "active_level": "PML/LL",
                    "level_price": 30099.0,
                },
                "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
                "step4": {
                    "status": "WAIT",
                    "next_step": "Step 4",
                    "state": {
                        "leg1_window_started_at": "2026-06-25T13:40:00Z",
                        "leg1_window_active": False,
                        "leg1_window_remaining": 0,
                        "leg1_window_expires_at": "2026-06-25T13:44:00Z",
                        "leg1_state_locked": False,
                        "leg1_status": "WAIT",
                    },
                },
                "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
                "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
            }
        )

        self.assertEqual(current_step, "Step 1")

    def test_build_entry_status_suppresses_expired_step2_publication(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        original_load_entry_state = entry_agent.load_entry_state
        try:
            entry_agent.load_entry_state = lambda: {"symbols": {"NQ": {}}}

            def fake_run_once(_symbol: str, persist: bool = True):
                return {
                    "requested_symbol": "NQ",
                    "normalized_symbol": "NQ",
                    "latest_price": 29595.75,
                    "latest_bar_time": "2026-06-25T14:47:00Z",
                    "ohlc": {"open": 29590.0, "high": 29600.0, "low": 29580.0, "close": 29595.75},
                    "liquidity": {
                        "tick_size": 0.25,
                        "nearest_level_above": "ONL",
                        "nearest_level_below": "YL",
                    },
                    "tv_context": {
                        "levels": {
                            "YL": {"price": 29540.0, "status": "ACTIVE", "stack_group": "LOW 2"},
                        }
                    },
                    "step_2_1a": {
                        "step_2_activated": True,
                        "active_level": "PML/LL",
                        "level_price": 30099.0,
                        "last_interacted_liquidity": {
                            "name": "PML/LL",
                            "price": 30099.0,
                            "display_name": "PML/LL Liquidity",
                        },
                    },
                    "rejection": {
                        "rejection_mode": "OFF",
                        "trigger_level": "PML/LL",
                        "trigger_price": 30099.0,
                    },
                    "step25": {"status": "WAIT", "next_step": "Step 2.5", "state": {}},
                    "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
                    "step4": {
                        "status": "WAIT",
                        "next_step": "Step 4",
                        "reason": "Leg 1 window expired.",
                        "state": {
                            "leg1_window_started_at": "2026-06-25T13:40:00Z",
                            "leg1_window_active": False,
                            "leg1_window_remaining": 0,
                            "leg1_window_expires_at": "2026-06-25T13:44:00Z",
                            "leg1_state_locked": False,
                            "leg1_status": "WAIT",
                        },
                    },
                    "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
                    "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
                    "rejection_lane": {
                        "lane_name": "rejection",
                        "lane_status": "idle",
                        "pathway_status": "idle",
                        "active_liquidity_name": None,
                        "active_liquidity_price": None,
                        "liquidity_group": None,
                        "close_boundary": None,
                        "extreme_boundary": None,
                        "wick_boundary_extreme": None,
                        "candle_count": None,
                        "step2_status": "WAIT",
                        "step4_status": "WAIT",
                        "step25_status": "WAIT",
                        "step2_step4_50_line": None,
                        "step4_step5_75_line": None,
                        "invalidation_reason": None,
                    },
                    "continuation_lane": {
                        "lane_name": "continuation",
                        "lane_status": "idle",
                        "pathway_status": "idle",
                        "active_liquidity_name": None,
                        "active_liquidity_price": None,
                        "liquidity_group": None,
                        "close_boundary": None,
                        "extreme_boundary": None,
                        "wick_boundary_extreme": None,
                        "candle_count": None,
                        "step2_status": "WAIT",
                        "step4_status": "WAIT",
                        "step25_status": "WAIT",
                        "step2_step4_50_line": None,
                        "step4_step5_75_line": None,
                        "invalidation_reason": None,
                        "continuation_type": "none",
                    },
                }

            entry_agent.run_once = fake_run_once
            status = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once
            entry_agent.load_entry_state = original_load_entry_state

        self.assertTrue(status["step2_lifecycle_window_terminated"])
        self.assertEqual(status["current_step"], "Step 1")
        self.assertEqual(status["current_step_status"], "WAIT")
        self.assertNotEqual(status["active_liquidity_name"], "PML/LL")
        self.assertNotIn("Step 2 confirmed", status["last_decision"])

    def test_build_entry_status_rotates_boundaries_with_new_active_owner_after_step2_termination(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        original_load_entry_state = entry_agent.load_entry_state
        original_active_liquidity_from_snapshot = entry_agent.active_liquidity_from_snapshot
        original_active_liquidity_group_from_snapshot = entry_agent.active_liquidity_group_from_snapshot
        original_next_same_side_liquidity_target = entry_agent.next_same_side_liquidity_target
        try:
            entry_agent.load_entry_state = lambda: {"symbols": {"NQ": {}}}
            entry_agent.active_liquidity_from_snapshot = lambda _snapshot: ("ONL", 29540.0)
            entry_agent.active_liquidity_group_from_snapshot = lambda _snapshot: {
                "name": "LOW 2",
                "display_name": "ONL/YL Liquidity",
                "components": ["ONL", "YL"],
                "side": "lower",
                "close_boundary": 29540.0,
                "extreme_boundary": 29520.0,
            }
            entry_agent.next_same_side_liquidity_target = lambda _tv_context, active_liquidity: (
                {"name": "YL", "price": 29520.0, "side": "lower"} if active_liquidity and active_liquidity.get("name") == "ONL" else None
            )

            def fake_run_once(_symbol: str, persist: bool = True):
                return {
                    "requested_symbol": "NQ",
                    "normalized_symbol": "NQ",
                    "latest_price": 29535.0,
                    "latest_bar_time": "2026-06-25T14:47:00Z",
                    "ohlc": {"open": 29548.0, "high": 29552.0, "low": 29530.0, "close": 29535.0},
                    "liquidity": {"tick_size": 0.25, "nearest_level_above": "ONL", "nearest_level_below": "YL"},
                    "tv_context": {"levels": {}},
                    "step_2_1a": {
                        "step_2_activated": True,
                        "active_level": "PML/LL",
                        "level_price": 30117.0,
                        "last_interacted_liquidity": {"name": "PML/LL", "price": 30117.0, "display_name": "PML/LL Liquidity"},
                        "step2_locked_owner": {
                            "pathway": "rejection",
                            "active_liquidity_name": "PML/LL",
                            "active_liquidity_price": 30117.0,
                            "close_boundary": 30117.0,
                            "extreme_boundary": 30099.0,
                            "active_liquidity": {"name": "PML/LL", "price": 30117.0, "display_name": "PML/LL Liquidity"},
                        },
                    },
                    "rejection": {"rejection_mode": "OFF"},
                    "step25": {"status": "WAIT", "next_step": "Step 2.5", "state": {}},
                    "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
                    "step4": {
                        "status": "WAIT",
                        "next_step": "Step 4",
                        "state": {
                            "leg1_window_started_at": "2026-06-25T13:40:00Z",
                            "leg1_window_active": False,
                            "leg1_window_remaining": 0,
                            "leg1_window_expires_at": "2026-06-25T13:44:00Z",
                            "leg1_state_locked": False,
                            "leg1_status": "WAIT",
                            "active_liquidity": {"name": "PML/LL", "price": 30117.0, "side": "lower"},
                            "next_break_side_liquidity": {"name": "ONL", "price": 29540.0, "side": "lower"},
                        },
                    },
                    "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
                    "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
                    "rejection_lane": {
                        "lane_name": "rejection",
                        "lane_status": "idle",
                        "pathway_status": "idle",
                        "active_liquidity_name": None,
                        "active_liquidity_price": None,
                        "liquidity_group": None,
                        "close_boundary": None,
                        "extreme_boundary": None,
                        "wick_boundary_extreme": None,
                        "candle_count": None,
                        "step2_status": "WAIT",
                        "step4_status": "WAIT",
                        "step25_status": "WAIT",
                        "step2_step4_50_line": None,
                        "step4_step5_75_line": None,
                        "invalidation_reason": None,
                    },
                    "continuation_lane": {
                        "lane_name": "continuation",
                        "lane_status": "idle",
                        "pathway_status": "idle",
                        "active_liquidity_name": None,
                        "active_liquidity_price": None,
                        "liquidity_group": None,
                        "close_boundary": None,
                        "extreme_boundary": None,
                        "wick_boundary_extreme": None,
                        "candle_count": None,
                        "step2_status": "WAIT",
                        "step4_status": "WAIT",
                        "step25_status": "WAIT",
                        "step2_step4_50_line": None,
                        "step4_step5_75_line": None,
                        "invalidation_reason": None,
                        "continuation_type": "none",
                    },
                }

            entry_agent.run_once = fake_run_once
            status = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once
            entry_agent.load_entry_state = original_load_entry_state
            entry_agent.active_liquidity_from_snapshot = original_active_liquidity_from_snapshot
            entry_agent.active_liquidity_group_from_snapshot = original_active_liquidity_group_from_snapshot
            entry_agent.next_same_side_liquidity_target = original_next_same_side_liquidity_target

        self.assertTrue(status["step2_lifecycle_window_terminated"])
        self.assertEqual(status["active_liquidity_name"], "ONL/YL")
        self.assertEqual(status["active_liquidity_group"]["name"], "LOW 2")
        self.assertEqual(status["close_boundary"], 29540.0)
        self.assertEqual(status["extreme_boundary"], 29520.0)
        self.assertEqual(status["step2_step4_50_line"], 29530.0)
        self.assertEqual(status["step4_step5_75_line"], 29525.0)

    def test_active_stack_from_context_rebuilds_canonical_lower_stack_from_single_level(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        stack = entry_agent.active_stack_from_context(
            {
                "levels": {
                    "ONL": {"price": 29924.5, "status": "ACTIVE", "stack_group": "LOW 2"},
                    "YL": {"price": 29924.5, "status": "ACTIVE", "stack_group": "LOW 2"},
                }
            },
            "ONL",
        )

        self.assertEqual(stack["name"], "LOW 2")
        self.assertEqual(stack["display_name"], "YL/ONL Liquidity")
        self.assertEqual(stack["close_boundary"], 29924.5)
        self.assertEqual(stack["extreme_boundary"], 29924.5)
        self.assertIn(stack["close_component"], {"ONL", "YL"})

    def test_build_entry_status_prefers_frozen_session_stack_map_for_rotated_owner(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        original_load_entry_state = entry_agent.load_entry_state
        try:
            entry_agent.load_entry_state = lambda: {"symbols": {"NQ": {}}}

            def fake_run_once(_symbol: str, persist: bool = True):
                return {
                    "requested_symbol": "NQ",
                    "normalized_symbol": "NQ",
                    "latest_price": 29924.5,
                    "latest_bar_time": "2026-06-25T14:47:00Z",
                    "ohlc": {"open": 29930.0, "high": 29932.0, "low": 29924.5, "close": 29924.5},
                    "liquidity": {"tick_size": 0.25, "nearest_level_above": "ONL", "nearest_level_below": "YL"},
                    "session_liquidity_context": {
                        "locked": True,
                        "disabled": False,
                        "active_levels": {
                            "ONL": {"price": 29924.5, "status": "ACTIVE", "stack_group": "LOW 2"},
                            "YL": {"price": 29924.5, "status": "ACTIVE", "stack_group": "LOW 2"},
                        },
                        "active_groups": [
                            {
                                "name": "LOW 2",
                                "display_name": "ONL/YL Liquidity",
                                "side": "lower",
                                "stack_group": "LOW 2",
                                "close_boundary": 29924.5,
                                "stack_extreme": 29924.5,
                                "extreme_boundary": 29924.5,
                                "wick_boundary_extreme": None,
                                "components": ["ONL", "YL"],
                                "prices": {"ONL": 29924.5, "YL": 29924.5},
                            }
                        ],
                        "tv_context": {
                            "locked": True,
                            "context_locked": True,
                            "locked_for_day": True,
                            "liquidity_context_locked": True,
                            "levels": {
                                "ONL": {"price": 29924.5, "status": "ACTIVE", "stack_group": "LOW 2"},
                                "YL": {"price": 29924.5, "status": "ACTIVE", "stack_group": "LOW 2"},
                            },
                        },
                    },
                    # Simulate a degraded selector path that only identifies the single touched level.
                    "tv_context": {
                        "levels": {
                            "ONL": {"price": 29924.5, "status": "ACTIVE", "stack_group": "NONE"},
                            "YL": {"price": 29924.5, "status": "ACTIVE", "stack_group": "NONE"},
                        }
                    },
                    "step_2_1a": {
                        "step_2_activated": True,
                        "active_level": "PML/LL",
                        "level_price": 30117.0,
                        "last_interacted_liquidity": {"name": "PML/LL", "price": 30117.0, "display_name": "PML/LL Liquidity"},
                        "step2_locked_owner": {
                            "pathway": "rejection",
                            "active_liquidity_name": "PML/LL",
                            "active_liquidity_price": 30117.0,
                            "close_boundary": 30117.0,
                            "extreme_boundary": 30099.0,
                            "active_liquidity": {"name": "PML/LL", "price": 30117.0, "display_name": "PML/LL Liquidity"},
                        },
                    },
                    "rejection": {"rejection_mode": "OFF"},
                    "step25": {"status": "WAIT", "next_step": "Step 2.5", "state": {}},
                    "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
                    "step4": {
                        "status": "WAIT",
                        "next_step": "Step 4",
                        "reason": "Leg 1 window expired.",
                        "state": {
                            "leg1_window_started_at": "2026-06-25T13:40:00Z",
                            "leg1_window_active": False,
                            "leg1_window_remaining": 0,
                            "leg1_window_expires_at": "2026-06-25T13:44:00Z",
                            "leg1_state_locked": False,
                            "leg1_status": "WAIT",
                        },
                    },
                    "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
                    "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
                    "rejection_lane": {
                        "lane_name": "rejection",
                        "lane_status": "idle",
                        "pathway_status": "idle",
                        "active_liquidity_name": None,
                        "active_liquidity_price": None,
                        "liquidity_group": None,
                        "close_boundary": None,
                        "extreme_boundary": None,
                        "wick_boundary_extreme": None,
                        "candle_count": None,
                        "step2_status": "WAIT",
                        "step4_status": "WAIT",
                        "step25_status": "WAIT",
                        "step2_step4_50_line": None,
                        "step4_step5_75_line": None,
                        "invalidation_reason": None,
                    },
                    "continuation_lane": {
                        "lane_name": "continuation",
                        "lane_status": "idle",
                        "pathway_status": "idle",
                        "active_liquidity_name": None,
                        "active_liquidity_price": None,
                        "liquidity_group": None,
                        "close_boundary": None,
                        "extreme_boundary": None,
                        "wick_boundary_extreme": None,
                        "candle_count": None,
                        "step2_status": "WAIT",
                        "step4_status": "WAIT",
                        "step25_status": "WAIT",
                        "step2_step4_50_line": None,
                        "step4_step5_75_line": None,
                        "invalidation_reason": None,
                        "continuation_type": "none",
                    },
                }

            entry_agent.run_once = fake_run_once
            status = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once
            entry_agent.load_entry_state = original_load_entry_state

        self.assertTrue(status["step2_lifecycle_window_terminated"])
        self.assertEqual(status["active_liquidity_name"], "ONL/YL")
        self.assertEqual(status["active_liquidity_group"]["name"], "LOW 2")
        self.assertEqual(status["active_liquidity_group"]["components"], ["ONL", "YL"])
        self.assertEqual(status["close_boundary"], 29924.5)
        self.assertEqual(status["extreme_boundary"], 29924.5)

    def test_public_active_liquidity_display_name_rebuilds_missing_frozen_group_display_name(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        name = entry_agent.public_active_liquidity_display_name(
            {
                "session_liquidity_context": {
                    "active_groups": [
                        {
                            "name": "LOW 2",
                            "side": "lower",
                            "components": ["ONL", "YL"],
                            "prices": {"ONL": 29924.5, "YL": 29924.5},
                            "close_boundary": 29924.5,
                            "extreme_boundary": 29924.5,
                        }
                    ]
                }
            },
            {"name": "LOW 2", "components": ["ONL", "YL"], "side": "lower", "close_boundary": 29924.5, "extreme_boundary": 29924.5},
            "ONL",
            29924.5,
        )

        self.assertEqual(name, "ONL/YL")

    def test_build_entry_status_exposes_frozen_group_debug_fields(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        original_load_entry_state = entry_agent.load_entry_state
        try:
            entry_agent.load_entry_state = lambda: {"symbols": {"NQ": {}}}

            def fake_run_once(_symbol: str, persist: bool = True):
                return {
                    "requested_symbol": "NQ",
                    "normalized_symbol": "NQ",
                    "latest_price": 29924.5,
                    "latest_bar_time": "2026-06-25T14:47:00Z",
                    "ohlc": {"open": 29930.0, "high": 29932.0, "low": 29924.5, "close": 29924.5},
                    "liquidity": {"tick_size": 0.25},
                    "session_liquidity_context": {
                        "locked": True,
                        "disabled": False,
                        "active_groups": [
                            {
                                "name": "LOW 2",
                                "side": "lower",
                                "components": ["ONL", "YL"],
                                "prices": {"ONL": 29924.5, "YL": 29924.5},
                                "close_boundary": 29924.5,
                                "extreme_boundary": 29924.5,
                            }
                        ],
                    },
                    "tv_context": {
                        "levels": {
                            "ONL": {"price": 29924.5, "status": "ACTIVE", "stack_group": "LOW 2"},
                            "YL": {"price": 29924.5, "status": "ACTIVE", "stack_group": "LOW 2"},
                        }
                    },
                    "step_2_1a": {"step_2_activated": False, "events": []},
                    "rejection": {"rejection_mode": "OFF"},
                    "step25": {"status": "WAIT", "next_step": "Step 2.5", "state": {}},
                    "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
                    "step4": {"status": "WAIT", "next_step": "Step 4", "state": {}},
                    "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
                    "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
                    "rejection_lane": {"lane_name": "rejection", "lane_status": "idle", "pathway_status": "idle", "active_liquidity_name": None, "active_liquidity_price": None, "liquidity_group": None, "close_boundary": None, "extreme_boundary": None, "wick_boundary_extreme": None, "candle_count": None, "step2_status": "WAIT", "step25_status": "WAIT", "step4_status": "WAIT", "step2_step4_50_line": None, "step4_step5_75_line": None, "invalidation_reason": None},
                    "continuation_lane": {"lane_name": "continuation", "lane_status": "idle", "pathway_status": "idle", "active_liquidity_name": None, "active_liquidity_price": None, "liquidity_group": None, "close_boundary": None, "extreme_boundary": None, "wick_boundary_extreme": None, "candle_count": None, "step2_status": "WAIT", "step25_status": "WAIT", "step4_status": "WAIT", "step2_step4_50_line": None, "step4_step5_75_line": None, "invalidation_reason": None, "continuation_type": "none"},
                }

            entry_agent.run_once = fake_run_once
            status = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once
            entry_agent.load_entry_state = original_load_entry_state

        self.assertTrue(status["frozen_group_found"])
        self.assertEqual(status["frozen_group_display_name"], "YL/ONL Liquidity")
        self.assertEqual(status["canonical_group_display_name"], "YL/ONL Liquidity")
        self.assertIn(status["selected_liquidity_name"], {"ONL", "YL"})
        self.assertEqual(status["frozen_active_groups"][0]["name"], "LOW 2")
        self.assertEqual(status["frozen_active_groups"][0]["components"], ["ONL", "YL"])

    def test_locked_entry_status_exposes_step2_lifecycle_window_terminated_debug_field(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        status = entry_agent.locked_entry_status(
            "NQ",
            {"requested_symbol": "NQ", "latest_bar_time": "2026-06-26T13:10:00Z", "ohlc": {}},
            "PRE_RTH_LOCK",
            "Awaiting 6:15 RTH activation line.",
        )

        self.assertIn("step2_lifecycle_window_terminated", status)
        self.assertFalse(status["step2_lifecycle_window_terminated"])

    def test_legacy_levels_are_not_reused_for_other_roots(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import levels
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_levels_path = levels.LEVELS_PATH
        original_by_symbol_path = levels.LEVELS_BY_SYMBOL_PATH
        original_context_path = levels.TV_CONTEXT_PATH
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            levels.LEVELS_PATH = temp_path / "levels.json"
            levels.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            levels.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            levels.LEVELS_PATH.write_text(json.dumps({"ONH": 27542.5}), encoding="utf-8")
            levels.TV_CONTEXT_PATH.write_text(json.dumps({"normalized_symbol": "NQ"}), encoding="utf-8")

            self.assertEqual(levels.load_levels("NQM6")["ONH"], 27542.5)
            self.assertIsNone(levels.load_levels("YMM6")["ONH"])
        levels.LEVELS_PATH = original_levels_path
        levels.LEVELS_BY_SYMBOL_PATH = original_by_symbol_path
        levels.TV_CONTEXT_PATH = original_context_path

    def test_symbol_root_normalization_supports_contract_and_tv_symbols(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import levels
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        self.assertEqual(levels.root_symbol("NQM6"), "NQ")
        self.assertEqual(levels.root_symbol("YMM6"), "YM")
        self.assertEqual(levels.root_symbol("RTYM6"), "RTY")
        self.assertEqual(levels.root_symbol("YM1!"), "YM")
        self.assertEqual(levels.root_symbol("RTY1!"), "RTY")

    def test_rithmic_atr_snapshot_is_available_by_alias(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        with tempfile.TemporaryDirectory() as temp_dir:
            atr_path = Path(temp_dir) / "rithmic_atr_snapshot.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = atr_path
            atr_path.write_text(
                json.dumps({
                    "symbols": {
                        "YM": {
                            "atr_value": 6.25,
                            "atr_bar_timestamp": "2026-05-05T18:26:00Z",
                            "atr_source": "test",
                        }
                    }
                }),
                encoding="utf-8",
            )

            atr = entry_agent.load_rithmic_atr_snapshot("YMM6")
            self.assertIsNotNone(atr)
            self.assertEqual(atr["atr_1m_14"], 6.25)
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path

    def test_step2_without_active_liquidity_has_step2_wait_reason(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        reason = entry_agent.wait_reason_for_current_step(
            "Step 2",
            None,
            False,
            {"status": "WAIT", "reason": "Step 4 waiting."},
            {"status": "WAIT", "reason": "Step 5 waiting."},
            {"status": "WAIT", "reason": "Step 6 waiting."},
        )
        self.assertEqual(reason, "No active liquidity selected.")

    def test_nq_publication_gate_blocks_step4_until_step3_passes(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        snapshot = {
            "normalized_symbol": "NQ",
            "latest_price": 29192.5,
            "ohlc_is_closed": True,
            "rejection": {"rejection_mode": "ON"},
            "step25": {"status": "READY"},
            "step3": {"status": "WAIT", "next_step": "Step 3"},
            "step4": {"status": "WAIT", "next_step": "Step 4"},
            "step5": {"status": "WAIT"},
            "step6": {"status": "WAIT"},
        }

        self.assertEqual(entry_agent.current_step_from_snapshot(snapshot), "Step 2")
        self.assertEqual(snapshot["publication_gate_debug"][0]["attempted_step"], "Step 4")
        self.assertIn("Step 3 officially passes", snapshot["publication_gate_debug"][0]["reason"])

    def test_nq_publication_gate_blocks_step5_until_leg1_locked(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        snapshot = {
            "normalized_symbol": "NQ",
            "latest_price": 29192.5,
            "ohlc_is_closed": True,
            "rejection": {"rejection_mode": "ON"},
            "step25": {"status": "READY"},
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4"},
            "step4": {
                "status": "READY",
                "next_step": "Step 5",
                "state": {"leg1_status": "WAIT", "leg1_state_locked": False},
            },
            "step5": {"status": "WAIT"},
            "step6": {"status": "WAIT"},
        }

        self.assertEqual(entry_agent.current_step_from_snapshot(snapshot), "Step 2")
        self.assertEqual(snapshot["publication_gate_debug"][0]["attempted_step"], "Step 4")
        self.assertIn("Leg 1 is close-confirmed", snapshot["publication_gate_debug"][0]["reason"])

    def test_nq_publication_gate_blocks_step6_until_leg2_locked(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        leg1_state = {
            "leg1_status": "COMPLETE",
            "leg1_state_locked": True,
            "leg1_reference_price": 29171.5,
            "leg1_reference_candle_time": "2026-05-13T13:56:00Z",
            "leg1_direction": "SHORT",
            "active_liquidity": {"name": "PML", "price": 29200.0},
            "leg1_completed_at": "2026-05-13T13:56:00Z",
            "current_active_sequence_started_at": "2026-05-13T13:55:00Z",
            "candle_a": {"timestamp": "2026-05-13T13:55:00Z"},
            "candle_b": {"timestamp": "2026-05-13T13:56:00Z"},
        }
        snapshot = {
            "normalized_symbol": "NQ",
            "latest_price": 29160.75,
            "ohlc_is_closed": True,
            "rejection": {"rejection_mode": "ON"},
            "step25": {"status": "READY"},
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4"},
            "step4": {"status": "READY", "next_step": "Step 5", "state": leg1_state},
            "step5": {"status": "READY", "next_step": "Step 6", "state": {"leg2_status": "WAIT"}},
            "step6": {"status": "ENTRY_CONFIRMED"},
        }

        self.assertEqual(entry_agent.current_step_from_snapshot(snapshot), "Step 4")
        self.assertEqual(snapshot["publication_gate_debug"][0]["attempted_step"], "Step 6")
        self.assertIn("Leg 2 are close-confirmed", snapshot["publication_gate_debug"][0]["reason"])

    def test_nq_publication_gate_allows_step6_after_leg2_validated(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        leg1_state = {
            "leg1_status": "COMPLETE",
            "leg1_state_locked": True,
            "leg1_reference_price": 29171.5,
            "leg1_reference_candle_time": "2026-05-13T13:56:00Z",
            "leg1_direction": "SHORT",
            "active_liquidity": {"name": "PML", "price": 29200.0},
            "leg1_completed_at": "2026-05-13T13:56:00Z",
            "current_active_sequence_started_at": "2026-05-13T13:55:00Z",
            "candle_a": {"timestamp": "2026-05-13T13:55:00Z"},
            "candle_b": {"timestamp": "2026-05-13T13:56:00Z"},
        }
        snapshot = {
            "normalized_symbol": "NQ",
            "latest_price": 29160.75,
            "ohlc_is_closed": True,
            "rejection": {"rejection_mode": "ON"},
            "step25": {"status": "READY"},
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4"},
            "step4": {"status": "READY", "next_step": "Step 5", "state": leg1_state},
            "step5": {"status": "READY", "next_step": "Step 6", "state": {"leg2_status": "VALIDATED"}},
            "step6": {"status": "ENTRY_CONFIRMED"},
        }

        self.assertEqual(entry_agent.current_step_from_snapshot(snapshot), "Step 6")
        self.assertNotIn("publication_gate_debug", snapshot)

    def test_continuation_step2_sr_requires_bullish_close_back_across_lower_liquidity(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step25_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        prev_candle = {"open": 29204.0, "high": 29205.0, "low": 29190.0, "close": 29192.5}
        bullish_reclaim = {"open": 29191.0, "high": 29208.0, "low": 29188.0, "close": 29206.0}
        bearish_reclaim = {"open": 29208.0, "high": 29210.0, "low": 29188.0, "close": 29206.0}

        valid = step25_engine.select_pathway(bullish_reclaim, prev_candle, 29200.0, "LL", active_liquidity_selected=True)
        invalid = step25_engine.select_pathway(bearish_reclaim, prev_candle, 29200.0, "LL", active_liquidity_selected=True)

        self.assertEqual(valid["status"], "READY")
        self.assertEqual(valid["controlling_mode"], "S/R")
        self.assertEqual(valid["activation_type"], "close")
        self.assertEqual(invalid["status"], "WAIT")

    def test_continuation_step2_rs_requires_bearish_close_back_across_upper_liquidity(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step25_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        prev_candle = {"open": 29402.0, "high": 29415.0, "low": 29401.0, "close": 29408.0}
        bearish_reclaim = {"open": 29409.0, "high": 29412.0, "low": 29390.0, "close": 29396.0}
        bullish_reclaim = {"open": 29394.0, "high": 29412.0, "low": 29390.0, "close": 29396.0}

        valid = step25_engine.select_pathway(bearish_reclaim, prev_candle, 29400.0, "LH", active_liquidity_selected=True)
        invalid = step25_engine.select_pathway(bullish_reclaim, prev_candle, 29400.0, "LH", active_liquidity_selected=True)

        self.assertEqual(valid["status"], "READY")
        self.assertEqual(valid["controlling_mode"], "R/S")
        self.assertEqual(valid["activation_type"], "close")
        self.assertEqual(invalid["status"], "WAIT")

    def test_continuation_step2_does_not_activate_on_wick_without_close_back_across(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step25_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        prev_candle = {"open": 29204.0, "high": 29206.0, "low": 29190.0, "close": 29192.5}
        wick_only = {"open": 29191.0, "high": 29205.0, "low": 29180.0, "close": 29196.0}

        result = step25_engine.select_pathway(wick_only, prev_candle, 29200.0, "LL", active_liquidity_selected=True)

        self.assertEqual(result["status"], "WAIT")
        self.assertIsNone(result["controlling_mode"])

    def test_same_candle_wick_reclaim_does_not_activate_continuation(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step25_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        candle = {"open": 29196.0, "high": 29208.0, "low": 29188.0, "close": 29198.0}
        result = step25_engine.evaluate_step25(
            {
                "rejection_mode": "ON",
                "initial_candle_a": candle,
                "controlling_mode": "S/R",
                "candidate_modes": ["S/R"],
                "provisional_candle_a": candle,
                "pathway_activation_type": "wick",
                "continuation_step2_activated": True,
                "events": [],
            }
        )

        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["state"]["controlling_mode"], "Normal Rejection Mode")
        self.assertEqual(result["state"]["pathway_activation_type"], "normal")
        self.assertIsNone(result["state"]["provisional_candle_a"])

    def test_continuation_step2_requires_active_liquidity_selected(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step25_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        prev_candle = {"open": 29204.0, "high": 29205.0, "low": 29190.0, "close": 29192.5}
        bullish_reclaim = {"open": 29191.0, "high": 29208.0, "low": 29188.0, "close": 29206.0}

        result = step25_engine.select_pathway(bullish_reclaim, prev_candle, 29200.0, "LL", active_liquidity_selected=False)

        self.assertEqual(result["status"], "WAIT")
        self.assertIsNone(result["controlling_mode"])

    def test_continuation_step2_requires_rejection_step2_confirmed(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step25_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        prev_candle = {"open": 29204.0, "high": 29205.0, "low": 29190.0, "close": 29192.5}
        bullish_reclaim = {"open": 29191.0, "high": 29208.0, "low": 29188.0, "close": 29206.0}

        result = step25_engine.select_pathway(
            bullish_reclaim,
            prev_candle,
            29200.0,
            "LL",
            active_liquidity_selected=True,
            rejection_step2_confirmed=False,
        )

        self.assertEqual(result["status"], "WAIT")
        self.assertIsNone(result["controlling_mode"])

    def test_continuation_step25_does_not_honor_requested_mode_without_step2_activation(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step25_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        candle = {"open": 29191.0, "high": 29208.0, "low": 29188.0, "close": 29206.0}
        result = step25_engine.evaluate_step25(
            {
                "rejection_mode": "ON",
                "initial_candle_a": candle,
                "controlling_mode": "S/R",
                "candidate_modes": ["S/R"],
                "reclaim_candle_a": candle,
                "continuation_step2_activated": False,
                "events": [],
            }
        )

        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["state"]["controlling_mode"], "Normal Rejection Mode")
        self.assertNotIn("S/R", result["state"]["candidate_modes"])

    def test_status_keeps_continuation_inactive_when_upper_stack_only_wicks_liquidity(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_get_latest_market_snapshot = entry_agent.get_latest_market_snapshot
        self.addCleanup(setattr, entry_agent, "get_latest_market_snapshot", original_get_latest_market_snapshot)
        entry_agent.get_latest_market_snapshot = lambda _symbol="NQ": None

        original_run_once = entry_agent.run_once
        self.addCleanup(setattr, entry_agent, "run_once", original_run_once)

        snapshot = {
            "requested_symbol": "NQ",
            "normalized_symbol": "NQ",
            "latest_price": 30672.0,
            "latest_bar_time": "2026-06-19T13:37:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 30673.5, "high": 30675.75, "low": 30670.5, "close": 30672.0},
            "liquidity": {"tick_size": 0.25},
            "step_2_1a": {
                "step_2_activated": False,
                "candle_a": None,
                "active_level": "LH",
                "level_price": 30674.0,
                "side": "upper",
                "last_evaluated_bar_time": "2026-06-19T13:37:00Z",
                "active_liquidity_group": {
                    "name": "HIGH 1",
                    "display_name": "LH/PMH Liquidity",
                    "components": ["LH", "PMH"],
                    "side": "upper",
                    "close_boundary": 30674.0,
                    "extreme_boundary": 30678.25,
                    "close_component": "LH",
                    "extreme_component": "PMH",
                },
                "last_interacted_liquidity": {
                    "name": "LH",
                    "price": 30674.0,
                    "display_name": "LH/PMH Liquidity",
                    "side": "upper",
                },
                "events": [{"event": "pre_activation_probe_detected", "timestamp": "2026-06-19T13:30:00Z"}],
            },
            "rejection": {"rejection_mode": "OFF"},
            "step25": {
                "status": "WAIT",
                "next_step": "Step 2.5",
                "state": {
                    "controlling_mode": "R/S",
                    "candidate_modes": ["R/S"],
                    "continuation_step2_activated": False,
                },
            },
            "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
            "step4": {"status": "WAIT", "next_step": "Step 4", "state": {}},
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        entry_agent.run_once = lambda _symbol="NQ", persist=True: copy.deepcopy(snapshot)

        status = entry_agent.build_entry_status("NQ")

        self.assertEqual(status["current_step"], "Step 2")
        self.assertEqual(status["current_pathway_control"], "inactive")
        self.assertEqual(status["continuation_pathway_status"], "inactive")
        self.assertEqual(status["continuation_side"]["pathway_status"], "inactive")
        self.assertEqual(status["sr_rs_context"], None)
        self.assertEqual(status["extreme_boundary"], 30678.25)

    def test_active_liquidity_selection_uses_active_tv_stack_zone(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        tv_context = {
            "levels": {
                "YH": {"price": 105.0, "status": "INACTIVE", "stack_group": "HIGH 1"},
                "ONH": {"price": 101.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "LH": {"price": 99.0, "status": "ACTIVE", "stack_group": "NONE"},
                "YL": {"price": 90.0, "status": "ACTIVE", "stack_group": "NONE"},
            }
        }

        selected = entry_agent.selected_active_liquidity_from_context(
            tv_context,
            100.25,
            {"open": 99.75, "high": 100.5, "low": 99.5, "close": 100.25},
        )

        self.assertEqual(selected["name"], "ONH")
        self.assertEqual(selected["price"], 101.0)
        self.assertEqual(selected["group"]["name"], "HIGH 1")
        self.assertEqual(selected["group"]["components"], ["ONH", "PMH"])
        self.assertEqual(selected["group"]["extreme_component"], "ONH")
        self.assertEqual(selected["group"]["close_component"], "PMH")
        self.assertNotIn("YH", selected["group"]["components"])

    def test_active_liquidity_upper_stack_selects_highest_actionable_component(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        selected = entry_agent.selected_active_liquidity_from_context(
            {
                "levels": {
                    "PMH": {"price": 29200.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "ONH": {"price": 29205.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                }
            },
            29209.0,
            {"open": 29206.0, "high": 29210.0, "low": 29204.0, "close": 29209.0},
        )

        self.assertEqual(selected["display_name"], "PMH/ONH Liquidity")
        self.assertEqual(selected["name"], "ONH")
        self.assertEqual(selected["price"], 29205.0)
        self.assertEqual(selected["group"]["extreme_component"], "ONH")
        self.assertEqual(selected["group"]["close_component"], "PMH")

    def test_ym_stacked_upper_lh_pmh_selects_on_wick_without_forcing_step2(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        candle = {"open": 50755.0, "high": 50771.0, "low": 50754.0, "close": 50759.0}
        selected = entry_agent.selected_active_liquidity_from_context(
            {
                "levels": {
                    "LH": {"price": 50763.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "PMH": {"price": 50764.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                }
            },
            50759.0,
            candle,
            tick_size=1.0,
        )

        self.assertEqual(selected["display_name"], "LH/PMH Liquidity")
        self.assertEqual(selected["group"]["display_name"], "LH/PMH Liquidity")
        self.assertEqual(selected["group"]["close_boundary"], 50763.0)
        self.assertEqual(selected["group"]["extreme_boundary"], 50764.0)
        self.assertEqual(selected["group"]["close_component"], "LH")
        self.assertEqual(selected["group"]["extreme_component"], "PMH")

        step2 = entry_agent.step_2_1a_initial_state(selected["name"], selected["price"], selected["side"], 1.0)
        entry_agent.evaluate_step_2_1a_candle(
            step2,
            {
                **candle,
                "timestamp": "2026-06-10T13:45:00Z",
                "active_level": selected["name"],
                "level_price": selected["price"],
            },
            0,
        )
        self.assertFalse(step2["step_2_activated"])
        self.assertEqual(step2["events"][0]["event"], "pre_activation_probe_detected")

    def test_active_liquidity_lower_stack_selects_lowest_actionable_component(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        selected = entry_agent.selected_active_liquidity_from_context(
            {
                "levels": {
                    "PML": {"price": 29000.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                    "ONL": {"price": 28995.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                }
            },
            28991.0,
            {"open": 28994.0, "high": 28996.0, "low": 28990.0, "close": 28991.0},
        )

        self.assertEqual(selected["display_name"], "PML/ONL Liquidity")
        self.assertEqual(selected["name"], "ONL")
        self.assertEqual(selected["price"], 28995.0)
        self.assertEqual(selected["group"]["extreme_component"], "ONL")
        self.assertEqual(selected["group"]["close_component"], "PML")

    def test_ym_equal_price_pml_onl_stack_displays_close_boundary_owner_first(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        selected = entry_agent.selected_active_liquidity_from_context(
            {
                "levels": {
                    "ONL": {"price": 50576.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                    "PML": {"price": 50576.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                }
            },
            50574.0,
            {"open": 50578.0, "high": 50579.0, "low": 50572.0, "close": 50574.0},
            tick_size=1.0,
        )

        self.assertEqual(selected["display_name"], "PML/ONL Liquidity")
        self.assertEqual(selected["group"]["display_name"], "PML/ONL Liquidity")
        self.assertEqual(selected["group"]["close_boundary"], 50576.0)
        self.assertEqual(selected["group"]["extreme_boundary"], 50576.0)
        self.assertEqual(selected["group"]["name"], "LOW 1")
        self.assertEqual(selected["group"]["close_component"], "PML")

    def test_lower_stack_exact_one_tick_beyond_close_boundary_activates(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        selected = entry_agent.selected_active_liquidity_from_context(
            {
                "levels": {
                    "PML": {"price": 100.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                    "ONL": {"price": 99.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                }
            },
            99.75,
            {"open": 100.25, "high": 100.5, "low": 99.5, "close": 99.75},
            tick_size=0.25,
        )

        self.assertEqual(selected["display_name"], "PML/ONL Liquidity")
        self.assertEqual(selected["name"], "ONL")
        self.assertEqual(selected["group"]["close_boundary"], 100.0)
        self.assertEqual(selected["group"]["extreme_boundary"], 99.0)
        self.assertEqual(selected["group"]["close_component"], "PML")

    def test_nq_single_active_liquidity_selection_still_works_unchanged(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        selected = entry_agent.selected_active_liquidity_from_context(
            {
                "levels": {
                    "PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "PML": {"price": 95.0, "status": "ACTIVE", "stack_group": "NONE"},
                }
            },
            100.25,
            {"open": 99.5, "high": 100.25, "low": 99.25, "close": 99.75},
            tick_size=0.25,
        )

        self.assertEqual(selected["display_name"], None)
        self.assertEqual(selected["name"], "PMH")
        self.assertEqual(selected["price"], 100.0)

    def test_standalone_active_liquidity_publishes_level_price_as_both_boundaries(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot
        original_load_tv_context = entry_agent.load_tv_context
        original_load_atr = entry_agent.load_rithmic_atr_snapshot

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"

            entry_agent.get_latest_market_snapshot = lambda _symbol="NQ": {
                "symbol": "NQM6",
                "normalized_symbol": "NQ",
                "latest_price": 100.25,
                "latest_bar_time": "2026-06-16T13:31:00Z",
                "ohlc_is_closed": True,
                "ohlc": {
                    "open": 99.5,
                    "high": 100.5,
                    "low": 99.25,
                    "close": 100.25,
                },
            }
            entry_agent.load_tv_context = lambda _symbol=None: {
                "normalized_symbol": "NQ",
                "locked": True,
                "levels": {
                    "PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "PML": {"price": 95.0, "status": "ACTIVE", "stack_group": "NONE"},
                },
            }
            entry_agent.load_rithmic_atr_snapshot = lambda _symbol="NQ": {"atr_1m_14": 10.0}

            try:
                status = entry_agent.build_entry_status("NQM6")
            finally:
                entry_agent.STATE_PATH = original_state_path
                entry_agent.TV_CONTEXT_PATH = original_context_path
                entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
                entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
                entry_agent.get_latest_market_snapshot = original_market_snapshot
                entry_agent.load_tv_context = original_load_tv_context
                entry_agent.load_rithmic_atr_snapshot = original_load_atr

        self.assertEqual(status["active_liquidity_name"], "PMH")
        self.assertEqual(status["active_liquidity_group"], None)
        self.assertEqual(status["close_boundary"], 100.0)
        self.assertEqual(status["extreme_boundary"], 100.0)

    def test_inactive_broken_pml_rotates_to_onl_same_stack_target(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

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
        self.assertEqual(result["level_price"], 49984.0)
        self.assertEqual(result["last_interacted_liquidity"]["name"], "ONL")
        self.assertEqual(result["active_liquidity_group"]["name"], "LOW 1")

    def test_nq_ll_exhaustion_rotates_to_onl_and_does_not_flip_back(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        market = {
            "latest_price": 28655.5,
            "latest_bar_time": "2026-05-07T13:15:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 28670.0, "high": 28670.25, "low": 28648.5, "close": 28655.5},
        }

        def fake_market_snapshot(_root):
            return {
                "source": "test",
                "symbol": "NQM6",
                "latest_price": market["latest_price"],
                "latest_bar_time": market["latest_bar_time"],
                "ohlc_is_closed": market["ohlc_is_closed"],
                "ohlc": dict(market["ohlc"]),
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = fake_market_snapshot
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "levels": {
                                    "LL": {"price": 28690.25, "status": "ACTIVE", "stack_group": "LOW 1"},
                                    "ONL": {"price": 28637.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "PML": {"price": 28717.0, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            ll_close = entry_agent.build_entry_status("NQM6")
            self.assertEqual(ll_close["active_liquidity_name"], "LL")
            self.assertEqual(ll_close["active_liquidity_price"], 28690.25)
            self.assertNotEqual(ll_close["leg1_status"], "COMPLETE")

            market.update(
                {
                    "latest_price": 28629.75,
                    "latest_bar_time": "2026-05-07T13:18:00Z",
                    "ohlc": {"open": 28644.75, "high": 28649.0, "low": 28625.0, "close": 28629.75},
                }
            )
            onl_reached = entry_agent.build_entry_status("NQM6")
            self.assertEqual(onl_reached["active_liquidity_name"], "ONL")
            self.assertEqual(onl_reached["active_liquidity_price"], 28637.0)

            market.update(
                {
                    "latest_price": 28658.5,
                    "latest_bar_time": "2026-05-07T13:22:00Z",
                    "ohlc": {"open": 28628.75, "high": 28660.0, "low": 28627.0, "close": 28658.5},
                }
            )
            after_onl_touch = entry_agent.build_entry_status("NQM6")
            self.assertEqual(after_onl_touch["active_liquidity_name"], "ONL")
            self.assertEqual(after_onl_touch["active_liquidity_price"], 28637.0)
            self.assertNotEqual(after_onl_touch["active_liquidity_name"], "LL")

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_no_leg1_50_percent_exhaustion_does_not_rotate_to_next_same_side_target(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        persisted_liquidity = {"name": "LL", "price": 100.0, "side": "lower"}
        persisted_state = {
            "last_interacted_liquidity_by_symbol": {"NQ": persisted_liquidity},
            "state_by_symbol": {
                "NQ": {
                    "last_interacted_liquidity": persisted_liquidity,
                    "step4": {"status": "WAIT", "state": {}},
                    "consumed_liquidity_levels": [],
                }
            },
        }
        snapshot = {
            "symbol": "NQM6",
            "normalized_symbol": "NQ",
            "latest_price": 95.0,
            "latest_bar_time": "2026-05-07T16:16:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 100.5, "high": 101.0, "low": 94.75, "close": 95.0},
            "tv_context": {
                "levels": {
                    "LL": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "ONL": {"price": 90.0, "status": "ACTIVE", "stack_group": "NONE"},
                }
            },
        }

        result = entry_agent.evaluate_live_step_2_1a(snapshot, {}, {"tick_size": 0.25}, persisted_state)

        self.assertEqual(result["active_level"], "LL")
        self.assertEqual(result["level_price"], 100.0)
        self.assertFalse(
            any(
                record.get("name") == "LL"
                and record.get("exhaustion_type") == "no_leg1_50_percent_exhaustion"
                for record in result["consumed_liquidity_levels"]
            )
        )

    def test_leg1_lock_prevents_rotation_to_next_same_side_target(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        candle_a = {"timestamp": "2026-05-07T16:18:00Z", "open": 101.0, "high": 101.5, "low": 99.0, "close": 99.5}
        candle_b = {"timestamp": "2026-05-07T16:19:00Z", "open": 99.5, "high": 100.0, "low": 98.5, "close": 100.0}
        persisted_liquidity = {"name": "LL", "price": 100.0, "side": "lower"}
        step4_state = {
            "leg1_state_locked": True,
            "leg1_status": "COMPLETE",
            "active_liquidity": persisted_liquidity,
            "candle_a": candle_a,
            "candle_b": candle_b,
            "leg1_completed_at": candle_b["timestamp"],
            "leg1_reference_price": candle_a["close"],
            "leg1_reference_candle_time": candle_a["timestamp"],
            "leg1_direction": "LONG",
            "setup_direction": "LONG",
            "current_active_sequence_started_at": candle_a["timestamp"],
        }
        persisted_state = {
            "last_interacted_liquidity_by_symbol": {"NQ": persisted_liquidity},
            "state_by_symbol": {
                "NQ": {
                    "last_interacted_liquidity": persisted_liquidity,
                    "step4": {"status": "READY", "state": step4_state, "next_step": "Step 5"},
                    "step5": {"status": "WAIT", "state": {"leg2_status": "WAIT"}, "next_step": "Step 5"},
                    "consumed_liquidity_levels": [],
                }
            },
        }
        snapshot = {
            "symbol": "NQM6",
            "normalized_symbol": "NQ",
            "latest_price": 96.0,
            "latest_bar_time": "2026-05-07T16:20:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 99.0, "high": 99.25, "low": 92.5, "close": 96.0},
            "tv_context": {
                "levels": {
                    "LL": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "ONL": {"price": 90.0, "status": "ACTIVE", "stack_group": "NONE"},
                }
            },
        }

        result = entry_agent.evaluate_live_step_2_1a(snapshot, {}, {"tick_size": 0.25}, persisted_state)

        self.assertEqual(result["active_level"], "LL")
        self.assertEqual(result["level_price"], 100.0)
        self.assertFalse(
            any(
                record.get("name") == "LL"
                and record.get("exhausted_by") == "ONL"
                for record in result["consumed_liquidity_levels"]
            )
        )

    def test_opposite_side_liquidity_breach_releases_stale_step2_lock_and_rearms_next_candle(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        locked_group = {
            "name": "LOW 1",
            "components": ["LL", "PML"],
            "prices": {"LL": 30509.5, "PML": 30538.5},
            "side": "lower",
            "display_name": "PML/LL Liquidity",
            "close_boundary": 30538.5,
            "extreme_boundary": 30509.5,
            "low": 30509.5,
            "high": 30538.5,
            "extreme_component": "LL",
            "close_component": "PML",
        }
        locked_active = {
            "name": "LL",
            "price": 30509.5,
            "display_name": "PML/LL Liquidity",
            "side": "lower",
            "group": locked_group,
        }
        locked_owner = {
            "pathway": "rejection",
            "active_liquidity": locked_active,
            "active_liquidity_name": "LL",
            "active_liquidity_price": 30509.5,
            "active_liquidity_display_name": "PML/LL Liquidity",
            "active_liquidity_group": locked_group,
            "liquidity_group": "LOW 1",
            "stack_components": ["LL", "PML"],
            "close_boundary": 30538.5,
            "extreme_boundary": 30509.5,
            "setup_direction": "LONG",
            "side": "lower",
            "candle_a": {
                "open": 30300.0,
                "high": 30310.0,
                "low": 30297.5,
                "close": 30306.0,
                "timestamp": "2026-06-15T13:15:00Z",
                "active_level": "LL",
                "level_price": 30509.5,
            },
            "activated_at": "2026-06-15T13:15:00Z",
        }
        tv_context = {
            "normalized_symbol": "NQ",
            "levels": {
                "PMH": {"price": 30616.75, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "PML": {"price": 30538.5, "status": "ACTIVE", "stack_group": "LOW 1"},
                "LH": {"price": 30628.25, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "LL": {"price": 30509.5, "status": "ACTIVE", "stack_group": "LOW 1"},
                "ONH": {"price": 30628.25, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "ONL": {"price": 30191.0, "status": "ACTIVE", "stack_group": "NONE"},
                "YH": {"price": 29760.0, "status": "REACTIVATED", "stack_group": "NONE"},
                "YL": {"price": 29230.0, "status": "ACTIVE", "stack_group": "NONE"},
            },
        }
        persisted_state = {
            "state_by_symbol": {
                "NQ": {
                    "step_2_1a": {
                        "step_2_activated": True,
                        "active_level": "LL",
                        "level_price": 30509.5,
                        "side": "lower",
                        "step2_locked_owner": locked_owner,
                        "last_interacted_liquidity": locked_active,
                    },
                    "step2_locked_owner": locked_owner,
                    "last_interacted_liquidity": locked_active,
                    "step_2_1a_candle_index": 494,
                    "step4": {"status": "WAIT", "state": {}},
                    "step5": {"status": "WAIT", "state": {}},
                    "consumed_liquidity_levels": [],
                }
            },
            "last_interacted_liquidity_by_symbol": {"NQ": locked_active},
        }
        breach_snapshot = {
            "symbol": "NQU6",
            "normalized_symbol": "NQ",
            "requested_symbol": "NQ",
            "latest_price": 30704.75,
            "latest_bar_time": "2026-06-15T13:59:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 30728.75, "high": 30733.0, "low": 30696.5, "close": 30697.75},
            "tv_context": copy.deepcopy(tv_context),
        }

        released = entry_agent.evaluate_live_step_2_1a(
            breach_snapshot,
            {},
            {"tick_size": 0.25},
            persisted_state,
        )

        self.assertFalse(released["step_2_activated"])
        self.assertIsNone(released["active_level"])
        self.assertIsNone(released.get("step2_locked_owner"))
        self.assertEqual(released["reason"], entry_agent.OPPOSITE_SIDE_LIQUIDITY_BREACH_RELEASE)
        self.assertEqual(released["state_transition_reason"], entry_agent.OPPOSITE_SIDE_LIQUIDITY_BREACH_RELEASE)
        self.assertEqual(released["audit_step2_event"], "opposite_side_liquidity_breach_release")

        next_persisted_state = {
            "state_by_symbol": {
                "NQ": {
                    "step_2_1a": released,
                    "step2_locked_owner": released.get("step2_locked_owner"),
                    "last_interacted_liquidity": released.get("last_interacted_liquidity"),
                    "step_2_1a_candle_index": released.get("next_candle_index"),
                    "step4": {"status": "WAIT", "state": {}},
                    "step5": {"status": "WAIT", "state": {}},
                    "consumed_liquidity_levels": released.get("consumed_liquidity_levels", []),
                }
            },
            "last_interacted_liquidity_by_symbol": {},
        }
        next_snapshot = {
            "symbol": "NQU6",
            "normalized_symbol": "NQ",
            "requested_symbol": "NQ",
            "latest_price": 30723.5,
            "latest_bar_time": "2026-06-15T14:00:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 30698.0, "high": 30715.75, "low": 30689.75, "close": 30702.75},
            "tv_context": copy.deepcopy(tv_context),
        }

        rearmed = entry_agent.evaluate_live_step_2_1a(
            next_snapshot,
            {},
            {"tick_size": 0.25},
            next_persisted_state,
        )

        self.assertTrue(rearmed["step_2_activated"])
        self.assertEqual(rearmed["active_level"], "ONH")
        self.assertEqual(rearmed["level_price"], 30628.25)
        self.assertEqual(rearmed["reason"], "Step 2.1A evaluated from live completed candle.")

    def test_current_step_remains_step2_when_active_liquidity_selected(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        snapshot = {
            "latest_price": 101.0,
            "ohlc": {"open": 100.5, "high": 101.0, "low": 100.25, "close": 101.0},
            "tv_context": {
                "levels": {
                    "ONH": {"price": 101.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "PMH": {"price": 100.0, "status": "INACTIVE", "stack_group": "NONE"},
                }
            },
            "rejection": {"rejection_mode": "OFF"},
            "step25": {"status": "WAIT"},
            "step3": {"status": "WAIT"},
            "step4": {"status": "WAIT"},
            "step5": {"status": "WAIT"},
            "step6": {"status": "WAIT"},
        }

        self.assertEqual(entry_agent.current_step_from_snapshot(snapshot), "Step 2")

    def test_observation_reset_clears_prior_day_leg1_state_and_confirms_step2(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        def fake_market_snapshot(_root):
            return {
                "source": "test",
                "symbol": "NQM6",
                "latest_price": 21425.0,
                "latest_bar_time": "2026-05-15T13:29:00Z",
                "ohlc_is_closed": True,
                "ohlc": {"open": 21410.0, "high": 21430.0, "low": 21408.0, "close": 21425.0},
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = fake_market_snapshot
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "locked": True,
                                "levels": {
                                    "PMH": {"price": 21420.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "PML": {"price": 21320.0, "status": "INACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            entry_agent.STATE_PATH.write_text(
                json.dumps(
                    {
                        "state_by_symbol": {
                            "NQ": {
                                "observation_reset_session_date": "2026-05-14",
                                "last_interacted_liquidity": {"name": "PML", "price": 21320.0, "side": "lower"},
                                "step25": {"status": "READY", "state": {"controlling_mode": "R/S"}},
                                "step4": {
                                    "status": "READY",
                                    "state": {
                                        "leg1_state_locked": True,
                                        "leg1_status": "COMPLETE",
                                        "leg1_completed_at": "2026-05-14T13:42:00Z",
                                        "leg1_reference_price": 21310.0,
                                        "leg1_reference_candle_time": "2026-05-14T13:41:00Z",
                                        "leg1_direction": "LONG",
                                        "active_liquidity": {"name": "PML", "price": 21320.0, "side": "lower"},
                                        "candle_a": {"timestamp": "2026-05-14T13:41:00Z"},
                                        "candle_b": {"timestamp": "2026-05-14T13:42:00Z"},
                                    },
                                },
                            }
                        },
                        "last_interacted_liquidity_by_symbol": {
                            "NQ": {"name": "PML", "price": 21320.0, "side": "lower"}
                        },
                    }
                ),
                encoding="utf-8",
            )

            status = entry_agent.build_entry_status("NQM6")
            state = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

        self.assertEqual(status["active_liquidity_name"], "PMH")
        self.assertEqual(status["current_step"], "Step 2")
        self.assertEqual(status["current_step_status"], "CONFIRMED")
        self.assertEqual(status["rejection_pathway_status"], "controlling")
        self.assertEqual(status["current_pathway_control"], "rejection")
        self.assertEqual(status["selected_pathway"], "rejection")
        self.assertIsNone(status["leg1_completed_at"])
        self.assertEqual(state["state_by_symbol"]["NQ"]["observation_reset_session_date"], "2026-05-15")

    def test_observation_window_blocks_entry_authorization_until_0630(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        entry_agent.run_once = lambda symbol, persist=True: {
            "requested_symbol": symbol,
            "normalized_symbol": "NQ",
            "latest_price": 100.0,
            "latest_bar_time": "2026-05-15T13:29:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
            "liquidity": {},
            "step_2_1a": {"step_2_activated": True, "active_level": "PMH", "level_price": 100.0, "side": "upper"},
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 100.0},
            "step25": {"status": "READY", "state": {"controlling_mode": "Normal Rejection Mode"}},
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4", "state": {}},
            "step4": {"status": "WAIT", "next_step": "Step 4", "state": {}},
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "ENTRY_CONFIRMED", "next_step": "Step 6", "state": {"entry_triggered": True}, "reason": "ready"},
        }
        try:
            status = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(status["entry_status"], "WAIT")
        self.assertIn("06:30 PT", status["wait_reason"])

    def test_entry_status_pre_rth_lock_blocks_step_progression_with_context(self):
        server = self._load_server()
        entry_agent = sys.modules["entry_agent"]

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot
        original_selected_liquidity = entry_agent.selected_active_liquidity_from_context
        self.addCleanup(setattr, entry_agent, "STATE_PATH", original_state_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_PATH", original_context_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_BY_SYMBOL_PATH", original_by_symbol_path)
        self.addCleanup(setattr, entry_agent, "get_latest_market_snapshot", original_market_snapshot)
        self.addCleanup(setattr, entry_agent, "selected_active_liquidity_from_context", original_selected_liquidity)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.get_latest_market_snapshot = lambda _symbol: {
                "source": "test",
                "symbol": "NQM6",
                "latest_price": 101.0,
                "latest_bar_time": "2026-05-18T13:04:00Z",
                "ohlc_is_closed": True,
                "ohlc": {"open": 99.0, "high": 102.0, "low": 98.5, "close": 101.0},
            }
            entry_agent.selected_active_liquidity_from_context = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("pre-RTH lock must run before active liquidity selection")
            )
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "locked": True,
                                "levels": {
                                    "PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "PML": {"price": 95.0, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            poisoned_state = {
                "state_by_symbol": {
                    "NQ": {
                        "last_interacted_liquidity": {"name": "PMH", "price": 100.0, "side": "upper"},
                        "step25": {"status": "READY", "state": {"controlling_mode": "Normal Rejection Mode"}},
                        "step4": {"status": "READY", "next_step": "Step 5", "state": {"leg1_status": "COMPLETE"}},
                        "step5": {"status": "READY", "next_step": "Step 6", "state": {"leg2_status": "COMPLETE"}},
                        "step6": {"status": "ENTRY_CONFIRMED", "state": {"entry_triggered": True}},
                    }
                },
                "last_interacted_liquidity_by_symbol": {
                    "NQ": {"name": "PMH", "price": 100.0, "side": "upper"}
                },
            }
            entry_agent.STATE_PATH.write_text(json.dumps(poisoned_state), encoding="utf-8")

            response = server.app.test_client().get("/entry/status?symbols=NQ")
            status = response.get_json()["symbols"][0]
            persisted_after = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot
        entry_agent.selected_active_liquidity_from_context = original_selected_liquidity

        self.assertEqual(response.status_code, 200)
        self.assertEqual(status["entry_status"], "WAIT")
        self.assertEqual(status["current_step"], "PRE_RTH_LOCK")
        self.assertEqual(status["wait_reason"], "Awaiting 6:15 RTH activation line.")
        self.assertEqual(status["last_decision"], "WAIT: Awaiting 6:15 RTH activation line.")
        self.assertIsNone(status["active_liquidity_name"])
        self.assertIsNone(status["selected_pathway"])
        self.assertEqual(status["rejection_pathway_status"], "inactive")
        self.assertEqual(status["continuation_pathway_status"], "inactive")
        self.assertEqual(status["continuation_type"], "none")
        self.assertNotIn(status["current_step"], {"Step 2", "Step 2.5", "Step 4", "Step 5", "Step 6"})
        self.assertEqual(persisted_after, poisoned_state)

    def test_entry_status_session_closed_blocks_new_setup_calculation(self):
        server = self._load_server()
        entry_agent = sys.modules["entry_agent"]

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot
        original_selected_liquidity = entry_agent.selected_active_liquidity_from_context
        self.addCleanup(setattr, entry_agent, "STATE_PATH", original_state_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_PATH", original_context_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_BY_SYMBOL_PATH", original_by_symbol_path)
        self.addCleanup(setattr, entry_agent, "get_latest_market_snapshot", original_market_snapshot)
        self.addCleanup(setattr, entry_agent, "selected_active_liquidity_from_context", original_selected_liquidity)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.get_latest_market_snapshot = lambda _symbol: {
                "source": "test",
                "symbol": "NQM6",
                "latest_price": 101.0,
                "latest_bar_time": "2026-05-18T15:00:00Z",
                "ohlc_is_closed": True,
                "ohlc": {"open": 99.0, "high": 102.0, "low": 98.5, "close": 101.0},
            }
            entry_agent.selected_active_liquidity_from_context = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("session-closed lock must run before active liquidity selection")
            )
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "locked": True,
                                "levels": {
                                    "PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "PML": {"price": 95.0, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            poisoned_state = {
                "state_by_symbol": {
                    "NQ": {
                        "last_interacted_liquidity": {"name": "PMH", "price": 100.0, "side": "upper"},
                        "step25": {"status": "READY", "state": {"controlling_mode": "Normal Rejection Mode"}},
                        "step4": {"status": "READY", "next_step": "Step 5", "state": {"leg1_status": "COMPLETE"}},
                        "step5": {"status": "READY", "next_step": "Step 6", "state": {"leg2_status": "COMPLETE"}},
                        "step6": {"status": "ENTRY_CONFIRMED", "state": {"entry_triggered": True}},
                    }
                },
                "last_interacted_liquidity_by_symbol": {
                    "NQ": {"name": "PMH", "price": 100.0, "side": "upper"}
                },
            }
            entry_agent.STATE_PATH.write_text(json.dumps(poisoned_state), encoding="utf-8")

            response = server.app.test_client().get("/entry/status?symbols=NQ")
            status = response.get_json()["symbols"][0]
            persisted_after = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot
        entry_agent.selected_active_liquidity_from_context = original_selected_liquidity

        self.assertEqual(response.status_code, 200)
        self.assertEqual(status["entry_status"], "WAIT")
        self.assertEqual(status["current_step"], "SESSION_CLOSED")
        self.assertEqual(status["wait_reason"], "Entry window closed at 8:00 AM PT.")
        self.assertEqual(status["last_decision"], "WAIT: Entry window closed at 8:00 AM PT.")
        self.assertIsNone(status["active_liquidity_name"])
        self.assertIsNone(status["selected_pathway"])
        self.assertEqual(status["rejection_pathway_status"], "inactive")
        self.assertEqual(status["continuation_pathway_status"], "inactive")
        self.assertEqual(status["continuation_type"], "none")
        self.assertNotIn(status["current_step"], {"Step 2", "Step 2.5", "Step 4", "Step 5", "Step 6"})
        self.assertEqual(persisted_after, poisoned_state)

    def test_pre_615_prior_date_step5_state_returns_clean_pre_rth_lock(self):
        server = self._load_server()
        entry_agent = sys.modules["entry_agent"]

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot
        self.addCleanup(setattr, entry_agent, "STATE_PATH", original_state_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_PATH", original_context_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_BY_SYMBOL_PATH", original_by_symbol_path)
        self.addCleanup(setattr, entry_agent, "get_latest_market_snapshot", original_market_snapshot)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.get_latest_market_snapshot = lambda _symbol: {
                "source": "test",
                "symbol": "NQM6",
                "latest_price": 101.0,
                "latest_bar_time": "2026-05-18T13:04:00Z",
                "ohlc_is_closed": True,
                "ohlc": {"open": 99.0, "high": 102.0, "low": 98.5, "close": 101.0},
            }
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps({"symbols": {"NQ": {"symbol": "NQ1!", "locked": True, "levels": {"PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"}}}}}),
                encoding="utf-8",
            )
            prior_state = self._prior_date_step5_state()
            entry_agent.STATE_PATH.write_text(json.dumps(prior_state), encoding="utf-8")

            response = server.app.test_client().get("/entry/status?symbols=NQ")
            status = response.get_json()["symbols"][0]
            persisted_after = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(status["current_step_label"], "Pre-RTH Lock")
        self._assert_clean_locked_status(status, "PRE_RTH_LOCK", "Awaiting 6:15 RTH activation line.")
        self.assertEqual(persisted_after, prior_state)

    def test_inside_window_prior_date_step5_state_is_ignored(self):
        server = self._load_server()
        entry_agent = sys.modules["entry_agent"]

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot
        self.addCleanup(setattr, entry_agent, "STATE_PATH", original_state_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_PATH", original_context_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_BY_SYMBOL_PATH", original_by_symbol_path)
        self.addCleanup(setattr, entry_agent, "get_latest_market_snapshot", original_market_snapshot)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.get_latest_market_snapshot = lambda _symbol: {
                "source": "test",
                "symbol": "NQM6",
                "latest_price": 99.0,
                "latest_bar_time": "2026-05-18T13:20:00Z",
                "ohlc_is_closed": True,
                "ohlc": {"open": 99.5, "high": 99.75, "low": 98.5, "close": 99.0},
            }
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "locked": True,
                                "levels": {
                                    "PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "PML": {"price": 95.0, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            entry_agent.STATE_PATH.write_text(json.dumps(self._prior_date_step5_state()), encoding="utf-8")

            response = server.app.test_client().get("/entry/status?symbols=NQ")
            status = response.get_json()["symbols"][0]

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(status["current_step"], "Step 5")
        self.assertIsNone(status["active_liquidity_name"])
        self.assertIsNone(status["active_liquidity_price"])
        self.assertIsNone(status["selected_pathway"])
        self.assertIsNone(status["setup_direction"])
        self.assertEqual(status["leg1_status"], "WAIT")
        self.assertEqual(status["leg1_state"], "WAIT")
        self.assertIsNone(status["leg1_completed_at"])
        self.assertIsNone(status["leg1_reference_price"])
        self.assertIsNone(status["leg1_reference_candle_time"])
        self.assertEqual(status["leg2_status"], "WAIT")
        self.assertIsNone(status["leg2_candidate_candle_time"])

    def test_at_or_after_800_prior_date_step5_state_returns_clean_session_closed(self):
        server = self._load_server()
        entry_agent = sys.modules["entry_agent"]

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot
        self.addCleanup(setattr, entry_agent, "STATE_PATH", original_state_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_PATH", original_context_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_BY_SYMBOL_PATH", original_by_symbol_path)
        self.addCleanup(setattr, entry_agent, "get_latest_market_snapshot", original_market_snapshot)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.get_latest_market_snapshot = lambda _symbol: {
                "source": "test",
                "symbol": "NQM6",
                "latest_price": 101.0,
                "latest_bar_time": "2026-05-18T15:00:00Z",
                "ohlc_is_closed": True,
                "ohlc": {"open": 99.0, "high": 102.0, "low": 98.5, "close": 101.0},
            }
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps({"symbols": {"NQ": {"symbol": "NQ1!", "locked": True, "levels": {"PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"}}}}}),
                encoding="utf-8",
            )
            prior_state = self._prior_date_step5_state()
            entry_agent.STATE_PATH.write_text(json.dumps(prior_state), encoding="utf-8")

            response = server.app.test_client().get("/entry/status?symbols=NQ")
            status = response.get_json()["symbols"][0]
            persisted_after = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(status["current_step_label"], "Session Closed")
        self._assert_clean_locked_status(status, "SESSION_CLOSED", "Entry window closed at 8:00 AM PT.")
        self.assertEqual(persisted_after, prior_state)

    def test_locked_leg1_prevents_active_liquidity_rotation(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        locked_liquidity = {"name": "LL", "price": 100.0, "side": "lower"}
        persisted_state = {
            "state_by_symbol": {
                "NQ": {
                    "last_interacted_liquidity": locked_liquidity,
                    "step4": {
                        "status": "READY",
                        "next_step": "Step 5",
                        "state": {
                            "leg1_state_locked": True,
                            "leg1_status": "COMPLETE",
                            "active_liquidity": locked_liquidity,
                            "candle_a": {"timestamp": "2026-05-15T13:25:00Z"},
                            "candle_b": {"timestamp": "2026-05-15T13:26:00Z"},
                            "leg1_completed_at": "2026-05-15T13:26:00Z",
                            "leg1_reference_price": 101.0,
                            "leg1_reference_candle_time": "2026-05-15T13:25:00Z",
                            "leg1_direction": "LONG",
                            "setup_direction": "LONG",
                        },
                    },
                    "consumed_liquidity_levels": [],
                }
            },
            "last_interacted_liquidity_by_symbol": {"NQ": locked_liquidity},
        }
        snapshot = {
            "symbol": "NQM6",
            "normalized_symbol": "NQ",
            "latest_price": 89.0,
            "latest_bar_time": "2026-05-15T13:29:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 96.0, "high": 97.0, "low": 88.0, "close": 89.0},
            "tv_context": {
                "levels": {
                    "LL": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "ONL": {"price": 90.0, "status": "ACTIVE", "stack_group": "NONE"},
                }
            },
        }

        result = entry_agent.evaluate_live_step_2_1a(snapshot, {}, {"tick_size": 0.25}, persisted_state)

        self.assertEqual(result["active_level"], "LL")
        self.assertEqual(result["level_price"], 100.0)

    def test_non_selected_pathway_cannot_overwrite_public_shared_state(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        entry_agent.run_once = lambda symbol, persist=True: {
            "requested_symbol": symbol,
            "normalized_symbol": "NQ",
            "latest_price": 99.0,
            "latest_bar_time": "2026-05-15T13:31:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 101.0, "high": 102.0, "low": 98.0, "close": 99.0},
            "liquidity": {},
            "step_2_1a": {"step_2_activated": True, "active_level": "PMH", "level_price": 100.0, "side": "upper"},
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 100.0},
            "step25": {
                "status": "READY",
                "state": {"controlling_mode": "Normal Rejection Mode", "candidate_modes": ["Normal Rejection Mode", "R/S"]},
            },
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4", "state": {}},
            "step4": {
                "status": "READY",
                "next_step": "Step 5",
                "state": {
                    "current_pathway_control": "continuation",
                    "current_controlling_mode": "R/S",
                    "current_continuation_type": "R/S",
                    "leg1_state_locked": True,
                    "leg1_status": "COMPLETE",
                    "active_liquidity": {"name": "PMH", "price": 100.0, "side": "upper"},
                    "candle_a": {"timestamp": "2026-05-15T13:27:00Z"},
                    "candle_b": {"timestamp": "2026-05-15T13:28:00Z"},
                    "leg1_completed_at": "2026-05-15T13:28:00Z",
                    "leg1_reference_price": 101.0,
                    "leg1_reference_candle_time": "2026-05-15T13:27:00Z",
                    "leg1_direction": "SHORT",
                    "setup_direction": "SHORT",
                },
            },
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        try:
            status = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(status["selected_pathway"], "rejection")
        self.assertEqual(status["current_pathway_control"], "rejection")
        self.assertEqual(status["current_controlling_mode"], "Normal Rejection Mode")
        self.assertIsNone(status["continuation_side"]["current_step"])

    def test_step4_invalidation_is_not_public_while_current_step_is_step2(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        entry_agent.run_once = lambda symbol, persist=True: {
            "requested_symbol": symbol,
            "normalized_symbol": "NQ",
            "latest_price": 100.0,
            "latest_bar_time": "2026-05-15T13:31:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
            "liquidity": {},
            "step_2_1a": {"step_2_activated": True, "active_level": "PMH", "level_price": 100.0, "side": "upper"},
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 100.0},
            "step25": {"status": "READY", "state": {"controlling_mode": "Normal Rejection Mode"}},
            "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
            "step4": {
                "step": "Step 4",
                "status": "TERMINATED",
                "next_step": "Step 2",
                "reason": "Active liquidity was penetrated beyond 50%.",
                "state": {
                    "invalidation_source": "leg1_50_percent_rule",
                    "invalidation_source_step": "Step 4",
                    "invalidation_source_candle_time": "2026-05-15T13:31:00Z",
                    "invalidated_at": "2026-05-15T13:31:00Z",
                    "active_liquidity": {"name": "PMH", "price": 100.0, "side": "upper"},
                },
            },
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        try:
            status = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(status["current_step"], "Step 2")
        self.assertEqual(status["current_step_status"], "CONFIRMED")
        self.assertEqual(status["entry_status"], "WAIT")
        self.assertIsNone(status["invalidation_reason"])
        self.assertIsNone(status["invalidation_source"])
        self.assertIsNone(status["invalidation_source_step"])
        self.assertEqual(status["internal_invalidation_reason"], "Active liquidity was penetrated beyond 50%.")
        self.assertTrue(status["last_decision"].startswith("WAIT:"))

    def test_step2_confirmed_at_uses_activation_candle_time_and_is_stable(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        activation_time = "2026-05-15T13:45:00Z"
        original_run_once = entry_agent.run_once
        entry_agent.run_once = lambda symbol, persist=True: {
            "requested_symbol": symbol,
            "normalized_symbol": "NQ",
            "latest_price": 100.0,
            "latest_bar_time": activation_time,
            "ohlc_is_closed": True,
            "ohlc": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
            "liquidity": {},
            "step_2_1a": {
                "step_2_activated": True,
                "active_level": "PMH",
                "level_price": 100.0,
                "side": "upper",
                "candle_index": 42,
                "step2_activation_candle_index": 42,
                "candle_a": {"timestamp": activation_time, "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
            },
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 100.0},
            "step25": {
                "status": "READY",
                "state": {
                    "controlling_mode": "Normal Rejection Mode",
                    "step25_block_reason": "Continuation seeded from rejection Step 4. Waiting for a later candle close through the continuation boundary.",
                },
            },
            "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
            "step4": {"status": "WAIT", "next_step": "Step 4", "state": {}},
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        try:
            first = entry_agent.build_entry_status("NQ")
            second = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(first["current_step"], "Step 2")
        self.assertEqual(first["current_step_confirmed_at"], activation_time)
        self.assertEqual(first["step2_candle_count"], 0)
        self.assertEqual(second["current_step_confirmed_at"], activation_time)
        self.assertEqual(second["step2_candle_count"], 0)

    def test_rejection_step4_count_stays_persisted_and_uses_only_completed_candles(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        previous_state = {
            "state_by_symbol": {
                "NQ": {
                    "normalized_symbol": "NQ",
                    "step4": {
                        "status": "WAIT",
                        "next_step": "Step 4",
                        "state": {
                            "leg1_window_started_at": "2026-06-30T13:35:00Z",
                            "leg1_window_candle_index": 0,
                            "leg1_window_remaining": 4,
                            "leg1_window_active": True,
                            "leg1_window_invalidated": False,
                            "leg1_status": "WAIT",
                            "active_liquidity": {"name": "PMH/LH/ONH", "price": 22100.0, "side": "upper"},
                        },
                    },
                    "rejection_lane": {
                        "lane_name": "rejection",
                        "lane_status": "controlling",
                        "pathway_status": "controlling",
                        "active_liquidity_name": "PMH/LH/ONH",
                        "liquidity_group": "HIGH 1",
                        "active_liquidity_price": 22100.0,
                        "close_boundary": 22096.0,
                        "extreme_boundary": 22100.0,
                        "wick_boundary_extreme": 22100.0,
                        "step2_candle_count": 0,
                        "step4_candle_count": 0,
                        "step2_status": "CONFIRMED",
                        "step4_status": "WAIT",
                        "step2_confirmed_at": "2026-06-30T13:35:00Z",
                        "step2_step4_50_line": 22088.0,
                        "step4_step5_75_line": 22082.0,
                        "invalidation_reason": None,
                    },
                }
            }
        }
        snapshots = [
            {
                "requested_symbol": "NQ",
                "normalized_symbol": "NQ",
                "latest_price": 22094.0,
                "latest_bar_time": "2026-06-30T13:36:00Z",
                "ohlc_is_closed": False,
                "ohlc": {"open": 22093.0, "high": 22096.0, "low": 22090.0, "close": 22094.0},
                "liquidity": {"tick_size": 0.25},
                "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 22100.0},
                "step_2_1a": {},
                "step25": {"status": "WAIT", "next_step": "Step 2.5", "state": {}},
                "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
                "step4": {"status": "WAIT", "next_step": "Step 4", "state": {}},
                "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
                "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
            },
            {
                "requested_symbol": "NQ",
                "normalized_symbol": "NQ",
                "latest_price": 22095.0,
                "latest_bar_time": "2026-06-30T13:36:00Z",
                "ohlc_is_closed": False,
                "ohlc": {"open": 22093.0, "high": 22097.0, "low": 22089.0, "close": 22095.0},
                "liquidity": {"tick_size": 0.25},
                "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 22100.0},
                "step_2_1a": {},
                "step25": {"status": "WAIT", "next_step": "Step 2.5", "state": {}},
                "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
                "step4": {"status": "WAIT", "next_step": "Step 4", "state": {}},
                "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
                "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
            },
            {
                "requested_symbol": "NQ",
                "normalized_symbol": "NQ",
                "latest_price": 22092.0,
                "latest_bar_time": "2026-06-30T13:36:00Z",
                "ohlc_is_closed": True,
                "ohlc": {"open": 22093.0, "high": 22097.0, "low": 22089.0, "close": 22092.0},
                "liquidity": {"tick_size": 0.25},
                "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 22100.0},
                "step_2_1a": {},
                "step25": {"status": "WAIT", "next_step": "Step 2.5", "state": {}},
                "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
                "step4": {"status": "WAIT", "next_step": "Step 4", "state": {}},
                "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
                "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
            },
            {
                "requested_symbol": "NQ",
                "normalized_symbol": "NQ",
                "latest_price": 22091.0,
                "latest_bar_time": "2026-06-30T13:37:00Z",
                "ohlc_is_closed": True,
                "ohlc": {"open": 22092.0, "high": 22095.0, "low": 22088.0, "close": 22091.0},
                "liquidity": {"tick_size": 0.25},
                "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 22100.0},
                "step_2_1a": {},
                "step25": {"status": "WAIT", "next_step": "Step 2.5", "state": {}},
                "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
                "step4": {"status": "WAIT", "next_step": "Step 4", "state": {}},
                "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
                "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
            },
        ]

        original_run_once = entry_agent.run_once
        original_load_entry_state = entry_agent.load_entry_state
        original_hide_unconfirmed = entry_agent.hide_unconfirmed_current_candle_advancement
        snapshot_iter = iter(snapshots)
        entry_agent.run_once = lambda symbol, persist=True: copy.deepcopy(next(snapshot_iter))
        entry_agent.load_entry_state = lambda: copy.deepcopy(previous_state)
        entry_agent.hide_unconfirmed_current_candle_advancement = lambda snapshot: None
        try:
            intrabar_first = entry_agent.build_entry_status("NQ")
            intrabar_second = entry_agent.build_entry_status("NQ")
            after_0636_close = entry_agent.build_entry_status("NQ")
            after_0637_close = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once
            entry_agent.load_entry_state = original_load_entry_state
            entry_agent.hide_unconfirmed_current_candle_advancement = original_hide_unconfirmed

        for status in (intrabar_first, intrabar_second, after_0636_close, after_0637_close):
            self.assertEqual(status["rejection_lane"]["step2_status"], "CONFIRMED")
            self.assertEqual(status["rejection_lane"]["step4_status"], "WAIT")
            self.assertEqual(status["step2_confirmed_at"], "2026-06-30T13:35:00Z")
            self.assertEqual(status["rejection_lane"]["active_liquidity_name"], "PMH/LH/ONH")
            self.assertIsNone(status["rejection_lane"]["invalidation_reason"])

        self.assertEqual(intrabar_first["rejection_lane"]["step4_candle_count"], 0)
        self.assertEqual(intrabar_first["leg1_window_candle_index"], 0)
        self.assertNotEqual(intrabar_first["rejection_lane"]["step4_candle_count"], 3)
        self.assertIsNotNone(intrabar_first["rejection_lane"])
        self.assertEqual(intrabar_second["rejection_lane"]["step4_candle_count"], 0)
        self.assertEqual(intrabar_second["leg1_window_candle_index"], 0)
        self.assertEqual(after_0636_close["rejection_lane"]["step4_candle_count"], 1)
        self.assertEqual(after_0636_close["leg1_window_candle_index"], 1)
        self.assertEqual(after_0637_close["rejection_lane"]["step4_candle_count"], 2)
        self.assertEqual(after_0637_close["leg1_window_candle_index"], 2)

    def test_step2_candle_count_is_blank_before_confirmation_and_advances_after(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        base_snapshot = {
            "requested_symbol": "NQ",
            "normalized_symbol": "NQ",
            "latest_price": 100.0,
            "ohlc_is_closed": True,
            "ohlc": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
            "liquidity": {},
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 100.0},
            "step25": {
                "status": "READY",
                "state": {
                    "controlling_mode": "Normal Rejection Mode",
                    "step25_block_reason": "Continuation seeded from rejection Step 4. Waiting for a later candle close through the continuation boundary.",
                },
            },
            "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
            "step4": {"status": "WAIT", "next_step": "Step 4", "state": {}},
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        snapshots = [
            {
                **copy.deepcopy(base_snapshot),
                "latest_bar_time": "2026-05-15T13:44:00Z",
                "step_2_1a": {"step_2_activated": False},
            },
            {
                **copy.deepcopy(base_snapshot),
                "latest_bar_time": "2026-05-15T13:45:00Z",
                "step_2_1a": {
                    "step_2_activated": True,
                    "active_level": "PMH",
                    "level_price": 100.0,
                    "side": "upper",
                    "candle_index": 10,
                    "step2_activation_candle_index": 10,
                    "candle_a": {"timestamp": "2026-05-15T13:45:00Z", "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
                },
            },
            {
                **copy.deepcopy(base_snapshot),
                "latest_bar_time": "2026-05-15T13:46:00Z",
                "step_2_1a": {
                    "step_2_activated": True,
                    "active_level": "PMH",
                    "level_price": 100.0,
                    "side": "upper",
                    "candle_index": 11,
                    "step2_activation_candle_index": 10,
                    "candle_a": {"timestamp": "2026-05-15T13:45:00Z", "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
                },
            },
            {
                **copy.deepcopy(base_snapshot),
                "latest_bar_time": "2026-05-15T13:47:00Z",
                "step_2_1a": {
                    "step_2_activated": True,
                    "active_level": "PMH",
                    "level_price": 100.0,
                    "side": "upper",
                    "candle_index": 12,
                    "step2_activation_candle_index": 10,
                    "candle_a": {"timestamp": "2026-05-15T13:45:00Z", "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
                },
            },
        ]

        cursor = {"index": 0}
        original_run_once = entry_agent.run_once
        entry_agent.run_once = lambda symbol, persist=True: copy.deepcopy(snapshots[cursor["index"]])
        try:
            pre_confirmation = entry_agent.build_entry_status("NQ")
            cursor["index"] = 1
            confirmation = entry_agent.build_entry_status("NQ")
            cursor["index"] = 2
            first_after = entry_agent.build_entry_status("NQ")
            cursor["index"] = 3
            second_after = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once

        self.assertIsNone(pre_confirmation["step2_candle_count"])
        self.assertEqual(confirmation["step2_candle_count"], 0)
        self.assertEqual(first_after["step2_candle_count"], 1)
        self.assertEqual(second_after["step2_candle_count"], 2)

    def test_step2_candle_count_falls_back_to_activation_time_when_indexes_are_missing(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        base_snapshot = {
            "requested_symbol": "YM",
            "normalized_symbol": "YM",
            "latest_price": 52234.0,
            "ohlc_is_closed": True,
            "ohlc": {"open": 52204.0, "high": 52238.0, "low": 52189.0, "close": 52234.0},
            "liquidity": {},
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 52176.0},
            "step25": {
                "status": "READY",
                "state": {
                    "controlling_mode": "Normal Rejection Mode",
                    "step25_block_reason": "Continuation seeded from rejection Step 4. Waiting for a later candle close through the continuation boundary.",
                },
            },
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4", "state": {}},
            "step4": {"status": "WAIT", "next_step": "Step 4", "state": {}},
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        snapshots = []
        for minute_offset in range(3):
            snapshots.append(
                {
                    **copy.deepcopy(base_snapshot),
                    "latest_bar_time": f"2026-06-24T13:5{minute_offset}:00Z",
                    "step_2_1a": {
                        "step_2_activated": True,
                        "active_level": "PMH",
                        "level_price": 52176.0,
                        "side": "upper",
                        "step2_activated_at": "2026-06-24T13:50:00Z",
                        "candle_a": {"timestamp": "2026-06-24T13:50:00Z"},
                    },
                }
            )

        cursor = {"index": 0}
        original_run_once = entry_agent.run_once
        entry_agent.run_once = lambda symbol, persist=True: copy.deepcopy(snapshots[cursor["index"]])
        try:
            zero = entry_agent.build_entry_status("YM")
            cursor["index"] = 1
            one = entry_agent.build_entry_status("YM")
            cursor["index"] = 2
            two = entry_agent.build_entry_status("YM")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(zero["step2_candle_count"], 0)
        self.assertEqual(one["step2_candle_count"], 1)
        self.assertEqual(two["step2_candle_count"], 2)

    def test_evaluate_live_step2_confirms_once_and_preserves_original_candle_a_on_later_qualifying_candles(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_selector = entry_agent.selected_active_liquidity_from_context
        original_recent_closed_bars = entry_agent.recent_closed_bars

        def fake_selector(_context, _latest_price, _ohlc, _tick_size):
            bar_time = _context.get("bar_time")
            if bar_time == "2026-07-01T14:13:00Z":
                return {
                    "name": "PMH",
                    "price": 100.0,
                    "side": "upper",
                    "display_name": "PMH",
                    "group": {
                        "name": "PMH",
                        "display_name": "PMH",
                        "side": "upper",
                        "close_boundary": 100.0,
                        "extreme_boundary": 100.0,
                        "stack_extreme": 100.0,
                        "components": ["PMH"],
                    },
                }
            return {
                "name": "LH",
                "price": 101.0,
                "side": "upper",
                "display_name": "LH",
                "group": {
                    "name": "LH",
                    "display_name": "LH",
                    "side": "upper",
                    "close_boundary": 101.0,
                    "extreme_boundary": 101.0,
                    "stack_extreme": 101.0,
                    "components": ["LH"],
                },
            }

        entry_agent.selected_active_liquidity_from_context = fake_selector
        entry_agent.recent_closed_bars = lambda _symbol, _limit: []
        try:
            persisted_state = {"state_by_symbol": {"NQ": {}}}
            snapshots = [
                {
                    "symbol": "NQ1!",
                    "normalized_symbol": "NQ",
                    "latest_price": 100.5,
                    "latest_bar_time": "2026-07-01T14:13:00Z",
                    "ohlc_is_closed": True,
                    "ohlc": {"open": 99.75, "high": 100.5, "low": 99.5, "close": 100.25},
                    "tv_context": {"levels": {"PMH": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"}}, "bar_time": "2026-07-01T14:13:00Z"},
                },
                {
                    "symbol": "NQ1!",
                    "normalized_symbol": "NQ",
                    "latest_price": 101.25,
                    "latest_bar_time": "2026-07-01T14:14:00Z",
                    "ohlc_is_closed": True,
                    "ohlc": {"open": 100.75, "high": 101.5, "low": 100.5, "close": 101.25},
                    "tv_context": {"levels": {"LH": {"price": 101.0, "status": "ACTIVE", "stack_group": "NONE"}}, "bar_time": "2026-07-01T14:14:00Z"},
                },
                {
                    "symbol": "NQ1!",
                    "normalized_symbol": "NQ",
                    "latest_price": 101.75,
                    "latest_bar_time": "2026-07-01T14:15:00Z",
                    "ohlc_is_closed": True,
                    "ohlc": {"open": 101.25, "high": 102.0, "low": 101.0, "close": 101.75},
                    "tv_context": {"levels": {"LH": {"price": 101.0, "status": "ACTIVE", "stack_group": "NONE"}}, "bar_time": "2026-07-01T14:15:00Z"},
                },
            ]

            first = entry_agent.evaluate_live_step_2_1a(snapshots[0], {}, {"tick_size": 0.25}, persisted_state)
            persisted_state["state_by_symbol"]["NQ"]["step_2_1a"] = copy.deepcopy(first)
            persisted_state["state_by_symbol"]["NQ"]["step_2_1a_candle_index"] = first["next_candle_index"]

            second = entry_agent.evaluate_live_step_2_1a(snapshots[1], {}, {"tick_size": 0.25}, persisted_state)
            persisted_state["state_by_symbol"]["NQ"]["step_2_1a"] = copy.deepcopy(second)
            persisted_state["state_by_symbol"]["NQ"]["step_2_1a_candle_index"] = second["next_candle_index"]

            third = entry_agent.evaluate_live_step_2_1a(snapshots[2], {}, {"tick_size": 0.25}, persisted_state)
        finally:
            entry_agent.selected_active_liquidity_from_context = original_selector
            entry_agent.recent_closed_bars = original_recent_closed_bars

        self.assertTrue(first["step_2_activated"])
        self.assertEqual(first["candle_a"]["timestamp"], "2026-07-01T14:13:00Z")
        self.assertEqual(first["step2_owner_seeded_at"], "2026-07-01T14:13:00Z")
        self.assertEqual(first["step2_activated_at"], "2026-07-01T14:13:00Z")
        self.assertEqual(first["step2_activation_candle_index"], 0)
        self.assertEqual(entry_agent.step2_confirmed_at(snapshots[0], first, "CONFIRMED"), "2026-07-01T14:13:00Z")
        self.assertEqual(entry_agent.step2_candle_count(snapshots[0], first), 0)

        self.assertTrue(second["step_2_activated"])
        self.assertEqual(second["candle_a"]["timestamp"], "2026-07-01T14:13:00Z")
        self.assertEqual(second["step2_owner_seeded_at"], "2026-07-01T14:13:00Z")
        self.assertEqual(second["step2_activated_at"], "2026-07-01T14:13:00Z")
        self.assertEqual(second["step2_activation_candle_index"], 0)
        self.assertEqual(second["audit_step2_event"], "already_active")
        self.assertEqual(entry_agent.step2_confirmed_at(snapshots[1], second, "CONFIRMED"), "2026-07-01T14:13:00Z")
        self.assertEqual(entry_agent.step2_candle_count(snapshots[1], second), 1)

        self.assertTrue(third["step_2_activated"])
        self.assertEqual(third["candle_a"]["timestamp"], "2026-07-01T14:13:00Z")
        self.assertEqual(third["step2_owner_seeded_at"], "2026-07-01T14:13:00Z")
        self.assertEqual(third["step2_activated_at"], "2026-07-01T14:13:00Z")
        self.assertEqual(third["step2_activation_candle_index"], 0)
        self.assertEqual(entry_agent.step2_confirmed_at(snapshots[2], third, "CONFIRMED"), "2026-07-01T14:13:00Z")
        self.assertEqual(entry_agent.step2_candle_count(snapshots[2], third), 2)

    def test_step2_candle_count_clears_instead_of_exposing_values_greater_than_four(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        count = entry_agent.step2_candle_count(
            {
                "latest_bar_time": "2026-06-25T13:50:00Z",
                "step4": {"state": {"leg1_window_started_at": "2026-06-25T13:40:00Z", "leg1_window_active": True, "leg1_window_candle_index": 6}},
            },
            {
                "step_2_activated": True,
                "step2_activation_candle_index": 10,
                "candle_index": 16,
            },
        )

        self.assertIsNone(count)

    def test_completed_rejection_step4_opens_continuation_lane(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        snapshot = {
            "requested_symbol": "YM",
            "normalized_symbol": "YM",
            "latest_price": 52226.0,
            "latest_bar_time": "2026-06-24T13:52:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 52233.0, "high": 52258.0, "low": 52217.0, "close": 52226.0},
            "tv_context": {
                "levels": {
                    "PMH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "LH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "ONH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "YH": {"price": 52281.0, "status": "ACTIVE", "stack_group": "NONE"},
                }
            },
            "liquidity": {
                "nearest_level_above": {"name": "YH", "price": 52281.0},
                "nearest_level_below": {"name": "PMH", "price": 52176.0},
                "tick_size": 1.0,
            },
            "step_2_1a": {
                "step_2_activated": True,
                "active_level": "PMH",
                "level_price": 52176.0,
                "side": "upper",
                "candle_index": 12,
                "step2_activation_candle_index": 10,
                "step2_activated_at": "2026-06-24T13:50:00Z",
                "step2_locked_owner": {
                    "pathway": "rejection",
                    "setup_direction": "SHORT",
                    "side": "upper",
                    "close_boundary": 52176.0,
                    "extreme_boundary": 52176.0,
                    "active_liquidity": {"name": "PMH", "price": 52176.0, "side": "upper"},
                },
                "next_same_side_liquidity": {"name": "YH", "price": 52281.0},
                "active_liquidity_group": {
                    "name": "HIGH 1",
                    "side": "upper",
                    "close_boundary": 52176.0,
                    "extreme_boundary": 52176.0,
                    "wick_boundary_extreme": None,
                },
            },
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 52176.0},
            "step25": {
                "status": "READY",
                "state": {
                    "controlling_mode": "Normal Rejection Mode",
                    "step25_block_reason": "Continuation seeded from rejection Step 4. Waiting for a later candle close through the continuation boundary.",
                },
            },
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4", "state": {}},
            "step4": {
                "status": "READY",
                "reason": "Step 4 ready: Leg 1 participation confirmed.",
                "state": {
                    "step4_confirmed_at": "2026-06-24T13:52:00Z",
                    "leg1_completed_at": "2026-06-24T13:52:00Z",
                    "leg1_status": "COMPLETE",
                    "leg1_state_locked": True,
                    "active_liquidity": {"name": "PMH", "price": 52176.0, "side": "upper"},
                },
            },
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        original_run_once = entry_agent.run_once
        original_load_state = entry_agent.load_entry_state
        entry_agent.run_once = lambda symbol, persist=True: copy.deepcopy(snapshot)
        entry_agent.load_entry_state = lambda: {}
        try:
            status = entry_agent.build_entry_status("YM")
        finally:
            entry_agent.run_once = original_run_once
            entry_agent.load_entry_state = original_load_state

        self.assertEqual(status["rejection_lane"]["lane_status"], "controlling")
        self.assertEqual(status["rejection_lane"]["step2_status"], "CONFIRMED")
        self.assertEqual(status["rejection_lane"]["step2_step4_50_line"], 52228.5)
        self.assertEqual(status["rejection_lane"]["step4_step5_75_line"], 52254.75)
        self.assertIsNone(status["rejection_lane"]["invalidation_reason"])
        self.assertIsNone(status["rejection_lane"]["active_liquidity_group"])
        self.assertEqual(status["continuation_lane"]["lane_status"], "eligible")
        self.assertEqual(status["continuation_lane"]["step2_status"], "WAIT")
        self.assertEqual(
            status["continuation_lane"]["step2_reason"],
            "Continuation seeded from rejection Step 4. Waiting for a later candle close through the continuation boundary.",
        )
        self.assertIsNone(status["continuation_lane"]["active_liquidity_group"])
        self.assertEqual(status["active_liquidity_name"], "PMH")
        self.assertEqual(status["rejection_lane"]["active_liquidity_name"], "PMH")
        self.assertEqual(status["continuation_lane"]["active_liquidity_name"], "PMH")
        self.assertEqual(status["step4_status"], "CONFIRMED")
        self.assertNotIn("step25_status", status)
        self.assertNotIn("step25_status", status["rejection_lane"])
        self.assertNotIn("step25_status", status["continuation_lane"])

    def test_invalidated_rejection_lane_does_not_republish_flat_wait_or_ready_without_reset(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        snapshot = {
            "requested_symbol": "YM",
            "normalized_symbol": "YM",
            "latest_price": 52220.0,
            "latest_bar_time": "2026-06-24T13:54:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 52210.0, "high": 52228.0, "low": 52199.0, "close": 52220.0},
            "tv_context": {
                "levels": {
                    "PMH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "LH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "ONH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "YH": {"price": 52281.0, "status": "ACTIVE", "stack_group": "NONE"},
                }
            },
            "liquidity": {
                "nearest_level_above": {"name": "YH", "price": 52281.0},
                "nearest_level_below": {"name": "PMH", "price": 52176.0},
                "tick_size": 1.0,
            },
            "step_2_1a": {
                "step_2_activated": True,
                "active_level": "PMH",
                "level_price": 52176.0,
                "side": "upper",
                "candle_index": 14,
                "step2_activation_candle_index": 10,
                "step2_activated_at": "2026-06-24T13:50:00Z",
                "step2_locked_owner": {
                    "pathway": "rejection",
                    "setup_direction": "SHORT",
                    "side": "upper",
                    "close_boundary": 52176.0,
                    "extreme_boundary": 52176.0,
                    "active_liquidity": {"name": "PMH", "price": 52176.0, "side": "upper"},
                },
                "next_same_side_liquidity": {"name": "YH", "price": 52281.0},
            },
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 52176.0},
            "step25": {"status": "READY", "state": {"controlling_mode": "Normal Rejection Mode"}},
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4", "state": {}},
            "step4": {
                "status": "WAIT",
                "reason": "Candle B failed participation and became the new rejection Candle A; waiting for a later future Candle B inside the original 4-candle Step 4 window.",
                "state": {},
            },
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        previous_state = {
            "state_by_symbol": {
                "YM": {
                    "rejection_lane": {
                        "lane_name": "rejection",
                        "lane_status": "invalidated",
                        "pathway_status": "invalidated",
                        "active_liquidity_name": "PMH/LH/ONH Liquidity",
                        "liquidity_group": "HIGH 1",
                        "active_liquidity_price": 52176.0,
                        "close_boundary": 52176.0,
                        "extreme_boundary": 52176.0,
                        "wick_boundary_extreme": None,
                        "candle_count": 3,
                        "step2_status": "CONFIRMED",
                        "step4_status": "TERMINATED",
                        "step2_step4_50_line": 52228.5,
                        "step4_step5_75_line": 52254.75,
                        "invalidation_reason": "STEP2_STEP4_50_LINE_TOUCHED",
                    },
                    "continuation_lane": {
                        "lane_name": "continuation",
                        "lane_status": "eligible",
                        "pathway_status": "eligible",
                    },
                }
            }
        }
        original_run_once = entry_agent.run_once
        original_load_state = entry_agent.load_entry_state
        entry_agent.run_once = lambda symbol, persist=True: copy.deepcopy(snapshot)
        entry_agent.load_entry_state = lambda: copy.deepcopy(previous_state)
        try:
            status = entry_agent.build_entry_status("YM")
        finally:
            entry_agent.run_once = original_run_once
            entry_agent.load_entry_state = original_load_state

        self.assertEqual(status["rejection_lane"]["lane_status"], "invalidated")
        self.assertEqual(status["continuation_lane"]["lane_status"], "eligible")
        self.assertEqual(status["active_liquidity_name"], "PMH")
        self.assertEqual(status["step4_status"], "TERMINATED")
        self.assertEqual(status["invalidation_reason"], "STEP2_STEP4_50_LINE_TOUCHED")
        self.assertEqual(status["step2_candle_count"], 4)
        self.assertNotIn("step25_status", status)

    def test_rejection_50_percent_invalidation_does_not_open_continuation_lane(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        snapshot = {
            "requested_symbol": "YM",
            "normalized_symbol": "YM",
            "latest_price": 52180.0,
            "latest_bar_time": "2026-06-24T13:55:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 52218.0, "high": 52233.0, "low": 52171.0, "close": 52180.0},
            "tv_context": {
                "levels": {
                    "PMH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "LH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "ONH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "YH": {"price": 52281.0, "status": "ACTIVE", "stack_group": "NONE"},
                }
            },
            "liquidity": {
                "nearest_level_above": {"name": "YH", "price": 52281.0},
                "nearest_level_below": {"name": "PMH", "price": 52176.0},
                "tick_size": 1.0,
            },
            "step_2_1a": {
                "step_2_activated": True,
                "active_level": "PMH",
                "level_price": 52176.0,
                "side": "upper",
                "candle_index": 15,
                "step2_activation_candle_index": 10,
                "step2_activated_at": "2026-06-24T13:50:00Z",
                "step2_locked_owner": {
                    "pathway": "rejection",
                    "setup_direction": "SHORT",
                    "side": "upper",
                    "close_boundary": 52176.0,
                    "extreme_boundary": 52176.0,
                    "active_liquidity": {"name": "PMH", "price": 52176.0, "side": "upper"},
                },
                "next_same_side_liquidity": {"name": "YH", "price": 52281.0},
                "active_liquidity_group": {
                    "name": "HIGH 1",
                    "side": "upper",
                    "close_boundary": 52176.0,
                    "extreme_boundary": 52176.0,
                    "wick_boundary_extreme": None,
                },
            },
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 52176.0},
            "step25": {
                "status": "WAIT",
                "state": {
                    "controlling_mode": None,
                    "continuation_eligibility_open": True,
                    "continuation_step2_activated": None,
                    "continuation_probe_boundary": {
                        "active": True,
                        "side": "upper",
                        "source_level": "PMH",
                        "boundary_price": 52171.0,
                    },
                    "current_boundary": 52171.0,
                },
            },
            "step3": {"status": "WAIT", "next_step": "Step 2.5", "state": {}},
            "step4": {"status": "WAIT", "reason": "Step 4 waiting for Step 2 Continuation selection, Step 3 permission, Candle A, Candle B, setup direction, ATR, and opposing liquidity.", "state": {}},
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        previous_state = {
            "state_by_symbol": {
                "YM": {
                    "rejection_lane": {
                        "lane_name": "rejection",
                        "lane_status": "invalidated",
                        "pathway_status": "invalidated",
                        "active_liquidity_name": "PMH/LH/ONH Liquidity",
                        "liquidity_group": "HIGH 1",
                        "active_liquidity_price": 52176.0,
                        "close_boundary": 52176.0,
                        "extreme_boundary": 52176.0,
                        "wick_boundary_extreme": None,
                        "candle_count": 4,
                        "step2_status": "CONFIRMED",
                        "step4_status": "TERMINATED",
                        "step2_step4_50_line": 52228.5,
                        "step4_step5_75_line": 52254.75,
                        "invalidation_reason": "STEP2_STEP4_50_LINE_TOUCHED",
                    },
                    "continuation_lane": {
                        "lane_name": "continuation",
                        "lane_status": "eligible",
                        "pathway_status": "eligible",
                    },
                }
            }
        }
        original_run_once = entry_agent.run_once
        original_load_state = entry_agent.load_entry_state
        entry_agent.run_once = lambda symbol, persist=True: copy.deepcopy(snapshot)
        entry_agent.load_entry_state = lambda: copy.deepcopy(previous_state)
        try:
            status = entry_agent.build_entry_status("YM")
        finally:
            entry_agent.run_once = original_run_once
            entry_agent.load_entry_state = original_load_state

        self.assertEqual(status["rejection_lane"]["lane_status"], "invalidated")
        self.assertEqual(status["continuation_lane"]["lane_status"], "idle")
        self.assertEqual(status["active_liquidity_name"], "PMH")
        self.assertEqual(status["rejection_lane"]["active_liquidity_name"], "PMH")
        self.assertIsNone(status["continuation_lane"]["active_liquidity_name"])
        self.assertIsNone(status["continuation_lane"].get("extreme_boundary"))
        self.assertIsNone(status["continuation_lane"].get("wick_boundary_extreme"))
        self.assertEqual(status["continuation_lane"]["step2_status"], "WAIT")
        self.assertEqual(status["step4_status"], "TERMINATED")
        self.assertEqual(status["invalidation_reason"], "STEP2_STEP4_50_LINE_TOUCHED")
        self.assertEqual(status["continuation_pathway_status"], "idle")
        self.assertNotIn("step25_status", status["continuation_lane"])

    def test_consumed_liquidity_blocks_continuation_seed_and_step2(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        reclaim_candle = {
            "timestamp": "2026-06-24T13:57:00Z",
            "open": 52181.0,
            "high": 52190.0,
            "low": 52135.0,
            "close": 52146.0,
        }
        snapshot = {
            "requested_symbol": "YM",
            "normalized_symbol": "YM",
            "latest_price": 52146.0,
            "latest_bar_time": "2026-06-24T13:57:00Z",
            "ohlc_is_closed": True,
            "ohlc": dict(reclaim_candle),
            "tv_context": {
                "levels": {
                    "PMH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "LH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "ONH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "YH": {"price": 52281.0, "status": "ACTIVE", "stack_group": "NONE"},
                }
            },
            "liquidity": {
                "nearest_level_above": {"name": "YH", "price": 52281.0},
                "nearest_level_below": {"name": "PMH", "price": 52176.0},
                "tick_size": 1.0,
            },
            "step_2_1a": {
                "step_2_activated": True,
                "active_level": "PMH",
                "level_price": 52176.0,
                "side": "upper",
                "candle_index": 17,
                "step2_activation_candle_index": 10,
                "step2_activated_at": "2026-06-24T13:50:00Z",
                "step2_locked_owner": {
                    "pathway": "rejection",
                    "setup_direction": "SHORT",
                    "side": "upper",
                    "close_boundary": 52176.0,
                    "extreme_boundary": 52176.0,
                    "active_liquidity": {"name": "PMH", "price": 52176.0, "side": "upper"},
                },
                "next_same_side_liquidity": {"name": "YH", "price": 52281.0},
                "active_liquidity_group": {
                    "name": "HIGH 1",
                    "side": "upper",
                    "close_boundary": 52176.0,
                    "extreme_boundary": 52176.0,
                    "wick_boundary_extreme": None,
                },
            },
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 52176.0},
            "step25": {
                "status": "READY",
                "state": {
                    "controlling_mode": "R/S",
                    "continuation_step2_activated": True,
                    "reclaim_candle_a": dict(reclaim_candle),
                    "continuation_probe_boundary": {
                        "active": True,
                        "side": "upper",
                        "source_level": "PMH",
                        "boundary_price": 52165.0,
                    },
                    "current_boundary": 52165.0,
                    "step25_block_reason": "Continuation reclaim is active from the seeded boundary.",
                },
            },
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4", "state": {}},
            "step4": {"status": "WAIT", "reason": "Step 4 waiting for continuation Candle B.", "state": {}},
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        previous_state = {
            "state_by_symbol": {
                "YM": {
                    "consumed_liquidity_levels": [
                        {
                            "key": "PMH:52176.0",
                            "name": "PMH",
                            "price": 52176.0,
                            "side": "upper",
                            "exhaustion_type": "step2_step4_50_percent_invalidation",
                            "invalidation_source_candle_time": "2026-06-24T13:55:00Z",
                        }
                    ],
                    "rejection_lane": {
                        "lane_name": "rejection",
                        "lane_status": "invalidated",
                        "pathway_status": "invalidated",
                        "active_liquidity_name": "PMH",
                        "active_liquidity_price": 52176.0,
                        "liquidity_level_name": "PMH",
                        "liquidity_level_price": 52176.0,
                        "step2_status": "CONFIRMED",
                        "step4_status": "TERMINATED",
                        "invalidation_reason": "STEP2_STEP4_50_LINE_TOUCHED",
                    },
                    "continuation_lane": {
                        "lane_name": "continuation",
                        "lane_status": "eligible",
                        "pathway_status": "eligible",
                        "active_liquidity_name": "PMH",
                        "active_liquidity_price": 52176.0,
                        "liquidity_level_name": "PMH",
                        "liquidity_level_price": 52176.0,
                        "wick_boundary_extreme": 52165.0,
                        "step2_status": "CONFIRMED",
                    },
                    "step25": {
                        "state": {
                            "continuation_eligible_source": "frozen_rejection_trade_state",
                            "continuation_step2_activated": True,
                        }
                    },
                }
            }
        }
        original_run_once = entry_agent.run_once
        original_load_state = entry_agent.load_entry_state
        entry_agent.run_once = lambda symbol, persist=True: copy.deepcopy(snapshot)
        entry_agent.load_entry_state = lambda: copy.deepcopy(previous_state)
        try:
            status = entry_agent.build_entry_status("YM")
        finally:
            entry_agent.run_once = original_run_once
            entry_agent.load_entry_state = original_load_state

        self.assertEqual(status["continuation_lane"]["lane_status"], "idle")
        self.assertEqual(status["continuation_lane"]["step2_status"], "WAIT")
        self.assertEqual(status["continuation_pathway_status"], "idle")

    def test_consumed_liquidity_survives_repeated_entry_status_polling(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        snapshot = {
            "requested_symbol": "YM",
            "normalized_symbol": "YM",
            "latest_price": 52180.0,
            "latest_bar_time": "2026-06-24T13:55:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 52218.0, "high": 52233.0, "low": 52171.0, "close": 52180.0},
            "tv_context": {
                "levels": {
                    "PMH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "LH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "ONH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "YH": {"price": 52281.0, "status": "ACTIVE", "stack_group": "NONE"},
                }
            },
            "liquidity": {
                "nearest_level_above": {"name": "YH", "price": 52281.0},
                "nearest_level_below": {"name": "PMH", "price": 52176.0},
                "tick_size": 1.0,
            },
            "step_2_1a": {
                "step_2_activated": True,
                "active_level": "PMH",
                "level_price": 52176.0,
                "side": "upper",
                "step2_activated_at": "2026-06-24T13:50:00Z",
                "step2_locked_owner": {
                    "pathway": "rejection",
                    "setup_direction": "SHORT",
                    "side": "upper",
                    "close_boundary": 52176.0,
                    "extreme_boundary": 52176.0,
                    "active_liquidity": {"name": "PMH", "price": 52176.0, "side": "upper"},
                },
                "active_liquidity_group": {
                    "name": "HIGH 1",
                    "side": "upper",
                    "close_boundary": 52176.0,
                    "extreme_boundary": 52176.0,
                    "wick_boundary_extreme": None,
                },
            },
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 52176.0},
            "step25": {"status": "WAIT", "state": {"controlling_mode": None, "continuation_eligibility_open": True}},
            "step3": {"status": "WAIT", "next_step": "Step 2.5", "state": {}},
            "step4": {
                "status": "TERMINATED",
                "reason": "STEP2_STEP4_50_LINE_TOUCHED",
                "state": {
                    "active_liquidity": {"name": "PMH", "price": 52176.0, "side": "upper"},
                    "invalidation_source": "step2_step4_50_line",
                    "invalidation_source_step": "Step 4",
                    "invalidation_source_candle_time": "2026-06-24T13:55:00Z",
                    "step2_step4_50_line_touched_at": "2026-06-24T13:55:00Z",
                    "consumed_liquidity_levels": [
                        {
                            "key": "PMH:52176.0",
                            "name": "PMH",
                            "price": 52176.0,
                            "side": "upper",
                            "exhaustion_type": "step2_step4_50_percent_invalidation",
                            "invalidation_source": "step2_step4_50_line",
                            "invalidation_source_step": "Step 4",
                            "invalidation_source_candle_time": "2026-06-24T13:55:00Z",
                        }
                    ],
                },
            },
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }

        original_run_once = entry_agent.run_once
        original_state_path = entry_agent.STATE_PATH
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                entry_agent.STATE_PATH = Path(temp_dir) / "entry_agent_state.json"
                entry_agent.STATE_PATH.write_text(
                    json.dumps(
                        {
                            "state_by_symbol": {
                                "YM": {
                                    "consumed_liquidity_levels": [
                                        {
                                            "key": "PMH:52176.0",
                                            "name": "PMH",
                                            "price": 52176.0,
                                            "side": "upper",
                                            "exhaustion_type": "step2_step4_50_percent_invalidation",
                                            "invalidation_source_candle_time": "2026-06-24T13:55:00Z",
                                        }
                                    ],
                                    "consumed_entry_setups": [],
                                }
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                entry_agent.run_once = lambda symbol="YM", persist=True: copy.deepcopy(snapshot)

                first = entry_agent.build_entry_status("YM")
                second = entry_agent.build_entry_status("YM")

                self.assertEqual(first["continuation_lane"]["lane_status"], "idle")
                self.assertEqual(second["continuation_lane"]["lane_status"], "idle")
                self.assertEqual(first["continuation_pathway_status"], "idle")
                self.assertEqual(second["continuation_pathway_status"], "idle")
        finally:
            entry_agent.run_once = original_run_once
            entry_agent.STATE_PATH = original_state_path

    def test_consumed_liquidity_blocks_after_entry_agent_state_reload(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        snapshot = {
            "requested_symbol": "YM",
            "normalized_symbol": "YM",
            "latest_price": 52146.0,
            "latest_bar_time": "2026-06-24T13:57:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 52181.0, "high": 52190.0, "low": 52135.0, "close": 52146.0},
            "tv_context": {
                "levels": {
                    "PMH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "LH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "ONH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "YH": {"price": 52281.0, "status": "ACTIVE", "stack_group": "NONE"},
                }
            },
            "liquidity": {
                "nearest_level_above": {"name": "YH", "price": 52281.0},
                "nearest_level_below": {"name": "PMH", "price": 52176.0},
                "tick_size": 1.0,
            },
            "step_2_1a": {
                "step_2_activated": True,
                "active_level": "PMH",
                "level_price": 52176.0,
                "side": "upper",
                "step2_activated_at": "2026-06-24T13:50:00Z",
                "step2_locked_owner": {
                    "pathway": "rejection",
                    "setup_direction": "SHORT",
                    "side": "upper",
                    "close_boundary": 52176.0,
                    "extreme_boundary": 52176.0,
                    "active_liquidity": {"name": "PMH", "price": 52176.0, "side": "upper"},
                },
                "active_liquidity_group": {
                    "name": "HIGH 1",
                    "side": "upper",
                    "close_boundary": 52176.0,
                    "extreme_boundary": 52176.0,
                    "wick_boundary_extreme": None,
                },
            },
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 52176.0},
            "step25": {
                "status": "READY",
                "state": {
                    "controlling_mode": "R/S",
                    "continuation_step2_activated": True,
                    "reclaim_candle_a": {"timestamp": "2026-06-24T13:57:00Z", "open": 52181.0, "high": 52190.0, "low": 52135.0, "close": 52146.0},
                },
            },
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4", "state": {}},
            "step4": {"status": "WAIT", "reason": "Step 4 waiting for continuation Candle B.", "state": {}},
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }

        original_run_once = entry_agent.run_once
        original_state_path = entry_agent.STATE_PATH
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                entry_agent.STATE_PATH = Path(temp_dir) / "entry_agent_state.json"
                entry_agent.STATE_PATH.write_text(
                    json.dumps(
                        {
                            "state_by_symbol": {
                                "YM": {
                                    "consumed_liquidity_levels": [
                                        {
                                            "key": "PMH:52176.0",
                                            "name": "PMH",
                                            "price": 52176.0,
                                            "side": "upper",
                                            "exhaustion_type": "step2_step4_50_percent_invalidation",
                                            "invalidation_source_candle_time": "2026-06-24T13:55:00Z",
                                        }
                                    ],
                                    "consumed_entry_setups": [],
                                }
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                entry_agent.run_once = lambda symbol="YM", persist=True: copy.deepcopy(snapshot)

                status = entry_agent.build_entry_status("YM")

                self.assertEqual(status["continuation_lane"]["lane_status"], "idle")
                self.assertEqual(status["continuation_lane"]["step2_status"], "WAIT")
                self.assertEqual(status["continuation_pathway_status"], "idle")
        finally:
            entry_agent.run_once = original_run_once
            entry_agent.STATE_PATH = original_state_path

    def test_controlling_continuation_lane_projects_flat_fields_after_completed_rejection_step4(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        reclaim_candle = {
            "timestamp": "2026-06-24T13:57:00Z",
            "open": 52181.0,
            "high": 52190.0,
            "low": 52135.0,
            "close": 52146.0,
        }
        snapshot = {
            "requested_symbol": "YM",
            "normalized_symbol": "YM",
            "latest_price": 52146.0,
            "latest_bar_time": "2026-06-24T13:57:00Z",
            "ohlc_is_closed": True,
            "ohlc": dict(reclaim_candle),
            "tv_context": {
                "levels": {
                    "PMH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "LH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "ONH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "YH": {"price": 52281.0, "status": "ACTIVE", "stack_group": "NONE"},
                }
            },
            "liquidity": {
                "nearest_level_above": {"name": "YH", "price": 52281.0},
                "nearest_level_below": {"name": "PMH", "price": 52176.0},
                "tick_size": 1.0,
            },
            "step_2_1a": {
                "step_2_activated": True,
                "active_level": "PMH",
                "level_price": 52176.0,
                "side": "upper",
                "candle_index": 17,
                "step2_activation_candle_index": 10,
                "step2_activated_at": "2026-06-24T13:50:00Z",
                "step2_locked_owner": {
                    "pathway": "rejection",
                    "setup_direction": "SHORT",
                    "side": "upper",
                    "close_boundary": 52176.0,
                    "extreme_boundary": 52176.0,
                    "active_liquidity": {"name": "PMH", "price": 52176.0, "side": "upper"},
                },
                "next_same_side_liquidity": {"name": "YH", "price": 52281.0},
                "active_liquidity_group": {
                    "name": "HIGH 1",
                    "side": "upper",
                    "close_boundary": 52176.0,
                    "extreme_boundary": 52176.0,
                    "wick_boundary_extreme": None,
                },
            },
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 52176.0},
            "step25": {
                "status": "READY",
                "state": {
                    "controlling_mode": "R/S",
                    "continuation_step2_activated": True,
                    "reclaim_candle_a": dict(reclaim_candle),
                    "continuation_probe_boundary": {
                        "active": True,
                        "side": "upper",
                        "source_level": "PMH",
                        "boundary_price": 52165.0,
                    },
                    "current_boundary": 52165.0,
                    "step25_block_reason": "Continuation reclaim is active from the seeded boundary.",
                },
            },
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4", "state": {}},
            "step4": {"status": "WAIT", "reason": "Step 4 waiting for continuation Candle B.", "state": {}},
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        previous_state = {
            "state_by_symbol": {
                "YM": {
                    "rejection_lane": {
                        "lane_name": "rejection",
                        "lane_status": "frozen",
                        "pathway_status": "frozen",
                        "active_liquidity_name": "PMH/LH/ONH Liquidity",
                        "liquidity_group": "HIGH 1",
                        "active_liquidity_price": 52176.0,
                        "close_boundary": 52176.0,
                        "extreme_boundary": 52176.0,
                        "wick_boundary_extreme": None,
                        "candle_count": 6,
                        "step2_status": "CONFIRMED",
                        "step4_status": "CONFIRMED",
                        "step2_step4_50_line": 52228.5,
                        "step4_step5_75_line": 52254.75,
                        "invalidation_reason": None,
                    },
                    "continuation_lane": {
                        "lane_name": "continuation",
                        "lane_status": "eligible",
                        "pathway_status": "eligible",
                        "active_liquidity_name": "PMH/LH/ONH Liquidity",
                        "liquidity_group": "HIGH 1",
                        "active_liquidity_price": 52176.0,
                        "close_boundary": 52176.0,
                        "extreme_boundary": 52176.0,
                        "wick_boundary_extreme": 52165.0,
                        "candle_count": None,
                        "step2_status": "WAIT",
                        "step4_status": "WAIT",
                        "step2_step4_50_line": None,
                        "step4_step5_75_line": None,
                        "invalidation_reason": None,
                    },
                    "step25": {
                        "state": {
                            "continuation_eligible_source": "frozen_rejection_trade_state",
                        }
                    },
                }
            }
        }
        original_run_once = entry_agent.run_once
        original_load_state = entry_agent.load_entry_state
        entry_agent.run_once = lambda symbol, persist=True: copy.deepcopy(snapshot)
        entry_agent.load_entry_state = lambda: copy.deepcopy(previous_state)
        try:
            status = entry_agent.build_entry_status("YM")
        finally:
            entry_agent.run_once = original_run_once
            entry_agent.load_entry_state = original_load_state

        self.assertEqual(status["rejection_lane"]["lane_status"], "frozen")
        self.assertEqual(status["continuation_lane"]["lane_status"], "controlling")
        self.assertEqual(status["continuation_lane"]["step2_status"], "CONFIRMED")
        self.assertEqual(status["continuation_lane"]["step4_status"], "WAIT")
        self.assertEqual(
            status["continuation_lane"]["step2_reason"],
            "Continuation Step 2 confirmed; lane frozen and controlling. Waiting for Step 4 participation.",
        )
        self.assertEqual(status["continuation_lane"]["selected_lane_display"], "YES")
        self.assertEqual(status["continuation_lane"]["step2_owner_frozen_display"], "YES")
        self.assertEqual(status["continuation_lane"]["lane_frozen_by_continuation_handoff_display"], "N/A")
        self.assertIsNone(status["continuation_lane"]["step2_step4_50_line"])
        self.assertIsNone(status["continuation_lane"]["step4_step5_75_line"])
        self.assertEqual(status["rejection_lane"]["candle_count"], 6)
        self.assertEqual(status["selected_pathway"], "continuation")
        self.assertEqual(status["step2_status"], "CONFIRMED")
        self.assertEqual(status["step4_status"], "WAIT")
        self.assertIsNone(status["step2_step4_50_line"])
        self.assertIsNone(status["step4_step5_75_line"])
        self.assertIsNone(status["step4_participation_50_line"])
        self.assertIsNone(status["step4_participation_75_line"])
        self.assertIsNone(status["invalidation_reason"])
        self.assertEqual(status["active_liquidity_name"], "PMH")

    def test_public_projection_maps_internal_step4_ready_to_confirmed(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        snapshot = {
            "requested_symbol": "YM",
            "normalized_symbol": "YM",
            "latest_price": 52150.0,
            "latest_bar_time": "2026-06-24T13:58:00Z",
            "ohlc_is_closed": True,
            "ohlc": {
                "timestamp": "2026-06-24T13:58:00Z",
                "open": 52148.0,
                "high": 52159.0,
                "low": 52143.0,
                "close": 52150.0,
            },
            "tv_context": {
                "levels": {
                    "PMH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "LH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "ONH": {"price": 52176.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "YH": {"price": 52281.0, "status": "ACTIVE", "stack_group": "NONE"},
                }
            },
            "liquidity": {
                "nearest_level_above": {"name": "YH", "price": 52281.0},
                "nearest_level_below": {"name": "PMH", "price": 52176.0},
                "tick_size": 1.0,
            },
            "step_2_1a": {
                "step_2_activated": True,
                "active_level": "PMH",
                "level_price": 52176.0,
                "side": "upper",
                "candle_index": 18,
                "step2_activation_candle_index": 10,
                "step2_activated_at": "2026-06-24T13:50:00Z",
                "step2_locked_owner": {
                    "pathway": "rejection",
                    "setup_direction": "SHORT",
                    "side": "upper",
                    "close_boundary": 52176.0,
                    "extreme_boundary": 52176.0,
                    "active_liquidity": {"name": "PMH", "price": 52176.0, "side": "upper"},
                },
                "next_same_side_liquidity": {"name": "YH", "price": 52281.0},
                "active_liquidity_group": {
                    "name": "HIGH 1",
                    "side": "upper",
                    "close_boundary": 52176.0,
                    "extreme_boundary": 52176.0,
                    "wick_boundary_extreme": None,
                },
            },
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 52176.0},
            "step25": {
                "status": "READY",
                "state": {
                    "controlling_mode": "Normal Rejection Mode",
                },
            },
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4", "state": {}},
            "step4": {"status": "READY", "reason": "Leg 1 complete.", "next_step": "Step 5", "state": {"leg1_status": "COMPLETE", "active_liquidity": {"name": "PMH", "price": 52176.0, "side": "upper"}}},
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        previous_state = {
            "state_by_symbol": {
                "YM": {
                    "rejection_lane": {},
                    "continuation_lane": {},
                }
            }
        }
        original_run_once = entry_agent.run_once
        original_load_state = entry_agent.load_entry_state
        entry_agent.run_once = lambda symbol, persist=True: copy.deepcopy(snapshot)
        entry_agent.load_entry_state = lambda: copy.deepcopy(previous_state)
        try:
            status = entry_agent.build_entry_status("YM")
        finally:
            entry_agent.run_once = original_run_once
            entry_agent.load_entry_state = original_load_state

        self.assertEqual(status["step4_status"], "CONFIRMED")
        self.assertEqual(status["continuation_lane"]["step4_status"], "WAIT")
        self.assertEqual(status["rejection_lane"]["step4_status"], "CONFIRMED")

    def test_leg1_leg2_and_entry_confirmed_at_use_confirmation_candle_times(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        leg1_time = "2026-05-15T13:47:00Z"
        leg2_time = "2026-05-15T13:52:00Z"
        entry_time = "2026-05-15T13:53:00Z"
        original_run_once = entry_agent.run_once
        original_consumed_guard = entry_agent.apply_consumed_entry_setup_guard
        entry_agent.run_once = lambda symbol, persist=True: {
            "requested_symbol": symbol,
            "normalized_symbol": "NQ",
            "latest_price": 101.0,
            "latest_bar_time": entry_time,
            "ohlc_is_closed": True,
            "ohlc": {"open": 100.5, "high": 101.5, "low": 100.0, "close": 101.0},
            "liquidity": {},
            "step_2_1a": {"step_2_activated": True, "active_level": "PMH", "level_price": 100.0, "side": "upper", "candle_a": {"timestamp": "2026-05-15T13:45:00Z"}},
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 100.0},
            "step25": {"status": "READY", "state": {"controlling_mode": "Normal Rejection Mode"}},
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4", "state": {}},
            "step4": {
                "status": "READY",
                "next_step": "Step 5",
                "state": {
                    "leg1_state_locked": True,
                    "leg1_status": "COMPLETE",
                    "leg1_completed_at": leg1_time,
                    "leg1_reference_price": 100.0,
                    "leg1_reference_candle_time": "2026-05-15T13:46:00Z",
                    "leg1_direction": "SHORT",
                    "setup_direction": "SHORT",
                    "active_liquidity": {"name": "PMH", "price": 100.0, "side": "upper"},
                    "candle_a": {"timestamp": "2026-05-15T13:46:00Z"},
                    "candle_b": {"timestamp": leg1_time},
                },
            },
            "step5": {
                "status": "READY",
                "next_step": "Step 6",
                "state": {
                    "leg2_status": "VALIDATED",
                    "leg2_candidate_candle_time": leg2_time,
                    "leg2_candle": {"timestamp": leg2_time},
                    "setup_direction": "SHORT",
                    "active_liquidity": {"name": "PMH", "price": 100.0, "side": "upper"},
                    "leg1_state_locked": True,
                    "leg1_status": "COMPLETE",
                    "leg1_completed_at": leg1_time,
                    "leg1_reference_price": 100.0,
                    "leg1_reference_candle_time": "2026-05-15T13:46:00Z",
                    "leg1_direction": "SHORT",
                    "candle_a": {"timestamp": "2026-05-15T13:46:00Z"},
                    "candle_b": {"timestamp": leg1_time},
                },
            },
            "step6": {
                "status": "ENTRY_CONFIRMED",
                "next_step": "Step 6",
                "state": {
                    "entry_triggered": True,
                    "entry_candle": {"timestamp": entry_time},
                    "setup_direction": "SHORT",
                },
                "reason": "entry confirmed",
            },
        }
        entry_agent.apply_consumed_entry_setup_guard = lambda _snapshot: None
        try:
            status = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once
            entry_agent.apply_consumed_entry_setup_guard = original_consumed_guard

        self.assertEqual(status["current_step"], "Step 6")
        self.assertEqual(status["leg1_confirmed_at"], leg1_time)
        self.assertEqual(status["leg2_confirmed_at"], leg2_time)
        self.assertEqual(status["entry_status_confirmed_at"], entry_time)
        self.assertEqual(status["current_step_confirmed_at"], entry_time)

    def test_reset_clears_confirmed_at_fields(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        entry_agent.run_once = lambda symbol, persist=True: {
            "requested_symbol": symbol,
            "normalized_symbol": "NQ",
            "latest_price": 99.0,
            "latest_bar_time": "2026-05-15T14:00:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 99.0, "high": 99.5, "low": 98.5, "close": 99.0},
            "liquidity": {},
            "step_2_1a": {"step_2_activated": False},
            "rejection": {"rejection_mode": "OFF"},
            "step25": {"status": "WAIT", "state": {}},
            "step3": {"status": "WAIT", "state": {}},
            "step4": {"status": "WAIT", "state": {}},
            "step5": {"status": "WAIT", "state": {}},
            "step6": {"status": "WAIT", "state": {}},
        }
        try:
            status = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once

        self.assertIsNone(status["current_step_confirmed_at"])
        self.assertIsNone(status["leg1_confirmed_at"])
        self.assertIsNone(status["leg2_confirmed_at"])
        self.assertIsNone(status["entry_status_confirmed_at"])

    def test_sr_continuation_waits_for_controlling_structure_sweep(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_recent = entry_agent.recent_closed_bars
        original_step6 = entry_agent.evaluate_step6
        entry_agent.recent_closed_bars = lambda _symbol, _limit: [
            {"timestamp": "2026-05-15T13:20:00Z", "open": 100.25, "high": 100.50, "low": 98.75, "close": 99.00},
            {"timestamp": "2026-05-15T13:21:00Z", "open": 99.00, "high": 101.00, "low": 98.90, "close": 100.50},
            {"timestamp": "2026-05-15T13:22:00Z", "open": 100.50, "high": 100.60, "low": 99.50, "close": 100.00},
        ]
        entry_agent.evaluate_step6 = lambda _interaction: self.fail("Step 6 should not evaluate before continuation structure sweep")
        snapshot = {
            "normalized_symbol": "NQ",
            "latest_bar_time": "2026-05-15T13:22:00Z",
            "ohlc": {"open": 100.50, "high": 100.60, "low": 99.50, "close": 100.00},
            "liquidity": {"tick_size": 0.25},
        }
        step5 = {
            "status": "READY",
            "next_step": "Step 6",
            "state": {
                "controlling_mode": "S/R",
                "pathway_level": 100.0,
                "tick_size": 0.25,
                "reclaim_candle_a": {"timestamp": "2026-05-15T13:21:00Z", "open": 99.0, "high": 101.0, "low": 98.9, "close": 100.5},
                "leg2_status": "VALIDATED",
                "leg2_candle": {"timestamp": "2026-05-15T13:22:00Z", "open": 100.5, "high": 100.6, "low": 99.5, "close": 100.0},
            },
        }
        try:
            result = entry_agent.evaluate_live_step6(snapshot, step5, {})
        finally:
            entry_agent.recent_closed_bars = original_recent
            entry_agent.evaluate_step6 = original_step6

        self.assertEqual(result["status"], "WAIT")
        self.assertFalse(result["state"]["continuation_controlling_structure_swept"])
        self.assertIn("sweep", result["reason"])

    def test_sr_continuation_sweep_allows_step6_evaluation(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_recent = entry_agent.recent_closed_bars
        original_step6 = entry_agent.evaluate_step6
        entry_agent.recent_closed_bars = lambda _symbol, _limit: [
            {"timestamp": "2026-05-15T13:20:00Z", "open": 100.25, "high": 100.50, "low": 98.75, "close": 99.00},
            {"timestamp": "2026-05-15T13:21:00Z", "open": 99.00, "high": 101.00, "low": 98.90, "close": 100.50},
        ]
        entry_agent.evaluate_step6 = lambda interaction: {
            "step": "Step 6",
            "status": "ENTRY_CONFIRMED",
            "next_step": "Step 6",
            "state": dict(interaction, entry_triggered=True),
            "reason": "entry allowed",
            "events": [],
        }
        snapshot = {
            "normalized_symbol": "NQ",
            "latest_bar_time": "2026-05-15T13:22:00Z",
            "ohlc": {"open": 100.50, "high": 100.75, "low": 99.50, "close": 100.00},
            "liquidity": {"tick_size": 0.25},
        }
        step5 = {
            "status": "READY",
            "next_step": "Step 6",
            "state": {
                "controlling_mode": "S/R",
                "pathway_level": 100.0,
                "tick_size": 0.25,
                "reclaim_candle_a": {"timestamp": "2026-05-15T13:21:00Z", "open": 99.0, "high": 101.0, "low": 98.9, "close": 100.5},
                "leg2_status": "VALIDATED",
                "leg2_candle": {"timestamp": "2026-05-15T13:22:00Z", "open": 100.5, "high": 100.75, "low": 99.5, "close": 100.0},
            },
        }
        try:
            result = entry_agent.evaluate_live_step6(snapshot, step5, {})
        finally:
            entry_agent.recent_closed_bars = original_recent
            entry_agent.evaluate_step6 = original_step6

        self.assertEqual(result["status"], "ENTRY_CONFIRMED")
        self.assertTrue(result["state"]["continuation_controlling_structure_swept"])

    def test_sr_continuation_reset_uses_next_bearish_close_through_push(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        bars = [
            {"timestamp": "2026-05-15T13:18:00Z", "open": 100.25, "high": 100.40, "low": 98.50, "close": 99.00},
            {"timestamp": "2026-05-15T13:19:00Z", "open": 98.90, "high": 99.70, "low": 98.80, "close": 99.50},
            {"timestamp": "2026-05-15T13:20:00Z", "open": 99.50, "high": 99.60, "low": 98.60, "close": 98.80},
            {"timestamp": "2026-05-15T13:21:00Z", "open": 98.80, "high": 100.50, "low": 98.70, "close": 100.25},
        ]

        structure = entry_agent.continuation_controlling_structure_from_bars("S/R", 100.0, bars, "2026-05-15T13:21:00Z")

        self.assertEqual(structure["start_time"], "2026-05-15T13:20:00Z")
        self.assertEqual(structure["end_time"], "2026-05-15T13:20:00Z")
        self.assertEqual(structure["low"], 98.60)

    def test_rs_continuation_waits_for_controlling_structure_sweep(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_recent = entry_agent.recent_closed_bars
        original_step6 = entry_agent.evaluate_step6
        entry_agent.recent_closed_bars = lambda _symbol, _limit: [
            {"timestamp": "2026-05-15T13:20:00Z", "open": 99.75, "high": 101.25, "low": 99.50, "close": 101.00},
            {"timestamp": "2026-05-15T13:21:00Z", "open": 101.00, "high": 101.10, "low": 99.00, "close": 99.50},
            {"timestamp": "2026-05-15T13:22:00Z", "open": 99.50, "high": 100.50, "low": 99.40, "close": 100.00},
        ]
        entry_agent.evaluate_step6 = lambda _interaction: self.fail("Step 6 should not evaluate before continuation structure sweep")
        snapshot = {
            "normalized_symbol": "NQ",
            "latest_bar_time": "2026-05-15T13:22:00Z",
            "ohlc": {"open": 99.50, "high": 100.50, "low": 99.40, "close": 100.00},
            "liquidity": {"tick_size": 0.25},
        }
        step5 = {
            "status": "READY",
            "next_step": "Step 6",
            "state": {
                "controlling_mode": "R/S",
                "pathway_level": 100.0,
                "tick_size": 0.25,
                "reclaim_candle_a": {"timestamp": "2026-05-15T13:21:00Z", "open": 101.0, "high": 101.1, "low": 99.0, "close": 99.5},
                "leg2_status": "VALIDATED",
                "leg2_candle": {"timestamp": "2026-05-15T13:22:00Z", "open": 99.5, "high": 100.5, "low": 99.4, "close": 100.0},
            },
        }
        try:
            result = entry_agent.evaluate_live_step6(snapshot, step5, {})
        finally:
            entry_agent.recent_closed_bars = original_recent
            entry_agent.evaluate_step6 = original_step6

        self.assertEqual(result["status"], "WAIT")
        self.assertFalse(result["state"]["continuation_controlling_structure_swept"])
        self.assertIn("controlling-structure low", result["reason"])

    def test_rs_continuation_sweep_allows_step6_evaluation(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_recent = entry_agent.recent_closed_bars
        original_step6 = entry_agent.evaluate_step6
        entry_agent.recent_closed_bars = lambda _symbol, _limit: [
            {"timestamp": "2026-05-15T13:20:00Z", "open": 99.75, "high": 101.25, "low": 99.50, "close": 101.00},
            {"timestamp": "2026-05-15T13:21:00Z", "open": 101.00, "high": 101.10, "low": 99.00, "close": 99.50},
        ]
        entry_agent.evaluate_step6 = lambda interaction: {
            "step": "Step 6",
            "status": "ENTRY_CONFIRMED",
            "next_step": "Step 6",
            "state": dict(interaction, entry_triggered=True),
            "reason": "entry allowed",
            "events": [],
        }
        snapshot = {
            "normalized_symbol": "NQ",
            "latest_bar_time": "2026-05-15T13:22:00Z",
            "ohlc": {"open": 99.50, "high": 100.50, "low": 99.25, "close": 100.00},
            "liquidity": {"tick_size": 0.25},
        }
        step5 = {
            "status": "READY",
            "next_step": "Step 6",
            "state": {
                "controlling_mode": "R/S",
                "pathway_level": 100.0,
                "tick_size": 0.25,
                "reclaim_candle_a": {"timestamp": "2026-05-15T13:21:00Z", "open": 101.0, "high": 101.1, "low": 99.0, "close": 99.5},
                "leg2_status": "VALIDATED",
                "leg2_candle": {"timestamp": "2026-05-15T13:22:00Z", "open": 99.5, "high": 100.5, "low": 99.25, "close": 100.0},
            },
        }
        try:
            result = entry_agent.evaluate_live_step6(snapshot, step5, {})
        finally:
            entry_agent.recent_closed_bars = original_recent
            entry_agent.evaluate_step6 = original_step6

        self.assertEqual(result["status"], "ENTRY_CONFIRMED")
        self.assertTrue(result["state"]["continuation_controlling_structure_swept"])

    def test_rs_continuation_reset_uses_next_bullish_close_through_push(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        bars = [
            {"timestamp": "2026-05-15T13:18:00Z", "open": 99.75, "high": 101.50, "low": 99.60, "close": 101.00},
            {"timestamp": "2026-05-15T13:19:00Z", "open": 101.10, "high": 101.20, "low": 100.40, "close": 100.50},
            {"timestamp": "2026-05-15T13:20:00Z", "open": 100.50, "high": 101.40, "low": 100.40, "close": 101.20},
            {"timestamp": "2026-05-15T13:21:00Z", "open": 101.20, "high": 101.30, "low": 99.50, "close": 99.75},
        ]

        structure = entry_agent.continuation_controlling_structure_from_bars("R/S", 100.0, bars, "2026-05-15T13:21:00Z")

        self.assertEqual(structure["start_time"], "2026-05-15T13:20:00Z")
        self.assertEqual(structure["end_time"], "2026-05-15T13:20:00Z")
        self.assertEqual(structure["high"], 101.40)

    def test_step2_wick_touch_selects_liquidity_but_waits_for_boundary_close(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        tv_context = {
            "levels": {
                "PMH": {"price": 49307, "status": "ACTIVE", "stack_group": "NONE"}
            }
        }

        selected = entry_agent.selected_active_liquidity_from_context(
            tv_context,
            49300,
            {"open": 49290, "high": 49310, "low": 49280, "close": 49300},
            tick_size=1.0,
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected["name"], "PMH")

        upper = entry_agent.step_2_1a_initial_state("PMH", 49307.0, "upper", tick_size=1.0)
        entry_agent.evaluate_step_2_1a_candle(
            upper,
            {"timestamp": "2026-05-19T13:30:00Z", "open": 49290, "high": 49310, "low": 49280, "close": 49300},
            0,
        )
        self.assertFalse(upper["step_2_activated"])
        self.assertTrue(upper["pre_activation_probe_boundary"]["active"])
        self.assertEqual(upper["pre_activation_probe_boundary"]["boundary_price"], 49310)
        entry_agent.evaluate_step_2_1a_candle(
            upper,
            {"timestamp": "2026-05-19T13:31:00Z", "open": 49302, "high": 49320, "low": 49298, "close": 49309},
            1,
        )
        self.assertFalse(upper["step_2_activated"])
        self.assertEqual(upper["pre_activation_probe_boundary"]["boundary_price"], 49320)
        entry_agent.evaluate_step_2_1a_candle(
            upper,
            {"timestamp": "2026-05-19T13:32:00Z", "open": 49310, "high": 49322, "low": 49308, "close": 49321},
            2,
        )
        self.assertTrue(upper["step_2_activated"])

        lower = entry_agent.step_2_1a_initial_state("PML", 100.0, "lower", tick_size=0.25)
        entry_agent.evaluate_step_2_1a_candle(
            lower,
            {"timestamp": "2026-05-19T13:30:00Z", "open": 100.5, "high": 100.75, "low": 99.5, "close": 100.1},
            0,
        )
        self.assertFalse(lower["step_2_activated"])
        self.assertTrue(lower["pre_activation_probe_boundary"]["active"])
        self.assertEqual(lower["pre_activation_probe_boundary"]["boundary_price"], 99.5)
        entry_agent.evaluate_step_2_1a_candle(
            lower,
            {"timestamp": "2026-05-19T13:31:00Z", "open": 100.0, "high": 100.25, "low": 99.0, "close": 99.6},
            1,
        )
        self.assertFalse(lower["step_2_activated"])
        self.assertEqual(lower["pre_activation_probe_boundary"]["boundary_price"], 99.0)
        entry_agent.evaluate_step_2_1a_candle(
            lower,
            {"timestamp": "2026-05-19T13:32:00Z", "open": 99.6, "high": 99.8, "low": 98.75, "close": 98.75},
            2,
        )
        self.assertTrue(lower["step_2_activated"])

    def test_ym_pml_ll_low_stack_selects_on_interaction_without_forcing_step2(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        tv_context = {
            "levels": {
                "PML": {"price": 49731.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "LL": {"price": 49730.0, "status": "ACTIVE", "stack_group": "LOW 1"},
            }
        }

        inside_candle = {"open": 49732.0, "high": 49733.0, "low": 49730.25, "close": 49730.5}
        exact_ll_candle = {"open": 49731.0, "high": 49732.0, "low": 49729.0, "close": 49730.0}
        beyond_ll_candle = {"open": 49731.0, "high": 49732.0, "low": 49728.0, "close": 49729.0}

        inside = entry_agent.selected_active_liquidity_from_context(
            tv_context,
            49730.5,
            inside_candle,
            tick_size=1.0,
        )
        exact_ll = entry_agent.selected_active_liquidity_from_context(
            tv_context,
            49730.0,
            exact_ll_candle,
            tick_size=1.0,
        )
        beyond_ll = entry_agent.selected_active_liquidity_from_context(
            tv_context,
            49729.0,
            beyond_ll_candle,
            tick_size=1.0,
        )

        for selected in (inside, exact_ll, beyond_ll):
            self.assertEqual(selected["name"], "LL")
            self.assertEqual(selected["price"], 49730.0)
            self.assertEqual(selected["display_name"], "PML/LL Liquidity")
            self.assertEqual(selected["group"]["display_name"], "PML/LL Liquidity")
            self.assertEqual(selected["group"]["close_boundary"], 49731.0)
            self.assertEqual(selected["group"]["extreme_boundary"], 49730.0)
            self.assertEqual(selected["group"]["close_component"], "PML")
            self.assertEqual(selected["group"]["extreme_component"], "LL")

        step2 = entry_agent.step_2_1a_initial_state(inside["name"], inside["price"], inside["side"], 1.0)
        entry_agent.evaluate_step_2_1a_candle(
            step2,
            {
                **inside_candle,
                "timestamp": "2026-06-10T13:45:00Z",
                "active_level": inside["name"],
                "level_price": inside["price"],
            },
            0,
        )
        self.assertFalse(step2["step_2_activated"])

    def test_ym_below_pmh_does_not_mark_pmh_active_liquidity(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = lambda _symbol: {
                "source": "test",
                "symbol": "YMM6",
                "latest_price": 49200,
                "latest_bar_time": "2026-05-06T15:00:00Z",
                "ohlc": {"open": 49195, "high": 49205, "low": 49190, "close": 49200},
            }
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "YM": {
                                "symbol": "YM1!",
                                "levels": {
                                    "PMH": {"price": 49307, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            status = entry_agent.build_entry_status("YMM6")
            self.assertIsNone(status["active_liquidity_name"])
            self.assertIsNone(status["active_liquidity_price"])
            self.assertEqual(status["next_liquidity_above"], {"name": "PMH", "price": 49307.0})

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_ym_touching_pmh_marks_pmh_active_liquidity(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = lambda _symbol: {
                "source": "test",
                "symbol": "YMM6",
                "latest_price": 49307,
                "latest_bar_time": "2026-05-06T15:00:00Z",
                "ohlc": {"open": 49300, "high": 49307, "low": 49295, "close": 49307},
            }
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "YM": {
                                "symbol": "YM1!",
                                "levels": {
                                    "PMH": {"price": 49307, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            status = entry_agent.build_entry_status("YMM6")
            self.assertEqual(status["active_liquidity_name"], "PMH")
            self.assertEqual(status["active_liquidity_price"], 49307.0)

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_active_liquidity_persists_after_rejection_and_updates_on_new_interaction(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        market = {
            "latest_price": 49200,
            "latest_bar_time": "2026-05-06T15:00:00Z",
            "ohlc": {"open": 49195, "high": 49205, "low": 49190, "close": 49200},
        }

        def fake_market_snapshot(_symbol):
            return {
                "source": "test",
                "symbol": "YMM6",
                "latest_price": market["latest_price"],
                "latest_bar_time": market["latest_bar_time"],
                "ohlc": dict(market["ohlc"]),
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = fake_market_snapshot
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "YM": {
                                "symbol": "YM1!",
                                "levels": {
                                    "PMH": {"price": 49307, "status": "ACTIVE", "stack_group": "NONE"},
                                    "ONH": {"price": 49400, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            below = entry_agent.build_entry_status("YMM6")
            self.assertIsNone(below["active_liquidity_name"])

            market.update(
                {
                    "latest_price": 49307,
                    "latest_bar_time": "2026-05-06T15:01:00Z",
                    "ohlc": {"open": 49300, "high": 49307, "low": 49295, "close": 49307},
                }
            )
            touch = entry_agent.build_entry_status("YMM6")
            # These timestamps are after the regular session close, so the public
            # endpoint no longer projects active liquidity ownership here.
            self.assertIsNone(touch["active_liquidity_name"])
            self.assertIsNone(touch["active_liquidity_price"])

            market.update(
                {
                    "latest_price": 49280,
                    "latest_bar_time": "2026-05-06T15:02:00Z",
                    "ohlc": {"open": 49300, "high": 49302, "low": 49275, "close": 49280},
                }
            )
            reject_away = entry_agent.build_entry_status("YMM6")
            self.assertIsNone(reject_away["active_liquidity_name"])
            self.assertIsNone(reject_away["active_liquidity_price"])

            market.update(
                {
                    "latest_price": 49400,
                    "latest_bar_time": "2026-05-06T15:03:00Z",
                    "ohlc": {"open": 49390, "high": 49400, "low": 49385, "close": 49400},
                }
            )
            new_level = entry_agent.build_entry_status("YMM6")
            self.assertIsNone(new_level["active_liquidity_name"])
            self.assertIsNone(new_level["active_liquidity_price"])

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_stale_step5_state_is_cleared_when_active_liquidity_becomes_na(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = lambda symbol: {
                "source": "test",
                "symbol": symbol,
                "latest_price": 49280,
                "latest_bar_time": "2026-05-06T15:02:00Z",
                "ohlc": {"open": 49300, "high": 49302, "low": 49275, "close": 49280},
            }
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "YM": {
                                "symbol": "YM1!",
                                "levels": {
                                    "PMH": {"price": 49307, "status": "n/a", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            stale_state = {
                "state_by_symbol": {
                    "YM": {
                        "normalized_symbol": "YM",
                        "step_2_1a": {
                            "active_level": "PMH",
                            "level_price": 49307.0,
                            "last_interacted_liquidity": {"name": "PMH", "price": 49307.0},
                        },
                        "last_interacted_liquidity": {"name": "PMH", "price": 49307.0},
                        "step4": {
                            "status": "READY",
                            "state": {
                                "setup_direction": "SHORT",
                                "leg1_status": "COMPLETE",
                                "leg1_state_locked": True,
                                "leg1_completed_at": "2026-05-06T15:01:00Z",
                                "leg1_reference_price": 49307.0,
                                "active_liquidity": {"name": "PMH", "price": 49307.0},
                            },
                        },
                        "step5": {
                            "status": "READY",
                            "state": {
                                "setup_direction": "SHORT",
                                "leg2_status": "CONFIRMED",
                                "leg2_candidate_candle_time": "2026-05-06T15:02:00Z",
                                "leg2_reference_price": 49307.0,
                                "invalidation_source": "stale",
                            },
                        },
                    }
                },
                "last_interacted_liquidity_by_symbol": {
                    "YM": {"name": "PMH", "price": 49307.0},
                },
            }
            entry_agent.STATE_PATH.write_text(json.dumps(stale_state), encoding="utf-8")

            status = entry_agent.build_entry_status("YMM6")
            persisted = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))["state_by_symbol"]["YM"]

            self.assertEqual(status["current_step"], "Step 2")
            self.assertEqual(status["current_step_label"], "Step 2 (Liquidity Close / Pathway Activation)")
            self.assertEqual(status["entry_status"], "WAIT")
            self.assertEqual(status["wait_reason"], "No active liquidity selected.")
            self.assertIsNone(status["active_liquidity_name"])
            self.assertIsNone(status["active_liquidity_price"])
            self.assertIsNone(status["setup_direction"])
            self.assertFalse(status["rejection_mode_entered"])
            self.assertEqual(status["leg1_status"], "WAIT")
            self.assertEqual(status["leg2_status"], "WAIT")
            self.assertIsNone(status["leg1_completed_at"])
            self.assertIsNone(status["leg1_reference_price"])
            self.assertIsNone(status["leg2_candidate_candle_time"])
            self.assertIsNone(status["leg2_reference_price"])
            self.assertIsNone(status["invalidation_source"])
            self.assertIsNone(status["invalidation_reason"])
            self.assertIsNone(persisted["step_2_1a"]["last_interacted_liquidity"])
            self.assertEqual(persisted["step5"]["state"], {})
            self.assertNotIn("YM", persisted["last_interacted_liquidity_by_symbol"])

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_intrabar_poke_does_not_publish_leg1_complete_until_close_confirmed(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        market = {
            "ohlc_is_closed": False,
            "ohlc": {"open": 50000.0, "high": 50012.0, "low": 49996.0, "close": 50008.0},
        }

        def fake_market_snapshot(symbol):
            return {
                "source": "test",
                "symbol": symbol,
                "latest_price": market["ohlc"]["close"],
                "latest_bar_time": "2026-05-06T14:59:00Z",
                "ohlc": dict(market["ohlc"]),
                "ohlc_is_closed": market["ohlc_is_closed"],
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = fake_market_snapshot
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "levels": {
                                    "PMH": {"price": 50000.0, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            entry_agent.STATE_PATH.write_text(
                json.dumps(
                    {
                        "state_by_symbol": {
                            "NQ": {
                                "normalized_symbol": "NQ",
                                "last_interacted_liquidity": {"name": "PMH", "price": 50000.0, "side": "upper"},
                                "step_2_1a": {
                                    "active_level": "PMH",
                                    "level_price": 50000.0,
                                    "last_interacted_liquidity": {"name": "PMH", "price": 50000.0, "side": "upper"},
                                },
                                "step4": {
                                    "status": "READY",
                                    "next_step": "Step 5",
                                    "state": {
                                        "setup_direction": "SHORT",
                                        "leg1_status": "COMPLETE",
                                        "leg1_state_locked": True,
                                        "leg1_completed_at": "2026-05-06T14:59:00Z",
                                        "leg1_reference_price": 50010.0,
                                        "leg1_reference_candle_time": "2026-05-06T14:59:00Z",
                                        "leg1_direction": "SHORT",
                                        "active_liquidity": {"name": "PMH", "price": 50000.0},
                                        "candle_a": {"timestamp": "2026-05-06T14:58:00Z"},
                                        "candle_b": {"timestamp": "2026-05-06T14:59:00Z"},
                                    },
                                },
                            }
                        },
                        "last_interacted_liquidity_by_symbol": {
                            "NQ": {"name": "PMH", "price": 50000.0, "side": "upper"},
                        },
                    }
                ),
                encoding="utf-8",
            )

            intrabar = entry_agent.build_entry_status("NQM6")
            self.assertEqual(intrabar["entry_status"], "WAIT")
            self.assertNotIn(intrabar["current_step"], {"Step 5", "Step 6"})
            self.assertEqual(intrabar["leg1_status"], "WAIT")
            self.assertIsNone(intrabar["setup_direction"])
            # Intrabar Step 4 keeps completion fields blank while publication is suppressed.
            self.assertIsNone(intrabar["leg1_completed_at"])
            self.assertIn(
                intrabar["wait_reason"],
                {
                    "Monitoring current 1-minute candle until close confirmation.",
                    "No active liquidity selected.",
                },
            )

            market["ohlc_is_closed"] = True
            confirmed = entry_agent.build_entry_status("NQM6")
            self.assertEqual(confirmed["current_step"], "Step 4")
            self.assertEqual(confirmed["leg1_status"], "COMPLETE")
            self.assertNotEqual(confirmed["wait_reason"], "Monitoring current 1-minute candle until close confirmation.")

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_unclosed_current_candle_does_not_publish_advanced_status_fields(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        current_time = "2026-05-07T13:45:00Z"
        current_candle = {
            "open": 50000.0,
            "high": 50020.0,
            "low": 49995.0,
            "close": 50015.0,
            "timestamp": current_time,
        }

        def fake_run_once(symbol, persist=True):
            return {
                "requested_symbol": symbol,
                "normalized_symbol": "NQ",
                "latest_price": current_candle["close"],
                "latest_bar_time": current_time,
                "ohlc": dict(current_candle),
                "ohlc_is_closed": False,
                "liquidity": {"tick_size": 0.25},
                "step_2_1a": {
                    "active_level": "PMH",
                    "level_price": 50000.0,
                    "last_interacted_liquidity": {"name": "PMH", "price": 50000.0},
                },
                "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 50000.0},
                "step25": {"status": "READY"},
                "step3": {"status": "ALLOW_STEP_4"},
                "step4": {
                    "status": "READY",
                    "next_step": "Step 5",
                    "state": {
                        "setup_direction": "SHORT",
                        "leg1_direction": "SHORT",
                        "leg1_status": "COMPLETE",
                        "leg1_state_locked": True,
                        "leg1_completed_at": current_time,
                        "leg1_reference_candle_time": current_time,
                        "latest_candle": dict(current_candle),
                    },
                },
                "step5": {
                    "status": "READY",
                    "next_step": "Step 6",
                    "state": {
                        "setup_direction": "SHORT",
                        "leg2_status": "COMPLETE",
                        "leg2_candidate_candle_time": current_time,
                        "latest_candle": dict(current_candle),
                    },
                },
                "step6": {
                    "status": "ENTRY_CONFIRMED",
                    "state": {
                        "setup_direction": "SHORT",
                        "entry_triggered": True,
                        "entry_candidate": dict(current_candle),
                        "entry_candle": dict(current_candle),
                    },
                },
            }

        entry_agent.run_once = fake_run_once
        try:
            status = entry_agent.build_entry_status("NQM6")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(status["entry_status"], "WAIT")
        self.assertNotIn(status["current_step"], {"Step 5", "Step 6"})
        self.assertEqual(status["leg1_status"], "WAIT")
        self.assertEqual(status["leg2_status"], "WAIT")
        self.assertIsNone(status["setup_direction"])
        self.assertFalse(status["rejection_mode_entered"])
        self.assertIsNone(status["leg1_completed_at"])
        self.assertIsNone(status["leg2_candidate_candle_time"])
        self.assertEqual(status["wait_reason"], "Monitoring current 1-minute candle until close confirmation.")

    def test_build_entry_status_publishes_liquidity_leg_atr_distance_using_stack_extremes(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once

        def fake_run_once(symbol, persist=True):
            return {
                "requested_symbol": symbol,
                "normalized_symbol": "NQ",
                "latest_price": 29392.0,
                "latest_bar_time": "2026-06-16T13:20:00Z",
                "ohlc": {
                    "open": 29388.0,
                    "high": 29395.0,
                    "low": 29386.0,
                    "close": 29392.0,
                    "timestamp": "2026-06-16T13:20:00Z",
                },
                "ohlc_is_closed": True,
                "liquidity": {"tick_size": 0.25},
                "tv_context": {
                    "daily_atr14": 150.0,
                    "levels": {
                        "PMH": {"price": 29402.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                        "ONH": {"price": 29410.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                        "LH": {"price": 29418.0, "status": "ACTIVE", "stack_group": "NONE"},
                    },
                },
                "step_2_1a": {
                    "active_level": "PMH",
                    "level_price": 29402.0,
                    "last_interacted_liquidity": {"name": "PMH", "display_name": "PMH/ONH Liquidity", "price": 29402.0},
                    "active_liquidity_group": {"display_name": "PMH/ONH Liquidity", "close_boundary": 29402.0, "stack_extreme": 29410.0},
                },
                "rejection": {},
                "step25": {"status": "WAIT"},
                "step3": {"status": "WAIT"},
                "step4": {"status": "WAIT"},
                "step5": {"status": "WAIT"},
                "step6": {"status": "WAIT"},
            }

        entry_agent.run_once = fake_run_once
        try:
            status = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once

        self.assertIsNone(status["leg_anchor_liquidity"])
        self.assertEqual(status["leg_anchor_price"], 29392.0)
        self.assertEqual(status["next_active_liquidity"], "PMH/ONH Liquidity")
        # Initial leg uses the stack's actionable extreme, not the close-boundary owner.
        self.assertEqual(status["next_active_liquidity_price"], 29410.0)
        self.assertEqual(status["distance_points"], 18.0)
        self.assertEqual(status["daily_atr14"], 150.0)
        self.assertEqual(status["liquidity_leg_atr_distance_pct"], 12.0)

        fake_run_once_locked = lambda symbol, persist=True: {
            **fake_run_once(symbol, persist),
            "latest_price": 29406.0,
            "latest_bar_time": "2026-06-16T13:35:00Z",
            "ohlc": {
                "open": 29412.0,
                "high": 29416.0,
                "low": 29400.0,
                "close": 29406.0,
                "timestamp": "2026-06-16T13:35:00Z",
            },
            "step_2_1a": {
                "step_2_activated": True,
                "step2_locked_owner": {
                    "pathway": "rejection",
                    "active_liquidity": {
                        "name": "PMH",
                        "display_name": "PMH/ONH Liquidity",
                        "price": 29402.0,
                        "side": "upper",
                    },
                },
                "next_same_side_liquidity": {"name": "LH", "price": 29418.0, "side": "upper"},
            },
        }
        entry_agent.run_once = fake_run_once_locked
        try:
            locked_status = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(locked_status["leg_anchor_liquidity"], "PMH/ONH Liquidity")
        # Post-confirmation legs anchor from the prior liquidity extreme, not the Step 2 close or owner price.
        self.assertEqual(locked_status["leg_anchor_price"], 29410.0)
        self.assertEqual(locked_status["next_active_liquidity"], "LH")
        self.assertEqual(locked_status["next_active_liquidity_price"], 29418.0)
        self.assertEqual(locked_status["distance_points"], 8.0)
        self.assertEqual(locked_status["daily_atr14"], 150.0)
        self.assertEqual(locked_status["liquidity_leg_atr_distance_pct"], 5.3333)

    def test_unclosed_leg1_candle1_masks_step4_invalidation_publication(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        current_time = "2026-05-14T13:39:00Z"
        current_candle = {
            "open": 21420.0,
            "high": 21424.0,
            "low": 21410.0,
            "close": 21418.0,
            "timestamp": current_time,
        }

        def fake_run_once(symbol, persist=True):
            return {
                "requested_symbol": symbol,
                "normalized_symbol": "NQ",
                "latest_price": current_candle["close"],
                "latest_bar_time": current_time,
                "ohlc": dict(current_candle),
                "ohlc_is_closed": False,
                "liquidity": {"tick_size": 0.25},
                "step_2_1a": {
                    "active_level": "ONH",
                    "level_price": 21400.0,
                    "last_interacted_liquidity": {"name": "ONH", "price": 21400.0},
                },
                "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "ONH", "trigger_price": 21400.0},
                "step25": {"status": "READY"},
                "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4"},
                "step4": {
                    "status": "TERMINATED",
                    "next_step": "Step 1",
                    "reason": "Candle B failed both close-based participation and 34% wick-based participation.",
                    "state": {
                        "latest_candle": dict(current_candle),
                        "candle_b": dict(current_candle),
                        "leg1_status": "INVALID",
                        "leg1_window_active": True,
                        "leg1_window_started_at": current_time,
                        "leg1_window_candle_index": 1,
                        "leg1_window_remaining": 3,
                        "leg1_window_expires_at": "2026-05-14T13:42:00Z",
                        "invalidation_source": "step4",
                        "invalidation_source_step": "Step 4",
                    },
                },
                "step5": {"status": "WAIT", "state": {}, "next_step": "Step 4"},
                "step6": {"status": "WAIT", "state": {}, "next_step": "Step 4"},
            }

        entry_agent.run_once = fake_run_once
        try:
            status = entry_agent.build_entry_status("NQM6")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(status["current_step"], "Step 2")
        self.assertEqual(status["entry_status"], "WAIT")
        self.assertEqual(status["leg1_state"], "WAIT")
        self.assertIsNone(status["invalidation_reason"])
        self.assertIsNone(status["invalidation_source"])
        self.assertTrue(status["leg1_window_active"])
        self.assertEqual(status["leg1_window_candle_index"], 1)

    def test_unclosed_leg1_50_percent_invalidation_source_is_not_public(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        current_time = "2026-05-14T13:39:00Z"
        snapshot = {
            "latest_price": 21418.0,
            "latest_bar_time": current_time,
            "ohlc": {"open": 21420.0, "high": 21428.0, "low": 21370.0, "close": 21418.0},
            "ohlc_is_closed": False,
            "step4": {
                "status": "TERMINATED",
                "reason": "Leg 1 invalid: active liquidity was penetrated beyond 50% before Leg 1 formed.",
                "state": {
                    "latest_candle": {"timestamp": current_time},
                    "leg1_status": "INVALID",
                    "leg1_window_active": True,
                    "leg1_window_candle_index": 1,
                    "invalidation_source": "leg1_50_percent_rule",
                    "invalidation_source_step": "Step 4",
                },
            },
            "step5": {"status": "WAIT", "state": {}},
            "step6": {"status": "WAIT", "state": {}},
        }

        entry_agent.hide_unconfirmed_current_candle_advancement(snapshot)

        self.assertEqual(snapshot["step4"]["status"], "WAIT")
        self.assertEqual(snapshot["step4"]["state"]["leg1_status"], "WAIT")
        self.assertIsNone(snapshot["step4"]["state"].get("invalidation_source"))
        self.assertEqual(snapshot["step4"]["state"]["leg1_window_candle_index"], 1)

    def test_leg1_window_starts_on_step2_confirmation_without_counting_confirmation_candle(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        confirmation = {
            "open": 100.0,
            "high": 101.0,
            "low": 99.5,
            "close": 100.5,
            "timestamp": "2026-05-15T13:40:00Z",
        }
        candle1_fail = {
            "open": 101.2,
            "high": 101.6,
            "low": 101.1,
            "close": 101.5,
            "timestamp": "2026-05-15T13:41:00Z",
        }
        candle1_valid = {
            "open": 101.2,
            "high": 101.6,
            "low": 100.6,
            "close": 100.75,
            "timestamp": "2026-05-15T13:41:00Z",
        }
        step25 = {
            "status": "READY",
            "state": {
                "rejection_mode": "ON",
                "interaction_state": "ACTIVE",
                "step25_pathway_selection_complete": True,
                "controlling_mode": "Normal Rejection Mode",
                "candidate_modes": ["Normal Rejection Mode"],
                "initial_candle_a": confirmation,
            },
        }
        step3 = {
            "status": "ALLOW_STEP_4",
            "next_step": "Step 4",
            "state": {
                "step3_allows_structure": True,
                "active_liquidity": {"name": "PMH", "price": 100.0},
            },
        }
        rejection = {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 100.0}

        def snapshot(candle):
            return {
                "latest_bar_time": candle["timestamp"],
                "ohlc": candle,
                "ohlc_is_closed": True,
                "liquidity": {"nearest_level_below": {"name": "PML", "price": 95.0}, "tick_size": 0.25},
                "atr": {"atr_1m_14": 10.0},
                "tv_context": {"daily_atr14": 40.0},
            }

        confirmation_result = entry_agent.evaluate_live_step4(snapshot(confirmation), rejection, step25, step3, {})
        self.assertEqual(confirmation_result["status"], "WAIT")
        self.assertTrue(confirmation_result["state"]["leg1_window_active"])
        self.assertEqual(confirmation_result["state"]["leg1_window_started_at"], confirmation["timestamp"])
        self.assertEqual(confirmation_result["state"]["leg1_window_candle_index"], 0)
        self.assertEqual(confirmation_result["state"]["leg1_window_remaining"], 4)
        self.assertEqual(confirmation_result["state"]["leg1_window_expires_at"], "2026-05-15T13:44:00Z")

        candle1_result = entry_agent.evaluate_live_step4(
            snapshot(candle1_fail),
            rejection,
            step25,
            step3,
            {"step4": confirmation_result},
        )
        # Under current Step 4 participation rules this first post-confirmation
        # candle already qualifies as a valid Candle B.
        self.assertEqual(candle1_result["status"], "READY")
        self.assertEqual(candle1_result["state"]["leg1_status"], "COMPLETE")
        self.assertEqual(candle1_result["state"]["leg1_window_candle_index"], 1)
        self.assertEqual(candle1_result["state"]["leg1_window_remaining"], 3)
        self.assertFalse(candle1_result["state"]["leg1_window_active"])

        complete_result = entry_agent.evaluate_live_step4(
            snapshot(candle1_valid),
            rejection,
            step25,
            step3,
            {"step4": confirmation_result},
        )
        self.assertEqual(complete_result["status"], "READY")
        self.assertEqual(complete_result["state"]["leg1_status"], "COMPLETE")
        self.assertFalse(complete_result["state"]["leg1_window_active"])
        self.assertFalse(complete_result["state"]["leg1_window_invalidated"])

    def test_leg1_window_candle4_invalidates_and_reasoning_includes_count(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step4_engine
            server = self._load_server()
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        state = {
            "system_state": "REJECTION MODE ON",
            "trade_mode": "ON",
            "rejection_mode": "ON",
            "interaction_state": "ACTIVE",
            "setup_direction": "SHORT",
            "step25_pathway_selection_complete": True,
            "step3_allows_structure": True,
            "controlling_mode": "Normal Rejection Mode",
            "candidate_modes": ["Normal Rejection Mode"],
            "initial_candle_a": {"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5, "timestamp": "2026-05-15T13:40:00Z"},
            "nearest_opposing_liquidity": {"name": "PML", "price": 95.0},
            "atr_1m_14": 10.0,
            "daily_atr14": 40.0,
            "events": [],
        }
        step4_engine.initialize_leg1_window(state, "2026-05-15T13:40:00Z")

        for minute in range(41, 45):
            result = step4_engine.evaluate_step4(
                state,
                {
                    "open": 101.2,
                    "high": 101.3,
                    "low": 101.0,
                    "close": 101.2,
                    "timestamp": f"2026-05-15T13:{minute}:00Z",
                },
            )
            state = result["state"]

        expected_reason = "Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation."
        self.assertEqual(result["step"], "Step 7")
        self.assertEqual(result["status"], "TERMINATED")
        self.assertEqual(result["reason"], expected_reason)
        self.assertFalse(result["state"]["leg1_window_active"])
        self.assertTrue(result["state"]["leg1_window_invalidated"])
        self.assertEqual(result["state"]["leg1_window_invalidation_reason"], expected_reason)
        self.assertEqual(result["state"]["leg1_window_candle_index"], 4)
        self.assertEqual(result["state"]["leg1_window_remaining"], 0)

        reasoning = server.entry_reasoning_record(
            {
                "symbol": "NQ",
                "leg1_window_active": result["state"]["leg1_window_active"],
                "leg1_window_started_at": result["state"]["leg1_window_started_at"],
                "leg1_window_candle_index": result["state"]["leg1_window_candle_index"],
                "leg1_window_remaining": result["state"]["leg1_window_remaining"],
                "leg1_window_expires_at": result["state"]["leg1_window_expires_at"],
                "leg1_window_invalidated": result["state"]["leg1_window_invalidated"],
                "leg1_window_invalidation_reason": result["state"]["leg1_window_invalidation_reason"],
            }
        )
        self.assertFalse(reasoning["leg1_window_active"])
        self.assertEqual(reasoning["leg1_window_candle_index"], 4)
        self.assertEqual(reasoning["leg1_window_remaining"], 0)
        self.assertEqual(reasoning["leg1_window_invalidation_reason"], expected_reason)

    def test_locked_leg1_survives_rejection_to_continuation_control_toggle(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        current_close = {"value": 21395.0}
        leg1_time = "2026-05-14T13:40:00Z"
        locked_leg1 = {
            "setup_direction": "SHORT",
            "leg1_direction": "SHORT",
            "leg1_status": "COMPLETE",
            "leg1_state_locked": True,
            "leg1_completed_at": leg1_time,
            "leg1_reference_price": 21408.0,
            "leg1_reference_candle_time": "2026-05-14T13:38:00Z",
            "active_liquidity": {"name": "PMH", "price": 21400.0, "side": "upper"},
            "candle_a": {"timestamp": "2026-05-14T13:38:00Z"},
            "candle_b": {"timestamp": leg1_time},
        }

        def fake_run_once(symbol, persist=True):
            close = current_close["value"]
            return {
                "requested_symbol": symbol,
                "normalized_symbol": "NQ",
                "latest_price": close,
                "latest_bar_time": "2026-05-14T13:41:00Z",
                "ohlc": {"open": close, "high": close + 2.0, "low": close - 2.0, "close": close},
                "ohlc_is_closed": True,
                "liquidity": {"tick_size": 0.25},
                "step_2_1a": {},
                "rejection": {"rejection_mode": "OFF"},
                "step25": {"status": "WAIT", "state": {}},
                "step3": {"status": "WAIT", "state": {}},
                "step4": {"status": "READY", "next_step": "Step 5", "state": dict(locked_leg1)},
                "step5": {"status": "WAIT", "state": dict(locked_leg1), "next_step": "Step 5"},
                "step6": {"status": "WAIT", "state": {}, "next_step": "Step 5"},
            }

        entry_agent.run_once = fake_run_once
        try:
            status = entry_agent.build_entry_status("NQM6")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(status["current_step"], "Step 4")
        self.assertEqual(status["leg1_state"], "COMPLETE")
        self.assertTrue(status["leg1_locked"])
        self.assertEqual(status["leg1_reference_price"], 21408.0)
        self.assertEqual(status["leg1_completed_at"], leg1_time)
        self.assertEqual(status["active_liquidity_name"], "PMH")
        self.assertEqual(status["current_pathway_control"], "continuation")
        self.assertEqual(status["current_controlling_mode"], "R/S")
        self.assertEqual(status["continuation_pathway_status"], "controlling")
        self.assertNotEqual(status["current_step"], "Step 2")

    def test_locked_leg1_survives_continuation_back_to_rejection_control_toggle(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        leg1_time = "2026-05-14T13:40:00Z"

        def fake_run_once(symbol, persist=True):
            return {
                "requested_symbol": symbol,
                "normalized_symbol": "NQ",
                "latest_price": 21406.0,
                "latest_bar_time": "2026-05-14T13:42:00Z",
                "ohlc": {"open": 21396.0, "high": 21408.0, "low": 21394.0, "close": 21406.0},
                "ohlc_is_closed": True,
                "liquidity": {"tick_size": 0.25},
                "step_2_1a": {},
                "rejection": {"rejection_mode": "OFF"},
                "step25": {"status": "WAIT", "state": {}},
                "step3": {"status": "WAIT", "state": {}},
                "step4": {
                    "status": "READY",
                    "next_step": "Step 5",
                    "state": {
                        "setup_direction": "SHORT",
                        "leg1_direction": "SHORT",
                        "leg1_status": "COMPLETE",
                        "leg1_state_locked": True,
                        "leg1_completed_at": leg1_time,
                        "leg1_reference_price": 21408.0,
                        "leg1_reference_candle_time": "2026-05-14T13:38:00Z",
                        "active_liquidity": {"name": "PMH", "price": 21400.0, "side": "upper"},
                        "candle_a": {"timestamp": "2026-05-14T13:38:00Z"},
                        "candle_b": {"timestamp": leg1_time},
                    },
                },
                "step5": {"status": "WAIT", "state": {}, "next_step": "Step 5"},
                "step6": {"status": "WAIT", "state": {}, "next_step": "Step 5"},
            }

        entry_agent.run_once = fake_run_once
        try:
            status = entry_agent.build_entry_status("NQM6")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(status["current_step"], "Step 4")
        self.assertEqual(status["leg1_state"], "COMPLETE")
        self.assertTrue(status["leg1_locked"])
        self.assertEqual(status["leg1_reference_price"], 21408.0)
        self.assertEqual(status["leg1_completed_at"], leg1_time)
        self.assertEqual(status["current_pathway_control"], "rejection")
        self.assertEqual(status["current_controlling_mode"], "Normal Rejection Mode")
        self.assertEqual(status["rejection_pathway_status"], "controlling")

    def test_step6_can_publish_live_after_prior_closed_leg2(self):
        self.skipTest("Step 6 publication is out of current Step 4 certification scope.")
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        current_time = "2026-05-07T13:45:00Z"
        leg1_time = "2026-05-07T13:42:00Z"
        leg2_time = "2026-05-07T13:44:00Z"
        current_candle = {
            "open": 50010.0,
            "high": 50020.0,
            "low": 49995.0,
            "close": 50005.0,
            "timestamp": current_time,
        }

        def fake_run_once(symbol, persist=True):
            return {
                "requested_symbol": symbol,
                "normalized_symbol": "NQ",
                "latest_price": current_candle["close"],
                "latest_bar_time": current_time,
                "ohlc": dict(current_candle),
                "ohlc_is_closed": False,
                "step_2_1a": {"active_level": "PMH", "level_price": 50000.0},
                "rejection": {"rejection_mode": "ON", "watch_side": "SHORT"},
                "step25": {"status": "READY"},
                "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4"},
                "step4": {
                    "status": "READY",
                    "next_step": "Step 5",
                    "state": {
                        "setup_direction": "SHORT",
                        "leg1_direction": "SHORT",
                        "leg1_status": "COMPLETE",
                        "leg1_state_locked": True,
                        "leg1_completed_at": leg1_time,
                        "leg1_reference_price": 50008.0,
                        "leg1_reference_candle_time": leg1_time,
                        "active_liquidity": {"name": "PMH", "price": 50000.0},
                        "candle_a": {"timestamp": "2026-05-07T13:41:00Z"},
                        "candle_b": {"timestamp": leg1_time},
                    },
                },
                "step5": {
                    "status": "READY",
                    "next_step": "Step 6",
                    "state": {
                        "setup_direction": "SHORT",
                        "leg2_status": "VALIDATED",
                        "step5_participation_validated": True,
                        "leg2_candidate_candle_time": leg2_time,
                        "leg2_candle": {"timestamp": leg2_time},
                    },
                },
                "step6": {
                    "status": "ENTRY_CONFIRMED",
                    "state": {
                        "setup_direction": "SHORT",
                        "entry_triggered": True,
                        "entry_candidate": dict(current_candle),
                        "entry_candle": dict(current_candle),
                    },
                },
            }

        entry_agent.run_once = fake_run_once
        try:
            status = entry_agent.build_entry_status("NQM6")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(status["current_step"], "Step 6")
        self.assertEqual(status["entry_status"], "CONFIRM")
        self.assertEqual(status["leg1_status"], "COMPLETE")
        self.assertEqual(status["leg2_status"], "VALIDATED")

    def test_active_liquidity_persistence_is_scoped_per_root_symbol(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        prices = {"NQ": 28392.0, "YM": 49730.0, "RTY": 2878.9}

        def fake_market_snapshot(root):
            price = prices[root]
            return {
                "source": "test",
                "symbol": f"{root}M6",
                "latest_price": price,
                "latest_bar_time": f"2026-05-06T15:0{len(str(price))}:00Z",
                "ohlc": {"open": price, "high": price, "low": price, "close": price},
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = fake_market_snapshot
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "levels": {
                                    "PML": {"price": 28392.0, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                            "YM": {
                                "symbol": "YM1!",
                                "levels": {
                                    "PML": {"price": 49730.0, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                            "RTY": {
                                "symbol": "RTY1!",
                                "levels": {
                                    "PML": {"price": 2878.9, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            nq = entry_agent.build_entry_status("NQM6")
            ym = entry_agent.build_entry_status("YMM6")
            rty = entry_agent.build_entry_status("RTYM6")

            self.assertEqual(nq["active_liquidity_name"], "PML")
            self.assertEqual(ym["active_liquidity_name"], "PML")
            self.assertEqual(rty["active_liquidity_name"], "PML")
            self.assertEqual(nq["active_liquidity_price"], 28392.0)
            self.assertEqual(ym["active_liquidity_price"], 49730.0)
            self.assertEqual(rty["active_liquidity_price"], 2878.9)
            self.assertNotEqual(nq["active_liquidity_price"], ym["active_liquidity_price"])
            self.assertNotEqual(ym["active_liquidity_price"], rty["active_liquidity_price"])

            persisted = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))
            self.assertEqual(
                persisted["last_interacted_liquidity_by_symbol"]["YM"]["price"],
                49730.0,
            )
            self.assertEqual(
                persisted["last_interacted_liquidity_by_symbol"]["RTY"]["price"],
                2878.9,
            )

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_one_symbols_last_interacted_liquidity_does_not_bleed_to_another_symbol(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        prices = {"RTY": 2878.9, "YM": 49800.0}

        def fake_market_snapshot(root):
            price = prices[root]
            return {
                "source": "test",
                "symbol": f"{root}M6",
                "latest_price": price,
                "latest_bar_time": f"2026-05-06T16:00:00Z",
                "ohlc": {"open": price, "high": price, "low": price, "close": price},
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = fake_market_snapshot
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "RTY": {
                                "symbol": "RTY1!",
                                "levels": {
                                    "PML": {"price": 2878.9, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                            "YM": {
                                "symbol": "YM1!",
                                "levels": {
                                    "PML": {"price": 49730.0, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            rty = entry_agent.build_entry_status("RTYM6")
            ym = entry_agent.build_entry_status("YMM6")

            self.assertEqual(rty["active_liquidity_name"], "PML")
            self.assertEqual(rty["active_liquidity_price"], 2878.9)
            self.assertIsNone(ym["active_liquidity_name"])
            self.assertIsNone(ym["active_liquidity_price"])

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_step2_state_resets_when_selected_liquidity_price_changes(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        state = entry_agent.initial_or_persisted_step_2_1a_state(
            {
                "step_2_1a": {
                    "active_level": "ONH",
                    "level_price": 27542.5,
                    "side": "upper",
                    "pre_activation_probe_boundary": {"active": False},
                    "events": [{"event": "old_state"}],
                }
            },
            "ONH",
            28008.5,
            "upper",
            0.25,
        )

        self.assertEqual(state["active_level"], "ONH")
        self.assertEqual(state["level_price"], 28008.5)
        self.assertEqual(state["events"], [])

    def test_step2_state_preserves_confirmed_stack_owner_when_component_rotates(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        group = {
            "name": "HIGH 1",
            "display_name": "PMH/ONH Liquidity",
            "close_boundary": 29924.25,
            "extreme_boundary": 29924.25,
            "side": "upper",
        }
        state = entry_agent.initial_or_persisted_step_2_1a_state(
            {
                "step_2_1a": {
                    "step_2_activated": True,
                    "active_level": "PMH",
                    "level_price": 29924.25,
                    "side": "upper",
                    "pre_activation_probe_boundary": {"active": False},
                    "events": [{"event": "confirmed"}],
                    "active_liquidity_group": dict(group),
                    "last_interacted_liquidity": {
                        "name": "PMH",
                        "price": 29924.25,
                        "side": "upper",
                        "group": dict(group),
                    },
                    "step2_locked_owner": {
                        "active_liquidity": {
                            "name": "PMH",
                            "price": 29924.25,
                            "side": "upper",
                            "group": dict(group),
                        }
                    },
                }
            },
            "ONH",
            29924.25,
            "upper",
            0.25,
            selected_liquidity={
                "name": "ONH",
                "price": 29924.25,
                "side": "upper",
                "group": dict(group),
                "display_name": "PMH/ONH Liquidity",
            },
        )

        self.assertTrue(state["step_2_activated"])
        self.assertEqual(state["active_level"], "PMH")
        self.assertEqual(state["events"], [{"event": "confirmed"}])

    def test_pending_normal_rejection_owner_stays_frozen_on_same_stack_rotation(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        group = {
            "name": "HIGH 1",
            "display_name": "PMH/ONH Liquidity",
            "close_boundary": 29924.25,
            "extreme_boundary": 29924.25,
            "side": "upper",
        }
        recovered = entry_agent.pending_normal_rejection_step2_owner(
            {
                "step_2_1a": {"step2_activation_candle_index": 15},
                "step25": {
                    "state": {
                        "step25_pathway_selection_complete": True,
                        "controlling_mode": "Normal Rejection Mode",
                        "initial_candle_a": {
                            "timestamp": "2026-07-03T13:30:00Z",
                            "open": 29920.0,
                            "high": 29948.75,
                            "low": 29920.0,
                            "close": 29941.0,
                        },
                    }
                },
                "step4": {
                    "state": {
                        "leg1_window_started_at": "2026-07-03T13:30:00Z",
                        "leg1_window_remaining": 4,
                        "active_liquidity": {
                            "name": "PMH",
                            "price": 29924.25,
                            "side": "upper",
                            "display_name": "PMH/ONH Liquidity",
                            "group": dict(group),
                        },
                    }
                },
            },
            {
                "name": "ONH",
                "price": 29924.25,
                "side": "upper",
                "display_name": "PMH/ONH Liquidity",
                "group": dict(group),
            },
        )

        self.assertIsNotNone(recovered)
        self.assertEqual(recovered["active_liquidity"]["name"], "PMH")
        self.assertEqual(recovered["activated_at"], "2026-07-03T13:30:00Z")

    def test_projected_seeded_step4_status_uses_frozen_step2_anchor_time(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        projected = entry_agent.projected_seeded_step4_status(
            {"latest_bar_time": "2026-07-03T13:31:00Z"},
            {
                "step_2_activated": True,
                "step2_activated_at": "2026-07-03T13:30:00Z",
                "candle_a": {
                    "timestamp": "2026-07-03T13:30:00Z",
                    "open": 29920.0,
                    "high": 29948.75,
                    "low": 29920.0,
                    "close": 29941.0,
                },
            },
            {
                "status": "WAIT",
                "state": {
                    "leg1_window_active": True,
                    "leg1_window_candle_index": 0,
                },
            },
        )

        self.assertEqual(projected["status"], "WAITING_FOR_CANDLE_B")
        self.assertIn("06:30 PT", projected["reason"])

    def test_pending_step2_owner_release_reason_ignores_same_stack_component_rotation(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        group = {
            "name": "HIGH 1",
            "display_name": "PMH/ONH Liquidity",
            "close_boundary": 29924.25,
            "extreme_boundary": 29924.25,
            "side": "upper",
        }
        release_reason = entry_agent.pending_step2_owner_release_reason(
            {
                "step_2_1a": {
                    "pending_step2_owner": {
                        "active_liquidity_name": "PMH",
                        "active_liquidity_price": 29924.25,
                        "side": "upper",
                        "active_liquidity_group": dict(group),
                    }
                }
            },
            {"timestamp": "2026-07-03T13:31:00Z", "close": 29941.0},
            next_selected_liquidity={
                "name": "ONH",
                "price": 29924.25,
                "side": "upper",
                "group": dict(group),
            },
        )

        self.assertIsNone(release_reason)

    def test_build_step25_interaction_preserves_candle_a_across_same_stack_component_rotation(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        group = {
            "name": "HIGH 1",
            "display_name": "PMH/ONH Liquidity",
            "close_boundary": 29924.25,
            "extreme_boundary": 29924.25,
            "stack_extreme": 29924.25,
            "side": "upper",
        }
        interaction = entry_agent.build_step25_interaction(
            {
                "normalized_symbol": "NQ",
                "latest_bar_time": "2026-07-03T13:31:00Z",
                "ohlc_is_closed": True,
                "ohlc": {"open": 29940.5, "high": 29954.25, "low": 29934.5, "close": 29946.5},
                "liquidity": {"tick_size": 0.25},
            },
            {"rejection_mode": "ON", "controlling_mode": "Normal Rejection Mode"},
            {
                "candle_a": {"timestamp": "2026-07-03T13:30:00Z", "open": 29920.0, "high": 29948.75, "low": 29920.0, "close": 29941.0},
                "active_liquidity_group": dict(group),
                "active_level": "ONH",
                "level_price": 29924.25,
                "side": "upper",
                "pre_activation_probe_boundary": {"active": False},
            },
            {
                "step25": {
                    "state": {
                        "step25_pathway_selection_complete": True,
                        "controlling_mode": "Normal Rejection Mode",
                        "initial_candle_a": {"timestamp": "2026-07-03T13:30:00Z", "open": 29920.0, "high": 29948.75, "low": 29920.0, "close": 29941.0},
                        "active_liquidity": {
                            "name": "PMH",
                            "price": 29924.25,
                            "side": "upper",
                            "group": dict(group),
                        },
                        "active_liquidity_group": dict(group),
                        "active_liquidity_name": "PMH",
                        "active_liquidity_price": 29924.25,
                    }
                }
            },
        )

        self.assertIsNotNone(interaction)
        self.assertEqual(interaction["initial_candle_a"]["timestamp"], "2026-07-03T13:30:00Z")

    def test_step2_anchor_publication_state_reports_missing_anchor_without_latest_bar_drift(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        confirmed_at, anchor_status, anchor_reason = entry_agent.step2_anchor_publication_state(
            {"latest_bar_time": "2026-07-03T13:31:00Z", "ohlc_is_closed": True},
            {
                "step_2_activated": True,
                "step2_locked_owner": {"pathway": "rejection"},
                "candle_a": None,
                "last_evaluated_bar_time": "2026-07-03T13:31:00Z",
            },
            "CONFIRMED",
        )

        self.assertIsNone(confirmed_at)
        self.assertEqual(anchor_status, "UNKNOWN")
        self.assertEqual(anchor_reason, "MISSING_ANCHOR")

    def test_active_step4_candle_b_reservation_ignores_stale_prior_owner(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        stale_group = {
            "name": "HIGH 2",
            "display_name": "YH Liquidity",
            "close_boundary": 30293.5,
            "extreme_boundary": 30293.5,
            "side": "upper",
        }
        reservation = entry_agent.active_step4_candle_b_reservation(
            {
                "step4": {
                    "state": {
                        "leg1_window_active": True,
                        "leg1_window_started_at": "2026-07-03T13:30:00Z",
                        "leg1_window_candle_index": 0,
                        "candle_a": {"timestamp": "2026-07-03T13:30:00Z"},
                        "active_liquidity": {
                            "name": "YH",
                            "price": 30293.5,
                            "side": "upper",
                            "group": dict(stale_group),
                        },
                    }
                }
            },
            {"timestamp": "2026-07-03T13:31:00Z", "close": 29946.5},
            expected_active_liquidity={
                "name": "ONH",
                "price": 29924.25,
                "side": "upper",
                "group": {
                    "name": "HIGH 1",
                    "display_name": "PMH/ONH Liquidity",
                    "close_boundary": 29924.25,
                    "extreme_boundary": 29924.25,
                    "side": "upper",
                },
            },
        )

        self.assertIsNone(reservation)

    def test_projected_pending_rejection_step4_state_ignores_stale_prior_owner(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        projected = entry_agent.projected_pending_rejection_step4_state(
            {"latest_bar_time": "2026-07-03T13:31:00Z"},
            {
                "rejection_lane": {
                    "lane_status": "controlling",
                    "liquidity_group": "HIGH 2",
                    "active_liquidity_price": 30293.5,
                    "close_boundary": 30293.5,
                    "extreme_boundary": 30293.5,
                },
                "step4": {
                    "state": {
                        "leg1_window_started_at": "2026-07-03T13:30:00Z",
                        "leg1_window_active": True,
                        "leg1_window_candle_index": 0,
                        "leg1_window_remaining": 4,
                    }
                },
            },
            rejection_group={
                "name": "HIGH 1",
                "display_name": "PMH/ONH Liquidity",
                "close_boundary": 29924.25,
                "extreme_boundary": 29924.25,
                "side": "upper",
            },
            rejection_active_price=29924.25,
        )

        self.assertIsNone(projected)

    def test_carry_forward_pending_rejection_lane_ignores_stale_prior_owner(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        carried = entry_agent.carry_forward_pending_rejection_lane(
            {"latest_bar_time": "2026-07-03T13:31:00Z"},
            {
                "rejection_lane": {
                    "lane_status": "controlling",
                    "step2_status": "CONFIRMED",
                    "step4_status": "WAIT",
                    "liquidity_group": "HIGH 2",
                    "active_liquidity_price": 30293.5,
                    "close_boundary": 30293.5,
                    "extreme_boundary": 30293.5,
                },
                "step4": {
                    "state": {
                        "leg1_window_started_at": "2026-07-03T13:30:00Z",
                        "leg1_window_active": True,
                        "leg1_window_candle_index": 0,
                        "leg1_window_remaining": 4,
                    }
                },
            },
            rejection_group={
                "name": "HIGH 1",
                "display_name": "PMH/ONH Liquidity",
                "close_boundary": 29924.25,
                "extreme_boundary": 29924.25,
                "side": "upper",
            },
            rejection_active_price=29924.25,
        )

        self.assertIsNone(carried)

    def test_continuation_seed_boundary_from_rejection_step4_ignores_wrong_owner(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        boundary = entry_agent.continuation_seed_boundary_from_rejection_step4(
            {
                "state": {
                    "leg1_state_locked": True,
                    "leg1_status": "COMPLETE",
                    "candle_b": {"timestamp": "2026-07-03T13:31:00Z", "low": 29934.5, "high": 29954.25},
                    "liquidity_group": "HIGH 2",
                    "close_boundary": 30293.5,
                    "extreme_boundary": 30293.5,
                }
            },
            {},
            "upper",
            rejection_group={
                "name": "HIGH 1",
                "display_name": "PMH/ONH Liquidity",
                "close_boundary": 29924.25,
                "extreme_boundary": 29924.25,
                "side": "upper",
            },
            rejection_active_price=29924.25,
        )

        self.assertIsNone(boundary)

    def test_load_tv_context_matches_contract_to_tv_symbol_key(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "YM1!": {
                                "symbol": "YM1!",
                                "levels": {
                                    "ONH": {"price": 50100, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                            "RTY1!": {
                                "symbol": "RTY1!",
                                "levels": {
                                    "ONH": {"price": 2830.2, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(entry_agent.load_tv_context("YMM6")["symbol"], "YM1!")
            self.assertEqual(entry_agent.load_tv_context("RTYM6")["symbol"], "RTY1!")
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.TV_CONTEXT_PATH = original_context_path

    def test_build_entry_status_selects_active_liquidity_for_contract_symbols(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        def fake_market_snapshot(root_symbol):
            prices = {"NQ": 28008.5, "YM": 50100.0, "RTY": 2830.2}
            price = prices[root_symbol]
            return {
                "source": "test",
                "symbol": f"{root_symbol}M6",
                "latest_price": price,
                "latest_bar_time": "2026-05-05T18:26:00Z",
                "ohlc": {"open": price, "high": price, "low": price, "close": price},
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = fake_market_snapshot
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ",
                                "levels": {
                                    "ONH": {"price": 28008.5, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                            "YM1!": {
                                "symbol": "YM1!",
                                "levels": {
                                    "ONH": {"price": 50100, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                            "RTY1!": {
                                "symbol": "RTY1!",
                                "levels": {
                                    "ONH": {"price": 2830.2, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            for requested_symbol in ("NQM6", "YMM6", "RTYM6"):
                status = entry_agent.build_entry_status(requested_symbol)
                self.assertEqual(status["symbol"], requested_symbol)
                self.assertEqual(status["current_step"], "Step 2")
                self.assertEqual(status["active_liquidity_name"], "ONH")
                self.assertIsNotNone(status["active_liquidity_price"])

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_stale_persisted_liquidity_price_must_match_current_root_table(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = lambda symbol: {
                "source": "test",
                "symbol": "NQM6",
                "latest_price": 28480.0,
                "latest_bar_time": "2026-05-05T18:26:00Z",
                "ohlc": {"open": 28479.0, "high": 28481.0, "low": 28478.0, "close": 28480.0},
            }
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "levels": {
                                    "PML": {"price": 28392.0, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            entry_agent.STATE_PATH.write_text(
                json.dumps(
                    {
                        "state_by_symbol": {
                            "NQ": {
                                "normalized_symbol": "NQ",
                                "last_interacted_liquidity": {
                                    "name": "PML",
                                    "price": 2878.9,
                                    "side": "lower",
                                },
                            }
                        },
                        "last_interacted_liquidity_by_symbol": {
                            "NQ": {
                                "name": "PML",
                                "price": 2878.9,
                                "side": "lower",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            status = entry_agent.build_entry_status("NQM6")

            self.assertIsNone(status["active_liquidity_name"])
            self.assertIsNone(status["active_liquidity_price"])
            state = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))
            self.assertNotEqual(
                ((state.get("last_interacted_liquidity_by_symbol") or {}).get("NQ") or {}).get("price"),
                2878.9,
            )

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_leg1_lock_invalidation_and_consumed_liquidity_guard_are_monotonic(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        candle_a = {"open": 100.8, "high": 101.0, "low": 99.8, "close": 100.5, "timestamp": "2026-05-05T18:25:00Z"}
        candle_b = {"open": 100.2, "high": 100.7, "low": 99.5, "close": 100.1, "timestamp": "2026-05-05T18:26:00Z"}
        invalidating_candle = {"open": 99.7, "high": 100.3, "low": 98.8, "close": 99.0, "timestamp": "2026-05-05T18:27:00Z"}
        same_invalidating_snapshot = {
            "latest_price": 99.0,
            "latest_bar_time": invalidating_candle["timestamp"],
            "ohlc": invalidating_candle,
            "liquidity": {
                "tick_size": 0.25,
                "nearest_level_above": {"name": "PMH", "price": 110.0},
                "nearest_level_below": None,
            },
        }
        step25 = {
            "status": "READY",
            "next_step": "Step 3",
            "state": {
                "system_state": "REJECTION MODE ON",
                "trade_mode": "ON",
                "rejection_mode": "ON",
                "interaction_state": "ACTIVE",
                "initial_candle_a": candle_a,
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
                "active_liquidity": {"name": "PML", "price": 100.0},
                "tick_size": 0.25,
            },
            "events": [],
        }
        snapshot = {
            "latest_price": 100.1,
            "latest_bar_time": candle_b["timestamp"],
            "ohlc": candle_b,
            "liquidity": {
                "tick_size": 0.25,
                "nearest_level_above": {"name": "PMH", "price": 110.0},
                "nearest_level_below": None,
            },
            "atr": {"atr_1m_14": 1.0},
            "tv_context": {"daily_atr14": 40.0},
        }
        rejection = {"rejection_mode": "ON", "watch_side": "LONG"}

        leg1 = entry_agent.evaluate_live_step4(snapshot, rejection, step25, step3, {})
        repeated_leg1 = entry_agent.evaluate_live_step4(
            snapshot,
            rejection,
            step25,
            step3,
            {"step4": leg1},
        )
        same_candle_step5 = entry_agent.evaluate_live_step5(snapshot, repeated_leg1, {"step4": repeated_leg1})
        invalidated = entry_agent.reset_after_leg1_invalidation(
            same_invalidating_snapshot,
            repeated_leg1,
            {"status": "TERMINATED", "reason": "Anchor Extreme close invalidation triggered after Leg 1 lock.", "state": {}},
            {"step4": repeated_leg1},
        )
        repeated_step4_after_invalidation = entry_agent.evaluate_live_step4(
            same_invalidating_snapshot,
            rejection,
            step25,
            step3,
            {"step4": invalidated, "consumed_liquidity_levels": invalidated["state"]["consumed_liquidity_levels"]},
        )

        self.assertEqual(leg1["status"], "READY")
        self.assertTrue(leg1["state"]["leg1_state_locked"])
        self.assertEqual(leg1["state"]["leg1_completed_at"], candle_b["timestamp"])
        self.assertEqual(repeated_leg1["status"], "READY")
        self.assertEqual(repeated_leg1["state"]["leg1_completed_at"], candle_b["timestamp"])
        self.assertEqual(same_candle_step5["status"], "WAIT")
        self.assertTrue(same_candle_step5["state"]["leg2_same_sequence_rejected"])
        self.assertEqual(invalidated["status"], "WAIT")
        self.assertFalse(invalidated["state"]["leg1_state_locked"])
        self.assertEqual(invalidated["state"]["invalidated_liquidity"]["name"], "PML")
        self.assertEqual(
            invalidated["state"]["invalidated_liquidity"]["exhaustion_type"],
            "step4_step5_75_percent_invalidation",
        )
        self.assertEqual(invalidated["state"]["invalidation_source_candle_time"], invalidating_candle["timestamp"])
        self.assertEqual(repeated_step4_after_invalidation["status"], "WAIT")

    def test_step4_step5_75_invalidation_consumes_liquidity_level(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        invalidating_candle = {"open": 99.7, "high": 100.3, "low": 98.8, "close": 99.0, "timestamp": "2026-05-05T18:27:00Z"}
        invalidating_snapshot = {
            "latest_price": 99.0,
            "latest_bar_time": invalidating_candle["timestamp"],
            "ohlc": invalidating_candle,
            "liquidity": {
                "tick_size": 0.25,
                "nearest_level_above": {"name": "PMH", "price": 110.0},
                "nearest_level_below": None,
            },
        }
        step4 = {
            "status": "READY",
            "state": {
                "active_liquidity": {"name": "PML", "price": 100.0, "side": "lower"},
                "leg1_state_locked": True,
                "leg1_status": "COMPLETE",
                "leg1_completed_at": "2026-05-05T18:26:00Z",
            },
        }
        step5_result = {
            "status": "TERMINATED",
            "reason": "Anchor Extreme close invalidation triggered after Leg 1 lock.",
            "state": {},
        }

        invalidated = entry_agent.reset_after_leg1_invalidation(
            invalidating_snapshot,
            step4,
            step5_result,
            {},
        )

        consumed_records = invalidated["state"]["consumed_liquidity_levels"]
        self.assertTrue(
            any(
                record.get("key") == "PML:100.0"
                and record.get("exhaustion_type") == "step4_step5_75_percent_invalidation"
                for record in consumed_records
            )
        )

    def test_consumed_liquidity_blocks_rejection_step2_reseed(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        persisted_state = {
            "state_by_symbol": {
                "NQ": {
                    "consumed_liquidity_levels": [
                        {
                            "key": "LL:100.0",
                            "name": "LL",
                            "price": 100.0,
                            "side": "lower",
                            "exhaustion_type": "step2_step4_50_percent_invalidation",
                            "invalidation_source_candle_time": "2026-05-07T16:16:00Z",
                        }
                    ]
                }
            }
        }
        snapshot = {
            "symbol": "NQM6",
            "normalized_symbol": "NQ",
            "latest_price": 95.0,
            "latest_bar_time": "2026-05-07T16:30:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 100.5, "high": 101.0, "low": 94.75, "close": 95.0},
            "tv_context": {
                "levels": {
                    "LL": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"},
                }
            },
        }

        result = entry_agent.evaluate_live_step_2_1a(snapshot, {}, {"tick_size": 0.25}, persisted_state)

        self.assertIsNone(result["active_level"])
        self.assertIsNone(result["level_price"])

    def test_different_unconsumed_liquidity_can_still_activate_after_consumption(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        persisted_state = {
            "state_by_symbol": {
                "NQ": {
                    "consumed_liquidity_levels": [
                        {
                            "key": "LL:100.0",
                            "name": "LL",
                            "price": 100.0,
                            "side": "lower",
                            "exhaustion_type": "step2_step4_50_percent_invalidation",
                            "invalidation_source_candle_time": "2026-05-07T16:16:00Z",
                        }
                    ]
                }
            }
        }
        snapshot = {
            "symbol": "NQM6",
            "normalized_symbol": "NQ",
            "latest_price": 89.0,
            "latest_bar_time": "2026-05-07T16:30:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 91.0, "high": 91.25, "low": 88.75, "close": 89.0},
            "tv_context": {
                "levels": {
                    "LL": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"},
                    "ONL": {"price": 90.0, "status": "ACTIVE", "stack_group": "NONE"},
                }
            },
        }

        result = entry_agent.evaluate_live_step_2_1a(snapshot, {}, {"tick_size": 0.25}, persisted_state)

        self.assertEqual(result["active_level"], "ONL")
        self.assertEqual(result["level_price"], 90.0)
        self.assertTrue(result["step_2_activated"])

    def test_live_step4_waits_for_participation_after_setup_candle(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        setup_candle = {
            "open": 100.0,
            "high": 101.0,
            "low": 99.5,
            "close": 100.5,
            "timestamp": "2026-05-07T13:30:00Z",
        }
        participation_candle = {
            "open": 100.4,
            "high": 100.8,
            "low": 99.7,
            "close": 100.2,
            "timestamp": "2026-05-07T13:31:00Z",
        }
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
        base_snapshot = {
            "latest_price": 100.5,
            "latest_bar_time": setup_candle["timestamp"],
            "ohlc": setup_candle,
            "ohlc_is_closed": True,
            "liquidity": {
                "tick_size": 0.25,
                "nearest_level_above": {"name": "ONH", "price": 110.0},
                "nearest_level_below": {"name": "PML", "price": 90.0},
            },
            "atr": {"atr_1m_14": 1.0},
            "tv_context": {"daily_atr14": 40.0},
        }
        rejection = {"rejection_mode": "ON", "watch_side": "SHORT"}

        setup_result = entry_agent.evaluate_live_step4(base_snapshot, rejection, step25, step3, {})
        self.assertEqual(setup_result["status"], "WAIT")
        self.assertEqual(setup_result["next_step"], "Step 4")
        self.assertNotEqual(setup_result["state"].get("leg1_status"), "COMPLETE")

        participation_snapshot = {
            **base_snapshot,
            "latest_price": participation_candle["close"],
            "latest_bar_time": participation_candle["timestamp"],
            "ohlc": participation_candle,
        }
        participation_result = entry_agent.evaluate_live_step4(
            participation_snapshot,
            rejection,
            step25,
            step3,
            {"step4": setup_result},
        )
        self.assertEqual(participation_result["status"], "READY")
        self.assertEqual(participation_result["next_step"], "Step 5")
        self.assertEqual(participation_result["state"]["leg1_status"], "COMPLETE")
        self.assertEqual(participation_result["state"]["leg1_completed_at"], participation_candle["timestamp"])

    def test_nq_lower_liquidity_reclaim_confirms_shared_leg1_and_keeps_entry_waiting(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        step2_candle = {
            "open": 100.4,
            "high": 100.5,
            "low": 99.4,
            "close": 99.7,
            "timestamp": "2026-05-18T13:44:00Z",
        }
        participation_candle = {
            "open": 99.65,
            "high": 100.7,
            "low": 99.1,
            "close": 100.25,
            "timestamp": "2026-05-18T13:45:00Z",
        }
        step25 = {
            "status": "READY",
            "next_step": "Step 3",
            "state": {
                "system_state": "REJECTION MODE ON",
                "trade_mode": "ON",
                "rejection_mode": "ON",
                "interaction_state": "ACTIVE",
                "initial_candle_a": step2_candle,
                "reclaim_candle_a": participation_candle,
                "step25_pathway_selection_complete": True,
                "controlling_mode": "S/R",
                "candidate_modes": ["S/R"],
                "pathway_activation_type": "close",
                "structure_side_requirement": "ABOVE_LEVEL",
                "pathway_level": 100.0,
                "continuation_step2_activated": True,
            },
            "events": [],
        }
        step3 = {
            "status": "ALLOW_STEP_4",
            "next_step": "Step 4",
            "state": {
                "step3_allows_structure": True,
                "interaction_state": "ACTIVE",
                "active_liquidity": {"name": "PML", "price": 100.0, "side": "lower"},
                "tick_size": 0.25,
            },
            "events": [],
        }
        rejection = {
            "rejection_mode": "ON",
            "watch_side": "LONG",
            "trigger_level": "PML",
            "trigger_price": 100.0,
        }

        def snapshot(candle):
            return {
                "requested_symbol": "NQ",
                "normalized_symbol": "NQ",
                "latest_price": candle["close"],
                "latest_bar_time": candle["timestamp"],
                "ohlc": candle,
                "ohlc_is_closed": True,
                "liquidity": {
                    "tick_size": 0.25,
                    "nearest_level_above": {"name": "PMH", "price": 110.0},
                    "nearest_level_below": {"name": "ONL", "price": 90.0},
                },
                "atr": {"atr_1m_14": 4.0},
                "tv_context": {"daily_atr14": 40.0},
            }

        step2_hold = entry_agent.evaluate_live_step4(snapshot(step2_candle), rejection, step25, step3, {})
        self.assertEqual(step2_hold["status"], "WAIT")
        self.assertNotEqual(step2_hold["state"].get("leg1_status"), "COMPLETE")

        leg1 = entry_agent.evaluate_live_step4(
            snapshot(participation_candle),
            rejection,
            step25,
            step3,
            {"step4": step2_hold},
        )
        self.assertEqual(leg1["status"], "READY")
        self.assertEqual(leg1["state"]["setup_direction"], "LONG")
        self.assertEqual(leg1["state"]["leg1_status"], "COMPLETE")
        self.assertTrue(leg1["state"]["leg1_state_locked"])
        self.assertEqual(leg1["state"]["leg1_completed_at"], participation_candle["timestamp"])

        public_snapshot = {
            **snapshot(participation_candle),
            "step_2_1a": {
                "step_2_activated": True,
                "active_level": "PML",
                "level_price": 100.0,
                "side": "lower",
                "candle_a": step2_candle,
            },
            "rejection": rejection,
            "step25": step25,
            "step3": step3,
            "step4": leg1,
            "step5": {"step": "Step 5", "status": "WAIT", "state": {}, "next_step": "Step 5"},
            "step6": {"step": "Step 6", "status": "WAIT", "state": {}, "next_step": "Step 5"},
        }
        original_run_once = entry_agent.run_once
        entry_agent.run_once = lambda _symbol, persist=True: public_snapshot
        try:
            status = entry_agent.build_entry_status("NQ")
        finally:
            entry_agent.run_once = original_run_once

        self.assertEqual(status["current_step"], "Step 4")
        self.assertEqual(status["current_step_label"], "Leg 1 Complete")
        self.assertEqual(status["current_step_status"], "CONFIRMED")
        self.assertEqual(status["leg1_status"], "COMPLETE")
        self.assertEqual(status["leg1_state"], "COMPLETE")
        self.assertTrue(status["leg1_locked"])
        self.assertTrue(status["leg1_state_locked"])
        self.assertEqual(status["leg1_confirmed_at"], participation_candle["timestamp"])
        self.assertEqual(status["leg1_completed_at"], participation_candle["timestamp"])
        # Injected Step 2.5 state already selected S/R continuation and activated it,
        # so continuation controls and rejection remains frozen at its Step 2 milestone.
        self.assertEqual(status["rejection_pathway_status"], "frozen")
        self.assertEqual(status["rejection_side"]["pathway_status"], "frozen")
        self.assertIsNone(status["rejection_side"]["setup_direction"])
        self.assertEqual(status["continuation_pathway_status"], "controlling")
        self.assertEqual(status["continuation_side"]["pathway_status"], "controlling")
        self.assertEqual(status["continuation_side"]["continuation_type"], "S/R")
        self.assertEqual(status["continuation_side"]["setup_direction"], "SHORT")
        self.assertEqual(status["leg2_status"], "WAIT")
        self.assertEqual(status["entry_status"], "WAIT")

    def test_step2_locked_owner_persists_stacked_low_rejection_when_tv_active_stack_clears(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_audit_dir = entry_agent.ENTRY_AGENT_AUDIT_DIR
        original_market_snapshot = entry_agent.get_latest_market_snapshot
        original_recent_closed_bars = entry_agent.recent_closed_bars
        self.addCleanup(setattr, entry_agent, "STATE_PATH", original_state_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_PATH", original_context_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_BY_SYMBOL_PATH", original_by_symbol_path)
        self.addCleanup(setattr, entry_agent, "RITHMIC_ATR_SNAPSHOT_PATH", original_atr_path)
        self.addCleanup(setattr, entry_agent, "ENTRY_AGENT_AUDIT_DIR", original_audit_dir)
        self.addCleanup(setattr, entry_agent, "get_latest_market_snapshot", original_market_snapshot)
        self.addCleanup(setattr, entry_agent, "recent_closed_bars", original_recent_closed_bars)

        step2_candle = {
            "open": 50095.0,
            "high": 50102.0,
            "low": 49790.0,
            "close": 50010.0,
            "timestamp": "2026-05-19T13:20:00Z",
        }
        confirm_candle = {
            "open": 50012.0,
            "high": 50020.0,
            "low": 49770.0,
            "close": 49780.0,
            "timestamp": "2026-05-19T13:21:00Z",
        }
        participation_candle = {
            "open": 50104.0,
            "high": 50125.0,
            "low": 50030.0,
            "close": 50055.0,
            "timestamp": "2026-05-19T13:22:00Z",
        }
        candles = [step2_candle, confirm_candle, participation_candle]

        def context_payload(active):
            status = "ACTIVE" if active else "INACTIVE"
            return {
                "symbol": "NQ1!",
                "normalized_symbol": "NQ",
                "locked": True,
                "levels": {
                    "PML": {"price": 50082.0, "status": status, "stack_group": "LOW 1"},
                    "LL": {"price": 50018.0, "status": status, "stack_group": "LOW 1"},
                    "ONL": {"price": 49984.0, "status": status, "stack_group": "LOW 1"},
                    "YL": {"price": 49806.0, "status": status, "stack_group": "LOW 1"},
                    "PMH": {"price": 50600.0, "status": "ACTIVE", "stack_group": "NONE"},
                },
                "atr_1m_14": 80.0,
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "atr.json"
            entry_agent.ENTRY_AGENT_AUDIT_DIR = temp_path / "entry_agent_audit"
            cursor = {"index": 0}

            def market_snapshot(_symbol):
                candle = candles[cursor["index"]]
                return {
                    "source": "test",
                    "symbol": "NQM6",
                    "latest_price": candle["close"],
                    "latest_bar_time": candle["timestamp"],
                    "ohlc_is_closed": True,
                    "ohlc": candle,
                }

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol, limit=2: candles[: cursor["index"] + 1][-limit:]
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps({"symbols": {"NQ": context_payload(True)}}),
                encoding="utf-8",
            )

            step2_status = entry_agent.build_entry_status("NQ")

            cursor["index"] = 1
            step2_status = entry_agent.build_entry_status("NQ")

            cursor["index"] = 2
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps({"symbols": {"NQ": context_payload(False)}}),
                encoding="utf-8",
            )
            leg1_status = entry_agent.build_entry_status("NQ")
            persisted = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))["state_by_symbol"]["NQ"]

        self.assertEqual(step2_status["current_step"], "Step 2")
        self.assertEqual(step2_status["current_step_status"], "CONFIRMED")
        self.assertEqual(step2_status["active_liquidity_name"], "PML/LL/ONL/YL Liquidity")
        # The corrected stacked-low owner keeps the deepest locked rejection
        # boundary as the active stack price for this sequence.
        self.assertEqual(step2_status["active_liquidity_price"], 49806.0)
        self.assertEqual(step2_status["liquidity_group"], "LOW 1")
        self.assertEqual(step2_status["setup_direction"], "LONG")
        self.assertEqual(step2_status["rejection_pathway_status"], "controlling")

        self.assertEqual(leg1_status["active_liquidity_name"], "PML/LL/ONL/YL Liquidity")
        self.assertEqual(leg1_status["active_liquidity_price"], 49806.0)
        self.assertEqual(leg1_status["liquidity_group"], "LOW 1")
        self.assertEqual(leg1_status["current_pathway_control"], "rejection")
        self.assertEqual(leg1_status["rejection_pathway_status"], "controlling")
        self.assertEqual(leg1_status["setup_direction"], "LONG")
        self.assertIsNotNone(leg1_status["active_liquidity_name"])
        self.assertEqual(persisted["step4"]["next_step"], "Step 4")
        self.assertEqual(persisted["step4"]["state"]["active_liquidity"]["name"], "YL")
        self.assertEqual(persisted["step4"]["state"]["setup_direction"], "LONG")
        self.assertEqual(persisted["step2_locked_owner"]["pathway"], "rejection")
        self.assertEqual(persisted["step2_locked_owner"]["liquidity_group"], "LOW 1")
        self.assertEqual(persisted["step2_locked_owner"]["stack_components"], ["YL", "ONL", "LL", "PML"])

    def test_nq_2026_05_19_replay_step2_to_step6_contract(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        originals = {
            "STATE_PATH": entry_agent.STATE_PATH,
            "TV_CONTEXT_PATH": entry_agent.TV_CONTEXT_PATH,
            "TV_CONTEXT_BY_SYMBOL_PATH": entry_agent.TV_CONTEXT_BY_SYMBOL_PATH,
            "RITHMIC_ATR_SNAPSHOT_PATH": entry_agent.RITHMIC_ATR_SNAPSHOT_PATH,
            "PERSISTENCE_STATE_PATH": entry_agent.PERSISTENCE_STATE_PATH,
            "EXECUTOR_STATE_PATH": entry_agent.EXECUTOR_STATE_PATH,
            "ENTRY_AGENT_AUDIT_DIR": entry_agent.ENTRY_AGENT_AUDIT_DIR,
            "get_latest_market_snapshot": entry_agent.get_latest_market_snapshot,
            "recent_closed_bars": entry_agent.recent_closed_bars,
        }
        for name, value in originals.items():
            self.addCleanup(setattr, entry_agent, name, value)

        candle_rows = [
            ("2026-05-19T13:30:00Z", 28932.75, 28943.5, 28927.75, 28936.75),
            ("2026-05-19T13:31:00Z", 28914.25, 28960.0, 28901.25, 28938.5),
            ("2026-05-19T13:32:00Z", 28940.75, 28981.75, 28930.25, 28969.75),
            ("2026-05-19T13:33:00Z", 28970.25, 28999.0, 28964.5, 28977.25),
            ("2026-05-19T13:34:00Z", 28977.0, 28984.0, 28960.0, 28977.0),
            ("2026-05-19T13:35:00Z", 28980.0, 28986.0, 28970.0, 28981.0),
            ("2026-05-19T13:36:00Z", 28981.25, 29044.75, 28981.25, 29043.5),
            ("2026-05-19T13:37:00Z", 29042.5, 29068.0, 29041.0, 29052.5),
            ("2026-05-19T13:38:00Z", 29052.0, 29056.0, 28980.0, 28990.0),
            ("2026-05-19T13:39:00Z", 28990.0, 29005.0, 28950.0, 28970.0),
            ("2026-05-19T13:40:00Z", 28970.0, 28980.0, 28945.0, 28960.0),
            ("2026-05-19T13:41:00Z", 28960.0, 28970.0, 28945.0, 28953.0),
            ("2026-05-19T13:42:00Z", 28953.0, 28965.5, 28928.0, 28929.25),
            ("2026-05-19T13:43:00Z", 28929.0, 28952.25, 28919.25, 28944.5),
            ("2026-05-19T13:44:00Z", 28944.5, 28951.25, 28903.75, 28913.25),
            ("2026-05-19T13:45:00Z", 28913.5, 28940.0, 28903.5, 28922.25),
        ]
        candles = [
            {"timestamp": ts, "open": open_, "high": high, "low": low, "close": close}
            for ts, open_, high, low, close in candle_rows
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "atr.json"
            entry_agent.PERSISTENCE_STATE_PATH = temp_path / "persistence_state.json"
            entry_agent.EXECUTOR_STATE_PATH = temp_path / "executor_state.json"
            entry_agent.ENTRY_AGENT_AUDIT_DIR = temp_path / "entry_agent_audit"
            entry_agent.PERSISTENCE_STATE_PATH.write_text(json.dumps({"trades": {}}), encoding="utf-8")
            entry_agent.EXECUTOR_STATE_PATH.write_text(json.dumps({"orders": {}}), encoding="utf-8")
            cursor = {"index": 0}

            def market_snapshot(_symbol):
                candle = candles[cursor["index"]]
                return {
                    "source": "test",
                    "symbol": "NQM6",
                    "latest_price": candle["close"],
                    "latest_bar_time": candle["timestamp"],
                    "ohlc_is_closed": True,
                    "ohlc": candle,
                }

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol, limit=2: candles[: cursor["index"] + 1][-limit:]
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "normalized_symbol": "NQ",
                                "locked": True,
                                "atr_1m_14": 40.0,
                                "daily_atr14": 500.0,
                                "levels": {
                                    "PMH": {"price": 28937.75, "status": "ACTIVE", "stack_group": "NONE"},
                                    "PML": {"price": 28700.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "ONH": {"price": 29150.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "ONL": {"price": 28600.0, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            observed = {}
            for index, candle in enumerate(candles):
                cursor["index"] = index
                status = entry_agent.build_entry_status("NQ")
                persisted = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))["state_by_symbol"]["NQ"]
                observed[candle["timestamp"]] = (status, persisted)

        status, persisted = observed["2026-05-19T13:30:00Z"]
        self.assertEqual(status["active_liquidity_name"], "PMH")
        self.assertFalse(status["rejection_mode_entered"])
        self.assertFalse(persisted["step_2_1a"]["step_2_activated"])
        self.assertTrue(persisted["step_2_1a"]["pre_activation_probe_boundary"]["active"])
        self.assertEqual(persisted["step_2_1a"]["pre_activation_probe_boundary"]["boundary_price"], 28943.5)

        status, persisted = observed["2026-05-19T13:31:00Z"]
        self.assertEqual(status["active_liquidity_name"], "PMH")
        self.assertEqual(status["current_step_status"], "WAIT")
        self.assertFalse(status["rejection_mode_entered"])
        self.assertFalse(persisted["step_2_1a"]["step_2_activated"])
        self.assertTrue(persisted["step_2_1a"]["pre_activation_probe_boundary"]["active"])
        self.assertEqual(persisted["step_2_1a"]["pre_activation_probe_boundary"]["boundary_price"], 28960.0)

        status, persisted = observed["2026-05-19T13:32:00Z"]
        self.assertEqual(status["current_step_status"], "CONFIRMED")
        self.assertTrue(status["rejection_mode_entered"])
        self.assertEqual(status["setup_direction"], "SHORT")
        self.assertEqual(status["active_liquidity_name"], "PMH")
        self.assertEqual(persisted["step2_locked_owner"]["active_liquidity_name"], "PMH")

        status, persisted = observed["2026-05-19T13:33:00Z"]
        self.assertEqual(persisted["step4"]["status"], "READY")
        self.assertEqual(persisted["step4"]["state"]["leg1_status"], "COMPLETE")
        self.assertEqual(persisted["step4"]["state"]["leg1_completed_at"], "2026-05-19T13:33:00Z")

        _status, persisted = observed["2026-05-19T13:35:00Z"]
        self.assertEqual(persisted["step5"]["state"]["leg2_status"], "CONFIRMED")
        self.assertEqual(persisted["step5"]["state"]["leg2_candle_a_time"], "2026-05-19T13:34:00Z")

        _status, persisted = observed["2026-05-19T13:36:00Z"]
        self.assertEqual(persisted["step5"]["state"]["leg2_status"], "WAIT")
        # Under the corrected contract Step 6 has not yet started tracking a
        # structure candidate here, so only the waiting state remains public.
        self.assertEqual(persisted["step6"]["status"], "WAIT")

        status, persisted = observed["2026-05-19T13:37:00Z"]
        self.assertIsNone(status["extended_retrace_pending"])
        self.assertIsNone(status["extended_retrace_blocked_immediate_entry"])
        self.assertEqual(status["entry_status"], "WAIT")
        self.assertEqual(persisted["step6"]["status"], "WAIT")

        status, persisted = observed["2026-05-19T13:42:00Z"]
        self.assertEqual(status["active_liquidity_name"], "PMH")
        self.assertEqual(status["sr_rs_context"], "Normal Rejection Mode")
        self.assertEqual(status["current_pathway_control"], "rejection")
        self.assertEqual(status["setup_direction"], "SHORT")
        self.assertIsNone(persisted["step25"]["state"]["reclaim_candle_a"])

        _status, persisted = observed["2026-05-19T13:43:00Z"]
        self.assertEqual(persisted["step4"]["status"], "READY")
        self.assertEqual(persisted["step4"]["state"]["setup_direction"], "SHORT")
        self.assertEqual(persisted["step4"]["state"]["leg1_completed_at"], "2026-05-19T13:42:00Z")
        self.assertEqual(persisted["step4"]["state"]["candle_a"]["timestamp"], "2026-05-19T13:37:00Z")

        _status, persisted = observed["2026-05-19T13:44:00Z"]
        # Current Step 4-scope contract leaves Step 5 in an exact WAIT shell here,
        # without publishing a partial leg2_status field.
        self.assertEqual(persisted["step5"]["status"], "WAIT")
        self.assertEqual(persisted["step5"]["state"], {})
        self.assertIsNone(persisted["step5"]["state"].get("leg2_candle_a_time"))

        _status, persisted = observed["2026-05-19T13:45:00Z"]
        self.assertIsNone(persisted["step5"]["state"].get("leg2_status"))
        self.assertEqual(persisted["step6"]["status"], "WAIT")

    def test_nq_2026_06_19_step2_confirmation_hands_off_candle_b_to_step4(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        originals = {
            "STATE_PATH": entry_agent.STATE_PATH,
            "TV_CONTEXT_PATH": entry_agent.TV_CONTEXT_PATH,
            "TV_CONTEXT_BY_SYMBOL_PATH": entry_agent.TV_CONTEXT_BY_SYMBOL_PATH,
            "RITHMIC_ATR_SNAPSHOT_PATH": entry_agent.RITHMIC_ATR_SNAPSHOT_PATH,
            "PERSISTENCE_STATE_PATH": entry_agent.PERSISTENCE_STATE_PATH,
            "EXECUTOR_STATE_PATH": entry_agent.EXECUTOR_STATE_PATH,
            "ENTRY_AGENT_AUDIT_DIR": entry_agent.ENTRY_AGENT_AUDIT_DIR,
            "get_latest_market_snapshot": entry_agent.get_latest_market_snapshot,
            "recent_closed_bars": entry_agent.recent_closed_bars,
            "append_entry_agent_audit_row": entry_agent.append_entry_agent_audit_row,
        }
        for name, value in originals.items():
            self.addCleanup(setattr, entry_agent, name, value)

        candle_rows = [
            ("2026-06-19T13:30:00Z", 30644.0, 30678.25, 30640.75, 30659.75),
            ("2026-06-19T13:31:00Z", 30659.0, 30661.25, 30646.5, 30660.25),
            ("2026-06-19T13:32:00Z", 30661.0, 30661.0, 30648.0, 30653.0),
            ("2026-06-19T13:33:00Z", 30651.75, 30651.75, 30637.75, 30642.75),
            ("2026-06-19T13:34:00Z", 30642.25, 30646.75, 30631.75, 30645.75),
            ("2026-06-19T13:35:00Z", 30647.0, 30663.5, 30645.75, 30660.25),
            ("2026-06-19T13:36:00Z", 30661.75, 30670.5, 30657.25, 30666.5),
            ("2026-06-19T13:37:00Z", 30667.25, 30675.75, 30664.5, 30664.5),
            ("2026-06-19T13:38:00Z", 30663.75, 30675.0, 30657.25, 30667.75),
            ("2026-06-19T13:39:00Z", 30667.75, 30667.75, 30659.0, 30663.75),
            ("2026-06-19T13:40:00Z", 30663.75, 30673.0, 30663.5, 30667.0),
            ("2026-06-19T13:41:00Z", 30666.5, 30668.0, 30655.75, 30658.75),
            ("2026-06-19T13:42:00Z", 30659.25, 30660.75, 30651.25, 30659.75),
            ("2026-06-19T13:43:00Z", 30661.0, 30664.75, 30653.75, 30664.75),
            ("2026-06-19T13:44:00Z", 30664.0, 30668.75, 30645.5, 30650.75),
            ("2026-06-19T13:45:00Z", 30651.75, 30662.0, 30642.25, 30661.25),
            ("2026-06-19T13:46:00Z", 30660.5, 30672.25, 30660.5, 30671.75),
            ("2026-06-19T13:47:00Z", 30672.25, 30680.0, 30668.0, 30671.75),
            ("2026-06-19T13:48:00Z", 30670.0, 30670.0, 30659.0, 30667.25),
            ("2026-06-19T13:49:00Z", 30668.5, 30671.5, 30660.0, 30671.0),
            ("2026-06-19T13:50:00Z", 30671.25, 30674.75, 30664.0, 30672.5),
            ("2026-06-19T13:51:00Z", 30671.25, 30679.5, 30667.75, 30674.0),
            ("2026-06-19T13:52:00Z", 30673.5, 30676.5, 30664.5, 30666.25),
            ("2026-06-19T13:53:00Z", 30668.5, 30673.75, 30666.0, 30673.75),
            ("2026-06-19T13:54:00Z", 30673.5, 30679.0, 30670.75, 30673.5),
            ("2026-06-19T13:55:00Z", 30669.75, 30676.25, 30669.0, 30675.25),
            ("2026-06-19T13:56:00Z", 30675.25, 30695.75, 30675.25, 30686.25),
            ("2026-06-19T13:57:00Z", 30685.0, 30693.5, 30683.0, 30686.75),
        ]
        candles = [
            {"timestamp": ts, "open": open_, "high": high, "low": low, "close": close}
            for ts, open_, high, low, close in candle_rows
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "atr.json"
            entry_agent.PERSISTENCE_STATE_PATH = temp_path / "persistence_state.json"
            entry_agent.EXECUTOR_STATE_PATH = temp_path / "executor_state.json"
            entry_agent.ENTRY_AGENT_AUDIT_DIR = temp_path / "entry_agent_audit"
            entry_agent.PERSISTENCE_STATE_PATH.write_text(json.dumps({"trades": {}}), encoding="utf-8")
            entry_agent.EXECUTOR_STATE_PATH.write_text(json.dumps({"orders": {}}), encoding="utf-8")
            entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
            cursor = {"index": 0}

            def market_snapshot(_symbol):
                candle = candles[cursor["index"]]
                return {
                    "source": "test",
                    "symbol": "NQ",
                    "latest_price": candle["close"],
                    "latest_bar_time": candle["timestamp"],
                    "ohlc_is_closed": True,
                    "ohlc": candle,
                }

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol, limit=120: candles[: cursor["index"] + 1][-limit:]
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "normalized_symbol": "NQ",
                                "locked": True,
                                "liquidity_context_locked": True,
                                "liquidity_context_locked_at": "2026-06-19T13:15:00Z",
                                "liquidity_context_source": "tradingview_level_helper",
                                "atr_1m_14": 40.0,
                                "daily_atr14": 500.0,
                                "levels": {
                                    "LH": {"price": 30666.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                                    "PMH": {"price": 30670.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                                    "ONH": {"price": 30770.75, "status": "ACTIVE", "stack_group": "HIGH 2"},
                                    "YH": {"price": 30783.25, "status": "ACTIVE", "stack_group": "HIGH 2"},
                                    "PML": {"price": 30397.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "LL": {"price": 30291.25, "status": "ACTIVE", "stack_group": "NONE"},
                                    "ONL": {"price": 30291.25, "status": "ACTIVE", "stack_group": "NONE"},
                                    "YL": {"price": 30125.75, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            observed = {}
            for index, candle in enumerate(candles):
                cursor["index"] = index
                observed[candle["timestamp"]] = entry_agent.build_entry_status("NQ")

            step2_status = observed["2026-06-19T13:56:00Z"]
            leg1_status = observed["2026-06-19T13:57:00Z"]
            persisted = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))["state_by_symbol"]["NQ"]
            step4 = persisted["step4"]
            step4_state = step4["state"]

        self.assertEqual(step2_status["current_step_label"], "Step 2 (Liquidity Close / Pathway Activation)")
        self.assertEqual(step2_status["setup_direction"], "SHORT")
        self.assertEqual(step2_status["current_pathway_control"], "rejection")

        # Static-stack rejection handoff:
        # 06:56 is the stack/extreme proof candle, not Candle B.
        # 06:57 is the first post-extreme candle and becomes Step 4 Candle A.
        # Candle B must be a later future candle, so Step 4 remains WAIT here.
        self.assertEqual(leg1_status["current_step_label"], "Step 2 (Liquidity Close / Pathway Activation)")
        self.assertEqual(leg1_status["leg1_state"], "WAIT")
        self.assertEqual(leg1_status["setup_direction"], "SHORT")
        self.assertIsNone(leg1_status["leg1_completed_at"])
        self.assertEqual(step4["status"], "WAIT")
        self.assertEqual(step4_state["stack_extreme_confirmation_candle"]["timestamp"], "2026-06-19T13:56:00Z")
        self.assertEqual(step4_state["candle_a"]["timestamp"], "2026-06-19T13:57:00Z")
        self.assertIsNone(step4_state.get("candle_b"))
        self.assertEqual(step4_state["candle_a_source"], "step4_stack_post_extreme_candle_a")
        self.assertTrue(step4_state.get("awaiting_stack_candle_b"))
        self.assertIsNone(step4_state.get("step3_close_participation_pass"))
        self.assertIsNone(step4_state.get("step3_wick_participation_pct"))
        self.assertIsNone(step4_state.get("leg1_status"))

    def test_nq_2026_06_19_high1_rs_continuation_activates_at_0700_using_pmh_extreme(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        originals = {
            "STATE_PATH": entry_agent.STATE_PATH,
            "TV_CONTEXT_PATH": entry_agent.TV_CONTEXT_PATH,
            "TV_CONTEXT_BY_SYMBOL_PATH": entry_agent.TV_CONTEXT_BY_SYMBOL_PATH,
            "RITHMIC_ATR_SNAPSHOT_PATH": entry_agent.RITHMIC_ATR_SNAPSHOT_PATH,
            "PERSISTENCE_STATE_PATH": entry_agent.PERSISTENCE_STATE_PATH,
            "EXECUTOR_STATE_PATH": entry_agent.EXECUTOR_STATE_PATH,
            "ENTRY_AGENT_AUDIT_DIR": entry_agent.ENTRY_AGENT_AUDIT_DIR,
            "get_latest_market_snapshot": entry_agent.get_latest_market_snapshot,
            "recent_closed_bars": entry_agent.recent_closed_bars,
            "append_entry_agent_audit_row": entry_agent.append_entry_agent_audit_row,
        }
        for name, value in originals.items():
            self.addCleanup(setattr, entry_agent, name, value)

        candle_rows = [
            ("2026-06-19T13:30:00Z", 30644.0, 30678.25, 30640.75, 30659.75),
            ("2026-06-19T13:31:00Z", 30659.0, 30661.25, 30646.5, 30660.25),
            ("2026-06-19T13:32:00Z", 30661.0, 30661.0, 30648.0, 30653.0),
            ("2026-06-19T13:33:00Z", 30651.75, 30651.75, 30637.75, 30642.75),
            ("2026-06-19T13:34:00Z", 30642.25, 30646.75, 30631.75, 30645.75),
            ("2026-06-19T13:35:00Z", 30647.0, 30663.5, 30645.75, 30660.25),
            ("2026-06-19T13:36:00Z", 30661.75, 30670.5, 30657.25, 30666.5),
            ("2026-06-19T13:37:00Z", 30667.25, 30675.75, 30664.5, 30664.5),
            ("2026-06-19T13:38:00Z", 30663.75, 30675.0, 30657.25, 30667.75),
            ("2026-06-19T13:39:00Z", 30667.75, 30667.75, 30659.0, 30663.75),
            ("2026-06-19T13:40:00Z", 30663.75, 30673.0, 30663.5, 30667.0),
            ("2026-06-19T13:41:00Z", 30666.5, 30668.0, 30655.75, 30658.75),
            ("2026-06-19T13:42:00Z", 30659.25, 30660.75, 30651.25, 30659.75),
            ("2026-06-19T13:43:00Z", 30661.0, 30664.75, 30653.75, 30664.75),
            ("2026-06-19T13:44:00Z", 30664.0, 30668.75, 30645.5, 30650.75),
            ("2026-06-19T13:45:00Z", 30651.75, 30662.0, 30642.25, 30661.25),
            ("2026-06-19T13:46:00Z", 30660.5, 30672.25, 30660.5, 30671.75),
            ("2026-06-19T13:47:00Z", 30672.25, 30680.0, 30668.0, 30671.75),
            ("2026-06-19T13:48:00Z", 30670.0, 30670.0, 30659.0, 30667.25),
            ("2026-06-19T13:49:00Z", 30668.5, 30671.5, 30660.0, 30671.0),
            ("2026-06-19T13:50:00Z", 30671.25, 30674.75, 30664.0, 30672.5),
            ("2026-06-19T13:51:00Z", 30671.25, 30679.5, 30667.75, 30674.0),
            ("2026-06-19T13:52:00Z", 30673.5, 30676.5, 30664.5, 30666.25),
            ("2026-06-19T13:53:00Z", 30668.5, 30673.75, 30666.0, 30673.75),
            ("2026-06-19T13:54:00Z", 30673.5, 30679.0, 30670.75, 30673.5),
            ("2026-06-19T13:55:00Z", 30669.75, 30676.25, 30669.0, 30675.25),
            ("2026-06-19T13:56:00Z", 30675.25, 30695.75, 30675.25, 30686.25),
            ("2026-06-19T13:57:00Z", 30685.0, 30693.5, 30683.0, 30686.75),
            ("2026-06-19T13:58:00Z", 30685.75, 30687.75, 30680.75, 30684.5),
            ("2026-06-19T13:59:00Z", 30685.0, 30686.75, 30678.0, 30682.75),
            ("2026-06-19T14:00:00Z", 30682.25, 30684.75, 30664.25, 30668.25),
        ]
        candles = [
            {"timestamp": ts, "open": open_, "high": high, "low": low, "close": close}
            for ts, open_, high, low, close in candle_rows
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "atr.json"
            entry_agent.PERSISTENCE_STATE_PATH = temp_path / "persistence_state.json"
            entry_agent.EXECUTOR_STATE_PATH = temp_path / "executor_state.json"
            entry_agent.ENTRY_AGENT_AUDIT_DIR = temp_path / "entry_agent_audit"
            entry_agent.PERSISTENCE_STATE_PATH.write_text(json.dumps({"trades": {}}), encoding="utf-8")
            entry_agent.EXECUTOR_STATE_PATH.write_text(json.dumps({"orders": {}}), encoding="utf-8")
            entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
            cursor = {"index": 0}

            def market_snapshot(_symbol):
                candle = candles[cursor["index"]]
                return {
                    "source": "test",
                    "symbol": "NQ",
                    "latest_price": candle["close"],
                    "latest_bar_time": candle["timestamp"],
                    "ohlc_is_closed": True,
                    "ohlc": candle,
                }

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol, limit=120: candles[: cursor["index"] + 1][-limit:]
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "normalized_symbol": "NQ",
                                "locked": True,
                                "liquidity_context_locked": True,
                                "liquidity_context_locked_at": "2026-06-19T13:15:00Z",
                                "liquidity_context_source": "tradingview_level_helper",
                                "atr_1m_14": 40.0,
                                "daily_atr14": 500.0,
                                "levels": {
                                    "LH": {"price": 30666.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                                    "PMH": {"price": 30670.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                                    "ONH": {"price": 30770.75, "status": "ACTIVE", "stack_group": "HIGH 2"},
                                    "YH": {"price": 30783.25, "status": "ACTIVE", "stack_group": "HIGH 2"},
                                    "PML": {"price": 30397.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "LL": {"price": 30291.25, "status": "ACTIVE", "stack_group": "NONE"},
                                    "ONL": {"price": 30291.25, "status": "ACTIVE", "stack_group": "NONE"},
                                    "YL": {"price": 30125.75, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            observed = {}
            persisted_states = {}
            for index, candle in enumerate(candles):
                cursor["index"] = index
                observed[candle["timestamp"]] = entry_agent.build_entry_status("NQ")
                persisted_states[candle["timestamp"]] = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))["state_by_symbol"]["NQ"]

        prior = observed["2026-06-19T13:59:00Z"]
        current = observed["2026-06-19T14:00:00Z"]
        step25_state = persisted_states["2026-06-19T14:00:00Z"]["step25"]["state"]

        # 06:59 provides the prior close beyond PMH needed for continuation qualification.
        self.assertGreater(prior["candle_close"], 30670.0)

        # 07:00 must activate R/S off the PMH stack extreme 30670.0, not the LH close boundary 30666.0.
        self.assertEqual(current["candle_close"], 30668.25)
        self.assertEqual(step25_state["level"], 30670.0)
        self.assertEqual(step25_state["stack_extreme"], 30670.0)
        self.assertEqual(step25_state["pathway_level"], 30670.0)
        self.assertTrue(step25_state["continuation_step2_activated"])
        self.assertEqual(step25_state["controlling_mode"], "R/S")
        self.assertEqual(current["current_pathway_control"], "continuation")
        self.assertEqual(current["sr_rs_context"], "R/S")
        self.assertEqual(current["setup_direction"], "LONG")

    def test_nq_2026_06_19_rs_continuation_hands_off_step4_on_next_candle(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        originals = {
            "STATE_PATH": entry_agent.STATE_PATH,
            "TV_CONTEXT_PATH": entry_agent.TV_CONTEXT_PATH,
            "TV_CONTEXT_BY_SYMBOL_PATH": entry_agent.TV_CONTEXT_BY_SYMBOL_PATH,
            "RITHMIC_ATR_SNAPSHOT_PATH": entry_agent.RITHMIC_ATR_SNAPSHOT_PATH,
            "PERSISTENCE_STATE_PATH": entry_agent.PERSISTENCE_STATE_PATH,
            "EXECUTOR_STATE_PATH": entry_agent.EXECUTOR_STATE_PATH,
            "ENTRY_AGENT_AUDIT_DIR": entry_agent.ENTRY_AGENT_AUDIT_DIR,
            "get_latest_market_snapshot": entry_agent.get_latest_market_snapshot,
            "recent_closed_bars": entry_agent.recent_closed_bars,
            "append_entry_agent_audit_row": entry_agent.append_entry_agent_audit_row,
        }
        for name, value in originals.items():
            self.addCleanup(setattr, entry_agent, name, value)

        candle_rows = [
            ("2026-06-19T13:30:00Z", 30644.0, 30678.25, 30640.75, 30659.75),
            ("2026-06-19T13:31:00Z", 30659.0, 30661.25, 30646.5, 30660.25),
            ("2026-06-19T13:32:00Z", 30661.0, 30661.0, 30648.0, 30653.0),
            ("2026-06-19T13:33:00Z", 30651.75, 30651.75, 30637.75, 30642.75),
            ("2026-06-19T13:34:00Z", 30642.25, 30646.75, 30631.75, 30645.75),
            ("2026-06-19T13:35:00Z", 30647.0, 30663.5, 30645.75, 30660.25),
            ("2026-06-19T13:36:00Z", 30661.75, 30670.5, 30657.25, 30666.5),
            ("2026-06-19T13:37:00Z", 30667.25, 30675.75, 30664.5, 30664.5),
            ("2026-06-19T13:38:00Z", 30663.75, 30675.0, 30657.25, 30667.75),
            ("2026-06-19T13:39:00Z", 30667.75, 30667.75, 30659.0, 30663.75),
            ("2026-06-19T13:40:00Z", 30663.75, 30673.0, 30663.5, 30667.0),
            ("2026-06-19T13:41:00Z", 30666.5, 30668.0, 30655.75, 30658.75),
            ("2026-06-19T13:42:00Z", 30659.25, 30660.75, 30651.25, 30659.75),
            ("2026-06-19T13:43:00Z", 30661.0, 30664.75, 30653.75, 30664.75),
            ("2026-06-19T13:44:00Z", 30664.0, 30668.75, 30645.5, 30650.75),
            ("2026-06-19T13:45:00Z", 30651.75, 30662.0, 30642.25, 30661.25),
            ("2026-06-19T13:46:00Z", 30660.5, 30672.25, 30660.5, 30671.75),
            ("2026-06-19T13:47:00Z", 30672.25, 30680.0, 30668.0, 30671.75),
            ("2026-06-19T13:48:00Z", 30670.0, 30670.0, 30659.0, 30667.25),
            ("2026-06-19T13:49:00Z", 30668.5, 30671.5, 30660.0, 30671.0),
            ("2026-06-19T13:50:00Z", 30671.25, 30674.75, 30664.0, 30672.5),
            ("2026-06-19T13:51:00Z", 30671.25, 30679.5, 30667.75, 30674.0),
            ("2026-06-19T13:52:00Z", 30673.5, 30676.5, 30664.5, 30666.25),
            ("2026-06-19T13:53:00Z", 30668.5, 30673.75, 30666.0, 30673.75),
            ("2026-06-19T13:54:00Z", 30673.5, 30679.0, 30670.75, 30673.5),
            ("2026-06-19T13:55:00Z", 30669.75, 30676.25, 30669.0, 30675.25),
            ("2026-06-19T13:56:00Z", 30675.25, 30695.75, 30675.25, 30686.25),
            ("2026-06-19T13:57:00Z", 30685.0, 30693.5, 30683.0, 30686.75),
            ("2026-06-19T13:58:00Z", 30685.75, 30687.75, 30680.75, 30684.5),
            ("2026-06-19T13:59:00Z", 30685.0, 30686.75, 30678.0, 30682.75),
            ("2026-06-19T14:00:00Z", 30682.25, 30684.75, 30664.25, 30668.25),
            ("2026-06-19T14:01:00Z", 30666.5, 30668.5, 30657.75, 30665.0),
        ]
        candles = [
            {"timestamp": ts, "open": open_, "high": high, "low": low, "close": close}
            for ts, open_, high, low, close in candle_rows
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "atr.json"
            entry_agent.PERSISTENCE_STATE_PATH = temp_path / "persistence_state.json"
            entry_agent.EXECUTOR_STATE_PATH = temp_path / "executor_state.json"
            entry_agent.ENTRY_AGENT_AUDIT_DIR = temp_path / "entry_agent_audit"
            entry_agent.PERSISTENCE_STATE_PATH.write_text(json.dumps({"trades": {}}), encoding="utf-8")
            entry_agent.EXECUTOR_STATE_PATH.write_text(json.dumps({"orders": {}}), encoding="utf-8")
            entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
            cursor = {"index": 0}

            def market_snapshot(_symbol):
                candle = candles[cursor["index"]]
                return {
                    "source": "test",
                    "symbol": "NQ",
                    "latest_price": candle["close"],
                    "latest_bar_time": candle["timestamp"],
                    "ohlc_is_closed": True,
                    "ohlc": candle,
                }

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol, limit=120: candles[: cursor["index"] + 1][-limit:]
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "normalized_symbol": "NQ",
                                "locked": True,
                                "liquidity_context_locked": True,
                                "liquidity_context_locked_at": "2026-06-19T13:15:00Z",
                                "liquidity_context_source": "tradingview_level_helper",
                                "atr_1m_14": 40.0,
                                "daily_atr14": 500.0,
                                "levels": {
                                    "LH": {"price": 30666.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                                    "PMH": {"price": 30670.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                                    "ONH": {"price": 30770.75, "status": "ACTIVE", "stack_group": "HIGH 2"},
                                    "YH": {"price": 30783.25, "status": "ACTIVE", "stack_group": "HIGH 2"},
                                    "PML": {"price": 30397.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "LL": {"price": 30291.25, "status": "ACTIVE", "stack_group": "NONE"},
                                    "ONL": {"price": 30291.25, "status": "ACTIVE", "stack_group": "NONE"},
                                    "YL": {"price": 30125.75, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            observed = {}
            persisted_states = {}
            for index, candle in enumerate(candles):
                cursor["index"] = index
                observed[candle["timestamp"]] = entry_agent.build_entry_status("NQ")
                persisted_states[candle["timestamp"]] = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))["state_by_symbol"]["NQ"]

        step25_0700 = persisted_states["2026-06-19T14:00:00Z"]["step25"]["state"]
        step4_0700 = persisted_states["2026-06-19T14:00:00Z"]["step4"]
        step4_state_0700 = step4_0700["state"]
        step4_0701 = persisted_states["2026-06-19T14:01:00Z"]["step4"]
        step4_state_0701 = step4_0701["state"]

        self.assertEqual(step25_0700["controlling_mode"], "R/S")
        self.assertTrue(step25_0700["continuation_step2_activated"])
        self.assertEqual(step25_0700["reclaim_candle_a"]["timestamp"], "2026-06-19T14:00:00Z")

        # 07:00 is continuation Candle A; Step 4 must wait and must not reuse stale rejection 06:56/SHORT context.
        self.assertEqual(step4_0700["status"], "WAIT")
        self.assertEqual(step4_state_0700["candle_a"]["timestamp"], "2026-06-19T14:00:00Z")
        self.assertIsNone(step4_state_0700.get("candle_b"))
        self.assertEqual(step4_state_0700["setup_direction"], "LONG")

        # 07:01 is the first continuation Candle B evaluation and should complete LONG Leg 1.
        self.assertEqual(step4_0701["status"], "READY")
        self.assertEqual(step4_state_0701["leg1_status"], "COMPLETE")
        self.assertEqual(step4_state_0701["candle_a"]["timestamp"], "2026-06-19T14:00:00Z")
        self.assertEqual(step4_state_0701["candle_b"]["timestamp"], "2026-06-19T14:01:00Z")
        self.assertEqual(step4_state_0701["setup_direction"], "LONG")

    def test_nq_2026_06_19_rs_continuation_preserves_completed_leg1_after_0701(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        originals = {
            "STATE_PATH": entry_agent.STATE_PATH,
            "TV_CONTEXT_PATH": entry_agent.TV_CONTEXT_PATH,
            "TV_CONTEXT_BY_SYMBOL_PATH": entry_agent.TV_CONTEXT_BY_SYMBOL_PATH,
            "RITHMIC_ATR_SNAPSHOT_PATH": entry_agent.RITHMIC_ATR_SNAPSHOT_PATH,
            "PERSISTENCE_STATE_PATH": entry_agent.PERSISTENCE_STATE_PATH,
            "EXECUTOR_STATE_PATH": entry_agent.EXECUTOR_STATE_PATH,
            "ENTRY_AGENT_AUDIT_DIR": entry_agent.ENTRY_AGENT_AUDIT_DIR,
            "get_latest_market_snapshot": entry_agent.get_latest_market_snapshot,
            "recent_closed_bars": entry_agent.recent_closed_bars,
            "append_entry_agent_audit_row": entry_agent.append_entry_agent_audit_row,
        }
        for name, value in originals.items():
            self.addCleanup(setattr, entry_agent, name, value)

        candle_rows = [
            ("2026-06-19T13:30:00Z", 30644.0, 30678.25, 30640.75, 30659.75),
            ("2026-06-19T13:31:00Z", 30659.0, 30661.25, 30646.5, 30660.25),
            ("2026-06-19T13:32:00Z", 30661.0, 30661.0, 30648.0, 30653.0),
            ("2026-06-19T13:33:00Z", 30651.75, 30651.75, 30637.75, 30642.75),
            ("2026-06-19T13:34:00Z", 30642.25, 30646.75, 30631.75, 30645.75),
            ("2026-06-19T13:35:00Z", 30647.0, 30663.5, 30645.75, 30660.25),
            ("2026-06-19T13:36:00Z", 30661.75, 30670.5, 30657.25, 30666.5),
            ("2026-06-19T13:37:00Z", 30667.25, 30675.75, 30664.5, 30664.5),
            ("2026-06-19T13:38:00Z", 30663.75, 30675.0, 30657.25, 30667.75),
            ("2026-06-19T13:39:00Z", 30667.75, 30667.75, 30659.0, 30663.75),
            ("2026-06-19T13:40:00Z", 30663.75, 30673.0, 30663.5, 30667.0),
            ("2026-06-19T13:41:00Z", 30666.5, 30668.0, 30655.75, 30658.75),
            ("2026-06-19T13:42:00Z", 30659.25, 30660.75, 30651.25, 30659.75),
            ("2026-06-19T13:43:00Z", 30661.0, 30664.75, 30653.75, 30664.75),
            ("2026-06-19T13:44:00Z", 30664.0, 30668.75, 30645.5, 30650.75),
            ("2026-06-19T13:45:00Z", 30651.75, 30662.0, 30642.25, 30661.25),
            ("2026-06-19T13:46:00Z", 30660.5, 30672.25, 30660.5, 30671.75),
            ("2026-06-19T13:47:00Z", 30672.25, 30680.0, 30668.0, 30671.75),
            ("2026-06-19T13:48:00Z", 30670.0, 30670.0, 30659.0, 30667.25),
            ("2026-06-19T13:49:00Z", 30668.5, 30671.5, 30660.0, 30671.0),
            ("2026-06-19T13:50:00Z", 30671.25, 30674.75, 30664.0, 30672.5),
            ("2026-06-19T13:51:00Z", 30671.25, 30679.5, 30667.75, 30674.0),
            ("2026-06-19T13:52:00Z", 30673.5, 30676.5, 30664.5, 30666.25),
            ("2026-06-19T13:53:00Z", 30668.5, 30673.75, 30666.0, 30673.75),
            ("2026-06-19T13:54:00Z", 30673.5, 30679.0, 30670.75, 30673.5),
            ("2026-06-19T13:55:00Z", 30669.75, 30676.25, 30669.0, 30675.25),
            ("2026-06-19T13:56:00Z", 30675.25, 30695.75, 30675.25, 30686.25),
            ("2026-06-19T13:57:00Z", 30685.0, 30693.5, 30683.0, 30686.75),
            ("2026-06-19T13:58:00Z", 30685.75, 30687.75, 30680.75, 30684.5),
            ("2026-06-19T13:59:00Z", 30685.0, 30686.75, 30678.0, 30682.75),
            ("2026-06-19T14:00:00Z", 30682.25, 30684.75, 30664.25, 30668.25),
            ("2026-06-19T14:01:00Z", 30666.5, 30668.5, 30657.75, 30665.0),
            ("2026-06-19T14:02:00Z", 30666.25, 30669.75, 30653.25, 30653.5),
        ]
        candles = [
            {"timestamp": ts, "open": open_, "high": high, "low": low, "close": close}
            for ts, open_, high, low, close in candle_rows
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "atr.json"
            entry_agent.PERSISTENCE_STATE_PATH = temp_path / "persistence_state.json"
            entry_agent.EXECUTOR_STATE_PATH = temp_path / "executor_state.json"
            entry_agent.ENTRY_AGENT_AUDIT_DIR = temp_path / "entry_agent_audit"
            entry_agent.PERSISTENCE_STATE_PATH.write_text(json.dumps({"trades": {}}), encoding="utf-8")
            entry_agent.EXECUTOR_STATE_PATH.write_text(json.dumps({"orders": {}}), encoding="utf-8")
            entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
            cursor = {"index": 0}

            def market_snapshot(_symbol):
                candle = candles[cursor["index"]]
                return {
                    "source": "test",
                    "symbol": "NQ",
                    "latest_price": candle["close"],
                    "latest_bar_time": candle["timestamp"],
                    "ohlc_is_closed": True,
                    "ohlc": candle,
                }

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol, limit=120: candles[: cursor["index"] + 1][-limit:]
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "normalized_symbol": "NQ",
                                "locked": True,
                                "liquidity_context_locked": True,
                                "liquidity_context_locked_at": "2026-06-19T13:15:00Z",
                                "liquidity_context_source": "tradingview_level_helper",
                                "atr_1m_14": 40.0,
                                "daily_atr14": 500.0,
                                "levels": {
                                    "LH": {"price": 30666.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                                    "PMH": {"price": 30670.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                                    "ONH": {"price": 30770.75, "status": "ACTIVE", "stack_group": "HIGH 2"},
                                    "YH": {"price": 30783.25, "status": "ACTIVE", "stack_group": "HIGH 2"},
                                    "PML": {"price": 30397.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "LL": {"price": 30291.25, "status": "ACTIVE", "stack_group": "NONE"},
                                    "ONL": {"price": 30291.25, "status": "ACTIVE", "stack_group": "NONE"},
                                    "YL": {"price": 30125.75, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            observed = {}
            persisted_states = {}
            for index, candle in enumerate(candles):
                cursor["index"] = index
                observed[candle["timestamp"]] = entry_agent.build_entry_status("NQ")
                persisted_states[candle["timestamp"]] = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))["state_by_symbol"]["NQ"]

        status_0702 = observed["2026-06-19T14:02:00Z"]
        step4_0701 = persisted_states["2026-06-19T14:01:00Z"]["step4"]["state"]
        step4_0702 = persisted_states["2026-06-19T14:02:00Z"]["step4"]["state"]
        step5_0702 = persisted_states["2026-06-19T14:02:00Z"]["step5"]["state"]

        self.assertEqual(step4_0701["leg1_status"], "COMPLETE")
        self.assertTrue(step4_0701["leg1_state_locked"])

        # 07:02 is the first future candle after the locked LONG Leg 1; it must preserve Leg 1 and lock Leg 2 from the Candle A close rule.
        self.assertEqual(status_0702["current_pathway_control"], "continuation")
        self.assertEqual(status_0702["sr_rs_context"], "R/S")
        self.assertEqual(status_0702["setup_direction"], "LONG")
        self.assertEqual(status_0702["current_step_label"], "Step 5 (Leg 2 Confirmation)")
        self.assertEqual(status_0702["leg1_state"], "COMPLETE")
        self.assertEqual(step4_0702["candle_a"]["timestamp"], "2026-06-19T14:00:00Z")
        self.assertEqual(step4_0702["candle_b"]["timestamp"], "2026-06-19T14:01:00Z")
        self.assertTrue(step4_0702["leg1_state_locked"])
        self.assertEqual(step4_0702["leg1_status"], "COMPLETE")
        self.assertEqual(step5_0702["leg2_status"], "CONFIRMED")
        self.assertEqual(step5_0702["leg2_candle_a_time"], "2026-06-19T14:02:00Z")
        self.assertIsNone(step5_0702.get("invalidated_at"))

    def test_nq_2026_06_19_rs_step6_window_preserves_lifecycle_through_0705(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        originals = {
            "STATE_PATH": entry_agent.STATE_PATH,
            "TV_CONTEXT_PATH": entry_agent.TV_CONTEXT_PATH,
            "TV_CONTEXT_BY_SYMBOL_PATH": entry_agent.TV_CONTEXT_BY_SYMBOL_PATH,
            "RITHMIC_ATR_SNAPSHOT_PATH": entry_agent.RITHMIC_ATR_SNAPSHOT_PATH,
            "PERSISTENCE_STATE_PATH": entry_agent.PERSISTENCE_STATE_PATH,
            "EXECUTOR_STATE_PATH": entry_agent.EXECUTOR_STATE_PATH,
            "ENTRY_AGENT_AUDIT_DIR": entry_agent.ENTRY_AGENT_AUDIT_DIR,
            "get_latest_market_snapshot": entry_agent.get_latest_market_snapshot,
            "recent_closed_bars": entry_agent.recent_closed_bars,
            "append_entry_agent_audit_row": entry_agent.append_entry_agent_audit_row,
        }
        for name, value in originals.items():
            self.addCleanup(setattr, entry_agent, name, value)

        candle_rows = [
            ("2026-06-19T13:30:00Z", 30644.0, 30678.25, 30640.75, 30659.75),
            ("2026-06-19T13:31:00Z", 30659.0, 30661.25, 30646.5, 30660.25),
            ("2026-06-19T13:32:00Z", 30661.0, 30661.0, 30648.0, 30653.0),
            ("2026-06-19T13:33:00Z", 30651.75, 30651.75, 30637.75, 30642.75),
            ("2026-06-19T13:34:00Z", 30642.25, 30646.75, 30631.75, 30645.75),
            ("2026-06-19T13:35:00Z", 30647.0, 30663.5, 30645.75, 30660.25),
            ("2026-06-19T13:36:00Z", 30661.75, 30670.5, 30657.25, 30666.5),
            ("2026-06-19T13:37:00Z", 30667.25, 30675.75, 30664.5, 30664.5),
            ("2026-06-19T13:38:00Z", 30663.75, 30675.0, 30657.25, 30667.75),
            ("2026-06-19T13:39:00Z", 30667.75, 30667.75, 30659.0, 30663.75),
            ("2026-06-19T13:40:00Z", 30663.75, 30673.0, 30663.5, 30667.0),
            ("2026-06-19T13:41:00Z", 30666.5, 30668.0, 30655.75, 30658.75),
            ("2026-06-19T13:42:00Z", 30659.25, 30660.75, 30651.25, 30659.75),
            ("2026-06-19T13:43:00Z", 30661.0, 30664.75, 30653.75, 30664.75),
            ("2026-06-19T13:44:00Z", 30664.0, 30668.75, 30645.5, 30650.75),
            ("2026-06-19T13:45:00Z", 30651.75, 30662.0, 30642.25, 30661.25),
            ("2026-06-19T13:46:00Z", 30660.5, 30672.25, 30660.5, 30671.75),
            ("2026-06-19T13:47:00Z", 30672.25, 30680.0, 30668.0, 30671.75),
            ("2026-06-19T13:48:00Z", 30670.0, 30670.0, 30659.0, 30667.25),
            ("2026-06-19T13:49:00Z", 30668.5, 30671.5, 30660.0, 30671.0),
            ("2026-06-19T13:50:00Z", 30671.25, 30674.75, 30664.0, 30672.5),
            ("2026-06-19T13:51:00Z", 30671.25, 30679.5, 30667.75, 30674.0),
            ("2026-06-19T13:52:00Z", 30673.5, 30676.5, 30664.5, 30666.25),
            ("2026-06-19T13:53:00Z", 30668.5, 30673.75, 30666.0, 30673.75),
            ("2026-06-19T13:54:00Z", 30673.5, 30679.0, 30670.75, 30673.5),
            ("2026-06-19T13:55:00Z", 30669.75, 30676.25, 30669.0, 30675.25),
            ("2026-06-19T13:56:00Z", 30675.25, 30695.75, 30675.25, 30686.25),
            ("2026-06-19T13:57:00Z", 30685.0, 30693.5, 30683.0, 30686.75),
            ("2026-06-19T13:58:00Z", 30685.75, 30687.75, 30680.75, 30684.5),
            ("2026-06-19T13:59:00Z", 30685.0, 30686.75, 30678.0, 30682.75),
            ("2026-06-19T14:00:00Z", 30682.25, 30684.75, 30664.25, 30668.25),
            ("2026-06-19T14:01:00Z", 30666.5, 30668.5, 30657.75, 30665.0),
            ("2026-06-19T14:02:00Z", 30666.25, 30669.75, 30653.25, 30653.5),
            ("2026-06-19T14:03:00Z", 30655.0, 30675.5, 30653.5, 30673.25),
            ("2026-06-19T14:04:00Z", 30671.75, 30680.5, 30671.25, 30677.75),
            ("2026-06-19T14:05:00Z", 30679.25, 30682.0, 30669.0, 30669.75),
        ]
        candles = [
            {"timestamp": ts, "open": open_, "high": high, "low": low, "close": close}
            for ts, open_, high, low, close in candle_rows
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "atr.json"
            entry_agent.PERSISTENCE_STATE_PATH = temp_path / "persistence_state.json"
            entry_agent.EXECUTOR_STATE_PATH = temp_path / "executor_state.json"
            entry_agent.ENTRY_AGENT_AUDIT_DIR = temp_path / "entry_agent_audit"
            entry_agent.PERSISTENCE_STATE_PATH.write_text(json.dumps({"trades": {}}), encoding="utf-8")
            entry_agent.EXECUTOR_STATE_PATH.write_text(json.dumps({"orders": {}}), encoding="utf-8")
            entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
            cursor = {"index": 0}

            def market_snapshot(_symbol):
                candle = candles[cursor["index"]]
                return {
                    "source": "test",
                    "symbol": "NQ",
                    "latest_price": candle["close"],
                    "latest_bar_time": candle["timestamp"],
                    "ohlc_is_closed": True,
                    "ohlc": candle,
                }

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol, limit=120: candles[: cursor["index"] + 1][-limit:]
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "normalized_symbol": "NQ",
                                "locked": True,
                                "liquidity_context_locked": True,
                                "liquidity_context_locked_at": "2026-06-19T13:15:00Z",
                                "liquidity_context_source": "tradingview_level_helper",
                                "atr_1m_14": 40.0,
                                "daily_atr14": 500.0,
                                "levels": {
                                    "LH": {"price": 30666.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                                    "PMH": {"price": 30670.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                                    "ONH": {"price": 30770.75, "status": "ACTIVE", "stack_group": "HIGH 2"},
                                    "YH": {"price": 30783.25, "status": "ACTIVE", "stack_group": "HIGH 2"},
                                    "PML": {"price": 30397.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "LL": {"price": 30291.25, "status": "ACTIVE", "stack_group": "NONE"},
                                    "ONL": {"price": 30291.25, "status": "ACTIVE", "stack_group": "NONE"},
                                    "YL": {"price": 30125.75, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            observed = {}
            persisted_states = {}
            for index, candle in enumerate(candles):
                cursor["index"] = index
                observed[candle["timestamp"]] = entry_agent.build_entry_status("NQ")
                persisted_states[candle["timestamp"]] = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))["state_by_symbol"]["NQ"]

        status_0703 = observed["2026-06-19T14:03:00Z"]
        status_0704 = observed["2026-06-19T14:04:00Z"]
        status_0705 = observed["2026-06-19T14:05:00Z"]
        step25_0705 = persisted_states["2026-06-19T14:05:00Z"]["step25"]["state"]
        step4_0705 = persisted_states["2026-06-19T14:05:00Z"]["step4"]["state"]
        step5_0702 = persisted_states["2026-06-19T14:02:00Z"]["step5"]["state"]
        step5_0703 = persisted_states["2026-06-19T14:03:00Z"]["step5"]["state"]
        step5_0704 = persisted_states["2026-06-19T14:04:00Z"]["step5"]["state"]
        step6_0703 = persisted_states["2026-06-19T14:03:00Z"]["step6"]["state"]
        step6_0704 = persisted_states["2026-06-19T14:04:00Z"]["step6"]["state"]
        step6_0705 = persisted_states["2026-06-19T14:05:00Z"]["step6"]["state"]

        self.assertEqual(step5_0702["leg2_status"], "CONFIRMED")
        self.assertEqual(step5_0702["leg2_candle_a_time"], "2026-06-19T14:02:00Z")

        self.assertEqual(status_0703["current_step_label"], "Step 5 (Leg 2 Confirmation)")
        self.assertEqual(step5_0703["leg2_status"], "VALIDATED")
        self.assertEqual(step6_0703["step6_window_candle_index"], 1)

        self.assertEqual(status_0704["current_step_label"], "Step 5 (Leg 2 Confirmation)")
        self.assertEqual(step5_0704["leg2_status"], "VALIDATED")
        self.assertEqual(step6_0704["step6_window_candle_index"], 2)

        # While the Step 6 window is active, lifecycle ownership must stay with the validated continuation.
        self.assertEqual(status_0705["current_step_label"], "Step 5 (Leg 2 Confirmation)")
        self.assertEqual(status_0705["current_pathway_control"], "continuation")
        self.assertEqual(status_0705["sr_rs_context"], "R/S")
        self.assertEqual(status_0705["setup_direction"], "LONG")
        self.assertEqual(step25_0705["reclaim_candle_a"]["timestamp"], "2026-06-19T14:00:00Z")
        self.assertEqual(step4_0705["candle_a"]["timestamp"], "2026-06-19T14:00:00Z")
        self.assertEqual(step4_0705["candle_b"]["timestamp"], "2026-06-19T14:01:00Z")
        self.assertTrue(step4_0705["leg1_state_locked"])
        self.assertEqual(step5_0704["leg2_status"], "VALIDATED")
        self.assertEqual(step6_0705["step6_window_candle_index"], 3)

    def test_nq_2026_06_19_rs_step6_evaluates_entry_models_on_candles_1_to_4(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        originals = {
            "STATE_PATH": entry_agent.STATE_PATH,
            "TV_CONTEXT_PATH": entry_agent.TV_CONTEXT_PATH,
            "TV_CONTEXT_BY_SYMBOL_PATH": entry_agent.TV_CONTEXT_BY_SYMBOL_PATH,
            "RITHMIC_ATR_SNAPSHOT_PATH": entry_agent.RITHMIC_ATR_SNAPSHOT_PATH,
            "PERSISTENCE_STATE_PATH": entry_agent.PERSISTENCE_STATE_PATH,
            "EXECUTOR_STATE_PATH": entry_agent.EXECUTOR_STATE_PATH,
            "ENTRY_AGENT_AUDIT_DIR": entry_agent.ENTRY_AGENT_AUDIT_DIR,
            "get_latest_market_snapshot": entry_agent.get_latest_market_snapshot,
            "recent_closed_bars": entry_agent.recent_closed_bars,
            "append_entry_agent_audit_row": entry_agent.append_entry_agent_audit_row,
        }
        for name, value in originals.items():
            self.addCleanup(setattr, entry_agent, name, value)

        candle_rows = [
            ("2026-06-19T13:30:00Z", 30644.0, 30678.25, 30640.75, 30659.75),
            ("2026-06-19T13:31:00Z", 30659.0, 30661.25, 30646.5, 30660.25),
            ("2026-06-19T13:32:00Z", 30661.0, 30661.0, 30648.0, 30653.0),
            ("2026-06-19T13:33:00Z", 30651.75, 30651.75, 30637.75, 30642.75),
            ("2026-06-19T13:34:00Z", 30642.25, 30646.75, 30631.75, 30645.75),
            ("2026-06-19T13:35:00Z", 30647.0, 30663.5, 30645.75, 30660.25),
            ("2026-06-19T13:36:00Z", 30661.75, 30670.5, 30657.25, 30666.5),
            ("2026-06-19T13:37:00Z", 30667.25, 30675.75, 30664.5, 30664.5),
            ("2026-06-19T13:38:00Z", 30663.75, 30675.0, 30657.25, 30667.75),
            ("2026-06-19T13:39:00Z", 30667.75, 30667.75, 30659.0, 30663.75),
            ("2026-06-19T13:40:00Z", 30663.75, 30673.0, 30663.5, 30667.0),
            ("2026-06-19T13:41:00Z", 30666.5, 30668.0, 30655.75, 30658.75),
            ("2026-06-19T13:42:00Z", 30659.25, 30660.75, 30651.25, 30659.75),
            ("2026-06-19T13:43:00Z", 30661.0, 30664.75, 30653.75, 30664.75),
            ("2026-06-19T13:44:00Z", 30664.0, 30668.75, 30645.5, 30650.75),
            ("2026-06-19T13:45:00Z", 30651.75, 30662.0, 30642.25, 30661.25),
            ("2026-06-19T13:46:00Z", 30660.5, 30672.25, 30660.5, 30671.75),
            ("2026-06-19T13:47:00Z", 30672.25, 30680.0, 30668.0, 30671.75),
            ("2026-06-19T13:48:00Z", 30670.0, 30670.0, 30659.0, 30667.25),
            ("2026-06-19T13:49:00Z", 30668.5, 30671.5, 30660.0, 30671.0),
            ("2026-06-19T13:50:00Z", 30671.25, 30674.75, 30664.0, 30672.5),
            ("2026-06-19T13:51:00Z", 30671.25, 30679.5, 30667.75, 30674.0),
            ("2026-06-19T13:52:00Z", 30673.5, 30676.5, 30664.5, 30666.25),
            ("2026-06-19T13:53:00Z", 30668.5, 30673.75, 30666.0, 30673.75),
            ("2026-06-19T13:54:00Z", 30673.5, 30679.0, 30670.75, 30673.5),
            ("2026-06-19T13:55:00Z", 30669.75, 30676.25, 30669.0, 30675.25),
            ("2026-06-19T13:56:00Z", 30675.25, 30695.75, 30675.25, 30686.25),
            ("2026-06-19T13:57:00Z", 30685.0, 30693.5, 30683.0, 30686.75),
            ("2026-06-19T13:58:00Z", 30685.75, 30687.75, 30680.75, 30684.5),
            ("2026-06-19T13:59:00Z", 30685.0, 30686.75, 30678.0, 30682.75),
            ("2026-06-19T14:00:00Z", 30682.25, 30684.75, 30664.25, 30668.25),
            ("2026-06-19T14:01:00Z", 30666.5, 30668.5, 30657.75, 30665.0),
            ("2026-06-19T14:02:00Z", 30666.25, 30669.75, 30653.25, 30653.5),
            ("2026-06-19T14:03:00Z", 30655.0, 30675.5, 30653.5, 30673.25),
            ("2026-06-19T14:04:00Z", 30671.75, 30680.5, 30671.25, 30677.75),
            ("2026-06-19T14:05:00Z", 30679.25, 30682.0, 30669.0, 30669.75),
            ("2026-06-19T14:06:00Z", 30670.0, 30674.25, 30664.0, 30672.75),
        ]
        candles = [
            {"timestamp": ts, "open": open_, "high": high, "low": low, "close": close}
            for ts, open_, high, low, close in candle_rows
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "atr.json"
            entry_agent.PERSISTENCE_STATE_PATH = temp_path / "persistence_state.json"
            entry_agent.EXECUTOR_STATE_PATH = temp_path / "executor_state.json"
            entry_agent.ENTRY_AGENT_AUDIT_DIR = temp_path / "entry_agent_audit"
            entry_agent.PERSISTENCE_STATE_PATH.write_text(json.dumps({"trades": {}}), encoding="utf-8")
            entry_agent.EXECUTOR_STATE_PATH.write_text(json.dumps({"orders": {}}), encoding="utf-8")
            entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
            cursor = {"index": 0}

            def market_snapshot(_symbol):
                candle = candles[cursor["index"]]
                return {
                    "source": "test",
                    "symbol": "NQ",
                    "latest_price": candle["close"],
                    "latest_bar_time": candle["timestamp"],
                    "ohlc_is_closed": True,
                    "ohlc": candle,
                }

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol, limit=120: candles[: cursor["index"] + 1][-limit:]
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "normalized_symbol": "NQ",
                                "locked": True,
                                "liquidity_context_locked": True,
                                "liquidity_context_locked_at": "2026-06-19T13:15:00Z",
                                "liquidity_context_source": "tradingview_level_helper",
                                "atr_1m_14": 40.0,
                                "daily_atr14": 500.0,
                                "levels": {
                                    "LH": {"price": 30666.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                                    "PMH": {"price": 30670.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                                    "ONH": {"price": 30770.75, "status": "ACTIVE", "stack_group": "HIGH 2"},
                                    "YH": {"price": 30783.25, "status": "ACTIVE", "stack_group": "HIGH 2"},
                                    "PML": {"price": 30397.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "LL": {"price": 30291.25, "status": "ACTIVE", "stack_group": "NONE"},
                                    "ONL": {"price": 30291.25, "status": "ACTIVE", "stack_group": "NONE"},
                                    "YL": {"price": 30125.75, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            persisted_states = {}
            for index, candle in enumerate(candles):
                cursor["index"] = index
                entry_agent.build_entry_status("NQ")
                persisted_states[candle["timestamp"]] = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))["state_by_symbol"]["NQ"]

        for ts, expected_index in (
            ("2026-06-19T14:03:00Z", 1),
            ("2026-06-19T14:04:00Z", 2),
            ("2026-06-19T14:05:00Z", 3),
            ("2026-06-19T14:06:00Z", 4),
        ):
            step6 = persisted_states[ts]["step6"]
            state = step6["state"]
            models = state["step6_entry_models"]
            self.assertEqual(state["step6_window_candle_index"], expected_index)
            self.assertTrue(models["large_wick_sweep"]["evaluated"])
            self.assertTrue(models["small_wick_sweep"]["evaluated"])
            self.assertTrue(models["double_wick_rejection"]["evaluated"])

        self.assertEqual(
            persisted_states["2026-06-19T14:03:00Z"]["step6"]["reason"],
            "Phase 1 Candle 1: entry models evaluated; no valid entry yet.",
        )
        self.assertEqual(
            persisted_states["2026-06-19T14:04:00Z"]["step6"]["reason"],
            "Phase 1 Candle 2: entry models evaluated; no valid entry yet.",
        )
        self.assertEqual(
            persisted_states["2026-06-19T14:05:00Z"]["step6"]["reason"],
            "Phase 1 Candle 3: entry models evaluated; no valid entry yet.",
        )
        self.assertEqual(
            persisted_states["2026-06-19T14:06:00Z"]["step6"]["reason"],
            "Phase 1 failed on Candle 4 with no valid Phase 2 failed-entry participation.",
        )

    def test_step2_pending_probe_wait_reason_uses_actionable_wick_boundary_when_present(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        originals = {
            "STATE_PATH": entry_agent.STATE_PATH,
            "TV_CONTEXT_PATH": entry_agent.TV_CONTEXT_PATH,
            "TV_CONTEXT_BY_SYMBOL_PATH": entry_agent.TV_CONTEXT_BY_SYMBOL_PATH,
            "RITHMIC_ATR_SNAPSHOT_PATH": entry_agent.RITHMIC_ATR_SNAPSHOT_PATH,
            "PERSISTENCE_STATE_PATH": entry_agent.PERSISTENCE_STATE_PATH,
            "EXECUTOR_STATE_PATH": entry_agent.EXECUTOR_STATE_PATH,
            "ENTRY_AGENT_AUDIT_DIR": entry_agent.ENTRY_AGENT_AUDIT_DIR,
            "get_latest_market_snapshot": entry_agent.get_latest_market_snapshot,
            "recent_closed_bars": entry_agent.recent_closed_bars,
        }
        for name, value in originals.items():
            self.addCleanup(setattr, entry_agent, name, value)

        candle_rows = [
            ("2026-06-19T13:30:00Z", 30644.0, 30678.25, 30640.75, 30659.75),
            ("2026-06-19T13:31:00Z", 30659.0, 30661.25, 30646.5, 30660.25),
            ("2026-06-19T13:32:00Z", 30661.0, 30661.0, 30648.0, 30653.0),
            ("2026-06-19T13:33:00Z", 30651.75, 30651.75, 30637.75, 30642.75),
            ("2026-06-19T13:34:00Z", 30642.25, 30646.75, 30631.75, 30645.75),
            ("2026-06-19T13:35:00Z", 30647.0, 30663.5, 30645.75, 30660.25),
            ("2026-06-19T13:36:00Z", 30661.75, 30670.5, 30657.25, 30666.5),
            ("2026-06-19T13:37:00Z", 30667.25, 30675.75, 30664.5, 30664.5),
            ("2026-06-19T13:38:00Z", 30663.75, 30675.0, 30657.25, 30667.75),
            ("2026-06-19T13:39:00Z", 30667.75, 30667.75, 30659.0, 30663.75),
            ("2026-06-19T13:40:00Z", 30663.75, 30673.0, 30663.5, 30667.0),
        ]
        candles = [
            {"timestamp": ts, "open": open_, "high": high, "low": low, "close": close}
            for ts, open_, high, low, close in candle_rows
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "atr.json"
            entry_agent.PERSISTENCE_STATE_PATH = temp_path / "persistence_state.json"
            entry_agent.EXECUTOR_STATE_PATH = temp_path / "executor_state.json"
            entry_agent.ENTRY_AGENT_AUDIT_DIR = temp_path / "entry_agent_audit"
            entry_agent.PERSISTENCE_STATE_PATH.write_text(json.dumps({"trades": {}}), encoding="utf-8")
            entry_agent.EXECUTOR_STATE_PATH.write_text(json.dumps({"orders": {}}), encoding="utf-8")
            cursor = {"index": 0}

            def market_snapshot(_symbol):
                candle = candles[cursor["index"]]
                return {
                    "source": "test",
                    "symbol": "NQM6",
                    "latest_price": candle["close"],
                    "latest_bar_time": candle["timestamp"],
                    "ohlc_is_closed": True,
                    "ohlc": candle,
                }

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol, limit=2: candles[: cursor["index"] + 1][-limit:]
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "normalized_symbol": "NQ",
                                "locked": True,
                                "context_locked": True,
                                "locked_for_day": True,
                                "session_locked": True,
                                "liquidity_context_locked": True,
                                "liquidity_context_locked_at": "2026-06-19T13:15:00Z",
                                "liquidity_context_source": "tradingview_level_helper",
                                "daily_atr14": 711.0385125891,
                                "levels": {
                                    "LH": {"price": 30666.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                                    "PMH": {"price": 30670.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                                    "ONH": {"price": 30770.75, "status": "ACTIVE", "stack_group": "HIGH 2"},
                                    "YH": {"price": 30783.25, "status": "ACTIVE", "stack_group": "HIGH 2"},
                                    "PML": {"price": 30525.25, "status": "ACTIVE", "stack_group": "LOW 1"},
                                    "LL": {"price": 30535.75, "status": "ACTIVE", "stack_group": "LOW 1"},
                                    "ONL": {"price": 30388.0, "status": "ACTIVE", "stack_group": "LOW 2"},
                                    "YL": {"price": 30391.0, "status": "ACTIVE", "stack_group": "LOW 2"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            observed = {}
            for index, candle in enumerate(candles):
                cursor["index"] = index
                observed[candle["timestamp"]] = entry_agent.build_entry_status("NQ")

        for timestamp in (
            "2026-06-19T13:36:00Z",
            "2026-06-19T13:37:00Z",
            "2026-06-19T13:38:00Z",
            "2026-06-19T13:39:00Z",
            "2026-06-19T13:40:00Z",
        ):
            status = observed[timestamp]
            self.assertEqual(status["current_step"], "Step 2")
            self.assertEqual(status["current_step_status"], "WAIT")
            self.assertEqual(status["extreme_boundary"], 30670.0)
            self.assertEqual(status["wick_boundary_extreme"], 30678.25)
            self.assertNotIn("actionable_boundary_price", status)
            self.assertIn("30678.25", status["wait_reason"])
            self.assertNotIn("30670.0", status["wait_reason"])
            self.assertNotIn("30670.5", status["wait_reason"])
            self.assertNotIn("30675.75", status["wait_reason"])

    def test_step2_wait_status_cannot_publish_confirmation_text(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        self.addCleanup(setattr, entry_agent, "run_once", original_run_once)

        snapshot = {
            "requested_symbol": "NQ",
            "normalized_symbol": "NQ",
            "latest_price": 30660.25,
            "latest_bar_time": "2026-06-19T13:35:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 30647.0, "high": 30663.5, "low": 30645.75, "close": 30660.25},
            "liquidity": {"tick_size": 0.25},
            "step_2_1a": {
                "step_2_activated": False,
                "candle_a": None,
                "active_level": "PMH",
                "level_price": 30670.0,
                "side": "upper",
                "active_liquidity_group": {
                    "name": "HIGH 1",
                    "display_name": "LH/PMH Liquidity",
                    "components": ["LH", "PMH"],
                    "side": "upper",
                    "close_boundary": 30666.0,
                    "extreme_boundary": 30678.25,
                },
                "last_interacted_liquidity": {
                    "name": "PMH",
                    "price": 30670.0,
                    "display_name": "LH/PMH Liquidity",
                    "side": "upper",
                },
            },
            "rejection": {"rejection_mode": "OFF"},
            "step25": {"status": "WAIT", "next_step": "Step 2.5", "state": {}},
            "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
            "step4": {"status": "WAIT", "next_step": "Step 4", "state": {}},
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        entry_agent.run_once = lambda _symbol="NQ", persist=True: copy.deepcopy(snapshot)

        status = entry_agent.build_entry_status("NQ")

        self.assertEqual(status["current_step"], "Step 2")
        self.assertEqual(status["current_step_status"], "WAIT")
        self.assertIn("waiting", status["wait_reason"].lower())
        self.assertNotIn("confirmed", status["wait_reason"].lower())

    def test_observation_window_low_stack_updates_wick_boundary_extreme_in_status(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        self.addCleanup(setattr, entry_agent, "run_once", original_run_once)

        snapshot = {
            "requested_symbol": "YM",
            "normalized_symbol": "YM",
            "latest_price": 51940.0,
            "latest_bar_time": "2026-06-24T13:24:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 51970.0, "high": 51974.0, "low": 51933.0, "close": 51940.0},
            "liquidity": {"tick_size": 1.0},
            "tv_context": {
                "locked": True,
                "context_locked": True,
                "locked_for_day": True,
                "levels": {
                    "ONL": {"price": 51961.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                    "LL": {"price": 51965.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                    "PML": {"price": 51984.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                },
            },
            "pre_open_observed_extreme": {"price": 51933.0, "side": "lower", "stack_group": "LOW 1"},
            "step_2_1a": {"step_2_activated": False, "events": []},
            "rejection": {"rejection_mode": "OFF"},
            "step25": {"status": "WAIT", "next_step": "Step 2.5", "state": {}},
            "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
            "step4": {"status": "WAIT", "next_step": "Step 4", "state": {}},
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        entry_agent.run_once = lambda _symbol="YM", persist=True: copy.deepcopy(snapshot)

        status = entry_agent.build_entry_status("YM")

        self.assertEqual(status["close_boundary"], 51984.0)
        self.assertEqual(status["extreme_boundary"], 51961.0)
        self.assertEqual(status["wick_boundary_extreme"], 51933.0)
        self.assertNotIn("actionable_boundary_price", status)
        self.assertEqual(status["frozen_tv_level"], 51984.0)
        self.assertEqual(status["active_liquidity_group"]["extreme_boundary"], 51961.0)
        self.assertEqual(status["active_liquidity_group"]["wick_boundary_extreme"], 51933.0)
        self.assertEqual(status["active_liquidity_group"]["close_boundary"], 51984.0)

    def test_observation_window_high_stack_updates_wick_boundary_extreme_in_status(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        self.addCleanup(setattr, entry_agent, "run_once", original_run_once)

        snapshot = {
            "requested_symbol": "NQ",
            "normalized_symbol": "NQ",
            "latest_price": 22220.0,
            "latest_bar_time": "2026-06-24T13:24:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 22202.0, "high": 22240.0, "low": 22198.0, "close": 22220.0},
            "liquidity": {"tick_size": 0.25},
            "tv_context": {
                "locked": True,
                "context_locked": True,
                "locked_for_day": True,
                "levels": {
                    "PMH": {"price": 22210.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "LH": {"price": 22205.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "ONH": {"price": 22230.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                },
            },
            "pre_open_observed_extreme": {"price": 22240.0, "side": "upper", "stack_group": "HIGH 1"},
            "step_2_1a": {"step_2_activated": False, "events": []},
            "rejection": {"rejection_mode": "OFF"},
            "step25": {"status": "WAIT", "next_step": "Step 2.5", "state": {}},
            "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
            "step4": {"status": "WAIT", "next_step": "Step 4", "state": {}},
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        entry_agent.run_once = lambda _symbol="NQ", persist=True: copy.deepcopy(snapshot)

        status = entry_agent.build_entry_status("NQ")

        self.assertEqual(status["close_boundary"], 22205.0)
        self.assertEqual(status["extreme_boundary"], 22230.0)
        self.assertEqual(status["wick_boundary_extreme"], 22240.0)
        self.assertNotIn("actionable_boundary_price", status)
        self.assertEqual(status["frozen_tv_level"], 22205.0)
        self.assertEqual(status["active_liquidity_group"]["extreme_boundary"], 22230.0)
        self.assertEqual(status["active_liquidity_group"]["wick_boundary_extreme"], 22240.0)
        self.assertEqual(status["active_liquidity_group"]["close_boundary"], 22205.0)

    def test_post_0630_low_stack_updates_wick_boundary_extreme_and_wait_reason_uses_actionable_boundary(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        originals = {
            "STATE_PATH": entry_agent.STATE_PATH,
            "TV_CONTEXT_PATH": entry_agent.TV_CONTEXT_PATH,
            "TV_CONTEXT_BY_SYMBOL_PATH": entry_agent.TV_CONTEXT_BY_SYMBOL_PATH,
            "RITHMIC_ATR_SNAPSHOT_PATH": entry_agent.RITHMIC_ATR_SNAPSHOT_PATH,
            "PERSISTENCE_STATE_PATH": entry_agent.PERSISTENCE_STATE_PATH,
            "EXECUTOR_STATE_PATH": entry_agent.EXECUTOR_STATE_PATH,
            "ENTRY_AGENT_AUDIT_DIR": entry_agent.ENTRY_AGENT_AUDIT_DIR,
            "get_latest_market_snapshot": entry_agent.get_latest_market_snapshot,
            "recent_closed_bars": entry_agent.recent_closed_bars,
        }
        for name, value in originals.items():
            self.addCleanup(setattr, entry_agent, name, value)

        candle = {"timestamp": "2026-06-24T13:31:00Z", "open": 51986.0, "high": 51990.0, "low": 51933.0, "close": 51970.0}

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "atr.json"
            entry_agent.PERSISTENCE_STATE_PATH = temp_path / "persistence_state.json"
            entry_agent.EXECUTOR_STATE_PATH = temp_path / "executor_state.json"
            entry_agent.ENTRY_AGENT_AUDIT_DIR = temp_path / "entry_agent_audit"
            entry_agent.PERSISTENCE_STATE_PATH.write_text(json.dumps({"trades": {}}), encoding="utf-8")
            entry_agent.EXECUTOR_STATE_PATH.write_text(json.dumps({"orders": {}}), encoding="utf-8")
            entry_agent.get_latest_market_snapshot = lambda _symbol: {
                "source": "test",
                "symbol": "YMM6",
                "latest_price": candle["close"],
                "latest_bar_time": candle["timestamp"],
                "ohlc_is_closed": True,
                "ohlc": candle,
            }
            entry_agent.recent_closed_bars = lambda _symbol, limit=2: [candle][-limit:]
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "YM": {
                                "symbol": "YM1!",
                                "normalized_symbol": "YM",
                                "locked": True,
                                "context_locked": True,
                                "locked_for_day": True,
                                "session_locked": True,
                                "liquidity_context_locked": True,
                                "levels": {
                                    "ONL": {"price": 51961.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                                    "LL": {"price": 51965.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                                    "PML": {"price": 51984.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            status = entry_agent.build_entry_status("YM")

        self.assertEqual(status["close_boundary"], 51984.0)
        self.assertEqual(status["extreme_boundary"], 51961.0)
        self.assertEqual(status["wick_boundary_extreme"], 51933.0)
        self.assertNotIn("actionable_boundary_price", status)
        self.assertEqual(status["active_liquidity_group"]["extreme_boundary"], 51961.0)
        self.assertEqual(status["active_liquidity_group"]["wick_boundary_extreme"], 51933.0)
        self.assertIn("51933.0", status["wait_reason"])
        self.assertNotIn("51961.0", status["wait_reason"])

    def test_high_side_confirmation_without_wick_beyond_extreme_publishes_no_wick_boundary(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        self.addCleanup(setattr, entry_agent, "run_once", original_run_once)

        snapshot = {
            "requested_symbol": "YM",
            "normalized_symbol": "YM",
            "latest_price": 52180.0,
            "latest_bar_time": "2026-06-24T13:50:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 52172.0, "high": 52176.0, "low": 52168.0, "close": 52180.0},
            "liquidity": {"tick_size": 1.0},
            "step_2_1a": {
                "step_2_activated": True,
                "active_level": "PMH",
                "level_price": 52176.0,
                "side": "upper",
                "active_liquidity_group": {
                    "name": "HIGH 1",
                    "display_name": "PMH Liquidity",
                    "components": ["PMH"],
                    "side": "upper",
                    "close_boundary": 52176.0,
                    "extreme_boundary": 52176.0,
                    "wick_boundary_extreme": None,
                },
                "step2_locked_owner": {
                    "pathway": "rejection",
                    "active_liquidity_name": "PMH",
                    "active_liquidity_price": 52176.0,
                    "active_liquidity_display_name": "PMH Liquidity",
                    "active_liquidity_group": {
                        "name": "HIGH 1",
                        "display_name": "PMH Liquidity",
                        "components": ["PMH"],
                        "side": "upper",
                        "close_boundary": 52176.0,
                        "extreme_boundary": 52176.0,
                        "wick_boundary_extreme": None,
                    },
                    "close_boundary": 52176.0,
                    "extreme_boundary": 52176.0,
                    "wick_boundary_extreme": None,
                },
            },
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 52176.0},
            "step25": {"status": "WAIT", "next_step": "Step 2.5", "state": {}},
            "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
            "step4": {"status": "WAIT", "next_step": "Step 4", "state": {}},
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        entry_agent.run_once = lambda _symbol="YM", persist=True: copy.deepcopy(snapshot)

        status = entry_agent.build_entry_status("YM")

        self.assertEqual(status["close_boundary"], 52176.0)
        self.assertEqual(status["extreme_boundary"], 52176.0)
        self.assertIsNone(status["wick_boundary_extreme"])
        self.assertEqual(status["current_step"], "Step 2")
        self.assertEqual(status["current_step_status"], "CONFIRMED")
        self.assertIsNone(status["active_liquidity_group"]["wick_boundary_extreme"])

    def test_wick_boundary_does_not_carry_into_new_owner_with_different_original_extreme(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        persisted_group = {
            "name": "HIGH 1",
            "display_name": "PMH Liquidity",
            "components": ["PMH"],
            "side": "upper",
            "close_boundary": 52176.0,
            "extreme_boundary": 52176.0,
            "wick_boundary_extreme": 52190.0,
        }
        new_owner_group = {
            "name": "HIGH 1",
            "display_name": "ONH Liquidity",
            "components": ["ONH"],
            "side": "upper",
            "close_boundary": 52210.0,
            "extreme_boundary": 52210.0,
            "wick_boundary_extreme": None,
        }

        merged = entry_agent.merge_monotonic_stack_extreme(new_owner_group, persisted_group)

        self.assertEqual(merged["extreme_boundary"], 52210.0)
        self.assertIsNone(merged["wick_boundary_extreme"])

    def test_rs_continuation_projection_has_one_authoritative_long_direction(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_run_once = entry_agent.run_once
        original_state_path = entry_agent.STATE_PATH
        self.addCleanup(setattr, entry_agent, "run_once", original_run_once)
        self.addCleanup(setattr, entry_agent, "STATE_PATH", original_state_path)

        active_liquidity = {"name": "PMH", "display_name": "PMH", "price": 28937.75, "side": "upper"}
        reclaim = {"timestamp": "2026-05-19T13:42:00Z", "open": 28953.0, "high": 28965.5, "low": 28928.0, "close": 28929.25}
        leg1 = {"timestamp": "2026-05-19T13:43:00Z", "open": 28929.0, "high": 28952.25, "low": 28919.25, "close": 28944.5}
        snapshot = {
            "requested_symbol": "NQ",
            "normalized_symbol": "NQ",
            "latest_price": 28944.5,
            "latest_bar_time": leg1["timestamp"],
            "ohlc_is_closed": True,
            "ohlc": {key: leg1[key] for key in ("open", "high", "low", "close")},
            "liquidity": {
                "active_level": "PMH",
                "active_price": 28937.75,
                "nearest_level_above": {"name": "LH", "price": 29117.0},
                "nearest_level_below": {"name": "PMH", "price": 28937.75},
                "tick_size": 0.25,
            },
            "step_2_1a": {
                "step_2_activated": True,
                "active_level": "PMH",
                "level_price": 28937.75,
                "candle_a": {"timestamp": "2026-05-19T13:32:00Z", "open": 28940.75, "high": 28981.75, "low": 28930.25, "close": 28969.75},
                "step2_locked_owner": {
                    "pathway": "rejection",
                    "active_liquidity": active_liquidity,
                    "active_liquidity_name": "PMH",
                    "active_liquidity_price": 28937.75,
                    "setup_direction": "SHORT",
                },
            },
            "rejection": {"rejection_mode": "ON", "watch_side": "SHORT", "trigger_level": "PMH", "trigger_price": 28937.75},
            "step25": {
                "status": "READY",
                "next_step": "Step 3",
                "state": {
                    "controlling_mode": "R/S",
                    "candidate_modes": ["R/S"],
                    "continuation_step2_activated": True,
                    "pathway_activation_type": "close",
                    "reclaim_candle_a": reclaim,
                    "initial_candle_a": reclaim,
                    "pathway_level": 28937.75,
                    "step25_pathway_selection_complete": True,
                },
            },
            "step3": {"status": "ALLOW_STEP_4", "next_step": "Step 4", "state": {"active_liquidity": active_liquidity}},
            "step4": {
                "status": "READY",
                "next_step": "Step 5",
                "reason": "Leg 1 complete.",
                "state": {
                    "controlling_mode": "R/S",
                    "current_pathway_control": "continuation",
                    "current_controlling_mode": "R/S",
                    "current_continuation_type": "R/S",
                    "shared_leg1_uses_initial_candle_a": True,
                    "setup_direction": "LONG",
                    "active_liquidity": active_liquidity,
                    "initial_candle_a": reclaim,
                    "candle_a": reclaim,
                    "candle_b": leg1,
                    "leg1_status": "COMPLETE",
                    "leg1_state_locked": True,
                    "leg1_completed_at": leg1["timestamp"],
                    "leg1_reference_price": reclaim["close"],
                    "leg1_reference_candle_time": reclaim["timestamp"],
                },
            },
            "step5": {"status": "WAIT", "state": {}, "next_step": "Step 5", "reason": "Waiting."},
            "step6": {"status": "WAIT", "state": {}, "next_step": "Step 6", "reason": "Waiting."},
        }
        entry_agent.run_once = lambda _symbol="NQ", persist=True: copy.deepcopy(snapshot)

        with tempfile.TemporaryDirectory() as temp_dir:
            entry_agent.STATE_PATH = Path(temp_dir) / "entry_agent_state.json"
            entry_agent.STATE_PATH.write_text(
                json.dumps({"state_by_symbol": {"NQ": {"consumed_liquidity_levels": [], "consumed_entry_setups": []}}}),
                encoding="utf-8",
            )
            status = entry_agent.build_entry_status("NQ")
            persisted_symbol_state = json.loads(entry_agent.STATE_PATH.read_text(encoding="utf-8"))["state_by_symbol"]["NQ"]

        self.assertEqual(persisted_symbol_state["consumed_liquidity_levels"], [])
        self.assertEqual(persisted_symbol_state["consumed_entry_setups"], [])

        self.assertEqual(status["selected_pathway"], "continuation")
        self.assertEqual(status["current_pathway_control"], "continuation")
        self.assertEqual(status["sr_rs_context"], "R/S")
        self.assertEqual(status["setup_direction"], "LONG")
        self.assertEqual(status["continuation_side"]["setup_direction"], "LONG")
        self.assertEqual(status["continuation_side"]["selected_pathway"], "continuation")
        self.assertEqual(status["continuation_side"]["pathway_status"], "controlling")
        self.assertNotEqual(status["rejection_side"]["setup_direction"], "SHORT")
        self.assertIsNone(status["rejection_side"]["entry_status"])
        # Frozen rejection Step 2 remains visible while continuation controls.
        self.assertEqual(status["rejection_side"]["current_step"], "Step 2")
        self.assertEqual(status["rejection_side"]["pathway_status"], "frozen")

    def test_rs_continuation_641_647_root_brain_contract(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import dry_run_injector
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        symbol = "NQ"
        tv_context = {
            "symbol": "NQ1!",
            "normalized_symbol": "NQ",
            "locked": True,
            "atr_1m_14": 40.0,
            "daily_atr14": 500.0,
            "levels": {
                "PMH": {"price": 28937.75, "status": "ACTIVE", "stack_group": "NONE"},
                "PML": {"price": 28700.0, "status": "ACTIVE", "stack_group": "NONE"},
                "ONH": {"price": 29150.0, "status": "ACTIVE", "stack_group": "NONE"},
                "ONL": {"price": 28600.0, "status": "ACTIVE", "stack_group": "NONE"},
            },
        }
        candles = dry_run_injector.build_scenario(symbol, "rs_continuation_641_647", tv_context)

        original_context = dry_run_injector.entry_agent.load_tv_context
        self.addCleanup(setattr, dry_run_injector.entry_agent, "load_tv_context", original_context)
        dry_run_injector.entry_agent.load_tv_context = lambda _symbol="NQ": copy.deepcopy(tv_context)

        with dry_run_injector.isolated_entry_agent_state(symbol) as state_path:
            dry_run_injector.seed_completed_pmh_rejection_state(state_path, symbol, 28937.75)
            statuses = dry_run_injector.run_dry_run(symbol, candles, scenario=None)

        status_1341 = statuses[0]
        self.assertEqual(status_1341["selected_pathway"], "rejection")
        self.assertEqual(status_1341["sr_rs_context"], "Normal Rejection Mode")
        self.assertEqual(status_1341["current_step"], "Step 6")
        self.assertEqual(status_1341["entry_status"], "CONFIRM")
        self.assertEqual(status_1341["rejection_side"]["entry_status"], "CONFIRM")
        self.assertEqual(status_1341["rejection_side"]["pathway_status"], "entered")
        self.assertNotEqual(status_1341["rejection_side"]["current_step"], "Step 5")
        self.assertNotEqual(status_1341["wait_reason"], "Leg 2 already validated; Step 6 handoff remains active.")
        self.assertIsNone(status_1341["continuation_side"]["current_step"])
        self.assertNotEqual(status_1341["selected_pathway"], "continuation")

        status_1342 = statuses[1]
        self.assertEqual(status_1342["selected_pathway"], "continuation")
        self.assertEqual(status_1342["sr_rs_context"], "R/S")
        self.assertEqual(status_1342["setup_direction"], "LONG")
        self.assertEqual(status_1342["continuation_side"]["pathway_status"], "controlling")
        self.assertEqual(status_1342["rejection_side"]["pathway_status"], "frozen")
        self.assertIsNone(status_1342["rejection_side"]["entry_status"])
        self.assertEqual(status_1342["rejection_side"]["current_step"], "Step 2")
        self.assertEqual(status_1342["consumed_liquidity_levels"], [])
        self.assertEqual(status_1342["current_step_confirmed_at"], "2026-05-19T13:42:00Z")
        # The corrected contract anchors the Leg 1 window to the original Step 2
        # confirmation candle for this sequence, not the later reclaim candle.
        self.assertEqual(status_1342["leg1_window_started_at"], "2026-05-19T13:32:00Z")
        self.assertEqual(status_1342["leg1_window_candle_index"], 1)
        self.assertNotEqual(status_1342["leg1_window_started_at"], "2026-05-19T13:42:00Z")

        status_1343 = statuses[2]
        # After the reclaim sequence, public projection drops back to the Step 2
        # continuation milestone until Step 4 reconfirms on a later candle.
        self.assertEqual(status_1343["current_step"], "Step 2")
        self.assertEqual(status_1343["leg1_state"], "WAIT")
        self.assertEqual(status_1343["selected_pathway"], "continuation")
        self.assertNotEqual(status_1343["rejection_side"]["setup_direction"], "SHORT")
        self.assertEqual(status_1343["rejection_side"]["current_step"], "Step 2")
        self.assertEqual(status_1343["leg1_window_started_at"], "2026-05-19T13:42:00Z")
        self.assertEqual(status_1343["leg1_window_candle_index"], 0)
        self.assertIsNone(status_1343["leg1_reference_candle_time"])
        self.assertNotEqual(status_1343["leg1_reference_price"], 28969.75)
        self.assertIsNone(status_1343["step4_proximity_distance"])
        self.assertIsNone(status_1343["step4_proximity_atr_threshold"])

        status_1344 = statuses[3]
        self.assertEqual(status_1344["current_step"], "Step 4")
        self.assertEqual(status_1344["leg2_state"], "WAIT")
        self.assertEqual(status_1344["setup_direction"], "LONG")
        self.assertFalse(status_1344["step6_window_active"])
        self.assertIsNone(status_1344["step6_window_started_at"])
        self.assertIsNone(status_1344["step6_window_candle_index"])
        self.assertIsNone(status_1344["step6_window_remaining"])
        self.assertIsNone(status_1344["step6_window_expires_at"])

        status_1345 = statuses[4]
        # Under the corrected daily-ATR proximity contract, public projection
        # falls back to the Step 2 continuation milestone here until Step 4
        # reconfirms on a later candle.
        self.assertEqual(status_1345["current_step"], "Step 2")
        self.assertEqual(status_1345["entry_status"], "WAIT")
        self.assertIsNone(status_1345["entry_type_number"])
        self.assertIsNone(status_1345["entry_type_name"])
        self.assertIsNone(status_1345["entry_model"])
        self.assertIn("Step 2 confirmed", status_1345["last_decision"])
        self.assertFalse(status_1345["step6_window_active"])
        self.assertIsNone(status_1345["step6_window_started_at"])
        self.assertIsNone(status_1345["step6_window_candle_index"])
        self.assertIsNone(status_1345["step6_window_remaining"])
        self.assertEqual(status_1345["selected_pathway"], "continuation")
        self.assertEqual(status_1345["setup_direction"], "LONG")
        self.assertNotEqual(status_1345["rejection_side"]["setup_direction"], "SHORT")
        self.assertIsNone(status_1345["rejection_side"]["entry_status"])
        self.assertEqual(status_1345["rejection_side"]["current_step"], "Step 2")

    def test_step6_window_expiration_publishes_past_step5_gate(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        snapshot = {
            "latest_price": 50611.0,
            "latest_bar_time": "2026-05-28T13:49:00Z",
            "ohlc_is_closed": True,
            "step6": {
                "step": "Step 7",
                "status": "TERMINATED",
                "reason": "Phase 1 failed on Candle 4 with no valid Phase 2 failed-entry participation.",
                "state": {
                    "terminated_by": "Step 6",
                    "step6_window_active": False,
                    "step6_window_started_at": "2026-05-28T13:45:00Z",
                    "step6_window_candle_index": 4,
                    "step6_window_remaining": 0,
                    "step6_window_expires_at": "2026-05-28T13:49:00Z",
                },
            },
            "step5": {
                "step": "Step 5",
                "status": "READY",
                "next_step": "Step 6",
                "state": {
                    "leg2_status": "VALIDATED",
                    "step5_participation_validated": True,
                    "leg2_candidate_candle_time": "2026-05-28T13:46:00Z",
                    "step6_window_active": True,
                    "step6_window_started_at": "2026-05-28T13:45:00Z",
                    "step6_window_candle_index": 4,
                    "step6_window_remaining": 0,
                    "step6_window_expires_at": "2026-05-28T13:49:00Z",
                },
            },
            "step4": {
                "step": "Step 4",
                "status": "READY",
                "next_step": "Step 5",
                "state": {
                    "leg1_status": "COMPLETE",
                    "leg1_state_locked": True,
                    "setup_direction": "SHORT",
                    "active_liquidity": {"name": "ONL", "price": 50576.0, "side": "lower"},
                    "leg1_reference_price": 50578.0,
                    "leg1_reference_candle_time": "2026-05-28T13:43:00Z",
                    "leg1_completed_at": "2026-05-28T13:44:00Z",
                    "candle_a": {"timestamp": "2026-05-28T13:43:00Z"},
                    "candle_b": {"timestamp": "2026-05-28T13:44:00Z"},
                },
            },
            "step3": {},
        }

        self.assertEqual(entry_agent.current_step_from_snapshot(snapshot), "Step 5")
        public_invalidation = entry_agent.public_invalidation_from_results(
            "Step 6",
            snapshot["step4"],
            snapshot["step5"],
            snapshot["step6"],
        )
        self.assertEqual(public_invalidation["source_step"], "Step 6")
        self.assertIn("Candle 4", public_invalidation["reason"])

    def test_step4_proximity_threshold_uses_daily_atr_not_one_minute_atr(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            from step4_engine import evaluate_step4
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        interaction = {
            "system_state": "REJECTION MODE ON",
            "trade_mode": "ON",
            "rejection_mode": "ON",
            "interaction_state": "ACTIVE",
            "setup_direction": "SHORT",
            "step25_pathway_selection_complete": True,
            "step3_allows_structure": True,
            "controlling_mode": "Normal Rejection Mode",
            "candidate_modes": ["Normal Rejection Mode"],
            "initial_candle_a": {"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5},
            "nearest_opposing_liquidity": {"name": "PML", "price": 95.0},
            "atr_1m_14": 10.0,
            "daily_atr14": 100.0,
            "events": [],
        }
        candle_b = {"open": 100.5, "high": 100.75, "low": 99.0, "close": 100.75}

        result = evaluate_step4(interaction, candle_b)

        self.assertEqual(result["step"], "Step 7")
        self.assertEqual(result["status"], "TERMINATED")
        self.assertEqual(result["state"]["proximity_daily_atr"], 100.0)
        self.assertEqual(result["state"]["proximity_atr_threshold"], 10.0)
        self.assertEqual(result["state"]["proximity_atr_threshold_percent"], 10.0)
        self.assertIn("10% daily ATR", result["reason"])

    def test_nq_644_645_live_status_replay_confirms_shared_leg1(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot
        original_recent_closed_bars = entry_agent.recent_closed_bars
        self.addCleanup(setattr, entry_agent, "STATE_PATH", original_state_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_PATH", original_context_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_BY_SYMBOL_PATH", original_by_symbol_path)
        self.addCleanup(setattr, entry_agent, "RITHMIC_ATR_SNAPSHOT_PATH", original_atr_path)
        self.addCleanup(setattr, entry_agent, "get_latest_market_snapshot", original_market_snapshot)
        self.addCleanup(setattr, entry_agent, "recent_closed_bars", original_recent_closed_bars)

        step2_candle = {
            "open": 100.4,
            "high": 100.5,
            "low": 99.4,
            "close": 99.7,
            "timestamp": "2026-05-18T13:44:00Z",
        }
        participation_candle = {
            "open": 99.65,
            "high": 100.7,
            "low": 99.1,
            "close": 100.25,
            "timestamp": "2026-05-18T13:45:00Z",
        }
        candles = [step2_candle, participation_candle]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "atr.json"
            cursor = {"index": 0}

            def market_snapshot(_symbol):
                candle = candles[cursor["index"]]
                return {
                    "source": "test",
                    "symbol": "NQM6",
                    "latest_price": candle["close"],
                    "latest_bar_time": candle["timestamp"],
                    "ohlc_is_closed": True,
                    "ohlc": candle,
                }

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol, limit=2: candles[: cursor["index"] + 1][-limit:]
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "normalized_symbol": "NQ",
                                "locked": True,
                                "levels": {
                                    "PML": {"price": 100.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "PMH": {"price": 110.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "ONL": {"price": 90.0, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                                "atr_1m_14": 4.0,
                                "daily_atr14": 40.0,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            step2_status = entry_agent.build_entry_status("NQ")
            cursor["index"] = 1
            leg1_status = entry_agent.build_entry_status("NQ")

        self.assertEqual(step2_status["current_step"], "Step 2")
        self.assertEqual(step2_status["current_step_status"], "CONFIRMED")
        self.assertEqual(step2_status["setup_direction"], "LONG")
        self.assertEqual(step2_status["rejection_side"]["setup_direction"], "LONG")
        self.assertIsNone(step2_status["continuation_side"]["setup_direction"])
        self.assertEqual(step2_status["leg1_status"], "WAIT")
        self.assertEqual(step2_status["leg2_status"], "WAIT")
        self.assertEqual(step2_status["entry_status"], "WAIT")

        self.assertEqual(leg1_status["current_step"], "Step 4")
        self.assertEqual(leg1_status["current_step_label"], "Leg 1 Complete")
        self.assertEqual(leg1_status["current_step_status"], "CONFIRMED")
        self.assertEqual(leg1_status["leg1_status"], "COMPLETE")
        self.assertEqual(leg1_status["leg1_state"], "COMPLETE")
        self.assertTrue(leg1_status["leg1_locked"])
        self.assertTrue(leg1_status["leg1_state_locked"])
        self.assertEqual(leg1_status["leg1_confirmed_at"], "2026-05-18T13:45:00Z")
        self.assertEqual(leg1_status["leg1_completed_at"], "2026-05-18T13:45:00Z")
        self.assertEqual(leg1_status["rejection_pathway_status"], "controlling")
        self.assertEqual(leg1_status["rejection_side"]["pathway_status"], "controlling")
        self.assertEqual(leg1_status["rejection_side"]["setup_direction"], "LONG")
        # This fixture never produces a valid continuation sequence because there is
        # no prior close beyond liquidity followed by a reclaim close back across it.
        self.assertEqual(leg1_status["continuation_pathway_status"], "inactive")
        self.assertEqual(leg1_status["continuation_side"]["pathway_status"], "inactive")
        self.assertEqual(leg1_status["continuation_side"]["continuation_type"], "none")
        self.assertIsNone(leg1_status["continuation_side"]["setup_direction"])
        self.assertEqual(leg1_status["leg2_status"], "WAIT")
        self.assertEqual(leg1_status["entry_status"], "WAIT")

    def test_nq_2026_06_12_step4_participation_lines_remain_visible_after_step2(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
            import tv_context_server as server
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_audit_dir = entry_agent.ENTRY_AGENT_AUDIT_DIR
        original_market_snapshot = entry_agent.get_latest_market_snapshot
        original_recent_closed_bars = entry_agent.recent_closed_bars
        original_append_audit = entry_agent.append_entry_agent_audit_row
        self.addCleanup(setattr, entry_agent, "STATE_PATH", original_state_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_PATH", original_context_path)
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_BY_SYMBOL_PATH", original_by_symbol_path)
        self.addCleanup(setattr, entry_agent, "RITHMIC_ATR_SNAPSHOT_PATH", original_atr_path)
        self.addCleanup(setattr, entry_agent, "ENTRY_AGENT_AUDIT_DIR", original_audit_dir)
        self.addCleanup(setattr, entry_agent, "get_latest_market_snapshot", original_market_snapshot)
        self.addCleanup(setattr, entry_agent, "recent_closed_bars", original_recent_closed_bars)
        self.addCleanup(setattr, entry_agent, "append_entry_agent_audit_row", original_append_audit)

        step2_candle = {
            "open": 29383.0,
            "high": 29392.5,
            "low": 29316.25,
            "close": 29322.5,
            "timestamp": "2026-06-12T13:33:00Z",
        }
        touch_candle = {
            "open": 29325.0,
            "high": 29355.75,
            "low": 29303.0,
            "close": 29333.0,
            "timestamp": "2026-06-12T13:34:00Z",
        }
        candles = [step2_candle, touch_candle]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "atr.json"
            entry_agent.ENTRY_AGENT_AUDIT_DIR = temp_path / "entry_agent_audit"
            entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
            cursor = {"index": 0}

            def market_snapshot(_symbol):
                candle = candles[cursor["index"]]
                return {
                    "source": "test",
                    "symbol": "NQM6",
                    "latest_price": candle["close"],
                    "latest_bar_time": candle["timestamp"],
                    "ohlc_is_closed": True,
                    "ohlc": candle,
                }

            entry_agent.get_latest_market_snapshot = market_snapshot
            entry_agent.recent_closed_bars = lambda _symbol, limit=2: candles[: cursor["index"] + 1][-limit:]
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "normalized_symbol": "NQ",
                                "locked": True,
                                "levels": {
                                    "PML": {"price": 29354.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "ONL": {"price": 29260.0, "status": "ACTIVE", "stack_group": "NONE"},
                                    "PMH": {"price": 29646.0, "status": "ACTIVE", "stack_group": "NONE"},
                                },
                                "atr_1m_14": 20.0,
                                "daily_atr14": 200.0,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            step2_status = entry_agent.build_entry_status("NQ")
            step2_reasoning = server.entry_reasoning_record(step2_status, "2026-06-12T13:33:00Z")
            cursor["index"] = 1
            invalidated_status = entry_agent.build_entry_status("NQ")

        self.assertEqual(step2_status["current_step"], "Step 2")
        self.assertEqual(step2_status["current_step_status"], "CONFIRMED")
        self.assertEqual(step2_status["setup_direction"], "LONG")
        self.assertEqual(step2_status["leg1_window_started_at"], "2026-06-12T13:33:00Z")
        self.assertEqual(step2_status["leg1_window_candle_index"], 0)
        self.assertEqual(step2_status["step2_candle_count"], 0)
        self.assertEqual(step2_status["step4_participation_50_line"], 29307.0)
        self.assertEqual(step2_status["step4_participation_75_line"], 29283.5)
        self.assertTrue(step2_status["step4_participation_lines_visible"])
        self.assertEqual(step2_status["rejection_side"]["step4_participation_50_line"], 29307.0)
        self.assertTrue(step2_status["rejection_side"]["step4_participation_lines_visible"])
        self.assertEqual(step2_reasoning["step2_candle_count"], 0)
        self.assertEqual(step2_reasoning["step4_participation_50_line"], 29307.0)
        self.assertEqual(step2_reasoning["step4_participation_75_line"], 29283.5)
        self.assertTrue(step2_reasoning["step4_participation_lines_visible"])

        self.assertEqual(invalidated_status["invalidation_reason"], "STEP2_STEP4_50_LINE_TOUCHED")
        self.assertEqual(invalidated_status["leg1_window_invalidation_reason"], "STEP2_STEP4_50_LINE_TOUCHED")
        self.assertEqual(invalidated_status["step4_participation_50_line"], 29307.0)
        self.assertFalse(invalidated_status["step4_participation_lines_visible"])

    def test_rejection_step2_remains_visible_when_continuation_controls_before_shared_leg1(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_get_latest_market_snapshot = entry_agent.get_latest_market_snapshot
        self.addCleanup(setattr, entry_agent, "get_latest_market_snapshot", original_get_latest_market_snapshot)
        entry_agent.get_latest_market_snapshot = lambda _symbol="NQ": None

        original_run_once = entry_agent.run_once
        self.addCleanup(setattr, entry_agent, "run_once", original_run_once)

        rejection_candle = {
            "open": 29000.0,
            "high": 29020.0,
            "low": 28990.0,
            "close": 29010.0,
            "timestamp": "2026-06-10T13:38:00Z",
        }
        continuation_candle = {
            "open": 29010.0,
            "high": 29015.0,
            "low": 28980.0,
            "close": 28990.0,
            "timestamp": "2026-06-10T13:40:00Z",
        }
        active_liquidity = {
            "name": "PMH",
            "display_name": "PMH Liquidity",
            "price": 29000.0,
            "side": "upper",
            "group": None,
        }
        locked_owner = {
            "pathway": "rejection",
            "active_liquidity": active_liquidity,
            "active_liquidity_name": "PMH",
            "active_liquidity_display_name": "PMH Liquidity",
            "active_liquidity_price": 29000.0,
            "active_liquidity_group": None,
            "setup_direction": "SHORT",
            "side": "upper",
            "candle_a": rejection_candle,
            "activated_at": "2026-06-10T13:38:00Z",
        }
        snapshot = {
            "requested_symbol": "NQ",
            "normalized_symbol": "NQ",
            "latest_price": continuation_candle["close"],
            "latest_bar_time": continuation_candle["timestamp"],
            "ohlc_is_closed": True,
            "ohlc": continuation_candle,
            "liquidity": {"tick_size": 0.25},
            "step_2_1a": {
                "step_2_activated": True,
                "candle_a": rejection_candle,
                "active_level": "PMH",
                "level_price": 29000.0,
                "side": "upper",
                "last_evaluated_bar_time": continuation_candle["timestamp"],
                "active_liquidity_group": None,
                "last_interacted_liquidity": active_liquidity,
                "step2_locked_owner": locked_owner,
                "events": [{"event": "step_2_activated", "timestamp": "2026-06-10T13:38:00Z"}],
            },
            "rejection": {
                "rejection_mode": "ON",
                "watch_side": "SHORT",
                "trigger_level": "PMH",
                "trigger_price": 29000.0,
            },
            "step25": {
                "status": "READY",
                "next_step": "Step 3",
                "state": {
                    "controlling_mode": "R/S",
                    "current_continuation_type": "R/S",
                    "reclaim_candle_a": continuation_candle,
                    "continuation_step2_activated": True,
                    "setup_direction": "LONG",
                },
            },
            "step3": {"status": "WAIT", "next_step": "Step 3", "state": {}},
            "step4": {"status": "WAIT", "next_step": "Step 4", "state": {}},
            "step5": {"status": "WAIT", "next_step": "Step 5", "state": {}},
            "step6": {"status": "WAIT", "next_step": "Step 6", "state": {}},
        }
        entry_agent.run_once = lambda _symbol="NQ", persist=True: copy.deepcopy(snapshot)

        status = entry_agent.build_entry_status("NQ")

        self.assertEqual(status["selected_pathway"], "continuation")
        self.assertEqual(status["current_pathway_control"], "continuation")
        self.assertEqual(status["continuation_side"]["pathway_status"], "controlling")
        self.assertEqual(status["continuation_side"]["current_step"], "Step 2")
        self.assertEqual(status["continuation_side"]["current_step_confirmed_at"], "2026-06-10T13:40:00Z")

        self.assertEqual(status["rejection_side"]["pathway_status"], "frozen")
        self.assertEqual(status["rejection_side"]["current_step"], "Step 2")
        self.assertEqual(status["rejection_side"]["current_step_label"], "Step 2 (Liquidity Close / Pathway Activation)")
        self.assertEqual(status["rejection_side"]["current_step_status"], "CONFIRMED")
        self.assertEqual(status["rejection_side"]["current_step_confirmed_at"], "2026-06-10T13:38:00Z")
        self.assertEqual(status["rejection_side"]["step2_status"], "CONFIRMED")
        self.assertEqual(status["rejection_side"]["step2_confirmed_at"], "2026-06-10T13:38:00Z")
        self.assertIsNone(status["rejection_side"]["leg1_status"])

    def test_leg1_50_percent_penetration_rule_fields_and_invalidation(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        candle_a = {"open": 100.2, "high": 100.3, "low": 99.9, "close": 100.1, "timestamp": "2026-05-05T18:25:00Z"}
        valid_b = {"open": 100.0, "high": 100.2, "low": 99.6, "close": 100.0, "timestamp": "2026-05-05T18:26:00Z"}
        invalid_b = {"open": 100.0, "high": 100.2, "low": 94.8, "close": 100.0, "timestamp": "2026-05-05T18:27:00Z"}
        step25 = {
            "status": "READY",
            "state": {
                "rejection_mode": "ON",
                "interaction_state": "ACTIVE",
                "initial_candle_a": candle_a,
                "step25_pathway_selection_complete": True,
            },
            "events": [],
        }
        step3 = {
            "status": "ALLOW_STEP_4",
            "next_step": "Step 4",
            "state": {
                "step3_allows_structure": True,
                "interaction_state": "ACTIVE",
                "active_liquidity": {"name": "PML", "price": 100.0},
                "tick_size": 0.25,
            },
            "events": [],
        }

        def snapshot(candle):
            return {
                "latest_price": candle["close"],
                "latest_bar_time": candle["timestamp"],
                "ohlc": candle,
                "liquidity": {
                    "tick_size": 0.25,
                    "nearest_level_below": {"name": "LL", "price": 90.0},
                    "nearest_level_above": {"name": "PMH", "price": 110.0},
                },
                "atr": {"atr_1m_14": 1.0},
                "tv_context": {"daily_atr14": 40.0},
            }

        valid = entry_agent.evaluate_live_step4(snapshot(valid_b), {"rejection_mode": "ON", "watch_side": "LONG"}, step25, step3, {})
        invalid = entry_agent.evaluate_live_step4(snapshot(invalid_b), {"rejection_mode": "ON", "watch_side": "LONG"}, step25, step3, {})

        self.assertEqual(valid["status"], "READY")
        self.assertAlmostEqual(valid["state"]["leg1_formed_at_percent"], 4.0)
        self.assertTrue(valid["state"]["leg1_50_percent_rule_passed"])
        self.assertEqual(invalid["status"], "TERMINATED")
        # This fixture invalidates earlier on the Step 2 -> Step 4 midpoint breach.
        self.assertIsNone(invalid["state"].get("leg1_50_percent_rule_passed"))
        self.assertEqual(invalid["state"]["invalidation_source"], "step2_step4_50_line")
        self.assertEqual(invalid["state"]["invalidation_source_step"], "Step 4")
        self.assertEqual(invalid["reason"], "STEP2_STEP4_50_LINE_TOUCHED")

    def test_step2_step4_50_invalidation_consumes_liquidity_level(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        candle_a = {"open": 100.2, "high": 100.3, "low": 99.9, "close": 100.1, "timestamp": "2026-05-05T18:25:00Z"}
        invalid_b = {"open": 100.0, "high": 100.2, "low": 94.8, "close": 100.0, "timestamp": "2026-05-05T18:27:00Z"}
        step25 = {
            "status": "READY",
            "state": {
                "rejection_mode": "ON",
                "interaction_state": "ACTIVE",
                "initial_candle_a": candle_a,
                "step25_pathway_selection_complete": True,
            },
            "events": [],
        }
        step3 = {
            "status": "ALLOW_STEP_4",
            "next_step": "Step 4",
            "state": {
                "step3_allows_structure": True,
                "interaction_state": "ACTIVE",
                "active_liquidity": {"name": "PML", "price": 100.0},
                "tick_size": 0.25,
            },
            "events": [],
        }
        snapshot = {
            "latest_price": invalid_b["close"],
            "latest_bar_time": invalid_b["timestamp"],
            "ohlc": invalid_b,
            "liquidity": {
                "tick_size": 0.25,
                "nearest_level_below": {"name": "LL", "price": 90.0},
                "nearest_level_above": {"name": "PMH", "price": 110.0},
            },
            "atr": {"atr_1m_14": 1.0},
            "tv_context": {"daily_atr14": 40.0},
        }

        result = entry_agent.evaluate_live_step4(
            snapshot,
            {"rejection_mode": "ON", "watch_side": "LONG"},
            step25,
            step3,
            {},
        )

        self.assertEqual(result["status"], "TERMINATED")
        self.assertTrue(
            any(
                record.get("key") == "PML:100.0"
                and record.get("exhaustion_type") == "step2_step4_50_percent_invalidation"
                for record in result["state"]["consumed_liquidity_levels"]
            )
        )

    def test_step2_step4_50_line_invalidation_now_captures_candle_a_only_breach_before_leg1(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        candle_a = {"open": 100.2, "high": 100.3, "low": 85.0, "close": 100.1, "timestamp": "2026-05-05T18:25:00Z"}
        candidate_b = {"open": 100.0, "high": 100.2, "low": 95.0, "close": 100.0, "timestamp": "2026-05-05T18:26:00Z"}
        step25 = {
            "status": "READY",
            "state": {
                "rejection_mode": "ON",
                "interaction_state": "ACTIVE",
                "initial_candle_a": candle_a,
                "step25_pathway_selection_complete": True,
            },
            "events": [],
        }
        step3 = {
            "status": "ALLOW_STEP_4",
            "next_step": "Step 4",
            "state": {
                "step3_allows_structure": True,
                "interaction_state": "ACTIVE",
                "active_liquidity": {"name": "PML", "price": 100.0},
                "tick_size": 0.25,
            },
            "events": [],
        }

        snapshot = {
            "latest_price": candidate_b["close"],
            "latest_bar_time": candidate_b["timestamp"],
            "ohlc": candidate_b,
            "liquidity": {
                "tick_size": 0.25,
                "nearest_level_below": {"name": "LL", "price": 80.0},
                "nearest_level_above": {"name": "PMH", "price": 110.0},
            },
            "atr": {"atr_1m_14": 1.0},
            "tv_context": {"daily_atr14": 40.0},
        }

        result = entry_agent.evaluate_live_step4(snapshot, {"rejection_mode": "ON", "watch_side": "LONG"}, step25, step3, {})

        self.assertEqual(result["status"], "TERMINATED")
        self.assertEqual(result["reason"], "STEP2_STEP4_50_LINE_TOUCHED")
        self.assertEqual(result["state"]["step2_step4_50_line"], 90.0)
        self.assertEqual(result["state"]["step2_step4_50_line_touched_at"], candle_a["timestamp"])
        self.assertNotEqual(result["state"].get("invalidation_source"), "leg1_50_percent_rule")

    def test_reserved_first_candle_b_touch_invalidates_when_step4_does_not_complete(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step4_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        state = {
            "rejection_mode": "ON",
            "step25_pathway_selection_complete": True,
            "step3_allows_structure": True,
            "interaction_state": "ACTIVE",
            "setup_direction": "SHORT",
            "initial_candle_a": {"timestamp": "2026-06-24T13:50:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
            "candle_a": {"timestamp": "2026-06-24T13:50:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
            "candle_a_source": "initial_candle_a",
            "active_liquidity": {"name": "PMH", "price": 100.0},
            "next_break_side_liquidity": {"name": "YH", "price": 110.0},
            "nearest_opposing_liquidity": {"name": "PML", "price": 90.0},
            "tick_size": 0.25,
            "daily_atr14": 40.0,
            "leg1_window_active": True,
            "leg1_window_started_at": "2026-06-24T13:50:00Z",
            "leg1_window_candle_index": 0,
            "reserved_rejection_candle_b_evaluation": True,
            "opening_post_confirmation_relaxed_wick": True,
            "events": [],
        }
        candidate_b = {"timestamp": "2026-06-24T13:51:00Z", "open": 105.1, "high": 105.25, "low": 104.8, "close": 105.2}

        result = step4_engine.evaluate_step4({**state, "candle_b": candidate_b})

        self.assertEqual(result["status"], "TERMINATED")
        self.assertEqual(result["reason"], "STEP2_STEP4_50_LINE_TOUCHED")
        self.assertEqual(result["state"]["invalidation_source"], "step2_step4_50_line")
        self.assertEqual(result["state"]["step2_step4_50_line"], 105.0)
        self.assertEqual(result["state"]["step2_step4_50_line_touched_at"], candidate_b["timestamp"])

    def test_reserved_first_candle_b_touch_still_allows_ready_when_handoff_completes(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step4_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        state = {
            "rejection_mode": "ON",
            "step25_pathway_selection_complete": True,
            "step3_allows_structure": True,
            "interaction_state": "ACTIVE",
            "setup_direction": "SHORT",
            "initial_candle_a": {"timestamp": "2026-06-24T13:50:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
            "candle_a": {"timestamp": "2026-06-24T13:50:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
            "candle_a_source": "initial_candle_a",
            "active_liquidity": {"name": "PMH", "price": 100.0},
            "next_break_side_liquidity": {"name": "YH", "price": 110.0},
            "nearest_opposing_liquidity": {"name": "PML", "price": 90.0},
            "tick_size": 0.25,
            "daily_atr14": 40.0,
            "leg1_window_active": True,
            "leg1_window_started_at": "2026-06-24T13:50:00Z",
            "leg1_window_candle_index": 0,
            "reserved_rejection_candle_b_evaluation": True,
            "opening_post_confirmation_relaxed_wick": True,
            "events": [],
        }
        candidate_b = {"timestamp": "2026-06-24T13:51:00Z", "open": 105.0, "high": 105.5, "low": 99.75, "close": 100.75}

        result = step4_engine.evaluate_step4({**state, "candle_b": candidate_b})

        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["next_step"], "Step 5")
        self.assertEqual(result["state"]["leg1_status"], "COMPLETE")

    def test_locked_leg1_skips_50_percent_rule_on_later_retracement(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        locked_state = {
            "rejection_mode": "ON",
            "interaction_state": "ACTIVE",
            "leg1_status": "COMPLETE",
            "leg1_state_locked": True,
            "setup_direction": "SHORT",
            "leg1_direction": "SHORT",
            "active_liquidity": {"name": "ONH", "price": 50000.0},
            "candle_a": {"open": 49980.0, "high": 50020.0, "low": 49970.0, "close": 50005.0, "timestamp": "2026-05-06T06:38:00-07:00"},
            "candle_b": {"open": 50003.0, "high": 50010.0, "low": 49980.0, "close": 49990.0, "timestamp": "2026-05-06T06:39:00-07:00"},
            "leg1_completed_at": "2026-05-06T06:39:00-07:00",
            "leg1_reference": 50005.0,
            "leg1_reference_price": 50005.0,
            "leg1_reference_candle_time": "2026-05-06T06:38:00-07:00",
            "leg1_extreme": 50020.0,
            "anchor_extreme": 50020.0,
            "current_active_sequence_started_at": "2026-05-06T06:38:00-07:00",
            "leg1_formed_at_percent": 10.0,
            "leg1_50_percent_rule_passed": True,
        }
        step25 = {
            "status": "READY",
            "next_step": "Step 3",
            "state": {
                "rejection_mode": "ON",
                "interaction_state": "ACTIVE",
                "initial_candle_a": locked_state["candle_a"],
                "step25_pathway_selection_complete": True,
            },
            "events": [],
        }
        step3 = {
            "status": "ALLOW_STEP_4",
            "next_step": "Step 4",
            "state": {
                "step3_allows_structure": True,
                "interaction_state": "ACTIVE",
                "active_liquidity": {"name": "ONH", "price": 50000.0},
            },
            "events": [],
        }
        retracement_snapshot = {
            "latest_price": 50060.0,
            "latest_bar_time": "2026-05-06T06:45:00-07:00",
            "ohlc": {"open": 50020.0, "high": 50070.0, "low": 50010.0, "close": 50060.0},
            "liquidity": {
                "tick_size": 1.0,
                "nearest_level_above": {"name": "YH", "price": 50100.0},
                "nearest_level_below": {"name": "ONH", "price": 50000.0},
            },
            "atr": {"atr_1m_14": 10.0},
            "tv_context": {"daily_atr14": 400.0},
        }

        result = entry_agent.evaluate_live_step4(
            retracement_snapshot,
            {"rejection_mode": "ON", "watch_side": "SHORT"},
            step25,
            step3,
            {"step4": {"status": "READY", "next_step": "Step 5", "state": locked_state, "events": []}},
        )

        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["next_step"], "Step 5")
        self.assertEqual(result["state"]["fifty_percent_rule_phase"], "skipped_leg1_locked")
        self.assertTrue(result["state"]["leg1_state_locked"])
        self.assertEqual(result["state"]["leg1_completed_at"], "2026-05-06T06:39:00-07:00")
        self.assertIsNone(result["state"].get("invalidation_source"))

    def test_leg2_25_percent_extension_rule_fields_and_invalidation(self):
        self.skipTest("Step 5 certification is out of current Step 4 certification scope.")
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step5_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        base_state = {
            "rejection_mode": "ON",
            "interaction_state": "ACTIVE",
            "leg1_status": "COMPLETE",
            "leg1_state_locked": True,
            "setup_direction": "LONG",
            "leg1_direction": "LONG",
            "tick_size": 0.25,
            "leg1_reference": 100.0,
            "leg1_reference_price": 100.0,
            "leg1_reference_candle_time": "2026-05-05T18:25:00Z",
            "leg1_extreme": 96.0,
            "anchor_extreme": 96.0,
            "leg1_completed_at": "2026-05-05T18:26:00Z",
            "current_active_sequence_started_at": "2026-05-05T18:25:00Z",
            "active_liquidity": {"name": "PML", "price": 100.0},
            "candle_a": {"open": 100.5, "high": 101.0, "low": 96.0, "close": 100.0},
            "candle_b": {"open": 99.8, "high": 100.1, "low": 96.5, "close": 99.5},
            "nearest_opposing_liquidity": {"name": "PMH", "price": 110.0},
            "atr_1m_14": 1.0,
            "enforce_leg2_25_percent_rule": True,
            "events": [],
        }

        valid = step5_engine.evaluate_step5(
            {**base_state, "latest_candle": {"open": 99.0, "high": 99.5, "low": 95.2, "close": 95.8}}
        )
        invalid = step5_engine.evaluate_step5(
            {**base_state, "latest_candle": {"open": 99.0, "high": 99.5, "low": 94.8, "close": 95.8}}
        )

        self.assertEqual(valid["status"], "WAIT")
        self.assertAlmostEqual(valid["state"]["leg2_formed_at_percent"], 22.857142857142776)
        self.assertTrue(valid["state"]["leg2_25_percent_rule_passed"])
        self.assertEqual(invalid["status"], "TERMINATED")
        self.assertAlmostEqual(invalid["state"]["leg2_formed_at_percent"], 34.285714285714285)
        self.assertFalse(invalid["state"]["leg2_25_percent_rule_passed"])
        self.assertIn("25%", invalid["reason"])

    def test_leg2_25_percent_waits_without_current_locked_leg1(self):
        self.skipTest("Step 5 certification is out of current Step 4 certification scope.")
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
            import step5_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        candle = {"open": 99.0, "high": 99.5, "low": 94.8, "close": 95.8, "timestamp": "2026-05-05T18:27:00Z"}
        base_state = {
            "rejection_mode": "ON",
            "interaction_state": "ACTIVE",
            "leg1_status": "COMPLETE",
            "setup_direction": "LONG",
            "tick_size": 0.25,
            "leg1_reference": 100.0,
            "leg1_extreme": 96.0,
            "anchor_extreme": 96.0,
            "candle_a": {"open": 100.5, "high": 101.0, "low": 96.0, "close": 100.0},
            "candle_b": {"open": 99.8, "high": 100.1, "low": 96.5, "close": 99.5},
            "nearest_opposing_liquidity": {"name": "PMH", "price": 110.0},
            "atr_1m_14": 1.0,
            "enforce_leg2_25_percent_rule": True,
            "latest_candle": candle,
            "events": [],
        }

        no_lock = step5_engine.evaluate_step5(base_state)
        stale_lock = step5_engine.evaluate_step5(
            {
                **base_state,
                "leg1_state_locked": True,
                "leg1_reference_price": 100.0,
                "leg1_reference_candle_time": "2026-05-05T13:38:00-07:00",
                "leg1_direction": "LONG",
                "active_liquidity": {"name": "PML", "price": 100.0},
                "leg1_completed_at": "2026-05-05T13:39:00-07:00",
                "current_active_sequence_started_at": "2026-05-05T18:25:00Z",
            }
        )
        live_wait = entry_agent.evaluate_live_step5(
            {"latest_price": 95.8, "latest_bar_time": candle["timestamp"], "ohlc": candle},
            {
                "status": "READY",
                "next_step": "Step 5",
                "state": {**base_state, "leg1_state_locked": False},
            },
            {},
        )

        self.assertEqual(no_lock["status"], "WAIT")
        self.assertIsNone(no_lock["state"]["leg2_formed_at_percent"])
        self.assertIsNone(no_lock["state"]["leg2_25_percent_rule_passed"])
        self.assertEqual(no_lock["reason"], "Waiting for valid locked Leg 1 reference")
        self.assertEqual(stale_lock["status"], "WAIT")
        self.assertIsNone(stale_lock["state"]["leg2_formed_at_percent"])
        self.assertIsNone(stale_lock["state"]["leg2_25_percent_rule_passed"])
        self.assertEqual(stale_lock["reason"], "Waiting for valid locked Leg 1 reference")
        self.assertEqual(live_wait["status"], "WAIT")
        self.assertEqual(live_wait["reason"], "Waiting for valid locked Leg 1 reference")

    def test_step5_rejects_same_sequence_leg2_candidate_after_locked_leg1(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        step4 = {
            "status": "READY",
            "next_step": "Step 5",
            "state": {
                "rejection_mode": "ON",
                "interaction_state": "ACTIVE",
                "leg1_status": "COMPLETE",
                "leg1_state_locked": True,
                "setup_direction": "LONG",
                "leg1_direction": "LONG",
                "tick_size": 0.25,
                "leg1_reference": 100.0,
                "leg1_reference_price": 100.0,
                "leg1_reference_candle_time": "2026-05-06T07:59:00-07:00",
                "leg1_extreme": 96.0,
                "anchor_extreme": 96.0,
                "leg1_completed_at": "2026-05-06T08:00:00-07:00",
                "current_active_sequence_started_at": "2026-05-06T07:59:00-07:00",
                "active_liquidity": {"name": "ONH", "price": 100.0},
                "candle_a": {
                    "open": 100.5,
                    "high": 101.0,
                    "low": 96.0,
                    "close": 100.0,
                    "timestamp": "2026-05-06T07:59:00-07:00",
                },
                "candle_b": {
                    "open": 99.8,
                    "high": 100.1,
                    "low": 96.5,
                    "close": 99.5,
                    "timestamp": "2026-05-06T08:00:00-07:00",
                },
                "nearest_opposing_liquidity": {"name": "PMH", "price": 110.0},
                "atr_1m_14": 1.0,
            },
        }
        same_candle = {
            "latest_price": 95.8,
            "latest_bar_time": "2026-05-06T15:00:00Z",
            "ohlc": {"open": 99.0, "high": 99.5, "low": 95.2, "close": 95.8},
        }
        later_candle = {
            "latest_price": 95.8,
            "latest_bar_time": "2026-05-06T15:01:00Z",
            "ohlc": {"open": 99.0, "high": 99.5, "low": 95.2, "close": 95.8},
        }

        same_result = entry_agent.evaluate_live_step5(same_candle, step4, {})
        later_result = entry_agent.evaluate_live_step5(later_candle, step4, {})

        self.assertEqual(same_result["status"], "WAIT")
        self.assertEqual(same_result["state"]["leg2_candidate_candle_time"], "2026-05-06T15:00:00Z")
        self.assertTrue(same_result["state"]["leg2_same_sequence_rejected"])
        self.assertEqual(
            same_result["state"]["leg2_wait_reason"],
            "Step 5 waiting for a separate future Leg 2 candle after locked Leg 1.",
        )
        self.assertEqual(later_result["status"], "WAIT")
        self.assertEqual(later_result["state"]["leg2_status"], "CONFIRMED")
        self.assertEqual(later_result["state"]["leg2_candidate_candle_time"], "2026-05-06T15:01:00Z")
        self.assertFalse(later_result["state"]["leg2_same_sequence_rejected"])

    def test_leg1_window_counts_next_four_closed_candles_after_step2(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step4_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        state = {
            "rejection_mode": "ON",
            "step25_pathway_selection_complete": True,
            "step3_allows_structure": True,
            "interaction_state": "ACTIVE",
            "setup_direction": "SHORT",
            "initial_candle_a": {"timestamp": "2026-05-14T13:38:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
            "active_liquidity": {"name": "PMH", "price": 100.0},
            "nearest_opposing_liquidity": {"name": "PML", "price": 90.0},
            "atr_1m_14": 1.0,
            "daily_atr14": 40.0,
            "events": [],
        }
        no_participation = [
            {"timestamp": "2026-05-14T13:39:00Z", "open": 102.0, "high": 102.75, "low": 102.0, "close": 102.5},
            {"timestamp": "2026-05-14T13:40:00Z", "open": 102.5, "high": 103.25, "low": 102.5, "close": 103.0},
            {"timestamp": "2026-05-14T13:41:00Z", "open": 103.0, "high": 103.75, "low": 103.0, "close": 103.5},
            {"timestamp": "2026-05-14T13:42:00Z", "open": 103.5, "high": 104.25, "low": 103.5, "close": 104.0},
        ]
        step4_engine.initialize_leg1_window(state, "2026-05-14T13:38:00Z")

        for index, candle in enumerate(no_participation, start=1):
            result = step4_engine.evaluate_step4({**state, "candle_b": candle})
            state = result["state"]
            self.assertEqual(state["leg1_window_candle_index"], index)
            self.assertEqual(state["leg1_window_started_at"], "2026-05-14T13:38:00Z")
            self.assertEqual(state["leg1_window_expires_at"], "2026-05-14T13:42:00Z")
            self.assertEqual(state["leg1_window_remaining"], 4 - index)
            if index < 4:
                self.assertEqual(result["status"], "WAIT")
                self.assertTrue(state["leg1_window_active"])
                self.assertNotIn("leg1_status", state)
            else:
                self.assertEqual(result["status"], "TERMINATED")
                self.assertFalse(state["leg1_window_active"])
                self.assertEqual(result["reason"], "Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation.")

    def test_leg1_window_accepts_participation_on_candles_1_through_4(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import step4_engine
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        def base_state():
            return {
                "rejection_mode": "ON",
                "step25_pathway_selection_complete": True,
                "step3_allows_structure": True,
                "interaction_state": "ACTIVE",
                "setup_direction": "SHORT",
                "initial_candle_a": {"timestamp": "2026-05-14T13:38:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
                "active_liquidity": {"name": "PMH", "price": 100.0},
                "nearest_opposing_liquidity": {"name": "PML", "price": 90.0},
                "atr_1m_14": 1.0,
                "daily_atr14": 40.0,
                "events": [],
            }

        no_participation = [
            {"timestamp": "2026-05-14T13:39:00Z", "open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
            {"timestamp": "2026-05-14T13:40:00Z", "open": 101.3, "high": 101.4, "low": 101.1, "close": 101.3},
            {"timestamp": "2026-05-14T13:41:00Z", "open": 101.4, "high": 101.5, "low": 101.2, "close": 101.4},
        ]
        participation = {"open": 102.0, "high": 102.5, "low": 100.0, "close": 100.75}

        for participation_index in (1, 2, 3, 4):
            with self.subTest(participation_index=participation_index):
                state = base_state()
                step4_engine.initialize_leg1_window(state, "2026-05-14T13:38:00Z")
                for candle in no_participation[: participation_index - 1]:
                    result = step4_engine.evaluate_step4({**state, "candle_b": candle})
                    self.assertEqual(result["status"], "WAIT")
                    state = result["state"]
                candle = {**participation, "timestamp": f"2026-05-14T13:{38 + participation_index:02d}:00Z"}
                result = step4_engine.evaluate_step4({**state, "candle_b": candle})

                self.assertEqual(result["status"], "READY")
                self.assertEqual(result["next_step"], "Step 5")
                self.assertEqual(result["state"]["leg1_status"], "COMPLETE")
                self.assertEqual(result["state"]["leg1_window_candle_index"], participation_index)
                self.assertFalse(result["state"]["leg1_window_active"])
                self.assertFalse(result["state"]["leg1_window_invalidated"])

    def test_market_feed_uses_trade_manager_last_price_snapshot(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import market_feed
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_urlopen = market_feed.urlopen
        original_bars_path = market_feed.RITHMIC_BARS_PATH
        original_executor_state_path = market_feed.EXECUTOR_STATE_PATH

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _traceback):
                return False

            def read(self):
                return json.dumps(
                    {
                        "timestamp": "2026-05-05T18:26:00Z",
                        "symbols": {
                            "YMM6": {
                                "last_price": 50101,
                                "last_price_at": "2026-05-05T18:26:01Z",
                                "current_1m_bar": {
                                    "open": 50100,
                                    "high": 50102,
                                    "low": 50099,
                                    "close": 50101,
                                    "timestamp": "2026-05-05T18:26:00Z",
                                },
                            }
                        },
                    }
                ).encode("utf-8")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            market_feed.RITHMIC_BARS_PATH = temp_path / "rithmic_recent_bars.json"
            market_feed.EXECUTOR_STATE_PATH = temp_path / "executor_state.json"
            market_feed.urlopen = lambda _url, timeout=0.5: FakeResponse()
            try:
                snapshot = market_feed.get_latest_market_snapshot("YM")
            finally:
                market_feed.urlopen = original_urlopen
                market_feed.RITHMIC_BARS_PATH = original_bars_path
                market_feed.EXECUTOR_STATE_PATH = original_executor_state_path

        self.assertEqual(snapshot["symbol"], "YMM6")
        self.assertEqual(snapshot["latest_price"], 50101.0)
        self.assertEqual(snapshot["ohlc"]["close"], 50101)

    def test_build_entry_status_waits_when_market_price_missing(self):
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            import entry_agent
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass

        original_state_path = entry_agent.STATE_PATH
        original_context_path = entry_agent.TV_CONTEXT_PATH
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        original_atr_path = entry_agent.RITHMIC_ATR_SNAPSHOT_PATH
        original_market_snapshot = entry_agent.get_latest_market_snapshot

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = temp_path / "rithmic_atr_snapshot.json"
            entry_agent.get_latest_market_snapshot = lambda symbol: {
                "source": "test",
                "symbol": symbol,
                "latest_price": None,
                "latest_bar_time": None,
                "ohlc": None,
            }
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ",
                                "levels": {
                                    "ONH": {"price": 28008.5, "status": "ACTIVE", "stack_group": "NONE"}
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            status = entry_agent.build_entry_status("NQM6")
            self.assertEqual(status["wait_reason"], "No market price available.")
            self.assertIsNone(status["active_liquidity_name"])
            self.assertIsNone(status["active_liquidity_price"])

        entry_agent.STATE_PATH = original_state_path
        entry_agent.TV_CONTEXT_PATH = original_context_path
        entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = original_by_symbol_path
        entry_agent.RITHMIC_ATR_SNAPSHOT_PATH = original_atr_path
        entry_agent.get_latest_market_snapshot = original_market_snapshot

    def test_tv_context_receiver_accepts_payload_without_strict_source(self):
        server = self._load_server()
        response = server.app.test_client().post(
            "/webhook/tv-context",
            json={"source": "wrong", "symbol": "NQ"},
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["context"]["source"], "wrong")

    def test_randle_taylor_context_receiver_accepts_valid_payload(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.LEVELS_PATH = temp_path / "levels.json"
            server.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.TV_CONTEXT_EVENTS_PATH = temp_path / "tv_context_events.jsonl"
            server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()

            response = server.app.test_client().post("/webhook/tv-context", json=self._valid_randle_taylor_payload())
            payload = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["normalized_symbol"], "NQ")
            self.assertEqual(payload["context"]["source"], "randle_taylor_map")
            self.assertTrue(payload["context"]["locked"])
            self.assertTrue(payload["context"]["taylor_context_locked"])
            self.assertEqual(payload["context"]["taylor_context_locked_at"], payload["context"]["received_at"])
            self.assertEqual(payload["context"]["taylor_context_source"], "randle_taylor_map")
            self.assertEqual(payload["context"]["locked_taylor_context"]["source"], "randle_taylor_map")
            self.assertEqual(payload["context"]["session_lock_price"], 29392.0)
            self.assertEqual(payload["context"]["daily_atr14"], 150.0)
            self.assertEqual(payload["context"]["locked_liquidity_context"]["session_lock_price"], 29392.0)
            self.assertEqual(payload["context"]["locked_liquidity_context"]["daily_atr14"], 150.0)
            self.assertEqual(payload["context"]["levels"]["ONH"]["price"], 29410.0)
            self.assertEqual(payload["context"]["taylor_context"]["t_plus"]["associated_extreme_name"], "ONH")

    def test_randle_taylor_context_receiver_rejects_missing_symbol(self):
        server = self._load_server()
        payload = self._valid_randle_taylor_payload()
        payload.pop("symbol")

        response = server.app.test_client().post("/webhook/tv-context", json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "symbol is required")

    def test_randle_taylor_context_receiver_rejects_missing_liquidity_map(self):
        server = self._load_server()
        payload = self._valid_randle_taylor_payload()
        payload.pop("liquidity_map")

        response = server.app.test_client().post("/webhook/tv-context", json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "liquidity_map is required")

    def test_randle_taylor_context_receiver_rejects_missing_taylor_context(self):
        server = self._load_server()
        payload = self._valid_randle_taylor_payload()
        payload.pop("taylor_context")

        response = server.app.test_client().post("/webhook/tv-context", json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "taylor_context is required")

    def test_randle_taylor_context_receiver_rejects_malformed_stack_data(self):
        server = self._load_server()
        payload = self._valid_randle_taylor_payload()
        payload["liquidity_map"]["stacks"][0]["close_boundary_price"] = "bad"

        response = server.app.test_client().post("/webhook/tv-context", json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn("close_boundary_price", response.get_json()["error"])

    def test_randle_taylor_context_receiver_rejects_malformed_taylor_association(self):
        server = self._load_server()
        payload = self._valid_randle_taylor_payload()
        payload["taylor_context"]["t_plus"]["associated_extreme_name"] = ""

        response = server.app.test_client().post("/webhook/tv-context", json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn("associated_extreme_name", response.get_json()["error"])

    def test_randle_taylor_context_appears_in_status_and_snapshot(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.LEVELS_PATH = temp_path / "levels.json"
            server.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.TV_CONTEXT_EVENTS_PATH = temp_path / "tv_context_events.jsonl"
            server.DATA_DIR = temp_path / "Data"
            server.ENTRY_LOG_DIR = temp_path / "logs"
            server.ENTRY_DECISIONS_LOG_PATH = server.ENTRY_LOG_DIR / "entry_decisions.jsonl"
            server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
            server.build_entry_status = lambda symbol: {
                "symbol": symbol,
                "timestamp": "2026-06-16T13:16:00+00:00",
                "current_step": "Step 2",
                "active_liquidity_name": "PMH",
                "active_liquidity_price": 29402.0,
                "setup_direction": None,
                "leg1_status": "WAIT",
                "leg2_status": "WAIT",
                "entry_status": "WAIT",
                "wait_reason": "Context only.",
                "invalidation_reason": None,
                "last_decision": "WAIT: Context only.",
            }
            client = server.app.test_client()

            post_response = client.post("/webhook/tv-context", json=self._valid_randle_taylor_payload())
            snapshot_response = client.get("/context?symbol=NQ")
            status_response = client.get("/entry/status?symbols=NQ")

            self.assertEqual(post_response.status_code, 200)
            self.assertEqual(snapshot_response.status_code, 200)
            self.assertEqual(status_response.status_code, 200)
            snapshot_payload = snapshot_response.get_json()
            status_payload = status_response.get_json()
            self.assertEqual(snapshot_payload["source"], "randle_taylor_map")
            self.assertEqual(snapshot_payload["session_lock_price"], 29392.0)
            self.assertEqual(snapshot_payload["daily_atr14"], 150.0)
            self.assertEqual(snapshot_payload["taylor_context"]["t_minus"]["associated_liquidity"], "LL/ONL Stack")
            self.assertEqual(status_payload["symbols"][0]["market_context"]["source"], "randle_taylor_map")
            self.assertEqual(status_payload["symbols"][0]["market_context"]["session_lock_price"], 29392.0)
            self.assertEqual(status_payload["symbols"][0]["market_context"]["daily_atr14"], 150.0)
            self.assertEqual(status_payload["symbols"][0]["market_context"]["liquidity_map"]["stacks"][0]["name"], "PMH/ONH Stack")
            self.assertEqual(status_payload["symbols"][0]["market_context"]["taylor_context"]["yesterday_close"]["associated_extreme_name"], "PML")

    def test_randle_taylor_context_receiver_has_no_execution_side_effects(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.LEVELS_PATH = temp_path / "levels.json"
            server.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.TV_CONTEXT_EVENTS_PATH = temp_path / "tv_context_events.jsonl"
            server.ENTRY_LOG_DIR = temp_path / "logs"
            server.ENTRY_DECISIONS_LOG_PATH = server.ENTRY_LOG_DIR / "entry_decisions.jsonl"
            server.build_entry_status = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("status evaluation must not run during context ingest"))
            server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()

            response = server.app.test_client().post("/webhook/tv-context", json=self._valid_randle_taylor_payload())

            self.assertEqual(response.status_code, 200)
            self.assertTrue(server.LEVELS_PATH.exists())
            self.assertTrue(server.LEVELS_BY_SYMBOL_PATH.exists())
            self.assertTrue(server.TV_CONTEXT_PATH.exists())
            self.assertTrue(server.TV_CONTEXT_BY_SYMBOL_PATH.exists())
            self.assertTrue(server.TV_CONTEXT_EVENTS_PATH.exists())
            self.assertFalse(server.ENTRY_DECISIONS_LOG_PATH.exists())

    def test_same_session_taylor_resend_rejected_without_force(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.LEVELS_PATH = temp_path / "levels.json"
            server.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.TV_CONTEXT_EVENTS_PATH = temp_path / "tv_context_events.jsonl"
            server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
            client = server.app.test_client()

            first = client.post("/webhook/tv-context", json=self._valid_randle_taylor_payload())
            second_payload = copy.deepcopy(self._valid_randle_taylor_payload())
            second_payload["taylor_context"]["t_plus"]["price"] = 29440.0
            second = client.post("/webhook/tv-context", json=second_payload)

            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 409)
            self.assertIn("resend requires force=true", second.get_json()["error"])

    def test_taylor_context_locks_independently_after_liquidity_already_locked(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.LEVELS_PATH = temp_path / "levels.json"
            server.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.TV_CONTEXT_EVENTS_PATH = temp_path / "tv_context_events.jsonl"
            server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
            client = server.app.test_client()

            liquidity_only = client.post(
                "/webhook/tv-context",
                json={
                    "source": "tradingview_level_helper",
                    "symbol": "NQ1!",
                    "timestamp": "2026-06-16T13:15:00Z",
                    "session_date": "2026-06-16",
                    "levels": {
                        "PMH": {"price": 29402.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                        "ONH": {"price": 29410.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                        "PML": {"price": 29354.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                        "ONL": {"price": 29330.0, "status": "ACTIVE", "stack_group": "LOW 2"},
                    },
                },
            )
            first_payload = liquidity_only.get_json()
            taylor_payload = client.post("/webhook/tv-context", json=self._valid_randle_taylor_payload())
            second_payload = taylor_payload.get_json()
            snapshot_payload = client.get("/context?symbol=NQ").get_json()

            self.assertEqual(liquidity_only.status_code, 200)
            self.assertTrue(first_payload["context"]["liquidity_context_locked"])
            self.assertIsNone(first_payload["context"].get("taylor_context"))
            self.assertIsNone(first_payload["context"].get("taylor_context_locked"))
            self.assertEqual(taylor_payload.status_code, 200)
            self.assertTrue(second_payload["context"]["liquidity_context_locked"])
            self.assertTrue(second_payload["context"]["taylor_context_locked"])
            self.assertEqual(second_payload["context"]["taylor_context_source"], "randle_taylor_map")
            self.assertEqual(second_payload["context"]["taylor_context"]["t_plus"]["price"], 29425.0)
            self.assertEqual(snapshot_payload["taylor_context"]["t_minus"]["price"], 29335.0)

    def test_later_level_helper_payload_preserves_locked_taylor_context(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.LEVELS_PATH = temp_path / "levels.json"
            server.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.TV_CONTEXT_EVENTS_PATH = temp_path / "tv_context_events.jsonl"
            server.DATA_DIR = temp_path / "Data"
            server.ENTRY_LOG_DIR = temp_path / "logs"
            server.ENTRY_DECISIONS_LOG_PATH = server.ENTRY_LOG_DIR / "entry_decisions.jsonl"
            server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
            server.build_entry_status = lambda symbol: {
                "symbol": symbol,
                "timestamp": "2026-06-16T13:20:00+00:00",
                "current_step": "Step 2",
                "active_liquidity_name": "PMH",
                "active_liquidity_price": 29402.0,
                "setup_direction": None,
                "leg1_status": "WAIT",
                "leg2_status": "WAIT",
                "entry_status": "WAIT",
                "wait_reason": "Context only.",
                "invalidation_reason": None,
                "last_decision": "WAIT: Context only.",
            }
            client = server.app.test_client()

            first = client.post("/webhook/tv-context", json=self._valid_randle_taylor_payload())
            first_payload = first.get_json()
            locked_at = first_payload["context"]["taylor_context_locked_at"]

            second = client.post(
                "/webhook/tv-context",
                json={
                    "source": "tradingview_level_helper",
                    "symbol": "NQ1!",
                    "timestamp": "2026-06-16T13:20:00Z",
                    "session_date": "2026-06-16",
                    "levels": {
                        "PMH": {"price": 29402.0, "status": "ACTIVE", "stack_group": "HIGH 9"},
                        "ONH": {"price": 29410.0, "status": "ACTIVE", "stack_group": "HIGH 9"},
                        "PML": {"price": 29354.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                    },
                    "heartbeat": {"bar_status": "closed"},
                },
            )
            second_payload = second.get_json()
            snapshot_payload = client.get("/context?symbol=NQ").get_json()
            status_payload = client.get("/entry/status?symbols=NQ").get_json()

            self.assertEqual(second.status_code, 200)
            self.assertTrue(second_payload["context"]["taylor_context_locked"])
            self.assertEqual(second_payload["context"]["taylor_context_locked_at"], locked_at)
            self.assertEqual(second_payload["context"]["taylor_context_source"], "randle_taylor_map")
            self.assertEqual(second_payload["context"]["taylor_context"]["t_plus"]["price"], 29425.0)
            self.assertEqual(second_payload["context"]["locked_taylor_context"]["taylor_context"]["t_minus"]["price"], 29335.0)
            self.assertEqual(snapshot_payload["taylor_context"]["t_plus"]["price"], 29425.0)
            self.assertEqual(status_payload["symbols"][0]["market_context"]["taylor_context"]["yesterday_close"]["price"], 29380.0)

    def test_force_true_replaces_locked_taylor_context(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.LEVELS_PATH = temp_path / "levels.json"
            server.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.TV_CONTEXT_EVENTS_PATH = temp_path / "tv_context_events.jsonl"
            server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
            client = server.app.test_client()

            first = client.post("/webhook/tv-context", json=self._valid_randle_taylor_payload())
            first_payload = first.get_json()
            replacement = copy.deepcopy(self._valid_randle_taylor_payload())
            replacement["force"] = True
            replacement["taylor_context"]["t_plus"]["price"] = 29460.0
            replacement["taylor_context"]["t_minus"]["price"] = 29310.0

            second = client.post("/webhook/tv-context?force=true", json=replacement)
            second_payload = second.get_json()
            snapshot_payload = client.get("/context?symbol=NQ").get_json()

            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            self.assertTrue(second_payload["context"]["taylor_context_locked"])
            # Force replacement must update the locked Taylor payload even if the lock timestamp is identical.
            self.assertTrue(second_payload["context"]["taylor_context_locked_at"])
            self.assertEqual(second_payload["context"]["taylor_context_source"], "randle_taylor_map")
            self.assertNotEqual(
                second_payload["context"]["locked_taylor_context"]["taylor_context"]["t_plus"]["price"],
                first_payload["context"]["locked_taylor_context"]["taylor_context"]["t_plus"]["price"],
            )
            self.assertEqual(second_payload["context"]["taylor_context"]["t_plus"]["price"], 29460.0)
            self.assertEqual(second_payload["context"]["taylor_context"]["t_minus"]["price"], 29310.0)
            self.assertEqual(second_payload["context"]["locked_taylor_context"]["taylor_context"]["t_plus"]["price"], 29460.0)
            self.assertEqual(second_payload["context"]["locked_taylor_context"]["taylor_context"]["t_minus"]["price"], 29310.0)
            self.assertEqual(snapshot_payload["taylor_context"]["t_plus"]["price"], 29460.0)

    def test_entry_status_preserves_requested_contract_symbol(self):
        server = self._load_server()
        server.build_entry_status = lambda symbol: {
            "symbol": symbol,
            "timestamp": "2026-05-05T00:00:00+00:00",
            "current_step": "Step 3",
            "active_liquidity_name": "ONH",
            "active_liquidity_price": 50100,
            "setup_direction": None,
            "leg1_status": "WAIT",
            "leg2_status": "WAIT",
            "entry_status": "WAIT",
            "wait_reason": "Leg 1 waiting.",
            "invalidation_reason": None,
            "last_decision": "WAIT: Leg 1 waiting.",
        }

        response = server.app.test_client().get("/entry/status?symbols=NQM6,YMM6,RTYM6")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["symbol"] for item in payload["symbols"]], ["NQM6", "YMM6", "RTYM6"])
        self.assertTrue(all(item["current_step"] == "Step 2" for item in payload["symbols"]))

    def test_sanitize_stale_session_state_clears_persisted_pathway_lanes(self):
        self._load_server()
        entry_agent = sys.modules["entry_agent"]
        symbol_state = {
            "normalized_symbol": "NQ",
            "latest_bar_time": "2026-06-30T14:35:00Z",
            "step_2_1a": {
                "step2_activated_at": "2026-06-30T14:31:00Z",
            },
            "rejection_lane": {
                "lane_name": "rejection",
                "lane_status": "controlling",
                "pathway_status": "controlling",
                "active_liquidity_name": "PMH/LH/ONH",
                "liquidity_group": "HIGH 1",
                "active_liquidity_price": 30217.0,
                "close_boundary": 30142.75,
                "extreme_boundary": 30217.0,
                "step2_confirmed_at": "2026-06-30T14:31:00Z",
            },
            "continuation_lane": {
                "lane_name": "continuation",
                "lane_status": "eligible",
                "pathway_status": "eligible",
                "active_liquidity_name": "PMH/LH/ONH",
                "liquidity_group": "HIGH 1",
                "active_liquidity_price": 30217.0,
                "close_boundary": 30142.75,
                "extreme_boundary": 30217.0,
                "step2_confirmed_at": "2026-06-30T14:31:00Z",
            },
        }
        persisted = {
            "normalized_symbol": "NQ",
            "rejection_lane": dict(symbol_state["rejection_lane"]),
            "continuation_lane": dict(symbol_state["continuation_lane"]),
            "state_by_symbol": {
                "NQ": dict(symbol_state),
            },
        }

        cleaned = entry_agent.sanitize_stale_session_state(persisted, "NQ", "2026-07-01")
        cleaned_symbol = entry_agent.symbol_scoped_persisted_state(cleaned, "NQ")

        self.assertNotIn("rejection_lane", cleaned_symbol)
        self.assertNotIn("continuation_lane", cleaned_symbol)
        self.assertNotIn("rejection_lane", cleaned)
        self.assertNotIn("continuation_lane", cleaned)

    def test_entry_status_uses_live_tv_session_to_clear_stale_lifecycle_when_market_snapshot_session_lags(self):
        server = self._load_server()
        entry_agent = sys.modules["entry_agent"]

        original_get_latest_market_snapshot = entry_agent.get_latest_market_snapshot
        self.addCleanup(setattr, entry_agent, "get_latest_market_snapshot", original_get_latest_market_snapshot)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            for attr, name in (
                ("STATE_PATH", "entry_agent_state.json"),
                ("TV_CONTEXT_PATH", "tv_context.json"),
                ("TV_CONTEXT_BY_SYMBOL_PATH", "tv_context_by_symbol.json"),
                ("STEP2_OWNER_DIAGNOSTICS_PATH", "entry_step2_owner_diagnostics.jsonl"),
            ):
                original = getattr(entry_agent, attr)
                self.addCleanup(setattr, entry_agent, attr, original)
                setattr(entry_agent, attr, temp_path / name)

            stale_session = "2026-07-08"
            current_session = "2026-07-09"
            stale_levels = {
                "PMH": {"price": 22950.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
            }
            current_levels = {
                "PMH": {"price": 23025.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
            }
            stale_context = {
                "source": "tradingview_level_helper",
                "symbol": "NQ1!",
                "normalized_symbol": "NQ",
                "received_at": "2026-07-08T13:15:00Z",
                "session_date": stale_session,
                "levels": copy.deepcopy(stale_levels),
                "last_tv_context_received_at": "2026-07-08T13:15:00Z",
                "last_tv_context_session_date": stale_session,
                "locked_liquidity_context": {
                    "levels": copy.deepcopy(stale_levels),
                    "liquidity_map": {
                        "levels": [{"name": "PMH", "price": 22950.0, "status": "ACTIVE", "stack_group": "HIGH 1"}],
                        "stacks": [],
                    },
                    "session_date": stale_session,
                    "locked_at": "2026-07-08T13:15:00Z",
                    "source": "tradingview_level_helper",
                    "daily_atr14": 640.0,
                    "midpoints": {},
                    "exhaustion_boundaries": {},
                },
                "liquidity_context_locked": True,
                "liquidity_context_locked_at": "2026-07-08T13:15:00Z",
                "liquidity_context_source": "tradingview_level_helper",
                "locked": True,
            }
            current_context = {
                "source": "tradingview_level_helper",
                "symbol": "NQ1!",
                "normalized_symbol": "NQ",
                "received_at": "2026-07-09T13:15:00Z",
                "session_date": current_session,
                "levels": copy.deepcopy(current_levels),
                "last_tv_context_received_at": "2026-07-09T13:15:00Z",
                "last_tv_context_session_date": current_session,
                "locked_liquidity_context": {
                    "levels": copy.deepcopy(current_levels),
                    "liquidity_map": {
                        "levels": [{"name": "PMH", "price": 23025.0, "status": "ACTIVE", "stack_group": "HIGH 1"}],
                        "stacks": [],
                    },
                    "session_date": current_session,
                    "locked_at": "2026-07-09T13:15:00Z",
                    "source": "tradingview_level_helper",
                    "daily_atr14": 645.0,
                    "midpoints": {},
                    "exhaustion_boundaries": {},
                },
                "liquidity_context_locked": True,
                "liquidity_context_locked_at": "2026-07-09T13:15:00Z",
                "liquidity_context_source": "tradingview_level_helper",
                "locked": True,
            }
            stale_lock = entry_agent.build_session_locked_tv_context(stale_context)
            entry_agent.STATE_PATH.write_text(
                json.dumps(
                    {
                        "state_by_symbol": {
                            "NQ": {
                                "normalized_symbol": "NQ",
                                "requested_symbol": "NQ",
                                "observation_reset_session_date": stale_session,
                                "latest_bar_time": "2026-07-08T18:52:00Z",
                                "session_liquidity_context": stale_lock,
                                "step_2_1a": {
                                    "step_2_activated": True,
                                    "active_level": "PMH",
                                    "level_price": 22950.0,
                                    "side": "upper",
                                    "step2_activated_at": "2026-07-08T18:52:00Z",
                                    "candle_a": {"timestamp": "2026-07-08T18:52:00Z"},
                                },
                                "rejection": {"rejection_mode": "ON", "watch_side": "SHORT"},
                                "step4": {
                                    "status": "READY",
                                    "state": {
                                        "leg1_state_locked": True,
                                        "leg1_status": "COMPLETE",
                                        "step4_confirmed_at": "2026-07-08T18:52:00Z",
                                    },
                                },
                                "rejection_lane": {
                                    "lane_status": "controlling",
                                    "step2_confirmed_at": "2026-07-08T18:52:00Z",
                                },
                                "trade_state": {
                                    "active": True,
                                    "selected_pathway": "rejection",
                                    "active_liquidity_name": "PMH",
                                    "active_liquidity_price": 22950.0,
                                    "close_boundary": 22950.0,
                                },
                            }
                        }
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps({"symbols": {"NQ": current_context}}, indent=2) + "\n",
                encoding="utf-8",
            )
            entry_agent.TV_CONTEXT_PATH.write_text(json.dumps(current_context, indent=2) + "\n", encoding="utf-8")

            entry_agent.get_latest_market_snapshot = lambda _symbol="NQ": {
                "symbol": "NQ",
                "latest_price": 23010.0,
                "latest_bar_time": "2026-07-08T18:52:00Z",
                "ohlc": {"open": 23000.0, "high": 23020.0, "low": 22990.0, "close": 23010.0},
                "ohlc_is_closed": True,
            }

            response = server.app.test_client().get("/entry/status?symbols=NQ")
            payload = response.get_json()["symbols"][0]

            self.assertEqual(response.status_code, 200)
            self.assertEqual(payload["liquidity_lock"]["session_date"], current_session)
            self.assertEqual(payload["liquidity_lock"]["last_tv_context_session_date"], current_session)
            self.assertEqual(payload["liquidity_lock"]["frozen_liquidity_levels"]["PMH"]["price"], 23025.0)
            self.assertIsNone(payload.get("step2_confirmed_at"))
            self.assertIsNone(payload.get("step4_confirmed_at"))
            self.assertIsNot(payload.get("trade_state", {}).get("active"), True)

    def test_entry_status_does_not_publish_prior_session_bar_as_current_market_snapshot(self):
        server = self._load_server()
        entry_agent = sys.modules["entry_agent"]
        market_feed = sys.modules["market_feed"]

        originals = {}
        for module, attr, name in (
            (entry_agent, "TV_CONTEXT_PATH", "tv_context.json"),
            (entry_agent, "TV_CONTEXT_BY_SYMBOL_PATH", "tv_context_by_symbol.json"),
            (entry_agent, "STATE_PATH", "entry_agent_state.json"),
            (market_feed, "RITHMIC_BARS_PATH", "rithmic_recent_bars.json"),
            (market_feed, "EXECUTOR_STATE_PATH", "executor_state.json"),
            (market_feed, "urlopen", None),
        ):
            originals[(id(module), attr)] = getattr(module, attr)
            self.addCleanup(setattr, module, attr, getattr(module, attr))

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entry_agent.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            entry_agent.STATE_PATH = temp_path / "entry_agent_state.json"
            market_feed.RITHMIC_BARS_PATH = temp_path / "rithmic_recent_bars.json"
            market_feed.EXECUTOR_STATE_PATH = temp_path / "executor_state.json"
            market_feed.urlopen = lambda *args, **kwargs: (_ for _ in ()).throw(OSError("offline"))

            current_session = "2026-07-09"
            current_context = {
                "source": "tradingview_level_helper",
                "symbol": "NQ1!",
                "normalized_symbol": "NQ",
                "received_at": "2026-07-09T13:30:00Z",
                "session_date": current_session,
                "last_tv_context_received_at": "2026-07-09T13:30:00Z",
                "last_tv_context_session_date": current_session,
                "locked": True,
                "liquidity_context_locked": True,
                "liquidity_context_locked_at": "2026-07-09T13:15:00Z",
                "levels": {
                    "PMH": {"price": 29786.5, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    "PML": {"price": 29681.0, "status": "ACTIVE", "stack_group": "NONE"},
                },
                "locked_liquidity_context": {
                    "levels": {
                        "PMH": {"price": 29786.5, "status": "ACTIVE", "stack_group": "HIGH 1"},
                        "PML": {"price": 29681.0, "status": "ACTIVE", "stack_group": "NONE"},
                    },
                    "liquidity_map": {
                        "levels": [
                            {"name": "PMH", "price": 29786.5, "status": "ACTIVE", "stack_group": "HIGH 1"},
                            {"name": "PML", "price": 29681.0, "status": "ACTIVE", "stack_group": "NONE"},
                        ],
                        "stacks": [],
                    },
                    "session_date": current_session,
                    "locked_at": "2026-07-09T13:15:00Z",
                    "source": "tradingview_level_helper",
                    "daily_atr14": 724.0,
                    "midpoints": {},
                    "exhaustion_boundaries": {},
                },
            }
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps({"symbols": {"NQ": current_context}}, indent=2) + "\n",
                encoding="utf-8",
            )
            entry_agent.TV_CONTEXT_PATH.write_text(json.dumps(current_context, indent=2) + "\n", encoding="utf-8")
            entry_agent.STATE_PATH.write_text(json.dumps({}), encoding="utf-8")
            market_feed.EXECUTOR_STATE_PATH.write_text(
                json.dumps(
                    {
                        "orders": {
                            "old-order": {
                                "symbol": "NQU6",
                                "updated_at": "2026-07-08T18:52:30Z",
                                "filled_price": 29408.0,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            market_feed.RITHMIC_BARS_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQU6": [
                                {
                                    "timestamp": "2026-07-08T18:52:00Z",
                                    "symbol": "NQU6",
                                    "open": 29404.0,
                                    "high": 29408.0,
                                    "low": 29403.75,
                                    "close": 29408.0,
                                }
                            ]
                        }
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            response = server.app.test_client().get("/entry/status?symbols=NQ")
            payload = response.get_json()["symbols"][0]

            self.assertEqual(response.status_code, 200)
            self.assertEqual(payload["liquidity_lock"]["session_date"], current_session)
            self.assertIsNone(payload["candle_time"])
            self.assertIsNone(payload["candle_open"])
            self.assertIsNone(payload["candle_high"])
            self.assertIsNone(payload["candle_low"])
            self.assertIsNone(payload["candle_close"])
            self.assertEqual(payload["wait_reason"], "No market price available.")

    def test_entry_status_cors_preflight_returns_allow_headers(self):
        server = self._load_server()
        response = server.app.test_client().options(
            "/entry/status?symbols=NQ,YM,RTY",
            headers={
                "Origin": "http://localhost:7001",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "*")
        self.assertIn("GET", response.headers.get("Access-Control-Allow-Methods", ""))
        self.assertEqual(response.headers.get("Access-Control-Allow-Headers"), "*")

    def test_entry_status_get_returns_cors_header(self):
        server = self._load_server()
        server.build_entry_status = lambda symbol: {
            "symbol": symbol,
            "timestamp": "2026-05-05T00:00:00+00:00",
            "current_step": "Step 3",
            "active_liquidity_name": "ONH",
            "active_liquidity_price": 50100,
            "setup_direction": None,
            "leg1_status": "WAIT",
            "leg2_status": "WAIT",
            "entry_status": "WAIT",
            "wait_reason": "Leg 1 waiting.",
            "invalidation_reason": None,
            "last_decision": "WAIT: Leg 1 waiting.",
        }

        response = server.app.test_client().get(
            "/entry/status?symbols=NQ",
            headers={"Origin": "http://localhost:7001"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "*")

    def test_entry_status_does_not_append_decision_log_or_mutate_throttle_cache(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.ENTRY_LOG_DIR = temp_path / "logs"
            server.ENTRY_DECISIONS_LOG_PATH = server.ENTRY_LOG_DIR / "entry_decisions.jsonl"
            server.ENTRY_DECISION_LAST_LOGGED.clear()
            state = {"step": "Step 3"}

            def fake_status(symbol):
                return {
                    "symbol": symbol,
                    "timestamp": "2026-05-05T00:00:00+00:00",
                    "current_step": state["step"],
                    "active_liquidity_name": "ONH",
                    "active_liquidity_price": 50100,
                    "setup_direction": "SHORT",
                    "leg1_status": "WAIT",
                    "leg2_status": "WAIT",
                    "entry_status": "WAIT",
                    "wait_reason": "Leg 1 waiting.",
                    "invalidation_reason": None,
                    "last_decision": f"WAIT: {state['step']}",
                }

            server.build_entry_status = fake_status
            client = server.app.test_client()

            first = client.get("/entry/status?symbols=NQ")
            second = client.get("/entry/status?symbols=NQ")
            state["step"] = "Step 4"
            third = client.get("/entry/status?symbols=NQ")

            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(third.status_code, 200)
            self.assertFalse(server.ENTRY_DECISIONS_LOG_PATH.exists())
            self.assertEqual(server.ENTRY_DECISION_LAST_LOGGED, {})

    def test_entry_log_debug_endpoint_returns_tail_limit(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.ENTRY_LOG_DIR = temp_path / "logs"
            server.ENTRY_DECISIONS_LOG_PATH = server.ENTRY_LOG_DIR / "entry_decisions.jsonl"
            server.ENTRY_LOG_DIR.mkdir(parents=True, exist_ok=True)
            server.ENTRY_DECISIONS_LOG_PATH.write_text(
                "\n".join(
                    json.dumps({"timestamp": f"t{i}", "symbol": "NQ", "current_step": f"Step {i}"})
                    for i in range(3)
                ) + "\n",
                encoding="utf-8",
            )

            response = server.app.test_client().get("/debug/entry-log?limit=2")
            payload = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["count"], 2)
            self.assertEqual([record["current_step"] for record in payload["records"]], ["Step 1", "Step 2"])

    def test_entry_status_does_not_append_reasoning_log_or_mutate_reasoning_cache(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.ENTRY_REASONING_DIR = temp_path / "reasoning"
            server.ENTRY_REASONING_LAST_LOGGED.clear()
            state = {"step": "Step 3", "candle_time": "2026-05-06T13:00:00Z"}

            def fake_status(symbol):
                return {
                    "symbol": symbol,
                    "timestamp": "2026-05-06T13:00:01+00:00",
                    "candle_time": state["candle_time"],
                    "candle_open": 50000,
                    "candle_high": 50010,
                    "candle_low": 49990,
                    "candle_close": 50005,
                    "current_step": state["step"],
                    "active_liquidity_name": "ONH",
                    "liquidity_price": 50000,
                    "liquidity_group": None,
                    "close_vs_level": 5,
                    "setup_direction": "SHORT",
                    "rejection_mode_entered": True,
                    "sr_rs_context": "Normal Rejection Mode",
                    "leg1_state": "WAIT",
                    "leg1_locked": False,
                    "leg1_reference_price": None,
                    "leg1_completed_at": None,
                    "fifty_percent_rule_phase": "pre_leg1_only",
                    "leg2_state": "WAIT",
                    "leg2_candidate_candle_time": None,
                    "leg2_reference_price": None,
                    "leg2_25_percent_rule_passed": None,
                    "entry_status": "WAIT",
                    "invalidation_source": None,
                    "invalidation_reason": None,
                    "wait_reason": "Leg 1 waiting.",
                    "last_decision": f"WAIT: {state['step']}",
                }

            server.build_entry_status = fake_status
            client = server.app.test_client()
            first = client.get("/entry/status?symbols=YM")
            duplicate = client.get("/entry/status?symbols=YM")
            state["step"] = "Step 4"
            transition = client.get("/entry/status?symbols=YM")
            state["candle_time"] = "2026-05-06T13:01:00Z"
            new_candle = client.get("/entry/status?symbols=YM")

            self.assertEqual(first.status_code, 200)
            self.assertEqual(duplicate.status_code, 200)
            self.assertEqual(transition.status_code, 200)
            self.assertEqual(new_candle.status_code, 200)
            self.assertFalse(server.ENTRY_REASONING_DIR.exists())
            self.assertEqual(server.ENTRY_REASONING_LAST_LOGGED, {})

    def test_entry_reasoning_log_endpoint_filters_symbols_and_date(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.DATA_DIR = temp_path / "Data"
            server.DATA_DIR.mkdir(parents=True, exist_ok=True)
            server.reasoning_log_path("2026-05-06").write_text(
                "\n".join(
                    [
                        json.dumps({"timestamp": "t1", "symbol": "NQ", "step": "Step 2"}),
                        json.dumps({"timestamp": "t2", "symbol": "YM", "step": "Step 4"}),
                        json.dumps({"timestamp": "t3", "symbol": "RTY", "step": "Step 5"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            one = server.app.test_client().get("/entry/reasoning_log?symbols=YM&date=2026-05-06")
            many = server.app.test_client().get("/entry/reasoning_log?symbols=NQ,YM,RTY&date=2026-05-06")

            self.assertEqual(one.status_code, 200)
            self.assertEqual(one.get_json()["count"], 1)
            self.assertEqual(one.get_json()["records"][0]["symbol"], "YM")
            self.assertEqual(many.status_code, 200)
            self.assertEqual(many.get_json()["count"], 3)

    def test_command_center_entry_agent_fetch_is_simple_get(self):
        html = (ROOT / "command_center.html").read_text(encoding="utf-8")
        marker = "async function refreshEntryAgentStatus()"
        start = html.index(marker)
        end = html.index("async function forceRefreshAll", start)
        snippet = html[start:end]

        self.assertIn('const ENTRY_AGENT_BASE = "http://127.0.0.1:7002";', html)
        self.assertIn('method: "GET"', snippet)
        self.assertIn('mode: "cors"', snippet)
        self.assertNotIn("fetchJson", snippet)
        self.assertNotIn("headers", snippet)
        self.assertNotIn("Content-Type", snippet)
        self.assertNotIn("Authorization", snippet)

    def test_tv_context_receiver_stores_context_by_symbol_and_debug_returns_it(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.LEVELS_PATH = temp_path / "levels.json"
            server.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.TV_CONTEXT_EVENTS_PATH = temp_path / "tv_context_events.jsonl"
            server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()

            response = server.app.test_client().post(
                "/webhook/tv-context",
                json={
                    "source": "tradingview_level_helper",
                    "symbol": "CBOT_MINI:YM1!",
                    "ONH_price": 50100,
                    "ONL_price": 49900,
                },
            )
            payload = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["normalized_symbol"], "YM")
            self.assertEqual(payload["context"]["source"], "tradingview_level_helper")

            debug_response = server.app.test_client().get("/debug/tv-context?symbol=YMM6")
            debug_payload = debug_response.get_json()

            self.assertEqual(debug_response.status_code, 200)
            self.assertEqual(debug_payload["price_truth"], "Rithmic")
            self.assertEqual(debug_payload["symbols"]["YM"]["ONH_price"], 50100)
            self.assertEqual(debug_payload["symbols"]["YM"]["normalized_symbol"], "YM")

            levels_payload = json.loads(server.LEVELS_BY_SYMBOL_PATH.read_text(encoding="utf-8"))
            self.assertEqual(levels_payload["symbols"]["YM"]["ONH"], 50100.0)

    def test_tv_context_receiver_keeps_nested_level_tables_isolated_by_ingest_order(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.LEVELS_PATH = temp_path / "levels.json"
            server.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.TV_CONTEXT_EVENTS_PATH = temp_path / "tv_context_events.jsonl"
            server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
            client = server.app.test_client()

            client.post(
                "/webhook/tv-context",
                json={
                    "source": "tradingview_level_helper",
                    "symbol": "NQ1!",
                    "levels": {
                        "PML": {"price": 28392.0, "status": "ACTIVE", "stack_group": "NONE"}
                    },
                },
            )
            client.post(
                "/webhook/tv-context",
                json={
                    "source": "tradingview_level_helper",
                    "symbol": "RTY1!",
                    "levels": {
                        "PML": {"price": 2878.9, "status": "ACTIVE", "stack_group": "NONE"}
                    },
                },
            )
            levels_payload = json.loads(server.LEVELS_BY_SYMBOL_PATH.read_text(encoding="utf-8"))
            self.assertEqual(levels_payload["symbols"]["NQ"]["PML"], 28392.0)
            self.assertEqual(levels_payload["symbols"]["RTY"]["PML"], 2878.9)

            client.post(
                "/webhook/tv-context",
                json={
                    "source": "tradingview_level_helper",
                    "symbol": "NQ1!",
                    "levels": {
                        "PML": {"price": 28393.0, "status": "ACTIVE", "stack_group": "NONE"}
                    },
                },
            )
            levels_payload = json.loads(server.LEVELS_BY_SYMBOL_PATH.read_text(encoding="utf-8"))
            # Post-lock helper updates must preserve the first valid session liquidity table.
            self.assertEqual(levels_payload["symbols"]["NQ"]["PML"], 28392.0)
            self.assertEqual(levels_payload["symbols"]["RTY"]["PML"], 2878.9)

    def test_tv_context_receiver_locks_615_session_liquidity_context_and_ignores_later_stack_mutation(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.LEVELS_PATH = temp_path / "levels.json"
            server.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.TV_CONTEXT_EVENTS_PATH = temp_path / "tv_context_events.jsonl"
            server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
            client = server.app.test_client()

            # The first valid 6:15 AM PT table becomes the session truth for stack ownership.
            first = client.post(
                "/webhook/tv-context",
                json={
                    "source": "tradingview_level_helper",
                    "symbol": "NQ1!",
                    "timestamp": "2026-06-19T13:15:00Z",
                    "levels": {
                        "LH": {"price": 30666.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                        "PMH": {"price": 30670.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                        "ONH": {"price": 30770.75, "status": "ACTIVE", "stack_group": "HIGH 2"},
                        "YH": {"price": 30783.25, "status": "ACTIVE", "stack_group": "HIGH 2"},
                        "LL": {"price": 30535.75, "status": "ACTIVE", "stack_group": "LOW 1"},
                        "PML": {"price": 30525.25, "status": "ACTIVE", "stack_group": "LOW 1"},
                        "ONL": {"price": 30388.0, "status": "ACTIVE", "stack_group": "LOW 2"},
                        "YL": {"price": 30391.0, "status": "ACTIVE", "stack_group": "LOW 2"},
                    },
                },
            )
            first_payload = first.get_json()

            self.assertEqual(first.status_code, 200)
            self.assertTrue(first_payload["context"]["liquidity_context_locked"])
            self.assertEqual(first_payload["context"]["liquidity_context_source"], "tradingview_level_helper")
            self.assertEqual(first_payload["context"]["levels"]["LH"]["stack_group"], "HIGH 1")
            self.assertEqual(first_payload["context"]["levels"]["PMH"]["stack_group"], "HIGH 1")
            self.assertEqual(first_payload["context"]["levels"]["ONH"]["stack_group"], "HIGH 2")
            self.assertEqual(first_payload["context"]["levels"]["YH"]["stack_group"], "HIGH 2")

            locked_at = first_payload["context"]["liquidity_context_locked_at"]

            second = client.post(
                "/webhook/tv-context",
                json={
                    "source": "tradingview_level_helper",
                    "symbol": "NQ1!",
                    "timestamp": "2026-06-19T13:30:00Z",
                    "levels": {
                        "LH": {"price": 30666.0, "status": "ACTIVE", "stack_group": "NONE"},
                        "PMH": {"price": 30670.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                        "ONH": {"price": 30770.75, "status": "ACTIVE", "stack_group": "HIGH 1"},
                        "YH": {"price": 30783.25, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    },
                    "heartbeat": {"bar_status": "closed"},
                },
            )
            second_payload = second.get_json()
            stored = json.loads(server.TV_CONTEXT_BY_SYMBOL_PATH.read_text(encoding="utf-8"))
            nq = stored["symbols"]["NQ"]

            self.assertEqual(second.status_code, 200)
            self.assertEqual(second_payload["context"]["liquidity_context_locked_at"], locked_at)
            self.assertEqual(nq["levels"]["LH"]["stack_group"], "HIGH 1")
            self.assertEqual(nq["levels"]["PMH"]["stack_group"], "HIGH 1")
            self.assertEqual(nq["levels"]["ONH"]["stack_group"], "HIGH 2")
            self.assertEqual(nq["levels"]["YH"]["stack_group"], "HIGH 2")
            self.assertEqual(nq["heartbeat"]["bar_status"], "closed")

    def test_load_tv_context_uses_locked_session_liquidity_context_not_later_mutable_payload(self):
        server = self._load_server()
        import entry_agent
        original_by_symbol_path = entry_agent.TV_CONTEXT_BY_SYMBOL_PATH
        self.addCleanup(setattr, entry_agent, "TV_CONTEXT_BY_SYMBOL_PATH", original_by_symbol_path)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.LEVELS_PATH = temp_path / "levels.json"
            server.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.TV_CONTEXT_EVENTS_PATH = temp_path / "tv_context_events.jsonl"
            server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
            entry_agent.TV_CONTEXT_BY_SYMBOL_PATH = server.TV_CONTEXT_BY_SYMBOL_PATH
            client = server.app.test_client()

            client.post(
                "/webhook/tv-context",
                json={
                    "source": "tradingview_level_helper",
                    "symbol": "NQ1!",
                    "timestamp": "2026-06-19T13:15:00Z",
                    "levels": {
                        "LH": {"price": 30666.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                        "PMH": {"price": 30670.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                        "ONH": {"price": 30770.75, "status": "ACTIVE", "stack_group": "HIGH 2"},
                        "YH": {"price": 30783.25, "status": "ACTIVE", "stack_group": "HIGH 2"},
                    },
                },
            )
            client.post(
                "/webhook/tv-context",
                json={
                    "source": "tradingview_level_helper",
                    "symbol": "NQ1!",
                    "timestamp": "2026-06-19T13:31:00Z",
                    "levels": {
                        "LH": {"price": 30666.0, "status": "ACTIVE", "stack_group": "NONE"},
                        "PMH": {"price": 30670.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                        "ONH": {"price": 30770.75, "status": "ACTIVE", "stack_group": "HIGH 1"},
                        "YH": {"price": 30783.25, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    },
                },
            )

            loaded = entry_agent.load_tv_context("NQM6")

            # Replay and live reads must resolve from the locked 6:15 session table.
            self.assertEqual(loaded["levels"]["LH"]["stack_group"], "HIGH 1")
            self.assertEqual(loaded["levels"]["PMH"]["stack_group"], "HIGH 1")
            self.assertEqual(loaded["levels"]["ONH"]["stack_group"], "HIGH 2")
            self.assertEqual(loaded["levels"]["YH"]["stack_group"], "HIGH 2")
            self.assertTrue(loaded["liquidity_context_locked"])

    def test_tv_context_receiver_replaces_stale_same_session_lock_and_clears_only_target_symbol_state(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.LEVELS_PATH = temp_path / "levels.json"
            server.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.TV_CONTEXT_EVENTS_PATH = temp_path / "tv_context_events.jsonl"
            server.ENTRY_AGENT_STATE_PATH = temp_path / "entry_agent_state.json"
            server.OPERATOR_AUDIT_LOG_PATH = temp_path / "operator_actions.jsonl"
            server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
            client = server.app.test_client()

            session_date = "2026-06-30"
            stale_nq_levels = {
                "PMH": {"price": 30142.75, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "PML": {"price": 30004.75, "status": "ACTIVE", "stack_group": "LOW 1"},
                "LH": {"price": 30175.5, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "ONH": {"price": 30217.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "ONL": {"price": 29934.75, "status": "ACTIVE", "stack_group": "LOW 1"},
                "YL": {"price": 29273.75, "status": "ACTIVE", "stack_group": "NONE"},
            }
            fresh_nq_levels = {
                "PMH": {"price": 30395.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "LH": {"price": 30435.25, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "ONH": {"price": 30553.75, "status": "ACTIVE", "stack_group": "HIGH 2"},
                "YH": {"price": 30610.0, "status": "ACTIVE", "stack_group": "HIGH 2"},
                "PML": {"price": 30220.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "ONL": {"price": 30110.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "YL": {"price": 29900.0, "status": "ACTIVE", "stack_group": "NONE"},
            }
            ym_levels = {
                "PMH": {"price": 52615.0, "status": "ACTIVE", "stack_group": "NONE"},
                "PML": {"price": 52493.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "LH": {"price": 52714.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "ONH": {"price": 52714.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "ONL": {"price": 52468.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "YL": {"price": 52324.0, "status": "ACTIVE", "stack_group": "NONE"},
            }
            stale_nq_context = {
                "source": "tradingview_level_helper",
                "symbol": "NQ1!",
                "normalized_symbol": "NQ",
                "received_at": "2026-07-01T06:46:03.235805Z",
                "session_date": session_date,
                "levels": copy.deepcopy(stale_nq_levels),
                "last_tv_context_received_at": "2026-07-01T06:46:03.235805Z",
                "last_tv_context_session_date": session_date,
                "last_tv_context_levels": copy.deepcopy(stale_nq_levels),
                "locked_liquidity_context": {
                    "levels": copy.deepcopy(stale_nq_levels),
                    "liquidity_map": {
                        "levels": [
                            {"name": name, "price": details["price"], "status": details["status"], "stack_group": details["stack_group"]}
                            for name, details in stale_nq_levels.items()
                        ],
                        "stacks": [],
                    },
                    "session_date": session_date,
                    "locked_at": "2026-07-01T06:46:03.235805Z",
                    "source": "tradingview_level_helper",
                    "session_lock_price": None,
                    "daily_atr14": 729.2,
                    "midpoints": {},
                    "exhaustion_boundaries": {},
                },
                "liquidity_context_locked": True,
                "liquidity_context_locked_at": "2026-07-01T06:46:03.235805Z",
                "liquidity_context_source": "tradingview_level_helper",
                "locked": True,
            }
            ym_context = {
                "source": "tradingview_level_helper",
                "symbol": "YM1!",
                "normalized_symbol": "YM",
                "received_at": "2026-07-01T06:51:18.787172Z",
                "session_date": session_date,
                "levels": copy.deepcopy(ym_levels),
                "last_tv_context_received_at": "2026-07-01T06:51:18.787172Z",
                "last_tv_context_session_date": session_date,
                "last_tv_context_levels": copy.deepcopy(ym_levels),
                "locked_liquidity_context": {
                    "levels": copy.deepcopy(ym_levels),
                    "liquidity_map": {
                        "levels": [
                            {"name": name, "price": details["price"], "status": details["status"], "stack_group": details["stack_group"]}
                            for name, details in ym_levels.items()
                        ],
                        "stacks": [],
                    },
                    "session_date": session_date,
                    "locked_at": "2026-06-30T13:15:00Z",
                    "source": "tradingview_level_helper",
                    "session_lock_price": 52615.0,
                    "daily_atr14": 654.8,
                    "midpoints": {},
                    "exhaustion_boundaries": {},
                },
                "liquidity_context_locked": True,
                "liquidity_context_locked_at": "2026-06-30T13:15:00Z",
                "liquidity_context_source": "tradingview_level_helper",
                "locked": True,
            }
            server.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps({"symbols": {"NQ": stale_nq_context, "YM": ym_context}}, indent=2) + "\n",
                encoding="utf-8",
            )
            server.TV_CONTEXT_PATH.write_text(json.dumps(stale_nq_context, indent=2) + "\n", encoding="utf-8")

            stale_nq_lock = server.build_session_locked_tv_context(stale_nq_context)
            ym_lock = server.build_session_locked_tv_context(ym_context)
            server.ENTRY_AGENT_STATE_PATH.write_text(
                json.dumps(
                    {
                        "state_by_symbol": {
                            "NQ": {
                                "normalized_symbol": "NQ",
                                "step_2_1a": {"active_level": "ONH", "level_price": 30217.0},
                                "step2_locked_owner": {"active_liquidity_name": "ONH", "active_liquidity_price": 30217.0},
                                "rejection_lane": {"active_liquidity_price": 30217.0, "close_boundary": 30142.75, "extreme_boundary": 30217.0},
                                "continuation_lane": {"active_liquidity_price": 30217.0, "close_boundary": 30142.75, "extreme_boundary": 30217.0},
                                "session_liquidity_context": stale_nq_lock,
                                "event_log": [],
                            },
                            "YM": {
                                "normalized_symbol": "YM",
                                "step_2_1a": {"active_level": "ONL", "level_price": 52468.0},
                                "rejection_lane": {"active_liquidity_price": 52468.0, "close_boundary": 52493.0, "extreme_boundary": 52468.0},
                                "continuation_lane": {"active_liquidity_price": 52714.0, "close_boundary": 52714.0, "extreme_boundary": 52714.0},
                                "session_liquidity_context": ym_lock,
                                "event_log": [],
                            },
                        }
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            response = client.post(
                "/webhook/tv-context",
                json={
                    "source": "tradingview_level_helper",
                    "symbol": "NQ1!",
                    "timestamp": "2026-07-01T06:51:01.726441Z",
                    "session_date": session_date,
                    "locked": True,
                    "liquidity_context_locked": True,
                    "liquidity_context_locked_at": "2026-07-01T06:51:01.726441Z",
                    "levels": copy.deepcopy(fresh_nq_levels),
                },
            )
            payload = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["normalized_symbol"], "NQ")
            self.assertEqual(payload["context"]["levels"]["PMH"]["price"], 30395.0)
            self.assertEqual(payload["context"]["levels"]["ONH"]["price"], 30553.75)
            self.assertEqual(payload["context"]["liquidity_context_locked_at"], "2026-07-01T06:51:01.726441Z")

            stored_contexts = json.loads(server.TV_CONTEXT_BY_SYMBOL_PATH.read_text(encoding="utf-8"))
            nq_context = stored_contexts["symbols"]["NQ"]
            ym_context_after = stored_contexts["symbols"]["YM"]
            self.assertEqual(nq_context["locked_liquidity_context"]["levels"]["PMH"]["price"], 30395.0)
            self.assertEqual(nq_context["locked_liquidity_context"]["levels"]["LH"]["price"], 30435.25)
            self.assertEqual(nq_context["locked_liquidity_context"]["levels"]["ONH"]["price"], 30553.75)
            self.assertEqual(nq_context["locked_liquidity_context"]["locked_at"], "2026-07-01T06:51:01.726441Z")
            self.assertEqual(ym_context_after, ym_context)

            state = json.loads(server.ENTRY_AGENT_STATE_PATH.read_text(encoding="utf-8"))
            nq_state = state["state_by_symbol"]["NQ"]
            ym_state = state["state_by_symbol"]["YM"]
            self.assertNotIn("step_2_1a", nq_state)
            self.assertNotIn("step2_locked_owner", nq_state)
            self.assertNotIn("rejection_lane", nq_state)
            self.assertNotIn("continuation_lane", nq_state)
            self.assertIn("session_liquidity_context", nq_state)
            self.assertEqual(nq_state["session_liquidity_context"]["tv_context"]["levels"]["PMH"]["price"], 30395.0)
            self.assertEqual(nq_state["session_liquidity_context"]["active_groups"][0]["close_boundary"], 30395.0)
            self.assertEqual(ym_state["session_liquidity_context"], ym_lock)
            self.assertIn("step_2_1a", ym_state)
            self.assertIn("rejection_lane", ym_state)
            self.assertIn("continuation_lane", ym_state)
            self.assertEqual(len(nq_state["event_log"]), 1)
            self.assertEqual(nq_state["event_log"][0]["event"], "stale_liquidity_lock_replaced_from_newer_tv_context")
            self.assertEqual(nq_state["event_log"][0]["previous_levels"]["PMH"]["price"], 30142.75)
            self.assertEqual(nq_state["event_log"][0]["incoming_levels"]["PMH"]["price"], 30395.0)

            audit_records = [
                json.loads(line)
                for line in server.OPERATOR_AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(audit_records), 1)
            self.assertEqual(audit_records[0]["event"], "stale_liquidity_lock_replaced_from_newer_tv_context")
            self.assertEqual(audit_records[0]["symbol"], "NQ")
            self.assertIn("step_2_1a", audit_records[0]["cleared_fields"])

    def test_tv_context_receiver_replaces_prior_session_locked_context_and_clears_only_target_symbol_state(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.LEVELS_PATH = temp_path / "levels.json"
            server.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.ENTRY_AGENT_STATE_PATH = temp_path / "entry_agent_state.json"
            server.OPERATOR_AUDIT_LOG_PATH = temp_path / "operator_actions.jsonl"
            server.TV_CONTEXT_EVENTS_PATH = temp_path / "tv_context_events.jsonl"
            server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
            client = server.app.test_client()

            previous_session = "2026-06-30"
            incoming_session = "2026-07-01"
            stale_ym_levels = {
                "PML": {"price": 52493.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "ONL": {"price": 52468.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "YL": {"price": 52324.0, "status": "ACTIVE", "stack_group": "NONE"},
            }
            fresh_ym_levels = {
                "PML": {"price": 52461.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "ONL": {"price": 52427.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "YL": {"price": 52383.0, "status": "ACTIVE", "stack_group": "LOW 1"},
            }
            nq_levels = {
                "PMH": {"price": 30395.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
            }
            stale_ym_context = {
                "source": "tradingview_level_helper",
                "symbol": "YM1!",
                "normalized_symbol": "YM",
                "received_at": "2026-06-30T13:15:00Z",
                "session_date": previous_session,
                "levels": copy.deepcopy(stale_ym_levels),
                "last_tv_context_received_at": "2026-06-30T13:15:00Z",
                "last_tv_context_session_date": previous_session,
                "last_tv_context_levels": copy.deepcopy(stale_ym_levels),
                "locked_liquidity_context": {
                    "levels": copy.deepcopy(stale_ym_levels),
                    "liquidity_map": {
                        "levels": [
                            {"name": name, "price": details["price"], "status": details["status"], "stack_group": details["stack_group"]}
                            for name, details in stale_ym_levels.items()
                        ],
                        "stacks": [],
                    },
                    "session_date": previous_session,
                    "locked_at": "2026-06-30T13:15:00Z",
                    "source": "tradingview_level_helper",
                    "session_lock_price": None,
                    "daily_atr14": 654.8,
                    "midpoints": {},
                    "exhaustion_boundaries": {},
                },
                "liquidity_context_locked": True,
                "liquidity_context_locked_at": "2026-06-30T13:15:00Z",
                "liquidity_context_source": "tradingview_level_helper",
                "locked": True,
            }
            nq_context = {
                "source": "tradingview_level_helper",
                "symbol": "NQ1!",
                "normalized_symbol": "NQ",
                "received_at": "2026-07-01T06:51:01.726441Z",
                "session_date": incoming_session,
                "levels": copy.deepcopy(nq_levels),
                "last_tv_context_received_at": "2026-07-01T06:51:01.726441Z",
                "last_tv_context_session_date": incoming_session,
                "last_tv_context_levels": copy.deepcopy(nq_levels),
                "locked_liquidity_context": {
                    "levels": copy.deepcopy(nq_levels),
                    "liquidity_map": {"levels": [{"name": "PMH", "price": 30395.0, "status": "ACTIVE", "stack_group": "HIGH 1"}], "stacks": []},
                    "session_date": incoming_session,
                    "locked_at": "2026-07-01T06:51:01.726441Z",
                    "source": "tradingview_level_helper",
                    "session_lock_price": None,
                    "daily_atr14": 729.2,
                    "midpoints": {},
                    "exhaustion_boundaries": {},
                },
                "liquidity_context_locked": True,
                "liquidity_context_locked_at": "2026-07-01T06:51:01.726441Z",
                "liquidity_context_source": "tradingview_level_helper",
                "locked": True,
            }
            server.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps({"symbols": {"YM": stale_ym_context, "NQ": nq_context}}, indent=2) + "\n",
                encoding="utf-8",
            )
            server.TV_CONTEXT_PATH.write_text(json.dumps(stale_ym_context, indent=2) + "\n", encoding="utf-8")

            stale_ym_lock = server.build_session_locked_tv_context(stale_ym_context)
            nq_lock = server.build_session_locked_tv_context(nq_context)
            server.ENTRY_AGENT_STATE_PATH.write_text(
                json.dumps(
                    {
                        "state_by_symbol": {
                            "YM": {
                                "normalized_symbol": "YM",
                                "step_2_1a": {"active_level": "ONL", "level_price": 52468.0},
                                "step2_locked_owner": {"active_liquidity_name": "PML/ONL", "close_boundary": 52493.0, "extreme_boundary": 52468.0},
                                "rejection": {"rejection_mode": "ON", "watch_side": "LONG"},
                                "step25": {"status": "READY", "state": {"controlling_mode": "R/S"}},
                                "step3": {"status": "ALLOW_STEP_4", "state": {"step3_allows_structure": True}},
                                "step4": {"status": "READY", "state": {"leg1_state_locked": True, "leg1_status": "COMPLETE", "step4_confirmed_at": "2026-06-30T13:31:00Z"}},
                                "step5": {"status": "WAIT", "state": {"leg2_status": "WAIT", "leg2_wait_reason": "waiting"}},
                                "step6": {"status": "WAIT", "state": {"step6_window_active": True}},
                                "rejection_lane": {"active_liquidity_price": 52468.0, "close_boundary": 52493.0, "extreme_boundary": 52468.0},
                                "continuation_lane": {"active_liquidity_price": 52468.0, "close_boundary": 52493.0, "extreme_boundary": 52468.0},
                                "gateway": {"current_step": "Step 5"},
                                "session_liquidity_context": stale_ym_lock,
                                "trade_state": {"active": True, "selected_pathway": "rejection"},
                                "market_state": {"active_liquidity_name": "PML/ONL"},
                                "consumed_liquidity_levels": [{"key": "PML:52493.0"}],
                                "consumed_entry_setups": [{"key": "old"}],
                                "event_log": [],
                            },
                            "NQ": {
                                "normalized_symbol": "NQ",
                                "step_2_1a": {"active_level": "PMH", "level_price": 30395.0},
                                "rejection_lane": {"active_liquidity_price": 30395.0, "close_boundary": 30395.0, "extreme_boundary": 30395.0},
                                "session_liquidity_context": nq_lock,
                                "event_log": [],
                            },
                        }
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            response = client.post(
                "/webhook/tv-context",
                json={
                    "source": "tradingview_level_helper",
                    "symbol": "YM1!",
                    "timestamp": "2026-07-01T13:15:00Z",
                    "session_date": incoming_session,
                    "locked": True,
                    "liquidity_context_locked": True,
                    "liquidity_context_locked_at": "2026-07-01T13:15:00Z",
                    "levels": copy.deepcopy(fresh_ym_levels),
                },
            )
            payload = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["normalized_symbol"], "YM")
            self.assertEqual(payload["context"]["session_date"], incoming_session)
            self.assertEqual(payload["context"]["levels"]["PML"]["price"], 52461.0)
            self.assertEqual(payload["context"]["levels"]["ONL"]["price"], 52427.0)
            self.assertEqual(payload["context"]["levels"]["YL"]["price"], 52383.0)

            stored_contexts = json.loads(server.TV_CONTEXT_BY_SYMBOL_PATH.read_text(encoding="utf-8"))
            ym_context = stored_contexts["symbols"]["YM"]
            nq_context_after = stored_contexts["symbols"]["NQ"]
            self.assertEqual(ym_context["session_date"], incoming_session)
            self.assertEqual(ym_context["locked_liquidity_context"]["session_date"], incoming_session)
            self.assertEqual(ym_context["locked_liquidity_context"]["levels"]["PML"]["price"], 52461.0)
            self.assertEqual(ym_context["locked_liquidity_context"]["levels"]["ONL"]["price"], 52427.0)
            self.assertEqual(ym_context["locked_liquidity_context"]["levels"]["YL"]["price"], 52383.0)
            self.assertEqual(nq_context_after, nq_context)

            state = json.loads(server.ENTRY_AGENT_STATE_PATH.read_text(encoding="utf-8"))
            ym_state = state["state_by_symbol"]["YM"]
            nq_state = state["state_by_symbol"]["NQ"]
            self.assertNotIn("step_2_1a", ym_state)
            self.assertNotIn("step2_locked_owner", ym_state)
            self.assertNotIn("rejection", ym_state)
            self.assertNotIn("step25", ym_state)
            self.assertNotIn("step3", ym_state)
            self.assertNotIn("step4", ym_state)
            self.assertNotIn("step5", ym_state)
            self.assertNotIn("step6", ym_state)
            self.assertNotIn("rejection_lane", ym_state)
            self.assertNotIn("continuation_lane", ym_state)
            self.assertNotIn("gateway", ym_state)
            self.assertIn("session_liquidity_context", ym_state)
            self.assertNotIn("trade_state", ym_state)
            self.assertNotIn("market_state", ym_state)
            self.assertNotIn("consumed_liquidity_levels", ym_state)
            self.assertNotIn("consumed_entry_setups", ym_state)
            self.assertEqual(ym_state["session_liquidity_context"]["tv_context"]["session_date"], incoming_session)
            self.assertEqual(ym_state["session_liquidity_context"]["tv_context"]["levels"]["PML"]["price"], 52461.0)
            self.assertEqual(ym_state["session_liquidity_context"]["tv_context"]["levels"]["YL"]["price"], 52383.0)
            self.assertEqual(nq_state["session_liquidity_context"], nq_lock)
            self.assertIn("step_2_1a", nq_state)
            self.assertEqual(len(ym_state["event_log"]), 1)
            self.assertEqual(ym_state["event_log"][0]["event"], "stale_liquidity_lock_replaced_from_newer_tv_context")
            self.assertEqual(ym_state["event_log"][0]["replacement_reason"], "newer_locked_session_rollover")
            self.assertEqual(ym_state["event_log"][0]["previous_session_date"], previous_session)
            self.assertEqual(ym_state["event_log"][0]["incoming_session_date"], incoming_session)

            audit_records = [
                json.loads(line)
                for line in server.OPERATOR_AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(audit_records), 1)
            self.assertEqual(audit_records[0]["event"], "stale_liquidity_lock_replaced_from_newer_tv_context")
            self.assertEqual(audit_records[0]["symbol"], "YM")
            self.assertEqual(audit_records[0]["replacement_reason"], "newer_locked_session_rollover")
            self.assertIn("session_liquidity_context", audit_records[0]["cleared_fields"])

    def test_tv_context_receiver_launching_after_615_locks_first_valid_payload_once(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.LEVELS_PATH = temp_path / "levels.json"
            server.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.TV_CONTEXT_EVENTS_PATH = temp_path / "tv_context_events.jsonl"
            server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
            client = server.app.test_client()

            first = client.post(
                "/webhook/tv-context",
                json={
                    "source": "tradingview_level_helper",
                    "symbol": "NQ1!",
                    "timestamp": "2026-06-19T14:05:00Z",
                    "levels": {
                        "LH": {"price": 30666.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                        "PMH": {"price": 30670.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                    },
                },
            )
            first_payload = first.get_json()
            second = client.post(
                "/webhook/tv-context",
                json={
                    "source": "tradingview_level_helper",
                    "symbol": "NQ1!",
                    "timestamp": "2026-06-19T14:06:00Z",
                    "levels": {
                        "LH": {"price": 30666.0, "status": "ACTIVE", "stack_group": "NONE"},
                        "PMH": {"price": 30670.0, "status": "ACTIVE", "stack_group": "HIGH 9"},
                    },
                },
            )
            second_payload = second.get_json()

            self.assertEqual(first.status_code, 200)
            self.assertTrue(first_payload["context"]["liquidity_context_locked"])
            self.assertEqual(second.status_code, 200)
            self.assertEqual(
                second_payload["context"]["liquidity_context_locked_at"],
                first_payload["context"]["liquidity_context_locked_at"],
            )
            self.assertEqual(second_payload["context"]["levels"]["LH"]["stack_group"], "HIGH 1")
            self.assertEqual(second_payload["context"]["levels"]["PMH"]["stack_group"], "HIGH 1")

    def test_manual_liquidity_lock_override_updates_only_requested_symbol(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.ENTRY_AGENT_STATE_PATH = temp_path / "entry_agent_state.json"
            server.OPERATOR_AUDIT_LOG_PATH = temp_path / "operator_actions.jsonl"
            session_date = server.datetime.now(server.LOCAL_MARKET_TIMEZONE).date().isoformat()

            old_levels = {
                "PMH": {"price": 52394.0, "status": "ACTIVE", "stack_group": "HIGH 2"},
                "LH": {"price": 52457.0, "status": "ACTIVE", "stack_group": "HIGH 2"},
                "ONH": {"price": 52526.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "YH": {"price": 53097.0, "status": "ACTIVE", "stack_group": "HIGH 2"},
                "PML": {"price": 52191.0, "status": "ACTIVE", "stack_group": "LOW 2"},
                "ONL": {"price": 52166.0, "status": "ACTIVE", "stack_group": "LOW 2"},
            }
            corrected_levels = {
                "PMH": {"price": 52394.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "LH": {"price": 52457.0, "status": "ACTIVE", "stack_group": "HIGH 1/HIGH 2"},
                "ONH": {"price": 52526.0, "status": "ACTIVE", "stack_group": "HIGH 2"},
                "YH": {"price": 53097.0, "status": "ACTIVE", "stack_group": "NONE"},
                "PML": {"price": 52191.0, "status": "ACTIVE", "stack_group": "LOW 1"},
                "ONL": {"price": 52166.0, "status": "ACTIVE", "stack_group": "LOW 1"},
            }
            locked_tv_context = {
                "symbol": "CBOT_MINI:YMU2026",
                "normalized_symbol": "YM",
                "source": "tradingview_level_helper",
                "received_at": "2026-06-26T13:15:00Z",
                "session_date": session_date,
                "time_zone": "America/Los_Angeles",
                "locked": True,
                "context_locked": True,
                "locked_for_day": True,
                "liquidity_context_locked_at": "2026-06-26T13:15:05Z",
                "liquidity_context_source": "tradingview_level_helper",
                "levels": copy.deepcopy(old_levels),
                "daily_atr14": 712.0,
            }
            session_lock = server.build_session_locked_tv_context(locked_tv_context)
            self.assertTrue(session_lock["locked"])
            old_lock_payload = {
                "levels": copy.deepcopy(old_levels),
                "liquidity_map": {
                    "levels": [
                        {"name": name, "price": details["price"], "status": details["status"], "stack_group": details["stack_group"]}
                        for name, details in old_levels.items()
                    ]
                },
                "session_date": session_date,
            }
            nq_context = {
                "symbol": "NQ1!",
                "normalized_symbol": "NQ",
                "session_date": session_date,
                "last_tv_context_session_date": session_date,
                "last_tv_context_levels": {
                    "PMH": {"price": 30000.0, "status": "ACTIVE", "stack_group": "HIGH 1"}
                },
                "locked_liquidity_context": {
                    "levels": {
                        "PMH": {"price": 30000.0, "status": "ACTIVE", "stack_group": "HIGH 1"}
                    },
                    "liquidity_map": {"levels": [{"name": "PMH", "price": 30000.0, "status": "ACTIVE", "stack_group": "HIGH 1"}]},
                },
            }
            server.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "YM": {
                                "symbol": "CBOT_MINI:YMU2026",
                                "normalized_symbol": "YM",
                                "session_date": session_date,
                                "last_tv_context_session_date": session_date,
                                "last_tv_context_levels": corrected_levels,
                                "locked_liquidity_context": old_lock_payload,
                            },
                            "NQ": nq_context,
                        }
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            server.TV_CONTEXT_PATH.write_text(
                json.dumps(
                    {
                        "symbol": "CBOT_MINI:YMU2026",
                        "normalized_symbol": "YM",
                        "session_date": session_date,
                        "last_tv_context_session_date": session_date,
                        "last_tv_context_levels": corrected_levels,
                        "locked_liquidity_context": copy.deepcopy(old_lock_payload),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            server.ENTRY_AGENT_STATE_PATH.write_text(
                json.dumps(
                    {
                        "state_by_symbol": {
                            "YM": {"normalized_symbol": "YM", "session_liquidity_context": session_lock, "event_log": []},
                            "NQ": {"normalized_symbol": "NQ", "session_liquidity_context": {"locked": True, "disabled": False, "tv_context": {"session_date": session_date}}, "event_log": []},
                        }
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            response = server.app.test_client().post(
                "/operator/liquidity-lock/override-from-latest-tv",
                json={"symbol": "YM"},
            )
            payload = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["symbol"], "YM")
            self.assertEqual(payload["session_date"], session_date)
            self.assertTrue(payload["frozen_lock_still_locked"])
            self.assertEqual(payload["audit_event"], "liquidity_lock_manual_override_applied")
            self.assertEqual(payload["before_stack_labels"]["PMH"], "HIGH 2")
            self.assertEqual(payload["after_stack_labels"]["PMH"], "HIGH 1")
            self.assertTrue(any(item["name"] == "LH" and item["after"] == "HIGH 1/HIGH 2" for item in payload["levels_changed"]))

            state = json.loads(server.ENTRY_AGENT_STATE_PATH.read_text(encoding="utf-8"))
            ym_state = state["state_by_symbol"]["YM"]["session_liquidity_context"]
            nq_state = state["state_by_symbol"]["NQ"]["session_liquidity_context"]
            self.assertTrue(ym_state["locked"])
            self.assertFalse(ym_state["disabled"])
            self.assertEqual(ym_state["tv_context"]["levels"]["PMH"]["price"], 52394.0)
            self.assertEqual(ym_state["tv_context"]["levels"]["PMH"]["status"], "ACTIVE")
            self.assertEqual(ym_state["tv_context"]["levels"]["PMH"]["stack_group"], "HIGH 1")
            self.assertEqual(ym_state["tv_context"]["levels"]["LH"]["stack_group"], "HIGH 1/HIGH 2")
            self.assertEqual(ym_state["tv_context"]["levels"]["YH"]["stack_group"], "NONE")
            self.assertEqual(ym_state["tv_context"]["session_date"], session_date)
            self.assertEqual(nq_state["tv_context"]["session_date"], session_date)
            self.assertEqual(len(state["state_by_symbol"]["YM"]["event_log"]), 1)
            self.assertEqual(
                state["state_by_symbol"]["YM"]["event_log"][0]["event"],
                "liquidity_lock_manual_override_applied",
            )

            stored_contexts = json.loads(server.TV_CONTEXT_BY_SYMBOL_PATH.read_text(encoding="utf-8"))
            ym_context = stored_contexts["symbols"]["YM"]
            self.assertEqual(ym_context["locked_liquidity_context"]["levels"]["PMH"]["price"], 52394.0)
            self.assertEqual(ym_context["locked_liquidity_context"]["levels"]["PMH"]["status"], "ACTIVE")
            self.assertEqual(ym_context["locked_liquidity_context"]["levels"]["PMH"]["stack_group"], "HIGH 1")
            self.assertEqual(ym_context["locked_liquidity_context"]["levels"]["ONL"]["stack_group"], "LOW 1")
            self.assertEqual(ym_context["last_tv_context_levels"]["LH"]["stack_group"], "HIGH 1/HIGH 2")
            self.assertEqual(stored_contexts["symbols"]["NQ"], nq_context)
            audit_records = [
                json.loads(line)
                for line in server.OPERATOR_AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(audit_records[0]["event"], "liquidity_lock_override_request_received")
            self.assertEqual(audit_records[0]["symbol"], "YM")
            self.assertEqual(audit_records[1]["event"], "liquidity_lock_override_request_completed")
            self.assertEqual(audit_records[1]["status"], "success")
            self.assertIsNone(audit_records[1]["failure_reason"])

    def test_manual_liquidity_lock_override_refuses_incomplete_latest_levels(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.ENTRY_AGENT_STATE_PATH = temp_path / "entry_agent_state.json"
            server.OPERATOR_AUDIT_LOG_PATH = temp_path / "operator_actions.jsonl"
            session_date = server.datetime.now(server.LOCAL_MARKET_TIMEZONE).date().isoformat()
            locked_tv_context = {
                "symbol": "CBOT_MINI:YMU2026",
                "normalized_symbol": "YM",
                "source": "tradingview_level_helper",
                "received_at": "2026-06-26T13:15:00Z",
                "session_date": session_date,
                "time_zone": "America/Los_Angeles",
                "locked": True,
                "context_locked": True,
                "locked_for_day": True,
                "liquidity_context_locked_at": "2026-06-26T13:15:05Z",
                "levels": {
                    "PMH": {"price": 52394.0, "status": "ACTIVE", "stack_group": "HIGH 2"},
                    "LH": {"price": 52457.0, "status": "ACTIVE", "stack_group": "HIGH 2"},
                },
            }
            session_lock = server.build_session_locked_tv_context(locked_tv_context)
            server.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "YM": {
                                "symbol": "CBOT_MINI:YMU2026",
                                "normalized_symbol": "YM",
                                "session_date": session_date,
                                "last_tv_context_session_date": session_date,
                                "last_tv_context_levels": {
                                    "PMH": {"price": 52394.0, "status": "ACTIVE", "stack_group": "HIGH 1"}
                                },
                                "locked_liquidity_context": {
                                    "levels": copy.deepcopy(locked_tv_context["levels"]),
                                    "liquidity_map": {"levels": [{"name": "PMH", "price": 52394.0, "status": "ACTIVE", "stack_group": "HIGH 2"}]},
                                },
                            }
                        }
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            server.ENTRY_AGENT_STATE_PATH.write_text(
                json.dumps(
                    {"state_by_symbol": {"YM": {"normalized_symbol": "YM", "session_liquidity_context": session_lock, "event_log": []}}},
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            response = server.app.test_client().post(
                "/operator/liquidity-lock/override-from-latest-tv",
                json={"symbol": "YM"},
            )
            payload = response.get_json()

            self.assertEqual(response.status_code, 409)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"], "latest_tv_context_levels_incomplete")
            self.assertEqual(payload["missing_levels"], ["LH"])
            audit_records = [
                json.loads(line)
                for line in server.OPERATOR_AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(audit_records[0]["event"], "liquidity_lock_override_request_received")
            self.assertEqual(audit_records[0]["symbol"], "YM")
            self.assertEqual(audit_records[1]["event"], "liquidity_lock_override_request_completed")
            self.assertEqual(audit_records[1]["status"], "failure")
            self.assertEqual(audit_records[1]["failure_reason"], "latest_tv_context_levels_incomplete")

    def test_manual_liquidity_lock_override_rebuilds_from_latest_tv_level_details(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.ENTRY_AGENT_STATE_PATH = temp_path / "entry_agent_state.json"
            session_date = server.datetime.now(server.LOCAL_MARKET_TIMEZONE).date().isoformat()

            old_levels = {
                "PMH": {"price": 52300.0, "status": "ACTIVE", "stack_group": "HIGH 2"},
                "LH": {"price": 52457.0, "status": "ACTIVE", "stack_group": "HIGH 2"},
            }
            corrected_levels = {
                "PMH": {"price": 52394.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
                "LH": {"price": 52457.0, "status": "ACTIVE", "stack_group": "HIGH 1"},
            }
            locked_tv_context = {
                "symbol": "CBOT_MINI:YMU2026",
                "normalized_symbol": "YM",
                "source": "tradingview_level_helper",
                "received_at": "2026-06-26T13:15:00Z",
                "session_date": session_date,
                "time_zone": "America/Los_Angeles",
                "locked": True,
                "context_locked": True,
                "locked_for_day": True,
                "liquidity_context_locked_at": "2026-06-26T13:15:05Z",
                "liquidity_context_source": "tradingview_level_helper",
                "levels": copy.deepcopy(old_levels),
                "daily_atr14": 712.0,
            }
            session_lock = server.build_session_locked_tv_context(locked_tv_context)
            self.assertTrue(session_lock["locked"])

            old_lock_payload = {
                "levels": copy.deepcopy(old_levels),
                "liquidity_map": {
                    "levels": [
                        {"name": name, "price": details["price"], "status": details["status"], "stack_group": details["stack_group"]}
                        for name, details in old_levels.items()
                    ]
                },
                "session_date": session_date,
            }
            server.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "YM": {
                                "symbol": "CBOT_MINI:YMU2026",
                                "normalized_symbol": "YM",
                                "session_date": session_date,
                                "last_tv_context_session_date": session_date,
                                "last_tv_context_received_at": "2026-06-26T14:02:00Z",
                                "last_tv_context_source": "tradingview_level_helper",
                                "last_tv_context_levels": corrected_levels,
                                "locked_liquidity_context": old_lock_payload,
                            }
                        }
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            server.ENTRY_AGENT_STATE_PATH.write_text(
                json.dumps(
                    {"state_by_symbol": {"YM": {"normalized_symbol": "YM", "session_liquidity_context": session_lock, "event_log": []}}},
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            response = server.app.test_client().post(
                "/operator/liquidity-lock/override-from-latest-tv",
                json={"symbol": "YM"},
            )
            payload = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["message"], "SUCCESS: frozen lock updated from latest TV context")

            state = json.loads(server.ENTRY_AGENT_STATE_PATH.read_text(encoding="utf-8"))
            ym_state = state["state_by_symbol"]["YM"]["session_liquidity_context"]
            self.assertEqual(ym_state["tv_context"]["levels"]["PMH"]["price"], 52394.0)
            self.assertEqual(ym_state["tv_context"]["levels"]["PMH"]["status"], "ACTIVE")
            self.assertEqual(ym_state["tv_context"]["levels"]["PMH"]["stack_group"], "HIGH 1")

            stored_contexts = json.loads(server.TV_CONTEXT_BY_SYMBOL_PATH.read_text(encoding="utf-8"))
            ym_context = stored_contexts["symbols"]["YM"]
            self.assertEqual(ym_context["locked_liquidity_context"]["levels"]["PMH"]["price"], 52394.0)
            self.assertEqual(ym_context["locked_liquidity_context"]["levels"]["PMH"]["status"], "ACTIVE")
            self.assertEqual(ym_context["locked_liquidity_context"]["levels"]["PMH"]["stack_group"], "HIGH 1")
            self.assertEqual(ym_context["locked_liquidity_context"]["liquidity_map"]["levels"][0]["price"], 52394.0)
            self.assertEqual(ym_context["locked_liquidity_context"]["liquidity_map"]["levels"][0]["status"], "ACTIVE")

    def test_entry_status_endpoint_exposes_step2_and_step4_timestamp_fields(self):
        server = self._load_server()
        server.build_entry_status = lambda symbol: {
            "symbol": server.normalize_symbol(symbol),
            "current_step": "Step 4",
            "current_step_label": "Step 4 (Leg 1 Formation)",
            "current_step_status": "WAIT",
            "current_step_confirmed_at": "2026-06-26T13:35:00Z",
            "step2_status": "CONFIRMED",
            "step2_owner_seeded_at": "2026-06-26T13:30:00Z",
            "step2_activated_at": "2026-06-26T13:31:00Z",
            "step2_confirmed_at": "2026-06-26T13:35:00Z",
            "step2_invalidated_at": None,
            "step2_owner_name": "PML/ONL Liquidity",
            "step2_direction": "LONG",
            "step2_event": "step_2_activated",
            "step2_reason": "Close below observed extreme confirmed Step 2 LONG rejection pathway.",
            "step4_status": "WAIT",
            "step4_event": "step4_waiting_for_candle_b",
            "step4_reason": "Waiting for Candle B.",
            "step4_candle_a_time": "2026-06-26T13:36:00Z",
            "step4_candle_b_time": None,
            "step4_rejection_completed_at": None,
            "step4_invalidated_at": None,
            "step4_owner_name": "PML/ONL Liquidity",
            "step4_direction": "LONG",
            "wait_reason": "Waiting for Candle B.",
            "last_decision": "WAIT: Waiting for Candle B.",
        }

        response = server.app.test_client().get("/entry/status?symbols=YM")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["symbols"]), 1)
        status = payload["symbols"][0]
        self.assertEqual(status["step2_owner_seeded_at"], "2026-06-26T13:30:00Z")
        self.assertEqual(status["step2_activated_at"], "2026-06-26T13:31:00Z")
        self.assertEqual(status["step2_confirmed_at"], "2026-06-26T13:35:00Z")
        self.assertIsNone(status["step2_invalidated_at"])
        self.assertEqual(status["step2_owner_name"], "PML/ONL Liquidity")
        self.assertEqual(status["step2_direction"], "LONG")
        self.assertEqual(status["step2_event"], "step_2_activated")
        self.assertEqual(status["step2_reason"], "Close below observed extreme confirmed Step 2 LONG rejection pathway.")
        self.assertEqual(status["step4_candle_a_time"], "2026-06-26T13:36:00Z")
        self.assertIsNone(status["step4_candle_b_time"])
        self.assertIsNone(status["step4_rejection_completed_at"])
        self.assertIsNone(status["step4_invalidated_at"])
        self.assertEqual(status["step4_owner_name"], "PML/ONL Liquidity")
        self.assertEqual(status["step4_direction"], "LONG")
        self.assertEqual(status["step4_event"], "step4_waiting_for_candle_b")
        self.assertEqual(status["step4_reason"], "Waiting for Candle B.")

    def test_debug_entry_liquidity_reports_per_root_pml_and_active_price(self):
        server = self._load_server()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            server.LEVELS_PATH = temp_path / "levels.json"
            server.LEVELS_BY_SYMBOL_PATH = temp_path / "levels_by_symbol.json"
            server.TV_CONTEXT_PATH = temp_path / "tv_context.json"
            server.TV_CONTEXT_BY_SYMBOL_PATH = temp_path / "tv_context_by_symbol.json"
            server.TV_CONTEXT_EVENTS_PATH = temp_path / "tv_context_events.jsonl"
            server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
            server.build_entry_status = lambda symbol: {
                "symbol": symbol,
                "active_liquidity_name": "PML",
                "active_liquidity_price": {"NQ": 28392.0, "YM": 49730.0, "RTY": 2878.9}[server.normalize_symbol(symbol)],
            }
            server.TV_CONTEXT_BY_SYMBOL_PATH.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "NQ": {
                                "symbol": "NQ1!",
                                "ticker": "NQ1!",
                                "levels": {"PML": {"price": 28392.0}},
                            },
                            "YM": {
                                "symbol": "YM1!",
                                "ticker": "YM1!",
                                "levels": {"PML": {"price": 49730.0}},
                            },
                            "RTY": {
                                "symbol": "RTY1!",
                                "ticker": "RTY1!",
                                "levels": {"PML": {"price": 2878.9}},
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            response = server.app.test_client().get("/debug/entry-liquidity?symbols=NQM6,YMM6,RTYM6")
            payload = response.get_json()

            self.assertEqual(response.status_code, 200)
            by_root = {record["normalized_root"]: record for record in payload["symbols"]}
            self.assertEqual(by_root["NQ"]["stored_pml"], 28392.0)
            self.assertEqual(by_root["YM"]["stored_pml"], 49730.0)
            self.assertEqual(by_root["RTY"]["stored_pml"], 2878.9)
            self.assertEqual(by_root["NQ"]["active_liquidity_price"], 28392.0)
            self.assertEqual(by_root["YM"]["active_liquidity_price"], 49730.0)
            self.assertEqual(by_root["RTY"]["active_liquidity_price"], 2878.9)

    def test_before_entry_authorization_uses_current_evaluation_candle_at_630(self):
        entry_agent = self._load_entry_agent()

        observation_snapshot = {
            "latest_bar_time": "2026-07-06T13:28:00Z",
            "ohlc_is_closed": False,
        }
        first_authorized_snapshot = {
            "latest_bar_time": "2026-07-06T13:29:00Z",
            "ohlc_is_closed": False,
        }
        closed_630_snapshot = {
            "latest_bar_time": "2026-07-06T13:30:00Z",
            "ohlc_is_closed": True,
        }

        self.assertTrue(entry_agent.before_entry_authorization(observation_snapshot))
        self.assertFalse(entry_agent.before_entry_authorization(first_authorized_snapshot))
        self.assertFalse(entry_agent.before_entry_authorization(closed_630_snapshot))

    def test_pending_ym_step4_anchor_preserved_across_631_and_632(self):
        entry_agent = self._load_entry_agent()

        active_group = {
            "name": "HIGH 2",
            "components": ["LH", "ONH"],
            "prices": {"LH": 53310.0, "ONH": 53310.0},
            "side": "upper",
            "display_name": "LH/ONH",
            "close_boundary": 53310.0,
            "extreme_boundary": 53310.0,
        }
        previous_state = {
            "leg1_window_started_at": "2026-07-06T13:30:00Z",
            "leg1_window_active": True,
            "leg1_window_candle_index": 0,
            "leg1_window_remaining": 4,
            "leg1_window_expires_at": "2026-07-06T13:34:00Z",
            "leg1_status": "WAIT",
            "leg1_state_locked": False,
            "step25_pathway_selection_complete": True,
            "active_liquidity": {
                "name": "ONH",
                "price": 53310.0,
                "side": "upper",
                "group": active_group,
            },
            "active_liquidity_name": "ONH",
            "active_liquidity_price": 53310.0,
            "active_liquidity_group": active_group,
            "initial_candle_a": {
                "open": 53290.0,
                "high": 53340.0,
                "low": 53280.0,
                "close": 53320.0,
                "timestamp": "2026-07-06T13:30:00Z",
            },
            "candle_a": {
                "open": 53290.0,
                "high": 53340.0,
                "low": 53280.0,
                "close": 53320.0,
                "timestamp": "2026-07-06T13:30:00Z",
            },
        }
        persisted_state = {"step4": {"state": previous_state, "status": "WAIT"}}
        rejection = {"controlling_mode": "Normal Rejection Mode"}
        step3 = {
            "status": "ALLOW_STEP_4",
            "next_step": "Step 4",
            "state": {
                "step3_allows_structure": True,
                "active_liquidity": {
                    "name": "ONH",
                    "price": 53310.0,
                    "side": "upper",
                    "group": active_group,
                },
                "close_boundary": 53310.0,
                "extreme_boundary": 53310.0,
            },
        }

        def build_snapshot(bar_time: str, close_price: float) -> dict:
            return {
                "normalized_symbol": "YM",
                "latest_bar_time": bar_time,
                "latest_price": close_price,
                "ohlc_is_closed": True,
                "ohlc": {
                    "open": close_price - 10.0,
                    "high": close_price + 5.0,
                    "low": close_price - 20.0,
                    "close": close_price,
                },
                "liquidity": {
                    "nearest_level_above": {"name": "LH", "price": 53310.0},
                    "nearest_level_below": {"name": "PMH", "price": 53164.0},
                    "tick_size": 1.0,
                },
                "tv_context": {"levels": {}},
            }

        def build_step25(anchor_time: str) -> dict:
            return {
                "status": "READY",
                "state": {
                    "controlling_mode": "Normal Rejection Mode",
                    "step25_pathway_selection_complete": True,
                    "interaction_state": "ACTIVE",
                    "rejection_mode": "ON",
                    "liquidity_type": "LEVEL",
                    "initial_candle_a": {
                        "open": 53295.0,
                        "high": 53330.0,
                        "low": 53285.0,
                        "close": 53315.0,
                        "timestamp": anchor_time,
                    },
                },
            }

        interaction_631 = entry_agent.build_step4_interaction(
            build_snapshot("2026-07-06T13:31:00Z", 53300.0),
            rejection,
            build_step25("2026-07-06T13:31:00Z"),
            step3,
            persisted_state,
        )
        self.assertEqual(interaction_631["initial_candle_a"]["timestamp"], "2026-07-06T13:30:00Z")
        seeded_631 = entry_agent.projected_seeded_step4_status(
            build_snapshot("2026-07-06T13:31:00Z", 53300.0),
            {"step_2_activated": True, "candle_a": {"timestamp": "2026-07-06T13:31:00Z"}},
            {"status": "WAIT", "state": interaction_631},
        )
        self.assertEqual(
            seeded_631["reason"],
            "Step 4 seeded: the participation window is anchored at the 06:30 PT Step 2 confirmation candle. Waiting for a qualifying participation candle.",
        )

        interaction_632 = entry_agent.build_step4_interaction(
            build_snapshot("2026-07-06T13:32:00Z", 53296.0),
            rejection,
            build_step25("2026-07-06T13:32:00Z"),
            step3,
            persisted_state,
        )
        self.assertEqual(interaction_632["initial_candle_a"]["timestamp"], "2026-07-06T13:30:00Z")
        seeded_632 = entry_agent.projected_seeded_step4_status(
            build_snapshot("2026-07-06T13:32:00Z", 53296.0),
            {"step_2_activated": True, "candle_a": {"timestamp": "2026-07-06T13:32:00Z"}},
            {"status": "WAIT", "state": interaction_632},
        )
        self.assertEqual(
            seeded_632["reason"],
            "Step 4 seeded: the participation window is anchored at the 06:30 PT Step 2 confirmation candle. Waiting for a qualifying participation candle.",
        )

    def test_archived_ym_2026_07_06_continuation_boundary_stays_53296_at_0632(self):
        entry_agent = self._load_entry_agent()

        archive_path = entry_agent.data_path("rithmic_session_bars", "2026-07-06", "YM_1m.jsonl")
        self.assertTrue(archive_path.exists(), f"Missing session archive: {archive_path}")

        rows = []
        for raw in archive_path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            record = json.loads(raw)
            if record.get("root_symbol") != "YM":
                continue
            timestamp = record["timestamp"]
            if "2026-07-06T13:15:00Z" <= timestamp <= "2026-07-06T13:32:00Z":
                rows.append(
                    {
                        "timestamp": timestamp,
                        "open": record["open"],
                        "high": record["high"],
                        "low": record["low"],
                        "close": record["close"],
                    }
                )
        rows.sort(key=lambda row: row["timestamp"])

        original_state_path = entry_agent.STATE_PATH
        original_persistence_path = entry_agent.PERSISTENCE_STATE_PATH
        original_executor_state_path = entry_agent.EXECUTOR_STATE_PATH
        original_get_snapshot = entry_agent.get_latest_market_snapshot
        original_load_tv = entry_agent.load_tv_context
        original_recent_closed_bars = entry_agent.recent_closed_bars
        original_load_atr = entry_agent.load_rithmic_atr_snapshot
        original_append_audit = entry_agent.append_entry_agent_audit_row
        tv_context = entry_agent.load_tv_context("YM")

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                entry_agent.STATE_PATH = Path(temp_dir) / "entry_agent_state.json"
                entry_agent.PERSISTENCE_STATE_PATH = Path(temp_dir) / "persistence_state.json"
                entry_agent.EXECUTOR_STATE_PATH = Path(temp_dir) / "executor_state.json"
                entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
                entry_agent.load_tv_context = lambda _symbol=None: tv_context
                entry_agent.load_rithmic_atr_snapshot = lambda _symbol="YM": {
                    "atr_1m_14": (tv_context or {}).get("atr_1m_14") or 10.0
                }

                replay_bars = []
                index = {"value": 0}

                def market_snapshot(_symbol: str = "YM") -> dict:
                    current = rows[index["value"]]
                    return {
                        "symbol": "YM",
                        "normalized_symbol": "YM",
                        "latest_price": current["close"],
                        "latest_bar_time": current["timestamp"],
                        "ohlc_is_closed": True,
                        "liquidity": {
                            "nearest_level_above": None,
                            "nearest_level_below": None,
                            "tick_size": 1.0,
                        },
                        "atr": {"atr_1m_14": (tv_context or {}).get("atr_1m_14") or 10.0},
                        "ohlc": {
                            "open": current["open"],
                            "high": current["high"],
                            "low": current["low"],
                            "close": current["close"],
                        },
                    }

                entry_agent.get_latest_market_snapshot = market_snapshot
                entry_agent.recent_closed_bars = lambda _symbol="YM", limit=120: list(replay_bars)[-limit:]

                boundaries = {}
                lane_reasons = {}
                for i, bar in enumerate(rows):
                    index["value"] = i
                    replay_bars.append(dict(bar))
                    entry_agent.run_once("YM", persist=True)
                    if bar["timestamp"] not in {"2026-07-06T13:31:00Z", "2026-07-06T13:32:00Z"}:
                        continue
                    state = entry_agent.load_entry_state().get("state_by_symbol", {}).get("YM", {})
                    step25_state = ((state.get("step25") or {}).get("state") or {})
                    status = entry_agent.build_entry_status("YM")
                    boundaries[bar["timestamp"]] = step25_state.get("continuation_active_boundary_price")
                    lane_reasons[bar["timestamp"]] = ((status.get("continuation_lane") or {}).get("step2_reason"))

                self.assertIsNone(boundaries["2026-07-06T13:31:00Z"])
                self.assertEqual(boundaries["2026-07-06T13:32:00Z"], 53296.0)
                self.assertEqual(
                    lane_reasons["2026-07-06T13:32:00Z"],
                    "Continuation eligible from frozen rejection trade_state; waiting for a close through active continuation boundary 53296.0.",
                )
        finally:
            entry_agent.STATE_PATH = original_state_path
            entry_agent.PERSISTENCE_STATE_PATH = original_persistence_path
            entry_agent.EXECUTOR_STATE_PATH = original_executor_state_path
            entry_agent.get_latest_market_snapshot = original_get_snapshot
            entry_agent.load_tv_context = original_load_tv
            entry_agent.recent_closed_bars = original_recent_closed_bars
            entry_agent.load_rithmic_atr_snapshot = original_load_atr
            entry_agent.append_entry_agent_audit_row = original_append_audit

    def test_archived_ym_2026_07_06_continuation_boundary_stays_53296_after_0636_step4_confirm(self):
        entry_agent = self._load_entry_agent()

        archive_path = entry_agent.data_path("rithmic_session_bars", "2026-07-06", "YM_1m.jsonl")
        self.assertTrue(archive_path.exists(), f"Missing session archive: {archive_path}")

        rows = []
        for raw in archive_path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            record = json.loads(raw)
            if record.get("root_symbol") != "YM":
                continue
            timestamp = record["timestamp"]
            if "2026-07-06T13:15:00Z" <= timestamp <= "2026-07-06T13:36:00Z":
                rows.append(
                    {
                        "timestamp": timestamp,
                        "open": record["open"],
                        "high": record["high"],
                        "low": record["low"],
                        "close": record["close"],
                    }
                )
        rows.sort(key=lambda row: row["timestamp"])

        original_state_path = entry_agent.STATE_PATH
        original_persistence_path = entry_agent.PERSISTENCE_STATE_PATH
        original_executor_state_path = entry_agent.EXECUTOR_STATE_PATH
        original_get_snapshot = entry_agent.get_latest_market_snapshot
        original_load_tv = entry_agent.load_tv_context
        original_recent_closed_bars = entry_agent.recent_closed_bars
        original_load_atr = entry_agent.load_rithmic_atr_snapshot
        original_append_audit = entry_agent.append_entry_agent_audit_row
        tv_context = entry_agent.load_tv_context("YM")

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                entry_agent.STATE_PATH = Path(temp_dir) / "entry_agent_state.json"
                entry_agent.PERSISTENCE_STATE_PATH = Path(temp_dir) / "persistence_state.json"
                entry_agent.EXECUTOR_STATE_PATH = Path(temp_dir) / "executor_state.json"
                entry_agent.append_entry_agent_audit_row = lambda _snapshot: None
                entry_agent.load_tv_context = lambda _symbol=None: tv_context
                entry_agent.load_rithmic_atr_snapshot = lambda _symbol="YM": {
                    "atr_1m_14": (tv_context or {}).get("atr_1m_14") or 10.0
                }

                replay_bars = []
                index = {"value": 0}

                def market_snapshot(_symbol: str = "YM") -> dict:
                    current = rows[index["value"]]
                    return {
                        "symbol": "YM",
                        "normalized_symbol": "YM",
                        "latest_price": current["close"],
                        "latest_bar_time": current["timestamp"],
                        "ohlc_is_closed": True,
                        "liquidity": {
                            "nearest_level_above": None,
                            "nearest_level_below": None,
                            "tick_size": 1.0,
                        },
                        "atr": {"atr_1m_14": (tv_context or {}).get("atr_1m_14") or 10.0},
                        "ohlc": {
                            "open": current["open"],
                            "high": current["high"],
                            "low": current["low"],
                            "close": current["close"],
                        },
                    }

                entry_agent.get_latest_market_snapshot = market_snapshot
                entry_agent.recent_closed_bars = lambda _symbol="YM", limit=120: list(replay_bars)[-limit:]

                status_636 = None
                for i, bar in enumerate(rows):
                    index["value"] = i
                    replay_bars.append(dict(bar))
                    entry_agent.run_once("YM", persist=True)
                    if bar["timestamp"] == "2026-07-06T13:36:00Z":
                        status_636 = entry_agent.build_entry_status("YM")

                self.assertIsNotNone(status_636)
                self.assertEqual(status_636["continuation_boundary"], 53296.0)
                self.assertEqual(status_636["continuation_lane"]["continuation_boundary"], 53296.0)
                self.assertEqual(status_636["continuation_lane"]["liquidity_level_price"], 53310.0)
                self.assertEqual(status_636["continuation_lane"]["step4_status"], "CONFIRMED")
                self.assertEqual(status_636["continuation_lane"]["step4_confirmed_at"], "2026-07-06T13:36:00Z")
                self.assertNotIn("close_boundary", status_636)
                self.assertNotIn("extreme_boundary", status_636)
                self.assertNotIn("wick_boundary_extreme", status_636)
                self.assertNotIn("continuation_reference_boundary_price", status_636)
                self.assertNotIn("continuation_active_boundary_price", status_636)
                self.assertNotIn("close_boundary", status_636["continuation_lane"])
                self.assertNotIn("extreme_boundary", status_636["continuation_lane"])
                self.assertNotIn("wick_boundary_extreme", status_636["continuation_lane"])
        finally:
            entry_agent.STATE_PATH = original_state_path
            entry_agent.PERSISTENCE_STATE_PATH = original_persistence_path
            entry_agent.EXECUTOR_STATE_PATH = original_executor_state_path
            entry_agent.get_latest_market_snapshot = original_get_snapshot
            entry_agent.load_tv_context = original_load_tv
            entry_agent.recent_closed_bars = original_recent_closed_bars
            entry_agent.load_rithmic_atr_snapshot = original_load_atr
            entry_agent.append_entry_agent_audit_row = original_append_audit

    def test_reexecution_procedure_ym_2026_07_06_replay_uses_session_archive_only(self):
        replay = self._replay_archived_ym_2026_07_06_public_window()
        archive_path = replay["archive_path"]
        recent_cache_path = replay["recent_cache_path"]

        self.assertIn("rithmic_session_bars", str(archive_path))
        self.assertTrue(str(archive_path).endswith("2026-07-06\\YM_1m.jsonl"))
        self.assertNotEqual(archive_path, recent_cache_path)
        self.assertIn("rithmic_recent_bars.json", str(recent_cache_path))
        self.assertEqual(
            set(replay["statuses"].keys()),
            {
                "2026-07-06T13:30:00Z",
                "2026-07-06T13:31:00Z",
                "2026-07-06T13:32:00Z",
                "2026-07-06T13:33:00Z",
                "2026-07-06T13:34:00Z",
                "2026-07-06T13:35:00Z",
                "2026-07-06T13:36:00Z",
            },
        )

    def test_archived_ym_2026_07_06_public_rejection_lifecycle_and_boundaries(self):
        replay = self._replay_archived_ym_2026_07_06_public_window()
        statuses = replay["statuses"]
        states = replay["states"]

        status_630 = statuses["2026-07-06T13:30:00Z"]
        self.assertEqual(status_630["current_step"], "Step 2")
        self.assertEqual(status_630["rejection_lane"]["step2_status"], "CONFIRMED")
        self.assertEqual(status_630["rejection_lane"]["liquidity_level_name"], "ONH/LH")
        self.assertEqual(status_630["rejection_lane"]["liquidity_level_price"], 53310.0)
        self.assertIsNone(status_630["rejection_lane"]["rejection_boundary"])

        status_631 = statuses["2026-07-06T13:31:00Z"]
        self.assertEqual(status_631["rejection_lane"]["step4_status"], "CONFIRMED")
        self.assertEqual(status_631["rejection_lane"]["step4_confirmed_at"], "2026-07-06T13:31:00Z")
        step4_state_631 = ((states["2026-07-06T13:31:00Z"].get("step4") or {}).get("state") or {})
        self.assertEqual((step4_state_631.get("initial_candle_a") or {}).get("timestamp"), "2026-07-06T13:30:00Z")

        status_632 = statuses["2026-07-06T13:32:00Z"]
        self.assertEqual(status_632["current_step"], "Step 5")
        step4_state_632 = ((states["2026-07-06T13:32:00Z"].get("step4") or {}).get("state") or {})
        self.assertEqual((step4_state_632.get("initial_candle_a") or {}).get("timestamp"), "2026-07-06T13:30:00Z")

    def test_archived_ym_2026_07_06_public_continuation_eligibility_and_reason_text(self):
        replay = self._replay_archived_ym_2026_07_06_public_window()
        statuses = replay["statuses"]

        for timestamp in (
            "2026-07-06T13:31:00Z",
            "2026-07-06T13:32:00Z",
            "2026-07-06T13:33:00Z",
            "2026-07-06T13:34:00Z",
        ):
            lane = statuses[timestamp]["continuation_lane"]
            self.assertEqual(lane["lane_status"], "eligible")
            self.assertEqual(lane["continuation_boundary"], 53296.0)
            self.assertIn("active continuation boundary 53296.0", lane["step2_reason"])

    def test_archived_ym_2026_07_06_public_continuation_lifecycle_boundary_preserved(self):
        replay = self._replay_archived_ym_2026_07_06_public_window()
        statuses = replay["statuses"]

        status_635 = statuses["2026-07-06T13:35:00Z"]
        self.assertEqual(status_635["selected_pathway"], "continuation")
        self.assertEqual(status_635["continuation_lane"]["step2_status"], "CONFIRMED")
        self.assertEqual(status_635["continuation_lane"]["step2_confirmed_at"], "2026-07-06T13:35:00Z")
        self.assertEqual(status_635["continuation_lane"]["continuation_boundary"], 53296.0)

        status_636 = statuses["2026-07-06T13:36:00Z"]
        self.assertEqual(status_636["continuation_lane"]["step4_status"], "CONFIRMED")
        self.assertEqual(status_636["continuation_lane"]["step4_confirmed_at"], "2026-07-06T13:36:00Z")
        self.assertEqual(status_636["continuation_lane"]["continuation_boundary"], 53296.0)
        self.assertNotEqual(status_636["continuation_lane"]["continuation_boundary"], 53259.0)

    def test_archived_ym_2026_07_06_public_payload_uses_boundary_model_only(self):
        replay = self._replay_archived_ym_2026_07_06_public_window()

        for status in replay["statuses"].values():
            for required_field in (
                "liquidity_level_name",
                "liquidity_level_price",
                "rejection_boundary",
                "continuation_boundary",
            ):
                self.assertIn(required_field, status)
            for retired_field in (
                "close_boundary",
                "extreme_boundary",
                "wick_boundary_extreme",
                "continuation_reference_boundary_price",
                "continuation_reference_boundary_type",
                "continuation_active_boundary_price",
            ):
                self.assertNotIn(retired_field, status)
            for lane_name in ("rejection_lane", "continuation_lane"):
                lane = status[lane_name]
                for required_field in (
                    "liquidity_level_name",
                    "liquidity_level_price",
                    "rejection_boundary",
                    "continuation_boundary",
                ):
                    self.assertIn(required_field, lane)
                for retired_field in (
                    "close_boundary",
                    "extreme_boundary",
                    "wick_boundary_extreme",
                    "continuation_reference_boundary_price",
                    "continuation_reference_boundary_type",
                    "continuation_active_boundary_price",
                ):
                    self.assertNotIn(retired_field, lane)

    def test_archived_nq_2026_07_06_rejection_boundary_retained_after_extension_backed_step2(self):
        entry_agent = self._load_entry_agent()
        replay = self._replay_archived_public_window(
            entry_agent=entry_agent,
            session_date="2026-07-06",
            root="NQ",
            start_timestamp="2026-07-06T13:15:00Z",
            end_timestamp="2026-07-06T14:14:00Z",
            checkpoints={
                "2026-07-06T14:12:00Z",
                "2026-07-06T14:13:00Z",
                "2026-07-06T14:14:00Z",
            },
        )

        for timestamp in (
            "2026-07-06T14:12:00Z",
            "2026-07-06T14:13:00Z",
            "2026-07-06T14:14:00Z",
        ):
            status = replay["statuses"][timestamp]
            lane = status["rejection_lane"]
            self.assertEqual(lane["step2_status"], "CONFIRMED")
            self.assertEqual(lane["liquidity_level_name"], "PMH/ONH")
            self.assertEqual(lane["liquidity_level_price"], 30011.25)
            self.assertEqual(lane["rejection_boundary"], 30012.25)
            self.assertNotEqual(lane["rejection_boundary"], lane["liquidity_level_price"])

        server = self._load_server()
        reasoning = server.entry_reasoning_record(replay["statuses"]["2026-07-06T14:12:00Z"])
        self.assertEqual(reasoning["liquidity_level_name"], "PMH/ONH")
        self.assertEqual(reasoning["liquidity_level_price"], 30011.25)
        self.assertEqual(reasoning["rejection_boundary"], 30012.25)

    def test_archived_nq_2026_07_08_rejection_step4_stays_terminated_and_50_line_frozen(self):
        entry_agent = self._load_entry_agent()
        replay = self._replay_archived_public_window(
            entry_agent=entry_agent,
            session_date="2026-07-08",
            root="NQ",
            start_timestamp="2026-07-08T13:15:00Z",
            end_timestamp="2026-07-08T13:39:00Z",
            checkpoints={
                "2026-07-08T13:30:00Z",
                "2026-07-08T13:31:00Z",
                "2026-07-08T13:32:00Z",
                "2026-07-08T13:33:00Z",
                "2026-07-08T13:34:00Z",
                "2026-07-08T13:35:00Z",
                "2026-07-08T13:36:00Z",
                "2026-07-08T13:37:00Z",
                "2026-07-08T13:38:00Z",
                "2026-07-08T13:39:00Z",
            },
        )

        statuses = replay["statuses"]
        states = replay["states"]

        self.assertEqual(statuses["2026-07-08T13:30:00Z"]["rejection_lane"]["step2_status"], "CONFIRMED")
        self.assertEqual(statuses["2026-07-08T13:30:00Z"]["rejection_lane"]["step2_confirmed_at"], "2026-07-08T13:30:00Z")
        self.assertEqual(statuses["2026-07-08T13:31:00Z"]["rejection_lane"]["step4_status"], "WAIT")
        self.assertEqual(statuses["2026-07-08T13:32:00Z"]["rejection_lane"]["step4_status"], "TERMINATED")
        self.assertEqual(statuses["2026-07-08T13:32:00Z"]["rejection_lane"]["invalidation_reason"], "STEP2_STEP4_50_LINE_TOUCHED")

        for timestamp in (
            "2026-07-08T13:33:00Z",
            "2026-07-08T13:34:00Z",
            "2026-07-08T13:35:00Z",
            "2026-07-08T13:37:00Z",
            "2026-07-08T13:38:00Z",
            "2026-07-08T13:39:00Z",
        ):
            lane = statuses[timestamp]["rejection_lane"]
            step4_state = ((states[timestamp].get("step4") or {}).get("state") or {})
            self.assertEqual(lane["step2_confirmed_at"], "2026-07-08T13:30:00Z")
            self.assertEqual(lane["step4_status"], "TERMINATED")
            self.assertNotEqual(lane["step4_status"], "WAIT")
            self.assertEqual(lane["invalidation_reason"], "STEP2_STEP4_50_LINE_TOUCHED")
            self.assertTrue(step4_state.get("leg1_window_invalidated"))
            self.assertEqual(step4_state.get("leg1_window_invalidation_reason"), "STEP2_STEP4_50_LINE_TOUCHED")

        frozen_line = statuses["2026-07-08T13:30:00Z"]["rejection_lane"]["step2_step4_50_line"]
        self.assertEqual(frozen_line, 29327.125)
        for timestamp in (
            "2026-07-08T13:31:00Z",
            "2026-07-08T13:32:00Z",
            "2026-07-08T13:33:00Z",
            "2026-07-08T13:34:00Z",
            "2026-07-08T13:35:00Z",
            "2026-07-08T13:37:00Z",
            "2026-07-08T13:38:00Z",
            "2026-07-08T13:39:00Z",
        ):
            self.assertEqual(statuses[timestamp]["rejection_lane"]["step2_step4_50_line"], frozen_line)

    def test_entry_status_replay_keeps_july_8_nq_rejection_lane_anchor_frozen(self):
        entry_agent = self._load_entry_agent()
        replay = self._replay_archived_status_endpoint_window(
            entry_agent=entry_agent,
            session_date="2026-07-08",
            root="NQ",
            start_timestamp="2026-07-08T13:15:00Z",
            end_timestamp="2026-07-08T13:39:00Z",
            checkpoints={
                "2026-07-08T13:30:00Z",
                "2026-07-08T13:31:00Z",
                "2026-07-08T13:32:00Z",
                "2026-07-08T13:33:00Z",
                "2026-07-08T13:34:00Z",
                "2026-07-08T13:35:00Z",
                "2026-07-08T13:36:00Z",
                "2026-07-08T13:37:00Z",
                "2026-07-08T13:38:00Z",
                "2026-07-08T13:39:00Z",
            },
            extra_polls_by_timestamp={
                "2026-07-08T13:31:00Z": 2,
                "2026-07-08T13:32:00Z": 2,
                "2026-07-08T13:39:00Z": 2,
            },
        )

        statuses = replay["statuses"]
        poll_history = replay["poll_history"]
        for timestamp in (
            "2026-07-08T13:30:00Z",
            "2026-07-08T13:31:00Z",
            "2026-07-08T13:32:00Z",
            "2026-07-08T13:33:00Z",
            "2026-07-08T13:34:00Z",
            "2026-07-08T13:35:00Z",
            "2026-07-08T13:37:00Z",
            "2026-07-08T13:38:00Z",
            "2026-07-08T13:39:00Z",
        ):
            self.assertEqual(statuses[timestamp]["rejection_lane"]["step2_confirmed_at"], "2026-07-08T13:30:00Z")
            self.assertEqual(statuses[timestamp]["leg1_window_started_at"], "2026-07-08T13:30:00Z")
        for timestamp in (
            "2026-07-08T13:31:00Z",
            "2026-07-08T13:32:00Z",
            "2026-07-08T13:33:00Z",
            "2026-07-08T13:34:00Z",
            "2026-07-08T13:35:00Z",
            "2026-07-08T13:37:00Z",
            "2026-07-08T13:38:00Z",
            "2026-07-08T13:39:00Z",
        ):
            self.assertNotEqual(statuses[timestamp]["rejection_lane"]["step2_confirmed_at"], timestamp)

        self.assertEqual(statuses["2026-07-08T13:30:00Z"]["leg1_window_started_at"], "2026-07-08T13:30:00Z")
        self.assertEqual(statuses["2026-07-08T13:31:00Z"]["leg1_window_started_at"], "2026-07-08T13:30:00Z")
        self.assertEqual(
            statuses["2026-07-08T13:30:00Z"]["step4_reason"],
            "Step 4 seeded: the participation window is anchored at the 06:30 PT Step 2 confirmation candle. Waiting for a qualifying participation candle.",
        )
        self.assertEqual(statuses["2026-07-08T13:31:00Z"]["rejection_lane"]["leg1_window_started_at"], "2026-07-08T13:30:00Z")
        self.assertEqual(
            statuses["2026-07-08T13:30:00Z"]["rejection_lane"]["step4_reason"],
            "Step 4 seeded: the participation window is anchored at the 06:30 PT Step 2 confirmation candle. Waiting for a qualifying participation candle.",
        )
        self.assertEqual(statuses["2026-07-08T13:32:00Z"]["rejection_lane"]["step4_status"], "TERMINATED")
        self.assertEqual(statuses["2026-07-08T13:32:00Z"]["rejection_lane"]["invalidation_reason"], "STEP2_STEP4_50_LINE_TOUCHED")

        frozen_line = statuses["2026-07-08T13:30:00Z"]["rejection_lane"]["step2_step4_50_line"]
        self.assertEqual(frozen_line, 29327.125)
        for timestamp in (
            "2026-07-08T13:31:00Z",
            "2026-07-08T13:32:00Z",
            "2026-07-08T13:33:00Z",
            "2026-07-08T13:34:00Z",
            "2026-07-08T13:35:00Z",
            "2026-07-08T13:37:00Z",
            "2026-07-08T13:38:00Z",
            "2026-07-08T13:39:00Z",
        ):
            lane = statuses[timestamp]["rejection_lane"]
            self.assertEqual(lane["step2_step4_50_line"], frozen_line)
        for timestamp in (
            "2026-07-08T13:33:00Z",
            "2026-07-08T13:34:00Z",
            "2026-07-08T13:35:00Z",
            "2026-07-08T13:37:00Z",
            "2026-07-08T13:38:00Z",
            "2026-07-08T13:39:00Z",
        ):
            lane = statuses[timestamp]["rejection_lane"]
            self.assertEqual(lane["step4_status"], "TERMINATED")
            self.assertNotEqual(lane["step4_status"], "WAIT")
            self.assertEqual(lane["invalidation_reason"], "STEP2_STEP4_50_LINE_TOUCHED")

        for timestamp in ("2026-07-08T13:31:00Z", "2026-07-08T13:32:00Z", "2026-07-08T13:39:00Z"):
            for poll in poll_history[timestamp]:
                self.assertEqual(poll["rejection_lane"]["step2_confirmed_at"], "2026-07-08T13:30:00Z")
                self.assertEqual(poll["leg1_window_started_at"], "2026-07-08T13:30:00Z")
                self.assertNotEqual(poll["rejection_lane"]["step2_confirmed_at"], timestamp)
        self.assertEqual(len(poll_history["2026-07-08T13:31:00Z"]), 3)
        self.assertEqual(len(poll_history["2026-07-08T13:32:00Z"]), 3)
        self.assertEqual(len(poll_history["2026-07-08T13:39:00Z"]), 3)

    def test_entry_status_persists_first_july_13_nq_rejection_step4_completion(self):
        entry_agent = self._load_entry_agent()
        replay = self._replay_archived_status_endpoint_window(
            entry_agent=entry_agent,
            session_date="2026-07-13",
            root="NQ",
            start_timestamp="2026-07-13T13:15:00Z",
            end_timestamp="2026-07-13T13:39:00Z",
            checkpoints={
                "2026-07-13T13:34:00Z",
                "2026-07-13T13:35:00Z",
                "2026-07-13T13:36:00Z",
                "2026-07-13T13:37:00Z",
                "2026-07-13T13:38:00Z",
                "2026-07-13T13:39:00Z",
            },
            extra_polls_by_timestamp={
                "2026-07-13T13:35:00Z": 2,
                "2026-07-13T13:36:00Z": 2,
            },
        )

        statuses = replay["statuses"]
        states = replay["states"]
        status_0634 = statuses["2026-07-13T13:34:00Z"]
        self.assertEqual(status_0634["rejection_lane"]["step2_status"], "CONFIRMED")
        self.assertEqual(status_0634["rejection_lane"]["step2_confirmed_at"], "2026-07-13T13:34:00Z")
        self.assertEqual(status_0634["step2_candle_count"], 0)
        self.assertIsNone(status_0634["rejection_boundary"])
        self.assertIsNone(status_0634["rejection_lane"]["rejection_boundary"])

        completed_at = "2026-07-13T13:35:00Z"
        expected_candle_b = {
            "open": 29641.0,
            "high": 29673.5,
            "low": 29640.0,
            "close": 29652.5,
            "timestamp": completed_at,
        }
        for timestamp in (
            "2026-07-13T13:35:00Z",
            "2026-07-13T13:36:00Z",
            "2026-07-13T13:37:00Z",
        ):
            status = statuses[timestamp]
            lane = status["rejection_lane"]
            step4 = states[timestamp]["step4"]
            step4_state = step4["state"]

            self.assertEqual(step4["status"], "READY", timestamp)
            self.assertEqual(step4_state["step4_confirmed_at"], completed_at, timestamp)
            self.assertEqual(step4_state["leg1_completed_at"], completed_at, timestamp)
            self.assertEqual(step4_state["leg1_reference_candle_time"], completed_at, timestamp)
            self.assertEqual(step4_state["candle_b"], expected_candle_b, timestamp)
            self.assertEqual(step4_state["participation_timer"]["completed_at"], completed_at, timestamp)
            self.assertEqual(step4_state["leg2_sweep_extreme"], 29631.75, timestamp)
            self.assertEqual(step4_state["step5_close_boundary"], 29642.25, timestamp)
            self.assertEqual(step4_state["leg1_reference_price"], 29642.25, timestamp)
            self.assertEqual(step4_state["leg1_status"], "COMPLETE", timestamp)
            self.assertIs(step4_state["leg1_state_locked"], True, timestamp)

            self.assertEqual(status["step4_status"], "CONFIRMED", timestamp)
            self.assertEqual(status["step4_confirmed_at"], completed_at, timestamp)
            self.assertEqual(status["step4_rejection_completed_at"], completed_at, timestamp)
            self.assertEqual(status["step4_candle_b_time"], completed_at, timestamp)
            self.assertEqual(status["leg1_completed_at"], completed_at, timestamp)
            self.assertEqual(status["leg1_reference_candle_time"], completed_at, timestamp)
            self.assertEqual(status["leg1_reference_price"], 29642.25, timestamp)
            self.assertEqual(status["leg2_sweep_extreme"], 29631.75, timestamp)
            self.assertEqual(status["step5_close_boundary"], 29642.25, timestamp)
            self.assertIs(status["leg1_locked"], True, timestamp)
            self.assertEqual(lane["step4_status"], "CONFIRMED", timestamp)
            self.assertEqual(lane["step4_confirmed_at"], completed_at, timestamp)
            self.assertEqual(lane["leg2_sweep_extreme"], 29631.75, timestamp)
            self.assertEqual(lane["step5_close_boundary"], 29642.25, timestamp)
            self.assertIsNone(status["rejection_boundary"], timestamp)
            self.assertIsNone(lane["rejection_boundary"], timestamp)

        # 06:38 legitimately creates the separate continuation lifecycle.  The
        # current Step 4 object may then belong to continuation, while the
        # completed rejection snapshot remains frozen on the rejection lane.
        for timestamp in ("2026-07-13T13:38:00Z", "2026-07-13T13:39:00Z"):
            status = statuses[timestamp]
            lane = status["rejection_lane"]
            persisted_lane = states[timestamp]["rejection_lane"]
            self.assertEqual(lane["lane_status"], "frozen", timestamp)
            self.assertEqual(lane["step4_status"], "CONFIRMED", timestamp)
            self.assertEqual(lane["step4_confirmed_at"], completed_at, timestamp)
            self.assertEqual(lane["leg2_sweep_extreme"], 29631.75, timestamp)
            self.assertEqual(lane["step5_close_boundary"], 29642.25, timestamp)
            self.assertEqual(persisted_lane["step4_confirmed_at"], completed_at, timestamp)
            self.assertEqual(persisted_lane["leg2_sweep_extreme"], 29631.75, timestamp)
            self.assertEqual(persisted_lane["step5_close_boundary"], 29642.25, timestamp)
            self.assertIsNone(lane["rejection_boundary"], timestamp)

        for timestamp in ("2026-07-13T13:35:00Z", "2026-07-13T13:36:00Z"):
            status = statuses[timestamp]
            self.assertEqual(status["step2_candle_count"], 1, timestamp)
            self.assertIs(status["continuation_eligible"], True, timestamp)
            self.assertEqual(status["continuation_lane"]["lane_status"], "eligible", timestamp)
            for poll in replay["poll_history"][timestamp]:
                self.assertEqual(poll["step4_confirmed_at"], completed_at, timestamp)
                self.assertEqual(poll["rejection_lane"]["step4_confirmed_at"], completed_at, timestamp)
                self.assertEqual(poll["leg2_sweep_extreme"], 29631.75, timestamp)
                self.assertEqual(poll["step5_close_boundary"], 29642.25, timestamp)

        page = (ROOT / "command_center.html").read_text(encoding="utf-8")
        self.assertIn("if (side && side.step4_confirmed_at) return side.step4_confirmed_at;", page)

    def test_runtime_replay_validation_reads_session_archive_bars(self):
        entry_agent = self._load_entry_agent()
        runtime_replay_validation = self._load_runtime_replay_validation()
        archive_path = entry_agent.data_path("rithmic_session_bars", "2026-07-06", "YM_1m.jsonl")

        rows = runtime_replay_validation.read_session_archive_bars(
            archive_path,
            "YM",
            "2026-07-06T13:30:00Z",
            "2026-07-06T13:32:00Z",
        )

        self.assertEqual(
            [row["timestamp"] for row in rows],
            [
                "2026-07-06T13:30:00Z",
                "2026-07-06T13:31:00Z",
                "2026-07-06T13:32:00Z",
            ],
        )
        self.assertEqual(
            rows[0],
            {
                "timestamp": "2026-07-06T13:30:00Z",
                "open": 53244.0,
                "high": 53354.0,
                "low": 53243.0,
                "close": 53340.0,
            },
        )
        self.assertFalse(hasattr(runtime_replay_validation, "read_reasoning_bars"))

    def test_command_center_displays_lane_specific_public_boundaries_only(self):
        page = (ROOT / "command_center.html").read_text(encoding="utf-8")

        self.assertIn('entryAgentField("Liquidity Level", liquidityLevel)', page)
        self.assertIn('? entryAgentField("Rejection Boundary", rejectionBoundary)', page)
        self.assertIn(': entryAgentField("Continuation Boundary", continuationBoundary)', page)
        self.assertIn('function entryAgentDisplayBoundary(boundary, liquidityLevelPrice)', page)
        self.assertIn('boundaryNumber === liquidityNumber', page)
        self.assertNotIn('entryAgentField("Close",', page)
        self.assertNotIn('entryAgentField("Extreme",', page)
        self.assertNotIn('entryAgentField("Wick",', page)


if __name__ == "__main__":
    unittest.main()
