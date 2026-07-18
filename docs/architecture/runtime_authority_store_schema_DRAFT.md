# Runtime Authority Store Schema and Typed Transaction Contract

Version: Draft 0.3 — Phase 3C1 normative remediation

Status: **DRAFT — NONCANONICAL — NOT APPROVED**

Implementation authorization: None

Runtime verification: Unauthorized and not performed

Governing status: ADR-014 is approved and unchanged. ADR-015 and ADR-016 are unapproved. The Entry Session Aggregate governed by ADR-014 is not stored in this database.

## 1. Normative artifact and boundary

This Markdown file is the explanatory normative contract. [`runtime_authority_store_schema_v2_DRAFT.sql`](runtime_authority_store_schema_v2_DRAFT.sql) is its mechanically executable normative DDL expansion and implementation reference. A conflict is a draft defect and fails review; neither file is production code or authorization to install a database.

The proposed store path is:

```text
%LOCALAPPDATA%\RandleRuntimeData\control\runtime_authority_v2.sqlite3
```

The path is resolved once to an absolute, nonsynchronized, non-reparse-point path and recorded in startup evidence. The store is the only durable authority store for supervisor, listener, bridge, health, subscription, termination, expectation, and recovery-control facts. Projection JSON, process memory, logs, status routes, Command Center, or a copied database cannot originate or restore authority.

One physical database does not merge logical ownership. The Runtime Authority Store Transaction Coordinator owns only connection setup, transaction serialization, writer-route checking, SQLite execution, rollback, commit, fsync, and readback. It cannot originate, evaluate, classify, grant, restore, or reinterpret a domain decision.

## 2. Executable database contract

| Item | Exact value |
|---|---|
| Schema identity | `RANDLE_RUNTIME_AUTHORITY_SCHEMA_V2` |
| Bootstrap identity | `RASTORE-BOOTSTRAP-V2` |
| `PRAGMA application_id` | `0x52484C54` (`1380469844`) |
| `PRAGMA user_version` | `2` |
| Minimum supported SQLite | `3.43.1` |
| Foreign keys | `ON` before any statement on every connection |
| Trusted schema | `OFF` |
| Recursive triggers | `ON` |
| Journal | `WAL` |
| Durability | `synchronous=FULL` |
| Busy timeout | `5000` ms |
| Encoding | UTF-8 |
| Read-only validation | URI `mode=ro`, then `query_only=ON`; no transaction/idempotency/metadata write |
| Mutating transaction start | `BEGIN IMMEDIATE` only for the healthy-store mutating envelope |

Every one of the 37 tables is `STRICT`. Every declared type is one of `INTEGER`, `REAL`, `TEXT`, `BLOB`, or `ANY`; this schema currently needs only `INTEGER` and `TEXT`. There are no declared aliases such as `UUID`, `SHA256`, `UTC`, `SEQ`, or `VERSION`.

Semantic normalization is column-specific SQL:

- UUID columns use a lowercase 36-character RFC-4122 layout, exact hyphen positions, hexadecimal-only payload, version nibble `1` through `5`, and variant nibble `8`, `9`, `a`, or `b`.
- SHA-256 columns use exactly 64 lowercase hexadecimal characters.
- UTC columns use exactly `YYYY-MM-DDTHH:MM:SS.ffffffZ`, fixed separators, terminal `Z`, and a non-NULL built-in `julianday(column)` result.
- Date columns use exactly `YYYY-MM-DD` and require `date(column)=column`.
- Boolean columns are `INTEGER` constrained to `0` or `1`.
- Sequence/version columns are `INTEGER` with the exact lower bound named on that column.
- JSON-bearing columns are `TEXT` and use built-in `json_valid(actual_column)` plus the exact required top-level type.

No check uses a placeholder parameter or an unregistered function.

## 3. Reproducible identities

### 3.1 Schema hash

`store_metadata.schema_hash` is SHA-256 of the schema block in the committed SQL artifact.

Canonicalization is exact:

1. Read the committed SQL file as UTF-8 without BOM.
2. Select bytes after the line `-- SCHEMA-HASH-BEGIN` and before the line `-- SCHEMA-HASH-END`; the marker lines and everything outside are excluded.
3. Convert CRLF or bare CR to LF.
4. Remove only trailing U+0020 spaces and U+0009 tabs from each selected line.
5. Preserve leading whitespace, token case, quoted text, comments inside the block, object order, and all other bytes.
6. Remove zero or more terminal LF characters and append exactly one LF.
7. Hash those UTF-8 bytes with SHA-256 and render 64 lowercase hexadecimal characters.

The block includes, in file order, all 37 `CREATE TABLE` definitions, inline primary/unique/check/foreign-key constraints, all 13 named partial unique indexes, and all 11 triggers. It excludes PRAGMAs, the surrounding DDL transaction, writer-registry data rows, and comments outside the block.

### 3.2 Writer-registry hash

