Randle AI Rejection Step 4 Lifecycle Specification
Version: 2.0
Document Type: Specialized Lifecycle Specification
Status: Draft — Not Canonical
Authority: Draft; it does not occupy the canonical authority order. Any approved successor would be subordinate to the Randle AI Constitution, Lifecycle Vocabulary, and Lifecycle Engine Specification.

IMPORTANT: This document is not canonical. The Step 4 Count-window, Candle A replacement, retry behavior, terminal window, corrected-candle policy, out-of-order policy, session rollover policy, and contract rollover policy remain unresolved. This document must not be used to authorize implementation changes until those rules are formally decided and this specification is explicitly approved.

1. Purpose
This draft describes the proposed architectural placement of Rejection Step 4 as a phase within one Rejection Lifecycle. It covers:
same-lifecycle ownership;
the exact Step 2 event reference;
frozen upstream facts;
persistence;
replay;
restart;
read-only behavior;
auditability;
the boundary through Continuation Eligibility Creation.

It reserves but does not define the unresolved Count-window, evaluation timing, Candle A replacement, unsuccessful-evaluation outcome, retry behavior, expiration behavior, terminal behavior, corrected-candle policy, out-of-order policy, session rollover policy, contract rollover policy, or market conditions required for confirmation. It defines no continuation lifecycle behavior after eligibility creation.

2. Position Within the Rejection Lifecycle
Liquidity Level
      │
      ▼
Rejection Step 2
      │
      ▼
Rejection Step 4
      │
      ▼
Continuation Eligibility Creation
      │
      ▼
STOP

Rejection Step 2 and Rejection Step 4 are phase identifiers within one Rejection Lifecycle. They share one lifecycle ID. Step 4 has no independent trading-lifecycle existence.

3. Lifecycle Domain and Phase Identifier
Lifecycle domain/type:
REJECTION

Lifecycle phase identifier:
REJECTION_STEP4

REJECTION_STEP4 identifies a stage within the same Rejection Lifecycle established at Step 2. It does not create an independent lifecycle, lifecycle ID, root lifecycle, or parent lifecycle relationship.

4. Upstream Step 2 Event Relationship
The Rejection Step 4 phase SHALL reference exactly one upstream event:
REJECTION_STEP2_CONFIRMED

Required immutable identifiers:
lifecycle_id
step2_event_id
session_id
symbol
direction
liquidity level identity
Step 2 confirmation candle identity

The step2_event_id SHALL be the exact event_id emitted by the canonical Step 2 specification. These references SHALL never change. Rejection Step 2 and Rejection Step 4 SHALL share the same lifecycle_id.

5. Phase Initialization
The Rejection Step 4 phase SHALL be initialized within the same Rejection Lifecycle after REJECTION_STEP2_CONFIRMED is durably recorded. No new lifecycle identity is created.

No market evaluation occurs merely because the phase is initialized. Initialization SHALL atomically persist:
the same lifecycle identity;
the exact Step 2 event reference;
the frozen Step 2 facts;
the specification version.

6. Frozen Step 2 Facts
The Rejection Step 4 phase SHALL reference the immutable Step 2 facts required by any future approved Step 4 rule, including:
Step 2 anchor;
exact named Step 2 boundary facts;
liquidity level identity;
direction;
confirmation candle identity;
confirmation timestamp.

These values remain the authoritative upstream reference for the entire Step 4 phase. They SHALL NOT be silently recalculated, replaced, or sourced from mutable runtime state.

This section does not define a Step 4 participation anchor or decide whether Candle A may be replaced.

7. Count Model
UNRESOLVED TRADING-RULE DECISION

Count 0 remains the Step 2 confirmation candle as defined by the binding Lifecycle Vocabulary and canonical Step 2 specification. The authorized Step 4 Count-window, evaluation count or counts, Candle A replacement behavior, and availability of later candles remain unresolved.

