param()

$ErrorActionPreference = 'Stop'
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Utf8 = New-Object System.Text.UTF8Encoding($false, $true)
$RegistryPath = Join-Path $PackageRoot 'governed_requirement_registry.json'
$Registry = Get-Content -Raw -Encoding UTF8 -LiteralPath $RegistryPath | ConvertFrom-Json

function Get-LowerSha256 {
    param([byte[]]$Bytes)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}

$requirementsByCategory = @{}
foreach ($requirement in $Registry.requirements) {
    if (-not $requirementsByCategory.ContainsKey($requirement.control_category)) {
        $requirementsByCategory[$requirement.control_category] = New-Object System.Collections.Generic.List[object]
    }
    $requirementsByCategory[$requirement.control_category].Add($requirement)
}

$cases = New-Object System.Collections.Generic.List[object]

function Get-ObservedCallerRole([string]$Id, [string]$Driver) {
    if ($Driver -eq 'PUBLIC_VERIFIER') { return 'PUBLIC_VERIFIER' }
    if ($Id -eq 'EXP-002' -or $Id -eq 'EXP-004') { return 'OBSERVATION' }
    if ($Id -eq 'PRI-002' -or $Id -eq 'SEM-007') { return 'COMPARATOR' }
    if ($Id -eq 'EXP-001' -or $Id -eq 'EXP-003' -or $Id -eq 'EXP-005' -or $Id -eq 'EXP-006' -or $Id -eq 'PRI-006' -or $Id -like 'SEM-*' -or $Driver -eq 'ACL_PROBE' -or $Driver -eq 'TOKEN_PROBE' -or $Driver -eq 'SOURCE_PROBE' -or $Driver -eq 'RECOVERY_HARNESS') { return 'EXECUTION' }
    if ($Id -eq 'UPG-001') { return 'SIGNER' }
    return 'OPERATOR'
}

function Add-Case {
    param(
        [string]$Id,
        [string]$Title,
        [string]$Driver,
        [string]$Operation,
        [string]$CallerRole,
        [string[]]$Categories,
        [string]$Mutation,
        [string]$ImplementationSurface
    )
    $observedCallerRole = Get-ObservedCallerRole $Id $Driver
    if ($CallerRole -cne $observedCallerRole) { throw "caller role does not match the measured outer-interface process for $Id`: declared=$CallerRole observed=$observedCallerRole" }
    $authority = New-Object System.Collections.Generic.List[object]
    foreach ($category in $Categories) {
        if (-not $requirementsByCategory.ContainsKey($category)) { throw "unknown requirement category $category" }
        foreach ($requirement in $requirementsByCategory[$category]) {
            if (@($authority | Where-Object requirement_id -eq $requirement.requirement_id).Count -eq 0) {
                $authority.Add([pscustomobject][ordered]@{
                    requirement_id = $requirement.requirement_id
                    governing_commit = $requirement.governing_commit
                    governing_blob = $requirement.governing_blob
                    governing_path = $requirement.governing_path
                    line_range = $requirement.line_range
                    clause_raw_sha256 = $requirement.clause_raw_sha256
                    section_heading = $requirement.section_heading
                })
            }
        }
    }
    $cases.Add([pscustomobject][ordered]@{
        case_id = $Id
        title = $Title
        driver = $Driver
        operation = $Operation
        caller_role = $CallerRole
        authority_refs = $authority.ToArray()
        request_recipe = [pscustomobject][ordered]@{
            mutation = $Mutation
            include_expectation_fields = $false
            include_desired_result = $false
            dynamic_fields = @('request_nonce','session_identity','case_token')
        }
        evidence_requirements = @(
            'RAW_FRAME_BYTES',
            'CALLER_PROCESS_IDENTITY',
            'CALLER_TOKEN_IDENTITY',
            'SERVER_RESPONSE_BYTES',
            'LEDGER_BEFORE_AFTER',
            'RECEIPT_STORE_BEFORE_AFTER',
            'FILESYSTEM_SIDE_EFFECT_SNAPSHOT'
        )
        implementation_surface = $ImplementationSurface
        actual_derivation_source = 'CURRENT_RUN_RAW_OS_AND_INTERFACE_EVIDENCE_ONLY'
    })
}

