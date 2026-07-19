# Runtime Authority Store Schema and Typed Transaction Contract

Version: Draft 0.5 — Phase 3C1-R2 F6 targeted normative remediation

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

Every one of the 40 tables is `STRICT`. Every declared type is one of `INTEGER`, `REAL`, `TEXT`, `BLOB`, or `ANY`; this schema currently needs only `INTEGER` and `TEXT`. There are no declared aliases such as `UUID`, `SHA256`, `UTC`, `SEQ`, or `VERSION`.

Semantic normalization is column-specific SQL:

- UUID columns use a lowercase 36-character RFC-4122 layout, exact hyphen positions, hexadecimal-only payload, version nibble `1` through `5`, and variant nibble `8`, `9`, `a`, or `b`.
- SHA-256 columns use exactly 64 lowercase hexadecimal characters.
- UTC columns use exactly `YYYY-MM-DDTHH:MM:SS.ffffffZ`, ASCII digits and separators, Gregorian year 0001 through 9999, calendar-valid month/day with the exact Gregorian leap rule, hour 00–23, minute/second 00–59 (leap second 60 is prohibited), and exact built-in `strftime` round-trip equality.
- Date columns use exactly `YYYY-MM-DD`, ASCII digits and separators, Gregorian year 0001 through 9999, calendar-valid month/day with the exact Gregorian leap rule, and exact built-in `strftime` round-trip equality.
- Boolean columns are `INTEGER` constrained to `0` or `1`.
- Sequence/version columns are `INTEGER` with the exact lower bound named on that column.
- JSON-bearing columns are `TEXT` and use built-in `json_valid(actual_column)` plus the exact required top-level type.

All normalization checks are closed built-in SQLite expressions. The F6 result/evidence integrity triggers additionally call `randle_sha256_hex_utf8(TEXT)`. The Coordinator SHALL register that one-argument function on every schema-creation, mutating, validation, startup-proof, restore, reinitialization, and bootstrap connection before executing schema SQL: input is a non-NULL SQLite `TEXT` value; the function hashes the exact UTF-8 bytes of that value with SHA-256; output is 64 lowercase hexadecimal ASCII characters. Registration SHALL use `SQLITE_UTF8 | SQLITE_DETERMINISTIC | SQLITE_INNOCUOUS`; it performs no I/O, reads no connection or locale state, and has no side effects. With `trusted_schema=OFF`, absence, NULL input, or a wrong result fails the preliminary empty-string call; the permanent schema-owned `randle_sha256_preflight_v` query fails a non-innocuous registration. Schema construction queries that view before COMMIT, and every read-only startup/validation connection SHALL query it again; any failure is closed.

## 3. Reproducible identities

### 3.1 Schema hash

`store_metadata.schema_hash` is SHA-256 of the schema block in the committed SQL artifact.

Phase 3C1-R2 published value: `c3d60c3c943958a588ff744467c4eca56063851bfe0288054dba6f08ca5bfc2a`.

Canonicalization is exact:

1. Read the committed SQL file as UTF-8 without BOM.
2. Select bytes after the line `-- SCHEMA-HASH-BEGIN` and before the line `-- SCHEMA-HASH-END`; the marker lines and everything outside are excluded.
3. Convert CRLF or bare CR to LF.
4. Remove only trailing U+0020 spaces and U+0009 tabs from each selected line.
5. Preserve leading whitespace, token case, quoted text, comments inside the block, object order, and all other bytes.
6. Remove zero or more terminal LF characters and append exactly one LF.
7. Hash those UTF-8 bytes with SHA-256 and render 64 lowercase hexadecimal characters.

The block includes, in file order, all 40 `CREATE TABLE` definitions, the one schema-owned `randle_sha256_preflight_v` view, inline primary/unique/check/foreign-key constraints, all 13 named partial unique indexes, and all 21 triggers. It excludes PRAGMAs, the preliminary temporary-table UDF call, the surrounding DDL transaction, writer-registry data rows, and comments outside the block.

### 3.2 Writer-registry hash

`store_metadata.writer_registry_hash` covers exactly the active version-2 rows installed between `-- WRITER-REGISTRY-HASH-BEGIN` and `-- WRITER-REGISTRY-HASH-END`.

Phase 3C1-R2 published value: `906286388a8a8c95ee1ae09b6537e969b998f9008e37ed9aae734a85361d0f20`.

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

The committed SQL-artifact byte hash is a separate provenance identity and is not substituted for either canonical hash. Phase 3C1-R2 committed SQL SHA-256: `8b7bc314163b2fef65cb61221026ba6b962ff20797aa6be57f944c0dcd7ae4fc`.

## 4. Initial bootstrap; no predecessor migration

Repository-wide search found no exact approved version-1 SQL artifact and no approved version-1 schema SHA-256. The former `RASTORE-MIG-002` claim is removed. No predecessor hash is invented.

Phase 3C1 therefore defines the initial governed v2 bootstrap `RASTORE-BOOTSTRAP-V2` and typed operation `TX-STORE-BOOTSTRAP-V2`. Bootstrap requires a separately authenticated Recovery Authorization, Architecture Governance approval, Deployment Authorization, the exact committed SQL artifact hash, the exact schema hash, and the exact writer-registry hash. Those approvals do not currently exist.

An authorized bootstrap first verifies the external chain and appends `BOOTSTRAP_PREPARED`, whose `output_artifacts` is empty and whose validation result is `PREPARED`; that yields the immutable external sequence/hash referenced by the candidate recovery row and avoids a self-hash cycle. It then constructs a new candidate file in the target directory, executes the complete SQL, installs `store_metadata` with a new store UUID and the computed hashes, runs the complete read-only validation envelope, and flushes the candidate file with `FlushFileBuffers`. It performs the section 14.6 same-volume write-through move, reopens read-only, repeats validation, then appends `BOOTSTRAP_COMPLETED` with the activated artifact length/hash. It makes no directory-flush claim. Failure before activation appends `BOOTSTRAP_FAILED` and deletes no source; failure after activation preserves the candidate as failed evidence and leaves startup failed.

Any legacy, `user_version=1`, unknown-version, missing-hash, unidentified, or projection-derived store is quarantined. No positive listener, bridge, health, readiness, session, deployment, or trading authority may be imported from it. A future import or migration requires a separately governed artifact with exact predecessor file, commit, SHA-256, transformation, preservation rules, rollback boundary, and authorization. No migration transaction is present in this catalog.

## 5. Closed table inventory

The executable contract has 40 tables and 552 columns: 485 are `NOT NULL` and 67 are nullable. It has 40 primary keys covering 49 primary-key columns. The R2 tables are `termination_evidence_sets` and `termination_evidence_set_producers`; the existing termination evidence/result/link tables gain the exact F6 identities and constraints. The recovery-binding columns from R1 remain mandatory together only for bootstrap/restore/reinitialization and prohibited for listener/bridge/cold-start recoveries. The primary key, exact nullability, all column checks, uniques, foreign keys, actions, and deferrability are expressed in the SQL, not inferred from this summary.

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
| Termination | `termination_evidence_sets` | `termination_evidence_set_id` | Health Durable Writer `INSERT` |
| Termination | `termination_evidence_set_producers` | `(termination_evidence_set_id,producer_role)` | Health Durable Writer `INSERT` |
| Termination | `termination_results` | `termination_result_id` | Health Durable Writer `INSERT` |
| Termination | `termination_result_evidence` | `(termination_evidence_set_id,contributor_role)` | Health Durable Writer `INSERT` |
| Expectation | `market_data_expectations` | `expectation_id` | Listener Incident Writer `INSERT`, `UPDATE` |
| Projection | `projection_cursors` | `(projection_name,scope_key)` | Projection Writer `INSERT`, `UPDATE`; no control authority |
| Store incident | `store_incidents` | `store_incident_id` | Store Incident Writer `INSERT`, `UPDATE` |

