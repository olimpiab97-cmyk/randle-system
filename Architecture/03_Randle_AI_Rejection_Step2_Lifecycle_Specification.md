Randle AI Rejection Step 2 Lifecycle Specification
Formal Deterministic Contract
Document Type: Specialized Lifecycle Specification
Status: Canonical
Authority: Specialized lifecycle authority governed by the Randle AI Constitution, Randle AI Lifecycle Vocabulary, Randle AI Lifecycle Engine Specification, and approved ADR-009 Boundary Architecture
Decision Basis: ADR-009 — Boundary Architecture, effective 2026-07-11
Domain: Rejection lifecycle
Step: Step 2
Applies to: Entry Agent live processing, replay, lifecycle persistence, event journals, tests, reasoning logs, and /entry/status.
Implementation Authority: None

ADR-010 Amendment Record: Effective 2026-07-13, all normative candle references in this Rejection-to-Continuation chain mean authoritative completed one-minute candles from the canonical one-minute series. ADR-010 also makes next-Liquidity-Level consumption an evaluation-authority guard before Rejection Step 2 evaluation. It does not change ADR-009's Boundary formulas, ownership, `P_in`, confirmation-first precedence, progression, or freeze mechanics.

1. Purpose
This specification defines the canonical Rejection Step 2 contract after the narrow amendment approved in ADR-009.

Rejection Step 2 is the confirmation and freeze of an existing Rejection Candidate-owned PROVISIONAL Rejection Boundary.
Accepted Rejection Step 2 creates the Rejection Lifecycle and establishes the confirmation candle as Rejection Count 0.

This specification defines:
Rejection Candidate and Rejection Boundary ownership;
strict-wick provisional-boundary formation;
provisional-boundary progression;
authorized completed-candle evaluation;
confirmation-first processing;
upper and lower one-tick confirmation rules;
freeze at the incoming provisional value;
atomic Rejection Lifecycle creation;
Candidate history and lineage preservation;
session-termination custody;
deterministic, idempotent outcomes.

This specification does not define or authorize implementation.

2. Governing Authority and Narrow Amendment
ADR-009 is the governing decision for Liquidity Level, Rejection Boundary, and Continuation Boundary semantics.

Effective 2026-07-11, ADR-009 is a narrow constitutional and architectural amendment limited to the Rejection Step 2 pattern and boundary statements expressly listed in its supersession ledger.
The retired Rejection Step 2 Leg 1/Leg 2 model ceased to govern when ADR-009 was approved.
All unaffected constitutional and universal lifecycle, evidence, identity, immutability, lineage, session, uniqueness, idempotency, and atomicity invariants remain higher authority and unchanged.

Stale terminology or specialized-specification language cannot silently restore a superseded Rejection Step 2 rule.

3. Separation of Responsibilities
3.1 Boundary formation
Boundary formation is the first authorized completed-candle wick strictly beyond the governing FROZEN Liquidity Level.
It creates a PROVISIONAL Rejection Boundary owned by the Rejection Candidate.

3.2 Provisional-boundary progression
Progression is movement of the same PROVISIONAL Rejection Boundary to a strictly farther outward wick extreme after an authorized boundary-confirmation close fails.
It is not a state transition, Candidate replacement, reseeding, restart, lifecycle replacement, or mutation of a frozen fact.

3.3 Rejection Step 2
Rejection Step 2 confirms and freezes the Candidate-owned PROVISIONAL Rejection Boundary.
It is not a participation rule.
It is not a Step 4 qualification rule.
It is not a mandatory multi-candle Leg 1/Leg 2 pattern.

3.4 Rejection Step 4
The Rejection Step 2 confirmation candle remains Rejection Count 0.
Subsequent Rejection Step 4 Count Window behavior is governed exclusively by ADR-006.
Rejection Step 4 Participation is governed exclusively by ADR-007.
This specification neither changes nor restates their detailed counting, participation, confirmation, retry, or expiration behavior.

No Step 4 participation or qualification predicate is evaluated as part of Rejection Step 2.
A later Step 4 outcome cannot retroactively alter accepted Rejection Step 2 or its frozen Rejection Boundary.

4. Domain Objects and Ownership
4.1 Liquidity Level
The Liquidity Level is a session-scoped market-truth aggregate root.
It owns its identity, value state, calculation provenance, freeze record, and historical record.
It freezes at 06:15 local time in America/Los_Angeles, including daylight-saving transitions.

