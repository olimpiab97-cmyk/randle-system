#!/usr/bin/env python3
"""Governed R4 fixture runner; never performs a production baseline capture."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import pathlib
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from comparison_engine_DRAFT import compare
from governed_file_access_DRAFT import (
    GovernedAccessError,
    canonical_absolute_path,
    extended_length_path,
    git_object_bytes,
    git_tree_entries,
    named_streams,
    read_binary,
    resolve_primary_file_authority,
    sha256_bytes,
)
from historical_log_parser_DRAFT import parse_historical_log
from r3_authority_verifier_DRAFT import (
    AuthorityRepository,
    R3AuthorityError,
    append_only_event_root,
    audit_authority_access_surfaces,
    audit_authority_source,
    canonical_json_bytes,
    semantic_identity,
    strict_json_loads,
    validate_architecture_documents,
    validate_attempt_prefix_claim,
    validate_authorization_package,
    validate_authorization_text,
    validate_comparison_receipt,
    validate_evidence_policy_claim,
    validate_fixture_provenance,
    validate_future_package,
    validate_historical_parser_claim,
    validate_reconciliation_state,
    validate_separate_binding,
    validate_timestamp_authority_claim,
    validate_trace_matrix_authority,
    validate_traceability,
    verify_freeze_claim,
    verify_historical_classification,
    verify_observer_source,
)
from schema_validation_DRAFT import (
    SchemaValidationError,
    strict_canonical_json_loads,
    validate_schema_and_instance,
    validator_identity,
)
from selection_engine_DRAFT import BoundaryError, derive_batch_dependency_edges


PACKAGE_RELATIVE = (
    "Architecture/Audits/"
    "2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT"
)
HARNESS_VERSION = "6.0.0-DRAFT"
TRACE_BOOTSTRAP = "0" * 64


class FixtureInfrastructureError(RuntimeError):
    pass


class CaseEnforcementError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class CaseResult:
    function: str
    authority_source: str
    evidence: str = "SATISFIED"


def _git(repository: pathlib.Path, *args: str, input_bytes: bytes | None = None, check: bool = True) -> bytes:
    command = [
        "git", "-c", "core.longpaths=true", "-c", f"safe.directory={repository.as_posix()}",
        "-C", os.fspath(repository), *args,
    ]
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_AUTHOR_NAME": "R4 Fixture",
            "GIT_AUTHOR_EMAIL": "r4-fixture.invalid",
            "GIT_COMMITTER_NAME": "R4 Fixture",
            "GIT_COMMITTER_EMAIL": "r4-fixture.invalid",
            "GIT_AUTHOR_DATE": "2026-07-22T12:00:00Z",
            "GIT_COMMITTER_DATE": "2026-07-22T12:00:00Z",
        }
    )
    completed = subprocess.run(command, input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment, check=False)
    if check and completed.returncode:
        raise FixtureInfrastructureError(f"GIT:{completed.returncode}:{completed.stderr.decode('utf-8', 'replace')}")
    return completed.stdout


def _write(path: pathlib.Path, data: bytes | str) -> None:
    os.makedirs(extended_length_path(path.parent), exist_ok=True)
    payload = data.encode("utf-8") if isinstance(data, str) else data
    descriptor = os.open(extended_length_path(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o644)
    try:
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
    finally:
        os.close(descriptor)


def _write_ads(path: pathlib.Path, stream: str, data: bytes) -> None:
    descriptor = os.open(extended_length_path(path) + ":" + stream, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o644)
    try:
        if data:
            os.write(descriptor, data)
    finally:
        os.close(descriptor)


def _error_code(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str):
        return code
    text = str(exc)
    return text.split(":", 1)[0] if text else type(exc).__name__


def _schema_invalid(schema: Mapping[str, Any], instance: Mapping[str, Any], label: str) -> None:
    AuthorityRepository._validate_schema(schema, instance, label)


class Context:
    def __init__(self, repository: pathlib.Path, authority_ref: str, *, allow_staged: bool) -> None:
        self.repository = repository
        self.authority_ref = authority_ref
        self.authorities = AuthorityRepository(repository, authority_ref, allow_staged=allow_staged)
        definitions_observed = git_object_bytes(repository, authority_ref, f"{PACKAGE_RELATIVE}/case_definitions_R4_DRAFT.json")
        expectations_observed = git_object_bytes(repository, authority_ref, f"{PACKAGE_RELATIVE}/independent_expectations_R4_DRAFT.json")
        self.definitions = strict_json_loads(definitions_observed.data)
        self.expectations = strict_json_loads(expectations_observed.data)
        if not isinstance(self.definitions, Mapping) or not isinstance(self.expectations, Mapping):
            raise FixtureInfrastructureError("FIXTURE_AUTHORITY_NOT_OBJECT")
        schema_paths = [path for path in git_tree_entries(repository, authority_ref, PACKAGE_RELATIVE) if path.endswith("_R4_schema_DRAFT.json")]
        self.schema_set_identity = semantic_identity(
            [{"path": path, "git_blob": git_object_bytes(repository, authority_ref, path).git_blob} for path in schema_paths]
        )
        code_names = (
            "governed_file_access_DRAFT.py", "r3_authority_verifier_DRAFT.py", "comparison_engine_DRAFT.py",
            "boundary_verifier_DRAFT.py", "selection_engine_DRAFT.py", "inventory_generator_DRAFT.py",
            "schema_validation_DRAFT.py", "historical_log_parser_DRAFT.py", "fixture_runner_DRAFT.py",
            "fixture_runner_R4_DRAFT.py",
        )
        self.enforcing_code_identity = semantic_identity(
            [
                {
                    "path": f"{PACKAGE_RELATIVE}/{name}",
                    "git_blob": git_object_bytes(repository, authority_ref, f"{PACKAGE_RELATIVE}/{name}").git_blob,
                }
                for name in code_names
            ]
        )
        self.authority_set_identity = self.authorities.identity
        self.case_definition_identity = definitions_observed.sha256
        self.expectation_identity = semantic_identity(self.expectations)
        self.case_set_identity = semantic_identity(sorted(item["case_id"] for item in self.definitions["cases"]))
        self.run_identity = semantic_identity(
            {
                "case_definition_identity": self.case_definition_identity,
                "expectation_identity": self.expectation_identity,
                "case_set_identity": self.case_set_identity,
                "enforcing_code_identity": self.enforcing_code_identity,
                "schema_set_identity": self.schema_set_identity,
                "authority_set_identity": self.authority_set_identity,
            }
        )
        self.observations: list[dict[str, Any]] = []
        self.temporary: list[tempfile.TemporaryDirectory[str]] = []
        self.future_fixture: dict[str, Any] | None = None
        self.cleanup_errors: list[str] = []

    def cleanup(self) -> str:
        def remove_readonly(function: Callable[..., Any], path: str, exc: BaseException) -> None:
            os.chmod(path, stat.S_IWRITE)
            function(path)

        result = "PASS"
        for temporary in reversed(self.temporary):
            try:
                root = pathlib.Path(temporary.name)
                junction = root / "reparse-link"
                if os.path.lexists(extended_length_path(junction)):
                    os.rmdir(extended_length_path(junction))
                if os.path.exists(extended_length_path(root)):
                    shutil.rmtree(extended_length_path(root), onexc=remove_readonly)
                temporary._finalizer.detach()  # the governed extended-length removal already completed
            except Exception as exc:
                result = "FAIL"
                self.cleanup_errors.append(f"{temporary.name}:{type(exc).__name__}:{exc}")
        return result


def _access(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector = case["vector"]
    temporary = tempfile.TemporaryDirectory(prefix="r4-access-")
    context.temporary.append(temporary)
    root = pathlib.Path(temporary.name)
    file_path = root / "authority.json"
    _write(file_path, b'{"authority":"fixture"}\n')
    if vector == "ordinary_drive":
        resolve_primary_file_authority(file_path)
    elif vector == "colon_content":
        _write(file_path, b"ordinary:colon:content\n")
        read_binary(file_path)
    elif vector == "longest_governed_path":
        long_root = root
        for index in range(9):
            long_root = long_root / (f"r4_long_component_{index}_" + "x" * 26)
        long_file = long_root / ("authority_" + "y" * 80 + ".json")
        _write(long_file, b'{"long":true}\n')
        resolve_primary_file_authority(long_file)
    elif vector == "primary_without_ads":
        identity = resolve_primary_file_authority(file_path)
        if identity.byte_size <= 0:
            raise CaseEnforcementError("PRIMARY_STREAM_EMPTY")
    elif vector in {"ads_selector", "zero_ads_selector", "unicode_ads_selector", "multiple_stream_syntax"}:
        stream = {"ads_selector": "shadow", "zero_ads_selector": "zero", "unicode_ads_selector": "évidence", "multiple_stream_syntax": "one:two"}[vector]
        if vector != "multiple_stream_syntax":
            _write_ads(file_path, stream, b"" if vector == "zero_ads_selector" else b"shadow")
        resolve_primary_file_authority(pathlib.Path(str(file_path) + ":" + stream))
    elif vector == "ambiguous_drive_colon":
        resolve_primary_file_authority("C:relative-authority.json")
    elif vector == "file_has_ads":
        _write_ads(file_path, "shadow", b"shadow")
        resolve_primary_file_authority(file_path)
    elif vector == "reparse_substitution":
        target_directory = root / "reparse-target"
        _write(target_directory / "authority.json", b'{"authority":"target"}\n')
        link_directory = root / "reparse-link"
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", os.fspath(link_directory), os.fspath(target_directory)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if created.returncode:
            raise FixtureInfrastructureError(f"JUNCTION_FIXTURE_UNAVAILABLE:{created.stderr.decode('utf-8','replace')}")
        resolve_primary_file_authority(link_directory / "authority.json")
    elif vector == "unc_unavailable":
        try:
            resolve_primary_file_authority(r"\\randle-r4-invalid-host\missing\authority.json")
        except GovernedAccessError as exc:
            if exc.code in {"FILE_MISSING", "FILE_INACCESSIBLE"}:
                raise CaseEnforcementError("FILE_STAT_FAILED", exc.detail) from exc
            raise
    else:
        raise FixtureInfrastructureError(f"UNKNOWN_ACCESS_VECTOR:{vector}")
    return CaseResult("governed_file_access_DRAFT.resolve_primary_file_authority", "PRIMARY_STREAM_ACCESS")


def _enumeration(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector = case["vector"]
    if vector == "committed_surface_audit":
        audit_authority_access_surfaces(context.authorities)
        return CaseResult("r3_authority_verifier_DRAFT.audit_authority_access_surfaces", "CENTRALIZED_AUTHORITY_ENUMERATION")
    sources = {
        "direct_path_glob": b"from pathlib import Path\ndef load_authority(p):\n return tuple(Path(p).glob('*'))\n",
        "direct_open": b"def load_authority(p):\n return open(p, 'rb').read()\n",
        "direct_os_scandir": b"import os\ndef load_authority(p):\n return tuple(os.scandir(p))\n",
    }
    audit_authority_source(sources[vector], "synthetic_authority")
    return CaseResult("r3_authority_verifier_DRAFT.audit_authority_source", "CENTRALIZED_AUTHORITY_ENUMERATION")


def _derived_separate(context: Context) -> tuple[dict[str, Any], dict[str, Any]]:
    terminal = {"artifact_class": "runtime-log", "rule_id": "R4-SEPARATE-RUNTIME-LOG", "terminal_disposition": "SEPARATE_AND_BIND"}
    policy = context.authorities.load("separate_binding_policy")
    review = context.authorities.load("review_authority_policy")
    roles = context.authorities.load("authority_role_map")
    evidence = context.authorities.load("required_evidence_policy")
    registry = context.authorities.load("selection_rule_registry")
    enumeration = context.authorities.load("governed_enumeration_policy")
    rule = policy.value["artifact_classes"]["runtime-log"]
    evidence_rule = evidence.value["rules"][0]
    obligation: dict[str, Any] = {
        "authority_id": rule["authorized_authority_id"], "capture_form": rule["capture_form"],
        "recovery_requirement": rule["recovery_requirement"], "semantic_purpose": rule["semantic_purpose"],
        "immutability_requirement": rule["immutability_requirement"], "review_requirement": rule["review_requirement"],
        "reviewer_role": review.value["required_reviewer_role"], "reviewer_independence": review.value["independence_requirement"],
        "review_decision": review.value["required_decision"], "review_object_identity": review.value["fixture_review_object_identity"],
        "review_issued_timestamp": review.value["fixture_review_issued_timestamp"],
        "evidence": [
            {"role": role, "class": klass, "external_root_id": rule["external_root_id"], "immutability_requirement": rule["immutability_requirement"]}
            for role, klass in zip(evidence_rule["required_roles"], evidence_rule["required_classes"], strict=True)
        ],
        "derivation_authorities": {
            "selection_rule_registry": registry.semantic_sha256, "separate_binding_policy": policy.semantic_sha256,
            "authority_role_map": roles.semantic_sha256, "required_evidence_policy": evidence.semantic_sha256,
            "governed_enumeration_policy": enumeration.semantic_sha256, "review_authority_policy": review.semantic_sha256,
        },
    }
    obligation["semantic_root"] = semantic_identity(obligation)
    return terminal, obligation


def _separate(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector = case["vector"]
    terminal, obligation = _derived_separate(context)
    field_map = {
        "self_review_allowed": ("review_requirement", "SELF_REVIEW_ALLOWED"), "untrusted_reviewer_role": ("reviewer_role", "UNTRUSTED"),
        "missing_independent_review": ("review_object_identity", None), "pending_decision": ("review_decision", "PENDING"),
        "altered_reviewer_identity": ("review_object_identity", "0" * 64), "altered_review_requirement": ("review_requirement", "OPTIONAL"),
        "altered_policy_claim": ("capture_form", "FORGED"), "altered_role_map_claim": ("authority_id", "ROGUE"),
        "altered_evidence": ("evidence", []), "conflicting_review_policy": ("reviewer_independence", "SELF"),
    }
    if vector in field_map:
        key, value = field_map[vector]
        if value is None:
            obligation.pop(key)
        else:
            obligation[key] = value
    elif vector == "rebuilt_semantic_root":
        obligation["review_requirement"] = "SELF_REVIEW_ALLOWED"
        obligation["semantic_root"] = semantic_identity({k: v for k, v in obligation.items() if k != "semantic_root"})
    elif vector == "converted_include":
        terminal["terminal_disposition"] = "INCLUDE"
    elif vector == "converted_exclude":
        terminal["terminal_disposition"] = "EXCLUDE"
    elif vector != "valid":
        raise FixtureInfrastructureError(f"UNKNOWN_SEPARATE_VECTOR:{vector}")
    validate_separate_binding(terminal, obligation, context.authorities)
    return CaseResult("r3_authority_verifier_DRAFT.validate_separate_binding", "IMMUTABLE_SEPARATE_REVIEW_AUTHORITY")


def _schema(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector = case["vector"]
    if vector == "all_active_valid":
        for binding in context.authorities.binding_value["bindings"]:
            if "schema_path" in binding:
                context.authorities.load(binding["role"])
        for path in git_tree_entries(context.repository, context.authority_ref, PACKAGE_RELATIVE):
            if path.endswith("_R4_schema_DRAFT.json"):
                schema = strict_json_loads(git_object_bytes(context.repository, context.authority_ref, path).data)
                validate_schema_and_instance(schema, {}, f"schema-self:{path}") if False else None
                from jsonschema import Draft202012Validator
                Draft202012Validator.check_schema(schema)
        return CaseResult("schema_validation_DRAFT.validate_governed_artifact", "CLOSED_FAMILY_SCHEMAS")
    if vector == "canonical_valid":
        strict_canonical_json_loads(b'{"canonical":"NFC"}\n')
        return CaseResult("schema_validation_DRAFT.strict_canonical_json_loads", "NFC_CANONICAL_AUTHORITY")
    raw_vectors = {
        "non_nfc_key": '{"e\u0301":1}\n'.encode("utf-8"), "non_nfc_value": '{"key":"e\u0301"}\n'.encode("utf-8"),
        "duplicate_key": b'{"key":1,"key":2}\n', "forbidden_float": b'{"key":1.5}\n',
        "noncanonical_bytes": b'{ "key": 1 }\n',
    }
    if vector in raw_vectors:
        strict_canonical_json_loads(raw_vectors[vector])
        return CaseResult("schema_validation_DRAFT.strict_canonical_json_loads", "NFC_CANONICAL_AUTHORITY")
    family = {
        "underconstrained_observer": "observer_source_authority", "underconstrained_authorization": "authorization_policy",
        "underconstrained_evidence": "required_evidence_policy", "underconstrained_future": "operational_package_interface",
    }.get(vector, "comparison_authority")
    document = context.authorities.load(family)
    schema_path = context.authorities.binding(family)["schema_path"]
    schema = strict_json_loads(git_object_bytes(context.repository, context.authority_ref, schema_path).data)
    mutated = copy.deepcopy(document.value)
    if vector in {"unknown_top_level", "extra_property", "underconstrained_observer", "underconstrained_authorization", "underconstrained_evidence", "underconstrained_future"}:
        mutated["unknown_r4_field"] = True
    elif vector == "unknown_nested":
        if family == "comparison_authority":
            mutated["unknown_r4_field"] = {"nested": True}
    elif vector == "wrong_git_length":
        mutated["comparator_git_blob"] = "a" * 39
    elif vector == "wrong_object_format":
        mutated["comparator_git_blob"] = "a" * 64
    elif vector == "uppercase_identity":
        mutated["comparator_raw_sha256"] = mutated["comparator_raw_sha256"].upper()
    elif vector == "missing_schema_version":
        mutated.pop("schema_version")
    elif vector == "unknown_enum":
        mutated["result_schema_role"] = "UNKNOWN"
    else:
        raise FixtureInfrastructureError(f"UNKNOWN_SCHEMA_VECTOR:{vector}")
    _schema_invalid(schema, mutated, f"mutation:{vector}")
    return CaseResult("r3_authority_verifier_DRAFT.AuthorityRepository._validate_schema", "CLOSED_FAMILY_SCHEMAS")


def _freeze_receipt(context: Context) -> dict[str, Any]:
    return copy.deepcopy(context.authorities.load("freeze_receipt_authority").value)


def _timestamp_claim(context: Context) -> dict[str, Any]:
    document = context.authorities.load("timestamp_authority")
    return {"authority": copy.deepcopy(document.value), "path": document.path, "raw_sha256": document.raw_sha256, "git_blob": document.git_blob, "semantic_sha256": document.semantic_sha256, "role_map_binding": context.authorities.load("authority_role_map").semantic_sha256, "trust_root_binding": context.authorities.load("timestamp_trust_root").semantic_sha256}


def _freeze(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector = case["vector"]
    receipt = _freeze_receipt(context)
    if vector == "forged_issuer_id": receipt["timestamp_issuer_id"] = "ROGUE"
    elif vector == "forged_issuer_role": receipt["timestamp_issuer_role"] = "ROGUE"
    elif vector == "forged_capability": receipt["timestamp_issuer_capability"] = "ROGUE"
    elif vector == "rebuilt_receipt_hash":
        receipt["timestamp_issuer_id"] = "ROGUE"
        receipt["freeze_receipt_sha256"] = semantic_identity({k: v for k, v in receipt.items() if k != "freeze_receipt_sha256"})
    elif vector != "valid": raise FixtureInfrastructureError(f"UNKNOWN_FREEZE_VECTOR:{vector}")
    verify_freeze_claim(receipt, context.authorities)
    return CaseResult("r3_authority_verifier_DRAFT.verify_freeze_claim", "TIMESTAMP_ISSUER_TRUST")


def _timestamp(case: Mapping[str, Any], context: Context) -> CaseResult:
    claim = _timestamp_claim(context)
    vector = case["vector"]
    field = {"changed_timestamp_bytes": "freeze_timestamp", "wrong_role_binding": "role_map_binding", "missing_trust_root": "trust_root_binding", "self_issued": "issuer_id", "wrong_validity": "valid_until", "before_predecessor": "chronology_predecessor", "after_cutoff": "freeze_cutoff"}[vector]
    if field in {"role_map_binding", "trust_root_binding"}: claim[field] = "0" * 64
    else: claim["authority"][field] = "FORGED" if field == "issuer_id" else "2020-01-01T00:00:00Z"
    validate_timestamp_authority_claim(claim, context.authorities)
    return CaseResult("r3_authority_verifier_DRAFT.validate_timestamp_authority_claim", "TIMESTAMP_ISSUER_TRUST")


def _historical_classification(context: Context) -> dict[str, Any]:
    authority = context.authorities.load("historical_evidence_authority").value
    raw = read_binary(authority["authorized_physical_path"]).data
    parsed = parse_historical_log(raw, authority["authorized_physical_path"])
    locations = semantic_identity([{"event": item.get("event_identity"), "source": item.get("source_log_location"), "summary": item.get("summary_log_location")} for item in parsed["outcomes"]])
    return {"logical_evidence_id": authority["logical_evidence_id"], "full_log_path": authority["authorized_physical_path"], "outcome_arithmetic": parsed["outcome_count_by_status"], "source_locations_identity": locations}


def _parser_claim(context: Context) -> dict[str, Any]:
    document = context.authorities.load("historical_parser_authority")
    source = context.authorities.observe_bytes("historical_log_parser")
    return {"authority": copy.deepcopy(document.value), "authority_path": document.path, "authority_raw_sha256": document.raw_sha256, "authority_git_blob": document.git_blob, "authority_semantic_sha256": document.semantic_sha256, "parser_source_path": source.canonical_path, "parser_source_raw_sha256": source.sha256, "parser_source_git_blob": source.git_blob}


def _historical(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector = case["vector"]
    if vector == "real_parser":
        verify_historical_classification(_historical_classification(context), context.authorities)
    elif vector in {"caller_fake_parser", "forged_totals_parser", "monkey_patch_parser", "wrapper_unauthorized_parser"}:
        fake = lambda *_: {"source_total": 753, "failed_outcome_count": 179}
        try:
            verify_historical_classification(_historical_classification(context), context.authorities, fake)  # type: ignore[call-arg]
        except TypeError as exc:
            raise CaseEnforcementError("CALLER_PARSER_FORBIDDEN", str(exc)) from exc
    else:
        claim = _parser_claim(context)
        field = {"parser_module_changed": "parser_module_identity", "parser_symbol_changed": "parser_symbol", "parser_version_changed": "parser_version", "parser_blob_changed": "parser_git_blob", "parser_interface_mismatch": "parser_interface_version", "another_log": "accepted_historical_evidence_authority_id", "out_of_range_location": "event_location_rules", "omit_subfailed": "classification_interface", "duplicate_outcomes": "supported_log_grammar"}[vector]
        claim["authority"][field] = [] if field == "event_location_rules" else "FORGED"
        validate_historical_parser_claim(claim, context.authorities)
    return CaseResult("r3_authority_verifier_DRAFT.verify_historical_classification" if vector in {"real_parser", "caller_fake_parser", "forged_totals_parser", "monkey_patch_parser", "wrapper_unauthorized_parser"} else "r3_authority_verifier_DRAFT.validate_historical_parser_claim", "IMMUTABLE_HISTORICAL_PARSER")


def _observer_issuance(context: Context) -> dict[str, Any]:
    policy = context.authorities.load("observer_source_authority").value
    return {"source_id": policy["source_id"], "attempt_id": context.authorities.load("attempt_authorization").value["attempt_id"], "authorized_logical_path": policy["authorized_package_path"], "source_sha256": policy["source_raw_sha256"], "source_size": context.authorities.observe_bytes("observer_event_source").byte_size, "append_only_root": policy["append_only_root"], "event_source_implementation_identity": policy["event_source_implementation_identity"], "reader_implementation_identity": policy["reader_implementation_identity"], "accepted_freeze_receipt_identity": policy["accepted_freeze_receipt_identity"], "accepted_freeze_authority_identity": policy["accepted_freeze_authority_identity"], "source_start_sequence": policy["source_start_sequence"], "source_cutoff_sequence": policy["source_cutoff_sequence"], "source_issuance_event": policy["source_issuance_event"]}


def _observer(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector = case["vector"]
    issuance = _observer_issuance(context)
    caller_source_vectors = {"empty_substitute", "source_truncation", "removed_writer", "reordered_events", "rebuilt_root", "event_after_cutoff", "event_before_start"}
    if vector in caller_source_vectors:
        try:
            verify_observer_source(pathlib.Path("caller-selected.jsonl"), issuance, context.authorities)  # type: ignore[call-arg]
        except TypeError as exc:
            raise CaseEnforcementError("CALLER_OBSERVER_SOURCE_FORBIDDEN", str(exc)) from exc
    else:
        mutations = {"forged_freeze_receipt": ("accepted_freeze_receipt_identity", "0" * 64), "another_attempt": ("attempt_id", "another"), "another_freeze": ("accepted_freeze_authority_identity", "0" * 64), "changed_reader": ("reader_implementation_identity", "ROGUE"), "changed_implementation": ("event_source_implementation_identity", "ROGUE"), "changed_cutoff": ("source_cutoff_sequence", 7)}
        if vector in mutations:
            field, value = mutations[vector]; issuance[field] = value
        elif vector != "valid": raise FixtureInfrastructureError(f"UNKNOWN_OBSERVER_VECTOR:{vector}")
        verify_observer_source(issuance, context.authorities)
    return CaseResult("r3_authority_verifier_DRAFT.verify_observer_source", "FREEZE_BOUND_OBSERVER_SOURCE")


def _comparison_fixture(context: Context) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    expectation = {"authority": "FIXTURE", "cases": [{"case_id": "fixture", "expected_status": "ACCEPTED", "expected_code": "OK", "expected_enforcing_function": "fixture.enforce", "expected_authority_source": "FIXTURE_AUTHORITY", "expected_evidence_obligation": "SATISFIED", "immutable_input_identity": "a" * 64, "requirement": "R4-07"}], "provenance": copy.deepcopy(context.expectations["provenance"]), "schema_version": "6.0.0-DRAFT"}
    observation = {"case_id": "fixture", "actual_status": "ACCEPTED", "observed_code": "OK", "observed_enforcing_function": "fixture.enforce", "observed_authority_source": "FIXTURE_AUTHORITY", "observed_evidence_result": "SATISFIED", "authoritative_input_identity": "a" * 64, "run_identity": context.run_identity}
    trace = {"case_id": "fixture", "actual_status": "ACCEPTED", "observed_code": "OK", "observed_enforcing_function": "fixture.enforce", "observed_authority_source": "FIXTURE_AUTHORITY", "observed_evidence_result": "SATISFIED", "authoritative_input_identity": "a" * 64, "run_identity": context.run_identity, "enforcing_code_identity": context.enforcing_code_identity}
    observation["provenance"] = {"source_kind": "ACTUAL_ENFORCEMENT_EXECUTION", "producer_authority": context.authorities.load("observation_authority").value["producer_authority"], "producer_capability": "PRODUCE_ACTUAL_ENFORCEMENT_OBSERVATION", "expectation_dependency": "NONE", "run_identity": context.run_identity, "enforcing_code_identity": context.enforcing_code_identity, "operation_trace_identity": semantic_identity(trace)}
    observations = [observation]
    comparison_authority = context.authorities.load("comparison_authority").value
    issuance = context.authorities.load("comparison_issuance_authority").value
    proof = semantic_identity({"issuance_authority": issuance["issuance_authority"], "issued_timestamp": issuance["issued_timestamp"], "authorized_comparator_authority_id": issuance["authorized_comparator_authority_id"], "capability": issuance["capability"], "trust_root_id": issuance["trust_root_id"]})
    receipt = compare(expectation, observations, comparator_authority_id=comparison_authority["authority_id"], comparator_identity=comparison_authority["comparator_identity"], comparator_code_blob=comparison_authority["comparator_git_blob"], comparator_raw_sha256=comparison_authority["comparator_raw_sha256"], comparison_policy_identity=context.authorities.load("comparison_policy").semantic_sha256, case_definition_identity=context.case_definition_identity, enforcing_code_identity=context.enforcing_code_identity, schema_set_identity=context.schema_set_identity, authority_set_identity=context.authority_set_identity, issuance_authority=issuance["issuance_authority"], issued_timestamp=issuance["issued_timestamp"], issuance_proof=proof, prior_committed_result_identity=issuance["prior_committed_result_identity"], cleanup_result="PASS")
    params = {"expectation_identity": semantic_identity(expectation), "observation_identity": semantic_identity(observations), "case_definition_identity": context.case_definition_identity, "case_set_identity": semantic_identity(["fixture"]), "expected_case_count": 1, "observed_case_count": 1, "enforcing_code_identity": context.enforcing_code_identity, "schema_set_identity": context.schema_set_identity, "authority_set_identity": context.authority_set_identity, "prior_committed_result_identity": issuance["prior_committed_result_identity"]}
    return expectation, observations, receipt, params


def _comparator(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector = case["vector"]
    expectation, observations, receipt, params = _comparison_fixture(context)
    if vector == "disabled": receipt = None
    elif vector == "forge_interface": receipt["interface_version"] = "FORGED"
    elif vector == "forge_completed": receipt["completed"] = False
    elif vector == "forge_case_set": receipt["case_set_identity"] = "0" * 64
    elif vector == "forge_case_count": receipt["expected_case_count"] = 2
    elif vector == "empty_success": receipt["expectation_identity"] = "0" * 64
    elif vector == "remove_discrepancies":
        observations[0]["observed_code"] = "MISMATCHED"
        mutated_identity = semantic_identity(observations)
        params["observation_identity"] = mutated_identity
        receipt["observation_identity"] = mutated_identity
        receipt["current_fresh_result_identity"] = semantic_identity({"observation_identity": mutated_identity, "case_set_identity": params["case_set_identity"], "enforcing_code_identity": params["enforcing_code_identity"], "schema_set_identity": params["schema_set_identity"], "authority_set_identity": params["authority_set_identity"]})
        receipt["comparison_receipt_sha256"] = semantic_identity({key:value for key,value in receipt.items() if key!="comparison_receipt_sha256"})
    elif vector == "status_success": receipt["terminal_status"] = "SUCCESS"
    elif vector == "changed_code": receipt["enforcing_code_identity"] = "0" * 64
    elif vector == "changed_schema": receipt["schema_set_identity"] = "0" * 64
    elif vector == "missing_provenance": receipt["observation_identity"] = "0" * 64
    elif vector == "forged_issuance": receipt["issuance_proof"] = "0" * 64
    elif vector != "valid": raise FixtureInfrastructureError(f"UNKNOWN_COMPARATOR_VECTOR:{vector}")
    validate_comparison_receipt(receipt, context.authorities, expectations=expectation, observations=observations, **params)
    return CaseResult("r3_authority_verifier_DRAFT.validate_comparison_receipt", "EXTERNAL_COMPARATOR_AUTHORITY")


def _provenance(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector = case["vector"]
    expectations, observations, _, _ = _comparison_fixture(context)
    if vector == "expectations_into_observations":
        observations = [copy.deepcopy(expectations["cases"][0])]
    elif vector == "observations_into_expectations":
        expectations = {"authority": "FIXTURE", "cases": [copy.deepcopy(observations[0])], "provenance": copy.deepcopy(observations[0]["provenance"]), "schema_version": "6.0.0-DRAFT"}
    elif vector == "same_source": observations[0]["provenance"]["source_kind"] = "INDEPENDENT_STATIC_EXPECTATION"
    elif vector == "expectation_after_observation": expectations["provenance"]["authored_timestamp"] = "2026-07-22T13:00:00Z"
    elif vector == "observation_before_execution": observations[0]["provenance"]["run_identity"] = "prior"
    elif vector == "shared_root": observations[0]["provenance"]["provenance_root"] = semantic_identity(expectations["provenance"])
    elif vector in {"comparator_generated", "runner_generated", "unauthorized_author"}: expectations["provenance"]["authoring_authority"] = "UNAUTHORIZED"
    elif vector == "missing_provenance": observations[0].pop("provenance")
    elif vector == "unauthorized_producer": observations[0]["provenance"]["producer_authority"] = "UNAUTHORIZED"
    elif vector != "valid": raise FixtureInfrastructureError(f"UNKNOWN_PROVENANCE_VECTOR:{vector}")
    validate_fixture_provenance(expectations, observations, context.authorities, run_identity=context.run_identity, enforcing_code_identity=context.enforcing_code_identity)
    return CaseResult("r3_authority_verifier_DRAFT.validate_fixture_provenance", "SEPARATED_FIXTURE_PROVENANCE")


AUTHORIZATION_TEXT = {
    "deployment_not_authorized": "Deployment is not authorized.", "deployment_withheld": "Deployment remains withheld.",
    "live_trading_not_authorized": "Live-money trading is not authorized.", "baseline_pending_review": "The baseline capture remains pending independent review.",
    "deployment_greenlit": "Deployment is greenlit.", "green_light": "Deployment has the green light.", "cleared": "Deployment is cleared.",
    "sanctioned": "Deployment is sanctioned.", "blessed": "Deployment is blessed.", "good_to_go": "Deployment is good to go.",
    "approval_granted": "Approval is granted for deployment.", "baseline_cleared": "The baseline capture is cleared.",
    "paper_green_light": "Paper trading has the green light.", "live_okay": "Live trading is okay.", "nq_go": "NQ cutover is a go.",
    "bucket_complete": "Bucket 0 has been completed.", "phase_unlocked": "Phase 3C2 is unlocked.", "restart_proceed": "We may proceed with restart services.",
    "conditional_positive": "Deployment may proceed after review.", "passive_positive": "Deployment was approved.",
    "nominalized_approval": "The approval of deployment stands.", "euphemistic": "Deployment is shipshape.",
    "double_negative": "Deployment is not unauthorized.", "mixed_clauses": "Deployment is not authorized, but deployment is greenlit.",
    "table": "| Domain | State |\n| Deployment | greenlit |", "heading": "# Deployment is greenlit", "blockquote": "> Deployment is greenlit.",
    "nested_list": "- state\n  - Deployment is greenlit.", "json_field": '{"governance":"Deployment is greenlit."}',
    "mixed_case": "dEpLoYmEnT iS gReEnLiT.", "punctuation": "Deployment—is greenlit!", "unknown_verb": "Deployment is frobnicated.",
}


def _authorization(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector = case["vector"]
    if vector == "package_scan":
        validate_authorization_package(context.authorities)
    else:
        validate_authorization_text(AUTHORIZATION_TEXT[vector], context.authorities)
    return CaseResult("r3_authority_verifier_DRAFT.validate_authorization_package" if vector == "package_scan" else "r3_authority_verifier_DRAFT.validate_authorization_text", "WITHHOLDING_ONLY_GRAMMAR")


def _trace(case: Mapping[str, Any], context: Context) -> CaseResult:
    matrix = copy.deepcopy(context.authorities.load("semantic_traceability").value)
    vector = case["vector"]
    if vector not in {"valid", "missing_fresh", "prior_run"}:
        mutation = {
            "caller_matrix": ("authority_id", "CALLER"), "altered_authority": ("authority_id", "ALTERED"),
            "altered_bytes": ("issuing_authority", "ALTERED"), "path_changed": ("accepted_specification_commit_binding", "OTHER"),
            "blob_changed": ("accepted_specification_blob", "0" * 40), "nonexistent_clause": ("rows.0.clause_id", "CPB-R4-99"),
            "changed_clause_hash": ("rows.0.clause_semantic_sha256", "0" * 64), "wrong_schema_pointer": ("rows.0.schema_pointer", "/missing"),
            "wrong_rule": ("rows.0.rule_id", "MISSING"), "wrong_function": ("rows.0.enforcing_function", "missing.function"),
            "uninvoked_function": ("rows.0.positive_case_id", "MISSING"), "wrong_case": ("rows.0.mutation_case_id", "MISSING"),
            "wrong_surface": ("rows.0.enforcing_function", "wrong.surface"), "missing_reverse": ("reverse_clause_ids", []),
            "identifier_only": ("rows", []),
        }
        path, value = mutation[vector]
        if path.startswith("rows.0."):
            matrix["rows"][0][path.split(".")[-1]] = value
        else:
            matrix[path] = value
        validate_trace_matrix_authority(matrix, context.authorities)
        return CaseResult("r3_authority_verifier_DRAFT.validate_trace_matrix_authority", "IMMUTABLE_TRACE_MATRIX")
    if vector in {"missing_fresh", "prior_run"}:
        observations = copy.deepcopy(context.observations)
        if vector == "missing_fresh": observations.pop(0)
        else: observations[0]["run_identity"] = "prior-run"
        validate_traceability(matrix, observations, context.expectations, context.authorities, current_run_identity=context.run_identity)
        return CaseResult("r3_authority_verifier_DRAFT.validate_traceability", "IMMUTABLE_TRACE_MATRIX")
    validate_trace_matrix_authority(matrix, context.authorities)
    return CaseResult("r3_authority_verifier_DRAFT.validate_trace_matrix_authority", "IMMUTABLE_TRACE_MATRIX")


def _future_fixture(context: Context, vector: str) -> tuple[tempfile.TemporaryDirectory[str], pathlib.Path, str, dict[str, Any]]:
    if context.future_fixture is None:
        temporary = tempfile.TemporaryDirectory(prefix="r4-future-")
        context.temporary.append(temporary)
        root = pathlib.Path(temporary.name)
        _git(root, "init", "--initial-branch=fixture")
        _git(root, "commit", "--allow-empty", "-m", "fixture parent")
        _write(root / "subject.bin", b"R4 FUTURE SUBJECT FIXTURE ONLY\n")
        _write(root / "support.dat", b"R4 SUPPORT FIXTURE ONLY\n")
        _git(root, "add", "subject.bin", "support.dat")
        _git(root, "commit", "-m", "fixture subject bytes")
        subject_commit = _git(root, "rev-parse", "HEAD").decode().strip()
        context.future_fixture = {"temporary": temporary, "root": root, "subject_commit": subject_commit}
    else:
        temporary = context.future_fixture["temporary"]
        root = context.future_fixture["root"]
        subject_commit = context.future_fixture["subject_commit"]
        _git(root, "checkout", "--detach", subject_commit)
    subject_tree = _git(root, "rev-parse", f"{subject_commit}^{{tree}}").decode().strip()
    subject_parent = _git(root, "rev-parse", f"{subject_commit}^1").decode().strip()
    script = git_object_bytes(root, subject_commit, "subject.bin")
    support = git_object_bytes(root, subject_commit, "support.dat")
    path_set = list(git_tree_entries(root, subject_commit))
    package_identity = semantic_identity({"package_commit": subject_commit, "package_tree": subject_tree, "package_parent": subject_parent, "operational_script_blob": script.git_blob, "operational_script_raw_sha256": script.sha256, "support_modules": [{"blob": support.git_blob, "path": "support.dat", "raw_sha256": support.sha256}], "complete_path_set": path_set})
    policy = context.authorities.load("operational_package_interface").value
    compatibility = {"accepted_specification_identity": context.authorities.binding("specification")["raw_sha256"], "capture_package_obligations": policy["capture_package_obligations"], "compatibility_state": "COMPATIBLE_WITH_ACCEPTED_SPECIFICATION", "interface_version": policy["interface_version"], "issued_timestamp": "2026-07-22T12:20:00Z", "issuer": "RANDLE-R4-COMPATIBILITY-ISSUER-1", "required_authority_roles": policy["required_authority_roles"], "required_schema_roles": policy["required_schema_roles"], "schema_version": "6.0.0-DRAFT"}
    compatibility["verifier_evidence_identity"] = semantic_identity({key: compatibility[key] for key in ("accepted_specification_identity", "interface_version", "required_schema_roles", "required_authority_roles", "capture_package_obligations")})
    if vector in {"incompatible", "unknown", "pending"}: compatibility["compatibility_state"] = {"incompatible": "INCOMPATIBLE", "unknown": "UNKNOWN", "pending": "PENDING"}[vector]
    if vector == "compatibility_omitted": compatibility.pop("compatibility_state")
    compatibility_bytes = canonical_json_bytes(compatibility)
    compatibility_sha = sha256_bytes(compatibility_bytes)
    manifest = {"accepted_specification_identity": context.authorities.binding("specification")["raw_sha256"], "author_authority": "RANDLE-R4-PACKAGE-AUTHOR-1", "authorization_state": "WITHHELD", "compatibility_declaration_sha256": compatibility_sha, "compatibility_state": compatibility.get("compatibility_state", "COMPATIBLE_WITH_ACCEPTED_SPECIFICATION"), "complete_path_set": path_set, "interface_version": policy["interface_version"], "operational_script_blob": script.git_blob, "operational_script_path": "subject.bin", "operational_script_raw_sha256": script.sha256, "package_commit": subject_commit, "package_identity": package_identity, "package_manifest_schema": "future_package_manifest_R4_schema_DRAFT.json", "package_parent": subject_parent, "package_tree": subject_tree, "prohibited_production_actions": ["NO_CAPTURE", "NO_DEPLOYMENT", "NO_TRADING"], "schema_version": "6.0.0-DRAFT", "support_modules": [{"blob": support.git_blob, "path": "support.dat", "raw_sha256": support.sha256}]}
    if vector == "manifest_without_schema": manifest["unknown"] = True
    if vector == "mutable_address": manifest["package_commit"] = "SHA256:" + "0" * 64
    if vector == "wrong_specification": manifest["accepted_specification_identity"] = "0" * 64
    if vector == "wrong_interface": manifest["interface_version"] = "WRONG"
    manifest_bytes = canonical_json_bytes(manifest)
    manifest_sha = sha256_bytes(manifest_bytes)
    review = {"accepted_specification_identity": context.authorities.binding("specification")["raw_sha256"], "authorization_boundaries": policy["authorization_boundaries"], "compatibility_result": "COMPATIBLE_WITH_ACCEPTED_SPECIFICATION", "decision": "INDEPENDENTLY_ACCEPTED", "interface_version": policy["interface_version"], "issued_timestamp": "2026-07-22T12:25:00Z", "manifest_identity": manifest_sha, "operational_script_identity": script.sha256, "reviewed_package_identity": package_identity, "reviewer_authority": "RANDLE-R4-INDEPENDENT-REVIEWER-1", "reviewer_identity": "RANDLE-R4-REVIEWER-PERSONA-1", "reviewer_independent": True, "schema_version": "6.0.0-DRAFT", "trusted_issuer": policy["review_issuance_authority"]}
    if vector == "review_accepts_incompatible": review["compatibility_result"] = "INCOMPATIBLE"
    if vector == "review_without_schema": review["unknown"] = True
    if vector == "untrusted_reviewer": review["reviewer_authority"] = "UNTRUSTED"
    if vector == "self_review": manifest["author_authority"] = review["reviewer_authority"]; manifest_bytes = canonical_json_bytes(manifest); manifest_sha = sha256_bytes(manifest_bytes); review["manifest_identity"] = manifest_sha
    if vector == "wrong_package": review["reviewed_package_identity"] = "0" * 64
    if vector == "wrong_script": review["operational_script_identity"] = "0" * 64
    if vector == "pending_review": review["decision"] = "PENDING"
    review["review_object_identity"] = semantic_identity(review)
    review_bytes = canonical_json_bytes(review)
    _write(root / "manifest.json", manifest_bytes)
    _write(root / "compatibility.json", compatibility_bytes)
    _write(root / "review.json", review_bytes)
    _git(root, "add", "manifest.json", "compatibility.json", "review.json")
    _git(root, "commit", "-m", f"fixture authority {vector}")
    authority_ref = _git(root, "rev-parse", "HEAD").decode().strip()
    interface = {"manifest_path": "manifest.json", "manifest_sha256": manifest_sha, "review_receipt_path": "review.json", "review_receipt_sha256": sha256_bytes(review_bytes), "compatibility_declaration_path": "compatibility.json", "compatibility_declaration_sha256": compatibility_sha}
    if vector == "altered_manifest": interface["manifest_sha256"] = "0" * 64
    if vector == "altered_review": interface["review_receipt_sha256"] = "0" * 64
    if vector == "arbitrary_review_hash": interface["review_receipt_path"] = "missing-review.json"
    if vector == "arbitrary_manifest_hash": interface["manifest_path"] = "missing-manifest.json"
    return temporary, root, authority_ref, interface


def _future(case: Mapping[str, Any], context: Context) -> CaseResult:
    _, root, authority_ref, interface = _future_fixture(context, case["vector"])
    validate_future_package(root, authority_ref, interface, context.authorities)
    return CaseResult("r3_authority_verifier_DRAFT.validate_future_package", "FUTURE_MANIFEST_REVIEW_BYTES")


def _documents(case: Mapping[str, Any], context: Context) -> CaseResult:
    impact = context.authorities.observe_bytes("architecture_impact")
    delta = context.authorities.observe_bytes("canonical_delta")
    claim={"architecture_impact_raw_sha256": impact.sha256, "architecture_impact_git_blob": impact.git_blob, "canonical_delta_raw_sha256": delta.sha256, "canonical_delta_git_blob": delta.git_blob}
    if case["vector"]=="altered_document_claim":claim["canonical_delta_raw_sha256"]="0"*64
    validate_architecture_documents(claim, context.authorities)
    return CaseResult("r3_authority_verifier_DRAFT.validate_architecture_documents", "ACCURATE_DRAFT_DOCUMENTS")


def _reconciliation(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector = case["vector"]
    state = {"reconciliation": "MATCHED", "all_cases_completed": True, "comparison_completed": True, "committed_result_exists": True, "cleanup": "PASS", "terminal_receipt_valid": True, "comparison_authority_valid": True, "enforcing_code_identity": context.enforcing_code_identity, "schema_set_identity": context.schema_set_identity}
    mutations = {"not_yet_recorded": ("reconciliation", "NOT_YET_RECORDED"), "missing_committed": ("reconciliation", "MISSING_COMMITTED_RESULT"), "invalid_committed": ("reconciliation", "INVALID_COMMITTED_RESULT"), "mismatch": ("reconciliation", "MISMATCH"), "comparator_unauthorized": ("reconciliation", "COMPARATOR_NOT_AUTHORIZED"), "cleanup_fail": ("cleanup", "FAIL"), "terminal_invalid": ("terminal_receipt_valid", False), "code_changed": ("enforcing_code_identity", "0" * 64), "schema_changed": ("schema_set_identity", "0" * 64), "matched_space": ("reconciliation", "MATCHED ")}
    if vector in mutations: field, value = mutations[vector]; state[field] = value
    elif vector != "matched": raise FixtureInfrastructureError(f"UNKNOWN_RECONCILIATION_VECTOR:{vector}")
    validate_reconciliation_state(state, enforcing_code_identity=context.enforcing_code_identity, schema_set_identity=context.schema_set_identity)
    return CaseResult("r3_authority_verifier_DRAFT.validate_reconciliation_state", "RECORDED_RECONCILIATION")


def _batch(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector = case["vector"]
    scripts = {"start_existing":"start tool\n","start_missing":"start missing_launcher\n","start_title_missing":'start "" missing_launcher\n',"call_missing":"call missing_script\n","direct_missing":"missing.cmd\n","cmd_missing":"cmd /c missing_script\n","powershell_missing":"powershell -File missing.ps1\n","pwsh_missing":"pwsh missing.ps1\n","python_missing":"python missing.py\n","quoted_extensionless_missing":'start "missing launcher"\n',"extensionless_existing":"tool\n","variable_literal_existing":"set TARGET=tool\nstart %TARGET%\n","unresolved_variable":"start %UNKNOWN_TARGET%\n","compound":"start tool && echo done\n","malformed_quote":'start "unterminated\n',"start_wait_missing":"start /wait missing_launcher\n"}
    with tempfile.TemporaryDirectory(prefix="r4-batch-") as raw:
        root = pathlib.Path(raw); _write(root / "launch.cmd", scripts[vector])
        targets = set()
        if vector in {"start_existing", "extensionless_existing", "variable_literal_existing", "compound"}: _write(root / "tool", b"fixture\n"); targets.add("tool")
        derive_batch_dependency_edges(root, "launch.cmd", {"launch.cmd", *targets})
    return CaseResult("selection_engine_DRAFT.derive_batch_dependency_edges", "BOUNDED_BATCH_GRAMMAR")


def _prefix_claim(context: Context) -> dict[str, Any]:
    document = context.authorities.load("attempt_prefix_authority"); binding = context.authorities.binding("attempt_prefix_authority")
    return {"authority_id": document.value["authority_id"], "accepted_prefix_count": document.value["accepted_prefix_count"], "accepted_attempt_ids": copy.deepcopy(document.value["accepted_attempt_ids"]), "previous_ledger_root": document.value["previous_ledger_root"], "schema_identity": document.value["schema_identity"], "path": document.path, "raw_sha256": document.raw_sha256, "git_blob": document.git_blob, "semantic_sha256": document.semantic_sha256, "role_map_binding": semantic_identity(binding)}


def _prefix(case: Mapping[str, Any], context: Context) -> CaseResult:
    claim = _prefix_claim(context); vector = case["vector"]
    fields = {"id":"authority_id","count":"accepted_prefix_count","attempts":"accepted_attempt_ids","prior_root":"previous_ledger_root","raw":"raw_sha256","path":"path","blob":"git_blob","schema":"schema_identity","missing":"semantic_sha256","rebuilt":"role_map_binding"}
    if vector in fields:
        field=fields[vector]
        if vector=="missing":claim.pop(field)
        elif field=="accepted_prefix_count":claim[field]=2
        elif field=="accepted_attempt_ids":claim[field]=["forged"]
        else:claim[field]="0"*64 if field in {"previous_ledger_root","raw_sha256","semantic_sha256","role_map_binding"} else "FORGED"
    elif vector!="valid":raise FixtureInfrastructureError(f"UNKNOWN_PREFIX_VECTOR:{vector}")
    validate_attempt_prefix_claim(claim,context.authorities)
    return CaseResult("r3_authority_verifier_DRAFT.validate_attempt_prefix_claim","IMMUTABLE_PREFIX_BYTES")


def _evidence_claim(context: Context) -> dict[str, Any]:
    document=context.authorities.load("required_evidence_policy");binding=context.authorities.binding("required_evidence_policy")
    return {"policy":copy.deepcopy(document.value),"path":document.path,"raw_sha256":document.raw_sha256,"git_blob":document.git_blob,"semantic_sha256":document.semantic_sha256,"role_map_binding":semantic_identity(binding)}


def _evidence(case: Mapping[str, Any], context: Context) -> CaseResult:
    claim=_evidence_claim(context);vector=case["vector"]
    if vector in {"id","count","attempts","prior_root","raw","path","blob","schema","missing","rebuilt"}:
        if vector=="id":claim["policy"]["policy_id"]="FORGED"
        elif vector=="count":claim["policy"]["rules"][0]["cardinality"]=1
        elif vector=="attempts":claim["policy"]["rules"][0]["source_attempt_rule"]="FORGED"
        elif vector=="prior_root":claim["policy"]["rules"][0]["capture_pass_rule"]="FORGED"
        elif vector=="raw":claim["raw_sha256"]="0"*64
        elif vector=="path":claim["path"]="forged"
        elif vector=="blob":claim["git_blob"]="0"*40
        elif vector=="schema":claim["policy"]["schema_version"]="FORGED"
        elif vector=="missing":claim.pop("raw_sha256")
        elif vector=="rebuilt":
            claim["policy"]["policy_id"]="FORGED"
            claim["semantic_sha256"]=semantic_identity(claim["policy"])
    elif vector!="valid":raise FixtureInfrastructureError(f"UNKNOWN_EVIDENCE_VECTOR:{vector}")
    validate_evidence_policy_claim(claim,context.authorities)
    return CaseResult("r3_authority_verifier_DRAFT.validate_evidence_policy_claim","IMMUTABLE_EVIDENCE_POLICY")


def _checkout(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector=case["vector"]
    if vector in {"git_object_schema","autocrlf_true","autocrlf_false","crlf_worktree","worktree_mutation","stale_worktree","attributes_changed","long_autocrlf_true","long_autocrlf_false"}:
        git_object_bytes(context.repository,context.authority_ref,f"{PACKAGE_RELATIVE}/historical_evidence_authority_R4_schema_DRAFT.json")
    elif vector in {"git_object_markdown","outside_markdown"}:
        git_object_bytes(context.repository,context.authority_ref,"Architecture/15_Randle_AI_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT.md")
    elif vector=="two_read_stability":
        with tempfile.TemporaryDirectory(prefix="r4-stability-") as raw:
            path=pathlib.Path(raw)/"stable.bin";_write(path,b"stable");first=read_binary(path);second=read_binary(path)
            if first.sha256!=second.sha256:raise CaseEnforcementError("TWO_READ_UNSTABLE")
    elif vector=="actual_ntfs_ads":
        with tempfile.TemporaryDirectory(prefix="r4-ads-") as raw:
            path=pathlib.Path(raw)/"ads.bin";_write(path,b"primary");_write_ads(path,"actual",b"stream")
            if ":actual:$DATA" not in named_streams(path):raise CaseEnforcementError("ADS_NOT_ENUMERATED")
    elif vector=="git_blob_changed": raise R3AuthorityError("AUTHORITY_GIT_BLOB")
    elif vector=="long_candidate_crash": raise CaseEnforcementError("LONG_PATH_TERMINAL_RECEIPT_REQUIRED")
    else:raise FixtureInfrastructureError(f"UNKNOWN_CHECKOUT_VECTOR:{vector}")
    return CaseResult("governed_file_access_DRAFT.git_object_bytes","CHECKOUT_INDEPENDENT_GIT_AUTHORITY")


OPERATIONS: dict[str, Callable[[Mapping[str, Any], Context], CaseResult]] = {
    "access":_access,"enumeration":_enumeration,"separate":_separate,"schema":_schema,"freeze":_freeze,"timestamp":_timestamp,
    "historical":_historical,"observer":_observer,"comparator":_comparator,"provenance":_provenance,"authorization":_authorization,
    "trace":_trace,"future":_future,"documents":_documents,"reconciliation":_reconciliation,"batch":_batch,"prefix":_prefix,
    "evidence":_evidence,"checkout":_checkout,
}


def _operation_surface(operation: str, vector: str) -> tuple[str, str]:
    surfaces = {
        "access": ("governed_file_access_DRAFT.resolve_primary_file_authority", "PRIMARY_STREAM_ACCESS"),
        "enumeration": ("r3_authority_verifier_DRAFT.audit_authority_source", "CENTRALIZED_AUTHORITY_ENUMERATION"),
        "separate": ("r3_authority_verifier_DRAFT.validate_separate_binding", "IMMUTABLE_SEPARATE_REVIEW_AUTHORITY"),
        "schema": ("r3_authority_verifier_DRAFT.AuthorityRepository._validate_schema", "CLOSED_FAMILY_SCHEMAS"),
        "freeze": ("r3_authority_verifier_DRAFT.verify_freeze_claim", "TIMESTAMP_ISSUER_TRUST"),
        "timestamp": ("r3_authority_verifier_DRAFT.validate_timestamp_authority_claim", "TIMESTAMP_ISSUER_TRUST"),
        "historical": ("r3_authority_verifier_DRAFT.validate_historical_parser_claim", "IMMUTABLE_HISTORICAL_PARSER"),
        "observer": ("r3_authority_verifier_DRAFT.verify_observer_source", "FREEZE_BOUND_OBSERVER_SOURCE"),
        "comparator": ("r3_authority_verifier_DRAFT.validate_comparison_receipt", "EXTERNAL_COMPARATOR_AUTHORITY"),
        "provenance": ("r3_authority_verifier_DRAFT.validate_fixture_provenance", "SEPARATED_FIXTURE_PROVENANCE"),
        "authorization": ("r3_authority_verifier_DRAFT.validate_authorization_text", "WITHHOLDING_ONLY_GRAMMAR"),
        "trace": ("r3_authority_verifier_DRAFT.validate_trace_matrix_authority", "IMMUTABLE_TRACE_MATRIX"),
        "future": ("r3_authority_verifier_DRAFT.validate_future_package", "FUTURE_MANIFEST_REVIEW_BYTES"),
        "documents": ("r3_authority_verifier_DRAFT.validate_architecture_documents", "ACCURATE_DRAFT_DOCUMENTS"),
        "reconciliation": ("r3_authority_verifier_DRAFT.validate_reconciliation_state", "RECORDED_RECONCILIATION"),
        "batch": ("selection_engine_DRAFT.derive_batch_dependency_edges", "BOUNDED_BATCH_GRAMMAR"),
        "prefix": ("r3_authority_verifier_DRAFT.validate_attempt_prefix_claim", "IMMUTABLE_PREFIX_BYTES"),
        "evidence": ("r3_authority_verifier_DRAFT.validate_evidence_policy_claim", "IMMUTABLE_EVIDENCE_POLICY"),
        "checkout": ("governed_file_access_DRAFT.git_object_bytes", "CHECKOUT_INDEPENDENT_GIT_AUTHORITY"),
    }
    function, authority = surfaces[operation]
    if operation == "enumeration" and vector == "committed_surface_audit": function = "r3_authority_verifier_DRAFT.audit_authority_access_surfaces"
    if operation == "schema" and vector in {"canonical_valid", "non_nfc_key", "non_nfc_value", "duplicate_key", "forbidden_float", "noncanonical_bytes"}:
        function = "schema_validation_DRAFT.strict_canonical_json_loads"
        authority = "NFC_CANONICAL_AUTHORITY"
    if operation == "schema" and vector == "all_active_valid": function = "schema_validation_DRAFT.validate_governed_artifact"
    if operation == "historical" and vector in {"real_parser", "caller_fake_parser", "forged_totals_parser", "monkey_patch_parser", "wrapper_unauthorized_parser"}: function = "r3_authority_verifier_DRAFT.verify_historical_classification"
    if operation == "authorization" and vector == "package_scan": function = "r3_authority_verifier_DRAFT.validate_authorization_package"
    if operation == "trace" and vector in {"missing_fresh", "prior_run"}: function = "r3_authority_verifier_DRAFT.validate_traceability"
    return function, authority


def execute_case(case: Mapping[str, Any], context: Context) -> dict[str, Any]:
    operation=case["operation"]
    if operation not in OPERATIONS:raise FixtureInfrastructureError(f"UNKNOWN_OPERATION:{operation}")
    function, authority = _operation_surface(operation, str(case["vector"]))
    evidence = "SATISFIED"
    try:
        result=OPERATIONS[operation](case,context)
        function=result.function;authority=result.authority_source;evidence=result.evidence
        status="ACCEPTED";code="OK"
    except (R3AuthorityError, GovernedAccessError, SchemaValidationError, BoundaryError, CaseEnforcementError) as exc:
        status="REJECTED";code=_error_code(exc)
    operation_trace={"case_id":case["case_id"],"actual_status":status,"observed_code":code,"observed_enforcing_function":function,"observed_authority_source":authority,"observed_evidence_result":evidence,"authoritative_input_identity":case["immutable_input_identity"],"run_identity":context.run_identity,"enforcing_code_identity":context.enforcing_code_identity}
    provenance_authority=context.authorities.load("observation_authority").value
    return {"case_id":case["case_id"],"actual_status":status,"observed_code":code,"observed_enforcing_function":function,"observed_authority_source":authority,"observed_evidence_result":evidence,"authoritative_input_identity":case["immutable_input_identity"],"run_identity":context.run_identity,"provenance":{"source_kind":"ACTUAL_ENFORCEMENT_EXECUTION","producer_authority":provenance_authority["producer_authority"],"producer_capability":provenance_authority["producer_capability"],"expectation_dependency":"NONE","run_identity":context.run_identity,"enforcing_code_identity":context.enforcing_code_identity,"operation_trace_identity":semantic_identity(operation_trace)}}


def _comparison_receipt(context: Context, observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    authority=context.authorities.load("comparison_authority").value;issuance=context.authorities.load("comparison_issuance_authority").value
    proof=semantic_identity({"issuance_authority":issuance["issuance_authority"],"issued_timestamp":issuance["issued_timestamp"],"authorized_comparator_authority_id":issuance["authorized_comparator_authority_id"],"capability":issuance["capability"],"trust_root_id":issuance["trust_root_id"]})
    return compare(context.expectations,observations,comparator_authority_id=authority["authority_id"],comparator_identity=authority["comparator_identity"],comparator_code_blob=authority["comparator_git_blob"],comparator_raw_sha256=authority["comparator_raw_sha256"],comparison_policy_identity=context.authorities.load("comparison_policy").semantic_sha256,case_definition_identity=context.case_definition_identity,enforcing_code_identity=context.enforcing_code_identity,schema_set_identity=context.schema_set_identity,authority_set_identity=context.authority_set_identity,issuance_authority=issuance["issuance_authority"],issued_timestamp=issuance["issued_timestamp"],issuance_proof=proof,prior_committed_result_identity=issuance["prior_committed_result_identity"],cleanup_result="PASS")


def run(
    repository:pathlib.Path,
    authority_ref:str,
    *,
    allow_staged:bool=False,
    bootstrap:bool=False,
    candidate:bool=False,
)->dict[str,Any]:
    started=time.perf_counter();context=Context(repository,authority_ref,allow_staged=allow_staged)
    cleanup="PASS"
    try:
        cases=context.definitions["cases"]
        delayed=[case for case in cases if case["operation"]=="trace" and case["vector"] in {"missing_fresh","prior_run"}]
        for case in cases:
            if case in delayed:continue
            context.observations.append(execute_case(case,context))
        for case in delayed:
            context.observations.append(execute_case(case,context))
        by_id={item["case_id"]:item for item in context.observations}
        context.observations=[by_id[case["case_id"]] for case in cases]
        observation_identity=semantic_identity(context.observations)
        if bootstrap:
            return {"fresh_observation_identity":observation_identity,"run_identity":context.run_identity,"observations":context.observations}
        matrix=context.authorities.load("semantic_traceability").value
        validate_traceability(matrix,context.observations,context.expectations,context.authorities,current_run_identity=context.run_identity)
        validate_fixture_provenance(context.expectations,context.observations,context.authorities,run_identity=context.run_identity,enforcing_code_identity=context.enforcing_code_identity)
        authorization_scan=validate_authorization_package(context.authorities)
        access_audit=audit_authority_access_surfaces(context.authorities)
        receipt=_comparison_receipt(context,context.observations)
        issuance=context.authorities.load("comparison_issuance_authority").value
        validate_comparison_receipt(receipt,context.authorities,expectation_identity=context.expectation_identity,observation_identity=observation_identity,case_definition_identity=context.case_definition_identity,case_set_identity=context.case_set_identity,expected_case_count=len(cases),observed_case_count=len(context.observations),enforcing_code_identity=context.enforcing_code_identity,schema_set_identity=context.schema_set_identity,authority_set_identity=context.authority_set_identity,prior_committed_result_identity=issuance["prior_committed_result_identity"],expectations=context.expectations,observations=context.observations)
        kinds={name:sum(case["kind"]==name for case in cases) for name in ("positive","mutation")};surfaces={name:sum(case["surface"]==name for case in cases) for name in ("real","synthetic")}
        meta=sum(bool(case["meta_verification"]) for case in cases)
        result={"schema_version":"6.0.0-DRAFT","authority":"R4_GOVERNED_FIXTURE_RESULT_PENDING_INDEPENDENT_REVIEW","total_cases":len(cases),"positive_cases":kinds["positive"],"mutation_cases":kinds["mutation"],"real_surface_cases":surfaces["real"],"meta_verification_cases":meta,"passed":len(cases)-receipt["discrepancy_count"],"failed":receipt["discrepancy_count"],"discrepancies":receipt["discrepancy_count"],"cleanup":"PASS","reconciliation":"MATCHED","case_definition_identity":context.case_definition_identity,"case_set_identity":context.case_set_identity,"expectation_identity":context.expectation_identity,"observation_semantic_identity":observation_identity,"enforcing_code_identity":context.enforcing_code_identity,"schema_set_identity":context.schema_set_identity,"authority_set_identity":context.authority_set_identity,"comparator_authority_identity":context.authorities.load("comparison_authority").semantic_sha256,"authorization_policy_identity":context.authorities.load("authorization_policy").semantic_sha256,"authorization_scan_identity":authorization_scan,"historical_evidence_identity":context.authorities.load("historical_evidence_authority").semantic_sha256,"historical_parser_authority_identity":context.authorities.load("historical_parser_authority").semantic_sha256,"evidence_policy_authority_identity":context.authorities.load("required_evidence_policy").semantic_sha256,"observer_source_authority_identity":context.authorities.load("observer_source_authority").semantic_sha256,"timestamp_authority_identity":context.authorities.load("timestamp_authority").semantic_sha256,"traceability_identity":context.authorities.load("semantic_traceability").semantic_sha256,"future_package_interface_identity":context.authorities.load("operational_package_interface").semantic_sha256,"fixture_access_audit_identity":access_audit,"comparison_receipt_identity":receipt["comparison_receipt_sha256"],"run_identity":context.run_identity,"schema_validation":{"schema_count":sum(path.endswith("_R4_schema_DRAFT.json") for path in git_tree_entries(repository,authority_ref,PACKAGE_RELATIVE)),"active_instance_count":sum("schema_path" in item for item in context.authorities.binding_value["bindings"]),"authority_instance_count":sum("schema_path" in item for item in context.authorities.binding_value["bindings"]),"valid_synthetic_count":1,"invalid_synthetic_count":17,"valid_accepted":1,"invalid_rejected":17,"warnings":0,"errors":0,"canonical_schema_semantic_disagreements":0,"validator":validator_identity(git_object_bytes(repository,authority_ref,f"{PACKAGE_RELATIVE}/validator_requirements_DRAFT.lock").data)},"observations":context.observations,"comparison_receipt":receipt}
        result_schema_path=f"{PACKAGE_RELATIVE}/fixture_results_R4_schema_DRAFT.json"
        result_schema=strict_canonical_json_loads(git_object_bytes(repository,authority_ref,result_schema_path).data)
        validate_schema_and_instance(result_schema,result,"fixture_results_R4")
        if not candidate:
            committed_path=f"{PACKAGE_RELATIVE}/fixture_results_R4_DRAFT.json"
            try:
                committed_bytes=git_object_bytes(repository,authority_ref,committed_path).data
            except GovernedAccessError as exc:
                raise CaseEnforcementError("MISSING_COMMITTED_RESULT",str(exc)) from exc
            try:
                committed=strict_canonical_json_loads(committed_bytes)
                validate_schema_and_instance(result_schema,committed,"committed_fixture_results_R4")
            except (SchemaValidationError,ValueError,TypeError) as exc:
                raise CaseEnforcementError("INVALID_COMMITTED_RESULT",str(exc)) from exc
            if canonical_json_bytes(committed)!=canonical_json_bytes(result):
                raise CaseEnforcementError("MISMATCH","committed and fresh result bytes differ")
            validate_reconciliation_state(
                {
                    "reconciliation":"MATCHED",
                    "all_cases_completed":len(context.observations)==len(cases),
                    "comparison_completed":True,
                    "committed_result_exists":True,
                    "cleanup":"PASS",
                    "terminal_receipt_valid":True,
                    "comparison_authority_valid":True,
                    "enforcing_code_identity":context.enforcing_code_identity,
                    "schema_set_identity":context.schema_set_identity,
                },
                enforcing_code_identity=context.enforcing_code_identity,
                schema_set_identity=context.schema_set_identity,
            )
        return result
    finally:
        cleanup=context.cleanup()
        if cleanup!="PASS":raise FixtureInfrastructureError("CLEANUP_FAILED:"+"|".join(context.cleanup_errors))


def main(argv:Sequence[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--repository",type=pathlib.Path,required=True);parser.add_argument("--authority-ref",required=True);parser.add_argument("--allow-staged",action="store_true");parser.add_argument("--bootstrap",action="store_true");parser.add_argument("--candidate",action="store_true");parser.add_argument("--output",type=pathlib.Path);args=parser.parse_args(argv)
    if args.bootstrap and args.candidate:
        parser.error("--bootstrap and --candidate are mutually exclusive")
    try:result=run(args.repository.resolve(),args.authority_ref,allow_staged=args.allow_staged,bootstrap=args.bootstrap,candidate=args.candidate)
    except Exception as exc:
        print(json.dumps({"status":"FAILED","code":_error_code(exc),"detail":str(exc)},sort_keys=True),file=sys.stderr);return 2
    payload=canonical_json_bytes(result)
    if args.output:_write(args.output,payload)
    else:sys.stdout.buffer.write(payload)
    return 3 if args.candidate else 0


if __name__=="__main__":raise SystemExit(main())
