[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet('BootstrapUpgradeAuthority','AuthorizeAndInstallTerminal')][string]$Mode,
    [Parameter(Mandatory = $true)][string]$BuildRoot,
    [Parameter(Mandatory = $true)][string]$EvidenceRoot,
    [ValidatePattern('^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')][string]$TransitionNonce
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$build = [IO.Path]::GetFullPath($BuildRoot)
$evidence = [IO.Path]::GetFullPath($EvidenceRoot)
$packageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$upgradeInstallRoot = 'C:\Program Files\RandleAI\TerminalUpgradeAuthority'
$upgradeStateRoot = 'C:\ProgramData\RandleAI\TerminalUpgradeAuthority'
$terminalInstallRoot = 'C:\Program Files\RandleAI\TerminalAuthorityV4'
$terminalStateRoot = 'C:\ProgramData\RandleAI\TerminalAuthority'
$remediationRoot = Join-Path $terminalStateRoot 'RemediationV4'
$artifactTool = Join-Path $build 'Bootstrap\R7ArtifactTool.bootstrap.exe'
$upgradeClient = Join-Path $upgradeInstallRoot 'RandleTerminalUpgradeClient.exe'
$upgradeService = 'RandleTerminalUpgradeAuthority'
$terminalService = 'RandleTerminalAuthority'
$terminalAccount = 'NT SERVICE\RandleTerminalAuthority'
$upgradeAccount = 'NT SERVICE\RandleTerminalUpgradeAuthority'
$executionAccount = 'NT SERVICE\RandleTerminalExecution'
$observationAccount = 'NT SERVICE\RandleTerminalObservation'
$comparatorAccount = 'NT SERVICE\RandleTerminalComparator'
$operatorSid = '*S-1-5-21-4259795780-3461844753-1172372902-1001'
$scExecutable = 'C:\Windows\System32\sc.exe'
$icaclsExecutable = 'C:\Windows\System32\icacls.exe'
$serviceSids = @{
    RandleTerminalAuthority = 'S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948'
    RandleTerminalExecution = 'S-1-5-80-2354876894-2467424667-1382161683-1170422623-3885682053'
    RandleTerminalObservation = 'S-1-5-80-1455550362-116536141-3163605276-3265053646-3003707260'
    RandleTerminalComparator = 'S-1-5-80-3174819085-3989415034-4266081362-372562941-1584450511'
    RandleTerminalUpgradeAuthority = 'S-1-5-80-238545627-4117296865-2677355104-248304369-1301198082'
}
$utilityIdentities = @{}
$script:utilityInvocationSequence = 0

