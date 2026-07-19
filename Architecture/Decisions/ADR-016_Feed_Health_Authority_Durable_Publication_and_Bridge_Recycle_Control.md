# ADR-016 - Feed-Health Authority, Durable Publication, and Bridge-Recycle Control

## 1. Status

**DRAFT 0.7 - PHASE 3C1-R3 F6 TARGETED NORMATIVE REMEDIATION - NOT APPROVED**

**Rewrite date:** 2026-07-17

**Decision authority:** None until explicit architecture approval.

**Implementation authorization:** None. This draft does not authorize storage migration, credential changes, process recycling, production code changes, restart, deployment, entry-lock clearing, or trading.

## 2. Evidence and problem statement

The preserved 2026-07-17 listener evidence proves repeated `WinError 5` failures during atomic replacement of the configured shared feed-health JSON target. The implementation cleared pending health before durable acknowledgement, reread stale persisted projection data, and terminated a bridge that direct current-generation data showed was alive.

The evidence proves the failed atomic replacement operation, target-path role, error code, pending-state loss, stale reread, and false-death control chain. It does not identify the Windows process holding an incompatible handle. This ADR SHALL NOT attribute the denial to OneDrive or any other process without direct handle-level evidence. The projection path being under OneDrive describes storage topology only.

The prior draft ranked direct evidence, local durable control, and shared projection, but did not define the transport, authentication, writer process, store, serialization, reader boundary, closed death predicates, or startup recovery. This rewrite defines those mechanisms completely.

Termination-evidence semantics are bounded by the bundled official RAPI Plus 13.7 documentation at `Rithmic API/RApiPlus.NET.13.7.0.0.zip!/13.7.0.0/doc/html/namespacecom_1_1omnesys_1_1rapi.html` and the wrapper evidence in `rithmic_live_listener.py`. The SDK documents `ConnectionBroken` as an automatically recovering condition and `ConnectionOpened` as initial/recovered connection; `ConnectionClosed` occurs for successful logout/destruction as well as observed closure; `LoginFailed` means login was not accepted but does not by itself prove invalid credentials; `ForcedLogout` is provider-initiated; and `ShutdownSignal` makes the engine inert. `AlertInfo` exposes type, connection, message, and `RpCode`, but the API does not supply one reliable process-terminal cause for every child disappearance. This ADR therefore preserves `UNKNOWN` independently in every unproven termination dimension rather than inferring cause from a PID change or missing process.

## 3. Decision

### 3.1 Governing invariant

Direct authenticated current-supervisor/current-epoch/current-generation events are the immediate liveness authority. One Listener-Supervisor-hosted Health Durable Writer owns health/bridge durable results inside the one physical Runtime Authority Control Database shared at storage level with ADR-015 ownership-separated tables. Shared JSON and Command Center/status output are projections only. Historical logs are diagnostics only.

No file projection, diagnostic response, process existence observation by a nonowner, missing HTTP response, or timestamp copied from an earlier epoch/generation SHALL authorize bridge recycle or full-listener restart.

Direct positive recovery evidence SHALL prevent or cancel an unfenced false-death decision. A process-control action SHALL require a readback-verified durable fence. If durable control is unavailable or ambiguous, new entries and new automatic lifecycle fences SHALL remain blocked.

### 3.2 Components and authority ownership

| Component | Runs in | Produces | Consumes | Lifecycle authority |
|---|---|---|---|---|
| Supervisor OS Authority Adapter | Listener Supervisor process | canonical listener process/lease observations from Windows process handles and the durable lease | Windows process APIs and the supervisor store | none independently; supplies facts to the State Evaluator |
| Health Event Ingress | Listener Supervisor process | validated ingress/acknowledgement facts | authenticated producer frames | none independently; validates and sequences evidence |
| Health Durable Writer | Listener Supervisor process | durable health commits, cursor, immutable committed snapshot | validated ingress queue | sole health-store writer; not a second lifecycle owner |
| Listener Supervisor State Evaluator | Listener Supervisor process | health state, pending/canceled/fenced bridge decisions, ADR-015 restart requests | immediate accepted evidence and committed health state | grants bridge fences; sole full-listener lifecycle owner remains ADR-015 Listener Supervisor |
| Rithmic listener | supervisor-granted listener process | listener lease, connection/login, subscription, tick, bridge-controller facts | supervisor acknowledgements and bridge commands | none for full listener |
| Bridge Controller | inside Rithmic listener | bridge process/generation/exit/recovery facts | current-generation fenced bridge commands | executes one bridge-generation action after durable fence; cannot allocate/fence listener epoch |
| Executor | Executor process | accepted-delivery and downstream-consumption facts | current immutable health snapshot for entry blocking | no listener or bridge process action |
| Projection Publisher | Listener Supervisor process | shared JSON projection | committed immutable health snapshot | no control authority |
| Startup/diagnostic/Command Center consumers | their owning processes | access telemetry only | read-only immutable snapshot/projection | no health or lifecycle authority |

Health Durable Writer SHALL be a subsystem of the Listener Supervisor process. It SHALL NOT run inside the supervised listener, Executor, Trade Manager, Entry Agent, launcher, Command Center, or a separate unowned service.

### 3.3 Runtime evidence transport

#### 3.3.1 Pipe and direction

All direct runtime health evidence from the listener, Bridge Controller, and Executor SHALL use one local duplex Windows named pipe:

```text
\\.\pipe\RandleSystem.HealthEvents.v1
```

The Listener Supervisor process SHALL create and own the pipe. The listener, Bridge Controller, and Executor SHALL be clients. The pipe SHALL carry producer events from clients to the supervisor and durable acknowledgements, capability revocation, and fenced bridge commands from the supervisor to the applicable client.

Supervisor-owned `LISTENER_PROCESS_*`, lease, epoch-fence, and shutdown-intent facts SHALL originate only in the in-process Supervisor OS Authority Adapter. The adapter SHALL obtain process facts from the exact supervisor-owned Windows process handle and creation identity and lease facts from the current durable supervisor lease; it SHALL serialize the same canonical event schema and pass it directly to the same validation/writer queue. It SHALL NOT use the named pipe, PID search, command-line matching, status endpoints, or projection files. No other in-process caller SHALL submit Supervisor fact types.

Shared files, loopback HTTP, Command Center polling, status GET routes, stdout scraping, and process command-line discovery SHALL NOT be runtime health evidence transports.

#### 3.3.2 Connection authentication

The pipe discretionary ACL SHALL permit only `SYSTEM`, `Administrators`, and the configured production runtime Windows SID. The server SHALL obtain the client PID through `GetNamedPipeClientProcessId`, resolve process creation time and executable/build identity, and compare them with the producer registration before accepting an event. Each client SHALL obtain the server PID through `GetNamedPipeServerProcessId`, verify the configured Supervisor Windows SID, process creation identity, and approved executable/build hash, and require the handshake `supervisor_generation_id` to equal its current owner grant before sending an event or accepting a command.

For each supervisor generation:

1. a producer connects under the permitted Windows SID;
2. the supervisor verifies PID, process creation time, executable/build identity, requested producer role, and current authority state;
3. the supervisor returns a memory-only producer capability over that pipe connection;
4. the capability contains `producer_capability_id`, `supervisor_generation_id`, permitted producer role, permitted fact types, permitted symbol/contracts, `listener_epoch_id`, permitted `bridge_generation_id` where applicable, issue time, expiry time, and revocation sequence;
5. the supervisor generates a 256-bit per-capability HMAC key and returns it only over the authenticated pipe; it SHALL NOT place the key in a command line, environment dump, shared file, projection, or log; and
6. a capability expires 30 seconds after issue and SHALL be renewed no later than 15 seconds after issue over the same mutually verified connection; renewal SHALL repeat PID/start/build, scope, supervisor generation, listener epoch, bridge generation, and revocation validation; and
7. pipe disconnect, process exit, fence, identity change, renewal failure, or supervisor-generation change revokes the capability immediately and requires registration again.

The supervisor SHALL reject an event if Windows identity, PID/start identity, executable/build identity, capability scope, supervisor generation, listener epoch, bridge generation, HMAC, sequence, or fact type does not match.

#### 3.3.3 Frame and canonical serialization

Each pipe message SHALL be:

```text
4-byte unsigned little-endian payload length
UTF-8 canonical JSON payload
```

Canonical JSON SHALL use lexicographically sorted keys, no insignificant whitespace, UTF-8 without BOM, JSON escaping for control characters, RFC 3339 UTC timestamps with `Z`, finite JSON numbers only, and integer identity/sequence fields. Maximum frame length SHALL be 65,536 bytes. Zero length, oversized length, malformed UTF-8/JSON, duplicate keys, nonfinite numbers, or unsupported schema SHALL be rejected before health evaluation.

Every event frame SHALL contain:

- `message_type = HEALTH_EVENT`;
- `schema_version = 1`;
- `policy_version = health-control-v1`;
- `health_event_id` as a UUID;
- `producer_capability_id`;
- `producer_instance_id`;
- `producer_sequence` as a strictly increasing integer;
- `producer_pid` and process creation time;
- `supervisor_generation_id`;
- `listener_epoch_id`;
- `bridge_generation_id` or explicit `null` when the fact is listener-scoped;
- logical symbol and resolved contract or explicit shared scope;
- closed `fact_type`;
- `source_observed_at_utc`;
- producer monotonic observation tick;
- fact-specific payload;
- `payload_sha256`; and
- `hmac_sha256` over the length-independent canonical payload with `hmac_sha256` omitted.

`payload_sha256` SHALL be SHA-256 over the same canonical payload with both integrity fields omitted. HMAC verification SHALL use constant-time comparison. A duplicate `health_event_id` with identical bytes is idempotent. A duplicate ID or producer sequence with different bytes is `AUTHENTICATED_EVENT_CONFLICT`, is rejected, and places that producer capability in revoked state.

#### 3.3.4 Closed direct-evidence fact types

Only these fact types constitute direct runtime evidence:

| Producer | Fact type | Meaning |
|---|---|---|
| Listener Supervisor | `LISTENER_PROCESS_STARTED`, `LISTENER_PROCESS_EXITED`, `LISTENER_LEASE_GRANTED`, `LISTENER_LEASE_EXPIRED`, `LISTENER_EPOCH_FENCED`, `SHUTDOWN_INTENT`, `OPERATOR_COMMAND_ACCEPTED`, `PROCESS_TERMINATION_EXECUTED` | OS process/lease/intent/execution facts owned by the supervisor |
| Rithmic listener | `LISTENER_LEASE_HEARTBEAT`, `RAPI_ALERT_OBSERVED`, `SUBSCRIPTION_REQUEST_RESULT`, `SUBSCRIPTION_PROOF_OBSERVED`, `SUBSCRIPTION_FAILED`, `TICK_ACCEPTED_BY_LISTENER` | raw current-epoch provider/feed facts; `SUBSCRIPTION_PROOF_OBSERVED` carries exact provider/request/contract evidence and the producer SHALL NOT self-declare the authoritative `SUBSCRIPTION_VERIFIED` result or a terminal cause |
| Bridge Controller | `BRIDGE_PROCESS_STARTED`, `BRIDGE_PROCESS_HEARTBEAT`, `BRIDGE_PROCESS_EXITED`, `BRIDGE_GENERATION_READY`, `BRIDGE_GENERATION_FENCED`, `BRIDGE_SHUTDOWN_REQUESTED`, `SUBSCRIPTION_RECOVERY_ATTEMPT`, `SUBSCRIPTION_RECOVERY_RESULT` | current bridge-generation process/intent/recovery acknowledgements only; `BRIDGE_GENERATION_READY` reports Controller execution readiness and SHALL NOT grant, adopt, or make the generation authoritative |
| Executor | `TICK_ACCEPTED_BY_EXECUTOR`, `TICK_REJECTED_BY_EXECUTOR`, `DOWNSTREAM_DELIVERY_COMMITTED` | downstream delivery/consumption facts |

Adding a fact type requires an approved ADR/specification amendment and schema/policy version change. Free-form event names SHALL NOT influence liveness or lifecycle decisions.