`store_metadata.writer_registry_hash` covers exactly the active version-2 rows installed between `-- WRITER-REGISTRY-HASH-BEGIN` and `-- WRITER-REGISTRY-HASH-END`.

Query and serialization are exact:

```sql
SELECT registry_version, table_name, operation, writer_id,
       writer_contract_identity, coalesce(writer_build_hash,'-'),
       effective_transaction_sequence,
       coalesce(cast(retired_transaction_sequence AS TEXT),'-'), active
FROM writer_registry
WHERE registry_version=2 AND active=1
ORDER BY registry_version, table_name, operation, writer_id,
         effective_transaction_sequence;
```

Serialize each value as its SQLite text rendering, with no quoting, join the nine fields with one U+0009 tab, append one LF per row, concatenate without a header or terminal blank row, encode UTF-8, and SHA-256 hash to lowercase hexadecimal. Closed values prohibit tabs, LF, or CR. `NULL` build/retirement values serialize as `-`. Every active table/operation scope is included; no inactive, other-version, metadata, rowid, insertion-order, timestamp, or file-path value is included.

The SQL artifact byte hash is a separate provenance identity and is not substituted for either canonical hash.

## 4. Initial bootstrap; no predecessor migration

Repository-wide search found no exact approved version-1 SQL artifact and no approved version-1 schema SHA-256. The former `RASTORE-MIG-002` claim is removed. No predecessor hash is invented.

Phase 3C1 therefore defines the initial governed v2 bootstrap `RASTORE-BOOTSTRAP-V2` and typed operation `TX-STORE-BOOTSTRAP-V2`. Bootstrap requires a separately authenticated Recovery Authorization, Architecture Governance approval, Deployment Authorization, the exact committed SQL artifact hash, the exact schema hash, and the exact writer-registry hash. Those approvals do not currently exist.

An authorized bootstrap would construct a new candidate file in the target directory, execute the complete SQL, install one `store_metadata` row with a new store UUID and the computed hashes, run the complete read-only validation envelope, flush candidate and directory, append external `BOOTSTRAP_PREPARED` evidence, atomically replace an absent target, reopen read-only, repeat validation, then append `BOOTSTRAP_COMPLETED`. Failure before activation deletes no source; failure after activation preserves the candidate as failed evidence and leaves startup failed.

Any legacy, `user_version=1`, unknown-version, missing-hash, unidentified, or projection-derived store is quarantined. No positive listener, bridge, health, readiness, session, deployment, or trading authority may be imported from it. A future import or migration requires a separately governed artifact with exact predecessor file, commit, SHA-256, transformation, preservation rules, rollback boundary, and authorization. No migration transaction is present in this catalog.

## 5. Closed table inventory

The executable contract has 37 tables and 468 columns. The primary key, exact nullability, all column checks, uniques, foreign keys, actions, and deferrability are expressed in the SQL, not inferred from this summary.

