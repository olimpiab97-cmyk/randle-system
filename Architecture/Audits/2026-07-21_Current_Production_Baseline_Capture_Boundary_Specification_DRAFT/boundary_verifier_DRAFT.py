#!/usr/bin/env python3
"""Draft-only semantic authority for the baseline-boundary specification.

This module validates synthetic specification fixtures.  It refuses to grant
capture, runtime, deployment, merge, or trading authority.  A separately
reviewed operational implementation is required before any production scan.
"""

from __future__ import annotations

import fnmatch
import ast
import hashlib
import json
import locale
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from governed_file_access_DRAFT import extended_length_path as governed_extended_length_path
from governed_file_access_DRAFT import read_binary as governed_read_binary


SERIALIZATION_ID = "RANDLE-CAPTURE-CJSON-1"
PACKAGE_ROLE_MAP_PATH = "Architecture/Audits/2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT/package_role_authority_DRAFT.json"
AUTHORITY_UNIVERSE_PATH = "Architecture/Audits/2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT/governed_authority_universe_DRAFT.json"
CLASSIFICATION_PARSER_NAME = "randle-pytest-quiet-log-parser"
CLASSIFICATION_PARSER_VERSION = "4.0.0-DRAFT"
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


def extended_length_path(path: Path) -> str:
    return governed_extended_length_path(path)


def read_bytes_long(path: Path) -> bytes:
    return governed_read_binary(path).data


def _git(repo: Path, *args: str, text: bool = True) -> str | bytes:
    command = ["git", "-c", "core.longpaths=true", "-c", f"safe.directory={repo.as_posix()}", "-C", os.fspath(repo), *args]
    validate_git_command_argv(command)
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=text,
    )
    require(completed.returncode == 0, "GIT_COMMAND_FAILED", f"{' '.join(args)}: {completed.stderr!r}")
    return completed.stdout


def validate_git_command_argv(command: Sequence[str]) -> None:
    joined = "\0".join(command)
    require("-c\0core.longpaths=true" in joined, "GIT_LONG_PATH_OPTION_MISSING", repr(list(command)))


