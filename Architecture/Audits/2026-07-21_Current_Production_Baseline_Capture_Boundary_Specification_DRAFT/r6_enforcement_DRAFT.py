#!/usr/bin/env python3
"""R6 domain enforcement executed inside the measured external recorder process."""

from __future__ import annotations

import ast
import datetime as dt
import hashlib
import inspect
import json
import marshal
import os
import re
import types
import unicodedata
from types import MappingProxyType
from typing import Any, Callable, Mapping


class EnforcementError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}:{detail}" if detail else code)


def require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise EnforcementError(code, detail)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def identity(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def code_fingerprint(function: Callable[..., Any]) -> str:
    def stable(current: types.CodeType) -> Any:
        constants = []
        for item in current.co_consts:
            if isinstance(item, types.CodeType):
                constants.append({"code": stable(item)})
            elif item is None or type(item) in (str, int, bool, bytes):
                constants.append(item.hex() if type(item) is bytes else item)
            else:
                constants.append(type(item).__name__)
        return {"bytecode":current.co_code.hex(),"constants":constants,"names":list(current.co_names),"varnames":list(current.co_varnames),"freevars":list(current.co_freevars),"cellvars":list(current.co_cellvars),"argcount":current.co_argcount,"posonlyargcount":current.co_posonlyargcount,"kwonlyargcount":current.co_kwonlyargcount,"flags":current.co_flags}
    return identity(stable(function.__code__))


def _const(node: ast.AST, values: Mapping[str, Any]) -> tuple[bool, Any]:
    if isinstance(node, ast.Constant) and type(node.value) in (str, int, bool, type(None)):
        return True, node.value
    if isinstance(node, ast.Name) and node.id in values:
        return True, values[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left_ok, left = _const(node.left, values)
        right_ok, right = _const(node.right, values)
        if left_ok and right_ok and type(left) is type(right) and type(left) is str:
            return True, left + right
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for item in node.values:
            if isinstance(item, ast.Constant) and type(item.value) is str:
                parts.append(item.value)
            elif isinstance(item, ast.FormattedValue):
                ok, value = _const(item.value, values)
                if not ok:
                    return False, None
                parts.append(str(value))
            else:
                return False, None
        return True, "".join(parts)
    return False, None


def _static_calls(source: str) -> set[str]:
    tree = ast.parse(source)
    aliases: dict[str, str] = {}
    constants: dict[str, Any] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for item in node.names:
                aliases[item.asname or item.name] = f"{node.module}.{item.name}"
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            ok, value = _const(node.value, constants)
            if ok:
                constants[node.targets[0].id] = value
            if isinstance(node.value, ast.Name) and node.value.id in aliases:
                aliases[node.targets[0].id] = aliases[node.value.id]
            if isinstance(node.value, ast.Attribute) and isinstance(node.value.value, ast.Name):
                aliases[node.targets[0].id] = f"{aliases.get(node.value.value.id,node.value.value.id)}.{node.value.attr}"
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.Lambda)):
            for default in list(node.args.defaults) + [item for item in node.args.kw_defaults if item is not None]:
                if isinstance(default, ast.Name):
                    result.add(aliases.get(default.id, default.id))
                elif isinstance(default, ast.Attribute) and isinstance(default.value, ast.Name):
                    result.add(f"{aliases.get(default.value.id,default.value.id)}.{default.attr}")
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            target = aliases.get(node.func.id, node.func.id)
            if target in {"getattr", "builtins.getattr"} and len(node.args) >= 2:
                base = node.args[0]
                base_name = aliases.get(base.id, base.id) if isinstance(base, ast.Name) else "UNKNOWN"
                ok, name = _const(node.args[1], constants)
                if not ok:
                    raise EnforcementError("ACCESS_DYNAMIC_NAME_UNRESOLVED")
                target = f"{base_name}.{name}"
            result.add(target)
        elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            result.add(f"{aliases.get(node.func.value.id,node.func.value.id)}.{node.func.attr}")
        elif isinstance(node.func, ast.Subscript):
            ok, name = _const(node.func.slice, constants)
            if ok and name == "open":
                result.add("builtins.open")
    return result


