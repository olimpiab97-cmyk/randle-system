# Randle AI Runtime Recovery Verification Specification

Version: Draft 0.4 - Phase 3B remediation

Document Type: Proposed Canonical Verification and Test Specification

Status: **DRAFT - NOT CANONICAL - NOT APPROVED**

Decision Sources: ADR-014 is approved and governing. ADR-015, ADR-016, and this verification specification remain unapproved drafts; their requirements are test targets only after independent approval and canonical incorporation.

Implementation Authorization: None

Scope: Entry session rollover, listener supervision/epochs, restart recovery, Runtime Authority Store conformance, feed-health durability, bridge generation/recycle, ATR continuity, startup/readiness, diagnostic purity, and NQ/YM integration

## 1. Verification principle

Tests prove approved authority; they do not approve the draft decisions. No result from this specification authorizes production start, deployment, entry-lock clearing, or trading.

Every run SHALL use an isolated data root, isolated ports, simulated/fake external feeds and webhook delivery, and no production credentials or persistence unless a later governed verification plan explicitly authorizes controlled production evidence capture.

## 2. Evidence classes

Every artifact SHALL be labeled:

- Immutable Incident Evidence;
- Canonical Archive Replay;
- Deterministic Synthetic Fixture;
- Fault-Injection Fixture;
- Isolated Integration Runtime; or
- Manual/Platform Diagnostic Evidence.

Synthetic and isolated evidence cannot be represented as a production fix or production readiness.

Every record SHALL include source/artifact hashes, code/build identity, rule/ADR/spec version, symbol, contract, session, rollover commit ID, listener epoch, bridge generation, health sequence/commit, event order, expected/actual result, and exclusions where applicable.

### 2.1 Bidirectional obligation and test identity

Every normative obligation exercised by this specification SHALL have a stable verification requirement ID. Every test case, fixture, fault point, report row, and evidence artifact SHALL cite at least one exact authority section and one ID below. Conversely, every ID SHALL resolve to one or more named tests and produced evidence rows; an untested ID or a test without an authority/ID mapping fails the Traceability gate.

The clause-level source of truth for this draft package is `Architecture/Audits/2026-07-17_ADR015_016_Clause_Traceability_Registry_DRAFT.md`. It assigns `ADR015-REQ-###`, `ADR016-REQ-###`, `ESR-REQ-###`, `STARTUP-REQ-###`, `DEP-REQ-###`, `STORE-REQ-###`, and `RRVSPEC-REQ-###` to every mandatory clause in the six normative architecture/store documents and this verification specification, and supplies both forward and reverse mappings to the verification families below. A section-family row below does not replace a clause row in that registry.

| Verification requirement ID | Exact normative obligation | Required verification sections/artifacts |
|---|---|---|
| `RRV-SR-001` | Approved ADR-014 sections 3.3-3.7; Entry Session Contract sections 4-9 | Sections 3.1-3.4; prior/current replay and atomic crash suite |
| `RRV-SR-002` | Approved ADR-014 sections 3.8-3.13; Entry Session Contract sections 3.1, 10-15 | Sections 3.2-3.5 and 8; state/authorization/divergence/startup suite |
| `RRV-LS-001` | ADR-015 sections 3.1-3.5 and 3.14 | Sections 4.3-4.4 and 8; sole-owner/generation/manual-start suite |
| `RRV-LS-002` | ADR-015 sections 3.6-3.8, including `RESTART_CANCELED` | Sections 4.1-4.4; ordering/cancellation/fence/restart-recovery suite |
| `RRV-LS-003` | ADR-015 sections 3.4.2 and 3.10-3.11, including SFF-01..03, policy limits, `SHARED_FEED_POLICY_INVALID`, market expectation, `RECOVERY_RATE_LIMITED_FAILED`, and `FAILED_RECOVERY_EXHAUSTED` | Sections 4.5-4.7 and 5.4; closed-state/shared-feed/policy/limit/exhaustion suite |
| `RRV-ATR-001` | ADR-015 section 3.12; Startup sections 6.1 and 9 | Sections 6-8; bridge/listener/cold-start ATR continuity suite |
| `RRV-FH-001` | ADR-016 sections 3.1-3.7, including the one-database identity contract and producer/evaluator/writer separation | Sections 5.1-5.2 and 5.5-5.8; transport/store/pending/corruption/identity/role suite |
| `RRV-FH-002` | ADR-016 sections 3.8-3.12, including projection isolation, five-field termination, BDPs, bridge states, and exhaustion | Sections 5.3-5.4; projection/termination/BDP/exhaustion suite |
| `RRV-FH-003` | ADR-016 sections 3.3.6, 3.9.1, 3.13-3.16 | Sections 5.5-5.8 and 8; complete health-state/time/recovery/startup suite |
| `RRV-ST-001` | Production Startup sections 3-14 | Section 8; bounded cold/manual start, READY/FAILED, and shutdown suite |
| `RRV-DP-001` | Diagnostic Purity sections 1-8 | Section 9; generated manifest/call-graph/nonmutation/idempotency suite |
| `RRV-DP-002` | Diagnostic Purity sections 5.1-7 route-specific migrations and primitive-unreachability obligations | Section 9; commit-bound thirteen-route cold/error/concurrency and replacement-boundary suite |
| `RRV-STORE-001` | Runtime Authority Store Schema sections 2-9 | Sections 5.8-5.9; schema, writer-routing, typed-transaction, crash/replay, reconstruction, and startup-proof suite |
| `RRV-GOV-001` | Verification sections 10-12 and canonical governance/traceability specifications | Sections 10-12; noninterference, evidence report, debt, and gate audit |

