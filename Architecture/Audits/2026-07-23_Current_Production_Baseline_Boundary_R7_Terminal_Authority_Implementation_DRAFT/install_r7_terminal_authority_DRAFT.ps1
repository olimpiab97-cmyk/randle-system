[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$serviceName = 'RandleTerminalAuthority'
$buildRoot = 'C:\Users\Trader\AppData\Local\Temp\r7i_b01_build_preinstall'
$packageRoot = 'C:\Users\Trader\AppData\Local\Temp\randle_r7_terminal_implementation_20260723_bb04ac5\Architecture\Audits\2026-07-23_Current_Production_Baseline_Boundary_R7_Terminal_Authority_Implementation_DRAFT'
$installRoot = 'C:\Program Files\RandleAI\TerminalAuthority'
$subjectRoot = 'C:\Program Files\RandleAI\TerminalAuthority\R7ExecutionSubject'
$configRoot = 'C:\ProgramData\RandleAI\TerminalAuthority\Config'
$authorityRoot = 'C:\ProgramData\RandleAI\TerminalAuthority\Config\R7Authorities'
$fixtureReceiptRoot = 'C:\ProgramData\RandleAI\TerminalAuthority\Evidence\R7FixtureProcessReceipts'
$rollbackRoot = 'C:\Users\Trader\AppData\Local\Temp\r7i_b01_correction_20260723_preflight\rollback_original_v1'
$serviceSid = 'S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948'

$artifacts = @(
    [pscustomobject]@{ Source = "$buildRoot\RandleTerminalAuthority.exe"; Target = "$installRoot\RandleTerminalAuthority.exe"; Sha256 = '9ea829416f37c94db2858586fa5e0042652f6caa4637a29fdbefb513577a7526' },
    [pscustomobject]@{ Source = "$buildRoot\RandleTerminalAuthorityR7Worker.exe"; Target = "$installRoot\RandleTerminalAuthorityR7Worker.exe"; Sha256 = 'b2971b85de73d999bfa801d047b22c2ec6fc3d6bc5cb5923ea4a9ab240ed4401' },
    [pscustomobject]@{ Source = "$buildRoot\RandleTerminalAuthorityR7Client.exe"; Target = "$installRoot\RandleTerminalAuthorityR7Client.exe"; Sha256 = '8d5a5e803c9b7c17f06a488ef815b138d9de1dcd666ab1d4c333414801d4b6e9' },
    [pscustomobject]@{ Source = "$buildRoot\RandleTerminalAuthorityR7PublicVerifier.exe"; Target = "$installRoot\RandleTerminalAuthorityR7PublicVerifier.exe"; Sha256 = '88c4e631035af0c7ec366256c78f4d1f21994554a30201b30b4d6bf775314a3d' },
    [pscustomobject]@{ Source = "$buildRoot\RandleTerminalAuthorityR7FixtureHost.exe"; Target = "$subjectRoot\powershell.exe"; Sha256 = '7a82bab5acfa36555d0e3b9cf29084101f8276b4ceba93cd48cc1e85fadf1454' },
    [pscustomobject]@{ Source = "$packageRoot\r7_terminal_authority_policy_DRAFT.json"; Target = "$configRoot\r7_terminal_authority_policy.json"; Sha256 = '76eb2900b2000aa0b41e6040335cc323f7443728aad21cd871d5b6b8e17bcd8b' },
    [pscustomobject]@{ Source = "$packageRoot\r7_real_case_definitions_DRAFT.json"; Target = "$authorityRoot\r7_real_case_definitions.json"; Sha256 = '58d6c043b857b6950d375724ef1f05b695028a3778ee47067284148c477b9214' },
    [pscustomobject]@{ Source = "$packageRoot\r7_independent_expectations_DRAFT.json"; Target = "$authorityRoot\r7_independent_expectations.json"; Sha256 = '7563a8b8af74f15ad226d61015d0946867fa1d18495143e8206600f1c3c81005' }
)

function Get-LowerSha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "MISSING_FILE:$Path" }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-Hash([string]$Path, [string]$Expected) {
    $actual = Get-LowerSha256 $Path
    if ($actual -cne $Expected) { throw "SHA256_MISMATCH:${Path}:${actual}:${Expected}" }
}

function Wait-ServiceState([string]$State, [int]$Seconds) {
    $controller = New-Object System.ServiceProcess.ServiceController($serviceName)
    try {
        $desired = [System.Enum]::Parse([System.ServiceProcess.ServiceControllerStatus], $State, $false)
        $controller.WaitForStatus($desired, [TimeSpan]::FromSeconds($Seconds))
    }
    finally { $controller.Dispose() }
}

function Restore-ProvisionedAuthority {
    try {
        $state = (Get-Service -Name $serviceName).Status
        if ($state -ne [System.ServiceProcess.ServiceControllerStatus]::Stopped) {
            Stop-Service -Name $serviceName -Force
            Wait-ServiceState 'Stopped' 30
        }
    }
    catch { }
    [System.IO.File]::Copy("$rollbackRoot\RandleTerminalAuthority.exe", "$installRoot\RandleTerminalAuthority.exe", $true)
    [System.IO.File]::Copy("$rollbackRoot\terminal_authority_policy.json", "$configRoot\terminal_authority_policy.json", $true)
    Assert-Hash "$installRoot\RandleTerminalAuthority.exe" '632afaeeaf15c26ac057b34692ac672e03bc02f60fbb35177c378736b5e316ba'
    Assert-Hash "$configRoot\terminal_authority_policy.json" '675a9fa9c761b2738e6b7115366eaf8bb001f6f9ff1f3fb598db2f68ad57fc19'
    Start-Service -Name $serviceName
    Wait-ServiceState 'Running' 30
}

