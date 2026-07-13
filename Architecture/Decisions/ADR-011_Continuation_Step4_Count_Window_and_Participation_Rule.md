# ADR-011 — Continuation Step 4 Count Window and Participation Rule

## 1. Status

**APPROVED**

Decision date: 2026-07-13  
Owner approval date: 2026-07-13

Approval authorizes architecture and canonical-document alignment only. It authorizes no implementation, test, persistence, migration, API, deployment, execution, risk, or position-management change.

## 2. Context

ADR-009 governs Continuation Boundary mechanics and Continuation Step 2 Confirmation. ADR-010 governs Continuation Creation, initial Boundary formation, Evaluation Start, one-minute candle authority, and governing-Liquidity-Level consumption precedence.

ADR-010 deferred Continuation Count 0, Participation, Count Window, and Step 4. This ADR supplies those post-Step-2 rules.

ADR-007 approved the 34% threshold, direction labels, and `OR` relationship for Rejection Participation, but referenced an existing wick-participation formula without stating its mathematics. This ADR records the owner-approved mathematics and independently adopts it for Continuation.

## 3. Decision

This ADR establishes:

- Continuation Step 2 Confirmation as immutable Continuation Count 0;
- a fixed Continuation Count Window with Counts 1 through 4;
- Count 0 as the immediately previous candle for Count 1;
- the current-candle opposing-wick formula stated in this ADR;
- `OR` between wick and directional-close predicates;
- direct, atomic Continuation Step 4 Confirmation from the first qualifying Count;
- Count 4 and session-expiration Step 4 expiration;
- consumption-first handling and post-Step-2 pre-Step-4 invalidation;
- one-minute evidence, identity, duplicate, restart, and replay requirements.

This ADR creates no new Boundary, Liquidity Level, or other liquidity or Boundary price object.

## 4. Continuation Count 0

The authoritative completed one-minute candle that confirms Continuation Step 2 under ADR-009 SHALL become Continuation Count 0.

Count 0 SHALL preserve or stably reference Continuation Lifecycle identity; Continuation Step 2 Confirmation identity; frozen Continuation Boundary identity; exact frozen `P_in`; governing `liquidity_level_id`; completed one-minute candle identity and OHLC; canonical ordering evidence; session, symbol, instrument, and contract; correction-and-ordering contract version; and rule and schema versions.

Count 0 initializes the fixed Continuation Count Window, does not participate, cannot confirm Continuation Step 4, cannot expire the Count Window, cannot be replaced, rolled, or reseeded, and is the immediately previous candle for Count 1.

The earliest possible Continuation Step 4 Confirmation is Count 1. Continuation Creation, initial Boundary formation, and Evaluation Start remain non-counting under ADR-010. The formation candle is not Count 0.

## 5. Fixed Count Window

| Count | Meaning |
|---|---|
| Count 0 | Immutable Continuation Step 2 Confirmation candle; non-participating |
| Count 1 | First Participation opportunity |
| Count 2 | Second Participation opportunity |
| Count 3 | Third Participation opportunity |
| Count 4 | Fourth and final Participation opportunity |

No Count 5 or later Count is authorized.

Each Count 1 through Count 4 candidate SHALL be an authoritative completed one-minute candle; the next distinct candle in canonical finalized order; in the same symbol, session, instrument, and contract; authorized by the canonical correction-and-ordering contract; and processed only after governing-Liquidity-Level consumption precedence.

The Count Window is fixed and non-expanding. It does not authorize a rolling Count 0, new anchor, reset, restart, reseed, skipped Count, substituted candle, favorable-later-candle selection, pause with retained later Counts, attempt aggregate, or retry aggregate.

## 6. Count ordering and previous-candle relationship

Each Participation candidate compares only with the immediately previous Count candle:

- Count 1 compares with Count 0;
- Count 2 compares with Count 1;
- Count 3 compares with Count 2;
- Count 4 compares with Count 3.

The immediately previous candle is not the most recent favorable or qualifying candle, Count 0 for every later Count, a rolling Candle A, a separately selected anchor, or an intrabar value.

A failed Participation Count becomes the immediately previous Count candle for the next authorized Count.

## 7. Continuation Participation

Let the current Continuation Count candle have completed OHLC:

- `O` = open;
- `H` = high;
- `L` = low;
- `C` = close.

Its complete range is:

```text
R = H - L
```

