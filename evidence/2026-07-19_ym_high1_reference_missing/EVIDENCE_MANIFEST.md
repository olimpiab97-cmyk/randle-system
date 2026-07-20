# YM HIGH 1 Frozen Reference Evidence Manifest

Capture date: 2026-07-19 PT / 2026-07-20 UTC

## Live source and relay boundary

- ngrok request ID: `airt_3Gkt4DxFVdw1EtfQCODzjlUOSNa`
- transport start: `2026-07-19T23:00:01-07:00`
- exact raw HTTP SHA-256: `2A0E9E27E710975B82D1B8C28E59154BA5EC3B33FE4E420F9998CEFE7CAFE910`
- exact JSON body SHA-256: `D97399AE6E99CFA281467B17C29FCD57F3340D662425D0950B4E4662E197E676`
- response raw SHA-256: `9B6BB0BFE8C38256CE12A5657E1CB0F6DF8BD64160BE947C8E056D63945C1A3D`
- response body SHA-256: `0DC054C89A7E496A8CBFEB2B3A861B4A83BE4FFF0D2882C818AF49F3948D058F`
- preserved ngrok artifact SHA-256: `6B6D3BABB24DDD909CF184FF25470D13EA2EE6E58F7FC45F0FC69C26D43A141C`
- archived rejection line received at `2026-07-20T06:00:01.261629+00:00`; raw-line SHA-256 `A3F040D8A81CD36B5832F4F9E8FCAA2FBE9985E95B3E094D724925CFF61D31CF`

The body has no `timestamp`, `session_date`, or `session_lock_price`. It declares YH `52835`, `ACTIVE`, `HIGH 1`; explicit HIGH 1 is `ONH,YH`, `52789..52835`; threshold is `59`.

## Runtime snapshots before quarantine

| Artifact | SHA-256 |
|---|---|
| `tv_context_events.jsonl` | `DDE634A12D86CDFF4A8C2B7B12CD5D243D6FACF4D77A80AA8BC668164529150D` |
| `tv_context_by_symbol.json` | `77B1B578C1AC19BCD3705A33838CC91A3FC817D71552409D7DA040C1DBEA7082` |
| `tv_context.json` | `F7E899DAC4C413AD8C0274B9B387A57CF60F9CEC19D87511E30792BBE4276764` |
| `entry_agent_state.json` | `9DE0D7BAA6090603BB5522B6B01D7BC0EB328125EAD0F1381222C68D996F0093` |
| `persistence_state.json` | `D29415E7C446C28E1144BD6F0EC379C0DDDBD84286670AB01708977147295D36` |
| `executor_state.json` | `41543817A0AB4387D99C6503797247C3BD279D50640ACD5284C075AA6E978B96` |

Each copy hash matched its source after services were stopped. The three quarantined Entry Agent artifacts were restored to the listed hashes.

## Stale-state test

Quarantined artifacts:

- `tv_context_by_symbol.json`
- `tv_context.json`
- `entry_agent_state.json`

Observed empty store: `{}`.

Exact body result with artifacts absent: `STACK_REFERENCE_PRICE_MISSING`, `YH`, `HIGH 1`. This proves the current body, not persisted state, produces the rejection.

## Source mapping

| File | Pre-correction SHA-256 | Post-correction SHA-256 |
|---|---|---|
| `REPLACE_ENTRY_AGENT_WEBHOOK_OVERLAPPING_FINALIZED_TABLE_STATE.pine` | `86431E9FD2C9086C1F71DC08026C59B268348E3A70A7DFDA0C4AC41D134B67D2` | `7A677CB6B40AFF4A180A121890C64F50D036E21F96E227ED3A3DBB1ABB2E911F` |

Related unchanged hashes:

- governed Pine: `AFE727A361404F6FF863EE4E63A7DD485A7EB3E0A24ABBD89EB9B97F068092CF`
- shared validator: `D3DA3DA112D239F1A90C3D008B9C02A05E74E7EC13B46721B56B8C1F05F44D93`
- receiver: `D614FF5C6AB45BF64F06860A83B70219B243989976A7AD4E8322B6E4DD806D01`
- launcher blob: `6d67a6bb31689449f2b19b62923ae1c9a003afd1`; accepted commit `7ab6ec65b32a0759c317e470fea617b2023f0616`

## Post-correction runtime observation

Repository correction was not published to TradingView.

- post-validation request ID: `airt_3GkyBgLpgQGgokCKrcv7ezYLIHX`
- start: `2026-07-19T23:42:07-07:00`
- raw HTTP SHA-256: `610F63C387F6F2C870D0863B2C7177FEBAF8E27AD7F56727E2926DECD2191573`
- body SHA-256: unchanged `D97399AE6E99CFA281467B17C29FCD57F3340D662425D0950B4E4662E197E676`
- response: HTTP 400, exact canonical reason unchanged
- preserved post-validation ngrok artifact SHA-256: `26442BD27A9DE5DE1ED31FEB50D83278B2635DF44BE33A681B3BF5CAF21B4DCB`
- latest archived rejection at `2026-07-20T06:43:01.903242+00:00`; raw-line SHA-256 `9CD0836F76708E2958AF54D9636F3DEEA403AFB4F6F81D43404CC6EB02022019`

## Governed startup

Valid terminal launch: `20260719_233503`.

- log SHA-256: `C04D37A5854A1552A3DE0A067E0E48A4A2399342D8763AB4F2D7B499ADAA1DB2`
- evidence SHA-256: `75E2EB6ADDF3DB0B52C31FEE75458271481BC003C049CC2EA8DBE3CE6A37BD21`
- terminal result: `FAILED`, emitted normally
- failed readiness: YM fresh receipt, current-session ladder/lifecycle state, NQ/YM ATR warming

Launch `20260719_232134` is explicitly invalidated because it preserved a delayed isolated temp-root Entry Agent. Launch `20260719_232831` was production-only but externally interrupted before the launcher terminal report. Neither is used for final readiness.

## Safety

- canonical trade authority: 128 records before and after; all record values unchanged; all closed
- Trade Manager projection: 30 records; all closed
- canonical Trade Manager orders: unchanged and zero active
- Executor state SHA-256 unchanged at `41543817...`; 419 historical orders, zero active
- positions: NQU6 `0`, YMU6 `0`
- risk state and failure state unchanged
- no source test or runtime validation authorized a live order

Final read-only safety capture at `2026-07-19T23:49:59-07:00`:

| Role | PID | Listener |
|---|---:|---|
| Executor | 11776 | 6001 |
| Trade Manager | 6168 | 7001 |
| Entry Agent context receiver | 5020 | 7002 |
| ngrok | 14980 | 4040 |
| Rithmic live listener | 4156 | no governed HTTP port |

Each governed port had exactly one owner. The final canonical scan found 128 trades and zero open trades. The Trade Manager projection contained 30 trades and zero open trades. Executor contained 419 historical orders, zero active orders, and flat NQU6/YMU6 positions.

Raw ngrok artifacts and complete runtime copies are retained locally in this evidence directory but intentionally excluded from Git because they contain runtime data and transport metadata.
