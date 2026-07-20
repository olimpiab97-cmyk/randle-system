# Randle AI TradingView Liquidity Ladder Verification Specification

Version: 1.2

Document Type: Canonical Verification Specification

Status: Canonical

Authority: TradingView Liquidity Ladder Calculation Contract; TradingView Webhook Contract; 06:15 Session Liquidity Lock Contract

Supersession: Version 1.1 withdrew the version 1.0 tests that treated YH/YL as categorically ineligible. Version 1.2 adds complete-source and source-identity verification for the canonical v14 liquidity sender without changing ladder eligibility.

## 1. Verification principle

Tests verify the canonical contracts; they do not define eligibility. Synthetic or model-level tests may supplement but cannot replace source-linked TradingView compilation and primary evidence when Pine execution is unavailable in the repository environment.

The 2026-07-16 screenshot verifies the YM daily result. It does not verify categorical YH/YL exclusion. Verification must prove the same result for the complete-span reason.

## 2. Required deterministic cases

Verification SHALL prove:

1. YH joins ONH/LH/PMH when the complete PMH-to-YH Liquidity Level span is within the threshold.
2. YH remains independent when that complete span exceeds the threshold.
3. YL joins a low-side stack when its complete span is within the threshold.
4. YL remains independent when that complete span exceeds the threshold.
5. Pairwise adjacency cannot create a transitive stack whose complete span exceeds the threshold.
6. Equal-price YH and another high-side Liquidity Level may stack.
7. Equal-price YL and another low-side Liquidity Level may stack.
8. Multiple independent high-side and low-side stacks receive stable nearest-outward numbering.
9. Every proposed new member is evaluated against the complete existing candidate span, not only its nearest neighbor.
10. Freeze, restore, reload, and late-start reconstruction preserve valid YH/YL membership and preserve valid `NONE` outcomes.
11. Table rows and webhook JSON agree with the same finalized groups.
12. Entry Agent accepts valid prior-RTH membership.
13. Entry Agent rejects a stack whose full Liquidity Level span exceeds the frozen threshold.
14. Entry Agent rejects unknown, mixed-side, undersized, duplicate, overlapping, contradictory, row-mismatched, or nondeterministically numbered definitions.
15. YM 2026-07-16 exact values produce ONH/LH/PMH `HIGH 1` and YH `NONE` because the complete PMH-to-YH span exceeds the threshold.
16. Equivalent NQ high-side and low-side cases follow the same rule.
17. Existing valid stacks without YH/YL remain unchanged.
18. Midpoint and exhaustion construction receives the correct ordered deduplicated anchors after a full-span split.
19. The existing inclusive threshold behavior, 10% Daily ATR setting, and tick normalization are unchanged.
20. Conforming sender payloads retain the existing JSON field shape.
21. The governed publication artifact is a complete Pine script, not a replacement-only tail.
22. The v14 liquidity sender publishes source `timestamp` from confirmed-bar `time_close` in UTC RFC 3339 whole-second form.
23. The v14 liquidity sender publishes `session_date` from the exchange `time_tradingday`, preserving one identity across pre-midnight and post-midnight bars in the same futures session.
24. The sender publishes no authoritative payload when source time, current frozen-session identity, frozen `session_lock_price`, frozen threshold, or required ATR telemetry is unavailable.
25. NQ and YM use one serializer and one source/session/frozen-reference contract without a symbol-specific exception.
26. Deterministic synthetic YM output proves stacked YH membership and separate numeric `session_lock_price`; deterministic NQ output proves the same schema when YH is unstacked.

## 3. Route and restoration verification

Verification SHALL cover:

- live construction;
- 06:15 freeze;
- late-start freeze;
- frozen restoration;
- table projection;
- webhook serialization and receipt archival;
- Entry Agent ingestion and session-lock construction;
- reload and rehydration; and
- repair, force, manual-lock, and legacy paths.

Every authority-exposure route must call the same structural invariant or prove equivalent fail-closed behavior. A scoped ingress test alone is insufficient.

## 4. Pine execution evidence

The preferred verification is automated Pine compilation and execution from the governed repository hash. When that capability is unavailable, repository source-readiness requires all of:

- a deterministic model of the identical grouping algorithm, explicitly labeled non-Pine;
- static source checks that pairwise union and categorical YH/YL guards are absent;
- static completeness checks for the Pine declaration, indicator declaration, helper/calculation/freeze/serializer/publication sections, and exactly one active serializer;
- deterministic synthetic JSON checks for field names, types, duplicate keys, NQ/YM parity, current-session identity, and fail-closed required authority;
- script title/version, canonical path, and exact repository SHA-256; and
- documented limitations and applicable debt.

That result may be labeled `PINE_SOURCE_READY_FOR_MANUAL_TRADINGVIEW_COMPILATION`; it SHALL NOT be labeled `PINE_COMPILED`. Publication additionally requires manual TradingView compilation from the exact repository bytes, captured compiler evidence, and table/webhook evidence from that compiled script.

The existing 2026-07-16 screenshot remains historical manual evidence for that day's split. It cannot provide manual compilation evidence for a later full-span source revision that has not been published or compiled.

## 5. Negative and compatibility cases

Verification SHALL also prove that the correction does not change:

- the set of recognized Liquidity Levels;
- configured threshold percentage, inclusive comparison, or tick normalization;
- high-side/low-side separation;
- finalized-stack numbering direction;
- ladder ordering;
- midpoint or exhaustion formulas;
- Step 2 or Step 4 behavior;
- ATR/RMA, listeners, Trade Manager, or execution behavior;
- trading-session semantics, except for adding the canonical source-generated `timestamp` and `session_date` representations required by the webhook contract; or
- existing field meanings expected by conforming receivers.

Historical fixtures containing YH/YL membership are not invalid by identity. Each must be assessed using its frozen side, threshold, and complete span. Missing authority remains an evidence limitation or debt; it cannot be replaced by categorical assumptions.

## 6. Evidence manifest

Every run or manual compilation record SHALL identify:

- source path and SHA-256;
- indicator title and version;
- compiler or model identity;
- symbol, date, timeframe, frozen reference, threshold, and input settings;
- expected and actual assignments;
- screenshot/payload artifact hashes; and
- known evidence limitations.

Erroneous intermediate revisions must remain preserved with explicit supersession and corrected interpretation.

## 7. Completion and publication gates

Repository source-readiness requires amended authority, deterministic cases, source structure and JSON-contract validation, receiver/session-lock compatibility checks, complete traceability, and reconciliation of every applicable finding. It does not require or imply TradingView compilation, alert publication, service operation, or trading authorization.

TradingView publication additionally requires the exact governed full-span Pine hash, source-linked manual or automated compilation, webhook compatibility proof, coordinated receiver readiness, alert recreation/cutover plan, repository-wide authorization, and explicit publication authorization. Outstanding manual compilation/publication debt remains Blocking for publication, not for committing a repository artifact explicitly marked uncompiled.

## 8. Expected implementation and traceability

Expected implementation areas:

- governed Level Map Helper Pine source under `TradingView/indicators/`;
- shared Entry Agent stack structural validator;
- `EntryAgent/tv_context_server.py`;
- `EntryAgent/entry_agent.py`; and
- deterministic verification support and `test_tradingview_liquidity_ladder.py`.
- complete sender-contract verification in `test_tradingview_canonical_sender.py`.

Expected traceability record:

- `Architecture/Traceability/2026-07-16_TradingView_Liquidity_Ladder_Architecture_Traceability_Matrix.md`.
