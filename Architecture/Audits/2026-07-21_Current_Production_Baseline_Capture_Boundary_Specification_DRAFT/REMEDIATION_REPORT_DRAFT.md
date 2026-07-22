# Current Production Baseline Capture Boundary Specification R2 Remediation Report

Status: draft remediation evidence; pending independent review.

Governing base: `50bc58afc8861631f253f787d88dbd0f28c2d328`.

External rejection authority: commit `7b60e890b7d426fd1331ab5876004b1b68ee6444`, document `Architecture/Audits/2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_Independent_Review_50bc_REJECTED.md`, Section 33.

## Remediation disposition

The R2 implementation replaces the rejected observation architecture. Readiness is determined only by the fresh raw observations and comparison receipt in `fixture_results_DRAFT.json`. The report does not manufacture expected outcomes and is not part of the accepted-specification input identity; the final Git commit still preserves it as provenance evidence.

Final precommit verification status: `PASS_FRESH_RECONCILED`.

## Section 33 and R2 coverage

| Area | Implemented authority | Actual enforcing surface |
|---|---|---|
| R2-01 | committed blob bytes, package LF policy, clean-filter reconciliation, fresh `core.autocrlf` variants, long paths | `derive_committed_package_authority`, `validate_package_checkout`, `op_checkout` |
| R2-02 | Python AST, PowerShell AST, actual JSON/YAML/TOML/INI parsers, bounded batch/shell grammar, extensionless paths | `derive_repository_selection`, `_config_edges`, `_lex_launch_lines` |
| R2-03 | independently regenerated complete disposition set and registry blobs | `validate_terminal_dispositions`, `validate_terminal_against_authority` |
| R2-04 | accepted-commit Git blobs, separately governed physical inventory root, exact clean non-production worktree gate, and five full authority/evidence tuples | `assert_governed_read_only_root`, `derive_selection_from_accepted_specification`, `validate_questioned_test_authority` |
| R2-05 | strict canonical loader, Draft 2020-12, semantic, cross-artifact, immutable authority | `validate_governed_artifact`, paired `op_schema` and `op_semantic` cases |
| R2-06 | real Windows stream enumeration and transition detection | `alternate_data_streams`, `stable_read`, `op_ads` |
| R2-07 | two complete content reads plus actual Git clean-filter identity | `stable_read`, `enumerate_inventory`, `verify_inventory` |
| R2-08 | independent accepted-repository and later-package reconstruction | `reconstruct_freeze_authority_v4`, `verify_freeze_claim_v4` |
| R2-09 | immutable preserved prefix and chained entry/root hashes | `validate_attempt_ledger_v4`, `validate_attempt_capture_authority_v4` |
| R2-10 | committed preexisting evidence policy reconciled to attempt authority | `validate_required_evidence_policy`, `validate_evidence_bindings_v4` |
| R2-11 | versioned parse of the actual 2,226,181-byte historical log | `parse_historical_log`, `validate_historical_record`, `validate_test_classification` |
| R2-12 | actual controlled Git repositories and append-only event observer | `observe_controlled_repository_state`, `validate_multi_pass` |
| R2-13 | static expectations, raw observations, comparison-only receipt, meta-mutations | `execute_raw`, `compare_observations`, `require_comparison_receipt` |
| R2-14 | structured withholding artifact and complete governed-package scan | `validate_authorization_state`, `validate_governance_package` |
| R2-15 | exact schema pointers, rules, source symbols, invoked cases, observations | `validate_traceability_v4` |
| R2-16 | distinct accepted-specification and later operational-package identities | `validate_operational_package_authority` |

## Independent authority sources

- Case definitions: committed `case_definitions_DRAFT.json`.
- Expectations: separately committed `independent_expectations_DRAFT.json`; static result truth.
- Observations: produced by real enforcing functions in `fixture_runner_DRAFT.py`.
- Enforcing code: SHA-256 semantic root over six named implementation files.
- Schema set: SHA-256 semantic root over every `*_schema_DRAFT.json`.
- Package authority: committed Git objects named by `package_role_authority_DRAFT.json`; derived review results are deliberately outside the accepted-specification input identity to avoid self-reference.
- Historical evidence: immutable external SHA-256 `6F1B876C814B25D27F5EF8B4CFE3A66C4B0E847263FEC784C56896DC8FF3194A`.