No `DELETE` route is active. Deletion is prohibited by the typed-plan authorizer; aggregate-child `ON DELETE CASCADE` actions are defined only so a separately approved candidate-construction rollback cannot create orphans. They do not authorize runtime deletion.

## 6. Foreign-key contract

The SQL contains 133 explicit foreign-key declarations and 173 child-column mappings. Every declaration names exact child column(s), parent table and column(s), `ON UPDATE`, `ON DELETE`, and any deferrability. Child nullability is declared on the child column. Every parent is a primary key or inline unconditional `UNIQUE` key; no FK targets a partial index, undefined column, or nonunique identity.

Action totals are:

| Action | Declaration count | Lifecycle reason |
|---|---:|---|
| `ON UPDATE RESTRICT` | 132 | Durable identity keys never change |
| `ON UPDATE CASCADE` | 1 | Composite health dimension/scope key remains internally coupled if a separately governed candidate transform renames the pair |
| `ON DELETE RESTRICT` | 116 | Identity/evidence parents cannot disappear while authoritative children exist |
| `ON DELETE CASCADE` | 17 | Incident/recovery aggregate children cannot be orphaned during pre-activation candidate rollback; runtime deletion remains unauthorized |

Sixty-one declarations are `DEFERRABLE INITIALLY DEFERRED` where transaction-commit/current-pointer or mutually linked history rows must be inserted atomically. Seventy-two are immediate where the parent must already exist. Representative insertion order is: transaction identity as required by the typed envelope; supervisor generation; policy/session references; listener epoch; bridge generation; incident/recovery parent; event/history/outcome child; current-pointer update; transaction completion/readback. Deferred cycles exist only inside one atomic aggregate and do not require an impossible committed intermediate state.

The executable SQL is the per-FK inventory: each `FOREIGN KEY ... REFERENCES ... ON UPDATE ... ON DELETE ...` clause is normative. `PRAGMA foreign_key_list(table)` must reproduce all 173 mappings; `PRAGMA foreign_key_check` must return zero rows.

## 7. Writer routing and exclusivity

The closed operation vocabulary is `INSERT`, `UPDATE`, `DELETE`. The v2 registry installs 62 active table/operation rows and 11 writer identities. Each row binds registry version, table, operation, writer identity, writer contract identity, optional deployment build hash, effective transaction sequence, retirement sequence, and active flag.

`uq_writer_registry_active_scope` is exactly:

```sql
CREATE UNIQUE INDEX uq_writer_registry_active_scope
ON writer_registry(table_name,operation)
WHERE active=1;
```

It is impossible for two writer identities to own the same active table/operation scope. The old active row must be retired by `TX-STORE-WRITER-RETIRE` in a healthy `BEGIN IMMEDIATE` transaction by changing only `active:1->0` and setting its exact retirement sequence; `trg_writer_registry_update_guard` rejects every other update and `trg_writer_registry_delete_guard` rejects deletion. `TX-STORE-WRITER-INSTALL` may insert the successor only after retirement, and `trg_writer_registry_successor_guard` requires `new.effective_transaction_sequence > predecessor.retired_transaction_sequence`; the current version-2 check and serialization-field checks also apply. Registry hash and `store_metadata.writer_registry_hash` change atomically. Any scope or build change requires governance and deployment authorization; neither exists now.

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

The 21 constraint-only triggers are:

| Trigger | Exact effect |
|---|---|
| `trg_writer_registry_update_guard` | permits only the exact active-to-retired update |
| `trg_writer_registry_successor_guard` | rejects active succession until the predecessor is retired and the successor effective sequence is strictly later |
| `trg_writer_registry_delete_guard` | prohibits registry deletion |
| `trg_idempotency_records_immutable` | rejects changed-input/result updates as `IDEMPOTENCY_CONFLICT` |
| `trg_listener_state_transitions_legal` | enforces the closed listener transition relation, including `STOPPING -> STOPPED` |
| `trg_listener_current_insert_match` | requires initial current row to match its exact transition/version/transaction |
| `trg_listener_current_update_match` | requires `old.version+1` and exact prior/result/current transition match |
| `trg_listener_restart_incidents_terminal_match` | requires a terminal incident to point to its own same-transaction outcome row |
| `trg_listener_restart_incidents_no_terminal_insert` | prohibits direct insertion of a terminal restart incident |
| `trg_domain_acknowledgements_required_match` | requires required-domain, supervisor-generation, listener-epoch, and expected-identity equality |
| `trg_subscription_verifications_proof` | permits positive subscription proof only from authenticated current identities and a `RITHMIC_LISTENER` `SUBSCRIPTION_PROOF` event |
| `trg_termination_evidence_integrity` | verifies authenticated evidence transaction/current identities, exact canonical evidence JSON, and its SHA-256 |
| `trg_termination_evidence_observation_sealed` | makes evidence immutable after a result commits for its observation identity |
| `trg_termination_results_structure` | requires current generation/epoch/bridge/process/observation, six complete producer streams, five direct contributors, cutoff/freshness, and transaction equality |
| `trg_termination_results_semantics` | requires each optional identity to be NULL only when inapplicable or to identify the exact direct contributor with the governed producer/type |
| `trg_termination_results_none_completeness` | requires all six governed producer streams to assert the exact role-specific authenticated absence before a field may be `NONE` |
| `trg_termination_results_known_conflict` | rejects `NONE` or concrete field classification when current authenticated producer evidence asserts incompatible values |
| `trg_termination_results_unknown_conflict` | requires `UNKNOWN/CONFLICT` exactly for a conflicting field and `UNKNOWN/INDETERMINATE` only for a nonconflicting unavailable field |
| `trg_termination_results_integrity` | recomputes the exact evidence-set and result serializations and rejects either hash mismatch |
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

`TX-STORE-QUARANTINE` never opens the corrupt database read-write and never depends on a write to it. After all handles close, the Recovery Controller reads the database and existing WAL/SHM files only to obtain exact lengths/SHA-256, and the external writer appends `QUARANTINE_PREPARED` naming that immutable source set. The Controller then moves each named file to the exact incident quarantine directory, flushes each destination file, and verifies destination length/hash; only then does the external writer append `QUARANTINE_COMPLETED`. Because a three-file move is not one filesystem primitive, any partial move is preserved and described by `QUARANTINE_FAILED`; neither source nor partial destination may be reopened as authority, and startup remains failed.

### 9.4 Restore and reinitialization

`TX-STORE-RESTORE` requires the exact authorized backup/store UUID/schema/hash/cursor and external authorization. After read-only source validation it appends `RESTORE_PREPARED` with empty `output_artifacts`/`PREPARED`, constructs the section 14.7 candidate carrying that external sequence/hash, validates and flushes it, atomically replaces the quarantined/absent target, reopens read-only, then appends `RESTORE_COMPLETED` with the activated artifact length/hash. Until completion, startup is failed. A pre-replacement failure appends `RESTORE_FAILED` and leaves the target untouched; a post-replacement failure restores the preactivation target only when no v2 commit occurred, otherwise quarantines the candidate and fails closed.

`TX-STORE-REINITIALIZE` requires explicit acknowledgement that authority/history is unavailable. After independent process reconciliation it appends `REINITIALIZE_PREPARED` with empty `output_artifacts`/`PREPARED`, then constructs the complete section 14.7 candidate carrying that sequence/hash: transaction/idempotency and metadata records, open store recovery/incident, fail-closed listener transition/current, five nonpositive health rows, and the aggregate. It creates no positive imported authority. Activation/readback is followed by `REINITIALIZE_COMPLETED` with the activated artifact length/hash; any failure appends `REINITIALIZE_FAILED` where writable and remains fail-closed. It cannot create an epoch, bridge, positive subscription, readiness, deployment, or trading fact.

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

