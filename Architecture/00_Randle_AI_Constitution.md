Randle AI Constitution
Deterministic Trading-System Engineering Standard
Document Type: Constitution
Status: Canonical
Authority: Foundational Architecture Authority
Applies to: Entry Agent, Rithmic Listener, Executor, Trade Manager, replay systems, status endpoints, Command Center projections, research tools, and future AI or machine-learning components.

1. Purpose
Randle AI is a deterministic market-structure system built around liquidity, volatility, confirmation, rejection, continuation, risk, and execution.
Its purpose is not to guess what the market may do through unrestricted artificial intelligence.
Its purpose is to:
Observe objective market information.
identify defined liquidity interactions;
apply deterministic rules;
preserve historical market facts;
produce reproducible lifecycle decisions;
execute only authorized trade instructions;
remain fully auditable through replay.
The architecture must reflect the same discipline as the trading methodology.
The system must never depend on loosely held memory, implicit state, ambiguous ownership, or silent historical mutation.

2. Governing Principle
The system does not remember truth.
The system reconstructs truth from preserved facts.
Current status is not authoritative merely because it is stored in a state file or displayed in the Command Center.
Current status is authoritative only when it can be deterministically derived from valid market facts, lifecycle facts, rule versions, and execution facts.

3. Sources of Truth
Randle AI recognizes four distinct sources of truth.
3.1 Market truth
Market truth includes:
Rithmic market-data messages;
completed bars;
exchange timestamps;
price;
volume;
bid and ask information;
liquidity levels;
session locks;
ATR and volatility observations;
other verified market inputs.
Market truth may be recorded and normalized.
It may not be rewritten by lifecycle logic, the UI, the AI layer, or execution logic.

3.2 Lifecycle truth
Lifecycle truth includes permanently captured facts such as:
lifecycle identity;
symbol;
session date;
rejection or continuation classification;
liquidity-level identity;
direction;
Step 2 confirmation;
Step 2 anchor;
confirmation candle;
Leg 1 values;
rejection boundary;
continuation boundary;
Step 4 confirmation;
termination;
invalidation;
level consumption;
continuation creation.
Once a lifecycle fact has occurred and been validly recorded, it is immutable.
A later condition may add another fact.
It may not erase or silently replace the earlier fact.

3.3 Projection truth
Projection truth includes derived operator-facing information such as:
current step;
candle count;
wait reason;
eligible or ineligible;
confirmation labels;
public boundary values;
current lifecycle summary;
Command Center display;
/entry/status output.
Projection truth is rebuildable.
It is not the original source of market or lifecycle truth.
A projection may be deleted and reconstructed without losing authoritative information.

3.4 Execution truth
Execution truth includes:
submitted orders;
acknowledged orders;
working orders;
fills;
cancellations;
rejections;
positions;
account state;
stop state;
target state.
Execution truth comes from the Executor, Rithmic order plant, exchange acknowledgments, and verified reconciliation.
Entry Agent may issue an execution intent.
Entry Agent may not declare an order filled, canceled, active, or closed without authoritative execution confirmation.

4. Immutable-Fact Doctrine
Article 4.1
Market facts are immutable after acceptance into the canonical event history.
Article 4.2
Confirmed lifecycle values are immutable after confirmation.
Article 4.3
A confirmed Step 2 anchor may not be recalculated from later candles.
Article 4.4
A confirmed rejection boundary may not be replaced because a newer candidate appears.
Article 4.5
A confirmed continuation boundary belongs to its continuation lifecycle and may not overwrite the rejection lifecycle that created it.
Article 4.6
Historical correction must occur through a new explicit correction, reversal, invalidation, or superseding event.
Historical records may not be silently edited.
Article 4.7
No fallback path may substitute a different market value for a missing confirmed value unless the formal lifecycle specification explicitly authorizes that substitution.

