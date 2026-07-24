#!/usr/bin/env python3
"""Generate closed JSON Schemas for the corrected R7 authority package."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SCHEMA = "https://json-schema.org/draft/2020-12/schema"
VERSION = "7.1.0-DRAFT"
SHA = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
GIT = {"type": "string", "pattern": "^[0-9a-f]{40}$"}
TIME = {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\\.[0-9]{7}Z$"}
SID = {"type": "string", "pattern": "^S-[0-9]+(?:-[0-9]+)+$"}
NONEMPTY = {"type": "string", "minLength": 1}
EVIDENCE_LOCATOR = {"type": "string", "pattern": "^randle-evidence://sha256/[0-9a-f]{64}$"}
TERMINAL_LOCATOR = {"type": "string", "pattern": "^randle-terminal://sha256/[0-9a-f]{64}$"}
RECONCILIATION_LOCATOR = {"type": "string", "pattern": "^randle-reconciliation://sha256/[0-9a-f]{64}$"}
OPTIONAL_EVIDENCE_LOCATOR = {"type": "string", "pattern": "^(?:|randle-evidence://sha256/[0-9a-f]{64})$"}
STRING_ARRAY = {"type": "array", "minItems": 1, "items": NONEMPTY}


def closed(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required if required is not None else list(properties),
        "properties": properties,
    }


def document(identifier: str, body: dict[str, Any], title: str) -> dict[str, Any]:
    return {"$schema": SCHEMA, "$id": f"https://randle.ai/schemas/{identifier}-7.1.0-draft.json", "title": title} | body


def write(name: str, value: dict[str, Any]) -> None:
    (ROOT / name).write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))


authority_properties = {
    "correction_requirements_git_blob": GIT,
    "correction_requirements_sha256": SHA,
    "provisioning_commit": GIT,
    "r6_commit": GIT,
    "r6_tree": GIT,
    "r7_blocked_commit": GIT,
    "r7_blocked_report_git_blob": GIT,
    "r7_incomplete_commit": GIT,
    "r7_incomplete_report_git_blob": GIT,
    "subject_case_git_blob": GIT,
    "subject_commit": GIT,
    "subject_parent": GIT,
    "subject_tree": GIT,
}
authority_source = closed(authority_properties)

governing_authority = closed(
    {
        "commit": GIT,
        "git_blob": GIT,
        "git_object_type": {"const": "blob"},
        "path": NONEMPTY,
        "requirement_id": NONEMPTY,
    },
    ["git_blob", "path", "requirement_id"],
)
source_case = closed({
    "case_id": {"type": "string", "pattern": "^R7-[0-9]{2}-(?:P|M)[0-9]{3}$"},
    "expected_authority_source": SHA,
    "expected_evidence_obligation": SHA,
    "immutable_input_identity": SHA,
    "kind": {"enum": ["positive", "mutation"]},
    "meta_verification": {"type": "boolean"},
    "mutation": NONEMPTY,
    "mutation_identity": SHA,
    "normative_clause": {"type": "string", "pattern": "^CPB-R7-[0-9]{2}$"},
    "public_interface": NONEMPTY,
    "r7_requirement": {"type": "string", "pattern": "^R7-[0-9]{2}$"},
    "surface": {"const": "real_surface"},
    "vector_handler": {"type": "boolean"},
})
subject_component = closed({
    "authority": {"const": "NONAUTHORITATIVE_MEASURED_EXECUTION_SUBJECT"},
    "commit": GIT,
    "direct_interface_git_blob": GIT,
    "fixture_host_sha256": SHA,
    "launcher_binary_sha256": SHA,
    "service_git_blob": GIT,
    "verifier_git_blob": GIT,
})
ledger_delta = closed({
    "outer_authority_entries_during_case": {"type": "integer", "minimum": 0},
    "subject_event_entries_at_least": {"type": "integer", "minimum": 1},
})
case_schema = closed({
    "caller_class": NONEMPTY,
    "caller_identity_rule": NONEMPTY,
    "case_id": {"type": "string", "pattern": "^R7-[0-9]{2}-(?:P|M)[0-9]{3}$"},
    "comparator_rule": NONEMPTY,
    "expected_acceptance": {"enum": ["ACCEPTED", "REJECTED"]},
    "expected_ledger_delta": ledger_delta,
    "expected_receipt_behavior": NONEMPTY,
    "expected_response_semantics": closed({"classification": NONEMPTY, "outcome": {"enum": ["ACCEPTED", "REJECTED"]}}),
    "expected_restart_retry_replay_behavior": NONEMPTY,
    "forbidden_side_effects": STRING_ARRAY,
    "governing_authorities": {"type": "array", "minItems": 5, "items": governing_authority},
    "governing_requirement_id": {"type": "string", "pattern": "^R7-[0-9]{2}$"},
    "initial_state": NONEMPTY,
    "input_construction_rule": NONEMPTY,
    "operation": {"const": "execute_case"},
    "prerequisites": STRING_ARRAY,
    "public_interface": NONEMPTY,
    "required_authoritative_side_effects": STRING_ARRAY,
    "required_execution_isolation": NONEMPTY,
    "required_observation_derivation": NONEMPTY,
    "required_raw_evidence": STRING_ARRAY,
    "source_case": source_case,
    "subject_component": subject_component,
    "traceability_mapping": closed({"forward": STRING_ARRAY, "reverse_required": {"const": True}}),
})
case_document = document("r7-real-case-definitions", closed({
    "artifact_type": {"const": "R7_REAL_PUBLIC_INTERFACE_CASE_DEFINITIONS"},
    "authority_model": {"const": "178_REQUIREMENT_DERIVED_DIRECT_PUBLIC_INTERFACE_CASES"},
    "case_count": {"const": 178},
    "cases": {"type": "array", "minItems": 178, "maxItems": 178, "items": case_schema},
    "governing_sources": authority_source,
    "schema_version": {"const": VERSION},
}), "R7 immutable real public-interface case definitions")
write("r7_real_case_definitions_schema_DRAFT.json", case_document)

expectation_schema = closed({
    "case_id": {"type": "string", "pattern": "^R7-[0-9]{2}-(?:P|M)[0-9]{3}$"},
    "expected_authority_source": SHA,
    "expected_enforcing_function": NONEMPTY,
    "expected_evidence_obligation": SHA,
    "expected_interface": NONEMPTY,
    "expected_ledger_delta": ledger_delta,
    "expected_outcome": {"enum": ["ACCEPTED", "REJECTED"]},
    "expected_response_classification": NONEMPTY,
    "forbidden_outcomes": STRING_ARRAY,
    "forbidden_side_effects": STRING_ARRAY,
    "governing_expectation": closed({
        "diagnostic_source_git_blob": GIT,
        "normative_clause": {"type": "string", "pattern": "^CPB-R7-[0-9]{2}$"},
        "r7_requirement": {"type": "string", "pattern": "^R7-[0-9]{2}$"},
    }),
    "provenance": {"const": "PRE_EXECUTION_INDEPENDENT_STATIC_EXPECTATION_NO_EVENT_OBSERVATION_RECEIPT_OR_COMPARATOR_INPUT"},
    "required_evidence": STRING_ARRAY,
    "required_side_effects": STRING_ARRAY,
})
expectation_document = document("r7-independent-expectations", closed({
    "artifact_type": {"const": "R7_INDEPENDENT_EXPECTATIONS"},
    "authoring_authority": {"const": "PRE_EXECUTION_GOVERNING_REQUIREMENT_DERIVATION"},
    "case_count": {"const": 178},
    "expectations": {"type": "array", "minItems": 178, "maxItems": 178, "items": expectation_schema},
    "provenance_policy": {"const": "NO_EXECUTION_EVENT_OBSERVATION_RECEIPT_COMPARATOR_OR_PRIOR_RESULT_INPUT"},
    "schema_version": {"const": VERSION},
    "source_authorities": authority_source,
}), "R7 immutable independent expectations")
write("r7_independent_expectations_schema_DRAFT.json", expectation_document)

probe_document = document("r7i-b01-adversarial-probes", closed({
    "artifact_type": {"const": "R7I_B01_ADVERSARIAL_PROBE_DEFINITIONS"},
    "governing_requirement": {"const": "R7I-B01"},
    "probe_count": {"const": 25},
    "probes": {"type": "array", "minItems": 25, "maxItems": 25, "items": closed({
        "attack": NONEMPTY,
        "expected_terminal_behavior": {"const": "REJECT_BEFORE_TERMINAL_OR_RECONCILIATION_AUTHORITY"},
        "probe_id": {"type": "string", "pattern": "^R7I-B01-A(?:0[1-9]|1[0-9]|2[0-5])$"},
        "required_evidence": NONEMPTY,
    })},
    "schema_version": {"const": VERSION},
}), "R7I-B01 synthetic-provenance adversarial definitions")
write("r7i_b01_adversarial_probes_schema_DRAFT.json", probe_document)

content_authority = closed({
    "count": {"type": "integer", "minimum": 1},
    "git_blob": GIT,
    "path": {"type": "string", "pattern": "^C:/ProgramData/RandleAI/TerminalAuthority/Config/R7Authorities/"},
    "raw_sha256": SHA,
    "size": {"type": "integer", "minimum": 1},
})
blob_authority = closed({"git_blob": GIT, "path": NONEMPTY, "raw_sha256": SHA, "size": {"type": "integer", "minimum": 1}})
policy_document = document("r7-terminal-authority-policy", closed({
    "adversarial_probe_authority": content_authority,
    "allowed_configurations": {"type": "array", "uniqueItems": True, "prefixItems": [{"const": value} for value in ["SHORT_AUTOCRLF_TRUE", "SHORT_AUTOCRLF_FALSE", "LONG_AUTOCRLF_TRUE", "LONG_AUTOCRLF_FALSE"]], "items": False, "minItems": 4, "maxItems": 4},
    "allowed_operations": {"type": "array", "minItems": 8, "maxItems": 8, "uniqueItems": True, "items": {"enum": ["EXECUTE_R7_RUN", "GET_HEALTH", "GET_LEDGER_STATUS", "GET_PUBLIC_TRUST", "GET_R7_RECEIPT", "GET_R7_RECONCILIATION", "ISSUE_R7_ATTEMPT", "RECONCILE_R7_TERMINAL_RECEIPTS"]}},
    "artifact_type": {"const": "R7_REAL_EXECUTION_TERMINAL_AUTHORITY_POLICY"},
    "case_authority": content_authority,
    "correction_requirements": blob_authority,
    "expectation_authority": content_authority,
    "fixed_roots": closed({name: {"type": "string", "pattern": "^C:/ProgramData/RandleAI/TerminalAuthority/"} for name in ["evidence", "fixture_process_receipts", "ledger", "receipts", "reconciliations", "responses", "sessions"]}),
    "interface_version": {"const": "3.0.0-DRAFT"},
    "ledger_id": SHA,
    "provisioning_commit": GIT,
    "public_key_identity": SHA,
    "python_runtime_manifest": closed({"file_count": {"type": "integer", "minimum": 1}, "git_blob": GIT, "raw_sha256": SHA, "runtime_root_identity": SHA, "size": {"type": "integer", "minimum": 1}}),
    "r6_commit": GIT,
    "r7_records": {"type": "array", "minItems": 2, "maxItems": 2, "items": closed({"commit": GIT, "report_git_blob": GIT})},
    "schema_version": {"const": VERSION},
    "service_sid": SID,
    "subject": closed({
        "commit": GIT, "direct_interface_sha256": SHA, "fixture_host_sha256": SHA,
        "governed_access_sha256": SHA, "launcher_sha256": SHA, "ledger_sha256": SHA,
        "python_sha256": SHA, "repository": NONEMPTY, "service_sha256": SHA,
        "tree": GIT, "verifier_sha256": SHA,
    }),
    "synthetic_authority_prohibitions": {"type": "array", "minItems": 7, "uniqueItems": True, "items": NONEMPTY},
    "threat_model": {"const": "FILTERED_INTERACTIVE_USER_HOSTILE_ELEVATED_ADMIN_AND_KERNEL_OUT_OF_SCOPE"},
    "worker_sha256": SHA,
}), "R7 real-execution terminal-authority policy")
write("r7_terminal_authority_policy_schema_DRAFT.json", policy_document)

terminal_payload_properties = {
    "artifact_type": {"const": "R7_SIGNED_TERMINAL_RECEIPT"},
    "attempt_id": SHA, "attempt_locator": EVIDENCE_LOCATOR, "case_count": {"const": 178},
    "case_definition_git_blob": GIT, "case_definition_sha256": SHA, "case_definition_size": {"const": 995804},
    "comparator_result_locator": EVIDENCE_LOCATOR,
    "configuration": {"enum": ["SHORT_AUTOCRLF_TRUE", "SHORT_AUTOCRLF_FALSE", "LONG_AUTOCRLF_TRUE", "LONG_AUTOCRLF_FALSE"]},
    "event_root": SHA, "event_source_locator": EVIDENCE_LOCATOR,
    "expectation_git_blob": GIT, "expectation_sha256": SHA, "expectation_size": {"const": 285399},
    "interface_version": {"const": "3.0.0-DRAFT"}, "ipc_identity": SHA, "issue_time": TIME,
    "ledger_genesis_identity": SHA, "ledger_id": SHA, "ledger_reservation_entry_identity": SHA,
    "ledger_reservation_prior_root": SHA, "ledger_reservation_sequence": {"type": "integer", "minimum": 1},
    "observation_locator": EVIDENCE_LOCATOR, "phase": {"enum": ["CANDIDATE", "FRESH"]},
    "policy_sha256": SHA, "process_index_locator": EVIDENCE_LOCATOR, "public_key_identity": SHA,
    "run_id": SHA, "run_issuance_ledger_entry_identity": SHA, "run_locator": EVIDENCE_LOCATOR,
    "run_nonce": SHA, "schema_version": {"const": VERSION}, "service_binary_sha256": SHA,
    "service_sid": SID, "subject_commit": GIT, "subject_process_id": {"type": "integer", "minimum": 1},
    "subject_run_id": SHA, "suite_process_receipt_locator": EVIDENCE_LOCATOR, "terminal_claim_identity": SHA,
    "terminal_verifier_result": {"const": "SEMANTICALLY_VERIFIED"}, "traceability_locator": EVIDENCE_LOCATOR,
    "worker_sha256": SHA,
}
signed_envelope = lambda payload: closed({
    "payload": payload,
    "public_key_identity": SHA,
    "signature": {"type": "string", "pattern": "^[A-Za-z0-9+/]+={0,2}$"},
    "signature_algorithm": {"const": "RSA-PSS-SHA256"},
})
write("signed_terminal_receipt_R7_schema_DRAFT.json", document("signed-terminal-receipt-r7", signed_envelope(closed(terminal_payload_properties)), "R7 signed real-execution terminal receipt"))

reconciliation_payload_properties = {
    "artifact_type": {"const": "R7_SIGNED_EXTERNAL_RECONCILIATION_RECEIPT"}, "attempt_id": SHA,
    "candidate_event_root": SHA, "candidate_receipt_identity": SHA, "candidate_receipt_locator": TERMINAL_LOCATOR,
    "candidate_run_id": SHA, "case_definition_git_blob": GIT,
    "configuration": {"enum": ["SHORT_AUTOCRLF_TRUE", "SHORT_AUTOCRLF_FALSE", "LONG_AUTOCRLF_TRUE", "LONG_AUTOCRLF_FALSE"]},
    "expectation_git_blob": GIT, "fresh_event_root": SHA, "fresh_receipt_identity": SHA,
    "fresh_receipt_locator": TERMINAL_LOCATOR, "fresh_run_id": SHA, "interface_version": {"const": "3.0.0-DRAFT"},
    "issue_time": TIME, "ledger_id": SHA, "ledger_reservation_entry_identity": SHA,
    "ledger_reservation_sequence": {"type": "integer", "minimum": 1}, "policy_sha256": SHA,
    "provenance_disjoint": {"const": True}, "public_key_identity": SHA, "reconciliation_claim_identity": SHA,
    "reconciliation_evaluator_result_locator": EVIDENCE_LOCATOR, "reconciliation_process_nonce": SHA,
    "reconciliation_process_receipt_locator": EVIDENCE_LOCATOR, "reconciliation_process_run_id": SHA,
    "reconciliation_result": {"const": "SEMANTICALLY_EQUIVALENT_REAL_EXECUTIONS"}, "schema_version": {"const": VERSION},
    "service_binary_sha256": SHA, "service_sid": SID, "subject_commit": GIT,
    "synthetic_result_class_absent": {"const": True}, "worker_sha256": SHA,
}
write("signed_reconciliation_receipt_R7_schema_DRAFT.json", document("signed-reconciliation-receipt-r7", signed_envelope(closed(reconciliation_payload_properties)), "R7 signed external reconciliation receipt"))

event_properties = {
    "actual_authority_identity": SHA, "actual_outcome": {"enum": ["ACCEPTED", "REJECTED"]},
    "case_definition_git_blob": GIT, "case_id": {"type": "string", "pattern": "^R7-[0-9]{2}-(?:P|M)[0-9]{3}$"},
    "enforcing_function": NONEMPTY, "event_constructor_binary_sha256": SHA, "event_hash": SHA,
    "event_schema_version": {"const": VERSION}, "event_time": TIME, "expectation_git_blob": GIT,
    "fixture_body_identity": SHA, "fixture_helper_file_identity": {"type": "string"}, "fixture_helper_invoked": {"type": "boolean"},
    "fixture_helper_process_id": {"type": "integer", "minimum": 0}, "fixture_process_receipt_identity": SHA,
    "fixture_process_receipt_locator": OPTIONAL_EVIDENCE_LOCATOR, "fixture_reparse_snapshot_identity": SHA,
    "fixture_reparse_snapshot_locator": OPTIONAL_EVIDENCE_LOCATOR, "forbidden_side_effect_absent": {"type": "boolean"},
    "inner_event_hash": SHA, "inner_execution_receipt_identity": SHA, "interface_identity": SHA,
    "interface_invoked": {"const": True}, "interface_operation": {"const": "execute_case"},
    "invoking_process_receipt_identity": SHA, "outer_post_ledger_root": SHA,
    "outer_post_ledger_sequence": {"type": "integer", "minimum": 0}, "outer_pre_ledger_root": SHA,
    "outer_pre_ledger_sequence": {"type": "integer", "minimum": 0}, "prior_event_hash": SHA,
    "public_interface": NONEMPTY, "public_interface_end_time": TIME, "public_interface_start_time": TIME,
    "public_request_locator": EVIDENCE_LOCATOR, "public_response_locator": EVIDENCE_LOCATOR,
    "raw_evidence_locators": {"type": "array", "minItems": 3, "items": EVIDENCE_LOCATOR},
    "request_sha256": SHA, "response_classification": NONEMPTY, "response_sha256": SHA, "run_id": SHA,
    "sequence": {"type": "integer", "minimum": 1}, "subject_case_token_identity": SHA,
    "subject_event_ledger_delta": {"type": "integer", "minimum": 1}, "subject_launcher_process_id": {"type": "integer", "minimum": 1},
    "subject_process_id": {"type": "integer", "minimum": 1}, "subject_service_sha256": SHA,
    "suite_process_receipt_locator": EVIDENCE_LOCATOR, "target_process_binary_sha256": SHA,
}
observation_properties = {
    "actual_authority_identity": SHA, "actual_outcome": {"enum": ["ACCEPTED", "REJECTED"]}, "case_id": NONEMPTY,
    "derived_at": TIME, "enforcing_function": NONEMPTY, "event_hash": SHA, "event_sequence": {"type": "integer", "minimum": 1},
    "evidence_citations": {"type": "array", "minItems": 4, "items": EVIDENCE_LOCATOR},
    "fixture_body_identity": SHA, "fixture_helper_file_identity": {"type": "string"}, "fixture_helper_invoked": {"type": "boolean"},
    "fixture_helper_process_id": {"type": "integer", "minimum": 0}, "fixture_process_receipt_identity": SHA,
    "fixture_process_receipt_locator": OPTIONAL_EVIDENCE_LOCATOR, "fixture_reparse_snapshot_identity": SHA,
    "fixture_reparse_snapshot_locator": OPTIONAL_EVIDENCE_LOCATOR, "forbidden_side_effect_absent": {"type": "boolean"},
    "inner_event_hash": SHA, "inner_execution_receipt_identity": SHA, "interface_invoked": {"const": True},
    "outer_ledger_delta": {"type": "integer", "minimum": 0}, "response_classification": NONEMPTY,
    "subject_case_token_identity": SHA, "subject_event_ledger_delta": {"type": "integer", "minimum": 1},
    "subject_process_id": {"type": "integer", "minimum": 1},
}

raw_case_properties = {
    "actual_authority_identity": SHA, "actual_outcome": {"enum": ["ACCEPTED", "REJECTED"]}, "case_id": NONEMPTY,
    "enforcing_function": NONEMPTY, "fixture_body_identity": SHA, "fixture_helper_file_identity": {"type": "string"},
    "fixture_helper_invoked": {"type": "boolean"}, "fixture_helper_process_id": {"type": "integer", "minimum": 0},
    "fixture_process_receipt_identity": SHA, "fixture_process_receipt_locator": OPTIONAL_EVIDENCE_LOCATOR,
    "fixture_reparse_snapshot_identity": SHA, "fixture_reparse_snapshot_locator": OPTIONAL_EVIDENCE_LOCATOR,
    "inner_event_hash": SHA, "inner_execution_receipt_identity": SHA, "outer_post_ledger_root": SHA,
    "outer_post_ledger_sequence": {"type": "integer", "minimum": 0}, "outer_pre_ledger_root": SHA,
    "outer_pre_ledger_sequence": {"type": "integer", "minimum": 0}, "public_interface": NONEMPTY,
    "public_interface_end_time": TIME, "public_interface_start_time": TIME, "public_request_locator": EVIDENCE_LOCATOR,
    "public_response_locator": EVIDENCE_LOCATOR, "request_sha256": SHA, "response_classification": NONEMPTY,
    "response_sha256": SHA, "subject_case_token_identity": SHA,
    "subject_event_ledger_delta": {"type": "integer", "minimum": 1},
    "subject_launcher_process_id": {"type": "integer", "minimum": 1}, "subject_process_id": {"type": "integer", "minimum": 1},
}

suite_process_payload = closed({
    "artifact_type": {"const": "R7_REAL_SUITE_PROCESS_RECEIPT"}, "case_count": {"const": 178}, "command_identity": SHA,
    "completion_state": {"const": "COMPLETE"}, "completion_time": TIME, "interface_version": {"const": "3.0.0-DRAFT"},
    "fixture_host_file_identity": {"type": "string"}, "fixture_host_sha256": SHA,
    "fixture_process_receipt_count": {"type": "integer", "minimum": 0}, "launch_receipt_locator": EVIDENCE_LOCATOR,
    "launcher_file_identity": {"type": "string"}, "launcher_process_id": {"type": "integer", "minimum": 1},
    "launcher_sha256": SHA, "mode": {"const": "execute-real-suite"},
    "parent_service_process_id": {"type": "integer", "minimum": 1}, "parent_service_binary_sha256": SHA,
    "parent_service_binary_file_identity": {"type": "string"}, "python_file_identity": {"type": "string"}, "python_sha256": SHA,
    "raw_case_index_locator": EVIDENCE_LOCATOR, "run_id": SHA, "schema_version": {"const": VERSION},
    "stderr_locator": EVIDENCE_LOCATOR, "subject_commit": GIT, "subject_process_id": {"type": "integer", "minimum": 1},
    "subject_ready_locator": EVIDENCE_LOCATOR, "subject_run_id": SHA, "subject_service_file_identity": {"type": "string"},
    "subject_service_git_blob": GIT, "subject_service_sha256": SHA,
    "subject_token_evidence": {"type": "object", "minProperties": 4}, "subject_token_evidence_identity": SHA,
})

worker_process_payload = closed({
    "artifact_type": {"const": "R7_PROCESS_EXECUTION_RECEIPT"}, "command_identity": SHA,
    "completion_state": {"const": "COMPLETE"}, "completion_time": TIME, "environment_identity": SHA,
    "exit_code": {"const": 0}, "input_identity": SHA, "input_locator": EVIDENCE_LOCATOR,
    "interface_version": {"const": "3.0.0-DRAFT"}, "launcher_authority_identity": SHA,
    "launcher_pid": {"type": "integer", "minimum": 1}, "mode": {"enum": ["derive-observations", "compare", "reconcile"]},
    "parent_service_binary_sha256": SHA, "process_id": {"type": "integer", "minimum": 1}, "process_nonce": SHA,
    "result": {"type": "object", "minProperties": 8}, "run_id": SHA, "schema_version": {"const": VERSION},
    "start_time": TIME, "stderr_identity": SHA, "stderr_length": {"type": "integer", "minimum": 0},
    "stderr_locator": EVIDENCE_LOCATOR, "stdout_identity": SHA, "stdout_length": {"type": "integer", "minimum": 1},
    "stdout_locator": EVIDENCE_LOCATOR, "worker_file_identity": {"type": "string"}, "worker_sha256": SHA,
})

subject_launch_properties = {
    "artifact_type": {"const": "R7_MEASURED_SUBJECT_LAUNCH"}, "authentication_type": {"type": "string"},
    "group_sids": {"type": "array", "items": SID}, "is_administrator": {"const": False}, "launch_time": TIME,
    "launcher_binary_sha256": SHA, "launcher_process_id": {"type": "integer", "minimum": 1}, "python_binary_sha256": SHA,
    "subject_process_id": {"type": "integer", "minimum": 1}, "subject_source_sha256": SHA,
    "token_inheritance": {"const": "CREATEPROCESS_DEFAULT_CALLER_TOKEN"}, "user_sid": SID,
}

fixture_receipt_properties = {
    "artifact_type": {"const": "R7_MEASURED_JUNCTION_FIXTURE_PROCESS"}, "authentication_type": {"type": "string"},
    "body_identity": SHA, "command": NONEMPTY, "command_sha256": SHA, "end_time": TIME, "exit_code": {"const": 0},
    "fixture_nonce": SHA, "group_sids": {"type": "array", "items": SID}, "helper_binary_file_identity": {"type": "string"},
    "helper_binary_sha256": SHA, "helper_process_id": {"type": "integer", "minimum": 1}, "is_administrator": {"const": False},
    "junction_path": NONEMPTY, "junction_path_sha256": SHA, "operation": {"const": "CREATE_DIRECTORY_JUNCTION_FIXTURE"},
    "outer_run_id": SHA, "parent_binary_file_identity": {"type": "string"}, "parent_binary_sha256": SHA,
    "parent_process_id": {"type": "integer", "minimum": 1}, "parent_start_time": TIME, "reparse_tag": {"const": "a0000003"},
    "schema_version": {"const": VERSION}, "start_time": TIME, "target_path": NONEMPTY, "target_path_sha256": SHA,
    "token_inheritance": {"const": "CREATEPROCESS_DEFAULT_CALLER_TOKEN"}, "user_sid": SID,
}

reparse_evidence_properties = {
    "artifact_type": {"const": "R7_SERVICE_REPARSE_SIDE_EFFECT_EVIDENCE"}, "body_identity": SHA,
    "capture_model": {"const": "FSCTL_GET_REPARSE_POINT"}, "capture_time": TIME, "case_id": NONEMPTY,
    "fixture_process_receipt_identity": SHA, "junction_attributes": {"type": "integer", "minimum": 0},
    "junction_path": NONEMPTY, "reparse_data_base64": NONEMPTY, "reparse_data_sha256": SHA, "run_id": SHA,
    "schema_version": {"const": VERSION}, "service_binary_file_identity": {"type": "string"}, "service_binary_sha256": SHA,
    "service_process_id": {"type": "integer", "minimum": 1}, "service_sid": SID,
    "target_attributes": {"type": "integer", "minimum": 0}, "target_path": NONEMPTY,
}

evidence_defs = {
    "event": closed(event_properties),
    "fixtureProcessReceipt": closed(fixture_receipt_properties),
    "rawCase": closed(raw_case_properties),
    "rawCaseIndex": closed({
        "artifact_type": {"const": "R7_REAL_SUITE_RAW_CASE_INDEX"}, "case_count": {"const": 178},
        "cases": {"type": "array", "minItems": 178, "maxItems": 178, "items": {"$ref": "#/$defs/rawCase"}},
        "final_source_locator": EVIDENCE_LOCATOR, "outer_run_id": SHA, "schema_version": {"const": VERSION},
        "setup_and_shutdown_locators": {"type": "array", "minItems": 8, "items": EVIDENCE_LOCATOR},
        "subject_ledger_snapshot_locator": EVIDENCE_LOCATOR, "subject_run_id": SHA,
    }),
    "reparseSideEffect": closed(reparse_evidence_properties),
    "reconciliationEvaluator": closed({
        "artifact_type": {"const": "R7_INDEPENDENT_EXTERNAL_RECONCILIATION_RESULT"}, "attempt_id": SHA,
        "candidate_event_root": SHA, "candidate_receipt_identity": SHA, "candidate_receipt_locator": TERMINAL_LOCATOR,
        "candidate_run_id": SHA, "case_definition_git_blob": GIT,
        "discrepancies": {"type": "array", "items": closed({"case_id": {"type": "string"}, "code": NONEMPTY, "detail": NONEMPTY})},
        "discrepancy_count": {"const": 0}, "expectation_git_blob": GIT, "fresh_event_root": SHA,
        "fresh_receipt_identity": SHA, "fresh_receipt_locator": TERMINAL_LOCATOR, "fresh_run_id": SHA,
        "policy_sha256": SHA, "reconciliation_process_nonce": SHA,
        "reconciliation_result": {"const": "RECONCILED_REAL_EXECUTIONS"}, "resolved_terminal_count": {"const": 2},
        "run_id": SHA, "schema_version": {"const": VERSION}, "service_binary_sha256": SHA,
        "synthetic_result_class_absent": {"const": True}, "worker_binary_sha256": SHA,
    }),
    "signedSuiteProcessReceipt": signed_envelope(suite_process_payload),
    "signedWorkerProcessReceipt": signed_envelope(worker_process_payload),
    "subjectLaunchReceipt": closed(subject_launch_properties),
    "eventSource": closed({
        "artifact_type": {"const": "R7_CURRENT_EXECUTION_EVENTS"}, "case_definition_git_blob": GIT,
        "event_count": {"const": 178}, "event_root": SHA,
        "events": {"type": "array", "minItems": 178, "maxItems": 178, "items": {"$ref": "#/$defs/event"}},
        "expectation_git_blob": GIT, "run_id": SHA, "schema_version": {"const": VERSION},
        "subject_run_id": SHA, "suite_process_receipt_locator": EVIDENCE_LOCATOR,
    }),
    "observation": closed(observation_properties),
    "observations": closed({
        "artifact_type": {"const": "R7_DERIVED_CURRENT_OBSERVATIONS"}, "event_source_locator": EVIDENCE_LOCATOR,
        "observation_count": {"const": 178},
        "observations": {"type": "array", "minItems": 178, "maxItems": 178, "items": {"$ref": "#/$defs/observation"}},
        "observer_binary_sha256": SHA, "observer_process_id": {"type": "integer", "minimum": 1},
        "observer_process_nonce": SHA, "run_id": SHA, "schema_version": {"const": VERSION},
    }),
    "comparison": closed({
        "artifact_type": {"const": "R7_INDEPENDENT_COMPARATOR_RESULT"},
        "case_decisions": {"type": "array", "minItems": 178, "maxItems": 178, "items": closed({"case_id": NONEMPTY, "decision": {"const": "CONFORMANT"}, "event_hash": SHA})},
        "case_definition_git_blob": GIT, "comparator_binary_sha256": SHA, "comparator_process_nonce": SHA,
        "conformity": {"const": "CONFORMANT"},
        "discrepancies": {"type": "array", "items": closed({"case_id": {"type": "string"}, "code": NONEMPTY, "detail": NONEMPTY})},
        "discrepancy_count": {"type": "integer", "minimum": 0}, "event_source_locator": EVIDENCE_LOCATOR,
        "expectation_git_blob": GIT, "observation_locator": EVIDENCE_LOCATOR, "resolved_case_count": {"const": 178},
        "run_id": SHA, "schema_version": {"const": VERSION}, "traceability_locator": EVIDENCE_LOCATOR,
    }),
    "processIndex": closed({
        "artifact_type": {"const": "R7_CURRENT_PROCESS_RECEIPT_INDEX"}, "comparator_process_receipt_locator": EVIDENCE_LOCATOR,
        "observation_process_receipt_locator": EVIDENCE_LOCATOR, "process_count": {"const": 3}, "run_id": SHA,
        "schema_version": {"const": VERSION}, "suite_process_receipt_locator": EVIDENCE_LOCATOR,
    }),
    "traceability": closed({
        "artifact_type": {"const": "R7_BIDIRECTIONAL_CURRENT_EXECUTION_TRACE"}, "case_definition_git_blob": GIT,
        "expectation_git_blob": GIT, "row_count": {"const": 178},
        "rows": {"type": "array", "minItems": 178, "maxItems": 178, "items": closed({
            "case_definition_git_blob": GIT, "case_id": NONEMPTY, "comparator_stage": {"const": "R7MeasuredWorker.compare"},
            "event_hash": SHA, "event_source_locator": EVIDENCE_LOCATOR, "expectation_git_blob": GIT,
            "governing_requirement_id": NONEMPTY, "observation_stage": {"const": "R7MeasuredWorker.derive-observations"},
            "process_receipt_locator": EVIDENCE_LOCATOR, "public_interface": NONEMPTY,
            "request_locator": EVIDENCE_LOCATOR, "response_locator": EVIDENCE_LOCATOR,
            "reverse_mapping_required": {"const": True}, "run_id": SHA,
        })},
        "run_id": SHA, "schema_version": {"const": VERSION},
    }),
}
evidence_document = {
    "$schema": SCHEMA,
    "$id": "https://randle.ai/schemas/terminal-authority-evidence-package-r7-7.1.0-draft.json",
    "title": "R7 current-run evidence graph objects",
    "$defs": evidence_defs,
    "oneOf": [{"$ref": f"#/$defs/{name}"} for name in (
        "eventSource", "observations", "comparison", "processIndex", "traceability", "rawCaseIndex",
        "signedSuiteProcessReceipt", "signedWorkerProcessReceipt", "subjectLaunchReceipt", "fixtureProcessReceipt", "reparseSideEffect",
        "reconciliationEvaluator",
    )],
}
write("terminal_authority_evidence_schema_package_R7_DRAFT.json", evidence_document)

coverage_document = document("r7-terminal-public-interface-coverage", closed({
    "artifact_type": {"const": "R7_REAL_PUBLIC_INTERFACE_COVERAGE"},
    "authority_status": {"const": "IMPLEMENTATION_EVIDENCE_NOT_ACCEPTANCE"},
    "case_definition_git_blob": GIT, "case_definition_sha256": SHA, "case_count": {"const": 178},
    "case_execution_count": {"type": "integer", "minimum": 178},
    "expected_acceptance_counts": closed({"ACCEPTED": {"const": 20}, "REJECTED": {"const": 158}}),
    "expectation_git_blob": GIT, "expectation_sha256": SHA,
    "interface_counts": {"type": "object", "minProperties": 1, "additionalProperties": {"type": "integer", "minimum": 1}},
    "matrix_execution_count": {"type": "integer", "minimum": 2}, "reconciliation_count": {"type": "integer", "minimum": 1},
    "requirement_counts": {"type": "object", "minProperties": 15, "additionalProperties": {"type": "integer", "minimum": 1}},
    "r7i_b01_attack_count": {"const": 25}, "schema_version": {"const": VERSION}, "status": {"const": "PASS"},
}), "R7 real public-interface coverage summary")
write("r7_terminal_public_interface_coverage_schema_DRAFT.json", coverage_document)

print(json.dumps({"generated_schema_count": 8, "schema_version": VERSION, "status": "GENERATED"}, sort_keys=True))