Before any verification run is accepted, the evidence manifest SHALL include both forward (`authority section -> clause requirement ID -> verification ID -> tests/evidence`) and reverse (`test/evidence -> verification ID -> clause requirement ID -> authority section`) views. Grouping is legal only when every individual mandatory clause is enumerated with a substantive scenario and assertion in the Phase 3B registry. Missing, duplicate-conflicting, boilerplate, or document-level-only citations fail verification and traceability. The registry is a present document obligation; it is not deferred to a future generated manifest.

## 3. ADR-014 session rollover verification

Verification IDs: `RRV-SR-001`, `RRV-SR-002`.

### 3.1 Prior-to-current replay

For NQ and YM independently:

1. start from a verified prior-session canonical aggregate;
2. preserve the prior receiver/canonical/frozen/observation/authorization identities;
3. deliver one complete current-session candidate in the authorized lock window;
4. prove validation completes before active mutation;
5. prove one complete candidate aggregate is built off-state;
6. prove one shared `session_rollover_commit_id` appears on every required member;
7. prove `trade_authorization_context_binding` is committed as `BLOCKED_PENDING_RUNTIME_GATES` and `authorized_session_rollover_commit_id` is committed as `null` without prior-session inheritance;
8. prove durable commit precedes current exposure;
9. prove new-session activation and prior-session retirement are two invariants of the same atomic commit, with no durable split state; and
10. prove every current projection converges on the same session/commit identity.

### 3.2 Exactly-once and ordering

Tests SHALL prove:

- duplicate receipt of the same accepted candidate returns the same commit and creates no second observation reset, ladder, retirement, or exposure event;
- stale/prior-session candidates cannot overwrite a current commit;
- two concurrent valid candidates serialize deterministically;
- a different later candidate for the already locked session rejects/quarantines; and
- NQ and YM commits remain independent.
- every later opening-entry request and authorization decision carries `authorized_session_rollover_commit_id` equal to the active commit and rejects null/missing/stale/prior-session/other-symbol/mismatched identities; and
- every declared Entry Session state, including `CANDIDATE_REJECTED` and `COMMIT_FAILED`, satisfies its entry/owner/durable-record/exit/restart/retry/authority/authorization table.

### 3.3 Validation failure

Incomplete, wrong-session, wrong-symbol, unauthorized-source, stale, structurally invalid, or contradictory candidates SHALL:

- remain archived with rejection evidence;
- create no rollover commit;
- leave prior canonical history unchanged;
- not advance observation reset;
- not expose a current receiver lock/frozen ladder; and
- keep the symbol WAIT/fail-closed.

The structural fixture SHALL use the then-approved stack/ladder contract. ADR-014 verification SHALL not require resolution of DEBT-015 unless a separately approved AIA proves direct dependency.

### 3.4 Crash and persistence injection

Inject failure or crash at every stage:

- candidate archive;
- validation result persistence;
- transaction preparation;
- aggregate/journal write;
- file/database flush;
- atomic commit/replace;
- integrity verification;
- atomic active-pointer/prior-retirement/observation/frozen-ladder/authorization mutation before COMMIT;
- each compatibility projection exposure; and
- post-commit evidence publication.

After restart, the result SHALL be one complete committed aggregate or no commit. A partial current session is prohibited. Committed-but-unexposed projections SHALL retry under the same commit ID.

### 3.5 Divergence detection

Independently corrupt/stale each required authoritative materialization to another session/commit:

- receiver current projection;
- canonical Entry Agent projection;
- frozen levels/ladders;
- observation state;
- session authorization.

The system SHALL enter `SESSION_PROJECTION_DIVERGED`, preserve evidence, identify the first mismatch, block entries, and recover only from verified canonical commit authority.

Separately corrupt status output and Command Center projection. Each case SHALL fail the observational `COMMAND_CENTER_ALIGNED`/projection-parity gate, preserve the committed session unchanged, and prove that the projection cannot write `SESSION_PROJECTION_DIVERGED`, close or veto the authoritative session transaction, or supply session/authorization authority.

## 4. ADR-015 listener supervisor verification

Verification IDs: `RRV-LS-001`, `RRV-LS-002`, `RRV-LS-003`.

### 4.1 Recovery threshold boundary

Use a deterministic clock to deliver a valid current-epoch recovery tick exactly before, at, and after the stale threshold. For every accepted event, prove durable intake/liveness commit occurs before stale evaluation.

