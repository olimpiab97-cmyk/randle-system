# ADR-015 - Listener Lifecycle Supervision, Epoch Fencing, and Restart Cancellation

## 1. Status

**DRAFT - NOT APPROVED**

**Draft date:** 2026-07-17

**Draft version:** Phase 3C1-R1 targeted normative remediation

**Decision authority:** None until explicit architecture approval.

**Implementation authorization:** None. This draft does not authorize process creation/termination, production code changes, restart, deployment, or trading.

## 2. Context

During the controlled 2026-07-17 shutdown, Executor accepted a fresh listener tick but evaluated its mutating stale watchdog before recording that tick in watchdog state. Executor terminated the recovered listener, started a replacement, and then logged recovery from the accepted event. It repeated the lifecycle action and created another listener authority epoch.

Executor also exposes diagnostic GET routes and an entry safety predicate that call the same mutating watchdog builder. Existing architecture assigns market-data truth to the listener, execution truth to Executor, and projections to read surfaces, but does not assign a single listener process-lifecycle owner, restart request contract, pending cancellation, epoch fence, or exactly-once restart incident.

## 3. Decision

### 3.1 Authoritative invariant

`Listener Supervisor` is the only authority authorized to start, stop, replace, or fence the full Rithmic listener process and allocate a new Listener Authority Epoch.

Executor is a health-data producer, fail-closed entry gate, and restart requester. Executor SHALL NOT directly terminate, start, or replace the listener.

One fenced restart incident SHALL produce at most one effective replacement listener and one new Listener Authority Epoch. Repeated level-triggered restart is prohibited.

### 3.2 Ownership boundaries

| Owner | Authority |
|---|---|
| Listener Supervisor | full listener process lifecycle, durable supervisor state, listener epoch allocation/fencing, restart incident decision and completion |
| Rithmic listener | accepted market data, completed bars, ATR/RMA inputs/observations, direct connection/subscription evidence within its current epoch |
| Bridge Controller within the listener | executes exactly one authenticated Supervisor-fenced bridge child command and reports exact results; owns no bridge incident/fence/generation grant and never the full listener epoch |
| Executor | accepted delivery evidence, symbol freshness observations, entry blocking, restart request publication, execution truth |
| Trade Manager | trade lifecycle and execution-management state; consumer of fenced current-epoch market publication |
| Entry Agent | entry lifecycle and readiness projection; consumer of current listener epoch/bar/ATR/session identities |
| Command Center | display only |
| Launcher/manual startup | bounded authenticated bootstrap/command client of the Listener Supervisor; SHALL NOT start, adopt, stop, replace, fence, or monitor the listener as a lifecycle owner |

### 3.3 Listener Authority Epoch

A `listener_epoch_id` is a monotonically ordered durable identity for one granted interval of full-listener publication authority. It SHALL include or reference:

- `supervisor_generation_id`;
- supervisor identity/version;
- listener process identity;
- granted symbol/contract set;
- epoch allocation sequence;
- epoch start time;
- authority lease/mutex identity where used;
- source/build identity; and
- prior epoch and transition reason.

Starting a new process does not make it authoritative until the supervisor durably grants the epoch. The new epoch SHALL NOT publish accepted current data until the old epoch is durably fenced. Old-epoch messages are rejected and audited.

#### 3.3.1 Supervisor generation and durable store

Exactly one supervisor generation SHALL hold the durable supervisor lease. Each successful lease acquisition SHALL atomically allocate a monotonically increasing `supervisor_generation_id`. Every listener epoch grant, fencing token, restart request acceptance, bridge-fence grant, execution command, child authority token, downstream acknowledgement, and completion record SHALL contain that generation. Messages from an earlier supervisor generation SHALL be rejected.

The Listener Supervisor SHALL use the one physical Runtime Authority Control Database defined jointly with ADR-016 at the absolute path resolved once at startup from `%LOCALAPPDATA%\RandleRuntimeData\control\runtime_authority_v2.sqlite3`. The resolved path SHALL be recorded in startup evidence. The explanatory normative contract is `docs/architecture/runtime_authority_store_schema_DRAFT.md`; its mechanically executable v2 DDL is `docs/architecture/runtime_authority_store_schema_v2_DRAFT.sql`. This is Pattern A: one SQLite database contains ownership-separated supervisor, listener-epoch, listener-lifecycle, listener-incident, acknowledgement, bridge, health, and termination tables so every declared foreign key is physically enforceable. Shared physical storage SHALL NOT merge authority ownership. Both schema artifacts remain draft, noncanonical, and unauthorized for runtime installation.

The in-process `Runtime Authority Store Transaction Coordinator` SHALL own the only read-write SQLite connection and SHALL mechanically serialize approved typed transaction plans; it owns no lifecycle, health, policy, or evidence decision. The closed logical writer allowlist is the Runtime Authority Store Schema section 7: `Supervisor Generation Writer` writes `supervisor_generations`/`supervisor_leases`; `Listener Epoch Writer` writes `listener_epochs`; `Listener State Writer` writes only `listener_current`/`listener_state_transitions`; `Listener Incident Writer` writes only listener incident, incident-transition, outcome, fence, execution, rehydration, policy, and expectation tables; `Listener Acknowledgement Writer` writes only `recovery_required_domains`/`domain_acknowledgements`; `Recovery Transaction Writer` alone writes `recovery_transactions`; `Bridge Generation Writer` alone writes `bridge_generations`; the ADR-016 Health Durable Writer writes bridge current/history/incidents/attempts/outcomes, health, producer, subscription, termination, and validated external-reference tables; `Projection Writer` alone writes `projection_cursors`; and `Store Incident Writer` alone writes `store_incidents`. The partial unique index on active `(table_name,operation)` registry scopes and the typed-plan authorizer SHALL reject a transaction plan that targets a table outside its named writer. The coordinator SHALL NOT originate, reinterpret, combine, or repair a domain decision.

The database SHALL use the exact Runtime Authority Store Schema section 2 configuration and section 4 tables. Listener current state SHALL exist only in `listener_current`; lifecycle history only in `listener_state_transitions`; restart incident/current version only in `listener_restart_incidents`; incident history only in `listener_restart_incident_transitions`; terminal result only in `listener_restart_outcomes`; fence/execution/rehydration only in their named tables; and authoritative domain acknowledgement only in `domain_acknowledgements`. Transactions spanning logical writers are prohibited except the closed writer sets named by the typed transaction catalog. ADR-016 bridge/health transactions remain authorized only by the State Evaluator and written through the exact Bridge Generation or Health Durable Writer routes. No local witness, cache, projection, or duplicate database may become a second identity authority.

A new supervisor generation MAY resume a previously durable fenced incident only by recording an adoption transition under the existing `restart_incident_id` and `restart_execution_id`. It SHALL NOT execute a stale in-memory command from the prior generation. An unreadable, corrupt, version-incompatible, or ambiguous store SHALL produce `SUPERVISOR_STORE_FAILED`, keep entries blocked, and prohibit listener start/adoption/restart until governed recovery.

#### 3.3.2 Exact listener storage and transaction binding

The Listener Supervisor lifecycle SHALL use only these Runtime Authority Store records:

| Domain fact | Sole durable record |
|---|---|
| current full-listener state/version/current incident | `listener_current` |
| full-listener transition history | `listener_state_transitions` |
| restart incident state/version/predicate/count | `listener_restart_incidents` |
| restart incident transition history | `listener_restart_incident_transitions` |
| terminal restart outcome | `listener_restart_outcomes` |
| no-cancel fence | `listener_fences` |
| exactly-one execution | `listener_execution_attempts` |
| recovery/rehydration state | `recovery_transactions`, `listener_rehydrations` |
| required authoritative acknowledgements | `recovery_required_domains` |
| accepted/rejected authoritative acknowledgement | `domain_acknowledgements` |

