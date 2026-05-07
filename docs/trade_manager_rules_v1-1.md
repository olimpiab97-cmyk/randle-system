# Trade Manager Operating Rules v1



Status: ACTIVE
Owner: Randle System
Last Updated: \[4/8/2026]



\# Trade Manager Operating Rules v1

Status: ACTIVE

Owner: Randle System

Last Updated: 2026-04-08





\## 1. Role Definition

Trade Manager is a deterministic post-submit lifecycle engine.

It begins only after a valid manual trade packet is submitted.

It is responsible for validating the packet, creating trade state, sending execution commands, processing price updates, managing BE/TP1/runner logic, and closing the trade.

It does not decide entries, interpret market structure, or create discretionary trades.





\## 2. Trade Packet Input Contract

Trade Manager only accepts a submit event with:

\- event

\- symbol

\- direction

\- entry\_price

\- stop\_price

\- tp1\_price

\- be\_trigger\_price

\- position\_size



Example packet:

{

&#x20; "event": "enter\_trade",

&#x20; "symbol": "NQ",

&#x20; "direction": "long",

&#x20; "entry\_price": 21450.25,

&#x20; "stop\_price": 21438.25,

&#x20; "tp1\_price": 21462.25,

&#x20; "be\_trigger\_price": 21456.25,

&#x20; "position\_size": 2

}





\## 3. Intake Validation Rules

Reject the packet if any required field is missing.

Reject if direction is not long or short.

For long trades: stop\_price < entry\_price < be\_trigger\_price < tp1\_price.

For short trades: stop\_price > entry\_price > be\_trigger\_price > tp1\_price.

Reject if stop distance is zero or negative.

Reject if position\_size is zero or negative.

Reject if daily trade limits are already hit.

Reject if duplicate active-trade rules would be violated.





\## 4. State Fields to Store

On acceptance, Trade Manager creates and stores:

\- trade\_id

\- symbol

\- direction

\- entry\_price

\- original\_stop

\- current\_stop

\- tp1\_price

\- be\_trigger

\- position\_size

\- remaining\_size

\- status

\- tp1\_hit

\- moved\_to\_be

\- be\_then\_tp1\_same\_update

\- stop\_state

\- created\_at

\- last\_price

\- last\_price\_at

\- be\_hit\_at

\- tp1\_hit\_at

\- exit\_price

\- exit\_reason

\- closed\_at





\## 5. Execution Actions on Submit

After successful intake:

1\. Create trade state.

2\. Send submit\_entry command to Executor.

3\. Send submit\_stop command to Executor.

4\. Mark trade status as active.

5\. Begin monitoring price updates.





\## 6. Price Update Processing Order

On every valid price update:

1\. Update last\_price.

2\. Update last\_price\_at.

3\. If trade is closed, ignore update.

4\. Check stop condition first.

5\. Check BE trigger second.

6\. Check TP1 third.

7\. Process same-update BE/TP1 in correct order.

8\. Persist state after any change.





\## 7. BE Rules

If moved\_to\_be is false and price reaches be\_trigger:

\- set current\_stop = entry\_price

\- set moved\_to\_be = true

\- set stop\_state = break\_even

\- set be\_hit\_at timestamp

\- send modify\_stop command to Executor



BE can only occur once.





\## 8. TP1 Rules

If tp1\_hit is false and price reaches tp1\_price:

\- reduce remaining\_size according to TP1 logic

\- set tp1\_hit = true

\- set tp1\_hit\_at timestamp

\- if runner remains open, continue management

\- if no size remains, close trade





\## 9. Same-Tick BE/TP1 Handling

If BE and TP1 are both triggered in the same price update:

\- process BE first

\- process TP1 second

\- set be\_then\_tp1\_same\_update = true



This prevents race-condition errors.





\## 10. Trade Closure Rules

A trade closes when:

\- stop is hit

\- runner stop is hit

\- manual flatten occurs

\- full size is exited



On closure:

\- set status = closed

\- set remaining\_size = 0

\- set exit\_reason

\- set exit\_price

\- set closed\_at

\- block all further management actions





\## 11. Allowed Executor Commands

Trade Manager may only send:

\- submit\_entry

\- submit\_stop

\- modify\_stop

\- cancel\_order

\- flatten\_symbol



Any other outbound command is invalid.





\## 12. Forbidden Actions

Trade Manager must never:

\- decide whether a setup is valid

\- create new discretionary entries

\- modify entry\_price after intake

\- widen a stop

\- manage a trade after status = closed

\- act on malformed packets

\- process unknown command types





\## 13. Global Risk Limits

New trade intake must reject if:

\- max daily trades reached

\- one-loss shutdown rule triggered

\- two-BE shutdown rule triggered



A breakeven trade counts toward the daily trade limit.

