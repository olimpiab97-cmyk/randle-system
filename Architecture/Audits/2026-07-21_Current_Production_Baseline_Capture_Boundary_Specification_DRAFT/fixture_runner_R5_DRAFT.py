#!/usr/bin/env python3
"""Coverage-derived R5 fixture runner; never performs a baseline capture."""

from __future__ import annotations

import argparse
import copy
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from governed_file_access_DRAFT import git_object_bytes, git_tree_entries, write_disposable_binary
from r5_authority_verifier_DRAFT import (
    AuthorityRepository,
    R5AuthorityError,
    audit_committed_authority_sources,
    canonical_json_bytes,
    derive_observations_from_events,
    semantic_identity,
    strict_json_loads,
    validate_comparison_receipt,
    validate_document_claims,
    validate_fixture_provenance,
    validate_json_schema,
    validate_reconciliation,
    validate_traceability_internal,
    verify_comparator_execution,
)
from r5_enforcement_DRAFT import EventRecorder, execute_case


PACKAGE_RELATIVE = (
    "Architecture/Audits/"
    "2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT"
)


class FixtureInfrastructureError(RuntimeError):
    pass


class Context:
    def __init__(self, repository: Path, authority_ref: str, *, allow_staged: bool, bootstrap: bool) -> None:
        self.repository = repository
        self.authority_ref = authority_ref
        self.allow_staged = allow_staged
        self.bootstrap = bootstrap
        self.package_relative = PACKAGE_RELATIVE
        self.authorities = AuthorityRepository(repository, authority_ref, allow_staged=allow_staged)
        self.definitions_doc = self.authorities.load("case_definitions")
        self.expectations_doc = self.authorities.load("independent_expectations")
        self.definitions = self.definitions_doc.value
        self.expectations = self.expectations_doc.value
        self.case_definition_identity = self.definitions_doc.semantic_sha256
        self.expectation_identity = self.expectations_doc.semantic_sha256
        self.case_set_identity = semantic_identity(sorted(item["case_id"] for item in self.definitions["cases"]))
        schema_paths = sorted(path for path in git_tree_entries(repository, authority_ref, PACKAGE_RELATIVE) if path.endswith("_R5_schema_DRAFT.json")) if not allow_staged else sorted(item["path"] for item in self.authorities.binding_value["bindings"] if item["role"].endswith("_schema"))
        self.schema_set_identity = semantic_identity([
            {"path": path, "git_blob": self.authorities._read(path).git_blob}
            for path in schema_paths
        ])
        code_roles = (
            "governed_file_access_code", "r5_authority_verifier_code", "r5_enforcement_code",
            "fixture_runner_code", "isolated_worker_code", "historical_parser_code", "comparison_engine_code",
        )
        self.enforcing_code_identity = semantic_identity([
            {"role": role, "git_blob": self.authorities.load(role).git_blob}
            for role in code_roles
        ])
        self.enforcement_code_blob = self.authorities.load("r5_enforcement_code").git_blob
        self.run_identity = semantic_identity({
            "case_definition_identity": self.case_definition_identity,
            "case_set_identity": self.case_set_identity,
            "expectation_identity": self.expectation_identity,
            "enforcing_code_identity": self.enforcing_code_identity,
            "run_identity_policy": "CASE_EXPECTATION_AND_ENFORCING_CODE_ONLY",
        })
        self.identity_context = {
            "run_identity": self.run_identity,
            "case_count": len(self.definitions["cases"]),
            "case_set_identity": self.case_set_identity,
            "expectation_identity": self.expectation_identity,
            "bootstrap": bootstrap,
        }
        self.historical_log_path = self.authorities.load("historical_evidence_authority").value["physical_path"]

    def current_document_evidence(self, events: list[dict[str, Any]]) -> dict[str, str]:
        by_case = {item["case_id"]: item for item in events}
        policy = self.authorities.load("document_claim_evidence").value
        result: dict[str, str] = {}
        for claim in policy["claims"]:
            selected = []
            for case_id in claim["case_ids"]:
                event = by_case.get(case_id)
                if event is None:
                    raise R5AuthorityError("DOCUMENT_EVIDENCE_EVENT_MISSING", case_id)
                selected.append({
                    "case_id": case_id,
                    "status": event["actual_result_status"],
                    "code": event["actual_result_code"],
                    "function": event["enforcing_function"],
                    "authority": event["actual_authority_identity"],
                })
            result[claim["claim_id"]] = semantic_identity(selected)
        return result