It is a logical append-only UTF-8 JSON Lines hash chain serialized only by the complete `RANDLE-RECOVERY-JCS-1` profile in section 14.6, including recursive unsigned-UTF-16-unit key ordering, NFC rejection, exact escaping, no insignificant whitespace, and signed-64-bit integer-only number semantics. Required fields are `record_version=1`, `sequence` starting at 1 and increasing by 1, `record_type`, `record_id`, `incident_id`, `startup_attempt_id`, `authorization_id`, `actor_id`, `occurred_at_utc`, `store_path`, `store_uuid` or `UNKNOWN`, `schema_identity` or `UNKNOWN`, `schema_hash` or `UNKNOWN`, `input_artifacts` ordered by section 14.6 normalized absolute path with length/SHA-256, `output_artifacts` in the same form, `validation_result`, `previous_record_sha256`, and `record_sha256`.

`record_sha256` is SHA-256 of the canonical object with `record_sha256` omitted. Sequence 1 uses 64 zeroes for `previous_record_sha256`; later rows use the preceding record hash. Closed current record types are `BOOTSTRAP_PREPARED`, `BOOTSTRAP_COMPLETED`, `BOOTSTRAP_FAILED`, `QUARANTINE_PREPARED`, `QUARANTINE_COMPLETED`, `QUARANTINE_FAILED`, `RESTORE_PREPARED`, `RESTORE_COMPLETED`, `RESTORE_FAILED`, `REINITIALIZE_PREPARED`, `REINITIALIZE_COMPLETED`, `REINITIALIZE_FAILED`, and `VERSION_CONFLICT_OBSERVED`. Migration record types are prohibited unless introduced by a future `FUTURE SEPARATELY GOVERNED PREDECESSOR-BOUND MIGRATION SPECIFICATION`.

There is one writer process under an exclusive evidence-file lock. It reads and verifies the complete existing chain, creates the same-directory `.<record_id>.tmp` with the verified prior bytes plus exactly one line, flushes that file with `FlushFileBuffers`, performs the section 14.6 same-volume `MoveFileExW` operation, reopens read-only, and verifies exact length, bytes, chain, and final hash. It makes no directory-flush claim. Interrupted temp files are nonauthoritative and are retained as evidence; restart resumes only from the last verified log and never skips a sequence. An unwritable or invalid chain fails recovery before activation.

At startup the Store Integrity Classifier consumes the verified chain to detect prepared-without-completed operations, unresolved quarantine, failed activation, and target/hash mismatch. Any unresolved item blocks `CONTROL_STORES_VERIFIED` and `SUPERVISOR_AUTHORITY_READY`. The evidence writer may record recovery facts; it may not decide listener lifecycle, session rollover, bridge lifecycle, health, readiness, deployment, or trading, and its records never create positive authority.

## 11. Closed typed-transaction catalog

There are exactly 55 operation IDs. Fifty-two are permitted `transaction_commits.transaction_type` values. `TX-STORE-VALIDATE` is read-only, `TX-STORE-QUARANTINE` is external-only, and `TX-STORE-VERSION-CONFLICT-REJECT` writes at most a rejected idempotency row with NULL `transaction_id`; the SQL deliberately excludes those three from `transaction_commits`. Every mutating request supplies authority-decision ID, writer set, exact record identities, source/destination state, parent identities, expected versions, idempotency key, canonical request hash, evidence-set hash, and deployment-bound writer identities. The common success/failure/crash/retry/reconstruction rules are section 9; the row below closes transaction-specific authority, writers, records, transition, and result.

| ID | Exact authority; writer set | Exact records and transition; success result |
|---|---|---|
| `TX-LSN-CANCEL` | Listener Supervisor State Evaluator; Listener Incident + Listener State Writers | Pending incident -> terminal `RESTART_CANCELED`; outcome row; listener `SUSPECT -> HEALTHY` or `SUSPECT -> SUSPECT` only from enumerated reevaluation; current/history/version rows; `RESTART_CANCELED` |
| `TX-LSN-FENCE` | Listener Supervisor State Evaluator; Listener Incident + Listener State + **Listener Epoch Writers** | incident `RESTART_PENDING -> RESTART_FENCED`; one fence; current epoch `CURRENT -> FENCED`; listener `SUSPECT -> FENCED`; `RESTART_FENCED` |
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

1. exact schema v2, schema hash, registry version 2/hash, PRAGMAs, governed SHA-256 function preflight, 40 tables, 552 columns, 133 FK declarations/173 mappings, 13 partial unique indexes, and 21 triggers;
2. exactly one valid current supervisor generation/lease and contiguous transaction cursor;
3. exactly one `listener_current`, its exact last transition/version, current epoch ancestry when non-NULL, and no prohibited transition;
4. exact current/open listener incident, terminal outcome relationship, execution, recovery, and acknowledgement set;
5. exact bridge generation written by Bridge Generation Writer, bridge current/history/incident/outcome ancestry;
6. exact producer/event identity, five dimension rows, derived aggregate, per-symbol current session reference and positive subscription rows;
7. no open corruption/schema/routing/recovery incident and no prepared-without-completed external recovery evidence; and
8. projection cursors considered only for parity and never for restoration.

Any mismatch yields `RECOVERY_REQUIRED` or `FAILED`, blocks listener/bridge start and readiness, and creates no positive authority.

## 14. Phase 3C1-R2 exact invariant closure

This section supersedes any inconsistent Phase 3C1 statement above. It does not alter schema version 2, approve this draft, or authorize installation.

### 14.1 Calendar-valid `DATE` and UTC text

`DATE` is exactly ten ASCII characters `YYYY-MM-DD`, year `0001` through `9999`. The concrete column check requires ASCII digits at positions 1–4, 6–7, and 9–10; hyphens at 5 and 8; month 01–12; day 01 through the exact Gregorian month length; and leap day only when `year % 400 = 0` or `year % 4 = 0 AND year % 100 <> 0`. It also requires `strftime('%Y-%m-%d',column||'T00:00:00Z')=column`. The only `DATE` column is `active_contract_sessions.session_date`.

UTC is exactly 27 ASCII characters `YYYY-MM-DDTHH:MM:SS.ffffffZ`. Each concrete UTC column repeats the same year/month/day test, exact separators, six ASCII fractional digits, uppercase `Z`, hour 00–23, minute 00–59, and second 00–59. Leap second 60 is prohibited. Full canonical equality is `strftime('%Y-%m-%dT%H:%M:%S',substr(column,1,19)||'Z')||substr(column,20,8)=column`. No registered function, locale, platform clock, or permissive `julianday()` result is involved.

### 14.2 Registry serialization and succession

The nine writer-hash fields use TAB as separator and `-` as the NULL sentinel. Every serialized identity text is either a closed SQL token (`table_name`, `operation`, `writer_id`) or `writer_contract_identity`, which must be nonempty, must not equal `-`, and must contain no TAB, LF, or CR. `writer_build_hash` is NULL or lowercase hexadecimal and therefore cannot contain a separator/sentinel. Integer fields use SQLite base-10 rendering.

The predecessor is the row for the same version/table/operation with the greatest non-NULL retirement sequence. `TX-STORE-WRITER-RETIRE` first durably changes the sole active predecessor to inactive at sequence `R`. `TX-STORE-WRITER-INSTALL` then inserts exactly one current-version successor with `effective_transaction_sequence > R`, a governed contract identity, and no active predecessor. The active-scope unique index and `trg_writer_registry_successor_guard` independently reject active conflict, same/lower sequence, version mismatch, and invalid contract identity.

### 14.3 Closed new commit operations

The following 18 operations extend, and do not replace, the 37-row catalog above. For each row the request is canonical JSON containing operation ID, authority-decision ID, every named row identity, source state/version, proposed result state/version, exact active writer identities/build hashes, and evidence SHA-256; its SHA-256 is `request_hash`. The idempotency key is `(operation ID, authority-decision ID)`. The coordinator inserts the transaction/idempotency identity before trigger-governed domain rows inside the same transaction, applies only the listed rows, updates metadata cursor/hash where listed, commits, then verifies on a separate read-only connection. Missing parent, stale expected version, route mismatch, or SQL constraint returns respectively `MISSING_PARENT`, `VERSION_CONFLICT`, `WRITER_ROUTING_REJECTED`, or `CONSTRAINT_REJECTED` with rollback. A precommit crash leaves no row; a postcommit/readback crash reconstructs by transaction/idempotency ID and exact result versions. Retry must reuse identical request bytes and returns the prior result; changed bytes are `IDEMPOTENCY_CONFLICT`.

