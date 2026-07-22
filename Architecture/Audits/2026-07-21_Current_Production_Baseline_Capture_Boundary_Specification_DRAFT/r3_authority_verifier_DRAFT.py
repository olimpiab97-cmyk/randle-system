#!/usr/bin/env python3
"""Independent-byte authority enforcement for governed remediation R4.

The functions in this module never accept a parsed authority object as proof of
its own authenticity.  Authority documents are loaded from a caller-independent
Git commit (or, only while preparing the candidate, the staged index), checked
against the committed role map, schema-validated, and then compared with claims.
"""

from __future__ import annotations

import ast
import copy
import datetime as dt
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from governed_file_access_DRAFT import (
    ByteObservation,
    GovernedAccessError,
    canonical_absolute_path,
    git_object_bytes,
    git_revision_identity,
    git_tree_entries,
    read_binary,
    sha256_bytes,
    stat_regular_file,
)


PACKAGE_RELATIVE = (
    "Architecture/Audits/"
    "2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT"
)
SPECIFICATION_PATH = "Architecture/15_Randle_AI_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT.md"
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_HEX_GIT = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_CLAUSE = re.compile(r"^Clause ID:\s*(CPB-R4-[0-9]{2})\s*$", re.MULTILINE)


class R3AuthorityError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


def require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise R3AuthorityError(code, detail)


