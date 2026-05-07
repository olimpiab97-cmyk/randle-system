# Signal → Trade Manager Schema

Version: 1.0
Status: LOCKED

## Purpose

Defines the required structure for any incoming trade signal.
If a signal does not meet these rules, it must be rejected.

---

## Required Payload

```json
{
  "event": "enter_trade",
  "symbol": "NQ",
  "direction": "long",
  "entry_price": 20150.25,
  "stop_price": 20138.25,
  "tp1_price": 20162.25,
  "be_trigger_price": 20156.25,
  "position_size": 2
}
```

---

## Required Fields

* event → must be `"enter_trade"`
* symbol → instrument (NQ, ES, etc.)
* direction → `"long"` or `"short"`
* entry_price → number
* stop_price → number
* tp1_price → number
* be_trigger_price → number
* position_size → number > 0

---

## Optional Fields

```json
{
  "trade_id": "T-12345678",
  "source": "tradingview",
  "timestamp": "2026-04-10T06:31:00",
  "strategy_tag": "ILC_rejection",
  "notes": "PMH rejection"
}
```

---

## Validation Rules

Reject if:

* missing required field
* event is not `"enter_trade"`
* direction not `"long"` or `"short"`
* position_size ≤ 0
* any price is not numeric

---

## Direction Rules

### Long

* stop_price < entry_price
* tp1_price > entry_price
* be_trigger_price > entry_price

### Short

* stop_price > entry_price
* tp1_price < entry_price
* be_trigger_price < entry_price

---

## Behavior

### Valid Signal

* create trade
* set state = pending
* begin entry workflow

### Invalid Signal

* reject
* return error
* do NOT create trade
