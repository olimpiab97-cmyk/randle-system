# Draft Package Index — Current Production Baseline Capture Boundary

Status: **REMEDIATED DRAFT — NOT CANONICAL — PENDING NEW INDEPENDENT REVIEW**

This directory contains specification-verification evidence only. The Python files are draft synthetic-fixture utilities, not production capture code. They require or construct disposable fixture roots and confer no capture authority.

## Machine-readable specification artifacts

| File | Role |
|---|---|
| `capture_boundary_schema_DRAFT.json` | Schema for canonical configuration |
| `boundary_config_DRAFT.json` | Draft canonical path, discovery, external-root, and freeze policy |
| `include_registry_schema_DRAFT.json` | Governed include-registry schema |
| `include_registry_DRAFT.json` | Seed entries, five mandatory B5 dispositions, and B1 sentinels |
| `exclusion_registry_schema_DRAFT.json` | Governed exclusion-registry schema |
| `exclusion_registry_DRAFT.json` | Narrow exclusion and separate-inventory entries |
| `selection_rule_registry_DRAFT.json` | Stable machine rule identifiers and predicates |
| `selection_rule_registry_schema_DRAFT.json` | Complete Draft 2020-12 schema for selection rules |
| `terminal_disposition_schema_DRAFT.json` | Schema for exhaustive `INCLUDE`/`EXCLUDE`/`SEPARATE_AND_BIND` output |
| `freeze_receipt_schema_DRAFT.json` | Pre-Pass-A freeze receipt schema |
| `attempt_ledger_schema_DRAFT.json` | Append-only attempt-ledger schema |
| `durable_manifest_schema_DRAFT.json` | Long-path-safe durable-manifest schema |
| `durable_evidence_binding_registry_schema_DRAFT.json` | Complete external/internal evidence binding schema |
| `test_classification_schema_DRAFT.json` | Complete test-outcome classification schema |
| `traceability_matrix_DRAFT.json` | B1–B5 and BR-01–BR-13 to clause/rule/function/case/result/obligation mapping |

## Draft verification implementation and evidence

| File | Role |
|---|---|
| `inventory_generator_DRAFT.py` | Real ADS, extended-path, no-follow, stable-read, raw/Git-clean identity fixture utility; production roots refused |
| `selection_engine_DRAFT.py` | Parser-backed Python/launcher/configuration/test fixed-point selector and terminal-disposition emitter; production roots refused |
| `boundary_verifier_DRAFT.py` | Semantic authority for registries, package Git blobs, inventories, freezes, attempts, evidence, outcomes, stability, traceability, and governance language |
| `schema_validation_DRAFT.py` | Pinned `jsonschema` 4.25.1 Draft 2020-12 schema/instance validation adapter |
| `fixture_runner_DRAFT.py` | Disposable real-filesystem/Git fixture and mutation harness |
| `expected_case_vectors_DRAFT.json` | Positive expected-behavior vectors |
| `mutation_case_vectors_DRAFT.json` | Fail-closed mutation vectors |
| `independent_expectations_DRAFT.json` | Independently stated complete case set and invariants |
| `fixture_results_DRAFT.json` | Bound 188/188 fresh result: 44 positive, 144 mutations, zero discrepancies |
| `CANONICAL_DELTA_DRAFT.md` | Proposed concepts, enforced controls, rejected practices, draft limits, and future incorporation targets |
| `REMEDIATION_REPORT_DRAFT.md` | BR-01 through BR-13 remediation evidence and continuing authority limits |

## Supporting governed documents outside this directory

- `Architecture/15_Randle_AI_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT.md`
- `Architecture/Impact_Assessments/2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_Architecture_Impact_Assessment_DRAFT.md`
- `Architecture/Traceability/2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_Traceability_Matrix_DRAFT.md`

## Authority statement

This package does not run or authorize a baseline capture. It does not authorize merge, canonical incorporation, implementation, deployment, restart, migration, NQ cutover, any trading, Bucket 0 completion, Bucket 1, Phase 3C2, or Phase 3C1-R11 acceptance.