`SUBSCRIPTION_VERIFIED` is the sole positive authoritative subscription result, not a producer event. The Rithmic listener is the authenticated evidence producer of `SUBSCRIPTION_PROOF_OBSERVED`; Health Event Ingress authenticates and sequences it as the SQL fact type `SUBSCRIPTION_PROOF`; the Listener Supervisor State Evaluator consumes the accepted proof with current supervisor/epoch/generation/contract/request identity and is the sole result authority; and the Health Durable Writer writes the resulting `SUBSCRIPTION_VERIFIED` disposition **only** in `subscription_verifications`. The committed row SHALL carry every source event ID/sequence, exact symbol/contract, request identity, provider acknowledgement, supervisor generation, listener epoch, bridge generation, evaluator decision/version, transaction identity, freshness bound, and integrity identity. The authenticated source-event object SHALL carry exact `contract_id`, `contract_session_ref_id`, `request_identity`, `provider_acknowledgement_identity`, `freshness_observation_identity`, and `proof_evidence_identity` text members equal to that committed row; missing or mismatched membership is `SUBSCRIPTION_PROOF_INVALID`. If that decision changes a health dimension, the State Evaluator must separately authorize `TX-HEALTH-DIMENSION-UPDATE`, which writes its own `health_transitions`, `health_current`, and `health_aggregate` records. A raw producer claim, `health_events` row, request return, projection, cache, `ACTIVE`, process existence, or evaluator memory without the durable `subscription_verifications` row SHALL NOT satisfy subscription readiness.

The executable composite keys bind each subscription to `(contract_session_ref_id,symbol,contract_id)` and `(bridge_generation_id,listener_epoch_id,supervisor_generation_id)`. Positive insertion additionally requires an active exact producer/sequence, current epoch/generation, authenticated proof event, nonmissing request/provider/evaluator/freshness/proof identities, integrity hash, and `TX-SUBSCRIPTION-VERIFY`. Thus NQ cannot point to a YM session, an old epoch/generation cannot become positive, and the partial unique index permits only one positive current row per symbol/session/generation.

The same producer/evaluator/writer separation is mandatory for major facts:

| Authoritative result | Authenticated evidence producer | Evaluator / transition authority | Sole durable writer | Projection/read consumer rule |
|---|---|---|---|---|
| listener proof of life | Supervisor OS Authority Adapter for owned process/lease plus Rithmic listener for lease heartbeat/publication | Listener Supervisor State Evaluator | Listener Supervisor Epoch/Incident Writer for epoch/lifecycle; Health Durable Writer for committed health facts | snapshots display only; no projection can refresh proof |
| `SUBSCRIPTION_VERIFIED` | Rithmic listener `SUBSCRIPTION_PROOF_OBSERVED` | Listener Supervisor State Evaluator | Health Durable Writer | consumers require committed current identity; projection is nonauthoritative |
| bridge generation acknowledgement/grant | Bridge Controller produces acknowledgement/execution result | Listener Supervisor State Evaluator alone grants/adopts/fences generation | **Bridge Generation Writer alone writes `bridge_generations`** | acknowledgement is not a grant; Health Durable Writer and Command Center cannot grant/write it |
| five-field termination observation | six authenticated producer streams provide exact intent/provider/process facts through one cutoff | Listener Supervisor State Evaluator detects conflict and classifies each independent field | Health Durable Writer writes raw evidence, exact set/producer/contributor membership, and derived result | logs/projections cannot classify, complete, or confirm |
| market-data expectation | Market Session Calendar Policy Owner produces approved artifact; Supervisor subscription-intent/lifecycle/clock adapters produce current inputs | ADR-015 Market Data Expectation Evaluator | Listener Incident Writer writes `market_data_expectations` | consumers block/display only; silence/projection cannot evaluate |
| ATR continuity/readiness | listener/tick journal and finalized-bar owner produce exact bar/history evidence | canonical bars/ATR authority evaluates ADR-015 disposition | canonical bars/ATR writer, never Health Durable Writer | health/Command Center consume identity only and cannot reset/rebuild |
| `COMMAND_CENTER_ALIGNED` | canonical owners publish immutable snapshots; Command Center produces display snapshot | startup observational parity evaluator only | startup evidence writer records parity result, not domain state | never health/lifecycle/session/recovery authority |

#### 3.3.5 Freshness and acceptance

The supervisor SHALL stamp `ingress_received_at_utc` and a supervisor monotonic tick when a complete frame arrives. An event becomes accepted direct evidence only after authentication, identity, order, schema, integrity, and freshness validation.

- A liveness-positive or terminal callback event SHALL arrive no more than 5 seconds after `source_observed_at_utc` and SHALL NOT be more than 2 seconds in the future relative to the supervisor clock.
- Listener lease and bridge process heartbeat cadence/state SHALL use ADR-015 policy fields `heartbeat_period_seconds`, `lease_suspect_seconds`, and `lease_unknown_seconds`. Absence alone SHALL NOT establish bridge death.
- Tick freshness SHALL be evaluated per symbol/contract using ADR-015 `symbol_tick_stale_seconds` and `symbol_data_unavailable_seconds`. Tick absence alone SHALL NOT establish bridge death or listener death.
- A frame outside the freshness bounds SHALL be durably classified as historical diagnostic evidence only if storage is available. It SHALL NOT refresh liveness, cancel a fence after its linearization point, or satisfy a terminal predicate.

Supervisor wall-clock rollback greater than 2 seconds, an unavailable/non-increasing monotonic clock, UTC/monotonic correlation error greater than 2 seconds, or conflicting clock-source identity SHALL enter `HEALTH_TIME_AUTHORITY_DEGRADED`, block new entries/new fences, and require recovery before liveness can be classified READY.

#### 3.3.6 `HEALTH_TIME_AUTHORITY_DEGRADED`

The Listener Supervisor State Evaluator is the sole transition authority for `HEALTH_TIME_AUTHORITY_DEGRADED`; the Health Durable Writer is its sole writer. Entry requires one of the exact clock failures in section 3.3.5. When the store is available, the writer SHALL commit/read back a health-state incident containing supervisor generation, listener epoch/bridge generation when granted, clock-source identities, last trusted UTC/monotonic correlation, observed samples, exact failing predicate, detection sequence/time when trustworthy, affected readiness scopes, and integrity identity. If that record cannot commit, `HEALTH_PERSISTENCE_DEGRADED` applies concurrently and the time state SHALL NOT be represented as durable.

Permitted actions while active are limited to retaining direct authenticated events as ordered observations, preserving existing execution/trade/protective-order truth under its existing owners, exposing the degradation through immutable diagnostics, and completing idempotently an execution whose fence/execution identity was durably committed and readback-verified before degradation.

Prohibited actions while active are classifying freshness or `DATA_EXPECTED`; creating, canceling, or fencing a new bridge/listener incident from time-dependent evidence; allocating a new epoch/generation; authorizing a new entry; using projection/file time as substitute authority; or converting clock ambiguity into bridge/listener death. The Supervisor SHALL NOT perform any prohibited action.

Recovery requires a Supervisor-owned clock validation transaction containing five consecutive samples over at least five seconds in which the monotonic source is available and strictly increasing, UTC is nondecreasing, the UTC and monotonic deltas differ by no more than 250 milliseconds per interval, and the source identities remain unchanged. The Health Durable Writer SHALL commit/read back `HEALTH_TIME_AUTHORITY_RECOVERED` with the validation samples and a new trusted correlation before the State Evaluator may clear the degraded state and reevaluate health from fresh current-generation evidence. Prior freshness SHALL NOT be carried across recovery.

At startup, any entry condition above SHALL make the health-store disposition nonready, prohibit producer/listener exposure, and terminate startup `FAILED` with `HEALTH_TIME_AUTHORITY_DEGRADED`. At runtime, one failed validation transaction leaves the state degraded; a second consecutive failed validation transaction escalates the incident to governed operator recovery while retaining the same degraded state and prohibiting automatic lifecycle action. Restart does not clear the incident: a new Supervisor generation SHALL complete the same validation and durable recovery record before readiness. The state blocks every readiness gate that depends on freshness, expectation, connection, subscription, tick, bar, ATR, bridge, or listener health.

### 3.4 Epoch and generation identity

Every accepted event SHALL match the current `supervisor_generation_id`.

Listener-scoped events SHALL match the one current unfenced `listener_epoch_id`. Bridge-scoped events SHALL also match the one current unfenced `bridge_generation_id` within that listener epoch. Executor events SHALL reference the listener tick identity and epoch/generation accepted by its intake journal.

A Bridge Generation change SHALL NOT allocate or imply a Listener Authority Epoch change. A Listener Authority Epoch fence SHALL revoke every capability and bridge generation scoped to the old epoch. An old supervisor generation, listener epoch, bridge generation, producer instance, or capability SHALL NOT refresh, cancel, fence, or control current authority.

### 3.5 Health authority hierarchy and transfer

Authority SHALL rank as follows:

1. **Accepted direct runtime evidence** - immediate current liveness, recovery, and entry-blocking authority in Listener Supervisor memory.
2. **Verified local durable health commit** - crash-recovery, incident/fence, cursor, and control-history authority.
3. **Projection layer** - asynchronous shared JSON and read-only status/Command Center views derived from a verified durable commit.
4. **Historical diagnostics** - incident logs, rejected frames, prior epochs/generations, and archived projections.

Authority transfers only through these exact transitions:

```text
PRODUCER_OBSERVATION
  -> AUTHENTICATED_FRAME_RECEIVED
  -> DIRECT_EVIDENCE_ACCEPTED
  -> DURABLE_COMMIT_PENDING
  -> DURABLE_COMMIT_VERIFIED
  -> PROJECTION_PENDING
  -> PROJECTION_PUBLISHED
```

`DIRECT_EVIDENCE_ACCEPTED` immediately MAY block entries, mark degradation, or cancel an unfenced pending recycle/restart. It SHALL NOT execute a process action. A bridge/listener lifecycle action requires a durable readback-verified fence.

`DURABLE_COMMIT_VERIFIED` transfers crash-recovery/control-history authority to the local store. It does not demote fresher accepted direct evidence. Fresh direct evidence that clears a predicate SHALL cancel an unfenced durable pending decision.

Projection publication never transfers control authority. No lower-ranked source SHALL override or manufacture a higher-ranked fact. If direct evidence and the durable store disagree, the supervisor SHALL expose `HEALTH_AUTHORITY_DIVERGED`, block entries/new fences, preserve both, and reconcile only by committing the accepted direct evidence or governed store recovery. It SHALL NOT choose the newest file.

### 3.6 Durable health control store

#### 3.6.1 Location and ownership

The proposed runtime-authority control store SHALL be the one physical SQLite database selected as Pattern A and defined jointly with ADR-015, explanatory contract `docs/architecture/runtime_authority_store_schema_DRAFT.md`, and executable DDL `docs/architecture/runtime_authority_store_schema_v2_DRAFT.sql` at the absolute path resolved once at startup from:

```text
%LOCALAPPDATA%\RandleRuntimeData\control\runtime_authority_v2.sqlite3
```

The resolved path SHALL be recorded in startup evidence and SHALL NOT be within the configured shared/synchronized projection root. Supervisor/listener and bridge/health identities live in ownership-separated tables in this same database so every declared foreign key is physically enforceable. A shared file does not create shared domain authority.

The in-process `Runtime Authority Store Transaction Coordinator` SHALL own the only read-write connection and mechanically serialize typed transaction plans. It owns no state transition, classification, identity, or recovery decision. The exact writer IDs, table/operation routes, activation/retirement, partial unique exclusivity, decision inputs, idempotency, optimistic-version rules, evidence, and prohibitions are Runtime Authority Store Schema sections 7, 9, and 11. The coordinator SHALL reject cross-owner or unregistered plans and SHALL NOT reinterpret their content.

No producer, projection publisher, launcher, endpoint, or downstream consumer SHALL open a write connection. The Listener Supervisor State Evaluator SHALL consume immutable committed snapshots supplied by the Health Durable Writer and authorize health/bridge transitions, not issue independent database writes. Diagnostic readers SHALL use the read-only snapshot transport in section 3.12 and SHALL NOT open the control database. No second database, copied identity row, local witness, cache, or projection may become an authority for a supervisor generation, listener epoch, bridge generation, incident, or health state.

#### 3.6.2 SQLite configuration and closed schema

Before accepting ingress, the writer SHALL set and verify:

```text
journal_mode = WAL
synchronous = FULL
foreign_keys = ON
trusted_schema = OFF
recursive_triggers = ON
busy_timeout = 5000 milliseconds
application_id = 0x52484C54
user_version = 2
```

The complete database-level contract is Runtime Authority Store Schema sections 2 through 14 and the executable SQL. It is exactly schema `RANDLE_RUNTIME_AUTHORITY_SCHEMA_V2`, `user_version=2`, initial bootstrap `RASTORE-BOOTSTRAP-V2`, 47 STRICT tables, 670 columns, 152 foreign-key declarations/203 child-column mappings, one SHA-256 preflight view, 70 active writer routes, 14 partial unique indexes, and 27 constraint triggers. There is no approved version-1 predecessor or migration. Every type, nullability, key, check, FK parent/action/deferrability, writer route, activation/retirement, hash rule, and reconstruction rule is exact; prose such as “appropriate to scope” cannot supply a constraint.

ADR-016 bridge and health authority SHALL use only these exact records:

| Domain fact | Sole durable record |
|---|---|
| Bridge Generation grant/ancestry | `bridge_generations` |
| current bridge state/version/incident | `bridge_current` |
| bridge transition history | `bridge_transitions` |
| bridge incident/version/predicate/count | `bridge_incidents` |
| recycle attempt | `bridge_recycle_attempts` |
| bridge terminal outcome | `bridge_outcomes` |
| authenticated producer registration/event | `producer_registrations`, `health_events` |
| independent current health dimension | `health_current` |
| health transition history | `health_transitions` |
| deterministic aggregate health | `health_aggregate` |
| committed subscription decision | `subscription_verifications` |
| raw termination evidence | `termination_evidence` |
| exact termination evidence-set header and producer completeness windows | `termination_evidence_sets`, `termination_evidence_set_producers` |
| five-field termination classification | `termination_results` |
| exact evidence contribution for each termination dimension | `termination_result_evidence` |
| market-data expectation | `market_data_expectations` |

The closed bridge transaction catalog is `TX-BRG-GRANT`, `TX-BRG-INITIALIZE`, `TX-BRG-RECYCLE-PENDING`, `TX-BRG-CANCEL`, `TX-BRG-FENCE`, `TX-BRG-EXECUTE`, `TX-BRG-REHYDRATE`, `TX-BRG-READY`, `TX-BRG-FAIL`, `TX-BRG-EXHAUSTED`, `TX-BRG-PLANNED-SHUTDOWN`, and `TX-BRG-EPOCH-TRANSITION`. The closed health/evidence/governance catalog is `TX-PRODUCER-REGISTER`, `TX-PRODUCER-RETIRE`, `TX-CONTRACT-SESSION-IMPORT`, `TX-CONTRACT-SESSION-RETIRE`, `TX-HEALTH-EVENT`, `TX-HEALTH-DIMENSION-UPDATE`, `TX-SUBSCRIPTION-VERIFY`, `TX-TERMINATION-EVIDENCE-INGEST`, `TX-TERMINATION-CLASSIFY`, `TX-EXPECTATION-EVALUATE`, `TX-POLICY-VALIDATE`, and `TX-PROJECTION-CURSOR`. `TX-TERMINATION-EVIDENCE-INGEST` is the narrowed R3 successor name for the former generic evidence operation, so the closed package remains 55 operation IDs/52 database-commit types. Runtime Authority Store Schema sections 9, 11, and 14 define their exact rows, writer sets, preconditions, idempotency, expected versions, results, crash, retry, and reconstruction. `TX-BRG-GRANT` always uses Bridge Generation Writer for `bridge_generations`; `TX-BRG-INITIALIZE` uses Health Durable Writer for initial bridge current/history only; `TX-SUBSCRIPTION-VERIFY` writes the result only to `subscription_verifications`; `TX-PROJECTION-CURSOR` uses Projection Writer. No other bridge/health cross-writer transaction is legal.

No cross-database SQLite foreign key is permitted. `active_contract_sessions` is a hash-validated external ADR-014 reference and SHALL NOT become a second session authority. Crash or partial write before COMMIT leaves no authority change; COMMIT/readback establishes the complete change. Any foreign-key, writer-routing, duplicate-current-row, partial-state, transaction-cursor, or parent-chain failure enters `HEALTH_STORE_CORRUPT` or ADR-015 `SUPERVISOR_STORE_FAILED` according to the affected domain and blocks startup/new fences.

#### 3.6.3 Closed operation envelopes

The universal Phase 3B envelope is removed. Only a healthy-store mutation uses `BEGIN IMMEDIATE`, domain rows, transaction/idempotency records, metadata cursor, `COMMIT`, and independent readback. `TX-STORE-VALIDATE` is genuinely read-only and writes none of those rows. `TX-STORE-QUARANTINE` uses the external recovery-evidence envelope and never opens the corrupt database read-write. Restore, reinitialization, and v2 bootstrap first append their external `*_PREPARED` row, construct and validate a new candidate whose store-recovery row carries that prepared sequence/hash, perform atomic file replacement/readback, and only then append `*_COMPLETED`. Version-conflict rejection writes one immutable rejection row only inside an already verified healthy store; otherwise it returns without changing authority. A future migration requires a separately approved predecessor-bound file-level envelope. Runtime Authority Store Schema sections 9 and 14.7 are the exact contract.

For a healthy-store health or bridge mutation, the owning writer retains the exact item; the Coordinator verifies schema/registry, active table/operation ownership, authority decision, current identities, parents, expected versions, producer sequence, idempotency key/request hash, and evidence hash; performs only the catalogued writes; commits under `synchronous=FULL`; opens a separate read-only verification connection; and returns a durable acknowledgement only after exact readback. Precommit failure rolls back. Postcommit/readback ambiguity is reconstructed by the same transaction/idempotency identity before retry; it never creates a second action.

#### 3.6.4 Locking and contention

The Supervisor process single-instance lease prevents two Runtime Authority Store Transaction Coordinators. The in-process coordinator queue serializes healthy-store mutations, while SQL index `uq_writer_registry_active_scope` prevents two active writer identities from owning one table/operation. `BEGIN IMMEDIATE` establishes the write lock only for that envelope. `SQLITE_BUSY` after 5 seconds is failure reason `HEALTH_STORE_CONTENTION`, not a health state and not success. The coordinator SHALL roll back; the owning writer SHALL retain pending, and only the State Evaluator may authorize persistence degradation.

No lock failure, timeout, access denial, or sharing violation SHALL cause writer failover to shared JSON, a second database, a new writer process, or an in-memory cursor represented as durable.

#### 3.6.5 Startup verification and corruption detection

Before pipe ingress opens, startup SHALL acquire the owner recovery lock, open no public/control transport, open the store read-only, and:

1. resolve and record the database, `-wal`, and `-shm` identities without following an unexpected reparse point;
2. open the configured database and let SQLite perform WAL recovery;
3. require SQLite `>=3.43.1`, `application_id=0x52484C54`, `user_version=2`, exact schema identity/hash, bootstrap identity, writer-registry version/hash, store UUID, created time, 47 tables, 670 columns, 152 FK declarations/203 mappings, the SHA-256 preflight view, 14 partial unique indexes, and 27 triggers;
4. run `PRAGMA quick_check` and require the single result `ok`, then run `PRAGMA foreign_key_check` and require zero rows;
5. verify the contiguous transaction cursor/idempotency results, 70 active exclusive writer routes and succession ordering, unique event/producer sequences, every stored canonical-event checksum, supervisor-generation sequence, listener-epoch/bridge-generation ancestry, and incident/fence/execution state-machine legality;
6. verify listener current/transition/outcome relationships, exact acknowledgements, Bridge Generation Writer provenance, subscription result separation, five health rows/aggregate, and no unresolved store/recovery incident; and
7. verify the external recovery-evidence hash chain and recover only the highest complete committed cursor and immutable snapshot.

SQLite I/O/corruption result, failed WAL recovery, failed pragma, mismatched application/schema/store identity, unsupported version, checksum/sequence/foreign-key/ancestry/state-machine failure, missing required sidecar during a noncheckpointed commit, or ambiguous current incident SHALL classify the store as `HEALTH_STORE_CORRUPT`. SQLite-uncommitted WAL transactions MAY be ignored only when SQLite's recovery and every subsequent verification succeed. File existence, parseability, recent modification time, or a partly readable table SHALL NOT establish integrity.

#### 3.6.6 Quarantine and recovery authority

