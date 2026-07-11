Randle AI Rejection Step 2 Lifecycle Specification
Formal Deterministic Contract
Document Type: Specialized Lifecycle Specification
Status: Canonical
Authority: Subordinate to the Randle AI Constitution, Lifecycle Vocabulary, and Lifecycle Engine Specification
Domain: Rejection lifecycle
Step: Step 2
Applies to: Entry Agent live processing, replay, lifecycle persistence, event journals, tests, reasoning logs, and /entry/status.

1. Purpose
Rejection Step 2 determines whether price has completed the defined rejection-confirmation pattern at an eligible liquidity level.
Its sole responsibilities are:
Evaluate an authorized rejection candidate.
determine whether the Step 2 confirmation rule has completed;
create one rejection lifecycle;
capture the Step 2 facts;
emit one immutable REJECTION_STEP2_CONFIRMED event.
Rejection Step 2 does not:
confirm Step 4;
create continuation;
execute a trade;
manage orders;
determine current positions;
rewrite liquidity levels;
modify confirmed lifecycle history;
make status endpoints stateful.

2. Domain Ownership
Rejection Step 2 belongs to one:
REJECTION_LIFECYCLE

It must never share mutable ownership with:
a continuation lifecycle;
another liquidity level;
another session;
another symbol;
another rejection candidate;
an execution order;
a UI projection.
The lifecycle established by Step 2 remains a rejection lifecycle permanently.
REJECTION_STEP2 and REJECTION_STEP4 are phase identifiers for stages owned by this same REJECTION_LIFECYCLE. Neither identifier denotes a separate independent trading lifecycle.

3. Authoritative Inputs
Rejection Step 2 may use only authorized inputs.
3.1 Session Inputs
Required:
session_id
session_date
session_status
entry_window_start
entry_window_end
session_lock_event_id

The session must be active and valid for new rejection evaluation.

3.2 Symbol Inputs
Required:
logical_symbol
market_data_contract
contract_mapping_version

The candle stream and liquidity level must belong to the same authorized symbol mapping.

3.3 Liquidity-Level Inputs
Required:
liquidity_level_id
liquidity_level_type
liquidity_level_price
liquidity_level_session_id
liquidity_level_locked_at
liquidity_level_status

The liquidity level must:
belong to the active session;
remain eligible under the level-consumption rules;
not be invalidated;
not be consumed;
be authorized for rejection evaluation.

3.4 Candle Inputs
Only completed and authorized candles may participate.
Each candle must include:
candle_id
logical_symbol
contract
session_id
interval
open_time
close_time
open
high
low
close
volume
source
completed

Every accepted candle must pass:
symbol validation;
contract validation;
session validation;
completion validation;
chronological-order validation;
duplicate validation;
freshness validation where applicable.

3.5 Volatility Inputs
When Step 2 rules or captured audit data require volatility normalization, Step 2 may use:
atr_value
atr_interval
atr_as_of
atr_source
atr_freshness_status
atr_version

The Step 2 event must capture the volatility value actually used at confirmation.
Later ATR changes must not alter the confirmed Step 2 event.

4. Preconditions
Rejection Step 2 evaluation may begin only when all of the following are true:
The session is valid for entry evaluation.
The logical symbol is authorized.
The contract mapping is valid.
The liquidity level belongs to the active session.
The liquidity level remains available.
No terminal level-consumption event blocks reuse.
Market data is sufficiently fresh.
Required volatility data is sufficiently fresh.
The candidate is classified as rejection.
No confirmed rejection Step 2 already owns the same candidate identity.
No prohibited duplicate lifecycle is being created.
The candle is completed and has not already been applied.
If any precondition fails, Step 2 must not confirm.

5. Rejection Candidate Identity
Before confirmation, each provisional candidate must have a stable candidate identity.
Recommended form:
candidate_id =
symbol
+ session_id
+ liquidity_level_id
+ direction
+ initial_interaction_candle_id

Example:
NQ-2026-07-10-ONH-SHORT-CANDIDATE-001

The candidate identity exists to:
prevent duplicate evaluation;
track candidate replacement;
establish causation;
support audit.
A candidate ID is not yet a permanent lifecycle ID.

6. Direction
Rejection direction must be explicit.
Examples:
Upper liquidity rejection:
direction = SHORT

Lower liquidity rejection:
direction = LONG

Direction must be assigned from the formal liquidity-interaction rule.
It must not be inferred later from current price.

7. Formal Step 2 Pattern
The existing Randle rejection-confirmation structure is:
Price interacts with or sweeps the eligible liquidity level.
Leg 1 shows movement away from the liquidity side.
Leg 2 confirms by closing beyond the Leg 1 close in the rejection direction.
The authorized sequence must complete within the defined candle limit.
The currently established confirmation framework is:
Leg 1:
Opposite-side rejection movement is shown.