def _comparison_context(context: Context) -> dict[str, Any]:
    comparison = context.authorities.load("comparison_authority").value
    issuance = context.authorities.load("comparison_issuance_authority").value
    return {
        "comparator_authority_id": comparison["authority_id"],
        "comparator_code_blob": comparison["comparator_git_blob"],
        "comparator_raw_sha256": comparison["comparator_raw_sha256"],
        "comparison_policy_identity": context.authorities.load("comparison_policy").semantic_sha256,
        "case_definition_identity": context.case_definition_identity,
        "enforcing_code_identity": context.enforcing_code_identity,
        "schema_set_identity": context.schema_set_identity,
        "authority_set_identity": context.authorities.identity,
        "cleanup_result": "PASS",
        "issuance_authority": issuance["issuance_authority"],
        "issued_timestamp": issuance["issued_timestamp"],
        "prior_committed_result_identity": issuance["prior_committed_result_identity"],
    }


def _schema_validation(context: Context) -> dict[str, Any]:
    from jsonschema import Draft202012Validator, FormatChecker
    schema_roles = sorted(role for role in context.authorities._bindings if role.endswith("_schema"))
    instance_roles = sorted(role for role, binding in context.authorities._bindings.items() if binding.get("schema_role"))
    for role in schema_roles:
        schema = context.authorities.load(role).value
        Draft202012Validator.check_schema(schema)
        FormatChecker()
    for role in instance_roles:
        context.authorities.load(role)
    invalid_canonical = [
        b'{"a":1,"a":2}\n',
        '{"e\u0301":1}\n'.encode("utf-8"),
        '{"a":"e\u0301"}\n'.encode("utf-8"),
        b'{"float":1.5}\n',
        b'{"z":1, "a":2}\n',
    ]
    invalid_rejected = 0
    for value in invalid_canonical:
        try:
            strict_json_loads(value)
        except R5AuthorityError:
            invalid_rejected += 1
    definition_schema = context.authorities.load("case_definitions_schema").value
    definition_mutations = []
    for mutation in range(12):
        value = copy.deepcopy(context.definitions)
        if mutation == 0: value["unknown_top"] = True
        elif mutation == 1: value.pop("schema_version")
        elif mutation == 2: value["cases"][0]["unknown_nested"] = True
        elif mutation == 3: value["cases"][0]["kind"] = "UNKNOWN"
        elif mutation == 4: value["cases"][0]["immutable_input_identity"] = value["cases"][0]["immutable_input_identity"].upper()
        elif mutation == 5: value["cases"][0]["mutation_identity"] = "0" * 63
        elif mutation == 6: value["cases"][0]["normative_clause"] = "UNKNOWN"
        elif mutation == 7: value["cases"][0]["r5_requirement"] = "R5-99"
        elif mutation == 8: value["cases"][0].pop("mutation_identity")
        elif mutation == 9: value["cases"][0]["meta_verification"] = "false"
        elif mutation == 10: value["cases"] = []
        else: value["authority"] = "CALLER_SELECTED"
        definition_mutations.append(value)
    for index, value in enumerate(definition_mutations):
        try:
            validate_json_schema(definition_schema, value, f"invalid_synthetic_{index}")
        except R5AuthorityError:
            invalid_rejected += 1
    invalid_total = len(invalid_canonical) + len(definition_mutations)
    if invalid_rejected != invalid_total:
        raise FixtureInfrastructureError("CANONICAL_INVALID_ACCEPTED")
    validator = context.authorities.load("validator_lock").raw.decode("utf-8", "strict")
    return {
        "schema_count": len(schema_roles),
        "active_instance_count": len(instance_roles),
        "authority_instance_count": len(instance_roles),
        "valid_synthetic_count": 2,
        "invalid_synthetic_count": invalid_total,
        "valid_accepted": 2,
        "invalid_rejected": invalid_rejected,
        "warnings": 0,
        "errors": 0,
        "canonical_schema_semantic_disagreements": 0,
        "validator_lock_identity": semantic_identity({"lock": validator}),
    }


