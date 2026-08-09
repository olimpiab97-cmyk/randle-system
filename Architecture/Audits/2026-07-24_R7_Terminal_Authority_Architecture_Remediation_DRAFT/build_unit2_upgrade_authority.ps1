[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$SourceCommit,
    [Parameter(Mandatory=$true)][string]$TargetBuildRoot,
    [Parameter(Mandatory=$true)][string]$BootstrapRecord,
    [Parameter(Mandatory=$true)][string]$UpgradePublicCertificate,
    [Parameter(Mandatory=$true)][string]$PreflightHostState,
    [Parameter(Mandatory=$true)][string]$OutputRoot,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedScriptSha256,
    [switch]$CandidateWorktree
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$packageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $packageRoot '..\..\..'))
$packageRelativeRoot = 'Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT'
$target = [IO.Path]::GetFullPath($TargetBuildRoot)
$output = [IO.Path]::GetFullPath($OutputRoot)
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
$unit1Commit = 'd22610e96496f7a9209edff36442be843f06fed4'
$unit1Tree = '8a627b54537e4c26835345907fc5181205ce496f'
$bootstrapCommit = 'b07fd42a20ed612d53070aa1d1ae1bda6ace1e93'
$bootstrapTree = '7d0d92000192b913f9ff3fba6e57ce7308d2f3be'
$bootstrapProvisioningScriptSha256 = 'ce93883e714a8a33e1a078cd5e6857c0012e601a9c9829df67b2aede882a2547'
$terminalLedgerId = '899e4db2b5c0f4ad58a09c682324a2ee9e5d7e2f180822ce9300922e56741d52'
$terminalLedgerRoot = '87fdc1bbcef606ad134cf5cd2c0cad83dd4df25ed96544c05fd5adbeff5f82e5'
$terminalCheckpointSha256 = '988f08177b04125e3f92f0696adac8c22b7d24ab0a4cba726145d97ea2958962'
$terminalPolicySha256 = '76eb2900b2000aa0b41e6040335cc323f7443728aad21cd871d5b6b8e17bcd8b'
$terminalBinarySha256 = '9ea829416f37c94db2858586fa5e0042652f6caa4637a29fdbefb513577a7526'
$terminalTrustSha256 = 'b84a4de14577580c64ff5b2446f120aa6f9ea60faa2cb5465b495282f0273285'
$terminalSid = 'S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948'
$upgradeSid = 'S-1-5-80-238545627-4117296865-2677355104-248304369-1301198082'
$transitionNonce = 'bc3a3218-5f52-4f2c-9d5e-eceda24dab36'
$provisioningNonce = '438bd38a-b02a-423f-bc5f-11847a8a76d9'
$expiration = '2026-08-24T00:00:00.0000000Z'
$compilerOptions = @('/nologo','/noconfig','/target:exe','/platform:x64','/optimize+','/checked+','/debug-','/warn:4','/warnaserror+','/nostdlib+','/langversion:5','/filealign:512')

