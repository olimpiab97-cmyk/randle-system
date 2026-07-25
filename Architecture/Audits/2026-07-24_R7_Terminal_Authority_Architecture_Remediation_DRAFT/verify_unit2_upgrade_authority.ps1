[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$SourceCommit,
    [Parameter(Mandatory=$true)][string]$BuildRoot,
    [Parameter(Mandatory=$true)][string]$PreflightHostState,
    [Parameter(Mandatory=$true)][string]$UtilityRegistry,
    [Parameter(Mandatory=$true)][string]$EvidenceRoot,
    [Parameter(Mandatory=$true)][string]$AttackRoot,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedScriptSha256
)

$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$service='RandleTerminalUpgradeAuthority'
$upgradeSid='S-1-5-80-238545627-4117296865-2677355104-248304369-1301198082'
$terminalSid='S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948'
$operatorSid='S-1-5-21-4259795780-3461844753-1172372902-1001'
$install='C:\Program Files\RandleAI\TerminalUpgradeAuthority'
$state='C:\ProgramData\RandleAI\TerminalUpgradeAuthority'
$build=[IO.Path]::GetFullPath($BuildRoot)
$evidence=[IO.Path]::GetFullPath($EvidenceRoot)
$attack=[IO.Path]::GetFullPath($AttackRoot)

