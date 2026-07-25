[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$SourceCommit,
    [Parameter(Mandatory=$true)][string]$BuildRoot,
    [Parameter(Mandatory=$true)][string]$BootstrapRecord,
    [Parameter(Mandatory=$true)][string]$PreflightHostState,
    [Parameter(Mandatory=$true)][string]$UtilityRegistry,
    [Parameter(Mandatory=$true)][string]$EvidenceRoot,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedBuildManifestSha256,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedScriptSha256,
    [Parameter(Mandatory=$true)][switch]$PreStartOnly
)

$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$service='RandleTerminalUpgradeAuthority'
$account='NT SERVICE\RandleTerminalUpgradeAuthority'
$terminalAccount='NT SERVICE\RandleTerminalAuthority'
$sid='S-1-5-80-238545627-4117296865-2677355104-248304369-1301198082'
$terminalSid='S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948'
$install='C:\Program Files\RandleAI\TerminalUpgradeAuthority'
$state='C:\ProgramData\RandleAI\TerminalUpgradeAuthority'
$config=Join-Path $state 'Config'
$trust=Join-Path $state 'Trust'
$evidenceParent=Join-Path $state 'Evidence'
$build=[IO.Path]::GetFullPath($BuildRoot)
$evidence=[IO.Path]::GetFullPath($EvidenceRoot)
$expectedBinary=Join-Path $install 'RandleTerminalUpgradeAuthority.exe'
$artifactTool=Join-Path $build 'Tools\R7ArtifactTool.exe'
$createdFiles=[Collections.Generic.List[string]]::new()
$createdEvidenceParent=$false
$rightsMeasurement=$null
$failureActionsChanged=$false
$mutations=[Collections.Generic.List[object]]::new()

