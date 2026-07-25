# Governed R7 Remediation Result — Incomplete

Date: 2026-07-22 (America/Los_Angeles)

## 1. Disposition

`REMEDIATION INCOMPLETE`

The post-commit hostile-interface audit found a replay/self-approval path in the proposed R7 fixture runner. The candidate package therefore was discarded from the remediation branch. This record is the only R7 branch delta retained over the immutable R6 base.

## 2. Immutable authorities

- R6 base: `87d066eb16d7fe0b6a1677ea7739c5c2ead4ad94`
- R6 parent: `c211870a8183e8f3e9ea9bf17fa34288b2c3000e`
- R6 tree: `f9891562ea09d011d4d9803d9cf64b88ff1f2dbf`
- R6 subject: `docs(recovery): bind fresh execution and boundary authorities`
- R6 rejection commit: `c286a89d3d858afdfcf677f087c723a460c1e396`
- R6 rejection record blob: `851a2aadef9e121e11b5b43837dd37c0a7c2dc96`
- R6 rejection record SHA-256: `27925c8b8ab0e59f4f0fe70585129ccc3d72e8301c95a35a6e42321a66ebb8c5`

The rejection record was read completely from the immutable review commit. Sections 37 through 41 were reconciled against Sections 7 through 29. R6-B01 through R6-B09 were treated as mandatory authority.

## 3. Preflight and isolation

The mandatory preflight passed before repository modification:

- no active repository writer and no Git lock;
- two command-scoped long-path-safe active-root status reads were byte-identical on stdout and stderr;
- active-root stdout: 84,082 bytes, 1,018 records, SHA-256 `cd3b26ff0e892aac6f59353fae055160f32e0da3d73484f4f430f48064038ef1`;
- active-root stderr: 6,358 bytes, 60 warnings, SHA-256 `6785fe51ed5b0258744cfe310a7a87ad4da103b9a4c15596bdcdb96d309f0ddb`;
- active-root branch `laptop_saved_work`, HEAD `e84774e8b3681ae0aeb8390390dafea8a4b8cfd4`;
- ten-second recursive writer watch: zero events;
- R6: exact parent, tree, subject, 65-path delta, all modes `100644`, 72 authority roles, zero role/blob mismatch;
- R6 rejection: exactly one review-record delta with the declared blob;
- 60 ancestry tests across 15 governed commits and four protected refs: zero prohibited merges;
- isolated worktree: `C:\Users\Trader\AppData\Local\Temp\randle_r7_remediation_20260722_87d066e`;
- isolated branch: `remediation/current-production-baseline-boundary-spec-r7-20260722`.

The dirty active production root was not cleaned, reset, stashed, moved, deleted, or used as the remediation worktree.

## 4. Candidate work and honest-run evidence

The discarded candidate package reached 178 coverage-derived cases (20 positive, 158 mutation), all labeled direct `real_surface`, and produced eight honest executions across short/long and `core.autocrlf=true/false`. Those eight executions reported 1,424/1,424 case executions, zero discrepancies, cleanup `PASS`, and candidate/fresh reconciliation `MATCHED`. All 17 run-provenance categories were distinct across all eight executions. The fixed ledger reported 12,354 entries and each of the eight final run authorities issued once and consumed once.

These honest-run results are retained only as diagnostic evidence. They do not overcome the hostile replay bypass.

Two candidate commits were discarded as permitted by the governed post-commit correction rule:

- `3f15585cebbb78646659ba9dee3f9dadba086fc8` — discarded after Windows ledger lock contention exposed unhandled `PermissionError`;
- `f0cfbce97e913a133530dd66a70326b1e03a0fb6` — discarded after the replay/self-approval bypass below survived.

Neither candidate is in the final remediation-branch history.

## 5. Blocking finding R7-B01 — replaceable authority client permits complete replay

Public surface: `fixture_runner_R7_DRAFT.run()`.

Mutation: replace the module-global `ExternalAuthorityClient` binding with a Python replay adapter. The adapter returned artifacts from a prior honest run, supplied an empty event list, and launched no issuer, parser, comparator, recorder, worker, or ledger process.

Observed result:

```json
{"discrepancies":0,"event_count_supplied":0,"external_processes_launched":0,"failed":0,"passed":178,"replayed_run_id":"df67470fda417db3c87537f4b8924330db8ed139f878a59021621208a6a56a6d","terminal_status":"MATCHED"}
```

Expected result: termination before acceptance because current external issuance, fresh process evidence, fresh authenticated events, current observations, independent comparison, and current reconciliation were absent.

Observed result: accepted terminal verification.

Impact: disposition-determinative. The proposed runner still allowed a caller-replaceable Python object to attest the entire external-authority chain. Prior receipts and observations could be reused as current evidence, and zero current events could still produce `MATCHED`.

## 6. Blocking finding R7-B02 — reconciliation trusts caller dictionaries

Public surface: `fixture_runner_R7_DRAFT.reconcile()`.

