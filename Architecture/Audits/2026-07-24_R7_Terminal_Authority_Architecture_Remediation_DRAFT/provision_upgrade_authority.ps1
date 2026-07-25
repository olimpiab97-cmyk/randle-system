[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$EvidenceRoot,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$SourceCommit,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$SourceTree,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedScriptSha256,
    [Parameter(Mandatory = $true)][string]$PriorFailedAttemptEvidence,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedPriorFailedAttemptSha256
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$serviceName = 'RandleTerminalUpgradeAuthority'
$serviceAccount = 'NT SERVICE\RandleTerminalUpgradeAuthority'
$terminalAccount = 'NT SERVICE\RandleTerminalAuthority'
$expectedSid = 'S-1-5-80-238545627-4117296865-2677355104-248304369-1301198082'
$installRoot = 'C:\Program Files\RandleAI\TerminalUpgradeAuthority'
$stateRoot = 'C:\ProgramData\RandleAI\TerminalUpgradeAuthority'
$binaryPath = Join-Path $installRoot 'RandleTerminalUpgradeAuthority.exe'
$trustRoot = Join-Path $stateRoot 'Trust'
$certificatePath = Join-Path $trustRoot 'upgrade_authority_public.cer'
$scExecutable = 'C:\Windows\System32\sc.exe'
$icaclsExecutable = 'C:\Windows\System32\icacls.exe'
$powershellExecutable = [IO.Path]::GetFullPath((Get-Process -Id $PID).Path)
$pkiModuleManifest = Join-Path $PSHOME 'Modules\PKI\PKI.psd1'
$governedUtilityHashes = @{}

function Get-LowerHash([string]$Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function Get-ByteHash([byte[]]$Bytes) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($Bytes)).Replace('-','')).ToLowerInvariant() }
    finally { $algorithm.Dispose() }
}
function Get-ProvisioningDependencies {
    $paths = [Collections.Generic.List[string]]::new()
    foreach ($path in @($powershellExecutable,$scExecutable,$icaclsExecutable)) { $paths.Add([IO.Path]::GetFullPath($path)) }
    $pkiRoot = Split-Path -Parent $pkiModuleManifest
    foreach ($file in Get-ChildItem -LiteralPath $pkiRoot -File -Recurse | Sort-Object FullName) { $paths.Add([IO.Path]::GetFullPath($file.FullName)) }
    $rows = [Collections.Generic.List[object]]::new()
    foreach ($path in $paths) { $item = Get-Item -LiteralPath $path -ErrorAction Stop; $rows.Add([ordered]@{path=$path;raw_sha256=(Get-LowerHash $path);size=$item.Length}) }
    return $rows.ToArray()
}
function Get-DependencySetIdentity([object[]]$Rows) {
    $json = $Rows | ConvertTo-Json -Depth 8 -Compress
    return Get-ByteHash ([Text.Encoding]::UTF8.GetBytes($json))
}