$positive = @(
    @('POS-001','Health lookup','PUBLIC_PIPE','GET_HEALTH','OPERATOR','OUTER,TRUST','NONE','TERMINAL_PIPE'),
    @('POS-002','Public trust lookup','PUBLIC_PIPE','GET_PUBLIC_TRUST','OPERATOR','TRUST,OUTER','NONE','TERMINAL_PIPE'),
    @('POS-003','Ledger status lookup','PUBLIC_PIPE','GET_LEDGER_STATUS','OPERATOR','STATE,HISTORY,OUTER','NONE','TERMINAL_PIPE'),
    @('POS-004','Terminal proposal submission','PUBLIC_PIPE','SUBMIT_TERMINAL_PROPOSAL','OPERATOR','STATE,OUTER','NONE','TERMINAL_PIPE'),
    @('POS-005','Candidate execution submission','PUBLIC_PIPE','SUBMIT_RUN_GRAPH','OPERATOR','OBSERVATION,COMPARATOR,OUTER','CANDIDATE_GRAPH','TERMINAL_PIPE'),
    @('POS-006','Fresh execution submission','PUBLIC_PIPE','SUBMIT_RUN_GRAPH','OPERATOR','OBSERVATION,COMPARATOR,OUTER','FRESH_GRAPH','TERMINAL_PIPE'),
    @('POS-007','Terminal receipt retrieval','PUBLIC_PIPE','GET_TERMINAL_RECEIPT','OPERATOR','OUTER,STATE','CURRENT_LOCATOR','TERMINAL_PIPE'),
    @('POS-008','Committed receipt structural public verification','PUBLIC_VERIFIER','VERIFY_TERMINAL_RECEIPT','PUBLIC_VERIFIER','TRUST,HISTORY,OUTER','COMMITTED_BOOTSTRAP_LOCATOR','PUBLIC_VERIFIER'),
    @('POS-009','Ledger entry lookup','PUBLIC_PIPE','GET_LEDGER_ENTRY','OPERATOR','STATE,HISTORY,OUTER','CURRENT_SEQUENCE','TERMINAL_PIPE'),
    @('POS-010','Structurally valid bootstrap reconciliation submission','PUBLIC_PIPE','SUBMIT_RECONCILIATION','OPERATOR','COMPARATOR,STATE,OUTER','DISTINCT_COMMITTED_BOOTSTRAP_LOCATORS','TERMINAL_PIPE'),
    @('POS-011','Reconciliation retrieval','PUBLIC_PIPE','GET_RECONCILIATION','OPERATOR','OUTER,STATE','CURRENT_LOCATOR','TERMINAL_PIPE'),
    @('POS-012','Committed bootstrap reconciliation structural verification','PUBLIC_VERIFIER','VERIFY_RECONCILIATION','PUBLIC_VERIFIER','COMPARATOR,TRUST,HISTORY','COMMITTED_BOOTSTRAP_LOCATOR','PUBLIC_VERIFIER'),
    @('POS-013','Idempotent retry','PUBLIC_PIPE','RETRY_REQUEST','OPERATOR','STATE,OUTER','SAME_IDENTITY_SAME_BYTES','TERMINAL_PIPE'),
    @('POS-014','Committed version-resolved receipt classification','PUBLIC_VERIFIER','CLASSIFY_RECEIPT','PUBLIC_VERIFIER','HISTORY,TRUST','COMMITTED_BOOTSTRAP_RECEIPT','PUBLIC_VERIFIER'),
    @('POS-015','Oldest historical receipt classification','PUBLIC_VERIFIER','CLASSIFY_RECEIPT','PUBLIC_VERIFIER','HISTORY,TRUST','OLDEST_RETAINED_RECEIPT','PUBLIC_VERIFIER'),
    @('POS-016','Sequence 332 classification lookup','PUBLIC_VERIFIER','CLASSIFY_LEDGER_SEQUENCE','PUBLIC_VERIFIER','HISTORY,STATE','SEQUENCE_332','PUBLIC_VERIFIER'),
    @('POS-017','Sequence 678 classification lookup','PUBLIC_VERIFIER','CLASSIFY_LEDGER_SEQUENCE','PUBLIC_VERIFIER','HISTORY,STATE','SEQUENCE_678','PUBLIC_VERIFIER'),
    @('POS-018','Service unavailable fail-closed lookup','SERVICE_CONTROL','GET_HEALTH','OPERATOR','OUTER,STATE','SERVICE_STOPPED','TERMINAL_PIPE'),
    @('POS-019','Committed response reconstruction after restart','SERVICE_CONTROL','RETRY_REQUEST','OPERATOR','STATE,HISTORY','RESTART_THEN_RETRY','TERMINAL_PIPE'),
    @('POS-020','Upgrade authority status lookup','UPGRADE_PIPE','GET_UPGRADE_STATUS','OPERATOR','UPGRADE,TRUST','NONE','UPGRADE_PIPE'),
    @('POS-021','Version history lookup','PUBLIC_VERIFIER','GET_VERSION_HISTORY','PUBLIC_VERIFIER','UPGRADE,HISTORY,TRUST','FULL_HISTORY','PUBLIC_VERIFIER'),
    @('POS-022','Recovery state lookup','PUBLIC_PIPE','GET_RECOVERY_STATE','OPERATOR','STATE,HISTORY','CURRENT_STATE','TERMINAL_PIPE')
)

$authorityAttacks = @(
    @('AUT-001','Nonexistent governing clause','AUTHORITY_VERIFIER','VERIFY_CASE_AUTHORITY','OPERATOR','TRACE,CANONICAL','NONEXISTENT_CLAUSE','AUTHORITY_REGISTRY'),
    @('AUT-002','Discarded object citation','AUTHORITY_VERIFIER','VERIFY_CASE_AUTHORITY','OPERATOR','TRACE,TRUST','PROHIBITED_F0_CITATION','AUTHORITY_REGISTRY'),
    @('AUT-003','Correct object wrong section','AUTHORITY_VERIFIER','VERIFY_CASE_AUTHORITY','OPERATOR','TRACE','WRONG_SECTION','AUTHORITY_REGISTRY'),
    @('AUT-004','Changed clause text with claimed identity','AUTHORITY_VERIFIER','VERIFY_CASE_AUTHORITY','OPERATOR','TRACE,CANONICAL','CLAUSE_TEXT_MUTATION','AUTHORITY_REGISTRY'),
    @('AUT-005','Requirement omitted from case registry','AUTHORITY_VERIFIER','VERIFY_COVERAGE','OPERATOR','TRACE','OMIT_REQUIREMENT','AUTHORITY_REGISTRY'),
    @('AUT-006','Unauthorized extra normative case','AUTHORITY_VERIFIER','VERIFY_COVERAGE','OPERATOR','TRACE,TRUST','EXTRA_UNAUTHORIZED_CASE','AUTHORITY_REGISTRY')
)