On `HEALTH_STORE_CORRUPT` or ADR-015 `SUPERVISOR_STORE_FAILED` caused by physical database integrity, the Supervisor SHALL enter terminal recovery state before producer registration or listener/bridge start. Under the exclusive recovery lock it closes every database handle; `TX-STORE-QUARANTINE` never opens or writes the corrupt database. The Recovery Controller moves and verifies the exact database/`-wal`/`-shm` set under `%LOCALAPPDATA%\RandleRuntimeData\control\quarantine\runtime_authority\<recovery_incident_id>\`. The `Runtime Authority Recovery Evidence Writer` records prepared/completed/failed facts only in `%LOCALAPPDATA%\RandleRuntimeData\control\evidence\runtime_authority_recovery_evidence_v1.jsonl` using Store Schema section 14.6's `RANDLE-RECOVERY-JCS-1`, size bounds, and exact Windows write-through replacement contract. It owns no lifecycle, session, bridge, health, readiness, deployment, or trading decision. If move/flush/hash/evidence verification is incomplete, source and partial evidence remain preserved and startup remains failed.

Automatic restoration is prohibited. A restore requires an authenticated operator recovery request by the Runtime Operations Owner, Architecture Governance approval of the exact source/disposition, and Deployment Authorization approval of the staged database hash. Valid restoration sources are limited to:

1. a local nonsynchronized owner-produced SQLite backup whose manifest names the same store UUID, source schema/policy version, contiguous cursor, supervisor generation/listener epoch/bridge ancestry, backup creation commit, SHA-256, and successful integrity verification; or
2. an offline governance-controlled byte-for-byte backup with the same evidence and chain of custody.

Shared/OneDrive projection JSON, Command Center/status output, logs, a copied snapshot, process memory, or operator-edited rows SHALL NOT restore canonical control authority. If no qualifying source exists, startup SHALL remain `CONTROL_STORE_RECOVERY_REQUIRED` and fail closed until a separately governed reinitialization plan is approved. A new empty store is reinitialization, not restoration; it SHALL allocate a new store UUID, fence every prior supervisor/listener/bridge identity, acknowledge loss of unrecoverable history, reconcile exact OS/broker/runtime process state, and obtain the three approvals above before any listener start.

A restore SHALL be built at a new staging path, opened only by the recovery tool, and pass every check in section 3.6.5. It SHALL preserve store UUID, durable cursor, listener-epoch and bridge-generation ancestry, and incident/fence/execution identities from the source. Startup SHALL allocate a new `supervisor_generation_id`; it SHALL NOT copy freshness into the new generation or adopt a prior listener/bridge solely from restored rows. Any cursor interval after the backup that could contain an unobserved fence/execution makes that backup ineligible until exact process/incident reconciliation proves no ambiguous action.

#### 3.6.7 Versioned migration and rollback

Schema version other than 2 SHALL be rejected. Repository search established no exact approved version-1 artifact or hash, so `RASTORE-MIG-002` is withdrawn, no startup/runtime path migrates or imports legacy authority, and Phase 3C1 is initial bootstrap `RASTORE-BOOTSTRAP-V2`. Every legacy/unidentified store is quarantined and supplies no positive authority. A future migration requires a unique ID, exact predecessor artifact/commit/SHA-256, approved `from_version`/`to_version`, tool/build hash, deterministic transform and preservation rules, expected output schema/hash, candidate validation, rollback boundary, test evidence, and the same three approvals as restoration.

Migration SHALL operate on a staged copy, preserve stable store/epoch/generation/incident identities unless the approved plan explicitly fences them, run every source and target integrity check, flush and hash the result, and write an append-only recovery audit record before activation. The prior database and sidecars SHALL remain quarantined. Rollback to the prior store is legal only before the migrated store becomes current and before any new committed cursor/fence/execution. After first new commit, rollback to an older cursor is prohibited; recovery SHALL move forward under a new approved incident.

Every bootstrap, quarantine, restore, reinitialization, activation, failed validation, and rollback SHALL use the `Runtime Authority Recovery Evidence Writer` contract and exact artifact path above. Its record contains recovery incident, startup attempt, authorization/actor identities, reason, all ordered input/output hashes and versions, preserved epoch/generation/cursor disposition, validation result, activation time, prior record hash, and record hash without secrets. A missing, unwritable, invalid, or capacity-exhausted evidence chain fails recovery before activation. Startup consumes the chain and blocks on prepared-without-completed or unresolved quarantine/recovery state. Migration is not a current operation; it exists only under a future separately governed predecessor-bound specification.

### 3.7 Pending retention, acknowledgement, retry, and backpressure

Ingress is at-least-once. Each producer SHALL retain every unacknowledged control-relevant event in a bounded ordered in-memory outbox and retry the same event ID/sequence after reconnect or negative/no acknowledgement. Producer termination can lose an unacknowledged observation; the durable store SHALL never claim it committed. On producer restart, a new producer instance/sequence starts and no lost event is inferred.

High-frequency observational events MAY coalesce only before Health Event Ingress accepts them and only for consecutive events of the same producer/scope/fact type. The retained item SHALL contain the newest value, first/last observation times, and coalesced count. Terminal, recovery, incident, fence, generation, authentication, and error events SHALL NOT coalesce.

After ingress acceptance, Health Durable Writer SHALL retain the exact event until durable acknowledgement. Retry SHALL use exponential delays of 100 ms, 250 ms, 500 ms, 1 s, 2 s, then 5 s maximum, with up to 20 percent jitter. Retry SHALL continue while the supervisor runs; it SHALL NOT spin or log more than one repeated identical incident per 30 seconds.

The writer queue SHALL hold at most 10,000 events or 64 MiB, whichever occurs first. At 80 percent capacity the supervisor SHALL enter `HEALTH_PERSISTENCE_DEGRADED`, reject new entry authorization, and apply producer backpressure. At capacity, it SHALL close/reject new ingress after returning `BACKPRESSURE_NO_ACK`; it SHALL NOT drop an accepted control-relevant event, advance a cursor, or create a fence.

### 3.8 Projection publication

The shared health JSON SHALL be an asynchronous projection generated only from an immutable verified committed snapshot. It SHALL contain the source health commit/cursor, supervisor generation, listener epoch, bridge generation, generation time, schema/policy version, and projection lag/degraded status.

For each projection attempt, Projection Publisher SHALL:

1. serialize canonical UTF-8 JSON to a unique temporary file in the projection target directory;
2. flush the language buffer;
3. call Windows `FlushFileBuffers` on the temporary file handle;
4. close the handle;
5. use `ReplaceFileW` when the target exists or `MoveFileExW` with `MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH` when it does not;
6. reopen and verify source cursor, identities, schema, and checksum; and
7. advance the projection cursor only after verification.

Failure at any step SHALL retain the projection item/cursor pending and record exact stage, Windows error code, attempt, and time without naming a conflicting handle owner absent direct evidence.

Shared/OneDrive health JSON SHALL NOT initiate, influence, reinforce, confirm, participate in, or contribute to any process-control, lifecycle, death, recovery, fencing, cancellation, authorization, or readiness decision. It SHALL NOT be read, joined, weighted, compared, correlated, or used as corroboration by a control predicate, alone or in combination. Projection publication is one-way from committed local health to observational display/interchange. No control module SHALL import the projection path or a value derived from it as input.

### 3.9 Closed bridge, health, evidence, reason, and termination domains

The domains below are disjoint. A bridge state SHALL NOT be used as a health state; an evidence fact or failure reason SHALL NOT be used as a state; and a termination-field value SHALL NOT substitute for a BDP predicate, health state, or lifecycle transition.

| Domain | Closed contents |
|---|---|
| Bridge lifecycle/current states | `BRIDGE_STARTUP_UNPROVEN`, `BRIDGE_STARTING`, `BRIDGE_READY`, `BRIDGE_SUSPECT`, `BRIDGE_FENCED`, `RECYCLE_EXECUTING`, `BRIDGE_REHYDRATING`, `PLANNED_SHUTDOWN`, `LISTENER_EPOCH_TRANSITION` |
| Bridge incident nonterminal state | `RECYCLE_PENDING` |
| Bridge incident terminal outcome | `RECYCLE_CANCELED`, `BRIDGE_FAILED`, `FAILED_RECOVERY_EXHAUSTED` |
| Authoritative health-control state | every positive/degraded state in section 3.9.1 |
| Accepted direct-evidence fact | section 3.3.4 fact types plus derived committed `SUBSCRIPTION_VERIFIED` |
| Failure/recovery reason or evidence result | `HEALTH_STORE_CONTENTION`, `AUTHENTICATED_EVENT_CONFLICT`, `BACKPRESSURE_NO_ACK`, `CONTROL_STORE_RECOVERY_REQUIRED`, `HEALTH_TIME_AUTHORITY_RECOVERED` |
| Bridge-death predicate | `BDP-01`, `BDP-02`, `BDP-03`, `BDP-04` |
| Termination field/value | only the five fields and closed values in section 3.9.2 |

The bridge lifecycle/incident state machine SHALL use only:

```text
BRIDGE_STARTUP_UNPROVEN
  -> BRIDGE_STARTING
  -> BRIDGE_READY
  -> BRIDGE_SUSPECT
  -> RECYCLE_PENDING
  -> RECYCLE_CANCELED | FAILED_RECOVERY_EXHAUSTED | BRIDGE_FENCED
  -> RECYCLE_EXECUTING
  -> BRIDGE_REHYDRATING
  -> BRIDGE_READY | BRIDGE_FAILED | FAILED_RECOVERY_EXHAUSTED

```

The State Evaluator is the sole transition authority for every bridge lifecycle/incident state below; Health Durable Writer is the sole writer of `bridge_current`, `bridge_transitions`, `bridge_incidents`, `bridge_recycle_attempts`, and `bridge_outcomes`. Bridge Generation Writer alone writes `bridge_generations`. Bridge Controller produces authenticated execution facts only and never selects or writes a state/generation.

| State/outcome | Exact entry evidence | Durable record and permitted exit | Restart behavior | Readiness effect |
|---|---|---|---|---|
| `BRIDGE_STARTUP_UNPROVEN` | No complete current Supervisor grant/Controller acknowledgement/connection/login/subscription proof exists | Current startup attempt/identity evidence; exits only to `BRIDGE_STARTING` by governed startup or `PLANNED_SHUTDOWN` by prior intent | Restore unproven; no inferred start/recycle | Nonready |
| `BRIDGE_STARTING` | Current Supervisor grant and authenticated start execution are committed, but readiness evidence is incomplete | Grant/execution/process identities; exits to `BRIDGE_READY`, `BRIDGE_SUSPECT`, or `PLANNED_SHUTDOWN` by exact evidence | Adopt exact process/execution or remain ambiguous/nonready; never duplicate-start | Nonready |
| `BRIDGE_READY` | Current generation, connection/login UP, exact required `SUBSCRIPTION_VERIFIED`, and required rehydration acknowledgements all commit | Current generation/health/rehydration record; exits only to `BRIDGE_SUSPECT`, `RECYCLE_PENDING`, `PLANNED_SHUTDOWN`, or `LISTENER_EPOCH_TRANSITION` | Reverify every proof; process existence alone cannot restore READY | Ready only with all other gates |
| `BRIDGE_SUSPECT` | A named current-generation health condition becomes unproven/degraded without satisfying a closed BDP | Exact suspect predicate/evidence; exits only to `BRIDGE_READY`, `RECYCLE_PENDING`, `PLANNED_SHUTDOWN`, or `LISTENER_EPOCH_TRANSITION` | Restore suspect and reevaluate; no implicit incident | Nonready for affected scope |
| `RECYCLE_PENDING` | Exactly one BDP-01..04 is proven and the incident compare-and-swap commits before fence | Incident/predicate/version/evidence; exits only to `RECYCLE_CANCELED`, `FAILED_RECOVERY_EXHAUSTED`, or `BRIDGE_FENCED` | Restore pending; revalidate/cancel/fail-exhausted/fence under the same incident, never act from polling | Nonready |
| `RECYCLE_CANCELED` | Exact conditions in this section's cancellation definition | Terminal incident record plus current bridge `BRIDGE_READY`/`BRIDGE_SUSPECT` result; no incident exit | Restore terminal no-action outcome | Determined only by the separate current bridge result |
| `BRIDGE_FENCED` | Pre-fence revalidation, rate eligibility, and `BEGIN IMMEDIATE` fence COMMIT/readback succeed | Fence/execution identity; exits only to `RECYCLE_EXECUTING`; a concurrent health/store failure leaves it fenced and blocks action until the same execution identity is resolved | Resume/adopt same execution identity; never allocate another | Nonready; old generation ineligible |
| `RECYCLE_EXECUTING` | Authenticated exact fenced command is accepted for the single execution identity | Controller acknowledgement/process result; exits to `BRIDGE_REHYDRATING`, `BRIDGE_FAILED`, or last-attempt `FAILED_RECOVERY_EXHAUSTED` | Adopt/resolve exact execution; no second effective child | Nonready |
| `BRIDGE_REHYDRATING` | Supervisor adopts/grants the replacement generation after exact execution | Grant, Controller acknowledgement, connection/login/subscription and domain rehydration records; exits to `BRIDGE_READY`, `BRIDGE_FAILED`, or last-attempt `FAILED_RECOVERY_EXHAUSTED` | Resume same recovery identity and remain fenced from publication until complete | Nonready |
| `BRIDGE_FAILED` | One permitted nonfinal execution ends without a ready generation while governed capacity remains | Terminal ordinary-failure incident record; later recovery requires a new BDP/incident and all cooldown/rate/fence rules | Restore terminal; no implicit retry | Nonready |
| `FAILED_RECOVERY_EXHAUSTED` | Exactly one of the two cross-ADR exhaustion predicates is proven | Terminal exhaustion record defined below; no bridge-only exit | Restore terminal; no implicit retry; SFF-03 is a separate listener incident | Both symbols blocked/nonready |
| `PLANNED_SHUTDOWN` | Authenticated durable shutdown intent precedes effect | Intent/action/result record; exits only through a new governed startup identity | Restore stopped/planned evidence; no recovery predicate | Nonready |
| `LISTENER_EPOCH_TRANSITION` | ADR-015 current listener epoch is fenced/replaced | Old/new epoch, bridge disposition, and downstream recovery identities; exits only through a new epoch's governed startup/rehydration | Reject old generation and resume the ADR-015 recovery transaction | Nonready |

Every bridge lifecycle or bridge-incident transition not explicitly listed in this table is prohibited. A bridge terminal outcome has no exit; later recovery requires the new incident/identity rules stated in its row and SHALL NOT reopen or rewrite the terminal outcome.

`BRIDGE_SUSPECT`, stale ticks, transport degradation, persistence degradation, projection lag, and missing diagnostics block affected new entries but SHALL NOT by themselves authorize recycle.

`BRIDGE_STARTUP_UNPROVEN` is the initial bridge lifecycle state before a current Supervisor bridge-generation grant, authenticated Bridge Controller acknowledgement, connection/login proof, and exact required-contract `SUBSCRIPTION_VERIFIED` evidence have durably committed. The Listener Supervisor State Evaluator is its sole transition authority and the Health Durable Writer is its sole writer. It survives restart as nonready evidence and MAY exit only to `BRIDGE_STARTING` through a current governed startup transaction or to `PLANNED_SHUTDOWN` through a prior durable shutdown intent; missing startup proof SHALL NOT create a recycle incident.

`SUBSCRIPTION_VERIFIED` is the sole ready subscription lifecycle fact. `ACTIVE` is not a subscription lifecycle state and SHALL NOT be accepted as an alias, fallback, or readiness proof.

`BRIDGE_FAILED` is an ordinary terminal result of one permitted bridge execution that did not establish a ready generation but did not consume the governed maximum and did not reach the governed recovery timeout for the last permitted execution. It records exact execution failure and permits no immediate implicit retry; a later action requires a newly satisfied BDP, cooldown/rate eligibility, and a new incident.

`FAILED_RECOVERY_EXHAUSTED` has exactly the meaning defined in ADR-015 section 3.11.5: either the durable pre-execution rolling-window count already equals `max_bridge_recycles_per_window`, in which case no process action occurs, or the last permitted `BRIDGE_EXECUTION_STARTED` fails to establish one ready generation before `bridge_recovery_timeout_seconds`. The Listener Supervisor State Evaluator is the transition authority and the Health Durable Writer SHALL persist it under the existing bridge incident/version with the policy digest, monotonic window, counted execution IDs, recovery deadline where applicable, current epoch/generation, absence of ready recovery, immediate revalidation evidence, and integrity identity. It is terminal for bridge-only automatic recovery, survives every process/supervisor/launcher restart, authorizes no implicit bridge retry, and is eligible for ADR-015 `SFF-03` only after the separate listener debounce, revalidation, rate-limit, incident, and fence requirements succeed.

`RECYCLE_CANCELED` is the durable terminal no-action outcome of one bridge incident. Entry requires a current authenticated recovery event that clears the closed predicate, an unfenced `RECYCLE_PENDING` incident, matching supervisor generation/listener epoch/bridge generation, and a successful compare-and-swap on the current incident version. The Listener Supervisor State Evaluator is the sole transition authority and the Health Durable Writer is the sole writer. One serializable transaction SHALL record the incident/evidence identities, original predicate, accepted recovery commit, prior/new incident versions, cancellation time, proof that no bridge fence/execution/generation grant occurred, and a post-recovery bridge reevaluation of `BRIDGE_READY` only when every current connection/login/required `SUBSCRIPTION_VERIFIED` fact is proven or otherwise `BRIDGE_SUSPECT`. A canceled incident SHALL NOT fence, execute, reopen, allocate a generation, retry, or supply SFF-03 evidence. On restart it restores only as terminal evidence and causes no lifecycle action; a later failure requires a new predicate, incident, debounce, cooldown/rate decision, and fence.

#### 3.9.1 Complete authoritative health-control state machines

Health control is five orthogonal domains so concurrent degradations remain explicit. `HEALTH_STARTUP_UNPROVEN` is the aggregate initial state; startup exits it only by committing one current row for every domain. A positive state in one domain SHALL NOT clear or mask degradation in another.

```text
HEALTH_STARTUP_UNPROVEN
  -> HEALTH_PERSISTENCE_READY
  -> HEALTH_TRANSPORT_READY
  -> HEALTH_AUTHENTICATION_READY
  -> HEALTH_AUTHORITY_COHERENT
  -> HEALTH_TIME_AUTHORITY_READY

