# Phase 2 Plan - Steps 3-6 Execution Engine

## 1. Overview

Phase 2 goal: convert the finalized blueprint into an executable EntryAgent decision engine for Steps 3-6.

The engine must remain decision-only. It may confirm or invalidate setup state, but it must not place live orders or modify Trade Manager / Executor behavior.

## 2. Module Breakdown

### step3_engine.py

Purpose:

- Classify active liquidity after Step 2 activation.
- Route to Normal Level logic or Static Stack logic.
- Enforce the pre-interaction rotation filter.

Inputs:

- Current interaction state.
- Active liquidity level or stack.
- Candle A.
- Stack boundaries.
- Recent completed candles.

Outputs:

- Step 3 status.
- Liquidity type.
- Route target: Step 4A, Step 4B, wait, or Step 7.
- Reason string.
- Events.

State dependencies:

- `rejection_mode`
- `trade_mode`
- `active_liquidity`
- `active_stack`
- `close_boundary`
- `extreme_boundary`
- `participation_timer`
- `sweep_extreme_boundary_seen`
- `rotation_filter_active`
- `stack_logic_valid`

### step4_engine.py

Purpose:

- Build Leg 1 from Candle A and Candle B.
- Validate close-based participation or 34% wick participation.
- Assign Leg 1 reference, Leg 1 extreme, and Anchor Extreme.
- Apply the 5% ATR proximity filter.

Inputs:

- Interaction state from Step 3.
- Candle A.
- Candidate Candle B.
- Setup direction.
- ATR context.
- Nearest liquidity distance.

Outputs:

- Leg 1 status.
- Candle B assignment.
- `leg1_reference`
- `leg1_extreme`
- `leg1_extreme_owner`
- `anchor_extreme`
- Route target: Step 5 or Step 7.
- Reason string.
- Events.

State dependencies:

- `candle_a`
- `candle_b`
- `setup_direction`
- `leg1_status`
- `proximity_distance`
- `proximity_atr_threshold`
- `anchor_extreme`

### step5_engine.py

Purpose:

- Confirm Leg 2 by locked priority order.
- Enforce one active structural reference.
- Apply Wick Probe Override, Participation Candle Extreme Override, or Core Requirement.
- Handle Anchor Extreme invalidation.

Inputs:

- Valid Leg 1 state.
- Candidate Leg 2 candle.
- Active setup direction.
- Wick probe state.
- Anchor Extreme.
- Dynamic stack context.

Outputs:

- Leg 2 status.
- Active Step 5 path.
- Updated wick probe state if applicable.
- Structure confirmed or invalidated.
- Route target: Step 6 or Step 7.
- Reason string.
- Events.

State dependencies:

- `leg1_reference`
- `leg1_extreme`
- `leg1_extreme_owner`
- `active_step5_path`
- `wick_probe_active`
- `probe_high`
- `probe_low`
- `dynamic_stack_active`
- `anchor_extreme`
- `step5_confirmed`

### step6_engine.py

Purpose:

- Run SC / SC2 / SC3 progression.
- Run SC Decision Pass.
- Evaluate entry models without placing orders.
- Emit entry-confirmed decision only.

Inputs:

- Confirmed Step 5 structure.
- Active SC candle.
- Next completed candle or intrabar evaluation payload.
- Setup direction.
- Tick size.

Outputs:

- SC Decision Pass output.
- Entry model states.
- Entry confirmed or invalidated.
- Route target: Step 10 decision output or Step 7.
- Reason string.
- Events.

State dependencies:

- `sc`
- `sc2`
- `sc3`
- `current_sc`
- `sc_progression_count`
- `sc_decision_pass_output`
- `sweep_entry_path`
- `double_wick_state`
- `entry_triggered`
- `entry_model_triggered`
- `entry_price`
- `entry_time`
- `structure_locked`

### step7_engine.py

Purpose:

- Centralized invalidation and termination path.
- Reset interaction structure.
- Prevent all structure reuse after termination.

Inputs:

- Current interaction object.
- Termination reason.
- Source step.

Outputs:

- `system_state = NEUTRAL RESET`
- `rejection_mode = OFF`
- `trade_mode = OFF`
- Cleared structure fields.
- Reason string.
- Termination event.

State dependencies:

- All interaction fields.
- `pre_activation_probe_boundary`
- Leg 1 state.
- Leg 2 state.
- SC state.
- Timing and sweep state.

## 3. State Model

The execution engine should operate on one interaction object passed through each step.

Key fields:

- `interaction_id`
- `system_state`
- `trade_mode`
- `rejection_mode`
- `interaction_state`
- `active_liquidity`
- `active_stack`
- `setup_direction`
- `candle_a`
- `candle_b`
- `leg1_status`
- `leg1_reference`
- `leg1_extreme`
- `leg1_extreme_owner`
- `anchor_extreme`
- `leg2_status`
- `leg2_candle`
- `active_step5_path`
- `wick_probe_active`
- `probe_high`
- `probe_low`
- `active_sc`
- `sc`
- `sc2`
- `sc3`
- `sc_progression_count`
- `sc_decision_pass_output`
- `entry_triggered`
- `entry_model_triggered`
- `structure_locked`
- `pre_activation_probe_boundary`
- `events`
- `reason`

## 4. Data Flow

`entry_agent.py` calls the decision modules after existing Step 1, Step 2, and Step 2.1A evaluation.

Execution order:

1. Step 1 gateway permission already evaluated.
2. Step 2 / Step 2.1A activates interaction and assigns Candle A.
3. `step3_engine.py` classifies liquidity and routes the interaction.
4. `step4_engine.py` validates participation and builds Leg 1.
5. `step5_engine.py` confirms or invalidates Leg 2.
6. `step6_engine.py` evaluates entry models and emits decision-only entry confirmation.
7. `step7_engine.py` handles every invalidation, reset, or failed setup.

Step 7 reset behavior:

- Clear Leg 1.
- Clear Leg 2.
- Clear SC progression.
- Clear sweep and wick probe state.
- Clear `pre_activation_probe_boundary`.
- Set system to `NEUTRAL RESET`.
- Preserve only audit events and termination reason.

## 5. Rules Enforcement

- Step 7 is the only invalidation path.
- No structure reuse after termination.
- Only one active structural reference may exist in Step 5.
- Step 5 override priority must be deterministic.
- Step 6 outputs are decisions only; no live orders.
- Every state transition must include a reason string.
- Every module must return deterministic outputs only.
- No module may infer missing candles, missing levels, or missing ATR.

## 6. Testing Plan

Replay tests for Step 3:

- Normal level routes to Step 4A.
- Static stack waits until Extreme Boundary sweep.
- Static stack routes to Step 4B after sweep.
- Pre-interaction rotation disables stack logic.

Replay tests for Step 4:

- Close-based participation passes.
- 34% wick participation passes.
- No participation routes through Step 7.
- 5% ATR proximity hard bypass routes through Step 7.

Replay tests for Step 5:

- Core 5.1 confirmation passes.
- Candle B extreme owner activates 5.3A.
- Wick probe activates 5.3B and overrides lower priority paths.
- Anchor Extreme close invalidates through Step 7.
- Failed Leg 2 routes through Step 7.

Replay tests for Step 6:

- SC Decision Pass classifies Large Wick and Small Wick paths.
- SC progression advances SC -> SC2 -> SC3.
- No entry after SC3 next candle routes through Step 7.
- Sweep Entry confirms decision without order placement.
- Double Wick confirms decision without order placement.

Replay tests for Step 7:

- Termination clears all reusable structure.
- Probe state is cleared.
- Prior Leg 1 / Leg 2 / SC cannot be reused after reset.
