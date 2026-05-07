# Trade State Schema v1

Status: ACTIVE
Owner: Randle System
Last Updated: [4/8/2026]

## 1. Identity

### trade_id
- Type: string
- Example: T-2e9adb51
- Set when: trade is accepted at intake
- Mutable: no
- Purpose: unique identifier for the trade across the entire system

---

### symbol
- Type: string
- Example: NQ
- Set when: trade is submitted
- Mutable: no
- Purpose: identifies which market the trade belongs to

---

### direction
- Type: string (long | short)
- Example: long
- Set when: trade is submitted
- Mutable: no
- Purpose: defines trade bias and determines all price logic (stop, TP1, BE comparisons)


## 2. Entry Package

### entry_price
- Type: float
- Example: 21450.25
- Set when: trade is accepted at intake
- Mutable: no
- Purpose: the approved entry price for the trade

---

### original_stop
- Type: float
- Example: 21438.25
- Set when: trade is accepted at intake
- Mutable: no
- Purpose: stores the initial stop for permanent reference

---

### current_stop
- Type: float
- Example: 21438.25
- Set when: trade is accepted at intake
- Mutable: yes
- Purpose: stores the active stop currently being enforced

---

### tp1_price
- Type: float
- Example: 21462.25
- Set when: trade is accepted at intake
- Mutable: no
- Purpose: defines the first target level for partial profit-taking

---

### be_trigger
- Type: float
- Example: 21456.25
- Set when: trade is accepted at intake
- Mutable: no
- Purpose: defines the price level that triggers stop movement to break even

---

### position_size
- Type: float
- Example: 2.0
- Set when: trade is accepted at intake
- Mutable: no
- Purpose: stores the full original size of the trade

---

### remaining_size
- Type: float
- Example: 2.0
- Set when: trade is accepted at intake
- Mutable: yes
- Purpose: stores how much of the position is still open after TP1 or closure

### Entry Package Invariants
- original_stop never changes after intake
- current_stop must always be a valid stop for the trade direction
- remaining_size must always be less than or equal to position_size
- remaining_size must never be negative
- be_trigger must remain between entry_price and tp1_price in the correct direction


## 3. Status Flags

### status
- Type: string (active | closed)
- Example: active
- Set when: trade is created (active)
- Updated when: trade is fully closed
- Mutable: yes
- Purpose: determines whether the trade is still being managed

---

### tp1_hit
- Type: boolean
- Example: false
- Set when: trade is created
- Updated when: price reaches TP1 level
- Mutable: yes
- Purpose: tracks whether partial profit has been taken

---

### moved_to_be
- Type: boolean
- Example: false
- Set when: trade is created
- Updated when: stop is moved to entry price
- Mutable: yes
- Purpose: tracks whether break-even protection has been activated

---

### be_then_tp1_same_update
- Type: boolean
- Example: false
- Set when: trade is created
- Updated when: BE and TP1 are triggered in the same price update
- Mutable: yes
- Purpose: prevents race condition bugs by recording event order

---

### stop_state
- Type: string (original | break_even | runner_original)
- Example: original
- Set when: trade is created
- Updated when: stop changes state (e.g., BE activation)
- Mutable: yes
- Purpose: tracks the logical state of the stop for management decisions

### Status Flag Invariants
- status = closed → no further updates allowed
- tp1_hit cannot be true if remaining_size == position_size
- moved_to_be must be true if current_stop == entry_price
- be_then_tp1_same_update can only be true if both events occurred in same tick
- stop_state must always reflect the actual stop logic in effect


## 4. Time Fields

### created_at
- Type: datetime (ISO 8601 string)
- Example: 2026-04-08T13:21:25.123456
- Set when: trade is accepted at intake
- Mutable: no
- Purpose: records when the trade was created in the system

---

### last_price_at
- Type: datetime (ISO 8601 string)
- Example: 2026-04-08T13:21:30.654321
- Set when: first price update is received
- Updated when: every price update
- Mutable: yes
- Purpose: tracks when the last price update occurred

---

### be_hit_at
- Type: datetime (ISO 8601 string)
- Example: 2026-04-08T13:22:05.111222
- Set when: BE trigger is hit
- Mutable: no (once set)
- Purpose: records when break-even condition was activated

---

### tp1_hit_at
- Type: datetime (ISO 8601 string)
- Example: 2026-04-08T13:22:10.333444
- Set when: TP1 is hit
- Mutable: no (once set)
- Purpose: records when partial profit was taken

---

### closed_at
- Type: datetime (ISO 8601 string)
- Example: 2026-04-08T13:25:00.000000
- Set when: trade is fully closed
- Mutable: no
- Purpose: records when the trade lifecycle ended

### Time Field Invariants
- created_at must always exist for any trade
- last_price_at must always be ≥ created_at
- be_hit_at cannot exist unless moved_to_be = true
- tp1_hit_at cannot exist unless tp1_hit = true
- closed_at must exist if status = closed
- no timestamp can be modified once set (except last_price_at)


## 5. Live Tracking

### last_price
- Type: float
- Example: 21494.0
- Set when: first price update is received
- Updated when: every price update
- Mutable: yes
- Purpose: represents the most recent market price used for decision-making

---

### exit_price
- Type: float
- Example: 21450.25
- Set when: trade is fully closed
- Mutable: no
- Purpose: stores the final exit price of the trade

---

### exit_reason
- Type: string (stop_hit | manual_flatten | runner_stop | tp_final)
- Example: stop_hit
- Set when: trade is closed
- Mutable: no
- Purpose: explains why the trade was closed

### Live Tracking Invariants
- last_price must always reflect the most recent price update
- exit_price must only be set once when the trade closes
- exit_reason must always be set if status = closed
- exit_price cannot exist if status = active
- last_price must be updated before any trade logic is evaluated


## 6. Valid Values

### status
- active
- closed

---

### direction
- long
- short

---

### stop_state
- original
- break_even
- runner_original

---

### exit_reason
- stop_hit
- manual_flatten
- runner_stop
- tp_final


## 7. Global Invariants (System Guarantees)

### Position Integrity
- remaining_size must always be ≤ position_size
- remaining_size must never be negative
- remaining_size must be 0 when status = closed

---

### Stop Logic
- current_stop must always be valid for trade direction:
  - long → stop < last_price
  - short → stop > last_price
- current_stop must NEVER move away from profitability
- if moved_to_be = true → current_stop must equal entry_price

---

### TP1 Logic
- tp1_hit = true → remaining_size must be < position_size
- tp1_hit cannot be true more than once
- tp1_hit_at must exist if tp1_hit = true

---

### Break-Even Logic
- moved_to_be can only transition from false → true once
- be_hit_at must exist if moved_to_be = true
- BE must be processed before TP1 if both occur in same update

---

### Status Integrity
- status = closed → no further updates allowed
- closed trades cannot receive price updates
- exit_reason must exist if status = closed
- exit_price must exist if status = closed

---

### Event Ordering
- created_at ≤ last_price_at ≤ closed_at
- be_hit_at must occur after created_at
- tp1_hit_at must occur after created_at
- closed_at must be the final timestamp

---

### Same-Tick Protection
- be_then_tp1_same_update can only be true if both BE and TP1 occurred in the same price update
- if true → BE must be processed first, TP1 second

---

### Data Integrity
- no field can be null unless explicitly allowed
- immutable fields must never change after being set
- all price comparisons must respect trade direction