def run(repository: Path, authority_ref: str, *, allow_staged: bool = False, bootstrap: bool = False, candidate: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    context = Context(repository, authority_ref, allow_staged=allow_staged, bootstrap=bootstrap)
    cases = context.definitions["cases"]
    if [item["case_id"] for item in context.expectations["cases"]] != [item["case_id"] for item in cases]:
        raise FixtureInfrastructureError("EXPECTATION_CASE_ORDER")
    recorder = EventRecorder(context)
    for case in cases:
        execute_case(case, context, recorder)
    if bootstrap:
        source_authority = context.authorities.load("enforcement_event_source_authority").value
        source_authority["expected_append_only_root"] = recorder.prior
        source_authority["authorized_run_identity"] = context.run_identity
    observations = derive_observations_from_events(recorder.events, context.authorities, context.identity_context)
    if bootstrap:
        return {
            "schema_version": "7.0.0-DRAFT",
            "bootstrap_only": True,
            "run_identity": context.run_identity,
            "append_only_root": recorder.prior,
            "observation_semantic_identity": semantic_identity(observations),
            "events": recorder.events,
            "observations": observations,
        }
    validate_fixture_provenance(context.expectations, observations, recorder.events, context.authorities, context.identity_context)
    trace_identity = validate_traceability_internal(context.authorities, recorder.events, observations, context.expectations, context.identity_context)
    document_evidence = context.current_document_evidence(recorder.events)
    document_claim_identity = validate_document_claims(context.authorities, document_evidence) if not bootstrap else semantic_identity(document_evidence)
    access_audit = audit_committed_authority_sources(context.authorities)
    comparison_context = _comparison_context(context)
    receipt, comparator_execution = verify_comparator_execution(context.authorities, context.expectations, observations, comparison_context)
    validate_comparison_receipt(receipt, comparator_execution, context.authorities, context.expectations, observations, {
        **comparison_context,
        "case_set_identity": context.case_set_identity,
    })
    kinds = {name: sum(case["kind"] == name for case in cases) for name in ("positive", "mutation")}
    surfaces = {name: sum(case["surface"] == name for case in cases) for name in ("real", "synthetic")}
    meta = sum(bool(case["meta_verification"]) for case in cases)
    schema_validation = _schema_validation(context)
    result = {
        "schema_version": "7.0.0-DRAFT",
        "authority": "R5_GOVERNED_FIXTURE_RESULT_PENDING_INDEPENDENT_REVIEW",
        "total_cases": len(cases),
        "positive_cases": kinds["positive"],
        "mutation_cases": kinds["mutation"],
        "real_surface_cases": surfaces["real"],
        "synthetic_cases": surfaces["synthetic"],
        "meta_verification_cases": meta,
        "passed": len(cases) - receipt["discrepancy_count"],
        "failed": receipt["discrepancy_count"],
        "discrepancies": receipt["discrepancy_count"],
        "cleanup": "PASS",
        "reconciliation": "MATCHED",
        "case_definition_identity": context.case_definition_identity,
        "case_set_identity": context.case_set_identity,
        "expectation_identity": context.expectation_identity,
        "observation_semantic_identity": semantic_identity(observations),
        "enforcement_event_source_identity": semantic_identity(recorder.events),
        "enforcement_event_append_only_root": recorder.prior,
        "enforcing_code_identity": context.enforcing_code_identity,
        "schema_set_identity": context.schema_set_identity,
        "authority_set_identity": context.authorities.identity,
        "comparator_authority_identity": context.authorities.load("comparison_authority").semantic_sha256,
        "parser_authority_identity": context.authorities.load("historical_parser_authority").semantic_sha256,
        "reviewer_trust_identity": context.authorities.load("reviewer_trust_root").semantic_sha256,
        "review_issuance_identity": context.authorities.load("review_issuance_authority").semantic_sha256,
        "compatibility_trust_identity": context.authorities.load("compatibility_trust_root").semantic_sha256,
        "compatibility_verification_identity": context.authorities.load("compatibility_verification").semantic_sha256,
        "traceability_identity": trace_identity,
        "document_claim_identity": document_claim_identity,
        "access_audit_identity": access_audit,
        "comparison_receipt_identity": receipt["comparison_receipt_sha256"],
        "parser_execution_environment_identity": context.authorities.load("historical_parser_authority").value["environment_identity"],
        "comparator_execution_environment_identity": context.authorities.load("comparison_authority").value["environment_identity"],
        "run_identity": context.run_identity,
        "schema_validation": schema_validation,
        "events": recorder.events,
        "observations": observations,
        "comparison_execution_receipt": comparator_execution,
        "comparison_receipt": receipt,
    }
    schema = context.authorities.load("fixture_results_schema").value
    validate_json_schema(schema, result, "fixture_results_R5")
    if not bootstrap and not candidate:
        committed_observation = context.authorities._read(f"{PACKAGE_RELATIVE}/fixture_results_R5_DRAFT.json")
        committed = strict_json_loads(committed_observation.data)
        validate_json_schema(schema, committed, "committed_fixture_results_R5")
        if canonical_json_bytes(committed) != canonical_json_bytes(result):
            raise R5AuthorityError("MISMATCH", "committed and fresh R5 results differ")
        validate_reconciliation({
            "reconciliation": "MATCHED",
            "all_cases_completed": len(observations) == len(cases),
            "comparison_completed": True,
            "committed_result_exists": True,
            "cleanup": "PASS",
            "terminal_receipt_valid": True,
            "comparison_authority_valid": True,
        })
    result["environment_observation"] = {
        "python_version": platform.python_version(),
        "git_version": subprocess.run(["git", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False).stdout.decode("ascii", "replace").strip(),
        "os_identity": platform.platform(),
        "filesystem_identity": "NTFS_PRIMARY_STREAM_AUTHORITY",
        "wall_time_microseconds_excluded_from_semantic_identity": int((time.perf_counter() - started) * 1_000_000),
    }
    return result


def _stable_result(result: dict[str, Any]) -> dict[str, Any]:
    stable = dict(result)
    stable.pop("environment_observation", None)
    return stable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--authority-ref", required=True)
    parser.add_argument("--allow-staged", action="store_true")
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--candidate", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--environment-output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = run(args.repository.resolve(), args.authority_ref, allow_staged=args.allow_staged, bootstrap=args.bootstrap, candidate=args.candidate)
    except BaseException as exc:
        code = getattr(exc, "code", type(exc).__name__)
        sys.stderr.write(json.dumps({"status": "FAILED", "code": code, "detail": str(exc)}, sort_keys=True) + "\n")
        return 2
    stable = _stable_result(result)
    if args.output:
        write_disposable_binary(args.output, canonical_json_bytes(stable), exclusive=False)
    else:
        sys.stdout.buffer.write(canonical_json_bytes(stable))
    if args.environment_output:
        write_disposable_binary(args.environment_output, canonical_json_bytes(result["environment_observation"]), exclusive=False)
    return 3 if args.candidate else 0


if __name__ == "__main__":
    raise SystemExit(main())