| Group | Table | Primary key | Logical writer and permitted operation |
|---|---|---|---|
| Mechanical | `store_metadata` | `singleton_id` | Coordinator `INSERT`, `UPDATE` |
| Mechanical | `writer_registry` | `(registry_version,table_name,operation,effective_transaction_sequence)` | Coordinator `INSERT`, governed retirement-only `UPDATE` |
| Mechanical | `transaction_commits` | `transaction_id` | Coordinator `INSERT` |
| Mechanical | `idempotency_records` | `(transaction_type,idempotency_key)` | Coordinator `INSERT` |
| Identity | `supervisor_generations` | `supervisor_generation_id` | Supervisor Generation Writer `INSERT`, `UPDATE` |
| Identity | `supervisor_leases` | `lease_id` | Supervisor Generation Writer `INSERT`, `UPDATE` |
| Policy | `shared_feed_policies` | `policy_identity` | Listener Incident Writer `INSERT`, `UPDATE` |
| Reference | `active_contract_sessions` | `contract_session_ref_id` | Health Durable Writer `INSERT`, `UPDATE`; ADR-014 remains source authority |
| Identity | `listener_epochs` | `listener_epoch_id` | Listener Epoch Writer `INSERT`, `UPDATE` |
| Recovery | `recovery_transactions` | `recovery_transaction_id` | Recovery Transaction Writer `INSERT`, `UPDATE` |
| Listener | `listener_current` | `singleton_id` | Listener State Writer `INSERT`, `UPDATE` |
| Listener | `listener_state_transitions` | `listener_transition_id` | Listener State Writer `INSERT` |
| Listener | `listener_restart_incidents` | `restart_incident_id` | Listener Incident Writer `INSERT`, `UPDATE` |
| Listener | `listener_restart_incident_transitions` | `incident_transition_id` | Listener Incident Writer `INSERT` |
| Listener | `listener_restart_outcomes` | `listener_outcome_id` | Listener Incident Writer `INSERT` |
| Listener | `listener_fences` | `listener_fence_id` | Listener Incident Writer `INSERT` |
| Listener | `listener_execution_attempts` | `listener_execution_id` | Listener Incident Writer `INSERT`, `UPDATE` |
| Listener | `listener_rehydrations` | `listener_rehydration_id` | Listener Incident Writer `INSERT`, `UPDATE` |
| Acknowledgement | `recovery_required_domains` | `(recovery_transaction_id,authoritative_domain)` | Listener Acknowledgement Writer `INSERT` |
| Acknowledgement | `domain_acknowledgements` | `acknowledgement_id` | Listener Acknowledgement Writer `INSERT` |
| Bridge | `bridge_generations` | `bridge_generation_id` | Bridge Generation Writer only, `INSERT`, `UPDATE` |
| Bridge | `bridge_current` | `singleton_id` | Health Durable Writer `INSERT`, `UPDATE` |
| Bridge | `bridge_transitions` | `bridge_transition_id` | Health Durable Writer `INSERT` |
| Bridge | `bridge_incidents` | `bridge_incident_id` | Health Durable Writer `INSERT`, `UPDATE` |
| Bridge | `bridge_recycle_attempts` | `bridge_attempt_id` | Health Durable Writer `INSERT`, `UPDATE` |
| Bridge | `bridge_outcomes` | `bridge_outcome_id` | Health Durable Writer `INSERT` |
| Health | `producer_registrations` | `producer_instance_id` | Health Durable Writer `INSERT`, `UPDATE` |
| Health | `health_events` | `health_event_id` | Health Durable Writer `INSERT` |
| Health | `health_current` | `(health_dimension,scope_key)` | Health Durable Writer `INSERT`, `UPDATE` |
| Health | `health_transitions` | `health_transition_id` | Health Durable Writer `INSERT` |
| Health | `health_aggregate` | `singleton_id` | Health Durable Writer `INSERT`, `UPDATE` |
| Subscription | `subscription_verifications` | `subscription_verification_id` | Health Durable Writer `INSERT` |
| Termination | `termination_evidence` | `termination_evidence_id` | Health Durable Writer `INSERT` |
| Termination | `termination_results` | `termination_result_id` | Health Durable Writer `INSERT` |
| Expectation | `market_data_expectations` | `expectation_id` | Listener Incident Writer `INSERT`, `UPDATE` |
| Projection | `projection_cursors` | `(projection_name,scope_key)` | Projection Writer `INSERT`, `UPDATE`; no control authority |
| Store incident | `store_incidents` | `store_incident_id` | Store Incident Writer `INSERT`, `UPDATE` |

No `DELETE` route is active. Deletion is prohibited by the typed-plan authorizer; aggregate-child `ON DELETE CASCADE` actions are defined only so a separately approved candidate-construction rollback cannot create orphans. They do not authorize runtime deletion.

## 6. Foreign-key contract

The SQL contains 115 explicit foreign-key declarations and 117 child-column mappings because two composite declarations each map two columns. Every declaration names exact child column(s), parent table and column(s), `ON UPDATE`, `ON DELETE`, and any deferrability. Child nullability is declared on the child column. Every parent is a primary key or inline unconditional `UNIQUE` key; no FK targets a partial index, undefined column, or nonunique identity.

Action totals are:

| Action | Declaration count | Lifecycle reason |
|---|---:|---|
| `ON UPDATE RESTRICT` | 114 | Durable identity keys never change |
| `ON UPDATE CASCADE` | 1 | Composite health dimension/scope key remains internally coupled if a separately governed candidate transform renames the pair |
| `ON DELETE RESTRICT` | 102 | Identity/evidence parents cannot disappear while authoritative children exist |
| `ON DELETE CASCADE` | 13 | Incident/recovery aggregate children cannot be orphaned during pre-activation candidate rollback; runtime deletion remains unauthorized |

Fifty declarations are `DEFERRABLE INITIALLY DEFERRED` where transaction-commit/current-pointer or mutually linked history rows must be inserted atomically. Sixty-five are immediate where the parent must already exist. Representative insertion order is: transaction identity as required by the typed envelope; supervisor generation; policy/session references; listener epoch; bridge generation; incident/recovery parent; event/history/outcome child; current-pointer update; transaction completion/readback. Deferred cycles exist only inside one atomic aggregate and do not require an impossible committed intermediate state.

The executable SQL is the per-FK inventory: each `FOREIGN KEY ... REFERENCES ... ON UPDATE ... ON DELETE ...` clause is normative. `PRAGMA foreign_key_list(table)` must reproduce all 117 mappings; `PRAGMA foreign_key_check` must return zero rows.

## 7. Writer routing and exclusivity

The closed operation vocabulary is `INSERT`, `UPDATE`, `DELETE`. The v2 registry installs 59 active table/operation rows and 11 writer identities. Each row binds registry version, table, operation, writer identity, writer contract identity, optional deployment build hash, effective transaction sequence, retirement sequence, and active flag.