At and around the boundary, a fresh accepted same-epoch tick SHALL cancel an unfenced pending restart and SHALL NOT stop/start a process or allocate an epoch.

The cancellation case SHALL prove one durable `RESTART_CANCELED` record with the original stale boundary, recovery event/intake/liveness commits, prior/committed incident versions, policy/epoch/generation identities, no fence/execution/epoch allocation, and the post-cancellation reevaluation. Prove deterministic `HEALTHY` when every listener-level suspect condition clears and deterministic `SUSPECT` when another condition remains.

### 4.2 Fence boundary

Tests SHALL prove:

- recovery before durable `RESTART_FENCED` cancels idempotently;
- a tick after `RESTART_FENCED` carrying the old epoch is rejected and cannot cancel;
- a new-epoch tick cannot be accepted before supervisor grant; and
- stale requests with prior fencing tokens reject.

Tests SHALL also prove that `RESTART_CANCELED` cannot transition to `RESTART_FENCED`, execute a stop/start, allocate an epoch, reopen, or retry after Supervisor restart. A later independently qualifying failure SHALL require a new incident/stale boundary and all current debounce/rate/fence rules.

### 4.3 Exactly-one restart

A genuinely stale listener SHALL create:

- one stable restart incident ID;
- one durable pending decision;
- one fence;
- one stop execution;
- one replacement start;
- one new epoch grant; and
- one completion/failure record.

Repeated level observations, duplicate requests, concurrent requesters, Executor restart, supervisor restart, and diagnostic polling SHALL create no second action for that incident.

### 4.4 Fault behavior

Cover stop timeout/failure, start failure, process exits before grant, duplicate process discovery, mutex/lease ambiguity, supervisor crash before/after fence, and rehydration failure. Each remains fail-closed under one incident identity.

### 4.5 Cross-symbol behavior

Tests SHALL separately model:

- NQ stale/YM fresh;
- YM stale/NQ fresh;
- both fresh with skewed timestamps;
- both terminally stale;
- shared connection failure;
- listener process exit; and
- terminal bridge recovery exhaustion.

One-symbol staleness SHALL not produce full shared-listener restart. Each approved `SHARED_FEED_FAILURE` predicate SHALL be tested positively and negatively.

For `SFF-02`, tests SHALL independently control and timestamp the durable epoch grant, Health Ingress heartbeat, Supervisor command-channel challenge/response, current-epoch publication ingress, and exact owned OS process handle. The positive case requires every pre-action input. Each one-missing/recovered/stale/identity-mismatched case SHALL reject or cancel. A restart request, publication fence, stop result, or replacement observation SHALL never appear in the evidence graph. The report SHALL render the full producer -> authenticated ingress/adapter -> durable fact -> Supervisor evaluator -> pending/revalidate/fence chain.

### 4.6 Governed limits and market-data expectation

Tests SHALL verify the exact policy schema, digest, owner, deployment binding, defaults, ranges, monotonic rolling windows, cooldown, and persistence across process/supervisor/launcher restart. At `max_bridge_recycles_per_window - 1`, one final qualifying execution is permitted; when the durable count equals the maximum, the next pending incident SHALL transition to `FAILED_RECOVERY_EXHAUSTED` without process action. No implicit attempt, generation, incident, wall-clock reset, or operator interpretation is permitted. Apply the equivalent boundary proof to full-listener restart limits.

For `FAILED_RECOVERY_EXHAUSTED`, positive cases SHALL cover both exact entry branches: pre-execution durable count already equal to maximum, and last permitted execution failing to commit `BRIDGE_GENERATION_READY` by the recovery deadline. Negative cases SHALL cover a remaining permitted attempt, recovery before the deadline, stale/prior-generation counts, wrong policy digest, and incomplete revalidation. A count greater than the maximum SHALL deterministically produce the governed store/authority-divergence failure with zero action and SHALL NOT produce exhaustion. Fault cases SHALL inject COMMIT/readback failure for the exhaustion record and prove no false durable outcome. Restart cases SHALL prove the terminal incident/count survives bridge, listener, Supervisor, and launcher restart. Escalation cases SHALL prove exhaustion itself performs no process action and becomes SFF-03 evidence only through a new listener restart incident with debounce, current revalidation, rate eligibility, fencing, and exactly-once execution. Ordinary `BRIDGE_FAILED` SHALL never substitute for exhaustion.

For full-listener `RECOVERY_RATE_LIMITED_FAILED`, positive cases SHALL cover the cooldown-active and durable-count-equals-maximum branches before fencing. Negative cases SHALL cover eligible capacity, stale/wrong policy evidence, and a bridge-only exhausted incident. Persistence and restart cases SHALL prove one terminal durable outcome, no process action, no epoch allocation, no automatic retry after Supervisor/launcher restart, and no automatic SFF predicate. Operator-recovery cases SHALL prove only the governed `RESUME_AFTER_LISTENER_RATE_LIMIT` command can create a new incident after the policy window is eligible; otherwise it returns `RATE_LIMIT_STILL_ACTIVE` without mutation.

