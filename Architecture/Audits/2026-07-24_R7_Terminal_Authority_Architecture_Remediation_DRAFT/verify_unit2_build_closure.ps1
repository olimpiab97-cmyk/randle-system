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
function BytesHash([byte[]]$Bytes) {
    $sha=[Security.Cryptography.SHA256]::Create()
    try{return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
}
function TextHash([string]$Value){return BytesHash ([Text.UTF8Encoding]::new($false).GetBytes($Value))}
function CrLfFixtureBytes([byte[]]$Bytes) {
    $stream=[IO.MemoryStream]::new();try{for($index=0;$index-lt$Bytes.Length;$index++){if($Bytes[$index]-eq10-and($index-eq0-or$Bytes[$index-1]-ne13)){$stream.WriteByte(13)};$stream.WriteByte($Bytes[$index])};return $stream.ToArray()}finally{$stream.Dispose()}
}
function UntrustedFixtureBlobIdentity([byte[]]$Bytes) {
    $header=[Text.Encoding]::ASCII.GetBytes(('blob '+$Bytes.Length+[char]0));$all=New-Object byte[] ($header.Length+$Bytes.Length);[Buffer]::BlockCopy($header,0,$all,0,$header.Length);[Buffer]::BlockCopy($Bytes,0,$all,$header.Length,$Bytes.Length);$sha=[Security.Cryptography.SHA1]::Create();try{return ([BitConverter]::ToString($sha.ComputeHash($all))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
}
function ReadJson([string]$Path) { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }
function Clone([object]$Value) { return ($Value | ConvertTo-Json -Depth 100 | ConvertFrom-Json) }
function Relative([string]$Base,[string]$Path) {
    $baseFull = [IO.Path]::GetFullPath($Base).TrimEnd('\') + '\'
    return [Uri]::UnescapeDataString(([Uri]$baseFull).MakeRelativeUri([Uri][IO.Path]::GetFullPath($Path)).ToString()).Replace('\','/')
}
function GitArgs([string[]]$Arguments) {
    $safe=$repositoryRoot.Replace('\','/');$result=@(& $git --no-pager -c "safe.directory=$safe" -c core.fsmonitor=false -c core.hooksPath=NUL -C $repositoryRoot @Arguments)
    if($LASTEXITCODE-ne0){Fail 'GIT_OBJECT_AUTHORITY_FAILURE' ($Arguments-join' ')}
    return $result
}
function GitBlobIdentity([byte[]]$Bytes) {
    $lengthText=$Bytes.Length.ToString([Globalization.CultureInfo]::InvariantCulture)
    $prefix=[Text.Encoding]::ASCII.GetBytes(('blob '+$lengthText+[char]0))
    $sha=[Security.Cryptography.SHA1]::Create()
    try{
        $stream=[IO.MemoryStream]::new()
        try{$stream.Write($prefix,0,$prefix.Length);$stream.Write($Bytes,0,$Bytes.Length);$stream.Position=0;return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-','').ToLowerInvariant()}finally{$stream.Dispose()}
    }finally{$sha.Dispose()}
}
function SafeGitBatchStderr([string]$Value) {
    if($null-eq$Value){return ''};$safe=($Value-replace'[\r\n\x00-\x1f]',' ').Trim();if($safe.Length-gt256){return $safe.Substring(0,256)};return $safe
}
function AssertGitBatchProcessResult([bool]$Exited,[int]$ExitCode,[string]$Stderr,[string]$Context) {
    if(-not$Exited-or$ExitCode-ne0){Fail 'GIT_BATCH_PROCESS_FAILURE' (('context={0};exited={1};exit_code={2};stderr={3}'-f$Context,$Exited,$ExitCode,(SafeGitBatchStderr $Stderr)))}
}
function ReadStrictGitBatchHeader([IO.Stream]$Stream,[int]$Index,[string]$RequestedOid) {
    $headerBytes=[Collections.Generic.List[byte]]::new();$maximumHeaderBytes=128
    while($true){
        $value=$Stream.ReadByte()
        if($value-lt0){Fail 'GIT_BATCH_HEADER_INVALID' (('index={0};requested={1};reason={2}'-f$Index,$RequestedOid,$(if($headerBytes.Count-eq0){'missing-header'}else{'partial-header'})))}
        if($value-eq10){break}
        if($value-eq13-or$value-eq0-or$value-gt127){Fail 'GIT_BATCH_HEADER_INVALID' (('index={0};requested={1};reason=forbidden-header-byte;byte={2}'-f$Index,$RequestedOid,$value))}
        if($headerBytes.Count-ge$maximumHeaderBytes){Fail 'GIT_BATCH_HEADER_INVALID' (('index={0};requested={1};reason=header-too-long'-f$Index,$RequestedOid))}
        $headerBytes.Add([byte]$value)
    }
    if($headerBytes.Count-eq0){Fail 'GIT_BATCH_HEADER_INVALID' (('index={0};requested={1};reason=empty-header'-f$Index,$RequestedOid))}
    $header=[Text.Encoding]::ASCII.GetString($headerBytes.ToArray())
    if($header-cnotmatch'^([0-9a-f]{40}) ([^ ]+) ([^ ]+)$'){Fail 'GIT_BATCH_HEADER_INVALID' (('index={0};requested={1};reason=grammar'-f$Index,$RequestedOid))}
    $observedOid=[string]$Matches[1];$objectType=[string]$Matches[2];$sizeText=[string]$Matches[3]
    if($objectType-cne'blob'){Fail 'GIT_BATCH_OBJECT_TYPE_MISMATCH' (('index={0};requested={1};observed={2};type={3}'-f$Index,$RequestedOid,$observedOid,$objectType))}
    if($sizeText-cnotmatch'^(0|[1-9][0-9]*)$'){Fail 'GIT_BATCH_DECLARED_SIZE_INVALID' (('index={0};requested={1};observed={2};size={3}'-f$Index,$RequestedOid,$observedOid,$sizeText))}
    $size=[uint64]0
    if(-not[uint64]::TryParse($sizeText,[Globalization.NumberStyles]::None,[Globalization.CultureInfo]::InvariantCulture,[ref]$size)-or$size-gt[uint64]67108864){Fail 'GIT_BATCH_DECLARED_SIZE_INVALID' (('index={0};requested={1};observed={2};size={3}'-f$Index,$RequestedOid,$observedOid,$sizeText))}
    if($observedOid-cne$RequestedOid){Fail 'GIT_BATCH_OBJECT_ORDER_MISMATCH' (('index={0};requested={1};observed={2}'-f$Index,$RequestedOid,$observedOid))}
    return [ordered]@{observed_oid=$observedOid;size=[long]$size}
}
function ReadAuthenticatedGitBatch([IO.Stream]$Stream,[object[]]$ExpectedObjects) {
    $results=[Collections.Generic.List[object]]::new()
    for($index=0;$index-lt$ExpectedObjects.Count;$index++){
        $expected=$ExpectedObjects[$index];$requestedOid=[string]$expected.oid
        if($requestedOid-cnotmatch'^[0-9a-f]{40}$'){Fail 'GIT_BATCH_OBJECT_ORDER_MISMATCH' (('index={0};requested={1};reason=invalid-request-oid'-f$index,$requestedOid))}
        $header=ReadStrictGitBatchHeader $Stream $index $requestedOid;$size=[int][long]$header.size;$payload=New-Object byte[] $size;$offset=0
        while($offset-lt$size){$read=$Stream.Read($payload,$offset,$size-$offset);if($read-le0){Fail 'GIT_BATCH_PAYLOAD_TRUNCATED' (('index={0};requested={1};declared={2};actual={3}'-f$index,$requestedOid,$size,$offset))};$offset+=$read}
        $delimiter=$Stream.ReadByte();if($delimiter-ne10){Fail 'GIT_BATCH_PAYLOAD_DELIMITER_INVALID' (('index={0};requested={1};observed={2}'-f$index,$requestedOid,$delimiter))}
        $computedOid=GitBlobIdentity $payload
        if($computedOid-cne[string]$header.observed_oid-or$computedOid-cne$requestedOid){Fail 'GIT_BATCH_BLOB_IDENTITY_MISMATCH' (('index={0};requested={1};observed={2};computed={3}'-f$index,$requestedOid,[string]$header.observed_oid,$computedOid))}
        $results.Add([ordered]@{bytes=$payload;computed_oid=$computedOid;path=[string]$expected.path;size=[long]$payload.Length})
    }
    $trailing=$Stream.ReadByte();if($trailing-ne-1){Fail 'GIT_BATCH_TRAILING_OUTPUT' (('index={0};observed_byte={1}'-f$ExpectedObjects.Count,$trailing))}
    return $results.ToArray()
}
function ReadGitBlobBytes([string]$Blob) {
    if($Blob-cnotmatch'^[0-9a-f]{40}$'){Fail 'GIT_OBJECT_AUTHORITY_FAILURE' 'invalid-blob-id'}
    if($null-ne(Get-Variable -Name gitBlobByteCache -Scope Script -ErrorAction SilentlyContinue)-and$script:gitBlobByteCache.ContainsKey($Blob)){return [byte[]]$script:gitBlobByteCache[$Blob]}
    $safe=$repositoryRoot.Replace('\','/');$quotedRepository='"'+$repositoryRoot.Replace('"','\"')+'"';$quotedSafe='"safe.directory='+$safe.Replace('"','\"')+'"'
    $psi=[Diagnostics.ProcessStartInfo]::new();$psi.FileName=$git;$psi.Arguments=('--no-pager -c '+$quotedSafe+' -c core.fsmonitor=false -c core.hooksPath=NUL -C '+$quotedRepository+' cat-file blob '+$Blob);$psi.UseShellExecute=$false;$psi.CreateNoWindow=$true;$psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
    $process=[Diagnostics.Process]::new();$process.StartInfo=$psi
    try{
        if(-not$process.Start()){Fail 'GIT_BATCH_PROCESS_FAILURE' 'context=cat-file;reason=start'}
        $stream=[IO.MemoryStream]::new();try{$copyTask=$process.StandardOutput.BaseStream.CopyToAsync($stream);$errorTask=$process.StandardError.ReadToEndAsync();$exited=$process.WaitForExit(30000);if(-not$exited){try{$process.Kill();$process.WaitForExit()}catch{};AssertGitBatchProcessResult $false -1 '' 'cat-file'};try{[void]$copyTask.GetAwaiter().GetResult()}catch{Fail 'GIT_BATCH_PROCESS_FAILURE' ('context=cat-file;reason=stdout-read;error='+$_.Exception.GetType().Name)};$errorText=$errorTask.GetAwaiter().GetResult();AssertGitBatchProcessResult $true $process.ExitCode $errorText 'cat-file';$bytes=$stream.ToArray();$computed=GitBlobIdentity $bytes;if($computed-cne$Blob){Fail 'GIT_BATCH_BLOB_IDENTITY_MISMATCH' ('index=0;requested='+$Blob+';observed=<direct>;computed='+$computed)};return $bytes}finally{$stream.Dispose()}
    }finally{$process.Dispose()}
}
function InitializeTreeAuthorityCache {
    if($null-eq(Get-Variable -Name treeAuthorityCacheKey -Scope Script -ErrorAction SilentlyContinue)){$script:treeAuthorityCacheKey='';$script:treeAuthorityCache=@{};$script:gitBlobByteCache=@{}}
    $cacheKey=$repositoryRoot+'|'+$SourceCommit;if($script:treeAuthorityCacheKey-ceq$cacheKey){return}
    $auditRoot=Join-Path $repositoryRoot $packageRelativeRoot.Replace('/','\');$paths=[Collections.Generic.List[string]]::new()
    foreach($path in @(Get-ChildItem -LiteralPath (Join-Path $auditRoot 'Source') -Filter '*.cs' -File|Sort-Object Name|ForEach-Object FullName)+@(Join-Path $auditRoot 'BuildInputs\R7BuildIdentityContract.cs')){$paths.Add((Relative $repositoryRoot $path))}
    $paths.Add($packageRelativeRoot+'/build_unit2_upgrade_authority.ps1');foreach($contract in @(ConfigurationContract)){if([string]$contract.class-ceq'COMMITTED'){$paths.Add([string]$contract.relative)}}
    $required=@($paths|Sort-Object -Unique);$rows=@(GitArgs (@('ls-tree','--full-tree',$SourceCommit,'--')+$required));$tree=@{}
    foreach($row in $rows){if([string]$row-notmatch'^(100644|100755) blob ([0-9a-f]{40})\t(.+)$'){Fail 'GIT_TREE_OBJECT_MISMATCH' 'unexpected-tree-row'};$tree[[string]$Matches[3]]=[ordered]@{blob=[string]$Matches[2];mode=[string]$Matches[1]}}
    foreach($path in $required){if(-not$tree.ContainsKey($path)){Fail 'GIT_TREE_OBJECT_MISMATCH' ($path+'/missing-or-nonblob')}}
    $safe=$repositoryRoot.Replace('\','/');$quotedRepository='"'+$repositoryRoot.Replace('"','\"')+'"';$quotedSafe='"safe.directory='+$safe.Replace('"','\"')+'"';$psi=[Diagnostics.ProcessStartInfo]::new();$psi.FileName=$git;$psi.Arguments=('--no-pager -c '+$quotedSafe+' -c core.fsmonitor=false -c core.hooksPath=NUL -C '+$quotedRepository+' cat-file --batch');$psi.UseShellExecute=$false;$psi.CreateNoWindow=$true;$psi.RedirectStandardInput=$true;$psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
    $process=[Diagnostics.Process]::new();$process.StartInfo=$psi;$authority=@{};$blobBytes=@{}
    try{
        if(-not$process.Start()){Fail 'GIT_BATCH_PROCESS_FAILURE' 'context=batch;reason=start'};$process.StandardInput.NewLine="`n";$expected=[Collections.Generic.List[object]]::new();foreach($path in $required){$blob=[string]$tree[$path].blob;$expected.Add([ordered]@{oid=$blob;path=$path});$process.StandardInput.WriteLine($blob)};$process.StandardInput.Close()
        $batchOutput=[IO.MemoryStream]::new();try{$copyTask=$process.StandardOutput.BaseStream.CopyToAsync($batchOutput);$errorTask=$process.StandardError.ReadToEndAsync();$exited=$process.WaitForExit(30000);if(-not$exited){try{$process.Kill();$process.WaitForExit()}catch{};AssertGitBatchProcessResult $false -1 '' 'batch'};try{[void]$copyTask.GetAwaiter().GetResult()}catch{Fail 'GIT_BATCH_PROCESS_FAILURE' ('context=batch;reason=stdout-read;error='+$_.Exception.GetType().Name)};$errorText=$errorTask.GetAwaiter().GetResult();AssertGitBatchProcessResult $true $process.ExitCode $errorText 'batch';$batchOutput.Position=0;$frames=@(ReadAuthenticatedGitBatch $batchOutput $expected.ToArray())}finally{$batchOutput.Dispose()}
        for($index=0;$index-lt$required.Count;$index++){$path=[string]$required[$index];$expectedBlob=[string]$tree[$path].blob;$bytes=[byte[]]$frames[$index].bytes;$authority[$path]=[ordered]@{git_blob_identity=$expectedBlob;mode=[string]$tree[$path].mode;path=$path;raw_sha256=(BytesHash $bytes);size=[long]$bytes.Length};$blobBytes[$expectedBlob]=$bytes}
    }finally{$process.Dispose()}
    $script:treeAuthorityCacheKey=$cacheKey;$script:treeAuthorityCache=$authority;$script:gitBlobByteCache=$blobBytes
}
function ExactTreeBlobAuthority([string]$RelativePath) {
    $path=AssertCanonicalInputPath $RelativePath 'git-tree';InitializeTreeAuthorityCache;if(-not$script:treeAuthorityCache.ContainsKey($path)){Fail 'GIT_TREE_OBJECT_MISMATCH' ($path+'/unauthorized')};return $script:treeAuthorityCache[$path]
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
function JsonKind([object]$Value) {
    if($null-eq$Value){return 'NULL'}
    if($Value-is[string]){return 'STRING'}
    if($Value-is[bool]){return 'BOOLEAN'}
    if($Value-is[byte]-or$Value-is[sbyte]-or$Value-is[int16]-or$Value-is[uint16]-or$Value-is[int32]-or$Value-is[uint32]-or$Value-is[int64]-or$Value-is[uint64]){return 'INTEGER'}
    if($Value-is[decimal]){if([decimal]::Truncate([decimal]$Value)-eq[decimal]$Value){return 'INTEGER'};return 'NUMBER_NONINTEGER'}
    if($Value-is[Array]){return 'ARRAY'}
    if($Value-is[Collections.IDictionary]-or$Value-is[PSCustomObject]){return 'OBJECT'}
    return 'OTHER'
}
function ExactJsonEqual([object]$Expected,[object]$Observed) {
    $expectedKind=JsonKind $Expected;$observedKind=JsonKind $Observed
    if($expectedKind-cne$observedKind){return $false}
    switch($expectedKind){
        'NULL'{return $true}
        'STRING'{return [string]$Expected-ceq[string]$Observed}
        'BOOLEAN'{return [bool]$Expected-eq[bool]$Observed}
        'INTEGER'{return [decimal]$Expected-eq[decimal]$Observed}
        'ARRAY'{
            $expectedItems=@($Expected);$observedItems=@($Observed);if($expectedItems.Count-ne$observedItems.Count){return $false}
            for($index=0;$index-lt$expectedItems.Count;$index++){if(-not(ExactJsonEqual $expectedItems[$index] $observedItems[$index])){return $false}}
            return $true
        }
        'OBJECT'{
            $expectedNames=@(FieldNames $Expected);$observedNames=@(FieldNames $Observed)
            if($expectedNames.Count-ne$observedNames.Count){return $false}
            foreach($name in $expectedNames){if($observedNames-cnotcontains$name-or-not(ExactJsonEqual (FieldValue $Expected $name) (FieldValue $Observed $name))){return $false}}
            return $true
        }
        default{return $false}
    }
}
function DiagnosticValue([object]$Value) {
    $kind=JsonKind $Value
    if($kind-ceq'NULL'){return 'NULL:<null>'}
    return ($kind+':'+($Value|ConvertTo-Json -Depth 20 -Compress))
}
function FailInputField([string]$Role,[string]$InputPath,[string]$Field,[object]$Expected,[object]$Observed) {
    Fail 'COMPILER_INPUT_IDENTITY_MISMATCH' (('role={0};input={1};field={2};expected={3};observed={4}' -f $Role,$InputPath,$Field,(DiagnosticValue $Expected),(DiagnosticValue $Observed)))
}
function FailInputType([string]$Role,[string]$InputPath,[string]$Field,[string]$ExpectedKind,[object]$Observed) {
    Fail 'COMPILER_INPUT_TYPE_MISMATCH' (('role={0};input={1};field={2};expected_type={3};observed={4}' -f $Role,$InputPath,$Field,$ExpectedKind,(DiagnosticValue $Observed)))
}
function AssertKind([string]$Role,[string]$InputPath,[string]$Field,[object]$Value,[string]$ExpectedKind) {
    if((JsonKind $Value)-cne$ExpectedKind){FailInputType $Role $InputPath $Field $ExpectedKind $Value}
}
function AssertSha256([string]$Role,[string]$InputPath,[string]$Field,[object]$Value) {
    AssertKind $Role $InputPath $Field $Value 'STRING';if([string]$Value-cnotmatch'^[0-9a-f]{64}$'){FailInputField $Role $InputPath $Field '<lowercase-sha256>' $Value}
}
function AssertGitBlob([string]$Role,[string]$InputPath,[string]$Field,[object]$Value) {
    AssertKind $Role $InputPath $Field $Value 'STRING';if([string]$Value-cnotmatch'^[0-9a-f]{40}$'){FailInputField $Role $InputPath $Field '<lowercase-git-blob>' $Value}
}
function AssertCanonicalInputPath([string]$Path,[string]$Context) {
    if([string]::IsNullOrWhiteSpace($Path)-or[IO.Path]::IsPathRooted($Path)){Fail 'COMPILER_INPUT_PATH_INVALID' ($Context+'/'+$Path)}
    $normalized=$Path.Replace('\','/')
    $segments=@($normalized.Split('/'))
    if($normalized-cne$Path-or@($segments|Where-Object{$_-ceq''-or$_-ceq'.'-or$_-ceq'..'}).Count-ne0){Fail 'COMPILER_INPUT_PATH_INVALID' ($Context+'/'+$Path)}
    return $normalized
}
function AssertExactObject([string]$Role,[string]$InputPath,[string]$Field,[object]$Expected,[object]$Observed) {
    if(-not(ExactJsonEqual $Expected $Observed)){FailInputField $Role $InputPath $Field $Expected $Observed}
}
function AssertCompilerInputSchema([string]$Role,[object]$InputRecord) {
    if((JsonKind $InputRecord)-cne'OBJECT'){FailInputType $Role '<unknown>' 'compiler_input' 'OBJECT' $InputRecord}
    $path=if(HasField $InputRecord 'path'){DiagnosticValue (FieldValue $InputRecord 'path')}else{'<missing>'}
    $required=@('generation_rule','generator','git_blob_identity','mode','path','raw_sha256','size')
    $observed=@(FieldNames $InputRecord)
    foreach($field in $required){if($observed-cnotcontains$field){Fail 'COMPILER_INPUT_SCHEMA_MISMATCH' (('role={0};input={1};missing={2}'-f$Role,$path,$field))}}
    foreach($field in $observed){if($required-cnotcontains$field){Fail 'COMPILER_INPUT_SCHEMA_MISMATCH' (('role={0};input={1};unknown={2}'-f$Role,$path,$field))}}
}
function Derive([string]$Domain,[string[]]$Values) {
    $builder=[Text.StringBuilder]::new();[void]$builder.Append($Domain.Length).Append(':').Append($Domain)
    foreach($value in $Values){$item=if($null-eq$value){''}else{[string]$value};[void]$builder.Append('|').Append($item.Length).Append(':').Append($item)}
    return TextHash $builder.ToString()
}
function MeasuredFileRow([string]$Path) {
    $full=[IO.Path]::GetFullPath($Path);if(-not(Test-Path -LiteralPath $full -PathType Leaf)){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' ($full+'/missing')}
    if(((Get-Item -LiteralPath $full -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)-ne0){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' ($full+'/reparse')}
    return [ordered]@{path=$full;raw_sha256=(Hash $full);size=[long](Get-Item -LiteralPath $full).Length}
}
function CommittedAuthorityRows([hashtable]$Overrides) {
    $auditRoot=Join-Path $repositoryRoot $packageRelativeRoot.Replace('/','\');$sourceRoot=Join-Path $auditRoot 'Source';$identityContract=Join-Path $auditRoot 'BuildInputs\R7BuildIdentityContract.cs'
    $paths=@(Get-ChildItem -LiteralPath $sourceRoot -Filter '*.cs' -File|Sort-Object Name|ForEach-Object FullName)+$identityContract
    return @($paths|ForEach-Object{
        $relative=Relative $repositoryRoot $_;$committed=ExactTreeBlobAuthority $relative
        $compilerSha=if($Overrides.ContainsKey('compiler_sha256:'+ $relative)){[string]$Overrides['compiler_sha256:'+ $relative]}else{Hash $_}
        $compilerSize=if($Overrides.ContainsKey('compiler_size:'+ $relative)){[long]$Overrides['compiler_size:'+ $relative]}else{[long](Get-Item -LiteralPath $_).Length}
        if($compilerSha-cne[string]$committed.raw_sha256-or$compilerSize-ne[long]$committed.size){Fail 'COMPILER_SOURCE_MATERIALIZATION_MISMATCH' ($relative+'/EXACT_GIT_BLOB_BYTES_REQUIRED')}
        $committed
    })
}
function GeneratedSourceContract {
    return @(
        [ordered]@{path='Generated/R7Unit2BuildBootstrap.g.cs';generation_rule='R7_UNIT2_BUILD_BOOTSTRAP_IDENTITY_V2';policy_input=$false;roles=@('BUILD_BOOTSTRAP_ARTIFACT_TOOL','BUILD_BOOTSTRAP_PROTECTED_METADATA_TOOL')},
        [ordered]@{path='Generated/R7Unit2ClientShared.g.cs';generation_rule='R7_UNIT2_CLIENT_SHARED_IDENTITY_V2';policy_input=$false;roles=@('UPGRADE_CLIENT','UPGRADE_PROTOCOL_PROBE','UPGRADE_PUBLIC_VERIFIER')},
        [ordered]@{path='Generated/R7Unit2Service.g.cs';generation_rule='R7_UNIT2_SERVICE_IDENTITY_V2';policy_input=$true;roles=@('UPGRADE_AUTHORITY')},
        [ordered]@{path='Generated/R7PackagedTools.g.cs';generation_rule='R7_UNIT2_PACKAGED_TOOLS_IDENTITY_V2';policy_input=$true;roles=@('PACKAGED_ARTIFACT_TOOL','PACKAGED_PROTECTED_METADATA_TOOL')}
    )
}
function GroundedGeneratorAuthority([hashtable]$Overrides) {
    $relative=$packageRelativeRoot+'/build_unit2_upgrade_authority.ps1';$path=Join-Path $repositoryRoot $relative.Replace('/','\')
    if(-not(Test-Path -LiteralPath $path -PathType Leaf)){Fail 'GENERATED_SOURCE_AUTHORITY_MISMATCH' ($relative+'/missing')}
    $committed=ExactTreeBlobAuthority $relative
    $materializedSha=if($Overrides.ContainsKey('generator_sha256')){[string]$Overrides.generator_sha256}else{Hash $path};$materializedSize=if($Overrides.ContainsKey('generator_size')){[long]$Overrides.generator_size}else{[long](Get-Item -LiteralPath $path).Length}
    if($materializedSha-cne[string]$committed.raw_sha256-or$materializedSize-ne[long]$committed.size){Fail 'GENERATOR_MATERIALIZATION_MISMATCH' ($relative+'/EXACT_GIT_BLOB_BYTES_REQUIRED')}
    return [ordered]@{git_blob_identity=$committed.git_blob_identity;path=$relative;raw_sha256=$committed.raw_sha256}
}
function ConfigurationContract {
    return @(
        [ordered]@{role='AUTHORITY_SOURCE_MANIFEST';class='COMMITTED';relative=$packageRelativeRoot+'/AuthoritySources/authority_source_manifest.json'},
        [ordered]@{role='BOOTSTRAP_RECORD';class='BOOTSTRAP';leaf='upgrade_authority_bootstrap_record.json'},
        [ordered]@{role='CASE_DEFINITIONS';class='COMMITTED';relative=$packageRelativeRoot+'/immutable_case_definitions.json'},
        [ordered]@{role='COVERAGE_PROOF';class='COMMITTED';relative=$packageRelativeRoot+'/exact_byte_coverage_proof.json'},
        [ordered]@{role='DEPENDENCY_MANIFEST';class='TARGET';suffix='Generated/dependency_manifest.json'},
        [ordered]@{role='EXPECTATIONS';class='COMMITTED';relative=$packageRelativeRoot+'/immutable_expectations.json'},
        [ordered]@{role='HISTORICAL_CLASSIFICATION_REGISTRY';class='COMMITTED';relative=$packageRelativeRoot+'/historical_classification_registry.json'},
        [ordered]@{role='NEGATIVE_CASE_REGISTRY';class='COMMITTED';relative=$packageRelativeRoot+'/unit2_build_closure_negative_cases.json'},
        [ordered]@{role='PREFLIGHT_HOST_STATE';class='PREFLIGHT';leaf='host-state.json'},
        [ordered]@{role='PRINCIPAL_REGISTRY';class='COMMITTED';relative=$packageRelativeRoot+'/service_principal_registry.json'},
        [ordered]@{role='REQUIREMENT_REGISTRY';class='COMMITTED';relative=$packageRelativeRoot+'/governed_requirement_registry.json'},
        [ordered]@{role='SCRIPT_REGISTRY';class='COMMITTED';relative=$packageRelativeRoot+'/governed_script_registry.json'},
        [ordered]@{role='TARGET_AUTHORITY_PACKAGE_MANIFEST';class='TARGET';suffix='Generated/authority_package_manifest.json'},
        [ordered]@{role='TARGET_BUILD_ORCHESTRATOR_RECEIPT';class='TARGET';suffix='Generated/build_orchestrator_receipt.json'},
        [ordered]@{role='TARGET_BUILD_RECEIPT';class='TARGET';suffix='Generated/build_receipt.json'},
        [ordered]@{role='TARGET_BUILD_SUMMARY';class='TARGET';suffix='build_summary.json'},
        [ordered]@{role='TARGET_POLICY';class='TARGET';suffix='Generated/terminal_authority_v4_policy.json'},
        [ordered]@{role='TARGET_TRANSITION_TEMPLATE';class='TARGET';suffix='Generated/transition_request_template.json'},
        [ordered]@{role='TERMINAL_KEY_METADATA';class='TARGET';suffix='Generated/terminal_key_file_metadata.json'},
        [ordered]@{role='UNIT2_AUTHORIZATION_SCOPE';class='COMMITTED';relative=$packageRelativeRoot+'/unit2_authorization_scope.json'},
        [ordered]@{role='UNIT2_COMPLETION_SCRIPT';class='COMMITTED';relative=$packageRelativeRoot+'/complete_unit2_upgrade_authority.ps1'},
        [ordered]@{role='UNIT2_STOPPED_INSTALL_CONTRACT';class='COMMITTED';relative=$packageRelativeRoot+'/unit2_stopped_install_contract.json'},
        [ordered]@{role='UPGRADE_KEY_METADATA';class='TARGET';suffix='Generated/upgrade_key_file_metadata.json'},
        [ordered]@{role='UPGRADE_PUBLIC_CERTIFICATE';class='BOOTSTRAP';leaf='upgrade_authority_public_from_store.cer'},
        [ordered]@{role='UTILITY_REGISTRY';class='COMMITTED';relative=$packageRelativeRoot+'/external_utility_registry.json'}
    )
}
function AssertConfigurationSchema([object]$Row,[string]$Context) {
    if((JsonKind $Row)-cne'OBJECT'){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' ($Context+'/not-object')};$required=@('path','raw_sha256','role','size');$names=@(FieldNames $Row)
    if($names.Count-ne$required.Count-or@($required|Where-Object{$names-cnotcontains$_}).Count-ne0){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' ($Context+'/schema')}
    AssertKind 'CONFIGURATION_AUTHORITY' $Context 'path' $Row.path 'STRING';AssertSha256 'CONFIGURATION_AUTHORITY' $Context 'raw_sha256' $Row.raw_sha256;AssertKind 'CONFIGURATION_AUTHORITY' $Context 'role' $Row.role 'STRING';AssertKind 'CONFIGURATION_AUTHORITY' $Context 'size' $Row.size 'INTEGER'
}
function GroundedConfigurationInventory([object]$Receipt) {
    if((JsonKind $Receipt.configuration_inputs)-cne'ARRAY'){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' 'inventory/not-array'}
    $contracts=@(ConfigurationContract);$observed=@($Receipt.configuration_inputs);if($observed.Count-ne$contracts.Count){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' 'inventory/count'}
    $summaryRows=@($observed|Where-Object{(JsonKind $_.role)-ceq'STRING'-and[string]$_.role-ceq'TARGET_BUILD_SUMMARY'});if($summaryRows.Count-ne1-or(JsonKind $summaryRows[0].path)-cne'STRING'){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' 'TARGET_BUILD_SUMMARY/locator'}
    $targetRoot=[IO.Path]::GetFullPath((Split-Path -Parent ([string]$summaryRows[0].path)));$temp=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')+'\';if(-not$targetRoot.StartsWith($temp,[StringComparison]::OrdinalIgnoreCase)){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' 'target-root/not-temp'}
    $bootstrapRows=@($observed|Where-Object{(JsonKind $_.role)-ceq'STRING'-and[string]$_.role-ceq'BOOTSTRAP_RECORD'});if($bootstrapRows.Count-ne1-or(JsonKind $bootstrapRows[0].path)-cne'STRING'){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' 'BOOTSTRAP_RECORD/locator'};$bootstrapRoot=[IO.Path]::GetFullPath((Split-Path -Parent ([string]$bootstrapRows[0].path)))
    $grounded=[Collections.Generic.List[object]]::new()
    for($index=0;$index-lt$contracts.Count;$index++){
        $contract=$contracts[$index];$row=$observed[$index];$role=[string]$contract.role;AssertConfigurationSchema $row $role
        if([string]$row.role-cne$role){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' ($role+'/order')}
        switch([string]$contract.class){
            'COMMITTED'{$tree=ExactTreeBlobAuthority ([string]$contract.relative);$expectedPath=[IO.Path]::GetFullPath((Join-Path $repositoryRoot ([string]$contract.relative).Replace('/','\')));$measured=MeasuredFileRow $expectedPath;if([string]$measured.raw_sha256-cne[string]$tree.raw_sha256-or[long]$measured.size-ne[long]$tree.size){Fail 'CONFIGURATION_INPUT_MATERIALIZATION_MISMATCH' ($role+'/EXACT_GIT_BLOB_BYTES_REQUIRED')}}
            'TARGET'{$expectedPath=[IO.Path]::GetFullPath((Join-Path $targetRoot ([string]$contract.suffix).Replace('/','\')));$measured=MeasuredFileRow $expectedPath}
            'BOOTSTRAP'{$expectedPath=[IO.Path]::GetFullPath((Join-Path $bootstrapRoot ([string]$contract.leaf)));$measured=MeasuredFileRow $expectedPath}
            'PREFLIGHT'{$actualPath=[IO.Path]::GetFullPath([string]$row.path);if([IO.Path]::GetFileName($actualPath)-cne[string]$contract.leaf-or-not$actualPath.StartsWith($temp,[StringComparison]::OrdinalIgnoreCase)){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' ($role+'/path')};$expectedPath=$actualPath;$measured=MeasuredFileRow $expectedPath}
            default{Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' ($role+'/classification')}
        }
        $expected=[ordered]@{path=$expectedPath;raw_sha256=$measured.raw_sha256;role=$role;size=$measured.size};if(-not(ExactJsonEqual $expected $row)){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' $role};$grounded.Add($expected)
    }
    $byRole=@{};foreach($row in $grounded){$byRole[[string]$row.role]=$row}
    if([string]$byRole.UPGRADE_PUBLIC_CERTIFICATE.raw_sha256-cne'2ef057a2c09d53da7096d92a09774b68986cf26c5d44000e1ec804d8ce837d7b'){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' 'UPGRADE_PUBLIC_CERTIFICATE/fixed-identity'}
    $summary=ReadJson ([string]$byRole.TARGET_BUILD_SUMMARY.path);if([string]$summary.source_commit-cne'd22610e96496f7a9209edff36442be843f06fed4'-or[string]$summary.source_tree-cne'8a627b54537e4c26835345907fc5181205ce496f'){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' 'TARGET_BUILD_SUMMARY/source'}
    $bootstrap=ReadJson ([string]$byRole.BOOTSTRAP_RECORD.path);if([string]$bootstrap.source_commit-cne'b07fd42a20ed612d53070aa1d1ae1bda6ace1e93'-or[string]$bootstrap.source_tree-cne'7d0d92000192b913f9ff3fba6e57ce7308d2f3be'-or[string]$bootstrap.public_certificate_sha256-cne[string]$byRole.UPGRADE_PUBLIC_CERTIFICATE.raw_sha256){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' 'BOOTSTRAP_RECORD/source'}
    $preflight=ReadJson ([string]$byRole.PREFLIGHT_HOST_STATE.path);if([string]$preflight.artifact_type-cne'R7_REMEDIATION_HOST_STATE_CAPTURE'-or[string]$preflight.phase-cne'PRECHANGE'-or[int64]$preflight.ledger_entry_file_count-ne678){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' 'PREFLIGHT_HOST_STATE/semantics'}
    return $grounded.ToArray()
}
function GroundedUtility([string]$Role,[object]$Registry) {
    $rows=@($Registry.utilities|Where-Object{[string]$_.role-ceq$Role});if($rows.Count-ne1){Fail 'BUILD_INPUT_CLOSURE_MISMATCH' ('utility/'+$Role+'/authority')};$row=$rows[0];$path=[IO.Path]::GetFullPath([string]$row.path)
    if(-not(Test-Path -LiteralPath $path -PathType Leaf)-or(Hash $path)-cne[string]$row.measurement.sha256-or[long](Get-Item -LiteralPath $path).Length-ne[long]$row.measurement.size){Fail 'BUILD_INPUT_CLOSURE_MISMATCH' ('utility/'+$Role+'/measurement')};return $row
}
function RecomputeBuildInputClosure([object[]]$CommittedRows,[object[]]$ConfigurationRows,[hashtable]$Overrides) {
    $sourceParts=@($CommittedRows|ForEach-Object{[string]$_.path+'|'+[string]$_.git_blob_identity+'|'+[string]$_.raw_sha256+'|'+[string]$_.size+'|'+[string]$_.mode})
    $configurationParts=@($ConfigurationRows|ForEach-Object{[string]$_.role+'|'+[string]$_.raw_sha256+'|'+[string]$_.size})
    $registry=ReadJson (Join-Path $repositoryRoot ($packageRelativeRoot+'/external_utility_registry.json').Replace('/','\'));$toolchainParts=[Collections.Generic.List[string]]::new()
    foreach($tool in @(@('CSC','CSC_COMPILER'),@('ILDASM','ILDASM_TOOL'),@('GIT','GIT_BUILD_AND_VERIFICATION'),@('POWERSHELL','POWERSHELL_ORCHESTRATOR'))){$row=GroundedUtility $tool[1] $registry;$toolchainParts.Add(([string]$tool[0]+'|'+[string]$row.measurement.sha256+'|'+[string]$row.measurement.size))}
    foreach($role in @('COMPILER_REFERENCE_mscorlib.dll','COMPILER_REFERENCE_System.dll','COMPILER_REFERENCE_System.Core.dll','COMPILER_REFERENCE_System.Security.dll','COMPILER_REFERENCE_System.ServiceProcess.dll')){$row=GroundedUtility $role $registry;$toolchainParts.Add('REFERENCE|'+[string]$row.measurement.sha256+'|'+[string]$row.measurement.size)}
    $roleDefinitions=@(
        @('BUILD_BOOTSTRAP_ARTIFACT_TOOL','RandleAI.R7Remediation.R7ArtifactToolProgram','UNIT2_BUILD_BOOTSTRAP_ARTIFACT_TOOL','R7ArtifactTool.build-bootstrap.exe','DISPOSABLE_BUILD_ONLY'),@('BUILD_BOOTSTRAP_PROTECTED_METADATA_TOOL','RandleAI.R7Remediation.R7ArtifactToolProgram','UNIT2_BUILD_BOOTSTRAP_PROTECTED_METADATA_TOOL','R7ProtectedMetadataTool.build-bootstrap.exe','DISPOSABLE_BUILD_ONLY'),@('UPGRADE_CLIENT','RandleAI.R7Remediation.R7Unit2UpgradeClientProgram','UNIT2_CLIENT','RandleTerminalUpgradeClient.exe','C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradeClient.exe'),@('UPGRADE_PUBLIC_VERIFIER','RandleAI.R7Remediation.R7Unit2UpgradePublicVerifierProgram','UNIT2_PUBLIC_VERIFIER','RandleTerminalUpgradePublicVerifier.exe','C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradePublicVerifier.exe'),@('UPGRADE_PROTOCOL_PROBE','RandleAI.R7Remediation.R7Unit2UpgradeProbeProgram','UNIT2_PROTOCOL_PROBE','RandleTerminalUpgradeProtocolProbe.exe','C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradeProtocolProbe.exe'),@('UPGRADE_AUTHORITY','RandleAI.R7Remediation.R7Unit2UpgradeServiceProgram','UNIT2_SERVICE','RandleTerminalUpgradeAuthority.exe','C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradeAuthority.exe'),@('PACKAGED_ARTIFACT_TOOL','RandleAI.R7Remediation.R7ArtifactToolProgram','UNIT2_PACKAGED_ARTIFACT_TOOL','R7ArtifactTool.exe','C:\ProgramData\RandleAI\TerminalUpgradeAuthority\BuildTools\R7ArtifactTool.exe'),@('PACKAGED_PROTECTED_METADATA_TOOL','RandleAI.R7Remediation.R7ArtifactToolProgram','UNIT2_PACKAGED_PROTECTED_METADATA_TOOL','R7ProtectedMetadataTool.exe','C:\ProgramData\RandleAI\TerminalUpgradeAuthority\BuildTools\R7ProtectedMetadataTool.exe'))
    $roleParts=@($roleDefinitions|ForEach-Object{$_[0]+'|'+$_[1]+'|'+$_[2]+'|'+$_[3]+'|'+$_[4]})
    $configByRole=@{};foreach($row in $ConfigurationRows){$configByRole[[string]$row.role]=$row};$template=ReadJson ([string]$configByRole.TARGET_TRANSITION_TEMPLATE.path);$targetManifest=ReadJson ([string]$configByRole.TARGET_AUTHORITY_PACKAGE_MANIFEST.path);$components=[Collections.Generic.List[object]]::new();$paths=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach($component in @($template.components)){$components.Add([ordered]@{final_path=[string]$component.final_path;role=[string]$component.role;sha256=[string]$component.sha256;staging_relative_path=[string]$component.staging_relative_path});[void]$paths.Add([string]$component.staging_relative_path)}
    $extra=0;foreach($file in @($targetManifest.files|Sort-Object staging_relative_path)){if($paths.Contains([string]$file.staging_relative_path)){continue};$components.Add([ordered]@{final_path=[string]$file.final_path;role=('PACKAGE_FILE_'+$extra.ToString('D4')+'_'+([string]$file.raw_sha256).Substring(0,16));sha256=[string]$file.raw_sha256;staging_relative_path=[string]$file.staging_relative_path});[void]$paths.Add([string]$file.staging_relative_path);$extra++}
    $componentParts=@($components|Sort-Object role|ForEach-Object{[string]$_.role+'|'+[string]$_.staging_relative_path+'|'+[string]$_.sha256+'|'+[string]$_.final_path})
    $closureInputs=@($sourceParts+$configurationParts+$toolchainParts.ToArray()+$requiredSwitches+$roleParts+$componentParts)
    if($Overrides.ContainsKey('closure_reorder')-and$closureInputs.Count-gt1){$value=$closureInputs[0];$closureInputs[0]=$closureInputs[1];$closureInputs[1]=$value}
    return Derive 'R7_UNIT2_BUILD_INPUT_CLOSURE_V2' $closureInputs
}
function GroundedPolicyAuthority([object]$Receipt,[string]$Closure,[hashtable]$Overrides) {
    $path=if($Overrides.ContainsKey('policy_path')){[string]$Overrides.policy_path}else{Join-Path $build 'Generated\unit2_upgrade_policy.json'}
    if(-not(Test-Path -LiteralPath $path -PathType Leaf)){Fail 'POLICY_INPUT_AUTHORITY_MISMATCH' 'artifact/missing'};$measured=MeasuredFileRow $path;$policy=ReadJson $path
    if([string]$policy.artifact_type-cne'R7_UNIT2_SEPARATE_UPGRADE_AUTHORITY_POLICY'-or[string]$policy.source_bindings.provisioning_commit-cne[string]$Receipt.source_commit-or[string]$policy.source_bindings.provisioning_tree-cne[string]$Receipt.source_tree-or[string]$policy.source_bindings.target_commit-cne'd22610e96496f7a9209edff36442be843f06fed4'-or[string]$policy.source_bindings.target_tree-cne'8a627b54537e4c26835345907fc5181205ce496f'){Fail 'POLICY_INPUT_AUTHORITY_MISMATCH' 'source-binding'}
    $manifest=ReadJson (Join-Path $build 'unit2_build_manifest.json');$installPath=Join-Path $build 'Install\unit2_upgrade_policy.json'
    if([string]$Receipt.policy_sha256-cne[string]$measured.raw_sha256-or[string]$manifest.policy_sha256-cne[string]$measured.raw_sha256-or-not(Test-Path -LiteralPath $installPath -PathType Leaf)-or(Hash $installPath)-cne[string]$measured.raw_sha256-or[long](Get-Item -LiteralPath $installPath).Length-ne[long]$measured.size){Fail 'POLICY_INPUT_AUTHORITY_MISMATCH' 'receipt/hash'}
    return [ordered]@{path=$measured.path;raw_sha256=$measured.raw_sha256;size=$measured.size}
}
function ExpectedGeneratedSourceInputs([object[]]$ConfigurationRows,[object[]]$CommittedRows,[object]$Generator,[string]$Closure,[object]$Policy,[bool]$PolicyInput) {
    $inputs=[Collections.Generic.List[object]]::new()
    foreach($row in $ConfigurationRows){
        $inputs.Add([ordered]@{identity=[string]$row.raw_sha256;role=[string]$row.role})
    }
    foreach($row in $CommittedRows){$inputs.Add([ordered]@{identity=[string]$row.raw_sha256;role=('COMPILER_SOURCE:'+[string]$row.path)})}
    $inputs.Add([ordered]@{identity=$Closure;role='BUILD_INPUT_CLOSURE'});$inputs.Add([ordered]@{identity=[string]$Generator.raw_sha256;role='GENERATOR_SCRIPT'})
    if($PolicyInput){$inputs.Add([ordered]@{identity=[string]$Policy.raw_sha256;role='COMPLETED_UNIT2_POLICY'})}
    return $inputs.ToArray()
}
function AssertSourceAuthority([object]$Observed,[object]$Expected,[string]$Context) {
    if((JsonKind $Observed)-cne'OBJECT'){Fail 'COMMITTED_SOURCE_AUTHORITY_MISMATCH' ($Context+'/not-object')}
    $fields=@('git_blob_identity','mode','path','raw_sha256','size');$names=@(FieldNames $Observed)
    if($names.Count-ne$fields.Count-or@($fields|Where-Object{$names-cnotcontains$_}).Count-ne0){Fail 'COMMITTED_SOURCE_AUTHORITY_MISMATCH' ($Context+'/schema')}
    AssertGitBlob 'COMMITTED_AUTHORITY' $Context 'git_blob_identity' $Observed.git_blob_identity;AssertKind 'COMMITTED_AUTHORITY' $Context 'mode' $Observed.mode 'STRING';AssertKind 'COMMITTED_AUTHORITY' $Context 'path' $Observed.path 'STRING';AssertSha256 'COMMITTED_AUTHORITY' $Context 'raw_sha256' $Observed.raw_sha256;AssertKind 'COMMITTED_AUTHORITY' $Context 'size' $Observed.size 'INTEGER'
    if(-not(ExactJsonEqual $Expected $Observed)){Fail 'COMMITTED_SOURCE_AUTHORITY_MISMATCH' $Context}
}
function AssertGeneratedOutputAuthority([string]$Path,[string]$Closure,[object]$Policy,[bool]$PolicyInput,[string]$SourceCommitValue,[string]$SourceTreeValue) {
    $text=[IO.File]::ReadAllText($Path)
    foreach($binding in @([ordered]@{field='BuildInputClosureSha256';value=$Closure},[ordered]@{field='SourceCommit';value=$SourceCommitValue},[ordered]@{field='SourceTree';value=$SourceTreeValue})){
        $matches=[regex]::Matches($text,('internal const string '+[regex]::Escape([string]$binding.field)+' = "([0-9a-f]+)";'))
        if($matches.Count-eq0-or@($matches|Where-Object{$_.Groups[1].Value-cne[string]$binding.value}).Count-ne0){Fail 'GENERATED_OUTPUT_AUTHORITY_MISMATCH' ((Split-Path -Leaf $Path)+'/'+[string]$binding.field)}
    }
    if($PolicyInput){foreach($field in @('UpgradePolicySha256','PolicySha256')){$matches=[regex]::Matches($text,('internal const string '+$field+' = "([0-9a-f]{64})";'));if($matches.Count-eq0-or@($matches|Where-Object{$_.Groups[1].Value-cne[string]$Policy.raw_sha256}).Count-ne0){Fail 'GENERATED_OUTPUT_AUTHORITY_MISMATCH' ((Split-Path -Leaf $Path)+'/'+$field)}}}
}
function CanonicalCompilerInputIndex([object]$Receipt,[object]$Determinism,[hashtable]$Overrides) {
    $index=@{}
    $committed=@(CommittedAuthorityRows $Overrides);$observedSources=@($Receipt.source_files)
    if((JsonKind $Receipt.source_files)-cne'ARRAY'-or$observedSources.Count-ne$committed.Count){Fail 'COMMITTED_SOURCE_AUTHORITY_MISMATCH' 'inventory'}
    for($sourceIndex=0;$sourceIndex-lt$committed.Count;$sourceIndex++){
        AssertSourceAuthority $observedSources[$sourceIndex] $committed[$sourceIndex] ([string]$committed[$sourceIndex].path);$source=$committed[$sourceIndex]
        $path=AssertCanonicalInputPath ([string]$source.path) 'committed-authority'
        if($index.ContainsKey($path)){Fail 'COMPILER_INPUT_AUTHORITY_AMBIGUOUS' $path}
        $index[$path]=[ordered]@{classification='COMMITTED';record=[ordered]@{generation_rule=$null;generator=$null;git_blob_identity=$source.git_blob_identity;mode=$source.mode;path=$path;raw_sha256=$source.raw_sha256;size=$source.size}}
    }
    $configuration=@(GroundedConfigurationInventory $Receipt);$closure=RecomputeBuildInputClosure $committed $configuration $Overrides
    if([string]$Receipt.build_input_closure_sha256-cne$closure-or[string]$Determinism.build_input_closure_sha256-cne$closure){Fail 'BUILD_INPUT_CLOSURE_MISMATCH' ('expected='+$closure+';receipt='+[string]$Receipt.build_input_closure_sha256+';determinism='+[string]$Determinism.build_input_closure_sha256)}
    $policy=GroundedPolicyAuthority $Receipt $closure $Overrides;$generator=GroundedGeneratorAuthority $Overrides;$contracts=@(GeneratedSourceContract);$observedGenerated=@($Receipt.generated_sources)
    if((JsonKind $Receipt.generated_sources)-cne'ARRAY'-or$observedGenerated.Count-ne$contracts.Count){Fail 'GENERATED_SOURCE_AUTHORITY_MISMATCH' 'inventory'}
    for($generatedIndex=0;$generatedIndex-lt$contracts.Count;$generatedIndex++){
        $contract=$contracts[$generatedIndex];$generated=$observedGenerated[$generatedIndex];$path=[string]$contract.path;$actualPath=Join-Path $build $path.Replace('/','\')
        if(-not(Test-Path -LiteralPath $actualPath -PathType Leaf)){Fail 'GENERATED_SOURCE_AUTHORITY_MISMATCH' ($path+'/missing-output')}
        AssertGeneratedOutputAuthority $actualPath $closure $policy ([bool]$contract.policy_input) ([string]$Receipt.source_commit) ([string]$Receipt.source_tree)
        $expected=[ordered]@{generation_rule=[string]$contract.generation_rule;generator=$generator;output_identity=(Hash $actualPath);path=$path;raw_sha256=(Hash $actualPath);size=[long](Get-Item -LiteralPath $actualPath).Length;source_inputs=(ExpectedGeneratedSourceInputs $configuration $committed $generator $closure $policy ([bool]$contract.policy_input))}
        if((JsonKind $generated)-cne'OBJECT'-or-not(ExactJsonEqual $expected $generated)){Fail 'GENERATED_SOURCE_AUTHORITY_MISMATCH' $path}
        $path=AssertCanonicalInputPath $path 'generated-authority'
        if($index.ContainsKey($path)){Fail 'COMPILER_INPUT_AUTHORITY_AMBIGUOUS' $path}
        $index[$path]=[ordered]@{classification='GENERATED';record=[ordered]@{generation_rule=$expected.generation_rule;generator=$generator;git_blob_identity=$null;mode=$null;path=$path;raw_sha256=$expected.raw_sha256;size=$expected.size}}
    }
    return [ordered]@{build_input_closure_sha256=$closure;configuration_inputs=$configuration;index=$index;policy=$policy}
}
function AssertCompilerInputBinding([string]$Role,[object]$InputRecord,[hashtable]$CanonicalIndex) {
    AssertCompilerInputSchema $Role $InputRecord
    AssertKind $Role '<unknown>' 'path' (FieldValue $InputRecord 'path') 'STRING';$path=AssertCanonicalInputPath ([string]$InputRecord.path) ($Role+'/role-input')
    if(-not$CanonicalIndex.ContainsKey($path)){Fail 'COMPILER_INPUT_AUTHORITY_MISSING' ($Role+'/'+$path)}
    $authority=$CanonicalIndex[$path];$canonical=$authority.record;$classification=[string]$authority.classification
    AssertSha256 $Role $path 'raw_sha256' $InputRecord.raw_sha256;AssertKind $Role $path 'size' $InputRecord.size 'INTEGER'
    if([decimal]$InputRecord.size-lt0-or[decimal]$InputRecord.size-gt[decimal][long]::MaxValue){FailInputField $Role $path 'size' '<integer-0-through-int64-max>' $InputRecord.size}
    if($classification-ceq'COMMITTED'){
        AssertGitBlob $Role $path 'git_blob_identity' $InputRecord.git_blob_identity;AssertKind $Role $path 'mode' $InputRecord.mode 'STRING';AssertKind $Role $path 'generation_rule' $InputRecord.generation_rule 'NULL';AssertKind $Role $path 'generator' $InputRecord.generator 'NULL'
    }else{
        AssertKind $Role $path 'git_blob_identity' $InputRecord.git_blob_identity 'NULL';AssertKind $Role $path 'mode' $InputRecord.mode 'NULL';AssertKind $Role $path 'generation_rule' $InputRecord.generation_rule 'STRING';AssertKind $Role $path 'generator' $InputRecord.generator 'OBJECT'
    }
    foreach($field in @('generation_rule','generator','git_blob_identity','mode','path','raw_sha256','size')){if(-not(ExactJsonEqual (FieldValue $canonical $field) (FieldValue $InputRecord $field))){FailInputField $Role $path $field (FieldValue $canonical $field) (FieldValue $InputRecord $field)}}
    return $classification
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
function AssertStringArray([string]$Code,[string]$Context,[object]$Value) {
    if((JsonKind $Value)-cne'ARRAY'-or@($Value|Where-Object{(JsonKind $_)-cne'STRING'}).Count-ne0){Fail $Code ($Context+'/string-array')}
}
function AssertDeterminismCompilerInputs([object]$Receipt,[object]$Determinism,[hashtable]$CanonicalInputs) {
    if((JsonKind $Determinism.role_determinism)-cne'ARRAY'){Fail 'DETERMINISM_COMPILER_INPUT_MISMATCH' 'roles/not-array'}
    $receiptRoles=@($Receipt.roles);$determinismRoles=@($Determinism.role_determinism)
    if($receiptRoles.Count-ne$determinismRoles.Count){Fail 'DETERMINISM_COMPILER_INPUT_MISMATCH' 'role-count'}
    foreach($receiptRole in $receiptRoles){
        $roleName=[string]$receiptRole.role;$matches=@($determinismRoles|Where-Object{(JsonKind $_.role)-ceq'STRING'-and[string]$_.role-ceq$roleName})
        if($matches.Count-ne1){Fail 'DETERMINISM_COMPILER_INPUT_MISMATCH' ($roleName+'/role-authority')};$detRole=$matches[0]
        if((JsonKind $detRole.compiler_inputs)-cne'ARRAY'){Fail 'DETERMINISM_COMPILER_INPUT_MISMATCH' ($roleName+'/inputs-not-array')}
        $expectedInputs=@($receiptRole.compiler_inputs);$observedInputs=@($detRole.compiler_inputs)
        if($expectedInputs.Count-ne$observedInputs.Count){Fail 'DETERMINISM_COMPILER_INPUT_MISMATCH' ($roleName+'/input-count')}
        for($inputIndex=0;$inputIndex-lt$expectedInputs.Count;$inputIndex++){
            [void](AssertCompilerInputBinding ('DETERMINISM:'+$roleName) $observedInputs[$inputIndex] $CanonicalInputs)
            if(-not(ExactJsonEqual $expectedInputs[$inputIndex] $observedInputs[$inputIndex])){Fail 'DETERMINISM_COMPILER_INPUT_MISMATCH' ($roleName+'/input/'+$inputIndex)}
        }
        AssertStringArray 'DETERMINISM_COMPILER_ARGUMENT_MISMATCH' ($roleName+'/pass_a') $detRole.compiler_arguments.pass_a;AssertStringArray 'DETERMINISM_COMPILER_ARGUMENT_MISMATCH' ($roleName+'/pass_b') $detRole.compiler_arguments.pass_b
        if(-not(ExactJsonEqual $receiptRole.compiler_arguments.pass_a $detRole.compiler_arguments.pass_a)-or-not(ExactJsonEqual $receiptRole.compiler_arguments.pass_b $detRole.compiler_arguments.pass_b)){Fail 'DETERMINISM_COMPILER_ARGUMENT_MISMATCH' $roleName}
    }
}
function ValidateModel([object]$Receipt,[object]$Determinism,[hashtable]$GeneratedTextOverrides,[hashtable]$ProvenanceOverrides=@{}) {
    $actualTree=[string](@(GitArgs @('show','-s','--format=%T',$SourceCommit))[0])
    if([string]$Receipt.source_commit-cne$SourceCommit-or[string]$Determinism.source_commit-cne$SourceCommit-or[string]$Receipt.source_tree-cne$actualTree-or[string]$Determinism.source_tree-cne$actualTree){Fail 'SOURCE_COMMIT_TREE_AUTHORITY_MISMATCH' 'receipt-or-determinism'}
    $authority=CanonicalCompilerInputIndex $Receipt $Determinism $ProvenanceOverrides;$canonicalInputs=$authority.index
    $declaredSourcePaths=@($Receipt.source_files|ForEach-Object{[string]$_.path})
    foreach($generated in @($Receipt.generated_sources)){
        $generatedPath=Join-Path $build ([string]$generated.path).Replace('/','\')
        $text=if($GeneratedTextOverrides.ContainsKey([string]$generated.path)){[string]$GeneratedTextOverrides[[string]$generated.path]}else{[IO.File]::ReadAllText($generatedPath)}
        if(SourceTokenInvalid $text){Fail 'GENERATED_SOURCE_TOKEN_INVALID' ([string]$generated.path)}
    }
    if((JsonKind $Receipt.roles)-cne'ARRAY'){Fail 'COMPILER_INPUT_SET_MISMATCH' 'roles-not-array'}
    $roleNames=@($Receipt.roles|ForEach-Object{if((JsonKind $_.role)-cne'STRING'){Fail 'COMPILER_INPUT_SET_MISMATCH' 'role-name-type'};[string]$_.role})
    if($roleNames.Count-ne$requiredRoles.Count-or@($roleNames|Sort-Object -Unique).Count-ne$requiredRoles.Count-or(@($roleNames|Sort-Object)-join"`n")-cne(@($requiredRoles|Sort-Object)-join"`n")){Fail 'COMPILER_INPUT_SET_MISMATCH' 'role-authority'}
    $roleGeneratedMap=@{};foreach($contract in @(GeneratedSourceContract)){foreach($allowedRole in @($contract.roles)){$roleGeneratedMap[[string]$allowedRole]=[string]$contract.path}}
    foreach($role in @($Receipt.roles)){
        if((JsonKind $role.compiler_inputs)-cne'ARRAY'){Fail 'COMPILER_INPUT_SET_MISMATCH' (([string]$role.role)+'/inputs-not-array')}
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
        $expectedGeneratedPath=[string]$roleGeneratedMap[[string]$role.role];if([string]$generatedInput[0].path-cne$expectedGeneratedPath){Fail 'ROLE_GENERATED_SOURCE_MISMATCH' (([string]$role.role)+'/'+[string]$generatedInput[0].path+'/'+$expectedGeneratedPath)}
        $generatedForRole=@($Receipt.generated_sources|Where-Object{[string]$_.path-ceq[string]$generatedInput[0].path})
        if($generatedForRole.Count -ne 1 -or [string]$generatedForRole[0].raw_sha256-cne[string]$role.generated_source_sha256){Fail 'COMPILER_INPUT_SET_MISMATCH' ([string]$role.role)}
        $expectedInputs=@($declaredSourcePaths)+[string]$generatedForRole[0].path
        if(($inputPaths-join "`n") -cne ($expectedInputs-join "`n")){Fail 'COMPILER_INPUT_SET_MISMATCH' (([string]$role.role)+'/ordered-inputs')}
        foreach($phase in @('pass_a','pass_b')){
            $arguments=@($role.compiler_arguments.$phase)
            AssertStringArray 'COMPILER_ARGUMENT_VECTOR_MISMATCH' (([string]$role.role)+'/'+$phase) $role.compiler_arguments.$phase
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
    AssertDeterminismCompilerInputs $Receipt $Determinism $canonicalInputs
}

function JoinFixtureBytes([object[]]$Parts) {
    $stream=[IO.MemoryStream]::new()
    try{foreach($part in $Parts){if($null-ne$part){$bytes=[byte[]]$part;$stream.Write($bytes,0,$bytes.Length)}};return $stream.ToArray()}finally{$stream.Dispose()}
}
function AsciiFixtureBytes([string]$Value){return [Text.Encoding]::ASCII.GetBytes($Value)}
function GitBatchFixtureFrame([string]$Header,[byte[]]$Payload,[byte[]]$HeaderDelimiter,[byte[]]$PayloadDelimiter) {
    return JoinFixtureBytes @((AsciiFixtureBytes $Header),$HeaderDelimiter,$Payload,$PayloadDelimiter)
}
function InvokeGitBatchParserFixture([string]$Mutation) {
    $paths=@(($packageRelativeRoot+'/Source/R7AdversarialHarness.cs'),($packageRelativeRoot+'/Source/R7ArtifactTool.cs'));$descriptors=[Collections.Generic.List[object]]::new();$payloads=[Collections.Generic.List[byte[]]]::new()
    foreach($path in $paths){$authority=ExactTreeBlobAuthority $path;$descriptors.Add([ordered]@{oid=[string]$authority.git_blob_identity;path=$path});$payloads.Add([byte[]](ReadGitBlobBytes ([string]$authority.git_blob_identity)))}
    $d0=$descriptors[0];$d1=$descriptors[1];$p0=[byte[]]$payloads[0];$p1=[byte[]]$payloads[1];$lf=[byte[]](10);$crlf=[byte[]](13,10);$none=[byte[]]@()
    $h0=[string]$d0.oid+' blob '+$p0.Length.ToString([Globalization.CultureInfo]::InvariantCulture);$h1=[string]$d1.oid+' blob '+$p1.Length.ToString([Globalization.CultureInfo]::InvariantCulture)
    $expected=@($d0);$streamBytes=$null;$runProcessCheck=$false
    switch($Mutation){
        'VALID'{$streamBytes=GitBatchFixtureFrame $h0 $p0 $lf $lf}
        'BATCH_HEADER_EMBEDDED_CR'{$header=[string]$d0.oid.Substring(0,8)+[char]13+[string]$d0.oid.Substring(8)+' blob '+$p0.Length;$streamBytes=GitBatchFixtureFrame $header $p0 $lf $lf}
        'BATCH_HEADER_CRLF_TERMINATOR'{$streamBytes=GitBatchFixtureFrame $h0 $p0 $crlf $lf}
        'BATCH_HEADER_UPPERCASE_OID'{$streamBytes=GitBatchFixtureFrame ([string]$d0.oid.ToUpperInvariant()+' blob '+$p0.Length) $p0 $lf $lf}
        'BATCH_HEADER_SHORT_OID'{$streamBytes=GitBatchFixtureFrame ([string]$d0.oid.Substring(1)+' blob '+$p0.Length) $p0 $lf $lf}
        'BATCH_HEADER_LONG_OID'{$streamBytes=GitBatchFixtureFrame ('0'+[string]$d0.oid+' blob '+$p0.Length) $p0 $lf $lf}
        'BATCH_HEADER_NONHEX_OID'{$streamBytes=GitBatchFixtureFrame ('g'+[string]$d0.oid.Substring(1)+' blob '+$p0.Length) $p0 $lf $lf}
        'BATCH_PAYLOAD_FROM_OTHER_BLOB'{$streamBytes=GitBatchFixtureFrame ([string]$d0.oid+' blob '+$p1.Length) $p1 $lf $lf}
        'BATCH_FALSE_HEADER_OID_CORRECT_PAYLOAD'{$streamBytes=GitBatchFixtureFrame ([string]$d1.oid+' blob '+$p0.Length) $p0 $lf $lf}
        'BATCH_ARBITRARY_PAYLOAD'{$payload=[byte[]](1,2,3,4,5,6,7);$streamBytes=GitBatchFixtureFrame ([string]$d0.oid+' blob '+$payload.Length) $payload $lf $lf}
        'BATCH_DECLARED_SIZE_INCORRECT'{$payload=JoinFixtureBytes @($p0,[byte[]](0));$streamBytes=GitBatchFixtureFrame ([string]$d0.oid+' blob '+$payload.Length) $payload $lf $lf}
        'BATCH_DECLARED_SIZE_SMALLER'{$streamBytes=GitBatchFixtureFrame ([string]$d0.oid+' blob '+($p0.Length-1)) $p0 $lf $lf}
        'BATCH_DECLARED_SIZE_LARGER'{$streamBytes=GitBatchFixtureFrame ([string]$d0.oid+' blob '+($p0.Length+2)) $p0 $lf $lf}
        'BATCH_PAYLOAD_TRUNCATED'{$truncated=New-Object byte[] ($p0.Length-1);[Buffer]::BlockCopy($p0,0,$truncated,0,$truncated.Length);$streamBytes=GitBatchFixtureFrame $h0 $truncated $lf $none}
        'BATCH_PAYLOAD_DELIMITER_MISSING'{$streamBytes=GitBatchFixtureFrame $h0 $p0 $lf $none}
        'BATCH_PAYLOAD_DELIMITER_CRLF'{$streamBytes=GitBatchFixtureFrame $h0 $p0 $lf $crlf}
        'BATCH_OBJECT_TYPE_WRONG'{$streamBytes=GitBatchFixtureFrame ([string]$d0.oid+' tree '+$p0.Length) $p0 $lf $lf}
        'BATCH_RESPONSE_REORDERED'{$expected=@($d0,$d1);$streamBytes=JoinFixtureBytes @((GitBatchFixtureFrame $h1 $p1 $lf $lf),(GitBatchFixtureFrame $h0 $p0 $lf $lf))}
        'BATCH_RESPONSE_DUPLICATE'{$expected=@($d0,$d1);$streamBytes=JoinFixtureBytes @((GitBatchFixtureFrame $h0 $p0 $lf $lf),(GitBatchFixtureFrame $h0 $p0 $lf $lf))}
        'BATCH_RESPONSE_MISSING'{$expected=@($d0,$d1);$streamBytes=GitBatchFixtureFrame $h0 $p0 $lf $lf}
        'BATCH_TRAILING_JUNK'{$streamBytes=JoinFixtureBytes @((GitBatchFixtureFrame $h0 $p0 $lf $lf),(AsciiFixtureBytes 'JUNK'))}
        'BATCH_TRAILING_LF'{$streamBytes=JoinFixtureBytes @((GitBatchFixtureFrame $h0 $p0 $lf $lf),$lf)}
        'BATCH_EXTRA_VALID_FRAME'{$streamBytes=JoinFixtureBytes @((GitBatchFixtureFrame $h0 $p0 $lf $lf),(GitBatchFixtureFrame $h1 $p1 $lf $lf))}
        'BATCH_DECLARED_SIZE_OVERFLOW'{$streamBytes=GitBatchFixtureFrame ([string]$d0.oid+' blob 18446744073709551616') $none $lf $none}
        'BATCH_HEADER_PARTIAL_EOF'{$streamBytes=AsciiFixtureBytes ([string]$d0.oid+' blob')}
        'BATCH_PROCESS_NONZERO'{$streamBytes=GitBatchFixtureFrame $h0 $p0 $lf $lf;$runProcessCheck=$true}
        default{throw 'Unknown Git batch fixture mutation: '+$Mutation}
    }
    $stream=[IO.MemoryStream]::new([byte[]]$streamBytes,$false)
    try{$result=@(ReadAuthenticatedGitBatch $stream $expected);if($runProcessCheck){AssertGitBatchProcessResult $true 17 'fixture nonzero process' 'fixture'};return $result}finally{$stream.Dispose()}
}

function InvokeNegativeCases([object]$Receipt,[object]$Determinism,[object]$NegativeRegistry) {
    $negativeResults=[Collections.Generic.List[object]]::new()
    foreach($case in @($NegativeRegistry.cases)){
        $mutated=Clone $Receipt;$detMutated=Clone $Determinism;$overrides=@{};$provenance=@{};$role=$mutated.roles[0];$directParserMutation=$null
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
            'COMPILER_INPUT_SIZE_NUMBER_TO_STRING'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord.size=[string]$inputRecord.size}
            'COMPILER_INPUT_MODE_STRING_TO_NUMBER'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord.mode=[int]$inputRecord.mode}
            'COMMITTED_NULL_GENERATION_RULE_TO_SENTINEL'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord.generation_rule='<null>'}
            'COMMITTED_NULL_GENERATOR_TO_SENTINEL'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord.generator='<null>'}
            'GENERATED_NULL_GIT_BLOB_TO_SENTINEL'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-like'Generated/*'})[0];$inputRecord.git_blob_identity='<null>'}
            'GENERATED_NULL_MODE_TO_SENTINEL'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-like'Generated/*'})[0];$inputRecord.mode='<null>'}
            'DETERMINISM_COMPILER_INPUT_HASH_CHANGED'{$detMutated.role_determinism[0].compiler_inputs[0].raw_sha256=('d'*64-join'')}
            'DETERMINISM_COMPILER_INPUT_REMOVED'{$detMutated.role_determinism[0].compiler_inputs=@($detMutated.role_determinism[0].compiler_inputs|Select-Object -Skip 1)}
            'DETERMINISM_COMPILER_INPUT_ADDED'{$detMutated.role_determinism[0].compiler_inputs=@($detMutated.role_determinism[0].compiler_inputs)+@(Clone $detMutated.role_determinism[0].compiler_inputs[0])}
            'DETERMINISM_COMPILER_INPUTS_REORDERED'{$inputs=@($detMutated.role_determinism[0].compiler_inputs);$value=$inputs[0];$inputs[0]=$inputs[1];$inputs[1]=$value;$detMutated.role_determinism[0].compiler_inputs=$inputs}
            'DETERMINISM_COMPILER_INPUT_SIZE_NUMBER_TO_STRING'{$detMutated.role_determinism[0].compiler_inputs[0].size=[string]$detMutated.role_determinism[0].compiler_inputs[0].size}
            'COORDINATED_GENERATED_PRODUCER_AUTHORITY_AND_ROLE'{$generated=$mutated.generated_sources[0];$source=$mutated.source_files[1];$fake=[ordered]@{git_blob_identity=[string]$source.git_blob_identity;path=[string]$source.path;raw_sha256=[string]$source.raw_sha256};$generated.generator=Clone $fake;foreach($consumer in @($mutated.roles)){foreach($inputRecord in @($consumer.compiler_inputs|Where-Object{[string]$_.path-ceq[string]$generated.path})){$inputRecord.generator=Clone $fake}}}
            'COORDINATED_GENERATED_PRODUCER_ALL_RECEIPTS'{$generated=$mutated.generated_sources[0];$source=$mutated.source_files[1];$fake=[ordered]@{git_blob_identity=[string]$source.git_blob_identity;path=[string]$source.path;raw_sha256=[string]$source.raw_sha256};$generated.generator=Clone $fake;foreach($consumer in @($mutated.roles)){foreach($inputRecord in @($consumer.compiler_inputs|Where-Object{[string]$_.path-ceq[string]$generated.path})){$inputRecord.generator=Clone $fake}};foreach($consumer in @($detMutated.role_determinism)){foreach($inputRecord in @($consumer.compiler_inputs|Where-Object{[string]$_.path-ceq[string]$generated.path})){$inputRecord.generator=Clone $fake}}}
            'UNAUTHORIZED_GENERATED_SOURCE_ROLE_ASSIGNMENT'{$donor=@($mutated.roles|Where-Object{[string]$_.role-ceq'PACKAGED_ARTIFACT_TOOL'})[0];$donorInput=Clone @($donor.compiler_inputs|Where-Object{[string]$_.path-like'Generated/*'})[0];$inputIndex=0;for(;$inputIndex-lt$role.compiler_inputs.Count;$inputIndex++){if([string]$role.compiler_inputs[$inputIndex].path-like'Generated/*'){break}};$role.compiler_inputs[$inputIndex]=$donorInput}
            'MISSING_FIELD_REPLACES_EXPLICIT_NULL'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord.PSObject.Properties.Remove('generation_rule')}
            'UNKNOWN_COMPILER_INPUT_FIELD'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord|Add-Member -NotePropertyName ungoverned_identity -NotePropertyValue 'forbidden'}
            'CRLF_COMPILER_MATERIALIZATION'{$source=$mutated.source_files[0];$authority=ExactTreeBlobAuthority ([string]$source.path);$crlf=CrLfFixtureBytes (ReadGitBlobBytes ([string]$authority.git_blob_identity));$provenance['compiler_sha256:'+[string]$source.path]=BytesHash $crlf;$provenance['compiler_size:'+[string]$source.path]=[long]$crlf.Length}
            'WORKTREE_PSEUDO_BLOB_FOR_TREE_BLOB'{$source=$mutated.source_files[0];$authority=ExactTreeBlobAuthority ([string]$source.path);$crlf=CrLfFixtureBytes (ReadGitBlobBytes ([string]$authority.git_blob_identity));$source.git_blob_identity=UntrustedFixtureBlobIdentity $crlf;foreach($consumer in @($mutated.roles)+@($detMutated.role_determinism)){foreach($inputRecord in @($consumer.compiler_inputs|Where-Object{[string]$_.path-ceq[string]$source.path})){$inputRecord.git_blob_identity=$source.git_blob_identity}}}
            'WORKTREE_SHA_FOR_COMMITTED_SHA'{$source=$mutated.source_files[0];$authority=ExactTreeBlobAuthority ([string]$source.path);$crlf=CrLfFixtureBytes (ReadGitBlobBytes ([string]$authority.git_blob_identity));$source.raw_sha256=BytesHash $crlf;$source.size=[long]$crlf.Length;foreach($consumer in @($mutated.roles)+@($detMutated.role_determinism)){foreach($inputRecord in @($consumer.compiler_inputs|Where-Object{[string]$_.path-ceq[string]$source.path})){$inputRecord.raw_sha256=$source.raw_sha256;$inputRecord.size=$source.size}}}
            'WORKTREE_SIZE_FOR_COMMITTED_SIZE'{$source=$mutated.source_files[0];$source.size=[long]$source.size+1;foreach($consumer in @($mutated.roles)+@($detMutated.role_determinism)){foreach($inputRecord in @($consumer.compiler_inputs|Where-Object{[string]$_.path-ceq[string]$source.path})){$inputRecord.size=$source.size}}}
            'UNGOVERNED_COMPILER_BYTE_MUTATION'{$source=$mutated.source_files[0];$provenance['compiler_sha256:'+[string]$source.path]='e'*64}
            'COORDINATED_CONFIGURATION_HASH_AND_CONSUMERS'{$config=$mutated.configuration_inputs[0];$old=[string]$config.raw_sha256;$config.raw_sha256='e'*64;foreach($generated in @($mutated.generated_sources)){foreach($inputRecord in @($generated.source_inputs)){if([string]$inputRecord.role-ceq[string]$config.role-and[string]$inputRecord.identity-ceq$old){$inputRecord.identity=$config.raw_sha256}}}}
            'COORDINATED_CONFIGURATION_PATH_SIZE_AND_CONSUMERS'{$config=$mutated.configuration_inputs[0];$old=[string]$config.raw_sha256;$config.path='C:\Temp\forged-authority-source-manifest.json';$config.raw_sha256='d'*64;$config.size=[long]$config.size+17;foreach($generated in @($mutated.generated_sources)){foreach($inputRecord in @($generated.source_inputs)){if([string]$inputRecord.role-ceq[string]$config.role-and[string]$inputRecord.identity-ceq$old){$inputRecord.identity=$config.raw_sha256}}}}
            'CONFIGURATION_INPUT_REMOVED'{$mutated.configuration_inputs=@($mutated.configuration_inputs|Select-Object -Skip 1)}
            'CONFIGURATION_INPUT_INSERTED'{$mutated.configuration_inputs=@(Clone $mutated.configuration_inputs[0])+@($mutated.configuration_inputs)}
            'CONFIGURATION_INPUTS_REORDERED'{$rows=@($mutated.configuration_inputs);$value=$rows[0];$rows[0]=$rows[1];$rows[1]=$value;$mutated.configuration_inputs=$rows}
            'COORDINATED_CLOSURE_AND_CONSUMERS'{$old=[string]$mutated.build_input_closure_sha256;$mutated.build_input_closure_sha256='f'*64;$detMutated.build_input_closure_sha256=$mutated.build_input_closure_sha256;foreach($generated in @($mutated.generated_sources)){foreach($inputRecord in @($generated.source_inputs)){if([string]$inputRecord.role-ceq'BUILD_INPUT_CLOSURE'-and[string]$inputRecord.identity-ceq$old){$inputRecord.identity=$mutated.build_input_closure_sha256}}}}
            'COORDINATED_POLICY_AND_CONSUMERS'{$old=[string]$mutated.policy_sha256;$mutated.policy_sha256='9'*64;foreach($generated in @($mutated.generated_sources)){foreach($inputRecord in @($generated.source_inputs)){if([string]$inputRecord.role-ceq'COMPLETED_UNIT2_POLICY'-and[string]$inputRecord.identity-ceq$old){$inputRecord.identity=$mutated.policy_sha256}}}}
            'POLICY_ARTIFACT_PATH_SUBSTITUTED'{$provenance.policy_path=Join-Path $build 'Generated\forged_unit2_upgrade_policy.json'}
            'COORDINATED_GENERATED_SOURCE_INPUTS_ALL_RECEIPTS'{$config=$mutated.configuration_inputs[0];$old=[string]$config.raw_sha256;$config.raw_sha256='8'*64;foreach($container in @($mutated.generated_sources)+@($detMutated.generated_sources)){foreach($inputRecord in @($container.source_inputs)){if([string]$inputRecord.role-ceq[string]$config.role-and[string]$inputRecord.identity-ceq$old){$inputRecord.identity=$config.raw_sha256}}}}
            'SOURCE_COMMIT_RETAINING_CONSUMERS'{$mutated.source_commit='a'*40;$detMutated.source_commit=$mutated.source_commit}
            'TREE_BLOB_CHANGED_WITH_ALL_CONSUMERS'{$source=$mutated.source_files[0];$source.git_blob_identity='c'*40;foreach($consumer in @($mutated.roles)+@($detMutated.role_determinism)){foreach($inputRecord in @($consumer.compiler_inputs|Where-Object{[string]$_.path-ceq[string]$source.path})){$inputRecord.git_blob_identity=$source.git_blob_identity}}}
            'CLOSURE_SERIALIZATION_ORDER_CHANGED'{$provenance.closure_reorder=$true}
            'FORGED_RECEIPTS_ORIGINAL_GENERATED_OUTPUT'{$oldClosure=[string]$mutated.build_input_closure_sha256;$oldPolicy=[string]$mutated.policy_sha256;$mutated.build_input_closure_sha256='7'*64;$detMutated.build_input_closure_sha256=$mutated.build_input_closure_sha256;$mutated.policy_sha256='6'*64;foreach($container in @($mutated.generated_sources)+@($detMutated.generated_sources)){foreach($inputRecord in @($container.source_inputs)){if([string]$inputRecord.role-ceq'BUILD_INPUT_CLOSURE'-and[string]$inputRecord.identity-ceq$oldClosure){$inputRecord.identity=$mutated.build_input_closure_sha256};if([string]$inputRecord.role-ceq'COMPLETED_UNIT2_POLICY'-and[string]$inputRecord.identity-ceq$oldPolicy){$inputRecord.identity=$mutated.policy_sha256}}}}
            {$_ -like 'BATCH_*'}{$directParserMutation=[string]$_}
            default{throw "Unknown negative mutation: $($case.mutation)"}
        }
        $observed=$null;$observedDetail=''
        try{if($null-ne$directParserMutation){[void](InvokeGitBatchParserFixture $directParserMutation)}else{ValidateModel $mutated $detMutated $overrides $provenance};throw 'NEGATIVE_CASE_UNEXPECTED_PASS'}catch{if($_.Exception.Message-ceq'NEGATIVE_CASE_UNEXPECTED_PASS'){throw};$parts=$_.Exception.Message-split'\|',2;$observed=$parts[0];if($parts.Count-gt1){$observedDetail=$parts[1]}}
        if($observed-cne[string]$case.expected_error){throw "Negative case wrong rejection: $($case.case_id) expected $($case.expected_error) observed $observed"}
        if(HasField $case 'expected_detail_pattern'){if($observedDetail-cnotmatch[string]$case.expected_detail_pattern){throw "Negative case wrong detail: $($case.case_id) observed $observedDetail"}}
        $negativeResults.Add([ordered]@{case_id=[string]$case.case_id;expected_detail=$observedDetail;expected_error=[string]$case.expected_error;mutation=[string]$case.mutation;observed_error=$observed;status='PASS'})
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
$expectedSourceRows=@(CommittedAuthorityRows @{})
$receiptSourceRows=@($receipt.source_files)
if($expectedSourceRows.Count-ne $receiptSourceRows.Count){throw 'Exact source inventory count mismatch'}
for($index=0;$index-lt $expectedSourceRows.Count;$index++){foreach($field in @('git_blob_identity','mode','path','raw_sha256','size')){$expectedValue=[string](FieldValue $expectedSourceRows[$index] $field);$actualValue=[string](FieldValue $receiptSourceRows[$index] $field);if($expectedValue-cne$actualValue){throw "Exact source inventory mismatch: $($expectedSourceRows[$index].path)/$field"}}}

$generatedNames=@($receipt.generated_sources|ForEach-Object{[string]$_.path}|Sort-Object);$expectedGenerated=@('Generated/R7PackagedTools.g.cs','Generated/R7Unit2BuildBootstrap.g.cs','Generated/R7Unit2ClientShared.g.cs','Generated/R7Unit2Service.g.cs')
if(($generatedNames-join "`n")-cne($expectedGenerated-join "`n")){throw 'Generated source inventory mismatch'}
foreach($row in @($receipt.generated_sources)){$path=Join-Path $build ([string]$row.path).Replace('/','\');if((Hash $path)-cne[string]$row.raw_sha256 -or (Get-Item -LiteralPath $path).Length-ne[long]$row.size -or [string]$row.output_identity-cne[string]$row.raw_sha256){throw "Generated source identity mismatch: $($row.path)"};if(SourceTokenInvalid ([IO.File]::ReadAllText($path))){throw "Generated source token invalid: $($row.path)"}}

$roleNames=@($receipt.roles|ForEach-Object{[string]$_.role}|Sort-Object);if(($roleNames-join "`n")-cne(($requiredRoles|Sort-Object)-join "`n")){throw 'Binary role set mismatch'}
ValidateModel $receipt $determinism @{}
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

$negativeRegistry=ReadJson $negativePath;$negativeResults=@(InvokeNegativeCases $receipt $determinism $negativeRegistry)

$result=[ordered]@{artifact_type='R7_UNIT2_BUILD_CLOSURE_VERIFICATION';build_manifest_sha256=(Hash $manifestPath);build_receipt_sha256=(Hash $receiptPath);determinism_receipt_sha256=(Hash $determinismPath);generated_source_count=$receipt.generated_sources.Count;negative_results=$negativeResults;negative_test_count=$negativeResults.Count;role_count=$receipt.roles.Count;schema_version='1.0.0';source_commit=$SourceCommit;source_identity_class=[string]$receipt.source_identity_class;source_tree=[string]$receipt.source_tree;status='PASS'}
if(Test-Path -LiteralPath $output){throw "Verification output exists: $output"};$parent=Split-Path -Parent $output;if(-not(Test-Path -LiteralPath $parent)){New-Item -ItemType Directory -Path $parent|Out-Null};[IO.File]::WriteAllText($output,($result|ConvertTo-Json -Depth 100),[Text.UTF8Encoding]::new($false))
[ordered]@{negative_test_count=$negativeResults.Count;output=$output;raw_sha256=(Hash $output);role_count=$receipt.roles.Count;status='PASS'}|ConvertTo-Json
