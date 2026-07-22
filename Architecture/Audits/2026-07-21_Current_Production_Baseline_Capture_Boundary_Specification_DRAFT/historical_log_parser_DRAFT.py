#!/usr/bin/env python3
"""Versioned parser for the bound 2026-07-20 broad pytest log.

The source was produced in quiet mode.  Failed and subfailed node IDs are
present in the terminal summary.  Passed and skipped node IDs are not present;
those outcomes are therefore identified by immutable progress-event byte
ranges and are never given fabricated node names.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


PARSER_NAME = "randle-pytest-quiet-log-parser"
PARSER_VERSION = "4.0.0-DRAFT"
NORMALIZATION_RULE = "UTF8-LF-OR-CRLF-PRESERVE-BYTE-RANGES"
FAILURE_RULE = "FAILED_AND_SUBFAILED_REQUIRE_SOURCE_NODE_AND_CLASSIFICATION"
EXPECTED_LOG_SHA256 = "6F1B876C814B25D27F5EF8B4CFE3A66C4B0E847263FEC784C56896DC8FF3194A"
EXPECTED_COUNTS = {"PASSED": 571, "FAILED": 156, "SUBFAILED": 23, "SKIPPED": 3, "ERROR": 0, "XFAIL": 0, "XPASS": 0}
PROGRESS_RE = re.compile(rb"^(?P<events>[.FEsxX]+)(?:\s+\[\s*\d+%\])?\r?\n?$")
FAILED_RE = re.compile(r"^FAILED (?P<node>\S+)$")
SUBFAILED_RE = re.compile(r"^SUBFAILED\(name=(?P<name>.+)\) (?P<parent>\S+)$")
SUMMARY_RE = re.compile(r"^(?P<failed>\d+) failed, (?P<passed>\d+) passed, (?P<skipped>\d+) skipped, (?P<subtests>\d+) subtests passed ")


class HistoricalLogError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _line_records(data: bytes) -> Iterable[tuple[int, int, int, bytes]]:
    offset = 0
    for line_number, line in enumerate(data.splitlines(keepends=True), 1):
        yield line_number, offset, offset + len(line), line
        offset += len(line)
    if offset != len(data):
        raise HistoricalLogError("LOG_LINE_ACCOUNTING", f"{offset}!={len(data)}")


def _location(line: int, column: int, byte_start: int, byte_end: int) -> dict[str, int]:
    return {"line": line, "column": column, "byte_start": byte_start, "byte_end": byte_end}


def _classified_fields(status: str, node: str) -> dict[str, str | None]:
    if status not in {"FAILED", "SUBFAILED", "ERROR", "XPASS"}:
        return {
            "classification_category": None,
            "classification_rationale": None,
            "source_reference": None,
            "parser_name": None,
            "parser_version": None,
            "normalization_rule": None,
            "classification_rule": None,
        }
    category = "HISTORICAL_SUBTEST_FAILURE" if status == "SUBFAILED" else "HISTORICAL_TEST_FAILURE"
    return {
        "classification_category": category,
        "classification_rationale": f"The bound historical pytest log records {status} for {node}.",
        "source_reference": "BOUND_FULL_LOG_AND_EXACT_EVENT_RANGE",
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "normalization_rule": NORMALIZATION_RULE,
        "classification_rule": FAILURE_RULE,
    }


def parse_historical_log(data: bytes, log_path: str) -> dict[str, Any]:
    if _sha256(data) != EXPECTED_LOG_SHA256:
        raise HistoricalLogError("BROAD_LOG_HASH", _sha256(data))
    failed_summary: list[dict[str, Any]] = []
    subfailed_summary: list[dict[str, Any]] = []
    progress: list[dict[str, Any]] = []
    terminal_summary: Mapping[str, str] | None = None
    for line_number, byte_start, byte_end, raw in _line_records(data):
        text = raw.decode("utf-8", errors="strict").rstrip("\r\n")
        progress_match = PROGRESS_RE.fullmatch(raw)
        if progress_match:
            prefix = progress_match.group("events")
            for column, token in enumerate(prefix, 1):
                progress.append(
                    {
                        "token": chr(token),
                        "source_location": _location(
                            line_number,
                            column,
                            byte_start + column - 1,
                            byte_start + column,
                        ),
                    }
                )
            continue
        failed_match = FAILED_RE.fullmatch(text)
        if failed_match:
            failed_summary.append(
                {
                    "node": failed_match.group("node"),
                    "source_location": _location(line_number, 1, byte_start, byte_end),
                    "source_text": text,
                }
            )
            continue
        subfailed_match = SUBFAILED_RE.fullmatch(text)
        if subfailed_match:
            try:
                name = ast.literal_eval(subfailed_match.group("name"))
            except (SyntaxError, ValueError) as exc:
                raise HistoricalLogError("SUBFAILED_NAME_PARSE", f"line={line_number}") from exc
            if not isinstance(name, str) or not name:
                raise HistoricalLogError("SUBFAILED_NAME_PARSE", f"line={line_number}")
            subfailed_summary.append(
                {
                    "name": name,
                    "parent": subfailed_match.group("parent"),
                    "source_location": _location(line_number, 1, byte_start, byte_end),
                    "source_text": text,
                }
            )
            continue
        summary_match = SUMMARY_RE.match(text)
        if summary_match:
            terminal_summary = summary_match.groupdict()
    if terminal_summary is None:
        raise HistoricalLogError("MISSING_TERMINAL_SUMMARY")
    if len(failed_summary) != EXPECTED_COUNTS["FAILED"] or len(subfailed_summary) != EXPECTED_COUNTS["SUBFAILED"]:
        raise HistoricalLogError("NAMED_OUTCOME_COUNT", f"{len(failed_summary)}/{len(subfailed_summary)}")
    token_counts = Counter(item["token"] for item in progress)
    expected_tokens = {".": 571, "F": 156, "s": 3}
    if dict(token_counts) != expected_tokens:
        raise HistoricalLogError("PROGRESS_EVENT_COUNT", repr(dict(token_counts)))
    if (
        int(terminal_summary["failed"]) != 179
        or int(terminal_summary["passed"]) != 571
        or int(terminal_summary["skipped"]) != 3
    ):
        raise HistoricalLogError("TERMINAL_SUMMARY_COUNT", repr(dict(terminal_summary)))
    outcomes: list[dict[str, Any]] = []
    failed_index = 0
    for ordinal, event in enumerate(progress, 1):
        token = event["token"]
        status = {".": "PASSED", "F": "FAILED", "s": "SKIPPED"}[token]
        summary_location = None
        if status == "FAILED":
            summary = failed_summary[failed_index]
            failed_index += 1
            node_identity = summary["node"]
            summary_location = summary["source_location"]
            identity = node_identity
        else:
            node_identity = None
            identity = f"QUIET_PROGRESS::{status}::{event['source_location']['byte_start']:08d}"
        outcome = {
            "identity": identity,
            "node_identity": node_identity,
            "event_identity": f"PYTEST_PROGRESS_EVENT::{ordinal:04d}",
            "parent_identity": None,
            "outcome": status,
            "source_log_location": event["source_location"],
            "summary_log_location": summary_location,
            **_classified_fields(status, node_identity or identity),
        }
        outcomes.append(outcome)
    for item in subfailed_summary:
        identity = f"{item['parent']}::SUBFAILED[{item['name']}]"
        outcomes.append(
            {
                "identity": identity,
                "node_identity": identity,
                "event_identity": f"PYTEST_SUBFAILED_SUMMARY::{item['source_location']['byte_start']:08d}",
                "parent_identity": item["parent"],
                "outcome": "SUBFAILED",
                "source_log_location": item["source_location"],
                "summary_log_location": item["source_location"],
                **_classified_fields("SUBFAILED", identity),
            }
        )
    counts = Counter(item["outcome"] for item in outcomes)
    for status in EXPECTED_COUNTS:
        counts.setdefault(status, 0)
    if dict(sorted(counts.items())) != dict(sorted(EXPECTED_COUNTS.items())):
        raise HistoricalLogError("OUTCOME_COUNT", repr(dict(counts)))
    categories = Counter(item["classification_category"] for item in outcomes if item["classification_category"])
    identities = [item["identity"] for item in outcomes]
    if len(identities) != len(set(identities)):
        raise HistoricalLogError("DUPLICATE_OUTCOME")
    record = {
        "schema_version": "4.0.0-DRAFT",
        "canonical_serialization": "RANDLE-CAPTURE-CJSON-1",
        "authority": "ACTUAL_BOUND_HISTORICAL_LOG_PENDING_INDEPENDENT_REVIEW",
        "full_log_path": log_path,
        "full_log_size": len(data),
        "full_log_sha256": EXPECTED_LOG_SHA256,
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "normalization_rules": [NORMALIZATION_RULE],
        "classification_rules": [FAILURE_RULE],
        "outcomes": outcomes,
        "outcome_identity_set_sha256": _sha256(json.dumps(sorted(identities), ensure_ascii=False, separators=(",", ":")).encode("utf-8")),
        "outcome_count_by_status": dict(sorted(counts.items())),
        "classification_count_by_category": dict(sorted(categories.items())),
        "source_total": len(outcomes),
        "accounted_total": len(outcomes),
        "failed_outcome_count": sum(counts[name] for name in ("FAILED", "SUBFAILED", "ERROR", "XPASS")),
        "quiet_progress_node_identity_limitation": {
            "affected_outcomes": counts["PASSED"] + counts["SKIPPED"],
            "node_identity_available": False,
            "event_identity_authority": "EXACT_SOURCE_BYTE_RANGE",
        },
    }
    return record


def validate_historical_record(record: Mapping[str, Any], data: bytes, log_path: str) -> None:
    expected = parse_historical_log(data, log_path)
    if record != expected:
        raise HistoricalLogError("HISTORICAL_RECORD_MISMATCH")
    for outcome in record["outcomes"]:
        location = outcome["source_log_location"]
        start, end = location["byte_start"], location["byte_end"]
        if not (0 <= start < end <= len(data)):
            raise HistoricalLogError("SOURCE_LOCATION_RANGE", outcome["identity"])
        source = data[start:end]
        token = {".": "PASSED", "F": "FAILED", "s": "SKIPPED"}
        if outcome["outcome"] in {"PASSED", "FAILED", "SKIPPED"} and token.get(source.decode("ascii")) != outcome["outcome"]:
            raise HistoricalLogError("SOURCE_LOCATION_OUTCOME", outcome["identity"])
        if outcome["outcome"] == "SUBFAILED" and not source.startswith(b"SUBFAILED("):
            raise HistoricalLogError("SOURCE_LOCATION_OUTCOME", outcome["identity"])


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--logical-path", required=True)
    args = parser.parse_args()
    data = args.log.read_bytes()
    print(canonical_bytes(parse_historical_log(data, args.logical_path)).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
