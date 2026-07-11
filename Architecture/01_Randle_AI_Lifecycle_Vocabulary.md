Randle AI Lifecycle Vocabulary
Formal Domain Definitions for Rejection and Continuation
Document Type: Lifecycle Vocabulary
Status: Canonical
Authority: Binding terminology standard subordinate only to the Randle AI Constitution
Applies to: Entry Agent, replay tools, lifecycle state, event journals, status projections, Codex prompts, tests, and operator documentation.

1. Purpose
The purpose of this vocabulary is to ensure that every component uses the same meaning for each lifecycle term.
No term in this document may be used interchangeably with another term unless explicitly stated.
The system must distinguish between:
raw market information;
recognized market facts;
lifecycle facts;
derived projections;
decisions;
execution facts.
Ambiguous words such as “current,” “active,” “confirmed,” “boundary,” “reset,” and “state” must always be tied to a specific owner and lifecycle.

2. Core Domain Objects
2.1 Session
A Session is the authoritative trading-day container for all market and lifecycle activity.
A session has:
session_id
session_date
timezone
start_time
lock_time
entry_window_start
entry_window_end
session_close_time
status
Example:
session_id: 2026-07-10-RTH-PT
session_date: 2026-07-10
timezone: America/Los_Angeles

A lifecycle may belong to only one session.

2.2 Symbol
A Symbol is the logical market identity used by the strategy.
Examples:
NQ
YM

The logical symbol must remain distinct from the resolved execution contract.
Example:
logical_symbol: NQ
execution_contract: NQU6

A contract rollover must not alter the logical identity of an existing lifecycle.

2.3 Contract
A Contract is the specific exchange instrument used for market data or execution.
Examples:
NQM6
NQU6
YMM6
YMU6

Contract resolution belongs to the market-data and execution boundary.
Lifecycle rules operate on the authorized symbol and contract mapping for that session.

2.4 Candle
A Candle is a completed, time-bounded market-data fact.
A candle includes:
symbol;
contract;
session;
interval;
open time;
close time;
open;
high;
low;
close;
volume;
source;
completion status.
Only completed candles may advance deterministic lifecycle rules unless a rule explicitly authorizes intrabar evaluation.

2.5 Liquidity Level
A Liquidity Level is a named, session-qualified market reference used by the strategy.
Examples:
YH
YL
ONH
ONL
PMH
PML
LH
LL
RTH high
RTH low
A liquidity level includes:
liquidity_level_id
level_type
price
session_id
source_window
locked_at
rule_version

Example:
NQ-2026-07-10-ONH

A liquidity level is not merely a price.
It is a permanent identity consisting of:
type;
price;
symbol;
session;
source window.

3. Lifecycle Types
A lifecycle type identifies an independent lifecycle domain, such as REJECTION or CONTINUATION. A lifecycle phase type or phase identifier, such as REJECTION_STEP2 or REJECTION_STEP4, identifies a stage within that lifecycle; it does not create another independent trading lifecycle. Rejection Step 2 and Rejection Step 4 therefore belong to one Rejection Lifecycle and share its lifecycle ID.

References in this vocabulary to Rejection Step 5, Rejection Step 6, or continuation phases reserve terminology and universal ownership distinctions only. They do not define canonical behavior for those phases or authorize their implementation in Architecture Documentation Release v1.0.

3.1 Rejection Lifecycle
A Rejection Lifecycle is the deterministic evaluation of whether price interacted with a liquidity level and rejected away from it according to the defined rejection rules.
A rejection lifecycle:
begins from a specific liquidity interaction;
owns its own Step 2;
owns its own Step 4;
may advance to Step 5 and Step 6;
may create a continuation lifecycle;
remains preserved after continuation creation.
Example lifecycle ID:
NQ-2026-07-10-ONH-REJECTION-001


3.2 Continuation Lifecycle
A Continuation Lifecycle is a new lifecycle created from a completed and eligible rejection lifecycle when price later satisfies the continuation creation rule.
A continuation lifecycle:
has its own lifecycle ID;
has one rejection parent;
owns its own Step 2;
owns its own Step 4;
owns its own timestamps;
owns its own candle count;
owns its own continuation boundary;
must never overwrite the rejection lifecycle.
Example lifecycle ID:
NQ-2026-07-10-ONH-CONTINUATION-001


3.3 Parent Lifecycle
A Parent Lifecycle is the lifecycle whose confirmed facts authorize creation of another lifecycle.
For continuation:
parent_lifecycle_type: REJECTION
child_lifecycle_type: CONTINUATION

