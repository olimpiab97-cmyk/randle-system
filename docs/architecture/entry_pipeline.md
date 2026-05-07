# \# Entry Pipeline

# 

# Version: 1.0

# Status: LOCKED

# 

# \## Purpose

# 

# Defines the exact flow from incoming signal → live managed trade.

# 

# \---

# 

# \# Step 1 — Receive Signal

# 

# Input must follow:

# 

# \* signal\_to\_manager schema

# 

# Action:

# 

# \* receive payload

# \* do not process yet

# 

# \---

# 

# \# Step 2 — Validate Signal

# 

# Check:

# 

# \* required fields present

# \* direction valid

# \* prices valid

# \* position\_size > 0

# \* directional rules correct

# 

# If invalid:

# 

# \* reject signal

# \* return error

# \* STOP

# 

# If valid:

# 

# \* continue

# 

# \---

# 

# \# Step 3 — Create Trade Object

# 

# Create:

# 

# \* trade\_id (if not provided)

# \* store all fields

# \* set:

# 

# ```

# status = pending

# remaining\_size = position\_size

# tp1\_hit = false

# moved\_to\_be = false

# ```

# 

# \---

# 

# \# Step 4 — Submit Entry

# 

# Send to Executor:

# 

# ```

# action: submit\_entry

# ```

# 

# Wait for response.

# 

# \---

# 

# \# Step 5 — Entry Confirmation

# 

# If success:

# 

# \* proceed to stop placement

# 

# If failure:

# 

# \* set state = error

# \* STOP

# 

# \---

# 

# \# Step 6 — Submit Initial Stop

# 

# Send to Executor:

# 

# ```

# action: submit\_stop

# ```

# 

# \* qty = full position

# \* stop\_price = original stop

# 

# Wait for response.

# 

# \---

# 

# \# Step 7 — Stop Confirmation

# 

# If success:

# 

# \* proceed

# 

# If failure:

# 

# \* send flatten\_symbol

# \* set state = error

# \* STOP

# 

# \---

# 

# \# Step 8 — Activate Trade

# 

# Set:

# 

# ```

# status = active

# ```

# 

# Trade is now live and managed.

# 

# \---

# 

# \# Final Result

# 

# Trade is:

# 

# \* active

# \* protected by stop

# \* ready for BE and TP1 logic

# 

# \---

# 

# \# Rules

# 

# \* Trade must NOT skip pending state

# \* Trade must NOT become active without a stop

# \* Trade Manager controls all state changes

# \* Executor only executes actions

# \* Any uncertainty → error state