| ID | Initiating authority; exact writers | Exact read/source -> writes/result |
|---|---|---|
| `TX-SUP-GENERATION-CREATE` | authenticated Startup/Recovery Authorization; Supervisor Generation Writer | require no `CURRENT` generation and expected metadata cursor; insert one `CURRENT` `supervisor_generations` row at prior max sequence+1; `GENERATION_CREATED` |
| `TX-SUP-LEASE-ACQUIRE` | Supervisor Lease Evaluator; Supervisor Generation Writer | current generation plus no held lease -> insert one version-1 `HELD` lease; `LEASE_ACQUIRED` |
| `TX-SUP-LEASE-RENEW` | Supervisor Lease Evaluator; Supervisor Generation Writer | exact held lease version/token/generation -> update expiry, last-renew transaction, version+1; `LEASE_RENEWED` |
| `TX-SUP-LEASE-RELEASE` | owning Supervisor or Recovery Authorization; Supervisor Generation Writer | exact held lease -> `RELEASED`, version+1; `LEASE_RELEASED` |
| `TX-SUP-GENERATION-RETIRE` | owning Supervisor or Recovery Authorization; Supervisor Generation Writer | generation `FENCED`, no held lease/current epoch/current bridge -> `RETIRED`; `GENERATION_RETIRED` |
| `TX-LSN-EPOCH-GRANT` | Listener Supervisor State Evaluator after current generation/held lease and authenticated process identity; Listener Epoch Writer | no current epoch -> insert next-sequence `CURRENT` epoch; `EPOCH_GRANTED` |
| `TX-LSN-EPOCH-FENCE` | Listener Supervisor State Evaluator; Listener Epoch Writer | exact current epoch -> `FENCED`, fence time/reason; `EPOCH_FENCED` |
| `TX-LSN-EPOCH-RETIRE` | Listener Supervisor State Evaluator after fence and absence of current child bridge/recovery; Listener Epoch Writer | exact `FENCED` epoch -> `RETIRED`; `EPOCH_RETIRED` |
| `TX-LSN-START` | Listener Supervisor State Evaluator with current generation/held lease and no open incident; Listener State Writer | `STOPPED` or fully closed `LISTENER_FAILED` -> `STARTING`, current/history version+1; `LISTENER_STARTING` |
| `TX-LSN-RESTART-PENDING` | Listener Supervisor State Evaluator satisfying one SFF predicate; Listener Incident + Listener State Writers | `HEALTHY` with current epoch and no incident -> insert nonterminal version-1 `RESTART_PENDING`, then `HEALTHY -> SUSPECT` current/history; `RESTART_PENDING` |
| `TX-STORE-WRITER-RETIRE` | Architecture Governance plus Deployment Authorization; Coordinator | sole active route at expected registry hash -> inactive with retirement sequence equal proposed transaction sequence; update registry hash and metadata; `WRITER_RETIRED` |
| `TX-STORE-WRITER-INSTALL` | same authorizations; Coordinator | retired predecessor and expected post-retirement hash -> insert one successor effective strictly after retirement; update registry hash and metadata; `WRITER_INSTALLED` |
| `TX-PRODUCER-REGISTER` | Health Ingress Registration Authority; Health Durable Writer | current generation/epoch and unique process/role -> insert version-1 `ACTIVE` producer; `PRODUCER_REGISTERED` |
| `TX-PRODUCER-RETIRE` | Health Ingress Registration Authority; Health Durable Writer | exact active producer and final sequence -> `RETIRED`; `PRODUCER_RETIRED` |
| `TX-CONTRACT-SESSION-IMPORT` | ADR-014 Reference Validator; Health Durable Writer | authenticated ADR-014 commit/hash for symbol/contract/session and no conflicting current symbol row -> insert `active_contract_sessions`; no session decision; `CONTRACT_SESSION_IMPORTED` |
| `TX-CONTRACT-SESSION-RETIRE` | ADR-014 Reference Validator; Health Durable Writer | exact current external reference plus a later authenticated ADR-014 commit or explicit invalidation -> set `valid_to_sequence`; `CONTRACT_SESSION_RETIRED` |
| `TX-STORE-RECOVERY-COMPLETE` | Store Integrity Classifier after authenticated Recovery Authorization; Recovery Transaction + Store Incident + Listener State Writers | candidate baseline `SUPERVISOR_STORE_FAILED`, open store recovery/incident, and current new supervisor generation -> close recovery/incident and transition `SUPERVISOR_STORE_FAILED -> STOPPED` version+1; `STORE_RECOVERY_COMPLETED` |
| `TX-BRG-INITIALIZE` | Listener Supervisor State Evaluator after `TX-BRG-GRANT`; Health Durable Writer | current granted generation and no `bridge_current` -> insert initial transition/current `NONE -> BRIDGE_STARTUP_UNPROVEN` version 1; `BRIDGE_INITIALIZED` |

`TX-BRG-GRANT` is the exact bridge-generation creation operation and permits no predecessor only for the first generation of a current listener epoch; otherwise it requires the prior generation fenced or retired. `TX-LSN-FENCE` includes Listener Epoch Writer and fences the current epoch in the same commit; no incident/state writer may modify an epoch.

#### 14.3.1 Complete active mutation-route coverage

The operation names below are exhaustive for all 62 active routes. `COMMON` means every one of the 52 commit operations inserts its transaction/idempotency rows and updates the metadata cursor; it does not authorize a domain row. Candidate construction uses the named bootstrap/restore/reinitialize operation only.