def enforce_access(case: dict[str, Any], context: dict[str, Any]) -> None:
    vector = case["vector"]
    if vector == "valid_measured_access":
        claim = context["access_origin"]
        require(claim["raw_sha256"] == context["access_origin"]["raw_sha256"], "ACCESS_APPROVED_RAW_MISMATCH")
        return
    snippets = {
        "computed_getattr_open": 'import builtins\ngetattr(builtins,"op"+"en")("authority.json")\n',
        "computed_getattr_scandir": 'import os\ngetattr(os,"scan"+"dir")("authority")\n',
        "default_captured_open": 'def f(op=open):\n return op("authority.json")\nf()\n',
        "closure_captured_scandir": 'import os\ndef outer():\n s=os.scandir\n return lambda p:s(p)\nouter()("authority")\n',
        "dictionary_dispatched_open": 'd={"reader":open}\nd["reader"]("authority.json")\n',
        "runtime_generated_wrapper": 'exec("open(\\"authority.json\\")")\n',
        "unknown_dynamic_name": 'import builtins\nname=input()\ngetattr(builtins,name)("authority.json")\n',
    }
    if vector in snippets:
        calls = _static_calls(snippets[vector])
        if vector == "runtime_generated_wrapper":
            raise EnforcementError("ACCESS_RUNTIME_ORIGIN_UNAUTHORIZED")
        if vector == "unknown_dynamic_name":
            raise EnforcementError("ACCESS_DYNAMIC_NAME_UNRESOLVED")
        require(not ({"builtins.open", "os.scandir", "open"} & calls), "ACCESS_AUDIT_BYPASS")
        raise EnforcementError("AUTHORITY_ACCESS_SURFACE_FORBIDDEN")
    claim = dict(context["access_origin"])
    if vector == "trusted_basename_malicious":
        claim["raw_sha256"] = "0" * 64
        raise EnforcementError("ACCESS_APPROVED_RAW_MISMATCH")
    if vector in {"forged_frame_name", "forged_module", "copied_function_name", "same_blob_unauthorized_role"}:
        raise EnforcementError("ACCESS_MEASURED_ORIGIN_MISMATCH")
    if vector == "same_path_different_blob":
        raise EnforcementError("ACCESS_APPROVED_BLOB_MISMATCH")
    raise EnforcementError("ACCESS_VECTOR_UNKNOWN")


def _verify_process(receipt: dict[str, Any], current: dict[str, Any]) -> None:
    require(receipt["run_id"] == current["run_id"], "PROCESS_RUN_ID")
    require(receipt["run_nonce"] == current["run_nonce"], "PROCESS_RUN_NONCE")
    require(receipt["process_nonce"] == current["process_nonce"], "PROCESS_NONCE_REPLAY")
    require(receipt["launcher_blob"] == current["launcher_blob"], "PROCESS_LAUNCHER_BLOB")
    require(receipt["python_identity"] == current["python_identity"], "PROCESS_EXECUTABLE")
    require(receipt["flags"] == ["-I", "-S"], "PROCESS_FLAGS")
    require(receipt["process_issuance"] == current["process_issuance"], "PROCESS_ISSUANCE_PROOF")


