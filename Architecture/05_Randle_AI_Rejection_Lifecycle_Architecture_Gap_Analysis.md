Randle AI Architecture Gap Analysis
Rejection Lifecycle Through Step 4
Version: 1.0
Document Type: Architecture Comparison and Decision Framework
Status: Architecture Decision Document
Authority: Subordinate to the Randle AI Constitution, Lifecycle Vocabulary, Lifecycle Engine Specification, and canonical lifecycle specifications
Scope: Rejection Step 2 through Rejection Step 4 and the minimum continuation-eligibility handoff
Boundary: Continuation concepts are referenced only for rejection-state isolation and the continuation-eligibility handoff; downstream continuation lifecycle behavior and implementation are outside scope.
Implementation Changes Authorized: None

1. Purpose
This document compares:
the current production Entry Agent architecture;
the proposed Randle AI lifecycle architecture;
the established trading behavior that must be preserved.
Its purpose is to determine which differences require:
an implementation change;
a specification correction;
a terminology clarification;
additional proof before a decision;
no action.
This document does not authorize code changes.
It creates the decision record that must exist before implementation work begins.

2. Evidence Sources
This analysis uses:
the [Current Production Ground Truth Audit](Audits/01_Randle_AI_Current_Production_Ground_Truth_Audit.md);
the Randle AI Constitution;
the Randle AI Lifecycle Vocabulary;
the Randle AI Lifecycle Engine Specification;
the Randle AI Rejection Step 2 Lifecycle Specification;
the draft Randle AI Rejection Step 4 Lifecycle Specification;
established live, replay, and regression observations.
The production audit established that the live system is primarily a disk-loaded, root-scoped snapshot engine rather than an in-memory lifecycle registry. Each pass loads state, evaluates the lifecycle, constructs projections, and optionally persists selected state.

3. Decision Classifications
Each gap SHALL be assigned one of the following decisions.
KEEP PRODUCTION
The current implementation represents the established trading rule and should be preserved.
The specification must be updated to describe it accurately.
CHANGE IMPLEMENTATION
The current behavior creates lifecycle corruption, nondeterminism, unsafe mutation, or an architectural violation independent of trading-rule interpretation.
CLARIFY SPECIFICATION
The production behavior and architectural intent may already agree, but terminology or representation differs.
PROVE BEFORE DECISION
The correct choice depends on a trading-rule determination, archived replay evidence, or additional implementation tracing.
DEFER
The issue is outside the current Step 2-through-Step 4 boundary.

4. Governing Principle
Trading-rule behavior and lifecycle architecture must be separated.
A current behavior SHALL NOT be changed merely because it uses a different internal representation.
A current behavior SHALL be changed when it permits:
false confirmation;
backward lifecycle movement;
duplicate advancement;
stale-state overwrite;
out-of-order confirmation;
restart divergence;
cross-session contamination;
read-side mutation;
historical-state destruction.

5. Production Model Versus Target Model
5.1 Production model
The current implementation uses:
one mutable state record per normalized root symbol;
implicit rejection ownership;
duplicated Step 2, Step 4, lane, and trade-state fields;
snapshot-based persistence;
status-driven lifecycle execution;
current-state replacement rather than immutable lifecycle history.
5.2 Target model
The proposed architecture uses:
explicit lifecycle identity;
explicit session and contract identity;
explicit parent-child relationships;
frozen lifecycle-owned snapshots;
monotonic legal transitions;
terminal-state protection;
deterministic persistence and replay;
read-only projections.
5.3 Architectural objective
The target is not necessarily to replace the entire production engine.
The immediate objective is to introduce sufficient identity, ownership, immutability, ordering, and persistence guarantees to make existing trading behavior safe and deterministic.

