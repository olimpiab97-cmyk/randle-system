# ADR-009 — Boundary Architecture

## 1. Status

**APPROVED**

**Date:** 2026-07-11

Explicit owner approval was granted effective July 11, 2026.

Approval authorizes the architecture decision, its narrow supersessions, and creation of this ADR-009 file. It does not authorize modification of any other architecture document, canonical-document alignment, implementation, tests, migration, runtime changes, staging, a commit, or any other file operation.

## 2. Context

The existing Rejection Step 2 architecture incorrectly combines:

- boundary formation and confirmation;
- candle participation;
- later Rejection Step 4 qualification.

That model makes Leg 1, Leg 2, Leg 1 Close, and their sequence part of Rejection Step 2 Confirmation.

ADR-009 deliberately replaces that model.

Under the corrected architecture:

- a strict wick beyond a governing frozen Liquidity Level forms a provisional boundary;
- later authorized completed candles may progress that boundary while Step 2 remains unconfirmed;
- Rejection Step 2 confirms and freezes the incoming provisional Rejection Boundary;
- the exact boundary value tested for confirmation becomes the frozen value;
- the confirming candle becomes Rejection Count 0;
- Step 4 participation and qualification remain separate.

The replacement rule is not equivalent to, supplemental to, or a specialization of the retired Leg 1/Leg 2 model.

## 3. Decision

ADR-009 establishes the governing architecture for:

- Liquidity Level ownership, lifecycle, and freeze semantics;
- Rejection Boundary formation, progression, confirmation, freeze, ownership, and history;
- Continuation Boundary formation, progression, confirmation, freeze, ownership, and history;
- deterministic completed-candle precedence;
- separation of Rejection Step 2 from Step 4 participation and qualification.

### Express replacement

The following rules ceased to govern Rejection Step 2 when ADR-009 was approved effective July 11, 2026:

- Leg 2 Close below Leg 1 Close for an upper/SHORT rejection;
- Leg 2 Close above Leg 1 Close for a lower/LONG rejection;
- Leg 1 Close as the Step 2 confirmation reference;
- Leg 1 and Leg 2 as mandatory components of the Step 2 confirmation pattern;
- any Leg 1/Leg 2 sequence limit that exists solely to support the retired pattern;
- delegated entry-type boundary derivation that conflicts with ADR-009’s strict-wick formation rule;
- any Step 2 condition whose actual purpose is candle participation or Step 4 qualification.

These rules are not preserved as hidden prerequisites. They are not moved into participation or Step 4. They may return only through a separate future ADR that explicitly defines and approves a new purpose.

### Narrow governance amendment

With explicit owner approval effective July 11, 2026, ADR-009 is a narrow constitutional and architectural amendment limited to the Rejection Step 2 pattern and boundary statements expressly listed in its supersession ledger.

The Constitution’s unaffected universal lifecycle, evidence, identity, immutability, lineage, session, uniqueness, idempotency, and atomicity invariants remain higher authority and unchanged.

Effective upon approval of ADR-009:

- the expressly identified retired statements ceased to govern;
- ADR-009’s replacement rules became governing immediately;
- no period exists in which both rule sets purport to govern;
- stale conflicting documentation cannot make the replacement contingent on later file edits.

The later documentation-alignment task will record the approved decision in affected canonical documents. It does not create or activate the decision and is not authorized by this ADR approval.

ADR-009 does not generally override the Constitution.

## 4. Separation of Step 2, Participation, and Step 4 Qualification

### Boundary formation

A strict wick beyond the governing frozen Liquidity Level creates a provisional boundary.

Boundary formation does not confirm Step 2.

### Provisional boundary progression

A later authorized completed candle may progress a provisional boundary to a strictly farther outward wick only when its boundary-confirmation close fails.

Progression remains part of provisional boundary formation. It is not:

- lifecycle reseeding;
- lifecycle restart;
- Candidate replacement;
- boundary replacement;
- a new boundary state;
- mutation of a frozen fact.

### Rejection Step 2

Rejection Step 2 is the confirmation and freeze of an existing provisional Rejection Boundary.

It is not:

- a candle-participation rule;
- a Step 4 qualification rule;
- a multi-candle Leg 1/Leg 2 pattern;
- a decision about later Step 4 success.

Accepted Rejection Step 2 Confirmation atomically creates the Rejection Lifecycle, freezes the incoming provisional boundary, and establishes the confirmation candle as Rejection Count 0.

### Rejection Step 4

The Rejection Step 2 confirmation candle remains Rejection Count 0.

ADR-006 alone governs the approved Rejection Step 4 Count Window.

ADR-007 alone governs the approved Rejection Step 4 Participation Rule.

ADR-009 neither changes nor restates their detailed counting, participation, confirmation, retry, or expiration behavior.

No Step 4 participation or qualification predicate is evaluated as part of Rejection Step 2.

Later Step 4 outcomes cannot retroactively alter accepted Rejection Step 2 Confirmation or its frozen Rejection Boundary.

## 5. Boundary Vocabulary