function Hash([string]$path){(Get-FileHash -LiteralPath ([IO.Path]::GetFullPath($path)) -Algorithm SHA256).Hash.ToLowerInvariant()}
function TextHash([string]$value){$sha=[Security.Cryptography.SHA256]::Create();try{([BitConverter]::ToString($sha.ComputeHash([Text.UTF8Encoding]::new($false).GetBytes($value)))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}}
function ReadJson([string]$path){Get-Content -LiteralPath $path -Raw|ConvertFrom-Json}
function WriteJsonNew([object]$value,[string]$path){$full=[IO.Path]::GetFullPath($path);if(Test-Path -LiteralPath $full){throw "Evidence exists: $full"};$parent=Split-Path -Parent $full;if(-not(Test-Path -LiteralPath $parent)){New-Item -ItemType Directory -Path $parent|Out-Null};[IO.File]::WriteAllText($full,($value|ConvertTo-Json -Depth 100),[Text.UTF8Encoding]::new($false));return $full}
function RunSc([string[]]$arguments){& $script:sc @arguments;if($LASTEXITCODE -ne 0){throw "sc.exe failed: $($arguments -join ' ')"}}
function WaitService([string]$expected){$deadline=[DateTime]::UtcNow.AddSeconds(30);do{$value=Get-Service -Name $service -ErrorAction Stop;if([string]$value.Status -ceq $expected){return};Start-Sleep -Milliseconds 250}while([DateTime]::UtcNow -lt $deadline);throw "Service did not reach $expected"}
function RunRole([string]$exe,[string[]]$arguments,[int[]]$expected){$output=@(& $exe @arguments 2>&1);$exit=$LASTEXITCODE;if($expected -notcontains $exit){throw "$exe exited $exit | $($output -join [Environment]::NewLine)"};return [ordered]@{exit_code=$exit;output=$output}}
function RunRejectedRole([string]$exe,[string[]]$arguments){$output=@(& $exe @arguments 2>&1);$exit=$LASTEXITCODE;if($exit -eq 0){throw "$exe unexpectedly succeeded | $($output -join [Environment]::NewLine)"};return [ordered]@{exit_code=$exit;output=$output}}
function TerminalSnapshot {
    $svc=Get-Service -Name 'RandleTerminalAuthority' -ErrorAction Stop
    $cim=Get-CimInstance Win32_Service -Filter "Name='RandleTerminalAuthority'"
    $binary='C:\Program Files\RandleAI\TerminalAuthority\RandleTerminalAuthority.exe'
    $policy='C:\ProgramData\RandleAI\TerminalAuthority\Config\r7_terminal_authority_policy.json'
    $checkpoint='C:\ProgramData\RandleAI\TerminalAuthority\Ledger\checkpoint.json'
    $trust='C:\ProgramData\RandleAI\TerminalAuthority\Trust\terminal_authority_public.cer'
    $policyJson=ReadJson $policy
    return [ordered]@{account=[string]$cim.StartName;binary_path=[string]$cim.PathName;binary_sha256=(Hash $binary);checkpoint_sha256=(Hash $checkpoint);interface=[string]$policyJson.interface_version;ledger_entry_count=@(Get-ChildItem -LiteralPath 'C:\ProgramData\RandleAI\TerminalAuthority\Ledger' -Filter '*.entry.json' -File).Count;ledger_root='87fdc1bbcef606ad134cf5cd2c0cad83dd4df25ed96544c05fd5adbeff5f82e5';policy_sha256=(Hash $policy);process_id=[long]$cim.ProcessId;service_state=[string]$svc.Status;trust_sha256=(Hash $trust)}
}
function AssertTerminal([object]$value,[long]$expectedPid){if([string]$value.account -cne 'NT SERVICE\RandleTerminalAuthority' -or [string]$value.binary_path -cne 'C:\Program Files\RandleAI\TerminalAuthority\RandleTerminalAuthority.exe' -or [string]$value.binary_sha256 -cne '9ea829416f37c94db2858586fa5e0042652f6caa4637a29fdbefb513577a7526' -or [string]$value.policy_sha256 -cne '76eb2900b2000aa0b41e6040335cc323f7443728aad21cd871d5b6b8e17bcd8b' -or [string]$value.interface -cne '3.0.0-DRAFT' -or [int]$value.ledger_entry_count -ne 678 -or [string]$value.ledger_root -cne '87fdc1bbcef606ad134cf5cd2c0cad83dd4df25ed96544c05fd5adbeff5f82e5' -or [string]$value.checkpoint_sha256 -cne '988f08177b04125e3f92f0696adac8c22b7d24ab0a4cba726145d97ea2958962' -or [string]$value.trust_sha256 -cne 'b84a4de14577580c64ff5b2446f120aa6f9ea60faa2cb5465b495282f0273285' -or [string]$value.service_state -cne 'Running' -or [long]$value.process_id -ne $expectedPid){throw 'Existing terminal state changed'}}

if(-not([Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))){throw 'Elevation required'}
if((Hash $PSCommandPath) -cne $ExpectedScriptSha256){throw 'Unit 2 verification script identity mismatch'}
$registry=ReadJson ([IO.Path]::GetFullPath($UtilityRegistry))
function Utility([string]$role){$rows=@($registry.utilities|Where-Object{$_.role -ceq $role});if($rows.Count -ne 1){throw "Utility role invalid: $role"};if((Hash ([string]$rows[0].path)) -cne [string]$rows[0].measurement.sha256){throw "Utility drift: $role"};return $rows[0]}
$scRow=Utility 'SC_SERVICE_CONTROL_TOOL';$powershellRow=Utility 'POWERSHELL_ORCHESTRATOR';$script:sc=[string]$scRow.path
$currentPowerShell=[Diagnostics.Process]::GetCurrentProcess().MainModule.FileName;if((Hash $currentPowerShell) -cne [string]$powershellRow.measurement.sha256){throw 'PowerShell identity drift'}
$manifest=ReadJson (Join-Path $build 'unit2_build_manifest.json');if([string]$manifest.source_commit -cne $SourceCommit -or [string]$manifest.status -cne 'PASS'){throw 'Build manifest mismatch'}
$preflight=[IO.Path]::GetFullPath($PreflightHostState);$preflightValue=ReadJson $preflight;if([string]$preflightValue.artifact_type -cne 'R7_REMEDIATION_HOST_STATE_CAPTURE' -or [string]$preflightValue.phase -cne 'PRECHANGE'){throw 'Preflight mismatch'}
if(-not(Test-Path -LiteralPath $evidence)){New-Item -ItemType Directory -Path $evidence|Out-Null}
$client=Join-Path $install 'RandleTerminalUpgradeClient.exe'
$verifier=Join-Path $install 'RandleTerminalUpgradePublicVerifier.exe'
$probe=Join-Path $install 'RandleTerminalUpgradeProtocolProbe.exe'
$serviceBinary=Join-Path $install 'RandleTerminalUpgradeAuthority.exe'
$policyPath=Join-Path $state 'Config\upgrade_authority_policy.json'
$policy=ReadJson $policyPath
$terminalBefore=TerminalSnapshot;$terminalPid=[long]$terminalBefore.process_id;AssertTerminal $terminalBefore $terminalPid
if([string](Get-Service -Name $service).Status -cne 'Running'){throw 'Upgrade authority must begin running'}

$healthBeforePath=Join-Path $evidence 'health-before-authorization.json';RunRole $client @('health',$healthBeforePath) @(0)|Out-Null
$identityPath=Join-Path $evidence 'public-identity.json';RunRole $client @('identity',$identityPath) @(0)|Out-Null
$boundaryPath=Join-Path $evidence 'service-boundary-measurement.json';RunRole $verifier @('measure-boundary',$boundaryPath) @(0)|Out-Null
$provisionedPath=Join-Path $evidence 'public-provisioned-verification.json';RunRole $verifier @('provisioned',$provisionedPath) @(0)|Out-Null
$interactiveKeyPath=Join-Path $evidence 'interactive-key-open-denied.json';RunRole $verifier @('key-open-denied',$interactiveKeyPath) @(0)|Out-Null
$parserPath=Join-Path $evidence 'live-ipc-integrity.json';RunRole $probe @('parser-suite',$parserPath) @(0)|Out-Null

$copiedRoot=Join-Path $evidence 'copied-executables';New-Item -ItemType Directory -Path $copiedRoot -ErrorAction Stop|Out-Null
$copiedClient=Join-Path $copiedRoot 'RandleTerminalUpgradeClient.exe';Copy-Item -LiteralPath $client -Destination $copiedClient
$copiedResult=RunRejectedRole $copiedClient @('authorize',(Join-Path $copiedRoot 'unexpected.json'))
$copiedService=Join-Path $copiedRoot 'RandleTerminalUpgradeAuthority.exe';Copy-Item -LiteralPath $serviceBinary -Destination $copiedService
$copiedServiceResult=RunRejectedRole $copiedService @()
WriteJsonNew ([ordered]@{artifact_type='R7_UNIT2_COPIED_EXECUTABLE_REJECTION';authority_effect=$false;copied_client_binary_sha256=(Hash $copiedClient);copied_client_exit_code=$copiedResult.exit_code;copied_client_output=$copiedResult.output;copied_service_binary_sha256=(Hash $copiedService);copied_service_exit_code=$copiedServiceResult.exit_code;copied_service_output=$copiedServiceResult.output;schema_version='1.0.0';status='PASS'}) (Join-Path $evidence 'copied-executable-rejection.json')|Out-Null

$activationRoot=Join-Path $state 'Activations';$marker=Join-Path $activationRoot 'simulated-install-marker.unit2-test';if(Test-Path -LiteralPath $marker){throw 'Simulated installation marker already exists'};[IO.File]::WriteAllText($marker,'UNIT2_SIMULATED_INSTALL_MARKER_NO_TERMINAL_INSTALLATION',[Text.UTF8Encoding]::new($false))
$markerRejectPath=Join-Path $evidence 'authorization-after-simulated-install-marker.json';RunRole $client @('authorize',$markerRejectPath) @(2)|Out-Null
$markerReject=ReadJson $markerRejectPath;if([string]$markerReject.response.error_code -cne 'TERMINAL_INSTALLATION_MARKER_PRESENT' -or [bool]$markerReject.response.authority_effect -ne $false){throw 'Installation-marker authorization did not fail closed'}
$preservedMarker=Join-Path (Join-Path $state 'Evidence') 'simulated-install-marker.rejected-evidence';if(Test-Path -LiteralPath $preservedMarker){throw 'Preserved marker target exists'};Move-Item -LiteralPath $marker -Destination $preservedMarker

$concurrent1=Join-Path $evidence 'authorization-concurrent-1.json';$concurrent2=Join-Path $evidence 'authorization-concurrent-2.json'
$stdout1=Join-Path $evidence 'authorization-concurrent-1.stdout.txt';$stderr1=Join-Path $evidence 'authorization-concurrent-1.stderr.txt';$stdout2=Join-Path $evidence 'authorization-concurrent-2.stdout.txt';$stderr2=Join-Path $evidence 'authorization-concurrent-2.stderr.txt'
$p1=Start-Process -FilePath $client -ArgumentList @('authorize',$concurrent1) -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout1 -RedirectStandardError $stderr1
$p2=Start-Process -FilePath $client -ArgumentList @('authorize',$concurrent2) -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout2 -RedirectStandardError $stderr2
$p1.WaitForExit();$p2.WaitForExit();if($p1.ExitCode -ne 0 -or $p2.ExitCode -ne 0){throw "Concurrent authorization failed: $($p1.ExitCode),$($p2.ExitCode)"}
$a1=ReadJson $concurrent1;$a2=ReadJson $concurrent2;if([string]$a1.response.authorization_identity -cne [string]$a2.response.authorization_identity -or [string]$a1.response.request_identity -cne [string]$a2.response.request_identity){throw 'Concurrent duplicate did not resolve identically'}
$healthCommittedPath=Join-Path $evidence 'health-after-authorization.json';RunRole $client @('health',$healthCommittedPath) @(0)|Out-Null;$healthCommitted=ReadJson $healthCommittedPath
$sequenceCommitted=[int64]$healthCommitted.response.ledger_sequence;$rootCommitted=[string]$healthCommitted.response.ledger_root
$replayPath=Join-Path $evidence 'authorization-idempotent-replay.json';RunRole $client @('authorize',$replayPath) @(0)|Out-Null
$healthReplayPath=Join-Path $evidence 'health-after-idempotent-replay.json';RunRole $client @('health',$healthReplayPath) @(0)|Out-Null;$healthReplay=ReadJson $healthReplayPath
if([int64]$healthReplay.response.ledger_sequence -ne $sequenceCommitted -or [string]$healthReplay.response.ledger_root -cne $rootCommitted){throw 'Idempotent replay created an authority effect'}
$getPath=Join-Path $evidence 'authorization-retrieval.json';RunRole $client @('get',$getPath) @(0)|Out-Null
$authorizedRunningPath=Join-Path $evidence 'public-authorized-running-verification.json';RunRole $verifier @('authorized',$authorizedRunningPath) @(0)|Out-Null;$authorizedRunning=ReadJson $authorizedRunningPath

RunSc @('stop',$service);WaitService 'Stopped';AssertTerminal (TerminalSnapshot) $terminalPid
$authorizedStoppedPath=Join-Path $evidence 'public-authorized-stopped-verification.json';RunRole $verifier @('authorized',$authorizedStoppedPath) @(0)|Out-Null
$attackOutput=Join-Path $evidence 'public-copy-mutation-attacks.json';RunRole $verifier @('attack-copies',$attack,$attackOutput) @(0)|Out-Null
$stoppedClient=RunRole $client @('health',(Join-Path $evidence 'stopped-client-unexpected.json')) @(1)
WriteJsonNew ([ordered]@{artifact_type='R7_UNIT2_STOPPED_SERVICE_FAIL_CLOSED';authority_effect=$false;client_exit_code=$stoppedClient.exit_code;client_output=$stoppedClient.output;schema_version='1.0.0';status='PASS'}) (Join-Path $evidence 'stopped-service-client-fail-closed.json')|Out-Null

RunSc @('start',$service);WaitService 'Running';AssertTerminal (TerminalSnapshot) $terminalPid
$healthRestartPath=Join-Path $evidence 'health-after-restart.json';RunRole $client @('health',$healthRestartPath) @(0)|Out-Null;$healthRestart=ReadJson $healthRestartPath
if([int64]$healthRestart.response.ledger_sequence -ne ($sequenceCommitted+1)){throw 'Restart continuity sequence mismatch'}
$authorizedRestartPath=Join-Path $evidence 'public-authorized-after-restart-verification.json';RunRole $verifier @('authorized',$authorizedRestartPath) @(0)|Out-Null;$authorizedRestart=ReadJson $authorizedRestartPath

$scEvidence=[Collections.Generic.List[object]]::new();foreach($query in @(@('qc',$service),@('qsidtype',$service),@('qprivs',$service),@('sdshow',$service),@('queryex',$service))){$captured=@(& $script:sc @query 2>&1);$exit=$LASTEXITCODE;if($exit -ne 0){throw "Service query failed: $($query -join ' ')"};$scEvidence.Add([ordered]@{arguments=$query;output=$captured;output_sha256=(TextHash ($captured -join "`r`n"))})}
$keyPath=Join-Path 'C:\ProgramData\Microsoft\Crypto\Keys' ([string]$policy.key.key_unique_name)
$aclPaths=@($install,$state,(Join-Path $state 'Config'),(Join-Path $state 'Ledger'),(Join-Path $state 'Trust'),(Join-Path $state 'Evidence'),(Join-Path $state 'Responses'),$keyPath)
$aclEvidence=@(foreach($path in $aclPaths){$acl=Get-Acl -LiteralPath $path;$sddl=$acl.Sddl;[ordered]@{owner=$acl.Owner;path=$path;sddl=$sddl;sddl_sha256=(TextHash $sddl)}})
$keySddl=[string](@($aclEvidence|Where-Object path -ceq $keyPath)[0].sddl);if($keySddl.Contains($terminalSid) -or $keySddl.Contains($operatorSid) -or $keySddl.Contains(';;;BU') -or $keySddl.Contains(';;;BA')){throw 'Upgrade private-key ACL grants a prohibited principal'}
$cert=New-Object Security.Cryptography.X509Certificates.X509Certificate2((Join-Path $state 'Trust\upgrade_authority_public.cer'))
$terminalAfter=TerminalSnapshot;AssertTerminal $terminalAfter $terminalPid
$summary=[ordered]@{
    artifact_type='R7_UNIT2_LIVE_VERIFICATION_SUMMARY';acl_evidence=$aclEvidence;authorization_identity=[string]$authorizedRestart.authorization_identity;
    build_manifest_sha256=(Hash (Join-Path $build 'unit2_build_manifest.json'));checkpoint_after_restart=[string]$authorizedRestart.checkpoint_sha256;
    copied_executable_rejected=$true;existing_terminal_after=$terminalAfter;existing_terminal_before=$terminalBefore;existing_terminal_changed=$false;
    final_ledger_root=[string]$authorizedRestart.ledger_root;final_ledger_sequence=[int64]$authorizedRestart.ledger_sequence;interface_version=[string]$policy.interface_version;
    key_acl_cross_service_denial=$true;key_algorithm='RSA-3072';key_nonexportability_verified=$true;key_provider='Microsoft Software Key Storage Provider';
    operation_allowlist=$policy.operation_allowlist;preflight_baseline_sha256=(Hash $preflight);principal_isolation_verified=$true;private_key_exported=$false;
    protocol_probe_sha256=(Hash $parserPath);public_certificate_sha256=(Hash (Join-Path $state 'Trust\upgrade_authority_public.cer'));public_certificate_thumbprint=$cert.Thumbprint.ToLowerInvariant();
    public_stopped_service_verification_sha256=(Hash $authorizedStoppedPath);restart_sequence_delta=1;schema_version='1.0.0';service_control_evidence=$scEvidence.ToArray();
    service_name=$service;service_sid=$upgradeSid;source_commit=$SourceCommit;status='PASS';terminal_installation_performed=$false;transition_disposition='AUTHORIZED FOR FUTURE INSTALLATION CONSIDERATION'
}
$cert.Dispose();$summaryPath=WriteJsonNew $summary (Join-Path $evidence 'unit2_live_verification_summary.json')
[ordered]@{authorization_identity=$summary.authorization_identity;evidence_root=$evidence;final_ledger_root=$summary.final_ledger_root;final_ledger_sequence=$summary.final_ledger_sequence;summary_sha256=(Hash $summaryPath);status='PASS'}|ConvertTo-Json
