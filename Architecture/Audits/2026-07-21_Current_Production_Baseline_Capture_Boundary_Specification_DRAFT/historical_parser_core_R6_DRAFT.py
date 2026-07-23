#!/usr/bin/env python3
"""Measured R6 parser core for the immutable 2026-07-20 pytest log."""

from __future__ import annotations

import ast
import hashlib
import re
from collections import Counter
from typing import Any


PARSER_INTERFACE_VERSION = "RANDLE-R6-HISTORICAL-PARSER-1"
PARSER_VERSION = "6.0.0-DRAFT"
PROGRESS_RE = re.compile(rb"^(?P<events>[.FEsxX]+)(?:\s+\[\s*\d+%\])?\r?\n?$")
FAILED_RE = re.compile(r"^FAILED (?P<node>\S+)$")
SUBFAILED_RE = re.compile(r"^SUBFAILED\(name=(?P<name>.+)\) (?P<parent>\S+)$")
SUMMARY_RE = re.compile(r"^(?P<failed>\d+) failed, (?P<passed>\d+) passed, (?P<skipped>\d+) skipped, (?P<subtests>\d+) subtests passed ")


def parse_historical_log(data: bytes, logical_path: str, expected_sha256: str) -> dict[str, Any]:
    observed_hash = hashlib.sha256(data).hexdigest().upper()
    if observed_hash != expected_sha256:
        raise ValueError("BROAD_LOG_HASH")
    progress: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    subfailed: list[dict[str, Any]] = []
    terminal: dict[str, str] | None = None
    offset = 0
    for line_number, raw in enumerate(data.splitlines(keepends=True), 1):
        start, end = offset, offset + len(raw)
        offset = end
        text = raw.decode("utf-8", "strict").rstrip("\r\n")
        match = PROGRESS_RE.fullmatch(raw)
        if match:
            for column, token in enumerate(match.group("events"), 1):
                progress.append({"token": chr(token), "line": line_number, "column": column, "byte_start": start + column - 1, "byte_end": start + column})
            continue
        named = FAILED_RE.fullmatch(text)
        if named:
            failed.append({"node": named.group("node"), "line": line_number, "byte_start": start, "byte_end": end})
            continue
        sub = SUBFAILED_RE.fullmatch(text)
        if sub:
            name = ast.literal_eval(sub.group("name"))
            if type(name) is not str:
                raise ValueError("SUBFAILED_NAME")
            subfailed.append({"name": name, "parent": sub.group("parent"), "line": line_number, "byte_start": start, "byte_end": end})
            continue
        summary = SUMMARY_RE.match(text)
        if summary:
            terminal = summary.groupdict()
    if offset != len(data) or terminal is None:
        raise ValueError("LOG_ACCOUNTING")
    token_counts = Counter(item["token"] for item in progress)
    if dict(token_counts) != {".": 571, "F": 156, "s": 3}:
        raise ValueError("PROGRESS_EVENT_COUNT")
    if len(failed) != 156 or len(subfailed) != 23:
        raise ValueError("NAMED_OUTCOME_COUNT")
    if (int(terminal["failed"]), int(terminal["passed"]), int(terminal["skipped"])) != (179, 571, 3):
        raise ValueError("TERMINAL_SUMMARY_COUNT")
    locations = {
        "first_progress": progress[0], "last_progress": progress[-1],
        "first_failed": failed[0], "last_failed": failed[-1],
        "first_subfailed": subfailed[0], "last_subfailed": subfailed[-1],
    }
    return {
        "schema_version": "6.0.0-DRAFT",
        "parser_interface_version": PARSER_INTERFACE_VERSION,
        "parser_version": PARSER_VERSION,
        "logical_evidence_id": logical_path,
        "full_log_size": len(data),
        "full_log_sha256": observed_hash,
        "outcome_count_by_status": {"ERROR": 0, "FAILED": 156, "PASSED": 571, "SKIPPED": 3, "SUBFAILED": 23, "XFAIL": 0, "XPASS": 0},
        "source_total": 753,
        "failed_outcome_count": 179,
        "source_location_evidence": locations,
    }