Leg 2:
A completed candle closes beyond the Leg 1 close
in the rejection direction.

Timing:
The required Leg 1 extreme sweep and confirmation sequence
must occur within the authorized maximum of three candles.

All directional comparisons must be explicitly defined.

8. Directional Confirmation Rules
8.1 Short Rejection
A short rejection originates from an upper liquidity level.
The formal comparison must establish:
Leg 2 close < Leg 1 close

The implementation must also verify all required sweep, interaction, candle-order, and candle-limit conditions.
A mere price movement below the level is not enough.
A wick alone is not enough unless the entry-type rule explicitly authorizes it.
The completed Step 2 pattern must satisfy the full rejection rule.

8.2 Long Rejection
A long rejection originates from a lower liquidity level.
The formal comparison must establish:
Leg 2 close > Leg 1 close

The implementation must also verify all required sweep, interaction, candle-order, and candle-limit conditions.
A mere price movement above the level is not enough.
A wick alone is not enough unless the entry-type rule explicitly authorizes it.

9. Entry-Type Classification
The rejection candidate may be classified under an authorized Step 2 entry type.
Current known categories include:
WICK_SWEEP_RECLAIM
BODY_RECLAIM
DOUBLE_WICK
IMPULSE_OPEN

Entry-type classification must occur through explicit deterministic rules.
Each type must ultimately define:
qualifying liquidity interaction;
Leg 1 selection;
Leg 2 requirement;
confirmation candle;
boundary derivation;
volatility requirement;
maximum candle sequence;
invalidating conditions.
The entry type must be captured at Step 2 confirmation.
It may not be silently changed later.

10. Leg 1 Selection
Leg 1 must be selected by one deterministic function.
The selection must not depend on:
dictionary iteration order;
the most recently written field;
whichever candidate is currently displayed;
UI state;
future candles not authorized by the rule;
continuation state.
The selected Leg 1 must capture:
leg1_candle_id
leg1_open_time
leg1_close_time
leg1_open
leg1_high
leg1_low
leg1_close
leg1_extreme
leg1_direction
leg1_selection_rule

For short rejection:
leg1_extreme = leg1_high

For long rejection:
leg1_extreme = leg1_low

Once Step 2 confirms, the selected Leg 1 is immutable.

11. Leg 2 Selection
Leg 2 is the completed candle that satisfies the Step 2 close-confirmation rule.
It must occur after Leg 1.
It must capture:
leg2_candle_id
leg2_open_time
leg2_close_time
leg2_open
leg2_high
leg2_low
leg2_close
leg2_confirmation_rule

The Leg 2 candle is the Step 2 confirmation candle.
Therefore:
Step 2 confirmation candle = Count 0


12. Maximum Candle Sequence
The rejection pattern must complete within the authorized sequence limit.
The currently established limit is:
maximum three candles

The origin used by this maximum sequence is a trading-rule input, not an implementation decision. It must be supplied by the governing approved trading-rule definition. This architecture specification does not select or change whether that origin is the initial interaction candle, Leg 1, Leg 2, or another formally defined point.

Implementation, live processing, archive replay, tests, status projections, and reasoning logs must use the same governing origin and may not independently define, infer, or reinterpret it.

13. Candidate Replacement Before Confirmation
Before Step 2 confirmation, a provisional candidate may be replaced only when the formal candidate-selection rule authorizes replacement.
Candidate replacement must:
Remain within the same session.
remain tied to the same authorized liquidity context or explicitly create another candidate;
preserve an audit record of the prior candidate;
not mutate any confirmed lifecycle;
not reuse a confirmed lifecycle ID;
not alter another lifecycle.
After confirmation:
candidate replacement is prohibited

A later valid setup must receive a new candidate and lifecycle identity.

14. Confirmation Event
When the full rule completes, Step 2 must emit exactly one:
REJECTION_STEP2_CONFIRMED

Recommended event structure:
{
    "event_id": "...",
    "event_type": "REJECTION_STEP2_CONFIRMED",
    "event_version": 1,
    "lifecycle_id": "...",
    "candidate_id": "...",
    "symbol": "NQ",
    "contract": "NQU6",
    "session_id": "2026-07-10-RTH-PT",
    "liquidity_level_id": "NQ-2026-07-10-ONH",
    "direction": "SHORT",
    "entry_type": "WICK_SWEEP_RECLAIM",
    "occurred_at": "...",
    "source_candle_time": "...",
    "sequence": 1,
    "causation_id": "...",
    "rule_version": "...",
    "payload": {
        "liquidity_level_price": 30250.00,
        "leg1": {...},
        "leg2": {...},
        "step2_anchor": {...},
        "rejection_boundary": {...},
        "atr_snapshot": {...},
        "confirmation_count": 0
    }
}