$expectationAttacks = @(
    @('EXP-001','Expected status injected into event request','SEMANTIC_PROBE','SUBMIT_RUN_GRAPH','EXECUTION','SEPARATION,OBSERVATION','EVENT_REQUEST_EXPECTED_STATUS','TERMINAL_PIPE'),
    @('EXP-002','Expected code copied to observation','SEMANTIC_PROBE','SUBMIT_RUN_GRAPH','OBSERVATION','SEPARATION,OBSERVATION','OBSERVATION_EXPECTED_CODE','TERMINAL_PIPE'),
    @('EXP-003','Event producer expectation-path access','ACL_PROBE','OPEN_EXPECTATION','EXECUTION','SEPARATION,PATH','EVENT_PRODUCER_READ_EXPECTATION','OS_BOUNDARY'),
    @('EXP-004','Observation producer expectation-path access','ACL_PROBE','OPEN_EXPECTATION','OBSERVATION','SEPARATION,PATH','OBSERVER_READ_EXPECTATION','OS_BOUNDARY'),
    @('EXP-005','Shared expected and actual semantic builder','SEMANTIC_PROBE','VERIFY_GENERATOR_SEPARATION','EXECUTION','SEPARATION,COMPARATOR','SHARED_SEMANTIC_BUILDER','SEMANTIC_VERIFIER'),
    @('EXP-006','Missing actual evidence defaults to expected value','SEMANTIC_PROBE','SUBMIT_RUN_GRAPH','EXECUTION','OBSERVATION,COMPARATOR','MISSING_ACTUAL_DEFAULT','TERMINAL_PIPE')
)

$semanticAttacks = @(
    @('SEM-001','Inner fixture passes while outer submission fails','PUBLIC_PIPE','SUBMIT_RUN_GRAPH','EXECUTION','OUTER','INNER_PASS_OUTER_NOT_INVOKED','TERMINAL_PIPE'),
    @('SEM-002','Worker returns PASS without outer invocation','PUBLIC_PIPE','SUBMIT_RUN_GRAPH','EXECUTION','OUTER,OBSERVATION','WORKER_PASS_ZERO_INVOCATION','TERMINAL_PIPE'),
    @('SEM-003','Fabricated request and response evidence','PUBLIC_PIPE','SUBMIT_RUN_GRAPH','EXECUTION','OUTER,OBSERVATION','FABRICATED_REQUEST_RESPONSE','TERMINAL_PIPE'),
    @('SEM-004','Fabricated side effects','PUBLIC_PIPE','SUBMIT_RUN_GRAPH','EXECUTION','OUTER,OBSERVATION','FABRICATED_SIDE_EFFECTS','TERMINAL_PIPE'),
    @('SEM-005','Fabricated receipt membership','PUBLIC_PIPE','SUBMIT_RUN_GRAPH','EXECUTION','STATE,OUTER','FABRICATED_RECEIPT_MEMBERSHIP','TERMINAL_PIPE'),
    @('SEM-006','Fabricated process identity','PUBLIC_PIPE','SUBMIT_RUN_GRAPH','EXECUTION','SEPARATION,OBSERVATION','FABRICATED_PROCESS_IDENTITY','TERMINAL_PIPE'),
    @('SEM-007','Matching comparator summaries with missing raw evidence','PUBLIC_PIPE','SUBMIT_RUN_GRAPH','COMPARATOR','COMPARATOR,OBSERVATION','SUMMARY_ONLY_COMPARISON','TERMINAL_PIPE'),
    @('SEM-008','Two invalid graphs reconcile','PUBLIC_PIPE','SUBMIT_RECONCILIATION','EXECUTION','COMPARATOR,STATE','TWO_INVALID_GRAPHS','TERMINAL_PIPE'),
    @('SEM-009','Replaceable supervisor complete replay with zero events','PUBLIC_PIPE','SUBMIT_RUN_GRAPH','EXECUTION','OUTER,STATE','SUPERVISOR_REPLAY_ZERO_EVENTS','TERMINAL_PIPE')
)