The closed ADR-015 listener transaction set is `TX-LSN-START`, `TX-LSN-RESTART-PENDING`, `TX-LSN-EPOCH-GRANT`, `TX-LSN-EPOCH-FENCE`, `TX-LSN-EPOCH-RETIRE`, `TX-LSN-CANCEL`, `TX-LSN-FENCE`, `TX-LSN-EXECUTION-START`, `TX-LSN-REHYDRATION-START`, `TX-LSN-ACK`, `TX-LSN-COMPLETE`, `TX-LSN-FAIL`, `TX-LSN-RATE-EXHAUSTED`, `TX-LSN-PLANNED-STOP`, and `TX-LSN-STOP-COMPLETE`. Supervisor generation/lease lifecycle uses `TX-SUP-GENERATION-CREATE`, `TX-SUP-LEASE-ACQUIRE`, `TX-SUP-LEASE-RENEW`, `TX-SUP-LEASE-RELEASE`, `TX-SUP-GENERATION-RETIRE`, and `TX-STORE-STALE-LEASE-FENCE`. Their exact preconditions, rows, writer sets, idempotency, expected versions, commit/readback, crash, replay, rollback, and reconstruction rules are Runtime Authority Store Schema sections 9, 11, and 14. A lifecycle, epoch, lease, or incident mutation outside that catalog is prohibited.

Every exact writer-set declaration SHALL include `Listener Incident Writer` for `TX-LSN-EXECUTION-START`. `TX-LSN-CANCEL` uses Listener Incident + Listener State Writers; **`TX-LSN-FENCE` uses Listener Incident + Listener State + Listener Epoch Writers and the epoch mutation is solely the Epoch Writer's item**; `TX-LSN-EXECUTION-START` uses Listener Incident Writer; `TX-LSN-REHYDRATION-START` uses Listener Incident + Recovery Transaction + Listener Acknowledgement + Listener State Writers; `TX-LSN-ACK` uses Listener Acknowledgement + Listener Incident Writers; `TX-LSN-COMPLETE`, `TX-LSN-FAIL`, and `TX-LSN-RATE-EXHAUSTED` use Listener Incident + applicable Recovery Transaction + Listener State Writers; and `TX-LSN-PLANNED-STOP`/`TX-LSN-STOP-COMPLETE` use Listener State Writer. The start/pending/epoch and supervisor-generation/lease writer sets are exactly Store Schema section 14.3. No broader listener writer set is legal.

Command Center SHALL NOT appear in `recovery_required_domains` or `domain_acknowledgements`. Its parity result cannot satisfy an acknowledgement, advance acknowledgement progress, or authorize `TX-LSN-COMPLETE`.

### 3.4 Supervisor state machine

The full-listener lifecycle SHALL use only the following closed transition relation:

```text
NONE -> STOPPED | STARTING | SUPERVISOR_STORE_FAILED
STOPPED -> STARTING
STARTING -> REHYDRATING | AMBIGUOUS_PROCESS_AUTHORITY | LISTENER_FAILED | STOPPING | SUPERVISOR_STORE_FAILED
REHYDRATING -> HEALTHY | SUSPECT | LISTENER_FAILED | FENCED | STOPPING | SUPERVISOR_STORE_FAILED
HEALTHY -> SUSPECT | FENCED | STOPPING | SUPERVISOR_STORE_FAILED
SUSPECT -> HEALTHY | SUSPECT [TX-LSN-CANCEL only] | FENCED | STOPPING | LISTENER_FAILED | SUPERVISOR_STORE_FAILED
FENCED -> REHYDRATING | LISTENER_FAILED | STOPPING | SUPERVISOR_STORE_FAILED
STOPPING -> STOPPED | LISTENER_FAILED | SUPERVISOR_STORE_FAILED
LISTENER_FAILED -> STARTING | STOPPING | SUPERVISOR_STORE_FAILED
AMBIGUOUS_PROCESS_AUTHORITY -> STOPPED | STARTING | SUPERVISOR_STORE_FAILED
SUPERVISOR_STORE_FAILED -> STOPPED
```

While a restart incident is `RESTART_PENDING`, the current full-listener state remains `SUSPECT`. A committed `RESTART_CANCELED` outcome atomically reevaluates that current state to `HEALTHY` or keeps it `SUSPECT`; the incident token is never a listener lifecycle state.

The associated restart-incident machine SHALL use only:

```text
RESTART_PENDING
  -> RESTART_CANCELED           (terminal incident outcome; no process action)
  |  RECOVERY_RATE_LIMITED_FAILED (terminal full-listener incident outcome; no process action)
  |  RESTART_FENCED
  -> RESTART_EXECUTING
  -> RESTART_REHYDRATING
  -> RESTART_COMPLETED | RESTART_FAILED
```

The incident record describes the durable decision/execution transaction and the current full-listener record describes operational eligibility. Both SHALL carry the same incident/recovery identity while that incident controls the listener, but neither record may substitute for the other's writer or evidence. `RESTART_CANCELED`, `RECOVERY_RATE_LIMITED_FAILED`, `RESTART_COMPLETED`, and `RESTART_FAILED` are incident terminal outcomes only. `STOPPED`, `STARTING`, `REHYDRATING`, `HEALTHY`, `SUSPECT`, `FENCED`, `STOPPING`, `LISTENER_FAILED`, `AMBIGUOUS_PROCESS_AUTHORITY`, and `SUPERVISOR_STORE_FAILED` are full-listener lifecycle states only. `RESTART_PENDING`, `RESTART_FENCED`, `RESTART_EXECUTING`, and `RESTART_REHYDRATING` are nonterminal restart-incident states only.

`SUSPECT` blocks new entry authorization for affected scope but does not itself authorize restart. `RESTART_PENDING` is cancellable. `RESTART_CANCELED` is the durable terminal outcome of that restart incident and is not a process action. The atomic pair `RESTART_FENCED` plus current-listener `FENCED` is the durable no-cancel boundary. Current-listener `LISTENER_FAILED` and incident outcome `RESTART_FAILED` remain separate fail-closed facts and require the recovery paths defined in the tables below.

Every transition not explicitly listed in the full-listener or restart-incident tables in section 3.4.2 is prohibited. A state or outcome SHALL NOT be inferred from process existence, projection data, a diagnostic read, or another state machine's token.

#### 3.4.1 Durable `RESTART_CANCELED` outcome

Only the Listener Supervisor State Evaluator, as transition authority, may authorize `RESTART_CANCELED`; only the Listener Incident Writer SHALL record its incident transition/outcome and only Listener State Writer SHALL record the resulting current-listener transition. Entry requires every cancellation condition in section 3.7, a successful compare-and-swap from the current `RESTART_PENDING` `incident_version`, and durable commit/readback before any caller is told that cancellation succeeded.

The durable cancellation record SHALL contain the restart incident ID, prior and committed incident versions, supervisor generation, listener epoch, affected feed/symbol scope, original stale boundary and predicate, accepted recovery event and intake/liveness commit identities, cancellation decision time, policy identity, post-cancellation reevaluation result, and integrity identity. It SHALL record that no listener fence, stop, replacement start, child authority token, or new listener epoch was allocated by the canceled incident. `RESTART_CANCELED` is the terminal state of the incident; `HEALTHY` or `SUSPECT` is the separately recorded current full-listener state and is not another incident outcome.

Within `TX-LSN-CANCEL`, after confirming the accepted recovery/liveness commit and before committing the incident outcome, the Listener Supervisor SHALL reevaluate the full current post-recovery evidence set. That typed transaction SHALL atomically write the transaction identity, incident transition, `RESTART_CANCELED` outcome, terminal incident update, listener transition, `listener_current` version, evidence references, and final metadata/readback. The resulting state SHALL be `HEALTHY` only when the canceled predicate and every other listener-level suspect condition are false; it SHALL be `SUSPECT` when any other listener-level condition remains unproven or degraded. When it remains `SUSPECT`, the State Writer SHALL commit the versioned self-edge `SUSPECT -> SUSPECT` with reason `CANCELLATION_REEVALUATION_REMAINS_SUSPECT`, expected prior version, same generation/epoch, current incident/outcome, and `TX-LSN-CANCEL` identity. That is the only legal listener self-edge. No intermediate committed cancellation lacking this reevaluation is legal. This reevaluation SHALL NOT reuse the canceled incident as a restart action.

`RESTART_CANCELED` SHALL NOT transition to `RESTART_FENCED` or current-listener `FENCED`, execute a stop/start, allocate an epoch, or be reopened. A later independently qualifying failure requires a new durable incident with a new stale boundary and incident ID and remains subject to debounce, cooldown, rate limits, and fencing. On supervisor restart, a durably canceled incident SHALL restore only as terminal cancellation evidence and SHALL cause no lifecycle action or retry.

#### 3.4.2 Closed state, outcome, and disposition registry

The following categories are disjoint. A token SHALL appear in exactly one category and SHALL NOT be used as an alias for a token in another category.

