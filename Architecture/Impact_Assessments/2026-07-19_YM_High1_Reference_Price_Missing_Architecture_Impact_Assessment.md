# 2026-07-19 YM HIGH 1 Frozen Reference — Architecture Impact Assessment

Document Type: Architecture Impact Assessment and pre-implementation gate

Status: APPROVED FOR REPOSITORY CONFORMANCE CORRECTION; publication and deployment not authorized

Canonical applicability: NQ and YM

## 1. Observation

At `2026-07-19T23:00:01-07:00`, ngrok request `airt_3Gkt4DxFVdw1EtfQCODzjlUOSNa` received a TradingView `YM1!` payload identified as `v14_overlapping_stack_smoke`. The source body declared:

- `YH` price `52835`, status `ACTIVE`, and membership `HIGH 1`;
- explicit `HIGH 1` members `ONH`, `YH`, with complete span `46`;
- frozen `stack_threshold` `59`; and
- no `session_lock_price`, `timestamp`, or `session_date` field.

Entry Agent rejected the payload before persistence with `STACK_REFERENCE_PRICE_MISSING: a frozen market reference is required to validate YH in HIGH 1`.

## 2. Proven first incorrect boundary

The stack assignment itself is not proven incorrect. Under the canonical full-span rule, YH may be a member when all members are on the same frozen market side and the complete span is within the threshold. The received span (`52835 - 52789 = 46`) is within the transmitted threshold (`59`).

The first proven incorrect authority boundary is webhook serialization in `REPLACE_ENTRY_AGENT_WEBHOOK_OVERLAPPING_FINALIZED_TABLE_STATE.pine`. Its `entryAgentPayload` builder emits the exact live version and finalized-table field shape but omits the existing canonical `session_lock_price`. The adjacent smoke serializer and governed source both emit `sessionLockPrice_eff`.

The receiver copies and forwards the JSON object without assigning a market reference. `EntryAgent/tv_context_server.py::build_context` invokes the shared structural validator before merge or persistence. `EntryAgent/liquidity_stack_validation.py::validate_liquidity_stack_structure` correctly requires the frozen reference when a roaming prior-RTH level participates in a side-labeled stack.

## 3. Stale-state discrimination

The current rejected body contains YH membership before relay parsing. A controlled test quarantined `tv_context_by_symbol.json`, `tv_context.json`, and `entry_agent_state.json` after preserving and hashing them. With `stored_context_by_root()` empty, the exact body still returned the identical `STACK_REFERENCE_PRICE_MISSING` result. Each artifact was restored with a SHA-256 match.

Persisted state is therefore not the producer of the current rejection. Historical YM state remains separately invalid/stale and fail-closed, but it does not contaminate this inbound validation.

## 4. Architecture impact classification

Classification: implementation conformance correction at the producing authority.

No authority boundary, eligibility rule, schema meaning, lifecycle rule, strategy rule, risk rule, or deployment rule changes. No ADR is required.

The existing authorities already require this field:

- TradingView Liquidity Ladder Calculation Contract v1.1 sections 8-9;
- TradingView Webhook Contract;
- 06:15 Session Liquidity Lock Contract; and
- TradingView Liquidity Ladder Verification Specification v1.1.

## 5. Canonical Delta

Semantic delta: none.

Representation correction: the finalized-table v14 sender must serialize the already-defined top-level numeric `session_lock_price` using the same frozen `sessionLockPrice_eff` that governed stack construction. A null or missing value remains nonauthoritative and must fail closed when side validation requires it.

YH/YL eligibility, complete-span calculation, stack labels, explicit members, threshold, midpoint/exhaustion calculations, NQ/YM parity, and receiver rejection behavior remain unchanged.

## 6. Approved implementation scope

1. Add `session_lock_price` to the finalized-table v14 TradingView webhook serializer.
2. Add regression coverage for sender serialization, exact missing-reference rejection, valid reference acceptance, symbol parity, stale-state isolation, invalid rehydration, and state-mutation absence.
3. Preserve the exact rejection code and startup fail-closed behavior.
4. Add evidence, traceability, and debt reconciliation records.

No Entry Agent, Trade Manager, Executor, launcher, strategy, order, position, risk, trade-record, production configuration, or deployment logic is approved for change.

## 7. Implementation and verification result

The finalized-table v14 sender now emits `session_lock_price` from the same frozen `sessionLockPrice_eff` authority used by stack construction. No receiver, validator, launcher, trading, order, position, risk, or deployment behavior changed.

Focused regression coverage passes for exact sender serialization, NQ/YM parity, permitted reference separation, precise invalid-ladder rejection, stale-state isolation, invalid rehydration, startup reason preservation, and trade/order/position nonmutation. Parser/static checks pass.

Runtime publication verification does not pass. The active TradingView alert continued to send the byte-identical pre-correction body without `session_lock_price`, so the corrected repository source has not been compiled and cut over. The latest current-session YM body remains correctly rejected. Current-session ladder/lifecycle readiness and canonical ATR readiness also remain independently false.

## 8. Five-gate Governance Verification

| Gate | Decision |
|---|---|
| Architecture | PASS — the existing producer/receiver authority boundary and fail-closed rule remain correct |
| Specification | PASS — existing contracts already require the frozen reference and no semantic amendment is needed |
| Implementation | PASS (repository) — the producing serializer emits the existing required field; prohibited consumers are unchanged |
| Verification | FAIL — focused checks pass, but current-source TradingView compile/publication, a fresh accepted YM receipt, full readiness, and the inherited broad-suite baseline are not proven |
| Traceability | PASS — observation, source boundary, implementation, tests, runtime evidence, and debt are linked bidirectionally |

Overall Governance Verification: **FAIL**.

Root-cause acceptance and repository-correction acceptance are supported. Runtime-readiness acceptance, TradingView publication/cutover, deployment authorization, and live-trading authorization remain **WITHHELD**.