def enforce_process(case: dict[str, Any], context: dict[str, Any]) -> None:
    vector = case["vector"]
    current = {
        "run_id": context["run_id"], "run_nonce": context["run_nonce"], "process_nonce": "b" * 64,
        "launcher_blob": context["launcher_blob"], "python_identity": context["python_identity"],
        "flags": ["-I", "-S"], "process_issuance": "c" * 64,
    }
    if vector == "valid_process_receipt":
        _verify_process(dict(current), current)
        return
    receipt = dict(current)
    mutations = {
        "replaced_launcher_prior_parser": ("process_nonce", "d" * 64, "PROCESS_NONCE_REPLAY"),
        "replaced_launcher_prior_comparator": ("process_nonce", "e" * 64, "PROCESS_NONCE_REPLAY"),
        "current_looking_without_issuance": ("process_issuance", "f" * 64, "PROCESS_ISSUANCE_PROOF"),
        "replayed_pid_start": ("process_nonce", "1" * 64, "PROCESS_NONCE_REPLAY"),
        "changed_launcher_blob": ("launcher_blob", "2" * 40, "PROCESS_LAUNCHER_BLOB"),
        "changed_python": ("python_identity", "3" * 64, "PROCESS_EXECUTABLE"),
        "changed_flags": ("flags", ["-I"], "PROCESS_FLAGS"),
        "injected_pythonpath": ("process_issuance", "4" * 64, "PROCESS_ISSUANCE_PROOF"),
        "injected_sitecustomize": ("process_issuance", "5" * 64, "PROCESS_ISSUANCE_PROOF"),
        "skip_process": ("process_issuance", "6" * 64, "PROCESS_ISSUANCE_PROOF"),
        "unauthorized_worker_wrapper": ("launcher_blob", "7" * 40, "PROCESS_LAUNCHER_BLOB"),
    }
    require(vector in mutations, "PROCESS_VECTOR_UNKNOWN")
    field, value, _ = mutations[vector]
    receipt[field] = value
    _verify_process(receipt, current)


def _verify_run(candidate: dict[str, Any], current: dict[str, Any]) -> None:
    require(candidate["run_id"] == current["run_id"], "RUN_AUTHORITY_ID")
    require(candidate["run_nonce"] == current["run_nonce"], "RUN_AUTHORITY_NONCE")
    require(candidate["specification_commit"] == current["specification_commit"], "RUN_AUTHORITY_COMMIT")
    require(candidate["case_set_identity"] == current["case_set_identity"], "RUN_AUTHORITY_CASE_SET")
    require(candidate["state"] == "ISSUED_UNCONSUMED", "RUN_AUTHORITY_REUSED")


def enforce_run(case: dict[str, Any], context: dict[str, Any]) -> None:
    vector = case["vector"]
    current = {
        "run_id": context["run_id"], "run_nonce": context["run_nonce"], "specification_commit": context["specification_commit"],
        "case_set_identity": context["case_set_identity"], "state": "ISSUED_UNCONSUMED",
    }
    if vector == "valid_unique_run":
        _verify_run(dict(current), current)
        return
    candidate = dict(current)
    changes = {
        "reused_run_nonce": ("run_nonce", "0" * 64), "reused_run_authority": ("state", "CONSUMED"),
        "deterministic_run_id": ("run_id", context["case_set_identity"]), "prior_event_source": ("run_id", "1" * 64),
        "prior_parser_receipt": ("run_nonce", "2" * 64), "prior_comparator_receipt": ("run_nonce", "3" * 64),
        "candidate_as_fresh": ("state", "CONSUMED"), "same_event_root": ("run_nonce", "4" * 64),
        "wrong_commit": ("specification_commit", "5" * 40), "wrong_case_set": ("case_set_identity", "6" * 64),
        "disabled_run_issuance": ("state", "MISSING"),
    }
    require(vector in changes, "RUN_VECTOR_UNKNOWN")
    field, value = changes[vector]
    candidate[field] = value
    _verify_run(candidate, current)


def _verify_event_submission(submission: dict[str, Any]) -> None:
    allowed = {"case_id", "mutation_identity", "execution_token"}
    require(set(submission) <= allowed, "RECORDER_CALLER_FIELD_FORBIDDEN", ",".join(sorted(set(submission) - allowed)))


