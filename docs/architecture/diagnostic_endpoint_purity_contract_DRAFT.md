# Diagnostic Endpoint Purity Contract

Version: Draft 0.4 — Phase 3B remediation

Status: **DRAFT - NOT CANONICAL - NOT APPROVED**

Proposed Authority: Constitution section 16; Lifecycle Engine section 32; ADR-012 section 3.6; ADR-015 and ADR-016 after approval

Implementation Authorization: None

Review basis: exact production source tree `704fd715cad3aad281c534f8337840e3aab96234` committed by `869b3f08df5c5dbfa975246547455ad185288605`. This document specifies required future behavior and does not authorize source changes.

## 1. Normative invariant

Every GET, HEAD, and OPTIONS endpoint SHALL be observational only. Request arrival SHALL NOT be treated as a domain, recovery, reconciliation, readiness, publication, or lifecycle event.

The invariant applies to the endpoint handler, every transitive dependency, every failure path, and every remote endpoint it invokes. A locally pure handler that calls a mutating upstream GET is impure.

Independent HTTP access telemetry MAY record transport metadata only when it is isolated from domain/control storage and SHALL NOT affect authority, readiness, freshness, caches, throttles, decisions, or response contents.

## 2. Prohibited effects

A GET, HEAD, or OPTIONS endpoint SHALL NOT directly or indirectly:

- mutate in-memory or durable authoritative state;
- hydrate, replace, repair, normalize, back up, or initialize persistence/configuration/cache/index state;
- populate a TradingView ATR cache, build an active-trade index, or create a persistence-corruption backup;
- construct a lazy singleton, pipeline, thread, client, journal, directory, or runtime authority object;
- update domain timestamps, freshness, counters, deduplication state, throttle state, or publication cursors;
- flush pending bars, health, session, observation, trade, or execution state;
- retry, acknowledge, or advance a durable write;
- construct, receive, commit, retire, or repair a session rollover;
- initialize, reset, or advance observation or entry lifecycle state;
- evaluate a control predicate whose evaluation changes state;
- create, cancel, fence, execute, complete, or retry a listener restart;
- create, cancel, fence, execute, complete, or retry a bridge recycle;
- allocate a supervisor generation, listener epoch, bridge generation, incident, or fencing token;
- start, stop, terminate, adopt, or replace a process;
- create, cancel, fill, amend, reconcile, or clear an order, position, trade, or entry request;
- emit a domain decision, reasoning, reconciliation, authorization, or lifecycle journal event; or
- cause a downstream service to perform any prohibited effect.

An error path SHALL return an explicit unavailable/error response without repair, retry, reset, reconciliation, or fallback to an older authority.

## 3. Pure snapshot boundary

### 3.1 Snapshot source

A diagnostic read SHALL consume one immutable prepublished, request-local snapshot supplied by the authoritative owner. If that snapshot does not exist or is not usable, the read SHALL return a deterministic governed read-only disposition such as `UNINITIALIZED`, `UNAVAILABLE`, or `STALE`; it SHALL NOT create the snapshot. The snapshot SHALL identify:

- authority owner;
- authority version;
- session, supervisor, listener-epoch, and bridge-generation identities when applicable;
- snapshot creation timestamp;
- source freshness or degradation state; and
- whether each displayed value is authoritative, projected, historical, or unavailable.

A diagnostic endpoint MAY calculate display-only values from that snapshot. It SHALL NOT call a writer, recovery primitive, control evaluator, or mutating refresh function. A `persist=false`, `dry_run`, query flag, decorator convention, or function name containing `snapshot` is not sufficient unless the writer boundary rejects invocation from the projection call graph.

### 3.2 Projection and historical data

OneDrive/shared JSON and other projection files MAY be displayed only as `PROJECTION_NONAUTHORITATIVE`. They SHALL NOT be merged into an authoritative health, readiness, session, or trade-control answer.

Historical diagnostics SHALL be labeled with their recorded identities and timestamps. They SHALL NOT be presented as current merely because the file or endpoint is reachable.

### 3.3 HEAD and OPTIONS