Parenthood does not transfer ownership.
The parent remains complete and independently auditable.

4. Lifecycle Identity
4.1 Lifecycle ID
A Lifecycle ID is the permanent identity of one rejection or continuation opportunity.
It must uniquely identify:
symbol;
session;
originating liquidity level;
lifecycle type;
sequence.
A lifecycle ID must never be reused.
A lifecycle ID must never change type.
A rejection lifecycle cannot become a continuation lifecycle.

4.2 Lifecycle Sequence
A Lifecycle Sequence distinguishes multiple valid lifecycle instances involving the same symbol, session, level, and lifecycle type.
Example:
NQ-2026-07-10-ONH-REJECTION-001
NQ-2026-07-10-ONH-REJECTION-002

A new sequence is created only when the formal rules permit a new opportunity.
A new candidate does not automatically justify a new lifecycle.

4.3 Lifecycle Status
A Lifecycle Status describes the lifecycle as a whole.
Allowed lifecycle-level statuses should be limited to terms such as:
PENDING
ACTIVE
CONFIRMED
TERMINATED
INVALIDATED
CONSUMED
EXPIRED
COMPLETED

Lifecycle status must not be used as a substitute for the status of an individual step.

5. Candidate Terminology
5.1 Candidate
A Candidate is a possible but unconfirmed lifecycle opportunity.
A candidate is provisional.
A candidate may change or disappear before confirmation.
A candidate is not a confirmed lifecycle fact.

5.2 Candidate Identity
A candidate may have a temporary identity for deduplication and tracking.
Example:
candidate_id
symbol
session_id
liquidity_level_id
direction
candidate_started_at

A candidate ID must not be presented as a permanent lifecycle ID until the formal lifecycle-creation rule is satisfied.

5.3 Candidate Replacement
Candidate Replacement is the authorized substitution of one provisional candidate for another before Step 2 confirmation.
Candidate replacement is allowed only before immutable lifecycle confirmation.
Candidate replacement must never rewrite a confirmed Step 2 lifecycle.

5.4 Reseed
The word reseed must be used only for provisional candidate creation before confirmation.
It must not mean:
replacing a confirmed Step 2;
resetting Step 4;
changing a frozen boundary;
changing lifecycle identity;
transferring continuation values into rejection;
reviving prior-session state.
After Step 2 confirmation, “reseed” is prohibited for that lifecycle.

6. Step Terminology
6.1 Step
A Step is a deterministic rule checkpoint within one lifecycle.
A step has:
lifecycle owner;
rule definition;
authorized inputs;
evaluation window;
completion event;
terminal outcomes.
A step is not an independent market object.
It exists only within a lifecycle.

6.2 Step Status
A Step Status describes the evaluation state of one step within one lifecycle.
Recommended statuses:
NOT_STARTED
SEARCHING
READY
CONFIRMED
FAILED
TERMINATED
EXPIRED
NOT_APPLICABLE

Avoid ambiguous labels such as:
ACTIVE
CURRENT
DONE
VALID
WAITING

unless the exact meaning is defined.

6.3 Current Step
Current Step is a projection showing the next or most relevant operator-facing lifecycle stage.
It is not authoritative history.
It must be derived from lifecycle events.
It must never be used to identify the parent of a new event.
Code must not perform logic equivalent to:
parent = current_step

The parent must be identified through lifecycle and event IDs.

7. Step 2 Vocabulary
7.1 Step 2 Candidate
A Step 2 Candidate is a provisional setup being evaluated for Step 2 confirmation.
It may contain temporary values.
Those values are not immutable until confirmation.

7.2 Step 2 Confirmation
Step 2 Confirmation is the authoritative event that the formal Step 2 rule has been satisfied for one lifecycle.
It must create or finalize:
lifecycle ID;
Step 2 event ID;
confirmation timestamp;
confirmation candle identity;
direction;
liquidity-level identity;
Leg 1 identity;
Step 2 anchor;
applicable boundary;
captured volatility values;
rule version.
After confirmation, these values are immutable unless the formal specification defines an explicit correction event.

7.3 Step 2 Event ID
A Step 2 Event ID uniquely identifies the Step 2 confirmation event.
Step 4 must reference this exact event.
Example for a rejection lifecycle:
event_id: NQ-2026-07-10-EVT-000142
event_type: REJECTION_STEP2_CONFIRMED


