# Diagnostic Endpoint Purity Contract

Version: Draft 0.3

Status: **DRAFT - NOT CANONICAL - NOT APPROVED**

Proposed Authority: Constitution section 16; Lifecycle Engine section 32; ADR-012 section 3.6; ADR-015 and ADR-016 after approval

Implementation Authorization: None

Review basis: production source as preserved on 2026-07-17. This document specifies required future behavior and does not authorize source changes.

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

## 5. Complete production GET audit

### 5.1 Confirmed mutating GET endpoints

The following nineteen GET paths are noncompliant in the preserved 2026-07-17 production source. `CONFIRMED` means the mutation is visible in the static handler or its transitive call graph, including cold/uninitialized and corrupt-persistence paths even when normal startup often initializes the same object first. This table defines the required replacement; it does not authorize implementation.

| Service and GET path | Confirmed mutation | Required replacement command or event boundary | Migration strategy | Required idempotency verification |
|---|---|---|---|---|
| Executor `GET /debug/watchdog` | `build_watchdog_state()` evaluates staleness, calls the listener restart path, mutates restart throttles/state, and can spawn/terminate listener processes. | Pure `GET /debug/watchdog` SHALL read the Listener Supervisor snapshot. Recovery SHALL enter through authenticated `POST /listener-supervisor/restart-requests`, owned by the Listener Supervisor and carrying the ADR-015 request/fence identities. | Introduce the Supervisor command and snapshot contracts; route every recovery caller to the command; remove process control from Executor; then switch the GET to snapshot-only. No compatibility mode SHALL preserve GET-triggered recovery. | 100 sequential and 20 concurrent GETs SHALL create zero requests/restarts. Repeating one POST with the same incident/version SHALL return the same committed disposition and SHALL cause at most one effective restart. |
| Executor `GET /debug/watchdog_alert` | Calls the same mutating watchdog builder and can trigger the same restart path. | Same pure Supervisor snapshot and authenticated restart-request command as above. | Migrate atomically with `/debug/watchdog`; the alert response SHALL be derived from the already-created immutable snapshot. | Repeated and concurrent GETs SHALL leave restart incident/version/fence/execution/process state byte-for-byte unchanged. |
| Executor `GET /sync_snapshot` | Clears working orders for flat symbols and calls `save_executor_state()`. | Pure `GET /sync_snapshot` SHALL return an immutable Executor snapshot. Orphan clearing SHALL occur through authenticated `POST /executor/reconciliation/clear-flat-working-orders` or the owning execution-state transition, with expected Executor state version. | Add the command and snapshot first; move all clearing out of snapshot construction; update local consumers; reject legacy GET-side clearing; retain response compatibility only for read fields. | Repeating the same reconciliation command key and expected version SHALL yield one committed clear. 100 sequential and 20 concurrent GETs SHALL change no order, state version, file, or journal. |
| Entry Agent `GET /entry/executor_status` | Calls Executor `GET /sync_snapshot`; the mutation is transitive even though the Entry Agent handler writes nothing directly. | The Entry Agent SHALL call the pure Executor snapshot endpoint only. Reconciliation remains at the Executor command boundary above. | Migrate only after Executor `/sync_snapshot` is proven pure; add an upstream-purity contract assertion and remove any fallback to a legacy mutating route. | Repeated direct and proxied GETs SHALL produce no Executor order/state/journal mutation; failure of the upstream snapshot SHALL return unavailable without reconciliation. |
| Trade Manager `GET /debug/risk_state` | Computes orphan exposure, persists an orphan-exposure event, updates `last_update_at`, and calls `save_state()`. It also transitively fetches Executor `/sync_snapshot`. | Pure GET SHALL calculate a display projection from immutable Trade Manager and Executor snapshots. Orphan reconciliation/publication SHALL enter through authenticated `POST /trade-manager/reconciliation/orphan-exposure`, owned by Trade Manager and carrying expected Trade Manager and Executor snapshot versions. | Introduce the versioned command; move persistence and publication out of the diagnostic builder; migrate upstream Executor access to its pure snapshot; then make GET projection-only. | One reconciliation key/version pair SHALL create at most one event/state update. Sequential/concurrent GETs SHALL not change `last_update_at`, events, state files, or Executor state. |
| Trade Manager `GET /trades` | Calls `refresh_trades_from_executor_activity()`, which synchronizes trade state, persists state/events, and can perform noon-runner flatten processing; it also depends on Executor `/sync_snapshot`. | Pure GET SHALL read a committed Trade Manager snapshot. Executor activity synchronization SHALL be an authenticated event/command ingestion path. Noon-runner flatten SHALL be a separately authenticated scheduled command with a session-date policy identity. | Split refresh, noon-runner, and response projection; run synchronization from the authoritative event/command path; migrate Executor reads; remove refresh from GET; preserve filtering as request-local projection only. | Duplicate Executor activity event IDs SHALL commit once. Duplicate noon-runner session/policy keys SHALL execute once. Sequential/concurrent GETs SHALL not alter trades, orders, events, timestamps, or scheduler state. |
| Trade Manager `GET /replay/<trade_id>` | Calls `refresh_trades_from_executor_activity()` before reconstructing the replay and therefore performs the same synchronization/persistence side effects. | Pure GET SHALL replay only the selected committed Trade Manager snapshot. Synchronization remains at the command/event boundary defined for `/trades`. | Complete the `/trades` refresh split, then bind replay to a requested or current committed state version. Missing/stale data SHALL be reported, not refreshed. | Repeated replay GETs for one trade/version SHALL leave every authority and journal unchanged and SHALL return the same reconstruction for the same inputs. |
| Trade Manager `GET /debug/tradingview/atr/<symbol>` | `get_tradingview_atr()` writes `TRADINGVIEW_ATR_CACHE[normalized_symbol]` on a cold-cache hit from persisted state. | TradingView ATR ingestion SHALL remain at the authenticated/validated `POST /webhook/tradingview/atr` event boundary. Any cache hydration SHALL occur in that event transaction or an explicit startup-owned `INITIALIZE_TV_ATR_CACHE` command before reads. GET SHALL read an immutable cache/store snapshot and return `UNAVAILABLE` on a miss. | Move cold-cache population out of `get_tradingview_atr()`; prehydrate through the owner command where required; update status consumers; prohibit GET fallback that populates the cache. | Cold, warm, missing, and corrupt-state cases under 100 sequential/20 concurrent GETs SHALL leave cache keys/values/object identity, state files, timestamps, events, and cursors unchanged. Repeating the hydration command with one idempotency/version key SHALL commit at most once. |
| Trade Manager `GET /debug/tradingview/atr_status` | Its builder calls `find_tradingview_atr_record()` per symbol, which writes `TRADINGVIEW_ATR_CACHE[candidate]` on a cold persisted-state hit. | Use the same POST/event or startup-owned cache hydration boundary as the symbol route. Status GET SHALL derive all symbols from one immutable preexisting snapshot and SHALL NOT populate cache or refresh freshness state. | Migrate atomically with `/debug/tradingview/atr/<symbol>`; remove the builder's transitive cold-cache branch and bind the response to one snapshot/reference time. | The same cold/warm/missing/corrupt and sequential/concurrent proofs SHALL cover both symbols and prove cache/state/timestamp identity unchanged. |
| Executor `GET /debug/tick_pipeline` | `get_executor_tick_pipeline()` lazily constructs `ExecutorTickPipeline`, loads journals/authority, starts worker threads, opens runtime clients, and mutates the global singleton. | Pipeline creation SHALL occur only in the Executor's explicit startup initialization transaction. GET SHALL read an already-published immutable pipeline snapshot or return `UNINITIALIZED`; it SHALL NOT call the lazy initializer. | Initialize and verify the pipeline before endpoint readiness; publish immutable snapshots; update the GET to read the snapshot reference; remove every diagnostic-call path to `get_executor_tick_pipeline()`. | Cold-start GETs SHALL create no singleton, thread, session, journal handle, directory, cursor, or authority load. Warm sequential/concurrent GETs SHALL leave all pipeline/runtime identities unchanged. Duplicate startup initialization under one attempt/version SHALL create exactly one pipeline. |
| Trade Manager `GET /debug/tick_pipeline` | `get_trade_manager_tick_pipeline()` lazily constructs `TradeManagerTickPipeline`, loads journals, starts worker/notification threads, opens runtime clients, and mutates the global singleton. | Pipeline creation SHALL occur only in the Trade Manager's explicit startup initialization transaction. GET SHALL read an already-published immutable pipeline snapshot or return `UNINITIALIZED`; it SHALL NOT call the lazy initializer. | Apply the same startup-initialize/publish/snapshot split as Executor and remove the route's transitive lazy-initializer call. | Cold-start and warm sequential/concurrent tests SHALL prove no singleton/thread/session/journal/directory/cursor mutation; duplicate startup initialization SHALL produce exactly one pipeline. |
| Trade Manager `GET /health` | Calls `get_trade_manager_tick_pipeline()` and therefore performs the same lazy singleton/journal/thread/client initialization before reporting reachability. | Health GET SHALL report immutable process identity and the already-published pipeline state or `UNINITIALIZED`. Pipeline creation remains exclusively in the explicit Trade Manager startup initialization transaction. | Migrate atomically with Trade Manager `/debug/tick_pipeline`; startup SHALL initialize before health readiness, while an early health read remains observational. | Cold-start health probes SHALL create no pipeline/thread/client/journal/directory/cursor. Warm probes SHALL leave runtime identities unchanged; reachability SHALL remain insufficient for readiness. |
| Trade Manager `GET /debug/nonclosed_trades` | Calls `load_state()`. When `PERSISTENCE_STATE_CACHE_LOADED` is false, the call reads/normalizes persistence, replaces `PERSISTENCE_STATE_CACHE`, sets the loaded flag, and rebuilds the active-trade index; unreadable persistence can call `backup_bad_persistence_file()` and create a `.bak` file. | Trade Manager startup SHALL own an idempotent `INITIALIZE_TRADE_MANAGER_STATE_SNAPSHOT` transaction, including integrity classification and governed corruption handling. GET SHALL read one immutable prepublished trade-state snapshot or return `UNINITIALIZED`, `UNAVAILABLE`, or `STALE`. | Remove `load_state()` and every repair/backup/index primitive from the handler call graph; initialize/publish state before readiness; bind response to snapshot version. | Cold, corrupt, missing, unavailable, and warm persistence cases under sequential/concurrent GETs SHALL prove no cache flag/object/index/file/backup change. Startup initialization duplicates SHALL commit once. |
| Trade Manager `GET /debug/noon_runner_flatten` | `build_noon_runner_flatten_status_payload()` calls `load_state()` and configuration access, reaching state/config cache hydration, active-index rebuild, and corrupt-file backup on cold/error paths. | State and configuration hydration/corruption disposition SHALL occur only in explicit startup owner transactions. GET SHALL combine immutable state/config/policy snapshots or return a governed read-only unavailable disposition. | Replace transitive loaders with versioned snapshot references; keep scheduled flatten execution at its authenticated command boundary. | Prove no state/config cache, index, scheduler, backup, file, event, or flatten action changes for cold/corrupt/changed-config and repeated/concurrent GETs. |
| Trade Manager `GET /paper_account_snapshot` | `build_trade_manager_paper_account_snapshot()` calls `load_state()`, reaching cold state-cache initialization, active-index rebuild, and corrupt-persistence backup creation. | GET SHALL calculate the display account projection from one immutable prepublished Trade Manager state snapshot or return `UNINITIALIZED`/`UNAVAILABLE`/`STALE`. Hydration and corruption handling remain startup-owned. | Remove `load_state()` from the request call graph and publish the required state version during startup/state commits. | Prove no state cache/index/file/backup/timestamp/event mutation across cold, corrupt, unavailable, warm, sequential, and concurrent calls. |
| Trade Manager `GET /events` | Calls `load_state()`, reaching cold state-cache initialization, active-index rebuild, and corrupt-persistence backup creation before reading events. | GET SHALL read immutable persisted/runtime event snapshots already published by their owners. Event-store hydration/repair/backup SHALL use startup or an authenticated maintenance command. | Replace the lazy state loader with immutable event/state snapshot references and return a governed unavailable disposition when absent. | Repeated and concurrent successful/error reads SHALL not load/replace caches, construct indexes, create backups, advance cursors, or append/trim events. |
| Trade Manager `GET /config/trade_manager_mode` | `load_trade_manager_config()` mutates `TRADE_MANAGER_CONFIG_CACHE_SIGNATURE` and `TRADE_MANAGER_CONFIG_CACHE_VALUE` on cold access and whenever file signature/content changes. | An explicit startup-owned `INITIALIZE_TRADE_MANAGER_CONFIG_SNAPSHOT` transaction or authenticated configuration-update command SHALL validate and publish the immutable configuration snapshot. GET SHALL only read that snapshot. | Remove configuration-file/stat/cache hydration from the GET path; changed configuration remains pending/unavailable until the owner command publishes a new version. | Cold, missing, corrupt, changed, stale, and wrong-version configuration cases SHALL prove no cache signature/value mutation under sequential/concurrent reads; duplicate owner commands commit once. |
| Trade Manager `GET /debug/atr_trade/<trade_id>` | Calls `load_state()` before reading the trade, reaching cold persistence hydration, active-index rebuild, and corrupt-persistence backup creation. | GET SHALL join an immutable trade snapshot with immutable ATR/bar audit snapshots or return a governed read-only unavailable result. | Remove `load_state()` and all repair/backup/index calls from the transitive path; bind response to explicit snapshot versions. | Cold/corrupt/unavailable/warm and sequential/concurrent calls SHALL create no state cache, index, backup, ATR cache, file, or cursor mutation. |
| Executor `GET /account_snapshot` | Transitively calls Trade Manager `GET /paper_account_snapshot`, whose cold/error path can hydrate Trade Manager state, rebuild the active-trade index, or create a corrupt-persistence backup. | Executor SHALL call only the corrected pure Trade Manager snapshot route and return its immutable versioned result or a deterministic unavailable disposition. | Migrate after Trade Manager `/paper_account_snapshot` is proven pure; prohibit fallback to the legacy mutating downstream route. | Direct and proxied cold/corrupt/unavailable/warm tests SHALL prove zero mutation in both processes, including no cache/index/backup creation. |