def _git_cleaned_blob_identity(repository: Path, path: str, data: bytes) -> str:
    completed = subprocess.run(
        [
            "git",
            "-c",
            "core.longpaths=true",
            "-c",
            f"safe.directory={repository.as_posix()}",
            "-C",
            os.fspath(repository),
            "hash-object",
            f"--path={path}",
            "--stdin",
        ],
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    require(completed.returncode == 0, "GIT_CLEAN_FILTER_FAILED", f"{path}:{completed.stderr.decode('utf-8', 'replace')}")
    return completed.stdout.decode("ascii").strip().lower()


def _effective_git_attributes(repository: Path, path: str) -> dict[str, str]:
    raw = _git(repository, "check-attr", "-z", "text", "eol", "filter", "--", path, text=False)
    parts = raw.decode("utf-8", "strict").split("\0")
    if parts and parts[-1] == "":
        parts.pop()
    require(len(parts) % 3 == 0, "GIT_ATTRIBUTE_RESULT", path)
    result: dict[str, str] = {}
    for index in range(0, len(parts), 3):
        checked_path, attribute, value = parts[index:index + 3]
        require(canonical_repository_path(checked_path) == path, "GIT_ATTRIBUTE_PATH", checked_path)
        result[attribute] = value
    return result


def _load_committed_json(repository: Path, commit: str, path: str) -> Mapping[str, Any]:
    canonical = canonical_repository_path(path)
    raw = _git(repository, "show", f"{commit}:{canonical}", text=False)
    value = strict_json_loads(raw)
    require(isinstance(value, Mapping), "COMMITTED_AUTHORITY_NOT_OBJECT", canonical)
    return value


def load_committed_role_map(repository: Path, commit: str) -> dict[str, str]:
    source = _load_committed_json(repository, commit, PACKAGE_ROLE_MAP_PATH)
    _require_fields(source, ("schema_version", "canonical_serialization", "authority", "roles"), "package role authority")
    require(source["canonical_serialization"] == SERIALIZATION_ID, "SERIALIZATION_ID", "package role authority")
    require(source["authority"] == "IMMUTABLE_COMMITTED_DRAFT_ROLE_MAP_PENDING_INDEPENDENT_REVIEW", "ROLE_MAP_AUTHORITY", str(source["authority"]))
    result: dict[str, str] = {}
    paths: set[str] = set()
    for entry in source["roles"]:
        _require_fields(entry, ("role", "path"), "package role")
        role = entry["role"]
        path = canonical_repository_path(entry["path"])
        require(re.fullmatch(r"[a-z][a-z0-9_]+", role or "") is not None, "INVALID_PACKAGE_ROLE", str(role))
        require(role not in result, "DUPLICATE_PACKAGE_ROLE", role)
        require(path not in paths, "DUPLICATE_PACKAGE_ROLE_PATH", path)
        result[role] = path
        paths.add(path)
    required = {
        "specification_document", "include_registry", "exclusion_registry", "selection_rule_registry",
        "boundary_configuration", "selection_engine", "inventory_generator", "boundary_verifier",
        "fixture_runner", "schema_validator", "independent_expectations",
        "package_role_authority", "governed_authority_universe", "package_line_ending_authority",
        "authorization_state", "authorization_state_schema", "attempt_prefix_authority",
        "attempt_prefix_authority_schema", "required_evidence_policy", "required_evidence_policy_schema",
        "operational_package_interface", "operational_package_interface_schema", "case_definitions",
        "case_definition_schema", "independent_expectations_schema", "semantic_traceability_schema",
        "historical_log_parser", "historical_classification", "test_classification_schema",
    }
    require(required <= set(result), "PACKAGE_ROLE_SET", repr(sorted(required - set(result))))
    require(result["package_role_authority"] == PACKAGE_ROLE_MAP_PATH, "ROLE_MAP_SELF_PATH", result["package_role_authority"])
    return result


def load_committed_authority_universe(repository: Path, commit: str) -> Mapping[str, Any]:
    value = _load_committed_json(repository, commit, AUTHORITY_UNIVERSE_PATH)
    _require_fields(value, ("schema_version", "canonical_serialization", "authority", "mandatory_tests", "attempt_authority", "evidence_authority", "environment_identity_fields", "governance_targets", "parser_authority"), "authority universe")
    require(value["authority"] == "IMMUTABLE_COMMITTED_DRAFT_UNIVERSE_PENDING_INDEPENDENT_REVIEW", "AUTHORITY_UNIVERSE_STATUS", str(value["authority"]))
    require(value["canonical_serialization"] == SERIALIZATION_ID, "SERIALIZATION_ID", "authority universe")
    return value


def load_local_authority_universe() -> Mapping[str, Any]:
    path = Path(__file__).resolve().parent / "governed_authority_universe_DRAFT.json"
    value = strict_json_loads(read_bytes_long(path))
    require(isinstance(value, Mapping), "AUTHORITY_UNIVERSE_NOT_OBJECT", os.fspath(path))
    _require_fields(value, ("authority", "mandatory_tests", "attempt_authority", "evidence_authority", "environment_identity_fields", "governance_targets", "parser_authority"), "local authority universe")
    return value


def derive_committed_package_authority(
    repository: Path,
    commit: str,
) -> dict[str, Any]:
    """Derive normative Git-object bytes and separately observe checkout bytes.

    This is the operational binding surface used by freeze verification.  Values
    supplied by a registry or receipt are never treated as their own evidence.
    """
    resolved_commit = str(_git(repository, "rev-parse", f"{commit}^{{commit}}")).strip().lower()
    role_paths = load_committed_role_map(repository, resolved_commit)
    object_format = str(_git(repository, "rev-parse", "--show-object-format")).strip()
    entries: list[dict[str, Any]] = []
    for role, raw_path in sorted(role_paths.items()):
        path = canonical_repository_path(raw_path)
        blob = str(_git(repository, "rev-parse", f"{resolved_commit}:{path}")).strip().lower()
        validate_git_object(blob, object_format, f"package role {role}")
        committed = _git(repository, "show", f"{resolved_commit}:{path}", text=False)
        if path.endswith(".json"):
            verify_stored_canonical_json(committed)
        disk_path = repository.joinpath(*PurePosixPath(path).parts)
        try:
            disk = read_bytes_long(disk_path)
        except (FileNotFoundError, OSError) as exc:
            raise BoundaryError("PACKAGE_FILE_MISSING", f"{path}:{exc}") from exc
        worktree_cleaned_blob = _git_cleaned_blob_identity(repository, path, disk)
        attributes = _effective_git_attributes(repository, path)
        package_scoped = path.startswith("Architecture/Audits/2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT/")
        governed_lf = package_scoped and (path.endswith((".json", ".py", ".md")) or path.endswith("/.gitattributes"))
        if governed_lf:
            require(attributes.get("eol") == "lf", "PACKAGE_LF_ATTRIBUTE_POLICY", path)
        cleaned_matches = worktree_cleaned_blob == blob
        raw_matches = disk == committed
        entries.append(
            {
                "role": role,
                "canonical_path": path,
                "byte_size": len(committed),
                "authoritative_byte_source": "COMMITTED_GIT_BLOB",
                "raw_sha256": sha256_bytes(committed),
                "git_blob": blob,
                "worktree_byte_size": len(disk),
                "worktree_raw_sha256": sha256_bytes(disk),
                "worktree_git_cleaned_blob": worktree_cleaned_blob,
                "effective_git_attributes": attributes,
                "worktree_matches_authoritative_bytes": raw_matches,
                "worktree_git_cleaned_matches_blob": cleaned_matches,
                "expected_checkout_transformation": (not raw_matches) and cleaned_matches and not governed_lf,
                "unexpected_checkout_transformation": (not raw_matches) and (governed_lf or not cleaned_matches),
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
        "checkout_transform_detected": any(not entry["worktree_matches_authoritative_bytes"] for entry in entries),
        "unexpected_checkout_transform_detected": any(entry["unexpected_checkout_transformation"] for entry in entries),
        "git_cleaned_mismatch_detected": any(not entry["worktree_git_cleaned_matches_blob"] for entry in entries),
    }
    authority["authority_sha256"] = semantic_identity(authority)
    return authority


def verify_committed_package_authority(
    expected: Mapping[str, Any],
    repository: Path,
) -> None:
    derived = derive_committed_package_authority(repository, expected["commit"])
    require(derived == expected, "PACKAGE_AUTHORITY_MISMATCH", "committed package or working bytes changed")


def validate_package_checkout(authority: Mapping[str, Any]) -> None:
    require(not authority["unexpected_checkout_transform_detected"], "PACKAGE_CHECKOUT_TRANSFORMED", "unexpected checkout transformation")
    require(not authority["git_cleaned_mismatch_detected"], "PACKAGE_WORKTREE_GIT_IDENTITY", "worktree clean-filter identity differs")


def derive_accepted_specification_authority(repository: Path, commit: str) -> dict[str, Any]:
    package = derive_committed_package_authority(repository, commit)
    entries = {item["role"]: item for item in package["entries"]}
    required = {
        "specification_document",
        "package_role_authority",
        "authorization_state",
        "boundary_verifier",
        "selection_rule_registry",
    }
    require(required <= set(entries), "ACCEPTED_SPECIFICATION_ROLE_SET", repr(sorted(required - set(entries))))
    state_path = entries["authorization_state"]["canonical_path"]
    authorization_state = _load_committed_json(repository, package["commit"], state_path)
    validate_authorization_state(authorization_state)
    schema_set = sorted(
        [{
            "role": entry["role"],
            "path": entry["canonical_path"],
            "git_blob": entry["git_blob"],
            "raw_sha256": entry["raw_sha256"],
        }
        for entry in package["entries"]
        if entry["role"].endswith("_schema")],
        key=lambda item: item["role"],
    )
    authority = {
        "interface_version": "RANDLE-BASELINE-BOUNDARY-4",
        "commit": package["commit"],
        "parent": package["parent"],
        "tree": package["tree"],
        "specification_document_blob": entries["specification_document"]["git_blob"],
        "schema_set": schema_set,
        "schema_set_identity": semantic_identity(schema_set),
        "package_role_map_blob": entries["package_role_authority"]["git_blob"],
        "rule_registry_blob": entries["selection_rule_registry"]["git_blob"],
        "verifier_blob": entries["boundary_verifier"]["git_blob"],
        "authorization_state_blob": entries["authorization_state"]["git_blob"],
        "authorization_state_identity": semantic_identity(authorization_state),
    }
    authority["accepted_specification_identity"] = semantic_identity(authority)
    return authority


def validate_accepted_specification_authority(
    repository: Path,
    accepted_authority: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a previously frozen acceptance receipt against Git objects."""
    _require_fields(
        accepted_authority,
        (
            "interface_version",
            "commit",
            "parent",
            "tree",
            "specification_document_blob",
            "schema_set",
            "schema_set_identity",
            "package_role_map_blob",
            "rule_registry_blob",
            "verifier_blob",
            "authorization_state_blob",
            "authorization_state_identity",
            "accepted_specification_identity",
        ),
        "accepted specification authority",
    )
    semantic = {key: value for key, value in accepted_authority.items() if key != "accepted_specification_identity"}
    require(
        accepted_authority["accepted_specification_identity"] == semantic_identity(semantic),
        "ACCEPTED_SPECIFICATION_RECEIPT_IDENTITY",
        "receipt",
    )
    derived = derive_accepted_specification_authority(repository, str(accepted_authority["commit"]))
    require(derived == dict(accepted_authority), "ACCEPTED_SPECIFICATION_AUTHORITY", "Git objects differ from accepted receipt")
    return derived


def derive_selection_from_accepted_specification(
    repository: Path,
    accepted_authority: Mapping[str, Any],
    *,
    capture_mode: bool = False,
    selection_root: Path | None = None,
) -> dict[str, Any]:
    """Load policy from the accepted commit and apply it to a separately governed root."""
    validated_acceptance = validate_accepted_specification_authority(repository, accepted_authority)
    accepted_commit = validated_acceptance["commit"]
    package = derive_committed_package_authority(repository, accepted_commit)
    validate_package_checkout(package)
    by_role = {entry["role"]: entry for entry in package["entries"]}
    required_roles = {
        "include_registry", "exclusion_registry", "selection_rule_registry", "boundary_configuration",
        "governed_authority_universe", "selection_engine", "inventory_generator", "boundary_verifier",
    }
    require(required_roles <= set(by_role), "ACCEPTED_SELECTION_ROLE_SET", repr(sorted(required_roles - set(by_role))))
    executing_paths = {
        "boundary_verifier": Path(__file__).resolve(),
    }
    from inventory_generator_DRAFT import __file__ as inventory_file
    from selection_engine_DRAFT import __file__ as selection_file, derive_repository_selection
    executing_paths.update({"inventory_generator": Path(inventory_file).resolve(), "selection_engine": Path(selection_file).resolve()})
    for role, executing_path in executing_paths.items():
        require(sha256_bytes(read_bytes_long(executing_path)) == by_role[role]["raw_sha256"], "EXECUTING_CODE_NOT_ACCEPTED_BLOB", role)
    include = _load_committed_json(repository, package["commit"], by_role["include_registry"]["canonical_path"])
    exclusion = _load_committed_json(repository, package["commit"], by_role["exclusion_registry"]["canonical_path"])
    rules = _load_committed_json(repository, package["commit"], by_role["selection_rule_registry"]["canonical_path"])
    configuration = _load_committed_json(repository, package["commit"], by_role["boundary_configuration"]["canonical_path"])
    universe = _load_committed_json(repository, package["commit"], by_role["governed_authority_universe"]["canonical_path"])
    bindings = {
        "include_registry_blob": by_role["include_registry"]["git_blob"],
        "exclusion_registry_blob": by_role["exclusion_registry"]["git_blob"],
        "selection_rule_registry_blob": by_role["selection_rule_registry"]["git_blob"],
        "boundary_configuration_blob": by_role["boundary_configuration"]["git_blob"],
    }
    governed_root = selection_root if selection_root is not None else repository
    same_repository = governed_root.resolve(strict=True) == repository.resolve(strict=True)
    return derive_repository_selection(
        governed_root, include, exclusion, rules, configuration,
        authority_universe=universe,
        registry_bindings=bindings,
        capture_mode=capture_mode,
        governed_repository_commit=accepted_commit if same_repository else None,
    )


def validate_operational_package_authority(
    repository: Path,
    accepted_specification: Mapping[str, Any],
    package_claim: Mapping[str, Any],
    freeze_claim: Mapping[str, Any],
    *,
    external_payloads: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    _require_fields(
        accepted_specification,
        ("commit", "interface_version", "accepted_specification_identity"),
        "accepted specification",
    )
    _require_fields(
        package_claim,
        (
            "identity_kind",
            "accepted_specification_commit",
            "accepted_specification_interface_version",
            "independent_review_decision",
            "package_review_receipt_sha256",
            "package_manifest_sha256",
            "operational_script_raw_sha256",
            "supporting_module_identities",
            "freeze_package_identity",
        ),
        "future operational package",
    )
    require(package_claim["accepted_specification_commit"] == accepted_specification["commit"], "OPERATIONAL_WRONG_SPECIFICATION", "commit")
    require(package_claim["accepted_specification_interface_version"] == accepted_specification["interface_version"], "OPERATIONAL_INTERFACE_VERSION", "compatibility")
    require(package_claim["independent_review_decision"] == "ACCEPT", "OPERATIONAL_PACKAGE_UNREVIEWED", str(package_claim["independent_review_decision"]))
    require(re.fullmatch(r"[0-9A-F]{64}", package_claim["package_review_receipt_sha256"] or "") is not None, "OPERATIONAL_REVIEW_RECEIPT", "hash")
    require(re.fullmatch(r"[0-9A-F]{64}", package_claim["package_manifest_sha256"] or "") is not None, "OPERATIONAL_MANIFEST", "hash")
    if package_claim["identity_kind"] == "GIT_COMMIT":
        _require_fields(
            package_claim,
            ("package_commit", "package_parent", "package_tree", "operational_script_path", "operational_script_git_blob"),
            "Git operational package",
        )
        commit = str(_git(repository, "rev-parse", f"{package_claim['package_commit']}^{{commit}}")).strip().lower()
        require(commit != accepted_specification["commit"], "SELF_REFERENTIAL_SPECIFICATION_PACKAGE", commit)
        require(commit == package_claim["package_commit"], "OPERATIONAL_PACKAGE_COMMIT", commit)
        ancestor = subprocess.run(
            ["git", "-c", "core.longpaths=true", "-c", f"safe.directory={repository.as_posix()}", "-C", os.fspath(repository), "merge-base", "--is-ancestor", accepted_specification["commit"], commit],
            check=False,
        )
        require(ancestor.returncode == 0, "OPERATIONAL_PACKAGE_NOT_DESCENDANT", commit)
        parent = str(_git(repository, "rev-parse", f"{commit}^")).strip().lower()
        tree = str(_git(repository, "rev-parse", f"{commit}^{{tree}}")).strip().lower()
        require(parent == package_claim["package_parent"], "OPERATIONAL_PACKAGE_PARENT", parent)
        require(tree == package_claim["package_tree"], "OPERATIONAL_PACKAGE_TREE", tree)
        script_path = canonical_repository_path(package_claim["operational_script_path"])
        script_blob = str(_git(repository, "rev-parse", f"{commit}:{script_path}")).strip().lower()
        script_bytes = _git(repository, "show", f"{commit}:{script_path}", text=False)
        require(script_blob == package_claim["operational_script_git_blob"], "OPERATIONAL_SCRIPT_BLOB", script_path)
        require(sha256_bytes(script_bytes) == package_claim["operational_script_raw_sha256"], "OPERATIONAL_SCRIPT_RAW_HASH", script_path)
        derived = {"identity_kind": "GIT_COMMIT", "commit": commit, "parent": parent, "tree": tree, "script_blob": script_blob, "script_raw_sha256": sha256_bytes(script_bytes)}
    elif package_claim["identity_kind"] == "EXTERNAL_CONTENT_ADDRESS":
        _require_fields(package_claim, ("package_content_address", "operational_script_content_address"), "external operational package")
        require(external_payloads is not None, "OPERATIONAL_EXTERNAL_PAYLOAD_MISSING", "payloads")
        package_address = package_claim["package_content_address"]
        script_address = package_claim["operational_script_content_address"]
        require(re.fullmatch(r"SHA256:[0-9A-F]{64}", package_address or "") is not None, "OPERATIONAL_EXTERNAL_ADDRESS", "package")
        require(re.fullmatch(r"SHA256:[0-9A-F]{64}", script_address or "") is not None, "OPERATIONAL_EXTERNAL_ADDRESS", "script")
        require(package_address in external_payloads and script_address in external_payloads, "OPERATIONAL_EXTERNAL_PAYLOAD_MISSING", "address")
        require("SHA256:" + sha256_bytes(external_payloads[package_address]) == package_address, "OPERATIONAL_EXTERNAL_ADDRESS", "package bytes")
        require("SHA256:" + sha256_bytes(external_payloads[script_address]) == script_address, "OPERATIONAL_EXTERNAL_ADDRESS", "script bytes")
        require(sha256_bytes(external_payloads[script_address]) == package_claim["operational_script_raw_sha256"], "OPERATIONAL_SCRIPT_RAW_HASH", "external")
        derived = {"identity_kind": "EXTERNAL_CONTENT_ADDRESS", "package_content_address": package_address, "script_content_address": script_address}
    else:
        raise BoundaryError("OPERATIONAL_IDENTITY_KIND", str(package_claim["identity_kind"]))
    package_identity = semantic_identity({**derived, "manifest": package_claim["package_manifest_sha256"], "review": package_claim["package_review_receipt_sha256"], "supporting": package_claim["supporting_module_identities"]})
    require(package_claim["freeze_package_identity"] == package_identity, "OPERATIONAL_FREEZE_PACKAGE_IDENTITY", "claim")
    require(freeze_claim.get("accepted_specification_identity") == accepted_specification["accepted_specification_identity"], "FREEZE_ACCEPTED_SPECIFICATION_IDENTITY", "freeze")
    require(freeze_claim.get("operational_package_identity") == package_identity, "FREEZE_OPERATIONAL_PACKAGE_IDENTITY", "freeze")
    return {**derived, "operational_package_identity": package_identity}


def _filesystem_identity(repository: Path) -> dict[str, Any]:
    root_stat = os.stat(extended_length_path(repository))
    identity: dict[str, Any] = {
        "filesystem_type": "NTFS" if os.name == "nt" else platform.system(),
        "volume_identity": str(root_stat.st_dev),
        "root_directory_identity": str(root_stat.st_ino),
        "case_sensitive": os.name != "nt",
    }
    if os.name == "nt":
        import ctypes
        root = Path(repository.anchor)
        volume_name = ctypes.create_unicode_buffer(1024)
        serial = ctypes.c_uint32()
        maximum = ctypes.c_uint32()
        flags = ctypes.c_uint32()
        fs_name = ctypes.create_unicode_buffer(256)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        ok = kernel32.GetVolumeInformationW(str(root), volume_name, len(volume_name), ctypes.byref(serial), ctypes.byref(maximum), ctypes.byref(flags), fs_name, len(fs_name))
        require(bool(ok), "FILESYSTEM_IDENTITY_FAILED", f"GetVolumeInformationW:{ctypes.get_last_error()}")
        guid = ctypes.create_unicode_buffer(1024)
        ok = kernel32.GetVolumeNameForVolumeMountPointW(str(root), guid, len(guid))
        require(bool(ok), "FILESYSTEM_IDENTITY_FAILED", f"GetVolumeNameForVolumeMountPointW:{ctypes.get_last_error()}")
        identity.update({"filesystem_type": fs_name.value, "volume_identity": f"{guid.value}|{serial.value:08X}"})
    return identity


def _environment_identity(repository: Path, authority: Mapping[str, Any], package: Mapping[str, Any]) -> dict[str, Any]:
    relevant_environment = {key: os.environ.get(key) for key in ("LANG", "LC_ALL", "PYTHONHASHSEED", "PYTHONUTF8", "TZ", "GIT_CONFIG_COUNT", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_GLOBAL")}
    all_git_config = str(_git(repository, "config", "--show-origin", "--list", text=True))
    git_behavior = "\n".join(line for line in all_git_config.splitlines() if re.search(r"\b(?:core\.(?:autocrlf|eol|safecrlf|ignorecase|symlinks)|filter\.|diff\.|merge\.)", line, re.I))
    executable_records = []
    for name, candidate in (("python", Path(sys.executable)), ("git", Path(shutil.which("git") or ""))):
        require(candidate.is_file(), "EXECUTABLE_IDENTITY_MISSING", name)
        executable_records.append({"name": name, "path": os.path.abspath(os.fspath(candidate)), "sha256": sha256_bytes(read_bytes_long(candidate))})
    filesystem = _filesystem_identity(repository)
    role_entry = next(entry for entry in package["entries"] if entry["role"] == "package_role_authority")
    schema_entries = sorted(
        ({"role": entry["role"], "git_blob": entry["git_blob"]} for entry in package["entries"] if entry["role"].endswith("_schema")),
        key=lambda item: item["role"],
    )
    return {
        "operating_system_identity": {"name": platform.system(), "version": platform.version(), "release": platform.release(), "architecture": platform.machine()},
        "python_version": platform.python_version(),
        "git_version": str(_git(repository, "--version")).strip(),
        "filesystem_type": filesystem["filesystem_type"],
        "volume_identity": filesystem["volume_identity"],
        "root_directory_identity": filesystem["root_directory_identity"],
        "locale": locale.setlocale(locale.LC_ALL, None),
        "timezone": list(time.tzname),
        "working_directory": os.path.abspath(os.fspath(repository)),
        "execution_environment_sha256": semantic_identity(relevant_environment),
        "git_behavior_configuration_sha256": sha256_bytes(git_behavior.encode("utf-8")),
        "parser_versions_sha256": semantic_identity(authority["parser_authority"]),
        "dependency_versions_sha256": semantic_identity({"python": platform.python_version(), "jsonschema": "4.25.1"}),
        "executable_identities_sha256": semantic_identity(executable_records),
        "package_role_map_identity": role_entry["raw_sha256"],
        "schema_set_identity": semantic_identity(schema_entries),
        "verifier_identity": next(entry["raw_sha256"] for entry in package["entries"] if entry["role"] == "boundary_verifier"),
    }


def derive_repository_freeze_state(
    repository: Path,
    specification_commit: str,
    terminal_result: Mapping[str, Any],
    evidence_registry: Mapping[str, Any],
    attempt_ledger: Mapping[str, Any],
    evidence_artifact_bytes: Mapping[str, bytes],
    *,
    timestamp_authority: str,
    authorization_identity: str,
) -> dict[str, Any]:
    """Derive freeze state without caller-selected roles or inventory values."""
    from inventory_generator_DRAFT import enumerate_inventory

    package = derive_committed_package_authority(repository, specification_commit)
    entries = {entry["role"]: entry for entry in package["entries"]}
    require("operational_capture_script" in entries, "FREEZE_OPERATIONAL_SCRIPT_NOT_BOUND", "a later separately reviewed package role is required")
    require("attempt_authority_anchor" in entries, "FREEZE_ATTEMPT_AUTHORITY_NOT_BOUND", "the append-only attempt authority must be a committed package role")
    authority = load_committed_authority_universe(repository, package["commit"])
    role_paths = load_committed_role_map(repository, package["commit"])
    attempt_authority_anchor = _load_committed_json(repository, package["commit"], role_paths["attempt_authority_anchor"])
    head = str(_git(repository, "rev-parse", "HEAD")).strip().lower()
    require(head == package["commit"], "FREEZE_HEAD_NOT_SPECIFICATION_COMMIT", head)
    inventory_document = enumerate_inventory(repository)
    generated_inventory = inventory_document["artifacts"]
    validate_inventory_security(generated_inventory)
    sets = validate_terminal_result(terminal_result)
    repository_universe = sorted(key for key in terminal_result["enumeration_universe"] if "::" not in key)
    require(repository_universe == sorted(item["canonical_path"] for item in generated_inventory), "FREEZE_INVENTORY_DISPOSITION_UNIVERSE", "repository paths")
    validate_attempt_ledger(attempt_ledger, attempt_authority_anchor)
    validate_evidence_bindings(evidence_registry, authority, attempt_ledger=attempt_ledger, repository=repository, artifact_bytes=evidence_artifact_bytes)
    branch_process = subprocess.run(["git", "-c", "core.longpaths=true", "-c", f"safe.directory={repository.as_posix()}", "-C", os.fspath(repository), "symbolic-ref", "-q", "HEAD"], capture_output=True, text=True, check=False)
    branch = branch_process.stdout.strip() if branch_process.returncode == 0 else "DETACHED"
    index_path = Path(str(_git(repository, "rev-parse", "--git-path", "index")).strip())
    if not index_path.is_absolute():
        index_path = repository / index_path
    index_bytes = read_bytes_long(index_path)
    status = _git(repository, "status", "--porcelain=v2", "-z", "--branch", "--untracked-files=all", text=False)
    attribute_paths = [item.decode("utf-8", "surrogateescape") for item in _git(repository, "ls-files", "-z", text=False).split(b"\0") if item and item.decode("utf-8", "surrogateescape").endswith(".gitattributes")]
    attributes = [{"path": path, "sha256": sha256_bytes(read_bytes_long(repository.joinpath(*PurePosixPath(path).parts)))} for path in sorted(attribute_paths)]
    environment = _environment_identity(repository, authority, package)
    filesystem = _filesystem_identity(repository)
    total_bytes = sum(int(item["raw_byte_size"] or 0) for item in generated_inventory)
    state = {
        "specification_commit": package["commit"], "specification_parent": package["parent"], "specification_tree": package["tree"],
        "specification_document_blob": entries["specification_document"]["git_blob"], "specification_document_sha256": entries["specification_document"]["raw_sha256"],
        "include_registry_blob": entries["include_registry"]["git_blob"], "include_registry_sha256": entries["include_registry"]["raw_sha256"],
        "exclusion_registry_blob": entries["exclusion_registry"]["git_blob"], "exclusion_registry_sha256": entries["exclusion_registry"]["raw_sha256"],
        "selection_rule_registry_blob": entries["selection_rule_registry"]["git_blob"], "selection_rule_registry_sha256": entries["selection_rule_registry"]["raw_sha256"],
        "boundary_configuration_blob": entries["boundary_configuration"]["git_blob"], "boundary_configuration_sha256": entries["boundary_configuration"]["raw_sha256"],
        "selection_engine_blob": entries["selection_engine"]["git_blob"], "selection_engine_sha256": entries["selection_engine"]["raw_sha256"],
        "inventory_generator_blob": entries["inventory_generator"]["git_blob"], "inventory_generator_sha256": entries["inventory_generator"]["raw_sha256"],
        "boundary_verifier_blob": entries["boundary_verifier"]["git_blob"], "boundary_verifier_sha256": entries["boundary_verifier"]["raw_sha256"],
        "operational_capture_script_blob": entries["operational_capture_script"]["git_blob"], "operational_capture_script_sha256": entries["operational_capture_script"]["raw_sha256"],
        "package_role_map_blob": entries["package_role_authority"]["git_blob"], "package_role_map_sha256": entries["package_role_authority"]["raw_sha256"],
        "authority_universe_blob": entries["governed_authority_universe"]["git_blob"], "authority_universe_sha256": entries["governed_authority_universe"]["raw_sha256"],
        "package_authority_sha256": package["authority_sha256"], "generated_inventory_sha256": inventory_document["inventory_sha256"],
        "artifact_count": len(generated_inventory), "total_bytes": total_bytes,
        "included_set_sha256": semantic_identity(sets["INCLUDE"]), "excluded_set_sha256": semantic_identity(sets["EXCLUDE"]), "separately_bound_set_sha256": semantic_identity(sets["SEPARATE_AND_BIND"]),
        "repository_head": head, "repository_branch_or_detached": branch, "index_sha256": sha256_bytes(index_bytes), "repository_status_sha256": sha256_bytes(status),
        "gitattributes_sha256": semantic_identity(attributes), "git_version": environment["git_version"], "python_version": environment["python_version"],
        "operating_system_identity": environment["operating_system_identity"], "filesystem_identity": filesystem, "execution_environment_identity": environment,
        "repository_object_format": package["object_format"], "timestamp_authority": timestamp_authority, "authorization_identity": authorization_identity,
        "freeze_receipt_schema_sha256": entries["freeze_receipt_schema"]["raw_sha256"], "required_evidence_set_sha256": evidence_registry["registry_identity_sha256"],
        "attempt_ledger_root_sha256": attempt_ledger["current_ledger_root_sha256"], "attempt_authority_anchor_sha256": entries["attempt_authority_anchor"]["raw_sha256"],
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
            raise BoundaryError("CASE_ONLY_PATH_COLLISION", f"{collisions[key]} <> {path}")
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


def validate_boundary_configuration(configuration: Mapping[str, Any], authority_universe: Mapping[str, Any] | None = None) -> None:
    authority = authority_universe or load_local_authority_universe()
    required_policies = (
        "discovery_policy", "path_policy", "long_path_policy", "ads_policy", "reparse_policy",
        "test_discovery_policy", "terminal_disposition_policy", "canonicalization_policy",
        "freeze_policy", "evidence_policy", "stability_policy", "governance_policy",
    )
    _require_fields(configuration, required_policies, "boundary configuration")
    discovery = configuration["discovery_policy"]
    _require_fields(discovery, ("supported_parsers", "governed_dynamic_dependencies", "governed_external_dependencies", "missing_literal_target", "unknown_governed_file", "unresolved_dynamic_dependency"), "discovery policy")
    require(discovery["supported_parsers"] == authority["parser_authority"]["dependency"], "PARSER_AUTHORITY_UNIVERSE", "dependency parser list")
    require(isinstance(discovery["governed_external_dependencies"], list) and discovery["governed_external_dependencies"], "EMPTY_DISCOVERY_POLICY", "external dependencies")
    for item in discovery["governed_dynamic_dependencies"]:
        _require_fields(item, ("source_path", "call_name", "line", "column", "target_module", "evidence"), "dynamic dependency")
        require(item["line"] >= 1 and item["column"] >= 0, "DYNAMIC_CALL_SITE", repr(item))
    require(configuration["long_path_policy"] == {"enabled": True, "hidden_and_system_entries": "ENUMERATE", "silent_skip": "STOP", "windows_path_form": "EXTENDED_LENGTH"}, "LONG_PATH_POLICY", "exact policy")
    require(configuration["ads_policy"].get("every_filesystem_file") is True and configuration["ads_policy"].get("appearing_or_disappearing") == "STOP" and configuration["ads_policy"].get("unsupported_environment") == "STOP", "ADS_POLICY", "exact policy")
    require(configuration["stability_policy"] == {"passes": ["PASS_A", "PASS_B", "FINAL"], "mismatch": "TERMINATE_UNSTABLE", "writer_count": 0, "runtime_operation_count": 0}, "STABILITY_POLICY", "exact policy")
    require(configuration["governance_policy"]["targets"] == authority["governance_targets"], "GOVERNANCE_TARGET_UNIVERSE", "targets")
    roots = configuration.get("external_roots")
    require(isinstance(roots, list) and bool(roots), "INVALID_EXTERNAL_ROOT", "external_roots")
    root_ids: set[str] = set()
    for item in roots:
        _require_fields(item, ("root_id", "role", "binding_required_at_freeze"), "external root")
        require(re.fullmatch(r"[a-z][a-z0-9_]+", item["root_id"] or "") is not None, "INVALID_EXTERNAL_ROOT", str(item.get("root_id")))
        require(item["root_id"] not in root_ids, "INVALID_EXTERNAL_ROOT", item["root_id"])
        require(len(item["role"].strip()) >= 20 and item["binding_required_at_freeze"] is True, "INVALID_EXTERNAL_ROOT", item["root_id"])
        root_ids.add(item["root_id"])


def _validate_evidence(evidence: Any, context: str) -> None:
    require(isinstance(evidence, list) and evidence, "MISSING_EVIDENCE", context)
    require(all(isinstance(item, str) and len(item.strip()) >= 3 for item in evidence), "MISSING_EVIDENCE", context)


def validate_registries(
    include_registry: Mapping[str, Any],
    exclusion_registry: Mapping[str, Any],
    rules: Mapping[str, Mapping[str, Any]],
    *,
    authority_universe: Mapping[str, Any],
    capture_mode: bool = False,
    accepted_review_binding: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Mapping[str, Any]], list[Mapping[str, Any]]]:
    _require_fields(include_registry, ("entries", "canonical_serialization"), "include registry")
    _require_fields(exclusion_registry, ("entries", "canonical_serialization", "validation_mode"), "exclusion registry")
    require(include_registry["canonical_serialization"] == SERIALIZATION_ID, "SERIALIZATION_ID", "include registry")
    require(exclusion_registry["canonical_serialization"] == SERIALIZATION_ID, "SERIALIZATION_ID", "exclusion registry")
    expected_mode = "CAPTURE" if capture_mode else "DRAFT_SPECIFICATION"
    require(exclusion_registry["validation_mode"] == expected_mode, "EXCLUSION_VALIDATION_MODE", expected_mode)
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
    validate_questioned_test_authority(repository_includes, validated_exclusions, authority_universe)
    return include_by_key, validated_exclusions


def validate_questioned_test_authority(
    repository_includes: Mapping[str, Mapping[str, Any]],
    exclusions: Sequence[Mapping[str, Any]],
    authority_universe: Mapping[str, Any] | None = None,
    frozen_content_identities: Mapping[str, Mapping[str, str]] | None = None,
) -> None:
    authority = authority_universe or load_local_authority_universe()
    declared = {item["path"]: item for item in authority["mandatory_tests"]}
    require(set(declared) == set(QUESTIONED_TESTS), "QUESTIONED_TEST_AUTHORITY_UNIVERSE", repr(sorted(set(declared) ^ set(QUESTIONED_TESTS))))
    for path in QUESTIONED_TESTS:
        entry = repository_includes.get(path)
        normative = declared[path]
        require(entry is not None, "QUESTIONED_TEST_REGISTRY_OMITTED", path)
        for field in ("class", "selection_rule_id", "authority_status", "rationale", "committed_role", "content_identity_policy", "evidence_references"):
            require(entry.get(field) == normative[field], "QUESTIONED_TEST_AUTHORITY_TUPLE", f"{path}:{field}")
        require(entry["required_capture_form"] == "RAW_AND_GIT_OBJECT", "QUESTIONED_TEST_CAPTURE_FORM", path)
        require(entry["expected_existence_state"] == "MUST_EXIST_AT_FREEZE", "QUESTIONED_TEST_EXISTENCE", path)
        require(not any(_exclusion_matches(path, exclusion) for exclusion in exclusions), "QUESTIONED_TEST_EXCLUSION", path)
        if frozen_content_identities is not None:
            identity = frozen_content_identities.get(path)
            require(isinstance(identity, Mapping), "QUESTIONED_TEST_CONTENT_IDENTITY", path)
            require(re.fullmatch(r"[0-9A-F]{64}", str(identity.get("raw_sha256", ""))) is not None, "QUESTIONED_TEST_RAW_IDENTITY", path)
            object_format = str(identity.get("repository_object_format", ""))
            validate_git_object(identity.get("computed_git_blob"), object_format, f"mandatory test {path}")


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
        "rule_registry_blob",
        "authority",
        "authority_identity",
        "rationale",
        "evidence",
        "evidence_identities",
        "source_identity",
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
        require(record["evidence_identities"] == [semantic_identity(item) for item in record["evidence"]], "DISPOSITION_EVIDENCE_IDENTITY", key)
        require(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", record["rule_registry_blob"] or "") is not None, "DISPOSITION_RULE_BLOB", key)
        require(record["authority_identity"] == semantic_identity(record["authority"]), "DISPOSITION_AUTHORITY_IDENTITY", key)
        require(re.fullmatch(r"[0-9A-F]{64}", str(record["source_identity"])) is not None, "DISPOSITION_SOURCE_IDENTITY", key)
        require(len(record["rationale"].strip()) >= 20, "MISSING_RATIONALE", key)
        if disposition == "SEPARATE_AND_BIND":
            require(bool(record["binding_obligation_ids"]), "MISSING_SEPARATE_BINDING", key)
            require(bool(record["separate_evidence_registry_identity"]), "MISSING_SEPARATE_REGISTRY", key)
            require(record["exclusion_review_identity"] is None, "SEPARATE_HAS_EXCLUSION_REVIEW", key)
        elif disposition == "EXCLUDE":
            require(bool(record["exclusion_review_identity"]), "MISSING_EXCLUSION_REVIEW", key)
            require(not record["binding_obligation_ids"], "EXCLUDED_HAS_BINDING", key)
            require(record["separate_evidence_registry_identity"] is None, "EXCLUDED_HAS_SEPARATE_REGISTRY", key)
            require(record["capture_form"] == "NO_CONTENT_EXCLUSION", "EXCLUDED_HAS_INCLUDE_METADATA", key)
        else:
            require(record["exclusion_review_identity"] is None, "INCLUDED_HAS_EXCLUSION", key)
            require(not record["binding_obligation_ids"], "INCLUDED_HAS_BINDING", key)
            require(record["separate_evidence_registry_identity"] is None, "INCLUDED_HAS_SEPARATE_REGISTRY", key)
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


def validate_terminal_result(result: Mapping[str, Any]) -> dict[str, list[str]]:
    _require_fields(
        result,
        (
            "enumeration_universe", "terminal_dispositions", "binding_obligations",
            "included_paths", "excluded_paths", "separately_bound_paths",
            "included_set_sha256", "excluded_set_sha256", "separately_bound_set_sha256",
            "disposition_set_sha256", "enumeration_universe_sha256", "binding_obligation_set_sha256",
            "include_registry_blob", "exclusion_registry_blob", "selection_rule_registry_blob", "boundary_configuration_blob",
        ),
        "terminal result",
    )
    sets = validate_terminal_dispositions(result["enumeration_universe"], result["terminal_dispositions"], result["binding_obligations"])
    for disposition, field, hash_field in (
        ("INCLUDE", "included_paths", "included_set_sha256"),
        ("EXCLUDE", "excluded_paths", "excluded_set_sha256"),
        ("SEPARATE_AND_BIND", "separately_bound_paths", "separately_bound_set_sha256"),
    ):
        require(result[field] == sets[disposition], "TERMINAL_DECLARED_SET", field)
        require(result[hash_field] == semantic_identity(sets[disposition]), "TERMINAL_SET_ROOT", hash_field)
    require(result["disposition_set_sha256"] == semantic_identity(result["terminal_dispositions"]), "DISPOSITION_SET_ROOT", "terminal dispositions")
    require(result["enumeration_universe_sha256"] == semantic_identity(result["enumeration_universe"]), "ENUMERATION_UNIVERSE_ROOT", "universe")
    require(result["binding_obligation_set_sha256"] == semantic_identity(result["binding_obligations"]), "BINDING_OBLIGATION_ROOT", "obligations")
    for record in result["terminal_dispositions"]:
        require(record["rule_registry_blob"] == result["selection_rule_registry_blob"], "DISPOSITION_RULE_BLOB", record["artifact_key"])
    return sets


def validate_terminal_against_authority(
    result: Mapping[str, Any],
    independently_enumerated_universe: Sequence[str],
    registry_bindings: Mapping[str, str],
) -> dict[str, list[str]]:
    sets = validate_terminal_result(result)
    expected_universe = sorted(independently_enumerated_universe, key=lambda item: item.encode("utf-8"))
    require(result["enumeration_universe"] == expected_universe, "DISPOSITION_INDEPENDENT_UNIVERSE", "inventory")
    for field in ("include_registry_blob", "exclusion_registry_blob", "selection_rule_registry_blob", "boundary_configuration_blob"):
        require(result[field] == registry_bindings[field], "DISPOSITION_REGISTRY_AUTHORITY", field)
    return sets


FULL_INVENTORY_IDENTITY_FIELDS = (
    "canonical_path",
    "path_sha256",
    "raw_byte_size",
    "raw_sha256",
    "first_raw_byte_size",
    "first_raw_sha256",
    "second_raw_byte_size",
    "second_raw_sha256",
    "pre_read_identity",
    "post_read_identity",
    "file_mode",
    "filesystem_attributes",
    "git_status",
    "parent_git_blob",
    "parent_git_mode",
    "index_git_blob",
    "index_git_mode",
    "working_tree_git_cleaned_sha256",
    "working_tree_git_cleaned_size",
    "computed_git_blob",
    "repository_object_format",
    "line_ending_profile",
    "encoding_profile",
    "gitattributes_sha256",
    "gitattributes_git_blob",
    "gitattributes_computed_git_blob",
    "git_attribute_results",
    "effective_clean_filter_identity",
    "symlink",
    "reparse_point",
    "external_root_id",
    "existence_state",
    "rename_destination",
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
        if record.get("existence_state") == "TOMBSTONE":
            require(record.get("raw_sha256") is None and record.get("raw_byte_size") is None, "TOMBSTONE_HAS_RAW_BYTES", path)
            require(record.get("parent_git_blob") is not None or record.get("index_git_blob") is not None, "UNBOUND_TOMBSTONE", path)
            continue
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
    require(sum(item["raw_byte_size"] or 0 for item in artifacts) == manifest["total_bytes"], "MANIFEST_BYTES", repr(manifest["total_bytes"]))
    require(manifest["artifact_path_set_sha256"] == semantic_identity(paths), "MANIFEST_PATH_SET", "path set")
    require(manifest["artifact_set_semantic_sha256"] == semantic_identity(artifacts), "MANIFEST_ARTIFACT_ROOT", "artifact set")
    semantic = {key: value for key, value in manifest.items() if key != "manifest_semantic_sha256"}
    require(manifest["manifest_semantic_sha256"] == semantic_identity(semantic), "MANIFEST_SEMANTIC_ROOT", "manifest")
    for item in artifacts:
        _require_fields(item, FULL_INVENTORY_IDENTITY_FIELDS, item.get("canonical_path", "artifact"))
        if item.get("existence_state") == "TOMBSTONE":
            require(item["raw_sha256"] is None and item["raw_byte_size"] is None, "MANIFEST_TOMBSTONE_RAW", item["canonical_path"])
        else:
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
    "package_role_map_blob",
    "package_role_map_sha256",
    "authority_universe_blob",
    "authority_universe_sha256",
    "package_authority_sha256",
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
    "execution_environment_identity",
    "repository_object_format",
    "timestamp_authority",
    "authorization_identity",
    "freeze_receipt_schema_sha256",
    "required_evidence_set_sha256",
    "attempt_ledger_root_sha256",
    "attempt_authority_anchor_sha256",
)


def build_freeze_receipt(attempt_id: str, timestamp: str, current: Mapping[str, Any]) -> dict[str, Any]:
    _require_fields(current, FREEZE_IDENTITY_FIELDS, "derived freeze state")
    receipt = {
        "schema_version": "3.0.0-DRAFT",
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


FREEZE_V4_FIELDS = (
    "accepted_specification_identity",
    "specification_commit",
    "specification_parent",
    "specification_tree",
    "specification_document_blob",
    "schema_set_identity",
    "include_registry_blob",
    "exclusion_registry_blob",
    "selection_rule_registry_blob",
    "boundary_configuration_blob",
    "selection_engine_blob",
    "inventory_generator_blob",
    "boundary_verifier_blob",
    "authorization_state_blob",
    "evidence_policy_blob",
    "attempt_prefix_authority_blob",
    "package_git_object_identity",
    "evidence_policy_identity",
    "attempt_prefix_authority_identity",
    "attempt_ledger_root",
    "operational_package_identity",
    "operational_capture_script_blob",
    "generated_inventory_sha256",
    "generated_disposition_sha256",
    "included_set_sha256",
    "excluded_set_sha256",
    "separately_bound_set_sha256",
    "artifact_count",
    "total_bytes",
    "repository_head",
    "repository_parent",
    "repository_branch_or_detached",
    "index_sha256",
    "repository_status_sha256",
    "gitattributes_sha256",
    "repository_object_format",
    "environment_identity",
    "attempt_id",
    "timestamp_authority",
    "authorization_identity",
)


def validate_attempt_prefix_authority_v4(prefix: Mapping[str, Any]) -> None:
    _require_fields(prefix, ("authority", "authority_id", "preserved_attempt_ids", "preserved_entry_count", "genesis_entry_hash_sha256", "preserved_ledger_root_sha256"), "attempt prefix authority")
    require(prefix["authority"] == "DRAFT_IMMUTABLE_GENESIS_PREFIX_PENDING_INDEPENDENT_REVIEW", "ATTEMPT_PREFIX_AUTHORITY", str(prefix["authority"]))
    require(prefix["preserved_entry_count"] == len(prefix["preserved_attempt_ids"]), "ATTEMPT_PREFIX_COUNT", "authority")
    require(len(prefix["preserved_attempt_ids"]) == len(set(prefix["preserved_attempt_ids"])), "ATTEMPT_PREFIX_DUPLICATE", "authority")
    for field in ("genesis_entry_hash_sha256", "preserved_ledger_root_sha256"):
        require(re.fullmatch(r"[0-9A-F]{64}", prefix[field] or "") is not None, "ATTEMPT_PREFIX_HASH", field)


def reconstruct_freeze_authority_v4(
    repository: Path,
    accepted_specification_authority: Mapping[str, Any],
    operational_repository: Path,
    operational_package_claim: Mapping[str, Any],
    *,
    attempt_id: str,
    timestamp_authority: str,
) -> dict[str, Any]:
    """Reconstruct every freeze claim from repositories and committed authorities."""
    accepted = validate_accepted_specification_authority(repository, accepted_specification_authority)
    accepted_specification_commit = accepted["commit"]
    package = derive_committed_package_authority(repository, accepted_specification_commit)
    validate_package_checkout(package)
    by_role = {entry["role"]: entry for entry in package["entries"]}
    selection = derive_selection_from_accepted_specification(repository, accepted)
    evidence_policy = _load_committed_json(repository, package["commit"], by_role["required_evidence_policy"]["canonical_path"])
    prefix = _load_committed_json(repository, package["commit"], by_role["attempt_prefix_authority"]["canonical_path"])
    authorization = _load_committed_json(repository, package["commit"], by_role["authorization_state"]["canonical_path"])
    validate_required_evidence_policy(evidence_policy)
    validate_attempt_prefix_authority_v4(prefix)
    validate_authorization_state(authorization)
    operational_core = validate_operational_package_authority(
        operational_repository,
        accepted,
        operational_package_claim,
        {
            "accepted_specification_identity": accepted["accepted_specification_identity"],
            "operational_package_identity": operational_package_claim["freeze_package_identity"],
        },
    )
    head = str(_git(repository, "rev-parse", "HEAD")).strip().lower()
    parent = str(_git(repository, "rev-parse", "HEAD^")).strip().lower()
    branch_process = subprocess.run(
        ["git", "-c", "core.longpaths=true", "-c", f"safe.directory={repository.as_posix()}", "-C", os.fspath(repository), "symbolic-ref", "-q", "--short", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    branch = branch_process.stdout.strip() if branch_process.returncode == 0 else "DETACHED"
    status = _git(repository, "status", "--porcelain=v2", "-z", "--branch", "--untracked-files=all", text=False)
    index_listing = _git(repository, "ls-files", "-s", "-z", text=False)
    environment = _environment_identity(repository, load_committed_authority_universe(repository, package["commit"]), package)
    script_blob = operational_core.get("script_blob") or operational_core.get("script_content_address")
    reconstructed = {
        "accepted_specification_identity": accepted["accepted_specification_identity"],
        "specification_commit": package["commit"],
        "specification_parent": package["parent"],
        "specification_tree": package["tree"],
        "specification_document_blob": by_role["specification_document"]["git_blob"],
        "schema_set_identity": accepted["schema_set_identity"],
        "include_registry_blob": by_role["include_registry"]["git_blob"],
        "exclusion_registry_blob": by_role["exclusion_registry"]["git_blob"],
        "selection_rule_registry_blob": by_role["selection_rule_registry"]["git_blob"],
        "boundary_configuration_blob": by_role["boundary_configuration"]["git_blob"],
        "selection_engine_blob": by_role["selection_engine"]["git_blob"],
        "inventory_generator_blob": by_role["inventory_generator"]["git_blob"],
        "boundary_verifier_blob": by_role["boundary_verifier"]["git_blob"],
        "authorization_state_blob": by_role["authorization_state"]["git_blob"],
        "evidence_policy_blob": by_role["required_evidence_policy"]["git_blob"],
        "attempt_prefix_authority_blob": by_role["attempt_prefix_authority"]["git_blob"],
        "package_git_object_identity": package["authority_sha256"],
        "evidence_policy_identity": semantic_identity(evidence_policy),
        "attempt_prefix_authority_identity": semantic_identity(prefix),
        "attempt_ledger_root": prefix["preserved_ledger_root_sha256"],
        "operational_package_identity": operational_core["operational_package_identity"],
        "operational_capture_script_blob": script_blob,
        "generated_inventory_sha256": selection["inventory"]["inventory_sha256"],
        "generated_disposition_sha256": selection["disposition_set_sha256"],
        "included_set_sha256": selection["included_set_sha256"],
        "excluded_set_sha256": selection["excluded_set_sha256"],
        "separately_bound_set_sha256": selection["separately_bound_set_sha256"],
        "artifact_count": selection["inventory"]["total_artifact_count"],
        "total_bytes": selection["inventory"]["total_bytes"],
        "repository_head": head,
        "repository_parent": parent,
        "repository_branch_or_detached": branch,
        "index_sha256": sha256_bytes(index_listing),
        "repository_status_sha256": sha256_bytes(status),
        "gitattributes_sha256": by_role["package_line_ending_authority"]["raw_sha256"],
        "repository_object_format": package["object_format"],
        "environment_identity": semantic_identity(environment),
        "attempt_id": attempt_id,
        "timestamp_authority": timestamp_authority,
        "authorization_identity": semantic_identity(authorization),
    }
    return reconstructed


def verify_freeze_claim_v4(
    receipt: Mapping[str, Any], repository: Path, accepted_specification_authority: Mapping[str, Any],
    operational_repository: Path, operational_package_claim: Mapping[str, Any],
) -> None:
    reconstructed = reconstruct_freeze_authority_v4(
        repository, accepted_specification_authority, operational_repository, operational_package_claim,
        attempt_id=receipt.get("attempt_id", ""), timestamp_authority=receipt.get("timestamp_authority", ""),
    )
    validate_freeze_v4(receipt, reconstructed)


def validate_freeze_v4(receipt: Mapping[str, Any], independently_reconstructed: Mapping[str, Any]) -> None:
    _require_fields(receipt, (*FREEZE_V4_FIELDS, "freeze_receipt_sha256"), "freeze v4 receipt")
    _require_fields(independently_reconstructed, FREEZE_V4_FIELDS, "independently reconstructed freeze v4")
    object_format = receipt["repository_object_format"]
    require(object_format in {"sha1", "sha256"}, "UNSUPPORTED_GIT_OBJECT_FORMAT", str(object_format))
    for field in ("specification_commit", "specification_parent", "specification_tree", "repository_head"):
        validate_git_object(receipt[field], object_format, f"freeze:{field}")
    for field in FREEZE_V4_FIELDS:
        require(receipt[field] == independently_reconstructed[field], "FREEZE_MISMATCH", field)
    semantic = {key: value for key, value in receipt.items() if key != "freeze_receipt_sha256"}
    require(receipt["freeze_receipt_sha256"] == semantic_identity(semantic), "FREEZE_RECEIPT_HASH", "v4")


def _schema_authority_pointers(value: Any, pointer: str = "") -> set[str]:
    result: set[str] = set()
    if isinstance(value, Mapping):
        properties = value.get("properties")
        if isinstance(properties, Mapping):
            for name, child in properties.items():
                child_pointer = f"{pointer}/properties/{name.replace('~', '~0').replace('/', '~1')}"
                result.add(child_pointer)
                result |= _schema_authority_pointers(child, child_pointer)
        definitions = value.get("$defs")
        if isinstance(definitions, Mapping):
            for name, child in definitions.items():
                result |= _schema_authority_pointers(child, f"{pointer}/$defs/{name}")
        for keyword in ("if", "then", "else", "not", "dependentSchemas"):
            if keyword in value and isinstance(value[keyword], Mapping):
                conditional_pointer = f"{pointer}/{keyword}"
                result.add(conditional_pointer)
                result |= _schema_authority_pointers(value[keyword], conditional_pointer)
        for keyword in ("allOf", "anyOf", "oneOf"):
            if isinstance(value.get(keyword), list):
                for index, child in enumerate(value[keyword]):
                    conditional_pointer = f"{pointer}/{keyword}/{index}"
                    result.add(conditional_pointer)
                    result |= _schema_authority_pointers(child, conditional_pointer)
    return result


def _source_functions(package_root: Path, source_file: str) -> set[str]:
    source = package_root / source_file
    tree = ast.parse(read_bytes_long(source).decode("utf-8"), filename=os.fspath(source))
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def validate_traceability_v4(
    matrix: Mapping[str, Any],
    package_root: Path,
    expectations: Mapping[str, Any],
    selection_rule_registry: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]] | None = None,
) -> None:
    _require_fields(matrix, ("authority", "rows", "schema_field_mappings", "rule_mappings", "function_mappings"), "semantic traceability v4")
    require(matrix["authority"] == "DRAFT_FIELD_FUNCTION_TRACEABILITY_PENDING_INDEPENDENT_REVIEW", "TRACE_AUTHORITY", str(matrix["authority"]))
    expectation_by_id = {item["case_id"]: item for item in expectations["cases"]}
    require(len(expectation_by_id) == len(expectations["cases"]), "TRACE_EXPECTATION_DUPLICATE", "cases")
    observed_by_id = {item["case_id"]: item for item in observations or []}
    require(not observations or set(observed_by_id) == set(expectation_by_id), "TRACE_OBSERVATION_SET", "fresh cases")
    seen_fields: set[str] = set()
    seen_functions: set[tuple[str, str]] = set()
    seen_cases: set[str] = set()
    require({row["requirement"] for row in matrix["rows"]} == {f"R2-{index:02d}" for index in range(1, 17)}, "TRACE_REQUIREMENT_SET", "R2-01..R2-16")
    for row in matrix["rows"]:
        _require_fields(row, ("requirement","normative_clause","schema_file","schema_pointer","rule_id","source_file","symbol","positive_case","mutation_case","expected_code","future_operational_obligation"), "trace row")
        schema = strict_json_loads(read_bytes_long(package_root / row["schema_file"]))
        pointer: Any = schema
        for token in [part.replace("~1", "/").replace("~0", "~") for part in row["schema_pointer"].split("/")[1:] if part]:
            require(isinstance(pointer, Mapping) and token in pointer, "TRACE_SCHEMA_POINTER", f"{row['schema_file']}#{row['schema_pointer']}")
            pointer = pointer[token]
        functions = _source_functions(package_root, row["source_file"])
        require(row["symbol"] in functions, "TRACE_FUNCTION", f"{row['source_file']}:{row['symbol']}")
        for case_id in (row["positive_case"], row["mutation_case"]):
            require(case_id in expectation_by_id, "TRACE_CASE", case_id)
            seen_cases.add(case_id)
        require(expectation_by_id[row["mutation_case"]]["expected_code"] == row["expected_code"], "TRACE_EXPECTED_CODE", row["mutation_case"])
        require(expectation_by_id[row["mutation_case"]]["expected_enforcing_surface"].endswith("." + row["symbol"]), "TRACE_ENFORCING_SURFACE", row["mutation_case"])
        if observations:
            observed = observed_by_id[row["mutation_case"]]
            require(observed["observed_code"] == row["expected_code"], "TRACE_OBSERVED_CODE", row["mutation_case"])
            require(observed["observed_enforcing_surface"] == expectation_by_id[row["mutation_case"]]["expected_enforcing_surface"], "TRACE_OBSERVED_SURFACE", row["mutation_case"])
        seen_fields.add(f"{row['schema_file']}#{row['schema_pointer']}")
        seen_functions.add((row["source_file"], row["symbol"]))
    governed_rules = {item["rule_id"] for item in selection_rule_registry["rules"]}
    traced_rules = {item["rule_id"] for item in matrix["rule_mappings"]}
    require(traced_rules == governed_rules, "TRACE_RULE_SET", repr(sorted(traced_rules ^ governed_rules)))
    for item in matrix["rule_mappings"]:
        require(item["case_id"] in expectation_by_id, "TRACE_RULE_CASE", item["rule_id"])
        require(item["symbol"] in _source_functions(package_root, item["source_file"]), "TRACE_RULE_FUNCTION", item["rule_id"])
    declared_fields: set[str] = set()
    for schema_path in sorted(package_root.glob("*_schema_DRAFT.json")):
        schema = strict_json_loads(read_bytes_long(schema_path))
        declared_fields |= {f"{schema_path.name}#{pointer}" for pointer in _schema_authority_pointers(schema)}
    mapped_fields = {f"{item['schema_file']}#{item['schema_pointer']}" for item in matrix["schema_field_mappings"]}
    require(mapped_fields == declared_fields, "TRACE_SCHEMA_FIELD_SET", repr(sorted(mapped_fields ^ declared_fields)[:20]))
    row_requirements = {row["requirement"] for row in matrix["rows"]}
    require(all(item["normative_requirement"] in row_requirements for item in matrix["schema_field_mappings"]), "TRACE_SCHEMA_FIELD_AUTHORITY", "mapping")
    expected_surfaces = {item["expected_enforcing_surface"] for item in expectations["cases"]}
    mapped_surfaces: set[str] = set()
    for item in matrix["function_mappings"]:
        require(item["symbol"] in _source_functions(package_root, item["source_file"]), "TRACE_FUNCTION", f"{item['source_file']}:{item['symbol']}")
        surface = Path(item["source_file"]).stem + "." + item["symbol"]
        mapped_surfaces.add(surface)
        require(item["invoked_case_ids"], "TRACE_FUNCTION_NOT_INVOKED", surface)
        for case_id in item["invoked_case_ids"]:
            require(case_id in expectation_by_id, "TRACE_FUNCTION_CASE", case_id)
            require(expectation_by_id[case_id]["expected_enforcing_surface"] == surface, "TRACE_FUNCTION_CASE_SURFACE", case_id)
            if observations:
                require(observed_by_id[case_id]["observed_enforcing_surface"] == surface, "TRACE_FUNCTION_NOT_OBSERVED", case_id)
    require(mapped_surfaces == expected_surfaces, "TRACE_FUNCTION_SURFACE_SET", repr(sorted(mapped_surfaces ^ expected_surfaces)))
    require(seen_fields and seen_functions and seen_cases, "IDENTIFIER_ONLY_TRACEABILITY", "semantic coverage empty")


def validate_test_classification(record: Mapping[str, Any], broad_log_bytes: bytes) -> None:
    """Reparse the immutable real log and compare the complete derived record."""
    try:
        from historical_log_parser_DRAFT import HistoricalLogError, validate_historical_record

        validate_historical_record(record, broad_log_bytes, str(record.get("full_log_path", "")))
    except HistoricalLogError as exc:
        raise BoundaryError(exc.code, exc.detail) from exc


ATTEMPT_DISPOSITIONS = {"NO_ARTIFACT", "PRE_PASS_A_STOP", "UNSTABLE", "ABORTED", "REJECTED", "SUCCESSFUL", "SUPERSEDED", "REVIEWED"}
PASS_STATES = {"NOT_STARTED", "RUNNING", "COMPLETED", "MISMATCH", "FAILED"}
STAGING_STATES = {"NONE", "PREPARED", "STAGED", "COMMITTED", "ABORTED"}


def attempt_identity(record: Mapping[str, Any]) -> str:
    return semantic_identity({key: value for key, value in record.items() if key != "attempt_identity_sha256"})


def ledger_root(attempts: Sequence[Mapping[str, Any]]) -> str:
    return semantic_identity([record["attempt_identity_sha256"] for record in attempts])


def attempt_authority_identity(anchor: Mapping[str, Any]) -> str:
    return semantic_identity({key: value for key, value in anchor.items() if key != "authorization_sha256"})


def validate_attempt_ledger(
    ledger: Mapping[str, Any],
    authority_anchor: Mapping[str, Any] | None = None,
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
            "authority_anchor_sha256",
            "repository_object_format",
        ),
        "attempt ledger",
    )
    attempts = ledger["attempts"]
    object_format = ledger["repository_object_format"]
    require(object_format in {"sha1", "sha256"}, "UNSUPPORTED_GIT_OBJECT_FORMAT", str(object_format))
    require(isinstance(authority_anchor, Mapping), "MISSING_ATTEMPT_AUTHORITY", "independent anchor")
    _require_fields(authority_anchor, ("authority_id", "authorized_attempt_ids", "previous_entry_count", "previous_ledger_root_sha256", "authorization_sha256"), "attempt authority anchor")
    require(authority_anchor["authorization_sha256"] == attempt_authority_identity(authority_anchor), "ATTEMPT_AUTHORITY_IDENTITY", str(authority_anchor["authority_id"]))
    require(ledger["authority_anchor_sha256"] == authority_anchor["authorization_sha256"], "ATTEMPT_AUTHORITY_ANCHOR", "ledger")
    require(ledger["entry_count"] == len(attempts), "ATTEMPT_COUNT", "ledger")
    ids = [record["attempt_id"] for record in attempts]
    require(ids == list(authority_anchor["authorized_attempt_ids"]), "FROZEN_ATTEMPT_UNIVERSE", repr(ids))
    require(ids == ledger["expected_attempt_ids"], "ATTEMPT_UNIVERSE", "ordered identifiers")
    require(ledger["expected_attempt_set_sha256"] == semantic_identity(ids), "ATTEMPT_SET_ROOT", "identifiers")
    require(len(ids) == len(set(ids)), "DUPLICATE_ATTEMPT_ID", repr(ids))
    require(authority_anchor["previous_entry_count"] <= len(ids), "ATTEMPT_AUTHORITY_COUNT", repr(authority_anchor["previous_entry_count"]))
    require(ledger["previous_ledger_root_sha256"] == authority_anchor["previous_ledger_root_sha256"], "PREVIOUS_LEDGER_AUTHORITY", "anchor")
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
        require(record["repository_identity"].get("object_format") == object_format, "ATTEMPT_OBJECT_FORMAT", attempt_id)
        validate_git_object(record["repository_identity"].get("head"), object_format, f"{attempt_id}:head")
        for commit in record["commits"]:
            validate_git_object(commit, object_format, f"{attempt_id}:commit")
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


def validate_attempt_authority(ledger: Mapping[str, Any], authority_anchor: Mapping[str, Any]) -> None:
    validate_attempt_ledger(ledger, authority_anchor)
    for record in ledger["attempts"]:
        for field in INCIDENT_FIELDS:
            require(record[field] is False, "ATTEMPT_AUTHORITY_INCIDENT", f"{record['attempt_id']}:{field}")


def attempt_entry_hash_v4(record: Mapping[str, Any]) -> str:
    excluded = {"current_entry_hash", "current_ledger_root"}
    return semantic_identity({key: value for key, value in record.items() if key not in excluded})


def chained_ledger_root_v4(previous_root: str, entry_hash: str) -> str:
    return semantic_identity({"previous_ledger_root": previous_root, "current_entry_hash": entry_hash})


def validate_attempt_ledger_v4(
    ledger: Mapping[str, Any],
    prefix_authority: Mapping[str, Any],
    prefix_binding: Mapping[str, str],
) -> None:
    _require_fields(
        prefix_authority,
        (
            "authority",
            "authority_id",
            "preserved_attempt_ids",
            "preserved_entry_count",
            "genesis_entry_hash_sha256",
            "preserved_ledger_root_sha256",
        ),
        "attempt prefix authority",
    )
    require(prefix_authority["authority"] == "DRAFT_IMMUTABLE_GENESIS_PREFIX_PENDING_INDEPENDENT_REVIEW", "ATTEMPT_PREFIX_AUTHORITY", str(prefix_authority["authority"]))
    require(prefix_authority["preserved_entry_count"] == len(prefix_authority["preserved_attempt_ids"]), "ATTEMPT_PREFIX_COUNT", "authority")
    _require_fields(prefix_binding, ("git_blob", "raw_sha256"), "attempt prefix binding")
    _require_fields(
        ledger,
        (
            "prefix_authority_blob",
            "prefix_authority_raw_sha256",
            "preserved_prefix_count",
            "full_current_count",
            "attempts",
            "current_ledger_root",
        ),
        "attempt ledger v4",
    )
    require(ledger["prefix_authority_blob"] == prefix_binding["git_blob"], "ATTEMPT_PREFIX_BLOB", "ledger")
    require(ledger["prefix_authority_raw_sha256"] == prefix_binding["raw_sha256"], "ATTEMPT_PREFIX_RAW_HASH", "ledger")
    attempts = ledger["attempts"]
    require(ledger["preserved_prefix_count"] == prefix_authority["preserved_entry_count"], "ATTEMPT_PREFIX_COUNT", "ledger")
    require(ledger["full_current_count"] == len(attempts), "ATTEMPT_COUNT", "ledger")
    ids = [item["attempt_id"] for item in attempts]
    require(len(ids) == len(set(ids)), "DUPLICATE_ATTEMPT_ID", repr(ids))
    require(ids[: ledger["preserved_prefix_count"]] == prefix_authority["preserved_attempt_ids"], "FROZEN_ATTEMPT_UNIVERSE", repr(ids))
    previous_attempt_id: str | None = None
    previous_entry_hash = prefix_authority["genesis_entry_hash_sha256"]
    previous_root = prefix_authority["genesis_entry_hash_sha256"]
    previous_end: str | None = None
    known: set[str] = set()
    for sequence, record in enumerate(attempts, 1):
        _require_fields(
            record,
            (
                "attempt_id",
                "sequence_number",
                "predecessor_attempt_id",
                "prior_entry_hash",
                "prior_ledger_root",
                "current_entry_hash",
                "current_ledger_root",
                "start_time",
                "end_time",
                "worktree",
                "branch",
                "evidence_directory",
                "pass_a_status",
                "pass_b_status",
                "staging_state",
                "commits",
                "manifest",
                "terminal_disposition",
                "relationship_to_prior_attempts",
                *INCIDENT_FIELDS,
            ),
            "attempt record v4",
        )
        require(record["sequence_number"] == sequence, "ATTEMPT_SEQUENCE", record["attempt_id"])
        require(record["predecessor_attempt_id"] == previous_attempt_id, "BROKEN_ATTEMPT_PREDECESSOR", record["attempt_id"])
        require(record["prior_entry_hash"] == previous_entry_hash, "BROKEN_PRIOR_ENTRY_HASH", record["attempt_id"])
        require(record["prior_ledger_root"] == previous_root, "BROKEN_PRIOR_LEDGER_ROOT", record["attempt_id"])
        entry_hash = attempt_entry_hash_v4(record)
        require(record["current_entry_hash"] == entry_hash, "BROKEN_ENTRY_HASH", record["attempt_id"])
        current_root = chained_ledger_root_v4(previous_root, entry_hash)
        require(record["current_ledger_root"] == current_root, "BROKEN_LEDGER_ROOT", record["attempt_id"])
        if sequence == prefix_authority["preserved_entry_count"]:
            require(current_root == prefix_authority["preserved_ledger_root_sha256"], "ATTEMPT_PRESERVED_PREFIX_ROOT", record["attempt_id"])
        require(record["start_time"] <= record["end_time"], "ATTEMPT_CHRONOLOGY", record["attempt_id"])
        if previous_end is not None:
            require(previous_end <= record["start_time"], "ATTEMPT_CROSS_CHRONOLOGY", record["attempt_id"])
        require(record["terminal_disposition"] in ATTEMPT_DISPOSITIONS, "MISSING_TERMINAL_DISPOSITION", record["attempt_id"])
        if record["terminal_disposition"] in {"NO_ARTIFACT", "PRE_PASS_A_STOP"}:
            require(record["manifest"] is None and record["commits"] == [], "CONFLICTING_ATTEMPT_CLAIM", record["attempt_id"])
        else:
            require(isinstance(record["manifest"], Mapping), "MISSING_MANIFEST_REFERENCE", record["attempt_id"])
        for related in record["relationship_to_prior_attempts"]:
            require(related in known, "NONEXISTENT_ATTEMPT_RELATIONSHIP", f"{record['attempt_id']}->{related}")
        known.add(record["attempt_id"])
        previous_attempt_id = record["attempt_id"]
        previous_entry_hash = entry_hash
        previous_root = current_root
        previous_end = record["end_time"]
    require(ledger["current_ledger_root"] == previous_root, "ATTEMPT_LEDGER_ROOT", "ledger")
    if not attempts:
        require(prefix_authority["preserved_entry_count"] == 0 and prefix_authority["preserved_ledger_root_sha256"] == prefix_authority["genesis_entry_hash_sha256"], "FROZEN_ATTEMPT_UNIVERSE", "empty ledger")


def validate_attempt_capture_authority_v4(
    ledger: Mapping[str, Any],
    prefix_authority: Mapping[str, Any],
    prefix_binding: Mapping[str, str],
) -> None:
    validate_attempt_ledger_v4(ledger, prefix_authority, prefix_binding)
    for record in ledger["attempts"]:
        for field in INCIDENT_FIELDS:
            require(record[field] is False, "ATTEMPT_AUTHORITY_INCIDENT", f"{record['attempt_id']}:{field}")


def evidence_entry_identity(entry: Mapping[str, Any]) -> str:
    return semantic_identity(entry)


def evidence_registry_root(entries: Sequence[Mapping[str, Any]]) -> str:
    return semantic_identity(entries)


def validate_evidence_bindings(
    registry: Mapping[str, Any],
    authority_universe: Mapping[str, Any] | None = None,
    *,
    attempt_ledger: Mapping[str, Any] | None = None,
    repository: Path | None = None,
    artifact_bytes: Mapping[str, bytes] | None = None,
    frozen_identity: str | None = None,
) -> None:
    authority = authority_universe or load_local_authority_universe()
    evidence_authority = authority["evidence_authority"]
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
            "authority_universe_sha256",
            "repository_object_format",
        ),
        "evidence registry",
    )
    entries = registry["entries"]
    require(registry["authority_universe_sha256"] == semantic_identity(authority), "EVIDENCE_AUTHORITY_UNIVERSE", "registry")
    require(registry["repository_object_format"] in {"sha1", "sha256"}, "UNSUPPORTED_GIT_OBJECT_FORMAT", str(registry["repository_object_format"]))
    require(isinstance(entries, list) and entries, "EMPTY_EVIDENCE_REGISTRY", "entries")
    paths = validate_path_set(entry["canonical_path"] for entry in entries)
    require(len(entries) == registry["expected_entry_count"], "EVIDENCE_COUNT", "registry")
    require(registry["expected_path_set_sha256"] == semantic_identity(paths), "EVIDENCE_PATH_SET", "registry")
    roles = sorted({entry["role"] for entry in entries})
    classes = sorted({entry["artifact_class"] for entry in entries})
    require(set(roles) == set(evidence_authority["required_roles"]), "FROZEN_EVIDENCE_ROLE_UNIVERSE", repr(sorted(set(roles) ^ set(evidence_authority["required_roles"]))))
    required_classes = evidence_authority["required_classes"]
    require(set(classes) == set(required_classes), "FROZEN_EVIDENCE_CLASS_UNIVERSE", repr(sorted(set(classes) ^ set(required_classes))))
    class_counts = Counter(entry["artifact_class"] for entry in entries)
    for class_name, constraint in required_classes.items():
        require(class_counts[class_name] >= constraint["minimum"], "FROZEN_EVIDENCE_CLASS_CARDINALITY", class_name)
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
        if attempt_ledger is not None:
            attempt_ids = {item["attempt_id"] for item in attempt_ledger["attempts"]}
            require(entry["source_attempt"] in attempt_ids, "EVIDENCE_SOURCE_ATTEMPT", entry["canonical_path"])
        if artifact_bytes is not None:
            require(entry["canonical_path"] in artifact_bytes, "EVIDENCE_SOURCE_ARTIFACT_MISSING", entry["canonical_path"])
            raw = artifact_bytes[entry["canonical_path"]]
            require(entry["byte_size"] == len(raw), "EVIDENCE_SOURCE_SIZE", entry["canonical_path"])
            require(entry["sha256"] == sha256_bytes(raw), "EVIDENCE_SOURCE_HASH", entry["canonical_path"])
        if entry["git_blob"] is not None:
            require(repository is not None, "EVIDENCE_GIT_REPOSITORY_REQUIRED", entry["canonical_path"])
            object_format = str(_git(repository, "rev-parse", "--show-object-format")).strip()
            require(object_format == registry["repository_object_format"], "EVIDENCE_OBJECT_FORMAT", entry["canonical_path"])
            validate_git_object(entry["git_blob"], object_format, entry["canonical_path"])
            blob_bytes = _git(repository, "cat-file", "blob", entry["git_blob"], text=False)
            if artifact_bytes is not None:
                require(blob_bytes == artifact_bytes[entry["canonical_path"]], "EVIDENCE_GIT_BLOB_BYTES", entry["canonical_path"])
    require(registry["semantic_root_sha256"] == evidence_registry_root(entries), "EVIDENCE_SEMANTIC_ROOT", "registry")
    semantic = {key: value for key, value in registry.items() if key != "registry_identity_sha256"}
    require(registry["registry_identity_sha256"] == semantic_identity(semantic), "EVIDENCE_REGISTRY_IDENTITY", "registry")
    if frozen_identity is not None:
        require(registry["registry_identity_sha256"] == frozen_identity, "FROZEN_EVIDENCE_REGISTRY", "registry")


def validate_required_evidence_policy(policy: Mapping[str, Any]) -> None:
    _require_fields(
        policy,
        (
            "authority",
            "policy_id",
            "required_roles",
            "required_classes",
            "conditional_rules",
            "required_source_attempt_relationships",
            "required_capture_pass_relationships",
            "required_immutability",
            "required_recovery_state",
        ),
        "required evidence policy",
    )
    require(
        policy["authority"] == "DRAFT_PREEXISTING_REQUIRED_EVIDENCE_POLICY_PENDING_INDEPENDENT_REVIEW",
        "EVIDENCE_POLICY_AUTHORITY",
        str(policy["authority"]),
    )
    require(isinstance(policy["required_roles"], Mapping) and policy["required_roles"], "EVIDENCE_POLICY_ROLES", "required_roles")
    require(isinstance(policy["required_classes"], Mapping) and policy["required_classes"], "EVIDENCE_POLICY_CLASSES", "required_classes")
    for role, constraint in policy["required_roles"].items():
        require(bool(constraint.get("semantic_purpose")), "EVIDENCE_POLICY_PURPOSE", role)
        require("exactly" in constraint or "minimum" in constraint, "EVIDENCE_POLICY_CARDINALITY", role)
    for artifact_class, constraint in policy["required_classes"].items():
        require("minimum" in constraint, "EVIDENCE_POLICY_CARDINALITY", artifact_class)


def validate_evidence_bindings_v4(
    registry: Mapping[str, Any],
    policy: Mapping[str, Any],
    policy_binding: Mapping[str, str],
    *,
    attempt_ledger: Mapping[str, Any],
    artifact_bytes: Mapping[str, bytes] | None = None,
) -> None:
    """Validate an evidence instance against independently supplied policy bytes."""
    validate_required_evidence_policy(policy)
    _require_fields(
        policy_binding,
        ("git_blob", "raw_sha256"),
        "required evidence policy binding",
    )
    _require_fields(
        registry,
        (
            "entries",
            "policy_blob",
            "policy_raw_sha256",
            "expected_entry_count",
            "expected_path_set_sha256",
            "expected_role_set",
            "expected_artifact_class_set",
            "total_bytes",
            "semantic_root_sha256",
            "registry_identity_sha256",
        ),
        "evidence registry v4",
    )
    require(registry["policy_blob"] == policy_binding["git_blob"], "EVIDENCE_POLICY_BLOB", "registry")
    require(registry["policy_raw_sha256"] == policy_binding["raw_sha256"], "EVIDENCE_POLICY_RAW_HASH", "registry")
    entries = registry["entries"]
    require(isinstance(entries, list) and entries, "EMPTY_EVIDENCE_REGISTRY", "entries")
    paths = validate_path_set(item["canonical_path"] for item in entries)
    require(len(entries) == registry["expected_entry_count"], "EVIDENCE_COUNT", "registry")
    require(registry["expected_path_set_sha256"] == semantic_identity(paths), "EVIDENCE_PATH_SET", "registry")
    roles = Counter(item["role"] for item in entries)
    classes = Counter(item["artifact_class"] for item in entries)
    expected_roles = sorted(policy["required_roles"])
    expected_classes = sorted(policy["required_classes"])
    require(registry["expected_role_set"] == expected_roles, "EVIDENCE_ROLE_SET", "policy")
    require(registry["expected_artifact_class_set"] == expected_classes, "EVIDENCE_CLASS_SET", "policy")
    require(set(roles) == set(expected_roles), "FROZEN_EVIDENCE_ROLE_UNIVERSE", repr(sorted(set(roles) ^ set(expected_roles))))
    require(set(classes) == set(expected_classes), "FROZEN_EVIDENCE_CLASS_UNIVERSE", repr(sorted(set(classes) ^ set(expected_classes))))
    for role, constraint in policy["required_roles"].items():
        if "exactly" in constraint:
            require(roles[role] == constraint["exactly"], "FROZEN_EVIDENCE_ROLE_CARDINALITY", role)
        else:
            require(roles[role] >= constraint["minimum"], "FROZEN_EVIDENCE_ROLE_CARDINALITY", role)
    for artifact_class, constraint in policy["required_classes"].items():
        require(classes[artifact_class] >= constraint["minimum"], "FROZEN_EVIDENCE_CLASS_CARDINALITY", artifact_class)
        if "maximum" in constraint:
            require(classes[artifact_class] <= constraint["maximum"], "FROZEN_EVIDENCE_CLASS_CARDINALITY", artifact_class)
    attempts = {item["attempt_id"]: item for item in attempt_ledger["attempts"]}
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
            ),
            "evidence entry v4",
        )
        require(entry["role"] in policy["required_roles"], "EVIDENCE_ROLE", entry["canonical_path"])
        requirement = policy["required_roles"][entry["role"]]
        require(isinstance(entry["authority_status"], str) and bool(entry["authority_status"].strip()), "EVIDENCE_AUTHORITY", entry["canonical_path"])
        require(entry["semantic_purpose"] == requirement["semantic_purpose"], "EVIDENCE_SEMANTIC_PURPOSE", entry["canonical_path"])
        require(entry["required_for_recovery"] is policy["required_recovery_state"], "EVIDENCE_RECOVERY_FLAG", entry["canonical_path"])
        require(entry["immutability_status"] in {"GIT_IMMUTABLE", "CONTENT_ADDRESSED_EXTERNAL"}, "EVIDENCE_IMMUTABILITY", entry["canonical_path"])
        require(entry["source_attempt"] in attempts, "EVIDENCE_SOURCE_ATTEMPT", entry["canonical_path"])
        require(entry["capture_pass"] in {"HISTORICAL", "PRE_PASS_A", "PASS_A", "PASS_B", "FINAL"}, "EVIDENCE_CAPTURE_PASS", entry["canonical_path"])
        require(isinstance(entry["byte_size"], int) and entry["byte_size"] >= 0, "EVIDENCE_SIZE", entry["canonical_path"])
        require(re.fullmatch(r"[0-9A-F]{64}", entry["sha256"] or "") is not None, "EVIDENCE_HASH", entry["canonical_path"])
        if artifact_bytes is not None:
            require(entry["canonical_path"] in artifact_bytes, "EVIDENCE_SOURCE_ARTIFACT_MISSING", entry["canonical_path"])
            payload = artifact_bytes[entry["canonical_path"]]
            require(entry["byte_size"] == len(payload), "EVIDENCE_SOURCE_SIZE", entry["canonical_path"])
            require(entry["sha256"] == sha256_bytes(payload), "EVIDENCE_SOURCE_HASH", entry["canonical_path"])
    require(registry["total_bytes"] == sum(item["byte_size"] for item in entries), "EVIDENCE_TOTAL_BYTES", "registry")
    require(registry["semantic_root_sha256"] == evidence_registry_root(entries), "EVIDENCE_SEMANTIC_ROOT", "registry")
    semantic = {key: value for key, value in registry.items() if key != "registry_identity_sha256"}
    require(registry["registry_identity_sha256"] == semantic_identity(semantic), "EVIDENCE_REGISTRY_IDENTITY", "registry")


STABILITY_FIELDS = (
    "repository_object_format",
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
    "operating_system_identity",
    "python_version",
    "git_version",
    "filesystem_type",
    "volume_identity",
    "root_directory_identity",
    "locale",
    "timezone",
    "working_directory",
    "execution_environment_sha256",
    "git_behavior_configuration_sha256",
    "parser_versions_sha256",
    "dependency_versions_sha256",
    "executable_identities_sha256",
    "package_role_map_identity",
    "schema_set_identity",
    "verifier_identity",
)


def validate_multi_pass(pass_a: Mapping[str, Any], pass_b: Mapping[str, Any], final: Mapping[str, Any]) -> None:
    authority_environment = set(load_local_authority_universe()["environment_identity_fields"])
    require(authority_environment <= set(STABILITY_FIELDS), "STABILITY_ENVIRONMENT_UNIVERSE", repr(sorted(authority_environment - set(STABILITY_FIELDS))))
    for state_name, state in (("PASS_A", pass_a), ("PASS_B", pass_b), ("FINAL", final)):
        _require_fields(state, STABILITY_FIELDS, state_name)
        object_format = state.get("repository_object_format", "sha1")
        validate_git_object(state["repository_head"], object_format, f"{state_name}:repository_head")
        validate_git_object(state["repository_parent"], object_format, f"{state_name}:repository_parent")
        validate_git_object(state["specification_commit"], object_format, f"{state_name}:specification_commit")
        require(state["writer_count"] == 0, "ACTIVE_WRITER", state_name)
        require(state["runtime_operation_count"] == 0, "RUNTIME_OPERATION", state_name)
        require(state["deployment_attempt_count"] == 0, "DEPLOYMENT_ATTEMPT", state_name)
        require(state["service_restart_attempt_count"] == 0, "SERVICE_RESTART_ATTEMPT", state_name)
    for field in STABILITY_FIELDS:
        require(pass_a[field] == pass_b[field] == final[field], "MULTIPASS_MISMATCH", field)


def _observe_event_source(path: Path, genesis_root: str) -> dict[str, Any]:
    raw = read_bytes_long(path) if path.is_file() else b""
    previous = genesis_root
    counts: Counter[str] = Counter()
    records: list[Mapping[str, Any]] = []
    for number, line in enumerate(raw.splitlines(), 1):
        if not line:
            continue
        record = strict_json_loads(line)
        require(isinstance(record, Mapping), "OBSERVER_EVENT_RECORD", str(number))
        _require_fields(record, ("sequence", "event_type", "timestamp", "previous_root", "current_root"), "observer event")
        require(record["sequence"] == len(records) + 1, "OBSERVER_EVENT_SEQUENCE", str(number))
        require(record["previous_root"] == previous, "OBSERVER_EVENT_PREDECESSOR", str(number))
        semantic = {key: value for key, value in record.items() if key != "current_root"}
        current = semantic_identity(semantic)
        require(record["current_root"] == current, "OBSERVER_EVENT_ROOT", str(number))
        require(record["event_type"] in {"WRITER", "RUNTIME_OPERATION", "DEPLOYMENT_ATTEMPT", "SERVICE_RESTART_ATTEMPT"}, "OBSERVER_EVENT_TYPE", str(record["event_type"]))
        counts[record["event_type"]] += 1
        previous = current
        records.append(record)
    return {"raw_sha256": sha256_bytes(raw), "root": previous, "count": len(records), "counts": counts}


def observe_controlled_repository_state(repository: Path, observer_event_path: Path) -> dict[str, Any]:
    """Directly observe a disposable Git repository and bound append-only events."""
    from inventory_generator_DRAFT import enumerate_inventory

    head = str(_git(repository, "rev-parse", "HEAD")).strip().lower()
    parent = str(_git(repository, "rev-parse", "HEAD^")).strip().lower()
    object_format = str(_git(repository, "rev-parse", "--show-object-format")).strip()
    validate_git_object(head, object_format, "observer:head")
    validate_git_object(parent, object_format, "observer:parent")
    config_raw = _git(repository, "show", f"{head}:.randle_observer_config.json", text=False)
    config = verify_stored_canonical_json(config_raw)
    require(isinstance(config, Mapping), "OBSERVER_CONFIG", "object")
    _require_fields(config, ("roles", "observer_genesis_root", "specification_path"), "observer config")
    branch_result = subprocess.run(
        ["git", "-c", "core.longpaths=true", "-c", f"safe.directory={repository.as_posix()}", "-C", os.fspath(repository), "symbolic-ref", "-q", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "DETACHED"
    index_path = Path(str(_git(repository, "rev-parse", "--git-path", "index")).strip())
    if not index_path.is_absolute():
        index_path = repository / index_path
    status = _git(repository, "status", "--porcelain=v2", "-z", "--branch", "--untracked-files=all", text=False)
    inventory = enumerate_inventory(repository)
    artifacts = inventory["artifacts"]
    roles: dict[str, dict[str, str]] = {}
    for role, path in config["roles"].items():
        canonical = canonical_repository_path(path)
        blob = str(_git(repository, "rev-parse", f"{head}:{canonical}")).strip().lower()
        validate_git_object(blob, object_format, f"observer role:{role}")
        payload = _git(repository, "show", f"{head}:{canonical}", text=False)
        roles[role] = {"blob": blob, "sha256": sha256_bytes(payload)}
    specification_path = canonical_repository_path(config["specification_path"])
    specification_blob = str(_git(repository, "rev-parse", f"{head}:{specification_path}")).strip().lower()
    events = _observe_event_source(observer_event_path, config["observer_genesis_root"])
    attributes = repository / ".gitattributes"
    attribute_bytes = read_bytes_long(attributes) if attributes.is_file() else b""
    raw_identity = semantic_identity([{"path": item["canonical_path"], "raw": item["raw_sha256"]} for item in artifacts])
    clean_identity = semantic_identity([{"path": item["canonical_path"], "clean": item["working_tree_git_cleaned_sha256"]} for item in artifacts])
    path_identity = semantic_identity([item["canonical_path"] for item in artifacts])
    role_identity = lambda name: roles.get(name, {"blob": "ABSENT"})["blob"]
    state = {
        "repository_object_format": object_format,
        "repository_branch_or_detached": branch,
        "repository_head": head,
        "repository_parent": parent,
        "index_sha256": sha256_bytes(read_bytes_long(index_path)),
        "repository_status_sha256": sha256_bytes(status),
        "specification_commit": head,
        "specification_tree": str(_git(repository, "rev-parse", f"{head}^{{tree}}")).strip().lower(),
        "specification_document_blob": specification_blob,
        "include_registry_identity": role_identity("include_registry"),
        "exclusion_registry_identity": role_identity("exclusion_registry"),
        "selection_rule_registry_identity": role_identity("selection_rule_registry"),
        "configuration_identity": role_identity("boundary_configuration"),
        "selection_engine_identity": role_identity("selection_engine"),
        "inventory_generator_identity": role_identity("inventory_generator"),
        "boundary_verifier_identity": role_identity("boundary_verifier"),
        "operational_capture_script_identity": role_identity("operational_capture_script"),
        "generated_inventory_identity": inventory["inventory_sha256"],
        "included_set_identity": role_identity("include_set"),
        "excluded_set_identity": role_identity("exclude_set"),
        "separately_bound_set_identity": role_identity("separate_set"),
        "raw_byte_identity": raw_identity,
        "git_cleaned_identity": clean_identity,
        "file_mode_identity": semantic_identity([{"path": item["canonical_path"], "mode": item["file_mode"]} for item in artifacts]),
        "path_identity": path_identity,
        "artifact_count": inventory["total_artifact_count"],
        "total_bytes": inventory["total_bytes"],
        "external_evidence_identity": role_identity("external_evidence"),
        "required_evidence_set_identity": role_identity("required_evidence"),
        "attempt_ledger_root_identity": role_identity("attempt_ledger"),
        "freeze_receipt_identity": role_identity("freeze_receipt"),
        "gitattributes_identity": sha256_bytes(attribute_bytes),
        "writer_count": events["counts"]["WRITER"],
        "runtime_operation_count": events["counts"]["RUNTIME_OPERATION"],
        "deployment_attempt_count": events["counts"]["DEPLOYMENT_ATTEMPT"],
        "service_restart_attempt_count": events["counts"]["SERVICE_RESTART_ATTEMPT"],
        "operating_system_identity": platform.platform(),
        "python_version": platform.python_version(),
        "git_version": str(_git(repository, "--version")).strip(),
        "filesystem_type": _filesystem_identity(repository)["filesystem_type"],
        "volume_identity": _filesystem_identity(repository)["volume_identity"],
        "root_directory_identity": _filesystem_identity(repository)["root_directory_identity"],
        "locale": locale.setlocale(locale.LC_ALL, None),
        "timezone": list(time.tzname),
        "working_directory": os.path.abspath(os.fspath(repository)),
        "execution_environment_sha256": semantic_identity({"observer_event_sha256": events["raw_sha256"], "observer_event_root": events["root"]}),
        "git_behavior_configuration_sha256": sha256_bytes(str(_git(repository, "config", "--show-origin", "--list")).encode("utf-8")),
        "parser_versions_sha256": semantic_identity(config.get("parser_versions", {})),
        "dependency_versions_sha256": semantic_identity(config.get("dependency_versions", {})),
        "executable_identities_sha256": semantic_identity({"python": sys.executable, "git": shutil.which("git")}),
        "package_role_map_identity": semantic_identity(config["roles"]),
        "schema_set_identity": role_identity("schema_set"),
        "verifier_identity": role_identity("boundary_verifier"),
    }
    return state


AUTHORIZATION_TARGET_PATTERNS = {
    "baseline capture": r"(?:baseline|production disk)[ -]capture|\bcapture\b",
    "operational capture-script work": r"operational capture[- ]script(?: work| authoring| creation)?",
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
    r"\b(?:is|are)\s+(?:now\s+)?authorized\b",
    r"\bauthorization\s*[:=]\s*(?:true|approved|authorized|granted)\b",
    r"\bmay now\b",
    r"\bmay\s+(?:begin|deploy|merge|trade|proceed|restart|migrate|complete)\b",
    r"\bmay proceed\b",
    r"\bproceed with\b",
    r"\bcan now\b",
    r"\bready for\b",
    r"\bpermission (?:is )?granted\b",
    r"\bapproved for\b",
    r"\bis approved\b",
    r"\b(?:is|are) permitted\b",
    r"\bapproved\b",
    r"\bcan (?:start|begin|proceed|deploy|merge|trade|restart|migrate|complete)\b",
    r"\bonce (?:this|it) passes\b",
    r"\bis complete\b",
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
    r"\bnor\b[^.\n]{0,120}\bauthoriz",
)

AUTHORITY_FIELD_TARGETS = {
    "approval_status": "ambiguous protected authority",
    "authorization_status": "ambiguous protected authority",
    "deployment_authorized": "deployment",
    "capture_authorized": "baseline capture",
    "operational_capture_script_work_authorized": "operational capture-script work",
    "merge_authorized": "merge",
    "implementation_authorized": "implementation",
    "trading_authorized": "live-money trading",
    "automated_paper_trading_authorized": "automated paper trading",
    "live_money_trading_authorized": "live-money trading",
    "bucket_completion_authorized": "Bucket 0",
    "bucket_0_complete": "Bucket 0",
    "bucket_1_authorized": "Bucket 1",
    "phase_3c2_authorized": "Phase 3C2",
    "nq_cutover_authorized": "NQ cutover",
}

PROTECTED_AUTHORIZATION_DOMAINS = (
    "baseline_capture",
    "operational_capture_script_work",
    "merge",
    "canonical_incorporation",
    "production_implementation",
    "deployment",
    "service_restart",
    "runtime_migration",
    "nq_cutover",
    "automated_paper_trading",
    "live_money_trading",
    "phase_3c2",
    "phase_3c1_r11_acceptance",
    "bucket_0_completion",
    "bucket_1_work",
)
WITHHELD_AUTHORIZATION_STATES = {"WITHHELD", "NOT_AUTHORIZED", "PENDING_INDEPENDENT_REVIEW"}


def validate_authorization_state(state: Mapping[str, Any]) -> None:
    _require_fields(state, ("schema_version", "authority", "protected_domains"), "authorization state")
    domains = state["protected_domains"]
    require(isinstance(domains, Mapping), "AUTHORIZATION_STATE_TYPE", "protected_domains")
    require(set(domains) == set(PROTECTED_AUTHORIZATION_DOMAINS), "AUTHORIZATION_DOMAIN_SET", repr(sorted(set(domains) ^ set(PROTECTED_AUTHORIZATION_DOMAINS))))
    for domain, value in domains.items():
        require(value in WITHHELD_AUTHORIZATION_STATES, "POSITIVE_AUTHORIZATION_STATE", f"{domain}:{value}")
    require(state["authority"] == "DRAFT_WITHHOLDING_AUTHORITY_PENDING_INDEPENDENT_REVIEW", "AUTHORIZATION_STATE_AUTHORITY", str(state["authority"]))


def _authorization_text_leaks(path: str, text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    if re.search(r"\bnot\s+(?:un|non)[- ]?authoriz", normalized):
        return [f"{path}:ambiguous-double-negative"]
    segments = [segment.strip(" \t#>*_`-:|") for segment in re.split(r"(?<=[.!?])\s+|[,;\n]|\bbut\b|\bhowever\b", normalized) if segment.strip()]
    leaks: list[str] = []
    for segment in segments:
        targets = [name for name, pattern in AUTHORIZATION_TARGET_PATTERNS.items() if re.search(pattern, segment)]
        if not targets:
            continue
        positive = any(re.search(pattern, segment) for pattern in POSITIVE_AUTHORIZATION)
        negative = any(re.search(pattern, segment) for pattern in NEGATIVE_AUTHORIZATION)
        ambiguous = bool(re.search(r"\b(?:unless|except if|could be|might be|conditionally)\b", segment) and (positive or "authoriz" in segment))
        if positive or ambiguous:
            # An explicit positive clause always dominates.  Negative clauses
            # are split independently and cannot mask it by proximity.
            if not (negative and not positive and not ambiguous):
                leaks.append(f"{path}:{','.join(targets)}:{segment[:160]}")
    return leaks


def _json_authorization_leaks(path: str, value: Any, location: str = "$") -> list[str]:
    leaks: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            folded = key.casefold().replace("-", "_")
            target = AUTHORITY_FIELD_TARGETS.get(folded)
            explicitly_withheld = child is False or child is None or (isinstance(child, str) and child.upper() in {"WITHHELD", "NOT_AUTHORIZED", "NONE"})
            if target and not explicitly_withheld:
                leaks.append(f"{path}:{location}.{key}:{target}:structured-positive-or-ambiguous")
            leaks.extend(_json_authorization_leaks(path, child, f"{location}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            leaks.extend(_json_authorization_leaks(path, child, f"{location}[{index}]"))
    elif isinstance(value, str):
        leaks.extend(_authorization_text_leaks(f"{path}:{location}", value))
    return leaks


def find_authorization_leakage(path: str, data: bytes) -> list[str]:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise BoundaryError("GOVERNANCE_TEXT_ENCODING", f"{path}:{exc}") from exc
    if path.casefold().endswith(".json"):
        try:
            return _json_authorization_leaks(path, strict_json_loads(data))
        except BoundaryError as exc:
            raise BoundaryError("GOVERNANCE_JSON_PARSE", f"{path}:{exc}") from exc
    return _authorization_text_leaks(path, text)


def validate_governance_package(
    changed_paths: Sequence[str],
    content_by_path: Mapping[str, bytes],
    events: Sequence[str] = (),
    authorization_state: Mapping[str, Any] | None = None,
) -> None:
    require(isinstance(authorization_state, Mapping), "MISSING_AUTHORIZATION_STATE", "governed package")
    validate_authorization_state(authorization_state)
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