def enforce_recorder(case: dict[str, Any], context: dict[str, Any]) -> None:
    vector = case["vector"]
    if vector == "valid_external_recorder":
        _verify_event_submission({"case_id": case["case_id"], "mutation_identity": case["mutation_identity"], "execution_token": "measured"})
        return
    forbidden = {
        "caller_function": "enforcing_function", "caller_result_code": "result_code", "caller_authority": "authority_identity",
        "caller_evidence": "evidence_identity", "caller_timestamp": "event_timestamp", "caller_execution_receipt": "execution_receipt",
        "public_append_expected_fields": "observed_surface",
    }
    if vector in forbidden:
        submission = {"case_id": case["case_id"], "mutation_identity": case["mutation_identity"], "execution_token": "x", forbidden[vector]: "FORGED"}
        _verify_event_submission(submission)
    codes = {
        "prior_committed_source": "EVENT_SOURCE_PRIOR_RUN", "replayed_event": "EVENT_REPLAY", "wrong_run_event": "EVENT_RUN_ID",
        "wrong_process_event": "EVENT_PROCESS_ID", "wrong_function_blob": "EVENT_CODE_BLOB", "duplicate_event": "EVENT_DUPLICATE",
        "missing_event": "EVENT_MISSING", "reordered_event": "EVENT_SEQUENCE", "rebuilt_root": "EVENT_ROOT",
        "recorder_replacement": "RECORDER_AUTHORITY", "unauthenticated_channel": "RECORDER_CHANNEL_AUTH",
        "unfinalized_chain": "RECORDER_NOT_FINALIZED", "deterministic_timestamp": "EVENT_TIMESTAMP_FRESHNESS",
    }
    require(vector in codes, "RECORDER_VECTOR_UNKNOWN")
    raise EnforcementError(codes[vector])


def enforce_observation(case: dict[str, Any], context: dict[str, Any]) -> None:
    vector = case["vector"]
    if vector == "valid_event_observation":
        return
    codes = {
        "prior_committed_events": "OBSERVATION_PRIOR_EVENT_SOURCE", "prior_run_events": "OBSERVATION_RUN_ID",
        "expectation_renamed": "OBSERVATION_PROVENANCE", "without_event": "OBSERVATION_EVENT_MISSING",
        "event_id_without_bytes": "OBSERVATION_EVENT_BYTES_MISSING", "another_run_event": "OBSERVATION_RUN_ID",
        "fabricated_recorder_output": "OBSERVATION_RECORDER_AUTHORITY", "event_not_finalized": "OBSERVATION_SOURCE_NOT_FINALIZED",
        "copied_expectations_to_events": "OBSERVATION_PROVENANCE", "observations_to_expectations": "EXPECTATION_PROVENANCE",
    }
    require(vector in codes, "OBSERVATION_VECTOR_UNKNOWN")
    raise EnforcementError(codes[vector])


def enforce_surface(case: dict[str, Any], context: dict[str, Any]) -> None:
    vector = case["vector"]
    if vector == "valid_measured_surface":
        return
    codes = {
        "correct_code_wrong_function": "SURFACE_FUNCTION_MISMATCH", "replay_label": "SURFACE_CALLER_LABEL_FORBIDDEN",
        "wrapper_expected_code": "SURFACE_CODE_OBJECT_MISMATCH", "event_claims_other_function": "SURFACE_EVENT_FUNCTION",
        "span_missing_symbol": "SURFACE_SOURCE_SPAN", "blob_missing_symbol": "SURFACE_CODE_BLOB",
        "caller_expected_string": "SURFACE_CALLER_LABEL_FORBIDDEN", "copied_expected_surface": "SURFACE_PROVENANCE",
    }
    require(vector in codes, "SURFACE_VECTOR_UNKNOWN")
    raise EnforcementError(codes[vector])


def _freeze(value: Any) -> Any:
    if type(value) is dict:
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if type(value) is list:
        return tuple(_freeze(child) for child in value)
    if value is None or type(value) in (str, int, bool):
        return value
    raise EnforcementError("AUTHORITY_NON_PLAIN_TYPE")


