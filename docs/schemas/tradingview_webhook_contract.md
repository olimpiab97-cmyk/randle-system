# TradingView Webhook Contract

Version: 1.5

Status: Canonical Runtime Contract

Authority: ADR-012 and the Randle AI Runtime Authority Specification

Scope:
- TradingView liquidity context webhook consumed by Entry Agent
- `randle_taylor_map` combined Taylor/session-context sender profile
- `tradingview_level_helper` liquidity-only sender profile
- `06:15 PT` session liquidity lock
- `06:15-06:29 PT` pre-open observation behavior
- `06:30+ PT` first Step 2 eligibility
- accepted-payload archival and replay evidence

Out of scope:
- HTF table contract
- Trade Manager
- Dynamic Risk Reset

## 1. Endpoint

- `POST /webhook/tv-context`

The payload is the authoritative TradingView session context feed for Entry Agent.

## 2. Supported Symbols

Only these roots are supported:

- `NQ`
- `YM`

Any alternate symbol form must normalize to one of those roots before Entry Agent consumes the payload.

## 3. Required Payload Shape

Canonical combined Taylor payload:

```json
{
  "source": "randle_taylor_map",
  "symbol": "NQ",
  "timestamp": "2026-06-22T06:15:00-07:00",
  "session_date": "2026-06-22",
  "time_zone": "America/Los_Angeles",
  "locked": true,
  "session_lock_price": 22143.25,
  "stack_threshold": 31.25,
  "atr_1m_14": 34.5,
  "daily_atr14": 312.75,
  "liquidity_map": {
    "levels": [
      {
        "name": "PMH",
        "price": 22131.50,
        "status": "ACTIVE",
        "stack_group": "HIGH 1"
      },
      {
        "name": "ONH",
        "price": 22129.75,
        "status": "ACTIVE",
        "stack_group": "HIGH 1"
      },
      {
        "name": "YH",
        "price": 22188.00,
        "status": "INACTIVE",
        "stack_group": "NONE"
      }
    ]
  },
  "taylor_context": {
    "day_type": "NORMAL",
    "bias": "NEUTRAL"
  }
}
```

### 3.1 Canonical Level Map liquidity-only profile

`tradingview_level_helper` is the existing independently merged liquidity-only source profile. It owns the complete finalized Liquidity Level table, stacks, frozen reference, frozen threshold, Level Map telemetry, source event time, and trading-session identity. It does not own and must not invent `taylor_context`; the separately governed `randle_taylor_map` profile owns Taylor context.

The canonical complete Pine source is `TradingView/indicators/Randle_AI_Level_Map_Helper.pine`. Its payload identity is `v14_canonical_liquidity_sender`.

The liquidity-only profile must include:

- `source = tradingview_level_helper`;
- `version = v14_canonical_liquidity_sender`;
- `symbol`, using the chart symbol consumed by canonical root normalization;
- source `timestamp`;
- canonical `session_date`;
- `time_zone = America/Los_Angeles`;
- `timeframe = 1`;
- `locked = true` and `session_locked = true`;
- numeric frozen `session_lock_price`;
- numeric frozen `stack_threshold` and configured `stack_threshold_pct`;
- `atr_1m_14` and `daily_atr14` telemetry;
- all eight named level rows in the top-level `levels` compatibility projection;
- all eight named level rows in `liquidity_map.levels`;
- complete finalized stacks in both the top-level `stacks` compatibility projection and `liquidity_map.stacks`;
- `midpoints` and `exhaustion_boundaries`; and
- the existing status, recurring-update, true-price, display-offset, premarket-range, and daily-range fields.

The sender must not call `alert()` unless every required source/session/frozen/numeric authority above is available and the current bar's trading-day identity equals the trading-day identity captured with the frozen lock.

## 4. Required Fields

Top-level fields required for every source profile:

- `source`
- `symbol`
- `timestamp`
- `session_date`
- `time_zone`
- `liquidity_map`

Required profile identity:

- `source`
- `version` for `tradingview_level_helper`

Required for Entry Agent session locking:

- `locked`
- `session_lock_price`

Required whenever any row has a non-`NONE` stack group:

- `stack_threshold`, or a canonical `daily_atr14` value from which the unchanged 10% threshold can be deterministically recovered for legacy compatibility

Required ATR fields for Entry Agent:

- `atr_1m_14`
- `daily_atr14`

Required Taylor context container:

- `taylor_context`

`taylor_context` is required only for the `randle_taylor_map` combined profile. It is prohibited for the Level Map sender to synthesize Taylor context merely to satisfy a shared transport shape.

## 5. Timestamp Rules