5. Lifecycle Identity Doctrine
Every independent market opportunity must have a permanent lifecycle identity.
A lifecycle identity must distinguish at least:
symbol;
session;
liquidity-level identity;
rejection or continuation;
direction;
lifecycle sequence or unique identifier.
A rejection lifecycle and its resulting continuation lifecycle are related but separate.
They may reference one another.
They may not share one mutable state object whose meaning changes over time.
Example:
NQ-2026-07-10-ONH-REJECTION-001

may create:
NQ-2026-07-10-ONH-CONTINUATION-001

The continuation lifecycle may reference the rejection lifecycle as its parent.
It may not repurpose the rejection lifecycle’s identity.

6. Single-Ownership Doctrine
Every field must have one clearly defined owner.
Examples:
Information
Authoritative owner
Completed candle
Market-data layer
Session liquidity lock
Session-lock layer
ATR observation
Volatility layer
Step 2 confirmation
Rejection or continuation lifecycle
Step 4 confirmation
Same lifecycle as its Step 2
Continuation creation
Confirmed rejection lifecycle
Current-step label
Projection layer
Working order
Execution layer
Filled quantity
Rithmic/execution reconciliation
UI display
Command Center projection

No component may claim authority over information owned by another component.

7. Step Recognition Doctrine
Steps are not mutable containers of truth.
A step is a rule-defined recognition of a market event within a specific lifecycle.
The proper behavior of a step is:
Receive authorized inputs.
evaluate its deterministic rule;
emit no event if the rule is incomplete;
emit one versioned event if the rule is completed;
become idempotent after emitting that event.
A step must not:
rewrite its parent;
alter upstream market data;
silently reset a confirmed event;
repurpose another lifecycle;
overwrite a later step;
derive execution truth;
mutate state during a read-only status request.

8. Step 2 Doctrine
Step 2 recognizes and records the defined confirmation of a rejection or continuation lifecycle.
Once Step 2 confirms, the system must preserve:
the lifecycle ID;
parent lifecycle ID when applicable;
market symbol;
session date;
lifecycle type;
direction;
liquidity-level identity;
confirmation candle time;
confirmation candle values;
Leg 1 identity and values;
Step 2 anchor;
rejection or continuation boundary;
ATR or volatility snapshot required by the rule;
rule version;
event sequence.
Later candles may advance the lifecycle.
They may not redefine the confirmed Step 2 event.
A new valid opportunity requires a new lifecycle identity.
It does not justify rewriting the existing Step 2 lifecycle.

9. Step 4 Doctrine
Step 4 is a later stage of the same lifecycle whose specific Step 2 event confirmed.
Step 4 is not an independent trading lifecycle.
Step 4 must reference:
the same lifecycle ID;
the exact Step 2 confirmation event ID;
the same session;
the same symbol;
the captured Step 2 boundary and anchor;
the authorized candle sequence;
the applicable rule version.
Step 4 may produce an event such as:
ready;
confirmed;
terminated;
failed;
expired;
invalidated.
Step 4 may not:
locate an unrelated “current Step 2” and modify it;
adopt a newer candidate from another lifecycle;
recalculate the confirmed Step 2 boundary;
rewrite rejection history when creating continuation;
reset itself because /entry/status was queried;
use stale prior-session state as the active parent.

10. Rejection and Continuation Separation
Rejection and continuation are separate lifecycle domains.
A rejection lifecycle may create a continuation lifecycle only when the formal continuation eligibility rule is satisfied.
The continuation lifecycle must receive:
its own lifecycle ID;
its own Step 2 state;
its own Step 4 state;
its own candle count;
its own confirmation timestamps;
its own boundary ownership.
The rejection lifecycle remains preserved after continuation begins.
Continuation does not rename, clear, or overwrite rejection.

Release v1.0 Scope Boundary
All continuation references in this Constitution establish universal rejection/continuation separation and ownership invariants only. They are conditional concepts for any future approved canonical continuation specification. This Constitution does not define continuation trading rules, a post-eligibility continuation state machine, or continuation implementation. The current specialized lifecycle specification boundary ends at Continuation Eligibility Creation.

