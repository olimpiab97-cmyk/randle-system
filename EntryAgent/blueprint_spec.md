# Entry Agent Blueprint Spec

Source: `raw_entry_blueprint.txt`

This spec organizes the raw Entry Agent blueprint into implementation-ready sections. It does not change rules, simplify logic, or add code.

## 1. System Architecture

### Pre-Market Engine

The Pre-Market Engine is the map builder. It constructs the complete structured market map before Step 1 begins.

Core law:

- The Entry Engine may only evaluate live price action relative to a validated, pre-built liquidity map.
- The Entry Engine must never reconstruct session logic.
- The Entry Engine must operate only on a fully defined context object.

The Pre-Market Engine output must include:

- Session context.
- Finalized liquidity levels.
- Stack and boundary definitions.
- Gateway definition.
- Step Engine state.
- ATR and range context.
- Interaction constraints and flags.
- Nearest newly relevant liquidity.

The final output object is:

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

### Entry Engine

The Entry Engine is the live decision engine.

It must:

- Use the Pre-Market Engine object as its only reference.
- Execute Steps 2-6 using the pre-built structure.
- Respect all Step rules already defined.
- Read, react, execute.

It must not:

- Rebuild Step 0.
- Recalculate GH/GL.
- Re-evaluate stacks.
- Override boundaries.
- Recalculate session levels.
- Reinterpret stacks.
- Infer structure.
- Rebuild context.

### Trade Manager

The Trade Manager is the execution and risk engine.

System architecture law:

- Pre-Market Engine = Map Builder.
- Entry Engine = Live Decision Engine.
- Trade Manager = Execution + Risk Engine.

Final bank line:

- Pre-Market defines reality.
- Entry Engine reacts to reality.
- Trade Manager executes reality.

## 2. Global States

### OFF

No active interaction.

### ARMED

Waiting for trigger into liquidity.

### REJECTION MODE ON

Interaction active, rejection pathways eligible.

### PROVISIONAL

Wick-based continuation pathway armed, awaiting Leg 1 / confirmation.

### NEUTRAL RESET

Interaction ended, waiting re-arm.

## 3. Required Inputs

### Levels

Active levels only:

- PMH
- PML
- LH
- LL
- ONH
- ONL
- YH
- YL

All levels must be passed as level name + price and status.

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

### OHLC Bars

The Step Engine requires completed candles for:

- Close into liquidity.
- Candle A.
- Candle B.
- Leg 2 candle.
- Phase 1 required entry candle.
- Phase 2 rolling A/B candles.
- Anchor Extreme.
- Opposite-side close invalidation.
- Wick probe and reclaim measurements.

### ATR

ATR inputs:

- 1-minute ATR(14) at entry.
- Daily ATR(14).
- Premarket range.
- Premarket ATR percentage.
- Overnight range.
- Overnight range percentage.

ATR is required for:

- Step 4 proximity filter, 5% ATR rule.
- Step 10 initial stop distance.
- Step 10 BE and TP1 management.
- Exhaustion logic later.

### Session Context

Required session context:

```text
{
   "symbol": "NQ",
   "date": "YYYY-MM-DD",
   "timezone": "America/Los_Angeles",
   "premarket_locked": True,
   "london_dst_adjusted": True/False
}
```

### Gateway Map

Gateway definition must be pre-built:

```text
"gateway": {
   "GH": {"name": "...", "price": value},
   "GL": {"name": "...", "price": value},
   "state": "OFF" or "ARMED"
}
```

Entry Engine must not compute GH/GL.

### Stack Boundaries

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

This fulfills:

- Step 0.2 stack detection.
- Step 0.3 boundaries.
- Step 0.5 output requirement.

Locked stack rule:

- Stacked liquidity is A+ only.
- Treat the entire stack as one zone.
- Close Boundary only defines the near edge of the zone.
- Extreme Boundary defines the only actionable trigger area.
- Stacked liquidity is not tradable at the Close Boundary.
- SHORT stack = price must create HH beyond the stack high / Extreme Boundary.
- LONG stack = price must create LL beyond the stack low / Extreme Boundary.
- No HH/LL beyond the stack extreme = no trade.

### Step Engine State

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

### Interaction Constraints / Flags

```text
"constraints": {
   "stack_requires_extreme_hit": True/False,
   "encroachment_active": True/False,
   "lh_promoted": True/False,
   "inactive_levels_removed": True
}
```

### Nearest Newly Relevant Liquidity

Definition: the next official liquidity level outside the current active level/stack that has not been consumed in the current interaction cycle.

```text
"next_liquidity": {
   "above": {"name": "...", "price": value},
   "below": {"name": "...", "price": value}
}
```

At all times, the system must identify the closest active liquidity level relative to current price that represents the next logical interaction target.

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

## 4. Step Engine

### Step 0 - Level Validation

0.1 Read table.

- Use active levels only.

0.2 Check for static stacks.

- If levels are within 10% ATR, treat as one stack.

0.3 Define boundaries.

- Close Boundary = closest level to price.
- Extreme Boundary = furthest level from price.
- For stacks, Close Boundary only defines the near edge of the zone.
- For stacks, Extreme Boundary defines the only actionable trigger area.
- Stacked liquidity requires extreme confirmation before any structure can begin.

0.4 Verify against chart.

- Table must match drawn levels.
- If mismatch, stop.

0.5 Output requirement.

Must define:

- Active level or stack.
- Close boundary.
- Extreme boundary.
- Nearest newly relevant liquidity.
- Whether next level is final in ladder.

0.6 Session-Built Liquidity Lock Rule.

Applies to:

- PMH
- PML
- ONH
- ONL

Before lock time:

- Levels are still developing.
- Any touch before lock is formation only.
- Formation does not count as actionable interaction, activation, or consumption.
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

### Step 1 - Gateway Rule

1.1 Define Gateway from Step 0.

Gateway:

- GH = closest meaningful liquidity above price.
- GL = closest meaningful liquidity below price.

Important rules:

- GH / GL are not fixed to PMH / PML.
- GH and GL are selected from the liquidity ladder.
- GH and GL must be defined using level names or stack names with associated prices, never raw price values.
- They can be PMH / PML, YH / YL, ONH / ONL, LH / LL.
- PMH, PML, ONH, ONL can only be used as GH/GL after they are locked.
- If price is inside a stack, treat the stack as one liquidity zone and define GH/GL outside the stack boundaries.

1.2 Gateway condition.

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

### Step 2 - Trade Mode Trigger + Rejection Mode Activation

2.1 Trigger.

- Did price close into active liquidity?
- If no, wait.
- If yes, proceed.

Active liquidity must be referenced using:

- Level name + price.
- Stack name + component levels.
- Never price alone.

Stack rule:

- If active liquidity is a stack, a close into the Close Boundary is not a tradable stack trigger.
- Close Boundary only defines the near edge of the stack zone.
- Extreme Boundary defines the only actionable trigger area.
- Upper stacked liquidity / SHORT setup requires HH beyond the highest stack price / Extreme Boundary.
- Lower stacked liquidity / LONG setup requires LL beyond the lowest stack price / Extreme Boundary.
- No Candle A may be assigned from a Close Boundary interaction inside the stack.
- No HH/LL beyond the stack extreme = no trade.

2.1A Pre-Activation Liquidity Probe Level Rule (NEW LOCKED).

2.1A Execution Notes (MANDATORY LOCKED)

State Variable

pre_activation_probe_boundary:
  active: true/false
  side: "upper" or "lower"
  source_level: level name or stack name
  boundary_price: float

Detection Logic

If:

- wick crosses active liquidity boundary
- AND candle does NOT close into liquidity
- AND Step 2 not yet activated

Then:

- set pre_activation_probe_boundary.active = true
- set boundary_price = wick extreme
- update boundary_price if a more extreme wick forms

Step 2 Override Logic

If pre_activation_probe_boundary.active = true:

- ignore original level price for activation
- use boundary_price as trigger

