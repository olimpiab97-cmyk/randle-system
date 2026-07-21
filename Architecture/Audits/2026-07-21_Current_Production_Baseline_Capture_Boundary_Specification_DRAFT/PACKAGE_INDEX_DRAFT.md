# Draft Package Index — Current Production Baseline Capture Boundary

Status: **DRAFT — NOT CANONICAL — NOT APPROVED**

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
| `freeze_receipt_schema_DRAFT.json` | Pre-Pass-A freeze receipt schema |
| `attempt_ledger_schema_DRAFT.json` | Append-only attempt-ledger schema |
| `durable_manifest_schema_DRAFT.json` | Long-path-safe durable-manifest schema |
| `durable_evidence_binding_registry_schema_DRAFT.json` | Complete external/internal evidence binding schema |
| `test_classification_schema_DRAFT.json` | Complete test-outcome classification schema |
| `traceability_matrix_DRAFT.json` | B1–B5-to-clause/rule/case/result/obligation mapping |

## Draft verification implementation and evidence

| File | Role |
|---|---|
| `inventory_generator_DRAFT.py` | Long-path, no-follow, stable-read inventory fixture utility; production roots refused |
| `selection_engine_DRAFT.py` | Synthetic AST import/dynamic-import/file/subprocess fixed-point selector; production roots refused |
| `boundary_verifier_DRAFT.py` | Pure validation functions for registries, inventory, freeze, evidence, outcomes, attempts, stability, and governance |
| `fixture_runner_DRAFT.py` | Synthetic fixture and mutation harness |
| `expected_case_vectors_DRAFT.json` | Positive expected-behavior vectors |
| `mutation_case_vectors_DRAFT.json` | Fail-closed mutation vectors |
| `independent_expectations_DRAFT.json` | Independently stated complete case set and invariants |
| `fixture_results_DRAFT.json` | Final 77/77 passing fixture result |

## Supporting governed documents outside this directory

- `Architecture/15_Randle_AI_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT.md`
- `Architecture/Impact_Assessments/2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_Architecture_Impact_Assessment_DRAFT.md`
- `Architecture/Traceability/2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_Traceability_Matrix_DRAFT.md`

## Authority statement

This package does not run or authorize a baseline capture. It does not authorize merge, canonical incorporation, implementation, deployment, restart, migration, NQ cutover, any trading, Bucket 0 completion, Bucket 1, Phase 3C2, or Phase 3C1-R11 acceptance.
