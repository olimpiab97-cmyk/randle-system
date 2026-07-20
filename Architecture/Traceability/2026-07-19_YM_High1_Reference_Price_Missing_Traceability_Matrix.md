# 2026-07-19 YM HIGH 1 Frozen Reference — Bidirectional Traceability Matrix

## Requirement-to-evidence trace

| Requirement | Authority / implementation | Verification / evidence | Result |
|---|---|---|---|
| Preserve original source body | TradingView alert → ngrok raw HTTP | request `airt_3Gkt4DxFVdw1EtfQCODzjlUOSNa`; body SHA-256 `D97399A...` | PASS |
| Prove relay translation | `Engines/trade_manager.py::tradingview_context_proxy_route` forwards parsed JSON unchanged | ngrok response preserves exact Entry Agent code; archived `received_payload` matches source semantics | PASS |
| Prove first YH membership boundary | governed Pine `buildFullSpanSide` / `commitFullSpanCandidate`; v14 `payloadTableStackLabelAtIndex` and `payloadExplicitStackObjectJson` | raw body has YH row and explicit `ONH,YH` membership before receiver | PASS |
| Require frozen market side authority | Liquidity Ladder Contract v1.1; `validate_liquidity_stack_structure` | exact missing-reference test for NQ and YM | PASS |
| Keep reference separate from membership | top-level `session_lock_price`; level `stack_group` and explicit stack members | valid-reference tests preserve both without embedding reference in YH | PASS |
| Correct producing authority | `REPLACE_ENTRY_AGENT_WEBHOOK_OVERLAPPING_FINALIZED_TABLE_STATE.pine` | corrected SHA-256 `7A677CB...`; static serialization test | PASS in repository |
| Do not weaken receiver | `EntryAgent/liquidity_stack_validation.py`; `tv_context_server.py::build_context` | precise rejection remains unchanged | PASS |
| Rule out stale contamination | persisted context/state quarantine with byte-for-byte restoration | empty-store probe returns identical error | PASS |
| Reject invalid rehydration identity | `_rebuild_frozen_lock_from_latest_tv` | prior-session lock returns `not_current_session` | PASS |
| Preserve NQ/YM parity | same sender field and shared validator | parametrized NQ/YM tests | PASS |
| Preserve startup diagnostics | accepted launcher commit `7ab6ec65...` | launch `20260719_233503` reaches terminal `FAILED` with exact gate reasons | PASS |
| Preserve trade/order/position state | Trade Manager and Executor authorities | 128/128 canonical trade records unchanged; Executor SHA unchanged; zero active orders; flat positions | PASS |
| Prove fresh accepted YM session | active TradingView publication | post-validation body remains byte-identical and missing the field | FAIL / DEBT-019 |
| Prove canonical ATR readiness | launcher ATR gate | NQ and YM warming `7/14` | FAIL |

## Implementation-to-authority reverse trace

| Changed implementation | Canonical clause | Regression |
|---|---|---|
| v14 serializer emits `session_lock_price` | Liquidity Ladder Contract v1.1 sections 8-9; Webhook Contract; Session Lock Contract | `test_finalized_sender_serializes_the_existing_frozen_reference_authority` |
| No receiver change | fail-closed incomplete-authority clauses | precise missing-reference and stale-isolation tests |
| No launcher change | accepted commit `7ab6ec65...` | launcher blob `6d67a6b...`; terminal startup evidence |

## Governance trace

- Architecture Impact Assessment: `Architecture/Impact_Assessments/2026-07-19_YM_High1_Reference_Price_Missing_Architecture_Impact_Assessment.md`
- Evidence manifest: `evidence/2026-07-19_ym_high1_reference_missing/EVIDENCE_MANIFEST.md`
- Debt review: `Architecture/Debt/Reviews/2026-07-19_YM_High1_Reference_Price_Missing.md`
- Publication debt: `Architecture/Debt/DEBT-2026-07-19-019_TradingView_V14_Frozen_Reference_Publication_Drift.md`
