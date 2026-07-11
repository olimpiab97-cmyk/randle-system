Randle AI Lifecycle Engine Specification
Version: 1.0
Document Type: Core Architecture Specification
Status: Canonical
Authority: Subordinate to the Randle AI Constitution and Randle AI Lifecycle Vocabulary
Scope: Universal lifecycle-engine mechanics for rejection, continuation, entry, management, and terminal decision lifecycles
Release Boundary: Universal constraints may reference continuation concepts, but this release does not define canonical continuation lifecycle behavior after Continuation Eligibility Creation and does not authorize continuation implementation.

1. Purpose
The Randle AI Lifecycle Engine is the shared architectural system responsible for creating, advancing, freezing, terminating, persisting, restoring, replaying, and exposing all Randle AI trading lifecycles.
This specification defines the universal lifecycle rules inherited by all canonical specialized lifecycle specifications.
It governs:
lifecycle identity;
lifecycle ownership;
parent-child relationships;
state transitions;
immutable and mutable data;
frozen snapshots;
event ordering;
duplicate-event handling;
stale-event handling;
out-of-order-event handling;
persistence;
restart restoration;
deterministic replay;
session rollover;
read-only projections;
terminal-state protection;
auditability;
regression requirements.
This specification does not define:
liquidity identification;
rejection qualification;
continuation qualification;
candle-pattern rules;
ATR calculations;
directional bias;
confirmation conditions;
entry conditions;
risk management;
target placement;
trade execution.
Those rules remain defined by their respective trading-rule and lifecycle specifications.

2. Governing Authority
Lifecycle behavior SHALL follow this authority order:
1. Randle AI Constitution
2. Randle AI Lifecycle Vocabulary
3. Randle AI Lifecycle Engine Specification
4. Canonical Lifecycle Specifications
5. Architecture Decision Documents
6. Implementation
7. Tests
8. Operator projections
Only explicitly approved canonical lifecycle specifications occupy item 4. Draft specifications and audit documents do not enter or alter this authority order.
A lower authority SHALL NOT contradict, weaken, bypass, or reinterpret a higher authority.
When implementation behavior conflicts with a canonical specification, the implementation is defective.
Observed runtime behavior does not become authoritative merely because it currently exists in code.

3. Architectural Principle
Every Randle AI decision process SHALL be represented as an explicit lifecycle.
A lifecycle SHALL have:
a unique identity;
a symbol;
a trading session;
a lifecycle type;
a direction where applicable;
a creation event;
a current state;
an ordered transition history;
defined mutable fields;
defined immutable fields;
an optional parent;
zero or more children;
a terminal or nonterminal status;
persistence and replay semantics.
No lifecycle may exist solely as an undocumented collection of unrelated flags.
No operator-facing status string may substitute for authoritative lifecycle state.

4. Lifecycle Object
Each lifecycle SHALL be represented by one authoritative lifecycle object.
At minimum, the object SHALL contain:
lifecycle_id
lifecycle_type
symbol
root_symbol
resolved_contract
session_id
direction
parent_lifecycle_id
root_lifecycle_id
state
created_at
updated_at
last_processed_event_time
terminal_at
terminal_reason
version
immutable_inputs
mutable_state
transition_history

Fields that do not apply to a specific lifecycle may be null, but their absence SHALL be intentional and schema-valid.

5. Lifecycle Identity
5.1 Unique identity
Every lifecycle SHALL have one unique, stable lifecycle_id.
The identifier SHALL remain unchanged for the full lifetime of the lifecycle, including:
live processing;
persistence;
restart;
replay;
read-only projection;
archival analysis.
A lifecycle SHALL NOT receive a new identity merely because the process restarts or the lifecycle is reloaded.
5.2 Identity composition
The lifecycle identity SHALL be sufficient to distinguish:
symbol;
session;
lifecycle type;
lifecycle instance;
parent lineage.
The exact identifier format is an implementation decision, provided uniqueness and stability are guaranteed.
5.3 No identity reuse
A terminated lifecycle ID SHALL never be reused.
A new setup, even at the same liquidity level and direction, SHALL create a new lifecycle identity when the governing specification permits a new lifecycle.