7.4 Step 2 Anchor
The Step 2 Anchor is the exact captured market reference established by the Step 2 rule.
It is lifecycle-owned.
It must specify:
value;
source candle;
derivation rule;
confirmation time;
rule version.
Once confirmed, it is frozen.

7.5 Step 2 Count 0
Count 0 is the Step 2 confirmation candle.
The confirmation candle is not Count 1.
The next completed authorized candle is Count 1.
The following completed authorized candle is Count 2.
This terminology must be identical in:
live processing;
replay;
tests;
UI;
reasoning logs;
status endpoints.

8. Step 4 Vocabulary
8.1 Step 4 Evaluation Window
The Step 4 Evaluation Window is the authorized candle sequence following Step 2 confirmation.
It begins and ends according to the formal lifecycle rules.
It must be tied to the Step 2 event ID.

8.2 Step 4 Ready
Step 4 Ready is a reserved label for a readiness condition if an approved canonical Step 4 specification uses it.
The exact meaning, timing, and transition associated with Ready remain unresolved in Architecture Documentation Release v1.0. Ready is not a canonical Step 4 outcome until an approved specification defines it.

8.3 Step 4 Confirmation
Step 4 Confirmation is the authoritative event that a formally approved Step 4 rule has been satisfied for one lifecycle.
If an approved canonical specification defines this event, it must reference:
lifecycle ID;
upstream Step 2 confirmation event ID;
Step 4 event ID;
the evaluation facts required by the approved rule;
rule version.
Step 4 confirmation cannot exist without a valid upstream Step 2 confirmation event in the same lifecycle.

8.4 Step 4 Termination
Step 4 Termination is a reserved label for an outcome that an approved canonical Step 4 specification may classify as terminal.
The conditions, timing, and relationship to retry, failure, and expiration remain unresolved. If an approved specification defines termination as terminal, it inherits the Lifecycle Engine's sticky-terminal protections.
A later valid setup requires a new lifecycle.

8.5 Step 4 Failure
Step 4 Failure is a reserved label for an unsuccessful evaluation if an approved canonical Step 4 specification uses that outcome. The lifecycle may or may not remain eligible depending on the future approved rule.
Failure must not be used interchangeably with termination.
The formal specification must state whether failure is:
temporary;
final;
retryable;
non-retryable.

8.6 Step 4 Expiration
Step 4 Expiration means the authorized evaluation window ended without confirmation.
Whether expiration exists, whether it is terminal, and how it relates to retry or termination are defined only by an approved canonical Step 4 specification. The current Step 4 draft does not decide those rules.

9. Candle-Sequence Vocabulary
9.1 Confirmation Candle
The Confirmation Candle is the completed candle that satisfies Step 2.
It is Count 0.

9.2 Candle A
Candle A is the first completed authorized candle after the Step 2 confirmation candle.
Candle A is Count 1.

9.3 Candle B
Candle B is the second completed authorized candle after the Step 2 confirmation candle.
Candle B is Count 2.

These count labels define vocabulary only. They do not determine the authorized Step 4 evaluation count, retry behavior, terminal window, or Candle A replacement policy; those rules remain unresolved pending an approved canonical Step 4 specification.

9.4 Authorized Candle
An Authorized Candle is a completed candle that:
belongs to the correct symbol;
belongs to the correct session;
occurs after the upstream Step 2 confirmation event;
falls within the authorized evaluation window;
has not already been applied;
satisfies freshness and ordering requirements.
A duplicate candle is not a second authorized candle.

10. Boundary Vocabulary
10.1 Liquidity Boundary
A Liquidity Boundary is the original named liquidity level used to initiate or classify the market interaction.
Example:
ONH at 30,250.00


10.2 Rejection Boundary
A Rejection Boundary is the frozen lifecycle value used to evaluate the rejection pathway after Step 2 confirmation.
It belongs only to the rejection lifecycle.
It must include:
price;
source candle;
source field;
capture time;
rule version.

10.3 Continuation Boundary
A Continuation Boundary is the frozen value created from an eligible confirmed rejection lifecycle for use by the continuation lifecycle.
It belongs to the continuation lifecycle after creation.
It may be derived from a rejection fact, but it is not the rejection boundary itself unless the formal rule explicitly makes them numerically equal.
Identity and ownership remain separate even when prices are equal.

