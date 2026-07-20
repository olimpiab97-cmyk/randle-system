# 2026-07-20 Complete TradingView v14 Canonical Sender Traceability Matrix

Scope: repository-only completion of the governed TradingView Level Map liquidity sender

Deployment disposition: NOT AUTHORIZED

## Baseline identity

| Evidence | Identity | Result |
|---|---|---|
| Accepted correction commit | `cf98972743cf665dbc718e83585605f269d6241e` / parent `7ab6ec65...` / tree `32f2e6b8...` | MATCH |
| Accepted replacement tail | `REPLACE_ENTRY_AGENT_WEBHOOK_OVERLAPPING_FINALIZED_TABLE_STATE.pine`, SHA-256 `7A677CB6...` | MATCH; bytes unchanged |
| Original complete local full-span source | `TradingView/indicators/Randle_AI_Level_Map_Helper.pine`, pre-task SHA-256 `AFE727A3...` | PRESERVED AS BASELINE IDENTITY |
| Final complete canonical source | same path, SHA-256 `1C795076...` | GOVERNED PUBLICATION CANDIDATE; UNCOMPILED |

## Authority-to-implementation trace

| Requirement | Canonical authority | Implementation | Verification | Result |
|---|---|---|---|---|
| Complete independently compilable source | Webhook Contract 3.1; Liquidity Ladder Contract 9; Verification Specification 2/4 | complete Pine declaration, indicator, inputs, calculations, freeze state, table, serializer, and `alert()` in `TradingView/indicators/Randle_AI_Level_Map_Helper.pine` | `test_complete_source_and_accepted_tail_provenance`; full-span source-structure test | PASS |
| Preserve accepted frozen reference | Liquidity Ladder Contract 2/8/9; DEBT-019 | `session_lock_price` serializes only `sessionLockPrice_eff`; accepted tail remains unchanged | accepted-tail hash and frozen-reference tests | PASS |
| Source-generated event time | Webhook Contract 5; AIA 3 | `canonicalSourceTimestamp` derives from confirmed-bar `time_close`, formatted UTC `yyyy-MM-dd'T'HH:mm:ss'Z'` | source-time structural test; YM/NQ fixtures | PASS |
| Canonical overnight session identity | Webhook Contract 5; AIA 4 | `canonicalSessionDate` derives from `time_tradingday`; `sessionTradingDay_lock` binds recurrence to the frozen lock | session-date and stale-rehydration tests | PASS |
| Fail closed on missing authority | Webhook Contract 3.1/5; Session Lock Contract | `canonicalPayloadReady` requires one-minute confirmed bar, canonical timezone, current frozen trading day, numeric reference/threshold/ATR, timestamp, and date before `alert()` | sender-gate test; strict missing timestamp/date tests; missing-reference test | PASS |
| Deterministic valid JSON | Webhook Contract 3.1/4/6 | one escaped string serializer, numeric null handling, stable key order, no trailing comma, one payload builder | duplicate-key/type tests and deterministic fixture parse | PASS |
| Complete rows and finalized stacks | Liquidity Ladder Contract 3-9 | all eight top-level levels; all eight `liquidity_map.levels`; complete explicit stacks in both projections | field inventory, fixtures, full-span suite | PASS |
| Keep reference separate from membership | Liquidity Ladder Contract 2/9 | reference is top-level only; YH/YL labels and explicit members remain unchanged | YM stacked-YH fixture and receiver validation | PASS |
| NQ/YM parity | Webhook Contract 2; Verification Specification 2 | one serializer uses `syminfo.ticker`; no NQ/YM branch | parameterized source, fixture, and receiver tests | PASS |
| Receiver remains fail closed | Webhook Contract 6; prior YM correction | no production Python change; existing structural validator still emits exact `STACK_REFERENCE_PRICE_MISSING` | `test_ym_high1_reference_price_contract.py`; canonical sender receiver tests | PASS |
| No strategy/runtime/execution delta | AIA 6; task scope | no Entry Agent, Trade Manager, Executor, risk, runtime, deployment, or alert file is in the scoped change | staged-path audit and production-file blob audit | PASS |
| Compilation/publication remains separate | Verification Specification 4/7; DEBT-019 | source marked ready, never marked compiled | no TradingView access; DEBT-019 remains Blocking | PASS |