### 5.2 Executor GET inventory

| Route | 2026-07-17 audit disposition | Required implementation disposition before runtime purity verification |
|---|---|---|
| `/health` | No domain mutation identified in handler. | Prove pure; report process reachability separately from readiness. |
| `/orders` | No domain mutation identified in handler. | Return an immutable, versioned Executor snapshot. |
| `/positions` | No domain mutation identified in handler. | Return an immutable, versioned Executor snapshot. |
| `/account_snapshot` | **Transitively mutating GET confirmed through Trade Manager `/paper_account_snapshot` cold/error persistence path.** | Apply section 5.1 replacement; no fallback to a mutating downstream route. |
| `/debug/live_prices` | No domain mutation identified in handler. | Label epoch and snapshot identities; prove pure. |
| `/debug/feed_health` | No mutation identified, but it reads the legacy shared health projection. | Replace control-looking output with the ADR-016 authoritative Supervisor snapshot or label legacy data `PROJECTION_NONAUTHORITATIVE`; prove it cannot affect control. |
| `/listener_feed_health` | No mutation identified, but it reads the legacy shared health projection. | Same requirement as `/debug/feed_health`. |
| `/debug/watchdog` | **Mutating GET confirmed.** | Apply section 5.1 replacement. |
| `/debug/watchdog_alert` | **Mutating GET confirmed.** | Apply section 5.1 replacement. |
| `/sync_snapshot` | **Mutating GET confirmed.** | Apply section 5.1 replacement. |
| `/debug/tick_pipeline` | **Mutating GET confirmed through lazy pipeline initialization.** | Apply section 5.1 replacement. |

