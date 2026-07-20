import json
import tempfile
import unittest
from pathlib import Path

from compact_trade_manager_tick_journals import compact_journals


def append_event(path, event):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, separators=(",", ":")) + "\n")


def tick_key(symbol, sequence):
    return f"{symbol}U6|run-1:{sequence}|2026-07-20T14:00:{sequence:02d}.000000000Z"


def trade_manager_acceptance(symbol, sequence):
    key = tick_key(symbol, sequence)
    return key, {
        "record_type": "trade_manager_tick_state",
        "pipeline_version": "trade_manager_symbol_fifo_wal_v3",
        "state": "accepted_by_trade_manager",
        "symbol_root": symbol,
        "tick_key": key,
        "tick": {
            "symbol": f"{symbol}U6",
            "symbol_root": symbol,
            "tick_key": key,
            "listener_tick_id": f"run-1:{sequence}",
            "listener_sequence": sequence,
            "executor_acceptance_sequence": sequence,
            "rithmic_source_timestamp_utc": f"2026-07-20T14:00:{sequence:02d}.000000000Z",
            "state": "accepted_by_trade_manager",
        },
    }


def executor_acceptance(symbol, sequence):
    key = tick_key(symbol, sequence)
    return key, {
        "record_type": "executor_tick_state",
        "pipeline_version": "executor_symbol_fifo_wal_v3",
        "state": "accepted_by_executor",
        "symbol_root": symbol,
        "tick_key": key,
        "tick": {
            "symbol": f"{symbol}U6",
            "symbol_root": symbol,
            "tick_key": key,
            "listener_tick_id": f"run-1:{sequence}",
            "listener_sequence": sequence,
            "executor_acceptance_sequence": sequence,
            "rithmic_source_timestamp_utc": f"2026-07-20T14:00:{sequence:02d}.000000000Z",
            "state": "accepted_by_executor",
        },
    }


def terminal_event(record_type, symbol, key, version=None, acknowledged=False):
    event = {
        "record_type": record_type,
        "pipeline_version": (
            "trade_manager_symbol_fifo_wal_v3"
            if record_type == "trade_manager_tick_state"
            else "executor_symbol_fifo_wal_v3"
        ),
        "state": "completed_by_trade_manager",
        "symbol_root": symbol,
        "tick_key": key,
    }
    if version is not None:
        event["trade_manager_state_version"] = version
    if acknowledged:
        event["completion_notification_state"] = "accepted_by_executor"
    return event


class TradeManagerTickJournalCompactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tm_tick_compaction_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manager_root = self.root / "manager"
        self.executor_root = self.root / "executor"
        self.persistence = self.root / "persistence_state.json"

    def write_persistence(self, version):
        self.persistence.write_text(
            json.dumps({"system": {"trade_manager_tick_state_version": version}, "trades": {}}),
            encoding="utf-8",
        )

    def append_manager_acceptance(self, symbol, sequence):
        key, event = trade_manager_acceptance(symbol, sequence)
        append_event(self.manager_root / f"{symbol}_ticks.jsonl", event)
        return key

    def append_manager_state(self, symbol, event):
        append_event(self.manager_root / f"{symbol}_tick_states.jsonl", event)

    def append_executor_acceptance(self, symbol, sequence):
        key, event = executor_acceptance(symbol, sequence)
        append_event(self.executor_root / f"{symbol}_ticks.jsonl", event)
        return key

    def append_executor_state(self, symbol, event):
        append_event(self.executor_root / f"{symbol}_tick_states.jsonl", event)

    def seed_acknowledged_symbol(self, symbol, sequence, version):
        manager_key = self.append_manager_acceptance(symbol, sequence)
        self.append_manager_state(
            symbol,
            terminal_event(
                "trade_manager_tick_state",
                symbol,
                manager_key,
                version=version,
                acknowledged=True,
            ),
        )
        executor_key = self.append_executor_acceptance(symbol, sequence)
        self.append_executor_state(
            symbol,
            terminal_event("executor_tick_state", symbol, executor_key, version=version),
        )
        return manager_key

    def run_compaction(self, threshold=1):
        return compact_journals(
            self.manager_root,
            self.executor_root,
            self.persistence,
            threshold_bytes=threshold,
        )

    def test_compaction_archives_history_and_retains_latest_sequence_authority(self):
        self.write_persistence(20)
        old_key = self.append_manager_acceptance("NQ", 1)
        self.append_manager_state(
            "NQ",
            terminal_event("trade_manager_tick_state", "NQ", old_key, version=10),
        )
        latest_key = self.append_manager_acceptance("NQ", 2)
        self.append_manager_state(
            "NQ",
            terminal_event("trade_manager_tick_state", "NQ", latest_key, version=20),
        )
        executor_key = self.append_executor_acceptance("NQ", 2)
        self.append_executor_state(
            "NQ",
            terminal_event("executor_tick_state", "NQ", executor_key, version=20),
        )
        self.seed_acknowledged_symbol("YM", 1, 20)

        result = self.run_compaction()

        nq_ticks = [
            json.loads(line)
            for line in (self.manager_root / "NQ_ticks.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        nq_states = [
            json.loads(line)
            for line in (self.manager_root / "NQ_tick_states.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual([event["tick_key"] for event in nq_ticks], [latest_key])
        self.assertEqual(nq_states[-1]["completion_notification_state"], "accepted_by_executor")
        self.assertEqual(
            nq_states[-1]["completion_notification_reconciliation"],
            "executor_terminal_state_present_during_offline_compaction",
        )
        self.assertTrue(any(self.manager_root.glob("NQ_ticks.jsonl.archive.*")))
        self.assertTrue(any(self.manager_root.glob("NQ_tick_states.jsonl.archive.*")))
        self.assertEqual(result[0]["retained_tick_count"], 1)
        self.assertEqual(result[0]["reconciled_notification_count"], 1)

    def test_compaction_retains_executor_nonterminal_completion(self):
        self.write_persistence(10)
        key = self.append_manager_acceptance("NQ", 1)
        self.append_manager_state(
            "NQ",
            terminal_event("trade_manager_tick_state", "NQ", key, version=10),
        )
        executor_key = self.append_executor_acceptance("NQ", 1)
        self.append_executor_state(
            "NQ",
            {
                "record_type": "executor_tick_state",
                "pipeline_version": "executor_symbol_fifo_wal_v3",
                "state": "accepted_by_trade_manager",
                "symbol_root": "NQ",
                "tick_key": executor_key,
            },
        )
        self.seed_acknowledged_symbol("YM", 1, 10)

        result = self.run_compaction()

        self.assertEqual(result[0]["retained_reason_counts"], {"executor_nonterminal": 1})
        states = [
            json.loads(line)
            for line in (self.manager_root / "NQ_tick_states.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertFalse(
            any(event.get("completion_notification_reconciliation") for event in states)
        )

    def test_compaction_retains_canonical_delta_newer_than_persistence(self):
        self.write_persistence(9)
        key = self.append_manager_acceptance("NQ", 1)
        self.append_manager_state(
            "NQ",
            terminal_event("trade_manager_tick_state", "NQ", key, version=10),
        )
        executor_key = self.append_executor_acceptance("NQ", 1)
        self.append_executor_state(
            "NQ",
            terminal_event("executor_tick_state", "NQ", executor_key, version=10),
        )
        self.seed_acknowledged_symbol("YM", 1, 9)

        result = self.run_compaction()

        self.assertEqual(
            result[0]["retained_reason_counts"],
            {"canonical_delta_not_persisted": 1},
        )

    def test_compaction_fails_closed_when_retained_tick_lacks_executor_authority(self):
        self.write_persistence(0)
        key = self.append_manager_acceptance("NQ", 1)
        self.append_manager_state(
            "NQ",
            {
                "record_type": "trade_manager_tick_state",
                "pipeline_version": "trade_manager_symbol_fifo_wal_v3",
                "state": "processing",
                "symbol_root": "NQ",
                "tick_key": key,
            },
        )
        # Give Executor a different current key so its authority is present but contradictory.
        other_key = self.append_executor_acceptance("NQ", 2)
        self.append_executor_state(
            "NQ",
            terminal_event("executor_tick_state", "NQ", other_key, version=1),
        )
        self.seed_acknowledged_symbol("YM", 1, 1)

        with self.assertRaisesRegex(
            RuntimeError,
            "retained_trade_manager_tick_missing_executor_authority:NQ",
        ):
            self.run_compaction()

    def test_compaction_fails_closed_on_malformed_journal_json(self):
        self.write_persistence(1)
        self.seed_acknowledged_symbol("NQ", 1, 1)
        self.seed_acknowledged_symbol("YM", 1, 1)
        with (self.manager_root / "NQ_tick_states.jsonl").open("a", encoding="utf-8") as handle:
            handle.write("{not-json}\n")

        with self.assertRaisesRegex(RuntimeError, "invalid_json"):
            self.run_compaction()


if __name__ == "__main__":
    unittest.main()