For `SHARED_FEED_POLICY_INVALID`, tests SHALL prove exact schema/version/digest/range/topology validation, the policy evaluator and incident writer roles, durable input identity and reason, startup terminal failure, zero speculative restart/recycle/fence, survival across restart, and recovery only after a corrected versioned policy passes a new startup validation.

### 4.7 Closed listener-state and incident-transition coverage

The suite SHALL exercise every permitted edge and at least one rejected unlisted edge for every full-listener state and restart-incident state/outcome in ADR-015 section 3.4.2. It SHALL prove one transition authority, one logical durable writer, deterministic restart restoration, readiness effect, and absence of category drift among lifecycle states, incident outcomes, reason codes, validation dispositions, and startup results.

The Market Data Expectation suite SHALL verify its calendar producer, Supervisor-owned evaluator, consumers, canonical JSON schema/digest, subscription-intent binding, `EXPECTATION_STARTUP_UNPROVEN` state, expected/not-expected transitions, boundary recomputation, expiration, clock-correlation loss, planned shutdown, and restart recovery. Tick silence SHALL never create `DATA_NOT_EXPECTED`; `EXPECTATION_STARTUP_UNPROVEN`/expired classification SHALL block entries and staleness-based lifecycle action.

## 5. ADR-016 feed-health and bridge verification

Verification IDs: `RRV-FH-001`, `RRV-FH-002`, `RRV-FH-003`.

### 5.1 Write-stage fault injection

Inject deterministic local SQLite failures at connection/open, `BEGIN IMMEDIATE`, schema/integrity validation, event/commit/cursor insert, WAL write/sync, `COMMIT`, and post-commit readback/checksum verification. Separately inject WinError 5 at every asynchronous projection stage: temporary-file creation/write/flush, `FlushFileBuffers`, `ReplaceFileW`/`MoveFileExW`, reopen/readback, and projection-cursor commit.

After every local durable failure, pending state SHALL remain, durable sequence/cursor SHALL not advance, no acknowledgement SHALL be emitted, retry SHALL be bounded, and no process-control action SHALL result from stale projection.

### 5.2 Serialization and retry

Concurrent listener, Executor, connection, subscription, heartbeat, and delivery producers SHALL yield one monotonic durable sequence through the Health Durable Writer. Tests SHALL verify duplicate handling, order, coalescing, backoff/jitter bounds, bounded memory/resource behavior, and no warning/write storm.

### 5.3 Projection isolation

Prove local durable success while the shared/OneDrive projection fails repeatedly. The local cursor SHALL advance, projection cursor SHALL remain pending, projection SHALL show lag when available, and no bridge/listener death decision SHALL consume the stale projection.

For every process-control, lifecycle, death, recovery, fencing, cancellation, authorization, and readiness predicate, mutate the projection through fresh, stale, missing, corrupt, contradictory, replayed, future-dated, and control-confirming values while holding direct/durable inputs constant. The decision and evidence set SHALL remain byte-for-byte unchanged and SHALL contain no projection path/value/hash. Projection SHALL neither initiate, influence, reinforce, confirm, participate in, nor contribute to the result.

The test/report SHALL state only that atomic replacement was denied unless separate approved handle-level evidence identifies the holder.

### 5.4 Bridge decision

Tests SHALL prove:

- stale shared projection plus fresh direct current-generation data cannot fence/recycle;
- prior-epoch/prior-generation health cannot control the current bridge;
- direct recovery before fence cancels;
- a genuine current-generation terminal bridge failure creates one fence and one recycle;
- new bridge generation remains in the same listener epoch;
- duplicate incident/request/poll does not recycle twice; and
- bridge exhaustion escalates only through a separate ADR-015 restart request.

Bridge lifecycle cases SHALL prove `BRIDGE_STARTUP_UNPROVEN` restores as nonready and exits only through the governed startup or planned-shutdown transition; `SUBSCRIPTION_VERIFIED` is the sole ready subscription fact and `ACTIVE` is rejected. `RECYCLE_CANCELED` cases SHALL prove the exact current authenticated recovery predicate, durable compare-and-swap record, atomic `BRIDGE_READY`/`BRIDGE_SUSPECT` reevaluation, no fence/execution/reopen/generation/SFF-03 effect, restart restoration without action, and a new incident for any later failure.

Every bridge-death predicate SHALL be tested against planned shutdown, governed operator shutdown, startup transition, controlled bridge recycle, and listener replacement already in progress; each SHALL be a negative case with zero new incident/fence/execution. BDP-01 positive cases SHALL prove an unexpected exact-process exit and all exclusions false.

Termination verification SHALL assert the five independent fields `initiator`, `requested_action`, `execution_method`, `observed_cause`, and `result`. Build a cross-product covering expected bridge shutdown, matched crash, authentication failure, connection loss, subscription failure, listener-requested recycle, listener shutdown, supervisor terminate/kill, operator-requested shutdown, provider forced logout/shutdown signal, recovery, timeout, unexpected nonzero exit without crash evidence, and disappearance. Each field SHALL derive only from its named evidence; tests SHALL reject any compound/legacy single terminal-reason field as control evidence.

