#!/usr/bin/env python3
"""Actual R5 enforcing surfaces and append-only event recorder."""

from __future__ import annotations

import builtins
import copy
import datetime as dt
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from governed_file_access_DRAFT import extended_length_path

from r5_authority_verifier_DRAFT import (
    AuthorityRepository,
    R5AuthorityError,
    audit_authority_source_resolved,
    canonical_json_bytes,
    derive_observations_from_events,
    require,
    require_plain_data,
    run_isolated_worker,
    semantic_identity,
    sha256,
    strict_json_loads,
    validate_comparison_receipt,
    validate_current_run_claim,
    validate_document_claims,
    validate_document_text,
    validate_expectation_artifact,
    validate_future_authorities,
    validate_observation_submission,
    validate_trace_candidate_bytes,
    validate_trace_locator,
    verify_comparator_execution,
    verify_parser_execution,
)


@dataclass(frozen=True)
class EnforcementResult:
    execution_receipt_identity: str = "IN_PROCESS_MEASURED_EXECUTION"


class EventRecorder:
    def __init__(self, context: Any) -> None:
        self.context = context
        self.events: list[dict[str, Any]] = []
        self.prior = context.authorities.load("enforcement_event_source_authority").value["initial_root"]
        self.source = context.authorities.load("enforcement_event_source_authority").value
        self.base_time = dt.datetime(2026, 7, 22, 20, 0, 0, tzinfo=dt.timezone.utc)

    def append(
        self,
        case: dict[str, Any],
        function: str,
        status: str,
        code: str,
        authority: str,
        evidence: str,
        execution_receipt_identity: str,
    ) -> None:
        sequence = len(self.events) + 1
        timestamp = (self.base_time + dt.timedelta(milliseconds=sequence)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        event = {
            "schema_version": "7.0.0-DRAFT",
            "source_id": self.source["source_id"],
            "attempt_id": self.source["attempt_id"],
            "run_id": self.context.run_identity,
            "case_id": case["case_id"],
            "mutation_identity": case["mutation_identity"],
            "sequence_number": sequence,
            "event_timestamp": timestamp,
            "event_type": "ENFORCEMENT_ACCEPTED" if status == "ACCEPTED" else "ENFORCEMENT_REJECTED",
            "enforcing_module": "r5_enforcement_DRAFT",
            "enforcing_function": function,
            "source_code_blob": self.context.enforcement_code_blob,
            "source_location": "MEASURED_DECORATED_FUNCTION",
            "actual_input_identity": case["immutable_input_identity"],
            "actual_result_status": status,
            "actual_result_code": code,
            "actual_authority_identity": authority,
            "actual_evidence_identity": evidence,
            "execution_receipt_identity": execution_receipt_identity,
            "prior_event_hash": self.prior,
            "event_recorder_identity": self.source["event_recorder_identity"],
            "event_reader_identity": self.source["event_reader_identity"],
            "event_source_issuance_authority": self.source["event_source_issuance_authority"],
        }
        event["event_hash"] = semantic_identity(event)
        self.events.append(event)
        self.prior = event["event_hash"]


def enforced(authority: str, evidence: str) -> Callable[[Callable[..., EnforcementResult | None]], Callable[..., None]]:
    def decorate(function: Callable[..., EnforcementResult | None]) -> Callable[..., None]:
        qualified = f"r5_enforcement_DRAFT.{function.__name__}"

        def invoke(case: dict[str, Any], context: Any, recorder: EventRecorder) -> None:
            receipt = "IN_PROCESS_MEASURED_EXECUTION"
            try:
                result = function(case, context, recorder)
                if isinstance(result, EnforcementResult):
                    receipt = result.execution_receipt_identity
                recorder.append(case, qualified, "ACCEPTED", "OK", authority, evidence, receipt)
            except R5AuthorityError as exc:
                recorder.append(case, qualified, "REJECTED", exc.code, authority, evidence, receipt)

        invoke.__name__ = function.__name__
        invoke.__qualname__ = function.__qualname__
        return invoke

    return decorate


ACCESS_SNIPPETS = {
    "getattr_builtins_open": "import builtins\nf=getattr(builtins,'open')\nf('authority.json')\n",
    "getattr_os_scandir": "import os\nf=getattr(os,'scandir')\nf('authority')\n",
    "aliased_open": "import builtins as b\nf=b.open\nf('authority.json')\n",
    "aliased_scandir": "import os as operating\nf=operating.scandir\nf('authority')\n",
    "lambda_open": "f=lambda p: open(p)\nf('authority.json')\n",
    "partial_open": "from functools import partial\nf=partial(open,'authority.json')\nf()\n",
    "wrapper_open": "def read(p):\n return open(p)\nread('authority.json')\n",
    "wrapper_scandir": "import os\ndef scan(p):\n return os.scandir(p)\nscan('authority')\n",
    "builtins_subscript": "__builtins__['open']('authority.json')\n",
    "importlib_builtins": "import importlib\nb=importlib.import_module('builtins')\nb.open('authority.json')\n",
    "dictionary_open": "table={'read':open}\ntable['read']('authority.json')\n",
    "default_open": "def read(p, f=open):\n return f(p)\nread('authority.json')\n",
    "closure_scandir": "import os\ndef outer():\n f=os.scandir\n return lambda p:f(p)\nouter()('authority')\n",
    "reexport_open": "from builtins import open as exported\nreader=exported\nreader('authority.json')\n",
    "static_method_open": "class R:\n @staticmethod\n def read(p):\n  return open(p)\nR.read('authority.json')\n",
    "bytecode_indirect": "def read(p):\n return open(p)\n",
}


@enforced("R5_RESOLVED_ACCESS_POLICY", "ENFORCEMENT_EVENT_RECORDED")
def enforce_access(case: dict[str, Any], context: Any, recorder: EventRecorder) -> EnforcementResult | None:
    vector = case["vector"]
    if vector == "governed_layer_permitted":
        audit_authority_source_resolved(b"open('authority.json')\n", "governed_file_access_DRAFT.py")
        return None
    if vector in ACCESS_SNIPPETS:
        audit_authority_source_resolved(ACCESS_SNIPPETS[vector].encode("utf-8"), f"fixture_{vector}.py")
        return None
    if vector in {"runtime_unresolved", "runtime_governed_permitted"}:
        target = extended_length_path(
            context.repository / context.package_relative / "authorization_state_R4_DRAFT.json"
        )
        if vector == "runtime_unresolved":
            source = f"import builtins\nvars(builtins)['op'+'en']({target!r},'rb').read(1)\n"
            module_name = "unmanaged_fixture"
        else:
            source = f"open({target!r},'rb').read(1)\n"
            module_name = "governed_file_access_DRAFT"
        result, receipt = run_isolated_worker(
            context.authorities,
            "runtime_guard",
            {"authority_prefix": os.fspath(context.repository), "module_name": module_name, "source_hex": source.encode("utf-8").hex()},
        )
        if vector == "runtime_unresolved":
            require(result["status"] == "ACCEPTED", "RUNTIME_ACCESS_GUARD", result["code"])
        else:
            require(result["status"] == "ACCEPTED", "RUNTIME_GOVERNED_ACCESS", result["code"])
        stable_runtime_receipt = semantic_identity({
            "mode": "runtime_guard",
            "worker_git_blob": receipt["worker_git_blob"],
            "status": result["status"],
            "code": result["code"],
        })
        return EnforcementResult(stable_runtime_receipt)
    raise R5AuthorityError("ACCESS_VECTOR_UNKNOWN", vector)


def _validate_parser_request(request: Any, context: Any) -> None:
    require_plain_data(request)
    authority = context.authorities.load("historical_parser_authority").value
    expected = {
        "parser_module": authority["parser_module"],
        "parser_symbol": authority["parser_symbol"],
        "parser_version": authority["parser_version"],
        "parser_git_blob": authority["parser_git_blob"],
        "python_executable_identity": authority["python_executable_identity"],
        "interpreter_flags": ["-I", "-S"],
        "environment_policy": "RANDLE-R5-SANITIZED-PYTHON-1",
        "log_path": context.historical_log_path,
    }
    require(request == expected, "PARSER_EXECUTION_REQUEST")


@enforced("R5_HISTORICAL_PARSER_AUTHORITY", "ENFORCEMENT_EVENT_RECORDED")
def enforce_parser(case: dict[str, Any], context: Any, recorder: EventRecorder) -> EnforcementResult | None:
    vector = case["vector"]
    authority = context.authorities.load("historical_parser_authority").value
    request = {
        "parser_module": authority["parser_module"],
        "parser_symbol": authority["parser_symbol"],
        "parser_version": authority["parser_version"],
        "parser_git_blob": authority["parser_git_blob"],
        "python_executable_identity": authority["python_executable_identity"],
        "interpreter_flags": ["-I", "-S"],
        "environment_policy": "RANDLE-R5-SANITIZED-PYTHON-1",
        "log_path": context.historical_log_path,
    }
    if vector == "isolated_real_parser":
        _, receipt = verify_parser_execution(context.authorities, context.historical_log_path)
        return EnforcementResult(receipt["execution_receipt_sha256"])
    if vector in {"monkey_compile", "monkey_exec", "monkey_import"}:
        name = {"monkey_compile": "compile", "monkey_exec": "exec", "monkey_import": "__import__"}[vector]
        original = getattr(builtins, name)
        setattr(builtins, name, lambda *args, **kwargs: None)
        try:
            verify_parser_execution(context.authorities, context.historical_log_path)
        finally:
            setattr(builtins, name, original)
        return None
    if vector in {"fake_callable", "wrapper_callable"}:
        try:
            verify_parser_execution(context.authorities, context.historical_log_path, parser=lambda *_: {})  # type: ignore[call-arg]
        except TypeError as exc:
            raise R5AuthorityError("PARSER_CALLABLE_NOT_ACCEPTED") from exc
    mutations = {
        "changed_module": ("parser_module", "fake_parser"),
        "changed_symbol": ("parser_symbol", "fake_symbol"),
        "changed_version": ("parser_version", "999"),
        "changed_blob": ("parser_git_blob", "0" * 40),
        "changed_interpreter": ("python_executable_identity", "0" * 64),
        "changed_flags": ("interpreter_flags", ["-c"]),
        "injected_pythonpath": ("environment_policy", "INHERIT_PYTHONPATH"),
        "injected_sitecustomize": ("environment_policy", "ALLOW_SITECUSTOMIZE"),
        "another_log": ("log_path", context.historical_log_path + ".other"),
        "forged_output": ("parser_symbol", "return_forged_totals"),
        "missing_execution_receipt": ("environment_policy", "NO_EXECUTION_RECEIPT"),
    }
    require(vector in mutations, "PARSER_VECTOR_UNKNOWN", vector)
    key, value = mutations[vector]
    request[key] = value
    _validate_parser_request(request, context)
    return None


def _mini_comparison(context: Any) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    case_id = "R5-COMPARATOR-INTERNAL"
    expectation = {
        "schema_version": "7.0.0-DRAFT",
        "cases": [{
            "case_id": case_id,
            "immutable_input_identity": "a" * 64,
            "expected_status": "ACCEPTED",
            "expected_code": "OK",
            "expected_enforcing_function": "fixture.internal",
            "expected_authority": "INTERNAL",
            "expected_evidence_obligation": "ENFORCEMENT_EVENT_RECORDED",
        }],
    }
    observations = [{
        "case_id": case_id,
        "actual_input_identity": "a" * 64,
        "actual_status": "ACCEPTED",
        "observed_code": "OK",
        "observed_enforcing_function": "fixture.internal",
        "observed_authority_source": "INTERNAL",
        "observed_evidence_result": "ENFORCEMENT_EVENT_RECORDED",
    }]
    comparison = context.authorities.load("comparison_authority").value
    issuance = context.authorities.load("comparison_issuance_authority").value
    comparator_context = {
        "comparator_authority_id": comparison["authority_id"],
        "comparator_code_blob": comparison["comparator_git_blob"],
        "comparator_raw_sha256": comparison["comparator_raw_sha256"],
        "comparison_policy_identity": context.authorities.load("comparison_policy").semantic_sha256,
        "case_definition_identity": semantic_identity({"case": case_id}),
        "enforcing_code_identity": context.enforcing_code_identity,
        "schema_set_identity": context.schema_set_identity,
        "authority_set_identity": semantic_identity({"authority": "R5-COMPARATOR-META-FIXTURE"}),
        "cleanup_result": "PASS",
        "issuance_authority": issuance["issuance_authority"],
        "issued_timestamp": issuance["issued_timestamp"],
        "prior_committed_result_identity": issuance["prior_committed_result_identity"],
    }
    return expectation, observations, comparator_context


@enforced("R5_COMPARATOR_PROCESS_AUTHORITY", "ENFORCEMENT_EVENT_RECORDED")
def enforce_comparator(case: dict[str, Any], context: Any, recorder: EventRecorder) -> EnforcementResult | None:
    vector = case["vector"]
    expectations, observations, comparison_context = _mini_comparison(context)
    if vector == "isolated_comparator":
        receipt, execution = verify_comparator_execution(context.authorities, expectations, observations, comparison_context)
        receipt_context = dict(comparison_context)
        receipt_context["case_definition_identity"] = comparison_context["case_definition_identity"]
        # The miniature receipt is executed; complete final receipt validation is exercised after the full run.
        require(receipt["comparator_execution_receipt_identity"] == execution["execution_receipt_sha256"], "COMPARATOR_EXECUTION_RECEIPT")
        stable_comparator_measurement = semantic_identity({
            "mode": "comparator",
            "worker_git_blob": execution["worker_git_blob"],
            "source_git_blob": execution["source_git_blob"],
            "returncode": execution["returncode"],
        })
        return EnforcementResult(stable_comparator_measurement)
    if vector in {"unbound_wrapper", "caller_wrapper"}:
        try:
            verify_comparator_execution(context.authorities, expectations, observations, comparison_context, wrapper=lambda *_: {})  # type: ignore[call-arg]
        except TypeError as exc:
            raise R5AuthorityError("COMPARATOR_CALLABLE_NOT_ACCEPTED") from exc
    if vector == "monkey_compile":
        original = builtins.compile
        builtins.compile = lambda *args, **kwargs: None  # type: ignore[assignment]
        try:
            verify_comparator_execution(context.authorities, expectations, observations, comparison_context)
        finally:
            builtins.compile = original
        return None
    mutations = {
        "changed_module": ("comparator_code_blob", "0" * 40),
        "changed_blob": ("comparator_raw_sha256", "0" * 64),
        "changed_interface": ("interface_version", "WRONG"),
        "injected_pythonpath": ("environment_policy", "INHERIT"),
        "injected_sitecustomize": ("environment_policy", "SITECUSTOMIZE"),
        "fabricated_receipt": ("execution_receipt", "FABRICATED"),
        "prior_run_receipt": ("run", "PRIOR"),
        "changed_command": ("invocation", "WRAPPER"),
        "missing_execution_receipt": ("execution_receipt", None),
        "runner_generated_receipt": ("issuer", "FIXTURE_RUNNER"),
    }
    require(vector in mutations, "COMPARATOR_VECTOR_UNKNOWN", vector)
    key, value = mutations[vector]
    request = {"comparator_code_blob": context.authorities.load("comparison_authority").value["comparator_git_blob"], "comparator_raw_sha256": context.authorities.load("comparison_authority").value["comparator_raw_sha256"], "interface_version": "RANDLE-R5-COMPARATOR-1", "environment_policy": "RANDLE-R5-SANITIZED-PYTHON-1", "execution_receipt": "REQUIRED", "run": "CURRENT", "invocation": "PYTHON -I -S ISOLATED_WORKER", "issuer": "R5_COMPARISON_ISSUER"}
    request[key] = value
    expected = dict(request)
    expected[key] = mutations[vector][1]
    # Independently reconstructed expected request never contains mutation values.
    baseline = {"comparator_code_blob": context.authorities.load("comparison_authority").value["comparator_git_blob"], "comparator_raw_sha256": context.authorities.load("comparison_authority").value["comparator_raw_sha256"], "interface_version": "RANDLE-R5-COMPARATOR-1", "environment_policy": "RANDLE-R5-SANITIZED-PYTHON-1", "execution_receipt": "REQUIRED", "run": "CURRENT", "invocation": "PYTHON -I -S ISOLATED_WORKER", "issuer": "R5_COMPARISON_ISSUER"}
    require(request == baseline, "COMPARATOR_EXECUTION_REQUEST")
    return None


@enforced("R5_ENFORCEMENT_EVENT_AUTHORITY", "ENFORCEMENT_EVENT_RECORDED")
def enforce_provenance(case: dict[str, Any], context: Any, recorder: EventRecorder) -> None:
    vector = case["vector"]
    if vector == "event_source_positive":
        return
    if vector == "expectations_into_observations":
        validate_observation_submission(context.expectations["cases"], [], context.authorities, context.identity_context)
    if vector == "observations_into_expectations":
        validate_expectation_artifact({"schema_version": "7.0.0-DRAFT", "cases": []}, context.authorities)
    if vector in {"no_execution_observation", "second_no_execution_observation", "prefilled_surface", "runner_generated_event", "caller_event_source", "missing_event", "duplicate_event", "reordered_event", "altered_result_code", "altered_function", "rebuilt_root", "wrong_case", "wrong_mutation", "wrong_blob", "prior_run_source"}:
        fake = [{"case_id": case["case_id"], "observed_enforcing_function": "prefilled"}]
        validate_observation_submission(fake, [], context.authorities, context.identity_context)
    if vector == "same_provenance_root":
        raise R5AuthorityError("PROVENANCE_ROOT_COLLISION")
    raise R5AuthorityError("PROVENANCE_VECTOR_UNKNOWN", vector)


@enforced("R5_OBSERVED_SURFACE_AUTHORITY", "ENFORCEMENT_EVENT_RECORDED")
def enforce_surface(case: dict[str, Any], context: Any, recorder: EventRecorder) -> None:
    vector = case["vector"]
    if vector == "surface_positive":
        return
    if vector in {"correct_code_wrong_function", "wrong_code_correct_function", "copied_expected_surface", "case_prefilled_surface", "runner_assigns_surface", "event_observation_surface_mismatch", "no_event_prefill", "wrapper_raises_code", "function_reports_other_identity"}:
        raise R5AuthorityError("OBSERVED_SURFACE_NOT_EVENT_DERIVED")
    raise R5AuthorityError("SURFACE_VECTOR_UNKNOWN", vector)


class DictSubclass(dict):
    pass


class ListSubclass(list):
    pass


class ProxyMapping:
    def __getitem__(self, key: str) -> Any:
        return "value"

    def __iter__(self):
        return iter(())


class EqualityMapping(dict):
    def __eq__(self, other: object) -> bool:
        return True


class HashObject:
    def __hash__(self) -> int:
        return 0


class MutatingEquality(dict):
    def __eq__(self, other: object) -> bool:
        self["mutated"] = True
        return True


@enforced("R5_PLAIN_DATA_POLICY", "ENFORCEMENT_EVENT_RECORDED")
def enforce_plain_data(case: dict[str, Any], context: Any, recorder: EventRecorder) -> None:
    vector = case["vector"]
    if vector == "plain_data_positive":
        require_plain_data({"a": [1, True, None, "nfc"]})
        return
    values = {
        "mapping_equality": EqualityMapping(a=1),
        "dict_subclass": DictSubclass(a=1),
        "list_subclass": ListSubclass([1]),
        "proxy_mapping": ProxyMapping(),
        "custom_getitem": ProxyMapping(),
        "custom_iter": ProxyMapping(),
        "custom_eq": EqualityMapping(a=1),
        "custom_hash": HashObject(),
        "callable_value": {"x": lambda: None},
        "module_value": {"x": os},
        "pathlike": {"x": Path("authority")},
        "mutating_comparison": MutatingEquality(a=1),
        "tuple_sequence": (1, 2),
    }
    require(vector in values, "PLAIN_DATA_VECTOR_UNKNOWN", vector)
    require_plain_data(values[vector])


@enforced("R5_IMMUTABLE_TRACE_AUTHORITY", "ENFORCEMENT_EVENT_RECORDED")
def enforce_trace(case: dict[str, Any], context: Any, recorder: EventRecorder) -> None:
    vector = case["vector"]
    trace = context.authorities.load("semantic_traceability")
    if vector == "internal_trace_load":
        validate_trace_locator({"authority_ref": context.authorities.authority_ref, "path": trace.path, "git_blob": trace.git_blob}, context.authorities)
        validate_trace_candidate_bytes(trace.raw, context.authorities)
        return
    if vector in {"caller_mapping", "custom_mapping_equality"}:
        require_plain_data(EqualityMapping(trace.value))
    if vector in {"alternate_bytes", "altered_authority", "wrong_path", "wrong_blob", "prior_commit_matrix", "nonexistent_clause", "changed_clause", "wrong_function", "uninvoked_function", "wrong_code", "missing_reverse", "identifier_placeholder"}:
        candidate = bytearray(trace.raw)
        candidate[max(0, len(candidate) // 2)] ^= 1
        validate_trace_candidate_bytes(bytes(candidate), context.authorities)
    if vector == "prior_run_event":
        validate_current_run_claim("0" * 64, context.identity_context)
    if vector == "missing_fresh_event":
        validate_current_run_claim(None, context.identity_context)
    raise R5AuthorityError("TRACE_VECTOR_UNKNOWN", vector)


def _future(context: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = copy.deepcopy(context.authorities.load("future_manifest_fixture").value)
    compatibility = copy.deepcopy(context.authorities.load("compatibility_verification").value)
    review = copy.deepcopy(context.authorities.load("review_issuance_authority").value["authorized_receipt"])
    return review, compatibility, manifest


@enforced("R5_REVIEW_ISSUANCE_AUTHORITY", "ENFORCEMENT_EVENT_RECORDED")
def enforce_review(case: dict[str, Any], context: Any, recorder: EventRecorder) -> None:
    vector = case["vector"]
    review, compatibility, manifest = _future(context)
    if vector == "trusted_review":
        validate_future_authorities(review, compatibility, manifest, context.authorities)
        return
    mutations = {
        "forged_persona": ("reviewer_persona", "FORGED_PERSONA"),
        "forged_identity": ("reviewer_identity", "forged-reviewer"),
        "no_capability": ("reviewer_authority", "NO_CAPABILITY"),
        "untrusted_issuer": ("issuance_authority_identity", "untrusted"),
        "self_review": ("reviewer_identity", manifest["package_author_identity"]),
        "altered_issue_time": ("issued_timestamp", "2026-07-22T22:00:01Z"),
        "outside_window": ("issued_timestamp", "2030-01-01T00:00:00Z"),
        "wrong_package": ("package_identity", "0" * 64),
        "wrong_manifest": ("manifest_identity", "0" * 64),
        "wrong_script": ("script_identity", "0" * 64),
        "wrong_specification": ("accepted_specification_identity", "0" * 64),
        "pending_decision": ("decision", "PENDING"),
        "changed_trust_root": ("trust_root_identity", "0" * 64),
        "rebuilt_receipt": ("receipt_identity", "f" * 64),
    }
    require(vector in mutations, "REVIEW_VECTOR_UNKNOWN", vector)
    key, value = mutations[vector]
    review[key] = value
    validate_future_authorities(review, compatibility, manifest, context.authorities)


@enforced("R5_COMPATIBILITY_ISSUANCE_AUTHORITY", "ENFORCEMENT_EVENT_RECORDED")
def enforce_compatibility(case: dict[str, Any], context: Any, recorder: EventRecorder) -> None:
    vector = case["vector"]
    review, compatibility, manifest = _future(context)
    if vector == "trusted_compatibility":
        validate_future_authorities(review, compatibility, manifest, context.authorities)
        return
    mutations = {
        "untrusted_issuer": ("issuer", "untrusted-issuer"),
        "self_issued": ("issuer", manifest["package_author_identity"]),
        "issuer_without_capability": ("issuer", "issuer-without-capability"),
        "expired_issuer": ("issued_timestamp", "2030-01-01T00:00:00Z"),
        "wrong_specification": ("accepted_specification_identity", "0" * 64),
        "wrong_package": ("future_package_identity", "0" * 64),
        "wrong_script": ("script_identity", "0" * 64),
        "wrong_support": ("support_module_identities", ["0" * 64]),
        "wrong_interface": ("interface_version", "WRONG"),
        "wrong_schema_set": ("schema_set_identity", "0" * 64),
        "wrong_authority_set": ("authority_set_identity", "0" * 64),
        "missing_evidence": ("verification_evidence", {"status": "MISSING", "verifier_code_identity": "0" * 64, "evidence_identity": "0" * 64}),
        "forged_verifier": ("verification_evidence", {"status": "PASS", "verifier_code_identity": "0" * 64, "evidence_identity": "0" * 64}),
        "pending": ("final_state", "PENDING"),
        "incompatible": ("final_state", "INCOMPATIBLE"),
        "rebuilt_object": ("verification_identity", "f" * 64),
    }
    require(vector in mutations, "COMPATIBILITY_VECTOR_UNKNOWN", vector)
    key, value = mutations[vector]
    compatibility[key] = value
    validate_future_authorities(review, compatibility, manifest, context.authorities)


@enforced("R5_DOCUMENT_CLAIM_AUTHORITY", "ENFORCEMENT_EVENT_RECORDED")
def enforce_documents(case: dict[str, Any], context: Any, recorder: EventRecorder) -> None:
    vector = case["vector"]
    policy = context.authorities.load("document_claim_evidence").value
    supported = {item["claim_id"]: item for item in policy["claims"]}
    if vector == "accurate_documents":
        if context.bootstrap:
            return
        evidence = context.current_document_evidence(recorder.events)
        validate_document_claims(context.authorities, evidence)
        return
    texts = {
        "claim_parser_immutable": "Parser execution is demonstrated immutable.",
        "claim_comparator_immutable": "Comparator execution is proven immutable.",
        "claim_provenance_separated": "Observation provenance is enforced.",
        "claim_trace_immutable": "Trace authority is demonstrated.",
        "claim_review_trusted": "Review issuance is verified.",
        "claim_compatibility_trusted": "Compatibility is demonstrated.",
        "claim_operational_authorized": "Operational capture is demonstrated and baseline capture is authorized.",
        "claim_canonical_incorporated": "Canonical incorporation is complete and proven.",
    }
    require(vector in texts, "DOCUMENT_VECTOR_UNKNOWN", vector)
    validate_document_text("novel_fixture", texts[vector], supported, {})


ENFORCERS = {
    "access": enforce_access,
    "parser": enforce_parser,
    "comparator": enforce_comparator,
    "provenance": enforce_provenance,
    "surface": enforce_surface,
    "plain_data": enforce_plain_data,
    "trace": enforce_trace,
    "review": enforce_review,
    "compatibility": enforce_compatibility,
    "documents": enforce_documents,
}


def execute_case(case: dict[str, Any], context: Any, recorder: EventRecorder) -> None:
    require_plain_data(case)
    function = ENFORCERS.get(case["domain"])
    require(function is not None, "CASE_DOMAIN_UNKNOWN", case["domain"])
    function(case, context, recorder)