This draft specifies no three-candle observation sequence, Count 2-only evaluation, final count, or retry window.

8. Step 4 Ready
UNRESOLVED TRADING-RULE DECISION

The existence, meaning, and timing of STEP4_READY within the Step 4 transition map remain unresolved. This draft defines no count or transition that enters Ready.

9. Step 4 Confirmation
UNRESOLVED TRADING-RULE DECISION

If formally approved trading rules recognize Step 4 confirmation, its event SHALL reference the same lifecycle ID and exact Step 2 event ID and SHALL freeze the confirmation facts required by the approved rule.

Confirmation, if it occurs, SHALL be recorded at most once. This architecture invariant does not select an evaluation candle, count, or window.

10. Failure
UNRESOLVED TRADING-RULE DECISION

Whether an unsuccessful evaluation emits STEP4_FAILED, whether failure remains eligible for another evaluation, and whether failure is terminal remain unresolved. This draft specifies no failure transition.

11. Expiration
UNRESOLVED TRADING-RULE DECISION

Whether and when the Step 4 evaluation window expires, whether later candles remain eligible, and whether expiration is distinct from another outcome remain unresolved. This draft specifies no expiration transition or final count.

12. Terminal and Retry Behavior
UNRESOLVED TRADING-RULE DECISION

Which Step 4 outcomes, if any, are terminal and whether any unsuccessful outcome is retryable remain unresolved. Any outcome later classified as terminal by an approved canonical specification SHALL inherit the Lifecycle Engine's sticky-terminal protections. This draft does not classify any Step 4 outcome as terminal.

13. Continuation Eligibility Creation
Continuation Eligibility Creation is the outer boundary of this draft.

If formally approved Step 4 rules produce confirmation and satisfy the eligibility prerequisites, the eligibility record SHALL reference and freeze:
the same Rejection Lifecycle ID;
the exact Step 2 event ID;
the Step 4 event ID;
the applicable rule version;
the exact upstream facts required by the approved rule.

The eligibility record is not continuation lifecycle creation. It creates no continuation lifecycle ID, state, phase, evaluation, or implementation authority. No post-eligibility continuation behavior is specified here.

14. Prevention of Rejection-State Overwrite
Later market events, projections, or prospective continuation records SHALL NOT overwrite accepted Rejection Lifecycle history, including:
Step 2 event facts;
accepted Step 4 event facts;
confirmation timestamps;
frozen anchors;
frozen boundary facts;
lifecycle identity.

A later valid rejection opportunity requires its own Rejection Lifecycle identity under the canonical lifecycle rules. Historical lifecycle facts remain immutable except through an explicitly authorized correction or superseding event.

15. Duplicate Events
Duplicate processing of the same logical Step 4 input or event SHALL produce the same accepted lifecycle history. It SHALL NOT:
create a second outcome event;
apply the same count or candle identity twice;
overwrite accepted timestamps or frozen facts;
create duplicate continuation eligibility.

This idempotency requirement does not define the unresolved Count-window or outcome set.

16. Stale and Corrected Events
The exact accept, buffer, quarantine, correction, supersession, or ignore policy for stale or corrected candles remains unresolved for Step 4.

Regardless of the future policy, stale or corrected input SHALL NOT silently rewrite an accepted Step 2 event, accepted Step 4 event, frozen fact, or lifecycle identity. Any accepted historical correction must use the correction doctrine established by higher authority.

17. Out-of-Order Events
The exact Step 4 out-of-order policy remains unresolved.

Where a future approved canonical specification permits reordering, processing SHALL remain deterministic and preserve accepted history. This statement does not select a reordering window or event-acceptance policy.

18. Restart Behavior
Restart SHALL restore, when present:
the Rejection Lifecycle ID;
the exact Step 2 event reference;
the current Step 4 phase record;
frozen Step 2 facts;
accepted Step 4 events or outcomes;
continuation eligibility;
the applicable version.