6. Session Identity
Each lifecycle SHALL belong to exactly one session_id.
The session identity SHALL be based on the canonical Randle AI trading-session definition.
A lifecycle SHALL NOT span multiple sessions unless a specialized canonical specification explicitly allows it.
Session identity SHALL be frozen at lifecycle creation.
A later system clock change, restart, delayed event, or stale payload SHALL NOT reassign the lifecycle to another session.

7. Symbol Identity and Contract Resolution
Each lifecycle SHALL preserve both:
the canonical root symbol, such as NQ or YM;
the resolved execution contract used by the authoritative live state.
Contract resolution SHALL follow the authoritative live execution state and canonical symbol-resolution rules.
Shared recent-bar files, ATR files, cached market snapshots, or front-month assumptions SHALL NOT independently override the execution contract associated with an active lifecycle.
A lifecycle SHALL NOT silently migrate from one futures contract to another.
A contract rollover SHALL require explicit lifecycle-safe resolution behavior.

8. Lifecycle Domains and Phase Types
Each independent trading lifecycle SHALL declare one immutable lifecycle type or domain, such as REJECTION or CONTINUATION.

Lifecycle phase types or phase identifiers identify stages within that lifecycle. Examples include:
Rejection Step 2
Rejection Step 4
Rejection Step 5
Rejection Step 6
Continuation Step 2
Continuation Step 4
Continuation Step 5
Continuation Step 6
Trade Management
Risk Reset
Entry Decision
A phase identifier does not create an independent lifecycle, lifecycle object, or lifecycle ID. Rejection Step 2 and Rejection Step 4 are stages of one Rejection Lifecycle and share its lifecycle ID. Event records may preserve the phase identifier that produced them.

The Lifecycle Engine SHALL treat the lifecycle domain/type as immutable. A rejection lifecycle SHALL NOT be converted into a continuation lifecycle by changing that field. The Rejection Step 5, Rejection Step 6, and continuation phase names above are taxonomy examples only; they do not specify or canonicalize behavior outside the current specialized specification boundary.

9. Parent-Child Relationships
Steps or phases inside one lifecycle are not parent and child lifecycles. In particular, Rejection Step 4 references the exact Rejection Step 2 confirmation event within the same Rejection Lifecycle. This section applies only when a distinct lifecycle is created under an approved canonical specification.

9.1 Parent ownership
A child lifecycle SHALL reference exactly one direct parent when a parent is required by its canonical specialized specification.
A parent reference SHALL include:
parent_lifecycle_id;
parent lifecycle type;
parent session;
parent symbol;
parent direction;
parent terminal or qualifying transition that authorized child creation.
9.2 Root lineage
Every lifecycle lineage SHALL identify one root_lifecycle_id.
For a root lifecycle:
root_lifecycle_id = lifecycle_id

For a child lifecycle:
root_lifecycle_id = parent.root_lifecycle_id

9.3 Parent immutability
Once assigned, a parent SHALL NOT be replaced.
A child SHALL NOT be reparented to a newer or more convenient lifecycle.
9.4 Parent qualification
A child lifecycle SHALL only be created when the parent reaches the exact qualifying state defined by the child’s canonical specialized specification.
The existence of similar market conditions SHALL NOT substitute for the required parent state.
9.5 Parent termination
A child’s behavior following parent termination SHALL be explicitly defined by the canonical specialized lifecycle specification.
The engine SHALL NOT infer that every parent termination automatically terminates every child.

10. Lifecycle State
Each lifecycle SHALL have exactly one authoritative current state.
The current state SHALL be derived from valid recorded transitions, not from loosely combined flags.
The engine MAY expose convenience booleans, but those booleans SHALL be projections of the authoritative state.
Examples:
is_confirmed
is_terminal
is_failed
is_expired
is_active

Convenience fields SHALL NOT independently control lifecycle behavior.

11. State Transition Model
11.1 Transition requirement
A lifecycle state may change only through an explicit legal transition.
Each transition SHALL record:
transition_id
lifecycle_id
from_state
to_state
event_id
event_time
processed_at
reason_code
source
lifecycle_version_before
lifecycle_version_after