HEAD SHALL execute no path that GET is prohibited from executing. OPTIONS SHALL return static route metadata and CORS information only. Neither method SHALL initialize lazy domain state or call an application handler with side effects.

## 4. Operational command boundary

Every mutation SHALL be owned by an explicit command or event boundary. A command boundary SHALL:

- use POST or an authenticated local IPC command, never GET, HEAD, or OPTIONS;
- identify the sole authority owner;
- authenticate and authorize the caller;
- require an idempotency key and expected authority version;
- include the applicable session, supervisor generation, listener epoch, bridge generation, incident, and fencing identities;
- commit its result durably before acknowledgement;
- return the committed identity and disposition;
- emit one domain audit event; and
- reject duplicate content under a different identity and conflicting content under the same identity.

Entry-safety evaluation MAY reject an entry request. It SHALL NOT initiate feed recovery, listener restart, bridge recycle, reconciliation, or persistence repair as a side effect.

## 5. Commit-bound production GET audit

### 5.1 Evidence identity and permanence boundary

The permanent architecture rule is sections 1 through 4: every diagnostic GET, HEAD, and OPTIONS route SHALL remain observational. The inventory below is a source-bound nonconformance record, not a timeless route catalog. It was reproduced from production source tree `704fd715cad3aad281c534f8337840e3aab96234`, committed by `869b3f08df5c5dbfa975246547455ad185288605`. A later source commit SHALL regenerate the route manifest and transitive call graph before implementation conformance or runtime purity verification is evaluated.

Exactly thirteen service/path entries in that tree have a demonstrated direct or transitive mutation. This contract identifies migration work only; none is corrected in source by this draft.

### 5.2 Exact current nonconformance inventory

