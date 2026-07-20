# TradingView Liquidity Ladder Calculation Contract

Version: 1.2

Status: Canonical Liquidity Level Calculation Contract

Authority: Randle AI Constitution §17; Lifecycle Vocabulary §2.5; 06:15 Session Liquidity Lock Contract

Canonical symbol applicability: NQ and YM

Supersession: Version 1.1 withdrew version 1.0's categorical YH/YL exclusion and pairwise-transitivity rule. Version 1.2 completes the governed v14 sender representation without changing those ladder rules. Historical versions remain recoverable from repository history and the superseded impact/evidence records.

## 1. Purpose and scope

This contract governs Liquidity Level stack eligibility, full-span construction, ladder projection, freeze behavior, and webhook representation of the TradingView Level Map Helper.

It does not change the configured stack threshold percentage, session windows, source prices, midpoint or exhaustion formulas, Entry Agent lifecycle rules, Step 2, Step 4, ATR, listener authority, Trade Manager, or execution.

## 2. Liquidity Level identities

The recognized Liquidity Levels are:

- prior-RTH: `YH`, `YL`;
- overnight: `ONH`, `ONL`;
- London: `LH`, `LL`; and
- premarket: `PMH`, `PML`.

Source identity remains immutable. It does not create a categorical stack-eligibility difference. Every recognized active Liquidity Level may be a stack candidate when it is on the applicable market side at the frozen state.

YH and YL may roam above or below current price. Their market side for stack construction is determined by their frozen price relative to the frozen session reference, not by the letters in their names.

## 3. Stack eligibility invariant

A proposed stack is valid only when all of the following are true:

1. it contains at least two recognized active Liquidity Levels;
2. every member is on the same market side at the frozen state;
3. the complete proposed span satisfies:

```text
highest-priced Liquidity Level - lowest-priced Liquidity Level <= stack threshold
```

4. each Liquidity Level belongs to at most one stack;
5. no stack definition overlaps or contradicts another; and
6. every projected row label agrees with the finalized explicit membership.

The comparison is inclusive. The existing 10% Daily ATR configuration and tick normalization are unchanged.

No Liquidity Level type, including YH or YL, is categorically excluded.

## 4. Deterministic full-span construction

Pairwise transitive connectivity is prohibited. The following is invalid when the final complete span exceeds the threshold:

```text
A to B <= threshold
B to C <= threshold
A to C > threshold
```

For each market side independently:

1. collect all recognized active Liquidity Levels on that side;
2. sort from innermost to outermost, using stable canonical row order to break equal-price ties;
3. begin a candidate with the first Liquidity Level;
4. for each next Liquidity Level, calculate the proposed candidate's complete highest-to-lowest span;
5. append the next Liquidity Level only when the proposed complete span is within the threshold;
6. otherwise finalize the current candidate and begin a new candidate with the next Liquidity Level; and
7. assign a stack label only to finalized candidates containing at least two members.

For a high-side stack, the lowest-priced member is the innermost Liquidity Level and the highest-priced member is the outermost Liquidity Level.

For a low-side stack, the highest-priced member is the innermost Liquidity Level and the lowest-priced member is the outermost Liquidity Level.

Equal-price Liquidity Levels remain distinct identities and may qualify together. Equality contributes zero to the complete span.

## 5. Group assignment and numbering

Independent high-side stacks are numbered deterministically from the nearest qualifying high-side stack to current price outward: `HIGH 1`, `HIGH 2`, and so on.

Independent low-side stacks are numbered from the nearest qualifying low-side stack to current price outward: `LOW 1`, `LOW 2`, and so on.

Every member of one finalized stack receives the same label. A singleton receives `NONE`. Numbering occurs only after the valid groups are finalized.

## 6. Stack Liquidity Levels

For a high-side stack:

- innermost Liquidity Level = lowest-priced member; and
- outermost Liquidity Level = highest-priced member.

For a low-side stack:

- innermost Liquidity Level = highest-priced member; and
- outermost Liquidity Level = lowest-priced member.

Only finalized members participate in those selections. These Liquidity Levels remain the inputs to unchanged downstream ladder, lifecycle, midpoint, and exhaustion behavior.

## 7. Ladder and target inputs

A stacked YH or YL contributes through the same governed deduplicated stack anchor as every other stack member. An unstacked YH or YL remains an independent ladder reference.

The table order remains price-derived:

- high side is displayed outward-to-price; and
- low side is displayed price-to-outward.

Each stack contributes its governed deduplicated anchor. Each independent active Liquidity Level remains an eligible independent ladder reference. Target construction consumes ordered deduplicated numeric anchors so exact duplicate prices do not create a zero-length ladder interval. Midpoint and exhaustion formulas are unchanged.

