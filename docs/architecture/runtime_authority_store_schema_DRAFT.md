# Runtime Authority Store Schema and Typed Transaction Contract

Version: Draft 0.1 — Phase 3B

Status: **DRAFT — NONCANONICAL — NOT APPROVED**

Implementation Authorization: None

Runtime Verification Status: Not authorized and not performed

Governing proposal: ADR-015 and ADR-016 remain unapproved. Approved ADR-014 is unchanged and its Entry Session store remains outside this database.

## 1. Scope and invariants

This contract defines the complete logical schema and typed transaction catalog for:

```text
%LOCALAPPDATA%\RandleRuntimeData\control\runtime_authority_v1.sqlite3
```

The path SHALL be resolved once, converted to an absolute path, and recorded in startup evidence. The database SHALL NOT reside in a shared or synchronized projection root. It is the sole durable store for Listener Supervisor identity, listener epochs and lifecycle, restart incidents, Bridge Generations and lifecycle, feed-health control state, termination evidence, and market-data expectation. It SHALL NOT contain or duplicate the ADR-014 Entry Session Aggregate or its active pointer.

One physical database does not merge domain authority. Every mutation SHALL name one registered logical writer and one authorized typed transaction. The Runtime Authority Store Transaction Coordinator performs only mechanical database work.

## 2. Database contract

| Item | Normative value |
|---|---|
| Schema identity | `RANDLE_RUNTIME_AUTHORITY_SCHEMA_V2` |
| `PRAGMA user_version` | `2` |
| Migration identity | `RASTORE-MIG-002` |
| Minimum SQLite | `3.37.0`, including STRICT tables, UPSERT, partial indexes, and deferred same-database foreign keys |
| `application_id` | hexadecimal `0x52484C54` |
| Journal mode | `WAL` |
| Synchronous mode | `FULL` |
| Foreign keys | `PRAGMA foreign_keys=ON` on every connection before any statement |
| Locking | `NORMAL`; one read-write coordinator connection; read-only snapshot connections only after commit |
| Busy timeout | exactly `5000` milliseconds |
| Transaction start | `BEGIN IMMEDIATE` |
| Isolation | serializable single-writer order supplied by the coordinator; no read-uncommitted connection |
| Text encoding | UTF-8 |
| Time representation | UTC RFC3339 text with `Z`; authoritative ordering uses integer sequences, never wall-clock order alone |
| Identity representation | lowercase canonical UUID text unless a table specifies an integer sequence |
| Integrity hashes | lowercase 64-character SHA-256 hexadecimal text |

Every table SHALL be STRICT. Boolean values SHALL be INTEGER with `CHECK(value IN (0,1))`. Enum values SHALL use the exact checks below. JSON values SHALL be canonical UTF-8 JSON text with sorted keys and no insignificant whitespace; their SHA-256 SHALL be stored beside the JSON where the record is evidence-bearing.

### 2.1 Schema identity and startup validation

`store_metadata.schema_hash` SHALL equal the SHA-256 of the canonical ordered schema manifest consisting of every table, column, type, nullability rule, primary key, unique constraint, foreign key, check constraint, index, and writer-registry row defined by this document. The startup validator SHALL:

1. open the database read-only first;
2. verify the resolved path is outside every configured projection root;
3. verify SQLite version is at least `3.37.0`;
4. verify `application_id=0x52484C54`, `user_version=2`, schema identity, migration identity, and schema hash;
5. compare normalized `sqlite_schema` rows to the canonical manifest;
6. open the sole coordinator write connection and set/verify every pragma in section 2;
7. execute `PRAGMA quick_check` and require the sole row `ok`;
8. execute `PRAGMA foreign_key_check` and require zero rows;
9. verify the writer-registry digest and every active writer mapping;
10. verify all partial-unique current-row indexes, transaction cursor continuity, idempotency records, current ancestry, and current-state/last-transition versions;
11. reconstruct section 10 state without consulting projections or process existence; and
12. return exactly `VERIFIED_CURRENT`, `RECOVERY_REQUIRED`, or `FAILED` with a durable validation evidence identity.

A missing database is not an empty valid database during production recovery. Creation is legal only in a separately authorized first-install or governed reinitialization transaction. A higher `user_version`, unknown schema hash, failed migration, failed integrity check, missing table/column/index, unauthorized writer row, or downgrade request SHALL return `RECOVERY_REQUIRED`, prohibit listener/bridge start, and create no replacement database.

### 2.2 Migration and corruption

Migration SHALL run only from a specifically listed predecessor schema under an approved migration artifact whose hash is deployment-bound. `RASTORE-MIG-002` accepts only predecessor `user_version=1` with its approved schema hash. The migration SHALL copy to a new local candidate database, validate the complete section 2.1 sequence, preserve store UUID and all immutable identities, atomically activate the candidate before its first production commit, and retain the original as a read-only rollback source. Rollback is prohibited after the first version-2 production commit. Downgrade is prohibited.

Failed integrity, undecodable canonical JSON, checksum mismatch, impossible transition, broken sequence, duplicate current row, or invalid parent identity SHALL classify the store `HEALTH_STORE_CORRUPT` and the listener domain `SUPERVISOR_STORE_FAILED`. The owning recovery command SHALL quarantine the database and WAL/SHM sidecars with an immutable manifest. Projection JSON, process memory, status output, or an empty database SHALL NOT restore authority.

## 3. Common column rules

The following exact types are reused below:

- `UUID`: canonical lower-case RFC-4122 text, default `TEXT NOT NULL CHECK(length(value)=36)`.
- `SHA256`: `TEXT NOT NULL CHECK(length(value)=64 AND value=lower(value))`.
- `UTC`: `TEXT NOT NULL CHECK(substr(value,-1,1)='Z')`.
- `SEQ`: `INTEGER NOT NULL CHECK(value>=0)`.
- `VERSION`: `INTEGER NOT NULL CHECK(value>=1)`.

The explicit `NULL` modifier on a column overrides a type alias's default `NOT NULL`; every other alias use retains the alias nullability. No omitted modifier is implementation choice.

“Immutable” means an UPDATE trigger SHALL reject any change to that column. Every table without an explicitly mutable column is append-only. Mutable current rows may change only through the named typed transactions with optimistic version comparison.

## 4. Exact table definitions

### 4.1 Mechanical store tables

#### `store_metadata`

Columns: `singleton_id INTEGER NOT NULL CHECK(singleton_id=1) PRIMARY KEY`; `store_uuid UUID`; `schema_identity TEXT NOT NULL CHECK(schema_identity='RANDLE_RUNTIME_AUTHORITY_SCHEMA_V2')`; `schema_hash SHA256`; `migration_identity TEXT NOT NULL CHECK(migration_identity='RASTORE-MIG-002')`; `writer_registry_version VERSION`; `writer_registry_hash SHA256`; `last_transaction_sequence INTEGER NOT NULL CHECK(last_transaction_sequence>=0)`; `last_transaction_id UUID NULL`; `integrity_state TEXT NOT NULL CHECK(integrity_state IN ('VERIFIED','RECOVERY_REQUIRED','CORRUPT'))`; `created_at_utc UTC`; `last_verified_at_utc UTC`.

All columns except `last_transaction_sequence`, `last_transaction_id`, `integrity_state`, `last_verified_at_utc`, `writer_registry_version`, `writer_registry_hash`, and versioned schema/migration fields during an authorized migration are immutable. The coordinator is the sole writer. Exactly one row SHALL exist.

#### `writer_registry`

Columns: `writer_id TEXT NOT NULL`; `registry_version VERSION`; `table_name TEXT NOT NULL`; `operation_mask TEXT NOT NULL CHECK(operation_mask IN ('INSERT','INSERT_UPDATE','MIGRATION_ONLY'))`; `authority_role TEXT NOT NULL`; `writer_build_hash SHA256`; `active INTEGER NOT NULL CHECK(active IN (0,1))`; `effective_transaction_sequence SEQ`; `retired_transaction_sequence INTEGER NULL CHECK(retired_transaction_sequence IS NULL OR retired_transaction_sequence>=effective_transaction_sequence)`; primary key `(writer_id,table_name,registry_version)`.

Partial unique index: one active row per `(table_name,writer_id)` where `active=1`. A writer may have multiple table rows, but no table/operation may be written by an actor absent from its active rows and the closed section 6 matrix. Only the coordinator may install rows as the mechanical step of an approved schema/writer-registry migration. Rows are immutable after installation except `active` and `retired_transaction_sequence` in that migration.

#### `transaction_commits`

Columns: `transaction_id UUID PRIMARY KEY`; `transaction_sequence INTEGER NOT NULL UNIQUE CHECK(transaction_sequence>=1)`; `transaction_type TEXT NOT NULL`; `idempotency_key TEXT NOT NULL`; `authority_decision_id UUID`; `writer_set_json TEXT NOT NULL`; `writer_set_hash SHA256`; `expected_versions_json TEXT NOT NULL`; `expected_versions_hash SHA256`; `result_versions_json TEXT NOT NULL`; `result_versions_hash SHA256`; `evidence_set_hash SHA256`; `committed_at_utc UTC`; `coordinator_build_hash SHA256`; `commit_readback_hash SHA256`.

Constraint: `UNIQUE(transaction_type,idempotency_key)`. The coordinator inserts exactly one row as the last logical write in every successful typed transaction. Rows are immutable.

#### `idempotency_records`

Columns: `transaction_type TEXT NOT NULL`; `idempotency_key TEXT NOT NULL`; `request_hash SHA256`; `status TEXT NOT NULL CHECK(status IN ('COMMITTED','REJECTED_VERSION','REJECTED_CONSTRAINT','REJECTED_ROUTING'))`; `transaction_id TEXT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `result_hash SHA256`; `created_at_utc UTC`; primary key `(transaction_type,idempotency_key)`.

The coordinator is sole writer. A repeated key with the same request hash returns the recorded result; a repeated key with a different request hash is `IDEMPOTENCY_CONFLICT` and performs no write.

### 4.2 Identity and policy tables

#### `supervisor_generations`

Columns: `supervisor_generation_id UUID PRIMARY KEY`; `generation_sequence INTEGER NOT NULL UNIQUE CHECK(generation_sequence>=1)`; `supervisor_instance_id UUID`; `process_id INTEGER NOT NULL CHECK(process_id>0)`; `process_start_utc UTC`; `build_hash SHA256`; `startup_attempt_id UUID`; `grant_transaction_id UUID REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `started_at_utc UTC`; `fenced_at_utc TEXT NULL CHECK(fenced_at_utc IS NULL OR substr(fenced_at_utc,-1,1)='Z')`; `fence_reason TEXT NULL`; `state TEXT NOT NULL CHECK(state IN ('CURRENT','FENCED','RETIRED'))`.

