#!/usr/bin/env python3
"""Governed R3 independent-expectation runner for disposable fixtures only."""

from __future__ import annotations

import argparse
import copy
import ctypes
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from boundary_verifier_DRAFT import validate_git_command_argv
from comparison_engine_DRAFT import compare
from governed_file_access_DRAFT import (
    GovernedAccessError,
    canonical_absolute_path,
    enumerate_directory,
    extended_length_path,
    git_object_bytes,
    git_revision_identity,
    git_tree_entries,
    read_binary,
    resolve_relative,
    sha256_bytes,
)
from historical_log_parser_DRAFT import parse_historical_log
from inventory_generator_DRAFT import alternate_data_streams, stable_read
from r3_authority_verifier_DRAFT import (
    PACKAGE_RELATIVE,
    AuthorityRepository,
    R3AuthorityError,
    append_only_event_root,
    authorization_statements,
    canonical_json_bytes,
    parse_authority_timestamp,
    semantic_identity,
    validate_attempt_prefix_claim,
    validate_authoritative_byte_claim,
    validate_architecture_documents,
    validate_authorization_state,
    validate_authorization_package,
    validate_authorization_text,
    validate_comparison_receipt,
    validate_evidence_policy_claim,
    validate_future_package,
    validate_frozen_timestamp_claim,
    validate_historical_authority_claim,
    validate_reconciliation_state,
    validate_separate_binding,
    validate_timestamp_chronology,
    validate_traceability,
    verify_freeze_claim,
    verify_historical_classification,
    verify_observer_source,
)
from schema_validation_DRAFT import (
    SchemaValidationError,
    validate_format_checker_configuration,
    validate_schema_and_instance,
    validate_validator_environment_claim,
    validator_identity,
)
from selection_engine_DRAFT import derive_batch_dependency_edges


HARNESS_VERSION = "5.0.0-DRAFT"
FIXTURE_PREFIX = "randle_boundary_r3_"
PACKAGE = Path(__file__).resolve().parent
CaseResult = tuple[str, str, str]


class FixtureInfrastructureError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


class _LongPathTemporaryDirectory:
    """Temporary directory whose cleanup also uses extended-length paths."""

    def __init__(self) -> None:
        self.name = tempfile.mkdtemp(prefix=FIXTURE_PREFIX)

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, exc_type: Any, exc: Any, traceback_value: Any) -> None:
        shutil.rmtree(extended_length_path(self.name))


def _git(repository: Path, *args: str, input_bytes: bytes | None = None, check: bool = True) -> bytes:
    command = [
        "git",
        "-c",
        "core.longpaths=true",
        "-c",
        f"safe.directory={repository.as_posix()}",
        "-C",
        os.fspath(repository),
        *args,
    ]
    result = subprocess.run(command, input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if check and result.returncode:
        raise FixtureInfrastructureError("FIXTURE_GIT", result.stderr.decode("utf-8", "replace"))
    return result.stdout


def _write(path: Path, data: bytes | str) -> None:
    payload = data.encode("utf-8") if isinstance(data, str) else data
    os.makedirs(extended_length_path(path.parent), exist_ok=True)
    descriptor = os.open(extended_length_path(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o644)
    try:
        position = 0
        while position < len(payload):
            position += os.write(descriptor, payload[position:])
    finally:
        os.close(descriptor)


def _make_repo(files: Mapping[str, bytes | str]) -> tuple[tempfile.TemporaryDirectory[str], Path, str]:
    temporary = tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX)
    root = Path(temporary.name)
    _git(root, "init", "-q")
    for relative, payload in files.items():
        _write(root.joinpath(*relative.split("/")), payload)
    _git(root, "add", "--all")
    _git(root, "-c", "user.name=R3 Fixture", "-c", "user.email=r3-fixture@invalid", "commit", "-q", "-m", "fixture")
    return temporary, root, _git(root, "rev-parse", "HEAD").decode("ascii").strip()


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "--all")
    _git(root, "-c", "user.name=R3 Fixture", "-c", "user.email=r3-fixture@invalid", "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD").decode("ascii").strip()


def _observation_claim(observed: Any) -> dict[str, Any]:
    return {
        "path": observed.canonical_path,
        "raw_sha256": observed.sha256,
        "byte_size": observed.byte_size,
        "git_blob": observed.git_blob,
    }


