# 2026-07-20 Complete TradingView v14 Canonical Sender — Architecture Impact Assessment

Document type: Narrow Architecture Impact Assessment

Status: APPROVED FOR REPOSITORY IMPLEMENTATION; TradingView compilation, publication, alert changes, deployment, and trading authorization excluded

Classification: Clarification and completion of existing canonical behavior

Canonical symbols: NQ and YM

## 1. Baseline and observed gap

Commit `cf98972743cf665dbc718e83585605f269d6241e` governs the accepted replacement tail `REPLACE_ENTRY_AGENT_WEBHOOK_OVERLAPPING_FINALIZED_TABLE_STATE.pine` at SHA-256 `7A677CB6B40AFF4A180A121890C64F50D036E21F96E227ED3A3DBB1ABB2E911F`. That tail correctly serializes `session_lock_price` from `sessionLockPrice_eff`.

The only complete local Level Map Helper containing the current full-span construction is `TradingView/indicators/Randle_AI_Level_Map_Helper.pine`, originally untracked at SHA-256 `AFE727A361404F6FF863EE4E63A7DD485A7EB3E0A24ABBD89EB9B97F068092CF`. Its prefix contains the Pine declaration, inputs, level calculations, full-span stack construction, freeze state, ladder, table, and plotting logic. Its final 57 lines contain an older v13 webhook serializer. The accepted 325-line replacement tail is not incorporated byte-for-byte; only the accepted frozen-reference field is common.

The tracked `liquidity_helper_production.pine` and local `taylor_helper_production.pine` are complete older v13 variants, but neither contains the current full-span construction, source timestamp, session date, or accepted v14 serializer. Historical exact-source and replacement-only Pine files are evidence or migration artifacts, not complete current publication authority. They remain unchanged and are excluded from this correction except for the accepted replacement tail, whose committed bytes and hash remain unchanged.

The complete source also omits sender `timestamp` and `session_date`. Its pre-lock `sessionLockPrice_eff` resolves to current `close`, so publication must be gated by frozen-lock identity rather than numeric presence alone.

In the completed artifact, the canonical webhook section starts at line 1541. A line-sequence comparison preserves 316 of the accepted tail's 325 lines exactly; the deliberate differences remove replacement-only instructions, escape JSON strings safely, add complete nested level rows, add source/session fields and gates, and advance the payload identity. The accepted `session_lock_price` serialization line itself remains byte-for-byte identical, and the accepted tail file remains byte-for-byte unchanged.

## 2. Existing authority paths

Entry Agent currently recognizes two source profiles on the same endpoint:

1. `randle_taylor_map`, the combined strict profile whose receiver requires Taylor context and the complete canonical field set; and
2. `tradingview_level_helper`, the liquidity-only Level Map profile whose current receiver retains legacy compatibility and merges independently with Taylor context.

This correction does not let the Level Map sender invent or own Taylor context. It completes the source-controlled liquidity profile and documents the already-implemented profile distinction. No receiver normalization, fallback, validation, lock, merge, or lifecycle behavior changes.

The strict combined profile rejects absent `timestamp` and `session_date`. The existing liquidity-only receiver profile still has a legacy receipt-time/session-date fallback. This task does not expand into production Python. The v14 source independently fails closed before publication when either identity is unavailable, so no conforming v14 source payload depends on that fallback. Receiver compatibility retirement remains outside this source-only correction and does not authorize receipt time as source authority.

## 3. Canonical source timestamp

The source event is the confirmed one-minute bar-close execution that calls `alert(..., alert.freq_once_per_bar_close)`. The canonical field is therefore derived from Pine `time_close`, not `time` (bar open) and not `timenow` (script execution wall clock).

Serialization is UTC RFC 3339 at whole-second precision:

```text
yyyy-MM-dd'T'HH:mm:ss'Z'
```

Pine expression:

```pine
str.format_time(time_close, "yyyy-MM-dd'T'HH:mm:ss'Z'", "UTC")
```

## 4. Canonical session date