Partial uniqueness: exactly one row with `state='CURRENT'`. Immutable except `fenced_at_utc`, `fence_reason`, and `state`. Owner: Listener Supervisor. Writer: Supervisor Generation Writer.

#### `supervisor_leases`

Columns: `lease_id UUID PRIMARY KEY`; `supervisor_generation_id UUID NOT NULL REFERENCES supervisor_generations(supervisor_generation_id)`; `lease_version VERSION`; `lease_token_hash SHA256 UNIQUE`; `acquired_monotonic_ns INTEGER NOT NULL CHECK(acquired_monotonic_ns>=0)`; `expires_monotonic_ns INTEGER NOT NULL CHECK(expires_monotonic_ns>acquired_monotonic_ns)`; `lease_state TEXT NOT NULL CHECK(lease_state IN ('HELD','RELEASED','EXPIRED','FENCED'))`; `last_renew_transaction_id UUID REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `updated_at_utc UTC`.

Partial uniqueness: one `HELD` lease per supervisor generation and one `HELD` lease globally. Mutable fields: version, expiry, state, last-renew transaction, update time. Owner/writer: Listener Supervisor / Supervisor Generation Writer.

#### `shared_feed_policies`

Columns: `policy_identity UUID PRIMARY KEY`; `policy_version VERSION`; `policy_sha256 SHA256 UNIQUE`; `schema_version VERSION`; `topology TEXT NOT NULL CHECK(topology='ONE_PHYSICAL_FEED_NQ_YM')`; `canonical_json TEXT NOT NULL`; `validation_disposition TEXT NOT NULL CHECK(validation_disposition IN ('POLICY_VALID','SHARED_FEED_POLICY_INVALID'))`; `validation_reason TEXT NOT NULL`; `deployment_authorization_id UUID`; `approved_at_utc UTC`; `validation_transaction_id UUID REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `active INTEGER NOT NULL CHECK(active IN (0,1))`.

Partial uniqueness: one active `POLICY_VALID` row. All fields immutable except `active`, which changes only when another validated deployment-bound policy activates. Owner: Listener Supervision Policy Owner. Evaluator: Policy Evaluator. Writer: Listener Incident Writer.

#### `active_contract_sessions`

Columns: `contract_session_ref_id UUID PRIMARY KEY`; `symbol TEXT NOT NULL CHECK(symbol IN ('NQ','YM'))`; `contract_id TEXT NOT NULL`; `session_id TEXT NOT NULL`; `session_date TEXT NOT NULL CHECK(length(session_date)=10)`; `session_rollover_commit_id UUID`; `source_authority TEXT NOT NULL CHECK(source_authority='ADR014_ENTRY_SESSION_STORE')`; `source_record_hash SHA256`; `validated_transaction_id UUID REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `valid_from_sequence SEQ`; `valid_to_sequence INTEGER NULL CHECK(valid_to_sequence IS NULL OR valid_to_sequence>valid_from_sequence)`.

Uniqueness: `UNIQUE(symbol,contract_id,session_id,session_rollover_commit_id)` and one row per symbol with `valid_to_sequence IS NULL`. This is a validated reference, not a second Entry Session authority. Owner remains Entry Agent Session Commit Writer outside this database. Health Durable Writer records the validated reference; it cannot change its source facts.

#### `listener_epochs`

Columns: `listener_epoch_id UUID PRIMARY KEY`; `epoch_sequence INTEGER NOT NULL UNIQUE CHECK(epoch_sequence>=1)`; `supervisor_generation_id UUID NOT NULL REFERENCES supervisor_generations(supervisor_generation_id)`; `listener_process_instance_id UUID`; `process_id INTEGER NOT NULL CHECK(process_id>0)`; `process_start_utc UTC`; `contract_set_hash SHA256`; `grant_token_hash SHA256 UNIQUE`; `grant_transaction_id UUID REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `granted_at_utc UTC`; `fenced_at_utc TEXT NULL CHECK(fenced_at_utc IS NULL OR substr(fenced_at_utc,-1,1)='Z')`; `state TEXT NOT NULL CHECK(state IN ('GRANTED','CURRENT','FENCED','RETIRED'))`.

Partial uniqueness: one row with `state='CURRENT'`. Immutable except `fenced_at_utc` and `state`. Owner: Listener Supervisor. Writer: Listener Epoch Writer.

#### `recovery_transactions`

Columns: `recovery_transaction_id UUID PRIMARY KEY`; `recovery_type TEXT NOT NULL CHECK(recovery_type IN ('LISTENER_RESTART','LISTENER_ADOPTION','BRIDGE_RECYCLE','COLD_START','STORE_RECOVERY'))`; `supervisor_generation_id UUID NOT NULL REFERENCES supervisor_generations(supervisor_generation_id)`; `listener_epoch_id UUID NULL REFERENCES listener_epochs(listener_epoch_id)`; `bridge_generation_id UUID NULL REFERENCES bridge_generations(bridge_generation_id) DEFERRABLE INITIALLY DEFERRED`; `listener_restart_incident_id UUID NULL REFERENCES listener_restart_incidents(restart_incident_id) DEFERRABLE INITIALLY DEFERRED`; `bridge_incident_id UUID NULL REFERENCES bridge_incidents(bridge_incident_id) DEFERRABLE INITIALLY DEFERRED`; `state TEXT NOT NULL CHECK(state IN ('OPEN','ACKNOWLEDGING','COMPLETED','FAILED','CANCELED'))`; `required_domain_set_hash SHA256`; `opened_transaction_id UUID REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `closed_transaction_id UUID NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `state_version VERSION`; `opened_at_utc UTC`; `closed_at_utc TEXT NULL CHECK(closed_at_utc IS NULL OR substr(closed_at_utc,-1,1)='Z')`.

Scope check: listener restart/adoption requires non-NULL `listener_epoch_id` and may reference only `listener_restart_incident_id`; bridge recycle requires all of `listener_epoch_id`, `bridge_generation_id`, and `bridge_incident_id` and requires NULL `listener_restart_incident_id`; cold/start-store recovery requires both incident columns NULL unless a separately enumerated typed transaction says otherwise. Partial uniqueness: at most one OPEN/ACKNOWLEDGING listener recovery per listener epoch and one per bridge generation. The foreign keys to later-declared same-database tables are present in the original `CREATE TABLE` definitions and are validated after the complete schema is installed in one migration transaction; no `ALTER TABLE ... ADD CONSTRAINT` is used. The owning listener or bridge evaluator supplies the decision; the sole table writer is Recovery Transaction Writer, which owns no decision authority.

### 4.3 Listener lifecycle tables

#### `listener_current`

Columns: `singleton_id INTEGER NOT NULL CHECK(singleton_id=1) PRIMARY KEY`; `supervisor_generation_id UUID NOT NULL REFERENCES supervisor_generations(supervisor_generation_id)`; `listener_epoch_id UUID NULL REFERENCES listener_epochs(listener_epoch_id)`; `lifecycle_state TEXT NOT NULL CHECK(lifecycle_state IN ('STOPPED','STARTING','REHYDRATING','HEALTHY','SUSPECT','FENCED','STOPPING','LISTENER_FAILED','AMBIGUOUS_PROCESS_AUTHORITY','SUPERVISOR_STORE_FAILED'))`; `state_version VERSION`; `last_transition_id UUID UNIQUE REFERENCES listener_state_transitions(listener_transition_id) DEFERRABLE INITIALLY DEFERRED`; `current_restart_incident_id UUID NULL REFERENCES listener_restart_incidents(restart_incident_id) DEFERRABLE INITIALLY DEFERRED`; `active_recovery_transaction_id UUID NULL REFERENCES recovery_transactions(recovery_transaction_id)`; `update_transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `writer_id TEXT NOT NULL CHECK(writer_id='LISTENER_STATE_WRITER')`; `committed_sequence SEQ`; `committed_at_utc UTC`.

The references to later-declared listener tables are installed in the original schema creation transaction and are physically checked after all tables exist. `listener_epoch_id` SHALL be NULL only in `STOPPED`, `STARTING`, `AMBIGUOUS_PROCESS_AUTHORITY`, or `SUPERVISOR_STORE_FAILED`. Mutable only through listener typed transactions with exact `state_version` comparison. Owner: Listener Supervisor State Evaluator. Writer: Listener State Writer.

#### `listener_state_transitions`

Columns: `listener_transition_id UUID PRIMARY KEY`; `supervisor_generation_id UUID NOT NULL REFERENCES supervisor_generations(supervisor_generation_id)`; `listener_epoch_id UUID NULL REFERENCES listener_epochs(listener_epoch_id)`; `prior_state TEXT NOT NULL`; `resulting_state TEXT NOT NULL`; `transition_reason TEXT NOT NULL`; `deciding_authority TEXT NOT NULL CHECK(deciding_authority='LISTENER_SUPERVISOR_STATE_EVALUATOR')`; `durable_writer TEXT NOT NULL CHECK(durable_writer='LISTENER_STATE_WRITER')`; `source_evidence_set_hash SHA256`; `restart_incident_id UUID NULL REFERENCES listener_restart_incidents(restart_incident_id)`; `recovery_transaction_id UUID NULL REFERENCES recovery_transactions(recovery_transaction_id)`; `transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `expected_prior_version VERSION`; `resulting_version INTEGER NOT NULL CHECK(resulting_version=expected_prior_version+1)`; `committed_at_utc UTC`.

Uniqueness: `UNIQUE(transaction_id,resulting_version)`. Append-only. Every prior/result pair SHALL be permitted by ADR-015.

#### `listener_restart_incidents`