function Hash([string]$Path){(Get-FileHash -LiteralPath ([IO.Path]::GetFullPath($Path)) -Algorithm SHA256).Hash.ToLowerInvariant()}
function ReadJson([string]$Path){Get-Content -LiteralPath ([IO.Path]::GetFullPath($Path)) -Raw|ConvertFrom-Json}
function IsAdministrator{return [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)}
function AssertStopped {
    $svc=Get-Service -Name $service -ErrorAction Stop
    $cim=Get-CimInstance Win32_Service -Filter "Name='$service'"
    if($svc.Status -ne 'Stopped' -or [long]$cim.ProcessId -ne 0){throw 'Upgrade service must remain stopped with PID 0'}
}
function Run([string]$Executable,[string[]]$Arguments){
    $output=@(& $Executable @Arguments 2>&1|ForEach-Object{[string]$_})
    $exit=$LASTEXITCODE
    if($exit -ne 0){throw "$Executable exited $exit | $($Arguments -join ' ') | $($output -join ' | ')"}
    return [ordered]@{arguments=@($Arguments);exit_code=$exit;output=@($output)}
}
function RunScMutation([string[]]$Arguments,[string]$Operation){
    AssertStopped
    $result=Run $script:sc $Arguments
    $mutations.Add([ordered]@{operation=$Operation;result=$result;service_stopped_before=$true})
    AssertStopped
    return $result
}
function NewDirectory([string]$Path){
    AssertStopped
    if(Test-Path -LiteralPath $Path){throw "Directory already exists: $Path"}
    New-Item -ItemType Directory -Path $Path|Out-Null
    AssertStopped
}
function CopyNew([string]$Source,[string]$Destination){
    AssertStopped
    if(Test-Path -LiteralPath $Destination){throw "Install target exists: $Destination"}
    Copy-Item -LiteralPath $Source -Destination $Destination
    $script:createdFiles.Add([IO.Path]::GetFullPath($Destination))
    $script:mutations.Add([ordered]@{destination=[IO.Path]::GetFullPath($Destination);operation='COPY_NEW';source=[IO.Path]::GetFullPath($Source);source_sha256=(Hash $Source)})
    AssertStopped
}
function TerminalSnapshot {
    $svc=Get-Service -Name 'RandleTerminalAuthority' -ErrorAction Stop
    $cim=Get-CimInstance Win32_Service -Filter "Name='RandleTerminalAuthority'"
    $binary='C:\Program Files\RandleAI\TerminalAuthority\RandleTerminalAuthority.exe'
    $policy='C:\ProgramData\RandleAI\TerminalAuthority\Config\r7_terminal_authority_policy.json'
    $checkpoint='C:\ProgramData\RandleAI\TerminalAuthority\Ledger\checkpoint.json'
    $trustPath='C:\ProgramData\RandleAI\TerminalAuthority\Trust\terminal_authority_public.cer'
    $policyJson=ReadJson $policy
    return [ordered]@{account=[string]$cim.StartName;binary_path=[string]$cim.PathName;binary_sha256=(Hash $binary);checkpoint_sha256=(Hash $checkpoint);interface=[string]$policyJson.interface_version;ledger_entry_count=@(Get-ChildItem -LiteralPath 'C:\ProgramData\RandleAI\TerminalAuthority\Ledger' -Filter '*.entry.json' -File).Count;ledger_id='899e4db2b5c0f4ad58a09c682324a2ee9e5d7e2f180822ce9300922e56741d52';ledger_root='87fdc1bbcef606ad134cf5cd2c0cad83dd4df25ed96544c05fd5adbeff5f82e5';policy_sha256=(Hash $policy);process_id=[long]$cim.ProcessId;service_state=[string]$svc.Status;trust_sha256=(Hash $trustPath)}
}
function AssertTerminalSnapshot([object]$Value){
    if([string]$Value.account -cne 'NT SERVICE\RandleTerminalAuthority' -or [string]$Value.binary_path -cne 'C:\Program Files\RandleAI\TerminalAuthority\RandleTerminalAuthority.exe' -or [string]$Value.binary_sha256 -cne '9ea829416f37c94db2858586fa5e0042652f6caa4637a29fdbefb513577a7526' -or [string]$Value.policy_sha256 -cne '76eb2900b2000aa0b41e6040335cc323f7443728aad21cd871d5b6b8e17bcd8b' -or [string]$Value.interface -cne '3.0.0-DRAFT' -or [int64]$Value.ledger_entry_count -ne 678 -or [string]$Value.checkpoint_sha256 -cne '988f08177b04125e3f92f0696adac8c22b7d24ab0a4cba726145d97ea2958962' -or [string]$Value.trust_sha256 -cne 'b84a4de14577580c64ff5b2446f120aa6f9ea60faa2cb5465b495282f0273285' -or [string]$Value.service_state -cne 'Running'){throw 'Existing terminal baseline drift'}
}
function RootAcl([string]$Path){$acl=Get-Acl -LiteralPath $Path;return [ordered]@{owner=[string]$acl.Owner;path=[IO.Path]::GetFullPath($Path);sddl=[string]$acl.Sddl}}
function AssertBootstrapRootAcl([object]$Bootstrap,[string]$Path){
    $rows=@($Bootstrap.root_acl_evidence|Where-Object{[string]$_.path -ceq [IO.Path]::GetFullPath($Path)})
    if($rows.Count -ne 1){throw "Bootstrap root ACL evidence absent: $Path"}
    $actual=RootAcl $Path
    if([string]$actual.owner -cne [string]$rows[0].owner -or [string]$actual.sddl -cne [string]$rows[0].sddl){throw "Bootstrap root ACL drift: $Path"}
}
function AssertNoAuthorityArtifacts {
    foreach($root in @((Join-Path $state 'Ledger'),(Join-Path $state 'Authorizations'),(Join-Path $state 'Responses'),(Join-Path $state 'Objects'),(Join-Path $state 'Recovery'),(Join-Path $state 'Activations'))){
        if((Test-Path -LiteralPath $root) -and @(Get-ChildItem -LiteralPath $root -Force -Recurse -File).Count -ne 0){throw "Forbidden authority artifact exists: $root"}
    }
}
function WriteFailure([object]$Failure){
    try{
        if(Test-Path -LiteralPath $evidence -PathType Container){
            AssertStopped
            [IO.File]::WriteAllText((Join-Path $evidence 'unit2b_failure.json'),($Failure|ConvertTo-Json -Depth 30),[Text.UTF8Encoding]::new($false))
        }
    }catch{}
}

