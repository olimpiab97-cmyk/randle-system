#!/usr/bin/env python3
"""Pure R3 comparator; its authority is supplied and checked externally."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from r3_authority_verifier_DRAFT import semantic_identity


COMPARATOR_INTERFACE_VERSION = "RANDLE-R3-COMPARATOR-1"


def compare(
    expectations: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    *,
    comparator_identity: str,
    comparator_raw_sha256: str,
    comparison_policy_identity: str,
    enforcing_code_identity: str,
    schema_set_identity: str,
    issuance_authority: str,
) -> dict[str, Any]:
    expected = {item["case_id"]: item for item in expectations["cases"]}
    observed = {item["case_id"]: item for item in observations}
    if len(expected) != len(expectations["cases"]):
        raise ValueError("DUPLICATE_EXPECTATION")
    if len(observed) != len(observations):
        raise ValueError("DUPLICATE_OBSERVATION")
    discrepancies: list[dict[str, Any]] = []
    if set(expected) != set(observed):
        discrepancies.append(
            {
                "case_id": "<case-set>",
                "field": "case_set",
                "expected": sorted(expected),
                "observed": sorted(observed),
            }
        )
    fields = (
        ("expected_status", "actual_status"),
        ("expected_code", "observed_code"),
        ("expected_enforcing_function", "observed_enforcing_function"),
        ("expected_authority_source", "observed_authority_source"),
        ("expected_evidence_obligation", "observed_evidence_result"),
        ("immutable_input_identity", "authoritative_input_identity"),
    )
    for case_id in sorted(set(expected) & set(observed)):
        for expected_field, observed_field in fields:
            if expected[case_id].get(expected_field) != observed[case_id].get(observed_field):
                discrepancies.append(
                    {
                        "case_id": case_id,
                        "field": observed_field,
                        "expected": expected[case_id].get(expected_field),
                        "observed": observed[case_id].get(observed_field),
                    }
                )
    expectation_identity = semantic_identity(expectations)
    observation_identity = semantic_identity(list(observations))
    receipt: dict[str, Any] = {
        "interface_version": COMPARATOR_INTERFACE_VERSION,
        "comparison_completed": True,
        "expectation_identity": expectation_identity,
        "observation_identity": observation_identity,
        "case_set_identity": semantic_identity(sorted(expected)),
        "case_count": len(expected),
        "enforcing_code_identity": enforcing_code_identity,
        "schema_set_identity": schema_set_identity,
        "discrepancies": discrepancies,
        "discrepancy_count": len(discrepancies),
        "status": "MATCHED" if not discrepancies else "MISMATCH",
        "comparator_identity": comparator_identity,
        "comparator_raw_sha256": comparator_raw_sha256,
        "comparison_policy_identity": comparison_policy_identity,
        "issuance_authority": issuance_authority,
    }
    receipt["comparison_receipt_sha256"] = semantic_identity(receipt)
    return receipt
