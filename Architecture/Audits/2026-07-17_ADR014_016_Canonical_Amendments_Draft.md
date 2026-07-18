# ADR-014 through ADR-016 - Exact Canonical Amendment Draft

Document Type: Coordinated amendment proposal

Status: **DRAFT - NOT APPLIED - NOT CANONICAL - NOT APPROVED**

Phase 3C1-R1 identity: **F1-F8 TARGETED NORMATIVE REMEDIATION IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R1 REVIEW**

Implementation Authorization: None

## 1. Amendment rule

ADR-014 is already approved and is the governing Entry-session dependency. Each proposed ADR-015/ADR-016 change SHALL be applied only if its owning ADR is explicitly approved. Amendments shared by ADR-015 and ADR-016 require approval of both decisions. Until coordinated canonical incorporation is separately authorized, existing canonical text plus approved ADR-014 remain authoritative and every amendment in this ledger remains noncanonical. Approval of one ADR does not silently approve another or authorize incorporation, implementation, verification, deployment, or trading.

The amendments do not modify stack/overlap authority. DEBT-015 remains a separate governed trace and is not an approval prerequisite for these drafts absent a later approved dependency assessment.

## 2. Constitution amendment

### Target

`Architecture/00_Randle_AI_Constitution.md`, after the existing Runtime Authority Alignment Record.

### Proposed insertion

```text
Runtime Recovery Alignment Record
ADR-014 is already approved and defines one indivisible Entry Session Rollover Transaction. Effective only if each proposed decision is separately approved and canonically incorporated, ADR-015 would assign full-listener process lifecycle and Listener Authority Epoch to one Listener Supervisor, and ADR-016 would define direct current-epoch health authority, a local serialized durable health control record, asynchronous shared-health projection, and fenced Bridge Generation recovery. These decisions clarify Sections 3, 6, 12 through 17, 20, and 22. They do not change trading rules, ATR mathematics, execution ownership, or stack calculation authority. ADR-015/ADR-016 draft status creates no authority and authorizes no implementation or deployment.
```

No constitutional doctrine text is proposed for replacement. The existing single-owner, session, read-only, volatility, replay, and failure doctrines remain higher authority.

## 3. Lifecycle Vocabulary amendments

### Target A

`Architecture/01_Randle_AI_Lifecycle_Vocabulary.md`, after section 2.1 Session.

### Proposed insertion

```text
2.1.1 Candidate Current-Session Payload
A Candidate Current-Session Payload is a complete immutable receiver archive proposed for the next per-symbol Entry Session Aggregate. It is noncurrent evidence until a Session Rollover Transaction commits. A sender lock assertion is an input field, not the canonical receiver lock fact.

2.1.2 Session Rollover Transaction
A Session Rollover Transaction is the indivisible validate-build-commit-expose transition whose one durable commit atomically activates the candidate and retires prior applicability while assigning one session_rollover_commit_id to the receiver lock, canonical Entry Agent aggregate, frozen ladders, observation state, session-context authorization, trade_authorization_context_binding, authorized_session_rollover_commit_id initialized null, exposure cursors, and prior-session retirement. A split activation/retirement or missing authorization-binding state SHALL NOT commit.

2.1.3 Active Session Projection
An Active Session Projection is a rebuildable current-session view derived from one committed Entry Session Aggregate. It is not the aggregate or commit authority.

2.1.4 Historical Session Archive
A Historical Session Archive preserves an ended session's immutable canonical facts after active applicability ends. It cannot serve as current-session fallback.
```

### Target B

Replace section 18.7 `Authority Epoch` with:

```text
18.7 Authority Epoch
An Authority Epoch is a durable, versioned interval during which one identified source instance owns canonical publication for stated symbols/contracts. A Listener Authority Epoch is allocated and fenced only by the Listener Supervisor. A downstream reconnect, bridge-generation change, projection restart, or process reachability observation is not automatically an authority-epoch change. Old-epoch input is ineligible after fence.
```

### Target C

Insert after section 18.7:

```text
18.7.1 Bridge Generation
A Bridge Generation identifies one RAPI bridge child within one Listener Authority Epoch. Recycling a bridge changes Bridge Generation but does not automatically change Listener Authority Epoch.

18.7.2 Restart Incident
A Restart Incident is the durable identity joining one stale observation, request, `RESTART_PENDING`, `RESTART_CANCELED`/`RECOVERY_RATE_LIMITED_FAILED`/`RESTART_FENCED`, execution, epoch transition, rehydration, and completion/failure. `RESTART_CANCELED` is a durable terminal incident outcome that performs no process action and requires deterministic post-cancellation `HEALTHY`/`SUSPECT` reevaluation. `RECOVERY_RATE_LIMITED_FAILED` is the distinct terminal full-listener incident outcome committed before fencing when the current governed cooldown is active or the durable full-listener restart count already equals its maximum; it performs no process action, supplies no automatic SFF fact, survives restart, and permits no automatic retry. One `RESTART_FENCED` incident SHALL execute at most one full-listener restart.

18.7.3 Fencing Token and Fence
A Fencing Token is a supervisor-issued current-version capability included in a request. It does not itself revoke authority. A Fence is the durable transition that revokes the stated epoch/generation and establishes the no-cancel boundary.

18.7.4 Health Commit and Health Projection
A Health Commit is a verified local durable control record carrying epoch, generation, sequence, and integrity identity. A Health Projection is an asynchronous rebuildable observational record derived from a Health Commit. It SHALL NOT initiate, influence, reinforce, confirm, participate in, or contribute to process control, lifecycle, death, recovery, fencing, cancellation, authorization, or readiness.

18.7.5 Health Persistence Degraded
HEALTH_PERSISTENCE_DEGRADED means the local durable health control record cannot be committed or recovered. New entries and new automatic lifecycle fences are blocked while direct current-epoch liveness remains observable and pending state remains unacknowledged.

18.7.6 Session Projection Diverged
SESSION_PROJECTION_DIVERGED is a fail-closed state in which current-labeled session surfaces disagree on session_rollover_commit_id or session identity. It preserves all evidence and authorizes no fallback or entry.

18.7.7 Failed Recovery Exhausted
FAILED_RECOVERY_EXHAUSTED is the durable terminal bridge-incident outcome created only when the pre-execution governed bridge count already equals its maximum, or the last permitted execution fails to establish a ready generation by its governed deadline. It performs no implicit retry or listener action and MAY supply SFF-03 evidence only through a separate current listener incident, debounce, revalidation, rate, and fence decision.

18.7.8 Health Time Authority Degraded
HEALTH_TIME_AUTHORITY_DEGRADED means the Supervisor cannot establish trustworthy monotonic/UTC time authority. It blocks freshness, expectation, entries, readiness, and new automatic lifecycle decisions until the closed durable recovery transaction succeeds. File/projection time is never substitute authority.

18.7.9 Bridge Lifecycle Terms
BRIDGE_STARTUP_UNPROVEN is the initial nonready bridge state before one current Supervisor grant, authenticated Controller acknowledgement, connection/login proof, and exact required-contract SUBSCRIPTION_VERIFIED evidence commit. SUBSCRIPTION_VERIFIED is the sole ready subscription lifecycle fact; ACTIVE is not an alias or readiness state. RECYCLE_CANCELED is the durable terminal no-action bridge-incident outcome produced by current-generation recovery before fence, with an atomic separate BRIDGE_READY or BRIDGE_SUSPECT current-state reevaluation. BRIDGE_FAILED is an ordinary nonexhausted permitted-execution result and is not FAILED_RECOVERY_EXHAUSTED. Bridge Controller facts, including BRIDGE_GENERATION_READY, are authenticated execution acknowledgements only and never grant/adopt authority.

18.7.10 Shared-Feed Policy Validation
SHARED_FEED_POLICY_INVALID is a deterministic policy-validation disposition and startup failure reason, not a listener or bridge lifecycle state and not a restart-incident outcome. The Listener Supervision Policy Evaluator validates the exact deployment-bound policy identity; the Listener Supervisor Incident Writer records the immutable validation result. It permits no speculative restart/recycle/fence and blocks startup readiness until a corrected, versioned, deployment-traceable policy passes a new startup validation.

18.7.11 Closed Transitions
For every listener, restart-incident, bridge, health-control, and Entry-session state machine, any transition not explicitly listed as a permitted exit in the governing transition table is prohibited.
```

### Target D

Append to section 16 Reset Vocabulary:

```text
New-session observation initialization is not an independent reset. It is a member of the committed Session Rollover Transaction and carries the same session_rollover_commit_id. A bridge-generation change is not an ATR/RMA reset. A full listener-epoch change requires deterministic rehydration; valid continuous durable history is preserved, while only approved invalidation/gap conditions authorize destructive reconstruction/reset.
```

## 4. Lifecycle Engine amendments

### Target A - section 31 Session Rollover

Append sections 31.6 through 31.9:

```text
31.6 Session rollover commit
For an Entry session, validation and candidate aggregate construction SHALL precede mutation. Candidate insertion, active-pointer transition, prior-session retirement, observation initialization, session authorization, trade_authorization_context_binding, authorized_session_rollover_commit_id initialized null, receiver lock, required frozen/session fields, and pending exposure cursors SHALL then commit atomically through one transaction identity before current exposure. A transaction missing activation, retirement, or either authorization-binding field SHALL be rejected.

31.7 Candidate isolation
A received new-session candidate may be archived as noncurrent evidence. It SHALL NOT become a current raw or canonical projection before durable commit.

31.8 Rollover persistence failure
Failure before commit preserves the prior canonical aggregate and leaves the new session fail-closed. Failure after commit but before complete exposure retains pending exposure under the same commit identity.

31.9 Session projection divergence
Current-labeled surfaces with different session/commit identities SHALL enter an explicit fail-closed divergence state and SHALL recover only from verified committed authority or governed replay.
```

### Target B - section 32 Read-Only Endpoints

Append to section 32.1:

```text
A read-only endpoint SHALL NOT create, request, cancel, fence, retry, or execute listener/bridge recovery; allocate authority epochs or generations; flush pending health/session state; advance publication cursors; start/stop a process; hydrate/normalize/repair/back up persistence; hydrate/replace configuration or domain caches; rebuild indexes; populate ATR caches; lazily construct pipelines/singletons/threads/clients/journals/directories; or invoke a mutating downstream read. GET, HEAD, health, debug, watchdog, alert, audit-query, proxy, and Command Center polling routes are read-only regardless of their name and SHALL return an immutable snapshot or a governed read-only unavailable disposition.
```

### Target C - section 35 Source Ownership

Insert after the examples:

```text
The Listener Supervisor exclusively owns full-listener process lifecycle, Listener Authority Epoch allocation/fencing, bridge incident/fencing decisions, and Bridge Generation grant/adoption. The market listener owns accepted market data and direct feed-health facts within the granted epoch. Bridge Controller executes only one Supervisor-fenced bridge command and reports its result; it does not grant authority. Executor may publish accepted-delivery health and request restart but owns no listener/bridge process action. A local Health Durable Writer owns durable health commit/cursor mutation. Shared health JSON is observational projection only and cannot participate in control/readiness.
```

### Target D - section 40 Minimum Engine Regression Tests

Append:

```text
40.16 Runtime authority recovery
Tests SHALL cover atomic Entry session rollover, shared commit identity, prior-session preservation, recovery-tick commit-before-evaluate, restart cancellation/fencing/exactly-one behavior, bridge/listener distinction, local durable health pending retention, corruption recovery, cross-symbol failure policy, ATR rehydration, cold/manual startup, and diagnostic process-lifecycle nonmutation.
```

## 5. ADR-012 amendment

### Target A - section 3.3 ATR/RMA continuity

Replace the sentence beginning `ATR/RMA reset is legal only` and its listener-epoch interpretation with:

```text
ATR/RMA disposition is closed. Bridge recycle and same-epoch symbol recovery SHALL RETAIN finalized bars/RMA and SHALL REHYDRATE only the incomplete minute from complete journal proof; stale-epoch/generation evidence SHALL be rejected without current ATR change. Listener restart/new epoch, cold startup, and interrupted startup recovery SHALL REHYDRATE exact continuous durable authority and record ATR_CONTINUITY_PRESERVED. Only DURABLE_HISTORY_GAP, DURABLE_HISTORY_CORRUPT, CONTRACT_IDENTITY_CHANGED, or SESSION_VOLATILITY_RESET_REQUIRED SHALL authorize the exact ADR-015 INVALIDATE/REBUILD/WARMUP disposition. No other reset reason is legal.
```

The existing four legal reason families remain, but they become eligibility for explicit reconstruction/reset disposition rather than mandatory reset on every event.

### Target B - section 3.6 Projection and writer separation

Append:

```text
Read-side separation includes process lifecycle and control persistence. GET/HEAD/status/health/debug/watchdog/alert/audit routes SHALL NOT request, cancel, fence, retry, or execute listener/bridge lifecycle action; flush pending health/session data; or advance control cursors.
```

### Target C - sections 6 and 10

Add verification/implementation references to the ADR-014 through ADR-016 session transaction, Listener Supervisor, local durable health writer, bridge controller, downstream epoch consumers, startup orchestration, and diagnostic purity suites. Existing July 16 continuity and evidence requirements remain unchanged.

## 6. Runtime Authority Specification amendment

### Header

Proposed version `1.3`; approved decision source ADR-014 plus proposed decision sources ADR-015/ADR-016 and canonical ADR-012; expand scope to Entry session rollover, listener supervision/epoch recovery, feed-health durability, bridge control, startup/readiness, and diagnostic purity only after coordinated approval/incorporation.

### Replace section 1 Authority boundaries with

```text
## 1. Authority boundaries

The Rithmic listener owns accepted completed one-minute candle history, direct current-epoch feed facts, and canonical ATR/RMA observations derived from accepted history. The Listener Supervisor exclusively owns full-listener process lifecycle, Listener Authority Epoch allocation/fencing, bridge incident/fencing decisions, and Bridge Generation grant/adoption. Bridge Controller executes only an exact Supervisor-fenced bridge command and reports exact results. Executor owns execution truth, accepted-delivery health facts, entry blocking, and restart requests, but not listener/bridge process lifecycle.

Session-lock policy is the sole candidate-eligibility and rollover/state-decision authority for the Entry Session Rollover Transaction. The Entry Agent Session Commit Writer is the sole durable writer and atomic transaction executor for the Entry Session Aggregate, canonical session-lock fact, active pointer, candidate activation, and prior-session retirement. The Commit Writer SHALL mechanically reject malformed, stale, unauthorized, or constraint-invalid write plans, but that rejection SHALL NOT transfer business-policy decision authority from Session-lock policy. TradingView owns the transmitted source payload. The local Health Durable Writer owns durable health commit/cursor mutation.

Shared recent-bar JSON, ATR snapshots, shared/OneDrive feed-health JSON, raw receiver/current files, status output, and Command Center output are projections/exposure surfaces. Projection failure or staleness does not revoke or create authority and cannot declare a process dead.
```