The session identity is derived from Pine `time_tradingday`, which is the trading-day date assigned by the symbol's exchange session and is specifically stable across overnight futures bars. It is formatted in UTC because `time_tradingday` represents 00:00 UTC of that trading day:

```pine
str.format_time(time_tradingday, "yyyy-MM-dd", "UTC")
```

Consequences:

- a pre-midnight futures bar and a post-midnight bar in the same exchange session carry the same `session_date`;
- the 06:15–07:30 America/Los_Angeles operating window carries that morning's trading date; and
- the date is not inferred from receiver receipt time or the bar's local calendar opening date.

The script captures `time_tradingday` with the 06:15 frozen lock. Recurring publication is prohibited when the current bar's trading-day identity differs from the frozen lock identity.

## 5. Canonical delta

1. Add the complete Pine source at the established canonical path.
2. Replace its older v13 webhook tail with the accepted finalized-table v14 tail.
3. Add deterministic `timestamp` and `session_date` fields.
4. Add the canonical `locked` alias, one-minute ATR telemetry, and complete `liquidity_map.levels` plus finalized stacks for the liquidity sender profile.
5. Require one-minute confirmed-bar execution, canonical timezone configuration, current frozen-session identity, numeric frozen reference, numeric threshold, and required ATR values before calling `alert()`.
6. Keep `session_lock_price` sourced only from `sessionLockPrice_eff` after the frozen lock is proven current.

### Existing canonical behavior

- one frozen 06:15 Level Map authority supplies all finalized liquidity rows, stacks, frozen threshold, and frozen market reference;
- source event time and exchange trading-session identity belong to the source payload; and
- incomplete, stale, contradictory, or missing frozen authority fails closed.

### New canonical representation

- one complete source-controlled v14 Pine artifact implements the already-required source timestamp, trading-session date, and frozen-reference fields;
- `time_close` and `time_tradingday` are named as their deterministic Pine authorities; and
- the source binds recurring publication to the trading-day identity captured with the frozen lock.

### Explicitly unchanged behavior

Strategy, ladder eligibility, YH/YL treatment, threshold, level prices, freeze timing, receiver validation, lifecycle, risk, execution, and trading authorization remain unchanged.

### Migration and compatibility

The committed replacement tail remains immutable historical migration evidence. `v14_canonical_liquidity_sender` supersedes v13 and replacement-tail-only publication candidates for future compilation; it does not alter already archived payloads or active TradingView alerts.

### Verification obligation

Repository checks must bind the complete source hash, structure, one serializer, deterministic valid JSON, field types/order, NQ/YM parity, strict receiver rejection cases, stale-session rejection, and unchanged frozen-stack validation. TradingView compilation and publication require separate manual evidence and authorization.

## 6. No semantic strategy delta

Unchanged:

- YH/YL eligibility and market-side treatment;
- full-span stack construction and threshold percentage;
- level source prices and active/inactive status;
- 06:15 freeze timing;
- ladder ordering, midpoint, exhaustion, rejection, continuation, Entry Agent, Trade Manager, Executor, risk, and trading authorization behavior.

No ADR is required. The webhook contract, Liquidity Ladder Calculation Contract, and TradingView Liquidity Ladder Verification Specification require narrow versioned clarifications for the already-implemented source profiles, complete-source authority, and exact source-time/session-date serialization.

## 7. Verification and authorization boundary

The completed repository artifact is `TradingView/indicators/Randle_AI_Level_Map_Helper.pine` at SHA-256 `1C795076B9463B3F567366851EDA4914D2248F1B4B5A7B1155C8E26CEF961D70`. Deterministic synthetic outputs are preserved for stacked-YH YM and unstacked-YH NQ under `tests/fixtures/tradingview/`.

Repository verification may establish `PINE_SOURCE_READY_FOR_MANUAL_TRADINGVIEW_COMPILATION`. Only TradingView can establish `PINE_COMPILED`.

This work does not authorize TradingView access, alert changes, service operation, deployment, automated paper entry, or live-money trading.
