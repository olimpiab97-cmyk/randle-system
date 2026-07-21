# Manual TradingView Verification Protocol — AFE727A3

Status: PREPARED; NOT EXECUTED

Prepared: 2026-07-16, America/Los_Angeles

Canonical authority: `Architecture/13_Randle_AI_TradingView_Liquidity_Ladder_Verification_Specification.md` §§1, 4, 6, and 7

Related debt: `DEBT-2026-07-16-008`, `DEBT-2026-07-16-010`, and `DEBT-2026-07-16-011`

## 1. Source identity

- Repository source: `C:\Webhook\RandleSystem\TradingView\indicators\Randle_AI_Level_Map_Helper.pine`
- Manual-verification copy: `C:\Users\Trader\Downloads\Randle_AI_Level_Map_Helper_Full_Span_Verification_AFE727A3.pine`
- SHA-256 of each file: `AFE727A361404F6FF863EE4E63A7DD485A7EB3E0A24ABBD89EB9B97F068092CF`
- Bytes in each file: `61,540`
- Pine declaration: version 6
- Indicator title in source: `5/5/2026 Randle AI - Level Map Helper `
- Payload identifier in source: `v13_directional_midpoints`

The download copy was made byte-for-byte from the governed repository source. It is the only revision eligible for this manual run.

## 2. Before opening TradingView

1. Run:

   ```powershell
   Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\Users\Trader\Downloads\Randle_AI_Level_Map_Helper_Full_Span_Verification_AFE727A3.pine'
   ```

2. Stop if the result is not exactly `AFE727A361404F6FF863EE4E63A7DD485A7EB3E0A24ABBD89EB9B97F068092CF`.
3. Copy the entire file into a blank TradingView Pine Editor buffer without editing any byte.
4. Compile and add it to the chart. Do not publish it and do not create, recreate, activate, or alter an alert.
5. If compilation fails, capture the complete compiler error and stop. Do not repair the source in TradingView.

Use a one-minute chart and `America/Los_Angeles` chart time so the session freeze and screenshot timestamps are reviewable. Preserve the indicator defaults, including the 10% Daily ATR stack threshold and all session settings.

## 3. Case A — YM 2026-07-16 over-span YH separation

Chart: `YM1!`, 2026-07-16, after the 06:15 PT freeze.

Expected Liquidity Levels:

| Liquidity Level | Price | Expected label |
|---|---:|---|
| YH | 53088 | `NONE` |
| ONH | 53057 | `HIGH 1` |
| LH | 53057 | `HIGH 1` |
| PMH | 53002 | `HIGH 1` |

Required calculation:

- configured threshold: approximately 60 points; record the exact frozen value displayed by the compiled script;
- proposed complete span: `53088 - 53002 = 86` points; and
- expected result: 86 exceeds the threshold, so YH remains `NONE` while ONH/LH/PMH form `HIGH 1`.

This is the negative case: adjacent proximity to ONH/LH must not pull YH into a transitive over-span stack.

If the compiled script displays a frozen threshold greater than or equal to 86, or any listed source price differs, capture the conflict and do not call the case passed.

## 4. Case B — NQ 2026-06-19 valid prior-RTH membership

Chart: `NQ1!`, session date 2026-06-19, after the 06:15 PT freeze. The archived runtime record normalizes the symbol as NQ; the historical replay market snapshot names the contract `NQM6`. Disable any continuous-contract back adjustment that changes the recorded true prices. If TradingView's historical contract mapping cannot reproduce the exact levels, capture that limitation and do not substitute a different date without a new governed evidence record.

Evidence-backed inputs:

| Liquidity Level | Price | Expected label |
|---|---:|---|
| YH | 30783.25 | `HIGH 2` |
| ONH | 30770.75 | `HIGH 2` |
| PMH | 30670.00 | `HIGH 1` |
| LH | 30666.00 | `HIGH 1` |
| LL | 30535.75 | `LOW 1` |
| PML | 30525.25 | `LOW 1` |
| YL | 30391.00 | `LOW 2` |
| ONL | 30388.00 | `LOW 2` |

Expected Daily ATR and threshold:

- Daily ATR: `711.0385125891`;
- raw 10% threshold: `71.10385125891` points;
- NQ 0.25-tick rounded threshold: `71.00` points;
- YH/ONH complete span: `30783.25 - 30770.75 = 12.50 <= 71.00`; and
- YL/ONL complete span: `30391.00 - 30388.00 = 3.00 <= 71.00`.

