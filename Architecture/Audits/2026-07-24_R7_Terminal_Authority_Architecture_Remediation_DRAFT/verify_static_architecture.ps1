[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string]$CompiledRoleRoot,
    [string]$StaticBuildRoot,
    [string]$Unit2BuildRoot,
    [string]$Unit2ClosureReport,
    [string]$TransactionProbeRoot,
    [string]$RecoveryProbeRoot,
    [string]$LegacySnapshotRoot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$packageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $packageRoot '..\..\..'))
$safeRepository = $repositoryRoot.Replace('\','/')
$gitExecutable = 'C:\Program Files\Git\cmd\git.exe'
$checks = [Collections.Generic.List[object]]::new()

function Add-Check([string]$Name, [bool]$Passed, [object]$Evidence) {
    $checks.Add([ordered]@{ evidence = $Evidence; name = $Name; status = $(if ($Passed) { 'PASS' } else { 'FAIL' }) })
    if (-not $Passed) { throw "Static architecture check failed: $Name" }
}
function Read-Json([string]$Path) { return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json }
function Read-JsonText([string]$Text) { return $Text | ConvertFrom-Json }
function Get-LowerHash([string]$Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function Get-GitBlobIdentity([string]$Path) {
    $bytes=[IO.File]::ReadAllBytes($Path);$header=[Text.Encoding]::ASCII.GetBytes(('blob '+$bytes.Length+[char]0));$all=New-Object byte[] ($header.Length+$bytes.Length)
    [Buffer]::BlockCopy($header,0,$all,0,$header.Length);[Buffer]::BlockCopy($bytes,0,$all,$header.Length,$bytes.Length);$sha=[Security.Cryptography.SHA1]::Create()
    try{return ([BitConverter]::ToString($sha.ComputeHash($all))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
}
function Git-Lines([string[]]$Arguments) {
    $value = @(& $gitExecutable -c "safe.directory=$safeRepository" -C $repositoryRoot @Arguments)
    if ($LASTEXITCODE -ne 0) { throw "git failed: $($Arguments -join ' ')" }
    return $value
}
function Require-GitObject([string]$Identity, [string]$Type) {
    $actual = ([string](Git-Lines @('cat-file','-t',$Identity))).Trim()
    Add-Check ("git-object-" + $Identity) ($actual -eq $Type) ([ordered]@{ actual_type = $actual; expected_type = $Type; identity = $Identity })
}
function Parse-PowerShell([string]$Path) {
    $tokens = $null; $errors = $null
    [Management.Automation.Language.Parser]::ParseFile($Path,[ref]$tokens,[ref]$errors) | Out-Null
    return @($errors)
}
function Write-JsonNew([object]$Value, [string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if (Test-Path -LiteralPath $full) { throw "Refusing verification overwrite: $full" }
    $parent = Split-Path -Parent $full
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
    [IO.File]::WriteAllText($full, ($Value | ConvertTo-Json -Depth 100), [Text.UTF8Encoding]::new($false))
}

$immutableObjects = [ordered]@{
    '87d066eb16d7fe0b6a1677ea7739c5c2ead4ad94' = 'commit'
    '343622743668d7ddc524513307e726f20d1db9fc' = 'blob'
    '06c6805ed52a0d539a73088c097c60dec335462a' = 'commit'
    '1be3b0b5f15ac8e68b88202e0e9d3787b69d1856' = 'blob'
    '8ec5697b3c6fd9d93b972113b7e79d033b4cb1f6' = 'commit'
    'dfa98a89049b9596387143c002252d91d608fbfc' = 'blob'
    'bb04ac54fb328516d0c785f4e6551e6a20d73759' = 'commit'
    '9d813a4bad29ec04f022f54ffcae73a5d542eb44' = 'commit'
    'f0cfbce97e913a133530dd66a70326b1e03a0fb6' = 'commit'
}
foreach ($entry in $immutableObjects.GetEnumerator()) { Require-GitObject $entry.Key $entry.Value }
$head = ([string](Git-Lines @('rev-parse','HEAD'))).Trim()
& $gitExecutable -c "safe.directory=$safeRepository" -C $repositoryRoot merge-base --is-ancestor '9d813a4bad29ec04f022f54ffcae73a5d542eb44' $head
Add-Check 'independent-rejection-preserved-in-ancestry' ($LASTEXITCODE -eq 0) ([ordered]@{ head = $head; required_ancestor = '9d813a4bad29ec04f022f54ffcae73a5d542eb44' })
foreach ($forbidden in @('06c6805ed52a0d539a73088c097c60dec335462a','8ec5697b3c6fd9d93b972113b7e79d033b4cb1f6','f0cfbce97e913a133530dd66a70326b1e03a0fb6')) {
    & $gitExecutable -c "safe.directory=$safeRepository" -C $repositoryRoot merge-base --is-ancestor $forbidden $head
    Add-Check ("forbidden-ancestry-absent-" + $forbidden) ($LASTEXITCODE -ne 0) ([ordered]@{ forbidden = $forbidden; head = $head })
}
$reviewFiles = @(Git-Lines @('ls-tree','-r','--name-only','9d813a4bad29ec04f022f54ffcae73a5d542eb44','--','Architecture/Audits/2026-07-23_R7_Independent_Terminal_Authority_Acceptance_Review/'))
Add-Check 'independent-review-package-count' ($reviewFiles.Count -eq 30) ([ordered]@{ count = $reviewFiles.Count; paths = $reviewFiles })

$requirementPath = Join-Path $packageRoot 'governed_requirement_registry.json'
$casePath = Join-Path $packageRoot 'immutable_case_definitions.json'
$expectationPath = Join-Path $packageRoot 'immutable_expectations.json'
$coveragePath = Join-Path $packageRoot 'exact_byte_coverage_proof.json'
$historyPath = Join-Path $packageRoot 'historical_classification_registry.json'
$manifestPath = Join-Path $packageRoot 'AuthoritySources\authority_source_manifest.json'
$scriptRegistryPath = Join-Path $packageRoot 'governed_script_registry.json'
$utilityRegistryPath = Join-Path $packageRoot 'external_utility_registry.json'
$sourceRolePath = Join-Path $packageRoot 'source_role_registry.json'
$requirements = Read-Json $requirementPath
$cases = Read-Json $casePath
$expectations = Read-Json $expectationPath
$coverage = Read-Json $coveragePath
$history = Read-Json $historyPath
$scriptRegistry = Read-Json $scriptRegistryPath
$utilityRegistry = Read-Json $utilityRegistryPath
$sourceRoleRegistry = Read-Json $sourceRolePath
$declaredRequirementCount = [int]$requirements.governing_requirement_count
$declaredCaseCount = [int]$cases.independently_determined_case_count
$declaredExpectationCount = [int]$expectations.expectation_count
Add-Check 'governed-requirement-count' ($declaredRequirementCount -gt 0 -and @($requirements.requirements).Count -eq $declaredRequirementCount -and [int]$coverage.governing_requirement_count -eq $declaredRequirementCount) ([ordered]@{ count = @($requirements.requirements).Count; declared = $declaredRequirementCount; sha256 = (Get-LowerHash $requirementPath) })
Add-Check 'independently-authored-case-count' ($declaredCaseCount -gt 0 -and @($cases.cases).Count -eq $declaredCaseCount -and [int]$coverage.case_count -eq $declaredCaseCount -and $cases.expectation_artifact_read -eq $false) ([ordered]@{ count = @($cases.cases).Count; declared = $declaredCaseCount; sha256 = (Get-LowerHash $casePath) })
Add-Check 'independently-authored-expectation-count' ($declaredExpectationCount -eq $declaredCaseCount -and @($expectations.expectations).Count -eq $declaredExpectationCount -and [int]$coverage.expectation_count -eq $declaredExpectationCount -and $expectations.case_artifact_read -eq $false -and $expectations.runtime_evidence_read -eq $false) ([ordered]@{ count = @($expectations.expectations).Count; declared = $declaredExpectationCount; sha256 = (Get-LowerHash $expectationPath) })
Add-Check 'coverage-zero-gaps' ([int]$coverage.unmapped_governing_requirement_count -eq 0 -and [int]$coverage.unauthorized_normative_case_count -eq 0 -and [int]$coverage.prohibited_source_reference_count -eq 0) ([ordered]@{ sha256 = (Get-LowerHash $coveragePath); unauthorized = $coverage.unauthorized_normative_case_count; unmapped = $coverage.unmapped_governing_requirement_count })
$sequence332 = @($history.rules | Where-Object { $_.PSObject.Properties.Name -contains 'original_sequence' -and $_.original_sequence -eq 332 })[0]
$sequence678 = @($history.rules | Where-Object { $_.PSObject.Properties.Name -contains 'original_sequence' -and $_.original_sequence -eq 678 })[0]
Add-Check 'historical-classification-registry-bound' ($sequence332.classification -eq 'INCOMPLETE_ISSUANCE_SUPERSEDED_NONAUTHORITY' -and $sequence678.classification -eq 'ABORTED_CLIENT_REJECTED_ISSUANCE_NONAUTHORITY') ([ordered]@{ sha256 = (Get-LowerHash $historyPath); sequence_332 = $sequence332; sequence_678 = $sequence678 })
$ambiguityRule = @($history.rules | Where-Object { $_.PSObject.Properties.Name -contains 'records' })[0]
$boundSequences = @($ambiguityRule.records | ForEach-Object { [long]$_.original_sequence })
$expectedAmbiguousSequences = @(326L,329L,332L,335L,375L,378L,381L,544L,547L,678L)
$exactSequenceOrder = ($boundSequences.Count -eq $expectedAmbiguousSequences.Count)
for ($index = 0; $exactSequenceOrder -and $index -lt $expectedAmbiguousSequences.Count; $index++) { if ($boundSequences[$index] -ne $expectedAmbiguousSequences[$index]) { $exactSequenceOrder = $false } }
$completeHistoricalBindings = @($ambiguityRule.records | Where-Object { $_.original_entry_identity -notmatch '^[0-9a-f]{64}$' -or $_.original_entry_hash -notmatch '^[0-9a-f]{64}$' -or $_.original_signed_issuance_receipt_identity -notmatch '^[0-9a-f]{64}$' -or $_.original_terminal_receipt_identity -ne 'ABSENT' -or $_.original_client_response_identity -ne 'ABSENT' -or $_.reuse -ne 'PERMANENTLY_FORBIDDEN' }).Count -eq 0
Add-Check 'ten-ambiguous-historical-issuances-exactly-bound' ($exactSequenceOrder -and $completeHistoricalBindings) ([ordered]@{ bound_sequences = $boundSequences; classification = $ambiguityRule.classification; record_count = @($ambiguityRule.records).Count })

$badCaseAuthority = [Collections.Generic.List[object]]::new()
foreach ($case in @($cases.cases)) {
    if ($case.request_recipe.include_expectation_fields -ne $false -or $case.request_recipe.include_desired_result -ne $false) { $badCaseAuthority.Add([ordered]@{ case_id = $case.case_id; reason = 'EXPECTATION_COUPLED_RECIPE' }) }
    foreach ($authority in @($case.authority_refs)) {
        if ($authority.governing_commit -eq 'f0cfbce97e913a133530dd66a70326b1e03a0fb6' -or [string]::IsNullOrWhiteSpace([string]$authority.clause_raw_sha256) -or [string]::IsNullOrWhiteSpace([string]$authority.line_range)) { $badCaseAuthority.Add([ordered]@{ case_id = $case.case_id; reason = 'UNRESOLVED_OR_PROHIBITED_AUTHORITY' }) }
    }
}
Add-Check 'case-authority-and-request-separation' ($badCaseAuthority.Count -eq 0) $badCaseAuthority.ToArray()
$actualRunIdentityLeak = @($expectations.expectations | Where-Object { $_.PSObject.Properties.Name -contains 'actual_run_identity' -or $_.PSObject.Properties.Name -contains 'observed_value' })
Add-Check 'expectations-free-of-current-run-identities' ($actualRunIdentityLeak.Count -eq 0) ([ordered]@{ leak_count = $actualRunIdentityLeak.Count })

$sourceRoot = Join-Path $packageRoot 'Source'
$sourceFiles = @(Get-ChildItem -LiteralPath $sourceRoot -File | Sort-Object Name)
Add-Check 'authority-runtime-source-language-closure' (@($sourceFiles | Where-Object Extension -ne '.cs').Count -eq 0) ([ordered]@{ source_count = $sourceFiles.Count; extensions = @($sourceFiles.Extension | Sort-Object -Unique) })
$sourceRoutes = @($sourceRoleRegistry.sources)
$actualSourceNames = @($sourceFiles | ForEach-Object Name | Sort-Object)
$routeSourceNames = @($sourceRoutes | ForEach-Object { Split-Path -Leaf ([string]$_.path) } | Sort-Object)
$badSourceRoutes = [Collections.Generic.List[object]]::new()
foreach($route in $sourceRoutes){
    $path=Join-Path $packageRoot ([string]$route.path).Replace('/','\')
    if(-not(Test-Path -LiteralPath $path -PathType Leaf) -or (Get-LowerHash $path) -cne [string]$route.raw_sha256 -or (Get-GitBlobIdentity $path) -cne [string]$route.git_blob_identity -or [string]$route.mode -cne '100644' -or @($route.requirement_ids).Count -eq 0 -or @($route.blocker_ids).Count -eq 0 -or @($route.architecture_roles).Count -eq 0 -or @($route.expected_verification).Count -eq 0 -or @($route.compiled_into_roles).Count -eq 0){$badSourceRoutes.Add($route)}
}
Add-Check 'all-source-files-have-complete-reverse-trace-routing' ([int]$sourceRoleRegistry.source_count -eq $sourceFiles.Count -and ($actualSourceNames -join "`n") -ceq ($routeSourceNames -join "`n") -and $badSourceRoutes.Count -eq 0 -and $routeSourceNames -contains 'R7MeasuredUtility.cs' -and $routeSourceNames -contains 'R7ServiceBoundary.cs' -and $routeSourceNames -contains 'R7RecoveryProbeAuditor.cs') ([ordered]@{bad_routes=$badSourceRoutes.ToArray();source_count=$sourceFiles.Count;source_role_registry_sha256=(Get-LowerHash $sourceRolePath)})
$signerSource = Get-Content -Raw -LiteralPath (Join-Path $sourceRoot 'R7TerminalSignerService.cs')
$signerLaunchTokens = @(@('CreateProcess(?:W)?\s*\(','Process\.Start\s*\(','CREATEPROCESS_DEFAULT_CALLER_TOKEN') | Where-Object { $signerSource -match $_ })
Add-Check 'signer-does-not-launch-semantic-children' ($signerLaunchTokens.Count -eq 0) ([ordered]@{ detected_tokens = $signerLaunchTokens })
$infrastructureSource = Get-Content -Raw -LiteralPath (Join-Path $sourceRoot 'R7ServiceInfrastructure.cs')
Add-Check 'signer-derives-principal-and-concurrency-facts-from-os' ($signerSource.Contains('SERVER_OS_PROBE_UNDER_PIPE_CLIENT_IMPERSONATION') -and $signerSource.Contains('CHILD_PROBE_REPORT_CONFLICT') -and $signerSource.Contains('DuplicateTokenExForProbe') -and $signerSource.Contains('OPEN_CNG_KEY_AND_SIGN_ARBITRARY_BYTES') -and $signerSource.Contains('OS_CONCURRENT_CONNECTION_NOT_OBSERVED') -and $infrastructureSource.Contains('RunAsCaller') -and $infrastructureSource.Contains('ConcurrentConnectionCountAtReceive')) ([ordered]@{ infrastructure_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7ServiceInfrastructure.cs'));signer_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7TerminalSignerService.cs')) })
$mandatoryExpandedCases = @('PRI-010','PRI-011','PRI-012','PRI-013','PRI-014','PRI-015','PAR-014','PAR-015','PAR-016','PAR-017','PAR-018','PAR-019','PAR-020','OUT-001','OUT-002','OUT-003','OUT-004','CON-001','CON-002')
$expandedCaseIds = @($cases.cases | ForEach-Object case_id)
Add-Check 'expanded-explicit-boundary-attacks-authored' (@($mandatoryExpandedCases | Where-Object { $_ -notin $expandedCaseIds }).Count -eq 0) ([ordered]@{ case_ids=$mandatoryExpandedCases;case_registry_sha256=(Get-LowerHash $casePath) })
$protocolSource = Get-Content -Raw -LiteralPath (Join-Path $sourceRoot 'R7CoreJsonProtocol.cs')
Add-Check 'strict-framed-protocol-source-present' ($protocolSource.Contains('MaximumFrameBytes = 65536') -and $protocolSource.Contains('MaximumPayloadBytes = MaximumFrameBytes - FrameHeaderBytes') -and $protocolSource.Contains('ProtocolVersion = "4.0"') -and $protocolSource.Contains('FrameHeaderBytes = 12')) ([ordered]@{ protocol_source_sha256 = Get-LowerHash (Join-Path $sourceRoot 'R7CoreJsonProtocol.cs') })
$roleSource = Get-Content -Raw -LiteralPath (Join-Path $sourceRoot 'R7RoleServices.cs')
Add-Check 'producer-expectation-artifact-not-loaded' (-not $roleSource.Contains('new R7AuthoritySet') -and $roleSource.Contains('expectation_artifact_read", false')) ([ordered]@{ role_source_sha256 = Get-LowerHash (Join-Path $sourceRoot 'R7RoleServices.cs') })
$matrixSource = Get-Content -Raw -LiteralPath (Join-Path $packageRoot 'run_fresh_matrix.ps1')
$expectationRequestTokens = @(@('expected_path','expected_sha256','$expectedSha','$expected =') | Where-Object { $matrixSource.Contains($_) -or $roleSource.Contains($_) -or $signerSource.Contains($_) })
Add-Check 'outer-requests-contain-no-expected-evidence' ($expectationRequestTokens.Count -eq 0) ([ordered]@{detected_tokens=$expectationRequestTokens})
$runtimeForbiddenInvocation = [Collections.Generic.List[string]]::new()
foreach ($sourceFile in $sourceFiles) {
    $text = Get-Content -Raw -LiteralPath $sourceFile.FullName
    if ($text -match '(?is)(?:FileName\s*=|Process\.Start\s*\()[^;\r\n]*(?:python(?:\.exe)?|git\.exe|libgit)') { $runtimeForbiddenInvocation.Add($sourceFile.Name) }
}
$controlledProcessLaunches = $roleSource.Contains('start.FileName = R7BuildIdentity.ExecutionBinaryPath') -and $roleSource.Contains('--r7-restricted-descendant-probe') -and $matrixSource.Contains('RandleTerminalPublicVerifier.exe')
Add-Check 'python-and-git-removed-from-runtime-authority' ($runtimeForbiddenInvocation.Count -eq 0 -and $controlledProcessLaunches) ([ordered]@{ controlled_fixed_process_launches = $controlledProcessLaunches; forbidden_files = $runtimeForbiddenInvocation.ToArray() })
$safeFileSource = Get-Content -Raw -LiteralPath (Join-Path $sourceRoot 'R7SafeFile.cs')
$upgradeSource = Get-Content -Raw -LiteralPath (Join-Path $sourceRoot 'R7UpgradeAuthorityService.cs')
$publicVerifierSource = Get-Content -Raw -LiteralPath (Join-Path $sourceRoot 'R7PublicVerifier.cs')
Add-Check 'signing-key-file-metadata-held-through-service-life' ($safeFileSource.Contains('HoldMetadataFile') -and $signerSource.Contains('TerminalKeyFileSecurityDescriptorSha256') -and $upgradeSource.Contains('UpgradeKeyFileSecurityDescriptorSha256') -and $signerSource.Contains('signingKeyFile.Dispose()') -and $upgradeSource.Contains('signingKeyFile.Dispose()')) ([ordered]@{safe_file_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7SafeFile.cs'));terminal_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7TerminalSignerService.cs'));upgrade_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7UpgradeAuthorityService.cs'))})
Add-Check 'upgrade-prepared-record-recovery-is-ledger-bound' ($upgradeSource.Contains('RecoverPreparedRecord') -and $upgradeSource.Contains('CONFLICTING_UPGRADE_AUTHORIZATION_RETRY') -and $upgradeSource.Contains('UPGRADE_RECORD_NOT_COMMITTED') -and $publicVerifierSource.Contains('UPGRADE_AUTHORIZATION_RAW_EVIDENCE_INVALID')) ([ordered]@{public_verifier_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7PublicVerifier.cs'));upgrade_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7UpgradeAuthorityService.cs'))})
$buildSource = Get-Content -Raw -LiteralPath (Join-Path $packageRoot 'build_remediation_package.ps1')
$syntheticUpgradeTokens = @(@('PROBE_UPGRADE_POLICY','ProbeUpgradePolicy','claimed_new_interface','worker_identity_matches') | Where-Object { $upgradeSource.Contains($_) -or $roleSource.Contains($_) })
Add-Check 'upgrade-attacks-use-real-authorization-interface' ($syntheticUpgradeTokens.Count -eq 0 -and $matrixSource.Contains("Invoke-ActualUpgradeAttack") -and $matrixSource.Contains("'AUTHORIZE_TERMINAL_UPGRADE'") -and $upgradeSource.Contains('R7_UPGRADE_AUTHORITY_SERVER_CAPTURED_INTERACTION') -and $signerSource.Contains('UPGRADE_SERVER_CAPTURE_MISMATCH')) ([ordered]@{synthetic_tokens=$syntheticUpgradeTokens;matrix_sha256=(Get-LowerHash (Join-Path $packageRoot 'run_fresh_matrix.ps1'));upgrade_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7UpgradeAuthorityService.cs'))})
Add-Check 'upgrade-component-identities-embedded-before-final-authority-build' ($upgradeSource.Contains('ExpectedSha256') -and $upgradeSource.Contains('COMPONENT_SET_MISMATCH') -and $buildSource.Contains('Finalize the non-circular upgrade policy') -and $buildSource.Contains('FinalPassA') -and $buildSource.Contains('upgrade_authority_build_receipt')) ([ordered]@{build_script_sha256=(Get-LowerHash (Join-Path $packageRoot 'build_remediation_package.ps1'));upgrade_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7UpgradeAuthorityService.cs'))})
Add-Check 'service-binaries-held-and-policy-bound-through-life' ($signerSource.Contains('signingBinaryFile') -and $signerSource.Contains('signingBinaryFile.Dispose()') -and $roleSource.Contains('R7ActiveUpgrade.ResolveAuthorization("EXECUTION")') -and $roleSource.Contains('R7ActiveUpgrade.ResolveAuthorization("OBSERVATION")') -and $roleSource.Contains('R7ActiveUpgrade.ResolveAuthorization("COMPARATOR")') -and $roleSource.Contains('binaryFile.Dispose()') -and $upgradeSource.Contains('serviceBinaryFile.Dispose()')) ([ordered]@{roles_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7RoleServices.cs'));signer_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7TerminalSignerService.cs'));upgrade_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7UpgradeAuthorityService.cs'))})
$installSource = Get-Content -Raw -LiteralPath (Join-Path $packageRoot 'install_authorized_transition.ps1')
$provisionSource = Get-Content -Raw -LiteralPath (Join-Path $packageRoot 'provision_upgrade_authority.ps1')
Add-Check 'build-time-toolchain-recursively-content-bound' ($buildSource.Contains('directory-manifest') -and $buildSource.Contains('Git installation changed while resolving immutable source objects') -and $buildSource.Contains('BOOTSTRAP_ARTIFACT_TOOL') -and $buildSource.Contains('normalized_il_equal=$true')) ([ordered]@{build_script_sha256=(Get-LowerHash (Join-Path $packageRoot 'build_remediation_package.ps1'))})
$installLines = @($installSource -split '\r?\n')
$terminalRootAclLine = @($installLines | Where-Object { $_.Contains('@($remediationRoot') })[0]
$upgradeStateAclLine = @($installLines | Where-Object { $_.Contains('@($upgradeStateRoot') -and $_.Contains('/inheritance:r') })[0]
$provisionRootAclPass = $provisionSource.Contains('Assert-DedicatedDirectoryAcl') -and $provisionSource.Contains('Assert-PublicCertificateAcl') -and $provisionSource.Contains('$immutableDirectories') -and $provisionSource.Contains('$mutableDirectories') -and $provisionSource.Contains('Dedicated authority directory principal set differs') -and $provisionSource.Contains("`$takeownExecutable = 'C:\Windows\System32\takeown.exe'") -and $provisionSource.Contains('$ExpectedFourthFailedAttemptSha256') -and $provisionSource.Contains('recovered_acl_mutation_in_current_attempt = $false') -and $provisionSource.Contains('$allowedAdminRights') -and -not $provisionSource.Contains('Invoke-Checked $takeownExecutable')
$immutableRootAclPass = $terminalRootAclLine.Contains('$terminalAccount`:(OI)(CI)(RX)') -and $upgradeStateAclLine.Contains('$upgradeAccount`:(OI)(CI)(RX)') -and $provisionRootAclPass
Add-Check 'immutable-authority-and-policy-roots-are-read-only-to-signers' $immutableRootAclPass ([ordered]@{install_sha256=(Get-LowerHash (Join-Path $packageRoot 'install_authorized_transition.ps1'));provision_sha256=(Get-LowerHash (Join-Path $packageRoot 'provision_upgrade_authority.ps1'));terminal_root_acl=$terminalRootAclLine;upgrade_state_acl=$upgradeStateAclLine})

$scriptErrors = [Collections.Generic.List[object]]::new()
$packageScripts = @(Get-ChildItem -LiteralPath $packageRoot -Filter '*.ps1' -File | Sort-Object Name)
foreach ($script in $packageScripts) {
    foreach ($error in @(Parse-PowerShell $script.FullName)) { $scriptErrors.Add([ordered]@{ message = $error.Message; path = $script.FullName; line = $error.Extent.StartLineNumber }) }
}
Add-Check 'powershell-orchestrators-parse' ($scriptErrors.Count -eq 0) $scriptErrors.ToArray()
$ambiguousTestPath=[Collections.Generic.List[object]]::new()
foreach($script in $packageScripts){$text=Get-Content -LiteralPath $script.FullName -Raw;if($text -match 'Test-Path\s+-LiteralPath[^\r\n]+\s-(?:or|and)\s+Test-Path'){$ambiguousTestPath.Add([ordered]@{path=$script.Name})}}
Add-Check 'powershell-test-path-boolean-expressions-are-unambiguous' ($ambiguousTestPath.Count -eq 0) $ambiguousTestPath.ToArray()
$unit2bInstallerPath=Join-Path $packageRoot 'complete_unit2_upgrade_authority.ps1'
$unit2bInstaller=Get-Content -LiteralPath $unit2bInstallerPath -Raw
$unit2bForbidden=[Collections.Generic.List[string]]::new()
foreach($pattern in @("@\('start'",'Start-Service','Stop-Service','Restart-Service','CngKey','SignData','SignHash','New-SelfSignedCertificate','UPGRADE_LEDGER_GENESIS','AUTHORIZE_TERMINAL_TRANSITION\s*\)')){if($unit2bInstaller -match $pattern){$unit2bForbidden.Add($pattern)}}
$failureActionLegacy=@("RunScMutation @('failure'","RunScMutation @('failureflag'","@('qfailure'","@('qfailureflag'","'actions=',''")
$failureActionLegacyFindings=@($failureActionLegacy|Where-Object{$unit2bInstaller.Contains($_)})
Add-Check 'unit2b-installer-is-stopped-prestart-only-and-rollback-bound' ($unit2bForbidden.Count -eq 0 -and $failureActionLegacyFindings.Count -eq 0 -and $unit2bInstaller.Contains('[Parameter(Mandatory=$true)][switch]$PreStartOnly') -and $unit2bInstaller.Contains('Only the explicit PreStartOnly path is exposed') -and $unit2bInstaller.Contains("RunEvidenceTool @('capture-failure-actions'") -and $unit2bInstaller.Contains("RunEvidenceTool @('configure-failure-actions-none'") -and $unit2bInstaller.Contains("RunEvidenceTool @('verify-failure-actions-none'") -and $unit2bInstaller.Contains("RunEvidenceTool @('restore-failure-actions'") -and $unit2bInstaller.Contains('RunEvidenceTool @(''service-boundary''') -and $unit2bInstaller.Contains('RunEvidenceTool @(''restore-service-boundary''') -and $unit2bInstaller.Contains("`$aclSnapshots.Add") -and $unit2bInstaller.Contains('Set-Acl -LiteralPath') -and $unit2bInstaller.Contains("'ROLLBACK_SCM_CONFIG'") -and $unit2bInstaller.Contains("'ROLLBACK_SCM_SID_TYPE'") -and $unit2bInstaller.Contains("'ROLLBACK_SCM_PRIVILEGES'") -and $unit2bInstaller.Contains('$failureActionsRestoreRequired=$true') -and $unit2bInstaller.Contains('service_started=$false') -and $unit2bInstaller.Contains('terminal_transition_authorized=$false')) ([ordered]@{failure_action_legacy_findings=$failureActionLegacyFindings;forbidden_tokens=$unit2bForbidden.ToArray();installer_sha256=(Get-LowerHash $unit2bInstallerPath)})
$installContractPath=Join-Path $packageRoot 'unit2_stopped_install_contract.json'
$installMapVerifierPath=Join-Path $packageRoot 'verify_unit2_install_map_evidence.ps1'
$installContract=Read-Json $installContractPath
$installMapVerifier=Get-Content -LiteralPath $installMapVerifierPath -Raw
$installIds=@($installContract.install_items|ForEach-Object{[string]$_.id}|Sort-Object)
$requiredInstallIds=@('BUILD_MANIFEST','DEPENDENCY_MANIFEST','DETERMINISM_RECEIPT','PACKAGE_MANIFEST','PACKAGED_ARTIFACT_TOOL','PACKAGED_PROTECTED_METADATA_TOOL','PUBLIC_CERTIFICATE','SOURCE_TO_BINARY_RECEIPT','UPGRADE_AUTHORITY','UPGRADE_CLIENT','UPGRADE_POLICY','UPGRADE_PROTOCOL_PROBE','UPGRADE_PUBLIC_VERIFIER')|Sort-Object
$installMapPass=@($installContract.install_items).Count -eq 13 -and (($installIds-join "`n") -ceq ($requiredInstallIds-join "`n")) -and @($installContract.install_items.source_path|Sort-Object -Unique).Count -eq 13 -and @($installContract.install_items.destination_path|Sort-Object -Unique).Count -eq 13 -and [string]$installContract.evidence_policy.fixed_root -ceq 'C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Evidence' -and [string]$installContract.evidence_policy.unexpected_existing_evidence_policy -ceq 'REJECT' -and @($installContract.evidence_policy.preserved_records).Count -eq 2 -and $unit2bInstaller.Contains('$installContract.install_items') -and $unit2bInstaller.Contains('WriteExclusiveBytes') -and $unit2bInstaller.Contains('AssertEvidenceSnapshot') -and -not $unit2bInstaller.Contains('evidence parent must not exist before installation') -and $installMapVerifier.Contains("test_count=`$results.Count")
Add-Check 'unit2b-install-map-and-append-safe-evidence-are-explicit-and-regressed' $installMapPass ([ordered]@{contract_sha256=(Get-LowerHash $installContractPath);install_ids=$installIds;regression_verifier_sha256=(Get-LowerHash $installMapVerifierPath)})
$failureActionSourcePath=Join-Path $sourceRoot 'R7ServiceFailureActions.cs'
$failureActionVerifierPath=Join-Path $packageRoot 'verify_failure_action_configuration.ps1'
$failureActionSource=Get-Content -LiteralPath $failureActionSourcePath -Raw
$failureActionVerifier=Get-Content -LiteralPath $failureActionVerifierPath -Raw
$failureActionNativeTokens=@('OpenSCManagerW','OpenServiceW','ChangeServiceConfig2W','QueryServiceConfig2W','ServiceConfigFailureActions = 2','ServiceConfigFailureActionsFlag = 4','NON_NULL_SENTINEL_WITH_ZERO_COUNT','FAILURE_ACTION_HELPER_FAILED_CLOSED_ROLLBACK_COMPLETE')
$failureActionRegressionTokens=@('EMPTY_ACTION_SET_REPRESENTED','PRIOR_RESTART_5000_CAPTURED','TARGET_CONTAINS_ZERO_ACTIONS','NONZERO_ACTION_READBACK_REJECTED','RESTART_READBACK_REJECTED','RUN_COMMAND_READBACK_REJECTED','REBOOT_READBACK_REJECTED','ROLLBACK_RECONSTRUCTS_RESTART_5000','EMPTY_ARGUMENT_OMISSION_DETECTED','LITERAL_QUOTE_CORRUPTION_DETECTED','EXTRA_ACTION_DETECTED','HELPER_FAILURE_FAILS_CLOSED')
$failureActionMissing=@($failureActionNativeTokens|Where-Object{-not $failureActionSource.Contains($_)})+@($failureActionRegressionTokens|Where-Object{-not $failureActionVerifier.Contains($_)})
Add-Check 'unit2b-failure-actions-use-measured-native-structure-and-negative-regressions' ($failureActionMissing.Count -eq 0 -and $failureActionSource.Contains('cActions') -eq $false -and $failureActionVerifier.Contains('native_api_invoked')) ([ordered]@{helper_sha256=(Get-LowerHash $failureActionSourcePath);missing_tokens=$failureActionMissing;verifier_sha256=(Get-LowerHash $failureActionVerifierPath)})
$artifactToolSource=Get-Content -LiteralPath (Join-Path $sourceRoot 'R7ArtifactTool.cs') -Raw
$safeFileSource=Get-Content -LiteralPath (Join-Path $sourceRoot 'R7SafeFile.cs') -Raw
$targetBuildSource=Get-Content -LiteralPath (Join-Path $packageRoot 'build_remediation_package.ps1') -Raw
$protectedMethod=[regex]::Match($safeFileSource,'(?s)internal static R7VerifiedMetadataFile HoldProtectedMetadataFile\(.+?\n        }\r?\n\r?\n        internal static R7VerifiedDirectory')
$protectedMetadataClosed=$protectedMethod.Success -and -not $protectedMethod.Value.Contains('GenericRead') -and -not $protectedMethod.Value.Contains('ReadAll(') -and $protectedMethod.Value.Contains('FileReadAttributes | ReadControl') -and $protectedMethod.Value.Contains('FileFlagBackupSemantics | FileFlagOpenReparsePoint') -and $protectedMethod.Value.Contains('StreamsByHandle(handle)')
Add-Check 'protected-key-metadata-is-held-no-read-and-exact-commit-bound' ($protectedMetadataClosed -and $artifactToolSource.Contains('measure-protected-metadata') -and $artifactToolSource.Contains('"data_access_requested", false') -and $artifactToolSource.Contains('"private_bytes_read", false') -and $artifactToolSource.Contains('"privilege_restored_before_evidence_write", true') -and $safeFileSource.Contains('RestoreTokenPrivileges') -and $targetBuildSource.Contains('Generated\ImmutableOrchestratorRepository') -and $targetBuildSource.Contains('R7_PROTECTED_METADATA_TOOL_BUILD_RECEIPT') -and $targetBuildSource.Contains('R7_PROTECTED_METADATA_TOOL_INVOCATION_RECEIPT') -and $targetBuildSource.Contains('private_bytes_read=$false') -and $targetBuildSource.Contains('data_access_requested=$false')) ([ordered]@{artifact_tool_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7ArtifactTool.cs'));build_script_sha256=(Get-LowerHash (Join-Path $packageRoot 'build_remediation_package.ps1'));safe_file_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7SafeFile.cs'))})
$unit2BuildPath=Join-Path $packageRoot 'build_unit2_upgrade_authority.ps1'
$unit2BuildSource=Get-Content -LiteralPath $unit2BuildPath -Raw
$unit2ClosureVerifierPath=Join-Path $packageRoot 'verify_unit2_build_closure.ps1'
$unit2ClosureVerifierSource=Get-Content -LiteralPath $unit2ClosureVerifierPath -Raw
$unit2NegativePath=Join-Path $packageRoot 'unit2_build_closure_negative_cases.json'
$unit2Negative=Read-Json $unit2NegativePath
$identityContractPath=Join-Path $packageRoot 'BuildInputs\R7BuildIdentityContract.cs'
$identityContractSource=Get-Content -LiteralPath $identityContractPath -Raw
$unit2AuthoritySource=Get-Content -LiteralPath (Join-Path $sourceRoot 'R7Unit2UpgradeAuthority.cs') -Raw
$legacyIdentityPath=Join-Path $packageRoot 'BuildInputs\R7DevelopmentIdentity.g.cs'
$unit2SourceTokens=@('UNIT2_GENERATED_','BOOTSTRAP_PENDING','STATIC_PLACEHOLDER','R7DevelopmentIdentity')
$unit2TokenFindings=@($unit2SourceTokens|Where-Object{$unit2AuthoritySource.Contains($_)-or$identityContractSource.Contains($_)})
Add-Check 'unit2-build-generates-final-identities-and-never-opens-private-key' (-not(Test-Path -LiteralPath $legacyIdentityPath) -and $unit2TokenFindings.Count -eq 0 -and $unit2BuildSource.Contains('R7Unit2ClientShared.g.cs') -and $unit2BuildSource.Contains('R7Unit2Service.g.cs') -and $unit2BuildSource.Contains('R7PackagedTools.g.cs') -and $unit2BuildSource.Contains('NONCIRCULAR_INPUT_CLOSURE_DERIVATION_V1') -and $unit2BuildSource.Contains('EXACT_POLICY_SHA256') -and $unit2BuildSource.Contains('compiler_arguments') -and $unit2BuildSource.Contains('compiler_inputs') -and $unit2BuildSource.Contains('PACKAGED_ARTIFACT_TOOL') -and $unit2BuildSource.Contains('PACKAGED_PROTECTED_METADATA_TOOL') -and $unit2BuildSource.Contains('ReflectionOnlyLoadFrom') -and -not $unit2BuildSource.Contains('measure-protected-metadata $keyPath') -and -not $unit2BuildSource.Contains('CngKey') -and -not $unit2BuildSource.Contains('SignData') -and -not $unit2BuildSource.Contains('SignHash')) ([ordered]@{build_script_sha256=(Get-LowerHash $unit2BuildPath);contract_sha256=(Get-LowerHash $identityContractPath);source_token_findings=$unit2TokenFindings})
Add-Check 'unit2-build-closure-verifier-and-negative-regressions-are-explicit' (@($unit2Negative.cases).Count -eq 9 -and $unit2ClosureVerifierSource.Contains('COMPILER_INPUT_SET_MISMATCH') -and $unit2ClosureVerifierSource.Contains('COMPILER_ARGUMENT_VECTOR_MISMATCH') -and $unit2ClosureVerifierSource.Contains('GENERATED_SOURCE_TOKEN_INVALID') -and $unit2ClosureVerifierSource.Contains('PACKAGED_TOOL_IDENTITY_INVALID') -and $unit2ClosureVerifierSource.Contains('ExtractIdentity') -and $unit2ClosureVerifierSource.Contains('ValidateModel')) ([ordered]@{negative_case_count=@($unit2Negative.cases).Count;negative_registry_sha256=(Get-LowerHash $unit2NegativePath);verifier_sha256=(Get-LowerHash $unit2ClosureVerifierPath)})
$declaredScriptNames=@($scriptRegistry.scripts|ForEach-Object{Split-Path -Leaf ([string]$_.path)}|Sort-Object)
$actualScriptNames=@($packageScripts|ForEach-Object Name|Sort-Object)
$badScriptRows=[Collections.Generic.List[object]]::new()
foreach($row in @($scriptRegistry.scripts)){
    $path=Join-Path $repositoryRoot ([string]$row.path).Replace('/','\')
    if(-not(Test-Path -LiteralPath $path -PathType Leaf) -or (Get-LowerHash $path) -cne [string]$row.raw_sha256 -or (Get-GitBlobIdentity $path) -cne [string]$row.git_blob_identity -or (Get-Item -LiteralPath $path).Length -ne [long]$row.size -or [string]$row.mode -cne '100644' -or @($row.allowed_invocation_stages).Count -eq 0 -or @($row.dependencies).Count -eq 0){$badScriptRows.Add($row)}
}
Add-Check 'governed-script-set-is-exact-and-content-bound' ([int]$scriptRegistry.script_count -eq $packageScripts.Count -and ($declaredScriptNames -join "`n") -ceq ($actualScriptNames -join "`n") -and $badScriptRows.Count -eq 0) ([ordered]@{bad_rows=$badScriptRows.ToArray();registry_sha256=(Get-LowerHash $scriptRegistryPath);script_count=$packageScripts.Count})
$requiredUtilityRoles=@('GIT_BUILD_AND_VERIFICATION','POWERSHELL_ORCHESTRATOR','CSC_COMPILER','ILDASM_TOOL','SC_SERVICE_CONTROL_TOOL','ICACLS_ACL_TOOL','FSUTIL_PATH_FIXTURE_TOOL','POWERSHELL_MANAGEMENT_ASSEMBLY','POWERSHELL_JOB_ASSEMBLY','POWERSHELL_UTILITY_MODULE_MANIFEST','POWERSHELL_UTILITY_MODULE_SCRIPT','PKI_MODULE_MANIFEST','PKI_MODULE_TYPES')
$badUtilityRows=[Collections.Generic.List[object]]::new();$utilityRoles=@($utilityRegistry.utilities|ForEach-Object{[string]$_.role})
foreach($row in @($utilityRegistry.utilities)){
    $path=[IO.Path]::GetFullPath([string]$row.path)
    if([bool]$row.path_search_allowed -or [bool]$row.runtime_authority -or -not(Test-Path -LiteralPath $path -PathType Leaf) -or (Get-LowerHash $path) -cne [string]$row.measurement.sha256 -or (Get-Item -LiteralPath $path).Length -ne [long]$row.measurement.size -or @($row.required_by_scripts).Count -eq 0 -or @($row.allowed_invocation_stages).Count -eq 0){$badUtilityRows.Add($row)}
}
Add-Check 'external-utility-set-is-classified-absolute-and-content-bound' ([int]$utilityRegistry.utility_count -eq @($utilityRegistry.utilities).Count -and $badUtilityRows.Count -eq 0 -and @($requiredUtilityRoles|Where-Object{$_ -notin $utilityRoles}).Count -eq 0) ([ordered]@{bad_rows=$badUtilityRows.ToArray();missing_roles=@($requiredUtilityRoles|Where-Object{$_ -notin $utilityRoles});registry_sha256=(Get-LowerHash $utilityRegistryPath);utility_count=@($utilityRegistry.utilities).Count})
$pathSearchFindings=[Collections.Generic.List[object]]::new()
foreach($script in $packageScripts){$text=Get-Content -LiteralPath $script.FullName -Raw;if($text -match '(?im)Get-Command\s+(?:git|sc|icacls|fsutil|csc|ildasm|powershell)(?:\.exe)?\b' -or $text -match '(?im)^\s*&\s*(?:git|sc|icacls|fsutil|csc|ildasm|powershell)(?:\.exe)?\b'){$pathSearchFindings.Add([ordered]@{path=$script.Name})}}
Add-Check 'external-process-launches-do-not-use-path-search' ($pathSearchFindings.Count -eq 0) $pathSearchFindings.ToArray()
$blockers = Read-Json (Join-Path $packageRoot 'blocker_remediation_map.json')
$missingImplementations = [Collections.Generic.List[string]]::new()
foreach ($blocker in @($blockers.blockers)) {
    foreach ($implementation in @($blocker.implementation)) { if (-not (Test-Path -LiteralPath (Join-Path $packageRoot $implementation))) { $missingImplementations.Add(($blocker.id + '|' + $implementation)) } }
}
Add-Check 'all-sixteen-blockers-have-existing-implementation-surfaces' (@($blockers.blockers).Count -eq 16 -and $missingImplementations.Count -eq 0) ([ordered]@{ blocker_count = @($blockers.blockers).Count; missing = $missingImplementations.ToArray() })
Add-Check 'all-blockers-remain-explicitly-partial' (@($blockers.blockers|Where-Object{[string]$_.status -cne 'PARTIAL'}).Count -eq 0 -and [string]$blockers.overall_status -match 'PARTIAL') ([ordered]@{overall_status=$blockers.overall_status;nonpartial=@($blockers.blockers|Where-Object{[string]$_.status -cne 'PARTIAL'}|ForEach-Object id)})
$readmePath=Join-Path $packageRoot 'README.md';$aiaPath=Join-Path $packageRoot 'Architecture_Impact_Assessment_PROPOSAL.md';$deltaPath=Join-Path $packageRoot 'Canonical_Delta_PROPOSAL.md';$threatPath=Join-Path $packageRoot 'Threat_Model.md'
$readmeText=Get-Content -LiteralPath $readmePath -Raw;$aiaText=Get-Content -LiteralPath $aiaPath -Raw;$deltaText=Get-Content -LiteralPath $deltaPath -Raw;$threatText=Get-Content -LiteralPath $threatPath -Raw
$documentationCorpus=$readmeText+"`n"+$aiaText+"`n"+$deltaText+"`n"+$threatText
$requiredDocumentationTokens=@('terminal signer, execution, observation, comparator, and upgrade authority','SeDenyInteractiveLogonRight','SeDenyRemoteInteractiveLogonRight','POS-005','POS-006','canonical','R7MeasuredUtility.cs','R7RecoveryProbeAuditor','runtime dependency closure','matrix','No live outer execution occurred','AUTHORIZED FOR FUTURE INSTALLATION CONSIDERATION')
$missingDocumentationTokens=@($requiredDocumentationTokens|Where-Object{-not $documentationCorpus.Contains($_)})
$boundedDocumentationClaims=$readmeText.Contains('Every `R7AR-B01` through `R7AR-B16` finding remains **PARTIAL**') -and $readmeText.Contains('does not accept R7') -and $readmeText.Contains('Terminal v4 installation/activation') -and $aiaText.Contains('All sixteen independent-review blockers remain partial') -and $aiaText.Contains('Acceptance remains solely a later independent-review decision') -and $deltaText.Contains('No canonical record, terminal installation/activation, terminal-ledger change, receipt, reconciliation, matrix run, deployment, or review disposition follows') -and $threatText.Contains('All `R7AR-B01` through `R7AR-B16` findings therefore remain partial') -and $threatText.Contains('Unit 2 authorization is not, by itself, proof that future current state remains unchanged')
Add-Check 'proposal-readme-threat-and-blocker-documentation-synchronized-to-unit2-bounded-partial-state' ($missingDocumentationTokens.Count -eq 0 -and $boundedDocumentationClaims) ([ordered]@{architecture_impact_assessment_sha256=(Get-LowerHash $aiaPath);canonical_delta_sha256=(Get-LowerHash $deltaPath);missing_tokens=$missingDocumentationTokens;readme_sha256=(Get-LowerHash $readmePath);threat_model_sha256=(Get-LowerHash $threatPath)})

if (-not [string]::IsNullOrWhiteSpace($StaticBuildRoot)) {
    $staticBuild=[IO.Path]::GetFullPath($StaticBuildRoot)
    $receiptPath=Join-Path $staticBuild 'static_build_receipt.json';$summaryPath=Join-Path $staticBuild 'static_build_summary.json';$dependencyPath=Join-Path $staticBuild 'Generated\static_dependency_manifest.json'
    foreach($required in @($receiptPath,$summaryPath,$dependencyPath)){if(-not(Test-Path -LiteralPath $required -PathType Leaf)){throw "Static build evidence missing: $required"}}
    $receipt=Read-Json $receiptPath;$summary=Read-Json $summaryPath;$dependency=Read-Json $dependencyPath
    $badBinaries=@($receipt.binaries|Where-Object{$_.normalized_il_equal -ne $true -or [string]$_.authority_classification -cne 'UNINSTALLED_NONAUTHORITATIVE_STATIC_COMPILE_EVIDENCE' -or @($_.source_paths).Count -ne $sourceFiles.Count})
    $unstableClosures=@($receipt.build_input_closures|Where-Object{$_.stable_during_use -ne $true -or [string]$_.initial_manifest_raw_sha256 -cne [string]$_.post_manifest_raw_sha256})
    Add-Check 'static-build-receipt-closes-all-roles-sources-and-dependencies' ([string]$receipt.status -ceq 'PASS' -and [int]$summary.binary_count -eq [int]$sourceRoleRegistry.executable_role_count -and @($receipt.binaries).Count -eq [int]$sourceRoleRegistry.executable_role_count -and $badBinaries.Count -eq 0 -and $unstableClosures.Count -eq 0 -and [string]$dependency.status -match 'RUNTIME_CLOSURE_REMAINS_PENDING_LIVE_PROOF' -and [string]$receipt.generated_identity.authority_classification -ceq 'UNINSTALLED_NONAUTHORITATIVE_STATIC_COMPILE_IDENTITY') ([ordered]@{bad_binaries=$badBinaries;build_receipt_sha256=(Get-LowerHash $receiptPath);dependency_manifest_sha256=(Get-LowerHash $dependencyPath);unstable_closures=$unstableClosures})
}

if (-not [string]::IsNullOrWhiteSpace($Unit2BuildRoot)) {
    if ([string]::IsNullOrWhiteSpace($Unit2ClosureReport)) { throw 'Unit2ClosureReport is required with Unit2BuildRoot.' }
    $unit2Build=[IO.Path]::GetFullPath($Unit2BuildRoot);$unit2ReportPath=[IO.Path]::GetFullPath($Unit2ClosureReport)
    $unit2ReceiptPath=Join-Path $unit2Build 'Generated\unit2_build_receipt.json';$unit2DeterminismPath=Join-Path $unit2Build 'Generated\unit2_build_determinism_receipt.json';$unit2ManifestPath=Join-Path $unit2Build 'unit2_build_manifest.json'
    foreach($required in @($unit2ReceiptPath,$unit2DeterminismPath,$unit2ManifestPath,$unit2ReportPath)){if(-not(Test-Path -LiteralPath $required -PathType Leaf)){throw "Unit 2 build-closure evidence missing: $required"}}
    $unit2Receipt=Read-Json $unit2ReceiptPath;$unit2Determinism=Read-Json $unit2DeterminismPath;$unit2Manifest=Read-Json $unit2ManifestPath;$unit2Report=Read-Json $unit2ReportPath
    $unit2BadRoles=@($unit2Receipt.roles|Where-Object{$_.normalized_il_equal-ne$true-or@($_.compiler_inputs).Count-ne(@($unit2Receipt.source_files).Count+1)-or@($_.compiler_arguments.pass_a).Count-ne@($_.compiler_arguments.pass_b).Count-or@($_.response_files).Count-ne0-or@($_.resource_files).Count-ne0})
    $unit2BadGenerated=@($unit2Receipt.generated_sources|Where-Object{[string]$_.generation_rule-notmatch'^R7_UNIT2_' -or [string]$_.raw_sha256-notmatch'^[0-9a-f]{64}$'})
    $unit2BadTargetExecutables=@($unit2Receipt.target_packaged_executables|Where-Object{[string]$_.raw_sha256-notmatch'^[0-9a-f]{64}$'-or@($_.embedded_identity.PSObject.Properties).Count-eq0})
    Add-Check 'unit2-exact-build-receipts-close-roles-inputs-arguments-and-generated-sources' ([string]$unit2Receipt.schema_version-ceq'2.0.0' -and @($unit2Receipt.roles).Count-eq8 -and @($unit2Receipt.generated_sources).Count-eq4 -and @($unit2Receipt.target_packaged_executables).Count-ge9 -and $unit2BadRoles.Count-eq0 -and $unit2BadGenerated.Count-eq0 -and $unit2BadTargetExecutables.Count-eq0 -and @($unit2Determinism.role_determinism).Count-eq8 -and @($unit2Determinism.target_packaged_executables).Count-eq@($unit2Receipt.target_packaged_executables).Count -and [string]$unit2Manifest.status-ceq'PASS' -and [string]$unit2Report.status-ceq'PASS' -and [int]$unit2Report.negative_test_count-eq9) ([ordered]@{bad_generated=$unit2BadGenerated;bad_roles=$unit2BadRoles;bad_target_packaged_executables=$unit2BadTargetExecutables;closure_report_sha256=(Get-LowerHash $unit2ReportPath);determinism_receipt_sha256=(Get-LowerHash $unit2DeterminismPath);manifest_sha256=(Get-LowerHash $unit2ManifestPath);source_to_binary_receipt_sha256=(Get-LowerHash $unit2ReceiptPath);target_packaged_executable_count=@($unit2Receipt.target_packaged_executables).Count})
}

if (-not [string]::IsNullOrWhiteSpace($CompiledRoleRoot)) {
    $compiled = [IO.Path]::GetFullPath($CompiledRoleRoot)
    $staticVerifier = Join-Path $compiled 'RandleTerminalStaticVerifier.Offline.exe'
    if (-not (Test-Path -LiteralPath $staticVerifier -PathType Leaf)) { $staticVerifier = Join-Path $compiled 'R7StaticVerification.exe' }
    if (-not (Test-Path -LiteralPath $staticVerifier -PathType Leaf)) { $staticVerifier = Join-Path $compiled 'RandleTerminalStaticVerifier.exe' }
    if (-not (Test-Path -LiteralPath $staticVerifier -PathType Leaf)) { throw 'Compiled static verifier is absent.' }
    $parserOutput = @(& $staticVerifier parser)
    Add-Check 'compiled-strict-parser-suite' ($LASTEXITCODE -eq 0 -and (Read-JsonText ($parserOutput -join "`n")).status -eq 'PASS') ([ordered]@{ output = $parserOutput })
    $authorityOutput = @(& $staticVerifier authority $packageRoot (Get-LowerHash $requirementPath) (Get-LowerHash $casePath) (Get-LowerHash $expectationPath) (Get-LowerHash $coveragePath) (Get-LowerHash $manifestPath))
    $authorityResult = Read-JsonText ($authorityOutput -join "`n")
    Add-Check 'compiled-complete-authority-and-thirty-file-review-package-suite' ($LASTEXITCODE -eq 0 -and $authorityResult.status -eq 'PASS' -and [int]$authorityResult.case_count -eq $declaredCaseCount -and [int]$authorityResult.independent_review_package_file_count -eq 30) ([ordered]@{ output = $authorityOutput })
    if ([string]::IsNullOrWhiteSpace($TransactionProbeRoot)) { throw 'TransactionProbeRoot is required with CompiledRoleRoot.' }
    $transactionOutput = @(& $staticVerifier transaction ([IO.Path]::GetFullPath($TransactionProbeRoot)))
    Add-Check 'compiled-transaction-recovery-suite' ($LASTEXITCODE -eq 0 -and (Read-JsonText ($transactionOutput -join "`n")).status -eq 'PASS') ([ordered]@{ output = $transactionOutput })
    if ([string]::IsNullOrWhiteSpace($RecoveryProbeRoot)) { throw 'RecoveryProbeRoot is required with CompiledRoleRoot.' }
    $recoveryOutput = @(& $staticVerifier recovery ([IO.Path]::GetFullPath($RecoveryProbeRoot)))
    $recoveryResult = Read-JsonText ($recoveryOutput -join "`n")
    Add-Check 'compiled-isolated-recovery-algorithm-suite' ($LASTEXITCODE -eq 0 -and $recoveryResult.status -eq 'PASS' -and [int]$recoveryResult.fault_point_count -eq 24) ([ordered]@{ output = $recoveryOutput })
    if (-not [string]::IsNullOrWhiteSpace($LegacySnapshotRoot)) {
        $legacy = [IO.Path]::GetFullPath($LegacySnapshotRoot)
        $legacyOutput = @(& $staticVerifier legacy-history (Join-Path $legacy 'Ledger') (Join-Path $legacy 'Trust\terminal_authority_public.cer') (Join-Path $legacy 'Receipts') (Join-Path $legacy 'Reconciliations') (Join-Path $legacy 'Evidence') (Join-Path $legacy 'Responses') $historyPath)
        $legacyResult = Read-JsonText ($legacyOutput -join "`n")
        Add-Check 'compiled-version-aware-retained-history-suite' ($LASTEXITCODE -eq 0 -and $legacyResult.status -eq 'PASS' -and [int]$legacyResult.ledger_entry_count -eq 678 -and [int]$legacyResult.terminal_receipt_count -eq 64 -and [int]$legacyResult.reconciliation_receipt_count -eq 31 -and [int]$legacyResult.classification_binding_count -eq 10) ([ordered]@{ output = $legacyOutput })
    }
}

$result = [ordered]@{
    artifact_type = 'R7_STATIC_ARCHITECTURE_VERIFICATION'
    check_count = $checks.Count
    checks = $checks.ToArray()
    failed_count = @($checks | Where-Object status -eq 'FAIL').Count
    head = $head
    passed_count = @($checks | Where-Object status -eq 'PASS').Count
    schema_version = '1.0.0'
    status = 'PASS'
}
Write-JsonNew $result $OutputPath
Write-Output ([ordered]@{ checks = $checks.Count; output = [IO.Path]::GetFullPath($OutputPath); raw_sha256 = (Get-LowerHash $OutputPath); status = 'PASS' } | ConvertTo-Json)