The wick predicate uses only the current Continuation Count candle’s OHLC. The immediately previous Count candle is not used for wick, range, body, high, or low calculations.

A candle with incomplete OHLC, malformed prices, non-authoritative normalization, or `R <= 0` cannot satisfy wick Participation and cannot be used to invent a percentage. The canonical market-data correction-and-ordering contract determines whether such a source is corrected, excluded, or otherwise made authoritative. This ADR does not terminate, expand, pause, or restart the Count Window solely because an input is malformed.

Participation is satisfied if either independent predicate is true:

1. the applicable current-candle opposing-wick predicate; **or**
2. the applicable Continuation-direction completed-close predicate.

Only one predicate is required. Both are not required. All prices and calculations SHALL use the authoritative canonical tick-size and normalization sources.

## 8. Directional Participation rules

The immutable child Continuation direction controls wick orientation and directional-close selection. Participation direction is not re-derived from the parent Rejection direction.

### Continuation LONG

The opposing wick is the current Count candle’s lower wick:

```text
W_long = min(O, C) - L
P_long = W_long / R
P_long >= 0.34
```

Equivalent percentage form:

```text
100 × W_long / R >= 34
```

Continuation LONG Participation is:

```text
P_long >= 0.34
OR
current Count completed close > immediately previous Count completed close
```

### Continuation SHORT

The opposing wick is the current Count candle’s upper wick:

```text
W_short = H - max(O, C)
P_short = W_short / R
P_short >= 0.34
```

Equivalent percentage form:

```text
100 × W_short / R >= 34
```

Continuation SHORT Participation is:

```text
P_short >= 0.34
OR
current Count completed close < immediately previous Count completed close
```

At least 34% is inclusive. Exactly 34% qualifies.

For directional-close Participation, candle open, candle color, intrabar route, prior-side crossing, and earlier candle route are irrelevant. Only the two completed closes are compared. No additional Boundary test, Liquidity Level close, reclaim, reversal route, candle-color rule, trend test, or percentage rule is authorized.

## 9. Continuation Step 4 Confirmation

A qualifying Participation result directly and atomically produces Continuation Step 4 Confirmation.

There is no separate Confirmation candle, second pattern, additional Boundary close, Liquidity Level close, percentage threshold, reclaim, reversal path, candle-color rule, trend test, or multi-candle Confirmation sequence.

The first Count from Count 1 through Count 4 that satisfies Participation SHALL become the confirming Continuation Count, record the qualifying predicate or predicates, produce Continuation Step 4 CONFIRMED, and terminate the Count Window immediately.

A Count satisfying both predicates remains one Participation result and one Step 4 Confirmation.

## 10. Failed Count behavior

When Count 1, Count 2, or Count 3 does not satisfy Participation, Step 4 remains unconfirmed; the failed Count remains immutable historical evidence; the next distinct authorized one-minute candle receives the next Count number; and the failed Count becomes the immediately previous candle for the next Participation evaluation.

No failed Count may change Count 0, reopen Continuation Step 2, change the frozen Continuation Boundary, change `P_in`, change governing `liquidity_level_id`, restart, reseed, roll, or expand the Count Window, or create an attempt or retry aggregate.

## 11. Count 4 and session expiration

Count 4 is the final Participation opportunity.

When Count 4 does not satisfy Participation, Continuation Step 4 becomes EXPIRED, the Count Window terminates, no Count 5 exists, Step 4 cannot later confirm from that lineage, and frozen Continuation Boundary, accepted Step 2, and lineage facts remain immutable.

EXPIRED is also the terminal Step 4 outcome when canonical session expiration occurs before Step 4 confirms.

If no separately governing canonical session-expiration instant is available, ADR-011 does not invent one. Count 4 failure remains independently sufficient to produce EXPIRED. Session expiration does not authorize pausing, expanding, restarting, reseeding, or replacing the Count Window.

## 12. Governing-Liquidity-Level consumption precedence

ADR-010’s next-Liquidity-Level consumption rule remains governing.

For every potential Count candle:

1. Validate session, symbol, instrument, contract, ordering, and candle authority.
2. Validate that the inherited governing Liquidity Level still has authority.
3. Determine whether the candle reaches the next distinct outside Liquidity Level.
4. If it does, process consumption first.
5. Only if authority remains active may the candle receive a Continuation Count.
6. Only an assigned Count may be evaluated for Participation.
7. Only valid Participation may confirm Continuation Step 4.

