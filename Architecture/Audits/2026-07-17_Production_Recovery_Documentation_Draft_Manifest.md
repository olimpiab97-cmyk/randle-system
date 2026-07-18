# 2026-07-17 Production Recovery - Documentation Draft Manifest

Status: **PHASE 3C1-R1 DRAFT PACKAGE INDEX - NONCANONICAL - NOT APPROVED**

Approval-Readiness Disposition: **F1-F8 REMEDIATED IN DRAFT - PENDING INDEPENDENT PHASE 3C1-R1 REVIEW; SEMANTIC TRACEABILITY DEFERRED TO PHASE 3C2**

## Phase 3C1-R1 active package

The Phase 3C1-R1 provenance commit is the exact byte-level identity for the active draft package. The following files are its authorized architecture/schema surfaces:

- `Architecture/Decisions/ADR-015_Listener_Lifecycle_Supervision_Epoch_Fencing_and_Restart_Cancellation.md` - unapproved;
- `Architecture/Decisions/ADR-016_Feed_Health_Authority_Durable_Publication_and_Bridge_Recycle_Control.md` - unapproved;
- `docs/architecture/runtime_authority_store_schema_DRAFT.md` - explanatory draft/noncanonical contract;
- `docs/architecture/runtime_authority_store_schema_v2_DRAFT.sql` - executable draft implementation reference, not production code;
- `docs/lifecycle/entry_session_rollover_contract_DRAFT.md` - draft support for approved ADR-014;
- `docs/architecture/production_startup_and_recovery_DRAFT.md` - draft/noncanonical;
- `Architecture/14_Randle_AI_Runtime_Recovery_Verification_Specification_DRAFT.md` - draft/noncanonical and not executed against production;
- `docs/architecture/diagnostic_endpoint_purity_contract_DRAFT.md` - draft/noncanonical; source-bound thirteen-route inventory unchanged;
- `Architecture/Audits/2026-07-17_ADR014_016_Canonical_Amendments_Draft.md` - proposal only, not applied;
- `Architecture/Audits/2026-07-17_ADR014_016_Cross_Document_Conflict_Matrix.md` - Phase 3C1-R1 draft disposition;
- `Architecture/Traceability/2026-07-17_Production_Recovery_Documentation_Traceability_Matrix.md` - package-level index only;
- `Architecture/Audits/2026-07-17_Approval_Remediation_Phase_3C1_R1_Redlines.md` - active targeted remediation record, not approval;
- `Architecture/Audits/2026-07-17_Approval_Remediation_Phase_3C1_Redlines.md` - superseded historical remediation record, not approval;
- `Architecture/Audits/2026-07-17_ADR015_016_Clause_Traceability_Registry_DRAFT.md` - historical rejected Phase 3B evidence; not approval-ready;
- this manifest, `Architecture/README.md`, and the directly affected blocking-debt records.

ADR-014 remains approved and unchanged. Its metadata-applied SHA-256 is `528B3C7099D63DB41C6B85E381EAD37AD1E479867C07934FD077EBBD8B5EC321`. The Runtime Authority Store proposal uses schema version 2 and an initial governed bootstrap; no approved predecessor artifact/hash was established. The provenance commit does not authorize approval, canonical incorporation, implementation, runtime verification, deployment, production `READY_LOCKED`, Bucket 0 completion, Bucket 1, or trading.

Semantic traceability is intentionally deferred. The historical Phase 3B registry does not prove substantive or structural completeness. Phase 3C2 may operate only on independently accepted Phase 3C1-R1 hashes.

### Phase 3C1-R1 executable identities

| Identity | Value |
|---|---|
| Runtime Authority Store schema version | `2` |
| SQL artifact SHA-256 | `fbc64af7bf9dc064e6a2e46172a253ea81d0d891ae2763c9cc65a74917fa8cc5` |
| Canonical schema hash | `10dab0b154fa34cabcbbf79ef3ef1966f6418e7e45a19543da2d6825aa260423` |
| Canonical writer-registry hash | `899bf56cbbae55068b136990c6baa1a01e4422da784119541089de9ecf3a3e28` |
| Executable inventory | 38 STRICT tables; 500 columns; 124 FK declarations/132 mappings; 13 partial unique indexes; 14 triggers; 60 active routes; 55 operations/52 commit types |