11. Append-Only Event Doctrine
Authoritative lifecycle changes should be represented as append-only events.
Examples include:
SESSION_LOCKED
LIQUIDITY_LEVEL_REGISTERED
STEP2_CONFIRMED
STEP4_READY
STEP4_CONFIRMED
STEP4_TERMINATED
LEVEL_INVALIDATED
LEVEL_CONSUMED
CONTINUATION_CREATED
TRADE_INTENT_EMITTED

Each event must include enough identity and version information to establish:
what occurred;
when it occurred;
which symbol it belongs to;
which session it belongs to;
which lifecycle it belongs to;
what caused it;
which rule version generated it;
its order within that lifecycle.
Events may be appended.
They may not be rewritten or deleted as routine lifecycle behavior.

12. Deterministic Projection Doctrine
Operator status must be derived from authoritative events and accepted market data.
A valid projection must be reproducible.
The following procedure must produce the same result every time:
Start with empty projection
Load the same ordered events
Apply the same rules version
Rebuild status
Compare final output

Given identical ordered inputs and identical code and rule versions, the resulting projection must be identical.
A restart must not change the resulting lifecycle truth.

13. Idempotency Doctrine
Processing the same logical input more than once must not create additional effects.
Examples:
The same completed candle delivered twice must not double-advance candle count.
The same Step 2 confirmation must not create two lifecycles.
The same Step 4 event must not confirm twice.
Repeated /entry/status requests must not alter state.
Replaying the same archive must not create different results.
Retrying an execution intent must not create an unauthorized duplicate order.
Every event-producing operation must have a stable identity or deduplication rule.

14. Ordering and Staleness Doctrine
The system must explicitly defend against:
duplicate events;
stale events;
out-of-order events;
prior-session events;
events from the wrong contract;
delayed projections;
delayed Rithmic prices;
mismatched lifecycle parents.
An older event may not overwrite a newer accepted event.
A prior-session lifecycle may not become active merely because its state file was loaded.
A stale market snapshot may not be presented as current market truth.
When ordering cannot be established safely, the system must reject or quarantine the event rather than guess.

15. Session-Boundary Doctrine
Every lifecycle belongs to one trading session.
At session rollover:
The previous session is closed.
Its authoritative history is preserved.
Its active projections are no longer eligible for the new session.
A new session identity is created.
New locks and liquidity levels are recorded under that session.
Prior-session state may be reviewed but not treated as current.
Session rollover must not depend on clearing arbitrary fields until the UI appears correct.
It must be a formal domain transition.

16. Read-Only Boundary Doctrine
Read-only operations must be truly read-only.
The following must never mutate or persist lifecycle state:
/entry/status;
Command Center polling;
debugging panels;
status serialization;
health checks;
audit queries;
projection inspection;
reporting endpoints.
A read request may build or return a projection.
It may not advance steps, reset lifecycles, rewrite files, reseed candidates, or persist derived state.

17. Volatility and Liquidity Doctrine
Liquidity and volatility observations are deterministic inputs or derived features.
They must have:
clear source data;
defined calculation;
defined time horizon;
defined timestamp;
defined freshness threshold;
defined version;
defined ownership.
A volatility observation used at confirmation must be captured with the lifecycle when required by the rule.
It may not later change merely because the rolling volatility value changed.
The same applies to liquidity identity, session levels, and captured boundaries.

18. AI Boundary Doctrine
Artificial intelligence or machine learning may:
score a valid deterministic setup;
classify a market regime;
estimate conditional probability;
recommend risk reduction;
recommend trade filtering;
detect anomalous data;
assist research.
Artificial intelligence or machine learning may not:
rewrite market history;
redefine a confirmed liquidity level;
alter Step 2 or Step 4 history;
create undocumented lifecycle transitions;
declare an execution fill;
bypass deterministic risk limits;
silently change rule definitions;
become the source of canonical market state.
The deterministic engine remains the authority.
The AI layer is advisory or bounded by explicit contracts.

