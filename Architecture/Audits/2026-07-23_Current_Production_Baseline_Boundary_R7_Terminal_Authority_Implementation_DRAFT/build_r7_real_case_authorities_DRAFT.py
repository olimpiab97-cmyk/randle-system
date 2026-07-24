#!/usr/bin/env python3
"""Freeze the pre-execution R7 real-interface and expectation authorities.

The discarded R7 implementation commit is used only as a content-addressed
source of the direct-interface case mapping.  Its runner, client, receipts,
results, and terminal decisions are never authority.  The mapping is accepted
only after this builder independently checks its cardinality, closed interface
set, real-surface classification, R6/R7 requirement coverage, and its separate
pre-execution expectation source.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
from collections import Counter
from typing import Any


R6_COMMIT = "87d066eb16d7fe0b6a1677ea7739c5c2ead4ad94"
R6_TREE = "f9891562ea09d011d4d9803d9cf64b88ff1f2dbf"
R6_SPEC_BLOB = "343622743668d7ddc524513307e726f20d1db9fc"
R6_SPEC_PATH = "Architecture/15_Randle_AI_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT.md"
R7_INCOMPLETE_COMMIT = "06c6805ed52a0d539a73088c097c60dec335462a"
R7_INCOMPLETE_BLOB = "1be3b0b5f15ac8e68b88202e0e9d3787b69d1856"
R7_INCOMPLETE_PATH = "Architecture/Audits/2026-07-22_Current_Production_Baseline_Boundary_R7_Remediation_87d066e_INCOMPLETE.md"
R7_BLOCKED_COMMIT = "8ec5697b3c6fd9d93b972113b7e79d033b4cb1f6"
R7_BLOCKED_BLOB = "dfa98a89049b9596387143c002252d91d608fbfc"
R7_BLOCKED_PATH = "Architecture/Audits/2026-07-23_Current_Production_Baseline_Boundary_R7_Continuation_87d066e_TASK_BLOCKED.md"
PROVISIONING_COMMIT = "bb04ac54fb328516d0c785f4e6551e6a20d73759"
PROVISIONING_REPORT_BLOB = "795c9a25ab70188625ff8cede82274b073cb0d3b"
PROVISIONING_REPORT_PATH = "Architecture/Audits/2026-07-23_Terminal_Authority_Infrastructure_Provisioning_DRAFT/TERMINAL_AUTHORITY_PROVISIONING_REPORT_DRAFT.md"

# Nonauthoritative diagnostic source objects.  Only the independently checked
# case/interface mapping and expectation rows are reused; no result is reused.
SUBJECT_COMMIT = "f0cfbce97e913a133530dd66a70326b1e03a0fb6"
SUBJECT_PARENT = R6_COMMIT
SUBJECT_TREE = "02324c2b2dc3415fa2dbe21144e12ab667bf40d9"
SUBJECT_CASE_BLOB = "e7919987dc0518f6eb5978bb9bf57989898a2c51"
SUBJECT_CASE_SHA256 = "29bd816d73ff6a4f40214817d97aae7448eea686e0ff1671d5bb7b7752236182"
SUBJECT_EXPECTATION_BLOB = "da11fc852e63e7f30a6265d04d8978d93aa359fd"
SUBJECT_EXPECTATION_SHA256 = "75c46f73efcf4cdcd5519cc6b0918457bf9bd3aaba9910e43a33a7b4c3c16cd9"
SUBJECT_DIRECT_BLOB = "3420572d96a65ffb8feb708657fdfa95eb1e08a4"
SUBJECT_SERVICE_BLOB = "cc6099f244fae8d052927b3abddddd702c09b505"
SUBJECT_VERIFIER_BLOB = "05a0dedbd024a90a9e93bd464ca360a84741a582"
SUBJECT_LAUNCHER_SHA256 = "3445e5effd6398b648afa6898391f4e2b5de34f696dd91bfedc2dc29be4e3877"
FIXTURE_HOST_SHA256 = "7a82bab5acfa36555d0e3b9cf29084101f8276b4ceba93cd48cc1e85fadf1454"

PACKAGE = pathlib.Path(__file__).resolve().parent
WORKTREE = PACKAGE.parents[2]
CORRECTION_PATH = PACKAGE / "R7I_B01_CORRECTION_REQUIREMENTS_DRAFT.md"
CASE_OUTPUT = PACKAGE / "r7_real_case_definitions_DRAFT.json"
EXPECTATION_OUTPUT = PACKAGE / "r7_independent_expectations_DRAFT.json"
PROBE_OUTPUT = PACKAGE / "r7i_b01_adversarial_probes_DRAFT.json"

INTERFACE_SYMBOLS = {
    "access_capability": "enforce_access_capability",
    "external_issuance": "enforce_external_issuance",
    "external_launch": "enforce_external_launch",
    "durable_ledger": "enforce_durable_ledger",
    "recorder_session": "enforce_recorder_session",
    "observation_evidence": "enforce_observation_evidence",
    "immutable_dispatch": "enforce_immutable_dispatch",
    "internal_repository": "enforce_internal_repository",
    "complete_trace": "enforce_complete_trace",
    "review_resolution": "enforce_review_resolution",
    "compatibility_resolution": "enforce_compatibility_resolution",
    "physical_filename": "enforce_physical_filename",
    "closed_authorization": "enforce_closed_authorization",
    "retained_controls": "enforce_retained_controls",
    "real_classification": "enforce_real_classification",
}

PROBES = [
    ("R7I-B01-A01", "predetermined PASS events without interface invocation"),
    ("R7I-B01-A02", "policy identities echoed as enforcement results"),
    ("R7I-B01-A03", "expectations copied into observations"),
    ("R7I-B01-A04", "constructed expected and observed OK values"),
    ("R7I-B01-A05", "zero discrepancies without case definitions"),
    ("R7I-B01-A06", "unresolved case-set identity"),
    ("R7I-B01-A07", "case bytes changed after identity calculation"),
    ("R7I-B01-A08", "caller-selected alternate case definitions"),
    ("R7I-B01-A09", "caller-selected alternate expectations"),
    ("R7I-B01-A10", "required case skipped"),
    ("R7I-B01-A11", "case duplicated"),
    ("R7I-B01-A12", "unknown extra case inserted"),
    ("R7I-B01-A13", "prior-run event evidence reused"),
    ("R7I-B01-A14", "prior-run process receipt reused"),
    ("R7I-B01-A15", "request or response evidence fabricated"),
    ("R7I-B01-A16", "process receipt without public-interface invocation"),
    ("R7I-B01-A17", "wrong binary or caller invokes interface"),
    ("R7I-B01-A18", "rejection accompanied by unauthorized authority append"),
    ("R7I-B01-A19", "success response without durable terminal append"),
    ("R7I-B01-A20", "candidate and fresh runs share synthetic evidence"),
    ("R7I-B01-A21", "two synthetic receipts reconcile structurally"),
    ("R7I-B01-A22", "trace row points to an event that did not occur"),
    ("R7I-B01-A23", "valid signature covers unresolved child evidence"),
    ("R7I-B01-A24", "valid receipt detached from authoritative ledger"),
    ("R7I-B01-A25", "copied internally consistent evidence root substituted"),
]


def git_bytes(object_id: str) -> bytes:
    return subprocess.run(
        ["git", "-c", f"safe.directory={WORKTREE.as_posix()}", "cat-file", "blob", object_id],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def load_bound_json(blob: str, expected_sha256: str) -> dict[str, Any]:
    raw = git_bytes(blob)
    if git_blob_id(raw) != blob or sha256(raw) != expected_sha256:
        raise RuntimeError(f"immutable diagnostic source mismatch: {blob}")
    return json.loads(raw.decode("utf-8", "strict"))


def validate_sources(cases: list[dict[str, Any]], expectations: list[dict[str, Any]]) -> None:
    if len(cases) != 178 or Counter(row["kind"] for row in cases) != {"positive": 20, "mutation": 158}:
        raise RuntimeError("R7 record-derived 20/158 cardinality mismatch")
    if any(row["surface"] != "real_surface" or row["vector_handler"] is not False for row in cases):
        raise RuntimeError("non-real or vector-handler case in diagnostic mapping")
    if set(row["public_interface"] for row in cases) != set(INTERFACE_SYMBOLS):
        raise RuntimeError("closed direct-interface set mismatch")
    required = {f"R7-{index:02d}" for index in range(1, 16)}
    if set(row["r7_requirement"] for row in cases) != required:
        raise RuntimeError("R7 requirement coverage mismatch")
    ids = [row["case_id"] for row in cases]
    if len(set(ids)) != len(ids):
        raise RuntimeError("duplicate case identity")
    by_id = {row["case_id"]: row for row in expectations}
    if set(by_id) != set(ids) or len(expectations) != len(ids):
        raise RuntimeError("independent expectation set mismatch")
    for row in cases:
        expected = by_id[row["case_id"]]
        if expected["expected_enforcing_function"] != INTERFACE_SYMBOLS[row["public_interface"]]:
            raise RuntimeError(f"enforcing function mismatch: {row['case_id']}")
        desired = "ACCEPTED" if row["kind"] == "positive" else "REJECTED"
        if expected["expected_status"] != desired:
            raise RuntimeError(f"expectation polarity mismatch: {row['case_id']}")
        if desired == "ACCEPTED" and expected["expected_code"] != "OK":
            raise RuntimeError(f"positive response mismatch: {row['case_id']}")


def build() -> tuple[bytes, bytes, bytes]:
    source_cases = load_bound_json(SUBJECT_CASE_BLOB, SUBJECT_CASE_SHA256)["cases"]
    source_expectations = load_bound_json(SUBJECT_EXPECTATION_BLOB, SUBJECT_EXPECTATION_SHA256)["cases"]
    validate_sources(source_cases, source_expectations)
    expected_by_id = {row["case_id"]: row for row in source_expectations}
    correction_bytes = CORRECTION_PATH.read_bytes()
    correction_blob = git_blob_id(correction_bytes)
    correction_sha = sha256(correction_bytes)

    cases: list[dict[str, Any]] = []
    expectations: list[dict[str, Any]] = []
    for source in source_cases:
        expected = expected_by_id[source["case_id"]]
        case_id = source["case_id"]
        requirement = source["r7_requirement"]
        interface = source["public_interface"]
        fixture_required = source["mutation"].startswith("reparse_substitution_")
        required_raw_evidence = [
            "exact canonical execute_case request bytes",
            "exact canonical subject response bytes",
            "measured launcher receipt and subject READY response",
            "subject stderr bytes",
            "signed outer suite process receipt",
            "launcher and subject PID, parent, start/end/exit, inherited token SID set, launcher, Python, and source identities",
            "outer pre/post ledger sequence and root",
            "inner case token, execution receipt, recorder event, and subject ledger evidence",
        ]
        required_side_effects = ["CURRENT_SUBJECT_RECORDER_EVENT", "CURRENT_SUBJECT_EVENT_LEDGER_APPEND"]
        if fixture_required:
            required_raw_evidence.append("current-run measured junction-fixture process receipt resolving helper binary/file identity, PID/parent PID, inherited restricted token, exact command hash, NTFS reparse tag, and case exchange time window")
            required_side_effects.append("CURRENT_MEASURED_NTFS_JUNCTION_FIXTURE")
        prerequisites = [
            "pinned case and expectation bytes resolve",
            "fixed subject commit and source blobs resolve",
            "fresh measured subject service and recorder are running",
            "outer authority identities and ledger verify",
        ]
        if fixture_required:
            prerequisites.append("fixed measured junction-fixture host resolves and the current-run fixture receipt directory is initially empty")
        forward = [requirement, source["normative_clause"], case_id, interface, "CURRENT_REQUEST_RESPONSE"]
        if fixture_required:
            forward.append("CURRENT_MEASURED_NTFS_JUNCTION_FIXTURE")
        forward.extend(["CURRENT_EVENT", "DERIVED_OBSERVATION", "INDEPENDENT_COMPARATOR", "TERMINAL_VERIFIER"])
        cases.append({
            "caller_class": "RESTRICTED_TERMINAL_AUTHORITY_SERVICE_CHILD",
            "caller_identity_rule": "subject process inherits the restricted service token; OS token evidence must resolve to the fixed service SID and nonadministrator state",
            "case_id": case_id,
            "comparator_rule": "independently resolve immutable authorities, exact request and response bytes, OS process receipt, inner recorder event, outer ledger boundaries, observation citations, and bidirectional trace before comparing outcome and code",
            "expected_acceptance": expected["expected_status"],
            "expected_ledger_delta": {"outer_authority_entries_during_case": 0, "subject_event_entries_at_least": 1},
            "expected_receipt_behavior": "the case cites the single current suite process receipt and its own unique request, response, case token, execution receipt, and recorder event; no case may issue a terminal receipt",
            "expected_response_semantics": {"classification": expected["expected_code"], "outcome": expected["expected_status"]},
            "expected_restart_retry_replay_behavior": "a retry requires a distinct suite process, run, process nonce, subject run, one-shot case token, request bytes, response bytes, recorder event, and process receipt",
            "forbidden_side_effects": ["OUTER_SUBJECT_AUTHORITY_APPEND", "PER_CASE_TERMINAL_RECEIPT", "PER_CASE_RECONCILIATION_RECEIPT", "CALLER_AUTHORED_RESULT"],
            "governing_authorities": [
                {"commit": R6_COMMIT, "git_blob": R6_SPEC_BLOB, "path": R6_SPEC_PATH, "requirement_id": requirement},
                {"commit": R7_INCOMPLETE_COMMIT, "git_blob": R7_INCOMPLETE_BLOB, "path": R7_INCOMPLETE_PATH, "requirement_id": "R7-B01/R7-B02"},
                {"commit": R7_BLOCKED_COMMIT, "git_blob": R7_BLOCKED_BLOB, "path": R7_BLOCKED_PATH, "requirement_id": "R7-EXTERNAL-TRUST"},
                {"commit": PROVISIONING_COMMIT, "git_blob": PROVISIONING_REPORT_BLOB, "path": PROVISIONING_REPORT_PATH, "requirement_id": "TERMINAL-AUTHORITY-PROVISIONING"},
                {"git_blob": correction_blob, "git_object_type": "blob", "path": CORRECTION_PATH.name, "requirement_id": "R7I-B01"},
            ],
            "governing_requirement_id": requirement,
            "initial_state": "fresh externally issued and consumed subject run, fresh recorder, current parser receipt, fixed outer ledger checkpoint, no case event yet",
            "input_construction_rule": f"PINNED_R7_DIRECT_CASE/{case_id}/{source['mutation_identity']}",
            "operation": "execute_case",
            "prerequisites": prerequisites,
            "public_interface": interface,
            "required_authoritative_side_effects": required_side_effects,
            "required_execution_isolation": "one fresh measured subject service per terminal run, fixed executable/script/repository identities, sanitized environment, one-shot per-case token, a measured closed fixture host only where explicitly required, and no caller-selected source or path",
            "required_observation_derivation": "derive status, code, enforcing function, service PID, token identity, execution receipt, recorder event, request and response identities, and outer ledger delta only from cited current evidence",
            "required_raw_evidence": required_raw_evidence,
            "source_case": source,
            "subject_component": {"authority": "NONAUTHORITATIVE_MEASURED_EXECUTION_SUBJECT", "commit": SUBJECT_COMMIT, "direct_interface_git_blob": SUBJECT_DIRECT_BLOB, "fixture_host_sha256": FIXTURE_HOST_SHA256, "launcher_binary_sha256": SUBJECT_LAUNCHER_SHA256, "service_git_blob": SUBJECT_SERVICE_BLOB, "verifier_git_blob": SUBJECT_VERIFIER_BLOB},
            "traceability_mapping": {"forward": forward, "reverse_required": True},
        })
        expectations.append({
            "case_id": case_id,
            "expected_authority_source": expected["expected_authority"],
            "expected_enforcing_function": expected["expected_enforcing_function"],
            "expected_evidence_obligation": expected["expected_evidence_obligation"],
            "expected_interface": interface,
            "expected_ledger_delta": {"outer_authority_entries_during_case": 0, "subject_event_entries_at_least": 1},
            "expected_outcome": expected["expected_status"],
            "expected_response_classification": expected["expected_code"],
            "forbidden_outcomes": ["UNRESOLVED_EVIDENCE", "PRIOR_RUN_EVIDENCE", "CALLER_RESULT_AUTHORITY", "SYNTHETIC_EXECUTION"],
            "forbidden_side_effects": cases[-1]["forbidden_side_effects"],
            "governing_expectation": {"diagnostic_source_git_blob": SUBJECT_EXPECTATION_BLOB, "normative_clause": source["normative_clause"], "r7_requirement": requirement},
            "provenance": "PRE_EXECUTION_INDEPENDENT_STATIC_EXPECTATION_NO_EVENT_OBSERVATION_RECEIPT_OR_COMPARATOR_INPUT",
            "required_evidence": cases[-1]["required_raw_evidence"],
            "required_side_effects": cases[-1]["required_authoritative_side_effects"],
        })

    sources = {
        "correction_requirements_git_blob": correction_blob,
        "correction_requirements_sha256": correction_sha,
        "provisioning_commit": PROVISIONING_COMMIT,
        "r6_commit": R6_COMMIT,
        "r6_tree": R6_TREE,
        "r7_blocked_commit": R7_BLOCKED_COMMIT,
        "r7_blocked_report_git_blob": R7_BLOCKED_BLOB,
        "r7_incomplete_commit": R7_INCOMPLETE_COMMIT,
        "r7_incomplete_report_git_blob": R7_INCOMPLETE_BLOB,
        "subject_case_git_blob": SUBJECT_CASE_BLOB,
        "subject_commit": SUBJECT_COMMIT,
        "subject_parent": SUBJECT_PARENT,
        "subject_tree": SUBJECT_TREE,
    }
    case_authority = {"artifact_type": "R7_REAL_PUBLIC_INTERFACE_CASE_DEFINITIONS", "authority_model": "178_REQUIREMENT_DERIVED_DIRECT_PUBLIC_INTERFACE_CASES", "case_count": len(cases), "cases": cases, "governing_sources": sources, "schema_version": "7.1.0-DRAFT"}
    expectation_authority = {"artifact_type": "R7_INDEPENDENT_EXPECTATIONS", "authoring_authority": "PRE_EXECUTION_GOVERNING_REQUIREMENT_DERIVATION", "case_count": len(expectations), "expectations": expectations, "provenance_policy": "NO_EXECUTION_EVENT_OBSERVATION_RECEIPT_COMPARATOR_OR_PRIOR_RESULT_INPUT", "schema_version": "7.1.0-DRAFT", "source_authorities": sources}
    probe_authority = {"artifact_type": "R7I_B01_ADVERSARIAL_PROBE_DEFINITIONS", "governing_requirement": "R7I-B01", "probe_count": len(PROBES), "probes": [{"attack": text, "expected_terminal_behavior": "REJECT_BEFORE_TERMINAL_OR_RECONCILIATION_AUTHORITY", "probe_id": probe_id, "required_evidence": "current isolated mutation result and absence of unauthorized outer ledger append"} for probe_id, text in PROBES], "schema_version": "7.1.0-DRAFT"}
    return canonical(case_authority), canonical(expectation_authority), canonical(probe_authority)


def main() -> int:
    case_bytes, expectation_bytes, probe_bytes = build()
    CASE_OUTPUT.write_bytes(case_bytes)
    EXPECTATION_OUTPUT.write_bytes(expectation_bytes)
    PROBE_OUTPUT.write_bytes(probe_bytes)
    print(json.dumps({
        "case_bytes": len(case_bytes), "case_count": 178, "case_git_blob": git_blob_id(case_bytes), "case_sha256": sha256(case_bytes),
        "expectation_bytes": len(expectation_bytes), "expectation_git_blob": git_blob_id(expectation_bytes), "expectation_sha256": sha256(expectation_bytes),
        "probe_bytes": len(probe_bytes), "probe_count": 25, "probe_git_blob": git_blob_id(probe_bytes), "probe_sha256": sha256(probe_bytes),
        "status": "BUILT_PRE_EXECUTION_AUTHORITIES",
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
