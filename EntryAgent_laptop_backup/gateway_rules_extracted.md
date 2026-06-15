# Gateway Rules Extracted

Source: `blueprint_spec.md`

This document extracts only explicit Gateway-related rules from `blueprint_spec.md`. No Python code is included.

## 1. Gateway-Related Rules

### Architecture Rules

The Pre-Market Engine is responsible for building the market map before Entry Engine evaluation.

The Entry Engine:

- May only evaluate live price action relative to a validated, pre-built liquidity map.
- Must never reconstruct session logic.
- Must operate only on a fully defined context object.
- Must use the Pre-Market Engine object as its only reference.
- Must not rebuild Step 0.
- Must not recalculate GH/GL.
- Must not re-evaluate stacks.
- Must not override boundaries.
- Must not recalculate session levels.
- Must not reinterpret stacks.
- Must not infer structure.
- Must not rebuild context.

The Pre-Market Engine output must include:

- Session context.
- Finalized liquidity levels.
- Stack and boundary definitions.
- Gateway definition.
- Step Engine state.
- ATR and range context.
- Interaction constraints and flags.
- Nearest newly relevant liquidity.

The final Pre-Market Engine output object is explicitly shown as:

```text
premarket_context = {
   session_context,
   levels,
   gateway,
   step_engine,
   atr,
   constraints,
   next_liquidity
}
```

### Gateway Map Rules

`blueprint_spec.md` states that the Gateway definition must be pre-built:

```text
"gateway": {
   "GH": {"name": "...", "price": value},
   "GL": {"name": "...", "price": value},
   "state": "OFF" or "ARMED"
}
```

Explicit rule:

- Entry Engine must not compute GH/GL.

### Step 1 Gateway Rule

Step 1 defines permission: whether the system is allowed to engage.

Step 1.1 defines Gateway from Step 0:

- GH = closest meaningful liquidity above price.
- GL = closest meaningful liquidity below price.

Important rules:

- GH / GL are not fixed to PMH / PML.
- GH and GL are selected from the liquidity ladder.
- GH and GL must be defined using level names or stack names with associated prices, never raw price values.
- They can be PMH / PML, YH / YL, ONH / ONL, LH / LL.
- PMH, PML, ONH, ONL can only be used as GH/GL after they are locked.
- If price is inside a stack, treat the stack as one liquidity zone and define GH/GL outside the stack boundaries.

Step 1.2 Gateway condition:

If price is between GH and GL:

- Inside Gateway.
- System State = OFF.
- Rejection Mode = OFF.
- Stop.

If price is outside Gateway:

- Outside Gateway.
- System State = ARMED.
- Proceed to Step 2.

Final system truth:

- Step 0 defines reality.
- Step 1 defines permission.

### Session-Built Liquidity Lock Rules Affecting Gateway

The Session-Built Liquidity Lock Rule applies to:

- PMH
- PML
- ONH
- ONL

Before lock time:

- These levels are still developing.
- Any touch before lock is formation only.
- Formation does not count as actionable interaction.
- Formation does not count as activation.
- Formation does not count as consumption.
- These levels are not eligible for Gateway, Trade Mode, or Rejection logic.

After lock time:

- The level becomes official liquidity.
- Not yet touched post-lock = actionable.
- Wick touch post-lock = tagged.
- Close into post-lock = activated.
- Completed interaction cycle = consumed.

Core rule:

- Pre-lock interaction does not matter for trading logic.
- Only post-lock interaction counts.

### Stack Rules Affecting Gateway

Step 0 stack rule:

- If levels are within 10% ATR, treat as one stack.

Step 0 boundary rule:

- Close Boundary = closest level to price.
- Extreme Boundary = furthest level from price.

Gateway stack handling:

- If price is inside a stack, treat the stack as one liquidity zone.
- GH/GL must be defined outside the stack boundaries.

### Nearest Newly Relevant Liquidity Rules Affecting Gateway Context

Definition:

- The next official liquidity level outside the current active level/stack that has not been consumed in the current interaction cycle.

At all times:

- The system must identify the closest active liquidity level relative to current price that represents the next logical interaction target.

A liquidity level is newly relevant if:

- It has not been closed through.
- It has not been consumed.
- It has not completed its interaction cycle.
- It is the next level in the liquidity ladder relative to current price.
- Price is approaching it or has just shifted toward it.