19. Execution Separation Doctrine
Decision and execution must remain separate.
Entry Agent may produce:
TRADE_INTENT

The Executor is responsible for validating and acting on that intent.
The execution layer must independently verify:
current price freshness;
symbol and contract resolution;
risk limits;
duplicate-order protection;
position state;
working-order state;
account state;
execution authorization.
A decision event does not equal a fill.
A fill does not retroactively alter the market reasoning that produced the decision.

20. Replay Doctrine
Every material live decision must be reproducible through replay.
Replay must use authoritative archived market data whenever available.
Reasoning logs and projections may assist audit, but they must not replace the underlying market facts.
Replay must be capable of confirming:
Step 2 identity;
Step 2 timing;
Step 2 captured values;
Step 4 timing;
candle counts;
termination;
invalidation;
continuation creation;
boundary retention;
final decision.
A replay discrepancy must be treated as an architectural or data-integrity issue.
It must not be dismissed as an unavoidable difference between live and replay behavior.

21. Versioning Doctrine
Material outputs must identify their governing versions.
This should include, where applicable:
event schema version;
lifecycle-rules version;
projection version;
volatility-feature version;
liquidity-feature version;
build or commit version;
last applied event ID;
last applied sequence.
A change in interpretation must be distinguishable from a change in market facts.

22. Failure Doctrine
When the system encounters an impossible or unauthorized transition, it must:
Preserve the existing valid state.
reject or quarantine the invalid transition;
record the violation;
expose the violation for audit;
avoid silently guessing or repairing history.
The system must prefer:
No new decision

over:
A decision derived from corrupted or ambiguous state


23. Codex Governance Doctrine
Codex is a contributor, not the architectural authority.
Before modifying lifecycle logic, Codex must identify:
The authoritative source of truth.
The owning component.
Whether the value is immutable.
The lifecycle identity.
The triggering event.
The legal state transition.
The effect of duplicate input.
The effect of stale input.
The effect of out-of-order input.
The session boundary behavior.
The replay behavior.
The regression test proving safety.
Codex may not solve lifecycle problems through arbitrary:
resets;
clears;
reseeding;
field substitution;
fallback values;
shared mutable dictionaries;
silent state migration;
cross-lifecycle copying;
status-endpoint persistence.
Any such operation must be explicitly authorized by the formal lifecycle specification.

24. Required Proof for Every Lifecycle Change
A lifecycle patch is incomplete until it includes evidence that:
existing confirmed facts remain unchanged;
the correct lifecycle owns the new value;
duplicate processing is a no-op;
restart produces the same output;
status polling produces no mutation;
stale input cannot overwrite current state;
prior-session state cannot become active;
rejection and continuation remain separate;
replay reproduces the live result;
unrelated Step 2, Step 4, Step 5, and Step 6 behavior remains unchanged.

25. Core Invariants
The following invariants are binding:
A Step 4 event must reference one valid upstream Step 2 confirmation event.

A Step 4 event and its upstream Step 2 confirmation event must share the same lifecycle ID.

A lifecycle may belong to only one symbol and one session.

A rejection lifecycle and a continuation lifecycle may not share the same lifecycle ID.

A confirmed boundary may not change within the same lifecycle.

A duplicate event may not create a second state transition.

A read-only request may not change lifecycle history.

An older event may not overwrite a newer accepted projection.

A current projection must be rebuildable from authoritative facts.

Execution state may not be inferred when authoritative execution information is available.


26. Final Authority
When convenience conflicts with determinism, determinism governs.
When a quick patch conflicts with lifecycle identity, lifecycle identity governs.
When stored state conflicts with reproducible market facts, reproducible market facts govern.
When the UI conflicts with the event history, the event history governs.
When Codex-generated code conflicts with this Constitution, the code is invalid.

Foundational Standard
Facts are preserved.
Lifecycles are identified.
Transitions are explicit.
Projections are rebuildable.
Operations are idempotent.
Sessions are isolated.
Execution is reconciled.
AI is bounded.
Every decision is reproducible.