### Insert after section 3

```text
## 3A. Listener epoch and ATR recovery

A bridge-generation change or same-epoch symbol recovery RETAINS completed-bar/RMA authority and REHYDRATES only the incomplete minute under complete journal proof. Stale-epoch/generation input is rejected with no current ATR effect. Full listener-epoch change, cold startup, and interrupted startup recovery enter REHYDRATING and reconstruct from durable current-contract authority. Exact continuous recovery records ATR_CONTINUITY_PRESERVED. Only DURABLE_HISTORY_GAP, DURABLE_HISTORY_CORRUPT, CONTRACT_IDENTITY_CHANGED, or SESSION_VOLATILITY_RESET_REQUIRED permits the exact approved INVALIDATE/REBUILD/WARMUP disposition. Shared projections have no ATR authority.
```

### Insert after section 4

```text
## 4A. Entry Session Rollover Transaction

The first valid current-session candidate SHALL be archived noncurrent, fully validated, and built as a complete candidate aggregate. One durable transaction SHALL atomically insert and activate the new session, retire prior applicability, initialize observation, activate receiver lock/frozen ladders/session authorization, commit trade_authorization_context_binding as BLOCKED_PENDING_RUNTIME_GATES, commit authorized_session_rollover_commit_id as null, create pending exposure cursors, and assign one session_rollover_commit_id across every member. Only then SHALL projections be eligible to expose it. A split activation/retirement or missing/inherited authorization-binding state SHALL NOT commit. Prior canonical history remains intact but nontradable after its applicability date on failure. Every later opening-entry request/decision SHALL carry the active authorized_session_rollover_commit_id. Current-labeled session/commit disagreement enters SESSION_PROJECTION_DIVERGED and remains fail-closed.
```

### Insert after section 5

```text
## 5A. Listener supervision and restart recovery

Listener Supervisor is the sole full-listener lifecycle authority. Every restart request carries supervisor generation, listener epoch, stale observation time, decision time, incident ID, expected incident version, and fencing token. Accepted same-epoch recovery data commits before stale evaluation and cancels an unfenced pending restart through one durable RESTART_CANCELED incident outcome, followed by deterministic HEALTHY/SUSPECT reevaluation. A canceled incident cannot fence, execute, allocate an epoch, reopen, or retry. One `RESTART_FENCED` incident executes at most one effective restart. Bridge/listener rate limits are durable monotonic rolling-window counts: when the bridge count equals its governed maximum, the pending bridge incident commits FAILED_RECOVERY_EXHAUSTED without process action; the last permitted timed-out recovery commits the same state. A full-listener incident instead commits distinct `RECOVERY_RATE_LIMITED_FAILED` before fencing when cooldown is active or the durable listener-restart count equals its maximum; it performs no process action, survives restart, permits no automatic retry, and supplies no automatic SFF predicate. `SHARED_FEED_POLICY_INVALID` is a policy-validation disposition/startup failure reason, never a lifecycle state or speculative restart trigger. The Supervisor-owned Market Data Expectation Evaluator binds the deployment-approved calendar, subscription intent, lifecycle, and clock; silence cannot define expectation. SFF-02 uses only pre-action heartbeat, command challenge, publication ingress, exact epoch grant, and exact OS-handle evidence and cannot depend on its fence/action. Per-symbol freshness cannot become shared-feed restart authority without an explicit SHARED_FEED_FAILURE predicate.

## 5B. Feed-health and bridge control

Direct current-epoch evidence owns immediate liveness. One physical SQLite database `%LOCALAPPDATA%\RandleRuntimeData\control\runtime_authority_v1.sqlite3` SHALL conform exactly to `docs/architecture/runtime_authority_store_schema_DRAFT.md`: database identity and SQLite requirements, complete table/column/nullability/key/check/foreign-key schema, closed logical writer registry, typed atomic transaction catalog, crash/replay rules, and deterministic startup reconstruction. Each table retains one logical domain writer; one Runtime Authority Store Transaction Coordinator performs only connection handling, serialization, constraint/idempotency enforcement, COMMIT/rollback, and mechanical recovery and cannot originate, evaluate, grant, classify, or own a domain identity or transition. Same-database foreign keys and uniqueness constraints are physically enforceable; no external identity copy or cross-database foreign key is authority. Pending state remains pending until COMMIT/readback success; failed writes do not acknowledge or advance the cursor. Shared/OneDrive JSON is asynchronous observational projection and SHALL NOT initiate, influence, reinforce, confirm, participate in, or contribute to control/readiness. The Rithmic listener produces authenticated subscription proof; Health Ingress validates it; the State Evaluator alone decides subscription transition; the Health Durable Writer alone commits `SUBSCRIPTION_VERIFIED`. Termination observations use independent initiator, requested action, execution method, observed cause, and result fields. For each field, NONE requires a complete trustworthy current-generation absence proof; missing, incomplete, conflicting, corrupt, unavailable, stale, wrong-identity, or unauthenticated evidence requires UNKNOWN. A nonzero exit alone does not prove BRIDGE_CRASH. BDP-01 requires unexpected current-generation process exit and excludes planned/operator shutdown, startup, controlled recycle, listener shutdown, and listener replacement. Bridge recycle requires one durable current-generation fence and does not create a listener epoch. Ordinary BRIDGE_FAILED remains distinct from terminal FAILED_RECOVERY_EXHAUSTED; only the latter may supply SFF-03 evidence. The complete health-control state machines and their permitted transitions are those in ADR-016 section 3.9.1; every unlisted transition is prohibited. Store failure enters HEALTH_PERSISTENCE_DEGRADED. Clock rollback/unavailable/non-increasing/correlation ambiguity enters HEALTH_TIME_AUTHORITY_DEGRADED. Both block new entries/new automatic fences and never transfer authority to projection.

## 5C. Diagnostic purity

GET/HEAD/status/health/debug/watchdog/alert/audit/proxy and Command Center polling are pure reads. They cannot mutate lifecycle/control state; hydrate, normalize, repair, or back up persistence; hydrate/replace configuration or domain caches; build indexes; populate ATR caches; lazily initialize pipelines/singletons/threads/clients/journals/directories; invoke a mutating downstream GET; or change processes. Mutating recovery, reconciliation, persistence/configuration hydration, corruption handling/backup, cache/index construction, and runtime initialization require explicit authenticated non-GET/event/startup boundaries under the owning transaction. A missing snapshot returns a governed read-only UNINITIALIZED, UNAVAILABLE, or STALE result.
```

