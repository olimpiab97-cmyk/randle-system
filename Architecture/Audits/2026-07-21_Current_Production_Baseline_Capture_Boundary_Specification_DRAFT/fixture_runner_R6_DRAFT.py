#!/usr/bin/env python3
"""Fresh-run R6 candidate/fresh fixture runner; never performs a production capture."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from governed_file_access_DRAFT import read_binary, write_disposable_binary
from r6_authority_verifier_DRAFT import (
    AuthorityRepository,
    BINDINGS_PATH,
    R6AuthorityError,
    audit_authority_source,
    canonical_json_bytes,
    code_object_fingerprint,
    freeze,
    git_blob_identity,
    git_object_bytes,
    parse_timestamp,
    require,
    semantic_identity,
    sha256,
    strict_json_loads,
    thaw,
    validate_compatibility,
    validate_documents,
    validate_document_text,
    validate_json_schema,
    validate_review_receipt,
    validate_traceability,
    verify_mandatory_tests,
    verify_validator_environment,
)
from fresh_run_issuer_R6_DRAFT import consume_run_authority, issue_fresh_run
from process_launch_boundary_R6_DRAFT import launch_measured


PACKAGE_RELATIVE = (
    "Architecture/Audits/"
    "2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT"
)
_BOUND_LAUNCH_MEASURED = launch_measured
_BOUND_ISSUE_FRESH_RUN = issue_fresh_run


class FixtureInfrastructureError(RuntimeError):
    pass


def _issue_run_checked(authorities: AuthorityRepository, request: dict[str, Any], disposable_root: Path) -> dict[str, Any]:
    policy = authorities.load_json("fresh_run_issuance_policy")
    require(code_object_fingerprint(_BOUND_ISSUE_FRESH_RUN.__code__) == policy["issuer_function_fingerprint"], "RUN_ISSUER_FUNCTION_REPLACED")
    return _BOUND_ISSUE_FRESH_RUN(authorities, request, disposable_root)


def _launch_checked(authorities: AuthorityRepository, mode: str, run_authority: dict[str, Any], payload: dict[str, Any], subject_role: str, disposable_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    policy = authorities.load_json("process_launch_authority")
    require(code_object_fingerprint(_BOUND_LAUNCH_MEASURED.__code__) == policy["launcher_function_fingerprint"], "PROCESS_LAUNCH_FUNCTION_REPLACED")
    return _BOUND_LAUNCH_MEASURED(authorities, mode, run_authority, payload, subject_role, disposable_root)


def _raw_authority(repository: Path, authority_ref: str, relative: str, worktree_mode: bool) -> bytes:
    if worktree_mode:
        return read_binary(repository / Path(relative), allow_reparse=False).data
    return git_object_bytes(repository, authority_ref, relative)


def _hash_file(path: Path) -> str:
    return read_binary(path, allow_reparse=False).sha256


def _stable_event(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "case_id": event["case_id"],
        "mutation_identity": event["mutation_identity"],
        "event_type": event["event_type"],
        "enforcing_module": event["enforcing_module"],
        "enforcing_function": event["enforcing_function"],
        "function_code_fingerprint": event["function_code_fingerprint"],
        "source_code_blob": event["source_code_blob"],
        "source_location": event["source_location"],
        "actual_input_identity": event["actual_input_identity"],
        "actual_result_status": event["actual_result_status"],
        "actual_result_code": event["actual_result_code"],
        "actual_authority_identity": event["actual_authority_identity"],
    }


def _derive_observations(events: Sequence[Mapping[str, Any]], source_receipt: Mapping[str, Any], run_authority: Mapping[str, Any], recorder_process_receipt: Mapping[str, Any]) -> list[dict[str, Any]]:
    require(source_receipt["finalized"] is True, "OBSERVATION_SOURCE_NOT_FINALIZED")
    require(source_receipt["run_id"] == run_authority["run_id"], "OBSERVATION_RUN_ID")
    require(source_receipt["event_count"] == len(events), "OBSERVATION_EVENT_COUNT")
    require(source_receipt["recorder_process_id"] == recorder_process_receipt["worker_pid"], "OBSERVATION_PROCESS_ID")
    prior = "0" * 64
    observations: list[dict[str, Any]] = []
    for sequence, event in enumerate(events, 1):
        require(event["sequence"] == sequence, "EVENT_SEQUENCE")
        require(event["prior_event_hash"] == prior, "EVENT_PRIOR_HASH")
        claimed = event["event_hash"]
        body = dict(event)
        body.pop("event_hash")
        require(semantic_identity(body) == claimed, "EVENT_HASH")
        require(event["run_id"] == run_authority["run_id"], "EVENT_RUN_ID")
        require(event["process_id"] == recorder_process_receipt["worker_pid"], "EVENT_PROCESS_ID")
        require(parse_timestamp(event["event_timestamp"], "event") >= parse_timestamp(run_authority["issued_timestamp"], "run issued"), "EVENT_TIMESTAMP_FRESHNESS")
        prior = claimed
        observations.append({
            "schema_version": "6.0.0-DRAFT",
            "case_id": event["case_id"],
            "run_id": run_authority["run_id"],
            "actual_input_identity": event["actual_input_identity"],
            "actual_status": event["actual_result_status"],
            "observed_code": event["actual_result_code"],
            "observed_enforcing_function": event["enforcing_function"],
            "observed_code_blob": event["source_code_blob"],
            "observed_authority_source": event["actual_authority_identity"],
            "observed_evidence_result": "FRESH_EXTERNAL_RECORDER_EVENT",
            "event_type": event["event_type"],
            "event_identity": event["event_hash"],
            "event_sequence": event["sequence"],
            "event_source_root": source_receipt["append_only_root"],
            "execution_receipt_identity": semantic_identity(dict(recorder_process_receipt)),
            "mandatory_test_receipt_identity": source_receipt["mandatory_test_receipt_identity"],
        })
    require(prior == source_receipt["append_only_root"], "EVENT_ROOT")
    return observations


def _normalized_observations(observations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    fields = (
        "case_id", "actual_input_identity", "actual_status", "observed_code", "observed_enforcing_function",
        "observed_code_blob", "observed_authority_source", "observed_evidence_result", "event_type",
        "mandatory_test_receipt_identity",
    )
    return [{field: item[field] for field in fields} for item in observations]


def _validate_event_source_schema(authorities: AuthorityRepository, events: list[dict[str, Any]], source_receipt: dict[str, Any]) -> None:
    event_schema = authorities.load_json("enforcement_event_record_schema")
    receipt_schema = authorities.load_json("fresh_event_source_receipt_schema")
    for index, event in enumerate(events):
        validate_json_schema(event_schema, event, f"event[{index}]")
    validate_json_schema(receipt_schema, source_receipt, "fresh_event_source_receipt")


def _claim_evidence(authorities: AuthorityRepository, events: Sequence[Mapping[str, Any]], observations: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    policy = authorities.load_json("document_claim_evidence")
    event_by_id = {item["case_id"]: item for item in events}
    observation_by_id = {item["case_id"]: item for item in observations}
    result: dict[str, str] = {}
    for claim in policy["claims"]:
        evidence = []
        for case_id in claim["case_ids"]:
            require(case_id in event_by_id and case_id in observation_by_id, "DOCUMENT_EVIDENCE_EVENT_MISSING", case_id)
            event = event_by_id[case_id]
            observation = observation_by_id[case_id]
            evidence.append({
                "case_id": case_id, "event_status": event["actual_result_status"], "event_code": event["actual_result_code"],
                "function": event["enforcing_function"], "observation_code": observation["observed_code"],
            })
        result[claim["claim_id"]] = semantic_identity(evidence)
    return result


def _schema_validation(authorities: AuthorityRepository) -> dict[str, Any]:
    schema_roles = sorted(role for role in authorities.roles if role.endswith("_schema"))
    instance_roles = sorted(role for role in authorities.roles if authorities.binding(role).get("schema_role"))
    for role in schema_roles:
        schema = authorities.load_json(role)
        from jsonschema import Draft202012Validator
        Draft202012Validator.check_schema(thaw(schema))
    for role in instance_roles:
        authorities.load_json(role)
    invalid = [
        b'{"a":1,"a":2}\n', '{"e\u0301":1}\n'.encode(), '{"a":"e\u0301"}\n'.encode(),
        b'{"a":1.5}\n', b'{"z":1,"a":2}\n',
    ]
    rejected = 0
    for data in invalid:
        try:
            strict_json_loads(data)
        except R6AuthorityError:
            rejected += 1
    require(rejected == len(invalid), "CANONICAL_INVALID_ACCEPTED")
    access = thaw(authorities.load_json("access_origin_authority"))
    access_schema = authorities.load_json("access_origin_authority_schema")
    schema_mutations = []
    upper = dict(access); upper["git_blob"] = upper["git_blob"].upper(); schema_mutations.append(upper)
    extra = dict(access); extra["unknown"] = True; schema_mutations.append(extra)
    missing = dict(access); missing.pop("schema_version"); schema_mutations.append(missing)
    schema_rejected = 0
    for index, value in enumerate(schema_mutations):
        try:
            validate_json_schema(access_schema, value, f"invalid_schema_{index}")
        except R6AuthorityError:
            schema_rejected += 1
    require(schema_rejected == len(schema_mutations), "SCHEMA_INVALID_ACCEPTED")
    return {
        "schema_count": len(schema_roles), "active_instance_count": len(instance_roles), "authority_instance_count": len(instance_roles),
        "valid_synthetic_count": 1, "invalid_synthetic_count": len(invalid) + len(schema_mutations), "valid_accepted": 1, "invalid_rejected": rejected + schema_rejected,
        "warnings": 0, "errors": 0, "canonical_schema_semantic_disagreements": 0,
    }


def _static_access_probes(authorities: AuthorityRepository) -> str:
    vectors = [
        b'import builtins\ngetattr(builtins,"op"+"en")("authority.json")\n',
        b'import os\ngetattr(os,"scan"+"dir")("authority")\n',
        b'def f(reader=open):\n return reader("authority.json")\nf()\n',
        b'import os\ndef outer():\n scan=os.scandir\n return lambda p:scan(p)\nouter()("authority")\n',
        b'd={"reader":open}\nd["reader"]("authority.json")\n',
    ]
    rejected = []
    for index, source in enumerate(vectors):
        try:
            audit_authority_source(source)
        except R6AuthorityError as exc:
            rejected.append({"index": index, "code": exc.code})
    require(len(rejected) == len(vectors), "ACCESS_STATIC_PROBE_BYPASS")
    approved = thaw(authorities.load_json("access_origin_authority"))
    malicious = b'import builtins\nbuiltins.open("authority.json")\n'
    try:
        audit_authority_source(malicious, approved)
    except R6AuthorityError as exc:
        require(exc.code in {"ACCESS_APPROVED_RAW_MISMATCH", "ACCESS_APPROVED_BLOB_MISMATCH"}, "ACCESS_TRUSTED_LABEL_PROBE")
        rejected.append({"index": len(vectors), "code": exc.code})
    else:
        raise R6AuthorityError("ACCESS_TRUSTED_LABEL_BYPASS")
    return semantic_identity(rejected)


def _validator_mutation_probes(lock_bytes: bytes) -> str:
    lock = strict_json_loads(lock_bytes)
    results = []
    mutations = [("missing-rfc3339-validator", "rfc3339-validator"), ("missing-PyYAML", "PyYAML"), ("missing-idna", "idna")]
    for label, name in mutations:
        mutated = json.loads(json.dumps(lock))
        mutated["required_distributions"][name] = "0.0.0-MISSING"
        try:
            verify_validator_environment(canonical_json_bytes(mutated))
        except R6AuthorityError as exc:
            require(exc.code == "VALIDATOR_DISTRIBUTION_VERSION", "VALIDATOR_MUTATION_SURFACE", label)
            results.append({"mutation": label, "code": exc.code})
        else:
            raise R6AuthorityError("VALIDATOR_MUTATION_BYPASS", label)
    mutated = json.loads(json.dumps(lock)); mutated["required_formats"].append("r6-nonexistent-format")
    try:
        verify_validator_environment(canonical_json_bytes(mutated))
    except R6AuthorityError as exc:
        require(exc.code == "VALIDATOR_FORMAT_CAPABILITY_MISSING", "VALIDATOR_MUTATION_SURFACE", "format")
        results.append({"mutation": "missing-format-capability", "code": exc.code})
    else:
        raise R6AuthorityError("VALIDATOR_MUTATION_BYPASS", "format")
    return semantic_identity(results)


def _load_candidate(path: Path) -> dict[str, Any]:
    return strict_json_loads(read_binary(path, allow_reparse=False).data)


def _reconcile(candidate: dict[str, Any], fresh: dict[str, Any]) -> dict[str, Any]:
    deterministic_fields = (
        "specification_identity", "case_definition_identity", "case_set_identity", "expectation_identity",
        "enforcing_code_identity", "schema_set_identity", "authority_set_identity", "normalized_observation_identity",
        "normalized_comparison_identity", "mandatory_test_semantic_identity", "traceability_identity", "document_claim_identity",
    )
    for field in deterministic_fields:
        require(candidate[field] == fresh[field], "RECONCILIATION_SEMANTIC_MISMATCH", field)
    for field in ("run_id", "run_nonce_identity", "parser_execution_receipt_identity", "comparator_execution_receipt_identity", "event_source_identity", "event_root", "terminal_receipt_identity"):
        require(candidate[field] != fresh[field], "RECONCILIATION_PROVENANCE_REUSED", field)
    return {"status": "MATCHED", "deterministic_fields": list(deterministic_fields), "candidate_run_id": candidate["run_id"], "fresh_run_id": fresh["run_id"]}


def run(
    repository: Path,
    authority_ref: str,
    physical_root: Path,
    phase: str,
    candidate_receipt: Path | None,
    state_root: Path,
    *,
    worktree_mode: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    lock_path = f"{PACKAGE_RELATIVE}/validator_environment_R6_DRAFT.lock.json"
    lock_bytes = _raw_authority(repository, authority_ref, lock_path, worktree_mode)
    environment_receipt = thaw(verify_validator_environment(lock_bytes))
    validator_mutation_probe_identity = _validator_mutation_probes(lock_bytes)
    authorities = AuthorityRepository(repository, authority_ref, worktree_mode=worktree_mode)
    definitions = thaw(authorities.load_json("case_definitions"))
    expectations = thaw(authorities.load_json("independent_expectations"))
    require([item["case_id"] for item in definitions["cases"]] == [item["case_id"] for item in expectations["cases"]], "EXPECTATION_CASE_ORDER")
    case_definition_identity = authorities.load_bytes("case_definitions").raw_sha256
    case_set_identity = semantic_identity(sorted(item["case_id"] for item in definitions["cases"]))
    expectation_identity = authorities.load_bytes("independent_expectations").raw_sha256
    schema_set_identity = semantic_identity([
        {"role": role, "path": authorities.binding(role)["path"], "git_blob": authorities.load_bytes(role).git_blob}
        for role in sorted(role for role in authorities.roles if role.endswith("_schema"))
    ])
    enforcing_roles = ("governed_file_access_code", "access_origin_code", "r6_authority_verifier_code", "r6_enforcement_code", "fixture_runner_code", "process_launch_code", "fresh_run_issuer_code", "isolated_worker_code", "historical_parser_code", "comparison_engine_code")
    enforcing_code_identity = semantic_identity([{"role": role, "git_blob": authorities.load_bytes(role).git_blob} for role in enforcing_roles])
    specification_identity = authorities.load_bytes("specification").raw_sha256
    mandatory_receipt = thaw(verify_mandatory_tests(authorities, physical_root))
    validate_json_schema(authorities.load_json("mandatory_test_receipt_schema"), mandatory_receipt, "mandatory_test_receipt")
    validate_json_schema(authorities.load_json("validator_environment_receipt_schema"), environment_receipt, "validator_environment_receipt")
    mandatory_test_semantic_identity = semantic_identity(mandatory_receipt)
    authority_set_identity = authorities.identity
    disposable_root = Path(tempfile.mkdtemp(prefix="r6-process-", dir=str(Path(tempfile.gettempdir()))))
    cleanup = "PENDING"
    try:
        request = {
            "issuing_authority": authorities.load_json("fresh_run_issuance_policy")["issuing_authority"],
            "specification_commit": authorities.commit,
            "case_set_identity": case_set_identity,
            "expectation_identity": expectation_identity,
            "enforcing_code_identity": enforcing_code_identity,
            "schema_set_identity": schema_set_identity,
            "event_recorder_authority": authorities.load_json("recorder_authority")["authority_id"],
            "comparator_authority": authorities.load_json("comparison_authority")["authority_id"],
            "mandatory_test_authority_identity": authorities.load_bytes("mandatory_test_authority").raw_sha256,
        }
        run_authority = _issue_run_checked(authorities, request, disposable_root)
        validate_json_schema(authorities.load_json("fresh_run_authority_schema"), run_authority, "fresh_run_authority")
        consume_run_authority(run_authority, state_root)
        access_origin = thaw(authorities.load_json("access_origin_authority"))
        access_audit_identity = audit_authority_source(authorities.load_bytes("governed_file_access_code").raw, access_origin)
        static_access_probe_identity = _static_access_probes(authorities)
        access_positive, access_positive_receipt = _launch_checked(
            authorities, "runtime_access", run_authority,
            {"vector": "permitted_measured_origin", "path": str(repository / authorities.binding("specification")["path"]), "directory": str(repository)},
            "access_origin_code", disposable_root,
        )
        require(access_positive["status"] == "PASS", "RUNTIME_ACCESS_POSITIVE")
        access_negative, access_negative_receipt = _launch_checked(
            authorities, "runtime_access", run_authority,
            {"vector": "computed_open", "path": str(repository / authorities.binding("specification")["path"]), "directory": str(repository)},
            "access_origin_code", disposable_root,
        )
        require(access_negative == {"status": "BLOCKED", "code": "RUNTIME_ACCESS_ORIGIN_UNAUTHORIZED"}, "RUNTIME_ACCESS_NEGATIVE")
        historical = authorities.load_json("historical_evidence_authority")
        parser_result, parser_receipt = _launch_checked(
            authorities, "historical_parser", run_authority,
            {"physical_path": historical["physical_path"], "logical_evidence_id": historical["logical_evidence_id"], "expected_sha256": historical["sha256"]},
            "historical_parser_code", disposable_root,
        )
        require(parser_result["source_total"] == 753 and parser_result["failed_outcome_count"] == 179, "HISTORICAL_PARSER_ARITHMETIC")
        domain_authorities = thaw(authorities.load_json("domain_authority_map"))["domains"]
        recorder_context = {
            "access_origin": access_origin,
            "run_id": run_authority["run_id"], "run_nonce": run_authority["run_nonce"],
            "specification_commit": authorities.commit, "case_set_identity": case_set_identity,
            "launcher_blob": authorities.load_bytes("process_launch_code").git_blob,
            "python_identity": _hash_file(Path(sys.executable)),
            "recorder_source_id": f"R6-EVENTS-{run_authority['run_id']}",
            "recorder_authority_identity": authorities.load_bytes("recorder_authority").raw_sha256,
            "recorder_reader_identity": authorities.load_json("recorder_authority")["reader_identity"],
            "enforcement_raw_sha256": authorities.load_bytes("r6_enforcement_code").raw_sha256,
            "enforcement_git_blob": authorities.load_bytes("r6_enforcement_code").git_blob,
            "domain_authorities": domain_authorities,
            "validator_status": environment_receipt["status"],
            "mandatory_status": mandatory_receipt["status"],
            "mandatory_paths": [item["path"] for item in mandatory_receipt["tests"]],
            "mandatory_test_authority_identity": authorities.load_bytes("mandatory_test_authority").raw_sha256,
            "mandatory_test_receipt_identity": mandatory_test_semantic_identity,
        }
        recorder_result, recorder_process_receipt = _launch_checked(
            authorities, "event_recorder", run_authority,
            {"case_definitions": definitions, "run_authority": run_authority, "context": recorder_context},
            "r6_enforcement_code", disposable_root,
        )
        events = recorder_result["events"]
        source_receipt = recorder_result["source_receipt"]
        _validate_event_source_schema(authorities, events, source_receipt)
        observations = _derive_observations(events, source_receipt, run_authority, recorder_process_receipt)
        observation_schema = authorities.load_json("observation_schema")
        for index, observation in enumerate(observations):
            validate_json_schema(observation_schema, observation, f"observation[{index}]")
        normalized_observation_identity = semantic_identity(_normalized_observations(observations))
        traceability_identity = validate_traceability(authorities, run_authority["run_id"], events, observations)
        review_receipt = thaw(authorities.load_json("future_review_receipt_fixture"))
        review_issuance_identity = validate_review_receipt(authorities, review_receipt)
        compatibility_claim = thaw(authorities.load_json("compatibility_evidence"))
        compatibility_evidence_identity = validate_compatibility(authorities, compatibility_claim)
        claim_evidence = _claim_evidence(authorities, events, observations)
        document_claim_identity = validate_documents(authorities, claim_evidence)
        document_probe_results = []
        for phrase in ("Parser process isolation is closed.", "Operational capture work is authorized."):
            try:
                validate_document_text(phrase, {})
            except R6AuthorityError as exc:
                document_probe_results.append({"phrase": phrase, "code": exc.code})
        require(len(document_probe_results) == 2, "DOCUMENT_NEGATIVE_PROBE_BYPASS")
        document_negative_probe_identity = semantic_identity(document_probe_results)
        comparison_context = {
            "run_id": run_authority["run_id"],
            "comparator_authority_id": authorities.load_json("comparison_authority")["authority_id"],
            "normalized_observation_identity": normalized_observation_identity,
            "case_definition_identity": case_definition_identity,
            "case_set_identity": case_set_identity,
            "enforcing_code_identity": enforcing_code_identity,
            "schema_set_identity": schema_set_identity,
            "authority_set_identity": authority_set_identity,
            "mandatory_test_semantic_identity": mandatory_test_semantic_identity,
        }
        comparison, comparator_receipt = _launch_checked(
            authorities, "comparator", run_authority,
            {"expectations": expectations, "observations": observations, "context": comparison_context},
            "comparison_engine_code", disposable_root,
        )
        require(comparison["completed"] is True, "COMPARISON_INCOMPLETE")
        require(comparison["terminal_status"] == "MATCHED" and comparison["discrepancy_count"] == 0, "COMPARISON_MISMATCH", json.dumps(comparison["discrepancies"][:20], sort_keys=True))
        validate_json_schema(authorities.load_json("terminal_comparison_receipt_schema"), comparison, "terminal_comparison_receipt")
        normalized_comparison_identity = comparison["normalized_comparison_identity"]
        schema_validation = _schema_validation(authorities)
        kinds = {name: sum(item["kind"] == name for item in definitions["cases"]) for name in ("positive", "mutation")}
        surfaces = {name: sum(item["surface"] == name for item in definitions["cases"]) for name in ("real", "synthetic")}
        base_result = {
            "schema_version": "6.0.0-DRAFT",
            "authority": "R6_GOVERNED_FIXTURE_RESULT_PENDING_INDEPENDENT_REVIEW",
            "phase": phase,
            "total_cases": len(definitions["cases"]), "positive_cases": kinds["positive"], "mutation_cases": kinds["mutation"],
            "real_surface_cases": surfaces["real"], "synthetic_cases": surfaces["synthetic"],
            "meta_verification_cases": sum(bool(item["meta_verification"]) for item in definitions["cases"]),
            "passed": len(definitions["cases"]), "failed": 0, "discrepancies": 0, "cleanup": "PASS",
            "specification_identity": specification_identity,
            "case_definition_identity": case_definition_identity, "case_set_identity": case_set_identity,
            "expectation_identity": expectation_identity, "enforcing_code_identity": enforcing_code_identity,
            "schema_set_identity": schema_set_identity, "authority_set_identity": authority_set_identity,
            "normalized_observation_identity": normalized_observation_identity,
            "normalized_comparison_identity": normalized_comparison_identity,
            "mandatory_test_semantic_identity": mandatory_test_semantic_identity,
            "traceability_identity": traceability_identity, "document_claim_identity": document_claim_identity,
            "review_issuance_identity": review_issuance_identity, "compatibility_evidence_identity": compatibility_evidence_identity,
            "access_audit_identity": access_audit_identity,
            "static_access_probe_identity": static_access_probe_identity,
            "validator_mutation_probe_identity": validator_mutation_probe_identity,
            "document_negative_probe_identity": document_negative_probe_identity,
            "run_id": run_authority["run_id"], "run_nonce_identity": sha256(run_authority["run_nonce"].encode("ascii")),
            "run_authority_identity": semantic_identity(run_authority),
            "parser_execution_receipt_identity": semantic_identity(parser_receipt),
            "comparator_execution_receipt_identity": semantic_identity(comparator_receipt),
            "recorder_execution_receipt_identity": semantic_identity(recorder_process_receipt),
            "event_source_identity": semantic_identity(events), "event_root": source_receipt["append_only_root"],
            "parser_result_identity": semantic_identity(parser_result),
            "comparison_receipt_identity": semantic_identity(comparison),
            "validator_environment_identity": semantic_identity(environment_receipt),
            "runtime_access_positive_receipt_identity": semantic_identity(access_positive_receipt),
            "runtime_access_negative_receipt_identity": semantic_identity(access_negative_receipt),
            "schema_validation": schema_validation,
            "historical_result": parser_result,
            "mandatory_test_receipt": mandatory_receipt,
            "environment_receipt": environment_receipt,
            "run_authority": run_authority,
            "source_receipt": source_receipt,
            "events": events,
            "observations": observations,
            "parser_execution_receipt": parser_receipt,
            "comparator_execution_receipt": comparator_receipt,
            "recorder_execution_receipt": recorder_process_receipt,
            "comparison_receipt": comparison,
        }
        terminal_body = {
            "schema_version": "6.0.0-DRAFT", "run_id": run_authority["run_id"], "phase": phase,
            "case_set_identity": case_set_identity, "normalized_observation_identity": normalized_observation_identity,
            "normalized_comparison_identity": normalized_comparison_identity, "event_root": source_receipt["append_only_root"],
            "parser_receipt_identity": semantic_identity(parser_receipt), "comparator_receipt_identity": semantic_identity(comparator_receipt),
            "cleanup": "PASS", "completed": True, "discrepancy_count": 0,
            "mandatory_test_semantic_identity": mandatory_test_semantic_identity,
            "issued_timestamp": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        base_result["terminal_receipt_identity"] = semantic_identity(terminal_body)
        base_result["terminal_receipt"] = {**terminal_body, "receipt_identity": base_result["terminal_receipt_identity"]}
        validate_json_schema(authorities.load_json("terminal_run_receipt_schema"), base_result["terminal_receipt"], "terminal_run_receipt")
        if phase == "candidate":
            base_result["reconciliation"] = "CANDIDATE_COMPLETE"
            base_result["reconciliation_receipt"] = None
        else:
            require(candidate_receipt is not None, "CANDIDATE_RECEIPT_REQUIRED")
            candidate = _load_candidate(candidate_receipt)
            fresh_view = {key: value for key, value in base_result.items() if key not in {"reconciliation", "reconciliation_receipt"}}
            reconciliation = _reconcile(candidate, fresh_view)
            base_result["reconciliation"] = "MATCHED"
            base_result["reconciliation_receipt"] = reconciliation
        validate_json_schema(authorities.load_json("fixture_results_schema"), base_result, "fixture_results_R6")
        cleanup = "PASS"
        return base_result
    finally:
        if disposable_root.exists():
            shutil.rmtree(disposable_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--authority-ref", required=True)
    parser.add_argument("--physical-root", type=Path, required=True)
    parser.add_argument("--phase", choices=("candidate", "fresh"), required=True)
    parser.add_argument("--candidate-receipt", type=Path)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--worktree-mode", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run(args.repository.resolve(), args.authority_ref, args.physical_root.resolve(), args.phase, args.candidate_receipt, args.state_root.resolve(), worktree_mode=args.worktree_mode)
    except BaseException as exc:
        code = getattr(exc, "code", type(exc).__name__)
        sys.stderr.write(json.dumps({"status": "FAILED", "code": code, "detail": str(exc)}, sort_keys=True) + "\n")
        return 2
    write_disposable_binary(args.output, canonical_json_bytes(result), exclusive=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
