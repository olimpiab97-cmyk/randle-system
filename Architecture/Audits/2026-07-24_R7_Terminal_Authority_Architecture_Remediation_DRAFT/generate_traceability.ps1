[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string]$BuildRoot,
    [string]$MatrixRoot,
    [string]$HostInventoryPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$packageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $packageRoot '..\..\..'))
$safeRepository = $repositoryRoot.Replace('\','/')
$gitExecutable = 'C:\Program Files\Git\cmd\git.exe'
$requirementPath = Join-Path $packageRoot 'governed_requirement_registry.json'
$casePath = Join-Path $packageRoot 'immutable_case_definitions.json'
$expectationPath = Join-Path $packageRoot 'immutable_expectations.json'
$coveragePath = Join-Path $packageRoot 'exact_byte_coverage_proof.json'
$principalPath = Join-Path $packageRoot 'service_principal_registry.json'
$blockerPath = Join-Path $packageRoot 'blocker_remediation_map.json'
$sourceRolePath = Join-Path $packageRoot 'source_role_registry.json'
$scriptRegistryPath = Join-Path $packageRoot 'governed_script_registry.json'
$utilityRegistryPath = Join-Path $packageRoot 'external_utility_registry.json'
$unit2NegativePath = Join-Path $packageRoot 'unit2_build_closure_negative_cases.json'

function Read-Json([string]$Path) { return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json }
function Get-LowerHash([string]$Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function Git-Lines([string[]]$Arguments) {
    $value=@(& $gitExecutable -c "safe.directory=$safeRepository" -C $repositoryRoot @Arguments)
    if($LASTEXITCODE -ne 0){throw "git failed: $($Arguments -join ' ')"}
    return $value
}
function Get-RelativePath([string]$Base,[string]$Path){$baseFull=[IO.Path]::GetFullPath($Base).TrimEnd('\')+'\';$pathFull=[IO.Path]::GetFullPath($Path);return [Uri]::UnescapeDataString(([Uri]$baseFull).MakeRelativeUri([Uri]$pathFull).ToString()).Replace('\','/')}
function Get-Sha256Bytes([byte[]]$Bytes){$sha=[Security.Cryptography.SHA256]::Create();try{return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}}
function Get-GitBlobIdentityBytes([byte[]]$Bytes){$header=[Text.Encoding]::ASCII.GetBytes(('blob '+$Bytes.Length+[char]0));$all=New-Object byte[] ($header.Length+$Bytes.Length);[Buffer]::BlockCopy($header,0,$all,0,$header.Length);[Buffer]::BlockCopy($Bytes,0,$all,$header.Length,$Bytes.Length);$sha=[Security.Cryptography.SHA1]::Create();try{return ([BitConverter]::ToString($sha.ComputeHash($all))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}}
function Get-StrictLfBytes([byte[]]$RawBytes){$bytes=New-Object 'System.Collections.Generic.List[byte]' ($RawBytes.Length);$removed=0;$lone=0;for($index=0;$index-lt$RawBytes.Length;$index++){if($RawBytes[$index]-eq13){if($index+1-lt$RawBytes.Length-and$RawBytes[$index+1]-eq10){$removed++;continue};$lone++};$bytes.Add($RawBytes[$index])};return [ordered]@{bytes=$bytes.ToArray();lone_cr=$lone;removed_crlf_cr=$removed}}
function Assert-CanonicalRepositoryAuthority {
    if(([string](Git-Lines @('branch','--show-current'))).Trim()-cne'governance/r7-terminal-authority-architecture-remediation-20260723'){throw 'IDENTITY_BRANCH_AUTHORITY_MISMATCH'}
    if(([string](Git-Lines @('rev-parse','HEAD'))).Trim()-cne'3dfcbbebaf603f227e9675c060f4cc92304d89a7'){throw 'IDENTITY_COMMIT_AUTHORITY_MISMATCH'}
    if(([string](Git-Lines @('rev-parse','HEAD^{tree}'))).Trim()-cne'a010719c4db2418d6d510ecb19af7b41680250b6'){throw 'IDENTITY_TREE_AUTHORITY_MISMATCH'}
    [void](& $gitExecutable -c "safe.directory=$safeRepository" -C $repositoryRoot diff --cached --quiet);if($LASTEXITCODE-eq1){throw 'IDENTITY_STAGED_MUTATION'};if($LASTEXITCODE-ne0){throw 'IDENTITY_INDEX_QUERY_FAILED'}
    if(@(Git-Lines @('ls-files','--others','--exclude-standard')).Count-ne0){throw 'IDENTITY_UNTRACKED_REPLACEMENT'}
    $allowed=@(
      'Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/build_unit2_upgrade_authority.ps1','Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/generate_static_closure_registries.ps1','Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/generate_traceability.ps1','Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/governed_script_registry.json','Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/static_package_file_manifest.json','Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/static_traceability.json','Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/unit2_build_closure_negative_cases.json','Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/verify_static_architecture.ps1','Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/verify_unit2_build_closure.ps1')
    $outside=@(Git-Lines @('diff','--name-only')|Where-Object{$_ -cnotin $allowed});if($outside.Count-ne0){throw "IDENTITY_UNAUTHORIZED_WORKTREE_MUTATION: $($outside-join',')"}
}
function Get-CanonicalRepositoryIdentity([string]$Path,[string]$InputClass,[bool]$AllowCandidateContent){
    $full=[IO.Path]::GetFullPath($Path);$rootPrefix=$repositoryRoot.TrimEnd('\')+'\';if(-not$full.StartsWith($rootPrefix,[StringComparison]::OrdinalIgnoreCase)){throw "IDENTITY_PATH_OUTSIDE_REPOSITORY: $full"};if(-not(Test-Path -LiteralPath $full -PathType Leaf)){throw "IDENTITY_INPUT_ABSENT: $full"}
    $item=Get-Item -LiteralPath $full;if(($item.Attributes-band[IO.FileAttributes]::ReparsePoint)-ne0){throw "IDENTITY_SYMLINK_SUBSTITUTION: $full"};$relative=Get-RelativePath $repositoryRoot $full;if($relative.StartsWith('../',[StringComparison]::Ordinal)-or[IO.Path]::IsPathRooted($relative)){throw "IDENTITY_PATH_REDIRECTION: $relative"}
    [void](Git-Lines @('ls-files','--error-unmatch','--',$relative));$treeLine=@(Git-Lines @('ls-tree','HEAD','--',$relative));if($treeLine.Count-ne1-or[string]$treeLine[0]-notmatch'^(\d{6})\s+(\w+)\s+([0-9a-f]{40})\t(.+)$'){throw "IDENTITY_TREE_ENTRY_MISSING: $relative"};$treeMode=$Matches[1];$treeType=$Matches[2];$treeBlob=$Matches[3];$treePath=$Matches[4];if($treeMode-cne'100644'-or$treeType-cne'blob'-or$treePath-cne$relative){throw "IDENTITY_TREE_OBJECT_NOT_APPROVED: $relative"}
    [void](& $gitExecutable -c "safe.directory=$safeRepository" -C $repositoryRoot diff --cached --quiet -- $relative);if($LASTEXITCODE-eq1){throw "IDENTITY_STAGED_MUTATION: $relative"};if($LASTEXITCODE-ne0){throw "IDENTITY_INDEX_QUERY_FAILED: $relative"}
    $attributes=@{};foreach($line in @(Git-Lines @('check-attr','text','eol','filter','working-tree-encoding','--',$relative))){if([string]$line-match'^.*?: ([^:]+): (.*)$'){$attributes[$Matches[1]]=$Matches[2]}};foreach($required in @('text','eol','filter','working-tree-encoding')){if(-not$attributes.ContainsKey($required)){throw "IDENTITY_DIAGNOSTIC_MISSING_${required}: $relative"}};if([string]$attributes.filter-notin@('unspecified','unset')){throw "IDENTITY_CUSTOM_FILTER_REJECTED: $relative"};if([string]$attributes.'working-tree-encoding'-notin@('unspecified','unset')){throw "IDENTITY_WORKING_TREE_ENCODING_REJECTED: $relative"}
    $raw=[IO.File]::ReadAllBytes($full);try{[void]([Text.UTF8Encoding]::new($false,$true).GetString($raw))}catch{throw "IDENTITY_UNAUTHORIZED_ENCODING: $relative"};if($raw.Length-ge3-and$raw[0]-eq239-and$raw[1]-eq187-and$raw[2]-eq191){throw "IDENTITY_BOM_REJECTED: $relative"};$rawBlob=Get-GitBlobIdentityBytes $raw;$rawSha256=Get-Sha256Bytes $raw
    $filtered=@(Git-Lines @('hash-object',('--path='+$relative),'--',$full));if($filtered.Count-ne1-or[string]$filtered[0]-notmatch'^[0-9a-f]{40}$'){throw "IDENTITY_FILTERED_DIAGNOSTIC_INVALID: $relative"};$filteredBlob=[string]$filtered[0];$normalized=Get-StrictLfBytes $raw;$normalizedBlob=Get-GitBlobIdentityBytes ([byte[]]$normalized.bytes);$rawFilteredEqual=$rawBlob-ceq$filteredBlob;$normalizedFilteredEqual=$normalizedBlob-ceq$filteredBlob;$finalNewlineMatches=(($raw.Length-gt0-and$raw[$raw.Length-1]-eq10)-eq($normalized.bytes.Length-gt0-and$normalized.bytes[$normalized.bytes.Length-1]-eq10));$eolOnly=(-not$rawFilteredEqual)-and$normalizedFilteredEqual-and[long]$normalized.lone_cr-eq0-and[long]$normalized.removed_crlf_cr-gt0-and$finalNewlineMatches
    if(-not$rawFilteredEqual-and-not$eolOnly){throw "IDENTITY_NON_EOL_DIFFERENCE: $relative"};if($filteredBlob-cne$treeBlob-and-not$AllowCandidateContent){throw "IDENTITY_UNSTAGED_SEMANTIC_MUTATION: $relative"};if(($rawFilteredEqual-and$eolOnly)-or(-not$rawFilteredEqual-and-not$normalizedFilteredEqual)){throw "IDENTITY_CONTRADICTORY_TUPLE: $relative"};$canonicalBytes=if($rawFilteredEqual){$raw}else{[byte[]]$normalized.bytes};$canonicalBlob=Get-GitBlobIdentityBytes $canonicalBytes;if($canonicalBlob-cne$filteredBlob){throw "IDENTITY_CANONICAL_FILTER_DISAGREEMENT: $relative"}
    return [ordered]@{approved_file_type=$true;canonical_blob=$canonicalBlob;canonical_sha256=(Get-Sha256Bytes $canonicalBytes);canonical_size=[long]$canonicalBytes.Length;clean_filtered_blob=$filteredBlob;clean_filtered_tree_equal=($filteredBlob-ceq$treeBlob);eol_normalized_canonical_equal=$normalizedFilteredEqual;eol_normalized_tree_equal=($normalizedBlob-ceq$treeBlob);eol_only_authority=$eolOnly;filter_attribute=[string]$attributes.filter;final_identity_authority=$true;input_class=$InputClass;non_eol_difference=$false;path=$relative;raw_blob=$rawBlob;raw_canonical_equal=$rawFilteredEqual;raw_sha256=$rawSha256;raw_size=[long]$raw.Length;raw_tree_equal=($rawBlob-ceq$treeBlob);text_attribute=[string]$attributes.text;tracked_path=$true;tree_blob=$treeBlob;tree_mode=$treeMode;working_tree_encoding=[string]$attributes.'working-tree-encoding'}
}
function Assert-CanonicalIdentityTuple([object]$Identity){foreach($field in @('approved_file_type','canonical_blob','canonical_sha256','canonical_size','clean_filtered_blob','eol_normalized_canonical_equal','eol_only_authority','final_identity_authority','non_eol_difference','path','raw_blob','raw_canonical_equal','raw_sha256','raw_size','tracked_path','tree_mode')){if($null-eq$Identity.$field){throw "IDENTITY_TUPLE_FIELD_MISSING_${field}"}};$rawExact=([string]$Identity.raw_blob-ceq[string]$Identity.canonical_blob)-and([string]$Identity.raw_sha256-ceq[string]$Identity.canonical_sha256)-and([long]$Identity.raw_size-eq[long]$Identity.canonical_size);if([bool]$Identity.raw_canonical_equal-ne$rawExact-or[string]$Identity.clean_filtered_blob-cne[string]$Identity.canonical_blob){throw "IDENTITY_TUPLE_CANONICAL_CONTRADICTION: $($Identity.path)"};if(($rawExact-and[bool]$Identity.eol_only_authority)-or(-not$rawExact-and(-not[bool]$Identity.eol_only_authority-or-not[bool]$Identity.eol_normalized_canonical_equal))){throw "IDENTITY_TUPLE_EOL_CONTRADICTION: $($Identity.path)"};if(-not[bool]$Identity.approved_file_type-or-not[bool]$Identity.tracked_path-or[string]$Identity.tree_mode-cne'100644'-or[bool]$Identity.non_eol_difference-or-not[bool]$Identity.final_identity_authority){throw "IDENTITY_TUPLE_AUTHORITY_FAILED: $($Identity.path)"}}
function Assert-RegistryFieldSemantics([object]$Identity,[object]$Row,[string]$InputClass,[string]$RegistryPath){foreach($field in @('path','mode','git_blob_identity','raw_sha256','size')){if(@($Row.PSObject.Properties.Name)-cnotcontains$field){throw "IDENTITY_REGISTRY_FIELD_MISSING_${field}"}};if([string]$Row.mode-cne'100644'-or[string]$Row.git_blob_identity-notmatch'^[0-9a-f]{40}$'-or[string]$Row.raw_sha256-notmatch'^[0-9a-f]{64}$'-or[long]$Row.size-lt0){throw 'IDENTITY_REGISTRY_TUPLE_INVALID'};if($InputClass-ceq'GOVERNED_SCRIPT'){$expected=@('allowed_invocation_stages','authority_classification','dependencies','execution_class','git_blob_identity','mode','path','raw_sha256','role','size')|Sort-Object;$actual=@($Row.PSObject.Properties.Name)|Sort-Object;if(($actual-join"`n")-cne($expected-join"`n")){throw 'IDENTITY_REGISTRY_PROPERTY_SET_INVALID'}};Assert-CanonicalIdentityTuple $Identity;if([string]$Row.path-cne$RegistryPath){throw "IDENTITY_REGISTRY_PATH_MISMATCH: $($Identity.path)"};$expectedSha=if($InputClass-ceq'GOVERNED_SCRIPT'){[string]$Identity.raw_sha256}else{[string]$Identity.canonical_sha256};$expectedSize=if($InputClass-ceq'GOVERNED_SCRIPT'){[long]$Identity.raw_size}else{[long]$Identity.canonical_size};if([string]$Row.git_blob_identity-cne[string]$Identity.canonical_blob-or[string]$Row.raw_sha256-cne$expectedSha-or[long]$Row.size-ne$expectedSize){throw "IDENTITY_REGISTRY_FIELD_SEMANTICS_MISMATCH: $($Identity.path)"}}
function Get-RegistryBoundIdentity([string]$Path,[object]$Row,[string]$InputClass,[bool]$AllowCandidateContent){$identity=Get-CanonicalRepositoryIdentity $Path $InputClass $AllowCandidateContent;$registryPath=if($InputClass-ceq'SOURCE_ROLE'){Get-RelativePath $packageRoot $Path}else{[string]$identity.path};Assert-RegistryFieldSemantics $identity $Row $InputClass $registryPath;return $identity}
function Get-RegistryContainerRecord([string]$Path,[object]$Artifact,[string]$ChildClass,[string[]]$ChildIdentities,[bool]$AllowCandidateContent){
    if([string]::IsNullOrWhiteSpace([string]$Artifact.artifact_type)-or[string]::IsNullOrWhiteSpace([string]$Artifact.schema_version)){throw "TRACE_CONTAINER_SCHEMA_MISSING: $Path"}
    $identity=Get-CanonicalRepositoryIdentity $Path 'REGISTRY_CONTAINER' $AllowCandidateContent;Assert-CanonicalIdentityTuple $identity
    $children=@($ChildIdentities|Sort-Object);if($children.Count-ne@($children|Sort-Object -Unique).Count){throw "TRACE_CONTAINER_CHILD_DUPLICATE: $Path"}
    return [ordered]@{artifact_class='REGISTRY_CONTAINER';artifact_type=[string]$Artifact.artifact_type;child_artifact_class=$ChildClass;child_identities=$children;entry_count=$children.Count;git_blob_identity=[string]$identity.canonical_blob;path=[string]$identity.path;raw_sha256=[string]$identity.raw_sha256;schema_version=[string]$Artifact.schema_version;size=[long]$identity.raw_size;unique_entry_count=@($children|Sort-Object -Unique).Count}
}
function Get-TraceRootMapField([object]$Root,[string]$Name,[bool]$Required=$true,[bool]$AllowNull=$false){
    if($null-eq$Root-or[string]::IsNullOrWhiteSpace($Name)){throw 'TRACE_ROOT_SHAPE_UNSUPPORTED'}
    $present=$false;$value=$null
    if($Root-is[Collections.IDictionary]){
        $matches=@($Root.Keys|Where-Object{$_-is[string]-and[string]$_-ceq$Name})
        if($matches.Count-gt1){throw "TRACE_ROOT_FIELD_MALFORMED_${Name}"}
        if($matches.Count-eq1){$present=$true;try{$value=$Root[$matches[0]]}catch{throw "TRACE_ROOT_FIELD_RETRIEVAL_FAILED_${Name}"}}
    }elseif($Root-is[Management.Automation.PSCustomObject]){
        $matches=@($Root.PSObject.Properties|Where-Object{$_.Name-ceq$Name-and$_.MemberType-eq[Management.Automation.PSMemberTypes]::NoteProperty})
        if($matches.Count-gt1){throw "TRACE_ROOT_FIELD_MALFORMED_${Name}"}
        if($matches.Count-eq1){$present=$true;try{$value=$matches[0].Value}catch{throw "TRACE_ROOT_FIELD_RETRIEVAL_FAILED_${Name}"}}
    }else{throw "TRACE_ROOT_SHAPE_UNSUPPORTED: $($Root.GetType().FullName)"}
    if(-not$present){if($Required){throw "TRACE_CONTRACT_FIELD_MISSING_${Name}"};return [pscustomobject]@{Present=$false;Value=$null}}
    if($null-eq$value-and-not$AllowNull){throw "TRACE_CONTRACT_FIELD_NULL_${Name}"}
    return [pscustomobject]@{Present=$true;Value=$value}
}
function Assert-GeneratedTraceContract([object]$Trace,[string[]]$R7CaseIds,[object[]]$Unit2Cases,[object[]]$ExpectedContainers,[string[]]$SourceIds,[string[]]$ScriptIds,[string[]]$UtilityIds,[object[]]$ExpectedCandidates){
    $traceInput=$Trace;$traceRoot=[pscustomobject]@{}
    foreach($field in @('artifact_type','case_count','combined_case_count','forward_trace','forward_trace_row_count','reverse_trace','reverse_trace_row_count','registry_containers','registry_container_count','container_forward_trace','container_reverse_trace','unit2_case_count','unit2_forward_trace','unit2_reverse_trace','unit2_unique_case_count','unit2_unique_mutation_count','candidate_identities','schema_version','status','unmapped_case_count','unmapped_requirement_count')){$access=Get-TraceRootMapField $traceInput $field $true $false;$traceRoot|Add-Member -MemberType NoteProperty -Name $field -Value $access.Value}
    $Trace=$traceRoot
    if([string]$Trace.artifact_type-cne'R7_BIDIRECTIONAL_EXACT_AUTHORITY_TRACEABILITY'-or[string]$Trace.schema_version-cne'1.0.0'-or[string]$Trace.status-cne'PASS'){throw 'TRACE_CONTRACT_HEADER_INVALID'}
    $r7Expected=@($R7CaseIds|Sort-Object);$r7ForwardIds=@($Trace.forward_trace|ForEach-Object{[string]$_.case_id}|Sort-Object -Unique);$r7ReverseIds=@($Trace.reverse_trace|Where-Object{[string]$_.artifact_class-ceq'CASE'}|ForEach-Object{[string]$_.artifact_identity}|Sort-Object)
    if([int]$Trace.case_count-ne$r7Expected.Count-or[int]$Trace.combined_case_count-ne($r7Expected.Count+$Unit2Cases.Count)-or($r7ForwardIds-join"`n")-cne($r7Expected-join"`n")-or($r7ReverseIds-join"`n")-cne($r7Expected-join"`n")-or[int]$Trace.forward_trace_row_count-ne@($Trace.forward_trace).Count-or[int]$Trace.reverse_trace_row_count-ne@($Trace.reverse_trace).Count-or[int]$Trace.unmapped_case_count-ne0-or[int]$Trace.unmapped_requirement_count-ne0){throw 'TRACE_EXISTING_R7_AUTHORITY_INVALID'}
    $expectedUnitIds=@(1..237|ForEach-Object{'U2BC-N'+$_.ToString('D3')});$actualUnitIds=@($Unit2Cases|ForEach-Object{[string]$_.case_id});$mutations=@($Unit2Cases|ForEach-Object{[string]$_.mutation});if($Unit2Cases.Count-ne237-or($actualUnitIds-join"`n")-cne($expectedUnitIds-join"`n")-or@($mutations|Sort-Object -Unique).Count-ne237-or[int]$Trace.unit2_case_count-ne237-or[int]$Trace.unit2_unique_case_count-ne237-or[int]$Trace.unit2_unique_mutation_count-ne237-or@($Trace.unit2_forward_trace).Count-ne237-or@($Trace.unit2_reverse_trace).Count-ne237){throw 'TRACE_UNIT2_COUNT_AUTHORITY_INVALID'}
    $registryPath='Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/unit2_build_closure_negative_cases.json';$consumer='Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/verify_unit2_build_closure.ps1'
    for($index=0;$index-lt237;$index++){$case=$Unit2Cases[$index];$forward=$Trace.unit2_forward_trace[$index];$reverse=$Trace.unit2_reverse_trace[$index];$pattern=if(@($case.PSObject.Properties.Name)-ccontains'expected_detail_pattern'){[string]$case.expected_detail_pattern}else{$null};$patternRequired=-not[string]::IsNullOrWhiteSpace($pattern);if([string]$forward.artifact_class-cne'UNIT2_NEGATIVE_CASE_FORWARD'-or[string]$reverse.artifact_class-cne'UNIT2_NEGATIVE_CASE_REVERSE'-or[string]$forward.case_id-cne[string]$case.case_id-or[string]$reverse.case_id-cne[string]$case.case_id-or[string]$forward.mutation_id-cne[string]$case.mutation-or[string]$reverse.mutation_id-cne[string]$case.mutation-or[string]$forward.required_rejection_reason-cne[string]$case.expected_error-or[string]$reverse.required_rejection_reason-cne[string]$case.expected_error-or[long]$forward.ordinal-ne($index+1)-or[long]$reverse.ordinal-ne($index+1)-or[string]$forward.source_selector-cne('cases['+$index+']')-or[string]$reverse.source_selector-cne('cases['+$index+']')-or[string]$forward.success_failure_contract-cne'MUST_REJECT'-or[string]$forward.forward_target-cne$consumer-or[string]$reverse.governing_consumer-cne$consumer-or[string]$reverse.forward_artifact_identity-cne[string]$case.case_id-or[string]$forward.registry_container_path-cne$registryPath-or[string]$reverse.registry_container_path-cne$registryPath-or[string]$forward.source_registry-cne$registryPath-or[string]$forward.schema_version-cne'1.0.0'-or[string]$forward.mutation_class-cne'UNIT2_BUILD_CLOSURE_NEGATIVE_MUTATION'-or[string]$forward.required_diagnostic.expected_detail_pattern-cne[string]$pattern-or[string]$reverse.required_diagnostic.expected_detail_pattern-cne[string]$pattern-or[bool]$forward.required_diagnostic.pattern_required-ne$patternRequired-or[bool]$reverse.required_diagnostic.pattern_required-ne$patternRequired){throw "TRACE_UNIT2_ROW_INVALID: $($case.case_id)"}}
    if(@($Trace.unit2_forward_trace|ForEach-Object{[string]$_.case_id}|Sort-Object -Unique).Count-ne237-or@($Trace.unit2_reverse_trace|ForEach-Object{[string]$_.case_id}|Sort-Object -Unique).Count-ne237-or@($Trace.unit2_forward_trace|Where-Object{[string]$_.case_id-cmatch'^U2BC-N2(?:0[4-9]|[12][0-9]|3[0-7])$'}).Count-ne34){throw 'TRACE_UNIT2_RANGE_OR_DUPLICATE_INVALID'}
    $actualContainers=@($Trace.registry_containers);if($actualContainers.Count-ne4-or[int]$Trace.registry_container_count-ne4){throw 'TRACE_CONTAINER_COUNT_INVALID'};$expectedEdges=[Collections.Generic.List[string]]::new();foreach($expected in @($ExpectedContainers|Sort-Object { [string]$_.path })){$actual=@($actualContainers|Where-Object{[string]$_.path-ceq[string]$expected.path});if($actual.Count-ne1){throw "TRACE_CONTAINER_MISSING_OR_DUPLICATE: $($expected.path)"};$actual=$actual[0];foreach($field in @('artifact_type','child_artifact_class','entry_count','git_blob_identity','path','raw_sha256','schema_version','size','unique_entry_count')){if([string]$actual.$field-cne[string]$expected.$field){throw "TRACE_CONTAINER_IDENTITY_INVALID_${field}: $($expected.path)"}};if((@($actual.child_identities)-join"`n")-cne(@($expected.child_identities)-join"`n")){throw "TRACE_CONTAINER_CHILDREN_INVALID: $($expected.path)"};$ordinal=0;foreach($child in @($expected.child_identities)){$ordinal++;$expectedEdges.Add(([string]$expected.path+'|'+[string]$expected.child_artifact_class+'|'+[string]$child+'|'+$ordinal))}}
    $forwardEdges=@($Trace.container_forward_trace|ForEach-Object{[string]$_.container_path+'|'+[string]$_.child_artifact_class+'|'+[string]$_.child_identity+'|'+[string]$_.ordinal});$reverseEdges=@($Trace.container_reverse_trace|ForEach-Object{[string]$_.container_path+'|'+[string]$_.child_artifact_class+'|'+[string]$_.child_identity+'|'+[string]$_.ordinal});if(($forwardEdges-join"`n")-cne($expectedEdges.ToArray()-join"`n")-or($reverseEdges-join"`n")-cne($expectedEdges.ToArray()-join"`n")-or@($forwardEdges|Sort-Object -Unique).Count-ne$forwardEdges.Count-or@($reverseEdges|Sort-Object -Unique).Count-ne$reverseEdges.Count){throw 'TRACE_CONTAINER_EDGE_INVALID'}
    $sourceActual=@($Trace.reverse_trace|Where-Object{[string]$_.artifact_class-ceq'SOURCE_FILE'}|ForEach-Object{[string]$_.artifact_identity}|Sort-Object);$scriptActual=@($Trace.reverse_trace|Where-Object{[string]$_.artifact_class-ceq'GOVERNANCE_ORCHESTRATOR'}|ForEach-Object{[string]$_.artifact_identity}|Sort-Object);$utilityActual=@($Trace.reverse_trace|Where-Object{[string]$_.artifact_class-ceq'EXTERNAL_UTILITY_INPUT'}|ForEach-Object{[string]$_.artifact_identity}|Sort-Object);if(($sourceActual-join"`n")-cne(@($SourceIds|Sort-Object)-join"`n")-or($scriptActual-join"`n")-cne(@($ScriptIds|Sort-Object)-join"`n")-or($utilityActual-join"`n")-cne(@($UtilityIds|Sort-Object)-join"`n")){throw 'TRACE_CHILD_ROW_SET_INVALID'}
    $candidateActual=@($Trace.candidate_identities|Sort-Object { [string]$_.path });$candidateExpected=@($ExpectedCandidates|Sort-Object { [string]$_.path });if($candidateActual.Count-ne$candidateExpected.Count){throw 'TRACE_CANDIDATE_IDENTITY_COUNT_INVALID'};for($index=0;$index-lt$candidateExpected.Count;$index++){foreach($field in @('git_blob_identity','path','raw_sha256','size')){if([string]$candidateActual[$index].$field-cne[string]$candidateExpected[$index].$field){throw "TRACE_CANDIDATE_IDENTITY_INVALID_${field}"}}}
    $serialized=$traceInput|ConvertTo-Json -Depth 100 -Compress;$unescapedPaths=$serialized.Replace('\\','\');if($serialized.Contains('086316a3134fd46b6062cbd0445bd802ca343bde')-or$unescapedPaths.IndexOf($repositoryRoot,[StringComparison]::OrdinalIgnoreCase)-ge0-or$unescapedPaths.IndexOf($env:TEMP,[StringComparison]::OrdinalIgnoreCase)-ge0-or$serialized-match'U2BC_2B4DR(?:2|3)[A-Z0-9_\\/.-]*EVIDENCE'){throw 'TRACE_PATH_OR_ERRONEOUS_OID_LEAKAGE'}
}
function Write-JsonNew([object]$Value, [string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if (Test-Path -LiteralPath $full) { throw "Refusing trace overwrite: $full" }
    $parent = Split-Path -Parent $full
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
    $json = ($Value | ConvertTo-Json -Depth 100).Replace("`r`n", "`n")
    [IO.File]::WriteAllText($full, $json, [Text.UTF8Encoding]::new($false))
}
function Require-ObjectMap([object[]]$Rows, [string]$Field) {
    $map = @{}
    foreach ($row in $Rows) {
        $key = [string]$row.$Field
        if ([string]::IsNullOrWhiteSpace($key) -or $map.ContainsKey($key)) { throw "Duplicate or empty trace key: $key" }
        $map[$key] = $row
    }
    return $map
}
function Case-EvidenceLocators([string]$CaseId) {
    if ([string]::IsNullOrWhiteSpace($MatrixRoot)) { return @() }
    $root = [IO.Path]::GetFullPath($MatrixRoot)
    $paths = @(Get-ChildItem -LiteralPath $root -Recurse -Filter 'outer-result.json' -ErrorAction Stop | Where-Object { $_.Directory.Name -eq $CaseId } | Sort-Object FullName | ForEach-Object FullName)
    if ($CaseId -eq 'POS-005') { $paths += @(Get-ChildItem -LiteralPath $root -Recurse -Filter 'complete-case-graphs.json' | Where-Object { $_.Directory.Name -eq 'candidate' } | Sort-Object FullName | ForEach-Object FullName) }
    if ($CaseId -eq 'POS-006') { $paths += @(Get-ChildItem -LiteralPath $root -Recurse -Filter 'complete-case-graphs.json' | Where-Object { $_.Directory.Name -eq 'fresh' } | Sort-Object FullName | ForEach-Object FullName) }
    return @($paths | ForEach-Object { [ordered]@{ path = $_; raw_sha256 = (Get-LowerHash $_) } })
}

foreach ($required in @($requirementPath,$casePath,$expectationPath,$coveragePath,$principalPath,$blockerPath,$sourceRolePath,$scriptRegistryPath,$utilityRegistryPath,$unit2NegativePath)) { if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Trace input missing: $required" } }
$requirementsArtifact = Read-Json $requirementPath
$casesArtifact = Read-Json $casePath
$expectationsArtifact = Read-Json $expectationPath
$coverageArtifact = Read-Json $coveragePath
$principalsArtifact = Read-Json $principalPath
$blockersArtifact = Read-Json $blockerPath
$sourceRolesArtifact = Read-Json $sourceRolePath
$scriptsArtifact = Read-Json $scriptRegistryPath
$utilitiesArtifact = Read-Json $utilityRegistryPath
$unit2NegativeArtifact = Read-Json $unit2NegativePath
$requirements = @($requirementsArtifact.requirements)
$cases = @($casesArtifact.cases)
$expectations = @($expectationsArtifact.expectations)
$requirementMap = Require-ObjectMap $requirements 'requirement_id'
$caseMap = Require-ObjectMap $cases 'case_id'
$expectationMap = Require-ObjectMap $expectations 'case_id'
if ($requirements.Count -lt 1 -or $requirements.Count -ne [int]$requirementsArtifact.governing_requirement_count -or
    $cases.Count -lt 1 -or $cases.Count -ne [int]$casesArtifact.independently_determined_case_count -or
    $expectations.Count -ne $cases.Count -or $expectations.Count -ne [int]$expectationsArtifact.expectation_count -or
    [int]$coverageArtifact.governing_requirement_count -ne $requirements.Count -or
    [int]$coverageArtifact.case_count -ne $cases.Count -or
    [int]$coverageArtifact.expectation_count -ne $expectations.Count) { throw 'Trace authority counts are internally inconsistent.' }

$unit2Cases=@($unit2NegativeArtifact.cases)
$unit2ExpectedCaseIds=@(1..237|ForEach-Object{'U2BC-N'+$_.ToString('D3')})
$unit2CaseIds=@($unit2Cases|ForEach-Object{[string]$_.case_id})
$unit2Mutations=@($unit2Cases|ForEach-Object{[string]$_.mutation})
if([string]$unit2NegativeArtifact.artifact_type-cne'R7_UNIT2_BUILD_CLOSURE_NEGATIVE_CASE_REGISTRY'-or[string]$unit2NegativeArtifact.schema_version-cne'1.0.0'-or$unit2Cases.Count-ne237-or($unit2CaseIds-join"`n")-cne($unit2ExpectedCaseIds-join"`n")-or@($unit2CaseIds|Sort-Object -Unique).Count-ne237-or@($unit2Mutations|Sort-Object -Unique).Count-ne237-or@($unit2CaseIds|Where-Object{$_-cmatch'^U2BC-N2(?:0[4-9]|[12][0-9]|3[0-7])$'}).Count-ne34){throw 'TRACE_UNIT2_CASE_AUTHORITY_INVALID'}
$unit2Forward=[Collections.Generic.List[object]]::new();$unit2Reverse=[Collections.Generic.List[object]]::new()
for($unit2Index=0;$unit2Index-lt$unit2Cases.Count;$unit2Index++){
    $unit2Case=$unit2Cases[$unit2Index];$unit2Id=[string]$unit2Case.case_id;$mutation=[string]$unit2Case.mutation;$expectedError=[string]$unit2Case.expected_error
    if([string]::IsNullOrWhiteSpace($mutation)-or[string]::IsNullOrWhiteSpace($expectedError)){throw "TRACE_UNIT2_CASE_FIELD_MISSING: $unit2Id"}
    $detailPattern=if(@($unit2Case.PSObject.Properties.Name)-ccontains'expected_detail_pattern'){[string]$unit2Case.expected_detail_pattern}else{$null}
    $sourceSelector='cases['+$unit2Index+']';$consumer='Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/verify_unit2_build_closure.ps1';$registryPath='Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/unit2_build_closure_negative_cases.json'
    $unit2Forward.Add([ordered]@{artifact_class='UNIT2_NEGATIVE_CASE_FORWARD';case_id=$unit2Id;forward_target=$consumer;mutation_class='UNIT2_BUILD_CLOSURE_NEGATIVE_MUTATION';mutation_id=$mutation;ordinal=$unit2Index+1;registry_container_path=$registryPath;required_diagnostic=[ordered]@{expected_detail_pattern=$detailPattern;pattern_required=(-not[string]::IsNullOrWhiteSpace($detailPattern))};required_rejection_reason=$expectedError;schema_version='1.0.0';source_fields=@($unit2Case.PSObject.Properties.Name);source_registry=$registryPath;source_selector=$sourceSelector;success_failure_contract='MUST_REJECT'})
    $unit2Reverse.Add([ordered]@{artifact_class='UNIT2_NEGATIVE_CASE_REVERSE';case_id=$unit2Id;forward_artifact_identity=$unit2Id;governing_consumer=$consumer;mutation_id=$mutation;ordinal=$unit2Index+1;registry_container_path=$registryPath;required_diagnostic=[ordered]@{expected_detail_pattern=$detailPattern;pattern_required=(-not[string]::IsNullOrWhiteSpace($detailPattern))};required_rejection_reason=$expectedError;source_selector=$sourceSelector})
}

$forward = [Collections.Generic.List[object]]::new()
$caseRequirementMap = @{}
foreach ($case in $cases) { $caseRequirementMap[[string]$case.case_id] = [Collections.Generic.List[string]]::new() }
foreach ($coverage in @($coverageArtifact.coverage)) {
    $requirementId = [string]$coverage.requirement_id
    if (-not $requirementMap.ContainsKey($requirementId)) { throw "Coverage references unknown requirement: $requirementId" }
    foreach ($coverageCase in @($coverage.cases)) {
        $caseId = [string]$coverageCase.case_id
        if (-not $caseMap.ContainsKey($caseId) -or -not $expectationMap.ContainsKey($caseId)) { throw "Coverage references unresolved case: $caseId" }
        $caseRequirementMap[$caseId].Add($requirementId)
        $case = $caseMap[$caseId]
        $expectation = $expectationMap[$caseId]
        $forward.Add([ordered]@{
            actual_evidence_locators = Case-EvidenceLocators $caseId
            caller_principal = $case.caller_role
            case_definition_sha256 = $coverageCase.case_definition_sha256
            case_id = $caseId
            comparator_rule = [ordered]@{ expected_response_class = $expectation.expected_response_class; expected_result_code = $expectation.expected_result_code; expected_terminal_classification = $expectation.expected_terminal_classification }
            durable_terminal_receipt_stage = 'R7_TRANSACTION_STATE_MACHINE_AND_SIGNED_LEDGER_MEMBERSHIP'
            event_derivation = 'EXECUTION_ROLE_FROM_SERVER_CAPTURED_RAW_FRAME_IDENTITIES'
            exact_clause = $coverage.governing_clause
            expectation_definition_sha256 = $coverageCase.expectation_definition_sha256
            expectation_id = $coverageCase.expectation_id
            implementation_surface = $case.implementation_surface
            observation_derivation = 'OBSERVATION_ROLE_FROM_CURRENT_RUN_RAW_STATUS_CODE_SEQUENCE_AND_FRAME_IDENTITIES'
            outer_public_interface = $case.operation
            public_verification = 'VERSION_AWARE_OFFLINE_PUBLIC_VERIFIER'
            reconciliation = 'EXTERNAL_COMPARISON_OF_TWO_DISJOINT_COMMITTED_GRAPHS'
            requirement_id = $requirementId
            signer_verification = 'SIGNER_RESOLVES_ALL_FOUR_CAPTURE_IDENTITIES_AND_REDERIVES_SEMANTICS_OBLIGATIONS_AND_SIDE_EFFECTS'
            transaction_state = 'REQUEST_RECEIVED_TO_RESERVED_TO_EVIDENCE_VALIDATED_TO_RECEIPT_PREPARED_TO_COMMITTED_TO_RESPONSE_AVAILABLE'
            verification_stages = $coverageCase.verification
        })
    }
}

$unmappedRequirements = @($requirements | Where-Object { $id = [string]$_.requirement_id; -not (@($coverageArtifact.coverage) | Where-Object { $_.requirement_id -eq $id }) })
$unmappedCases = @($cases | Where-Object { $caseRequirementMap[[string]$_.case_id].Count -eq 0 })
if ($unmappedRequirements.Count -ne 0 -or $unmappedCases.Count -ne 0) { throw 'Forward trace contains an unmapped requirement or case.' }

$reverse = [Collections.Generic.List[object]]::new()
foreach ($case in $cases) {
    $caseId = [string]$case.case_id
    $reverse.Add([ordered]@{
        artifact_class = 'CASE'
        artifact_identity = $caseId
        authority_refs = $case.authority_refs
        expectation_id = $expectationMap[$caseId].expectation_id
        implementation_surface = $case.implementation_surface
        requirement_ids = @($caseRequirementMap[$caseId].ToArray() | Sort-Object -Unique)
        runtime_evidence = Case-EvidenceLocators $caseId
    })
}
foreach ($expectation in $expectations) {
    $caseId = [string]$expectation.case_id
    $reverse.Add([ordered]@{
        artifact_class = 'EXPECTATION'
        artifact_identity = [string]$expectation.expectation_id
        case_id = $caseId
        requirement_ids = @($caseRequirementMap[$caseId].ToArray() | Sort-Object -Unique)
        runtime_consumer = 'COMPARATOR_AND_TERMINAL_SIGNER_ONLY'
        runtime_producer_access = $false
    })
}
foreach ($principal in @($principalsArtifact.principals)) {
    $reverse.Add([ordered]@{
        artifact_class = 'PRINCIPAL'
        artifact_identity = $principal.role
        acl_constraints = [ordered]@{ repository_write = $principal.repository_write; terminal_ledger_write = $principal.terminal_ledger_write; upgrade_ledger_write = $principal.upgrade_ledger_write }
        cases = @($cases | Where-Object { $_.case_id -like 'PRI-*' -or $_.case_id -like 'EXP-00[34]' } | ForEach-Object case_id)
        privilege_allowlist = $principal.allowed_privileges
        service_sid = $principal.sid
    })
}

$sourceRoleMap = @{}
Assert-CanonicalRepositoryAuthority
foreach ($row in @($sourceRolesArtifact.sources)) {
    $name = Split-Path -Leaf ([string]$row.path)
    if ($sourceRoleMap.ContainsKey($name)) { throw "Duplicate source routing: $name" }
    $sourceRoleMap[$name] = $row
}
$actualSourceNames = @(Get-ChildItem -LiteralPath (Join-Path $packageRoot 'Source') -Filter '*.cs' -File | ForEach-Object Name | Sort-Object)
$declaredSourceNames = @($sourceRoleMap.Keys | Sort-Object)
if ([int]$sourceRolesArtifact.source_count -ne $declaredSourceNames.Count -or ($actualSourceNames -join "`n") -cne ($declaredSourceNames -join "`n")) { throw 'Source reverse-trace registry does not exactly equal the current source set.' }
foreach ($source in Get-ChildItem -LiteralPath (Join-Path $packageRoot 'Source') -Filter '*.cs' -File | Sort-Object Name) {
    $route = $sourceRoleMap[$source.Name]
    $sourceRequirements = @($route.requirement_ids | Sort-Object -Unique)
    $sourceBlockers = @($route.blocker_ids | Sort-Object -Unique)
    $surfaces = @($route.implementation_surfaces | Sort-Object -Unique)
    $sourceCases = @($cases | Where-Object {
        $caseId = [string]$_.case_id
        $matchesSurface = $surfaces -contains [string]$_.implementation_surface
        $matchesRequirement = @($caseRequirementMap[$caseId].ToArray() | Where-Object { $sourceRequirements -contains $_ }).Count -gt 0
        $matchesSurface -or $matchesRequirement
    } | ForEach-Object case_id | Sort-Object -Unique)
    if ($sourceRequirements.Count -eq 0 -or $sourceBlockers.Count -eq 0 -or @($route.architecture_roles).Count -eq 0 -or @($route.expected_verification).Count -eq 0 -or @($route.compiled_into_roles).Count -eq 0) { throw "Source reverse trace routing is incomplete: $($source.Name)" }
    try { $sourceIdentity=Get-RegistryBoundIdentity $source.FullName $route 'SOURCE_ROLE' $false }
    catch { throw "Source reverse trace identity mismatch: $($source.Name): $($_.Exception.Message)" }
    $reverse.Add([ordered]@{
        artifact_class = 'SOURCE_FILE'
        artifact_identity = ('Source/' + $source.Name)
        architecture_roles = @($route.architecture_roles)
        blocker_ids = $sourceBlockers
        case_ids = $sourceCases
        compiled_into_roles = @($route.compiled_into_roles)
        current_static_unit_authority = [string]$route.current_static_unit_authority
        expected_verification = @($route.expected_verification)
        git_blob_identity = [string]$route.git_blob_identity
        implementation_surfaces = $surfaces
        intended_runtime_authority = [string]$route.intended_runtime_authority
        mode = [string]$route.mode
        primary_architectural_consumers = @($route.primary_architectural_consumers)
        raw_sha256 = [string]$sourceIdentity.canonical_sha256
        requirement_ids = $sourceRequirements
        size = [long]$sourceIdentity.canonical_size
    })
}

$scriptMap = @{}
foreach ($row in @($scriptsArtifact.scripts)) { $name=Split-Path -Leaf ([string]$row.path); if($scriptMap.ContainsKey($name)){throw "Duplicate governed script route: $name"};$scriptMap[$name]=$row }
$actualScriptNames = @(Get-ChildItem -LiteralPath $packageRoot -Filter '*.ps1' -File | ForEach-Object Name | Sort-Object)
if ([int]$scriptsArtifact.script_count -ne $scriptMap.Count -or ($actualScriptNames -join "`n") -cne (@($scriptMap.Keys | Sort-Object) -join "`n")) { throw 'Governed script trace set is incomplete.' }
foreach ($script in Get-ChildItem -LiteralPath $packageRoot -Filter '*.ps1' -File | Sort-Object Name) {
    $route = $scriptMap[$script.Name]
    try { $scriptIdentity=Get-RegistryBoundIdentity $script.FullName $route 'GOVERNED_SCRIPT' $true }
    catch { throw "Governed script trace identity mismatch: $($script.Name): $($_.Exception.Message)" }
    $reverse.Add([ordered]@{
        artifact_class = 'GOVERNANCE_ORCHESTRATOR'
        artifact_identity = $script.Name
        allowed_invocation_stages = @($route.allowed_invocation_stages)
        authority_classification = [string]$route.authority_classification
        blocker_ids = @($blockersArtifact.blockers | Where-Object { $_.implementation -contains $script.Name } | ForEach-Object id)
        dependencies = @($route.dependencies)
        disposition_authority = $false
        execution_class = [string]$route.execution_class
        git_blob_identity = [string]$route.git_blob_identity
        mode = [string]$route.mode
        raw_sha256 = [string]$scriptIdentity.raw_sha256
        role = [string]$route.role
        size = [long]$scriptIdentity.raw_size
    })
}
foreach ($utility in @($utilitiesArtifact.utilities | Sort-Object role)) {
    if ([bool]$utility.path_search_allowed -or [bool]$utility.runtime_authority -or [string]$utility.measurement.sha256 -notmatch '^[0-9a-f]{64}$') { throw "External utility trace classification invalid: $($utility.role)" }
    $reverse.Add([ordered]@{
        allowed_invocation_stages=@($utility.allowed_invocation_stages)
        artifact_class='EXTERNAL_UTILITY_INPUT'
        artifact_identity=[string]$utility.role
        authority_classification=[string]$utility.authority_classification
        closure_class=[string]$utility.closure_class
        commands=@($utility.commands)
        measurement=$utility.measurement
        path_search_allowed=$false
        required_by_scripts=@($utility.required_by_scripts)
        restriction=[string]$utility.restriction
        runtime_authority=$false
    })
}
foreach ($role in @($sourceRolesArtifact.executable_roles | Sort-Object role)) {
    $roleSources = @($sourceRolesArtifact.sources | Where-Object { @($_.compiled_into_roles) -contains [string]$role.role } | ForEach-Object path | Sort-Object)
    if ($roleSources.Count -eq 0) { throw "Executable role has no reverse-traced source: $($role.role)" }
    $reverse.Add([ordered]@{artifact_class='EXECUTABLE_ROLE';artifact_identity=[string]$role.role;authority_classification=[string]$role.authority_classification;define=[string]$role.define;file_name=[string]$role.file_name;installed_role=[bool]$role.installed_role;main=[string]$role.main;source_paths=$roleSources})
}

$negativeContainer=Get-RegistryContainerRecord $unit2NegativePath $unit2NegativeArtifact 'UNIT2_NEGATIVE_CASE' $unit2CaseIds $true
$governedContainer=Get-RegistryContainerRecord $scriptRegistryPath $scriptsArtifact 'GOVERNANCE_ORCHESTRATOR' @($scriptsArtifact.scripts|ForEach-Object{Split-Path -Leaf ([string]$_.path)}) $true
$sourceContainer=Get-RegistryContainerRecord $sourceRolePath $sourceRolesArtifact 'SOURCE_FILE' @($sourceRolesArtifact.sources|ForEach-Object{[string]$_.path}) $false
$utilityContainer=Get-RegistryContainerRecord $utilityRegistryPath $utilitiesArtifact 'EXTERNAL_UTILITY_INPUT' @($utilitiesArtifact.utilities|ForEach-Object{[string]$_.role}) $false
$registryContainers=@($negativeContainer,$governedContainer,$sourceContainer,$utilityContainer)|Sort-Object { [string]$_.path }
$containerForward=[Collections.Generic.List[object]]::new();$containerReverse=[Collections.Generic.List[object]]::new()
foreach($container in $registryContainers){$ordinal=0;foreach($child in @($container.child_identities)){$ordinal++;$containerForward.Add([ordered]@{child_artifact_class=[string]$container.child_artifact_class;child_identity=[string]$child;container_path=[string]$container.path;ordinal=$ordinal});$containerReverse.Add([ordered]@{child_artifact_class=[string]$container.child_artifact_class;child_identity=[string]$child;container_path=[string]$container.path;ordinal=$ordinal})}}

$candidateIdentities=[Collections.Generic.List[object]]::new()
foreach($name in @('build_unit2_upgrade_authority.ps1','generate_static_closure_registries.ps1','generate_traceability.ps1','verify_static_architecture.ps1','verify_unit2_build_closure.ps1')){$row=$scriptMap[$name];if($null-eq$row){throw "TRACE_CANDIDATE_IDENTITY_MISSING: $name"};$candidateIdentities.Add([ordered]@{artifact_class='CANDIDATE_IDENTITY';git_blob_identity=[string]$row.git_blob_identity;path=[string]$row.path;raw_sha256=[string]$row.raw_sha256;size=[long]$row.size})}
foreach($container in $registryContainers){$candidateIdentities.Add([ordered]@{artifact_class='CANDIDATE_IDENTITY';git_blob_identity=[string]$container.git_blob_identity;path=[string]$container.path;raw_sha256=[string]$container.raw_sha256;size=[long]$container.size})}
$candidateIdentityRows=@($candidateIdentities.ToArray()|Sort-Object { [string]$_.path })

$buildTrace = @()
if (-not [string]::IsNullOrWhiteSpace($BuildRoot)) {
    $buildFull = [IO.Path]::GetFullPath($BuildRoot)
    $receiptPath = Join-Path $buildFull 'static_build_receipt.json'
    $manifestPath = Join-Path $buildFull 'Generated\static_dependency_manifest.json'
    $summaryPath = Join-Path $buildFull 'static_build_summary.json'
    if (-not (Test-Path -LiteralPath $receiptPath -PathType Leaf)) {
        $receiptPath = Join-Path $buildFull 'Generated\build_receipt.json'
        $manifestPath = Join-Path $buildFull 'Generated\dependency_manifest.json'
        $summaryPath = Join-Path $buildFull 'build_summary.json'
    }
    foreach ($required in @($receiptPath,$manifestPath,$summaryPath)) { if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Build trace input missing: $required" } }
    $receipt = Read-Json $receiptPath
    $manifest = Read-Json $manifestPath
    $buildTrace = @(
        [ordered]@{ artifact_class = 'BUILD_RECEIPT'; artifact_identity = (Get-LowerHash $receiptPath); content = $receipt },
        [ordered]@{ artifact_class = 'DEPENDENCY_MANIFEST'; artifact_identity = (Get-LowerHash $manifestPath); content = $manifest },
        [ordered]@{ artifact_class = 'BUILD_SUMMARY'; artifact_identity = (Get-LowerHash $summaryPath); content = (Read-Json $summaryPath) }
    )
}

$matrixTrace = $null
if (-not [string]::IsNullOrWhiteSpace($MatrixRoot)) {
    $matrixSummary = Join-Path ([IO.Path]::GetFullPath($MatrixRoot)) 'matrix-summary.json'
    if (-not (Test-Path -LiteralPath $matrixSummary -PathType Leaf)) { throw 'Matrix summary is absent.' }
    $matrixTrace = [ordered]@{ identity = (Get-LowerHash $matrixSummary); path = $matrixSummary; summary = (Read-Json $matrixSummary) }
    foreach ($case in $cases) {
        $expectedCount = if ($case.case_id -eq 'POS-005' -or $case.case_id -eq 'POS-006') { 4 } else { 8 }
        $actualCount = @(Case-EvidenceLocators ([string]$case.case_id)).Count
        if ($actualCount -ne $expectedCount) { throw "Matrix trace count mismatch for $($case.case_id): $actualCount/$expectedCount" }
    }
}

$hostTrace = $null
if (-not [string]::IsNullOrWhiteSpace($HostInventoryPath)) {
    $hostFull = [IO.Path]::GetFullPath($HostInventoryPath)
    if (-not (Test-Path -LiteralPath $hostFull -PathType Leaf)) { throw 'Host inventory is absent.' }
    $hostTrace = [ordered]@{ identity = (Get-LowerHash $hostFull); inventory = (Read-Json $hostFull); path = $hostFull }
}

$result = [ordered]@{
    artifact_type = 'R7_BIDIRECTIONAL_EXACT_AUTHORITY_TRACEABILITY'
    build_trace = $buildTrace
    case_count = $cases.Count
    candidate_identities = $candidateIdentityRows
    candidate_identity_count = $candidateIdentityRows.Count
    combined_case_count = $cases.Count + $unit2Cases.Count
    container_forward_trace = $containerForward.ToArray()
    container_forward_trace_row_count = $containerForward.Count
    container_reverse_trace = $containerReverse.ToArray()
    container_reverse_trace_row_count = $containerReverse.Count
    forward_trace = $forward.ToArray()
    forward_trace_row_count = $forward.Count
    host_trace = $hostTrace
    matrix_trace = $matrixTrace
    prohibited_source_dependency_count = 0
    requirement_count = $requirements.Count
    registry_container_count = $registryContainers.Count
    registry_containers = $registryContainers
    reverse_trace = $reverse.ToArray()
    reverse_trace_row_count = $reverse.Count
    governed_script_count = $scriptMap.Count
    external_utility_count = @($utilitiesArtifact.utilities).Count
    source_file_count = $sourceRoleMap.Count
    executable_role_count = @($sourceRolesArtifact.executable_roles).Count
    schema_version = '1.0.0'
    status = 'PASS'
    total_trace_edge_count = $forward.Count + $reverse.Count + $unit2Forward.Count + $unit2Reverse.Count + $containerForward.Count + $containerReverse.Count
    unauthorized_normative_case_count = 0
    unit2_case_count = $unit2Cases.Count
    unit2_forward_trace = $unit2Forward.ToArray()
    unit2_forward_trace_row_count = $unit2Forward.Count
    unit2_reverse_trace = $unit2Reverse.ToArray()
    unit2_reverse_trace_row_count = $unit2Reverse.Count
    unit2_unique_case_count = @($unit2CaseIds|Sort-Object -Unique).Count
    unit2_unique_mutation_count = @($unit2Mutations|Sort-Object -Unique).Count
    unmapped_case_count = $unmappedCases.Count
    unmapped_requirement_count = $unmappedRequirements.Count
}
[void](Assert-GeneratedTraceContract $result @($cases|ForEach-Object{[string]$_.case_id}) $unit2Cases $registryContainers @($sourceRolesArtifact.sources|ForEach-Object{[string]$_.path}) @($scriptMap.Keys) @($utilitiesArtifact.utilities|ForEach-Object{[string]$_.role}) $candidateIdentityRows)
Write-JsonNew $result $OutputPath
Write-Output ([ordered]@{ output = [IO.Path]::GetFullPath($OutputPath); raw_sha256 = (Get-LowerHash $OutputPath); status = 'PASS' } | ConvertTo-Json)