Columns: `restart_incident_id UUID PRIMARY KEY`; `supervisor_generation_id UUID NOT NULL REFERENCES supervisor_generations(supervisor_generation_id)`; `listener_epoch_id UUID NOT NULL REFERENCES listener_epochs(listener_epoch_id)`; `incident_state TEXT NOT NULL CHECK(incident_state IN ('RESTART_PENDING','RESTART_FENCED','RESTART_EXECUTING','RESTART_REHYDRATING','TERMINAL'))`; `incident_version VERSION`; `sff_predicate TEXT NOT NULL CHECK(sff_predicate IN ('SFF-01_LISTENER_EXITED','SFF-02_LISTENER_LEASE_LOST','SFF-03_BRIDGE_RECOVERY_EXHAUSTED'))`; `observed_stale_timestamp_utc UTC`; `decision_timestamp_utc UTC`; `fencing_token_hash SHA256`; `policy_identity UUID NOT NULL REFERENCES shared_feed_policies(policy_identity)`; `attempt_count INTEGER NOT NULL CHECK(attempt_count>=0)`; `rate_window_started_utc UTC`; `evidence_set_hash SHA256`; `current_outcome_id UUID NULL REFERENCES listener_restart_outcomes(listener_outcome_id) DEFERRABLE INITIALLY DEFERRED`; `last_transition_id UUID UNIQUE REFERENCES listener_restart_incident_transitions(incident_transition_id) DEFERRABLE INITIALLY DEFERRED`; `update_transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `created_at_utc UTC`; `updated_at_utc UTC`.

The later-table references are installed in the original schema creation transaction. Mutable fields are state/version/count/outcome/last transition/update time/transaction. Writer: Listener Incident Writer.

#### `listener_restart_incident_transitions`

Columns: `incident_transition_id UUID PRIMARY KEY`; `restart_incident_id UUID NOT NULL REFERENCES listener_restart_incidents(restart_incident_id)`; `prior_incident_state TEXT NOT NULL`; `resulting_incident_state TEXT NOT NULL`; `transition_reason TEXT NOT NULL`; `deciding_authority TEXT NOT NULL CHECK(deciding_authority='LISTENER_SUPERVISOR_STATE_EVALUATOR')`; `durable_writer TEXT NOT NULL CHECK(durable_writer='LISTENER_INCIDENT_WRITER')`; `evidence_set_hash SHA256`; `transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `expected_prior_version VERSION`; `resulting_version INTEGER NOT NULL CHECK(resulting_version=expected_prior_version+1)`; `committed_at_utc UTC`.

Append-only; `UNIQUE(restart_incident_id,resulting_version)`.

#### `listener_restart_outcomes`

Columns: `listener_outcome_id UUID PRIMARY KEY`; `restart_incident_id UUID NOT NULL UNIQUE REFERENCES listener_restart_incidents(restart_incident_id)`; `outcome TEXT NOT NULL CHECK(outcome IN ('RESTART_CANCELED','RESTART_COMPLETED','RESTART_FAILED','RECOVERY_RATE_LIMITED_FAILED'))`; `resulting_listener_state TEXT NOT NULL CHECK(resulting_listener_state IN ('HEALTHY','SUSPECT','LISTENER_FAILED','FENCED','SUPERVISOR_STORE_FAILED'))`; `rate_limit_evidence_hash TEXT NULL CHECK(rate_limit_evidence_hash IS NULL OR length(rate_limit_evidence_hash)=64)`; `automatic_retry_prohibited INTEGER NOT NULL CHECK(automatic_retry_prohibited IN (0,1))`; `escalation_identity TEXT NULL`; `evidence_set_hash SHA256`; `transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `committed_at_utc UTC`.

Append-only. `RECOVERY_RATE_LIMITED_FAILED` requires non-NULL rate-limit evidence and `automatic_retry_prohibited=1`.

#### `listener_fences`

Columns: `listener_fence_id UUID PRIMARY KEY`; `restart_incident_id UUID NOT NULL UNIQUE REFERENCES listener_restart_incidents(restart_incident_id)`; `supervisor_generation_id UUID NOT NULL REFERENCES supervisor_generations(supervisor_generation_id)`; `listener_epoch_id UUID NOT NULL REFERENCES listener_epochs(listener_epoch_id)`; `fencing_token_hash SHA256 UNIQUE`; `reason TEXT NOT NULL`; `evidence_set_hash SHA256`; `transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `fenced_at_utc UTC`.

Append-only. One fence per listener incident.

#### `listener_execution_attempts`

Columns: `listener_execution_id UUID PRIMARY KEY`; `restart_incident_id UUID NOT NULL UNIQUE REFERENCES listener_restart_incidents(restart_incident_id)`; `listener_fence_id UUID NOT NULL UNIQUE REFERENCES listener_fences(listener_fence_id)`; `supervisor_generation_id UUID NOT NULL REFERENCES supervisor_generations(supervisor_generation_id)`; `attempt_number INTEGER NOT NULL CHECK(attempt_number=1)`; `child_authority_token_hash SHA256 UNIQUE`; `command_hash SHA256`; `execution_state TEXT NOT NULL CHECK(execution_state IN ('STARTED','PROCESS_STOP_CONFIRMED','REPLACEMENT_STARTED','FAILED'))`; `process_result_hash TEXT NULL CHECK(process_result_hash IS NULL OR length(process_result_hash)=64)`; `transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `started_at_utc UTC`; `completed_at_utc TEXT NULL CHECK(completed_at_utc IS NULL OR substr(completed_at_utc,-1,1)='Z')`.

Mutable only for monotonic execution-state progression and result completion. Writer: Listener Incident Writer. Exactly one execution per fenced incident.

#### `listener_rehydrations`

Columns: `listener_rehydration_id UUID PRIMARY KEY`; `recovery_transaction_id UUID NOT NULL UNIQUE REFERENCES recovery_transactions(recovery_transaction_id)`; `restart_incident_id UUID NULL REFERENCES listener_restart_incidents(restart_incident_id)`; `supervisor_generation_id UUID NOT NULL REFERENCES supervisor_generations(supervisor_generation_id)`; `listener_epoch_id UUID NOT NULL REFERENCES listener_epochs(listener_epoch_id)`; `disposition TEXT NOT NULL CHECK(disposition IN ('ADOPT_EPOCH','NEW_EPOCH','COLD_START'))`; `required_domain_set_hash SHA256`; `acknowledgement_progress_count INTEGER NOT NULL CHECK(acknowledgement_progress_count>=0)`; `required_count INTEGER NOT NULL CHECK(required_count>0 AND acknowledgement_progress_count<=required_count)`; `state TEXT NOT NULL CHECK(state IN ('OPEN','COMPLETE','FAILED'))`; `state_version VERSION`; `transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `opened_at_utc UTC`; `closed_at_utc TEXT NULL CHECK(closed_at_utc IS NULL OR substr(closed_at_utc,-1,1)='Z')`.

Mutable progress/state/version only. Writer: Listener Incident Writer.

#### `recovery_required_domains`

Columns: `recovery_transaction_id UUID NOT NULL REFERENCES recovery_transactions(recovery_transaction_id)`; `authoritative_domain TEXT NOT NULL CHECK(authoritative_domain IN ('FINALIZED_BARS','CANONICAL_RMA_ATR','EXECUTOR_INTAKE','TRADE_MANAGER_INTAKE','ENTRY_AGENT_RUNTIME'))`; `expected_domain_identity SHA256`; `required INTEGER NOT NULL CHECK(required=1)`; primary key `(recovery_transaction_id,authoritative_domain)`.

Append-only. Command Center SHALL NOT be inserted because it is not an authoritative domain. Writer: Listener Acknowledgement Writer from the rehydration-start decision.

#### `domain_acknowledgements`

Columns: `acknowledgement_id UUID PRIMARY KEY`; `recovery_transaction_id UUID NOT NULL REFERENCES recovery_transactions(recovery_transaction_id)`; `supervisor_generation_id UUID NOT NULL REFERENCES supervisor_generations(supervisor_generation_id)`; `listener_epoch_id UUID NOT NULL REFERENCES listener_epochs(listener_epoch_id)`; `authoritative_domain TEXT NOT NULL CHECK(authoritative_domain IN ('FINALIZED_BARS','CANONICAL_RMA_ATR','EXECUTOR_INTAKE','TRADE_MANAGER_INTAKE','ENTRY_AGENT_RUNTIME'))`; `expected_domain_identity SHA256`; `observed_domain_identity SHA256`; `acknowledgement_disposition TEXT NOT NULL CHECK(acknowledgement_disposition IN ('ACCEPTED','REJECTED_IDENTITY','REJECTED_INTEGRITY','REJECTED_STALE','REJECTED_UNAUTHENTICATED'))`; `evidence_hash SHA256`; `evidence_producer TEXT NOT NULL`; `validator TEXT NOT NULL CHECK(validator='HEALTH_INGRESS')`; `evaluator TEXT NOT NULL CHECK(evaluator='LISTENER_SUPERVISOR_STATE_EVALUATOR')`; `durable_writer TEXT NOT NULL CHECK(durable_writer='LISTENER_ACKNOWLEDGEMENT_WRITER')`; `creation_sequence SEQ`; `transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `created_at_utc UTC`.

Uniqueness: `UNIQUE(recovery_transaction_id,authoritative_domain,acknowledgement_disposition,observed_domain_identity)`. Partial unique index: one row per `(recovery_transaction_id,authoritative_domain)` where disposition is `ACCEPTED`. An accepted row requires a matching `recovery_required_domains` row and equality of expected and observed identities. Append-only.

### 4.4 Bridge lifecycle tables

#### `bridge_generations`

Columns: `bridge_generation_id UUID PRIMARY KEY`; `bridge_generation_sequence INTEGER NOT NULL CHECK(bridge_generation_sequence>=1)`; `listener_epoch_id UUID NOT NULL REFERENCES listener_epochs(listener_epoch_id)`; `supervisor_generation_id UUID NOT NULL REFERENCES supervisor_generations(supervisor_generation_id)`; `grant_token_hash SHA256 UNIQUE`; `controller_capability_hash SHA256`; `grant_transaction_id UUID REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `state TEXT NOT NULL CHECK(state IN ('GRANTED','CURRENT','FENCED','RETIRED'))`; `granted_at_utc UTC`; `fenced_at_utc TEXT NULL CHECK(fenced_at_utc IS NULL OR substr(fenced_at_utc,-1,1)='Z')`; unique `(listener_epoch_id,bridge_generation_sequence)`.

