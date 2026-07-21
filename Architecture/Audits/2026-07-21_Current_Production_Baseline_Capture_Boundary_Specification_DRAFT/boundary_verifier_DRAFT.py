#!/usr/bin/env python3
"""Draft-only verifier for the production-baseline boundary specification.

This module validates synthetic fixtures and frozen metadata. It is deliberately
not a capture utility and refuses to read the production repository or runtime
roots on its own.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


CANONICAL_JSON_VERSION = "RANDLE-CAPTURE-CJSON-1"
QUESTIONED_TESTS = (
    "test_command_center_listener_watchdog.py",
    "test_offline_replay.py",
    "test_kpi_liquidity_atr_distance_report.py",
    "test_tick_receiver_pipeline.py",
    "test_tick_receiver_throughput.py",
)
LONG_PATH_ARTIFACTS = (
    "raw_files/Architecture/Impact_Assessments/Evidence/2026-07-16_TradingView_Liquidity_Ladder/"
    "Randle_AI_Level_Map_Helper_7-16_Erroneous_Categorical_Exclusion_0543DD45.pine",
    "raw_files/Architecture/Impact_Assessments/Evidence/2026-07-16_TradingView_Liquidity_Ladder/"
    "Randle_AI_Level_Map_Helper_7-16_Superseded_2A389A_Revision.pine",
)
PRODUCTION_SIGNALS = frozenset(
    {
        "imports_captured_runtime",
        "references_captured_path",
        "executes_captured_entrypoint",
        "governed_production_recovery",
        "startup_recovery",
        "listener_feed_health",
        "trade_manager",
        "data_pipeline",
        "deployment_startup",
        "fixture_of_selected_test",
        "architecture_required_evidence",
        "generated_authoritative",
        "static_runtime_dependency",
        "runtime_open_target",
        "route_registration",
        "subprocess_target",
        "plugin_target",
    }
)
ALLOWED_OUTCOMES = frozenset(
    {"PASSED", "FAILED", "SUBFAILED", "SKIPPED", "ERROR", "XFAIL", "XPASS"}
)
FORBIDDEN_REPOSITORY_PREFIXES = (
    "EntryAgent/",
    "Data/",
    "Rithmic/",
    "deployment/",
    "launchers/",
    "config/production/",
)
FORBIDDEN_REPOSITORY_BASENAMES = {
    "entry_agent.py",
    "rithmic_live_listener.py",
    "launch_all.ps1",
    "trade_manager.py",
}


class BoundaryError(ValueError):
    """A deterministic fail-closed verification error."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise BoundaryError(code, detail)


