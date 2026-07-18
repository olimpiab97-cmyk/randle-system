# DEBT-2026-07-17-016 - Unauthenticated TradingView Webhook Sender

Unique Identifier: `DEBT-2026-07-17-016`
Date Introduced: `UNKNOWN - present in the production public webhook path by 2026-07-17`
Date Discovered: `2026-07-17`
Discovery Source: `ADR-014 and production-startup substantive architecture closure review`
Primary Category: `Architectural Debt`
Secondary Categories: `Specification Debt`, `Implementation Debt`, `Verification Debt`, `Operational Debt`, `Documentation Debt`, `Governance Debt`
Current Owner: `TradingView Ingress Security Owner`
Current Status: `BLOCKING`
Risk Classification: `CRITICAL`
Deployment Impact: `BLOCKS_ALL - public TradingView production readiness, current-session candidate commitment, entry authorization, and live deployment`
Next Review Date: `2026-07-18`

## Canonical authority affected

Constitution sections 3, 6, 12-16, 20, and 22; TradingView Webhook Contract sections 4, 7, and 11; approved ADR-014 section 3.4.1; proposed Production Startup, Recovery, and Readiness Contract sections 6 and 10.

## Root cause

The production public webhook path accepts JSON through Ngrok and Trade Manager relay without a governed authenticated sender principal or a cryptographic binding among sender identity, exact payload bytes, freshness, and replay evidence. Route metadata, TLS to the public hostname, `Host`, source address, user-agent, receipt time, sender-provided timestamp/session fields, `locked=true`, and payload hash do not authenticate the sender.

The existing lock/merge behavior can limit some duplicate effects after an accepted lock, but it does not prove who submitted the first candidate and does not supply sender-bound nonce/replay authority. A payload timestamp/session identity may also be absent and replaced with receiver observation time.

## Current implementation status

`Engines/trade_manager.py` accepts `/webhook/tv-context` JSON, records route/request metadata, and forwards the payload locally. `EntryAgent/tv_context_server.py` validates and persists content but performs no signature, authenticated-principal, nonce, or sender-bound replay verification. Preserved 2026-07-17 relay evidence records an Ngrok host and `TradingView Webhook` user-agent, which proves neither sender identity nor cryptographic payload provenance.

## Affected completion gates

- Architecture: sender-authentication authority and trust boundary are not canonically selected.
- Specification: no approved identity/freshness/replay contract exists.
- Implementation: no conforming authentication mechanism exists.
- Verification: no valid/invalid/replay/key-rotation/failure suite exists.
- Traceability: mechanism-to-authority-to-test mapping cannot complete until the security decision exists.

## Dependencies

ADR-014 is approved for internal session transaction atomicity without selecting the security mechanism. Production startup and candidate commitment remain blocked until a separate security Architecture Impact Assessment and decision define the authenticated sender, supported TradingView capabilities/constraints, key or credential custody, freshness/replay semantics, failure behavior, rotation/revocation, operational recovery, and exact deployment boundary.

## Required resolution

1. Establish the external sender and public-ingress threat/trust model from evidence.
2. Determine actual TradingView webhook authentication capabilities without inventing unsupported behavior.
3. Approve a separate security architecture and canonical contract that binds an authenticated sender principal to exact payload bytes, intended session, freshness, and replay identity.
4. Preserve route traversal, payload/session eligibility, and sender authentication as three distinct facts.
5. Implement fail-closed validation before ADR-014 production candidate commitment.
6. Make startup positively prove the approved authentication result; unavailable/failed/ambiguous validation remains terminal `FAILED`.
7. Verify spoofing, replay, duplicate, missing/stale/future timestamp, payload alteration, credential rotation/revocation, authority unavailability, and audit-redaction behavior.

## Exit criteria

1. The sender-authentication authority and mechanism are approved in a separate governed security decision.
2. The TradingView Webhook Contract and startup/readiness authority are approved and unambiguous.
3. Production implementation validates sender identity, exact payload integrity, freshness/intended session, and replay before candidate commitment.
4. Negative/rotation/recovery tests and real public-route integration pass.
5. Bidirectional traceability and all five completion gates pass.
6. Explicit deployment authorization records exact security artifact/config identities.

## Status history

| Date | From | To | Actor | Reason and evidence |
|---|---|---|---|---|
| 2026-07-17 | - | BLOCKING | Architecture Governance Owner | Production trust-boundary review confirmed public route and payload validation but no authenticated sender identity or sender-bound replay proof |
| 2026-07-17 | BLOCKING | BLOCKING (approval review) | Architecture Governance Owner | ADR-014's route/content/sender separation received an APPROVE recommendation without inventing a mechanism; startup, verification, and amendment drafts remain rejected/incomplete and production commitment/READY/deployment/trading remain prohibited |
| 2026-07-17 | BLOCKING | BLOCKING (ADR-014 approved) | Architecture Governance Owner | Formal ADR-014 approval was applied at the approved content hash; no sender-authentication mechanism was approved and this debt continues to block production candidate commitment, deployment, `READY_LOCKED`, and trading |
| 2026-07-18 | BLOCKING | BLOCKING (Phase 3C1 supporting drafts reconciled) | Architecture Governance Owner | Phase 3C1 preserved ADR-014 ownership and the startup fail-closed sender-authority gate while remediating only runtime-authority schema/specification defects. No authentication mechanism was selected; semantic traceability is deferred to Phase 3C2; this debt remains fully blocking. |

## Traceability

- Approved transaction decision: `Architecture/Decisions/ADR-014_Authoritative_Entry_Session_Rollover_Transaction.md`
- Draft lifecycle contract: `docs/lifecycle/entry_session_rollover_contract_DRAFT.md`
- Draft startup contract: `docs/architecture/production_startup_and_recovery_DRAFT.md`
- Conflict matrix: `Architecture/Audits/2026-07-17_ADR014_016_Cross_Document_Conflict_Matrix.md`
- Traceability matrix: `Architecture/Traceability/2026-07-17_Production_Recovery_Documentation_Traceability_Matrix.md`
- Phase 3C1 redline: `Architecture/Audits/2026-07-17_Approval_Remediation_Phase_3C1_Redlines.md`
- Production ingress units: `Engines/trade_manager.py`, `EntryAgent/tv_context_server.py`

## Approval

None. No deferral, acceptance, mechanism, or deployment exception is approved.

## Retirement evidence

None.
