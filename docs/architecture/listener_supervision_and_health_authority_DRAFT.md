# Listener Supervision and Feed-Health Authority Contract

Version: Historical Draft 0.1 - Withdrawn 2026-07-17

Status: **WITHDRAWN — SUPERSEDED DRAFT**

Governance Disposition: **NONCANONICAL; NOT AN AUTHORITY SOURCE; NOT IMPLEMENTATION INPUT**

Supersession: Retained only as historical design evidence. Its cancellation, exhaustion, storage, and role terminology is superseded by the coordinated ADR-015/ADR-016 proposal and Phase 3A supporting specifications, subject to their future independent approval and canonical incorporation. ADR-015 and ADR-016 remain unapproved; withdrawal of this older draft does not approve them.

Normative Effect: None. Every `SHALL`, `MUST`, state, schema, owner, and implementation statement below is historical text and SHALL NOT be cited as current authority, active dependency, implementation requirement, verification target, readiness evidence, or deployment input.

Proposed Authority: ADR-015 and ADR-016 after approval; ADR-012; Runtime Authority Specification after coordinated amendment

Implementation Authorization: None

## 1. Historical purpose

Define the concrete component boundaries, identities, state machines, durable records, requests, fences, health publication, and recovery behavior for the Rithmic listener and its bridge.

## 2. Component roles

| Component | May produce facts | May request | May execute lifecycle action |
|---|---|---|---|
| Listener Supervisor | supervisor/epoch/process facts | listener start/restart/stop internally | full listener only |
| Rithmic listener | ticks, bars, connection, subscription, heartbeat, ATR inputs | bridge recovery; supervisor restart request when policy allows | bridge only through Bridge Controller |
| Bridge Controller | bridge process/generation facts | bridge recycle | current bridge generation only after durable fence |
| Executor | accepted delivery, symbol freshness, execution facts | listener restart | none for listener/bridge |
| Health Durable Writer | health commit/cursor facts | persistence retry | durable store writes only |
| Launcher/manual orchestration | startup/shutdown intent | supervisor commands | may start supervisor, never listener after supervisor architecture is adopted |
| GET/status/Command Center | none beyond access telemetry | none | none |

## 3. Listener epoch schema

```text
listener_epoch_id
epoch_sequence
supervisor_instance_id
listener_process_id
listener_build_id
granted_symbol_contracts
authority_lease_or_mutex_id
started_at_utc
granted_at_utc
prior_epoch_id
transition_reason
status
fenced_at_utc
```

Only the Supervisor SHALL allocate, grant, or fence this identity.

## 4. Bridge generation schema

```text
listener_epoch_id
bridge_generation_id
bridge_generation_sequence
bridge_process_id
bridge_build_or_script_id
requested_subscriptions
started_at_utc
ready_at_utc
status
prior_generation_id
transition_reason
fenced_at_utc
```

Bridge generation sequence is scoped to a listener epoch. Changing it does not change listener epoch.

## 5. Restart request schema

```text
restart_incident_id
supervisor_generation_id
listener_epoch_id
fencing_token
expected_incident_version
requester_id
request_sequence
observed_stale_timestamp_utc
decision_timestamp_utc
affected_symbols
resolved_contracts
direct_evidence_ids
health_commit_id
requested_action = FULL_LISTENER_RESTART
reason_code
policy_version
```

Required transitions:

```text
REQUESTED -> PENDING -> CANCELED
REQUESTED -> PENDING -> FENCED -> EXECUTING -> REHYDRATING -> COMPLETED | FAILED
```

Only `PENDING -> FENCED` can execute. Duplicate requests cannot repeat it.

## 6. Recovery tick contract

Accepted same-epoch data SHALL be journaled and liveness-committed before restart evaluation. The liveness update SHALL reference the accepted event sequence and epoch. If it clears the pending predicate before fence, the supervisor commits cancellation. Evaluation then uses the updated state.

## 7. Cross-symbol contract

Production topology `randle-rapi-feed-topology-v1` SHALL treat NQ and YM as two symbol/contract authorities using one physical RAPI MarketData connection, bridge child, and listener process. Health, subscription, tick, bar, and ATR state remain per exact symbol/contract. Only the Listener Supervisor SHALL declare runtime `SHARED_FEED_FAILURE`.

The Supervisor SHALL load and digest-verify the approved `config/runtime/listener_shared_feed_policy_v1.json` schema defined by ADR-015 section 3.11.2. Missing/out-of-range/extra fields, an unapproved version/digest, or an environment/command-line/source/launcher override SHALL prohibit automatic lifecycle actions and fail readiness. All thresholds, debounce, pre-fence revalidation, bridge/listener cooldown, rate window, maximum attempts, and escalation SHALL use that policy and the Supervisor monotonic clock.