| Table | Active operation -> exact typed operation(s) |
|---|---|
| `store_metadata` | INSERT -> `TX-STORE-BOOTSTRAP-V2`, `TX-STORE-RESTORE`, `TX-STORE-REINITIALIZE` candidate; UPDATE -> `COMMON` |
| `writer_registry` | INSERT -> `TX-STORE-BOOTSTRAP-V2`, `TX-STORE-RESTORE`, `TX-STORE-REINITIALIZE`, `TX-STORE-WRITER-INSTALL`; UPDATE -> `TX-STORE-WRITER-RETIRE` |
| `transaction_commits` | INSERT -> `COMMON` |
| `idempotency_records` | INSERT -> `COMMON`, `TX-STORE-VERSION-CONFLICT-REJECT` |
| `supervisor_generations` | INSERT -> `TX-SUP-GENERATION-CREATE`; UPDATE -> `TX-SUP-GENERATION-RETIRE`, `TX-STORE-STALE-LEASE-FENCE` |
| `supervisor_leases` | INSERT -> `TX-SUP-LEASE-ACQUIRE`; UPDATE -> `TX-SUP-LEASE-RENEW`, `TX-SUP-LEASE-RELEASE`, `TX-STORE-STALE-LEASE-FENCE` |
| `shared_feed_policies` | INSERT/UPDATE -> `TX-POLICY-VALIDATE` |
| `active_contract_sessions` | INSERT -> `TX-CONTRACT-SESSION-IMPORT`; UPDATE -> `TX-CONTRACT-SESSION-RETIRE` |
| `listener_epochs` | INSERT -> `TX-LSN-EPOCH-GRANT`; UPDATE -> `TX-LSN-EPOCH-FENCE`, `TX-LSN-EPOCH-RETIRE`, `TX-LSN-FENCE` |
| `recovery_transactions` | INSERT -> `TX-STORE-BOOTSTRAP-V2`, `TX-STORE-RESTORE`, `TX-STORE-REINITIALIZE`, `TX-LSN-REHYDRATION-START`, `TX-BRG-REHYDRATE`; UPDATE -> `TX-LSN-COMPLETE`, `TX-LSN-FAIL`, `TX-LSN-RATE-EXHAUSTED`, `TX-BRG-READY`, `TX-BRG-FAIL`, `TX-BRG-EXHAUSTED`, `TX-STORE-RECOVERY-COMPLETE` |
| `listener_current` | INSERT -> `TX-STORE-BOOTSTRAP-V2`, `TX-STORE-RESTORE`, `TX-STORE-REINITIALIZE`; UPDATE -> `TX-LSN-START`, `TX-LSN-RESTART-PENDING`, `TX-LSN-CANCEL`, `TX-LSN-FENCE`, `TX-LSN-REHYDRATION-START`, `TX-LSN-COMPLETE`, `TX-LSN-FAIL`, `TX-LSN-RATE-EXHAUSTED`, `TX-LSN-PLANNED-STOP`, `TX-LSN-STOP-COMPLETE`, `TX-STORE-RECOVERY-COMPLETE` |
| `listener_state_transitions` | INSERT -> `TX-STORE-BOOTSTRAP-V2`, `TX-STORE-RESTORE`, `TX-STORE-REINITIALIZE`, `TX-LSN-START`, `TX-LSN-RESTART-PENDING`, `TX-LSN-CANCEL`, `TX-LSN-FENCE`, `TX-LSN-REHYDRATION-START`, `TX-LSN-COMPLETE`, `TX-LSN-FAIL`, `TX-LSN-RATE-EXHAUSTED`, `TX-LSN-PLANNED-STOP`, `TX-LSN-STOP-COMPLETE`, `TX-STORE-RECOVERY-COMPLETE` |
| `listener_restart_incidents` | INSERT -> `TX-LSN-RESTART-PENDING`; UPDATE -> `TX-LSN-CANCEL`, `TX-LSN-FENCE`, `TX-LSN-EXECUTION-START`, `TX-LSN-REHYDRATION-START`, `TX-LSN-ACK`, `TX-LSN-COMPLETE`, `TX-LSN-FAIL`, `TX-LSN-RATE-EXHAUSTED` |
| `listener_restart_incident_transitions` | INSERT -> `TX-LSN-CANCEL`, `TX-LSN-FENCE`, `TX-LSN-EXECUTION-START`, `TX-LSN-REHYDRATION-START`, `TX-LSN-COMPLETE`, `TX-LSN-FAIL`, `TX-LSN-RATE-EXHAUSTED` |
| `listener_restart_outcomes` | INSERT -> `TX-LSN-CANCEL`, `TX-LSN-COMPLETE`, `TX-LSN-FAIL`, `TX-LSN-RATE-EXHAUSTED` |
| `listener_fences` | INSERT -> `TX-LSN-FENCE` |
| `listener_execution_attempts` | INSERT -> `TX-LSN-EXECUTION-START`; UPDATE -> `TX-LSN-REHYDRATION-START`, `TX-LSN-COMPLETE`, `TX-LSN-FAIL` |
| `listener_rehydrations` | INSERT -> `TX-LSN-REHYDRATION-START`; UPDATE -> `TX-LSN-ACK`, `TX-LSN-COMPLETE`, `TX-LSN-FAIL` |
| `recovery_required_domains` | INSERT -> `TX-LSN-REHYDRATION-START` |
| `domain_acknowledgements` | INSERT -> `TX-LSN-ACK` |
| `bridge_generations` | INSERT -> `TX-BRG-GRANT`; UPDATE -> `TX-BRG-GRANT`, `TX-BRG-EPOCH-TRANSITION` |
| `bridge_current` | INSERT -> `TX-BRG-INITIALIZE`; UPDATE -> `TX-BRG-RECYCLE-PENDING`, `TX-BRG-CANCEL`, `TX-BRG-FENCE`, `TX-BRG-EXECUTE`, `TX-BRG-REHYDRATE`, `TX-BRG-READY`, `TX-BRG-FAIL`, `TX-BRG-EXHAUSTED`, `TX-BRG-PLANNED-SHUTDOWN`, `TX-BRG-EPOCH-TRANSITION` |
| `bridge_transitions` | INSERT -> `TX-BRG-INITIALIZE`, `TX-BRG-RECYCLE-PENDING`, `TX-BRG-CANCEL`, `TX-BRG-FENCE`, `TX-BRG-EXECUTE`, `TX-BRG-REHYDRATE`, `TX-BRG-READY`, `TX-BRG-FAIL`, `TX-BRG-EXHAUSTED`, `TX-BRG-PLANNED-SHUTDOWN`, `TX-BRG-EPOCH-TRANSITION` |
| `bridge_incidents` | INSERT -> `TX-BRG-RECYCLE-PENDING`; UPDATE -> `TX-BRG-CANCEL`, `TX-BRG-FENCE`, `TX-BRG-EXECUTE`, `TX-BRG-REHYDRATE`, `TX-BRG-READY`, `TX-BRG-FAIL`, `TX-BRG-EXHAUSTED` |
| `bridge_recycle_attempts` | INSERT -> `TX-BRG-EXECUTE`; UPDATE -> `TX-BRG-REHYDRATE`, `TX-BRG-READY`, `TX-BRG-FAIL`, `TX-BRG-EXHAUSTED` |
| `bridge_outcomes` | INSERT -> `TX-BRG-CANCEL`, `TX-BRG-READY`, `TX-BRG-FAIL`, `TX-BRG-EXHAUSTED`, `TX-BRG-PLANNED-SHUTDOWN` |
| `producer_registrations` | INSERT -> `TX-PRODUCER-REGISTER`; UPDATE -> `TX-PRODUCER-RETIRE` |
| `health_events` | INSERT -> `TX-HEALTH-EVENT` |
| `health_current` | INSERT -> `TX-STORE-BOOTSTRAP-V2`, `TX-STORE-RESTORE`, `TX-STORE-REINITIALIZE`; UPDATE -> `TX-HEALTH-DIMENSION-UPDATE` |
| `health_transitions` | INSERT -> `TX-HEALTH-DIMENSION-UPDATE` |
| `health_aggregate` | INSERT -> `TX-STORE-BOOTSTRAP-V2`, `TX-STORE-RESTORE`, `TX-STORE-REINITIALIZE`; UPDATE -> `TX-HEALTH-DIMENSION-UPDATE` |
| `subscription_verifications` | INSERT -> `TX-SUBSCRIPTION-VERIFY` |
| `termination_evidence` | INSERT -> `TX-TERMINATION-EVIDENCE` |
| `termination_evidence_sets` | INSERT -> `TX-TERMINATION-CLASSIFY` |
| `termination_evidence_set_producers` | INSERT -> `TX-TERMINATION-CLASSIFY` |
| `termination_result_evidence` | INSERT -> `TX-TERMINATION-CLASSIFY` |
| `termination_results` | INSERT -> `TX-TERMINATION-CLASSIFY` |
| `market_data_expectations` | INSERT/UPDATE -> `TX-EXPECTATION-EVALUATE` |
| `projection_cursors` | INSERT/UPDATE -> `TX-PROJECTION-CURSOR` |
| `store_incidents` | INSERT/UPDATE -> `TX-STORE-INCIDENT`, `TX-STORE-BOOTSTRAP-V2`, `TX-STORE-RESTORE`, `TX-STORE-REINITIALIZE`, `TX-STORE-RECOVERY-COMPLETE` |

No normative mutation path remains uncovered; no DELETE route exists.

### 14.4 Cancellation and terminal listener incidents

`TX-LSN-CANCEL` creates `RESTART_CANCELED`, updates the pending incident to terminal, and reevaluates `SUSPECT` to exactly `HEALTHY` or `SUSPECT`. The latter commits `SUSPECT -> SUSPECT`, increments state version, and uses reason `CANCELLATION_REEVALUATION_REMAINS_SUSPECT`. The trigger permits that self-edge only when the transaction type is `TX-LSN-CANCEL`; `writer_set_json` is an exact two-element string set containing `LISTENER_INCIDENT_WRITER` and `LISTENER_STATE_WRITER`; the current incident/outcome/transaction match; the outcome result is `SUSPECT`; the current row has the expected prior version; and supervisor generation/listener epoch and row writer constraints match. No other listener self-edge is legal.