6. Gap 1 — Rejection Lifecycle Identity
Production
Rejection identity is implicit.
It is represented through a combination of:
root symbol;
activation timestamp;
liquidity owner;
direction;
Candle A;
boundaries;
current mutable state.
There is no explicit rejection lifecycle ID that consistently owns both Rejection Step 2 and Rejection Step 4 phases.
Target
Every rejection lifecycle has:
a stable lifecycle ID;
a session ID;
a symbol and contract identity;
an immutable Step 2 event reference for the Step 4 phase;
a root lifecycle ID.
Risk
Without explicit identity:
a new rejection can replace an earlier rejection;
continuation may inherit from an ambiguous parent;
replay and restart cannot prove object continuity;
multiple fields may describe different versions of the same rejection;
historical truth is difficult to retain.
Decision
CHANGE IMPLEMENTATION
Required direction
Introduce stable rejection identity without changing trading-rule evaluation.
At minimum:
rejection_lifecycle_id
session_id
root_symbol
resolved_contract
step2_confirmation_time
owner_identity
direction

The identity may initially be added to the existing snapshot architecture rather than requiring a complete event-sourced redesign.

7. Gap 2 — Step 2-to-Step 4 Phase Ownership and Event Reference
Production
The parent relationship is implicit through:
Step 2 Candle A;
Step 2.5 initial Candle A;
owner and group;
direction;
reference liquidity;
Step 4 window start.
Step 4 has no explicit reference to the exact Step 2 confirmation event.
Target
Rejection Step 4 is a phase within the same Rejection Lifecycle as its confirmed Step 2 and must reference that exact Step 2 confirmation event.
Risk
An implicit phase/event relationship permits:
reattachment to a newer owner;
anchor replacement;
session mixing;
contract mixing;
inability to prove which Step 2 authorized Step 4.
Decision
CHANGE IMPLEMENTATION
Required direction
Step 4 SHALL persist:
rejection_lifecycle_id
step2_event_id
step2_confirmation_time
step2_owner_identity
lifecycle_direction
lifecycle_session_id
lifecycle_contract

The shared lifecycle identity and exact Step 2 event reference SHALL remain unchanged after Step 4 phase initialization.

8. Gap 3 — Count Model
Production
The implemented Step 4 window permits evaluation at:
Count 1;
Count 2;
Count 3;
Count 4;
potentially Count 5 or later in a static-stack branch.
Count 0 is the Step 2 confirmation candle.
Prior draft conflict
Before the Architecture Documentation Release v1.0 cleanup, the Step 4 draft stated:
Count 0 = Step 2 confirmation;
Count 1 = observation only;
Count 2 = sole Step 4 evaluation;
no Count 3 or later evaluation.
Conflict
This is a direct trading-rule conflict, not merely an architectural representation difference.
Decision
PROVE BEFORE DECISION
Required proof
Before changing code or finalizing the specification, establish the authoritative Step 4 rule:
Can Count 1 confirm?
Is Count 2 the sole evaluation candle?
Is there a four-candle participation window?
Are Counts 3 and 4 valid retry candles?
Is active Candle A allowed to roll after Count 2?
Is Count 5+ ever intentionally valid?
Current status
The current Step 4 specification SHALL remain draft and noncanonical until this trading-rule conflict is resolved.
No Count-window code change is authorized.
The current Step 4 draft removes those Count-window assertions and leaves the rule unresolved.

9. Gap 4 — Count Representation
Production
Counts are stored as fields, candidate collections, and window indexes.
They are not individual enum states.
Target
The draft Step 4 transition diagram represents Count 0 and Count 1 as if they were formal states.
Analysis
The trading engine does not require counts to be enum states.
A deterministic count field tied to unique candle identity is sufficient.
Decision
CLARIFY SPECIFICATION
Specification correction
The final specification should distinguish:
lifecycle state;
evaluation count;
candle identity;
public display status.
Counts SHALL be lifecycle checkpoints, not necessarily states.

10. Gap 5 — Meaning of READY
Production
Internal READY means Step 4 evaluation succeeded.
The public projection maps it to CONFIRMED.
Prior draft conflict
The pre-cleanup draft defined STEP4_READY as a transient state immediately before Count 2 evaluation. The current draft defers READY meaning and timing pending an authorized rule decision.
Conflict
The same term describes two different lifecycle moments.
Decision
KEEP PRODUCTION
Required correction
Do not redefine the established internal READY state during the current architecture phase.
The Lifecycle Vocabulary should state:
Internal READY = Step 4 successfully completed.
Public canonical label = Step 4 Confirmed.

