[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ArtifactTool,
    [Parameter(Mandatory=$true)][string]$OutputRoot
)

$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$root=Split-Path -Parent $PSCommandPath
$tool=[IO.Path]::GetFullPath($ArtifactTool)
$output=[IO.Path]::GetFullPath($OutputRoot)
if(-not(Test-Path -LiteralPath $tool -PathType Leaf)){throw 'Artifact tool is absent'}
if(Test-Path -LiteralPath $output){throw 'Failure-action regression output root must be new'}
New-Item -ItemType Directory -Path $output|Out-Null

$installerPath=Join-Path $root 'complete_unit2_upgrade_authority.ps1'
$helperPath=Join-Path $root 'Source\R7ServiceFailureActions.cs'
$artifactSourcePath=Join-Path $root 'Source\R7ArtifactTool.cs'
$installer=Get-Content -LiteralPath $installerPath -Raw
$helper=Get-Content -LiteralPath $helperPath -Raw
$artifactSource=Get-Content -LiteralPath $artifactSourcePath -Raw

$forbiddenInstaller=@(
    "RunScMutation @('failure'",
    "RunScMutation @('failureflag'",
    "@('qfailure'",
    "@('qfailureflag'",
    "'actions=',''"
)
foreach($token in $forbiddenInstaller){if($installer.Contains($token)){throw "Legacy shell failure-action path remains: $token"}}

$requiredInstaller=@(
    "@('capture-failure-actions'",
    "@('configure-failure-actions-none'",
    "@('verify-failure-actions-none'",
    "@('restore-failure-actions'",
    '$failureActionsRestoreRequired=$true',
    'AssertStopped'
)
foreach($token in $requiredInstaller){if(-not $installer.Contains($token)){throw "Installer failure-action binding missing: $token"}}

$requiredHelper=@(
    'OpenSCManagerW',
    'OpenServiceW',
    'ChangeServiceConfig2W',
    'QueryServiceConfig2W',
    'ServiceConfigFailureActions = 2',
    'ServiceConfigFailureActionsFlag = 4',
    'NON_NULL_SENTINEL_WITH_ZERO_COUNT',
    'FAILURE_ACTION_HELPER_FAILED_CLOSED_ROLLBACK_COMPLETE',
    'FAILURE_ACTION_ROLLBACK_MISMATCH'
)
foreach($token in $requiredHelper){if(-not $helper.Contains($token)){throw "Native helper invariant missing: $token"}}

foreach($command in @('capture-failure-actions','configure-failure-actions-none','verify-failure-actions-none','restore-failure-actions','failure-actions-regression')){if(-not $artifactSource.Contains('args[0] == "'+$command+'"')){throw "Artifact-tool command absent: $command"}}

$regressionPath=Join-Path $output 'failure_action_regression.json'
$toolOutput=@(& $tool 'failure-actions-regression' $regressionPath 2>&1|ForEach-Object{[string]$_})
if($LASTEXITCODE -ne 0){throw "Failure-action regression executable failed: $($toolOutput -join ' | ')"}
$regression=Get-Content -LiteralPath $regressionPath -Raw|ConvertFrom-Json
$expected=@(
    'EMPTY_ACTION_SET_REPRESENTED',
    'PRIOR_RESTART_5000_CAPTURED',
    'TARGET_CONTAINS_ZERO_ACTIONS',
    'NONZERO_ACTION_READBACK_REJECTED',
    'RESTART_READBACK_REJECTED',
    'RUN_COMMAND_READBACK_REJECTED',
    'REBOOT_READBACK_REJECTED',
    'ROLLBACK_RECONSTRUCTS_RESTART_5000',
    'EMPTY_ARGUMENT_OMISSION_DETECTED',
    'LITERAL_QUOTE_CORRUPTION_DETECTED',
    'EXTRA_ACTION_DETECTED',
    'HELPER_FAILURE_FAILS_CLOSED'
)
if([string]$regression.status -cne 'PASS' -or [bool]$regression.native_api_invoked -or [int64]$regression.case_count -ne $expected.Count){throw 'Failure-action regression envelope invalid'}
$actual=@($regression.cases|ForEach-Object{if([string]$_.status -cne 'PASS'){throw "Regression case failed: $([string]$_.case)"};[string]$_.case})
if(($actual -join "`n") -cne ($expected -join "`n")){throw 'Failure-action regression case inventory mismatch'}

$result=[ordered]@{
    artifact_type='R7_FAILURE_ACTION_CONFIGURATION_STATIC_VERIFICATION'
    case_count=$expected.Count
    helper_sha256=(Get-FileHash -LiteralPath $helperPath -Algorithm SHA256).Hash.ToLowerInvariant()
    installer_sha256=(Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
    native_api_invoked=$false
    regression_sha256=(Get-FileHash -LiteralPath $regressionPath -Algorithm SHA256).Hash.ToLowerInvariant()
    schema_version='1.0.0'
    status='PASS'
}
$resultPath=Join-Path $output 'failure_action_static_verification.json'
[IO.File]::WriteAllText($resultPath,($result|ConvertTo-Json -Depth 10 -Compress),[Text.UTF8Encoding]::new($false))
$result|ConvertTo-Json -Depth 10
