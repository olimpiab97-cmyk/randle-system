# DEBT-2026-07-17-012 - Entry Session Rollover Atomicity

Unique Identifier: `DEBT-2026-07-17-012`
Date Introduced: `No later than the pre-2026-07-17 nontransactional receiver/canonical write flow; exact current-helper provenance is uncommitted and unresolved`
Date Discovered: `2026-07-17`
Discovery Source: `06:15 session-rollover fail-closed evidence and controlled diagnostic shutdown`
Primary Category: `Architectural Debt`
Secondary Categories: `Specification Debt`, `Implementation Debt`, `Test Debt`, `Operational Debt`, `Documentation Debt`, `Governance Debt`
Current Owner: `Entry Agent Session-Lock Authority Owner`
Current Status: `BLOCKING`
Risk Classification: `CRITICAL`
Deployment Impact: `BLOCKS_ALL - production startup, entry authorization, and live deployment`
Next Review Date: `2026-07-18`

## Canonical authority affected

Constitution sections 6, 12, 14-17, and 22; ADR-012; Runtime Authority sections 4-5; Session Liquidity Lock Contract.

## Root cause

The normal current-session payload is tested for an explicit sender lock before the receiver constructs its canonical lock. Raw receiver state advances unconditionally while canonical replacement is conditional. A separate Rithmic-driven observation reset latch can advance the session before the lock exists, and persistence can retain the truthy prior-session lock. No crash-consistent session-transition record joins these facts.

## Required resolution

ADR-014 approval is complete. The remaining resolution SHALL approve and canonically incorporate the required specification changes through their own governed actions; implement one validate-build-commit-expose session transaction; preserve prior history inactive; make duplicate/crash recovery idempotent; and verify NQ/YM current-session parity.

The Entry Session Rollover Contract SHALL align its complete state set and place active-pointer/prior-session retirement inside the durable commit rather than after durable success. The canonical amendment and runtime verification drafts SHALL encode the accepted TradingView trust boundary and exact rollover ordering before coordinated promotion.

## Exit criteria

1. One approved session-rollover authority and sequence exist.
2. Raw/current projection cannot advance before canonical commit.
3. Observation reset and lock installation share one transition identity.
4. Valid lock replaces prior active state exactly once; invalid lock remains fail-closed.
5. Crash/restart and duplicate replay pass for NQ and YM.
6. Traceability and all five gates pass.
7. Explicit deployment authorization is recorded.

## Status history

| Date | From | To | Actor | Reason and evidence |
|---|---|---|---|---|
| 2026-07-17 | - | BLOCKING | Architecture Governance Owner | Preserved evidence proves raw July 17 session state diverged from canonical July 16 state |
| 2026-07-17 | BLOCKING | BLOCKING (documentation drafted) | Architecture Governance Owner | ADR-014, Entry Session Rollover Contract, coordinated amendments, verification specification, conflict matrix, and bidirectional traceability drafted but not approved or implemented |
| 2026-07-17 | BLOCKING | BLOCKING (approval review) | Architecture Governance Owner | ADR-014 received an APPROVE recommendation, but the Entry contract, runtime verification specification, and canonical amendment ledger were rejected for blocking session-state/ordering/reconciliation gaps; no document was marked approved |
| 2026-07-17 | BLOCKING | BLOCKING (Phase 1 remediation drafted) | Architecture Governance Owner | Atomic activation/prior-retirement, sole writer, store failure states, verification, amendment, and conflict redlines drafted; pending coordinated approval review and all later gates |
| 2026-07-17 | BLOCKING | BLOCKING (ADR-014 approved) | Architecture Governance Owner | Formal user approval applied to ADR-014 only, bound to SHA-256 `BD76D1B398515EA00E230B9C8A00A540344E061A36B228BF112F784F6AC34F25`; supporting specifications, canonical incorporation, implementation, runtime verification, deployment, `READY_LOCKED`, and trading remain incomplete or unauthorized |
| 2026-07-18 | BLOCKING | BLOCKING (Phase 3C1 normative remediation drafted) | Architecture Governance Owner | The support contract now enumerates exact destinations for all twelve states and exact degraded/corrupt recovery classifications while preserving Session-lock policy decision authority and the sole Entry Agent Session Commit Writer. Pending independent Phase 3C1 review; semantic traceability is deferred to Phase 3C2; no implementation, verification, deployment, or debt retirement occurred. |

## Traceability

- Approved ADR: `Architecture/Decisions/ADR-014_Authoritative_Entry_Session_Rollover_Transaction.md` (approval bound to SHA-256 `BD76D1B398515EA00E230B9C8A00A540344E061A36B228BF112F784F6AC34F25`)
- Draft contract: `docs/lifecycle/entry_session_rollover_contract_DRAFT.md`
- Matrix: `Architecture/Traceability/2026-07-17_Production_Recovery_Documentation_Traceability_Matrix.md`
- Verification draft: `Architecture/14_Randle_AI_Runtime_Recovery_Verification_Specification_DRAFT.md`
- Phase 3C1 redline: `Architecture/Audits/2026-07-17_Approval_Remediation_Phase_3C1_Redlines.md`

## Retirement evidence

None.
