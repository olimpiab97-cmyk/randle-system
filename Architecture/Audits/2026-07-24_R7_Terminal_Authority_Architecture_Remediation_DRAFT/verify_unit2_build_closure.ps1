[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$SourceCommit,
    [Parameter(Mandatory=$true)][string]$BuildRoot,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedScriptSha256,
    [switch]$CandidateWorktree
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$packageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $packageRoot '..\..\..'))
$packageRelativeRoot = 'Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT'
$build = [IO.Path]::GetFullPath($BuildRoot)
$output = [IO.Path]::GetFullPath($OutputPath)
$receiptPath = Join-Path $build 'Generated\unit2_build_receipt.json'
$determinismPath = Join-Path $build 'Generated\unit2_build_determinism_receipt.json'
$manifestPath = Join-Path $build 'unit2_build_manifest.json'
$negativePath = Join-Path $packageRoot 'unit2_build_closure_negative_cases.json'
$contractPath = Join-Path $packageRoot 'BuildInputs\R7BuildIdentityContract.cs'
$requiredSwitches = @('/nologo','/noconfig','/target:exe','/platform:x64','/optimize+','/checked+','/debug-','/warn:4','/warnaserror+','/nostdlib+','/langversion:5','/filealign:512')
$requiredRoles = @('BUILD_BOOTSTRAP_ARTIFACT_TOOL','BUILD_BOOTSTRAP_PROTECTED_METADATA_TOOL','PACKAGED_ARTIFACT_TOOL','PACKAGED_PROTECTED_METADATA_TOOL','UPGRADE_AUTHORITY','UPGRADE_CLIENT','UPGRADE_PROTOCOL_PROBE','UPGRADE_PUBLIC_VERIFIER')

