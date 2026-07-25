param()

$ErrorActionPreference = 'Stop'
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Utf8 = New-Object System.Text.UTF8Encoding($false, $true)
$Expectations = New-Object System.Collections.Generic.List[object]

function Get-LowerSha256 {
    param([byte[]]$Bytes)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Add-Expectation {
    param(
        [string]$CaseId,
        [string]$Classification,
        [string]$ResponseClass,
        [string]$Code,
        [string[]]$RequiredEvidence,
        [string[]]$RequiredEffects,
        [string[]]$ForbiddenEffects,
        [string]$RestartRetry,
        [string]$PublicClassification,
        [string]$Rationale
    )
    $Expectations.Add([pscustomobject][ordered]@{
        expectation_id = 'EXPECT-' + $CaseId
        case_id = $CaseId
        expected_terminal_classification = $Classification
        expected_response_class = $ResponseClass
        expected_result_code = $Code
        required_evidence = $RequiredEvidence
        required_durable_side_effects = $RequiredEffects
        forbidden_durable_side_effects = $ForbiddenEffects
        restart_retry_obligation = $RestartRetry
        expected_public_classification = $PublicClassification
        semantic_rationale = $Rationale
    })
}

function Add-ReadSuccess {
    param([string]$Id,[string]$Code,[string]$Classification,[string]$Rationale)
    Add-Expectation $Id $Classification 'COMPLETE' $Code `
        @('EXACT_REQUEST_FRAME','SERVER_CAPTURED_CALLER','EXACT_RESPONSE_FRAME','HELD_HANDLE_IDENTITIES') `
        @() @('LEDGER_APPEND','RECEIPT_WRITE','TRUST_WRITE','AUTHORITY_STATE_CHANGE') `
        'REPLAY_IS_READ_ONLY_AND_DETERMINISTIC' $Classification $Rationale
}

function Add-Rejection {
    param([string]$Id,[string]$Code,[string]$Rationale,[string[]]$Evidence=@('EXACT_REJECTED_FRAME','SERVER_CAPTURED_CALLER','NO_AUTHORITY_EFFECT_PROOF'))
    Add-Expectation $Id 'REJECTED_NONAUTHORITY' 'REJECTED' $Code $Evidence @() `
        @('TERMINAL_COMMIT','RECONCILIATION_COMMIT','UPGRADE_AUTHORIZATION','TRUST_WRITE','LEDGER_AUTHORITY_APPEND') `
        'IDENTICAL_RETRY_RETURNS_IDENTICAL_REJECTION' 'REJECTED_NONAUTHORITY' $Rationale
}

# This source intentionally does not read the case artifact, requirement registry, event,
# observation, comparator output, ledger, receipt store, or any current-run identity.
Add-ReadSuccess 'POS-001' 'AUTHORITY_HEALTHY' 'READ_ONLY_SUCCESS' 'Health resolves the measured active service without changing authority state.'
Add-ReadSuccess 'POS-002' 'PUBLIC_TRUST_RESOLVED' 'READ_ONLY_SUCCESS' 'Trust history resolves from public material only.'
Add-ReadSuccess 'POS-003' 'LEDGER_STATUS_RESOLVED' 'READ_ONLY_SUCCESS' 'Ledger status is derived from verified signed-chain bytes.'
Add-Expectation 'POS-004' 'REQUEST_RECEIVED_NONAUTHORITY' 'COMPLETE' 'REQUEST_RECEIVED' `
    @('EXACT_REQUEST_FRAME','SERVER_CAPTURED_CALLER','REQUEST_CONTENT_HASH','RESERVATION_ENTRY') `
    @('REQUEST_RECEIVED_ENTRY','RESERVED_ENTRY') @('TERMINAL_COMMIT_BEFORE_EVIDENCE_VALIDATION') `
    'SAME_IDENTITY_SAME_BYTES_RESOLVES_THE_RESERVATION' 'INCOMPLETE_ISSUANCE' 'Proposal submission alone cannot be terminal authority.'
Add-Expectation 'POS-005' 'VALID_NONAUTHORITATIVE_CANDIDATE_EVIDENCE' 'COMPLETE' 'CANDIDATE_GRAPH_RECORDED' `
    @('OUTER_INVOCATION','RAW_PROCESS_EVIDENCE','RAW_REQUEST_RESPONSE','RAW_SIDE_EFFECTS','SIGNER_REDERIVATION') `
    @('CANDIDATE_EVIDENCE_ENTRY') @('FRESH_TERMINAL_AUTHORITY','RECONCILIATION_COMMIT') `
    'SAME_GRAPH_IDENTITY_REPLAYS_THE_SAME_CANDIDATE_CLASSIFICATION' 'STRUCTURALLY_VALID_CANDIDATE_EVIDENCE' 'Candidate evidence is retained but cannot substitute for fresh authority.'
Add-Expectation 'POS-006' 'COMMITTED_AUTHORITATIVE_FRESH_RECEIPT' 'COMPLETE' 'TERMINAL_RECEIPT_COMMITTED' `
    @('OUTER_INVOCATION','RAW_PROCESS_EVIDENCE','RAW_REQUEST_RESPONSE','RAW_SIDE_EFFECTS','INDEPENDENT_EVENT','INDEPENDENT_OBSERVATION','COMPARATOR_RESULT','SIGNER_REDERIVATION','COMMIT_ENTRY') `
    @('RECEIPT_PREPARED_ENTRY','TERMINAL_COMMIT_ENTRY','CONTENT_ADDRESSED_RESPONSE') @('UNVERIFIED_CHILD_ASSERTION_AS_AUTHORITY') `
    'SAME_IDENTITY_SAME_BYTES_RECONSTRUCTS_IDENTICAL_COMMITTED_RESPONSE' 'VALID_AUTHORITATIVE_RECEIPT' 'Only independently rederived fresh evidence may commit terminal authority.'
Add-ReadSuccess 'POS-007' 'TERMINAL_RECEIPT_RESOLVED' 'READ_ONLY_SUCCESS' 'Retrieval resolves the committed receipt through signed ledger membership.'
Add-ReadSuccess 'POS-008' 'TERMINAL_RECEIPT_VALID' 'STRUCTURALLY_VALID_NONAUTHORITATIVE_BOOTSTRAP_EVIDENCE' 'Public verification validates a committed bootstrap receipt without promoting it to terminal authority; the complete fresh receipt is verified after graph commitment.'
Add-ReadSuccess 'POS-009' 'LEDGER_ENTRY_RESOLVED' 'READ_ONLY_SUCCESS' 'Lookup returns the exact signed entry and public chain proof.'
Add-Expectation 'POS-010' 'VALID_NONAUTHORITATIVE_BOOTSTRAP_RECONCILIATION' 'COMPLETE' 'RECONCILIATION_COMMITTED' `
    @('TWO_DISJOINT_VALID_GRAPHS','BOTH_TERMINAL_MEMBERSHIP_PROOFS','EXTERNAL_COMPARISON','COMMIT_ENTRY') `
    @('RECONCILIATION_PREPARED_ENTRY','RECONCILIATION_COMMIT_ENTRY','CONTENT_ADDRESSED_RESPONSE') @('RECONCILIATION_OF_UNCOMMITTED_OR_INVALID_GRAPH') `
    'SAME_IDENTITY_SAME_BYTES_RECONSTRUCTS_IDENTICAL_COMMITTED_RESPONSE' 'STRUCTURALLY_VALID_NONAUTHORITATIVE_BOOTSTRAP_RECONCILIATION' 'This non-circular seed proves the real reconciliation interface and disjoint committed membership without claiming the later full-graph reconciliation; the full reconciliation is independently verified after both complete runs commit.'
Add-ReadSuccess 'POS-011' 'RECONCILIATION_RESOLVED' 'READ_ONLY_SUCCESS' 'Retrieval resolves signed reconciliation membership.'
Add-ReadSuccess 'POS-012' 'RECONCILIATION_VALID' 'STRUCTURALLY_VALID_NONAUTHORITATIVE_BOOTSTRAP_RECONCILIATION' 'Public verification checks both committed bootstrap graphs and their comparison without promoting the seed receipt.'
Add-Expectation 'POS-013' 'REQUEST_RECEIVED_NONAUTHORITY' 'COMPLETE' 'REQUEST_RECEIVED' `
    @('REQUEST_IDENTITY','REQUEST_CONTENT_HASH','ORIGINAL_COMMIT','RECONSTRUCTED_RESPONSE_HASH') @() @('SECOND_COMMIT','MUTATED_RESPONSE') `
    'EVERY_RETRY_RETURNS_BYTE_IDENTICAL_RESPONSE' 'REQUEST_RECEIVED_NONAUTHORITY' 'The committed proposal response is reconstructed byte-identically without promoting proposal state to terminal authority.'
Add-ReadSuccess 'POS-014' 'CURRENT_RECEIPT_CLASSIFIED' 'STRUCTURALLY_VALID_NONAUTHORITATIVE_BOOTSTRAP_EVIDENCE' 'The committed bootstrap receipt resolves under the exact current service and policy version without circular promotion.'
Add-ReadSuccess 'POS-015' 'OLDEST_RECEIPT_CLASSIFIED' 'VERSION_RESOLVED_HISTORICAL_EVIDENCE' 'Oldest retained evidence is verified and classified under its issuance rules without global failure.'
Add-ReadSuccess 'POS-016' 'SEQUENCE_332_CLASSIFIED' 'INCOMPLETE_ISSUANCE_SUPERSEDED_NONAUTHORITY' 'Sequence 332 is preserved and permanently barred from reconciliation or reuse.'
Add-ReadSuccess 'POS-017' 'SEQUENCE_678_CLASSIFIED' 'ABORTED_CLIENT_REJECTED_ISSUANCE_NONAUTHORITY' 'Sequence 678 is preserved and its usable-attempt ambiguity is closed append-only.'
Add-Expectation 'POS-018' 'SERVICE_UNAVAILABLE_NONAUTHORITY' 'UNAVAILABLE' 'SERVICE_UNAVAILABLE' `
    @('PIPE_CONNECTION_FAILURE','SERVICE_STOPPED_STATE','NO_SIDE_EFFECT_PROOF') @() @('FALLBACK_AUTHORITY','LEDGER_APPEND','RECEIPT_WRITE') `
    'RETRY_REQUIRES_SERVICE_RETURN_AND_DOES_NOT_INFER_SUCCESS' 'NO_AUTHORITY_ISSUED' 'Clients fail closed when terminal authority is unavailable.'
Add-Expectation 'POS-019' 'REQUEST_RECEIVED_NONAUTHORITY' 'COMPLETE' 'REQUEST_RECEIVED' `
    @('COMMIT_ENTRY','RESTART_RECOVERY_PROOF','RECONSTRUCTED_RESPONSE_HASH') @('RESPONSE_AVAILABLE_ENTRY_IF_NOT_ALREADY_PRESENT') @('SECOND_TERMINAL_COMMIT') `
    'POST_RESTART_RETRY_IS_BYTE_IDENTICAL' 'REQUEST_RECEIVED_NONAUTHORITY' 'Durable ledger state reconstructs the exact nonauthority proposal response after restart.'
Add-ReadSuccess 'POS-020' 'UPGRADE_AUTHORITY_STATUS_RESOLVED' 'READ_ONLY_SUCCESS' 'Separate upgrade authority exposes only public status and history.'
Add-ReadSuccess 'POS-021' 'VERSION_HISTORY_RESOLVED' 'READ_ONLY_SUCCESS' 'Every transition, rollback, revocation, and service generation is publicly linked.'
Add-ReadSuccess 'POS-022' 'RECOVERY_STATE_RESOLVED' 'READ_ONLY_SUCCESS' 'Recovery state is derived from append-only transaction transitions.'

$AuthorityCodes = @{
    'AUT-001'='UNKNOWN_CLAUSE'; 'AUT-002'='PROHIBITED_AUTHORITY_SOURCE'; 'AUT-003'='CLAUSE_LOCATOR_MISMATCH';
    'AUT-004'='CLAUSE_HASH_MISMATCH'; 'AUT-005'='REQUIREMENT_COVERAGE_GAP'; 'AUT-006'='UNAUTHORIZED_NORMATIVE_CASE'
}
foreach ($id in $AuthorityCodes.Keys) { Add-Rejection $id $AuthorityCodes[$id] 'Normative authority must resolve to exact immutable governing clause bytes.' }

$ExpectationCodes = @{
    'EXP-001'='EXPECTED_FIELD_IN_EVENT_REJECTED'; 'EXP-002'='EXPECTED_FIELD_IN_OBSERVATION_REJECTED';
    'EXP-003'='EXPECTATION_ACL_ACCESS_DENIED'; 'EXP-004'='EXPECTATION_ACL_ACCESS_DENIED';
    'EXP-005'='SEMANTIC_STAGE_COUPLING_REJECTED'; 'EXP-006'='RAW_EVIDENCE_REQUIRED'
}
foreach ($id in $ExpectationCodes.Keys) {
    if ($id -eq 'EXP-003' -or $id -eq 'EXP-004') { Add-Rejection $id $ExpectationCodes[$id] 'Expected semantics cannot enter request, event, observation, or missing-evidence defaults.' @('CALLER_TOKEN','SERVER_DERIVED_OS_PROBE','ACCESS_DENIED_RESULT','UNCHANGED_OBJECT_HASH') }
    else { Add-Rejection $id $ExpectationCodes[$id] 'Expected semantics cannot enter request, event, observation, or missing-evidence defaults.' }
}

$SemanticCodes = @{
    'SEM-001'='OUTER_INTERFACE_NOT_INVOKED'; 'SEM-002'='OUTER_INTERFACE_NOT_INVOKED';
    'SEM-003'='RAW_FRAME_EVIDENCE_MISMATCH'; 'SEM-004'='RAW_SIDE_EFFECT_EVIDENCE_MISMATCH';
    'SEM-005'='LEDGER_MEMBERSHIP_NOT_RESOLVED'; 'SEM-006'='PROCESS_IDENTITY_MISMATCH';
    'SEM-007'='RAW_EVIDENCE_REQUIRED'; 'SEM-008'='INVALID_GRAPH_RECONCILIATION'; 'SEM-009'='REPLAY_WITHOUT_CURRENT_EVENTS'
}
foreach ($id in $SemanticCodes.Keys) { Add-Rejection $id $SemanticCodes[$id] 'Child summaries never establish disposition-determinative facts.' }

foreach ($id in 1..5 | ForEach-Object { 'PRI-{0:D3}' -f $_ }) {
    Add-Rejection $id 'OS_ACCESS_DENIED' 'The caller token has no key, ledger, trust, or receipt-store capability.' @('CALLER_TOKEN','OBJECT_ACL','ACCESS_DENIED_RESULT','UNCHANGED_OBJECT_HASH')
}
Add-Rejection 'PRI-006' 'CALLER_NOT_AUTHORIZED' 'Signer-only dispatch is denied before operation execution.'
Add-Rejection 'PRI-007' 'SIGNER_SID_EXCLUDED' 'The execution token must not contain the terminal signer SID.' @('EFFECTIVE_TOKEN_GROUPS','SIGNER_SID_ABSENCE')
Add-Rejection 'PRI-008' 'DESCENDANT_CAPABILITY_DENIED' 'A child cannot manufacture or inherit signer capability.' @('PARENT_TOKEN','DESCENDANT_TOKEN','KEY_AND_LEDGER_ACCESS_DENIAL')
Add-Expectation 'PRI-009' 'ISOLATION_PROVED' 'COMPLETE' 'NO_SIGNER_SEMANTIC_CHILD' `
    @('SIGNER_PROCESS_TREE','SERVICE_CONTROL_IDENTITY','EXECUTION_SERVICE_TOKEN') @() @('SIGNER_TOKEN_CHILD') `
    'RESTART_PRESERVES_SERVICE_IDENTITY_SEPARATION' 'BOUNDARY_CONTROL_VALID' 'The signer does not spawn semantic execution processes.'
foreach ($id in 10..14 | ForEach-Object { 'PRI-{0:D3}' -f $_ }) {
    Add-Rejection $id 'OS_ACCESS_DENIED' 'The signer independently repeats the hostile capability attempt under the authenticated child token and derives the denial from the OS.' @('CALLER_TOKEN','SERVER_DERIVED_OS_PROBE','ACCESS_DENIED_RESULT','UNCHANGED_OBJECT_HASH')
}
Add-Rejection 'PRI-015' 'CHILD_PROBE_REPORT_CONFLICT' 'A child-reported denial cannot override the signer server probe, which proves the public control file was readable.' @('CALLER_TOKEN','SERVER_DERIVED_OS_PROBE','CHILD_REPORT_CONFLICT','NO_AUTHORITY_EFFECT_PROOF')

$ParserCodes = @{
    'PAR-001'='DUPLICATE_KEY'; 'PAR-002'='DUPLICATE_KEY'; 'PAR-003'='DUPLICATE_KEY';
    'PAR-004'='TRAILING_BYTES'; 'PAR-005'='TRAILING_BYTES'; 'PAR-006'='TYPE_MISMATCH';
    'PAR-007'='NULL_NOT_ALLOWED'; 'PAR-008'='INVALID_UTF8'; 'PAR-009'='NON_CANONICAL_UNICODE';
    'PAR-011'='FRAME_TOO_LARGE'; 'PAR-012'='INCOMPLETE_FRAME'; 'PAR-013'='MULTIPLE_FRAMES';
    'PAR-014'='DUPLICATE_KEY'; 'PAR-015'='DUPLICATE_KEY'; 'PAR-016'='DUPLICATE_KEY';
    'PAR-017'='DUPLICATE_KEY'; 'PAR-018'='DUPLICATE_KEY'; 'PAR-019'='DUPLICATE_KEY'; 'PAR-020'='DUPLICATE_KEY'
}
foreach ($id in $ParserCodes.Keys) { Add-Rejection $id $ParserCodes[$id] 'Strict framed parsing rejects ambiguity before dispatch.' @('RAW_FRAME_BYTES','PARSER_REJECTION_OFFSET','NO_DISPATCH_PROOF','NO_AUTHORITY_EFFECT_PROOF') }
Add-Expectation 'PAR-010' 'FRAME_ACCEPTED_NONAUTHORITY' 'COMPLETE' 'FRAME_SIZE_ACCEPTED' `
    @('RAW_FRAME_SIZE_65536','COMPLETE_FRAME','STRICT_PARSE_RESULT') @() @('AUTHORITY_EFFECT_FROM_BOUNDARY_PROBE') `
    'IDENTICAL_BOUNDARY_FRAME_HAS_IDENTICAL_PARSE_RESULT' 'PROTOCOL_BOUNDARY_VALID' 'Exactly 65,536 total frame bytes, including the 12-byte header, are accepted when framing, canonical JSON, schema, and semantics are valid.'

Add-Rejection 'OUT-001' 'OPERATION_NOT_ALLOWED' 'Unknown operations are rejected by the actual outer dispatcher without authority effect.'
Add-Rejection 'OUT-002' 'RECEIPT_NOT_COMMITTED' 'An unresolved outer receipt locator cannot be used as committed authority.'
Add-Rejection 'OUT-003' 'TRUST_IDENTITY_MISMATCH' 'The outer identity verifier rejects a claimed trust identity that does not equal the governed public trust identity.'
Add-Rejection 'OUT-004' 'LEDGER_IDENTITY_MISMATCH' 'The outer identity verifier rejects a claimed ledger identity that does not equal the governed append-only ledger.'

Add-Expectation 'CON-001' 'CONCURRENCY_PROVED' 'COMPLETE' 'CONCURRENT_IDENTICAL_RETRY_RESOLVED' `
    @('OS_CONCURRENT_CONNECTIONS','TWO_SERVER_INTERACTIONS','ONE_TRANSACTION_STATE','BYTE_IDENTICAL_RESPONSE') @('ONE_NONAUTHORITY_PROPOSAL_TRANSACTION') @('SECOND_COMMIT','MUTATED_RESPONSE','FRESH_TERMINAL_AUTHORITY') `
    'CONCURRENT_SAME_IDENTITY_RETRY_IS_DETERMINISTIC' 'CONCURRENT_IDEMPOTENCE_PROVED' 'Two already-connected clients sending identical canonical bytes resolve one transaction and the same durable response.'
Add-Expectation 'CON-002' 'CONCURRENCY_PROVED' 'COMPLETE' 'CONCURRENT_CONFLICT_REJECTED' `
    @('OS_CONCURRENT_CONNECTIONS','TWO_SERVER_INTERACTIONS','ONE_TRANSACTION_STATE','ONE_COMMIT_ONE_CONFLICT') @('ONE_NONAUTHORITY_PROPOSAL_TRANSACTION') @('SECOND_COMMIT','FRESH_TERMINAL_AUTHORITY') `
    'CONCURRENT_SAME_IDENTITY_RETRY_IS_DETERMINISTIC' 'CONCURRENT_CONFLICT_PROVED' 'Two already-connected clients using one identity with different canonical bytes produce one nonauthority transaction and one conflict.'

$UpgradeCodes = @{
    'UPG-001'='UPGRADE_CALLER_NOT_AUTHORIZED'; 'UPG-002'='AUTHORIZATION_NOT_PREINSTALL';
    'UPG-003'='REVOKED_COMPONENT'; 'UPG-004'='DOWNGRADE_NOT_AUTHORIZED'; 'UPG-005'='POLICY_ROLLBACK';
    'UPG-006'='COMPONENT_SET_MISMATCH'; 'UPG-007'='CONFLICTING_UPGRADE_AUTHORIZATION_RETRY'; 'UPG-008'='HOST_BINDING_MISMATCH';
    'UPG-009'='INCOMPLETE_COMPONENT_SET'; 'UPG-010'='UNAUTHORIZED_COMPONENT_SET'
}
foreach ($id in $UpgradeCodes.Keys) { Add-Rejection $id $UpgradeCodes[$id] 'Only a prior one-time component-complete authorization from the separate upgrade authority can activate a service.' @('UPGRADE_REQUEST','CALLER_IDENTITY','UPGRADE_LEDGER_PROOF','ACTIVE_VERSION_UNCHANGED') }

Add-Rejection 'HIS-001' 'VERSION_RULE_MISMATCH' 'Historical evidence must be interpreted only by its resolved schema and policy version.'
Add-Expectation 'HIS-002' 'VERIFY_ALL_COMPLETE' 'COMPLETE' 'ALL_ENTRIES_CLASSIFIED' `
    @('ALL_CHAIN_SIGNATURES','VERSION_RESOLUTION_FOR_EACH_ENTRY','CLASSIFICATION_FOR_EACH_ENTRY') @() @('GLOBAL_FAILURE_FROM_LEGACY_CLASS') `
    'REPLAY_IS_DETERMINISTIC' 'MIXED_VERSION_HISTORY_VALID' 'Legacy evidence is classified rather than reinterpreted or allowed to fail the full chain.'
Add-Expectation 'HIS-003' 'RECOVERED' 'COMPLETE' 'CHECKPOINT_ADVANCED_BY_REPLAY' `
    @('STALE_VALID_CHECKPOINT','LATER_VALID_CHAIN','REPLAY_PROOF') @('ATOMIC_CHECKPOINT_REPLACEMENT','RECOVERY_ENTRY') @('LEDGER_REWRITE') `
    'SECOND_RECOVERY_IS_IDEMPOTENT' 'RECOVERED_CHECKPOINT' 'Valid later signed entries deterministically advance a stale checkpoint.'
Add-Expectation 'HIS-004' 'RECOVERED' 'COMPLETE' 'PARTIAL_CHECKPOINT_QUARANTINED' `
    @('INVALID_CHECKPOINT_BYTES','COMPLETE_LEDGER_CHAIN','LAST_VALID_CHECKPOINT') @('ATOMIC_CHECKPOINT_REPLACEMENT','RECOVERY_ENTRY') @('LEDGER_REWRITE') `
    'SECOND_RECOVERY_IS_IDEMPOTENT' 'RECOVERED_CHECKPOINT' 'A partial checkpoint is never accepted as state authority.'
Add-Expectation 'HIS-005' 'COMMITTED_RESPONSE_RECONSTRUCTED' 'COMPLETE' 'RESPONSE_RECONSTRUCTED' `
    @('COMMIT_ENTRY','RECEIPT_CONTENT','REQUEST_CONTENT_HASH') @('RESPONSE_AVAILABLE_ENTRY') @('ABORT_OF_COMMITTED_AUTHORITY','SECOND_COMMIT') `
    'RETRY_IS_BYTE_IDENTICAL' 'VALID_AUTHORITATIVE_RECEIPT' 'A committed receipt remains unambiguous despite response delivery failure.'
Add-Rejection 'HIS-006' 'ORPHAN_RESPONSE_NONAUTHORITY' 'A response without a commit has no authority and cannot be retrieved as committed.'
Add-Expectation 'HIS-007' 'ABORTED' 'COMPLETE' 'INCOMPLETE_RESERVATION_ABORTED' `
    @('RESERVATION_ENTRY','ABSENT_COMMIT','RECOVERY_POLICY') @('ABORT_ENTRY') @('TERMINAL_RECEIPT','RECONCILIATION_USE') `
    'RETRY_RETURNS_ABORT_CLASSIFICATION' 'ABORTED_ISSUANCE' 'Recovery closes an incomplete reservation append-only.'
Add-Rejection 'HIS-008' 'RECEIPT_NOT_COMMITTED' 'Reconciliation only consumes committed version-valid terminal receipts.'
Add-Rejection 'HIS-009' 'HISTORICAL_SEQUENCE_NONREUSABLE' 'Sequence 332 is preserved, superseded, and permanently nonauthoritative.'
Add-Rejection 'HIS-010' 'HISTORICAL_SEQUENCE_NONREUSABLE' 'Sequence 678 is preserved, aborted, and permanently nonauthoritative.'
Add-Expectation 'HIS-011' 'COMMITTED_RESPONSE_RECONSTRUCTED' 'COMPLETE' 'RESPONSE_RECONSTRUCTED' `
    @('COMMIT_ENTRY','CLIENT_DISCONNECT','REQUEST_CONTENT_HASH') @('RESPONSE_AVAILABLE_ENTRY') @('CLIENT_VISIBLE_REJECTION_CLASSIFICATION') `
    'RETRY_IS_BYTE_IDENTICAL' 'VALID_AUTHORITATIVE_RECEIPT' 'Disconnect after commit does not change committed authority semantics.'
Add-Expectation 'HIS-012' 'RECOVERED' 'COMPLETE' 'RECOVERY_RESUMED' `
    @('RECOVERY_TRANSITION_LOG','RESTART_BOUNDARY','FINAL_STATE_PROOF') @('RECOVERY_COMPLETION_ENTRY') @('DUPLICATE_AUTHORITY') `
    'ADDITIONAL_RESTART_IS_IDEMPOTENT' 'RECOVERED_TRANSACTION' 'Recovery itself is resumable from append-only state.'
Add-Rejection 'HIS-013' 'ILLEGAL_DUPLICATE_TRANSITION' 'Exactly one current governed terminal state exists for a request identity.'
Add-Rejection 'HIS-014' 'CONFLICTING_CLASSIFICATION' 'A later append cannot conflict with a final supersession or abort classification.'

foreach ($n in 1..12) {
    $id = 'PHY-{0:D3}' -f $n
    Add-Rejection $id 'UNSAFE_FILE_IDENTITY' 'Authority use requires a held no-follow handle with canonical path, volume, file ID, owner, ACL, links, streams, size, and content bound.' @('ATTACK_PATH','HELD_HANDLE_IDENTITY','REJECTION_REASON','NO_USE_PROOF')
}
foreach ($n in 13..16) {
    $id = 'PHY-{0:D3}' -f $n
    Add-Expectation $id 'DEPENDENCY_ABSENT' 'COMPLETE' 'REMOVED_FROM_AUTHORITY_PATH' `
        @('PROCESS_MODULE_SET','DEPENDENCY_MANIFEST','SOURCE_SCAN','RUNTIME_INVOCATION_SCAN') @() @('PYTHON_OR_GIT_AUTHORITY_INVOCATION') `
        'RESTART_LOAD_SET_REMAINS_CLOSED' 'DEPENDENCY_CLOSURE_VALID' 'Python and mutable machine-global Git are absent from disposition-determinative runtime.'
}
foreach ($n in 17..19) {
    $id = 'PHY-{0:D3}' -f $n
    Add-Rejection $id 'DEPENDENCY_IDENTITY_MISMATCH' 'Runtime and build dependencies are content-bound and substitutions fail before execution.' @('EXPECTED_MANIFEST','LOADED_OR_BUILD_IDENTITY','MISMATCH_PROOF','NO_AUTHORITY_EFFECT_PROOF')
}

$CrashExpectations = @{
    'CRS-001'=@('NO_STATE','NO_RESERVATION');
    'CRS-002'=@('ABORTED','RESERVATION_ABORTED');
    'CRS-003'=@('ABORTED','VALIDATED_TRANSACTION_ABORTED');
    'CRS-004'=@('ABORTED','PREPARED_TRANSACTION_ABORTED');
    'CRS-005'=@('ABORTED','UNCOMMITTED_RECEIPT_QUARANTINED');
    'CRS-006'=@('COMMITTED_RESPONSE_RECONSTRUCTED','RESPONSE_RECONSTRUCTED');
    'CRS-007'=@('RECOVERED','CHECKPOINT_ADVANCED_BY_REPLAY');
    'CRS-008'=@('RECOVERED','PARTIAL_CHECKPOINT_QUARANTINED');
    'CRS-009'=@('COMMITTED_RESPONSE_RECONSTRUCTED','RESPONSE_RECONSTRUCTED');
    'CRS-010'=@('ABORTED','RECONCILIATION_ABORTED');
    'CRS-011'=@('RECOVERED','CLASSIFICATION_TRANSITION_RECOVERED');
    'CRS-012'=@('RECOVERED','RECOVERY_RESUMED');
    'CRS-013'=@('FAILED_CLOSED','DURABLE_WRITE_FAILED');
    'CRS-014'=@('FAILED_CLOSED','ACCESS_DENIED');
    'CRS-015'=@('RECOVERED','PARTIAL_WRITE_REJECTED');
    'CRS-016'=@('FAILED_CLOSED','DIRECTORY_DURABILITY_FAILED');
    'CRS-017'=@('COMMITTED_RESPONSE_RECONSTRUCTED','RESPONSE_RECONSTRUCTED')
}
foreach ($id in $CrashExpectations.Keys) {
    $classification = $CrashExpectations[$id][0]
    $code = $CrashExpectations[$id][1]
    Add-Expectation $id $classification 'COMPLETE' $code `
        @('FAULT_POINT_PROOF','APPEND_ONLY_TRANSACTION_LOG','LEDGER_CHAIN_PROOF','CHECKPOINT_PROOF','RESTART_PROOF') `
        @('GOVERNED_RECOVERY_OR_ABORT_ENTRY_WHEN_STATE_EXISTS') @('LEDGER_REWRITE','HISTORY_DELETION','AMBIGUOUS_COMMIT') `
        'REPEATED_RECOVERY_IS_IDEMPOTENT' $classification 'Fault recovery derives exactly one state from durable append-only evidence.'
}

$TraceCodes = @{
    'TRC-001'='CIRCULAR_TRACE'; 'TRC-002'='EXECUTION_PROOF_MISSING'; 'TRC-003'='RAW_EVIDENCE_MISSING';
    'TRC-004'='PROVENANCE_MISSING'; 'TRC-005'='UNAUTHORIZED_DEPENDENCY';
    'TRC-006'='PROTECTED_APPROVAL_CLAIM'; 'TRC-007'='PROPOSAL_CANONICALITY_VIOLATION'
}
foreach ($id in $TraceCodes.Keys) { Add-Rejection $id $TraceCodes[$id] 'Trace and documentation claims must resolve bidirectionally to exact authority and raw execution evidence.' }

$Ids = @($Expectations | ForEach-Object case_id)
if ($Expectations.Count -lt 1) { throw 'no independently authored expectations were produced' }
if (@($Ids | Sort-Object -Unique).Count -ne $Ids.Count) { throw 'duplicate expectation case ID' }

$Artifact = [pscustomobject][ordered]@{
    artifact_type = 'R7_REMEDIATION_IMMUTABLE_EXPECTATIONS'
    schema_version = '1.0.0'
    authored_stage = 'EXPECTATION_AUTHORING_STAGE'
    case_artifact_read = $false
    requirement_registry_read = $false
    runtime_evidence_read = $false
    authored_before_execution = $true
    prohibited_source_commit = 'f0cfbce97e913a133530dd66a70326b1e03a0fb6'
    prohibited_source_reference_count = 0
    expectation_count = $Expectations.Count
    expectations = @($Expectations | Sort-Object case_id)
}
$Json = $Artifact | ConvertTo-Json -Depth 12
$Output = Join-Path $PackageRoot 'immutable_expectations.json'
[System.IO.File]::WriteAllText($Output, $Json + "`n", $Utf8)

$Serialized = [System.IO.File]::ReadAllText($Output, $Utf8)
foreach ($forbiddenName in @('actual_status','actual_code','observed_value','run_identity','process_id','session_identity')) {
    if ($Serialized -match ('"' + [regex]::Escape($forbiddenName) + '"\s*:')) { throw "forbidden runtime field in expectation artifact: $forbiddenName" }
}
[pscustomobject]@{
    expectation_count = $Expectations.Count
    case_artifact_read = $false
    requirement_registry_read = $false
    runtime_evidence_read = $false
    prohibited_source_reference_count = 0
    output_sha256 = Get-LowerSha256 -Bytes ([System.IO.File]::ReadAllBytes($Output))
} | ConvertTo-Json