The lifecycle field step2_event_id SHALL equal the event_id of this one REJECTION_STEP2_CONFIRMED event. Rejection Step 4 SHALL reference that exact identifier.


15. Lifecycle Creation
A permanent rejection lifecycle is established when Step 2 confirms.
Recommended lifecycle ID:
{symbol}-{session_date}-{liquidity_level_type}-REJECTION-{sequence}

Example:
NQ-2026-07-10-ONH-REJECTION-001

The lifecycle must capture:
lifecycle_id
lifecycle_type = REJECTION
session_id
symbol
contract
direction
liquidity_level_id
candidate_id
step2_event_id
rule_version
created_at

The lifecycle type is immutable.

16. Step 2 Anchor
The Step 2 anchor is the lifecycle-owned market reference created by the Step 2 rule.
It must include:
anchor_price
anchor_type
anchor_source_candle_id
anchor_source_field
anchor_created_at
anchor_rule_version

The specification for each entry type must identify exactly which price becomes the anchor.
After Step 2 confirmation:
anchor_price cannot change
anchor_source_candle_id cannot change
anchor_type cannot change

A new candle may not improve, replace, move, or reseed the confirmed anchor.

17. Rejection Boundary
Step 2 must capture the rejection boundary required for downstream rejection evaluation.
The boundary record must include:
boundary_price
boundary_type = REJECTION
boundary_source_candle_id
boundary_source_field
boundary_created_at
boundary_rule_version

After confirmation, the rejection boundary is frozen.
The following are prohibited:
recalculating it from the latest candle;
replacing it with a continuation boundary;
replacing it with the liquidity-level price;
replacing it with a fallback value;
clearing it during Step 4 evaluation;
changing it because another candidate appears;
deriving it from a projection field.

18. Captured Step 2 Facts
At confirmation, Step 2 must permanently capture at least:
lifecycle_id
step2_event_id
candidate_id
session_id
session_date
logical_symbol
contract
direction
entry_type
liquidity_level_id
liquidity_level_type
liquidity_level_price
interaction_candle_id
leg1 identity and OHLC
leg1 close
leg1 extreme
leg2 identity and OHLC
confirmation candle ID
confirmation timestamp
step2 anchor
rejection boundary
ATR or volatility snapshot
rule version
event version
Count 0 designation

These are lifecycle facts.
They are not current-status fields.

19. Immutable Fields
After REJECTION_STEP2_CONFIRMED, the following may never be changed within the same lifecycle:
lifecycle ID;
lifecycle type;
session ID;
symbol;
direction;
liquidity-level identity;
entry type;
selected Leg 1;
Leg 1 close;
Leg 1 extreme;
selected Leg 2;
confirmation candle;
confirmation timestamp;
Step 2 anchor;
rejection boundary;
captured ATR snapshot;
Step 2 event ID;
rule version used for confirmation.
A later event may terminate, invalidate, consume, or complete the lifecycle.
It may not rewrite these facts.

20. Derived Fields
The following are projections and may be rebuilt:
current_step
step2_status_label
step2_candle_count_display
wait_reason
operator_message
public_rejection_boundary
elapsed_candles
eligible_for_step4

Derived fields must always trace back to the immutable Step 2 event.
They may not become the source of truth.

21. Legal Outcomes Before Confirmation
A candidate being evaluated by Step 2 may produce:
NO_CHANGE
CANDIDATE_STARTED
CANDIDATE_UPDATED
CANDIDATE_REPLACED
CANDIDATE_DISCARDED
CANDIDATE_EXPIRED
REJECTION_STEP2_CONFIRMED
LEVEL_INVALIDATED
LEVEL_CONSUMED
SESSION_CLOSED

Each outcome must be generated by an explicit rule.

22. Legal Outcomes After Confirmation
After Step 2 confirmation, the same Rejection Lifecycle may advance into its Rejection Step 4 phase. The exact Step 4 outcome set and transition map are governed only by an approved canonical Rejection Step 4 specification.

Because the current Step 4 specification is a draft, this document does not canonically select among READY, CONFIRMED, FAILED, TERMINATED, or EXPIRED outcomes.

Step 2 itself remains confirmed.
It does not return to:
SEARCHING
CANDIDATE
NOT_STARTED

within the same lifecycle.

23. Prohibited Transitions
The following transitions are invalid:
REJECTION_STEP2_CONFIRMED
→ REJECTION_STEP2_SEARCHING

REJECTION_STEP2_CONFIRMED
→ CANDIDATE_REPLACED

REJECTION_STEP2_CONFIRMED
→ CONFIRMED_WITH_NEW_BOUNDARY

REJECTION_STEP2_CONFIRMED
→ CONTINUATION_STEP2_CONFIRMED
using the same lifecycle ID