| ID | Service and route | Exact registration and transitive call path in `869b3f...` | Current mutation | Required future read-only behavior and command boundary |
|---|---|---|---|---|
| `GET-EXEC-001` | Executor `GET /debug/watchdog` | `executor.py:1945-1947` -> `build_watchdog_state()` at `618-664` -> listener restart path | Stale evaluation can update restart state/throttles and spawn or terminate listener processes. | GET SHALL consume an immutable Listener Supervisor snapshot. Recovery SHALL use an authenticated, fenced restart-request command. |
| `GET-EXEC-002` | Executor `GET /debug/watchdog_alert` | `executor.py:1950-1963` -> `build_watchdog_state()` at `618-664` | Same watchdog/restart mutation as `GET-EXEC-001`. | Same snapshot and restart-command split; the alert response SHALL be request-local projection only. |
| `GET-EXEC-003` | Executor `GET /sync_snapshot` | `executor.py:1966-1986` -> flat-symbol working-order clear -> `save_executor_state()` | Clears working orders and durably writes Executor state. | GET SHALL read an immutable Executor snapshot. Clearing SHALL use an authenticated reconciliation command with expected state version and idempotency key. |
| `GET-EA-001` | Entry Agent `GET /debug/entry-liquidity` | `EntryAgent/tv_context_server.py:589-623`, call at `605` -> `entry_agent.build_entry_status()` at `EntryAgent/entry_agent.py:4668-4682` -> `run_once(..., persist=True)` at `3976-4052` -> `append_entry_agent_audit_row(snapshot)` and `persist_state(snapshot)` | Appends the Entry Agent audit row and persists Entry Agent pipeline state. This route does not call the receiver's decision/reasoning append helpers; that separate mutation belongs to `GET-EA-002`. | GET SHALL consume a prepublished immutable entry-liquidity snapshot or return `UNINITIALIZED`, `UNAVAILABLE`, or `STALE`. Pipeline execution/persistence SHALL occur only at an explicit event/command boundary. |
| `GET-EA-002` | Entry Agent `GET /entry/status` | `EntryAgent/tv_context_server.py:672-706` -> `build_entry_status()` -> `run_once(..., persist=True)` -> `append_entry_agent_audit_row`/`persist_state`; response path at `697-699` additionally calls `append_entry_decision_log` and `append_entry_reasoning_log` | Appends the Entry Agent audit row, persists pipeline state, and appends receiver decision/reasoning log records. | GET SHALL consume the immutable status snapshot only. Snapshot publication and all audit/decision/reasoning append work SHALL occur before exposure at the owning event/command boundary. |
| `GET-TM-001` | Trade Manager `GET /debug/risk_state` | `Engines/trade_manager.py:3979-3995` -> `load_state()`, Executor `/sync_snapshot`, orphan evaluation/event, `save_state()`, and noon processing | Hydrates/repairs state on error paths, calls a mutating downstream GET, appends orphan evidence, updates state, and may run noon logic. | GET SHALL join immutable Trade Manager and Executor snapshots. Reconciliation/publication SHALL use authenticated commands/events. |
| `GET-TM-002` | Trade Manager `GET /trades` | `Engines/trade_manager.py:5782-5799` -> `refresh_trades_from_executor_activity()` at `3893-3936` -> noon processing, `load_state()`, Executor reconciliation, and `save_state()` | Synchronizes trades, performs noon processing, calls mutating Executor snapshot, and persists state/events. | GET SHALL filter one committed Trade Manager snapshot. Synchronization and noon-runner behavior SHALL use separate idempotent event/command boundaries. |
| `GET-TM-003` | Trade Manager `GET /replay/<trade_id>` | `Engines/trade_manager.py:5892-5905` -> `refresh_trades_from_executor_activity()` | Same synchronization, reconciliation, noon, and persistence mutations as `GET-TM-002`. | GET SHALL replay a selected immutable committed state version without refresh. |
| `GET-TM-004` | Trade Manager `GET /debug/tradingview/atr/<symbol>` | `Engines/trade_manager.py:5554-5572` -> `get_tradingview_atr()` at `4854-4863` -> persisted-state lookup/cache path | On a cold hit, populates `TRADINGVIEW_ATR_CACHE`; corrupt persistence can reach the backup path. | GET SHALL read a prepublished immutable ATR projection or return a governed unavailable result. ATR ingestion/cache construction SHALL be owned by an event/startup command. |
| `GET-TM-005` | Trade Manager `GET /debug/tradingview/atr_status` | `Engines/trade_manager.py:5575-5577` -> `find_tradingview_atr_record()` at `2439-2464` | Cold persisted-state hits populate `TRADINGVIEW_ATR_CACHE`. | GET SHALL derive all symbol rows from one immutable preexisting ATR projection and SHALL NOT populate or refresh the cache. |
| `GET-TM-006` | Trade Manager `GET /debug/noon_runner_flatten` | `Engines/trade_manager.py:5636-5638` -> status builder at `3807-3820` -> `load_state()` | Loads/normalizes persistence; corrupt-state path can create a backup. | GET SHALL read immutable state/policy snapshots. Hydration, corruption disposition, repair, backup, and noon execution SHALL remain explicit startup/command actions. |
| `GET-TM-007` | Trade Manager `GET /events` | `Engines/trade_manager.py:5864-5874` -> `load_state()` | Loads/normalizes persistence; corrupt-state path can create a backup. | GET SHALL read an immutable event snapshot or return a governed unavailable result. |
| `GET-TM-008` | Trade Manager `GET /debug/atr_trade/<trade_id>` | `Engines/trade_manager.py:5936-5961` -> `load_state()` | Loads/normalizes persistence; corrupt-state path can create a backup. | GET SHALL join immutable trade and ATR/bar audit snapshots without hydration or repair. |

### 5.3 Required migration and route-specific verification

For each row above, future implementation SHALL remove every listed mutation from the route and every transitive dependency. The replacement GET SHALL consume one immutable prepublished snapshot or return a deterministic read-only disposition. The owning authenticated event, startup transaction, or POST command SHALL perform any required persistence, reconciliation, cache construction, log append, repair, backup, or process control.