if(-not $PreStartOnly){throw 'Only the explicit PreStartOnly path is exposed by this committed Unit 2B installer'}
if(-not(IsAdministrator)){throw 'Elevation required'}
if((Hash $PSCommandPath) -cne $ExpectedScriptSha256){throw 'Unit 2B installer script identity mismatch'}
$manifestPath=Join-Path $build 'unit2_build_manifest.json'
if((Hash $manifestPath) -cne $ExpectedBuildManifestSha256){throw 'Unit 2B build manifest identity mismatch'}
$manifest=ReadJson $manifestPath
if([string]$manifest.source_commit -cne $SourceCommit -or [string]$manifest.status -cne 'PASS'){throw 'Build manifest source binding invalid'}
$utility=ReadJson $UtilityRegistry
function Utility([string]$Role){$rows=@($utility.utilities|Where-Object{$_.role -ceq $Role});if($rows.Count -ne 1){throw "Utility role invalid: $Role"};$path=[IO.Path]::GetFullPath([string]$rows[0].path);if((Hash $path) -cne [string]$rows[0].measurement.sha256){throw "Utility drift: $Role"};return $rows[0]}
$scRow=Utility 'SC_SERVICE_CONTROL_TOOL'
$icaclsRow=Utility 'ICACLS_ACL_TOOL'
$powershellRow=Utility 'POWERSHELL_ORCHESTRATOR'
$sc=[string]$scRow.path
$icacls=[string]$icaclsRow.path
$currentPowerShell=[Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
if(-not([IO.Path]::GetFullPath($currentPowerShell).Equals([IO.Path]::GetFullPath([string]$powershellRow.path),[StringComparison]::OrdinalIgnoreCase)) -or (Hash $currentPowerShell) -cne [string]$powershellRow.measurement.sha256){throw 'PowerShell orchestrator identity mismatch'}
if(-not(Test-Path -LiteralPath $artifactTool -PathType Leaf)){throw 'Measured boundary tool absent'}
$artifactRow=@($manifest.files|Where-Object{[string]$_.path -ceq 'Tools/R7ArtifactTool.exe'})
if($artifactRow.Count -ne 1 -or (Hash $artifactTool) -cne [string]$artifactRow[0].raw_sha256){throw 'Measured boundary tool manifest mismatch'}
$preflightPath=[IO.Path]::GetFullPath($PreflightHostState)
$preflight=ReadJson $preflightPath
$preflightSha=Hash $preflightPath
if([string]$preflight.artifact_type -cne 'R7_REMEDIATION_HOST_STATE_CAPTURE' -or [string]$preflight.phase -cne 'PRECHANGE' -or [int64]$preflight.ledger_entry_file_count -ne 678 -or [string]$preflight.checkpoint.raw_sha256 -cne '988f08177b04125e3f92f0696adac8c22b7d24ab0a4cba726145d97ea2958962'){throw 'Preflight host-state identity invalid'}
$bootstrap=ReadJson $BootstrapRecord
if([string]$bootstrap.service_sid -cne $sid -or [string]$bootstrap.key_unique_name -cne 'c3bb9b44730bef59a70100a6b23fffb9_c5338977-c52f-4ca7-af6f-db9b5e287cca' -or [string]$bootstrap.public_certificate_sha256 -cne '2ef057a2c09d53da7096d92a09774b68986cf26c5d44000e1ec804d8ce837d7b'){throw 'Bootstrap identity mismatch'}
AssertStopped
$terminalBefore=TerminalSnapshot
AssertTerminalSnapshot $terminalBefore
AssertNoAuthorityArtifacts
foreach($requiredRoot in @($install,$config,$trust)){if(-not(Test-Path -LiteralPath $requiredRoot -PathType Container)){throw "Preserved root absent: $requiredRoot"};AssertBootstrapRootAcl $bootstrap $requiredRoot}
if(@(Get-ChildItem -LiteralPath $install -Force).Count -ne 0){throw 'Upgrade installation root is not empty'}
if(@(Get-ChildItem -LiteralPath $config -Force).Count -ne 0){throw 'Upgrade configuration root is not empty'}
if(Test-Path -LiteralPath $evidenceParent){throw 'Unit 2B evidence parent must not exist before installation'}
$certTarget=Join-Path $trust 'upgrade_authority_public.cer'
if((Hash $certTarget) -cne [string]$bootstrap.public_certificate_sha256){throw 'Preserved public certificate bytes drifted'}
$certificateAcl=Get-Acl -LiteralPath $certTarget
if([string]$certificateAcl.Sddl -cne [string]$bootstrap.public_certificate_file_acl_sddl){throw 'Preserved public certificate ACL drifted'}

try{
    NewDirectory $evidenceParent
    $createdEvidenceParent=$true
    NewDirectory $evidence
    $baselineRecord=[ordered]@{artifact_type='R7_UNIT2B_PRESTART_INSTALL_BASELINE';bootstrap_record_sha256=(Hash $BootstrapRecord);existing_terminal=$terminalBefore;preflight_host_state_sha256=$preflightSha;schema_version='1.0.0';service_state='STOPPED';source_commit=$SourceCommit;upgrade_service_pid=0}
    AssertStopped
    [IO.File]::WriteAllText((Join-Path $evidence 'preinstall_baseline.json'),($baselineRecord|ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))

    RunScMutation @('config',$service,'binPath=',$expectedBinary,'start=','demand','obj=',$account) 'SCM_CONFIG_FIXED_BINARY_ACCOUNT_MANUAL'|Out-Null
    RunScMutation @('sidtype',$service,'restricted') 'SCM_SID_TYPE_RESTRICTED'|Out-Null
    RunScMutation @('privs',$service,'SeChangeNotifyPrivilege') 'SCM_REQUIRED_PRIVILEGES_MINIMAL'|Out-Null
    RunScMutation @('failure',$service,'reset=','0','actions=','') 'SCM_FAILURE_ACTIONS_CLEARED'|Out-Null
    $failureActionsChanged=$true
    RunScMutation @('failureflag',$service,'0') 'SCM_NONCRASH_FAILURE_ACTIONS_DISABLED'|Out-Null

    $installInput=Join-Path $build 'Install'
    $installMap=@(
        [ordered]@{source=(Join-Path $installInput 'RandleTerminalUpgradeAuthority.exe');destination=(Join-Path $install 'RandleTerminalUpgradeAuthority.exe')},
        [ordered]@{source=(Join-Path $installInput 'RandleTerminalUpgradeClient.exe');destination=(Join-Path $install 'RandleTerminalUpgradeClient.exe')},
        [ordered]@{source=(Join-Path $installInput 'RandleTerminalUpgradePublicVerifier.exe');destination=(Join-Path $install 'RandleTerminalUpgradePublicVerifier.exe')},
        [ordered]@{source=(Join-Path $installInput 'unit2_upgrade_policy.json');destination=(Join-Path $config 'upgrade_authority_policy.json')},
        [ordered]@{source=(Join-Path $installInput 'dependency_manifest.json');destination=(Join-Path $config 'dependency_manifest.json')},
        [ordered]@{source=(Join-Path $installInput 'unit2_build_receipt.json');destination=(Join-Path $config 'upgrade_authority_build_receipt.json')}
    )
    foreach($item in $installMap){CopyNew ([string]$item.source) ([string]$item.destination)}
    if((Hash (Join-Path $installInput 'upgrade_authority_public.cer')) -cne (Hash $certTarget)){throw 'Build public certificate differs from preserved public trust'}

    foreach($root in @($install,$config,$trust)){
        AssertStopped
        $ownerResult=Run $icacls @($root,'/setowner','SYSTEM','/T','/C')
        $aclResult=Run $icacls @($root,'/inheritance:r','/grant:r','SYSTEM:(OI)(CI)(F)','BUILTIN\Administrators:(OI)(CI)(F)',"$account`:(OI)(CI)(RX)","$terminalAccount`:(OI)(CI)(RX)",'BUILTIN\Users:(OI)(CI)(RX)','/T','/C')
        $mutations.Add([ordered]@{acl_result=$aclResult;operation='ACL_FIXED_READ_ONLY_AUTHORITY_INPUT_ROOT';owner_result=$ownerResult;root=$root;service_stopped_before=$true})
        AssertStopped
    }
    AssertStopped
    $evidenceOwner=Run $icacls @($evidenceParent,'/setowner','SYSTEM','/T','/C')
    $evidenceAcl=Run $icacls @($evidenceParent,'/inheritance:r','/grant:r','SYSTEM:(OI)(CI)(F)','BUILTIN\Administrators:(OI)(CI)(F)',"$account`:(OI)(CI)(F)","$terminalAccount`:(OI)(CI)(RX)",'BUILTIN\Users:(OI)(CI)(RX)','/T','/C')
    $mutations.Add([ordered]@{acl_result=$evidenceAcl;operation='ACL_FIXED_EVIDENCE_ROOT';owner_result=$evidenceOwner;root=$evidenceParent;service_stopped_before=$true})
    AssertStopped

    $rightsMeasurement=Join-Path $evidence 'service_boundary_rights.json'
    AssertStopped
    Run $artifactTool @('service-boundary',$service,$sid,$expectedBinary,$rightsMeasurement)|Out-Null
    $mutations.Add([ordered]@{measurement=$rightsMeasurement;operation='LSA_DENY_RIGHTS_ENFORCE_AND_MEASURE';service_stopped_before=$true})
    AssertStopped

    $physical=[Collections.Generic.List[object]]::new()
    foreach($item in $installMap){
        $name=[IO.Path]::GetFileName([string]$item.destination)
        $contentPath=Join-Path $evidence ('physical_content_'+$name+'.json')
        $metadataPath=Join-Path $evidence ('physical_metadata_'+$name+'.json')
        AssertStopped;Run $artifactTool @('measure',[string]$item.destination,$contentPath)|Out-Null
        AssertStopped;Run $artifactTool @('measure-metadata',[string]$item.destination,$metadataPath)|Out-Null
        $physical.Add([ordered]@{content_measurement=$contentPath;metadata_measurement=$metadataPath;path=[string]$item.destination;sha256=(Hash ([string]$item.destination))})
    }
    $certContent=Join-Path $evidence 'physical_content_upgrade_authority_public.cer.json'
    $certMetadata=Join-Path $evidence 'physical_metadata_upgrade_authority_public.cer.json'
    AssertStopped;Run $artifactTool @('measure',$certTarget,$certContent)|Out-Null
    AssertStopped;Run $artifactTool @('measure-metadata',$certTarget,$certMetadata)|Out-Null
    $physical.Add([ordered]@{content_measurement=$certContent;metadata_measurement=$certMetadata;path=$certTarget;sha256=(Hash $certTarget)})

    $expectedInstallNames=@('RandleTerminalUpgradeAuthority.exe','RandleTerminalUpgradeClient.exe','RandleTerminalUpgradePublicVerifier.exe')
    $actualInstallNames=@(Get-ChildItem -LiteralPath $install -Force -File|ForEach-Object Name|Sort-Object)
    if((@($expectedInstallNames|Sort-Object)-join "`n") -cne ($actualInstallNames-join "`n")){throw 'Installed executable set is not exact'}
    $expectedConfigNames=@('dependency_manifest.json','upgrade_authority_build_receipt.json','upgrade_authority_policy.json')
    $actualConfigNames=@(Get-ChildItem -LiteralPath $config -Force -File|ForEach-Object Name|Sort-Object)
    if((@($expectedConfigNames|Sort-Object)-join "`n") -cne ($actualConfigNames-join "`n")){throw 'Installed configuration set is not exact'}
    if(@(Get-ChildItem -LiteralPath $trust -Force -File).Count -ne 1){throw 'Public trust file set is not exact'}

    $policy=ReadJson (Join-Path $config 'upgrade_authority_policy.json')
    if(([string[]]@($policy.operation_allowlist)-join "`n") -cne (@('AUTHORIZE_TERMINAL_TRANSITION','GET_AUTHORIZATION','GET_HEALTH','GET_PUBLIC_IDENTITY')-join "`n") -or [string]$policy.service.name -cne $service -or [string]$policy.service.account -cne $account -or [string]$policy.service.sid -cne $sid -or [string]$policy.provisioning_script_sha256 -cne $ExpectedScriptSha256 -or [string]$policy.key.key_unique_name -cne [string]$bootstrap.key_unique_name){throw 'Installed policy fixed-boundary validation failed'}

    $qc=Run $sc @('qc',$service)
    $sidType=Run $sc @('qsidtype',$service)
    $privileges=Run $sc @('qprivs',$service)
    $failure=Run $sc @('qfailure',$service)
    $failureFlag=Run $sc @('qfailureflag',$service)
    $query=Run $sc @('queryex',$service)
    $qcText=$qc.output -join "`n";$sidText=$sidType.output -join "`n";$privText=$privileges.output -join "`n";$failureText=$failure.output -join "`n";$failureFlagText=$failureFlag.output -join "`n";$queryText=$query.output -join "`n"
    if($qcText -notmatch [regex]::Escape($expectedBinary) -or $qcText -notmatch 'DEMAND_START' -or $qcText -notmatch [regex]::Escape($account) -or $sidText -notmatch 'RESTRICTED' -or $privText -notmatch 'SeChangeNotifyPrivilege' -or $privText -match 'SeImpersonatePrivilege' -or $failureText -match 'RESTART|RUN COMMAND|REBOOT' -or $failureFlagText -notmatch 'FALSE' -or $queryText -notmatch 'STATE\s+: 1\s+STOPPED' -or $queryText -notmatch 'PID\s+: 0'){throw 'Stopped SCM boundary verification failed'}

    $terminalServiceDacl=Run $sc @('sdshow','RandleTerminalAuthority')
    if(($terminalServiceDacl.output -join '') -match [regex]::Escape($sid)){throw 'Upgrade SID unexpectedly appears in terminal service DACL'}
    $repositoryAcl=RootAcl 'C:\Users\Trader\AppData\Local\Temp\randle_r7_arch_remediation_20260724_9d813a4'
    $terminalBoundaryAcls=@('C:\Program Files\RandleAI\TerminalAuthority','C:\ProgramData\RandleAI\TerminalAuthority')|ForEach-Object{RootAcl $_}
    foreach($acl in @($repositoryAcl)+@($terminalBoundaryAcls)){if([string]$acl.sddl -match ('\(A;[^\)]*(?:0x1301bf|0x1201bf|FA|FW|WD|DC|WA|WO)[^\)]*;;;'+[regex]::Escape($sid)+'\)')){throw "Upgrade SID has writable boundary ACE: $([string]$acl.path)"}}

    AssertNoAuthorityArtifacts
    $terminalAfter=TerminalSnapshot
    AssertTerminalSnapshot $terminalAfter
    if([long]$terminalBefore.process_id -ne [long]$terminalAfter.process_id){throw 'Existing terminal service process changed'}
    AssertStopped
    $record=[ordered]@{artifact_type='R7_UNIT2B_STOPPED_BOUNDARY_INSTALLATION_RECORD';build_manifest_sha256=$ExpectedBuildManifestSha256;existing_terminal_after=$terminalAfter;existing_terminal_before=$terminalBefore;failure_actions_disabled=$true;installed_files=@($physical);key_opened_for_signing=$false;ledger_created=$false;mutations=$mutations.ToArray();preflight_baseline_sha256=$preflightSha;private_key_exported=$false;provisioning_attestation_issued=$false;public_certificate_retained_sha256=(Hash $certTarget);repository_acl=$repositoryAcl;schema_version='1.0.0';service_name=$service;service_pid=0;service_started=$false;service_state='STOPPED';source_commit=$SourceCommit;status='PASS';terminal_boundary_acls=$terminalBoundaryAcls;terminal_transition_authorized=$false;utilities=@([ordered]@{role=[string]$scRow.role;sha256=[string]$scRow.measurement.sha256},[ordered]@{role=[string]$icaclsRow.role;sha256=[string]$icaclsRow.measurement.sha256},[ordered]@{role=[string]$powershellRow.role;sha256=[string]$powershellRow.measurement.sha256})}
    $rawRecord=Join-Path $evidence 'unit2b_installation_record.raw.json'
    $recordPath=Join-Path $evidence 'unit2b_installation_record.json'
    AssertStopped
    [IO.File]::WriteAllText($rawRecord,($record|ConvertTo-Json -Depth 40),[Text.UTF8Encoding]::new($false))
    AssertStopped
    Run $artifactTool @('canonicalize',$rawRecord,$recordPath)|Out-Null
    AssertStopped
    [ordered]@{evidence_root=$evidence;record_sha256=(Hash $recordPath);service_started=$false;status='PASS';terminal_transition_authorized=$false}|ConvertTo-Json
}
catch{
    $failure=[ordered]@{artifact_type='R7_UNIT2B_INSTALLATION_FAILURE';error=$_.Exception.GetType().FullName+'|'+$_.Exception.Message;rollback_attempted=$true;schema_version='1.0.0';service_started=$false;terminal_transition_authorized=$false}
    $rollbackErrors=[Collections.Generic.List[string]]::new()
    try{AssertStopped}catch{$rollbackErrors.Add($_.Exception.Message)}
    if($rightsMeasurement -and (Test-Path -LiteralPath $rightsMeasurement -PathType Leaf)){
        try{AssertStopped;$restorePath=Join-Path $evidence 'service_boundary_rights_restoration.json';Run $artifactTool @('restore-service-boundary',$rightsMeasurement,$restorePath)|Out-Null}catch{$rollbackErrors.Add($_.Exception.Message)}
    }
    if($failureActionsChanged){try{RunScMutation @('failure',$service,'reset=','86400','actions=','restart/5000') 'ROLLBACK_SCM_FAILURE_ACTIONS'|Out-Null}catch{$rollbackErrors.Add($_.Exception.Message)}}
    foreach($path in @($createdFiles.ToArray()|Sort-Object -Descending)){
        try{AssertStopped;$resolved=[IO.Path]::GetFullPath($path);if(-not($resolved.StartsWith($install+'\',[StringComparison]::OrdinalIgnoreCase) -or $resolved.StartsWith($config+'\',[StringComparison]::OrdinalIgnoreCase))){throw "Rollback path escaped Unit 2B roots: $resolved"};if(Test-Path -LiteralPath $resolved -PathType Leaf){Remove-Item -LiteralPath $resolved -Force}}catch{$rollbackErrors.Add($_.Exception.Message)}
    }
    $failure['rollback_errors']=$rollbackErrors.ToArray()
    $failure['rollback_complete']=($rollbackErrors.Count -eq 0)
    WriteFailure $failure
    throw ('UNIT2B_INSTALLATION_FAILED_AND_ROLLBACK_'+($(if($rollbackErrors.Count -eq 0){'COMPLETE'}else{'INCOMPLETE'}))+'|'+$failure.error)
}