def _normalize_json(value: Any) -> Any:
    if isinstance(value, str):
        normalized = unicodedata.normalize("NFC", value)
        require(normalized == value, "NONCANONICAL_UNICODE", repr(value))
        require(not any(0xD800 <= ord(ch) <= 0xDFFF for ch in value), "SURROGATE", repr(value))
        return value
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        raise BoundaryError("FLOAT_FORBIDDEN", repr(value))
    if isinstance(value, list):
        return [_normalize_json(item) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            require(isinstance(key, str), "NONSTRING_KEY", repr(key))
            nkey = unicodedata.normalize("NFC", key)
            require(nkey == key, "NONCANONICAL_KEY", repr(key))
            require(nkey not in normalized, "DUPLICATE_KEY", nkey)
            normalized[nkey] = _normalize_json(item)
        return normalized
    raise BoundaryError("UNSUPPORTED_JSON_TYPE", type(value).__name__)


def canonical_json_bytes(value: Any) -> bytes:
    """Return RANDLE-CAPTURE-CJSON-1 semantic bytes (no trailing newline)."""

    normalized = _normalize_json(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def stored_json_bytes(value: Any) -> bytes:
    """Return canonical stored-file bytes: semantic bytes plus one LF."""

    return canonical_json_bytes(value) + b"\n"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def semantic_identity(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def canonical_repository_path(path: str) -> str:
    require(isinstance(path, str) and path != "", "INVALID_PATH", repr(path))
    require(path == unicodedata.normalize("NFC", path), "PATH_UNICODE", path)
    require("\\" not in path, "PATH_SEPARATOR", path)
    require("\x00" not in path, "PATH_NUL", repr(path))
    require(not path.startswith("/"), "ABSOLUTE_PATH", path)
    require(not re.match(r"^[A-Za-z]:", path), "DRIVE_PATH", path)
    parts = path.split("/")
    require(all(part not in {"", ".", ".."} for part in parts), "PATH_TRAVERSAL", path)
    require(all(":" not in part for part in parts), "ADS_PATH", path)
    require(all(not part.endswith((" ", ".")) for part in parts), "WIN32_ALIAS", path)
    canonical = PurePosixPath(*parts).as_posix()
    require(canonical == path, "NONCANONICAL_PATH", path)
    return canonical


def _collision_key(path: str) -> str:
    return unicodedata.normalize("NFC", canonical_repository_path(path)).casefold()


def validate_path_set(paths: Iterable[str]) -> list[str]:
    canonical = [canonical_repository_path(path) for path in paths]
    counts = Counter(canonical)
    duplicates = sorted(path for path, count in counts.items() if count != 1)
    require(not duplicates, "DUPLICATE_PATH", repr(duplicates))
    keys: dict[str, str] = {}
    for path in canonical:
        key = _collision_key(path)
        if key in keys and keys[key] != path:
            raise BoundaryError("PATH_COLLISION", f"{keys[key]} <> {path}")
        keys[key] = path
    return sorted(canonical, key=lambda item: item.encode("utf-8"))


def _require_fields(record: Mapping[str, Any], fields: Sequence[str], context: str) -> None:
    missing = [field for field in fields if field not in record]
    require(not missing, "MISSING_FIELD", f"{context}: {missing}")


def validate_rule_registry(registry: Mapping[str, Any]) -> set[str]:
    _require_fields(registry, ("schema_version", "rules"), "selection rules")
    rules = registry["rules"]
    require(isinstance(rules, list) and rules, "EMPTY_RULES", "selection rule registry")
    identifiers: set[str] = set()
    for rule in rules:
        _require_fields(
            rule,
            ("rule_id", "class", "disposition", "predicate", "evidence_required", "failure_behavior"),
            "selection rule",
        )
        rid = rule["rule_id"]
        require(re.fullmatch(r"[A-Z][A-Z0-9_-]{2,63}", rid or "") is not None, "INVALID_RULE_ID", repr(rid))
        require(rid not in identifiers, "DUPLICATE_RULE_ID", rid)
        require(rule["disposition"] in {"INCLUDE", "EXCLUDE", "SEPARATE", "DERIVE"}, "BAD_DISPOSITION", rid)
        require(len(rule["failure_behavior"]) >= 12, "WEAK_FAILURE_BEHAVIOR", rid)
        identifiers.add(rid)
    return identifiers


def _validate_evidence(evidence: Any, context: str) -> None:
    require(isinstance(evidence, list) and evidence, "MISSING_EVIDENCE", context)
    require(all(isinstance(item, str) and ":" in item for item in evidence), "INVALID_EVIDENCE", context)


def _exclusion_matches(path: str, entry: Mapping[str, Any]) -> bool:
    target = entry["path_or_pattern"]
    match_type = entry["match_type"]
    if match_type == "exact":
        return path == target
    if match_type == "prefix":
        prefix = target.rstrip("/") + "/"
        return path.startswith(prefix)
    if match_type == "suffix":
        return path.endswith(target)
    if match_type == "segment":
        return target in path.split("/")
    if match_type == "glob":
        return fnmatch.fnmatchcase(path, target)
    raise BoundaryError("INVALID_MATCH_TYPE", str(match_type))


def validate_registries(
    include_registry: Mapping[str, Any],
    exclusion_registry: Mapping[str, Any],
    rule_ids: set[str],
) -> tuple[dict[str, Mapping[str, Any]], list[Mapping[str, Any]]]:
    includes = include_registry.get("entries")
    exclusions = exclusion_registry.get("entries")
    require(isinstance(includes, list), "BAD_INCLUDE_REGISTRY", "entries")
    require(isinstance(exclusions, list), "BAD_EXCLUSION_REGISTRY", "entries")

    include_by_path: dict[str, Mapping[str, Any]] = {}
    include_keys: dict[str, str] = {}
    for entry in includes:
        _require_fields(
            entry,
            (
                "entry_id",
                "path",
                "path_kind",
                "class",
                "selection_rule_id",
                "evidence_references",
                "authority_status",
                "required_capture_form",
                "expected_existence_state",
                "rationale",
            ),
            "include entry",
        )
        require(entry["path_kind"] in {"repository-relative", "external-root-relative"}, "UNSUPPORTED_INCLUDE_KIND", entry["entry_id"])
        path = canonical_repository_path(entry["path"])
        registry_key = f"{entry.get('external_root_id', 'repository')}::{path}"
        if entry["path_kind"] == "external-root-relative":
            require(registry_key not in include_by_path, "DUPLICATE_INCLUDE", registry_key)
            require(bool(entry.get("external_root_id")), "MISSING_EXTERNAL_ROOT", entry["entry_id"])
            require(entry["required_capture_form"] == "EXTERNAL_RAW_BYTES", "BAD_EXTERNAL_CAPTURE_FORM", entry["entry_id"])
            require(entry["selection_rule_id"] in rule_ids, "INVALID_RULE_ID", entry["selection_rule_id"])
            _validate_evidence(entry["evidence_references"], entry["entry_id"])
            require(len(entry["rationale"].strip()) >= 20, "MISSING_RATIONALE", entry["entry_id"])
            include_by_path[registry_key] = entry
            continue
        require(path not in include_by_path, "DUPLICATE_INCLUDE", path)
        collision = _collision_key(path)
        if collision in include_keys and include_keys[collision] != path:
            raise BoundaryError("PATH_COLLISION", f"{include_keys[collision]} <> {path}")
        include_keys[collision] = path
        require(entry["selection_rule_id"] in rule_ids, "INVALID_RULE_ID", entry["selection_rule_id"])
        _validate_evidence(entry["evidence_references"], entry["entry_id"])
        require(len(entry["rationale"].strip()) >= 20, "MISSING_RATIONALE", entry["entry_id"])
        include_by_path[path] = entry

    validated_exclusions: list[Mapping[str, Any]] = []
    exclusion_keys: set[tuple[str, str]] = set()
    for entry in exclusions:
        _require_fields(
            entry,
            (
                "entry_id",
                "path_or_pattern",
                "match_type",
                "exclusion_rule_id",
                "class",
                "rationale",
                "evidence",
                "comparable_path_consistency_proof",
                "authority",
                "reviewer_status",
                "fail_closed_behavior",
            ),
            "exclusion entry",
        )
        match_type = entry["match_type"]
        require(match_type in {"exact", "prefix", "suffix", "segment", "glob"}, "INVALID_MATCH_TYPE", entry["entry_id"])
        target = entry["path_or_pattern"]
        if match_type in {"exact", "prefix"}:
            canonical_repository_path(target.rstrip("/"))
        elif match_type == "segment":
            require("/" not in target and target not in {"", ".", ".."}, "PATTERN_OVERREACH", target)
        elif match_type == "suffix":
            require(target.startswith(".") and "/" not in target, "PATTERN_OVERREACH", target)
        else:
            require(target not in {"*", "**", "**/*"}, "PATTERN_OVERREACH", target)
            require(not target.startswith("**/"), "PATTERN_OVERREACH", target)
        key = (match_type, target)
        require(key not in exclusion_keys, "DUPLICATE_EXCLUSION", repr(key))
        exclusion_keys.add(key)
        require(entry["exclusion_rule_id"] in rule_ids, "INVALID_RULE_ID", entry["exclusion_rule_id"])
        require(len(entry["rationale"].strip()) >= 20, "MISSING_RATIONALE", entry["entry_id"])
        _validate_evidence(entry["evidence"], entry["entry_id"])
        require(len(entry["comparable_path_consistency_proof"].strip()) >= 20, "MISSING_CONSISTENCY_PROOF", entry["entry_id"])
        require(entry["reviewer_status"] in {"PENDING_INDEPENDENT_REVIEW", "ACCEPTED"}, "BAD_REVIEW_STATUS", entry["entry_id"])
        require("STOP" in entry["fail_closed_behavior"].upper(), "WEAK_FAIL_CLOSED", entry["entry_id"])
        validated_exclusions.append(entry)

    conflicts = sorted(
        path
        for path, entry in include_by_path.items()
        if entry["path_kind"] == "repository-relative"
        and any(_exclusion_matches(path, exclusion) for exclusion in validated_exclusions)
    )
    require(not conflicts, "INCLUDE_EXCLUDE_CONFLICT", repr(conflicts))
    return include_by_path, validated_exclusions


def is_test_candidate(path: str) -> bool:
    name = path.rsplit("/", 1)[-1].casefold()
    return bool(
        re.fullmatch(r"test_.+\.py", name)
        or re.fullmatch(r".+_test\.py", name)
        or re.fullmatch(r".+_tests\.py", name)
        or "replay_test" in name
        or re.fullmatch(r"(?:run_|scenario_).+\.py", name)
    )


def derive_selection(
    files: Sequence[Mapping[str, Any]],
    include_registry: Mapping[str, Any],
    exclusion_registry: Mapping[str, Any],
    rule_registry: Mapping[str, Any],
) -> list[str]:
    rule_ids = validate_rule_registry(rule_registry)
    includes, exclusions = validate_registries(include_registry, exclusion_registry, rule_ids)
    paths = validate_path_set(record["path"] for record in files)
    by_path = {record["path"]: record for record in files}
    repository_includes = {
        path: entry for path, entry in includes.items() if entry["path_kind"] == "repository-relative"
    }
    missing = sorted(path for path in repository_includes if path not in by_path)
    require(not missing, "MISSING_REQUIRED_PATH", repr(missing))
    selected: set[str] = set()
    for path in paths:
        record = by_path[path]
        signals = set(record.get("signals", []))
        known_class = record.get("class")
        matching = [entry for entry in exclusions if _exclusion_matches(path, entry)]
        if path in repository_includes:
            require(not matching, "INCLUDE_EXCLUDE_CONFLICT", path)
            selected.add(path)
            continue
        if is_test_candidate(path):
            if signals & PRODUCTION_SIGNALS:
                require(not matching, "RELEVANT_TEST_EXCLUDED", path)
                selected.add(path)
            elif matching:
                continue
            else:
                raise BoundaryError("UNKNOWN_TEST_DISPOSITION", path)
            continue
        if signals & PRODUCTION_SIGNALS:
            require(not matching, "RELEVANT_PATH_EXCLUDED", path)
            selected.add(path)
        elif matching:
            continue
        else:
            require(known_class in {"governance-only", "external-dependency-placeholder"}, "UNKNOWN_FILE_CLASS", path)
    return sorted(selected, key=lambda item: item.encode("utf-8"))


def verify_inventory(expected: Sequence[Mapping[str, Any]], actual: Sequence[Mapping[str, Any]]) -> None:
    expected_paths = validate_path_set(record["path"] for record in expected)
    actual_paths = validate_path_set(record["path"] for record in actual)
    require(expected_paths == actual_paths, "INVENTORY_PATH_SET", f"expected={expected_paths}; actual={actual_paths}")
    expected_by_path = {record["path"]: record for record in expected}
    actual_by_path = {record["path"]: record for record in actual}
    for path in expected_paths:
        for field in ("size", "sha256"):
            require(expected_by_path[path].get(field) == actual_by_path[path].get(field), "INVENTORY_IDENTITY", f"{path}:{field}")


def validate_inventory_security(records: Sequence[Mapping[str, Any]]) -> None:
    for record in records:
        path = canonical_repository_path(record["path"])
        require(record.get("accessible", True) is True, "PERMISSION_DENIED", path)
        require(record.get("reparse_point", False) is False, "REPARSE_POINT_AMBIGUITY", path)
        require(not record.get("alternate_data_streams", []), "ALTERNATE_DATA_STREAM", path)
        require(record.get("stable_read", True) is True, "FILE_MUTATED_DURING_SCAN", path)


def verify_manifest(manifest: Mapping[str, Any]) -> None:
    _require_fields(manifest, ("artifacts", "total_artifact_count", "total_bytes"), "durable manifest")
    artifacts = manifest["artifacts"]
    paths = validate_path_set(item["canonical_path"] for item in artifacts)
    require(len(paths) == manifest["total_artifact_count"], "MANIFEST_COUNT", repr(manifest["total_artifact_count"]))
    require(sum(item["size"] for item in artifacts) == manifest["total_bytes"], "MANIFEST_BYTES", repr(manifest["total_bytes"]))
    for item in artifacts:
        require(re.fullmatch(r"[0-9A-F]{64}", item["sha256"] or "") is not None, "MANIFEST_HASH", item["canonical_path"])


def verify_long_path_artifacts(manifest: Mapping[str, Any]) -> None:
    present = {item["canonical_path"] for item in manifest["artifacts"]}
    missing = sorted(set(LONG_PATH_ARTIFACTS) - present)
    require(not missing, "LONG_PATH_OMISSION", repr(missing))


FREEZE_IDENTITY_FIELDS = (
    "specification_commit",
    "specification_tree",
    "specification_document_blob",
    "include_registry_blob",
    "exclusion_registry_blob",
    "selection_script_blob",
    "verification_script_blob",
    "canonical_configuration_blob",
    "inventory_sha256",
    "repository_status_sha256",
    "repository_head",
    "index_sha256",
)


def validate_freeze(
    receipt: Mapping[str, Any],
    current: Mapping[str, Any],
    used_attempt_ids: set[str] | None = None,
) -> None:
    _require_fields(receipt, ("attempt_id", "freeze_receipt_sha256", *FREEZE_IDENTITY_FIELDS), "freeze receipt")
    if used_attempt_ids is not None:
        require(receipt["attempt_id"] not in used_attempt_ids, "REUSED_ATTEMPT_ID", receipt["attempt_id"])
    for field in FREEZE_IDENTITY_FIELDS:
        require(receipt[field] == current.get(field), "FREEZE_MISMATCH", field)
    semantic = {key: value for key, value in receipt.items() if key != "freeze_receipt_sha256"}
    require(receipt["freeze_receipt_sha256"] == semantic_identity(semantic), "FREEZE_RECEIPT_HASH", "self identity")


def validate_test_classification(record: Mapping[str, Any], broad_log_bytes: bytes) -> None:
    _require_fields(
        record,
        ("parser_name", "parser_version", "normalization_rules", "broad_log_sha256", "outcomes", "totals"),
        "test classification",
    )
    require(record["broad_log_sha256"] == sha256_bytes(broad_log_bytes), "BROAD_LOG_HASH", "test log")
    outcomes = record["outcomes"]
    identities = [item["identity"] for item in outcomes]
    require(len(identities) == len(set(identities)), "DUPLICATE_OUTCOME", "test identity")
    for item in outcomes:
        require(item["outcome"] in ALLOWED_OUTCOMES, "UNSUPPORTED_OUTCOME", item["identity"])
        if item["outcome"] == "SUBFAILED":
            require(bool(item.get("parent_identity")), "SUBFAILED_PARENT", item["identity"])
        if item["outcome"] in {"FAILED", "SUBFAILED", "ERROR", "XPASS"}:
            _require_fields(item, ("classification_category", "classification_rationale", "source_reference"), item["identity"])
    if record["parser_name"] == "randle-pytest-outcome-parser":
        try:
            parsed = json.loads(broad_log_bytes.decode("utf-8"))
            source_outcomes = parsed["outcomes"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise BoundaryError("UNPARSABLE_BROAD_LOG", str(exc)) from exc
        source_tuples = sorted(
            (item["identity"], item.get("parent_identity"), item["outcome"])
            for item in source_outcomes
        )
        classified_tuples = sorted(
            (item["identity"], item.get("parent_identity"), item["outcome"])
            for item in outcomes
        )
        require(source_tuples == classified_tuples, "UNSUPPORTED_RECLASSIFICATION", "source outcomes differ")
    computed = Counter(item["outcome"] for item in outcomes)
    for outcome in ALLOWED_OUTCOMES:
        require(record["totals"].get(outcome, 0) == computed.get(outcome, 0), "TEST_TOTAL_MISMATCH", outcome)
    require(sum(record["totals"].values()) == len(outcomes), "TEST_ACCOUNTING_MISMATCH", "all outcomes")


def validate_attempt_ledger(records: Sequence[Mapping[str, Any]]) -> None:
    identifiers: set[str] = set()
    for record in records:
        _require_fields(
            record,
            (
                "attempt_id",
                "start_time",
                "end_time",
                "initiating_session",
                "repository_identity",
                "specification_identity",
                "script_identity",
                "inventory_identity",
                "worktree",
                "branch",
                "evidence_directory",
                "pass_a_status",
                "pass_b_status",
                "staging_state",
                "commits",
                "runtime_access",
                "production_modification",
                "stop_reason",
                "terminal_disposition",
                "manifest",
                "relationship_to_prior_attempts",
            ),
            "attempt record",
        )
        attempt_id = record["attempt_id"]
        require(attempt_id not in identifiers, "DUPLICATE_ATTEMPT_ID", attempt_id)
        identifiers.add(attempt_id)
        disposition = record["terminal_disposition"]
        require(disposition in {"NO_ARTIFACT", "PRE_PASS_A_STOP", "UNSTABLE", "ABORTED", "REJECTED", "SUCCESSFUL", "SUPERSEDED", "REVIEWED"}, "MISSING_TERMINAL_DISPOSITION", str(disposition))
        if disposition in {"NO_ARTIFACT", "PRE_PASS_A_STOP"}:
            require(record["worktree"] is None and record["branch"] is None, "CONFLICTING_ATTEMPT_CLAIM", attempt_id)
            require(record["evidence_directory"] is None and record["manifest"] is None, "CONFLICTING_ATTEMPT_CLAIM", attempt_id)
            require(record["pass_a_status"] == "NOT_STARTED" and record["pass_b_status"] == "NOT_STARTED", "CONFLICTING_ATTEMPT_CLAIM", attempt_id)
        if disposition in {"UNSTABLE", "REJECTED", "SUCCESSFUL", "SUPERSEDED", "REVIEWED"}:
            require(isinstance(record["manifest"], dict), "MISSING_MANIFEST_REFERENCE", attempt_id)
            _require_fields(record["manifest"], ("canonical_path", "size", "sha256"), attempt_id)
        require(record["runtime_access"] is False, "RUNTIME_ACCESS", attempt_id)
        require(record["production_modification"] is False, "PRODUCTION_MODIFICATION", attempt_id)


def validate_evidence_bindings(registry: Mapping[str, Any]) -> None:
    entries = registry.get("entries")
    require(isinstance(entries, list) and entries, "EMPTY_EVIDENCE_REGISTRY", "entries")
    paths: set[str] = set()
    for entry in entries:
        _require_fields(
            entry,
            ("canonical_path", "role", "byte_size", "sha256", "git_blob", "authority_status", "immutability_status", "required_for_recovery"),
            "evidence binding",
        )
        path = entry["canonical_path"]
        require(path not in paths, "DUPLICATE_EVIDENCE_BINDING", path)
        paths.add(path)
        require(isinstance(entry["byte_size"], int) and entry["byte_size"] >= 0, "EVIDENCE_SIZE", path)
        require(re.fullmatch(r"[0-9A-F]{64}", entry["sha256"] or "") is not None, "EVIDENCE_HASH", path)
        require(entry["immutability_status"] in {"GIT_IMMUTABLE", "CONTENT_ADDRESSED_EXTERNAL", "MUTABLE_SOURCE_SNAPSHOT"}, "EVIDENCE_IMMUTABILITY", path)


STABILITY_FIELDS = (
    "specification_identity",
    "script_identity",
    "inventory_identity",
    "raw_byte_identity",
    "git_cleaned_identity",
    "status_identity",
    "path_count",
    "external_evidence_identity",
    "head_identity",
    "index_identity",
)


def validate_multi_pass(pass_a: Mapping[str, Any], pass_b: Mapping[str, Any], final: Mapping[str, Any]) -> None:
    for field in STABILITY_FIELDS:
        require(pass_a.get(field) == pass_b.get(field) == final.get(field), "MULTIPASS_MISMATCH", field)
    for state in (pass_a, pass_b, final):
        require(state.get("writer_count") == 0, "ACTIVE_WRITER", "multi-pass")
        require(state.get("runtime_operations") == 0, "RUNTIME_OPERATION", "multi-pass")


def validate_governance_package(
    changed_paths: Sequence[str],
    events: Sequence[str],
    emitted_authorizations: Sequence[str],
) -> None:
    paths = validate_path_set(changed_paths)
    for path in paths:
        require(path.startswith("Architecture/"), "NON_GOVERNANCE_CHANGE", path)
        require(not path.startswith(FORBIDDEN_REPOSITORY_PREFIXES), "PRODUCTION_CHANGE", path)
        require(path.rsplit("/", 1)[-1] not in FORBIDDEN_REPOSITORY_BASENAMES, "PRODUCTION_CHANGE", path)
    forbidden_events = {"runtime_access", "deployment", "service_restart", "baseline_capture", "merge", "trading"}
    require(not (set(events) & forbidden_events), "FORBIDDEN_EVENT", repr(sorted(set(events) & forbidden_events)))
    require(not emitted_authorizations, "AUTHORIZATION_EMITTED", repr(emitted_authorizations))


def compare_declared_inventory(selected_paths: Sequence[str], declared_paths: Sequence[str]) -> None:
    selected = validate_path_set(selected_paths)
    declared = validate_path_set(declared_paths)
    require(selected == declared, "ALLOWLIST_DRIFT", f"selected={selected}; declared={declared}")


def ensure_all_questioned_tests(selected_paths: Sequence[str]) -> None:
    selected = set(selected_paths)
    missing = sorted(set(QUESTIONED_TESTS) - selected)
    require(not missing, "QUESTIONED_TEST_OMITTED", repr(missing))