function Hash([string]$Path) { return (Get-FileHash -LiteralPath ([IO.Path]::GetFullPath($Path)) -Algorithm SHA256).Hash.ToLowerInvariant() }
function ReadJson([string]$Path) { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }
function Clone([object]$Value) { return ($Value | ConvertTo-Json -Depth 100 | ConvertFrom-Json) }
function Relative([string]$Base,[string]$Path) {
    $baseFull = [IO.Path]::GetFullPath($Base).TrimEnd('\') + '\'
    return [Uri]::UnescapeDataString(([Uri]$baseFull).MakeRelativeUri([Uri][IO.Path]::GetFullPath($Path)).ToString()).Replace('\','/')
}
function GitBlob([string]$Path) {
    $bytes = [IO.File]::ReadAllBytes([IO.Path]::GetFullPath($Path));$header=[Text.Encoding]::ASCII.GetBytes(('blob '+$bytes.Length+[char]0));$all=New-Object byte[] ($header.Length+$bytes.Length)
    [Buffer]::BlockCopy($header,0,$all,0,$header.Length);[Buffer]::BlockCopy($bytes,0,$all,$header.Length,$bytes.Length);$sha=[Security.Cryptography.SHA1]::Create()
    try{return ([BitConverter]::ToString($sha.ComputeHash($all))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
}
function Fail([string]$Code,[string]$Detail) { throw ([IO.InvalidDataException]::new($Code + '|' + $Detail)) }
function HasField([object]$Value,[string]$Name) {
    if($null-eq$Value){return $false}
    if($Value -is [Collections.IDictionary]){return $Value.Contains($Name)}
    return $null-ne($Value.PSObject.Properties[$Name])
}
function FieldValue([object]$Value,[string]$Name) {
    if(-not(HasField $Value $Name)){return $null}
    if($Value -is [Collections.IDictionary]){return $Value[$Name]}
    return ($Value.PSObject.Properties[$Name]).Value
}
function FieldNames([object]$Value) {
    if($null-eq$Value){return @()}
    if($Value -is [Collections.IDictionary]){return @($Value.Keys|ForEach-Object{[string]$_})}
    return @($Value.PSObject.Properties|ForEach-Object{[string]$_.Name})
}
function DiagnosticValue([object]$Value) {
    if($null-eq$Value){return '<null>'}
    if($Value -is [string]){return [string]$Value}
    return ($Value|ConvertTo-Json -Depth 20 -Compress)
}
function FailInputField([string]$Role,[string]$InputPath,[string]$Field,[object]$Expected,[object]$Observed) {
    Fail 'COMPILER_INPUT_IDENTITY_MISMATCH' (('role={0};input={1};field={2};expected={3};observed={4}' -f $Role,$InputPath,$Field,(DiagnosticValue $Expected),(DiagnosticValue $Observed)))
}
function AssertCanonicalInputPath([string]$Path,[string]$Context) {
    if([string]::IsNullOrWhiteSpace($Path)-or[IO.Path]::IsPathRooted($Path)){Fail 'COMPILER_INPUT_PATH_INVALID' ($Context+'/'+$Path)}
    $normalized=$Path.Replace('\','/')
    $segments=@($normalized.Split('/'))
    if($normalized-cne$Path-or@($segments|Where-Object{$_-ceq''-or$_-ceq'.'-or$_-ceq'..'}).Count-ne0){Fail 'COMPILER_INPUT_PATH_INVALID' ($Context+'/'+$Path)}
    return $normalized
}
function AssertExactObject([string]$Role,[string]$InputPath,[string]$Field,[object]$Expected,[object]$Observed) {
    if($null-eq$Expected-or$null-eq$Observed){if((DiagnosticValue $Expected)-cne(DiagnosticValue $Observed)){FailInputField $Role $InputPath $Field $Expected $Observed};return}
    $expectedNames=@(FieldNames $Expected|Sort-Object);$observedNames=@(FieldNames $Observed|Sort-Object)
    if(($expectedNames-join "`n")-cne($observedNames-join "`n")){FailInputField $Role $InputPath ($Field+'.fields') $expectedNames $observedNames}
    foreach($name in $expectedNames){$expectedValue=FieldValue $Expected $name;$observedValue=FieldValue $Observed $name;if((DiagnosticValue $expectedValue)-cne(DiagnosticValue $observedValue)){FailInputField $Role $InputPath ($Field+'.'+$name) $expectedValue $observedValue}}
}
function AssertCompilerInputSchema([string]$Role,[object]$InputRecord) {
    $path=if(HasField $InputRecord 'path'){[string](FieldValue $InputRecord 'path')}else{'<missing>'}
    $required=@('generation_rule','generator','git_blob_identity','mode','path','raw_sha256','size')
    $observed=@(FieldNames $InputRecord)
    foreach($field in $required){if($observed-cnotcontains$field){FailInputField $Role $path $field '<present>' '<missing>'}}
    foreach($field in $observed){if($required-cnotcontains$field){FailInputField $Role $path $field '<absent>' (FieldValue $InputRecord $field)}}
}
function CanonicalCompilerInputIndex([object]$Receipt) {
    $index=@{}
    foreach($source in @($Receipt.source_files)){
        $path=AssertCanonicalInputPath ([string]$source.path) 'committed-authority'
        if($index.ContainsKey($path)){Fail 'COMPILER_INPUT_AUTHORITY_AMBIGUOUS' $path}
        $index[$path]=[ordered]@{classification='COMMITTED';record=[ordered]@{generation_rule=$null;generator=$null;git_blob_identity=$source.git_blob_identity;mode=$source.mode;path=$path;raw_sha256=$source.raw_sha256;size=$source.size}}
    }
    foreach($generated in @($Receipt.generated_sources)){
        $path=AssertCanonicalInputPath ([string]$generated.path) 'generated-authority'
        if($index.ContainsKey($path)){Fail 'COMPILER_INPUT_AUTHORITY_AMBIGUOUS' $path}
        $index[$path]=[ordered]@{classification='GENERATED';record=[ordered]@{generation_rule=$generated.generation_rule;generator=$generated.generator;git_blob_identity=$null;mode=$null;path=$path;raw_sha256=$generated.raw_sha256;size=$generated.size}}
    }
    return $index
}
function AssertCompilerInputBinding([string]$Role,[object]$InputRecord,[hashtable]$CanonicalIndex) {
    AssertCompilerInputSchema $Role $InputRecord
    $path=AssertCanonicalInputPath ([string]$InputRecord.path) ($Role+'/role-input')
    if(-not$CanonicalIndex.ContainsKey($path)){Fail 'COMPILER_INPUT_AUTHORITY_MISSING' ($Role+'/'+$path)}
    $canonical=$CanonicalIndex[$path].record
    foreach($field in @('generation_rule','git_blob_identity','mode','path','raw_sha256','size')){$expected=FieldValue $canonical $field;$observed=FieldValue $InputRecord $field;if((DiagnosticValue $expected)-cne(DiagnosticValue $observed)){FailInputField $Role $path $field $expected $observed}}
    AssertExactObject $Role $path 'generator' (FieldValue $canonical 'generator') (FieldValue $InputRecord 'generator')
    return [string]$CanonicalIndex[$path].classification
}
function ForbiddenIdentity([object]$Value) {
    $text = [string]$Value
    if ([string]::IsNullOrWhiteSpace($text)) { return $true }
    if ($text -match '^(?:0{40}|0{64}|0{8}|0{8}:0{16})$') { return $true }
    return $text -match '(?i)(?:BOOTSTRAP_PENDING|DEVELOPMENT|PLACEHOLDER|\bTBD\b|\bUNKNOWN\b)'
}
function SourceTokenInvalid([string]$Text) {
    return $Text -match '(?i)(?:UNIT2_GENERATED_|BOOTSTRAP_PENDING|STATIC_PLACEHOLDER|R7DevelopmentIdentity)' -or $Text -match '"0{40}"' -or $Text -match '"0{64}"'
}
function ExtractIdentity([string]$Binary) {
    $assembly=[Reflection.Assembly]::ReflectionOnlyLoadFrom([IO.Path]::GetFullPath($Binary));$result=[ordered]@{}
    foreach($typeName in @('RandleAI.R7Remediation.R7BuildIdentity','RandleAI.R7Remediation.R7Unit2BuildIdentity')){$type=$assembly.GetType($typeName,$true,$false);foreach($field in @($type.GetFields([Reflection.BindingFlags]'Static,NonPublic,Public')|Sort-Object Name)){if($field.IsLiteral){$result[($type.Name+'.'+$field.Name)]=$field.GetRawConstantValue()}}}
    return $result
}
function ExtractPackagedIdentity([string]$Binary) {
    $assembly=[Reflection.Assembly]::ReflectionOnlyLoadFrom([IO.Path]::GetFullPath($Binary));$result=[ordered]@{}
    foreach($typeName in @('RandleAI.R7Remediation.R7BuildIdentity','RandleAI.R7Remediation.R7Unit2BuildIdentity')){$type=$assembly.GetType($typeName,$false,$false);if($null-eq$type){continue};foreach($field in @($type.GetFields([Reflection.BindingFlags]'Static,NonPublic,Public')|Sort-Object Name)){if($field.IsLiteral){$result[($type.Name+'.'+$field.Name)]=$field.GetRawConstantValue()}}}
    return $result
}
function ValidateModel([object]$Receipt,[hashtable]$GeneratedTextOverrides) {
    $canonicalInputs=CanonicalCompilerInputIndex $Receipt
    $declaredSourcePaths=@($Receipt.source_files|ForEach-Object{[string]$_.path})
    foreach($generated in @($Receipt.generated_sources)){
        $generatedPath=Join-Path $build ([string]$generated.path).Replace('/','\')
        $text=if($GeneratedTextOverrides.ContainsKey([string]$generated.path)){[string]$GeneratedTextOverrides[[string]$generated.path]}else{[IO.File]::ReadAllText($generatedPath)}
        if(SourceTokenInvalid $text){Fail 'GENERATED_SOURCE_TOKEN_INVALID' ([string]$generated.path)}
    }
    foreach($role in @($Receipt.roles)){
        $seenRoleInputs=@{};$committedInputCount=0;$generatedInputCount=0
        foreach($roleInput in @($role.compiler_inputs)){
            $classification=AssertCompilerInputBinding ([string]$role.role) $roleInput $canonicalInputs
            $inputPath=[string]$roleInput.path
            if($seenRoleInputs.ContainsKey($inputPath)){Fail 'COMPILER_INPUT_SET_MISMATCH' (([string]$role.role)+'/duplicate/'+$inputPath)}
            $seenRoleInputs[$inputPath]=$true
            if($classification-ceq'COMMITTED'){$committedInputCount++}elseif($classification-ceq'GENERATED'){$generatedInputCount++}
        }
        $inputPaths=@($role.compiler_inputs|ForEach-Object{[string]$_.path})
        $generatedInput=@($role.compiler_inputs|Where-Object{[string]$_.path-like'Generated/*'})
        if($generatedInput.Count-ne1-or$generatedInputCount-ne1-or$committedInputCount-ne$declaredSourcePaths.Count){Fail 'COMPILER_INPUT_SET_MISMATCH' ([string]$role.role)}
        $generatedForRole=@($Receipt.generated_sources|Where-Object{[string]$_.path-ceq[string]$generatedInput[0].path})
        if($generatedForRole.Count -ne 1 -or [string]$generatedForRole[0].raw_sha256-cne[string]$role.generated_source_sha256){Fail 'COMPILER_INPUT_SET_MISMATCH' ([string]$role.role)}
        $expectedInputs=@($declaredSourcePaths)+[string]$generatedForRole[0].path
        if(($inputPaths-join "`n") -cne ($expectedInputs-join "`n")){Fail 'COMPILER_INPUT_SET_MISMATCH' (([string]$role.role)+'/ordered-inputs')}
        foreach($phase in @('pass_a','pass_b')){
            $arguments=@($role.compiler_arguments.$phase)
            foreach($switch in $requiredSwitches){if($arguments -cnotcontains $switch){Fail 'COMPILER_ARGUMENT_VECTOR_MISMATCH' (([string]$role.role)+'/'+$phase+'/'+$switch)}}
            if(@($arguments|Where-Object{[string]$_ -like '/main:*'}).Count -ne 1 -or @($arguments|Where-Object{[string]$_ -like '/out:*'}).Count -ne 1 -or @($arguments|Where-Object{[string]$_ -like '/define:*'}).Count -ne 1){Fail 'COMPILER_ARGUMENT_VECTOR_MISMATCH' (([string]$role.role)+'/'+$phase+'/role-switches')}
            $sourceArguments=@($arguments|Where-Object{[string]$_ -notlike '/*'}|ForEach-Object{[IO.Path]::GetFullPath([string]$_)})
            $inputActual=@($role.compiler_inputs|ForEach-Object{if([string]$_.path -like 'Generated/*'){Join-Path $build ([string]$_.path).Replace('/','\')}else{Join-Path $repositoryRoot ([string]$_.path).Replace('/','\')}}|ForEach-Object{[IO.Path]::GetFullPath($_)})
            if((@($sourceArguments|Sort-Object)-join "`n") -cne (@($inputActual|Sort-Object)-join "`n")){Fail 'COMPILER_INPUT_SET_MISMATCH' (([string]$role.role)+'/'+$phase+'/arguments')}
            $expected=@($requiredSwitches)
            $expected+=('/main:'+[string]$role.main)
            $expected+=('/out:'+$(if($phase-ceq'pass_a'){[IO.Path]::GetFullPath([string]$role.pass_a_path)}else{[IO.Path]::GetFullPath([string]$role.pass_b_path)}))
            $expected+=('/define:'+[string]$role.define)
            foreach($reference in @($Receipt.framework_references)){$expected+=('/reference:'+[IO.Path]::GetFullPath([string]$reference.path))}
            $expected+=@($inputActual)
            if(($arguments-join "`n")-cne($expected-join "`n")){Fail 'COMPILER_ARGUMENT_VECTOR_MISMATCH' (([string]$role.role)+'/'+$phase+'/ordered')}
        }
        $invalidIdentities=@($role.embedded_identity.PSObject.Properties|Where-Object{ForbiddenIdentity $_.Value})
        if([string]$role.role -like 'PACKAGED_*' -and $invalidIdentities.Count -ne 0){Fail 'PACKAGED_TOOL_IDENTITY_INVALID' ([string]$role.role)}
        if($invalidIdentities.Count-ne 0){Fail 'EMBEDDED_IDENTITY_INVALID' (([string]$role.role)+'/'+[string]$invalidIdentities[0].Name)}
    }
    foreach($packaged in @($Receipt.target_packaged_executables)){
        $invalid=@($packaged.embedded_identity.PSObject.Properties|Where-Object{ForbiddenIdentity $_.Value})
        if($invalid.Count-ne0){Fail 'PACKAGED_TOOL_IDENTITY_INVALID' (([string]$packaged.path)+'/'+[string]$invalid[0].Name)}
    }
}

function InvokeNegativeCases([object]$Receipt,[object]$NegativeRegistry) {
    $negativeResults=[Collections.Generic.List[object]]::new()
    foreach($case in @($NegativeRegistry.cases)){
        $mutated=Clone $Receipt;$overrides=@{};$role=$mutated.roles[0]
        switch([string]$case.mutation){
            'OMIT_COMMITTED_COMPILER_INPUT'{$role.compiler_inputs=@($role.compiler_inputs|Select-Object -Skip 1)}
            'OMIT_GENERATED_COMPILER_INPUT'{$role.compiler_inputs=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})}
            'REMOVE_REQUIRED_COMPILER_ARGUMENT'{$role.compiler_arguments.pass_a=@($role.compiler_arguments.pass_a|Where-Object{[string]$_-cne'/warnaserror+'})}
            'ZERO_EMBEDDED_IDENTITY'{$role.embedded_identity.'R7BuildIdentity.SourceCommit'=('0'*40)}
            'DIAGNOSTIC_EMBEDDED_IDENTITY'{$role.embedded_identity.'R7BuildIdentity.IdentityBindingKind'='DEVELOPMENT'}
            'TOKEN_IN_NONCOMPILED_SOURCE_REGION'{$path=[string]$mutated.generated_sources[0].path;$overrides[$path]=([IO.File]::ReadAllText((Join-Path $build $path.Replace('/','\')))+"`r`n#if NEVER`r`n// UNIT2_GENERATED_FORBIDDEN`r`n#endif`r`n")}
            'PACKAGED_TOOL_DIAGNOSTIC_IDENTITY'{$role=@($mutated.roles|Where-Object{[string]$_.role-ceq'PACKAGED_ARTIFACT_TOOL'})[0];$role.embedded_identity.'R7BuildIdentity.IdentityBindingKind'='PLACEHOLDER'}
            'RECEIPT_SOURCE_NOT_IN_ARGUMENT_VECTOR'{$role.compiler_arguments.pass_a=@($role.compiler_arguments.pass_a|Where-Object{[string]$_-cne(Join-Path $repositoryRoot ([string]$mutated.source_files[0].path).Replace('/','\'))})}
            'ARGUMENT_SOURCE_NOT_IN_RECEIPT'{$role.compiler_arguments.pass_a+=('C:\Temp\unrecorded-input.cs')}
            'REORDER_COMPILER_ARGUMENTS'{$arguments=@($role.compiler_arguments.pass_a);$left=[Array]::IndexOf([string[]]$arguments,'/target:exe');$right=[Array]::IndexOf([string[]]$arguments,'/platform:x64');if($left-lt0-or$right-lt0){throw 'Negative reorder fixture invalid'};$value=$arguments[$left];$arguments[$left]=$arguments[$right];$arguments[$right]=$value;$role.compiler_arguments.pass_a=$arguments}
            'SUBSTITUTE_COMPILER_ARGUMENT'{$arguments=@($role.compiler_arguments.pass_a);$index=[Array]::IndexOf([string[]]$arguments,'/optimize+');if($index-lt0){throw 'Negative argument-substitution fixture invalid'};$arguments[$index]='/optimize-';$role.compiler_arguments.pass_a=$arguments}
            'DUPLICATE_COMPILER_ARGUMENT'{$arguments=[Collections.Generic.List[string]]::new();foreach($argument in @($role.compiler_arguments.pass_a)){$arguments.Add([string]$argument)};$index=$arguments.IndexOf('/checked+');if($index-lt0){throw 'Negative argument-duplicate fixture invalid'};$arguments.Insert($index+1,'/checked+');$role.compiler_arguments.pass_a=$arguments.ToArray()}
            'SUBSTITUTE_COMPILER_INPUT_RAW_SHA256'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord.raw_sha256=('a'*64-join'')}
            'SUBSTITUTE_COMPILER_INPUT_SIZE'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord.size=[long]$inputRecord.size+1}
            'SUBSTITUTE_COMMITTED_GIT_BLOB'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord.git_blob_identity=('b'*40-join'')}
            'SUBSTITUTE_COMPILER_INPUT_MODE'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord.mode='100755'}
            'SUBSTITUTE_GENERATED_INPUT_AUTHORITY'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-like'Generated/*'})[0];$inputRecord.generator.raw_sha256=('c'*64-join'')}
            default{throw "Unknown negative mutation: $($case.mutation)"}
        }
        $observed=$null
        try{ValidateModel $mutated $overrides;throw 'NEGATIVE_CASE_UNEXPECTED_PASS'}catch{if($_.Exception.Message-ceq'NEGATIVE_CASE_UNEXPECTED_PASS'){throw};$observed=($_.Exception.Message-split'\|')[0]}
        if($observed-cne[string]$case.expected_error){throw "Negative case wrong rejection: $($case.case_id) expected $($case.expected_error) observed $observed"}
        $negativeResults.Add([ordered]@{case_id=[string]$case.case_id;expected_error=[string]$case.expected_error;mutation=[string]$case.mutation;observed_error=$observed;status='PASS'})
    }
    return $negativeResults.ToArray()
}

if((Hash $PSCommandPath) -cne $ExpectedScriptSha256){throw 'Verifier script identity mismatch'}
foreach($required in @($receiptPath,$determinismPath,$manifestPath,$negativePath,$contractPath)){if(-not(Test-Path -LiteralPath $required -PathType Leaf)){throw "Required verification input missing: $required"}}
$receipt=ReadJson $receiptPath;$determinism=ReadJson $determinismPath;$manifest=ReadJson $manifestPath
if([string]$receipt.artifact_type -cne 'R7_UNIT2_UPGRADE_AUTHORITY_SOURCE_TO_BINARY_RECEIPT' -or [string]$receipt.schema_version -cne '2.0.0'){throw 'Source-to-binary receipt header invalid'}
if([string]$determinism.artifact_type -cne 'R7_UNIT2B_BUILD_DETERMINISM_RECEIPT' -or [string]$determinism.status -cne 'PASS'){throw 'Determinism receipt header invalid'}
if([string]$manifest.status -cne 'PASS' -or [string]$manifest.build_receipt_sha256 -cne (Hash $receiptPath) -or [string]$manifest.build_determinism_receipt_sha256 -cne (Hash $determinismPath)){throw 'Build manifest receipt binding invalid'}
if([string]$receipt.source_commit -cne $SourceCommit -or [string]$determinism.source_commit -cne $SourceCommit -or [string]$manifest.source_commit -cne $SourceCommit){throw 'Source commit binding invalid'}

$utility=ReadJson (Join-Path $packageRoot 'external_utility_registry.json');$gitRow=@($utility.utilities|Where-Object{[string]$_.role -ceq 'GIT_BUILD_AND_VERIFICATION'});if($gitRow.Count-ne 1){throw 'Governed Git row invalid'};$git=[string]$gitRow[0].path;$safe=$repositoryRoot.Replace('\','/')
$head=(& $git --no-pager -c "safe.directory=$safe" -C $repositoryRoot rev-parse HEAD).Trim();if($head-cne $SourceCommit){throw 'Verification HEAD mismatch'}
$status=@(& $git --no-pager -c "safe.directory=$safe" -C $repositoryRoot status --porcelain=v1 --untracked-files=all);if(-not $CandidateWorktree -and $status.Count-ne 0){throw 'Exact verification checkout is not clean'}
if(-not $CandidateWorktree){$tree=(& $git --no-pager -c "safe.directory=$safe" -C $repositoryRoot show -s --format=%T $SourceCommit).Trim();if([string]$receipt.source_tree-cne $tree -or [string]$determinism.source_tree-cne $tree){throw 'Exact source tree binding invalid'}}

$actualSources=@(Get-ChildItem -LiteralPath (Join-Path $packageRoot 'Source') -Filter '*.cs' -File|Sort-Object Name|ForEach-Object FullName)+$contractPath
$expectedSourceRows=@($actualSources|ForEach-Object{[ordered]@{git_blob_identity=(GitBlob $_);mode='100644';path=(Relative $repositoryRoot $_);raw_sha256=(Hash $_);size=(Get-Item -LiteralPath $_).Length}})
$receiptSourceRows=@($receipt.source_files)
if($expectedSourceRows.Count-ne $receiptSourceRows.Count){throw 'Exact source inventory count mismatch'}
for($index=0;$index-lt $expectedSourceRows.Count;$index++){foreach($field in @('git_blob_identity','mode','path','raw_sha256','size')){$expectedValue=[string](FieldValue $expectedSourceRows[$index] $field);$actualValue=[string](FieldValue $receiptSourceRows[$index] $field);if($expectedValue-cne$actualValue){throw "Exact source inventory mismatch: $($expectedSourceRows[$index].path)/$field"}}}

$generatedNames=@($receipt.generated_sources|ForEach-Object{[string]$_.path}|Sort-Object);$expectedGenerated=@('Generated/R7PackagedTools.g.cs','Generated/R7Unit2BuildBootstrap.g.cs','Generated/R7Unit2ClientShared.g.cs','Generated/R7Unit2Service.g.cs')
if(($generatedNames-join "`n")-cne($expectedGenerated-join "`n")){throw 'Generated source inventory mismatch'}
foreach($row in @($receipt.generated_sources)){$path=Join-Path $build ([string]$row.path).Replace('/','\');if((Hash $path)-cne[string]$row.raw_sha256 -or (Get-Item -LiteralPath $path).Length-ne[long]$row.size -or [string]$row.output_identity-cne[string]$row.raw_sha256){throw "Generated source identity mismatch: $($row.path)"};if(SourceTokenInvalid ([IO.File]::ReadAllText($path))){throw "Generated source token invalid: $($row.path)"}}

$roleNames=@($receipt.roles|ForEach-Object{[string]$_.role}|Sort-Object);if(($roleNames-join "`n")-cne(($requiredRoles|Sort-Object)-join "`n")){throw 'Binary role set mismatch'}
ValidateModel $receipt @{}
foreach($role in @($receipt.roles)){
    $passA=[IO.Path]::GetFullPath([string]$role.pass_a_path);$passB=[IO.Path]::GetFullPath([string]$role.pass_b_path)
    if(-not $passA.StartsWith($build.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)-or-not $passB.StartsWith($build.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){throw "Binary path escaped build root: $($role.role)"}
    if((Hash $passA)-cne[string]$role.pass_a_sha256 -or (Hash $passB)-cne[string]$role.pass_b_sha256 -or (Get-Item -LiteralPath $passA).Length-ne[long]$role.size -or $role.normalized_il_equal-ne$true){throw "Binary identity mismatch: $($role.role)"}
    $actualIdentity=ExtractIdentity $passA
    foreach($property in $role.embedded_identity.PSObject.Properties){if(-not $actualIdentity.Contains($property.Name)-or[string]$actualIdentity[$property.Name]-cne[string]$property.Value){throw "Extracted identity mismatch: $($role.role)/$($property.Name)"}}
}
$packagedArtifact=@($receipt.roles|Where-Object{[string]$_.role-ceq'PACKAGED_ARTIFACT_TOOL'})[0];$packagedProtected=@($receipt.roles|Where-Object{[string]$_.role-ceq'PACKAGED_PROTECTED_METADATA_TOOL'})[0]
if((Hash (Join-Path $build 'Tools\R7ArtifactTool.exe'))-cne[string]$packagedArtifact.pass_a_sha256 -or (Hash (Join-Path $build 'Tools\R7ProtectedMetadataTool.exe'))-cne[string]$packagedProtected.pass_a_sha256){throw 'Packaged tool copy identity mismatch'}
$targetRoot=Join-Path $build 'TargetStaging';$targetRows=@($receipt.target_packaged_executables|Sort-Object path);$actualTargetExecutables=@(Get-ChildItem -LiteralPath $targetRoot -Filter '*.exe' -File -Recurse|Sort-Object FullName)
if($targetRows.Count-ne$actualTargetExecutables.Count-or$targetRows.Count-eq0){throw 'Target packaged executable inventory mismatch'}
for($index=0;$index-lt$targetRows.Count;$index++){
    $actualPath='Staging/'+$actualTargetExecutables[$index].FullName.Substring($targetRoot.Length+1).Replace('\','/')
    if([string]$targetRows[$index].path-cne$actualPath-or[string]$targetRows[$index].raw_sha256-cne(Hash $actualTargetExecutables[$index].FullName)-or[long]$targetRows[$index].size-ne$actualTargetExecutables[$index].Length){throw "Target packaged executable identity mismatch: $actualPath"}
    $actualIdentity=ExtractPackagedIdentity $actualTargetExecutables[$index].FullName;if($actualIdentity.Count-eq0){throw "Target packaged executable omits identity: $actualPath"}
    foreach($property in $targetRows[$index].embedded_identity.PSObject.Properties){if(-not$actualIdentity.Contains($property.Name)-or[string]$actualIdentity[$property.Name]-cne[string]$property.Value-or(ForbiddenIdentity $property.Value)){throw "Target packaged executable embedded identity mismatch: $actualPath/$($property.Name)"}}
}
$detTargetRows=@($determinism.target_packaged_executables|Sort-Object path);if(($detTargetRows|ConvertTo-Json -Depth 20 -Compress)-cne($targetRows|ConvertTo-Json -Depth 20 -Compress)){throw 'Determinism target packaged executable inventory mismatch'}

$detRoles=@($determinism.role_determinism|Sort-Object role);$receiptRoles=@($receipt.roles|Sort-Object role);if($detRoles.Count-ne$receiptRoles.Count){throw 'Determinism role count mismatch'}
for($index=0;$index-lt$receiptRoles.Count;$index++){foreach($field in @('role','generated_source_sha256','normalized_il_sha256','pass_a_sha256','pass_b_sha256','size')){$detValue=[string](FieldValue $detRoles[$index] $field);$receiptValue=[string](FieldValue $receiptRoles[$index] $field);if($detValue-cne$receiptValue){throw "Determinism role mismatch: $($receiptRoles[$index].role)/$field"}};if((@($detRoles[$index].compiler_arguments.pass_a)-join "`n")-cne(@($receiptRoles[$index].compiler_arguments.pass_a)-join "`n")-or(@($detRoles[$index].compiler_arguments.pass_b)-join "`n")-cne(@($receiptRoles[$index].compiler_arguments.pass_b)-join "`n")){throw "Determinism compiler arguments mismatch: $($receiptRoles[$index].role)"}}

$manifestDeclared=@($manifest.files|Sort-Object path);$manifestActual=@(Get-ChildItem -LiteralPath $build -File -Recurse|Where-Object{$_.FullName-ne$manifestPath-and$_.FullName-notlike'*.raw'-and$_.FullName-notlike'*.raw.il'}|ForEach-Object{[ordered]@{path=$_.FullName.Substring($build.Length+1).Replace('\','/');raw_sha256=(Hash $_.FullName);size=$_.Length}})
$manifestActual=@($manifestActual|Sort-Object{[string](FieldValue $_ 'path')})
if($manifestDeclared.Count-ne$manifestActual.Count){throw 'Package manifest file count mismatch'}
for($index=0;$index-lt$manifestActual.Count;$index++){foreach($field in @('path','raw_sha256','size')){$declaredValue=[string](FieldValue $manifestDeclared[$index] $field);$actualValue=[string](FieldValue $manifestActual[$index] $field);if($declaredValue-cne$actualValue){throw "Package manifest mismatch: $($manifestActual[$index].path)/$field"}};if([string]$manifestActual[$index].path-match'(^|/)\.\.(/|$)'){throw 'Package manifest path escape'}}

$negativeRegistry=ReadJson $negativePath;$negativeResults=@(InvokeNegativeCases $receipt $negativeRegistry)

$result=[ordered]@{artifact_type='R7_UNIT2_BUILD_CLOSURE_VERIFICATION';build_manifest_sha256=(Hash $manifestPath);build_receipt_sha256=(Hash $receiptPath);determinism_receipt_sha256=(Hash $determinismPath);generated_source_count=$receipt.generated_sources.Count;negative_results=$negativeResults;negative_test_count=$negativeResults.Count;role_count=$receipt.roles.Count;schema_version='1.0.0';source_commit=$SourceCommit;source_identity_class=[string]$receipt.source_identity_class;source_tree=[string]$receipt.source_tree;status='PASS'}
if(Test-Path -LiteralPath $output){throw "Verification output exists: $output"};$parent=Split-Path -Parent $output;if(-not(Test-Path -LiteralPath $parent)){New-Item -ItemType Directory -Path $parent|Out-Null};[IO.File]::WriteAllText($output,($result|ConvertTo-Json -Depth 100),[Text.UTF8Encoding]::new($false))
[ordered]@{negative_test_count=$negativeResults.Count;output=$output;raw_sha256=(Hash $output);role_count=$receipt.roles.Count;status='PASS'}|ConvertTo-Json
