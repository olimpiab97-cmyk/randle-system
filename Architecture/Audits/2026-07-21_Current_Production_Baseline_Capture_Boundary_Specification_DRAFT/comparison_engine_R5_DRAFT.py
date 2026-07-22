#!/usr/bin/env python3
"""Pure R5 comparator executed only by the measured isolated worker."""

from __future__ import annotations

import hashlib
import json
from typing import Any


COMPARATOR_INTERFACE_VERSION = "RANDLE-R5-COMPARATOR-1"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def identity(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def compare(expectations: dict[str, Any], observations: list[dict[str, Any]], context: dict[str, Any]) -> dict[str, Any]:
    expected = {item["case_id"]: item for item in expectations["cases"]}
    observed = {item["case_id"]: item for item in observations}
    if len(expected) != len(expectations["cases"]):
        raise ValueError("DUPLICATE_EXPECTATION")
    if len(observed) != len(observations):
        raise ValueError("DUPLICATE_OBSERVATION")
    discrepancies: list[dict[str, Any]] = []
    if set(expected) != set(observed):
        discrepancies.append({"case_id": "<case-set>", "field": "case_set", "expected": sorted(expected), "observed": sorted(observed)})
    fields = (
        ("immutable_input_identity", "actual_input_identity"),
        ("expected_status", "actual_status"),
        ("expected_code", "observed_code"),
        ("expected_enforcing_function", "observed_enforcing_function"),
        ("expected_authority", "observed_authority_source"),
        ("expected_evidence_obligation", "observed_evidence_result"),
    )
    for case_id in sorted(set(expected) & set(observed)):
        for left, right in fields:
            if expected[case_id].get(left) != observed[case_id].get(right):
                discrepancies.append({"case_id": case_id, "field": right, "expected": expected[case_id].get(left), "observed": observed[case_id].get(right)})
    result = {
        "schema_version": "7.0.0-DRAFT",
        "comparator_authority_id": context["comparator_authority_id"],
        "comparator_code_blob": context["comparator_code_blob"],
        "comparator_raw_sha256": context["comparator_raw_sha256"],
        "interface_version": COMPARATOR_INTERFACE_VERSION,
        "comparison_policy_identity": context["comparison_policy_identity"],
        "case_definition_identity": context["case_definition_identity"],
        "case_set_identity": identity(sorted(expected)),
        "expected_case_count": len(expected),
        "observed_case_count": len(observed),
        "completed": len(observed) == len(expected),
        "expectation_identity": identity(expectations),
        "observation_identity": identity(observations),
        "enforcing_code_identity": context["enforcing_code_identity"],
        "schema_set_identity": context["schema_set_identity"],
        "authority_set_identity": context["authority_set_identity"],
        "discrepancies": discrepancies,
        "discrepancy_count": len(discrepancies),
        "discrepancy_identity": identity(discrepancies),
        "terminal_status": "MATCHED" if not discrepancies else "MISMATCH",
        "cleanup_result": context["cleanup_result"],
        "issuance_authority": context["issuance_authority"],
        "issued_timestamp": context["issued_timestamp"],
        "prior_committed_result_identity": context["prior_committed_result_identity"],
        "current_fresh_result_identity": identity({"observations": observations, "enforcing_code_identity": context["enforcing_code_identity"], "schema_set_identity": context["schema_set_identity"], "authority_set_identity": context["authority_set_identity"]}),
    }
    return result
