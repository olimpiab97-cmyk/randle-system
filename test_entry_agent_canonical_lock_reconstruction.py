from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
ENTRY_AGENT_ROOT = ROOT / "EntryAgent"
for path in (ROOT, ENTRY_AGENT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import entry_agent
import tv_context_server as server


MARKET_TIMEZONE = ZoneInfo("America/Los_Angeles")


def level(price: float, stack_group: str = "NONE") -> dict[str, object]:
    return {
        "price": price,
        "status": "ACTIVE",
        "stack_group": stack_group,
        "stack_groups": [] if stack_group == "NONE" else [stack_group],
        "stack_display": stack_group,
    }


def source_time() -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=1)


def canonical_payload(symbol: str, *, stacked_yh: bool = True) -> dict[str, object]:
    timestamp = source_time()
    session_date = timestamp.astimezone(MARKET_TIMEZONE).date().isoformat()
    if stacked_yh:
        high_levels = {
            "PMH": level(52516),
            "LH": {**level(52574), "status": "INACTIVE"},
            "ONH": level(52789, "HIGH 1"),
            "YH": level(52835, "HIGH 1"),
        }
        high_stack = {
            "id": "HIGH 1",
            "side": "HIGH",
            "members": ["ONH", "YH"],
            "innermost_price": 52789,
            "outermost_price": 52835,
        }
    else:
        high_levels = {
            "PMH": level(52581, "HIGH 1"),
            "LH": level(52622, "HIGH 1"),
            "ONH": level(52622, "HIGH 1"),
            "YH": level(52835),
        }
        high_stack = {
            "id": "HIGH 1",
            "side": "HIGH",
            "members": ["PMH", "LH", "ONH"],
            "innermost_price": 52581,
            "outermost_price": 52622,
        }
    low_stack = {
        "id": "LOW 1",
        "side": "LOW",
        "members": ["LL", "PML"],
        "innermost_price": 52430,
        "outermost_price": 52429,
    }
    levels = {
        "PMH": high_levels["PMH"],
        "PML": level(52429, "LOW 1"),
        "LH": high_levels["LH"],
        "LL": level(52430, "LOW 1"),
        "ONH": high_levels["ONH"],
        "ONL": level(52238),
        "YH": high_levels["YH"],
        "YL": level(52174),
    }
    stacks = [high_stack, low_stack]
    return {
        "source": server.CANONICAL_LIQUIDITY_SOURCE,
        "version": server.CANONICAL_LIQUIDITY_VERSION,
        "context_mode": "locked_levels_session_snapshot",
        "session_locked": True,
        "locked": True,
        "price_is_true_level": True,
        "display_offsets_applied_to_chart_only": True,
        "is_recurring_update": False,
        "symbol": symbol,
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "session_date": session_date,
        "time_zone": "America/Los_Angeles",
        "timeframe": "1",
        "session_lock_price": 52437,
        "stack_threshold": 62,
        "daily_atr14": 611.0949591232,
        "levels": levels,
        "liquidity_map": {
            "levels": [{"name": name, **copy.deepcopy(details)} for name, details in levels.items()],
            "stacks": copy.deepcopy(stacks),
        },
        "stacks": copy.deepcopy(stacks),
        "midpoints": {},
        "exhaustion_boundaries": {},
    }


def legacy_payload(symbol: str) -> dict[str, object]:
    payload = canonical_payload(symbol, stacked_yh=False)
    payload["version"] = "v14_overlapping_stack_smoke"
    payload.pop("session_lock_price")
    payload["stack_threshold"] = 61
    payload["daily_atr14"] = 607.0949591232
    return payload


