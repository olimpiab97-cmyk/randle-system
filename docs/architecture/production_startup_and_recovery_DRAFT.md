# Production Startup, Recovery, and Readiness Contract

Version: Draft 0.4 - Phase 3A remediation

Status: **DRAFT - NOT CANONICAL - NOT APPROVED**

Governing Dependency: approved ADR-014 and canonical ADR-012. ADR-015, ADR-016, this startup contract, and coordinated Runtime Authority amendments remain proposed draft authority pending independent approval and canonical incorporation.

Implementation Authorization: None. Production remains stopped.

## 1. Purpose

Define one bounded cold-start and manual-start transaction with explicit authority restoration, dependency order, positive readiness proof, terminal success/failure, ATR continuity, external webhook proof, entry-lock preservation, and controlled shutdown.

## 2. Governing startup invariant

Process existence, endpoint reachability, file existence, newest timestamps, or absence of errors is not readiness. Each readiness transition requires positive evidence from its named authority and validation against the current startup attempt, supervisor generation, listener epoch, bridge generation, symbol/contract, session commit, bar, ATR, and projection identities.

The startup orchestrator is a bounded client of domain owners. It SHALL NOT become Listener Supervisor, Health Durable Writer, Entry Session Commit Writer, trade owner, execution owner, or trading-authorization owner.

The only terminal startup results are:

```text
READY_LOCKED
FAILED
```

`READY_LOCKED` means the full infrastructure and current production context are coherent while the production entry lock remains engaged. It is not deployment authorization or trading permission. `FAILED` records exact blockers and SHALL NOT be presented as partial success.

## 3. Startup attempt identity and deadlines

Before any process start, the orchestrator SHALL create:

- `startup_attempt_id` as a UUID;
- `startup_started_at_utc`;
- `startup_started_monotonic`;
- `startup_policy_version = startup-readiness-v1`;
- exact build/config identities;
- per-phase deadline values; and
- one absolute `startup_deadline_utc` and monotonic deadline.

The default policy SHALL be:

| Phase | Maximum elapsed time from phase start |
|---|---:|
| Pre-start authority/evidence gate | 30 seconds |
| Listener Supervisor restore | 30 seconds |
| Executor restore/reconciliation | 30 seconds |
| Trade Manager restore/reconciliation | 30 seconds |
| Entry Agent restore | 30 seconds |
| Listener start/epoch/bridge grant | 90 seconds |
| Rithmic login/subscriptions/current ticks | 90 seconds |
| Completed-bar/ATR rehydration | 180 seconds |
| Ngrok/public TradingView delivery | 300 seconds |
| Current session/ladder/Command Center reconciliation | 300 seconds |
| Absolute attempt deadline | 900 seconds |

An override requires an approved deployment configuration with a finite positive value and recorded reason. Missing, zero, negative, nonfinite, or unbounded timeout SHALL fail the pre-start gate. A timeout SHALL transition the affected state to FAILED and SHALL NOT trigger an implicit restart loop.

