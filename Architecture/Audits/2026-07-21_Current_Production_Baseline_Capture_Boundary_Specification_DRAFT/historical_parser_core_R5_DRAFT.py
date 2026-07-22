#!/usr/bin/env python3
"""Standalone measured parser core for the bound 2026-07-20 pytest log."""

from __future__ import annotations

import ast
import hashlib
import re
from collections import Counter
from typing import Any


PARSER_INTERFACE_VERSION = "RANDLE-R5-HISTORICAL-PARSER-1"
PARSER_VERSION = "5.0.0-DRAFT"
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
        match_text = FAILED_RE.fullmatch(text)
        if match_text:
            failed.append({"node": match_text.group("node"), "line": line_number, "byte_start": start, "byte_end": end})
            continue
        match_text = SUBFAILED_RE.fullmatch(text)
        if match_text:
            name = ast.literal_eval(match_text.group("name"))
            if type(name) is not str:
                raise ValueError("SUBFAILED_NAME")
            subfailed.append({"name": name, "parent": match_text.group("parent"), "line": line_number, "byte_start": start, "byte_end": end})
            continue
        match_text = SUMMARY_RE.match(text)
        if match_text:
            terminal = match_text.groupdict()
    if offset != len(data) or terminal is None:
        raise ValueError("LOG_ACCOUNTING")
    token_counts = Counter(item["token"] for item in progress)
    if dict(token_counts) != {".": 571, "F": 156, "s": 3}:
        raise ValueError("PROGRESS_EVENT_COUNT")
    if len(failed) != 156 or len(subfailed) != 23:
        raise ValueError("NAMED_OUTCOME_COUNT")
    if (int(terminal["failed"]), int(terminal["passed"]), int(terminal["skipped"])) != (179, 571, 3):
        raise ValueError("TERMINAL_SUMMARY_COUNT")
    outcomes: list[dict[str, Any]] = []
    failed_index = 0
    for ordinal, item in enumerate(progress, 1):
        status = {".": "PASSED", "F": "FAILED", "s": "SKIPPED"}[item["token"]]
        node = failed[failed_index]["node"] if status == "FAILED" else None
        if status == "FAILED":
            failed_index += 1
        outcomes.append({"event_identity": f"PROGRESS::{ordinal:04d}", "outcome": status, "node_identity": node, "source_location": {key: item[key] for key in ("line", "column", "byte_start", "byte_end")}})
    for item in subfailed:
        outcomes.append({"event_identity": f"SUBFAILED::{item['byte_start']:08d}", "outcome": "SUBFAILED", "node_identity": f"{item['parent']}::SUBFAILED[{item['name']}]", "source_location": {"line": item["line"], "column": 1, "byte_start": item["byte_start"], "byte_end": item["byte_end"]}})
    counts = Counter(item["outcome"] for item in outcomes)
    for status in ("PASSED", "FAILED", "SUBFAILED", "SKIPPED", "ERROR", "XFAIL", "XPASS"):
        counts.setdefault(status, 0)
    return {
        "schema_version": "7.0.0-DRAFT",
        "parser_interface_version": PARSER_INTERFACE_VERSION,
        "parser_version": PARSER_VERSION,
        "logical_evidence_id": logical_path,
        "full_log_size": len(data),
        "full_log_sha256": observed_hash,
        "outcome_count_by_status": dict(sorted(counts.items())),
        "source_total": len(outcomes),
        "failed_outcome_count": counts["FAILED"] + counts["SUBFAILED"] + counts["ERROR"],
        "outcomes": outcomes,
    }