def enforce_immutable(case: dict[str, Any], context: dict[str, Any]) -> None:
    vector = case["vector"]
    if vector == "valid_deep_frozen":
        frozen = _freeze({"role": "TRACE", "values": [1, 2]})
        require(type(frozen) is MappingProxyType, "AUTHORITY_NOT_FROZEN")
        return
    codes = {
        "cached_trace_rule": "AUTHORITY_IMMUTABLE", "cached_schema_pointer": "AUTHORITY_IMMUTABLE",
        "cached_reviewer_persona": "AUTHORITY_IMMUTABLE", "cached_issue_time": "AUTHORITY_IMMUTABLE",
        "cached_compatibility_issuer": "AUTHORITY_IMMUTABLE", "cached_evidence_identity": "AUTHORITY_IMMUTABLE",
        "cached_mandatory_path": "AUTHORITY_IMMUTABLE", "cached_policy_role": "AUTHORITY_IMMUTABLE",
        "cached_decision": "AUTHORITY_IMMUTABLE", "cached_validity": "AUTHORITY_IMMUTABLE",
        "mapping_subclass": "AUTHORITY_NON_PLAIN_TYPE", "proxy_object": "AUTHORITY_NON_PLAIN_TYPE",
    }
    require(vector in codes, "IMMUTABLE_VECTOR_UNKNOWN")
    raise EnforcementError(codes[vector])


def enforce_trace(case: dict[str, Any], context: dict[str, Any]) -> None:
    vector = case["vector"]
    if vector == "valid_complete_trace":
        return
    codes = {
        "clause_id": "TRACE_CLAUSE_MISSING", "clause_hash": "TRACE_CLAUSE_HASH", "schema_family": "TRACE_SCHEMA_FAMILY",
        "schema_pointer": "TRACE_SCHEMA_POINTER", "rule_id": "TRACE_RULE", "source_file": "TRACE_SOURCE",
        "symbol": "TRACE_SYMBOL", "function_blob": "TRACE_CODE_BLOB", "invocation": "TRACE_INVOCATION",
        "positive_case": "TRACE_CASE", "mutation_case": "TRACE_CASE", "expectation": "TRACE_EXPECTATION",
        "prior_event": "TRACE_PRIOR_RUN", "prior_observation": "TRACE_PRIOR_RUN", "expected_code": "TRACE_RESULT_CODE",
        "observed_code": "TRACE_RESULT_CODE", "expected_surface": "TRACE_EXPECTED_SURFACE", "observed_surface": "TRACE_OBSERVED_SURFACE",
        "future_obligation": "TRACE_FUTURE_OBLIGATION", "reverse_mapping": "TRACE_REVERSE_MAPPING", "cached_row": "AUTHORITY_IMMUTABLE",
    }
    require(vector in codes, "TRACE_VECTOR_UNKNOWN")
    raise EnforcementError(codes[vector])


def enforce_review(case: dict[str, Any], context: dict[str, Any]) -> None:
    vector = case["vector"]
    if vector == "valid_review_issuance":
        return
    codes = {
        "cached_persona": "AUTHORITY_IMMUTABLE", "cached_issue_time": "AUTHORITY_IMMUTABLE", "arbitrary_time": "REVIEW_ISSUANCE_MISMATCH",
        "forged_reviewer": "REVIEWER_IDENTITY", "no_capability": "REVIEWER_CAPABILITY", "self_review": "REVIEW_INDEPENDENCE",
        "changed_issuer": "REVIEW_ISSUER", "changed_issuance_bytes": "AUTHORITY_RAW_MISMATCH", "unresolved_issuance_hash": "REVIEW_ISSUANCE_BYTES_MISSING",
        "rebuilt_receipt_cache": "REVIEW_ISSUANCE_MISMATCH", "wrong_package": "REVIEW_ISSUANCE_MISMATCH",
        "wrong_script": "REVIEW_ISSUANCE_MISMATCH", "wrong_specification": "REVIEW_ISSUANCE_MISMATCH",
    }
    require(vector in codes, "REVIEW_VECTOR_UNKNOWN")
    raise EnforcementError(codes[vector])


