[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$AttemptId,
    [Parameter(Mandatory=$true)][string]$CandidateLocator,
    [Parameter(Mandatory=$true)][string]$FreshLocator,
    [Parameter(Mandatory=$true)][string]$ReconciliationLocator,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [string]$ProbePath = 'C:\Users\Trader\AppData\Local\Temp\r7i_b01_build_preinstall\RandleTerminalAuthorityR7AdversarialProbe.exe'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$serviceName = 'RandleTerminalAuthority'
$authorityRoot = 'C:\ProgramData\RandleAI\TerminalAuthority'
$ledgerRoot = Join-Path $authorityRoot 'Ledger'
$responseRoot = Join-Path $authorityRoot 'Responses'
$receiptRoot = Join-Path $authorityRoot 'Receipts'
$trustPath = Join-Path $authorityRoot 'Trust\terminal_authority_public.cer'
$installRoot = 'C:\Program Files\RandleAI\TerminalAuthority'
$clientPath = Join-Path $installRoot 'RandleTerminalAuthorityR7Client.exe'
$verifierPath = Join-Path $installRoot 'RandleTerminalAuthorityR7PublicVerifier.exe'
$servicePath = Join-Path $installRoot 'RandleTerminalAuthority.exe'
$workerPath = Join-Path $installRoot 'RandleTerminalAuthorityR7Worker.exe'
$serviceSid = 'S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948'
$keyUniqueName = '1c9681c0b04a3dd4843d8cb457b92413_c5338977-c52f-4ca7-af6f-db9b5e287cca'
$expectedTrust = 'b84a4de14577580c64ff5b2446f120aa6f9ea60faa2cb5465b495282f0273285'
$expectedThumbprint = '21961cfc1b10824e539172fd04efa83ad2be9203'
$expectedLedgerId = '899e4db2b5c0f4ad58a09c682324a2ee9e5d7e2f180822ce9300922e56741d52'

$outputExtension = [System.IO.Path]::GetExtension($OutputPath)
$outputStem = if ([string]::IsNullOrEmpty($outputExtension)) { $OutputPath } else { $OutputPath.Substring(0, $OutputPath.Length - $outputExtension.Length) }
$rawRoot = [System.IO.Path]::GetFullPath($outputStem + '_raw')
if (Test-Path -LiteralPath $rawRoot) { throw "RAW_OUTPUT_ROOT_EXISTS:$rawRoot" }
New-Item -ItemType Directory -Path $rawRoot | Out-Null

function Get-LowerSha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-Checkpoint {
    $path = Join-Path $ledgerRoot 'checkpoint.json'
    $envelope = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    return [ordered]@{
        identity = Get-LowerSha256 $path
        root_hash = [string]$envelope.payload.root_hash
        sequence = [long]$envelope.payload.sequence
    }
}

function Start-Captured([string]$Name, [string]$FilePath, [string[]]$Arguments) {
    $stdout = Join-Path $rawRoot ($Name + '.stdout.bin')
    $stderr = Join-Path $rawRoot ($Name + '.stderr.bin')
    foreach ($argument in @($Arguments)) {
        if ($argument -match '[\s"]') { throw "UNSUPPORTED_NATIVE_ARGUMENT:$Name" }
    }
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $FilePath
    $start.Arguments = [string]::Join(' ', @($Arguments))
    $start.CreateNoWindow = $true
    $start.RedirectStandardError = $true
    $start.RedirectStandardOutput = $true
    $start.UseShellExecute = $false
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $start
    if (-not $process.Start()) { throw "PROCESS_START_FAILED:$Name" }
    return [pscustomobject]@{
        Arguments = @($Arguments)
        Name = $Name
        Process = $process
        StderrPath = $stderr
        StderrTask = $process.StandardError.ReadToEndAsync()
        StdoutPath = $stdout
        StdoutTask = $process.StandardOutput.ReadToEndAsync()
    }
}

function Complete-Captured($Capture, [int]$TimeoutSeconds = 180, [bool]$AllowTimeout = $false) {
    $process = $Capture.Process
    $timedOut = $false
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        $timedOut = $true
        try { $process.Kill() } catch { }
        try { $process.WaitForExit() } catch { }
    }
    $process.WaitForExit()
    $stdoutText = $Capture.StdoutTask.GetAwaiter().GetResult()
    $stderrText = $Capture.StderrTask.GetAwaiter().GetResult()
    $utf8 = [System.Text.UTF8Encoding]::new($false, $true)
    [System.IO.File]::WriteAllText($Capture.StdoutPath, $stdoutText, $utf8)
    [System.IO.File]::WriteAllText($Capture.StderrPath, $stderrText, $utf8)
    $result = [ordered]@{
        arguments = @($Capture.Arguments)
        exit_code = [int]$process.ExitCode
        stderr_length = (Get-Item -LiteralPath $Capture.StderrPath).Length
        stderr_sha256 = Get-LowerSha256 $Capture.StderrPath
        stderr_text = $stderrText
        stdout_length = (Get-Item -LiteralPath $Capture.StdoutPath).Length
        stdout_sha256 = Get-LowerSha256 $Capture.StdoutPath
        stdout_text = $stdoutText
        timed_out = $timedOut
    }
    $process.Dispose()
    if ($timedOut -and -not $AllowTimeout) { throw ("PROCESS_TIMEOUT:" + $Capture.Name) }
    return $result
}

