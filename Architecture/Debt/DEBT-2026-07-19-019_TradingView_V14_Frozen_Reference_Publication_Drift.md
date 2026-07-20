# DEBT-2026-07-19-019 — TradingView v14 Frozen Reference Publication Drift

Status: BLOCKING — TradingView publication and runtime readiness

Discovery Source: 2026-07-19 YM `STACK_REFERENCE_PRICE_MISSING` investigation

Owner: TradingView Level Map publication/cutover authority

## Condition

The active TradingView alert identified as `v14_overlapping_stack_smoke` serializes finalized YH/YL stack membership and `stack_threshold` but omits the existing canonical `session_lock_price` field.

The repository's governed Pine source already serializes the field. The v14 finalized-table replacement serializer omitted it. That serializer is corrected in repository SHA-256 `7A677CB6B40AFF4A180A121890C64F50D036E21F96E227ED3A3DBB1ABB2E911F`, but the active TradingView publication has not been replaced.

## Runtime consequence

A YH/YL-containing stack cannot be side-validated without the exact frozen market reference used by the sender. Entry Agent correctly rejects the body with `STACK_REFERENCE_PRICE_MISSING` before merge, persistence, rehydration, frozen-ladder projection, lifecycle evaluation, or order state.

NQ currently passes the same ingress path only because its accepted body has no stack membership and therefore does not require side disambiguation. This is not a symbol-specific exception.

## Prohibited remediation

- Do not infer the missing reference from current price, Rithmic bars, a prior payload, persisted state, or YH/YL names.
- Do not remove YH/YL from a valid stack solely to bypass side validation.
- Do not weaken the receiver or mark a rejected body fresh/current.
- Do not authorize deployment or live trading from repository-only tests.

## Retirement evidence

All of the following are required:

1. compile the exact corrected v14 serializer in TradingView and preserve the source hash and compiler evidence;
2. verify the table, explicit stack objects, and webhook body agree;
3. recreate or update both NQ and YM alerts through an explicitly authorized cutover;
4. receive a fresh YM body containing numeric `session_lock_price`, current session identity, `stack_threshold`, and unchanged finalized membership;
5. observe Entry Agent acceptance exactly once and replacement/quarantine of stale prior-session context under existing rules;
6. prove NQ and YM follow the same structural validator;
7. prove current-session ladder readiness and canonical ATR readiness independently;
8. prove no trade, order, position, account, risk, or cash authority changed; and
9. obtain explicit deployment authorization.

Repository correction alone does not retire this debt.
