# DEBT-2026-07-17-013 - Listener Supervision Recovery Race

Unique Identifier: `DEBT-2026-07-17-013`
Date Introduced: `2026-05-07 baseline watchdog/restart units`
Date Discovered: `2026-07-17`
Discovery Source: `Controlled diagnostic shutdown process lineage and Executor logs`
Primary Category: `Architectural Debt`
Secondary Categories: `Specification Debt`, `Implementation Debt`, `Test Debt`, `Operational Debt`, `Documentation Debt`, `Governance Debt`
Current Owner: `Listener Supervision Policy Owner`
Current Status: `BLOCKING`
Risk Classification: `CRITICAL`
Deployment Impact: `BLOCKS_ALL - production listener startup, runtime recovery, entry authorization, and live deployment`
Next Review Date: `2026-07-18`

## Canonical authority affected

Constitution sections 6, 12, 16-17, and 22; ADR-012; Runtime Authority sections 1, 3, and 5.

## Root cause

Executor is the accidental listener process supervisor. The accepted-tick worker calls a mutating stale/restart builder before committing the accepted tick to watchdog state. Restart is level-triggered and memory-debounced, with no durable incident latch, pending cancellation, or epoch fence. Debug GETs and an entry safety read share the mutating path.

## Required resolution

Approve ADR-015; assign one Listener Supervisor; remove direct restart from Executor/read paths; define commit-before-evaluate recovery, cancellation, fencing, persistent exactly-one behavior, listener epoch, bridge generation, and ATR/downstream rehydration.

The approved architecture must also bind production topology and every shared-feed threshold to the versioned/digest-authorized policy owned by `Listener Supervision Policy Owner`, distinguish per-symbol degradation from bridge recycle and full-listener restart, and enforce debounce, recovery cancellation, cooldown, maximum restart rate, and fail-closed escalation.

Before approval, ADR-015 SHALL prohibit the attempt that would exceed the bridge maximum, replace circular SFF-02 fence corroboration with independent predecision evidence, define the market-data-expected input authority, and make every ATR invalidation reason-to-state disposition deterministic. The supporting listener, verification, and amendment drafts SHALL carry the complete supervisor-generation/request/store/policy contracts without weakened projection or durability language.

## Exit criteria

1. The supervisor owner and state machine are canonical.
2. A committed fresh same-epoch tick cancels an unfenced pending restart.
3. A genuinely stale listener causes exactly one fenced epoch transition.
4. GET/read/order-check paths cannot mutate process lifecycle.
5. Debounce/latch survives component restart.
6. Cold/manual integration and ATR epoch tests pass.
7. Policy schema/default/range/digest tests, `SFF-01` through `SFF-03`, cancellation, cooldown, rate-limit, and repeated-recovery escalation pass.
8. Traceability and all five gates pass.
9. Explicit deployment authorization is recorded.

## Status history

| Date | From | To | Actor | Reason and evidence |
|---|---|---|---|---|
| 2026-07-17 | - | BLOCKING | Architecture Governance Owner | Executor PID 13768 terminated two recovered listener instances and created new authority epochs |
| 2026-07-17 | BLOCKING | BLOCKING (documentation drafted) | Architecture Governance Owner | ADR-015, supervisor/startup/diagnostic contracts, coordinated amendments, verification specification, conflict matrix, and traceability drafted but not approved or implemented |
| 2026-07-17 | BLOCKING | BLOCKING (architecture question resolved in draft) | Architecture Governance Owner | NQ/YM shared physical-feed topology, sole declaration authority, governed policy schema/owner/defaults/ranges/digest, closed full-restart predicates, debounce/cancellation/cooldown/rate-limit/escalation were added to unapproved ADR-015 |
| 2026-07-17 | BLOCKING | BLOCKING (approval review rejected) | Architecture Governance Owner | ADR-015 and its supporting listener/verification/amendment drafts were rejected for rate-limit, SFF corroboration, market-data-expected authority, deterministic ATR, and schema/ownership reconciliation defects |
| 2026-07-17 | BLOCKING | BLOCKING (Phase 1 remediation drafted) | Architecture Governance Owner | Pre-execution maximum enforcement, acyclic SFF-02 evidence, named market-expectation authority, closed ATR matrix, and mirror reconciliations drafted; pending approval review and implementation/verification |
| 2026-07-17 | BLOCKING | BLOCKING (Phase 3A remediation drafted) | Architecture Governance Owner | Closed listener/incident vocabulary, distinct full-listener rate-limit outcome, policy-validation disposition, implementable one-database identity design, and clause-level traceability drafted; pending independent approval and all later gates |
| 2026-07-17 | BLOCKING | BLOCKING (Phase 3A approval rejected; Phase 3B remediation pending review) | Architecture Governance Owner | Phase 3A did not contain an implementable complete Runtime Authority Store schema or semantic clause/scenario/assertion traceability. Phase 3B adds a draft exact schema, writer routing, typed listener transactions, store-bound startup proofs, and semantic mappings; none is approved, canonical, implemented, or verified. |
| 2026-07-18 | BLOCKING | BLOCKING (Phase 3C1 normative remediation drafted) | Architecture Governance Owner | Executable v2 `STRICT` DDL, exclusive writer routing, exact listener state/incident/acknowledgement ownership, `TX-LSN-STOP-COMPLETE`, deterministic rate exhaustion, separate operation envelopes, and startup proofs were corrected in draft. Pending independent Phase 3C1 review; semantic traceability is deferred to Phase 3C2; no authority, implementation, verification, or deployment was granted. |
| 2026-07-18 | BLOCKING | BLOCKING (Phase 3C1-R1 targeted remediation drafted) | Architecture Governance Owner | F1-F5/F8 listener-facing gaps were corrected in draft: exact calendar checks, governed writer succession, cancellation-only `SUSPECT` self-edge, complete supervisor/lease/epoch/start operation coverage, terminal incident/outcome identity, and explicit post-replacement baseline/version. Pending independent Phase 3C1-R1 review; no canonical, implementation, runtime, deployment, or trading authority was granted. |

## Traceability

- Draft ADR: `Architecture/Decisions/ADR-015_Listener_Lifecycle_Supervision_Epoch_Fencing_and_Restart_Cancellation.md`
- Active draft startup/purity contracts: `docs/architecture/production_startup_and_recovery_DRAFT.md` and `docs/architecture/diagnostic_endpoint_purity_contract_DRAFT.md`
- Withdrawn historical draft, not authority or implementation input: `docs/architecture/listener_supervision_and_health_authority_DRAFT.md`
- Historical rejected Phase 3B clause registry: `Architecture/Audits/2026-07-17_ADR015_016_Clause_Traceability_Registry_DRAFT.md`
- Phase 3C1-R1 Store Schema and executable reference: `docs/architecture/runtime_authority_store_schema_DRAFT.md`, `docs/architecture/runtime_authority_store_schema_v2_DRAFT.sql`
- Active Phase 3C1-R1 redline: `Architecture/Audits/2026-07-17_Approval_Remediation_Phase_3C1_R1_Redlines.md`
- Superseded historical Phase 3C1 redline: `Architecture/Audits/2026-07-17_Approval_Remediation_Phase_3C1_Redlines.md`
- Matrix: `Architecture/Traceability/2026-07-17_Production_Recovery_Documentation_Traceability_Matrix.md`
- Verification draft: `Architecture/14_Randle_AI_Runtime_Recovery_Verification_Specification_DRAFT.md`

## Retirement evidence

None.