## Implementation-to-authority reverse trace

| Changed artifact | Reason | Governing authority | Verification |
|---|---|---|---|
| `TradingView/indicators/Randle_AI_Level_Map_Helper.pine` | establish complete v14 source and source/session/frozen-reference serializer | Webhook Contract 3.1/5; Liquidity Ladder Contract 8/9 | canonical sender and full-span tests |
| `.gitattributes` | preserve LF byte identity for the accepted tail and complete canonical Pine source on Windows checkouts | source-hash publication control | clean-index checkout hashes |
| `docs/schemas/tradingview_webhook_contract.md` | specify exact liquidity profile, source clocks, required fields, and version | ADR-012/runtime authority chain | field inventory, strict parser, and fixture tests |
| `docs/lifecycle/tradingview_liquidity_ladder_calculation_contract.md` | remove obsolete v13 publication identity while preserving ladder semantics | Constitution 17; Session Liquidity Lock Contract | full-span and frozen-reference tests |
| `Architecture/13_Randle_AI_TradingView_Liquidity_Ladder_Verification_Specification.md` | distinguish repository source readiness from TradingView compilation | development/governance process | source structure and deterministic fixture tests |
| `test_tradingview_canonical_sender.py` and NQ/YM fixtures | bind source structure, JSON contract, parity, and receiver compatibility | Verification Specification 2-5 | pytest result |
| `test_tradingview_liquidity_ladder.py` | bind existing full-span suite to the new canonical source identity | Liquidity Ladder Contract 3-12 | pytest result |
| AIA, this matrix, and DEBT-019 | architecture assessment, bidirectional trace, and unresolved publication control | Modernization Charter 3.13/3.16; Debt Specification | document review and staged-path audit |

## Governance verification

### Repository verification record

| Command/check | Result | Disposition |
|---|---|---|
| `python -m py_compile test_tradingview_canonical_sender.py test_tradingview_liquidity_ladder.py test_ym_high1_reference_price_contract.py` | PASS | parser/static check |
| focused canonical sender, full-span, YM reference, shared-boundary, and pre-open projection suites | 67 passed | task verification PASS |
| clean staged-index checkout: canonical sender and full-span suites | 22 passed, 25 explicitly scoped skips | PASS; skips are production receiver/runtime and historical evidence excluded from this source-only commit |
| structural inventory | 1,915 lines; one Pine declaration; one indicator; one payload builder; one active alert call; 2 valid fixtures | task verification PASS |
| `EntryAgent/session_runtime_tests.py` | 16 passed, 13 failed | pre-existing Entry Agent/date/runtime-path baseline; no test reads the changed Pine artifact |
| five selected legacy endpoint rejection tests | 5 failed with HTTP 503 before expected 400 validation | pre-existing fail-closed startup/fixture interaction; production Python excluded from task |
| TradingView Pine compilation | NOT PERFORMED | owned by Blocking DEBT-019 |

| Gate | Task result | Evidence |
|---|---|---|
| Architecture | PASS | narrow AIA classifies completion of existing behavior and identifies no strategy/authority redesign |
| Specification | PASS | webhook, ladder, and verification contracts state exact v14 source representation |
| Implementation | PASS | complete canonical source at SHA-256 `1C795076...`; accepted tail unchanged |
| Verification | PASS | focused source/JSON/receiver/full-span suites pass; TradingView compilation explicitly not performed |
| Traceability | PASS | forward and reverse mappings above; DEBT-019 owns manual compilation/publication work |

Task-level Governance Verification: PASS for repository source readiness.

Repository-wide Governance Verification: FAIL for deployment. DEBT-019 remains Blocking; TradingView compilation/publication, fresh external receipts, current runtime readiness, and explicit deployment authorization are absent. Unrelated pre-existing failures in `EntryAgent/session_runtime_tests.py` also prevent representing the dirty worktree as a clean repository-wide regression baseline.

## Authorization decisions

- Repository artifact completion: authorized by this task.
- Manual TradingView compilation: not performed.
- TradingView publication or alert cutover: not authorized.
- Automated paper entry: withheld.
- Live-money trading: withheld.