### Liquidity Level

A Liquidity Level is a session-scoped market-truth aggregate root used as the governing price reference for derived-boundary formation.

### Rejection Candidate

A Rejection Candidate is the provisional owner of a possible Rejection Boundary before Rejection Step 2 Confirmation.

The Candidate must exist no later than initial provisional Rejection Boundary formation.

It may:

- exist before the boundary-formation candle; or
- be established atomically with initial boundary formation under the later aligned Candidate-start rule.

ADR-009 does not define an independent Candidate market trigger or introduce an unnamed boundary owner.

### Rejection Boundary

A Rejection Boundary is a Candidate-owned derived price object that may be `ABSENT` or `PROVISIONAL` before Rejection Step 2 Confirmation and becomes a frozen Rejection Lifecycle fact when Step 2 confirms.

### Continuation Boundary

A Continuation Boundary is a Continuation Lifecycle-owned derived price object governed by the same formation, progression, confirmation, and freeze mechanics.

It is independent from, and is not copied from, the Rejection Boundary.

### Boundary-formation candle

The authorized completed candle that first wicks strictly beyond the governing frozen Liquidity Level and establishes the provisional boundary.

### Boundary-evaluation candle

An authorized completed candle permitted to evaluate an existing provisional boundary.

### Step 2 confirmation candle

The authorized completed boundary-evaluation candle whose close satisfies the one-tick confirmation predicate against the incoming provisional boundary.

For Rejection, this candle becomes Count 0.

### Incoming provisional boundary

`P_in` means:

> The committed provisional boundary value that existed immediately before the current authorized completed candle was evaluated.

The current candle’s wick cannot redefine `P_in` before its close is evaluated.

### Outward progression

For an upper boundary, outward progression means movement to a strictly higher high.

For a lower boundary, outward progression means movement to a strictly lower low.

### Canonical instrument tick

`τ` is one canonical tick for the applicable instrument. The boundary record must preserve the identity or version of the governing tick-size source.

### Boundary value states

The boundary value model contains:

- `ABSENT`
- `PROVISIONAL`
- `FROZEN`

The only boundary state transitions are:

```text
ABSENT → PROVISIONAL
PROVISIONAL → FROZEN
```

A farther outward value while `PROVISIONAL` is progression within the same state.

A `FROZEN` boundary has no outgoing boundary transition. Duplicate processing may produce an idempotent no-op, but `FROZEN → FROZEN` is not a domain transition.

For a Rejection Boundary, `ABSENT` is owned by an existing Rejection Candidate.

For a Continuation Boundary, `ABSENT` is only a conceptual owner-scoped value state if a future Continuation Creation ADR explicitly authorizes a Continuation Lifecycle to exist before initial boundary formation. ADR-009 does not authorize that lifecycle state.

A nonexistent, ownerless Continuation Boundary must not be represented as `ABSENT`.

Leg 1 and Leg 2 are not normative Rejection Step 2 concepts under ADR-009.

## 6. Liquidity Level Architecture

The Liquidity Level is a session-scoped market-truth aggregate root.

It exclusively owns:

- `liquidity_level_id`;
- session identity;
- symbol or instrument identity;
- level type or side;
- current value state;
- provisional or frozen price;
- calculation-contract identity and version;
- source-window identity;
- calculation provenance;
- freeze timestamp;
- complete historical record.

Its lifecycle is:

- `ABSENT` before its authorized calculation produces a valid session value;
- `PROVISIONAL` after the first valid value is produced and before freeze;
- `FROZEN` at 06:15 local time in `America/Los_Angeles`.

The timezone definition includes daylight-saving transitions.

Before 06:15, the authorized Liquidity Level calculation may update the provisional value according to its versioned calculation contract.

At 06:15:

- the latest valid provisional value freezes;
- the frozen value becomes immutable;
- no later market input may alter it;
- the freeze must be recorded before derived-boundary evaluation is authorized.

The Session-lock layer owns the authoritative session-lock fact that causes the 06:15 freeze. It is not a second owner of the Liquidity Level.

The Liquidity Level aggregate owns its resulting value state, freeze record, provenance, and history.

Rejection Candidates, Rejection Lifecycles, Continuation Eligibility records, and Continuation Lifecycles are consumers and lineage holders only. They cannot calculate, recalculate, replace, or modify the Liquidity Level.

Derived Rejection or Continuation Boundary formation is prohibited until the governing Liquidity Level is `FROZEN`.

### Liquidity Level Calculation Contract

ADR-009 defines the Liquidity Level lifecycle and 06:15 freeze semantics. It does not define the strategy-specific price calculation.

A separate approved and versioned Liquidity Level Calculation Contract must define:

- formation-window start and end;
- eligible market-data intervals or events;
- whether the calculation produces an upper level, lower level, or both;
- exact price calculation;
- aggregation method;
- rounding and tick normalization;
- treatment of intervals touching or spanning 06:15;
- missing-data treatment;
- source-time ordering;
- corrected-data behavior;
- replay behavior.