If a pre-evaluation state is needed, it must use a different term, such as:
EVALUATION_ELIGIBLE
COUNT_WINDOW_OPEN
READY_FOR_EVALUATION

No new pre-evaluation state is required unless implementation evidence shows it is useful.

11. Gap 6 — Failure, Expiration, and Termination
Production
The engine uses:
WAIT for retryable participation misses;
TERMINATED for structural failure, invalidation, or window exhaustion;
Step 7 termination mechanics for terminal failure.
There is no clean separate FAILED and EXPIRED lifecycle enum.
Prior draft conflict
The pre-cleanup draft distinguished:
Step 4 Failed;
Step 4 Expired.
Analysis
Separate terminal enums are not required if:
the terminal reason is explicit;
retry behavior is deterministic;
the lifecycle cannot reopen;
the operator projection uses canonical language.
Decision
CLARIFY SPECIFICATION
Required direction
The final Step 4 specification should allow:
terminal_status = TERMINATED
terminal_reason = CONFIRMATION_FAILED
terminal_reason = WINDOW_EXPIRED
terminal_reason = STRUCTURAL_INVALIDATION

The distinction should live in reason codes unless there is a demonstrated need for separate states.

12. Gap 7 — Frozen Step 2 Anchor
Production
The Step 2 confirmation candle and owner are generally retained.
However, Step 4 may replace its active Candle A with a deeper participation extreme beginning at later counts.
Prior draft conflict
The pre-cleanup draft treated the Step 2 anchor and Step 4 Candle A as one permanently frozen object. The current draft leaves Candle A replacement unresolved.
Conflict
The term “anchor” is overloaded.
Production contains at least two possible anchor concepts:
Step 2 confirmation anchor;
Step 4 active participation anchor.
Decision
CLARIFY SPECIFICATION
Required correction
Define both separately:
Step 2 Confirmation Anchor
The immutable Step 2 confirmation candle and parent identity.
Step 4 Participation Anchor
The candle used by the Step 4 participation structure, which may or may not be permitted to roll according to the established trading rule.
The specification SHALL NOT prohibit Step 4 participation-anchor replacement until the trading rule is proven.

13. Gap 8 — Rejection Boundary
Production
Several boundaries exist:
close boundary;
stack extreme;
extreme boundary;
wick boundary extreme;
rejection boundary;
Step 2-to-Step 4 50% line;
continuation reference boundary.
Step 4 does not consistently consume one uniquely named “rejection boundary.”
Target
The lifecycle specification refers to one frozen rejection boundary.
Risk
A single ambiguous term can cause Codex to freeze or transmit the wrong price.
Decision
CLARIFY SPECIFICATION
Required boundary dictionary
The canonical vocabulary must define, at minimum:
liquidity_level_price
step2_confirmation_boundary
step2_close_boundary
step2_extreme_boundary
step2_wick_boundary
step4_50_percent_line
step4_participation_anchor
continuation_reference_boundary
continuation_wick_boundary

Each Step 4 rule SHALL reference the exact boundary name it uses.

14. Gap 9 — Sticky Step 4 Termination
Production
The live wrapper often preserves completed Step 4 state.
However:
the raw engine can reprocess a completed Step 4;
observational fields continue changing;
continuation can replace the shared Step 4 record;
session/context replacement can remove terminal state.
Target
Terminal Step 4 history is permanently immutable.
Decision
CHANGE IMPLEMENTATION
Required direction
Terminal protection must exist inside the authoritative Step 4 engine, not only in wrapper logic.
At minimum:
completed rejection Step 4 cannot return to WAIT;
terminal structural fields cannot be rewritten;
continuation cannot replace rejection Step 4;
resets cannot delete archived terminal truth;
observational fields must be separated from terminal lifecycle fields.
This change must preserve the established Count-window and confirmation rule.

