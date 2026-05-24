# Entry Agent Replay Audit - 2026-05-18

## Sources
- reasoning: `C:\Webhook\RandleSystem\Data\entry_reasoning_2026-05-18.jsonl`
- recent_bars: `C:\Webhook\RandleSystem\Data\rithmic_recent_bars.json`
- tv_context_by_symbol: `C:\Webhook\RandleSystem\EntryAgent\tv_context_by_symbol.json`
- tv_context_events: `C:\Webhook\RandleSystem\EntryAgent\tv_context_events.jsonl`
- persistence_state: `C:\Webhook\RandleSystem\Data\persistence_state.json`
- executor_state: `C:\Webhook\RandleSystem\Data\executor_state.json`
- fill_audit: `C:\Webhook\RandleSystem\Data\fill_audit_log.jsonl`

## Summary
- Audited rows: 833
- Regression cases: 39
- active_liquidity_expected_mismatch: 39

## Candle-by-Candle Findings
| YM | 2026-05-18T13:47:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=rejection mode=Normal Rejection Mode | leg1=WAIT | leg1_window=Candle 0 of 4 remaining=4 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T13:47:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=continuation mode=R/S | leg1=WAIT | leg1_window=Candle 0 of 4 remaining=4 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T13:49:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=rejection mode=Normal Rejection Mode | leg1=WAIT | leg1_window=Candle 0 of 4 remaining=4 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T13:50:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=rejection mode=Normal Rejection Mode | leg1=WAIT | leg1_window=Candle 0 of 4 remaining=4 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T13:50:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=rejection mode=Normal Rejection Mode | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T13:51:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=rejection mode=Normal Rejection Mode | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T13:52:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=YH | control=rejection mode=Normal Rejection Mode | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T13:52:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=rejection mode=Normal Rejection Mode | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T13:53:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=rejection mode=Normal Rejection Mode | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T13:54:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=rejection mode=Normal Rejection Mode | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T13:55:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=rejection mode=Normal Rejection Mode | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T13:56:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=rejection mode=Normal Rejection Mode | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T13:57:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=rejection mode=Normal Rejection Mode | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T13:58:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=rejection mode=Normal Rejection Mode | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T13:59:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=rejection mode=Normal Rejection Mode | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:00:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=rejection mode=Normal Rejection Mode | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:01:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=rejection mode=Normal Rejection Mode | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:02:00Z | close_confirmed=False | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=rejection mode=Normal Rejection Mode | leg1=WAIT | leg1_window=Candle 1 of 4 remaining=3 | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:04:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:08:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:09:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:10:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:11:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:12:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:13:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:17:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:18:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:19:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:20:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:24:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:25:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:26:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:27:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:28:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:29:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:30:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:31:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:32:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |
| YM | 2026-05-18T14:33:00Z | close_confirmed=True | expected_step=Step 2 | actual_step=Step 2 | expected_liq=ONH | actual_liq=ONH/PMH Liquidity | control=None mode=None | leg1=WAIT | leg1_window=- | leg2=WAIT | trades=- | flags=active_liquidity_mismatch |