The ADR-015 Market Data Expectation Evaluator inside the Listener Supervisor SHALL be the sole runtime owner of `market_data_expected`. The Market Session Calendar Policy Owner produces the deployment-bound calendar; the evaluator consumes only that verified calendar, Supervisor-owned subscription intent, startup/shutdown state, and correlated clocks. Startup-unproven, expired, or clock/intent-mismatched expectation blocks staleness-based lifecycle action. Planned shutdown produces `DATA_NOT_EXPECTED_PLANNED_SHUTDOWN`; tick silence never produces `DATA_NOT_EXPECTED`.

One-symbol `STALE`, `DATA_UNAVAILABLE`, or subscription failure blocks that symbol and permits bounded symbol recovery only. Bridge recycle requires an ADR-016 BDP. Full listener restart requires exactly one ADR-015 `SFF-01`, `SFF-02`, or `SFF-03`, continuous debounce, current corroboration, immediate revalidation, and a durable fence. `SFF-02` SHALL use only the pre-action epoch grant, Health Ingress heartbeat/publication facts, Supervisor command-channel challenge results, and exact OS handle described by ADR-015; a request, fence, stop, or replacement result SHALL NOT corroborate it. Recovery before the fence SHALL cancel. Before every bridge/listener execution the Supervisor SHALL compare the durable monotonic rolling-window count to the governed maximum. A count already equal to the maximum SHALL complete the incident as exhausted/rate-limited without process action; it SHALL NOT create an implicit retry or reset on process/supervisor/launcher restart.

## 8. Durable supervisor store

Supervisor state SHALL be local, serialized, crash-consistent, versioned, and independent of Executor memory. It SHALL preserve:

- current/prior listener epoch;
- restart incident and state;
- current fencing token;
- executed stop/start command identity;
- process identity/adoption evidence;
- rehydration acknowledgements; and
- completion/failure.

Supervisor restart SHALL resume, not duplicate, a fenced incident.

## 9. Health event and durable-store schema

```text
health_event_id
health_sequence
health_commit_id
listener_epoch_id
bridge_generation_id
symbol
resolved_contract
producer_id
producer_sequence
fact_type
observed_at_utc
recorded_at_utc
direct_evidence_id
prior_health_sequence
schema_version
checksum
```

The Health Durable Writer inside Listener Supervisor SHALL be the sole writer to the ADR-016 local SQLite control store. Producers enqueue; they do not write SQLite, replace a snapshot, or acknowledge durability.

## 10. Durable health write algorithm

1. Retain the exact pending event without acknowledgement.
2. Validate HMAC, producer capability, supervisor generation, listener epoch, bridge generation, producer sequence, order, and deduplication.
3. On the sole serialized writer connection, execute `BEGIN IMMEDIATE` against `%LOCALAPPDATA%\RandleRuntimeData\control\feed_health_v1.sqlite3` configured with `journal_mode=WAL`, `synchronous=FULL`, `foreign_keys=ON`, and the approved `application_id`/`user_version`.
4. Insert the immutable event, derived current state, incident linkage where applicable, health commit, and cursor update in that one transaction.
5. Execute `COMMIT`; SQLite/WAL full-synchronous commit is the durability boundary.
6. Reread through a separate read-only connection and verify commit ID, sequence/cursor, epoch/generation, schema, and checksum.
7. Only after successful readback, acknowledge the producer and remove the pending item.
8. Queue an asynchronous projection item derived from the verified immutable commit.

Failure at any step leaves the durable cursor unchanged and the event pending.

## 11. Retry and degradation

Retries SHALL be bounded exponential backoff with jitter. High-frequency updates may coalesce only when the newest authoritative value and all incident/order evidence remain reproducible.

When the local store is unavailable:

```text
health_control_state = HEALTH_PERSISTENCE_DEGRADED
new_entries = BLOCKED
automatic_new_bridge_or_listener_fence = PROHIBITED
direct_current_epoch_liveness = RETAINED_FOR_IMMEDIATE_OBSERVATION
pending_health = RETAINED_WITHIN_BOUNDED_RESOURCES
```

Shared projection failure alone does not set the durable store unavailable.

## 12. Shared/OneDrive projection

The projection SHALL contain source health commit/cursor, epoch, generation, generated time, schema, and lag status. It SHALL be written asynchronously. It SHALL NOT initiate, influence, reinforce, confirm, participate in, or contribute to any process-control, lifecycle, death, recovery, fencing, cancellation, authorization, or readiness decision, alone or combined. No control module SHALL read or import it.

The observed WinError 5 proves atomic replacement denial. It does not prove which process held an incompatible handle. No log/report SHALL name the handle owner without direct handle evidence.

## 13. Bridge recycle contract

Bridge recycle requires a durable current-generation incident and fence. The Supervisor State Evaluator SHALL:

1. validate current epoch/generation;
2. validate direct terminal predicate;
3. debounce;
4. revalidate immediately;
5. cancel if recovered;
6. durably fence the generation;
7. allocate one execution identity and intended next generation; and
8. issue one authenticated execution command after durable readback.