The Session-lock layer owns the authoritative session-lock fact that causes the 06:15 freeze. It is not a second Liquidity Level owner.
The Rejection Candidate and Rejection Lifecycle consume and retain lineage to the Liquidity Level; they do not calculate, recalculate, replace, or modify it.

Its strategy-specific calculation is governed by a separately approved, versioned Liquidity Level Calculation Contract.
This specification does not define its formation window, output side set, price calculation, aggregation, exact 06:15 interval membership, correction behavior, or out-of-order-data behavior.

If no valid provisional Liquidity Level exists at the freeze event, no guessed, cached, zero, prior-session, or later-derived substitute is permitted.
Activity requiring that governing level must fail closed, and no Rejection Boundary requiring it may form.

4.2 Rejection Candidate
The Rejection Candidate is the stable owner of the Rejection Boundary while its value state is ABSENT or PROVISIONAL.
The Candidate must exist no later than initial provisional Rejection Boundary formation.

The Candidate may already exist or may be established atomically with initial formation under a separately approved Candidate-establishment rule.
ADR-009 and this specification do not define that independent establishment trigger or introduce a new identity component, event, candle role, or boundary owner for it.

### Candidate Replacement boundary

ADR-009 does not define or authorize a Candidate Replacement trigger.

Provisional Rejection Boundary formation and outward progression remain within the same Rejection Candidate and Rejection Boundary identities. They are not Candidate Replacement.

Before Rejection Step 2 Confirmation, Candidate Replacement may occur only when a separately approved Candidate-selection rule expressly authorizes it.

Any separately authorized Candidate Replacement must:

- remain within the governing session;
- remain within the authorized Liquidity Level context or establish a distinct Candidate identity as required by its governing rule;
- preserve the prior Candidate, its Rejection Boundary, and its complete authoritative history as immutable historical evidence;
- not mutate a confirmed Rejection Lifecycle;
- not reuse a confirmed Rejection Lifecycle identity;
- not alter another Candidate, owner, boundary, or Lifecycle;
- remain deterministic, unique, idempotent, and replayable.

After Rejection Step 2 Confirmation, Candidate Replacement is prohibited.

The existence of these safeguards does not authorize Candidate Replacement and does not define when it may occur.

4.3 Rejection Lifecycle
The Rejection Lifecycle does not own the provisional Rejection Boundary before confirmation.
It is created atomically when Rejection Step 2 confirms.
At that operation, it establishes the exact frozen incoming boundary as its immutable Rejection Boundary fact and preserves the Candidate identity and authoritative history as lineage.

4.4 Evaluation authority
Boundary ownership and boundary evaluation authority are distinct.
Ownership identifies the Candidate that owns the Rejection Boundary identity and state before confirmation.
Evaluation authority identifies whether a particular completed candle is permitted to form or evaluate that boundary under this specification and the applicable universal contracts.

5. Boundary Value-State Model
The Rejection Boundary uses exactly these owner-scoped value states:
ABSENT;
PROVISIONAL;
FROZEN.

The only boundary state transitions are:
ABSENT to PROVISIONAL;
PROVISIONAL to FROZEN.

A strictly farther outward value while PROVISIONAL is value progression within the same state.
A FROZEN Rejection Boundary has no outgoing boundary transition.
Duplicate processing may produce an idempotent no-op, but FROZEN to FROZEN is not a domain transition.

6. Symbols and Authoritative Inputs
Every symbol in the price rules is defined before use:

LL
The price of the governing FROZEN Liquidity Level for the same symbol, instrument mapping, session, level identity, and boundary side.

P_in
The committed PROVISIONAL Rejection Boundary value that existed immediately before the current authorized completed candle was evaluated.

P_new
The initial PROVISIONAL Rejection Boundary value created by the authorized boundary-formation candle.

P_out
The authoritative PROVISIONAL Rejection Boundary value after an authorized evaluation that does not confirm.

P_frozen
The immutable Rejection Boundary value established by accepted Rejection Step 2 confirmation.

H
The high of the current authorized completed candle.

Lo
The low of the current authorized completed candle.

C
The close of the current authorized completed candle.

τ
One canonical instrument tick for the applicable instrument. The Rejection Boundary record must preserve the identity or version of the authoritative governing tick-size source used for the evaluation.