Mutation: supply two minimal fabricated dictionaries with the same fabricated semantic mapping and different arbitrary provenance strings. No schemas, run receipts, process receipts, event bytes, observations, comparator receipt, terminal receipt, ledger entry, or authority resolver were supplied.

Observed result:

```python
{'status': 'MATCHED', 'semantic_identities': {'fabricated': 'same'}, 'provenance_disjoint': True}
```

Expected result: fail closed at canonical/schema/evidence resolution.

Observed result: `MATCHED`.

Impact: disposition-determinative. Reconciliation compared caller behavior rather than internally resolving immutable authority and current execution evidence.

## 7. Root cause

The proposed external service used process-private HMAC receipts, but the parent runner did not possess an independently verifiable immutable trust root for those receipts. It delegated validation to a replaceable Python client object. After service shutdown, the terminal and process receipt proofs were not independently verifiable by the public reconciliation surface. Consequently, a replay adapter could simulate the complete service protocol.

## 8. Exact remediation required

Before any R7 package may be labeled ready:

1. Remove `ExternalAuthorityClient` or any equivalent caller-replaceable Python object from the acceptance path.
2. Put final run execution, terminal issuance, and reconciliation behind a separately measured noncaller-replaceable boundary.
3. Bind a durable public verification key or OS-authenticated trust root whose private authority is unavailable to the runner and hostile caller.
4. Make every parser, comparator, recorder, event-source, observation, terminal, and reconciliation receipt independently verifiable after the issuing process exits.
5. Make reconciliation accept only immutable receipt/evidence locators, internally load all bytes, validate closed schemas, verify signatures/trust chains, verify the authoritative ledger, resolve all process and event evidence, and reject arbitrary dictionaries.
6. Bind terminal issuance and final reconciliation to authoritative durable-ledger entries; a caller must not be able to append authoritative ledger records directly.
7. Add direct public-interface mutations that replace the client/supervisor, replay a complete prior result, supply zero events, fabricate reconciliation dictionaries, and attempt direct ledger append.
8. Ensure those mutations prevent terminal `MATCHED`, then rerun the complete eight-execution matrix and post-commit audit.
9. Correct Architecture Impact Assessment and Canonical Delta claims so none of the discarded package controls is described as demonstrated or closed.

## 9. Evidence disposition

Durable evidence is this Git record plus the immutable R6 and R6-review Git objects. Disposable diagnostic evidence remains under `C:\Users\Trader\AppData\Local\Temp`:

- `r7_final_st_candidate.json` — SHA-256 `2d5f83494956f4124054e8791a2cdc0f528439c9cfa1194dc5c13857b21b5cf5`;
- `r7_final_st_fresh.json` — SHA-256 `134ec9a158a35407b0b6fae4c3dbb24e3ff84cb20f4ccdad63a276627e4292da`;
- `r7_final_sf_candidate.json` — SHA-256 `bf7933b1f11646d8975eea7f269ffd4f6d3681a7e551f2a3b9a4609caf19a0ee`;
- `r7_final_sf_fresh.json` — SHA-256 `6756e98529818c69006eb69ed8a516ba5c4c367f276df75c9aa29084edddd91a`;
- `r7_final_lt_candidate.json` — SHA-256 `fd3900a76fe8e00edb36205cf0ccbb4ec0e6e187968ac42e388d3d320ba4de8c`;
- `r7_final_lt_fresh.json` — SHA-256 `4a02ae436481c03735b6750cf06361d4d4a814f225098b84f5954a140a81fa71`;
- `r7_final_lf_candidate.json` — SHA-256 `400922d59e4355a59885ff954917bd9b4f2b83aedf760f8c4a74bd35570b82eb`;
- `r7_final_lf_fresh.json` — SHA-256 `2da9485e5e985ef9bd6dfa425f1e3133477a46a0b7f611bfec116edfc34f51be`.

The four disposable matrix worktrees and temporary build/probe scripts were removed. The validator environment and raw result receipts are not authority for any future run.

## 10. Continuing authorization state

- A production baseline capture is not authorized.
- Operational capture-script work is not authorized.
- Operational capture-package work is not authorized.
- Merge is not authorized.
- Canonical incorporation is not authorized.
- Production implementation is not authorized.
- Deployment is not authorized.
- Production restart is not authorized.
- Runtime migration is not authorized.
- NQ cutover is not authorized.
- Automated paper trading is not authorized.
- Live-money trading is not authorized.
- Phase 3C2 is not authorized.
- Phase 3C1-R11 acceptance is not authorized during this task.
- Bucket 0 remains incomplete.
- Bucket 1 remains blocked.

The exact next governed action is a separately authorized continuation remediation based directly on immutable R6 commit `87d066eb16d7fe0b6a1677ea7739c5c2ead4ad94`, consuming this incomplete record as external authority. No operational-package or baseline-capture authorization may be considered.

CURRENT PRODUCTION BASELINE CAPTURE BOUNDARY SPECIFICATION REMEDIATION R7 — INCOMPLETE
