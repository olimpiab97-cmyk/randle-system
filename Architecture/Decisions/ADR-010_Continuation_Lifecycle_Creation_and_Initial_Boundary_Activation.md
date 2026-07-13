# ADR-010 — Continuation Lifecycle Creation and Initial Boundary Activation

## 1. Status

**APPROVED**

Date: 2026-07-13
Owner approval: 2026-07-13
Approval scope: canonical architecture and documentation alignment only. This ADR authorizes no implementation, schema, migration, API, test, deployment, or execution change.

## 2. Context

ADR-008 deliberately stops at one AVAILABLE Continuation Eligibility after an accepted Rejection Step 4 Confirmation. ADR-009 deliberately defines Boundary ownership and later Boundary mechanics without defining Continuation Creation, initial Continuation Boundary formation, or Continuation Evaluation Start.

This ADR supplies those deferred rules. It also establishes the governing Liquidity Level authority that must remain valid for the Rejection-to-Continuation lineage, the canonical one-minute candle source for that chain, and the effect of reaching the next Liquidity Level.

The parent Rejection remains the authority for its own validity, its Count Window, its Participation rule, and Step 4 acceptance. This ADR does not reopen those decisions.

## 3. Decision

For one authoritative Rejection-to-Continuation lineage, exactly one approved, frozen Liquidity Level has governing authority. Its immutable `liquidity_level_id` is inherited by the Rejection, ADR-008 Eligibility, and any Continuation child.

An accepted Rejection Step 4 Confirmation creates one AVAILABLE Continuation Eligibility under ADR-008. If the same authoritative completed one-minute candle satisfies this ADR's Creation predicate, it SHALL be the Creation source. Otherwise, the first later qualifying authoritative completed one-minute candle in canonical finalized order SHALL be the Creation source. The system cannot skip that candle for a later candle.

Creation, AVAILABLE-to-CONSUMED Eligibility transition, child lineage, initial PROVISIONAL Continuation Boundary formation, and Evaluation Start are one atomic child-side result. The formation candle is excluded from Continuation Step 2 evaluation. Later Boundary mechanics remain governed by ADR-009.

Before Creation, consumption of the exact inherited governing Liquidity Level transitions AVAILABLE Eligibility to INVALIDATED. After Creation, consumption ends Continuation Boundary evaluation authority as specified here; it does not alter accepted parent facts or a Boundary already frozen by Continuation Step 2.

## 4. Exclusive price-object vocabulary

Within the Liquidity Level, Rejection Boundary, and Continuation Boundary architecture governed by ADR-009 and ADR-010, there are exactly three authoritative liquidity and boundary price objects:

1. Liquidity Level
2. Rejection Boundary
3. Continuation Boundary

No fourth liquidity or boundary price object is authorized. In particular, Liquidity Context, Close Boundary, Extreme Boundary, Wick Boundary Extreme, Internal Effective Boundary, Stack Boundary, Reference Boundary, and synthetic, blended, or effective stack price are retired and non-governing terms.

An upper or lower Rejection Boundary is a directional description of a Rejection Boundary. An upper or lower Continuation Boundary is a directional description of a Continuation Boundary. Neither creates another object type.

This limitation applies only to this liquidity and boundary architecture. It does not define or prohibit future, separately governed entry, order, fill, stop, target, execution, risk, or position-management prices.

## 5. Canonical one-minute candle authority

For this Rejection-to-Continuation lifecycle chain, every normative reference to a completed candle means an **authoritative completed one-minute candle from the canonical one-minute series**.

This authority applies to Rejection Boundary formation and progression, Rejection Step 2 and Count 0, the ADR-006 Count Window, the ADR-007 Participation Rule, Rejection Step 4 Confirmation, ADR-008 Eligibility handoff, Continuation Creation, initial Continuation Boundary formation, Evaluation Start, and later Continuation Boundary evaluation under ADR-009.

A three-minute, five-minute, fifteen-minute, other aggregated, tick-only, incomplete, intrabar, or substituted interval cannot authoritatively advance these rules.