REJECTION_STEP2_CONFIRMED
→ PRIOR_SESSION_ACTIVE

REJECTION_STEP2_CONFIRMED
→ CLEARED_BY_STATUS_REQUEST

REJECTION_STEP2_CONFIRMED
→ RESEEDED_FROM_LATER_CANDLE


24. Idempotency Contract
Reprocessing the same confirmation candle must not create:
another Step 2 event;
another lifecycle;
another sequence increment;
another candle count;
another boundary;
a modified confirmation timestamp.
The idempotency key should include sufficient identity, such as:
event_type
session_id
symbol
liquidity_level_id
candidate_id
confirmation_candle_id
rule_version

When the same logical confirmation is encountered again:
result = NO_OP_DUPLICATE


25. Out-of-Order Candle Contract
If a candle older than the last accepted Step 2 input arrives:
it must not replace Leg 1;
it must not replace Leg 2;
it must not move the anchor;
it must not change the confirmation time;
it must not decrement or increment counts;
it must not create another lifecycle.
The candle must be:
rejected
quarantined
or safely ignored

with an audit record.

26. Session Contract
A rejection Step 2 lifecycle belongs to exactly one session.
A prior-session Step 2 confirmation may be displayed historically.
It may not become the active Step 2 for a new session.
On session rollover:
confirmed Step 2 history remains preserved;
active eligibility ends according to the session rules;
the projection for the new session begins empty;
a new candidate requires the new session ID.
No Step 2 field should be “carried forward” merely because it exists in persistent storage.

27. Status Endpoint Contract
/entry/status may report the Step 2 projection.
It may not:
evaluate a new Step 2;
create a candidate;
replace a candidate;
confirm Step 2;
write lifecycle state;
update candle count;
persist an anchor;
modify a boundary;
trigger session rollover;
alter reasoning history.
Repeated requests must be observationally pure.

28. Replay Contract
Given the same:
ordered completed candles;
session lock;
liquidity levels;
volatility inputs;
rule version;
contract mapping;
replay must reproduce exactly:
candidate selection;
Leg 1;
Leg 2;
confirmation candle;
confirmation timestamp;
lifecycle ID;
Step 2 anchor;
rejection boundary;
entry type;
volatility snapshot;
event sequence.
Any difference between live and replay is a defect unless caused by a documented difference in authoritative input.

29. Required Invariants
The following must always hold:
Step 2 confirmation has exactly one lifecycle ID.

The lifecycle type is REJECTION.

The confirmation candle is Count 0.

Leg 2 occurs after Leg 1.

The Step 2 event belongs to the same session as the liquidity level.

The Step 2 event belongs to the same symbol as the candles.

The confirmed boundary is immutable.

The selected Leg 1 is immutable.

A duplicate confirmation is a no-op.

A continuation lifecycle cannot overwrite rejection Step 2.

A read-only request cannot create or modify Step 2.


30. Minimum Regression Tests
The implementation must include tests proving:
Short rejection Step 2 confirms correctly.
Long rejection Step 2 confirms correctly.
Leg 2 must close beyond the Leg 1 close.
A wick without the required close does not confirm.
The sequence respects the maximum candle limit.
The confirmation candle is Count 0.
A duplicate candle does not double-confirm.
A restart immediately after confirmation reproduces the same Step 2.
A later candidate does not replace confirmed Step 2.
A continuation candidate does not overwrite rejection Step 2.
A stale candle does not replace Leg 1.
An out-of-order candle does not replace Leg 2.
A prior-session Step 2 does not become active today.
/entry/status does not mutate Step 2.
Replay produces the same lifecycle and boundary.
The rejected or consumed liquidity level cannot improperly generate Step 2.
Contract mismatch blocks confirmation.
Missing or stale required ATR blocks confirmation when the rule requires fresh ATR.
Candidate replacement remains possible only before confirmation.
Step 2 remains confirmed after any later Step 4 outcome.

31. Codex Modification Requirements
Before changing Rejection Step 2 code, Codex must report:
Authoritative input source

Candidate identity rule

Lifecycle creation point

Leg 1 selection function

Leg 2 confirmation function

Anchor derivation function

Boundary derivation function

Persistence writer

Projection reader

Duplicate protection

Session guard

Replay test coverage

Codex must not modify Step 2 until it can identify every writer capable of changing:
Step 2 confirmation status;
Step 2 timestamp;
Leg 1 identity;
anchor;
rejection boundary;
lifecycle ID;
candle count.

32. Acceptance Standard
Rejection Step 2 is correctly implemented only when:
One valid market pattern
creates one rejection lifecycle
with one immutable Step 2 event
and one reproducible set of captured facts.

No polling, restart, later candle, continuation process, UI projection, stale file, or fallback path may change those captured facts.