Restart SHALL NOT infer an unresolved Count-window or recompute accepted Step 4 facts from current market conditions.

19. Session and Contract Rollover
The exact Step 4 session-rollover and contract-rollover policies remain unresolved.

The higher-authority isolation rules still apply: prior-session state SHALL NOT appear as active current-session state, and an active lifecycle SHALL NOT silently migrate to another contract. This draft does not decide archival, carry-forward, replacement, or termination behavior at either rollover boundary.

20. Read-Only Endpoints
Read-only endpoints SHALL NOT:
process a market event;
advance the Step 4 phase;
emit a Step 4 outcome;
create continuation eligibility;
persist lifecycle state.

Endpoints SHALL expose projections only. This rule does not define any unresolved Step 4 transition.

21. Legal Transitions
UNRESOLVED TRADING-RULE DECISION

No Step 4 transition map is canonical in this draft. Legal transitions require an approved Step 4 Count-window, outcome, retry, expiration, and terminal-window decision.

22. Prohibited Transitions
UNRESOLVED TRADING-RULE DECISION

This draft defines no Step 4-specific prohibited-transition table because doing so would select unresolved outcomes or terminal behavior. The higher-authority prohibitions against identity changes, upstream-event replacement, silent frozen-fact mutation, duplicate accepted events, and read-side mutation remain applicable.

23. Architecture Invariants
The following architecture invariants do not decide an unresolved trading rule.

Same-Lifecycle Invariant
Rejection Step 2 and Rejection Step 4 share one Rejection Lifecycle ID.

Upstream-Event Invariant
The Step 4 phase references the exact accepted Step 2 confirmation event ID.

Frozen-Fact Invariant
Accepted Step 2 facts are not silently recomputed or replaced during Step 4.

Idempotency Invariant
Duplicate logical input does not create duplicate accepted events or eligibility records.

Confirmation-Event Invariant
If an approved rule recognizes Step 4 confirmation, that confirmation event is accepted at most once.

Eligibility-Ordering Invariant
Continuation eligibility cannot precede an accepted Step 4 confirmation event produced under an approved rule.

Replay Invariant
Given the same archived facts, rule version, and approved event policy, replay reconstructs the same accepted lifecycle history.

Restart Invariant
Restart preserves lifecycle identity, exact upstream-event linkage, and frozen accepted facts.

24. Minimum Regression Evidence
This draft does not authorize implementation.

Any future separately authorized implementation under an approved canonical Step 4 specification SHALL test the approved trading rules and the architecture invariants above. Before approval, documentation and audit work may verify only that a proposal:
uses one Rejection Lifecycle identity for Step 2 and Step 4;
references the exact Step 2 event ID;
preserves frozen upstream facts;
prevents duplicate accepted events and eligibility records;
restores and replays accepted facts deterministically;
keeps read-only endpoints nonmutating;
does not infer any unresolved rule.

25. Codex Audit Requirements
A Codex audit of a future Step 4 proposal SHALL identify:
every file that creates or mutates the Rejection Lifecycle's Step 4 phase record;
every lifecycle writer and projection reader;
the shared lifecycle identity and exact Step 2 event linkage;
persistence, restoration, replay, session, contract, and endpoint paths;
duplicate, stale, corrected, and out-of-order handling;
every unresolved trading rule.

An audit SHALL report unresolved rules rather than infer them from code, tests, variable names, production observations, or this draft.

26. Architectural Guarantee
The Rejection Lifecycle's Step 4 phase is intended to provide a deterministic, immutable, auditable layer between its confirmed Step 2 event and Continuation Eligibility Creation.

It SHALL preserve same-lifecycle identity, exact upstream-event linkage, and frozen facts. This draft does not fix the Step 4 Count-window, Candle A replacement, retry model, terminal outcome, corrected-candle policy, out-of-order policy, rollover policy, or continuation lifecycle behavior and does not authorize implementation.