For every field independently, tests SHALL include:

- complete trustworthy current-generation evidence proving one concrete non-`NONE` value;
- complete trustworthy current-generation evidence proving `NONE`;
- missing evidence;
- incomplete/sequence-gapped evidence;
- conflicting evidence;
- corrupt durable evidence store;
- unavailable durable evidence store;
- stale supervisor generation;
- wrong listener epoch;
- wrong bridge generation;
- unauthenticated/integrity-failed evidence;
- unexpected exact-process nonzero exit without matched crash evidence; and
- matched exception/crash evidence.

Only the complete absence proof may yield `NONE`. Every missing, incomplete, conflicting, corrupt, unavailable, stale, wrong-identity, or unauthenticated case SHALL yield `UNKNOWN` for that unproven field while preserving independently proven fields. The unexpected nonzero-exit case SHALL retain `observed_cause=UNKNOWN` and MAY record `result=PROCESS_EXITED`; only matched authoritative crash evidence may produce `observed_cause=BRIDGE_CRASH`. BDP-01 eligibility SHALL be tested independently from crash classification.

### 5.5 Degraded durable store

When the local durable store cannot recover or commit, prove:

- `HEALTH_PERSISTENCE_DEGRADED` is exposed;
- pending state remains within bounded resources;
- new entries are blocked;
- direct liveness remains visible;
- automatic new bridge/listener fence is prohibited;
- existing trade/execution truth is preserved by its owners; and
- recovery from the last valid commit is deterministic.

### 5.6 Corruption recovery

Cover malformed SQLite header/page/WAL/SHM, failed `integrity_check`, schema/application/policy mismatch, checksum/cursor/sequence gap, illegal epoch/generation ancestry, impossible incident/fence/execution state, and ambiguous process authority. Each case SHALL close handles, create a flush/hash-verified read-only quarantine set and manifest, preserve the original, and return `CONTROL_STORE_RECOVERY_REQUIRED`.

Automatic restore, newest-file selection, projection/log/status/memory reconstruction, in-place repair, and empty replacement SHALL fail. A qualifying owner-produced or governance-controlled backup SHALL remain noncurrent until staged full verification, identity/history preservation, three named approvals, recovery-audit durability, new supervisor generation, and process-ambiguity reconciliation succeed. Test no-source governed reinitialization, staged version migration, rollback before activation/first commit, rollback prohibition afterward, and every audit-path failure. Unresolved recovery SHALL terminate startup fail-closed.

### 5.7 Time-authority degradation

Using deterministic injectable UTC and monotonic clocks, verify every `HEALTH_TIME_AUTHORITY_DEGRADED` entry predicate: UTC rollback greater than two seconds, unavailable or non-increasing monotonic source, correlation error greater than two seconds, and conflicting clock-source identity. Prove the sole State Evaluator/Health Durable Writer transition, durable incident contents, concurrent persistence degradation when commit fails, and survival across Supervisor generation restart.

While degraded, prove ordered direct observations remain distinguishable from durable facts, entries and freshness/expectation/readiness remain blocked, no new bridge/listener incident is created/canceled/fenced from time-dependent evidence, no epoch/generation is allocated, and file/projection time cannot substitute. Test idempotent completion only for an already readback-verified fence.

Recovery tests SHALL require exactly the five-sample/at-least-five-second monotonic/UTC/source-identity transaction and durable `HEALTH_TIME_AUTHORITY_RECOVERED` record before clearing. Test every failed sample condition, loss of prior freshness, fresh-current-generation reevaluation, startup terminal failure, one failed recovery remaining degraded, and the second consecutive failed recovery escalating to governed operator recovery without automatic lifecycle action.

### 5.8 Complete health-state, identity-store, and role coverage

For every authoritative health state in ADR-016 section 3.9.1, tests SHALL exercise every permitted edge, reject at least one unlisted edge, verify the exact evaluator, transition authority, Health Durable Writer record, restart restoration, readiness effect, escalation behavior, and required recovery evidence. Evidence facts and failure reasons SHALL be rejected as state-machine members.

The control-store suite SHALL prove the exact database contract in `docs/architecture/runtime_authority_store_schema_DRAFT.md`: schema identity `RANDLE_RUNTIME_AUTHORITY_V2`, every named table and column, each primary/unique/check/foreign-key constraint, `PRAGMA foreign_keys=ON`, zero `foreign_key_check` rows, WAL/FULL durability, writer-registry allowlists, optimistic versions, typed transaction coverage, crash-before/after-COMMIT reconstruction, corrupt-database quarantine, and rejection of every unauthorized write plan. It SHALL prove that the Runtime Authority Store Transaction Coordinator performs only connection, serialization, constraint, idempotency, commit/rollback, and mechanical recovery functions and cannot originate, evaluate, or own a domain identity or transition. No external database identity copy or unenforceable cross-database foreign key is permitted.