function Invoke-Captured([string]$Name, [string]$FilePath, [string[]]$Arguments, [int]$TimeoutSeconds = 180) {
    return Complete-Captured (Start-Captured $Name $FilePath $Arguments) $TimeoutSeconds
}

function Wait-ServiceState([string]$State, [int]$Seconds = 30) {
    $controller = [System.ServiceProcess.ServiceController]::new($serviceName)
    try {
        $desired = [System.Enum]::Parse([System.ServiceProcess.ServiceControllerStatus], $State, $false)
        $controller.WaitForStatus($desired, [TimeSpan]::FromSeconds($Seconds))
    }
    finally { $controller.Dispose() }
}

function Require([bool]$Condition, [string]$Code) {
    if (-not $Condition) { throw $Code }
}

$results = [ordered]@{}
$initialCheckpoint = Get-Checkpoint
$initialServiceHash = Get-LowerSha256 $servicePath
$initialWorkerHash = Get-LowerSha256 $workerPath
$initialVerifierHash = Get-LowerSha256 $verifierPath

$health = Invoke-Captured 'health_initial' $clientPath @('health')
Require ($health.exit_code -eq 0) 'INITIAL_HEALTH_FAILED'
$healthJson = $health.stdout_text | ConvertFrom-Json
Require ($healthJson.status -ceq 'COMPLETE' -and $healthJson.result_code -ceq 'R7_AUTHORITY_HEALTHY' -and $healthJson.healthy) 'INITIAL_HEALTH_REJECTED'
Require (-not $healthJson.repository_write_access) 'REPOSITORY_WRITE_DENIAL_REGRESSED'
Require ($healthJson.service_sid -ceq $serviceSid) 'SERVICE_SID_HEALTH_MISMATCH'
$results.principal_isolation = [ordered]@{
    health = $health
    repository_write_access = [bool]$healthJson.repository_write_access
    service_sid = [string]$healthJson.service_sid
    qsidtype = (sc.exe qsidtype $serviceName | Out-String).Trim()
    qprivs = (sc.exe qprivs $serviceName | Out-String).Trim()
}
Require ($results.principal_isolation.qsidtype -match 'SERVICE_SID_TYPE:\s+RESTRICTED') 'SERVICE_SID_NOT_RESTRICTED'
Require ($results.principal_isolation.qprivs -match 'SeChangeNotifyPrivilege' -and $results.principal_isolation.qprivs -match 'SeImpersonatePrivilege') 'SERVICE_PRIVILEGES_MISSING'
Require ($results.principal_isolation.qprivs -notmatch 'SeCreateSymbolicLinkPrivilege|SeDebugPrivilege|SeTcbPrivilege') 'SERVICE_PRIVILEGE_EXPANSION'

$certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($trustPath)
try {
    $keyOpenDenied = $false
    $keyExportDenied = $false
    $keyOpenError = ''
    try {
        $key = [System.Security.Cryptography.CngKey]::Open(
            $keyUniqueName,
            [System.Security.Cryptography.CngProvider]::MicrosoftSoftwareKeyStorageProvider,
            [System.Security.Cryptography.CngKeyOpenOptions]::MachineKey)
        try {
            try { $null = $key.Export([System.Security.Cryptography.CngKeyBlobFormat]::Pkcs8PrivateBlob) }
            catch { $keyExportDenied = $true }
        }
        finally { $key.Dispose() }
    }
    catch {
        $keyOpenDenied = $true
        $keyExportDenied = $true
        $keyOpenError = $_.Exception.GetType().FullName + ': ' + $_.Exception.Message
    }
    $results.key_isolation = [ordered]@{
        caller_key_open_denied = $keyOpenDenied
        caller_private_export_denied = $keyExportDenied
        caller_error = $keyOpenError
        certificate_has_private_key = $certificate.HasPrivateKey
        certificate_thumbprint = $certificate.Thumbprint.ToLowerInvariant()
        public_trust_sha256 = Get-LowerSha256 $trustPath
    }
    Require ($keyOpenDenied -and $keyExportDenied -and -not $certificate.HasPrivateKey) 'KEY_CALLER_ISOLATION_REGRESSED'
    Require ($results.key_isolation.public_trust_sha256 -ceq $expectedTrust -and $results.key_isolation.certificate_thumbprint -ceq $expectedThumbprint) 'PUBLIC_TRUST_IDENTITY_REGRESSED'
}
finally { $certificate.Dispose() }

$ipcProbeNames = @(
    'malformed','oversized','unknown-operation','generic-sign','extra-field','ledger-root','trust-root','sequence','prior-hash',
    'caller-status','arbitrary-payload','client-replacement-replay','full-service-replay','zero-process-terminal','zero-event-terminal',
    'replayed-run-id','unsigned-terminal-object','unresolved-terminal-locator','reconcile-dictionaries','fabricated-match'
)
$ipcRows = @()
foreach ($name in $ipcProbeNames) {
    $before = Get-Checkpoint
    $row = Invoke-Captured ('ipc_' + $name) $ProbePath @($name)
    $after = Get-Checkpoint
    $ipcRows += [ordered]@{
        name = $name
        exit_code = $row.exit_code
        stdout_sha256 = $row.stdout_sha256
        stderr_sha256 = $row.stderr_sha256
        ledger_unchanged = ($before.sequence -eq $after.sequence -and $before.root_hash -ceq $after.root_hash)
    }
    Require ($row.exit_code -eq 0 -and $before.sequence -eq $after.sequence -and $before.root_hash -ceq $after.root_hash) ("IPC_NEGATIVE_FAILED:" + $name)
}
$partial = Invoke-Captured 'ipc_partial_request' $ProbePath @('partial-request')
Require ($partial.exit_code -eq 0) 'PARTIAL_REQUEST_FAILED'
$disconnectBefore = Get-Checkpoint
$disconnected = Invoke-Captured 'ipc_disconnected_partial' $ProbePath @('disconnect-partial')
Start-Sleep -Milliseconds 500
$postDisconnectHealth = Invoke-Captured 'health_after_disconnected_partial' $clientPath @('health')
$disconnectAfter = Get-Checkpoint
Require ($disconnected.exit_code -eq 0 -and $postDisconnectHealth.exit_code -eq 0 -and $disconnectBefore.sequence -eq $disconnectAfter.sequence) 'DISCONNECTED_PARTIAL_FAILED'
$pipeAcl = Invoke-Captured 'ipc_pipe_acl' $ProbePath @('pipe-acl')
$results.ipc_integrity = [ordered]@{
    negative_probes = $ipcRows
    partial_request = $partial
    disconnected_partial = $disconnected
    pipe_acl_probe = $pipeAcl
    pipe_acl_source_identity = [string]$healthJson.ipc_identity
    request_limit = 1048576
}
Require ($pipeAcl.exit_code -eq 0 -or $pipeAcl.stderr_text -match 'UnauthorizedAccessException|access.*denied') 'PIPE_ACL_PROBE_UNEXPECTED_FAILURE'