Activation requires:

- close beyond boundary_price

On activation:

- Candle A = that closing candle
- pre_activation_probe_boundary.active = false

Priority Rule

Pre-Activation Probe Boundary overrides:

- original level trigger (Step 2.1)
- stack close boundary trigger

Until:

- Step 2 activates OR
- any Reset condition listed below occurs

Logging Requirement

Log event:
"pre_activation_probe_detected"
Include:

- level name
- side (upper/lower)
- boundary_price
- timestamp

Log event:
"pre_activation_probe_consumed"
when Step 2 activates

Core Law (Execution Form)

If probe exists:
Activation = close beyond probe
Else:
Activation = close beyond level

2.1A Candle Source Clarification (MANDATORY LOCKED)

All probe detection and activation logic must use the SAME candle source as Step 2.

If Step 2 uses:

- 1-minute closes, probe detection must use 1-minute wick extremes
- No mixing of timeframes is allowed

Violation:

Using different timeframe for wick vs close = INVALID behavior

2.1A Same-Candle Constraint (MANDATORY LOCKED)

A single candle may NOT simultaneously:

- create a pre-activation probe
- AND activate Step 2

Rule:

If a candle wicks beyond liquidity AND closes beyond the required Step 2 activation boundary:

- This candle is treated ONLY as Step 2 activation
- No probe state is recorded

Interpretation:

Probe must exist BEFORE the activation candle

2.1A Level Association Rule (MANDATORY LOCKED)

Each pre_activation_probe_boundary must be tied to EXACTLY ONE level or stack.

If price transitions to a new nearest liquidity level:

- Existing probe MUST be discarded
- New probe detection begins for the new level

No cross-level carryover allowed

2.1A Safety Guard (MANDATORY LOCKED)

If boundary_price is not set AND pre_activation_probe_boundary.active = true:

- Block Step 2 activation
- Log error: "probe_state_invalid_missing_boundary"
- Do NOT proceed

2.1A Equality / Tick Precision Rule (MANDATORY LOCKED)

All comparisons for probe detection and activation must respect tick size.

Rules:

- "beyond boundary" requires 1 tick past the level
- equality (touching the level exactly) is NOT sufficient
- floating point comparisons must be normalized to tick precision

Examples:

upper side:
close >= boundary_price + 1 tick = valid activation
close == boundary_price = INVALID

lower side:
close <= boundary_price - 1 tick = valid activation
close == boundary_price = INVALID

2.1A Gap Handling Rule (MANDATORY LOCKED)

If price gaps beyond a level or probe boundary:

- Treat the candle that opens after the gap as the evaluation candle.
- If that candle CLOSES beyond the required boundary:
  - Step 2 activates normally
  - Candle A = that candle
- Do NOT create a probe from gap-only movement
- Probe requires an actual wick within a formed candle

2.1A Ordering Priority Rule (MANDATORY LOCKED)

Evaluation order within each candle MUST be:

1. Check for Step 2 activation
2. If not activated, check for probe detection
3. Update probe boundary if needed

This prevents:

- probe overriding a valid activation
- incorrect state transitions

Rule:

Activation always has priority over probe detection within the same candle

2.1A Debug Snapshot Requirement (MANDATORY LOCKED)

At every candle close, log:

- current active level / stack
- probe active state
- boundary_price
- whether activation condition was evaluated as true/false
- reason for pass/fail

Purpose:

Allows full reconstruction of Step 2 decisions during replay and debugging

2.1A Probe Expiration Rule (MANDATORY LOCKED)

A pre_activation_probe_boundary may NOT persist indefinitely.

Expiration Condition:

If N completed candle closes occur after the detection candle without Step 2 activation:

- pre_activation_probe_boundary.active = false
- boundary_price = null
- log: "probe_expired_timeout"

Default:

N = 5 candles (configurable)

Purpose:

Prevents stale probe levels from blocking valid future activations

2.1A Re-Entry Protection Rule (MANDATORY LOCKED)

If a probe was previously consumed (Step 2 activated and failed later):

The system must NOT reuse the same probe boundary on re-approach.

Rule:

On Step 7 termination:

- All probe state must be cleared
- New approach must form a NEW probe or clean activation

No historical probe reuse allowed

2.1A Multi-Probe Conflict Rule (MANDATORY LOCKED)

If probes form on BOTH sides (upper and lower) within the same approach sequence:

System must prioritize the side of the current active liquidity target

Rule:

- If targeting upper liquidity, ignore lower-side probe
- If targeting lower liquidity, ignore upper-side probe

No dual-boundary state allowed

2.1A Safety Halt Condition (MANDATORY LOCKED)

If conflicting states occur:

- probe active = true
- AND Step 2 activates on original level instead of probe boundary

- BLOCK activation
- log: "probe_override_violation"
- do NOT proceed

Purpose:

Prevents silent logic corruption

Once activated:

- Candle B must show valid participation.
- Leg 1 forms normally from Candle A + Candle B.
- Leg 2 follows Step 5.
- Entry follows Step 6.
- No shortcut or bypass is created.

Scope:

- Applies only to the current active liquidity level/stack and current approach sequence.
- It is not a permanent level.
- It is not added to the liquidity ladder.

Reset:

Clear the probe boundary when:

- A different level becomes Nearest Newly Relevant Liquidity.
- Step 1 Gateway recalculates after price transitions away.
- Step 7 Interaction Termination occurs.
- A valid Step 2 activation occurs and the probe is consumed into Candle A.

Core Law:

- A wick before activation does not create structure; it becomes the temporary trigger boundary required for activation.

2.2 Activation.

First candle that closes into active liquidity:

- Trade Mode = ON.
- Rejection Mode = ON.
- New interaction cycle begins.
- This candle = Candle A.

Candle A must be defined using:

- Level name + price.
- Stack name + component levels.
- Never price alone.

Mode enforcement:

- Upon activation of Rejection Mode, continuation logic is disabled.
- Bypass retest logic is disabled.
- No continuation or bypass retest evaluation may occur while Rejection Mode is active.

2.3 State rule while active.

Allowed:

- Participation tracking.
- Leg 1 / Leg 2 validation.
- Timing rules.
- Sweep logic.

Not allowed:

- Independent continuation logic.
- Breakout / trend continuation.
- Bypass retest search.
- Reuse of prior structure.

2.4 Rejection Engine initialization.

Upon activation:

- Normal Rejection Mode = ON.
- S/R Rejection Mode = OFF.
- R/S Rejection Mode = OFF.
- Controlling Mode = NONE.

During the active interaction, S/R or R/S may activate.

Activation of S/R or R/S:

- Does not override Normal Rejection Mode.
- Does not trigger entry by itself.
- Does not bypass Step 5 structure requirements.

Entry may occur only after:

- A mode becomes the Controlling Mode.
- Valid Step 5 structure is confirmed.

If multiple modes are active:

- The first mode to complete valid Step 5 structure becomes Controlling Mode.
- All other modes are immediately frozen.
- Only the Controlling Mode may proceed to Step 6.

If one mode invalidates while another remains valid:

- The interaction stays active under the remaining valid mode.

If all active modes invalidate:

- Proceed to Step 7, Interaction Termination.

System lock:

- Stacks require extreme confirmation.
- Close Boundary only defines the near edge of the zone.
- Extreme Boundary defines the only actionable trigger area.
- No Candle A or Leg 1 is allowed from a close into the Close Boundary.
- All references to liquidity in Step 2 must use level name + price or stack name + components.
- Price-only references are invalid.

2.5 Pullback Continuation Activation.

Purpose: allow S/R or R/S continuation to activate after a terminated or completed interaction.

Activation condition:

- After a prior interaction has been terminated or completed.

SHORT, S/R:

- Price previously closed below a level.
- Then closes back above that level.
- S/R Mode = ON through independent activation.

LONG, R/S:

- Price previously closed above a level.
- Then closes back below that level.
- R/S Mode = ON through independent activation.

Critical rule:

- This activation does not require Rejection Mode to be active.

State transition:

- Rejection Mode = ON.
- S/R or R/S Mode = ON.
- Treat as a new interaction cycle.

After activation:

- Must still follow Step 4, Step 5, and Step 6.
- No shortcuts.

### Step 3 - Liquidity Type

Only valid if Rejection Mode = ON.

3A Normal Level:

- Start participation immediately.
- Up to 3 candles allowed in liquidity.
- 4th candle must show participation.
- If no participation, Step 7.
- If valid, Step 4A.

3B Static Stack:

- Trade Mode already ON.
- No participation timer yet.
- Requirement: has price created HH/LL beyond the Extreme Boundary?
- If no, wait.
- If yes, start 1-2-3 rule after extreme confirmation.
- Up to 3 candles allowed after extreme confirmation.
- 4th candle must show participation.
- If no participation, Step 7.
- If valid, Step 4B.
- Upper stack / SHORT: HH must be beyond the highest stack price.
- Lower stack / LONG: LL must be beyond the lowest stack price.
- A sweep of the Extreme Boundary alone is not enough unless it creates the required HH/LL beyond the stack extreme.
- One level before + one sweep does not qualify a stack setup.
- No HH/LL beyond stack extreme = no trade.

3C Pre-Interaction Rotation Filter:

Purpose: prevent stacked logic from activating when price forms rotational structure before reaching liquidity.

Activation condition:

- Before sweeping the Extreme Boundary of a stack, price forms any of:
  - 3+ alternating candles.
  - Overlapping bodies.
  - Micro HH/LL sequence.
  - Visible consolidation cluster.

Then:

- Stack Logic remains locked to the stack zone.
- Step 3B is not downgraded into Normal Level logic.
- System must wait for clean HH/LL beyond the Extreme Boundary.

Routing rule:

- Wait for clean HH/LL beyond the Extreme Boundary.
- Do not allow Close Boundary logic to start Candle A or Leg 1.

One-liner:

- If price balances before a stack, wait for the extreme break; no HH/LL beyond stack extreme = no trade.

### Step 4 - Participation / Leg 1

Precondition:

- Rejection Mode = ON.
- Interaction = ACTIVE.

4A Normal Level Leg 1:

- Candle A must close into liquidity.
- Candle B is the Participation Candle.

4A.1 Participation Timing Window:

- After Step 2 activates and Candle A is assigned, the system may wait through Candle 2 and Candle 3 for valid opposite participation.
- Candle 4 is the final decision candle.
- If valid participation appears on Candle 2, Candle 3, or Candle 4:
  - Leg 1 = COMPLETE.
  - Proceed normally.
- If Candle 4 closes continuing in the break direction and does not meet valid wick-based participation:
  - Opposite participation = NOT PRESENT.
  - Level = GATEWAY.
  - No Leg 1.
  - No setup.
  - No trade.

Participation is valid if either condition is true:

- Close-Based Participation:
  - SHORT: Candle B does not close above Candle A high.
  - LONG: Candle B does not close below Candle A low.
- Wick-Based Participation, 34% Rule:
  - Measure full candle range high to low.
  - Measure opposing wick.
  - SHORT: upper wick.
  - LONG: lower wick.
  - Opposing wick must be at least 34% of total range.

Validation law:

- If Close-Based OR Wick-Based, valid.
- Else invalid.

If valid:

- Leg 1 COMPLETE.
- Leg 1 Extreme = most extreme price of Candle A + B.

Anchor Assignment Rule:

- Upon completion of Leg 1, assign the Anchor Extreme.
- Anchor Extreme becomes the structural invalidation boundary for the setup.
- Anchor Extreme becomes the reference for Step 5 and Step 6 protection rules.

4A.0 Mandatory Proximity Filter:

- Immediately after Leg 1, measure distance to nearest liquidity level.
- If distance <= 5% ATR:
  - HARD BYPASS.
  - Skip setup entirely.
  - Proceed to Step 7 reset.
- If distance > 5% ATR:
  - Proceed to Step 5.
- No continuation allowed without this check.

4B Static Stack Leg 1:

- Leg 1 may only begin after stack extreme confirmation.
- Upper stack / SHORT: Leg 1 requires HH beyond the stack high / Extreme Boundary.
- Lower stack / LONG: Leg 1 requires LL beyond the stack low / Extreme Boundary.
- Leg 1 cannot begin inside the stack.
- Leg 1 cannot form at the Close Boundary.
- A close into the Close Boundary is not tradable.
- No HH/LL beyond the stack extreme = no trade.

4D Participation Gate:

- No valid participation = no Leg 1 = no trade.

Core law:

- 34% wick confirms participation.
- Close rules confirm structure.

Final bank line:

- Participation shows two ways: hold by close or rejection by wick. Either completes Leg 1.

### Step 5 - Leg 2 Confirmation

Precondition:

- Rejection Mode = ON.
- Leg 1 = VALID.
- Interaction = ACTIVE.
- Anchor Extreme = ASSIGNED.

Step 5 priority order:

- Evaluate Wick Probe Override first, then Candle B Extreme Override, then Standard Leg 2 Logic.
- Highest active override always controls.
- Only one Step 5 confirmation path may be active at a time.
- No blending of logic is allowed.

5.1 Leg 2 Candle A Confirmation:

Leg 2 Candle A must confirm by satisfying the active Step 5 confirmation path.

Base rule:

- Candle A must CLOSE beyond the active Leg 1 reference.
- Candle A must also satisfy any active override requirement.

The active confirmation path must follow this priority hierarchy:

1. Wick Probe Override.
2. Candle B Extreme Override.
3. Standard Leg 2 Logic.

Only one confirmation path may be active at a time.

5.2 Standard Leg 2 Logic:

Standard Leg 2 confirms when a single candle:

- CLOSES beyond the active Leg 1 reference.
- SWEEPS the active Leg 1 extreme.

If both are satisfied:

- This candle becomes Leg 2 Candle A.

5.3 Leg 1 Definitions:

- Leg 1 reference = Candle A close by default.
- Candle B close if Candle B Reference Upgrade activates.
- Leg 1 extreme = most extreme price of Candle A + Candle B.
- These values are fixed once Leg 1 completes, except for Candle B Reference Upgrade.

5.3A Candle B Reference Upgrade:

Activation:

- Candle B trades beyond Candle A close in the active rejection direction.

SHORT:

- Candle B high > Candle A close.

LONG:

- Candle B low < Candle A close.

Effect:

- Candle B close becomes the active Leg 1 reference.
- Candle A close is replaced as the Leg 1 reference.
- Leg 1 extreme remains unchanged.

Important:

- Candle B does not need to own the extreme for this rule to activate.
- If Candle B trades beyond Candle A close but does not exceed Candle A extreme, Candle B close still becomes active reference while Candle A may still own the extreme.

5.4 Candle B Extreme Override:

Activation:

- Candle B establishes the Leg 1 extreme.

Effect:

- Standard Leg 2 logic is disabled.
- Leg 2 Candle A must confirm by CLOSE beyond Candle B extreme only.

SHORT:

- Leg 2 Candle A must CLOSE above Candle B high.

LONG:

- Leg 2 Candle A must CLOSE below Candle B low.

This close alone becomes the required structural confirmation condition for Leg 2 Candle A.

5.5 Wick Probe Override:

Activation:

After Leg 1 completion and before valid Leg 2 confirmation:

- Price WICKS beyond the active Leg 1 extreme.
- Price does NOT close beyond the active Leg 1 reference.

Effect:

- Leg 2 is not valid yet.
- Wick Probe becomes active.

Probe Threshold:

- SHORT: Highest wick beyond Leg 1 extreme = Probe High.
- LONG: Lowest wick beyond Leg 1 extreme = Probe Low.

Leg 2 Candle A must now confirm by:

- CLOSE beyond the active Leg 1 reference.
- CLOSE beyond the active Probe Threshold.

Probe Update Rule:

- Additional LONG probes use the lowest Probe Low.
- Additional SHORT probes use the highest Probe High.

All prior Leg 2 logic is suspended while Wick Probe is active.

5.6 Dynamic Stack Routing:

If dynamic stacking becomes active after Leg 1:

Leg 2 Candle A must confirm using:

- Active confirmation path.
- Sweep of the next liquidity Extreme Boundary.

If Extreme Boundary is not swept:

- Leg 2 = INVALID.

5.7 Post-Confirmation Participation Window:

Once Leg 2 Candle A confirms:

- Leg 2 is structurally confirmed.
- A 4-candle participation window begins immediately.

Define:

- Candle 1 = first candle after Leg 2 Candle A.
- Candle 2 = second candle after Leg 2 Candle A.
- Candle 3 = third candle after Leg 2 Candle A.
- Candle 4 = REQUIRED PARTICIPATION CANDLE.

Candles 1-3 may do anything structurally as long as global invalidation rules are not violated.

Candle 4 must show valid participation.

If Candle 4 shows valid participation:

- Leg 2 = VALIDATED.
- 2-Leg Structure = COMPLETE.
- Proceed to Step 6.

If Candle 4 does not show valid participation:

- Leg 2 = INVALID.
- Structure = INVALID.
- Interaction = CONSUMED / FAILED.
- Proceed to Step 7.

5.8 Participation Definition:

Participation means the opposite side responds to Leg 2 Candle A.

SHORT:

- After an upside Leg 2 Candle A, Candle 4 must show bearish / seller participation.

LONG:

- After a downside Leg 2 Candle A, Candle 4 must show bullish / buyer participation.

Implementation should use existing Step 4 participation concepts where possible.

Valid participation may include:

- Opposite-colored close.
- Rejection behavior.
- Valid interaction behavior already recognized by the engine.

Do not require LH / HL here.
Do not require entry here.
Do not start Step 6 retry logic here.

Step 5 participation is only a validation gate.

5.9 Post-Confirmation Proximity Filter:

After Leg 2 Candle A confirms and before proceeding to Step 6:

Measure distance from Leg 2 Candle A close to nearest opposing liquidity level.

If distance <= 2.5% ATR:

- Leg 2 = DISQUALIFIED.
- Structure = INVALID.
- Proceed to Step 7.

If distance > 2.5% ATR:

- Structure remains valid.
- Continue Step 5 participation window.

Leg 2 must confirm with sufficient clearance from next liquidity.

5.10 Anchor Extreme Invalidation:

Anchor Extreme:

- SHORT: Anchor Extreme = HIGH of final bullish displacement.
- LONG: Anchor Extreme = LOW of final bearish displacement.

Rule:

- Once Anchor Extreme is established, price must not close beyond that extreme on the opposite side before Step 6 entry completes.
- If violated:
  - Structure = INVALID.
  - Rejection Mode = OFF.
  - Proceed to Step 7.

- Wicks beyond Anchor Extreme are allowed.
- Only closes invalidate structure.

5.11 Failed Leg 2 Resolution:

If price sweeps active Leg 1 extreme but does not close beyond active Leg 1 reference:

- Leg 2 = INVALID.

If after failed Leg 2 attempt, price closes back through liquidity in the opposite direction of the rejection attempt:

- Rejection Mode = OFF.
- Current rejection sequence = TERMINATED.
- Proceed to Step 7.
- Step 9 may become eligible if activation conditions are met.

5.12 Active Reference Rule:

- Step 5 must use only one active structural reference.
- Candle A close by default.
- Candle B close if Candle B Reference Upgrade activates.
- The active Leg 1 reference may not be redefined, blended, or replaced after Leg 1 completes.
- Leg 1 extreme remains separate from Leg 1 reference.

5.13 Anchor Stability Rule:

- Once assigned, Anchor Extreme may not be changed, updated, or reassigned within the same interaction.
- All validation, invalidation, and entry protection must reference original Anchor Extreme only.
- No recalculation or reinterpretation allowed.

Step 5 to Step 6 Handoff:

Step 5 hands off to Step 6 only when:

1. Leg 2 Candle A confirms under active confirmation path.
2. Proximity filter passes.
3. Candle 4 participation requirement passes.
4. Anchor Extreme remains intact.
5. No global invalidation fires.

Then:

- Leg 2 = VALIDATED.
- 2-Leg Structure = COMPLETE.
- Step 6 = ACTIVE.

Core law:

- Leg 2 Candle A confirms structure.
- Candle 4 confirms participation.
- Step 6 handles entry.
- No valid Candle A = no structure.
- No Candle 4 participation = no trade.
- No confirmation = reset.

### Step 6 - Entry Types

First valid trigger wins.

6.1 Opposing Setup Override:

If a valid opposing rejection setup forms before the current setup completes, original setup is immediately invalidated.

Condition:

- During active rejection sequence, opposing S/R or R/S setup completes Leg 1 and begins to resolve price in opposite direction.

Then:

- Original setup is invalidated.
- All Leg 1 / Leg 2 structures tied to original setup are discarded.
- System immediately abandons original setup.
- Control transfers to opposing setup.
- Opposing setup becomes only valid pathway.

Core law:

- Only one directional premise may remain valid within an interaction.

6.2 Phase 1, Initial Entry Window:

After Leg 2 Candle A confirms:

- Candle 1 = first candle after Leg 2 Candle A.
- Candle 2 = second candle.
- Candle 3 = third candle.
- Candle 4 = REQUIRED ENTRY CANDLE.

Rule:

- A valid Step 6 entry MUST trigger on Candle 4.
- No early entry before Candle 4.
- No late entry after Candle 4.

If entry triggers on Candle 4:

- ENTRY CONFIRMED.
- Execute immediately.
- Interaction = CONSUMED.

If no entry triggers on Candle 4:

- Entry = FAILED.
- Check for failed-entry / opposite-participation.
- If valid failed-entry participation exists, transition to Phase 2.
- If not, Structure = INVALID and proceed to Step 7.

6.3 Phase 2, Rolling A/B Re-Entry Window:

Activation:

- Phase 1 failed.
- A failed-entry / opposite-participation candle exists.

From the failed-entry candle, start a fixed 4-candle window:

- Candle 1.
- Candle 2.
- Candle 3.
- Candle 4 = FINAL ENTRY CANDLE.

Within Candles 1-4, A/B structure is rolling and dynamic.

A Candle definition:

- SHORT: any candle that makes a new higher high inside the window becomes active A.
- LONG: any candle that makes a new lower low inside the window becomes active A.
- Each new A replaces the prior A.

B Candle definition:

- The next qualifying candle that triggers a valid Step 6 entry model against the active A.
- B must occur within the fixed 4-candle window.

Valid sequences include:

- Candle 1 = A, Candle 2 = B.
- Candle 2 = A, Candle 3 = B.
- Candle 3 = A, Candle 4 = B.
- Any valid A/B combination inside the 4-candle window.

Final constraint:

- Candle 4 must complete as a valid B entry candle if no prior B triggered.
- Candle 4 cannot be only A.
- If no valid B entry occurs by Candle 4:
  - Structure = INVALID.
  - Interaction = CONSUMED.
  - Proceed to Step 7.

Only one Phase 2 cycle is allowed.
No third attempt.
No re-arming.
No late entries.

6.4 Entry Models, Active Anchor Classification:

Before evaluating an entry candle, classify all allowed entry models for the active anchor.

Active anchor law:

- Phase 1: active anchor = Leg 2 Candle A.
- Phase 2: active anchor = rolling A, the most recent valid new extreme inside the fixed 4-candle window.
- Only current active anchor is valid.
- Prior anchors are not reused, blended, or referenced after replacement.

Step 1, Wick Classification:

- Measure active anchor wick as percentage of total active anchor range.
- If active anchor wick >= 20%:
  - Sweep Entry = Large Wick path.
  - Double Wick = ACTIVE.