$principalAttacks = @(
    @('PRI-001','Execution child opens terminal key','ACL_PROBE','OPEN_TERMINAL_KEY','EXECUTION','SEPARATION,TRUST','DIRECT_KEY_OPEN','OS_BOUNDARY'),
    @('PRI-002','Comparator opens terminal key','ACL_PROBE','OPEN_TERMINAL_KEY','COMPARATOR','SEPARATION,TRUST','DIRECT_KEY_OPEN','OS_BOUNDARY'),
    @('PRI-003','Execution child appends ledger','ACL_PROBE','APPEND_TERMINAL_LEDGER','EXECUTION','SEPARATION,STATE','DIRECT_LEDGER_APPEND','OS_BOUNDARY'),
    @('PRI-004','Execution child writes trust','ACL_PROBE','WRITE_TERMINAL_TRUST','EXECUTION','SEPARATION,TRUST','DIRECT_TRUST_WRITE','OS_BOUNDARY'),
    @('PRI-005','Execution child writes receipt','ACL_PROBE','WRITE_TERMINAL_RECEIPT','EXECUTION','SEPARATION,STATE','DIRECT_RECEIPT_WRITE','OS_BOUNDARY'),
    @('PRI-006','Execution child invokes signer-only operation','PUBLIC_PIPE','SIGNER_ONLY_OPERATION','EXECUTION','SEPARATION,TRUST','SIGNER_ONLY_CALL','TERMINAL_PIPE'),
    @('PRI-007','Execution token contains signer SID','TOKEN_PROBE','VERIFY_TOKEN','EXECUTION','SEPARATION','SIGNER_SID_MEMBERSHIP','OS_BOUNDARY'),
    @('PRI-008','Execution child spawns signer-capable descendant','TOKEN_PROBE','SPAWN_DESCENDANT','EXECUTION','SEPARATION','DESCENDANT_CAPABILITY','OS_BOUNDARY'),
    @('PRI-009','Signer launches semantic child with signer token','SOURCE_PROBE','VERIFY_NO_SIGNER_CHILD_LAUNCH','EXECUTION','SEPARATION','SIGNER_PROCESS_CREATION','SOURCE_AND_RUNTIME'),
    @('PRI-010','Execution child signs arbitrary bytes','ACL_PROBE','SIGN_ARBITRARY_BYTES','EXECUTION','SEPARATION,TRUST','SIGN_ARBITRARY_BYTES','OS_BOUNDARY'),
    @('PRI-011','Execution child opens upgrade-authority key','ACL_PROBE','OPEN_UPGRADE_KEY','EXECUTION','SEPARATION,TRUST,UPGRADE','DIRECT_UPGRADE_KEY_OPEN','OS_BOUNDARY'),
    @('PRI-012','Execution child replaces a retained receipt','ACL_PROBE','REPLACE_TERMINAL_RECEIPT','EXECUTION','SEPARATION,STATE','DIRECT_RECEIPT_REPLACE','OS_BOUNDARY'),
    @('PRI-013','Execution child replaces server evidence','ACL_PROBE','REPLACE_TERMINAL_EVIDENCE','EXECUTION','SEPARATION,OBSERVATION','DIRECT_EVIDENCE_REPLACE','OS_BOUNDARY'),
    @('PRI-014','Execution child impersonates terminal signer','TOKEN_PROBE','IMPERSONATE_TERMINAL_SIGNER','EXECUTION','SEPARATION,TRUST','IMPERSONATE_SIGNER','OS_BOUNDARY'),
    @('PRI-015','Child fabricates access denial for a readable control','ACL_PROBE','FABRICATE_ACCESS_DENIAL','EXECUTION','SEPARATION,OBSERVATION','CONTROL_PUBLIC_TRUST_READ','OS_BOUNDARY')
)