The role suite SHALL prove that the Rithmic listener emits authenticated `SUBSCRIPTION_PROOF_OBSERVED`, the State Evaluator alone decides the transition, and the Health Durable Writer alone commits `SUBSCRIPTION_VERIFIED`. Equivalent producer/evaluator/writer separation SHALL be proved for proof of life, bridge acknowledgement/generation grant, termination evidence, market-data expectation, ATR continuity, and Command Center parity.

### 5.9 Runtime Authority Store typed-transaction and reconstruction coverage

Verification ID: `RRV-STORE-001`.

Schema validation SHALL enumerate the complete table catalog from the Store Schema, parse every declared foreign key, and prove that its referenced table and column exist in the same database, are uniquely addressable, and have compatible representations. It SHALL prove every table has an explicit primary key, every column has explicit nullability, every current-row uniqueness scope is enforceable, and every logical writer has an allowlisted operation set with a required authority decision or command, idempotency key, optimistic version, audit record, and fail-closed rejection.

Positive, negative, crash, retry, version-conflict, missing-parent, corrupt-record, and unauthorized-writer scenarios SHALL cover every closed typed transaction: all `TX-LSN-*`, `TX-STORE-*`, `TX-BRG-*`, and `TX-HEALTH-*` transactions. The suite SHALL specifically prove atomic listener cancellation, fencing, execution start, rehydration start, each authoritative-domain acknowledgement, completion, ordinary failure, rate exhaustion, planned stop, each bridge generation/recycle/fence/execution/rehydration/ready/failure/exhaustion/shutdown/epoch-transition transaction, and independent-dimension health update with atomic aggregate recomputation.

For pre-COMMIT crash, the suite SHALL prove that none of the typed transaction's rows or current-state versions becomes visible. For post-COMMIT/pre-response crash, it SHALL replay the same idempotency key and prove byte-equivalent committed identities and versions with no duplicate state or action. Constraint, version, writer-routing, missing-parent, and corrupt-record failures SHALL create no partial domain state and SHALL return the exact Store Schema disposition. Startup reconstruction SHALL prove the last committed transaction cursor, current listener/epoch/bridge/health/incident/acknowledgement identities, and fail closed on any ambiguity without consulting process existence or projection JSON.

## 6. ATR continuity and rehydration

Verification ID: `RRV-ATR-001`.

### 6.1 Bridge recycle

Prove bridge recycle and same-epoch symbol recovery `RETAIN` finalized bars/RMA, `REHYDRATE` the incomplete minute only from complete journal proof, and otherwise discard only that incomplete minute. Neither case SHALL invalidate/rebuild finalized ATR.

### 6.2 Listener epoch change

Prove:

- old-epoch data rejects after fence;
- downstream enters REHYDRATING;
- exact durable completed history reconstructs the same RMA and emits continuity preserved;
- process restart alone does not emit reset;
- `DURABLE_HISTORY_GAP`, `DURABLE_HISTORY_CORRUPT`, `CONTRACT_IDENTITY_CHANGED`, and `SESSION_VOLATILITY_RESET_REQUIRED` each produce the exact ADR-015 retain/invalidate/rebuild/rehydrate disposition and WARMUP/fail-closed state; no other reason is accepted; and
- no old-epoch ATR combines with new-epoch ticks.

### 6.3 Cold startup

Cover sufficient continuous history, insufficient history, gapped/corrupt history, resolved-contract change, prior-session archive, current-session context missing, stale-epoch evidence, and interrupted startup recovery. Readiness SHALL distinguish REHYDRATING, WARMUP, WAIT, and LIVE deterministically and resume the recorded disposition without implicit reselection.

## 7. Downstream consumer verification

For bridge recycle, listener restart, and cold startup, assert deterministic behavior for:

- Executor epoch/generation intake and opening-action block;
- Trade Manager durable trade preservation, current price-input state, and no invented execution truth;
- Entry Agent lifecycle/session preservation and readiness;
- Command Center exact epoch/generation/session/ATR projection; and
- external TradingView delivery independence from trading authorization.

No consumer SHALL publish LIVE by combining mismatched session, contract, listener epoch, bridge generation, bar, ATR, lifecycle, or commit identities.

## 8. Startup and manual-start integration

Verification ID: `RRV-ST-001`.

Using the same isolated fixtures, verify:

- a current signed governance applicability snapshot with exactly zero blocking production-readiness debts, plus missing/stale/digest-mismatched/nonzero cases;
- canonical cold-start dependency order;
- manual start invoking identical owner commands and readiness contracts;
- exactly one Listener Supervisor and one granted listener;
- duplicate/stale process and port conflicts fail closed;
- positive Executor exclusive authority and entry-lock proof;
- current supervisor generation/listener epoch, current session commit, canonical frozen ladder, canonical ATR, and same-identity joins;
- current governed listener policy validates without `SHARED_FEED_POLICY_INVALID`;
- current session absent, valid, invalid, pending, committed-unexposed, and diverged cases;
- local health unavailable and shared projection unavailable cases;
- ngrok/external delivery starts only after local dependencies and cannot authorize entries;
- authenticated sender identity binds to the real public receipt/payload, and startup fails deterministically while `DEBT-2026-07-17-016` remains unresolved;
- partial failure produces no unbounded restart loop; and
- final readiness keeps entry lock engaged absent separate authorization.