| Category | Closed members |
|---|---|
| Full-listener lifecycle state | `STOPPED`, `STARTING`, `REHYDRATING`, `HEALTHY`, `SUSPECT`, `FENCED`, `STOPPING`, `LISTENER_FAILED`, `AMBIGUOUS_PROCESS_AUTHORITY`, `SUPERVISOR_STORE_FAILED` |
| Restart-incident nonterminal state | `RESTART_PENDING`, `RESTART_FENCED`, `RESTART_EXECUTING`, `RESTART_REHYDRATING` |
| Restart-incident terminal outcome | `RESTART_CANCELED`, `RESTART_COMPLETED`, `RESTART_FAILED`, `RECOVERY_RATE_LIMITED_FAILED` |
| Shared-feed predicate | `SFF-01_LISTENER_EXITED`, `SFF-02_LISTENER_LEASE_LOST`, `SFF-03_BRIDGE_RECOVERY_EXHAUSTED` |
| Bridge-incident terminal outcome owned by ADR-016 | `FAILED_RECOVERY_EXHAUSTED` |
| Policy-validation disposition and startup failure reason | `SHARED_FEED_POLICY_INVALID` |
| Market-data-expectation state | `EXPECTATION_STARTUP_UNPROVEN`, `DATA_EXPECTED`, `DATA_NOT_EXPECTED`, `EXPECTATION_EXPIRED`, `DATA_NOT_EXPECTED_PLANNED_SHUTDOWN` |
| Per-symbol data-health state | `STALE`, `DATA_UNAVAILABLE` |
| ATR disposition | `RETAIN`, `INVALIDATE`, `REBUILD`, `REHYDRATE` |
| ATR invalidation reason | `DURABLE_HISTORY_GAP`, `DURABLE_HISTORY_CORRUPT`, `CONTRACT_IDENTITY_CHANGED`, `SESSION_VOLATILITY_RESET_REQUIRED` |

The Listener Supervisor State Evaluator is the sole transition authority for every full-listener and restart-incident row below. `listener_current` and `listener_state_transitions` are written only by Listener State Writer. Restart incident, incident-transition, outcome, fence, execution, and rehydration rows are written only by Listener Incident Writer. Required-domain and acknowledgement rows are written only by Listener Acknowledgement Writer. The Runtime Authority Store Transaction Coordinator is only the mechanical SQLite serializer.

| Full-listener state | Entry evidence | Durable representation | Permitted exits | Restart/recovery behavior | Readiness effect | Verification |
|---|---|---|---|---|---|---|
| `STOPPED` | No current granted listener process and a completed startup/shutdown or initial-store record | current listener-state row, process/epoch absence proof, reason | `STARTING` only by governed startup | Restore stopped; never infer or auto-start | Nonready | `RRV-LS-001`, `RRV-ST-001` |
| `STARTING` | Governed startup/restart execution exists and child identity is publication-fenced | execution/child token/intended epoch/start evidence | `REHYDRATING`, `AMBIGUOUS_PROCESS_AUTHORITY`, `LISTENER_FAILED`, `STOPPING`, `SUPERVISOR_STORE_FAILED` | Adopt the exact child/execution or remain blocked; never duplicate-start | Nonready | `RRV-LS-001`, `RRV-LS-002` |
| `REHYDRATING` | One granted new/current epoch awaits authoritative domain acknowledgements | recovery transaction and required acknowledgement identity set | `HEALTHY`, `SUSPECT`, `LISTENER_FAILED`, `FENCED`, `STOPPING`, `SUPERVISOR_STORE_FAILED` | Resume same recovery identity; Command Center cannot close it | Nonready | `RRV-LS-001`, `RRV-ATR-001`, `RRV-ST-001` |
| `HEALTHY` | Current epoch plus all required authoritative domain acknowledgements and no suspect predicate | current epoch/health/acknowledgement commit | `SUSPECT`, `FENCED`, `STOPPING`, `SUPERVISOR_STORE_FAILED` | Reprove after restart; process existence alone is insufficient | Listener gate eligible only with all other readiness gates | `RRV-LS-001`, `RRV-ST-001` |
| `SUSPECT` | One named current listener-health condition is degraded/unproven | exact predicate/evidence/stale boundary/current epoch | `HEALTHY`, authorized cancellation-only `SUSPECT`, `FENCED`, `STOPPING`, `LISTENER_FAILED`, `SUPERVISOR_STORE_FAILED` | Restore and reevaluate; `SUSPECT -> SUSPECT` is legal only for the exact `TX-LSN-CANCEL` evidence/transaction predicate | Blocks affected/all new entries | `RRV-LS-001`, `RRV-LS-003` |
| `FENCED` | Atomic `RESTART_PENDING -> RESTART_FENCED` transaction revokes current epoch publication | epoch fence, incident version, execution ID, fencing token | `REHYDRATING`, `LISTENER_FAILED`, `STOPPING`, `SUPERVISOR_STORE_FAILED` | Resume same execution; recovery data cannot unfence | Nonready; old epoch ineligible | `RRV-LS-001`, `RRV-LS-002` |
| `STOPPING` | Exact fenced or planned stop command accepted for the one execution identity | process handle/command/ack/result evidence | `STOPPED`, `LISTENER_FAILED`, `SUPERVISOR_STORE_FAILED` | `TX-LSN-STOP-COMPLETE` alone commits `STOPPING -> STOPPED`; no second stop/start incident | Nonready | `RRV-LS-002` |
| `LISTENER_FAILED` | Current listener startup/stop/rehydration operation fails with authoritative evidence | failure stage, process/epoch/incident/execution identities | `STARTING`, `STOPPING`, `SUPERVISOR_STORE_FAILED` | No automatic retry; retain evidence across restart | Nonready; entries blocked | `RRV-LS-002`, `RRV-LS-003` |
| `AMBIGUOUS_PROCESS_AUTHORITY` | Exact owned-process/adoption evidence cannot prove zero or one authoritative child | conflicting/unknown process identities and investigation evidence | `STOPPED`, `STARTING`, `SUPERVISOR_STORE_FAILED` | Prohibit another start until ambiguity is resolved durably | Nonready; entries blocked | `RRV-LS-002` |
| `SUPERVISOR_STORE_FAILED` | Runtime Authority Control Database integrity, writer routing, count, or current-authority invariant fails | store incident, failed checks, last verified cursor, recovery identity | `STOPPED` only after completed governed store recovery and zero-authoritative-process proof | No listener start/adopt/restart; restart does not clear | Nonready; entries blocked | `RRV-LS-002`, `RRV-FH-003` |

| Restart-incident state/outcome | Entry evidence | Durable representation | Permitted exits | Restart/recovery behavior | Readiness effect | Verification |
|---|---|---|---|---|---|---|
| `RESTART_PENDING` | Exactly one SFF predicate is proven after debounce and incident CAS succeeds | incident ID/version, predicate, stale boundary, evidence, policy identity | `RESTART_CANCELED`, `RECOVERY_RATE_LIMITED_FAILED`, `RESTART_FENCED` | Restore pending and revalidate; no process action from polling | Listener remains `SUSPECT`; nonready | `RRV-LS-001`, `RRV-LS-003` |
| `RESTART_FENCED` | Pre-fence revalidation and rate eligibility pass and the atomic incident/current-listener fence commits | incident/fence/execution/current epoch/supervisor generation | `RESTART_EXECUTING` only | Resume/adopt same execution; never cancel or allocate another | Nonready | `RRV-LS-001`, `RRV-LS-002` |
| `RESTART_EXECUTING` | Exact fenced stop/start command is accepted under the one execution identity | command/child token/process result evidence | `RESTART_REHYDRATING`, `RESTART_FAILED` | Resolve/adopt same effective child; no second effective restart | Nonready | `RRV-LS-002` |
| `RESTART_REHYDRATING` | Replacement listener is adopted/granted and authoritative domains are restoring | new epoch/recovery/acknowledgement set | `RESTART_COMPLETED`, `RESTART_FAILED` | Resume same recovery identity; no timeout to success | Nonready | `RRV-LS-001`, `RRV-ATR-001` |
| `RESTART_CANCELED` | Section 3.4.1 cancellation CAS and post-recovery listener reevaluation commit | terminal cancellation record plus atomic `HEALTHY`/`SUSPECT` current state | none | Restore terminal no-action evidence; later failure requires new incident | Depends on separate current listener state | `RRV-LS-001` |
| `RESTART_COMPLETED` | One new epoch and every authoritative-domain rehydration acknowledgement commit under the incident | terminal completion/new epoch/execution/acknowledgement record | none | Restore terminal; no duplicate action | Contributes only through current `HEALTHY` state | `RRV-LS-002`, `RRV-ST-001` |
| `RESTART_FAILED` | The fenced execution or rehydration fails before completion | terminal failure/stage/process/epoch/evidence record | none | No automatic retry; governed recovery creates a new incident after current-state reconciliation | Nonready; entries blocked | `RRV-LS-002`, `RRV-LS-003` |
| `RECOVERY_RATE_LIMITED_FAILED` | Section 3.11.7 current SFF incident is eligible but listener cooldown is active or the pre-fence durable count equals the maximum | terminal rate-limit record defined in 3.11.7 | none | Restore terminal; no action/reopen/retry; operator recovery is section 3.11.7 only | Both symbols blocked/nonready | `RRV-LS-003`, `RRV-ST-001` |

