[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$SourceCommit,
    [Parameter(Mandatory = $true)][string]$RepositoryRoot,
    [Parameter(Mandatory = $true)][string]$EvidenceRoot,
    [Parameter(Mandatory = $true)][string]$CheckoutBase,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')][string]$ActiveTransitionNonce
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repository = [IO.Path]::GetFullPath($RepositoryRoot)
$safeRepository = $repository.Replace('\','/')
$evidence = [IO.Path]::GetFullPath($EvidenceRoot)
$checkoutBaseFull = [IO.Path]::GetFullPath($CheckoutBase)
$packageRelative = 'Architecture\Audits\2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT'
$casePath = Join-Path $repository "$packageRelative\immutable_case_definitions.json"
$harness = 'C:\Program Files\RandleAI\TerminalAuthorityV4\RandleTerminalAdversarialHarness.exe'
$publicVerifier = 'C:\Program Files\RandleAI\TerminalAuthorityV4\RandleTerminalPublicVerifier.exe'
$upgradeClient = 'C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradeClient.exe'
$artifactTool = 'C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Build\R7ArtifactTool.bootstrap.exe'
$upgradeCertificate = 'C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Trust\upgrade_authority_public.cer'
$upgradeAuthorizationRoot = 'C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Authorizations'
$upgradeStagingRoot = 'C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Staging'
$executionTestRoot = 'C:\ProgramData\RandleAI\TerminalExecution\TestRoots'
$alternateVolumeRoot = 'S:\RandleAI\TerminalAuthorityTestRoots'
$oldestRetainedReceipt = '8a06b2c2e851cc45f13ee9a618b6f34b1064945b63905c616cb6fd1893be6418'
$terminalServices = @('RandleTerminalUpgradeAuthority','RandleTerminalAuthority','RandleTerminalObservation','RandleTerminalComparator','RandleTerminalExecution')
$gitExecutable = 'C:\Program Files\Git\cmd\git.exe'
$aclTool = 'C:\Windows\System32\icacls.exe'
$fsutilTool = 'C:\Windows\System32\fsutil.exe'

function Get-LowerHash([string]$Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function Get-TextHash([string]$Value) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value))).Replace('-', '')).ToLowerInvariant() }
    finally { $algorithm.Dispose() }
}
function New-CanonicalGuid { return [Guid]::NewGuid().ToString('D').ToLowerInvariant() }
function Write-JsonNew([object]$Value, [string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if (Test-Path -LiteralPath $full) { throw "Refusing evidence overwrite: $full" }
    $parent = Split-Path -Parent $full
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
    [IO.File]::WriteAllText($full, ($Value | ConvertTo-Json -Depth 100), [Text.UTF8Encoding]::new($false))
}
function Read-Json([string]$Path) { return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json }
function Require-NewDirectory([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if (Test-Path -LiteralPath $full) { throw "Directory already exists: $full" }
    New-Item -ItemType Directory -Path $full | Out-Null
    return $full
}
function Invoke-Captured([string]$FilePath, [string[]]$Arguments, [string]$CaptureStem, [int[]]$AllowedExitCodes) {
    $stdout = $CaptureStem + '.stdout.log'
    $stderr = $CaptureStem + '.stderr.log'
    if ((Test-Path -LiteralPath $stdout) -or (Test-Path -LiteralPath $stderr)) { throw "Capture already exists: $CaptureStem" }
    & $FilePath @Arguments 1> $stdout 2> $stderr
    $exitCode = $LASTEXITCODE
    if ($AllowedExitCodes -notcontains $exitCode) { throw "$FilePath exited $exitCode; evidence: $CaptureStem" }
    return [ordered]@{ exit_code = $exitCode; stderr_path = $stderr; stderr_sha256 = (Get-LowerHash $stderr); stdout_path = $stdout; stdout_sha256 = (Get-LowerHash $stdout) }
}
function Invoke-Harness([string[]]$Arguments, [string]$OutputPath) {
    $capture = Invoke-Captured $harness ($Arguments + @($OutputPath)) ($OutputPath + '.process') @(0)
    if (-not (Test-Path -LiteralPath $OutputPath -PathType Leaf)) { throw "Harness output absent: $OutputPath" }
    return [ordered]@{ invocation = $capture; value = (Read-Json $OutputPath) }
}
function Invoke-Git([string[]]$Arguments, [string]$CaptureStem) {
    return Invoke-Captured $gitExecutable $Arguments $CaptureStem @(0)
}
function Get-Response([object]$HarnessResult) {
    if ($null -eq $HarnessResult.value.response) { throw 'Outer-interface response missing.' }
    return $HarnessResult.value.response
}
function New-PayloadFile([object]$Payload, [string]$Path) { return New-CanonicalPayloadFile $Payload $Path }
function New-CanonicalPayloadFile([object]$Payload, [string]$Path) {
    $raw = $Path + '.raw.json'
    Write-JsonNew $Payload $raw
    & $artifactTool canonicalize $raw $Path | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Canonical payload creation failed: $Path" }
    return $Path
}
function Get-VerifiedActiveUpgradePayload([string]$Root) {
    $envelope = Join-Path $upgradeAuthorizationRoot ($ActiveTransitionNonce + '.upgrade.json')
    $payload = Join-Path $Root 'active-upgrade-authorization.verified-payload.json'
    & $artifactTool verify-envelope $envelope $upgradeCertificate (Get-LowerHash $upgradeCertificate) $payload | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Active upgrade authorization failed independent public verification.' }
    $value = Read-Json $payload
    if ($value.operation -cne 'AUTHORIZE_TERMINAL_UPGRADE' -or $value.transition_nonce -cne $ActiveTransitionNonce -or $value.revocation_state -cne 'ACTIVE') { throw 'Active upgrade authorization semantics mismatch.' }
    return $value
}
function Invoke-ActualUpgradeAttack([string]$CaseId, [object]$Context, [string]$RunRoot) {
    $caseRoot = Join-Path $RunRoot ('Cases\' + $CaseId + '\actual-upgrade-interface')
    New-Item -ItemType Directory -Path $caseRoot -Force | Out-Null
    $active = Get-VerifiedActiveUpgradePayload $caseRoot
    $payload = ($active | ConvertTo-Json -Depth 100 | ConvertFrom-Json)
    foreach ($name in @('activation_sequence','authorization_time','authority_class','operation','request_frame_sha256','request_identity','request_payload_identity','revocation_state','schema_version','verification_object_identity')) { $payload.PSObject.Properties.Remove($name) }
    $payload.components = @($payload.components | ForEach-Object { [ordered]@{final_path=$_.final_path;role=$_.role;sha256=$_.sha256;staging_relative_path=$_.staging_relative_path} })
    $nonce = New-CanonicalGuid
    if ($CaseId -eq 'UPG-007') {
        $nonce = $ActiveTransitionNonce
        $payload.rollback_constraints = 'CONFLICTING_REPLAY_ATTACK|' + [string]$Context.run_label
    } else {
        $stage = Join-Path $upgradeStagingRoot $nonce
        New-Item -ItemType Directory -Path $stage | Out-Null
        & $aclTool $stage /setowner SYSTEM | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Unable to set governed staging owner: $stage" }
        & $aclTool $stage /inheritance:r /grant:r 'SYSTEM:(OI)(CI)(F)' 'BUILTIN\Administrators:(OI)(CI)(F)' 'NT SERVICE\RandleTerminalUpgradeAuthority:(OI)(CI)(RX)' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Unable to set governed staging ACL: $stage" }
        $payload.staging_root = $stage
    }
    $payload.transition_nonce = $nonce
    switch ($CaseId) {
        'UPG-002' { }
        'UPG-003' { (@($payload.components | Where-Object role -CEQ 'TERMINAL_SIGNER'))[0].sha256 = '9ea829416f37c94db2858586fa5e0042652f6caa4637a29fdbefb513577a7526' }
        'UPG-004' { $payload.new_interface_version = '1.0.0' }
        'UPG-005' { (@($payload.components | Where-Object role -CEQ 'TERMINAL_POLICY'))[0].sha256 = '76eb2900b2000aa0b41e6040335cc323f7443728aad21cd871d5b6b8e17bcd8b' }
        'UPG-006' { (@($payload.components | Where-Object role -CEQ 'EXECUTION'))[0].sha256 = ('0' * 64) }
        'UPG-007' { }
        'UPG-008' { $payload.host_binding.terminal_ledger_id = ('f' * 64) }
        'UPG-009' { $payload.components = @($payload.components | Select-Object -First ($payload.components.Count - 1)) }
        'UPG-010' { $payload.components[0].role = 'GENERIC_SIGNING_SERVICE' }
        default { throw "No actual upgrade attack recipe for $CaseId" }
    }
    $payloadPath = New-CanonicalPayloadFile $payload (Join-Path $caseRoot 'authorization-payload.json')
    $interactionPath = Join-Path $caseRoot 'outer-interaction.json'
    $capture = Invoke-Captured $upgradeClient @('AUTHORIZE_TERMINAL_UPGRADE',$payloadPath,$interactionPath) (Join-Path $caseRoot 'upgrade-client') @(2)
    $interaction = Read-Json $interactionPath
    if ($interaction.response.status -cne 'REJECTED') { throw "Actual upgrade attack was not rejected: $CaseId" }
    Write-JsonNew ([ordered]@{case_id=$CaseId;interaction_sha256=(Get-LowerHash $interactionPath);process=$capture;request_identity=$interaction.request_identity;run_label=$Context.run_label;staging_root=$payload.staging_root;transition_nonce=$nonce}) (Join-Path $caseRoot 'attack-evidence-index.json')
    return [ordered]@{ external_request_frame=$interaction.request_frame;external_response_frame=$interaction.response_frame;upgrade_request_identity=$interaction.request_identity }
}
function Get-LedgerStatus([string]$Root, [string]$Label) {
    $payload = New-PayloadFile ([ordered]@{}) (Join-Path $Root "$Label.payload.json")
    $result = Invoke-Harness @('call','terminal','GET_LEDGER_STATUS',$payload) (Join-Path $Root "$Label.outer.json")
    $response = Get-Response $result
    if ($response.status -ne 'COMPLETE' -or $response.result_code -ne 'LEDGER_STATUS_RESOLVED') { throw 'Ledger status did not resolve.' }
    return $response
}
function Invoke-TerminalProposal([string]$Root, [string]$Label, [string]$CheckoutIdentity, [string]$AutoCrlf, [string]$CheckoutLength) {
    $requestId = New-CanonicalGuid
    $payloadValue = [ordered]@{
        checkout_identity = $CheckoutIdentity
        configuration = [ordered]@{ autocrlf = $AutoCrlf; checkout_length = $CheckoutLength }
        proposal_identity = Get-TextHash("R7-PROPOSAL|$Label|$requestId")
    }
    $payload = New-PayloadFile $payloadValue (Join-Path $Root "$Label.payload.json")
    $first = Invoke-Harness @('call-id','terminal','SUBMIT_TERMINAL_PROPOSAL',$payload,$requestId) (Join-Path $Root "$Label.first.outer.json")
    $second = Invoke-Harness @('call-id','terminal','SUBMIT_TERMINAL_PROPOSAL',$payload,$requestId) (Join-Path $Root "$Label.identical-retry.outer.json")
    $firstBytes = [Convert]::FromBase64String($first.value.response_frame)
    $secondBytes = [Convert]::FromBase64String($second.value.response_frame)
    if ((Get-TextHash([Convert]::ToBase64String($firstBytes))) -ne (Get-TextHash([Convert]::ToBase64String($secondBytes)))) { throw 'Identical request retry response differs.' }
    $conflictPayloadValue = [ordered]@{
        checkout_identity = $CheckoutIdentity
        configuration = [ordered]@{ autocrlf = $AutoCrlf; checkout_length = $CheckoutLength }
        proposal_identity = Get-TextHash("R7-CONFLICT|$Label|$requestId")
    }
    $conflictPayload = New-PayloadFile $conflictPayloadValue (Join-Path $Root "$Label.conflict.payload.json")
    $conflict = Invoke-Harness @('call-id','terminal','SUBMIT_TERMINAL_PROPOSAL',$conflictPayload,$requestId) (Join-Path $Root "$Label.conflicting-retry.outer.json")
    $conflictResponse = Get-Response $conflict
    if ($conflictResponse.status -ne 'REJECTED' -or $conflictResponse.error_code -ne 'REQUEST_IDENTITY_CONFLICT') { throw 'Conflicting retry was not rejected.' }
    return [ordered]@{
        first_receipt_identity = (Get-Response $first).receipt_identity
        identical_response_frame_sha256 = $first.value.response_frame_sha256
        request_identity = $requestId
        retry_response_frame_sha256 = $second.value.response_frame_sha256
        conflicting_retry_code = $conflictResponse.error_code
    }
}
function New-FreshCheckout([string]$ConfigRoot, [string]$RunKind, [string]$AutoCrlf, [string]$CheckoutLength) {
    $label = ($CheckoutLength + '-' + $AutoCrlf + '-' + $RunKind.ToLowerInvariant())
    if ($CheckoutLength -eq 'long') {
        $padding = 'long_checkout_component_' + ('r7terminalauthority_' * 7)
        $checkout = Join-Path $checkoutBaseFull ($padding + $label)
    } else { $checkout = Join-Path $checkoutBaseFull ('r7-' + $label) }
    if (Test-Path -LiteralPath $checkout) { throw "Fresh checkout target already exists: $checkout" }
    $captureRoot = Join-Path $ConfigRoot ('checkout-' + $RunKind.ToLowerInvariant())
    New-Item -ItemType Directory -Path $captureRoot | Out-Null
    Invoke-Git @('-c',"safe.directory=$safeRepository",'-c','core.longpaths=true','clone','--no-hardlinks','--no-checkout',$repository,$checkout) (Join-Path $captureRoot 'clone') | Out-Null
    $safeCheckout = $checkout.Replace('\','/')
    Invoke-Git @('-c',"safe.directory=$safeCheckout",'-C',$checkout,'config','core.longpaths','true') (Join-Path $captureRoot 'config-longpaths') | Out-Null
    Invoke-Git @('-c',"safe.directory=$safeCheckout",'-C',$checkout,'config','core.autocrlf',$AutoCrlf) (Join-Path $captureRoot 'config-autocrlf') | Out-Null
    Invoke-Git @('-c',"safe.directory=$safeCheckout",'-C',$checkout,'checkout','--detach',$SourceCommit) (Join-Path $captureRoot 'checkout') | Out-Null
    $head = (& $gitExecutable -c "safe.directory=$safeCheckout" -C $checkout rev-parse HEAD).Trim()
    $tree = (& $gitExecutable -c "safe.directory=$safeCheckout" -C $checkout show -s --format=%T HEAD).Trim()
    $statusBytes = [Text.Encoding]::UTF8.GetBytes((& $gitExecutable -c "safe.directory=$safeCheckout" -C $checkout status --porcelain=v1 --untracked-files=all) -join "`n")
    if ($head -ne $SourceCommit -or $statusBytes.Length -ne 0) { throw "Fresh checkout is not clean at exact commit: $checkout" }
    if ($CheckoutLength -eq 'long' -and $checkout.Length -lt 180) { throw "Long checkout is insufficiently long: $($checkout.Length)" }
    if ($CheckoutLength -eq 'short' -and $checkout.Length -gt 160) { throw "Short checkout is unexpectedly long: $($checkout.Length)" }
    $tracked = [Collections.Generic.List[object]]::new()
    foreach ($relative in (& $gitExecutable -c "safe.directory=$safeCheckout" -C $checkout ls-files)) {
        $full = Join-Path $checkout $relative
        $tracked.Add([ordered]@{ path = $relative.Replace('\','/'); raw_sha256 = (Get-LowerHash $full); size = (Get-Item -LiteralPath $full).Length })
    }
    $identityPath = Join-Path $captureRoot 'checkout_identity.json'
    $gitPath = $gitExecutable
    Write-JsonNew ([ordered]@{
        artifact_type = 'R7_FRESH_DETACHED_CHECKOUT_IDENTITY'
        autocrlf = $AutoCrlf
        checkout_length = $CheckoutLength
        checkout_nonce = New-CanonicalGuid
        checkout_path = $checkout
        checkout_path_length = $checkout.Length
        git_executable = $gitPath
        git_executable_sha256 = Get-LowerHash $gitPath
        head = $head
        run_kind = $RunKind
        schema_version = '1.0.0'
        source_tree = $tree
        tracked_files = $tracked.ToArray()
    }) $identityPath
    return [ordered]@{ checkout_identity = (Get-LowerHash $identityPath); identity_path = $identityPath; path = $checkout; tree = $tree }
}
function Start-PathRace([string]$CaseId, [object]$Fixture) {
    if ($CaseId -notin @('PHY-007','PHY-008','PHY-012')) { return $null }
    $attack = [string]$Fixture.attack_path
    return Start-Job -ScriptBlock {
        param($CaseId, $Attack)
        $success = 0; $denied = 0; $other = 0
        if ($CaseId -eq 'PHY-007') {
            $moved = $Attack + '.racing'
            for ($index = 0; $index -lt 3000; $index++) {
                try { Move-Item -LiteralPath $Attack -Destination $moved -ErrorAction Stop; Move-Item -LiteralPath $moved -Destination $Attack -ErrorAction Stop; $success++ } catch { $denied++; if ((Test-Path -LiteralPath $moved) -and -not (Test-Path -LiteralPath $Attack)) { try { Move-Item -LiteralPath $moved -Destination $Attack -ErrorAction Stop } catch { $other++ } } }
                Start-Sleep -Milliseconds 1
            }
        } elseif ($CaseId -eq 'PHY-008') {
            for ($index = 0; $index -lt 3000; $index++) {
                try { [IO.File]::WriteAllText($Attack, ('RACE-' + $index)); $success++ } catch { $denied++ }
                Start-Sleep -Milliseconds 1
            }
        } else {
            $directory = Split-Path -Parent $Attack; $moved = $directory + '.racing'
            for ($index = 0; $index -lt 3000; $index++) {
                try { Move-Item -LiteralPath $directory -Destination $moved -ErrorAction Stop; Move-Item -LiteralPath $moved -Destination $directory -ErrorAction Stop; $success++ } catch { $denied++; if ((Test-Path -LiteralPath $moved) -and -not (Test-Path -LiteralPath $directory)) { try { Move-Item -LiteralPath $moved -Destination $directory -ErrorAction Stop } catch { $other++ } } }
                Start-Sleep -Milliseconds 1
            }
        }
        [ordered]@{ attack_path = $Attack; case_id = $CaseId; denied_or_conflicting_attempts = $denied; other_failures = $other; successful_substitution_attempts = $success }
    } -ArgumentList $CaseId,$attack
}
function Invoke-Case([string]$CaseId, [object]$Fixture, [string]$RunRoot) {
    $caseRoot = Join-Path $RunRoot ('Cases\' + $CaseId)
    New-Item -ItemType Directory -Path $caseRoot -Force | Out-Null
    $fixturePath = New-PayloadFile $Fixture (Join-Path $caseRoot 'fixture.json')
    $raceJob = Start-PathRace $CaseId $Fixture
    if ($null -ne $raceJob) { Start-Sleep -Milliseconds 150 }
    try { $result = Invoke-Harness @('execute-outer-case',$CaseId,$fixturePath) (Join-Path $caseRoot 'outer-result.json') }
    finally {
        if ($null -ne $raceJob) {
            $raceJob | Wait-Job -Timeout 20 | Out-Null
            if ($raceJob.State -eq 'Running') { Stop-Job -Job $raceJob }
            $raceResult = @($raceJob | Receive-Job)
            Write-JsonNew $raceResult (Join-Path $caseRoot 'race-result.json')
            Remove-Job -Job $raceJob -Force
        }
    }
    $response = Get-Response $result
    if ($response.status -ne 'COMPLETE' -or $response.result_code -ne 'CASE_EXECUTED_THROUGH_HOSTILE_OUTER_INTERFACE') { throw "Hostile outer-interface relay failed to construct case graph: $CaseId" }
    if ($response.request_builder_expectation_artifact_read -ne $false -or $response.event_producer_expectation_artifact_read -ne $false) { throw "Request/event expectation separation failed: $CaseId" }
    return $response.case_graph
}
function New-PathFixture([string]$CaseId, [string]$RunLabel, [string]$RunRoot) {
    $testRoot = Join-Path $executionTestRoot ($RunLabel + '\' + $CaseId)
    if (Test-Path -LiteralPath $testRoot) { throw "Path test root already exists: $testRoot" }
    New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
    $reference = Join-Path $testRoot 'governed-reference.bin'
    [IO.File]::WriteAllBytes($reference, [Text.Encoding]::UTF8.GetBytes("GOVERNED-R7-REFERENCE|$RunLabel|$CaseId"))
    $attack = Join-Path $testRoot 'attack.bin'
    $raceEvidence = [ordered]@{ attempted = $false; case_id = $CaseId }
    switch ($CaseId) {
        'PHY-001' {
            $target = Join-Path $testRoot 'junction-target'; New-Item -ItemType Directory -Path $target | Out-Null
            [IO.File]::WriteAllBytes((Join-Path $target 'attack.bin'), [IO.File]::ReadAllBytes($reference))
            $junction = Join-Path $testRoot 'junction-entry'; New-Item -ItemType Junction -Path $junction -Target $target | Out-Null
            $attack = Join-Path $junction 'attack.bin'
        }
        'PHY-002' { [IO.File]::WriteAllBytes($attack, [IO.File]::ReadAllBytes($reference)); $link = Join-Path $testRoot 'attack-link.bin'; New-Item -ItemType SymbolicLink -Path $link -Target $attack | Out-Null; $attack = $link }
        'PHY-003' { $source = Join-Path $testRoot 'hardlink-source.bin'; [IO.File]::WriteAllBytes($source, [IO.File]::ReadAllBytes($reference)); New-Item -ItemType HardLink -Path $attack -Target $source | Out-Null }
        'PHY-004' { [IO.File]::WriteAllBytes($attack, [IO.File]::ReadAllBytes($reference)); [IO.File]::WriteAllText($attack + ':R7ATTACK', 'alternate-stream'); $attack = $attack + ':R7ATTACK' }
        'PHY-005' {
            $longName = Join-Path $testRoot 'short-name-attack-source.bin'; [IO.File]::WriteAllBytes($longName, [IO.File]::ReadAllBytes($reference))
            & $fsutilTool file setshortname $longName R7ATTK~1.BIN | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'Unable to create governed 8.3 alias attack.' }
            $attack = Join-Path $testRoot 'R7ATTK~1.BIN'
        }
        'PHY-006' { $canonical = Join-Path $testRoot 'Case-Attack.bin'; [IO.File]::WriteAllBytes($canonical, [IO.File]::ReadAllBytes($reference)); $attack = $canonical.ToUpperInvariant() }
        'PHY-007' { [IO.File]::WriteAllText($attack, 'RACE-SUBSTITUTION'); $raceEvidence = [ordered]@{ attempted = $true; case_id = $CaseId; operation = 'rename_substitution'; source = $attack; substitute = (Join-Path $testRoot 'rename-substitute.bin') }; [IO.File]::WriteAllBytes($raceEvidence.substitute, [IO.File]::ReadAllBytes($reference)) }
        'PHY-008' { [IO.File]::WriteAllText($attack, 'READ-AFTER-HASH-SUBSTITUTION'); $raceEvidence = [ordered]@{ attempted = $true; case_id = $CaseId; operation = 'replacement_after_measurement'; source = $attack; substitute = (Join-Path $testRoot 'replacement.bin') }; [IO.File]::WriteAllBytes($raceEvidence.substitute, [IO.File]::ReadAllBytes($reference)) }
        'PHY-009' { [IO.File]::WriteAllBytes($attack, [IO.File]::ReadAllBytes($reference)) }
        'PHY-010' { $stale = Join-Path $testRoot 'stale-subtree'; New-Item -ItemType Directory -Path $stale | Out-Null; $attack = Join-Path $stale 'attack.bin'; [IO.File]::WriteAllBytes($attack, [IO.File]::ReadAllBytes($reference)) }
        'PHY-011' { if (-not (Test-Path -LiteralPath $alternateVolumeRoot)) { New-Item -ItemType Directory -Path $alternateVolumeRoot -Force | Out-Null }; $alt = Join-Path $alternateVolumeRoot ($RunLabel + '-' + $CaseId + '.bin'); [IO.File]::WriteAllBytes($alt, [IO.File]::ReadAllBytes($reference)); $attack = $alt }
        'PHY-012' { $directory = Join-Path $testRoot 'directory-race'; New-Item -ItemType Directory -Path $directory | Out-Null; $attack = Join-Path $directory 'attack.bin'; [IO.File]::WriteAllText($attack, 'DIRECTORY-ENTRY-RACE'); $raceEvidence = [ordered]@{ attempted = $true; case_id = $CaseId; operation = 'directory_entry_substitution'; source = $attack; substitute = (Join-Path $directory 'substitute.bin') }; [IO.File]::WriteAllBytes($raceEvidence.substitute, [IO.File]::ReadAllBytes($reference)) }
        default { throw "Unknown path case: $CaseId" }
    }
    Write-JsonNew $raceEvidence (Join-Path $RunRoot ('Cases\' + $CaseId + '\race-attempt.json'))
    return [ordered]@{ attack_path = $attack; reference_path = $reference }
}
function New-DependencyFixture([string]$CaseId, [string]$RunLabel) {
    $role = 'TERMINAL_SIGNER'
    $reference = ''
    if ($CaseId -eq 'PHY-017') { $reference = 'C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework\v4.8\System.dll' }
    elseif ($CaseId -eq 'PHY-018') { $reference = 'C:\Program Files\RandleAI\TerminalAuthorityV4\RandleTerminalExecution.exe'; $role = 'EXECUTION' }
    elseif ($CaseId -eq 'PHY-019') { $reference = 'C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework\v4.8\mscorlib.dll'; $role = 'BUILD_RECEIPT' }
    if (-not $reference) { return [ordered]@{ attack_path='';claimed_component_sha256=('0' * 64);reference_path='';role=$role } }
    $root = Join-Path $executionTestRoot ($RunLabel + '\DependencyAttacks\' + $CaseId)
    if (Test-Path -LiteralPath $root) { throw "Dependency attack root already exists: $root" }
    New-Item -ItemType Directory -Path $root -Force | Out-Null
    $attack = if ($CaseId -eq 'PHY-018') { Join-Path $root 'R7UnmanifestedSideLoad.dll' } else { Join-Path $root ([IO.Path]::GetFileName($reference)) }
    [IO.File]::WriteAllBytes($attack, [Text.Encoding]::UTF8.GetBytes("R7-SUBSTITUTED-DEPENDENCY|$RunLabel|$CaseId"))
    return [ordered]@{ attack_path=$attack;claimed_component_sha256=('0' * 64);reference_path=$reference;role=$role }
}
function New-CaseFixture([object]$Case, [object]$Context, [string]$RunRoot) {
    $id = [string]$Case.case_id
    if ($id -like 'PHY-0??' -and [int]$id.Substring(4) -le 12) { return New-PathFixture $id $Context.run_label $RunRoot }
    if ($Case.driver -eq 'RECOVERY_HARNESS') { return [ordered]@{ isolated_root = (Join-Path $executionTestRoot ($Context.run_label + '\IsolatedTests\' + $id)) } }
    if ($Case.driver -eq 'ACL_PROBE' -or $Case.driver -eq 'TOKEN_PROBE' -or $Case.driver -eq 'SOURCE_PROBE') { return [ordered]@{ target_identity = ('R7_FIXED_TARGET|' + $id + '|' + $Context.run_label) } }
    if ($Case.driver -eq 'CONCURRENCY_PROBE') { return [ordered]@{ checkout_identity=$Context.checkout_identity;configuration=[ordered]@{autocrlf=$Context.autocrlf;checkout_length=$Context.checkout_length};proposal_identity=(Get-TextHash("CONCURRENCY|$id|$($Context.run_label)")) } }
    if ($Case.driver -eq 'UPGRADE_PIPE' -or $Case.driver -eq 'UPGRADE_VERIFIER') {
        if ($id -eq 'POS-020' -or $id -eq 'UPG-001') { return [ordered]@{} }
        return Invoke-ActualUpgradeAttack $id $Context $RunRoot
    }
    if ($Case.driver -eq 'DEPENDENCY_PROBE') {
        return New-DependencyFixture $id $Context.run_label
    }
    switch ($id) {
        'POS-004' { return [ordered]@{ checkout_identity = $Context.checkout_identity; configuration = [ordered]@{ autocrlf = $Context.autocrlf; checkout_length = $Context.checkout_length }; proposal_identity = (Get-TextHash("POS-004|$($Context.run_label)")) } }
        'POS-007' { return [ordered]@{ receipt_identity = $Context.bootstrap_candidate_receipt } }
        'POS-008' { return [ordered]@{ receipt_identity = $Context.bootstrap_candidate_receipt } }
        'POS-009' { $status = Get-LedgerStatus $RunRoot ('pos009-ledger-' + (New-CanonicalGuid)); return [ordered]@{ sequence = [long]$status.ledger_sequence } }
        'POS-010' { return [ordered]@{ candidate_receipt_identity = $Context.bootstrap_candidate_receipt; fresh_receipt_identity = $Context.bootstrap_fresh_receipt; reconciliation_provenance_identity = (Get-TextHash("POS-010|$($Context.run_label)")) } }
        'POS-011' { return [ordered]@{ receipt_identity = $Context.bootstrap_reconciliation_receipt } }
        'POS-012' { return [ordered]@{ receipt_identity = $Context.bootstrap_reconciliation_receipt } }
        'POS-013' { return [ordered]@{ original_request_identity = $Context.proposal_request_identity } }
        'POS-014' { return [ordered]@{ receipt_identity = $Context.bootstrap_candidate_receipt } }
        'POS-015' { return [ordered]@{ receipt_identity = $oldestRetainedReceipt } }
        'POS-016' { return [ordered]@{ sequence = 332 } }
        'POS-017' { return [ordered]@{ sequence = 678 } }
        'POS-018' { return $Context.service_stop_fixture }
        'POS-019' { return [ordered]@{ original_request_identity = $Context.proposal_request_identity } }
        'POS-022' { return [ordered]@{ request_identity = $Context.proposal_request_identity } }
        'HIS-001' { return [ordered]@{ receipt_identity = $Context.bootstrap_candidate_receipt } }
        'OUT-002' { return [ordered]@{ receipt_identity = ('0' * 64) } }
        'OUT-003' { return [ordered]@{ ledger_identity = '899e4db2b5c0f4ad58a09c682324a2ee9e5d7e2f180822ce9300922e56741d52'; trust_identity = ('0' * 64) } }
        'OUT-004' { return [ordered]@{ ledger_identity = ('0' * 64); trust_identity = 'b84a4de14577580c64ff5b2446f120aa6f9ea60faa2cb5465b495282f0273285' } }
        default { return [ordered]@{} }
    }
}
function Get-ServiceStopFixture([string]$RunRoot) {
    Stop-Service -Name 'RandleTerminalAuthority' -Force
    (Get-Service -Name 'RandleTerminalAuthority').WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Stopped, [TimeSpan]::FromSeconds(30))
    $unavailablePath = Join-Path $RunRoot 'service-unavailable-observation.json'
    $unavailable = Invoke-Harness @('service-unavailable') $unavailablePath
    Start-Service -Name 'RandleTerminalAuthority'
    (Get-Service -Name 'RandleTerminalAuthority').WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Running, [TimeSpan]::FromSeconds(30))
    $value = $unavailable.value
    if ($value.outcome -ne 'SERVICE_UNAVAILABLE') { throw 'Stopped terminal service unexpectedly accepted a connection.' }
    return [ordered]@{ client_error_code = $value.error_code; observation_time = $value.observation_time; request_frame = $value.request_frame; request_frame_sha256 = $value.request_frame_sha256 }
}
function New-BootstrapContext([string]$RunRoot, [object]$Checkout, [string]$RunKind, [string]$AutoCrlf, [string]$CheckoutLength, [string]$RunLabel) {
    $bootstrapRoot = Join-Path $RunRoot 'Bootstrap'
    New-Item -ItemType Directory -Path $bootstrapRoot | Out-Null
    $candidateGraph = Invoke-Case 'POS-001' ([ordered]@{}) (Join-Path $bootstrapRoot 'candidate-seed')
    $freshGraph = Invoke-Case 'POS-001' ([ordered]@{}) (Join-Path $bootstrapRoot 'fresh-seed')
    $candidateGraphsPath = New-CanonicalPayloadFile @($candidateGraph) (Join-Path $bootstrapRoot 'candidate-graphs.json')
    $freshGraphsPath = New-CanonicalPayloadFile @($freshGraph) (Join-Path $bootstrapRoot 'fresh-graphs.json')
    $candidateRequest = New-CanonicalGuid; $freshRequest = New-CanonicalGuid
    $candidateProvenance = Get-TextHash("BOOTSTRAP-CANDIDATE|$RunLabel|$candidateRequest")
    $freshProvenance = Get-TextHash("BOOTSTRAP-FRESH|$RunLabel|$freshRequest")
    $candidate = Invoke-Harness @('submit-run','BOOTSTRAP_CANDIDATE',$Checkout.checkout_identity,$candidateProvenance,$AutoCrlf,$CheckoutLength,$candidateGraphsPath,$candidateRequest) (Join-Path $bootstrapRoot 'candidate-receipt.outer.json')
    $fresh = Invoke-Harness @('submit-run','BOOTSTRAP_FRESH',$Checkout.checkout_identity,$freshProvenance,$AutoCrlf,$CheckoutLength,$freshGraphsPath,$freshRequest) (Join-Path $bootstrapRoot 'fresh-receipt.outer.json')
    $candidateReceipt = (Get-Response $candidate).receipt_identity
    $freshReceipt = (Get-Response $fresh).receipt_identity
    $reconciliationProvenance = Get-TextHash("BOOTSTRAP-RECONCILIATION|$RunLabel|$candidateReceipt|$freshReceipt")
    $reconciliation = Invoke-Harness @('reconcile',$candidateReceipt,$freshReceipt,$reconciliationProvenance) (Join-Path $bootstrapRoot 'reconciliation.outer.json')
    $reconciliationResponse = Get-Response $reconciliation
    if ($reconciliationResponse.full_case_registry -ne $false) { throw 'Bootstrap reconciliation incorrectly claimed full authority.' }
    $proposal = Invoke-TerminalProposal $bootstrapRoot 'transaction-seed' $Checkout.checkout_identity $AutoCrlf $CheckoutLength
    $serviceStop = Get-ServiceStopFixture $bootstrapRoot
    return [ordered]@{
        autocrlf = $AutoCrlf
        bootstrap_candidate_receipt = $candidateReceipt
        bootstrap_fresh_receipt = $freshReceipt
        bootstrap_reconciliation_receipt = $reconciliationResponse.receipt_identity
        checkout_identity = $Checkout.checkout_identity
        checkout_length = $CheckoutLength
        proposal_request_identity = $proposal.request_identity
        run_kind = $RunKind
        run_label = $RunLabel
        service_stop_fixture = $serviceStop
        transaction_probe = $proposal
    }
}
function Invoke-CompleteRun([object[]]$Cases, [string]$ConfigRoot, [string]$RunKind, [string]$AutoCrlf, [string]$CheckoutLength) {
    $runRoot = Join-Path $ConfigRoot $RunKind.ToLowerInvariant()
    New-Item -ItemType Directory -Path $runRoot | Out-Null
    $checkout = New-FreshCheckout $ConfigRoot $RunKind $AutoCrlf $CheckoutLength
    $runLabel = ($CheckoutLength + '-' + $AutoCrlf + '-' + $RunKind.ToLowerInvariant() + '-' + (New-CanonicalGuid))
    $context = New-BootstrapContext $runRoot $checkout $RunKind $AutoCrlf $CheckoutLength $runLabel
    $caseCount = @($Cases).Count
    if ($caseCount -lt 3 -or @($Cases | Where-Object { $_.case_id -eq 'POS-005' }).Count -ne 1 -or @($Cases | Where-Object { $_.case_id -eq 'POS-006' }).Count -ne 1) { throw 'Governed case registry lacks unique outer-submission cases.' }
    $baseGraphs = [Collections.Generic.List[object]]::new()
    foreach ($case in $Cases) {
        $caseId = [string]$case.case_id
        if ($caseId -eq 'POS-005' -or $caseId -eq 'POS-006') { continue }
        $fixture = New-CaseFixture $case $context $runRoot
        $baseGraphs.Add((Invoke-Case $caseId $fixture $runRoot))
    }
    if ($baseGraphs.Count -ne ($caseCount - 2)) { throw "Nonrecursive graph count mismatch: $($baseGraphs.Count)" }
    $submissionCaseId = if ($RunKind -eq 'CANDIDATE') { 'POS-005' } else { 'POS-006' }
    $caseRunKind = if ($RunKind -eq 'CANDIDATE') { 'CASE_CANDIDATE' } else { 'CASE_FRESH' }
    $caseProvenance = Get-TextHash("OUTER-SUBMISSION-CASE|$runLabel|$submissionCaseId|$SourceCommit")
    $caseGraphInputRoot = Join-Path $executionTestRoot ($runLabel + '\SubmissionGraphs')
    New-Item -ItemType Directory -Path $caseGraphInputRoot -Force | Out-Null
    $caseGraphInputPath = New-CanonicalPayloadFile $baseGraphs.ToArray() (Join-Path $caseGraphInputRoot ($submissionCaseId + '.case-graphs.json'))
    $submissionFixture = [ordered]@{
        case_graph_path = $caseGraphInputPath
        case_graph_sha256 = Get-LowerHash $caseGraphInputPath
        checkout_identity = $checkout.checkout_identity
        configuration = [ordered]@{ autocrlf = $AutoCrlf; checkout_length = $CheckoutLength }
        provenance_identity = $caseProvenance
        run_kind = $caseRunKind
    }
    $submissionCaseGraph = Invoke-Case $submissionCaseId $submissionFixture $runRoot
    $graphs = [Collections.Generic.List[object]]::new()
    foreach ($graph in $baseGraphs) { $graphs.Add($graph) }
    $graphs.Add($submissionCaseGraph)
    if ($graphs.Count -ne ($caseCount - 1)) { throw "Complete run graph count mismatch: $($graphs.Count)" }
    $graphsPath = New-CanonicalPayloadFile $graphs.ToArray() (Join-Path $runRoot 'complete-case-graphs.json')
    $provenance = Get-TextHash("COMPLETE-RUN|$runLabel|$($checkout.checkout_identity)|$SourceCommit")
    $requestId = New-CanonicalGuid
    $submission = Invoke-Harness @('submit-run',$RunKind,$checkout.checkout_identity,$provenance,$AutoCrlf,$CheckoutLength,$graphsPath,$requestId) (Join-Path $runRoot 'terminal-run-receipt.outer.json')
    $response = Get-Response $submission
    $expectedCode = if ($RunKind -eq 'CANDIDATE') { 'CANDIDATE_GRAPH_RECORDED' } else { 'TERMINAL_RECEIPT_COMMITTED' }
    if ($response.status -ne 'COMPLETE' -or $response.result_code -ne $expectedCode -or $response.complete_case_registry -ne $true -or [int]$response.case_count -ne ($caseCount - 1)) { throw "Complete $RunKind run was not issued correctly." }
    Write-JsonNew ([ordered]@{
        artifact_type = 'R7_COMPLETE_RUN_SUMMARY'
        case_count = ($caseCount - 1)
        checkout_identity = $checkout.checkout_identity
        checkout_path = $checkout.path
        provenance_identity = $provenance
        receipt_identity = $response.receipt_identity
        request_identity = $requestId
        run_kind = $RunKind
        submission_case_id = $submissionCaseId
        submission_case_provenance_identity = $caseProvenance
        schema_version = '1.0.0'
        source_commit = $SourceCommit
        source_tree = $checkout.tree
        transaction_probe = $context.transaction_probe
    }) (Join-Path $runRoot 'run-summary.json')
    return [ordered]@{ checkout = $checkout; provenance = $provenance; receipt_identity = $response.receipt_identity; request_identity = $requestId; root = $runRoot }
}
function Capture-RoleHealth([string]$Root, [string]$Label) {
    $results = [Collections.Generic.List[object]]::new()
    foreach ($role in @('terminal','execution','observation','comparator','upgrade')) {
        $operation = if ($role -eq 'terminal') { 'GET_HEALTH' } elseif ($role -eq 'upgrade') { 'GET_UPGRADE_STATUS' } else { 'GET_ROLE_HEALTH' }
        $payload = New-PayloadFile ([ordered]@{}) (Join-Path $Root "$Label-$role.payload.json")
        $call = Invoke-Harness @('call',$role,$operation,$payload) (Join-Path $Root "$Label-$role.outer.json")
        $results.Add([ordered]@{ operation = $operation; role = $role; response = (Get-Response $call) })
    }
    return $results.ToArray()
}
function Invoke-ServiceStoppedRestartVerification([string]$Root) {
    $stoppedRoot = Join-Path $Root 'service-stopped-restart-verification'; New-Item -ItemType Directory -Path $stoppedRoot | Out-Null
    foreach ($name in @('RandleTerminalExecution','RandleTerminalObservation','RandleTerminalComparator','RandleTerminalAuthority','RandleTerminalUpgradeAuthority')) {
        Stop-Service -Name $name -Force
        (Get-Service -Name $name).WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Stopped, [TimeSpan]::FromSeconds(30))
    }
    $publicStopped = Invoke-Captured $publicVerifier @((Join-Path $stoppedRoot 'public-verification.json')) (Join-Path $stoppedRoot 'public-verifier') @(0)
    $unavailable = Invoke-Harness @('service-unavailable') (Join-Path $stoppedRoot 'terminal-unavailable.json')
    $executionPayload = New-PayloadFile ([ordered]@{}) (Join-Path $stoppedRoot 'execution-health.payload.json')
    $executionFailure = Invoke-Captured $harness @('call','execution','GET_ROLE_HEALTH',$executionPayload,(Join-Path $stoppedRoot 'execution-health.outer.json')) (Join-Path $stoppedRoot 'execution-client-fail-closed') @(1)
    foreach ($name in $terminalServices) {
        Start-Service -Name $name
        (Get-Service -Name $name).WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Running, [TimeSpan]::FromSeconds(30))
    }
    $health = Capture-RoleHealth $stoppedRoot 'after-restart-health'
    $publicRestarted = Invoke-Captured $publicVerifier @((Join-Path $stoppedRoot 'public-verification-after-restart.json')) (Join-Path $stoppedRoot 'public-verifier-after-restart') @(0)
    $status = Get-LedgerStatus $stoppedRoot 'after-restart-ledger'
    $summary = [ordered]@{
        artifact_type = 'R7_SERVICE_STOPPED_AND_RESTART_VERIFICATION'
        clients_failed_closed = ($unavailable.value.outcome -eq 'SERVICE_UNAVAILABLE' -and $executionFailure.exit_code -eq 1)
        ledger_root_after_restart = $status.ledger_root
        ledger_sequence_after_restart = $status.ledger_sequence
        public_verification_after_restart_sha256 = Get-LowerHash (Join-Path $stoppedRoot 'public-verification-after-restart.json')
        public_verification_while_stopped_sha256 = Get-LowerHash (Join-Path $stoppedRoot 'public-verification.json')
        restarted_role_health = $health
        schema_version = '1.0.0'
        services = $terminalServices
    }
    Write-JsonNew $summary (Join-Path $stoppedRoot 'summary.json')
    return $summary
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Elevation is required for dedicated-service and physical-boundary probes.' }
foreach ($required in @($repository,$casePath,$harness,$publicVerifier,$executionTestRoot)) { if (-not (Test-Path -LiteralPath $required)) { throw "Required path missing: $required" } }
if ((& $gitExecutable -c "safe.directory=$safeRepository" -C $repository cat-file -t $SourceCommit).Trim() -ne 'commit') { throw 'Source commit is not locally resolvable.' }
if (-not (Test-Path -LiteralPath 'S:\' -PathType Container)) { throw 'The governed alternate-volume attack requires S:\.' }
$evidence = Require-NewDirectory $evidence
$checkoutBaseFull = Require-NewDirectory $checkoutBaseFull
$casesArtifact = Read-Json $casePath
$declaredCaseCount = [int]$casesArtifact.independently_determined_case_count
if ($casesArtifact.expectation_artifact_read -ne $false -or $declaredCaseCount -lt 1) { throw 'Case artifact separation or count invalid.' }
$cases = @($casesArtifact.cases)
if ($cases.Count -ne $declaredCaseCount) { throw 'Case artifact row count differs from its independently enumerated count.' }
$expectationPath = Join-Path $repository "$packageRelative\immutable_expectations.json"
$expectationReadProof = [ordered]@{ artifact_path = $expectationPath; matrix_orchestrator_read = $false; request_builder_read = $false }
Write-JsonNew $expectationReadProof (Join-Path $evidence 'expectation-separation-proof.json')
$initialHealth = Capture-RoleHealth $evidence 'initial-health'
$matrixRows = [Collections.Generic.List[object]]::new()
$configurations = @(
    [ordered]@{ autocrlf = 'true'; checkout_length = 'short' },
    [ordered]@{ autocrlf = 'false'; checkout_length = 'short' },
    [ordered]@{ autocrlf = 'true'; checkout_length = 'long' },
    [ordered]@{ autocrlf = 'false'; checkout_length = 'long' }
)
foreach ($configuration in $configurations) {
    $configurationLabel = $configuration.checkout_length + '-autocrlf-' + $configuration.autocrlf
    $configurationRoot = Join-Path $evidence $configurationLabel
    New-Item -ItemType Directory -Path $configurationRoot | Out-Null
    $candidate = Invoke-CompleteRun $cases $configurationRoot 'CANDIDATE' $configuration.autocrlf $configuration.checkout_length
    $fresh = Invoke-CompleteRun $cases $configurationRoot 'FRESH' $configuration.autocrlf $configuration.checkout_length
    if ($candidate.checkout.checkout_identity -eq $fresh.checkout.checkout_identity -or $candidate.provenance -eq $fresh.provenance -or $candidate.receipt_identity -eq $fresh.receipt_identity) { throw 'Candidate/fresh provenance is not disjoint.' }
    $reconciliationProvenance = Get-TextHash("FULL-RECONCILIATION|$configurationLabel|$($candidate.receipt_identity)|$($fresh.receipt_identity)")
    $reconciliation = Invoke-Harness @('reconcile',$candidate.receipt_identity,$fresh.receipt_identity,$reconciliationProvenance) (Join-Path $configurationRoot 'full-reconciliation.outer.json')
    $reconciliationResponse = Get-Response $reconciliation
    if ($reconciliationResponse.status -ne 'COMPLETE' -or $reconciliationResponse.result_code -ne 'RECONCILIATION_COMMITTED' -or $reconciliationResponse.full_case_registry -ne $true) { throw "Full reconciliation failed: $configurationLabel" }
    $publicPath = Join-Path $configurationRoot 'public-verification.json'
    $publicCapture = Invoke-Captured $publicVerifier @($publicPath) (Join-Path $configurationRoot 'public-verifier') @(0)
    $matrixRows.Add([ordered]@{
        autocrlf = $configuration.autocrlf
        candidate_checkout_identity = $candidate.checkout.checkout_identity
        candidate_receipt_identity = $candidate.receipt_identity
        checkout_length = $configuration.checkout_length
        fresh_checkout_identity = $fresh.checkout.checkout_identity
        fresh_receipt_identity = $fresh.receipt_identity
        public_verification_sha256 = Get-LowerHash $publicPath
        reconciliation_receipt_identity = $reconciliationResponse.receipt_identity
        reconciliation_provenance_identity = $reconciliationProvenance
    })
}
$restart = Invoke-ServiceStoppedRestartVerification $evidence
$finalHealth = Capture-RoleHealth $evidence 'final-health'
$finalStatus = Get-LedgerStatus $evidence 'final-ledger-status'
$summary = [ordered]@{
    artifact_type = 'R7_REMEDIATION_CANDIDATE_FRESH_MATRIX'
    case_count = $declaredCaseCount
    candidate_run_count = 4
    configurations = $matrixRows.ToArray()
    expectation_artifact_read_by_matrix_or_request_builder = $false
    final_ledger_root = $finalStatus.ledger_root
    final_ledger_sequence = $finalStatus.ledger_sequence
    final_role_health = $finalHealth
    fresh_run_count = 4
    initial_role_health = $initialHealth
    matrix_status = 'PASS'
    prohibited_source_evidence_reused = $false
    reconciliation_count = 4
    schema_version = '1.0.0'
    service_stopped_restart = $restart
    source_commit = $SourceCommit
}
Write-JsonNew $summary (Join-Path $evidence 'matrix-summary.json')
Write-Output ($summary | ConvertTo-Json -Depth 20)