### 5.3 Trade Manager GET inventory

| Route | 2026-07-17 audit disposition | Required implementation disposition before runtime purity verification |
|---|---|---|
| `/debug/risk_state` | **Mutating GET confirmed.** | Apply section 5.1 replacement. |
| `/debug/nonclosed_trades` | **Mutating GET confirmed through `load_state()` cold/error persistence path.** | Apply section 5.1 replacement. |
| `/debug/instruments` | No domain mutation identified. | Prove configuration reads do not repair or write defaults. |
| `/debug/tv-context-proxy` | No domain mutation identified. | Return request-local copy and prove pure. |
| `/debug/tradingview/atr/<symbol>` | **Mutating GET confirmed through cold-cache population.** | Apply section 5.1 replacement; label TradingView ATR noncanonical. |
| `/debug/tradingview/atr_status` | **Mutating GET confirmed through transitive cold-cache population.** | Apply section 5.1 replacement. |
| `/debug/canonical/atr_status` | No route-local mutation identified. | Prove the builder performs no mutation and includes current listener epoch. |
| `/debug/atr_shadow` and `/debug/atr_shadow/<symbol>` | No domain mutation identified. | Label file-backed data with recorded identity/freshness and prove pure. |
| `/debug/noon_runner_flatten` | **Mutating GET confirmed through state/configuration hydration and corrupt-persistence backup reachability.** | Apply section 5.1 replacement; prove the builder cannot execute or advance the noon runner. |
| `/paper_account_snapshot` | **Mutating GET confirmed through `load_state()` cold/error persistence path.** | Apply section 5.1 replacement. |
| `/health` | **Mutating GET confirmed through lazy pipeline initialization.** | Apply section 5.1 replacement; report reachability separately from readiness. |
| `/debug/tick_pipeline` | **Mutating GET confirmed through lazy pipeline initialization.** | Apply section 5.1 replacement. |
| `/trades` | **Mutating GET confirmed.** | Apply section 5.1 replacement. |
| `/trade_screenshots/<path:filename>` | No domain mutation identified. | Prove path resolution/access logging is isolated from domain state. |
| `/events` | **Mutating GET confirmed through `load_state()` cold/error persistence path.** | Apply section 5.1 replacement; bind to immutable event snapshot. |
| `/debug/version` | No domain mutation identified. | Prove pure; version presence is not readiness. |
| `/config/trade_manager_mode` GET branch | **Mutating GET confirmed through configuration cache signature/value hydration or replacement.** | Apply section 5.1 replacement; split immutable read and command authorization contracts. |
| `/replay/<trade_id>` | **Mutating GET confirmed.** | Apply section 5.1 replacement. |
| `/debug/atr/<symbol>` | No domain mutation identified. | Prove bar/ATR readers do not repair, publish, cache, or advance cursors. |
| `/debug/atr_trade/<trade_id>` | **Mutating GET confirmed through `load_state()` cold/error persistence path.** | Apply section 5.1 replacement. |