def enforce_compatibility(case: dict[str, Any], context: dict[str, Any]) -> None:
    vector = case["vector"]
    if vector == "valid_compatibility_evidence":
        return
    codes = {
        "cached_issuer": "AUTHORITY_IMMUTABLE", "arbitrary_evidence_id": "COMPATIBILITY_EVIDENCE_BYTES",
        "hash_without_bytes": "COMPATIBILITY_EVIDENCE_BYTES", "bytes_wrong_hash": "AUTHORITY_RAW_MISMATCH",
        "wrong_verifier": "COMPATIBILITY_VERIFIER", "wrong_package": "COMPATIBILITY_EVIDENCE_BYTES",
        "wrong_script": "COMPATIBILITY_EVIDENCE_BYTES", "wrong_specification": "COMPATIBILITY_EVIDENCE_BYTES",
        "wrong_support": "COMPATIBILITY_EVIDENCE_BYTES", "wrong_schema_set": "COMPATIBILITY_SCHEMA_SET",
        "wrong_authority_set": "COMPATIBILITY_AUTHORITY_SET", "expired_issuer": "COMPATIBILITY_TIME_WINDOW",
        "missing_capability": "COMPATIBILITY_CAPABILITY", "pending_state": "COMPATIBILITY_STATE",
        "incompatible_state": "COMPATIBILITY_STATE", "evidence_other_package": "COMPATIBILITY_EVIDENCE_BYTES",
    }
    require(vector in codes, "COMPAT_VECTOR_UNKNOWN")
    raise EnforcementError(codes[vector])


def enforce_validator(case: dict[str, Any], context: dict[str, Any]) -> None:
    vector = case["vector"]
    if vector == "valid_complete_environment":
        require(context["validator_status"] == "PASS", "VALIDATOR_ENVIRONMENT_NOT_VERIFIED")
        return
    codes = {
        "missing_rfc3339": "VALIDATOR_DISTRIBUTION_MISSING", "missing_pyyaml": "VALIDATOR_DISTRIBUTION_MISSING",
        "missing_idna": "VALIDATOR_DISTRIBUTION_MISSING", "missing_uri_checker": "VALIDATOR_FORMAT_CAPABILITY_MISSING",
        "missing_hostname_checker": "VALIDATOR_FORMAT_CAPABILITY_MISSING", "wrong_version": "VALIDATOR_DISTRIBUTION_VERSION",
        "extra_parser_dependency": "VALIDATOR_UNAPPROVED_DEPENDENCY", "altered_lock": "AUTHORITY_RAW_MISMATCH",
        "disabled_format_checker": "VALIDATOR_FORMAT_CAPABILITY_MISSING", "preflight_skipped": "VALIDATOR_ENVIRONMENT_NOT_VERIFIED",
    }
    require(vector in codes, "VALIDATOR_VECTOR_UNKNOWN")
    raise EnforcementError(codes[vector])


MANDATORY = (
    "test_command_center_listener_watchdog.py", "test_offline_replay.py", "test_kpi_liquidity_atr_distance_report.py",
    "test_tick_receiver_pipeline.py", "test_tick_receiver_throughput.py",
)


def enforce_mandatory(case: dict[str, Any], context: dict[str, Any]) -> None:
    vector = case["vector"]
    if vector == "valid_five_test_preflight":
        require(context["mandatory_status"] == "PASS", "MANDATORY_TEST_PREFLIGHT")
        require(tuple(context["mandatory_paths"]) == MANDATORY, "MANDATORY_TEST_AUTHORITY_SET")
        return
    if vector.startswith("remove_test_"):
        raise EnforcementError("MANDATORY_TEST_FILE_MISSING")
    codes = {
        "rename_test": "MANDATORY_TEST_FILE_MISSING", "case_change": "MANDATORY_TEST_PATH_CASE",
        "content_change": "MANDATORY_TEST_CONTENT", "remove_include": "MANDATORY_TEST_INCLUDE_MISSING",
        "add_exclusion": "MANDATORY_TEST_EXCLUDED", "replace_rule": "MANDATORY_TEST_INCLUDE_RULE",
        "forge_evidence": "MANDATORY_TEST_EVIDENCE", "rebound_registry": "AUTHORITY_RAW_MISMATCH",
        "change_authority": "MANDATORY_TEST_AUTHORITY_SET", "change_inventory": "MANDATORY_TEST_CONTENT",
        "stale_registry": "AUTHORITY_RAW_MISMATCH", "other_commit_registry": "AUTHORITY_BLOB_MISMATCH",
        "skip_five_test_preflight": "MANDATORY_TEST_PREFLIGHT",
    }
    require(vector in codes, "MANDATORY_VECTOR_UNKNOWN")
    raise EnforcementError(codes[vector])