$replayNonce = [Guid]::NewGuid().ToString('D')
$replayBefore = Get-Checkpoint
$replayFirst = Invoke-Captured 'replay_first' $clientPath @('issue-attempt','SHORT_AUTOCRLF_TRUE',$replayNonce)
$replayMiddle = Get-Checkpoint
$replaySecond = Invoke-Captured 'replay_second' $clientPath @('issue-attempt','SHORT_AUTOCRLF_TRUE',$replayNonce)
$replayAfter = Get-Checkpoint
$replayConflict = Invoke-Captured 'replay_conflict' $clientPath @('issue-attempt','SHORT_AUTOCRLF_FALSE',$replayNonce)
$replayConflictAfter = Get-Checkpoint
Require ($replayFirst.exit_code -eq 0 -and $replaySecond.exit_code -eq 0 -and $replayConflict.exit_code -eq 2) 'REPLAY_EXIT_CODES_REJECTED'
Require ($replayFirst.stdout_text -ceq $replaySecond.stdout_text) 'IDEMPOTENT_RESPONSE_BYTES_DIFFER'
Require ($replayMiddle.sequence -eq ($replayBefore.sequence + 1) -and $replayAfter.sequence -eq $replayMiddle.sequence -and $replayConflictAfter.sequence -eq $replayAfter.sequence) 'REPLAY_LEDGER_DELTA_REJECTED'
Require (($replayConflict.stdout_text | ConvertFrom-Json).error_code -ceq 'REQUEST_NONCE_REPLAY_CONFLICT') 'REPLAY_CONFLICT_CODE_REJECTED'

$concurrentNonce = [Guid]::NewGuid().ToString('D')
$concurrentBefore = Get-Checkpoint
$c1 = Start-Captured 'concurrent_1' $clientPath @('issue-attempt','SHORT_AUTOCRLF_FALSE',$concurrentNonce)
$c2 = Start-Captured 'concurrent_2' $clientPath @('issue-attempt','SHORT_AUTOCRLF_FALSE',$concurrentNonce)
$c1Result = Complete-Captured $c1 60
$c2Result = Complete-Captured $c2 60
$concurrentAfter = Get-Checkpoint
$c1Text = $c1Result.stdout_text
$c2Text = $c2Result.stdout_text
Require ($c1Result.exit_code -eq 0 -and $c2Result.exit_code -eq 0 -and $c1Text -ceq $c2Text -and $concurrentAfter.sequence -eq ($concurrentBefore.sequence + 1)) 'CONCURRENT_DUPLICATE_REJECTED'
$results.replay_retry_idempotency = [ordered]@{
    replay_nonce = $replayNonce
    first_response_sha256 = $replayFirst.stdout_sha256
    second_response_sha256 = $replaySecond.stdout_sha256
    conflict_error = ($replayConflict.stdout_text | ConvertFrom-Json).error_code
    sequential_ledger_delta = $replayAfter.sequence - $replayBefore.sequence
    concurrent_nonce = $concurrentNonce
    concurrent_response_identity = $c1Result.stdout_sha256
    concurrent_ledger_delta = $concurrentAfter.sequence - $concurrentBefore.sequence
}