15. Gap 10 — Rejection-State Overwrite
Production
One mutable per-root Step 4 object is reused.
Continuation can replace the raw rejection Step 4 record.
Historical rejection truth survives only partially in lane or trade-state projections.
Target
Rejection and continuation are distinct lifecycle records.
Decision
CHANGE IMPLEMENTATION
Required direction
Separate at minimum:
rejection_step4
continuation_step4

or:
lifecycles.rejection.step4
lifecycles.continuation.step4

Continuation SHALL reference the completed rejection record rather than replace it.

16. Gap 11 — Continuation-Eligibility Handoff
Production
Continuation eligibility is created in two representations:
same-pass derived continuation lane;
later persisted Step 2.5 eligibility fields reconstructed from trade state.
The two representations may not become durable at the same moment.
Target
Continuation eligibility is created atomically from confirmed Rejection Step 4.
Risk
The system may temporarily show:
completed rejection;
eligible continuation lane;
no matching durable raw Step 4 confirmation;
incomplete persisted handoff.
Decision
CHANGE IMPLEMENTATION
Required direction
Create one authoritative eligibility record atomically with the durable Step 4 confirmation checkpoint.
Projections may continue to display lanes, but they SHALL derive from that record.
Minimum fields:
eligibility_id
source_rejection_lifecycle_id
created_at
step4_confirmation_time
owner_identity
direction
continuation_reference_boundary
continuation_wick_boundary
session_id
contract

This change stops at eligibility creation and does not define downstream continuation behavior.

17. Gap 12 — Duplicate Candle Handling
Production
Step 4 candidate keys are tuples in memory but become lists after JSON serialization.
The same candle can therefore advance the count again after restart.
Candidate identity also includes OHLC, allowing the same timestamp with revised OHLC to appear as a new candidate.
Target
One completed candle advances the lifecycle at most once.
Decision
CHANGE IMPLEMENTATION
Required direction
Canonical candle identity should be stable across serialization.
At minimum:
symbol
contract
timeframe
candle_close_timestamp
session_id

OHLC may be retained for audit but SHALL NOT be the sole duplicate identity.
A corrected same-timestamp candle requires an explicit correction policy; it must not silently count as another lifecycle candle.

18. Gap 13 — Out-of-Order Events
Production
Step 2 and Step 4 generally process arrival order.
A Step 4 candidate may have a timestamp earlier than its upstream Step 2 confirmation event and still confirm.
Target
A Step 4 phase event cannot precede its upstream Step 2 confirmation event, and accepted event order is monotonic.
Decision
CHANGE IMPLEMENTATION
Required direction
Before Step 4 candidate registration:
candidate_timestamp > step2_confirmation_timestamp
candidate_timestamp > last_accepted_step4_candidate_timestamp
candidate_session_id == lifecycle_session_id

Invalid chronology SHALL be rejected or recorded for audit.
This is an architecture fix and does not alter the market-pattern rule.

19. Gap 14 — Stale Event Handling
Production
There is partial stale-session sanitization, but no universal monotonic event gate.
Delayed context and prior-session payloads can replace current lifecycle context.
Target
Older events cannot replace newer authoritative state.
Decision
CHANGE IMPLEMENTATION
Required direction
Add monotonic guards for:
session context;
TV lock session;
Step 2 candles;
Step 4 candidates;
persistence versions;
contract identity.
A prior-session payload SHALL never replace a current-session lock.

20. Gap 15 — Read-Only Endpoint Behavior
Production
GET /entry/status runs lifecycle processing, performs a narrow checkpoint write, and appends logs.
Command Center polling therefore functions as a lifecycle scheduler.
Target
Read-only endpoints construct projections only.
Decision
CHANGE IMPLEMENTATION
Required direction
Separate:
authoritative lifecycle processor
read-only status projection

The processor must run independently of GET requests.
A status request SHALL not:
create Step 2;
advance Step 4;
persist lifecycle state;
create eligibility;
append authoritative decision records.
This is a major architecture change and should not be combined casually with trading-rule changes.