11.2 Legal transitions
Legal transitions SHALL be enumerated by the canonical specialized lifecycle specification.
Any transition not explicitly legal SHALL be prohibited.
11.3 Atomicity
A transition and its required data updates SHALL occur atomically.
The engine SHALL NOT expose a state where:
the state has advanced but required frozen fields are missing;
a confirmation exists without a confirmation timestamp;
a terminal state exists without a terminal reason;
a child exists before its parent-authorizing transition is durable.
11.4 Monotonic advancement
Lifecycle progression SHALL be monotonic.
A lifecycle SHALL NOT move backward to an earlier state.
11.5 Single-transition evaluation
One event SHALL NOT cause multiple incompatible transitions for the same lifecycle.
When one event legitimately causes a sequence of transitions, the sequence SHALL be deterministic, ordered, and defined by specification.

12. Mutable and Immutable Data
12.1 Immutable data
Immutable lifecycle data SHALL include, at minimum:
lifecycle ID;
lifecycle type;
symbol identity;
session identity;
direction once established;
parent identity;
root identity;
creation timestamp;
frozen anchors;
frozen boundaries;
confirmation candle identity after confirmation;
confirmation timestamp after confirmation;
terminal timestamp after termination;
terminal reason after termination.
12.2 Mutable data
Mutable data may include:
current state;
count progress;
last processed event;
temporary evaluation data;
nonterminal wait reason;
current lifecycle version.
Mutable fields SHALL become immutable when the canonical specialized specification freezes them.
12.3 No silent mutation
Every authoritative mutation SHALL correspond to:
a processed event;
a legal transition;
a version increment;
an auditable reason.

13. Frozen Snapshots
13.1 Freeze event
When a canonical specialized lifecycle specification requires an anchor, boundary, reference candle, direction, or other input to freeze, the engine SHALL capture an immutable snapshot at the exact qualifying transition.
13.2 Snapshot ownership
The lifecycle SHALL own its frozen snapshot.
It SHALL NOT depend on a later lookup into mutable global state to reconstruct what the value “must have been.”
13.3 Snapshot inheritance
A child lifecycle may inherit frozen values from its parent.
Inherited values SHALL be copied or immutably referenced in a way that prevents later mutation.
13.4 No recomputation
After freezing, a value SHALL NOT be recalculated from newer candles, current ATR, revised liquidity data, current prices, or reconstructed runtime assumptions.

14. Event Model
Every lifecycle change SHALL be driven by a canonical event.
Events may include:
completed market candle;
session open;
session close;
Step confirmation;
expiration trigger;
parent transition;
execution event;
risk event;
restart restoration event;
rollover event.
Each event SHALL include:
event_id
event_type
symbol
session_id
event_time
source_time
received_at
source
payload_hash
sequence_metadata


15. Event Identity and Idempotency
15.1 Unique event identity
Each canonical event SHALL have a stable event identity.
Where an upstream source does not provide one, the engine SHALL construct a deterministic identity from canonical event attributes.
15.2 Duplicate detection
An event already applied to a lifecycle SHALL not be applied again.
15.3 Idempotent result
Reprocessing the same event SHALL produce no lifecycle change after its first valid application.
Duplicate processing SHALL NOT:
advance a count twice;
create two confirmations;
create duplicate children;
overwrite timestamps;
append contradictory transition records;
increment lifecycle state more than once.

16. Event Ordering
16.1 Authoritative ordering
Lifecycle events SHALL be ordered using canonical market-event time and required sequence metadata.
Processing arrival time SHALL NOT automatically determine lifecycle order.
16.2 Equal timestamps
Where multiple events share a timestamp, the engine SHALL use a deterministic tie-breaking rule.
16.3 No arrival-order dependence
Identical historical events processed in different arrival order SHALL produce the same final lifecycle state, provided the complete valid event set is available and the canonical specialized specification permits reordering.

17. Stale Events
An event is stale when it predates the lifecycle’s current authoritative processing boundary and cannot legally change the current state.
A stale event SHALL NOT:
regress state;
alter frozen data;
replace a confirmation;
replace a terminal reason;
modify a child relationship;
reopen an expired lifecycle;
create a late duplicate child.
The engine SHALL either:
ignore the stale event; or
record it as rejected for audit.
The chosen behavior SHALL be deterministic.

