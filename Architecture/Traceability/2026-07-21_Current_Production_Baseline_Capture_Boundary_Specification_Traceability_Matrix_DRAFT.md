# Traceability Narrative: Current Production Baseline Capture Boundary R2

Status: draft narrative; machine authority is `semantic_traceability_DRAFT.json`.

## Trace chain

Every R2 row binds:

1. normative requirement and specification clause;
2. schema family and exact JSON Pointer for every property or conditional;
3. selection-rule registry entry;
4. source file and exact function symbol;
5. invoked positive and mutation cases;
6. static expectation, including exact terminal disposition, status, code, surface, evidence, and authority result;
7. fresh raw observation; and
8. future operational obligation.

Reverse checks require every schema pointer, selection-rule ID, and expected enforcing surface to have authority. The verifier parses source files with the Python AST, proves each mapped symbol exists, and proves every mapped symbol is invoked by a case expecting that exact surface. No `ALL_DECLARED_FIELDS` placeholder is valid.

## R2 mapping summary

| Requirement | Primary schema families | Primary enforcing symbols | Real-surface proof |
|---|---|---|---|
| R2-01 | case, expectation, package JSON families | `derive_committed_package_authority`, `validate_package_checkout`, `verify_stored_canonical_json` | fresh autocrlf variants, long-path checkout, object/worktree mutations |
| R2-02 | boundary configuration and rule registry | `derive_repository_selection`, `_config_edges`, `_lex_launch_lines` | AST/config parses and missing literal dependencies |
| R2-03 | terminal disposition | `validate_terminal_dispositions`, `validate_terminal_against_authority` | independent universe and registry blobs |
| R2-04 | include, exclusion, rule, boundary configuration | `assert_governed_read_only_root`, `derive_selection_from_accepted_specification`, `validate_questioned_test_authority` | exact accepted-commit policy worktree, separately governed inventory root, actual role blobs, and five files |
| R2-05 | all 17 schema families | `validate_schema_and_instance`, `validate_governed_artifact` | paired schema and semantic invalid vectors |
| R2-06 | boundary configuration | `alternate_data_streams`, `stable_read` | actual NTFS streams and transitions |
| R2-07 | durable manifest and boundary | `stable_read`, `enumerate_inventory`, `verify_inventory` | actual two reads and Git clean filters |
| R2-08 | freeze receipt and operational interface | `reconstruct_freeze_authority_v4`, `verify_freeze_claim_v4` | accepted and later disposable repositories |
| R2-09 | attempt ledger and prefix authority | `validate_attempt_ledger_v4`, `validate_attempt_capture_authority_v4` | externally frozen prefix and chained roots |
| R2-10 | evidence binding and policy | `validate_required_evidence_policy`, `validate_evidence_bindings_v4` | policy-vs-instance semantic mutations |
| R2-11 | test classification | `parse_historical_log`, `validate_historical_record`, `validate_test_classification` | actual immutable 2,226,181-byte log |
| R2-12 | freeze, boundary, manifest | `observe_controlled_repository_state`, `validate_multi_pass` | actual repositories and append-only observer |
| R2-13 | case and expectation | `execute_raw`, `compare_observations`, `require_comparison_receipt` | force-success and comparison meta-mutations |
| R2-14 | authorization state | `validate_authorization_state`, `validate_governance_package` | complete package scan and structured/text mutations |
| R2-15 | semantic traceability | `validate_traceability_v4` | field, rule, symbol, case, expectation, observation mutations |
| R2-16 | operational-package interface and freeze | `validate_operational_package_authority` | distinct later commit and compatibility mutations |

## BR-01 through BR-13 relationship

The R2 rows refine and supersede the earlier BR repair claims:

- BR-01 through BR-04 are strengthened by R2-02 through R2-05.
- BR-05 through BR-07 are strengthened by R2-06 through R2-08.
- BR-08 through BR-10 are strengthened by R2-09 through R2-11.
- BR-11 through BR-13 are strengthened by R2-12 through R2-14.
- R2-01, R2-13, R2-15, and R2-16 address cross-cutting byte authority, observation independence, semantic trace, and future-package separation.

Exact field mappings, rule mappings, function mappings, and invoked case IDs are intentionally kept in the machine artifact so this narrative cannot silently redefine them.

## Boundary

This trace demonstrates draft enforcement only. It does not establish execution authority. Baseline capture and operational capture-script work remain withheld.