function Hash([string]$Path) {
    return (Get-FileHash -LiteralPath ([IO.Path]::GetFullPath($Path)) -Algorithm SHA256).Hash.ToLowerInvariant()
}
function BytesHash([byte[]]$Bytes) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant() }
    finally { $algorithm.Dispose() }
}
function GitBlobBytes([byte[]]$Bytes) {
    $header = [Text.Encoding]::ASCII.GetBytes(('blob ' + $Bytes.Length + [char]0))
    $all = New-Object byte[] ($header.Length + $Bytes.Length)
    [Buffer]::BlockCopy($header,0,$all,0,$header.Length)
    [Buffer]::BlockCopy($Bytes,0,$all,$header.Length,$Bytes.Length)
    $algorithm = [Security.Cryptography.SHA1]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($all))).Replace('-','').ToLowerInvariant() }
    finally { $algorithm.Dispose() }
}
function TextHash([string]$Value) { return BytesHash ([Text.UTF8Encoding]::new($false).GetBytes($Value)) }
function GitBlob([string]$Path) {
    $bytes = [IO.File]::ReadAllBytes([IO.Path]::GetFullPath($Path))
    return GitBlobBytes $bytes
}
function ByteEqual([byte[]]$Left,[byte[]]$Right) {
    if ($null -eq $Left -or $null -eq $Right -or $Left.Length -ne $Right.Length) { return $false }
    for ($index=0; $index -lt $Left.Length; $index++) { if ($Left[$index] -ne $Right[$index]) { return $false } }
    return $true
}
function NormalizeCrlf([byte[]]$Bytes) {
    $stream=[IO.MemoryStream]::new();$loneCr=$false
    try {
        for($index=0;$index-lt$Bytes.Length;$index++){
            if($Bytes[$index]-eq13){
                if($index+1-lt$Bytes.Length-and$Bytes[$index+1]-eq10){continue}
                $loneCr=$true
            }
            $stream.WriteByte($Bytes[$index])
        }
        return [ordered]@{bytes=$stream.ToArray();lone_cr=$loneCr}
    } finally { $stream.Dispose() }
}
function EolClass([byte[]]$Bytes) {
    $crlf=0;$lf=0;$cr=0
    for($index=0;$index-lt$Bytes.Length;$index++){
        if($Bytes[$index]-eq13){if($index+1-lt$Bytes.Length-and$Bytes[$index+1]-eq10){$crlf++;$index++}else{$cr++}}
        elseif($Bytes[$index]-eq10){$lf++}
    }
    if($cr-gt0){return 'LONE_CR_OR_MIXED'}
    if($crlf-gt0-and$lf-gt0){return 'MIXED_CRLF_LF'}
    if($crlf-gt0){return 'CRLF'}
    if($lf-gt0){return 'LF'}
    return 'NONE'
}
function EncodingClass([byte[]]$Bytes) {
    if($Bytes.Length-ge3-and$Bytes[0]-eq239-and$Bytes[1]-eq187-and$Bytes[2]-eq191){return 'UTF8_BOM'}
    try{[void]([Text.UTF8Encoding]::new($false,$true).GetString($Bytes));return 'UTF8_NO_BOM'}catch{return 'NON_UTF8'}
}
function RecordHas([object]$Record,[string]$Name) {
    if($null-eq$Record){return $false};if($Record-is[Collections.IDictionary]){return $Record.Contains($Name)};return $null-ne$Record.PSObject.Properties[$Name]
}
function TestExactCheckoutIdentityRecord([object]$Record,[bool]$AllowCandidate) {
    $required=@('schema_version','source_identity_class','path','git_blob_identity','mode','tree_size','raw_worktree_blob_identity','raw_sha256','size','clean_filtered_worktree_blob_identity','raw_tree_exact_equal','clean_filtered_tree_equal','eol_normalized_tree_equal','eol_only_exception','non_eol_difference','raw_eol','index_eol','worktree_eol','encoding','text_attribute','eol_attribute','filter_attribute','working_tree_encoding_attribute','custom_filter_present','external_filter_required','approved_file_type','tracked_path','tree_entry_present','repository_clean','index_clean','staged_mutation','unstaged_semantic_mutation','untracked_replacement','symlink_substitution','path_redirection','candidate_worktree','final_newline_matches','bom_matches','compiler_input_authority','rejection_reason')
    foreach($field in $required){if(-not(RecordHas $Record $field)){return $false}}
    $exactMode=([string]$Record.source_identity_class-ceq'EXACT_COMMIT_AND_TREE'-and-not[bool]$Record.candidate_worktree-and[bool]$Record.repository_clean-and[bool]$Record.index_clean)
    $candidateMode=($AllowCandidate-and[string]$Record.source_identity_class-ceq'CANDIDATE_CONTENT_DERIVATION_V1'-and[bool]$Record.candidate_worktree-and[bool]$Record.index_clean)
    $rawExact=[bool]$Record.raw_tree_exact_equal;$eolOnly=[bool]$Record.eol_only_exception
    $rawContract=($rawExact-and-not$eolOnly-and[string]$Record.raw_worktree_blob_identity-ceq[string]$Record.git_blob_identity)-or(-not$rawExact-and$eolOnly-and[string]$Record.raw_worktree_blob_identity-cne[string]$Record.git_blob_identity-and[bool]$Record.eol_normalized_tree_equal-and-not[bool]$Record.non_eol_difference)
    return (($exactMode-or$candidateMode)-and[string]$Record.schema_version-ceq'2.1.0'-and[string]$Record.path-cmatch'^[^\\/:]+(?:/[^\\/:]+)+$'-and[string]$Record.git_blob_identity-cmatch'^[0-9a-f]{40}$'-and[string]$Record.raw_worktree_blob_identity-cmatch'^[0-9a-f]{40}$'-and[string]$Record.clean_filtered_worktree_blob_identity-ceq[string]$Record.git_blob_identity-and[string]$Record.raw_sha256-cmatch'^[0-9a-f]{64}$'-and[long]$Record.tree_size-ge0-and[long]$Record.size-ge0-and[bool]$Record.clean_filtered_tree_equal-and$rawContract-and[bool]$Record.tracked_path-and[bool]$Record.tree_entry_present-and[bool]$Record.approved_file_type-and-not[bool]$Record.custom_filter_present-and-not[bool]$Record.external_filter_required-and[string]$Record.filter_attribute-in@('unspecified','unset','')-and[string]$Record.working_tree_encoding_attribute-in@('unspecified','unset','')-and-not[bool]$Record.staged_mutation-and-not[bool]$Record.unstaged_semantic_mutation-and-not[bool]$Record.untracked_replacement-and-not[bool]$Record.symlink_substitution-and-not[bool]$Record.path_redirection-and[bool]$Record.final_newline_matches-and[bool]$Record.bom_matches-and[bool]$Record.compiler_input_authority-and[string]$Record.rejection_reason-ceq'')
}
function ReadGitObjectBytes([string]$Oid) {
    if($Oid-cnotmatch'^[0-9a-f]{40}$'){throw 'Invalid Git blob identity'}
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$git;$info.Arguments=('--no-pager -c "safe.directory='+$safeRepository+'" -c core.fsmonitor=false -c core.hooksPath=NUL -C "'+$repositoryRoot+'" cat-file blob '+$Oid);$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    $process=[Diagnostics.Process]::new();$process.StartInfo=$info
    try{if(-not$process.Start()){throw 'Git blob reader launch failed'};$memory=[IO.MemoryStream]::new();try{$process.StandardOutput.BaseStream.CopyTo($memory);$errorText=$process.StandardError.ReadToEnd();$process.WaitForExit();if($process.ExitCode-ne0){throw ('Git blob reader failed: '+$errorText)};return $memory.ToArray()}finally{$memory.Dispose()}}finally{$process.Dispose()}
}
function EffectiveGitAttributes([string]$Relative) {
    $values=[ordered]@{text='unspecified';eol='unspecified';filter='unspecified';working_tree_encoding='unspecified'}
    foreach($line in @(& $git --no-pager -c "safe.directory=$safeRepository" -c core.fsmonitor=false -c core.hooksPath=NUL -C $repositoryRoot check-attr text eol filter working-tree-encoding -- $Relative)){
        if($line-match'^[^:]+: ([^:]+): (.*)$'){$name=$Matches[1].Replace('-','_');if($values.Contains($name)){$values[$name]=$Matches[2]}}
    }
    if($LASTEXITCODE-ne0){throw "Git attribute query failed: $Relative"}
    return $values
}
function ExactCheckoutCompilerInput([string]$Path,[string]$Relative,[string]$TreeBlob,[string]$Mode,[long]$TreeSize) {
    $full=[IO.Path]::GetFullPath($Path);$repoPrefix=$repositoryRoot.TrimEnd('\')+'\'
    $raw=[IO.File]::ReadAllBytes($full);$treeBytes=ReadGitObjectBytes $TreeBlob;$normalized=NormalizeCrlf $raw
    $cleanBlob=(@(& $git --no-pager -c "safe.directory=$safeRepository" -c core.fsmonitor=false -c core.hooksPath=NUL -C $repositoryRoot hash-object ("--path=$Relative") -- $full))[0].Trim()
    if($LASTEXITCODE-ne0-or$cleanBlob-cnotmatch'^[0-9a-f]{40}$'){throw "Path-aware clean-filter identity failed: $Relative"}
    $trackedOutput=@(& $git --no-pager -c "safe.directory=$safeRepository" -c core.fsmonitor=false -c core.hooksPath=NUL -C $repositoryRoot ls-files --error-unmatch -- $Relative);$tracked=($LASTEXITCODE-eq0-and$trackedOutput.Count-eq1)
    $eolLine=(@(& $git --no-pager -c "safe.directory=$safeRepository" -c core.fsmonitor=false -c core.hooksPath=NUL -C $repositoryRoot ls-files --eol -- $Relative))[0]
    if($LASTEXITCODE-ne0-or$eolLine-cnotmatch'^i/([^ ]+)\s+w/([^ ]+)\s+attr/.*\t') { throw "Git EOL authority failed: $Relative" }
    $indexEol=$Matches[1];$worktreeEol=$Matches[2];$attributes=EffectiveGitAttributes $Relative
    $rawBlob=GitBlob $full;$rawExact=(ByteEqual $raw $treeBytes);$cleanEqual=$cleanBlob-ceq$TreeBlob;$normalizedEqual=ByteEqual ([byte[]]$normalized.bytes) $treeBytes
    $filterValue=[string]$attributes.filter;$encodingValue=[string]$attributes.working_tree_encoding
    $customFilter=($filterValue-cnotin@('unspecified','unset',''))
    $encodingConversion=($encodingValue-cnotin@('unspecified','unset',''))
    $approvedType=($Mode-ceq'100644'-and((Get-Item -LiteralPath $full -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)-eq0-and$full.StartsWith($repoPrefix,[StringComparison]::OrdinalIgnoreCase))
    $bomRaw=($raw.Length-ge3-and$raw[0]-eq239-and$raw[1]-eq187-and$raw[2]-eq191);$bomTree=($treeBytes.Length-ge3-and$treeBytes[0]-eq239-and$treeBytes[1]-eq187-and$treeBytes[2]-eq191)
    $eolOnly=(-not$rawExact-and$cleanEqual-and$normalizedEqual-and-not[bool]$normalized.lone_cr-and-not$customFilter-and-not$encodingConversion-and$approvedType-and$tracked-and$raw.Length-ge$treeBytes.Length)
    $modeAuthority=if($CandidateWorktree){$sourceIdentityClass-ceq'CANDIDATE_CONTENT_DERIVATION_V1'-and$indexClean}else{$sourceIdentityClass-ceq'EXACT_COMMIT_AND_TREE'-and$repositoryClean-and$indexClean}
    $record=[ordered]@{schema_version='2.1.0';source_identity_class=$sourceIdentityClass;path=$Relative;git_blob_identity=$TreeBlob;mode=$Mode;tree_size=$TreeSize;raw_worktree_blob_identity=$rawBlob;raw_sha256=(BytesHash $raw);size=[long]$raw.Length;clean_filtered_worktree_blob_identity=$cleanBlob;raw_tree_exact_equal=$rawExact;clean_filtered_tree_equal=$cleanEqual;eol_normalized_tree_equal=$normalizedEqual;eol_only_exception=$eolOnly;non_eol_difference=(-not$rawExact-and-not$normalizedEqual);raw_eol=(EolClass $raw);index_eol=$indexEol;worktree_eol=$worktreeEol;encoding=(EncodingClass $raw);text_attribute=[string]$attributes.text;eol_attribute=[string]$attributes.eol;filter_attribute=$filterValue;working_tree_encoding_attribute=$encodingValue;custom_filter_present=$customFilter;external_filter_required=$false;approved_file_type=$approvedType;tracked_path=$tracked;tree_entry_present=$true;repository_clean=$repositoryClean;index_clean=$indexClean;staged_mutation=$false;unstaged_semantic_mutation=$false;untracked_replacement=$false;symlink_substitution=$false;path_redirection=$false;candidate_worktree=[bool]$CandidateWorktree;final_newline_matches=$normalizedEqual;bom_matches=($bomRaw-eq$bomTree);compiler_input_authority=$true;rejection_reason=''}
    $authority=TestExactCheckoutIdentityRecord $record ([bool]$CandidateWorktree);$record.compiler_input_authority=$authority
    $record.rejection_reason=if($authority){''}elseif(-not$tracked){'UNTRACKED_PATH'}elseif(-not$approvedType){'UNAPPROVED_FILE_TYPE'}elseif(-not$cleanEqual){'CLEAN_FILTER_TREE_MISMATCH'}elseif($customFilter){'CUSTOM_FILTER_PRESENT'}elseif($encodingConversion){'WORKING_TREE_ENCODING_PRESENT'}elseif(-not($rawExact-or$eolOnly)){'NON_EOL_RAW_DIFFERENCE'}else{'SOURCE_MODE_OR_CLEAN_STATE_INVALID'}
    return $record
}
function TestGovernedScriptIdentityRecord([object]$Record) {
    $required=@('schema_version','source_identity_class','path','registry_shape_valid','tracked_path','approved_file_type','tree_mode','registry_mode','object_type','raw_worktree_blob_identity','independent_raw_no_filter_blob_identity','raw_sha256','registry_raw_sha256','raw_size','registry_raw_size','clean_filtered_worktree_blob_identity','canonical_blob_identity','registry_canonical_blob_identity','registry_canonical_recomputed_blob_identity','canonical_sha256','registry_canonical_sha256','canonical_size','registry_canonical_size','raw_canonical_equal','eol_normalized_canonical_equal','eol_only_authority','non_eol_difference','final_newline_matches','index_eol','worktree_eol','filter_attribute','working_tree_encoding_attribute','custom_filter_present','encoding_conversion_present','candidate_worktree','repository_clean','index_clean')
    foreach($field in $required){if(-not(RecordHas $Record $field)){return $false}}
    $candidateMode=([bool]$Record.candidate_worktree-and[string]$Record.source_identity_class-ceq'CANDIDATE_CONTENT_DERIVATION_V1'-and[bool]$Record.index_clean)
    $exactMode=(-not[bool]$Record.candidate_worktree-and[string]$Record.source_identity_class-ceq'EXACT_COMMIT_AND_TREE'-and[bool]$Record.repository_clean-and[bool]$Record.index_clean)
    $rawAuthority=([string]$Record.raw_worktree_blob_identity-ceq[string]$Record.independent_raw_no_filter_blob_identity-and[string]$Record.raw_sha256-ceq[string]$Record.registry_raw_sha256-and[long]$Record.raw_size-eq[long]$Record.registry_raw_size)
    $canonicalAuthority=([string]$Record.clean_filtered_worktree_blob_identity-ceq[string]$Record.canonical_blob_identity-and[string]$Record.canonical_blob_identity-ceq[string]$Record.registry_canonical_blob_identity-and[string]$Record.registry_canonical_blob_identity-ceq[string]$Record.registry_canonical_recomputed_blob_identity-and[string]$Record.canonical_sha256-ceq[string]$Record.registry_canonical_sha256-and[long]$Record.canonical_size-eq[long]$Record.registry_canonical_size)
    $rawExact=([string]$Record.raw_worktree_blob_identity-ceq[string]$Record.canonical_blob_identity-and[string]$Record.raw_sha256-ceq[string]$Record.canonical_sha256-and[long]$Record.raw_size-eq[long]$Record.canonical_size)
    $domainAuthority=([bool]$Record.raw_canonical_equal-eq$rawExact)-and(($rawExact-and-not[bool]$Record.eol_only_authority)-or(-not$rawExact-and[bool]$Record.eol_only_authority-and[bool]$Record.eol_normalized_canonical_equal-and-not[bool]$Record.non_eol_difference))
    return ([string]$Record.schema_version-ceq'GOVERNED_SCRIPT_IDENTITY_DOMAIN_V1'-and($candidateMode-or$exactMode)-and[bool]$Record.registry_shape_valid-and[string]$Record.path-cmatch'^[^\\/:]+(?:/[^\\/:]+)+$'-and[bool]$Record.tracked_path-and[bool]$Record.approved_file_type-and[string]$Record.tree_mode-ceq'100644'-and[string]$Record.registry_mode-ceq'100644'-and[string]$Record.object_type-ceq'blob'-and[string]$Record.raw_worktree_blob_identity-cmatch'^[0-9a-f]{40}$'-and[string]$Record.independent_raw_no_filter_blob_identity-cmatch'^[0-9a-f]{40}$'-and[string]$Record.raw_sha256-cmatch'^[0-9a-f]{64}$'-and[string]$Record.registry_raw_sha256-cmatch'^[0-9a-f]{64}$'-and[string]$Record.clean_filtered_worktree_blob_identity-cmatch'^[0-9a-f]{40}$'-and[string]$Record.canonical_blob_identity-cmatch'^[0-9a-f]{40}$'-and[string]$Record.registry_canonical_blob_identity-cmatch'^[0-9a-f]{40}$'-and[string]$Record.canonical_sha256-cmatch'^[0-9a-f]{64}$'-and[string]$Record.registry_canonical_sha256-cmatch'^[0-9a-f]{64}$'-and[long]$Record.raw_size-ge0-and[long]$Record.registry_raw_size-ge0-and[long]$Record.canonical_size-ge0-and[long]$Record.registry_canonical_size-ge0-and$rawAuthority-and$canonicalAuthority-and$domainAuthority-and[bool]$Record.final_newline_matches-and-not[bool]$Record.custom_filter_present-and-not[bool]$Record.encoding_conversion_present-and[string]$Record.filter_attribute-in@('unspecified','unset','')-and[string]$Record.working_tree_encoding_attribute-in@('unspecified','unset',''))
}
function GovernedScriptIdentity([object]$Row) {
    $expectedFields=@('allowed_invocation_stages','authority_classification','dependencies','execution_class','git_blob_identity','mode','path','raw_sha256','role','size')|Sort-Object
    $actualFields=@($Row.PSObject.Properties.Name)|Sort-Object
    if(($actualFields-join"`n")-cne($expectedFields-join"`n")){throw 'Governed script registry object shape invalid'}
    $relative=[string]$Row.path
    if($relative-cnotmatch'^[^\\/:]+(?:/[^\\/:]+)+$'){throw "Governed script registry path invalid: $relative"}
    $full=[IO.Path]::GetFullPath((Join-Path $repositoryRoot $relative.Replace('/','\')));$repoPrefix=$repositoryRoot.TrimEnd('\')+'\'
    if(-not$full.StartsWith($repoPrefix,[StringComparison]::OrdinalIgnoreCase)-or(Relative $repositoryRoot $full)-cne$relative-or-not(Test-Path -LiteralPath $full -PathType Leaf)){throw "Governed script registry path authority failed: $relative"}
    $trackedOutput=@(& $git --no-pager -c "safe.directory=$safeRepository" -c core.fsmonitor=false -c core.hooksPath=NUL -C $repositoryRoot ls-files --error-unmatch -- $relative);$tracked=($LASTEXITCODE-eq0-and$trackedOutput.Count-eq1-and[string]$trackedOutput[0]-ceq$relative)
    $stageOutput=@(& $git --no-pager -c "safe.directory=$safeRepository" -c core.fsmonitor=false -c core.hooksPath=NUL -C $repositoryRoot ls-files --stage -- $relative);$treeMode=if($LASTEXITCODE-eq0-and$stageOutput.Count-eq1-and[string]$stageOutput[0]-match'^(\d{6}) [0-9a-f]{40} \d+\t'){$Matches[1]}else{''}
    $approvedType=(((Get-Item -LiteralPath $full -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)-eq0)
    $attributes=EffectiveGitAttributes $relative;$filterValue=[string]$attributes.filter;$encodingValue=[string]$attributes.working_tree_encoding;$customFilter=$filterValue-cnotin@('unspecified','unset','');$encodingConversion=$encodingValue-cnotin@('unspecified','unset','')
    $eolLine=(@(& $git --no-pager -c "safe.directory=$safeRepository" -c core.fsmonitor=false -c core.hooksPath=NUL -C $repositoryRoot ls-files --eol -- $relative))[0]
    if($LASTEXITCODE-ne0-or$eolLine-cnotmatch'^i/([^ ]+)\s+w/([^ ]+)\s+attr/.*\t'){throw "Governed script EOL authority failed: $relative"};$indexEol=$Matches[1];$worktreeEol=$Matches[2]
    $raw=[IO.File]::ReadAllBytes($full);try{[void]([Text.UTF8Encoding]::new($false,$true).GetString($raw))}catch{throw "Governed script encoding invalid: $relative"}
    if($raw.Length-ge3-and$raw[0]-eq239-and$raw[1]-eq187-and$raw[2]-eq191){throw "Governed script BOM invalid: $relative"}
    $rawBlob=GitBlobBytes $raw;$rawNoFilter=(@(& $git --no-pager -c "safe.directory=$safeRepository" -c core.fsmonitor=false -c core.hooksPath=NUL -C $repositoryRoot hash-object --no-filters -- $full))[0].Trim()
    if($LASTEXITCODE-ne0-or$rawNoFilter-cnotmatch'^[0-9a-f]{40}$'){throw "Governed script raw identity failed: $relative"}
    $cleanBlob=(@(& $git --no-pager -c "safe.directory=$safeRepository" -c core.fsmonitor=false -c core.hooksPath=NUL -C $repositoryRoot hash-object ("--path=$relative") -- $full))[0].Trim()
    if($LASTEXITCODE-ne0-or$cleanBlob-cnotmatch'^[0-9a-f]{40}$'){throw "Governed script path-aware clean identity failed: $relative"}
    $normalized=NormalizeCrlf $raw;$normalizedBlob=GitBlobBytes ([byte[]]$normalized.bytes);$rawCanonical=$rawBlob-ceq$cleanBlob;$normalizedCanonical=$normalizedBlob-ceq$cleanBlob
    $finalNewlineMatches=(($raw.Length-gt0-and$raw[$raw.Length-1]-eq10)-eq($normalized.bytes.Length-gt0-and$normalized.bytes[$normalized.bytes.Length-1]-eq10))
    $eolOnly=(-not$rawCanonical-and$normalizedCanonical-and-not[bool]$normalized.lone_cr-and$finalNewlineMatches);$canonicalBytes=if($rawCanonical){$raw}elseif($eolOnly){[byte[]]$normalized.bytes}else{[byte[]]@()};$canonicalBlob=GitBlobBytes $canonicalBytes
    $objectType=(@(& $git --no-pager -c "safe.directory=$safeRepository" -c core.fsmonitor=false -c core.hooksPath=NUL -C $repositoryRoot cat-file -t ([string]$Row.git_blob_identity)))[0].Trim()
    if($LASTEXITCODE-ne0-or$objectType-cne'blob'){throw "Governed script canonical object type invalid: $relative"}
    $registryCanonicalBytes=ReadGitObjectBytes ([string]$Row.git_blob_identity)
    $record=[ordered]@{schema_version='GOVERNED_SCRIPT_IDENTITY_DOMAIN_V1';source_identity_class=$sourceIdentityClass;path=$relative;registry_shape_valid=$true;tracked_path=$tracked;approved_file_type=$approvedType;tree_mode=$treeMode;registry_mode=[string]$Row.mode;object_type=$objectType;raw_worktree_blob_identity=$rawBlob;independent_raw_no_filter_blob_identity=$rawNoFilter;raw_sha256=(BytesHash $raw);registry_raw_sha256=[string]$Row.raw_sha256;raw_size=[long]$raw.Length;registry_raw_size=[long]$Row.size;clean_filtered_worktree_blob_identity=$cleanBlob;canonical_blob_identity=$canonicalBlob;registry_canonical_blob_identity=[string]$Row.git_blob_identity;registry_canonical_recomputed_blob_identity=(GitBlobBytes $registryCanonicalBytes);canonical_sha256=(BytesHash $canonicalBytes);registry_canonical_sha256=(BytesHash $registryCanonicalBytes);canonical_size=[long]$canonicalBytes.Length;registry_canonical_size=[long]$registryCanonicalBytes.Length;raw_canonical_equal=$rawCanonical;eol_normalized_canonical_equal=$normalizedCanonical;eol_only_authority=$eolOnly;non_eol_difference=(-not$rawCanonical-and-not$normalizedCanonical);final_newline_matches=$finalNewlineMatches;index_eol=$indexEol;worktree_eol=$worktreeEol;filter_attribute=$filterValue;working_tree_encoding_attribute=$encodingValue;custom_filter_present=$customFilter;encoding_conversion_present=$encodingConversion;candidate_worktree=[bool]$CandidateWorktree;repository_clean=$repositoryClean;index_clean=$indexClean}
    if(-not(TestGovernedScriptIdentityRecord $record)){throw ("Governed script registry identity-domain mismatch: $relative; raw_sha256=$($record.raw_sha256); raw_size=$($record.raw_size); raw_no_filter_blob=$($record.raw_worktree_blob_identity); clean_filtered_blob=$($record.clean_filtered_worktree_blob_identity); registry_canonical_blob=$($record.registry_canonical_blob_identity); canonical_sha256=$($record.canonical_sha256); canonical_size=$($record.canonical_size)")}
    return $record
}
function ReadJson([string]$Path) { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }
function WriteRaw([object]$Value,[string]$Path) { [IO.File]::WriteAllText($Path,($Value | ConvertTo-Json -Depth 100),[Text.UTF8Encoding]::new($false)) }
function Canonical([object]$Value,[string]$Path,[string]$Tool) {
    if (Test-Path -LiteralPath $Path) { throw "Output exists: $Path" }
    $raw = $Path + '.raw'
    WriteRaw $Value $raw
    & $Tool canonicalize $raw $Path | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Canonicalization failed: $Path" }
}
function NewDir([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        if (@(Get-ChildItem -LiteralPath $Path -Force).Count -ne 0) { throw "Output root not empty: $Path" }
    } else { New-Item -ItemType Directory -Path $Path | Out-Null }
}
function Relative([string]$Base,[string]$Path) {
    $baseFull = [IO.Path]::GetFullPath($Base).TrimEnd('\') + '\'
    return [Uri]::UnescapeDataString(([Uri]$baseFull).MakeRelativeUri([Uri][IO.Path]::GetFullPath($Path)).ToString()).Replace('\','/')
}
function EscapeCs([string]$Value) { return $Value.Replace('\','\\').Replace('"','\"') }
function Derive([string]$Domain,[string[]]$Values) {
    $builder = [Text.StringBuilder]::new()
    [void]$builder.Append($Domain.Length).Append(':').Append($Domain)
    foreach ($value in $Values) {
        $item = if ($null -eq $value) { '' } else { [string]$value }
        [void]$builder.Append('|').Append($item.Length).Append(':').Append($item)
    }
    return TextHash $builder.ToString()
}
function NormalizeIl([string]$Binary,[string]$Destination,[string]$Ildasm) {
    $raw = $Destination + '.raw.il'
    & $Ildasm /text /nobar /utf8 ("/out=$raw") $Binary | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "ILDASM failed: $Binary" }
    $text = [IO.File]::ReadAllText($raw)
    $mvid = [regex]::Match($text,'(?m)^// MVID: \{([0-9A-Fa-f-]+)\}\r?$')
    if (-not $mvid.Success) { throw "MVID absent: $Binary" }
    $text = $text.Replace($mvid.Groups[1].Value,'NORMALIZED-MVID')
    $text = [regex]::Replace($text,'(?m)^// Image base: 0x[0-9A-Fa-f]+\r?$','// Image base: NORMALIZED')
    $text = [regex]::Replace($text,'(?m)^// WARNING: Created Win32 resource file .+\.raw\.res\r?$','// WARNING: Created Win32 resource file NORMALIZED.raw.res')
    [IO.File]::WriteAllText($Destination,$text,[Text.UTF8Encoding]::new($false))
    return Hash $Destination
}
function CompilerArguments([object]$Role,[string]$Destination,[string[]]$References,[string[]]$Sources,[string]$IdentitySource) {
    $arguments = @($compilerOptions)
    $arguments += ('/main:' + [string]$Role.main)
    $arguments += ('/out:' + [IO.Path]::GetFullPath($Destination))
    $arguments += ('/define:' + [string]$Role.define)
    foreach ($reference in $References) { $arguments += ('/reference:' + [IO.Path]::GetFullPath($reference)) }
    foreach ($source in $Sources) { $arguments += [IO.Path]::GetFullPath($source) }
    $arguments += [IO.Path]::GetFullPath($IdentitySource)
    return @($arguments)
}
function Compile([string]$Compiler,[string[]]$Arguments,[string]$Destination,[string]$Role) {
    & $Compiler @Arguments
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Destination -PathType Leaf)) { throw "Compilation failed: $Role" }
}
function ExtractIdentity([string]$Binary) {
    $assembly = [Reflection.Assembly]::ReflectionOnlyLoadFrom([IO.Path]::GetFullPath($Binary))
    $result = [ordered]@{}
    foreach ($typeName in @('RandleAI.R7Remediation.R7BuildIdentity','RandleAI.R7Remediation.R7Unit2BuildIdentity')) {
        $type = $assembly.GetType($typeName,$true,$false)
        foreach ($field in @($type.GetFields([Reflection.BindingFlags]'Static,NonPublic,Public') | Sort-Object Name)) {
            if ($field.IsLiteral) { $result[($type.Name + '.' + $field.Name)] = $field.GetRawConstantValue() }
        }
    }
    return $result
}
function ExtractPackagedIdentity([string]$Binary) {
    $assembly = [Reflection.Assembly]::ReflectionOnlyLoadFrom([IO.Path]::GetFullPath($Binary))
    $result = [ordered]@{}
    foreach ($typeName in @('RandleAI.R7Remediation.R7BuildIdentity','RandleAI.R7Remediation.R7Unit2BuildIdentity')) {
        $type = $assembly.GetType($typeName,$false,$false)
        if ($null -eq $type) { continue }
        foreach ($field in @($type.GetFields([Reflection.BindingFlags]'Static,NonPublic,Public') | Sort-Object Name)) {
            if ($field.IsLiteral) { $result[($type.Name + '.' + $field.Name)] = $field.GetRawConstantValue() }
        }
    }
    return $result
}
function IsForbiddenIdentityValue([object]$Value) {
    if ($Value -isnot [string]) { return $false }
    $text = [string]$Value
    if ([string]::IsNullOrWhiteSpace($text) -or $text -match '^(?:0{40}|0{64}|0{8}|0{8}:0{16})$') { return $true }
    return $text -match '(?i)(?:BOOTSTRAP_PENDING|DEVELOPMENT|PLACEHOLDER|\bTBD\b|\bUNKNOWN\b)'
}
function AssertIdentity([object]$Expected,[object]$ExpectedUnit2,[object]$Actual,[string]$Role) {
    foreach ($key in @($Expected.Keys)) {
        $qualified = 'R7BuildIdentity.' + $key
        if (-not $Actual.Contains($qualified) -or [string]$Actual[$qualified] -cne [string]$Expected[$key]) { throw "Embedded identity mismatch: $Role/$qualified" }
    }
    foreach ($key in @($ExpectedUnit2.Keys)) {
        $qualified = 'R7Unit2BuildIdentity.' + $key
        if (-not $Actual.Contains($qualified) -or [string]$Actual[$qualified] -cne [string]$ExpectedUnit2[$key]) { throw "Embedded Unit 2 identity mismatch: $Role/$qualified" }
    }
}
function GeneratedRow([string]$Path,[string]$Rule,[string]$ScriptSha,[string]$ScriptBlob,[object[]]$Inputs) {
    return [ordered]@{
        generator=[ordered]@{git_blob_identity=$ScriptBlob;path=($packageRelativeRoot + '/build_unit2_upgrade_authority.ps1');raw_sha256=$ScriptSha}
        generation_rule=$Rule
        output_identity=(Hash $Path)
        path=('Generated/' + [IO.Path]::GetFileName($Path))
        raw_sha256=(Hash $Path)
        size=(Get-Item -LiteralPath $Path).Length
        source_inputs=$Inputs
    }
}
function IdentitySource([string]$Path,[object]$Values,[object]$Unit2Values) {
    $lines = [Collections.Generic.List[string]]::new()
    $lines.Add('namespace RandleAI.R7Remediation')
    $lines.Add('{')
    $lines.Add('    internal static class R7BuildIdentity')
    $lines.Add('    {')
    foreach ($key in @($Values.Keys)) {
        $value = $Values[$key]
        if ($value -is [uint32] -or $value -is [int32] -or $value -is [int64]) { $lines.Add(('        internal const uint ' + $key + ' = ' + [uint32]$value + ';')) }
        else { $lines.Add(('        internal const string ' + $key + ' = "' + (EscapeCs ([string]$value)) + '";')) }
    }
    $lines.Add('    }')
    $lines.Add('    internal static class R7Unit2BuildIdentity')
    $lines.Add('    {')
    foreach ($key in @($Unit2Values.Keys)) {
        $value = $Unit2Values[$key]
        if ($value -is [uint32] -or $value -is [int32] -or $value -is [int64]) { $lines.Add(('        internal const uint ' + $key + ' = ' + [uint32]$value + ';')) }
        else { $lines.Add(('        internal const string ' + $key + ' = "' + (EscapeCs ([string]$value)) + '";')) }
    }
    $lines.Add('    }')
    $lines.Add('}')
    [IO.File]::WriteAllText($Path,($lines -join "`r`n") + "`r`n",[Text.UTF8Encoding]::new($false))
}

if ((Hash $PSCommandPath) -cne $ExpectedScriptSha256) { throw 'Build script identity mismatch' }
if (-not $output.StartsWith($tempRoot,[StringComparison]::OrdinalIgnoreCase)) { throw 'Build output must remain below the disposable Temp root' }
if ($output.StartsWith($repositoryRoot.TrimEnd('\') + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Build output must remain outside the source checkout' }
NewDir $output
foreach ($directory in @('Generated','Install','Measurements','NormalizedIL','PassA','PassB','TargetStaging','Tools')) { New-Item -ItemType Directory -Path (Join-Path $output $directory) | Out-Null }

$registry = ReadJson (Join-Path $packageRoot 'external_utility_registry.json')
function Utility([string]$Role) {
    $rows = @($registry.utilities | Where-Object { [string]$_.role -ceq $Role })
    if ($rows.Count -ne 1) { throw "Utility role invalid: $Role" }
    $path = [IO.Path]::GetFullPath([string]$rows[0].path)
    if ((Hash $path) -cne [string]$rows[0].measurement.sha256 -or (Get-Item -LiteralPath $path).Length -ne [long]$rows[0].measurement.size) { throw "Utility drift: $Role" }
    return $rows[0]
}
$gitRow = Utility 'GIT_BUILD_AND_VERIFICATION'
$cscRow = Utility 'CSC_COMPILER'
$ildasmRow = Utility 'ILDASM_TOOL'
$powershellRow = Utility 'POWERSHELL_ORCHESTRATOR'
$git = [string]$gitRow.path
$csc = [string]$cscRow.path
$ildasm = [string]$ildasmRow.path
$referenceRoles = @('COMPILER_REFERENCE_mscorlib.dll','COMPILER_REFERENCE_System.dll','COMPILER_REFERENCE_System.Core.dll','COMPILER_REFERENCE_System.Security.dll','COMPILER_REFERENCE_System.ServiceProcess.dll')
$referenceRows = @($referenceRoles | ForEach-Object { Utility $_ })
$refs = @($referenceRows | ForEach-Object { [string]$_.path })

$safeRepository = $repositoryRoot.Replace('\','/')
$head = (& $git --no-pager -c "safe.directory=$safeRepository" -C $repositoryRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $head -cne $SourceCommit) { throw 'Source HEAD mismatch' }
$status = @(& $git --no-pager -c "safe.directory=$safeRepository" -C $repositoryRoot status --porcelain=v1 --untracked-files=all)
if (-not $CandidateWorktree -and $status.Count -ne 0) { throw 'Exact source checkout is not clean' }
$repositoryClean = $status.Count -eq 0
& $git --no-pager -c "safe.directory=$safeRepository" -C $repositoryRoot diff --cached --quiet
$indexClean = $LASTEXITCODE -eq 0
if (-not $indexClean) { throw 'Cached index is not clean' }
$sourceIdentityClass = if ($CandidateWorktree) { 'CANDIDATE_CONTENT_DERIVATION_V1' } else { 'EXACT_COMMIT_AND_TREE' }
$tree = if ($CandidateWorktree) { '' } else { (& $git --no-pager -c "safe.directory=$safeRepository" -C $repositoryRoot show -s --format=%T $SourceCommit).Trim() }

$sourcePaths = @(Get-ChildItem -LiteralPath (Join-Path $packageRoot 'Source') -Filter '*.cs' -File | Sort-Object Name | ForEach-Object FullName)
$contractPath = Join-Path $packageRoot 'BuildInputs\R7BuildIdentityContract.cs'
if ($sourcePaths.Count -eq 0 -or -not (Test-Path -LiteralPath $contractPath -PathType Leaf)) { throw 'Compiler source inventory is incomplete' }
$committedCompilerPaths = @($sourcePaths + $contractPath)
$sourceRows = [Collections.Generic.List[object]]::new()
$sourceClosureParts = [Collections.Generic.List[string]]::new()
foreach ($path in $committedCompilerPaths) {
    $relative = (Relative $repositoryRoot $path)
    $treeRow = @(& $git --no-pager -c "safe.directory=$safeRepository" -C $repositoryRoot ls-tree -l $SourceCommit -- $relative)
    if ($treeRow.Count -ne 1 -or [string]$treeRow[0] -notmatch '^(100644) blob ([0-9a-f]{40})\s+([0-9]+)\t') { throw "Committed compiler input absent or non-regular: $relative" }
    $mode=$Matches[1];$treeBlob=$Matches[2];$treeSize=[long]$Matches[3]
    $row = ExactCheckoutCompilerInput $path $relative $treeBlob $mode $treeSize
    if(-not[bool]$row.compiler_input_authority){throw ("Committed compiler input authority failed: $relative/$($row.rejection_reason)")}
    $sourceRows.Add($row)
    $sourceClosureParts.Add(($relative+'|'+$treeBlob+'|'+$row.raw_worktree_blob_identity+'|'+$row.raw_sha256+'|'+$row.size+'|'+$row.tree_size+'|'+$row.clean_filtered_worktree_blob_identity+'|'+$row.raw_tree_exact_equal+'|'+$row.clean_filtered_tree_equal+'|'+$row.eol_normalized_tree_equal+'|'+$row.eol_only_exception+'|'+$mode))
}
if ($CandidateWorktree) { $tree = (Derive 'R7_UNIT2_CANDIDATE_TREE_V1' @($sourceClosureParts.ToArray())).Substring(0,40) }

$bootstrapPath = [IO.Path]::GetFullPath($BootstrapRecord)
$certificatePath = [IO.Path]::GetFullPath($UpgradePublicCertificate)
$preflightPath = [IO.Path]::GetFullPath($PreflightHostState)
$bootstrap = ReadJson $bootstrapPath
$certSha = Hash $certificatePath
if ([string]$bootstrap.source_commit -cne $bootstrapCommit -or [string]$bootstrap.source_tree -cne $bootstrapTree -or [string]$bootstrap.provisioning_script_sha256 -cne $bootstrapProvisioningScriptSha256 -or [string]$bootstrap.service_sid -cne $upgradeSid -or [string]$bootstrap.public_certificate_sha256 -cne $certSha -or [string]$bootstrap.public_export_sha256 -cne $certSha -or $bootstrap.private_key_exported -ne $false -or $bootstrap.recovered_acl_mutation_in_current_attempt -ne $false) { throw 'Preserved Unit 2A bootstrap binding invalid' }
$preflight = ReadJson $preflightPath
if ([string]$preflight.artifact_type -cne 'R7_REMEDIATION_HOST_STATE_CAPTURE' -or [string]$preflight.phase -cne 'PRECHANGE' -or [int64]$preflight.ledger_entry_file_count -ne 678 -or [string]$preflight.checkpoint.raw_sha256 -cne $terminalCheckpointSha256) { throw 'Preflight host-state binding invalid' }
$terminalRows = @($preflight.terminal_authority_services | Where-Object { [string]$_.name -ceq 'RandleTerminalAuthority' })
if ($terminalRows.Count -ne 1 -or [string]$terminalRows[0].state -cne 'Running' -or [string]$terminalRows[0].binary_sha256 -cne $terminalBinarySha256) { throw 'Preflight terminal authority binding invalid' }

$targetSummaryPath = Join-Path $target 'build_summary.json'
$targetOrchestratorReceiptPath = Join-Path $target 'Generated\build_orchestrator_receipt.json'
$targetReceiptPath = Join-Path $target 'Generated\build_receipt.json'
$targetTemplatePath = Join-Path $target 'Generated\transition_request_template.json'
$dependencyPath = Join-Path $target 'Generated\dependency_manifest.json'
$targetPolicyPath = Join-Path $target 'Generated\terminal_authority_v4_policy.json'
$targetManifestPath = Join-Path $target 'Generated\authority_package_manifest.json'
$terminalKeyMetadataPath = Join-Path $target 'Generated\terminal_key_file_metadata.json'
$upgradeKeyMetadataPath = Join-Path $target 'Generated\upgrade_key_file_metadata.json'
foreach ($required in @($targetSummaryPath,$targetOrchestratorReceiptPath,$targetReceiptPath,$targetTemplatePath,$dependencyPath,$targetPolicyPath,$targetManifestPath,$terminalKeyMetadataPath,$upgradeKeyMetadataPath)) { if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Target build input missing: $required" } }
$targetSummary = ReadJson $targetSummaryPath
if ([string]$targetSummary.source_commit -cne $unit1Commit -or [string]$targetSummary.source_tree -cne $unit1Tree) { throw 'Target source identity mismatch' }
$targetOrchestratorReceiptSha = Hash $targetOrchestratorReceiptPath
$targetReceiptSha = Hash $targetReceiptPath
$dependencySha = Hash $dependencyPath
$targetPolicySha = Hash $targetPolicyPath
$targetManifestSha = Hash $targetManifestPath
$targetTemplate = ReadJson $targetTemplatePath
if ([string]$targetTemplate.build_receipt_sha256 -cne $targetReceiptSha -or [string]$targetTemplate.dependency_manifest_sha256 -cne $dependencySha) { throw 'Target template binding invalid' }
$terminalKey = ReadJson $terminalKeyMetadataPath
$upgradeKey = ReadJson $upgradeKeyMetadataPath
if ([string]$terminalKey.owner_sid -cne 'S-1-5-18' -or [string]$upgradeKey.owner_sid -cne 'S-1-5-18' -or [long]$terminalKey.hard_link_count -ne 1 -or [long]$upgradeKey.hard_link_count -ne 1 -or [string]$upgradeKey.canonical_path -cne ('C:\ProgramData\Microsoft\Crypto\Keys\' + [string]$bootstrap.key_unique_name)) { throw 'Committed key-metadata input invalid' }

$requirementPath = Join-Path $packageRoot 'governed_requirement_registry.json'
$casePath = Join-Path $packageRoot 'immutable_case_definitions.json'
$expectationPath = Join-Path $packageRoot 'immutable_expectations.json'
$coveragePath = Join-Path $packageRoot 'exact_byte_coverage_proof.json'
$authorityManifestPath = Join-Path $packageRoot 'AuthoritySources\authority_source_manifest.json'
$historyPath = Join-Path $packageRoot 'historical_classification_registry.json'
$principalPath = Join-Path $packageRoot 'service_principal_registry.json'
$scriptRegistryPath = Join-Path $packageRoot 'governed_script_registry.json'
$utilityRegistryPath = Join-Path $packageRoot 'external_utility_registry.json'
$scopePath = Join-Path $packageRoot 'unit2_authorization_scope.json'
$negativeCasesPath = Join-Path $packageRoot 'unit2_build_closure_negative_cases.json'
$installContractPath = Join-Path $packageRoot 'unit2_stopped_install_contract.json'
$hardenerPath = Join-Path $packageRoot 'complete_unit2_upgrade_authority.ps1'
$scriptSha = Hash $PSCommandPath
$scriptBlob = GitBlob $PSCommandPath

$configurationPaths = [ordered]@{
    AUTHORITY_SOURCE_MANIFEST=$authorityManifestPath; BOOTSTRAP_RECORD=$bootstrapPath; CASE_DEFINITIONS=$casePath; COVERAGE_PROOF=$coveragePath;
    DEPENDENCY_MANIFEST=$dependencyPath; EXPECTATIONS=$expectationPath; HISTORICAL_CLASSIFICATION_REGISTRY=$historyPath; NEGATIVE_CASE_REGISTRY=$negativeCasesPath;
    PREFLIGHT_HOST_STATE=$preflightPath; PRINCIPAL_REGISTRY=$principalPath; REQUIREMENT_REGISTRY=$requirementPath; SCRIPT_REGISTRY=$scriptRegistryPath;
    TARGET_AUTHORITY_PACKAGE_MANIFEST=$targetManifestPath; TARGET_BUILD_ORCHESTRATOR_RECEIPT=$targetOrchestratorReceiptPath; TARGET_BUILD_RECEIPT=$targetReceiptPath;
    TARGET_BUILD_SUMMARY=$targetSummaryPath; TARGET_POLICY=$targetPolicyPath; TARGET_TRANSITION_TEMPLATE=$targetTemplatePath; TERMINAL_KEY_METADATA=$terminalKeyMetadataPath;
    UNIT2_AUTHORIZATION_SCOPE=$scopePath; UNIT2_COMPLETION_SCRIPT=$hardenerPath; UNIT2_STOPPED_INSTALL_CONTRACT=$installContractPath; UPGRADE_KEY_METADATA=$upgradeKeyMetadataPath; UPGRADE_PUBLIC_CERTIFICATE=$certificatePath;
    UTILITY_REGISTRY=$utilityRegistryPath
}
$configurationRows = [Collections.Generic.List[object]]::new()
$configurationClosureParts = [Collections.Generic.List[string]]::new()
foreach ($entry in $configurationPaths.GetEnumerator() | Sort-Object Key) {
    if (-not (Test-Path -LiteralPath $entry.Value -PathType Leaf)) { throw "Configuration input absent: $($entry.Key)" }
    $row = [ordered]@{path=[IO.Path]::GetFullPath([string]$entry.Value);raw_sha256=(Hash ([string]$entry.Value));role=[string]$entry.Key;size=(Get-Item -LiteralPath ([string]$entry.Value)).Length}
    $configurationRows.Add($row)
    $configurationClosureParts.Add(($row.role + '|' + $row.raw_sha256 + '|' + $row.size))
}

$components = [Collections.Generic.List[object]]::new()
$componentPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($component in @($targetTemplate.components)) {
    $components.Add([ordered]@{final_path=[string]$component.final_path;role=[string]$component.role;sha256=[string]$component.sha256;staging_relative_path=[string]$component.staging_relative_path})
    [void]$componentPaths.Add([string]$component.staging_relative_path)
}
$targetManifest = ReadJson $targetManifestPath
$extraIndex = 0
foreach ($file in @($targetManifest.files | Sort-Object staging_relative_path)) {
    if ($componentPaths.Contains([string]$file.staging_relative_path)) { continue }
    $components.Add([ordered]@{final_path=[string]$file.final_path;role=('PACKAGE_FILE_' + $extraIndex.ToString('D4') + '_' + ([string]$file.raw_sha256).Substring(0,16));sha256=[string]$file.raw_sha256;staging_relative_path=[string]$file.staging_relative_path})
    [void]$componentPaths.Add([string]$file.staging_relative_path)
    $extraIndex++
}
$targetPackagedExecutables = [Collections.Generic.List[object]]::new()
foreach ($executable in Get-ChildItem -LiteralPath (Join-Path $target 'Staging') -Filter '*.exe' -File -Recurse | Sort-Object FullName) {
    $identity = ExtractPackagedIdentity $executable.FullName
    if ($identity.Count -eq 0) { throw "Target packaged executable omits governed build identity: $($executable.FullName)" }
    foreach ($field in $identity.GetEnumerator()) {
        if (IsForbiddenIdentityValue $field.Value) { throw "Target packaged executable contains forbidden identity: $($executable.FullName)/$($field.Key)" }
    }
    $relativeExecutable = 'Staging/' + $executable.FullName.Substring((Join-Path $target 'Staging').Length + 1).Replace('\','/')
    $targetPackagedExecutables.Add([ordered]@{embedded_identity=$identity;path=$relativeExecutable;raw_sha256=(Hash $executable.FullName);size=$executable.Length})
}
$componentClosure = @($components | Sort-Object role | ForEach-Object { ([string]$_.role + '|' + [string]$_.staging_relative_path + '|' + [string]$_.sha256 + '|' + [string]$_.final_path) })
$targetComponentSetSha = Derive 'R7_UNIT2_TARGET_COMPONENT_SET_V1' $componentClosure
$fixedRoots = @('C:\Program Files\RandleAI\TerminalUpgradeAuthority','C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Config','C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Ledger','C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Trust','C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Evidence','C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Responses','C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Objects','C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Authorizations','C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Recovery','C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Staging')
$fixedRootsSha = Derive 'R7_UNIT2_FIXED_ROOTS_V1' $fixedRoots
$toolchainClosure = @(
    ('CSC|' + (Hash $csc) + '|' + (Get-Item -LiteralPath $csc).Length),
    ('ILDASM|' + (Hash $ildasm) + '|' + (Get-Item -LiteralPath $ildasm).Length),
    ('GIT|' + (Hash $git) + '|' + (Get-Item -LiteralPath $git).Length),
    ('POWERSHELL|' + (Hash ([string]$powershellRow.path)) + '|' + (Get-Item -LiteralPath ([string]$powershellRow.path)).Length)
)
foreach ($reference in $refs) { $toolchainClosure += ('REFERENCE|' + (Hash $reference) + '|' + (Get-Item -LiteralPath $reference).Length) }
$roleDefinitions = @(
    [ordered]@{role='BUILD_BOOTSTRAP_ARTIFACT_TOOL';name='R7ArtifactTool.build-bootstrap.exe';main='RandleAI.R7Remediation.R7ArtifactToolProgram';define='UNIT2_BUILD_BOOTSTRAP_ARTIFACT_TOOL';identity='bootstrap';intended='DISPOSABLE_BUILD_ONLY'},
    [ordered]@{role='BUILD_BOOTSTRAP_PROTECTED_METADATA_TOOL';name='R7ProtectedMetadataTool.build-bootstrap.exe';main='RandleAI.R7Remediation.R7ArtifactToolProgram';define='UNIT2_BUILD_BOOTSTRAP_PROTECTED_METADATA_TOOL';identity='bootstrap';intended='DISPOSABLE_BUILD_ONLY'},
    [ordered]@{role='UPGRADE_CLIENT';name='RandleTerminalUpgradeClient.exe';main='RandleAI.R7Remediation.R7Unit2UpgradeClientProgram';define='UNIT2_CLIENT';identity='client';intended='C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradeClient.exe'},
    [ordered]@{role='UPGRADE_PUBLIC_VERIFIER';name='RandleTerminalUpgradePublicVerifier.exe';main='RandleAI.R7Remediation.R7Unit2UpgradePublicVerifierProgram';define='UNIT2_PUBLIC_VERIFIER';identity='client';intended='C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradePublicVerifier.exe'},
    [ordered]@{role='UPGRADE_PROTOCOL_PROBE';name='RandleTerminalUpgradeProtocolProbe.exe';main='RandleAI.R7Remediation.R7Unit2UpgradeProbeProgram';define='UNIT2_PROTOCOL_PROBE';identity='client';intended='C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradeProtocolProbe.exe'},
    [ordered]@{role='UPGRADE_AUTHORITY';name='RandleTerminalUpgradeAuthority.exe';main='RandleAI.R7Remediation.R7Unit2UpgradeServiceProgram';define='UNIT2_SERVICE';identity='service';intended='C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradeAuthority.exe'},
    [ordered]@{role='PACKAGED_ARTIFACT_TOOL';name='R7ArtifactTool.exe';main='RandleAI.R7Remediation.R7ArtifactToolProgram';define='UNIT2_PACKAGED_ARTIFACT_TOOL';identity='tools';intended='C:\ProgramData\RandleAI\TerminalUpgradeAuthority\BuildTools\R7ArtifactTool.exe'},
    [ordered]@{role='PACKAGED_PROTECTED_METADATA_TOOL';name='R7ProtectedMetadataTool.exe';main='RandleAI.R7Remediation.R7ArtifactToolProgram';define='UNIT2_PACKAGED_PROTECTED_METADATA_TOOL';identity='tools';intended='C:\ProgramData\RandleAI\TerminalUpgradeAuthority\BuildTools\R7ProtectedMetadataTool.exe'}
)
$roleClosure = @($roleDefinitions | ForEach-Object { ([string]$_.role + '|' + [string]$_.main + '|' + [string]$_.define + '|' + [string]$_.name + '|' + [string]$_.intended) })
$buildInputClosureSha = Derive 'R7_UNIT2_BUILD_INPUT_CLOSURE_V2' @($sourceClosureParts.ToArray() + $configurationClosureParts.ToArray() + $toolchainClosure + $compilerOptions + $roleClosure + $componentClosure)
$sourceReceiptDerivationSha = Derive 'R7_UNIT2_SOURCE_TO_BINARY_RECEIPT_DERIVATION_V1' @($buildInputClosureSha,$SourceCommit,$tree)
$determinismDerivationSha = Derive 'R7_UNIT2_DETERMINISM_RECEIPT_DERIVATION_V1' @($buildInputClosureSha,$SourceCommit,$tree)
$clientPolicyDerivationSha = Derive 'R7_UNIT2_CLIENT_POLICY_BINDING_DERIVATION_V1' @($buildInputClosureSha,$certSha,$dependencySha,$targetReceiptSha)
$hostIdentitySha = Derive 'R7_UNIT2_HOST_IDENTITY_V1' @($terminalLedgerId,$terminalSid,[string]$upgradeKey.volume_identity,$terminalTrustSha256,$terminalPolicySha256,$terminalBinarySha256,$terminalLedgerRoot,$terminalCheckpointSha256)

$identityCommon = [ordered]@{
    IdentitySchemaVersion='2.0.0';IdentityBindingKind='EXACT_CONTENT_AND_NONCIRCULAR_DERIVATION_V1';BuildInputClosureSha256=$buildInputClosureSha;
    SourceToBinaryReceiptDerivationSha256=$sourceReceiptDerivationSha;DeterminismReceiptDerivationSha256=$determinismDerivationSha;
    UpgradePublicCertificateSha256=$certSha;UpgradeCertificateSha256=$certSha;UpgradePublicKeyIdentity=$certSha;DependencyManifestSha256=$dependencySha;
    UpgradeBinaryPath='C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradeAuthority.exe';SourceCommit=$SourceCommit;SourceTree=$tree;
    RequirementRegistrySha256=(Hash $requirementPath);CaseDefinitionsSha256=(Hash $casePath);ExpectationsSha256=(Hash $expectationPath);CoverageProofSha256=(Hash $coveragePath);
    AuthoritySourceManifestSha256=(Hash $authorityManifestPath);HistoricalClassificationRegistrySha256=(Hash $historyPath);ScriptRegistrySha256=(Hash $scriptRegistryPath);UtilityRegistrySha256=(Hash $utilityRegistryPath);
    FixedRootsSha256=$fixedRootsSha;TargetBuildReceiptSha256=$targetReceiptSha;TargetOrchestratorReceiptSha256=$targetOrchestratorReceiptSha;TargetComponentSetSha256=$targetComponentSetSha;
    HostIdentitySha256=$hostIdentitySha;InterfaceIdentity='1.0.0';ProtocolIdentity='4.0';PipeIdentity='RandleAI.TerminalUpgradeAuthority.v1';TerminalServiceSid=$terminalSid;UpgradeServiceSid=$upgradeSid;
    TerminalPublicTrustSha256=$terminalTrustSha256;TerminalPolicySha256=$terminalPolicySha256;TerminalBinarySha256=$terminalBinarySha256;TerminalLedgerIdentity=$terminalLedgerId;TerminalLedgerRoot=$terminalLedgerRoot;TerminalCheckpointSha256=$terminalCheckpointSha256;
    ExecutionBinaryPath='C:\Program Files\RandleAI\TerminalAuthorityV4\RandleTerminalExecution.exe';ObservationBinaryPath='C:\Program Files\RandleAI\TerminalAuthorityV4\RandleTerminalObservation.exe';ComparatorBinaryPath='C:\Program Files\RandleAI\TerminalAuthorityV4\RandleTerminalComparator.exe';
    TerminalKeyFilePath=[string]$terminalKey.canonical_path;TerminalKeyFileIdentity=[string]$terminalKey.file_identity;TerminalKeyFileOwnerSid=[string]$terminalKey.owner_sid;TerminalKeyFileSecurityDescriptorSha256=[string]$terminalKey.security_descriptor_sha256;TerminalKeyFileVolumeIdentity=[string]$terminalKey.volume_identity;TerminalKeyFileLinkCount=[uint32]$terminalKey.hard_link_count;
    UpgradeKeyFilePath=[string]$upgradeKey.canonical_path;UpgradeKeyFileIdentity=[string]$upgradeKey.file_identity;UpgradeKeyFileOwnerSid=[string]$upgradeKey.owner_sid;UpgradeKeyFileSecurityDescriptorSha256=[string]$upgradeKey.security_descriptor_sha256;UpgradeKeyFileVolumeIdentity=[string]$upgradeKey.volume_identity;UpgradeKeyFileLinkCount=[uint32]$upgradeKey.hard_link_count;
    UpgradeKeyCanonicalAclSha256=[string]$bootstrap.key_file_acl_sha256
}
function ValuesWithPolicy([string]$PolicySha,[string]$BindingKind) {
    $values = [ordered]@{}
    foreach ($key in $identityCommon.Keys) { $values[$key] = $identityCommon[$key] }
    $values['UpgradePolicySha256'] = $PolicySha
    $values['UpgradePolicyBindingKind'] = $BindingKind
    return $values
}
function Unit2Values([string]$PolicySha,[string]$BindingKind) {
    return [ordered]@{
        PublicCertificateSha256=$certSha;PolicySha256=$PolicySha;DependencyManifestSha256=$dependencySha;SourceCommit=$SourceCommit;SourceTree=$tree;
        KeyFilePath=[string]$upgradeKey.canonical_path;KeyFileOwnerSid=[string]$upgradeKey.owner_sid;KeyFileSecurityDescriptorSha256=[string]$upgradeKey.security_descriptor_sha256;
        KeyFileVolumeIdentity=[string]$upgradeKey.volume_identity;KeyFileIdentity=[string]$upgradeKey.file_identity;KeyFileLinkCount=[uint32]$upgradeKey.hard_link_count;
        BuildInputClosureSha256=$buildInputClosureSha;PolicyBindingKind=$BindingKind
    }
}
$generatorInputs = @($configurationRows | ForEach-Object { [ordered]@{identity=[string]$_.raw_sha256;role=[string]$_.role} })
$generatorInputs += @($sourceRows | ForEach-Object { [ordered]@{identity=[string]$_.raw_sha256;role=('COMPILER_SOURCE:' + [string]$_.path)} })
$generatorInputs += @([ordered]@{identity=$buildInputClosureSha;role='BUILD_INPUT_CLOSURE'},[ordered]@{identity=$scriptSha;role='GENERATOR_SCRIPT'})

$bootstrapIdentityPath = Join-Path $output 'Generated\R7Unit2BuildBootstrap.g.cs'
$bootstrapValues = ValuesWithPolicy $clientPolicyDerivationSha 'NONCIRCULAR_INPUT_CLOSURE_DERIVATION_V1'
IdentitySource $bootstrapIdentityPath $bootstrapValues (Unit2Values $clientPolicyDerivationSha 'NONCIRCULAR_INPUT_CLOSURE_DERIVATION_V1')
$bootstrapGeneratedRow = GeneratedRow $bootstrapIdentityPath 'R7_UNIT2_BUILD_BOOTSTRAP_IDENTITY_V2' $scriptSha $scriptBlob $generatorInputs

$roleResults = [Collections.Generic.List[object]]::new()
$roleState = @{}
function BuildRole([object]$Role,[string]$IdentityPath,[object]$ExpectedIdentity,[object]$ExpectedUnit2,[object]$GeneratedSourceRow) {
    $passA = Join-Path $output ('PassA\' + [string]$Role.name)
    $passB = Join-Path $output ('PassB\' + [string]$Role.name)
    $argumentsA = CompilerArguments $Role $passA $refs $committedCompilerPaths $IdentityPath
    $argumentsB = CompilerArguments $Role $passB $refs $committedCompilerPaths $IdentityPath
    Compile $csc $argumentsA $passA ([string]$Role.role)
    [Threading.Thread]::Sleep(1100)
    Compile $csc $argumentsB $passB ([string]$Role.role)
    $ilAPath = Join-Path $output ('NormalizedIL\' + [string]$Role.name + '.pass-a.il')
    $ilBPath = Join-Path $output ('NormalizedIL\' + [string]$Role.name + '.pass-b.il')
    $ilA = NormalizeIl $passA $ilAPath $ildasm
    $ilB = NormalizeIl $passB $ilBPath $ildasm
    if ($ilA -cne $ilB) { throw "Normalized IL mismatch: $($Role.role)" }
    $embedded = ExtractIdentity $passA
    AssertIdentity $ExpectedIdentity $ExpectedUnit2 $embedded ([string]$Role.role)
    $inputRows = @($sourceRows | ForEach-Object { [ordered]@{generation_rule=$null;generator=$null;schema_version=[string]$_.schema_version;source_identity_class=[string]$_.source_identity_class;git_blob_identity=[string]$_.git_blob_identity;mode=[string]$_.mode;path=[string]$_.path;tree_size=[long]$_.tree_size;raw_worktree_blob_identity=[string]$_.raw_worktree_blob_identity;raw_sha256=[string]$_.raw_sha256;size=[long]$_.size;clean_filtered_worktree_blob_identity=[string]$_.clean_filtered_worktree_blob_identity;raw_tree_exact_equal=[bool]$_.raw_tree_exact_equal;clean_filtered_tree_equal=[bool]$_.clean_filtered_tree_equal;eol_normalized_tree_equal=[bool]$_.eol_normalized_tree_equal;eol_only_exception=[bool]$_.eol_only_exception;non_eol_difference=[bool]$_.non_eol_difference;raw_eol=[string]$_.raw_eol;index_eol=[string]$_.index_eol;worktree_eol=[string]$_.worktree_eol;encoding=[string]$_.encoding;text_attribute=[string]$_.text_attribute;eol_attribute=[string]$_.eol_attribute;filter_attribute=[string]$_.filter_attribute;working_tree_encoding_attribute=[string]$_.working_tree_encoding_attribute;custom_filter_present=[bool]$_.custom_filter_present;external_filter_required=[bool]$_.external_filter_required;approved_file_type=[bool]$_.approved_file_type;tracked_path=[bool]$_.tracked_path;tree_entry_present=[bool]$_.tree_entry_present;repository_clean=[bool]$_.repository_clean;index_clean=[bool]$_.index_clean;staged_mutation=[bool]$_.staged_mutation;unstaged_semantic_mutation=[bool]$_.unstaged_semantic_mutation;untracked_replacement=[bool]$_.untracked_replacement;symlink_substitution=[bool]$_.symlink_substitution;path_redirection=[bool]$_.path_redirection;candidate_worktree=[bool]$_.candidate_worktree;final_newline_matches=[bool]$_.final_newline_matches;bom_matches=[bool]$_.bom_matches;compiler_input_authority=[bool]$_.compiler_input_authority;rejection_reason=[string]$_.rejection_reason} })
    $inputRows += [ordered]@{generation_rule=[string]$GeneratedSourceRow.generation_rule;generator=$GeneratedSourceRow.generator;git_blob_identity=$null;mode=$null;path=[string]$GeneratedSourceRow.path;raw_sha256=[string]$GeneratedSourceRow.raw_sha256;size=[long]$GeneratedSourceRow.size}
    $result = [ordered]@{
        architecture='x64';compiler_arguments=[ordered]@{pass_a=@($argumentsA);pass_b=@($argumentsB)};compiler_inputs=$inputRows;define=[string]$Role.define;
        embedded_identity=$embedded;file_name=[string]$Role.name;generated_source_sha256=(Hash $IdentityPath);intended_future_installation_path=[string]$Role.intended;
        main=[string]$Role.main;normalized_il_equal=$true;normalized_il_sha256=$ilA;pass_a_path=$passA;pass_a_sha256=(Hash $passA);pass_b_path=$passB;pass_b_sha256=(Hash $passB);
        platform='x64';preprocessor_symbols=@([string]$Role.define);resource_files=@();response_files=@();role=[string]$Role.role;size=(Get-Item -LiteralPath $passA).Length;
        standard_library_behavior='NOSTDLIB_EXPLICIT_REFERENCES';target_type='exe'
    }
    $roleResults.Add($result)
    $roleState[[string]$Role.role] = $result
}

$bootstrapUnit2Values = Unit2Values $clientPolicyDerivationSha 'NONCIRCULAR_INPUT_CLOSURE_DERIVATION_V1'
foreach ($role in @($roleDefinitions | Where-Object { [string]$_.identity -ceq 'bootstrap' })) { BuildRole $role $bootstrapIdentityPath $bootstrapValues $bootstrapUnit2Values $bootstrapGeneratedRow }
$artifactBootstrap = [string]$roleState.BUILD_BOOTSTRAP_ARTIFACT_TOOL.pass_a_path

$hostCore = [ordered]@{terminal_ledger_id=$terminalLedgerId;terminal_public_trust_sha256=$terminalTrustSha256;terminal_service_sid=$terminalSid;volume_identity=[string]$upgradeKey.volume_identity}
$hostCorePath = Join-Path $output 'Generated\host_identity_input.json'
Canonical $hostCore $hostCorePath $artifactBootstrap
$hostIdentity = Hash $hostCorePath
$targetBindings = [ordered]@{authority_package_manifest_sha256=$targetManifestSha;build_orchestrator_receipt_sha256=$targetOrchestratorReceiptSha;build_receipt_sha256=$targetReceiptSha;case_definitions_sha256=(Hash $casePath);dependency_manifest_sha256=$dependencySha;expectations_sha256=(Hash $expectationPath);expected_terminal_ledger_continuity='PRESERVE_SEQUENCE_678_ROOT_AND_CHECKPOINT_UNTIL_SEPARATE_INSTALL_UNIT';expected_terminal_public_trust_sha256=$terminalTrustSha256;interface_version='4.0.0-REMEDIATION';principal_registry_sha256=(Hash $principalPath);requirement_registry_sha256=(Hash $requirementPath);script_registry_sha256=(Hash $scriptRegistryPath);terminal_policy_sha256=$targetPolicySha;utility_registry_sha256=(Hash $utilityRegistryPath)}
$authorityBindings = [ordered]@{bootstrap_source_commit=$bootstrapCommit;bootstrap_source_tree=$bootstrapTree;fourth_failed_bootstrap_attempt_sha256=[string]$bootstrap.fourth_failed_attempt_sha256;independent_rejection_commit='9d813a4bad29ec04f022f54ffcae73a5d542eb44';preflight_baseline_sha256=(Hash $preflightPath);prior_failed_bootstrap_attempt_sha256=[string]$bootstrap.prior_failed_attempt_sha256;second_failed_bootstrap_attempt_sha256=[string]$bootstrap.second_failed_attempt_sha256;third_failed_bootstrap_attempt_sha256=[string]$bootstrap.third_failed_attempt_sha256;prohibited_source_commit='f0cfbce97e913a133530dd66a70326b1e03a0fb6';prohibited_source_dependency_count=0;provisioned_infrastructure_commit='bb04ac54fb328516d0c785f4e6551e6a20d73759';provisioning_commit=$SourceCommit;r6_commit='87d066eb16d7fe0b6a1677ea7739c5c2ead4ad94';r7_record_commits=@('06c6805ed52a0d539a73088c097c60dec335462a','8ec5697b3c6fd9d93b972113b7e79d033b4cb1f6');unit1_commit=$unit1Commit;unit2_authorization_scope_sha256=(Hash $scopePath)}
$rollback = [ordered]@{automatic_rollback=$false;existing_terminal_ledger_rewrite='PROHIBITED';governed_rollback_authorization_required=$true;rejected_v3_reinstall='PROHIBITED';v1_rollback='PROHIBITED'}
$threat = [ordered]@{excludes=@('kernel','offline_administrator','physical_attack','TPM_or_HSM_claim');protects=@('terminal_self_authorization','caller_selected_components','component_substitution','cross_host_replay','policy_downgrade','interface_downgrade','authorization_replay')}
$plan = [ordered]@{components=$components.ToArray();current_checkpoint_sha256=$terminalCheckpointSha256;current_ledger_root=$terminalLedgerRoot;current_ledger_sequence=678;host_identity=$hostIdentity;target_bindings=$targetBindings;transition_nonce=$transitionNonce}
$planPath = Join-Path $output 'Generated\transition_plan.json'
Canonical $plan $planPath $artifactBootstrap
$planSha = Hash $planPath
$ledgerId = Derive 'R7_UNIT2_UPGRADE_LEDGER_V1' @($certSha,$terminalLedgerId,$SourceCommit)

$clientIdentityPath = Join-Path $output 'Generated\R7Unit2ClientShared.g.cs'
$clientValues = ValuesWithPolicy $clientPolicyDerivationSha 'NONCIRCULAR_INPUT_CLOSURE_DERIVATION_V1'
IdentitySource $clientIdentityPath $clientValues (Unit2Values $clientPolicyDerivationSha 'NONCIRCULAR_INPUT_CLOSURE_DERIVATION_V1')
$clientGeneratedRow = GeneratedRow $clientIdentityPath 'R7_UNIT2_CLIENT_SHARED_IDENTITY_V2' $scriptSha $scriptBlob $generatorInputs
$clientUnit2Values = Unit2Values $clientPolicyDerivationSha 'NONCIRCULAR_INPUT_CLOSURE_DERIVATION_V1'
foreach ($role in @($roleDefinitions | Where-Object { [string]$_.identity -ceq 'client' })) { BuildRole $role $clientIdentityPath $clientValues $clientUnit2Values $clientGeneratedRow }

$policy = [ordered]@{
    artifact_type='R7_UNIT2_SEPARATE_UPGRADE_AUTHORITY_POLICY';authority_bindings=$authorityBindings;authorization_expiration=$expiration;authorization_scope_sha256=(Hash $scopePath);bootstrap_authority='EXPLICIT_R7_REMEDIATION_UNIT_2_AUTHORIZATION';dependency_manifest_sha256=$dependencySha;
    fixed_roots=$fixedRoots;host_binding=[ordered]@{checkpoint_sha256=$terminalCheckpointSha256;host_identity=$hostIdentity;terminal_interface='3.0.0-DRAFT';terminal_ledger_id=$terminalLedgerId;terminal_ledger_root=$terminalLedgerRoot;terminal_ledger_sequence=678;terminal_policy_sha256=$terminalPolicySha256;terminal_public_trust_sha256=$terminalTrustSha256;terminal_service_binary_sha256=$terminalBinarySha256;terminal_service_name='RandleTerminalAuthority';terminal_service_sid=$terminalSid;volume_identity=[string]$upgradeKey.volume_identity};
    installer_script_sha256=[string]$targetTemplate.installer_identity.script_sha256;interface_version='1.0.0';key=[ordered]@{algorithm='RSA-3072';export_policy='NONEXPORTABLE';key_unique_name=[string]$bootstrap.key_unique_name;provider='Microsoft Software Key Storage Provider';scope='LocalMachine';signature_algorithm='RSA-PSS-SHA256'};ledger_id=$ledgerId;minimum_terminal_version='4.0.0-REMEDIATION';operation_allowlist=@('AUTHORIZE_TERMINAL_TRANSITION','GET_AUTHORIZATION','GET_HEALTH','GET_PUBLIC_IDENTITY');preflight_baseline_sha256=(Hash $preflightPath);protocol_version='4.0';provisioning_nonce=$provisioningNonce;provisioning_script_sha256=(Hash $hardenerPath);public_certificate_sha256=$certSha;required_components=$components.ToArray();revoked_component_sha256=@('632afaeeaf15c26ac057b34692ac672e03bc02f60fbb35177c378736b5e316ba',$terminalBinarySha256,$terminalPolicySha256);rollback_constraints=$rollback;schema_version='2.0.0';service=[ordered]@{account='NT SERVICE\RandleTerminalUpgradeAuthority';denied_logon_rights=@('SeDenyInteractiveLogonRight','SeDenyRemoteInteractiveLogonRight');name='RandleTerminalUpgradeAuthority';pipe='RandleAI.TerminalUpgradeAuthority.v1';required_privileges=@('SeChangeNotifyPrivilege');sid=$upgradeSid;sid_type='RESTRICTED'};source_bindings=[ordered]@{provisioning_commit=$SourceCommit;provisioning_tree=$tree;target_commit=$unit1Commit;target_tree=$unit1Tree;unit1_commit=$unit1Commit;unit1_tree=$unit1Tree};target_bindings=$targetBindings;threat_model=$threat;transition_nonce=$transitionNonce;transition_plan_sha256=$planSha;
    upgrade_client_sha256=[string]$roleState.UPGRADE_CLIENT.pass_a_sha256;upgrade_probe_sha256=[string]$roleState.UPGRADE_PROTOCOL_PROBE.pass_a_sha256;upgrade_public_verifier_sha256=[string]$roleState.UPGRADE_PUBLIC_VERIFIER.pass_a_sha256;volume_identity=[string]$upgradeKey.volume_identity
}
$policyPath = Join-Path $output 'Generated\unit2_upgrade_policy.json'
Canonical $policy $policyPath $artifactBootstrap
$policySha = Hash $policyPath

$serviceIdentityPath = Join-Path $output 'Generated\R7Unit2Service.g.cs'
$serviceValues = ValuesWithPolicy $policySha 'EXACT_POLICY_SHA256'
IdentitySource $serviceIdentityPath $serviceValues (Unit2Values $policySha 'EXACT_POLICY_SHA256')
$serviceInputs = @($generatorInputs + [ordered]@{identity=$policySha;role='COMPLETED_UNIT2_POLICY'})
$serviceGeneratedRow = GeneratedRow $serviceIdentityPath 'R7_UNIT2_SERVICE_IDENTITY_V2' $scriptSha $scriptBlob $serviceInputs
$serviceUnit2Values = Unit2Values $policySha 'EXACT_POLICY_SHA256'
foreach ($role in @($roleDefinitions | Where-Object { [string]$_.identity -ceq 'service' })) { BuildRole $role $serviceIdentityPath $serviceValues $serviceUnit2Values $serviceGeneratedRow }

$toolsIdentityPath = Join-Path $output 'Generated\R7PackagedTools.g.cs'
$toolValues = ValuesWithPolicy $policySha 'EXACT_POLICY_SHA256'
IdentitySource $toolsIdentityPath $toolValues (Unit2Values $policySha 'EXACT_POLICY_SHA256')
$toolsGeneratedRow = GeneratedRow $toolsIdentityPath 'R7_UNIT2_PACKAGED_TOOLS_IDENTITY_V2' $scriptSha $scriptBlob $serviceInputs
$toolsUnit2Values = Unit2Values $policySha 'EXACT_POLICY_SHA256'
foreach ($role in @($roleDefinitions | Where-Object { [string]$_.identity -ceq 'tools' })) { BuildRole $role $toolsIdentityPath $toolValues $toolsUnit2Values $toolsGeneratedRow }

$artifactFinal = [string]$roleState.PACKAGED_ARTIFACT_TOOL.pass_a_path
foreach ($result in $roleResults) {
    $measurementAPath = Join-Path $output ('Measurements\' + [string]$result.role + '.pass-a.json')
    $measurementBPath = Join-Path $output ('Measurements\' + [string]$result.role + '.pass-b.json')
    & $artifactFinal measure ([string]$result.pass_a_path) $measurementAPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Pass-A measurement failed: $($result.role)" }
    & $artifactFinal measure ([string]$result.pass_b_path) $measurementBPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Pass-B measurement failed: $($result.role)" }
    $measurementA = ReadJson $measurementAPath
    $measurementB = ReadJson $measurementBPath
    $result['pass_a_file_identity'] = [string]$measurementA.file_identity
    $result['pass_b_file_identity'] = [string]$measurementB.file_identity
    $result['pass_a_measurement_sha256'] = Hash $measurementAPath
    $result['pass_b_measurement_sha256'] = Hash $measurementBPath
}

$scriptRegistry = ReadJson $scriptRegistryPath
$governedScripts = [Collections.Generic.List[object]]::new()
foreach ($row in @($scriptRegistry.scripts | Sort-Object path)) {
    $path = Join-Path $repositoryRoot ([string]$row.path).Replace('/','\')
    [void](GovernedScriptIdentity $row)
    $governedScripts.Add([ordered]@{git_blob_identity=[string]$row.git_blob_identity;mode=[string]$row.mode;path=[string]$row.path;raw_sha256=[string]$row.raw_sha256;role=[string]$row.role;size=[long]$row.size})
}
$generatedSources = @($bootstrapGeneratedRow,$clientGeneratedRow,$serviceGeneratedRow,$toolsGeneratedRow)
$frameworkReferences = @($referenceRows | ForEach-Object { [ordered]@{path=[string]$_.path;raw_sha256=[string]$_.measurement.sha256;role=[string]$_.role;size=[long]$_.measurement.size} })
$compilerIdentity = [ordered]@{path=$csc;raw_sha256=(Hash $csc);size=(Get-Item -LiteralPath $csc).Length}
$toolchain = @(@($cscRow,$ildasmRow,$gitRow,$powershellRow) | ForEach-Object { [ordered]@{measurement=$_.measurement;role=[string]$_.role} })
$nonCircular = [ordered]@{algorithm='SHA256_UTF8_LENGTH_PREFIXED_FIELDS_V1';build_input_closure_sha256=$buildInputClosureSha;client_policy_binding_derivation_sha256=$clientPolicyDerivationSha;determinism_receipt_derivation_sha256=$determinismDerivationSha;reason='The client raw identities are policy inputs, so client binaries bind the complete pre-policy input closure; service and packaged tools bind the completed policy raw identity.';source_to_binary_receipt_derivation_sha256=$sourceReceiptDerivationSha}
$receipt = [ordered]@{
    artifact_type='R7_UNIT2_UPGRADE_AUTHORITY_SOURCE_TO_BINARY_RECEIPT';build_input_closure_sha256=$buildInputClosureSha;compiler=$compilerIdentity;configuration_inputs=$configurationRows.ToArray();dependency_manifest_sha256=$dependencySha;
    framework_references=$frameworkReferences;generated_sources=$generatedSources;governed_scripts=$governedScripts.ToArray();noncircular_derivations=$nonCircular;policy_sha256=$policySha;roles=@($roleResults | Sort-Object role);
    schema_version='2.1.0';source_commit=$SourceCommit;source_files=$sourceRows.ToArray();source_identity_class=$sourceIdentityClass;source_tree=$tree;target_build_receipt_sha256=$targetReceiptSha;target_packaged_executables=$targetPackagedExecutables.ToArray();target_source_commit=$unit1Commit;target_source_tree=$unit1Tree;toolchain=$toolchain
}
$receiptPath = Join-Path $output 'Generated\unit2_build_receipt.json'
Canonical $receipt $receiptPath $artifactFinal
$determinismRoles = @($roleResults | Sort-Object role | ForEach-Object { [ordered]@{compiler_arguments=$_.compiler_arguments;compiler_inputs=$_.compiler_inputs;file_name=$_.file_name;generated_source_sha256=$_.generated_source_sha256;normalized_il_equal=$_.normalized_il_equal;normalized_il_sha256=$_.normalized_il_sha256;pass_a_sha256=$_.pass_a_sha256;pass_b_sha256=$_.pass_b_sha256;preprocessor_symbols=$_.preprocessor_symbols;resource_files=$_.resource_files;response_files=$_.response_files;role=$_.role;size=$_.size} })
$determinismReceipt = [ordered]@{artifact_type='R7_UNIT2B_BUILD_DETERMINISM_RECEIPT';build_input_closure_sha256=$buildInputClosureSha;compiler=$compilerIdentity;framework_references=$frameworkReferences;generated_sources=$generatedSources;noncircular_derivations=$nonCircular;role_determinism=$determinismRoles;schema_version='2.1.0';source_commit=$SourceCommit;source_files=$sourceRows.ToArray();source_identity_class=$sourceIdentityClass;source_tree=$tree;status='PASS';target_build_orchestrator_receipt_sha256=$targetOrchestratorReceiptSha;target_packaged_executables=$targetPackagedExecutables.ToArray()}
$determinismPath = Join-Path $output 'Generated\unit2_build_determinism_receipt.json'
Canonical $determinismReceipt $determinismPath $artifactFinal

Copy-Item -LiteralPath ([string]$roleState.UPGRADE_AUTHORITY.pass_a_path) -Destination (Join-Path $output 'Install\RandleTerminalUpgradeAuthority.exe')
Copy-Item -LiteralPath ([string]$roleState.UPGRADE_CLIENT.pass_a_path) -Destination (Join-Path $output 'Install\RandleTerminalUpgradeClient.exe')
Copy-Item -LiteralPath ([string]$roleState.UPGRADE_PROTOCOL_PROBE.pass_a_path) -Destination (Join-Path $output 'Install\RandleTerminalUpgradeProtocolProbe.exe')
Copy-Item -LiteralPath ([string]$roleState.UPGRADE_PUBLIC_VERIFIER.pass_a_path) -Destination (Join-Path $output 'Install\RandleTerminalUpgradePublicVerifier.exe')
Copy-Item -LiteralPath $policyPath -Destination (Join-Path $output 'Install\unit2_upgrade_policy.json')
Copy-Item -LiteralPath $dependencyPath -Destination (Join-Path $output 'Install\dependency_manifest.json')
Copy-Item -LiteralPath $receiptPath -Destination (Join-Path $output 'Install\unit2_build_receipt.json')
Copy-Item -LiteralPath $certificatePath -Destination (Join-Path $output 'Install\upgrade_authority_public.cer')
Copy-Item -LiteralPath ([string]$roleState.PACKAGED_ARTIFACT_TOOL.pass_a_path) -Destination (Join-Path $output 'Tools\R7ArtifactTool.exe')
Copy-Item -LiteralPath ([string]$roleState.PACKAGED_PROTECTED_METADATA_TOOL.pass_a_path) -Destination (Join-Path $output 'Tools\R7ProtectedMetadataTool.exe')
foreach ($item in Get-ChildItem -LiteralPath (Join-Path $target 'Staging') -Force) { Copy-Item -LiteralPath $item.FullName -Destination (Join-Path $output 'TargetStaging') -Recurse }

$manifestRows = @(Get-ChildItem -LiteralPath $output -File -Recurse | Where-Object { $_.FullName -notlike '*.raw' -and $_.FullName -notlike '*.raw.il' } | Sort-Object FullName | ForEach-Object { [ordered]@{path=$_.FullName.Substring($output.Length + 1).Replace('\','/');raw_sha256=(Hash $_.FullName);size=$_.Length} })
$manifest = [ordered]@{artifact_type='R7_UNIT2_BUILD_OUTPUT_MANIFEST';build_determinism_receipt_sha256=(Hash $determinismPath);build_receipt_sha256=(Hash $receiptPath);files=$manifestRows;policy_sha256=$policySha;prohibited_source_dependency_count=0;schema_version='2.1.0';self_exclusion='unit2_build_manifest.json';source_commit=$SourceCommit;source_identity_class=$sourceIdentityClass;source_tree=$tree;status='PASS';target_source_commit=$unit1Commit;transition_plan_sha256=$planSha}
$manifestPath = Join-Path $output 'unit2_build_manifest.json'
Canonical $manifest $manifestPath $artifactFinal
[ordered]@{build_determinism_receipt_sha256=(Hash $determinismPath);build_input_closure_sha256=$buildInputClosureSha;build_manifest_sha256=(Hash $manifestPath);build_receipt_sha256=(Hash $receiptPath);output_root=$output;policy_sha256=$policySha;role_count=$roleResults.Count;source_commit=$SourceCommit;source_identity_class=$sourceIdentityClass;source_tree=$tree;status='PASS'} | ConvertTo-Json