Each route SHALL have a positive purity scenario, cold/uninitialized scenario, 100 sequential-read scenario, 20 concurrent-read scenario, absent/unavailable-snapshot scenario, and corruption-path scenario when persistence is reachable. Assertions SHALL prove no authoritative file, database row, cache object, state version, index, timestamp, log, journal, process, order, position, pending entry request, restart incident, or authorization changes because of the read. `GET-EA-001` and `GET-EA-002` SHALL prove that `run_once(..., persist=True)` and pipeline-state persistence are unreachable; `GET-EA-002` SHALL additionally prove that both receiver decision/reasoning log append helpers are unreachable. `GET-TM-004` and `GET-TM-005` SHALL prove no `TRADINGVIEW_ATR_CACHE` creation or replacement. `GET-EXEC-001` and `GET-EXEC-002` SHALL prove no restart request, fence, execution, epoch, or process mutation. `GET-EXEC-003`, `GET-TM-001`, `GET-TM-002`, and `GET-TM-003` SHALL prove no direct or transitive order/state reconciliation.

### 5.4 Disproved Phase 3A inventory entries

The following seven routes are absent from the exact committed source registrations and SHALL NOT be represented as current-source nonconformance:

- Executor `/debug/tick_pipeline`;
- Entry Agent `/entry/executor_status`;
- Trade Manager `/debug/tick_pipeline`;
- Trade Manager `/health`;
- Trade Manager `/debug/nonclosed_trades`;
- Trade Manager `/paper_account_snapshot`; and
- Trade Manager `/config/trade_manager_mode`.

The Phase 3A claims involving `get_executor_tick_pipeline`, `get_trade_manager_tick_pipeline`, `PERSISTENCE_STATE_CACHE`, `PERSISTENCE_STATE_CACHE_LOADED`, active-trade-index mutation, and configuration-cache hydration are not supported by this source tree and SHALL NOT be used as current-source evidence. They MAY appear in future implementation design only when explicitly labeled proposed and SHALL NOT be used to claim present nonconformance.

Executor `GET /account_snapshot` at `executor.py:1888-1890` calls its local JSON snapshot builder at `854-880`; it is not a Trade Manager proxy in this tree. No mutation was demonstrated in that path. It remains subject to the permanent purity rule and future generated manifest.

### 5.5 Other inspected routes and manifest closure

Other committed GET routes for Executor, Trade Manager, and Entry Agent were inspected and no mutation was demonstrated in their reachable application call graphs. That negative finding is bound to the stated tree and is not a permanent exemption. Projection-backed routes SHALL label projection data nonauthoritative, and endpoint reachability SHALL NOT establish readiness.

Before runtime purity verification may pass, a generated route manifest SHALL enumerate every registered GET, HEAD, and OPTIONS route in every production service and bind each to a call-graph disposition and purity scenario. The manifest SHALL fail closed if a registered read route is absent or any transitive path reaches mutation, state/configuration hydration, repair, backup creation, cache population/replacement, index construction, pipeline/singleton initialization, process control, authority refresh, durable write, or domain/audit event append. A later source commit SHALL invalidate and regenerate the source-bound inventory; it SHALL NOT inherit the thirteen-entry count.

## 6. Migration constraints

Migration SHALL proceed in this order for each impure GET:

1. Define the authority-owned immutable snapshot and authenticated command/event schema.
2. Define explicit owner startup transactions for persistence hydration, configuration hydration, integrity/corruption disposition, repair/backup creation, cache/index construction, and pipeline initialization; none may be entered from a diagnostic method.
3. Implement command/startup idempotency, expected-version validation, fencing where applicable, durable acknowledgement, and audit behavior.
4. Move every mutation to the applicable command/event/startup boundary.
5. Remove all legacy GET-triggered and transitive recovery, reconciliation, hydration, repair, backup, caching, reindexing, and initialization paths.
6. Change the GET to snapshot-only behavior with deterministic `UNINITIALIZED`, `UNAVAILABLE`, or `STALE` behavior when no eligible snapshot exists.
7. Update all direct and proxy consumers.
8. Run the purity verification in section 7.
9. Remove legacy compatibility code after consumer verification.

A migration SHALL NOT use dual-write authority, GET-triggered compatibility behavior, or fallback from the new pure GET to the legacy mutating GET.

## 7. Required idempotency and purity verification

For every GET, HEAD, and OPTIONS route and every alternate/proxy route, verification SHALL:

- enumerate the transitive call graph to every writer, process-control, order-control, lifecycle, clock/freshness, and journal primitive;
- capture hashes and metadata for every authoritative and projection file before and after 100 sequential successful reads, 100 sequential error-path reads, and 20 concurrent reads;
- snapshot in-memory Supervisor, health, session, observation, entry lifecycle, Trade Manager, Executor, cursor, throttle, deduplication, scheduler, and authorization state before and after;
- capture process tree, listener authority, bridge generation, port ownership, active orders, active positions, and pending entry requests before and after;
- exercise reads while session commits, restart cancellation/fencing, bridge recycle, health persistence retry, order reconciliation, and trade synchronization are pending;
- exercise cold/uninitialized and warm cache/pipeline states and prove reads create no singleton, thread, client session, journal handle, directory, cache entry, or initialization cursor;
- exercise corrupt, unavailable, missing, and changed persistence/configuration and prove reads perform no hydration, normalization, repair, backup creation, cache signature/value replacement, active-trade index construction, or fallback;
- exercise direct and transitive proxy routes with wrong-generation, stale, uninitialized, and absent snapshots and require deterministic read-only `UNINITIALIZED`, `UNAVAILABLE`, or `STALE` results;
- instrument the exact current mutation primitives `build_watchdog_state`, the listener restart path, flat-symbol working-order clearing, `save_executor_state`, `build_entry_status`, `run_once(..., persist=True)`, pipeline-state persistence, decision/reasoning log append, `refresh_trades_from_executor_activity`, noon-runner processing, `load_state`, corrupt-persistence backup creation, and TradingView ATR cache writers and prove they are unreachable from every registered GET/HEAD/OPTIONS call graph after remediation;
- prove zero new domain/control/audit events except isolated HTTP access telemetry;
- prove no persistence retry or cursor acknowledgement occurs;
- prove serialization/dependency/timeouts return error without repair;
- prove the same immutable snapshot yields the same normalized response; and
- prove every replacement command is idempotent under sequential duplicates, concurrent duplicates, delayed duplicates, and process restart between commit and response.

The verification SHALL fail on any state-version, timestamp, file, journal, process, port, order, position, authority, or authorization difference attributable to the read.

## 8. Startup probe rule

Startup readiness probes SHALL call only routes proven pure by section 7. A readiness probe SHALL validate the returned positive proof; HTTP status or endpoint reachability alone SHALL NOT satisfy readiness.

If no pure endpoint exists for a required authority proof, startup SHALL fail with `READINESS_PROBE_CONTRACT_MISSING`. It SHALL NOT invoke a legacy mutating GET.

## 9. Governance boundary

Architecture-document approval would approve this contract's required future behavior only. It would not assert that the thirteen source-bound paths are conforming, authorize source changes, satisfy runtime purity verification, or authorize deployment. Approved ADR-014 remains the fixed governing dependency; ADR-015, ADR-016, and this contract remain unapproved drafts in this Phase 3B record.

This draft does not approve any endpoint, command, source modification, migration, implementation conformance, runtime verification, deployment, restart, `READY_LOCKED`, or trading authorization. This draft is eligible for a separate canonical-incorporation decision only after ADR-015/ADR-016 and this contract independently pass approval review and the clause-level obligation traceability is complete. Canonical incorporation SHALL precede and govern any later implementation authorization. Implementation conformance SHALL require all thirteen source-bound migration obligations, plus any path discovered by the regenerated manifest for the implementation commit, to be corrected at explicit startup/command boundaries. Runtime purity verification SHALL then prove the corrected source; deployment authorization remains a later separate gate. Neither implementation nor test evidence SHALL retroactively create or substitute for canonical authority.

Traceability: `Architecture/Traceability/2026-07-17_Production_Recovery_Documentation_Traceability_Matrix.md`.

Clause-level traceability: every normative clause in this draft is assigned a stable `DEP-REQ-###` identity with forward and reverse verification mapping in `Architecture/Audits/2026-07-17_ADR015_016_Clause_Traceability_Registry_DRAFT.md`. The external recovery matrix is a package-level index only and SHALL NOT substitute for the clause-level registry.
