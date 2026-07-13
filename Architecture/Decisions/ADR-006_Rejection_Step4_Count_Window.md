# ADR-006: Rejection Step 4 Count Window

## Status

APPROVED

## Date

2026-07-10

## Purpose

ADR-010 Narrow Amendment Record: Effective 2026-07-13, every Count Window candle source in the Rejection-to-Continuation chain is an authoritative completed one-minute candle from the canonical one-minute series. This does not change Count indexing, Count Window length, retry behavior, expiration, terminal behavior, or any other ADR-006 decision.

ADR-011 Relationship Record: ADR-011 separately governs the Continuation Count 0 and Count 1 through Count 4 Window after Continuation Step 2 Confirmation. It does not extend, replace, or otherwise alter this ADR's Rejection Count Window.

This Architecture Decision Record establishes the authoritative Rejection Step 4 Count-window trading rule. It records the approved decision only; it is not a trading-rule implementation and does not modify code, tests, runtime state, or an existing specification.

## Evidence Basis

This decision is based only on:

- `Architecture/Audits/01_Randle_AI_Current_Production_Ground_Truth_Audit.md`;
- `Architecture/Audits/02_Randle_AI_Rejection_Lifecycle_Migration_Review.md`;
- the completed Phase 1.1 Rejection Step 4 Count-window determination report.

No additional behavior is inferred or approved by this ADR.

## Decision

### Count 0

Count 0 is the Rejection Step 2 confirmation candle.

It initializes Step 4.

It performs no Step 4 evaluation.

### Count 1

Count 1 is the first eligible completed-candle evaluation.

It may confirm Step 4.

### Count 2

Count 2 is an eligible evaluation.

It may confirm Step 4.

### Count 3

Count 3 is an eligible evaluation.

It may confirm Step 4.

### Count 4

Count 4 is the final eligible evaluation.

It may confirm Step 4.

Failure to confirm by completion of Count 4 terminates the Step 4 window.

### Count 5+

Count 5 or later is not part of the authorized trading rule.

Any Count 5+ behavior is implementation behavior only and SHALL NOT become canonical without a future ADR.

## Retry Rule

Counts 1 through 3 remain retryable unless an independently authorized terminal invalidation occurs.

Count 4 is terminal.

## Window Rule

The Step 4 window is permanently tied to the original Rejection Step 2 confirmation event.

The window never resets.

## Deferred Decision

Normal Rejection Participation Candle A Replacement is explicitly deferred.

It remains unresolved and requires a separate ADR before becoming canonical.

## Out of Scope

This ADR does not determine:

- continuation lifecycle behavior;
- persistence;
- replay;
- restart;
- session behavior;
- contract behavior;
- implementation architecture.

## Authority

This ADR authorizes revision of `Architecture/04_Randle_AI_Rejection_Step4_Lifecycle_Specification_DRAFT.md` to align with the approved Count-window rule while leaving Normal Rejection Participation Candle A Replacement unresolved.

It authorizes future specification updates only. It does not authorize implementation changes.