ADR-009 does not assert that any particular high, low, open, close, midpoint, range, or formation window governs.

If no valid provisional Liquidity Level exists at the freeze event:

- no substitute may be guessed;
- no zero value may be created;
- no cached value may be used;
- no prior-session value may be used;
- no later-derived value may be substituted;
- no derived boundary may form for activity requiring that level;
- the missing-level outcome must be recorded deterministically.

This is a missing-governing-reference outcome, not a frozen zero-price Liquidity Level.

## 7. Common Derived-Boundary Mechanics

A Rejection Boundary or Continuation Boundary may form only when:

- its governing Liquidity Level is `FROZEN`;
- the identified owner has evaluation authority;
- an authorized completed candle wicks strictly beyond that Liquidity Level.

Touching the Liquidity Level is insufficient.

For an upper boundary:

- the completed candle high must be strictly above the governing Liquidity Level;
- the initial provisional boundary equals that high.

For a lower boundary:

- the completed candle low must be strictly below the governing Liquidity Level;
- the initial provisional boundary equals that low.

Only authorized completed candles may authoritatively:

- form a boundary;
- evaluate an existing provisional boundary;
- progress a provisional boundary;
- confirm Step 2;
- freeze a boundary.

Intrabar extremes may be observed, but they cannot alter authoritative boundary state.

A boundary-formation candle cannot confirm the boundary it just formed.

For an upper formation:

```text
P_new = H
C <= H
```

The candle therefore cannot close at least one tick above `P_new`.

For a lower formation:

```text
P_new = Lo
C >= Lo
```

The candle therefore cannot close at least one tick below `P_new`.

### Universal validity and integrity guards

Applicable universal guards include:

- active valid session;
- authorized symbol and instrument;
- valid contract mapping;
- governing Liquidity Level identity;
- frozen governing Liquidity Level;
- authoritative completed-candle data;
- stable owner identity;
- evaluation authority;
- uniqueness;
- idempotency;
- duplicate protection;
- deterministic event ordering;
- required evidence and lineage.

These guards determine whether a candle is authorized to evaluate the boundary. They are not additional Step 2 price predicates.

Retired interaction, sweep, Leg, entry-type pattern, candle-sequence, participation, and volatility conditions are not retained as Candidate or Step 2 prerequisites.

If a candle lacks evaluation authority or fails a universal guard:

- it does not confirm Step 2;
- it does not progress the boundary;
- it produces no boundary transition;
- the committed provisional value remains unchanged.

Such a candle is unauthorized. It is not a failed confirmation candle.

Only an authorized boundary evaluation may produce:

- confirmation;
- outward progression after failed confirmation;
- an unchanged authorized result.

## 8. Rejection Candidate and Provisional Boundary Formation

The Rejection Candidate must exist no later than initial provisional Rejection Boundary formation.

The Candidate may already exist or may be established atomically with initial boundary formation according to the later aligned Candidate-start rule.

ADR-009 does not independently define the Candidate-start market trigger. It requires only that no provisional Rejection Boundary exist without its identified Candidate owner.

The Candidate exclusively owns the Rejection Boundary while it is `ABSENT` or `PROVISIONAL`.

### Upper Rejection Boundary formation

The first authorized completed candle whose high is strictly above the governing frozen upper Liquidity Level forms an upper provisional Rejection Boundary.

The initial provisional value equals that candle’s high.

### Lower Rejection Boundary formation

The first authorized completed candle whose low is strictly below the governing frozen lower Liquidity Level forms a lower provisional Rejection Boundary.

The initial provisional value equals that candle’s low.

Touching the governing Liquidity Level produces no boundary formation.

The Candidate must preserve:

- Candidate identity;
- Rejection Boundary identity;
- authorized boundary side and direction identity;
- governing Liquidity Level identity;
- boundary-formation candle identity and completed OHLC;
- initial provisional value;
- every later provisional extreme;
- every authorized boundary-evaluation candle;
- `P_in` used for each authorized evaluation;
- each authorized evaluation outcome;
- rule version;
- source-data provenance.

No Leg selection or retired pattern sequence is required.

## 9. Rejection Step 2 Confirmation

For each authorized completed candle evaluating an existing provisional Rejection Boundary:

1. Load the committed provisional boundary that existed before the candle was processed.
2. Define that value as `P_in`.
3. Evaluate the completed candle close against `P_in`.
4. If the close confirms, freeze exactly `P_in`.
5. Create the Rejection Lifecycle atomically with confirmation.
6. Record the confirmation candle as Rejection Count 0.
7. Do not progress the boundary from the confirming candle’s farther wick.
8. Only when the close fails may a strictly farther wick progress the provisional boundary.
9. If the close fails and no farther wick exists, retain `P_in` unchanged.

Confirmation and progression are mutually exclusive for the same boundary and candle.

Accepted Rejection Step 2 Confirmation must atomically:

- validate evaluation authority and universal guards;
- validate the boundary-close predicate;
- freeze `P_in`;
- emit exactly one `REJECTION_STEP2_CONFIRMED` event;
- create exactly one Rejection Lifecycle;
- establish the frozen Rejection Boundary as the Lifecycle’s immutable boundary fact;
- preserve Candidate identity and complete provisional history as lineage;
- establish the confirmation candle as Rejection Count 0.

The Step 2 confirmation candle establishes Rejection Count 0. Subsequent Count Window behavior is governed exclusively by ADR-006.

The retired Leg 1 and Leg 2 predicates are not evaluated.

No Step 4 participation or qualification predicate is evaluated during Step 2.

## 10. Continuation Boundary Architecture

Continuation Boundary mechanics use the same:

- conceptual value-state model;
- strict-wick formation;
- completed-candle authority;
- incoming-boundary snapshot;
- confirmation-first precedence;
- one-tick close;
- failed-close outward progression;
- freeze-at-`P_in` rule;
- post-freeze immutability.

The Continuation Boundary has its own:

- identity;
- owner;
- value;
- formation history;
- progression history;
- evaluation history;
- Step 2 Confirmation;
- freeze record.

It is numerically and historically independent from the Rejection Boundary.

The Rejection Boundary is not copied into the Continuation Boundary.

Continuation Eligibility:

- does not form a Continuation Boundary;
- does not own a Continuation Boundary;
- does not progress a Continuation Boundary;
- does not freeze a Continuation Boundary.

A Continuation Boundary is owned exclusively by its Continuation Lifecycle from first formation onward. A Continuation Boundary cannot exist before its Continuation Lifecycle identity exists.

Before Continuation Creation, the confirmed Rejection Lifecycle coexists with no Continuation Boundary object.

ADR-009 does not decide whether:

- Continuation Creation precedes initial boundary formation; or
- Continuation Creation and initial boundary formation occur atomically.

Mentioning those possibilities does not authorize either sequence.

ADR-009 does not authorize a Continuation Lifecycle with an `ABSENT` boundary where current canonical Vocabulary prohibits that state. The future Continuation Creation ADR must select the sequence and explicitly align the Lifecycle Vocabulary.

No Continuation Candidate or other pre-lifecycle provisional owner is introduced.

ADR-009 does not define:

- the Continuation Creation market trigger;
- Continuation Evaluation Start;
- continuation direction mapping;
- continuation Count 0;
- continuation participation;
- continuation Step 4;
- continuation entry behavior.

## 11. Candle-Processing Precedence

For every completed candle presented for boundary processing:

1. Validate evaluation authority and universal guards.
2. If authorization fails, produce no boundary evaluation or change.
3. If authorization succeeds, snapshot the committed provisional value as `P_in`.
4. Evaluate the completed close against `P_in`.
5. If the close confirms, freeze `P_in`.
6. Stop evaluation for that boundary.
7. Only if the close fails, compare the completed outward wick with `P_in`.
8. Progress only when the wick is strictly farther outward.
9. Otherwise retain `P_in`.

The current candle’s wick must never redefine `P_in` before its close is evaluated.

A confirming candle cannot progress the same boundary.

An equal wick extreme causes no change.

An unauthorized candle produces no boundary evaluation and is not a failed confirmation candle.

This ordering prevents intrabar movement from changing the same candle’s confirmation target.

## 12. Upper-Boundary Rule

An upper provisional boundary confirms when an authorized completed candle closes at least one canonical instrument tick above the provisional boundary that existed before the candle was processed.

### Confirmation

```text
C >= P_in + τ
```

If confirmation succeeds:

```text
P_frozen = P_in
```

If the close does not confirm, but the completed high is strictly farther outward, the provisional boundary progresses to that high.

### Progression after failed confirmation

```text
C < P_in + τ
and
H > P_in
```

Then:

```text
P_out = H
```

If the close fails and `H <= P_in`:

```text
P_out = P_in
```

Where:

- `C` is the authorized completed candle close;
- `H` is the authorized completed candle high;
- `τ` is one canonical instrument tick.

## 13. Lower-Boundary Rule

A lower provisional boundary confirms when an authorized completed candle closes at least one canonical instrument tick below the provisional boundary that existed before the candle was processed.

### Confirmation

```text
C <= P_in - τ
```

If confirmation succeeds:

```text
P_frozen = P_in
```

If the close does not confirm, but the completed low is strictly farther outward, the provisional boundary progresses to that low.

### Progression after failed confirmation

```text
C > P_in - τ
and
Lo < P_in
```

Then:

```text
P_out = Lo
```

If the close fails and `Lo >= P_in`:

```text
P_out = P_in
```

Where:

- `C` is the authorized completed candle close;
- `Lo` is the authorized completed candle low;
- `τ` is one canonical instrument tick.

## 14. Ownership and Lineage

### Liquidity Level

The Liquidity Level aggregate root owns its identity, value state, calculation provenance, freeze record, and history.

The Session-lock layer owns the authoritative session-lock fact that causes the 06:15 freeze. It is not a second Liquidity Level owner.

### Rejection Boundary before confirmation

The Rejection Candidate owns:

- Rejection Boundary identity;
- `ABSENT` or `PROVISIONAL` state;
- current provisional value;
- complete progression history;
- evaluation history;
- governing Liquidity Level reference.

### Rejection Step 2 atomic operation

Rejection Step 2 Confirmation must atomically:

1. validate the authorized boundary-close predicate;
2. freeze `P_in`;
3. create the Rejection Lifecycle;
4. establish the frozen Rejection Boundary as the Lifecycle’s immutable boundary fact;
5. preserve Candidate identity and complete provisional history as lineage;
6. establish the confirmation candle as Rejection Count 0.

The Candidate remains immutable historical evidence. It is not a second active owner after confirmation.

Freeze and Lifecycle adoption are separate semantic effects even when committed atomically.

No unnamed boundary owner or “boundary-formation context” is introduced.

### Continuation Boundary

The Continuation Lifecycle owns its Continuation Boundary from first formation onward.

Continuation Eligibility remains an authorization and lineage record. It is not a mutable boundary owner.

### Lineage

Derived boundaries preserve:

- governing Liquidity Level identity;
- session identity;
- symbol or instrument identity;
- rule version;
- source-data provenance.

A Continuation Lifecycle additionally preserves:

- Rejection parent identity;
- accepted parent Step 4 Confirmation identity;
- Continuation Eligibility identity.

Lineage does not create shared ownership or numerical coupling.

## 15. Freeze Semantics

The Liquidity Level and derived boundaries freeze through different events.

### Liquidity Level freeze

The Liquidity Level freezes by time at 06:15 local time in `America/Los_Angeles`.

Its freeze is not Step 2-based.

### Derived-boundary freeze

A Rejection or Continuation Boundary freezes only when its own Step 2 confirms.

For every derived boundary:

- the exact value evaluated is the exact value frozen;
- the frozen value is `P_in`;
- a confirming candle’s farther wick cannot progress it;
- future farther wicks cannot alter it;
- provisional progression does not restart or reseed a lifecycle;
- numerical equality with another boundary does not merge identity.

A frozen boundary has no outgoing boundary transition.

Duplicate processing may produce an idempotent no-op. It does not create another freeze transition.

## 16. Session Termination

When an owning Candidate or Lifecycle loses evaluation authority through its approved session or terminal event:

- an unconfirmed provisional boundary does not freeze;
- it does not return to `ABSENT`;
- it does not progress further;
- it does not transfer to another owner;
- it cannot carry forward as active state into another session;
- its final provisional value remains preserved;
- its complete formation, progression, and evaluation history remains preserved as inactive historical evidence.

No fourth boundary state is created.

The exact terminal session deadline remains governed by the owning Candidate or Lifecycle’s approved session rules. ADR-009 does not invent a universal trading-session deadline.

A frozen Liquidity Level remains preserved as a historical session market-truth object after active session applicability ends.

## 17. Cross-Boundary Relationships

Liquidity Level, Rejection Boundary, and Continuation Boundary have separate identities.

Rejection and Continuation Boundaries have separate:

- owners;
- values;
- states;
- formation histories;
- progression histories;
- Step 2 Confirmations;
- freeze records.

One boundary cannot:

- create another boundary;
- progress another boundary;
- confirm another boundary;
- freeze another boundary;
- reset another boundary;
- replace another boundary;
- invalidate another boundary.

Numerical equality does not merge boundary identity.

Each derived boundary evaluates its own `P_in`.

Both derived boundaries preserve governing Liquidity Level identity and session lineage. Continuation additionally preserves Rejection parent and Eligibility lineage.

A lifecycle event may authorize later lifecycle or boundary activity. A boundary value itself does not create another boundary.

Under the approved lifecycle order:

- a provisional Rejection Boundary and provisional Continuation Boundary cannot coexist;
- before Continuation Creation, a frozen Rejection Boundary may coexist with no Continuation Boundary object;
- after a Continuation Lifecycle and its boundary exist through a future authorized Creation sequence, the frozen Rejection Boundary may coexist with that Continuation Boundary while it is `PROVISIONAL` or `FROZEN`.

An `ABSENT` Continuation Boundary is only a conceptual owner-scoped value state if a future Continuation Creation ADR explicitly authorizes a Lifecycle to exist before initial boundary formation. ADR-009 does not presently authorize that state.

Boundary independence does not automatically authorize one candle to evaluate multiple owners. Multi-owner candle routing requires an explicit future lifecycle rule.

## 18. Invariants

The following must always hold:

1. A derived boundary cannot form before its governing Liquidity Level is `FROZEN`.
2. Derived-boundary formation requires a strict wick beyond the Liquidity Level.
3. Touching the Liquidity Level is insufficient.
4. Only authorized completed candles may form, evaluate, progress, confirm, or freeze a derived boundary.
5. An unauthorized candle produces no boundary evaluation or change.
6. An unauthorized candle is not a failed confirmation candle.
7. A boundary-formation candle cannot confirm its newly formed boundary.
8. Every authorized evaluation of an existing provisional boundary uses the committed pre-candle `P_in`.
9. Confirmation is evaluated before same-candle progression.
10. Confirmation and progression are mutually exclusive for one boundary and candle.
11. The exact value tested is the exact value frozen.
12. Equal wick extremes do not progress a boundary.
13. A frozen boundary has no outgoing boundary transition.
14. The Rejection Candidate exclusively owns the Rejection Boundary before confirmation.
15. The Candidate must exist no later than initial provisional boundary formation.
16. The Rejection Lifecycle owns the frozen Rejection Boundary after atomic adoption.
17. The Candidate remains historical lineage, not a second active owner.
18. Rejection Count 0 is the Rejection Step 2 confirmation candle.
19. No retired Leg 1 or Leg 2 predicate is required for Rejection Step 2.
20. No retired pattern sequence is required for Rejection Step 2.
21. No Step 4 participation or qualification predicate is required for Rejection Step 2.
22. ADR-006 alone governs the approved Rejection Step 4 Count Window.
23. ADR-007 alone governs the approved Rejection Step 4 Participation Rule.
24. ADR-009 does not change or reinterpret ADR-006 or ADR-007.
25. Later Step 4 outcomes cannot alter accepted Step 2 or its frozen Rejection Boundary.
26. Continuation Eligibility cannot own, form, progress, or freeze a Continuation Boundary.
27. A Continuation Boundary is not copied from the Rejection Boundary.
28. A Continuation Boundary cannot exist before its Continuation Lifecycle identity.
29. ADR-009 does not authorize a Continuation Lifecycle with an `ABSENT` boundary.
30. Rejection and Continuation Boundaries cannot mutate one another.
31. Session termination cannot freeze an unconfirmed provisional boundary.
32. A missing Liquidity Level cannot receive a substitute value.
33. Approval of ADR-009 authorizes creation of this ADR-009 file but does not authorize implementation or modification of any other file.

## 19. Consequences

### Positive consequences

- Rejection Step 2 has one precise responsibility.
- Boundary formation, progression, confirmation, and freeze are explicit.
- The tested boundary and frozen boundary are identical.
- Confirmation remains reachable.
- Completed-candle processing is deterministic.
- Intrabar event order cannot move the same candle’s confirmation target.
- Farther provisional extremes are preserved without mutating frozen facts.
- No retired Step 2 predicate survives as hidden Step 4 behavior.
- ADR-006 and ADR-007 remain unchanged.
- Rejection and Continuation retain independent boundary identities and histories.
- Continuation Creation sequencing remains open for its dedicated ADR.

### Costs and required follow-up

- Candidate progression and evaluation history must remain architecturally preserved.
- Existing canonical documents contain retired pattern requirements and require authorized alignment.
- ADR-008 contains copied-and-frozen Continuation Boundary language requiring narrow alignment.
- Lifecycle Vocabulary requires provisional derived-boundary terminology.
- A versioned Liquidity Level Calculation Contract remains required.
- Corrected-candle and out-of-order handling remain dependent on a canonical system-wide market-data contract.

These follow-up requirements did not delay the effect of ADR-009 upon approval. Approval authorizes creation of this ADR-009 file only; it does not authorize the follow-up documentation alignment or any implementation change.

## 20. Explicitly Superseded Rejection Step 2 Rules

### Disposition definitions

**REPLACED BY ADR-009** means ADR-009 supplies the governing replacement rule.

**SUPERSEDED AND REMOVED; NOT REASSIGNED** means:

- the rule no longer governs Rejection Step 2;
- it is not moved into participation;
- it is not moved into Step 4 qualification;
- it is not preserved as a dormant, fallback, supplemental, or hidden predicate;
- it may return only through a separately approved future ADR defining a new purpose.

**UNAFFECTED** means the existing rule remains governing without reinterpretation by ADR-009.

**REQUIRES DOCUMENTATION ALIGNMENT** means a document must later be revised to express the approved architecture. The stale language ceased to govern when ADR-009 was approved. Documentation alignment is not authorized by this ADR approval.

### Rule supersession ledger

| Existing rule or requirement | Disposition |
|---|---|
| Leg 1 as a mandatory Rejection Step 2 pattern component | **SUPERSEDED AND REMOVED; NOT REASSIGNED** |
| Leg 2 as a mandatory Rejection Step 2 pattern component | **SUPERSEDED AND REMOVED; NOT REASSIGNED** |
| Leg 1 Close as the Rejection Step 2 confirmation reference | **SUPERSEDED AND REMOVED; NOT REASSIGNED** |
| Upper/SHORT confirmation requiring Leg 2 Close below Leg 1 Close | **REPLACED BY ADR-009** |
| Lower/LONG confirmation requiring Leg 2 Close above Leg 1 Close | **REPLACED BY ADR-009** |
| Leg 1/Leg 2 sequence requirements used solely by the retired confirmation model | **SUPERSEDED AND REMOVED; NOT REASSIGNED** |
| Delegated Rejection Boundary derivation conflicting with strict-wick formation | **REPLACED BY ADR-009** |
| Retired interaction, sweep, entry-type pattern, and volatility gates attached to the old Step 2 pattern | **SUPERSEDED AND REMOVED; NOT REASSIGNED** |
| Universal session, symbol, instrument, contract, data-authority, identity, lineage, ordering, uniqueness, and idempotency guards | **UNAFFECTED** |
| Rejection Count 0 identity | **UNAFFECTED** |
| ADR-006 Rejection Step 4 Count Window | **UNAFFECTED** |
| ADR-007 Rejection Step 4 Participation Rule | **UNAFFECTED** |
| Unaffected ADR-008 Eligibility, lineage, uniqueness, session, and atomicity decisions | **UNAFFECTED** |
| ADR-008 copied-and-immediately-frozen Continuation Boundary presumption | **REPLACED BY ADR-009** |

