[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string]$CompiledRoleRoot,
    [string]$StaticBuildRoot,
    [string]$Unit2BuildRoot,
    [string]$Unit2ClosureReport,
    [string]$TransactionProbeRoot,
    [string]$RecoveryProbeRoot,
    [string]$LegacySnapshotRoot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$packageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $packageRoot '..\..\..'))
$safeRepository = $repositoryRoot.Replace('\','/')
$gitExecutable = 'C:\Program Files\Git\cmd\git.exe'
$checks = [Collections.Generic.List[object]]::new()

function Add-Check([string]$Name, [bool]$Passed, [object]$Evidence) {
    $checks.Add([ordered]@{ evidence = $Evidence; name = $Name; status = $(if ($Passed) { 'PASS' } else { 'FAIL' }) })
    if (-not $Passed) { throw "Static architecture check failed: $Name" }
}
function Read-Json([string]$Path) { return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json }
function Read-JsonText([string]$Text) { return $Text | ConvertFrom-Json }
function Get-LowerHash([string]$Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function Get-GitBlobIdentity([string]$Path) {
    $bytes=[IO.File]::ReadAllBytes($Path);$header=[Text.Encoding]::ASCII.GetBytes(('blob '+$bytes.Length+[char]0));$all=New-Object byte[] ($header.Length+$bytes.Length)
    [Buffer]::BlockCopy($header,0,$all,0,$header.Length);[Buffer]::BlockCopy($bytes,0,$all,$header.Length,$bytes.Length);$sha=[Security.Cryptography.SHA1]::Create()
    try{return ([BitConverter]::ToString($sha.ComputeHash($all))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
}
function Git-Lines([string[]]$Arguments) {
    $value = @(& $gitExecutable -c "safe.directory=$safeRepository" -C $repositoryRoot @Arguments)
    if ($LASTEXITCODE -ne 0) { throw "git failed: $($Arguments -join ' ')" }
    return $value
}
function Get-RelativePath([string]$Base, [string]$Path) {
    $baseFull = [IO.Path]::GetFullPath($Base).TrimEnd('\') + '\'
    $pathFull = [IO.Path]::GetFullPath($Path)
    return [Uri]::UnescapeDataString(([Uri]$baseFull).MakeRelativeUri([Uri]$pathFull).ToString()).Replace('\','/')
}
function Get-Sha256Bytes([byte[]]$Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
}
function Get-GitBlobIdentityBytes([byte[]]$Bytes) {
    $header = [Text.Encoding]::ASCII.GetBytes(('blob ' + $Bytes.Length + [char]0))
    $all = New-Object byte[] ($header.Length + $Bytes.Length)
    [Buffer]::BlockCopy($header,0,$all,0,$header.Length)
    [Buffer]::BlockCopy($Bytes,0,$all,$header.Length,$Bytes.Length)
    $sha = [Security.Cryptography.SHA1]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($all))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
}
function Get-StrictLfBytes([byte[]]$RawBytes) {
    $bytes = New-Object 'System.Collections.Generic.List[byte]' ($RawBytes.Length)
    $removed = 0; $lone = 0
    for ($index = 0; $index -lt $RawBytes.Length; $index++) {
        if ($RawBytes[$index] -eq 13) {
            if ($index + 1 -lt $RawBytes.Length -and $RawBytes[$index + 1] -eq 10) { $removed++; continue }
            $lone++
        }
        $bytes.Add($RawBytes[$index])
    }
    return [ordered]@{ bytes=$bytes.ToArray(); lone_cr=$lone; removed_crlf_cr=$removed }
}
function Assert-CanonicalRepositoryAuthority {
    $expectedBranch = 'governance/r7-terminal-authority-architecture-remediation-20260723'
    $expectedHead = '3dfcbbebaf603f227e9675c060f4cc92304d89a7'
    $expectedTree = 'a010719c4db2418d6d510ecb19af7b41680250b6'
    if (([string](Git-Lines @('branch','--show-current'))).Trim() -cne $expectedBranch) { throw 'IDENTITY_BRANCH_AUTHORITY_MISMATCH' }
    if (([string](Git-Lines @('rev-parse','HEAD'))).Trim() -cne $expectedHead) { throw 'IDENTITY_COMMIT_AUTHORITY_MISMATCH' }
    if (([string](Git-Lines @('rev-parse','HEAD^{tree}'))).Trim() -cne $expectedTree) { throw 'IDENTITY_TREE_AUTHORITY_MISMATCH' }
    [void](& $gitExecutable -c "safe.directory=$safeRepository" -C $repositoryRoot diff --cached --quiet)
    if ($LASTEXITCODE -eq 1) { throw 'IDENTITY_STAGED_MUTATION' }
    if ($LASTEXITCODE -ne 0) { throw 'IDENTITY_INDEX_QUERY_FAILED' }
    $untracked = @(Git-Lines @('ls-files','--others','--exclude-standard'))
    if ($untracked.Count -ne 0) { throw 'IDENTITY_UNTRACKED_REPLACEMENT' }
    $allowed = @(
        'Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/build_unit2_upgrade_authority.ps1',
        'Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/generate_static_closure_registries.ps1',
        'Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/generate_traceability.ps1',
        'Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/governed_script_registry.json',
        'Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/static_package_file_manifest.json',
        'Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/static_traceability.json',
        'Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/unit2_build_closure_negative_cases.json',
        'Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/verify_static_architecture.ps1',
        'Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/verify_unit2_build_closure.ps1'
    )
    $outside = @(Git-Lines @('diff','--name-only') | Where-Object { $_ -cnotin $allowed })
    if ($outside.Count -ne 0) { throw "IDENTITY_UNAUTHORIZED_WORKTREE_MUTATION: $($outside -join ',')" }
}
function Get-CanonicalRepositoryIdentity([string]$Path, [string]$InputClass, [bool]$AllowCandidateContent) {
    $full = [IO.Path]::GetFullPath($Path); $rootPrefix = $repositoryRoot.TrimEnd('\') + '\'
    if (-not $full.StartsWith($rootPrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "IDENTITY_PATH_OUTSIDE_REPOSITORY: $full" }
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { throw "IDENTITY_INPUT_ABSENT: $full" }
    $item = Get-Item -LiteralPath $full
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "IDENTITY_SYMLINK_SUBSTITUTION: $full" }
    $relative = Get-RelativePath $repositoryRoot $full
    if ($relative.StartsWith('../',[StringComparison]::Ordinal) -or [IO.Path]::IsPathRooted($relative)) { throw "IDENTITY_PATH_REDIRECTION: $relative" }
    [void](Git-Lines @('ls-files','--error-unmatch','--',$relative))
    $treeLine = @(Git-Lines @('ls-tree','HEAD','--',$relative))
    if ($treeLine.Count -ne 1 -or [string]$treeLine[0] -notmatch '^(\d{6})\s+(\w+)\s+([0-9a-f]{40})\t(.+)$') { throw "IDENTITY_TREE_ENTRY_MISSING: $relative" }
    $treeMode=$Matches[1]; $treeType=$Matches[2]; $treeBlob=$Matches[3]; $treePath=$Matches[4]
    if ($treeMode -cne '100644' -or $treeType -cne 'blob' -or $treePath -cne $relative) { throw "IDENTITY_TREE_OBJECT_NOT_APPROVED: $relative" }
    [void](& $gitExecutable -c "safe.directory=$safeRepository" -C $repositoryRoot diff --cached --quiet -- $relative)
    if ($LASTEXITCODE -eq 1) { throw "IDENTITY_STAGED_MUTATION: $relative" }
    if ($LASTEXITCODE -ne 0) { throw "IDENTITY_INDEX_QUERY_FAILED: $relative" }
    $attributes=@{}; foreach($line in @(Git-Lines @('check-attr','text','eol','filter','working-tree-encoding','--',$relative))){if([string]$line -match '^.*?: ([^:]+): (.*)$'){$attributes[$Matches[1]]=$Matches[2]}}
    foreach($required in @('text','eol','filter','working-tree-encoding')){if(-not $attributes.ContainsKey($required)){throw "IDENTITY_DIAGNOSTIC_MISSING_${required}: $relative"}}
    if([string]$attributes.filter -notin @('unspecified','unset')){throw "IDENTITY_CUSTOM_FILTER_REJECTED: $relative"}
    if([string]$attributes.'working-tree-encoding' -notin @('unspecified','unset')){throw "IDENTITY_WORKING_TREE_ENCODING_REJECTED: $relative"}
    $raw=[IO.File]::ReadAllBytes($full); try{[void]([Text.UTF8Encoding]::new($false,$true).GetString($raw))}catch{throw "IDENTITY_UNAUTHORIZED_ENCODING: $relative"}
    if($raw.Length -ge 3 -and $raw[0] -eq 239 -and $raw[1] -eq 187 -and $raw[2] -eq 191){throw "IDENTITY_BOM_REJECTED: $relative"}
    $rawBlob=Get-GitBlobIdentityBytes $raw; $rawSha256=Get-Sha256Bytes $raw
    $filtered=@(Git-Lines @('hash-object',('--path='+$relative),'--',$full)); if($filtered.Count -ne 1 -or [string]$filtered[0] -notmatch '^[0-9a-f]{40}$'){throw "IDENTITY_FILTERED_DIAGNOSTIC_INVALID: $relative"}
    $filteredBlob=[string]$filtered[0]; $normalized=Get-StrictLfBytes $raw; $normalizedBlob=Get-GitBlobIdentityBytes ([byte[]]$normalized.bytes)
    $rawFilteredEqual=$rawBlob -ceq $filteredBlob; $normalizedFilteredEqual=$normalizedBlob -ceq $filteredBlob
    $finalNewlineMatches=(($raw.Length -gt 0 -and $raw[$raw.Length-1] -eq 10) -eq ($normalized.bytes.Length -gt 0 -and $normalized.bytes[$normalized.bytes.Length-1] -eq 10))
    $eolOnly=(-not $rawFilteredEqual) -and $normalizedFilteredEqual -and [long]$normalized.lone_cr -eq 0 -and [long]$normalized.removed_crlf_cr -gt 0 -and $finalNewlineMatches
    if(-not $rawFilteredEqual -and -not $eolOnly){throw "IDENTITY_NON_EOL_DIFFERENCE: $relative"}
    if($filteredBlob -cne $treeBlob -and -not $AllowCandidateContent){throw "IDENTITY_UNSTAGED_SEMANTIC_MUTATION: $relative"}
    if(($rawFilteredEqual -and $eolOnly) -or (-not $rawFilteredEqual -and -not $normalizedFilteredEqual)){throw "IDENTITY_CONTRADICTORY_TUPLE: $relative"}
    $canonicalBytes=if($rawFilteredEqual){$raw}else{[byte[]]$normalized.bytes}; $canonicalBlob=Get-GitBlobIdentityBytes $canonicalBytes
    if($canonicalBlob -cne $filteredBlob){throw "IDENTITY_CANONICAL_FILTER_DISAGREEMENT: $relative"}
    return [ordered]@{approved_file_type=$true;canonical_blob=$canonicalBlob;canonical_sha256=(Get-Sha256Bytes $canonicalBytes);canonical_size=[long]$canonicalBytes.Length;clean_filtered_blob=$filteredBlob;clean_filtered_tree_equal=($filteredBlob -ceq $treeBlob);eol_normalized_canonical_equal=$normalizedFilteredEqual;eol_normalized_tree_equal=($normalizedBlob -ceq $treeBlob);eol_only_authority=$eolOnly;filter_attribute=[string]$attributes.filter;final_identity_authority=$true;input_class=$InputClass;non_eol_difference=$false;path=$relative;raw_blob=$rawBlob;raw_canonical_equal=$rawFilteredEqual;raw_sha256=$rawSha256;raw_size=[long]$raw.Length;raw_tree_equal=($rawBlob -ceq $treeBlob);text_attribute=[string]$attributes.text;tracked_path=$true;tree_blob=$treeBlob;tree_mode=$treeMode;working_tree_encoding=[string]$attributes.'working-tree-encoding'}
}
function Assert-CanonicalIdentityTuple([object]$Identity) {
    foreach($field in @('approved_file_type','canonical_blob','canonical_sha256','canonical_size','clean_filtered_blob','eol_normalized_canonical_equal','eol_only_authority','final_identity_authority','non_eol_difference','path','raw_blob','raw_canonical_equal','raw_sha256','raw_size','tracked_path','tree_mode')){if($null -eq $Identity.$field){throw "IDENTITY_TUPLE_FIELD_MISSING_${field}"}}
    $rawExact=([string]$Identity.raw_blob -ceq [string]$Identity.canonical_blob)-and([string]$Identity.raw_sha256 -ceq [string]$Identity.canonical_sha256)-and([long]$Identity.raw_size -eq [long]$Identity.canonical_size)
    if([bool]$Identity.raw_canonical_equal -ne $rawExact -or [string]$Identity.clean_filtered_blob -cne [string]$Identity.canonical_blob){throw "IDENTITY_TUPLE_CANONICAL_CONTRADICTION: $($Identity.path)"}
    if(($rawExact-and[bool]$Identity.eol_only_authority)-or(-not$rawExact-and(-not[bool]$Identity.eol_only_authority-or-not[bool]$Identity.eol_normalized_canonical_equal))){throw "IDENTITY_TUPLE_EOL_CONTRADICTION: $($Identity.path)"}
    if(-not[bool]$Identity.approved_file_type-or-not[bool]$Identity.tracked_path-or[string]$Identity.tree_mode-cne'100644'-or[bool]$Identity.non_eol_difference-or-not[bool]$Identity.final_identity_authority){throw "IDENTITY_TUPLE_AUTHORITY_FAILED: $($Identity.path)"}
}
function Assert-RegistryFieldSemantics([object]$Identity,[object]$Row,[string]$InputClass,[string]$RegistryPath) {
    foreach($field in @('path','mode','git_blob_identity','raw_sha256','size')){if(@($Row.PSObject.Properties.Name) -cnotcontains $field){throw "IDENTITY_REGISTRY_FIELD_MISSING_${field}"}}
    if([string]$Row.mode -cne '100644' -or [string]$Row.git_blob_identity -notmatch '^[0-9a-f]{40}$' -or [string]$Row.raw_sha256 -notmatch '^[0-9a-f]{64}$' -or [long]$Row.size -lt 0){throw 'IDENTITY_REGISTRY_TUPLE_INVALID'}
    if($InputClass -ceq 'GOVERNED_SCRIPT'){$expected=@('allowed_invocation_stages','authority_classification','dependencies','execution_class','git_blob_identity','mode','path','raw_sha256','role','size')|Sort-Object;$actual=@($Row.PSObject.Properties.Name)|Sort-Object;if(($actual-join"`n")-cne($expected-join"`n")){throw 'IDENTITY_REGISTRY_PROPERTY_SET_INVALID'}}
    Assert-CanonicalIdentityTuple $identity
    if([string]$Row.path -cne $registryPath){throw "IDENTITY_REGISTRY_PATH_MISMATCH: $($identity.path)"}
    $expectedSha=if($InputClass -ceq 'GOVERNED_SCRIPT'){[string]$identity.raw_sha256}else{[string]$identity.canonical_sha256};$expectedSize=if($InputClass -ceq 'GOVERNED_SCRIPT'){[long]$identity.raw_size}else{[long]$identity.canonical_size}
    if([string]$Row.git_blob_identity -cne [string]$identity.canonical_blob -or [string]$Row.raw_sha256 -cne $expectedSha -or [long]$Row.size -ne $expectedSize){throw "IDENTITY_REGISTRY_FIELD_SEMANTICS_MISMATCH: $($identity.path)"}
}
function Get-RegistryBoundIdentity([string]$Path,[object]$Row,[string]$InputClass,[bool]$AllowCandidateContent) {
    $identity=Get-CanonicalRepositoryIdentity $Path $InputClass $AllowCandidateContent
    $registryPath=if($InputClass -ceq 'SOURCE_ROLE'){Get-RelativePath $packageRoot $Path}else{[string]$identity.path}
    Assert-RegistryFieldSemantics $identity $Row $InputClass $registryPath
    return $identity
}
function Get-RegistryContainerRecord([string]$Path,[object]$Artifact,[string]$ChildClass,[string[]]$ChildIdentities,[bool]$AllowCandidateContent) {
    if([string]::IsNullOrWhiteSpace([string]$Artifact.artifact_type)-or[string]::IsNullOrWhiteSpace([string]$Artifact.schema_version)){throw "TRACE_CONTAINER_SCHEMA_MISSING: $Path"}
    $identity=Get-CanonicalRepositoryIdentity $Path 'REGISTRY_CONTAINER' $AllowCandidateContent;Assert-CanonicalIdentityTuple $identity
    $children=@($ChildIdentities|Sort-Object);if($children.Count-ne@($children|Sort-Object -Unique).Count){throw "TRACE_CONTAINER_CHILD_DUPLICATE: $Path"}
    return [ordered]@{artifact_class='REGISTRY_CONTAINER';artifact_type=[string]$Artifact.artifact_type;child_artifact_class=$ChildClass;child_identities=$children;entry_count=$children.Count;git_blob_identity=[string]$identity.canonical_blob;path=[string]$identity.path;raw_sha256=[string]$identity.raw_sha256;schema_version=[string]$Artifact.schema_version;size=[long]$identity.raw_size;unique_entry_count=@($children|Sort-Object -Unique).Count}
}
function Assert-StaticTraceabilityContract([object]$Trace,[string[]]$R7CaseIds,[object[]]$Unit2Cases,[object[]]$ExpectedContainers,[string[]]$SourceIds,[string[]]$ScriptIds,[string[]]$UtilityIds,[object[]]$ExpectedCandidates) {
    foreach($field in @('artifact_type','case_count','combined_case_count','forward_trace','forward_trace_row_count','reverse_trace','reverse_trace_row_count','registry_containers','registry_container_count','container_forward_trace','container_reverse_trace','unit2_case_count','unit2_forward_trace','unit2_reverse_trace','unit2_unique_case_count','unit2_unique_mutation_count','candidate_identities','schema_version','status')){if(@($Trace.PSObject.Properties.Name)-cnotcontains$field){throw "TRACE_CONTRACT_FIELD_MISSING_${field}"}}
    if([string]$Trace.artifact_type-cne'R7_BIDIRECTIONAL_EXACT_AUTHORITY_TRACEABILITY'-or[string]$Trace.schema_version-cne'1.0.0'-or[string]$Trace.status-cne'PASS'){throw 'TRACE_CONTRACT_HEADER_INVALID'}
    $r7Expected=@($R7CaseIds|Sort-Object);$r7ForwardIds=@($Trace.forward_trace|ForEach-Object{[string]$_.case_id}|Sort-Object -Unique);$r7ReverseIds=@($Trace.reverse_trace|Where-Object{[string]$_.artifact_class-ceq'CASE'}|ForEach-Object{[string]$_.artifact_identity}|Sort-Object)
    if([int]$Trace.case_count-ne$r7Expected.Count-or[int]$Trace.combined_case_count-ne($r7Expected.Count+$Unit2Cases.Count)-or($r7ForwardIds-join"`n")-cne($r7Expected-join"`n")-or($r7ReverseIds-join"`n")-cne($r7Expected-join"`n")-or[int]$Trace.forward_trace_row_count-ne@($Trace.forward_trace).Count-or[int]$Trace.reverse_trace_row_count-ne@($Trace.reverse_trace).Count-or[int]$Trace.unmapped_case_count-ne0-or[int]$Trace.unmapped_requirement_count-ne0){throw 'TRACE_EXISTING_R7_AUTHORITY_INVALID'}
    $expectedUnitIds=@(1..237|ForEach-Object{'U2BC-N'+$_.ToString('D3')});$actualUnitIds=@($Unit2Cases|ForEach-Object{[string]$_.case_id});$mutations=@($Unit2Cases|ForEach-Object{[string]$_.mutation})
    if($Unit2Cases.Count-ne237-or($actualUnitIds-join"`n")-cne($expectedUnitIds-join"`n")-or@($mutations|Sort-Object -Unique).Count-ne237-or[int]$Trace.unit2_case_count-ne237-or[int]$Trace.unit2_unique_case_count-ne237-or[int]$Trace.unit2_unique_mutation_count-ne237-or@($Trace.unit2_forward_trace).Count-ne237-or@($Trace.unit2_reverse_trace).Count-ne237){throw 'TRACE_UNIT2_COUNT_AUTHORITY_INVALID'}
    $unit2RegistryPath='Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/unit2_build_closure_negative_cases.json';$unit2Consumer='Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/verify_unit2_build_closure.ps1'
    for($index=0;$index-lt237;$index++){$case=$Unit2Cases[$index];$forward=$Trace.unit2_forward_trace[$index];$reverse=$Trace.unit2_reverse_trace[$index];$pattern=if(@($case.PSObject.Properties.Name)-ccontains'expected_detail_pattern'){[string]$case.expected_detail_pattern}else{$null};$patternRequired=-not[string]::IsNullOrWhiteSpace($pattern);if([string]$forward.artifact_class-cne'UNIT2_NEGATIVE_CASE_FORWARD'-or[string]$reverse.artifact_class-cne'UNIT2_NEGATIVE_CASE_REVERSE'-or[string]$forward.case_id-cne[string]$case.case_id-or[string]$reverse.case_id-cne[string]$case.case_id-or[string]$forward.mutation_id-cne[string]$case.mutation-or[string]$reverse.mutation_id-cne[string]$case.mutation-or[string]$forward.required_rejection_reason-cne[string]$case.expected_error-or[string]$reverse.required_rejection_reason-cne[string]$case.expected_error-or[long]$forward.ordinal-ne($index+1)-or[long]$reverse.ordinal-ne($index+1)-or[string]$forward.source_selector-cne('cases['+$index+']')-or[string]$reverse.source_selector-cne('cases['+$index+']')-or[string]$forward.success_failure_contract-cne'MUST_REJECT'-or[string]$forward.forward_target-cne$unit2Consumer-or[string]$reverse.governing_consumer-cne$unit2Consumer-or[string]$reverse.forward_artifact_identity-cne[string]$case.case_id-or[string]$forward.registry_container_path-cne$unit2RegistryPath-or[string]$reverse.registry_container_path-cne$unit2RegistryPath-or[string]$forward.source_registry-cne$unit2RegistryPath-or[string]$forward.schema_version-cne'1.0.0'-or[string]$forward.mutation_class-cne'UNIT2_BUILD_CLOSURE_NEGATIVE_MUTATION'-or[string]$forward.required_diagnostic.expected_detail_pattern-cne[string]$pattern-or[string]$reverse.required_diagnostic.expected_detail_pattern-cne[string]$pattern-or[bool]$forward.required_diagnostic.pattern_required-ne$patternRequired-or[bool]$reverse.required_diagnostic.pattern_required-ne$patternRequired){throw "TRACE_UNIT2_ROW_INVALID: $($case.case_id)"}}
    if(@($Trace.unit2_forward_trace|ForEach-Object{[string]$_.case_id}|Sort-Object -Unique).Count-ne237-or@($Trace.unit2_reverse_trace|ForEach-Object{[string]$_.case_id}|Sort-Object -Unique).Count-ne237-or@($Trace.unit2_forward_trace|Where-Object{[string]$_.case_id-cmatch'^U2BC-N2(?:0[4-9]|[12][0-9]|3[0-7])$'}).Count-ne34){throw 'TRACE_UNIT2_RANGE_OR_DUPLICATE_INVALID'}
    $actualContainers=@($Trace.registry_containers);if($actualContainers.Count-ne4-or[int]$Trace.registry_container_count-ne4){throw 'TRACE_CONTAINER_COUNT_INVALID'}
    $expectedForward=[Collections.Generic.List[string]]::new();foreach($expected in @($ExpectedContainers|Sort-Object { [string]$_.path })){$actual=@($actualContainers|Where-Object{[string]$_.path-ceq[string]$expected.path});if($actual.Count-ne1){throw "TRACE_CONTAINER_MISSING_OR_DUPLICATE: $($expected.path)"};$actual=$actual[0];foreach($field in @('artifact_type','child_artifact_class','entry_count','git_blob_identity','path','raw_sha256','schema_version','size','unique_entry_count')){if([string]$actual.$field-cne[string]$expected.$field){throw "TRACE_CONTAINER_IDENTITY_INVALID_${field}: $($expected.path)"}};if((@($actual.child_identities)-join"`n")-cne(@($expected.child_identities)-join"`n")){throw "TRACE_CONTAINER_CHILDREN_INVALID: $($expected.path)"};$ordinal=0;foreach($child in @($expected.child_identities)){$ordinal++;$expectedForward.Add(([string]$expected.path+'|'+[string]$expected.child_artifact_class+'|'+[string]$child+'|'+$ordinal))}}
    $forwardEdges=@($Trace.container_forward_trace|ForEach-Object{[string]$_.container_path+'|'+[string]$_.child_artifact_class+'|'+[string]$_.child_identity+'|'+[string]$_.ordinal});$reverseEdges=@($Trace.container_reverse_trace|ForEach-Object{[string]$_.container_path+'|'+[string]$_.child_artifact_class+'|'+[string]$_.child_identity+'|'+[string]$_.ordinal});if(($forwardEdges-join"`n")-cne($expectedForward.ToArray()-join"`n")-or($reverseEdges-join"`n")-cne($expectedForward.ToArray()-join"`n")-or@($forwardEdges|Sort-Object -Unique).Count-ne$forwardEdges.Count-or@($reverseEdges|Sort-Object -Unique).Count-ne$reverseEdges.Count){throw 'TRACE_CONTAINER_EDGE_INVALID'}
    $sourceActual=@($Trace.reverse_trace|Where-Object{[string]$_.artifact_class-ceq'SOURCE_FILE'}|ForEach-Object{[string]$_.artifact_identity}|Sort-Object);$scriptActual=@($Trace.reverse_trace|Where-Object{[string]$_.artifact_class-ceq'GOVERNANCE_ORCHESTRATOR'}|ForEach-Object{[string]$_.artifact_identity}|Sort-Object);$utilityActual=@($Trace.reverse_trace|Where-Object{[string]$_.artifact_class-ceq'EXTERNAL_UTILITY_INPUT'}|ForEach-Object{[string]$_.artifact_identity}|Sort-Object)
    if(($sourceActual-join"`n")-cne(@($SourceIds|Sort-Object)-join"`n")-or($scriptActual-join"`n")-cne(@($ScriptIds|Sort-Object)-join"`n")-or($utilityActual-join"`n")-cne(@($UtilityIds|Sort-Object)-join"`n")){throw 'TRACE_CHILD_ROW_SET_INVALID'}
    $candidateActual=@($Trace.candidate_identities|Sort-Object { [string]$_.path });$candidateExpected=@($ExpectedCandidates|Sort-Object { [string]$_.path });if($candidateActual.Count-ne$candidateExpected.Count){throw 'TRACE_CANDIDATE_IDENTITY_COUNT_INVALID'};for($index=0;$index-lt$candidateExpected.Count;$index++){foreach($field in @('git_blob_identity','path','raw_sha256','size')){if([string]$candidateActual[$index].$field-cne[string]$candidateExpected[$index].$field){throw "TRACE_CANDIDATE_IDENTITY_INVALID_${field}"}}}
    $serialized=$Trace|ConvertTo-Json -Depth 100 -Compress;$unescapedPaths=$serialized.Replace('\\','\');if($serialized.Contains('086316a3134fd46b6062cbd0445bd802ca343bde')-or$unescapedPaths.IndexOf($repositoryRoot,[StringComparison]::OrdinalIgnoreCase)-ge0-or$unescapedPaths.IndexOf($env:TEMP,[StringComparison]::OrdinalIgnoreCase)-ge0-or$serialized-match'U2BC_2B4DR(?:2|3)[A-Z0-9_\\/.-]*EVIDENCE'){throw 'TRACE_PATH_OR_ERRONEOUS_OID_LEAKAGE'}
    return [ordered]@{combined_case_count=388;container_edge_count=$expectedForward.Count;registry_container_count=4;r7_case_count=$r7Expected.Count;unit2_case_count=237;unit2_n204_n237_count=34}
}
function Require-GitObject([string]$Identity, [string]$Type) {
    $actual = ([string](Git-Lines @('cat-file','-t',$Identity))).Trim()
    Add-Check ("git-object-" + $Identity) ($actual -eq $Type) ([ordered]@{ actual_type = $actual; expected_type = $Type; identity = $Identity })
}
function Parse-PowerShell([string]$Path) {
    $tokens = $null; $errors = $null
    [Management.Automation.Language.Parser]::ParseFile($Path,[ref]$tokens,[ref]$errors) | Out-Null
    return @($errors)
}
function Write-JsonNew([object]$Value, [string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if (Test-Path -LiteralPath $full) { throw "Refusing verification overwrite: $full" }
    $parent = Split-Path -Parent $full
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
    [IO.File]::WriteAllText($full, ($Value | ConvertTo-Json -Depth 100), [Text.UTF8Encoding]::new($false))
}

$immutableObjects = [ordered]@{
    '87d066eb16d7fe0b6a1677ea7739c5c2ead4ad94' = 'commit'
    '343622743668d7ddc524513307e726f20d1db9fc' = 'blob'
    '06c6805ed52a0d539a73088c097c60dec335462a' = 'commit'
    '1be3b0b5f15ac8e68b88202e0e9d3787b69d1856' = 'blob'
    '8ec5697b3c6fd9d93b972113b7e79d033b4cb1f6' = 'commit'
    'dfa98a89049b9596387143c002252d91d608fbfc' = 'blob'
    'bb04ac54fb328516d0c785f4e6551e6a20d73759' = 'commit'
    '9d813a4bad29ec04f022f54ffcae73a5d542eb44' = 'commit'
    'f0cfbce97e913a133530dd66a70326b1e03a0fb6' = 'commit'
}
foreach ($entry in $immutableObjects.GetEnumerator()) { Require-GitObject $entry.Key $entry.Value }
$head = ([string](Git-Lines @('rev-parse','HEAD'))).Trim()
& $gitExecutable -c "safe.directory=$safeRepository" -C $repositoryRoot merge-base --is-ancestor '9d813a4bad29ec04f022f54ffcae73a5d542eb44' $head
Add-Check 'independent-rejection-preserved-in-ancestry' ($LASTEXITCODE -eq 0) ([ordered]@{ head = $head; required_ancestor = '9d813a4bad29ec04f022f54ffcae73a5d542eb44' })
foreach ($forbidden in @('06c6805ed52a0d539a73088c097c60dec335462a','8ec5697b3c6fd9d93b972113b7e79d033b4cb1f6','f0cfbce97e913a133530dd66a70326b1e03a0fb6')) {
    & $gitExecutable -c "safe.directory=$safeRepository" -C $repositoryRoot merge-base --is-ancestor $forbidden $head
    Add-Check ("forbidden-ancestry-absent-" + $forbidden) ($LASTEXITCODE -ne 0) ([ordered]@{ forbidden = $forbidden; head = $head })
}
$reviewFiles = @(Git-Lines @('ls-tree','-r','--name-only','9d813a4bad29ec04f022f54ffcae73a5d542eb44','--','Architecture/Audits/2026-07-23_R7_Independent_Terminal_Authority_Acceptance_Review/'))
Add-Check 'independent-review-package-count' ($reviewFiles.Count -eq 30) ([ordered]@{ count = $reviewFiles.Count; paths = $reviewFiles })

$requirementPath = Join-Path $packageRoot 'governed_requirement_registry.json'
$casePath = Join-Path $packageRoot 'immutable_case_definitions.json'
$expectationPath = Join-Path $packageRoot 'immutable_expectations.json'
$coveragePath = Join-Path $packageRoot 'exact_byte_coverage_proof.json'
$historyPath = Join-Path $packageRoot 'historical_classification_registry.json'
$manifestPath = Join-Path $packageRoot 'AuthoritySources\authority_source_manifest.json'
$scriptRegistryPath = Join-Path $packageRoot 'governed_script_registry.json'
$utilityRegistryPath = Join-Path $packageRoot 'external_utility_registry.json'
$sourceRolePath = Join-Path $packageRoot 'source_role_registry.json'
$traceabilityPath = Join-Path $packageRoot 'static_traceability.json'
$unit2NegativePath = Join-Path $packageRoot 'unit2_build_closure_negative_cases.json'
$requirements = Read-Json $requirementPath
$cases = Read-Json $casePath
$expectations = Read-Json $expectationPath
$coverage = Read-Json $coveragePath
$history = Read-Json $historyPath
$scriptRegistry = Read-Json $scriptRegistryPath
$utilityRegistry = Read-Json $utilityRegistryPath
$sourceRoleRegistry = Read-Json $sourceRolePath
$traceability = Read-Json $traceabilityPath
$unit2Negative = Read-Json $unit2NegativePath
$declaredRequirementCount = [int]$requirements.governing_requirement_count
$declaredCaseCount = [int]$cases.independently_determined_case_count
$declaredExpectationCount = [int]$expectations.expectation_count
Add-Check 'governed-requirement-count' ($declaredRequirementCount -gt 0 -and @($requirements.requirements).Count -eq $declaredRequirementCount -and [int]$coverage.governing_requirement_count -eq $declaredRequirementCount) ([ordered]@{ count = @($requirements.requirements).Count; declared = $declaredRequirementCount; sha256 = (Get-LowerHash $requirementPath) })
Add-Check 'independently-authored-case-count' ($declaredCaseCount -gt 0 -and @($cases.cases).Count -eq $declaredCaseCount -and [int]$coverage.case_count -eq $declaredCaseCount -and $cases.expectation_artifact_read -eq $false) ([ordered]@{ count = @($cases.cases).Count; declared = $declaredCaseCount; sha256 = (Get-LowerHash $casePath) })
Add-Check 'independently-authored-expectation-count' ($declaredExpectationCount -eq $declaredCaseCount -and @($expectations.expectations).Count -eq $declaredExpectationCount -and [int]$coverage.expectation_count -eq $declaredExpectationCount -and $expectations.case_artifact_read -eq $false -and $expectations.runtime_evidence_read -eq $false) ([ordered]@{ count = @($expectations.expectations).Count; declared = $declaredExpectationCount; sha256 = (Get-LowerHash $expectationPath) })
Add-Check 'coverage-zero-gaps' ([int]$coverage.unmapped_governing_requirement_count -eq 0 -and [int]$coverage.unauthorized_normative_case_count -eq 0 -and [int]$coverage.prohibited_source_reference_count -eq 0) ([ordered]@{ sha256 = (Get-LowerHash $coveragePath); unauthorized = $coverage.unauthorized_normative_case_count; unmapped = $coverage.unmapped_governing_requirement_count })
$sequence332 = @($history.rules | Where-Object { $_.PSObject.Properties.Name -contains 'original_sequence' -and $_.original_sequence -eq 332 })[0]
$sequence678 = @($history.rules | Where-Object { $_.PSObject.Properties.Name -contains 'original_sequence' -and $_.original_sequence -eq 678 })[0]
Add-Check 'historical-classification-registry-bound' ($sequence332.classification -eq 'INCOMPLETE_ISSUANCE_SUPERSEDED_NONAUTHORITY' -and $sequence678.classification -eq 'ABORTED_CLIENT_REJECTED_ISSUANCE_NONAUTHORITY') ([ordered]@{ sha256 = (Get-LowerHash $historyPath); sequence_332 = $sequence332; sequence_678 = $sequence678 })
$ambiguityRule = @($history.rules | Where-Object { $_.PSObject.Properties.Name -contains 'records' })[0]
$boundSequences = @($ambiguityRule.records | ForEach-Object { [long]$_.original_sequence })
$expectedAmbiguousSequences = @(326L,329L,332L,335L,375L,378L,381L,544L,547L,678L)
$exactSequenceOrder = ($boundSequences.Count -eq $expectedAmbiguousSequences.Count)
for ($index = 0; $exactSequenceOrder -and $index -lt $expectedAmbiguousSequences.Count; $index++) { if ($boundSequences[$index] -ne $expectedAmbiguousSequences[$index]) { $exactSequenceOrder = $false } }
$completeHistoricalBindings = @($ambiguityRule.records | Where-Object { $_.original_entry_identity -notmatch '^[0-9a-f]{64}$' -or $_.original_entry_hash -notmatch '^[0-9a-f]{64}$' -or $_.original_signed_issuance_receipt_identity -notmatch '^[0-9a-f]{64}$' -or $_.original_terminal_receipt_identity -ne 'ABSENT' -or $_.original_client_response_identity -ne 'ABSENT' -or $_.reuse -ne 'PERMANENTLY_FORBIDDEN' }).Count -eq 0
Add-Check 'ten-ambiguous-historical-issuances-exactly-bound' ($exactSequenceOrder -and $completeHistoricalBindings) ([ordered]@{ bound_sequences = $boundSequences; classification = $ambiguityRule.classification; record_count = @($ambiguityRule.records).Count })

$badCaseAuthority = [Collections.Generic.List[object]]::new()
foreach ($case in @($cases.cases)) {
    if ($case.request_recipe.include_expectation_fields -ne $false -or $case.request_recipe.include_desired_result -ne $false) { $badCaseAuthority.Add([ordered]@{ case_id = $case.case_id; reason = 'EXPECTATION_COUPLED_RECIPE' }) }
    foreach ($authority in @($case.authority_refs)) {
        if ($authority.governing_commit -eq 'f0cfbce97e913a133530dd66a70326b1e03a0fb6' -or [string]::IsNullOrWhiteSpace([string]$authority.clause_raw_sha256) -or [string]::IsNullOrWhiteSpace([string]$authority.line_range)) { $badCaseAuthority.Add([ordered]@{ case_id = $case.case_id; reason = 'UNRESOLVED_OR_PROHIBITED_AUTHORITY' }) }
    }
}
Add-Check 'case-authority-and-request-separation' ($badCaseAuthority.Count -eq 0) $badCaseAuthority.ToArray()
$actualRunIdentityLeak = @($expectations.expectations | Where-Object { $_.PSObject.Properties.Name -contains 'actual_run_identity' -or $_.PSObject.Properties.Name -contains 'observed_value' })
Add-Check 'expectations-free-of-current-run-identities' ($actualRunIdentityLeak.Count -eq 0) ([ordered]@{ leak_count = $actualRunIdentityLeak.Count })

$sourceRoot = Join-Path $packageRoot 'Source'
$sourceFiles = @(Get-ChildItem -LiteralPath $sourceRoot -File | Sort-Object Name)
Add-Check 'authority-runtime-source-language-closure' (@($sourceFiles | Where-Object Extension -ne '.cs').Count -eq 0) ([ordered]@{ source_count = $sourceFiles.Count; extensions = @($sourceFiles.Extension | Sort-Object -Unique) })
$sourceRoutes = @($sourceRoleRegistry.sources)
$actualSourceNames = @($sourceFiles | ForEach-Object Name | Sort-Object)
$routeSourceNames = @($sourceRoutes | ForEach-Object { Split-Path -Leaf ([string]$_.path) } | Sort-Object)
$badSourceRoutes = [Collections.Generic.List[object]]::new()
Assert-CanonicalRepositoryAuthority
foreach($route in $sourceRoutes){
    $path=Join-Path $packageRoot ([string]$route.path).Replace('/','\')
    try {
        [void](Get-RegistryBoundIdentity $path $route 'SOURCE_ROLE' $false)
        if(@($route.requirement_ids).Count -eq 0 -or @($route.blocker_ids).Count -eq 0 -or @($route.architecture_roles).Count -eq 0 -or @($route.expected_verification).Count -eq 0 -or @($route.compiled_into_roles).Count -eq 0){throw 'IDENTITY_REVERSE_TRACE_ROUTING_INCOMPLETE'}
    } catch { $badSourceRoutes.Add([ordered]@{path=[string]$route.path;reason=$_.Exception.Message}) }
}
Add-Check 'all-source-files-have-complete-reverse-trace-routing' ([int]$sourceRoleRegistry.source_count -eq $sourceFiles.Count -and ($actualSourceNames -join "`n") -ceq ($routeSourceNames -join "`n") -and $badSourceRoutes.Count -eq 0 -and $routeSourceNames -contains 'R7MeasuredUtility.cs' -and $routeSourceNames -contains 'R7ServiceBoundary.cs' -and $routeSourceNames -contains 'R7RecoveryProbeAuditor.cs') ([ordered]@{bad_routes=$badSourceRoutes.ToArray();source_count=$sourceFiles.Count;source_role_registry_sha256=(Get-LowerHash $sourceRolePath)})
$signerSource = Get-Content -Raw -LiteralPath (Join-Path $sourceRoot 'R7TerminalSignerService.cs')
$signerLaunchTokens = @(@('CreateProcess(?:W)?\s*\(','Process\.Start\s*\(','CREATEPROCESS_DEFAULT_CALLER_TOKEN') | Where-Object { $signerSource -match $_ })
Add-Check 'signer-does-not-launch-semantic-children' ($signerLaunchTokens.Count -eq 0) ([ordered]@{ detected_tokens = $signerLaunchTokens })
$infrastructureSource = Get-Content -Raw -LiteralPath (Join-Path $sourceRoot 'R7ServiceInfrastructure.cs')
Add-Check 'signer-derives-principal-and-concurrency-facts-from-os' ($signerSource.Contains('SERVER_OS_PROBE_UNDER_PIPE_CLIENT_IMPERSONATION') -and $signerSource.Contains('CHILD_PROBE_REPORT_CONFLICT') -and $signerSource.Contains('DuplicateTokenExForProbe') -and $signerSource.Contains('OPEN_CNG_KEY_AND_SIGN_ARBITRARY_BYTES') -and $signerSource.Contains('OS_CONCURRENT_CONNECTION_NOT_OBSERVED') -and $infrastructureSource.Contains('RunAsCaller') -and $infrastructureSource.Contains('ConcurrentConnectionCountAtReceive')) ([ordered]@{ infrastructure_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7ServiceInfrastructure.cs'));signer_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7TerminalSignerService.cs')) })
$mandatoryExpandedCases = @('PRI-010','PRI-011','PRI-012','PRI-013','PRI-014','PRI-015','PAR-014','PAR-015','PAR-016','PAR-017','PAR-018','PAR-019','PAR-020','OUT-001','OUT-002','OUT-003','OUT-004','CON-001','CON-002')
$expandedCaseIds = @($cases.cases | ForEach-Object case_id)
Add-Check 'expanded-explicit-boundary-attacks-authored' (@($mandatoryExpandedCases | Where-Object { $_ -notin $expandedCaseIds }).Count -eq 0) ([ordered]@{ case_ids=$mandatoryExpandedCases;case_registry_sha256=(Get-LowerHash $casePath) })
$protocolSource = Get-Content -Raw -LiteralPath (Join-Path $sourceRoot 'R7CoreJsonProtocol.cs')
Add-Check 'strict-framed-protocol-source-present' ($protocolSource.Contains('MaximumFrameBytes = 65536') -and $protocolSource.Contains('MaximumPayloadBytes = MaximumFrameBytes - FrameHeaderBytes') -and $protocolSource.Contains('ProtocolVersion = "4.0"') -and $protocolSource.Contains('FrameHeaderBytes = 12')) ([ordered]@{ protocol_source_sha256 = Get-LowerHash (Join-Path $sourceRoot 'R7CoreJsonProtocol.cs') })
$roleSource = Get-Content -Raw -LiteralPath (Join-Path $sourceRoot 'R7RoleServices.cs')
Add-Check 'producer-expectation-artifact-not-loaded' (-not $roleSource.Contains('new R7AuthoritySet') -and $roleSource.Contains('expectation_artifact_read", false')) ([ordered]@{ role_source_sha256 = Get-LowerHash (Join-Path $sourceRoot 'R7RoleServices.cs') })
$matrixSource = Get-Content -Raw -LiteralPath (Join-Path $packageRoot 'run_fresh_matrix.ps1')
$expectationRequestTokens = @(@('expected_path','expected_sha256','$expectedSha','$expected =') | Where-Object { $matrixSource.Contains($_) -or $roleSource.Contains($_) -or $signerSource.Contains($_) })
Add-Check 'outer-requests-contain-no-expected-evidence' ($expectationRequestTokens.Count -eq 0) ([ordered]@{detected_tokens=$expectationRequestTokens})
$runtimeForbiddenInvocation = [Collections.Generic.List[string]]::new()
foreach ($sourceFile in $sourceFiles) {
    $text = Get-Content -Raw -LiteralPath $sourceFile.FullName
    if ($text -match '(?is)(?:FileName\s*=|Process\.Start\s*\()[^;\r\n]*(?:python(?:\.exe)?|git\.exe|libgit)') { $runtimeForbiddenInvocation.Add($sourceFile.Name) }
}
$controlledProcessLaunches = $roleSource.Contains('start.FileName = R7BuildIdentity.ExecutionBinaryPath') -and $roleSource.Contains('--r7-restricted-descendant-probe') -and $matrixSource.Contains('RandleTerminalPublicVerifier.exe')
Add-Check 'python-and-git-removed-from-runtime-authority' ($runtimeForbiddenInvocation.Count -eq 0 -and $controlledProcessLaunches) ([ordered]@{ controlled_fixed_process_launches = $controlledProcessLaunches; forbidden_files = $runtimeForbiddenInvocation.ToArray() })
$safeFileSource = Get-Content -Raw -LiteralPath (Join-Path $sourceRoot 'R7SafeFile.cs')
$upgradeSource = Get-Content -Raw -LiteralPath (Join-Path $sourceRoot 'R7UpgradeAuthorityService.cs')
$publicVerifierSource = Get-Content -Raw -LiteralPath (Join-Path $sourceRoot 'R7PublicVerifier.cs')
Add-Check 'signing-key-file-metadata-held-through-service-life' ($safeFileSource.Contains('HoldMetadataFile') -and $signerSource.Contains('TerminalKeyFileSecurityDescriptorSha256') -and $upgradeSource.Contains('UpgradeKeyFileSecurityDescriptorSha256') -and $signerSource.Contains('signingKeyFile.Dispose()') -and $upgradeSource.Contains('signingKeyFile.Dispose()')) ([ordered]@{safe_file_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7SafeFile.cs'));terminal_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7TerminalSignerService.cs'));upgrade_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7UpgradeAuthorityService.cs'))})
Add-Check 'upgrade-prepared-record-recovery-is-ledger-bound' ($upgradeSource.Contains('RecoverPreparedRecord') -and $upgradeSource.Contains('CONFLICTING_UPGRADE_AUTHORIZATION_RETRY') -and $upgradeSource.Contains('UPGRADE_RECORD_NOT_COMMITTED') -and $publicVerifierSource.Contains('UPGRADE_AUTHORIZATION_RAW_EVIDENCE_INVALID')) ([ordered]@{public_verifier_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7PublicVerifier.cs'));upgrade_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7UpgradeAuthorityService.cs'))})
$buildSource = Get-Content -Raw -LiteralPath (Join-Path $packageRoot 'build_remediation_package.ps1')
$syntheticUpgradeTokens = @(@('PROBE_UPGRADE_POLICY','ProbeUpgradePolicy','claimed_new_interface','worker_identity_matches') | Where-Object { $upgradeSource.Contains($_) -or $roleSource.Contains($_) })
Add-Check 'upgrade-attacks-use-real-authorization-interface' ($syntheticUpgradeTokens.Count -eq 0 -and $matrixSource.Contains("Invoke-ActualUpgradeAttack") -and $matrixSource.Contains("'AUTHORIZE_TERMINAL_UPGRADE'") -and $upgradeSource.Contains('R7_UPGRADE_AUTHORITY_SERVER_CAPTURED_INTERACTION') -and $signerSource.Contains('UPGRADE_SERVER_CAPTURE_MISMATCH')) ([ordered]@{synthetic_tokens=$syntheticUpgradeTokens;matrix_sha256=(Get-LowerHash (Join-Path $packageRoot 'run_fresh_matrix.ps1'));upgrade_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7UpgradeAuthorityService.cs'))})
Add-Check 'upgrade-component-identities-embedded-before-final-authority-build' ($upgradeSource.Contains('ExpectedSha256') -and $upgradeSource.Contains('COMPONENT_SET_MISMATCH') -and $buildSource.Contains('Finalize the non-circular upgrade policy') -and $buildSource.Contains('FinalPassA') -and $buildSource.Contains('upgrade_authority_build_receipt')) ([ordered]@{build_script_sha256=(Get-LowerHash (Join-Path $packageRoot 'build_remediation_package.ps1'));upgrade_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7UpgradeAuthorityService.cs'))})
Add-Check 'service-binaries-held-and-policy-bound-through-life' ($signerSource.Contains('signingBinaryFile') -and $signerSource.Contains('signingBinaryFile.Dispose()') -and $roleSource.Contains('R7ActiveUpgrade.ResolveAuthorization("EXECUTION")') -and $roleSource.Contains('R7ActiveUpgrade.ResolveAuthorization("OBSERVATION")') -and $roleSource.Contains('R7ActiveUpgrade.ResolveAuthorization("COMPARATOR")') -and $roleSource.Contains('binaryFile.Dispose()') -and $upgradeSource.Contains('serviceBinaryFile.Dispose()')) ([ordered]@{roles_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7RoleServices.cs'));signer_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7TerminalSignerService.cs'));upgrade_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7UpgradeAuthorityService.cs'))})
$installSource = Get-Content -Raw -LiteralPath (Join-Path $packageRoot 'install_authorized_transition.ps1')
$provisionSource = Get-Content -Raw -LiteralPath (Join-Path $packageRoot 'provision_upgrade_authority.ps1')
Add-Check 'build-time-toolchain-recursively-content-bound' ($buildSource.Contains('directory-manifest') -and $buildSource.Contains('Git installation changed while resolving immutable source objects') -and $buildSource.Contains('BOOTSTRAP_ARTIFACT_TOOL') -and $buildSource.Contains('normalized_il_equal=$true')) ([ordered]@{build_script_sha256=(Get-LowerHash (Join-Path $packageRoot 'build_remediation_package.ps1'))})
$installLines = @($installSource -split '\r?\n')
$terminalRootAclLine = @($installLines | Where-Object { $_.Contains('@($remediationRoot') })[0]
$upgradeStateAclLine = @($installLines | Where-Object { $_.Contains('@($upgradeStateRoot') -and $_.Contains('/inheritance:r') })[0]
$provisionRootAclPass = $provisionSource.Contains('Assert-DedicatedDirectoryAcl') -and $provisionSource.Contains('Assert-PublicCertificateAcl') -and $provisionSource.Contains('$immutableDirectories') -and $provisionSource.Contains('$mutableDirectories') -and $provisionSource.Contains('Dedicated authority directory principal set differs') -and $provisionSource.Contains("`$takeownExecutable = 'C:\Windows\System32\takeown.exe'") -and $provisionSource.Contains('$ExpectedFourthFailedAttemptSha256') -and $provisionSource.Contains('recovered_acl_mutation_in_current_attempt = $false') -and $provisionSource.Contains('$allowedAdminRights') -and -not $provisionSource.Contains('Invoke-Checked $takeownExecutable')
$immutableRootAclPass = $terminalRootAclLine.Contains('$terminalAccount`:(OI)(CI)(RX)') -and $upgradeStateAclLine.Contains('$upgradeAccount`:(OI)(CI)(RX)') -and $provisionRootAclPass
Add-Check 'immutable-authority-and-policy-roots-are-read-only-to-signers' $immutableRootAclPass ([ordered]@{install_sha256=(Get-LowerHash (Join-Path $packageRoot 'install_authorized_transition.ps1'));provision_sha256=(Get-LowerHash (Join-Path $packageRoot 'provision_upgrade_authority.ps1'));terminal_root_acl=$terminalRootAclLine;upgrade_state_acl=$upgradeStateAclLine})

$scriptErrors = [Collections.Generic.List[object]]::new()
$packageScripts = @(Get-ChildItem -LiteralPath $packageRoot -Filter '*.ps1' -File | Sort-Object Name)
foreach ($script in $packageScripts) {
    foreach ($error in @(Parse-PowerShell $script.FullName)) { $scriptErrors.Add([ordered]@{ message = $error.Message; path = $script.FullName; line = $error.Extent.StartLineNumber }) }
}
Add-Check 'powershell-orchestrators-parse' ($scriptErrors.Count -eq 0) $scriptErrors.ToArray()
$ambiguousTestPath=[Collections.Generic.List[object]]::new()
foreach($script in $packageScripts){$text=Get-Content -LiteralPath $script.FullName -Raw;if($text -match 'Test-Path\s+-LiteralPath[^\r\n]+\s-(?:or|and)\s+Test-Path'){$ambiguousTestPath.Add([ordered]@{path=$script.Name})}}
Add-Check 'powershell-test-path-boolean-expressions-are-unambiguous' ($ambiguousTestPath.Count -eq 0) $ambiguousTestPath.ToArray()
$unit2bInstallerPath=Join-Path $packageRoot 'complete_unit2_upgrade_authority.ps1'
$unit2bInstaller=Get-Content -LiteralPath $unit2bInstallerPath -Raw
$unit2bForbidden=[Collections.Generic.List[string]]::new()
foreach($pattern in @("@\('start'",'Start-Service','Stop-Service','Restart-Service','CngKey','SignData','SignHash','New-SelfSignedCertificate','UPGRADE_LEDGER_GENESIS','AUTHORIZE_TERMINAL_TRANSITION\s*\)')){if($unit2bInstaller -match $pattern){$unit2bForbidden.Add($pattern)}}
$failureActionLegacy=@("RunScMutation @('failure'","RunScMutation @('failureflag'","@('qfailure'","@('qfailureflag'","'actions=',''")
$failureActionLegacyFindings=@($failureActionLegacy|Where-Object{$unit2bInstaller.Contains($_)})
Add-Check 'unit2b-installer-is-stopped-prestart-only-and-rollback-bound' ($unit2bForbidden.Count -eq 0 -and $failureActionLegacyFindings.Count -eq 0 -and $unit2bInstaller.Contains('[Parameter(Mandatory=$true)][switch]$PreStartOnly') -and $unit2bInstaller.Contains('Only the explicit PreStartOnly path is exposed') -and $unit2bInstaller.Contains("RunEvidenceTool @('capture-failure-actions'") -and $unit2bInstaller.Contains("RunEvidenceTool @('configure-failure-actions-none'") -and $unit2bInstaller.Contains("RunEvidenceTool @('verify-failure-actions-none'") -and $unit2bInstaller.Contains("RunEvidenceTool @('restore-failure-actions'") -and $unit2bInstaller.Contains('RunEvidenceTool @(''service-boundary''') -and $unit2bInstaller.Contains('RunEvidenceTool @(''restore-service-boundary''') -and $unit2bInstaller.Contains("`$aclSnapshots.Add") -and $unit2bInstaller.Contains('Set-Acl -LiteralPath') -and $unit2bInstaller.Contains("'ROLLBACK_SCM_CONFIG'") -and $unit2bInstaller.Contains("'ROLLBACK_SCM_SID_TYPE'") -and $unit2bInstaller.Contains("'ROLLBACK_SCM_PRIVILEGES'") -and $unit2bInstaller.Contains('$failureActionsRestoreRequired=$true') -and $unit2bInstaller.Contains('service_started=$false') -and $unit2bInstaller.Contains('terminal_transition_authorized=$false')) ([ordered]@{failure_action_legacy_findings=$failureActionLegacyFindings;forbidden_tokens=$unit2bForbidden.ToArray();installer_sha256=(Get-LowerHash $unit2bInstallerPath)})
$installContractPath=Join-Path $packageRoot 'unit2_stopped_install_contract.json'
$installMapVerifierPath=Join-Path $packageRoot 'verify_unit2_install_map_evidence.ps1'
$installContract=Read-Json $installContractPath
$installMapVerifier=Get-Content -LiteralPath $installMapVerifierPath -Raw
$installIds=@($installContract.install_items|ForEach-Object{[string]$_.id}|Sort-Object)
$requiredInstallIds=@('BUILD_MANIFEST','DEPENDENCY_MANIFEST','DETERMINISM_RECEIPT','PACKAGE_MANIFEST','PACKAGED_ARTIFACT_TOOL','PACKAGED_PROTECTED_METADATA_TOOL','PUBLIC_CERTIFICATE','SOURCE_TO_BINARY_RECEIPT','UPGRADE_AUTHORITY','UPGRADE_CLIENT','UPGRADE_POLICY','UPGRADE_PROTOCOL_PROBE','UPGRADE_PUBLIC_VERIFIER')|Sort-Object
$installMapPass=@($installContract.install_items).Count -eq 13 -and (($installIds-join "`n") -ceq ($requiredInstallIds-join "`n")) -and @($installContract.install_items.source_path|Sort-Object -Unique).Count -eq 13 -and @($installContract.install_items.destination_path|Sort-Object -Unique).Count -eq 13 -and [string]$installContract.evidence_policy.fixed_root -ceq 'C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Evidence' -and [string]$installContract.evidence_policy.unexpected_existing_evidence_policy -ceq 'REJECT' -and @($installContract.evidence_policy.preserved_records).Count -eq 2 -and $unit2bInstaller.Contains('$installContract.install_items') -and $unit2bInstaller.Contains('WriteExclusiveBytes') -and $unit2bInstaller.Contains('AssertEvidenceSnapshot') -and -not $unit2bInstaller.Contains('evidence parent must not exist before installation') -and $installMapVerifier.Contains("test_count=`$results.Count")
Add-Check 'unit2b-install-map-and-append-safe-evidence-are-explicit-and-regressed' $installMapPass ([ordered]@{contract_sha256=(Get-LowerHash $installContractPath);install_ids=$installIds;regression_verifier_sha256=(Get-LowerHash $installMapVerifierPath)})
$failureActionSourcePath=Join-Path $sourceRoot 'R7ServiceFailureActions.cs'
$failureActionVerifierPath=Join-Path $packageRoot 'verify_failure_action_configuration.ps1'
$failureActionSource=Get-Content -LiteralPath $failureActionSourcePath -Raw
$failureActionVerifier=Get-Content -LiteralPath $failureActionVerifierPath -Raw
$failureActionNativeTokens=@('OpenSCManagerW','OpenServiceW','ChangeServiceConfig2W','QueryServiceConfig2W','ServiceConfigFailureActions = 2','ServiceConfigFailureActionsFlag = 4','NON_NULL_SENTINEL_WITH_ZERO_COUNT','FAILURE_ACTION_HELPER_FAILED_CLOSED_ROLLBACK_COMPLETE')
$failureActionRegressionTokens=@('EMPTY_ACTION_SET_REPRESENTED','PRIOR_RESTART_5000_CAPTURED','TARGET_CONTAINS_ZERO_ACTIONS','NONZERO_ACTION_READBACK_REJECTED','RESTART_READBACK_REJECTED','RUN_COMMAND_READBACK_REJECTED','REBOOT_READBACK_REJECTED','ROLLBACK_RECONSTRUCTS_RESTART_5000','EMPTY_ARGUMENT_OMISSION_DETECTED','LITERAL_QUOTE_CORRUPTION_DETECTED','EXTRA_ACTION_DETECTED','HELPER_FAILURE_FAILS_CLOSED')
$failureActionMissing=@($failureActionNativeTokens|Where-Object{-not $failureActionSource.Contains($_)})+@($failureActionRegressionTokens|Where-Object{-not $failureActionVerifier.Contains($_)})
Add-Check 'unit2b-failure-actions-use-measured-native-structure-and-negative-regressions' ($failureActionMissing.Count -eq 0 -and $failureActionSource.Contains('cActions') -eq $false -and $failureActionVerifier.Contains('native_api_invoked')) ([ordered]@{helper_sha256=(Get-LowerHash $failureActionSourcePath);missing_tokens=$failureActionMissing;verifier_sha256=(Get-LowerHash $failureActionVerifierPath)})
$artifactToolSource=Get-Content -LiteralPath (Join-Path $sourceRoot 'R7ArtifactTool.cs') -Raw
$safeFileSource=Get-Content -LiteralPath (Join-Path $sourceRoot 'R7SafeFile.cs') -Raw
$targetBuildSource=Get-Content -LiteralPath (Join-Path $packageRoot 'build_remediation_package.ps1') -Raw
$protectedMethod=[regex]::Match($safeFileSource,'(?s)internal static R7VerifiedMetadataFile HoldProtectedMetadataFile\(.+?\n        }\r?\n\r?\n        internal static R7VerifiedDirectory')
$protectedMetadataClosed=$protectedMethod.Success -and -not $protectedMethod.Value.Contains('GenericRead') -and -not $protectedMethod.Value.Contains('ReadAll(') -and $protectedMethod.Value.Contains('FileReadAttributes | ReadControl') -and $protectedMethod.Value.Contains('FileFlagBackupSemantics | FileFlagOpenReparsePoint') -and $protectedMethod.Value.Contains('StreamsByHandle(handle)')
Add-Check 'protected-key-metadata-is-held-no-read-and-exact-commit-bound' ($protectedMetadataClosed -and $artifactToolSource.Contains('measure-protected-metadata') -and $artifactToolSource.Contains('"data_access_requested", false') -and $artifactToolSource.Contains('"private_bytes_read", false') -and $artifactToolSource.Contains('"privilege_restored_before_evidence_write", true') -and $safeFileSource.Contains('RestoreTokenPrivileges') -and $targetBuildSource.Contains('Generated\ImmutableOrchestratorRepository') -and $targetBuildSource.Contains('R7_PROTECTED_METADATA_TOOL_BUILD_RECEIPT') -and $targetBuildSource.Contains('R7_PROTECTED_METADATA_TOOL_INVOCATION_RECEIPT') -and $targetBuildSource.Contains('private_bytes_read=$false') -and $targetBuildSource.Contains('data_access_requested=$false')) ([ordered]@{artifact_tool_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7ArtifactTool.cs'));build_script_sha256=(Get-LowerHash (Join-Path $packageRoot 'build_remediation_package.ps1'));safe_file_sha256=(Get-LowerHash (Join-Path $sourceRoot 'R7SafeFile.cs'))})
$unit2BuildPath=Join-Path $packageRoot 'build_unit2_upgrade_authority.ps1'
$unit2BuildSource=Get-Content -LiteralPath $unit2BuildPath -Raw
$unit2ClosureVerifierPath=Join-Path $packageRoot 'verify_unit2_build_closure.ps1'
$unit2ClosureVerifierSource=Get-Content -LiteralPath $unit2ClosureVerifierPath -Raw
$unit2RequiredNegativeMutations=@('OMIT_COMMITTED_COMPILER_INPUT','OMIT_GENERATED_COMPILER_INPUT','REMOVE_REQUIRED_COMPILER_ARGUMENT','ZERO_EMBEDDED_IDENTITY','DIAGNOSTIC_EMBEDDED_IDENTITY','TOKEN_IN_NONCOMPILED_SOURCE_REGION','PACKAGED_TOOL_DIAGNOSTIC_IDENTITY','RECEIPT_SOURCE_NOT_IN_ARGUMENT_VECTOR','ARGUMENT_SOURCE_NOT_IN_RECEIPT','REORDER_COMPILER_ARGUMENTS','SUBSTITUTE_COMPILER_ARGUMENT','DUPLICATE_COMPILER_ARGUMENT','SUBSTITUTE_COMPILER_INPUT_RAW_SHA256','SUBSTITUTE_COMPILER_INPUT_SIZE','SUBSTITUTE_COMMITTED_GIT_BLOB','SUBSTITUTE_COMPILER_INPUT_MODE','SUBSTITUTE_GENERATED_INPUT_AUTHORITY','COMPILER_INPUT_SIZE_NUMBER_TO_STRING','COMPILER_INPUT_MODE_STRING_TO_NUMBER','COMMITTED_NULL_GENERATION_RULE_TO_SENTINEL','COMMITTED_NULL_GENERATOR_TO_SENTINEL','GENERATED_NULL_GIT_BLOB_TO_SENTINEL','GENERATED_NULL_MODE_TO_SENTINEL','DETERMINISM_COMPILER_INPUT_HASH_CHANGED','DETERMINISM_COMPILER_INPUT_REMOVED','DETERMINISM_COMPILER_INPUT_ADDED','DETERMINISM_COMPILER_INPUTS_REORDERED','DETERMINISM_COMPILER_INPUT_SIZE_NUMBER_TO_STRING','COORDINATED_GENERATED_PRODUCER_AUTHORITY_AND_ROLE','COORDINATED_GENERATED_PRODUCER_ALL_RECEIPTS','UNAUTHORIZED_GENERATED_SOURCE_ROLE_ASSIGNMENT','MISSING_FIELD_REPLACES_EXPLICIT_NULL','UNKNOWN_COMPILER_INPUT_FIELD','CRLF_COMPILER_MATERIALIZATION','WORKTREE_PSEUDO_BLOB_FOR_TREE_BLOB','WORKTREE_SHA_FOR_COMMITTED_SHA','WORKTREE_SIZE_FOR_COMMITTED_SIZE','UNGOVERNED_COMPILER_BYTE_MUTATION','COORDINATED_CONFIGURATION_HASH_AND_CONSUMERS','COORDINATED_CONFIGURATION_PATH_SIZE_AND_CONSUMERS','CONFIGURATION_INPUT_REMOVED','CONFIGURATION_INPUT_INSERTED','CONFIGURATION_INPUTS_REORDERED','COORDINATED_CLOSURE_AND_CONSUMERS','COORDINATED_POLICY_AND_CONSUMERS','POLICY_ARTIFACT_PATH_SUBSTITUTED','COORDINATED_GENERATED_SOURCE_INPUTS_ALL_RECEIPTS','SOURCE_COMMIT_RETAINING_CONSUMERS','TREE_BLOB_CHANGED_WITH_ALL_CONSUMERS','CLOSURE_SERIALIZATION_ORDER_CHANGED','FORGED_RECEIPTS_ORIGINAL_GENERATED_OUTPUT','BATCH_HEADER_EMBEDDED_CR','BATCH_HEADER_CRLF_TERMINATOR','BATCH_HEADER_UPPERCASE_OID','BATCH_HEADER_SHORT_OID','BATCH_HEADER_LONG_OID','BATCH_HEADER_NONHEX_OID','BATCH_PAYLOAD_FROM_OTHER_BLOB','BATCH_ARBITRARY_PAYLOAD','BATCH_DECLARED_SIZE_INCORRECT','BATCH_DECLARED_SIZE_SMALLER','BATCH_DECLARED_SIZE_LARGER','BATCH_PAYLOAD_TRUNCATED','BATCH_PAYLOAD_DELIMITER_MISSING','BATCH_PAYLOAD_DELIMITER_CRLF','BATCH_OBJECT_TYPE_WRONG','BATCH_RESPONSE_REORDERED','BATCH_RESPONSE_DUPLICATE','BATCH_RESPONSE_MISSING','BATCH_TRAILING_JUNK','BATCH_TRAILING_LF','BATCH_EXTRA_VALID_FRAME','BATCH_DECLARED_SIZE_OVERFLOW','BATCH_HEADER_PARTIAL_EOF','BATCH_PROCESS_NONZERO','LIFECYCLE_OVERSIZED_DECLARED_PAYLOAD','LIFECYCLE_AGGREGATE_BUDGET_EXCEEDED','LIFECYCLE_SUSTAINED_STDOUT','LIFECYCLE_STDERR_LIMIT_EXCEEDED','LIFECYCLE_CONCURRENT_STREAMS_NONZERO','LIFECYCLE_CHILD_HOLDS_STDOUT','LIFECYCLE_CHILD_HOLDS_STDERR','LIFECYCLE_CHILD_HOLDS_BOTH_PIPES','LIFECYCLE_PARENT_HANGS_AFTER_FRAMES','LIFECYCLE_CHILD_ALIVE_AFTER_PARENT_EXIT','LIFECYCLE_CHILD_ALIVE_AFTER_PARENT_TIMEOUT','LIFECYCLE_DELAYED_TRAILING_STDOUT','LIFECYCLE_VALID_FRAMES_NONZERO_EXIT','LIFECYCLE_EXIT_BEFORE_REQUIRED_FRAMES','LIFECYCLE_TIMEOUT_HEADER_READ','LIFECYCLE_TIMEOUT_PAYLOAD_READ','LIFECYCLE_TIMEOUT_EXACT_EOF','LIFECYCLE_TIMEOUT_STDERR_COMPLETION','LIFECYCLE_CLEANUP_DEADLINE_EXCEEDED','LIFECYCLE_TREE_TERMINATION_UNCONFIRMED','LIFECYCLE_EXPECTED_SIZE_MISMATCH','LIFECYCLE_AGGREGATE_ARITHMETIC_OVERFLOW')
$unit2RequiredNegativeMutations+=@('LAUNCH_UNLISTED_FILE_HANDLE','LAUNCH_UNLISTED_ANONYMOUS_PIPE','LAUNCH_UNLISTED_NAMED_PIPE','LAUNCH_CROSS_RUN_STDOUT','LAUNCH_CROSS_RUN_STDERR','LAUNCH_CROSS_RUN_STDIN','LAUNCH_ENV_SENTINEL_ABSENT','LAUNCH_GIT_TRACE_ABSENT','LAUNCH_GIT_CONFIG_COUNT_ABSENT','LAUNCH_GIT_DIR_ABSENT','LAUNCH_GIT_WORK_TREE_ABSENT','LAUNCH_GIT_OBJECT_DIRECTORY_ABSENT','LAUNCH_HOME_PROFILE_ABSENT','LAUNCH_ENV_DUPLICATE_REJECTED','LAUNCH_ENV_NUL_REJECTED','LAUNCH_ATTRIBUTE_INIT_FAILURE','LAUNCH_HANDLE_LIST_UPDATE_FAILURE','LAUNCH_JOB_ASSIGNMENT_FAILURE','LAUNCH_JOB_ASSIGNMENT_CHILD_TERMINATED','LAUNCH_JOB_ASSIGNMENT_CONFIRMATION_FAILURE','LAUNCH_RESUME_FAILURE','LAUNCH_RESUME_JOB_CLEANUP','LAUNCH_RESUME_CONFIRMATION_FAILURE','LAUNCH_HOSTILE_PATH_IGNORED','LAUNCH_ONLY_THREE_STD_HANDLES','LAUNCH_CONCURRENT_HANDLE_ISOLATION','LAUNCH_NO_FAULT_SURVIVOR','LAUNCH_NO_PENDING_TASKS','LAUNCH_FAULT_DEADLINE_BOUNDED')
$unit2RequiredNegativeMutations+=@('P03A_JOB_LIST_SIZE_FAILURE','P03A_JOB_LIST_INIT_FAILURE','P03A_JOB_LIST_UPDATE_FAILURE','P03A_JOB_AT_CREATION_REJECTION','P03A_NO_CHILD_ON_CREATION_REJECTION','P03A_PRE_RESUME_QUERY_FAILURE','P03A_PRE_RESUME_ACTIVE_UNEXPECTED','P03A_ACTUAL_RESUME_FAILURE','P03A_UNEXPECTED_SUSPEND_COUNT','P03A_RESUME_JOB_CLEANUP','P03A_JOB_TERMINATION_FAILURE','P03A_PROCESS_TERMINATION_FAILURE','P03A_BOTH_TERMINATIONS_FAIL_FINAL_ZERO','P03A_FINAL_QUERY_FAILURE','P03A_PARENT_WAIT_FAILURE','P03A_CLEANUP_DEADLINE_EXHAUSTION','P03A_PREQUERY_AND_FINAL_QUERY_FAILURE','P03A_ATTRIBUTE_ALLOCATION_CLEANUP','P03A_REPEATED_JOB_AT_CREATION_FAILURES','P03A_REPEATED_RESUME_FAILURE','P03A_PRE_RESUME_MARKER_ABSENT','P03A_TASKS_TERMINAL','P03A_ORIGINAL_DEADLINE_BOUND','P03A_TASK_COMPLETED','P03A_TASK_FAULTED','P03A_TASK_CANCELED','P03A_AUTHENTIC_CONTAINED_LAUNCH')
$unit2RequiredNegativeMutations+=@('X01_FALLBACK_AFTER_DEADLINE','X01_FALLBACK_BEFORE_TASK_OBSERVATION','X01_PID_RECONCILIATION_AFTER_DEADLINE','X01_TASK_RECONCILIATION_AFTER_DEADLINE','X01_START_BEFORE_COMPLETE_AFTER','X01_START_AFTER_DEADLINE','X01_UNKNOWN_JOB_AUTHORITY','X01_INCOMPLETE_PID_AUTHORITY','X01_RECONSTRUCT_AFTER_TIMESTAMP_CHANGE','X01_DIAGNOSTIC_PROCESS_CONDITIONS','X01_POST_JOB_CLOSE_SNAPSHOT','X01_FINAL_TERMINAL_SNAPSHOT','LIFECYCLE_READINESS_WRONG_NONCE','LIFECYCLE_READINESS_STALE_NONCE','LIFECYCLE_READINESS_REPLAY','LIFECYCLE_READINESS_WRONG_CASE','LIFECYCLE_READINESS_WRONG_PARENT','LIFECYCLE_READINESS_UNRELATED_PID','LIFECYCLE_READINESS_OUTSIDE_JOB','LIFECYCLE_READINESS_NOT_DESCENDED','LIFECYCLE_READINESS_MISSING_DESCENDANT','LIFECYCLE_READINESS_DUPLICATE_DESCENDANT','LIFECYCLE_READINESS_DEAD_DESCENDANT','LIFECYCLE_READINESS_MISSING_STDOUT','LIFECYCLE_READINESS_MISSING_STDERR','LIFECYCLE_READINESS_STDOUT_THROUGH_STDERR','LIFECYCLE_READINESS_STDERR_THROUGH_STDOUT','LIFECYCLE_READINESS_WRONG_STREAM_ROLE','LIFECYCLE_READINESS_WRONG_TOKEN_PID','LIFECYCLE_READINESS_INCOMPLETE_RECORD','LIFECYCLE_READINESS_PARENT_EXITS','LIFECYCLE_READINESS_MODIFIED_AFTER_PUBLICATION','X03_STDOUT_RUNNING_UNTIL_CLOSE','X03_STDERR_RUNNING_UNTIL_CLOSE','X03_BOTH_RUNNING_UNTIL_CLOSE','X03_BOTH_RUNNING_UNTIL_JOB_CLOSE','X03_INPUT_COMPLETES_PIPES_RUNNING','X03_INPUT_FAULTS_DURING_TERMINALIZATION','X03_INPUT_CANCELS_DURING_TERMINALIZATION','X03_STDOUT_FAULTS_DURING_TERMINALIZATION','X03_STDERR_CANCELS_DURING_TERMINALIZATION','X03_PARENT_EXITS_WITH_ACTIVE_PIPES','X03_DESCENDANT_EXITS_AFTER_JOB_CLOSE','X03_PID_DISAPPEARS_AFTER_JOB_CLOSE','X03_DELAYED_PIPE_COMPLETION_AFTER_EXIT','X03_POST_CLOSE_PROCESS_REMEASUREMENT','X03_POST_CLOSE_TASK_REMEASUREMENT','X03_PRE_RETURN_PID_OBSERVATION','X03_PRE_RETURN_TASK_OBSERVATION','X03_DELIBERATELY_NONTERMINAL_OPERATION')
$unit2RequiredNegativeMutations+=@('XID_NON_EOL_RAW_DIFFERENCE_WITH_CLEAN_MATCH','XID_SEMANTIC_CHARACTER_WITH_CRLF','XID_WHITESPACE_BEYOND_CRLF','XID_FINAL_NEWLINE_ADDED','XID_FINAL_NEWLINE_REMOVED','XID_BOM_INSERTED','XID_BOM_REMOVED','XID_LONE_CR','XID_MIXED_EOL_SEMANTIC','XID_CUSTOM_CLEAN_FILTER','XID_CUSTOM_SMUDGE_FILTER','XID_REQUIRED_EXTERNAL_FILTER','XID_UNAUTHORIZED_WORKING_TREE_ENCODING','XID_WRONG_CLEAN_FILTER_PATH_CONTEXT','XID_WRONG_TREE_BLOB','XID_MISSING_TREE_ENTRY','XID_NON_BLOB_TREE_ENTRY','XID_STAGED_SEMANTIC_MUTATION','XID_UNSTAGED_SEMANTIC_MUTATION','XID_UNTRACKED_REPLACEMENT','XID_SYMLINK_SUBSTITUTION','XID_PATH_REDIRECTION','XID_MISSING_RAW_IDENTITY','XID_MISSING_CLEAN_FILTER_IDENTITY','XID_MISSING_EOL_NORMALIZED_IDENTITY','XID_MISSING_EOL_ONLY_AUTHORITY','XID_CONTRADICTORY_RAW_EQUALITY','XID_CONTRADICTORY_CLEAN_FILTER_EQUALITY','XID_CONTRADICTORY_EOL_ONLY_TUPLE','XID_RAW_MISMATCH_WITHOUT_EOL_AUTHORITY','XID_CANDIDATE_FOR_EXACT_COMMIT','XID_BUILD_VERIFIER_PREDICATE_DISAGREEMENT','XID_RECEIPT_VERIFIER_SCHEMA_DISAGREEMENT','XID_FALSE_NO_CUSTOM_FILTER_DECLARATION')
$unit2NegativeMutations=@($unit2Negative.cases|ForEach-Object{[string]$_.mutation})
$unit2NegativeCaseIds=@($unit2Negative.cases|ForEach-Object{[string]$_.case_id})
$unit2RequiredNegativeCaseIds=@(1..237|ForEach-Object{'U2BC-N'+$_.ToString('D3')})
$unit2MissingNegativeMutations=@($unit2RequiredNegativeMutations|Where-Object{$_ -cnotin $unit2NegativeMutations})
$unit2PositiveMutations=@($unit2Negative.lifecycle_positive_cases|ForEach-Object{[string]$_.mutation});$unit2PositiveCaseIds=@($unit2Negative.lifecycle_positive_cases|ForEach-Object{[string]$_.case_id});$unit2ExpectedPositiveMutations=@('LIFECYCLE_VALID_BOUNDED_STDERR','LIFECYCLE_VALID_AUTHENTIC_MULTI_OBJECT')
$unit2NegativeRegistryComplete=$unit2MissingNegativeMutations.Count-eq0 -and $unit2NegativeMutations.Count-eq$unit2RequiredNegativeMutations.Count -and $unit2NegativeMutations.Count-eq@($unit2NegativeMutations|Select-Object -Unique).Count -and ($unit2NegativeMutations-join"`n")-ceq($unit2RequiredNegativeMutations-join"`n") -and ($unit2NegativeCaseIds-join"`n")-ceq($unit2RequiredNegativeCaseIds-join"`n") -and ($unit2PositiveMutations-join"`n")-ceq($unit2ExpectedPositiveMutations-join"`n") -and ($unit2PositiveCaseIds-join"`n")-ceq"U2BC-P001`nU2BC-P002"
$negativeContainer=Get-RegistryContainerRecord $unit2NegativePath $unit2Negative 'UNIT2_NEGATIVE_CASE' $unit2NegativeCaseIds $true
$governedContainer=Get-RegistryContainerRecord $scriptRegistryPath $scriptRegistry 'GOVERNANCE_ORCHESTRATOR' @($scriptRegistry.scripts|ForEach-Object{Split-Path -Leaf ([string]$_.path)}) $true
$sourceContainer=Get-RegistryContainerRecord $sourceRolePath $sourceRoleRegistry 'SOURCE_FILE' @($sourceRoleRegistry.sources|ForEach-Object{[string]$_.path}) $false
$utilityContainer=Get-RegistryContainerRecord $utilityRegistryPath $utilityRegistry 'EXTERNAL_UTILITY_INPUT' @($utilityRegistry.utilities|ForEach-Object{[string]$_.role}) $false
$traceContainers=@($negativeContainer,$governedContainer,$sourceContainer,$utilityContainer)|Sort-Object path
$traceCandidates=[Collections.Generic.List[object]]::new()
foreach($name in @('build_unit2_upgrade_authority.ps1','generate_static_closure_registries.ps1','generate_traceability.ps1','verify_static_architecture.ps1','verify_unit2_build_closure.ps1')){$row=@($scriptRegistry.scripts|Where-Object{(Split-Path -Leaf ([string]$_.path))-ceq$name});if($row.Count-ne1){throw "TRACE_CANDIDATE_IDENTITY_MISSING: $name"};$traceCandidates.Add([ordered]@{artifact_class='CANDIDATE_IDENTITY';git_blob_identity=[string]$row[0].git_blob_identity;path=[string]$row[0].path;raw_sha256=[string]$row[0].raw_sha256;size=[long]$row[0].size})}
foreach($container in $traceContainers){$traceCandidates.Add([ordered]@{artifact_class='CANDIDATE_IDENTITY';git_blob_identity=[string]$container.git_blob_identity;path=[string]$container.path;raw_sha256=[string]$container.raw_sha256;size=[long]$container.size})}
$traceContract=Assert-StaticTraceabilityContract $traceability @($cases.cases|ForEach-Object{[string]$_.case_id}) @($unit2Negative.cases) $traceContainers @($sourceRoleRegistry.sources|ForEach-Object{[string]$_.path}) @($scriptRegistry.scripts|ForEach-Object{Split-Path -Leaf ([string]$_.path)}) @($utilityRegistry.utilities|ForEach-Object{[string]$_.role}) @($traceCandidates.ToArray())
Add-Check 'unit2-static-traceability-contract-complete' ($traceContract.unit2_case_count-eq237-and$traceContract.unit2_n204_n237_count-eq34-and$traceContract.registry_container_count-eq4-and$traceContract.r7_case_count-eq151) $traceContract
$identityContractPath=Join-Path $packageRoot 'BuildInputs\R7BuildIdentityContract.cs'
$identityContractSource=Get-Content -LiteralPath $identityContractPath -Raw
$unit2AuthoritySource=Get-Content -LiteralPath (Join-Path $sourceRoot 'R7Unit2UpgradeAuthority.cs') -Raw
$legacyIdentityPath=Join-Path $packageRoot 'BuildInputs\R7DevelopmentIdentity.g.cs'
$unit2SourceTokens=@('UNIT2_GENERATED_','BOOTSTRAP_PENDING','STATIC_PLACEHOLDER','R7DevelopmentIdentity')
$unit2TokenFindings=@($unit2SourceTokens|Where-Object{$unit2AuthoritySource.Contains($_)-or$identityContractSource.Contains($_)})
Add-Check 'unit2-build-generates-final-identities-and-never-opens-private-key' (-not(Test-Path -LiteralPath $legacyIdentityPath) -and $unit2TokenFindings.Count -eq 0 -and $unit2BuildSource.Contains('R7Unit2ClientShared.g.cs') -and $unit2BuildSource.Contains('R7Unit2Service.g.cs') -and $unit2BuildSource.Contains('R7PackagedTools.g.cs') -and $unit2BuildSource.Contains('NONCIRCULAR_INPUT_CLOSURE_DERIVATION_V1') -and $unit2BuildSource.Contains('EXACT_POLICY_SHA256') -and $unit2BuildSource.Contains('compiler_arguments') -and $unit2BuildSource.Contains('compiler_inputs') -and $unit2BuildSource.Contains('PACKAGED_ARTIFACT_TOOL') -and $unit2BuildSource.Contains('PACKAGED_PROTECTED_METADATA_TOOL') -and $unit2BuildSource.Contains('ReflectionOnlyLoadFrom') -and -not $unit2BuildSource.Contains('measure-protected-metadata $keyPath') -and -not $unit2BuildSource.Contains('CngKey') -and -not $unit2BuildSource.Contains('SignData') -and -not $unit2BuildSource.Contains('SignHash')) ([ordered]@{build_script_sha256=(Get-LowerHash $unit2BuildPath);contract_sha256=(Get-LowerHash $identityContractPath);source_token_findings=$unit2TokenFindings})
Add-Check 'unit2-build-closure-verifier-and-negative-regressions-are-explicit' ($unit2NegativeRegistryComplete -and $unit2ClosureVerifierSource.Contains('COMPILER_INPUT_SET_MISMATCH') -and $unit2ClosureVerifierSource.Contains('COMPILER_INPUT_IDENTITY_MISMATCH') -and $unit2ClosureVerifierSource.Contains('COMPILER_INPUT_TYPE_MISMATCH') -and $unit2ClosureVerifierSource.Contains('COMPILER_ARGUMENT_VECTOR_MISMATCH') -and $unit2ClosureVerifierSource.Contains('GENERATED_SOURCE_TOKEN_INVALID') -and $unit2ClosureVerifierSource.Contains('PACKAGED_TOOL_IDENTITY_INVALID') -and $unit2ClosureVerifierSource.Contains('TestExactCheckoutIdentityRecord') -and $unit2ClosureVerifierSource.Contains('EXACT_CHECKOUT_IDENTITY_INVALID') -and $unit2ClosureVerifierSource.Contains('clean_filtered_worktree_blob_identity') -and $unit2ClosureVerifierSource.Contains('eol_only_exception') -and $unit2ClosureVerifierSource.Contains('ExactJsonEqual') -and $unit2ClosureVerifierSource.Contains('ExactTreeBlobAuthority') -and $unit2ClosureVerifierSource.Contains('ReadAuthenticatedGitBatch') -and $unit2ClosureVerifierSource.Contains('GitBlobIdentity') -and $unit2ClosureVerifierSource.Contains('GIT_BATCH_TRAILING_OUTPUT') -and $unit2ClosureVerifierSource.Contains('ReadGitBlobBytes') -and $unit2ClosureVerifierSource.Contains('GroundedConfigurationInventory') -and $unit2ClosureVerifierSource.Contains('RecomputeBuildInputClosure') -and $unit2ClosureVerifierSource.Contains('GroundedPolicyAuthority') -and $unit2ClosureVerifierSource.Contains('AssertGeneratedOutputAuthority') -and $unit2ClosureVerifierSource.Contains('GroundedGeneratorAuthority') -and $unit2ClosureVerifierSource.Contains('GeneratedSourceContract') -and $unit2ClosureVerifierSource.Contains('AssertDeterminismCompilerInputs') -and $unit2ClosureVerifierSource.Contains('AssertCompilerInputBinding') -and $unit2ClosureVerifierSource.Contains('ExtractIdentity') -and $unit2ClosureVerifierSource.Contains('ValidateModel') -and $unit2ClosureVerifierSource.Contains('PROC_THREAD_ATTRIBUTE_JOB_LIST') -and $unit2ClosureVerifierSource.Contains('CleanupCreatedProcessAndFail') -and -not $unit2ClosureVerifierSource.Contains('AssignProcessToJobObject')) ([ordered]@{missing_mutations=$unit2MissingNegativeMutations;negative_case_count=@($unit2Negative.cases).Count;negative_registry_sha256=(Get-LowerHash $unit2NegativePath);verifier_sha256=(Get-LowerHash $unit2ClosureVerifierPath)})
$declaredScriptNames=@($scriptRegistry.scripts|ForEach-Object{Split-Path -Leaf ([string]$_.path)}|Sort-Object)
$actualScriptNames=@($packageScripts|ForEach-Object Name|Sort-Object)
$badScriptRows=[Collections.Generic.List[object]]::new()
foreach($row in @($scriptRegistry.scripts)){
    $path=Join-Path $repositoryRoot ([string]$row.path).Replace('/','\')
    try {
        [void](Get-RegistryBoundIdentity $path $row 'GOVERNED_SCRIPT' $true)
        if(@($row.allowed_invocation_stages).Count -eq 0 -or @($row.dependencies).Count -eq 0){throw 'IDENTITY_SCRIPT_ROUTING_INCOMPLETE'}
    } catch { $badScriptRows.Add([ordered]@{path=[string]$row.path;reason=$_.Exception.Message}) }
}
Add-Check 'governed-script-set-is-exact-and-content-bound' ([int]$scriptRegistry.script_count -eq $packageScripts.Count -and ($declaredScriptNames -join "`n") -ceq ($actualScriptNames -join "`n") -and $badScriptRows.Count -eq 0) ([ordered]@{bad_rows=$badScriptRows.ToArray();registry_sha256=(Get-LowerHash $scriptRegistryPath);script_count=$packageScripts.Count})
$requiredUtilityRoles=@('GIT_BUILD_AND_VERIFICATION','POWERSHELL_ORCHESTRATOR','CSC_COMPILER','ILDASM_TOOL','SC_SERVICE_CONTROL_TOOL','ICACLS_ACL_TOOL','FSUTIL_PATH_FIXTURE_TOOL','POWERSHELL_MANAGEMENT_ASSEMBLY','POWERSHELL_JOB_ASSEMBLY','POWERSHELL_UTILITY_MODULE_MANIFEST','POWERSHELL_UTILITY_MODULE_SCRIPT','PKI_MODULE_MANIFEST','PKI_MODULE_TYPES')
$badUtilityRows=[Collections.Generic.List[object]]::new();$utilityRoles=@($utilityRegistry.utilities|ForEach-Object{[string]$_.role})
foreach($row in @($utilityRegistry.utilities)){
    $path=[IO.Path]::GetFullPath([string]$row.path)
    if([bool]$row.path_search_allowed -or [bool]$row.runtime_authority -or -not(Test-Path -LiteralPath $path -PathType Leaf) -or (Get-LowerHash $path) -cne [string]$row.measurement.sha256 -or (Get-Item -LiteralPath $path).Length -ne [long]$row.measurement.size -or @($row.required_by_scripts).Count -eq 0 -or @($row.allowed_invocation_stages).Count -eq 0){$badUtilityRows.Add($row)}
}
Add-Check 'external-utility-set-is-classified-absolute-and-content-bound' ([int]$utilityRegistry.utility_count -eq @($utilityRegistry.utilities).Count -and $badUtilityRows.Count -eq 0 -and @($requiredUtilityRoles|Where-Object{$_ -notin $utilityRoles}).Count -eq 0) ([ordered]@{bad_rows=$badUtilityRows.ToArray();missing_roles=@($requiredUtilityRoles|Where-Object{$_ -notin $utilityRoles});registry_sha256=(Get-LowerHash $utilityRegistryPath);utility_count=@($utilityRegistry.utilities).Count})
$pathSearchFindings=[Collections.Generic.List[object]]::new()
foreach($script in $packageScripts){$text=Get-Content -LiteralPath $script.FullName -Raw;if($text -match '(?im)Get-Command\s+(?:git|sc|icacls|fsutil|csc|ildasm|powershell)(?:\.exe)?\b' -or $text -match '(?im)^\s*&\s*(?:git|sc|icacls|fsutil|csc|ildasm|powershell)(?:\.exe)?\b'){$pathSearchFindings.Add([ordered]@{path=$script.Name})}}
Add-Check 'external-process-launches-do-not-use-path-search' ($pathSearchFindings.Count -eq 0) $pathSearchFindings.ToArray()
$blockers = Read-Json (Join-Path $packageRoot 'blocker_remediation_map.json')
$missingImplementations = [Collections.Generic.List[string]]::new()
foreach ($blocker in @($blockers.blockers)) {
    foreach ($implementation in @($blocker.implementation)) { if (-not (Test-Path -LiteralPath (Join-Path $packageRoot $implementation))) { $missingImplementations.Add(($blocker.id + '|' + $implementation)) } }
}
Add-Check 'all-sixteen-blockers-have-existing-implementation-surfaces' (@($blockers.blockers).Count -eq 16 -and $missingImplementations.Count -eq 0) ([ordered]@{ blocker_count = @($blockers.blockers).Count; missing = $missingImplementations.ToArray() })
Add-Check 'all-blockers-remain-explicitly-partial' (@($blockers.blockers|Where-Object{[string]$_.status -cne 'PARTIAL'}).Count -eq 0 -and [string]$blockers.overall_status -match 'PARTIAL') ([ordered]@{overall_status=$blockers.overall_status;nonpartial=@($blockers.blockers|Where-Object{[string]$_.status -cne 'PARTIAL'}|ForEach-Object id)})
$readmePath=Join-Path $packageRoot 'README.md';$aiaPath=Join-Path $packageRoot 'Architecture_Impact_Assessment_PROPOSAL.md';$deltaPath=Join-Path $packageRoot 'Canonical_Delta_PROPOSAL.md';$threatPath=Join-Path $packageRoot 'Threat_Model.md'
$readmeText=Get-Content -LiteralPath $readmePath -Raw;$aiaText=Get-Content -LiteralPath $aiaPath -Raw;$deltaText=Get-Content -LiteralPath $deltaPath -Raw;$threatText=Get-Content -LiteralPath $threatPath -Raw
$documentationCorpus=$readmeText+"`n"+$aiaText+"`n"+$deltaText+"`n"+$threatText
$requiredDocumentationTokens=@('terminal signer, execution, observation, comparator, and upgrade authority','SeDenyInteractiveLogonRight','SeDenyRemoteInteractiveLogonRight','POS-005','POS-006','canonical','R7MeasuredUtility.cs','R7RecoveryProbeAuditor','runtime dependency closure','matrix','No live outer execution occurred','AUTHORIZED FOR FUTURE INSTALLATION CONSIDERATION')
$missingDocumentationTokens=@($requiredDocumentationTokens|Where-Object{-not $documentationCorpus.Contains($_)})
$boundedDocumentationClaims=$readmeText.Contains('Every `R7AR-B01` through `R7AR-B16` finding remains **PARTIAL**') -and $readmeText.Contains('does not accept R7') -and $readmeText.Contains('Terminal v4 installation/activation') -and $aiaText.Contains('All sixteen independent-review blockers remain partial') -and $aiaText.Contains('Acceptance remains solely a later independent-review decision') -and $deltaText.Contains('No canonical record, terminal installation/activation, terminal-ledger change, receipt, reconciliation, matrix run, deployment, or review disposition follows') -and $threatText.Contains('All `R7AR-B01` through `R7AR-B16` findings therefore remain partial') -and $threatText.Contains('Unit 2 authorization is not, by itself, proof that future current state remains unchanged')
Add-Check 'proposal-readme-threat-and-blocker-documentation-synchronized-to-unit2-bounded-partial-state' ($missingDocumentationTokens.Count -eq 0 -and $boundedDocumentationClaims) ([ordered]@{architecture_impact_assessment_sha256=(Get-LowerHash $aiaPath);canonical_delta_sha256=(Get-LowerHash $deltaPath);missing_tokens=$missingDocumentationTokens;readme_sha256=(Get-LowerHash $readmePath);threat_model_sha256=(Get-LowerHash $threatPath)})

if (-not [string]::IsNullOrWhiteSpace($StaticBuildRoot)) {
    $staticBuild=[IO.Path]::GetFullPath($StaticBuildRoot)
    $receiptPath=Join-Path $staticBuild 'static_build_receipt.json';$summaryPath=Join-Path $staticBuild 'static_build_summary.json';$dependencyPath=Join-Path $staticBuild 'Generated\static_dependency_manifest.json'
    foreach($required in @($receiptPath,$summaryPath,$dependencyPath)){if(-not(Test-Path -LiteralPath $required -PathType Leaf)){throw "Static build evidence missing: $required"}}
    $receipt=Read-Json $receiptPath;$summary=Read-Json $summaryPath;$dependency=Read-Json $dependencyPath
    $badBinaries=@($receipt.binaries|Where-Object{$_.normalized_il_equal -ne $true -or [string]$_.authority_classification -cne 'UNINSTALLED_NONAUTHORITATIVE_STATIC_COMPILE_EVIDENCE' -or @($_.source_paths).Count -ne $sourceFiles.Count})
    $unstableClosures=@($receipt.build_input_closures|Where-Object{$_.stable_during_use -ne $true -or [string]$_.initial_manifest_raw_sha256 -cne [string]$_.post_manifest_raw_sha256})
    Add-Check 'static-build-receipt-closes-all-roles-sources-and-dependencies' ([string]$receipt.status -ceq 'PASS' -and [int]$summary.binary_count -eq [int]$sourceRoleRegistry.executable_role_count -and @($receipt.binaries).Count -eq [int]$sourceRoleRegistry.executable_role_count -and $badBinaries.Count -eq 0 -and $unstableClosures.Count -eq 0 -and [string]$dependency.status -match 'RUNTIME_CLOSURE_REMAINS_PENDING_LIVE_PROOF' -and [string]$receipt.generated_identity.authority_classification -ceq 'UNINSTALLED_NONAUTHORITATIVE_STATIC_COMPILE_IDENTITY') ([ordered]@{bad_binaries=$badBinaries;build_receipt_sha256=(Get-LowerHash $receiptPath);dependency_manifest_sha256=(Get-LowerHash $dependencyPath);unstable_closures=$unstableClosures})
}

if (-not [string]::IsNullOrWhiteSpace($Unit2BuildRoot)) {
    if ([string]::IsNullOrWhiteSpace($Unit2ClosureReport)) { throw 'Unit2ClosureReport is required with Unit2BuildRoot.' }
    $unit2Build=[IO.Path]::GetFullPath($Unit2BuildRoot);$unit2ReportPath=[IO.Path]::GetFullPath($Unit2ClosureReport)
    $unit2ReceiptPath=Join-Path $unit2Build 'Generated\unit2_build_receipt.json';$unit2DeterminismPath=Join-Path $unit2Build 'Generated\unit2_build_determinism_receipt.json';$unit2ManifestPath=Join-Path $unit2Build 'unit2_build_manifest.json'
    foreach($required in @($unit2ReceiptPath,$unit2DeterminismPath,$unit2ManifestPath,$unit2ReportPath)){if(-not(Test-Path -LiteralPath $required -PathType Leaf)){throw "Unit 2 build-closure evidence missing: $required"}}
    $unit2Receipt=Read-Json $unit2ReceiptPath;$unit2Determinism=Read-Json $unit2DeterminismPath;$unit2Manifest=Read-Json $unit2ManifestPath;$unit2Report=Read-Json $unit2ReportPath
    $unit2BadRoles=@($unit2Receipt.roles|Where-Object{$_.normalized_il_equal-ne$true-or@($_.compiler_inputs).Count-ne(@($unit2Receipt.source_files).Count+1)-or@($_.compiler_arguments.pass_a).Count-ne@($_.compiler_arguments.pass_b).Count-or@($_.response_files).Count-ne0-or@($_.resource_files).Count-ne0})
    $unit2BadGenerated=@($unit2Receipt.generated_sources|Where-Object{[string]$_.generation_rule-notmatch'^R7_UNIT2_' -or [string]$_.raw_sha256-notmatch'^[0-9a-f]{64}$'})
    $unit2BadTargetExecutables=@($unit2Receipt.target_packaged_executables|Where-Object{[string]$_.raw_sha256-notmatch'^[0-9a-f]{64}$'-or@($_.embedded_identity.PSObject.Properties).Count-eq0})
    Add-Check 'unit2-exact-build-receipts-close-roles-inputs-arguments-and-generated-sources' ([string]$unit2Receipt.schema_version-ceq'2.0.0' -and @($unit2Receipt.roles).Count-eq8 -and @($unit2Receipt.generated_sources).Count-eq4 -and @($unit2Receipt.target_packaged_executables).Count-ge9 -and $unit2BadRoles.Count-eq0 -and $unit2BadGenerated.Count-eq0 -and $unit2BadTargetExecutables.Count-eq0 -and @($unit2Determinism.role_determinism).Count-eq8 -and @($unit2Determinism.target_packaged_executables).Count-eq@($unit2Receipt.target_packaged_executables).Count -and [string]$unit2Manifest.status-ceq'PASS' -and [string]$unit2Report.status-ceq'PASS' -and [int]$unit2Report.negative_test_count-eq@($unit2Negative.cases).Count -and @($unit2Report.negative_results).Count-eq@($unit2Negative.cases).Count) ([ordered]@{bad_generated=$unit2BadGenerated;bad_roles=$unit2BadRoles;bad_target_packaged_executables=$unit2BadTargetExecutables;closure_report_sha256=(Get-LowerHash $unit2ReportPath);determinism_receipt_sha256=(Get-LowerHash $unit2DeterminismPath);manifest_sha256=(Get-LowerHash $unit2ManifestPath);negative_case_count=@($unit2Negative.cases).Count;source_to_binary_receipt_sha256=(Get-LowerHash $unit2ReceiptPath);target_packaged_executable_count=@($unit2Receipt.target_packaged_executables).Count})
}

if (-not [string]::IsNullOrWhiteSpace($CompiledRoleRoot)) {
    $compiled = [IO.Path]::GetFullPath($CompiledRoleRoot)
    $staticVerifier = Join-Path $compiled 'RandleTerminalStaticVerifier.Offline.exe'
    if (-not (Test-Path -LiteralPath $staticVerifier -PathType Leaf)) { $staticVerifier = Join-Path $compiled 'R7StaticVerification.exe' }
    if (-not (Test-Path -LiteralPath $staticVerifier -PathType Leaf)) { $staticVerifier = Join-Path $compiled 'RandleTerminalStaticVerifier.exe' }
    if (-not (Test-Path -LiteralPath $staticVerifier -PathType Leaf)) { throw 'Compiled static verifier is absent.' }
    $parserOutput = @(& $staticVerifier parser)
    Add-Check 'compiled-strict-parser-suite' ($LASTEXITCODE -eq 0 -and (Read-JsonText ($parserOutput -join "`n")).status -eq 'PASS') ([ordered]@{ output = $parserOutput })
    $authorityOutput = @(& $staticVerifier authority $packageRoot (Get-LowerHash $requirementPath) (Get-LowerHash $casePath) (Get-LowerHash $expectationPath) (Get-LowerHash $coveragePath) (Get-LowerHash $manifestPath))
    $authorityResult = Read-JsonText ($authorityOutput -join "`n")
    Add-Check 'compiled-complete-authority-and-thirty-file-review-package-suite' ($LASTEXITCODE -eq 0 -and $authorityResult.status -eq 'PASS' -and [int]$authorityResult.case_count -eq $declaredCaseCount -and [int]$authorityResult.independent_review_package_file_count -eq 30) ([ordered]@{ output = $authorityOutput })
    if ([string]::IsNullOrWhiteSpace($TransactionProbeRoot)) { throw 'TransactionProbeRoot is required with CompiledRoleRoot.' }
    $transactionOutput = @(& $staticVerifier transaction ([IO.Path]::GetFullPath($TransactionProbeRoot)))
    Add-Check 'compiled-transaction-recovery-suite' ($LASTEXITCODE -eq 0 -and (Read-JsonText ($transactionOutput -join "`n")).status -eq 'PASS') ([ordered]@{ output = $transactionOutput })
    if ([string]::IsNullOrWhiteSpace($RecoveryProbeRoot)) { throw 'RecoveryProbeRoot is required with CompiledRoleRoot.' }
    $recoveryOutput = @(& $staticVerifier recovery ([IO.Path]::GetFullPath($RecoveryProbeRoot)))
    $recoveryResult = Read-JsonText ($recoveryOutput -join "`n")
    Add-Check 'compiled-isolated-recovery-algorithm-suite' ($LASTEXITCODE -eq 0 -and $recoveryResult.status -eq 'PASS' -and [int]$recoveryResult.fault_point_count -eq 24) ([ordered]@{ output = $recoveryOutput })
    if (-not [string]::IsNullOrWhiteSpace($LegacySnapshotRoot)) {
        $legacy = [IO.Path]::GetFullPath($LegacySnapshotRoot)
        $legacyOutput = @(& $staticVerifier legacy-history (Join-Path $legacy 'Ledger') (Join-Path $legacy 'Trust\terminal_authority_public.cer') (Join-Path $legacy 'Receipts') (Join-Path $legacy 'Reconciliations') (Join-Path $legacy 'Evidence') (Join-Path $legacy 'Responses') $historyPath)
        $legacyResult = Read-JsonText ($legacyOutput -join "`n")
        Add-Check 'compiled-version-aware-retained-history-suite' ($LASTEXITCODE -eq 0 -and $legacyResult.status -eq 'PASS' -and [int]$legacyResult.ledger_entry_count -eq 678 -and [int]$legacyResult.terminal_receipt_count -eq 64 -and [int]$legacyResult.reconciliation_receipt_count -eq 31 -and [int]$legacyResult.classification_binding_count -eq 10) ([ordered]@{ output = $legacyOutput })
    }
}

$result = [ordered]@{
    artifact_type = 'R7_STATIC_ARCHITECTURE_VERIFICATION'
    check_count = $checks.Count
    checks = $checks.ToArray()
    failed_count = @($checks | Where-Object status -eq 'FAIL').Count
    head = $head
    passed_count = @($checks | Where-Object status -eq 'PASS').Count
    schema_version = '1.0.0'
    status = 'PASS'
}
Write-JsonNew $result $OutputPath
Write-Output ([ordered]@{ checks = $checks.Count; output = [IO.Path]::GetFullPath($OutputPath); raw_sha256 = (Get-LowerHash $OutputPath); status = 'PASS' } | ConvertTo-Json)