Evidence for each such candle SHALL preserve or stably reference the canonical one-minute series identity, interval designation, candle identity, open and close times, completed OHLC, market-data source, finalization or authority status, source provenance, and correction-and-ordering contract version.

## 6. Governing Liquidity Level and stack selection

The governing Liquidity Level is an approved, independently identified, FROZEN, UPPER or LOWER Liquidity Level authorized for the applicable session, symbol, and instrument. ADR-010 does not calculate, select, reconstruct, replace, or reclassify it.

Approved families are non-exhaustive examples only: Yesterday High and Low, Overnight High and Low, London High and Low, and Pre-Market High and Low. A current-session Yesterday High or Low is valid when it is intentionally calculated under its approved contract, has a current-session identity, and is FROZEN. It is not a stale prior-session fallback.

A stack is grouping and selection logic only. It is not a price object, Boundary, owner, Lifecycle, or separate governing reference.

- When no approved stack applies, the selected Liquidity Level is the governing Liquidity Level.
- For an approved upper stack, its highest-priced component Liquidity Level is selected as the governing Liquidity Level. It may be described as the outermost component Liquidity Level.
- For an approved lower stack, its lowest-priced component Liquidity Level is selected as the governing Liquidity Level. It may be described as the outermost component Liquidity Level.

The selected governing `liquidity_level_id` remains immutable through the Rejection Candidate, Rejection Boundary, Rejection Step 2, Rejection Lifecycle and Count 0, Step 4, Eligibility, Creation, Continuation Lifecycle, and Continuation Boundary formation and evaluation. No lineage may switch family, side, same-session level, numerically nearby price, or numerically equal but different identity.

The selection evidence SHALL preserve the selected identity, fixed ordered component identities, fixed component set, and stack-selection rule identity and version. Later stack changes cannot silently replace the selected governing Liquidity Level. A later rotation, reformation, or reselection belongs to a separately authorized new or rotated lineage and does not mutate this lineage.

The Leg 1/Leg 2-based Dynamic Stack Routing formulation is retired and non-governing. ADR-010 does not define a replacement dynamic-routing rule. Any future rule must use no retired Leg terminology, select one actual Liquidity Level, create no fourth price object, preserve one governing identity, and comply with this ADR's one-minute and consumption rules.

If tied outermost components have the same normalized price but different identities, the upstream approved stack-selection contract MUST deterministically select one identity. ADR-010 does not invent a family, alphabetical, creation-time, identifier, or operator tie-break. Without an upstream result, the parent interaction fails closed and no authoritative Rejection lineage, Eligibility, or Creation authority exists. This blocks only that tied-stack interaction, not this ADR.

## 7. Strategy direction and Boundary-side mapping

Continuation direction is immutable and deterministically opposite the completed parent Rejection direction:

| Governing Liquidity Level | Parent Rejection | Continuation | Continuation activity | Initial Continuation Boundary |
| --- | --- | --- | --- | --- |
| UPPER | SHORT | LONG | Below the same governing Liquidity Level | LOWER |
| LOWER | LONG | SHORT | Above the same governing Liquidity Level | UPPER |

“Continuation of the original trend” is explanatory only. This ADR creates no trend object, detector, timeframe, or additional trend predicate.

## 8. Continuation Creation predicate

All Creation comparisons use prices normalized under the authoritative canonical tick-size source, whose identity or version is preserved in Creation evidence. Strict inequality is required; equality is insufficient and sub-tick prices are not authorized.

For parent Rejection SHORT to child Continuation LONG, Creation requires:

`completed one-minute close < governing upper Liquidity Level`

For parent Rejection LONG to child Continuation SHORT, Creation requires:

`completed one-minute close > governing lower Liquidity Level`

When all guards are satisfied, the qualifying authoritative completed one-minute candle SHALL trigger Creation. For LONG, its completed low SHALL form the initial PROVISIONAL lower Continuation Boundary. For SHORT, its completed high SHALL form the initial PROVISIONAL upper Continuation Boundary.