These hashes identify an unapproved draft only. The provenance commit hash is recorded after commit creation; it creates no approval or implementation authority.

## Historical pre-remediation identities

Historical Identity Notice: The hashes below identify the pre-remediation documentation draft set only. They SHALL NOT identify the Phase 3B package, establish a competing current version, or be used for approval. The Phase 3B remediation report and its document-only Git commit supply the next review identities. The listed combined listener-support draft is `WITHDRAWN — SUPERSEDED DRAFT`. The new Runtime Authority Store Schema and semantic clause/scenario/assertion registry are absent from this historical table and are identified only by the Phase 3B commit.

No listed artifact authorizes implementation, production restart, deployment, entry-lock clearing, or trading.

| Review artifact | Bytes | Lines | SHA-256 |
|---|---:|---:|---|
| `Architecture/Decisions/ADR-014_Authoritative_Entry_Session_Rollover_Transaction.md` | 17,304 | 291 | `500b3394892a5c07cb0bd57a5c564d8d0f10046601658024dde3b777db762605` |
| `Architecture/Decisions/ADR-015_Listener_Lifecycle_Supervision_Epoch_Fencing_and_Restart_Cancellation.md` | 17,493 | 293 | `661539465903ab26e437d416f0b1b333f11fbdcf79a89b7b253e6d4a3291ed03` |
| `Architecture/Decisions/ADR-016_Feed_Health_Authority_Durable_Publication_and_Bridge_Recycle_Control.md` | 15,878 | 269 | `e0a8cbb432392bbe790133c7a9dd737027a3a912706813a2c7ce0cc79a072883` |
| `Architecture/14_Randle_AI_Runtime_Recovery_Verification_Specification_DRAFT.md` | 14,417 | 334 | `d3b32328e1cce9c2f4bde442be2b0af70910e35928f6441275dfe8d61d64f2a7` |
| `docs/lifecycle/entry_session_rollover_contract_DRAFT.md` | 9,333 | 198 | `49e628800406ac16deb04b4a370b3a4ccc2e789b20829b50d6fdace70fe12ee5` |
| `docs/architecture/listener_supervision_and_health_authority_DRAFT.md` | 8,193 | 227 | `49dde0c858e4eb32f19d25a8499f086e70bece24fb0e0aa59870911ff1bc5778` |
| `docs/architecture/production_startup_and_recovery_DRAFT.md` | 9,810 | 186 | `5957f670ddac31a6d1046891c829d524125fb2aeabf1b53307920ffff2194f86` |
| `docs/architecture/diagnostic_endpoint_purity_contract_DRAFT.md` | 3,537 | 81 | `cd8f3b23c674c168cc4057a496df4ecd61193fb6e900f08352e9f64eceb6dafb` |
| `Architecture/Audits/2026-07-17_ADR014_016_Canonical_Amendments_Draft.md` | 22,111 | 364 | `c25b09e71765f210668bb9450607130d30df56a73fa3b6562ab1ff9071fc3571` |
| `Architecture/Audits/2026-07-17_ADR014_016_Cross_Document_Conflict_Matrix.md` | 15,239 | 107 | `345867a4b8f0939639d9787e4f4d4aed8ced5435c74710474915007c995220b9` |
| `Architecture/Traceability/2026-07-17_Production_Recovery_Documentation_Traceability_Matrix.md` | 14,117 | 127 | `2c2c544c2e0614e4d0b34b463b09b9c57bd9a6efe0d247611ca2ed64e57bb437` |
| `Architecture/Debt/Reviews/2026-07-17_Production_Recovery_Documentation_Phase_Debt_Reconciliation.md` | 2,395 | 48 | `91de7c17209ca89982d7027cb84bfefe071749c14f8bf0dd41fecf2c48866808` |

Evidence bundle aggregates remain governed by `Architecture/Audits/2026-07-17_Production_Recovery_Evidence_Baseline.md` and were reverified unchanged after drafting.
