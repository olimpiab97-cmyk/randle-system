import argparse
import json
import os
import shutil
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import msvcrt


TRADE_MANAGER_RECORD_TYPE = "trade_manager_tick_state"
EXECUTOR_RECORD_TYPE = "executor_tick_state"
TRADE_MANAGER_TERMINAL_STATES = {"completed_by_trade_manager", "failed"}
EXECUTOR_TERMINAL_STATES = {"completed_by_trade_manager", "failed"}
DEFAULT_THRESHOLD_BYTES = 64 * 1024 * 1024


def iter_records(path, expected_record_type):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            try:
                record = json.loads(raw_line)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"invalid_json:{path}:{line_number}:{exc}") from exc
            if not isinstance(record, dict):
                raise RuntimeError(f"invalid_record_type:{path}:{line_number}")
            if record.get("record_type") != expected_record_type:
                raise RuntimeError(
                    f"unexpected_record_type:{path}:{line_number}:{record.get('record_type')}"
                )
            yield raw_line, record


def write_raw(handle, raw_line):
    handle.write(raw_line.rstrip("\r\n"))
    handle.write("\n")


def durable_close(handle):
    handle.flush()
    os.fsync(handle.fileno())
    handle.close()


def archive_path(path, stamp):
    candidate = path.with_name(f"{path.name}.archive.{stamp}")
    if not candidate.exists():
        return candidate
    return path.with_name(f"{path.name}.archive.{stamp}.{uuid.uuid4().hex[:8]}")


def load_persisted_trade_manager_version(persistence_file):
    try:
        with persistence_file.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
    except Exception as exc:
        raise RuntimeError(f"persistence_state_invalid:{persistence_file}:{exc}") from exc
    if not isinstance(state, dict) or not isinstance(state.get("system"), dict):
        raise RuntimeError(f"persistence_state_schema_invalid:{persistence_file}")
    raw_version = state["system"].get("trade_manager_tick_state_version")
    try:
        version = int(raw_version)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"persistence_tick_state_version_invalid:{persistence_file}:{raw_version}"
        ) from exc
    if version < 0:
        raise RuntimeError(f"persistence_tick_state_version_negative:{version}")
    return version


def load_executor_records(executor_root, symbol):
    tick_path = executor_root / f"{symbol}_ticks.jsonl"
    state_path = executor_root / f"{symbol}_tick_states.jsonl"
    if not tick_path.exists() or not state_path.exists():
        raise RuntimeError(f"executor_journal_pair_missing:{symbol}")

    records = {}
    acceptance_order = []
    for _, event in iter_records(tick_path, EXECUTOR_RECORD_TYPE):
        if event.get("state") != "accepted_by_executor" or not isinstance(event.get("tick"), dict):
            raise RuntimeError(f"executor_acceptance_record_invalid:{tick_path}")
        tick_key = str(event.get("tick_key") or "")
        if not tick_key:
            raise RuntimeError(f"executor_tick_key_missing:{tick_path}")
        if tick_key in records:
            raise RuntimeError(f"executor_duplicate_acceptance:{symbol}:{tick_key}")
        record = dict(event["tick"])
        record["state"] = "accepted_by_executor"
        records[tick_key] = record
        acceptance_order.append(tick_key)

    for _, event in iter_records(state_path, EXECUTOR_RECORD_TYPE):
        tick_key = str(event.get("tick_key") or "")
        if not tick_key:
            raise RuntimeError(f"executor_state_tick_key_missing:{state_path}")
        if tick_key in records:
            records[tick_key].update(event)

    return records, acceptance_order


def load_trade_manager_state_summary(state_path):
    summary = {}
    event_count = 0
    for _, event in iter_records(state_path, TRADE_MANAGER_RECORD_TYPE):
        event_count += 1
        tick_key = str(event.get("tick_key") or "")
        if not tick_key:
            raise RuntimeError(f"trade_manager_state_tick_key_missing:{state_path}")
        current = summary.setdefault(tick_key, {})
        current.update(event)
    return summary, event_count


def state_version(record):
    raw_value = record.get("trade_manager_state_version")
    if raw_value in (None, ""):
        return None
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"trade_manager_state_version_invalid:{raw_value}") from exc
    if value < 0:
        raise RuntimeError(f"trade_manager_state_version_negative:{value}")
    return value


def retention_reason(summary, executor_record, persisted_version):
    state = str(summary.get("state") or "accepted_by_trade_manager")
    if state not in TRADE_MANAGER_TERMINAL_STATES:
        return "trade_manager_nonterminal"

    version = state_version(summary)
    if version is not None and version > persisted_version:
        return "canonical_delta_not_persisted"

    executor_state = str((executor_record or {}).get("state") or "")
    if executor_record is not None and executor_state not in EXECUTOR_TERMINAL_STATES:
        return "executor_nonterminal"
    return None


