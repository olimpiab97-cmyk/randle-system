-- Runtime Authority Store schema v2 -- Phase 3C1 draft implementation reference.
-- DRAFT / NONCANONICAL / NOT APPROVED / NOT AUTHORIZED FOR RUNTIME INSTALLATION.
-- Minimum SQLite: 3.43.1.  This artifact uses only built-in SQLite expressions.

PRAGMA foreign_keys = ON;
PRAGMA trusted_schema = OFF;
PRAGMA recursive_triggers = ON;
PRAGMA busy_timeout = 5000;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA application_id = 0x52484C54;
PRAGMA user_version = 2;

BEGIN IMMEDIATE;

-- SCHEMA-HASH-BEGIN
CREATE TABLE store_metadata (
    singleton_id INTEGER NOT NULL PRIMARY KEY CHECK (singleton_id = 1),
    store_uuid TEXT NOT NULL CHECK (length(store_uuid)=36 AND store_uuid=lower(store_uuid) AND substr(store_uuid,9,1)='-' AND substr(store_uuid,14,1)='-' AND substr(store_uuid,19,1)='-' AND substr(store_uuid,24,1)='-' AND replace(store_uuid,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(store_uuid,15,1) IN ('1','2','3','4','5') AND substr(store_uuid,20,1) IN ('8','9','a','b')),
    schema_identity TEXT NOT NULL CHECK (schema_identity='RANDLE_RUNTIME_AUTHORITY_SCHEMA_V2'),
    schema_hash TEXT NOT NULL CHECK (length(schema_hash)=64 AND schema_hash=lower(schema_hash) AND schema_hash NOT GLOB '*[^0-9a-f]*'),
    bootstrap_identity TEXT NOT NULL CHECK (bootstrap_identity='RASTORE-BOOTSTRAP-V2'),
    writer_registry_version INTEGER NOT NULL CHECK (writer_registry_version=2),
    writer_registry_hash TEXT NOT NULL CHECK (length(writer_registry_hash)=64 AND writer_registry_hash=lower(writer_registry_hash) AND writer_registry_hash NOT GLOB '*[^0-9a-f]*'),
    last_transaction_sequence INTEGER NOT NULL CHECK (last_transaction_sequence>=0),
    last_transaction_id TEXT NULL CHECK (last_transaction_id IS NULL OR (length(last_transaction_id)=36 AND last_transaction_id=lower(last_transaction_id) AND substr(last_transaction_id,9,1)='-' AND substr(last_transaction_id,14,1)='-' AND substr(last_transaction_id,19,1)='-' AND substr(last_transaction_id,24,1)='-' AND replace(last_transaction_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(last_transaction_id,15,1) IN ('1','2','3','4','5') AND substr(last_transaction_id,20,1) IN ('8','9','a','b'))),
    integrity_state TEXT NOT NULL CHECK (integrity_state IN ('VERIFIED','RECOVERY_REQUIRED','CORRUPT')),
    created_at_utc TEXT NOT NULL CHECK (length(created_at_utc)=27 AND substr(created_at_utc,5,1)='-' AND substr(created_at_utc,8,1)='-' AND substr(created_at_utc,11,1)='T' AND substr(created_at_utc,14,1)=':' AND substr(created_at_utc,17,1)=':' AND substr(created_at_utc,20,1)='.' AND substr(created_at_utc,27,1)='Z' AND julianday(created_at_utc) IS NOT NULL),
    last_verified_at_utc TEXT NULL CHECK (last_verified_at_utc IS NULL OR (length(last_verified_at_utc)=27 AND substr(last_verified_at_utc,5,1)='-' AND substr(last_verified_at_utc,8,1)='-' AND substr(last_verified_at_utc,11,1)='T' AND substr(last_verified_at_utc,14,1)=':' AND substr(last_verified_at_utc,17,1)=':' AND substr(last_verified_at_utc,20,1)='.' AND substr(last_verified_at_utc,27,1)='Z' AND julianday(last_verified_at_utc) IS NOT NULL)),
    FOREIGN KEY (last_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE writer_registry (
    registry_version INTEGER NOT NULL CHECK (registry_version=2),
    table_name TEXT NOT NULL CHECK (table_name IN ('store_metadata','writer_registry','transaction_commits','idempotency_records','supervisor_generations','supervisor_leases','shared_feed_policies','active_contract_sessions','listener_epochs','recovery_transactions','listener_current','listener_state_transitions','listener_restart_incidents','listener_restart_incident_transitions','listener_restart_outcomes','listener_fences','listener_execution_attempts','listener_rehydrations','recovery_required_domains','domain_acknowledgements','bridge_generations','bridge_current','bridge_transitions','bridge_incidents','bridge_recycle_attempts','bridge_outcomes','producer_registrations','health_events','health_current','health_transitions','health_aggregate','subscription_verifications','termination_evidence','termination_results','market_data_expectations','projection_cursors','store_incidents')),
    operation TEXT NOT NULL CHECK (operation IN ('INSERT','UPDATE','DELETE')),
    writer_id TEXT NOT NULL CHECK (writer_id IN ('RUNTIME_AUTHORITY_STORE_TRANSACTION_COORDINATOR','SUPERVISOR_GENERATION_WRITER','LISTENER_EPOCH_WRITER','LISTENER_STATE_WRITER','LISTENER_INCIDENT_WRITER','LISTENER_ACKNOWLEDGEMENT_WRITER','RECOVERY_TRANSACTION_WRITER','BRIDGE_GENERATION_WRITER','HEALTH_DURABLE_WRITER','PROJECTION_WRITER','STORE_INCIDENT_WRITER')),
    writer_contract_identity TEXT NOT NULL,
    writer_build_hash TEXT NULL CHECK (writer_build_hash IS NULL OR (length(writer_build_hash)=64 AND writer_build_hash=lower(writer_build_hash) AND writer_build_hash NOT GLOB '*[^0-9a-f]*')),
    effective_transaction_sequence INTEGER NOT NULL CHECK (effective_transaction_sequence>=0),
    retired_transaction_sequence INTEGER NULL CHECK (retired_transaction_sequence IS NULL OR retired_transaction_sequence>=effective_transaction_sequence),
    active INTEGER NOT NULL CHECK (active IN (0,1)),
    PRIMARY KEY (registry_version,table_name,operation,effective_transaction_sequence),
    UNIQUE (registry_version,table_name,operation,writer_id,effective_transaction_sequence),
    CHECK ((active=1 AND retired_transaction_sequence IS NULL) OR (active=0 AND retired_transaction_sequence IS NOT NULL))
) STRICT;

CREATE TABLE transaction_commits (
    transaction_id TEXT NOT NULL PRIMARY KEY CHECK (length(transaction_id)=36 AND transaction_id=lower(transaction_id) AND substr(transaction_id,9,1)='-' AND substr(transaction_id,14,1)='-' AND substr(transaction_id,19,1)='-' AND substr(transaction_id,24,1)='-' AND replace(transaction_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(transaction_id,15,1) IN ('1','2','3','4','5') AND substr(transaction_id,20,1) IN ('8','9','a','b')),
    transaction_sequence INTEGER NOT NULL UNIQUE CHECK (transaction_sequence>=1),
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('TX-LSN-CANCEL','TX-LSN-FENCE','TX-LSN-EXECUTION-START','TX-LSN-REHYDRATION-START','TX-LSN-ACK','TX-LSN-COMPLETE','TX-LSN-FAIL','TX-LSN-RATE-EXHAUSTED','TX-LSN-PLANNED-STOP','TX-LSN-STOP-COMPLETE','TX-STORE-RESTORE','TX-STORE-REINITIALIZE','TX-STORE-STALE-LEASE-FENCE','TX-STORE-INCIDENT','TX-STORE-BOOTSTRAP-V2','TX-BRG-RECYCLE-PENDING','TX-BRG-CANCEL','TX-BRG-FENCE','TX-BRG-EXECUTE','TX-BRG-REHYDRATE','TX-BRG-READY','TX-BRG-FAIL','TX-BRG-EXHAUSTED','TX-BRG-GRANT','TX-BRG-PLANNED-SHUTDOWN','TX-BRG-EPOCH-TRANSITION','TX-HEALTH-EVENT','TX-HEALTH-DIMENSION-UPDATE','TX-SUBSCRIPTION-VERIFY','TX-TERMINATION-EVIDENCE','TX-TERMINATION-CLASSIFY','TX-EXPECTATION-EVALUATE','TX-POLICY-VALIDATE','TX-PROJECTION-CURSOR')),
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL CHECK (length(request_hash)=64 AND request_hash=lower(request_hash) AND request_hash NOT GLOB '*[^0-9a-f]*'),
    authority_decision_id TEXT NOT NULL CHECK (length(authority_decision_id)=36 AND authority_decision_id=lower(authority_decision_id) AND substr(authority_decision_id,9,1)='-' AND substr(authority_decision_id,14,1)='-' AND substr(authority_decision_id,19,1)='-' AND substr(authority_decision_id,24,1)='-' AND replace(authority_decision_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(authority_decision_id,15,1) IN ('1','2','3','4','5') AND substr(authority_decision_id,20,1) IN ('8','9','a','b')),
    writer_set_json TEXT NOT NULL CHECK (json_valid(writer_set_json)=1 AND json_type(writer_set_json)='array'),
    writer_set_hash TEXT NOT NULL CHECK (length(writer_set_hash)=64 AND writer_set_hash=lower(writer_set_hash) AND writer_set_hash NOT GLOB '*[^0-9a-f]*'),
    expected_versions_json TEXT NOT NULL CHECK (json_valid(expected_versions_json)=1 AND json_type(expected_versions_json)='object'),
    expected_versions_hash TEXT NOT NULL CHECK (length(expected_versions_hash)=64 AND expected_versions_hash=lower(expected_versions_hash) AND expected_versions_hash NOT GLOB '*[^0-9a-f]*'),
    result_versions_json TEXT NOT NULL CHECK (json_valid(result_versions_json)=1 AND json_type(result_versions_json)='object'),
    result_versions_hash TEXT NOT NULL CHECK (length(result_versions_hash)=64 AND result_versions_hash=lower(result_versions_hash) AND result_versions_hash NOT GLOB '*[^0-9a-f]*'),
    evidence_set_hash TEXT NOT NULL CHECK (length(evidence_set_hash)=64 AND evidence_set_hash=lower(evidence_set_hash) AND evidence_set_hash NOT GLOB '*[^0-9a-f]*'),
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,27,1)='Z' AND julianday(committed_at_utc) IS NOT NULL),
    coordinator_build_hash TEXT NOT NULL CHECK (length(coordinator_build_hash)=64 AND coordinator_build_hash=lower(coordinator_build_hash) AND coordinator_build_hash NOT GLOB '*[^0-9a-f]*'),
    commit_readback_hash TEXT NOT NULL CHECK (length(commit_readback_hash)=64 AND commit_readback_hash=lower(commit_readback_hash) AND commit_readback_hash NOT GLOB '*[^0-9a-f]*'),
    UNIQUE (transaction_type,idempotency_key)
) STRICT;

CREATE TABLE idempotency_records (
    transaction_type TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL CHECK (length(request_hash)=64 AND request_hash=lower(request_hash) AND request_hash NOT GLOB '*[^0-9a-f]*'),
    status TEXT NOT NULL CHECK (status IN ('COMMITTED','REJECTED_VERSION','REJECTED_CONSTRAINT','REJECTED_ROUTING','REJECTED_MISSING_PARENT')),
    transaction_id TEXT NULL CHECK (transaction_id IS NULL OR (length(transaction_id)=36 AND transaction_id=lower(transaction_id) AND substr(transaction_id,9,1)='-' AND substr(transaction_id,14,1)='-' AND substr(transaction_id,19,1)='-' AND substr(transaction_id,24,1)='-' AND replace(transaction_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(transaction_id,15,1) IN ('1','2','3','4','5') AND substr(transaction_id,20,1) IN ('8','9','a','b'))),
    result_hash TEXT NOT NULL CHECK (length(result_hash)=64 AND result_hash=lower(result_hash) AND result_hash NOT GLOB '*[^0-9a-f]*'),
    created_at_utc TEXT NOT NULL CHECK (length(created_at_utc)=27 AND substr(created_at_utc,27,1)='Z' AND julianday(created_at_utc) IS NOT NULL),
    PRIMARY KEY (transaction_type,idempotency_key),
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CHECK ((status='COMMITTED' AND transaction_id IS NOT NULL) OR (status<>'COMMITTED' AND transaction_id IS NULL))
) STRICT;

CREATE TABLE supervisor_generations (
    supervisor_generation_id TEXT NOT NULL PRIMARY KEY CHECK (length(supervisor_generation_id)=36 AND supervisor_generation_id=lower(supervisor_generation_id) AND substr(supervisor_generation_id,9,1)='-' AND substr(supervisor_generation_id,14,1)='-' AND substr(supervisor_generation_id,19,1)='-' AND substr(supervisor_generation_id,24,1)='-' AND replace(supervisor_generation_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(supervisor_generation_id,15,1) IN ('1','2','3','4','5') AND substr(supervisor_generation_id,20,1) IN ('8','9','a','b')),
    generation_sequence INTEGER NOT NULL UNIQUE CHECK (generation_sequence>=1),
    supervisor_instance_id TEXT NOT NULL CHECK (length(supervisor_instance_id)=36 AND supervisor_instance_id=lower(supervisor_instance_id) AND substr(supervisor_instance_id,9,1)='-' AND substr(supervisor_instance_id,14,1)='-' AND substr(supervisor_instance_id,19,1)='-' AND substr(supervisor_instance_id,24,1)='-' AND replace(supervisor_instance_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(supervisor_instance_id,15,1) IN ('1','2','3','4','5') AND substr(supervisor_instance_id,20,1) IN ('8','9','a','b')),
    process_id INTEGER NOT NULL CHECK (process_id>0),
    process_start_utc TEXT NOT NULL CHECK (length(process_start_utc)=27 AND substr(process_start_utc,27,1)='Z' AND julianday(process_start_utc) IS NOT NULL),
    build_hash TEXT NOT NULL CHECK (length(build_hash)=64 AND build_hash=lower(build_hash) AND build_hash NOT GLOB '*[^0-9a-f]*'),
    startup_attempt_id TEXT NOT NULL CHECK (length(startup_attempt_id)=36 AND startup_attempt_id=lower(startup_attempt_id) AND substr(startup_attempt_id,9,1)='-' AND substr(startup_attempt_id,14,1)='-' AND substr(startup_attempt_id,19,1)='-' AND substr(startup_attempt_id,24,1)='-' AND replace(startup_attempt_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(startup_attempt_id,15,1) IN ('1','2','3','4','5') AND substr(startup_attempt_id,20,1) IN ('8','9','a','b')),
    grant_transaction_id TEXT NOT NULL,
    started_at_utc TEXT NOT NULL CHECK (length(started_at_utc)=27 AND substr(started_at_utc,27,1)='Z' AND julianday(started_at_utc) IS NOT NULL),
    fenced_at_utc TEXT NULL CHECK (fenced_at_utc IS NULL OR (length(fenced_at_utc)=27 AND substr(fenced_at_utc,27,1)='Z' AND julianday(fenced_at_utc) IS NOT NULL)),
    fence_reason TEXT NULL,
    state TEXT NOT NULL CHECK (state IN ('CURRENT','FENCED','RETIRED')),
    writer_id TEXT NOT NULL CHECK (writer_id='SUPERVISOR_GENERATION_WRITER'),
    FOREIGN KEY (grant_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE supervisor_leases (
    lease_id TEXT NOT NULL PRIMARY KEY CHECK (length(lease_id)=36 AND lease_id=lower(lease_id) AND substr(lease_id,9,1)='-' AND substr(lease_id,14,1)='-' AND substr(lease_id,19,1)='-' AND substr(lease_id,24,1)='-' AND replace(lease_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(lease_id,15,1) IN ('1','2','3','4','5') AND substr(lease_id,20,1) IN ('8','9','a','b')),
    supervisor_generation_id TEXT NOT NULL,
    lease_version INTEGER NOT NULL CHECK (lease_version>=1),
    lease_token_hash TEXT NOT NULL UNIQUE CHECK (length(lease_token_hash)=64 AND lease_token_hash=lower(lease_token_hash) AND lease_token_hash NOT GLOB '*[^0-9a-f]*'),
    acquired_monotonic_ns INTEGER NOT NULL CHECK (acquired_monotonic_ns>=0),
    expires_monotonic_ns INTEGER NOT NULL CHECK (expires_monotonic_ns>acquired_monotonic_ns),
    lease_state TEXT NOT NULL CHECK (lease_state IN ('HELD','RELEASED','EXPIRED','FENCED')),
    last_renew_transaction_id TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL CHECK (length(updated_at_utc)=27 AND substr(updated_at_utc,27,1)='Z' AND julianday(updated_at_utc) IS NOT NULL),
    writer_id TEXT NOT NULL CHECK (writer_id='SUPERVISOR_GENERATION_WRITER'),
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (last_renew_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE shared_feed_policies (
    policy_identity TEXT NOT NULL PRIMARY KEY CHECK (length(policy_identity)=36 AND policy_identity=lower(policy_identity) AND substr(policy_identity,9,1)='-' AND substr(policy_identity,14,1)='-' AND substr(policy_identity,19,1)='-' AND substr(policy_identity,24,1)='-' AND replace(policy_identity,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(policy_identity,15,1) IN ('1','2','3','4','5') AND substr(policy_identity,20,1) IN ('8','9','a','b')),
    policy_version INTEGER NOT NULL CHECK (policy_version>=1),
    policy_sha256 TEXT NOT NULL UNIQUE CHECK (length(policy_sha256)=64 AND policy_sha256=lower(policy_sha256) AND policy_sha256 NOT GLOB '*[^0-9a-f]*'),
    schema_version INTEGER NOT NULL CHECK (schema_version>=1),
    topology TEXT NOT NULL CHECK (topology='ONE_PHYSICAL_FEED_NQ_YM'),
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)=1 AND json_type(canonical_json)='object'),
    validation_disposition TEXT NOT NULL CHECK (validation_disposition IN ('POLICY_VALID','SHARED_FEED_POLICY_INVALID')),
    validation_reason TEXT NOT NULL,
    deployment_authorization_id TEXT NOT NULL,
    approved_at_utc TEXT NOT NULL CHECK (length(approved_at_utc)=27 AND substr(approved_at_utc,27,1)='Z' AND julianday(approved_at_utc) IS NOT NULL),
    validation_transaction_id TEXT NOT NULL,
    active INTEGER NOT NULL CHECK (active IN (0,1)),
    writer_id TEXT NOT NULL CHECK (writer_id='LISTENER_INCIDENT_WRITER'),
    FOREIGN KEY (validation_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CHECK (active=0 OR validation_disposition='POLICY_VALID')
) STRICT;

CREATE TABLE active_contract_sessions (
    contract_session_ref_id TEXT NOT NULL PRIMARY KEY CHECK (length(contract_session_ref_id)=36 AND contract_session_ref_id=lower(contract_session_ref_id) AND substr(contract_session_ref_id,9,1)='-' AND substr(contract_session_ref_id,14,1)='-' AND substr(contract_session_ref_id,19,1)='-' AND substr(contract_session_ref_id,24,1)='-' AND replace(contract_session_ref_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(contract_session_ref_id,15,1) IN ('1','2','3','4','5') AND substr(contract_session_ref_id,20,1) IN ('8','9','a','b')),
    symbol TEXT NOT NULL CHECK (symbol IN ('NQ','YM')),
    contract_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    session_date TEXT NOT NULL CHECK (length(session_date)=10 AND substr(session_date,5,1)='-' AND substr(session_date,8,1)='-' AND date(session_date)=session_date),
    session_rollover_commit_id TEXT NOT NULL CHECK (length(session_rollover_commit_id)=36 AND session_rollover_commit_id=lower(session_rollover_commit_id) AND substr(session_rollover_commit_id,9,1)='-' AND substr(session_rollover_commit_id,14,1)='-' AND substr(session_rollover_commit_id,19,1)='-' AND substr(session_rollover_commit_id,24,1)='-' AND replace(session_rollover_commit_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(session_rollover_commit_id,15,1) IN ('1','2','3','4','5') AND substr(session_rollover_commit_id,20,1) IN ('8','9','a','b')),
    source_authority TEXT NOT NULL CHECK (source_authority='ADR014_ENTRY_SESSION_STORE'),
    source_record_hash TEXT NOT NULL CHECK (length(source_record_hash)=64 AND source_record_hash=lower(source_record_hash) AND source_record_hash NOT GLOB '*[^0-9a-f]*'),
    validated_transaction_id TEXT NOT NULL,
    valid_from_sequence INTEGER NOT NULL CHECK (valid_from_sequence>=0),
    valid_to_sequence INTEGER NULL CHECK (valid_to_sequence IS NULL OR valid_to_sequence>valid_from_sequence),
    writer_id TEXT NOT NULL CHECK (writer_id='HEALTH_DURABLE_WRITER'),
    UNIQUE (symbol,contract_id,session_id,session_rollover_commit_id),
    FOREIGN KEY (validated_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE listener_epochs (
    listener_epoch_id TEXT NOT NULL PRIMARY KEY CHECK (length(listener_epoch_id)=36 AND listener_epoch_id=lower(listener_epoch_id) AND substr(listener_epoch_id,9,1)='-' AND substr(listener_epoch_id,14,1)='-' AND substr(listener_epoch_id,19,1)='-' AND substr(listener_epoch_id,24,1)='-' AND replace(listener_epoch_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(listener_epoch_id,15,1) IN ('1','2','3','4','5') AND substr(listener_epoch_id,20,1) IN ('8','9','a','b')),
    epoch_sequence INTEGER NOT NULL UNIQUE CHECK (epoch_sequence>=1),
    supervisor_generation_id TEXT NOT NULL,
    listener_process_instance_id TEXT NOT NULL CHECK (length(listener_process_instance_id)=36 AND listener_process_instance_id=lower(listener_process_instance_id) AND substr(listener_process_instance_id,9,1)='-' AND substr(listener_process_instance_id,14,1)='-' AND substr(listener_process_instance_id,19,1)='-' AND substr(listener_process_instance_id,24,1)='-' AND replace(listener_process_instance_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(listener_process_instance_id,15,1) IN ('1','2','3','4','5') AND substr(listener_process_instance_id,20,1) IN ('8','9','a','b')),
    process_id INTEGER NOT NULL CHECK (process_id>0),
    process_start_utc TEXT NOT NULL CHECK (length(process_start_utc)=27 AND substr(process_start_utc,27,1)='Z' AND julianday(process_start_utc) IS NOT NULL),
    contract_set_hash TEXT NOT NULL CHECK (length(contract_set_hash)=64 AND contract_set_hash=lower(contract_set_hash) AND contract_set_hash NOT GLOB '*[^0-9a-f]*'),
    grant_token_hash TEXT NOT NULL UNIQUE CHECK (length(grant_token_hash)=64 AND grant_token_hash=lower(grant_token_hash) AND grant_token_hash NOT GLOB '*[^0-9a-f]*'),
    grant_transaction_id TEXT NOT NULL,
    granted_at_utc TEXT NOT NULL CHECK (length(granted_at_utc)=27 AND substr(granted_at_utc,27,1)='Z' AND julianday(granted_at_utc) IS NOT NULL),
    fenced_at_utc TEXT NULL CHECK (fenced_at_utc IS NULL OR (length(fenced_at_utc)=27 AND substr(fenced_at_utc,27,1)='Z' AND julianday(fenced_at_utc) IS NOT NULL)),
    state TEXT NOT NULL CHECK (state IN ('GRANTED','CURRENT','FENCED','RETIRED')),
    writer_id TEXT NOT NULL CHECK (writer_id='LISTENER_EPOCH_WRITER'),
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (grant_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE recovery_transactions (
    recovery_transaction_id TEXT NOT NULL PRIMARY KEY CHECK (length(recovery_transaction_id)=36 AND recovery_transaction_id=lower(recovery_transaction_id) AND substr(recovery_transaction_id,9,1)='-' AND substr(recovery_transaction_id,14,1)='-' AND substr(recovery_transaction_id,19,1)='-' AND substr(recovery_transaction_id,24,1)='-' AND replace(recovery_transaction_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(recovery_transaction_id,15,1) IN ('1','2','3','4','5') AND substr(recovery_transaction_id,20,1) IN ('8','9','a','b')),
    recovery_type TEXT NOT NULL CHECK (recovery_type IN ('LISTENER_RESTART','LISTENER_ADOPTION','BRIDGE_RECYCLE','COLD_START','STORE_RESTORE','STORE_REINITIALIZE','STORE_BOOTSTRAP')),
    supervisor_generation_id TEXT NOT NULL,
    listener_epoch_id TEXT NULL,
    bridge_generation_id TEXT NULL,
    listener_restart_incident_id TEXT NULL,
    bridge_incident_id TEXT NULL,
    state TEXT NOT NULL CHECK (state IN ('OPEN','ACKNOWLEDGING','COMPLETED','FAILED','CANCELED')),
    required_domain_set_hash TEXT NOT NULL CHECK (length(required_domain_set_hash)=64 AND required_domain_set_hash=lower(required_domain_set_hash) AND required_domain_set_hash NOT GLOB '*[^0-9a-f]*'),
    opened_transaction_id TEXT NOT NULL,
    closed_transaction_id TEXT NULL,
    state_version INTEGER NOT NULL CHECK (state_version>=1),
    opened_at_utc TEXT NOT NULL CHECK (length(opened_at_utc)=27 AND substr(opened_at_utc,27,1)='Z' AND julianday(opened_at_utc) IS NOT NULL),
    closed_at_utc TEXT NULL CHECK (closed_at_utc IS NULL OR (length(closed_at_utc)=27 AND substr(closed_at_utc,27,1)='Z' AND julianday(closed_at_utc) IS NOT NULL)),
    writer_id TEXT NOT NULL CHECK (writer_id='RECOVERY_TRANSACTION_WRITER'),
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (listener_epoch_id) REFERENCES listener_epochs(listener_epoch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (bridge_generation_id) REFERENCES bridge_generations(bridge_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (listener_restart_incident_id) REFERENCES listener_restart_incidents(restart_incident_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (bridge_incident_id) REFERENCES bridge_incidents(bridge_incident_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (opened_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (closed_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CHECK ((state IN ('OPEN','ACKNOWLEDGING') AND closed_transaction_id IS NULL AND closed_at_utc IS NULL) OR (state IN ('COMPLETED','FAILED','CANCELED') AND closed_transaction_id IS NOT NULL AND closed_at_utc IS NOT NULL)),
    CHECK ((recovery_type IN ('LISTENER_RESTART','LISTENER_ADOPTION') AND listener_epoch_id IS NOT NULL AND bridge_generation_id IS NULL AND bridge_incident_id IS NULL) OR (recovery_type='BRIDGE_RECYCLE' AND listener_epoch_id IS NOT NULL AND bridge_generation_id IS NOT NULL AND bridge_incident_id IS NOT NULL AND listener_restart_incident_id IS NULL) OR (recovery_type='COLD_START' AND listener_epoch_id IS NOT NULL AND bridge_generation_id IS NULL AND listener_restart_incident_id IS NULL AND bridge_incident_id IS NULL) OR (recovery_type IN ('STORE_RESTORE','STORE_REINITIALIZE','STORE_BOOTSTRAP') AND listener_epoch_id IS NULL AND bridge_generation_id IS NULL AND listener_restart_incident_id IS NULL AND bridge_incident_id IS NULL))
) STRICT;

CREATE TABLE listener_current (
    singleton_id INTEGER NOT NULL PRIMARY KEY CHECK (singleton_id=1),
    supervisor_generation_id TEXT NOT NULL,
    listener_epoch_id TEXT NULL,
    lifecycle_state TEXT NOT NULL CHECK (lifecycle_state IN ('STOPPED','STARTING','REHYDRATING','HEALTHY','SUSPECT','FENCED','STOPPING','LISTENER_FAILED','AMBIGUOUS_PROCESS_AUTHORITY','SUPERVISOR_STORE_FAILED')),
    state_version INTEGER NOT NULL CHECK (state_version>=1),
    last_transition_id TEXT NOT NULL UNIQUE,
    current_restart_incident_id TEXT NULL,
    active_recovery_transaction_id TEXT NULL,
    update_transaction_id TEXT NOT NULL,
    writer_id TEXT NOT NULL CHECK (writer_id='LISTENER_STATE_WRITER'),
    committed_sequence INTEGER NOT NULL CHECK (committed_sequence>=0),
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,27,1)='Z' AND julianday(committed_at_utc) IS NOT NULL),
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (listener_epoch_id) REFERENCES listener_epochs(listener_epoch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (last_transition_id) REFERENCES listener_state_transitions(listener_transition_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (current_restart_incident_id) REFERENCES listener_restart_incidents(restart_incident_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (active_recovery_transaction_id) REFERENCES recovery_transactions(recovery_transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (update_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CHECK ((listener_epoch_id IS NULL AND lifecycle_state IN ('STOPPED','STARTING','AMBIGUOUS_PROCESS_AUTHORITY','SUPERVISOR_STORE_FAILED')) OR (listener_epoch_id IS NOT NULL AND lifecycle_state IN ('REHYDRATING','HEALTHY','SUSPECT','FENCED','STOPPING','LISTENER_FAILED')))
) STRICT;

CREATE TABLE listener_state_transitions (
    listener_transition_id TEXT NOT NULL PRIMARY KEY CHECK (length(listener_transition_id)=36 AND listener_transition_id=lower(listener_transition_id) AND substr(listener_transition_id,9,1)='-' AND substr(listener_transition_id,14,1)='-' AND substr(listener_transition_id,19,1)='-' AND substr(listener_transition_id,24,1)='-' AND replace(listener_transition_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(listener_transition_id,15,1) IN ('1','2','3','4','5') AND substr(listener_transition_id,20,1) IN ('8','9','a','b')),
    supervisor_generation_id TEXT NOT NULL,
    listener_epoch_id TEXT NULL,
    prior_state TEXT NOT NULL CHECK (prior_state IN ('NONE','STOPPED','STARTING','REHYDRATING','HEALTHY','SUSPECT','FENCED','STOPPING','LISTENER_FAILED','AMBIGUOUS_PROCESS_AUTHORITY','SUPERVISOR_STORE_FAILED')),
    resulting_state TEXT NOT NULL CHECK (resulting_state IN ('STOPPED','STARTING','REHYDRATING','HEALTHY','SUSPECT','FENCED','STOPPING','LISTENER_FAILED','AMBIGUOUS_PROCESS_AUTHORITY','SUPERVISOR_STORE_FAILED')),
    transition_reason TEXT NOT NULL,
    deciding_authority TEXT NOT NULL CHECK (deciding_authority='LISTENER_SUPERVISOR_STATE_EVALUATOR'),
    durable_writer TEXT NOT NULL CHECK (durable_writer='LISTENER_STATE_WRITER'),
    source_evidence_set_hash TEXT NOT NULL CHECK (length(source_evidence_set_hash)=64 AND source_evidence_set_hash=lower(source_evidence_set_hash) AND source_evidence_set_hash NOT GLOB '*[^0-9a-f]*'),
    restart_incident_id TEXT NULL,
    recovery_transaction_id TEXT NULL,
    transaction_id TEXT NOT NULL,
    expected_prior_version INTEGER NOT NULL CHECK (expected_prior_version>=0),
    resulting_version INTEGER NOT NULL CHECK (resulting_version=expected_prior_version+1),
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,27,1)='Z' AND julianday(committed_at_utc) IS NOT NULL),
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (listener_epoch_id) REFERENCES listener_epochs(listener_epoch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (restart_incident_id) REFERENCES listener_restart_incidents(restart_incident_id) ON UPDATE RESTRICT ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (recovery_transaction_id) REFERENCES recovery_transactions(recovery_transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    UNIQUE (transaction_id,resulting_version)
) STRICT;

CREATE TABLE listener_restart_incidents (
    restart_incident_id TEXT NOT NULL PRIMARY KEY CHECK (length(restart_incident_id)=36 AND restart_incident_id=lower(restart_incident_id) AND substr(restart_incident_id,9,1)='-' AND substr(restart_incident_id,14,1)='-' AND substr(restart_incident_id,19,1)='-' AND substr(restart_incident_id,24,1)='-' AND replace(restart_incident_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(restart_incident_id,15,1) IN ('1','2','3','4','5') AND substr(restart_incident_id,20,1) IN ('8','9','a','b')),
    supervisor_generation_id TEXT NOT NULL,
    listener_epoch_id TEXT NOT NULL,
    incident_state TEXT NOT NULL CHECK (incident_state IN ('RESTART_PENDING','RESTART_FENCED','RESTART_EXECUTING','RESTART_REHYDRATING','TERMINAL')),
    incident_version INTEGER NOT NULL CHECK (incident_version>=1),
    sff_predicate TEXT NOT NULL CHECK (sff_predicate IN ('SFF-01_LISTENER_EXITED','SFF-02_LISTENER_LEASE_LOST','SFF-03_BRIDGE_RECOVERY_EXHAUSTED')),
    observed_stale_timestamp_utc TEXT NOT NULL CHECK (length(observed_stale_timestamp_utc)=27 AND substr(observed_stale_timestamp_utc,27,1)='Z' AND julianday(observed_stale_timestamp_utc) IS NOT NULL),
    decision_timestamp_utc TEXT NOT NULL CHECK (length(decision_timestamp_utc)=27 AND substr(decision_timestamp_utc,27,1)='Z' AND julianday(decision_timestamp_utc) IS NOT NULL),
    fencing_token_hash TEXT NOT NULL CHECK (length(fencing_token_hash)=64 AND fencing_token_hash=lower(fencing_token_hash) AND fencing_token_hash NOT GLOB '*[^0-9a-f]*'),
    policy_identity TEXT NOT NULL,
    attempt_count INTEGER NOT NULL CHECK (attempt_count>=0),
    rate_window_started_utc TEXT NOT NULL CHECK (length(rate_window_started_utc)=27 AND substr(rate_window_started_utc,27,1)='Z' AND julianday(rate_window_started_utc) IS NOT NULL),
    evidence_set_hash TEXT NOT NULL CHECK (length(evidence_set_hash)=64 AND evidence_set_hash=lower(evidence_set_hash) AND evidence_set_hash NOT GLOB '*[^0-9a-f]*'),
    current_outcome_id TEXT NULL,
    last_transition_id TEXT NULL UNIQUE,
    update_transaction_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL CHECK (length(created_at_utc)=27 AND substr(created_at_utc,27,1)='Z' AND julianday(created_at_utc) IS NOT NULL),
    updated_at_utc TEXT NOT NULL CHECK (length(updated_at_utc)=27 AND substr(updated_at_utc,27,1)='Z' AND julianday(updated_at_utc) IS NOT NULL),
    writer_id TEXT NOT NULL CHECK (writer_id='LISTENER_INCIDENT_WRITER'),
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (listener_epoch_id) REFERENCES listener_epochs(listener_epoch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (policy_identity) REFERENCES shared_feed_policies(policy_identity) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (current_outcome_id) REFERENCES listener_restart_outcomes(listener_outcome_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (last_transition_id) REFERENCES listener_restart_incident_transitions(incident_transition_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (update_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CHECK ((incident_state='TERMINAL' AND current_outcome_id IS NOT NULL) OR (incident_state<>'TERMINAL' AND current_outcome_id IS NULL))
) STRICT;

CREATE TABLE listener_restart_incident_transitions (
    incident_transition_id TEXT NOT NULL PRIMARY KEY CHECK (length(incident_transition_id)=36 AND incident_transition_id=lower(incident_transition_id) AND substr(incident_transition_id,9,1)='-' AND substr(incident_transition_id,14,1)='-' AND substr(incident_transition_id,19,1)='-' AND substr(incident_transition_id,24,1)='-' AND replace(incident_transition_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(incident_transition_id,15,1) IN ('1','2','3','4','5') AND substr(incident_transition_id,20,1) IN ('8','9','a','b')),
    restart_incident_id TEXT NOT NULL,
    prior_incident_state TEXT NOT NULL CHECK (prior_incident_state IN ('RESTART_PENDING','RESTART_FENCED','RESTART_EXECUTING','RESTART_REHYDRATING')),
    resulting_incident_state TEXT NOT NULL CHECK (resulting_incident_state IN ('RESTART_FENCED','RESTART_EXECUTING','RESTART_REHYDRATING','TERMINAL')),
    transition_reason TEXT NOT NULL,
    deciding_authority TEXT NOT NULL CHECK (deciding_authority='LISTENER_SUPERVISOR_STATE_EVALUATOR'),
    durable_writer TEXT NOT NULL CHECK (durable_writer='LISTENER_INCIDENT_WRITER'),
    evidence_set_hash TEXT NOT NULL CHECK (length(evidence_set_hash)=64 AND evidence_set_hash=lower(evidence_set_hash) AND evidence_set_hash NOT GLOB '*[^0-9a-f]*'),
    transaction_id TEXT NOT NULL,
    expected_prior_version INTEGER NOT NULL CHECK (expected_prior_version>=1),
    resulting_version INTEGER NOT NULL CHECK (resulting_version=expected_prior_version+1),
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,27,1)='Z' AND julianday(committed_at_utc) IS NOT NULL),
    FOREIGN KEY (restart_incident_id) REFERENCES listener_restart_incidents(restart_incident_id) ON UPDATE RESTRICT ON DELETE CASCADE,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    UNIQUE (restart_incident_id,resulting_version)
) STRICT;

CREATE TABLE listener_restart_outcomes (
    listener_outcome_id TEXT NOT NULL PRIMARY KEY CHECK (length(listener_outcome_id)=36 AND listener_outcome_id=lower(listener_outcome_id) AND substr(listener_outcome_id,9,1)='-' AND substr(listener_outcome_id,14,1)='-' AND substr(listener_outcome_id,19,1)='-' AND substr(listener_outcome_id,24,1)='-' AND replace(listener_outcome_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(listener_outcome_id,15,1) IN ('1','2','3','4','5') AND substr(listener_outcome_id,20,1) IN ('8','9','a','b')),
    restart_incident_id TEXT NOT NULL UNIQUE,
    outcome TEXT NOT NULL CHECK (outcome IN ('RESTART_CANCELED','RESTART_COMPLETED','RESTART_FAILED','RECOVERY_RATE_LIMITED_FAILED')),
    resulting_listener_state TEXT NOT NULL CHECK (resulting_listener_state IN ('HEALTHY','SUSPECT','LISTENER_FAILED','FENCED','SUPERVISOR_STORE_FAILED')),
    rate_limit_evidence_hash TEXT NULL CHECK (rate_limit_evidence_hash IS NULL OR (length(rate_limit_evidence_hash)=64 AND rate_limit_evidence_hash=lower(rate_limit_evidence_hash) AND rate_limit_evidence_hash NOT GLOB '*[^0-9a-f]*')),
    automatic_retry_prohibited INTEGER NOT NULL CHECK (automatic_retry_prohibited IN (0,1)),
    escalation_identity TEXT NULL,
    evidence_set_hash TEXT NOT NULL CHECK (length(evidence_set_hash)=64 AND evidence_set_hash=lower(evidence_set_hash) AND evidence_set_hash NOT GLOB '*[^0-9a-f]*'),
    transaction_id TEXT NOT NULL,
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,27,1)='Z' AND julianday(committed_at_utc) IS NOT NULL),
    writer_id TEXT NOT NULL CHECK (writer_id='LISTENER_INCIDENT_WRITER'),
    FOREIGN KEY (restart_incident_id) REFERENCES listener_restart_incidents(restart_incident_id) ON UPDATE RESTRICT ON DELETE CASCADE,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CHECK ((outcome='RESTART_CANCELED' AND resulting_listener_state IN ('HEALTHY','SUSPECT') AND automatic_retry_prohibited=1 AND rate_limit_evidence_hash IS NULL) OR (outcome='RESTART_COMPLETED' AND resulting_listener_state='HEALTHY' AND automatic_retry_prohibited=1 AND rate_limit_evidence_hash IS NULL) OR (outcome='RESTART_FAILED' AND resulting_listener_state IN ('LISTENER_FAILED','FENCED','SUPERVISOR_STORE_FAILED') AND automatic_retry_prohibited=1 AND rate_limit_evidence_hash IS NULL) OR (outcome='RECOVERY_RATE_LIMITED_FAILED' AND resulting_listener_state='LISTENER_FAILED' AND automatic_retry_prohibited=1 AND rate_limit_evidence_hash IS NOT NULL))
) STRICT;

CREATE TABLE listener_fences (
    listener_fence_id TEXT NOT NULL PRIMARY KEY CHECK (length(listener_fence_id)=36 AND listener_fence_id=lower(listener_fence_id) AND substr(listener_fence_id,9,1)='-' AND substr(listener_fence_id,14,1)='-' AND substr(listener_fence_id,19,1)='-' AND substr(listener_fence_id,24,1)='-' AND replace(listener_fence_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(listener_fence_id,15,1) IN ('1','2','3','4','5') AND substr(listener_fence_id,20,1) IN ('8','9','a','b')),
    restart_incident_id TEXT NOT NULL UNIQUE,
    supervisor_generation_id TEXT NOT NULL,
    listener_epoch_id TEXT NOT NULL,
    fencing_token_hash TEXT NOT NULL UNIQUE CHECK (length(fencing_token_hash)=64 AND fencing_token_hash=lower(fencing_token_hash) AND fencing_token_hash NOT GLOB '*[^0-9a-f]*'),
    reason TEXT NOT NULL,
    evidence_set_hash TEXT NOT NULL CHECK (length(evidence_set_hash)=64 AND evidence_set_hash=lower(evidence_set_hash) AND evidence_set_hash NOT GLOB '*[^0-9a-f]*'),
    transaction_id TEXT NOT NULL,
    fenced_at_utc TEXT NOT NULL CHECK (length(fenced_at_utc)=27 AND substr(fenced_at_utc,27,1)='Z' AND julianday(fenced_at_utc) IS NOT NULL),
    writer_id TEXT NOT NULL CHECK (writer_id='LISTENER_INCIDENT_WRITER'),
    FOREIGN KEY (restart_incident_id) REFERENCES listener_restart_incidents(restart_incident_id) ON UPDATE RESTRICT ON DELETE CASCADE,
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (listener_epoch_id) REFERENCES listener_epochs(listener_epoch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE listener_execution_attempts (
    listener_execution_id TEXT NOT NULL PRIMARY KEY CHECK (length(listener_execution_id)=36 AND listener_execution_id=lower(listener_execution_id) AND substr(listener_execution_id,9,1)='-' AND substr(listener_execution_id,14,1)='-' AND substr(listener_execution_id,19,1)='-' AND substr(listener_execution_id,24,1)='-' AND replace(listener_execution_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(listener_execution_id,15,1) IN ('1','2','3','4','5') AND substr(listener_execution_id,20,1) IN ('8','9','a','b')),
    restart_incident_id TEXT NOT NULL UNIQUE,
    listener_fence_id TEXT NOT NULL UNIQUE,
    supervisor_generation_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL CHECK (attempt_number=1),
    child_authority_token_hash TEXT NOT NULL UNIQUE CHECK (length(child_authority_token_hash)=64 AND child_authority_token_hash=lower(child_authority_token_hash) AND child_authority_token_hash NOT GLOB '*[^0-9a-f]*'),
    command_hash TEXT NOT NULL CHECK (length(command_hash)=64 AND command_hash=lower(command_hash) AND command_hash NOT GLOB '*[^0-9a-f]*'),
    execution_state TEXT NOT NULL CHECK (execution_state IN ('STARTED','PROCESS_STOP_CONFIRMED','REPLACEMENT_STARTED','FAILED')),
    process_result_hash TEXT NULL CHECK (process_result_hash IS NULL OR (length(process_result_hash)=64 AND process_result_hash=lower(process_result_hash) AND process_result_hash NOT GLOB '*[^0-9a-f]*')),
    transaction_id TEXT NOT NULL,
    started_at_utc TEXT NOT NULL CHECK (length(started_at_utc)=27 AND substr(started_at_utc,27,1)='Z' AND julianday(started_at_utc) IS NOT NULL),
    completed_at_utc TEXT NULL CHECK (completed_at_utc IS NULL OR (length(completed_at_utc)=27 AND substr(completed_at_utc,27,1)='Z' AND julianday(completed_at_utc) IS NOT NULL)),
    writer_id TEXT NOT NULL CHECK (writer_id='LISTENER_INCIDENT_WRITER'),
    FOREIGN KEY (restart_incident_id) REFERENCES listener_restart_incidents(restart_incident_id) ON UPDATE RESTRICT ON DELETE CASCADE,
    FOREIGN KEY (listener_fence_id) REFERENCES listener_fences(listener_fence_id) ON UPDATE RESTRICT ON DELETE CASCADE,
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CHECK ((execution_state='STARTED' AND completed_at_utc IS NULL AND process_result_hash IS NULL) OR (execution_state<>'STARTED' AND completed_at_utc IS NOT NULL AND process_result_hash IS NOT NULL))
) STRICT;

CREATE TABLE listener_rehydrations (
    listener_rehydration_id TEXT NOT NULL PRIMARY KEY CHECK (length(listener_rehydration_id)=36 AND listener_rehydration_id=lower(listener_rehydration_id) AND substr(listener_rehydration_id,9,1)='-' AND substr(listener_rehydration_id,14,1)='-' AND substr(listener_rehydration_id,19,1)='-' AND substr(listener_rehydration_id,24,1)='-' AND replace(listener_rehydration_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(listener_rehydration_id,15,1) IN ('1','2','3','4','5') AND substr(listener_rehydration_id,20,1) IN ('8','9','a','b')),
    recovery_transaction_id TEXT NOT NULL UNIQUE,
    restart_incident_id TEXT NULL,
    supervisor_generation_id TEXT NOT NULL,
    listener_epoch_id TEXT NOT NULL,
    disposition TEXT NOT NULL CHECK (disposition IN ('ADOPT_EPOCH','NEW_EPOCH','COLD_START')),
    required_domain_set_hash TEXT NOT NULL CHECK (length(required_domain_set_hash)=64 AND required_domain_set_hash=lower(required_domain_set_hash) AND required_domain_set_hash NOT GLOB '*[^0-9a-f]*'),
    acknowledgement_progress_count INTEGER NOT NULL CHECK (acknowledgement_progress_count>=0),
    required_count INTEGER NOT NULL CHECK (required_count>0 AND acknowledgement_progress_count<=required_count),
    state TEXT NOT NULL CHECK (state IN ('OPEN','COMPLETE','FAILED')),
    state_version INTEGER NOT NULL CHECK (state_version>=1),
    transaction_id TEXT NOT NULL,
    opened_at_utc TEXT NOT NULL CHECK (length(opened_at_utc)=27 AND substr(opened_at_utc,27,1)='Z' AND julianday(opened_at_utc) IS NOT NULL),
    closed_at_utc TEXT NULL CHECK (closed_at_utc IS NULL OR (length(closed_at_utc)=27 AND substr(closed_at_utc,27,1)='Z' AND julianday(closed_at_utc) IS NOT NULL)),
    writer_id TEXT NOT NULL CHECK (writer_id='LISTENER_INCIDENT_WRITER'),
    FOREIGN KEY (recovery_transaction_id) REFERENCES recovery_transactions(recovery_transaction_id) ON UPDATE RESTRICT ON DELETE CASCADE,
    FOREIGN KEY (restart_incident_id) REFERENCES listener_restart_incidents(restart_incident_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (listener_epoch_id) REFERENCES listener_epochs(listener_epoch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CHECK ((state='OPEN' AND closed_at_utc IS NULL) OR (state IN ('COMPLETE','FAILED') AND closed_at_utc IS NOT NULL))
) STRICT;

CREATE TABLE recovery_required_domains (
    recovery_transaction_id TEXT NOT NULL,
    authoritative_domain TEXT NOT NULL CHECK (authoritative_domain IN ('FINALIZED_BARS','CANONICAL_RMA_ATR','EXECUTOR_INTAKE','TRADE_MANAGER_INTAKE','ENTRY_AGENT_RUNTIME')),
    expected_domain_identity TEXT NOT NULL CHECK (length(expected_domain_identity)=64 AND expected_domain_identity=lower(expected_domain_identity) AND expected_domain_identity NOT GLOB '*[^0-9a-f]*'),
    required INTEGER NOT NULL CHECK (required=1),
    writer_id TEXT NOT NULL CHECK (writer_id='LISTENER_ACKNOWLEDGEMENT_WRITER'),
    PRIMARY KEY (recovery_transaction_id,authoritative_domain),
    FOREIGN KEY (recovery_transaction_id) REFERENCES recovery_transactions(recovery_transaction_id) ON UPDATE RESTRICT ON DELETE CASCADE
) STRICT;

CREATE TABLE domain_acknowledgements (
    acknowledgement_id TEXT NOT NULL PRIMARY KEY CHECK (length(acknowledgement_id)=36 AND acknowledgement_id=lower(acknowledgement_id) AND substr(acknowledgement_id,9,1)='-' AND substr(acknowledgement_id,14,1)='-' AND substr(acknowledgement_id,19,1)='-' AND substr(acknowledgement_id,24,1)='-' AND replace(acknowledgement_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(acknowledgement_id,15,1) IN ('1','2','3','4','5') AND substr(acknowledgement_id,20,1) IN ('8','9','a','b')),
    recovery_transaction_id TEXT NOT NULL,
    supervisor_generation_id TEXT NOT NULL,
    listener_epoch_id TEXT NOT NULL,
    authoritative_domain TEXT NOT NULL CHECK (authoritative_domain IN ('FINALIZED_BARS','CANONICAL_RMA_ATR','EXECUTOR_INTAKE','TRADE_MANAGER_INTAKE','ENTRY_AGENT_RUNTIME')),
    expected_domain_identity TEXT NOT NULL CHECK (length(expected_domain_identity)=64 AND expected_domain_identity=lower(expected_domain_identity) AND expected_domain_identity NOT GLOB '*[^0-9a-f]*'),
    observed_domain_identity TEXT NOT NULL CHECK (length(observed_domain_identity)=64 AND observed_domain_identity=lower(observed_domain_identity) AND observed_domain_identity NOT GLOB '*[^0-9a-f]*'),
    acknowledgement_disposition TEXT NOT NULL CHECK (acknowledgement_disposition IN ('ACCEPTED','REJECTED_IDENTITY','REJECTED_INTEGRITY','REJECTED_STALE','REJECTED_UNAUTHENTICATED')),
    evidence_hash TEXT NOT NULL CHECK (length(evidence_hash)=64 AND evidence_hash=lower(evidence_hash) AND evidence_hash NOT GLOB '*[^0-9a-f]*'),
    evidence_producer TEXT NOT NULL,
    validator TEXT NOT NULL CHECK (validator='HEALTH_INGRESS'),
    evaluator TEXT NOT NULL CHECK (evaluator='LISTENER_SUPERVISOR_STATE_EVALUATOR'),
    durable_writer TEXT NOT NULL CHECK (durable_writer='LISTENER_ACKNOWLEDGEMENT_WRITER'),
    creation_sequence INTEGER NOT NULL CHECK (creation_sequence>=0),
    transaction_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL CHECK (length(created_at_utc)=27 AND substr(created_at_utc,27,1)='Z' AND julianday(created_at_utc) IS NOT NULL),
    FOREIGN KEY (recovery_transaction_id) REFERENCES recovery_transactions(recovery_transaction_id) ON UPDATE RESTRICT ON DELETE CASCADE,
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (listener_epoch_id) REFERENCES listener_epochs(listener_epoch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (recovery_transaction_id,authoritative_domain) REFERENCES recovery_required_domains(recovery_transaction_id,authoritative_domain) ON UPDATE RESTRICT ON DELETE CASCADE,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    UNIQUE (recovery_transaction_id,authoritative_domain,acknowledgement_disposition,observed_domain_identity),
    CHECK (acknowledgement_disposition<>'ACCEPTED' OR expected_domain_identity=observed_domain_identity)
) STRICT;

CREATE TABLE bridge_generations (
    bridge_generation_id TEXT NOT NULL PRIMARY KEY CHECK (length(bridge_generation_id)=36 AND bridge_generation_id=lower(bridge_generation_id) AND substr(bridge_generation_id,9,1)='-' AND substr(bridge_generation_id,14,1)='-' AND substr(bridge_generation_id,19,1)='-' AND substr(bridge_generation_id,24,1)='-' AND replace(bridge_generation_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(bridge_generation_id,15,1) IN ('1','2','3','4','5') AND substr(bridge_generation_id,20,1) IN ('8','9','a','b')),
    bridge_generation_sequence INTEGER NOT NULL CHECK (bridge_generation_sequence>=1),
    listener_epoch_id TEXT NOT NULL,
    supervisor_generation_id TEXT NOT NULL,
    grant_token_hash TEXT NOT NULL UNIQUE CHECK (length(grant_token_hash)=64 AND grant_token_hash=lower(grant_token_hash) AND grant_token_hash NOT GLOB '*[^0-9a-f]*'),
    controller_capability_hash TEXT NOT NULL CHECK (length(controller_capability_hash)=64 AND controller_capability_hash=lower(controller_capability_hash) AND controller_capability_hash NOT GLOB '*[^0-9a-f]*'),
    grant_transaction_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('GRANTED','CURRENT','FENCED','RETIRED')),
    granted_at_utc TEXT NOT NULL CHECK (length(granted_at_utc)=27 AND substr(granted_at_utc,27,1)='Z' AND julianday(granted_at_utc) IS NOT NULL),
    fenced_at_utc TEXT NULL CHECK (fenced_at_utc IS NULL OR (length(fenced_at_utc)=27 AND substr(fenced_at_utc,27,1)='Z' AND julianday(fenced_at_utc) IS NOT NULL)),
    writer_id TEXT NOT NULL CHECK (writer_id='BRIDGE_GENERATION_WRITER'),
    UNIQUE (listener_epoch_id,bridge_generation_sequence),
    FOREIGN KEY (listener_epoch_id) REFERENCES listener_epochs(listener_epoch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (grant_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE bridge_current (
    singleton_id INTEGER NOT NULL PRIMARY KEY CHECK (singleton_id=1),
    supervisor_generation_id TEXT NOT NULL,
    listener_epoch_id TEXT NOT NULL,
    bridge_generation_id TEXT NOT NULL,
    bridge_state TEXT NOT NULL CHECK (bridge_state IN ('BRIDGE_STARTUP_UNPROVEN','BRIDGE_STARTING','BRIDGE_READY','BRIDGE_SUSPECT','RECYCLE_PENDING','RECYCLE_CANCELED','BRIDGE_FENCED','RECYCLE_EXECUTING','BRIDGE_REHYDRATING','BRIDGE_FAILED','FAILED_RECOVERY_EXHAUSTED','PLANNED_SHUTDOWN','LISTENER_EPOCH_TRANSITION')),
    state_version INTEGER NOT NULL CHECK (state_version>=1),
    current_bridge_incident_id TEXT NULL,
    last_transition_id TEXT NOT NULL UNIQUE,
    update_transaction_id TEXT NOT NULL,
    committed_sequence INTEGER NOT NULL CHECK (committed_sequence>=0),
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,27,1)='Z' AND julianday(committed_at_utc) IS NOT NULL),
    writer_id TEXT NOT NULL CHECK (writer_id='HEALTH_DURABLE_WRITER'),
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (listener_epoch_id) REFERENCES listener_epochs(listener_epoch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (bridge_generation_id) REFERENCES bridge_generations(bridge_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (current_bridge_incident_id) REFERENCES bridge_incidents(bridge_incident_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (last_transition_id) REFERENCES bridge_transitions(bridge_transition_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (update_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE bridge_transitions (
    bridge_transition_id TEXT NOT NULL PRIMARY KEY CHECK (length(bridge_transition_id)=36 AND bridge_transition_id=lower(bridge_transition_id) AND substr(bridge_transition_id,9,1)='-' AND substr(bridge_transition_id,14,1)='-' AND substr(bridge_transition_id,19,1)='-' AND substr(bridge_transition_id,24,1)='-' AND replace(bridge_transition_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(bridge_transition_id,15,1) IN ('1','2','3','4','5') AND substr(bridge_transition_id,20,1) IN ('8','9','a','b')),
    bridge_generation_id TEXT NOT NULL,
    prior_state TEXT NOT NULL,
    resulting_state TEXT NOT NULL,
    reason TEXT NOT NULL,
    deciding_authority TEXT NOT NULL CHECK (deciding_authority='LISTENER_SUPERVISOR_STATE_EVALUATOR'),
    durable_writer TEXT NOT NULL CHECK (durable_writer='HEALTH_DURABLE_WRITER'),
    bridge_incident_id TEXT NULL,
    evidence_set_hash TEXT NOT NULL CHECK (length(evidence_set_hash)=64 AND evidence_set_hash=lower(evidence_set_hash) AND evidence_set_hash NOT GLOB '*[^0-9a-f]*'),
    transaction_id TEXT NOT NULL,
    expected_prior_version INTEGER NOT NULL CHECK (expected_prior_version>=0),
    resulting_version INTEGER NOT NULL CHECK (resulting_version=expected_prior_version+1),
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,27,1)='Z' AND julianday(committed_at_utc) IS NOT NULL),
    FOREIGN KEY (bridge_generation_id) REFERENCES bridge_generations(bridge_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (bridge_incident_id) REFERENCES bridge_incidents(bridge_incident_id) ON UPDATE RESTRICT ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    UNIQUE (bridge_generation_id,resulting_version)
) STRICT;

CREATE TABLE bridge_incidents (
    bridge_incident_id TEXT NOT NULL PRIMARY KEY CHECK (length(bridge_incident_id)=36 AND bridge_incident_id=lower(bridge_incident_id) AND substr(bridge_incident_id,9,1)='-' AND substr(bridge_incident_id,14,1)='-' AND substr(bridge_incident_id,19,1)='-' AND substr(bridge_incident_id,24,1)='-' AND replace(bridge_incident_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(bridge_incident_id,15,1) IN ('1','2','3','4','5') AND substr(bridge_incident_id,20,1) IN ('8','9','a','b')),
    supervisor_generation_id TEXT NOT NULL,
    listener_epoch_id TEXT NOT NULL,
    bridge_generation_id TEXT NOT NULL,
    incident_state TEXT NOT NULL CHECK (incident_state IN ('RECYCLE_PENDING','BRIDGE_FENCED','RECYCLE_EXECUTING','BRIDGE_REHYDRATING','TERMINAL')),
    incident_version INTEGER NOT NULL CHECK (incident_version>=1),
    bdp_predicate TEXT NOT NULL CHECK (bdp_predicate IN ('BDP-01_UNEXPECTED_PROCESS_EXIT','BDP-02_AUTH_FAILURE','BDP-03_CONNECTION_FAILURE','BDP-04_SUBSCRIPTION_FAILURE')),
    policy_identity TEXT NOT NULL,
    attempt_count INTEGER NOT NULL CHECK (attempt_count>=0),
    deadline_utc TEXT NOT NULL CHECK (length(deadline_utc)=27 AND substr(deadline_utc,27,1)='Z' AND julianday(deadline_utc) IS NOT NULL),
    evidence_set_hash TEXT NOT NULL CHECK (length(evidence_set_hash)=64 AND evidence_set_hash=lower(evidence_set_hash) AND evidence_set_hash NOT GLOB '*[^0-9a-f]*'),
    current_outcome_id TEXT NULL,
    last_transition_id TEXT NULL UNIQUE,
    update_transaction_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL CHECK (length(created_at_utc)=27 AND substr(created_at_utc,27,1)='Z' AND julianday(created_at_utc) IS NOT NULL),
    updated_at_utc TEXT NOT NULL CHECK (length(updated_at_utc)=27 AND substr(updated_at_utc,27,1)='Z' AND julianday(updated_at_utc) IS NOT NULL),
    writer_id TEXT NOT NULL CHECK (writer_id='HEALTH_DURABLE_WRITER'),
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (listener_epoch_id) REFERENCES listener_epochs(listener_epoch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (bridge_generation_id) REFERENCES bridge_generations(bridge_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (policy_identity) REFERENCES shared_feed_policies(policy_identity) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (current_outcome_id) REFERENCES bridge_outcomes(bridge_outcome_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (last_transition_id) REFERENCES bridge_transitions(bridge_transition_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (update_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CHECK ((incident_state='TERMINAL' AND current_outcome_id IS NOT NULL) OR (incident_state<>'TERMINAL' AND current_outcome_id IS NULL))
) STRICT;

CREATE TABLE bridge_recycle_attempts (
    bridge_attempt_id TEXT NOT NULL PRIMARY KEY CHECK (length(bridge_attempt_id)=36 AND bridge_attempt_id=lower(bridge_attempt_id) AND substr(bridge_attempt_id,9,1)='-' AND substr(bridge_attempt_id,14,1)='-' AND substr(bridge_attempt_id,19,1)='-' AND substr(bridge_attempt_id,24,1)='-' AND replace(bridge_attempt_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(bridge_attempt_id,15,1) IN ('1','2','3','4','5') AND substr(bridge_attempt_id,20,1) IN ('8','9','a','b')),
    bridge_incident_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL CHECK (attempt_number>=1),
    bridge_generation_id TEXT NOT NULL,
    command_hash TEXT NOT NULL CHECK (length(command_hash)=64 AND command_hash=lower(command_hash) AND command_hash NOT GLOB '*[^0-9a-f]*'),
    fencing_token_hash TEXT NOT NULL UNIQUE CHECK (length(fencing_token_hash)=64 AND fencing_token_hash=lower(fencing_token_hash) AND fencing_token_hash NOT GLOB '*[^0-9a-f]*'),
    controller_ack_hash TEXT NULL CHECK (controller_ack_hash IS NULL OR (length(controller_ack_hash)=64 AND controller_ack_hash=lower(controller_ack_hash) AND controller_ack_hash NOT GLOB '*[^0-9a-f]*')),
    execution_result TEXT NULL CHECK (execution_result IS NULL OR execution_result IN ('READY','FAILED','TIMED_OUT','CANCELED')),
    transaction_id TEXT NOT NULL,
    started_at_utc TEXT NOT NULL CHECK (length(started_at_utc)=27 AND substr(started_at_utc,27,1)='Z' AND julianday(started_at_utc) IS NOT NULL),
    completed_at_utc TEXT NULL CHECK (completed_at_utc IS NULL OR (length(completed_at_utc)=27 AND substr(completed_at_utc,27,1)='Z' AND julianday(completed_at_utc) IS NOT NULL)),
    writer_id TEXT NOT NULL CHECK (writer_id='HEALTH_DURABLE_WRITER'),
    FOREIGN KEY (bridge_incident_id) REFERENCES bridge_incidents(bridge_incident_id) ON UPDATE RESTRICT ON DELETE CASCADE,
    FOREIGN KEY (bridge_generation_id) REFERENCES bridge_generations(bridge_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    UNIQUE (bridge_incident_id,attempt_number),
    CHECK ((execution_result IS NULL AND controller_ack_hash IS NULL AND completed_at_utc IS NULL) OR (execution_result IS NOT NULL AND controller_ack_hash IS NOT NULL AND completed_at_utc IS NOT NULL))
) STRICT;

CREATE TABLE bridge_outcomes (
    bridge_outcome_id TEXT NOT NULL PRIMARY KEY CHECK (length(bridge_outcome_id)=36 AND bridge_outcome_id=lower(bridge_outcome_id) AND substr(bridge_outcome_id,9,1)='-' AND substr(bridge_outcome_id,14,1)='-' AND substr(bridge_outcome_id,19,1)='-' AND substr(bridge_outcome_id,24,1)='-' AND replace(bridge_outcome_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(bridge_outcome_id,15,1) IN ('1','2','3','4','5') AND substr(bridge_outcome_id,20,1) IN ('8','9','a','b')),
    bridge_incident_id TEXT NOT NULL UNIQUE,
    outcome TEXT NOT NULL CHECK (outcome IN ('RECYCLE_CANCELED','BRIDGE_READY','BRIDGE_FAILED','FAILED_RECOVERY_EXHAUSTED','PLANNED_SHUTDOWN','LISTENER_EPOCH_TRANSITION')),
    resulting_bridge_state TEXT NOT NULL CHECK (resulting_bridge_state IN ('RECYCLE_CANCELED','BRIDGE_READY','BRIDGE_FAILED','FAILED_RECOVERY_EXHAUSTED','PLANNED_SHUTDOWN','LISTENER_EPOCH_TRANSITION')),
    automatic_retry_prohibited INTEGER NOT NULL CHECK (automatic_retry_prohibited IN (0,1)),
    rate_or_deadline_evidence_hash TEXT NULL CHECK (rate_or_deadline_evidence_hash IS NULL OR (length(rate_or_deadline_evidence_hash)=64 AND rate_or_deadline_evidence_hash=lower(rate_or_deadline_evidence_hash) AND rate_or_deadline_evidence_hash NOT GLOB '*[^0-9a-f]*')),
    escalation_identity TEXT NULL,
    evidence_set_hash TEXT NOT NULL CHECK (length(evidence_set_hash)=64 AND evidence_set_hash=lower(evidence_set_hash) AND evidence_set_hash NOT GLOB '*[^0-9a-f]*'),
    transaction_id TEXT NOT NULL,
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,27,1)='Z' AND julianday(committed_at_utc) IS NOT NULL),
    writer_id TEXT NOT NULL CHECK (writer_id='HEALTH_DURABLE_WRITER'),
    FOREIGN KEY (bridge_incident_id) REFERENCES bridge_incidents(bridge_incident_id) ON UPDATE RESTRICT ON DELETE CASCADE,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CHECK (outcome=resulting_bridge_state),
    CHECK ((outcome='FAILED_RECOVERY_EXHAUSTED' AND automatic_retry_prohibited=1 AND rate_or_deadline_evidence_hash IS NOT NULL) OR (outcome<>'FAILED_RECOVERY_EXHAUSTED' AND rate_or_deadline_evidence_hash IS NULL))
) STRICT;

CREATE TABLE producer_registrations (
    producer_instance_id TEXT NOT NULL PRIMARY KEY CHECK (length(producer_instance_id)=36 AND producer_instance_id=lower(producer_instance_id) AND substr(producer_instance_id,9,1)='-' AND substr(producer_instance_id,14,1)='-' AND substr(producer_instance_id,19,1)='-' AND substr(producer_instance_id,24,1)='-' AND replace(producer_instance_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(producer_instance_id,15,1) IN ('1','2','3','4','5') AND substr(producer_instance_id,20,1) IN ('8','9','a','b')),
    producer_role TEXT NOT NULL CHECK (producer_role IN ('RITHMIC_LISTENER','BRIDGE_CONTROLLER','EXECUTOR','TRADE_MANAGER','ENTRY_AGENT','OS_ADAPTER','RAPI_ADAPTER','CLOCK_ADAPTER')),
    process_id INTEGER NOT NULL CHECK (process_id>0),
    process_start_utc TEXT NOT NULL CHECK (length(process_start_utc)=27 AND substr(process_start_utc,27,1)='Z' AND julianday(process_start_utc) IS NOT NULL),
    build_hash TEXT NOT NULL CHECK (length(build_hash)=64 AND build_hash=lower(build_hash) AND build_hash NOT GLOB '*[^0-9a-f]*'),
    capability_key_id TEXT NOT NULL CHECK (length(capability_key_id)=36 AND capability_key_id=lower(capability_key_id) AND substr(capability_key_id,9,1)='-' AND substr(capability_key_id,14,1)='-' AND substr(capability_key_id,19,1)='-' AND substr(capability_key_id,24,1)='-' AND replace(capability_key_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(capability_key_id,15,1) IN ('1','2','3','4','5') AND substr(capability_key_id,20,1) IN ('8','9','a','b')),
    scope_json TEXT NOT NULL CHECK (json_valid(scope_json)=1 AND json_type(scope_json)='object'),
    issued_sequence INTEGER NOT NULL CHECK (issued_sequence>=0),
    revoked_sequence INTEGER NULL CHECK (revoked_sequence IS NULL OR revoked_sequence>issued_sequence),
    registration_transaction_id TEXT NOT NULL,
    writer_id TEXT NOT NULL CHECK (writer_id='HEALTH_DURABLE_WRITER'),
    UNIQUE (producer_role,process_id,process_start_utc),
    FOREIGN KEY (registration_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE health_events (
    health_event_id TEXT NOT NULL PRIMARY KEY CHECK (length(health_event_id)=36 AND health_event_id=lower(health_event_id) AND substr(health_event_id,9,1)='-' AND substr(health_event_id,14,1)='-' AND substr(health_event_id,19,1)='-' AND substr(health_event_id,24,1)='-' AND replace(health_event_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(health_event_id,15,1) IN ('1','2','3','4','5') AND substr(health_event_id,20,1) IN ('8','9','a','b')),
    producer_instance_id TEXT NOT NULL,
    producer_sequence INTEGER NOT NULL CHECK (producer_sequence>=1),
    supervisor_generation_id TEXT NOT NULL,
    listener_epoch_id TEXT NOT NULL,
    bridge_generation_id TEXT NULL,
    fact_type TEXT NOT NULL CHECK (fact_type IN ('DIRECT_PROOF_OF_LIFE','SUBSCRIPTION_PROOF','TRANSPORT_STATUS','AUTHENTICATION_STATUS','AUTHORITY_COHERENCE_STATUS','TIME_AUTHORITY_STATUS','DOWNSTREAM_DELIVERY','TERMINATION_OBSERVATION')),
    scope_key TEXT NOT NULL CHECK (scope_key IN ('GLOBAL','NQ','YM','NQ_YM_SHARED_FEED')),
    canonical_event_json TEXT NOT NULL CHECK (json_valid(canonical_event_json)=1 AND json_type(canonical_event_json)='object'),
    event_sha256 TEXT NOT NULL CHECK (length(event_sha256)=64 AND event_sha256=lower(event_sha256) AND event_sha256 NOT GLOB '*[^0-9a-f]*'),
    observed_monotonic_ns INTEGER NOT NULL CHECK (observed_monotonic_ns>=0),
    observed_at_utc TEXT NOT NULL CHECK (length(observed_at_utc)=27 AND substr(observed_at_utc,27,1)='Z' AND julianday(observed_at_utc) IS NOT NULL),
    ingress_sequence INTEGER NOT NULL CHECK (ingress_sequence>=0),
    authentication_disposition TEXT NOT NULL CHECK (authentication_disposition IN ('AUTHENTICATED','REJECTED')),
    transaction_id TEXT NOT NULL,
    writer_id TEXT NOT NULL CHECK (writer_id='HEALTH_DURABLE_WRITER'),
    FOREIGN KEY (producer_instance_id) REFERENCES producer_registrations(producer_instance_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (listener_epoch_id) REFERENCES listener_epochs(listener_epoch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (bridge_generation_id) REFERENCES bridge_generations(bridge_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    UNIQUE (producer_instance_id,producer_sequence)
) STRICT;

CREATE TABLE health_current (
    health_dimension TEXT NOT NULL CHECK (health_dimension IN ('PERSISTENCE','TRANSPORT','AUTHENTICATION','AUTHORITY_COHERENCE','TIME_AUTHORITY')),
    scope_key TEXT NOT NULL CHECK (scope_key IN ('GLOBAL','NQ_YM_SHARED_FEED')),
    health_state TEXT NOT NULL CHECK (health_state IN ('HEALTH_STARTUP_UNPROVEN','HEALTH_PERSISTENCE_READY','HEALTH_PERSISTENCE_DEGRADED','HEALTH_STORE_CORRUPT','HEALTH_TRANSPORT_READY','HEALTH_TRANSPORT_DEGRADED','HEALTH_AUTHENTICATION_READY','HEALTH_AUTHENTICATION_FAILED','HEALTH_AUTHORITY_COHERENT','HEALTH_AUTHORITY_DIVERGED','HEALTH_TIME_AUTHORITY_READY','HEALTH_TIME_AUTHORITY_DEGRADED')),
    state_version INTEGER NOT NULL CHECK (state_version>=1),
    supervisor_generation_id TEXT NOT NULL,
    listener_epoch_id TEXT NULL,
    bridge_generation_id TEXT NULL,
    last_transition_id TEXT NULL UNIQUE,
    source_event_id TEXT NULL,
    update_transaction_id TEXT NOT NULL,
    committed_sequence INTEGER NOT NULL CHECK (committed_sequence>=0),
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,27,1)='Z' AND julianday(committed_at_utc) IS NOT NULL),
    writer_id TEXT NOT NULL CHECK (writer_id='HEALTH_DURABLE_WRITER'),
    PRIMARY KEY (health_dimension,scope_key),
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (listener_epoch_id) REFERENCES listener_epochs(listener_epoch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (bridge_generation_id) REFERENCES bridge_generations(bridge_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (last_transition_id) REFERENCES health_transitions(health_transition_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (source_event_id) REFERENCES health_events(health_event_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (update_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CHECK ((health_dimension IN ('PERSISTENCE','TIME_AUTHORITY') AND scope_key='GLOBAL') OR (health_dimension IN ('TRANSPORT','AUTHENTICATION','AUTHORITY_COHERENCE') AND scope_key='NQ_YM_SHARED_FEED')),
    CHECK ((health_dimension='PERSISTENCE' AND health_state IN ('HEALTH_STARTUP_UNPROVEN','HEALTH_PERSISTENCE_READY','HEALTH_PERSISTENCE_DEGRADED','HEALTH_STORE_CORRUPT')) OR (health_dimension='TRANSPORT' AND health_state IN ('HEALTH_STARTUP_UNPROVEN','HEALTH_TRANSPORT_READY','HEALTH_TRANSPORT_DEGRADED')) OR (health_dimension='AUTHENTICATION' AND health_state IN ('HEALTH_STARTUP_UNPROVEN','HEALTH_AUTHENTICATION_READY','HEALTH_AUTHENTICATION_FAILED')) OR (health_dimension='AUTHORITY_COHERENCE' AND health_state IN ('HEALTH_STARTUP_UNPROVEN','HEALTH_AUTHORITY_COHERENT','HEALTH_AUTHORITY_DIVERGED')) OR (health_dimension='TIME_AUTHORITY' AND health_state IN ('HEALTH_STARTUP_UNPROVEN','HEALTH_TIME_AUTHORITY_READY','HEALTH_TIME_AUTHORITY_DEGRADED'))),
    CHECK ((health_state IN ('HEALTH_STARTUP_UNPROVEN','HEALTH_PERSISTENCE_DEGRADED','HEALTH_STORE_CORRUPT') AND listener_epoch_id IS NULL AND bridge_generation_id IS NULL AND last_transition_id IS NULL AND source_event_id IS NULL) OR (health_state NOT IN ('HEALTH_STARTUP_UNPROVEN','HEALTH_PERSISTENCE_DEGRADED','HEALTH_STORE_CORRUPT') AND listener_epoch_id IS NOT NULL AND last_transition_id IS NOT NULL AND source_event_id IS NOT NULL))
) STRICT;

CREATE TABLE health_transitions (
    health_transition_id TEXT NOT NULL PRIMARY KEY CHECK (length(health_transition_id)=36 AND health_transition_id=lower(health_transition_id) AND substr(health_transition_id,9,1)='-' AND substr(health_transition_id,14,1)='-' AND substr(health_transition_id,19,1)='-' AND substr(health_transition_id,24,1)='-' AND replace(health_transition_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(health_transition_id,15,1) IN ('1','2','3','4','5') AND substr(health_transition_id,20,1) IN ('8','9','a','b')),
    health_dimension TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    prior_state TEXT NOT NULL,
    resulting_state TEXT NOT NULL,
    reason TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    deciding_authority TEXT NOT NULL CHECK (deciding_authority='LISTENER_SUPERVISOR_STATE_EVALUATOR'),
    durable_writer TEXT NOT NULL CHECK (durable_writer='HEALTH_DURABLE_WRITER'),
    transaction_id TEXT NOT NULL,
    expected_prior_version INTEGER NOT NULL CHECK (expected_prior_version>=1),
    resulting_version INTEGER NOT NULL CHECK (resulting_version=expected_prior_version+1),
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,27,1)='Z' AND julianday(committed_at_utc) IS NOT NULL),
    FOREIGN KEY (health_dimension,scope_key) REFERENCES health_current(health_dimension,scope_key) ON UPDATE CASCADE ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (source_event_id) REFERENCES health_events(health_event_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    UNIQUE (health_dimension,scope_key,resulting_version)
) STRICT;

CREATE TABLE health_aggregate (
    singleton_id INTEGER NOT NULL PRIMARY KEY CHECK (singleton_id=1),
    aggregate_state TEXT NOT NULL CHECK (aggregate_state IN ('HEALTH_READY','HEALTH_DEGRADED','HEALTH_CORRUPT','HEALTH_STARTUP_UNPROVEN')),
    aggregate_version INTEGER NOT NULL CHECK (aggregate_version>=1),
    dimension_set_hash TEXT NOT NULL CHECK (length(dimension_set_hash)=64 AND dimension_set_hash=lower(dimension_set_hash) AND dimension_set_hash NOT GLOB '*[^0-9a-f]*'),
    blocking_dimension_set_json TEXT NOT NULL CHECK (json_valid(blocking_dimension_set_json)=1 AND json_type(blocking_dimension_set_json)='array'),
    blocking_dimension_set_hash TEXT NOT NULL CHECK (length(blocking_dimension_set_hash)=64 AND blocking_dimension_set_hash=lower(blocking_dimension_set_hash) AND blocking_dimension_set_hash NOT GLOB '*[^0-9a-f]*'),
    update_transaction_id TEXT NOT NULL,
    committed_sequence INTEGER NOT NULL CHECK (committed_sequence>=0),
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,27,1)='Z' AND julianday(committed_at_utc) IS NOT NULL),
    writer_id TEXT NOT NULL CHECK (writer_id='HEALTH_DURABLE_WRITER'),
    FOREIGN KEY (update_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE subscription_verifications (
    subscription_verification_id TEXT NOT NULL PRIMARY KEY CHECK (length(subscription_verification_id)=36 AND subscription_verification_id=lower(subscription_verification_id) AND substr(subscription_verification_id,9,1)='-' AND substr(subscription_verification_id,14,1)='-' AND substr(subscription_verification_id,19,1)='-' AND substr(subscription_verification_id,24,1)='-' AND replace(subscription_verification_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(subscription_verification_id,15,1) IN ('1','2','3','4','5') AND substr(subscription_verification_id,20,1) IN ('8','9','a','b')),
    symbol TEXT NOT NULL CHECK (symbol IN ('NQ','YM')),
    contract_session_ref_id TEXT NOT NULL,
    supervisor_generation_id TEXT NOT NULL,
    listener_epoch_id TEXT NOT NULL,
    bridge_generation_id TEXT NOT NULL,
    source_health_event_id TEXT NOT NULL,
    proof_producer_id TEXT NOT NULL,
    validator TEXT NOT NULL CHECK (validator='HEALTH_INGRESS'),
    evaluator TEXT NOT NULL CHECK (evaluator='LISTENER_SUPERVISOR_STATE_EVALUATOR'),
    disposition TEXT NOT NULL CHECK (disposition IN ('SUBSCRIPTION_VERIFIED','REJECTED')),
    evidence_hash TEXT NOT NULL CHECK (length(evidence_hash)=64 AND evidence_hash=lower(evidence_hash) AND evidence_hash NOT GLOB '*[^0-9a-f]*'),
    transaction_id TEXT NOT NULL,
    verified_at_utc TEXT NOT NULL CHECK (length(verified_at_utc)=27 AND substr(verified_at_utc,27,1)='Z' AND julianday(verified_at_utc) IS NOT NULL),
    writer_id TEXT NOT NULL CHECK (writer_id='HEALTH_DURABLE_WRITER'),
    FOREIGN KEY (contract_session_ref_id) REFERENCES active_contract_sessions(contract_session_ref_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (listener_epoch_id) REFERENCES listener_epochs(listener_epoch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (bridge_generation_id) REFERENCES bridge_generations(bridge_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (source_health_event_id) REFERENCES health_events(health_event_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (proof_producer_id) REFERENCES producer_registrations(producer_instance_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE termination_evidence (
    termination_evidence_id TEXT NOT NULL PRIMARY KEY CHECK (length(termination_evidence_id)=36 AND termination_evidence_id=lower(termination_evidence_id) AND substr(termination_evidence_id,9,1)='-' AND substr(termination_evidence_id,14,1)='-' AND substr(termination_evidence_id,19,1)='-' AND substr(termination_evidence_id,24,1)='-' AND replace(termination_evidence_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(termination_evidence_id,15,1) IN ('1','2','3','4','5') AND substr(termination_evidence_id,20,1) IN ('8','9','a','b')),
    bridge_generation_id TEXT NOT NULL,
    producer_instance_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL CHECK (evidence_type IN ('RAPI_CALLBACK','PROCESS_EXIT','PROCESS_EXCEPTION','SUPERVISOR_COMMAND','OPERATOR_COMMAND','OS_HANDLE','LISTENER_SHUTDOWN','STARTUP_TRANSITION')),
    canonical_evidence_json TEXT NOT NULL CHECK (json_valid(canonical_evidence_json)=1 AND json_type(canonical_evidence_json)='object'),
    evidence_sha256 TEXT NOT NULL CHECK (length(evidence_sha256)=64 AND evidence_sha256=lower(evidence_sha256) AND evidence_sha256 NOT GLOB '*[^0-9a-f]*'),
    authentication_disposition TEXT NOT NULL CHECK (authentication_disposition IN ('AUTHENTICATED','REJECTED')),
    observed_at_utc TEXT NOT NULL CHECK (length(observed_at_utc)=27 AND substr(observed_at_utc,27,1)='Z' AND julianday(observed_at_utc) IS NOT NULL),
    observed_monotonic_ns INTEGER NOT NULL CHECK (observed_monotonic_ns>=0),
    transaction_id TEXT NOT NULL,
    writer_id TEXT NOT NULL CHECK (writer_id='HEALTH_DURABLE_WRITER'),
    FOREIGN KEY (bridge_generation_id) REFERENCES bridge_generations(bridge_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (producer_instance_id) REFERENCES producer_registrations(producer_instance_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE termination_results (
    termination_result_id TEXT NOT NULL PRIMARY KEY CHECK (length(termination_result_id)=36 AND termination_result_id=lower(termination_result_id) AND substr(termination_result_id,9,1)='-' AND substr(termination_result_id,14,1)='-' AND substr(termination_result_id,19,1)='-' AND substr(termination_result_id,24,1)='-' AND replace(termination_result_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(termination_result_id,15,1) IN ('1','2','3','4','5') AND substr(termination_result_id,20,1) IN ('8','9','a','b')),
    bridge_generation_id TEXT NOT NULL UNIQUE,
    initiator TEXT NOT NULL,
    requested_action TEXT NOT NULL,
    execution_method TEXT NOT NULL,
    observed_cause TEXT NOT NULL,
    result TEXT NOT NULL,
    initiator_evidence_set_hash TEXT NOT NULL CHECK (length(initiator_evidence_set_hash)=64 AND initiator_evidence_set_hash=lower(initiator_evidence_set_hash) AND initiator_evidence_set_hash NOT GLOB '*[^0-9a-f]*'),
    requested_action_evidence_set_hash TEXT NOT NULL CHECK (length(requested_action_evidence_set_hash)=64 AND requested_action_evidence_set_hash=lower(requested_action_evidence_set_hash) AND requested_action_evidence_set_hash NOT GLOB '*[^0-9a-f]*'),
    execution_method_evidence_set_hash TEXT NOT NULL CHECK (length(execution_method_evidence_set_hash)=64 AND execution_method_evidence_set_hash=lower(execution_method_evidence_set_hash) AND execution_method_evidence_set_hash NOT GLOB '*[^0-9a-f]*'),
    observed_cause_evidence_set_hash TEXT NOT NULL CHECK (length(observed_cause_evidence_set_hash)=64 AND observed_cause_evidence_set_hash=lower(observed_cause_evidence_set_hash) AND observed_cause_evidence_set_hash NOT GLOB '*[^0-9a-f]*'),
    result_evidence_set_hash TEXT NOT NULL CHECK (length(result_evidence_set_hash)=64 AND result_evidence_set_hash=lower(result_evidence_set_hash) AND result_evidence_set_hash NOT GLOB '*[^0-9a-f]*'),
    evaluator TEXT NOT NULL CHECK (evaluator='LISTENER_SUPERVISOR_STATE_EVALUATOR'),
    durable_writer TEXT NOT NULL CHECK (durable_writer='HEALTH_DURABLE_WRITER'),
    classification_version INTEGER NOT NULL CHECK (classification_version>=1),
    transaction_id TEXT NOT NULL,
    classified_at_utc TEXT NOT NULL CHECK (length(classified_at_utc)=27 AND substr(classified_at_utc,27,1)='Z' AND julianday(classified_at_utc) IS NOT NULL),
    FOREIGN KEY (bridge_generation_id) REFERENCES bridge_generations(bridge_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE market_data_expectations (
    expectation_id TEXT NOT NULL PRIMARY KEY CHECK (length(expectation_id)=36 AND expectation_id=lower(expectation_id) AND substr(expectation_id,9,1)='-' AND substr(expectation_id,14,1)='-' AND substr(expectation_id,19,1)='-' AND substr(expectation_id,24,1)='-' AND replace(expectation_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(expectation_id,15,1) IN ('1','2','3','4','5') AND substr(expectation_id,20,1) IN ('8','9','a','b')),
    symbol TEXT NOT NULL CHECK (symbol IN ('NQ','YM')),
    contract_session_ref_id TEXT NOT NULL,
    policy_identity TEXT NOT NULL,
    supervisor_generation_id TEXT NOT NULL,
    listener_epoch_id TEXT NOT NULL,
    expectation_state TEXT NOT NULL CHECK (expectation_state IN ('EXPECTATION_STARTUP_UNPROVEN','DATA_EXPECTED','DATA_NOT_EXPECTED','EXPECTATION_EXPIRED')),
    calendar_identity TEXT NOT NULL CHECK (length(calendar_identity)=64 AND calendar_identity=lower(calendar_identity) AND calendar_identity NOT GLOB '*[^0-9a-f]*'),
    subscription_intent_identity TEXT NOT NULL CHECK (length(subscription_intent_identity)=64 AND subscription_intent_identity=lower(subscription_intent_identity) AND subscription_intent_identity NOT GLOB '*[^0-9a-f]*'),
    clock_evidence_hash TEXT NOT NULL CHECK (length(clock_evidence_hash)=64 AND clock_evidence_hash=lower(clock_evidence_hash) AND clock_evidence_hash NOT GLOB '*[^0-9a-f]*'),
    valid_from_utc TEXT NOT NULL CHECK (length(valid_from_utc)=27 AND substr(valid_from_utc,27,1)='Z' AND julianday(valid_from_utc) IS NOT NULL),
    expires_at_utc TEXT NOT NULL CHECK (length(expires_at_utc)=27 AND substr(expires_at_utc,27,1)='Z' AND julianday(expires_at_utc) IS NOT NULL AND expires_at_utc>valid_from_utc),
    current INTEGER NOT NULL CHECK (current IN (0,1)),
    evaluation_transaction_id TEXT NOT NULL,
    evaluated_at_utc TEXT NOT NULL CHECK (length(evaluated_at_utc)=27 AND substr(evaluated_at_utc,27,1)='Z' AND julianday(evaluated_at_utc) IS NOT NULL),
    writer_id TEXT NOT NULL CHECK (writer_id='LISTENER_INCIDENT_WRITER'),
    FOREIGN KEY (contract_session_ref_id) REFERENCES active_contract_sessions(contract_session_ref_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (policy_identity) REFERENCES shared_feed_policies(policy_identity) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (listener_epoch_id) REFERENCES listener_epochs(listener_epoch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (evaluation_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE projection_cursors (
    projection_name TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    source_transaction_sequence INTEGER NOT NULL CHECK (source_transaction_sequence>=0),
    published_transaction_sequence INTEGER NOT NULL CHECK (published_transaction_sequence>=0 AND published_transaction_sequence<=source_transaction_sequence),
    source_hash TEXT NOT NULL CHECK (length(source_hash)=64 AND source_hash=lower(source_hash) AND source_hash NOT GLOB '*[^0-9a-f]*'),
    projection_hash TEXT NOT NULL CHECK (length(projection_hash)=64 AND projection_hash=lower(projection_hash) AND projection_hash NOT GLOB '*[^0-9a-f]*'),
    publication_state TEXT NOT NULL CHECK (publication_state IN ('PENDING','PUBLISHED','FAILED')),
    last_attempt_utc TEXT NOT NULL CHECK (length(last_attempt_utc)=27 AND substr(last_attempt_utc,27,1)='Z' AND julianday(last_attempt_utc) IS NOT NULL),
    transaction_id TEXT NOT NULL,
    writer_id TEXT NOT NULL CHECK (writer_id='PROJECTION_WRITER'),
    PRIMARY KEY (projection_name,scope_key),
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CHECK ((publication_state='PUBLISHED' AND published_transaction_sequence=source_transaction_sequence) OR (publication_state<>'PUBLISHED' AND published_transaction_sequence<source_transaction_sequence))
) STRICT;

CREATE TABLE store_incidents (
    store_incident_id TEXT NOT NULL PRIMARY KEY CHECK (length(store_incident_id)=36 AND store_incident_id=lower(store_incident_id) AND substr(store_incident_id,9,1)='-' AND substr(store_incident_id,14,1)='-' AND substr(store_incident_id,19,1)='-' AND substr(store_incident_id,24,1)='-' AND replace(store_incident_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(store_incident_id,15,1) IN ('1','2','3','4','5') AND substr(store_incident_id,20,1) IN ('8','9','a','b')),
    incident_type TEXT NOT NULL CHECK (incident_type IN ('WRITE_FAILED','READBACK_FAILED','CORRUPTION','SCHEMA_MISMATCH','WRITER_ROUTING_FAILED','VERSION_CONFLICT','MISSING_PARENT','MIGRATION_FAILED','RECOVERY_REQUIRED')),
    affected_table TEXT NOT NULL,
    affected_identity TEXT NOT NULL,
    last_verified_transaction_sequence INTEGER NOT NULL CHECK (last_verified_transaction_sequence>=0),
    evidence_hash TEXT NOT NULL CHECK (length(evidence_hash)=64 AND evidence_hash=lower(evidence_hash) AND evidence_hash NOT GLOB '*[^0-9a-f]*'),
    disposition TEXT NOT NULL CHECK (disposition IN ('OPEN','QUARANTINED','RECOVERED','FAILED')),
    recovery_authorization_id TEXT NULL,
    transaction_id TEXT NULL,
    created_at_utc TEXT NOT NULL CHECK (length(created_at_utc)=27 AND substr(created_at_utc,27,1)='Z' AND julianday(created_at_utc) IS NOT NULL),
    closed_at_utc TEXT NULL CHECK (closed_at_utc IS NULL OR (length(closed_at_utc)=27 AND substr(closed_at_utc,27,1)='Z' AND julianday(closed_at_utc) IS NOT NULL)),
    writer_id TEXT NOT NULL CHECK (writer_id='STORE_INCIDENT_WRITER'),
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CHECK ((disposition='OPEN' AND closed_at_utc IS NULL) OR (disposition<>'OPEN' AND closed_at_utc IS NOT NULL))
) STRICT;

CREATE UNIQUE INDEX uq_writer_registry_active_scope ON writer_registry(table_name,operation) WHERE active=1;
CREATE UNIQUE INDEX uq_supervisor_generation_current ON supervisor_generations(state) WHERE state='CURRENT';
CREATE UNIQUE INDEX uq_supervisor_lease_held_generation ON supervisor_leases(supervisor_generation_id) WHERE lease_state='HELD';
CREATE UNIQUE INDEX uq_supervisor_lease_held_global ON supervisor_leases(lease_state) WHERE lease_state='HELD';
CREATE UNIQUE INDEX uq_shared_feed_policy_active_valid ON shared_feed_policies(active) WHERE active=1 AND validation_disposition='POLICY_VALID';
CREATE UNIQUE INDEX uq_active_contract_session_current_symbol ON active_contract_sessions(symbol) WHERE valid_to_sequence IS NULL;
CREATE UNIQUE INDEX uq_listener_epoch_current ON listener_epochs(state) WHERE state='CURRENT';
CREATE UNIQUE INDEX uq_recovery_open_listener_epoch ON recovery_transactions(listener_epoch_id) WHERE state IN ('OPEN','ACKNOWLEDGING') AND recovery_type IN ('LISTENER_RESTART','LISTENER_ADOPTION','COLD_START');
CREATE UNIQUE INDEX uq_recovery_open_bridge_generation ON recovery_transactions(bridge_generation_id) WHERE state IN ('OPEN','ACKNOWLEDGING') AND recovery_type='BRIDGE_RECYCLE';
CREATE UNIQUE INDEX uq_domain_ack_positive ON domain_acknowledgements(recovery_transaction_id,authoritative_domain) WHERE acknowledgement_disposition='ACCEPTED';
CREATE UNIQUE INDEX uq_bridge_generation_current_epoch ON bridge_generations(listener_epoch_id) WHERE state='CURRENT';
CREATE UNIQUE INDEX uq_subscription_verified_current ON subscription_verifications(symbol,contract_session_ref_id,bridge_generation_id) WHERE disposition='SUBSCRIPTION_VERIFIED';
CREATE UNIQUE INDEX uq_market_expectation_current ON market_data_expectations(symbol,listener_epoch_id) WHERE current=1;

CREATE TRIGGER trg_writer_registry_update_guard
BEFORE UPDATE ON writer_registry
WHEN NOT (OLD.active=1 AND OLD.retired_transaction_sequence IS NULL AND NEW.active=0 AND NEW.retired_transaction_sequence IS NOT NULL AND NEW.retired_transaction_sequence>=OLD.effective_transaction_sequence AND NEW.registry_version=OLD.registry_version AND NEW.table_name=OLD.table_name AND NEW.operation=OLD.operation AND NEW.writer_id=OLD.writer_id AND NEW.writer_contract_identity=OLD.writer_contract_identity AND NEW.writer_build_hash IS OLD.writer_build_hash AND NEW.effective_transaction_sequence=OLD.effective_transaction_sequence)
BEGIN SELECT RAISE(ABORT,'WRITER_REGISTRY_UPDATE_PROHIBITED'); END;

CREATE TRIGGER trg_writer_registry_delete_guard
BEFORE DELETE ON writer_registry
BEGIN SELECT RAISE(ABORT,'WRITER_REGISTRY_DELETE_PROHIBITED'); END;

CREATE TRIGGER trg_idempotency_records_immutable
BEFORE UPDATE ON idempotency_records
BEGIN SELECT RAISE(ABORT,'IDEMPOTENCY_CONFLICT'); END;

CREATE TRIGGER trg_listener_state_transitions_legal
BEFORE INSERT ON listener_state_transitions
WHEN NOT (
    (NEW.prior_state='NONE' AND NEW.resulting_state IN ('STOPPED','STARTING','SUPERVISOR_STORE_FAILED')) OR
    (NEW.prior_state='STOPPED' AND NEW.resulting_state='STARTING') OR
    (NEW.prior_state='STARTING' AND NEW.resulting_state IN ('REHYDRATING','AMBIGUOUS_PROCESS_AUTHORITY','LISTENER_FAILED','STOPPING','SUPERVISOR_STORE_FAILED')) OR
    (NEW.prior_state='REHYDRATING' AND NEW.resulting_state IN ('HEALTHY','SUSPECT','LISTENER_FAILED','FENCED','STOPPING','SUPERVISOR_STORE_FAILED')) OR
    (NEW.prior_state='HEALTHY' AND NEW.resulting_state IN ('SUSPECT','STOPPING','FENCED','SUPERVISOR_STORE_FAILED')) OR
    (NEW.prior_state='SUSPECT' AND NEW.resulting_state IN ('HEALTHY','FENCED','STOPPING','LISTENER_FAILED','SUPERVISOR_STORE_FAILED')) OR
    (NEW.prior_state='FENCED' AND NEW.resulting_state IN ('REHYDRATING','LISTENER_FAILED','STOPPING','SUPERVISOR_STORE_FAILED')) OR
    (NEW.prior_state='STOPPING' AND NEW.resulting_state IN ('STOPPED','LISTENER_FAILED','SUPERVISOR_STORE_FAILED')) OR
    (NEW.prior_state='LISTENER_FAILED' AND NEW.resulting_state IN ('STARTING','STOPPING','SUPERVISOR_STORE_FAILED')) OR
    (NEW.prior_state='AMBIGUOUS_PROCESS_AUTHORITY' AND NEW.resulting_state IN ('STOPPED','STARTING','SUPERVISOR_STORE_FAILED')) OR
    (NEW.prior_state='SUPERVISOR_STORE_FAILED' AND NEW.resulting_state='STOPPED'))
BEGIN SELECT RAISE(ABORT,'LISTENER_TRANSITION_PROHIBITED'); END;

CREATE TRIGGER trg_listener_current_insert_match
BEFORE INSERT ON listener_current
WHEN NOT EXISTS (SELECT 1 FROM listener_state_transitions t WHERE t.listener_transition_id=NEW.last_transition_id AND t.supervisor_generation_id=NEW.supervisor_generation_id AND t.listener_epoch_id IS NEW.listener_epoch_id AND t.resulting_state=NEW.lifecycle_state AND t.resulting_version=NEW.state_version AND t.transaction_id=NEW.update_transaction_id)
BEGIN SELECT RAISE(ABORT,'LISTENER_CURRENT_TRANSITION_MISMATCH'); END;

CREATE TRIGGER trg_listener_current_update_match
BEFORE UPDATE ON listener_current
WHEN NEW.state_version<>OLD.state_version+1 OR NOT EXISTS (SELECT 1 FROM listener_state_transitions t WHERE t.listener_transition_id=NEW.last_transition_id AND t.supervisor_generation_id=NEW.supervisor_generation_id AND t.listener_epoch_id IS NEW.listener_epoch_id AND t.prior_state=OLD.lifecycle_state AND t.resulting_state=NEW.lifecycle_state AND t.expected_prior_version=OLD.state_version AND t.resulting_version=NEW.state_version AND t.transaction_id=NEW.update_transaction_id)
BEGIN SELECT RAISE(ABORT,'LISTENER_CURRENT_VERSION_OR_TRANSITION_MISMATCH'); END;

CREATE TRIGGER trg_listener_restart_incidents_terminal_match
BEFORE UPDATE ON listener_restart_incidents
WHEN NEW.incident_state='TERMINAL' AND NOT EXISTS (SELECT 1 FROM listener_restart_outcomes o WHERE o.listener_outcome_id=NEW.current_outcome_id AND o.restart_incident_id=NEW.restart_incident_id AND o.transaction_id=NEW.update_transaction_id)
BEGIN SELECT RAISE(ABORT,'LISTENER_TERMINAL_OUTCOME_MISMATCH'); END;

CREATE TRIGGER trg_domain_acknowledgements_required_match
BEFORE INSERT ON domain_acknowledgements
WHEN NOT EXISTS (SELECT 1 FROM recovery_transactions r JOIN recovery_required_domains d ON d.recovery_transaction_id=r.recovery_transaction_id AND d.authoritative_domain=NEW.authoritative_domain WHERE r.recovery_transaction_id=NEW.recovery_transaction_id AND r.supervisor_generation_id=NEW.supervisor_generation_id AND r.listener_epoch_id=NEW.listener_epoch_id AND d.expected_domain_identity=NEW.expected_domain_identity) OR (NEW.acknowledgement_disposition='ACCEPTED' AND NEW.expected_domain_identity<>NEW.observed_domain_identity)
BEGIN SELECT RAISE(ABORT,'ACKNOWLEDGEMENT_IDENTITY_OR_GENERATION_MISMATCH'); END;

CREATE TRIGGER trg_subscription_verifications_proof
BEFORE INSERT ON subscription_verifications
WHEN NEW.disposition='SUBSCRIPTION_VERIFIED' AND NOT EXISTS (SELECT 1 FROM health_events e JOIN producer_registrations p ON p.producer_instance_id=e.producer_instance_id WHERE e.health_event_id=NEW.source_health_event_id AND e.producer_instance_id=NEW.proof_producer_id AND p.producer_role='RITHMIC_LISTENER' AND e.fact_type='SUBSCRIPTION_PROOF' AND e.authentication_disposition='AUTHENTICATED' AND e.supervisor_generation_id=NEW.supervisor_generation_id AND e.listener_epoch_id=NEW.listener_epoch_id AND e.bridge_generation_id=NEW.bridge_generation_id AND e.scope_key=NEW.symbol)
BEGIN SELECT RAISE(ABORT,'SUBSCRIPTION_PROOF_INVALID'); END;

CREATE TRIGGER trg_health_aggregate_exact_state
BEFORE INSERT ON health_aggregate
WHEN (SELECT count(*) FROM health_current)<>5 OR NEW.aggregate_state<>(CASE WHEN EXISTS (SELECT 1 FROM health_current WHERE health_state='HEALTH_STORE_CORRUPT') THEN 'HEALTH_CORRUPT' WHEN EXISTS (SELECT 1 FROM health_current WHERE health_state IN ('HEALTH_PERSISTENCE_DEGRADED','HEALTH_TRANSPORT_DEGRADED','HEALTH_AUTHENTICATION_FAILED','HEALTH_AUTHORITY_DIVERGED','HEALTH_TIME_AUTHORITY_DEGRADED')) THEN 'HEALTH_DEGRADED' WHEN EXISTS (SELECT 1 FROM health_current WHERE health_state='HEALTH_STARTUP_UNPROVEN') THEN 'HEALTH_STARTUP_UNPROVEN' ELSE 'HEALTH_READY' END)
BEGIN SELECT RAISE(ABORT,'HEALTH_AGGREGATE_STATE_MISMATCH'); END;

CREATE TRIGGER trg_health_aggregate_update_state
BEFORE UPDATE ON health_aggregate
WHEN (SELECT count(*) FROM health_current)<>5 OR NEW.aggregate_state<>(CASE WHEN EXISTS (SELECT 1 FROM health_current WHERE health_state='HEALTH_STORE_CORRUPT') THEN 'HEALTH_CORRUPT' WHEN EXISTS (SELECT 1 FROM health_current WHERE health_state IN ('HEALTH_PERSISTENCE_DEGRADED','HEALTH_TRANSPORT_DEGRADED','HEALTH_AUTHENTICATION_FAILED','HEALTH_AUTHORITY_DIVERGED','HEALTH_TIME_AUTHORITY_DEGRADED')) THEN 'HEALTH_DEGRADED' WHEN EXISTS (SELECT 1 FROM health_current WHERE health_state='HEALTH_STARTUP_UNPROVEN') THEN 'HEALTH_STARTUP_UNPROVEN' ELSE 'HEALTH_READY' END)
BEGIN SELECT RAISE(ABORT,'HEALTH_AGGREGATE_STATE_MISMATCH'); END;
-- SCHEMA-HASH-END

-- WRITER-REGISTRY-HASH-BEGIN
INSERT INTO writer_registry(registry_version,table_name,operation,writer_id,writer_contract_identity,writer_build_hash,effective_transaction_sequence,retired_transaction_sequence,active) VALUES
(2,'active_contract_sessions','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'active_contract_sessions','UPDATE','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),
(2,'bridge_current','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'bridge_current','UPDATE','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),
(2,'bridge_generations','INSERT','BRIDGE_GENERATION_WRITER','PHASE3C1-BRIDGE-GENERATION-WRITER-V1',NULL,0,NULL,1),(2,'bridge_generations','UPDATE','BRIDGE_GENERATION_WRITER','PHASE3C1-BRIDGE-GENERATION-WRITER-V1',NULL,0,NULL,1),
(2,'bridge_incidents','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'bridge_incidents','UPDATE','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),
(2,'bridge_outcomes','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'bridge_recycle_attempts','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'bridge_recycle_attempts','UPDATE','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'bridge_transitions','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),
(2,'domain_acknowledgements','INSERT','LISTENER_ACKNOWLEDGEMENT_WRITER','PHASE3C1-LISTENER-ACKNOWLEDGEMENT-WRITER-V1',NULL,0,NULL,1),
(2,'health_aggregate','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'health_aggregate','UPDATE','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'health_current','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'health_current','UPDATE','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'health_events','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'health_transitions','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),
(2,'idempotency_records','INSERT','RUNTIME_AUTHORITY_STORE_TRANSACTION_COORDINATOR','PHASE3C1-RUNTIME-AUTHORITY-STORE-TRANSACTION-COORDINATOR-V1',NULL,0,NULL,1),
(2,'listener_current','INSERT','LISTENER_STATE_WRITER','PHASE3C1-LISTENER-STATE-WRITER-V1',NULL,0,NULL,1),(2,'listener_current','UPDATE','LISTENER_STATE_WRITER','PHASE3C1-LISTENER-STATE-WRITER-V1',NULL,0,NULL,1),
(2,'listener_epochs','INSERT','LISTENER_EPOCH_WRITER','PHASE3C1-LISTENER-EPOCH-WRITER-V1',NULL,0,NULL,1),(2,'listener_epochs','UPDATE','LISTENER_EPOCH_WRITER','PHASE3C1-LISTENER-EPOCH-WRITER-V1',NULL,0,NULL,1),
(2,'listener_execution_attempts','INSERT','LISTENER_INCIDENT_WRITER','PHASE3C1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'listener_execution_attempts','UPDATE','LISTENER_INCIDENT_WRITER','PHASE3C1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'listener_fences','INSERT','LISTENER_INCIDENT_WRITER','PHASE3C1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'listener_rehydrations','INSERT','LISTENER_INCIDENT_WRITER','PHASE3C1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'listener_rehydrations','UPDATE','LISTENER_INCIDENT_WRITER','PHASE3C1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),
(2,'listener_restart_incident_transitions','INSERT','LISTENER_INCIDENT_WRITER','PHASE3C1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'listener_restart_incidents','INSERT','LISTENER_INCIDENT_WRITER','PHASE3C1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'listener_restart_incidents','UPDATE','LISTENER_INCIDENT_WRITER','PHASE3C1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'listener_restart_outcomes','INSERT','LISTENER_INCIDENT_WRITER','PHASE3C1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'listener_state_transitions','INSERT','LISTENER_STATE_WRITER','PHASE3C1-LISTENER-STATE-WRITER-V1',NULL,0,NULL,1),
(2,'market_data_expectations','INSERT','LISTENER_INCIDENT_WRITER','PHASE3C1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'market_data_expectations','UPDATE','LISTENER_INCIDENT_WRITER','PHASE3C1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'producer_registrations','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'producer_registrations','UPDATE','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'projection_cursors','INSERT','PROJECTION_WRITER','PHASE3C1-PROJECTION-WRITER-V1',NULL,0,NULL,1),(2,'projection_cursors','UPDATE','PROJECTION_WRITER','PHASE3C1-PROJECTION-WRITER-V1',NULL,0,NULL,1),
(2,'recovery_required_domains','INSERT','LISTENER_ACKNOWLEDGEMENT_WRITER','PHASE3C1-LISTENER-ACKNOWLEDGEMENT-WRITER-V1',NULL,0,NULL,1),(2,'recovery_transactions','INSERT','RECOVERY_TRANSACTION_WRITER','PHASE3C1-RECOVERY-TRANSACTION-WRITER-V1',NULL,0,NULL,1),(2,'recovery_transactions','UPDATE','RECOVERY_TRANSACTION_WRITER','PHASE3C1-RECOVERY-TRANSACTION-WRITER-V1',NULL,0,NULL,1),(2,'shared_feed_policies','INSERT','LISTENER_INCIDENT_WRITER','PHASE3C1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'shared_feed_policies','UPDATE','LISTENER_INCIDENT_WRITER','PHASE3C1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),
(2,'store_incidents','INSERT','STORE_INCIDENT_WRITER','PHASE3C1-STORE-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'store_incidents','UPDATE','STORE_INCIDENT_WRITER','PHASE3C1-STORE-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'store_metadata','INSERT','RUNTIME_AUTHORITY_STORE_TRANSACTION_COORDINATOR','PHASE3C1-RUNTIME-AUTHORITY-STORE-TRANSACTION-COORDINATOR-V1',NULL,0,NULL,1),(2,'store_metadata','UPDATE','RUNTIME_AUTHORITY_STORE_TRANSACTION_COORDINATOR','PHASE3C1-RUNTIME-AUTHORITY-STORE-TRANSACTION-COORDINATOR-V1',NULL,0,NULL,1),(2,'subscription_verifications','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'supervisor_generations','INSERT','SUPERVISOR_GENERATION_WRITER','PHASE3C1-SUPERVISOR-GENERATION-WRITER-V1',NULL,0,NULL,1),(2,'supervisor_generations','UPDATE','SUPERVISOR_GENERATION_WRITER','PHASE3C1-SUPERVISOR-GENERATION-WRITER-V1',NULL,0,NULL,1),(2,'supervisor_leases','INSERT','SUPERVISOR_GENERATION_WRITER','PHASE3C1-SUPERVISOR-GENERATION-WRITER-V1',NULL,0,NULL,1),(2,'supervisor_leases','UPDATE','SUPERVISOR_GENERATION_WRITER','PHASE3C1-SUPERVISOR-GENERATION-WRITER-V1',NULL,0,NULL,1),(2,'termination_evidence','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'termination_results','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'transaction_commits','INSERT','RUNTIME_AUTHORITY_STORE_TRANSACTION_COORDINATOR','PHASE3C1-RUNTIME-AUTHORITY-STORE-TRANSACTION-COORDINATOR-V1',NULL,0,NULL,1),(2,'writer_registry','INSERT','RUNTIME_AUTHORITY_STORE_TRANSACTION_COORDINATOR','PHASE3C1-RUNTIME-AUTHORITY-STORE-TRANSACTION-COORDINATOR-V1',NULL,0,NULL,1),(2,'writer_registry','UPDATE','RUNTIME_AUTHORITY_STORE_TRANSACTION_COORDINATOR','PHASE3C1-RUNTIME-AUTHORITY-STORE-TRANSACTION-COORDINATOR-V1',NULL,0,NULL,1);
-- WRITER-REGISTRY-HASH-END

COMMIT;
