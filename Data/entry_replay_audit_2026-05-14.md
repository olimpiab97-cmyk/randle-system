# Entry Agent Replay Audit - 2026-05-14

## Sources
- reasoning: `C:\Webhook\RandleSystem\Data\entry_reasoning_2026-05-14.jsonl`
- recent_bars: `C:\Webhook\RandleSystem\Data\rithmic_recent_bars.json`
- tv_context_by_symbol: `C:\Webhook\RandleSystem\EntryAgent\tv_context_by_symbol.json`
- tv_context_events: `C:\Webhook\RandleSystem\EntryAgent\tv_context_events.jsonl`
- persistence_state: `C:\Webhook\RandleSystem\Data\persistence_state.json`
- executor_state: `C:\Webhook\RandleSystem\Data\executor_state.json`
- fill_audit: `C:\Webhook\RandleSystem\Data\fill_audit_log.jsonl`

## Summary
- Audited rows: 1045
- Regression cases: 66
- active_liquidity_expected_mismatch: 66

## Candle-by-Candle Findings
| YM | 2026-05-13T20:23:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=LL | actual_liq=PMH | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:07:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:08:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:09:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 2 of 4 remaining=2 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:10:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 3 of 4 remaining=1 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:11:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 4 of 4 remaining=0 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:12:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:13:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:14:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 2 of 4 remaining=2 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:15:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 3 of 4 remaining=1 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:16:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 4 of 4 remaining=0 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:17:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:18:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:19:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 2 of 4 remaining=2 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:20:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 3 of 4 remaining=1 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:21:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 4 of 4 remaining=0 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:22:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:25:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 3 of 4 remaining=1 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:26:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 4 of 4 remaining=0 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:27:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:28:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:29:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 2 of 4 remaining=2 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:30:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 3 of 4 remaining=1 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:31:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 4 of 4 remaining=0 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| NQ | 2026-05-14T04:35:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PMH | actual_liq=PMH/LH/ONH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 3 of 4 remaining=1 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:36:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| NQ | 2026-05-14T04:37:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PMH | actual_liq=PMH/LH/ONH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:37:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| NQ | 2026-05-14T04:38:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PMH | actual_liq=PMH/LH/ONH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:38:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 2 of 4 remaining=2 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| NQ | 2026-05-14T04:39:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PMH | actual_liq=PMH/LH/ONH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 2 of 4 remaining=2 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:39:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 3 of 4 remaining=1 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| NQ | 2026-05-14T04:40:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PMH | actual_liq=PMH/LH/ONH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 3 of 4 remaining=1 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:40:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 4 of 4 remaining=0 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| NQ | 2026-05-14T04:41:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PMH | actual_liq=PMH/LH/ONH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 4 of 4 remaining=0 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:41:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| NQ | 2026-05-14T04:41:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PMH | actual_liq=PMH/LH/ONH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 4 of 4 remaining=0 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T04:41:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=PML | actual_liq=LH/ONH/YH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T13:28:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-14T13:28:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| NQ | 2026-05-14T13:47:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=LH | actual_liq=ONH | control=None mode=None | leg1=WAIT | leg1_window=Candle 3 of 4 remaining=1 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T13:47:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=LL | actual_liq=LL/ONL Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 3 of 4 remaining=1 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T13:47:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=LL | actual_liq=LL/ONL Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 3 of 4 remaining=1 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:13:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:14:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:14:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:15:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 2 of 4 remaining=2 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:16:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 3 of 4 remaining=1 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:17:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 4 of 4 remaining=0 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:18:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:19:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:20:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 2 of 4 remaining=2 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:21:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 3 of 4 remaining=1 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:22:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 4 of 4 remaining=0 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:23:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:25:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 2 of 4 remaining=2 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:26:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 3 of 4 remaining=1 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:27:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 4 of 4 remaining=0 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:28:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:30:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 2 of 4 remaining=2 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:31:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 3 of 4 remaining=1 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:31:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 3 of 4 remaining=1 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:32:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 4 of 4 remaining=0 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:33:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:34:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| RTY | 2026-05-14T15:35:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=Candle 2 of 4 remaining=2 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |

## Leg 1 Window Replay
| YM | 2026-05-14T04:08:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T04:11:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T04:08:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T04:11:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T04:09:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T04:11:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T04:09:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T04:11:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T04:10:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T04:11:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T04:10:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T04:11:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T04:11:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T04:11:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T04:11:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T04:11:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| NQ | 2026-05-14T04:13:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T04:16:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T04:13:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T04:16:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T04:14:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T04:16:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T04:14:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T04:16:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T04:15:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T04:16:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T04:15:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T04:16:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T04:16:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T04:16:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T04:16:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T04:16:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| NQ | 2026-05-14T04:18:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T04:21:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T04:18:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T04:21:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T04:19:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T04:21:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T04:19:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T04:21:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T04:20:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T04:21:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T04:20:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T04:21:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T04:21:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T04:21:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T04:21:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T04:21:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| NQ | 2026-05-14T04:25:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T04:26:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T04:25:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T04:26:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T04:26:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T04:26:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T04:26:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T04:26:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| NQ | 2026-05-14T04:28:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T04:31:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T04:28:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T04:31:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T04:29:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T04:31:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T04:29:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T04:31:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T04:30:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T04:31:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T04:30:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T04:31:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T04:31:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T04:31:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T04:31:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T04:31:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| NQ | 2026-05-14T04:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T04:36:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T04:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T04:36:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T04:37:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T04:40:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T04:38:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T04:41:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T04:38:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T04:40:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T04:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T04:41:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T04:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T04:40:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T04:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T04:41:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T04:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T04:40:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| NQ | 2026-05-14T04:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T04:41:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| NQ | 2026-05-14T04:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T04:41:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:29:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:32:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:30:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:32:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:31:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T13:32:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:32:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:32:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| RTY | 2026-05-14T13:34:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:37:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:37:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T13:37:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T13:37:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:37:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T13:38:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T13:37:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:37:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:38:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:38:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:38:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:38:00Z | invalidated=True | reason=Candle B failed both close-based participation and 34% wick-based participation. |
| YM | 2026-05-14T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T13:42:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:42:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:42:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:42:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:42:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| RTY | 2026-05-14T13:42:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:42:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:42:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:42:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:42:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:42:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:42:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:42:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:42:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:42:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:42:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:42:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:42:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:42:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:42:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:42:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:42:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:42:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:42:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:42:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:42:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:42:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:42:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:42:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:42:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:42:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:47:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T13:45:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:48:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:45:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:48:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:45:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:47:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:46:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:48:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:46:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T13:47:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T13:46:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:48:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:47:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T13:48:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:47:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:47:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| RTY | 2026-05-14T13:47:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T13:48:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:47:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T13:48:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T13:47:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T13:48:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:48:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:48:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| RTY | 2026-05-14T13:48:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:48:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:49:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:52:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:50:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:52:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T13:50:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:53:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:51:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T13:52:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T13:51:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:53:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T13:52:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T13:53:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:52:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:52:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| RTY | 2026-05-14T13:53:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:53:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:54:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:57:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T13:55:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:58:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:55:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T13:58:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:55:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:57:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:56:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:58:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:56:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T13:57:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T13:56:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T13:58:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T13:57:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T13:58:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T13:57:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:57:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| RTY | 2026-05-14T13:57:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T13:58:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T13:58:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:58:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| NQ | 2026-05-14T13:58:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T13:58:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T13:59:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:02:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:00:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:02:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:00:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:03:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:01:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:02:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:01:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:03:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:05:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:02:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| RTY | 2026-05-14T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:03:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:03:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| NQ | 2026-05-14T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:05:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:07:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:05:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:05:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T14:05:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:07:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:06:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:07:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:07:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:07:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| NQ | 2026-05-14T14:07:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:10:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:08:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:10:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:09:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:10:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:09:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:10:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:10:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T14:10:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:12:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:11:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:12:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:12:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:12:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| NQ | 2026-05-14T14:13:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:16:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:13:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:16:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:14:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:17:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:14:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:16:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:14:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:16:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:14:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:16:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:14:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:16:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:14:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:16:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:14:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:16:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:14:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:16:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:14:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:16:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:14:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:16:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:14:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:16:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:14:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:16:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:14:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:16:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:15:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:16:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:15:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:17:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:15:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:16:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:15:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:16:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:16:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:16:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T14:16:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:17:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:16:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:16:00Z | invalidated=True | reason=Candle B failed both close-based participation and 34% wick-based participation. |
| YM | 2026-05-14T14:17:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:17:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| NQ | 2026-05-14T14:19:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:22:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:19:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:22:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:20:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:22:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:20:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:22:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:21:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:22:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:21:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:22:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:22:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:22:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T14:22:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:22:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| RTY | 2026-05-14T14:23:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:26:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:23:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:26:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:24:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:27:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:24:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:26:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:24:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:26:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:24:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:26:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:24:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:26:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:24:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:26:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:24:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:26:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:24:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:26:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:24:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:26:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:24:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:26:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:25:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:26:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:25:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:28:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:25:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:27:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:25:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:26:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:25:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:26:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:26:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:28:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:26:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:26:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| RTY | 2026-05-14T14:26:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:26:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| NQ | 2026-05-14T14:27:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:28:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:27:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:27:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| NQ | 2026-05-14T14:28:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:28:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| RTY | 2026-05-14T14:28:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:31:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:29:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:32:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:29:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:31:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:30:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:33:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:30:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:32:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:30:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:31:00Z | invalidated=False | reason=None |
| NQ | 2026-05-14T14:31:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:33:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:31:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:32:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:31:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:31:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| NQ | 2026-05-14T14:32:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:33:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:32:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:32:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| NQ | 2026-05-14T14:33:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:33:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| RTY | 2026-05-14T14:33:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:36:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:34:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:37:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:34:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:36:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:37:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:35:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:36:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:37:00Z | invalidated=False | reason=None |
| RTY | 2026-05-14T14:36:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:36:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T14:37:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:37:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T14:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:42:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:42:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:42:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:42:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-14T14:42:00Z | invalidated=True | reason=Candle 4 closed without valid Shared Leg 1 participation. |
| YM | 2026-05-14T14:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-14T14:47:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:45:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-14T14:47:00Z | invalidated=False | reason=None |
| YM | 2026-05-14T14:46:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-14T14:47:00Z | invalidated=False | reason=None |