$parserAttacks = @(
    @('PAR-001','Duplicate operation key','RAW_FRAME','GET_HEALTH','OPERATOR','CANONICAL,OUTER','DUPLICATE_OPERATION','TERMINAL_PIPE'),
    @('PAR-002','Duplicate nonce key','RAW_FRAME','GET_HEALTH','OPERATOR','CANONICAL','DUPLICATE_NONCE','TERMINAL_PIPE'),
    @('PAR-003','Duplicate nested evidence key','RAW_FRAME','SUBMIT_RUN_GRAPH','OPERATOR','CANONICAL','DUPLICATE_NESTED_EVIDENCE','TERMINAL_PIPE'),
    @('PAR-004','First-object second-object ambiguity','RAW_FRAME','GET_HEALTH','OPERATOR','CANONICAL','TWO_JSON_OBJECTS','TERMINAL_PIPE'),
    @('PAR-005','Trailing JSON bytes','RAW_FRAME','GET_HEALTH','OPERATOR','CANONICAL','TRAILING_JSON','TERMINAL_PIPE'),
    @('PAR-006','Numeric string coercion','RAW_FRAME','GET_LEDGER_ENTRY','OPERATOR','CANONICAL','NUMERIC_STRING','TERMINAL_PIPE'),
    @('PAR-007','Null absent ambiguity','RAW_FRAME','GET_TERMINAL_RECEIPT','OPERATOR','CANONICAL','NULL_INSTEAD_OF_ABSENT','TERMINAL_PIPE'),
    @('PAR-008','Invalid UTF-8','RAW_FRAME','GET_HEALTH','OPERATOR','CANONICAL','INVALID_UTF8','TERMINAL_PIPE'),
    @('PAR-009','Unicode normalization collision','RAW_FRAME','GET_TERMINAL_RECEIPT','OPERATOR','CANONICAL','NON_NFC_IDENTIFIER','TERMINAL_PIPE'),
    @('PAR-010','Exact 65536-byte complete frame','RAW_FRAME','FRAME_BOUNDARY','OPERATOR','CANONICAL','FRAME_65536','TERMINAL_PIPE'),
    @('PAR-011','Exact 65537-byte complete frame','RAW_FRAME','FRAME_BOUNDARY','OPERATOR','CANONICAL','FRAME_65537','TERMINAL_PIPE'),
    @('PAR-012','Partial frame','RAW_FRAME','FRAME_BOUNDARY','OPERATOR','CANONICAL','PARTIAL_FRAME','TERMINAL_PIPE'),
    @('PAR-013','Multiple frames in one pipe message','RAW_FRAME','GET_HEALTH','OPERATOR','CANONICAL','MULTIPLE_FRAMES','TERMINAL_PIPE'),
    @('PAR-014','Duplicate protocol version key','RAW_FRAME','GET_HEALTH','OPERATOR','CANONICAL','DUPLICATE_VERSION','TERMINAL_PIPE'),
    @('PAR-015','Duplicate payload key','RAW_FRAME','GET_HEALTH','OPERATOR','CANONICAL','DUPLICATE_PAYLOAD','TERMINAL_PIPE'),
    @('PAR-016','Duplicate receipt locator key','RAW_FRAME','GET_TERMINAL_RECEIPT','OPERATOR','CANONICAL,STATE','DUPLICATE_RECEIPT_LOCATOR','TERMINAL_PIPE'),
    @('PAR-017','Duplicate ledger identity key','RAW_FRAME','VERIFY_PUBLIC_IDENTITY','OPERATOR','CANONICAL,STATE','DUPLICATE_LEDGER_IDENTITY','TERMINAL_PIPE'),
    @('PAR-018','Duplicate trust identity key','RAW_FRAME','VERIFY_PUBLIC_IDENTITY','OPERATOR','CANONICAL,TRUST','DUPLICATE_TRUST_IDENTITY','TERMINAL_PIPE'),
    @('PAR-019','Duplicate case identity key','RAW_FRAME','VERIFY_CASE_AUTHORITY','OPERATOR','CANONICAL,TRACE','DUPLICATE_CASE_IDENTITY','TERMINAL_PIPE'),
    @('PAR-020','Duplicate expectation identity key','RAW_FRAME','SUBMIT_RUN_GRAPH','OPERATOR','CANONICAL,SEPARATION','DUPLICATE_EXPECTATION_IDENTITY','TERMINAL_PIPE')
)

$outerInterfaceAttacks = @(
    @('OUT-001','Invalid outer operation','PUBLIC_PIPE','UNKNOWN_OPERATION','OPERATOR','OUTER','INVALID_OPERATION','TERMINAL_PIPE'),
    @('OUT-002','Invalid receipt locator','PUBLIC_PIPE','GET_TERMINAL_RECEIPT','OPERATOR','OUTER,STATE','INVALID_RECEIPT_LOCATOR','TERMINAL_PIPE'),
    @('OUT-003','Invalid public trust identity','PUBLIC_PIPE','VERIFY_PUBLIC_IDENTITY','OPERATOR','OUTER,TRUST','INVALID_TRUST_IDENTITY','TERMINAL_PIPE'),
    @('OUT-004','Invalid public ledger identity','PUBLIC_PIPE','VERIFY_PUBLIC_IDENTITY','OPERATOR','OUTER,STATE','INVALID_LEDGER_IDENTITY','TERMINAL_PIPE')
)

$concurrencyAttacks = @(
    @('CON-001','Concurrent identical request retry','CONCURRENCY_PROBE','VERIFY_CONCURRENT_INTERACTIONS','OPERATOR','STATE,OUTER','CONCURRENT_IDENTICAL_RETRY','TERMINAL_PIPE'),
    @('CON-002','Concurrent conflicting bytes under one request identity','CONCURRENCY_PROBE','VERIFY_CONCURRENT_INTERACTIONS','OPERATOR','STATE,OUTER','CONCURRENT_CONFLICTING_BYTES','TERMINAL_PIPE')
)