### Amend sections 8 through 10

Add audit events for rollover candidate/commit/divergence/exposure; restart requested/`RESTART_CANCELED`/`RECOVERY_RATE_LIMITED_FAILED`/`RESTART_FENCED`/completed; `SHARED_FEED_POLICY_INVALID`; bridge ordinary failure/`FAILED_RECOVERY_EXHAUSTED`; epoch grant/fence; bridge generation/recycle; health-state transitions including `HEALTH_PERSISTENCE_DEGRADED` and `HEALTH_TIME_AUTHORITY_DEGRADED`; shared projection lag; and ATR continuity/rehydration. Add the new Runtime Recovery Verification Specification and Phase 3B semantic clause/scenario/assertion registry to the deployment gate and expected areas.

## 7. NQ Live Continuity Verification Specification amendment

### Target

`Architecture/09_Randle_AI_NQ_Live_Continuity_Verification_Specification.md` sections 2.1, 2.5, 5, and 6.

### Proposed amendment

```text
The July 16 NQ continuity cases remain canonical incident regressions. Cross-symbol session rollover, Listener Supervisor, feed-health durable publication, bridge generation, cold/manual startup, and diagnostic process-lifecycle purity are governed by the separately approved Runtime Recovery Verification Specification. An explicit listener epoch change requires deterministic rehydration; process restart alone does not prove ATR reset. Passing this NQ suite does not satisfy ADR-014 through ADR-016 system-wide verification.
```

## 8. Session Liquidity Lock Contract amendment

### Targets

`docs/lifecycle/session_liquidity_lock_contract.md` sections 1, 3, 4.1, 10, and 11.

### Proposed exact additions

Append to section 1:

```text
The received table is a noncurrent candidate until the Entry Session Rollover Transaction commits. The authoritative current table is the frozen table identified by the committed session_rollover_commit_id. A sender locked flag is not the receiver lock fact.
```

Replace the first paragraph of section 3 with:

```text
Entry Agent SHALL archive the first complete post-06:15 candidate, validate it under the governing webhook/liquidity contracts, build the complete session aggregate without active-state mutation, and invoke one ADR-014 Session Rollover Transaction. No lock, level, ladder, observation, authorization, or current projection is active until the transaction durably commits.
```

Append to section 4.1:

```text
New-session observation initialization/reset is a member of the committed rollover and carries its commit ID. No Rithmic candle, startup, status read, or candidate pre-processing may advance the observation-reset session independently.
```

Append to section 10:

```text
Contract validation fails when any authoritative current-labeled receiver-lock, Entry Agent aggregate, frozen-ladder, observation, or authorization member disagrees on `session_rollover_commit_id` or session identity. The result is `SESSION_PROJECTION_DIVERGED` and fail-closed preservation, not fallback or repair. Command Center is not an aggregate member or session authority: a Command Center mismatch fails only the separate observational `COMMAND_CENTER_ALIGNED` startup gate and SHALL NOT mutate, veto, or redefine the committed session.
```

Append expected implementation/verification references to ADR-014 transaction and Runtime Recovery Verification.

No stack/overlap sentence is changed by this amendment. DEBT-015 remains separate.

## 9. TradingView Webhook Contract amendment

### Targets

`docs/schemas/tradingview_webhook_contract.md` sections 4, 7, 11, and 12.

### Proposed exact additions

Append to section 4:

```text
`locked` is the sender's assertion about the finalized TradingView table. It is required input where stated but is not the receiver's canonical session-lock fact or proof of durable Entry Agent commit.
```

Replace section 7's opening with:

```text
At 06:15 PT, the first valid session payload becomes a noncurrent Candidate Current-Session Payload. It locks the production session only after the ADR-014 Session Rollover Transaction validates, builds, assigns one session_rollover_commit_id, durably commits, and exposes it. Later payload rules are evaluated against that committed identity.
```

Append to section 11:

```text
Receipt archival precedes current-session exposure and SHALL label candidate receipt, validation result, committed session_rollover_commit_id when one exists, and exposure result separately. Archival does not make the candidate current. Rejected/uncommitted candidates remain immutable noncurrent evidence.
```

Add ADR-014 and Runtime Recovery Verification expected areas to section 12.

Append to the sender-authority section:

```text
Public-route traversal and payload/session eligibility do not authenticate the TradingView sender. Production candidate commitment requires a separately approved sender-authentication authority bound to the exact receipt ID and payload hash. While DEBT-2026-07-17-016 remains blocking, candidate commitment, startup READY, deployment, and trading are prohibited. This amendment selects no authentication mechanism.
```

## 10. Entry Pipeline amendment

### Target

`docs/architecture/entry_pipeline.md`, before Step 1.

### Proposed insertion

```text
Precondition - Runtime and Session Authority
No signal may enter Step 1 unless the requested symbol is CURRENT_CONTEXT_READY/LIVE under the current session_rollover_commit_id, trade_authorization_context_binding, authorized_session_rollover_commit_id, listener_epoch_id, bridge generation where required, completed bar, ATR, contract, lifecycle, Trade Manager, and Executor reconciliation. Any mismatch, REHYDRATING, WARMUP, HEALTH_PERSISTENCE_DEGRADED, HEALTH_TIME_AUTHORITY_DEGRADED, FAILED_RECOVERY_EXHAUSTED, SESSION_PROJECTION_DIVERGED, SUSPECT, or unresolved pending/fenced restart state rejects/blocks the new signal without invoking recovery as a read-side effect. RESTART_CANCELED is eligible only after its required authoritative post-cancellation HEALTHY reevaluation; Command Center parity supplies no domain authority.
```

## 11. Persistence and Recovery amendment

### Target

`docs/architecture/persistence_and_recovery.md`, Purpose/Source of Truth.

### Proposed insertion

```text
Scope boundary: this contract governs Trade Manager/trade persistence. Entry Session Rollover authority, Listener Supervisor state, and feed-health control persistence are governed by their own approved runtime contracts. Trade persistence SHALL NOT be used to infer listener health, repair a session aggregate, or replace supervisor/health durable records.
```

## 12. Safety Rails amendment

### Target

`docs/architecture/safety_rails.md`, after System Safety.

### Proposed insertion

```text
Runtime Authority Safety
- Runtime authority uncertainty blocks new entries.
- Projection staleness cannot declare a listener/bridge dead.
- A read endpoint cannot repair or restart.
- Existing execution truth and protective-order ownership remain preserved during feed/session degradation.
- Session, listener epoch, bridge generation, health commit, bar, ATR, and contract mismatches fail closed and remain visible.
```

## 13. Architecture README amendment

Retain ADR-014 under approved ADRs as the existing governing Entry-session decision. Add ADR-015, ADR-016, the Runtime Authority Store Schema, and active supporting draft specifications under `Current Draft Items`, explicitly labeled noncanonical/not approved. Mark `docs/architecture/listener_supervision_and_health_authority_DRAFT.md` as `WITHDRAWN — SUPERSEDED DRAFT`, noncanonical, historical evidence only, and remove it from active normative/implementation dependency lists. Do not list ADR-015/ADR-016 under approved ADRs until separate approval and canonical incorporation. Add the Phase 3B remediation record, semantic clause/scenario/assertion registry, conflict matrix, and package traceability record as nonauthoritative evidence indexes.

## 14. Live Ops Command Allowlist amendment

### Target

`LIVE_OPS_COMMAND_ALLOWLIST.md`, section 2.

### Proposed insertion

```text
Every allowed GET/HEAD status, debug, health, watchdog, alert, audit, proxy, cache, configuration, account, event, or Command Center polling endpoint is observational only. Inclusion in this allowlist never authorizes lifecycle/control mutation; cache population; persistence hydration, normalization, repair, corruption handling, or backup creation; configuration hydration/replacement; active-index construction/replacement; ATR-cache creation; lazy pipeline/singleton/thread/client/journal/directory initialization; transitive invocation of a mutating downstream GET; process action; restart/recycle request; health flush; session commit; cursor advance; authorization change; or risk mutation. Such work SHALL occur only at an explicit authenticated startup, event, or non-GET governed command boundary owned by the applicable transaction. A GET without a prepublished immutable snapshot SHALL return a governed read-only `UNINITIALIZED`, `UNAVAILABLE`, or `STALE` disposition. Any GET from which any prohibited primitive remains reachable SHALL be removed from the allowlist until corrected and verified.
```

