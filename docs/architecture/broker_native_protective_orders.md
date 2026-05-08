# Broker-Native Protective Order Architecture

## Current local-executor contract

1. Trade Manager submits an entry order.
2. The executor fills the entry and returns the actual fill price.
3. Trade Manager derives stop, TP1, and BE trigger from the fill.
4. Trade Manager immediately submits a resting stop order for the full position.
5. Trade Manager immediately submits a resting TP1 limit order for 50% of the position.
6. The trade is not marked `active` until the protective stop and TP1 limit are accepted or reconciled as already active.
7. The initial stop and TP1 limit share one `oco_group` (`OCO-<trade_id>-PROTECTIVE`) with roles `protective_stop` and `tp1_limit`.

The local executor persists those orders in `executor_state.json`, so stop and TP1 protection remains present if Trade Manager stops polling after entry.

## Order lifecycle

Initial entry:
- `submit_entry` fills the entry.
- `submit_stop` creates the full-size protective stop.
- `submit_limit` creates the half-size TP1 resting limit.

Break-even:
- BE trigger sends `modify_stop`.
- The existing active stop order keeps the same order ID.
- The stop price changes to entry, quantity remains the current protected quantity, and the executor records `modify_history`.
- The initial protective `oco_group` and `protective_stop` role are preserved.

Stop before TP1:
- The stop fill closes the position.
- The TP1 peer in the same `oco_group` is cancelled with `closed_reason=oco_cancel_after_stop_fill`.
- No active TP1 limit remains after the stop fill.

TP1:
- TP1 limit fill reduces the position.
- The active stop is resized for the remaining runner quantity in the local executor fill path.
- Trade Manager runner handling may then restore the runner stop to original stop with `reset_stop_to_original`.
- The runner stop records `oco_parent_group` and moves to role `runner_stop`; it no longer remains in the initial TP1 OCO group because TP1 has already filled.
- The runner is not allowed to continue without an active stop; uncertain protection is treated as an error/safety condition.

Restart:
- Startup reconciliation reads executor orders and symbol positions.
- Existing active stops, active TP1 limits, trade IDs, order IDs, and orphan exposure are rebuilt from executor truth where possible.
- OCO group fields are persisted in executor orders and copied back into Trade Manager trade state during reconciliation.
- Unknown executor exposure is surfaced as critical orphan exposure instead of being treated as protected.

## Noon cutoff fallback

Current primary path:
- Trade Manager runs the 12:00 PT runner cutoff.
- It sends `flatten_symbol`, marks the runner closed, and records the flatten result.

Required broker-side deployment contingency:
- Rithmic-native deployment should place or maintain a broker-side contingency for the runner, such as a broker-hosted timed flatten/market-on-close equivalent when available, or an external watchdog process that is independent of Trade Manager.
- The watchdog must read broker positions/orders directly, flatten remaining runner exposure at/after 12:00 PT, and cancel stale working orders.
- Until that broker-side timer/watchdog exists, local executor tests can verify only the Trade Manager flatten command and documentation of the independent contingency.

## Rithmic adapter replacement point

The current executor actions are the adapter boundary:
- `submit_entry`
- `submit_stop`
- `submit_limit`
- `modify_stop`
- `reset_stop_to_original`
- `flatten_symbol`
- `sync_snapshot`

A Rithmic adapter should implement these as real native broker orders. For production, stop/TP1 should become native bracket or OCO-linked orders so a TP1 fill and stop cancellation/replacement cannot leave the account unprotected during adapter or network failure.