A candle that consumes the governing Liquidity Level receives no Count, is not evaluated for Participation, cannot confirm Step 4, and cannot preserve later Count opportunities.

## 13. Consumption after Step 2 but before Step 4

When the inherited governing Liquidity Level is consumed after accepted Continuation Step 2 but before Continuation Step 4 Confirmation, accepted parent Rejection facts remain immutable; Continuation Eligibility remains CONSUMED; Continuation Creation remains immutable; the frozen Continuation Boundary remains immutable; Continuation Step 2 Confirmation remains immutable; Continuation Count 0 remains immutable; remaining Count Window authority ends; no later Count is assigned; and Continuation Step 4 becomes INVALIDATED.

INVALIDATED is distinct from CONFIRMED and EXPIRED. Consumption does not return the Boundary to PROVISIONAL or ABSENT and does not reopen or undo Continuation Step 2.

## 14. Same-candle Participation and consumption

When a potential Count candle otherwise satisfies Participation and reaches the next distinct outside Liquidity Level:

1. recognize next-Level reach;
2. consume the inherited governing Liquidity Level;
3. end Count Window authority;
4. do not assign a Count;
5. do not evaluate Participation;
6. do not confirm Step 4;
7. produce Continuation Step 4 INVALIDATED.

The candle’s close or apparent wick-participation result cannot revive consumed authority.

## 15. Consumption after Step 4

When Continuation Step 4 confirmed on an earlier Count, Step 4 Confirmation, the confirming Count, and the frozen Continuation Boundary remain immutable. Later Liquidity Level consumption cannot change CONFIRMED to INVALIDATED or EXPIRED and cannot reopen the Count Window.

Any downstream post-Step-4 lifecycle consequence remains outside ADR-011.

## 16. Terminal outcomes

ADR-011 authorizes exactly these Continuation Step 4 terminal outcomes:

| Outcome | Produced by |
|---|---|
| CONFIRMED | First Count 1–4 Participation result |
| EXPIRED | Failed Count 4, or canonical session expiration before Step 4 confirms |
| INVALIDATED | Governing-Liquidity-Level consumption after Step 2 and before Step 4 confirms |

These are Step 4 lifecycle outcomes. They are not Liquidity Level value states, Boundary states, Eligibility states, or new price objects.

The Continuation Boundary remains FROZEN after accepted Continuation Step 2 regardless of later Step 4 outcome.

## 17. Immutable lineage

ADR-011 cannot alter governing `liquidity_level_id`; parent Rejection Step 2 Confirmation; frozen Rejection Boundary; parent Rejection Count 0; accepted parent Rejection Step 4; CONSUMED Continuation Eligibility; Continuation Creation; Continuation Lifecycle identity; frozen Continuation Boundary; exact frozen `P_in`; Continuation Step 2 Confirmation; or Continuation Count 0.

No Step 4 result may reopen, rewrite, replace, delete, reseed, or transfer these facts.

## 18. One-minute candle authority

All Continuation Count Window and Participation operations use authoritative completed one-minute candles from the canonical one-minute series.

No other interval, aggregated candle, incomplete candle, intrabar fact, tick-only input, temporary candle version, or arrival-order event may assign a Count, evaluate Participation, or produce Step 4 outcome.

Canonical finalized ordering governs.

## 19. Atomicity

For a qualifying Count candle, Count assignment, Participation evaluation, qualifying-predicate evidence, confirming Count identity, Continuation Step 4 CONFIRMED, and Count Window closure SHALL be one atomic domain result.

For failed Count 1 through Count 3, Count assignment and failed Participation evidence SHALL commit together.

For failed Count 4, Count 4 assignment, failed Participation result, Continuation Step 4 EXPIRED, and Count Window closure SHALL be one atomic domain result.

For pre-Step-4 consumption, next-Level reach, governing-Liquidity-Level consumption, loss of Count Window authority, and Continuation Step 4 INVALIDATED SHALL be one atomic domain result.

No authoritative partial state is permitted. This ADR defines domain atomicity only and selects no implementation technology.

## 20. Duplicate, restart, correction, and replay

Duplicate processing SHALL resolve to existing Count and outcome identities. It cannot assign the same Count twice, evaluate Participation twice, or confirm, expire, or invalidate Step 4 twice.

Restart SHALL restore immutable Count 0, all committed Counts, immediately previous Count identity, next Count number, current Step 4 outcome, and governing-Liquidity-Level authority state.

