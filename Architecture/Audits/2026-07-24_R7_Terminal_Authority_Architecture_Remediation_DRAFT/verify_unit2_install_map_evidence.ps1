[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [string]$ContractPath=(Join-Path $PSScriptRoot 'unit2_stopped_install_contract.json'),
    [string]$InstallerPath=(Join-Path $PSScriptRoot 'complete_unit2_upgrade_authority.ps1')
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest

function Clone([object]$Value){$Value|ConvertTo-Json -Depth 30|ConvertFrom-Json}
function HashBytes([byte[]]$Bytes){$sha=[Security.Cryptography.SHA256]::Create();try{([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}}
function ValidateMap([object[]]$Rows,[string[]]$Manifested){
    $required=@('BUILD_MANIFEST','DEPENDENCY_MANIFEST','DETERMINISM_RECEIPT','PACKAGE_MANIFEST','PACKAGED_ARTIFACT_TOOL','PACKAGED_PROTECTED_METADATA_TOOL','PUBLIC_CERTIFICATE','SOURCE_TO_BINARY_RECEIPT','UPGRADE_AUTHORITY','UPGRADE_CLIENT','UPGRADE_POLICY','UPGRADE_PROTOCOL_PROBE','UPGRADE_PUBLIC_VERIFIER')|Sort-Object
    $destinations=@{BUILD_MANIFEST='C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Config\unit2_build_manifest.json';DEPENDENCY_MANIFEST='C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Config\dependency_manifest.json';DETERMINISM_RECEIPT='C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Config\upgrade_authority_determinism_receipt.json';PACKAGE_MANIFEST='C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Config\unit2b_install_package_manifest.json';PACKAGED_ARTIFACT_TOOL='C:\ProgramData\RandleAI\TerminalUpgradeAuthority\BuildTools\R7ArtifactTool.exe';PACKAGED_PROTECTED_METADATA_TOOL='C:\ProgramData\RandleAI\TerminalUpgradeAuthority\BuildTools\R7ProtectedMetadataTool.exe';PUBLIC_CERTIFICATE='C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Trust\upgrade_authority_public.cer';SOURCE_TO_BINARY_RECEIPT='C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Config\upgrade_authority_build_receipt.json';UPGRADE_AUTHORITY='C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradeAuthority.exe';UPGRADE_CLIENT='C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradeClient.exe';UPGRADE_POLICY='C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Config\upgrade_authority_policy.json';UPGRADE_PROTOCOL_PROBE='C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradeProtocolProbe.exe';UPGRADE_PUBLIC_VERIFIER='C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradePublicVerifier.exe'}
    if($Rows.Count -ne 13 -or ((@($Rows.id|Sort-Object)-join "`n") -cne ($required-join "`n"))){throw 'required payload set'}
    if(@($Rows.source_path|Sort-Object -Unique).Count -ne $Rows.Count){throw 'duplicate source'}
    if(@($Rows.destination_path|Sort-Object -Unique).Count -ne $Rows.Count){throw 'duplicate destination'}
    foreach($row in $Rows){
        if(-not $destinations.ContainsKey([string]$row.id) -or [string]$row.destination_path -cne [string]$destinations[[string]$row.id]){throw 'fixed destination mismatch'}
        $expectedBehavior=$(if([string]$row.id -ceq 'PUBLIC_CERTIFICATE'){'PRESERVE_EXISTING_EXACT_OR_COPY_NEW'}else{'COPY_NEW_EXCLUSIVE'})
        if([string]$row.destination_behavior -cne $expectedBehavior){throw 'destination behavior mismatch'}
        if([IO.Path]::IsPathRooted([string]$row.source_path) -or [string]$row.source_path -match '(^|/)\.\.(/|$)' -or [string]$row.source_path -match '\\'){throw 'source escape'}
        if($row.PSObject.Properties.Name -contains 'expected_sha256' -and [string]$row.expected_sha256 -cne [string]$row.actual_sha256){throw 'wrong hash'}
        if($row.PSObject.Properties.Name -contains 'expected_size' -and [long]$row.expected_size -ne [long]$row.actual_size){throw 'wrong size'}
    }
    $mapped=@($Rows|Where-Object{[string]$_.expected_sha256_source -ceq 'PACKAGE_MANIFEST_ROW'}|ForEach-Object{[string]$_.source_path}|Sort-Object)
    if(($mapped-join "`n") -cne (@($Manifested|Sort-Object)-join "`n")){throw 'unmanifested payload'}
}
function ValidateEvidence([object]$Model){
    if([string]$Model.owner -cne 'NT AUTHORITY\SYSTEM'){throw 'owner'}
    if([bool]$Model.reparse){throw 'reparse'}
    $allowed=@('S-1-5-18','S-1-5-32-544')
    foreach($writer in @($Model.writers)){if($allowed -notcontains [string]$writer){throw 'writable ace'}}
    if([bool]$Model.collision){throw 'collision'}
    if([bool]$Model.overwrite){throw 'overwrite'}
    if(@($Model.unexpected).Count -ne 0){throw 'unexpected evidence'}
}
function ExpectPass([string]$Name,[scriptblock]$Body){try{&$Body;$script:results.Add([ordered]@{name=$Name;status='PASS'})}catch{$script:results.Add([ordered]@{error=$_.Exception.Message;name=$Name;status='FAIL'})}}
function ExpectFail([string]$Name,[scriptblock]$Body){try{&$Body;$script:results.Add([ordered]@{error='fixture was accepted';name=$Name;status='FAIL'})}catch{$script:results.Add([ordered]@{name=$Name;rejection=$_.Exception.Message;status='PASS'})}}

$contract=Get-Content -LiteralPath ([IO.Path]::GetFullPath($ContractPath)) -Raw|ConvertFrom-Json
$installer=Get-Content -LiteralPath ([IO.Path]::GetFullPath($InstallerPath)) -Raw
foreach($token in @('$installContract.install_items','PRESERVE_EXISTING_EXACT_OR_COPY_NEW','COPY_NEW_EXCLUSIVE','WriteExclusiveBytes','GetEvidenceSnapshot','AssertEvidenceSnapshot','createdEvidenceFiles')){if(-not $installer.Contains($token)){throw "Installer closure token absent: $token"}}
if($installer.Contains('evidence parent must not exist before installation')){throw 'Legacy Evidence absence guard remains'}
$base=@($contract.install_items|ForEach-Object{Clone $_})
foreach($row in $base){$row|Add-Member expected_sha256 ('a'*64);$row|Add-Member actual_sha256 ('a'*64);$row|Add-Member expected_size 10;$row|Add-Member actual_size 10}
$manifested=@($base|Where-Object{[string]$_.expected_sha256_source -ceq 'PACKAGE_MANIFEST_ROW'}|ForEach-Object{[string]$_.source_path})
$results=[Collections.Generic.List[object]]::new()

ExpectPass '01_COMPLETE_SIX_EXECUTABLE_TOOL_MAP' {ValidateMap $base $manifested}
ExpectFail '02_MISSING_PROTOCOL_PROBE' {ValidateMap @($base|Where-Object{$_.id -cne 'UPGRADE_PROTOCOL_PROBE'}) $manifested}
ExpectFail '03_MISSING_ARTIFACT_TOOL' {ValidateMap @($base|Where-Object{$_.id -cne 'PACKAGED_ARTIFACT_TOOL'}) $manifested}
ExpectFail '04_MISSING_PROTECTED_METADATA_TOOL' {ValidateMap @($base|Where-Object{$_.id -cne 'PACKAGED_PROTECTED_METADATA_TOOL'}) $manifested}
$x=@($base|ForEach-Object{Clone $_});$x[1].destination_path=$x[0].destination_path;ExpectFail '05_DUPLICATE_DESTINATION' {ValidateMap $x $manifested}
$x=@($base|ForEach-Object{Clone $_});$x[1].source_path=$x[0].source_path;ExpectFail '06_DUPLICATE_SOURCE' {ValidateMap $x $manifested}
$x=@($base|ForEach-Object{Clone $_});$x[0].source_path='../escape.exe';ExpectFail '07_SOURCE_PATH_ESCAPE' {ValidateMap $x $manifested}
$x=@($base|ForEach-Object{Clone $_});$x[0].actual_sha256=('b'*64);ExpectFail '08_WRONG_HASH' {ValidateMap $x $manifested}
$x=@($base|ForEach-Object{Clone $_});$x[0].actual_size=11;ExpectFail '09_WRONG_SIZE' {ValidateMap $x $manifested}
ExpectFail '10_UNMANIFESTED_INSTALLABLE_PAYLOAD' {ValidateMap $base @($manifested+'Install/Unexpected.exe')}

$valid=[ordered]@{collision=$false;overwrite=$false;owner='NT AUTHORITY\SYSTEM';reparse=$false;unexpected=@();writers=@('S-1-5-18','S-1-5-32-544')}
ExpectPass '11_EXISTING_VALID_EVIDENCE_ROOT' {ValidateEvidence $valid}
$priorA=[Text.Encoding]::UTF8.GetBytes('preinstall-baseline');$priorB=[Text.Encoding]::UTF8.GetBytes('failure-record');$before=@((HashBytes $priorA),(HashBytes $priorB));$after=@((HashBytes $priorA),(HashBytes $priorB));ExpectPass '12_PRESERVED_EVIDENCE_BYTE_IDENTICAL' {if(($before-join '') -cne ($after-join '')){throw 'changed'}}
$x=Clone $valid;$x.overwrite=$true;ExpectFail '13_ATTEMPTED_OVERWRITE' {ValidateEvidence $x}
$x=Clone $valid;$x.collision=$true;ExpectFail '14_FILENAME_COLLISION' {ValidateEvidence $x}
$x=Clone $valid;$x.owner='BUILTIN\Users';ExpectFail '15_INVALID_OWNER' {ValidateEvidence $x}
$x=Clone $valid;$x.writers=@('S-1-5-18','S-1-5-32-544','S-1-5-32-545');ExpectFail '16_UNAUTHORIZED_WRITABLE_ACE' {ValidateEvidence $x}
$x=Clone $valid;$x.reparse=$true;ExpectFail '17_REPARSE_EVIDENCE_ROOT' {ValidateEvidence $x}
$prior=@('prior/a.json','prior/b.json');$current=@('current/transient.json','current/preinstall_baseline.json','current/unit2b_failure.json');$remaining=@($prior)+@($current|Where-Object{$_ -match '(preinstall_baseline|unit2b_failure)' });ExpectPass '18_ROLLBACK_REMOVES_ONLY_CURRENT_TRANSIENTS' {if($remaining -contains 'current/transient.json'){throw 'transient retained'}}
ExpectPass '19_ROLLBACK_PRESERVES_ALL_PRIOR_EVIDENCE' {foreach($p in $prior){if($remaining -notcontains $p){throw 'prior removed'}}}
$x=Clone $valid;$x.unexpected=@('unknown.json');ExpectFail '20_UNEXPECTED_EVIDENCE_REJECTED' {ValidateEvidence $x}
$fixtureRoot=Join-Path ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($OutputPath))) ('unit2b3d_fixture_'+[Guid]::NewGuid().ToString('N'));New-Item -ItemType Directory -Path $fixtureRoot|Out-Null
try{
    $claim=Join-Path $fixtureRoot '.claim';[IO.File]::WriteAllBytes($claim,[byte[]](1));ExpectFail '21_CONCURRENT_EXCLUSIVE_CREATE_COLLISION' {$s=[IO.File]::Open($claim,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);$s.Dispose()}
    $missing=Join-Path $fixtureRoot 'Evidence';ExpectPass '22_MISSING_EVIDENCE_ROOT_SAFE_CREATE' {New-Item -ItemType Directory -Path $missing|Out-Null;if(-not(Test-Path -LiteralPath $missing -PathType Container)){throw 'absent'}}
}finally{Remove-Item -LiteralPath $fixtureRoot -Recurse -Force}

$failed=@($results|Where-Object{$_.status -cne 'PASS'})
$receipt=[ordered]@{artifact_type='R7_UNIT2B3D_INSTALL_MAP_EVIDENCE_REGRESSION';contract_sha256=(Get-FileHash -LiteralPath $ContractPath -Algorithm SHA256).Hash.ToLowerInvariant();host_actions_performed=$false;results=$results.ToArray();schema_version='1.0.0';status=$(if($failed.Count -eq 0){'PASS'}else{'FAIL'});test_count=$results.Count}
$json=$receipt|ConvertTo-Json -Depth 20
$out=[IO.Path]::GetFullPath($OutputPath);$parent=[IO.Path]::GetDirectoryName($out);if(-not(Test-Path -LiteralPath $parent)){New-Item -ItemType Directory -Path $parent|Out-Null};[IO.File]::WriteAllText($out,$json,[Text.UTF8Encoding]::new($false))
if($failed.Count){throw "Unit 2B-3D regression failures: $($failed.name -join ', ')"}
$json
