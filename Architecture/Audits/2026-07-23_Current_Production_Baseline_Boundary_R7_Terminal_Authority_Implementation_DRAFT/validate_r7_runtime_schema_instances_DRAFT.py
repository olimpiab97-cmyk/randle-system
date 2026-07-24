#!/usr/bin/env python3
"""Validate fixed-root governed runtime receipts and their primary evidence graph."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
from verify_r7_terminal_authority_package_DRAFT import read_json, validate_schema


ROOTS = {
    "evidence": Path(r"C:\ProgramData\RandleAI\TerminalAuthority\Evidence"),
    "terminal": Path(r"C:\ProgramData\RandleAI\TerminalAuthority\Receipts"),
    "reconciliation": Path(r"C:\ProgramData\RandleAI\TerminalAuthority\Reconciliations"),
}
LOCATOR = re.compile(r"^randle-(evidence|terminal|reconciliation)://sha256/([0-9a-f]{64})$")
PACKAGE = Path(__file__).resolve().parent


def require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def load_locator(locator: str) -> tuple[dict[str, Any], str]:
    match = LOCATOR.fullmatch(locator)
    require(match is not None, f"LOCATOR_SHAPE:{locator}")
    kind, identity = match.groups()
    path = ROOTS[kind] / f"{identity}.json"
    require(path.is_file(), f"LOCATOR_UNRESOLVED:{locator}")
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == identity, f"LOCATOR_CONTENT_ADDRESS:{locator}")
    value = json.loads(data.decode("utf-8"))
    require(isinstance(value, dict), f"LOCATOR_OBJECT:{locator}")
    return value, kind


def validate(value: dict[str, Any], schema: dict[str, Any]) -> None:
    validate_schema(value, schema, schema)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--terminal-locator", action="append", default=[])
    parser.add_argument("--reconciliation-locator", action="append", default=[])
    args = parser.parse_args()
    require(args.terminal_locator or args.reconciliation_locator, "NO_LOCATORS")

    terminal_schema = read_json(PACKAGE / "signed_terminal_receipt_R7_schema_DRAFT.json")
    reconciliation_schema = read_json(PACKAGE / "signed_reconciliation_receipt_R7_schema_DRAFT.json")
    evidence_schema = read_json(PACKAGE / "terminal_authority_evidence_schema_package_R7_DRAFT.json")
    validated: set[str] = set()
    kinds: Counter[str] = Counter()

    def validate_evidence(locator: str) -> dict[str, Any]:
        if locator in validated:
            return load_locator(locator)[0]
        value, kind = load_locator(locator)
        require(kind == "evidence", f"EXPECTED_EVIDENCE:{locator}")
        validate(value, evidence_schema)
        validated.add(locator)
        payload = value.get("payload", value)
        artifact_type = payload.get("artifact_type", "UNKNOWN") if isinstance(payload, dict) else "UNKNOWN"
        kinds[artifact_type] += 1
        return value

    def validate_terminal(locator: str) -> dict[str, Any]:
        if locator in validated:
            return load_locator(locator)[0]
        envelope, kind = load_locator(locator)
        require(kind == "terminal", f"EXPECTED_TERMINAL:{locator}")
        validate(envelope, terminal_schema)
        validated.add(locator)
        kinds["R7_SIGNED_TERMINAL_RECEIPT"] += 1
        payload = envelope["payload"]
        for key in ("event_source_locator", "observation_locator", "comparator_result_locator", "process_index_locator", "traceability_locator"):
            validate_evidence(payload[key])
        suite = validate_evidence(payload["suite_process_receipt_locator"])
        suite_payload = suite["payload"]
        validate_evidence(suite_payload["launch_receipt_locator"])
        raw_index = validate_evidence(suite_payload["raw_case_index_locator"])
        for case in raw_index["cases"]:
            fixture_locator = case["fixture_process_receipt_locator"]
            snapshot_locator = case["fixture_reparse_snapshot_locator"]
            if fixture_locator:
                validate_evidence(fixture_locator)
                validate_evidence(snapshot_locator)
        process_index, _ = load_locator(payload["process_index_locator"])
        for key in ("suite_process_receipt_locator", "observation_process_receipt_locator", "comparator_process_receipt_locator"):
            validate_evidence(process_index[key])
        return envelope

    for locator in args.terminal_locator:
        validate_terminal(locator)

    for locator in args.reconciliation_locator:
        envelope, kind = load_locator(locator)
        require(kind == "reconciliation", f"EXPECTED_RECONCILIATION:{locator}")
        validate(envelope, reconciliation_schema)
        validated.add(locator)
        kinds["R7_SIGNED_EXTERNAL_RECONCILIATION_RECEIPT"] += 1
        payload = envelope["payload"]
        validate_terminal(payload["candidate_receipt_locator"])
        validate_terminal(payload["fresh_receipt_locator"])
        validate_evidence(payload["reconciliation_evaluator_result_locator"])
        validate_evidence(payload["reconciliation_process_receipt_locator"])

    result = {
        "artifact_type": "R7_RUNTIME_SCHEMA_INSTANCE_VALIDATION",
        "object_count": len(validated),
        "object_types": dict(sorted(kinds.items())),
        "schema_version": "7.1.0-DRAFT",
        "status": "PASS_NOT_ACCEPTANCE",
    }
    sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        sys.stderr.write(type(exc).__name__ + ": " + str(exc) + "\n")
        raise SystemExit(1)