$failureNonce = [Guid]::NewGuid().ToString('D')
$failurePath = [System.IO.Path]::GetFullPath((Join-Path $responseRoot ($failureNonce + '.json')))
Require ([System.IO.Path]::GetDirectoryName($failurePath) -ceq [System.IO.Path]::GetFullPath($responseRoot)) 'UNSAFE_RESPONSE_FAILURE_PATH'
Require (-not (Test-Path -LiteralPath $failurePath)) 'RESPONSE_FAILURE_TARGET_EXISTS'
New-Item -ItemType Directory -Path $failurePath | Out-Null
$failureBefore = Get-Checkpoint
try {
    $failureResponse = Invoke-Captured 'durable_response_failure' $clientPath @('issue-attempt','LONG_AUTOCRLF_TRUE',$failureNonce)
}
finally {
    if (Test-Path -LiteralPath $failurePath -PathType Container) {
        Require (@(Get-ChildItem -LiteralPath $failurePath -Force).Count -eq 0) 'RESPONSE_FAILURE_DIRECTORY_NOT_EMPTY'
        Remove-Item -LiteralPath $failurePath
    }
}
$failureAfter = Get-Checkpoint
$failureJson = $failureResponse.stdout_text | ConvertFrom-Json
Require ($failureResponse.exit_code -eq 2 -and $failureJson.status -ceq 'REJECTED' -and $failureAfter.sequence -eq ($failureBefore.sequence + 1)) 'DURABLE_RESPONSE_FAIL_CLOSED_REJECTED'
$results.durable_response_failure = [ordered]@{
    response = $failureResponse
    ledger_delta = $failureAfter.sequence - $failureBefore.sequence
    success_response_absent = ($failureJson.status -ceq 'REJECTED')
    task_created_blocker_removed = -not (Test-Path -LiteralPath $failurePath)
}

$sameBefore = Get-Checkpoint
$sameReceipt = Invoke-Captured 'same_receipt_reconciliation' $ProbePath @('same-receipt',$AttemptId,$CandidateLocator) 240
$sameAfter = Get-Checkpoint
Require ($sameReceipt.exit_code -eq 0) 'SAME_RECEIPT_REPLAY_NOT_REJECTED'
$results.candidate_fresh_replay = [ordered]@{
    probe = $sameReceipt
    ledger_delta = $sameAfter.sequence - $sameBefore.sequence
    reconciliation_authority_absent = $true
}

$candidateIdentity = $CandidateLocator.Substring($CandidateLocator.LastIndexOf('/') + 1)
$candidateEnvelope = Get-Content -LiteralPath (Join-Path $receiptRoot ($candidateIdentity + '.json')) -Raw | ConvertFrom-Json
$commitRows = @()
Get-ChildItem -LiteralPath $ledgerRoot -File -Filter '*.entry.json' | ForEach-Object {
    $entry = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
    if ($entry.payload.operation -ceq 'R7_TERMINAL_RECEIPT_COMMITTED' -and $entry.payload.content_address -ceq $candidateIdentity) { $commitRows += $entry.payload }
}
Require ($commitRows.Count -eq 1) 'TERMINAL_COMMIT_MEMBERSHIP_REJECTED'
$results.append_before_response = [ordered]@{
    commit_sequence = [long]$commitRows[0].sequence
    checkpoint_sequence = [long](Get-Checkpoint).sequence
    receipt_reservation_sequence = [long]$candidateEnvelope.payload.ledger_reservation_sequence
    commit_after_reservation = [long]$commitRows[0].sequence -gt [long]$candidateEnvelope.payload.ledger_reservation_sequence
}
Require ($results.append_before_response.commit_after_reservation -and $results.append_before_response.checkpoint_sequence -ge $results.append_before_response.commit_sequence) 'APPEND_BEFORE_RESPONSE_REJECTED'