### 5.4 Entry Agent GET inventory

| Route | 2026-07-17 audit disposition | Required implementation disposition before runtime purity verification |
|---|---|---|
| `/debug/tv-context-receipt` | No domain mutation identified. | Return immutable receipt snapshot; receipt existence SHALL NOT imply real-public-webhook readiness unless correlated under the Startup specification. |
| `/debug/tv-ladder-validation` | No domain mutation identified; explicitly test-only. | Prove it cannot write canonical persistence or authorization and retain the test/unverified label. |
| `/context` | No domain mutation identified. | Identify raw/projection/canonical authority explicitly; file existence SHALL NOT imply authority. |
| `/debug/tv-context` | No domain mutation identified. | Label receiver/raw projection separately from canonical session authority. |
| `/debug/entry-liquidity` | Uses projection-guarded `build_entry_status`; no mutation identified. | Prove the projection guard rejects every transitive writer and the route emits no reasoning/decision events. |
| `/debug/entry-log` | No domain mutation identified. | Prove tail reads do not rotate, truncate, checkpoint, or advance a cursor. |
| `/entry/reasoning_log` | No domain mutation identified. | Same log-read requirement. |
| `/entry/status` | Uses projection-guarded `build_entry_status`; no mutation identified. | Prove repeated status reads do not advance session, observation, lifecycle, reasoning logs, or authorization. |
| `/entry/executor_status` | **Transitively mutating GET confirmed.** | Apply section 5.1 replacement. |