def validate_candidate(tick_temp, state_temp, retained_keys, expected_latest_key):
    accepted_keys = []
    for _, event in iter_records(tick_temp, TRADE_MANAGER_RECORD_TYPE):
        if event.get("state") != "accepted_by_trade_manager" or not isinstance(event.get("tick"), dict):
            raise RuntimeError(f"candidate_acceptance_record_invalid:{tick_temp}")
        accepted_keys.append(str(event.get("tick_key") or ""))

    if len(accepted_keys) != len(set(accepted_keys)):
        raise RuntimeError("candidate_duplicate_trade_manager_acceptance")
    if set(accepted_keys) != set(retained_keys):
        raise RuntimeError("candidate_retained_key_mismatch")
    if not accepted_keys or accepted_keys[-1] != expected_latest_key:
        raise RuntimeError("candidate_latest_sequence_authority_missing")

    state_keys = set()
    for _, event in iter_records(state_temp, TRADE_MANAGER_RECORD_TYPE):
        tick_key = str(event.get("tick_key") or "")
        if tick_key not in retained_keys:
            raise RuntimeError(f"candidate_unretained_state_event:{tick_key}")
        state_keys.add(tick_key)

    return {
        "retained_tick_count": len(accepted_keys),
        "state_tick_count": len(state_keys),
        "latest_tick_key": expected_latest_key,
    }


def restore_from_archive(path, archive):
    restore_temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.restore.tmp")
    with archive.open("rb") as source, restore_temp.open("wb") as target:
        shutil.copyfileobj(source, target)
        target.flush()
        os.fsync(target.fileno())
    os.replace(restore_temp, path)