- The payload timestamp governs session-lock timing and observation-window classification.
- The receiver must interpret timestamps in `America/Los_Angeles`.
- Receipt time is not the source of truth when payload time is present.
- For `tradingview_level_helper`, the source event is the confirmed one-minute bar-close execution that invokes `alert(..., alert.freq_once_per_bar_close)`.
- That profile must derive `timestamp` from Pine `time_close`, not bar-open `time` and not execution-wall-clock `timenow`.
- It must serialize the value in UTC RFC 3339 at whole-second precision as `yyyy-MM-dd'T'HH:mm:ssZ`, with literal suffix `Z`.
- For `tradingview_level_helper`, `session_date` must derive from Pine `time_tradingday` and serialize as `YYYY-MM-DD` using UTC calendar extraction. `time_tradingday` supplies the exchange trading-day identity for overnight futures sessions; it must not be replaced by the local calendar date of the bar open.
- Pre-midnight and post-midnight futures bars in one exchange session therefore share one `session_date`. The 06:15–07:30 America/Los_Angeles operating window maps to the trading date containing that morning's window.
- The Level Map sender must capture the trading-day identity with the 06:15 frozen lock and suppress publication after the exchange trading day changes until a new valid lock exists.

## 6. Liquidity Map Rules

Each liquidity row must support:

- `name`
- `price`
- `status`
- `stack_group`

Supported level names:

- `PMH`
- `PML`
- `ONH`
- `ONL`
- `YH`
- `YL`
- `LH`
- `LL`

Supported statuses:

- `ACTIVE`
- `INACTIVE`

Supported stack behavior:

- rows sharing the same `stack_group` belong to the same locked stack
- stack membership freezes at `06:15 PT`
- later payloads cannot rewrite the locked stack membership for the active session
- every recognized Liquidity Level, including YH and YL, may be a member
- every final stack must contain at least two members on the same frozen market side
- the complete highest-to-lowest Liquidity Level span must be less than or equal to the frozen `stack_threshold`
- pairwise adjacency cannot authorize a final stack whose complete span exceeds that threshold
- YH/YL transmit a valid stack label when they qualify and `NONE` otherwise

Receiver validation:

- Entry Agent must accept valid YH/YL membership
- Entry Agent must reject or disable unknown-member, mixed-side, undersized, span-invalid, duplicate, overlapping, contradictory, row/explicit-mismatched, or nondeterministically numbered definitions
- the received invalid payload must remain archived with its rejection result
- the receiver must not silently rewrite invalid membership or group labels

Ownership constraint:

- `INACTIVE` levels from the locked table cannot become owners later in the session

## 7. 06:15 PT Lock Contract

At `06:15 PT`, the first valid session payload must lock:

- the liquidity table
- each row's `ACTIVE` / `INACTIVE` state
- stack membership
- the corresponding Taylor context snapshot

Once locked:

- later webhook updates cannot mutate the locked session table
- later webhook updates cannot promote an `INACTIVE` locked level into ownership eligibility
- reload, late-start reconstruction, or derived-stack projection must preserve valid YH/YL membership and must reject structurally invalid frozen membership

## 8. 06:15-06:29 PT Observation Contract

This window is observation only.

Allowed:

- lock session liquidity at `06:15 PT`
- observe market structure
- track pre-open highs, lows, and wicks as context
- update the current pre-open observed extreme

Not allowed:

- Step 2 activation
- Step 2 owner lock
- rejection owner creation
- continuation owner creation
- Step 2.5+
- Step 3+
- Step 4 / Step 5 / Step 6

Observation rule:

- if price trades, wicks, or closes beyond locked liquidity before `06:30 PT`, that move becomes pre-open context only
- it must not activate Step 2 during the observation window

Monotonic observed-wick rule:

- the authoritative input is completed-candle OHLC against the frozen session map; the candle close may establish interaction eligibility but cannot substitute for the wick extreme
- for an upper observation, only a strictly higher high may replace the stored high
- for a lower observation, only a strictly lower low may replace the stored low
- equal or inward extremes preserve the stored observation, including when a later candle begins or closes differently
- a candidate with a different side or frozen liquidity identity cannot silently replace the stored observation; a separately governed explicit lifecycle transition is required
- projection refresh, reconnect, or receipt of telemetry cannot clear or retract the stored observation

## 9. 06:30 PT And Later

At `06:30 PT`, Step 2 becomes eligible for the first time.

Step 2 must evaluate against:

- the locked `06:15 PT` liquidity table
- the locked active/inactive statuses
- the latest valid pre-open observed extreme if pre-open price extended beyond the locked liquidity boundary

Close-beyond rule:

- if pre-open price already established a farther wick or boundary beyond the locked liquidity, then post-open Step 2 confirmation must close beyond that pre-open observed extreme under the normal Step 2 directional rules

Step 2 to Step 4 reservation rule:

- once Step 2 confirms and seeds rejection Candle A, the next future candle is reserved as Step 4 Candle B
- while that Candle B reservation is active, opposite-side release cannot clear the active rejection owner before Candle B is evaluated
- while that Candle B reservation is active, a fresh Step 2 owner cannot be created on that same candle
- while that Candle B reservation is active, Step 2.5 continuation logic cannot preempt the Candle B evaluation on that same candle
- same-candle Step 4 completion and Step 2.5 continuation activation are not allowed
- after Step 4 completes, any continuation activation must come from a later future close beyond the continuation boundary

## 10. Canonical Example

Locked session liquidity:

- `PMH/ONH` high stack

Pre-open behavior:

- at `06:25 PT`, price closes above `PMH/ONH`
- at `06:25 PT`, price also creates a higher wick above the stack
- the `06:25 PT` candle does not activate Step 2
- that wick high becomes the current pre-open observed extreme

Open behavior:

- at `06:30 PT` and later, SHORT rejection becomes eligible for the first time
- Step 2 must still use the locked `06:15 PT` liquidity table
- Step 2 must also require the normal close-beyond test relative to the pre-open wick extreme

## 11. Accepted Payload Archival

Every accepted `POST /webhook/tv-context` request must append one versioned receipt event before the request is considered auditable.

The event must preserve:

- schema version
- complete parsed request payload without selecting or flattening away fields
- complete nested `liquidity_map`
- every transmitted level row, status, and `stack_group`
- every transmitted explicit stack or ladder row
- source timestamp and receipt timestamp
- raw symbol and normalized root symbol
- session date and time zone
- acceptance and normalization result
- exact immutable locked context projected from the request

Normalized and flattened fields may be stored in addition to the complete payload. They are not substitutes for it.

When the sender supplies level rows with frozen `stack_group` membership but omits an explicit `stacks` array, Entry Agent may derive the stack projection deterministically. The receipt must retain the original rows, and the derived stack must remain distinguishable from sender-supplied payload data.

Receipt archival does not prove TradingView sent a field that was absent. Historical events created before this contract that retained only flattened fields must be reported as incomplete evidence and must not be described as exact original webhook bodies.

## 12. Expected Implementation and Verification

### Expected Implementation Areas

- the shared Entry Agent Liquidity Level stack validator for complete-span, market-side, membership, numbering, and overlap invariants; and
- `EntryAgent/tv_context_server.py` `POST /webhook/tv-context` acceptance, complete receipt archival, structural validation, locked-context projection, and deterministic derived-stack labeling; and
- `EntryAgent/entry_agent.py` completed-candle observation selection, monotonic observed-wick merge, persistence, and `06:30 PT` projection into the matching frozen group; and
- `EntryAgent/entry_agent.py` session-lock, reload, rehydration, repair, force, manual, and legacy defense-in-depth validation; and
- archive readers and replay tools that distinguish sender-supplied fields from deterministic derivation.

### Verification Areas

- `test_nq_20260716_regressions.py` accepted nested-payload archival and derived-stack cases;
- `test_nq_20260716_regressions.py` 06:15-06:30 NQ observed-wick running-extreme and smaller-wick preservation replay;
- schema-version, source/receipt identity, and immutable locked-context assertions; and
- replay provenance checks that label incomplete historical receipts without overstating evidence.
- TradingView Liquidity Ladder Verification Specification cases for YH/YL valid membership, full-span split, webhook/table parity, freeze/reload, route coverage, YM exact values, and NQ equivalence.

### Compatibility note

The complete Level Map sender advances its payload identity from the incomplete v13/replacement-tail condition to `v14_canonical_liquidity_sender`. Existing field meanings, stack rules, and receiver structural invariants are unchanged. The additive `timestamp`, `session_date`, `locked`, `atr_1m_14`, complete `liquidity_map.levels`, and separately frozen `session_lock_price` fields complete the documented liquidity-only profile. Receivers remain compatible with structurally conforming historical v13 payloads during the existing compatibility period; this does not authorize new v13 publication or permit receipt time to substitute for source identity in the v14 sender. Coordinated TradingView compilation, publication, and alert cutover remain separately governed.

### Traceability Record

The full-span stack construction, receiver/lock validation, current/historical source identities, and verification are registered in `Architecture/Traceability/2026-07-16_TradingView_Liquidity_Ladder_Architecture_Traceability_Matrix.md`. The July 16 NQ runtime and premarket observed-wick work remain separately mapped in their NQ matrices.