Every transition not listed as a permitted exit in either table is prohibited. Terminal incident outcomes have no exit. A later action SHALL use a new incident ID after the named recovery prerequisites; it SHALL NOT reopen, rewrite, or alias a terminal outcome.

`TX-LSN-STOP-COMPLETE` is the only stop-completion operation. Its preconditions are current `listener_current.lifecycle_state='STOPPING'`, exact expected `state_version`, current supervisor generation, an already fenced/retired listener epoch, authenticated process-exit or handle-release evidence for the exact owned process, no unresolved process-authority ambiguity, and a Listener Supervisor State Evaluator decision bound to that evidence. Listener State Writer atomically inserts one `listener_state_transitions` row with `STOPPING -> STOPPED`, resulting version `expected+1`, then updates `listener_current` to `STOPPED` with NULL listener epoch/current incident/recovery and the same transaction identity. The transition, current row, transaction/idempotency record, cursor, and readback hash are the complete evidence. Same key/same request is idempotent; changed input conflicts. A crash before COMMIT leaves `STOPPING`; a crash after COMMIT reconstructs `STOPPED` from the transition/current/readback identity and never issues another stop. Constraint, parent, routing, and readback failures use the exact schema-contract results and never synthesize `STOPPED`.

### 3.5 Restart request contract

Every restart request SHALL contain:

- `supervisor_generation_id`;
- `listener_epoch_id`;
- `observed_stale_timestamp_utc`;
- `decision_timestamp_utc`;
- `restart_incident_id`;
- `fencing_token`;
- requester identity and request sequence;
- expected `incident_version`;
- affected symbol(s) and resolved contracts;
- direct evidence references and health commit identity;
- requested action (`FULL_LISTENER_RESTART` only under this ADR); and
- reason code and supervisor-policy version.

The `fencing_token` is the supervisor-issued current-epoch capability/version presented with the request. Possession does not fence the listener and does not authorize the requester to act. The supervisor SHALL validate the token, current epoch, evidence, and incident before one transaction records incident `RESTART_FENCED` and current-listener `FENCED`.

`restart_incident_id` SHALL remain stable across duplicate requests for the same observed incident. Duplicate request receipt is a no-op except for audit/counter updates that do not create a second lifecycle action.

### 3.6 Accepted recovery data ordering

For a valid tick belonging to the current unfenced epoch, the authoritative order SHALL be:

1. validate epoch, symbol, contract, source time, duplicate identity, and freshness;
2. durably accept the event in the owning intake journal;
3. commit current-epoch/symbol liveness and accepted sequence;
4. publish the recovery/cancellation fact to the supervisor;
5. begin the matching unfenced `RESTART_PENDING` compare-and-swap cancellation transaction;
6. evaluate every remaining listener-level suspect condition from the post-intake-commit state; and
7. atomically commit the durable `RESTART_CANCELED` incident outcome and the deterministic current full-listener `HEALTHY` or `SUSPECT` state.

The stale evaluator SHALL NOT make a restart decision from the timestamp preceding an event already accepted for that epoch.

### 3.7 Pending restart cancellation

A fresh accepted same-epoch event SHALL cancel a matching pending restart when all are true:

- the incident remains `RESTART_PENDING`;
- the listener epoch has not been fenced;
- the event belongs to the same epoch and affected symbol/feed scope;
- event source time/sequence is newer than the observed stale boundary; and
- direct health evidence no longer satisfies the restart predicate.

Cancellation SHALL be durable and idempotent. After incident `RESTART_FENCED` and current-listener `FENCED` commit, old-epoch data cannot cancel the restart and is rejected as fenced, even if it arrives late.

The Listener Supervisor State Evaluator is the single transition authority for restart-incident state; Listener Incident Writer is the single incident/history/outcome writer; Listener State Writer is the single current-listener/history writer. Cancellation and `RESTART_PENDING -> RESTART_FENCED` SHALL be compare-and-swap transitions on `incident_version` within the durable supervisor transaction; the fence branch SHALL atomically set the current full-listener state to `FENCED`. The linearization point is the successful durable commit of one branch. A recovery fact is eligible to win only after its accepted intake/liveness commit is durable and before the `RESTART_FENCED` commit linearizes. The losing transaction SHALL reread the committed incident version and SHALL NOT perform a lifecycle effect. There SHALL be exactly one winner.

### 3.8 Restart decision and exactly-once execution

The supervisor SHALL revalidate direct current-epoch liveness immediately before fencing. If the predicate has cleared, it cancels. If it persists, the supervisor SHALL atomically:

- bind the incident ID to the current epoch and fencing token;
- bind the current `supervisor_generation_id` and allocate one `restart_execution_id`;
- record the final evidence and decision time;
- mark the incident `RESTART_FENCED` and the current full-listener state `FENCED` in the same transaction;
- revoke old-epoch publication authority; and
- issue one restart execution command.

Restart execution SHALL be edge-triggered from the durable `RESTART_PENDING -> RESTART_FENCED` transition paired atomically with current-listener `FENCED`. Polling a stale level, retrying a request, reading status, restarting Executor, or restarting the launcher SHALL NOT execute another effective restart.

Every stop/start attempt for the incident SHALL carry the durable `restart_execution_id` and current `supervisor_generation_id`. A replacement listener SHALL receive a one-use `child_authority_token` bound to `restart_execution_id`, intended new epoch sequence, executable/build identity, and parent supervisor generation. It SHALL remain publication-fenced until adopted and granted.

On supervisor recovery, the supervisor SHALL first inspect the durable execution record and OS process identity carrying that child token. If the matching child exists, it SHALL be adopted and SHALL NOT be started again. If absence is conclusively proven, the supervisor MAY retry the idempotent start under the same `restart_execution_id`; the retry SHALL NOT allocate a second incident or second effective epoch. Ambiguous process identity SHALL produce `AMBIGUOUS_PROCESS_AUTHORITY`, block entries, and prohibit another start.

Exactly one effective restart means no more than one replacement listener SHALL receive publication authority and no more than one new listener epoch SHALL be granted for the fenced incident, regardless of duplicate requests, command retries, supervisor crash, launcher restart, or missing completion acknowledgement.

### 3.9 Completion records

One full restart incident SHALL record:

- supervisor generation and incident version;
- incident/request/fencing identities;
- restart execution and child authority-token identities;
- old listener epoch and process identity;
- stop requested/completed/failed times;
- new process identity;
- new epoch allocation/grant time;
- rehydration start/completion/failure;
- affected symbols/contracts;
- bars/ATR restoration disposition;
- downstream acknowledgement identities; and
- final state and reason.

Stop failure, start failure, duplicate process discovery, lost authority mutex/lease, and rehydration failure remain one incident with explicit status. They do not silently create a second incident.

An initial `listener_restart_incidents` row SHALL be nonterminal. Listener Incident Writer may reach `TERMINAL` only by inserting the exact `listener_restart_outcomes` row and versioned incident-transition row before updating the incident in the same typed transaction. Incident, outcome, and incident transition SHALL share incident ID and completion transaction; incident and outcome SHALL share the identical optional recovery-transaction ID. The prior incident state/outcome mapping is closed by executable trigger. Direct terminal insertion, a cross-incident outcome, or any transaction/recovery mismatch is prohibited.

### 3.10 Bridge recycle versus full listener restart

A `Bridge Generation` identifies one RAPI bridge child within a listener epoch. A bridge recycle:

- is governed by ADR-016;
- changes `bridge_generation_id`;
- does not automatically change `listener_epoch_id`;
- does not authorize Executor to restart the listener;
- preserves accepted completed-bar and valid ATR/RMA authority; and
- produces a distinct bridge incident/completion record.

A full listener restart fences the old listener epoch, stops/replaces the listener process, allocates a new epoch, and invokes the downstream behavior in section 3.12.

### 3.11 Cross-symbol failure policy

#### 3.11.1 Physical-feed and declaration authority

Under production topology version `randle-rapi-feed-topology-v1`, NQ and YM share one physical RAPI MarketData connection, one RAPI bridge child, and one full listener process. They do not share symbol subscription, contract, tick-freshness, bar, or ATR authority. A topology that uses separate physical connections requires a new approved topology/policy version and SHALL NOT inherit this shared-failure rule by implication.

The Listener Supervisor is the sole runtime authority permitted to declare `SHARED_FEED_FAILURE`. Executor, listener, Bridge Controller, launcher, Trade Manager, Entry Agent, Command Center, diagnostic routes, and operators MAY publish authenticated evidence or commands within their existing boundaries but SHALL NOT directly declare the runtime state or perform the restart. The `Listener Supervision Policy Owner` owns the proposed policy schema and values; the `Architecture Governance Owner` approves a policy version; the `Deployment Authorization Owner` binds one approved policy SHA-256 to one deployment authorization. Those roles define/approve policy but do not become runtime lifecycle authorities.

#### 3.11.2 Governed policy artifact

The Supervisor SHALL load exactly one immutable deployment-bundle artifact at `config/runtime/listener_shared_feed_policy_v1.json`. The artifact SHALL use canonical UTF-8 JSON, reject duplicate keys, and contain the following closed schema. Values outside the allowed range, missing fields, additional control fields, an unapproved version, or a digest that differs from the deployment authorization SHALL produce `SHARED_FEED_POLICY_INVALID`, keep entries blocked, and prohibit automatic bridge recycle/full-listener restart.

| Field | Type | Default | Allowed value/range |
|---|---|---:|---|
| `schema_version` | integer | `1` | exactly `1` |
| `policy_id` | string | `listener-shared-feed-policy-v1` | exactly approved identifier |
| `topology_version` | string | `randle-rapi-feed-topology-v1` | exactly approved identifier |
| `physical_feed_scope` | enum | `RAPI_MARKET_DATA_CONNECTION` | exactly listed value |
| `required_symbols` | ordered string array | `["NQ","YM"]` | exactly NQ and YM for this version |
| `heartbeat_period_seconds` | integer | `1` | `1..2` |
| `lease_suspect_seconds` | integer | `3` | `3..5` and greater than heartbeat period |
| `lease_unknown_seconds` | integer | `5` | `5..10` and greater than suspect |
| `listener_control_probe_attempts` | integer | `2` | `2..3` |
| `listener_control_probe_interval_seconds` | integer | `1` | `1..3` |
| `symbol_tick_stale_seconds` | integer | `30` | `15..60` |
| `symbol_data_unavailable_seconds` | integer | `90` | `60..180` and greater than stale |
| `shared_connection_debounce_seconds` | integer | `15` | `5..60` |
| `shared_all_symbol_debounce_seconds` | integer | `15` | `10..60` |
| `pre_fence_revalidation_max_age_seconds` | integer | `2` | `1..5` |
| `subscription_recovery_attempts` | integer | `3` | `1..3` |
| `subscription_attempt_wait_seconds` | integer | `5` | `3..15` |
| `bridge_recycle_cooldown_seconds` | integer | `60` | `30..300` |
| `bridge_recycle_rate_window_seconds` | integer | `900` | `600..1800` |
| `max_bridge_recycles_per_window` | integer | `3` | `1..3` |
| `bridge_recovery_timeout_seconds` | integer | `180` | `60..300` |
| `listener_restart_cooldown_seconds` | integer | `300` | `120..900` |
| `listener_restart_rate_window_seconds` | integer | `1800` | `900..3600` |
| `max_listener_restarts_per_window` | integer | `2` | `1..2` |
| `market_calendar_id` | string | `cme-index-market-data-v1` | exactly the deployment-approved identifier |
| `market_calendar_version` | positive integer | `1` | exactly the deployment-approved version |
| `market_calendar_sha256` | string | deployment bound | exactly 64 lowercase hexadecimal characters matching deployment authorization |

Every nondefault value requires a new policy version, rationale, Architecture Governance approval, deployment authorization, artifact digest, and traceability record. Environment variables, command-line values, source-code constants, launcher defaults, status files, and projections SHALL NOT override these values. Policy time calculations SHALL use the Supervisor monotonic clock; UTC timestamps remain audit fields only.

##### 3.11.2.1 `SHARED_FEED_POLICY_INVALID`

`SHARED_FEED_POLICY_INVALID` is a deterministic policy-validation disposition and startup failure reason. It is not a full-listener lifecycle state, restart-incident state/outcome, SFF predicate, health state, or process-termination reason.

The `Listener Supervision Policy Evaluator` is the sole evaluator and disposition authority. Its input identity SHALL contain the resolved artifact path, canonical bytes SHA-256, schema version, policy ID, topology version, deployment-authorization ID and bound digest, evaluator build, startup attempt, and evaluation sequence. The `Listener Incident Writer` SHALL durably write the result to `shared_feed_policies` through `TX-POLICY-VALIDATE` and the mechanical transaction coordinator. The record SHALL contain every failed field/rule, expected value/range, observed type/value or absence, duplicate/additional-key evidence, approval/deployment mismatch, exact reason code, evaluation time, and integrity identity.

Entry occurs when any required artifact, schema, identifier, type, range, cross-field constraint, approval, deployment binding, or digest validation fails. At startup it SHALL terminate the attempt as `FAILED` with reason `SHARED_FEED_POLICY_INVALID` before listener/bridge process start or authority grant. At runtime, discovery of a mismatch SHALL enter current-listener `SUSPECT`, block both symbols and new lifecycle fences, preserve the currently verified policy identity as historical evidence, and require controlled shutdown; it SHALL NOT trigger speculative bridge recycle or listener restart.

The disposition survives supervisor/process restart. It has no automatic retry or normal-state transition. Recovery requires the Policy Owner to issue a corrected versioned artifact, Architecture Governance to approve that exact version, Deployment Authorization to bind its exact digest, and a new startup attempt to record `POLICY_VALID` for the new input identity. An operator SHALL NOT edit, waive, or reinterpret the failed artifact in place. `SHARED_FEED_POLICY_INVALID` blocks `PRESTART_VALIDATED`, `SUPERVISOR_AUTHORITY_READY`, `MARKET_DATA_EXPECTATION_READY`, listener/bridge grants, and terminal `READY_LOCKED`. Verification requirements are `RRV-LS-003`, `RRV-ST-001`, and `RRV-GOV-001` positive-valid, negative-field/range/digest, restart-survival, no-process-action, and corrected-version recovery cases.

#### 3.11.3 Market-data-expected authority

The `Market Data Expectation Evaluator`, a policy subsystem inside the Listener Supervisor, is the sole runtime owner of `market_data_expected` state. It does not own feed lifecycle. It SHALL consume only:

- the immutable deployment-bundle calendar `config/runtime/market_data_expectation_calendar_v1.json`, whose identifier, version, and SHA-256 match the governed policy and deployment authorization;
- the Supervisor-owned current symbol/contract subscription intent;
- the Supervisor-owned startup, running, and planned-shutdown lifecycle state; and
- a healthy monotonic clock correlated to recorded UTC at supervisor-generation start.

The calendar producer is the `Market Session Calendar Policy Owner`. The artifact SHALL use canonical UTF-8 JSON, reject duplicate keys and additional fields, and contain `schema_version=1`, `calendar_id`, `calendar_version`, `timezone`, `valid_from_utc`, `valid_through_utc`, and an ordered array of nonoverlapping expected-data intervals with `start_utc`, `end_utc`, and `reason`. Architecture Governance SHALL approve the version and Deployment Authorization SHALL bind its SHA-256. The Listener Supervisor SHALL verify the artifact before granting a listener epoch.