`uq_writer_registry_active_scope` is exactly:

```sql
CREATE UNIQUE INDEX uq_writer_registry_active_scope
ON writer_registry(table_name,operation)
WHERE active=1;
```

It is impossible for two writer identities to own the same active table/operation scope. The old active row must be retired in a healthy `BEGIN IMMEDIATE` registry-change transaction by changing only `active:1->0` and setting `retired_transaction_sequence>=effective_transaction_sequence`; `trg_writer_registry_update_guard` rejects every other update and `trg_writer_registry_delete_guard` rejects deletion. Only after retirement may one successor row activate at a later effective sequence. Registry hash and `store_metadata.writer_registry_hash` change atomically. Any scope or build change requires governance and deployment authorization; neither exists now.

Before a domain mutation, the Coordinator's exact typed-plan precondition is:

1. one current verified metadata row names schema v2 and active registry version/hash;
2. request names transaction type, authority-decision ID, idempotency key, request hash, expected versions, evidence-set hash, and writer set;
3. every `(table,operation,writer_id)` exists exactly once among active version-2 rows and is effective at the proposed next transaction sequence;
4. every writer is in the transaction's exact closed writer set below;
5. no requested `DELETE` scope exists; and
6. writer build hash equals the deployment-bound row when a build hash is non-NULL.

Failure returns `WRITER_ROUTING_REJECTED`, changes no domain row, and cannot be reinterpreted by the Coordinator.

## 8. Partial unique indexes and triggers

The 13 partial unique indexes are the exact SQL definitions for: writer table/operation ownership; one current supervisor generation; one held lease per generation and globally; one active valid policy; one current contract session per symbol; one current listener epoch; one open listener recovery per epoch; one open bridge recovery per generation; one positive acknowledgement per recovery/domain; one current bridge generation per listener epoch; one positive subscription verification per symbol/session/bridge generation; and one current market-data expectation per symbol/epoch.

The 11 constraint-only triggers are:

| Trigger | Exact effect |
|---|---|
| `trg_writer_registry_update_guard` | permits only the exact active-to-retired update |
| `trg_writer_registry_delete_guard` | prohibits registry deletion |
| `trg_idempotency_records_immutable` | rejects changed-input/result updates as `IDEMPOTENCY_CONFLICT` |
| `trg_listener_state_transitions_legal` | enforces the closed listener transition relation, including `STOPPING -> STOPPED` |
| `trg_listener_current_insert_match` | requires initial current row to match its exact transition/version/transaction |
| `trg_listener_current_update_match` | requires `old.version+1` and exact prior/result/current transition match |
| `trg_listener_restart_incidents_terminal_match` | requires a terminal incident to point to its own same-transaction outcome row |
| `trg_domain_acknowledgements_required_match` | requires required-domain, supervisor-generation, listener-epoch, and expected-identity equality |
| `trg_subscription_verifications_proof` | permits positive subscription proof only from authenticated current identities and a `RITHMIC_LISTENER` `SUBSCRIPTION_PROOF` event |
| `trg_health_aggregate_exact_state` | enforces exact five-row aggregate derivation on insert |
| `trg_health_aggregate_update_state` | enforces exact five-row aggregate derivation on update |

Triggers only abort; none creates, mutates, classifies, or repairs another domain row.

## 9. Separate operation envelopes

### 9.1 Healthy-store mutating transaction

Applicable only to the listener, bridge, health, policy, expectation, projection, stale-lease, store-incident, and healthy-store version-conflict operations listed below.

The Coordinator verifies schema/registry, writer routes, authority decision, parents, expected versions, request hash, and existing idempotency record; begins `BEGIN IMMEDIATE`; applies exactly the named rows; inserts one `transaction_commits` row and one `COMMITTED` idempotency row; advances metadata cursor; commits; opens a separate read-only connection; and verifies result rows, cursor, hashes, and FK state. Pre-commit failure rolls back all writes. A commit with failed readback returns `COMMIT_UNKNOWN`, permits no duplicate action, and is reconstructed by transaction/idempotency identity before retry. Same key/same request returns the stored result; same key/different request returns `IDEMPOTENCY_CONFLICT` without a write.

### 9.2 Read-only validation

`TX-STORE-VALIDATE` is an operation identity, not a database transaction. It opens URI `mode=ro`, sets `query_only=ON`, verifies path, SQLite version, PRAGMAs, metadata/hash/registry identity, normalized schema, `quick_check=ok`, zero FK rows, indexes, triggers, current uniqueness, sequence, parentage, current/history versions, acknowledgements, subscription ownership, bridge writer, and unresolved recovery state. It writes no metadata, transaction, idempotency, or domain row. Result is `VERIFIED_CURRENT`, `RECOVERY_REQUIRED`, or `FAILED` returned to the caller and, when needed, recorded only by the external evidence writer.