Creation imposes no additional ADR-009 Step 2-style offset beyond the first valid tick-normalized price strictly on the Continuation side of the governing Liquidity Level. The candle open, prior close, color, intrabar route, and whether it crossed either side during its interval are irrelevant. “Closes beyond” means that the completed one-minute close is located beyond the applicable reference; it does not require an opening or earlier close on the opposite side.

Creation does not require a reclaim, return-through path, a new Participation result, another Step 4 result, a multi-candle Creation pattern, an attempt, or a retry.

## 9. Creation versus Continuation Step 2

Creation and Continuation Step 2 have distinct references and results:

| Operation | Price reference | Completed one-minute close rule | Result |
| --- | --- | --- | --- |
| LONG Creation | Governing upper Liquidity Level | Close strictly below it | Create child; form lower Boundary at candle low |
| SHORT Creation | Governing lower Liquidity Level | Close strictly above it | Create child; form upper Boundary at candle high |
| LONG Step 2 | Incoming PROVISIONAL Continuation Boundary, `P_in` | `close <= P_in - one canonical instrument tick` | Confirm; freeze exactly `P_in` |
| SHORT Step 2 | Incoming PROVISIONAL Continuation Boundary, `P_in` | `close >= P_in + one canonical instrument tick` | Confirm; freeze exactly `P_in` |

After a Continuation Boundary exists, do not add a second Liquidity Level close predicate to Step 2. The Liquidity Level remains lineage and authority; ADR-009 alone governs `P_in`, confirmation-first precedence, failed-close-only progression, and freeze-at-`P_in`.

## 10. Same-Step-4-candle Creation

The accepted Rejection Step 4 Confirmation is an authoritative completed one-minute candle. When it satisfies the applicable Creation close predicate, the following ordered facts SHALL occur:

1. Apply all Liquidity Level consumption and parent-validity guards.
2. If the governing Liquidity Level remains active and the parent Step 4 is accepted, ADR-008 creates one AVAILABLE Eligibility.
3. ADR-010 evaluates the same completed one-minute candle.
4. That candle SHALL be the mandatory Creation source.
5. The child-side atomic transition creates the child, consumes Eligibility, forms the initial PROVISIONAL Continuation Boundary at the candle's outward extreme, and records Evaluation Start effective after the candle.

The same candle is expressly authorized to evidence the distinct ordered facts of Step 4 Confirmation, Eligibility creation, Continuation Creation, and Boundary formation. This is not generic multi-owner candle routing. Failure of the ADR-010 child-side transition does not roll back accepted Step 4 or the ADR-008 handoff.

## 11. Later-candle Creation

If the accepted Step 4 candle does not satisfy the Creation close predicate, Eligibility remains AVAILABLE. No child or Continuation Boundary exists; Eligibility is neither consumed nor invalidated merely because that close is nonqualifying; and no attempt or retry object exists.

The first later qualifying authoritative completed one-minute candle in canonical finalized order SHALL trigger Creation only while Eligibility is AVAILABLE, the governing Liquidity Level remains active and unconsumed, and session, symbol, instrument, contract, lineage, ordering, uniqueness, and data-authority guards pass. An earlier qualifying finalized candle cannot be skipped for a later candle.

## 12. First qualifying one-minute candle

The Creation source is the first qualifying authoritative completed one-minute candle in the finalized sequence produced by the canonical market-data correction and ordering contract. It is not the first arrival, processed message, provisional candle version, recovery time, or wall-clock discovery.

If that source exists but the child-side atomic transition fails before commit, Eligibility remains AVAILABLE and recovery SHALL replay Creation from that same source. A later candle cannot replace it; no attempt or retry count is created. If the correction-and-ordering contract later changes authoritative history, that contract governs the corrected source selection. This ADR does not define corrected-candle or out-of-order mechanics.

## 13. Atomic Continuation Creation transition

Once the predicate qualifies, the following are one co-committed child-side transition:

1. Validate AVAILABLE Eligibility, active and unconsumed governing Liquidity Level, parent validity, and all session, symbol, instrument, contract, one-minute data, ordering, uniqueness, lineage, and duplicate guards.
2. Validate the Creation close, derive child direction and Boundary side, and establish deterministic Continuation Lifecycle identity and immutable parent, root, session, Eligibility, and governing-Level lineage.
3. Co-commit `CONTINUATION_CREATED`, AVAILABLE to CONSUMED, and the immutable Eligibility-to-child link.
4. Establish the Lifecycle as Boundary owner, establish the Boundary identity, form the initial PROVISIONAL Boundary at the qualifying candle's outward extreme, and record the distinct Boundary-formation fact.
5. Record Evaluation Start, effective only after the formation candle, and commit the complete result atomically.

No authoritative partial state may contain CONSUMED Eligibility without its child; a child while Eligibility remains AVAILABLE; a child without immutable parent and governing-Level lineage; a Boundary without its Lifecycle owner; a child without its initial PROVISIONAL Boundary; or Evaluation Start without Creation and formation.

This is domain atomicity only. It selects no database, transaction, event-store, API, persistence, key, hash, or serialization technology.

## 14. Initial Continuation Boundary

The initial Continuation Boundary has its own stable identity and belongs exclusively to the Continuation Lifecycle. It begins PROVISIONAL, preserves the governing Liquidity Level identity, formation candle, completed OHLC, and source provenance, and remains independent from the parent Rejection Boundary.

- Continuation LONG: initial lower Boundary equals the formation candle's completed low.
- Continuation SHORT: initial upper Boundary equals the formation candle's completed high.

The parent Rejection Boundary is immutable lineage only. It is never the Creation reference, initial value, copied object, transferred object, inverted value, mirrored value, promoted object, or transformed child Boundary state.

## 15. Continuation Evaluation Start

Creation, Boundary formation, and Evaluation Start are separate ordered facts in the atomic transition. Evaluation Start identifies that later Continuation Boundary evaluation authority begins only after the formation one-minute candle.

Evaluation Start evidence SHALL separately preserve its identity, causal Creation identity, Continuation Boundary identity, effective point after the formation candle, and governing-rule version.

ADR-010 assigns no Continuation Count 0 to Creation, Boundary formation, or Evaluation Start. Whether a later Continuation Step 2 Confirmation becomes Count 0 remains deferred. Parent Rejection Count 0 is immutable lineage and is never reused as a child Count 0.

## 16. Formation-candle exclusion

The formation completed one-minute candle supplies Creation and Boundary-formation evidence and causes Evaluation Start to be recorded. It cannot evaluate, progress, confirm, or freeze its newly formed Continuation Boundary.

The next distinct canonically ordered authorized completed one-minute candle is the first possible Continuation Step 2 evaluation candle.

## 17. Liquidity Level consumption semantics

The Liquidity Level value states remain ABSENT, PROVISIONAL, and FROZEN. Consumption is not a fourth value state and is not a FROZEN-to-CONSUMED price-state transition.

A consumed governing Liquidity Level remains FROZEN and immutable historical market truth. Consumption is a separate authority fact that ends its ability to govern further activity in this lineage. It does not alter frozen price, `liquidity_level_id`, calculation provenance, freeze history, or historical existence.

ADR-010 governs next-Liquidity-Level reach consumption, its authority semantics, its temporal precedence, and its effects on Rejection authority, Eligibility, Creation, and Continuation Boundary evaluation.

## 18. Next-Liquidity-Level consumption rule

For current governing upper Liquidity Level `LL_A`, let `LL_B` be the next distinct approved Liquidity Level above `LL_A` and outside the selected stack, and let `H` be the completed one-minute candle high. `LL_A` is consumed when:

`H >= LL_B`

For current governing lower Liquidity Level `LL_A`, let `LL_B` be the next distinct approved Liquidity Level below `LL_A` and outside the selected stack, and let `Lo` be the completed one-minute candle low. `LL_A` is consumed when:

`Lo <= LL_B`

Touching `LL_B` is sufficient. A component already in the fixed selected stack is not `LL_B`. This ADR does not define level-map ordering that determines `LL_B`.

