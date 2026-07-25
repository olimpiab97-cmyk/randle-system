[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$SourceCommit,
    [Parameter(Mandatory=$true)][string]$BuildRoot,
    [Parameter(Mandatory=$true)][string]$BootstrapRecord,
    [Parameter(Mandatory=$true)][string]$PreflightHostState,
    [Parameter(Mandatory=$true)][string]$UtilityRegistry,
    [Parameter(Mandatory=$true)][string]$EvidenceRoot,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedBuildManifestSha256,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedPackageManifestSha256,
    [Parameter(Mandatory=$true)][ValidateRange(1,[long]::MaxValue)][long]$ExpectedPackageManifestSize,
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
$buildTools=Join-Path $state 'BuildTools'
$evidenceParent=Join-Path $state 'Evidence'
$build=[IO.Path]::GetFullPath($BuildRoot)
$evidence=[IO.Path]::GetFullPath($EvidenceRoot)
$packageManifestPath=Join-Path $build 'unit2b3b_install_package_manifest.json'
$installContractPath=Join-Path $build 'Governance\unit2_stopped_install_contract.json'
$expectedBinary=Join-Path $install 'RandleTerminalUpgradeAuthority.exe'
$artifactTool=Join-Path $build 'Tools\R7ArtifactTool.exe'
$createdFiles=[Collections.Generic.List[string]]::new()
$createdDirectories=[Collections.Generic.List[string]]::new()
$createdEvidenceFiles=[Collections.Generic.List[string]]::new()
$createdEvidenceParent=$false
$createdEvidenceRun=$false
$evidenceClaim=$null
$evidenceClaimCreated=$false
$priorEvidenceSnapshot=@()
$rightsMeasurement=$null
$failureActionsSnapshot=$null
$failureActionsRestoreRequired=$false
$failureActionsConfiguration=$null
$failureActionsVerification=$null
$scmConfigurationChanged=$false
$mutations=[Collections.Generic.List[object]]::new()
$aclSnapshots=[Collections.Generic.List[object]]::new()

function Hash([string]$Path){(Get-FileHash -LiteralPath ([IO.Path]::GetFullPath($Path)) -Algorithm SHA256).Hash.ToLowerInvariant()}
function HashText([string]$Text){$sha=[Security.Cryptography.SHA256]::Create();try{return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}}
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
    $script:createdDirectories.Add([IO.Path]::GetFullPath($Path))
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
function AssertNoReparseTraversal([string]$Root,[string]$Path){
    $rootFull=[IO.Path]::GetFullPath($Root).TrimEnd('\')
    $pathFull=[IO.Path]::GetFullPath($Path)
    if($pathFull -cne $rootFull -and -not $pathFull.StartsWith($rootFull+'\',[StringComparison]::OrdinalIgnoreCase)){throw "Path escaped fixed root: $pathFull"}
    $cursor=$rootFull
    foreach($segment in @($pathFull.Substring($rootFull.Length).TrimStart('\').Split(@('\'),[StringSplitOptions]::RemoveEmptyEntries))){
        $cursor=Join-Path $cursor $segment
        if((Test-Path -LiteralPath $cursor) -and (((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)){throw "Reparse traversal rejected: $cursor"}
    }
}
function AssertSingleDataStream([string]$Path){
    $streams=@(Get-Item -LiteralPath $Path -Stream * -ErrorAction Stop)
    if($streams.Count -ne 1 -or [string]$streams[0].Stream -cne ':$DATA'){throw "Unexpected alternate data stream: $Path"}
}
function WriteExclusiveBytes([string]$Path,[byte[]]$Bytes){
    $full=[IO.Path]::GetFullPath($Path)
    $stream=[IO.File]::Open($full,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try{$stream.Write($Bytes,0,$Bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
}
function WriteEvidenceJson([string]$Name,[object]$Value){
    $path=Join-Path $evidence $Name
    AssertNoReparseTraversal $evidence $path
    WriteExclusiveBytes $path ([Text.UTF8Encoding]::new($false).GetBytes(($Value|ConvertTo-Json -Depth 50)))
    $script:createdEvidenceFiles.Add($path)
    return $path
}
function RunEvidenceTool([string[]]$Arguments,[string]$OutputPath){
    if(Test-Path -LiteralPath $OutputPath){throw "Evidence output collision: $OutputPath"}
    AssertNoReparseTraversal $evidence $OutputPath
    $result=Run $artifactTool $Arguments
    if(-not(Test-Path -LiteralPath $OutputPath -PathType Leaf)){throw "Evidence output absent: $OutputPath"}
    $script:createdEvidenceFiles.Add([IO.Path]::GetFullPath($OutputPath))
    return $result
}
function GetEvidenceSnapshot([object]$Policy){
    if(-not(Test-Path -LiteralPath $evidenceParent -PathType Container)){return @()}
    $expected=@{};foreach($row in @($Policy.preserved_records)){$expected[[string]$row.relative_path]=$row}
    $actual=[Collections.Generic.List[object]]::new()
    foreach($file in @(Get-ChildItem -LiteralPath $evidenceParent -Recurse -File -Force|Sort-Object FullName)){
        $relative=$file.FullName.Substring($evidenceParent.TrimEnd('\').Length+1).Replace('\','/')
        if(-not $expected.ContainsKey($relative)){throw "Unexpected pre-existing evidence rejected: $relative"}
        $row=$expected[$relative]
        if($file.Length -ne [long]$row.size -or (Hash $file.FullName) -cne [string]$row.raw_sha256){throw "Preserved evidence identity mismatch: $relative"}
        AssertSingleDataStream $file.FullName
        $actual.Add([ordered]@{path=$relative;raw_sha256=(Hash $file.FullName);size=[long]$file.Length})
    }
    if($actual.Count -ne $expected.Count){throw 'Required preserved evidence is absent'}
    return $actual.ToArray()
}
function AssertEvidenceSnapshot([object[]]$Snapshot){
    foreach($row in @($Snapshot)){$path=Join-Path $evidenceParent ([string]$row.path).Replace('/','\');if(-not(Test-Path -LiteralPath $path -PathType Leaf) -or (Hash $path) -cne [string]$row.raw_sha256 -or (Get-Item -LiteralPath $path).Length -ne [long]$row.size){throw "Prior evidence changed: $([string]$row.path)"}}
}
function AssertEvidenceRootAcl([object]$Policy){
    $item=Get-Item -LiteralPath $evidenceParent -Force
    if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'Evidence root reparse point rejected'}
    $acl=Get-Acl -LiteralPath $evidenceParent
    if([string]$acl.Owner -cne [string]$Policy.root_owner){throw 'Evidence root owner invalid'}
    $allowed=@([string[]]$Policy.allowed_writable_sids)
    $writeMask=[long]([Security.AccessControl.FileSystemRights]::WriteData -bor [Security.AccessControl.FileSystemRights]::AppendData -bor [Security.AccessControl.FileSystemRights]::CreateDirectories -bor [Security.AccessControl.FileSystemRights]::Delete -bor [Security.AccessControl.FileSystemRights]::ChangePermissions -bor [Security.AccessControl.FileSystemRights]::TakeOwnership)
    $rules=@($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))
    foreach($rule in $rules){if($rule.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and (([long]$rule.FileSystemRights -band $writeMask) -ne 0) -and $allowed -notcontains [string]$rule.IdentityReference.Value){throw "Unauthorized writable Evidence ACE: $([string]$rule.IdentityReference.Value)"}}
    foreach($sid in $allowed){if(@($rules|Where-Object{[string]$_.IdentityReference.Value -ceq $sid -and $_.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and (([long]$_.FileSystemRights -band [long][Security.AccessControl.FileSystemRights]::FullControl) -ne 0)}).Count -eq 0){throw "Required Evidence writer absent: $sid"}}
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
            WriteEvidenceJson 'unit2b_failure.json' $Failure|Out-Null
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
if(-not(Test-Path -LiteralPath $packageManifestPath -PathType Leaf) -or (Hash $packageManifestPath) -cne $ExpectedPackageManifestSha256 -or (Get-Item -LiteralPath $packageManifestPath).Length -ne $ExpectedPackageManifestSize){throw 'Unit 2B package manifest identity mismatch'}
$packageManifest=ReadJson $packageManifestPath
if([string]$packageManifest.source_commit -cne $SourceCommit -or [string]$packageManifest.status -cne 'PASS' -or [bool]$packageManifest.host_actions_performed){throw 'Package manifest source or offline binding invalid'}
$contractRows=@($packageManifest.files|Where-Object{[string]$_.path -ceq 'Governance/unit2_stopped_install_contract.json'})
if($contractRows.Count -ne 1 -or -not(Test-Path -LiteralPath $installContractPath -PathType Leaf) -or (Hash $installContractPath) -cne [string]$contractRows[0].raw_sha256 -or (Get-Item -LiteralPath $installContractPath).Length -ne [long]$contractRows[0].size){throw 'Install contract package binding invalid'}
$installContract=ReadJson $installContractPath
if([string]$installContract.artifact_type -cne 'R7_UNIT2_STOPPED_INSTALL_CONTRACT' -or [string]$installContract.schema_version -cne '1.0.0'){throw 'Install contract schema invalid'}
$installPlan=@($installContract.install_items)
$requiredInstallIds=@('BUILD_MANIFEST','DEPENDENCY_MANIFEST','DETERMINISM_RECEIPT','PACKAGE_MANIFEST','PACKAGED_ARTIFACT_TOOL','PACKAGED_PROTECTED_METADATA_TOOL','PUBLIC_CERTIFICATE','SOURCE_TO_BINARY_RECEIPT','UPGRADE_AUTHORITY','UPGRADE_CLIENT','UPGRADE_POLICY','UPGRADE_PROTOCOL_PROBE','UPGRADE_PUBLIC_VERIFIER')|Sort-Object
if($installPlan.Count -ne 13 -or ((@($installPlan.id|Sort-Object)-join "`n") -cne ($requiredInstallIds-join "`n"))){throw 'Install contract required payload set invalid'}
if(@($installPlan.source_path|Sort-Object -Unique).Count -ne $installPlan.Count){throw 'Install contract duplicate source'}
if(@($installPlan.destination_path|ForEach-Object{[IO.Path]::GetFullPath([string]$_)}|Sort-Object -Unique).Count -ne $installPlan.Count){throw 'Install contract duplicate destination'}
$manifestedInstallable=@($packageManifest.files|Where-Object{([string]$_.path -match '^(Install/.+|Tools/.+|Receipts/unit2_build_determinism_receipt.json|unit2_build_manifest.json)$')}|ForEach-Object{[string]$_.path}|Sort-Object)
$declaredManifestInstallable=@($installPlan|Where-Object{[string]$_.expected_sha256_source -ceq 'PACKAGE_MANIFEST_ROW'}|ForEach-Object{[string]$_.source_path}|Sort-Object)
if(($manifestedInstallable-join "`n") -cne ($declaredManifestInstallable-join "`n")){throw 'Unmanifested or unmapped installable payload'}
foreach($item in $installPlan){
    $sourceRelative=[string]$item.source_path
    if([IO.Path]::IsPathRooted($sourceRelative) -or $sourceRelative -match '(^|/)\.\.(/|$)' -or $sourceRelative.Contains('\')){throw "Install source path invalid: $sourceRelative"}
    $source=Join-Path $build $sourceRelative.Replace('/','\')
    AssertNoReparseTraversal $build $source
    if(-not(Test-Path -LiteralPath $source -PathType Leaf)){throw "Install source absent: $sourceRelative"}
    AssertSingleDataStream $source
    if([string]$item.expected_sha256_source -ceq 'PACKAGE_MANIFEST_ROW'){
        $rows=@($packageManifest.files|Where-Object{[string]$_.path -ceq $sourceRelative})
        if($rows.Count -ne 1 -or (Hash $source) -cne [string]$rows[0].raw_sha256 -or (Get-Item -LiteralPath $source).Length -ne [long]$rows[0].size){throw "Install source manifest mismatch: $sourceRelative"}
    }elseif([string]$item.id -ceq 'PACKAGE_MANIFEST'){
        if((Hash $source) -cne $ExpectedPackageManifestSha256 -or (Get-Item -LiteralPath $source).Length -ne $ExpectedPackageManifestSize){throw 'Package manifest self identity mismatch'}
    }else{throw "Install identity source invalid: $([string]$item.id)"}
    if([string]$item.required_owner -cne 'NT AUTHORITY\SYSTEM' -or [string]$item.rollback_behavior -notmatch 'CURRENT_RUN' -or [string]::IsNullOrWhiteSpace([string]$item.acl_class) -or [string]::IsNullOrWhiteSpace([string]$item.authority_classification)){throw "Install metadata incomplete: $([string]$item.id)"}
}
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
$configChildren=@(Get-ChildItem -LiteralPath $config -Force)
$expectedConfigChildren=@('BuildInputClosures','SourceInputs')
if($configChildren.Count -ne $expectedConfigChildren.Count -or ((@($configChildren.Name|Sort-Object)-join "`n") -cne (@($expectedConfigChildren|Sort-Object)-join "`n"))){throw 'Upgrade configuration root contains an unexpected bootstrap artifact'}
foreach($childName in $expectedConfigChildren){
    $child=Join-Path $config $childName
    if(-not(Test-Path -LiteralPath $child -PathType Container) -or @(Get-ChildItem -LiteralPath $child -Force).Count -ne 0){throw "Upgrade bootstrap configuration root is not an empty directory: $child"}
    AssertBootstrapRootAcl $bootstrap $child
}
$evidencePolicy=$installContract.evidence_policy
if([IO.Path]::GetFullPath([string]$evidencePolicy.fixed_root) -cne [IO.Path]::GetFullPath($evidenceParent)){throw 'Evidence contract fixed root invalid'}
if([IO.Path]::GetPathRoot($evidenceParent) -cne [IO.Path]::GetPathRoot($state)){throw 'Evidence root is on the wrong volume'}
$runIdentity=HashText ("R7_UNIT2B3C_EVIDENCE_RUN_V1`n$SourceCommit`n$ExpectedPackageManifestSha256`n$ExpectedBuildManifestSha256`n$ExpectedScriptSha256")
$expectedEvidence=Join-Path $evidenceParent (([string]$evidencePolicy.run_directory_prefix)+$runIdentity)
if($evidence -cne [IO.Path]::GetFullPath($expectedEvidence)){throw 'EvidenceRoot is not the governed content-addressed run directory'}
AssertNoReparseTraversal $state $evidenceParent
if(Test-Path -LiteralPath $evidenceParent){
    if(-not(Test-Path -LiteralPath $evidenceParent -PathType Container)){throw 'Evidence root is not a directory'}
    AssertEvidenceRootAcl $evidencePolicy
    $priorEvidenceSnapshot=@(GetEvidenceSnapshot $evidencePolicy)
}
$certTarget=Join-Path $trust 'upgrade_authority_public.cer'
if((Hash $certTarget) -cne [string]$bootstrap.public_certificate_sha256){throw 'Preserved public certificate bytes drifted'}
    $certificateAcl=Get-Acl -LiteralPath $certTarget
    if([string]$certificateAcl.Sddl -cne [string]$bootstrap.public_certificate_file_acl_sddl){throw 'Preserved public certificate ACL drifted'}
    foreach($snapshotPath in @($install,$config,$trust,$certTarget)){$aclSnapshots.Add([ordered]@{acl=(Get-Acl -LiteralPath $snapshotPath);path=$snapshotPath})}

try{
    if(-not(Test-Path -LiteralPath $evidenceParent)){
        NewDirectory $evidenceParent
        $createdEvidenceParent=$true
        $rootOwner=Run $icacls @($evidenceParent,'/setowner','SYSTEM','/C')
        $rootAcl=Run $icacls @($evidenceParent,'/inheritance:r','/grant:r','SYSTEM:(OI)(CI)(F)','BUILTIN\Administrators:(OI)(CI)(F)')
        $mutations.Add([ordered]@{acl_result=$rootAcl;operation='CREATE_GOVERNED_EVIDENCE_ROOT';owner_result=$rootOwner;root=$evidenceParent;service_stopped_before=$true})
        AssertEvidenceRootAcl $evidencePolicy
    }
    $evidenceClaim=Join-Path $evidenceParent ('.'+$runIdentity+[string]$evidencePolicy.exclusive_claim_suffix)
    WriteExclusiveBytes $evidenceClaim ([Text.Encoding]::UTF8.GetBytes($runIdentity+"`n"))
    $evidenceClaimCreated=$true
    if(Test-Path -LiteralPath $evidence){throw 'Content-addressed evidence run collision'}
    NewDirectory $evidence
    $createdEvidenceRun=$true
    $baselineRecord=[ordered]@{artifact_type='R7_UNIT2B_PRESTART_INSTALL_BASELINE';bootstrap_record_sha256=(Hash $BootstrapRecord);existing_terminal=$terminalBefore;preflight_host_state_sha256=$preflightSha;schema_version='1.0.0';service_state='STOPPED';source_commit=$SourceCommit;upgrade_service_pid=0}
    AssertStopped
    WriteEvidenceJson 'preinstall_baseline.json' $baselineRecord|Out-Null

    RunScMutation @('config',$service,'binPath=',$expectedBinary,'start=','demand','obj=',$account) 'SCM_CONFIG_FIXED_BINARY_ACCOUNT_MANUAL'|Out-Null
    RunScMutation @('sidtype',$service,'restricted') 'SCM_SID_TYPE_RESTRICTED'|Out-Null
    RunScMutation @('privs',$service,'SeChangeNotifyPrivilege') 'SCM_REQUIRED_PRIVILEGES_MINIMAL'|Out-Null
    $scmConfigurationChanged=$true
    $failureActionsSnapshot=Join-Path $evidence 'failure_actions_before.json'
    AssertStopped
    RunEvidenceTool @('capture-failure-actions',$service,$failureActionsSnapshot) $failureActionsSnapshot|Out-Null
    AssertStopped
    $failureActionsRestoreRequired=$true
    $failureActionsConfiguration=Join-Path $evidence 'failure_actions_configuration.json'
    AssertStopped
    $failureConfigurationResult=RunEvidenceTool @('configure-failure-actions-none',$service,'0',$failureActionsSnapshot,$failureActionsConfiguration) $failureActionsConfiguration
    $mutations.Add([ordered]@{measurement=$failureActionsConfiguration;operation='SCM_FAILURE_ACTIONS_NATIVE_ZERO_ACTION_CONFIGURATION';result=$failureConfigurationResult;service_stopped_before=$true})
    AssertStopped

    if(-not(Test-Path -LiteralPath $buildTools)){NewDirectory $buildTools}
    $installMap=@($installPlan|ForEach-Object{
        [ordered]@{acl_class=[string]$_.acl_class;authority_classification=[string]$_.authority_classification;destination=[IO.Path]::GetFullPath([string]$_.destination_path);destination_behavior=[string]$_.destination_behavior;id=[string]$_.id;kind=[string]$_.kind;rollback_behavior=[string]$_.rollback_behavior;source=[IO.Path]::GetFullPath((Join-Path $build ([string]$_.source_path).Replace('/','\')));source_path=[string]$_.source_path}
    })
    foreach($item in $installMap){
        if([string]$item.destination_behavior -ceq 'PRESERVE_EXISTING_EXACT_OR_COPY_NEW'){
            if(Test-Path -LiteralPath ([string]$item.destination) -PathType Leaf){
                if((Hash ([string]$item.source)) -cne (Hash ([string]$item.destination)) -or (Get-Item -LiteralPath ([string]$item.source)).Length -ne (Get-Item -LiteralPath ([string]$item.destination)).Length){throw "Preserved install target differs: $([string]$item.id)"}
            }else{CopyNew ([string]$item.source) ([string]$item.destination)}
        }elseif([string]$item.destination_behavior -ceq 'COPY_NEW_EXCLUSIVE'){
            CopyNew ([string]$item.source) ([string]$item.destination)
        }else{throw "Unknown destination behavior: $([string]$item.id)"}
    }

    foreach($root in @($install,$config,$trust,$buildTools)){
        AssertStopped
        $ownerResult=Run $icacls @($root,'/setowner','SYSTEM','/T','/C')
        $aclResult=Run $icacls @($root,'/inheritance:r','/grant:r','SYSTEM:(OI)(CI)(F)','BUILTIN\Administrators:(OI)(CI)(F)',"$account`:(OI)(CI)(RX)","$terminalAccount`:(OI)(CI)(RX)",'BUILTIN\Users:(OI)(CI)(RX)','/T','/C')
        $mutations.Add([ordered]@{acl_result=$aclResult;operation='ACL_FIXED_READ_ONLY_AUTHORITY_INPUT_ROOT';owner_result=$ownerResult;root=$root;service_stopped_before=$true})
        AssertStopped
    }
    AssertStopped
    $evidenceOwner=Run $icacls @($evidence,'/setowner','SYSTEM','/T','/C')
    $evidenceAcl=Run $icacls @($evidence,'/inheritance:r','/grant:r','SYSTEM:(OI)(CI)(F)','BUILTIN\Administrators:(OI)(CI)(F)','/T','/C')
    $mutations.Add([ordered]@{acl_result=$evidenceAcl;operation='ACL_CURRENT_EVIDENCE_RUN_ONLY';owner_result=$evidenceOwner;root=$evidence;service_stopped_before=$true})
    AssertStopped

    $rightsMeasurement=Join-Path $evidence 'service_boundary_rights.json'
    AssertStopped
    RunEvidenceTool @('service-boundary',$service,$sid,$expectedBinary,$rightsMeasurement) $rightsMeasurement|Out-Null
    $mutations.Add([ordered]@{measurement=$rightsMeasurement;operation='LSA_DENY_RIGHTS_ENFORCE_AND_MEASURE';service_stopped_before=$true})
    AssertStopped

    $physical=[Collections.Generic.List[object]]::new()
    foreach($item in $installMap){
        $name=[IO.Path]::GetFileName([string]$item.destination)
        $contentPath=Join-Path $evidence ('physical_content_'+$name+'.json')
        $metadataPath=Join-Path $evidence ('physical_metadata_'+$name+'.json')
        AssertStopped;RunEvidenceTool @('measure',[string]$item.destination,$contentPath) $contentPath|Out-Null
        AssertStopped;RunEvidenceTool @('measure-metadata',[string]$item.destination,$metadataPath) $metadataPath|Out-Null
        $physical.Add([ordered]@{content_measurement=$contentPath;metadata_measurement=$metadataPath;path=[string]$item.destination;sha256=(Hash ([string]$item.destination))})
    }

    $expectedInstallNames=@('RandleTerminalUpgradeAuthority.exe','RandleTerminalUpgradeClient.exe','RandleTerminalUpgradeProtocolProbe.exe','RandleTerminalUpgradePublicVerifier.exe')
    $actualInstallNames=@(Get-ChildItem -LiteralPath $install -Force -File|ForEach-Object Name|Sort-Object)
    if((@($expectedInstallNames|Sort-Object)-join "`n") -cne ($actualInstallNames-join "`n")){throw 'Installed executable set is not exact'}
    $expectedConfigNames=@('dependency_manifest.json','unit2_build_manifest.json','unit2b_install_package_manifest.json','upgrade_authority_build_receipt.json','upgrade_authority_determinism_receipt.json','upgrade_authority_policy.json')
    $actualConfigNames=@(Get-ChildItem -LiteralPath $config -Force -File|ForEach-Object Name|Sort-Object)
    if((@($expectedConfigNames|Sort-Object)-join "`n") -cne ($actualConfigNames-join "`n")){throw 'Installed configuration set is not exact'}
    if(@(Get-ChildItem -LiteralPath $trust -Force -File).Count -ne 1){throw 'Public trust file set is not exact'}
    $expectedToolNames=@('R7ArtifactTool.exe','R7ProtectedMetadataTool.exe')
    $actualToolNames=@(Get-ChildItem -LiteralPath $buildTools -Force -File|ForEach-Object Name|Sort-Object)
    if((@($expectedToolNames|Sort-Object)-join "`n") -cne ($actualToolNames-join "`n")){throw 'Installed governed tool set is not exact'}

    $policy=ReadJson (Join-Path $config 'upgrade_authority_policy.json')
    if(([string[]]@($policy.operation_allowlist)-join "`n") -cne (@('AUTHORIZE_TERMINAL_TRANSITION','GET_AUTHORIZATION','GET_HEALTH','GET_PUBLIC_IDENTITY')-join "`n") -or [string]$policy.service.name -cne $service -or [string]$policy.service.account -cne $account -or [string]$policy.service.sid -cne $sid -or [string]$policy.provisioning_script_sha256 -cne $ExpectedScriptSha256 -or [string]$policy.key.key_unique_name -cne [string]$bootstrap.key_unique_name){throw 'Installed policy fixed-boundary validation failed'}

    $qc=Run $sc @('qc',$service)
    $sidType=Run $sc @('qsidtype',$service)
    $privileges=Run $sc @('qprivs',$service)
    $failureActionsVerification=Join-Path $evidence 'failure_actions_verification.json'
    AssertStopped
    RunEvidenceTool @('verify-failure-actions-none',$service,'0',$failureActionsVerification) $failureActionsVerification|Out-Null
    AssertStopped
    $query=Run $sc @('queryex',$service)
    $qcText=$qc.output -join "`n";$sidText=$sidType.output -join "`n";$privText=$privileges.output -join "`n";$queryText=$query.output -join "`n"
    if($qcText -notmatch [regex]::Escape($expectedBinary) -or $qcText -notmatch 'DEMAND_START' -or $qcText -notmatch [regex]::Escape($account) -or $sidText -notmatch 'RESTRICTED' -or $privText -notmatch 'SeChangeNotifyPrivilege' -or $privText -match 'SeImpersonatePrivilege' -or $queryText -notmatch 'STATE\s+: 1\s+STOPPED' -or $queryText -notmatch 'PID\s+: 0'){throw 'Stopped SCM boundary verification failed'}

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
    AssertEvidenceSnapshot $priorEvidenceSnapshot
    $record=[ordered]@{artifact_type='R7_UNIT2B_STOPPED_BOUNDARY_INSTALLATION_RECORD';build_manifest_sha256=$ExpectedBuildManifestSha256;evidence_run_identity=$runIdentity;existing_terminal_after=$terminalAfter;existing_terminal_before=$terminalBefore;failure_actions_configuration_sha256=(Hash $failureActionsConfiguration);failure_actions_disabled=$true;failure_actions_prior_snapshot_sha256=(Hash $failureActionsSnapshot);failure_actions_verification_sha256=(Hash $failureActionsVerification);install_contract_sha256=(Hash $installContractPath);installed_files=@($physical);key_opened_for_signing=$false;ledger_created=$false;mutations=$mutations.ToArray();package_manifest_sha256=$ExpectedPackageManifestSha256;preexisting_evidence=@($priorEvidenceSnapshot);preflight_baseline_sha256=$preflightSha;private_key_exported=$false;provisioning_attestation_issued=$false;public_certificate_retained_sha256=(Hash $certTarget);repository_acl=$repositoryAcl;schema_version='1.0.0';service_name=$service;service_pid=0;service_started=$false;service_state='STOPPED';source_commit=$SourceCommit;status='PASS';terminal_boundary_acls=$terminalBoundaryAcls;terminal_transition_authorized=$false;utilities=@([ordered]@{role=[string]$scRow.role;sha256=[string]$scRow.measurement.sha256},[ordered]@{role=[string]$icaclsRow.role;sha256=[string]$icaclsRow.measurement.sha256},[ordered]@{role=[string]$powershellRow.role;sha256=[string]$powershellRow.measurement.sha256})}
    $rawRecord=Join-Path $evidence 'unit2b_installation_record.raw.json'
    $recordPath=Join-Path $evidence 'unit2b_installation_record.json'
    AssertStopped
    WriteEvidenceJson 'unit2b_installation_record.raw.json' $record|Out-Null
    AssertStopped
    RunEvidenceTool @('canonicalize',$rawRecord,$recordPath) $recordPath|Out-Null
    AssertStopped
    AssertEvidenceSnapshot $priorEvidenceSnapshot
    Remove-Item -LiteralPath $evidenceClaim -Force
    $evidenceClaim=$null
    $evidenceClaimCreated=$false
    [ordered]@{evidence_root=$evidence;record_sha256=(Hash $recordPath);service_started=$false;status='PASS';terminal_transition_authorized=$false}|ConvertTo-Json
}
catch{
    $failure=[ordered]@{artifact_type='R7_UNIT2B_INSTALLATION_FAILURE';error=$_.Exception.GetType().FullName+'|'+$_.Exception.Message;rollback_attempted=$true;schema_version='1.0.0';service_started=$false;terminal_transition_authorized=$false}
    $rollbackErrors=[Collections.Generic.List[string]]::new()
    try{AssertStopped}catch{$rollbackErrors.Add($_.Exception.Message)}
    if($rightsMeasurement -and (Test-Path -LiteralPath $rightsMeasurement -PathType Leaf)){
        try{AssertStopped;$restorePath=Join-Path $evidence 'service_boundary_rights_restoration.json';RunEvidenceTool @('restore-service-boundary',$rightsMeasurement,$restorePath) $restorePath|Out-Null}catch{$rollbackErrors.Add($_.Exception.Message)}
    }
    if($failureActionsRestoreRequired -and $failureActionsSnapshot -and (Test-Path -LiteralPath $failureActionsSnapshot -PathType Leaf)){
        try{AssertStopped;$failureRestorePath=Join-Path $evidence 'failure_actions_restoration.json';RunEvidenceTool @('restore-failure-actions',$service,$failureActionsSnapshot,$failureRestorePath) $failureRestorePath|Out-Null;AssertStopped}catch{$rollbackErrors.Add($_.Exception.Message)}
    }
    if($scmConfigurationChanged){
        try{RunScMutation @('config',$service,'binPath=',$expectedBinary,'start=','demand','obj=',$account) 'ROLLBACK_SCM_CONFIG'|Out-Null}catch{$rollbackErrors.Add($_.Exception.Message)}
        try{RunScMutation @('sidtype',$service,'restricted') 'ROLLBACK_SCM_SID_TYPE'|Out-Null}catch{$rollbackErrors.Add($_.Exception.Message)}
        try{RunScMutation @('privs',$service,'SeChangeNotifyPrivilege') 'ROLLBACK_SCM_PRIVILEGES'|Out-Null}catch{$rollbackErrors.Add($_.Exception.Message)}
    }
    foreach($path in @($createdFiles.ToArray()|Sort-Object -Descending)){
        try{AssertStopped;$resolved=[IO.Path]::GetFullPath($path);if(-not($resolved.StartsWith($install+'\',[StringComparison]::OrdinalIgnoreCase) -or $resolved.StartsWith($config+'\',[StringComparison]::OrdinalIgnoreCase) -or $resolved.StartsWith($buildTools+'\',[StringComparison]::OrdinalIgnoreCase))){throw "Rollback path escaped Unit 2B roots: $resolved"};if(Test-Path -LiteralPath $resolved -PathType Leaf){Remove-Item -LiteralPath $resolved -Force}}catch{$rollbackErrors.Add($_.Exception.Message)}
    }
    foreach($snapshot in @($aclSnapshots.ToArray()|Sort-Object{([string]$_.path).Length} -Descending)){
        try{AssertStopped;if(Test-Path -LiteralPath ([string]$snapshot.path)){Set-Acl -LiteralPath ([string]$snapshot.path) -AclObject $snapshot.acl;AssertStopped}}catch{$rollbackErrors.Add($_.Exception.Message)}
    }
    foreach($path in @($createdEvidenceFiles.ToArray()|Sort-Object -Unique|Sort-Object -Descending)){
        try{$resolved=[IO.Path]::GetFullPath($path);AssertNoReparseTraversal $evidence $resolved;if([IO.Path]::GetFileName($resolved) -notin @('preinstall_baseline.json','unit2b_failure.json') -and (Test-Path -LiteralPath $resolved -PathType Leaf)){Remove-Item -LiteralPath $resolved -Force}}catch{$rollbackErrors.Add($_.Exception.Message)}
    }
    if($evidenceClaimCreated -and $evidenceClaim){try{if(Test-Path -LiteralPath $evidenceClaim -PathType Leaf){Remove-Item -LiteralPath $evidenceClaim -Force};$evidenceClaimCreated=$false}catch{$rollbackErrors.Add($_.Exception.Message)}}
    try{AssertEvidenceSnapshot $priorEvidenceSnapshot}catch{$rollbackErrors.Add($_.Exception.Message)}
    if((Test-Path -LiteralPath $buildTools -PathType Container) -and @(Get-ChildItem -LiteralPath $buildTools -Force).Count -eq 0){try{Remove-Item -LiteralPath $buildTools -Force}catch{$rollbackErrors.Add($_.Exception.Message)}}
    $failure['rollback_errors']=$rollbackErrors.ToArray()
    $failure['rollback_complete']=($rollbackErrors.Count -eq 0)
    WriteFailure $failure
    throw ('UNIT2B_INSTALLATION_FAILED_AND_ROLLBACK_'+($(if($rollbackErrors.Count -eq 0){'COMPLETE'}else{'INCOMPLETE'}))+'|'+$failure.error)
}