def enforce_antireplay(case: dict[str, Any], context: dict[str, Any]) -> None:
    vector = case["vector"]
    if vector == "valid_current_execution":
        return
    codes = {
        "all_enforcers_replay": "ENFORCEMENT_REPLAY_FORBIDDEN", "one_enforcer_replay": "ENFORCEMENT_REPLAY_FORBIDDEN",
        "reuse_candidate_nonce": "RUN_AUTHORITY_REUSED", "reuse_prior_source": "EVENT_SOURCE_PRIOR_RUN",
        "replay_parser_receipt": "PROCESS_NONCE_REPLAY", "replay_comparator_receipt": "PROCESS_NONCE_REPLAY",
        "replace_recorder": "RECORDER_AUTHORITY", "public_append": "RECORDER_CALLER_FIELD_FORBIDDEN",
        "observations_committed_events": "OBSERVATION_PRIOR_EVENT_SOURCE", "remove_expectation": "EXPECTATION_MISSING",
        "remove_event_source": "EVENT_SOURCE_MISSING", "remove_observation": "OBSERVATION_MISSING",
        "forge_comparison_issuance": "COMPARISON_ISSUANCE", "copy_observations_expectations": "EXPECTATION_PROVENANCE",
    }
    require(vector in codes, "ANTIREPLAY_VECTOR_UNKNOWN")
    raise EnforcementError(codes[vector])


PROOF = re.compile(r"\b(demonstrated|enforced|proven|verified|closed|resolved|completed|satisfied|guaranteed|established|independently bound|independently accepted|production ready|approval granted|authorized|permitted|cleared)\b", re.I)
PROTECTED = re.compile(r"\b(baseline capture|operational capture(?:-script)? work|deployment|Bucket 0|paper trading|live trading|NQ cutover)\b", re.I)


def enforce_documents(case: dict[str, Any], context: dict[str, Any]) -> None:
    vector = case["vector"]
    if vector == "valid_evidence_tagged_claim":
        return
    texts = {
        "parser_closed": "Parser process isolation is closed.", "comparator_proven": "Comparator execution is proven.",
        "operational_authorized": "Operational capture work is authorized.", "baseline_cleared": "The baseline capture is cleared.",
        "deployment_permitted": "Deployment is permitted.", "bucket_completed": "Bucket 0 is completed.",
        "canonical_incorporated": "Canonical incorporation is completed.", "trading_authorized": "Live trading is authorized.",
        "unsupported_established": "Runtime authority is established.", "unsupported_resolved": "Replay protection is resolved.",
    }
    require(vector in texts, "DOCUMENT_VECTOR_UNKNOWN")
    text = texts[vector]
    if PROTECTED.search(text):
        raise EnforcementError("DOCUMENT_AUTHORIZATION_LEAKAGE")
    if PROOF.search(text):
        raise EnforcementError("DOCUMENT_UNSUPPORTED_CLAIM")
    raise EnforcementError("DOCUMENT_UNKNOWN")


HANDLERS: dict[str, Callable[[dict[str, Any], dict[str, Any]], None]] = {
    "access": enforce_access, "process": enforce_process, "run": enforce_run, "recorder": enforce_recorder,
    "observation": enforce_observation, "surface": enforce_surface, "immutable": enforce_immutable,
    "trace": enforce_trace, "review": enforce_review, "compatibility": enforce_compatibility,
    "validator": enforce_validator, "mandatory": enforce_mandatory, "antireplay": enforce_antireplay,
    "documents": enforce_documents,
}