Consumption evidence SHALL preserve or stably reference the consumed governing identity, next Liquidity Level identity and normalized price, consuming one-minute candle identity and OHLC, canonical order, session and symbol, consumption-rule identity and version, and source provenance.

## 19. Consumption before Rejection Step 2

If the governing Liquidity Level is consumed before accepted Rejection Step 2, the Rejection Candidate loses evaluation authority. A PROVISIONAL Rejection Boundary does not freeze, return to ABSENT, or progress. No Rejection Lifecycle, Rejection Count 0, Step 4 processing, Eligibility, or Continuation Lifecycle is created. Candidate and Boundary history remains inactive historical evidence.

## 20. Consumption after Rejection Step 2 but before Step 4

If consumption occurs after accepted Rejection Step 2 but before accepted Step 4, accepted Step 2, the frozen Rejection Boundary, Rejection Count 0, and the Rejection Lifecycle remain immutable historical truth. Remaining Step 4 evaluation authority ends. Step 4 cannot be accepted, and no Eligibility or Continuation Lifecycle arises from that lineage.

Consumption does not retroactively invalidate, delete, reopen, or rewrite accepted Step 2.

## 21. Same-candle consumption before Step 4 and Creation

When one authoritative completed one-minute candle otherwise appears to satisfy Step 4, closes on the Continuation side of governing Liquidity Level `A`, and reaches next distinct Liquidity Level `B`, process it in this order:

1. Recognize reach of `B`.
2. Consume `A`.
3. End remaining parent evaluation authority.
4. Do not accept Step 4 from `A`.
5. Do not create Eligibility.
6. Do not apply Creation from `A`.

The close cannot reactivate a consumed governing Liquidity Level.

## 22. Consumption after Step 4 but before Creation

ADR-008 already recognizes INVALIDATED as a possible terminal Eligibility status after a separately approved specific invalidation rule. ADR-010 supplies that rule.

If the exact inherited governing Liquidity Level is consumed after accepted Step 4 created AVAILABLE Eligibility but before Creation, accepted Step 2, frozen Rejection Boundary, Step 4, and parent Lifecycle remain immutable historical truth. Eligibility transitions:

`AVAILABLE → INVALIDATED`

No child or Continuation Boundary may be created. Eligibility cannot switch Liquidity Levels or return to AVAILABLE. This is distinct from AVAILABLE to CONSUMED through Creation and AVAILABLE to EXPIRED through session expiration.

## 23. Consumption after Creation but before Continuation Step 2

If consumption occurs after Creation but before Continuation Step 2 Confirmation, parent facts remain immutable and Eligibility remains CONSUMED. No second Eligibility transition occurs. Continuation Boundary evaluation authority ends. An unconfirmed PROVISIONAL Continuation Boundary does not freeze, return to ABSENT, progress, or transfer; its final value and history remain inactive historical evidence under ADR-009.

This ADR does not assign the child’s final named terminal status.

## 24. Consumption precedence before Continuation Step 2

For every post-formation authoritative completed one-minute candle while the Continuation Boundary is PROVISIONAL:

1. Validate that the governing Liquidity Level still has authority.
2. Evaluate next-Liquidity-Level reach.
3. If reached, record consumption first, end Boundary evaluation authority, and do not evaluate ADR-009 Step 2 for that candle. The candle does not confirm, progress, or freeze the Boundary; `P_in` and history remain inactive evidence.
4. Only while the governing Level remains active and unconsumed may ADR-009 evaluate the candle close against `P_in`.
5. When evaluation is authorized, apply ADR-009 confirmation-first precedence.

A candle that consumes the governing Liquidity Level cannot also confirm or progress a Continuation Boundary. This is an evaluation-authority guard, not a change to ADR-009’s price mechanics.

## 25. Consumption after Continuation Step 2

If Continuation Step 2 confirmed on an earlier candle, the Continuation Boundary is FROZEN. Later Liquidity Level consumption cannot alter it, undo Step 2, or return the Boundary to PROVISIONAL or ABSENT.

