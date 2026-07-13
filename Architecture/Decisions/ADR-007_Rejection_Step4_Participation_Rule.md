# ADR-007: Rejection Step 4 Participation Rule

## Status

APPROVED

## Date

2026-07-10

## Purpose

ADR-010 Narrow Amendment Record: Effective 2026-07-13, the current and immediately previous Participation candle sources in the Rejection-to-Continuation chain are authoritative completed one-minute candles from the canonical one-minute series. This does not change Participation predicates, wick requirements, direction-specific close requirements, or any other ADR-007 decision.

This Architecture Decision Record establishes the authoritative Rejection Step 4 participation timing and confirmation rule. It replaces legacy Candle A / Candle B terminology with a direct Count-and-Participation rule and records an architecture decision only; it is not a trading-rule implementation.

## Governing Decision

1. Rejection Step 2 confirmation is Count 0.
2. Count 0 initializes the Rejection Step 4 window.
3. Count 0 does not evaluate Step 4 participation.
4. The system then receives exactly four additional completed-candle opportunities:
   - Count 1
   - Count 2
   - Count 3
   - Count 4
5. Any Count 1 through Count 4 may confirm Rejection Step 4.
6. Each candidate candle is evaluated relative to the immediately previous completed candle.
7. Participation for a SHORT rejection is satisfied when either:
   - the current candle has at least 34% wick participation under the existing wick-participation formula; or
   - the current candle closes lower than the immediately previous candle.
8. Participation for a LONG rejection is satisfied when either:
   - the current candle has at least 34% wick participation under the existing wick-participation formula; or
   - the current candle closes higher than the immediately previous candle.
9. If participation is not satisfied at Counts 1, 2, or 3, the lifecycle remains eligible for the next count unless an independently authorized terminal invalidation occurs.
10. Count 4 is the final eligible evaluation.
11. If Step 4 has not confirmed by the completion of Count 4, the Rejection Step 4 window terminates.
12. Count 5 or later is not permitted within the same Rejection Step 4 window.
13. The original Count 0 identity and four-candle window never restart.

## Terminology Decision

- Candle A and Candle B are legacy implementation terms.
- Candle A and Candle B are not required as governing Rejection Step 4 lifecycle concepts.
- The canonical architecture shall instead use:
  - Count 0;
  - Count 1 through Count 4;
  - immediately previous completed candle;
  - current candidate candle;
  - participation;
  - Step 4 confirmation;
  - terminal Step 4 window.

This ADR does not define a rolling or immutable Candle A rule and does not preserve a Candle A replacement decision. That issue is eliminated from the canonical architecture by expressing the rule directly.

## Scope

This ADR governs only Rejection Step 4 participation timing and confirmation.

It does not define:

- continuation lifecycle behavior;
- Step 5 or Step 6;
- persistence;
- replay architecture;
- restart behavior;
- session rollover;
- contract rollover;
- execution;
- risk management.

## Authority

This ADR:

- supersedes any proposed ADR-007 text based on immutable or rolling Candle A;
- authorizes revision of `Architecture/04_Randle_AI_Rejection_Step4_Lifecycle_Specification_DRAFT.md` where necessary to remove Candle A / Candle B as governing Rejection Step 4 concepts and align the draft with this decision;
- authorizes revision of `Architecture/01_Randle_AI_Lifecycle_Vocabulary.md` where necessary to remove Candle A / Candle B as governing Rejection Step 4 concepts and align the vocabulary with this decision;
- does not authorize code or test changes.

No implementation change is authorized by this ADR.