### 9.3 Corrupt-store quarantine

`TX-STORE-QUARANTINE` never opens the corrupt database read-write and never depends on a write to it. After all handles close, the Recovery Controller moves the database and existing WAL/SHM as one identity set into the exact quarantine directory, hashes and flushes them, and the external evidence writer records `QUARANTINE_PREPARED` then `QUARANTINE_COMPLETED`. Failure preserves source/partial evidence and startup remains failed.

### 9.4 Restore and reinitialization

`TX-STORE-RESTORE` requires the exact authorized backup/store UUID/schema/hash/cursor and external authorization. It copies to a new candidate, validates source and candidate read-only, writes `RESTORE_PREPARED`, flushes, atomically replaces the quarantined/absent target, reopens read-only, then writes `RESTORE_COMPLETED`. Until completion, startup is failed. A pre-replacement failure leaves the target untouched; a post-replacement failure restores the preactivation target only when no v2 commit occurred, otherwise quarantines the candidate and fails closed.

`TX-STORE-REINITIALIZE` requires explicit acknowledgement that authority/history is unavailable. It constructs a new UUID store, creates no positive imported authority, initializes only `SUPERVISOR_STORE_FAILED`, the five nonpositive health rows, `HEALTH_CORRUPT`, and one open `RECOVERY_REQUIRED` incident after independently reconciling process state. It records prepared/completed external evidence. It cannot create an epoch, bridge, positive subscription, readiness, deployment, or trading fact.

### 9.5 Version-conflict rejection

`TX-STORE-VERSION-CONFLICT-REJECT` writes one `REJECTED_VERSION` idempotency row inside an already verified healthy store only when writer routing and the request/idempotency identities are themselves valid. It changes no domain row and inserts no `transaction_commits` row. If store health or routing is unverified, it returns `VERSION_CONFLICT` without changing the database and the external writer may record `VERSION_CONFLICT_OBSERVED`; that external evidence has no authority effect.

### 9.6 Initial bootstrap and future migration

`TX-STORE-BOOTSTRAP-V2` uses the file-level envelope in section 4. No approved predecessor or migration exists. A future schema migration must have its own privileged ID, exact predecessor artifact/commit/hash, source read-only verification, deterministic candidate transform, preservation rules, external prepared/completed evidence, atomic replacement, pre-first-commit rollback boundary, and fail-closed result. It cannot be routed through a normal domain transaction.

## 10. Runtime Authority Recovery Evidence Writer

Name: `Runtime Authority Recovery Evidence Writer`.

Owner: Runtime Operations Recovery Controller. Authorization source: an authenticated Recovery Authorization naming record type, incident, store identity/hash, actor, expiry, Architecture Governance approval, and Deployment Authorization. The writer validates this authorization but owns none of those decisions.

Exact artifact path:

```text
%LOCALAPPDATA%\RandleRuntimeData\control\evidence\runtime_authority_recovery_evidence_v1.jsonl
```

It is a logical append-only UTF-8 JSON Lines hash chain. Each canonical JSON object has sorted Unicode code-point keys, no insignificant whitespace, LF termination, integers in shortest decimal form, and no floating-point values. Required fields are `record_version=1`, `sequence` starting at 1 and increasing by 1, `record_type`, `record_id`, `incident_id`, `startup_attempt_id`, `authorization_id`, `actor_id`, `occurred_at_utc`, `store_path`, `store_uuid` or `UNKNOWN`, `schema_identity` or `UNKNOWN`, `schema_hash` or `UNKNOWN`, `input_artifacts` ordered by normalized absolute path with length/SHA-256, `output_artifacts` in the same form, `validation_result`, `previous_record_sha256`, and `record_sha256`.

`record_sha256` is SHA-256 of the canonical object with `record_sha256` omitted. Sequence 1 uses 64 zeroes for `previous_record_sha256`; later rows use the preceding record hash. Closed record types are `BOOTSTRAP_PREPARED`, `BOOTSTRAP_COMPLETED`, `BOOTSTRAP_FAILED`, `QUARANTINE_PREPARED`, `QUARANTINE_COMPLETED`, `QUARANTINE_FAILED`, `RESTORE_PREPARED`, `RESTORE_COMPLETED`, `RESTORE_FAILED`, `REINITIALIZE_PREPARED`, `REINITIALIZE_COMPLETED`, `REINITIALIZE_FAILED`, `MIGRATION_PREPARED`, `MIGRATION_COMPLETED`, `MIGRATION_FAILED`, and `VERSION_CONFLICT_OBSERVED`.

There is one writer process under an exclusive evidence-file lock. It reads and verifies the complete existing chain, creates a same-directory `.<record_id>.tmp` with the verified prior bytes plus exactly one line, flushes the file, atomically replaces the log with write-through semantics, flushes the containing directory, reopens read-only, and verifies length and final hash. Interrupted temp files are nonauthoritative and are retained as evidence; restart resumes only from the last verified log and never skips a sequence. An unwritable or invalid chain fails recovery before activation.

