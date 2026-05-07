Trade Lifecycle



This is the official state machine for the Trade Manager build.



The goal is simple:



one trade has one clear life

only valid transitions are allowed

Trade Manager owns the brain

Executor only carries out actions

1\. Core Rule

Trade Manager is the only component allowed to change trade state



Executor can:



receive commands

simulate or place orders

return success/failure



Executor cannot:



decide trade status

decide TP1 hit

decide BE move

decide whether trade is partial or closed



That all belongs to Trade Manager.



2\. Official Trade States



Use these states only:



pending

active

partial

closed

error



That is enough.



3\. What Each State Means

pending



Trade has been created, validated, and submitted for entry, but is not yet confirmed live.



This means:



trade record exists

entry process has started

trade is not yet active

management logic should not run yet



Typical conditions:



entry signal accepted

entry order command sent

waiting for confirmation that entry is live

active



Trade is fully live and under management.



This means:



entry confirmed

full size is live

stop should exist

TP1 and BE logic may run

trade has not yet partially exited

partial



Trade is still live, but TP1 has been taken and only the runner remains.



This means:



TP1 already hit

remaining size is less than original size

runner is still active

runner stop logic now applies

TP1 cannot fire again

closed



Trade is fully done.



This means:



remaining size = 0

no more management actions allowed

no more TP1

no more BE

no more stop movement

trade is final except for logging/review

error



Trade entered an unsafe or unresolved condition.



Use this only when the system cannot safely trust the trade state.



Examples:



stop cancel failed and replacement status is unclear

executor returned conflicting order status

trade manager cannot determine whether position is still open

restart caused unresolved mismatch



This is not a normal trade outcome.

This is a protection state.



4\. Official State Transitions



Only these transitions are allowed.



Normal flow

pending -> active

active -> partial

active -> closed

partial -> closed

Failure / protection flow

pending -> error

active -> error

partial -> error

Recovery flow



Only if later designed and verified:



error -> closed



Do not allow automatic error -> active or error -> partial unless a future recovery module explicitly proves it is safe.



5\. Transition Definitions

A. pending -> active



This happens when entry is confirmed and the trade is now live.



Requirements:



entry accepted

position exists or entry is confirmed by executor

initial stop submitted successfully

trade has a valid live structure



Result:



trade becomes manageable

TP1 logic may start

BE logic may start

B. active -> partial



This happens when TP1 is hit and part of the position is exited.



Requirements:



trade is active

TP1 has not already hit

partial exit is confirmed

remaining size > 0



Result:



mark tp1\_hit = True

update remaining\_size

switch state to partial

runner logic becomes active

Atomic BE + TP1 Same-Update Handling

BE and TP1 are detected before any order mutation.

If both are hit on the same price update, TP1 is processed first.

Only the runner quantity gets moved to BE.

If a valid runner stop already exists, the manager reconciles to that stop instead of halting.

If no valid runner stop exists, the system must emergency flatten and halt.

Regression coverage:

test_long_same_update_tp1_then_be_leaves_runner_protected_without_halt

test_tp1_runner_without_valid_stop_emergency_flattens

C. active -> closed



This happens when the trade ends before any partial exists.



Examples:



full stop hit before TP1

manual flatten of full position

BE stop hit before TP1

forced flatten after failure

full exit for any valid reason



Requirements:



remaining size becomes 0



Result:



mark closed\_at

set exit\_reason

no further automation allowed

D. partial -> closed



This happens when runner is no longer open.



Examples:



runner stop hit

manual flatten of runner

forced flatten of runner

final exit taken



Requirements:



remaining size becomes 0



Result:



trade is finished

no further trade actions allowed

E. pending -> error



This happens when entry workflow breaks before the trade becomes live.



Examples:



entry fails

stop cannot be established

malformed execution response

uncertain live state during entry



Result:



trade is frozen for protection

no active management logic should continue blindly

F. active -> error



This happens when an active trade becomes unsafe to manage.



Examples:



stop cancel succeeds but replacement stop is uncertain