18. Out-of-Order Events
18.1 Nonterminal lifecycle
For a nonterminal lifecycle, the engine may buffer or reorder out-of-order events when necessary to preserve canonical sequence.
18.2 Terminal lifecycle
An out-of-order event SHALL NOT modify a terminal lifecycle.
18.3 Late discovery
If a late event reveals that prior processing lacked required market data, the engine SHALL NOT silently rewrite live history.
Any correction mechanism SHALL be explicit, auditable, and separated from ordinary live lifecycle advancement.
18.4 Replay distinction
Historical replay may reconstruct from the complete ordered event set.
Live correction and offline replay SHALL not be conflated.

19. Lifecycle Counts
Where a canonical specialized specification uses Count 0, Count 1, Count 2, or another count sequence:
each count SHALL correspond to one unique qualifying completed candle;
the count SHALL advance only once per candle;
duplicate data SHALL not advance the count;
incomplete candles SHALL not advance the count;
stale candles SHALL not advance the count;
out-of-session candles SHALL not advance the count;
count identity SHALL be tied to candle identity, not merely an integer variable.
A restart SHALL restore the exact previously reached count.
A status request SHALL not advance a count.

20. Confirmation Events
20.1 Single confirmation per phase and event type
Within one lifecycle, each canonical phase-specific confirmation event type SHALL be accepted at most once. Rejection Step 2 confirmation and Rejection Step 4 confirmation are distinct event types within the same Rejection Lifecycle.
20.2 Confirmation data
Each accepted confirmation event SHALL atomically freeze the fields required for its phase and event type.
At minimum:
phase identifier;
confirmation state;
confirmation candle;
confirmation timestamp;
confirmation event;
applicable anchor;
applicable boundary;
lifecycle version.
20.3 Confirmation immutability
Once a confirmation event is accepted, its frozen confirmation data SHALL NOT change.
20.4 No retroactive confirmation
A lifecycle phase SHALL NOT confirm from an event outside the legal evaluation window defined by its approved canonical specification.
Historical replay shall reproduce a valid original confirmation but SHALL NOT invent a confirmation prohibited by the trading rules.

21. Terminal States
A state is terminal when no future ordinary market event may advance or alter the lifecycle.
Terminal states may include:
Confirmed;
Failed;
Expired;
Invalidated;
Consumed;
Cancelled;
Completed.
The applicable terminal states SHALL be defined by each canonical specialized lifecycle specification.

22. Sticky Termination
All terminal states SHALL be sticky.
Once terminal:
state SHALL NOT regress;
terminal timestamp SHALL NOT change;
terminal reason SHALL NOT change;
frozen values SHALL NOT change;
future events SHALL NOT retry the lifecycle;
read-only requests SHALL NOT revive it;
restart SHALL NOT reopen it;
session rollover SHALL NOT reactivate it.
A separate future opportunity SHALL require a separate lifecycle.

23. Failure and Expiration
23.1 Distinct meanings
Failure and expiration SHALL remain semantically distinct when both exist.
Failure means an authorized evaluation occurred and the required condition was not satisfied.
Expiration means the permitted evaluation window closed without further legal advancement.
23.2 No ambiguous terminal state
A lifecycle SHALL NOT be simultaneously failed and expired unless the canonical specialized specification explicitly defines a combined representation.
23.3 Reason codes
Terminal reasons SHALL use canonical reason codes rather than uncontrolled free text.
Operator-facing text may be derived from the reason code.

24. Eligibility and Child Lifecycle Creation
24.1 Eligibility is not child creation
An eligibility record does not create a child lifecycle, child lifecycle identity, or parent-child relationship.
24.2 Atomic eligibility
When a parent transition creates only child eligibility, the engine SHALL atomically persist:
the parent transition;
the parent’s frozen prospective-child inputs;
the eligibility record.
24.3 Authorized child creation
If a future approved canonical specification separately authorizes child lifecycle creation, that creation SHALL atomically persist the child identity and parent-child relationship.
24.4 Single child creation
A duplicate parent transition SHALL NOT create duplicate children.
24.5 Child input preservation
The child SHALL inherit the exact frozen parent data required by its canonical specialized specification.
The child SHALL NOT derive those values from later global state.