## Confirmed Structure / Pathway Control
| NQ | 2026-05-14T15:16:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:16:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:17:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:17:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:17:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:17:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:17:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:17:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:17:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:17:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:17:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:17:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:17:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:17:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:17:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:19:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:19:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:21:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:21:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:22:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:23:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:25:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:25:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:25:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:25:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:25:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:25:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:25:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:25:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:25:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:25:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:25:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:25:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:25:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:27:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:27:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:28:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:28:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:28:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:28:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:28:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:28:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:28:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:28:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:28:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:28:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:28:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:28:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:29:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:30:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:31:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:32:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:33:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:34:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:35:00Z | step=Step 4 | leg1=COMPLETE | control=None | mode=None | continuation=None | leg2=WAIT |
| NQ | 2026-05-14T15:37:00Z | step=Step 4 | leg1=COMPLETE | control=rejection | mode=Normal Rejection Mode | continuation=R/S | leg2=WAIT |
| NQ | 2026-05-14T15:38:00Z | step=Step 4 | leg1=COMPLETE | control=rejection | mode=Normal Rejection Mode | continuation=R/S | leg2=WAIT |

## Regression Cases
- `active_liquidity_expected_mismatch` YM 2026-05-13T20:23:00Z: Expected active liquidity LL from the logged candle close and TV levels, but status published PMH. expected=LL actual=PMH
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:07:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:08:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:09:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:10:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:11:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:12:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:13:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:14:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:15:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:16:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:17:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:18:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:19:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:20:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:21:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:22:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:25:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:26:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:27:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:28:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:29:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:30:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:31:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` NQ 2026-05-14T04:35:00Z: Expected active liquidity PMH from the logged candle close and TV levels, but status published PMH/LH/ONH Liquidity. expected=PMH actual=PMH/LH/ONH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:36:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` NQ 2026-05-14T04:37:00Z: Expected active liquidity PMH from the logged candle close and TV levels, but status published PMH/LH/ONH Liquidity. expected=PMH actual=PMH/LH/ONH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:37:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` NQ 2026-05-14T04:38:00Z: Expected active liquidity PMH from the logged candle close and TV levels, but status published PMH/LH/ONH Liquidity. expected=PMH actual=PMH/LH/ONH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:38:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` NQ 2026-05-14T04:39:00Z: Expected active liquidity PMH from the logged candle close and TV levels, but status published PMH/LH/ONH Liquidity. expected=PMH actual=PMH/LH/ONH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:39:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` NQ 2026-05-14T04:40:00Z: Expected active liquidity PMH from the logged candle close and TV levels, but status published PMH/LH/ONH Liquidity. expected=PMH actual=PMH/LH/ONH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:40:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` NQ 2026-05-14T04:41:00Z: Expected active liquidity PMH from the logged candle close and TV levels, but status published PMH/LH/ONH Liquidity. expected=PMH actual=PMH/LH/ONH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:41:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` NQ 2026-05-14T04:41:00Z: Expected active liquidity PMH from the logged candle close and TV levels, but status published PMH/LH/ONH Liquidity. expected=PMH actual=PMH/LH/ONH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T04:41:00Z: Expected active liquidity PML from the logged candle close and TV levels, but status published LH/ONH/YH Liquidity. expected=PML actual=LH/ONH/YH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T13:28:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-14T13:28:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` NQ 2026-05-14T13:47:00Z: Expected active liquidity LH from the logged candle close and TV levels, but status published ONH. expected=LH actual=ONH
- `active_liquidity_expected_mismatch` RTY 2026-05-14T13:47:00Z: Expected active liquidity LL from the logged candle close and TV levels, but status published LL/ONL Liquidity. expected=LL actual=LL/ONL Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T13:47:00Z: Expected active liquidity LL from the logged candle close and TV levels, but status published LL/ONL Liquidity. expected=LL actual=LL/ONL Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:13:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:14:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:14:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:15:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:16:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:17:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:18:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:19:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:20:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:21:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:22:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:23:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:25:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:26:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:27:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:28:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:30:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:31:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:31:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:32:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:33:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:34:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` RTY 2026-05-14T15:35:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