## 15. No-amendment / separate-scope decisions

- ADR-013 is unchanged.
- `Architecture/13_Randle_AI_TradingView_Liquidity_Ladder_Verification_Specification.md` is unchanged by ADR-014 through ADR-016.
- TradingView Liquidity Ladder Calculation Contract overlap/full-span text is unchanged here.
- DEBT-015 remains separately governed and does not block this documentation/recovery scope absent direct-dependency approval.
- `launch_all.ps1`, `run_system.ps1`, `executor.py`, `rithmic_live_listener.py`, Entry Agent, Trade Manager, Command Center, and tests are implementation/verification targets, not documentation amendments in this authorized phase.

## 16. Production Startup and Recovery specification promotion

If separately approved for canonical promotion, the startup contract SHALL require positive proof of zero applicable blocking production-readiness debt, exclusive Executor authority, exclusive Listener Supervisor authority/current generation, current listener epoch, current Entry session commit, canonical frozen ladder, canonical ATR, and authenticated sender identity. It SHALL consume ADR-016 `RAPI_ALERT_OBSERVED(ConnectionOpened/LoginComplete)` derived UP state and the committed `SUBSCRIPTION_VERIFIED` state produced by Rithmic-listener evidence, State Evaluator decision, and Health Durable Writer persistence; obsolete `CONNECTION_UP`, `LOGIN_UP`, `SUBSCRIPTION_ACTIVE`, and normative `ACTIVE` fact names SHALL NOT be canonicalized. Startup SHALL reach exactly one terminal result, `READY_LOCKED` or `FAILED`, before a separately governed post-startup deployment/trading decision can evaluate `TRADING_PERMITTED`; that state contributes no startup evidence. Current production cannot reach `READY_LOCKED` while `DEBT-2026-07-17-016` remains unresolved.

## 17. Approval sequencing

1. Treat approved ADR-014 as the fixed governing dependency and independently review ADR-015 and ADR-016.
2. Review each supporting draft, this amendment ledger, and the conflict matrix without reopening or weakening ADR-014.
3. If ADR-015/ADR-016 and supporting amendments are approved, obtain separate canonical-incorporation authorization; approval alone does not apply this ledger.
4. After authorized incorporation, re-run bidirectional traceability/debt review and record exact canonical versions.
5. Only then consider a separate implementation authorization. Approval/incorporation never implies verification, deployment, `READY_LOCKED`, Bucket 0 completion, Bucket 1 authorization, or trading.

## 18. Phase 3C1 normative architecture disposition

This section supersedes the rejected Phase 3B storage and traceability incorporation proposal. It records draft reconciliation only. It does not propose canonical incorporation of ADR-015, ADR-016, the Runtime Authority Store Schema, the executable SQL, or the historical Phase 3B registry.

### 18.1 Executable store contract

- The explanatory contract is `docs/architecture/runtime_authority_store_schema_DRAFT.md`; its executable expansion is `docs/architecture/runtime_authority_store_schema_v2_DRAFT.sql`.
- Proposed store identity is SQLite `user_version=2`, thirty-seven `STRICT` tables, SQLite-native declared types, explicit same-database foreign keys/actions, exact checks, indexes, and triggers.
- Writer authorization is registry-version 2 and is exclusive per active `(table_name, operation)` scope. The registry binds writer identity, writer build/contract identity, activation sequence, retirement sequence, and registry version. The Runtime Authority Store Transaction Coordinator remains mechanical only.
- `listener_current` and `listener_state_transitions` belong to Listener State Writer; restart incident and `listener_restart_outcomes` rows belong to Listener Incident Writer; acknowledgements belong to Listener Acknowledgement Writer; `bridge_generations` belongs only to Bridge Generation Writer; `subscription_verifications` belongs to Health Durable Writer.
- `TX-LSN-STOP-COMPLETE` performs the exact `STOPPING -> STOPPED` listener transition. `TX-LSN-EXECUTION-START` includes Listener Incident Writer. `TX-LSN-RATE-EXHAUSTED` deterministically produces `LISTENER_FAILED`, an incident terminal-outcome reference, and a durable `RECOVERY_RATE_LIMITED_FAILED` row in `listener_restart_outcomes`.
- Store validation is read-only. Quarantine uses the external Runtime Authority Recovery Evidence Writer and never writes to the corrupt store. Restore/reinitialization, version-conflict rejection, initial bootstrap, and any future predecessor-bound migration use their separate closed envelopes.
- No approved predecessor schema artifact/hash was established. Version 2 is the initial governed bootstrap proposal. Unidentified legacy stores are quarantined; positive authority import is prohibited until a separate predecessor-bound import/migration contract is governed.

### 18.2 Exact Entry Session destinations

ADR-014 remains unchanged: Session-lock policy is the sole eligibility and rollover-decision authority, and Entry Agent Session Commit Writer is the sole durable writer and executor. The supporting draft permits only these destinations:

| Source | Exact permitted destinations |
|---|---|
| `NO_CURRENT_SESSION_CONTEXT` | `CANDIDATE_PENDING`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` |
| `STALE_PRIOR_SESSION_BLOCKED` | `CANDIDATE_PENDING`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` |
| `CANDIDATE_PENDING` | `CANDIDATE_VALIDATED`, `CANDIDATE_REJECTED`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` |
| `CANDIDATE_VALIDATED` | `COMMITTING`, `CANDIDATE_REJECTED`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` |
| `CANDIDATE_REJECTED` | `CANDIDATE_PENDING`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` |
| `COMMITTING` | `CURRENT_CONTEXT_READY`, `COMMIT_FAILED`, `COMMITTED_FAIL_CLOSED`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` |
| `COMMIT_FAILED` | `COMMITTING`, `CANDIDATE_REJECTED`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` |
| `COMMITTED_FAIL_CLOSED` | `CURRENT_CONTEXT_READY`, `SESSION_PROJECTION_DIVERGED`, `STALE_PRIOR_SESSION_BLOCKED`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` |
| `CURRENT_CONTEXT_READY` | `CANDIDATE_PENDING`, `STALE_PRIOR_SESSION_BLOCKED`, `SESSION_PROJECTION_DIVERGED`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` |
| `SESSION_PROJECTION_DIVERGED` | `COMMITTED_FAIL_CLOSED`, `CURRENT_CONTEXT_READY`, `STALE_PRIOR_SESSION_BLOCKED`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` |
| `SESSION_STORE_DEGRADED` | `NO_CURRENT_SESSION_CONTEXT`, `STALE_PRIOR_SESSION_BLOCKED`, `COMMITTED_FAIL_CLOSED`, `CURRENT_CONTEXT_READY`, `SESSION_STORE_CORRUPT` |
| `SESSION_STORE_CORRUPT` | `NO_CURRENT_SESSION_CONTEXT`, `STALE_PRIOR_SESSION_BLOCKED`, `COMMITTED_FAIL_CLOSED`, `CURRENT_CONTEXT_READY` |

Every unlisted transition is prohibited. Recovery classification and evidence do not transfer eligibility or rollover-decision authority away from Session-lock policy.

### 18.3 Startup, diagnostic, and traceability boundary

- `CONTROL_STORES_VERIFIED` and `SUPERVISOR_AUTHORITY_READY` consume exact schema/registry hashes, writer exclusivity, current-state/version/cursor relationships, terminal incident outcomes, acknowledgement/generation checks, health/subscription ownership, and the verified external recovery-evidence chain.
- The source-bound diagnostic inventory remains frozen at 31 registered GET service/path entries, 13 mutating entries, and 13 unique mutating URL patterns for source tree `704fd715cad3aad281c534f8337840e3aab96234`.
- The Phase 3B clause registry is historical rejected evidence. Full semantic forward/reverse traceability is intentionally deferred to Phase 3C2 and may be rebuilt only against independently accepted Phase 3C1-R1 hashes.
- Coordinated package approval is not possible in Phase 3C1. ADR-015 and ADR-016 remain unapproved; every supporting specification and schema remains draft and noncanonical; canonical incorporation, implementation, runtime verification, deployment, `READY_LOCKED`, `TRADING_PERMITTED`, Bucket 0 completion, Bucket 1 work, and trading remain unauthorized.

## 19. Phase 3C1-R1 superseding proposed amendment set

This proposal supersedes section 18 only for F1-F8 readiness. Future canonical incorporation would additionally:

- adopt schema-v2's exact Gregorian `YYYY-MM-DD` and six-fraction UTC constraints, 38-table/500-column/124-FK/60-route/14-trigger inventory, external prepared-evidence binding for store recovery rows, and reproducible republished hashes;
- adopt registry retirement-before-successor enforcement and delimiter-safe nine-field serialization;
- make cancellation's only listener self-edge an exact `TX-LSN-CANCEL` `SUSPECT -> SUSPECT`, and prohibit direct terminal incident insertion;
- adopt the 55-operation catalog, including supervisor/lease, listener epoch/start/pending, registry/producer/session-reference, store-recovery-completion, and bridge-initialization operations; `TX-LSN-FENCE` includes Listener Epoch Writer;
- bind subscription proof to exact producer sequence, symbol/contract session, request/provider/evaluator/freshness, current epoch/bridge generation, proof/integrity, and commit identities;
- add the five-row termination evidence relationship, exact SQL vocabularies, and deterministic concrete/absence/uncertainty basis;
- adopt `RANDLE-RECOVERY-JCS-1`, bounded JSONL, exact Windows write-through replacement/readback semantics, no false directory-flush claim, and evidence-only authority;
- adopt complete bootstrap/restore/reinitialization candidate rows/insertion order and explicit post-replacement Entry/Runtime initialization; and
- remove current migration testing. Migration would exist only under a future separately governed predecessor-bound specification.

These are proposals only. ADR-014 remains approved and unchanged; ADR-015/016 remain unapproved. Phase 3C2 semantic traceability remains deferred until independent acceptance of exact Phase 3C1-R1 hashes.
