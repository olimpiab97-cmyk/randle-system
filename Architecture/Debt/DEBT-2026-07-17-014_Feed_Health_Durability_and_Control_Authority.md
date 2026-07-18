# DEBT-2026-07-17-014 - Feed Health Durability and Control Authority

Unique Identifier: `DEBT-2026-07-17-014`
Date Introduced: `2026-05-07 baseline pending-clear and projection-driven watchdog units; current swallowed-write wrapper is uncommitted`
Date Discovered: `2026-07-17`
Discovery Source: `Controlled diagnostic shutdown listener, bridge, and feed-health evidence`
Primary Category: `Architectural Debt`
Secondary Categories: `Specification Debt`, `Implementation Debt`, `Test Debt`, `Operational Debt`, `Documentation Debt`, `Governance Debt`
Current Owner: `Rithmic Runtime Health and Bridge Authority Owner`
Current Status: `BLOCKING`
Risk Classification: `CRITICAL`
Deployment Impact: `BLOCKS_ALL - production feed startup, bridge recycling, listener recovery, entry authorization, and live deployment`
Next Review Date: `2026-07-18`

## Canonical authority affected

Constitution sections 3.1, 6, 12, 16-17, and 22; ADR-012; Runtime Authority sections 1-3.

## Root cause

Several writers update one shared JSON projection, whose configured path is under OneDrive, without serialization. Windows denied atomic replacement with WinError 5. The writer swallowed failure; TickWorker cleared pending state before knowing the result; the listener reread stale persisted projection as live control authority and terminated a bridge receiving current data.

The failed atomic replacement operation is proven. The identity of the Windows process holding the conflicting handle was not captured. The path alone does not establish that OneDrive or any other process caused the denial.

## Required resolution

Approve ADR-016; establish direct current-epoch health authority, one local durable writer, explicit success/failure, pending retention, bounded retry, asynchronous OneDrive projection, and direct-evidence bridge recycle with epoch/generation fencing.

The architecture must preserve raw documented RAPI callbacks and exact process/intent evidence, classify every unsupported or ambiguous dimension as field-specific `UNKNOWN`, prohibit process-disappearance inference, and define verified quarantine, approved restoration sources, no-source fail-closed recovery, epoch/generation preservation, versioned staged migration, rollback boundary, and recovery audit.

Before approval, ADR-016 SHALL separate or deterministically prioritize terminal initiator/action/execution/cause dimensions and SHALL exclude matching planned shutdown/transition intent from BDP-01. Supporting specifications SHALL prohibit projection participation in control even as supplemental evidence, use the exact SQLite transaction contract/fact names, and verify the full governed restoration/migration matrix.

## Exit criteria

1. Health authority hierarchy and durable contract are canonical.
2. WinError 5 never clears pending state or advances durable sequence.
3. Stale projection cannot kill a demonstrably live bridge.
4. Legitimate bridge failure causes exactly one bridge-only recycle.
5. Bridge recycle and full listener epoch transition have distinct ATR/readiness effects.
6. Sharing-violation cause is deterministically reproduced/bounded in nonproduction.
7. Every five-field RAPI termination value and field-specific `UNKNOWN` conservative action passes evidence-correlation tests.
8. Corruption/quarantine/restore/reinitialize/migrate/rollback/audit startup cases pass without projection fallback.
9. Cold/manual integration, traceability, and all five gates pass.
10. Explicit deployment authorization is recorded.

## Status history

| Date | From | To | Actor | Reason and evidence |
|---|---|---|---|---|
| 2026-07-17 | - | BLOCKING | Architecture Governance Owner | Repeated failed health persistence caused stale-projection bridge termination |
| 2026-07-17 | BLOCKING | BLOCKING (documentation drafted) | Architecture Governance Owner | ADR-016, durable health/bridge/startup/diagnostic contracts, coordinated amendments, verification specification, conflict matrix, and traceability drafted but not approved or implemented |
| 2026-07-17 | BLOCKING | BLOCKING (architecture questions resolved in draft) | Architecture Governance Owner | Evidence-bounded RAPI terminal taxonomy with explicit UNKNOWN and fully specified corrupt-store quarantine/restoration/migration/startup behavior were added to unapproved ADR-016/startup drafts |
| 2026-07-17 | BLOCKING | BLOCKING (approval review rejected) | Architecture Governance Owner | ADR-016 and its supporting listener/startup/verification/amendment drafts were rejected for overlapping terminal classification, BDP-01 planned-intent conflict, weakened projection control language, obsolete fact names, and incomplete governed recovery verification |
| 2026-07-17 | BLOCKING | BLOCKING (Phase 1 remediation drafted) | Architecture Governance Owner | Five-field termination model, unexpected-only BDP-01, absolute projection isolation, SQLite/control ownership mirrors, current readiness facts, and recovery verification drafted; pending approval review and implementation/verification |
| 2026-07-17 | BLOCKING | BLOCKING (Phase 3A remediation drafted) | Architecture Governance Owner | Complete orthogonal health-state machines, one physical runtime-authority database with separated logical writers, producer/evaluator/writer roles, and clause-level traceability drafted; pending independent approval and all later gates |
| 2026-07-17 | BLOCKING | BLOCKING (Phase 3A approval rejected; Phase 3B remediation pending review) | Architecture Governance Owner | Phase 3A's database description did not define all tables, keys, acknowledgement/current-state records, typed cross-writer transactions, crash/reconstruction behavior, or semantic verification mappings. Phase 3B proposes those contracts in a new draft store schema; no implementation or conformance is claimed. |
| 2026-07-18 | BLOCKING | BLOCKING (Phase 3C1 normative remediation drafted) | Architecture Governance Owner | The v2 executable schema, recovery-evidence writer, initial-bootstrap/quarantine contract, separate operation envelopes, subscription-only durable record, Bridge Generation Writer ownership, and exact startup evidence were corrected in draft. Pending independent Phase 3C1 review; semantic traceability is deferred to Phase 3C2; no runtime verification or production change occurred. |

## Traceability

- Draft ADR: `Architecture/Decisions/ADR-016_Feed_Health_Authority_Durable_Publication_and_Bridge_Recycle_Control.md`
- Active draft runtime contracts: `docs/architecture/production_startup_and_recovery_DRAFT.md` and `docs/architecture/diagnostic_endpoint_purity_contract_DRAFT.md`
- Withdrawn historical draft, not authority or implementation input: `docs/architecture/listener_supervision_and_health_authority_DRAFT.md`
- Historical rejected Phase 3B clause registry: `Architecture/Audits/2026-07-17_ADR015_016_Clause_Traceability_Registry_DRAFT.md`
- Phase 3C1 Store Schema and executable reference: `docs/architecture/runtime_authority_store_schema_DRAFT.md`, `docs/architecture/runtime_authority_store_schema_v2_DRAFT.sql`
- Phase 3C1 redline: `Architecture/Audits/2026-07-17_Approval_Remediation_Phase_3C1_Redlines.md`
- Matrix: `Architecture/Traceability/2026-07-17_Production_Recovery_Documentation_Traceability_Matrix.md`
- Verification draft: `Architecture/14_Randle_AI_Runtime_Recovery_Verification_Specification_DRAFT.md`

## Retirement evidence

None.
