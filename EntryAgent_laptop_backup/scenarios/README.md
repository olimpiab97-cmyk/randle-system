# Synthetic Scenario Runner

These JSON files are isolated proof scenarios for Entry Agent Step 2 and Step 2.5 only.

Run one with:

```powershell
python EntryAgent\synthetic_scenario_runner.py EntryAgent\scenarios\example.json
```

Scenario fields:

- `symbol`: root symbol such as `NQ`.
- `daily_atr`: synthetic daily ATR context for future expansion.
- `tick_size`: optional, defaults to `0.25`.
- `levels`: artificial liquidity table. Use `group` or `stack_group` for stacks.
- `candles`: manually injected closed candles, processed in order.

The runner bypasses live feeds, webhooks, persistence, executor, and Trade Manager. It calls production Step 2, Step 2.5, and active-liquidity selection helpers in memory.