The evaluation must also possess authoritative identity and lineage for:
Rejection Candidate;
Rejection Boundary;
governing Liquidity Level;
symbol and authorized instrument mapping;
session;
direction;
completed candle;
event ordering;
applicable rule and lifecycle versions.

7. Universal Guards and Evaluation Authorization
Before a candle may form or evaluate a Rejection Boundary, the engine must validate all applicable universal validity and integrity guards, including:
active valid session;
authorized symbol and instrument mapping;
stable Rejection Candidate identity;
governing Liquidity Level identity;
FROZEN governing Liquidity Level;
authoritative completed-candle data;
evaluation authority;
required evidence and lineage;
deterministic event ordering;
uniqueness;
idempotency;
duplicate protection.

For this chain, the candle must be an authoritative completed one-minute candle. Before Rejection Step 2 evaluation, ADR-010 next-Liquidity-Level consumption authority must also remain untriggered. When consumption occurs first, the Candidate loses evaluation authority and this specification performs no formation, confirmation, or progression for that candle.

These guards determine whether the candle is authorized to evaluate the boundary.
They are not additional Rejection Step 2 price predicates.

If a candle lacks evaluation authority or fails an applicable universal guard:
it does not form a boundary;
it does not confirm Step 2;
it does not progress the boundary;
it produces no boundary transition;
an existing P_in remains unchanged;
the candle is not classified as a failed-confirmation candle.

Retired interaction, sweep, entry-type pattern, Leg sequence, and volatility gates attached to the old Rejection Step 2 model are not universal guards and do not govern this specification.

8. Direction Identity
An upper Rejection Boundary corresponds to the existing upper/SHORT Rejection direction identity.
A lower Rejection Boundary corresponds to the existing lower/LONG Rejection direction identity.

These direction identities select the symmetric upper or lower boundary rule only.
They do not restore a Leg-based close relationship, participation predicate, Step 4 qualification predicate, continuation direction mapping, or other retired trading-pattern gate.

9. Provisional Rejection Boundary Formation
Derived-boundary formation is prohibited until the governing Liquidity Level is FROZEN.
Only an authorized completed candle may authoritatively form a Rejection Boundary.
Intrabar extremes may be observed, but they cannot change authoritative boundary state before the candle closes.

9.1 Upper formation
In plain English, an upper provisional Rejection Boundary forms when the completed candle high is strictly above the governing frozen Liquidity Level. The new provisional value is that candle high.

H > LL

P_new = H

9.2 Lower formation
In plain English, a lower provisional Rejection Boundary forms when the completed candle low is strictly below the governing frozen Liquidity Level. The new provisional value is that candle low.

Lo < LL

P_new = Lo

9.3 Touch is insufficient
For either direction, equality with LL is not formation.
A candle that merely touches the governing Liquidity Level leaves an ABSENT Rejection Boundary unchanged.

9.4 Formation-candle logical consequence
The candle that first forms a boundary cannot also confirm that newly formed boundary under valid OHLC data.

For an upper formation candle:

P_new = H

C <= H

Therefore, the candle cannot close at or above H plus τ.

For a lower formation candle:

P_new = Lo

C >= Lo

Therefore, the candle cannot close at or below Lo minus τ.

This is a logical consequence of valid OHLC data, not an additional discretionary prohibition.

10. Incoming-Boundary and Candle-Processing Precedence
For every authorized completed candle evaluating an existing PROVISIONAL Rejection Boundary:
1. Load the committed provisional boundary that existed before the candle was processed.
2. Define that value as P_in.
3. Evaluate the candle close against P_in.
4. If the close confirms, set P_frozen equal to P_in.
5. Atomically complete Rejection Step 2 and stop evaluation for that boundary.
6. Only when the confirmation close fails may the candle wick progress the provisional value.
7. If the close fails and no strictly farther outward wick exists, retain P_in unchanged.

The current candle's wick must never redefine P_in before its close is evaluated.
Confirmation and progression are mutually exclusive for the same boundary and candle.

11. Upper Rejection Boundary Rule
An upper provisional Rejection Boundary confirms when an authorized completed candle closes at least one canonical instrument tick above the provisional boundary that existed before the candle was processed.

Confirmation:

C >= P_in + τ

When confirmation succeeds:

P_frozen = P_in

The confirming candle cannot progress the same boundary, even when H is strictly above P_in.

If the close does not confirm and the candle reaches a strictly higher high, the same provisional Rejection Boundary progresses to that higher high.

Progression only after failed confirmation:

C < P_in + τ

and

H > P_in

Then:

P_out = H

If the close fails and the high is equal to or below P_in, the provisional value does not change:

C < P_in + τ

and

H <= P_in

Then:

P_out = P_in

12. Lower Rejection Boundary Rule
A lower provisional Rejection Boundary confirms when an authorized completed candle closes at least one canonical instrument tick below the provisional boundary that existed before the candle was processed.

Confirmation:

C <= P_in - τ

When confirmation succeeds:

P_frozen = P_in

The confirming candle cannot progress the same boundary, even when Lo is strictly below P_in.

If the close does not confirm and the candle reaches a strictly lower low, the same provisional Rejection Boundary progresses to that lower low.

Progression only after failed confirmation:

C > P_in - τ

and

Lo < P_in

Then:

P_out = Lo

If the close fails and the low is equal to or above P_in, the provisional value does not change:

C > P_in - τ

and

Lo >= P_in

Then:

P_out = P_in

13. Legal Evaluation Outcomes
Each completed candle presented for this Candidate and boundary has exactly one deterministic candle-processing result. Separately, an approved terminal or session event may produce the authority-termination semantic result in Section 13.6.

13.1 Unauthorized result
The candle lacks evaluation authority or fails an applicable universal guard.
No boundary evaluation or change occurs.

13.2 Initial formation result
An authorized completed candle strictly wicks beyond LL while the Candidate-owned Rejection Boundary is ABSENT.
The boundary moves from ABSENT to PROVISIONAL at that candle's outward extreme.

13.3 Confirmation result
An authorized completed candle satisfies the applicable one-tick close predicate against P_in.
Exactly P_in freezes, and the atomic Rejection Step 2 confirmation operation occurs.

13.4 Progression result
The authorized one-tick confirmation close fails and the completed candle has a strictly farther outward wick.
The value progresses within PROVISIONAL state.

13.5 Unchanged result
The authorized one-tick confirmation close fails and the completed candle has no strictly farther outward wick.
The value remains P_in.

13.6 Authority-termination result
An approved terminal or session event ends further evaluation authority while the boundary remains unconfirmed.
The boundary remains PROVISIONAL as inactive historical evidence and receives no further evaluation.

An unsuccessful authorized boundary-confirmation close is not automatically lifecycle Failure or termination.
These descriptions define permitted semantic effects only. They do not create event names, persisted outcome codes, lifecycle statuses, or a fourth boundary value state.

14. Atomic Rejection Step 2 Confirmation
Accepted Rejection Step 2 confirmation is one atomic domain operation with separate semantic effects:
1. validate evaluation authority and all applicable universal guards;
2. validate the applicable one-tick close predicate against P_in;
3. freeze exactly P_in;
4. emit exactly one REJECTION_STEP2_CONFIRMED event;
5. create exactly one Rejection Lifecycle;
6. establish the frozen Rejection Boundary as the Lifecycle's immutable boundary fact;
7. preserve the Rejection Candidate identity and authoritative provisional history as lineage;
8. establish the confirmation candle as Rejection Count 0.

No partial state is legal.
A confirmation event without the frozen P_in, a Lifecycle without the accepted confirmation, or a frozen boundary without its Candidate lineage is prohibited.

15. Confirmation Evidence and Historical Lineage
The authoritative evidence includes:
Rejection Candidate identity;
Rejection Boundary identity;
governing Liquidity Level identity;
symbol, instrument mapping, session, and direction;
boundary-formation candle identity, completed OHLC, and initial provisional value;
every provisional progression, its source completed-candle identity, completed OHLC, and resulting provisional value;
every authorized boundary-evaluation candle identity, completed OHLC, P_in, and evaluation outcome;
confirmation candle identity, completed OHLC, and close;
identity or version of the governing canonical tick-size source;
source-data provenance;
P_frozen;
REJECTION_STEP2_CONFIRMED event identity and timestamp;
created Rejection Lifecycle identity;
Rejection Count 0 identity;
Candidate-to-Lifecycle lineage;
applicable rule and lifecycle versions.