$before = [ordered]@{
    service_state = (Get-Service -Name $serviceName).Status.ToString()
    service_sha256 = Get-LowerSha256 "$installRoot\RandleTerminalAuthority.exe"
    checkpoint_sha256 = Get-LowerSha256 'C:\ProgramData\RandleAI\TerminalAuthority\Ledger\checkpoint.json'
}

foreach ($artifact in $artifacts) { Assert-Hash $artifact.Source $artifact.Sha256 }
Assert-Hash "$rollbackRoot\RandleTerminalAuthority.exe" '632afaeeaf15c26ac057b34692ac672e03bc02f60fbb35177c378736b5e316ba'
Assert-Hash "$rollbackRoot\terminal_authority_policy.json" '675a9fa9c761b2738e6b7115366eaf8bb001f6f9ff1f3fb598db2f68ad57fc19'

try {
    Stop-Service -Name $serviceName
    Wait-ServiceState 'Stopped' 30
    foreach ($artifact in $artifacts) {
        $targetParent = Split-Path -Parent $artifact.Target
        if (-not (Test-Path -LiteralPath $targetParent -PathType Container)) { throw "TARGET_PARENT_MISSING:$targetParent" }
        [System.IO.File]::Copy($artifact.Source, $artifact.Target, $true)
        Assert-Hash $artifact.Target $artifact.Sha256
    }
    if (-not (Test-Path -LiteralPath $fixtureReceiptRoot -PathType Container)) {
        New-Item -ItemType Directory -Path $fixtureReceiptRoot | Out-Null
    }
    $fixtureAcl = Get-Acl -LiteralPath $fixtureReceiptRoot
    $serviceRule = $fixtureAcl.Access | Where-Object {
        $_.IdentityReference.Value -eq 'NT SERVICE\RandleTerminalAuthority' -and
        $_.AccessControlType -eq [System.Security.AccessControl.AccessControlType]::Allow -and
        (($_.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::Modify) -eq [System.Security.AccessControl.FileSystemRights]::Modify)
    }
    if (-not $serviceRule) { throw 'FIXTURE_RECEIPT_ROOT_SERVICE_ACL_MISSING' }
    Start-Service -Name $serviceName
    Wait-ServiceState 'Running' 30
    Start-Sleep -Milliseconds 750
    $healthRaw = & "$installRoot\RandleTerminalAuthorityR7Client.exe" health
    if ($LASTEXITCODE -ne 0) { throw "HEALTH_CLIENT_EXIT:$LASTEXITCODE" }
    $health = $healthRaw | ConvertFrom-Json
    if ($health.status -cne 'COMPLETE' -or $health.result_code -cne 'R7_AUTHORITY_HEALTHY' -or -not $health.healthy -or
        $health.binary_sha256 -cne '9ea829416f37c94db2858586fa5e0042652f6caa4637a29fdbefb513577a7526' -or
        $health.policy_sha256 -cne '76eb2900b2000aa0b41e6040335cc323f7443728aad21cd871d5b6b8e17bcd8b' -or
        $health.worker_sha256 -cne 'b2971b85de73d999bfa801d047b22c2ec6fc3d6bc5cb5923ea4a9ab240ed4401' -or
        $health.service_sid -cne $serviceSid -or $health.repository_write_access) {
        throw 'POST_INSTALL_HEALTH_IDENTITY_REJECTED'
    }
    $sidType = sc.exe qsidtype $serviceName | Out-String
    $privileges = sc.exe qprivs $serviceName | Out-String
    if ($sidType -notmatch 'SERVICE_SID_TYPE:\s+RESTRICTED' -or
        $privileges -notmatch 'SeChangeNotifyPrivilege' -or $privileges -notmatch 'SeImpersonatePrivilege' -or
        $privileges -match 'SeCreateSymbolicLinkPrivilege') {
        throw 'POST_INSTALL_SERVICE_TOKEN_POLICY_REJECTED'
    }
    [pscustomobject]@{
        status = 'CORRECTED_AUTHORITY_INSTALLED'
        rollback_performed = $false
        before = $before
        after = $health
        installed = @($artifacts | ForEach-Object { [pscustomobject]@{ path = $_.Target; sha256 = Get-LowerSha256 $_.Target } })
        fixture_receipt_root = $fixtureReceiptRoot
        fixture_receipt_root_acl_sddl = $fixtureAcl.GetSecurityDescriptorSddlForm([System.Security.AccessControl.AccessControlSections]::All)
    } | ConvertTo-Json -Depth 8 -Compress
}
catch {
    $failure = $_.Exception.Message
    Restore-ProvisionedAuthority
    [pscustomobject]@{
        status = 'INSTALLATION_FAILED_ROLLBACK_COMPLETE'
        failure = $failure
        rollback_performed = $true
        restored_service_sha256 = Get-LowerSha256 "$installRoot\RandleTerminalAuthority.exe"
        restored_service_state = (Get-Service -Name $serviceName).Status.ToString()
    } | ConvertTo-Json -Depth 5 -Compress
    exit 91
}