The orchestrator SHALL write an append-only attempt evidence record under `%LOCALAPPDATA%\RandleRuntimeData\control\startup\` using the attempt ID. This record is audit evidence, not domain authority, and SHALL contain no credentials or secrets.

## 4. Pre-start authority gate

Before any production process start, orchestration SHALL verify and record:

- a governance-produced applicability snapshot showing zero production-readiness debts in `BLOCKING` status, with registry hash, evaluation time, scope decision, and deployment authorization identity;
- explicit documentation/deployment/start authorization and exact artifact/config hashes;
- production entry lock engaged for NQ and YM;
- Executor/Trade Manager flat or an explicitly governed active-trade disposition;
- no unresolved prior startup attempt with live process authority;
- expected ports/processes clear or one explicitly adoptable owner identified;
- local ADR-014 session-store and Pattern A Runtime Authority Control Database paths are outside shared/synchronized projection roots;
- store existence/disposition, schema version, integrity, and recovery result from each owning component;
- credential/config presence without logging secret values;
- required symbols NQ/YM and resolved contract expectations;
- required current trading session/date/time-zone expectation; and
- startup attempt/deadline evidence.

Failure SHALL terminate startup before public exposure. Startup SHALL NOT clear, copy, overwrite, create an empty replacement for, or infer authority around an untrusted store.

### 4.1 Corrupt control-store restoration and migration gate

Each control-store owner SHALL return exactly one pre-start disposition: `VERIFIED_CURRENT`, `RECOVERY_REQUIRED`, or `FAILED`. Orchestration SHALL NOT inspect tables and invent a disposition, select the newest file, or continue around an owner that returns `RECOVERY_REQUIRED`/`FAILED`.

For the Pattern A Runtime Authority Control Database, integrity detection, table-writer routing, same-database foreign keys, verified quarantine, valid restore sources, approvals, epoch/generation preservation, reinitialization, migration, rollback, and audit SHALL follow ADR-015 section 3.3.1 and ADR-016 sections 3.6.1-3.6.7 exactly. The startup evidence manifest SHALL include the store UUID, resolved database/sidecar paths, schema/policy/table-writer-registry/migration identities, last verified supervisor and health cursors, supervisor/listener/bridge ancestry, integrity/foreign-key/writer-routing results, recovery incident, quarantine manifest/hash, candidate source/hash, approval identities, and activation audit record as applicable.

No restoration or migration is automatic. Shared/OneDrive projection JSON, Command Center/status output, logs, process memory, a copied snapshot, or operator-edited records SHALL NOT be a control restoration source. When no qualifying owner-produced or governance-controlled backup exists, startup SHALL record `CONTROL_STORE_RECOVERY_REQUIRED`, remain terminally `FAILED`, leave public exposure and listener start prohibited, and require a separately governed operator reinitialization plan.

An approved restoration SHALL preserve the source store UUID, durable cursor, incident/fence/execution history, and listener/bridge ancestry, then allocate a new supervisor generation without importing prior freshness. A reinitialization SHALL use a new store UUID, fence every prior authority identity, reconcile exact runtime/OS state, and remain blocked until explicitly activated. A migration SHALL be versioned, staged, hash-bound, fully validated, and reversible only before activation/first new commit. An unresolved cursor gap or ambiguous process action SHALL make the candidate ineligible.

The same no-projection-fallback, no-empty-replacement, staged-validation, audit, and fail-closed startup rules SHALL apply to the separate ADR-014 session store through its owning recovery contract. ADR-015 supervisor and ADR-016 health/bridge tables are not separate stores; they share the Pattern A physical database while retaining the exact logical writers and authorities in the table-writer registry. If the Session Commit Writer or Runtime Authority recovery owner lacks an approved recovery disposition for detected corruption/version mismatch, startup SHALL fail; ADR-016 recovery SHALL NOT be generalized to manufacture session authority.

## 5. Canonical dependency order

The order SHALL be:

1. **Governance debt gate** verifies zero applicable blocking production-readiness debt; failure terminates before process start.
2. **Listener Supervisor** restores its durable store, acquires one new supervisor generation, and exposes no listener authority until recovery is coherent.
3. **Executor** restores/reconciles execution truth, establishes its exclusive execution-command authority, exposes immutable reads, and accepts only supervisor-granted epoch data.
4. **Trade Manager** restores trade lifecycle, reconciles with Executor through an explicit command/event boundary, and keeps new entries blocked.
5. **Entry Agent / TradingView receiver** restores the ADR-014 session store and Entry lifecycle, exposes candidate receipt, and keeps session/trade authorization blocked.
6. **Rithmic listener through Listener Supervisor** starts/adopts one process, receives one epoch grant, and starts one Bridge Generation.
7. **ADR-015 market-data expectation and ADR-016 health control** verify expected-data authority, register authenticated producers, commit current health, and establish current connection/subscription/tick evidence.
8. **Bars/ATR recovery** restores completed-bar/RMA authority and reconciles current contracts/epoch.
9. **Ngrok and external TradingView route** starts only after the local receiver/relay is pure and reachable.
10. **Real external TradingView delivery** proves the actual public inbound route and separately obtains authenticated sender identity.
11. **Session/ladder reconciliation** verifies the current ADR-014 commit and exact canonical frozen-ladder parity for NQ/YM.
12. **Command Center projection** proves the same production identities without using test/unverified projection.
13. **Terminal readiness evaluator** records `READY_LOCKED` or `FAILED`.

Starting a later component early SHALL NOT bypass its prerequisites. Manual startup SHALL call the same owners in this order and SHALL NOT substitute direct listener or bridge commands.

## 6. Readiness state contract

Every row whose `Contribution to terminal READY` cell says `Required` or `Required before ...` is a mandatory startup gate for NQ and YM where symbol-scoped. Rows labeled `Insufficient alone` are prerequisite evidence only. Post-start authorization states are excluded from this table. A mandatory state not reached by its deadline is `FAILED`.

| Readiness state | Prerequisite authorities | Required positive proof | Validation method | Failure condition | Contribution to terminal READY |
|---|---|---|---|---|---|
| `ZERO_BLOCKING_PRODUCTION_DEBT` | Architecture Debt Registry owner; Architecture Governance; Deployment Authorization Owner | immutable applicability snapshot with registry/schema version, registry SHA-256, evaluated debt IDs/statuses, production-readiness scope, evaluation time, approver identity, and count `0` for applicable `BLOCKING` debt | verify signatures/identities, registry digest, scope rules, status history, deployment binding, and no later superseding debt record | any applicable blocking debt, stale/missing snapshot, digest/status/scope mismatch, or unapproved exception | Required before any process start; no exception or implicit waiver |
| `PRESTART_VALIDATED` | deployment/start authorization; entry-lock owner; process/port evidence | authorization ID, lock identity, store paths, expected symbols/contracts/session, no ambiguous live authority | compare hashes/IDs; exact PID/port inventory; owner-signed store dispositions | missing authorization, lock open, ambiguous process/port/store | Required |
| `CONTROL_STORES_VERIFIED` | ADR-014 Session Commit Writer for the session store; Runtime Authority recovery owner plus ADR-015 logical writers and ADR-016 Health Durable Writer for the one Pattern A database | both physical stores return `VERIFIED_CURRENT`; the runtime database additionally proves one coordinator, table-writer registry, same-database foreign keys, schema/integrity, supervisor/health cursors, current authority, or an approved fully activated recovery with audit identity | ADR-014 recovery contract plus ADR-015 3.3.1 and ADR-016 3.6.1-3.6.7; compare store UUID/version/cursors/table-writer digest/FK/incident/approval hashes | `RECOVERY_REQUIRED`, corruption, writer-routing/FK failure, unsupported version, quarantine/audit failure, unapproved source, unresolved cursor/process ambiguity | Required before any authority-dependent start |
| `PROCESS_STARTED` | owning component launcher/start command | PID, parent PID, executable/build hash, start time, startup attempt ID | OS process identity equals intended artifact and attempt | process absent, duplicate, wrong parent/build, exited | Insufficient alone; prerequisite only |
| `ENDPOINT_REACHABLE` | started component and pure endpoint owner | response with PID/build/startup attempt correlation | bounded local request and exact response identity | timeout, wrong PID/build/attempt, mutating endpoint | Insufficient alone; prerequisite only |
| `SUPERVISOR_AUTHORITY_READY` | ADR-015 supervisor-generation/epoch/incident authorities in the Pattern A Runtime Authority Control Database | verified ownership-separated tables, one current `supervisor_generation_id`, no ambiguous fenced/executing incident, one lease holder | same-database integrity/schema/table-writer/FK/cursor/incident validation plus lease verification | corrupt/unreadable database, duplicate writer/lease/identity, invalid FK/routing, ambiguous execution/process | Required |
| `SHARED_FEED_POLICY_VALID` | ADR-015 Listener Supervision Policy Evaluator; Architecture Governance; Deployment Authorization Owner | durable `POLICY_VALID` result binding exact canonical artifact bytes/hash, schema/policy/topology identity, allowed values/ranges, evaluator build, approval, deployment authorization, and startup attempt | compare the policy-validation result to the deployment artifact and `policy_validation_results` row in the Pattern A database | `SHARED_FEED_POLICY_INVALID`, missing/stale result, digest/version/range/approval mismatch, or attempted override | Required before listener/bridge grant; invalid policy terminates startup without restart |
| `EXECUTOR_AUTHORITY_READY` | Executor execution authority/store; Listener Supervisor epoch contract | one exclusive Executor command owner for the startup attempt/build/config, verified execution-store identity, current supervisor-generation intake grant, entry gate locked, and no competing Executor command process | owner-issued authority/reconciliation command followed by immutable store/process/lease readback and supervisor-grant comparison | duplicate/ambiguous owner, wrong build/attempt/store, missing current grant, stale epoch acceptance, or unlocked entry gate | Required; process/endpoint evidence is insufficient |
| `EXECUTOR_RECONCILED_LOCKED` | Executor execution store and live broker/paper authority | positions/orders/pending requests reconciled; current intake accepts only supervisor-granted epoch; entry lock engaged | explicit reconciliation command result and immutable snapshot compare | unknown exposure/order/request, stale epoch intake, read-side mutation | Required |
| `TRADE_MANAGER_RECONCILED_LOCKED` | Trade Manager durable trade state and Executor snapshot | every open/closed trade agrees with execution truth; new entries blocked | explicit idempotent reconcile command followed by pure snapshot comparison | orphan/unknown exposure, persistence ambiguity, entry gate open | Required |
| `ENTRY_AGENT_RESTORED_BLOCKED` | ADR-014 Entry Session Commit Writer/store | store schema/integrity verified; current or explicit no-current session state restored; no raw/canonical divergence | ADR-014 startup decision table and active-pointer verification | corrupt store, partial authority, prior session active after date boundary | Required |
| `LISTENER_EPOCH_GRANTED` | Listener Supervisor | one child process with one-use authority token, one current epoch grant, old epoch fenced, listener acknowledgement | supervisor durable incident/epoch record plus child token/process identity | duplicate process, old epoch live, missing grant/ack, stale supervisor generation | Required |
| `BRIDGE_GENERATION_GRANTED` | Listener Supervisor State Evaluator as sole grant authority; Bridge Controller as acknowledgement/result producer only | one Supervisor-granted current Bridge Generation within the granted listener epoch, plus the Bridge Controller's authenticated acknowledgement of that exact grant/capability | compare Supervisor durable grant/readback to authenticated Bridge Controller acknowledgement and exact current identities | bridge generation mismatch, old capability, unfenced duplicate, missing Supervisor grant, or an acknowledgement represented as grant authority | Required |
| `MARKET_DATA_EXPECTATION_READY` | ADR-015 Market Data Expectation Evaluator; deployment-bound calendar and subscription intent | current nonexpired `DATA_EXPECTED` record for NQ/YM with calendar ID/version/digest, interval, subscription-intent version, supervisor generation, listener epoch, and evaluation/expiration times | verify calendar/deployment hash, interval coverage, monotonic/UTC correlation, current subscription intent, owner commit and expiration | `EXPECTATION_STARTUP_UNPROVEN`, `EXPECTATION_EXPIRED`, `DATA_NOT_EXPECTED`, clock ambiguity, calendar or intent mismatch | Required for market-data readiness; silence cannot satisfy or negate it |
| `RITHMIC_CONNECTED` | current listener/bridge direct evidence | fresh authenticated current-generation `RAPI_ALERT_OBSERVED(AlertType=ConnectionOpened)` with derived `connection=UP`, and `RAPI_ALERT_OBSERVED(AlertType=LoginComplete)` with derived `login=UP`, both after epoch/generation grant | ADR-016 pipe producer identity/HMAC/sequence/freshness plus durable health COMMIT/readback | terminal/conflicting callback, missing UP derivation, stale/unauthenticated/prior-generation evidence, deadline | Required |
| `SYMBOLS_SUBSCRIBED` | Rithmic listener authenticated `SUBSCRIPTION_PROOF_OBSERVED` producer; Listener Supervisor State Evaluator; Health Durable Writer | committed `SUBSCRIPTION_VERIFIED` for resolved current NQ and YM contracts after the current generation grant | authenticate/sequence the producer proof, verify exact contract/epoch/generation/request/freshness, inspect the evaluator decision, and require Health Durable Writer COMMIT/readback of the current result | missing/wrong contract, producer self-assertion without evaluator/writer, one symbol unverified, old generation, request return/`ACTIVE` without committed verification | Required |
| `CURRENT_EPOCH_TICKS` | listener, Executor, Trade Manager intake authorities | at least one fresh tick per symbol accepted by listener, durably accepted by Executor, and committed by Trade Manager after epoch grant | join tick ID/sequence, source time, epoch/generation, symbol/contract, and three acknowledgement records | missing/mismatched/duplicate-conflicting/stale tick or downstream ack | Required |
| `HEALTH_CONTROL_DURABLE` | ADR-016 Health Durable Writer/store | current health commit/cursor includes connection, login, subscriptions, bridge and delivery facts and proves no active `HEALTH_TIME_AUTHORITY_DEGRADED` or other health-authority degradation | SQLite COMMIT/readback identity and cursor verification plus current clock-correlation/recovery record | degraded/corrupt store, `HEALTH_TIME_AUTHORITY_DEGRADED`, pending unacknowledged current facts | Required |
| `BARS_FINALIZED` | listener finalized-bar authority | verified durable completed-bar sequence for each current contract; any new bar identifies current epoch | bar ID/sequence/checksum/contract/session validation; rehydration disposition | gap/corruption/contract mismatch or only incomplete bar without valid history | Required |
| `CANONICAL_RMA_ATR_READY` | canonical ATR/RMA authority and current ADR-015 recovery transaction | Wilder RMA record for the current resolved contract and active ADR-014 session; applicable current listener epoch; recovery transaction/continuity identity; closed `RETAIN`/`INVALIDATE`/`REBUILD`/`REHYDRATE` disposition; included-history identity/count; value; and `last_finalized_bar_id` exactly equal to `BARS_FINALIZED` | join ATR record to current session commit, listener epoch/recovery incident, durable completed-bar cursor/checksum, and latest finalized-bar identity; independently recompute or verify the RMA and disposition; apply section 6.1 when no new bar finalized | WARMUP, gap, corrupt/missing RMA, stale epoch/recovery transaction/cache/session, mismatched latest bar/contract/session, unclosed disposition, or inherited projection-only ATR | Required; WARMUP is failure at deadline |
| `TV_RECEIVER_REACHABLE` | Entry Agent receiver | pure local receiver readiness response correlated to PID/build/attempt | bounded endpoint identity and nonmutation test contract | timeout, wrong process/build, endpoint mutation | Required but insufficient without external receipt |
| `NGROK_ROUTE_READY` | Ngrok process and local relay owner | exactly one approved HTTPS tunnel to the intended local upstream and public host recorded | ngrok local API plus local upstream identity comparison | duplicate/wrong tunnel/upstream/host, endpoint only without receipt | Required but insufficient without external receipt |
| `REAL_PUBLIC_ROUTE_DELIVERY_PROVEN` | ngrok, relay, Entry receiver | one post-attempt request traverses the deployment-authorized public host -> relay -> Entry receiver under one receipt ID and exact payload hash | correlate tunnel activation/host, ingress/forward/ack times, relay receipt, Entry immutable receipt, and identical payload bytes/hash; reject loopback/self-probe evidence | local self-probe, receipt predating attempt/tunnel, wrong host/upstream, missing hop, payload mismatch | Required; proves route only |
| `WEBHOOK_SENDER_AUTHORITY_VERIFIED` | separately approved TradingView sender-authentication authority; ADR-014 candidate validator | authenticated sender principal is cryptographically bound to the exact receipt ID/payload hash plus freshness and replay evidence, with result `VERIFIED` | execute the approved security contract and join its validation record to route receipt and candidate identity | authority/mechanism unavailable, `FAILED`, identity/payload mismatch, replay ambiguity, timestamp/session freshness failure | Required; current production cannot satisfy this state |
| `ENTRY_SESSION_COMMITTED` | ADR-014 Entry Session Commit Writer | verified current-session aggregate and materialized identical commit/session/integrity identity on every required current artifact | ADR-014 store active pointer plus projection comparison | no current commit, candidate only, stale prior active, missing/mismatched commit ID, store degradation | Required |
| `PRODUCTION_LADDER_AUTHORITATIVE` | committed Entry Session Aggregate and Entry ladder builder | canonical frozen ladder activated inside the current session transaction; exact received payload -> production resolved frozen ladder equality, including distinct owners, levels/stacks/order/derived entries/source timestamp/version and shared commit ID | deterministic field-by-field comparison using payload hash, active pointer, frozen-ladder integrity identity, and session commit ID | first divergence, candidate/raw-only/test projection, merged owners, missing detail, inactive/mismatched frozen ladder | Required |
| `COMMAND_CENTER_ALIGNED` | canonical domain-owner snapshots as inputs; Command Center display projection as observational output only | production projection equals the canonical owner snapshots and carries current session commit/epoch/generation/bar/ATR identities without claiming ownership | pure read and exact field/identity comparison against owner-supplied immutable snapshots; verify that the projection emits no acknowledgement consumed by Listener Supervisor | TEST/UNVERIFIED label, stale/missing/mixed identity, polling mutation, projection used to close `REHYDRATING`, or projection value used as health/session/lifecycle/recovery evidence | Required observational parity gate only; supplies no canonical or lifecycle authority |
| `STARTUP_READY_LOCKED` | all required states above | one coherent NQ identity set and one coherent YM identity set; no blocker; entry lock still engaged | terminal evaluator checks all positive proofs and records evidence manifest | any missing/failed state, deadline, mismatch, or entry lock open | Sole startup success state |

### 6.1 Valid no-new-finalized-bar ATR continuity case

Startup MAY reuse the numerical value of a previously committed canonical RMA without recalculation only when all of the following positive evidence is present:

1. the canonical finalized-bar owner proves that no bar later than the recorded `last_finalized_bar_id` has finalized for the current resolved contract and active session;
2. `BARS_FINALIZED` identifies that same latest bar, cursor, checksum, included-history boundary, and contract/session identity;
3. the current ADR-015 recovery transaction verifies continuous durable history and records `ATR_CONTINUITY_PRESERVED` with disposition `RETAIN` by verified `REHYDRATE`;
4. a current readiness record materializes the current supervisor generation, applicable listener epoch, recovery transaction/incident identity, active session commit, contract, retained RMA record, latest bar, and integrity identity;
5. current-epoch connection, subscription, and tick gates independently prove that the feed is current; and
6. no stale epoch, prior session, prior contract, projection/cache-only value, gap, corruption, reset reason, or newer unprocessed finalized bar exists.

This case reuses a verified mathematical result but SHALL NOT reuse prior freshness or readiness. Failure of any condition requires the closed ADR-015 rehydration/rebuild disposition and remains `REHYDRATING` or `WARMUP`; file existence, unchanged value, or absence of a newly observed bar is insufficient.

### 6.2 Post-start deployment and trading authorization

`TRADING_PERMITTED` is a post-start authorization decision state. It is not a startup readiness gate, prerequisite, proof, or terminal result. The terminal startup evaluator SHALL first evaluate every mandatory section 6 gate and record exactly one `READY_LOCKED` or `FAILED` result. `TRADING_PERMITTED` SHALL NOT contribute evidence to, cause, repair, or be evaluated inside `READY_LOCKED`.

Only after a durable `READY_LOCKED` record exists may the separately governed Deployment Authorization Owner and Trading Authorization Owner evaluate a post-start authorization transaction. That transaction SHALL carry the exact startup attempt and terminal record, current ADR-014 session commit, listener epoch, bridge generation, contracts, bar/ATR identities, Executor/Trade Manager/risk identities, zero applicable blocking-debt snapshot, deployment artifact/config hashes, authorization scope/expiration, and independent lock-release authority. It SHALL fail closed if any identity has changed or any readiness/degradation/debt condition is no longer satisfied.

The post-start decision may produce `TRADING_PERMITTED` only after `DEBT-2026-07-17-016` is resolved through separately approved, implemented, and verified sender-authentication authority; all applicable production blocking debt is zero; deployment is explicitly authorized; Bucket 0 has its separate complete exit decision; and the exact trading scope is explicitly authorized. It SHALL NOT bypass the sender debt, deployment authorization, the entry lock owner, Bucket 0 exit, or any runtime authority. It SHALL NOT imply Bucket 0 completion, authorize Bucket 1, approve Step 2 Rejection, or compensate for an incomplete liquidity ladder.

`READY_LOCKED` therefore means ready while locked. Absence, denial, expiry, or revocation of the later trading decision leaves startup successfully `READY_LOCKED` and trading blocked; it SHALL NOT retroactively convert startup to `FAILED`. Runtime degradation after authorization follows the owning fail-closed gate and revokes or blocks entry eligibility without rewriting the historical startup terminal result.

## 7. Negative evidence rules

The following SHALL NOT satisfy any readiness state:

- stale files or timestamps;
- prior-session locks or canonical aggregates after their applicability date;
- prior supervisor generations, listener epochs, or bridge generations;
- raw receiver candidates or sender `locked=true` assertions;
- Command Center test/unverified projections;
- file existence without schema/integrity/current identity verification;
- PID/process existence or port ownership alone;
- endpoint reachability alone;
- local public self-probes;
- a user-agent string without the correlated real external delivery evidence;
- public-route traversal, TLS, `Host`, source address, receipt time, sender timestamp/session assertion, `locked=true`, or payload hash without separately verified sender identity;
- shared/OneDrive feed-health JSON;
- projection freshness without direct/durable authority;
- WARMUP, WAIT, REHYDRATING, SUSPECT, PENDING, DIVERGED, DEGRADED, or FAILED states; or
- `HEALTH_TIME_AUTHORITY_DEGRADED`, `FAILED_RECOVERY_EXHAUSTED`, `RESTART_CANCELED` without its required post-cancellation reevaluation, or any unresolved bridge/listener incident; or
- absence of an observed error.

Durable current-session, completed-bar, and ATR authority MAY predate the startup attempt only when its canonical identity/integrity is verified and the applicable recovery contract permits rehydration. Connection, login, subscription, current-epoch tick/delivery, current supervisor/epoch/generation, and real public-webhook evidence SHALL postdate the relevant attempt/grant.

## 8. ADR-014 session startup decision table

| Startup evidence | Required state/action |
|---|---|
| Verified current-session aggregate and all present current artifacts share complete commit identity | restore; regenerate missing projections; remain `COMMITTED_FAIL_CLOSED` until required exposures verify |
| Verified aggregate with missing/partial projections | aggregate remains authority; retry projections under same ID; entries blocked |
| Current-labeled session/commit/version/integrity mismatch | `SESSION_PROJECTION_DIVERGED`; preserve; terminal Entry readiness failure |
| Corrupt/gapped/unreadable session store or no verified active pointer | `SESSION_STORE_CORRUPT`; no projection/raw/prior fallback; terminal failure |
| Valid current candidate plus stale prior committed aggregate | candidate stays noncurrent; prior historical/ineligible; execute normal transaction exactly once |
| No current candidate/commit | `NO_CURRENT_SESSION_CONTEXT`; terminal full-stack readiness failure at deadline |
| Current-labeled artifact lacks materialized commit ID | invalid/unexposed; never authority |

No startup path SHALL advance observation reset independently.

## 9. ATR continuity and rehydration

### 9.1 Bridge recycle

- listener epoch remains unchanged;
- finalized completed bars and valid Wilder RMA remain unchanged;
- incomplete minute follows ADR-015 gap-free reconstruction or explicit incomplete-minute discard;
- affected symbol remains REHYDRATING until current-generation publication resumes; and
- bridge change alone SHALL NOT emit `canonical_atr_reset`.

### 9.2 Full listener restart

- old epoch is durably fenced and new epoch granted;
- old-epoch input is rejected;
- completed bars/RMA reconstruct from durable current-contract authority;
- exact continuous reconstruction emits `ATR_CONTINUITY_PRESERVED`;
- only ADR-015 closed invalidation reasons SHALL authorize reset/WARMUP;
- process restart alone SHALL NOT discard valid history; and
- authoritative-domain acknowledgements from bars/ATR owner, Executor, Trade Manager, and Entry Agent SHALL match before Listener Supervisor `REHYDRATING` closes; Command Center supplies no acknowledgement to that transition.

### 9.3 Cold startup

- recover the highest verified durable completed-bar/RMA authority;
- reconcile session, contract, bar, supervisor generation, and listener epoch;
- use REHYDRATING during exact reconstruction;
- WARMUP remains nonready and becomes terminal failure at the startup deadline;
- shared recent-bar/ATR/health projection SHALL NOT be sole or supplemental authority; and
- record recovery source, last bar, included count, value, continuity/reset disposition, and identity set.

## 10. Real public TradingView delivery and sender authority

The readiness delivery SHALL be externally originated after Ngrok route activation and after `startup_started_at_utc`. It SHALL traverse the public HTTPS hostname, Trade Manager relay, and Entry receiver. One receipt ID and exact payload hash SHALL join all three hop records. This establishes route traversal only.

The relay SHALL record public host, tunnel/startup attempt identity, ingress time, forwarded time, receiver acknowledgement time, source timestamp/version when supplied, payload hash, and sender-authentication result reference without logging credentials. The Entry diagnostic receipt channel SHALL remain noncanonical unless the payload independently satisfies session eligibility and sender authentication and is processed as the authorized real ADR-014 candidate.

A local client request to the public URL, loopback request, startup helper self-probe, replayed prior receipt, or user-agent string alone SHALL NOT satisfy this state.

The 2026-07-17 production trust boundary is explicitly insufficient for sender authentication: Trade Manager receives unauthenticated JSON, records public-route metadata (`Host`, source address as observed through the relay, user-agent, receipt time), and forwards it locally; Entry Agent validates/normalizes content but verifies no signature, authenticated principal, nonce, or sender-bound replay token. The approved public route can be correlated only from tunnel/host/relay/Entry evidence; it does not prove the TradingView sender. Payload timestamp/session fields are self-asserted and may be absent, at which point receiver time is only observation time. Existing same-session lock behavior limits some duplicate effects but does not prevent first-candidate injection or precommit replay.

No authentication mechanism is selected by this startup contract. Until a separate approved security decision resolves `DEBT-2026-07-17-016` and implements the authority consumed by `WEBHOOK_SENDER_AUTHORITY_VERIFIED`, startup SHALL fail both `ZERO_BLOCKING_PRODUCTION_DEBT` and `WEBHOOK_SENDER_AUTHORITY_VERIFIED`, then terminate `FAILED` with `BLOCKING_PRODUCTION_DEBT` and `WEBHOOK_SENDER_AUTHENTICATION_UNAVAILABLE`. Current production therefore cannot reach `READY_LOCKED`. This blocks production readiness/trading but does not alter ADR-014's internal atomic rollover semantics.

## 11. Terminal evaluation and reporting

At or before the absolute deadline, the evaluator SHALL write exactly one terminal record.

`READY_LOCKED` requires:

- every mandatory startup row in section 6 is positively proven; section 6.2 `TRADING_PERMITTED` is explicitly excluded;
- the applicable blocking production-debt count is exactly zero;
- Executor and Listener Supervisor exclusive authorities are established under the current startup attempt;
- the listener epoch, session commit, canonical ATR, and canonical frozen ladder are current and mutually coherent;
- authenticated TradingView sender identity is verified for the committed payload;
- NQ and YM each have one coherent current identity set;
- no unresolved pending/fenced/ambiguous lifecycle incident;
- no degraded/diverged/corrupt authority;
- Command Center production projection equality;
- Executor and Trade Manager reconciliation; and
- production entry lock engaged.

The terminal evaluator SHALL NOT read, request, or infer `TRADING_PERMITTED`. It SHALL record `READY_LOCKED` with the entry lock engaged and then terminate the bounded startup transaction. Any later trading decision is a separate authority transaction under section 6.2.

`COMMAND_CENTER_ALIGNED` is evaluated only after the authoritative domain states it displays have reached their own required states. Its pass/fail result MAY satisfy or fail the bounded observational startup parity requirement, but it SHALL NOT change, close, cancel, fence, authorize, repair, or veto any underlying Listener Supervisor, health, session, ATR, recovery, or trade authority state. The terminal evaluator compares projection output to canonical owner evidence; it does not promote projection content into authority.

`FAILED` SHALL include:

- startup attempt/policy/build/config identities;
- terminal time and elapsed time;
- failed component/state/symbol;
- exact missing or contradictory proof;
- last observed authority identities;
- timeout, integrity, authentication, persistence, or dependency reason;
- processes/ports left running or stopped; and
- evidence locations.

The launcher SHALL stop polling after terminal record, SHALL NOT print aggregate success for healthy subsets, and SHALL NOT restart a failed component without a new durable incident and separately authorized retry.

## 12. Manual startup and operational restart

Manual startup SHALL invoke the same owner commands, startup attempt schema, deadlines, dependency order, validation methods, and terminal evaluator. Direct shell start of the listener or bridge SHALL NOT be a conforming manual start.

Manual full-listener restart SHALL use ADR-015 `MANUAL_OPERATOR_RESTART` and SHALL NOT bypass supervisor generation, incident, fence, execution identity, epoch grant, rehydration, or acknowledgement.

Manual bridge recycle SHALL use the ADR-016 durable bridge incident/fence transaction and one current-generation execution identity. Direct child termination does not authorize a replacement.

## 13. Failure containment

- Persistence SHALL NOT be cleared, copied, or manually advanced to satisfy a probe.
- Shared health projection SHALL NOT drive health or any underlying domain-readiness fact. Command Center projection MAY affect only the separate observational `COMMAND_CENTER_ALIGNED` gate under section 11 and SHALL NOT create an underlying proof.
- One healthy symbol SHALL NOT mask the other symbol's blocker.
- A process/authority ambiguity SHALL prevent a second start.
- External exposure SHALL NOT imply backend or trading readiness.
- Startup failure SHALL preserve current execution/protective-order truth under its owners.
- Any failure after Ngrok exposure SHALL keep the entry lock engaged and report the exposed route in terminal evidence.

## 14. Controlled shutdown

Shutdown SHALL:

1. engage/confirm entry block;
2. reconcile active execution/trade state;
3. record planned shutdown intent in Supervisor/health authority;
4. stop external delivery/ngrok;
5. stop Entry Agent/Trade Manager intake as governed;
6. command Listener Supervisor to fence and stop listener/bridge;
7. stop Executor and remaining services;
8. stop Listener Supervisor last; and
9. verify process identities and ports clear and preserve evidence.

Planned absence SHALL NOT be classified as bridge/listener death or trigger automatic restart. Broad Python termination is prohibited as a normal operation.

## 15. Current implementation conflicts

The following are nonconforming implementation evidence only and are not modified by this draft:

- `launch_all.ps1` directly starts the listener, reads shared feed-health JSON, and can accept a local public self-probe;
- `run_system.ps1` broadly terminates Python and directly starts the listener;
- Executor directly performs listener restart and allocates listener generations;
- current GET routes perform lifecycle/reconciliation mutations; and
- current health control lacks ADR-016 transport/store/fence semantics.

No existing launcher behavior is grandfathered as readiness authority.

## 16. Required verification

Verification SHALL cover every state row positively and negatively, including:

- process/endpoint evidence insufficient by itself;
- corrupt/missing/stale/prior-session/prior-epoch/test-projection cases;
- all three control-store recovery outcomes;
- Pattern A Runtime Authority Control Database table-writer/foreign-key/identity verification and proof that no separate supervisor or health identity store is consulted;
- `SHARED_FEED_POLICY_VALID` positive proof and every `SHARED_FEED_POLICY_INVALID` no-start/no-restart/restart-survival/corrected-version case;
- current supervisor/epoch/generation grants and duplicate ambiguity;
- NQ/YM connection, subscription, tick, downstream delivery, bars, and ATR proofs;
- canonical ATR latest-finalized-bar equality, current session/contract/epoch/recovery identity, closed disposition, stale-cache rejection, and every valid/invalid no-new-finalized-bar continuity condition in section 6.1;
- zero-applicable-blocking-debt proof, including explicit `DEBT-2026-07-17-016` failure while unresolved;
- positive Executor authority, Listener Supervisor authority, current listener epoch, current session commit, canonical ATR, canonical frozen-ladder, and authenticated-sender gates;
- WARMUP/REHYDRATING never satisfying READY;
- local self-probe/user-agent spoof versus real external TradingView delivery;
- public-route proof versus sender-identity authentication, including unavailable authority, identity/hash mismatch, missing/self-asserted timestamp, duplicate/replay ambiguity, and exact fail-closed terminal reason;
- health-store corruption detection, verified quarantine, quarantine failure, qualifying/nonqualifying restore, no-source recovery-required, reinitialization, migration, pre/post-activation rollback boundary, epoch/generation preservation, and audit failure;
- exact raw payload -> Entry ladder -> Command Center production parity;
- Command Center observational parity with proof that it cannot acknowledge or close Listener Supervisor `REHYDRATING` or supply health/session/lifecycle/recovery evidence;
- `HEALTH_TIME_AUTHORITY_DEGRADED` startup/runtime failure and recovery behavior;
- entry lock remaining engaged at `READY_LOCKED`;
- proof that `TRADING_PERMITTED` is absent from all startup prerequisite/evidence calculations, occurs only in a separately authorized post-start transaction, and cannot bypass debt/deployment/Bucket 0/Bucket 1 gates;
- each per-phase and absolute deadline;
- exactly one terminal result and no partial-success presentation;
- manual start through identical owner commands;
- failure after Ngrok exposure; and
- controlled shutdown during pending/fenced incidents.

## 17. Governance boundary

This draft is not canonical or approved. It changes no code, process, port, persistence, entry lock, or trading state. Production restart, deployment, and trading authorization remain prohibited until ADRs/specifications are approved, implementation and verification gates pass, traceability/debt are reconciled, and explicit authorization is granted.

Every normative clause in this draft is assigned a stable `STARTUP-REQ-###` identity with forward and reverse verification mapping in `Architecture/Audits/2026-07-17_ADR015_016_Clause_Traceability_Registry_DRAFT.md`. The external recovery matrix is a package-level index only and SHALL NOT substitute for that clause-level registry.