HEALTH_PERSISTENCE_READY <-> HEALTH_PERSISTENCE_DEGRADED -> HEALTH_STORE_CORRUPT
HEALTH_TRANSPORT_READY <-> HEALTH_TRANSPORT_DEGRADED
HEALTH_AUTHENTICATION_READY <-> HEALTH_AUTHENTICATION_FAILED
HEALTH_AUTHORITY_COHERENT <-> HEALTH_AUTHORITY_DIVERGED -> HEALTH_STORE_CORRUPT
HEALTH_TIME_AUTHORITY_READY <-> HEALTH_TIME_AUTHORITY_DEGRADED
```

The Listener Supervisor State Evaluator is the sole health-state transition authority. The Health Durable Writer is the sole writer of `health_current`, `health_transitions`, and `health_aggregate` when the database is trustworthy. When the database cannot durably represent its own persistence/corruption failure, the `Runtime Authority Recovery Evidence Writer` defined completely in Runtime Authority Store Schema sections 10 and 14.6 is the sole external evidence writer. Its exact path, `RANDLE-RECOVERY-JCS-1` bytes, sequence, bounded write-through replacement, record types, restart verification, and startup consumption apply; that evidence does not become a substitute health store or identity authority.

| Health state | Exact meaning and entry condition | Source evidence and evaluator | Durable representation / writer | Permitted exits and recovery | Prohibited exits/actions | Restart and readiness effect | Escalation / verification |
|---|---|---|---|---|---|---|---|
| `HEALTH_STARTUP_UNPROVEN` | No complete current startup verification and five-domain state set has committed | store recovery, clock, transport, authentication, identity coherence evidence; State Evaluator | startup health-state row and attempt identity; Health Durable Writer when store is verified | only to the five positive domain rows as one startup snapshot, or terminal startup failure | no READY inference, producer exposure, listener/bridge grant, entry, or lifecycle fence | restores unproven; blocks every health-dependent readiness gate | deadline -> startup `FAILED`; `RRV-FH-003`, `RRV-ST-001` |
| `HEALTH_PERSISTENCE_READY` | current physical database/WAL/schema/writer routing/cursor/readback are verified and no pending persistence failure exists | coordinator and readback evidence; State Evaluator | `health_current` persistence-domain row; Health Durable Writer | `HEALTH_PERSISTENCE_DEGRADED`; `HEALTH_STORE_CORRUPT` | cannot be inferred from file existence or last projection | reverify after restart; required for health control readiness | invariant failure -> degraded/corrupt; `RRV-FH-001`, `RRV-FH-003` |
| `HEALTH_PERSISTENCE_DEGRADED` | COMMIT/readback, writer queue, access, lock, or contention prevents durable current health but corruption is not yet proven | exact coordinator/write/readback failure and last verified cursor; State Evaluator | if writable, transition row by Health Durable Writer; otherwise in-memory incident plus external flushed recovery evidence by Recovery Evidence Writer, later reconciled | `HEALTH_PERSISTENCE_READY` after successful pending replay/COMMIT/readback; `HEALTH_STORE_CORRUPT` if integrity becomes unprovable | no ack/cursor advance/new fence/entry/projection fallback or new identity | survives restart through last verified cursor plus recovery evidence; blocks entries/new fences and readiness | capacity/retry exhaustion escalates to governed operator recovery; `RRV-FH-001`, `RRV-FH-003` |
| `HEALTH_STORE_CORRUPT` | schema/WAL/checksum/sequence/FK/writer-routing/identity/state-machine verification fails | startup/runtime integrity evidence; State Evaluator | external quarantine/recovery incident and manifest; Recovery Evidence Writer; corrupt DB is evidence only | `HEALTH_PERSISTENCE_READY` only through approved restoration/reinitialization and a new startup verification | no automatic restore, empty replacement, projection/log repair, producer/listener start, recycle/restart | restart remains terminal recovery-required; startup/readiness failed | `CONTROL_STORE_RECOVERY_REQUIRED`; `RRV-FH-003`, `RRV-ST-001` |
| `HEALTH_TRANSPORT_READY` | named-pipe server/client identities, capability, sequence, and current connection are verified for required producers | authenticated handshake/current connections; State Evaluator | transport-domain row; Health Durable Writer | `HEALTH_TRANSPORT_DEGRADED` | no readiness from endpoint/file/process existence | reprove on supervisor/producer restart; required for affected readiness | repeated connection failure remains degraded; `RRV-FH-001`, `RRV-FH-003` |
| `HEALTH_TRANSPORT_DEGRADED` | required pipe/capability disconnects, expires, or becomes unavailable without a terminal process predicate | ingress/capability/pipe facts; State Evaluator | transport incident/current row; Health Durable Writer when possible | `HEALTH_TRANSPORT_READY` after full re-registration and fresh accepted evidence | no death inference, fence, recycle, restart, or projection fallback | capability revoked; affected entries/readiness blocked; survives until reproof | repeated failure -> governed operator investigation, no automatic lifecycle action; `RRV-FH-001`, `RRV-FH-003` |
| `HEALTH_AUTHENTICATION_READY` | every required producer has current verified SID/PID/start/build/capability/HMAC identity | handshake and accepted frame evidence; State Evaluator | authentication-domain row; Health Durable Writer | `HEALTH_AUTHENTICATION_FAILED` | no trust from prior generation or partial identity | re-register/reprove after restart; required for affected evidence/readiness | `RRV-FH-001`, `RRV-FH-003` |
| `HEALTH_AUTHENTICATION_FAILED` | required frame/producer has authentication, integrity, identity, sequence-conflict, or capability failure | rejected frame/OS identity/capability evidence; State Evaluator | authentication incident/current row; Health Durable Writer when trustworthy | `HEALTH_AUTHENTICATION_READY` only after revoke, successful full re-registration, and fresh accepted evidence | rejected evidence cannot refresh/cancel/fence/classify terminal state; no projection substitute | affected entries/new fences/readiness blocked; restart does not clear without re-registration | three consecutive failures or conflict revokes capability and escalates incident; `RRV-FH-001`, `RRV-FH-003` |
| `HEALTH_AUTHORITY_COHERENT` | accepted direct evidence, committed current rows, parent identities, and cursor agree | State Evaluator comparison of direct/durable authority | coherence-domain row; Health Durable Writer | `HEALTH_AUTHORITY_DIVERGED` | no lower-ranked evidence override | reverify after recovery/restart; required for readiness | `RRV-FH-001`, `RRV-FH-003` |
| `HEALTH_AUTHORITY_DIVERGED` | direct/durable facts, cursor, parent identity, count, or state-machine result conflict | preserved conflicting facts and comparison; State Evaluator | divergence row if trustworthy; otherwise external recovery evidence; Health Durable Writer or Recovery Evidence Writer | `HEALTH_AUTHORITY_COHERENT` only by committing accepted current evidence under intact identity; `HEALTH_STORE_CORRUPT` if integrity is unprovable | no arbitrary winner, projection repair, new fence/entry, or count relabeling | survives restart; blocks entries/new fences/readiness | unresolved or structural divergence -> store recovery; `RRV-FH-001`, `RRV-FH-003` |
| `HEALTH_TIME_AUTHORITY_READY` | current monotonic/UTC source identities and correlation are verified and no time incident is active | clock validation transaction; State Evaluator | time-domain row/correlation identity; Health Durable Writer | `HEALTH_TIME_AUTHORITY_DEGRADED` | no reuse after clock-source change | revalidate after supervisor restart; required for freshness/expectation/readiness | `RRV-FH-003`, `RRV-ST-001` |
| `HEALTH_TIME_AUTHORITY_DEGRADED` | any exact section 3.3.5 clock failure occurs | clock samples/source identities; State Evaluator | time incident/current row by Health Durable Writer, or concurrent non-durable recovery evidence if persistence is degraded | `HEALTH_TIME_AUTHORITY_READY` only after the exact five-sample recovery COMMIT/readback | no freshness/expectation classification, time-dependent incident create/cancel/fence, epoch/generation allocation, entry, or file/projection time substitute | survives restart; blocks every freshness/expectation/feed/bar/ATR health readiness gate | second failed recovery transaction -> governed operator recovery; `RRV-FH-003`, `RRV-ST-001` |

Every health-state transition not explicitly listed in the table is prohibited. A recovery reason such as `HEALTH_TIME_AUTHORITY_RECOVERED`, a store reason such as `HEALTH_STORE_CONTENTION`, or startup result `CONTROL_STORE_RECOVERY_REQUIRED` SHALL NOT be stored or consumed as a health state. Clearing a state requires the exact named recovery evidence, evaluator decision, Health Durable Writer COMMIT/readback when the database is trustworthy, or the explicitly governed external recovery-evidence transaction when it is not; process restart, elapsed time, projection freshness, or operator assertion is insufficient.

#### 3.9.2 RAPI observation and termination model

The listener SHALL emit the raw SDK alert as `RAPI_ALERT_OBSERVED` with exact `AlertType`, `ConnectionId`, `RpCode`, message, callback time, listener epoch, bridge generation, producer sequence, and bridge process identity. It SHALL NOT translate the alert into an unsupported precise cause.

The Supervisor State Evaluator SHALL represent a terminal observation with five independent fields. No field SHALL be derived from another field, concatenated into a compound reason, or filled more precisely than its evidence permits.

| Field | Closed values | Authoritative derivation |
|---|---|---|
| `initiator` | `NONE`, `LISTENER`, `LISTENER_SUPERVISOR`, `AUTHENTICATED_OPERATOR`, `RAPI_PROVIDER`, `UNKNOWN` | Matching authenticated/durable intent or exact provider callback only; process disappearance does not identify an initiator |
| `requested_action` | `NONE`, `BRIDGE_RECYCLE`, `BRIDGE_SHUTDOWN`, `LISTENER_SHUTDOWN`, `FULL_LISTENER_RESTART`, `UNKNOWN` | Current durable command/incident bound to the exact epoch/generation before execution |
| `execution_method` | `NONE`, `GRACEFUL_RAPI_LOGOUT`, `GRACEFUL_PROCESS_EXIT`, `SUPERVISOR_TERMINATE`, `SUPERVISOR_KILL`, `PROCESS_SELF_EXIT`, `PROVIDER_FORCED_LOGOUT`, `PROVIDER_SHUTDOWN_SIGNAL`, `UNKNOWN` | Exact command acknowledgement, owned-handle process result, or raw provider alert; a new PID or missing process is insufficient |
| `observed_cause` | `NONE`, `PLANNED_SHUTDOWN`, `BRIDGE_CRASH`, `AUTHENTICATION_FAILURE`, `CONNECTION_LOSS`, `SUBSCRIPTION_FAILURE`, `LISTENER_EXIT`, `RAPI_ENGINE_INERT`, `UNKNOWN` | Raw callbacks, matched exception/crash evidence, exact owned-handle evidence, and matching durable intent; `LoginFailed` proves only authentication not accepted, and `ShutdownSignal` proves only engine inert |
| `result` | `NONE`, `COMPLETED_EXPECTED`, `RECOVERED`, `FAILED`, `TIMED_OUT`, `CANCELED`, `PROCESS_EXITED`, `ENGINE_INERT`, `UNKNOWN` | Durable action completion/cancellation or exact current process/provider result after the observation |

The active termination contract is schema version 2. The record SHALL carry `observed_at_utc` as its authoritative classification cutoff, `recorded_at_utc` as the exact transaction commit time, `termination_schema_version=2`, and `record_integrity_sha256`, plus result/set/observation identities, supervisor generation, listener epoch, bridge generation, exact listener process, observation sequence, classification decision/evaluator version, committing transaction, and the governed optional request/operator/provider/OS/process-exit/bridge/listener identities. Contributor observation time may not follow the cutoff and may not precede it by more than five seconds. Record time SHALL be at or after cutoff and no more than 30 seconds later. Prior/future/mixed contributor schema versions fail.

One `termination_evidence_sets` row names exactly one result and identity tuple. It has exactly six complete producer windows—`RITHMIC_LISTENER`, `BRIDGE_CONTROLLER`, `OS_ADAPTER`, `RAPI_ADAPTER`, `SUPERVISOR_ADAPTER`, and `OPERATOR_ADAPTER`. `termination_producer_cursors` is the durable arrival-order authority for each registered instance. `TX-TERMINATION-EVIDENCE-INGEST` reads its expected cursor version, requires producer and ingress sequences to equal prior+1, inserts exactly one normalized payload and evidence row, advances both cursor sequences and the state version in the same immediate transaction, and commits the exact request/evidence hash and idempotency identity. A new instance starts at 1. Duplicate delivery with the same idempotency key and request hash returns the recorded result without reinsertion; a different payload, late delivery, sequence gap, concurrent stale cursor, fenced instance, or old instance after replacement fails without cursor movement. A producer is fenced when its registration is durably retired; restart requires a new registered instance at sequence 1. Every evidence-set window uses only rows accepted by this path, starts at 1 for that instance’s first set, and each later set starts at its prior accepted end plus one. A set cannot splice instances.

Exactly five `termination_result_evidence` direct contributors are required, one each for `INITIATOR_EVIDENCE`, `REQUESTED_ACTION_EVIDENCE`, `EXECUTION_METHOD_EVIDENCE`, `OBSERVED_CAUSE_EVIDENCE`, and `RESULT_EVIDENCE`. Each link repeats and composite-binds the result/set, evidence ID, producer/sequence/type/time/schema/hash, normalized payload identity/hash, current generation/epoch/bridge/process/observation, authentication disposition, role, assertion kind, and value. One evidence ID cannot satisfy two roles or results. Optional identities are closed: `request_identity` is the `REQUESTED_ACTION_EVIDENCE` command payload; `operator_command_identity` is the authenticated-operator `INITIATOR_EVIDENCE` command; `process_exit_evidence_identity` is OS-backed `RESULT_EVIDENCE`; provider identity resolves in priority order Result, Cause, Method, Initiator; OS identity resolves Result/process-exit, Cause, then Method; bridge identity is Bridge-backed Result; listener identity resolves Listener-backed Result, Cause, then Initiator. The first applicable priority is mandatory and every later identity is NULL. Each identity must name the exact direct contributor, normalized payload, governed producer, current identity tuple, and authenticated row. Another role, supporting-only row, result, set, generation, epoch, bridge, process, observation, or producer instance fails.

For every field, `NONE` is legal only when current authenticated content proves complete absence through the cutoff: respectively no actor/provider/process/supervisor/operator initiated; no shutdown/recycle/restart/logout/termination request exists; no method occurred and no termination is unobserved; no applicable cause exists; or no termination action/event/result applies. For that role, every one of the six cursor-complete producer windows must supply a `CLASSIFICATION_DERIVATION` payload whose exact start/end/cursor/cutoff match the set, whose recomputed counts are zero for positive, uncertainty, conflict, and missing sequences, and whose role-specific scope is exact. SQL independently scans every in-window normalized payload and rejects any non-absence assertion. A self-declared evidence type, assertion, value, absence scope, or derivation count is not proof; a label without the six complete windows, or five `PROCESS_EXCEPTION` labels, fails.

If evidence is stale, missing, incomplete, gapped, conflicting, corrupt, unauthenticated, unavailable, cross-identity, schema-incompatible, integrity-invalid, or itself asserts uncertainty, a known or `NONE` classification is prohibited. Structural/currentity/integrity failure aborts the whole result. In a structurally complete current set, every authenticated in-window assertion is evaluated, including supporting `UNKNOWN`, `UNCERTAINTY`, and `INDETERMINATE` rows. R3 defines no same-observation precedence that can override such a row: the affected field must commit `UNKNOWN/CONFLICT` or `UNKNOWN/INDETERMINATE`; the other four fields remain independent unless their own role contains uncertainty or conflict. Planned-shutdown dependency checks can additionally reject the whole result when requested action, execution method, or result is unproved. Any `UNKNOWN` blocks termination-related startup proof. Resolution requires a new observation identity, the next gapless observation sequence, and a wholly current evidence set; prior results remain immutable.

Concrete values require positive evidence content, not merely a link label. `BRIDGE_CRASH` requires matched `PROCESS_EXCEPTION` or authoritative `OS_HANDLE` crash evidence; nonzero exit alone is insufficient. `PLANNED_SHUTDOWN` requires an authenticated planned command plus matched expected execution/result evidence. `AUTHENTICATED_OPERATOR` requires its direct operator-command identity; `FULL_LISTENER_RESTART` requires its direct request identity; provider actions require direct authenticated provider evidence; process-exit result requires the matched current process observation; and `ENGINE_INERT` requires current RAPI engine observation. Runtime Authority Store Schema section 14.5 and the executable checks/triggers define the closed evidence-type mapping for every other concrete value.

The Health State Evaluator alone detects conflict and classifies. The Health Durable Writer records the authorized decision; SQL validates but cannot originate or repair it. Concrete facts are accepted only through normalized payload tables: authenticated command/principal/action; exact OS process/start/exit/crash/method/handle; provider callback/RpCode/authentication/engine/connection; bridge generation/state/recovery/action/disposition; or listener epoch/generation/state/incident/transition/outcome. The executable predicate maps every concrete vocabulary token to its required producer, direct role, evidence type, and payload content; in particular nonzero exit alone cannot prove `BRIDGE_CRASH`. `termination_evidence.canonical_evidence_json` embeds the compact normalized payload JSON and hash. `RANDLE-TERMINATION-EVIDENCE-SET-3` serializes cursor versions and payload hashes; `RANDLE-TERMINATION-RESULT-3` serializes all optionals and contributor payload identities/hashes. The governed UDF must be registered `SQLITE_UTF8|SQLITE_DETERMINISTIC|SQLITE_INNOCUOUS` on every schema-creation, validation, trigger, index, authority-read, and authority-write connection. The direct output check, schema-owned view under `trusted_schema=OFF`, and expression index independently reject missing/wrong, non-innocuous, and nondeterministic registrations.

Derivation SHALL follow these rules:

- planned bridge/listener shutdown requires a matching durable intent preceding the effect; it yields the proven initiator/action while method, cause, and result remain independently evidenced;
- listener-requested recycle records `initiator=LISTENER` and `requested_action=BRIDGE_RECYCLE` only after the Supervisor accepts the authenticated request; it does not prove a failure cause or execution;
- supervisor terminate/kill is an execution method only when the durable fenced execution record and OS Process Adapter prove that exact command against the exact process;
- `LoginFailed` yields `observed_cause=AUTHENTICATION_FAILURE` only in the narrow sense that login was not accepted; invalid credentials SHALL NOT be inferred;
- `ConnectionBroken` yields `observed_cause=CONNECTION_LOSS`; later `ConnectionOpened` or accepted current-generation connection/login/subscription/tick evidence yields `result=RECOVERED` and cancels an unfenced matching incident;
- a matched unhandled exception, Windows crash/exception status with authoritative crash correlation, or equivalent authenticated crash report with no planned intent yields `observed_cause=BRIDGE_CRASH`; a nonzero exit code alone does not; and
- process disappearance, unmatched `ConnectionClosed`, missing evidence, unsupported `RpCode`, or conflicting intent yields `UNKNOWN` for every unproven field. It SHALL block affected entries and SHALL NOT authorize recycle/restart without an independently satisfied closed predicate.

An unexpected exact-process exit with no matched crash evidence SHALL record `result=PROCESS_EXITED`, retain `observed_cause=UNKNOWN`, and retain `UNKNOWN` for every other unproven dimension. The independently proven unexpected exit MAY satisfy BDP-01 when all BDP-01 identity and planned-transition exclusions pass; it SHALL NOT be relabeled as an internal crash.

`ForcedLogout` and `ShutdownSignal` SHALL remain exact RAPI observations. `ForcedLogout` supports `execution_method=PROVIDER_FORCED_LOGOUT` but does not prove why. `ShutdownSignal` supports `execution_method=PROVIDER_SHUTDOWN_SIGNAL`, `observed_cause=RAPI_ENGINE_INERT`, and `result=ENGINE_INERT`, but does not prove crash/authentication cause or listener failure.

The current-generation derived connection/login state transitions are closed: `ConnectionOpened -> connection=UP`; `ConnectionBroken -> connection=RECOVERING`; intent-matched `ConnectionClosed -> connection=PLANNED_CLOSED`; unmatched `ConnectionClosed -> connection=UNKNOWN`; `LoginComplete -> login=UP`; `LoginFailed -> login=FAILED_NOT_ACCEPTED`; `ForcedLogout -> login=FORCED_OUT`; and `ShutdownSignal -> engine=INERT`. `QuietHeartbeat`, `TradingEnabled`, and `TradingDisabled` SHALL NOT establish terminal cause. `ServiceError` SHALL retain exact `RpCode`/message and remain nonterminal unless a separately approved provider mapping and closed predicate says otherwise.

### 3.10 Closed bridge-recycle predicates

Bridge recycle SHALL be legal only when one current bridge generation satisfies exactly one predicate below and the decision reaches a readback-verified durable fence.

#### BDP-01 - unexpected bridge process exit

Required evidence:

- authenticated `BRIDGE_PROCESS_EXITED` from the current Bridge Controller capability;
- matching bridge PID/start identity and current bridge generation;
- exit code/time captured from the owned child-process handle; and
- immediate revalidation confirms no current-generation bridge process is running and no later `BRIDGE_PROCESS_STARTED`/`BRIDGE_GENERATION_READY` exists;
- the durable lifecycle state immediately before exit was `BRIDGE_READY` or `BRIDGE_SUSPECT`; and
- no matching planned shutdown, governed operator shutdown, startup transition, controlled bridge recycle, listener shutdown, or listener replacement incident was pending, fenced, or executing for that process identity.

BDP-01 SHALL be satisfied only by an unexpected failure. Only a matched unhandled exception, authoritative crash/exception status correlated to the exact process, or equivalent authenticated crash report yields `observed_cause=BRIDGE_CRASH`; a nonzero or otherwise abnormal exit code alone does not. An exact unexpected exit with insufficient cause evidence retains `observed_cause=UNKNOWN` and SHALL remain eligible because unexpected process exit itself is independently proven. No debounce is required after the exit-handle result and exclusions are verified. Listener process exit or listener lease loss does not satisfy BDP-01; it is an ADR-015 listener failure.

#### BDP-02 - unrecovered shared connection loss

Required evidence:

- fresh authenticated `RAPI_ALERT_OBSERVED(AlertType=ConnectionBroken)` for the current listener epoch/bridge generation;
- the exact bridge process remains alive, so BDP-01 does not apply;
- the SDK-owned recovery interval remains continuously unrecovered for ADR-015 `shared_connection_debounce_seconds`;
- no later current-generation `ConnectionOpened`, verified login/subscription, or accepted tick exists; and
- immediate revalidation through the same authenticated producer and exact process identity confirms the broken connection has not recovered.

Any listed recovery event before fence cancels the pending incident.

#### BDP-03 - all-required-subscription recovery exhausted

Required evidence:

- current connection and login remain positively verified;
- every required NQ and YM contract independently has `SUBSCRIPTION_FAILED` or a failed current-generation recovery result;
- Bridge Controller performs exactly `subscription_recovery_attempts` resubscribe attempts per required subscription, each waiting `subscription_attempt_wait_seconds` for `SUBSCRIPTION_VERIFIED` or an accepted exact-contract tick;
- failures overlap for at least ADR-015 `shared_all_symbol_debounce_seconds`;
- no required subscription becomes verified and no accepted exact-contract tick arrives; and
- immediate authenticated revalidation confirms every required subscription remains failed.

One-symbol subscription failure SHALL block that symbol and continue symbol recovery; it SHALL NOT satisfy BDP-03 or recycle the shared bridge.

#### BDP-04 - current RAPI engine shutdown signal

Required evidence:

- fresh authenticated `RAPI_ALERT_OBSERVED(AlertType=ShutdownSignal)` for the current listener epoch/bridge generation;
- the exact bridge process remains alive, so BDP-01 does not apply;
- the current engine remains inert and no later current-generation bridge-ready/connection/login/subscription/tick evidence exists for `shared_connection_debounce_seconds`;
- no planned listener/bridge shutdown intent matches the alert; and
- immediate authenticated revalidation confirms the same engine/generation is inert.

`ShutdownSignal` does not prove why the engine stopped. BDP-04 authorizes at most one bridge recycle within the current listener epoch; it SHALL NOT classify crash, authentication failure, or full-listener failure.

#### Explicit nonpredicates

The following SHALL NOT satisfy or contribute to any bridge-recycle predicate:

- stale or absent ticks by themselves;
- failed or delayed durable health publication;
- `HEALTH_PERSISTENCE_DEGRADED` or store corruption;
- delayed, stale, missing, corrupt, or fresh projection data;
- writer contention/backpressure;
- health transport unavailable or authentication failure;
- bridge generation transition already in progress;
- planned or governed operator shutdown, startup transition, controlled bridge recycle, listener replacement already in progress, listener shutdown, planned bridge shutdown, or listener epoch transition;
- `LoginFailed`, `ForcedLogout`, `ConnectionClosed`, unsupported `RpCode`, or `UNKNOWN` termination dimensions without an independently satisfied BDP;
- listener process exit/lease loss, which is governed by ADR-015;
- endpoint failure, missing diagnostic response, PID search, command-line match, or Command Center state.

### 3.11 Bridge recycle transaction

One bridge recycle SHALL use one `bridge_restart_incident_id`, `incident_version`, current supervisor generation, listener epoch, bridge generation, predicate ID, evidence set, observed/decision times, `bridge_fencing_token`, and `bridge_restart_execution_id`.

The state evaluator SHALL create `RECYCLE_PENDING` only from a closed predicate. A fresh accepted current-generation recovery event that clears the predicate SHALL compare-and-swap the incident to `RECYCLE_CANCELED`. Immediately before fencing, the evaluator SHALL revalidate authentication, identities, predicate, absence of recovery, incident version, cooldown, and the ADR-015 durable monotonic rolling-window execution count. If the count already equals the maximum, the writer SHALL compare-and-swap `RECYCLE_PENDING -> FAILED_RECOVERY_EXHAUSTED` without fencing, allocating an execution identity, or performing process action. A count greater than the maximum SHALL instead record `HEALTH_AUTHORITY_DIVERGED`/`SUPERVISOR_STORE_FAILED`, block both symbols, perform no process action, and require governed store recovery; it SHALL NOT enter `FAILED_RECOVERY_EXHAUSTED`.

`RECYCLE_PENDING -> BRIDGE_FENCED` SHALL be one `BEGIN IMMEDIATE` compare-and-swap transaction that records the final evidence, revokes old bridge-generation capability, advances incident version, and allocates the one execution identity. That durable commit is the no-cancel linearization point.

When the count is below the maximum and the `BRIDGE_FENCED` commit/readback succeeds, the supervisor SHALL send one HMAC-authenticated `EXECUTE_BRIDGE_RECYCLE` command over the current duplex pipe connection. The command SHALL carry the fence, execution identity, old generation, and intended next generation sequence. Bridge Controller SHALL reject a missing, stale, duplicate-conflicting, wrong-generation, or wrong-supervisor command.

Bridge Controller SHALL terminate/start at most one bridge child for the execution identity, report process identity and result, and keep the new generation publication-fenced until the supervisor durably records/adopts it and returns `BRIDGE_GENERATION_GRANT`. Duplicate identical commands are idempotent and return the recorded result. One bridge incident SHALL produce at most one effective replacement bridge generation and SHALL NOT change `listener_epoch_id`.

When the execution is the last permitted execution in the rolling window, failure to commit one current `BRIDGE_GENERATION_READY` before `bridge_recovery_timeout_seconds` SHALL cause the State Evaluator and Health Durable Writer to compare-and-swap that same executing/rehydrating incident to `FAILED_RECOVERY_EXHAUSTED`. An earlier permitted execution failure that leaves remaining governed capacity records ordinary `BRIDGE_FAILED`; neither branch creates an implicit retry.

If a permitted bridge execution completes as ordinary `BRIDGE_FAILED`, it authorizes no implicit retry or listener action. If the exact exhaustion conditions are met, the existing incident SHALL instead commit `FAILED_RECOVERY_EXHAUSTED`. Only that exact exhausted state may become `SFF-03` evidence, and escalation to full listener restart still requires a new ADR-015 restart request/incident, debounce, revalidation, rate eligibility, and listener fence. Neither bridge outcome fences or allocates a Listener Authority Epoch.

### 3.12 Direct proof of life and read-only snapshot

A live bridge is proven only by all of:

- current supervisor generation and unfenced listener epoch;
- accepted bridge process heartbeat within ADR-015 `lease_suspect_seconds`;
- current connection and login UP;
- fresh authenticated current-generation `SUBSCRIPTION_VERIFIED` for the exact required symbol/contract; and
- for active-market data readiness, a current-generation accepted tick within ADR-015 `symbol_tick_stale_seconds` for that symbol.

Absence of the final tick condition produces `STALE` symbol data, not bridge death. A fresh accepted current-generation tick, connection recovery, login recovery, or restored subscription after a failure boundary SHALL cancel an unfenced matching recycle.

Noncontrol consumers SHALL obtain committed snapshots from a second read-only named pipe:

```text
\\.\pipe\RandleSystem.HealthSnapshot.v1
```

The Listener Supervisor owns this pipe. Requests SHALL contain `schema_version=1`, requested scope, and correlation ID. Responses SHALL contain the immutable committed snapshot, direct-evidence freshness overlay, current identities, commit/cursor, degraded state, and correlation ID. Snapshot reads SHALL NOT enqueue writes, refresh liveness, create/cancel/fence incidents, advance cursors, retry persistence, or execute processes.

### 3.13 Durable-store and transport degradation

When a health commit cannot complete/read back, the supervisor SHALL enter `HEALTH_PERSISTENCE_DEGRADED`, retain accepted evidence/pending items within bounds, block new entries, and prohibit new bridge/listener fences. Direct accepted evidence remains immediate observation authority but SHALL NOT be represented as durable.

During `HEALTH_PERSISTENCE_DEGRADED`, an action whose fence and execution ID were durably committed and readback-verified before degradation MAY be completed idempotently under that same identity. It SHALL NOT allocate a new fence, incident, bridge generation, or listener epoch until durable control recovers. If prior fence verification is unavailable or ambiguous, no process action SHALL occur automatically.

When event transport is unavailable, the supervisor SHALL enter `HEALTH_TRANSPORT_DEGRADED`, block affected entries, revoke the disconnected capability, and reject inference from silence. It SHALL NOT recycle a bridge or restart a listener because the pipe disconnected. Direct supervisor-owned listener process/lease facts remain governed by ADR-015.

Authentication/integrity failure SHALL reject the event, revoke the capability after a duplicate conflict or three consecutive failures, enter `HEALTH_AUTHENTICATION_FAILED` for affected scope, and block entries/new fences until successful re-registration. It SHALL NOT treat the rejected frame as positive or terminal evidence.

### 3.14 Failure matrix

| Failure/event | Authoritative state | Permitted actions | Prohibited actions | Fail-safe result |
|---|---|---|---|---|
| Local durable write/COMMIT/readback failure | accepted direct evidence plus last verified durable cursor; `HEALTH_PERSISTENCE_DEGRADED` | retain pending, bounded retry, expose degradation, complete only a previously verified fence | acknowledge, advance cursor, create new fence, use projection, authorize entry | entries/new fences blocked |
| SQLite corruption/schema/sequence/incident failure | no trustworthy current durable control; `HEALTH_STORE_CORRUPT` | close handles, verified quarantine copy/manifest, terminal governed recovery | start producers/listener, create replacement, recover from projection, recycle/restart automatically | startup/control FAILED |
| Quarantine copy/flush/hash/audit failure | corrupt source plus incomplete recovery evidence | preserve all bytes/paths and report exact failed stage | delete/move source, activate restore, open ingress | `CONTROL_STORE_RECOVERY_REQUIRED`; startup FAILED |
| Qualifying approved backup available | quarantined source remains evidence; staged backup is candidate only | three-party-approved staged restore; full integrity/identity/process-ambiguity validation | automatic activation, projection-derived repair, freshness carryover | blocked until validated activation and new supervisor generation |
| No qualifying backup | no current durable control authority | governed reinitialization proposal and exact runtime/process reconciliation | automatic empty DB, projection/log reconstruction, listener start | `CONTROL_STORE_RECOVERY_REQUIRED`; startup FAILED |
| Schema migration required | source store remains authority/evidence; staged output noncurrent | approved versioned offline migration, hashes, validation, pre-exposure rollback | in-place/automatic migration, rollback after a new commit | startup FAILED until approved activation |
| Shared projection write failure/WinError 5 | local durable commit remains authority | retain projection pending, bounded retry, display lag if possible | clear projection cursor, declare death, reset ATR, change lifecycle | control unaffected; projection degraded |
| Stale/delayed/missing projection | direct/durable local authority unchanged | display stale/missing state | use in readiness or control, alone or combined | no lifecycle effect |
| Tick exceeds policy `symbol_tick_stale_seconds` | symbol `STALE`; bridge state otherwise determined by direct process/connection evidence | block symbol entries, continue observation/subscription recovery | bridge recycle/full restart from staleness alone | symbol fail-closed |
| Tick exceeds policy `symbol_data_unavailable_seconds` | symbol `DATA_UNAVAILABLE` | block symbol, apply approved symbol recovery | infer shared bridge/listener death without closed predicate | symbol fail-closed |
| BDP-01 through BDP-04 proven with all transition/shutdown exclusions false | current direct predicate plus durable incident | pending/revalidate/cancel or durable fence and one bridge recycle | unfenced action, second generation, listener epoch allocation | exactly one bridge action or failed incident |
| Listener process exit/lease loss | ADR-015 listener failure | publish ADR-015 restart request/incident evidence | classify as bridge death, bridge-only recycle as substitute | full listener remains supervisor-governed |
| Health event pipe unavailable | `HEALTH_TRANSPORT_DEGRADED` | block entries, reconnect/register, retain producer outbox | infer death from silence, create fence, read projection as substitute | fail-closed observation loss |
| Authentication/HMAC/PID mismatch | event rejected; affected scope `HEALTH_AUTHENTICATION_FAILED` | incident, capability revoke/re-register | accept fact, refresh liveness, fence from rejected fact | entries/new fences blocked |
| Supervisor generation/epoch/generation mismatch | event rejected and audited as stale/fenced | producer re-register under current identities | affect current health, cancel/fence, publish as current | current authority unchanged |
| Clock rollback/unavailable/non-increasing monotonic source/correlation ambiguity | `HEALTH_TIME_AUTHORITY_DEGRADED`, plus persistence degradation if the incident cannot commit | retain ordered observations, complete only a previously verified fence, execute the closed five-sample recovery transaction | classify freshness/expectation, create or cancel a time-dependent incident, allocate epoch/generation, use file/projection time, authorize entry | startup FAILED or runtime entries/new lifecycle actions blocked; second failed recovery attempt escalates to governed operator recovery |
| Writer queue high-water/capacity | `HEALTH_PERSISTENCE_DEGRADED` | backpressure, no-ack, retry | drop accepted control event, advance cursor, create fence | entries/new fences blocked |
| Planned startup | `BRIDGE_STARTUP_UNPROVEN`/`BRIDGE_STARTING` | establish new current identities and positive evidence | recycle from missing startup evidence, mark READY from process | startup remains unready |
| Planned shutdown | `PLANNED_SHUTDOWN` | record intent, fence/stop through owner | classify planned absence as failure or auto-restart | stopped, no restart loop |
| Bridge generation transition | old generation fenced, new `BRIDGE_REHYDRATING` | re-register capability/subscriptions, preserve finalized bars/RMA | old-generation control, listener epoch change by implication | entries blocked until coherent |
| Ordinary permitted bridge execution fails before exhaustion | `BRIDGE_FAILED` | preserve evidence; wait for a newly satisfied BDP plus cooldown/rate eligibility | implicit retry, reuse execution identity for another effective generation, direct listener restart | bridge remains unavailable; entries blocked |
| Bridge pre-execution maximum reached or last permitted recovery times out | `FAILED_RECOVERY_EXHAUSTED` | durable terminal commit; ADR-015 SFF-03 request eligibility after separate debounce/revalidation/rate checks | another bridge attempt, counter reset, direct epoch allocation/restart | both symbols blocked; no process action from exhaustion itself |
| Listener epoch transition | ADR-015 `REHYDRATING` | revoke old capabilities, reconstruct bars/RMA, require new acks | combine old/new epoch data, bridge-only substitution | deterministic rehydration |
| Startup store recovery succeeds | last verified durable commit is recovery authority; direct evidence not yet current | allocate new supervisor generation, re-register producers, revalidate current runtime | treat prior-generation direct freshness as current | blocked until positive current evidence |
| Startup store recovery fails | `HEALTH_STORE_CORRUPT` | preserve evidence, terminal startup failure | projection fallback, empty overwrite, process recycle | production remains stopped |

### 3.15 ATR, session, and trade isolation

Health persistence, transport, authentication, or projection failure is not a bar, ATR, session, ladder, trade, or execution authority event. It SHALL NOT reset RMA, change session, alter a frozen ladder, advance observation, change trade truth, cancel protective orders, or create a Listener Authority Epoch.

A Bridge Generation change within one listener epoch SHALL preserve finalized bars and valid RMA. Its incomplete minute follows ADR-015's gap-free reconstruction rule. A full listener epoch change follows ADR-015 and ADR-012 rehydration/closed-reset rules.

### 3.16 Read-side purity

Health, debug, status, startup-probe, audit, and Command Center GET/HEAD/OPTIONS requests SHALL read only immutable snapshots/projections. They SHALL NOT flush pending health, retry the store/projection, acknowledge events, advance cursors, register/revoke capabilities, refresh authoritative timestamps, create/cancel/fence incidents, or start/stop a process.

## 4. Consequences

- Health control becomes an explicit Listener Supervisor subsystem rather than a shared-file convention.
- Production gains two local named pipes and one physical local SQLite Runtime Authority Control Database with ownership-separated tables and logical writers.
- Producers require current supervisor-generation capabilities and at-least-once acknowledgement handling.
- Shared/OneDrive JSON remains useful for display/interchange but is structurally absent from control inputs.
- Availability decreases during store/transport ambiguity because new entries and new lifecycle fences remain blocked.
- Bridge recycle is legal only under four closed predicates and one durable current-generation fence.
- Precise Windows handle attribution remains evidence-driven.

## 5. Scope and isolation

This ADR governs direct feed-health evidence transport, authentication, identities, durable health control, pending/cursor semantics, projection publication, RAPI terminal/recycle classification, Bridge Generation fencing/recycle, degradation, and startup recovery.

Approved ADR-014 remains the Entry session authority. Within this proposed coordinated package, ADR-015 would be the sole authority for full-listener process lifecycle and Listener Authority Epoch if separately approved and canonically incorporated. This draft creates no current listener authority and does not change Pine, webhook payload meaning, stack validation, ATR formula, Step 2/4, trade ownership, execution actions, protective orders, or risk.

`DEBT-2026-07-17-015` remains separately governed.

## 6. Required verification

Verification SHALL cover:

- named-pipe ACL, PID/start/build binding, capability grant/revoke, HMAC, frame bounds, canonical JSON, checksum, duplicate/id conflict, and stale supervisor/epoch/generation rejection;
- producer/evaluator/transition-authority/durable-writer separation for listener proof of life, `SUBSCRIPTION_PROOF_OBSERVED` -> `SUBSCRIPTION_VERIFIED`, bridge acknowledgement/grant, termination, market-data expectation, ATR continuity, and Command Center parity;
- event freshness plus every ADR-015 policy heartbeat/tick/debounce/attempt boundary with deterministic clocks;
- `HEALTH_TIME_AUTHORITY_DEGRADED` entry, durable/non-durable evidence, startup failure, runtime prohibitions, five-sample recovery, second-failure escalation, restart survival, readiness blocking, and no projection-time fallback;
- every bridge and authoritative health state in section 3.9, every listed permitted exit, every recovery/escalation/restart/readiness behavior, and rejection of all unlisted transitions and cross-domain aliases;
- Pattern A one-physical-database identity design, exact table set, one physical transaction coordinator, logical table-writer routing, same-database foreign keys, uniqueness, transaction boundaries, cross-owner-plan rejection, crash/partial-write/WAL reconstruction, corruption handling, and prohibition of a duplicate identity authority;
- SQLite configured pragmas, `BEGIN IMMEDIATE`, `synchronous=FULL`, COMMIT/readback acknowledgement, monotonic cursor, duplicate idempotency, and contention;
- WinError 5 and every store/projection write stage without unsupported handle attribution;
- producer outbox, no-ack retry, writer pending retention, backpressure, capacity, and no warning storm;
- WAL restart recovery, unsupported schema, checksum/sequence/same-database-foreign-key/ancestry/writer-routing/incident failure, verified quarantine, qualifying and nonqualifying restoration sources, no-source fail-closed recovery, reinitialization, rollback boundary, audit failure, and empty-store overwrite prohibition; migration verification is absent from the current catalog and may exist only under a future `FUTURE SEPARATELY GOVERNED PREDECESSOR-BOUND MIGRATION SPECIFICATION`;
- every independent termination field/value, complete-evidence `NONE`, every mandatory `UNKNOWN` evidence defect, raw callback preservation, intent/exit correlation, nonzero-exit-without-crash evidence, matched crash evidence, `ConnectionBroken` recovery, `ConnectionOpened` cancellation, `LoginFailed` non-credential narrowing, `ShutdownSignal` engine-inert behavior, and per-field `UNKNOWN` from process disappearance;
- projection one-way dependency and proof that stale/fresh/corrupt/missing/contradictory projection cannot initiate, influence, reinforce, confirm, participate in, or contribute to control/readiness;
- every BDP predicate positive/negative case, every explicit nonpredicate, and BDP-01 exclusion of every planned/operator/startup/recycle/shutdown/replacement transition;
- `RECYCLE_CANCELED` exact entry evidence, atomic durable incident/current-state result, `BRIDGE_READY`/`BRIDGE_SUSPECT` derivation, prohibited fence/execution/reopen/generation/SFF-03 transitions, restart restoration, later-incident separation, old-generation rejection after fence, duplicate command idempotency, and one effective replacement bridge generation;
- `BRIDGE_STARTUP_UNPROVEN` entry/exit/restart/readiness behavior and proof that only exact current-generation `SUBSCRIPTION_VERIFIED` satisfies subscription readiness while `ACTIVE` is rejected;
- ordinary `BRIDGE_FAILED` versus identical cross-ADR `FAILED_RECOVERY_EXHAUSTED` entry/persistence/no-action/restart-survival/SFF-03 behavior;
- durable fence completion during later store degradation and ambiguous fence no-action;
- transport/authentication degradation and no death inference from silence;
- bridge versus listener failure and separate ADR-015 escalation;
- ATR/finalized-bar continuity and incomplete-minute disposition; and
- pure snapshot reads with no persistence, cursor, liveness, incident, authorization, process, or port effect.

## 7. Relationship to existing authority and proposed amendments

- Constitution single-owner, durable-before-exposure, read-only, failure-preservation, and fail-closed doctrines remain governing.
- ADR-012 finalized-bar/RMA continuity and read-side separation remain governing.
- If separately approved and canonically incorporated, ADR-015 would own Listener Supervisor generation, full-listener restart, epoch fencing, and downstream rehydration. Its current draft status creates no authority.
- Runtime Authority SHALL require coordinated amendment only after this ADR is approved.
- Shared health JSON remains a projection; this ADR defines the missing local control implementation contract.

## 8. Rejected alternatives

Rejected: shared JSON as control; fresh shared JSON as supplemental control; multiple writers; Health Durable Writer inside the listener or Executor; HTTP/status transport for direct evidence; unauthenticated producer claims; tick staleness as bridge death; implicit/open-ended death predicates; bridge recycle without durable fence; new empty DB on corruption; cursor advance on attempted write; memory-only durable claims; projection fallback; automatic listener epoch on bridge recycle; and blaming OneDrive without handle evidence.

## 9. Architectural exit criteria

The ADR is architecturally closed only when:

1. one authenticated pipe, one Supervisor-hosted writer, and one local SQLite store are the only health-control path;
2. current supervisor/epoch/generation identity is verified for every direct fact;
3. direct evidence acceptance, durable commit, acknowledgement, and projection are separate observable states;
4. failed persistence retains pending and cannot authorize control;
5. shared projection has no import path into control/readiness;
6. only BDP-01 through BDP-04 can create a bridge pending decision;
7. one verified fence produces at most one effective bridge generation;
8. ordinary `BRIDGE_FAILED` and terminal `FAILED_RECOVERY_EXHAUSTED` remain distinct and only the latter can supply SFF-03 evidence;
9. `HEALTH_TIME_AUTHORITY_DEGRADED` and every other degradation/startup recovery follow the failure matrix exactly; and
10. all required verification and governance gates pass.

## 10. Expected implementation and verification

Expected future implementation areas, without authorization:

- Listener Supervisor Health Event Ingress, State Evaluator, Health Durable Writer, snapshot pipe, and projection publisher;
- listener/Bridge Controller and Executor authenticated producer clients/outboxes;
- local health SQLite store and exact data-path separation;
- bridge incident/fence/command state machine;
- startup/readiness consumers using the immutable snapshot pipe; and
- replacement of every shared-file control reader.

Expected verification artifacts:

- transport/authentication/integrity suite;
- durable store/fault/corruption/restart suite;
- bridge predicate/fence/exactly-once suite;
- projection isolation and WinError 5 suite;
- ATR/epoch/bridge integration suite;
- startup/degradation matrix; and
- diagnostic nonmutation suite.

Current semantic traceability is incomplete. `Architecture/Audits/2026-07-17_ADR015_016_Clause_Traceability_Registry_DRAFT.md` is historical rejected Phase 3B evidence, not a current forward/reverse mapping. Phase 3C2 will rebuild clause/scenario/assertion traceability only from independently accepted Phase 3C1-R3 hashes. The external recovery matrix remains a package-level index and is not a substitute. No implementation or production authorization follows from this draft.