The evaluator SHALL durably publish one of `EXPECTATION_STARTUP_UNPROVEN`, `DATA_EXPECTED`, `DATA_NOT_EXPECTED`, `EXPECTATION_EXPIRED`, or `DATA_NOT_EXPECTED_PLANNED_SHUTDOWN`, with calendar identity/digest, subscription-intent version, supervisor generation, listener epoch where granted, effective interval, evaluation time, and expiration. Its consumers are the Supervisor per-symbol/shared-failure evaluators and startup readiness. Executor, Entry Agent, Trade Manager, and Command Center MAY consume a signed current-state snapshot for blocking/display only and SHALL NOT change the classification.

At startup the state SHALL be `EXPECTATION_STARTUP_UNPROVEN` until artifact integrity, deployment binding, clock correlation, interval coverage, and current subscription intent all verify. The evaluator SHALL recompute at every calendar boundary and subscription/startup/shutdown transition. The state expires immediately when `valid_through_utc` is reached, clock correlation is lost, the bound artifact changes, or the subscription-intent version no longer matches; expiry enters `EXPECTATION_EXPIRED`, blocks entries/readiness, and prohibits staleness-based recycle/restart. Planned shutdown SHALL durably enter `DATA_NOT_EXPECTED_PLANNED_SHUTDOWN` before stop/fence activity and SHALL NOT satisfy a recovery predicate. Absence of ticks, quiet market, a stale file, or a projection SHALL NOT produce `DATA_NOT_EXPECTED`.

#### 3.11.4 Per-symbol conditions

Freshness SHALL be evaluated per exact symbol/contract only while current topology, session calendar, subscription intent, and market-data-expected state are positively established. Quiet-market or planned-closed intervals SHALL produce `DATA_NOT_EXPECTED`, not staleness.

- No accepted current-generation tick for `symbol_tick_stale_seconds` produces per-symbol `STALE`, blocks new entries for that symbol, and permits observation/resubscription only.
- Persistence of that condition for `symbol_data_unavailable_seconds` produces per-symbol `DATA_UNAVAILABLE` and permits the ADR-016 subscription-recovery procedure.
- One-symbol stale/unavailable/subscription failure SHALL NOT declare shared-feed failure, recycle the shared bridge solely for that symbol, or restart the listener.
- Global maximum/minimum tick age, cross-symbol OR aggregation, projection age, endpoint failure, prior-epoch evidence, and file timestamps SHALL NOT establish any lifecycle predicate.

#### 3.11.5 Bridge recycle conditions

Bridge recycle remains an ADR-016 action within the current listener epoch. It MAY become pending only from an ADR-016 closed predicate based on current-generation process exit, an unrecovered documented RAPI connection/engine condition, or all-required-symbol subscription recovery exhaustion. `ConnectionBroken` begins the configured connection debounce because the RAPI SDK owns automatic connection recovery; `ConnectionOpened` or later accepted current-generation connection/login/subscription/tick evidence cancels the unfenced incident. `LoginFailed` blocks startup/current feed authority and requires its exact classification under ADR-016; it SHALL NOT by itself trigger an automatic full-listener restart.

The Supervisor SHALL permit no new automatic bridge recycle during `bridge_recycle_cooldown_seconds`. Before allocating a bridge execution, it SHALL count durable `BRIDGE_EXECUTION_STARTED` records whose Supervisor-monotonic start times fall within the current `bridge_recycle_rate_window_seconds`. If the count equals `max_bridge_recycles_per_window`, the pending incident SHALL transition without process action to `FAILED_RECOVERY_EXHAUSTED`, both symbols SHALL remain blocked, and the evidence SHALL become eligible for `SFF-03`. A count greater than the governed maximum is an impossible policy/store invariant violation: it SHALL enter `SUPERVISOR_STORE_FAILED`, perform no process action, block both symbols, and require governed store recovery; it SHALL NOT be relabeled as exhaustion. If the last permitted execution fails to establish one ready generation within `bridge_recovery_timeout_seconds`, that same incident SHALL transition to `FAILED_RECOVERY_EXHAUSTED` immediately. No implicit retry, extra attempt, new incident, process/supervisor/launcher restart, supervisor-generation change, wall-clock change, or operator interpretation SHALL reset or bypass the durable rolling-window count. A successful ready generation completes the incident and does not authorize another recycle while cooldown or the maximum count applies.

`FAILED_RECOVERY_EXHAUSTED` is the terminal bridge-incident outcome shared with ADR-016. It means either (a) the pre-execution durable rolling-window count already equals the governed maximum, so no new bridge process action is legal, or (b) the last permitted `BRIDGE_EXECUTION_STARTED` failed to establish one `BRIDGE_GENERATION_READY` generation before the governed recovery deadline. The Listener Supervisor State Evaluator SHALL cause the Health Durable Writer to commit/read back this outcome in the ADR-016 health control store under the existing bridge incident ID and version. The record SHALL contain supervisor generation, listener epoch, old/intended bridge generation, policy version/digest, monotonic window bounds, counted execution IDs, exhaustion branch, recovery deadline when applicable, current connection/login/subscription evidence, absence of a ready generation, immediate revalidation result, and integrity identity. The outcome authorizes no implicit bridge retry and survives listener, supervisor, launcher, and process restart. It becomes input to `SFF-03` only through the separate debounce, revalidation, listener-rate-limit, and fencing rules below; it does not itself restart the listener or allocate an epoch.

#### 3.11.6 Full-listener shared-failure predicates

A full-listener restart affecting NQ and YM requires the Listener Supervisor to durably classify one and only one current-epoch predicate:

- `SFF-01_LISTENER_EXITED`: the Supervisor's exact owned Windows process handle reports exit for the current listener PID/creation identity; exit code/time and absence of a later adopted current-epoch process are durably verified.
- `SFF-02_LISTENER_LEASE_LOST`: all of the following pre-action evidence is simultaneously true: (a) the Supervisor's durable epoch grant identifies the exact current listener PID/creation identity and unexpired epoch scope; (b) Health Event Ingress has accepted no authenticated listener lease heartbeat for that identity for `lease_unknown_seconds`; (c) the Supervisor's authenticated command channel receives no valid challenge response for `listener_control_probe_attempts`, separated by `listener_control_probe_interval_seconds`; (d) Health Event Ingress has accepted no authenticated current-epoch listener publication newer than the stale boundary; and (e) the Supervisor's exact owned Windows process handle reports that the granted process still exists, so `SFF-01` does not apply. Inputs (b) and (d) come from Health Event Ingress, input (c) comes from the Supervisor command-channel verifier, and input (e) comes from the Supervisor OS Process Adapter. None is produced by a restart request, fence, stop, replacement, projection, or the decision being evaluated. Heartbeat silence, command failure, publication silence, or process existence alone is insufficient.
- `SFF-03_BRIDGE_RECOVERY_EXHAUSTED`: ADR-016 has durably completed the current-epoch bridge incident as `FAILED_RECOVERY_EXHAUSTED`, the configured bridge cooldown/rate/timeout conditions are satisfied, no ready current-generation bridge exists, and immediate revalidation finds no qualifying recovery evidence.

Connection loss, login failure, one/all-symbol tick staleness, one subscription failure, all-symbol subscription failure before bridge recovery exhaustion, health persistence failure, projection staleness, diagnostic failure, and process disappearance without exact owned-handle/intent evidence SHALL NOT directly establish full-listener failure. `UNKNOWN` in any ADR-016 termination dimension SHALL NOT authorize automatic full-listener restart unless a separate `SFF-01`, `SFF-02`, or `SFF-03` is independently proven.

#### 3.11.7 Debounce, cancellation, cooldown, and escalation

`SFF-02` and `SFF-03` SHALL remain continuously true for `shared_connection_debounce_seconds`; any all-symbol corroboration SHALL overlap for `shared_all_symbol_debounce_seconds`. Before fencing, the Supervisor SHALL revalidate every required input from its named producer at an age no greater than `pre_fence_revalidation_max_age_seconds`. A fence or lifecycle result SHALL NOT be an input to that revalidation.

An accepted current-epoch listener heartbeat plus restored command/control for `SFF-02`, or an accepted ready bridge generation with connection/login and required subscriptions for `SFF-03`, SHALL cancel an unfenced incident. An accepted same-epoch tick that clears the underlying predicate SHALL commit before cancellation/evaluation under sections 3.6-3.8. Cancellation after the durable `RESTART_FENCED`/current-listener `FENCED` linearization point is prohibited.