### 5.5 Audit completeness rule

Before runtime purity verification may pass, a generated route manifest SHALL enumerate every GET, HEAD, and OPTIONS route registered by Executor, Trade Manager, Entry Agent, Listener Supervisor, Bridge Controller, Command Center backend, launcher/readiness service, and any new recovery service. The test suite SHALL fail when a registered read route lacks a disposition in this contract and an automated purity test, or when any transitive path reaches mutation, persistence/configuration hydration, normalization/repair, backup creation, cache loading/replacement, index construction, ATR cache population, pipeline/singleton/thread/client/journal initialization, or another lazy domain/control primitive.

The Phase 2 static re-audit enumerated every Flask GET/HEAD/OPTIONS registration in `executor.py`, `Engines/trade_manager.py`, and `EntryAgent/tv_context_server.py` on 2026-07-17 and followed each documented route through its direct application dependencies. It confirms nineteen mutating paths: the original twelve, both ATR cold-cache paths, every GET-triggered tick-pipeline initializer, every listed `load_state()` cold/error path, the configuration-cache loader, and the transitive Executor account snapshot. These paths are identified migration obligations and are not corrected in source by this contract. The remaining route dispositions are provisional until the generated call-graph/purity suite proves them; the static count SHALL NOT be treated as permission to omit a newly discovered path. New services proposed by ADR-015 and ADR-016 do not yet exist and SHALL be added to the generated manifest before runtime purity verification.

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
- instrument `load_state`, `_load_state_cached_unlocked`, `_set_state_cache_unlocked`, `backup_bad_persistence_file`, `load_trade_manager_config`, TradingView ATR cache writers, active-index builders, and tick-pipeline initializers and prove they are unreachable from every GET/HEAD/OPTIONS call graph;
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