The Candidate remains immutable historical evidence after confirmation.
It is not a second active owner of the frozen boundary.

These facts must be authoritatively preserved and stably linked under the canonical evidence contract. This specification does not require complete history duplication inside one event payload and does not select a persistence or serialization design.

16. Freeze and Immutability
For Rejection Step 2:
the boundary freezes only when its own one-tick confirmation predicate succeeds;
the exact value tested is the exact value frozen;
the confirming candle's farther wick is ignored for progression;
future farther wicks cannot alter the frozen value;
later Step 4 outcomes cannot alter the frozen value;
provisional progression never alters a frozen fact;
Candidate history is not deleted or rewritten;
freeze and Lifecycle adoption are separate semantic effects even though they commit atomically.

17. Generic Step 2 Anchor
A generic Step 2 Anchor may remain where a separately approved rule independently requires one.
For Rejection Step 2 governed by ADR-009, an Anchor:
does not replace P_in;
does not alter the one-tick confirmation predicate;
does not change P_frozen;
does not become a required, hidden, supplemental, or fallback Rejection Step 2 predicate.

18. Session Termination
When the Rejection Candidate loses evaluation authority through its approved terminal or session event:
an unconfirmed PROVISIONAL Rejection Boundary does not freeze;
it does not return to ABSENT;
it does not progress further;
it does not transfer to another owner;
it cannot carry forward as active state into another session;
its final provisional value and complete authoritative history remain preserved as inactive historical evidence under the Candidate.

No fourth boundary value state is created.
The exact Candidate terminal-session deadline remains governed by a separately approved session rule; this specification does not invent a universal deadline.

19. Event Ordering, Idempotency, and Replay
Only authorized completed candles may authoritatively form, evaluate, progress, confirm, or freeze the Rejection Boundary.
Intrabar extremes cannot alter committed boundary state.

P_in must be stable for the full evaluation of one completed candle.
The same canonical completed candle and incoming committed state must produce the same result in live processing, restart recovery, and replay.

Duplicate delivery of a candle, formation effect, progression effect, or accepted confirmation must produce an idempotent no-op after its first valid application.
It must not:
form a second boundary;
progress the boundary twice;
change P_in;
freeze twice;
emit duplicate confirmation events;
create duplicate Rejection Lifecycles;
change Rejection Count 0.

Corrected-candle and out-of-order-event handling remain deferred pending a separately approved canonical system-wide market-data correction and ordering contract.
This specification does not create that contract, invent a local correction engine, or select a correction policy.

20. Rejection Count 0 and Step 4 Isolation
The accepted Rejection Step 2 confirmation candle is Rejection Count 0.
Its identity is immutable and tied to the exact REJECTION_STEP2_CONFIRMED event and Rejection Lifecycle.

Subsequent Count Window behavior is governed exclusively by ADR-006.
Rejection Step 4 Participation is governed exclusively by ADR-007.
ADR-009 and this specification neither change nor reinterpret ADR-006 or ADR-007.

No Step 4 participation or qualification predicate is evaluated during Rejection Step 2.
No Step 4 outcome may retroactively invalidate or modify accepted Step 2, Rejection Count 0, Candidate lineage, or the frozen Rejection Boundary.

21. Explicitly Superseded and Prohibited Rejection Step 2 Rules
The following retired rules do not govern Rejection Step 2:
Leg 1 as a mandatory pattern component;
Leg 2 as a mandatory pattern component;
Leg 1 Close as the confirmation reference;
an upper/SHORT Leg 2 close below Leg 1 Close;
a lower/LONG Leg 2 close above Leg 1 Close;
any Leg 1/Leg 2 sequence limit used only by the retired confirmation model;
interaction or sweep as a Rejection Step 2 trading gate;
entry-type pattern as a Rejection Step 2 trading gate;
retired volatility logic as a Rejection Step 2 trading gate;
delegated boundary derivation that conflicts with strict-wick formation;
participation as a Rejection Step 2 predicate;
Step 4 qualification as a Rejection Step 2 predicate.

These rules are superseded and removed; not reassigned.
They are not moved into Candidate formation, Participation, or Step 4 qualification.
They are not preserved as dormant, hidden, supplemental, or fallback predicates.
They may return only through a separately approved future ADR defining a new purpose.

