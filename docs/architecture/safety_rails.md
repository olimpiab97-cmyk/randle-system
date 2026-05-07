# \# Safety Rails

# Version: 1.0

# Status: LOCKED

# 

# \## Purpose

# Defines the non-negotiable protection rules for the trading system.

# 

# These rules exist to prevent bad trades, duplicate actions, orphaned stops, invalid state changes, and unsafe automation behavior.

# 

# \---

# 

# \# 1. Signal Safety

# 

# \## Reject signal if:

# \- required field is missing

# \- event is not `enter\_trade`

# \- direction is not `long` or `short`

# \- position\_size <= 0

# \- any required price field is missing

# \- any required price field is not numeric

# 

# \## Reject long signal if:

# \- stop\_price >= entry\_price

# \- tp1\_price <= entry\_price

# \- be\_trigger\_price <= entry\_price

# 

# \## Reject short signal if:

# \- stop\_price <= entry\_price

# \- tp1\_price >= entry\_price

# \- be\_trigger\_price >= entry\_price

# 

# \---

# 

# \# 2. Trade Creation Safety

# 

# \## Do not create a trade if:

# \- signal fails validation

# \- another active or partial trade already exists for the same symbol, unless multi-trade mode is explicitly allowed

# \- trade\_id already exists

# \- system cannot assign a valid trade record

# 

# \## Rules:

# \- one trade\_id = one trade only

# \- one symbol should only have one managed trade unless future rules explicitly allow otherwise

# 

# \---

# 

# \# 3. State Safety

# 

# \## Invalid transitions are forbidden

# 

# Allowed transitions only:

# \- pending -> active

# \- active -> partial

# \- active -> closed

# \- partial -> closed

# \- pending -> error

# \- active -> error

# \- partial -> error

# \- error -> closed

# 

# \## Never allow:

# \- pending -> partial

# \- closed -> active

# \- closed -> partial

# \- closed -> pending

# \- partial -> active

# \- error -> active

# \- error -> partial

# 

# \## Rules:

# \- if remaining\_size == 0, trade must be closed

# \- if state == partial, tp1\_hit must be true

# \- closed trades cannot receive new management actions

# 

# \---

# 

# \# 4. Entry Safety

# 

# \## A trade cannot become active unless:

# \- entry is confirmed

# \- initial stop is confirmed

# \- trade state is valid

# 

# \## If entry succeeds but stop fails:

# \- immediately send flatten\_symbol

# \- set trade state = error

# 

# \## Rules:

# \- no live trade without a stop

# \- no guessing on entry state

# \- uncertainty = error

# 

# \---

# 

# \# 5. Break-Even Safety

# 

# \## Do not move to BE if:

# \- moved\_to\_be is already true

# \- trade is not active

# \- stop\_state is not original

# \- trade is closed

# \- trade is in error

# 

# \## Rules:

# \- BE can only happen once

# \- BE must only apply to a valid live position

# \- BE must not run on a closed trade

# \- BE must not run on a partial trade unless future runner rules explicitly allow it

# 

# \## If stop cancel succeeds but replacement stop is not confirmed:

# \- immediately send flatten\_symbol

# \- set state = error

# 

# \---

# 

# \# 6. TP1 Safety

# 

# \## Do not execute TP1 if:

# \- tp1\_hit is already true

# \- trade is not active

# \- trade is closed

# \- trade is in error

# \- remaining\_size is already reduced in a way that makes TP1 invalid

# 

# \## Rules:

# \- TP1 can only happen once

# \- partial state must only occur after confirmed TP1

# \- TP1 must never fire twice

# 

# \---

# 

# \# 7. Order Action Safety

# 

# \## Every command must include:

# \- action

# \- trade\_id

# \- symbol

# \- payload

# 

# \## Reject action if:

# \- trade\_id is missing

# \- trade\_id is unknown

# \- symbol does not match the trade record

# \- action is unknown

# \- payload is malformed

# 

# \## Rules:

# \- one action = one response

# \- executor must return structured success/failure

# \- executor never changes trade state

# 

# \---

# 

# \# 8. Duplicate Protection

# 

# \## Reject or ignore:

# \- duplicate trade signal

# \- duplicate TP1 command

# \- duplicate BE command

# \- duplicate close command

# \- duplicate cancel request for the same completed action

# 

# \## Rules:

# \- same trade event must not execute twice

# \- repeated messages must not create repeated fills or repeated state changes

# 

# \---

# 

# \# 9. Closed Trade Protection

# 

# \## Once a trade is closed:

# \- no BE logic

# \- no TP1 logic

# \- no stop movement

# \- no cancel/replace

# \- no reactivation

# 

# \## Rules:

# \- closed means final

# \- only logging and review are allowed after close

# 

# \---

# 

# \# 10. Error State Protection

# 

# \## If trade enters error:

# \- stop normal automation

# \- allow only safe actions:

# &#x20; - flatten\_symbol

# &#x20; - reconciliation

# &#x20; - logging

# &#x20; - manual review

# 

# \## Rules:

# \- error is a protection state, not a normal operating state

# \- do not resume normal management from error unless a future reconciliation module explicitly allows it

# 

# \---

# 

# \# 11. Symbol Safety

# 

# \## Never allow:

# \- one trade to modify another trade's symbol

# \- one symbol action to apply to a different symbol

# \- stop or flatten commands for the wrong trade

# 

# \## Rules:

# \- trade\_id and symbol must always match the stored trade record

# 

# \---

# 

# \# 12. Quantity Safety

# 

# \## Reject if:

# \- qty <= 0

# \- qty > remaining\_size when action is for partial or runner management

# \- qty does not match intended action

# 

# \## Rules:

# \- full-size actions must use full live size

# \- runner actions must use remaining size only

# \- quantity must always be explicit

# 

# \---

# 

# \# 13. Stop Safety

# 

# \## Reject or fail-safe if:

# \- stop order is missing for a live active trade

# \- stop replacement is attempted without identifying the current stop

# \- cancel succeeds but replacement stop is uncertain

# \- trade is live and protected stop cannot be confirmed

# 

# \## Rules:

# \- every live trade must have a known stop state

# \- no naked exposure allowed

# \- uncertainty about stop protection = flatten + error

# 

# \---

# 

# \# 14. Response Safety

# 

# \## Every executor response must include:

# \- success

# \- action

# \- trade\_id

# \- symbol

# \- data or error

# \- timestamp

# 

# \## Rules:

# \- no freeform ambiguous responses

# \- no silent failures

# \- failures must be structured

# 

# \---

# 

# \# 15. System Safety

# 

# \## If system is unsure about:

# \- position state

# \- working orders

# \- stop status

# \- whether trade is still open

# 

# Then:

# \- move trade to error

# \- trigger safe resolution path

# 

# \## Rules:

# \- system must never guess when money is at risk

# \- uncertainty must be treated as danger

# 

# \---

# 

# \# 16. Core Principle

# 

# When the system is uncertain, it must protect capital first.

# 

# Priority order:

# 1\. protect position

# 2\. prevent duplicate action

# 3\. preserve clean state

# 4\. continue automation only if confirmed safe