## 8. Freeze, reload, and late start

At the 06:15 session lock, finalized membership, labels, innermost and outermost Liquidity Levels, ordered ladder anchors, frozen threshold, and target inputs freeze under the Session Liquidity Lock Contract.

YH/YL freeze with a valid stack label when the complete-span rule passes. They freeze with `NONE` when they are not members of a qualifying group.

Reload, restoration, rehydration, repair, force, manual-lock, legacy, and late-start paths SHALL apply or validate this contract before table, frozen ladder, webhook, or LIVE projection. If the frozen threshold, frozen market-side reference, row membership, or other required authority is unavailable, the path must report unavailable/rehydrating and fail closed; it must not guess a group.

## 9. Projection and webhook contract

The chart table and webhook are projections of the same finalized assignment and SHALL agree for every row.

TradingView SHALL serialize YH/YL with a valid `stack_group` when they are finalized members and with `NONE` otherwise. The Level Map payload SHALL also serialize the frozen `stack_threshold` and `session_lock_price` used for structural validation. `session_lock_price` remains separate from row membership, extrema, threshold, display offsets, and current market price.

The complete governed sender is `TradingView/indicators/Randle_AI_Level_Map_Helper.pine`, with payload identity `v14_canonical_liquidity_sender`. It SHALL serialize source `timestamp` from the confirmed bar's `time_close` in UTC RFC 3339 whole-second form and `session_date` from `time_tradingday` as `YYYY-MM-DD`. Publication SHALL fail closed when the current exchange trading-day identity does not match the identity captured with the frozen 06:15 lock.

Entry Agent SHALL validate all transmitted or derived groups structurally. It must accept valid YH/YL membership. It must reject and archive span-invalid, mixed-side, undersized, overlapping, contradictory, unknown-member, duplicate-member, nondeterministically numbered, or row/explicit-mismatched proposals. It must not silently normalize invalid membership.

## 10. Canonical examples

YM 2026-07-16:

```text
YH   53088   NONE
ONH  53057   HIGH 1
LH   53057   HIGH 1
PMH  53002   HIGH 1
PML  52880   LOW 1
LL   52835   LOW 1
ONL  52832   LOW 1
YL   52680   NONE
```

The high group is valid because the `PMH`-to-`ONH/LH` complete span is within the threshold. Adding `YH` would make the complete `PMH`-to-`YH` span exceed the threshold, so YH is `NONE` on this map.

If the same-side values change so that the complete `PMH`-to-`YH` span is within the threshold, YH joins that high-side stack. The symmetric rule applies to YL on the low side and to NQ.

## 11. Failure conditions

Conformance fails if:

- pairwise adjacency creates a final stack whose complete span exceeds the threshold;
- YH or YL is excluded solely because of source identity;
- a valid YH/YL member is forced to `NONE` or rejected by the receiver;
- any final stack has fewer than two members;
- members occupy different frozen market sides;
- one Liquidity Level belongs to multiple stacks;
- row labels and explicit membership disagree;
- definitions overlap, contradict one another, or are numbered nondeterministically;
- table and webhook assignments differ;
- reload, restoration, or late start exposes an invalid frozen group; or
- the correction changes threshold percentage, tick normalization, ladder ordering, midpoint/exhaustion formulas, or downstream lifecycle rules.

## 12. Expected implementation and verification

### Expected implementation areas

- governed complete TradingView Level Map Helper Pine source under `TradingView/indicators/`;
- shared Entry Agent stack structural validator;
- `EntryAgent/tv_context_server.py` inbound validation, archival, and derived-stack projection;
- `EntryAgent/entry_agent.py` session-lock and restoration defense-in-depth validation; and
- chart table and webhook serialization units in the governed Pine source.

### Expected verification areas

- `test_tradingview_liquidity_ladder.py` deterministic identical-algorithm model and receiver/lock cases;
- source-linked TradingView compilation from the exact governed hash or the explicitly governed manual limitation;
- YM 2026-07-16 exact values and NQ equivalents;
- high/low YH/YL join and split, equal price, full-span bridge prevention, numbering, freeze, reload, late-start, table/webhook parity, ingress, restoration, and target-anchor cases;
- static alternate-route/writer audit; and
- coordinated sender/receiver compatibility verification before publication or deployment.

### Traceability record

Implementation, authority, verification, evidence, and debt are mapped in `Architecture/Traceability/2026-07-16_TradingView_Liquidity_Ladder_Architecture_Traceability_Matrix.md`.