The later Lifecycle status, Participation, Count Window, Step 4, and terminal consequence remain deferred.

## 26. Session and contract constraints

Creation requires the same governing `liquidity_level_id`, session identity, logical symbol identity, and instrument or contract identity preserved through parent and Eligibility lineage. Cross-session or cross-contract Creation is not authorized.

A mismatched candle cannot trigger Creation, consume Eligibility, form a Continuation Boundary, create Evaluation Start, or produce a Continuation transition. Contract mapping changes cannot silently remap Eligibility or the child. Contract-rollover invalidation and remapping remain deferred.

Creation must be canonically ordered before Eligibility expiration. When ordering is equal, unavailable, ambiguous, or indeterminate, Creation does not occur and expiration governs. No universal terminal clock time is introduced.

## 27. Identity, lineage, and evidence

Creation records SHALL preserve or stably reference the child and Eligibility identities; parent Rejection and root identities; governing `liquidity_level_id`, type, UPPER or LOWER classification, frozen value, calculation-contract identity and version, and source provenance; stack-selection evidence where applicable; parent Step 2, Count 0, and accepted Step 4 identities; parent frozen Rejection Boundary identity as lineage only; child direction and Boundary side; canonical one-minute series and candle evidence; canonical tick-size source identity or version; source and event times; canonical ordering evidence; source provenance; and rule and schema versions.

Boundary-formation evidence SHALL separately preserve Continuation Boundary identity, governing Level identity, side, formation candle and completed OHLC, Creation-close and strict-wick results, initial PROVISIONAL value, and formation-rule version.

All Creation, Boundary, and Evaluation Start identities SHALL be deterministic, stable, unique, idempotent, and replayable. This ADR prescribes no exact encoding or storage format.

## 28. Duplicate, restart, replay, and failure behavior

Duplicate delivery of a qualifying one-minute candle resolves to the existing Eligibility, child, Boundary, and Evaluation Start identities. It cannot consume Eligibility twice or create duplicate facts.

Before any qualifying source exists, restart restores AVAILABLE Eligibility and no child, Boundary, or Evaluation Start. After a qualifying source but before commit, restart restores AVAILABLE Eligibility and replays that same source. After Creation, restart restores the same CONSUMED Eligibility, child, governing-Level lineage, direction, Boundary identity and value, Creation, formation, and Evaluation Start facts.

Replay SHALL reproduce the same result after applying finalized one-minute ordering, consumption precedence, parent validity, Eligibility state, and the Creation predicate. No partial child result is legal. Corrected-candle and out-of-order handling remains governed by the canonical correction-and-ordering contract.

## 29. ADR-006 through ADR-009 relationships

ADR-006 remains the authority for the Rejection Step 4 Count Window. ADR-007 remains the authority for the Participation Rule. ADR-008 remains the authority for accepted Step 4 handoff, Eligibility identity, uniqueness, cardinality, parent lineage, session isolation, handoff atomicity, idempotency, and terminal status model. ADR-009 remains the authority for Boundary value states, ownership, strict-wick formation, `P_in`, confirmation-first precedence, failed-close-only progression, freeze-at-`P_in`, post-freeze immutability, and historical custody.

ADR-010 governs the limited cross-lifecycle rules expressly stated here. It does not supersede those ADRs in full.

## Narrow amendments to ADR-006 through ADR-009

Upon owner approval, ADR-010 is a narrow cross-lifecycle amendment limited to the one-minute candle-source, Liquidity Level consumption-authority, pre-Creation Eligibility invalidation, Continuation Creation, initial Continuation Boundary formation, and Evaluation Start rules expressly identified in this ADR. All unaffected ADR-006 through ADR-009 decisions remain governing and unchanged.