$upgradeAttacks = @(
    @('UPG-001','Terminal service signs its own upgrade','UPGRADE_PIPE','AUTHORIZE_TERMINAL_UPGRADE','SIGNER','UPGRADE,SEPARATION','SELF_AUTHORIZATION','UPGRADE_PIPE'),
    @('UPG-002','Upgrade authorization created after installation','UPGRADE_PIPE','AUTHORIZE_TERMINAL_UPGRADE','OPERATOR','UPGRADE','POST_INSTALL_AUTHORIZATION','UPGRADE_PIPE'),
    @('UPG-003','Rejected v3 binary reinstall','UPGRADE_PIPE','AUTHORIZE_TERMINAL_UPGRADE','OPERATOR','UPGRADE','REJECTED_V3_REINSTALL','UPGRADE_PIPE'),
    @('UPG-004','Version 1 downgrade','UPGRADE_PIPE','AUTHORIZE_TERMINAL_UPGRADE','OPERATOR','UPGRADE','V1_DOWNGRADE','UPGRADE_PIPE'),
    @('UPG-005','Policy-only downgrade','UPGRADE_PIPE','AUTHORIZE_TERMINAL_UPGRADE','OPERATOR','UPGRADE','POLICY_DOWNGRADE','UPGRADE_PIPE'),
    @('UPG-006','Worker substitution','UPGRADE_PIPE','AUTHORIZE_TERMINAL_UPGRADE','OPERATOR','UPGRADE,DEPENDENCY','WORKER_SUBSTITUTION','UPGRADE_PIPE'),
    @('UPG-007','Conflicting replay of an issued transition nonce','UPGRADE_PIPE','AUTHORIZE_TERMINAL_UPGRADE','OPERATOR','UPGRADE,STATE','REPLAY_AUTHORIZATION','UPGRADE_PIPE'),
    @('UPG-008','Authorization for another host','UPGRADE_PIPE','AUTHORIZE_TERMINAL_UPGRADE','OPERATOR','UPGRADE','OTHER_HOST','UPGRADE_PIPE'),
    @('UPG-009','Missing component in upgrade set','UPGRADE_PIPE','AUTHORIZE_TERMINAL_UPGRADE','OPERATOR','UPGRADE,DEPENDENCY','OMIT_COMPONENT','UPGRADE_PIPE'),
    @('UPG-010','Unauthorized component role submitted for signing','UPGRADE_PIPE','AUTHORIZE_TERMINAL_UPGRADE','OPERATOR','UPGRADE,TRUST','UNAUTHORIZED_COMPONENT_SET','UPGRADE_PIPE')
)

$historyAttacks = @(
    @('HIS-001','Historical receipt interpreted by wrong version verifier','PUBLIC_VERIFIER','CLASSIFY_RECEIPT','PUBLIC_VERIFIER','HISTORY','WRONG_VERSION_RULE','PUBLIC_VERIFIER'),
    @('HIS-002','Old receipt causes verify-all failure','PUBLIC_VERIFIER','VERIFY_ALL','PUBLIC_VERIFIER','HISTORY','LEGACY_RECEIPT_PRESENT','PUBLIC_VERIFIER'),
    @('HIS-003','Stale checkpoint with valid later entries','RECOVERY_HARNESS','RECOVER_LEDGER','EXECUTION','STATE,HISTORY','STALE_CHECKPOINT','RECOVERY_ENGINE'),
    @('HIS-004','Partial checkpoint','RECOVERY_HARNESS','RECOVER_LEDGER','EXECUTION','STATE','PARTIAL_CHECKPOINT','RECOVERY_ENGINE'),
    @('HIS-005','Commit without response','RECOVERY_HARNESS','RECOVER_TRANSACTION','EXECUTION','STATE','COMMIT_NO_RESPONSE','RECOVERY_ENGINE'),
    @('HIS-006','Response without commit','RECOVERY_HARNESS','RECOVER_TRANSACTION','EXECUTION','STATE','RESPONSE_NO_COMMIT','RECOVERY_ENGINE'),
    @('HIS-007','Reservation without completion','RECOVERY_HARNESS','RECOVER_TRANSACTION','EXECUTION','STATE,HISTORY','INCOMPLETE_RESERVATION','RECOVERY_ENGINE'),
    @('HIS-008','Reconciliation against uncommitted receipt','PUBLIC_PIPE','SUBMIT_RECONCILIATION','OPERATOR','STATE,COMPARATOR','UNCOMMITTED_RECEIPT','TERMINAL_PIPE'),
    @('HIS-009','Sequence 332 reuse','PUBLIC_PIPE','SUBMIT_RUN_GRAPH','OPERATOR','HISTORY,STATE','REUSE_SEQUENCE_332','TERMINAL_PIPE'),
    @('HIS-010','Sequence 678 ambiguity reuse','PUBLIC_PIPE','SUBMIT_RUN_GRAPH','OPERATOR','HISTORY,STATE','REUSE_SEQUENCE_678','TERMINAL_PIPE'),
    @('HIS-011','Client disconnect after commit','RECOVERY_HARNESS','RECOVER_TRANSACTION','EXECUTION','STATE','DISCONNECT_AFTER_COMMIT','RECOVERY_ENGINE'),
    @('HIS-012','Restart during recovery','RECOVERY_HARNESS','RECOVER_TRANSACTION','EXECUTION','STATE,HISTORY','RESTART_DURING_RECOVERY','RECOVERY_ENGINE'),
    @('HIS-013','Duplicate completion','RECOVERY_HARNESS','RECOVER_TRANSACTION','EXECUTION','STATE','DUPLICATE_COMPLETION','RECOVERY_ENGINE'),
    @('HIS-014','Conflicting supersession','PUBLIC_PIPE','SUBMIT_HISTORY_CLASSIFICATION','OPERATOR','HISTORY,STATE','CONFLICTING_SUPERSESSION','TERMINAL_PIPE')
)

