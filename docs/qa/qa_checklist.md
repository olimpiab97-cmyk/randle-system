# \# QA Checklist

# Version: 1.0

# Status: ACTIVE

# 

# \## Purpose

# Defines the required test scenarios to validate the trading system before live broker integration.

# 

# Every scenario must be tested and marked:

# \- PASS

# \- FAIL

# 

# \---

# 

# \# 1. Entry Pipeline

# 

# \## Valid Entry

# \- \[ ] valid signal creates trade

# \- \[ ] trade enters pending state

# \- \[ ] entry submitted

# \- \[ ] stop submitted

# \- \[ ] trade becomes active

# 

# \## Invalid Entry

# \- \[ ] missing field rejected

# \- \[ ] invalid direction rejected

# \- \[ ] invalid price structure rejected

# \- \[ ] position\_size <= 0 rejected

# 

# \---

# 

# \# 2. Lifecycle Transitions

# 

# \- \[ ] pending -> active works

# \- \[ ] active -> partial works

# \- \[ ] active -> closed works

# \- \[ ] partial -> closed works

# 

# \## Invalid Transitions

# \- \[ ] pending -> partial blocked

# \- \[ ] closed -> active blocked

# \- \[ ] partial -> active blocked

# 

# \---

# 

# \# 3. Break Even (BE)

# 

# \- \[ ] BE triggers at correct price

# \- \[ ] stop moves to entry

# \- \[ ] moved\_to\_be set correctly

# \- \[ ] BE only executes once

# \- \[ ] BE does not execute on closed trade

# 

# \---

# 

# \# 4. TP1

# 

# \- \[ ] TP1 triggers correctly

# \- \[ ] remaining\_size reduced correctly

# \- \[ ] state moves to partial

# \- \[ ] TP1 only executes once

# 

# \---

# 

# \# 5. BE / TP1 Edge Cases

# 

# \- \[ ] BE before TP1

# \- \[ ] TP1 before BE

# \- \[ ] same-update BE + TP1 handled correctly

# \- \[ ] runner stop preserved after TP1

# 

# \---

# 

# \# 6. Stop Handling

# 

# \- \[ ] stop submitted on entry

# \- \[ ] stop replaced correctly

# \- \[ ] stop always exists for active trade

# \- \[ ] stop cancel + replace works

# 

# \## Failure

# \- \[ ] stop cancel failure triggers flatten

# \- \[ ] stop replace failure triggers flatten

# 

# \---

# 

# \# 7. Flatten

# 

# \- \[ ] manual flatten closes trade

# \- \[ ] forced flatten closes trade

# \- \[ ] flatten sets state to closed

# \- \[ ] no further actions after close

# 

# \---

# 

# \# 8. Duplicate Protection

# 

# \- \[ ] duplicate signal ignored or rejected

# \- \[ ] duplicate TP1 blocked

# \- \[ ] duplicate BE blocked

# \- \[ ] duplicate flatten blocked

# 

# \---

# 

# \# 9. Closed Trade Protection

# 

# \- \[ ] no BE after close

# \- \[ ] no TP1 after close

# \- \[ ] no stop movement after close

# \- \[ ] no reactivation of closed trade

# 

# \---

# 

# \# 10. Error Handling

# 

# \- \[ ] invalid state moves to error

# \- \[ ] system stops normal automation in error

# \- \[ ] error allows only safe actions

# \- \[ ] error does not resume automatically

# 

# \---

# 

# \# 11. Persistence

# 

# \- \[ ] trade saved on creation

# \- \[ ] trade saved on every state change

# \- \[ ] state restored after restart

# \- \[ ] active trade resumes correctly

# 

# \---

# 

# \# 12. Recovery

# 

# \- \[ ] active trade reconciles correctly

# \- \[ ] partial trade reconciles correctly

# \- \[ ] missing stop triggers error

# \- \[ ] position mismatch triggers error

# \- \[ ] unsafe state triggers flatten

# 

# \---

# 

# \# 13. Executor Communication

# 

# \- \[ ] valid command sent correctly

# \- \[ ] response format correct

# \- \[ ] failure response handled correctly

# \- \[ ] unknown action rejected

# 

# \---

# 

# \# 14. System Safety

# 

# \- \[ ] no trade without stop

# \- \[ ] no negative qty

# \- \[ ] no action on unknown trade\_id

# \- \[ ] symbol mismatch blocked

# 

# \---

# 

# \# 15. Final Validation

# 

# \- \[ ] full trade lifecycle works end-to-end

# \- \[ ] no duplicate actions occur

# \- \[ ] no invalid transitions occur

# \- \[ ] no unsafe exposure occurs