executor responses conflict

trade manager loses certainty about live orders or size

live state mismatch after restart



Result:



protection logic takes over

likely forced flatten or manual intervention path

G. partial -> error



Same as above, but while runner is live.



Examples:



runner stop status becomes uncertain

partial fill state is inconsistent

manager cannot trust remaining position state

6\. State Ownership Rules

Trade Manager owns:

status

tp1\_hit

moved\_to\_be

be\_was\_hit

stop\_state

remaining\_size

exit\_reason

timestamps

all transition decisions

Executor owns:

action result only



Examples:



order accepted

order rejected

cancel succeeded

flatten succeeded

stop submitted



Executor reports facts.

Trade Manager interprets them and updates state.



7\. Allowed Logic by State

In pending



Allowed:



validate trade

submit entry

submit initial stop

confirm entry status

reject invalid trade



Not allowed:



BE logic

TP1 logic

runner logic

In active



Allowed:



monitor price

evaluate BE

evaluate TP1

move stop

flatten trade

close trade



Not allowed:



second entry creation

second TP1

In partial



Allowed:



manage runner

flatten runner

monitor runner stop

close trade



Not allowed:



TP1 again

full-size assumptions

original active-state logic that ignores reduced size

In closed



Allowed:



log

score

archive

display



Not allowed:



any order actions

any trade management

any state reactivation

In error



Allowed:



emergency flatten

reconciliation

logging

manual review

safe shutdown logic



Not allowed:



normal automated management as if nothing happened

8\. Required Trade Fields by Lifecycle



These fields should exist across the lifecycle:



trade\_id

symbol

direction

entry\_price

original\_stop

current\_stop

tp1\_price

be\_trigger

position\_size

remaining\_size

status

stop\_state

tp1\_hit

moved\_to\_be

be\_was\_hit

be\_hit\_at

created\_at

closed\_at

exit\_reason



Helpful optional fields:



entry\_confirmed\_at

tp1\_hit\_at

last\_price

last\_price\_at

error\_reason

executor\_ack\_log

9\. Exit Reasons



Use fixed exit reasons so logging stays clean.



Examples:



stop\_loss

breakeven

tp1\_and\_runner\_stop

manual\_flatten

forced\_flatten

entry\_failed

state\_uncertain

runner\_stop

full\_target

system\_error



You do not need every one right now, but they should come from a fixed set.



10\. Non-Negotiable Lifecycle Rules

Rule 1



A trade can never skip directly from pending to partial.



Rule 2



A trade can never leave closed.



Rule 3



A trade can never resume normal management from error unless a future recovery module explicitly reconciles it.



Rule 4



TP1 can only happen once.



Rule 5



BE can only happen once.



Rule 6



If remaining\_size == 0, state must be closed.



Rule 7



If state is partial, then tp1\_hit must be True.



Rule 8



If state is active, then full size should still be live.



Rule 9



Every state transition must be triggered by a defined event, not by guesswork.



11\. Event-to-State Map

Entry accepted and protected

event: entry confirmed + stop confirmed

transition: pending -> active

TP1 hit

event: partial exit confirmed

transition: active -> partial

Full stop hit before TP1

event: full position closed

transition: active -> closed

BE stop hit before TP1

event: remaining size becomes 0 at entry stop

transition: active -> closed

Manual flatten while full size is live

event: flatten confirmed

transition: active -> closed

Manual flatten while runner is live

event: flatten confirmed

transition: partial -> closed

Runner stop hit

event: remaining size becomes 0

transition: partial -> closed

Unsafe uncertainty

event: unresolved order/position mismatch

transition: active -> error or partial -> error

12\. Simplest Visual

pending

&#x20;  ↓

active

&#x20; ↙  ↘

partial  closed

&#x20;  ↓

closed



pending/active/partial

&#x20;  ↓

error

&#x20;  ↓

closed   (only through safe resolution)

13\. What This Locks Down



This checks off:



official state names

official transitions

state ownership

what each module is allowed to do

