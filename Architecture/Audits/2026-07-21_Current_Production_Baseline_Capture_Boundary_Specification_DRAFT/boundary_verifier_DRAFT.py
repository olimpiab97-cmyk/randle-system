#!/usr/bin/env python3
"""Draft-only semantic authority for the baseline-boundary specification.

This module validates synthetic specification fixtures.  It refuses to grant
capture, runtime, deployment, merge, or trading authority.  A separately
reviewed operational implementation is required before any production scan.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import platform
import re
import subprocess
import unicodedata
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


SERIALIZATION_ID = "RANDLE-CAPTURE-CJSON-1"
QUESTIONED_TESTS = (
    "test_command_center_listener_watchdog.py",
    "test_offline_replay.py",
    "test_kpi_liquidity_atr_distance_report.py",
    "test_tick_receiver_pipeline.py",
    "test_tick_receiver_throughput.py",
)
LONG_PATH_SENTINELS = (
    "raw_files/Architecture/Impact_Assessments/Evidence/2026-07-16_TradingView_Liquidity_Ladder/Randle_AI_Level_Map_Helper_7-16_Erroneous_Categorical_Exclusion_0543DD45.pine",
    "raw_files/Architecture/Impact_Assessments/Evidence/2026-07-16_TradingView_Liquidity_Ladder/Randle_AI_Level_Map_Helper_7-16_Superseded_2A389A_Revision.pine",
)
ALLOWED_OUTCOMES = {"PASSED", "FAILED", "SUBFAILED", "SKIPPED", "ERROR", "XFAIL", "XPASS"}
CLASSIFIED_OUTCOMES = {"FAILED", "SUBFAILED", "ERROR", "XPASS"}
TERMINAL_DISPOSITIONS = {"INCLUDE", "EXCLUDE", "SEPARATE_AND_BIND"}
PATH_KINDS = {"repository-relative", "external-root-relative"}
CAPTURE_FORMS = {
    "RAW_AND_GIT_OBJECT",
    "RAW_BYTES",
    "EXTERNAL_RAW_BYTES",
    "TOMBSTONE",
    "LINK_AND_TARGET",
    "SEPARATE_CONTENT_BINDING",
    "NO_CONTENT_EXCLUSION",
}
EXISTENCE_STATES = {
    "MUST_EXIST_AT_FREEZE",
    "MUST_EXIST_IF_SOURCE_EVIDENCE_ROOT_IS_SELECTED",
    "MAY_EXIST_CLASSIFIED",
    "MUST_BE_ABSENT",
    "TOMBSTONE",
}
PRODUCTION_SIGNALS = {
    "governed_production_recovery",
    "imports_captured_runtime",
    "references_captured_runtime",
    "executes_captured_entrypoint",
    "startup_recovery",
    "listener_feed_health",
    "trade_manager",
    "data_pipeline",
    "deployment_startup",
    "replay",
    "pipeline",
    "throughput",
    "kpi_report",
    "selected_dependency",
    "fixture_of_selected_test",
    "scenario_of_selected_test",
}
INCIDENT_FIELDS = (
    "runtime_access",
    "production_modification",
    "deployment_attempted",
    "service_restart_attempted",
)


class BoundaryError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise BoundaryError(code, detail)


def _require_fields(value: Mapping[str, Any], fields: Iterable[str], context: str) -> None:
    missing = sorted(field for field in fields if field not in value)
    require(not missing, "MISSING_FIELD", f"{context}: {missing}")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _validate_json_value(value: Any, context: str = "$") -> Any:
    if isinstance(value, float):
        raise BoundaryError("FLOAT_FORBIDDEN", context)
    if isinstance(value, str):
        require(unicodedata.normalize("NFC", value) == value, "NON_NFC_STRING", context)
        require(not any(0xD800 <= ord(ch) <= 0xDFFF for ch in value), "SURROGATE_FORBIDDEN", context)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{context}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            require(isinstance(key, str), "NON_STRING_KEY", context)
            _validate_json_value(key, f"{context}.<key>")
            _validate_json_value(item, f"{context}.{key}")
    elif value is not None and not isinstance(value, (bool, int)):
        raise BoundaryError("UNSUPPORTED_JSON_VALUE", f"{context}:{type(value).__name__}")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    _validate_json_value(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def stored_json_bytes(value: Any) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def semantic_identity(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _git(repo: Path, *args: str, text: bool = True) -> str | bytes:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", os.fspath(repo), *args],
        check=False,
        capture_output=True,
        text=text,
    )
    require(completed.returncode == 0, "GIT_COMMAND_FAILED", f"{' '.join(args)}: {completed.stderr!r}")
    return completed.stdout


def derive_committed_package_authority(
    repository: Path,
    commit: str,
    role_paths: Mapping[str, str],
) -> dict[str, Any]:
    """Derive package authority from Git objects and current raw bytes.

    This is the operational binding surface used by freeze verification.  Values
    supplied by a registry or receipt are never treated as their own evidence.
    """
    object_format = str(_git(repository, "rev-parse", "--show-object-format")).strip()
    resolved_commit = str(_git(repository, "rev-parse", f"{commit}^{{commit}}")).strip().lower()
    entries: list[dict[str, Any]] = []
    for role, raw_path in sorted(role_paths.items()):
        path = canonical_repository_path(raw_path)
        blob = str(_git(repository, "rev-parse", f"{resolved_commit}:{path}")).strip().lower()
        validate_git_object(blob, object_format, f"package role {role}")
        committed = _git(repository, "show", f"{resolved_commit}:{path}", text=False)
        disk_path = repository.joinpath(*PurePosixPath(path).parts)
        require(disk_path.is_file(), "PACKAGE_FILE_MISSING", path)
        disk = disk_path.read_bytes()
        require(disk == committed, "PACKAGE_WORKTREE_DIFFERS_FROM_COMMIT", path)
        entries.append(
            {
                "role": role,
                "canonical_path": path,
                "byte_size": len(committed),
                "raw_sha256": sha256_bytes(committed),
                "git_blob": blob,
            }
        )
    require(len(entries) == len(role_paths), "PACKAGE_ROLE_COLLISION", repr(role_paths))
    tree = str(_git(repository, "rev-parse", f"{resolved_commit}^{{tree}}")).strip().lower()
    parent = str(_git(repository, "rev-parse", f"{resolved_commit}^")).strip().lower()
    authority = {
        "object_format": object_format,
        "commit": resolved_commit,
        "parent": parent,
        "tree": tree,
        "entries": entries,
    }
    authority["authority_sha256"] = semantic_identity(authority)
    return authority


def verify_committed_package_authority(
    expected: Mapping[str, Any],
    repository: Path,
    role_paths: Mapping[str, str],
) -> None:
    derived = derive_committed_package_authority(repository, expected["commit"], role_paths)
    require(derived == expected, "PACKAGE_AUTHORITY_MISMATCH", "committed package or working bytes changed")


def derive_repository_freeze_state(
    repository: Path,
    specification_commit: str,
    role_paths: Mapping[str, str],
    generated_inventory: Sequence[Mapping[str, Any]],
    terminal_result: Mapping[str, Any],
    evidence_registry: Mapping[str, Any],
    attempt_ledger: Mapping[str, Any],
    *,
    timestamp_authority: str,
    authorization_identity: str,
) -> dict[str, Any]:
    """Independently derive all freeze fields available from immutable inputs.

    The caller supplies content structures, never precomputed receipt fields.
    Repository and package identities are read from Git and disk here.
    """
    required_roles = {
        "specification_document", "include_registry", "exclusion_registry", "selection_rule_registry",
        "boundary_configuration", "selection_engine", "inventory_generator", "boundary_verifier",
        "operational_capture_script", "freeze_receipt_schema",
    }
    require(set(role_paths) == required_roles, "FREEZE_PACKAGE_ROLE_SET", repr(sorted(set(role_paths) ^ required_roles)))
    package = derive_committed_package_authority(repository, specification_commit, role_paths)
    entries = {entry["role"]: entry for entry in package["entries"]}
    head = str(_git(repository, "rev-parse", "HEAD")).strip().lower()
    require(head == package["commit"], "FREEZE_HEAD_NOT_SPECIFICATION_COMMIT", head)
    branch_process = subprocess.run(
        ["git", "-c", f"safe.directory={repository.as_posix()}", "-C", os.fspath(repository), "symbolic-ref", "-q", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    branch = branch_process.stdout.strip() if branch_process.returncode == 0 else "DETACHED"
    index_path = Path(str(_git(repository, "rev-parse", "--git-path", "index")).strip())
    if not index_path.is_absolute():
        index_path = repository / index_path
    require(index_path.is_file(), "FREEZE_INDEX_MISSING", os.fspath(index_path))
    status = _git(repository, "status", "--porcelain=v2", "-z", "--branch", "--untracked-files=all", text=False)
    attributes_path = repository / ".gitattributes"
    attributes = attributes_path.read_bytes() if attributes_path.is_file() else b""
    validate_evidence_bindings(evidence_registry)
    validate_attempt_ledger(attempt_ledger, attempt_ledger["expected_attempt_ids"])
    dispositions = terminal_result["terminal_dispositions"]
    sets = validate_terminal_dispositions(terminal_result["enumeration_universe"], dispositions, terminal_result["binding_obligations"])
    total_bytes = sum(int(item["raw_byte_size"]) for item in generated_inventory)
    fs_stat = repository.stat()
    state = {
        "specification_commit": package["commit"],
        "specification_parent": package["parent"],
        "specification_tree": package["tree"],
        "specification_document_blob": entries["specification_document"]["git_blob"],
        "specification_document_sha256": entries["specification_document"]["raw_sha256"],
        "include_registry_blob": entries["include_registry"]["git_blob"],
        "include_registry_sha256": entries["include_registry"]["raw_sha256"],
        "exclusion_registry_blob": entries["exclusion_registry"]["git_blob"],
        "exclusion_registry_sha256": entries["exclusion_registry"]["raw_sha256"],
        "selection_rule_registry_blob": entries["selection_rule_registry"]["git_blob"],
        "selection_rule_registry_sha256": entries["selection_rule_registry"]["raw_sha256"],
        "boundary_configuration_blob": entries["boundary_configuration"]["git_blob"],
        "boundary_configuration_sha256": entries["boundary_configuration"]["raw_sha256"],
        "selection_engine_blob": entries["selection_engine"]["git_blob"],
        "selection_engine_sha256": entries["selection_engine"]["raw_sha256"],
        "inventory_generator_blob": entries["inventory_generator"]["git_blob"],
        "inventory_generator_sha256": entries["inventory_generator"]["raw_sha256"],
        "boundary_verifier_blob": entries["boundary_verifier"]["git_blob"],
        "boundary_verifier_sha256": entries["boundary_verifier"]["raw_sha256"],
        "operational_capture_script_blob": entries["operational_capture_script"]["git_blob"],
        "operational_capture_script_sha256": entries["operational_capture_script"]["raw_sha256"],
        "generated_inventory_sha256": semantic_identity(generated_inventory),
        "artifact_count": len(generated_inventory),
        "total_bytes": total_bytes,
        "included_set_sha256": semantic_identity(sets["INCLUDE"]),
        "excluded_set_sha256": semantic_identity(sets["EXCLUDE"]),
        "separately_bound_set_sha256": semantic_identity(sets["SEPARATE_AND_BIND"]),
        "repository_head": head,
        "repository_branch_or_detached": branch,
        "index_sha256": sha256_bytes(index_path.read_bytes()),
        "repository_status_sha256": sha256_bytes(status),
        "gitattributes_sha256": sha256_bytes(attributes),
        "git_version": str(_git(repository, "--version")).strip(),
        "python_version": platform.python_version(),
        "operating_system_identity": {"name": platform.system(), "version": platform.version(), "architecture": platform.machine()},
        "filesystem_identity": {"filesystem_type": "NTFS" if os.name == "nt" else platform.system(), "volume_serial": str(fs_stat.st_dev), "case_sensitive": os.name != "nt"},
        "repository_object_format": package["object_format"],
        "timestamp_authority": timestamp_authority,
        "authorization_identity": authorization_identity,
        "freeze_receipt_schema_sha256": entries["freeze_receipt_schema"]["raw_sha256"],
        "required_evidence_set_sha256": evidence_registry["registry_identity_sha256"],
        "attempt_ledger_root_sha256": attempt_ledger["current_ledger_root_sha256"],
    }
    _require_fields(state, FREEZE_IDENTITY_FIELDS, "derived repository freeze state")
    return state


def strict_json_loads(data: bytes) -> Any:
    require(not data.startswith(b"\xef\xbb\xbf"), "UTF8_BOM_FORBIDDEN", "JSON")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            require(key not in result, "DUPLICATE_JSON_KEY", key)
            result[key] = value
        return result

    try:
        text = data.decode("utf-8", errors="strict")
        value = json.loads(text, object_pairs_hook=pairs, parse_float=lambda raw: (_ for _ in ()).throw(BoundaryError("FLOAT_FORBIDDEN", raw)))
    except UnicodeDecodeError as exc:
        raise BoundaryError("INVALID_UTF8", str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise BoundaryError("INVALID_JSON", str(exc)) from exc
    return _validate_json_value(value)


def verify_stored_canonical_json(data: bytes) -> Any:
    require(data.endswith(b"\n") and not data.endswith(b"\n\n"), "TERMINAL_LF", "stored JSON")
    require(b"\r" not in data, "CR_FORBIDDEN", "stored JSON")
    value = strict_json_loads(data[:-1])
    require(stored_json_bytes(value) == data, "NONCANONICAL_JSON", "stored bytes")
    return value


def canonical_repository_path(path: str) -> str:
    require(isinstance(path, str) and path, "INVALID_PATH", repr(path))
    require(unicodedata.normalize("NFC", path) == path, "NON_NFC_PATH", path)
    require("\\" not in path and "\x00" not in path and ":" not in path, "INVALID_PATH", path)
    require(not path.startswith("/") and not re.match(r"^[A-Za-z]:", path), "ABSOLUTE_PATH", path)
    parts = PurePosixPath(path).parts
    require(bool(parts) and all(part not in {"", ".", ".."} for part in parts), "PATH_TRAVERSAL", path)
    require(all(not part.endswith((" ", ".")) for part in parts), "WIN32_ALIAS", path)
    canonical = "/".join(parts)
    require(canonical == path, "NONCANONICAL_PATH", path)
    return canonical


def artifact_key(path_kind: str, path: str, external_root_id: str | None = None) -> str:
    canonical = canonical_repository_path(path)
    require(path_kind in PATH_KINDS, "INVALID_PATH_KIND", path_kind)
    if path_kind == "external-root-relative":
        require(bool(external_root_id), "MISSING_EXTERNAL_ROOT", canonical)
        return f"{external_root_id}::{canonical}"
    require(external_root_id in {None, ""}, "UNEXPECTED_EXTERNAL_ROOT", canonical)
    return canonical


def _collision_key(path: str) -> str:
    return unicodedata.normalize("NFC", path).casefold()


def validate_path_set(paths: Iterable[str]) -> list[str]:
    canonical = [canonical_repository_path(path) for path in paths]
    duplicates = sorted(path for path, count in Counter(canonical).items() if count > 1)
    require(not duplicates, "DUPLICATE_PATH", repr(duplicates))
    collisions: dict[str, str] = {}
    for path in canonical:
        key = _collision_key(path)
        if key in collisions and collisions[key] != path:
            raise BoundaryError("PATH_COLLISION", f"{collisions[key]} <> {path}")
        collisions[key] = path
    return sorted(canonical, key=lambda item: item.encode("utf-8"))


def validate_git_object(value: str | None, object_format: str, context: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    length = {"sha1": 40, "sha256": 64}.get(object_format)
    require(length is not None, "UNSUPPORTED_GIT_OBJECT_FORMAT", object_format)
    require(isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None, "INVALID_GIT_OBJECT", context)


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


def validate_rule_registry(registry: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    _require_fields(registry, ("schema_version", "canonical_serialization", "rules"), "selection-rule registry")
    require(registry["canonical_serialization"] == SERIALIZATION_ID, "SERIALIZATION_ID", "selection rules")
    rules = registry["rules"]
    require(isinstance(rules, list) and rules, "EMPTY_RULE_REGISTRY", "rules")
    result: dict[str, Mapping[str, Any]] = {}
    for rule in rules:
        _require_fields(
            rule,
            (
                "rule_id",
                "class",
                "disposition",
                "predicate",
                "evidence_required",
                "failure_behavior",
                "authority_clause",
                "parser_ids",
            ),
            "selection rule",
        )
        rule_id = rule["rule_id"]
        require(re.fullmatch(r"[A-Z][A-Z0-9_-]+", rule_id or "") is not None, "INVALID_RULE_ID", str(rule_id))
        require(rule_id not in result, "DUPLICATE_RULE", rule_id)
        require(rule["disposition"] in {"DERIVE", *TERMINAL_DISPOSITIONS}, "INVALID_RULE_DISPOSITION", rule_id)
        require(isinstance(rule["evidence_required"], list) and rule["evidence_required"], "MISSING_EVIDENCE", rule_id)
        require(isinstance(rule["parser_ids"], list), "MISSING_PARSER_IDS", rule_id)
        require("STOP" in rule["failure_behavior"].upper(), "WEAK_FAIL_CLOSED", rule_id)
        result[rule_id] = rule
    return result


def _validate_evidence(evidence: Any, context: str) -> None:
    require(isinstance(evidence, list) and evidence, "MISSING_EVIDENCE", context)
    require(all(isinstance(item, str) and len(item.strip()) >= 3 for item in evidence), "MISSING_EVIDENCE", context)


def validate_registries(
    include_registry: Mapping[str, Any],
    exclusion_registry: Mapping[str, Any],
    rules: Mapping[str, Mapping[str, Any]],
    *,
    capture_mode: bool = False,
    accepted_review_binding: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Mapping[str, Any]], list[Mapping[str, Any]]]:
    _require_fields(include_registry, ("entries", "canonical_serialization"), "include registry")
    _require_fields(exclusion_registry, ("entries", "canonical_serialization"), "exclusion registry")
    require(include_registry["canonical_serialization"] == SERIALIZATION_ID, "SERIALIZATION_ID", "include registry")
    require(exclusion_registry["canonical_serialization"] == SERIALIZATION_ID, "SERIALIZATION_ID", "exclusion registry")
    include_by_key: dict[str, Mapping[str, Any]] = {}
    collision_keys: dict[str, str] = {}
    for entry in include_registry["entries"]:
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
        key = artifact_key(entry["path_kind"], entry["path"], entry.get("external_root_id"))
        require(key not in include_by_key, "DUPLICATE_INCLUDE", key)
        collision = _collision_key(key)
        require(collision not in collision_keys or collision_keys[collision] == key, "PATH_COLLISION", key)
        collision_keys[collision] = key
        require(entry["selection_rule_id"] in rules, "INVALID_RULE_ID", entry["selection_rule_id"])
        require(entry["required_capture_form"] in CAPTURE_FORMS, "INVALID_CAPTURE_FORM", entry["entry_id"])
        require(entry["expected_existence_state"] in EXISTENCE_STATES, "INVALID_EXISTENCE_STATE", entry["entry_id"])
        if entry["path_kind"] == "external-root-relative":
            require(entry["required_capture_form"] == "EXTERNAL_RAW_BYTES", "BAD_EXTERNAL_CAPTURE_FORM", entry["entry_id"])
        _validate_evidence(entry["evidence_references"], entry["entry_id"])
        require(len(entry["rationale"].strip()) >= 20, "MISSING_RATIONALE", entry["entry_id"])
        include_by_key[key] = entry

    validated_exclusions: list[Mapping[str, Any]] = []
    exclusion_keys: set[tuple[str, str]] = set()
    for entry in exclusion_registry["entries"]:
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
                "capture_mode_eligibility",
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
            require(target not in {"*", "**", "**/*"} and not target.startswith("**/"), "PATTERN_OVERREACH", target)
        key = (match_type, target)
        require(key not in exclusion_keys, "DUPLICATE_EXCLUSION", repr(key))
        exclusion_keys.add(key)
        require(entry["exclusion_rule_id"] in rules, "INVALID_RULE_ID", entry["exclusion_rule_id"])
        require(len(entry["rationale"].strip()) >= 20, "MISSING_RATIONALE", entry["entry_id"])
        _validate_evidence(entry["evidence"], entry["entry_id"])
        require(len(entry["comparable_path_consistency_proof"].strip()) >= 20, "MISSING_CONSISTENCY_PROOF", entry["entry_id"])
        require(entry["reviewer_status"] in {"PENDING_INDEPENDENT_REVIEW", "ACCEPTED"}, "BAD_REVIEW_STATUS", entry["entry_id"])
        require(entry["capture_mode_eligibility"] in {"REQUIRES_ACCEPTED_REVIEW_BINDING", "ELIGIBLE"}, "BAD_CAPTURE_ELIGIBILITY", entry["entry_id"])
        require("STOP" in entry["fail_closed_behavior"].upper(), "WEAK_FAIL_CLOSED", entry["entry_id"])
        if capture_mode:
            if entry["reviewer_status"] != "ACCEPTED" or entry["capture_mode_eligibility"] != "ELIGIBLE":
                require(
                    bool(accepted_review_binding)
                    and accepted_review_binding.get("specification_commit")
                    and accepted_review_binding.get("review_commit")
                    and accepted_review_binding.get("disposition") == "ACCEPT",
                    "PENDING_EXCLUSION_CAPTURE_MODE",
                    entry["entry_id"],
                )
        validated_exclusions.append(entry)

    repository_includes = {
        key: entry for key, entry in include_by_key.items() if entry["path_kind"] == "repository-relative"
    }
    conflicts = sorted(
        path for path in repository_includes if any(_exclusion_matches(path, exclusion) for exclusion in validated_exclusions)
    )
    require(not conflicts, "INCLUDE_EXCLUDE_CONFLICT", repr(conflicts))
    validate_questioned_test_authority(repository_includes, validated_exclusions)
    return include_by_key, validated_exclusions


def validate_questioned_test_authority(
    repository_includes: Mapping[str, Mapping[str, Any]],
    exclusions: Sequence[Mapping[str, Any]],
) -> None:
    for path in QUESTIONED_TESTS:
        entry = repository_includes.get(path)
        require(entry is not None, "QUESTIONED_TEST_REGISTRY_OMITTED", path)
        require(entry["selection_rule_id"] == "PRODUCTION_TEST_CLOSURE", "QUESTIONED_TEST_RULE", path)
        require(entry["required_capture_form"] == "RAW_AND_GIT_OBJECT", "QUESTIONED_TEST_CAPTURE_FORM", path)
        require(entry["expected_existence_state"] == "MUST_EXIST_AT_FREEZE", "QUESTIONED_TEST_EXISTENCE", path)
        require(not any(_exclusion_matches(path, exclusion) for exclusion in exclusions), "QUESTIONED_TEST_EXCLUSION", path)


def is_test_candidate(path: str, source_text: str | None = None) -> bool:
    name = path.rsplit("/", 1)[-1].casefold()
    named = bool(
        re.fullmatch(r"test_.+\.py", name)
        or re.fullmatch(r".+_test\.py", name)
        or re.fullmatch(r".+_tests\.py", name)
        or "replay_test" in name
        or re.fullmatch(r"(?:run_|scenario_).+\.py", name)
    )
    if named or source_text is None:
        return named
    content_markers = (
        "import pytest",
        "from pytest",
        "import unittest",
        "unittest.TestCase",
        "@pytest.fixture",
        "@pytest.mark.",
        "@pytest.mark.parametrize",
        "register_scenario(",
    )
    return any(marker in source_text for marker in content_markers)


def validate_terminal_dispositions(
    universe_keys: Sequence[str],
    dispositions: Sequence[Mapping[str, Any]],
    binding_obligations: Sequence[Mapping[str, Any]],
) -> dict[str, list[str]]:
    expected = sorted(universe_keys, key=lambda item: item.encode("utf-8"))
    require(len(expected) == len(set(expected)), "DUPLICATE_UNIVERSE_ARTIFACT", repr(expected))
    required_fields = (
        "artifact_key",
        "canonical_path",
        "path_kind",
        "artifact_class",
        "terminal_disposition",
        "governing_rule",
        "authority",
        "rationale",
        "evidence",
        "capture_form",
        "existence_state",
        "external_root_id",
        "binding_obligation_ids",
        "exclusion_review_identity",
        "separate_evidence_registry_identity",
    )
    by_key: dict[str, Mapping[str, Any]] = {}
    sets = {name: [] for name in TERMINAL_DISPOSITIONS}
    for record in dispositions:
        _require_fields(record, required_fields, "terminal disposition")
        key = artifact_key(record["path_kind"], record["canonical_path"], record.get("external_root_id"))
        require(record["artifact_key"] == key, "DISPOSITION_KEY_MISMATCH", key)
        require(key not in by_key, "MULTIPLE_TERMINAL_DISPOSITIONS", key)
        disposition = record["terminal_disposition"]
        require(disposition in TERMINAL_DISPOSITIONS, "INVALID_TERMINAL_DISPOSITION", key)
        require(record["capture_form"] in CAPTURE_FORMS, "INVALID_CAPTURE_FORM", key)
        require(record["existence_state"] in EXISTENCE_STATES, "INVALID_EXISTENCE_STATE", key)
        _validate_evidence(record["evidence"], key)
        require(len(record["rationale"].strip()) >= 20, "MISSING_RATIONALE", key)
        if disposition == "SEPARATE_AND_BIND":
            require(bool(record["binding_obligation_ids"]), "MISSING_SEPARATE_BINDING", key)
            require(bool(record["separate_evidence_registry_identity"]), "MISSING_SEPARATE_REGISTRY", key)
        elif disposition == "EXCLUDE":
            require(bool(record["exclusion_review_identity"]), "MISSING_EXCLUSION_REVIEW", key)
            require(not record["binding_obligation_ids"], "EXCLUDED_HAS_BINDING", key)
        else:
            require(record["exclusion_review_identity"] is None, "INCLUDED_HAS_EXCLUSION", key)
        by_key[key] = record
        sets[disposition].append(key)
    actual = sorted(by_key, key=lambda item: item.encode("utf-8"))
    require(actual == expected, "DISPOSITION_UNIVERSE_MISMATCH", f"expected={expected}; actual={actual}")
    obligation_by_id: dict[str, Mapping[str, Any]] = {}
    for obligation in binding_obligations:
        _require_fields(
            obligation,
            ("obligation_id", "artifact_key", "canonical_path", "role", "authority", "required_fields", "evidence"),
            "binding obligation",
        )
        oid = obligation["obligation_id"]
        require(oid not in obligation_by_id, "DUPLICATE_BINDING_OBLIGATION", oid)
        require(obligation["artifact_key"] in sets["SEPARATE_AND_BIND"], "ORPHAN_BINDING_OBLIGATION", oid)
        require(set(obligation["required_fields"]) >= {"canonical_path", "role", "byte_size", "sha256", "authority_status", "immutability_status", "required_for_recovery"}, "INCOMPLETE_BINDING_OBLIGATION", oid)
        _validate_evidence(obligation["evidence"], oid)
        obligation_by_id[oid] = obligation
    referenced = {
        oid
        for key in sets["SEPARATE_AND_BIND"]
        for oid in by_key[key]["binding_obligation_ids"]
    }
    require(referenced == set(obligation_by_id), "BINDING_OBLIGATION_SET_MISMATCH", repr(sorted(referenced ^ set(obligation_by_id))))
    for values in sets.values():
        values.sort(key=lambda item: item.encode("utf-8"))
    union = set().union(*(set(values) for values in sets.values()))
    require(len(union) == sum(len(values) for values in sets.values()) == len(expected), "DISPOSITION_SET_OVERLAP", "sets")
    return sets


FULL_INVENTORY_IDENTITY_FIELDS = (
    "canonical_path",
    "path_sha256",
    "raw_byte_size",
    "raw_sha256",
    "pre_read_identity",
    "post_read_identity",
    "file_mode",
    "filesystem_attributes",
    "git_status",
    "parent_git_blob",
    "index_git_blob",
    "working_tree_git_cleaned_sha256",
    "working_tree_git_cleaned_size",
    "computed_git_blob",
    "repository_object_format",
    "line_ending_profile",
    "encoding_profile",
    "gitattributes_sha256",
    "git_attribute_results",
    "symlink",
    "reparse_point",
    "external_root_id",
)


def verify_inventory(expected: Sequence[Mapping[str, Any]], actual: Sequence[Mapping[str, Any]]) -> None:
    expected_paths = validate_path_set(record["canonical_path"] for record in expected)
    actual_paths = validate_path_set(record["canonical_path"] for record in actual)
    require(expected_paths == actual_paths, "INVENTORY_PATH_SET", f"expected={expected_paths}; actual={actual_paths}")
    expected_by = {record["canonical_path"]: record for record in expected}
    actual_by = {record["canonical_path"]: record for record in actual}
    for path in expected_paths:
        _require_fields(expected_by[path], FULL_INVENTORY_IDENTITY_FIELDS, path)
        _require_fields(actual_by[path], FULL_INVENTORY_IDENTITY_FIELDS, path)
        for field in FULL_INVENTORY_IDENTITY_FIELDS:
            require(expected_by[path][field] == actual_by[path][field], "INVENTORY_IDENTITY", f"{path}:{field}")


def validate_inventory_security(records: Sequence[Mapping[str, Any]]) -> None:
    for record in records:
        path = canonical_repository_path(record["canonical_path"])
        require(record.get("accessible", True) is True, "PERMISSION_DENIED", path)
        require(record.get("reparse_point", False) is False, "REPARSE_POINT_AMBIGUITY", path)
        require(not record.get("alternate_data_streams", []), "ALTERNATE_DATA_STREAM", path)
        require(record.get("stable_read", True) is True, "FILE_MUTATED_DURING_SCAN", path)


def verify_long_path_sentinels(selected_root_id: str, records: Sequence[Mapping[str, Any]]) -> None:
    require(bool(selected_root_id), "LONG_PATH_ROOT_IDENTITY", "selected evidence root")
    present = {record["canonical_path"] for record in records}
    missing = sorted(set(LONG_PATH_SENTINELS) - present)
    require(not missing, "LONG_PATH_SENTINEL_MISSING", repr(missing))


def verify_manifest(manifest: Mapping[str, Any]) -> None:
    _require_fields(
        manifest,
        (
            "artifacts",
            "total_artifact_count",
            "total_bytes",
            "artifact_path_set_sha256",
            "artifact_set_semantic_sha256",
            "manifest_semantic_sha256",
        ),
        "durable manifest",
    )
    artifacts = manifest["artifacts"]
    paths = validate_path_set(item["canonical_path"] for item in artifacts)
    require(len(paths) == manifest["total_artifact_count"], "MANIFEST_COUNT", repr(manifest["total_artifact_count"]))
    require(sum(item["raw_byte_size"] for item in artifacts) == manifest["total_bytes"], "MANIFEST_BYTES", repr(manifest["total_bytes"]))
    require(manifest["artifact_path_set_sha256"] == semantic_identity(paths), "MANIFEST_PATH_SET", "path set")
    require(manifest["artifact_set_semantic_sha256"] == semantic_identity(artifacts), "MANIFEST_ARTIFACT_ROOT", "artifact set")
    semantic = {key: value for key, value in manifest.items() if key != "manifest_semantic_sha256"}
    require(manifest["manifest_semantic_sha256"] == semantic_identity(semantic), "MANIFEST_SEMANTIC_ROOT", "manifest")
    for item in artifacts:
        _require_fields(item, FULL_INVENTORY_IDENTITY_FIELDS, item.get("canonical_path", "artifact"))
        require(re.fullmatch(r"[0-9A-F]{64}", item["raw_sha256"] or "") is not None, "MANIFEST_HASH", item["canonical_path"])
        validate_git_object(item["computed_git_blob"], item["repository_object_format"], item["canonical_path"], nullable=True)


FREEZE_IDENTITY_FIELDS = (
    "specification_commit",
    "specification_parent",
    "specification_tree",
    "specification_document_blob",
    "specification_document_sha256",
    "include_registry_blob",
    "include_registry_sha256",
    "exclusion_registry_blob",
    "exclusion_registry_sha256",
    "selection_rule_registry_blob",
    "selection_rule_registry_sha256",
    "boundary_configuration_blob",
    "boundary_configuration_sha256",
    "selection_engine_blob",
    "selection_engine_sha256",
    "inventory_generator_blob",
    "inventory_generator_sha256",
    "boundary_verifier_blob",
    "boundary_verifier_sha256",
    "operational_capture_script_blob",
    "operational_capture_script_sha256",
    "generated_inventory_sha256",
    "artifact_count",
    "total_bytes",
    "included_set_sha256",
    "excluded_set_sha256",
    "separately_bound_set_sha256",
    "repository_head",
    "repository_branch_or_detached",
    "index_sha256",
    "repository_status_sha256",
    "gitattributes_sha256",
    "git_version",
    "python_version",
    "operating_system_identity",
    "filesystem_identity",
    "repository_object_format",
    "timestamp_authority",
    "authorization_identity",
    "freeze_receipt_schema_sha256",
    "required_evidence_set_sha256",
    "attempt_ledger_root_sha256",
)


def build_freeze_receipt(attempt_id: str, timestamp: str, current: Mapping[str, Any]) -> dict[str, Any]:
    _require_fields(current, FREEZE_IDENTITY_FIELDS, "derived freeze state")
    receipt = {
        "schema_version": "2.0.0-DRAFT",
        "canonical_serialization": SERIALIZATION_ID,
        "attempt_id": attempt_id,
        "timestamp": timestamp,
        **{field: current[field] for field in FREEZE_IDENTITY_FIELDS},
    }
    receipt["freeze_receipt_sha256"] = semantic_identity(receipt)
    return receipt


def validate_freeze(
    receipt: Mapping[str, Any] | None,
    independently_derived_current: Mapping[str, Any],
    used_attempt_ids: set[str] | None = None,
) -> None:
    require(isinstance(receipt, Mapping), "MISSING_FREEZE_RECEIPT", "receipt")
    _require_fields(receipt, ("attempt_id", "timestamp", "freeze_receipt_sha256", *FREEZE_IDENTITY_FIELDS), "freeze receipt")
    if used_attempt_ids is not None:
        require(receipt["attempt_id"] not in used_attempt_ids, "REUSED_ATTEMPT_ID", receipt["attempt_id"])
    _require_fields(independently_derived_current, FREEZE_IDENTITY_FIELDS, "independently derived freeze state")
    for field in FREEZE_IDENTITY_FIELDS:
        require(receipt[field] == independently_derived_current[field], "FREEZE_MISMATCH", field)
    semantic = {key: value for key, value in receipt.items() if key != "freeze_receipt_sha256"}
    require(receipt["freeze_receipt_sha256"] == semantic_identity(semantic), "FREEZE_RECEIPT_HASH", "self identity")


def validate_test_classification(record: Mapping[str, Any], broad_log_bytes: bytes) -> None:
    _require_fields(
        record,
        (
            "full_log_path",
            "full_log_size",
            "full_log_sha256",
            "parser_name",
            "parser_version",
            "normalization_rules",
            "classification_rules",
            "outcomes",
            "outcome_identity_set_sha256",
            "outcome_count_by_status",
            "classification_count_by_category",
            "source_total",
            "accounted_total",
        ),
        "test classification",
    )
    require(isinstance(record["full_log_path"], str) and record["full_log_path"], "BROAD_LOG_PATH", "classification")
    require(record["full_log_size"] == len(broad_log_bytes), "BROAD_LOG_SIZE", "classification")
    require(record["full_log_sha256"] == sha256_bytes(broad_log_bytes), "BROAD_LOG_HASH", "test log")
    require(bool(record["parser_name"]) and bool(record["parser_version"]), "PARSER_IDENTITY", "classification")
    require(isinstance(record["normalization_rules"], list) and record["normalization_rules"], "NORMALIZATION_RULES", "classification")
    require(isinstance(record["classification_rules"], list) and record["classification_rules"], "CLASSIFICATION_RULES", "classification")
    outcomes = record["outcomes"]
    identities = [item["identity"] for item in outcomes]
    require(len(identities) == len(set(identities)), "DUPLICATE_OUTCOME", "test identity")
    for item in outcomes:
        _require_fields(
            item,
            (
                "identity",
                "parent_identity",
                "outcome",
                "source_log_location",
                "classification_category",
                "classification_rationale",
                "source_reference",
                "parser_name",
                "parser_version",
                "normalization_rule",
                "classification_rule",
            ),
            "outcome",
        )
        require(item["outcome"] in ALLOWED_OUTCOMES, "UNSUPPORTED_OUTCOME", item["identity"])
        require(bool(item["source_log_location"]), "MISSING_OUTCOME_SOURCE_LOCATION", item["identity"])
        if item["outcome"] == "SUBFAILED":
            require(bool(item["parent_identity"]), "SUBFAILED_PARENT", item["identity"])
        if item["outcome"] in CLASSIFIED_OUTCOMES:
            for field in ("classification_category", "classification_rationale", "source_reference", "parser_name", "parser_version", "normalization_rule", "classification_rule"):
                require(isinstance(item[field], str) and bool(item[field].strip()), "EMPTY_FAILURE_CLASSIFICATION", f"{item['identity']}:{field}")
        else:
            require(all(item[field] is None for field in ("classification_category", "classification_rationale", "source_reference", "parser_name", "parser_version", "normalization_rule", "classification_rule")), "NONFAILURE_CLASSIFICATION", item["identity"])
    if record["parser_name"] == "randle-pytest-outcome-parser":
        try:
            parsed = strict_json_loads(broad_log_bytes)
            source_outcomes = parsed["outcomes"]
        except (BoundaryError, KeyError, TypeError) as exc:
            raise BoundaryError("UNPARSABLE_BROAD_LOG", str(exc)) from exc
        source_tuples = sorted((item["identity"], item.get("parent_identity"), item["outcome"]) for item in source_outcomes)
        classified_tuples = sorted((item["identity"], item.get("parent_identity"), item["outcome"]) for item in outcomes)
        require(source_tuples == classified_tuples, "UNSUPPORTED_RECLASSIFICATION", "source outcomes differ")
    computed = Counter(item["outcome"] for item in outcomes)
    for outcome in ALLOWED_OUTCOMES:
        require(record["outcome_count_by_status"].get(outcome) == computed.get(outcome, 0), "TEST_TOTAL_MISMATCH", outcome)
    category_computed = Counter(item["classification_category"] for item in outcomes if item["classification_category"] is not None)
    require(record["classification_count_by_category"] == dict(sorted(category_computed.items())), "CATEGORY_TOTAL_MISMATCH", "categories")
    require(record["outcome_identity_set_sha256"] == semantic_identity(sorted(identities)), "OUTCOME_IDENTITY_SET", "outcomes")
    require(record["source_total"] == len(outcomes), "SOURCE_TOTAL_MISMATCH", "source")
    require(record["accounted_total"] == len(outcomes), "TEST_ACCOUNTING_MISMATCH", "accounted")


ATTEMPT_DISPOSITIONS = {"NO_ARTIFACT", "PRE_PASS_A_STOP", "UNSTABLE", "ABORTED", "REJECTED", "SUCCESSFUL", "SUPERSEDED", "REVIEWED"}
PASS_STATES = {"NOT_STARTED", "RUNNING", "COMPLETED", "MISMATCH", "FAILED"}
STAGING_STATES = {"NONE", "PREPARED", "STAGED", "COMMITTED", "ABORTED"}


def attempt_identity(record: Mapping[str, Any]) -> str:
    return semantic_identity({key: value for key, value in record.items() if key != "attempt_identity_sha256"})


def ledger_root(attempts: Sequence[Mapping[str, Any]]) -> str:
    return semantic_identity([record["attempt_identity_sha256"] for record in attempts])


def validate_attempt_ledger(
    ledger: Mapping[str, Any],
    independently_frozen_expected_attempt_ids: Sequence[str] | None = None,
) -> None:
    _require_fields(
        ledger,
        (
            "attempts",
            "entry_count",
            "expected_attempt_ids",
            "expected_attempt_set_sha256",
            "previous_ledger_root_sha256",
            "current_ledger_root_sha256",
        ),
        "attempt ledger",
    )
    attempts = ledger["attempts"]
    require(ledger["entry_count"] == len(attempts), "ATTEMPT_COUNT", "ledger")
    ids = [record["attempt_id"] for record in attempts]
    if independently_frozen_expected_attempt_ids is not None:
        require(ids == list(independently_frozen_expected_attempt_ids), "FROZEN_ATTEMPT_UNIVERSE", repr(ids))
    require(ids == ledger["expected_attempt_ids"], "ATTEMPT_UNIVERSE", "ordered identifiers")
    require(ledger["expected_attempt_set_sha256"] == semantic_identity(ids), "ATTEMPT_SET_ROOT", "identifiers")
    require(len(ids) == len(set(ids)), "DUPLICATE_ATTEMPT_ID", repr(ids))
    by_id: dict[str, Mapping[str, Any]] = {}
    previous_identity: str | None = None
    for index, record in enumerate(attempts, 1):
        _require_fields(
            record,
            (
                "attempt_id",
                "sequence_number",
                "predecessor_attempt_identity",
                "attempt_identity_sha256",
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
                *INCIDENT_FIELDS,
                "stop_reason",
                "terminal_disposition",
                "manifest",
                "relationship_to_prior_attempts",
            ),
            "attempt record",
        )
        attempt_id = record["attempt_id"]
        require(record["sequence_number"] == index, "ATTEMPT_SEQUENCE", attempt_id)
        require(record["predecessor_attempt_identity"] == previous_identity, "BROKEN_ATTEMPT_PREDECESSOR", attempt_id)
        require(record["attempt_identity_sha256"] == attempt_identity(record), "ATTEMPT_IDENTITY", attempt_id)
        require(record["start_time"] <= record["end_time"], "ATTEMPT_CHRONOLOGY", attempt_id)
        require(record["terminal_disposition"] in ATTEMPT_DISPOSITIONS, "MISSING_TERMINAL_DISPOSITION", attempt_id)
        require(record["pass_a_status"] in PASS_STATES and record["pass_b_status"] in PASS_STATES, "INVALID_PASS_STATE", attempt_id)
        require(record["staging_state"] in STAGING_STATES, "INVALID_STAGING_STATE", attempt_id)
        if record["terminal_disposition"] in {"NO_ARTIFACT", "PRE_PASS_A_STOP"}:
            require(record["worktree"] is None and record["branch"] is None and record["evidence_directory"] is None, "CONFLICTING_ATTEMPT_CLAIM", attempt_id)
            require(record["manifest"] is None and record["commits"] == [] and record["staging_state"] == "NONE", "CONFLICTING_ATTEMPT_CLAIM", attempt_id)
            require(record["pass_a_status"] == "NOT_STARTED" and record["pass_b_status"] == "NOT_STARTED", "CONFLICTING_ATTEMPT_CLAIM", attempt_id)
        if record["terminal_disposition"] in {"UNSTABLE", "REJECTED", "SUCCESSFUL", "SUPERSEDED", "REVIEWED"}:
            require(isinstance(record["manifest"], Mapping), "MISSING_MANIFEST_REFERENCE", attempt_id)
            _require_fields(record["manifest"], ("canonical_path", "byte_size", "sha256"), attempt_id)
        for target in record["relationship_to_prior_attempts"]:
            require(target in by_id, "NONEXISTENT_ATTEMPT_RELATIONSHIP", f"{attempt_id}->{target}")
        by_id[attempt_id] = record
        previous_identity = record["attempt_identity_sha256"]
    require(ledger["current_ledger_root_sha256"] == ledger_root(attempts), "ATTEMPT_LEDGER_ROOT", "current")
    if attempts:
        require(ledger["previous_ledger_root_sha256"] is None or re.fullmatch(r"[0-9A-F]{64}", ledger["previous_ledger_root_sha256"]) is not None, "PREVIOUS_LEDGER_ROOT", "format")


def validate_attempt_authority(ledger: Mapping[str, Any]) -> None:
    validate_attempt_ledger(ledger)
    for record in ledger["attempts"]:
        for field in INCIDENT_FIELDS:
            require(record[field] is False, "ATTEMPT_AUTHORITY_INCIDENT", f"{record['attempt_id']}:{field}")


def evidence_entry_identity(entry: Mapping[str, Any]) -> str:
    return semantic_identity(entry)


def evidence_registry_root(entries: Sequence[Mapping[str, Any]]) -> str:
    return semantic_identity(entries)


def validate_evidence_bindings(registry: Mapping[str, Any], frozen_identity: str | None = None) -> None:
    _require_fields(
        registry,
        (
            "entries",
            "expected_entry_count",
            "expected_path_set_sha256",
            "expected_role_set",
            "expected_artifact_class_set",
            "total_bytes",
            "semantic_root_sha256",
            "registry_identity_sha256",
        ),
        "evidence registry",
    )
    entries = registry["entries"]
    require(isinstance(entries, list) and entries, "EMPTY_EVIDENCE_REGISTRY", "entries")
    paths = validate_path_set(entry["canonical_path"] for entry in entries)
    require(len(entries) == registry["expected_entry_count"], "EVIDENCE_COUNT", "registry")
    require(registry["expected_path_set_sha256"] == semantic_identity(paths), "EVIDENCE_PATH_SET", "registry")
    roles = sorted({entry["role"] for entry in entries})
    classes = sorted({entry["artifact_class"] for entry in entries})
    require(registry["expected_role_set"] == roles, "EVIDENCE_ROLE_SET", "registry")
    require(registry["expected_artifact_class_set"] == classes, "EVIDENCE_CLASS_SET", "registry")
    require(registry["total_bytes"] == sum(entry["byte_size"] for entry in entries), "EVIDENCE_TOTAL_BYTES", "registry")
    for entry in entries:
        _require_fields(
            entry,
            (
                "canonical_path",
                "role",
                "artifact_class",
                "authority_status",
                "byte_size",
                "sha256",
                "git_blob",
                "immutability_status",
                "required_for_recovery",
                "source_attempt",
                "capture_pass",
                "semantic_purpose",
                "external_root_id",
            ),
            "evidence binding",
        )
        require(isinstance(entry["byte_size"], int) and entry["byte_size"] >= 0, "EVIDENCE_SIZE", entry["canonical_path"])
        require(re.fullmatch(r"[0-9A-F]{64}", entry["sha256"] or "") is not None, "EVIDENCE_HASH", entry["canonical_path"])
        require(entry["immutability_status"] in {"GIT_IMMUTABLE", "CONTENT_ADDRESSED_EXTERNAL", "MUTABLE_SOURCE_SNAPSHOT"}, "EVIDENCE_IMMUTABILITY", entry["canonical_path"])
        require(isinstance(entry["required_for_recovery"], bool), "EVIDENCE_RECOVERY_FLAG", entry["canonical_path"])
        require(all(bool(entry[field]) for field in ("role", "artifact_class", "authority_status", "source_attempt", "capture_pass", "semantic_purpose")), "INCOMPLETE_EVIDENCE_BINDING", entry["canonical_path"])
    require(registry["semantic_root_sha256"] == evidence_registry_root(entries), "EVIDENCE_SEMANTIC_ROOT", "registry")
    semantic = {key: value for key, value in registry.items() if key != "registry_identity_sha256"}
    require(registry["registry_identity_sha256"] == semantic_identity(semantic), "EVIDENCE_REGISTRY_IDENTITY", "registry")
    if frozen_identity is not None:
        require(registry["registry_identity_sha256"] == frozen_identity, "FROZEN_EVIDENCE_REGISTRY", "registry")


STABILITY_FIELDS = (
    "repository_branch_or_detached",
    "repository_head",
    "repository_parent",
    "index_sha256",
    "repository_status_sha256",
    "specification_commit",
    "specification_tree",
    "specification_document_blob",
    "include_registry_identity",
    "exclusion_registry_identity",
    "selection_rule_registry_identity",
    "configuration_identity",
    "selection_engine_identity",
    "inventory_generator_identity",
    "boundary_verifier_identity",
    "operational_capture_script_identity",
    "generated_inventory_identity",
    "included_set_identity",
    "excluded_set_identity",
    "separately_bound_set_identity",
    "raw_byte_identity",
    "git_cleaned_identity",
    "file_mode_identity",
    "path_identity",
    "artifact_count",
    "total_bytes",
    "external_evidence_identity",
    "required_evidence_set_identity",
    "attempt_ledger_root_identity",
    "freeze_receipt_identity",
    "gitattributes_identity",
    "writer_count",
    "runtime_operation_count",
    "deployment_attempt_count",
    "service_restart_attempt_count",
)


def validate_multi_pass(pass_a: Mapping[str, Any], pass_b: Mapping[str, Any], final: Mapping[str, Any]) -> None:
    for state_name, state in (("PASS_A", pass_a), ("PASS_B", pass_b), ("FINAL", final)):
        _require_fields(state, STABILITY_FIELDS, state_name)
    for field in STABILITY_FIELDS:
        require(pass_a[field] == pass_b[field] == final[field], "MULTIPASS_MISMATCH", field)
    for state in (pass_a, pass_b, final):
        require(state["writer_count"] == 0, "ACTIVE_WRITER", "multi-pass")
        require(state["runtime_operation_count"] == 0, "RUNTIME_OPERATION", "multi-pass")
        require(state["deployment_attempt_count"] == 0, "DEPLOYMENT_ATTEMPT", "multi-pass")
        require(state["service_restart_attempt_count"] == 0, "SERVICE_RESTART_ATTEMPT", "multi-pass")


AUTHORIZATION_TARGET_PATTERNS = {
    "baseline capture": r"(?:baseline|production disk)[ -]capture",
    "merge": r"\bmerge\b|canonical incorporation",
    "implementation": r"production implementation|\bimplement(?:ation)?\b",
    "deployment": r"\bdeploy(?:ment)?\b",
    "service restart": r"service restart|production restart|restart services?",
    "runtime migration": r"runtime migration",
    "NQ cutover": r"nq cutover",
    "automated paper trading": r"automated paper trading|paper trading",
    "live-money trading": r"live[- ]money trading|live trading",
    "Phase 3C2": r"phase 3c2",
    "Phase 3C1-R11 acceptance": r"phase 3c1-r11 acceptance|r11 acceptance",
    "Bucket 0": r"bucket 0",
    "Bucket 1": r"bucket 1",
}
POSITIVE_AUTHORIZATION = (
    r"\bis authorized\b",
    r"\bare authorized\b",
    r"\bauthoriz(?:e|es|ed)\b(?!\s+no\b)",
    r"\bmay now\b",
    r"\bmay proceed\b",
    r"\bproceed with\b",
    r"\bcan now\b",
    r"\bready for\b",
    r"\bpermission (?:is )?granted\b",
    r"\bapproved for\b",
    r"\bapproval status\s*[:=]\s*(?:approved|authorized|ready)\b",
)
NEGATIVE_AUTHORIZATION = (
    r"\bnot authorized\b",
    r"\bno [^.\n]{0,500}\bauthoriz",
    r"\bdoes not authorize\b",
    r"\bdoes not [^.\n]{0,80}\bauthorize\b",
    r"\bdo not authorize\b",
    r"\bnot[_ -]authorized\b",
    r"\bauthority[_ -]status[^.\n]{0,40}\bnone\b",
    r"\bremains? withheld\b",
    r"\bnot approved\b",
    r"\bmust not\b",
    r"\bmay not\b",
    r"\bcannot\b",
    r"\bblocked\b",
    r"\brequires? (?:a )?separate(?:ly)? (?:requested |governed |explicit )?authorization\b",
)


def find_authorization_leakage(path: str, data: bytes) -> list[str]:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise BoundaryError("GOVERNANCE_TEXT_ENCODING", f"{path}:{exc}") from exc
    normalized = unicodedata.normalize("NFKC", text).casefold()
    segments = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+|[;\n]|\|", normalized) if segment.strip()]
    leaks: list[str] = []
    for segment in segments:
        targets = [name for name, pattern in AUTHORIZATION_TARGET_PATTERNS.items() if re.search(pattern, segment)]
        if not targets:
            continue
        positive = any(re.search(pattern, segment) for pattern in POSITIVE_AUTHORIZATION)
        negative = any(re.search(pattern, segment) for pattern in NEGATIVE_AUTHORIZATION)
        contradictory = positive and negative and bool(re.search(r"\b(?:but|however|nevertheless|except)\b", segment))
        if positive and (not negative or contradictory):
            leaks.append(f"{path}:{','.join(targets)}:{segment[:160]}")
    return leaks


def validate_governance_package(
    changed_paths: Sequence[str],
    content_by_path: Mapping[str, bytes],
    events: Sequence[str] = (),
) -> None:
    paths = validate_path_set(changed_paths)
    require(set(paths) == set(content_by_path), "GOVERNANCE_CONTENT_SET", "changed paths")
    for path in paths:
        require(path.startswith("Architecture/"), "NON_GOVERNANCE_CHANGE", path)
        leaks = find_authorization_leakage(path, content_by_path[path])
        require(not leaks, "AUTHORIZATION_LEAKAGE", repr(leaks))
    forbidden_events = {"runtime_access", "deployment", "service_restart", "baseline_capture", "merge", "trading"}
    require(not (set(events) & forbidden_events), "FORBIDDEN_EVENT", repr(sorted(set(events) & forbidden_events)))


def compare_declared_inventory(selected_paths: Sequence[str], declared_paths: Sequence[str]) -> None:
    selected = validate_path_set(selected_paths)
    declared = validate_path_set(declared_paths)
    require(selected == declared, "ALLOWLIST_DRIFT", f"selected={selected}; declared={declared}")


def ensure_all_questioned_tests(selected_paths: Sequence[str]) -> None:
    selected = set(selected_paths)
    missing = sorted(set(QUESTIONED_TESTS) - selected)
    require(not missing, "QUESTIONED_TEST_OMITTED", repr(missing))


def validate_traceability(
    matrix: Mapping[str, Any],
    case_ids: set[str],
    enforcement_functions: set[str],
    schema_files: set[str],
) -> None:
    findings = matrix["findings"]
    require({item["finding_id"] for item in findings} == {f"BR-{index:02d}" for index in range(1, 14)}, "TRACE_FINDINGS", "BR-01..BR-13")
    requirements = matrix["requirements"]
    require({item["clause"] for item in requirements} == {str(index) for index in range(1, 19)}, "TRACE_CLAUSES", "1..18")
    traced_cases = {
        case
        for item in requirements
        for case in case_ids
        if case in item.get("verification_case_ids", []) or any(case.startswith(prefix) for prefix in item.get("verification_case_prefixes", []))
    }
    require(traced_cases == case_ids, "TRACE_CASES", repr(sorted(traced_cases ^ case_ids)))
    traced_functions = {fn for item in requirements for fn in item.get("enforcing_functions", [])}
    require(traced_functions == enforcement_functions, "TRACE_FUNCTIONS", repr(sorted(traced_functions ^ enforcement_functions)))
    governed_schemas = {entry["schema_file"] for entry in matrix["schema_governance"]}
    require(governed_schemas == schema_files, "TRACE_SCHEMA_FILES", repr(sorted(governed_schemas ^ schema_files)))
    for entry in matrix["schema_governance"]:
        require(entry["field_scope"] == "ALL_DECLARED_FIELDS", "TRACE_SCHEMA_FIELDS", entry["schema_file"])
        require(bool(entry["governing_clauses"]), "TRACE_SCHEMA_FIELDS", entry["schema_file"])
    for item in requirements:
        require(item["machine_rule_ids"], "ORPHAN_CLAUSE", item["clause"])
        require(item.get("verification_case_ids") or item.get("verification_case_prefixes"), "ORPHAN_CLAUSE", item["clause"])
        require(item["expected_result"] and item["observed_result"], "DESCRIPTIVE_ONLY_TRACE", item["clause"])
        require(item["future_capture_obligation"], "MISSING_FUTURE_OBLIGATION", item["clause"])
    for finding in findings:
        _require_fields(finding, ("finding_id", "normative_clauses", "machine_rule_ids", "enforcing_functions", "verification_case_prefixes", "expected_result", "observed_result", "future_capture_obligation"), finding["finding_id"])
        require(finding["normative_clauses"] and finding["machine_rule_ids"] and finding["enforcing_functions"] and finding["verification_case_prefixes"], "DESCRIPTIVE_ONLY_TRACE", finding["finding_id"])