The expected table proves both valid prior-RTH memberships: YH joins ONH in `HIGH 2`, and YL joins ONL in `LOW 2`. The more inward groups remain independently numbered because the intervening price gaps would make a combined proposed span exceed the threshold.

Provenance:

- `EntryAgent/logs/operator_actions.jsonl` line 8, file SHA-256 `B167CDA6DA40CB22710EDB5097B97DCF1F76D0AFD0BE5742359715A767A5CC74`, preserves the 2026-06-19 frozen NQ labels and all eight prices.
- `test_entry_status_endpoint.py` lines 9127-9138, file SHA-256 `6DC0D4225421F175C4F175225529491525DFDF55BD34D854BE0153A81732C0B6`, is the existing dated replay fixture that binds those prices to Daily ATR `711.0385125891` and the two valid prior-RTH groups.
- `trades.json`, file SHA-256 `C1835CBAEB2CC8040DFAB043C0FF2FA3691E3200772B818F2AFBC26F2AE37444`, independently preserves that Daily ATR on two NQ durable trade snapshots (`T-3f9e18db` and `T-5dd27285`).

Evidence limitation: the archived operator record is a later replacement audit of a 2026-06-19 frozen lock, not a source-linked TradingView screenshot or original webhook body. The replay fixture and durable trade snapshots corroborate the Daily ATR, but they do not prove execution of SHA `AFE727A3...`. The manual run must confirm the source prices, Daily ATR, frozen threshold, and labels. Any conflict remains open evidence under DEBT-011.

## 5. Screenshots to capture

For each passing case, capture one or more original PNG screenshots that together show:

- symbol and chart date/time;
- the indicator title;
- the Liquidity Level table;
- true prices;
- stack labels;
- visible ladder ordering; and
- enough chart context to establish that the 06:15 freeze has occurred.

Suggested filenames:

- `YM1_2026-07-16_AFE727A3_Over_Span.png`
- `NQ1_2026-06-19_AFE727A3_Valid_Prior_RTH.png`
- `AFE727A3_Pine_Compile_Error.png` if compilation fails

Also record the exact Daily ATR and frozen stack threshold shown for each case. Preserve the original screenshot binaries; do not crop, annotate, recompress, or overwrite them before hashing.

## 6. Owner attestation

Supply this attestation with the screenshots:

> I pasted the exact downloaded source with SHA-256 `AFE727A361404F6FF863EE4E63A7DD485A7EB3E0A24ABBD89EB9B97F068092CF` unchanged into the TradingView Pine Editor. TradingView compiled it and I added that compiled revision to the chart. I made no source edits inside TradingView. The supplied original screenshots came from that compiled revision. I did not create, recreate, activate, or alter any TradingView alert, and I did not publish the indicator.

If any sentence is not true, replace it with the exact limitation rather than attesting.

## 7. Pass/fail boundary

- Case A passes only if the source-linked compiled table shows YH `NONE` and ONH/LH/PMH `HIGH 1` for the complete-span reason.
- Case B passes only if the source-linked compiled table shows at least the expected YH/ONH and YL/ONL memberships with the recorded full spans within the displayed frozen threshold.
- A screenshot from the historical categorical revision `0543DD45...` is not valid evidence for this run.
- A compile screenshot alone does not prove either behavioral case.
- Do not retire DEBT-011 unless both cases pass and every other exit criterion, including applicable broad verification, is satisfied.
- No alert or live webhook execution is authorized by this protocol. Sender/receiver publication compatibility remains a separate gate.

## 8. Preparation traceability

| Preparation artifact/action | Canonical authority | Verification | Debt |
|---|---|---|---|
| Hash-bound repository source and download copy | Verification Specification §§4 and 6 | SHA-256 and byte-length equality | DEBT-008, DEBT-011 |
| Case A | Verification Specification §§1-2 | pending current-source TradingView screenshot | DEBT-011 |
| Case B | Verification Specification §§1-2 and 5-6 | archived lock/replay provenance; pending current-source TradingView screenshot | DEBT-010, DEBT-011 |
| No-publication/no-alert boundary | Verification Specification §7; Development Process Specification §11 | owner attestation and later evidence review | DEBT-008, DEBT-011 |

