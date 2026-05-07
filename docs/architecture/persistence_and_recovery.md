# Persistence and Recovery
Version: 1.0
Status: LOCKED

## Purpose
Defines how the system stores trade state, restores trade state after restart, and handles uncertainty safely.

The goal is simple:
- active trades must not disappear if the process restarts
- the system must know where trade truth lives
- recovery must protect capital first

---

# 1. Source of Truth

## Official Rule
Trade Manager is the owner of trade lifecycle state.

However, persisted trade records must exist outside memory so the system can recover after restart.

## Required Principle
In-memory state is not enough.
Active and partial trades must be saved to persistent storage.

---

# 2. What Must Be Persisted

For every trade, persist at minimum:

- trade_id
- symbol
- direction
- entry_price
- original_stop
- current_stop
- tp1_price
- be_trigger
- position_size
- remaining_size
- status
- stop_state
- tp1_hit
- moved_to_be
- be_was_hit
- created_at
- closed_at
- exit_reason
- stop_order_id
- tp1_order_id
- entry_order_id
- last_price
- last_price_at
- error_reason

---

# 3. When To Persist

Persist immediately after any important change.

## Required persistence events:
- trade created
- entry confirmed
- stop confirmed
- trade activated
- TP1 hit
- BE moved
- stop changed
- flatten triggered
- trade closed
- trade enters error

## Rule
Do not wait to save later.
Every material state change must be written immediately.

---

# 4. Minimum Storage Rule

The system must maintain a persistent store that survives process restart.

Examples that are acceptable:
- JSON file
- SQLite database
- other durable local storage

## Rule
The first version may use a simple file-based store.
It does not need to be fancy.
It does need to be reliable.

---

# 5. Startup Recovery

When Trade Manager starts:

## Step 1
Load all persisted trades.

## Step 2
Identify trades with state:
- pending
- active
- partial
- error

## Step 3
Do not blindly resume automation yet.

## Step 4
For each non-closed trade, run reconciliation.

---

# 6. Reconciliation Purpose

Reconciliation means:
compare persisted trade state against current real system state before resuming management.

The system must confirm:
- whether position is open
- whether stop exists
- whether working orders exist
- whether remaining size matches expectation

## Rule
No normal automation resumes until reconciliation is complete.

---

# 7. Recovery By State

## Pending
A pending trade found on restart is unsafe unless the system can confirm exactly what happened.

### Rules
- if entry was never confirmed, mark as closed or error based on known facts
- if entry status is uncertain, move to error
- do not auto-promote pending to active by guesswork

---

## Active
For an active trade found on restart:

### Must confirm
- open position exists
- size matches expected live size
- stop exists and matches known protection state

### If confirmed
- resume active management

### If not confirmed
- move to error
- begin safe resolution path

---

## Partial
For a partial trade found on restart:

### Must confirm
- runner position exists
- remaining_size matches persisted state
- runner stop exists and is known

### If confirmed
- resume partial management

### If not confirmed
- move to error
- begin safe resolution path

---

## Error
For an error trade found on restart:

### Rules
- do not resume normal automation
- allow only:
  - flatten_symbol
  - reconciliation
  - logging
  - manual review

---

# 8. Safe Resolution Path

If recovery cannot confirm the trade safely:

## Actions
- move trade to error
- log the reason
- attempt safe flatten if a live position may still exist
- do not continue normal automation

## Principle
If the system is unsure, protect capital first.

---

# 9. Stop Recovery Rule

A live trade without a confirmed stop is unsafe.

## If restart occurs and:
- open position exists
- stop cannot be confirmed

Then:
- trade must move to error
- safe flatten path should be triggered unless a reconciliation module later restores protection with certainty

## Rule
No live position may continue unmanaged without known protection.

---

# 10. Position Mismatch Rule

If persisted trade data and live position data do not match, this is a recovery failure.

Examples:
- persisted size = 2, live size = 1
- persisted state = active, but no position exists
- persisted state = partial, but full size is live
- persisted stop_state does not match actual stop condition

## Action
- move trade to error
- log mismatch
- trigger safe resolution path if needed

---

# 11. Closed Trade Recovery Rule

Closed trades may be loaded for records, but they must not re-enter automation.

## Rule
Closed means final even after restart.

Allowed:
- display
- review
- scoring
- archive

Not allowed:
- BE logic
- TP1 logic
- stop changes
- reactivation

---

# 12. Write Integrity Rule

Persistence writes must be treated as part of trade safety.

## Rules
- failed save = serious system problem
- if material state cannot be saved reliably, move trade/system toward safe halt
- do not continue pretending state is secure if persistence failed

---

# 13. Recovery Logging

Every recovery action must be logged.

Minimum recovery log items:
- startup time
- trade_id
- persisted state found
- reconciliation result
- mismatch details
- recovery action taken
- whether automation resumed
- whether flatten was triggered

---

# 14. Recovery Outcomes

Each recovered trade must end in one of these outcomes:

- resumed_active
- resumed_partial
- closed_no_position
- error_state
- flattened_for_safety

## Rule
Every recovery attempt must produce a clear final classification.

---

# 15. Core Principles

1. In-memory state is never enough
2. Every material trade event must be persisted
3. Restart must trigger reconciliation, not blind continuation
4. Uncertainty means error, not guesswork
5. Live positions without known protection are unacceptable
6. Closed trades never resume automation
7. Capital protection comes before automation continuity