At startup the Store Integrity Classifier consumes the verified chain to detect prepared-without-completed operations, unresolved quarantine, failed activation, and target/hash mismatch. Any unresolved item blocks `CONTROL_STORES_VERIFIED` and `SUPERVISOR_AUTHORITY_READY`. The evidence writer may record recovery facts; it may not decide listener lifecycle, session rollover, bridge lifecycle, health, readiness, deployment, or trading, and its records never create positive authority.

## 11. Closed typed-transaction catalog

There are exactly 37 operation IDs. Thirty-four are permitted `transaction_commits.transaction_type` values. `TX-STORE-VALIDATE` is read-only, `TX-STORE-QUARANTINE` is external-only, and `TX-STORE-VERSION-CONFLICT-REJECT` writes at most a rejected idempotency row with NULL `transaction_id`; the SQL deliberately excludes those three from `transaction_commits`. Every mutating request supplies authority-decision ID, writer set, exact record identities, source/destination state, parent identities, expected versions, idempotency key, canonical request hash, evidence-set hash, and deployment-bound writer identities. The common success/failure/crash/retry/reconstruction rules are section 9; the row below closes transaction-specific authority, writers, records, transition, and result.

| ID | Exact authority; writer set | Exact records and transition; success result |
|---|---|---|
| `TX-LSN-CANCEL` | Listener Supervisor State Evaluator; Listener Incident + Listener State Writers | Pending incident -> terminal `RESTART_CANCELED`; outcome row; listener `SUSPECT -> HEALTHY` or `SUSPECT -> SUSPECT` only from enumerated reevaluation; current/history/version rows; `RESTART_CANCELED` |
| `TX-LSN-FENCE` | Listener Supervisor State Evaluator; Listener Incident + Listener State Writers | incident `RESTART_PENDING -> RESTART_FENCED`; one fence; listener `SUSPECT -> FENCED`; `RESTART_FENCED` |
| `TX-LSN-EXECUTION-START` | Listener Supervisor State Evaluator; **Listener Incident Writer** | one `listener_execution_attempts` row and incident `RESTART_FENCED -> RESTART_EXECUTING`; no state-writer row; `EXECUTION_STARTED` |
| `TX-LSN-REHYDRATION-START` | Listener Supervisor State Evaluator; Listener Incident + Recovery Transaction + Listener Acknowledgement + Listener State Writers | incident/execution -> `RESTART_REHYDRATING`; listener -> `REHYDRATING`; open recovery/rehydration and exact five required-domain rows; `REHYDRATION_STARTED` |
| `TX-LSN-ACK` | Listener Supervisor State Evaluator after Health Ingress validation; Listener Acknowledgement + Listener Incident Writers | one accepted/rejected acknowledgement; accepted identity/generation match; monotonic rehydration progress; `ACK_RECORDED` |
| `TX-LSN-COMPLETE` | Listener Supervisor State Evaluator; Listener Incident + Recovery Transaction + Listener State Writers | all five positive acknowledgements; incident -> terminal `RESTART_COMPLETED`; recovery/rehydration -> `COMPLETED`; listener `REHYDRATING -> HEALTHY`; `RESTART_COMPLETED` |
| `TX-LSN-FAIL` | Listener Supervisor State Evaluator; Listener Incident + optional Recovery Transaction + Listener State Writers | current nonterminal incident -> terminal `RESTART_FAILED`; open recovery -> `FAILED`; listener exact current state -> `LISTENER_FAILED`; `RESTART_FAILED` |
| `TX-LSN-RATE-EXHAUSTED` | Listener Supervisor State Evaluator; Listener Incident + optional Recovery Transaction + Listener State Writers | eligible current incident -> terminal `RECOVERY_RATE_LIMITED_FAILED`; required rate evidence; retry prohibited; listener deterministically -> `LISTENER_FAILED`; `RECOVERY_RATE_LIMITED_FAILED` |
| `TX-LSN-PLANNED-STOP` | Listener Supervisor State Evaluator; Listener State Writer | `STARTING`, `REHYDRATING`, `HEALTHY`, `SUSPECT`, `FENCED`, or `LISTENER_FAILED` -> `STOPPING`; transition/current/version; `STOPPING` |
| `TX-LSN-STOP-COMPLETE` | Listener Supervisor State Evaluator using authenticated process-stop/handle-release and epoch-fence evidence; Listener State Writer | **`STOPPING -> STOPPED`**; one transition, `listener_current` version+1, NULL epoch/current incident/recovery, transaction/idempotency; duplicate returns same result; precommit crash leaves `STOPPING`; postcommit crash reconstructs `STOPPED`; `STOPPED` |
| `TX-STORE-VALIDATE` | Store Integrity Classifier; no database writer | read-only section 9.2; no records; `VERIFIED_CURRENT`, `RECOVERY_REQUIRED`, or `FAILED` |
| `TX-STORE-QUARANTINE` | Recovery Authorization; Runtime Authority Recovery Evidence Writer only | external section 9.3; corrupt DB unchanged by writer; `QUARANTINED` or `QUARANTINE_FAILED` |
| `TX-STORE-RESTORE` | Recovery + Governance + Deployment authorizations; Recovery Evidence Writer and mechanical Recovery Controller | external/candidate section 9.4; validated atomic replacement; `RESTORED` or fail closed |
| `TX-STORE-REINITIALIZE` | same three authorizations plus loss acknowledgement; Recovery Evidence Writer and mechanical Recovery Controller | new negative-only store described in 9.4; `REINITIALIZED_FAIL_CLOSED` |
| `TX-STORE-VERSION-CONFLICT-REJECT` | mechanical expected-version comparison; Coordinator only in a healthy store | no domain or commit row; one immutable `REJECTED_VERSION` idempotency row when safe; otherwise no DB write; `VERSION_CONFLICT` |
| `TX-STORE-STALE-LEASE-FENCE` | Supervisor lease evaluator; Supervisor Generation Writer | current stale lease/generation -> `FENCED`; no domain inference; `LEASE_FENCED` |
| `TX-STORE-INCIDENT` | affected-domain classifier; Store Incident Writer | one/open or terminal incident row and exact evidence; no classification by writer; `STORE_INCIDENT_RECORDED` |
| `TX-STORE-BOOTSTRAP-V2` | section 4 authorizations; Recovery Evidence Writer and mechanical Recovery Controller/Coordinator | new candidate, registry/metadata, validation, atomic first activation; no legacy import; `BOOTSTRAPPED_V2` |
| `TX-BRG-RECYCLE-PENDING` | Listener Supervisor State Evaluator; Health Durable Writer | bridge `BRIDGE_SUSPECT -> RECYCLE_PENDING`; incident/current/history/version; `RECYCLE_PENDING` |
| `TX-BRG-CANCEL` | State Evaluator; Health Durable Writer | pending incident -> terminal `RECYCLE_CANCELED`; bridge -> `RECYCLE_CANCELED`; outcome/history/current; `RECYCLE_CANCELED` |
| `TX-BRG-FENCE` | State Evaluator; Health Durable Writer | `RECYCLE_PENDING -> BRIDGE_FENCED`; incident/current transition; no generation allocation; `BRIDGE_FENCED` |
| `TX-BRG-EXECUTE` | State Evaluator; Health Durable Writer | `BRIDGE_FENCED -> RECYCLE_EXECUTING`; one numbered recycle attempt; `RECYCLE_EXECUTING` |
| `TX-BRG-REHYDRATE` | State Evaluator; Health Durable + Recovery Transaction Writers | `RECYCLE_EXECUTING -> BRIDGE_REHYDRATING`; open bridge recovery; `BRIDGE_REHYDRATING` |
| `TX-BRG-READY` | State Evaluator; Health Durable + Recovery Transaction Writers | authenticated current-generation recovery proof; bridge -> `BRIDGE_READY`; incident outcome `BRIDGE_READY`; recovery complete; `BRIDGE_READY` |
| `TX-BRG-FAIL` | State Evaluator; Health Durable + optional Recovery Transaction Writers | active incident -> terminal ordinary `BRIDGE_FAILED`; recovery fail; bridge `BRIDGE_FAILED`; `BRIDGE_FAILED` |
| `TX-BRG-EXHAUSTED` | State Evaluator; Health Durable + optional Recovery Transaction Writers | exact count/deadline evidence; incident -> terminal `FAILED_RECOVERY_EXHAUSTED`; retry prohibited; `FAILED_RECOVERY_EXHAUSTED` |
| `TX-BRG-GRANT` | State Evaluator; **Bridge Generation Writer only** | prior current generation fenced/retired, one successor `GRANTED/CURRENT`; no Health Durable write to `bridge_generations`; `BRIDGE_GENERATION_GRANTED` |
| `TX-BRG-PLANNED-SHUTDOWN` | State Evaluator; Health Durable Writer | bridge -> `PLANNED_SHUTDOWN`; exact termination evidence/outcome; `PLANNED_SHUTDOWN` |
| `TX-BRG-EPOCH-TRANSITION` | State Evaluator; Health Durable + Bridge Generation Writers | old generation -> `FENCED/RETIRED`, bridge -> `LISTENER_EPOCH_TRANSITION`; no recycle alias; `LISTENER_EPOCH_TRANSITION` |
| `TX-HEALTH-EVENT` | Health Ingress authentication/validation; Health Durable Writer | one authenticated/rejected `health_events` row; vocabulary excludes `SUBSCRIPTION_VERIFIED`; `HEALTH_EVENT_RECORDED` |
| `TX-HEALTH-DIMENSION-UPDATE` | State Evaluator; Health Durable Writer | one dimension transition/current version plus exact five-row aggregate; `HEALTH_DIMENSION_UPDATED` |
| `TX-SUBSCRIPTION-VERIFY` | State Evaluator after Health Ingress; Health Durable Writer | `SUBSCRIPTION_VERIFIED` is written **only** to `subscription_verifications`; any resulting health change is a separate `TX-HEALTH-DIMENSION-UPDATE`; `SUBSCRIPTION_VERIFIED` or `REJECTED` |
| `TX-TERMINATION-EVIDENCE` | Health Ingress; Health Durable Writer | one authenticated/rejected termination evidence row; `TERMINATION_EVIDENCE_RECORDED` |
| `TX-TERMINATION-CLASSIFY` | State Evaluator; Health Durable Writer | one field-complete generation result with concrete/`NONE`/`UNKNOWN` values and evidence hashes; `TERMINATION_CLASSIFIED` |
| `TX-EXPECTATION-EVALUATE` | Market Data Expectation Evaluator; Listener Incident Writer | close prior current expectation and insert exact successor for symbol/epoch; `EXPECTATION_EVALUATED` |
| `TX-POLICY-VALIDATE` | Listener Supervision Policy Evaluator; Listener Incident Writer | immutable policy validation and optional active successor; `POLICY_VALID` or `SHARED_FEED_POLICY_INVALID` |
| `TX-PROJECTION-CURSOR` | Projection Publisher; Projection Writer | projection cursor only after source commit; no control/readiness effect; `PROJECTION_RECORDED` |