22. Cross-Boundary Protection
The Rejection Boundary retains its own identity, owner, value, progression history, confirmation, and session lineage.
It cannot create, progress, confirm, freeze, reset, replace, transfer into, or invalidate a Continuation Boundary.
A Continuation Boundary cannot create, progress, confirm, freeze, reset, replace, transfer into, or invalidate the Rejection Boundary.
Lineage references and numerical equality do not merge boundary identities or authorize either boundary to mutate the other.

The Rejection Boundary is not copied, transferred, promoted, or transformed into a Continuation Boundary.
Continuation Eligibility does not own, form, progress, confirm, or freeze a Continuation Boundary.
No Continuation Boundary exists before its Continuation Lifecycle identity.

ADR-010 governs Continuation Creation, initial Boundary formation, and Evaluation Start. This specification continues to prohibit a Continuation Lifecycle with an ABSENT boundary.

23. Read-Only Purity and Traceability
Read-only projections, status requests, audits, serialization, reporting, and operator displays must not:
form or progress a boundary;
authoritatively accept confirmation or produce a boundary or lifecycle transition;
freeze a boundary;
create a Candidate or Lifecycle;
change P_in;
change Rejection Count 0;
rewrite Candidate history;
alter session authority.

Every projected boundary must remain traceable to its authoritative boundary identity, owner, session, governing Liquidity Level, and lifecycle lineage when applicable.

24. Deferred Contracts and Decisions
The following remain outside this specification:
Liquidity Level formation-window start and end;
Liquidity Level price calculation and output side set;
exact market-interval membership at 06:15;
canonical corrected-candle and out-of-order-data rules;
exact Rejection Candidate establishment sequencing before or with initial boundary formation;
precise Candidate terminal-session deadline;
continuation Count 0;
continuation participation and Step 4;
multi-owner candle routing.

These deferrals do not reopen this specification's strict-wick formation, confirmation-first precedence, one-tick close, failed-close-only progression, freeze-at-P_in, ownership, or immutability decisions.

25. Canonical Invariants
The following invariants must always hold:
1. The governing Liquidity Level is FROZEN before Rejection Boundary formation.
2. A strict wick beyond LL is required; touching LL is insufficient.
3. Only an authorized completed candle may authoritatively form, evaluate, progress, confirm, or freeze the boundary.
4. The Rejection Candidate owns the boundary while it is ABSENT or PROVISIONAL.
5. The Candidate must exist no later than initial provisional formation.
6. ADR-009 does not define the Candidate's independent establishment trigger.
7. The only boundary transitions are ABSENT to PROVISIONAL and PROVISIONAL to FROZEN.
8. Provisional progression retains the same Candidate and boundary identities.
9. Every authorized evaluation of an existing provisional boundary snapshots P_in before processing the candle.
10. Confirmation is evaluated before same-candle wick progression.
11. The exact P_in tested is the exact value frozen.
12. A confirming candle cannot progress the same boundary.
13. Only a failed one-tick confirmation close may permit strictly farther outward progression.
14. Equal extremes do not progress the boundary.
15. A boundary-formation candle cannot confirm its newly formed boundary.
16. Accepted confirmation atomically creates exactly one Rejection Lifecycle and exactly one REJECTION_STEP2_CONFIRMED event.
17. The confirmation candle is Rejection Count 0.
18. Candidate identity and authoritative history remain preserved as lineage.
19. A FROZEN boundary has no outgoing boundary transition.
20. Session termination does not freeze or reset an unconfirmed provisional boundary.
21. No retired Rejection Step 2 predicate remains governing or is reassigned.
22. Step 4 participation and qualification are not Step 2 predicates.
23. A later Step 4 outcome cannot change accepted Step 2 or its frozen boundary.
24. Rejection and Continuation Boundaries remain independent.
25. ADR-010, not this specification, governs Continuation Creation sequencing and Evaluation Start.

26. Acceptance Standard and Authorization Boundary
This specification is aligned only when architecture, implementation, tests, replay, persistence, and projections use the same approved Rejection Step 2 meaning without restoring a retired predicate or changing ADR-006 or ADR-007.

This document defines architecture only.
Its approval and alignment do not authorize:
implementation changes;
test changes;
runtime-state changes;
database or persistence changes;
migration;
deployment;
canonical market-data correction policy;
Continuation Creation architecture;
execution;
a Git commit.
