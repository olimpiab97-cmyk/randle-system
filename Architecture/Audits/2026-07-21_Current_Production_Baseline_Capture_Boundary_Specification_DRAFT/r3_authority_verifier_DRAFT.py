#!/usr/bin/env python3
"""Independent-byte authority enforcement for governed remediation R3.

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from governed_file_access_DRAFT import (
    ByteObservation,
    GovernedAccessError,
    canonical_absolute_path,
    git_object_bytes,
    git_revision_identity,
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
_CLAUSE = re.compile(r"^Clause ID:\s*(CPB-R3-[0-9]{2})\s*$", re.MULTILINE)


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
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=lambda value: (_ for _ in ()).throw(R3AuthorityError("JSON_NONFINITE", value)))
    except R3AuthorityError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise R3AuthorityError("INVALID_JSON", str(exc)) from exc


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
    """Loads authority bytes from an external Git ref and enforces role bindings."""

    def __init__(self, repository: Path, authority_ref: str, *, allow_staged: bool = False) -> None:
        if authority_ref == ":" and not allow_staged:
            raise R3AuthorityError("STAGED_AUTHORITY_FORBIDDEN")
        self.repository = repository
        self.authority_ref = authority_ref
        binding_path = f"{PACKAGE_RELATIVE}/r3_authority_bindings_DRAFT.json"
        observed = git_object_bytes(repository, authority_ref, binding_path)
        require(observed.data == canonical_json_bytes(strict_json_loads(observed.data)), "BINDING_NOT_CANONICAL")
        parsed = strict_json_loads(observed.data)
        require(isinstance(parsed, Mapping), "INVALID_BINDING_DOCUMENT")
        require(parsed.get("authority_id") == "RANDLE-R3-AUTHORITY-BINDINGS-1", "BINDING_AUTHORITY_ID")
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
        return semantic_identity(
            {
                "binding_blob": self.binding_observation.git_blob,
                "binding_raw_sha256": self.binding_observation.sha256,
                "roles": sorted(self._bindings),
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
    policy = authorities.load("separate_binding_policy").value
    role_map = authorities.load("authority_role_map").value
    include = terminal_record.get("terminal_disposition") == "INCLUDE"
    if include:
        require(not obligation, "INCLUDE_CONVERTED_TO_SEPARATE")
        return
    require(terminal_record.get("terminal_disposition") == "SEPARATE_AND_BIND", "INVALID_TERMINAL_DISPOSITION")
    artifact_class = terminal_record.get("artifact_class")
    rules = policy.get("artifact_classes", {})
    require(artifact_class in rules, "SEPARATE_CLASS_UNAUTHORIZED", str(artifact_class))
    rule = rules[artifact_class]
    require(obligation.get("authority_id") in rule.get("authorized_authority_ids", []), "SEPARATE_AUTHORITY_UNAUTHORIZED")
    require(obligation.get("authority_id") in role_map.get("authority_ids", []), "SEPARATE_AUTHORITY_ROLE_UNBOUND")
    for field in ("capture_form", "recovery_requirement", "semantic_purpose", "immutability_requirement"):
        require(obligation.get(field) == rule.get(field), f"SEPARATE_{field.upper()}")
    evidence = obligation.get("evidence")
    require(isinstance(evidence, list), "SEPARATE_EVIDENCE_INVALID")
    expected_roles = sorted(rule.get("required_evidence_roles", []))
    expected_classes = sorted(rule.get("required_evidence_classes", []))
    require(sorted(item.get("role") for item in evidence) == expected_roles, "SEPARATE_EVIDENCE_ROLES")
    require(sorted(item.get("class") for item in evidence) == expected_classes, "SEPARATE_EVIDENCE_CLASSES")
    require(len(evidence) == rule.get("cardinality"), "SEPARATE_EVIDENCE_CARDINALITY")
    allowed_roots = set(policy.get("allowed_external_roots", []))
    require(all(item.get("external_root_id") in allowed_roots for item in evidence), "SEPARATE_EXTERNAL_ROOT")


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
    require(claim == timestamp.get("freeze_issued_timestamp"), "TIMESTAMP_AUTHORITY_MISMATCH")
    parse_authority_timestamp(claim, "frozen-timestamp-claim")


def validate_attempt_prefix_authority(authorities: AuthorityRepository) -> BoundDocument:
    document = authorities.load("attempt_prefix_authority")
    value = document.value
    require(value.get("authority_id") == "RANDLE-R3-ATTEMPT-PREFIX-1", "PREFIX_AUTHORITY_ID")
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
    require(value.get("policy_id") == "RANDLE-R3-REQUIRED-EVIDENCE-1", "EVIDENCE_POLICY_ID")
    rules = value.get("rules")
    require(isinstance(rules, list) and rules, "EVIDENCE_POLICY_RULES")
    for rule in rules:
        for field in (
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
    attempt = authorities.load("attempt_authorization").value
    timestamp = authorities.load("timestamp_authority").value
    prefix = validate_attempt_prefix_authority(authorities).value
    evidence = validate_evidence_policy_authority(authorities).value
    require(receipt.get("attempt_id") == attempt.get("attempt_id"), "FREEZE_ATTEMPT_ID")
    require(receipt.get("attempt_sequence") == attempt.get("attempt_sequence"), "FREEZE_ATTEMPT_SEQUENCE")
    require(receipt.get("issued_timestamp") == timestamp.get("freeze_issued_timestamp"), "FREEZE_TIMESTAMP")
    require(receipt.get("issuance_authority") == attempt.get("issuance_authority"), "FREEZE_ISSUANCE_AUTHORITY")
    require(attempt.get("status") == "AUTHORIZED_FOR_SPECIFICATION_FIXTURE_ONLY", "FREEZE_ATTEMPT_NOT_AUTHORIZED")
    require(attempt.get("reused") is False, "FREEZE_ATTEMPT_REUSED")
    issuance = parse_authority_timestamp(attempt.get("issued_timestamp"), "attempt-issued")
    expiry = parse_authority_timestamp(attempt.get("expires_timestamp"), "attempt-expires")
    freeze = parse_authority_timestamp(timestamp.get("freeze_issued_timestamp"), "freeze-issued")
    cutoff = parse_authority_timestamp(timestamp.get("freeze_cutoff_timestamp"), "freeze-cutoff")
    prior = parse_authority_timestamp(timestamp.get("prior_ledger_timestamp"), "prior-ledger")
    require(prior <= issuance <= freeze <= expiry <= cutoff, "FREEZE_CHRONOLOGY")
    expected = {
        "attempt_prefix_authority_identity": semantic_identity(prefix),
        "evidence_policy_identity": semantic_identity(evidence),
        "observer_authority_identity": authorities.load("observer_source_authority").semantic_sha256,
        "specification_authority_identity": authorities.binding("specification").get("raw_sha256"),
    }
    for field, value in expected.items():
        require(receipt.get(field) == value, "FREEZE_EXTERNAL_AUTHORITY", field)
    semantic = {key: value for key, value in receipt.items() if key != "freeze_receipt_sha256"}
    require(receipt.get("freeze_receipt_sha256") == semantic_identity(semantic), "FREEZE_RECEIPT_HASH")


def verify_historical_classification(
    classification: Mapping[str, Any],
    authorities: AuthorityRepository,
    parser: Any,
) -> Mapping[str, Any]:
    authority = authorities.load("historical_evidence_authority").value
    physical = authority.get("authorized_physical_path")
    require(isinstance(physical, str), "HISTORICAL_AUTHORITY_PATH")
    require(classification.get("logical_evidence_id") == authority.get("logical_evidence_id"), "HISTORICAL_LOGICAL_ID")
    require(classification.get("full_log_path") == physical, "HISTORICAL_CLAIMED_PATH")
    observed = read_binary(physical)
    require(observed.byte_size == authority.get("byte_size"), "HISTORICAL_SIZE")
    require(observed.sha256 == authority.get("sha256"), "HISTORICAL_HASH")
    require(authority.get("source_external_root_id") == "RANDLE-RUNTIME-PROVENANCE", "HISTORICAL_EXTERNAL_ROOT")
    parsed = parser(observed.data)
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


def append_only_event_root(events: Sequence[Mapping[str, Any]], initial_root: str) -> str:
    root = initial_root
    for sequence, event in enumerate(events, 1):
        require(event.get("sequence") == sequence, "OBSERVER_EVENT_SEQUENCE")
        root = semantic_identity({"previous_root": root, "event": event})
    return root


def verify_observer_source(
    source_path: Path,
    issuance: Mapping[str, Any],
    authorities: AuthorityRepository,
) -> Mapping[str, Any]:
    policy = authorities.load("observer_source_authority").value
    require(issuance.get("source_id") == policy.get("source_id"), "OBSERVER_SOURCE_ID")
    require(issuance.get("attempt_id") == authorities.load("attempt_authorization").value.get("attempt_id"), "OBSERVER_ATTEMPT_ID")
    expected_path = authorities.repository.joinpath(*str(policy.get("authorized_package_path")).split("/"))
    require(canonical_absolute_path(source_path) == canonical_absolute_path(expected_path), "OBSERVER_PATH_SUBSTITUTION")
    require(canonical_absolute_path(str(issuance.get("authorized_physical_path"))) == canonical_absolute_path(expected_path), "OBSERVER_ISSUANCE_PATH")
    stat_regular_file(source_path)
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
    require(issuance.get("event_source_implementation_identity") == policy.get("event_source_implementation_identity"), "OBSERVER_IMPLEMENTATION")
    require(issuance.get("reader_implementation_identity") == policy.get("reader_implementation_identity"), "OBSERVER_READER_IMPLEMENTATION")
    return {"events": events, "append_only_root": root, "source_sha256": observed.sha256, "source_kind": observed.source_kind}


def validate_comparison_receipt(
    receipt: Mapping[str, Any] | None,
    authorities: AuthorityRepository,
    *,
    expectation_identity: str,
    observation_identity: str,
    enforcing_code_identity: str,
    schema_set_identity: str,
) -> None:
    require(isinstance(receipt, Mapping), "MISSING_COMPARISON_RECEIPT")
    authority = authorities.load("comparison_authority").value
    policy = authorities.load("comparison_policy").value
    comparator_binding = authorities.binding("comparison_engine")
    require(authority.get("comparator_raw_sha256") == comparator_binding.get("raw_sha256"), "COMPARATOR_CODE_HASH")
    require(authority.get("comparator_git_blob") == comparator_binding.get("git_blob"), "COMPARATOR_CODE_BLOB")
    require(receipt.get("comparator_identity") == authority.get("comparator_identity"), "COMPARATOR_IDENTITY")
    require(receipt.get("comparator_raw_sha256") == authority.get("comparator_raw_sha256"), "COMPARATOR_CODE_HASH")
    require(receipt.get("comparison_policy_identity") == semantic_identity(policy), "COMPARISON_POLICY_IDENTITY")
    require(receipt.get("expectation_identity") == expectation_identity, "COMPARISON_EXPECTATION_IDENTITY")
    require(receipt.get("observation_identity") == observation_identity, "COMPARISON_OBSERVATION_IDENTITY")
    require(receipt.get("enforcing_code_identity") == enforcing_code_identity, "COMPARISON_ENFORCING_CODE_IDENTITY")
    require(receipt.get("schema_set_identity") == schema_set_identity, "COMPARISON_SCHEMA_SET_IDENTITY")
    require(receipt.get("issuance_authority") == authority.get("issuance_authority"), "COMPARISON_ISSUANCE_AUTHORITY")
    require(receipt.get("status") in policy.get("terminal_statuses", []), "COMPARISON_STATUS")
    require(receipt.get("status") == "MATCHED", "COMPARISON_NOT_MATCHED")
    discrepancies = receipt.get("discrepancies")
    require(isinstance(discrepancies, list), "COMPARISON_DISCREPANCIES")
    require(receipt.get("discrepancy_count") == len(discrepancies) == 0, "COMPARISON_DISCREPANCY_COUNT")
    semantic = {key: value for key, value in receipt.items() if key != "comparison_receipt_sha256"}
    require(receipt.get("comparison_receipt_sha256") == semantic_identity(semantic), "COMPARISON_RECEIPT_HASH")


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
    "live_money_trading": ("live-money trading", "live money trading"),
    "phase_3c2": ("phase 3c2",),
    "phase_3c1_r11_acceptance": ("phase 3c1-r11 acceptance",),
    "bucket_0_completion": ("bucket 0 complete", "bucket 0 completion"),
    "bucket_1_work": ("bucket 1",),
}
_NEGATIVE = re.compile(r"\b(is not authorized|are not authorized|not authorized|does not authorize|not authorize|is not|are not|contains? no|performs? no|no\s+\w+|remains? withheld|not permitted|may not|must not|remains? pending|remains? blocked|incomplete)\b", re.I)
_POSITIVE = re.compile(r"\b(approved?|approval is granted|authorized|permitted|may proceed|may begin|may now|can start|cleared|okay to|ok to|proceed|complete)\b", re.I)
_CONDITIONAL = re.compile(r"\b(if|after|when|once|provided|subject to|unless)\b", re.I)
_DOUBLE_NEGATIVE = re.compile(r"\b(not\s+(?:unauthorized|prohibited|withheld|blocked)|never\s+not)\b", re.I)


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
            negative = bool(_NEGATIVE.search(sentence))
            positive = bool(_POSITIVE.search(_NEGATIVE.sub("", sentence)))
            conditional = bool(_CONDITIONAL.search(sentence))
            double_negative = bool(_DOUBLE_NEGATIVE.search(sentence))
            if double_negative or conditional or positive:
                polarity = "REJECT"
            elif negative:
                polarity = "WITHHELD"
            else:
                polarity = "NONAUTHORITY"
            results.append(
                {
                    "protected_object": protected,
                    "statement": sentence,
                    "polarity": polarity,
                    "modality": "CONDITIONAL" if conditional else "UNCONDITIONAL",
                    "contradiction": "YES" if positive and negative else "NO",
                }
            )
    return results


def validate_authorization_text(text: str, authorities: AuthorityRepository) -> None:
    policy = authorities.load("authorization_policy").value
    require(sorted(policy.get("protected_domains", [])) == sorted(_PROTECTED), "AUTHORIZATION_POLICY_DOMAIN_SET")
    statements = authorization_statements(text)
    require(all(item["polarity"] in {"WITHHELD", "NONAUTHORITY"} for item in statements), "AUTHORIZATION_TEXT_LEAKAGE")


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
    """Bind R3 impact/delta claims to their immutable Git-object document bytes."""

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
        "Demonstrated R3 enforcement",
        "Controls still draft",
        "Future operational-package work",
        "Future capture authorization",
        "Rejected R2 controls",
        "Continuing authorization boundaries",
        "no canonical incorporation",
    )
    for marker in (*required_targets, *required_boundaries):
        require(marker in combined, "ARCHITECTURE_DOCUMENT_CONTENT", marker)


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


def validate_traceability(
    matrix: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    expectations: Mapping[str, Any],
    authorities: AuthorityRepository,
    *,
    current_run_identity: str,
) -> None:
    spec_binding = authorities.binding("specification")
    specification = git_object_bytes(authorities.repository, authorities.authority_ref, str(spec_binding.get("path")))
    require(specification.sha256 == spec_binding.get("raw_sha256"), "SPECIFICATION_AUTHORITY_HASH")
    clauses = _extract_clauses(specification.data)
    observed = {item.get("case_id"): item for item in observations}
    expected = {item.get("case_id"): item for item in expectations.get("cases", [])}
    rows = matrix.get("rows")
    require(isinstance(rows, list) and rows, "TRACE_ROWS")
    reverse: set[str] = set()
    for row in rows:
        clause_id = row.get("clause_id")
        require(clause_id in clauses, "TRACE_CLAUSE_MISSING", str(clause_id))
        require(semantic_identity(clauses[clause_id]) == row.get("clause_semantic_sha256"), "TRACE_CLAUSE_HASH", str(clause_id))
        schema_observed = git_object_bytes(authorities.repository, authorities.authority_ref, row.get("schema_path"))
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


def validate_future_package(
    package_repository: Path,
    package_ref: str,
    interface: Mapping[str, Any],
    authorities: AuthorityRepository,
) -> Mapping[str, Any]:
    policy = authorities.load("operational_package_interface").value
    manifest_path = interface.get("manifest_path")
    review_path = interface.get("review_receipt_path")
    require(isinstance(manifest_path, str) and isinstance(review_path, str), "FUTURE_AUTHORITY_BYTES_MISSING")
    try:
        manifest_observed = git_object_bytes(package_repository, package_ref, manifest_path)
        review_observed = git_object_bytes(package_repository, package_ref, review_path)
    except GovernedAccessError as exc:
        raise R3AuthorityError("FUTURE_AUTHORITY_BYTES_MISSING", exc.detail) from exc
    require(manifest_observed.sha256 == interface.get("manifest_sha256"), "FUTURE_MANIFEST_HASH")
    require(review_observed.sha256 == interface.get("review_receipt_sha256"), "FUTURE_REVIEW_HASH")
    manifest = strict_json_loads(manifest_observed.data)
    review = strict_json_loads(review_observed.data)
    require(isinstance(manifest, Mapping) and isinstance(review, Mapping), "FUTURE_AUTHORITY_OBJECT")
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
    require(review.get("decision") == "APPROVED", "FUTURE_REVIEW_DECISION")
    require(review.get("reviewer_authority") != manifest.get("author_authority"), "FUTURE_SELF_REVIEW")
    require(review.get("reviewer_authority") in policy.get("trusted_reviewers", []), "FUTURE_REVIEWER")
    require(review.get("reviewed_package_identity") == semantic_identity(manifest), "FUTURE_REVIEWED_PACKAGE")
    require(review.get("accepted_specification_identity") == authorities.binding("specification").get("raw_sha256"), "FUTURE_ACCEPTED_SPECIFICATION")
    require(review.get("interface_version") == policy.get("interface_version"), "FUTURE_INTERFACE_VERSION")
    parse_authority_timestamp(review.get("issued_timestamp"), "future-review-issued")
    script_path = manifest.get("operational_script_path")
    try:
        script = git_object_bytes(package_repository, revision["commit"], script_path)
    except GovernedAccessError as exc:
        raise R3AuthorityError("FUTURE_SCRIPT_BYTES", exc.detail) from exc
    require(script.git_blob == manifest.get("operational_script_blob"), "FUTURE_SCRIPT_BLOB")
    supporting = manifest.get("support_modules")
    require(isinstance(supporting, list), "FUTURE_SUPPORT_MODULES")
    for item in supporting:
        try:
            observed = git_object_bytes(package_repository, revision["commit"], item.get("path"))
        except GovernedAccessError as exc:
            raise R3AuthorityError("FUTURE_SUPPORT_BYTES", exc.detail) from exc
        require(observed.git_blob == item.get("blob"), "FUTURE_SUPPORT_BLOB")
    return {
        "manifest_sha256": manifest_observed.sha256,
        "review_receipt_sha256": review_observed.sha256,
        "package_identity": semantic_identity(manifest),
    }