An incident insert must be nonterminal. To become terminal, the Incident Writer inserts its outcome and incident-transition rows, then updates the incident. The terminal update trigger requires a permitted nonterminal predecessor, version+1, the incident's transition ID, same completion transaction, same incident ID, and identical optional recovery-transaction identity. Direct terminal insertion, another incident's outcome, transaction mismatch, recovery mismatch, or invalid outcome/predecessor mapping aborts.

### 14.5 Subscription and five-field termination identity

A subscription verification includes source producer and sequence, symbol, contract identity, unconditional composite contract-session reference, request identity, provider acknowledgement identity, evaluator decision/version, freshness observation identity, current listener epoch, current bridge generation, proof identity/hash, record integrity hash, and committing transaction. The composite foreign keys require `(contract_session_ref_id,symbol,contract_id)` and `(bridge_generation_id,listener_epoch_id,supervisor_generation_id)` coherence. The positive-proof trigger additionally requires a current epoch/generation, active Rithmic listener producer, exact producer sequence, authenticated `SUBSCRIPTION_PROOF`, current external session reference, and `TX-SUBSCRIPTION-VERIFY`. Its authenticated event object must contain exact text members `contract_id`, `contract_session_ref_id`, `request_identity`, `provider_acknowledgement_identity`, `freshness_observation_identity`, and `proof_evidence_identity`, each equal to the committed row. Cross-symbol, stale-epoch, wrong-generation, missing or mismatched provider/request/proof/freshness identity, and duplicate positive-current rows fail.

The five SQL vocabularies exactly match ADR-016: initiator `NONE|LISTENER|LISTENER_SUPERVISOR|AUTHENTICATED_OPERATOR|RAPI_PROVIDER|UNKNOWN`; requested action `NONE|BRIDGE_RECYCLE|BRIDGE_SHUTDOWN|LISTENER_SHUTDOWN|FULL_LISTENER_RESTART|UNKNOWN`; execution method `NONE|GRACEFUL_RAPI_LOGOUT|GRACEFUL_PROCESS_EXIT|SUPERVISOR_TERMINATE|SUPERVISOR_KILL|PROCESS_SELF_EXIT|PROVIDER_FORCED_LOGOUT|PROVIDER_SHUTDOWN_SIGNAL|UNKNOWN`; observed cause `NONE|PLANNED_SHUTDOWN|BRIDGE_CRASH|AUTHENTICATION_FAILURE|CONNECTION_LOSS|SUBSCRIPTION_FAILURE|LISTENER_EXIT|RAPI_ENGINE_INERT|UNKNOWN`; result `NONE|COMPLETED_EXPECTED|RECOVERED|FAILED|TIMED_OUT|CANCELED|PROCESS_EXITED|ENGINE_INERT|UNKNOWN`.

The active termination contract is `termination_schema_version=2`. One immutable `termination_evidence_sets` row names one result, the current supervisor generation, listener epoch, bridge generation, listener process, observation identity/sequence/cutoff, classification decision/evaluator version, set hash, and committing transaction. The cutoff is the result `observed_at_utc`. All contributing evidence is at or before the cutoff and no older than five seconds at cutoff. `termination_results.recorded_at_utc` equals or follows the cutoff by at most 30 seconds and equals the transaction commit time. Missing, prior, future, or mixed schema versions fail.

Each set contains exactly six producer-window rows, one each for `RITHMIC_LISTENER`, `BRIDGE_CONTROLLER`, `OS_ADAPTER`, `RAPI_ADAPTER`, `SUPERVISOR_ADAPTER`, and `OPERATOR_ADAPTER`. A producer instance’s first termination window starts at sequence 1; every later window for that producer and bridge starts at the prior window’s end plus one. `producer_sequence=ingress_sequence`; `(producer_instance_id,producer_sequence)` and `(producer_instance_id,ingress_sequence)` are unconditional unique keys. `last_accepted_sequence=expected_end_sequence`, and every integer in the closed start/end interval must have one authenticated evidence row matching the set generation, epoch, bridge, process, observation, schema version, and cutoff. A missing, duplicate, skipped, out-of-order, unauthenticated, unmatched-producer, or after-cutoff row aborts classification. Producer restart creates a newly registered producer instance whose first window starts at 1; a set cannot splice two instances for one role. Current-generation reset likewise uses new generation/epoch/bridge/producer/observation identities, never a sequence reset inside an existing instance.

Exactly five `termination_result_evidence` rows must exist before result insertion, one for each role `INITIATOR_EVIDENCE`, `REQUESTED_ACTION_EVIDENCE`, `EXECUTION_METHOD_EVIDENCE`, `OBSERVED_CAUSE_EVIDENCE`, and `RESULT_EVIDENCE`. The composite keys bind every link to the exact result/set and repeat the evidence producer, sequence, type, time, schema, hash, generation, epoch, bridge, process, observation, authentication disposition, role, assertion kind, and asserted value. One evidence ID may be a contributor to only one set and one role. An unrelated sixth contributor necessarily duplicates a closed role or evidence identity and fails. Supporting observations remain inside the six complete producer windows but are not contributors.

Every optional result identity is either NULL because its field makes that identity inapplicable, or is the exact identity carried by a direct contributor: operator command -> operator initiator; provider evidence -> provider initiator/method; OS evidence -> OS execution/cause/result; bridge evidence -> bridge request/cause; listener evidence -> listener initiator/shutdown/exit; request -> requested-action contributor. The result process and observation identities are mandatory and are composite-FK equal to all contributors. Cross-result, cross-set, stale generation/epoch/bridge, cross-process, cross-observation, or outside-the-five identity fails. Symbol/contract identities are intentionally inapplicable to this shared bridge/process termination classification; the exact evidence JSON has no symbol/contract member and extra JSON members fail equality.

`NONE` is field-specific positive absence evidence, not a relationship label. All six producer windows must contain a `STARTUP_TRANSITION` row for the field with the exact role-specific absence scope; the selected contributor is one of those six authenticated, current, sequence-complete assertions. The scopes are respectively `NO_INITIATOR_THROUGH_CUTOFF`, `NO_REQUEST_THROUGH_CUTOFF`, `NO_EXECUTION_THROUGH_CUTOFF`, `NO_CAUSE_THROUGH_CUTOFF`, and `NO_RESULT_THROUGH_CUTOFF`; every current supporting observation for that role must assert the same absence and none may assert another fact. Thus Initiator NONE proves no listener/supervisor/operator/provider actor; Requested Action NONE proves no recycle/shutdown/restart/logout/termination request; Execution Method NONE proves no method and no unobserved process termination; Observed Cause NONE proves no observed applicable cause; Result NONE proves no termination/recovery action or event. `PROCESS_EXCEPTION` can never be an absence proof.

Any stale, missing, incomplete, sequence-gapped, conflicting, corrupt, unauthenticated, wrong-generation/epoch/bridge/process/observation/result/set/schema/integrity identity aborts the result insert, so no current result exists and startup remains unproven. Within an otherwise current, complete set, uncertainty is field-specific: two or more distinct non-UNKNOWN assertions for a role require that field’s contributor to be `UNKNOWN` with `CONFLICT`; a role with no conflict but unavailable positive/absence fact requires `UNKNOWN` with `INDETERMINATE`. A conflict or indeterminacy does not automatically erase another independently complete field. A known/NONE token for a conflicting field fails, as does `CONFLICT` without a conflict or `INDETERMINATE` with one.