A liquidity level is no longer relevant if:

- Price has closed beyond it and interaction is complete.
- Structure tied to that level has been completed or invalidated.
- A new level has become the closer target after a shift.

Hard rule:

- The system must always operate relative to the nearest newly relevant liquidity.
- No decisions may be based on previously consumed or inactive levels.

## 2. Explicit States

### Global States

Explicit global states in `blueprint_spec.md`:

- OFF
- ARMED
- REJECTION MODE ON
- PROVISIONAL
- NEUTRAL RESET

### Gateway State Values

Explicit gateway state values in the pre-built gateway map:

- OFF
- ARMED

### Step 1 State Values

Explicit Step Engine field:

```text
"step1_state": "OFF/ARMED"
```

### Gateway-Driven State Transitions

If price is between GH and GL:

- Inside Gateway.
- System State = OFF.
- Rejection Mode = OFF.
- Stop.

If price is outside Gateway:

- Outside Gateway.
- System State = ARMED.
- Proceed to Step 2.

## 3. Explicit Time Windows

The Gateway section does not define exact clock-time windows for:

- PREMARKET
- OPENING_WINDOW
- MIDSESSION
- CLOSED

Explicit time-related Gateway-adjacent rules:

- Session context includes `timezone`.
- Session context includes `premarket_locked`.
- PMH, PML, ONH, ONL are not eligible for Gateway before lock time.
- PMH, PML, ONH, ONL become official liquidity after lock time.

Trade Management explicitly defines a 12:00 PM hard cutoff:

- At 12:00 PM, close all open positions immediately.
- Cancel all working orders.
- No new trades allowed.
- Runner exits on stop or 12:00 PM hard cutoff.
- 12:00 PM = flat, done.

Ambiguity:

- `blueprint_spec.md` does not explicitly state whether the Gateway Engine should use the 12:00 PM Trade Management cutoff to classify Gateway `session_phase` as CLOSED.

## 4. Explicit Inputs Required

### Pre-Market Context

The Entry Engine must use the Pre-Market Engine object as its only reference:

```text
premarket_context = {
   session_context,
   levels,
   gateway,
   step_engine,
   atr,
   constraints,
   next_liquidity
}
```

### Session Context

Explicit session context:

```text
{
   "symbol": "NQ",
   "date": "YYYY-MM-DD",
   "timezone": "America/Los_Angeles",
   "premarket_locked": True,
   "london_dst_adjusted": True/False
}
```

### Levels

Finalized liquidity levels must include level name, price, and status:

```text
"levels": {
   "PMH": {"price": PMH_eff, "status": pmhStatus_eff},
   "PML": {"price": PML_eff, "status": pmlStatus_eff},
   "LH":  {"price": LH_eff,  "status": lhStatus_eff},
   "LL":  {"price": LL_eff,  "status": llStatus_eff},
   "ONH": {"price": ONH_eff, "status": onhStatus_eff},
   "ONL": {"price": ONL_eff, "status": onlStatus_eff},
   "YH":  {"price": YH_eff,  "status": yhStatus_eff},
   "YL":  {"price": YL_eff,  "status": ylStatus_eff}
}
```

### Gateway

Explicit Gateway input:

```text
"gateway": {
   "GH": {"name": "...", "price": value},
   "GL": {"name": "...", "price": value},
   "state": "OFF" or "ARMED"
}
```

### Stack and Boundary Definitions

For both sides:

```text
"high_side": {
   "type": "SINGLE" or "STACK",
   "target_name": "...",
   "close_boundary": value,
   "extreme_boundary": value,
   "next_outside": value,
   "encroachment_line": value
}
```

```text
"low_side": {
   ...
}
```

### Step Engine State

Explicit Step Engine input:

```text
"step_engine": {
   "step0_high_type": "SINGLE/STACK",
   "step0_low_type": "SINGLE/STACK",
   "step1_state": "OFF/ARMED",

   "high_side": {
       "step2_triggered": False,
       "step3_eligible": False
   },

   "low_side": {
       "step2_triggered": False,
       "step3_eligible": False
   }
}
```

### ATR / Range Context

Explicit ATR input:

```text
"atr": {
   "daily_atr_14": value,
   "premarket_range": value,
   "premarket_atr_pct": value,
   "overnight_range": value,
   "overnight_range_pct": value
}
```

### Constraints

Explicit constraints input:

```text
"constraints": {
   "stack_requires_extreme_hit": True/False,
   "encroachment_active": True/False,
   "lh_promoted": True/False,
   "inactive_levels_removed": True
}
```

### Next Liquidity

Explicit next liquidity input:

```text
"next_liquidity": {
   "above": {"name": "...", "price": value},
   "below": {"name": "...", "price": value}
}
```

## 5. Explicit Outputs Required

### Gateway Output In Blueprint Text

The blueprint explicitly defines Gateway output/state effects, not a standalone output dict.

If inside Gateway:

- Inside Gateway.
- System State = OFF.
- Rejection Mode = OFF.
- Stop.

If outside Gateway:

- Outside Gateway.
- System State = ARMED.
- Proceed to Step 2.

### Step 0 Output Requirement Connected To Gateway

Step 0 must define:

- Active level or stack.
- Close boundary.
- Extreme boundary.
- Nearest newly relevant liquidity.
- Whether next level is final in ladder.

### Pre-Market Gateway Object Output

The Pre-Market Engine must output:

```text
"gateway": {
   "GH": {"name": "...", "price": value},
   "GL": {"name": "...", "price": value},
   "state": "OFF" or "ARMED"
}
```

### Not Explicitly Defined As Outputs

The following desired output fields are not explicitly defined in `blueprint_spec.md` as a Gateway Engine output dict:

- `gateway_status`
- `gateway_reason`
- `allowed_sides`
- `session_phase`
- `near_liquidity`
- `nearest_level`

Closest explicit mappings from the spec:

- `gateway_status` could map to System State OFF/ARMED or inside/outside Gateway, but this mapping is not explicitly defined.
- `gateway_reason` could be derived from inside/outside Gateway, but exact text is not defined.
- `allowed_sides` is not defined by Gateway rules.
- `session_phase` names PREMARKET / OPENING_WINDOW / MIDSESSION / CLOSED are not defined by Gateway rules.
- `near_liquidity` is not defined as a boolean Gateway output.
- `nearest_level` is related to nearest newly relevant liquidity, but the exact output field is not defined.

## 6. Ambiguities / Assumptions Needing User Confirmation

1. Should the Gateway Engine consume only a full `premarket_context` object, or may it use the current flat `tv_context.json` fields?

2. If `gateway` is missing from context, should Gateway evaluation:
   - block,
   - return unknown,
   - or skip Gateway until premarket_context exists?

3. How should blueprint state values map to requested output values?
   - OFF / ARMED are explicit.
   - OPEN / BLOCKED are requested but not explicit in `blueprint_spec.md`.

4. How should `allowed_sides` be determined?
   - Gateway rules define permission to engage, not LONG / SHORT / BOTH / NONE.
   - Direction appears to be determined later by liquidity interaction and rejection mode.

5. How should `session_phase` be calculated?
   - Requested values are PREMARKET / OPENING_WINDOW / MIDSESSION / CLOSED.
   - `blueprint_spec.md` does not define exact time windows for these phase names.
   - The spec mentions premarket lock and 12:00 PM Trade Management cutoff, but not a Gateway-specific phase model.

6. Should the 12:00 PM Trade Management hard cutoff block Gateway evaluation and set `session_phase = CLOSED`?
   - The cutoff is explicit in Trade Management.
   - It is not explicitly stated as a Gateway rule.

7. What defines `near_liquidity = true`?
   - The spec defines nearest newly relevant liquidity.
   - It does not define a boolean near-liquidity threshold.

8. Should `nearest_level` mean:
   - nearest newly relevant liquidity from `next_liquidity`,
   - GH or GL,
   - active level/stack,
   - or nearest raw level by price?

9. Should PMH/PML/ONH/ONL lock status come from level `status`, `premarket_locked`, a time rule, or another explicit field?

10. Should Entry Agent block if level names/prices are present but level statuses are missing?

11. Should stack handling require `high_side` and `low_side` from premarket_context before Gateway can be evaluated?

12. What should happen when price is inside a stack but no outside-stack GH/GL is provided?

13. Should current rejection state influence Gateway output?
   - Requested Gateway inputs include rejection state.
   - The extracted Gateway rules do not define how rejection state changes Gateway permission.

14. Should `OPENING_WINDOW` exist as an Entry Agent state?
   - The requested output includes it.
   - The blueprint spec extraction does not define it.