- **ADR-006:** its Count Window candle source is narrowed to the canonical authoritative completed one-minute series for this chain. Count indexing, length, retry, expiration, terminal behavior, and all other ADR-006 decisions are unchanged.
- **ADR-007:** its current and immediately previous Participation candles are narrowed to the same one-minute series. Participation predicates, wick requirements, direction-specific close requirements, and all other ADR-007 decisions are unchanged.
- **ADR-008:** its accepted Step 4 source candle is one-minute for this chain; ADR-010 adds consumption of the inherited governing Liquidity Level before Creation as the specific AVAILABLE-to-INVALIDATED trigger; and same-source Step-4-to-Creation routing is authorized only after ADR-008 creates AVAILABLE Eligibility. Handoff, identity, uniqueness, cardinality, lineage, session isolation, atomicity, idempotency, CONSUMED, and EXPIRED semantics are unchanged.
- **ADR-009:** its completed-candle source is narrowed to the same one-minute series for this chain; governing-Level consumption is an evaluation-authority guard before `P_in` evaluation; and ADR-010 supplies Creation, initial Boundary formation, and Evaluation Start. ADR-009’s value states, strict-wick formation, `P_in`, confirmation-first precedence, failed-close-only progression, freeze-at-`P_in`, ownership, post-freeze immutability, and historical custody are unchanged.

## 30. Parent validity and percentage-rule boundary

ADR-010 requires an active unconsumed governing Liquidity Level, valid parent Rejection, accepted Step 4, and AVAILABLE ADR-008 Eligibility. Parent Rejection architecture remains responsible for independently governed parent-validity rules, including its 50% rules, 75% rules, Participation, Count Window, and Step 4 acceptance.

ADR-010 does not calculate or reconstruct a parent percentage threshold. A parent percentage invalidation and next-Liquidity-Level consumption are separate guards unless another approved rule expressly equates them. ADR-010 consumes the final parent-validity outcome while applying its own consumption-authority rule.

## 31. Explicitly rejected alternatives

Rejected alternatives include: a fourth liquidity or boundary price object; retired boundary terminology as authority; Leg 1 or Leg 2 governance; stack-owned or synthetic prices; multiple governing Levels for one lineage; level switching; discretionary tied-stack selection; Creation from consumed authority; touch or equality Creation; non-one-minute or intrabar advancement; optional skipping or source replacement after failed commit; formation-candle Step 2 evaluation; consumption-candle Step 2 confirmation or progression; copied or transformed Rejection Boundaries; Count 0 assigned by Creation, formation, or Evaluation Start; attempts or retry aggregates; cross-session or cross-contract Creation; partial child state; and implementation authority.

## 32. Deferred decisions

Outside ADR-010 are exact Liquidity Level calculations and family registry; level-map ordering and tied-stack tie-break; replacement dynamic stack routing; corrected-candle and out-of-order mechanics; contract rollover; final child terminal-status name after post-Creation consumption; whether later Step 2 becomes Count 0; Continuation Participation, Count Window, Step 4, entries, execution, risk, position management, exact session deadline, identity encoding, and generic candle routing beyond the expressly authorized Step-4-to-Creation reuse.

These deferred decisions do not reopen this ADR.

## 33. Consequences

Benefits: one canonical candle series; one governing Liquidity Level; exactly three liquidity and boundary price objects; deterministic same-source and later-source Creation; close-only predicates; deterministic consumption precedence; no retroactive mutation of accepted parent facts; no child from consumed authority; stable stack selection; clear Creation-versus-Step-2 separation; and replayable source selection.

Costs and dependencies: canonical documents require one-minute terminology alignment; tied-stack selection remains upstream; corrected-candle and ordering contracts remain required; final post-Creation child status remains deferred; legacy terminology requires non-governing cleanup; and implementation remains unauthorized.

## 34. Non-goals

This ADR does not define implementation, code, tests, persistence technology, schemas, APIs, migrations, deployment, Liquidity Level calculations, parent percentage thresholds, Continuation Count 0, Participation, Count Window, Step 4, entries, execution, risk, position management, or later Continuation lifecycle behavior.

## 35. Worked examples