21. Gap 16 — Persistence Atomicity
Production
Lifecycle state uses direct JSON writes.
There is:
no schema version;
no lifecycle revision;
no compare-and-swap protection;
no corruption recovery beyond loading an empty object.
Target
Committed transitions are atomic and versioned.
Decision
CHANGE IMPLEMENTATION
Required direction
Introduce:
atomic temporary write and replace;
schema version;
state revision;
last committed event identity;
corruption detection;
recovery behavior that does not silently reseed.
A full database migration is not required for the first hardening phase.

22. Gap 17 — Restart Restoration
Production
Restart occurs through ordinary load-and-evaluate behavior.
Candidate identity changes across JSON serialization, allowing a committed candle to be counted again.
Missing or invalid state may reseed from current inputs.
Target
Restart restores the exact committed lifecycle.
Decision
CHANGE IMPLEMENTATION
Required direction
Normalize persisted candidate identities and validate restored state before processing a new event.
Restart SHALL preserve:
parent identity;
count;
last accepted candle;
terminal state;
frozen inputs;
eligibility handoff.

23. Gap 18 — Session Identity and Rollover
Production
Session identity is stored in context and reset fields, not lifecycle identity.
Active state is cleared or replaced during session/context changes.
Historical lifecycle truth is not retained inside the active state document.
Target
Every lifecycle belongs to one immutable session namespace.
Decision
CHANGE IMPLEMENTATION
Required direction
Add session identity to every active rejection record.
Rollover should:
close or archive the prior active lifecycle;
initialize a new session record;
preserve prior terminal truth;
reject delayed prior-session replacement.
The first implementation may archive compact lifecycle records rather than introducing a full historical event store.

24. Gap 19 — Contract Identity
Production
State is keyed by root.
Contracts sharing the same root use the same lifecycle record.
Target
The lifecycle preserves both root and authoritative resolved contract.
Decision
CHANGE IMPLEMENTATION
Required direction
Retain root-level strategy ownership while storing the exact contract associated with:
upstream Step 2 confirmation event;
accepted candles;
execution state;
eligibility creation.
Contract rollover must not silently alter an active lifecycle’s market identity.

25. Gap 20 — Replay Inputs
Production
Archived bars are used, but replay injects current TradingView context and current or fallback ATR.
Replay is therefore not historically self-contained.
Target
Replay reproduces lifecycle output from archived historical inputs.
Decision
CHANGE IMPLEMENTATION
Required direction
Archive and replay:
session liquidity context;
relevant TV lock data;
ATR input;
contract mapping;
configuration version.
Until then, replay results must be labeled as:
bars replayed under current context

rather than authoritative historical reconstruction.

26. Gap 21 — Projection as Restoration Authority
Production
Rejection lanes, continuation lanes, and trade state are derived projections, but full persistence later uses them as restoration inputs.
Target
Projections are derived from authoritative lifecycle state.
Decision
CHANGE IMPLEMENTATION
Required direction
Define one authoritative state source.
Lanes and public status may be persisted for observability, but they SHALL NOT override or reconstruct newer authoritative lifecycle state unless explicitly versioned and validated.

27. Gap 22 — Root-Scoped Snapshot Architecture
Production
The system uses one root-scoped snapshot loaded and rebuilt each pass.
Proposed target
The Lifecycle Engine Specification suggests discrete lifecycle objects and transition history.
Analysis
A full replacement with an event-sourced registry is not immediately necessary.
The current snapshot architecture can be hardened by adding:
identity;
versioning;
lineage and upstream-event linkage;
frozen records;
transition guards;
archived terminal summaries.
Decision
DEFER
Constraint
Do not undertake a wholesale event-sourcing rewrite during the Step 2-through-Step 4 stabilization phase.
Strengthen the existing model first.