25. Prevention of Lifecycle Overwrite
One lifecycle SHALL NOT overwrite another lifecycle’s authoritative state.
In particular:
continuation state SHALL NOT overwrite rejection state;
a new rejection SHALL NOT overwrite a prior rejection;
a current-session lifecycle SHALL NOT overwrite an archived prior-session lifecycle;
status projection SHALL NOT write back into authoritative state;
executor state SHALL NOT replace Entry Agent lifecycle history;
Entry Agent state SHALL NOT fabricate executor state.
Each lifecycle SHALL remain separately identifiable and historically preserved.

26. Persistence
26.1 Durable state
Every authoritative transition SHALL be persisted before it is treated as committed.
26.2 Persisted content
Persistence SHALL include:
lifecycle object;
current state;
lifecycle version;
immutable snapshot;
parent-child linkage;
transition history or sufficient event history;
last processed event identity;
terminal data;
session identity.
26.3 Atomic write
Persistence SHALL prevent partially written lifecycle state.
Atomic file replacement, transactional storage, or an equivalent durability mechanism SHALL be used.
26.4 Persistence failure
If durable persistence fails, the engine SHALL NOT falsely report that the transition committed.
26.5 No read-side persistence
Read-only operations SHALL not trigger authoritative persistence.

27. Lifecycle Versioning
Each authoritative lifecycle mutation SHALL increment a monotonic lifecycle version.
Versioning SHALL support:
stale-write detection;
duplicate-write prevention;
restart validation;
audit comparison;
projection freshness.
A write based on an older lifecycle version SHALL not overwrite a newer version.

28. Restart Restoration
28.1 Authoritative restore
After restart, the engine SHALL restore lifecycle state from durable authoritative storage.
28.2 Exact restoration
Restoration SHALL preserve:
lifecycle identity;
session identity;
state;
count;
parent linkage;
frozen data;
confirmation data;
terminal data;
last processed event;
lifecycle version.
28.3 No automatic recomputation
Restart SHALL NOT recompute an already-persisted lifecycle from mutable current market state unless an explicit recovery procedure requires replay.
28.4 Resume point
A nonterminal lifecycle SHALL resume from the exact last committed state.
28.5 Terminal restore
A terminal lifecycle SHALL restore as terminal and remain immutable.

29. Crash Consistency
The engine SHALL tolerate interruption between event receipt and lifecycle commit.
After restart, one of the following SHALL be true:
the transition was fully committed; or
the transition was not committed and may be safely reprocessed.
A partially committed lifecycle state is prohibited.

30. Deterministic Replay
30.1 Replay source
Replay SHALL use the canonical archived market-event source required by the applicable validation procedure.
Reasoning logs, UI snapshots, or operator text SHALL NOT substitute for canonical archived bars when validating candle-driven lifecycle behavior.
30.2 Deterministic result
Given:
the same canonical starting state;
the same ordered events;
the same canonical rules;
the same configuration;
replay SHALL produce the same:
lifecycle identities or deterministic equivalents;
transitions;
counts;
frozen values;
confirmations;
failures;
expirations;
children;
terminal states.
30.3 No wall-clock dependency
Replay SHALL not depend on the current system time except where explicitly simulated from event time.
30.4 No hidden live dependency
Replay SHALL not depend on:
current live prices;
current working orders;
current front-month files;
current ATR snapshots;
mutable global caches;
active network services.
All required inputs SHALL be provided by the replay environment.

31. Session Rollover
31.1 Session boundary
At canonical session rollover, the engine SHALL establish a new lifecycle namespace.
31.2 Previous-session preservation
Previous-session lifecycles SHALL remain archived and immutable.
31.3 New-session isolation
The new session SHALL NOT inherit prior-session:
active counts;
waiting states;
ready states;
stale confirmation timestamps;
trade-state flags;
last decisions;
rejection boundaries;
continuation boundaries;
unless a canonical specialized specification explicitly authorizes cross-session inheritance.
31.4 Rollover reset
Reset logic SHALL affect only fields designated as session-scoped.
Historical lifecycle records SHALL not be deleted merely to initialize a new session.
31.5 Mixed-session payloads
A payload containing a new session ID with stale prior-session lifecycle data SHALL be rejected, sanitized, or isolated.
It SHALL NOT be published as current-session state.