For every row, missing parent returns `MISSING_PARENT`; expected-version mismatch follows the version-conflict envelope; constraint failure returns `CONSTRAINT_REJECTED`; routing failure returns `WRITER_ROUTING_REJECTED`; commit ambiguity returns `COMMIT_UNKNOWN`. A retry never changes inputs under the same idempotency key. Reconstruction uses the committed transaction/idempotency row plus exact current/history/parent identities, never process existence or projection state.

## 12. Closed listener transitions and acknowledgements

The SQL trigger is the executable listener transition relation. It includes initialization and recovery paths plus exact `STOPPING -> STOPPED`. Every unlisted pair aborts with `LISTENER_TRANSITION_PROHIBITED`. ADR-015 remains the explanatory owner of the same relation.

A positive acknowledgement requires one `recovery_required_domains` parent, the same recovery transaction, supervisor generation, listener epoch, authoritative domain, and expected/observed identity. `uq_domain_ack_positive` permits only one accepted row per recovery/domain. Wrong-generation and identity mismatch abort. Rejected evidence may be retained but cannot advance progress.

`RECOVERY_RATE_LIMITED_FAILED` is a terminal row in `listener_restart_outcomes`, must be referenced by the terminal incident's `current_outcome_id`, requires rate evidence and retry prohibition, and deterministically produces listener state `LISTENER_FAILED`.