Bridge Controller SHALL only execute that exact command idempotently, terminate/start at most one child, report exact process/result evidence, and wait publication-fenced. The Supervisor alone SHALL grant the next generation in the same listener epoch after durable adoption. The listener and Controller SHALL rehydrate subscription/publication state only under that grant and publish completion/failure evidence.

Projection staleness is never the direct terminal predicate.

The listener SHALL publish raw `RAPI_ALERT_OBSERVED` type/connection/`RpCode`/message and SHALL NOT invent a terminal cause. The Supervisor SHALL apply ADR-016 section 3.9.1's independent `initiator`, `requested_action`, `execution_method`, `observed_cause`, and `result` fields exactly; every unproven dimension remains `UNKNOWN`. Process disappearance alone proves no initiator/action/method/cause and SHALL NOT authorize automatic recycle/restart. Only a satisfied ADR-016 BDP-01 through BDP-04 SHALL authorize creation of `RECYCLE_PENDING`. BDP-01 SHALL additionally prove unexpected exit and SHALL exclude planned shutdown, governed operator shutdown, startup transition, controlled bridge recycle, listener shutdown, and listener replacement already in progress.

## 14. Full listener escalation

Bridge recovery exhaustion may publish an ADR-015 restart request. It cannot terminate the listener or allocate an epoch. Full restart uses a separate incident and supervisor fence.

ATR disposition SHALL follow ADR-015 section 3.12 without local discretion: same-epoch bridge recycle and symbol recovery retain finalized bars/RMA and rehydrate only the incomplete minute; stale-epoch/generation evidence is rejected with no current ATR change; listener restart/new epoch, cold startup, and interrupted startup recovery rehydrate exact continuous authority or apply exactly one closed `DURABLE_HISTORY_GAP`, `DURABLE_HISTORY_CORRUPT`, `CONTRACT_IDENTITY_CHANGED`, or `SESSION_VOLATILITY_RESET_REQUIRED` invalidate/rebuild disposition. No other reset reason is legal.

## 15. Pure read contract

All GET/HEAD status, health, watchdog, alert, audit, and Command Center routes SHALL use immutable snapshots. Reads cannot enqueue control requests, flush health, modify timestamps/cursors, fence, cancel, restart, or recycle.

## 16. Recovery and corruption

On startup, the Health Durable Writer SHALL complete ADR-016 sections 3.6.5-3.6.7 before ingress, listener/bridge start, or public readiness. It SHALL verify the SQLite database/WAL/SHM, application/schema/policy/store identities, pragmas, foreign keys, checksums, contiguous cursors, epoch/generation ancestry, and legal incident/fence/execution state.

Failure SHALL enter `HEALTH_STORE_CORRUPT`, close handles, create a flushed/hash-verified read-only quarantine set and manifest, and return `CONTROL_STORE_RECOVERY_REQUIRED`. Automatic restore, in-place/automatic migration, projection/log/status/memory repair, and empty replacement are prohibited.

A restore requires an approved qualifying local owner-produced or governance-controlled backup, staging, full verification, preserved store/cursor/epoch/generation/incident identity, a new supervisor generation, exact ambiguous-process reconciliation, three named approvals, and recovery audit. If no source qualifies, startup SHALL fail until governed reinitialization. Migration SHALL be versioned/staged/hash-bound and rollback SHALL be permitted only before activation/first new commit.

## 17. Expected Implementation and Verification

Expected implementation areas:

- new Listener Supervisor and durable store;
- `executor.py` request/health client and pure watchdog projection;
- `rithmic_live_listener.py` epoch/bridge/health producer and Bridge Controller;
- local health durable store and `data_paths.py` path separation;
- `launch_all.ps1` and manual startup conformance; and
- downstream epoch/generation-aware consumers.

Expected verification areas:

- threshold-boundary/recovery/fence/exactly-one supervisor suite;
- WinError 5/write-stage/corruption/pending-retention suite;
- cross-symbol/shared-feed tests;
- independent termination-field callback/intent/exit taxonomy and per-field `UNKNOWN` tests;
- policy schema/digest/range/default/debounce/cancel/cooldown/rate-limit tests;
- verified quarantine, approved/nonapproved restore, no-source reinitialization, staged migration, rollback-boundary, and recovery-audit tests;
- bridge versus full-listener integration; and
- diagnostic endpoint nonmutation tests.

Historical traceability only: `Architecture/Traceability/2026-07-17_Production_Recovery_Documentation_Traceability_Matrix.md`. Active clause-level requirements are registered only from ADR-015, ADR-016, the Entry Session Contract, Startup Specification, and Diagnostic Purity Contract in `Architecture/Audits/2026-07-17_ADR015_016_Clause_Traceability_Registry_DRAFT.md`.