10.4 Frozen Boundary
A Frozen Boundary is a confirmed boundary whose numerical value and source identity may no longer change within the lifecycle.
“Frozen” refers to immutability.
It does not mean:
currently displayed;
cached;
copied into a UI field;
temporarily unavailable;
inferred from a later candle.

10.5 Public Boundary
A Public Boundary is the operator-facing projection of an authoritative lifecycle boundary.
Examples:
Rejection Boundary
Continuation Boundary
The public field is not authoritative by itself.
It must identify or be traceable to its lifecycle-owned source.

11. Leg Vocabulary
11.1 Leg 1
Leg 1 is the first formally defined market movement used by the confirmation model.
Leg 1 must have:
candle identity;
direction;
open;
high;
low;
close;
extreme;
relationship to the liquidity level.
The formal Step 2 specification will define exactly when Leg 1 begins and ends.

11.2 Leg 1 Close
The Leg 1 Close is the confirmed close value belonging to the selected Leg 1 candle.
It is not interchangeable with:
confirmation candle close;
current candle close;
liquidity-level price;
Leg 1 extreme.

11.3 Leg 1 Extreme
The Leg 1 Extreme is the high or low of the selected Leg 1 candle, depending on direction.
Once captured at Step 2 confirmation, it belongs to that lifecycle.

12. Invalidity and Consumption Vocabulary
12.1 Invalidation
Invalidation is an explicit lifecycle event stating that a defined rule condition has made a level or lifecycle unusable.
Invalidation must identify:
subject being invalidated;
threshold;
triggering candle;
event time;
lifecycle effect.
Invalidation is not the same as termination unless the formal rules say so.

12.2 Level Consumption
Level Consumption means a named liquidity level can no longer be reused for another rejection or continuation opportunity under the current session rules.
Consumption belongs to the liquidity-level identity.
It must not be represented merely by clearing a lifecycle field.

12.3 50% Invalidation
50% Invalidation means the formal 50% threshold was crossed according to the strategy definition.
Its exact reference range, calculation, direction, and candle requirement must be defined in the lifecycle specification.

12.4 75% Invalidation
75% Invalidation means the formal 75% threshold was crossed according to the strategy definition.
It must be represented as an explicit event and linked to the affected level or lifecycle.

12.5 Sticky Terminal State
A Sticky Terminal State is a state that cannot be reversed within the same lifecycle.
Examples may include:
terminated;
invalidated;
consumed;
expired;
completed.
A sticky state may only be followed by an allowed downstream event or a new lifecycle.

13. Continuation Vocabulary
The terms in this section reserve consistent vocabulary and universal ownership distinctions. They do not define a canonical continuation lifecycle state machine, trading rule, transition sequence, or implementation. Architecture Documentation Release v1.0's specialized lifecycle scope ends at Continuation Eligibility Creation.

13.1 Continuation Eligibility
Continuation Eligibility is a derived condition stating that a completed rejection lifecycle has satisfied all prerequisites required to create a continuation lifecycle.
Eligibility is not continuation creation.
Eligibility is not Step 2 confirmation.

13.2 Continuation Creation
Continuation Creation is the explicit event that establishes a new continuation lifecycle.
It must include:
continuation lifecycle ID;
parent rejection lifecycle ID;
parent Step 4 event ID;
continuation boundary;
direction;
creation time;
rule version.

13.3 Continuation Evaluation Start
Continuation Evaluation Start is the first authorized market event after continuation creation that begins the continuation Step 2 search.
It must not alter the parent rejection lifecycle.

13.4 Continuation Confirmation
Continuation Confirmation means the continuation lifecycle’s own Step 2 rule has confirmed.
It is not inherited from the rejection lifecycle.

14. Projection Vocabulary
14.1 Projection
A Projection is a rebuildable representation of authoritative facts for a particular purpose.
Examples:
operator status;
lifecycle summary;
current step;
public boundary display;
replay checkpoint;
Command Center panel.

14.2 Active Lifecycle Projection
An Active Lifecycle Projection is the current operator-facing summary of a lifecycle that remains eligible for further legal transitions.
It is not the lifecycle itself.

14.3 Last Decision
Last Decision is a historical projection of the most recent decision event.
It must not be used as current lifecycle state.
It must include enough identity to distinguish:
session;
lifecycle;
event time;
decision type.

14.4 Wait Reason
A Wait Reason is an operator-facing explanation of why no new lifecycle transition has occurred.
It is derived.
It may not change authoritative lifecycle facts.