function Get-LowerHash([string]$Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function Get-RelativePath([string]$Base, [string]$Path) {
    $baseFull = [IO.Path]::GetFullPath($Base).TrimEnd('\') + '\'; $pathFull = [IO.Path]::GetFullPath($Path)
    return [Uri]::UnescapeDataString(([Uri]$baseFull).MakeRelativeUri([Uri]$pathFull).ToString()).Replace('/', '\')
}
function Assert-DedicatedPath([string]$Path, [string]$Root) {
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\'); $fixed = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    if ($full -ne $fixed -and -not $full.StartsWith($fixed + '\', [StringComparison]::Ordinal)) { throw "Path escapes dedicated root: $full" }
}
function Invoke-Checked([string]$FilePath, [string[]]$Arguments) {
    $full = [IO.Path]::GetFullPath($FilePath)
    $expected = $utilityIdentities[$full]
    if ($null -eq $expected) { throw "Executable is not in the governed installer utility set: $full" }
    $script:utilityInvocationSequence++
    $prefix = 'utility-' + $script:utilityInvocationSequence.ToString('D4')
    $argumentPath = Join-Path $evidence ($prefix + '.arguments.json')
    $invocationPath = Join-Path $evidence ($prefix + '.invocation.json')
    Write-Canonical ([object[]]$Arguments) $argumentPath
    & $artifactTool 'run-measured-utility' $full ([string]$expected.sha256) ([string]$expected.owner_sid) ([string]$expected.security_descriptor_sha256) ([string]$expected.volume_identity) ([string]$expected.hard_link_count) $argumentPath $invocationPath | Out-Null
    $exit = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath $invocationPath -PathType Leaf)) { throw "Measured utility produced no invocation evidence: $full" }
    $invocation = Get-Content -Raw -LiteralPath $invocationPath | ConvertFrom-Json
    if ($invocation.artifact_type -cne 'R7_HELD_MEASURED_UTILITY_INVOCATION' -or $invocation.executable_sha256 -cne [string]$expected.sha256 -or [long]$invocation.exit_code -ne 0 -or $exit -ne 0) { throw "$full exited $($invocation.exit_code)" }
}
function Durable-Copy([string]$Source, [string]$Destination) {
    if (Test-Path -LiteralPath $Destination) { throw "Refusing overwrite: $Destination" }
    $parent = Split-Path -Parent $Destination
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
    & $artifactTool durable-copy $Source $Destination | Out-Null
    if ($LASTEXITCODE -ne 0 -or (Get-LowerHash $Source) -ne (Get-LowerHash $Destination)) { throw "Durable copy failed: $Destination" }
}
function Set-SystemOwner([string]$Path) { Invoke-Checked $icaclsExecutable @($Path, '/setowner', 'SYSTEM', '/T', '/C') }
function Set-SystemDirectoryOwner([string]$Path) { Invoke-Checked $icaclsExecutable @($Path, '/setowner', 'SYSTEM', '/C') }
function Write-Canonical([object]$Value, [string]$Path) {
    $raw = $Path + '.raw'
    [IO.File]::WriteAllText($raw, ($Value | ConvertTo-Json -Depth 32), [Text.UTF8Encoding]::new($false))
    & $artifactTool canonicalize $raw $Path | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Canonical write failed: $Path" }
}
function Assert-ExactPropertySet([object]$Value, [string[]]$Expected, [string]$Label) {
    $actual = @($Value.PSObject.Properties.Name | Sort-Object)
    $required = @($Expected | Sort-Object)
    if ($actual.Count -ne $required.Count -or (($actual -join "`n") -cne ($required -join "`n"))) { throw "$Label property set is not exact." }
}
function Ensure-Service([string]$Name, [string]$Binary, [string]$Account) {
    if (Get-Service -Name $Name -ErrorAction SilentlyContinue) {
        Invoke-Checked $scExecutable @('config', $Name, "binPath= `"$Binary`"", 'start= demand', "obj= $Account")
    } else {
        Invoke-Checked $scExecutable @('create', $Name, "binPath= `"$Binary`"", 'start= demand', "obj= $Account")
    }
    Invoke-Checked $scExecutable @('sidtype', $Name, 'restricted')
    Invoke-Checked $scExecutable @('privs', $Name, 'SeChangeNotifyPrivilege')
    Invoke-Checked $scExecutable @('failure', $Name, 'reset= 86400', 'actions= restart/5000')
}
function Assert-ServiceBoundary([string]$Name, [string]$Binary, [string]$Label) {
    if (-not $serviceSids.ContainsKey($Name)) { throw "No governed SID exists for service $Name" }
    $path = Join-Path $evidence ($Label + '.service_boundary.json')
    & $artifactTool 'service-boundary' $Name ([string]$serviceSids[$Name]) ([IO.Path]::GetFullPath($Binary)) $path | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "OS-enforced service boundary verification failed: $Name" }
    $value = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
    if ($value.artifact_type -cne 'R7_OS_ENFORCED_SERVICE_BOUNDARY_MEASUREMENT' -or $value.service_sid -cne [string]$serviceSids[$Name] -or -not [bool]$value.interactive_logon_denied -or -not [bool]$value.remote_interactive_logon_denied -or $value.service_sid_type -cne 'RESTRICTED') { throw "Service boundary measurement is inconsistent: $Name" }
    return [ordered]@{measurement=$value;path=$path}
}
function Restore-ServiceBoundary([object]$Boundary, [string]$Label) {
    $path = Join-Path $evidence ($Label + '.service_boundary_restoration.json')
    & $artifactTool 'restore-service-boundary' ([string]$Boundary.path) $path | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Service boundary account-right restoration failed: $Label" }
}
function Wait-ServiceState([string]$Name, [string]$State, [int]$Seconds) {
    $service = Get-Service -Name $Name -ErrorAction Stop
    $service.WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::$State, [TimeSpan]::FromSeconds($Seconds))
}
function Assert-RoleHealth([string]$Harness, [string]$Role, [string]$ExpectedCode, [string]$Label, [string]$Operation='GET_ROLE_HEALTH') {
    $payloadPath = Join-Path $evidence ($TransitionNonce + '.' + $Label + '.health_payload.json')
    $outputPath = Join-Path $evidence ($TransitionNonce + '.' + $Label + '.health_interaction.json')
    Write-Canonical ([ordered]@{}) $payloadPath
    & $Harness 'call' $Role $Operation $payloadPath $outputPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Measured role health invocation failed: $Label" }
    $health = Get-Content -Raw -LiteralPath $outputPath | ConvertFrom-Json
    if ($health.response.status -cne 'COMPLETE' -or $health.response.result_code -cne $ExpectedCode) { throw "Measured role health semantics failed: $Label" }
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent(); $principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Elevation is required.' }
foreach ($required in @($artifactTool, (Join-Path $build 'build_summary.json'))) { if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Build input missing: $required" } }
Assert-DedicatedPath $upgradeInstallRoot 'C:\Program Files\RandleAI'
Assert-DedicatedPath $upgradeStateRoot 'C:\ProgramData\RandleAI'
Assert-DedicatedPath $terminalInstallRoot 'C:\Program Files\RandleAI'
Assert-DedicatedPath $remediationRoot $terminalStateRoot
if (-not (Test-Path -LiteralPath $evidence)) { New-Item -ItemType Directory -Path $evidence | Out-Null }
$summary = Get-Content -Raw -LiteralPath (Join-Path $build 'build_summary.json') | ConvertFrom-Json
Assert-ExactPropertySet $summary @('artifact_type','authority_package_manifest_sha256','build_receipt_sha256','case_definitions_sha256','dependency_manifest_sha256','expectations_sha256','installer_script_sha256','interface_version','prohibited_source_dependency_count','requirement_registry_sha256','schema_version','source_commit','source_tree','terminal_policy_sha256','upgrade_authority_build_receipt_sha256','upgrade_binary_sha256','upgrade_ledger_id','upgrade_policy_sha256','upgrade_public_certificate_sha256') 'Build summary'
$runningInstallerSha256 = Get-LowerHash $PSCommandPath
if ($summary.artifact_type -cne 'R7_REMEDIATION_BUILD_SUMMARY' -or $summary.installer_script_sha256 -cne $runningInstallerSha256 -or [long]$summary.prohibited_source_dependency_count -ne 0) { throw 'Running installer is not the exact governed build input.' }
$installerDependencyManifestPath = Join-Path $build 'Generated\dependency_manifest.json'
if (-not (Test-Path -LiteralPath $installerDependencyManifestPath -PathType Leaf) -or (Get-LowerHash $installerDependencyManifestPath) -cne [string]$summary.dependency_manifest_sha256) { throw 'Installer dependency manifest does not match the governed build summary.' }
$installerDependencies = Get-Content -Raw -LiteralPath $installerDependencyManifestPath | ConvertFrom-Json
foreach ($role in @('HOST_SERVICE_CONTROL_TOOL','HOST_ACL_TOOL')) {
    $rows = @($installerDependencies.build_tools | Where-Object { $_.role -ceq $role })
    if ($rows.Count -ne 1) { throw "Installer dependency role is not unique: $role" }
    $path = [IO.Path]::GetFullPath([string]$rows[0].measurement.path)
    $measurement = $rows[0].measurement
    $hash = [string]$measurement.sha256
    if ($hash -notmatch '^[0-9a-f]{64}$' -or [string]$measurement.owner_sid -notmatch '^S-1-' -or [string]$measurement.security_descriptor_sha256 -notmatch '^[0-9a-f]{64}$' -or [string]$measurement.volume_identity -notmatch '^[0-9a-f]{8,64}$' -or [long]$measurement.hard_link_count -lt 1 -or (Get-LowerHash $path) -cne $hash -or $utilityIdentities.ContainsKey($path)) { throw "Installer utility identity mismatch: $role" }
    $utilityIdentities[$path] = $measurement
}
if ($utilityIdentities.Count -ne 2 -or -not $utilityIdentities.ContainsKey($scExecutable) -or -not $utilityIdentities.ContainsKey($icaclsExecutable)) { throw 'Governed installer utility set is incomplete.' }

if ($Mode -eq 'BootstrapUpgradeAuthority') {
    $sourceRoot = Join-Path $build 'UpgradeBootstrap'
    $binarySource = Join-Path $sourceRoot 'RandleTerminalUpgradeAuthority.exe'
    $clientSource = Join-Path $sourceRoot 'RandleTerminalUpgradeClient.exe'
    $policySource = Join-Path $sourceRoot 'upgrade_authority_policy.json'
    $dependencySource = Join-Path $sourceRoot 'dependency_manifest.json'
    $buildReceiptSource = Join-Path $sourceRoot 'upgrade_authority_build_receipt.json'
    $certificateSource = Join-Path $sourceRoot 'upgrade_authority_public.cer'
    foreach ($required in @($binarySource,$clientSource,$policySource,$dependencySource,$buildReceiptSource,$certificateSource)) { if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Upgrade bootstrap input missing: $required" } }
    if ((Get-LowerHash $buildReceiptSource) -cne [string]$summary.upgrade_authority_build_receipt_sha256) { throw 'Upgrade build receipt differs from the governed build summary.' }
    $upgradeBuildReceipt = Get-Content -Raw -LiteralPath $buildReceiptSource | ConvertFrom-Json
    Assert-ExactPropertySet $upgradeBuildReceipt @('artifact_type','binary','compiler_options','dependency_manifest_sha256','final_build_input_closures','generated_identity_sha256','governed_scripts','schema_version','source_commit','source_files','source_tree','toolchain','upgrade_policy_sha256') 'Upgrade build receipt'
    if ($upgradeBuildReceipt.artifact_type -cne 'R7_UPGRADE_AUTHORITY_SOURCE_TO_BINARY_BUILD_RECEIPT' -or $upgradeBuildReceipt.source_commit -cne $summary.source_commit -or $upgradeBuildReceipt.source_tree -cne $summary.source_tree -or $upgradeBuildReceipt.upgrade_policy_sha256 -cne $summary.upgrade_policy_sha256) { throw 'Upgrade build receipt semantics mismatch.' }
    $installedCertificate = Join-Path $upgradeStateRoot 'Trust\upgrade_authority_public.cer'
    if ((Get-LowerHash $certificateSource) -ne (Get-LowerHash $installedCertificate)) { throw 'Provisioned upgrade certificate differs from the governed build input.' }
    $destinations = @(
        @($binarySource,(Join-Path $upgradeInstallRoot 'RandleTerminalUpgradeAuthority.exe')),
        @($clientSource,(Join-Path $upgradeInstallRoot 'RandleTerminalUpgradeClient.exe')),
        @($policySource,(Join-Path $upgradeStateRoot 'Config\upgrade_authority_policy.json')),
        @($dependencySource,(Join-Path $upgradeStateRoot 'Config\dependency_manifest.json')),
        @($buildReceiptSource,(Join-Path $upgradeStateRoot 'Config\upgrade_authority_build_receipt.json'))
    )
    $bootstrapRelativeFiles = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($name in @('RandleTerminalUpgradeAuthority.exe','RandleTerminalUpgradeClient.exe','upgrade_authority_policy.json','dependency_manifest.json','upgrade_authority_build_receipt.json','upgrade_authority_public.cer')) { [void]$bootstrapRelativeFiles.Add($name) }
    foreach ($closure in @($upgradeBuildReceipt.final_build_input_closures)) {
        Assert-ExactPropertySet $closure @('file_count','final_manifest_raw_sha256','initial_manifest_raw_sha256','manifest_relative_path','role','stable_during_use') ('Upgrade closure ' + [string]$closure.role)
        $relative = [string]$closure.manifest_relative_path
        if (-not $relative.StartsWith('BuildInputClosures/',[StringComparison]::Ordinal) -or $relative.Contains('..') -or -not $bootstrapRelativeFiles.Add($relative)) { throw "Invalid upgrade closure path: $relative" }
        $source = Join-Path $sourceRoot $relative.Replace('/','\')
        if ((Get-LowerHash $source) -cne [string]$closure.final_manifest_raw_sha256) { throw "Upgrade closure identity mismatch: $relative" }
        $destinations += ,@($source,(Join-Path (Join-Path $upgradeStateRoot 'Config') $relative.Replace('/','\')))
    }
    foreach ($sourceRow in @($upgradeBuildReceipt.source_files) + @($upgradeBuildReceipt.governed_scripts)) {
        $relative = 'SourceInputs/' + [string]$sourceRow.path
        if ($relative.Contains('..') -or $relative.Contains('\') -or -not $bootstrapRelativeFiles.Add($relative)) { throw "Invalid upgrade source-input path: $relative" }
        $source = Join-Path $sourceRoot $relative.Replace('/','\')
        if ((Get-LowerHash $source) -cne [string]$sourceRow.raw_sha256 -or (Get-Item -LiteralPath $source).Length -ne [long]$sourceRow.size) { throw "Upgrade source-input identity mismatch: $relative" }
        $destinations += ,@($source,(Join-Path (Join-Path $upgradeStateRoot 'Config') $relative.Replace('/','\')))
    }
    foreach ($bootstrapFile in Get-ChildItem -LiteralPath $sourceRoot -File -Recurse) {
        $relative = (Get-RelativePath $sourceRoot $bootstrapFile.FullName).Replace('\','/')
        if (-not $bootstrapRelativeFiles.Contains($relative)) { throw "Unmanifested upgrade-bootstrap file: $relative" }
    }
    if (@(Get-ChildItem -LiteralPath $sourceRoot -File -Recurse).Count -ne $bootstrapRelativeFiles.Count) { throw 'Upgrade-bootstrap manifest is incomplete.' }
    foreach ($pair in $destinations) { Durable-Copy $pair[0] $pair[1]; Set-SystemOwner $pair[1] }
    Set-SystemOwner $upgradeInstallRoot
    Set-SystemOwner $upgradeStateRoot
    Invoke-Checked $icaclsExecutable @($upgradeInstallRoot, '/inheritance:r', '/grant:r', 'SYSTEM:(OI)(CI)(F)', 'BUILTIN\Administrators:(OI)(CI)(F)', "$upgradeAccount`:(OI)(CI)(RX)", "$terminalAccount`:(OI)(CI)(RX)", '/T', '/C')
    Invoke-Checked $icaclsExecutable @($upgradeStateRoot, '/inheritance:r', '/grant:r', 'SYSTEM:(OI)(CI)(F)', 'BUILTIN\Administrators:(OI)(CI)(F)', "$upgradeAccount`:(OI)(CI)(RX)", "$terminalAccount`:(OI)(CI)(RX)", 'BUILTIN\Users:(OI)(CI)(RX)', '/T', '/C')
    foreach ($mutableRoot in @(
        (Join-Path $upgradeStateRoot 'Activations'),
        (Join-Path $upgradeStateRoot 'Authorizations'),
        (Join-Path $upgradeStateRoot 'Ledger'),
        (Join-Path $upgradeStateRoot 'Objects'),
        (Join-Path $upgradeStateRoot 'Recovery')
    )) {
        Invoke-Checked $icaclsExecutable @($mutableRoot, '/inheritance:r', '/grant:r', 'SYSTEM:(OI)(CI)(F)', 'BUILTIN\Administrators:(OI)(CI)(F)', "$upgradeAccount`:(OI)(CI)(F)", "$terminalAccount`:(OI)(CI)(RX)", 'BUILTIN\Users:(OI)(CI)(RX)', '/T', '/C')
    }
    Ensure-Service $upgradeService (Join-Path $upgradeInstallRoot 'RandleTerminalUpgradeAuthority.exe') $upgradeAccount
    $upgradeServiceBoundary = Assert-ServiceBoundary $upgradeService (Join-Path $upgradeInstallRoot 'RandleTerminalUpgradeAuthority.exe') 'upgrade-authority-bootstrap'
    Start-Service -Name $upgradeService
    Wait-ServiceState $upgradeService 'Running' 30
    $record = [ordered]@{artifact_type='R7_UPGRADE_AUTHORITY_INSTALLATION_RECORD';binary_sha256=(Get-LowerHash (Join-Path $upgradeInstallRoot 'RandleTerminalUpgradeAuthority.exe'));build_receipt_sha256=(Get-LowerHash (Join-Path $upgradeStateRoot 'Config\upgrade_authority_build_receipt.json'));client_sha256=(Get-LowerHash (Join-Path $upgradeInstallRoot 'RandleTerminalUpgradeClient.exe'));dependency_manifest_sha256=(Get-LowerHash (Join-Path $upgradeStateRoot 'Config\dependency_manifest.json'));policy_sha256=(Get-LowerHash (Join-Path $upgradeStateRoot 'Config\upgrade_authority_policy.json'));schema_version='1.0.0';service_boundary=$upgradeServiceBoundary.measurement;service_state=(Get-Service $upgradeService).Status.ToString();upgrade_public_certificate_sha256=(Get-LowerHash $installedCertificate)}
    Write-Canonical $record (Join-Path $evidence 'upgrade_authority_installation_record.json')
    return
}

if ([string]::IsNullOrWhiteSpace($TransitionNonce)) { throw 'AuthorizeAndInstallTerminal requires a governed transition nonce.' }
if (-not (Test-Path -LiteralPath $upgradeClient -PathType Leaf)) { throw 'Measured upgrade client is missing.' }
if ((Get-Service -Name $upgradeService -ErrorAction Stop).Status -ne 'Running') { throw 'Upgrade authority service is not running.' }
$stageRoot = Join-Path $upgradeStateRoot ('Staging\' + $TransitionNonce)
if (Test-Path -LiteralPath $stageRoot) { throw 'Transition staging root already exists; refusing replay.' }
New-Item -ItemType Directory -Path $stageRoot | Out-Null
foreach ($file in Get-ChildItem -LiteralPath (Join-Path $build 'Staging') -File -Recurse) {
    $relative = Get-RelativePath (Join-Path $build 'Staging') $file.FullName
    Durable-Copy $file.FullName (Join-Path $stageRoot $relative)
}
Durable-Copy (Join-Path $packageRoot 'install_authorized_transition.ps1') (Join-Path $stageRoot 'installer\install_authorized_transition.ps1')
Set-SystemOwner $stageRoot
Invoke-Checked $icaclsExecutable @($stageRoot, '/inheritance:r', '/grant:r', 'SYSTEM:(OI)(CI)(F)', 'BUILTIN\Administrators:(OI)(CI)(F)', "$upgradeAccount`:(OI)(CI)(RX)", '/T', '/C')

$template = Get-Content -Raw -LiteralPath (Join-Path $build 'Generated\transition_request_template.json') | ConvertFrom-Json
$template.staging_root = $stageRoot
$template.transition_nonce = $TransitionNonce
$requestPath = Join-Path $evidence ($TransitionNonce + '.authorization_payload.json')
Write-Canonical $template $requestPath
$authorizationInteraction = Join-Path $evidence ($TransitionNonce + '.authorization_interaction.json')
& $upgradeClient 'AUTHORIZE_TERMINAL_UPGRADE' $requestPath $authorizationInteraction
if ($LASTEXITCODE -ne 0) { throw 'Separate upgrade authority rejected the pre-install transition.' }
$interaction = Get-Content -Raw -LiteralPath $authorizationInteraction | ConvertFrom-Json
$authorizationIdentity = [string]$interaction.response.authorization_identity
if ($authorizationIdentity -notmatch '^[0-9a-f]{64}$') { throw 'Upgrade authorization identity is invalid.' }
$authorizationRecord = Join-Path $upgradeStateRoot ('Authorizations\' + $TransitionNonce + '.upgrade.json')
if ((Get-LowerHash $authorizationRecord) -ne $authorizationIdentity) { throw 'Signed pre-install authorization does not resolve.' }

# Resolve the signed record from the live, separate authority and independently
# verify its signature before consuming any staged byte. The artifact tool is
# itself one of the exact components the authority just measured and signed.
$authorizedToolRow = @($template.components | Where-Object { $_.role -ceq 'INSTALLER_TOOL' })
if ($authorizedToolRow.Count -ne 1) { throw 'Authorization template does not contain exactly one installer tool.' }
$artifactTool = Join-Path $stageRoot ([string]$authorizedToolRow[0].staging_relative_path).Replace('/','\')
if ((Get-LowerHash $artifactTool) -cne [string]$authorizedToolRow[0].sha256) { throw 'Staged installer tool differs from the pre-install authorized identity.' }
$getAuthorizationPayload = Join-Path $evidence ($TransitionNonce + '.get_authorization_payload.json')
Write-Canonical ([ordered]@{transition_nonce=$TransitionNonce}) $getAuthorizationPayload
$getAuthorizationInteraction = Join-Path $evidence ($TransitionNonce + '.get_authorization_interaction.json')
& $upgradeClient 'GET_AUTHORIZATION' $getAuthorizationPayload $getAuthorizationInteraction
if ($LASTEXITCODE -ne 0) { throw 'Signed authorization could not be resolved from the upgrade authority.' }
$resolvedAuthorization = Get-Content -Raw -LiteralPath $getAuthorizationInteraction | ConvertFrom-Json
if ($resolvedAuthorization.response.status -cne 'COMPLETE' -or $resolvedAuthorization.response.result_code -cne 'UPGRADE_AUTHORIZATION_RESOLVED' -or $resolvedAuthorization.response.authorization_identity -cne $authorizationIdentity) { throw 'Resolved authorization response is inconsistent.' }
$resolvedEnvelopePath = Join-Path $evidence ($TransitionNonce + '.resolved_authorization.envelope.json')
[IO.File]::WriteAllBytes($resolvedEnvelopePath, [Convert]::FromBase64String([string]$resolvedAuthorization.response.record))
if ((Get-LowerHash $resolvedEnvelopePath) -cne $authorizationIdentity) { throw 'Resolved authorization envelope identity mismatch.' }
$verifiedAuthorizationPayloadPath = Join-Path $evidence ($TransitionNonce + '.verified_authorization_payload.json')
$upgradeCertificatePath = Join-Path $upgradeStateRoot 'Trust\upgrade_authority_public.cer'
& $artifactTool verify-envelope $resolvedEnvelopePath $upgradeCertificatePath ([string]$summary.upgrade_public_certificate_sha256) $verifiedAuthorizationPayloadPath
if ($LASTEXITCODE -ne 0) { throw 'Upgrade authorization signature verification failed.' }
$verifiedAuthorization = Get-Content -Raw -LiteralPath $verifiedAuthorizationPayloadPath | ConvertFrom-Json
Assert-ExactPropertySet $verifiedAuthorization @('activation_sequence','authorization_time','authority_class','build_receipt_sha256','components','dependency_manifest_sha256','host_binding','installer_identity','new_interface_version','old_interface_version','old_policy_sha256','old_service_binary_sha256','operation','request_frame_sha256','request_identity','request_payload_identity','revocation_state','rollback_constraints','schema_version','source_commit','source_tree','staging_root','transition_nonce','verification_object_identity') 'Verified authorization'
if ($verifiedAuthorization.operation -cne 'AUTHORIZE_TERMINAL_UPGRADE' -or $verifiedAuthorization.authority_class -cne 'TERMINAL_UPGRADE_AUTHORIZATION' -or $verifiedAuthorization.revocation_state -cne 'ACTIVE' -or $verifiedAuthorization.transition_nonce -cne $TransitionNonce -or $verifiedAuthorization.staging_root -cne $stageRoot -or $verifiedAuthorization.source_commit -cne $summary.source_commit -or $verifiedAuthorization.source_tree -cne $summary.source_tree) { throw 'Verified authorization semantics mismatch.' }
Assert-ExactPropertySet $verifiedAuthorization.installer_identity @('executable_sha256','script_sha256') 'Verified installer identity'
if ($verifiedAuthorization.installer_identity.script_sha256 -cne $runningInstallerSha256 -or $verifiedAuthorization.installer_identity.executable_sha256 -cne (Get-LowerHash $upgradeClient)) { throw 'Running installer or upgrade client differs from the signed pre-install authorization.' }
$authorizedComponents = @{}
foreach ($row in @($verifiedAuthorization.components)) {
    Assert-ExactPropertySet $row @('file_identity','final_path','final_path_preinstall_state','role','sha256','size','staging_relative_path') ('Authorized component ' + [string]$row.role)
    if ($row.final_path_preinstall_state -cne 'ABSENT' -or $authorizedComponents.ContainsKey([string]$row.role)) { throw 'Authorized component set is duplicated or was not pre-install.' }
    $templateRow = @($template.components | Where-Object { $_.role -ceq [string]$row.role })
    if ($templateRow.Count -ne 1 -or $templateRow[0].sha256 -cne $row.sha256 -or $templateRow[0].final_path -cne $row.final_path -or $templateRow[0].staging_relative_path -cne $row.staging_relative_path) { throw 'Signed component differs from the submitted governed transition set.' }
    $stagedPath = Join-Path $stageRoot ([string]$row.staging_relative_path).Replace('/','\')
    if ((Get-LowerHash $stagedPath) -cne [string]$row.sha256) { throw 'Staged component changed after pre-install authorization.' }
    $authorizedComponents[[string]$row.role] = $row
}
if ($authorizedComponents.Count -ne @($template.components).Count) { throw 'Signed authorization component count mismatch.' }
$authorizedBuildReceipt = Get-Content -Raw -LiteralPath (Join-Path $stageRoot ([string]$authorizedComponents.BUILD_RECEIPT.staging_relative_path).Replace('/','\')) | ConvertFrom-Json
if ($authorizedBuildReceipt.bootstrap_artifact_tool_sha256 -cne (Get-LowerHash $artifactTool)) { throw 'Authorized installer tool is not the tool bound by the build receipt.' }

$expectedOldTerminalBinary = 'C:\Program Files\RandleAI\TerminalAuthority\RandleTerminalAuthority.exe'
$oldTerminalImagePath = [string](Get-ItemProperty -LiteralPath ('Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\' + $terminalService) -Name ImagePath -ErrorAction Stop).ImagePath
$oldTerminalObjectName = [string](Get-ItemProperty -LiteralPath ('Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\' + $terminalService) -Name ObjectName -ErrorAction Stop).ObjectName
$normalizedOldTerminalImagePath = $oldTerminalImagePath.Trim().Trim('"')
if ([IO.Path]::GetFullPath($normalizedOldTerminalImagePath) -cne $expectedOldTerminalBinary -or $oldTerminalObjectName -cne $terminalAccount) { throw 'Current terminal service configuration differs from the governed prechange identity.' }
$oldTerminalConfig = (& $scExecutable qc $terminalService 2>&1 | Out-String)
$oldTerminalRequiredPrivileges = @((Get-ItemProperty -LiteralPath ('Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\' + $terminalService) -Name RequiredPrivileges -ErrorAction Stop).RequiredPrivileges)
if ($oldTerminalRequiredPrivileges.Count -eq 0) { throw 'Current terminal service has no restorable privilege configuration.' }
$terminalInstallRootPreexisting = Test-Path -LiteralPath $terminalInstallRoot
$remediationRootPreexisting = Test-Path -LiteralPath $remediationRoot
$executionStateRootPreexisting = Test-Path -LiteralPath 'C:\ProgramData\RandleAI\TerminalExecution'
$observationStateRootPreexisting = Test-Path -LiteralPath 'C:\ProgramData\RandleAI\TerminalObservation'
$comparatorStateRootPreexisting = Test-Path -LiteralPath 'C:\ProgramData\RandleAI\TerminalComparator'
$installedFinalPaths = [Collections.Generic.List[string]]::new()
$tradingBefore = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match 'EntryAgent|TradeManager|TradingView|ngrok|Rithmic|executor|tick_receiver' } | Select-Object Id,ProcessName,StartTime
$terminalStopped = $false
$terminalConfigurationChanged = $false
$serviceBoundaries = [Collections.Generic.List[object]]::new()
try {
    Stop-Service -Name $terminalService -Force
    Wait-ServiceState $terminalService 'Stopped' 30
    $terminalStopped = $true

    $authorityManifestPath = Join-Path $stageRoot ([string]$authorizedComponents.AUTHORITY_PACKAGE_MANIFEST.staging_relative_path).Replace('/','\')
    if ((Get-LowerHash $authorityManifestPath) -cne [string]$authorizedComponents.AUTHORITY_PACKAGE_MANIFEST.sha256) { throw 'Authorized authority-package manifest changed before installation.' }
    $authorityManifest = Get-Content -Raw -LiteralPath $authorityManifestPath | ConvertFrom-Json
    Assert-ExactPropertySet $authorityManifest @('artifact_type','files','prohibited_source_commit','prohibited_source_dependency_count','schema_version','source_commit','source_tree') 'Authority package manifest'
    if ($authorityManifest.artifact_type -cne 'R7_CONTENT_ADDRESSED_AUTHORITY_PACKAGE_MANIFEST' -or [long]$authorityManifest.prohibited_source_dependency_count -ne 0 -or $authorityManifest.prohibited_source_commit -cne 'f0cfbce97e913a133530dd66a70326b1e03a0fb6' -or $authorityManifest.source_commit -cne $summary.source_commit -or $authorityManifest.source_tree -cne $summary.source_tree) { throw 'Authority package manifest semantics mismatch.' }
    $manifestByRelativePath = @{}
    foreach ($row in @($authorityManifest.files)) {
        Assert-ExactPropertySet $row @('final_path','raw_sha256','size','staging_relative_path') ('Manifest row ' + [string]$row.staging_relative_path)
        if ($manifestByRelativePath.ContainsKey([string]$row.staging_relative_path)) { throw 'Duplicate authority-package manifest path.' }
        $manifestByRelativePath[[string]$row.staging_relative_path] = $row
        $source = Join-Path $stageRoot ([string]$row.staging_relative_path).Replace('/','\')
        if ((Get-LowerHash $source) -cne [string]$row.raw_sha256 -or (Get-Item -LiteralPath $source).Length -ne [long]$row.size) { throw "Staged component changed after authorization: $source" }
    }
    foreach ($authorized in @($authorizedComponents.Values | Where-Object { $_.role -cne 'AUTHORITY_PACKAGE_MANIFEST' })) {
        $manifestRow = $manifestByRelativePath[[string]$authorized.staging_relative_path]
        if ($null -eq $manifestRow -or $manifestRow.raw_sha256 -cne $authorized.sha256 -or $manifestRow.final_path -cne $authorized.final_path) { throw ('Signed component is not identically bound by the authority-package manifest: ' + [string]$authorized.role) }
    }
    $allowedStageFiles = @($manifestByRelativePath.Keys) + @('authority/authority_package_manifest.json','installer/install_authorized_transition.ps1')
    foreach ($stageFile in Get-ChildItem -LiteralPath $stageRoot -File -Recurse) {
        $relativeStageFile = (Get-RelativePath $stageRoot $stageFile.FullName).Replace('\','/')
        if ($allowedStageFiles -cnotcontains $relativeStageFile) { throw "Unmanifested staging file: $relativeStageFile" }
    }
    foreach ($row in @($authorityManifest.files)) {
        $source = Join-Path $stageRoot ([string]$row.staging_relative_path).Replace('/','\')
        $destination = [string]$row.final_path
        Durable-Copy $source $destination
        Set-SystemOwner $destination
        $installedFinalPaths.Add([IO.Path]::GetFullPath($destination))
    }
    $manifestDestination = Join-Path $remediationRoot 'Authority\authority_package_manifest.json'
    Durable-Copy $authorityManifestPath $manifestDestination
    Set-SystemOwner $manifestDestination
    $installedFinalPaths.Add([IO.Path]::GetFullPath($manifestDestination))
    $activeTransition = Join-Path $remediationRoot 'Trust\active_upgrade_transition.json'
    Durable-Copy $authorizationRecord $activeTransition
    Set-SystemOwner $activeTransition
    $installedFinalPaths.Add([IO.Path]::GetFullPath($activeTransition))

    foreach ($directory in @(
        (Join-Path $remediationRoot 'Objects'),(Join-Path $remediationRoot 'Receipts'),(Join-Path $remediationRoot 'Responses'),(Join-Path $remediationRoot 'Evidence'),(Join-Path $remediationRoot 'Recovery'),
        'C:\ProgramData\RandleAI\TerminalExecution','C:\ProgramData\RandleAI\TerminalExecution\TestRoots','C:\ProgramData\RandleAI\TerminalExecution\TestRoots\PublicVerifierProbes','C:\ProgramData\RandleAI\TerminalObservation','C:\ProgramData\RandleAI\TerminalComparator'
    )) { if (-not (Test-Path -LiteralPath $directory)) { New-Item -ItemType Directory -Path $directory | Out-Null }; Set-SystemOwner $directory }

    Invoke-Checked $icaclsExecutable @($terminalInstallRoot, '/inheritance:r', '/grant:r', 'SYSTEM:(OI)(CI)(F)', 'BUILTIN\Administrators:(OI)(CI)(F)', "$terminalAccount`:(OI)(CI)(RX)", "$upgradeAccount`:(OI)(CI)(RX)", "$executionAccount`:(OI)(CI)(RX)", "$observationAccount`:(OI)(CI)(RX)", "$comparatorAccount`:(OI)(CI)(RX)", '/T', '/C')
    Invoke-Checked $icaclsExecutable @($remediationRoot, '/inheritance:r', '/grant:r', 'SYSTEM:(OI)(CI)(F)', 'BUILTIN\Administrators:(OI)(CI)(F)', "$terminalAccount`:(OI)(CI)(RX)", "$upgradeAccount`:(OI)(CI)(RX)", 'BUILTIN\Users:(OI)(CI)(RX)', '/T', '/C')
    foreach ($mutableRoot in @(
        (Join-Path $remediationRoot 'Objects'),
        (Join-Path $remediationRoot 'Receipts'),
        (Join-Path $remediationRoot 'Responses'),
        (Join-Path $remediationRoot 'Evidence'),
        (Join-Path $remediationRoot 'Recovery')
    )) {
        Invoke-Checked $icaclsExecutable @($mutableRoot, '/inheritance:r', '/grant:r', 'SYSTEM:(OI)(CI)(F)', 'BUILTIN\Administrators:(OI)(CI)(F)', "$terminalAccount`:(OI)(CI)(F)", 'BUILTIN\Users:(OI)(CI)(RX)', '/T', '/C')
    }
    $casePath = Join-Path $remediationRoot 'Authority\immutable_case_definitions.json'
    $expectationPath = Join-Path $remediationRoot 'Authority\immutable_expectations.json'
    $dependencyPath = Join-Path $remediationRoot 'Config\dependency_manifest.json'
    Invoke-Checked $icaclsExecutable @($casePath, '/grant:r', "$executionAccount`:(R)", "$comparatorAccount`:(R)")
    Invoke-Checked $icaclsExecutable @($expectationPath, '/inheritance:r', '/grant:r', 'SYSTEM:(F)', 'BUILTIN\Administrators:(F)', "$terminalAccount`:(R)", "$comparatorAccount`:(R)", 'BUILTIN\Users:(R)', '/deny', "$executionAccount`:(R)", "$observationAccount`:(R)")
    Invoke-Checked $icaclsExecutable @($dependencyPath, '/grant:r', "$executionAccount`:(R)", "$observationAccount`:(R)", "$comparatorAccount`:(R)", 'BUILTIN\Users:(R)')
    Invoke-Checked $icaclsExecutable @('C:\ProgramData\RandleAI\TerminalExecution', '/inheritance:r', '/grant:r', 'SYSTEM:(OI)(CI)(F)', 'BUILTIN\Administrators:(OI)(CI)(F)', "$executionAccount`:(OI)(CI)(F)", "$terminalAccount`:(OI)(CI)(RX)", '/T', '/C')
    Invoke-Checked $icaclsExecutable @('C:\ProgramData\RandleAI\TerminalExecution\TestRoots\PublicVerifierProbes', '/inheritance:r', '/grant:r', 'SYSTEM:(OI)(CI)(F)', 'BUILTIN\Administrators:(OI)(CI)(F)', "$operatorSid`:(OI)(CI)(M)", "$terminalAccount`:(OI)(CI)(RX)", '/T', '/C')
    Invoke-Checked $icaclsExecutable @('C:\ProgramData\RandleAI\TerminalObservation', '/inheritance:r', '/grant:r', 'SYSTEM:(OI)(CI)(F)', 'BUILTIN\Administrators:(OI)(CI)(F)', "$observationAccount`:(OI)(CI)(F)", "$terminalAccount`:(OI)(CI)(RX)", '/T', '/C')
    Invoke-Checked $icaclsExecutable @('C:\ProgramData\RandleAI\TerminalComparator', '/inheritance:r', '/grant:r', 'SYSTEM:(OI)(CI)(F)', 'BUILTIN\Administrators:(OI)(CI)(F)', "$comparatorAccount`:(OI)(CI)(F)", "$terminalAccount`:(OI)(CI)(RX)", '/T', '/C')
    Invoke-Checked $icaclsExecutable @((Join-Path $terminalStateRoot 'Ledger'), '/inheritance:r', '/grant:r', 'SYSTEM:(OI)(CI)(F)', 'BUILTIN\Administrators:(OI)(CI)(F)', "$terminalAccount`:(OI)(CI)(F)", '/T', '/C')
    Invoke-Checked $icaclsExecutable @((Join-Path $terminalStateRoot 'Trust'), '/inheritance:r', '/grant:r', 'SYSTEM:(OI)(CI)(F)', 'BUILTIN\Administrators:(OI)(CI)(F)', "$terminalAccount`:(OI)(CI)(R)", 'BUILTIN\Users:(OI)(CI)(R)', '/T', '/C')
    $authorityDirectories = @(
        'C:\Program Files\RandleAI\TerminalAuthorityV4',
        'C:\ProgramData\RandleAI\TerminalAuthority',
        'C:\ProgramData\RandleAI\TerminalAuthority\Ledger',
        'C:\ProgramData\RandleAI\TerminalAuthority\Trust',
        'C:\ProgramData\RandleAI\TerminalAuthority\Evidence',
        'C:\ProgramData\RandleAI\TerminalAuthority\Receipts',
        'C:\ProgramData\RandleAI\TerminalAuthority\Reconciliations',
        'C:\ProgramData\RandleAI\TerminalAuthority\Responses',
        'C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4',
        'C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Authority',
        'C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Authority\AuthoritySources',
        'C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Build',
        'C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Build\BuildInputClosures',
        'C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Build\SourceInputs',
        'C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Config',
        'C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Trust',
        'C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Objects',
        'C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Receipts',
        'C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Responses',
        'C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Evidence',
        'C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Recovery',
        'C:\ProgramData\RandleAI\TerminalExecution',
        'C:\ProgramData\RandleAI\TerminalExecution\TestRoots',
        'C:\ProgramData\RandleAI\TerminalExecution\TestRoots\PublicVerifierProbes',
        'C:\ProgramData\RandleAI\TerminalObservation',
        'C:\ProgramData\RandleAI\TerminalComparator',
        'C:\Program Files\RandleAI\TerminalUpgradeAuthority',
        'C:\ProgramData\RandleAI\TerminalUpgradeAuthority',
        'C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Config',
        'C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Config\BuildInputClosures',
        'C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Config\SourceInputs',
        'C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Trust',
        'C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Ledger',
        'C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Authorizations',
        'C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Objects',
        'C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Activations',
        'C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Staging',
        'C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Recovery'
    )
    foreach ($directory in $authorityDirectories) {
        if (-not (Test-Path -LiteralPath $directory -PathType Container)) { throw "Required authority directory is absent: $directory" }
        Set-SystemDirectoryOwner $directory
        Invoke-Checked $icaclsExecutable @($directory, '/grant:r', "$upgradeAccount`:(RX)")
    }

    Ensure-Service 'RandleTerminalExecution' (Join-Path $terminalInstallRoot 'RandleTerminalExecution.exe') $executionAccount
    Ensure-Service 'RandleTerminalObservation' (Join-Path $terminalInstallRoot 'RandleTerminalObservation.exe') $observationAccount
    Ensure-Service 'RandleTerminalComparator' (Join-Path $terminalInstallRoot 'RandleTerminalComparator.exe') $comparatorAccount
    $serviceBoundaries.Add((Assert-ServiceBoundary 'RandleTerminalExecution' (Join-Path $terminalInstallRoot 'RandleTerminalExecution.exe') ($TransitionNonce + '.execution')))
    $serviceBoundaries.Add((Assert-ServiceBoundary 'RandleTerminalObservation' (Join-Path $terminalInstallRoot 'RandleTerminalObservation.exe') ($TransitionNonce + '.observation')))
    $serviceBoundaries.Add((Assert-ServiceBoundary 'RandleTerminalComparator' (Join-Path $terminalInstallRoot 'RandleTerminalComparator.exe') ($TransitionNonce + '.comparator')))
    Invoke-Checked $scExecutable @('config', $terminalService, ('binPath= "' + (Join-Path $terminalInstallRoot 'RandleTerminalAuthority.exe') + '"'))
    Invoke-Checked $scExecutable @('sidtype', $terminalService, 'restricted')
    Invoke-Checked $scExecutable @('privs', $terminalService, 'SeChangeNotifyPrivilege')
    $terminalConfigurationChanged = $true
    $serviceBoundaries.Add((Assert-ServiceBoundary $terminalService (Join-Path $terminalInstallRoot 'RandleTerminalAuthority.exe') ($TransitionNonce + '.terminal')))
    $installedHarness = [string]$authorizedComponents.ADVERSARIAL_HARNESS.final_path
    Start-Service 'RandleTerminalObservation'; Wait-ServiceState 'RandleTerminalObservation' 'Running' 30
    Start-Service 'RandleTerminalComparator'; Wait-ServiceState 'RandleTerminalComparator' 'Running' 30
    Start-Service 'RandleTerminalExecution'; Wait-ServiceState 'RandleTerminalExecution' 'Running' 30
    Assert-RoleHealth $installedHarness 'observation' 'OBSERVATION_ROLE_HEALTHY' 'preactivation-observation'
    Assert-RoleHealth $installedHarness 'comparator' 'COMPARATOR_ROLE_HEALTHY' 'preactivation-comparator'
    Assert-RoleHealth $installedHarness 'execution' 'EXECUTION_ROLE_HEALTHY' 'preactivation-execution'
    Start-Service $terminalService; Wait-ServiceState $terminalService 'Running' 30
    Assert-RoleHealth $installedHarness 'terminal' 'AUTHORITY_HEALTHY' 'postactivation-terminal' 'GET_HEALTH'

    $tradingAfter = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match 'EntryAgent|TradeManager|TradingView|ngrok|Rithmic|executor|tick_receiver' } | Select-Object Id,ProcessName,StartTime
    $installationRecord = [ordered]@{artifact_type='R7_AUTHORIZED_TERMINAL_TRANSITION_INSTALLATION';authorization_identity=$authorizationIdentity;installed_interface='4.0.0-REMEDIATION';old_terminal_service_config=$oldTerminalConfig;schema_version='1.0.0';service_boundaries=@($serviceBoundaries | ForEach-Object { $_.measurement });services=@('RandleTerminalUpgradeAuthority','RandleTerminalObservation','RandleTerminalComparator','RandleTerminalExecution','RandleTerminalAuthority');source_commit=$summary.source_commit;source_tree=$summary.source_tree;trading_processes_after=$tradingAfter;trading_processes_before=$tradingBefore;transition_nonce=$TransitionNonce}
    Write-Canonical $installationRecord (Join-Path $evidence ($TransitionNonce + '.installation_record.json'))
} catch {
    $failure = $_
    foreach ($name in @('RandleTerminalExecution','RandleTerminalObservation','RandleTerminalComparator')) {
        if (Get-Service -Name $name -ErrorAction SilentlyContinue) {
            try { Stop-Service -Name $name -Force -ErrorAction SilentlyContinue; Wait-ServiceState $name 'Stopped' 30 } catch {}
        }
    }
    $activationPath = Join-Path $upgradeStateRoot ('Activations\' + $TransitionNonce + '.activation.json')
    if (-not (Test-Path -LiteralPath $activationPath)) {
        $revocationPayload = Join-Path $evidence ($TransitionNonce + '.revocation_payload.json')
        Write-Canonical ([ordered]@{reason='INSTALLATION_FAILED_BEFORE_ACTIVATION';transition_nonce=$TransitionNonce}) $revocationPayload
        & $upgradeClient 'REVOKE_AUTHORIZATION' $revocationPayload (Join-Path $evidence ($TransitionNonce + '.revocation_interaction.json')) | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Separate upgrade authority failed to revoke the unactivated authorization.' }
        if (-not $terminalStopped) {
            $unchangedImagePath = [string](Get-ItemProperty -LiteralPath ('Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\' + $terminalService) -Name ImagePath -ErrorAction Stop).ImagePath
            if ([IO.Path]::GetFullPath($unchangedImagePath.Trim().Trim('"')) -cne $expectedOldTerminalBinary) { throw 'Pre-install failure unexpectedly changed the terminal service image path.' }
            $oldService = Get-Service -Name $terminalService -ErrorAction Stop
            if ($oldService.Status -eq [System.ServiceProcess.ServiceControllerStatus]::StopPending) {
                $oldService.WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Stopped, [TimeSpan]::FromSeconds(30))
                $oldService.Refresh()
            }
            if ($oldService.Status -eq [System.ServiceProcess.ServiceControllerStatus]::Stopped) {
                Start-Service -Name $terminalService
                Wait-ServiceState $terminalService 'Running' 30
            } elseif ($oldService.Status -ne [System.ServiceProcess.ServiceControllerStatus]::Running) {
                throw ('Old terminal service entered an unexpected state after pre-install failure: ' + $oldService.Status.ToString())
            }
            Write-Canonical ([ordered]@{artifact_type='R7_PREINSTALL_AUTHORIZATION_REVOCATION';authorization_identity=$authorizationIdentity;failure=[string]$failure;host_installation_started=$false;old_terminal_binary=$expectedOldTerminalBinary;schema_version='1.0.0';transition_nonce=$TransitionNonce}) (Join-Path $evidence ($TransitionNonce + '.preinstall_authorization_revocation.json'))
            throw $failure
        }
        for ($boundaryIndex = $serviceBoundaries.Count - 1; $boundaryIndex -ge 0; $boundaryIndex--) {
            $boundary = $serviceBoundaries[$boundaryIndex]
            Restore-ServiceBoundary $boundary ($TransitionNonce + '.' + [string]$boundary.measurement.service_name + '.rollback')
        }
        if ($terminalConfigurationChanged) {
            Invoke-Checked $scExecutable @('config', $terminalService, ('binPath= "' + $expectedOldTerminalBinary + '"'))
            Invoke-Checked $scExecutable @('privs', $terminalService, ([string]::Join('/', [string[]]$oldTerminalRequiredPrivileges)))
        }
        foreach ($name in @('RandleTerminalExecution','RandleTerminalObservation','RandleTerminalComparator')) {
            if (Get-Service -Name $name -ErrorAction SilentlyContinue) { Invoke-Checked $scExecutable @('delete', $name) }
        }

        $failedRoot = Join-Path $upgradeStateRoot ('FailedInstallations\' + $TransitionNonce)
        if (Test-Path -LiteralPath $failedRoot) { throw 'Failure-quarantine root already exists.' }
        New-Item -ItemType Directory -Path $failedRoot | Out-Null
        Invoke-Checked $icaclsExecutable @($failedRoot, '/inheritance:r', '/grant:r', 'SYSTEM:(OI)(CI)(F)', 'BUILTIN\Administrators:(OI)(CI)(F)', "$upgradeAccount`:(OI)(CI)(RX)", 'BUILTIN\Users:(OI)(CI)(RX)', '/T', '/C')
        $quarantined = [Collections.Generic.List[object]]::new()
        $rootRows = @(
            [ordered]@{label='ProgramFiles-TerminalAuthorityV4';path=$terminalInstallRoot;preexisting=$terminalInstallRootPreexisting},
            [ordered]@{label='ProgramData-RemediationV4';path=$remediationRoot;preexisting=$remediationRootPreexisting},
            [ordered]@{label='ProgramData-TerminalExecution';path='C:\ProgramData\RandleAI\TerminalExecution';preexisting=$executionStateRootPreexisting},
            [ordered]@{label='ProgramData-TerminalObservation';path='C:\ProgramData\RandleAI\TerminalObservation';preexisting=$observationStateRootPreexisting},
            [ordered]@{label='ProgramData-TerminalComparator';path='C:\ProgramData\RandleAI\TerminalComparator';preexisting=$comparatorStateRootPreexisting}
        )
        foreach ($rootRow in $rootRows) {
            if (-not [bool]$rootRow.preexisting -and (Test-Path -LiteralPath ([string]$rootRow.path))) {
                $destination = Join-Path $failedRoot ([string]$rootRow.label)
                $inventory = @()
                foreach ($file in Get-ChildItem -LiteralPath ([string]$rootRow.path) -File -Recurse -ErrorAction Stop) { $inventory += [ordered]@{relative_path=(Get-RelativePath ([string]$rootRow.path) $file.FullName);sha256=(Get-LowerHash $file.FullName);size=$file.Length} }
                Move-Item -LiteralPath ([string]$rootRow.path) -Destination $destination -ErrorAction Stop
                $quarantined.Add([ordered]@{destination=$destination;files=$inventory;original_path=[string]$rootRow.path})
            }
        }
        if ($terminalInstallRootPreexisting -or $remediationRootPreexisting) {
            foreach ($installedPath in @($installedFinalPaths | Sort-Object -Descending)) {
                if (-not (Test-Path -LiteralPath $installedPath -PathType Leaf)) { continue }
                if ($installedPath.StartsWith($terminalInstallRoot + '\',[StringComparison]::Ordinal)) { $relativeInstalled = 'preexisting-roots\ProgramFiles\' + (Get-RelativePath $terminalInstallRoot $installedPath) }
                elseif ($installedPath.StartsWith($remediationRoot + '\',[StringComparison]::Ordinal)) { $relativeInstalled = 'preexisting-roots\ProgramData\' + (Get-RelativePath $remediationRoot $installedPath) }
                else { throw "Installed rollback path escaped dedicated roots: $installedPath" }
                $quarantineDestination = Join-Path $failedRoot $relativeInstalled
                $quarantineParent = Split-Path -Parent $quarantineDestination
                if (-not (Test-Path -LiteralPath $quarantineParent)) { New-Item -ItemType Directory -Path $quarantineParent -Force | Out-Null }
                $quarantineHash = Get-LowerHash $installedPath
                $quarantineSize = (Get-Item -LiteralPath $installedPath).Length
                Move-Item -LiteralPath $installedPath -Destination $quarantineDestination -ErrorAction Stop
                $quarantined.Add([ordered]@{destination=$quarantineDestination;files=@([ordered]@{relative_path=[IO.Path]::GetFileName($installedPath);sha256=$quarantineHash;size=$quarantineSize});original_path=$installedPath})
            }
        }
        Write-Canonical ([ordered]@{artifact_type='R7_PREACTIVATION_FAILURE_QUARANTINE';authorization_identity=$authorizationIdentity;failure=[string]$failure;old_terminal_binary=$expectedOldTerminalBinary;quarantined=$quarantined.ToArray();schema_version='1.0.0';transition_nonce=$TransitionNonce}) (Join-Path $evidence ($TransitionNonce + '.preactivation_failure_quarantine.json'))
        Start-Service -Name $terminalService
        Wait-ServiceState $terminalService 'Running' 30
    } elseif (Test-Path -LiteralPath $activationPath) {
        if ((Get-Service -Name $terminalService -ErrorAction SilentlyContinue).Status -ne 'Stopped') { Stop-Service -Name $terminalService -Force -ErrorAction SilentlyContinue; Wait-ServiceState $terminalService 'Stopped' 30 }
        Write-Canonical ([ordered]@{activation_identity=(Get-LowerHash $activationPath);artifact_type='R7_POSTACTIVATION_FAILURE_BLOCKER';failure=[string]$failure;required_action='SEPARATE_GOVERNED_ROLLBACK_OR_FORWARD_FIX';schema_version='1.0.0';transition_nonce=$TransitionNonce}) (Join-Path $evidence ($TransitionNonce + '.postactivation_failure_blocker.json'))
    }
    throw $failure
}