32. Read-Only Endpoints
32.1 Non-mutating guarantee
A read-only endpoint SHALL NOT:
run lifecycle advancement;
evaluate confirmation;
advance counts;
create child lifecycles;
change wait reasons;
update timestamps;
persist state;
consume a level;
expire a lifecycle;
invoke execution-side effects.
32.2 Projection only
Read-only endpoints SHALL construct projections from already-authoritative state.
32.3 Safe derivation
A projection may calculate display-only values provided the calculation does not alter authoritative lifecycle state.
32.4 Repeated reads
Repeated identical reads SHALL produce no lifecycle mutation.
32.5 Failure isolation
A projection failure SHALL not corrupt or alter lifecycle state.

33. Public and Operator-Facing Projections
Public status fields SHALL be projections, not lifecycle authorities.
Operator-facing simplification may expose fields such as:
Liquidity Level;
Rejection Boundary;
Continuation Boundary;
Current Step;
Wait Reason;
Confirmation Time.
Simplification SHALL NOT erase the underlying authoritative lifecycle distinction.
Public terminology SHALL conform to the canonical Lifecycle Vocabulary.
Deprecated internal names SHALL not leak into operator-facing output when the vocabulary specification prohibits them.

34. Freshness
Every projection that combines lifecycle, market, ATR, listener, or executor data SHALL preserve the independent freshness status of each source.
Stale market data SHALL NOT be presented as current merely because lifecycle data is current.
Stale lifecycle data SHALL NOT be presented as current merely because prices are current.
A read-side aggregator SHALL not merge incompatible sessions or contracts into one apparently valid snapshot.

35. Source Ownership
Each subsystem SHALL retain authority over its own domain.
Examples:
market listener owns listener feed-health and received tick freshness;
executor owns positions, orders, fills, and execution prices;
Entry Agent owns entry lifecycles and decision state;
ATR subsystem owns ATR snapshot calculation;
Command Center owns display projections only.
One subsystem SHALL NOT fabricate authoritative state belonging to another.

36. Error Handling
Lifecycle errors SHALL fail safely.
An error SHALL NOT:
falsely confirm a lifecycle;
silently skip required termination;
overwrite frozen data;
advance a count twice;
create duplicate children;
expose stale state as current;
mutate state through a read endpoint.
Errors SHALL be logged with:
lifecycle ID;
event ID;
state;
version;
session;
symbol;
error category;
attempted transition.

37. Legal Universal Operations
The following operations are universally legal when their preconditions are satisfied:
CREATE lifecycle
PROCESS new canonical event
ADVANCE through an explicitly legal transition
FREEZE an input at its canonical freeze point
CREATE an authorized child
PERSIST a committed transition
RESTORE exact persisted state
PROJECT state without mutation
ARCHIVE terminal or prior-session state
REPLAY from canonical archived inputs
IGNORE or reject duplicate and stale events


38. Universally Prohibited Operations
The following operations are prohibited:
Mutating lifecycle state from a read-only endpoint
Regressing a lifecycle to an earlier state
Changing a terminal state through ordinary market processing
Changing a frozen anchor or boundary
Replacing a lifecycle parent
Reusing a terminated lifecycle identity
Advancing a count from an incomplete candle
Advancing a count twice from one candle
Confirming more than once
Creating duplicate child lifecycles
Overwriting rejection state with continuation state
Merging lifecycles from different sessions
Silently moving an active lifecycle to another contract
Using stale cached data to replace newer authoritative state
Recomputing persisted history from current mutable state
Publishing prior-session lifecycle state as current-session state
Treating UI text as authoritative lifecycle state