1. **Single UPPER level.** An accepted SHORT Step 4 one-minute candle closes at 99.90 below an upper governing Level at 100.00, with a low of 99.80. It SHALL create LONG Continuation and a lower PROVISIONAL Boundary of 99.80.
2. **Single LOWER level.** An accepted LONG Step 4 one-minute candle closes at 100.10 above a lower governing Level at 100.00, with a high of 100.20. It SHALL create SHORT Continuation and an upper PROVISIONAL Boundary of 100.20.
3. **Same-side open.** A LONG Creation candle opens below an upper governing Level, stays below it, and closes below it. It qualifies: only its close location controls Creation.
4. **Later Step 2.** A LONG formation low is 99.80. The next distinct authorized one-minute candle closes 99.79 with a 0.01 tick. ADR-009 confirms and freezes 99.80.
5. **Stack selection.** An upper stack components price at 100.00 and 100.25. The 100.25 component Level is selected. No stack Boundary is created.
6. **Tied stack.** Two upper outermost components both price at 100.25 but have different identities. Without the upstream deterministic tie-break, the interaction fails closed before parent lineage.
7. **Internal stack component.** Reaching a component already inside the fixed selected stack does not consume the governing Level; it is not the next outside Level.
8. **Before Rejection Step 2.** A Candidate with a PROVISIONAL Boundary reaches next outside Level. Candidate authority ends and the PROVISIONAL Boundary remains inactive history.
9. **After Rejection Step 2.** Next outside Level is reached before Step 4. Accepted Step 2 and its frozen Boundary remain immutable; Step 4 authority ends.
10. **Same Step 4 candle reach.** A candle appears to meet Step 4 and Creation close but reaches next outside Level. Consumption occurs first; no Step 4, Eligibility, or child arises from the prior Level.
11. **After AVAILABLE Eligibility.** Later next-Level reach moves AVAILABLE Eligibility to INVALIDATED; accepted parent facts remain unchanged.
12. **After Creation.** Next-Level reach ends unconfirmed Continuation Boundary evaluation; Eligibility remains CONSUMED and the Boundary history is retained.
13. **Apparent Step 2 plus consumption.** A LONG candle closes one tick below `P_in` but its high reaches next outside upper Level. Consumption wins; it neither confirms nor progresses the Boundary.
14. **After Step 2.** A later consumption event cannot change a Boundary already FROZEN on an earlier Step 2 candle.
15. **Non-one-minute input.** A five-minute bar cannot authoritatively form, confirm, or advance this lifecycle.
16. **Duplicate and failed commit.** Duplicate source delivery resolves to existing facts. A pre-commit failure recovers from the same earliest finalized source, not a later candle.

## 36. Approval checklist

- [ ] Three liquidity and boundary price objects only
- [ ] Retired boundary synonyms remain non-governing
- [ ] Retired Leg terminology remains non-governing
- [ ] One governing Liquidity Level per lineage
- [ ] Stack selects an existing outermost component
- [ ] Governing `liquidity_level_id` is immutable
- [ ] Tied stack fails closed upstream
- [ ] Canonical authoritative completed one-minute series
- [ ] Opposite parent-to-child direction
- [ ] Tick-normalized strict Creation close
- [ ] Creation and Step 2 reference separation
- [ ] Mandatory same-Step-4-candle Creation
- [ ] Mandatory first later qualifying candle
- [ ] Atomic Creation, Eligibility consumption, Boundary formation, and Evaluation Start
- [ ] Formation-candle exclusion
- [ ] No Count 0 assignment by ADR-010
- [ ] Consumption is authority fact, not Liquidity Level value state
- [ ] Upper and lower next-Level consumption rules
- [ ] Temporal consumption consequences
- [ ] AVAILABLE to INVALIDATED trigger
- [ ] Consumption precedence before Continuation Step 2
- [ ] Parent 50% and 75% rules remain upstream
- [ ] Same-session and same-contract limits
- [ ] Duplicate and replay guarantees
- [ ] Narrow one-minute amendments to ADR-006 through ADR-009
- [ ] Narrow consumption-authority amendments
- [ ] Scope-limited three-price-object vocabulary
- [ ] ADR-010 ownership of next-Liquidity-Level consumption
- [ ] Complete canonical alignment map required
- [ ] No implementation authority