Replay SHALL reproduce the same Count assignments, previous-candle relationships, Participation results, confirming, expiring, or invalidating source, and terminal outcome.

Corrected authoritative history remains governed by the canonical correction-and-ordering contract. ADR-011 does not define correction mechanics.

## 21. Identity and evidence

The architecture SHALL preserve or stably reference:

- `continuation_lifecycle_id`;
- `parent_rejection_lifecycle_id`;
- `continuation_eligibility_id`;
- governing `liquidity_level_id`;
- frozen Continuation Boundary identity and frozen `P_in`;
- Continuation Step 2 Confirmation and Count 0 identities;
- every assigned Count number, Count candle identity, and immediately previous Count identity;
- completed OHLC, canonical one-minute series identity, interval designation, symbol, session, instrument, contract, and canonical order;
- correction-and-ordering contract version and canonical tick-size source identity and version;
- ADR-007 decision identity, locked owner formula source, and ADR-011 formula adoption identity and version;
- current-candle full range, opposing wick, wick ratio, threshold result, directional-close result, Participation result, and qualifying predicate or predicates;
- confirming Count identity when CONFIRMED, Count 4 identity when EXPIRED through failure, session-expiration identity when EXPIRED through session termination, consumption evidence when INVALIDATED, terminal outcome, and rule and schema versions.

A later ADR-007 amendment does not silently change this Continuation formula. Changing Continuation wick Participation requires an explicit ADR-011 amendment or later approved superseding Continuation decision.

This ADR selects no database, event store, payload, API, persistence, serialization, or identifier-encoding design.

## 22. ADR relationships

- ADR-006 remains governing for Rejection Count Window behavior.
- ADR-007 remains governing for Rejection Participation behavior.
- ADR-008 remains governing for Rejection Step 4 to Continuation Eligibility.
- ADR-009 remains governing for Continuation Boundary mechanics and Continuation Step 2 Confirmation.
- ADR-010 remains governing for Continuation Creation, initial Boundary formation, Evaluation Start, one-minute authority, and governing-Liquidity-Level consumption.
- ADR-011 independently adopts the simple four-opportunity structure and current-candle opposing-wick mathematics for Continuation.
- ADR-011 defines Continuation Count 0, Count Window, Participation, Step 4 Confirmation, EXPIRED, and post-Step-2 pre-Step-4 INVALIDATED.
- ADR-011 does not modify Rejection rules.

ADR-011 canonically records the previously referenced but unstated 34% wick-participation mathematics. The formula completion is a narrow documentation and architecture amendment to ADR-007. It does not change ADR-007’s approved threshold, direction, `OR` relationship, Count Window, or Rejection Participation behavior.

ADR-007 remains the Rejection authority. ADR-011 is the separate Continuation authority.

## 23. Explicitly rejected alternatives

Reject Count 0 Participation; same-candle Continuation Step 2 and Step 4 Confirmation; fewer or more than four post-Step-2 opportunities; Count 5; rolling, replacing, or reseeding Count 0; Candle A or Candle B; Leg terminology; another Boundary; another liquidity or Boundary price object; another governing Liquidity Level; level switching; Count restart, reseed, skipped Count, or favorable later-candle selection; intrabar Participation; interval substitution; `AND` instead of `OR`; wick calculation from the previous Count candle; a wick threshold other than inclusive 34%; another directional-close predicate; another Confirmation candle after Participation; Step 4 from consumed authority; retroactive mutation of accepted Step 2 or frozen Boundary facts; and implementation authority.

## 24. Deferred matters

Outside ADR-011 are behavior after confirmed Continuation Step 4; entry eligibility and timing; execution; risk; stop, target, and trade-management prices; position management; replacement dynamic stack routing; Liquidity Level calculations; tied-stack tie-break implementation; market-data correction mechanics; contract-rollover handling; implementation; tests; migration; and deployment.

## 25. Consequences

Benefits include one deterministic post-Step-2 Continuation shape; explicit Count 0 and fixed Count Window; unambiguous current-candle wick mathematics; clear current-wick versus previous-close separation; no ambiguous Participation anchor; direct Step 4 confirmation; no Count 5 or hidden retry state; consumption-first protection; and immutable parent, child, Boundary, and Count lineage.

