-- Runtime Authority Store schema v2 -- Phase 3C1-R2 draft implementation reference.
-- DRAFT / NONCANONICAL / NOT APPROVED / NOT AUTHORIZED FOR RUNTIME INSTALLATION.
-- Minimum SQLite: 3.43.1.  All F1 normalization uses built-ins; F6 integrity uses
-- the precisely governed randle_sha256_hex_utf8 function preflighted below.

PRAGMA foreign_keys = ON;
PRAGMA trusted_schema = OFF;
PRAGMA recursive_triggers = ON;
PRAGMA busy_timeout = 5000;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA application_id = 0x52484C54;
PRAGMA user_version = 2;

-- Before this artifact or any connection-level validation runs, register
-- randle_sha256_hex_utf8(TEXT) with SQLITE_UTF8, SQLITE_DETERMINISTIC, and
-- SQLITE_INNOCUOUS. It hashes the exact UTF-8 bytes of its sole non-NULL TEXT
-- argument and returns 64 lowercase hexadecimal SHA-256 characters. This
-- preliminary direct call rejects a missing or incorrect function. The
-- schema-owned view and final SELECT below additionally reject a registration
-- that is not SQLITE_INNOCUOUS while trusted_schema remains OFF.
CREATE TEMP TABLE randle_sha256_preflight(value TEXT NOT NULL CHECK (value='e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')) STRICT;
INSERT INTO randle_sha256_preflight(value) VALUES (randle_sha256_hex_utf8(''));
DROP TABLE randle_sha256_preflight;

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
    created_at_utc TEXT NOT NULL CHECK (length(created_at_utc)=27 AND substr(created_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,5,1)='-' AND substr(created_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,8,1)='-' AND substr(created_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,11,1)='T' AND substr(created_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(created_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(created_at_utc,14,1)=':' AND substr(created_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(created_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(created_at_utc,17,1)=':' AND substr(created_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(created_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(created_at_utc,20,1)='.' AND substr(created_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,27,1)='Z' AND CAST(substr(created_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(created_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(created_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(created_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(created_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(created_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(created_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(created_at_utc,1,19)||'Z')||substr(created_at_utc,20,8)=created_at_utc),
    last_verified_at_utc TEXT NULL CHECK (last_verified_at_utc IS NULL OR (length(last_verified_at_utc)=27 AND substr(last_verified_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(last_verified_at_utc,5,1)='-' AND substr(last_verified_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(last_verified_at_utc,8,1)='-' AND substr(last_verified_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(last_verified_at_utc,11,1)='T' AND substr(last_verified_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(last_verified_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(last_verified_at_utc,14,1)=':' AND substr(last_verified_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(last_verified_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(last_verified_at_utc,17,1)=':' AND substr(last_verified_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(last_verified_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(last_verified_at_utc,20,1)='.' AND substr(last_verified_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(last_verified_at_utc,27,1)='Z' AND CAST(substr(last_verified_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(last_verified_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(last_verified_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(last_verified_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(last_verified_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(last_verified_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(last_verified_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(last_verified_at_utc,1,19)||'Z')||substr(last_verified_at_utc,20,8)=last_verified_at_utc)),
    FOREIGN KEY (last_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE writer_registry (
    registry_version INTEGER NOT NULL CHECK (registry_version=2),
    table_name TEXT NOT NULL CHECK (table_name IN ('store_metadata','writer_registry','transaction_commits','idempotency_records','supervisor_generations','supervisor_leases','shared_feed_policies','active_contract_sessions','listener_epochs','recovery_transactions','listener_current','listener_state_transitions','listener_restart_incidents','listener_restart_incident_transitions','listener_restart_outcomes','listener_fences','listener_execution_attempts','listener_rehydrations','recovery_required_domains','domain_acknowledgements','bridge_generations','bridge_current','bridge_transitions','bridge_incidents','bridge_recycle_attempts','bridge_outcomes','producer_registrations','health_events','health_current','health_transitions','health_aggregate','subscription_verifications','termination_evidence','termination_evidence_sets','termination_evidence_set_producers','termination_results','termination_result_evidence','market_data_expectations','projection_cursors','store_incidents')),
    operation TEXT NOT NULL CHECK (operation IN ('INSERT','UPDATE','DELETE')),
    writer_id TEXT NOT NULL CHECK (writer_id IN ('RUNTIME_AUTHORITY_STORE_TRANSACTION_COORDINATOR','SUPERVISOR_GENERATION_WRITER','LISTENER_EPOCH_WRITER','LISTENER_STATE_WRITER','LISTENER_INCIDENT_WRITER','LISTENER_ACKNOWLEDGEMENT_WRITER','RECOVERY_TRANSACTION_WRITER','BRIDGE_GENERATION_WRITER','HEALTH_DURABLE_WRITER','PROJECTION_WRITER','STORE_INCIDENT_WRITER')),
    writer_contract_identity TEXT NOT NULL CHECK (length(writer_contract_identity)>0 AND writer_contract_identity<>'-' AND instr(writer_contract_identity,char(9))=0 AND instr(writer_contract_identity,char(10))=0 AND instr(writer_contract_identity,char(13))=0),
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
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('TX-SUP-GENERATION-CREATE','TX-SUP-LEASE-ACQUIRE','TX-SUP-LEASE-RENEW','TX-SUP-LEASE-RELEASE','TX-SUP-GENERATION-RETIRE','TX-LSN-EPOCH-GRANT','TX-LSN-EPOCH-FENCE','TX-LSN-EPOCH-RETIRE','TX-LSN-START','TX-LSN-RESTART-PENDING','TX-LSN-CANCEL','TX-LSN-FENCE','TX-LSN-EXECUTION-START','TX-LSN-REHYDRATION-START','TX-LSN-ACK','TX-LSN-COMPLETE','TX-LSN-FAIL','TX-LSN-RATE-EXHAUSTED','TX-LSN-PLANNED-STOP','TX-LSN-STOP-COMPLETE','TX-STORE-WRITER-RETIRE','TX-STORE-WRITER-INSTALL','TX-PRODUCER-REGISTER','TX-PRODUCER-RETIRE','TX-CONTRACT-SESSION-IMPORT','TX-CONTRACT-SESSION-RETIRE','TX-STORE-RECOVERY-COMPLETE','TX-STORE-RESTORE','TX-STORE-REINITIALIZE','TX-STORE-STALE-LEASE-FENCE','TX-STORE-INCIDENT','TX-STORE-BOOTSTRAP-V2','TX-BRG-INITIALIZE','TX-BRG-RECYCLE-PENDING','TX-BRG-CANCEL','TX-BRG-FENCE','TX-BRG-EXECUTE','TX-BRG-REHYDRATE','TX-BRG-READY','TX-BRG-FAIL','TX-BRG-EXHAUSTED','TX-BRG-GRANT','TX-BRG-PLANNED-SHUTDOWN','TX-BRG-EPOCH-TRANSITION','TX-HEALTH-EVENT','TX-HEALTH-DIMENSION-UPDATE','TX-SUBSCRIPTION-VERIFY','TX-TERMINATION-EVIDENCE','TX-TERMINATION-CLASSIFY','TX-EXPECTATION-EVALUATE','TX-POLICY-VALIDATE','TX-PROJECTION-CURSOR')),
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
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,5,1)='-' AND substr(committed_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,8,1)='-' AND substr(committed_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,11,1)='T' AND substr(committed_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(committed_at_utc,14,1)=':' AND substr(committed_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,17,1)=':' AND substr(committed_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,20,1)='.' AND substr(committed_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,27,1)='Z' AND CAST(substr(committed_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(committed_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(committed_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(committed_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(committed_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(committed_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(committed_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(committed_at_utc,1,19)||'Z')||substr(committed_at_utc,20,8)=committed_at_utc),
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
    created_at_utc TEXT NOT NULL CHECK (length(created_at_utc)=27 AND substr(created_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,5,1)='-' AND substr(created_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,8,1)='-' AND substr(created_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,11,1)='T' AND substr(created_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(created_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(created_at_utc,14,1)=':' AND substr(created_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(created_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(created_at_utc,17,1)=':' AND substr(created_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(created_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(created_at_utc,20,1)='.' AND substr(created_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,27,1)='Z' AND CAST(substr(created_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(created_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(created_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(created_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(created_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(created_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(created_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(created_at_utc,1,19)||'Z')||substr(created_at_utc,20,8)=created_at_utc),
    PRIMARY KEY (transaction_type,idempotency_key),
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CHECK ((status='COMMITTED' AND transaction_id IS NOT NULL) OR (status<>'COMMITTED' AND transaction_id IS NULL))
) STRICT;

CREATE TABLE supervisor_generations (
    supervisor_generation_id TEXT NOT NULL PRIMARY KEY CHECK (length(supervisor_generation_id)=36 AND supervisor_generation_id=lower(supervisor_generation_id) AND substr(supervisor_generation_id,9,1)='-' AND substr(supervisor_generation_id,14,1)='-' AND substr(supervisor_generation_id,19,1)='-' AND substr(supervisor_generation_id,24,1)='-' AND replace(supervisor_generation_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(supervisor_generation_id,15,1) IN ('1','2','3','4','5') AND substr(supervisor_generation_id,20,1) IN ('8','9','a','b')),
    generation_sequence INTEGER NOT NULL UNIQUE CHECK (generation_sequence>=1),
    supervisor_instance_id TEXT NOT NULL CHECK (length(supervisor_instance_id)=36 AND supervisor_instance_id=lower(supervisor_instance_id) AND substr(supervisor_instance_id,9,1)='-' AND substr(supervisor_instance_id,14,1)='-' AND substr(supervisor_instance_id,19,1)='-' AND substr(supervisor_instance_id,24,1)='-' AND replace(supervisor_instance_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(supervisor_instance_id,15,1) IN ('1','2','3','4','5') AND substr(supervisor_instance_id,20,1) IN ('8','9','a','b')),
    process_id INTEGER NOT NULL CHECK (process_id>0),
    process_start_utc TEXT NOT NULL CHECK (length(process_start_utc)=27 AND substr(process_start_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(process_start_utc,5,1)='-' AND substr(process_start_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(process_start_utc,8,1)='-' AND substr(process_start_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(process_start_utc,11,1)='T' AND substr(process_start_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(process_start_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(process_start_utc,14,1)=':' AND substr(process_start_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(process_start_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(process_start_utc,17,1)=':' AND substr(process_start_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(process_start_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(process_start_utc,20,1)='.' AND substr(process_start_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(process_start_utc,27,1)='Z' AND CAST(substr(process_start_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(process_start_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(process_start_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(process_start_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(process_start_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(process_start_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(process_start_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(process_start_utc,1,19)||'Z')||substr(process_start_utc,20,8)=process_start_utc),
    build_hash TEXT NOT NULL CHECK (length(build_hash)=64 AND build_hash=lower(build_hash) AND build_hash NOT GLOB '*[^0-9a-f]*'),
    startup_attempt_id TEXT NOT NULL CHECK (length(startup_attempt_id)=36 AND startup_attempt_id=lower(startup_attempt_id) AND substr(startup_attempt_id,9,1)='-' AND substr(startup_attempt_id,14,1)='-' AND substr(startup_attempt_id,19,1)='-' AND substr(startup_attempt_id,24,1)='-' AND replace(startup_attempt_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(startup_attempt_id,15,1) IN ('1','2','3','4','5') AND substr(startup_attempt_id,20,1) IN ('8','9','a','b')),
    grant_transaction_id TEXT NOT NULL,
    started_at_utc TEXT NOT NULL CHECK (length(started_at_utc)=27 AND substr(started_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(started_at_utc,5,1)='-' AND substr(started_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(started_at_utc,8,1)='-' AND substr(started_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(started_at_utc,11,1)='T' AND substr(started_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(started_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(started_at_utc,14,1)=':' AND substr(started_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(started_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(started_at_utc,17,1)=':' AND substr(started_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(started_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(started_at_utc,20,1)='.' AND substr(started_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(started_at_utc,27,1)='Z' AND CAST(substr(started_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(started_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(started_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(started_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(started_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(started_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(started_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(started_at_utc,1,19)||'Z')||substr(started_at_utc,20,8)=started_at_utc),
    fenced_at_utc TEXT NULL CHECK (fenced_at_utc IS NULL OR (length(fenced_at_utc)=27 AND substr(fenced_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(fenced_at_utc,5,1)='-' AND substr(fenced_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(fenced_at_utc,8,1)='-' AND substr(fenced_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(fenced_at_utc,11,1)='T' AND substr(fenced_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(fenced_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(fenced_at_utc,14,1)=':' AND substr(fenced_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(fenced_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(fenced_at_utc,17,1)=':' AND substr(fenced_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(fenced_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(fenced_at_utc,20,1)='.' AND substr(fenced_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(fenced_at_utc,27,1)='Z' AND CAST(substr(fenced_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(fenced_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(fenced_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(fenced_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(fenced_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(fenced_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(fenced_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(fenced_at_utc,1,19)||'Z')||substr(fenced_at_utc,20,8)=fenced_at_utc)),
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
    updated_at_utc TEXT NOT NULL CHECK (length(updated_at_utc)=27 AND substr(updated_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(updated_at_utc,5,1)='-' AND substr(updated_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(updated_at_utc,8,1)='-' AND substr(updated_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(updated_at_utc,11,1)='T' AND substr(updated_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(updated_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(updated_at_utc,14,1)=':' AND substr(updated_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(updated_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(updated_at_utc,17,1)=':' AND substr(updated_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(updated_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(updated_at_utc,20,1)='.' AND substr(updated_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(updated_at_utc,27,1)='Z' AND CAST(substr(updated_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(updated_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(updated_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(updated_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(updated_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(updated_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(updated_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(updated_at_utc,1,19)||'Z')||substr(updated_at_utc,20,8)=updated_at_utc),
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
    approved_at_utc TEXT NOT NULL CHECK (length(approved_at_utc)=27 AND substr(approved_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(approved_at_utc,5,1)='-' AND substr(approved_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(approved_at_utc,8,1)='-' AND substr(approved_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(approved_at_utc,11,1)='T' AND substr(approved_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(approved_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(approved_at_utc,14,1)=':' AND substr(approved_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(approved_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(approved_at_utc,17,1)=':' AND substr(approved_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(approved_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(approved_at_utc,20,1)='.' AND substr(approved_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(approved_at_utc,27,1)='Z' AND CAST(substr(approved_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(approved_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(approved_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(approved_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(approved_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(approved_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(approved_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(approved_at_utc,1,19)||'Z')||substr(approved_at_utc,20,8)=approved_at_utc),
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
    session_date TEXT NOT NULL CHECK (length(session_date)=10 AND substr(session_date,1,4) NOT GLOB '*[^0-9]*' AND substr(session_date,5,1)='-' AND substr(session_date,6,2) NOT GLOB '*[^0-9]*' AND substr(session_date,8,1)='-' AND substr(session_date,9,2) NOT GLOB '*[^0-9]*' AND CAST(substr(session_date,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(session_date,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(session_date,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(session_date,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(session_date,1,4) AS INTEGER)%400=0 OR (CAST(substr(session_date,1,4) AS INTEGER)%4=0 AND CAST(substr(session_date,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%d',session_date||'T00:00:00Z')=session_date),
    session_rollover_commit_id TEXT NOT NULL CHECK (length(session_rollover_commit_id)=36 AND session_rollover_commit_id=lower(session_rollover_commit_id) AND substr(session_rollover_commit_id,9,1)='-' AND substr(session_rollover_commit_id,14,1)='-' AND substr(session_rollover_commit_id,19,1)='-' AND substr(session_rollover_commit_id,24,1)='-' AND replace(session_rollover_commit_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(session_rollover_commit_id,15,1) IN ('1','2','3','4','5') AND substr(session_rollover_commit_id,20,1) IN ('8','9','a','b')),
    source_authority TEXT NOT NULL CHECK (source_authority='ADR014_ENTRY_SESSION_STORE'),
    source_record_hash TEXT NOT NULL CHECK (length(source_record_hash)=64 AND source_record_hash=lower(source_record_hash) AND source_record_hash NOT GLOB '*[^0-9a-f]*'),
    validated_transaction_id TEXT NOT NULL,
    valid_from_sequence INTEGER NOT NULL CHECK (valid_from_sequence>=0),
    valid_to_sequence INTEGER NULL CHECK (valid_to_sequence IS NULL OR valid_to_sequence>valid_from_sequence),
    writer_id TEXT NOT NULL CHECK (writer_id='HEALTH_DURABLE_WRITER'),
    UNIQUE (symbol,contract_id,session_id,session_rollover_commit_id),
    UNIQUE (contract_session_ref_id,symbol,contract_id),
    FOREIGN KEY (validated_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE listener_epochs (
    listener_epoch_id TEXT NOT NULL PRIMARY KEY CHECK (length(listener_epoch_id)=36 AND listener_epoch_id=lower(listener_epoch_id) AND substr(listener_epoch_id,9,1)='-' AND substr(listener_epoch_id,14,1)='-' AND substr(listener_epoch_id,19,1)='-' AND substr(listener_epoch_id,24,1)='-' AND replace(listener_epoch_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(listener_epoch_id,15,1) IN ('1','2','3','4','5') AND substr(listener_epoch_id,20,1) IN ('8','9','a','b')),
    epoch_sequence INTEGER NOT NULL UNIQUE CHECK (epoch_sequence>=1),
    supervisor_generation_id TEXT NOT NULL,
    listener_process_instance_id TEXT NOT NULL CHECK (length(listener_process_instance_id)=36 AND listener_process_instance_id=lower(listener_process_instance_id) AND substr(listener_process_instance_id,9,1)='-' AND substr(listener_process_instance_id,14,1)='-' AND substr(listener_process_instance_id,19,1)='-' AND substr(listener_process_instance_id,24,1)='-' AND replace(listener_process_instance_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(listener_process_instance_id,15,1) IN ('1','2','3','4','5') AND substr(listener_process_instance_id,20,1) IN ('8','9','a','b')),
    process_id INTEGER NOT NULL CHECK (process_id>0),
    process_start_utc TEXT NOT NULL CHECK (length(process_start_utc)=27 AND substr(process_start_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(process_start_utc,5,1)='-' AND substr(process_start_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(process_start_utc,8,1)='-' AND substr(process_start_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(process_start_utc,11,1)='T' AND substr(process_start_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(process_start_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(process_start_utc,14,1)=':' AND substr(process_start_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(process_start_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(process_start_utc,17,1)=':' AND substr(process_start_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(process_start_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(process_start_utc,20,1)='.' AND substr(process_start_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(process_start_utc,27,1)='Z' AND CAST(substr(process_start_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(process_start_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(process_start_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(process_start_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(process_start_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(process_start_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(process_start_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(process_start_utc,1,19)||'Z')||substr(process_start_utc,20,8)=process_start_utc),
    contract_set_hash TEXT NOT NULL CHECK (length(contract_set_hash)=64 AND contract_set_hash=lower(contract_set_hash) AND contract_set_hash NOT GLOB '*[^0-9a-f]*'),
    grant_token_hash TEXT NOT NULL UNIQUE CHECK (length(grant_token_hash)=64 AND grant_token_hash=lower(grant_token_hash) AND grant_token_hash NOT GLOB '*[^0-9a-f]*'),
    grant_transaction_id TEXT NOT NULL,
    granted_at_utc TEXT NOT NULL CHECK (length(granted_at_utc)=27 AND substr(granted_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(granted_at_utc,5,1)='-' AND substr(granted_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(granted_at_utc,8,1)='-' AND substr(granted_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(granted_at_utc,11,1)='T' AND substr(granted_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(granted_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(granted_at_utc,14,1)=':' AND substr(granted_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(granted_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(granted_at_utc,17,1)=':' AND substr(granted_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(granted_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(granted_at_utc,20,1)='.' AND substr(granted_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(granted_at_utc,27,1)='Z' AND CAST(substr(granted_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(granted_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(granted_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(granted_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(granted_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(granted_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(granted_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(granted_at_utc,1,19)||'Z')||substr(granted_at_utc,20,8)=granted_at_utc),
    fenced_at_utc TEXT NULL CHECK (fenced_at_utc IS NULL OR (length(fenced_at_utc)=27 AND substr(fenced_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(fenced_at_utc,5,1)='-' AND substr(fenced_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(fenced_at_utc,8,1)='-' AND substr(fenced_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(fenced_at_utc,11,1)='T' AND substr(fenced_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(fenced_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(fenced_at_utc,14,1)=':' AND substr(fenced_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(fenced_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(fenced_at_utc,17,1)=':' AND substr(fenced_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(fenced_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(fenced_at_utc,20,1)='.' AND substr(fenced_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(fenced_at_utc,27,1)='Z' AND CAST(substr(fenced_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(fenced_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(fenced_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(fenced_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(fenced_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(fenced_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(fenced_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(fenced_at_utc,1,19)||'Z')||substr(fenced_at_utc,20,8)=fenced_at_utc)),
    state TEXT NOT NULL CHECK (state IN ('GRANTED','CURRENT','FENCED','RETIRED')),
    writer_id TEXT NOT NULL CHECK (writer_id='LISTENER_EPOCH_WRITER'),
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (grant_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE recovery_transactions (
    recovery_transaction_id TEXT NOT NULL PRIMARY KEY CHECK (length(recovery_transaction_id)=36 AND recovery_transaction_id=lower(recovery_transaction_id) AND substr(recovery_transaction_id,9,1)='-' AND substr(recovery_transaction_id,14,1)='-' AND substr(recovery_transaction_id,19,1)='-' AND substr(recovery_transaction_id,24,1)='-' AND replace(recovery_transaction_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(recovery_transaction_id,15,1) IN ('1','2','3','4','5') AND substr(recovery_transaction_id,20,1) IN ('8','9','a','b')),
    recovery_type TEXT NOT NULL CHECK (recovery_type IN ('LISTENER_RESTART','LISTENER_ADOPTION','BRIDGE_RECYCLE','COLD_START','STORE_RESTORE','STORE_REINITIALIZE','STORE_BOOTSTRAP')),
    supervisor_generation_id TEXT NULL,
    listener_epoch_id TEXT NULL,
    bridge_generation_id TEXT NULL,
    listener_restart_incident_id TEXT NULL,
    bridge_incident_id TEXT NULL,
    state TEXT NOT NULL CHECK (state IN ('OPEN','ACKNOWLEDGING','COMPLETED','FAILED','CANCELED')),
    required_domain_set_hash TEXT NOT NULL CHECK (length(required_domain_set_hash)=64 AND required_domain_set_hash=lower(required_domain_set_hash) AND required_domain_set_hash NOT GLOB '*[^0-9a-f]*'),
    external_evidence_sequence INTEGER NULL CHECK (external_evidence_sequence IS NULL OR external_evidence_sequence>=1),
    external_evidence_record_hash TEXT NULL CHECK (external_evidence_record_hash IS NULL OR (length(external_evidence_record_hash)=64 AND external_evidence_record_hash=lower(external_evidence_record_hash) AND external_evidence_record_hash NOT GLOB '*[^0-9a-f]*')),
    opened_transaction_id TEXT NOT NULL,
    closed_transaction_id TEXT NULL,
    state_version INTEGER NOT NULL CHECK (state_version>=1),
    opened_at_utc TEXT NOT NULL CHECK (length(opened_at_utc)=27 AND substr(opened_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(opened_at_utc,5,1)='-' AND substr(opened_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(opened_at_utc,8,1)='-' AND substr(opened_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(opened_at_utc,11,1)='T' AND substr(opened_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(opened_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(opened_at_utc,14,1)=':' AND substr(opened_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(opened_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(opened_at_utc,17,1)=':' AND substr(opened_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(opened_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(opened_at_utc,20,1)='.' AND substr(opened_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(opened_at_utc,27,1)='Z' AND CAST(substr(opened_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(opened_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(opened_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(opened_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(opened_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(opened_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(opened_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(opened_at_utc,1,19)||'Z')||substr(opened_at_utc,20,8)=opened_at_utc),
    closed_at_utc TEXT NULL CHECK (closed_at_utc IS NULL OR (length(closed_at_utc)=27 AND substr(closed_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(closed_at_utc,5,1)='-' AND substr(closed_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(closed_at_utc,8,1)='-' AND substr(closed_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(closed_at_utc,11,1)='T' AND substr(closed_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(closed_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(closed_at_utc,14,1)=':' AND substr(closed_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(closed_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(closed_at_utc,17,1)=':' AND substr(closed_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(closed_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(closed_at_utc,20,1)='.' AND substr(closed_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(closed_at_utc,27,1)='Z' AND CAST(substr(closed_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(closed_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(closed_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(closed_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(closed_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(closed_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(closed_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(closed_at_utc,1,19)||'Z')||substr(closed_at_utc,20,8)=closed_at_utc)),
    writer_id TEXT NOT NULL CHECK (writer_id='RECOVERY_TRANSACTION_WRITER'),
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (listener_epoch_id) REFERENCES listener_epochs(listener_epoch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (bridge_generation_id) REFERENCES bridge_generations(bridge_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (listener_restart_incident_id) REFERENCES listener_restart_incidents(restart_incident_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (bridge_incident_id) REFERENCES bridge_incidents(bridge_incident_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (opened_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (closed_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CHECK ((state IN ('OPEN','ACKNOWLEDGING') AND closed_transaction_id IS NULL AND closed_at_utc IS NULL) OR (state IN ('COMPLETED','FAILED','CANCELED') AND closed_transaction_id IS NOT NULL AND closed_at_utc IS NOT NULL)),
    CHECK ((recovery_type IN ('LISTENER_RESTART','LISTENER_ADOPTION') AND supervisor_generation_id IS NOT NULL AND listener_epoch_id IS NOT NULL AND bridge_generation_id IS NULL AND bridge_incident_id IS NULL) OR (recovery_type='BRIDGE_RECYCLE' AND supervisor_generation_id IS NOT NULL AND listener_epoch_id IS NOT NULL AND bridge_generation_id IS NOT NULL AND bridge_incident_id IS NOT NULL AND listener_restart_incident_id IS NULL) OR (recovery_type='COLD_START' AND supervisor_generation_id IS NOT NULL AND listener_epoch_id IS NOT NULL AND bridge_generation_id IS NULL AND listener_restart_incident_id IS NULL AND bridge_incident_id IS NULL) OR (recovery_type IN ('STORE_RESTORE','STORE_REINITIALIZE','STORE_BOOTSTRAP') AND listener_epoch_id IS NULL AND bridge_generation_id IS NULL AND listener_restart_incident_id IS NULL AND bridge_incident_id IS NULL)),
    CHECK ((recovery_type IN ('STORE_RESTORE','STORE_REINITIALIZE','STORE_BOOTSTRAP') AND external_evidence_sequence IS NOT NULL AND external_evidence_record_hash IS NOT NULL) OR (recovery_type NOT IN ('STORE_RESTORE','STORE_REINITIALIZE','STORE_BOOTSTRAP') AND external_evidence_sequence IS NULL AND external_evidence_record_hash IS NULL))
) STRICT;

CREATE TABLE listener_current (
    singleton_id INTEGER NOT NULL PRIMARY KEY CHECK (singleton_id=1),
    supervisor_generation_id TEXT NULL,
    listener_epoch_id TEXT NULL,
    lifecycle_state TEXT NOT NULL CHECK (lifecycle_state IN ('STOPPED','STARTING','REHYDRATING','HEALTHY','SUSPECT','FENCED','STOPPING','LISTENER_FAILED','AMBIGUOUS_PROCESS_AUTHORITY','SUPERVISOR_STORE_FAILED')),
    state_version INTEGER NOT NULL CHECK (state_version>=1),
    last_transition_id TEXT NOT NULL UNIQUE,
    current_restart_incident_id TEXT NULL,
    active_recovery_transaction_id TEXT NULL,
    update_transaction_id TEXT NOT NULL,
    writer_id TEXT NOT NULL CHECK (writer_id='LISTENER_STATE_WRITER'),
    committed_sequence INTEGER NOT NULL CHECK (committed_sequence>=0),
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,5,1)='-' AND substr(committed_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,8,1)='-' AND substr(committed_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,11,1)='T' AND substr(committed_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(committed_at_utc,14,1)=':' AND substr(committed_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,17,1)=':' AND substr(committed_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,20,1)='.' AND substr(committed_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,27,1)='Z' AND CAST(substr(committed_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(committed_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(committed_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(committed_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(committed_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(committed_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(committed_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(committed_at_utc,1,19)||'Z')||substr(committed_at_utc,20,8)=committed_at_utc),
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (listener_epoch_id) REFERENCES listener_epochs(listener_epoch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (last_transition_id) REFERENCES listener_state_transitions(listener_transition_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (current_restart_incident_id) REFERENCES listener_restart_incidents(restart_incident_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (active_recovery_transaction_id) REFERENCES recovery_transactions(recovery_transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (update_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CHECK ((listener_epoch_id IS NULL AND lifecycle_state IN ('STOPPED','STARTING','AMBIGUOUS_PROCESS_AUTHORITY','SUPERVISOR_STORE_FAILED')) OR (listener_epoch_id IS NOT NULL AND lifecycle_state IN ('REHYDRATING','HEALTHY','SUSPECT','FENCED','STOPPING','LISTENER_FAILED'))),
    CHECK (supervisor_generation_id IS NOT NULL OR lifecycle_state IN ('STOPPED','SUPERVISOR_STORE_FAILED'))
) STRICT;

CREATE TABLE listener_state_transitions (
    listener_transition_id TEXT NOT NULL PRIMARY KEY CHECK (length(listener_transition_id)=36 AND listener_transition_id=lower(listener_transition_id) AND substr(listener_transition_id,9,1)='-' AND substr(listener_transition_id,14,1)='-' AND substr(listener_transition_id,19,1)='-' AND substr(listener_transition_id,24,1)='-' AND replace(listener_transition_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(listener_transition_id,15,1) IN ('1','2','3','4','5') AND substr(listener_transition_id,20,1) IN ('8','9','a','b')),
    supervisor_generation_id TEXT NULL,
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
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,5,1)='-' AND substr(committed_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,8,1)='-' AND substr(committed_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,11,1)='T' AND substr(committed_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(committed_at_utc,14,1)=':' AND substr(committed_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,17,1)=':' AND substr(committed_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,20,1)='.' AND substr(committed_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,27,1)='Z' AND CAST(substr(committed_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(committed_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(committed_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(committed_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(committed_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(committed_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(committed_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(committed_at_utc,1,19)||'Z')||substr(committed_at_utc,20,8)=committed_at_utc),
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (listener_epoch_id) REFERENCES listener_epochs(listener_epoch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (restart_incident_id) REFERENCES listener_restart_incidents(restart_incident_id) ON UPDATE RESTRICT ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (recovery_transaction_id) REFERENCES recovery_transactions(recovery_transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    UNIQUE (transaction_id,resulting_version),
    CHECK (supervisor_generation_id IS NOT NULL OR (prior_state='NONE' AND resulting_state IN ('STOPPED','SUPERVISOR_STORE_FAILED')))
) STRICT;

CREATE TABLE listener_restart_incidents (
    restart_incident_id TEXT NOT NULL PRIMARY KEY CHECK (length(restart_incident_id)=36 AND restart_incident_id=lower(restart_incident_id) AND substr(restart_incident_id,9,1)='-' AND substr(restart_incident_id,14,1)='-' AND substr(restart_incident_id,19,1)='-' AND substr(restart_incident_id,24,1)='-' AND replace(restart_incident_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(restart_incident_id,15,1) IN ('1','2','3','4','5') AND substr(restart_incident_id,20,1) IN ('8','9','a','b')),
    supervisor_generation_id TEXT NOT NULL,
    listener_epoch_id TEXT NOT NULL,
    incident_state TEXT NOT NULL CHECK (incident_state IN ('RESTART_PENDING','RESTART_FENCED','RESTART_EXECUTING','RESTART_REHYDRATING','TERMINAL')),
    incident_version INTEGER NOT NULL CHECK (incident_version>=1),
    sff_predicate TEXT NOT NULL CHECK (sff_predicate IN ('SFF-01_LISTENER_EXITED','SFF-02_LISTENER_LEASE_LOST','SFF-03_BRIDGE_RECOVERY_EXHAUSTED')),
    observed_stale_timestamp_utc TEXT NOT NULL CHECK (length(observed_stale_timestamp_utc)=27 AND substr(observed_stale_timestamp_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(observed_stale_timestamp_utc,5,1)='-' AND substr(observed_stale_timestamp_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(observed_stale_timestamp_utc,8,1)='-' AND substr(observed_stale_timestamp_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(observed_stale_timestamp_utc,11,1)='T' AND substr(observed_stale_timestamp_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(observed_stale_timestamp_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(observed_stale_timestamp_utc,14,1)=':' AND substr(observed_stale_timestamp_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(observed_stale_timestamp_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(observed_stale_timestamp_utc,17,1)=':' AND substr(observed_stale_timestamp_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(observed_stale_timestamp_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(observed_stale_timestamp_utc,20,1)='.' AND substr(observed_stale_timestamp_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(observed_stale_timestamp_utc,27,1)='Z' AND CAST(substr(observed_stale_timestamp_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(observed_stale_timestamp_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(observed_stale_timestamp_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(observed_stale_timestamp_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(observed_stale_timestamp_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(observed_stale_timestamp_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(observed_stale_timestamp_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(observed_stale_timestamp_utc,1,19)||'Z')||substr(observed_stale_timestamp_utc,20,8)=observed_stale_timestamp_utc),
    decision_timestamp_utc TEXT NOT NULL CHECK (length(decision_timestamp_utc)=27 AND substr(decision_timestamp_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(decision_timestamp_utc,5,1)='-' AND substr(decision_timestamp_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(decision_timestamp_utc,8,1)='-' AND substr(decision_timestamp_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(decision_timestamp_utc,11,1)='T' AND substr(decision_timestamp_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(decision_timestamp_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(decision_timestamp_utc,14,1)=':' AND substr(decision_timestamp_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(decision_timestamp_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(decision_timestamp_utc,17,1)=':' AND substr(decision_timestamp_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(decision_timestamp_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(decision_timestamp_utc,20,1)='.' AND substr(decision_timestamp_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(decision_timestamp_utc,27,1)='Z' AND CAST(substr(decision_timestamp_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(decision_timestamp_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(decision_timestamp_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(decision_timestamp_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(decision_timestamp_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(decision_timestamp_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(decision_timestamp_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(decision_timestamp_utc,1,19)||'Z')||substr(decision_timestamp_utc,20,8)=decision_timestamp_utc),
    fencing_token_hash TEXT NOT NULL CHECK (length(fencing_token_hash)=64 AND fencing_token_hash=lower(fencing_token_hash) AND fencing_token_hash NOT GLOB '*[^0-9a-f]*'),
    policy_identity TEXT NOT NULL,
    attempt_count INTEGER NOT NULL CHECK (attempt_count>=0),
    rate_window_started_utc TEXT NOT NULL CHECK (length(rate_window_started_utc)=27 AND substr(rate_window_started_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(rate_window_started_utc,5,1)='-' AND substr(rate_window_started_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(rate_window_started_utc,8,1)='-' AND substr(rate_window_started_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(rate_window_started_utc,11,1)='T' AND substr(rate_window_started_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(rate_window_started_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(rate_window_started_utc,14,1)=':' AND substr(rate_window_started_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(rate_window_started_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(rate_window_started_utc,17,1)=':' AND substr(rate_window_started_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(rate_window_started_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(rate_window_started_utc,20,1)='.' AND substr(rate_window_started_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(rate_window_started_utc,27,1)='Z' AND CAST(substr(rate_window_started_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(rate_window_started_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(rate_window_started_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(rate_window_started_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(rate_window_started_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(rate_window_started_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(rate_window_started_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(rate_window_started_utc,1,19)||'Z')||substr(rate_window_started_utc,20,8)=rate_window_started_utc),
    evidence_set_hash TEXT NOT NULL CHECK (length(evidence_set_hash)=64 AND evidence_set_hash=lower(evidence_set_hash) AND evidence_set_hash NOT GLOB '*[^0-9a-f]*'),
    current_outcome_id TEXT NULL,
    recovery_transaction_id TEXT NULL,
    last_transition_id TEXT NULL UNIQUE,
    update_transaction_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL CHECK (length(created_at_utc)=27 AND substr(created_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,5,1)='-' AND substr(created_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,8,1)='-' AND substr(created_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,11,1)='T' AND substr(created_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(created_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(created_at_utc,14,1)=':' AND substr(created_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(created_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(created_at_utc,17,1)=':' AND substr(created_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(created_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(created_at_utc,20,1)='.' AND substr(created_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,27,1)='Z' AND CAST(substr(created_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(created_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(created_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(created_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(created_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(created_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(created_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(created_at_utc,1,19)||'Z')||substr(created_at_utc,20,8)=created_at_utc),
    updated_at_utc TEXT NOT NULL CHECK (length(updated_at_utc)=27 AND substr(updated_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(updated_at_utc,5,1)='-' AND substr(updated_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(updated_at_utc,8,1)='-' AND substr(updated_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(updated_at_utc,11,1)='T' AND substr(updated_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(updated_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(updated_at_utc,14,1)=':' AND substr(updated_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(updated_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(updated_at_utc,17,1)=':' AND substr(updated_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(updated_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(updated_at_utc,20,1)='.' AND substr(updated_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(updated_at_utc,27,1)='Z' AND CAST(substr(updated_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(updated_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(updated_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(updated_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(updated_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(updated_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(updated_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(updated_at_utc,1,19)||'Z')||substr(updated_at_utc,20,8)=updated_at_utc),
    writer_id TEXT NOT NULL CHECK (writer_id='LISTENER_INCIDENT_WRITER'),
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (listener_epoch_id) REFERENCES listener_epochs(listener_epoch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (policy_identity) REFERENCES shared_feed_policies(policy_identity) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (current_outcome_id) REFERENCES listener_restart_outcomes(listener_outcome_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (recovery_transaction_id) REFERENCES recovery_transactions(recovery_transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
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
    recovery_transaction_id TEXT NULL,
    transaction_id TEXT NOT NULL,
    expected_prior_version INTEGER NOT NULL CHECK (expected_prior_version>=1),
    resulting_version INTEGER NOT NULL CHECK (resulting_version=expected_prior_version+1),
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,5,1)='-' AND substr(committed_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,8,1)='-' AND substr(committed_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,11,1)='T' AND substr(committed_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(committed_at_utc,14,1)=':' AND substr(committed_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,17,1)=':' AND substr(committed_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,20,1)='.' AND substr(committed_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,27,1)='Z' AND CAST(substr(committed_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(committed_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(committed_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(committed_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(committed_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(committed_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(committed_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(committed_at_utc,1,19)||'Z')||substr(committed_at_utc,20,8)=committed_at_utc),
    FOREIGN KEY (restart_incident_id) REFERENCES listener_restart_incidents(restart_incident_id) ON UPDATE RESTRICT ON DELETE CASCADE,
    FOREIGN KEY (recovery_transaction_id) REFERENCES recovery_transactions(recovery_transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
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
    recovery_transaction_id TEXT NULL,
    transaction_id TEXT NOT NULL,
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,5,1)='-' AND substr(committed_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,8,1)='-' AND substr(committed_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,11,1)='T' AND substr(committed_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(committed_at_utc,14,1)=':' AND substr(committed_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,17,1)=':' AND substr(committed_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,20,1)='.' AND substr(committed_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,27,1)='Z' AND CAST(substr(committed_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(committed_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(committed_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(committed_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(committed_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(committed_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(committed_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(committed_at_utc,1,19)||'Z')||substr(committed_at_utc,20,8)=committed_at_utc),
    writer_id TEXT NOT NULL CHECK (writer_id='LISTENER_INCIDENT_WRITER'),
    FOREIGN KEY (restart_incident_id) REFERENCES listener_restart_incidents(restart_incident_id) ON UPDATE RESTRICT ON DELETE CASCADE,
    FOREIGN KEY (recovery_transaction_id) REFERENCES recovery_transactions(recovery_transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
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
    fenced_at_utc TEXT NOT NULL CHECK (length(fenced_at_utc)=27 AND substr(fenced_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(fenced_at_utc,5,1)='-' AND substr(fenced_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(fenced_at_utc,8,1)='-' AND substr(fenced_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(fenced_at_utc,11,1)='T' AND substr(fenced_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(fenced_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(fenced_at_utc,14,1)=':' AND substr(fenced_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(fenced_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(fenced_at_utc,17,1)=':' AND substr(fenced_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(fenced_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(fenced_at_utc,20,1)='.' AND substr(fenced_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(fenced_at_utc,27,1)='Z' AND CAST(substr(fenced_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(fenced_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(fenced_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(fenced_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(fenced_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(fenced_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(fenced_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(fenced_at_utc,1,19)||'Z')||substr(fenced_at_utc,20,8)=fenced_at_utc),
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
    started_at_utc TEXT NOT NULL CHECK (length(started_at_utc)=27 AND substr(started_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(started_at_utc,5,1)='-' AND substr(started_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(started_at_utc,8,1)='-' AND substr(started_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(started_at_utc,11,1)='T' AND substr(started_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(started_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(started_at_utc,14,1)=':' AND substr(started_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(started_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(started_at_utc,17,1)=':' AND substr(started_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(started_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(started_at_utc,20,1)='.' AND substr(started_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(started_at_utc,27,1)='Z' AND CAST(substr(started_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(started_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(started_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(started_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(started_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(started_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(started_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(started_at_utc,1,19)||'Z')||substr(started_at_utc,20,8)=started_at_utc),
    completed_at_utc TEXT NULL CHECK (completed_at_utc IS NULL OR (length(completed_at_utc)=27 AND substr(completed_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(completed_at_utc,5,1)='-' AND substr(completed_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(completed_at_utc,8,1)='-' AND substr(completed_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(completed_at_utc,11,1)='T' AND substr(completed_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(completed_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(completed_at_utc,14,1)=':' AND substr(completed_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(completed_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(completed_at_utc,17,1)=':' AND substr(completed_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(completed_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(completed_at_utc,20,1)='.' AND substr(completed_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(completed_at_utc,27,1)='Z' AND CAST(substr(completed_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(completed_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(completed_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(completed_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(completed_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(completed_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(completed_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(completed_at_utc,1,19)||'Z')||substr(completed_at_utc,20,8)=completed_at_utc)),
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
    opened_at_utc TEXT NOT NULL CHECK (length(opened_at_utc)=27 AND substr(opened_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(opened_at_utc,5,1)='-' AND substr(opened_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(opened_at_utc,8,1)='-' AND substr(opened_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(opened_at_utc,11,1)='T' AND substr(opened_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(opened_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(opened_at_utc,14,1)=':' AND substr(opened_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(opened_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(opened_at_utc,17,1)=':' AND substr(opened_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(opened_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(opened_at_utc,20,1)='.' AND substr(opened_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(opened_at_utc,27,1)='Z' AND CAST(substr(opened_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(opened_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(opened_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(opened_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(opened_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(opened_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(opened_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(opened_at_utc,1,19)||'Z')||substr(opened_at_utc,20,8)=opened_at_utc),
    closed_at_utc TEXT NULL CHECK (closed_at_utc IS NULL OR (length(closed_at_utc)=27 AND substr(closed_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(closed_at_utc,5,1)='-' AND substr(closed_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(closed_at_utc,8,1)='-' AND substr(closed_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(closed_at_utc,11,1)='T' AND substr(closed_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(closed_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(closed_at_utc,14,1)=':' AND substr(closed_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(closed_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(closed_at_utc,17,1)=':' AND substr(closed_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(closed_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(closed_at_utc,20,1)='.' AND substr(closed_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(closed_at_utc,27,1)='Z' AND CAST(substr(closed_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(closed_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(closed_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(closed_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(closed_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(closed_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(closed_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(closed_at_utc,1,19)||'Z')||substr(closed_at_utc,20,8)=closed_at_utc)),
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
    created_at_utc TEXT NOT NULL CHECK (length(created_at_utc)=27 AND substr(created_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,5,1)='-' AND substr(created_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,8,1)='-' AND substr(created_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,11,1)='T' AND substr(created_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(created_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(created_at_utc,14,1)=':' AND substr(created_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(created_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(created_at_utc,17,1)=':' AND substr(created_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(created_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(created_at_utc,20,1)='.' AND substr(created_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,27,1)='Z' AND CAST(substr(created_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(created_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(created_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(created_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(created_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(created_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(created_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(created_at_utc,1,19)||'Z')||substr(created_at_utc,20,8)=created_at_utc),
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
    granted_at_utc TEXT NOT NULL CHECK (length(granted_at_utc)=27 AND substr(granted_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(granted_at_utc,5,1)='-' AND substr(granted_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(granted_at_utc,8,1)='-' AND substr(granted_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(granted_at_utc,11,1)='T' AND substr(granted_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(granted_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(granted_at_utc,14,1)=':' AND substr(granted_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(granted_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(granted_at_utc,17,1)=':' AND substr(granted_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(granted_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(granted_at_utc,20,1)='.' AND substr(granted_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(granted_at_utc,27,1)='Z' AND CAST(substr(granted_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(granted_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(granted_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(granted_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(granted_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(granted_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(granted_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(granted_at_utc,1,19)||'Z')||substr(granted_at_utc,20,8)=granted_at_utc),
    fenced_at_utc TEXT NULL CHECK (fenced_at_utc IS NULL OR (length(fenced_at_utc)=27 AND substr(fenced_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(fenced_at_utc,5,1)='-' AND substr(fenced_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(fenced_at_utc,8,1)='-' AND substr(fenced_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(fenced_at_utc,11,1)='T' AND substr(fenced_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(fenced_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(fenced_at_utc,14,1)=':' AND substr(fenced_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(fenced_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(fenced_at_utc,17,1)=':' AND substr(fenced_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(fenced_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(fenced_at_utc,20,1)='.' AND substr(fenced_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(fenced_at_utc,27,1)='Z' AND CAST(substr(fenced_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(fenced_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(fenced_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(fenced_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(fenced_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(fenced_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(fenced_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(fenced_at_utc,1,19)||'Z')||substr(fenced_at_utc,20,8)=fenced_at_utc)),
    writer_id TEXT NOT NULL CHECK (writer_id='BRIDGE_GENERATION_WRITER'),
    UNIQUE (listener_epoch_id,bridge_generation_sequence),
    UNIQUE (bridge_generation_id,listener_epoch_id,supervisor_generation_id),
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
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,5,1)='-' AND substr(committed_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,8,1)='-' AND substr(committed_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,11,1)='T' AND substr(committed_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(committed_at_utc,14,1)=':' AND substr(committed_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,17,1)=':' AND substr(committed_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,20,1)='.' AND substr(committed_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,27,1)='Z' AND CAST(substr(committed_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(committed_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(committed_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(committed_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(committed_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(committed_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(committed_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(committed_at_utc,1,19)||'Z')||substr(committed_at_utc,20,8)=committed_at_utc),
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
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,5,1)='-' AND substr(committed_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,8,1)='-' AND substr(committed_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,11,1)='T' AND substr(committed_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(committed_at_utc,14,1)=':' AND substr(committed_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,17,1)=':' AND substr(committed_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,20,1)='.' AND substr(committed_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,27,1)='Z' AND CAST(substr(committed_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(committed_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(committed_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(committed_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(committed_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(committed_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(committed_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(committed_at_utc,1,19)||'Z')||substr(committed_at_utc,20,8)=committed_at_utc),
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
    deadline_utc TEXT NOT NULL CHECK (length(deadline_utc)=27 AND substr(deadline_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(deadline_utc,5,1)='-' AND substr(deadline_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(deadline_utc,8,1)='-' AND substr(deadline_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(deadline_utc,11,1)='T' AND substr(deadline_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(deadline_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(deadline_utc,14,1)=':' AND substr(deadline_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(deadline_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(deadline_utc,17,1)=':' AND substr(deadline_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(deadline_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(deadline_utc,20,1)='.' AND substr(deadline_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(deadline_utc,27,1)='Z' AND CAST(substr(deadline_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(deadline_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(deadline_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(deadline_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(deadline_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(deadline_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(deadline_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(deadline_utc,1,19)||'Z')||substr(deadline_utc,20,8)=deadline_utc),
    evidence_set_hash TEXT NOT NULL CHECK (length(evidence_set_hash)=64 AND evidence_set_hash=lower(evidence_set_hash) AND evidence_set_hash NOT GLOB '*[^0-9a-f]*'),
    current_outcome_id TEXT NULL,
    last_transition_id TEXT NULL UNIQUE,
    update_transaction_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL CHECK (length(created_at_utc)=27 AND substr(created_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,5,1)='-' AND substr(created_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,8,1)='-' AND substr(created_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,11,1)='T' AND substr(created_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(created_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(created_at_utc,14,1)=':' AND substr(created_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(created_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(created_at_utc,17,1)=':' AND substr(created_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(created_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(created_at_utc,20,1)='.' AND substr(created_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,27,1)='Z' AND CAST(substr(created_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(created_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(created_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(created_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(created_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(created_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(created_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(created_at_utc,1,19)||'Z')||substr(created_at_utc,20,8)=created_at_utc),
    updated_at_utc TEXT NOT NULL CHECK (length(updated_at_utc)=27 AND substr(updated_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(updated_at_utc,5,1)='-' AND substr(updated_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(updated_at_utc,8,1)='-' AND substr(updated_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(updated_at_utc,11,1)='T' AND substr(updated_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(updated_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(updated_at_utc,14,1)=':' AND substr(updated_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(updated_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(updated_at_utc,17,1)=':' AND substr(updated_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(updated_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(updated_at_utc,20,1)='.' AND substr(updated_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(updated_at_utc,27,1)='Z' AND CAST(substr(updated_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(updated_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(updated_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(updated_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(updated_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(updated_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(updated_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(updated_at_utc,1,19)||'Z')||substr(updated_at_utc,20,8)=updated_at_utc),
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
    started_at_utc TEXT NOT NULL CHECK (length(started_at_utc)=27 AND substr(started_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(started_at_utc,5,1)='-' AND substr(started_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(started_at_utc,8,1)='-' AND substr(started_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(started_at_utc,11,1)='T' AND substr(started_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(started_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(started_at_utc,14,1)=':' AND substr(started_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(started_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(started_at_utc,17,1)=':' AND substr(started_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(started_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(started_at_utc,20,1)='.' AND substr(started_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(started_at_utc,27,1)='Z' AND CAST(substr(started_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(started_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(started_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(started_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(started_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(started_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(started_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(started_at_utc,1,19)||'Z')||substr(started_at_utc,20,8)=started_at_utc),
    completed_at_utc TEXT NULL CHECK (completed_at_utc IS NULL OR (length(completed_at_utc)=27 AND substr(completed_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(completed_at_utc,5,1)='-' AND substr(completed_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(completed_at_utc,8,1)='-' AND substr(completed_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(completed_at_utc,11,1)='T' AND substr(completed_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(completed_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(completed_at_utc,14,1)=':' AND substr(completed_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(completed_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(completed_at_utc,17,1)=':' AND substr(completed_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(completed_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(completed_at_utc,20,1)='.' AND substr(completed_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(completed_at_utc,27,1)='Z' AND CAST(substr(completed_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(completed_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(completed_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(completed_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(completed_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(completed_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(completed_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(completed_at_utc,1,19)||'Z')||substr(completed_at_utc,20,8)=completed_at_utc)),
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
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,5,1)='-' AND substr(committed_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,8,1)='-' AND substr(committed_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,11,1)='T' AND substr(committed_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(committed_at_utc,14,1)=':' AND substr(committed_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,17,1)=':' AND substr(committed_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,20,1)='.' AND substr(committed_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,27,1)='Z' AND CAST(substr(committed_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(committed_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(committed_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(committed_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(committed_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(committed_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(committed_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(committed_at_utc,1,19)||'Z')||substr(committed_at_utc,20,8)=committed_at_utc),
    writer_id TEXT NOT NULL CHECK (writer_id='HEALTH_DURABLE_WRITER'),
    FOREIGN KEY (bridge_incident_id) REFERENCES bridge_incidents(bridge_incident_id) ON UPDATE RESTRICT ON DELETE CASCADE,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CHECK (outcome=resulting_bridge_state),
    CHECK ((outcome='FAILED_RECOVERY_EXHAUSTED' AND automatic_retry_prohibited=1 AND rate_or_deadline_evidence_hash IS NOT NULL) OR (outcome<>'FAILED_RECOVERY_EXHAUSTED' AND rate_or_deadline_evidence_hash IS NULL))
) STRICT;

CREATE TABLE producer_registrations (
    producer_instance_id TEXT NOT NULL PRIMARY KEY CHECK (length(producer_instance_id)=36 AND producer_instance_id=lower(producer_instance_id) AND substr(producer_instance_id,9,1)='-' AND substr(producer_instance_id,14,1)='-' AND substr(producer_instance_id,19,1)='-' AND substr(producer_instance_id,24,1)='-' AND replace(producer_instance_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(producer_instance_id,15,1) IN ('1','2','3','4','5') AND substr(producer_instance_id,20,1) IN ('8','9','a','b')),
    producer_role TEXT NOT NULL CHECK (producer_role IN ('RITHMIC_LISTENER','BRIDGE_CONTROLLER','EXECUTOR','TRADE_MANAGER','ENTRY_AGENT','OS_ADAPTER','RAPI_ADAPTER','CLOCK_ADAPTER','SUPERVISOR_ADAPTER','OPERATOR_ADAPTER')),
    process_id INTEGER NOT NULL CHECK (process_id>0),
    process_start_utc TEXT NOT NULL CHECK (length(process_start_utc)=27 AND substr(process_start_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(process_start_utc,5,1)='-' AND substr(process_start_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(process_start_utc,8,1)='-' AND substr(process_start_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(process_start_utc,11,1)='T' AND substr(process_start_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(process_start_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(process_start_utc,14,1)=':' AND substr(process_start_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(process_start_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(process_start_utc,17,1)=':' AND substr(process_start_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(process_start_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(process_start_utc,20,1)='.' AND substr(process_start_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(process_start_utc,27,1)='Z' AND CAST(substr(process_start_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(process_start_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(process_start_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(process_start_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(process_start_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(process_start_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(process_start_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(process_start_utc,1,19)||'Z')||substr(process_start_utc,20,8)=process_start_utc),
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
    observed_at_utc TEXT NOT NULL CHECK (length(observed_at_utc)=27 AND substr(observed_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(observed_at_utc,5,1)='-' AND substr(observed_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(observed_at_utc,8,1)='-' AND substr(observed_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(observed_at_utc,11,1)='T' AND substr(observed_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(observed_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(observed_at_utc,14,1)=':' AND substr(observed_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(observed_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(observed_at_utc,17,1)=':' AND substr(observed_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(observed_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(observed_at_utc,20,1)='.' AND substr(observed_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(observed_at_utc,27,1)='Z' AND CAST(substr(observed_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(observed_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(observed_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(observed_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(observed_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(observed_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(observed_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(observed_at_utc,1,19)||'Z')||substr(observed_at_utc,20,8)=observed_at_utc),
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
    supervisor_generation_id TEXT NULL,
    listener_epoch_id TEXT NULL,
    bridge_generation_id TEXT NULL,
    last_transition_id TEXT NULL UNIQUE,
    source_event_id TEXT NULL,
    update_transaction_id TEXT NOT NULL,
    committed_sequence INTEGER NOT NULL CHECK (committed_sequence>=0),
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,5,1)='-' AND substr(committed_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,8,1)='-' AND substr(committed_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,11,1)='T' AND substr(committed_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(committed_at_utc,14,1)=':' AND substr(committed_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,17,1)=':' AND substr(committed_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,20,1)='.' AND substr(committed_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,27,1)='Z' AND CAST(substr(committed_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(committed_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(committed_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(committed_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(committed_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(committed_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(committed_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(committed_at_utc,1,19)||'Z')||substr(committed_at_utc,20,8)=committed_at_utc),
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
    CHECK ((health_state IN ('HEALTH_STARTUP_UNPROVEN','HEALTH_PERSISTENCE_DEGRADED','HEALTH_STORE_CORRUPT') AND listener_epoch_id IS NULL AND bridge_generation_id IS NULL AND last_transition_id IS NULL AND source_event_id IS NULL) OR (health_state NOT IN ('HEALTH_STARTUP_UNPROVEN','HEALTH_PERSISTENCE_DEGRADED','HEALTH_STORE_CORRUPT') AND supervisor_generation_id IS NOT NULL AND listener_epoch_id IS NOT NULL AND last_transition_id IS NOT NULL AND source_event_id IS NOT NULL)),
    CHECK (supervisor_generation_id IS NOT NULL OR health_state IN ('HEALTH_STARTUP_UNPROVEN','HEALTH_STORE_CORRUPT'))
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
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,5,1)='-' AND substr(committed_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,8,1)='-' AND substr(committed_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,11,1)='T' AND substr(committed_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(committed_at_utc,14,1)=':' AND substr(committed_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,17,1)=':' AND substr(committed_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,20,1)='.' AND substr(committed_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,27,1)='Z' AND CAST(substr(committed_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(committed_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(committed_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(committed_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(committed_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(committed_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(committed_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(committed_at_utc,1,19)||'Z')||substr(committed_at_utc,20,8)=committed_at_utc),
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
    committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=27 AND substr(committed_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,5,1)='-' AND substr(committed_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,8,1)='-' AND substr(committed_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,11,1)='T' AND substr(committed_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(committed_at_utc,14,1)=':' AND substr(committed_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,17,1)=':' AND substr(committed_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(committed_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(committed_at_utc,20,1)='.' AND substr(committed_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(committed_at_utc,27,1)='Z' AND CAST(substr(committed_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(committed_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(committed_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(committed_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(committed_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(committed_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(committed_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(committed_at_utc,1,19)||'Z')||substr(committed_at_utc,20,8)=committed_at_utc),
    writer_id TEXT NOT NULL CHECK (writer_id='HEALTH_DURABLE_WRITER'),
    FOREIGN KEY (update_transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE subscription_verifications (
    subscription_verification_id TEXT NOT NULL PRIMARY KEY CHECK (length(subscription_verification_id)=36 AND subscription_verification_id=lower(subscription_verification_id) AND substr(subscription_verification_id,9,1)='-' AND substr(subscription_verification_id,14,1)='-' AND substr(subscription_verification_id,19,1)='-' AND substr(subscription_verification_id,24,1)='-' AND replace(subscription_verification_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(subscription_verification_id,15,1) IN ('1','2','3','4','5') AND substr(subscription_verification_id,20,1) IN ('8','9','a','b')),
    symbol TEXT NOT NULL CHECK (symbol IN ('NQ','YM')),
    contract_id TEXT NOT NULL CHECK (length(contract_id)>0 AND instr(contract_id,char(9))=0 AND instr(contract_id,char(10))=0 AND instr(contract_id,char(13))=0),
    contract_session_ref_id TEXT NOT NULL,
    supervisor_generation_id TEXT NOT NULL,
    listener_epoch_id TEXT NOT NULL,
    bridge_generation_id TEXT NOT NULL,
    source_health_event_id TEXT NOT NULL,
    proof_producer_id TEXT NOT NULL,
    source_producer_sequence INTEGER NOT NULL CHECK (source_producer_sequence>=1),
    request_identity TEXT NOT NULL CHECK (length(request_identity)=36 AND request_identity=lower(request_identity) AND substr(request_identity,9,1)='-' AND substr(request_identity,14,1)='-' AND substr(request_identity,19,1)='-' AND substr(request_identity,24,1)='-' AND replace(request_identity,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(request_identity,15,1) IN ('1','2','3','4','5') AND substr(request_identity,20,1) IN ('8','9','a','b')),
    provider_acknowledgement_identity TEXT NOT NULL CHECK (length(provider_acknowledgement_identity)=36 AND provider_acknowledgement_identity=lower(provider_acknowledgement_identity) AND substr(provider_acknowledgement_identity,9,1)='-' AND substr(provider_acknowledgement_identity,14,1)='-' AND substr(provider_acknowledgement_identity,19,1)='-' AND substr(provider_acknowledgement_identity,24,1)='-' AND replace(provider_acknowledgement_identity,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(provider_acknowledgement_identity,15,1) IN ('1','2','3','4','5') AND substr(provider_acknowledgement_identity,20,1) IN ('8','9','a','b')),
    evaluator_decision_identity TEXT NOT NULL CHECK (length(evaluator_decision_identity)=36 AND evaluator_decision_identity=lower(evaluator_decision_identity) AND substr(evaluator_decision_identity,9,1)='-' AND substr(evaluator_decision_identity,14,1)='-' AND substr(evaluator_decision_identity,19,1)='-' AND substr(evaluator_decision_identity,24,1)='-' AND replace(evaluator_decision_identity,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(evaluator_decision_identity,15,1) IN ('1','2','3','4','5') AND substr(evaluator_decision_identity,20,1) IN ('8','9','a','b')),
    evaluator_version INTEGER NOT NULL CHECK (evaluator_version>=1),
    freshness_observation_identity TEXT NOT NULL CHECK (length(freshness_observation_identity)=36 AND freshness_observation_identity=lower(freshness_observation_identity) AND substr(freshness_observation_identity,9,1)='-' AND substr(freshness_observation_identity,14,1)='-' AND substr(freshness_observation_identity,19,1)='-' AND substr(freshness_observation_identity,24,1)='-' AND replace(freshness_observation_identity,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(freshness_observation_identity,15,1) IN ('1','2','3','4','5') AND substr(freshness_observation_identity,20,1) IN ('8','9','a','b')),
    proof_evidence_identity TEXT NOT NULL CHECK (length(proof_evidence_identity)=36 AND proof_evidence_identity=lower(proof_evidence_identity) AND substr(proof_evidence_identity,9,1)='-' AND substr(proof_evidence_identity,14,1)='-' AND substr(proof_evidence_identity,19,1)='-' AND substr(proof_evidence_identity,24,1)='-' AND replace(proof_evidence_identity,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(proof_evidence_identity,15,1) IN ('1','2','3','4','5') AND substr(proof_evidence_identity,20,1) IN ('8','9','a','b')),
    validator TEXT NOT NULL CHECK (validator='HEALTH_INGRESS'),
    evaluator TEXT NOT NULL CHECK (evaluator='LISTENER_SUPERVISOR_STATE_EVALUATOR'),
    disposition TEXT NOT NULL CHECK (disposition IN ('SUBSCRIPTION_VERIFIED','REJECTED')),
    evidence_hash TEXT NOT NULL CHECK (length(evidence_hash)=64 AND evidence_hash=lower(evidence_hash) AND evidence_hash NOT GLOB '*[^0-9a-f]*'),
    integrity_hash TEXT NOT NULL CHECK (length(integrity_hash)=64 AND integrity_hash=lower(integrity_hash) AND integrity_hash NOT GLOB '*[^0-9a-f]*'),
    transaction_id TEXT NOT NULL,
    verified_at_utc TEXT NOT NULL CHECK (length(verified_at_utc)=27 AND substr(verified_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(verified_at_utc,5,1)='-' AND substr(verified_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(verified_at_utc,8,1)='-' AND substr(verified_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(verified_at_utc,11,1)='T' AND substr(verified_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(verified_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(verified_at_utc,14,1)=':' AND substr(verified_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(verified_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(verified_at_utc,17,1)=':' AND substr(verified_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(verified_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(verified_at_utc,20,1)='.' AND substr(verified_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(verified_at_utc,27,1)='Z' AND CAST(substr(verified_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(verified_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(verified_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(verified_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(verified_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(verified_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(verified_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(verified_at_utc,1,19)||'Z')||substr(verified_at_utc,20,8)=verified_at_utc),
    writer_id TEXT NOT NULL CHECK (writer_id='HEALTH_DURABLE_WRITER'),
    FOREIGN KEY (contract_session_ref_id,symbol,contract_id) REFERENCES active_contract_sessions(contract_session_ref_id,symbol,contract_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (supervisor_generation_id) REFERENCES supervisor_generations(supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (listener_epoch_id) REFERENCES listener_epochs(listener_epoch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (bridge_generation_id,listener_epoch_id,supervisor_generation_id) REFERENCES bridge_generations(bridge_generation_id,listener_epoch_id,supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (source_health_event_id) REFERENCES health_events(health_event_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (proof_producer_id) REFERENCES producer_registrations(producer_instance_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE termination_evidence (
    termination_evidence_id TEXT NOT NULL PRIMARY KEY CHECK (length(termination_evidence_id)=36 AND termination_evidence_id=lower(termination_evidence_id) AND substr(termination_evidence_id,9,1)='-' AND substr(termination_evidence_id,14,1)='-' AND substr(termination_evidence_id,19,1)='-' AND substr(termination_evidence_id,24,1)='-' AND replace(termination_evidence_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(termination_evidence_id,15,1) IN ('1','2','3','4','5') AND substr(termination_evidence_id,20,1) IN ('8','9','a','b')),
    producer_instance_id TEXT NOT NULL,
    producer_sequence INTEGER NOT NULL CHECK (producer_sequence>=1),
    ingress_sequence INTEGER NOT NULL CHECK (ingress_sequence>=1),
    supervisor_generation_id TEXT NOT NULL,
    listener_epoch_id TEXT NOT NULL,
    bridge_generation_id TEXT NOT NULL,
    observed_process_identity TEXT NOT NULL CHECK (length(observed_process_identity)=36 AND observed_process_identity=lower(observed_process_identity) AND substr(observed_process_identity,9,1)='-' AND substr(observed_process_identity,14,1)='-' AND substr(observed_process_identity,19,1)='-' AND substr(observed_process_identity,24,1)='-' AND replace(observed_process_identity,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(observed_process_identity,15,1) IN ('1','2','3','4','5') AND substr(observed_process_identity,20,1) IN ('8','9','a','b')),
    termination_observation_identity TEXT NOT NULL CHECK (length(termination_observation_identity)=36 AND termination_observation_identity=lower(termination_observation_identity) AND substr(termination_observation_identity,9,1)='-' AND substr(termination_observation_identity,14,1)='-' AND substr(termination_observation_identity,19,1)='-' AND substr(termination_observation_identity,24,1)='-' AND replace(termination_observation_identity,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(termination_observation_identity,15,1) IN ('1','2','3','4','5') AND substr(termination_observation_identity,20,1) IN ('8','9','a','b')),
    evidence_role TEXT NOT NULL CHECK (evidence_role IN ('INITIATOR_EVIDENCE','REQUESTED_ACTION_EVIDENCE','EXECUTION_METHOD_EVIDENCE','OBSERVED_CAUSE_EVIDENCE','RESULT_EVIDENCE')),
    assertion_kind TEXT NOT NULL CHECK (assertion_kind IN ('POSITIVE','ABSENCE','UNCERTAINTY')),
    asserted_value TEXT NOT NULL CHECK (
        (evidence_role='INITIATOR_EVIDENCE' AND asserted_value IN ('NONE','LISTENER','LISTENER_SUPERVISOR','AUTHENTICATED_OPERATOR','RAPI_PROVIDER','UNKNOWN')) OR
        (evidence_role='REQUESTED_ACTION_EVIDENCE' AND asserted_value IN ('NONE','BRIDGE_RECYCLE','BRIDGE_SHUTDOWN','LISTENER_SHUTDOWN','FULL_LISTENER_RESTART','UNKNOWN')) OR
        (evidence_role='EXECUTION_METHOD_EVIDENCE' AND asserted_value IN ('NONE','GRACEFUL_RAPI_LOGOUT','GRACEFUL_PROCESS_EXIT','SUPERVISOR_TERMINATE','SUPERVISOR_KILL','PROCESS_SELF_EXIT','PROVIDER_FORCED_LOGOUT','PROVIDER_SHUTDOWN_SIGNAL','UNKNOWN')) OR
        (evidence_role='OBSERVED_CAUSE_EVIDENCE' AND asserted_value IN ('NONE','PLANNED_SHUTDOWN','BRIDGE_CRASH','AUTHENTICATION_FAILURE','CONNECTION_LOSS','SUBSCRIPTION_FAILURE','LISTENER_EXIT','RAPI_ENGINE_INERT','UNKNOWN')) OR
        (evidence_role='RESULT_EVIDENCE' AND asserted_value IN ('NONE','COMPLETED_EXPECTED','RECOVERED','FAILED','TIMED_OUT','CANCELED','PROCESS_EXITED','ENGINE_INERT','UNKNOWN'))),
    absence_scope TEXT NULL CHECK (absence_scope IS NULL OR absence_scope IN ('NO_INITIATOR_THROUGH_CUTOFF','NO_REQUEST_THROUGH_CUTOFF','NO_EXECUTION_THROUGH_CUTOFF','NO_CAUSE_THROUGH_CUTOFF','NO_RESULT_THROUGH_CUTOFF')),
    uncertainty_reason TEXT NULL CHECK (uncertainty_reason IS NULL OR uncertainty_reason IN ('CONFLICT','INDETERMINATE')),
    request_identity TEXT NULL CHECK (request_identity IS NULL OR (length(request_identity)=36 AND request_identity=lower(request_identity) AND substr(request_identity,9,1)='-' AND substr(request_identity,14,1)='-' AND substr(request_identity,19,1)='-' AND substr(request_identity,24,1)='-' AND replace(request_identity,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(request_identity,15,1) IN ('1','2','3','4','5') AND substr(request_identity,20,1) IN ('8','9','a','b'))),
    operator_command_identity TEXT NULL CHECK (operator_command_identity IS NULL OR (length(operator_command_identity)=36 AND operator_command_identity=lower(operator_command_identity) AND substr(operator_command_identity,9,1)='-' AND substr(operator_command_identity,14,1)='-' AND substr(operator_command_identity,19,1)='-' AND substr(operator_command_identity,24,1)='-' AND replace(operator_command_identity,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(operator_command_identity,15,1) IN ('1','2','3','4','5') AND substr(operator_command_identity,20,1) IN ('8','9','a','b'))),
    evidence_type TEXT NOT NULL CHECK (evidence_type IN ('RAPI_CALLBACK','PROCESS_EXIT','PROCESS_EXCEPTION','SUPERVISOR_COMMAND','OPERATOR_COMMAND','OS_HANDLE','LISTENER_SHUTDOWN','STARTUP_TRANSITION')),
    canonical_evidence_json TEXT NOT NULL CHECK (json_valid(canonical_evidence_json)=1 AND json_type(canonical_evidence_json)='object'),
    evidence_sha256 TEXT NOT NULL CHECK (length(evidence_sha256)=64 AND evidence_sha256=lower(evidence_sha256) AND evidence_sha256 NOT GLOB '*[^0-9a-f]*'),
    termination_schema_version INTEGER NOT NULL CHECK (termination_schema_version=2),
    authentication_disposition TEXT NOT NULL CHECK (authentication_disposition IN ('AUTHENTICATED','REJECTED')),
    observed_at_utc TEXT NOT NULL CHECK (length(observed_at_utc)=27 AND substr(observed_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(observed_at_utc,5,1)='-' AND substr(observed_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(observed_at_utc,8,1)='-' AND substr(observed_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(observed_at_utc,11,1)='T' AND substr(observed_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(observed_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(observed_at_utc,14,1)=':' AND substr(observed_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(observed_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(observed_at_utc,17,1)=':' AND substr(observed_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(observed_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(observed_at_utc,20,1)='.' AND substr(observed_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(observed_at_utc,27,1)='Z' AND CAST(substr(observed_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(observed_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(observed_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(observed_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(observed_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(observed_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(observed_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(observed_at_utc,1,19)||'Z')||substr(observed_at_utc,20,8)=observed_at_utc),
    observed_monotonic_ns INTEGER NOT NULL CHECK (observed_monotonic_ns>=0),
    transaction_id TEXT NOT NULL,
    writer_id TEXT NOT NULL CHECK (writer_id='HEALTH_DURABLE_WRITER'),
    FOREIGN KEY (bridge_generation_id,listener_epoch_id,supervisor_generation_id) REFERENCES bridge_generations(bridge_generation_id,listener_epoch_id,supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (producer_instance_id) REFERENCES producer_registrations(producer_instance_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    UNIQUE (producer_instance_id,producer_sequence),
    UNIQUE (producer_instance_id,ingress_sequence),
    UNIQUE (termination_evidence_id,producer_instance_id,producer_sequence,evidence_type,observed_at_utc,termination_schema_version,evidence_sha256,supervisor_generation_id,listener_epoch_id,bridge_generation_id,observed_process_identity,termination_observation_identity,authentication_disposition,evidence_role,assertion_kind,asserted_value),
    CHECK (ingress_sequence=producer_sequence),
    CHECK ((asserted_value='NONE' AND assertion_kind='ABSENCE' AND uncertainty_reason IS NULL AND absence_scope=CASE evidence_role WHEN 'INITIATOR_EVIDENCE' THEN 'NO_INITIATOR_THROUGH_CUTOFF' WHEN 'REQUESTED_ACTION_EVIDENCE' THEN 'NO_REQUEST_THROUGH_CUTOFF' WHEN 'EXECUTION_METHOD_EVIDENCE' THEN 'NO_EXECUTION_THROUGH_CUTOFF' WHEN 'OBSERVED_CAUSE_EVIDENCE' THEN 'NO_CAUSE_THROUGH_CUTOFF' ELSE 'NO_RESULT_THROUGH_CUTOFF' END AND evidence_type='STARTUP_TRANSITION') OR (asserted_value='UNKNOWN' AND assertion_kind='UNCERTAINTY' AND absence_scope IS NULL AND uncertainty_reason IS NOT NULL) OR (asserted_value NOT IN ('NONE','UNKNOWN') AND assertion_kind='POSITIVE' AND absence_scope IS NULL AND uncertainty_reason IS NULL)),
    CHECK ((asserted_value='AUTHENTICATED_OPERATOR' AND evidence_type='OPERATOR_COMMAND' AND operator_command_identity IS NOT NULL) OR asserted_value<>'AUTHENTICATED_OPERATOR'),
    CHECK ((asserted_value='RAPI_PROVIDER' AND evidence_type='RAPI_CALLBACK') OR asserted_value<>'RAPI_PROVIDER'),
    CHECK ((asserted_value='LISTENER' AND evidence_type='LISTENER_SHUTDOWN') OR asserted_value<>'LISTENER'),
    CHECK ((asserted_value='LISTENER_SUPERVISOR' AND evidence_type='SUPERVISOR_COMMAND') OR asserted_value<>'LISTENER_SUPERVISOR'),
    CHECK ((evidence_role='REQUESTED_ACTION_EVIDENCE' AND asserted_value NOT IN ('NONE','UNKNOWN') AND request_identity IS NOT NULL AND evidence_type IN ('SUPERVISOR_COMMAND','OPERATOR_COMMAND','LISTENER_SHUTDOWN')) OR evidence_role<>'REQUESTED_ACTION_EVIDENCE' OR asserted_value IN ('NONE','UNKNOWN')),
    CHECK ((asserted_value='GRACEFUL_RAPI_LOGOUT' AND evidence_type IN ('RAPI_CALLBACK','SUPERVISOR_COMMAND')) OR asserted_value<>'GRACEFUL_RAPI_LOGOUT'),
    CHECK ((asserted_value='GRACEFUL_PROCESS_EXIT' AND evidence_type IN ('PROCESS_EXIT','OS_HANDLE')) OR asserted_value<>'GRACEFUL_PROCESS_EXIT'),
    CHECK ((asserted_value IN ('SUPERVISOR_TERMINATE','SUPERVISOR_KILL') AND evidence_type IN ('SUPERVISOR_COMMAND','OS_HANDLE')) OR asserted_value NOT IN ('SUPERVISOR_TERMINATE','SUPERVISOR_KILL')),
    CHECK ((asserted_value='PROCESS_SELF_EXIT' AND evidence_type IN ('PROCESS_EXIT','OS_HANDLE')) OR asserted_value<>'PROCESS_SELF_EXIT'),
    CHECK ((asserted_value IN ('PROVIDER_FORCED_LOGOUT','PROVIDER_SHUTDOWN_SIGNAL') AND evidence_type='RAPI_CALLBACK') OR asserted_value NOT IN ('PROVIDER_FORCED_LOGOUT','PROVIDER_SHUTDOWN_SIGNAL')),
    CHECK ((asserted_value='BRIDGE_CRASH' AND evidence_type IN ('PROCESS_EXCEPTION','OS_HANDLE')) OR asserted_value<>'BRIDGE_CRASH'),
    CHECK ((asserted_value='PLANNED_SHUTDOWN' AND evidence_type IN ('SUPERVISOR_COMMAND','OPERATOR_COMMAND','LISTENER_SHUTDOWN')) OR asserted_value<>'PLANNED_SHUTDOWN'),
    CHECK ((asserted_value IN ('AUTHENTICATION_FAILURE','CONNECTION_LOSS','SUBSCRIPTION_FAILURE','RAPI_ENGINE_INERT') AND evidence_type='RAPI_CALLBACK') OR asserted_value NOT IN ('AUTHENTICATION_FAILURE','CONNECTION_LOSS','SUBSCRIPTION_FAILURE','RAPI_ENGINE_INERT')),
    CHECK ((asserted_value='LISTENER_EXIT' AND evidence_type IN ('PROCESS_EXIT','OS_HANDLE','LISTENER_SHUTDOWN')) OR asserted_value<>'LISTENER_EXIT'),
    CHECK ((asserted_value IN ('COMPLETED_EXPECTED','RECOVERED','FAILED','TIMED_OUT','CANCELED') AND evidence_type IN ('SUPERVISOR_COMMAND','RAPI_CALLBACK','OS_HANDLE','PROCESS_EXIT')) OR asserted_value NOT IN ('COMPLETED_EXPECTED','RECOVERED','FAILED','TIMED_OUT','CANCELED')),
    CHECK ((asserted_value='PROCESS_EXITED' AND evidence_type IN ('PROCESS_EXIT','OS_HANDLE')) OR asserted_value<>'PROCESS_EXITED'),
    CHECK ((asserted_value='ENGINE_INERT' AND evidence_type='RAPI_CALLBACK') OR asserted_value<>'ENGINE_INERT'),
    CHECK ((evidence_type='OPERATOR_COMMAND' AND operator_command_identity IS NOT NULL) OR evidence_type<>'OPERATOR_COMMAND')
) STRICT;

CREATE TABLE termination_evidence_sets (
    termination_evidence_set_id TEXT NOT NULL PRIMARY KEY CHECK (length(termination_evidence_set_id)=36 AND termination_evidence_set_id=lower(termination_evidence_set_id) AND substr(termination_evidence_set_id,9,1)='-' AND substr(termination_evidence_set_id,14,1)='-' AND substr(termination_evidence_set_id,19,1)='-' AND substr(termination_evidence_set_id,24,1)='-' AND replace(termination_evidence_set_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(termination_evidence_set_id,15,1) IN ('1','2','3','4','5') AND substr(termination_evidence_set_id,20,1) IN ('8','9','a','b')),
    termination_result_id TEXT NOT NULL UNIQUE CHECK (length(termination_result_id)=36 AND termination_result_id=lower(termination_result_id) AND substr(termination_result_id,9,1)='-' AND substr(termination_result_id,14,1)='-' AND substr(termination_result_id,19,1)='-' AND substr(termination_result_id,24,1)='-' AND replace(termination_result_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(termination_result_id,15,1) IN ('1','2','3','4','5') AND substr(termination_result_id,20,1) IN ('8','9','a','b')),
    supervisor_generation_id TEXT NOT NULL,
    listener_epoch_id TEXT NOT NULL,
    bridge_generation_id TEXT NOT NULL,
    observed_process_identity TEXT NOT NULL CHECK (length(observed_process_identity)=36 AND observed_process_identity=lower(observed_process_identity) AND substr(observed_process_identity,9,1)='-' AND substr(observed_process_identity,14,1)='-' AND substr(observed_process_identity,19,1)='-' AND substr(observed_process_identity,24,1)='-' AND replace(observed_process_identity,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(observed_process_identity,15,1) IN ('1','2','3','4','5') AND substr(observed_process_identity,20,1) IN ('8','9','a','b')),
    termination_observation_identity TEXT NOT NULL CHECK (length(termination_observation_identity)=36 AND termination_observation_identity=lower(termination_observation_identity) AND substr(termination_observation_identity,9,1)='-' AND substr(termination_observation_identity,14,1)='-' AND substr(termination_observation_identity,19,1)='-' AND substr(termination_observation_identity,24,1)='-' AND replace(termination_observation_identity,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(termination_observation_identity,15,1) IN ('1','2','3','4','5') AND substr(termination_observation_identity,20,1) IN ('8','9','a','b')),
    observation_sequence INTEGER NOT NULL CHECK (observation_sequence>=1),
    observation_cutoff_utc TEXT NOT NULL CHECK (length(observation_cutoff_utc)=27 AND substr(observation_cutoff_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(observation_cutoff_utc,5,1)='-' AND substr(observation_cutoff_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(observation_cutoff_utc,8,1)='-' AND substr(observation_cutoff_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(observation_cutoff_utc,11,1)='T' AND substr(observation_cutoff_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(observation_cutoff_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(observation_cutoff_utc,14,1)=':' AND substr(observation_cutoff_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(observation_cutoff_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(observation_cutoff_utc,17,1)=':' AND substr(observation_cutoff_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(observation_cutoff_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(observation_cutoff_utc,20,1)='.' AND substr(observation_cutoff_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(observation_cutoff_utc,27,1)='Z' AND CAST(substr(observation_cutoff_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(observation_cutoff_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(observation_cutoff_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(observation_cutoff_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(observation_cutoff_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(observation_cutoff_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(observation_cutoff_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(observation_cutoff_utc,1,19)||'Z')||substr(observation_cutoff_utc,20,8)=observation_cutoff_utc),
    classification_decision_identity TEXT NOT NULL CHECK (length(classification_decision_identity)=36 AND classification_decision_identity=lower(classification_decision_identity) AND substr(classification_decision_identity,9,1)='-' AND substr(classification_decision_identity,14,1)='-' AND substr(classification_decision_identity,19,1)='-' AND substr(classification_decision_identity,24,1)='-' AND replace(classification_decision_identity,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(classification_decision_identity,15,1) IN ('1','2','3','4','5') AND substr(classification_decision_identity,20,1) IN ('8','9','a','b')),
    evaluator_version INTEGER NOT NULL CHECK (evaluator_version>=1),
    termination_schema_version INTEGER NOT NULL CHECK (termination_schema_version=2),
    evidence_set_integrity_sha256 TEXT NOT NULL CHECK (length(evidence_set_integrity_sha256)=64 AND evidence_set_integrity_sha256=lower(evidence_set_integrity_sha256) AND evidence_set_integrity_sha256 NOT GLOB '*[^0-9a-f]*'),
    transaction_id TEXT NOT NULL,
    writer_id TEXT NOT NULL CHECK (writer_id='HEALTH_DURABLE_WRITER'),
    UNIQUE (termination_evidence_set_id,termination_result_id,supervisor_generation_id,listener_epoch_id,bridge_generation_id,observed_process_identity,termination_observation_identity,observation_sequence,observation_cutoff_utc,classification_decision_identity,evaluator_version,termination_schema_version,evidence_set_integrity_sha256,transaction_id),
    FOREIGN KEY (termination_result_id) REFERENCES termination_results(termination_result_id) ON UPDATE RESTRICT ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (bridge_generation_id,listener_epoch_id,supervisor_generation_id) REFERENCES bridge_generations(bridge_generation_id,listener_epoch_id,supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE termination_evidence_set_producers (
    termination_evidence_set_id TEXT NOT NULL,
    producer_role TEXT NOT NULL CHECK (producer_role IN ('RITHMIC_LISTENER','BRIDGE_CONTROLLER','OS_ADAPTER','RAPI_ADAPTER','SUPERVISOR_ADAPTER','OPERATOR_ADAPTER')),
    producer_instance_id TEXT NOT NULL,
    expected_start_sequence INTEGER NOT NULL CHECK (expected_start_sequence>=1),
    expected_end_sequence INTEGER NOT NULL CHECK (expected_end_sequence>=expected_start_sequence),
    last_accepted_sequence INTEGER NOT NULL CHECK (last_accepted_sequence=expected_end_sequence),
    transaction_id TEXT NOT NULL,
    writer_id TEXT NOT NULL CHECK (writer_id='HEALTH_DURABLE_WRITER'),
    PRIMARY KEY (termination_evidence_set_id,producer_role),
    UNIQUE (termination_evidence_set_id,producer_instance_id),
    FOREIGN KEY (termination_evidence_set_id) REFERENCES termination_evidence_sets(termination_evidence_set_id) ON UPDATE RESTRICT ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (producer_instance_id) REFERENCES producer_registrations(producer_instance_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE termination_results (
    termination_result_id TEXT NOT NULL PRIMARY KEY CHECK (length(termination_result_id)=36 AND termination_result_id=lower(termination_result_id) AND substr(termination_result_id,9,1)='-' AND substr(termination_result_id,14,1)='-' AND substr(termination_result_id,19,1)='-' AND substr(termination_result_id,24,1)='-' AND replace(termination_result_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(termination_result_id,15,1) IN ('1','2','3','4','5') AND substr(termination_result_id,20,1) IN ('8','9','a','b')),
    bridge_generation_id TEXT NOT NULL,
    supervisor_generation_id TEXT NOT NULL,
    listener_epoch_id TEXT NOT NULL,
    termination_observation_identity TEXT NOT NULL CHECK (length(termination_observation_identity)=36 AND termination_observation_identity=lower(termination_observation_identity) AND substr(termination_observation_identity,9,1)='-' AND substr(termination_observation_identity,14,1)='-' AND substr(termination_observation_identity,19,1)='-' AND substr(termination_observation_identity,24,1)='-' AND replace(termination_observation_identity,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(termination_observation_identity,15,1) IN ('1','2','3','4','5') AND substr(termination_observation_identity,20,1) IN ('8','9','a','b')),
    observed_process_identity TEXT NOT NULL CHECK (length(observed_process_identity)=36 AND observed_process_identity=lower(observed_process_identity) AND substr(observed_process_identity,9,1)='-' AND substr(observed_process_identity,14,1)='-' AND substr(observed_process_identity,19,1)='-' AND substr(observed_process_identity,24,1)='-' AND replace(observed_process_identity,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(observed_process_identity,15,1) IN ('1','2','3','4','5') AND substr(observed_process_identity,20,1) IN ('8','9','a','b')),
    observation_sequence INTEGER NOT NULL CHECK (observation_sequence>=1),
    request_identity TEXT NULL CHECK (request_identity IS NULL OR (length(request_identity)=36 AND request_identity=lower(request_identity) AND substr(request_identity,9,1)='-' AND substr(request_identity,14,1)='-' AND substr(request_identity,19,1)='-' AND substr(request_identity,24,1)='-' AND replace(request_identity,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(request_identity,15,1) IN ('1','2','3','4','5') AND substr(request_identity,20,1) IN ('8','9','a','b'))),
    operator_command_identity TEXT NULL CHECK (operator_command_identity IS NULL OR (length(operator_command_identity)=36 AND operator_command_identity=lower(operator_command_identity) AND substr(operator_command_identity,9,1)='-' AND substr(operator_command_identity,14,1)='-' AND substr(operator_command_identity,19,1)='-' AND substr(operator_command_identity,24,1)='-' AND replace(operator_command_identity,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(operator_command_identity,15,1) IN ('1','2','3','4','5') AND substr(operator_command_identity,20,1) IN ('8','9','a','b'))),
    provider_evidence_identity TEXT NULL,
    os_evidence_identity TEXT NULL,
    bridge_evidence_identity TEXT NULL,
    listener_evidence_identity TEXT NULL,
    classification_decision_identity TEXT NOT NULL CHECK (length(classification_decision_identity)=36 AND classification_decision_identity=lower(classification_decision_identity) AND substr(classification_decision_identity,9,1)='-' AND substr(classification_decision_identity,14,1)='-' AND substr(classification_decision_identity,19,1)='-' AND substr(classification_decision_identity,24,1)='-' AND replace(classification_decision_identity,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(classification_decision_identity,15,1) IN ('1','2','3','4','5') AND substr(classification_decision_identity,20,1) IN ('8','9','a','b')),
    initiator TEXT NOT NULL CHECK (initiator IN ('NONE','LISTENER','LISTENER_SUPERVISOR','AUTHENTICATED_OPERATOR','RAPI_PROVIDER','UNKNOWN')),
    requested_action TEXT NOT NULL CHECK (requested_action IN ('NONE','BRIDGE_RECYCLE','BRIDGE_SHUTDOWN','LISTENER_SHUTDOWN','FULL_LISTENER_RESTART','UNKNOWN')),
    execution_method TEXT NOT NULL CHECK (execution_method IN ('NONE','GRACEFUL_RAPI_LOGOUT','GRACEFUL_PROCESS_EXIT','SUPERVISOR_TERMINATE','SUPERVISOR_KILL','PROCESS_SELF_EXIT','PROVIDER_FORCED_LOGOUT','PROVIDER_SHUTDOWN_SIGNAL','UNKNOWN')),
    observed_cause TEXT NOT NULL CHECK (observed_cause IN ('NONE','PLANNED_SHUTDOWN','BRIDGE_CRASH','AUTHENTICATION_FAILURE','CONNECTION_LOSS','SUBSCRIPTION_FAILURE','LISTENER_EXIT','RAPI_ENGINE_INERT','UNKNOWN')),
    result TEXT NOT NULL CHECK (result IN ('NONE','COMPLETED_EXPECTED','RECOVERED','FAILED','TIMED_OUT','CANCELED','PROCESS_EXITED','ENGINE_INERT','UNKNOWN')),
    termination_evidence_set_id TEXT NOT NULL UNIQUE,
    evidence_set_integrity_sha256 TEXT NOT NULL CHECK (length(evidence_set_integrity_sha256)=64 AND evidence_set_integrity_sha256=lower(evidence_set_integrity_sha256) AND evidence_set_integrity_sha256 NOT GLOB '*[^0-9a-f]*'),
    evaluator TEXT NOT NULL CHECK (evaluator='LISTENER_SUPERVISOR_STATE_EVALUATOR'),
    durable_writer TEXT NOT NULL CHECK (durable_writer='HEALTH_DURABLE_WRITER'),
    evaluator_version INTEGER NOT NULL CHECK (evaluator_version>=1),
    observed_at_utc TEXT NOT NULL CHECK (length(observed_at_utc)=27 AND substr(observed_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(observed_at_utc,5,1)='-' AND substr(observed_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(observed_at_utc,8,1)='-' AND substr(observed_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(observed_at_utc,11,1)='T' AND substr(observed_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(observed_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(observed_at_utc,14,1)=':' AND substr(observed_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(observed_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(observed_at_utc,17,1)=':' AND substr(observed_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(observed_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(observed_at_utc,20,1)='.' AND substr(observed_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(observed_at_utc,27,1)='Z' AND CAST(substr(observed_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(observed_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(observed_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(observed_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(observed_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(observed_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(observed_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(observed_at_utc,1,19)||'Z')||substr(observed_at_utc,20,8)=observed_at_utc),
    recorded_at_utc TEXT NOT NULL CHECK (length(recorded_at_utc)=27 AND substr(recorded_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(recorded_at_utc,5,1)='-' AND substr(recorded_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(recorded_at_utc,8,1)='-' AND substr(recorded_at_utc,9,2) NOT GLOB '*[^0-9]*' AND CAST(substr(recorded_at_utc,9,2) AS INTEGER)>=1 AND substr(recorded_at_utc,11,1)='T' AND substr(recorded_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(recorded_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(recorded_at_utc,14,1)=':' AND substr(recorded_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(recorded_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(recorded_at_utc,17,1)=':' AND substr(recorded_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(recorded_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(recorded_at_utc,20,1)='.' AND substr(recorded_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(recorded_at_utc,27,1)='Z' AND CAST(substr(recorded_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(recorded_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(recorded_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(recorded_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(recorded_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(recorded_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(recorded_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(recorded_at_utc,1,19)||'Z')||substr(recorded_at_utc,20,8)=recorded_at_utc),
    termination_schema_version INTEGER NOT NULL CHECK (termination_schema_version=2),
    record_integrity_sha256 TEXT NOT NULL CHECK (length(record_integrity_sha256)=64 AND record_integrity_sha256=lower(record_integrity_sha256) AND record_integrity_sha256 NOT GLOB '*[^0-9a-f]*'),
    transaction_id TEXT NOT NULL,
    FOREIGN KEY (bridge_generation_id,listener_epoch_id,supervisor_generation_id) REFERENCES bridge_generations(bridge_generation_id,listener_epoch_id,supervisor_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (provider_evidence_identity) REFERENCES termination_evidence(termination_evidence_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (os_evidence_identity) REFERENCES termination_evidence(termination_evidence_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (bridge_evidence_identity) REFERENCES termination_evidence(termination_evidence_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (listener_evidence_identity) REFERENCES termination_evidence(termination_evidence_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (termination_evidence_set_id,termination_result_id,supervisor_generation_id,listener_epoch_id,bridge_generation_id,observed_process_identity,termination_observation_identity,observation_sequence,observed_at_utc,classification_decision_identity,evaluator_version,termination_schema_version,evidence_set_integrity_sha256,transaction_id) REFERENCES termination_evidence_sets(termination_evidence_set_id,termination_result_id,supervisor_generation_id,listener_epoch_id,bridge_generation_id,observed_process_identity,termination_observation_identity,observation_sequence,observation_cutoff_utc,classification_decision_identity,evaluator_version,termination_schema_version,evidence_set_integrity_sha256,transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    UNIQUE (bridge_generation_id,observation_sequence),
    UNIQUE (bridge_generation_id,termination_observation_identity),
    CHECK (recorded_at_utc>=observed_at_utc AND ((CAST(strftime('%s',substr(recorded_at_utc,1,19)||'Z') AS INTEGER)*1000000+CAST(substr(recorded_at_utc,21,6) AS INTEGER))-(CAST(strftime('%s',substr(observed_at_utc,1,19)||'Z') AS INTEGER)*1000000+CAST(substr(observed_at_utc,21,6) AS INTEGER))) BETWEEN 0 AND 30000000)
) STRICT;

CREATE TABLE termination_result_evidence (
    termination_evidence_set_id TEXT NOT NULL,
    termination_result_id TEXT NOT NULL,
    contributor_role TEXT NOT NULL CHECK (contributor_role IN ('INITIATOR_EVIDENCE','REQUESTED_ACTION_EVIDENCE','EXECUTION_METHOD_EVIDENCE','OBSERVED_CAUSE_EVIDENCE','RESULT_EVIDENCE')),
    termination_evidence_id TEXT NOT NULL,
    producer_instance_id TEXT NOT NULL,
    producer_sequence INTEGER NOT NULL CHECK (producer_sequence>=1),
    evidence_type TEXT NOT NULL CHECK (evidence_type IN ('RAPI_CALLBACK','PROCESS_EXIT','PROCESS_EXCEPTION','SUPERVISOR_COMMAND','OPERATOR_COMMAND','OS_HANDLE','LISTENER_SHUTDOWN','STARTUP_TRANSITION')),
    observed_at_utc TEXT NOT NULL,
    termination_schema_version INTEGER NOT NULL CHECK (termination_schema_version=2),
    evidence_sha256 TEXT NOT NULL CHECK (length(evidence_sha256)=64 AND evidence_sha256=lower(evidence_sha256) AND evidence_sha256 NOT GLOB '*[^0-9a-f]*'),
    supervisor_generation_id TEXT NOT NULL,
    listener_epoch_id TEXT NOT NULL,
    bridge_generation_id TEXT NOT NULL,
    observed_process_identity TEXT NOT NULL,
    termination_observation_identity TEXT NOT NULL,
    authentication_disposition TEXT NOT NULL CHECK (authentication_disposition='AUTHENTICATED'),
    assertion_kind TEXT NOT NULL CHECK (assertion_kind IN ('POSITIVE','ABSENCE','UNCERTAINTY')),
    asserted_value TEXT NOT NULL,
    classification_basis TEXT NOT NULL CHECK (classification_basis IN ('POSITIVE_PROOF','COMPLETE_ABSENCE_PROOF','UNCERTAINTY')),
    transaction_id TEXT NOT NULL,
    writer_id TEXT NOT NULL CHECK (writer_id='HEALTH_DURABLE_WRITER'),
    PRIMARY KEY (termination_evidence_set_id,contributor_role),
    UNIQUE (termination_evidence_set_id,termination_evidence_id),
    UNIQUE (termination_evidence_id),
    UNIQUE (termination_result_id,contributor_role),
    FOREIGN KEY (termination_evidence_set_id) REFERENCES termination_evidence_sets(termination_evidence_set_id) ON UPDATE RESTRICT ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (termination_result_id) REFERENCES termination_results(termination_result_id) ON UPDATE RESTRICT ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (termination_evidence_id,producer_instance_id,producer_sequence,evidence_type,observed_at_utc,termination_schema_version,evidence_sha256,supervisor_generation_id,listener_epoch_id,bridge_generation_id,observed_process_identity,termination_observation_identity,authentication_disposition,contributor_role,assertion_kind,asserted_value) REFERENCES termination_evidence(termination_evidence_id,producer_instance_id,producer_sequence,evidence_type,observed_at_utc,termination_schema_version,evidence_sha256,supervisor_generation_id,listener_epoch_id,bridge_generation_id,observed_process_identity,termination_observation_identity,authentication_disposition,evidence_role,assertion_kind,asserted_value) ON UPDATE RESTRICT ON DELETE RESTRICT,
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
    valid_from_utc TEXT NOT NULL CHECK (length(valid_from_utc)=27 AND substr(valid_from_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(valid_from_utc,5,1)='-' AND substr(valid_from_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(valid_from_utc,8,1)='-' AND substr(valid_from_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(valid_from_utc,11,1)='T' AND substr(valid_from_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(valid_from_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(valid_from_utc,14,1)=':' AND substr(valid_from_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(valid_from_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(valid_from_utc,17,1)=':' AND substr(valid_from_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(valid_from_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(valid_from_utc,20,1)='.' AND substr(valid_from_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(valid_from_utc,27,1)='Z' AND CAST(substr(valid_from_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(valid_from_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(valid_from_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(valid_from_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(valid_from_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(valid_from_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(valid_from_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(valid_from_utc,1,19)||'Z')||substr(valid_from_utc,20,8)=valid_from_utc),
    expires_at_utc TEXT NOT NULL CHECK (length(expires_at_utc)=27 AND substr(expires_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(expires_at_utc,5,1)='-' AND substr(expires_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(expires_at_utc,8,1)='-' AND substr(expires_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(expires_at_utc,11,1)='T' AND substr(expires_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(expires_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(expires_at_utc,14,1)=':' AND substr(expires_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(expires_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(expires_at_utc,17,1)=':' AND substr(expires_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(expires_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(expires_at_utc,20,1)='.' AND substr(expires_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(expires_at_utc,27,1)='Z' AND CAST(substr(expires_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(expires_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(expires_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(expires_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(expires_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(expires_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(expires_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(expires_at_utc,1,19)||'Z')||substr(expires_at_utc,20,8)=expires_at_utc AND expires_at_utc>valid_from_utc),
    current INTEGER NOT NULL CHECK (current IN (0,1)),
    evaluation_transaction_id TEXT NOT NULL,
    evaluated_at_utc TEXT NOT NULL CHECK (length(evaluated_at_utc)=27 AND substr(evaluated_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(evaluated_at_utc,5,1)='-' AND substr(evaluated_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(evaluated_at_utc,8,1)='-' AND substr(evaluated_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(evaluated_at_utc,11,1)='T' AND substr(evaluated_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(evaluated_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(evaluated_at_utc,14,1)=':' AND substr(evaluated_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(evaluated_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(evaluated_at_utc,17,1)=':' AND substr(evaluated_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(evaluated_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(evaluated_at_utc,20,1)='.' AND substr(evaluated_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(evaluated_at_utc,27,1)='Z' AND CAST(substr(evaluated_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(evaluated_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(evaluated_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(evaluated_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(evaluated_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(evaluated_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(evaluated_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(evaluated_at_utc,1,19)||'Z')||substr(evaluated_at_utc,20,8)=evaluated_at_utc),
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
    last_attempt_utc TEXT NOT NULL CHECK (length(last_attempt_utc)=27 AND substr(last_attempt_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(last_attempt_utc,5,1)='-' AND substr(last_attempt_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(last_attempt_utc,8,1)='-' AND substr(last_attempt_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(last_attempt_utc,11,1)='T' AND substr(last_attempt_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(last_attempt_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(last_attempt_utc,14,1)=':' AND substr(last_attempt_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(last_attempt_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(last_attempt_utc,17,1)=':' AND substr(last_attempt_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(last_attempt_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(last_attempt_utc,20,1)='.' AND substr(last_attempt_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(last_attempt_utc,27,1)='Z' AND CAST(substr(last_attempt_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(last_attempt_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(last_attempt_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(last_attempt_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(last_attempt_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(last_attempt_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(last_attempt_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(last_attempt_utc,1,19)||'Z')||substr(last_attempt_utc,20,8)=last_attempt_utc),
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
    created_at_utc TEXT NOT NULL CHECK (length(created_at_utc)=27 AND substr(created_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,5,1)='-' AND substr(created_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,8,1)='-' AND substr(created_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,11,1)='T' AND substr(created_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(created_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(created_at_utc,14,1)=':' AND substr(created_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(created_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(created_at_utc,17,1)=':' AND substr(created_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(created_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(created_at_utc,20,1)='.' AND substr(created_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(created_at_utc,27,1)='Z' AND CAST(substr(created_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(created_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(created_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(created_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(created_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(created_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(created_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(created_at_utc,1,19)||'Z')||substr(created_at_utc,20,8)=created_at_utc),
    closed_at_utc TEXT NULL CHECK (closed_at_utc IS NULL OR (length(closed_at_utc)=27 AND substr(closed_at_utc,1,4) NOT GLOB '*[^0-9]*' AND substr(closed_at_utc,5,1)='-' AND substr(closed_at_utc,6,2) NOT GLOB '*[^0-9]*' AND substr(closed_at_utc,8,1)='-' AND substr(closed_at_utc,9,2) NOT GLOB '*[^0-9]*' AND substr(closed_at_utc,11,1)='T' AND substr(closed_at_utc,12,2) NOT GLOB '*[^0-9]*' AND CAST(substr(closed_at_utc,12,2) AS INTEGER) BETWEEN 0 AND 23 AND substr(closed_at_utc,14,1)=':' AND substr(closed_at_utc,15,2) NOT GLOB '*[^0-9]*' AND CAST(substr(closed_at_utc,15,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(closed_at_utc,17,1)=':' AND substr(closed_at_utc,18,2) NOT GLOB '*[^0-9]*' AND CAST(substr(closed_at_utc,18,2) AS INTEGER) BETWEEN 0 AND 59 AND substr(closed_at_utc,20,1)='.' AND substr(closed_at_utc,21,6) NOT GLOB '*[^0-9]*' AND substr(closed_at_utc,27,1)='Z' AND CAST(substr(closed_at_utc,1,4) AS INTEGER) BETWEEN 1 AND 9999 AND CAST(substr(closed_at_utc,6,2) AS INTEGER) BETWEEN 1 AND 12 AND CAST(substr(closed_at_utc,9,2) AS INTEGER) BETWEEN 1 AND (CASE CAST(substr(closed_at_utc,6,2) AS INTEGER) WHEN 2 THEN CASE WHEN (CAST(substr(closed_at_utc,1,4) AS INTEGER)%400=0 OR (CAST(substr(closed_at_utc,1,4) AS INTEGER)%4=0 AND CAST(substr(closed_at_utc,1,4) AS INTEGER)%100<>0)) THEN 29 ELSE 28 END WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END) AND strftime('%Y-%m-%dT%H:%M:%S',substr(closed_at_utc,1,19)||'Z')||substr(closed_at_utc,20,8)=closed_at_utc)),
    writer_id TEXT NOT NULL CHECK (writer_id='STORE_INCIDENT_WRITER'),
    FOREIGN KEY (transaction_id) REFERENCES transaction_commits(transaction_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CHECK ((disposition='OPEN' AND closed_at_utc IS NULL) OR (disposition<>'OPEN' AND closed_at_utc IS NOT NULL))
) STRICT;

CREATE VIEW randle_sha256_preflight_v AS
SELECT randle_sha256_hex_utf8('') AS empty_sha256;

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

CREATE TRIGGER trg_writer_registry_successor_guard
BEFORE INSERT ON writer_registry
WHEN NEW.active=1 AND EXISTS (SELECT 1 FROM writer_registry p WHERE p.registry_version=NEW.registry_version AND p.table_name=NEW.table_name AND p.operation=NEW.operation) AND (
    EXISTS (SELECT 1 FROM writer_registry p WHERE p.registry_version=NEW.registry_version AND p.table_name=NEW.table_name AND p.operation=NEW.operation AND p.active=1) OR
    NEW.effective_transaction_sequence <= COALESCE((SELECT max(p.retired_transaction_sequence) FROM writer_registry p WHERE p.registry_version=NEW.registry_version AND p.table_name=NEW.table_name AND p.operation=NEW.operation AND p.active=0),-1)
)
BEGIN SELECT RAISE(ABORT,'WRITER_SUCCESSOR_SEQUENCE_INVALID'); END;

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
    (NEW.prior_state='SUSPECT' AND NEW.resulting_state='SUSPECT' AND NEW.transition_reason='CANCELLATION_REEVALUATION_REMAINS_SUSPECT' AND NEW.restart_incident_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM transaction_commits tc
        JOIN listener_restart_incidents i ON i.restart_incident_id=NEW.restart_incident_id
        JOIN listener_restart_outcomes o ON o.listener_outcome_id=i.current_outcome_id AND o.restart_incident_id=i.restart_incident_id
        JOIN listener_current c ON c.singleton_id=1
        WHERE tc.transaction_id=NEW.transaction_id AND tc.transaction_type='TX-LSN-CANCEL'
          AND json_array_length(tc.writer_set_json)=2
          AND EXISTS (SELECT 1 FROM json_each(tc.writer_set_json) w WHERE w.type='text' AND w.value='LISTENER_INCIDENT_WRITER')
          AND EXISTS (SELECT 1 FROM json_each(tc.writer_set_json) w WHERE w.type='text' AND w.value='LISTENER_STATE_WRITER')
          AND i.incident_state='TERMINAL' AND i.update_transaction_id=NEW.transaction_id
          AND o.transaction_id=NEW.transaction_id AND o.outcome='RESTART_CANCELED' AND o.resulting_listener_state='SUSPECT'
          AND i.supervisor_generation_id=NEW.supervisor_generation_id AND i.listener_epoch_id=NEW.listener_epoch_id
          AND c.supervisor_generation_id=NEW.supervisor_generation_id AND c.listener_epoch_id=NEW.listener_epoch_id
          AND c.current_restart_incident_id=NEW.restart_incident_id AND c.lifecycle_state='SUSPECT'
          AND c.state_version=NEW.expected_prior_version
    )) OR
    (NEW.prior_state='FENCED' AND NEW.resulting_state IN ('REHYDRATING','LISTENER_FAILED','STOPPING','SUPERVISOR_STORE_FAILED')) OR
    (NEW.prior_state='STOPPING' AND NEW.resulting_state IN ('STOPPED','LISTENER_FAILED','SUPERVISOR_STORE_FAILED')) OR
    (NEW.prior_state='LISTENER_FAILED' AND NEW.resulting_state IN ('STARTING','STOPPING','SUPERVISOR_STORE_FAILED')) OR
    (NEW.prior_state='AMBIGUOUS_PROCESS_AUTHORITY' AND NEW.resulting_state IN ('STOPPED','STARTING','SUPERVISOR_STORE_FAILED')) OR
    (NEW.prior_state='SUPERVISOR_STORE_FAILED' AND NEW.resulting_state='STOPPED'))
BEGIN SELECT RAISE(ABORT,'LISTENER_TRANSITION_PROHIBITED'); END;

CREATE TRIGGER trg_listener_current_insert_match
BEFORE INSERT ON listener_current
WHEN NOT EXISTS (SELECT 1 FROM listener_state_transitions t WHERE t.listener_transition_id=NEW.last_transition_id AND t.supervisor_generation_id IS NEW.supervisor_generation_id AND t.listener_epoch_id IS NEW.listener_epoch_id AND t.resulting_state=NEW.lifecycle_state AND t.resulting_version=NEW.state_version AND t.transaction_id=NEW.update_transaction_id)
BEGIN SELECT RAISE(ABORT,'LISTENER_CURRENT_TRANSITION_MISMATCH'); END;

CREATE TRIGGER trg_listener_current_update_match
BEFORE UPDATE ON listener_current
WHEN NEW.state_version<>OLD.state_version+1 OR NOT EXISTS (SELECT 1 FROM listener_state_transitions t WHERE t.listener_transition_id=NEW.last_transition_id AND t.supervisor_generation_id IS NEW.supervisor_generation_id AND t.listener_epoch_id IS NEW.listener_epoch_id AND t.prior_state=OLD.lifecycle_state AND t.resulting_state=NEW.lifecycle_state AND t.expected_prior_version=OLD.state_version AND t.resulting_version=NEW.state_version AND t.transaction_id=NEW.update_transaction_id)
BEGIN SELECT RAISE(ABORT,'LISTENER_CURRENT_VERSION_OR_TRANSITION_MISMATCH'); END;

CREATE TRIGGER trg_listener_restart_incidents_terminal_match
BEFORE UPDATE ON listener_restart_incidents
WHEN NEW.incident_state='TERMINAL' AND (
    OLD.incident_state='TERMINAL' OR NEW.incident_version<>OLD.incident_version+1 OR
    NOT EXISTS (SELECT 1 FROM listener_restart_incident_transitions it WHERE it.incident_transition_id=NEW.last_transition_id AND it.restart_incident_id=NEW.restart_incident_id AND it.prior_incident_state=OLD.incident_state AND it.resulting_incident_state='TERMINAL' AND it.expected_prior_version=OLD.incident_version AND it.resulting_version=NEW.incident_version AND it.recovery_transaction_id IS NEW.recovery_transaction_id AND it.transaction_id=NEW.update_transaction_id) OR
    NOT EXISTS (SELECT 1 FROM listener_restart_outcomes o WHERE o.listener_outcome_id=NEW.current_outcome_id AND o.restart_incident_id=NEW.restart_incident_id AND o.transaction_id=NEW.update_transaction_id AND o.recovery_transaction_id IS NEW.recovery_transaction_id AND ((o.outcome='RESTART_CANCELED' AND OLD.incident_state='RESTART_PENDING') OR (o.outcome='RESTART_COMPLETED' AND OLD.incident_state='RESTART_REHYDRATING') OR (o.outcome='RESTART_FAILED' AND OLD.incident_state IN ('RESTART_PENDING','RESTART_FENCED','RESTART_EXECUTING','RESTART_REHYDRATING')) OR (o.outcome='RECOVERY_RATE_LIMITED_FAILED' AND OLD.incident_state='RESTART_PENDING')))
)
BEGIN SELECT RAISE(ABORT,'LISTENER_TERMINAL_OUTCOME_MISMATCH'); END;

CREATE TRIGGER trg_listener_restart_incidents_no_terminal_insert
BEFORE INSERT ON listener_restart_incidents
WHEN NEW.incident_state='TERMINAL'
BEGIN SELECT RAISE(ABORT,'LISTENER_TERMINAL_INSERT_PROHIBITED'); END;

CREATE TRIGGER trg_domain_acknowledgements_required_match
BEFORE INSERT ON domain_acknowledgements
WHEN NOT EXISTS (SELECT 1 FROM recovery_transactions r JOIN recovery_required_domains d ON d.recovery_transaction_id=r.recovery_transaction_id AND d.authoritative_domain=NEW.authoritative_domain WHERE r.recovery_transaction_id=NEW.recovery_transaction_id AND r.supervisor_generation_id=NEW.supervisor_generation_id AND r.listener_epoch_id=NEW.listener_epoch_id AND d.expected_domain_identity=NEW.expected_domain_identity) OR (NEW.acknowledgement_disposition='ACCEPTED' AND NEW.expected_domain_identity<>NEW.observed_domain_identity)
BEGIN SELECT RAISE(ABORT,'ACKNOWLEDGEMENT_IDENTITY_OR_GENERATION_MISMATCH'); END;

CREATE TRIGGER trg_subscription_verifications_proof
BEFORE INSERT ON subscription_verifications
WHEN NEW.disposition='SUBSCRIPTION_VERIFIED' AND NOT EXISTS (
    SELECT 1 FROM health_events e
    JOIN producer_registrations p ON p.producer_instance_id=e.producer_instance_id
    JOIN active_contract_sessions s ON s.contract_session_ref_id=NEW.contract_session_ref_id AND s.symbol=NEW.symbol AND s.contract_id=NEW.contract_id AND s.valid_to_sequence IS NULL
    JOIN listener_epochs le ON le.listener_epoch_id=NEW.listener_epoch_id AND le.supervisor_generation_id=NEW.supervisor_generation_id AND le.state='CURRENT'
    JOIN bridge_generations bg ON bg.bridge_generation_id=NEW.bridge_generation_id AND bg.listener_epoch_id=NEW.listener_epoch_id AND bg.supervisor_generation_id=NEW.supervisor_generation_id AND bg.state='CURRENT'
    JOIN transaction_commits tc ON tc.transaction_id=NEW.transaction_id AND tc.transaction_type='TX-SUBSCRIPTION-VERIFY'
    WHERE e.health_event_id=NEW.source_health_event_id AND e.producer_instance_id=NEW.proof_producer_id
      AND e.producer_sequence=NEW.source_producer_sequence AND p.producer_role='RITHMIC_LISTENER' AND p.revoked_sequence IS NULL
      AND e.fact_type='SUBSCRIPTION_PROOF' AND e.authentication_disposition='AUTHENTICATED'
      AND e.supervisor_generation_id=NEW.supervisor_generation_id AND e.listener_epoch_id=NEW.listener_epoch_id
      AND e.bridge_generation_id=NEW.bridge_generation_id AND e.scope_key=NEW.symbol
      AND json_type(e.canonical_event_json,'$.contract_id')='text' AND json_extract(e.canonical_event_json,'$.contract_id')=NEW.contract_id
      AND json_type(e.canonical_event_json,'$.contract_session_ref_id')='text' AND json_extract(e.canonical_event_json,'$.contract_session_ref_id')=NEW.contract_session_ref_id
      AND json_type(e.canonical_event_json,'$.request_identity')='text' AND json_extract(e.canonical_event_json,'$.request_identity')=NEW.request_identity
      AND json_type(e.canonical_event_json,'$.provider_acknowledgement_identity')='text' AND json_extract(e.canonical_event_json,'$.provider_acknowledgement_identity')=NEW.provider_acknowledgement_identity
      AND json_type(e.canonical_event_json,'$.freshness_observation_identity')='text' AND json_extract(e.canonical_event_json,'$.freshness_observation_identity')=NEW.freshness_observation_identity
      AND json_type(e.canonical_event_json,'$.proof_evidence_identity')='text' AND json_extract(e.canonical_event_json,'$.proof_evidence_identity')=NEW.proof_evidence_identity
)
BEGIN SELECT RAISE(ABORT,'SUBSCRIPTION_PROOF_INVALID'); END;

CREATE TRIGGER trg_termination_evidence_integrity
BEFORE INSERT ON termination_evidence
WHEN NOT (
    EXISTS (SELECT 1 FROM transaction_commits tc WHERE tc.transaction_id=NEW.transaction_id AND tc.transaction_type='TX-TERMINATION-EVIDENCE' AND tc.committed_at_utc>=NEW.observed_at_utc) AND
    EXISTS (SELECT 1 FROM producer_registrations p WHERE p.producer_instance_id=NEW.producer_instance_id AND p.revoked_sequence IS NULL) AND
    EXISTS (SELECT 1 FROM supervisor_generations sg JOIN listener_epochs le ON le.supervisor_generation_id=sg.supervisor_generation_id JOIN bridge_generations bg ON bg.listener_epoch_id=le.listener_epoch_id AND bg.supervisor_generation_id=sg.supervisor_generation_id WHERE sg.supervisor_generation_id=NEW.supervisor_generation_id AND sg.state='CURRENT' AND le.listener_epoch_id=NEW.listener_epoch_id AND le.listener_process_instance_id=NEW.observed_process_identity AND le.state='CURRENT' AND bg.bridge_generation_id=NEW.bridge_generation_id AND bg.state='CURRENT') AND
    NEW.canonical_evidence_json=json_object(
        'termination_evidence_id',NEW.termination_evidence_id,'producer_instance_id',NEW.producer_instance_id,'producer_sequence',NEW.producer_sequence,'ingress_sequence',NEW.ingress_sequence,
        'supervisor_generation_id',NEW.supervisor_generation_id,'listener_epoch_id',NEW.listener_epoch_id,'bridge_generation_id',NEW.bridge_generation_id,
        'observed_process_identity',NEW.observed_process_identity,'termination_observation_identity',NEW.termination_observation_identity,
        'evidence_role',NEW.evidence_role,'assertion_kind',NEW.assertion_kind,'asserted_value',NEW.asserted_value,
        'absence_scope',coalesce(NEW.absence_scope,'-'),'uncertainty_reason',coalesce(NEW.uncertainty_reason,'-'),
        'request_identity',coalesce(NEW.request_identity,'-'),'operator_command_identity',coalesce(NEW.operator_command_identity,'-'),
        'evidence_type',NEW.evidence_type,'termination_schema_version',NEW.termination_schema_version,'authentication_disposition',NEW.authentication_disposition,
        'observed_at_utc',NEW.observed_at_utc,'observed_monotonic_ns',NEW.observed_monotonic_ns,'transaction_id',NEW.transaction_id) AND
    randle_sha256_hex_utf8(NEW.canonical_evidence_json)=NEW.evidence_sha256
)
BEGIN SELECT RAISE(ABORT,'TERMINATION_EVIDENCE_INTEGRITY_INVALID'); END;

CREATE TRIGGER trg_termination_evidence_observation_sealed
BEFORE INSERT ON termination_evidence
WHEN EXISTS (SELECT 1 FROM termination_results r WHERE r.termination_observation_identity=NEW.termination_observation_identity)
BEGIN SELECT RAISE(ABORT,'TERMINATION_OBSERVATION_ALREADY_CLASSIFIED'); END;

CREATE TRIGGER trg_termination_results_structure
BEFORE INSERT ON termination_results
WHEN NOT (
    EXISTS (
        SELECT 1 FROM termination_evidence_sets s
        JOIN transaction_commits tc ON tc.transaction_id=NEW.transaction_id AND tc.transaction_type='TX-TERMINATION-CLASSIFY'
        JOIN supervisor_generations sg ON sg.supervisor_generation_id=NEW.supervisor_generation_id AND sg.state='CURRENT'
        JOIN listener_epochs le ON le.listener_epoch_id=NEW.listener_epoch_id AND le.supervisor_generation_id=NEW.supervisor_generation_id AND le.listener_process_instance_id=NEW.observed_process_identity AND le.state='CURRENT'
        JOIN bridge_generations bg ON bg.bridge_generation_id=NEW.bridge_generation_id AND bg.listener_epoch_id=NEW.listener_epoch_id AND bg.supervisor_generation_id=NEW.supervisor_generation_id AND bg.state='CURRENT'
        WHERE s.termination_evidence_set_id=NEW.termination_evidence_set_id AND s.termination_result_id=NEW.termination_result_id
          AND s.supervisor_generation_id=NEW.supervisor_generation_id AND s.listener_epoch_id=NEW.listener_epoch_id AND s.bridge_generation_id=NEW.bridge_generation_id
          AND s.observed_process_identity=NEW.observed_process_identity AND s.termination_observation_identity=NEW.termination_observation_identity
          AND s.observation_sequence=NEW.observation_sequence AND s.observation_cutoff_utc=NEW.observed_at_utc
          AND s.classification_decision_identity=NEW.classification_decision_identity AND s.evaluator_version=NEW.evaluator_version
          AND s.termination_schema_version=NEW.termination_schema_version AND s.evidence_set_integrity_sha256=NEW.evidence_set_integrity_sha256
          AND s.transaction_id=NEW.transaction_id AND tc.committed_at_utc=NEW.recorded_at_utc AND tc.evidence_set_hash=NEW.evidence_set_integrity_sha256
          AND json_array_length(tc.writer_set_json)=1 AND EXISTS (SELECT 1 FROM json_each(tc.writer_set_json) w WHERE w.type='text' AND w.value='HEALTH_DURABLE_WRITER')) AND
    NEW.observation_sequence=coalesce((SELECT max(r.observation_sequence)+1 FROM termination_results r WHERE r.bridge_generation_id=NEW.bridge_generation_id),1) AND
    (SELECT count(*) FROM termination_evidence_set_producers p WHERE p.termination_evidence_set_id=NEW.termination_evidence_set_id AND p.transaction_id=NEW.transaction_id)=6 AND
    NOT EXISTS (
        SELECT 1 FROM termination_evidence_set_producers p
        JOIN termination_evidence_sets s ON s.termination_evidence_set_id=p.termination_evidence_set_id
        WHERE p.termination_evidence_set_id=NEW.termination_evidence_set_id AND NOT (
            EXISTS (SELECT 1 FROM producer_registrations pr WHERE pr.producer_instance_id=p.producer_instance_id AND pr.producer_role=p.producer_role AND pr.revoked_sequence IS NULL) AND
            p.expected_start_sequence=coalesce((SELECT max(pp.expected_end_sequence)+1 FROM termination_evidence_set_producers pp JOIN termination_evidence_sets ps ON ps.termination_evidence_set_id=pp.termination_evidence_set_id WHERE pp.producer_instance_id=p.producer_instance_id AND ps.bridge_generation_id=s.bridge_generation_id AND ps.observation_sequence<s.observation_sequence),1) AND
            (SELECT count(*) FROM termination_evidence e WHERE e.producer_instance_id=p.producer_instance_id AND e.termination_observation_identity=s.termination_observation_identity AND e.supervisor_generation_id=s.supervisor_generation_id AND e.listener_epoch_id=s.listener_epoch_id AND e.bridge_generation_id=s.bridge_generation_id AND e.observed_process_identity=s.observed_process_identity AND e.termination_schema_version=s.termination_schema_version AND e.authentication_disposition='AUTHENTICATED' AND e.producer_sequence BETWEEN p.expected_start_sequence AND p.expected_end_sequence AND e.observed_at_utc<=s.observation_cutoff_utc)=p.expected_end_sequence-p.expected_start_sequence+1 AND
            (SELECT min(e.producer_sequence) FROM termination_evidence e WHERE e.producer_instance_id=p.producer_instance_id AND e.termination_observation_identity=s.termination_observation_identity AND e.producer_sequence BETWEEN p.expected_start_sequence AND p.expected_end_sequence)=p.expected_start_sequence AND
            (SELECT max(e.producer_sequence) FROM termination_evidence e WHERE e.producer_instance_id=p.producer_instance_id AND e.termination_observation_identity=s.termination_observation_identity AND e.producer_sequence BETWEEN p.expected_start_sequence AND p.expected_end_sequence)=p.expected_end_sequence AND
            NOT EXISTS (SELECT 1 FROM termination_evidence a JOIN termination_evidence b ON b.producer_instance_id=a.producer_instance_id AND b.termination_observation_identity=a.termination_observation_identity AND b.producer_sequence>a.producer_sequence AND b.ingress_sequence<=a.ingress_sequence WHERE a.producer_instance_id=p.producer_instance_id AND a.termination_observation_identity=s.termination_observation_identity AND a.producer_sequence BETWEEN p.expected_start_sequence AND p.expected_end_sequence AND b.producer_sequence BETWEEN p.expected_start_sequence AND p.expected_end_sequence) AND
            (SELECT max((CAST(strftime('%s',substr(e.observed_at_utc,1,19)||'Z') AS INTEGER)*1000000+CAST(substr(e.observed_at_utc,21,6) AS INTEGER))) FROM termination_evidence e WHERE e.producer_instance_id=p.producer_instance_id AND e.termination_observation_identity=s.termination_observation_identity AND e.producer_sequence BETWEEN p.expected_start_sequence AND p.expected_end_sequence) >= (CAST(strftime('%s',substr(s.observation_cutoff_utc,1,19)||'Z') AS INTEGER)*1000000+CAST(substr(s.observation_cutoff_utc,21,6) AS INTEGER))-5000000)) AND
    NOT EXISTS (
        SELECT 1 FROM termination_evidence e
        JOIN producer_registrations pr ON pr.producer_instance_id=e.producer_instance_id
        WHERE e.termination_observation_identity=NEW.termination_observation_identity
          AND e.supervisor_generation_id=NEW.supervisor_generation_id AND e.listener_epoch_id=NEW.listener_epoch_id AND e.bridge_generation_id=NEW.bridge_generation_id AND e.observed_process_identity=NEW.observed_process_identity
          AND pr.producer_role IN ('RITHMIC_LISTENER','BRIDGE_CONTROLLER','OS_ADAPTER','RAPI_ADAPTER','SUPERVISOR_ADAPTER','OPERATOR_ADAPTER')
          AND NOT EXISTS (SELECT 1 FROM termination_evidence_set_producers p WHERE p.termination_evidence_set_id=NEW.termination_evidence_set_id AND p.producer_instance_id=e.producer_instance_id AND e.producer_sequence BETWEEN p.expected_start_sequence AND p.expected_end_sequence)) AND
    NOT EXISTS (SELECT 1 FROM termination_result_evidence x WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id AND (CAST(strftime('%s',substr(x.observed_at_utc,1,19)||'Z') AS INTEGER)*1000000+CAST(substr(x.observed_at_utc,21,6) AS INTEGER)) < (CAST(strftime('%s',substr(NEW.observed_at_utc,1,19)||'Z') AS INTEGER)*1000000+CAST(substr(NEW.observed_at_utc,21,6) AS INTEGER))-5000000) AND
    (SELECT count(*) FROM termination_result_evidence x WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id AND x.termination_result_id=NEW.termination_result_id AND x.transaction_id=NEW.transaction_id)=5
)
BEGIN SELECT RAISE(ABORT,'TERMINATION_EVIDENCE_STRUCTURE_INVALID'); END;

CREATE TRIGGER trg_termination_results_semantics
BEFORE INSERT ON termination_results
WHEN NOT (
    EXISTS (SELECT 1 FROM termination_result_evidence x JOIN termination_evidence e ON e.termination_evidence_id=x.termination_evidence_id WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id AND x.contributor_role='INITIATOR_EVIDENCE' AND e.asserted_value=NEW.initiator AND x.classification_basis=CASE WHEN NEW.initiator='NONE' THEN 'COMPLETE_ABSENCE_PROOF' WHEN NEW.initiator='UNKNOWN' THEN 'UNCERTAINTY' ELSE 'POSITIVE_PROOF' END) AND
    EXISTS (SELECT 1 FROM termination_result_evidence x JOIN termination_evidence e ON e.termination_evidence_id=x.termination_evidence_id WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id AND x.contributor_role='REQUESTED_ACTION_EVIDENCE' AND e.asserted_value=NEW.requested_action AND x.classification_basis=CASE WHEN NEW.requested_action='NONE' THEN 'COMPLETE_ABSENCE_PROOF' WHEN NEW.requested_action='UNKNOWN' THEN 'UNCERTAINTY' ELSE 'POSITIVE_PROOF' END) AND
    EXISTS (SELECT 1 FROM termination_result_evidence x JOIN termination_evidence e ON e.termination_evidence_id=x.termination_evidence_id WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id AND x.contributor_role='EXECUTION_METHOD_EVIDENCE' AND e.asserted_value=NEW.execution_method AND x.classification_basis=CASE WHEN NEW.execution_method='NONE' THEN 'COMPLETE_ABSENCE_PROOF' WHEN NEW.execution_method='UNKNOWN' THEN 'UNCERTAINTY' ELSE 'POSITIVE_PROOF' END) AND
    EXISTS (SELECT 1 FROM termination_result_evidence x JOIN termination_evidence e ON e.termination_evidence_id=x.termination_evidence_id WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id AND x.contributor_role='OBSERVED_CAUSE_EVIDENCE' AND e.asserted_value=NEW.observed_cause AND x.classification_basis=CASE WHEN NEW.observed_cause='NONE' THEN 'COMPLETE_ABSENCE_PROOF' WHEN NEW.observed_cause='UNKNOWN' THEN 'UNCERTAINTY' ELSE 'POSITIVE_PROOF' END) AND
    EXISTS (SELECT 1 FROM termination_result_evidence x JOIN termination_evidence e ON e.termination_evidence_id=x.termination_evidence_id WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id AND x.contributor_role='RESULT_EVIDENCE' AND e.asserted_value=NEW.result AND x.classification_basis=CASE WHEN NEW.result='NONE' THEN 'COMPLETE_ABSENCE_PROOF' WHEN NEW.result='UNKNOWN' THEN 'UNCERTAINTY' ELSE 'POSITIVE_PROOF' END) AND
    ((NEW.requested_action IN ('NONE','UNKNOWN') AND NEW.request_identity IS NULL) OR (NEW.requested_action NOT IN ('NONE','UNKNOWN') AND NEW.request_identity IS NOT NULL AND EXISTS (SELECT 1 FROM termination_result_evidence x JOIN termination_evidence e ON e.termination_evidence_id=x.termination_evidence_id WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id AND e.request_identity=NEW.request_identity))) AND
    ((NEW.initiator='AUTHENTICATED_OPERATOR' AND NEW.operator_command_identity IS NOT NULL AND EXISTS (SELECT 1 FROM termination_result_evidence x JOIN termination_evidence e ON e.termination_evidence_id=x.termination_evidence_id JOIN producer_registrations p ON p.producer_instance_id=e.producer_instance_id WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id AND e.operator_command_identity=NEW.operator_command_identity AND e.evidence_type='OPERATOR_COMMAND' AND p.producer_role='OPERATOR_ADAPTER')) OR (NEW.initiator<>'AUTHENTICATED_OPERATOR' AND NEW.operator_command_identity IS NULL)) AND
    (NEW.provider_evidence_identity IS NULL OR EXISTS (SELECT 1 FROM termination_result_evidence x JOIN termination_evidence e ON e.termination_evidence_id=x.termination_evidence_id JOIN producer_registrations p ON p.producer_instance_id=e.producer_instance_id WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id AND e.termination_evidence_id=NEW.provider_evidence_identity AND e.evidence_type='RAPI_CALLBACK' AND p.producer_role='RAPI_ADAPTER')) AND
    (NEW.os_evidence_identity IS NULL OR EXISTS (SELECT 1 FROM termination_result_evidence x JOIN termination_evidence e ON e.termination_evidence_id=x.termination_evidence_id JOIN producer_registrations p ON p.producer_instance_id=e.producer_instance_id WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id AND e.termination_evidence_id=NEW.os_evidence_identity AND e.evidence_type IN ('OS_HANDLE','PROCESS_EXIT','PROCESS_EXCEPTION') AND p.producer_role='OS_ADAPTER')) AND
    (NEW.bridge_evidence_identity IS NULL OR EXISTS (SELECT 1 FROM termination_result_evidence x JOIN termination_evidence e ON e.termination_evidence_id=x.termination_evidence_id JOIN producer_registrations p ON p.producer_instance_id=e.producer_instance_id WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id AND e.termination_evidence_id=NEW.bridge_evidence_identity AND p.producer_role='BRIDGE_CONTROLLER')) AND
    (NEW.listener_evidence_identity IS NULL OR EXISTS (SELECT 1 FROM termination_result_evidence x JOIN termination_evidence e ON e.termination_evidence_id=x.termination_evidence_id JOIN producer_registrations p ON p.producer_instance_id=e.producer_instance_id WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id AND e.termination_evidence_id=NEW.listener_evidence_identity AND p.producer_role='RITHMIC_LISTENER')) AND
    ((EXISTS (SELECT 1 FROM termination_result_evidence x JOIN termination_evidence e ON e.termination_evidence_id=x.termination_evidence_id JOIN producer_registrations p ON p.producer_instance_id=e.producer_instance_id WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id AND e.assertion_kind='POSITIVE' AND p.producer_role='RAPI_ADAPTER'))=(NEW.provider_evidence_identity IS NOT NULL)) AND
    ((EXISTS (SELECT 1 FROM termination_result_evidence x JOIN termination_evidence e ON e.termination_evidence_id=x.termination_evidence_id JOIN producer_registrations p ON p.producer_instance_id=e.producer_instance_id WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id AND e.assertion_kind='POSITIVE' AND p.producer_role='OS_ADAPTER'))=(NEW.os_evidence_identity IS NOT NULL)) AND
    ((EXISTS (SELECT 1 FROM termination_result_evidence x JOIN termination_evidence e ON e.termination_evidence_id=x.termination_evidence_id JOIN producer_registrations p ON p.producer_instance_id=e.producer_instance_id WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id AND e.assertion_kind='POSITIVE' AND p.producer_role='BRIDGE_CONTROLLER'))=(NEW.bridge_evidence_identity IS NOT NULL)) AND
    ((EXISTS (SELECT 1 FROM termination_result_evidence x JOIN termination_evidence e ON e.termination_evidence_id=x.termination_evidence_id JOIN producer_registrations p ON p.producer_instance_id=e.producer_instance_id WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id AND e.assertion_kind='POSITIVE' AND p.producer_role='RITHMIC_LISTENER'))=(NEW.listener_evidence_identity IS NOT NULL)) AND
    (NEW.observed_cause<>'PLANNED_SHUTDOWN' OR (NEW.request_identity IS NOT NULL AND NEW.requested_action NOT IN ('NONE','UNKNOWN') AND NEW.execution_method NOT IN ('NONE','UNKNOWN') AND NEW.result IN ('COMPLETED_EXPECTED','PROCESS_EXITED','ENGINE_INERT')))
)
BEGIN SELECT RAISE(ABORT,'TERMINATION_EVIDENCE_SEMANTICS_INVALID'); END;

CREATE TRIGGER trg_termination_results_none_completeness
BEFORE INSERT ON termination_results
WHEN EXISTS (
    SELECT 1 FROM termination_result_evidence x
    WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id
      AND (CASE x.contributor_role WHEN 'INITIATOR_EVIDENCE' THEN NEW.initiator WHEN 'REQUESTED_ACTION_EVIDENCE' THEN NEW.requested_action WHEN 'EXECUTION_METHOD_EVIDENCE' THEN NEW.execution_method WHEN 'OBSERVED_CAUSE_EVIDENCE' THEN NEW.observed_cause ELSE NEW.result END)='NONE'
      AND (SELECT count(DISTINCT p.producer_role)
           FROM termination_evidence e
           JOIN termination_evidence_set_producers p ON p.producer_instance_id=e.producer_instance_id AND p.termination_evidence_set_id=NEW.termination_evidence_set_id
           WHERE e.termination_observation_identity=NEW.termination_observation_identity
             AND e.evidence_role=x.contributor_role
             AND e.producer_sequence BETWEEN p.expected_start_sequence AND p.expected_end_sequence
             AND e.asserted_value='NONE' AND e.assertion_kind='ABSENCE'
             AND e.evidence_type='STARTUP_TRANSITION'
             AND e.absence_scope=CASE x.contributor_role WHEN 'INITIATOR_EVIDENCE' THEN 'NO_INITIATOR_THROUGH_CUTOFF' WHEN 'REQUESTED_ACTION_EVIDENCE' THEN 'NO_REQUEST_THROUGH_CUTOFF' WHEN 'EXECUTION_METHOD_EVIDENCE' THEN 'NO_EXECUTION_THROUGH_CUTOFF' WHEN 'OBSERVED_CAUSE_EVIDENCE' THEN 'NO_CAUSE_THROUGH_CUTOFF' ELSE 'NO_RESULT_THROUGH_CUTOFF' END)<>6
)
BEGIN SELECT RAISE(ABORT,'TERMINATION_NONE_EVIDENCE_INCOMPLETE'); END;

CREATE TRIGGER trg_termination_results_known_conflict
BEFORE INSERT ON termination_results
WHEN EXISTS (
    SELECT 1 FROM termination_result_evidence x
    WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id
      AND (CASE x.contributor_role WHEN 'INITIATOR_EVIDENCE' THEN NEW.initiator WHEN 'REQUESTED_ACTION_EVIDENCE' THEN NEW.requested_action WHEN 'EXECUTION_METHOD_EVIDENCE' THEN NEW.execution_method WHEN 'OBSERVED_CAUSE_EVIDENCE' THEN NEW.observed_cause ELSE NEW.result END)<>'UNKNOWN'
      AND EXISTS (
          SELECT 1 FROM termination_evidence e JOIN termination_evidence_set_producers p ON p.producer_instance_id=e.producer_instance_id AND p.termination_evidence_set_id=NEW.termination_evidence_set_id
          WHERE e.termination_observation_identity=NEW.termination_observation_identity AND e.evidence_role=x.contributor_role
            AND e.producer_sequence BETWEEN p.expected_start_sequence AND p.expected_end_sequence AND e.asserted_value<>'UNKNOWN'
            AND e.asserted_value<>(CASE x.contributor_role WHEN 'INITIATOR_EVIDENCE' THEN NEW.initiator WHEN 'REQUESTED_ACTION_EVIDENCE' THEN NEW.requested_action WHEN 'EXECUTION_METHOD_EVIDENCE' THEN NEW.execution_method WHEN 'OBSERVED_CAUSE_EVIDENCE' THEN NEW.observed_cause ELSE NEW.result END))
)
BEGIN SELECT RAISE(ABORT,'TERMINATION_EVIDENCE_CONFLICT_UNRESOLVED'); END;

CREATE TRIGGER trg_termination_results_unknown_conflict
BEFORE INSERT ON termination_results
WHEN EXISTS (
    SELECT 1 FROM termination_result_evidence x JOIN termination_evidence c ON c.termination_evidence_id=x.termination_evidence_id
    WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id
      AND (CASE x.contributor_role WHEN 'INITIATOR_EVIDENCE' THEN NEW.initiator WHEN 'REQUESTED_ACTION_EVIDENCE' THEN NEW.requested_action WHEN 'EXECUTION_METHOD_EVIDENCE' THEN NEW.execution_method WHEN 'OBSERVED_CAUSE_EVIDENCE' THEN NEW.observed_cause ELSE NEW.result END)='UNKNOWN'
      AND ((c.uncertainty_reason='CONFLICT' AND (SELECT count(DISTINCT e.asserted_value) FROM termination_evidence e JOIN termination_evidence_set_producers p ON p.producer_instance_id=e.producer_instance_id AND p.termination_evidence_set_id=NEW.termination_evidence_set_id WHERE e.termination_observation_identity=NEW.termination_observation_identity AND e.evidence_role=x.contributor_role AND e.producer_sequence BETWEEN p.expected_start_sequence AND p.expected_end_sequence AND e.asserted_value<>'UNKNOWN')<=1)
        OR (c.uncertainty_reason='INDETERMINATE' AND (SELECT count(DISTINCT e.asserted_value) FROM termination_evidence e JOIN termination_evidence_set_producers p ON p.producer_instance_id=e.producer_instance_id AND p.termination_evidence_set_id=NEW.termination_evidence_set_id WHERE e.termination_observation_identity=NEW.termination_observation_identity AND e.evidence_role=x.contributor_role AND e.producer_sequence BETWEEN p.expected_start_sequence AND p.expected_end_sequence AND e.asserted_value<>'UNKNOWN')>1))
)
BEGIN SELECT RAISE(ABORT,'TERMINATION_UNKNOWN_REASON_INVALID'); END;

CREATE TRIGGER trg_termination_results_integrity
BEFORE INSERT ON termination_results
WHEN NOT EXISTS (
    SELECT 1 FROM termination_evidence_sets s WHERE s.termination_evidence_set_id=NEW.termination_evidence_set_id AND
    s.evidence_set_integrity_sha256=randle_sha256_hex_utf8(
        'RANDLE-TERMINATION-EVIDENCE-SET-2'||char(10)||
        s.termination_evidence_set_id||char(9)||s.termination_result_id||char(9)||s.supervisor_generation_id||char(9)||s.listener_epoch_id||char(9)||s.bridge_generation_id||char(9)||s.observed_process_identity||char(9)||s.termination_observation_identity||char(9)||s.observation_sequence||char(9)||s.observation_cutoff_utc||char(9)||s.classification_decision_identity||char(9)||s.evaluator_version||char(9)||s.termination_schema_version||char(9)||s.transaction_id||char(10)||
        (SELECT group_concat(line,char(10)) FROM (SELECT 'P'||char(9)||p.producer_role||char(9)||p.producer_instance_id||char(9)||p.expected_start_sequence||char(9)||p.expected_end_sequence||char(9)||p.last_accepted_sequence AS line FROM termination_evidence_set_producers p WHERE p.termination_evidence_set_id=s.termination_evidence_set_id ORDER BY p.producer_role))||char(10)||
        (SELECT group_concat(line,char(10)) FROM (SELECT 'E'||char(9)||p.producer_role||char(9)||e.producer_sequence||char(9)||e.termination_evidence_id||char(9)||e.evidence_sha256 AS line FROM termination_evidence_set_producers p JOIN termination_evidence e ON e.producer_instance_id=p.producer_instance_id AND e.producer_sequence BETWEEN p.expected_start_sequence AND p.expected_end_sequence WHERE p.termination_evidence_set_id=s.termination_evidence_set_id AND e.termination_observation_identity=s.termination_observation_identity ORDER BY p.producer_role,e.producer_sequence))||char(10)||
        (SELECT group_concat(line,char(10)) FROM (SELECT 'C'||char(9)||x.contributor_role||char(9)||x.termination_evidence_id AS line FROM termination_result_evidence x WHERE x.termination_evidence_set_id=s.termination_evidence_set_id ORDER BY x.contributor_role))||char(10)) AND
    NEW.record_integrity_sha256=randle_sha256_hex_utf8(
        'RANDLE-TERMINATION-RESULT-2'||char(10)||
        NEW.termination_result_id||char(9)||NEW.termination_evidence_set_id||char(9)||NEW.supervisor_generation_id||char(9)||NEW.listener_epoch_id||char(9)||NEW.bridge_generation_id||char(9)||NEW.observed_process_identity||char(9)||NEW.termination_observation_identity||char(9)||NEW.observation_sequence||char(9)||coalesce(NEW.request_identity,'-')||char(9)||coalesce(NEW.operator_command_identity,'-')||char(9)||coalesce(NEW.provider_evidence_identity,'-')||char(9)||coalesce(NEW.os_evidence_identity,'-')||char(9)||coalesce(NEW.bridge_evidence_identity,'-')||char(9)||coalesce(NEW.listener_evidence_identity,'-')||char(9)||NEW.classification_decision_identity||char(9)||NEW.initiator||char(9)||NEW.requested_action||char(9)||NEW.execution_method||char(9)||NEW.observed_cause||char(9)||NEW.result||char(9)||NEW.evaluator||char(9)||NEW.durable_writer||char(9)||NEW.evaluator_version||char(9)||NEW.evidence_set_integrity_sha256||char(9)||NEW.observed_at_utc||char(9)||NEW.recorded_at_utc||char(9)||NEW.termination_schema_version||char(9)||NEW.transaction_id||char(10)||
        (SELECT group_concat(line,char(10)) FROM (SELECT x.contributor_role||char(9)||x.termination_evidence_id AS line FROM termination_result_evidence x WHERE x.termination_evidence_set_id=NEW.termination_evidence_set_id ORDER BY x.contributor_role))||char(10))
)
BEGIN SELECT RAISE(ABORT,'TERMINATION_RECORD_INTEGRITY_INVALID'); END;

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
(2,'active_contract_sessions','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-R1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'active_contract_sessions','UPDATE','HEALTH_DURABLE_WRITER','PHASE3C1-R1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),
(2,'bridge_current','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-R1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'bridge_current','UPDATE','HEALTH_DURABLE_WRITER','PHASE3C1-R1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),
(2,'bridge_generations','INSERT','BRIDGE_GENERATION_WRITER','PHASE3C1-R1-BRIDGE-GENERATION-WRITER-V1',NULL,0,NULL,1),(2,'bridge_generations','UPDATE','BRIDGE_GENERATION_WRITER','PHASE3C1-R1-BRIDGE-GENERATION-WRITER-V1',NULL,0,NULL,1),
(2,'bridge_incidents','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-R1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'bridge_incidents','UPDATE','HEALTH_DURABLE_WRITER','PHASE3C1-R1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),
(2,'bridge_outcomes','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-R1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'bridge_recycle_attempts','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-R1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'bridge_recycle_attempts','UPDATE','HEALTH_DURABLE_WRITER','PHASE3C1-R1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'bridge_transitions','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-R1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),
(2,'domain_acknowledgements','INSERT','LISTENER_ACKNOWLEDGEMENT_WRITER','PHASE3C1-R1-LISTENER-ACKNOWLEDGEMENT-WRITER-V1',NULL,0,NULL,1),
(2,'health_aggregate','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-R1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'health_aggregate','UPDATE','HEALTH_DURABLE_WRITER','PHASE3C1-R1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'health_current','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-R1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'health_current','UPDATE','HEALTH_DURABLE_WRITER','PHASE3C1-R1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'health_events','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-R1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'health_transitions','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-R1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),
(2,'idempotency_records','INSERT','RUNTIME_AUTHORITY_STORE_TRANSACTION_COORDINATOR','PHASE3C1-R1-RUNTIME-AUTHORITY-STORE-TRANSACTION-COORDINATOR-V1',NULL,0,NULL,1),
(2,'listener_current','INSERT','LISTENER_STATE_WRITER','PHASE3C1-R1-LISTENER-STATE-WRITER-V1',NULL,0,NULL,1),(2,'listener_current','UPDATE','LISTENER_STATE_WRITER','PHASE3C1-R1-LISTENER-STATE-WRITER-V1',NULL,0,NULL,1),
(2,'listener_epochs','INSERT','LISTENER_EPOCH_WRITER','PHASE3C1-R1-LISTENER-EPOCH-WRITER-V1',NULL,0,NULL,1),(2,'listener_epochs','UPDATE','LISTENER_EPOCH_WRITER','PHASE3C1-R1-LISTENER-EPOCH-WRITER-V1',NULL,0,NULL,1),
(2,'listener_execution_attempts','INSERT','LISTENER_INCIDENT_WRITER','PHASE3C1-R1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'listener_execution_attempts','UPDATE','LISTENER_INCIDENT_WRITER','PHASE3C1-R1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'listener_fences','INSERT','LISTENER_INCIDENT_WRITER','PHASE3C1-R1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'listener_rehydrations','INSERT','LISTENER_INCIDENT_WRITER','PHASE3C1-R1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'listener_rehydrations','UPDATE','LISTENER_INCIDENT_WRITER','PHASE3C1-R1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),
(2,'listener_restart_incident_transitions','INSERT','LISTENER_INCIDENT_WRITER','PHASE3C1-R1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'listener_restart_incidents','INSERT','LISTENER_INCIDENT_WRITER','PHASE3C1-R1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'listener_restart_incidents','UPDATE','LISTENER_INCIDENT_WRITER','PHASE3C1-R1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'listener_restart_outcomes','INSERT','LISTENER_INCIDENT_WRITER','PHASE3C1-R1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'listener_state_transitions','INSERT','LISTENER_STATE_WRITER','PHASE3C1-R1-LISTENER-STATE-WRITER-V1',NULL,0,NULL,1),
(2,'market_data_expectations','INSERT','LISTENER_INCIDENT_WRITER','PHASE3C1-R1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'market_data_expectations','UPDATE','LISTENER_INCIDENT_WRITER','PHASE3C1-R1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'producer_registrations','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-R1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'producer_registrations','UPDATE','HEALTH_DURABLE_WRITER','PHASE3C1-R1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'projection_cursors','INSERT','PROJECTION_WRITER','PHASE3C1-R1-PROJECTION-WRITER-V1',NULL,0,NULL,1),(2,'projection_cursors','UPDATE','PROJECTION_WRITER','PHASE3C1-R1-PROJECTION-WRITER-V1',NULL,0,NULL,1),
(2,'recovery_required_domains','INSERT','LISTENER_ACKNOWLEDGEMENT_WRITER','PHASE3C1-R1-LISTENER-ACKNOWLEDGEMENT-WRITER-V1',NULL,0,NULL,1),(2,'recovery_transactions','INSERT','RECOVERY_TRANSACTION_WRITER','PHASE3C1-R1-RECOVERY-TRANSACTION-WRITER-V1',NULL,0,NULL,1),(2,'recovery_transactions','UPDATE','RECOVERY_TRANSACTION_WRITER','PHASE3C1-R1-RECOVERY-TRANSACTION-WRITER-V1',NULL,0,NULL,1),(2,'shared_feed_policies','INSERT','LISTENER_INCIDENT_WRITER','PHASE3C1-R1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'shared_feed_policies','UPDATE','LISTENER_INCIDENT_WRITER','PHASE3C1-R1-LISTENER-INCIDENT-WRITER-V1',NULL,0,NULL,1),
(2,'store_incidents','INSERT','STORE_INCIDENT_WRITER','PHASE3C1-R1-STORE-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'store_incidents','UPDATE','STORE_INCIDENT_WRITER','PHASE3C1-R1-STORE-INCIDENT-WRITER-V1',NULL,0,NULL,1),(2,'store_metadata','INSERT','RUNTIME_AUTHORITY_STORE_TRANSACTION_COORDINATOR','PHASE3C1-R1-RUNTIME-AUTHORITY-STORE-TRANSACTION-COORDINATOR-V1',NULL,0,NULL,1),(2,'store_metadata','UPDATE','RUNTIME_AUTHORITY_STORE_TRANSACTION_COORDINATOR','PHASE3C1-R1-RUNTIME-AUTHORITY-STORE-TRANSACTION-COORDINATOR-V1',NULL,0,NULL,1),(2,'subscription_verifications','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-R1-HEALTH-DURABLE-WRITER-V1',NULL,0,NULL,1),(2,'supervisor_generations','INSERT','SUPERVISOR_GENERATION_WRITER','PHASE3C1-R1-SUPERVISOR-GENERATION-WRITER-V1',NULL,0,NULL,1),(2,'supervisor_generations','UPDATE','SUPERVISOR_GENERATION_WRITER','PHASE3C1-R1-SUPERVISOR-GENERATION-WRITER-V1',NULL,0,NULL,1),(2,'supervisor_leases','INSERT','SUPERVISOR_GENERATION_WRITER','PHASE3C1-R1-SUPERVISOR-GENERATION-WRITER-V1',NULL,0,NULL,1),(2,'supervisor_leases','UPDATE','SUPERVISOR_GENERATION_WRITER','PHASE3C1-R1-SUPERVISOR-GENERATION-WRITER-V1',NULL,0,NULL,1),(2,'termination_evidence','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-R2-HEALTH-DURABLE-WRITER-TERMINATION-V1',NULL,0,NULL,1),(2,'termination_evidence_set_producers','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-R2-HEALTH-DURABLE-WRITER-TERMINATION-V1',NULL,0,NULL,1),(2,'termination_evidence_sets','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-R2-HEALTH-DURABLE-WRITER-TERMINATION-V1',NULL,0,NULL,1),(2,'termination_result_evidence','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-R2-HEALTH-DURABLE-WRITER-TERMINATION-V1',NULL,0,NULL,1),(2,'termination_results','INSERT','HEALTH_DURABLE_WRITER','PHASE3C1-R2-HEALTH-DURABLE-WRITER-TERMINATION-V1',NULL,0,NULL,1),(2,'transaction_commits','INSERT','RUNTIME_AUTHORITY_STORE_TRANSACTION_COORDINATOR','PHASE3C1-R1-RUNTIME-AUTHORITY-STORE-TRANSACTION-COORDINATOR-V1',NULL,0,NULL,1),(2,'writer_registry','INSERT','RUNTIME_AUTHORITY_STORE_TRANSACTION_COORDINATOR','PHASE3C1-R1-RUNTIME-AUTHORITY-STORE-TRANSACTION-COORDINATOR-V1',NULL,0,NULL,1),(2,'writer_registry','UPDATE','RUNTIME_AUTHORITY_STORE_TRANSACTION_COORDINATOR','PHASE3C1-R1-RUNTIME-AUTHORITY-STORE-TRANSACTION-COORDINATOR-V1',NULL,0,NULL,1);
-- WRITER-REGISTRY-HASH-END

SELECT empty_sha256 FROM randle_sha256_preflight_v;

COMMIT;