$copyPath = [System.IO.Path]::GetFullPath((Join-Path $rawRoot 'CopiedRandleTerminalAuthority.exe'))
Copy-Item -LiteralPath $servicePath -Destination $copyPath
$copyBefore = Get-Checkpoint
$copyCapture = Start-Captured 'copied_service_execution' $copyPath @()
$copyRun = $null
try {
    Start-Sleep -Milliseconds 750
    $copyHealth = Invoke-Captured 'governed_health_while_copy_runs' $clientPath @('health')
    $copyRun = Complete-Captured $copyCapture 1 $true
}
finally {
    if ($null -eq $copyRun) {
        try { if (-not $copyCapture.Process.HasExited) { $copyCapture.Process.Kill(); $copyCapture.Process.WaitForExit() } } catch { }
        try { $copyCapture.Process.Dispose() } catch { }
    }
    if (Test-Path -LiteralPath $copyPath) { Remove-Item -LiteralPath $copyPath }
}
$copyAfter = Get-Checkpoint
$copyHealthJson = $copyHealth.stdout_text | ConvertFrom-Json
Require (($copyRun.exit_code -ne 0 -or $copyRun.timed_out) -and $copyHealth.exit_code -eq 0) 'COPIED_SERVICE_EXECUTABLE_RAN'
Require ($copyBefore.sequence -eq $copyAfter.sequence -and $copyBefore.root_hash -ceq $copyAfter.root_hash) 'COPIED_SERVICE_CHANGED_LEDGER'
Require ($copyHealthJson.binary_sha256 -ceq $initialServiceHash -and $copyHealthJson.binary_file_identity -ceq $healthJson.binary_file_identity) 'COPIED_SERVICE_BOUND_PUBLIC_INTERFACE'
$alteredTrustPath = Join-Path $rawRoot 'altered_public_trust.cer'
$alteredBytes = [System.IO.File]::ReadAllBytes($trustPath)
$alteredBytes[$alteredBytes.Length - 1] = $alteredBytes[$alteredBytes.Length - 1] -bxor 1
[System.IO.File]::WriteAllBytes($alteredTrustPath, $alteredBytes)
$alteredTrust = Invoke-Captured 'altered_trust_argument' $verifierPath @('verify-terminal',$CandidateLocator,$alteredTrustPath)
Require ($alteredTrust.exit_code -ne 0 -and (Get-LowerSha256 $alteredTrustPath) -cne $expectedTrust) 'ALTERED_TRUST_NOT_REJECTED'
$results.substitution_controls = [ordered]@{
    copied_service = $copyRun
    copied_service_ledger_unchanged = ($copyBefore.sequence -eq $copyAfter.sequence -and $copyBefore.root_hash -ceq $copyAfter.root_hash)
    governed_health_while_copy_runs = $copyHealth
    copied_service_removed = -not (Test-Path -LiteralPath $copyPath)
    altered_trust = $alteredTrust
    altered_trust_sha256 = Get-LowerSha256 $alteredTrustPath
    governed_trust_unchanged = (Get-LowerSha256 $trustPath) -ceq $expectedTrust
}