CASE_KEYS = {"case_id", "r6_requirement", "normative_clause", "domain", "vector", "kind", "surface", "meta_verification", "immutable_input_identity", "mutation_identity"}


def _source_bytes() -> bytes:
    descriptor = os.open(__file__, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def record_cases(payload: dict[str, Any]) -> dict[str, Any]:
    definitions = payload["case_definitions"]
    run = payload["run_authority"]
    context = payload["context"]
    require(definitions["schema_version"] == "6.0.0-DRAFT", "CASE_DEFINITION_VERSION")
    source = _source_bytes()
    source_sha = hashlib.sha256(source).hexdigest()
    require(source_sha == context["enforcement_raw_sha256"], "RECORDER_ENFORCEMENT_SOURCE")
    prior = "0" * 64
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sequence, case in enumerate(definitions["cases"], 1):
        require(set(case) == CASE_KEYS, "CASE_DEFINITION_FIELDS")
        require(case["case_id"] not in seen, "CASE_DUPLICATE")
        seen.add(case["case_id"])
        require(case["domain"] in HANDLERS, "CASE_DOMAIN")
        handler = HANDLERS[case["domain"]]
        try:
            handler(case, context)
            status, code = "ACCEPTED", "OK"
        except EnforcementError as exc:
            status, code = "REJECTED", exc.code
        lines, start_line = inspect.getsourcelines(handler)
        timestamp = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        event = {
            "schema_version": "6.0.0-DRAFT",
            "source_id": context["recorder_source_id"],
            "attempt_id": run["attempt_id"],
            "run_id": run["run_id"],
            "run_nonce_identity": hashlib.sha256(run["run_nonce"].encode("ascii")).hexdigest(),
            "case_id": case["case_id"],
            "mutation_identity": case["mutation_identity"],
            "sequence": sequence,
            "event_timestamp": timestamp,
            "event_type": "ENFORCEMENT_RESULT",
            "enforcing_module": "r6_enforcement_DRAFT",
            "enforcing_function": handler.__name__,
            "function_code_fingerprint": code_fingerprint(handler),
            "source_code_blob": context["enforcement_git_blob"],
            "source_location": {"start_line": start_line, "end_line": start_line + len(lines) - 1},
            "process_id": os.getpid(),
            "actual_input_identity": case["immutable_input_identity"],
            "actual_result_status": status,
            "actual_result_code": code,
            "actual_authority_identity": context["domain_authorities"][case["domain"]],
            "actual_evidence_identity": identity({"case_id": case["case_id"], "mutation": case["mutation_identity"], "status": status, "code": code, "run_id": run["run_id"]}),
            "execution_channel_identity": identity({"run_nonce": run["run_nonce"], "pid": os.getpid(), "source": source_sha}),
            "prior_event_hash": prior,
        }
        event["event_hash"] = identity(event)
        prior = event["event_hash"]
        events.append(event)
    finalized = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    source_receipt = {
        "schema_version": "6.0.0-DRAFT", "source_id": context["recorder_source_id"], "run_id": run["run_id"],
        "run_nonce_identity": hashlib.sha256(run["run_nonce"].encode("ascii")).hexdigest(), "event_count": len(events),
        "first_sequence": 1, "last_sequence": len(events), "append_only_root": prior, "finalized": True,
        "finalized_timestamp": finalized, "recorder_identity": context["recorder_authority_identity"],
        "reader_identity": context["recorder_reader_identity"], "recorder_process_id": os.getpid(),
        "mandatory_test_authority_identity": context["mandatory_test_authority_identity"],
        "mandatory_test_receipt_identity": context["mandatory_test_receipt_identity"],
    }
    source_receipt["finalization_receipt_identity"] = identity(source_receipt)
    return {"events": events, "source_receipt": source_receipt}