### Constitutional and documentation alignment ledger

| Document and affected area | Disposition |
|---|---|
| `Architecture/00_Randle_AI_Constitution.md` — Rejection Step 2-specific Leg 1 evidence references in lifecycle-truth and Step 2 field lists | **REQUIRES DOCUMENTATION ALIGNMENT** |
| `Architecture/01_Randle_AI_Lifecycle_Vocabulary.md` — mandatory Leg terminology and frozen-only boundary definitions | **REQUIRES DOCUMENTATION ALIGNMENT** |
| `Architecture/02_Randle_AI_Lifecycle_Engine_Specification.md` — governance language needed to record the narrow approved amendment mechanism | **REQUIRES DOCUMENTATION ALIGNMENT** |
| `Architecture/03_Randle_AI_Rejection_Step2_Lifecycle_Specification.md` — retired pattern, price predicates, sequence, evidence, boundary derivation, invariants, and associated requirements | **REQUIRES DOCUMENTATION ALIGNMENT** |
| `Architecture/Decisions/ADR-008_Rejection_Step4_Continuation_Eligibility_Handoff.md` — copied-and-frozen Continuation Boundary statements and dependencies | **REQUIRES DOCUMENTATION ALIGNMENT** |

Effective upon approval, the identified constitutional references ceased to require Leg-based Rejection Step 2 evidence. Their universal evidence-preservation purpose remains governing and is satisfied by preserved Candidate identity, boundary-formation history, provisional progression history, authorized evaluation history, confirmation candle, frozen boundary, lineage, and rule version.

This is a narrow constitutional amendment. It does not weaken or supersede any unaffected universal constitutional invariant.

## 21. Narrow ADR-008 Supersession

ADR-008 remains approved except where it states or depends on the presumption that:

- the frozen Rejection Boundary is copied as the Continuation Boundary at Continuation Eligibility creation;
- the Continuation Boundary freezes at Eligibility creation;
- Continuation Eligibility or its handoff record owns that Continuation Boundary;
- ADR-008’s atomic Eligibility handoff includes a copied-and-frozen Continuation Boundary.

ADR-009 supersedes only that copied-and-immediately-frozen Continuation Boundary model.

The following ADR-008 decisions remain governing:

- accepted Rejection Step 4 Confirmation produces Continuation Eligibility;
- Eligibility creation is atomic with accepted Step 4 Confirmation;
- Eligibility is unique for its accepted rejection;
- Eligibility may produce at most one Continuation Lifecycle;
- Continuation Creation consumes Eligibility;
- the Rejection parent remains terminal and immutable;
- parent and Eligibility lineage remain preserved;
- session isolation remains governing;
- duplicate processing remains idempotent;
- Continuation Creation and Evaluation Start remain outside ADR-008.

Later alignment of ADR-008 will record this narrow supersession. ADR-009 does not otherwise revise ADR-008, and its approval does not authorize that alignment.

## 22. Deferred Decisions and Required Contracts

The following remain intentionally outside ADR-009:

- Liquidity Level formation-window start and end;
- Liquidity Level price calculation;
- Liquidity Level upper/lower output set;
- exact market-interval membership at 06:15;
- canonical corrected-candle rules;
- canonical out-of-order-data rules;
- exact Rejection Candidate establishment sequencing before or with initial boundary formation;
- Continuation Creation market trigger;
- whether Continuation Creation precedes initial boundary formation or occurs atomically with it;
- Continuation Evaluation Start;
- continuation direction mapping;
- continuation Count 0;
- continuation participation;
- continuation Step 4;
- multi-owner candle routing;
- precise Candidate or Lifecycle terminal-session deadlines.

Required future contracts include:

- a versioned Liquidity Level Calculation Contract;
- a canonical market-data correction and ordering contract;
- a Continuation Creation ADR;
- an authorized canonical-document alignment revision.

These deferred matters do not reopen ADR-009’s strict-wick formation, provisional progression, confirmation-first precedence, one-tick close, freeze-at-`P_in`, ownership, or post-freeze immutability decisions.

They were not blockers to approval of ADR-009’s boundary architecture.

## 23. Non-goals

ADR-009 does not define or authorize:

- code;
- tests;
- runtime migration;
- persistence technology;
- database schemas;
- APIs;
- projections;
- implementation architecture;
- Continuation Creation behavior;
- continuation participation;
- continuation Step 4;
- entries;
- execution;
- risk management;
- position management;
- modification of any other architecture document;
- canonical-document alignment;
- staging or committing changes.

Creation of this ADR-009 file is expressly authorized by the owner’s July 11, 2026 ratification instruction.

## 24. Worked Examples

All candles in these examples are completed and authorized.

### Upper confirmation with a farther wick

Given:

- incoming upper provisional boundary: `100.00`;
- candle high: `100.03`;
- candle close: `100.01`;
- tick size: `0.01`.

The required confirmation close is `100.01`.

Result:

- the close confirms;
- `100.00` freezes;
- the wick to `100.03` does not progress the boundary;
- the confirming candle becomes Rejection Count 0;
- no Step 4 participation or qualification result is evaluated as part of Step 2;
- ADR-006 and ADR-007 remain the exclusive authorities for their respective Step 4 subjects.

Freezing `100.03` would be invalid because that value was not tested.

Progressing to `100.03` before evaluating the close would be invalid because it would replace the current candle’s confirmation target.

### Lower confirmation with a farther wick

Given:

- incoming lower provisional boundary: `100.00`;
- candle low: `99.97`;
- candle close: `99.99`;
- tick size: `0.01`.

The required confirmation close is `99.99`.

Result:

- the close confirms;
- `100.00` freezes;
- the wick to `99.97` does not progress the boundary;
- the confirming candle becomes Rejection Count 0;
- no Step 4 participation or qualification result is evaluated as part of Step 2.

### Failed close with outward progression

Given:

- incoming upper provisional boundary: `100.00`;
- candle high: `100.03`;
- candle close: `100.00`;
- tick size: `0.01`.

The required confirmation close is `100.01`.

Result:

- the close fails;
- the high is strictly farther outward;
- the boundary remains `PROVISIONAL`;
- its value progresses to `100.03`;
- no Rejection Lifecycle is created;
- no Rejection Count 0 is established.

### Failed close without progression

Given:

- incoming lower provisional boundary: `100.00`;
- candle low: `100.00`;
- candle close: `100.00`;
- tick size: `0.01`.

The required confirmation close is `99.99`.

Result:

- the close fails;
- the low equals, rather than falls below, the incoming boundary;
- equal extremes do not progress a boundary;
- the boundary remains `PROVISIONAL` at `100.00`;
- no Rejection Lifecycle is created;
- no Rejection Count 0 is established.

## 25. Approval Checklist

ADR-009 was explicitly approved effective July 11, 2026:

- [x] The retired Rejection Step 2 Leg 1/Leg 2 model is expressly replaced.
- [x] No retired close predicate survives as a hidden prerequisite.
- [x] No retired rule is reassigned to participation or Step 4.
- [x] Strict-wick provisional-boundary formation is accepted.
- [x] Confirmation-first candle precedence is accepted.
- [x] The one-tick upper and lower confirmation predicates are accepted.
- [x] Freeze-at-`P_in` is accepted.
- [x] Candidate ownership and atomic Lifecycle adoption are accepted.
- [x] Rejection Count 0 remains the Step 2 confirmation candle.
- [x] Step 4 participation and qualification remain separate from Step 2.
- [x] ADR-006 and ADR-007 remain unchanged.
- [x] Continuation uses independent boundary mechanics.
- [x] No Continuation Boundary may exist before its Lifecycle identity.
- [x] ADR-009 does not authorize a Continuation Lifecycle with an `ABSENT` boundary.
- [x] ADR-008 supersession remains narrow.
- [x] Liquidity Level aggregate-root ownership is accepted.
- [x] The 06:15 `America/Los_Angeles` freeze is accepted.
- [x] The narrow constitutional amendment is accepted.
- [x] Deferred matters remain outside ADR-009.
- [x] No implementation or modification of any other architecture document is authorized.

### Final consistency statement

This approved ADR confirms that:

- no retired Leg 1/Leg 2 rule remains;
- no retired rule was reassigned into participation or Step 4;
- no close relative to Leg 1 remains relevant to Rejection Step 2;
- no retired pattern sequence remains relevant;
- no Continuation Boundary exists before its Continuation Lifecycle identity;
- ADR-009 does not authorize an ownerless or presently unauthorized `ABSENT` Continuation Boundary;
- ADR-006 and ADR-007 were not modified, restated, or reinterpreted;
- ADR-008 supersession remains limited to its copied-and-immediately-frozen Continuation Boundary presumption;
- constitutional supersession is limited to the specifically identified Rejection Step 2 Leg and boundary statements;
- all unaffected constitutional and universal invariants remain governing;
- no missing Liquidity Level receives a substitute value;
- approval authorizes creation of this ADR-009 file only and does not authorize implementation, modification of any other architecture document, canonical-document alignment, tests, migration, runtime changes, staging, or a commit.

### Remaining owner decisions

None.