- If active anchor wick < 20%:
  - Sweep Entry = Small Wick path.
  - Double Wick = ELIMINATED.

Step 2, Active Model Output:

Must state:

- Sweep Entry path = Large Wick or Small Wick.
- Double Wick = ACTIVE or ELIMINATED.

Reset rule:

- Whenever Phase 2 rolling A updates, all prior model eligibility is discarded.
- Full decision pass recomputed from scratch using new active anchor only.

Enforcement:

- No entry evaluation may occur until active-anchor decision pass output is explicitly defined.

6.5 Required Leg-In Liquidity Sweep Gate, S/R and R/S only:

Applies only to:

- S/R continuation setups.
- R/S continuation setups.

Does not apply to:

- Standard rejection setups.
- Any non S/R / R/S pathway.

Required leg-in liquidity exists only when:

- Controlling Mode = S/R or R/S.
- The same leg that qualified the setup, wick or close beyond level, also created internal liquidity before reaching the level.

S/R, SHORT:

- If the leg that wicked into LL or closed below LL also created a Higher High before reaching LL, that HH = required liquidity.

R/S, LONG:

- If the leg that wicked into LH or closed above LH also created a Lower Low before reaching LH, that LL = required liquidity.

Rule:

- If controlling_mode is S/R or R/S and required leg-in liquidity exists, entry evaluation is blocked until that liquidity is swept.

If not swept:

- Step 6 = WAIT.
- Interaction = ACTIVE.
- Structure = VALID.
- Phase timing continues.
- No entry model may trigger.

If swept:

- Continue to active Phase 1 or Phase 2 entry evaluation.

Failure:

- If Phase 1 or Phase 2 timing expires before sweep, Entry Failure and proceed to Step 7.

Important:

- This rule only gates Step 6.
- It does not invalidate Step 4 or Step 5.
- It does not reset interaction.
- This rule is active only when controlling_mode = S/R or R/S.
- Otherwise, ignore completely.

Entry Model 1, Sweep Entry:

Large Wick Sweep:

- Condition: SC wick >= 20% total SC range.
- SHORT wick = SC high to SC body high.
- LONG wick = SC body low to SC low.
- Reclaim measured across wick only.

Requirements:

- Entry candle sweeps SC extreme by at least 1 tick.
- Reclaims at least 60% of SC wick range.
- Reclaim level exceeded by at least 1 tick.
- Only first valid reclaim after sweep may trigger entry.

SHORT trigger:

- Wick Range = SC high to SC body high.
- 60% level = 60% of wick measured down from SC high.
- Price trades back below 60% reclaim level by at least 1 tick.

LONG trigger:

- Wick Range = SC body low to SC low.
- 60% level = 60% of wick measured up from SC low.
- Price trades back above 60% reclaim level by at least 1 tick.

Execution:

- Intrabar valid.
- No close required.
- First valid touch through reclaim level = trigger.

Invalidation:

- If sweep occurs but reclaim does not reach required wick level cleanly, no Large Wick Sweep entry exists.
- Repeated reclaim attempts on same SC are invalid.

Small Wick Sweep:

- Condition: SC wick < 20% total SC range.

Requirements:

- Sweep SC extreme by at least 1 tick.
- Reclaim SC body level by at least 1 tick.
- Occurs within the active Phase 1 or Phase 2 timing window.
- Only first valid reclaim after sweep may trigger entry.

SC body:

- BODY LOW = lowest open/close.
- BODY HIGH = highest open/close.

LONG:

- Sweep below SC low.
- Trigger when price trades above BODY LOW by at least 1 tick.

SHORT:

- Sweep above SC high.
- Trigger when price trades below BODY HIGH by at least 1 tick.

Execution:

- Intrabar valid.
- No close required.
- First valid touch through body reclaim level = trigger.

Invalidation:

- If sweep occurs but reclaim does not exceed body level by at least 1 tick, no Small Wick Sweep entry exists.
- Repeated reclaim attempts on same SC are invalid.

Entry Model 2, Double Wick Rejection:

- SC = candle immediately before entry.
- SC wick >= 20% of total SC range.
- Entry penetrates at least 50% of SC wick.
- Entry reclaims.

SHORT:

- Penetrate above.
- Reclaim below.

LONG:

- Penetrate below.
- Reclaim above.

Execution:

- Intrabar valid.
- No close required.

6.6 Model Enforcement:

- Uses SC Decision Pass output.
- No independent classification occurs.
- Per current SC only.
- Elimination logic applied fresh using active SC.
- Sweep Entry always remains if conditions possible.
- When SC updates, all elimination logic is cleared and recomputed.
- If 2 models eliminated, remaining model is active.

6.7 Entry Confirmation + Routing:

If any model triggers:

- ENTRY CONFIRMED.
- EXECUTE IMMEDIATELY.
- Interaction = CONSUMED.

State changes:

- Rejection Mode = OFF.
- Trade Mode = OFF.
- Structure = LOCKED.

Structure lock:

- No changes to Leg 1, Leg 2, or SC.

Single Entry Rule:

- Only one entry allowed.

System transition:

- ACTIVE TRADE STATE.
- Proceed to Step 10.

Post entry:

- No new evaluation.
- No continuation.
- No new interactions.

After trade resolution:

- NEUTRAL.

Core law:

- Entry consumes interaction.

6.7a Entry Time Priority:

- All active entry models must be evaluated simultaneously.
- Execute first model that becomes valid in time.
- No later-valid model may override or delay earlier-valid trigger.
- If multiple models qualify within same candle, earliest intrabar trigger takes precedence.

6.8 Invalidation:

Structure invalid if:

- Phase 1 fails and no valid Phase 2 activation exists.
- Phase 2 activates but no valid B entry occurs by Candle 4.
- Required leg-in liquidity gate blocks entry until timing expires.
- Sweep occurs without reclaim.
- Anchor Extreme is violated.
- Opposing setup override invalidates original setup.

Then proceed to Step 7.

6.9 Global Invalidation:

- No trigger.
- Timing fails.
- Structure breaks.
- No trade.

6.10 Anchor Extreme Invalidation:

- If price closes beyond Anchor Extreme before entry is triggered:
  - Structure = INVALID.
  - Proceed to Step 7.
- Closes within liquidity or Leg 1 structure do not count as failure.
- Only Anchor Extreme violation defines true opposite-side failure.

6.11 System Truth:

- Step 4 = Participation.
- Step 5 = Structure Confirmation.
- Step 6 = Entry.

6.12 Entry Anchor Law:

- Phase 1 active anchor = Leg 2 Candle A.
- Phase 2 active anchor = rolling A, the most recent valid new extreme inside the fixed 4-candle window.
- Only current active anchor is valid.
- Prior anchors are not reused, blended, or referenced after replacement.

6.13 Rejection Completion:

- Rejection sequence Steps 3-6 must fully complete for a trade to be valid.
- If any part fails, becomes invalid, or does not produce valid entry:
  - Rejection attempt is FAILED.
  - No trade may be taken from that interaction.
  - Interaction is complete or terminated per global rules.

Final bank line:

- Phase 1 must resolve on Candle 4.
- If Phase 1 fails, the market gets one structured rolling A/B retry.
- Phase 2 must resolve by Candle 4.
- Structure is fixed.
- Timing is strict.
- Anchor can roll only inside Phase 2.
- Entry is immediate when valid.
- No valid entry by deadline = no trade.

6.11 Leg 2 Re-Attempt Model, BE-Based:

Activation requires all:

- Trade was executed from Step 6.
- Trade reached Break Even.
- Structure has not been invalidated.
- No opposite-side close has occurred.
- Interaction is still active.
- Step 7 has not triggered.
- Rule 4A.0 does not apply here.

Transformation:

- Once BE is triggered, New Leg 1 close = original entry price.
- New Leg 1 extreme = original entry extreme used for stop.
- No new participation is created.
- No new Step 4 is evaluated.

New Leg 2 requirement:

- Sweep new Leg 1 extreme.
- Close beyond new Leg 1 close.