$physicalAttacks = @(
    @('PHY-001','Junction substitution','PATH_PROBE','OPEN_AUTHORITY_FILE','OPERATOR','PATH','JUNCTION_SUBSTITUTION','SAFE_FILE'),
    @('PHY-002','Symlink substitution','PATH_PROBE','OPEN_AUTHORITY_FILE','OPERATOR','PATH','SYMLINK_SUBSTITUTION','SAFE_FILE'),
    @('PHY-003','Hard-link substitution','PATH_PROBE','OPEN_AUTHORITY_FILE','OPERATOR','PATH','HARDLINK_SUBSTITUTION','SAFE_FILE'),
    @('PHY-004','Alternate data stream','PATH_PROBE','OPEN_AUTHORITY_FILE','OPERATOR','PATH','ALTERNATE_DATA_STREAM','SAFE_FILE'),
    @('PHY-005','8.3 alias','PATH_PROBE','OPEN_AUTHORITY_FILE','OPERATOR','PATH','SHORT_NAME_ALIAS','SAFE_FILE'),
    @('PHY-006','Case alias','PATH_PROBE','OPEN_AUTHORITY_FILE','OPERATOR','PATH','CASE_ALIAS','SAFE_FILE'),
    @('PHY-007','Rename between hash and use','PATH_PROBE','OPEN_AUTHORITY_FILE','OPERATOR','PATH','RENAME_RACE','SAFE_FILE'),
    @('PHY-008','Replacement after measurement','PATH_PROBE','OPEN_AUTHORITY_FILE','OPERATOR','PATH','READ_AFTER_HASH_REPLACEMENT','SAFE_FILE'),
    @('PHY-009','Copied evidence root','PATH_PROBE','OPEN_EVIDENCE','OPERATOR','PATH,HISTORY','COPIED_EVIDENCE_ROOT','SAFE_FILE'),
    @('PHY-010','Stale evidence subtree','PATH_PROBE','OPEN_EVIDENCE','OPERATOR','PATH,HISTORY','STALE_EVIDENCE_SUBTREE','SAFE_FILE'),
    @('PHY-011','Alternate volume','PATH_PROBE','OPEN_AUTHORITY_FILE','OPERATOR','PATH','ALTERNATE_VOLUME','SAFE_FILE'),
    @('PHY-012','Directory-entry race','PATH_PROBE','OPEN_AUTHORITY_FILE','OPERATOR','PATH','DIRECTORY_ENTRY_RACE','SAFE_FILE'),
    @('PHY-013','Python user-site import','DEPENDENCY_PROBE','VERIFY_NO_PYTHON','OPERATOR','DEPENDENCY','PYTHON_USER_SITE','DEPENDENCY_VERIFIER'),
    @('PHY-014','Python current-directory import','DEPENDENCY_PROBE','VERIFY_NO_PYTHON','OPERATOR','DEPENDENCY','PYTHON_CURRENT_DIRECTORY','DEPENDENCY_VERIFIER'),
    @('PHY-015','Unmanifested Python module','DEPENDENCY_PROBE','VERIFY_NO_PYTHON','OPERATOR','DEPENDENCY','UNMANIFESTED_MODULE','DEPENDENCY_VERIFIER'),
    @('PHY-016','Global Git replacement','DEPENDENCY_PROBE','VERIFY_NO_RUNTIME_GIT','OPERATOR','DEPENDENCY','GLOBAL_GIT_REPLACEMENT','DEPENDENCY_VERIFIER'),
    @('PHY-017','Framework assembly replacement','DEPENDENCY_PROBE','VERIFY_RUNTIME_MODULES','OPERATOR','DEPENDENCY','FRAMEWORK_ASSEMBLY_REPLACEMENT','DEPENDENCY_VERIFIER'),
    @('PHY-018','DLL side-loading','DEPENDENCY_PROBE','VERIFY_RUNTIME_MODULES','OPERATOR','DEPENDENCY','DLL_SIDELOAD','DEPENDENCY_VERIFIER'),
    @('PHY-019','Compiler reference substitution','DEPENDENCY_PROBE','VERIFY_BUILD_RECEIPT','OPERATOR','DEPENDENCY','COMPILER_REFERENCE_SUBSTITUTION','DEPENDENCY_VERIFIER')
)

$crashMutations = @(
    'BEFORE_RESERVATION','AFTER_RESERVATION','AFTER_EVIDENCE_VALIDATION','AFTER_RECEIPT_PREPARATION','AFTER_RECEIPT_STORAGE','AFTER_COMMIT_APPEND','BEFORE_CHECKPOINT_UPDATE','DURING_CHECKPOINT_UPDATE','AFTER_CHECKPOINT_BEFORE_RESPONSE','DURING_RECONCILIATION','DURING_ABORT_OR_SUPERSESSION','DURING_RESTART_RECOVERY','DISK_FULL','ACCESS_DENIED','PARTIAL_WRITE','PARENT_DIRECTORY_PERSISTENCE_FAILURE','CLIENT_DISCONNECT_AFTER_COMMIT'
)
$crash = for ($index = 0; $index -lt $crashMutations.Count; $index++) {
    @(('CRS-{0:D3}' -f ($index + 1)),('Crash/fault point ' + $crashMutations[$index]),'RECOVERY_HARNESS','FAULT_INJECTION','EXECUTION','STATE,HISTORY',$crashMutations[$index],'RECOVERY_ENGINE')
}