Minimum concrete proof is closed by role and evidence type exactly as the executable checks state. `LISTENER`, `LISTENER_SUPERVISOR`, `AUTHENTICATED_OPERATOR`, and `RAPI_PROVIDER` initiators require respectively `LISTENER_SHUTDOWN`, `SUPERVISOR_COMMAND`, `OPERATOR_COMMAND`, and `RAPI_CALLBACK`. Every concrete requested action requires a request identity and one of `SUPERVISOR_COMMAND|OPERATOR_COMMAND|LISTENER_SHUTDOWN`. `GRACEFUL_RAPI_LOGOUT` requires `RAPI_CALLBACK|SUPERVISOR_COMMAND`; `GRACEFUL_PROCESS_EXIT` requires `PROCESS_EXIT|OS_HANDLE`; `SUPERVISOR_TERMINATE|SUPERVISOR_KILL` require `SUPERVISOR_COMMAND|OS_HANDLE`; `PROCESS_SELF_EXIT` requires `PROCESS_EXIT|OS_HANDLE`; provider-forced methods require `RAPI_CALLBACK`. `BRIDGE_CRASH` requires `PROCESS_EXCEPTION|OS_HANDLE`; authentication/connection/subscription/engine causes require `RAPI_CALLBACK`; `LISTENER_EXIT` requires `PROCESS_EXIT|OS_HANDLE|LISTENER_SHUTDOWN`; `PLANNED_SHUTDOWN` requires `SUPERVISOR_COMMAND|OPERATOR_COMMAND|LISTENER_SHUTDOWN`. `COMPLETED_EXPECTED|RECOVERED|FAILED|TIMED_OUT|CANCELED` require `SUPERVISOR_COMMAND|RAPI_CALLBACK|OS_HANDLE|PROCESS_EXIT`; `PROCESS_EXITED` requires `PROCESS_EXIT|OS_HANDLE`; `ENGINE_INERT` requires current `RAPI_CALLBACK`. Nonzero exit alone supplies no classified cause. `PLANNED_SHUTDOWN` additionally requires an authenticated current command contributor and expected execution/result evidence; `AUTHENTICATED_OPERATOR` requires its direct `operator_command_identity`; `FULL_LISTENER_RESTART` requires its direct governed request; provider-forced values require direct provider evidence; process-exit values require the matched process observation.

The Health State Evaluator owns conflict detection and the decision; the Health Durable Writer records only its authorized decision. The database validates but never originates the classification. Reclassification uses a new observation identity, the next gapless `observation_sequence` for the same bridge generation, complete producer windows, decision ID, evidence set, result, and transaction; prior rows remain immutable. The current result is deterministically the unique maximum sequence for that bridge generation. A committed field-specific `UNKNOWN` blocks the termination-related startup proof until a later current nonconflicting classification satisfies it.

Evidence integrity is `SHA-256(UTF-8(canonical_evidence_json))`, where the SQL `json_object` expression in `trg_termination_evidence_integrity` supplies the exact ordered field list, represents inapplicable NULL identity as JSON string `"-"`, uses compact SQLite JSON output, and rejects any different byte representation. The set hash is SHA-256 of `RANDLE-TERMINATION-EVIDENCE-SET-2\n`, one tab-separated header line, producer-window lines ordered by producer role, all in-window evidence lines ordered by producer role/sequence, and the five contributor lines ordered by contributor role, each block LF-terminated exactly as the trigger constructs it. The result hash is SHA-256 of `RANDLE-TERMINATION-RESULT-2\n`, the exact tab-separated result line with NULL optionals as `-`, then five contributor lines ordered by role, with one final LF. Tabs/LF/CR/sentinel ambiguity is prohibited by the source column checks. `randle_sha256_hex_utf8` recomputes both before insert; a changed byte or hash fails.

### 14.6 `RANDLE-RECOVERY-JCS-1` canonical evidence profile

`RANDLE-RECOVERY-JCS-1` is a complete project profile and does not incorporate RFC 8785: its signed 64-bit integer domain is intentionally not the RFC 8785/IEEE-754 number domain. Input is decoded as strict UTF-8 without BOM. Malformed UTF-8, a decoded duplicate key at any object depth (including two differently escaped spellings of the same key), a lone/invalid surrogate code point, and every string or key not already Unicode NFC are rejected; the writer never silently normalizes accepted input. Objects are recursively ordered by decoded key using unsigned UTF-16 code-unit lexicographic order, with an exhausted shorter key sorting first; arrays preserve input order. Keys and string values emit non-ASCII scalar values literally as UTF-8 and never as surrogate escapes. Quotation mark emits `\"`, reverse solidus emits `\\`, U+0008/U+0009/U+000A/U+000C/U+000D emit `\b|\t|\n|\f|\r`, and the remaining U+0000–U+001F values emit lowercase `\u00xx`; solidus is never escaped. No other escape or insignificant whitespace is emitted. The only values are objects, arrays, strings, Boolean `true|false`, `null`, and signed 64-bit integers. Integers emit the shortest base-10 digits, with `-` only for a negative nonzero value and no leading zero; floating point, exponent syntax, negative zero, NaN, and infinity are rejected.

Paths are first resolved by `GetFullPathNameW`; relative, device, alternate-data-stream, reparse-point, dot-segment, and root-target paths are rejected. The drive letter is uppercased, separators are reverse solidus, no trailing separator is retained except a drive root, and the already-NFC result is serialized literally. Input literal `é` and input `\u00e9` parse to one scalar and therefore produce the same single literal UTF-8 canonical form; only that emitted literal-UTF-8 form is accepted as a canonical stored line.

`record_sha256` hashes the canonical object bytes with the `record_sha256` member omitted and no newline. The stored line is the canonical object including that lowercase hash plus one LF. Whole-file verification hashes and parses the exact concatenation of canonical lines including every LF; CRLF, BOM, missing final LF, blank line, or noncanonical line fails. Sequence and previous-record hash rules remain section 10.

The one writer holds the named system mutex `Global\\RandleRuntimeAuthorityRecoveryEvidenceWriterV1`, whose DACL permits only `SYSTEM`, `Administrators`, and the configured Runtime Operations Recovery Controller SID, and an exclusive target handle; inability to create/acquire either fails `RECOVERY_EVIDENCE_WRITER_EXCLUSIVE`. It opens the exact same-directory `.<record_id>.tmp` with `CreateFileW(CREATE_NEW, GENERIC_WRITE, share mode 0, FILE_ATTRIBUTE_NORMAL|FILE_FLAG_WRITE_THROUGH)`; an existing temp name returns `RECOVERY_EVIDENCE_TEMP_COLLISION` and is never overwritten. It writes verified prior bytes plus one line with `WriteFile`, verifies every reported byte count, calls `FlushFileBuffers`, and closes. It then calls same-volume `MoveFileExW(temp,target,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)` for an existing target or `MoveFileExW(temp,target,MOVEFILE_WRITE_THROUGH)` for first creation. Cross-volume fallback and copy/delete behavior are prohibited. It reopens the target with `CreateFileW(GENERIC_READ, FILE_SHARE_READ, OPEN_EXISTING)`, verifies exact length, bytes, whole chain, and last hash, and reports success only after that readback. Windows exposes no portable directory-handle fsync guarantee for this contract; none is claimed. Same-volume NTFS replacement is atomic to readers, but sudden-power-loss durability of the directory entry remains a residual platform risk; prepared-without-verified-completion evidence therefore keeps startup failed. On restart every `.<record_id>.tmp` is opened read-only, hashed, and compared with the verified target and its named prepared record. It is never adopted. If the target chain is valid, the writer appends that operation's closed `*_FAILED` type naming the orphan hash, verifies the new chain, and only then calls `DeleteFileW` on the temp; deletion failure retains the temp and keeps startup failed. If the target chain is invalid or the prepared identity cannot be proven, the temp is retained and startup fails. No retry overwrites or reuses an orphan name.

One canonical record including LF is at most 65,536 bytes. The file is at most 16,777,216 bytes and 4,096 records, whichever is reached first. Whole-file replacement is permitted only within those bounds. No compaction, truncation, rollover, sequence reset, or deletion is permitted by this contract. If the next append exceeds any bound, the writer returns `RECOVERY_EVIDENCE_CAPACITY_EXHAUSTED`, leaves the verified file unchanged, and recovery/startup remains failed pending a separately governed archival/rollover contract.