Entry:

- Same locked Step 6 two-phase timing rules apply unless explicitly superseded here.
- The prior "SC progression active" wording conflicts with the locked two-phase model and is superseded by Phase 1 / Phase 2 timing.

Timing:

- Must complete within 3 candles from BE trigger.
- If not, invalid and proceed to Step 7.

Hard limits:

- Maximum one re-attempt per interaction.
- If re-attempt fails, interaction is complete.
- Cannot occur if full stop was hit, structure breaks, or opposite-side close occurs.

Risk:

- Treated as new trade.
- Must respect 10% max risk.
- No overlapping exposure allowed.

Core law:

- If the market defends your entry at BE, it may offer a cleaner Leg 2, but it must confirm structure again.

### Step 7 - Interaction Termination

Trigger if any:

- Participation fails.
- Structure fails.
- Timing fails.
- Sweep fails.
- Opposite-side close occurs.

On termination:

- Rejection Mode OFF.
- Trade Mode OFF.
- Delete all structure.
- Delete Leg 1.
- Delete Leg 2.
- Delete timing.
- Delete sweep logic.
- System State = NEUTRAL RESET.

Rule:

- Once dead, cannot reuse.

Mode Transition Rule:

- Rejection Mode = OFF.
- System State = NEUTRAL RESET.
- No continuation or bypass retest state is carried forward.
- New setup requires fresh valid liquidity interaction.

Global interaction termination:

- If price exits active liquidity zone without initiating or progressing valid structural development, interaction is dead/invalid.
- Immediately terminate current 0-6 cycle.
- Reset system state.
- Return to Step 1 Gateway Rule.

Exit definition:

- Price closes outside active liquidity zone and no valid participation or structural development has occurred.
- OR structure has clearly failed or been invalidated.

Structural Exit Exception:

- If price exits liquidity zone after valid participation has occurred, movement may represent Leg 1 or ongoing structural development, and interaction remains active.

Termination conditions before structure completion:

- Price leaves liquidity zone without required sweep for stack.
- No participation within allowed candle window.
- Structure begins but fails and price exits zone.
- Clean continuation away from level without forming structure.
- Opposite-side break before setup completes.

After termination:

- Current interaction discarded completely.
- No structure carries forward.
- No bias retained.
- Return to neutral evaluation state.
- Return to Step 1.
- Re-evaluate current location.
- Wait for next valid close into liquidity.
- Begin new 0-6 cycle.

Key principle:

- Each liquidity interaction is independent.
- If it does not complete required behavior, it is void and has no impact on future setups.

### Step 8 - Rejection Mode Re-Activation

8.1 New Liquidity:

- Close into new level.
- Rejection Mode ON.

8.2 Same Liquidity Re-Entry:

Same-liquidity rejection may reactivate only if price closes beyond the most extreme close printed during the immediately prior terminated interaction at that same liquidity.

- LONG: above that interaction's highest close.
- SHORT: below that interaction's lowest close.
- Else: no re-activation.

8.3 System Routing:

If same-liquidity re-entry qualifies:

- Rejection Mode = ON.
- Treat as new interaction.
- Proceed to Step 3.
- Start fresh Step 4 participation / Leg 1 evaluation.
- Prior structure may not be reused.

### Step 9

The raw blueprint references Step 9 eligibility in Step 5.6A, but does not define Step 9 in the provided text.

### Step 10 - Trade Management

10.1 Risk Model:

- Maximum risk per trade = 10%.
- ATR source = 1-minute ATR(14) at moment of entry.
- Stop distance = greater of 1-minute ATR(14) or distance required to clear structure extreme by at least 2 ticks.
- Long stop below structure extreme + 2 ticks.
- Short stop above structure extreme + 2 ticks.
- If stop > ATR, reduce position size.
- Total trade risk must remain <= 10%.
- Stop is defined at entry.
- No discretionary widening after entry.

10.2 Order Placement:

- Immediately upon entry, place bracket order.
- Initial stop loss from 10.1.
- Primary target = +1 ATR from entry.
- Orders must function as one unified management set.

10.3 Early Protection:

Move stop to BE when first of:

- Price reaches +0.5 ATR intrabar.
- 3 candles pass after entry.

BE = entry price.

10.4 Break Even:

- BE is intermediate state, not final outcome.
- Trade remains active after BE.
- Trade continues toward TP1 or stop.

10.5 Primary Target:

- At +1 ATR from entry, close 50% position.
- Remaining 50% becomes Runner.
- After TP1, move stop on remaining 50% from BE back to original ATR-based stop.
- 50% locked at +1 ATR.
- Remaining 50% has full ATR room.
- Net trade risk = neutral.

10.6 Runner:

- Remaining 50% = Runner.
- Runner remains open until stop is hit or 12:00 PM hard cutoff.
- No trailing stop.
- No discretionary adjustment.
- No additional targets.

10.7 Time-Based Exit:

At 12:00 PM:

- Close all open positions immediately.
- Cancel all working orders.
- No new trades allowed.

10.8 Management Priority:

If multiple events occur within same candle:

- BE trigger.
- TP1 fill +1 ATR.
- Stop execution.

10.9 Trade Completion Outcomes:

- Full Stop: initial stop hit before BE or TP1.
- Break Even: BE triggered and price returns to entry.
- Partial + Runner: 50% taken at +1 ATR, remaining 50% managed until stop or time exit.
- Time Exit: runner still open at 12:00 PM, position closed at cutoff.

10.10 Mandatory Session Close:

- No positions held past session.
- No swing holds.
- No overnight exposure.
- No exceptions.

10.11 State Freeze / Evidence:

System may record only confirmed events:

- Level touched.
- Order triggered.
- Target filled.
- Stop filled.
- Time cutoff reached.

Not allowed:

- Assuming future candle path.
- Assuming continuation.
- Assuming stop/target hit without confirmation.
- Projecting outcome.

Core law:

- Once a new state is reached, stop evaluation until next event is visibly confirmed.

Step 10 summary:

- Risk = 10% max.
- Stop = max(ATR, structure + 2 ticks).
- BE = first of +0.5 ATR or 3 candles.
- TP1 = +1 ATR, take 50%.
- After TP1, stop returns to original ATR stop.
- Runner = stop or 12:00 PM.
- 12:00 PM = flat, done.

## 5. Rejection Engine

Purpose:

- Allow multiple rejection pathways to be evaluated within a single liquidity interaction while preserving failure-driven logic and one-entry-per-interaction rule.

Core structure:

- Global System State controls overall behavior: OFF, ARMED, REJECTION MODE ON, NEUTRAL RESET.
- Rejection Engine Layer tracks Normal Rejection Mode, S/R Rejection Mode, and R/S Rejection Mode.
- These are parallel pathways, not separate systems.

Normal Rejection Mode:

- Activated through Step 2.
- Close into liquidity.
- Standard Steps 3-6 flow.

Core truth:

- Rejection is a process, not a direction.
- Attempt -> Failure -> Pullback -> Continuation.
- Rejection Mode = failure-driven transition model.
- Includes normal rejection attempts and pullback continuation pathways S/R and R/S.

While active:

- Allowed: participation, Leg 1 / Leg 2, pullback structure.
- Not allowed: independent breakout trading, bypass logic.

Completion:

- Trade completes or fails.
- Reset system.

Final system truth:

- Level tests control.
- Failure defines direction.
- Pullback creates opportunity.
- Continuation executes the trade.

Final one-liner:

- Test -> Fail -> Pullback -> Continue.

### S/R Rejection Mode

SHORT - Pullback continuation from failed LONG.

Purpose:

- Convert failed LONG attempt at support into SHORT pullback continuation.
- Not a reversal model.
- Failure occurs at level.
- Structure forms above level.
- Entry occurs on pullback away from level.

Preconditions:

- Rejection Mode = ON.
- Interaction = ACTIVE.
- Active liquidity defined.
- Step 2 completed.

Primary Activation:

- Price expands down into liquidity.
- Sweeps Extreme Boundary by at least 1 tick.
- Price closes back above the level.
- S/R Mode = ON only after close above level.

Secondary Wick-Based Provisional Activation:

- After price has closed below level, a green candle wicks back into or above level but does not close back above level.
- That candle may become Provisional Candle A.

Requirements:

- Candle must be green.
- Wick must trade into or through level.
- Candle must occur after below-level failure sequence is active.

State:

- S/R Mode = PROVISIONAL.
- Provisional Candle A = wick candle.

Timing:

- No structural evaluation before close-based activation or wick-based provisional activation.

Structure:

- Must form on pullback above level.
- All structure must remain above level.
- No structure below is valid.

First Opportunity Law:

- Only first structure is valid.
- If structure fails or invalidation occurs, pathway permanently closed.

Leg 1:

- Close-based path: Leg 1 forms normally from Candle A + Candle B using standard participation rules.
- Wick-based provisional path: Provisional Candle A is wick-back-into-level candle; next valid opposite participation candle may complete Leg 1 even if price has not closed above level.
- Candle B must show valid seller participation.
- Candle B close must remain above level.
- If valid, Leg 1 = COMPLETE and S/R Mode = ACTIVE.

Leg 2:

- Standard path: if price already closed above level, use standard S/R continuation rules.
- Override path: if Leg 1 formed from wick-based provisional path and no candle has closed above level, Leg 2 must close above highest active wick threshold.
- Highest active wick threshold = highest wick of Provisional Candle A, or highest wick of Candle B if Candle B extends extreme, or highest wick probe formed after Leg 1 completion and before Leg 2 confirmation.
- Both Leg closes must remain above level unless Override Path active.
- When Override Path active, Leg 2 close above highest wick threshold is required confirmation condition.

Entry:

- Entry via Step 6 from structure above level.
- SHORT continuation from pullback.
- Valid Leg 2 does not automatically trigger entry.
- Step 6 trigger must still qualify.

Approved Step 6 triggers:

- Sweep entry.
- Wick reclaim.
- Body reclaim.
- Other approved Step 6 trigger.

Not approved:

- Double wick hesitation.
- No clear sweep/reclaim trigger.
- Ambiguous trigger pattern.

If no valid trigger appears:

- No trade.

Invalidation:

- If price closes below Anchor Extreme, S/R invalid, Mode OFF, pathway terminated.
- Closes only; wicks ignored for invalidation.
- No re-attempt.
- No reinterpretation.

Direction:

- SHORT continuation only.

### R/S Rejection Mode

LONG - Pullback continuation from failed SHORT.

Purpose:

- Convert failed SHORT attempt at resistance into LONG pullback continuation.
- Not a reversal model.
- Failure occurs at level.
- Structure forms below level.
- Entry occurs on pullback away from level.

Preconditions:

- Rejection Mode = ON.
- Interaction = ACTIVE.
- Active liquidity defined.
- Step 2 completed.

Primary Activation:

- Price expands up into liquidity.
- Sweeps Extreme Boundary by at least 1 tick.
- Price closes back below level.
- R/S Mode = ON only after close below level.

Secondary Wick-Based Provisional Activation:

- After price has closed above level, a red candle wicks back into or below level but does not close back below level.
- That candle may become Provisional Candle A.

Requirements:

- Candle must be red.
- Wick must trade into or through level.
- Candle must occur after above-level failure sequence is active.

State:

- R/S Mode = PROVISIONAL.
- Provisional Candle A = wick candle.

Timing:

- No structural evaluation before close-based activation or wick-based provisional activation.

Structure:

- Must form on pullback below level.
- All structure must remain below level.
- No structure above is valid.

First Opportunity Law:

- Single attempt only.

Leg 1:

- Close-based path: Leg 1 forms normally from Candle A + Candle B using standard participation rules.
- Wick-based provisional path: Provisional Candle A is wick-back-into-level candle; next valid opposite participation candle may complete Leg 1 even if price has not closed below level.
- Candle B must show valid buyer participation.
- Candle B close must remain below level.
- If valid, Leg 1 = COMPLETE and R/S Mode = ACTIVE.

Leg 2:

- Standard path: if price already closed below level, use standard R/S continuation rules.
- Override path: if Leg 1 formed from wick-based provisional path and no candle has closed below level, Leg 2 must close below lowest active wick threshold.
- Lowest active wick threshold = lowest wick of Provisional Candle A, or lowest wick of Candle B if Candle B extends extreme, or lowest wick probe formed after Leg 1 completion and before Leg 2 confirmation.
- Both Leg closes must remain below level unless Override Path active.
- When Override Path active, Leg 2 close below lowest wick threshold is required confirmation condition.

Entry:

- Entry via Step 6 from structure below level.
- LONG continuation from pullback.
- Valid Leg 2 does not automatically trigger entry.
- Step 6 trigger must still qualify.

Approved Step 6 triggers:

- Sweep entry.
- Wick reclaim.
- Body reclaim.
- Other approved Step 6 trigger.

Not approved:

- Double wick hesitation.
- No clear sweep/reclaim trigger.
- Ambiguous trigger pattern.

If no valid trigger appears:

- No trade.

Invalidation:

- If price closes above Anchor Extreme, R/S invalid, Mode OFF.

Direction:

- LONG continuation only.

### Key Structural Definitions

Anchor Extreme:

- Final displacement push into liquidity.
- Defines true structural boundary.
- SHORT, S/R: high of displacement.
- LONG, R/S: low of displacement.

Close vs Wick Rule:

- Wicks may violate.
- Only closes define structure.

Directional Control Law:

- Only one directional premise valid.
- Opposing structure = immediate override.

Global Routing Rule - Rejection Only:

- After price closes into active liquidity, system activates Rejection Mode only.
- Rejection Mode = ON.
- System must resolve interaction through rejection logic only.
- If rejection fails, invalidates, or terminates without valid rejection completion:
  - Rejection Mode = OFF.
  - System State = NEUTRAL RESET.
  - No bypass setup may be evaluated.

## 6. Leg-1 Engine

Leg 1 is built in Step 4.

Inputs:

- Rejection Mode = ON.
- Interaction = ACTIVE.
- Candle A closed into liquidity.
- Candle B participation candle.

Outputs:

- Leg 1 status.
- Leg 1 close = Candle A close.
- Leg 1 extreme = most extreme price of Candle A + B.
- Anchor Extreme assignment.
- Proximity filter pass/fail.

Rules:

- Participation valid through Close-Based or Wick-Based 34% rule.
- Static Stack Leg 1 is valid only after HH/LL beyond the stack Extreme Boundary.
- Static Stack Close Boundary interaction is not enough to form Candle A or Leg 1.
- No valid participation = no Leg 1 = no trade.
- Immediately after Leg 1, distance to nearest liquidity must be greater than 5% ATR or hard bypass.

## 7. Leg-2 Engine

Leg 2 is built in Step 5.

Inputs:

- Rejection Mode = ON.
- Leg 1 valid.
- Interaction active.
- Leg 1 close.
- Leg 1 extreme.
- Active override state.
- Anchor Extreme.

Priority:

- Wick Probe Override first.
- Candle B Extreme Override next.
- Standard Leg 2 Logic last.

Outputs:

- Leg 2 Candle A = CONFIRMED, then Step 5 participation window.
- 2-Leg Structure = COMPLETE only after Candle 4 participation validates.
- Or Structure = INVALID and Step 7.

Rules:

- Only one Step 5 confirmation path may be active at a time.
- Leg 2 always confirms beyond Leg 1.
- Active references may not be blended.
- Anchor Extreme may not be changed after assignment.

## 8. Entry Models

Entry Models are evaluated in Step 6 after Step 5 confirms structure.

SC Decision Pass must occur before entry evaluation.

Active model output must state:

- Sweep Entry path = Large Wick or Small Wick.
- Double Wick = ACTIVE or ELIMINATED.