function Assert-DedicatedPath([string]$Path, [string]$RequiredRoot) {
    $resolved = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    $root = [IO.Path]::GetFullPath($RequiredRoot).TrimEnd('\')
    if ($resolved -ne $root -and -not $resolved.StartsWith($root + '\', [StringComparison]::Ordinal)) {
        throw "Path escapes dedicated authority root: $resolved"
    }
}

function Invoke-Checked([string]$FilePath, [string[]]$Arguments) {
    $full = [IO.Path]::GetFullPath($FilePath)
    $expected = [string]$governedUtilityHashes[$full]
    if ($expected -notmatch '^[0-9a-f]{64}$' -or (Get-LowerHash $full) -cne $expected) { throw "Provisioning utility identity mismatch before use: $full" }
    & $full @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$FilePath exited $LASTEXITCODE" }
    if ((Get-LowerHash $full) -cne $expected) { throw "Provisioning utility identity changed during use: $full" }
}
function Capture-Checked([string]$FilePath, [string[]]$Arguments) {
    $full = [IO.Path]::GetFullPath($FilePath)
    $expected = [string]$governedUtilityHashes[$full]
    if ($expected -notmatch '^[0-9a-f]{64}$' -or (Get-LowerHash $full) -cne $expected) { throw "Provisioning utility identity mismatch before captured use: $full" }
    $output = (& $full @Arguments 2>&1 | Out-String)
    $exit = $LASTEXITCODE
    if ((Get-LowerHash $full) -cne $expected) { throw "Provisioning utility identity changed during captured use: $full" }
    if ($exit -ne 0) { throw "$full exited $exit" }
    return $output
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Elevation is required.' }
if ((Get-LowerHash $PSCommandPath) -cne $ExpectedScriptSha256) { throw 'Provisioning script does not match the governed committed identity.' }
$priorFailurePath = [IO.Path]::GetFullPath($PriorFailedAttemptEvidence)
if (-not (Test-Path -LiteralPath $priorFailurePath -PathType Leaf) -or (Get-LowerHash $priorFailurePath) -cne $ExpectedPriorFailedAttemptSha256) { throw 'Prior failed-attempt evidence identity mismatch.' }
$priorFailure = Get-Content -LiteralPath $priorFailurePath -Raw | ConvertFrom-Json
if ([string]$priorFailure.artifact_type -cne 'R7_UNIT2_FAILED_BOOTSTRAP_ATTEMPT' -or
    [string]$priorFailure.failure_classification -cne 'SAFE_PRE_SERVICE_CREATE_ARGUMENT_FRAMING_FAILURE' -or
    [string]$priorFailure.status -cne 'PRESERVED_NONAUTHORITY_FAILURE' -or
    [bool]$priorFailure.service_exists -or [int]$priorFailure.certificate_count -ne 0 -or
    [int]$priorFailure.observed_file_count -ne 0 -or [int]@($priorFailure.observed_directories).Count -ne 12 -or
    [string]$priorFailure.terminal_authority_effect -cne 'NONE') { throw 'Prior failed-attempt evidence is not the governed safe pre-service failure.' }
foreach ($required in @($powershellExecutable,$scExecutable,$icaclsExecutable,$pkiModuleManifest)) { if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Provisioning dependency missing: $required" } }
$dependenciesBefore = @(Get-ProvisioningDependencies)
$dependenciesBeforeIdentity = Get-DependencySetIdentity $dependenciesBefore
$governedUtilityHashes[$scExecutable] = [string](@($dependenciesBefore | Where-Object { $_.path -ceq $scExecutable })[0].raw_sha256)
$governedUtilityHashes[$icaclsExecutable] = [string](@($dependenciesBefore | Where-Object { $_.path -ceq $icaclsExecutable })[0].raw_sha256)
Import-Module -Name $pkiModuleManifest -Force -ErrorAction Stop

$evidence = [IO.Path]::GetFullPath($EvidenceRoot)
if (-not (Test-Path -LiteralPath $evidence)) { New-Item -ItemType Directory -Path $evidence | Out-Null }
if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) { throw 'Upgrade authority service already exists; refusing bootstrap replay.' }
if (Test-Path -LiteralPath $certificatePath) { throw 'Upgrade public certificate already exists; refusing key replacement.' }
Assert-DedicatedPath $installRoot 'C:\Program Files\RandleAI'
Assert-DedicatedPath $stateRoot 'C:\ProgramData\RandleAI'

foreach ($directory in @(
    $installRoot,
    $stateRoot,
    (Join-Path $stateRoot 'Activations'),
    (Join-Path $stateRoot 'Authorizations'),
    (Join-Path $stateRoot 'Config'),
    (Join-Path $stateRoot 'Config\BuildInputClosures'),
    (Join-Path $stateRoot 'Config\SourceInputs'),
    (Join-Path $stateRoot 'Ledger'),
    (Join-Path $stateRoot 'Objects'),
    (Join-Path $stateRoot 'Recovery'),
    (Join-Path $stateRoot 'Staging'),
    $trustRoot
)) {
    if (-not (Test-Path -LiteralPath $directory)) { New-Item -ItemType Directory -Path $directory | Out-Null }
}

Invoke-Checked $scExecutable @('create', $serviceName, 'binPath=', $binaryPath, 'start=', 'demand', 'obj=', $serviceAccount)
Invoke-Checked $scExecutable @('sidtype', $serviceName, 'restricted')
Invoke-Checked $scExecutable @('privs', $serviceName, 'SeChangeNotifyPrivilege')
Invoke-Checked $scExecutable @('failure', $serviceName, 'reset=', '86400', 'actions=', 'restart/5000')

$sidOutput = Capture-Checked $scExecutable @('showsid',$serviceName)
if ($sidOutput -notmatch [regex]::Escape($expectedSid)) { throw 'Resolved service SID does not match the governed principal identity.' }

$certificate = New-SelfSignedCertificate `
    -Subject 'CN=Randle Terminal Upgrade Authority 2026-07-24' `
    -FriendlyName 'Randle Terminal Upgrade Authority 2026-07-24' `
    -CertStoreLocation 'Cert:\LocalMachine\My' `
    -KeyAlgorithm RSA `
    -KeyLength 3072 `
    -HashAlgorithm SHA256 `
    -KeyExportPolicy NonExportable `
    -KeySpec Signature `
    -Provider 'Microsoft Software Key Storage Provider' `
    -NotAfter ([DateTimeOffset]::UtcNow.AddYears(10).UtcDateTime)
if (-not $certificate.HasPrivateKey) { throw 'Upgrade authority certificate lacks a private key.' }
Export-Certificate -Cert $certificate -FilePath $certificatePath -Type CERT | Out-Null

$rsa = [Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($certificate)
try {
    if ($rsa.KeySize -ne 3072) { throw 'Upgrade key is not RSA-3072.' }
    $uniqueName = $rsa.Key.UniqueName
    if ([string]::IsNullOrWhiteSpace($uniqueName)) { throw 'CNG unique key name is unavailable.' }
} finally {
    $rsa.Dispose()
}
$keyPath = Join-Path 'C:\ProgramData\Microsoft\Crypto\Keys' $uniqueName
if (-not (Test-Path -LiteralPath $keyPath -PathType Leaf)) { throw 'Nonexportable CNG key file was not found.' }

Invoke-Checked $icaclsExecutable @($keyPath, '/setowner', 'SYSTEM')
Invoke-Checked $icaclsExecutable @($keyPath, '/inheritance:r', '/grant:r', 'SYSTEM:(F)', "$serviceAccount`:(R)")
foreach ($root in @($installRoot, $stateRoot)) {
    Invoke-Checked $icaclsExecutable @($root, '/setowner', 'SYSTEM', '/T', '/C')
    Invoke-Checked $icaclsExecutable @($root, '/inheritance:r', '/grant:r', 'SYSTEM:(OI)(CI)(F)', 'BUILTIN\Administrators:(OI)(CI)(F)', "$serviceAccount`:(OI)(CI)(RX)", "$terminalAccount`:(OI)(CI)(RX)", 'BUILTIN\Users:(OI)(CI)(RX)', '/T', '/C')
}
foreach ($mutableRoot in @(
    (Join-Path $stateRoot 'Activations'),
    (Join-Path $stateRoot 'Authorizations'),
    (Join-Path $stateRoot 'Ledger'),
    (Join-Path $stateRoot 'Objects'),
    (Join-Path $stateRoot 'Recovery')
)) {
    Invoke-Checked $icaclsExecutable @($mutableRoot, '/inheritance:r', '/grant:r', 'SYSTEM:(OI)(CI)(F)', 'BUILTIN\Administrators:(OI)(CI)(F)', "$serviceAccount`:(OI)(CI)(F)", "$terminalAccount`:(OI)(CI)(RX)", 'BUILTIN\Users:(OI)(CI)(RX)', '/T', '/C')
}
Invoke-Checked $icaclsExecutable @($certificatePath, '/inheritance:r', '/grant:r', 'SYSTEM:(F)', 'BUILTIN\Administrators:(F)', "$serviceAccount`:(R)", "$terminalAccount`:(R)", 'BUILTIN\Users:(R)')

$certificateHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $certificatePath).Hash.ToLowerInvariant()
$keyAcl = (Get-Acl -LiteralPath $keyPath).Sddl
$sha = [Security.Cryptography.SHA256]::Create()
try { $keyAclHash = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($keyAcl))).Replace('-', '')).ToLowerInvariant() } finally { $sha.Dispose() }
$serviceConfig = Capture-Checked $scExecutable @('qc',$serviceName)
$servicePrivileges = Capture-Checked $scExecutable @('qprivs',$serviceName)
$serviceSidType = Capture-Checked $scExecutable @('qsidtype',$serviceName)
$dependenciesAfter = @(Get-ProvisioningDependencies)
$dependenciesAfterIdentity = Get-DependencySetIdentity $dependenciesAfter
if ($dependenciesAfterIdentity -cne $dependenciesBeforeIdentity) { throw 'Provisioning dependency set changed during use.' }
$record = [ordered]@{
    artifact_type = 'R7_SEPARATE_UPGRADE_AUTHORITY_BOOTSTRAP_RECORD'
    bootstrap_authority = 'EXPLICIT_R7_REMEDIATION_AUTHORIZATION_ONLY'
    certificate_path = $certificatePath
    key_algorithm = 'RSA-3072-PSS-SHA256'
    key_export_policy = 'NONEXPORTABLE'
    key_file_acl_sha256 = $keyAclHash
    key_unique_name = $uniqueName
    interactive_logon_denial = 'DEFERRED_TO_MEASURED_PRESTART_BOOTSTRAP'
    private_key_exported = $false
    prior_failed_attempt_sha256 = $ExpectedPriorFailedAttemptSha256
    prior_failed_attempt_status = 'PRESERVED_NONAUTHORITY_FAILURE'
    provisioning_dependencies = $dependenciesBefore
    provisioning_dependency_set_sha256 = $dependenciesBeforeIdentity
    provisioning_script_sha256 = $ExpectedScriptSha256
    public_certificate_sha256 = $certificateHash
    schema_version = '1.0.0'
    service_account = $serviceAccount
    service_config = $serviceConfig
    service_privileges = $servicePrivileges
    service_sid = $expectedSid
    service_sid_resolution = $sidOutput
    service_sid_type = $serviceSidType
    source_commit = $SourceCommit
    source_tree = $SourceTree
}
$recordPath = Join-Path $evidence 'upgrade_authority_bootstrap_record.json'
[IO.File]::WriteAllText($recordPath, ($record | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
Get-FileHash -Algorithm SHA256 -LiteralPath $recordPath, $certificatePath | Format-Table -AutoSize