The suite SHALL prove startup reaches terminal `READY_LOCKED` or `FAILED` before any post-startup deployment/trading decision is evaluated. `TRADING_PERMITTED` SHALL be absent from every `READY_LOCKED` predicate and evidence graph. Only a later separately governed decision may evaluate it, and that decision SHALL remain blocked by unresolved `DEBT-2026-07-17-016`, missing deployment authorization, incomplete Bucket 0, or any other applicable governance prerequisite.

## 9. Diagnostic endpoint purity

Verification IDs: `RRV-DP-001`, `RRV-DP-002`.

Enumerate every GET/HEAD/status/health/debug/audit/Command Center route, including alternate paths. For each:

- map the transitive call graph;
- prove no writer/control primitive is reachable in projection mode;
- compare authoritative files and in-memory control snapshots before/after repeated/concurrent requests;
- prove no restart/recycle/session commit/health flush/cursor change/process/port change;
- prove failure isolation; and
- distinguish access telemetry from domain events.

Endpoints named watchdog or alert remain subject to this rule.

The source-bound inventory SHALL use commit `869b3f08df5c5dbfa975246547455ad185288605`, tree `704fd715cad3aad281c534f8337840e3aab96234`, and the thirteen service/path entries in Diagnostic Purity section 5.2: Executor `/debug/watchdog`, `/debug/watchdog_alert`, and `/sync_snapshot`; Entry Agent `/debug/entry-liquidity` and `/entry/status`; Trade Manager `/debug/risk_state`, `/trades`, `/replay/<trade_id>`, `/debug/tradingview/atr/<symbol>`, `/debug/tradingview/atr_status`, `/debug/noon_runner_flatten`, `/events`, and `/debug/atr_trade/<trade_id>`. A later implementation commit SHALL regenerate the inventory and fail on every unclassified or newly reachable mutating read path; it SHALL NOT inherit this count as an exemption.

| Scenario target | Exact registration and transitive source path | Current mutation to exclude after implementation |
|---|---|---|
| `GET-EXEC-001` `/debug/watchdog` | `executor.py:1945-1947` -> `build_watchdog_state:618-664` -> restart path | restart state/throttle and listener process action |
| `GET-EXEC-002` `/debug/watchdog_alert` | `executor.py:1950-1963` -> same builder/restart path | same restart mutation |
| `GET-EXEC-003` `/sync_snapshot` | `executor.py:1966-1986` -> flat-symbol clear -> `save_executor_state` | order clear and durable Executor state write |
| `GET-EA-001` `/debug/entry-liquidity` | `tv_context_server.py:589-623` -> `build_entry_status:4668-4682` -> `run_once:3976-4052` -> `append_entry_agent_audit_row`/`persist_state` | audit append and pipeline-state persistence |
| `GET-EA-002` `/entry/status` | `tv_context_server.py:672-706` -> same status/run-once persistence; `697-699` -> decision/reasoning append helpers | audit/pipeline persistence and receiver log appends |
| `GET-TM-001` `/debug/risk_state` | `trade_manager.py:3979-3995` -> `load_state`, Executor snapshot, orphan event/save, noon status | persistence/reconciliation/event/noon mutation |
| `GET-TM-002` `/trades` | `trade_manager.py:5782-5799` -> `refresh_trades_from_executor_activity:3893-3936` | synchronization/noon/reconciliation/save |
| `GET-TM-003` `/replay/<trade_id>` | `trade_manager.py:5892-5905` -> same refresh path | same synchronization/persistence mutation |
| `GET-TM-004` `/debug/tradingview/atr/<symbol>` | `trade_manager.py:5554-5572` -> `get_tradingview_atr:4854-4863` | cold cache write and reachable corrupt-persistence handling |
| `GET-TM-005` `/debug/tradingview/atr_status` | `trade_manager.py:5575-5577` -> `find_tradingview_atr_record:2439-2464` | cold `TRADINGVIEW_ATR_CACHE` write |
| `GET-TM-006` `/debug/noon_runner_flatten` | `trade_manager.py:5636-5638` -> status builder `3807-3820` -> `load_state` | state load/normalization and corrupt backup path |
| `GET-TM-007` `/events` | `trade_manager.py:5864-5874` -> `load_state` | state load/normalization and corrupt backup path |
| `GET-TM-008` `/debug/atr_trade/<trade_id>` | `trade_manager.py:5936-5961` -> `load_state` | state load/normalization and corrupt backup path |

For every listed route, the scenario catalog SHALL identify the exact source registration, transitive call path, current mutation, intended immutable snapshot, and command/event/startup boundary. Each route SHALL have positive read-only, cold-state, 100 sequential, 20 concurrent, unavailable-snapshot, wrong-identity, and applicable corruption-path assertions. The assertions SHALL prove no cache fill, persistence hydration or normalization, backup creation, state/log append, order reconciliation, pipeline-state persistence, lifecycle action, or authorization change.