class CanonicalLockLifecycleTests(unittest.TestCase):
    def build(self, payload: dict[str, object]) -> dict[str, object]:
        context, error = server.build_context(payload)
        self.assertIsNone(error)
        self.assertIsInstance(context, dict)
        return context

    def test_initial_canonical_lock_and_response_projection_preserve_reference(self):
        context = self.build(canonical_payload("YM1!"))
        stored = server.merge_session_liquidity_context(None, context)
        projection = server.public_market_context(stored)

        self.assertEqual(stored["session_lock_price"], 52437)
        self.assertEqual(stored["locked_liquidity_context"]["session_lock_price"], 52437)
        self.assertTrue(stored["liquidity_context_authoritative"])
        self.assertEqual(projection["session_lock_price"], 52437)
        self.assertEqual(projection["locked_liquidity_context"]["session_lock_price"], 52437)

    def test_persistence_rehydration_retains_exact_reference(self):
        stored = server.merge_session_liquidity_context(None, self.build(canonical_payload("YM1!")))
        lock = entry_agent.build_session_locked_tv_context(stored)
        rehydrated_state = json.loads(json.dumps({"state_by_symbol": {"YM": {"session_liquidity_context": lock}}}))
        rehydrated = entry_agent.locked_session_liquidity_context(rehydrated_state, "YM")

        self.assertTrue(rehydrated["locked"])
        self.assertFalse(rehydrated["disabled"])
        self.assertEqual(rehydrated["tv_context"]["session_lock_price"], 52437)
        self.assertEqual(rehydrated["tv_context"]["stack_threshold"], 62.0)
        self.assertEqual(rehydrated["tv_context"]["daily_atr14"], 611.0949591232)
        self.assertEqual(rehydrated["tv_context"]["version"], server.CANONICAL_LIQUIDITY_VERSION)
        self.assertIsNotNone(rehydrated["tv_context"]["timestamp"])

    def test_recurring_payload_cannot_silently_change_valid_frozen_values(self):
        first = server.merge_session_liquidity_context(None, self.build(canonical_payload("YM1!")))
        changed_payload = canonical_payload("YM1!")
        changed_payload["session_lock_price"] = 52500
        changed_payload["stack_threshold"] = 99
        changed_payload["daily_atr14"] = 999.0
        changed_payload["levels"]["PMH"]["price"] = 52000
        next(row for row in changed_payload["liquidity_map"]["levels"] if row["name"] == "PMH")["price"] = 52000
        recurring = self.build(changed_payload)

        self.assertFalse(server.should_replace_stale_locked_liquidity_context(first, recurring))
        merged = server.merge_session_liquidity_context(first, recurring)
        self.assertEqual(merged["session_lock_price"], 52437)
        self.assertEqual(merged["stack_threshold"], 62.0)
        self.assertEqual(merged["daily_atr14"], 611.0949591232)
        self.assertEqual(merged["locked_liquidity_context"]["session_lock_price"], 52437)
        self.assertEqual(merged["last_tv_context_candidate"]["session_lock_price"], 52500)

    def test_legacy_lock_without_reference_is_preserved_but_not_authoritative(self):
        legacy = server.merge_session_liquidity_context(None, self.build(legacy_payload("YM1!")))
        lock = entry_agent.build_session_locked_tv_context(legacy)
        rehydrated = entry_agent.locked_session_liquidity_context(
            {"state_by_symbol": {"YM": {"session_liquidity_context": lock}}},
            "YM",
        )

        self.assertIsNone(legacy["session_lock_price"])
        self.assertFalse(legacy["liquidity_context_authoritative"])
        self.assertEqual(legacy["liquidity_context_authority_error"], "SESSION_LOCK_REFERENCE_PRICE_MISSING")
        self.assertFalse(lock["locked"])
        self.assertTrue(lock["disabled"])
        self.assertIn("SESSION_LOCK_REFERENCE_PRICE_MISSING", lock["error"])
        self.assertFalse(rehydrated["locked"])
        self.assertTrue(rehydrated["disabled"])

    def test_nq_and_ym_share_reference_and_membership_rules(self):
        for symbol in ("NQ1!", "YM1!"):
            with self.subTest(symbol=symbol):
                context = self.build(canonical_payload(symbol, stacked_yh=True))
                lock = entry_agent.build_session_locked_tv_context(context)
                self.assertTrue(lock["locked"])
                self.assertEqual(lock["tv_context"]["session_lock_price"], 52437)
                high = next(group for group in lock["active_groups"] if group.get("stack_group") == "HIGH 1")
                self.assertEqual(set(high["components"]), {"ONH", "YH"})

    def test_unstacked_yh_remains_valid_under_the_same_canonical_schema(self):
        for symbol in ("NQ1!", "YM1!"):
            with self.subTest(symbol=symbol):
                context = self.build(canonical_payload(symbol, stacked_yh=False))
                lock = entry_agent.build_session_locked_tv_context(context)
                self.assertTrue(lock["locked"])
                self.assertEqual(lock["tv_context"]["levels"]["YH"]["stack_group"], "NONE")
                self.assertEqual(lock["tv_context"]["session_lock_price"], 52437)

    def test_explicit_reconstruction_is_session_bound_auditable_and_symbol_scoped(self):
        legacy = server.merge_session_liquidity_context(None, self.build(legacy_payload("YM1!")))
        canonical = self.build(canonical_payload("YM1!", stacked_yh=True))
        recurring = server.merge_session_liquidity_context(legacy, canonical)
        legacy_lock = entry_agent.build_session_locked_tv_context(legacy)
        nq_sentinel = {"locked": True, "tv_context": {"session_date": "NQ_UNCHANGED"}}

        with tempfile.TemporaryDirectory(prefix="canonical_lock_reconstruction_") as temp_dir:
            temp = Path(temp_dir)
            context_path = temp / "tv_context.json"
            contexts_path = temp / "tv_context_by_symbol.json"
            state_path = temp / "entry_agent_state.json"
            audit_path = temp / "logs" / "operator_actions.jsonl"
            context_path.write_text(json.dumps(recurring), encoding="utf-8")
            contexts_path.write_text(
                json.dumps({"symbols": {"YM": recurring, "NQ": {"sentinel": "unchanged"}}}),
                encoding="utf-8",
            )
            state_path.write_text(
                json.dumps({
                    "state_by_symbol": {
                        "YM": {
                            "normalized_symbol": "YM",
                            "session_liquidity_context": legacy_lock,
                            "step_2_1a": {"status": "CONFIRMED"},
                            "event_log": [],
                        },
                        "NQ": {"normalized_symbol": "NQ", "session_liquidity_context": nq_sentinel},
                    }
                }),
                encoding="utf-8",
            )
            flat_snapshot = {"ok": True, "symbols": {"YMU6": {"position_qty": 0, "working_orders": []}}}
            with (
                mock.patch.object(server, "TV_CONTEXT_PATH", context_path),
                mock.patch.object(server, "TV_CONTEXT_BY_SYMBOL_PATH", contexts_path),
                mock.patch.object(server, "ENTRY_AGENT_STATE_PATH", state_path),
                mock.patch.object(server, "OPERATOR_AUDIT_LOG_PATH", audit_path),
                mock.patch.object(server, "ENTRY_LOG_DIR", audit_path.parent),
                mock.patch.object(server, "fetch_local_json", return_value=flat_snapshot),
            ):
                response = server.app.test_client().post(
                    "/operator/liquidity-lock/reconstruct-from-latest-canonical",
                    json={"symbol": "YM", "reason": server.CANONICAL_LOCK_RECONSTRUCTION_REASON},
                )

            self.assertEqual(response.status_code, 200, response.get_json())
            result = response.get_json()
            self.assertEqual(result["session_lock_price"], 52437)
            self.assertEqual(result["stack_threshold"], 62.0)
            self.assertEqual(result["daily_atr14"], 611.0949591232)
            self.assertEqual(result["source_timestamp"], canonical["timestamp"])
            self.assertEqual(result["audit_event"], "canonical_liquidity_lock_reconstructed")
            self.assertIn("step_2_1a", result["cleared_fields"])

            persisted_contexts = json.loads(contexts_path.read_text(encoding="utf-8"))
            persisted_state = json.loads(state_path.read_text(encoding="utf-8"))
            ym_context = persisted_contexts["symbols"]["YM"]
            ym_lock = persisted_state["state_by_symbol"]["YM"]["session_liquidity_context"]
            self.assertEqual(persisted_contexts["symbols"]["NQ"], {"sentinel": "unchanged"})
            self.assertEqual(persisted_state["state_by_symbol"]["NQ"]["session_liquidity_context"], nq_sentinel)
            self.assertEqual(ym_context["session_lock_price"], 52437)
            self.assertEqual(ym_context["locked_liquidity_context"]["session_lock_price"], 52437)
            self.assertEqual(ym_context["stack_threshold"], 62.0)
            self.assertEqual(ym_context["daily_atr14"], 611.0949591232)
            self.assertNotEqual(ym_context["liquidity_context_locked_at"], legacy["liquidity_context_locked_at"])
            self.assertEqual(
                ym_context["locked_liquidity_context"]["lock_reconstruction"]["previous_locked_at"],
                legacy["liquidity_context_locked_at"],
            )
            rehydrated = entry_agent.locked_session_liquidity_context(persisted_state, "YM")
            self.assertTrue(rehydrated["locked"])
            self.assertEqual(rehydrated["tv_context"]["session_lock_price"], 52437)
            next_context = self.build(canonical_payload("YM1!", stacked_yh=True))
            after_recurring = server.merge_session_liquidity_context(ym_context, next_context)
            self.assertEqual(after_recurring["session_lock_price"], 52437)
            self.assertEqual(after_recurring["stack_threshold"], 62.0)
            self.assertEqual(after_recurring["daily_atr14"], 611.0949591232)
            self.assertTrue(after_recurring["liquidity_context_authoritative"])
            audit = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(audit[0]["event"], "canonical_liquidity_lock_reconstruction_requested")
            self.assertEqual(audit[-1]["status"], "success")
            self.assertTrue(list(temp.glob("tv_context_by_symbol.json.bak_*")))
            self.assertTrue(list(temp.glob("entry_agent_state.json.bak_*")))

    def test_reconstruction_refuses_prior_session_candidate(self):
        legacy = server.merge_session_liquidity_context(None, self.build(legacy_payload("YM1!")))
        lock = entry_agent.build_session_locked_tv_context(legacy)
        candidate = self.build(canonical_payload("YM1!"))
        yesterday = (datetime.now(MARKET_TIMEZONE).date() - timedelta(days=1)).isoformat()
        candidate["session_date"] = yesterday
        legacy["last_tv_context_candidate"] = candidate

        rebuilt, error = server._reconstruct_frozen_lock_from_latest_canonical("YM", legacy, lock)

        self.assertIsNone(rebuilt)
        self.assertEqual(error["error"], "session_date_mismatch")


if __name__ == "__main__":
    unittest.main()
