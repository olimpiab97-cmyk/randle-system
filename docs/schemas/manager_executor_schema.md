\# Trade Manager ↔ Executor Schema



Version: 1.0

Status: LOCKED



\## Purpose



Defines how Trade Manager sends actions and Executor responds.



Trade Manager = decision maker

Executor = action taker



\---



\# Command Format



\## Standard Command



```json

{

&#x20; "action": "submit\_entry",

&#x20; "trade\_id": "T-12345678",

&#x20; "symbol": "NQ",

&#x20; "payload": {}

}

```



\---



\# Actions



\## submit\_entry



```json

{

&#x20; "action": "submit\_entry",

&#x20; "trade\_id": "T-12345678",

&#x20; "symbol": "NQ",

&#x20; "payload": {

&#x20;   "direction": "long",

&#x20;   "qty": 2,

&#x20;   "entry\_price": 20150.25

&#x20; }

}

```



\## submit\_stop



```json

{

&#x20; "action": "submit\_stop",

&#x20; "trade\_id": "T-12345678",

&#x20; "symbol": "NQ",

&#x20; "payload": {

&#x20;   "qty": 2,

&#x20;   "stop\_price": 20138.25

&#x20; }

}

```



\## submit\_limit (TP1)



```json

{

&#x20; "action": "submit\_limit",

&#x20; "trade\_id": "T-12345678",

&#x20; "symbol": "NQ",

&#x20; "payload": {

&#x20;   "qty": 1,

&#x20;   "limit\_price": 20162.25,

&#x20;   "purpose": "tp1"

&#x20; }

}

```



\## cancel\_order



```json

{

&#x20; "action": "cancel\_order",

&#x20; "trade\_id": "T-12345678",

&#x20; "symbol": "NQ",

&#x20; "payload": {

&#x20;   "broker\_order\_id": "STOP-123",

&#x20;   "reason": "move\_to\_be"

&#x20; }

}

```



\## flatten\_symbol



```json

{

&#x20; "action": "flatten\_symbol",

&#x20; "trade\_id": "T-12345678",

&#x20; "symbol": "NQ",

&#x20; "payload": {

&#x20;   "reason": "forced\_flatten"

&#x20; }

}

```



\---



\# Response Format



\## Standard Response



```json

{

&#x20; "success": true,

&#x20; "action": "submit\_stop",

&#x20; "trade\_id": "T-12345678",

&#x20; "symbol": "NQ",

&#x20; "data": {},

&#x20; "error": null,

&#x20; "timestamp": "2026-04-10T06:35:10"

}

```



\---



\## Success Example



```json

{

&#x20; "success": true,

&#x20; "action": "submit\_stop",

&#x20; "trade\_id": "T-12345678",

&#x20; "symbol": "NQ",

&#x20; "data": {

&#x20;   "broker\_order\_id": "STOP-ae9284b3",

&#x20;   "status": "accepted"

&#x20; },

&#x20; "error": null,

&#x20; "timestamp": "2026-04-10T06:35:10"

}

```



\---



\## Failure Example



```json

{

&#x20; "success": false,

&#x20; "action": "submit\_stop",

&#x20; "trade\_id": "T-12345678",

&#x20; "symbol": "NQ",

&#x20; "data": null,

&#x20; "error": {

&#x20;   "code": "STOP\_REJECTED",

&#x20;   "message": "Invalid stop price"

&#x20; },

&#x20; "timestamp": "2026-04-10T06:35:10"

}

```



\---



\# Error Codes



\* INVALID\_PAYLOAD

\* UNKNOWN\_ACTION

\* ORDER\_REJECTED

\* STOP\_REJECTED

\* LIMIT\_REJECTED

\* CANCEL\_FAILED

\* FLATTEN\_FAILED

\* POSITION\_UNKNOWN

\* ORDER\_NOT\_FOUND

\* EXECUTOR\_UNAVAILABLE

\* SYSTEM\_ERROR



\---



\# Rules



\* every command must include trade\_id

\* every response must echo action, trade\_id, symbol

\* executor never changes trade state

\* one action = one response

\* errors must be structured