## Leg 1 Window Replay
| NQ | 2026-05-18T13:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T13:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=False | expires_at=2026-05-15T15:46:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=False | expires_at=2026-05-15T14:28:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=False | expires_at=2026-05-15T14:28:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T13:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=False | expires_at=2026-05-15T15:46:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:05:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:06:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:07:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:08:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:09:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:10:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:11:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:12:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:13:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:14:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:22:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:23:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:24:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:25:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:26:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:27:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:28:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:29:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:30:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:31:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=False | expires_at=2026-05-15T15:12:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:38:00Z | step=Step 2 | leg1=WAIT | window=Candle 0 of 4 | remaining=4 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:39:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:40:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:41:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:42:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:42:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:43:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| NQ | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 0 of 4 | remaining=4 | active=True | expires_at=2026-05-18T13:48:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:42:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| RTY | 2026-05-18T13:44:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T13:42:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:45:00Z | step=Step 4 | leg1=COMPLETE | window=Candle 1 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:48:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:46:00Z | step=Step 2 | leg1=WAIT | window=Candle 0 of 4 | remaining=4 | active=True | expires_at=2026-05-18T13:50:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:46:00Z | step=Step 2 | leg1=WAIT | window=Candle 0 of 4 | remaining=4 | active=True | expires_at=2026-05-18T13:50:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T13:47:00Z | step=Step 2 | leg1=WAIT | window=Candle 0 of 4 | remaining=4 | active=True | expires_at=2026-05-18T13:51:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:47:00Z | step=Step 4 | leg1=COMPLETE | window=Candle 1 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:50:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T13:47:00Z | step=Step 2 | leg1=WAIT | window=Candle 0 of 4 | remaining=4 | active=True | expires_at=2026-05-18T13:51:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T13:48:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T13:51:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:49:00Z | step=Step 2 | leg1=WAIT | window=Candle 0 of 4 | remaining=4 | active=True | expires_at=2026-05-18T13:53:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T13:49:00Z | step=Step 2 | leg1=WAIT | window=Candle 0 of 4 | remaining=4 | active=True | expires_at=2026-05-18T13:53:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T13:50:00Z | step=Step 4 | leg1=COMPLETE | window=Candle 1 of 4 | remaining=0 | active=False | expires_at=2026-05-18T13:53:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T13:50:00Z | step=Step 2 | leg1=WAIT | window=Candle 0 of 4 | remaining=4 | active=True | expires_at=2026-05-18T13:53:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T13:50:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=False | expires_at=2026-05-18T13:53:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T13:51:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=False | expires_at=2026-05-18T13:53:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T13:52:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=False | expires_at=2026-05-18T13:53:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T13:52:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=False | expires_at=2026-05-18T13:53:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T13:53:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=False | expires_at=2026-05-18T13:53:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T13:54:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=False | expires_at=2026-05-18T13:53:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T13:55:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=False | expires_at=2026-05-18T13:53:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T13:56:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=False | expires_at=2026-05-18T13:53:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T13:57:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=False | expires_at=2026-05-18T13:53:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T13:58:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=False | expires_at=2026-05-18T13:53:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T13:59:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=False | expires_at=2026-05-18T13:53:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T14:00:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=False | expires_at=2026-05-18T13:53:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:01:00Z | step=Step 2 | leg1=WAIT | window=Candle 0 of 4 | remaining=4 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T14:01:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=False | expires_at=2026-05-18T13:53:00Z | invalidated=False | reason=None |
| YM | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=False | expires_at=2026-05-18T13:53:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T14:05:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T14:05:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T14:05:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T14:05:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T14:05:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T14:05:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T14:05:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:02:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T14:05:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T14:05:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T14:05:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T14:05:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T14:05:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T14:05:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T14:05:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T14:05:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |
| NQ | 2026-05-18T14:03:00Z | step=Step 2 | leg1=WAIT | window=Candle 1 of 4 | remaining=3 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 2 of 4 | remaining=2 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 3 of 4 | remaining=1 | active=True | expires_at=2026-05-18T14:05:00Z | invalidated=False | reason=None |
| NQ | 2026-05-18T14:04:00Z | step=Step 2 | leg1=WAIT | window=Candle 4 of 4 | remaining=0 | active=False | expires_at=2026-05-18T14:05:00Z | invalidated=True | reason=Leg 1 invalid: no valid Candle B formed within 4 candles after Step 2 confirmation. |

## Confirmed Structure / Pathway Control
| NQ | 2026-05-18T13:45:00Z | step=Step 4 | leg1=COMPLETE | control=rejection | mode=Normal Rejection Mode | continuation=S/R | leg2=WAIT |
| NQ | 2026-05-18T13:47:00Z | step=Step 4 | leg1=COMPLETE | control=rejection | mode=Normal Rejection Mode | continuation=S/R | leg2=WAIT |
| NQ | 2026-05-18T13:50:00Z | step=Step 4 | leg1=COMPLETE | control=rejection | mode=Normal Rejection Mode | continuation=S/R | leg2=WAIT |

## Regression Cases
- `active_liquidity_expected_mismatch` YM 2026-05-18T13:47:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T13:47:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T13:49:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T13:50:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T13:50:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T13:51:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T13:52:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published YH. expected=ONH actual=YH
- `active_liquidity_expected_mismatch` YM 2026-05-18T13:52:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T13:53:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T13:54:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T13:55:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T13:56:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T13:57:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T13:58:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T13:59:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:00:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:01:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:02:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:04:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:08:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:09:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:10:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:11:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:12:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:13:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:17:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:18:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:19:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:20:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:24:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:25:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:26:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:27:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:28:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:29:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:30:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:31:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:32:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
- `active_liquidity_expected_mismatch` YM 2026-05-18T14:33:00Z: Expected active liquidity ONH from the logged candle close and TV levels, but status published ONH/PMH Liquidity. expected=ONH actual=ONH/PMH Liquidity