After one effective full-listener restart, the Supervisor SHALL prohibit another automatic full restart for `listener_restart_cooldown_seconds`. Before `RESTART_PENDING -> RESTART_FENCED`, the Listener Supervisor State Evaluator SHALL read and bind the durable Supervisor-monotonic rolling window of effective `RESTART_EXECUTING` records; Listener Incident Writer performs only the authorized durable write. If the current SFF predicate remains proven but cooldown is active, or the pre-fence count equals `max_listener_restarts_per_window`, the same `RESTART_PENDING` incident SHALL transition without fence, stop, start, child token, or epoch allocation to terminal `RECOVERY_RATE_LIMITED_FAILED`. A count greater than the maximum is an impossible store invariant and SHALL enter `SUPERVISOR_STORE_FAILED`, not rate-limit failure.

`RECOVERY_RATE_LIMITED_FAILED` is a full-listener restart-incident terminal outcome and is semantically distinct from ADR-016 bridge outcome `FAILED_RECOVERY_EXHAUSTED`. Its entry evidence SHALL include supervisor generation, current listener epoch, restart incident/version, exact SFF predicate/evidence, policy version/digest, cooldown start/end when applicable, monotonic window bounds, counted restart execution IDs, maximum, pre-fence revalidation, decision time, and integrity identity. The Listener Supervisor State Evaluator is its sole transition authority. Listener Incident Writer SHALL insert the terminal `RECOVERY_RATE_LIMITED_FAILED` row in `listener_restart_outcomes`, update `listener_restart_incidents.current_outcome_id` to that row and the incident state to terminal, and preserve the terminal relationship across restart. Listener State Writer SHALL separately write the resulting listener transition/current row. The exact deterministic resulting listener state is `LISTENER_FAILED`; no policy-selected alternative is permitted.

The outcome sets the current listener state exactly to `LISTENER_FAILED`, keeps NQ and YM blocked, survives listener/supervisor/launcher/process restart, and has no permitted exit, reopen, automatic retry, or implicit process action. It is not an SFF predicate and cannot supply `SFF-03`; rather, it is the terminal disposition of a listener incident whose SFF predicate was already independently proven. The Supervisor SHALL NOT reset or bypass cooldown/window evidence through process restart, supervisor generation change, launcher restart, wall-clock change, incident renaming, or operator interpretation.

The only recovery path is an authenticated `RESUME_AFTER_LISTENER_RATE_LIMIT` operator command after the durable monotonic cooldown has ended and the rolling count is below the governed maximum. The command SHALL acknowledge the terminal incident without changing it, revalidate policy/store/current process and SFF evidence, and either (a) record recovery-without-action when the SFF predicate cleared or (b) create a new `RESTART_PENDING` incident with a new incident ID when the predicate remains proven. If eligibility is still false, the command deterministically returns `RATE_LIMIT_STILL_ACTIVE` and performs no lifecycle action. Verification SHALL cover cooldown and maximum boundaries, count-greater-than-maximum store failure, restart survival, no retry/reopen, cleared-predicate recovery, new-incident recovery, and ineligible operator command under `RRV-LS-003` and `RRV-ST-001`.

### 3.12 Deterministic downstream and ATR behavior

`RETAIN` means keep the verified canonical finalized-bar sequence and RMA accumulator unchanged. `INVALIDATE` means mark a precisely bounded canonical suffix unusable without deleting its audit history. `REBUILD` means calculate a new canonical sequence from the earliest complete verified input required by the approved RMA contract. `REHYDRATE` means load and verify an existing durable canonical sequence without reseeding it.

| Case | Finalized bars | Incomplete minute | Canonical RMA/ATR | Required state |
|---|---|---|---|---|
| Bridge recycle in the same listener epoch | `RETAIN` | `REHYDRATE` from the gap-free, duplicate-free current-epoch tick journal; if proof fails, discard only the incomplete minute as `BRIDGE_GAP_INCOMPLETE_MINUTE_DISCARDED` | `RETAIN`; bridge generation alone SHALL NOT invalidate or rebuild it | Affected symbols remain `REHYDRATING` until the new generation, subscriptions, bar cursor, and retained ATR identity agree |
| Same-epoch symbol subscription recovery | `RETAIN` for that symbol | `REHYDRATE` under the same journal proof; otherwise discard only that symbol's incomplete minute | `RETAIN`; missing recovery ticks SHALL NOT rewrite finalized ATR | That symbol remains blocked/`REHYDRATING`; the other symbol is unchanged |
| Evidence carrying a stale listener epoch or stale bridge generation | Reject and quarantine; SHALL NOT append | Reject | `RETAIN` current authority; stale evidence SHALL NOT invalidate, rebuild, or rehydrate it | Record fenced/stale evidence; no current-state transition |
| Legitimate full listener restart / new listener epoch | `REHYDRATE` exact durable finalized history; old incomplete minute is fenced and SHALL cross the boundary only when complete journal proof succeeds | Fence, then `REHYDRATE` only on complete proof; otherwise discard | Apply the closed mapping below; process restart alone requires `RETAIN` through verified rehydration | All downstream consumers enter `REHYDRATING` and reject the old epoch |
| Cold startup | `REHYDRATE` from local durable canonical authority | Rehydrate only with complete journal proof; otherwise discard | Apply the closed mapping below | Remain `REHYDRATING` or `WARMUP`; no file existence/process reachability release |
| Startup recovery after interrupted rehydration | Resume the durable recovery transaction and `REHYDRATE`; never infer completion | Same rule as the interrupted case | Resume the recorded disposition; SHALL NOT choose a new disposition implicitly | Remain fail-closed until the original recovery identity completes |

For a new listener epoch, cold startup, or startup recovery, the following mapping is exhaustive:

- exact continuous durable history and matching symbol/contract identity: `RETAIN` by verified `REHYDRATE`, record `ATR_CONTINUITY_PRESERVED`;
- `DURABLE_HISTORY_GAP`: `INVALIDATE` from the first untrusted finalized bar, `REBUILD` from the earliest complete verified sequence, and remain `WARMUP` until the canonical minimum is satisfied;
- `DURABLE_HISTORY_CORRUPT`: quarantine the corrupt source, `INVALIDATE` its bounded sequence, `REBUILD` only from a separately verified local canonical source, and remain fail-closed if none exists;
- `CONTRACT_IDENTITY_CHANGED`: archive the old-contract sequence, create a separate new-contract sequence, `REBUILD` without combining contracts, and remain `WARMUP` until complete; and
- `SESSION_VOLATILITY_RESET_REQUIRED`: archive the prior accumulator and `REBUILD` from the exact boundary required by the separately approved volatility/session contract.

No other reason is legal. `otherwise invalid`, bridge recycle, reconnect, projection failure, endpoint failure, listener process restart by itself, or implementation preference SHALL NOT invalidate or rebuild ATR/RMA.

| Event | Executor | Trade Manager | Entry Agent | Command Center |
|---|---|---|---|---|
| Bridge generation change, same listener epoch | Accept only current generation publications; block affected symbol until coherent | Preserve trade truth; mark price input degraded/rehydrating | Preserve lifecycle/session truth; affected symbol remains `REHYDRATING` | Display same listener epoch, new generation, and exact ATR disposition |
| Legitimate full listener epoch change | Fence old epoch; accept new epoch only after grant | Preserve trade state; reject old-epoch prices | Preserve session state; require new epoch/bar/ATR coherence | Display transition; SHALL NOT present mixed epochs as `LIVE` |
| Cold/startup recovery | Keep intake publication-fenced until authority/recovery proofs pass | Restore/reconcile trade state independently | Restore committed session and remain `REHYDRATING` | Display component-specific blockers |

`REHYDRATING` SHALL close only after durable acknowledgements from the authoritative bars/ATR owner, Executor, Trade Manager, and Entry Agent name the same supervisor generation, listener epoch, symbol/contract set, last completed bar, ATR record/disposition, and incident ID. Missing or mismatched authoritative-domain acknowledgement SHALL remain fail-closed and SHALL NOT time out to LIVE.

Command Center SHALL NOT acknowledge, close, veto, mutate, or otherwise participate in Listener Supervisor `REHYDRATING`. Command Center parity MAY be checked later as the separate observational `COMMAND_CENTER_ALIGNED` startup gate. That gate consumes canonical owner identities and verifies display parity only; it supplies no feed-health, listener-lifecycle, session, or recovery authority and cannot change an authoritative domain state.

### 3.13 Diagnostic and read-side purity

GET, HEAD, health, status, debug, Command Center polling, and audit-query endpoints SHALL be pure observations. They SHALL NOT:

- create or update restart incidents;
- transition supervisor state;
- allocate epochs or fencing tokens;
- cancel or fence a restart;
- terminate/start a listener or bridge;
- update authoritative freshness timestamps; or
- persist domain/control state.

Restart requests require an explicit authenticated command/event boundary using a non-GET method or internal durable event channel. An entry-safety read MAY block an action but SHALL NOT request or execute restart as a side effect.

### 3.14 Startup and shutdown ownership

The official launcher SHALL start or attach to exactly one Listener Supervisor, submit one startup intent, wait for the bounded startup terminal result, record the handoff, and exit. After handoff it SHALL NOT poll listener health for lifecycle purposes, restart the supervisor, start/adopt/stop the listener, or retain a listener-restart loop. Executor SHALL NOT inherit supervision.

A manual full-listener restart SHALL be an authenticated idempotent `MANUAL_OPERATOR_RESTART` command to the Listener Supervisor. The supervisor SHALL create or reuse one durable incident and apply the same pending, revalidation, fence, execution, epoch, rehydration, and completion protocol. Direct OS termination is an emergency containment action only: it SHALL block entries and preserve evidence, and SHALL NOT authorize a replacement process or epoch.

If the Listener Supervisor crashes, lease expiry SHALL make listener publication and new entries ineligible. No other component SHALL inherit supervision. Recovery SHALL start a new supervisor generation through the governed supervisor-start command and the durable recovery protocol in this ADR.

Shutdown SHALL command the supervisor, record intent, fence publication, stop the listener/bridge, and verify final process/port state. Broad process killing and command-line matching alone are not lifecycle authority.

## 4. Consequences

- Executor loses direct listener process control.
- A dedicated durable supervisor state is required.
- Recovery ordering is defined at accepted-event commit, not HTTP arrival.
- Read endpoints become structurally incapable of restart.
- Bridge and full-listener incidents have separate identities and effects.
- Restart availability can be lower when authority is ambiguous, but the system remains fail-closed rather than creating repeated epochs.

## 5. Scope and isolation

This ADR governs full-listener process lifecycle, Listener Authority Epoch, restart requests/cancellation/fencing/completion, cross-symbol shared-feed decisions, and downstream epoch behavior.

It does not define feed-health storage mechanics or bridge-death evidence beyond the boundary delegated to ADR-016. It does not change session rollover, trading rules, ATR formula, Step 2/4, trade state, execution actions, or risk.

## 6. Required verification

Verification SHALL cover:

- recovery tick at the threshold boundary;
- accepted same-epoch tick commit before stale evaluation;
- pending restart cancellation before fence;
- durable `RESTART_CANCELED` entry, evidence, idempotency, post-cancellation `HEALTHY`/`SUSPECT` reevaluation, restart restoration, and prohibited canceled-to-fenced/execution transitions;
- every full-listener and restart-incident state/outcome in section 3.4.2, every listed permitted exit, and rejection of every unlisted transition or cross-category alias;
- `RECOVERY_RATE_LIMITED_FAILED` cooldown/count entry branches, durable schema, no-action/no-reopen/restart survival, store-count invariant failure, deterministic operator recovery, and distinction from bridge `FAILED_RECOVERY_EXHAUSTED`;
- `SHARED_FEED_POLICY_INVALID` classification, every schema/range/digest/approval failure, durable result, startup failure, runtime no-restart behavior, restart survival, and corrected-version recovery;
- Pattern A physical database schema, table-writer authorization, one read-write coordinator, enforceable same-database foreign keys, cross-table atomicity, crash/partial-write recovery, and rejection of a duplicate identity store or unauthorized table writer;
- old-epoch tick rejection after fence;
- genuinely stale listener causing exactly one restart/new epoch;
- duplicate requests, polls, Executor restart, and supervisor restart causing no duplicate action;
- pure diagnostic/read endpoints;
- failed stop/start, duplicate discovery, and rehydration failure;
- NQ-only, YM-only, symbol skew, and explicit shared-feed failure;
- policy schema/default/range/digest/owner validation; rejection of environment, launcher, source-constant, stale-policy, and unapproved overrides;
- Market Data Expectation calendar schema/owner/digest/intent/lifecycle/freshness/expiry/startup/shutdown behavior and rejection of tick-silence inference;
- each `SFF-01` through `SFF-03` positive and negative predicate, including the action-independent SFF-02 evidence chain, every debounce boundary, pre-fence revalidation, and recovery cancellation;
- bridge/listener cooldowns, durable monotonic rate windows, maximum-minus-one/final-attempt/maximum-equals-no-action boundaries, and exhausted/rate-limited escalation without implicit retry;
- identical ADR-015/ADR-016 `FAILED_RECOVERY_EXHAUSTED` persistence, restart survival, no-action, revalidation, SFF-03 eligibility, and escalation behavior;
- bridge generation change without listener epoch change;
- every section 3.12 RETAIN/INVALIDATE/REBUILD/REHYDRATE case and deterministic Executor/Trade Manager/Entry Agent/Command Center behavior; and
- cold/manual startup and controlled shutdown through one supervisor.

## 7. Relationship to existing authority and proposed amendments

- Constitution sections 3, 6, 12-17, 19, and 22 remain governing.
- Lifecycle Engine sections 11.3, 15-18, 26-35, 39-40, and 43 remain governing.
- ADR-012 continuity, rehydration, reset taxonomy, and read-side purity remain governing and require the clarifying epoch amendments registered with this draft.
- If separately approved and canonically incorporated, ADR-015 would assign the previously missing full-listener lifecycle owner and supply restart request, cancellation, fencing, and exactly-once behavior. This draft assigns no current authority.
- Runtime Authority, Lifecycle Vocabulary, startup/recovery, diagnostic purity, and verification specifications require the draft amendments registered for this decision.

## 8. Rejected alternatives

Rejected: Executor direct restart; mutating GET routes; level-triggered restart with cooldown only; global NQ/YM last-tick authority; process discovery as fencing; allocating an epoch before old authority is revoked; treating bridge recycle as a listener restart; and discarding valid ATR history on every process start.

## 9. Architectural Exit Criteria

### What invariant would approval and canonical incorporation establish?

The proposed invariant is that one durable Listener Supervisor owns full-listener lifecycle and epoch fencing; accepted recovery data commits before stale evaluation; unfenced pending restarts are cancellable; and one fenced incident executes at most one restart. This invariant is not canonical while the ADR remains unapproved.

### Why was the previous architecture insufficient?

It assigned market and execution truth but not process-lifecycle supervision, request identity, cancellation, fencing, exactly-once restart, or cross-symbol shared-feed policy.

### What future implementations are constrained?

Executor watchdogs, Listener Supervisor, launchers/manual startup, listener process adoption, generation allocators, diagnostic endpoints, readiness aggregators, and every downstream epoch consumer.

### How would an implementation violate this ADR?

By letting Executor/read routes restart, evaluating stale state before an accepted recovery commit, repeating a restart from a stale level, changing epoch for bridge-only recycle, accepting old-epoch data, or restarting all symbols from one implicit global timestamp.

## 10. Expected Implementation and Verification

### Expected Implementation Areas

- a dedicated canonical Listener Supervisor service/module and the concrete local SQLite supervisor store defined by section 3.3.1;
- `executor.py` accepted-tick ordering, health publication, restart-request client, fail-closed gating, and pure watchdog routes;
- `rithmic_live_listener.py` epoch grant/fence conformance and bridge boundary;
- `launch_all.ps1`, manual startup procedures, and legacy `run_system.ps1` conformance to one supervisor; and
- Trade Manager and Entry Agent epoch-aware authoritative-domain acknowledgement consumers, plus Command Center observational parity projection with no listener-lifecycle role.

### Verification Areas

- dedicated ADR-015 supervisor/recovery race and fault-injection suite;
- Executor diagnostic endpoint nonmutation suite;
- listener epoch/bridge generation integration suite;
- NQ/YM shared-feed classification tests;
- ATR/downstream rehydration tests; and
- isolated cold/manual startup and shutdown evidence.

### Traceability Record

Current semantic traceability is incomplete. `Architecture/Audits/2026-07-17_ADR015_016_Clause_Traceability_Registry_DRAFT.md` is historical rejected Phase 3B evidence, not a current forward/reverse mapping. Phase 3C2 will rebuild clause/scenario/assertion traceability only from independently accepted Phase 3C1-R1 hashes. The external recovery matrix remains a package-level index and is not a substitute.
