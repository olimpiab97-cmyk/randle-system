\### Event: Trade Accepted



Changes:

\- create trade\_id

\- set status = active

\- set remaining\_size = position\_size

\- set tp1\_hit = false

\- set moved\_to\_be = false

\- set stop\_state = original

\- set created\_at timestamp

\- set current\_stop = original\_stop



Actions:

\- send submit\_entry

\- send submit\_stop



\### Event: Price Update



Changes:

\- update last\_price

\- update last\_price\_at



Rules:

\- if status = closed → STOP (ignore update)



\### Event: Stop Hit



Condition:

\- long → last\_price <= current\_stop

\- short → last\_price >= current\_stop



Changes:

\- set remaining\_size = 0

\- set status = closed

\- set exit\_reason = stop\_hit

\- set exit\_price = current\_stop

\- set closed\_at timestamp



Actions:

\- send flatten\_symbol



\### Event: Break-Even Trigger



Condition:

\- moved\_to\_be = false

\- price reaches be\_trigger



Changes:

\- set current\_stop = entry\_price

\- set moved\_to\_be = true

\- set stop\_state = break\_even

\- set be\_hit\_at timestamp



Actions:

\- send modify\_stop → entry\_price



\### Event: TP1 Hit



Condition:

\- tp1\_hit = false

\- price reaches tp1\_price



Changes:

\- reduce remaining\_size

\- set tp1\_hit = true

\- set tp1\_hit\_at timestamp



Actions:

\- partial exit OR logical reduction



\### Event: BE and TP1 Same Update



Condition:

\- both BE and TP1 triggered in same price update



Order:

1\. process BE

2\. process TP1



Changes:

\- set be\_then\_tp1\_same\_update = true



\### Event: Manual Flatten



Changes:

\- set remaining\_size = 0

\- set status = closed

\- set exit\_reason = manual\_flatten

\- set exit\_price = last\_price

\- set closed\_at timestamp



Actions:

\- send flatten\_symbol