Current record types exclude migration: `BOOTSTRAP_PREPARED|COMPLETED|FAILED`, `QUARANTINE_PREPARED|COMPLETED|FAILED`, `RESTORE_PREPARED|COMPLETED|FAILED`, `REINITIALIZE_PREPARED|COMPLETED|FAILED`, and `VERSION_CONFLICT_OBSERVED`. A future migration record type exists only under a `FUTURE SEPARATELY GOVERNED PREDECESSOR-BOUND MIGRATION SPECIFICATION`.

### 14.7 Candidate-store construction and post-replacement initialization

All candidate construction uses `foreign_keys=ON` and one transaction whose declared deferred relationships are checked at COMMIT. SQL objects and the 62-row registry are installed first. Bootstrap and reinitialization then use this exact order: (1) the one candidate `transaction_commits` row; (2) its `idempotency_records` row; (3) `store_metadata`; (4) the store recovery row with external prepared-evidence sequence/hash; (5) the reinitialization-only `store_incidents` row, with bootstrap inserting none; (6) the initialization listener transition; (7) `listener_current`; (8) five `health_current` rows in dimension order `PERSISTENCE,TRANSPORT,AUTHENTICATION,AUTHORITY_COHERENCE,TIME_AUTHORITY`; (9) `health_aggregate`; and (10) metadata cursor/readback verification. Generation, lease, policy, contract-session, producer, epoch, bridge, subscription, termination, expectation, and projection tables are empty in both candidates; reinitialization alone has the named open recovery/incident.

Restore never inserts the bootstrap/reinitialization listener or health baseline. It authenticates a complete schema-v2 backup; requires its 62 active registry rows to equal the SQL-installed rows byte-for-byte; installs any authenticated retired registry history through the same successor constraints; and inserts the preserved domain rows plus one new restore operation in this exact order: (1) all preserved `transaction_commits` in sequence order followed by `TX-STORE-RESTORE`; (2) matching preserved idempotency rows followed by restore idempotency; (3) `store_metadata` with preserved UUID/creation identity and next cursor; (4) `supervisor_generations`, then `supervisor_leases`, `shared_feed_policies`, and `active_contract_sessions`; (5) `producer_registrations`; (6) `listener_epochs` and `bridge_generations`; (7) preserved nonterminal listener/bridge incidents and the nonterminal predecessor images of every terminal incident, then recovery transactions, outcomes, incident transitions, fences, execution attempts, rehydrations, required domains, and acknowledgements, using declared deferral for their incident/recovery cycles; each terminal listener incident is then updated from the exact predecessor state/version through its preserved terminal transition and own outcome under its preserved completion transaction, so the direct-terminal-insert prohibition and terminal-match trigger both execute; (8) listener/bridge state transitions followed by their exact current rows; (9) `health_events`, then `health_transitions`, five exact `health_current` rows, and `health_aggregate`; (10) `subscription_verifications`; (11) `termination_evidence`, then `termination_evidence_sets`, their six `termination_evidence_set_producers` windows, the five `termination_result_evidence` contributors, and finally `termination_results`, using the declared deferred result/set links while every trigger remains active; (12) `market_data_expectations`, `projection_cursors`, and preserved `store_incidents`; (13) the completed `STORE_RESTORE` recovery row carrying the new external `RESTORE_PREPARED` sequence/hash; and (14) metadata readback. Any predecessor image required for trigger-valid reconstruction must be uniquely derivable from preserved transition history or restore fails `RESTORE_HISTORY_INCOMPLETE`; triggers are never disabled. Any table absent from the authenticated backup is absent only if its SQL nullability/cardinality permits that exact state. `PRAGMA integrity_check='ok'`, zero `foreign_key_check` rows, all startup proof queries, and exact row-count/hash comparison to the backup plus the enumerated restore additions are mandatory before activation.

Clean bootstrap inserts exactly the registry plus: one sequence-1 `TX-STORE-BOOTSTRAP-V2` commit/idempotency row; metadata cursor 1; one completed `STORE_BOOTSTRAP` recovery row carrying the external `BOOTSTRAP_PREPARED` sequence and record hash; one initialization transition `NONE -> STOPPED` version 1 with NULL generation/epoch; one matching `listener_current`; five `HEALTH_STARTUP_UNPROVEN` rows with NULL generation/epoch/bridge; and aggregate `HEALTH_STARTUP_UNPROVEN`. It requires zero-owned-process evidence. It inserts zero generation, lease, producer, contract session, epoch, bridge, subscription, termination, expectation, projection, or open incident rows.

Restore copies every authenticated row and exact cursor/hash from a verified schema-v2 backup, preserves store UUID and all versions, appends one `TX-STORE-RESTORE` commit/idempotency row and completed `STORE_RESTORE` recovery row carrying the external `RESTORE_PREPARED` sequence and record hash at the next sequence, recomputes metadata readback hash, then validates. It imports no row from an unknown or mismatched store. The first post-replacement database operation is either read-only validation or a normal CAS against the preserved exact current state/version.

Reinitialization inserts the registry plus: one sequence-1 `TX-STORE-REINITIALIZE` commit/idempotency row; metadata cursor 1 with a new UUID and `RECOVERY_REQUIRED`; one open `STORE_REINITIALIZE` recovery row carrying the external `REINITIALIZE_PREPARED` sequence and record hash; one open `RECOVERY_REQUIRED` store incident carrying that same record hash; initialization transition `NONE -> SUPERVISOR_STORE_FAILED` version 1 with NULL generation/epoch; matching `listener_current`; PERSISTENCE=`HEALTH_STORE_CORRUPT` and the other four dimensions=`HEALTH_STARTUP_UNPROVEN`, all with NULL generation/epoch/bridge; and aggregate `HEALTH_CORRUPT`. It inserts zero positive authority rows and zero projection cursors. The first post-replacement mutation is `TX-SUP-GENERATION-CREATE` against metadata cursor 1, not a CAS against a nonexistent generation. After the new lease/process/zero-authority reconciliation, `TX-STORE-RECOVERY-COMPLETE` closes recovery/incident and moves the explicit version-1 listener baseline to `STOPPED` version 2. Any failure rolls back that transaction and leaves the baseline fail-closed.

Entry Session recovery is cross-store and cannot use a Runtime Authority Store FK. A newly initialized Entry Session store receives `TX-ENTRY-STORE-RECOVERY-INITIALIZE`: authenticated external evidence identifies the unavailable prior store/hash; Session-lock policy classifies fail-closed and selects `NO_CURRENT_SESSION_CONTEXT`; Entry Agent Session Commit Writer, as sole writer/executor, inserts version 1 from source token `NONE`. Restore instead preserves the authenticated prior state/version and its first policy-authorized CAS uses that exact version. A failed initialization leaves no current Entry Session row and opening entry remains prohibited.

No current staged migration verification exists. Any migration transform, evidence type, or test is future-only under `FUTURE SEPARATELY GOVERNED PREDECESSOR-BOUND MIGRATION SPECIFICATION` and is not a Phase 3C1-R2 executable obligation.

## 15. Verification and governance boundary

Phase 3C1-R2 isolated validation must execute the SQL only against temporary databases; introspect every table/column/key/FK/action/index/trigger; run `integrity_check` and `foreign_key_check`; exercise every F6 trigger and its missing/duplicate/cross-identity/stale/gap/conflict/NONE/UNKNOWN/concrete/integrity cases; and rerun the accepted F1–F5/F7/F8 schema regressions without reopening their contracts.

Those are document/schema validation exercises only. They are not production implementation, runtime verification, deployment, readiness, or trading authorization. Full semantic clause-to-scenario traceability is intentionally deferred to Phase 3C2 and is not approval-ready. Phase 3C2 may use only hashes accepted by an independent Phase 3C1-R2 review.