39. Universal Invariants
The following invariants SHALL always hold.
39.1 Identity invariant
A lifecycle has exactly one stable identity.
39.2 Session invariant
A lifecycle belongs to exactly one session.
39.3 Type invariant
A lifecycle type never changes.
39.4 Parent invariant
A lifecycle has no more than one direct parent.
39.5 State invariant
A lifecycle has exactly one authoritative current state.
39.6 Transition invariant
Every state change is represented by one legal, auditable transition.
39.7 Monotonicity invariant
Lifecycle state never regresses.
39.8 Freeze invariant
A frozen value never changes.
39.9 Confirmation invariant
Within one lifecycle, each canonical phase-specific confirmation event type is accepted at most once.
39.10 Terminal invariant
A terminal lifecycle never reopens.
39.11 Count invariant
A qualifying candle advances a lifecycle count at most once.
39.12 Idempotency invariant
Processing the same event more than once produces no additional lifecycle effect.
39.13 Version invariant
Lifecycle version increases monotonically with authoritative mutation.
39.14 Persistence invariant
Committed state is durable and crash-consistent.
39.15 Restart invariant
Restart preserves the exact committed lifecycle.
39.16 Replay invariant
Canonical replay reproduces the same lifecycle result.
39.17 Session-isolation invariant
Prior-session state cannot become active current-session state without explicit canonical authorization.
39.18 Read-only invariant
A read operation cannot modify authoritative state.
39.19 Lineage invariant
A child’s parent and root lineage remain permanent.
39.20 Source-authority invariant
No subsystem may fabricate another subsystem’s authoritative data.

40. Minimum Engine Regression Tests
Every implementation SHALL include automated tests covering at least the following.
40.1 Lifecycle creation
creates one lifecycle with one unique identity;
assigns correct type, symbol, direction, and session;
records creation event;
sets root lineage correctly.
40.2 Parent-child linkage
creates child only after authorized parent transition;
assigns correct parent;
assigns correct root lifecycle;
prevents reparenting;
prevents duplicate child creation.
40.3 Legal transitions
allows every documented legal transition;
records transition metadata;
increments version;
persists atomically.
40.4 Prohibited transitions
rejects every undocumented transition;
prevents backward movement;
prevents terminal reopening.
40.5 Frozen values
freezes each value at the correct transition;
preserves values across later candles;
preserves values across restart;
preserves values across replay.
40.6 Duplicate events
duplicate candle does not advance count twice;
duplicate confirmation event does not reconfirm;
duplicate parent event does not create duplicate child;
duplicate event does not alter timestamps.
40.7 Stale events
stale candle does not regress state;
stale event does not replace frozen data;
stale event does not reopen terminal state;
stale prior-session data does not populate current-session status.
40.8 Out-of-order events
buffers or deterministically rejects nonterminal out-of-order events;
preserves terminal state;
produces deterministic replay result.
40.9 Persistence
committed transition survives restart;
incomplete atomic write is not loaded as valid;
stale version cannot overwrite newer version.
40.10 Restart
restores exact lifecycle ID;
restores exact state;
restores exact count;
restores parent-child linkage;
restores frozen inputs;
restores terminal state;
resumes from the next valid event.
40.11 Replay
archived bars reconstruct expected lifecycle;
repeated replay produces identical output;
replay does not use live mutable data;
replay matches canonical checkpoint fixtures.
40.12 Session rollover
archives prior-session lifecycle;
initializes clean current-session namespace;
prevents stale lifecycle carryover;
preserves historical records.
40.13 Read-only endpoints
repeated status reads cause no state mutation;
reads do not update timestamps;
reads do not advance counts;
reads do not create confirmations;
reads do not persist;
reads do not create children.
40.14 Symbol and contract behavior
root requests resolve to the authoritative live contract;
cached front-month data does not override active execution state;
rollover does not silently migrate active lifecycle identity;
mixed-contract snapshots are rejected or isolated.
40.15 Source freshness
stale market source remains visibly stale;
fresh ATR does not mask stale listener price;
fresh price does not mask stale lifecycle;
mixed-session aggregate is not published as valid.

41. Canonical Specialized Lifecycle Specification Requirements
Every canonical specialized lifecycle specification SHALL define:
lifecycle domain/type and applicable phase identifier;
creation preconditions;
parent requirements;
initial state;
legal states;
legal transitions;
prohibited transitions;
mutable fields;
immutable fields;
freeze points;
event window;
count behavior where applicable;
confirmation behavior;
failure behavior;
expiration behavior;
terminal behavior;
child-creation behavior;
restart behavior;
replay checkpoints;
minimum specialized regression tests.
A canonical specialized specification may strengthen this engine contract but SHALL NOT weaken it.