28. Decisions Summary
Area
Decision
Explicit rejection identity
CHANGE IMPLEMENTATION
Explicit Step 2 phase/event reference
CHANGE IMPLEMENTATION
Count 1–4 behavior
PROVE BEFORE DECISION
Count fields vs enum states
CLARIFY SPECIFICATION
Internal READY meaning confirmed
KEEP PRODUCTION
Failure vs expiration enums
CLARIFY SPECIFICATION
Step 2 anchor vs Step 4 participation anchor
CLARIFY SPECIFICATION
Boundary terminology
CLARIFY SPECIFICATION
Sticky terminal protection
CHANGE IMPLEMENTATION
Rejection/continuation state separation
CHANGE IMPLEMENTATION
Atomic continuation eligibility
CHANGE IMPLEMENTATION
Duplicate handling
CHANGE IMPLEMENTATION
Out-of-order handling
CHANGE IMPLEMENTATION
Stale-event/session protection
CHANGE IMPLEMENTATION
GET endpoint mutation
CHANGE IMPLEMENTATION
Persistence atomicity/versioning
CHANGE IMPLEMENTATION
Restart determinism
CHANGE IMPLEMENTATION
Session identity and archival
CHANGE IMPLEMENTATION
Contract identity
CHANGE IMPLEMENTATION
Replay self-containment
CHANGE IMPLEMENTATION
Projection authority
CHANGE IMPLEMENTATION
Full event-sourced rewrite
DEFER


29. Draft Protection Applied for Architecture Documentation Release v1.0
The Step 4 draft removes the assertion that Count 2 is the sole evaluation candle and removes Count 0 and Count 1 from a formal state-transition diagram.
READY meaning, failure, expiration, retry, termination, Candle A replacement, and the terminal window remain unresolved and are not decided by the draft.
The draft distinguishes the immutable Step 2 reference from any unresolved Step 4 participation anchor and requires exact boundary names without selecting a trading-rule value.
The current specification scope ends at the minimum continuation-eligibility handoff and does not define downstream continuation behavior.

30. Immediate Implementation Hardening Candidates
The following corrections can be justified without resolving the Step 4 Count-window trading rule:
stable serialized candle identity;
rejection lifecycle ID;
exact Step 2 event ID on the Step 4 phase;
timestamp monotonicity;
rejection/continuation Step 4 state separation;
terminal-state guard inside the core Step 4 engine;
atomic persistence;
schema and revision fields;
session and contract identity;
prior-session replacement protection;
read-only endpoint separation;
atomic continuation-eligibility record.
These changes must be designed to preserve current market-pattern and Count-window behavior unless separately authorized.

31. Required Trading-Rule Decision
Before Step 4 can become canonical, the following question must be answered:
What is the exact authorized Step 4 evaluation window after the Step 2 confirmation candle?
The answer must explicitly define:
Count 0:
Count 1:
Count 2:
Count 3:
Count 4:
Count 5+:
Candle A replacement:
Retry behavior:
Terminal window:

This determination should be based on:
the original trading blueprint;
established user intent;
known successful live examples;
archived replay checkpoints;
current tests;
any prior explicit rule decision.
No architecture document or code patch should silently decide this trading rule.

32. Recommended Sequence
Stage 1 — Resolve Step 4 Rule
Establish the true Count-window and Candle A behavior.
Stage 2 — Correct Specifications
Update:
Lifecycle Vocabulary;
Rejection Step 4 Lifecycle Specification;
relevant portions of the Lifecycle Engine Specification.
Stage 3 — Architecture-Only Hardening
Implement identity, ordering, persistence, terminality, session, contract, endpoint, and handoff protections without changing the Step 4 trading rule.
Stage 4 — Regression and Replay
Run:
known archived rejection cases;
duplicate tests;
restart tests;
stale and out-of-order tests;
endpoint nonmutation tests;
session rollover tests.
Stage 5 — Live Validation
Validate Rejection Step 2 and Step 4 before specifying or modifying downstream continuation behavior.

33. Final Conclusion
The current Entry Agent contains established and sophisticated rejection logic, but the lifecycle architecture remains implicit, root-scoped, mutable, and distributed across engine state, lanes, trade state, persistence, and public projections.
The correct path is not to replace the production system wholesale.
The correct path is to:
prove the actual Step 4 trading rule;
correct the draft specification;
preserve established trading behavior;
harden identity, ownership, ordering, terminality, persistence, restart, session, contract, endpoint, and handoff behavior;
validate the rejection lifecycle through Step 4 before proceeding downstream.
No Step 5 or continuation-lifecycle specification should be made canonical until this foundation is proven.