Architecture-document approval would approve this contract's required future behavior only. It would not assert that the nineteen source paths are conforming, authorize source changes, satisfy runtime purity verification, or authorize deployment. Approved ADR-014 remains the fixed governing dependency; ADR-015, ADR-016, and this contract remain unapproved drafts in this Phase 3A record.

This draft does not approve any endpoint, command, source modification, migration, implementation conformance, runtime verification, deployment, restart, `READY_LOCKED`, or trading authorization. This draft is eligible for a separate canonical-incorporation decision only after ADR-015/ADR-016 and this contract independently pass approval review and the clause-level obligation traceability is complete. Canonical incorporation SHALL precede and govern any later implementation authorization. Implementation conformance SHALL require all nineteen identified migration obligations and any newly discovered path to be corrected at explicit startup/command boundaries. Runtime purity verification SHALL then prove the corrected source; deployment authorization remains a later separate gate. Neither implementation nor test evidence SHALL retroactively create or substitute for canonical authority.

Traceability: `Architecture/Traceability/2026-07-17_Production_Recovery_Documentation_Traceability_Matrix.md`.

Clause-level traceability: every normative clause in this draft is assigned a stable `DEP-REQ-###` identity with forward and reverse verification mapping in `Architecture/Audits/2026-07-17_ADR015_016_Clause_Traceability_Registry_DRAFT.md`. The external recovery matrix is a package-level index only and SHALL NOT substitute for the clause-level registry.