## 13. Startup reconstruction

Startup first performs the read-only validation envelope and external recovery-chain verification. Reconstruction then requires, in order:

1. exact schema v2, schema hash, registry version 2/hash, PRAGMAs, 37 tables, 468 columns, 115 FK declarations/117 mappings, 13 partial unique indexes, and 11 triggers;
2. exactly one valid current supervisor generation/lease and contiguous transaction cursor;
3. exactly one `listener_current`, its exact last transition/version, current epoch ancestry when non-NULL, and no prohibited transition;
4. exact current/open listener incident, terminal outcome relationship, execution, recovery, and acknowledgement set;
5. exact bridge generation written by Bridge Generation Writer, bridge current/history/incident/outcome ancestry;
6. exact producer/event identity, five dimension rows, derived aggregate, per-symbol current session reference and positive subscription rows;
7. no open corruption/schema/routing/recovery incident and no prepared-without-completed external recovery evidence; and
8. projection cursors considered only for parity and never for restoration.

Any mismatch yields `RECOVERY_REQUIRED` or `FAILED`, blocks listener/bridge start and readiness, and creates no positive authority.

## 14. Verification and governance boundary

Phase 3C1 isolated validation must execute the SQL only against a temporary database; introspect every table/column/key/FK/action/index/trigger; run `quick_check` and `foreign_key_check`; exercise every trigger, writer conflict, valid/invalid transition, `STOPPING -> STOPPED`, acknowledgement uniqueness/generation, subscription ownership, bridge writer, idempotency conflict, rollback/readback, missing parent, both canonical hashes, and corrupt-store external quarantine without a corrupt-store write.

Those are document/schema validation exercises only. They are not production implementation, runtime verification, deployment, readiness, or trading authorization. Full semantic clause-to-scenario traceability is intentionally deferred to Phase 3C2 and is not approval-ready. Phase 3C2 may use only hashes accepted by an independent Phase 3C1 review.