Partial uniqueness: one CURRENT generation per listener epoch. Owner: Supervisor State Evaluator. Writer: Bridge Generation Writer.

#### `bridge_current`

Columns: `singleton_id INTEGER NOT NULL CHECK(singleton_id=1) PRIMARY KEY`; `supervisor_generation_id UUID NOT NULL REFERENCES supervisor_generations(supervisor_generation_id)`; `listener_epoch_id UUID NOT NULL REFERENCES listener_epochs(listener_epoch_id)`; `bridge_generation_id UUID NOT NULL REFERENCES bridge_generations(bridge_generation_id)`; `bridge_state TEXT NOT NULL CHECK(bridge_state IN ('BRIDGE_STARTUP_UNPROVEN','BRIDGE_STARTING','BRIDGE_READY','BRIDGE_SUSPECT','RECYCLE_PENDING','RECYCLE_CANCELED','BRIDGE_FENCED','RECYCLE_EXECUTING','BRIDGE_REHYDRATING','BRIDGE_FAILED','FAILED_RECOVERY_EXHAUSTED','PLANNED_SHUTDOWN','LISTENER_EPOCH_TRANSITION'))`; `state_version VERSION`; `current_bridge_incident_id UUID NULL REFERENCES bridge_incidents(bridge_incident_id) DEFERRABLE INITIALLY DEFERRED`; `last_transition_id UUID UNIQUE REFERENCES bridge_transitions(bridge_transition_id) DEFERRABLE INITIALLY DEFERRED`; `update_transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `committed_sequence SEQ`; `committed_at_utc UTC`.

The later-table references are installed in the original schema creation transaction. Mutable only through bridge typed transactions. Owner: Supervisor State Evaluator. Writer: Health Durable Writer.

#### `bridge_transitions`

Columns: `bridge_transition_id UUID PRIMARY KEY`; `bridge_generation_id UUID NOT NULL REFERENCES bridge_generations(bridge_generation_id)`; `prior_state TEXT NOT NULL`; `resulting_state TEXT NOT NULL`; `reason TEXT NOT NULL`; `deciding_authority TEXT NOT NULL CHECK(deciding_authority='LISTENER_SUPERVISOR_STATE_EVALUATOR')`; `durable_writer TEXT NOT NULL CHECK(durable_writer='HEALTH_DURABLE_WRITER')`; `bridge_incident_id UUID NULL REFERENCES bridge_incidents(bridge_incident_id) DEFERRABLE INITIALLY DEFERRED`; `evidence_set_hash SHA256`; `transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `expected_prior_version VERSION`; `resulting_version INTEGER NOT NULL CHECK(resulting_version=expected_prior_version+1)`; `committed_at_utc UTC`.

`UNIQUE(bridge_generation_id,resulting_version)`. Append-only. The later-table reference is installed in the original schema creation transaction.

#### `bridge_incidents`

Columns: `bridge_incident_id UUID PRIMARY KEY`; `supervisor_generation_id UUID NOT NULL REFERENCES supervisor_generations(supervisor_generation_id)`; `listener_epoch_id UUID NOT NULL REFERENCES listener_epochs(listener_epoch_id)`; `bridge_generation_id UUID NOT NULL REFERENCES bridge_generations(bridge_generation_id)`; `incident_state TEXT NOT NULL CHECK(incident_state IN ('RECYCLE_PENDING','BRIDGE_FENCED','RECYCLE_EXECUTING','BRIDGE_REHYDRATING','TERMINAL'))`; `incident_version VERSION`; `bdp_predicate TEXT NOT NULL CHECK(bdp_predicate IN ('BDP-01_UNEXPECTED_PROCESS_EXIT','BDP-02_AUTH_FAILURE','BDP-03_CONNECTION_FAILURE','BDP-04_SUBSCRIPTION_FAILURE'))`; `policy_identity UUID NOT NULL REFERENCES shared_feed_policies(policy_identity)`; `attempt_count INTEGER NOT NULL CHECK(attempt_count>=0)`; `deadline_utc UTC`; `evidence_set_hash SHA256`; `current_outcome_id UUID NULL REFERENCES bridge_outcomes(bridge_outcome_id) DEFERRABLE INITIALLY DEFERRED`; `last_transition_id UUID UNIQUE REFERENCES bridge_transitions(bridge_transition_id) DEFERRABLE INITIALLY DEFERRED`; `update_transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `created_at_utc UTC`; `updated_at_utc UTC`.

The later-table references are installed in the original schema creation transaction. Mutable incident fields only. Writer: Health Durable Writer.

#### `bridge_recycle_attempts`

Columns: `bridge_attempt_id UUID PRIMARY KEY`; `bridge_incident_id UUID NOT NULL REFERENCES bridge_incidents(bridge_incident_id)`; `attempt_number INTEGER NOT NULL CHECK(attempt_number>=1)`; `bridge_generation_id UUID NOT NULL REFERENCES bridge_generations(bridge_generation_id)`; `command_hash SHA256`; `fencing_token_hash SHA256 UNIQUE`; `controller_ack_hash TEXT NULL CHECK(controller_ack_hash IS NULL OR length(controller_ack_hash)=64)`; `execution_result TEXT NULL CHECK(execution_result IS NULL OR execution_result IN ('READY','FAILED','TIMED_OUT','CANCELED'))`; `transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `started_at_utc UTC`; `completed_at_utc TEXT NULL CHECK(completed_at_utc IS NULL OR substr(completed_at_utc,-1,1)='Z')`; unique `(bridge_incident_id,attempt_number)`.

Writer: Health Durable Writer. Bridge Controller is evidence producer/executor only.

#### `bridge_outcomes`

Columns: `bridge_outcome_id UUID PRIMARY KEY`; `bridge_incident_id UUID NOT NULL UNIQUE REFERENCES bridge_incidents(bridge_incident_id)`; `outcome TEXT NOT NULL CHECK(outcome IN ('RECYCLE_CANCELED','BRIDGE_READY','BRIDGE_FAILED','FAILED_RECOVERY_EXHAUSTED','PLANNED_SHUTDOWN','LISTENER_EPOCH_TRANSITION'))`; `resulting_bridge_state TEXT NOT NULL`; `automatic_retry_prohibited INTEGER NOT NULL CHECK(automatic_retry_prohibited IN (0,1))`; `rate_or_deadline_evidence_hash TEXT NULL CHECK(rate_or_deadline_evidence_hash IS NULL OR length(rate_or_deadline_evidence_hash)=64)`; `escalation_identity TEXT NULL`; `evidence_set_hash SHA256`; `transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `committed_at_utc UTC`.

Append-only. `FAILED_RECOVERY_EXHAUSTED` requires retry prohibited and non-NULL rate/deadline evidence.

### 4.5 Health, subscription, termination, and expectation tables

#### `producer_registrations`

Columns: `producer_instance_id UUID PRIMARY KEY`; `producer_role TEXT NOT NULL CHECK(producer_role IN ('RITHMIC_LISTENER','BRIDGE_CONTROLLER','EXECUTOR','TRADE_MANAGER','ENTRY_AGENT','OS_ADAPTER','RAPI_ADAPTER','CLOCK_ADAPTER'))`; `process_id INTEGER NOT NULL CHECK(process_id>0)`; `process_start_utc UTC`; `build_hash SHA256`; `capability_key_id UUID`; `scope_json TEXT NOT NULL`; `issued_sequence SEQ`; `revoked_sequence INTEGER NULL CHECK(revoked_sequence IS NULL OR revoked_sequence>issued_sequence)`; `registration_transaction_id UUID REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`.

Unique `(producer_role,process_id,process_start_utc)`. Health Durable Writer records evaluator-approved registrations; secrets are not stored.

#### `health_events`

Columns: `health_event_id UUID PRIMARY KEY`; `producer_instance_id UUID NOT NULL REFERENCES producer_registrations(producer_instance_id)`; `producer_sequence INTEGER NOT NULL CHECK(producer_sequence>=1)`; `supervisor_generation_id UUID NOT NULL REFERENCES supervisor_generations(supervisor_generation_id)`; `listener_epoch_id UUID NOT NULL REFERENCES listener_epochs(listener_epoch_id)`; `bridge_generation_id TEXT NULL REFERENCES bridge_generations(bridge_generation_id)`; `fact_type TEXT NOT NULL`; `scope_key TEXT NOT NULL`; `canonical_event_json TEXT NOT NULL`; `event_sha256 SHA256`; `observed_monotonic_ns INTEGER NOT NULL CHECK(observed_monotonic_ns>=0)`; `observed_at_utc UTC`; `ingress_sequence SEQ`; `authentication_disposition TEXT NOT NULL CHECK(authentication_disposition IN ('AUTHENTICATED','REJECTED'))`; `transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; unique `(producer_instance_id,producer_sequence)`.

Append-only. Only AUTHENTICATED events may support a positive transition.

#### `health_current`