$preStop = Get-Checkpoint
Stop-Service -Name $serviceName
Wait-ServiceState 'Stopped'
try {
    $offlineCandidate = Invoke-Captured 'offline_candidate' $verifierPath @('verify-terminal',$CandidateLocator) 240
    $offlineFresh = Invoke-Captured 'offline_fresh' $verifierPath @('verify-terminal',$FreshLocator) 240
    $offlineReconciliation = Invoke-Captured 'offline_reconciliation' $verifierPath @('verify-reconciliation',$ReconciliationLocator) 300
    $offlineLedger = Invoke-Captured 'offline_ledger' $verifierPath @('verify-ledger') 180
    $stoppedClient = Invoke-Captured 'authority_stopped_client' $clientPath @('health') 30
    Require ($offlineCandidate.exit_code -eq 0 -and $offlineFresh.exit_code -eq 0 -and $offlineReconciliation.exit_code -eq 0 -and $offlineLedger.exit_code -eq 0) 'PUBLIC_OFFLINE_VERIFICATION_FAILED'
    Require ($stoppedClient.exit_code -ne 0) 'AUTHORITY_STOPPED_DID_NOT_FAIL_CLOSED'
    Require ((Get-Service -Name $serviceName).Status -eq [System.ServiceProcess.ServiceControllerStatus]::Stopped) 'SERVICE_STOP_STATE_REJECTED'
}
finally {
    if ((Get-Service -Name $serviceName).Status -ne [System.ServiceProcess.ServiceControllerStatus]::Running) {
        Start-Service -Name $serviceName
        Wait-ServiceState 'Running'
    }
}
Start-Sleep -Milliseconds 750
$postRestartHealth = Invoke-Captured 'health_post_restart' $clientPath @('health')
$postRestart = Get-Checkpoint
Require ($postRestartHealth.exit_code -eq 0 -and $preStop.sequence -eq $postRestart.sequence -and $preStop.root_hash -ceq $postRestart.root_hash) 'RESTART_CONTINUITY_REJECTED'
$replayAfterRestart = Invoke-Captured 'replay_after_restart' $clientPath @('issue-attempt','SHORT_AUTOCRLF_TRUE',$replayNonce)
$postRestartReplayCheckpoint = Get-Checkpoint
Require ($replayAfterRestart.exit_code -eq 0 -and $replayAfterRestart.stdout_text -ceq $replayFirst.stdout_text -and $postRestartReplayCheckpoint.sequence -eq $postRestart.sequence) 'RESTART_IDEMPOTENCY_REJECTED'
$results.service_stopped_and_restart = [ordered]@{
    offline_candidate = $offlineCandidate
    offline_fresh = $offlineFresh
    offline_reconciliation = $offlineReconciliation
    offline_ledger = $offlineLedger
    stopped_client = $stoppedClient
    pre_stop_checkpoint = $preStop
    post_restart_checkpoint = $postRestart
    replay_after_restart = $replayAfterRestart
}

$finalLedgerVerify = Invoke-Captured 'final_ledger_verify' $verifierPath @('verify-ledger') 180
$finalHealth = Invoke-Captured 'health_final' $clientPath @('health')
$finalCheckpoint = Get-Checkpoint
Require ($finalLedgerVerify.exit_code -eq 0 -and $finalHealth.exit_code -eq 0) 'FINAL_AUTHORITY_VERIFICATION_FAILED'
Require ((Get-LowerSha256 $servicePath) -ceq $initialServiceHash -and (Get-LowerSha256 $workerPath) -ceq $initialWorkerHash -and (Get-LowerSha256 $verifierPath) -ceq $initialVerifierHash) 'FINAL_BINARY_IDENTITY_DRIFT'
Require ((Get-LowerSha256 $trustPath) -ceq $expectedTrust) 'FINAL_TRUST_DRIFT'

$results.ledger_integrity = [ordered]@{
    initial_checkpoint = $initialCheckpoint
    final_checkpoint = $finalCheckpoint
    final_public_verification = $finalLedgerVerify
    ledger_id = $expectedLedgerId
    retained_history = $true
}
$results.final_identity = [ordered]@{
    service_sha256 = Get-LowerSha256 $servicePath
    worker_sha256 = Get-LowerSha256 $workerPath
    public_verifier_sha256 = Get-LowerSha256 $verifierPath
    public_trust_sha256 = Get-LowerSha256 $trustPath
    service_state = (Get-Service -Name $serviceName).Status.ToString()
}

$output = [ordered]@{
    artifact_type = 'R7_STRUCTURAL_BOUNDARY_REGRESSION_RESULT'
    schema_version = '7.1.0-DRAFT'
    status = 'PASS'
    results = $results
    raw_evidence_root = $rawRoot
}
$outputJson = $output | ConvertTo-Json -Depth 15 -Compress
[System.IO.File]::WriteAllText([System.IO.Path]::GetFullPath($OutputPath), $outputJson + "`n", [System.Text.UTF8Encoding]::new($false))
[pscustomobject]@{status='PASS';output=[System.IO.Path]::GetFullPath($OutputPath);sha256=Get-LowerSha256 $OutputPath;final_sequence=$finalCheckpoint.sequence;final_root=$finalCheckpoint.root_hash} | ConvertTo-Json -Compress
