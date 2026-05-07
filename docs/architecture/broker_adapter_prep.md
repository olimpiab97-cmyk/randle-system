# \# Broker Adapter Prep

# Version: 1.0

# Status: LOCKED

# 

# \## Purpose

# Defines how the trading system will connect to a real broker without changing Trade Manager logic.

# 

# The goal is simple:

# \- Trade Manager stays broker-agnostic

# \- Executor sends universal actions

# \- Broker adapter translates those actions into broker-specific API calls

# 

# This keeps the brain stable even if the broker changes later.

# 

# \---

# 

# \# 1. Core Design Rule

# 

# Trade Manager must never depend on broker-specific code, wording, or API structure.

# 

# Trade Manager only speaks in system actions.

# 

# Examples:

# \- submit\_entry

# \- submit\_stop

# \- submit\_limit

# \- cancel\_order

# \- flatten\_symbol

# \- get\_position

# \- get\_working\_orders

# 

# The broker adapter is responsible for translating these into broker-specific requests.

# 

# \---

# 

# \# 2. Architecture

# 

# \## System Layers

# 

# 1\. Trade Manager

# &#x20;  - owns logic

# &#x20;  - owns lifecycle

# &#x20;  - owns state transitions

# 

# 2\. Executor

# &#x20;  - receives system actions

# &#x20;  - validates command structure

# &#x20;  - sends requests to broker adapter

# 

# 3\. Broker Adapter

# &#x20;  - converts system commands into broker API calls

# &#x20;  - receives broker responses

# &#x20;  - converts broker responses into system response schema

# 

# 4\. Broker API

# &#x20;  - actual external connection to broker

# 

# \---

# 

# \# 3. Official Adapter Responsibility

# 

# The broker adapter must:

# 

# \- map system action names to broker API actions

# \- map system payload fields to broker-specific fields

# \- normalize broker responses into the standard executor response schema

# \- normalize broker errors into standard system error codes

# \- isolate all broker-specific complexity from Trade Manager

# 

# \---

# 

# \# 4. Universal Actions To Support

# 

# The first broker adapter version must support:

# 

# \- submit\_entry

# \- submit\_stop

# \- submit\_limit

# \- cancel\_order

# \- flatten\_symbol

# \- get\_position

# \- get\_working\_orders

# 

# Optional later:

# \- replace\_order

# \- get\_fills

# \- get\_account\_status

# \- get\_order\_status

# 

# \---

# 

# \# 5. Translation Rule

# 

# \## Input

# The broker adapter receives a standard system command:

# 

# {

# &#x20; "action": "submit\_stop",

# &#x20; "trade\_id": "T-123",

# &#x20; "symbol": "NQ",

# &#x20; "payload": {

# &#x20;   "qty": 2,

# &#x20;   "stop\_price": 20138.25

# &#x20; }

# }

# 

# \## Output

# The broker adapter converts this into the broker's required API format.

# 

# \## Return

# The broker adapter must always return the standard system response structure.

# 

# \---

# 

# \# 6. Standardized Return Rule

# 

# No matter what the broker returns, the adapter must normalize the result into:

# 

# {

# &#x20; "success": true,

# &#x20; "action": "submit\_stop",

# &#x20; "trade\_id": "T-123",

# &#x20; "symbol": "NQ",

# &#x20; "data": {},

# &#x20; "error": null,

# &#x20; "timestamp": "..."

# }

# 

# or

# 

# {

# &#x20; "success": false,

# &#x20; "action": "submit\_stop",

# &#x20; "trade\_id": "T-123",

# &#x20; "symbol": "NQ",

# &#x20; "data": null,

# &#x20; "error": {

# &#x20;   "code": "STOP\_REJECTED",

# &#x20;   "message": "..."

# &#x20; },

# &#x20; "timestamp": "..."

# }

# 

# \---

# 

# \# 7. Broker Isolation Rule

# 

# Broker-specific fields must never leak upward into Trade Manager logic unless intentionally stored as metadata.

# 

# Allowed:

# \- broker\_order\_id

# \- broker\_fill\_id

# \- broker\_account\_id

# 

# Not allowed:

# \- broker-specific status language controlling lifecycle directly

# \- broker-specific enum values becoming system state names

# 

# \---

# 

# \# 8. Required Adapter Mappings

# 

# The adapter must eventually define:

# 

# \## Action Mapping

# Map each system action to broker API request type.

# 

# \## Field Mapping

# Map each payload field into broker request fields.

# 

# Examples:

# \- qty

# \- symbol

# \- direction

# \- entry\_price

# \- stop\_price

# \- limit\_price

# 

# \## Response Mapping

# Convert broker success responses into system schema.

# 

# \## Error Mapping

# Convert broker errors into system error codes.

# 

# \---

# 

# \# 9. Error Normalization Rule

# 

# Broker-specific errors must be translated into standard system error codes whenever possible.

# 

# Standard codes include:

# \- INVALID\_PAYLOAD

# \- ORDER\_REJECTED

# \- STOP\_REJECTED

# \- LIMIT\_REJECTED

# \- CANCEL\_FAILED

# \- FLATTEN\_FAILED

# \- POSITION\_UNKNOWN

# \- ORDER\_NOT\_FOUND

# \- EXECUTOR\_UNAVAILABLE

# \- SYSTEM\_ERROR

# 

# If broker error does not map cleanly:

# \- use SYSTEM\_ERROR

# \- include original broker message in error details

# 

# \---

# 

# \# 10. Position and Orders Rule

# 

# The adapter must support broker queries for:

# 

# \- current position by symbol

# \- current working orders by symbol or trade reference

# 

# This is required for:

# \- reconciliation

# \- restart recovery

# \- stop verification

# \- error handling

# 

# \---

# 

# \# 11. Fill Awareness Rule

# 

# When the broker API later supports fills or execution events, the adapter must normalize them before they reach Trade Manager.

# 

# Examples:

# \- entry filled

# \- TP1 filled

# \- stop filled

# \- partial fill

# \- cancel confirmed

# 

# Trade Manager should receive normalized facts, not raw broker event language.

# 

# \---

# 

# \# 12. Sim vs Live Rule

# 

# The broker adapter layer must support both:

# 

# \- simulated broker mode

# \- live broker mode

# 

# \## Rules

# \- Trade Manager logic should not change between sim and live

# \- only the adapter/backend connection should change

# \- sim and live must share the same action/response contract

# 

# \---

# 

# \# 13. Safety Rule

# 

# If the adapter cannot confirm what happened at the broker level, it must return a structured failure.

# 

# It must never fabricate certainty.

# 

# If uncertain:

# \- return failure

# \- include details

# \- allow Trade Manager to move to safe handling

# 

# \---

# 

# \# 14. Testing Rule

# 

# Before live integration, the adapter must be testable in isolation.

# 

# Minimum adapter tests:

# \- submit\_entry success/fail

# \- submit\_stop success/fail

# \- submit\_limit success/fail

# \- cancel\_order success/fail

# \- flatten\_symbol success/fail

# \- get\_position success/fail

# \- get\_working\_orders success/fail

# 

# \---

# 

# \# 15. Future Broker Swap Rule

# 

# The system should be able to replace one broker adapter with another without rewriting Trade Manager.

# 

# This means:

# \- Trade Manager stays unchanged

# \- Executor command schema stays unchanged

# \- only adapter implementation changes

# 

# \---

# 

# \# 16. Core Principle

# 

# The broker adapter is a translation layer, not a decision layer.

# 

# It translates.

# It does not think.

# It does not own lifecycle.

# It does not change trade logic.