Columns: `health_dimension TEXT NOT NULL CHECK(health_dimension IN ('PERSISTENCE','TRANSPORT','AUTHENTICATION','AUTHORITY_COHERENCE','TIME_AUTHORITY'))`; `scope_key TEXT NOT NULL CHECK(scope_key IN ('GLOBAL','NQ_YM_SHARED_FEED'))`; `health_state TEXT NOT NULL CHECK(health_state IN ('HEALTH_STARTUP_UNPROVEN','HEALTH_PERSISTENCE_READY','HEALTH_PERSISTENCE_DEGRADED','HEALTH_STORE_CORRUPT','HEALTH_TRANSPORT_READY','HEALTH_TRANSPORT_DEGRADED','HEALTH_AUTHENTICATION_READY','HEALTH_AUTHENTICATION_FAILED','HEALTH_AUTHORITY_COHERENT','HEALTH_AUTHORITY_DIVERGED','HEALTH_TIME_AUTHORITY_READY','HEALTH_TIME_AUTHORITY_DEGRADED'))`; `state_version VERSION`; `supervisor_generation_id UUID NOT NULL REFERENCES supervisor_generations(supervisor_generation_id)`; `listener_epoch_id UUID NULL REFERENCES listener_epochs(listener_epoch_id)`; `bridge_generation_id UUID NULL REFERENCES bridge_generations(bridge_generation_id)`; `last_transition_id UUID UNIQUE NULL REFERENCES health_transitions(health_transition_id) DEFERRABLE INITIALLY DEFERRED`; `source_event_id UUID NULL REFERENCES health_events(health_event_id)`; `update_transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `committed_sequence SEQ`; `committed_at_utc UTC`; primary key `(health_dimension,scope_key)`.

The state SHALL belong to its dimension: persistence states only in PERSISTENCE, transport states only in TRANSPORT, authentication states only in AUTHENTICATION, coherence states only in AUTHORITY_COHERENCE, and time states only in TIME_AUTHORITY. Scope is closed: PERSISTENCE and TIME_AUTHORITY use only `GLOBAL`; TRANSPORT, AUTHENTICATION, and AUTHORITY_COHERENCE use only `NQ_YM_SHARED_FEED`. Exactly those five primary-key rows form the aggregate input. `HEALTH_STARTUP_UNPROVEN`, `HEALTH_PERSISTENCE_DEGRADED`, and `HEALTH_STORE_CORRUPT` may have NULL listener/bridge/source-event identities only during cold initialization or governed store recovery; every ready/coherent state and every other degraded/failed/diverged state requires a non-NULL listener epoch, applicable bridge generation, last transition, and authenticated source event. Mutable only through `TX-HEALTH-DIMENSION-UPDATE`.

#### `health_transitions`

Columns: `health_transition_id UUID PRIMARY KEY`; `health_dimension TEXT NOT NULL`; `scope_key TEXT NOT NULL`; `prior_state TEXT NOT NULL`; `resulting_state TEXT NOT NULL`; `reason TEXT NOT NULL`; `source_event_id UUID NOT NULL REFERENCES health_events(health_event_id)`; `deciding_authority TEXT NOT NULL CHECK(deciding_authority='LISTENER_SUPERVISOR_STATE_EVALUATOR')`; `durable_writer TEXT NOT NULL CHECK(durable_writer='HEALTH_DURABLE_WRITER')`; `transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `expected_prior_version VERSION`; `resulting_version INTEGER NOT NULL CHECK(resulting_version=expected_prior_version+1)`; `committed_at_utc UTC`; foreign key `(health_dimension,scope_key)` references `health_current(health_dimension,scope_key)` DEFERRABLE INITIALLY DEFERRED; unique `(health_dimension,scope_key,resulting_version)`.

Append-only.

#### `health_aggregate`

Columns: `singleton_id INTEGER NOT NULL CHECK(singleton_id=1) PRIMARY KEY`; `aggregate_state TEXT NOT NULL CHECK(aggregate_state IN ('HEALTH_READY','HEALTH_DEGRADED','HEALTH_CORRUPT','HEALTH_STARTUP_UNPROVEN'))`; `aggregate_version VERSION`; `dimension_set_hash SHA256`; `blocking_dimension_set_json TEXT NOT NULL`; `blocking_dimension_set_hash SHA256`; `update_transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `committed_sequence SEQ`; `committed_at_utc UTC`.

Derivation is closed: any CORRUPT dimension -> `HEALTH_CORRUPT`; else any DEGRADED/FAILED/DIVERGED dimension -> `HEALTH_DEGRADED`; else any STARTUP_UNPROVEN dimension -> `HEALTH_STARTUP_UNPROVEN`; only all five ready/coherent states -> `HEALTH_READY`. Health Durable Writer updates this row atomically with one dimension transition.

#### `subscription_verifications`

Columns: `subscription_verification_id UUID PRIMARY KEY`; `symbol TEXT NOT NULL CHECK(symbol IN ('NQ','YM'))`; `contract_session_ref_id UUID NOT NULL REFERENCES active_contract_sessions(contract_session_ref_id)`; `supervisor_generation_id UUID NOT NULL REFERENCES supervisor_generations(supervisor_generation_id)`; `listener_epoch_id UUID NOT NULL REFERENCES listener_epochs(listener_epoch_id)`; `bridge_generation_id UUID NOT NULL REFERENCES bridge_generations(bridge_generation_id)`; `source_health_event_id UUID NOT NULL REFERENCES health_events(health_event_id)`; `proof_producer_id UUID NOT NULL REFERENCES producer_registrations(producer_instance_id)`; `validator TEXT NOT NULL CHECK(validator='HEALTH_INGRESS')`; `evaluator TEXT NOT NULL CHECK(evaluator='LISTENER_SUPERVISOR_STATE_EVALUATOR')`; `disposition TEXT NOT NULL CHECK(disposition IN ('SUBSCRIPTION_VERIFIED','REJECTED'))`; `evidence_hash SHA256`; `transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `verified_at_utc UTC`.

Partial uniqueness: one `SUBSCRIPTION_VERIFIED` row per `(symbol,contract_session_ref_id,bridge_generation_id)`. Append-only. Only an authenticated Rithmic listener event may produce positive proof.

#### `termination_evidence`

Columns: `termination_evidence_id UUID PRIMARY KEY`; `bridge_generation_id UUID NOT NULL REFERENCES bridge_generations(bridge_generation_id)`; `producer_instance_id UUID NOT NULL REFERENCES producer_registrations(producer_instance_id)`; `evidence_type TEXT NOT NULL CHECK(evidence_type IN ('RAPI_CALLBACK','PROCESS_EXIT','PROCESS_EXCEPTION','SUPERVISOR_COMMAND','OPERATOR_COMMAND','OS_HANDLE','LISTENER_SHUTDOWN','STARTUP_TRANSITION'))`; `canonical_evidence_json TEXT NOT NULL`; `evidence_sha256 SHA256`; `authentication_disposition TEXT NOT NULL CHECK(authentication_disposition IN ('AUTHENTICATED','REJECTED'))`; `observed_at_utc UTC`; `observed_monotonic_ns INTEGER NOT NULL CHECK(observed_monotonic_ns>=0)`; `transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`.

Append-only.

#### `termination_results`

Columns: `termination_result_id UUID PRIMARY KEY`; `bridge_generation_id UUID NOT NULL UNIQUE REFERENCES bridge_generations(bridge_generation_id)`; `initiator TEXT NOT NULL`; `requested_action TEXT NOT NULL`; `execution_method TEXT NOT NULL`; `observed_cause TEXT NOT NULL`; `result TEXT NOT NULL`; `initiator_evidence_set_hash SHA256`; `requested_action_evidence_set_hash SHA256`; `execution_method_evidence_set_hash SHA256`; `observed_cause_evidence_set_hash SHA256`; `result_evidence_set_hash SHA256`; `evaluator TEXT NOT NULL CHECK(evaluator='LISTENER_SUPERVISOR_STATE_EVALUATOR')`; `durable_writer TEXT NOT NULL CHECK(durable_writer='HEALTH_DURABLE_WRITER')`; `classification_version VERSION`; `transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `classified_at_utc UTC`.

Each semantic field SHALL contain a concrete governed value, `NONE`, or `UNKNOWN` under ADR-016. Append-only per generation; corrected evidence requires a new bridge generation or a separately governed superseding evidence record, never in-place reinterpretation.

#### `market_data_expectations`

Columns: `expectation_id UUID PRIMARY KEY`; `symbol TEXT NOT NULL CHECK(symbol IN ('NQ','YM'))`; `contract_session_ref_id UUID NOT NULL REFERENCES active_contract_sessions(contract_session_ref_id)`; `policy_identity UUID NOT NULL REFERENCES shared_feed_policies(policy_identity)`; `supervisor_generation_id UUID NOT NULL REFERENCES supervisor_generations(supervisor_generation_id)`; `listener_epoch_id UUID NOT NULL REFERENCES listener_epochs(listener_epoch_id)`; `expectation_state TEXT NOT NULL CHECK(expectation_state IN ('EXPECTATION_STARTUP_UNPROVEN','DATA_EXPECTED','DATA_NOT_EXPECTED','EXPECTATION_EXPIRED'))`; `calendar_identity SHA256`; `subscription_intent_identity SHA256`; `clock_evidence_hash SHA256`; `valid_from_utc UTC`; `expires_at_utc UTC`; `current INTEGER NOT NULL CHECK(current IN (0,1))`; `evaluation_transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `evaluated_at_utc UTC`.

Check: `expires_at_utc > valid_from_utc`. Partial unique index: one row per `(symbol,listener_epoch_id)` where `current=1`. A new evaluation transaction atomically clears the prior current flag and inserts the successor; wall-clock expiration changes the state to `EXPECTATION_EXPIRED` through `TX-EXPECTATION-EVALUATE`, never through an index predicate. Rows are otherwise append-only. Owner: Market Data Expectation Evaluator; writer: Listener Incident Writer.

#### `projection_cursors`

