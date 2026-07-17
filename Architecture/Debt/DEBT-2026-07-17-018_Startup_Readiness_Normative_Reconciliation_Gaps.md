# DEBT-2026-07-17-018 - Startup Readiness Normative Reconciliation Gaps

Unique Identifier: `DEBT-2026-07-17-018`
Date Introduced: `2026-07-17 startup/readiness draft`
Date Discovered: `2026-07-17`
Discovery Source: `Coordinated authority-package approval review`
Primary Category: `Specification Debt`
Secondary Categories: `Architectural Debt`, `Verification Debt`, `Documentation Debt`, `Governance Debt`
Current Owner: `Production Startup and Readiness Architecture Owner`
Current Status: `BLOCKING`
Risk Classification: `CRITICAL`
Deployment Impact: `BLOCKS_ALL - startup contract approval, production READY, restart, deployment, and trading readiness`
Next Review Date: `2026-07-18`

## Canonical authority affected

Constitution sections 6, 12-17, 20, and 22; approved ADR-014; proposed ADR-015 and ADR-016; Architecture Debt Specification sections 3, 6, and 8; proposed Production Startup, Recovery, and Readiness Contract sections 6 and 11.

## Root cause

The startup draft was updated incrementally after the ADR-016 evidence schema and DEBT-016 boundary changed. It still names obsolete direct fact types, does not contain a positive versioned gate proving zero applicable Blocking debt, and conflates Executor reconciliation/entry blocking with a positive nontrading Executor authority-ready state.

## Current specification status

- `RITHMIC_CONNECTED` names `CONNECTION_UP`/`LOGIN_UP`, while ADR-016 defines raw `RAPI_ALERT_OBSERVED` and derived committed `connection=UP`/`login=UP`.
- `SYMBOLS_SUBSCRIBED` names `SUBSCRIPTION_ACTIVE`, while ADR-016 defines `SUBSCRIPTION_VERIFIED`.
- `STARTUP_READY_LOCKED` says “no blocker” without a debt-registry authority, applicability decision, version/hash, review date, or zero-Blocking proof.
- `EXECUTOR_RECONCILED_LOCKED` proves reconciliation/entry block but not a distinct current-build/config/epoch/command-authority readiness grant.

## Affected completion gates

- Architecture: readiness authority and debt applicability owner are incomplete.
- Specification: fact names and terminal READY proof conflict with governing drafts.
- Verification: positive/negative cases cannot target one canonical schema.
- Traceability: startup rows do not map to exact ADR-016 facts or debt authority.

## Required resolution

1. Replace obsolete health fact names with the exact accepted raw, derived, and durable ADR-016 identities.
2. Add a mandatory governance readiness row naming the Debt Registry authority, applicability review owner, registry/version/hash, review time, and zero applicable `BLOCKING` result.
3. Add an explicit nontrading Executor authority-ready state distinct from flat/reconciled/entry-locked and from later `TRADING_PERMITTED`.
4. Define the session-calendar/market-data-expected authority consumed by startup and ADR-015.
5. Extend terminal READY/FAILED evidence and runtime recovery tests for all new rows.
6. Preserve DEBT-016 as independently blocking: the corrected contract may be approved, but current production cannot reach READY without authenticated sender authority.

## Exit criteria

1. Startup specification uses only current approved authority/fact names.
2. READY requires positive same-session/same-epoch evidence, explicit Executor authority, and zero applicable Blocking debt.
3. DEBT-016 unavailable/failed behavior remains terminal FAILED.
4. Every positive/negative/deadline case passes in isolated cold/manual startup.
5. Traceability and all five gates pass.

## Status history

| Date | From | To | Actor | Reason and evidence |
|---|---|---|---|---|
| 2026-07-17 | - | BLOCKING | Architecture Governance Owner | Approval review found obsolete ADR-016 readiness facts and missing debt/Executor authority gates |
| 2026-07-17 | BLOCKING | BLOCKING (Phase 1 remediation drafted) | Architecture Governance Owner | Startup draft now uses current RAPI/subscription terminology and adds zero-blocking-debt, Executor/Supervisor, epoch/session, canonical ATR/frozen-ladder, market expectation, and sender-authentication gates; DEBT-016 explicitly prevents READY |
| 2026-07-17 | BLOCKING | BLOCKING (ADR-014 approved) | Architecture Governance Owner | ADR-014 is now an approved governing dependency; ADR-015, ADR-016, the startup specification, implementation, verification, deployment, and production `READY_LOCKED` remain unapproved, incomplete, or unauthorized |

## Traceability

- Review: `Architecture/Audits/2026-07-17_Coordinated_Authority_Package_Approval_Review.md`
- Draft startup contract: `docs/architecture/production_startup_and_recovery_DRAFT.md`
- Approved ADR: `Architecture/Decisions/ADR-014_Authoritative_Entry_Session_Rollover_Transaction.md`
- Draft ADRs: `Architecture/Decisions/ADR-015_Listener_Lifecycle_Supervision_Epoch_Fencing_and_Restart_Cancellation.md`, `Architecture/Decisions/ADR-016_Feed_Health_Authority_Durable_Publication_and_Bridge_Recycle_Control.md`
- Verification draft: `Architecture/14_Randle_AI_Runtime_Recovery_Verification_Specification_DRAFT.md`

## Approval

None.

## Retirement evidence

None.