Costs and dependencies include ADR-007 formula alignment without Rejection behavior change; canonical correction-and-ordering authority; a session-expiration contract; deferred post-Step-4 lifecycle behavior; later correction of stale ADR-010 documentation; and continued implementation separation.

## 26. Non-goals

ADR-011 does not define Continuation Creation, Boundary mechanics, `P_in`, Level selection, stack selection, parent Rejection rules, entry, execution, risk, position management, persistence technology, schemas, APIs, migrations, deployment, tests, or implementation.

## 27. Worked examples

1. **Continuation LONG higher-close Participation.** Count 0 closes at 100.00. Count 1 closes at 100.10. The close predicate qualifies, Count 1 directly confirms Step 4, and the window closes.

2. **Continuation SHORT lower-close Participation.** Count 1 fails. Count 2 closes below Count 1. Count 2 directly confirms Step 4.

3. **Continuation LONG wick-only Participation.** The immediately previous Count close is 100.50 or higher. The current Count has:

   ```text
   O = 100.60
   H = 100.80
   L = 100.00
   C = 100.50
   R = 100.80 - 100.00 = 0.80
   W_long = min(100.60, 100.50) - 100.00 = 0.50
   P_long = 0.50 / 0.80 = 0.625 = 62.5%
   ```

   `62.5% >= 34%`, so the wick predicate qualifies. The higher-close predicate fails because 100.50 is not higher than the previous close. The Count directly confirms Step 4 through wick-only Participation.

4. **Continuation SHORT wick-only Participation.** The immediately previous Count close is 100.30 or lower. The current Count has:

   ```text
   O = 100.20
   H = 101.00
   L = 100.00
   C = 100.30
   R = 101.00 - 100.00 = 1.00
   W_short = 101.00 - max(100.20, 100.30) = 0.70
   P_short = 0.70 / 1.00 = 0.70 = 70%
   ```

   `70% >= 34%`, so the wick predicate qualifies. The lower-close predicate fails because 100.30 is not lower than the previous close. The Count directly confirms Step 4 through wick-only Participation.

5. **Both predicates qualify.** A Count has a qualifying opposing wick and a qualifying directional close. It produces one Participation result and one Step 4 Confirmation.

6. **Counts 1 through 3 fail.** Each failed Count becomes the immediately previous Count candle for the next evaluation. Count 3 compares with Count 2, not Count 0.

7. **Count 4 fails.** Count 4 fails both predicates. Step 4 becomes EXPIRED and Count 5 cannot be assigned.

8. **Count 0 does not participate.** Continuation Step 2 Confirmation becomes Count 0 even if its OHLC appears favorable. It cannot confirm Step 4.

9. **Consumption before Count.** A potential Count candle reaches the next outside Liquidity Level. Consumption occurs first; no Count is assigned, Participation is not evaluated, and Step 4 becomes INVALIDATED.

10. **Consumption after confirmed Step 4.** Count 1 already confirmed Step 4. A later candle reaches the next outside Liquidity Level. Step 4 remains CONFIRMED, the confirming Count remains immutable, and the frozen Continuation Boundary remains immutable.

11. **Duplicate and restart.** Duplicate delivery resolves to the same Count and outcome. Restart restores Count 0, prior Counts, current outcome, and the next legal Count.

## 28. Approval checklist

- [ ] Continuation Step 2 Confirmation becomes Count 0
- [ ] Count 0 does not participate
- [ ] Count 1 compares with Count 0
- [ ] Four fixed Participation opportunities
- [ ] Count 4 finality
- [ ] Current-candle full-range formula
- [ ] LONG lower-wick formula
- [ ] SHORT upper-wick formula
- [ ] Inclusive 34% threshold
- [ ] Current-candle wick versus previous-Count close distinction
- [ ] Higher close for Continuation LONG
- [ ] Lower close for Continuation SHORT
- [ ] Wick OR directional close
- [ ] First qualifying Count directly confirms Step 4
- [ ] Count Window closes immediately on Confirmation
- [ ] Failed Counts 1–3 advance
- [ ] Failed Count 4 EXPIRES
- [ ] Session expiration EXPIRES
- [ ] No Count 5
- [ ] No restart or reseed
- [ ] One-minute authority
- [ ] Consumption before Count assignment
- [ ] Post-Step-2 pre-Step-4 consumption INVALIDATES
- [ ] Post-Step-4 immutability
- [ ] Immutable lineage
- [ ] Duplicate and replay guarantees
- [ ] No implementation authority