Instrumentation SHALL prove the exact committed-source primitives `build_watchdog_state`, listener restart execution, flat-symbol working-order clearing, `save_executor_state`, `build_entry_status`, `run_once(..., persist=True)`, `append_entry_agent_audit_row`, `persist_state`, receiver decision/reasoning log append helpers, `refresh_trades_from_executor_activity`, noon-runner processing, `load_state`, corrupt-persistence backup creation, and `TRADINGVIEW_ATR_CACHE` writers are unreachable from every remediated GET/HEAD/OPTIONS call graph. It SHALL specifically prove that Entry Agent `/debug/entry-liquidity` and `/entry/status` cannot append the Entry Agent audit or persist pipeline state, and that `/entry/status` cannot invoke either receiver log append helper; `/debug/entry-liquidity` is not falsely attributed a direct receiver-log append in the baseline. Both TradingView ATR routes SHALL be unable to create/replace cache records, and watchdog reads SHALL be unable to request or execute restart actions.

Tests SHALL NOT represent the following absent routes or symbols as current-source findings: Executor `/debug/tick_pipeline`; Entry Agent `/entry/executor_status`; Trade Manager `/debug/tick_pipeline`, `/health`, `/debug/nonclosed_trades`, `/paper_account_snapshot`, or `/config/trade_manager_mode`; `get_executor_tick_pipeline`; `get_trade_manager_tick_pipeline`; `PERSISTENCE_STATE_CACHE`; `PERSISTENCE_STATE_CACHE_LOADED`; active-trade-index mutation; or configuration-cache hydration. Executor `/account_snapshot` SHALL be tested as the local JSON snapshot route actually present in the tree, not as a Trade Manager proxy. Each future replacement POST/event/startup command SHALL pass sequential-duplicate, concurrent-duplicate, crash-after-commit, and restart idempotency tests.

## 10. Negative and noninterference cases

Verification ID: `RRV-GOV-001`.

Verification SHALL prove the recovery changes do not alter:

- Pine or transmitted liquidity calculations;
- stack/overlap/full-span rules;
- Step 2 or Step 4;
- ATR mathematics;
- Trade Manager ownership;
- Executor execution semantics;
- working orders/positions;
- Command Center test-mode nonauthorization;
- risk/session lock time; or
- NQ/YM market-structure rules.

DEBT-015 remains separately governed and is not an ADR-014 through ADR-016 exit criterion absent a newly approved direct-dependency assessment.

## 11. Reporting requirements

Every bounded report SHALL include exact command, environment isolation, fixture/evidence identity, source hashes, pass/fail/skip count, runtime, excluded suites, failure disposition, debt IDs, and whether any live process or production persistence was altered.

No scoped or synthetic pass SHALL be called production-ready.

## 12. Completion and deployment gates

Completion requires:

1. approved ADR-014 remains governing and ADR-015/ADR-016 receive separate explicit approval;
2. coordinated canonical amendments approved;
3. independent A/B/C suites pass;
4. full isolated integration passes;
5. broad regression disposition;
6. bidirectional traceability complete;
7. every debt applicable to production readiness retired/resolved and the startup zero-blocking-debt proof passes;
8. Architecture, Specification, Implementation, Verification, and Traceability gates PASS;
9. exact deployment artifact/config identity; and
10. explicit deployment authorization.

Production restart and entry authorization remain separately controlled after deployment authorization.

## 13. Expected Implementation and Verification

Expected implementation areas under test:

- Entry Agent receiver/session transaction and projections;
- Listener Supervisor logical writers and the ownership-separated tables in the shared physical runtime-authority store;
- Executor health/restart request and pure watchdog paths;
- Rithmic listener Bridge Controller and health writer;
- local runtime-authority control database and nonauthoritative shared projection publisher;
- Trade Manager, Entry Agent, Command Center downstream readiness;
- startup/manual-start/shutdown orchestration; and
- diagnostic endpoints.

Expected verification artifacts:

- ADR-014 rollover/atomicity/crash suite;
- ADR-015 supervisor/threshold/fence/cross-symbol suite;
- ADR-016 health persistence/bridge/corruption suite;
- ATR rehydration suite;
- diagnostic purity suite;
- isolated cold/manual integration report; and
- approved evidence manifests and traceability matrix.

Traceability: `Architecture/Audits/2026-07-17_ADR015_016_Clause_Traceability_Registry_DRAFT.md` is the draft package's Phase 3B semantic clause/scenario/assertion forward/reverse registry. Section 2.1 defines verification families. `Architecture/Traceability/2026-07-17_Production_Recovery_Documentation_Traceability_Matrix.md` is a noncanonical package-level evidence index and explicitly defers clause mapping to the registry. No traceability record creates authority, implementation conformance, verification completion, deployment permission, `READY_LOCKED`, or trading authorization.