15. Event Vocabulary
15.1 Event
An Event is an immutable record that a domain fact occurred.
An event must be written in past tense.
Examples:
STEP2_CONFIRMED
STEP4_TERMINATED
CONTINUATION_CREATED
LEVEL_CONSUMED


15.2 Event ID
An Event ID is the globally or domain-unique identity of an event.
Repeated processing of the same event ID must be a no-op.

15.3 Causation ID
A Causation ID identifies the event or market input that directly caused another event.
Example:
STEP4_CONFIRMED
caused_by:
CANDLE_COMPLETED


15.4 Correlation ID
A Correlation ID groups related events for audit.
For lifecycle events, the lifecycle ID may serve as the correlation ID.

15.5 Event Sequence
An Event Sequence is the monotonic order of accepted events within a lifecycle or session stream.
An event with an older sequence may not overwrite a projection built from a newer sequence.

16. Reset Vocabulary
The word reset is prohibited unless its exact target and legal meaning are stated.
Allowed forms may include:
projection rebuild
new session initialization
provisional candidate discard
test fixture reset

The word reset must not mean:
erase confirmed history;
clear a boundary;
remove an accepted upstream Step 2 event reference;
revive a terminated lifecycle;
convert rejection into continuation;
load yesterday’s lifecycle as today’s;
make the UI look current by deleting evidence.

17. State Vocabulary
The generic word state must be qualified.
Use:
market-data state;
candidate state;
lifecycle state;
step state;
projection state;
execution state;
session state;
UI state.
Do not use unqualified statements such as:
update the state
clear state
use current state
restore state

Every state mutation must name:
the owner;
the lifecycle;
the field;
the triggering event;
the legal transition.

18. Freshness Vocabulary
18.1 Fresh
Fresh means the data timestamp is within the formally defined freshness threshold for its use.
Freshness must be evaluated against:
source timestamp;
current system time;
expected feed interval;
market session;
configured threshold.

18.2 Stale
Stale means data is older than the authorized freshness threshold.
Stale data may be displayed with warning context.
It may not authorize a new trade decision or execution action unless the formal rule explicitly permits it.

18.3 Missing
Missing means no authoritative value exists.
Missing is not the same as stale.
The system must not silently replace missing information with:
prior-session data;
a different contract;
a UI cache;
a later-derived value;
a default zero;
a guessed boundary.

19. Error Vocabulary
19.1 Invalid Transition
An Invalid Transition is an attempted lifecycle change not permitted by the formal transition table.
It must be rejected or quarantined.

19.2 Ownership Violation
An Ownership Violation occurs when one component or lifecycle attempts to alter information owned by another.
Example:
Continuation Step 2 overwrites rejection Step 2 boundary.


19.3 Parent Mismatch
A Parent Mismatch occurs when a distinct child lifecycle references the wrong parent lifecycle. An Upstream Event Mismatch occurs when a Step 4 phase event references the wrong Step 2 confirmation event or a different Rejection Lifecycle.

19.4 Session Mismatch
A Session Mismatch occurs when an event, candle, level, or lifecycle belongs to a different session from the target lifecycle.

19.5 Contract Mismatch
A Contract Mismatch occurs when market or execution data is applied under the wrong resolved contract identity.

19.6 Projection Drift
Projection Drift occurs when the stored or displayed projection differs from the result produced by replaying the authoritative events.
Projection drift is a defect.

20. Required Naming Standard
Every future field or event should make ownership clear.
Preferred:
rejection_step2_confirmed_at
continuation_step2_confirmed_at
rejection_boundary
continuation_boundary
parent_rejection_lifecycle_id
step4_upstream_step2_event_id

Avoid:
step2_time
boundary
current_confirmed
active_leg
last_step
state

Generic fields create accidental cross-lifecycle overwrites.

21. Binding Interpretation Rules
When two terms appear similar, apply these rules:
Candidate is not confirmed.

Ready is not confirmed.

Eligible is not created.

Created is not confirmed.

Failure is not automatically termination.

Termination is sticky.

Projection is not source truth.

Rejection is not continuation.

Logical symbol is not execution contract.

Missing is not stale.

A numerical match does not establish shared ownership.

A displayed value does not establish authority.


22. Foundational Vocabulary Standard
Every lifecycle fact must answer:
What is it?

Who owns it?

Which lifecycle does it belong to?

Which session does it belong to?

What event created it?

Can it still change?

What event may legally follow it?

Any field that cannot answer those questions is architecturally ambiguous and must not become authoritative.
