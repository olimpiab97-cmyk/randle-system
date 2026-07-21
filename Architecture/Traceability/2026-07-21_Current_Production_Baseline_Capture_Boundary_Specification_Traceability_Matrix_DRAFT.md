# Traceability Matrix — Current Production Baseline Capture Boundary Specification

Status: **DRAFT — NOT CANONICAL — NOT APPROVED**

The authoritative draft machine-readable matrix for this package is `Architecture/Audits/2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT/traceability_matrix_DRAFT.json`. It provides both directions: each B1–B5 finding names its requirement rows, and every requirement row names clauses, machine rules, artifacts, fixture cases, expected results, and future obligations.

## Finding-to-prevention summary

| Finding | Preventing clauses | Principal rules/artifacts | Verification | Future obligation |
|---|---|---|---|---|
| B1 — incomplete durable manifest | 8, 12, 16 | `ARCHITECTURE_EVIDENCE_REQUIRED`, long-path manifest schema, two Pine sentinels | `INV-001`–`INV-007`, `EVD-003` | Extended-length enumeration and complete durable binding |
| B2 — missing immutable evidence binding | 1, 2, 8–10, 13, 15–16 | freeze receipt, durable manifest, external dependency bindings | `FRZ-*`, `EVD-*`, `STB-*` | Content-bind every recovery dependency in committed provenance |
| B3 — incomplete failure classification | 5, 14, 16 | complete classification schema and source reconciliation | `TST-000`–`TST-009` | Preserve every outcome, including each `SUBFAILED` |
| B4 — unreconciled attempt provenance | 11, 16 | append-only attempt-ledger schema | `ATT-001`–`ATT-005` | Distinguish no-artifact and unstable attempts permanently |
| B5 — nonreproducible boundary | 1–10, 15–16 | fixed-point derivation, governed registries, freeze, script identity | `SEL-*`, `REG-*`, `FRZ-*`, `STB-*` | Independently accept and freeze rules before a new attempt |

## Clause and case coverage

All 17 top-level normative clauses are represented by `RQ-01` through `RQ-17`. All 77 fixture cases appear in at least one row or in the executable expected/mutation vector coverage. The fixture runner verifies that every implemented case has exactly one expectation vector, that the independent expectation set exactly equals the implemented case set, and that the recorded result reconciles to that set.

## Bidirectional review procedure

An independent reviewer SHALL verify both directions:

1. For each B1–B5 finding, follow `finding.requirement_ids`, then verify every referenced clause, rule, artifact, case, expected result, and obligation.
2. For each `RQ-*` row, follow `finding_ids` back to the originating defect and confirm that the expected result prevents recurrence.
3. Compare every `verification_case_id` with `expected_case_vectors_DRAFT.json` or `mutation_case_vectors_DRAFT.json` and with `fixture_results_DRAFT.json`.
4. Compare every rule ID with `selection_rule_registry_DRAFT.json` and the exact registry entries that invoke it.
5. Treat any missing reverse edge, unknown ID, or untested obligation as a blocking specification defect.