$traceAttacks = @(
    @('TRC-001','Circular trace mapping','TRACE_VERIFIER','VERIFY_TRACE','OPERATOR','TRACE','CIRCULAR_TRACE','TRACE_VERIFIER'),
    @('TRC-002','Source without execution','TRACE_VERIFIER','VERIFY_TRACE','OPERATOR','TRACE','SOURCE_WITHOUT_EXECUTION','TRACE_VERIFIER'),
    @('TRC-003','Event without raw evidence','TRACE_VERIFIER','VERIFY_TRACE','OPERATOR','TRACE,OBSERVATION','EVENT_WITHOUT_RAW','TRACE_VERIFIER'),
    @('TRC-004','Host artifact without provenance','TRACE_VERIFIER','VERIFY_TRACE','OPERATOR','TRACE,PATH','HOST_ARTIFACT_ORPHAN','TRACE_VERIFIER'),
    @('TRC-005','Runtime dependency without requirement','TRACE_VERIFIER','VERIFY_TRACE','OPERATOR','TRACE,DEPENDENCY','DEPENDENCY_ORPHAN','TRACE_VERIFIER'),
    @('TRC-006','Unknown protected-domain approval euphemism','CLAIM_VERIFIER','VERIFY_DOCUMENT_CLAIM','OPERATOR','DOCUMENT','UNKNOWN_APPROVAL_VERB','CLAIM_VERIFIER'),
    @('TRC-007','Proposal treated as canonical incorporation','CLAIM_VERIFIER','VERIFY_DOCUMENT_CLAIM','OPERATOR','DOCUMENT','CANONICAL_INCORPORATION_CLAIM','CLAIM_VERIFIER')
)

$allRows = @($positive) + @($authorityAttacks) + @($expectationAttacks) + @($semanticAttacks) + @($principalAttacks) + @($parserAttacks) + @($outerInterfaceAttacks) + @($concurrencyAttacks) + @($upgradeAttacks) + @($historyAttacks) + @($physicalAttacks) + @($traceAttacks)
foreach ($row in $allRows) {
    Add-Case -Id $row[0] -Title $row[1] -Driver $row[2] -Operation $row[3] -CallerRole $row[4] -Categories ($row[5].Split(',')) -Mutation $row[6] -ImplementationSurface $row[7]
}
if (($crash.Count % 8) -ne 0) { throw "invalid crash case authoring field count: $($crash.Count)" }
for ($index = 0; $index -lt $crash.Count; $index += 8) {
    Add-Case -Id $crash[$index] -Title $crash[$index + 1] -Driver $crash[$index + 2] -Operation $crash[$index + 3] -CallerRole $crash[$index + 4] -Categories ($crash[$index + 5].Split(',')) -Mutation $crash[$index + 6] -ImplementationSurface $crash[$index + 7]
}

$caseIds = @($cases | ForEach-Object case_id)
$independentlyDerivedCaseCount = $positive.Count + $authorityAttacks.Count + $expectationAttacks.Count + $semanticAttacks.Count + $principalAttacks.Count + $parserAttacks.Count + $outerInterfaceAttacks.Count + $concurrencyAttacks.Count + $upgradeAttacks.Count + $historyAttacks.Count + $physicalAttacks.Count + $traceAttacks.Count + $crashMutations.Count
if ($cases.Count -ne $independentlyDerivedCaseCount) { throw "case construction count does not equal the independently enumerated positive, negative, bypass, recovery, concurrency, upgrade, historical, outer-interface, and reconciliation vectors: constructed=$($cases.Count) derived=$independentlyDerivedCaseCount" }
if (@($caseIds | Sort-Object -Unique).Count -ne $caseIds.Count) { throw 'duplicate case ID' }
$mappedRequirements = @($cases | ForEach-Object { $_.authority_refs } | ForEach-Object requirement_id | Sort-Object -Unique)
$allRequirements = @($Registry.requirements | ForEach-Object requirement_id | Sort-Object -Unique)
$unmapped = @($allRequirements | Where-Object { $_ -notin $mappedRequirements })
if ($unmapped.Count -ne 0) { throw "unmapped requirements: $($unmapped -join ',')" }

$artifact = [pscustomobject][ordered]@{
    artifact_type = 'R7_REMEDIATION_IMMUTABLE_CASE_DEFINITIONS'
    schema_version = '1.0.0'
    authored_stage = 'CASE_DEFINITION_STAGE'
    expectation_artifact_read = $false
    prohibited_source_commit = 'f0cfbce97e913a133530dd66a70326b1e03a0fb6'
    prohibited_source_reference_count = 0
    requirement_registry_sha256 = Get-LowerSha256 -Bytes ([System.IO.File]::ReadAllBytes($RegistryPath))
    independently_determined_case_count = $cases.Count
    cases = $cases.ToArray()
}
$json = $artifact | ConvertTo-Json -Depth 15
$output = Join-Path $PackageRoot 'immutable_case_definitions.json'
[System.IO.File]::WriteAllText($output, $json + "`n", $Utf8)
[pscustomobject]@{
    case_count = $cases.Count
    mapped_requirement_count = $mappedRequirements.Count
    unmapped_requirement_count = $unmapped.Count
    prohibited_source_reference_count = 0
    output_sha256 = Get-LowerSha256 -Bytes ([System.IO.File]::ReadAllBytes($output))
} | ConvertTo-Json