The committed fixture receipt exercises both marker-bound synthetic inventory roots and the exact-clean governed-worktree gate. Accepted-specification Git-object authority and physical inventory authority are distinct function inputs. Because a commit cannot contain a result that names its own not-yet-created identity without circularity, the exact final remediation-commit derivation is a required post-commit check and is reported by the governing task record; the verifier derives that authority from final Git objects and does not accept a receipt field as evidence.

## Historical classification

The actual log was independently checked before use. The governed artifact contains 753 derived events: 571 PASSED, 156 FAILED, 23 SUBFAILED, 3 SKIPPED, and 0 ERROR. All 179 failed or subfailed events have nonempty category, rationale, source, parser, version, normalization rule, classification rule, and validated source location. No arithmetic-only synthetic list is used.

## Fixture-independence correction

The rejected helper architecture has been removed. No function named by concatenating `expect_` and `failure` exists in the runner. Negative cases are recorded as `REJECTED` only when the invoked enforcing surface raises its governed code. The comparator checks exact status, disposition, code, surface, evidence, and authority result. A comparison receipt is mandatory. Force-success, comparison-disable, observation-replacement, expectation-only, observation-only, enforcing-code, and label-only meta-mutations are preserved.

## Results

- Total cases: `250`
- Positive cases: `28`
- Mutation cases: `222`
- Real-surface cases: `250`
- Meta-verification cases: `10`
- Passed: `250`
- Failed: `0`
- Discrepancies: `0`
- Cleanup: `PASS`
- Candidate wall time: `1237.675` seconds
- Fresh-reconciliation wall time: `1241.850` seconds
- Case-definition SHA-256: `DC577355FDE118AEC6650876A790C9EDACC58E893969122907B0458E31032DA6`
- Case-set SHA-256: `DB86AD00233C5C54217DD10F85374D3BAE5A87A529652178CE245C4BC136BEE1`
- Independent-expectation SHA-256: `9FBDDFD738A59BEB09013CBCC327A2E43A14366B83598D2684D45CCFB933D8ED`
- Observation-semantic SHA-256: `2F5A3F561410A1EBB1641E5C8EF0CA0BB6F9886017BCC676E9F6057139C8B4EE`
- Enforcing-code identity: `31009D59B86D8439EC7273FC6433C5FD41A43E2FBCB20B94C33B2BA271B3A213`
- Schema-set identity: `98E706F2105D62E0624FD54EEC24AA4949153D250C9AE6E180DA51239B5B1292`
- External historical-evidence identity: `6F1B876C814B25D27F5EF8B4CFE3A66C4B0E847263FEC784C56896DC8FF3194A`
- Comparison-receipt SHA-256: `7377049E4A9E1D203A4E3F864B6185BE47A76C5C8D7AFDE98C725F34D88BC0F9`
- Validator: `jsonschema 4.25.1`, Draft `2020-12`
- Python: `3.12.2`
- Git: `2.53.0.windows.2`
- OS: `Windows-11-10.0.22000-SP0`
- Filesystem: `NTFS`
- Committed/fresh reconciliation: `PASS`

## Known environment outcome

Named, zero-byte, multiple, appearing, disappearing, and content-changing ADS cases use the actual Windows stream APIs. An independent reproduction of an ADS enumeration access-denial could not be created on this Windows identity without changing protected state; that case terminates explicitly as `ADS_ACCESS_FAILURE_UNSUPPORTED`. It is not reported as filesystem-backed success.

## Boundaries

Baseline capture is not authorized. Operational capture-script work is not authorized. Merge, canonical incorporation, production implementation, deployment, service restart, runtime migration, NQ cutover, automated paper trading, live-money trading, Phase 3C2, and Phase 3C1-R11 acceptance are not authorized. Bucket 0 remains incomplete. Bucket 1 remains blocked.