Models named in the raw blueprint:

- Sweep Entry.
- Large Wick Sweep.
- Small Wick Sweep.
- Double Wick Rejection.

Rules:

- First valid trigger wins.
- Entry may be intrabar.
- No close required for listed sweep/reclaim triggers.
- Phase 1 must resolve on Candle 4.
- Phase 2 is the only retry and uses the fixed rolling A/B window.
- Each active anchor recomputes model eligibility from scratch.
- No evaluation before active-anchor Decision Pass output exists.
- If no valid entry by the active phase deadline, structure invalid.

## 9. Trade Management

Trade Management is Step 10.

Rules:

- Maximum risk per trade = 10%.
- Stop = greater of 1-minute ATR(14) or structure extreme clearance by at least 2 ticks.
- Long stop below structure extreme + 2 ticks.
- Short stop above structure extreme + 2 ticks.
- If stop > ATR, reduce position size.
- Stop defined at entry.
- No discretionary widening.
- Immediately place bracket order.
- Initial stop loss.
- Primary target = +1 ATR.
- BE when first of +0.5 ATR intrabar or 3 candles after entry.
- TP1 at +1 ATR closes 50%.
- Remaining 50% becomes Runner.
- After TP1, runner stop moves from BE back to original ATR-based stop.
- Runner exits on stop or 12:00 PM hard cutoff.
- No trailing stop.
- No discretionary adjustment.
- No additional targets.
- At 12:00 PM, close all positions, cancel all working orders, no new trades.
- No positions held past session.
- No swing holds.
- No overnight exposure.
- Record only confirmed events.

## 10. State Variables Needed In Code

### Global / Session

- system_state
- trade_mode
- rejection_mode
- interaction_state
- premarket_locked
- london_dst_adjusted
- symbol
- date
- timezone

### Levels / Context

- levels
- level status
- active level
- active stack
- close boundary
- extreme boundary
- nearest newly relevant liquidity
- next level final in ladder
- gateway GH
- gateway GL
- gateway state
- high_side context
- low_side context
- stack type
- target_name
- next_outside
- encroachment_line

### Rejection Modes

- normal_rejection_mode
- sr_rejection_mode
- rs_rejection_mode
- controlling_mode
- provisional_state
- provisional_candle_a
- active_liquidity
- interaction_cycle_id
- consumed levels
- inactive levels

### Step 3

- liquidity_type
- participation_timer
- sweep_extreme_boundary_seen
- rotation_filter_active
- stack_logic_valid

### Leg 1

- candle_a
- candle_b
- leg1_status
- leg1_close
- leg1_extreme
- leg1_extreme_owner
- anchor_extreme
- proximity_distance
- proximity_atr_threshold

### Leg 2

- leg2_status
- leg2_candle
- active_step5_path
- wick_probe_active
- probe_high
- probe_low
- dynamic_stack_active
- step5_confirmed

### Entry

- phase1_anchor
- phase1_candle_count
- phase2_active
- phase2_candle_count
- phase2_active_a
- phase2_active_a_candle_number
- sc_decision_pass_output
- sweep_entry_path
- double_wick_state
- entry_triggered
- entry_model_triggered
- entry_price
- entry_time
- structure_locked

### Trade Management

- atr_1m_14_at_entry
- daily_atr_14
- stop_distance
- initial_stop
- structure_extreme_stop_reference
- position_size
- risk_percent
- primary_target
- be_trigger
- be_state
- tp1_state
- runner_state
- runner_stop
- time_cutoff
- management_event_state

## 11. Functions / Modules To Build

### Pre-Market Engine

- Build session_context.
- Build finalized levels with price and status.
- Detect static stacks within 10% ATR.
- Define close_boundary and extreme_boundary.
- Verify table levels against chart/drawn levels.
- Apply session-built liquidity lock rule.
- Build high_side and low_side contexts.
- Build gateway GH/GL.
- Build step_engine initial state.
- Build ATR and range context.
- Build interaction constraints.
- Build next_liquidity.
- Output premarket_context object.

### Entry Engine

- Read premarket_context only.
- Evaluate Step 1 Gateway state.
- Detect Step 2 close into active liquidity.
- Initialize Rejection Mode.
- Initialize Normal, S/R, and R/S mode states.
- Enforce rejection-only routing.
- Evaluate pullback continuation independent activation.
- Classify liquidity type Step 3.
- Enforce pre-interaction rotation filter.
- Track participation windows.
- Build Leg 1.
- Assign Anchor Extreme.
- Apply Step 4 proximity filter.
- Confirm Leg 2 by Step 5 priority order.
- Track Wick Probe overrides.
- Apply Dynamic Stack Routing.
- Apply Anchor Extreme invalidation.
- Apply opposing setup override.
- Run Phase 1 Candle 4 timing.
- Run Phase 2 rolling A/B timing when activated.
- Run active-anchor Decision Pass.
- Evaluate entry models simultaneously.
- Enforce first valid trigger wins.
- Lock structure on entry.
- Terminate/reset interaction on failure.
- Support same-liquidity re-entry rule.
- Maintain nearest newly relevant liquidity.

### Trade Manager

- Calculate max 10% risk sizing.
- Use 1-minute ATR(14) at entry.
- Set initial stop using max ATR or structure extreme + 2 ticks.
- Place bracket order immediately.
- Move stop to BE on first of +0.5 ATR or 3 candles.
- Close 50% at +1 ATR.
- Move runner stop from BE back to original ATR stop after TP1.
- Close runner on stop or 12:00 PM cutoff.
- Cancel orders at cutoff.
- Record confirmed events only.

## 12. Open Questions / Ambiguities

The following are present in the raw blueprint text and need clarification before implementation:

- Step 9 is referenced in Step 5.6A as potentially eligible, but Step 9 is not defined in the provided raw text.
- Step 10.8 lists simultaneous events in priority context: BE trigger, TP1 fill, Stop execution. The raw text does not state the final ordered resolution after listing them.
- The raw blueprint uses both timezone `America/Los_Angeles` in session_context and `America/New_York` in TradingView context work outside this document; the raw blueprint's session context value is `America/Los_Angeles`.

## 13. Build Order Recommendation

Recommended order from the raw blueprint structure:

1. Pre-Market Engine context object:
   - Session context.
   - Levels with status.
   - Stack and boundary definitions.
   - Gateway.
   - ATR/range context.
   - Constraints.
   - Next liquidity.

2. Step 0 / Step 1 validators:
   - Level validation.
   - Static stack handling.
   - Session-built lock rule.
   - Gateway permission.

3. Step 2 Rejection Mode activation:
   - Close into liquidity.
   - Stack close-boundary commitment.
   - Mode initialization.
   - Rejection-only routing.
   - Pullback continuation independent activation.

4. Step 3 liquidity classification:
   - Normal level.
   - Static stack.
   - Pre-interaction rotation filter.

5. Step 4 Leg 1:
   - Candle A / Candle B.
   - Close-based participation.
   - 34% wick participation.
   - Anchor assignment.
   - 5% ATR proximity filter.

6. Step 5 Leg 2:
   - Priority order Wick Probe Override -> Candle B Extreme Override -> Standard Leg 2 Logic.
   - Wick Probe Override.
   - Candle B Extreme Override.
   - Dynamic Stack Routing.
   - Anchor Extreme invalidation.
   - Candle 4 participation validation before Step 6 handoff.

7. Step 6 Entry Models:
   - Opposing setup override.
   - Phase 1 Candle 4 timing.
   - Phase 2 rolling A/B timing.
   - Active-anchor Decision Pass.
   - Sweep Entry.
   - Double Wick.
   - First valid trigger wins.

8. Step 7 and Step 8:
   - Interaction termination.
   - Neutral reset.
   - Same-liquidity re-entry.

9. Step 10 Trade Management:
   - Risk model.
   - Bracket order.
   - BE.
   - TP1.
   - Runner.
   - 12:00 PM cutoff.
   - Confirmed-event state freeze.