def _pairs(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise R3AuthorityError("DUPLICATE_JSON_KEY", key)
        result[key] = value
    return result


def strict_json_loads(data: bytes) -> Any:
    require(not data.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")), "JSON_BOM")
    try:
        text = data.decode("utf-8", "strict")
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(R3AuthorityError("JSON_NONFINITE", token)),
            parse_float=lambda token: (_ for _ in ()).throw(R3AuthorityError("JSON_FLOAT_FORBIDDEN", token)),
        )
        _require_nfc(value)
        return value
    except R3AuthorityError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise R3AuthorityError("INVALID_JSON", str(exc)) from exc


def _require_nfc(value: Any, pointer: str = "") -> None:
    if isinstance(value, str):
        require(unicodedata.normalize("NFC", value) == value, "JSON_NON_NFC", pointer or "/")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _require_nfc(item, f"{pointer}/{index}")
    elif isinstance(value, Mapping):
        for key, item in value.items():
            require(unicodedata.normalize("NFC", key) == key, "JSON_NON_NFC_KEY", f"{pointer}/{key}")
            _require_nfc(item, f"{pointer}/{key}")


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise R3AuthorityError("NONCANONICAL_JSON_VALUE", str(exc)) from exc


def semantic_identity(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def git_blob_identity(data: bytes, object_format: str = "sha1") -> str:
    algorithm = hashlib.sha1 if object_format == "sha1" else hashlib.sha256
    return algorithm(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def validate_authoritative_byte_claim(claim: Mapping[str, Any], observed: ByteObservation) -> None:
    expected = {
        "path": observed.canonical_path,
        "raw_sha256": observed.sha256,
        "byte_size": observed.byte_size,
        "git_blob": observed.git_blob,
    }
    for field, value in expected.items():
        require(claim.get(field) == value, "AUTHORITATIVE_BYTE_CLAIM", field)


def _json_pointer(value: Any, pointer: str) -> Any:
    require(pointer == "" or pointer.startswith("/"), "INVALID_JSON_POINTER", pointer)
    current = value
    for raw in pointer.split("/")[1:]:
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            require(token.isdigit() and int(token) < len(current), "SCHEMA_POINTER_MISSING", pointer)
            current = current[int(token)]
        elif isinstance(current, Mapping):
            require(token in current, "SCHEMA_POINTER_MISSING", pointer)
            current = current[token]
        else:
            raise R3AuthorityError("SCHEMA_POINTER_MISSING", pointer)
    return current


@dataclass(frozen=True)
class BoundDocument:
    role: str
    path: str
    raw: bytes
    value: Mapping[str, Any]
    raw_sha256: str
    git_blob: str
    semantic_sha256: str
    schema_identity: str


class AuthorityRepository:
    """Loads R4 authority bytes from an external Git ref and enforces role bindings."""

    def __init__(self, repository: Path, authority_ref: str, *, allow_staged: bool = False) -> None:
        if authority_ref == ":" and not allow_staged:
            raise R3AuthorityError("STAGED_AUTHORITY_FORBIDDEN")
        self.repository = repository
        self.authority_ref = authority_ref
        binding_path = f"{PACKAGE_RELATIVE}/r4_authority_bindings_DRAFT.json"
        observed = git_object_bytes(repository, authority_ref, binding_path)
        require(observed.data == canonical_json_bytes(strict_json_loads(observed.data)), "BINDING_NOT_CANONICAL")
        parsed = strict_json_loads(observed.data)
        require(isinstance(parsed, Mapping), "INVALID_BINDING_DOCUMENT")
        binding_schema = git_object_bytes(
            repository,
            authority_ref,
            f"{PACKAGE_RELATIVE}/authority_bindings_R4_schema_DRAFT.json",
        )
        schema_value = strict_json_loads(binding_schema.data)
        require(isinstance(schema_value, Mapping), "BINDING_SCHEMA_NOT_OBJECT")
        self._validate_schema(schema_value, parsed, "authority_bindings")
        require(parsed.get("authority_id") == "RANDLE-R4-AUTHORITY-BINDINGS-1", "BINDING_AUTHORITY_ID")
        entries = parsed.get("bindings")
        require(isinstance(entries, list) and entries, "BINDING_SET_EMPTY")
        self.binding_observation = observed
        self.binding_value = parsed
        self._bindings: dict[str, Mapping[str, Any]] = {}
        for entry in entries:
            require(isinstance(entry, Mapping), "INVALID_BINDING_ENTRY")
            role = entry.get("role")
            require(isinstance(role, str) and role not in self._bindings, "DUPLICATE_BINDING_ROLE", str(role))
            self._bindings[role] = entry

    @property
    def identity(self) -> str:
        excluded = {
            "semantic_traceability",
            "traceability_narrative",
            "remediation_report",
            "architecture_impact",
            "canonical_delta",
            "package_index",
        }
        return semantic_identity(
            {
                "authority_model": "RANDLE-R4-EXECUTION-AUTHORITY-SET-1",
                "bindings": [
                    {
                        "role": role,
                        "path": self._bindings[role].get("path"),
                        "git_blob": self._bindings[role].get("git_blob"),
                        "raw_sha256": self._bindings[role].get("raw_sha256"),
                        "semantic_sha256": self._bindings[role].get("semantic_sha256"),
                    }
                    for role in sorted(set(self._bindings) - excluded)
                ],
            }
        )

    def binding(self, role: str) -> Mapping[str, Any]:
        require(role in self._bindings, "AUTHORITY_ROLE_UNBOUND", role)
        return self._bindings[role]

    def observe_bytes(self, role: str) -> ByteObservation:
        """Load non-JSON or JSON bytes only after the immutable role binding matches."""

        binding = self.binding(role)
        path = binding.get("path")
        require(isinstance(path, str), "INVALID_ROLE_BINDING", role)
        observed = git_object_bytes(self.repository, self.authority_ref, path)
        require(observed.sha256 == binding.get("raw_sha256"), "AUTHORITY_RAW_SHA256", role)
        require(observed.git_blob == binding.get("git_blob"), "AUTHORITY_GIT_BLOB", role)
        return observed

    def load(self, role: str) -> BoundDocument:
        binding = self.binding(role)
        observed = self.observe_bytes(role)
        path = binding.get("path")
        schema_path = binding.get("schema_path")
        require(isinstance(path, str) and isinstance(schema_path, str), "INVALID_ROLE_BINDING", role)
        value = strict_json_loads(observed.data)
        require(isinstance(value, Mapping), "AUTHORITY_NOT_OBJECT", role)
        require(observed.data == canonical_json_bytes(value), "AUTHORITY_NOT_CANONICAL", role)
        semantic = semantic_identity(value)
        require(semantic == binding.get("semantic_sha256"), "AUTHORITY_SEMANTIC_IDENTITY", role)
        schema_observed = git_object_bytes(self.repository, self.authority_ref, schema_path)
        require(schema_observed.sha256 == binding.get("schema_raw_sha256"), "AUTHORITY_SCHEMA_RAW_SHA256", role)
        schema = strict_json_loads(schema_observed.data)
        require(isinstance(schema, Mapping), "AUTHORITY_SCHEMA_NOT_OBJECT", role)
        self._validate_schema(schema, value, role)
        return BoundDocument(
            role=role,
            path=path,
            raw=observed.data,
            value=value,
            raw_sha256=observed.sha256,
            git_blob=observed.git_blob or "",
            semantic_sha256=semantic,
            schema_identity=schema_observed.sha256,
        )

    @staticmethod
    def _validate_schema(schema: Mapping[str, Any], value: Mapping[str, Any], role: str) -> None:
        try:
            from jsonschema import Draft202012Validator, FormatChecker

            Draft202012Validator.check_schema(schema)
            errors = sorted(
                Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value),
                key=lambda error: (list(error.absolute_path), error.message),
            )
        except Exception as exc:
            if isinstance(exc, R3AuthorityError):
                raise
            raise R3AuthorityError("SCHEMA_VALIDATOR_FAILURE", f"{role}:{exc}") from exc
        require(not errors, "AUTHORITY_SCHEMA_INVALID", f"{role}:{errors[0].message if errors else ''}")


def validate_reconciliation_state(
    state: Mapping[str, Any],
    *,
    enforcing_code_identity: str,
    schema_set_identity: str,
) -> None:
    allowed = {
        "MATCHED",
        "NOT_YET_RECORDED",
        "MISMATCH",
        "MISSING_COMMITTED_RESULT",
        "INVALID_COMMITTED_RESULT",
        "COMPARATOR_NOT_AUTHORIZED",
    }
    status = state.get("reconciliation")
    require(status in allowed, "INVALID_RECONCILIATION_STATE", str(status))
    require(status == "MATCHED", str(status))
    require(state.get("all_cases_completed") is True, "CASES_INCOMPLETE")
    require(state.get("comparison_completed") is True, "COMPARISON_INCOMPLETE")
    require(state.get("committed_result_exists") is True, "MISSING_COMMITTED_RESULT")
    require(state.get("cleanup") == "PASS", "CLEANUP_FAILED")
    require(state.get("terminal_receipt_valid") is True, "TERMINAL_RECEIPT_INVALID")
    require(state.get("comparison_authority_valid") is True, "COMPARATOR_NOT_AUTHORIZED")
    require(state.get("enforcing_code_identity") == enforcing_code_identity, "ENFORCING_CODE_IDENTITY_CHANGED")
    require(state.get("schema_set_identity") == schema_set_identity, "SCHEMA_SET_IDENTITY_CHANGED")


def validate_separate_binding(
    terminal_record: Mapping[str, Any],
    obligation: Mapping[str, Any],
    authorities: AuthorityRepository,
) -> None:
    policy_document = authorities.load("separate_binding_policy")
    review_document = authorities.load("review_authority_policy")
    role_document = authorities.load("authority_role_map")
    evidence_document = authorities.load("required_evidence_policy")
    registry_document = authorities.load("selection_rule_registry")
    enumeration_document = authorities.load("governed_enumeration_policy")
    policy = policy_document.value
    review_policy = review_document.value
    role_map = role_document.value
    require(terminal_record.get("terminal_disposition") == "SEPARATE_AND_BIND", "INVALID_TERMINAL_DISPOSITION")
    artifact_class = terminal_record.get("artifact_class")
    rules = policy.get("artifact_classes", {})
    require(artifact_class in rules, "SEPARATE_CLASS_UNAUTHORIZED", str(artifact_class))
    require(artifact_class in enumeration_document.value.get("authorized_artifact_classes", []), "SEPARATE_ENUMERATION_CLASS")
    require(
        terminal_record.get("rule_id") in {item.get("rule_id") for item in registry_document.value.get("rules", [])},
        "SEPARATE_RULE_UNAUTHORIZED",
    )
    rule = rules[artifact_class]
    authority_id = rule.get("authorized_authority_id")
    require(authority_id in role_map.get("authority_ids", []), "SEPARATE_AUTHORITY_ROLE_UNBOUND")
    review_requirement = rule.get("review_requirement")
    require(review_requirement in review_policy.get("allowed_review_requirements", []), "SEPARATE_REVIEW_REQUIREMENT")
    require(review_requirement != "SELF_REVIEW_ALLOWED", "SEPARATE_SELF_REVIEW")
    evidence_rule = next(
        (item for item in evidence_document.value.get("rules", []) if item.get("artifact_class") == artifact_class),
        None,
    )
    require(isinstance(evidence_rule, Mapping), "SEPARATE_EVIDENCE_POLICY_MISSING")
    expected_evidence = [
        {
            "role": role,
            "class": evidence_class,
            "external_root_id": rule.get("external_root_id"),
            "immutability_requirement": rule.get("immutability_requirement"),
        }
        for role, evidence_class in zip(
            evidence_rule.get("required_roles", []),
            evidence_rule.get("required_classes", []),
            strict=True,
        )
    ]
    expected: dict[str, Any] = {
        "authority_id": authority_id,
        "capture_form": rule.get("capture_form"),
        "recovery_requirement": rule.get("recovery_requirement"),
        "semantic_purpose": rule.get("semantic_purpose"),
        "immutability_requirement": rule.get("immutability_requirement"),
        "review_requirement": review_requirement,
        "reviewer_role": review_policy.get("required_reviewer_role"),
        "reviewer_independence": review_policy.get("independence_requirement"),
        "review_decision": review_policy.get("required_decision"),
        "review_object_identity": review_policy.get("fixture_review_object_identity"),
        "review_issued_timestamp": review_policy.get("fixture_review_issued_timestamp"),
        "evidence": expected_evidence,
        "derivation_authorities": {
            "selection_rule_registry": registry_document.semantic_sha256,
            "separate_binding_policy": policy_document.semantic_sha256,
            "authority_role_map": role_document.semantic_sha256,
            "required_evidence_policy": evidence_document.semantic_sha256,
            "governed_enumeration_policy": enumeration_document.semantic_sha256,
            "review_authority_policy": review_document.semantic_sha256,
        },
    }
    expected["semantic_root"] = semantic_identity(expected)
    require(obligation == expected, "SEPARATE_OBLIGATION_MISMATCH")


def parse_authority_timestamp(value: Any, context: str) -> dt.datetime:
    require(isinstance(value, str), "TIMESTAMP_NOT_TEXT", context)
    try:
        from rfc3339_validator import validate_rfc3339
    except ImportError as exc:
        raise R3AuthorityError("FORMAT_DEPENDENCY_UNAVAILABLE", "rfc3339-validator") from exc
    require(bool(validate_rfc3339(value)), "INVALID_RFC3339", context)
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise R3AuthorityError("INVALID_RFC3339", context) from exc
    require(parsed.tzinfo is not None, "TIMESTAMP_TIMEZONE_MISSING", context)
    return parsed.astimezone(dt.timezone.utc)


def validate_timestamp_chronology(
    timestamps: Mapping[str, Any],
    *,
    ordered_fields: Sequence[str],
    cutoff: str,
) -> None:
    values = [parse_authority_timestamp(timestamps.get(field), field) for field in ordered_fields]
    require(values == sorted(values), "TIMESTAMP_CHRONOLOGY")
    require(values[-1] <= parse_authority_timestamp(cutoff, "cutoff"), "TIMESTAMP_AFTER_CUTOFF")


def validate_frozen_timestamp_claim(claim: str, authorities: AuthorityRepository) -> None:
    timestamp = authorities.load("timestamp_authority").value
    require(claim == timestamp.get("freeze_timestamp"), "TIMESTAMP_AUTHORITY_MISMATCH")
    parse_authority_timestamp(claim, "frozen-timestamp-claim")


def validate_timestamp_authority_claim(claim: Mapping[str, Any], authorities: AuthorityRepository) -> None:
    document = authorities.load("timestamp_authority")
    expected = {
        "authority": document.value,
        "path": document.path,
        "raw_sha256": document.raw_sha256,
        "git_blob": document.git_blob,
        "semantic_sha256": document.semantic_sha256,
        "role_map_binding": authorities.load("authority_role_map").semantic_sha256,
        "trust_root_binding": authorities.load("timestamp_trust_root").semantic_sha256,
    }
    require(claim == expected, "TIMESTAMP_AUTHORITY_CLAIM_MISMATCH")


def validate_attempt_prefix_authority(authorities: AuthorityRepository) -> BoundDocument:
    document = authorities.load("attempt_prefix_authority")
    value = document.value
    require(value.get("authority_id") == "RANDLE-R4-ATTEMPT-PREFIX-1", "PREFIX_AUTHORITY_ID")
    attempts = value.get("accepted_attempt_ids")
    require(isinstance(attempts, list) and len(attempts) == value.get("accepted_prefix_count"), "PREFIX_COUNT")
    require(len(attempts) == len(set(attempts)), "PREFIX_ATTEMPT_DUPLICATE")
    require(_HEX_64.fullmatch(str(value.get("previous_ledger_root"))) is not None, "PREFIX_PREVIOUS_ROOT")
    return document


def validate_attempt_prefix_claim(claim: Mapping[str, Any], authorities: AuthorityRepository) -> None:
    document = validate_attempt_prefix_authority(authorities)
    binding = authorities.binding("attempt_prefix_authority")
    expected = {
        "authority_id": document.value.get("authority_id"),
        "accepted_prefix_count": document.value.get("accepted_prefix_count"),
        "accepted_attempt_ids": document.value.get("accepted_attempt_ids"),
        "previous_ledger_root": document.value.get("previous_ledger_root"),
        "schema_identity": document.value.get("schema_identity"),
        "path": document.path,
        "raw_sha256": document.raw_sha256,
        "git_blob": document.git_blob,
        "semantic_sha256": document.semantic_sha256,
        "role_map_binding": semantic_identity(binding),
    }
    for field, value in expected.items():
        require(claim.get(field) == value, "PREFIX_CLAIM_MISMATCH", field)


def validate_evidence_policy_authority(authorities: AuthorityRepository) -> BoundDocument:
    document = authorities.load("required_evidence_policy")
    value = document.value
    require(value.get("policy_id") == "RANDLE-R4-REQUIRED-EVIDENCE-1", "EVIDENCE_POLICY_ID")
    rules = value.get("rules")
    require(isinstance(rules, list) and rules, "EVIDENCE_POLICY_RULES")
    for rule in rules:
        for field in (
            "artifact_class",
            "required_roles",
            "required_classes",
            "cardinality",
            "conditional_rule",
            "semantic_purpose",
            "required_for_recovery",
            "source_attempt_rule",
            "capture_pass_rule",
            "immutability_rule",
        ):
            require(field in rule, "EVIDENCE_POLICY_FIELD", field)
    return document


def validate_evidence_policy_claim(claim: Mapping[str, Any], authorities: AuthorityRepository) -> None:
    document = validate_evidence_policy_authority(authorities)
    binding = authorities.binding("required_evidence_policy")
    expected = {
        "policy": document.value,
        "path": document.path,
        "raw_sha256": document.raw_sha256,
        "git_blob": document.git_blob,
        "semantic_sha256": document.semantic_sha256,
        "role_map_binding": semantic_identity(binding),
    }
    for field, value in expected.items():
        require(claim.get(field) == value, "EVIDENCE_POLICY_CLAIM_MISMATCH", field)


def verify_freeze_claim(receipt: Mapping[str, Any], authorities: AuthorityRepository) -> None:
    attempt_document = authorities.load("attempt_authorization")
    timestamp_document = authorities.load("timestamp_authority")
    trust_document = authorities.load("timestamp_trust_root")
    role_document = authorities.load("authority_role_map")
    freeze_document = authorities.load("freeze_receipt_authority")
    attempt = attempt_document.value
    timestamp = timestamp_document.value
    prefix = validate_attempt_prefix_authority(authorities)
    evidence = validate_evidence_policy_authority(authorities)
    trusted_issuer = next(
        (item for item in trust_document.value.get("trusted_issuers", []) if item.get("issuer_id") == timestamp.get("issuer_id")),
        None,
    )
    require(isinstance(trusted_issuer, Mapping), "TIMESTAMP_ISSUER_UNTRUSTED")
    require(timestamp.get("issuer_role") == trusted_issuer.get("issuer_role"), "TIMESTAMP_ISSUER_ROLE")
    require(timestamp.get("issuer_capability") in trusted_issuer.get("capabilities", []), "TIMESTAMP_ISSUER_CAPABILITY")
    require(timestamp.get("issuer_id") != timestamp.get("authority_id"), "TIMESTAMP_SELF_ISSUED")
    require(timestamp.get("authorized_attempt_id") == attempt.get("attempt_id"), "TIMESTAMP_ATTEMPT_ID")
    require(timestamp.get("sequence") == attempt.get("attempt_sequence"), "TIMESTAMP_SEQUENCE")
    require(timestamp.get("role_map_identity") == role_document.semantic_sha256, "TIMESTAMP_ROLE_MAP_BINDING")
    require(timestamp.get("trust_root_identity") == trust_document.semantic_sha256, "TIMESTAMP_TRUST_ROOT_BINDING")
    require(receipt.get("attempt_id") == attempt.get("attempt_id"), "FREEZE_ATTEMPT_ID")
    require(receipt.get("attempt_sequence") == attempt.get("attempt_sequence"), "FREEZE_ATTEMPT_SEQUENCE")
    require(receipt.get("issued_timestamp") == timestamp.get("freeze_timestamp"), "FREEZE_TIMESTAMP")
    require(receipt.get("issuance_authority") == attempt.get("issuance_authority"), "FREEZE_ISSUANCE_AUTHORITY")
    require(receipt.get("timestamp_issuer_id") == trusted_issuer.get("issuer_id"), "FREEZE_TIMESTAMP_ISSUER")
    require(receipt.get("timestamp_issuer_role") == trusted_issuer.get("issuer_role"), "FREEZE_TIMESTAMP_ISSUER_ROLE")
    require(receipt.get("timestamp_issuer_capability") == timestamp.get("issuer_capability"), "FREEZE_TIMESTAMP_CAPABILITY")
    require(attempt.get("status") == "AUTHORIZED_FOR_SPECIFICATION_FIXTURE_ONLY", "FREEZE_ATTEMPT_NOT_AUTHORIZED")
    require(attempt.get("reused") is False, "FREEZE_ATTEMPT_REUSED")
    issuance = parse_authority_timestamp(attempt.get("issued_timestamp"), "attempt-issued")
    expiry = parse_authority_timestamp(attempt.get("expires_timestamp"), "attempt-expires")
    valid_from = parse_authority_timestamp(timestamp.get("valid_from"), "timestamp-valid-from")
    valid_until = parse_authority_timestamp(timestamp.get("valid_until"), "timestamp-valid-until")
    freeze = parse_authority_timestamp(timestamp.get("freeze_timestamp"), "freeze-issued")
    cutoff = parse_authority_timestamp(timestamp.get("freeze_cutoff"), "freeze-cutoff")
    prior = parse_authority_timestamp(timestamp.get("chronology_predecessor"), "prior-ledger")
    issued = parse_authority_timestamp(timestamp.get("issued_timestamp"), "timestamp-issued")
    require(prior <= issuance <= valid_from <= issued <= freeze <= expiry <= valid_until <= cutoff, "FREEZE_CHRONOLOGY")
    expected = {
        "attempt_authorization_identity": attempt_document.semantic_sha256,
        "timestamp_authority_identity": timestamp_document.semantic_sha256,
        "timestamp_trust_root_identity": trust_document.semantic_sha256,
        "attempt_prefix_authority_identity": prefix.semantic_sha256,
        "evidence_policy_identity": evidence.semantic_sha256,
        "specification_authority_identity": authorities.binding("specification").get("raw_sha256"),
    }
    for field, value in expected.items():
        require(receipt.get(field) == value, "FREEZE_EXTERNAL_AUTHORITY", field)
    semantic = {key: value for key, value in receipt.items() if key != "freeze_receipt_sha256"}
    require(receipt.get("freeze_receipt_sha256") == semantic_identity(semantic), "FREEZE_RECEIPT_HASH")
    require(receipt == freeze_document.value, "FREEZE_RECEIPT_AUTHORITY_MISMATCH")


def verify_historical_classification(
    classification: Mapping[str, Any],
    authorities: AuthorityRepository,
) -> Mapping[str, Any]:
    authority_document = authorities.load("historical_evidence_authority")
    parser_document = authorities.load("historical_parser_authority")
    authority = authority_document.value
    parser_authority = parser_document.value
    parser_source = authorities.observe_bytes("historical_log_parser")
    require(parser_source.canonical_path == parser_authority.get("parser_source_path"), "HISTORICAL_PARSER_PATH")
    require(parser_source.git_blob == parser_authority.get("parser_git_blob"), "HISTORICAL_PARSER_BLOB")
    require(parser_source.sha256 == parser_authority.get("parser_raw_sha256"), "HISTORICAL_PARSER_HASH")
    require(parser_authority.get("accepted_historical_evidence_authority_id") == authority.get("authority_id"), "HISTORICAL_PARSER_EVIDENCE_AUTHORITY")
    require(authority.get("parser_authority_identity") == parser_document.semantic_sha256, "HISTORICAL_EVIDENCE_PARSER_AUTHORITY")
    physical = authority.get("authorized_physical_path")
    require(isinstance(physical, str), "HISTORICAL_AUTHORITY_PATH")
    require(classification.get("logical_evidence_id") == authority.get("logical_evidence_id"), "HISTORICAL_LOGICAL_ID")
    require(classification.get("full_log_path") == physical, "HISTORICAL_CLAIMED_PATH")
    observed = read_binary(physical)
    require(observed.byte_size == authority.get("byte_size"), "HISTORICAL_SIZE")
    require(observed.sha256.upper() == authority.get("sha256"), "HISTORICAL_HASH")
    require(authority.get("source_external_root_id") == "RANDLE-RUNTIME-PROVENANCE", "HISTORICAL_EXTERNAL_ROOT")
    namespace: dict[str, Any] = {
        "__name__": str(parser_authority.get("parser_module_identity")),
        "__file__": str(parser_authority.get("parser_source_path")),
    }
    try:
        exec(compile(parser_source.data, str(parser_authority.get("parser_source_path")), "exec"), namespace, namespace)
    except Exception as exc:
        raise R3AuthorityError("HISTORICAL_PARSER_LOAD", str(exc)) from exc
    parser_symbol = parser_authority.get("parser_symbol")
    parser = namespace.get(parser_symbol)
    require(callable(parser), "HISTORICAL_PARSER_SYMBOL")
    require(namespace.get("PARSER_VERSION") == parser_authority.get("parser_version"), "HISTORICAL_PARSER_VERSION")
    require(namespace.get("NORMALIZATION_RULE") == parser_authority.get("normalization_rules"), "HISTORICAL_PARSER_NORMALIZATION")
    parsed = parser(observed.data, physical)
    require(isinstance(parsed, Mapping), "HISTORICAL_PARSE_RESULT")
    arithmetic = parsed.get("outcome_count_by_status")
    locations = semantic_identity(
        [
            {
                "event": item.get("event_identity"),
                "source": item.get("source_log_location"),
                "summary": item.get("summary_log_location"),
            }
            for item in parsed.get("outcomes", [])
        ]
    )
    require(arithmetic == classification.get("outcome_arithmetic"), "HISTORICAL_OUTCOME_ARITHMETIC")
    require(locations == classification.get("source_locations_identity"), "HISTORICAL_SOURCE_LOCATIONS")
    require(parsed.get("source_total") == 753, "HISTORICAL_TOTAL")
    require(parsed.get("failed_outcome_count") == 179, "HISTORICAL_FAILED_TOTAL")
    for outcome in parsed.get("outcomes", []):
        location = outcome.get("source_log_location", {})
        require(
            isinstance(location.get("byte_start"), int)
            and isinstance(location.get("byte_end"), int)
            and 0 <= location["byte_start"] < location["byte_end"] <= observed.byte_size,
            "HISTORICAL_SOURCE_LOCATION_RANGE",
        )
    return parsed


def validate_historical_authority_claim(claim: Mapping[str, Any], authorities: AuthorityRepository) -> None:
    document = authorities.load("historical_evidence_authority")
    binding = authorities.binding("historical_evidence_authority")
    expected = {
        "authority": document.value,
        "path": document.path,
        "raw_sha256": document.raw_sha256,
        "git_blob": document.git_blob,
        "semantic_sha256": document.semantic_sha256,
        "role_map_binding": semantic_identity(binding),
    }
    for field, value in expected.items():
        require(claim.get(field) == value, "HISTORICAL_AUTHORITY_CLAIM_MISMATCH", field)


def validate_historical_parser_claim(claim: Mapping[str, Any], authorities: AuthorityRepository) -> None:
    document = authorities.load("historical_parser_authority")
    source = authorities.observe_bytes("historical_log_parser")
    expected = {
        "authority": document.value,
        "authority_path": document.path,
        "authority_raw_sha256": document.raw_sha256,
        "authority_git_blob": document.git_blob,
        "authority_semantic_sha256": document.semantic_sha256,
        "parser_source_path": source.canonical_path,
        "parser_source_raw_sha256": source.sha256,
        "parser_source_git_blob": source.git_blob,
    }
    require(claim == expected, "HISTORICAL_PARSER_CLAIM_MISMATCH")


def append_only_event_root(events: Sequence[Mapping[str, Any]], initial_root: str) -> str:
    root = initial_root
    for sequence, event in enumerate(events, 1):
        require(event.get("sequence") == sequence, "OBSERVER_EVENT_SEQUENCE")
        root = semantic_identity({"previous_root": root, "event": event})
    return root


def verify_observer_source(
    issuance: Mapping[str, Any],
    authorities: AuthorityRepository,
) -> Mapping[str, Any]:
    policy_document = authorities.load("observer_source_authority")
    freeze_document = authorities.load("freeze_receipt_authority")
    timestamp_document = authorities.load("timestamp_authority")
    policy = policy_document.value
    require(issuance.get("source_id") == policy.get("source_id"), "OBSERVER_SOURCE_ID")
    require(issuance.get("attempt_id") == authorities.load("attempt_authorization").value.get("attempt_id"), "OBSERVER_ATTEMPT_ID")
    require(issuance.get("authorized_logical_path") == policy.get("authorized_package_path"), "OBSERVER_PATH_SUBSTITUTION")
    require(policy.get("accepted_freeze_receipt_identity") == freeze_document.semantic_sha256, "OBSERVER_FREEZE_RECEIPT_AUTHORITY")
    require(issuance.get("accepted_freeze_receipt_identity") == freeze_document.semantic_sha256, "OBSERVER_ISSUANCE_FREEZE_RECEIPT")
    require(policy.get("accepted_freeze_authority_identity") == freeze_document.semantic_sha256, "OBSERVER_FREEZE_AUTHORITY")
    require(issuance.get("accepted_freeze_authority_identity") == freeze_document.semantic_sha256, "OBSERVER_ISSUANCE_FREEZE_AUTHORITY")
    require(policy.get("timestamp_authority_identity") == timestamp_document.semantic_sha256, "OBSERVER_TIMESTAMP_AUTHORITY")
    observed = authorities.observe_bytes("observer_event_source")
    require(observed.sha256 == policy.get("source_raw_sha256"), "OBSERVER_SOURCE_HASH")
    require(observed.sha256 == issuance.get("source_sha256"), "OBSERVER_ISSUANCE_HASH")
    require(observed.byte_size == issuance.get("source_size"), "OBSERVER_SOURCE_SIZE")
    events = [strict_json_loads(line + b"\n") for line in observed.data.splitlines() if line]
    require(all(isinstance(event, Mapping) for event in events), "OBSERVER_EVENT_INVALID")
    root = append_only_event_root(events, policy.get("initial_root"))
    require(root == policy.get("append_only_root"), "OBSERVER_POLICY_ROOT")
    require(root == issuance.get("append_only_root"), "OBSERVER_APPEND_ONLY_ROOT")
    require([event.get("event_type") for event in events] == policy.get("expected_event_sequence"), "OBSERVER_EXPECTED_SEQUENCE")
    require(all(event.get("attempt_id") == issuance.get("attempt_id") for event in events), "OBSERVER_EVENT_ATTEMPT")
    require(all(event.get("freeze_receipt_identity") == freeze_document.semantic_sha256 for event in events), "OBSERVER_EVENT_FREEZE_RECEIPT")
    start = parse_authority_timestamp(policy.get("source_start_timestamp"), "observer-start")
    cutoff = parse_authority_timestamp(policy.get("source_cutoff_timestamp"), "observer-cutoff")
    event_times = [parse_authority_timestamp(event.get("timestamp"), "observer-event") for event in events]
    require(all(start <= event_time <= cutoff for event_time in event_times), "OBSERVER_EVENT_OUTSIDE_WINDOW")
    require(issuance.get("event_source_implementation_identity") == policy.get("event_source_implementation_identity"), "OBSERVER_IMPLEMENTATION")
    require(issuance.get("reader_implementation_identity") == policy.get("reader_implementation_identity"), "OBSERVER_READER_IMPLEMENTATION")
    require(issuance.get("source_start_sequence") == policy.get("source_start_sequence"), "OBSERVER_START_SEQUENCE")
    require(issuance.get("source_cutoff_sequence") == policy.get("source_cutoff_sequence"), "OBSERVER_CUTOFF_SEQUENCE")
    require(issuance.get("source_issuance_event") == policy.get("source_issuance_event"), "OBSERVER_ISSUANCE_EVENT")
    return {"events": events, "append_only_root": root, "source_sha256": observed.sha256, "source_kind": observed.source_kind}


def validate_comparison_receipt(
    receipt: Mapping[str, Any] | None,
    authorities: AuthorityRepository,
    *,
    expectation_identity: str,
    observation_identity: str,
    case_definition_identity: str,
    case_set_identity: str,
    expected_case_count: int,
    observed_case_count: int,
    enforcing_code_identity: str,
    schema_set_identity: str,
    authority_set_identity: str,
    prior_committed_result_identity: str,
    expectations: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
) -> None:
    require(isinstance(receipt, Mapping), "MISSING_COMPARISON_RECEIPT")
    receipt_schema = strict_json_loads(
        git_object_bytes(
            authorities.repository,
            authorities.authority_ref,
            f"{PACKAGE_RELATIVE}/terminal_comparison_receipt_R4_schema_DRAFT.json",
        ).data
    )
    require(isinstance(receipt_schema, Mapping), "COMPARISON_RECEIPT_SCHEMA")
    AuthorityRepository._validate_schema(receipt_schema, receipt, "terminal_comparison_receipt")
    authority_document = authorities.load("comparison_authority")
    policy_document = authorities.load("comparison_policy")
    issuance_document = authorities.load("comparison_issuance_authority")
    authority = authority_document.value
    policy = policy_document.value
    issuance = issuance_document.value
    comparator_binding = authorities.binding("comparison_engine")
    require(authority.get("comparator_raw_sha256") == comparator_binding.get("raw_sha256"), "COMPARATOR_CODE_HASH")
    require(authority.get("comparator_git_blob") == comparator_binding.get("git_blob"), "COMPARATOR_CODE_BLOB")
    require(receipt.get("comparator_authority_id") == authority.get("authority_id"), "COMPARATOR_AUTHORITY_ID")
    require(receipt.get("comparator_identity") == authority.get("comparator_identity"), "COMPARATOR_IDENTITY")
    require(receipt.get("comparator_code_blob") == authority.get("comparator_git_blob"), "COMPARATOR_CODE_BLOB")
    require(receipt.get("comparator_raw_sha256") == authority.get("comparator_raw_sha256"), "COMPARATOR_CODE_HASH")
    require(receipt.get("interface_version") == authority.get("comparator_interface_version"), "COMPARATOR_INTERFACE_VERSION")
    require(receipt.get("completed") is True, "COMPARISON_INCOMPLETE")
    require(receipt.get("comparison_policy_identity") == policy_document.semantic_sha256, "COMPARISON_POLICY_IDENTITY")
    require(receipt.get("case_definition_identity") == case_definition_identity, "COMPARISON_CASE_DEFINITION_IDENTITY")
    require(receipt.get("case_set_identity") == case_set_identity, "COMPARISON_CASE_SET_IDENTITY")
    require(receipt.get("expected_case_count") == expected_case_count, "COMPARISON_EXPECTED_CASE_COUNT")
    require(receipt.get("observed_case_count") == observed_case_count, "COMPARISON_OBSERVED_CASE_COUNT")
    require(expected_case_count == observed_case_count, "COMPARISON_CASE_COUNT_MISMATCH")
    require(receipt.get("expectation_identity") == expectation_identity, "COMPARISON_EXPECTATION_IDENTITY")
    require(receipt.get("observation_identity") == observation_identity, "COMPARISON_OBSERVATION_IDENTITY")
    require(receipt.get("enforcing_code_identity") == enforcing_code_identity, "COMPARISON_ENFORCING_CODE_IDENTITY")
    require(receipt.get("schema_set_identity") == schema_set_identity, "COMPARISON_SCHEMA_SET_IDENTITY")
    require(receipt.get("authority_set_identity") == authority_set_identity, "COMPARISON_AUTHORITY_SET_IDENTITY")
    require(receipt.get("issuance_authority") == issuance.get("issuance_authority"), "COMPARISON_ISSUANCE_AUTHORITY")
    require(receipt.get("issued_timestamp") == issuance.get("issued_timestamp"), "COMPARISON_ISSUED_TIMESTAMP")
    require(receipt.get("prior_committed_result_identity") == prior_committed_result_identity, "COMPARISON_PRIOR_RESULT")
    require(issuance.get("authorized_comparator_authority_id") == authority.get("authority_id"), "COMPARISON_ISSUANCE_COMPARATOR")
    expected_proof = semantic_identity(
        {
            "issuance_authority": issuance.get("issuance_authority"),
            "issued_timestamp": issuance.get("issued_timestamp"),
            "authorized_comparator_authority_id": issuance.get("authorized_comparator_authority_id"),
            "capability": issuance.get("capability"),
            "trust_root_id": issuance.get("trust_root_id"),
        }
    )
    require(receipt.get("issuance_proof") == expected_proof, "COMPARISON_ISSUANCE_PROOF")
    require(receipt.get("terminal_status") in policy.get("terminal_statuses", []), "COMPARISON_STATUS")
    require(receipt.get("terminal_status") == "MATCHED", "COMPARISON_NOT_MATCHED")
    require(receipt.get("cleanup_result") == "PASS", "COMPARISON_CLEANUP")
    discrepancies = receipt.get("discrepancies")
    require(isinstance(discrepancies, list), "COMPARISON_DISCREPANCIES")
    require(receipt.get("discrepancy_count") == len(discrepancies) == 0, "COMPARISON_DISCREPANCY_COUNT")
    require(receipt.get("discrepancy_identity") == semantic_identity(discrepancies), "COMPARISON_DISCREPANCY_IDENTITY")
    expected_by_id = {item.get("case_id"): item for item in expectations.get("cases", [])}
    observed_by_id = {item.get("case_id"): item for item in observations}
    require(len(expected_by_id) == len(expectations.get("cases", [])), "DUPLICATE_EXPECTATION")
    require(len(observed_by_id) == len(observations), "DUPLICATE_OBSERVATION")
    derived_discrepancies: list[dict[str, Any]] = []
    if set(expected_by_id) != set(observed_by_id):
        derived_discrepancies.append({"case_id": "<case-set>", "field": "case_set", "expected": sorted(expected_by_id), "observed": sorted(observed_by_id)})
    comparison_fields = (
        ("expected_status", "actual_status"),
        ("expected_code", "observed_code"),
        ("expected_enforcing_function", "observed_enforcing_function"),
        ("expected_authority_source", "observed_authority_source"),
        ("expected_evidence_obligation", "observed_evidence_result"),
        ("immutable_input_identity", "authoritative_input_identity"),
    )
    for case_id in sorted(set(expected_by_id) & set(observed_by_id)):
        for expected_field, observed_field in comparison_fields:
            if expected_by_id[case_id].get(expected_field) != observed_by_id[case_id].get(observed_field):
                derived_discrepancies.append({"case_id": case_id, "field": observed_field, "expected": expected_by_id[case_id].get(expected_field), "observed": observed_by_id[case_id].get(observed_field)})
    require(discrepancies == derived_discrepancies, "COMPARISON_DISCREPANCIES_DERIVATION")
    expected_fresh = semantic_identity(
        {
            "observation_identity": observation_identity,
            "case_set_identity": case_set_identity,
            "enforcing_code_identity": enforcing_code_identity,
            "schema_set_identity": schema_set_identity,
            "authority_set_identity": authority_set_identity,
        }
    )
    require(receipt.get("current_fresh_result_identity") == expected_fresh, "COMPARISON_FRESH_RESULT")
    semantic = {key: value for key, value in receipt.items() if key != "comparison_receipt_sha256"}
    require(receipt.get("comparison_receipt_sha256") == semantic_identity(semantic), "COMPARISON_RECEIPT_HASH")


def validate_fixture_provenance(
    expectations: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    authorities: AuthorityRepository,
    *,
    run_identity: str,
    enforcing_code_identity: str,
) -> None:
    expectation_authority = authorities.load("expectation_authority").value
    observation_authority = authorities.load("observation_authority").value
    provenance = expectations.get("provenance")
    require(isinstance(provenance, Mapping), "EXPECTATION_PROVENANCE_MISSING")
    expected_expectation_provenance = {
        "source_kind": "INDEPENDENT_STATIC_EXPECTATION",
        "authoring_authority": expectation_authority.get("authoring_authority"),
        "expectation_schema_role": expectation_authority.get("expectation_schema_role"),
        "case_definition_role": expectation_authority.get("case_definition_role"),
        "normative_source_role": expectation_authority.get("normative_source_role"),
        "observation_dependency": "NONE",
        "authored_timestamp": expectation_authority.get("authored_timestamp"),
    }
    require(provenance == expected_expectation_provenance, "EXPECTATION_PROVENANCE_INVALID")
    expectation_time = parse_authority_timestamp(provenance.get("authored_timestamp"), "expectation-authored")
    observation_time = parse_authority_timestamp(observation_authority.get("execution_issued_timestamp"), "observation-issued")
    require(expectation_time < observation_time, "EXPECTATION_AFTER_OBSERVATION")
    expectation_root = semantic_identity(provenance)
    expected_cases = {item.get("case_id"): item for item in expectations.get("cases", [])}
    require(len(expected_cases) == len(expectations.get("cases", [])), "DUPLICATE_EXPECTATION")
    for observation in observations:
        case_id = observation.get("case_id")
        require(case_id in expected_cases, "OBSERVATION_WITHOUT_EXPECTATION", str(case_id))
        observed_provenance = observation.get("provenance")
        require(isinstance(observed_provenance, Mapping), "OBSERVATION_PROVENANCE_MISSING", str(case_id))
        require(observed_provenance.get("provenance_root") != expectation_root, "PROVENANCE_ROOT_REUSE", str(case_id))
        require(observed_provenance.get("source_kind") == "ACTUAL_ENFORCEMENT_EXECUTION", "OBSERVATION_SOURCE_KIND", str(case_id))
        require(observed_provenance.get("producer_authority") == observation_authority.get("producer_authority"), "OBSERVATION_PRODUCER", str(case_id))
        require(observed_provenance.get("producer_capability") == observation_authority.get("producer_capability"), "OBSERVATION_PRODUCER_CAPABILITY", str(case_id))
        require(observed_provenance.get("expectation_dependency") == "NONE", "OBSERVATION_EXPECTATION_DEPENDENCY", str(case_id))
        require(observed_provenance.get("run_identity") == run_identity, "OBSERVATION_RUN_IDENTITY", str(case_id))
        require(observed_provenance.get("enforcing_code_identity") == enforcing_code_identity, "OBSERVATION_CODE_IDENTITY", str(case_id))
        operation_trace = {
            "case_id": case_id,
            "actual_status": observation.get("actual_status"),
            "observed_code": observation.get("observed_code"),
            "observed_enforcing_function": observation.get("observed_enforcing_function"),
            "observed_authority_source": observation.get("observed_authority_source"),
            "observed_evidence_result": observation.get("observed_evidence_result"),
            "authoritative_input_identity": observation.get("authoritative_input_identity"),
            "run_identity": run_identity,
            "enforcing_code_identity": enforcing_code_identity,
        }
        require(observed_provenance.get("operation_trace_identity") == semantic_identity(operation_trace), "OBSERVATION_EXECUTION_PROOF", str(case_id))
        require(semantic_identity(observed_provenance) != expectation_root, "PROVENANCE_ROOT_REUSE", str(case_id))
        require(not any(key.startswith("expected_") for key in observation), "EXPECTATION_COPIED_TO_OBSERVATION", str(case_id))
    for expected in expectations.get("cases", []):
        require(not any(key.startswith("actual_") or key.startswith("observed_") for key in expected), "OBSERVATION_COPIED_TO_EXPECTATION", str(expected.get("case_id")))


_PROTECTED = {
    "baseline_capture": ("baseline capture", "capture may begin", "capture can start"),
    "operational_capture_script": ("operational capture-script", "operational capture script"),
    "merge": ("merge",),
    "canonical_incorporation": ("canonical incorporation",),
    "production_implementation": ("production implementation",),
    "deployment": ("deployment", "deploy"),
    "service_restart": ("service restart", "restart services", "production restart"),
    "runtime_migration": ("runtime migration",),
    "nq_cutover": ("nq cutover",),
    "automated_paper_trading": ("automated paper trading", "paper trading"),
    "live_money_trading": ("live-money trading", "live money trading", "live trading"),
    "phase_3c2": ("phase 3c2",),
    "phase_3c1_r11_acceptance": ("phase 3c1-r11 acceptance",),
    "bucket_0_completion": ("bucket 0", "bucket 0 complete", "bucket 0 completion"),
    "bucket_1_work": ("bucket 1",),
}
_NEGATIVE = re.compile(r"\b(no|is not authorized|are not authorized|not authorized|does not authorize|do not authorize|not authorize|is not permitted|are not permitted|not permitted|does not perform|do not perform|does not begin|do not begin|does not complete|do not complete|may not|must not|cannot|remains? withheld|remains? pending independent review|remains? blocked|remains? incomplete|is incomplete|are incomplete)\b", re.I)
_CONDITIONAL = re.compile(r"\b(if|after|when|once|provided|subject to|unless)\b", re.I)
_DOUBLE_NEGATIVE = re.compile(r"\b(not\s+(?:unauthorized|prohibited|withheld|blocked)|never\s+not)\b", re.I)
_CONTRADICTION_CONNECTOR = re.compile(r"\b(but|however|yet|although|nevertheless)\b", re.I)


def _sentences(text: str) -> Iterable[str]:
    normalized = re.sub(r"[`*_>#|\[\]{}()]", " ", text)
    for sentence in re.split(r"[.!?;\n]+", normalized):
        compact = " ".join(sentence.split())
        if compact:
            yield compact


def authorization_statements(text: str) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for sentence in _sentences(text):
        lowered = sentence.casefold()
        for protected, phrases in _PROTECTED.items():
            if not any(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", lowered) for phrase in phrases):
                continue
            negative_match = _NEGATIVE.search(sentence)
            conditional = bool(_CONDITIONAL.search(sentence))
            double_negative = bool(_DOUBLE_NEGATIVE.search(sentence))
            contradiction = bool(_CONTRADICTION_CONNECTOR.search(sentence))
            if double_negative or conditional or contradiction or negative_match is None:
                decision_state = "REJECT"
            else:
                marker = negative_match.group(1).casefold()
                decision_state = "PENDING_INDEPENDENT_REVIEW" if "pending independent review" in marker else (
                    "WITHHELD" if "withheld" in marker or "blocked" in marker or "incomplete" in marker else "NOT_AUTHORIZED"
                )
            results.append(
                {
                    "protected_object": protected,
                    "statement": sentence,
                    "action": phrases[0],
                    "authority_phrase": negative_match.group(1) if negative_match else "UNKNOWN",
                    "polarity": "NEGATIVE" if negative_match else "UNKNOWN",
                    "modality": "CONDITIONAL" if conditional else "UNCONDITIONAL",
                    "condition": "PRESENT" if conditional else "ABSENT",
                    "actor": "UNSPECIFIED",
                    "decision_state": decision_state,
                    "contradiction": "YES" if contradiction or double_negative else "NO",
                }
            )
    return results


def validate_authorization_text(text: str, authorities: AuthorityRepository) -> None:
    policy = authorities.load("authorization_policy").value
    require(sorted(policy.get("protected_domains", [])) == sorted(_PROTECTED), "AUTHORIZATION_POLICY_DOMAIN_SET")
    statements = authorization_statements(text)
    allowed = set(policy.get("allowed_decision_states", []))
    require(allowed == {"WITHHELD", "NOT_AUTHORIZED", "PENDING_INDEPENDENT_REVIEW"}, "AUTHORIZATION_ALLOWED_STATE_SET")
    require(all(item["decision_state"] in allowed for item in statements), "AUTHORIZATION_TEXT_LEAKAGE")


def validate_authorization_package(authorities: AuthorityRepository) -> str:
    """Scan every policy-designated governance-text role from immutable Git bytes."""

    policy = authorities.load("authorization_policy").value
    roles = policy.get("scanned_text_roles")
    required = {"specification", "architecture_impact", "canonical_delta", "traceability_narrative", "package_index", "remediation_report"}
    require(isinstance(roles, list) and set(roles) == required, "AUTHORIZATION_SCAN_ROLE_SET")
    observations = []
    for role in sorted(roles):
        observed = authorities.observe_bytes(role)
        try:
            text = observed.data.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise R3AuthorityError("AUTHORIZATION_SCAN_ENCODING", role) from exc
        validate_authorization_text(text, authorities)
        observations.append({"role": role, "raw_sha256": observed.sha256, "git_blob": observed.git_blob})
    return semantic_identity(observations)


def validate_authorization_state(state: Mapping[str, Any], authorities: AuthorityRepository) -> None:
    policy = authorities.load("authorization_policy").value
    domains = state.get("domains")
    require(isinstance(domains, Mapping), "AUTHORIZATION_STATE_DOMAINS")
    require(set(domains) == set(policy.get("protected_domains", [])), "AUTHORIZATION_STATE_DOMAIN_SET")
    require(all(value == "WITHHELD" for value in domains.values()), "AUTHORIZATION_STATE_LEAKAGE")


def validate_architecture_documents(claim: Mapping[str, Any], authorities: AuthorityRepository) -> None:
    """Bind R4 impact/delta claims and reject demonstrated-control overstatement."""

    impact = authorities.observe_bytes("architecture_impact")
    delta = authorities.observe_bytes("canonical_delta")
    expected = {
        "architecture_impact_raw_sha256": impact.sha256,
        "architecture_impact_git_blob": impact.git_blob,
        "canonical_delta_raw_sha256": delta.sha256,
        "canonical_delta_git_blob": delta.git_blob,
    }
    for field, value in expected.items():
        require(claim.get(field) == value, "ARCHITECTURE_DOCUMENT_BINDING", field)

    combined = (impact.data + b"\n" + delta.data).decode("utf-8", "strict")
    required_targets = (
        "Architecture/README.md",
        "Architecture/06_Randle_AI_Modernization_Charter.md",
        "Architecture/07_Randle_AI_Modernization_Roadmap.md",
        "Architecture/10_Randle_AI_Architecture_Traceability_Specification.md",
        "Architecture/12_Randle_AI_Development_Process_Specification.md",
        "Architecture/14_Randle_AI_Runtime_Recovery_Verification_Specification_DRAFT.md",
        "eventual canonical successor",
        "CODEX_TASK_TEMPLATE.md",
        ".gitattributes",
    )
    required_boundaries = (
        "Proven and retained from R3",
        "Corrected and demonstrated by R4",
        "Controls still draft",
        "Future operational-package work remains withheld",
        "Future capture authorization remains withheld",
        "No canonical incorporation is claimed",
        "Deployment remains withheld",
    )
    for marker in (*required_targets, *required_boundaries):
        require(marker in combined, "ARCHITECTURE_DOCUMENT_CONTENT", marker)
    for prohibited in ("canonical incorporation complete", "operational authority granted", "capture is authorized"):
        require(prohibited not in combined.casefold(), "ARCHITECTURE_DOCUMENT_OVERSTATEMENT", prohibited)


def _extract_clauses(specification: bytes) -> dict[str, str]:
    text = specification.decode("utf-8", "strict")
    matches = list(_CLAUSE.finditer(text))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end():end].strip()
        require(match.group(1) not in result, "DUPLICATE_SPECIFICATION_CLAUSE", match.group(1))
        result[match.group(1)] = body
    return result


def _source_functions(data: bytes) -> set[str]:
    try:
        tree = ast.parse(data.decode("utf-8", "strict"))
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise R3AuthorityError("TRACE_SOURCE_PARSE", str(exc)) from exc
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def audit_authority_source(data: bytes, module_role: str) -> str:
    """Reject ordinary authority I/O outside the governed access boundary."""

    try:
        tree = ast.parse(data.decode("utf-8", "strict"))
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise R3AuthorityError("AUTHORITY_SOURCE_PARSE", f"{module_role}:{exc}") from exc
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    def enclosing_function(node: ast.AST) -> str:
        current = node
        while current in parents:
            current = parents[current]
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return current.name
        return "<module>"

    wrapper_allow = {
        "governed_file_access": {
            "named_streams",
            "stat_regular_file",
            "read_binary",
            "read_named_stream",
            "enumerate_directory",
            "enumerate_regular_files",
        },
        "fixture_runner_r4": {"_write", "_write_fixture", "_append_fixture_event"},
        "legacy_fixture_runner": {"write_fixture", "append_event", "op_ads", "op_stability"},
        "boundary_verifier": {"_filesystem_identity"},
    }
    allowed_functions = wrapper_allow.get(module_role, set())
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = enclosing_function(node)
        forbidden = False
        surface = ""
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            forbidden, surface = True, "open"
        elif isinstance(node.func, ast.Attribute):
            attribute = node.func.attr
            if attribute in {"glob", "rglob", "read_bytes", "read_text"}:
                forbidden, surface = True, f"Path.{attribute}"
            elif attribute in {"scandir", "listdir"} and isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                forbidden, surface = True, f"os.{attribute}"
            elif attribute == "stat":
                forbidden, surface = True, "ordinary.stat"
        if forbidden and function not in allowed_functions:
            violations.append(f"{module_role}:{function}:{surface}:{getattr(node, 'lineno', 0)}")
    require(not violations, "AUTHORITY_ACCESS_BYPASS", ",".join(violations))
    return semantic_identity({"module_role": module_role, "source_sha256": sha256_bytes(data), "violations": []})


def audit_authority_access_surfaces(authorities: AuthorityRepository) -> str:
    roles = (
        "governed_file_access",
        "fixture_runner_r4",
        "boundary_verifier",
        "inventory_generator",
        "selection_engine",
        "schema_validation",
        "historical_log_parser",
        "comparison_engine",
        "r4_authority_verifier",
        "legacy_fixture_runner",
    )
    observations = []
    for role in roles:
        observed = authorities.observe_bytes(role)
        observations.append({"role": role, "audit_identity": audit_authority_source(observed.data, role)})
    return semantic_identity(observations)


def validate_trace_matrix_authority(matrix: Mapping[str, Any], authorities: AuthorityRepository) -> BoundDocument:
    document = authorities.load("semantic_traceability")
    require(matrix == document.value, "TRACE_MATRIX_AUTHORITY_MISMATCH")
    return document


def validate_traceability(
    matrix: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    expectations: Mapping[str, Any],
    authorities: AuthorityRepository,
    *,
    current_run_identity: str,
) -> None:
    matrix_document = validate_trace_matrix_authority(matrix, authorities)
    spec_binding = authorities.binding("specification")
    specification = git_object_bytes(authorities.repository, authorities.authority_ref, str(spec_binding.get("path")))
    require(specification.sha256 == spec_binding.get("raw_sha256"), "SPECIFICATION_AUTHORITY_HASH")
    clauses = _extract_clauses(specification.data)
    require(matrix.get("authority_id") == "RANDLE-R4-SEMANTIC-TRACEABILITY-1", "TRACE_MATRIX_AUTHORITY_ID")
    require(matrix.get("accepted_specification_commit_binding") == "CURRENT_IMMUTABLE_AUTHORITY_REF", "TRACE_SPECIFICATION_COMMIT_BINDING")
    require(matrix.get("accepted_specification_blob") == spec_binding.get("git_blob"), "TRACE_SPECIFICATION_BLOB")
    require(matrix.get("clause_anchor_set") == sorted(clauses), "TRACE_CLAUSE_SET")
    require(matrix.get("expectation_identity") == semantic_identity(expectations), "TRACE_EXPECTATION_IDENTITY")
    require(matrix.get("fresh_observation_identity") == semantic_identity(list(observations)), "TRACE_FRESH_OBSERVATION_IDENTITY")
    require(matrix.get("case_set_identity") == semantic_identity(sorted(item.get("case_id") for item in expectations.get("cases", []))), "TRACE_CASE_SET_IDENTITY")
    observed = {item.get("case_id"): item for item in observations}
    expected = {item.get("case_id"): item for item in expectations.get("cases", [])}
    rows = matrix.get("rows")
    require(isinstance(rows, list) and rows, "TRACE_ROWS")
    require(matrix.get("rule_set_identity") == semantic_identity(sorted(item.get("rule_id") for item in authorities.load("selection_rule_registry").value.get("rules", []))), "TRACE_RULE_SET_IDENTITY")
    require(matrix.get("function_set_identity") == semantic_identity(sorted({str(row.get("enforcing_function")) for row in rows})), "TRACE_FUNCTION_SET_IDENTITY")
    require(matrix.get("issuing_authority") == "RANDLE-R4-TRACEABILITY-ISSUER-1", "TRACE_ISSUING_AUTHORITY")
    reverse: set[str] = set()
    schema_blobs: set[str] = set()
    for row in rows:
        clause_id = row.get("clause_id")
        require(clause_id in clauses, "TRACE_CLAUSE_MISSING", str(clause_id))
        require(semantic_identity(clauses[clause_id]) == row.get("clause_semantic_sha256"), "TRACE_CLAUSE_HASH", str(clause_id))
        schema_observed = git_object_bytes(authorities.repository, authorities.authority_ref, row.get("schema_path"))
        schema_blobs.add(str(schema_observed.git_blob))
        schema = strict_json_loads(schema_observed.data)
        _json_pointer(schema, row.get("schema_pointer"))
        rule_document = authorities.load("selection_rule_registry").value
        require(row.get("rule_id") in {item.get("rule_id") for item in rule_document.get("rules", [])}, "TRACE_RULE_MISSING")
        source = git_object_bytes(authorities.repository, authorities.authority_ref, row.get("source_path"))
        enforcing_function = str(row.get("enforcing_function"))
        require(enforcing_function.rsplit(".", 1)[-1] in _source_functions(source.data), "TRACE_FUNCTION_MISSING")
        for case_key in ("positive_case_id", "mutation_case_id"):
            case_id = row.get(case_key)
            require(case_id in expected, "TRACE_EXPECTATION_MISSING", str(case_id))
            require(case_id in observed, "TRACE_FRESH_OBSERVATION_MISSING", str(case_id))
            require(observed[case_id].get("run_identity") == current_run_identity, "TRACE_PRIOR_OBSERVATION", str(case_id))
            require(observed[case_id].get("observed_enforcing_function") == enforcing_function, "TRACE_ENFORCING_FUNCTION", str(case_id))
            require(observed[case_id].get("observed_code") == expected[case_id].get("expected_code"), "TRACE_OBSERVED_CODE", str(case_id))
        reverse.add(str(clause_id))
        require(row.get("future_obligation"), "TRACE_FUTURE_OBLIGATION", str(clause_id))
    require(reverse == set(matrix.get("reverse_clause_ids", [])), "TRACE_REVERSE_MAPPING")
    require(matrix.get("schema_set_identity") == semantic_identity(sorted(schema_blobs)), "TRACE_SCHEMA_SET_IDENTITY")
    require(set(matrix.get("future_obligation_set", [])) == {row.get("future_obligation") for row in rows}, "TRACE_FUTURE_OBLIGATION_SET")


def validate_future_package(
    package_repository: Path,
    package_ref: str,
    interface: Mapping[str, Any],
    authorities: AuthorityRepository,
) -> Mapping[str, Any]:
    policy = authorities.load("operational_package_interface").value
    manifest_path = interface.get("manifest_path")
    review_path = interface.get("review_receipt_path")
    compatibility_path = interface.get("compatibility_declaration_path")
    require(isinstance(manifest_path, str) and isinstance(review_path, str) and isinstance(compatibility_path, str), "FUTURE_AUTHORITY_BYTES_MISSING")
    try:
        manifest_observed = git_object_bytes(package_repository, package_ref, manifest_path)
        review_observed = git_object_bytes(package_repository, package_ref, review_path)
        compatibility_observed = git_object_bytes(package_repository, package_ref, compatibility_path)
    except GovernedAccessError as exc:
        raise R3AuthorityError("FUTURE_AUTHORITY_BYTES_MISSING", exc.detail) from exc
    require(manifest_observed.sha256 == interface.get("manifest_sha256"), "FUTURE_MANIFEST_HASH")
    require(review_observed.sha256 == interface.get("review_receipt_sha256"), "FUTURE_REVIEW_HASH")
    require(compatibility_observed.sha256 == interface.get("compatibility_declaration_sha256"), "FUTURE_COMPATIBILITY_HASH")
    manifest = strict_json_loads(manifest_observed.data)
    review = strict_json_loads(review_observed.data)
    compatibility = strict_json_loads(compatibility_observed.data)
    require(isinstance(manifest, Mapping) and isinstance(review, Mapping) and isinstance(compatibility, Mapping), "FUTURE_AUTHORITY_OBJECT")
    for schema_role, instance, label in (
        ("future_package_manifest_schema", manifest, "future_package_manifest"),
        ("future_review_receipt_schema", review, "future_review_receipt"),
        ("compatibility_declaration_schema", compatibility, "future_compatibility_declaration"),
    ):
        schema = strict_json_loads(authorities.observe_bytes(schema_role).data)
        require(isinstance(schema, Mapping), "FUTURE_SCHEMA_OBJECT", schema_role)
        AuthorityRepository._validate_schema(schema, instance, label)
    require(manifest.get("interface_version") == policy.get("interface_version"), "FUTURE_INTERFACE_VERSION")
    package_commit_claim = manifest.get("package_commit")
    require(isinstance(package_commit_claim, str), "FUTURE_PACKAGE_COMMIT")
    try:
        revision = git_revision_identity(package_repository, package_commit_claim)
    except GovernedAccessError as exc:
        raise R3AuthorityError("FUTURE_PACKAGE_IDENTITY", exc.detail) from exc
    require(revision["commit"] != authorities.authority_ref, "FUTURE_SELF_REFERENTIAL_IDENTITY")
    require(manifest.get("package_commit") == revision["commit"], "FUTURE_PACKAGE_COMMIT")
    require(manifest.get("package_tree") == revision["tree"], "FUTURE_PACKAGE_TREE")
    require(manifest.get("package_parent") == revision["parent"], "FUTURE_PACKAGE_PARENT")
    require(manifest.get("complete_path_set") == list(git_tree_entries(package_repository, revision["commit"])), "FUTURE_COMPLETE_PATH_SET")
    require(manifest.get("accepted_specification_identity") == authorities.binding("specification").get("raw_sha256"), "FUTURE_ACCEPTED_SPECIFICATION")
    require(manifest.get("compatibility_state") == "COMPATIBLE_WITH_ACCEPTED_SPECIFICATION", "FUTURE_COMPATIBILITY_STATE")
    require(manifest.get("compatibility_declaration_sha256") == compatibility_observed.sha256, "FUTURE_COMPATIBILITY_BINDING")
    require(compatibility.get("compatibility_state") == "COMPATIBLE_WITH_ACCEPTED_SPECIFICATION", "FUTURE_COMPATIBILITY_STATE")
    require(compatibility.get("accepted_specification_identity") == authorities.binding("specification").get("raw_sha256"), "FUTURE_COMPATIBILITY_SPECIFICATION")
    require(compatibility.get("interface_version") == policy.get("interface_version"), "FUTURE_COMPATIBILITY_INTERFACE")
    require(compatibility.get("required_schema_roles") == policy.get("required_schema_roles"), "FUTURE_COMPATIBILITY_SCHEMAS")
    require(compatibility.get("required_authority_roles") == policy.get("required_authority_roles"), "FUTURE_COMPATIBILITY_AUTHORITIES")
    require(compatibility.get("capture_package_obligations") == policy.get("capture_package_obligations"), "FUTURE_COMPATIBILITY_OBLIGATIONS")
    expected_compatibility_evidence = semantic_identity(
        {
            "accepted_specification_identity": compatibility.get("accepted_specification_identity"),
            "interface_version": compatibility.get("interface_version"),
            "required_schema_roles": compatibility.get("required_schema_roles"),
            "required_authority_roles": compatibility.get("required_authority_roles"),
            "capture_package_obligations": compatibility.get("capture_package_obligations"),
        }
    )
    require(compatibility.get("verifier_evidence_identity") == expected_compatibility_evidence, "FUTURE_COMPATIBILITY_EVIDENCE")
    require(review.get("decision") == "INDEPENDENTLY_ACCEPTED", "FUTURE_REVIEW_DECISION")
    require(review.get("reviewer_independent") is True, "FUTURE_REVIEW_INDEPENDENCE")
    require(review.get("reviewer_authority") != manifest.get("author_authority"), "FUTURE_SELF_REVIEW")
    require(review.get("reviewer_authority") in policy.get("trusted_reviewers", []), "FUTURE_REVIEWER")
    require(review.get("manifest_identity") == manifest_observed.sha256, "FUTURE_REVIEW_MANIFEST")
    require(review.get("accepted_specification_identity") == authorities.binding("specification").get("raw_sha256"), "FUTURE_ACCEPTED_SPECIFICATION")
    require(review.get("interface_version") == policy.get("interface_version"), "FUTURE_INTERFACE_VERSION")
    require(review.get("compatibility_result") == "COMPATIBLE_WITH_ACCEPTED_SPECIFICATION", "FUTURE_REVIEW_COMPATIBILITY")
    require(review.get("trusted_issuer") == policy.get("review_issuance_authority"), "FUTURE_REVIEW_ISSUER")
    require(review.get("authorization_boundaries") == policy.get("authorization_boundaries"), "FUTURE_REVIEW_AUTHORIZATION")
    review_without_identity = {key: value for key, value in review.items() if key != "review_object_identity"}
    require(review.get("review_object_identity") == semantic_identity(review_without_identity), "FUTURE_REVIEW_OBJECT_IDENTITY")
    parse_authority_timestamp(review.get("issued_timestamp"), "future-review-issued")
    script_path = manifest.get("operational_script_path")
    try:
        script = git_object_bytes(package_repository, revision["commit"], script_path)
    except GovernedAccessError as exc:
        raise R3AuthorityError("FUTURE_SCRIPT_BYTES", exc.detail) from exc
    require(script.git_blob == manifest.get("operational_script_blob"), "FUTURE_SCRIPT_BLOB")
    require(script.sha256 == manifest.get("operational_script_raw_sha256"), "FUTURE_SCRIPT_HASH")
    require(review.get("operational_script_identity") == script.sha256, "FUTURE_REVIEW_SCRIPT")
    supporting = manifest.get("support_modules")
    require(isinstance(supporting, list), "FUTURE_SUPPORT_MODULES")
    for item in supporting:
        try:
            observed = git_object_bytes(package_repository, revision["commit"], item.get("path"))
        except GovernedAccessError as exc:
            raise R3AuthorityError("FUTURE_SUPPORT_BYTES", exc.detail) from exc
        require(observed.git_blob == item.get("blob"), "FUTURE_SUPPORT_BLOB")
        require(observed.sha256 == item.get("raw_sha256"), "FUTURE_SUPPORT_HASH")
    derived_package_identity = semantic_identity(
        {
            "package_commit": revision["commit"],
            "package_tree": revision["tree"],
            "package_parent": revision["parent"],
            "operational_script_blob": script.git_blob,
            "operational_script_raw_sha256": script.sha256,
            "support_modules": supporting,
            "complete_path_set": manifest.get("complete_path_set"),
        }
    )
    require(manifest.get("package_identity") == derived_package_identity, "FUTURE_PACKAGE_IDENTITY")
    require(review.get("reviewed_package_identity") == derived_package_identity, "FUTURE_REVIEWED_PACKAGE")
    return {
        "manifest_sha256": manifest_observed.sha256,
        "review_receipt_sha256": review_observed.sha256,
        "package_identity": derived_package_identity,
        "compatibility_identity": compatibility_observed.sha256,
    }