def compact_symbol(
    journal_root,
    executor_root,
    symbol,
    persisted_version,
    threshold_bytes,
    stamp,
):
    tick_path = journal_root / f"{symbol}_ticks.jsonl"
    state_path = journal_root / f"{symbol}_tick_states.jsonl"
    if not tick_path.exists() or not state_path.exists():
        raise RuntimeError(f"trade_manager_journal_pair_missing:{symbol}")

    original_bytes = tick_path.stat().st_size + state_path.stat().st_size
    if original_bytes < threshold_bytes:
        return {
            "symbol": symbol,
            "status": "below_threshold",
            "original_bytes": original_bytes,
            "threshold_bytes": threshold_bytes,
        }

    executor_records, executor_order = load_executor_records(executor_root, symbol)
    if not executor_order:
        raise RuntimeError(f"executor_sequence_authority_missing:{symbol}")
    state_summary, state_event_count = load_trade_manager_state_summary(state_path)

    tick_temp = tick_path.with_name(f".{tick_path.name}.{uuid.uuid4().hex}.tmp")
    state_temp = state_path.with_name(f".{state_path.name}.{uuid.uuid4().hex}.tmp")
    retained_keys = set()
    retained_reasons = {}
    accepted_keys = set()
    accepted_event_count = 0
    latest_tick_key = None
    latest_raw = None

    tick_handle = tick_temp.open("w", encoding="utf-8", newline="\n")
    try:
        for raw_line, event in iter_records(tick_path, TRADE_MANAGER_RECORD_TYPE):
            if event.get("state") != "accepted_by_trade_manager" or not isinstance(event.get("tick"), dict):
                raise RuntimeError(f"trade_manager_acceptance_record_invalid:{tick_path}")
            tick_key = str(event.get("tick_key") or "")
            if not tick_key:
                raise RuntimeError(f"trade_manager_tick_key_missing:{tick_path}")
            if tick_key in accepted_keys:
                raise RuntimeError(f"trade_manager_duplicate_acceptance:{symbol}:{tick_key}")
            accepted_keys.add(tick_key)
            accepted_event_count += 1
            latest_tick_key = tick_key
            latest_raw = raw_line

            summary = state_summary.get(tick_key, {})
            reason = retention_reason(summary, executor_records.get(tick_key), persisted_version)
            if reason:
                write_raw(tick_handle, raw_line)
                retained_keys.add(tick_key)
                retained_reasons[tick_key] = reason

        if latest_tick_key is None or latest_raw is None:
            raise RuntimeError(f"trade_manager_sequence_authority_missing:{symbol}")
        if latest_tick_key not in retained_keys:
            write_raw(tick_handle, latest_raw)
            retained_keys.add(latest_tick_key)
            retained_reasons[latest_tick_key] = "latest_sequence_authority"
        durable_close(tick_handle)
    except Exception:
        if not tick_handle.closed:
            tick_handle.close()
        tick_temp.unlink(missing_ok=True)
        raise

    unknown_state_keys = set(state_summary) - accepted_keys
    if unknown_state_keys:
        tick_temp.unlink(missing_ok=True)
        sample = sorted(unknown_state_keys)[:3]
        raise RuntimeError(f"trade_manager_state_without_acceptance:{symbol}:{sample}")

    missing_executor_keys = sorted(key for key in retained_keys if key not in executor_records)
    if missing_executor_keys:
        tick_temp.unlink(missing_ok=True)
        raise RuntimeError(
            f"retained_trade_manager_tick_missing_executor_authority:{symbol}:{missing_executor_keys[:3]}"
        )

    reconciled_notifications = []
    state_handle = state_temp.open("w", encoding="utf-8", newline="\n")
    try:
        for raw_line, event in iter_records(state_path, TRADE_MANAGER_RECORD_TYPE):
            if event.get("tick_key") in retained_keys:
                write_raw(state_handle, raw_line)

        reconciliation_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        for tick_key in sorted(retained_keys):
            summary = state_summary.get(tick_key, {})
            executor_record = executor_records[tick_key]
            manager_state = str(summary.get("state") or "accepted_by_trade_manager")
            executor_state = str(executor_record.get("state") or "")
            if (
                manager_state in TRADE_MANAGER_TERMINAL_STATES
                and executor_state in EXECUTOR_TERMINAL_STATES
                and summary.get("completion_notification_state") != "accepted_by_executor"
            ):
                reconciliation = {
                    "record_type": TRADE_MANAGER_RECORD_TYPE,
                    "pipeline_version": summary.get("pipeline_version")
                    or "trade_manager_symbol_fifo_wal_v3",
                    "recorded_at_utc": reconciliation_time,
                    "symbol_root": symbol,
                    "tick_key": tick_key,
                    "state": manager_state,
                    "completion_notification_state": "accepted_by_executor",
                    "completion_notification_failure": None,
                    "completion_notification_reconciled_at_utc": reconciliation_time,
                    "completion_notification_reconciliation": "executor_terminal_state_present_during_offline_compaction",
                }
                write_raw(
                    state_handle,
                    json.dumps(reconciliation, sort_keys=True, separators=(",", ":")),
                )
                reconciled_notifications.append(tick_key)
        durable_close(state_handle)
    except Exception:
        if not state_handle.closed:
            state_handle.close()
        tick_temp.unlink(missing_ok=True)
        state_temp.unlink(missing_ok=True)
        raise

    candidate = validate_candidate(
        tick_temp,
        state_temp,
        retained_keys,
        latest_tick_key,
    )

    archives = {}
    try:
        for name, path in (("ticks", tick_path), ("states", state_path)):
            archive = archive_path(path, stamp)
            os.link(path, archive)
            archives[name] = archive
    except Exception:
        tick_temp.unlink(missing_ok=True)
        state_temp.unlink(missing_ok=True)
        for archive in archives.values():
            archive.unlink(missing_ok=True)
        raise

    tick_replaced = False
    state_replaced = False
    try:
        os.replace(tick_temp, tick_path)
        tick_replaced = True
        os.replace(state_temp, state_path)
        state_replaced = True
    except Exception:
        if tick_replaced:
            restore_from_archive(tick_path, archives["ticks"])
        if state_replaced:
            restore_from_archive(state_path, archives["states"])
        tick_temp.unlink(missing_ok=True)
        state_temp.unlink(missing_ok=True)
        raise

    compacted_bytes = tick_path.stat().st_size + state_path.stat().st_size
    reason_counts = {}
    for reason in retained_reasons.values():
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    return {
        "symbol": symbol,
        "status": "compacted",
        "original_bytes": original_bytes,
        "compacted_bytes": compacted_bytes,
        "accepted_events_scanned": accepted_event_count,
        "state_events_scanned": state_event_count,
        "retained_tick_count": candidate["retained_tick_count"],
        "retained_reason_counts": reason_counts,
        "reconciled_notification_count": len(reconciled_notifications),
        "latest_tick_key": candidate["latest_tick_key"],
        "executor_latest_tick_key": executor_order[-1],
        "persisted_trade_manager_state_version": persisted_version,
        "archives": {key: str(value) for key, value in archives.items()},
    }


@contextmanager
def exclusive_lock(journal_root):
    journal_root.mkdir(parents=True, exist_ok=True)
    lock_path = journal_root / "trade_manager_tick_compaction.lock"
    handle = lock_path.open("a+b")
    try:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        yield
    finally:
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            handle.close()


def compact_journals(
    journal_root,
    executor_root,
    persistence_file,
    threshold_bytes=DEFAULT_THRESHOLD_BYTES,
):
    journal_root = Path(journal_root)
    executor_root = Path(executor_root)
    persistence_file = Path(persistence_file)
    persisted_version = load_persisted_trade_manager_version(persistence_file)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with exclusive_lock(journal_root):
        return [
            compact_symbol(
                journal_root,
                executor_root,
                symbol,
                persisted_version,
                threshold_bytes,
                stamp,
            )
            for symbol in ("NQ", "YM")
        ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal-root", required=True)
    parser.add_argument("--executor-journal-root", required=True)
    parser.add_argument("--persistence-file", required=True)
    parser.add_argument("--threshold-bytes", type=int, default=DEFAULT_THRESHOLD_BYTES)
    args = parser.parse_args()
    try:
        results = compact_journals(
            args.journal_root,
            args.executor_journal_root,
            args.persistence_file,
            args.threshold_bytes,
        )
    except Exception as exc:
        print(f"{type(exc).__name__}:{exc}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "results": results}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