Columns: `projection_name TEXT NOT NULL`; `scope_key TEXT NOT NULL`; `source_transaction_sequence SEQ`; `published_transaction_sequence SEQ`; `source_hash SHA256`; `projection_hash SHA256`; `publication_state TEXT NOT NULL CHECK(publication_state IN ('PENDING','PUBLISHED','FAILED'))`; `last_attempt_utc UTC`; `transaction_id UUID NOT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; primary key `(projection_name,scope_key)`.

Health Durable Writer is sole writer. These cursors have no control or readiness authority.

#### `store_incidents`

Columns: `store_incident_id UUID PRIMARY KEY`; `incident_type TEXT NOT NULL CHECK(incident_type IN ('WRITE_FAILED','READBACK_FAILED','CORRUPTION','SCHEMA_MISMATCH','WRITER_ROUTING_FAILED','VERSION_CONFLICT','MISSING_PARENT','MIGRATION_FAILED','RECOVERY_REQUIRED'))`; `affected_table TEXT NOT NULL`; `affected_identity TEXT NOT NULL`; `last_verified_transaction_sequence SEQ`; `evidence_hash SHA256`; `disposition TEXT NOT NULL CHECK(disposition IN ('OPEN','QUARANTINED','RECOVERED','FAILED'))`; `recovery_authorization_id TEXT NULL`; `transaction_id TEXT NULL REFERENCES transaction_commits(transaction_id) DEFERRABLE INITIALLY DEFERRED`; `created_at_utc UTC`; `closed_at_utc TEXT NULL CHECK(closed_at_utc IS NULL OR substr(closed_at_utc,-1,1)='Z')`.

Store Incident Writer is the sole table writer and records only a classification already decided by the affected domain evaluator or governed recovery authority. It owns no lifecycle, health, schema-recovery, or readiness decision. Open incidents survive restart and block the affected authority.

### 4.6 Closed index and constraint-trigger catalog

The following partial indexes SHALL exist under these exact names and predicates in addition to inline primary/unique constraints:

| Index name | Exact unique key and predicate |
|---|---|
| `uq_writer_registry_active_table_writer` | UNIQUE `(table_name,writer_id)` WHERE `active=1` |
| `uq_supervisor_generation_current` | UNIQUE `(state)` WHERE `state='CURRENT'` |
| `uq_supervisor_lease_held_generation` | UNIQUE `(supervisor_generation_id)` WHERE `lease_state='HELD'` |
| `uq_supervisor_lease_held_global` | UNIQUE `(lease_state)` WHERE `lease_state='HELD'` |
| `uq_shared_feed_policy_active_valid` | UNIQUE `(active)` WHERE `active=1 AND validation_disposition='POLICY_VALID'` |
| `uq_active_contract_session_current_symbol` | UNIQUE `(symbol)` WHERE `valid_to_sequence IS NULL` |
| `uq_listener_epoch_current` | UNIQUE `(state)` WHERE `state='CURRENT'` |
| `uq_recovery_open_listener_epoch` | UNIQUE `(listener_epoch_id)` WHERE `state IN ('OPEN','ACKNOWLEDGING') AND recovery_type IN ('LISTENER_RESTART','LISTENER_ADOPTION','COLD_START')` |
| `uq_recovery_open_bridge_generation` | UNIQUE `(bridge_generation_id)` WHERE `state IN ('OPEN','ACKNOWLEDGING') AND recovery_type='BRIDGE_RECYCLE'` |
| `uq_domain_ack_positive` | UNIQUE `(recovery_transaction_id,authoritative_domain)` WHERE `acknowledgement_disposition='ACCEPTED'` |
| `uq_bridge_generation_current_epoch` | UNIQUE `(listener_epoch_id)` WHERE `state='CURRENT'` |
| `uq_subscription_verified_current` | UNIQUE `(symbol,contract_session_ref_id,bridge_generation_id)` WHERE `disposition='SUBSCRIPTION_VERIFIED'` |
| `uq_market_expectation_current` | UNIQUE `(symbol,listener_epoch_id)` WHERE `current=1` |

Every trigger name SHALL be `trg_<table>_<purpose>`. Immutable-column triggers use purpose `immutable` and execute `BEFORE UPDATE OF <the exact immutable columns listed in that table section>`; if any `OLD.column IS NOT NEW.column`, they raise `ABORT 'IMMUTABLE_COLUMN'`. The exact semantic constraint triggers are:

| Trigger name | Timing and exact rejection condition |
|---|---|
| `trg_recovery_transactions_scope` | BEFORE INSERT/UPDATE; reject unless the recovery-type/null-parent rules immediately following that table are true |
| `trg_listener_current_epoch_scope` | BEFORE INSERT/UPDATE; reject a NULL listener epoch outside the four listed listener states or a non-NULL current incident/recovery whose parent identities differ |
| `trg_domain_acknowledgements_required_match` | BEFORE INSERT; reject unless a required-domain parent exists, all generation/epoch/recovery identities match, and an ACCEPTED row has equal expected/observed identity |
| `trg_listener_restart_outcomes_semantics` | BEFORE INSERT; reject unless rate exhaustion has non-NULL rate evidence and retry prohibition, cancellation results only in HEALTHY/SUSPECT, and the incident is current/version-matched |
| `trg_bridge_outcomes_semantics` | BEFORE INSERT; reject unless exhaustion has non-NULL rate/deadline evidence and retry prohibition and the incident/generation/current-state versions match |
| `trg_health_current_dimension_state` | BEFORE INSERT/UPDATE; reject a state outside its named dimension, a dimension/scope pair outside the exact five-row set, or a positive/ordinary degraded state lacking the identities/event required after the table definition |
| `trg_health_aggregate_exact_derivation` | BEFORE INSERT/UPDATE; reject unless recomputation from the five current dimension rows exactly equals aggregate state, version input set, dimension hash, and blocker set/hash |
| `trg_termination_results_field_evidence` | BEFORE INSERT; reject any concrete/NONE/UNKNOWN field whose evidence-set hash and evidence sufficiency classification do not satisfy ADR-016's closed per-field rule |
| `trg_market_data_expectations_successor` | BEFORE INSERT/UPDATE; reject overlapping current evaluations, a successor that fails to close the prior current row in the same typed transaction, or expiry not greater than start |

No other trigger may mutate a domain row. Constraint triggers only abort. All successor/current-row changes occur through the named typed transaction, and the schema hash includes every normalized index and trigger definition above.

## 5. Table lifecycle, ownership, and reconstruction

| Tables | Owner / writer | Creation and retirement | Restart reconstruction |
|---|---|---|---|
| `store_metadata`, `writer_registry`, `transaction_commits`, `idempotency_records` | Mechanical store / Coordinator | install or typed transaction; never silently retired | verify schema, registry, contiguous transaction sequence and idempotency results |
| `supervisor_generations`, `supervisor_leases` | Listener Supervisor / Generation Writer | generation acquisition and release/fence | exactly one current generation and one held lease or fail ambiguous |
| `shared_feed_policies`, `market_data_expectations` | Policy or Expectation Evaluator / Incident Writer | validated deployment policy/evaluation; superseded by explicit new row | select exact active policy and current unexpired evaluation; never newest-file inference |
| `active_contract_sessions` | external ADR-014 authority reference / Health Durable Writer | validated source reference; close validity on exact new source reference | revalidate source hash and active ADR-014 commit; mismatch blocks |
| `listener_epochs` | Listener Supervisor / Epoch Writer | grant only after prior fence; retire explicitly | select the sole CURRENT row and verify generation/process/grant ancestry |
| `recovery_transactions` | owning Listener or Bridge State Evaluator / Recovery Transaction Writer | typed listener/bridge/store recovery transaction; terminal rows immutable | restore exact open recovery and its typed parent identity |
| listener incident/execution/rehydration tables | Listener Supervisor / Listener Incident Writer | typed incident transaction; terminal rows immutable | restore exact open incident, execution, rehydration, counts, and outcomes |
| `listener_current`, `listener_state_transitions` | State Evaluator / Listener State Writer | initialized through startup typed transaction; transitions only | singleton plus last-transition/version/hash must agree or `SUPERVISOR_STORE_FAILED` |
| `recovery_required_domains`, `domain_acknowledgements` | State Evaluator / Acknowledgement Writer | rehydration start and authenticated acknowledgement | compute outstanding set from required minus accepted; Command Center never appears |
| bridge generation/current/incident/transition/attempt/outcome tables | State Evaluator / Bridge Generation Writer or Health Durable Writer | typed bridge transactions only | verify sole current generation/current row and exact open incident/outcome |
| health event/current/transition/aggregate/subscription/termination tables | State Evaluator / Health Durable Writer | authenticated ingress and typed health transactions | reconstruct every dimension independently, then verify aggregate derivation |
| `projection_cursors` | Projection publication domain / Health Durable Writer | post-control publication only | rebuildable from committed source; never restores control |
| `store_incidents` | affected domain evaluator / Store Incident Writer | failure or recovery typed transaction | any OPEN corruption/schema/routing incident blocks affected startup |

No positive state may be reconstructed from process existence, endpoint response, projection JSON, log text, file timestamp, or the absence of an error.

## 6. Closed logical writer registry

| Writer ID | Permitted tables/operations | Required authority and idempotency | Prohibited behavior |
|---|---|---|---|
| `SUPERVISOR_GENERATION_WRITER` | INSERT/UPDATE `supervisor_generations`, `supervisor_leases` only | Supervisor lease/grant/fence decision; generation or lease identity plus expected version | all listener state, incident, epoch, bridge, health, termination, store-incident, readiness tables |
| `LISTENER_EPOCH_WRITER` | INSERT/UPDATE `listener_epochs` | Supervisor epoch grant/fence decision; grant/fence token; expected current epoch | generation, listener state/incident, bridge/health tables |
| `LISTENER_STATE_WRITER` | INSERT/UPDATE `listener_current`; INSERT `listener_state_transitions` | State Evaluator transition decision; transition ID; expected listener state version | incidents, acknowledgements, epochs, bridge/health tables |
| `LISTENER_INCIDENT_WRITER` | INSERT/UPDATE `listener_restart_incidents`, `listener_execution_attempts`, `listener_rehydrations`; INSERT-only `listener_restart_incident_transitions`, `listener_restart_outcomes`, `listener_fences`, `shared_feed_policies`, `market_data_expectations` | Supervisor/Policy/Expectation evaluator decision; incident/rehydration/policy identity; expected version | listener current/transitions, acknowledgements, recovery transactions, bridge current, health state |
| `LISTENER_ACKNOWLEDGEMENT_WRITER` | `recovery_required_domains`, `domain_acknowledgements` | State Evaluator decision after Health Ingress validation; recovery/domain/evidence identity | lifecycle completion, listener current, bridge/health state |
| `RECOVERY_TRANSACTION_WRITER` | INSERT/UPDATE `recovery_transactions` only | owning Listener or Bridge State Evaluator decision; recovery identity, exact parent incident/generation, expected version | every lifecycle/current/incident/acknowledgement/health table and every recovery decision |
| `BRIDGE_GENERATION_WRITER` | INSERT/UPDATE `bridge_generations` | Supervisor State Evaluator grant/fence; generation token; expected current generation | bridge state/incident/outcome, listener epoch/state, health state |
| `HEALTH_DURABLE_WRITER` | INSERT/UPDATE `active_contract_sessions`, `bridge_current`, `bridge_incidents`, `bridge_recycle_attempts`, `health_current`, `health_aggregate`, `projection_cursors`; INSERT-only `bridge_transitions`, `bridge_outcomes`, `producer_registrations`, `health_events`, `health_transitions`, `subscription_verifications`, `termination_evidence`, `termination_results` | State Evaluator decision and authenticated evidence; event/incident/transition identity; expected version | supervisor generations/leases, listener epochs/current/incidents/acknowledgements, recovery transactions, store incidents, Entry Session store |
| `STORE_INCIDENT_WRITER` | INSERT/UPDATE `store_incidents` only | affected-domain classifier or governed recovery authorization; incident identity and expected disposition | domain classification, recovery authorization, all lifecycle/health/identity tables |
| `RUNTIME_AUTHORITY_STORE_TRANSACTION_COORDINATOR` | INSERT/UPDATE `store_metadata`, `writer_registry`, `idempotency_records`; INSERT-only `transaction_commits`; execute registered subplans without becoming their logical writer | complete typed transaction envelope, registered writer set, decision IDs, expected versions, idempotency key | every domain decision, classification, grant, readiness decision, repair, or invented transition |
| `ENTRY_AGENT_SESSION_COMMIT_WRITER` | none in this database | ADR-014 transaction outside this store | every runtime-authority table |

Every request SHALL include writer ID, typed transaction ID, authority-decision ID, idempotency key, request hash, expected versions, evidence-set hash, and writer build hash. A writer-routing violation commits no domain row, returns `WRITER_ROUTING_REJECTED`, and records an out-of-band fail-closed incident at the next valid owning recovery boundary. Version conflict returns `VERSION_CONFLICT`; missing parent returns `MISSING_PARENT`; constraint failure returns `CONSTRAINT_REJECTED`. None is retried with changed inputs under the same key.

## 7. Typed transaction envelope

Every type below uses one `BEGIN IMMEDIATE` transaction, verifies schema/writer registry/parents/expected versions/idempotency, applies the exact listed rows, inserts one `transaction_commits` row, updates `store_metadata`, commits, performs readback on a read-only connection, and only then acknowledges success. “Atomic” always means these exact operations, not a generic related-record promise.

### 7.1 Listener typed transactions

| ID | Authority and preconditions | Atomic writes | Result |
|---|---|---|---|
| `TX-LSN-CANCEL` | State Evaluator; incident `RESTART_PENDING`; unfenced; accepted current-generation recovery event; exact incident/listener versions | incident transition to TERMINAL; `RESTART_CANCELED` outcome; listener transition to `HEALTHY` or `SUSPECT`; listener singleton/version; incident singleton/version; evidence; transaction row | terminal cancellation and explicit current listener state; no process action |
| `TX-LSN-FENCE` | State Evaluator; qualifying current SFF; incident pending; policy/debounce/rate valid; exact versions | listener fence; incident transition to `RESTART_FENCED`; listener transition to `FENCED`; both current records; evidence | durable no-cancel boundary |
| `TX-LSN-EXECUTION-START` | State Evaluator; fenced incident/listener; no execution row; count below maximum | one execution attempt; incident to `RESTART_EXECUTING`; retry/rate count; current identities/evidence | exactly one execution identity/child token |
| `TX-LSN-REHYDRATION-START` | State Evaluator; execution/adoption/cold-start evidence; prior epoch disposition proven | recovery transaction OPEN; listener rehydration OPEN; required-domain rows; incident to `RESTART_REHYDRATING` when applicable; listener to `REHYDRATING`; new/retained epoch rows as decided | closed required acknowledgement set and recovery identity |
| `TX-LSN-ACK` | State Evaluator after Health Ingress validates authenticated exact-domain evidence; required row exists; no positive ack exists | one acknowledgement; rehydration progress/version; recovery state `ACKNOWLEDGING`; no listener completion | one domain accepted or rejected; duplicate positive prohibited |
| `TX-LSN-COMPLETE` | State Evaluator; every required domain has exactly one accepted matching acknowledgement; current identities coherent | incident `RESTART_COMPLETED`; listener `HEALTHY`; listener/incident transitions; recovery and rehydration COMPLETE; outcome; current rows | completed recovery under one identity |
| `TX-LSN-FAIL` | State Evaluator; execution or rehydration failed before rate exhaustion | incident `RESTART_FAILED`; listener `LISTENER_FAILED`; transition histories; recovery/rehydration FAILED; outcome/escalation | fail closed; no automatic retry unless a new governed incident is permitted |
| `TX-LSN-RATE-EXHAUSTED` | State Evaluator; pending incident; cooldown active or durable count equals maximum before fence | incident terminal; `RECOVERY_RATE_LIMITED_FAILED`; fail-closed listener `SUSPECT` or `LISTENER_FAILED` as policy dictates; rate evidence/escalation; transitions | no fence, execution, epoch, or automatic retry |
| `TX-LSN-PLANNED-STOP` | State Evaluator; governed operator/supervisor stop authorization; exact current listener/epoch versions | listener transition/current state to `STOPPING`; transition history; epoch fence as authorized | planned stop initiated, never SFF evidence |
| `TX-LSN-STOP-COMPLETE` | State Evaluator; listener `STOPPING`; exact process-exit acknowledgement proves the governed stop command completed | listener transition/current state to `STOPPED`; transition history; epoch state to `RETIRED`; completion evidence | planned lifecycle complete, no SFF/restart incident |

`TX-LSN-CANCEL` writer set is exactly `LISTENER_INCIDENT_WRITER + LISTENER_STATE_WRITER`. `TX-LSN-FENCE` and `TX-LSN-RATE-EXHAUSTED` use that same closed two-writer set. `TX-LSN-REHYDRATION-START` uses `LISTENER_INCIDENT_WRITER + LISTENER_STATE_WRITER + LISTENER_EPOCH_WRITER + LISTENER_ACKNOWLEDGEMENT_WRITER + RECOVERY_TRANSACTION_WRITER`. `TX-LSN-ACK` uses `LISTENER_ACKNOWLEDGEMENT_WRITER + LISTENER_INCIDENT_WRITER + RECOVERY_TRANSACTION_WRITER`. `TX-LSN-COMPLETE` and `TX-LSN-FAIL` use `LISTENER_INCIDENT_WRITER + LISTENER_STATE_WRITER + RECOVERY_TRANSACTION_WRITER`; completion also uses `LISTENER_ACKNOWLEDGEMENT_WRITER` to close the acknowledgement set. `TX-LSN-PLANNED-STOP` and `TX-LSN-STOP-COMPLETE` use `LISTENER_STATE_WRITER + LISTENER_EPOCH_WRITER`. No other cross-writer listener transaction is legal.

### 7.2 Supervisor-store recovery transactions

| ID | Preconditions | Writes/result |
|---|---|---|
| `TX-STORE-VALIDATE` | read-only validation succeeds | validation evidence only; no domain state change |
| `TX-STORE-INCIDENT` | a committed store can still record a bounded write/readback/routing/version incident | append `store_incidents`; affected state remains unchanged/fail-closed |
| `TX-STORE-STALE-LEASE-FENCE` | State Evaluator proves persisted lease expired using trustworthy current time plus OS/process identity and acquires the governed replacement-generation authorization | prior lease `FENCED`; prior generation `FENCED`; new generation/lease allocated in one transaction; incident evidence retained |
| `TX-STORE-VERSION-CONFLICT-REJECT` | typed plan's expected version differs from the committed current version | no domain row changes; idempotency result `REJECTED_VERSION`; version-conflict incident queued for `TX-STORE-INCIDENT` without retrying changed inputs under the same key |
| `TX-STORE-QUARANTINE` | integrity/schema failure; operator recovery authorization | no mutation to corrupt DB; external immutable quarantine manifest |
| `TX-STORE-RESTORE` | approved qualifying local/offline backup, exact hashes, three required approvals, process ambiguity resolved | validate candidate copy; atomically activate before first new commit; insert recovery incident and new supervisor generation; preserve ancestry |
| `TX-STORE-REINITIALIZE` | no trustworthy source and separately approved reinitialization plan | new store UUID; fence all prior identities in audit evidence; create initial failed/blocked states; no positive freshness/readiness |
| `TX-STORE-MIGRATE-V2` | exact approved v1 predecessor and migration hash | staged candidate migration, full validation, atomic activation; no rollback after first v2 production commit |

`TX-STORE-INCIDENT` uses only `STORE_INCIDENT_WRITER`. `TX-STORE-VALIDATE` performs read-only validation and the Coordinator may update only `store_metadata.last_verified_at_utc` and its integrity disposition under the supplied Store Integrity Classifier decision. `TX-STORE-STALE-LEASE-FENCE` uses only `SUPERVISOR_GENERATION_WRITER`; it cannot execute without the named State Evaluator authorization. `TX-STORE-VERSION-CONFLICT-REJECT` writes only the Coordinator-owned idempotency rejection row; any durable incident uses a later `TX-STORE-INCIDENT`. `TX-STORE-QUARANTINE` writes no row to the corrupt database and writes only the separately governed immutable quarantine manifest. `TX-STORE-RESTORE` uses `STORE_INCIDENT_WRITER + SUPERVISOR_GENERATION_WRITER` after the candidate database has passed all read-only checks. `TX-STORE-REINITIALIZE` uses exactly `SUPERVISOR_GENERATION_WRITER + LISTENER_STATE_WRITER + HEALTH_DURABLE_WRITER + STORE_INCIDENT_WRITER`: it creates a new supervisor generation, `listener_current=SUPERVISOR_STORE_FAILED`, five nonpositive health dimension rows with persistence `HEALTH_STORE_CORRUPT` and the rest `HEALTH_STARTUP_UNPROVEN`, `health_aggregate=HEALTH_CORRUPT`, and one OPEN `RECOVERY_REQUIRED` incident. It creates no listener epoch, bridge generation, subscription, expectation, termination, acknowledgement, ready/coherent state, or freshness fact. `TX-STORE-MIGRATE-V2` uses the Coordinator's `MIGRATION_ONLY` registry rows and no domain writer; it preserves domain records byte-for-byte except the approved deterministic schema transform. No recovery transaction grants the Coordinator classification or restoration authority.

An incomplete transaction has no `transaction_commits` row and no visible SQLite commit after WAL recovery; it is uncommitted. A visible commit with matching transaction row/readback hash is committed even if no response was sent. Any other combination is corruption and enters governed recovery.

### 7.3 Bridge typed transactions

| ID | Authority and preconditions | Atomic writes | Result |
|---|---|---|---|
| `TX-BRG-GRANT` | State Evaluator; current supervisor/listener epoch; prior bridge fenced/absent | bridge generation; bridge current `BRIDGE_STARTING`; transition | one Supervisor-granted generation; Controller only acknowledges |
| `TX-BRG-RECYCLE-PENDING` | State Evaluator; unexpected current-generation BDP; exclusions clear; below limit | bridge incident pending; bridge current `RECYCLE_PENDING`; transition/evidence | cancellable incident |
| `TX-BRG-CANCEL` | State Evaluator; pending/unfenced; fresh recovery evidence | terminal `RECYCLE_CANCELED`; bridge `BRIDGE_READY` or `BRIDGE_SUSPECT`; transition/outcome | no process action |
| `TX-BRG-FENCE` | State Evaluator; pending predicate revalidated | incident `BRIDGE_FENCED`; bridge generation/state fenced; transition; token | no-cancel boundary |
| `TX-BRG-EXECUTE` | fenced incident; permitted attempt remains | recycle attempt; incident/state `RECYCLE_EXECUTING`; count/evidence | one bounded Controller command |
| `TX-BRG-REHYDRATE` | authenticated replacement/reconnect result | new bridge generation grant; incident/state `BRIDGE_REHYDRATING`; recovery transaction | no listener epoch change |
| `TX-BRG-READY` | current generation login/subscriptions and required health proof committed | bridge `BRIDGE_READY`; outcome; transitions; recovery complete | successful bridge-only recovery |
| `TX-BRG-FAIL` | permitted attempt fails before exhaustion | `BRIDGE_FAILED`; outcome/evidence; no exhaustion alias | ordinary nonexhausted failure |
| `TX-BRG-EXHAUSTED` | pre-action count equals maximum or final permitted attempt misses deadline | `FAILED_RECOVERY_EXHAUSTED`; terminal outcome; rate/deadline/escalation evidence | no retry; eligible only as separately authenticated SFF-03 input |
| `TX-BRG-PLANNED-SHUTDOWN` | governed shutdown intent matches generation | `PLANNED_SHUTDOWN`; outcome/transition | excluded from BDP/SFF |
| `TX-BRG-EPOCH-TRANSITION` | listener epoch fence/new epoch transaction | `LISTENER_EPOCH_TRANSITION`; old bridge generation fenced/retired; transition/outcome | no bridge fact grants the new listener epoch |

Bridge generation changes use `BRIDGE_GENERATION_WRITER`; bridge state/incident/outcome/attempt writes use `HEALTH_DURABLE_WRITER`. `TX-BRG-GRANT` and `TX-BRG-EPOCH-TRANSITION` use exactly those two writers. `TX-BRG-REHYDRATE` uses those two plus `RECOVERY_TRANSACTION_WRITER`. `TX-BRG-READY` uses `HEALTH_DURABLE_WRITER + RECOVERY_TRANSACTION_WRITER`. Every other bridge transaction uses only `HEALTH_DURABLE_WRITER`. No other cross-writer bridge transaction is legal.

### 7.4 Health and evidence typed transactions

| ID | Authority and preconditions | Atomic writes | Result |
|---|---|---|---|
| `TX-HEALTH-EVENT` | Health Ingress authenticates producer, sequence, identities, integrity and freshness | event; durable cursor; transaction | accepted immutable evidence; rejected evidence creates no positive fact |
| `TX-HEALTH-DIMENSION-UPDATE` | State Evaluator consumes committed event and exact prior dimension version | health transition; one `health_current` row; recomputed `health_aggregate`; event/cursor references | one dimension changes without overwriting another |
| `TX-SUBSCRIPTION-VERIFY` | authenticated listener proof; exact current contract/epoch/generation | subscription result plus relevant health event/transition/aggregate | `SUBSCRIPTION_VERIFIED` only after evaluator decision and commit |
| `TX-TERMINATION-EVIDENCE` | authenticated RAPI/OS/listener/supervisor/operator source | termination evidence row | evidence only; no classification or lifecycle action |
| `TX-TERMINATION-CLASSIFY` | State Evaluator has complete current-generation evidence set or proves deficiency | five independent result fields and evidence-set hashes | concrete/NONE/UNKNOWN per field; nonzero exit alone never crash |
| `TX-EXPECTATION-EVALUATE` | Expectation Evaluator has active policy, contract/session, calendar, intent and trustworthy clock | expectation row and transaction evidence | exact startup/data-expected/not-expected/expired result |
| `TX-POLICY-VALIDATE` | Policy Evaluator has deployment-bound canonical policy bytes and authorization | policy validation result/activation | valid policy or `SHARED_FEED_POLICY_INVALID`; no process action |
| `TX-PROJECTION-CURSOR` | control transaction already committed | projection cursor only | observational publication progress; no feedback into control |

`TX-HEALTH-EVENT`, `TX-HEALTH-DIMENSION-UPDATE`, `TX-SUBSCRIPTION-VERIFY`, `TX-TERMINATION-EVIDENCE`, `TX-TERMINATION-CLASSIFY`, and `TX-PROJECTION-CURSOR` use only `HEALTH_DURABLE_WRITER`. `TX-EXPECTATION-EVALUATE` and `TX-POLICY-VALIDATE` use only `LISTENER_INCIDENT_WRITER`. No health/evidence transaction may write `recovery_transactions` or `store_incidents`; those require their separately named writers and transaction types.

## 8. Common crash, replay, rollback, and rejection rules

These rules apply to every typed transaction:

| Condition | Deterministic result |
|---|---|
| Crash before SQLite COMMIT | no domain authority change; WAL recovery rolls back; same request/key may replay |
| Crash after COMMIT before readback/response | startup/readback locates `transaction_commits`; same key returns committed result; no duplicate transition |
| Same idempotency key and request hash | return recorded committed or rejected result without executing again |
| Same key, different request hash | `IDEMPOTENCY_CONFLICT`; zero domain writes |
| Constraint or FK failure | rollback entire transaction; `CONSTRAINT_REJECTED`; current authority unchanged/fail-closed |
| Expected-version mismatch | rollback; `VERSION_CONFLICT`; caller must reread and obtain a new authority decision/key |
| Writer-routing failure | rollback; `WRITER_ROUTING_REJECTED`; no coordinator reinterpretation |
| Missing parent | rollback; `MISSING_PARENT`; no placeholder parent or copied authority |
| Corrupt parent/current row | no transaction; `STORE_CORRUPT`; governed quarantine/recovery |
| Readback/hash mismatch | no acknowledgement; `READBACK_FAILED`; preserve pending request; recovery determines whether COMMIT exists |
| Response delivery failure | committed result remains authoritative; retry returns same result |

No failed transaction may partially advance a cursor, clear pending evidence, allocate an epoch/generation, or expose a positive readiness state.

## 9. Closed transition and positive-state rules

Every lifecycle transition not explicitly permitted by ADR-015, ADR-016, and the corresponding typed transaction above is prohibited. A row cannot be inserted merely because its enum value is valid. The typed transaction, authority decision, expected version, evidence set, parent identities, and permitted prior/result pair SHALL all validate.

Command Center is absent from `recovery_required_domains` and `domain_acknowledgements`. `COMMAND_CENTER_ALIGNED` is an external observational startup parity result and SHALL NOT be stored as listener, bridge, health, recovery, or session authority.

## 10. Deterministic startup reconstruction

After WAL recovery and section 2.1 validation, the owning components SHALL reconstruct in this exact order:

1. highest contiguous `transaction_commits.transaction_sequence` and matching metadata cursor;
2. active writer registry and zero unauthorized table/writer combinations;
3. sole CURRENT supervisor generation and sole HELD lease;
4. sole `listener_current` row and matching last listener transition/version;
5. sole CURRENT listener epoch where the listener state requires one;
6. exact current listener incident, outcome, fence, execution, rehydration, and recovery relationship;
7. outstanding authoritative acknowledgement set computed from required domains minus accepted acknowledgements;
8. sole current Bridge Generation, `bridge_current`, transition, incident, attempt, and outcome relationship;
9. all five independent `health_current` dimensions and matching transitions;
10. recomputed aggregate health equality with `health_aggregate`;
11. current subscription, termination, policy, expectation, and validated contract/session references; and
12. every open store incident and projection cursor, with projection excluded from authority.

Zero or multiple singleton/current rows, a state/version/transition mismatch, an incident referenced by two current authorities, a missing accepted acknowledgement claimed as complete, stale-generation positive evidence, an incomplete parent chain, or a transaction cursor gap SHALL return `CONTROL_STORE_AUTHORITY_AMBIGUOUS`, set `SUPERVISOR_STORE_FAILED`/affected health degradation when safely writable, and terminate startup `FAILED`. Process existence SHALL NOT resolve ambiguity.

## 11. Verification obligations

Document-only validation SHALL prove every table, column, primary key, unique constraint, foreign key target, enum, writer allowlist, and typed transaction reference is closed. Future authorized implementation verification SHALL cover every permitted transaction, every prohibited writer/table pair, pre/post-commit crash, response loss, replay, version conflict, FK failure, missing parent, corruption, migration, reconstruction, duplicate-current-row, stale-generation, acknowledgement, rate/exhaustion, and projection-isolation case.

## 12. Governance boundary and provenance

This draft defines proposed architecture only. It does not approve ADR-015 or ADR-016, modify ADR-014, incorporate canonical amendments, authorize implementation, perform runtime verification, authorize deployment, produce `READY_LOCKED`, complete Bucket 0, authorize Bucket 1, or authorize trading.

ADR-014’s metadata-applied committed SHA-256 remains `528B3C7099D63DB41C6B85E381EAD37AD1E479867C07934FD077EBBD8B5EC321`. Governance records also cite the earlier approved-content hash `BD76D1B398515EA00E230B9C8A00A540344E061A36B228BF112F784F6AC34F25`; the corresponding pre-metadata Git blob is not independently reconstructable from current repository history. That provenance limitation does not authorize any ADR-014 modification.