42. Codex Implementation Requirements
Codex SHALL treat this document as a compliance contract.
Before modifying lifecycle code, Codex SHALL identify:
the affected lifecycle type;
current state owners;
transition call sites;
persistence paths;
read-only projection paths;
replay paths;
restart paths;
session-rollover paths;
parent-child creation paths;
relevant tests.
Codex SHALL NOT infer lifecycle behavior solely from variable names or existing implementation defects.

43. Codex Audit Requirements
A Codex audit claiming compliance SHALL provide all of the following.
43.1 File inventory
List every file that:
creates lifecycle state;
mutates lifecycle state;
persists lifecycle state;
restores lifecycle state;
replays lifecycle state;
exposes lifecycle state;
resets lifecycle state at session rollover.
43.2 Function inventory
Identify the exact functions responsible for:
lifecycle creation;
state transition;
count advancement;
freeze operations;
confirmation;
failure;
expiration;
child creation;
persistence;
restoration;
projection.
43.3 State-transition map
Produce the implemented transition map and compare it to the canonical specialized specification.
Any extra or missing transition SHALL be reported.
43.4 Mutation audit
Identify every write to authoritative lifecycle fields.
Confirm that:
each write is legal;
each write is event-driven;
each write increments version;
frozen fields have no later write path;
terminal fields have no reopening path.
43.5 Read-only audit
Trace all read-only endpoints and confirm they cannot:
call lifecycle advancement with persistence;
change in-memory authoritative state;
write lifecycle files;
create child state;
modify timestamps.
43.6 Duplicate-event audit
Demonstrate how event identity prevents duplicate processing.
43.7 Stale and ordering audit
Demonstrate how stale and out-of-order events are detected and handled.
43.8 Persistence audit
Document:
authoritative storage path;
atomic-write method;
schema;
version handling;
recovery behavior;
corruption behavior.
43.9 Restart audit
Demonstrate restoration of:
exact lifecycle IDs;
exact states;
exact counts;
frozen anchors;
frozen boundaries;
parent-child relationships;
terminal states.
43.10 Session-rollover audit
Demonstrate that a new session cannot expose stale prior-session lifecycle state as current.
43.11 Replay audit
Run canonical archived-bar replay and compare expected checkpoint output against actual output.
Replay validation SHALL use archived market bars, not reasoning logs.
43.12 Contract-resolution audit
Verify that active lifecycle symbol resolution follows authoritative live execution state and does not incorrectly prefer a different contract merely because recent-bar or ATR files contain it.
43.13 Regression evidence
Provide the exact commands and results for:
targeted lifecycle tests;
read-only endpoint tests;
replay tests;
restart tests;
session-rollover tests;
duplicate/stale/out-of-order tests;
full relevant test suite.

44. Required Codex Audit Output Format
A completed audit SHALL report:
1. Files inspected
2. Functions inspected
3. Lifecycle owners
4. Implemented legal transitions
5. Implemented prohibited-transition protections
6. Frozen-field write audit
7. Parent-child audit
8. Duplicate-event behavior
9. Stale-event behavior
10. Out-of-order-event behavior
11. Persistence behavior
12. Restart behavior
13. Session-rollover behavior
14. Read-only endpoint behavior
15. Replay results
16. Contract-resolution behavior
17. Regression commands
18. Regression results
19. Remaining defects
20. Compliance conclusion

The compliance conclusion SHALL be one of:
COMPLIANT
PARTIALLY COMPLIANT
NONCOMPLIANT
A partially compliant or noncompliant result SHALL list each unresolved defect and its operational consequence.

45. Change-Control Rule
Any change to lifecycle semantics SHALL require:
identification of the governing canonical document;
explicit specification amendment;
implementation update;
regression-test update;
replay validation;
restart validation;
read-only endpoint validation;
session-rollover validation.
Implementation changes SHALL NOT silently redefine lifecycle architecture.

46. Final Architectural Guarantee
The Randle AI Lifecycle Engine SHALL ensure that every decision lifecycle is:
explicitly identified;
correctly parented;
legally advanced;
deterministically counted;
immutably frozen;
terminally protected;
durably persisted;
exactly restored;
reproducibly replayed;
isolated by session;
safely projected;
fully auditable.
No trading rule is changed by this specification.
This specification provides the architecture required to preserve those rules exactly across live operation, duplicate data, stale data, out-of-order data, process restart, historical replay, contract rollover, session rollover, and read-only observation.