def _exception_code(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    if code:
        return str(code)
    text = str(exc)
    return text.split(":", 1)[0] if text else type(exc).__name__


def _exception_function(exc: BaseException) -> str:
    allowed = {
        "governed_file_access_DRAFT.py",
        "r3_authority_verifier_DRAFT.py",
        "schema_validation_DRAFT.py",
        "selection_engine_DRAFT.py",
        "inventory_generator_DRAFT.py",
        "historical_log_parser_DRAFT.py",
        "comparison_engine_DRAFT.py",
        "fixture_runner_R3_DRAFT.py",
        "boundary_verifier_DRAFT.py",
    }
    ignored = {"require", "execute_case", "_exception_function"}
    for frame in reversed(traceback.extract_tb(exc.__traceback__)):
        name = Path(frame.filename).name
        if name in allowed and frame.name not in ignored:
            return f"{name[:-3]}.{frame.name}"
    return f"{type(exc).__module__}.{type(exc).__name__}"


class Context:
    def __init__(self, repository: Path, authority_ref: str, allow_staged: bool) -> None:
        self.repository = repository
        self.authority_ref = authority_ref
        self.authorities = AuthorityRepository(repository, authority_ref, allow_staged=allow_staged)
        self.validator_lock_bytes = git_object_bytes(
            repository,
            authority_ref,
            f"{PACKAGE_RELATIVE}/validator_requirements_DRAFT.lock",
        ).data
        self.observations: list[dict[str, Any]] = []
        self.definitions: Mapping[str, Any] = {}
        self.expectations: Mapping[str, Any] = {}
        self.run_identity = ""
        self.enforcing_code_identity = ""
        self.schema_set_identity = ""


AUTHORITY_SOURCE = {
    "architecture": "IMMUTABLE_ARCHITECTURE_DOCUMENT_BYTES",
    "access": "GOVERNED_FILE_ACCESS_LAYER",
    "checkout": "IMMUTABLE_GIT_OBJECT",
    "reconciliation": "COMMITTED_RESULT_AND_EXTERNAL_COMPARATOR",
    "batch": "BOUNDED_BATCH_GRAMMAR",
    "separate": "SEPARATE_BINDING_POLICY",
    "timestamp": "PINNED_VALIDATOR_AND_TIMESTAMP_AUTHORITY",
    "freeze": "ATTEMPT_AND_TIMESTAMP_AUTHORITY",
    "prefix": "ATTEMPT_PREFIX_AUTHORITY_BYTES",
    "evidence": "REQUIRED_EVIDENCE_POLICY_BYTES",
    "historical": "HISTORICAL_EVIDENCE_AUTHORITY_BYTES",
    "observer": "OBSERVER_SOURCE_AUTHORITY_BYTES",
    "comparator": "COMPARISON_AUTHORITY_BYTES",
    "authorization": "AUTHORIZATION_POLICY_BYTES",
    "trace": "IMMUTABLE_SPECIFICATION_AND_FRESH_OBSERVATIONS",
    "future": "FUTURE_MANIFEST_AND_REVIEW_BYTES",
    "real": "ACTUAL_FILESYSTEM_AND_GIT_SURFACE",
}


def _ok(function: str, operation: str) -> CaseResult:
    return function, AUTHORITY_SOURCE[operation], "SATISFIED"


def op_access(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector = case["vector"]
    paths = git_tree_entries(context.repository, context.authority_ref)
    schemas = [path for path in paths if path.endswith("_schema_DRAFT.json")]
    markdown = [path for path in paths if path.endswith(".md")]
    if vector in {"git_longest_schema", "git_longest_markdown"}:
        selected = max(schemas if vector.endswith("schema") else markdown, key=len)
        git_object_bytes(context.repository, context.authority_ref, selected)
        return _ok("governed_file_access_DRAFT.git_object_bytes", "access")
    if vector == "worktree_longest_schema":
        selected = max(schemas, key=len)
        read_binary(context.repository.joinpath(*selected.split("/")))
        return _ok("governed_file_access_DRAFT.read_binary", "access")
    if vector == "unc_identity":
        value = extended_length_path(r"\\server\share\authority.json")
        if os.name == "nt" and not value.startswith("\\\\?\\UNC\\"):
            raise FixtureInfrastructureError("UNC_PREFIX")
        return _ok("governed_file_access_DRAFT.extended_length_path", "access")
    if vector == "relative_escape":
        resolve_relative(context.repository, "../escape")
    if vector == "missing_core_longpaths":
        validate_git_command_argv(["git", "status"])
    with _LongPathTemporaryDirectory() as raw:
        root = Path(raw)
        long_parent = root.joinpath(*[(f"segment-{index}-" + "x" * 46) for index in range(5)])
        target = long_parent / "authority-schema-with-long-name.json"
        if vector in {"long_path", "missing_long_path", "renamed_long_path", "inaccessible_long_path", "reparse_point"}:
            _write(target, b'{"long":true}\n')
        if vector == "long_path":
            observed = read_binary(target)
            if observed.data != b'{"long":true}\n' or len(canonical_absolute_path(target)) <= 260:
                raise FixtureInfrastructureError("LONG_PATH_NOT_EXERCISED")
            return _ok("governed_file_access_DRAFT.read_binary", "access")
        if vector == "missing_long_path":
            read_binary(long_parent / "missing.json")
        if vector == "renamed_long_path":
            replacement = long_parent / "renamed.json"
            os.replace(extended_length_path(target), extended_length_path(replacement))
            read_binary(target)
        if vector == "inaccessible_long_path":
            if os.name != "nt":
                raise FixtureInfrastructureError("WINDOWS_REQUIRED")
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            create_file = kernel32.CreateFileW
            create_file.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
            create_file.restype = ctypes.c_void_p
            handle = create_file(extended_length_path(target), 0x80000000, 0, None, 3, 0, None)
            if handle == ctypes.c_void_p(-1).value:
                raise FixtureInfrastructureError("EXCLUSIVE_HANDLE")
            try:
                read_binary(target)
            finally:
                kernel32.CloseHandle(handle)
        if vector == "reparse_point":
            target_directory = root / "junction-target"
            _write(target_directory / "authority.json", b'{"junction":true}\n')
            link = root / "authority-link-directory"
            created = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", os.fspath(link), os.fspath(target_directory)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if created.returncode:
                raise FixtureInfrastructureError("REPARSE_FIXTURE_UNAVAILABLE", created.stderr.decode("utf-8", "replace"))
            read_binary(link / "authority.json")
        if vector == "directory_enumeration":
            _write(root / "b.txt", b"b")
            _write(root / "a.txt", b"a")
            values = enumerate_directory(root)
            if list(values) != sorted(values, key=str.casefold):
                raise FixtureInfrastructureError("DIRECTORY_ORDER")
            return _ok("governed_file_access_DRAFT.enumerate_directory", "access")
        if vector == "changed_long_blob":
            temp, repo, old_commit = _make_repo({"long/authority.json": b'{"version":1}\n'})
            try:
                old = git_object_bytes(repo, old_commit, "long/authority.json")
                _write(repo / "long" / "authority.json", b'{"version":2}\n')
                new_commit = _commit(repo, "changed blob")
                new = git_object_bytes(repo, new_commit, "long/authority.json")
                validate_authoritative_byte_claim(_observation_claim(old), new)
            finally:
                temp.cleanup()
    raise FixtureInfrastructureError("UNKNOWN_ACCESS_VECTOR", str(vector))


def _checkout_repo() -> tuple[tempfile.TemporaryDirectory[str], Path, str]:
    return _make_repo(
        {
            ".gitattributes": "*.json text eol=lf\n*.py text eol=lf\n",
            "package/authority.json": b'{"state":"WITHHELD"}\n',
            "docs/outside.md": b"Outside role map\nSecond line\n",
        }
    )


def op_checkout(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector = case["vector"]
    temporary, repo, commit = _checkout_repo()
    try:
        path = "package/authority.json"
        observed = git_object_bytes(repo, commit, path)
        claim = _observation_claim(observed)
        target = repo / "package" / "authority.json"
        if vector in {"autocrlf_true", "autocrlf_false", "git_object_read"}:
            _git(repo, "-c", f"core.autocrlf={'true' if vector == 'autocrlf_true' else 'false'}", "checkout-index", "-a", "-f")
            validate_authoritative_byte_claim(claim, git_object_bytes(repo, commit, path))
            return _ok("r3_authority_verifier_DRAFT.validate_authoritative_byte_claim", "checkout")
        if vector == "crlf_transformed_worktree":
            _write(target, b'{"state":"WITHHELD"}\r\n')
            validate_authoritative_byte_claim(claim, git_object_bytes(repo, commit, path))
            return _ok("r3_authority_verifier_DRAFT.validate_authoritative_byte_claim", "checkout")
        if vector == "worktree_mutation_unchanged_git":
            _write(target, b'{"state":"CHANGED_WORKTREE_ONLY"}\n')
            validate_authoritative_byte_claim(claim, git_object_bytes(repo, commit, path))
            return _ok("r3_authority_verifier_DRAFT.validate_authoritative_byte_claim", "checkout")
        if vector == "outside_markdown_transformed":
            outside = git_object_bytes(repo, commit, "docs/outside.md")
            _write(repo / "docs" / "outside.md", outside.data.replace(b"\n", b"\r\n"))
            validate_authoritative_byte_claim(_observation_claim(outside), git_object_bytes(repo, commit, "docs/outside.md"))
            return _ok("r3_authority_verifier_DRAFT.validate_authoritative_byte_claim", "checkout")
        if vector == "git_blob_mutation_stale_worktree":
            old_worktree = read_binary(target).data
            _write(target, b'{"state":"CHANGED_GIT_OBJECT"}\n')
            changed = _commit(repo, "changed authority")
            _write(target, old_worktree)
            validate_authoritative_byte_claim(claim, git_object_bytes(repo, changed, path))
        if vector == "attributes_changed":
            attributes = git_object_bytes(repo, commit, ".gitattributes")
            _write(repo / ".gitattributes", b"*.json text eol=crlf\n")
            changed = _commit(repo, "changed attributes")
            validate_authoritative_byte_claim(_observation_claim(attributes), git_object_bytes(repo, changed, ".gitattributes"))
        if vector == "observation_identity_stable":
            first = semantic_identity(_observation_claim(observed))
            _write(target, observed.data.replace(b"\n", b"\r\n"))
            second = semantic_identity(_observation_claim(git_object_bytes(repo, commit, path)))
            if first != second:
                raise FixtureInfrastructureError("CHECKOUT_IDENTITY_CHANGED")
            return _ok("governed_file_access_DRAFT.git_object_bytes", "checkout")
    finally:
        temporary.cleanup()
    raise FixtureInfrastructureError("UNKNOWN_CHECKOUT_VECTOR", str(vector))


def op_reconciliation(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector = case["vector"]
    state = {
        "reconciliation": "MATCHED",
        "all_cases_completed": True,
        "comparison_completed": True,
        "committed_result_exists": True,
        "cleanup": "PASS",
        "terminal_receipt_valid": True,
        "comparison_authority_valid": True,
        "enforcing_code_identity": context.enforcing_code_identity,
        "schema_set_identity": context.schema_set_identity,
    }
    if vector == "not_yet_recorded":
        state["reconciliation"] = "NOT_YET_RECORDED"
    elif vector == "no_committed_result":
        state["reconciliation"] = "MISSING_COMMITTED_RESULT"; state["committed_result_exists"] = False
    elif vector in {"altered_committed", "altered_fresh"}:
        state["reconciliation"] = "MISMATCH"
    elif vector == "missing_comparison_receipt":
        state["terminal_receipt_valid"] = False
    elif vector == "invalid_comparison_authority":
        state["reconciliation"] = "COMPARATOR_NOT_AUTHORIZED"; state["comparison_authority_valid"] = False
    elif vector == "changed_enforcing_code":
        state["enforcing_code_identity"] = "0" * 64
    elif vector == "changed_schema_set":
        state["schema_set_identity"] = "0" * 64
    elif vector == "invalid_committed_result":
        state["reconciliation"] = "INVALID_COMMITTED_RESULT"
    elif vector == "cleanup_failed":
        state["cleanup"] = "FAIL"
    elif vector != "matched":
        raise FixtureInfrastructureError("UNKNOWN_RECONCILIATION_VECTOR", str(vector))
    validate_reconciliation_state(
        state,
        enforcing_code_identity=context.enforcing_code_identity,
        schema_set_identity=context.schema_set_identity,
    )
    return _ok("r3_authority_verifier_DRAFT.validate_reconciliation_state", "reconciliation")


def op_batch(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector = case["vector"]
    scripts = {
        "start_missing": "start missing_launcher\n",
        "start_title_missing": 'start "" missing_launcher\n',
        "call_missing": "call missing_script\n",
        "cmd_missing": "cmd /c missing_script\n",
        "quoted_extensionless_missing": 'start "missing launcher"\n',
        "existing_extensionless": "tool\n",
        "variable_literal": "set TARGET=tool\nstart %TARGET%\n",
        "unresolved_variable": "start %UNKNOWN_TARGET%\n",
        "unsupported_compound": "start tool && echo done\n",
        "malformed_quoting": 'start "unterminated\n',
        "direct_script": "script.cmd\n",
        "powershell_target": "powershell -File script.ps1\n",
        "pwsh_target": "pwsh script.ps1\n",
        "python_target": "python script.py\n",
        "relative_target": "call sub/script.cmd\n",
    }
    with tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX) as raw:
        root = Path(raw)
        _write(root / "launch.cmd", scripts[vector])
        targets = {
            "existing_extensionless": "tool",
            "variable_literal": "tool",
            "unsupported_compound": "tool",
            "direct_script": "script.cmd",
            "powershell_target": "script.ps1",
            "pwsh_target": "script.ps1",
            "python_target": "script.py",
            "relative_target": "sub/script.cmd",
        }
        if vector in targets:
            _write(root.joinpath(*targets[vector].split("/")), "fixture\n")
        path_set = {"launch.cmd", *targets.values()}
        derive_batch_dependency_edges(root, "launch.cmd", path_set)
    return _ok("selection_engine_DRAFT.derive_batch_dependency_edges", "batch")


def _separate_fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    terminal = {"terminal_disposition": "SEPARATE_AND_BIND", "artifact_class": "runtime-log"}
    obligation = {
        "authority_id": "RANDLE-R3-HISTORICAL-EVIDENCE-1",
        "capture_form": "RAW_BYTES_WITH_EXTERNAL_PROVENANCE",
        "recovery_requirement": "REQUIRED_FOR_RECOVERY",
        "semantic_purpose": "PRESERVE_HISTORICAL_TEST_OUTCOME_AUTHORITY",
        "immutability_requirement": "CONTENT_ADDRESSED_IMMUTABLE",
        "evidence": [
            {"role": "historical-content", "class": "content-hash", "external_root_id": "RANDLE-RUNTIME-PROVENANCE"},
            {"role": "historical-path", "class": "path-authority", "external_root_id": "RANDLE-RUNTIME-PROVENANCE"},
        ],
    }
    return terminal, obligation


def op_separate(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector = case["vector"]
    terminal, obligation = _separate_fixture()
    if vector == "authority": obligation["authority_id"] = "FORGED"
    elif vector == "evidence": obligation["evidence"][0]["role"] = "forged"
    elif vector == "capture_form": obligation["capture_form"] = "RAW_BYTES"
    elif vector == "recovery": obligation["recovery_requirement"] = "OPTIONAL"
    elif vector == "purpose": obligation["semantic_purpose"] = "CHANGED"
    elif vector == "remove_evidence": obligation["evidence"].pop()
    elif vector == "uncommitted_authority": obligation["authority_id"] = "UNCOMMITTED"
    elif vector == "external_root": obligation["evidence"][0]["external_root_id"] = "ROGUE"
    elif vector == "include_to_separate": terminal["artifact_class"] = "production-source"
    elif vector == "immutability": obligation["immutability_requirement"] = "MUTABLE"
    elif vector not in {"positive", "rebuild_root"}:
        raise FixtureInfrastructureError("UNKNOWN_SEPARATE_VECTOR", str(vector))
    validate_separate_binding(terminal, obligation, context.authorities)
    return _ok("r3_authority_verifier_DRAFT.validate_separate_binding", "separate")


def op_timestamp(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector = case["vector"]
    if vector == "valid_utc": parse_authority_timestamp("2026-07-22T11:00:00Z", "fixture")
    elif vector == "valid_offset": parse_authority_timestamp("2026-07-22T04:00:00-07:00", "fixture")
    elif vector == "invalid_text": parse_authority_timestamp("not-a-time", "fixture")
    elif vector == "missing_timezone": parse_authority_timestamp("2026-07-22T11:00:00", "fixture")
    elif vector == "impossible_date": parse_authority_timestamp("2026-02-30T11:00:00Z", "fixture")
    elif vector == "caller_chosen":
        validate_frozen_timestamp_claim("2026-07-22T11:06:00Z", context.authorities)
    elif vector == "outside_chronology": validate_timestamp_chronology({"a":"2026-07-22T12:00:00Z","b":"2026-07-22T11:00:00Z"}, ordered_fields=("a","b"), cutoff="2026-07-22T13:00:00Z")
    elif vector == "without_format_checker": validate_format_checker_configuration(None)
    elif vector == "validator_environment_changed":
        claim = validator_identity(context.validator_lock_bytes); claim["version"] = "0.0.0"; validate_validator_environment_claim(claim, context.validator_lock_bytes)
    elif vector == "schema_invalid_timestamp":
        schema = {"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","properties":{"time":{"type":"string","format":"date-time"}},"required":["time"]}
        validate_schema_and_instance(schema, {"time":"not-a-time"}, "r3-invalid-time")
    elif vector == "semantic_schema_agreement":
        schema = {"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","properties":{"time":{"type":"string","format":"date-time"}},"required":["time"]}
        validate_schema_and_instance(schema, {"time":"2026-07-22T11:00:00Z"}, "r3-valid-time")
        parse_authority_timestamp("2026-07-22T11:00:00Z", "fixture")
    else: raise FixtureInfrastructureError("UNKNOWN_TIMESTAMP_VECTOR", str(vector))
    return _ok("r3_authority_verifier_DRAFT.parse_authority_timestamp", "timestamp")


def _freeze_receipt(context: Context) -> dict[str, Any]:
    attempt = context.authorities.load("attempt_authorization").value
    timestamp = context.authorities.load("timestamp_authority").value
    receipt = {
        "attempt_id": attempt["attempt_id"],
        "attempt_sequence": attempt["attempt_sequence"],
        "issued_timestamp": timestamp["freeze_issued_timestamp"],
        "issuance_authority": attempt["issuance_authority"],
        "attempt_prefix_authority_identity": context.authorities.load("attempt_prefix_authority").semantic_sha256,
        "evidence_policy_identity": context.authorities.load("required_evidence_policy").semantic_sha256,
        "observer_authority_identity": context.authorities.load("observer_source_authority").semantic_sha256,
        "specification_authority_identity": context.authorities.binding("specification")["raw_sha256"],
    }
    receipt["freeze_receipt_sha256"] = semantic_identity(receipt)
    return receipt


def op_freeze(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector = case["vector"]
    receipt = _freeze_receipt(context)
    if vector == "attempt_id": receipt["attempt_id"] = "caller-attempt"
    elif vector == "timestamp": receipt["issued_timestamp"] = "2026-07-22T11:06:00Z"
    elif vector == "forged_receipt_hash":
        receipt["attempt_id"] = "caller-attempt"
        receipt["freeze_receipt_sha256"] = semantic_identity({k:v for k,v in receipt.items() if k!="freeze_receipt_sha256"})
    elif vector == "sequence": receipt["attempt_sequence"] = 2
    elif vector == "issuance": receipt["issuance_authority"] = "FORGED"
    elif vector == "reused": receipt["attempt_id"] = "r2-specification-fixture-attempt-001"
    elif vector == "expired": receipt["issued_timestamp"] = "2026-07-22T12:30:00Z"
    elif vector == "before_prior": receipt["issued_timestamp"] = "2026-07-22T09:00:00Z"
    elif vector == "after_cutoff": receipt["issued_timestamp"] = "2026-07-22T14:00:00Z"
    elif vector == "external_authority": receipt["evidence_policy_identity"] = "0"*64
    elif vector != "positive": raise FixtureInfrastructureError("UNKNOWN_FREEZE_VECTOR", str(vector))
    if vector not in {"positive", "forged_receipt_hash"}:
        receipt["freeze_receipt_sha256"] = semantic_identity({k:v for k,v in receipt.items() if k!="freeze_receipt_sha256"})
    verify_freeze_claim(receipt, context.authorities)
    return _ok("r3_authority_verifier_DRAFT.verify_freeze_claim", "freeze")


def _prefix_claim(context: Context) -> dict[str, Any]:
    document = context.authorities.load("attempt_prefix_authority")
    return {
        "authority_id": document.value["authority_id"], "accepted_prefix_count": document.value["accepted_prefix_count"],
        "accepted_attempt_ids": document.value["accepted_attempt_ids"], "previous_ledger_root": document.value["previous_ledger_root"],
        "schema_identity": document.value["schema_identity"], "path": document.path, "raw_sha256": document.raw_sha256,
        "git_blob": document.git_blob, "semantic_sha256": document.semantic_sha256,
        "role_map_binding": semantic_identity(context.authorities.binding("attempt_prefix_authority")),
    }


def op_prefix(case: Mapping[str, Any], context: Context) -> CaseResult:
    claim = _prefix_claim(context); vector = case["vector"]
    fields = {"authority_id":"authority_id","prefix_count":"accepted_prefix_count","attempt_ids":"accepted_attempt_ids","prior_root":"previous_ledger_root","raw_bytes":"raw_sha256","different_object":"semantic_sha256","path":"path","blob":"git_blob","schema":"schema_identity","role_map":"role_map_binding"}
    if vector in fields:
        field=fields[vector]; claim[field] = ([] if field=="accepted_attempt_ids" else "FORGED")
    elif vector == "missing_bytes": claim.pop("raw_sha256")
    elif vector != "positive": raise FixtureInfrastructureError("UNKNOWN_PREFIX_VECTOR", str(vector))
    validate_attempt_prefix_claim(claim, context.authorities)
    return _ok("r3_authority_verifier_DRAFT.validate_attempt_prefix_claim", "prefix")


def _evidence_claim(context: Context) -> dict[str, Any]:
    document=context.authorities.load("required_evidence_policy")
    return {"policy":copy.deepcopy(document.value),"path":document.path,"raw_sha256":document.raw_sha256,"git_blob":document.git_blob,"semantic_sha256":document.semantic_sha256,"role_map_binding":semantic_identity(context.authorities.binding("required_evidence_policy"))}


def op_evidence(case: Mapping[str, Any], context: Context) -> CaseResult:
    claim=_evidence_claim(context); vector=case["vector"]
    if vector=="policy_id":claim["policy"]["policy_id"]="FORGED"
    elif vector=="recovery":claim["policy"]["rules"][0]["required_for_recovery"]=False
    elif vector=="roles":claim["policy"]["rules"][0]["required_roles"]=["forged"]
    elif vector=="classes":claim["policy"]["rules"][0]["required_classes"]=["forged"]
    elif vector=="cardinality":claim["policy"]["rules"][0]["cardinality"]=1
    elif vector=="purpose":claim["policy"]["rules"][0]["semantic_purpose"]="FORGED"
    elif vector=="source_attempt":claim["policy"]["rules"][0]["source_attempt_rule"]="ANY"
    elif vector=="path":claim["path"]="other.json"
    elif vector=="blob":claim["git_blob"]="0"*40
    elif vector=="rebuild_roots":
        claim["policy"]["policy_id"]="FORGED"
        claim["semantic_sha256"]=semantic_identity(claim["policy"])
    elif vector=="missing_bytes":claim.pop("raw_sha256")
    elif vector != "positive":raise FixtureInfrastructureError("UNKNOWN_EVIDENCE_VECTOR",str(vector))
    validate_evidence_policy_claim(claim,context.authorities)
    return _ok("r3_authority_verifier_DRAFT.validate_evidence_policy_claim","evidence")


def _historical_classification(context: Context) -> dict[str, Any]:
    authority=context.authorities.load("historical_evidence_authority").value
    raw=read_binary(authority["authorized_physical_path"]).data
    parsed=parse_historical_log(raw,authority["authorized_physical_path"])
    locations=semantic_identity([{"event":i.get("event_identity"),"source":i.get("source_log_location"),"summary":i.get("summary_log_location")} for i in parsed["outcomes"]])
    return {"logical_evidence_id":authority["logical_evidence_id"],"full_log_path":authority["authorized_physical_path"],"outcome_arithmetic":parsed["outcome_count_by_status"],"source_locations_identity":locations}


def _historical_claim(context: Context) -> dict[str, Any]:
    document=context.authorities.load("historical_evidence_authority")
    return {"authority":copy.deepcopy(document.value),"path":document.path,"raw_sha256":document.raw_sha256,"git_blob":document.git_blob,"semantic_sha256":document.semantic_sha256,"role_map_binding":semantic_identity(context.authorities.binding("historical_evidence_authority"))}


def op_historical(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector=case["vector"]
    if vector in {"positive","nonexistent_path","different_filename","logical_id","case_variation","moved_path","wrong_external_root"}:
        classification=_historical_classification(context)
        if vector=="nonexistent_path":classification["full_log_path"] += ".missing"
        elif vector=="different_filename":classification["full_log_path"] = str(Path(classification["full_log_path"]).with_name("other.log"))
        elif vector=="logical_id":classification["logical_evidence_id"]="FORGED"
        elif vector=="case_variation":classification["full_log_path"]=classification["full_log_path"].upper()
        elif vector=="moved_path":classification["full_log_path"] = str(Path(classification["full_log_path"]).parent/"moved.log")
        elif vector=="wrong_external_root":
            claim=_historical_claim(context);claim["authority"]["source_external_root_id"]="ROGUE";validate_historical_authority_claim(claim,context.authorities)
        verify_historical_classification(classification,context.authorities,lambda data:parse_historical_log(data,classification["full_log_path"]))
        return _ok("r3_authority_verifier_DRAFT.verify_historical_classification","historical")
    claim=_historical_claim(context)
    if vector=="altered_hash":claim["authority"]["sha256"]="0"*64
    elif vector=="authority_bytes":claim["raw_sha256"]="0"*64
    elif vector=="path_normalization":claim["authority"]["path_normalization"]="FORGED"
    elif vector=="reparse_substitution":claim["authority"]["authorized_physical_path"]="C:\\forged-link.log"
    else:raise FixtureInfrastructureError("UNKNOWN_HISTORICAL_VECTOR",str(vector))
    validate_historical_authority_claim(claim,context.authorities)
    return _ok("r3_authority_verifier_DRAFT.validate_historical_authority_claim","historical")


def _observer_issuance(context: Context, source: Path) -> dict[str, Any]:
    policy=context.authorities.load("observer_source_authority").value
    observed=context.authorities.observe_bytes("observer_event_source")
    return {"source_id":policy["source_id"],"attempt_id":context.authorities.load("attempt_authorization").value["attempt_id"],"authorized_physical_path":canonical_absolute_path(source),"source_sha256":observed.sha256,"source_size":observed.byte_size,"append_only_root":policy["append_only_root"],"event_source_implementation_identity":policy["event_source_implementation_identity"],"reader_implementation_identity":policy["reader_implementation_identity"]}


def op_observer(case: Mapping[str, Any], context: Context) -> CaseResult:
    policy=context.authorities.load("observer_source_authority").value
    source=context.repository.joinpath(*policy["authorized_package_path"].split("/"));issuance=_observer_issuance(context,source);vector=case["vector"]
    if vector in {"event_removed","event_reordered","source_truncated"}:
        original=read_binary(source).data; lines=original.splitlines(keepends=True)
        mutated=(b"".join(lines[1:]) if vector=="event_removed" else b"".join(reversed(lines)) if vector=="event_reordered" else original[:len(original)//2])
        try:
            _write(source,mutated)
            mutation=read_binary(source)
            issuance["source_sha256"]=mutation.sha256
            issuance["source_size"]=mutation.byte_size
            verify_observer_source(source,issuance,context.authorities)
        finally:_write(source,original)
        raise FixtureInfrastructureError("OBSERVER_MUTATION_ACCEPTED")
    if vector=="alternate_empty":
        with tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX) as raw:
            alternate=Path(raw)/"events.jsonl";_write(alternate,b"");verify_observer_source(alternate,issuance,context.authorities)
    elif vector=="source_path":issuance["authorized_physical_path"]="C:\\other.jsonl"
    elif vector=="root_rebuilt":issuance["append_only_root"]="0"*64
    elif vector=="different_attempt":issuance["attempt_id"]="other"
    elif vector=="forged_source_id":issuance["source_id"]="FORGED"
    elif vector=="implementation":issuance["event_source_implementation_identity"]="FORGED"
    elif vector=="reader":issuance["reader_implementation_identity"]="FORGED"
    elif vector=="issuance_hash":issuance["source_sha256"]="0"*64
    elif vector!="positive":raise FixtureInfrastructureError("UNKNOWN_OBSERVER_VECTOR",str(vector))
    verify_observer_source(source,issuance,context.authorities)
    return _ok("r3_authority_verifier_DRAFT.verify_observer_source","observer")


def _comparison_fixture(context: Context) -> tuple[dict[str, Any],list[dict[str,Any]],dict[str,Any]]:
    expected={"authority":"INDEPENDENT","cases":[{"case_id":"fixture","expected_status":"ACCEPTED","expected_code":"OK","expected_enforcing_function":"fixture.enforce","expected_authority_source":"FIXTURE_AUTHORITY","expected_evidence_obligation":"SATISFIED","immutable_input_identity":"a"*64}]}
    observed=[{"case_id":"fixture","actual_status":"ACCEPTED","observed_code":"OK","observed_enforcing_function":"fixture.enforce","observed_authority_source":"FIXTURE_AUTHORITY","observed_evidence_result":"SATISFIED","authoritative_input_identity":"a"*64,"run_identity":"fixture"}]
    authority=context.authorities.load("comparison_authority").value;policy=context.authorities.load("comparison_policy").value
    receipt=compare(expected,observed,comparator_identity=authority["comparator_identity"],comparator_raw_sha256=authority["comparator_raw_sha256"],comparison_policy_identity=semantic_identity(policy),enforcing_code_identity=context.enforcing_code_identity,schema_set_identity=context.schema_set_identity,issuance_authority=authority["issuance_authority"])
    return expected,observed,receipt


def op_comparator(case: Mapping[str, Any], context: Context) -> CaseResult:
    expected,observed,receipt=_comparison_fixture(context);vector=case["vector"]
    if vector=="disabled":receipt=None
    elif vector=="empty_success":receipt["expectation_identity"]="0"*64
    elif vector=="code_replaced":receipt["comparator_raw_sha256"]="0"*64
    elif vector=="identity_forged":receipt["comparator_identity"]="FORGED"
    elif vector=="runner_generated":receipt["issuance_authority"]="RUNNER"
    elif vector=="altered_observations":receipt["observation_identity"]="0"*64
    elif vector=="discrepancies_removed":receipt["discrepancies"]=[{"case_id":"x"}]
    elif vector=="status_success":receipt["status"]="MISMATCH"
    elif vector=="policy_altered":receipt["comparison_policy_identity"]="0"*64
    elif vector=="schema_changed":receipt["schema_set_identity"]="0"*64
    elif vector!="positive":raise FixtureInfrastructureError("UNKNOWN_COMPARATOR_VECTOR",str(vector))
    if isinstance(receipt,dict) and vector!="positive":receipt["comparison_receipt_sha256"]=semantic_identity({k:v for k,v in receipt.items() if k!="comparison_receipt_sha256"})
    validate_comparison_receipt(receipt,context.authorities,expectation_identity=semantic_identity(expected),observation_identity=semantic_identity(observed),enforcing_code_identity=context.enforcing_code_identity,schema_set_identity=context.schema_set_identity)
    return _ok("r3_authority_verifier_DRAFT.validate_comparison_receipt","comparator")


def op_authorization(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector=case["vector"]
    if vector.startswith("structured_"):
        state=copy.deepcopy(context.authorities.load("authorization_state").value)
        if vector=="structured_positive":state["domains"]["deployment"]="AUTHORIZED"
        validate_authorization_state(state,context.authorities)
        return _ok("r3_authority_verifier_DRAFT.validate_authorization_state","authorization")
    text=case["input"]["text"]
    validate_authorization_text(text,context.authorities)
    return _ok("r3_authority_verifier_DRAFT.validate_authorization_text","authorization")


def op_architecture(case: Mapping[str, Any], context: Context) -> CaseResult:
    impact = context.authorities.observe_bytes("architecture_impact")
    delta = context.authorities.observe_bytes("canonical_delta")
    claim = {
        "architecture_impact_raw_sha256": impact.sha256,
        "architecture_impact_git_blob": impact.git_blob,
        "canonical_delta_raw_sha256": delta.sha256,
        "canonical_delta_git_blob": delta.git_blob,
    }
    if case["vector"] == "altered_document_claim":
        claim["canonical_delta_raw_sha256"] = "0" * 64
    elif case["vector"] != "positive":
        raise FixtureInfrastructureError("UNKNOWN_ARCHITECTURE_VECTOR", str(case["vector"]))
    validate_architecture_documents(claim, context.authorities)
    return _ok("r3_authority_verifier_DRAFT.validate_architecture_documents", "architecture")


def _future_repo(context: Context, vector: str) -> tuple[tempfile.TemporaryDirectory[str], Path, str, dict[str,Any]]:
    temporary,root,_=_make_repo({"seed.txt":"seed\n"})
    _write(root/"capture_future.py","# future fixture only\n")
    _write(root/"support.py","# support fixture\n")
    package_commit=_commit(root,"future package content")
    revision=git_revision_identity(root,package_commit)
    script=git_object_bytes(root,package_commit,"capture_future.py");support=git_object_bytes(root,package_commit,"support.py")
    policy=context.authorities.load("operational_package_interface").value
    manifest={"interface_version":policy["interface_version"],"package_commit":revision["commit"],"package_tree":revision["tree"],"package_parent":revision["parent"],"operational_script_path":"capture_future.py","operational_script_blob":script.git_blob,"support_modules":[{"path":"support.py","blob":support.git_blob}],"author_authority":"RANDLE-FUTURE-PACKAGE-AUTHOR-1","compatibility_declaration":"COMPATIBLE_WITH_ACCEPTED_SPECIFICATION"}
    review={"decision":"APPROVED","reviewer_authority":"RANDLE-INDEPENDENT-REVIEWER-1","reviewed_package_identity":semantic_identity(manifest),"issued_timestamp":"2026-07-22T12:30:00Z","accepted_specification_identity":context.authorities.binding("specification")["raw_sha256"],"interface_version":policy["interface_version"]}
    if vector=="review_different_package":review["reviewed_package_identity"]="0"*64
    elif vector=="manifest_different_script":manifest["operational_script_path"]="other.py";review["reviewed_package_identity"]=semantic_identity(manifest)
    elif vector=="untrusted_reviewer":review["reviewer_authority"]="UNTRUSTED"
    elif vector=="self_review":review["reviewer_authority"]=manifest["author_authority"]
    elif vector=="pending":review["decision"]="PENDING"
    elif vector=="issue_time":review["issued_timestamp"]="invalid"
    elif vector=="wrong_specification":review["accepted_specification_identity"]="0"*64
    elif vector=="wrong_interface":review["interface_version"]="WRONG"
    elif vector=="mutable_address":manifest["package_commit"]="main";review["reviewed_package_identity"]=semantic_identity(manifest)
    elif vector=="self_referential":manifest["package_commit"]=context.authority_ref;review["reviewed_package_identity"]=semantic_identity(manifest)
    _write(root/"manifest.json",canonical_json_bytes(manifest));_write(root/"review.json",canonical_json_bytes(review))
    governance_commit=_commit(root,"future governance objects")
    interface={"manifest_path":"manifest.json","review_receipt_path":"review.json","manifest_sha256":git_object_bytes(root,governance_commit,"manifest.json").sha256,"review_receipt_sha256":git_object_bytes(root,governance_commit,"review.json").sha256}
    if vector=="arbitrary_review_hash":interface["review_receipt_sha256"]="0"*64
    elif vector=="arbitrary_manifest_hash":interface["manifest_sha256"]="0"*64
    elif vector=="review_without_bytes":interface["review_receipt_path"]="missing-review.json"
    elif vector=="manifest_without_bytes":interface["manifest_path"]="missing-manifest.json"
    elif vector=="receipt_hash_mismatch":interface["review_receipt_sha256"]="1"*64
    return temporary,root,governance_commit,interface


def op_future(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector=case["vector"];temporary,root,commit,interface=_future_repo(context,vector)
    try:validate_future_package(root,commit,interface,context.authorities)
    finally:temporary.cleanup()
    return _ok("r3_authority_verifier_DRAFT.validate_future_package","future")


def op_real(case: Mapping[str, Any], context: Context) -> CaseResult:
    vector=case["vector"]
    with tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX) as raw:
        root=Path(raw);path=root/"artifact.bin";_write(path,b"stable")
        if vector=="ads":
            _write(Path(str(path)+":governed"),b"stream")
            stable_read(path)
        elif vector=="two_read":
            result=stable_read(path)
            if result["first_data"]!=result["second_data"]:raise FixtureInfrastructureError("TWO_READ")
            return _ok("inventory_generator_DRAFT.stable_read","real")
        elif vector=="replacement":
            def mutate(target:Path)->None:
                replacement=target.with_suffix(".replacement");_write(replacement,b"stable");os.replace(replacement,target)
            stable_read(path,mutation_hook=mutate,ads_probe=lambda _path:[])
        elif vector=="actual_git_repo":
            temporary,repo,commit=_make_repo({"authority.txt":"authority\n"})
            try:git_object_bytes(repo,commit,"authority.txt")
            finally:temporary.cleanup()
            return _ok("governed_file_access_DRAFT.git_object_bytes","real")
    raise FixtureInfrastructureError("UNKNOWN_REAL_VECTOR",str(vector))


def op_trace(case: Mapping[str, Any], context: Context) -> CaseResult:
    observed=git_object_bytes(context.repository,context.authority_ref,f"{PACKAGE_RELATIVE}/semantic_traceability_R3_DRAFT.json")
    matrix=copy.deepcopy(json.loads(observed.data));vector=case["vector"]
    observations=copy.deepcopy(context.observations)
    if vector in {"bootstrap_positive", "bootstrap_mutation"}:
        matrix["rows"] = [matrix["rows"][0]]
        matrix["reverse_clause_ids"] = [matrix["rows"][0]["clause_id"]]
        if vector == "bootstrap_mutation":
            matrix["rows"][0]["clause_id"] = "CPB-R3-99"
    elif vector=="nonexistent_clause":matrix["rows"][0]["clause_id"]="CPB-R3-99"
    elif vector=="altered_clause_text":matrix["rows"][0]["clause_semantic_sha256"]="0"*64
    elif vector=="wrong_clause_hash":matrix["rows"][1]["clause_semantic_sha256"]="0"*64
    elif vector=="missing_fresh_observation":observations=[item for item in observations if item["case_id"]!=matrix["rows"][0]["positive_case_id"]]
    elif vector=="prior_observation":next(item for item in observations if item["case_id"]==matrix["rows"][0]["positive_case_id"])["run_identity"]="prior"
    elif vector=="wrong_function":matrix["rows"][0]["enforcing_function"]="r3_authority_verifier_DRAFT.nonexistent_function"
    elif vector=="never_invoked":matrix["rows"][0]["positive_case_id"]="R3-TRACE-POSITIVE"
    elif vector=="wrong_schema_pointer":matrix["rows"][0]["schema_pointer"]="/missing"
    elif vector=="wrong_rule":matrix["rows"][0]["rule_id"]="MISSING"
    elif vector=="wrong_case":matrix["rows"][0]["mutation_case_id"]="MISSING"
    elif vector=="wrong_observed_code":
        target=matrix["rows"][0]["mutation_case_id"];next(item for item in observations if item["case_id"]==target)["observed_code"]="FORGED"
    elif vector=="identifier_placeholder":matrix["rows"]=[]
    elif vector=="removed_reverse":matrix["reverse_clause_ids"].pop()
    elif vector not in {"positive", "bootstrap_positive", "bootstrap_mutation"}:raise FixtureInfrastructureError("UNKNOWN_TRACE_VECTOR",str(vector))
    validate_traceability(matrix,observations,context.expectations,context.authorities,current_run_identity=context.run_identity)
    return _ok("r3_authority_verifier_DRAFT.validate_traceability","trace")


OPERATIONS: dict[str, Callable[[Mapping[str, Any], Context], CaseResult]] = {
    "access":op_access,"checkout":op_checkout,"reconciliation":op_reconciliation,"batch":op_batch,
    "separate":op_separate,"timestamp":op_timestamp,"freeze":op_freeze,"prefix":op_prefix,
    "evidence":op_evidence,"historical":op_historical,"observer":op_observer,"comparator":op_comparator,
    "authorization":op_authorization,"architecture":op_architecture,"future":op_future,"real":op_real,"trace":op_trace,
}


def execute_case(case: Mapping[str, Any], context: Context) -> dict[str, Any]:
    operation_name=case["operation"]
    try:
        result=OPERATIONS[operation_name](case,context)
        status="ACCEPTED";code="OK";function,authority,evidence=result
    except BaseException as exc:
        status="REJECTED";code=_exception_code(exc);function=_exception_function(exc);authority=AUTHORITY_SOURCE[operation_name];evidence="REJECTION_EVIDENCE"
    return {"case_id":case["case_id"],"actual_status":status,"observed_code":code,"observed_enforcing_function":function,"observed_authority_source":authority,"observed_evidence_result":evidence,"authoritative_input_identity":case["immutable_input_identity"],"run_identity":context.run_identity}


def _identity_set(repository:Path,authority_ref:str,paths:Sequence[str])->str:
    return semantic_identity([{"path":path,"raw_sha256":git_object_bytes(repository,authority_ref,path).sha256,"git_blob":git_object_bytes(repository,authority_ref,path).git_blob} for path in sorted(paths)])


def run(repository:Path,authority_ref:str,*,allow_staged:bool=False,prepare:bool=False)->dict[str,Any]:
    context=Context(repository,authority_ref,allow_staged)
    authorization_scan_identity=validate_authorization_package(context.authorities)
    definitions_observed=git_object_bytes(repository,authority_ref,f"{PACKAGE_RELATIVE}/case_definitions_R3_DRAFT.json")
    expectations_observed=git_object_bytes(repository,authority_ref,f"{PACKAGE_RELATIVE}/independent_expectations_R3_DRAFT.json")
    context.definitions=json.loads(definitions_observed.data);context.expectations=json.loads(expectations_observed.data)
    case_schema=json.loads(git_object_bytes(repository,authority_ref,f"{PACKAGE_RELATIVE}/case_definition_R3_schema_DRAFT.json").data)
    expectation_schema=json.loads(git_object_bytes(repository,authority_ref,f"{PACKAGE_RELATIVE}/independent_expectations_R3_schema_DRAFT.json").data)
    trace_schema=json.loads(git_object_bytes(repository,authority_ref,f"{PACKAGE_RELATIVE}/semantic_traceability_R3_schema_DRAFT.json").data)
    trace_instance=json.loads(git_object_bytes(repository,authority_ref,f"{PACKAGE_RELATIVE}/semantic_traceability_R3_DRAFT.json").data)
    binding_schema=json.loads(git_object_bytes(repository,authority_ref,f"{PACKAGE_RELATIVE}/r3_authority_bindings_schema_DRAFT.json").data)
    validate_schema_and_instance(case_schema,context.definitions,"r3-case-definitions")
    validate_schema_and_instance(expectation_schema,context.expectations,"r3-independent-expectations")
    validate_schema_and_instance(trace_schema,trace_instance,"r3-semantic-traceability")
    validate_schema_and_instance(binding_schema,context.authorities.binding_value,"r3-authority-bindings")
    cases=context.definitions["cases"];expected_by_id={item["case_id"]:item for item in context.expectations["cases"]}
    if {item["case_id"] for item in cases}!=set(expected_by_id) or len(cases)!=len(expected_by_id):raise FixtureInfrastructureError("CASE_EXPECTATION_SET")
    for case in cases:
        identity=semantic_identity(case["input"])
        if case["immutable_input_identity"]!=identity or expected_by_id[case["case_id"]]["immutable_input_identity"]!=identity:raise FixtureInfrastructureError("IMMUTABLE_INPUT_IDENTITY",case["case_id"])
    code_paths=[f"{PACKAGE_RELATIVE}/{name}" for name in ("governed_file_access_DRAFT.py","r3_authority_verifier_DRAFT.py","comparison_engine_DRAFT.py","boundary_verifier_DRAFT.py","selection_engine_DRAFT.py","inventory_generator_DRAFT.py","schema_validation_DRAFT.py","historical_log_parser_DRAFT.py","fixture_runner_R3_DRAFT.py")]
    schema_paths=[path for path in git_tree_entries(repository,authority_ref,PACKAGE_RELATIVE) if path.endswith("_schema_DRAFT.json")]
    context.enforcing_code_identity=_identity_set(repository,authority_ref,code_paths)
    context.schema_set_identity=_identity_set(repository,authority_ref,schema_paths)
    context.run_identity=semantic_identity({"case_definition":definitions_observed.sha256,"expectation":expectations_observed.sha256,"enforcing_code":context.enforcing_code_identity,"schema_set":context.schema_set_identity,"authority":context.authorities.identity})
    before={item.name for item in Path(tempfile.gettempdir()).glob(FIXTURE_PREFIX+"*")}
    started=time.perf_counter()
    for case in cases:
        observation=execute_case(case,context);context.observations.append(observation)
    after={item.name for item in Path(tempfile.gettempdir()).glob(FIXTURE_PREFIX+"*")};cleanup="PASS" if before==after else "FAIL"
    comparison_authority=context.authorities.load("comparison_authority").value;comparison_policy=context.authorities.load("comparison_policy").value
    receipt=compare(context.expectations,context.observations,comparator_identity=comparison_authority["comparator_identity"],comparator_raw_sha256=comparison_authority["comparator_raw_sha256"],comparison_policy_identity=semantic_identity(comparison_policy),enforcing_code_identity=context.enforcing_code_identity,schema_set_identity=context.schema_set_identity,issuance_authority=comparison_authority["issuance_authority"])
    observation_identity=semantic_identity(context.observations);expectation_identity=semantic_identity(context.expectations)
    try:
        validate_comparison_receipt(receipt,context.authorities,expectation_identity=expectation_identity,observation_identity=observation_identity,enforcing_code_identity=context.enforcing_code_identity,schema_set_identity=context.schema_set_identity)
    except R3AuthorityError as exc:
        # Candidate authoring may emit an explicitly non-successful diagnostic
        # receipt so expectation disagreements can be corrected. Review mode
        # remains fail-closed, and candidate mode still exits nonzero.
        if not prepare or exc.code != "COMPARISON_NOT_MATCHED":
            raise
    kinds=Counter(item["kind"] for item in cases);surfaces=Counter(item["surface"] for item in cases)
    result={"schema_version":"5.0.0-DRAFT","authority":"R3_GOVERNED_FIXTURE_RESULT_PENDING_INDEPENDENT_REVIEW","harness_version":HARNESS_VERSION,"total_cases":len(cases),"positive_cases":kinds["positive"],"mutation_cases":kinds["mutation"],"real_surface_cases":surfaces["real"],"meta_verification_cases":surfaces["meta"],"passed":len(cases)-receipt["discrepancy_count"],"failed":receipt["discrepancy_count"],"discrepancies":receipt["discrepancy_count"],"cleanup":"PASS" if cleanup=="PASS" else "FAIL","case_definition_identity":definitions_observed.sha256,"case_set_identity":semantic_identity(sorted(item["case_id"] for item in cases)),"expectation_identity":expectation_identity,"observation_semantic_identity":observation_identity,"enforcing_code_identity":context.enforcing_code_identity,"schema_set_identity":context.schema_set_identity,"comparator_authority_identity":context.authorities.load("comparison_authority").semantic_sha256,"authorization_policy_identity":context.authorities.load("authorization_policy").semantic_sha256,"authorization_scan_identity":authorization_scan_identity,"historical_evidence_identity":context.authorities.load("historical_evidence_authority").semantic_sha256,"attempt_prefix_authority_identity":context.authorities.load("attempt_prefix_authority").semantic_sha256,"evidence_policy_authority_identity":context.authorities.load("required_evidence_policy").semantic_sha256,"observer_source_authority_identity":context.authorities.load("observer_source_authority").semantic_sha256,"traceability_identity":git_object_bytes(repository,authority_ref,f"{PACKAGE_RELATIVE}/semantic_traceability_R3_DRAFT.json").sha256,"future_package_interface_identity":context.authorities.load("operational_package_interface").semantic_sha256,"comparison_receipt_identity":receipt["comparison_receipt_sha256"],"validator":validator_identity(context.validator_lock_bytes),"python_version":platform.python_version(),"git_version":subprocess.run(["git","--version"],capture_output=True,text=True,check=True).stdout.strip(),"os_identity":platform.platform(),"filesystem_identity":"NTFS" if os.name=="nt" else platform.system(),"run_identity":context.run_identity,"observations":context.observations,"comparison_receipt":receipt}
    deterministic_fields=tuple(key for key in result if key not in {"authority","validator","python_version","git_version","os_identity","filesystem_identity"})
    reconciliation="NOT_YET_RECORDED"
    if not prepare:
        try:committed=json.loads(git_object_bytes(repository,authority_ref,f"{PACKAGE_RELATIVE}/fixture_results_R3_DRAFT.json").data)
        except GovernedAccessError:reconciliation="MISSING_COMMITTED_RESULT"
        else:
            result_schema=json.loads(git_object_bytes(repository,authority_ref,f"{PACKAGE_RELATIVE}/fixture_results_R3_schema_DRAFT.json").data)
            try:validate_schema_and_instance(result_schema,committed,"r3-committed-result")
            except SchemaValidationError:reconciliation="INVALID_COMMITTED_RESULT"
            else:
                if all(committed.get(field)==result.get(field) for field in deterministic_fields):reconciliation="MATCHED"
                else:reconciliation="MISMATCH"
    result["reconciliation"]=reconciliation
    result["terminal_receipt_valid"]=receipt["status"]=="MATCHED"
    result["wall_time_seconds"]=round(time.perf_counter()-started,3)
    return result


def main(argv:Sequence[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--repository",type=Path);parser.add_argument("--authority-ref");parser.add_argument("--prepare",action="store_true");parser.add_argument("--output",type=Path);args=parser.parse_args(argv)
    repository=args.repository or Path(_git(PACKAGE,"rev-parse","--show-toplevel").decode().strip());authority_ref=args.authority_ref or _git(repository,"rev-parse","HEAD").decode().strip()
    result=run(repository,authority_ref,allow_staged=args.prepare and authority_ref==":",prepare=args.prepare)
    payload=json.dumps(result,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n"
    if args.output:_write(args.output,payload)
    else:print(payload,end="")
    return 0 if result["failed"]==0 and result["cleanup"]=="PASS" and result["terminal_receipt_valid"] and result["reconciliation"]=="MATCHED" else 1


if __name__=="__main__":raise SystemExit(main())
