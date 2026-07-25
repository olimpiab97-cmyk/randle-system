[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$EvidenceRoot,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$SourceCommit,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$SourceTree,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedScriptSha256,
    [Parameter(Mandatory = $true)][string]$PriorFailedAttemptEvidence,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedPriorFailedAttemptSha256,
    [Parameter(Mandatory = $true)][string]$SecondFailedAttemptEvidence,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedSecondFailedAttemptSha256,
    [Parameter(Mandatory = $true)][string]$ThirdFailedAttemptEvidence,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedThirdFailedAttemptSha256
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$serviceName = 'RandleTerminalUpgradeAuthority'
$serviceAccount = 'NT SERVICE\RandleTerminalUpgradeAuthority'
$terminalAccount = 'NT SERVICE\RandleTerminalAuthority'
$expectedSid = 'S-1-5-80-238545627-4117296865-2677355104-248304369-1301198082'
$terminalSid = 'S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948'
$installRoot = 'C:\Program Files\RandleAI\TerminalUpgradeAuthority'
$stateRoot = 'C:\ProgramData\RandleAI\TerminalUpgradeAuthority'
$binaryPath = Join-Path $installRoot 'RandleTerminalUpgradeAuthority.exe'
$trustRoot = Join-Path $stateRoot 'Trust'
$certificatePath = Join-Path $trustRoot 'upgrade_authority_public.cer'
$scExecutable = 'C:\Windows\System32\sc.exe'
$icaclsExecutable = 'C:\Windows\System32\icacls.exe'
$takeownExecutable = 'C:\Windows\System32\takeown.exe'
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
    foreach ($path in @($powershellExecutable,$scExecutable,$icaclsExecutable,$takeownExecutable)) { $paths.Add([IO.Path]::GetFullPath($path)) }
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

function Assert-DedicatedDirectoryAcl([string]$Path, [bool]$ServiceMayWrite) {
    $item = Get-Item -LiteralPath $Path -Force
    if (-not $item.PSIsContainer -or (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { throw "Dedicated authority directory is absent or reparsed: $Path" }
    $acl = Get-Acl -LiteralPath $Path
    if ($acl.Owner -cne 'NT AUTHORITY\SYSTEM' -or -not $acl.AreAccessRulesProtected) { throw "Dedicated authority directory owner or inheritance differs: $Path" }
    $rules = @($acl.GetAccessRules($true, $false, [Security.Principal.SecurityIdentifier]))
    if (@($rules | Where-Object { $_.IsInherited -or $_.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow }).Count -ne 0) { throw "Dedicated authority directory contains inherited or deny rules: $Path" }
    $systemSid = 'S-1-5-18'; $adminSid = 'S-1-5-32-544'; $usersSid = 'S-1-5-32-545'
    $expectedSids = @($systemSid,$adminSid,$usersSid,$expectedSid,$terminalSid) | Sort-Object
    $actualSids = @($rules | ForEach-Object { $_.IdentityReference.Value } | Sort-Object -Unique)
    if (($expectedSids -join ',') -cne ($actualSids -join ',')) { throw "Dedicated authority directory principal set differs: $Path" }
    $writeRights = [int64]([Security.AccessControl.FileSystemRights]::WriteData -bor [Security.AccessControl.FileSystemRights]::AppendData -bor [Security.AccessControl.FileSystemRights]::WriteExtendedAttributes -bor [Security.AccessControl.FileSystemRights]::WriteAttributes -bor [Security.AccessControl.FileSystemRights]::Delete -bor [Security.AccessControl.FileSystemRights]::ChangePermissions -bor [Security.AccessControl.FileSystemRights]::TakeOwnership)
    foreach ($sid in @($usersSid,$terminalSid)) {
        $rule = @($rules | Where-Object { $_.IdentityReference.Value -ceq $sid })
        $rights = $(if ($rule.Count -eq 1) { [int64]$rule[0].FileSystemRights } else { 0 })
        if ($rule.Count -ne 1 -or (($rights -band $writeRights) -ne 0) -or (($rights -band [int64][Security.AccessControl.FileSystemRights]::ReadAndExecute) -ne [int64][Security.AccessControl.FileSystemRights]::ReadAndExecute)) { throw "Dedicated authority directory public or terminal rule is not read-and-execute only: $Path / $sid" }
    }
    foreach ($sid in @($systemSid,$adminSid)) {
        $rule = @($rules | Where-Object { $_.IdentityReference.Value -ceq $sid })
        if ($rule.Count -ne 1 -or (([int64]$rule[0].FileSystemRights -band [int64][Security.AccessControl.FileSystemRights]::FullControl) -ne [int64][Security.AccessControl.FileSystemRights]::FullControl)) { throw "Dedicated authority directory administrative rule is not full control: $Path / $sid" }
    }
    $serviceRule = @($rules | Where-Object { $_.IdentityReference.Value -ceq $expectedSid })
    if ($serviceRule.Count -ne 1) { throw "Dedicated authority service rule is absent or ambiguous: $Path" }
    $serviceRights = [int64]$serviceRule[0].FileSystemRights
    if ($ServiceMayWrite) {
        if (($serviceRights -band [int64][Security.AccessControl.FileSystemRights]::FullControl) -ne [int64][Security.AccessControl.FileSystemRights]::FullControl) { throw "Dedicated mutable directory does not grant service full control: $Path" }
    } elseif (($serviceRights -band $writeRights) -ne 0 -or ($serviceRights -band [int64][Security.AccessControl.FileSystemRights]::ReadAndExecute) -ne [int64][Security.AccessControl.FileSystemRights]::ReadAndExecute) {
        throw "Dedicated immutable directory service rule is not read-and-execute only: $Path"
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
$secondFailurePath = [IO.Path]::GetFullPath($SecondFailedAttemptEvidence)
if (-not (Test-Path -LiteralPath $secondFailurePath -PathType Leaf) -or (Get-LowerHash $secondFailurePath) -cne $ExpectedSecondFailedAttemptSha256) { throw 'Second failed-attempt evidence identity mismatch.' }
$secondFailure = Get-Content -LiteralPath $secondFailurePath -Raw | ConvertFrom-Json
if ([string]$secondFailure.artifact_type -cne 'R7_UNIT2_FAILED_BOOTSTRAP_ATTEMPT' -or
    [string]$secondFailure.failure_classification -cne 'SAFE_POST_SERVICE_CREATE_CNG_KEYSPEC_COMPATIBILITY_FAILURE' -or
    [string]$secondFailure.status -cne 'PRESERVED_NONAUTHORITY_FAILURE' -or
    [string]$secondFailure.service.state -cne 'Stopped' -or [int]$secondFailure.certificate_count -ne 0 -or
    [int]$secondFailure.new_authority_file_count -ne 0 -or [bool]$secondFailure.private_key_created -or
    [string]$secondFailure.terminal_authority_effect -cne 'NONE') { throw 'Second failed-attempt evidence is not the governed stopped-service CNG compatibility failure.' }
$thirdFailurePath = [IO.Path]::GetFullPath($ThirdFailedAttemptEvidence)
if (-not (Test-Path -LiteralPath $thirdFailurePath -PathType Leaf) -or (Get-LowerHash $thirdFailurePath) -cne $ExpectedThirdFailedAttemptSha256) { throw 'Third failed-attempt evidence identity mismatch.' }
$thirdFailure = Get-Content -LiteralPath $thirdFailurePath -Raw | ConvertFrom-Json
if ([string]$thirdFailure.artifact_type -cne 'R7_UNIT2_FAILED_BOOTSTRAP_ATTEMPT' -or
    [string]$thirdFailure.failure_classification -cne 'SAFE_POST_KEY_AND_PUBLIC_CERTIFICATE_CERTIFICATE_ACL_REWRITE_FAILURE' -or
    [string]$thirdFailure.status -cne 'PRESERVED_NONAUTHORITY_FAILURE' -or
    [string]$thirdFailure.source_commit -cne '12d07030cd3674978603b3f0f9afe4a88f3f4f64' -or
    [string]$thirdFailure.service.state -cne 'Stopped' -or [int64]$thirdFailure.service.process_id -ne 0 -or
    [string]$thirdFailure.service.account -cne $serviceAccount -or [string]$thirdFailure.service.binary_path -cne $binaryPath -or [string]$thirdFailure.service.start_mode -cne 'Manual' -or
    -not [bool]$thirdFailure.certificate.empty_protected_file_dacl -or
    [string]$thirdFailure.certificate.file_path -cne $certificatePath -or
    [string]$thirdFailure.certificate.file_acl_sddl -notmatch '^O:SY.+D:PAI$' -or
    [string]$thirdFailure.certificate.public_raw_data_sha256 -notmatch '^[0-9a-f]{64}$' -or
    [string]$thirdFailure.certificate.store_thumbprint -notmatch '^[0-9a-f]{40}$' -or
    -not [bool]$thirdFailure.certificate.store_has_private_key_reference -or
    [string]$thirdFailure.key.name -notmatch '^[0-9A-Za-z_-]{1,512}$' -or
    [bool]$thirdFailure.key.private_bytes_read -or [bool]$thirdFailure.key.private_bytes_exported -or
    [string]$thirdFailure.terminal_authority_effect -cne 'NONE') { throw 'Third failed-attempt evidence is not the governed stopped-service certificate-ACL failure.' }
foreach ($required in @($powershellExecutable,$scExecutable,$icaclsExecutable,$takeownExecutable,$pkiModuleManifest)) { if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Provisioning dependency missing: $required" } }
$dependenciesBefore = @(Get-ProvisioningDependencies)
$dependenciesBeforeIdentity = Get-DependencySetIdentity $dependenciesBefore
$governedUtilityHashes[$scExecutable] = [string](@($dependenciesBefore | Where-Object { $_.path -ceq $scExecutable })[0].raw_sha256)
$governedUtilityHashes[$icaclsExecutable] = [string](@($dependenciesBefore | Where-Object { $_.path -ceq $icaclsExecutable })[0].raw_sha256)
$governedUtilityHashes[$takeownExecutable] = [string](@($dependenciesBefore | Where-Object { $_.path -ceq $takeownExecutable })[0].raw_sha256)
Import-Module -Name $pkiModuleManifest -Force -ErrorAction Stop

$evidence = [IO.Path]::GetFullPath($EvidenceRoot)
if (-not (Test-Path -LiteralPath $evidence)) { New-Item -ItemType Directory -Path $evidence | Out-Null }
if (-not (Get-Service -Name $serviceName -ErrorAction SilentlyContinue)) { throw 'Preserved stopped upgrade service is absent; refusing discontinuous bootstrap.' }
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
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) { throw "Preserved dedicated authority directory is absent: $directory" }
}

$immutableDirectories = @($installRoot,$stateRoot,(Join-Path $stateRoot 'Config'),(Join-Path $stateRoot 'Config\BuildInputClosures'),(Join-Path $stateRoot 'Config\SourceInputs'),(Join-Path $stateRoot 'Staging'),$trustRoot)
$mutableDirectories = @((Join-Path $stateRoot 'Activations'),(Join-Path $stateRoot 'Authorizations'),(Join-Path $stateRoot 'Ledger'),(Join-Path $stateRoot 'Objects'),(Join-Path $stateRoot 'Recovery'))
foreach ($directory in $immutableDirectories) { Assert-DedicatedDirectoryAcl $directory $false }
foreach ($directory in $mutableDirectories) { Assert-DedicatedDirectoryAcl $directory $true }

$existingService = Get-CimInstance Win32_Service -Filter "Name='$serviceName'"
if ($null -eq $existingService -or [string]$existingService.State -cne 'Stopped' -or [int64]$existingService.ProcessId -ne 0 -or
    [string]$existingService.StartName -cne $serviceAccount -or [string]$existingService.PathName -cne $binaryPath -or
    [string]$existingService.StartMode -cne 'Manual') { throw 'Preserved upgrade service configuration differs from the governed failed-attempt state.' }

$sidOutput = Capture-Checked $scExecutable @('showsid',$serviceName)
if ($sidOutput -notmatch [regex]::Escape($expectedSid)) { throw 'Resolved service SID does not match the governed principal identity.' }

$storeThumbprint = ([string]$thirdFailure.certificate.store_thumbprint).ToUpperInvariant()
$subjectCertificates = @(Get-ChildItem -Path 'Cert:\LocalMachine\My' | Where-Object { [string]$_.Subject -ceq [string]$thirdFailure.certificate.store_subject })
if ($subjectCertificates.Count -ne 1 -or $subjectCertificates[0].Thumbprint.ToUpperInvariant() -cne $storeThumbprint) { throw 'Preserved upgrade certificate identity is absent, ambiguous, or conflicting.' }
$certificate = $subjectCertificates[0]
if ([string]$certificate.Subject -cne [string]$thirdFailure.certificate.store_subject -or -not $certificate.HasPrivateKey) { throw 'Preserved upgrade certificate metadata differs from failed-attempt evidence.' }
$publicRawHash = Get-ByteHash $certificate.RawData
if ($publicRawHash -cne [string]$thirdFailure.certificate.public_raw_data_sha256) { throw 'Preserved public certificate bytes differ from failed-attempt evidence.' }
$publicRsa = [Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPublicKey($certificate)
try { if ($null -eq $publicRsa -or $publicRsa.KeySize -ne 3072) { throw 'Preserved public certificate is not RSA-3072.' } } finally { if ($null -ne $publicRsa) { $publicRsa.Dispose() } }

$uniqueName = [string]$thirdFailure.key.name
$keyPath = Join-Path 'C:\ProgramData\Microsoft\Crypto\Keys' $uniqueName
if (-not (Test-Path -LiteralPath $keyPath -PathType Leaf)) { throw 'Nonexportable CNG key file was not found.' }
$keyItem = Get-Item -LiteralPath $keyPath -Force
$keyAclBefore = Get-Acl -LiteralPath $keyPath
if ($keyItem.Length -ne [int64]$thirdFailure.key.length -or $keyAclBefore.Owner -cne [string]$thirdFailure.key.owner -or $keyAclBefore.Sddl -cne [string]$thirdFailure.key.acl_sddl) { throw 'Preserved upgrade key metadata differs from failed-attempt evidence.' }
$certificateAclBefore = Get-Acl -LiteralPath $certificatePath
if ($certificateAclBefore.Sddl -cne [string]$thirdFailure.certificate.file_acl_sddl) { throw 'Preserved public-certificate ACL differs from failed-attempt evidence.' }

$reexportPath = Join-Path $evidence 'upgrade_authority_public_from_store.cer'
if (Test-Path -LiteralPath $reexportPath) { throw 'Public-certificate re-export evidence path already exists.' }
Export-Certificate -Cert $certificate -FilePath $reexportPath -Type CERT | Out-Null
if ((Get-LowerHash $reexportPath) -cne $publicRawHash) { throw 'Public certificate export does not equal the preserved certificate bytes.' }

Invoke-Checked $takeownExecutable @('/F', $certificatePath, '/A')
Invoke-Checked $icaclsExecutable @($certificatePath, '/grant:r', 'SYSTEM:(F)', 'BUILTIN\Administrators:(F)', "$serviceAccount`:(R)", "$terminalAccount`:(R)", 'BUILTIN\Users:(R)')
Invoke-Checked $icaclsExecutable @($certificatePath, '/setowner', 'SYSTEM')
Invoke-Checked $icaclsExecutable @($keyPath, '/inheritance:r', '/grant:r', 'SYSTEM:(F)', "$serviceAccount`:(R)", 'BUILTIN\Administrators:(RA,RC)')
Invoke-Checked $icaclsExecutable @($keyPath, '/setowner', 'SYSTEM')

$certificateHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $certificatePath).Hash.ToLowerInvariant()
$keyAcl = (Get-Acl -LiteralPath $keyPath).Sddl
$certificateAcl = (Get-Acl -LiteralPath $certificatePath).Sddl
$sha = [Security.Cryptography.SHA256]::Create()
try { $keyAclHash = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($keyAcl))).Replace('-', '')).ToLowerInvariant() } finally { $sha.Dispose() }
$sha = [Security.Cryptography.SHA256]::Create()
try { $certificateAclHash = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($certificateAcl))).Replace('-', '')).ToLowerInvariant() } finally { $sha.Dispose() }
if ($certificateHash -cne $publicRawHash) { throw 'Recovered fixed public certificate differs from the preserved store identity.' }
$keyAclObject = Get-Acl -LiteralPath $keyPath
$keyRules = @($keyAclObject.GetAccessRules($true, $false, [Security.Principal.SecurityIdentifier]))
$adminSid = 'S-1-5-32-544'
$serviceSid = $expectedSid
$systemSid = 'S-1-5-18'
$observedSids = @($keyRules | ForEach-Object { $_.IdentityReference.Value } | Sort-Object -Unique)
$expectedSids = @($adminSid,$systemSid,$serviceSid) | Sort-Object
if (($observedSids -join ',') -cne ($expectedSids -join ',') -or $observedSids -contains $terminalSid) { throw 'Recovered key ACL principal set is not closed.' }
if (@($keyRules | Where-Object { $_.IsInherited }).Count -ne 0 -or $keyAclObject.Owner -cne 'NT AUTHORITY\SYSTEM') { throw 'Recovered key ACL inheritance or owner is not closed.' }
$adminRule = @($keyRules | Where-Object { $_.IdentityReference.Value -ceq $adminSid })
if ($adminRule.Count -ne 1) { throw 'Recovered key ACL administrator metadata rule is absent or ambiguous.' }
$adminRights = [int64]$adminRule[0].FileSystemRights
$allowedAdminRights = [int64]([Security.AccessControl.FileSystemRights]::ReadAttributes -bor [Security.AccessControl.FileSystemRights]::ReadPermissions)
if (($adminRights -band (-bnot $allowedAdminRights)) -ne 0) { throw 'Recovered key ACL grants Administrators more than metadata-read rights.' }
$serviceRule = @($keyRules | Where-Object { $_.IdentityReference.Value -ceq $serviceSid })
$systemRule = @($keyRules | Where-Object { $_.IdentityReference.Value -ceq $systemSid })
if ($serviceRule.Count -ne 1 -or $systemRule.Count -ne 1) { throw 'Recovered key ACL authority rules are absent or ambiguous.' }
$serviceRights = [int64]$serviceRule[0].FileSystemRights
$prohibitedServiceRights = [int64]([Security.AccessControl.FileSystemRights]::WriteData -bor [Security.AccessControl.FileSystemRights]::AppendData -bor [Security.AccessControl.FileSystemRights]::WriteExtendedAttributes -bor [Security.AccessControl.FileSystemRights]::WriteAttributes -bor [Security.AccessControl.FileSystemRights]::Delete -bor [Security.AccessControl.FileSystemRights]::ChangePermissions -bor [Security.AccessControl.FileSystemRights]::TakeOwnership)
if (($serviceRights -band [int64][Security.AccessControl.FileSystemRights]::ReadData) -eq 0 -or ($serviceRights -band $prohibitedServiceRights) -ne 0) { throw 'Recovered key ACL service rule is not read-only.' }
if (([int64]$systemRule[0].FileSystemRights -band [int64][Security.AccessControl.FileSystemRights]::FullControl) -ne [int64][Security.AccessControl.FileSystemRights]::FullControl) { throw 'Recovered key ACL SYSTEM rule is not full control.' }
$serviceConfig = Capture-Checked $scExecutable @('qc',$serviceName)
$servicePrivileges = Capture-Checked $scExecutable @('qprivs',$serviceName)
$serviceSidType = Capture-Checked $scExecutable @('qsidtype',$serviceName)
$dependenciesAfter = @(Get-ProvisioningDependencies)
$dependenciesAfterIdentity = Get-DependencySetIdentity $dependenciesAfter
if ($dependenciesAfterIdentity -cne $dependenciesBeforeIdentity) { throw 'Provisioning dependency set changed during use.' }
$rootAclEvidence = @(foreach ($directory in @(($immutableDirectories + $mutableDirectories) | Sort-Object -Unique)) { $acl = Get-Acl -LiteralPath $directory; [ordered]@{ owner=$acl.Owner; path=$directory; sddl=$acl.Sddl; sddl_sha256=(Get-ByteHash ([Text.Encoding]::UTF8.GetBytes($acl.Sddl))) } })
$record = [ordered]@{
    artifact_type = 'R7_SEPARATE_UPGRADE_AUTHORITY_BOOTSTRAP_RECORD'
    bootstrap_authority = 'EXPLICIT_R7_REMEDIATION_AUTHORIZATION_ONLY'
    certificate_path = $certificatePath
    key_algorithm = 'RSA-3072-PSS-SHA256'
    key_export_policy = 'NONEXPORTABLE'
    key_file_acl_sha256 = $keyAclHash
    key_file_acl_sddl = $keyAcl
    key_unique_name = $uniqueName
    interactive_logon_denial = 'DEFERRED_TO_MEASURED_PRESTART_BOOTSTRAP'
    private_key_exported = $false
    prior_failed_attempt_sha256 = $ExpectedPriorFailedAttemptSha256
    prior_failed_attempt_status = 'PRESERVED_NONAUTHORITY_FAILURE'
    second_failed_attempt_sha256 = $ExpectedSecondFailedAttemptSha256
    second_failed_attempt_status = 'PRESERVED_NONAUTHORITY_FAILURE'
    third_failed_attempt_sha256 = $ExpectedThirdFailedAttemptSha256
    third_failed_attempt_status = 'PRESERVED_NONAUTHORITY_FAILURE'
    provisioning_dependencies = $dependenciesBefore
    provisioning_dependency_set_sha256 = $dependenciesBeforeIdentity
    provisioning_script_sha256 = $ExpectedScriptSha256
    root_acl_evidence = $rootAclEvidence
    public_certificate_sha256 = $certificateHash
    public_certificate_file_acl_sha256 = $certificateAclHash
    public_certificate_file_acl_sddl = $certificateAcl
    public_certificate_store_thumbprint = $storeThumbprint.ToLowerInvariant()
    public_export_evidence_path = $reexportPath
    public_export_sha256 = (Get-LowerHash $reexportPath)
    recovery_utility = [ordered]@{ path=$takeownExecutable; raw_sha256=[string]$governedUtilityHashes[$takeownExecutable]; operation='CERTIFICATE_FILE_OWNER_RECOVERY_ONLY' }
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
