[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ArtifactTool,
    [switch]$GenerateGovernedScriptRegistry,
    [switch]$GenerateRegistries,
    [switch]$GeneratePackageManifest,
    [string]$ExternalMeasurementRoot,
    [switch]$ReplaceExisting
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$packageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $packageRoot '..\..\..'))
$packageRelativeRoot = 'Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT'
$artifactToolFull = [IO.Path]::GetFullPath($ArtifactTool)
$measurementRoot = if ([string]::IsNullOrWhiteSpace($ExternalMeasurementRoot)) { Join-Path $packageRoot ('Build\StaticRegistryMeasurements_' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmss')) } else { [IO.Path]::GetFullPath($ExternalMeasurementRoot) }
$canonicalWriteQueue = New-Object 'System.Collections.Generic.List[object]'

function Get-LowerHash([string]$Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function Get-RelativePath([string]$Base, [string]$Path) {
    $baseFull = [IO.Path]::GetFullPath($Base).TrimEnd('\') + '\'
    $pathFull = [IO.Path]::GetFullPath($Path)
    return [Uri]::UnescapeDataString(([Uri]$baseFull).MakeRelativeUri([Uri]$pathFull).ToString()).Replace('\','/')
}
function Get-GitBlobIdentity([string]$Path) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    $header = [Text.Encoding]::ASCII.GetBytes(('blob ' + $bytes.Length + [char]0))
    $all = New-Object byte[] ($header.Length + $bytes.Length)
    [Buffer]::BlockCopy($header,0,$all,0,$header.Length)
    [Buffer]::BlockCopy($bytes,0,$all,$header.Length,$bytes.Length)
    $sha = [Security.Cryptography.SHA1]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($all))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
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
function Invoke-GitText([string[]]$Arguments, [string]$FailureReason) {
    $safeRoot = $repositoryRoot.Replace('\','/')
    $output = @(& git.exe -c "safe.directory=$safeRoot" -C $repositoryRoot @Arguments)
    if ($LASTEXITCODE -ne 0) { throw $FailureReason }
    return @($output)
}
function Get-StrictLfBytes([byte[]]$RawBytes) {
    $bytes = New-Object 'System.Collections.Generic.List[byte]' ($RawBytes.Length)
    $removed = 0
    $lone = 0
    for ($index = 0; $index -lt $RawBytes.Length; $index++) {
        if ($RawBytes[$index] -eq 13) {
            if ($index + 1 -lt $RawBytes.Length -and $RawBytes[$index + 1] -eq 10) { $removed++; continue }
            $lone++
        }
        $bytes.Add($RawBytes[$index])
    }
    return [ordered]@{ bytes=$bytes.ToArray(); lone_cr=$lone; removed_crlf_cr=$removed }
}
function Get-CanonicalRepositoryIdentity([string]$Path, [string]$InputClass, [bool]$AllowCandidateContent) {
    $full = [IO.Path]::GetFullPath($Path)
    $rootPrefix = $repositoryRoot.TrimEnd('\') + '\'
    if (-not $full.StartsWith($rootPrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "IDENTITY_PATH_OUTSIDE_REPOSITORY: $full" }
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { throw "IDENTITY_INPUT_ABSENT: $full" }
    $relative = Get-RelativePath $repositoryRoot $full
    if ($relative.StartsWith('../',[StringComparison]::Ordinal) -or [IO.Path]::IsPathRooted($relative)) { throw "IDENTITY_PATH_REDIRECTION: $relative" }

    [void](Invoke-GitText @('ls-files','--error-unmatch','--',$relative) "IDENTITY_UNTRACKED_PATH: $relative")
    $treeLine = @(Invoke-GitText @('ls-tree','HEAD','--',$relative) "IDENTITY_TREE_LOOKUP_FAILED: $relative")
    if ($treeLine.Count -ne 1 -or [string]$treeLine[0] -notmatch '^(\d{6})\s+(\w+)\s+([0-9a-f]{40})\t(.+)$') { throw "IDENTITY_TREE_ENTRY_MISSING: $relative" }
    $treeMode = $Matches[1]; $treeType = $Matches[2]; $treeBlob = $Matches[3]; $treePath = $Matches[4]
    if ($treeMode -cne '100644' -or $treeType -cne 'blob' -or $treePath -cne $relative) { throw "IDENTITY_TREE_OBJECT_NOT_APPROVED: $relative" }

    [void](& git.exe -c "safe.directory=$($repositoryRoot.Replace('\','/'))" -C $repositoryRoot diff --cached --quiet -- $relative)
    if ($LASTEXITCODE -eq 1) { throw "IDENTITY_STAGED_MUTATION: $relative" }
    if ($LASTEXITCODE -ne 0) { throw "IDENTITY_INDEX_QUERY_FAILED: $relative" }

    $attributes = @{}
    foreach ($line in @(Invoke-GitText @('check-attr','text','eol','filter','working-tree-encoding','--',$relative) "IDENTITY_ATTRIBUTE_QUERY_FAILED: $relative")) {
        if ([string]$line -match '^.*?: ([^:]+): (.*)$') { $attributes[$Matches[1]] = $Matches[2] }
    }
    foreach ($required in @('text','eol','filter','working-tree-encoding')) { if (-not $attributes.ContainsKey($required)) { throw "IDENTITY_DIAGNOSTIC_MISSING_${required}: $relative" } }
    if ([string]$attributes.filter -notin @('unspecified','unset')) { throw "IDENTITY_CUSTOM_FILTER_REJECTED: $relative" }
    if ([string]$attributes.'working-tree-encoding' -notin @('unspecified','unset')) { throw "IDENTITY_WORKING_TREE_ENCODING_REJECTED: $relative" }

    $raw = [IO.File]::ReadAllBytes($full)
    try { [void]([Text.UTF8Encoding]::new($false,$true).GetString($raw)) }
    catch { throw "IDENTITY_UNAUTHORIZED_ENCODING: $relative" }
    $rawBom = $raw.Length -ge 3 -and $raw[0] -eq 239 -and $raw[1] -eq 187 -and $raw[2] -eq 191
    if ($rawBom) { throw "IDENTITY_BOM_REJECTED: $relative" }
    $rawBlob = Get-GitBlobIdentityBytes $raw
    $rawSha256 = Get-Sha256Bytes $raw
    $filtered = @(Invoke-GitText @('hash-object',("--path=" + $relative),'--',$full) "IDENTITY_CLEAN_FILTER_FAILED: $relative")
    if ($filtered.Count -ne 1 -or [string]$filtered[0] -notmatch '^[0-9a-f]{40}$') { throw "IDENTITY_FILTERED_DIAGNOSTIC_INVALID: $relative" }
    $filteredBlob = [string]$filtered[0]
    $normalized = Get-StrictLfBytes $raw
    $normalizedBlob = Get-GitBlobIdentityBytes ([byte[]]$normalized.bytes)
    $normalizedSha256 = Get-Sha256Bytes ([byte[]]$normalized.bytes)
    $rawTreeEqual = $rawBlob -ceq $treeBlob
    $filteredTreeEqual = $filteredBlob -ceq $treeBlob
    $normalizedFilteredEqual = $normalizedBlob -ceq $filteredBlob
    $rawFilteredEqual = $rawBlob -ceq $filteredBlob
    $finalNewlineMatches = (($raw.Length -gt 0 -and $raw[$raw.Length - 1] -eq 10) -eq ($normalized.bytes.Length -gt 0 -and $normalized.bytes[$normalized.bytes.Length - 1] -eq 10))
    $eolOnly = (-not $rawFilteredEqual) -and $normalizedFilteredEqual -and [long]$normalized.lone_cr -eq 0 -and [long]$normalized.removed_crlf_cr -gt 0 -and $finalNewlineMatches
    if (-not $rawFilteredEqual -and -not $eolOnly) { throw "IDENTITY_NON_EOL_DIFFERENCE: $relative" }
    if (-not $filteredTreeEqual -and -not $AllowCandidateContent) { throw "IDENTITY_UNSTAGED_SEMANTIC_MUTATION: $relative" }
    if (($rawFilteredEqual -and $eolOnly) -or (-not $rawFilteredEqual -and -not $normalizedFilteredEqual)) { throw "IDENTITY_CONTRADICTORY_TUPLE: $relative" }

    $canonicalBytes = if ($rawFilteredEqual) { $raw } else { [byte[]]$normalized.bytes }
    $canonicalBlob = Get-GitBlobIdentityBytes $canonicalBytes
    if ($canonicalBlob -cne $filteredBlob) { throw "IDENTITY_CANONICAL_FILTER_DISAGREEMENT: $relative" }
    return [ordered]@{
        approved_file_type=$true; canonical_blob=$canonicalBlob; canonical_sha256=(Get-Sha256Bytes $canonicalBytes); canonical_size=[long]$canonicalBytes.Length
        clean_filtered_blob=$filteredBlob; clean_filtered_tree_equal=$filteredTreeEqual; eol_normalized_canonical_equal=$normalizedFilteredEqual; eol_normalized_sha256=$normalizedSha256; eol_normalized_tree_equal=($normalizedBlob -ceq $treeBlob)
        eol_only_authority=$eolOnly; eol_attribute=[string]$attributes.eol; filter_attribute=[string]$attributes.filter; final_newline_matches=$finalNewlineMatches
        final_identity_authority=$true; input_class=$InputClass; non_eol_difference=$false; path=$relative; raw_blob=$rawBlob; raw_canonical_equal=$rawFilteredEqual; raw_sha256=$rawSha256; raw_size=[long]$raw.Length
        raw_tree_equal=$rawTreeEqual; text_attribute=[string]$attributes.text; tracked_path=$true; tree_blob=$treeBlob; tree_mode=$treeMode
        working_tree_encoding=[string]$attributes.'working-tree-encoding'
    }
}
function Assert-GovernedScriptRegistryTuple([object]$Identity,[object]$Row) {
    foreach ($field in @('approved_file_type','canonical_blob','canonical_sha256','canonical_size','clean_filtered_blob','eol_normalized_canonical_equal','eol_only_authority','final_identity_authority','non_eol_difference','path','raw_blob','raw_canonical_equal','raw_sha256','raw_size','tracked_path','tree_mode')) {
        if ($null -eq $Identity.$field) { throw "IDENTITY_TUPLE_FIELD_MISSING_${field}" }
    }
    $expectedFields=@('allowed_invocation_stages','authority_classification','dependencies','execution_class','git_blob_identity','mode','path','raw_sha256','role','size')|Sort-Object;$actualFields=@($Row.Keys)|Sort-Object
    if(($actualFields-join"`n")-cne($expectedFields-join"`n")){throw 'IDENTITY_REGISTRY_PROPERTY_SET_INVALID'}
    if([string]$Row.mode-cne'100644'-or[string]$Row.path-cne[string]$Identity.path-or[string]$Row.git_blob_identity-notmatch'^[0-9a-f]{40}$'-or[string]$Row.raw_sha256-notmatch'^[0-9a-f]{64}$'-or[long]$Row.size-lt0){throw 'IDENTITY_REGISTRY_TUPLE_INVALID'}
    $rawExact = ([string]$Identity.raw_blob -ceq [string]$Identity.canonical_blob) -and ([string]$Identity.raw_sha256 -ceq [string]$Identity.canonical_sha256) -and ([long]$Identity.raw_size -eq [long]$Identity.canonical_size)
    if ([bool]$Identity.raw_canonical_equal -ne $rawExact -or [string]$Identity.clean_filtered_blob -cne [string]$Identity.canonical_blob) { throw "IDENTITY_TUPLE_CANONICAL_CONTRADICTION: $($Identity.path)" }
    if (($rawExact -and [bool]$Identity.eol_only_authority) -or (-not $rawExact -and (-not [bool]$Identity.eol_only_authority -or -not [bool]$Identity.eol_normalized_canonical_equal))) { throw "IDENTITY_TUPLE_EOL_CONTRADICTION: $($Identity.path)" }
    if (-not [bool]$Identity.approved_file_type -or -not [bool]$Identity.tracked_path -or [string]$Identity.tree_mode -cne '100644' -or [bool]$Identity.non_eol_difference -or -not [bool]$Identity.final_identity_authority) { throw "IDENTITY_TUPLE_AUTHORITY_FAILED: $($Identity.path)" }
    if ([string]$Row.git_blob_identity -cne [string]$Identity.canonical_blob -or [string]$Row.raw_sha256 -cne [string]$Identity.raw_sha256 -or [long]$Row.size -ne [long]$Identity.raw_size) { throw "IDENTITY_REGISTRY_FIELD_SEMANTICS_MISMATCH: $($Identity.path)" }
}
function Assert-GovernedOutputScope([string[]]$Paths) {
    $allowed = @('governed_script_registry.json','source_role_registry.json','external_utility_registry.json','static_package_file_manifest.json')
    $seen = @{}
    foreach ($path in $Paths) {
        $full = [IO.Path]::GetFullPath($path)
        if (-not $full.StartsWith(($packageRoot.TrimEnd('\') + '\'),[StringComparison]::OrdinalIgnoreCase)) { throw "OUTPUT_SCOPE_ESCAPE: $full" }
        if ($allowed -notcontains [IO.Path]::GetFileName($full)) { throw "OUTPUT_SCOPE_UNAUTHORIZED: $full" }
        if ($seen.ContainsKey($full)) { throw "OUTPUT_SCOPE_DUPLICATE: $full" }
        $seen[$full] = $true
    }
}
function Write-CanonicalNew([object]$Value, [string]$Path, [string]$Label) {
    $full = [IO.Path]::GetFullPath($Path)
    if ((Test-Path -LiteralPath $full) -and -not $ReplaceExisting) { throw "$Label already exists: $full" }
    if (-not (Test-Path -LiteralPath $measurementRoot)) { New-Item -ItemType Directory -Path $measurementRoot | Out-Null }
    $raw = Join-Path $measurementRoot ($Label + '.raw.json')
    $canonical = Join-Path $measurementRoot ($Label + '.canonical.json')
    if ((Test-Path -LiteralPath $raw) -or (Test-Path -LiteralPath $canonical)) { throw "$Label measurement output already exists." }
    [IO.File]::WriteAllText($raw, ($Value | ConvertTo-Json -Depth 100), [Text.UTF8Encoding]::new($false))
    & $artifactToolFull canonicalize $raw $canonical | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $canonical -PathType Leaf)) { throw "Canonical registry generation failed: $Label" }
    $pending = Join-Path (Split-Path -Parent $full) ('.' + [IO.Path]::GetFileName($full) + '.pending.' + [Guid]::NewGuid().ToString('N'))
    $backup = Join-Path (Split-Path -Parent $full) ('.' + [IO.Path]::GetFileName($full) + '.backup.' + [Guid]::NewGuid().ToString('N'))
    try {
        [IO.File]::WriteAllBytes($pending,[IO.File]::ReadAllBytes($canonical))
        if (Test-Path -LiteralPath $full) { [IO.File]::Replace($pending,$full,$backup,$true) }
        else { [IO.File]::Move($pending,$full) }
    }
    finally {
        if (Test-Path -LiteralPath $pending) { Remove-Item -LiteralPath $pending -Force }
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
    }
    if (-not (Test-Path -LiteralPath $full -PathType Leaf) -or (Get-LowerHash $full) -cne (Get-LowerHash $canonical)) { throw "Canonical registry write failed: $Label" }
}
function Queue-CanonicalWrite([object]$Value, [string]$Path, [string]$Label) {
    $canonicalWriteQueue.Add([ordered]@{ label=$Label; path=[IO.Path]::GetFullPath($Path); value=$Value })
}
function New-ScriptDefinition([string]$Name,[string]$Role,[string[]]$Stages,[string]$ExecutionClass,[string[]]$Dependencies,[string]$AuthorityClass) {
    return [ordered]@{ authority_classification=$AuthorityClass; dependencies=$Dependencies; execution_class=$ExecutionClass; name=$Name; role=$Role; stages=$Stages }
}
function New-SourceDefinition([string]$Name,[string[]]$ArchitectureRoles,[string[]]$Blockers,[string[]]$Surfaces,[string[]]$Verification,[string]$IntendedAuthority,[string[]]$Consumers) {
    return [ordered]@{ architecture_roles=$ArchitectureRoles; blockers=$Blockers; consumers=$Consumers; implementation_surfaces=$Surfaces; intended_authority=$IntendedAuthority; name=$Name; verification=$Verification }
}
function New-UtilityDefinition([string]$Role,[string]$Path,[string[]]$Stages,[string[]]$Scripts,[string]$Restriction,[string]$Classification,[string]$ClosureClass,[string[]]$Commands) {
    return [ordered]@{ authority_classification=$Classification; closure_class=$ClosureClass; commands=$Commands; path=$Path; required_by_scripts=$Scripts; restriction=$Restriction; role=$Role; stages=$Stages }
}

if (-not $GenerateGovernedScriptRegistry -and -not $GenerateRegistries -and -not $GeneratePackageManifest) { throw 'Select GenerateGovernedScriptRegistry, GenerateRegistries, or GeneratePackageManifest.' }
if ($GenerateGovernedScriptRegistry -and ($GenerateRegistries -or $GeneratePackageManifest)) { throw 'GenerateGovernedScriptRegistry is an isolated mode and cannot be combined with another generation mode.' }
if (-not (Test-Path -LiteralPath $artifactToolFull -PathType Leaf)) { throw 'Artifact tool is absent.' }
$plannedOutputs = @()
if ($GenerateGovernedScriptRegistry) { $plannedOutputs += Join-Path $packageRoot 'governed_script_registry.json' }
if ($GenerateRegistries) { $plannedOutputs += @((Join-Path $packageRoot 'governed_script_registry.json'),(Join-Path $packageRoot 'external_utility_registry.json'),(Join-Path $packageRoot 'source_role_registry.json')) }
if ($GeneratePackageManifest) { $plannedOutputs += Join-Path $packageRoot 'static_package_file_manifest.json' }
Assert-GovernedOutputScope $plannedOutputs

if ($GenerateGovernedScriptRegistry -or $GenerateRegistries) {
    $scriptDefinitions = @(
        (New-ScriptDefinition 'author_cases.ps1' 'CASE_AUTHORING' @('PRECOMMIT_AUTHORITY_GENERATION') 'BUILD_TIME' @('POWERSHELL_ORCHESTRATOR') 'NONAUTHORITATIVE_GOVERNANCE_DERIVATION'),
        (New-ScriptDefinition 'author_expectations.ps1' 'EXPECTATION_AUTHORING' @('PRECOMMIT_AUTHORITY_GENERATION') 'BUILD_TIME' @('POWERSHELL_ORCHESTRATOR') 'NONAUTHORITATIVE_INDEPENDENT_EXPECTATION_DERIVATION'),
        (New-ScriptDefinition 'build_remediation_package.ps1' 'TERMINAL_TARGET_BUILD' @('UNIT2_TARGET_BUILD','FUTURE_POSTCOMMIT_BUILD') 'BUILD_TIME' @('POWERSHELL_ORCHESTRATOR','CSC_COMPILER','ILDASM_TOOL','GIT_BUILD_AND_VERIFICATION','ARTIFACT_TOOL_BUILD_OUTPUT') 'UNIT2_CONTENT_ADDRESSED_UNINSTALLED_TERMINAL_TARGET_BUILD'),
        (New-ScriptDefinition 'build_static_closure.ps1' 'STATIC_CLOSURE_BUILD' @('PRECOMMIT_STATIC_BUILD','DETACHED_POSTCOMMIT_STATIC_BUILD') 'BUILD_TIME' @('POWERSHELL_ORCHESTRATOR','CSC_COMPILER','ILDASM_TOOL','GIT_BUILD_AND_VERIFICATION','ARTIFACT_TOOL_BUILD_OUTPUT') 'NONAUTHORITATIVE_STATIC_COMPILE_EVIDENCE'),
        (New-ScriptDefinition 'build_unit2_upgrade_authority.ps1' 'UNIT2_UPGRADE_AUTHORITY_BUILD' @('UNIT2_POSTCOMMIT_BUILD') 'BUILD_TIME' @('POWERSHELL_ORCHESTRATOR','CSC_COMPILER','ILDASM_TOOL','GIT_BUILD_AND_VERIFICATION','ARTIFACT_TOOL_BUILD_OUTPUT') 'UNIT2_CONTENT_BOUND_BUILD_ORCHESTRATION'),
        (New-ScriptDefinition 'capture_remediation_host_state.ps1' 'HOST_STATE_CAPTURE' @('READ_ONLY_PREFLIGHT','FUTURE_POSTTRANSITION_CAPTURE') 'VERIFICATION_TIME' @('POWERSHELL_ORCHESTRATOR','GIT_BUILD_AND_VERIFICATION','SC_SERVICE_CONTROL_TOOL','POWERSHELL_MANAGEMENT_ASSEMBLY') 'READ_ONLY_EVIDENCE_CAPTURE_NO_AUTHORITY'),
        (New-ScriptDefinition 'complete_unit2_upgrade_authority.ps1' 'UNIT2B_STOPPED_BOUNDARY_INSTALLATION' @('UNIT2B_PRESTART_INSTALLATION_ONLY') 'INSTALLATION_TIME' @('POWERSHELL_ORCHESTRATOR','SC_SERVICE_CONTROL_TOOL','ICACLS_ACL_TOOL','POWERSHELL_MANAGEMENT_ASSEMBLY','ARTIFACT_TOOL_BUILD_OUTPUT') 'UNIT2B_LIMITED_STOPPED_SERVICE_FILESYSTEM_SCM_ACL_AND_ACCOUNT_RIGHT_MUTATION'),
        (New-ScriptDefinition 'extract_immutable_authority.ps1' 'IMMUTABLE_AUTHORITY_EXTRACTION' @('PRECOMMIT_AUTHORITY_GENERATION') 'BUILD_TIME' @('POWERSHELL_ORCHESTRATOR','GIT_BUILD_AND_VERIFICATION') 'NONAUTHORITATIVE_BYTE_EXTRACTION'),
        (New-ScriptDefinition 'generate_requirement_registry.ps1' 'REQUIREMENT_REGISTRY_GENERATION' @('PRECOMMIT_AUTHORITY_GENERATION') 'BUILD_TIME' @('POWERSHELL_ORCHESTRATOR') 'NONAUTHORITATIVE_DERIVATION_FROM_GOVERNING_BYTES'),
        (New-ScriptDefinition 'generate_static_closure_registries.ps1' 'STATIC_REGISTRY_GENERATION' @('PRECOMMIT_STATIC_CLOSURE') 'BUILD_TIME' @('POWERSHELL_ORCHESTRATOR','ARTIFACT_TOOL_BUILD_OUTPUT') 'NONAUTHORITATIVE_STATIC_MANIFEST_GENERATOR'),
        (New-ScriptDefinition 'generate_traceability.ps1' 'TRACEABILITY_GENERATION' @('PRECOMMIT_STATIC_VERIFICATION','FUTURE_POSTMATRIX_VERIFICATION') 'VERIFICATION_TIME' @('POWERSHELL_ORCHESTRATOR') 'NONAUTHORITATIVE_TRACE_EVIDENCE'),
        (New-ScriptDefinition 'install_authorized_transition.ps1' 'FUTURE_AUTHORIZED_INSTALLER' @('FUTURE_SEPARATELY_AUTHORIZED_HOST_TRANSITION') 'INSTALLATION_TIME' @('POWERSHELL_ORCHESTRATOR','SC_SERVICE_CONTROL_TOOL','ICACLS_ACL_TOOL','POWERSHELL_MANAGEMENT_ASSEMBLY','ARTIFACT_TOOL_BUILD_OUTPUT') 'FUTURE_HOST_MUTATION_PLAN_NOT_INVOKED_IN_STATIC_UNIT'),
        (New-ScriptDefinition 'provision_upgrade_authority.ps1' 'UNIT2_UPGRADE_BOOTSTRAP' @('UNIT2_POSTCOMMIT_PROVISIONING') 'INSTALLATION_TIME' @('POWERSHELL_ORCHESTRATOR','SC_SERVICE_CONTROL_TOOL','ICACLS_ACL_TOOL','TAKEOWN_CERTIFICATE_ACL_RECOVERY_TOOL','POWERSHELL_MANAGEMENT_ASSEMBLY','PKI_MODULE_MANIFEST') 'UNIT2_EXPLICITLY_AUTHORIZED_KEY_SERVICE_AND_ROOT_BOOTSTRAP'),
        (New-ScriptDefinition 'run_fresh_matrix.ps1' 'FUTURE_MATRIX_ORCHESTRATOR' @('FUTURE_POSTCOMMIT_POSTINSTALL_MATRIX') 'VERIFICATION_TIME' @('POWERSHELL_ORCHESTRATOR','GIT_BUILD_AND_VERIFICATION','ICACLS_ACL_TOOL','FSUTIL_PATH_FIXTURE_TOOL','POWERSHELL_MANAGEMENT_ASSEMBLY','POWERSHELL_JOB_ASSEMBLY','ARTIFACT_TOOL_BUILD_OUTPUT') 'NONAUTHORITATIVE_FUTURE_MATRIX_ORCHESTRATION_NOT_INVOKED_IN_STATIC_UNIT'),
        (New-ScriptDefinition 'scan_secrets_and_contamination.ps1' 'SECRET_AND_CONTAMINATION_SCAN' @('PRECOMMIT_STATIC_VERIFICATION','STAGED_DELTA_VERIFICATION','FUTURE_POSTMATRIX_VERIFICATION') 'VERIFICATION_TIME' @('POWERSHELL_ORCHESTRATOR','GIT_BUILD_AND_VERIFICATION','POWERSHELL_UTILITY_MODULE') 'NONAUTHORITATIVE_FAIL_CLOSED_VERIFICATION'),
        (New-ScriptDefinition 'verify_authority_coverage.ps1' 'AUTHORITY_COVERAGE_VERIFICATION' @('PRECOMMIT_STATIC_VERIFICATION','DETACHED_POSTCOMMIT_STATIC_VERIFICATION') 'VERIFICATION_TIME' @('POWERSHELL_ORCHESTRATOR') 'NONAUTHORITATIVE_FAIL_CLOSED_VERIFICATION'),
        (New-ScriptDefinition 'verify_failure_action_configuration.ps1' 'FAILURE_ACTION_CONFIGURATION_VERIFICATION' @('PRECOMMIT_STATIC_VERIFICATION','DETACHED_POSTCOMMIT_STATIC_VERIFICATION') 'VERIFICATION_TIME' @('POWERSHELL_ORCHESTRATOR','ARTIFACT_TOOL_BUILD_OUTPUT') 'NONAUTHORITATIVE_OFFLINE_NATIVE_STRUCTURE_REGRESSION'),
        (New-ScriptDefinition 'verify_unit2_install_map_evidence.ps1' 'UNIT2_INSTALL_MAP_EVIDENCE_VERIFICATION' @('PRECOMMIT_STATIC_VERIFICATION','DETACHED_POSTCOMMIT_STATIC_VERIFICATION') 'VERIFICATION_TIME' @('POWERSHELL_ORCHESTRATOR') 'NONAUTHORITATIVE_OFFLINE_INSTALL_MAP_AND_EVIDENCE_FIXTURE_REGRESSION'),
        (New-ScriptDefinition 'verify_static_architecture.ps1' 'STATIC_ARCHITECTURE_VERIFICATION' @('PRECOMMIT_STATIC_VERIFICATION','DETACHED_POSTCOMMIT_STATIC_VERIFICATION') 'VERIFICATION_TIME' @('POWERSHELL_ORCHESTRATOR','GIT_BUILD_AND_VERIFICATION','STATIC_VERIFIER_OFFLINE_BUILD_OUTPUT') 'NONAUTHORITATIVE_FAIL_CLOSED_VERIFICATION'),
        (New-ScriptDefinition 'verify_unit2_build_closure.ps1' 'UNIT2_BUILD_CLOSURE_VERIFICATION' @('UNIT2_PRECOMMIT_CANDIDATE_VERIFICATION','UNIT2_DETACHED_POSTCOMMIT_VERIFICATION') 'VERIFICATION_TIME' @('POWERSHELL_ORCHESTRATOR','GIT_BUILD_AND_VERIFICATION') 'NONAUTHORITATIVE_FAIL_CLOSED_BUILD_IDENTITY_VERIFICATION'),
        (New-ScriptDefinition 'verify_unit2_upgrade_authority.ps1' 'UNIT2_UPGRADE_AUTHORITY_VERIFICATION' @('UNIT2_POSTPROVISION_LIVE_VERIFICATION') 'VERIFICATION_TIME' @('POWERSHELL_ORCHESTRATOR','SC_SERVICE_CONTROL_TOOL','POWERSHELL_MANAGEMENT_ASSEMBLY','UNIT2_UPGRADE_CLIENT_BUILD_OUTPUT','UNIT2_UPGRADE_PUBLIC_VERIFIER_BUILD_OUTPUT','UNIT2_UPGRADE_PROTOCOL_PROBE_BUILD_OUTPUT') 'UNIT2_PUBLIC_AND_LIVE_BOUNDARY_VERIFICATION')
    )
    $actualScripts = @(Get-ChildItem -LiteralPath $packageRoot -Filter '*.ps1' -File | Sort-Object Name)
    $declaredScriptNames = @($scriptDefinitions | ForEach-Object name | Sort-Object)
    $actualScriptNames = @($actualScripts | ForEach-Object Name | Sort-Object)
    if (($declaredScriptNames -join "`n") -cne ($actualScriptNames -join "`n")) { throw 'Governed script definition set does not equal the package script set.' }
    $scriptRows = foreach ($definition in $scriptDefinitions | Sort-Object name) {
        $file = Get-Item -LiteralPath (Join-Path $packageRoot $definition.name)
        $identity = Get-CanonicalRepositoryIdentity $file.FullName 'GOVERNED_SCRIPT' $true
        $row = [ordered]@{
            allowed_invocation_stages = $definition.stages
            authority_classification = $definition.authority_classification
            dependencies = $definition.dependencies
            execution_class = $definition.execution_class
            git_blob_identity = [string]$identity.canonical_blob
            mode = '100644'
            path = ($packageRelativeRoot + '/' + $file.Name)
            raw_sha256 = [string]$identity.raw_sha256
            role = $definition.role
            size = [long]$identity.raw_size
        }
        Assert-GovernedScriptRegistryTuple $identity $row
        $row
    }
    $scriptArtifact = [ordered]@{ artifact_type='R7_GOVERNED_SCRIPT_REGISTRY'; authority_classification='NONAUTHORITATIVE_STATIC_PACKAGE_CLOSURE'; generated_from_current_bytes=$true; schema_version='1.0.0'; script_count=@($scriptRows).Count; scripts=@($scriptRows); status='STATIC_CLOSED_POSTCOMMIT_BLOB_VERIFICATION_REQUIRED' }
    Queue-CanonicalWrite $scriptArtifact (Join-Path $packageRoot 'governed_script_registry.json') 'governed-script-registry'
}

if ($GenerateRegistries) {
    $managementAssembly = 'C:\Windows\Microsoft.Net\assembly\GAC_MSIL\Microsoft.PowerShell.Commands.Management\v4.0_3.0.0.0__31bf3856ad364e35\Microsoft.PowerShell.Commands.Management.dll'
    $jobAssembly = 'C:\Windows\Microsoft.Net\assembly\GAC_MSIL\System.Management.Automation\v4.0_3.0.0.0__31bf3856ad364e35\System.Management.Automation.dll'
    $utilityModuleManifest = 'C:\Windows\System32\WindowsPowerShell\v1.0\Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1'
    $utilityModuleScript = 'C:\Windows\System32\WindowsPowerShell\v1.0\Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psm1'
    $utilityDefinitions = @(
        (New-UtilityDefinition 'GIT_BUILD_AND_VERIFICATION' 'C:\Program Files\Git\cmd\git.exe' @('BUILD_TIME','VERIFICATION_TIME','FUTURE_MATRIX') @('extract_immutable_authority.ps1','build_remediation_package.ps1','build_static_closure.ps1','build_unit2_upgrade_authority.ps1','capture_remediation_host_state.ps1','run_fresh_matrix.ps1','scan_secrets_and_contamination.ps1','verify_static_architecture.ps1','verify_unit2_build_closure.ps1') 'ABSOLUTE_PATH_ONLY; ENVIRONMENT_AND_CONFIG_CLOSED; PROHIBITED_FROM_RUNTIME_AUTHORITY' 'NONAUTHORITATIVE_BUILD_AND_VERIFICATION_TOOL' 'RECURSIVE_INSTALLATION_ROOT' @('cat-file','ls-tree','rev-parse','status','diff','clone','checkout')),
        (New-UtilityDefinition 'POWERSHELL_ORCHESTRATOR' 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' @('BUILD_TIME','VERIFICATION_TIME','UNIT2_INSTALLATION','UNIT2_VERIFICATION','FUTURE_INSTALLATION','FUTURE_MATRIX') @($actualScriptNames) 'ABSOLUTE_HOST_PATH; NONAUTHORITATIVE_ORCHESTRATOR; SCRIPT_BYTES_SEPARATELY_GOVERNED' 'NONAUTHORITATIVE_ORCHESTRATOR' 'RECURSIVE_POWERSHELL_ROOT' @('PowerShell-script-host')),
        (New-UtilityDefinition 'CSC_COMPILER' 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe' @('BUILD_TIME') @('build_remediation_package.ps1','build_static_closure.ps1','build_unit2_upgrade_authority.ps1') 'ABSOLUTE_PATH; FIXED OPTIONS; NO RESPONSE FILES; NO PATH SEARCH' 'NONAUTHORITATIVE_COMPILER_INPUT' 'RECURSIVE_FRAMEWORK_ROOT' @('compile-x64-net48')),
        (New-UtilityDefinition 'ILDASM_TOOL' 'C:\Program Files (x86)\Microsoft SDKs\Windows\v10.0A\bin\NETFX 4.8 Tools\x64\ildasm.exe' @('BUILD_TIME') @('build_remediation_package.ps1','build_static_closure.ps1','build_unit2_upgrade_authority.ps1') 'ABSOLUTE_PATH; NORMALIZED_IL_COMPARISON_ONLY' 'NONAUTHORITATIVE_BINARY_SEMANTIC_CHECK_TOOL' 'RECURSIVE_ILDASM_ROOT' @('normalized-il')),
        (New-UtilityDefinition 'SC_SERVICE_CONTROL_TOOL' 'C:\Windows\System32\sc.exe' @('READ_ONLY_PREFLIGHT','UNIT2_INSTALLATION','UNIT2_VERIFICATION','FUTURE_INSTALLATION') @('capture_remediation_host_state.ps1','complete_unit2_upgrade_authority.ps1','install_authorized_transition.ps1','provision_upgrade_authority.ps1','verify_unit2_upgrade_authority.ps1') 'ABSOLUTE PATH; UNIT2 USE LIMITED TO UPGRADE AUTHORITY; TERMINAL SERVICE MUTATION FORBIDDEN' 'UNIT2_GOVERNED_HOST_TRANSITION_UTILITY' 'FILE_MEASUREMENT_OS_TCB' @('qc','qsidtype','qprivs','upgrade-service-start-stop')),
        (New-UtilityDefinition 'ICACLS_ACL_TOOL' 'C:\Windows\System32\icacls.exe' @('UNIT2_INSTALLATION','FUTURE_INSTALLATION','FUTURE_MATRIX_FIXTURE') @('complete_unit2_upgrade_authority.ps1','install_authorized_transition.ps1','provision_upgrade_authority.ps1','run_fresh_matrix.ps1') 'ABSOLUTE PATH; UNIT2 DEDICATED ROOTS ONLY' 'UNIT2_GOVERNED_ACL_UTILITY' 'FILE_MEASUREMENT_OS_TCB' @('dedicated-root-acl-application')),
        (New-UtilityDefinition 'TAKEOWN_CERTIFICATE_ACL_RECOVERY_TOOL' 'C:\Windows\System32\takeown.exe' @('PRESERVED_UNIT2_BOOTSTRAP_RECOVERY_AT_22CE0E7') @('provision_upgrade_authority.ps1') 'ABSOLUTE PATH; HISTORICAL INVOCATION AT COMMIT 22CE0E7 WAS LIMITED TO THE EXACT PUBLIC CERTIFICATE FILE; CURRENT RESUME MUST VALIDATE ITS EFFECT AND MUST NOT REINVOKE' 'PRESERVED_UNIT2_GOVERNED_ONE_TIME_CERTIFICATE_ACL_RECOVERY_UTILITY' 'FILE_MEASUREMENT_OS_TCB' @('preserved-takeown-upgrade-public-certificate-only')),
        (New-UtilityDefinition 'FSUTIL_PATH_FIXTURE_TOOL' 'C:\Windows\System32\fsutil.exe' @('FUTURE_MATRIX_FIXTURE') @('run_fresh_matrix.ps1') 'ABSOLUTE_PATH; ISOLATED TEST ROOT ONLY; NOT INVOKED IN STATIC UNIT' 'FUTURE_NONAUTHORITY_FIXTURE_UTILITY_NOT_INVOKED' 'FILE_MEASUREMENT_OS_TCB' @('future-setshortname')),
        (New-UtilityDefinition 'RUNTIME_MACHINE_CONFIG' 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\Config\machine.config' @('BUILD_TIME','RUNTIME_INPUT') @('build_remediation_package.ps1','build_static_closure.ps1','build_unit2_upgrade_authority.ps1') 'CONTENT_BOUND_CONFIGURATION; NO ENVIRONMENT OVERRIDE' 'FRAMEWORK_CONFIGURATION_INPUT' 'RECURSIVE_FRAMEWORK_ROOT' @('clr-configuration')),
        (New-UtilityDefinition 'COMPILER_REFERENCE_mscorlib.dll' 'C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework\v4.8\mscorlib.dll' @('BUILD_TIME') @('build_remediation_package.ps1','build_static_closure.ps1','build_unit2_upgrade_authority.ps1') 'ABSOLUTE_REFERENCE; NOSTDLIB; EXPLICIT REFERENCE' 'COMPILER_REFERENCE_INPUT' 'RECURSIVE_REFERENCE_ROOT' @('compile-reference')),
        (New-UtilityDefinition 'COMPILER_REFERENCE_System.dll' 'C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework\v4.8\System.dll' @('BUILD_TIME') @('build_remediation_package.ps1','build_static_closure.ps1','build_unit2_upgrade_authority.ps1') 'ABSOLUTE_REFERENCE; NOSTDLIB; EXPLICIT REFERENCE' 'COMPILER_REFERENCE_INPUT' 'RECURSIVE_REFERENCE_ROOT' @('compile-reference')),
        (New-UtilityDefinition 'COMPILER_REFERENCE_System.Core.dll' 'C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework\v4.8\System.Core.dll' @('BUILD_TIME') @('build_remediation_package.ps1','build_static_closure.ps1','build_unit2_upgrade_authority.ps1') 'ABSOLUTE_REFERENCE; NOSTDLIB; EXPLICIT REFERENCE' 'COMPILER_REFERENCE_INPUT' 'RECURSIVE_REFERENCE_ROOT' @('compile-reference')),
        (New-UtilityDefinition 'COMPILER_REFERENCE_System.Security.dll' 'C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework\v4.8\System.Security.dll' @('BUILD_TIME') @('build_remediation_package.ps1','build_static_closure.ps1','build_unit2_upgrade_authority.ps1') 'ABSOLUTE_REFERENCE; NOSTDLIB; EXPLICIT REFERENCE' 'COMPILER_REFERENCE_INPUT' 'RECURSIVE_REFERENCE_ROOT' @('compile-reference')),
        (New-UtilityDefinition 'COMPILER_REFERENCE_System.ServiceProcess.dll' 'C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework\v4.8\System.ServiceProcess.dll' @('BUILD_TIME') @('build_remediation_package.ps1','build_static_closure.ps1','build_unit2_upgrade_authority.ps1') 'ABSOLUTE_REFERENCE; NOSTDLIB; EXPLICIT REFERENCE' 'COMPILER_REFERENCE_INPUT' 'RECURSIVE_REFERENCE_ROOT' @('compile-reference')),
        (New-UtilityDefinition 'POWERSHELL_MANAGEMENT_ASSEMBLY' $managementAssembly @('READ_ONLY_PREFLIGHT','UNIT2_INSTALLATION','UNIT2_VERIFICATION','FUTURE_INSTALLATION','FUTURE_MATRIX') @('capture_remediation_host_state.ps1','complete_unit2_upgrade_authority.ps1','install_authorized_transition.ps1','provision_upgrade_authority.ps1','run_fresh_matrix.ps1','verify_unit2_upgrade_authority.ps1') 'CMDLETS RESOLVE TO THIS MEASURED ASSEMBLY; UNIT2 MUTATION LIMITED TO UPGRADE AUTHORITY' 'POWERSHELL_CMDLET_PROVIDER_INPUT' 'FILE_MEASUREMENT_OS_TCB' @('Get-Service','Start-Service','Stop-Service','New-Item','Get-CimInstance','Start-Process','Move-Item')),
        (New-UtilityDefinition 'POWERSHELL_JOB_ASSEMBLY' $jobAssembly @('FUTURE_MATRIX_FIXTURE') @('run_fresh_matrix.ps1') 'START-JOB PROVIDER MEASURED; CHILD POWERSHELL CLOSURE REQUIRED; NOT INVOKED IN STATIC UNIT' 'FUTURE_NONAUTHORITY_MATRIX_JOB_PROVIDER' 'FILE_MEASUREMENT_OS_TCB' @('Start-Job')),
        (New-UtilityDefinition 'POWERSHELL_UTILITY_MODULE_MANIFEST' $utilityModuleManifest @('BUILD_TIME','VERIFICATION_TIME') @($actualScriptNames) 'MODULE MANIFEST CONTENT BOUND WITH POWERSHELL ROOT' 'POWERSHELL_MODULE_INPUT' 'RECURSIVE_POWERSHELL_ROOT' @('Get-FileHash','ConvertTo-Json')),
        (New-UtilityDefinition 'POWERSHELL_UTILITY_MODULE_SCRIPT' $utilityModuleScript @('BUILD_TIME','VERIFICATION_TIME') @($actualScriptNames) 'MODULE SCRIPT CONTENT BOUND WITH POWERSHELL ROOT' 'POWERSHELL_MODULE_INPUT' 'RECURSIVE_POWERSHELL_ROOT' @('Get-FileHash')),
        (New-UtilityDefinition 'PKI_MODULE_MANIFEST' 'C:\Windows\System32\WindowsPowerShell\v1.0\Modules\PKI\pki.psd1' @('UNIT2_UPGRADE_PROVISIONING') @('provision_upgrade_authority.ps1') 'EXPLICIT IMPORT BY ABSOLUTE MANIFEST; UNIT2 USE LIMITED TO NONEXPORTABLE UPGRADE KEY AND PUBLIC CERTIFICATE' 'UNIT2_KEY_PROVISIONING_MODULE' 'RECURSIVE_POWERSHELL_ROOT' @('New-SelfSignedCertificate','Export-Certificate')),
        (New-UtilityDefinition 'PKI_MODULE_TYPES' 'C:\Windows\System32\WindowsPowerShell\v1.0\Modules\PKI\pki.types.ps1xml' @('UNIT2_UPGRADE_PROVISIONING') @('provision_upgrade_authority.ps1') 'CONTENT BOUND PKI MODULE INPUT' 'UNIT2_KEY_PROVISIONING_MODULE_INPUT' 'RECURSIVE_POWERSHELL_ROOT' @('PKI-types'))
    )
    if (-not (Test-Path -LiteralPath $measurementRoot)) { New-Item -ItemType Directory -Path $measurementRoot | Out-Null }
    $utilityIndex = 0
    $utilityRows = foreach ($definition in $utilityDefinitions | Sort-Object role) {
        $full = [IO.Path]::GetFullPath($definition.path)
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { throw "External utility input missing: $full" }
        $measurementPath = Join-Path $measurementRoot ('u' + $utilityIndex.ToString('D2') + '.json')
        $utilityIndex++
        & $artifactToolFull measure $full $measurementPath | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "External utility measurement failed: $($definition.role)" }
        $identity = Get-CanonicalRepositoryIdentity $file.FullName 'SOURCE_ROLE' $false
        [ordered]@{
            allowed_invocation_stages = $definition.stages
            authority_classification = $definition.authority_classification
            closure_class = $definition.closure_class
            commands = $definition.commands
            measurement = (Get-Content -LiteralPath $measurementPath -Raw | ConvertFrom-Json)
            path = $full
            path_search_allowed = $false
            required_by_scripts = $definition.required_by_scripts
            restriction = $definition.restriction
            role = $definition.role
            runtime_authority = $false
        }
    }
    $utilityArtifact = [ordered]@{ artifact_type='R7_EXTERNAL_UTILITY_REGISTRY'; authority_classification='NONAUTHORITATIVE_STATIC_DEPENDENCY_CLOSURE'; schema_version='1.0.0'; status='STATIC_CONTENT_BOUND_HOST_SPECIFIC_POSTCOMMIT_REVALIDATION_REQUIRED'; utility_count=@($utilityRows).Count; utilities=@($utilityRows) }
    Queue-CanonicalWrite $utilityArtifact (Join-Path $packageRoot 'external_utility_registry.json') 'external-utility-registry'

    $targets = @(
        [ordered]@{authority_classification='UNIT2_UPGRADE_DISPOSITION_AUTHORITY_AFTER_PROVISIONING';define='UNIT2_SERVICE';file_name='RandleTerminalUpgradeAuthority.exe';installed_role=$true;main='RandleAI.R7Remediation.R7Unit2UpgradeServiceProgram';role='UNIT2_UPGRADE_AUTHORITY'},
        [ordered]@{authority_classification='UNIT2_NONAUTHORITATIVE_MEASURED_CLIENT';define='';file_name='RandleTerminalUpgradeClient.exe';installed_role=$true;main='RandleAI.R7Remediation.R7Unit2UpgradeClientProgram';role='UNIT2_UPGRADE_CLIENT'},
        [ordered]@{authority_classification='UNIT2_PUBLIC_ONLY_UPGRADE_VERIFIER';define='';file_name='RandleTerminalUpgradePublicVerifier.exe';installed_role=$true;main='RandleAI.R7Remediation.R7Unit2UpgradePublicVerifierProgram';role='UNIT2_UPGRADE_PUBLIC_VERIFIER'},
        [ordered]@{authority_classification='UNIT2_NONAUTHORITATIVE_PROTOCOL_ATTACK_DRIVER';define='';file_name='RandleTerminalUpgradeProtocolProbe.exe';installed_role=$true;main='RandleAI.R7Remediation.R7Unit2UpgradeProbeProgram';role='UNIT2_UPGRADE_PROTOCOL_PROBE'},
        [ordered]@{authority_classification='FUTURE_TERMINAL_SIGNER_BINARY';define='';file_name='RandleTerminalAuthority.exe';installed_role=$true;main='RandleAI.R7Remediation.R7TerminalServiceProgram';role='TERMINAL_SIGNER'},
        [ordered]@{authority_classification='NONAUTHORITATIVE_RAW_EXECUTION_PRODUCER';define='EXECUTION_ROLE';file_name='RandleTerminalExecution.exe';installed_role=$true;main='RandleAI.R7Remediation.R7ExecutionServiceProgram';role='EXECUTION'},
        [ordered]@{authority_classification='NONAUTHORITATIVE_RAW_OBSERVATION_PRODUCER';define='OBSERVATION_ROLE';file_name='RandleTerminalObservation.exe';installed_role=$true;main='RandleAI.R7Remediation.R7ObservationServiceProgram';role='OBSERVATION'},
        [ordered]@{authority_classification='NONAUTHORITATIVE_SEMANTIC_COMPARATOR';define='COMPARATOR_ROLE';file_name='RandleTerminalComparator.exe';installed_role=$true;main='RandleAI.R7Remediation.R7ComparatorServiceProgram';role='COMPARATOR'},
        [ordered]@{authority_classification='OFFLINE_PUBLIC_CLASSIFICATION_VERIFIER';define='';file_name='RandleTerminalPublicVerifier.exe';installed_role=$true;main='RandleAI.R7Remediation.R7PublicVerifierProgram';role='PUBLIC_VERIFIER'},
        [ordered]@{authority_classification='NONAUTHORITATIVE_AUTHORITY_PACKAGE_VERIFIER';define='';file_name='RandleTerminalAuthorityVerifier.exe';installed_role=$true;main='RandleAI.R7Remediation.R7AuthorityVerifierProgram';role='AUTHORITY_VERIFIER'},
        [ordered]@{authority_classification='NONAUTHORITATIVE_ADVERSARIAL_ORCHESTRATION_SUPPORT';define='';file_name='RandleTerminalAdversarialHarness.exe';installed_role=$true;main='RandleAI.R7Remediation.R7AdversarialHarnessProgram';role='ADVERSARIAL_HARNESS'},
        [ordered]@{authority_classification='NONAUTHORITATIVE_INSTALLED_STATIC_SUPPORT';define='INSTALLED_STATIC_ROLE';file_name='RandleTerminalStaticVerifier.exe';installed_role=$true;main='RandleAI.R7Remediation.R7StaticVerificationProgram';role='STATIC_VERIFIER_INSTALLED'},
        [ordered]@{authority_classification='NONAUTHORITATIVE_OFFLINE_STATIC_SUPPORT';define='';file_name='RandleTerminalStaticVerifier.Offline.exe';installed_role=$false;main='RandleAI.R7Remediation.R7StaticVerificationProgram';role='STATIC_VERIFIER_OFFLINE'},
        [ordered]@{authority_classification='NONAUTHORITATIVE_BUILD_AND_INSTALL_SUPPORT';define='';file_name='R7ArtifactTool.exe';installed_role=$false;main='RandleAI.R7Remediation.R7ArtifactToolProgram';role='ARTIFACT_TOOL'}
    )
    $allCompiledRoles = @($targets | ForEach-Object role)
    $sourceDefinitions = @(
        (New-SourceDefinition 'R7AdversarialHarness.cs' @('HOSTILE_OUTER_INTERFACE_DRIVER','MATRIX_ORCHESTRATION') @('R7AR-B03','R7AR-B16') @('TERMINAL_PIPE','PUBLIC_VERIFIER','UPGRADE_PIPE','OS_BOUNDARY','SAFE_FILE','DEPENDENCY_VERIFIER','RECOVERY_ENGINE') @('COMPILE','STATIC_TRACE','FUTURE_MATRIX') 'NONAUTHORITATIVE_SUPPORT' @('ADVERSARIAL_HARNESS')),
        (New-SourceDefinition 'R7ArtifactTool.cs' @('MEASUREMENT_TOOL','PROTECTED_METADATA_TOOL','BUILD_SUPPORT','INSTALL_SUPPORT','SCM_FAILURE_ACTION_COMMAND_SURFACE') @('R7AR-B05','R7AR-B07','R7AR-B11','R7AR-B12','R7AR-B15') @('SAFE_FILE','DEPENDENCY_VERIFIER','OS_BOUNDARY') @('COMPILE','UTILITY_MEASUREMENT','PROTECTED_KEY_METADATA_NO_READ','FAILURE_ACTION_REGRESSION','STATIC_TRACE') 'NONAUTHORITATIVE_SUPPORT' @('ARTIFACT_TOOL')),
        (New-SourceDefinition 'R7AuthorityArtifacts.cs' @('EXACT_AUTHORITY_RESOLUTION') @('R7AR-B01','R7AR-B14') @('AUTHORITY_REGISTRY') @('STATIC_AUTHORITY','STATIC_TRACE') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER','PUBLIC_VERIFIER','AUTHORITY_VERIFIER','EXECUTION','OBSERVATION','COMPARATOR')),
        (New-SourceDefinition 'R7AuthorityVerifier.cs' @('AUTHORITY_PACKAGE_VERIFIER') @('R7AR-B01','R7AR-B14') @('AUTHORITY_REGISTRY') @('STATIC_AUTHORITY','STATIC_TRACE') 'NONAUTHORITATIVE_SUPPORT' @('AUTHORITY_VERIFIER')),
        (New-SourceDefinition 'R7BuildClosureVerifier.cs' @('BUILD_AND_BINARY_CLOSURE_VERIFIER') @('R7AR-B07','R7AR-B12','R7AR-B15') @('DEPENDENCY_VERIFIER','SOURCE_AND_RUNTIME') @('STATIC_BUILD_RECEIPT','STATIC_TRACE') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER','UNIT2_UPGRADE_AUTHORITY','UNIT2_UPGRADE_PUBLIC_VERIFIER','PUBLIC_VERIFIER')),
        (New-SourceDefinition 'R7CoreJsonProtocol.cs' @('STRICT_FRAMING','CANONICAL_JSON') @('R7AR-B06') @('TERMINAL_PIPE') @('PARSER_22_CASES','COMPILE','STATIC_TRACE') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('ALL_EXECUTABLE_ROLES')),
        (New-SourceDefinition 'R7CryptoLedger.cs' @('CRYPTOGRAPHIC_LEDGER','DURABLE_FILE') @('R7AR-B08','R7AR-B09','R7AR-B10') @('TERMINAL_PIPE','RECOVERY_ENGINE','PUBLIC_VERIFIER','UPGRADE_PIPE') @('STATIC_TRANSACTION','STATIC_RECOVERY','STATIC_HISTORY','STATIC_TRACE','UNIT2_LEDGER') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER','UNIT2_UPGRADE_AUTHORITY','UNIT2_UPGRADE_PUBLIC_VERIFIER','PUBLIC_VERIFIER')),
        (New-SourceDefinition 'R7DependencyClosure.cs' @('RUNTIME_DEPENDENCY_CLOSURE') @('R7AR-B12','R7AR-B15') @('DEPENDENCY_VERIFIER','SOURCE_AND_RUNTIME') @('STATIC_DEPENDENCY_MANIFEST','COMPILE','STATIC_TRACE','FUTURE_RUNTIME_PROBE') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('ALL_INSTALLED_ROLES')),
        (New-SourceDefinition 'R7EvidenceStore.cs' @('RAW_INTERACTION_EVIDENCE_STORE') @('R7AR-B03','R7AR-B04') @('TERMINAL_PIPE') @('COMPILE','STATIC_TRACE','FUTURE_HOSTILE_GRAPH_ATTACKS') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER')),
        (New-SourceDefinition 'R7HistoricalClassification.cs' @('VERSIONED_HISTORY_CLASSIFICATION') @('R7AR-B08','R7AR-B13') @('PUBLIC_VERIFIER','RECOVERY_ENGINE') @('STATIC_HISTORY','STATIC_TRACE','FUTURE_APPEND_ONLY_CLASSIFICATION') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER','PUBLIC_VERIFIER')),
        (New-SourceDefinition 'R7MeasuredUtility.cs' @('HELD_MEASURED_UTILITY_INVOCATION') @('R7AR-B05','R7AR-B11','R7AR-B12','R7AR-B15') @('OS_BOUNDARY','SAFE_FILE','DEPENDENCY_VERIFIER') @('COMPILE','STATIC_UTILITY_REGISTRY','STATIC_TRACE','FUTURE_INSTALLATION_PROBE') 'NONAUTHORITATIVE_SUPPORT' @('ARTIFACT_TOOL')),
        (New-SourceDefinition 'R7Policy.cs' @('POLICY_AND_VERSION_BINDING') @('R7AR-B07','R7AR-B08','R7AR-B12') @('UPGRADE_PIPE','TERMINAL_PIPE','PUBLIC_VERIFIER') @('COMPILE','STATIC_TRACE','FUTURE_ACTIVATION') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER','UNIT2_UPGRADE_AUTHORITY','UNIT2_UPGRADE_PUBLIC_VERIFIER','PUBLIC_VERIFIER')),
        (New-SourceDefinition 'R7PublicVerifier.cs' @('VERSION_AWARE_OFFLINE_PUBLIC_VERIFICATION') @('R7AR-B07','R7AR-B08','R7AR-B13','R7AR-B16') @('PUBLIC_VERIFIER') @('STATIC_HISTORY','COMPILE','STATIC_TRACE','FUTURE_STOPPED_VERIFICATION') 'PUBLIC_CLASSIFICATION_DETERMINATIVE' @('PUBLIC_VERIFIER')),
        (New-SourceDefinition 'R7RecoveryProbeAuditor.cs' @('INDEPENDENT_RECOVERY_PROOF_REDERIVATION') @('R7AR-B04','R7AR-B10') @('RECOVERY_ENGINE','CLAIM_VERIFIER') @('STATIC_RECOVERY','COMPILE','STATIC_TRACE') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER')),
        (New-SourceDefinition 'R7RecoveryProbeEngine.cs' @('ISOLATED_RECOVERY_FAULT_ENGINE') @('R7AR-B10') @('RECOVERY_ENGINE') @('STATIC_RECOVERY','COMPILE','STATIC_TRACE','FUTURE_CRASH_MATRIX') 'NONAUTHORITATIVE_ISOLATED_TEST_SUPPORT' @('STATIC_VERIFIER_OFFLINE','EXECUTION')),
        (New-SourceDefinition 'R7RoleServices.cs' @('EXECUTION_PRODUCER','OBSERVATION_PRODUCER','SEMANTIC_COMPARATOR','NESTED_OUTER_SUBMISSION') @('R7AR-B02','R7AR-B03','R7AR-B05','R7AR-B16') @('TERMINAL_PIPE','OS_BOUNDARY','SEMANTIC_VERIFIER') @('COMPILE','STATIC_TRACE','FUTURE_OUTER_INTERFACE_MATRIX') 'NONAUTHORITATIVE_PRODUCERS_AND_COMPARATOR' @('EXECUTION','OBSERVATION','COMPARATOR')),
        (New-SourceDefinition 'R7SafeFile.cs' @('HELD_NO_FOLLOW_FILE_IDENTITY','PROTECTED_METADATA_WITHOUT_DATA_ACCESS') @('R7AR-B11','R7AR-B12') @('SAFE_FILE','DEPENDENCY_VERIFIER') @('COMPILE','PROTECTED_KEY_METADATA_NO_READ','STATIC_TRACE','FUTURE_PHYSICAL_ATTACKS') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('ALL_EXECUTABLE_ROLES')),
        (New-SourceDefinition 'R7ServiceBoundary.cs' @('LSA_ACCOUNT_RIGHTS','SCM_SERVICE_BOUNDARY') @('R7AR-B05','R7AR-B07') @('OS_BOUNDARY') @('COMPILE','STATIC_UTILITY_REGISTRY','STATIC_TRACE','FUTURE_SERVICE_BOUNDARY_PROBES') 'NONAUTHORITATIVE_FUTURE_INSTALLATION_SUPPORT' @('ARTIFACT_TOOL')),
        (New-SourceDefinition 'R7ServiceFailureActions.cs' @('SCM_FAILURE_ACTION_NATIVE_CONFIGURATION','SCM_FAILURE_ACTION_NATIVE_READBACK','SCM_FAILURE_ACTION_EXACT_ROLLBACK','FAILURE_ACTION_OFFLINE_REGRESSION') @('R7AR-B05','R7AR-B07','R7AR-B12','R7AR-B15') @('OS_BOUNDARY','DEPENDENCY_VERIFIER') @('COMPILE','FAILURE_ACTION_REGRESSION','STATIC_UTILITY_REGISTRY','STATIC_TRACE') 'NONAUTHORITATIVE_STOPPED_INSTALLATION_SUPPORT' @('ARTIFACT_TOOL')),
        (New-SourceDefinition 'R7ServiceInfrastructure.cs' @('NAMED_PIPE_SERVER','OS_CALLER_CAPTURE') @('R7AR-B05','R7AR-B06') @('TERMINAL_PIPE','OS_BOUNDARY') @('COMPILE','PARSER_22_CASES','STATIC_TRACE','UNIT2_LIVE_IPC','FUTURE_LIVE_IPC') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER','UNIT2_UPGRADE_AUTHORITY','EXECUTION','OBSERVATION','COMPARATOR')),
        (New-SourceDefinition 'R7StaticVerification.cs' @('OFFLINE_STATIC_TEST_DRIVER') @('R7AR-B01','R7AR-B06','R7AR-B08','R7AR-B09','R7AR-B10','R7AR-B14') @('AUTHORITY_REGISTRY','RECOVERY_ENGINE','TERMINAL_PIPE') @('PARSER_22_CASES','STATIC_AUTHORITY','STATIC_TRANSACTION','STATIC_RECOVERY','STATIC_HISTORY','STATIC_TRACE') 'NONAUTHORITATIVE_SUPPORT' @('STATIC_VERIFIER_OFFLINE','STATIC_VERIFIER_INSTALLED')),
        (New-SourceDefinition 'R7TerminalSignerService.cs' @('TERMINAL_SEMANTIC_AUTHORITY','NESTED_OUTER_GRAPH_REDERIVATION') @('R7AR-B02','R7AR-B03','R7AR-B04','R7AR-B05','R7AR-B08','R7AR-B09','R7AR-B13','R7AR-B14') @('TERMINAL_PIPE','CLAIM_VERIFIER','SEMANTIC_VERIFIER','TRACE_VERIFIER','PUBLIC_VERIFIER') @('COMPILE','STATIC_TRACE','FUTURE_HOSTILE_GRAPH_ATTACKS','FUTURE_MATRIX') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER')),
        (New-SourceDefinition 'R7Transaction.cs' @('APPEND_ONLY_TRANSACTION_STATE_MACHINE') @('R7AR-B09','R7AR-B10') @('TERMINAL_PIPE','RECOVERY_ENGINE') @('STATIC_TRANSACTION','STATIC_RECOVERY','COMPILE','STATIC_TRACE') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER','UNIT2_UPGRADE_AUTHORITY')),
        (New-SourceDefinition 'R7UpgradeAuthorityService.cs' @('SUPERSEDED_PRE_UNIT2_UPGRADE_PROPOSAL') @('R7AR-B07') @('UPGRADE_PIPE') @('COMPILE','STATIC_TRACE') 'NONAUTHORITATIVE_SUPERSEDED_SOURCE_NOT_SELECTED_AS_ENTRYPOINT' @('SOURCE_CLOSURE_ONLY')),
        (New-SourceDefinition 'R7UpgradeClient.cs' @('SUPERSEDED_PRE_UNIT2_UPGRADE_CLIENT') @('R7AR-B07') @('UPGRADE_PIPE') @('COMPILE','STATIC_TRACE') 'NONAUTHORITATIVE_SUPERSEDED_SOURCE_NOT_SELECTED_AS_ENTRYPOINT' @('SOURCE_CLOSURE_ONLY')),
        (New-SourceDefinition 'R7Unit2UpgradeAuthority.cs' @('UNIT2_NONCIRCULAR_UPGRADE_AUTHORITY','FIXED_TRANSITION_PAYLOAD','SIGNED_PROVISIONING_ATTESTATION','UPGRADE_LEDGER') @('R7AR-B05','R7AR-B06','R7AR-B07','R7AR-B09','R7AR-B10','R7AR-B11','R7AR-B12','R7AR-B15') @('UPGRADE_PIPE','OS_BOUNDARY','SAFE_FILE','DEPENDENCY_VERIFIER') @('COMPILE','UNIT2_LIVE_IPC','UNIT2_LEDGER','UNIT2_AUTHORIZATION') 'UPGRADE_DISPOSITION_DETERMINATIVE_AFTER_UNIT2_PROVISIONING' @('UNIT2_UPGRADE_AUTHORITY')),
        (New-SourceDefinition 'R7Unit2UpgradeClient.cs' @('UNIT2_NARROW_UPGRADE_CLIENT') @('R7AR-B06','R7AR-B07') @('UPGRADE_PIPE') @('COMPILE','UNIT2_AUTHORIZATION') 'NONAUTHORITATIVE_REQUEST_SUPPORT' @('UNIT2_UPGRADE_CLIENT')),
        (New-SourceDefinition 'R7Unit2UpgradeProbe.cs' @('UNIT2_STRICT_PROTOCOL_PROBE') @('R7AR-B06','R7AR-B07') @('UPGRADE_PIPE') @('COMPILE','UNIT2_LIVE_IPC') 'NONAUTHORITATIVE_ADVERSARIAL_VERIFICATION' @('UNIT2_UPGRADE_PROTOCOL_PROBE')),
        (New-SourceDefinition 'R7Unit2UpgradePublicVerifier.cs' @('UNIT2_PUBLIC_ONLY_VERIFIER','UNIT2_BOUNDARY_ENFORCER','UNIT2_KEY_DENIAL_PROBE') @('R7AR-B05','R7AR-B07','R7AR-B08','R7AR-B10') @('UPGRADE_PIPE','PUBLIC_VERIFIER','OS_BOUNDARY') @('COMPILE','UNIT2_PUBLIC_STOPPED_VERIFICATION','UNIT2_PRINCIPAL_ISOLATION') 'PUBLIC_UPGRADE_CLASSIFICATION_DETERMINATIVE' @('UNIT2_UPGRADE_PUBLIC_VERIFIER'))
    )
    $actualSources = @(Get-ChildItem -LiteralPath (Join-Path $packageRoot 'Source') -Filter '*.cs' -File | Sort-Object Name)
    if ((@($sourceDefinitions | ForEach-Object name | Sort-Object) -join "`n") -cne (@($actualSources | ForEach-Object Name | Sort-Object) -join "`n")) { throw 'Source routing definition set does not equal the current source set.' }
    $requirements = Get-Content -LiteralPath (Join-Path $packageRoot 'governed_requirement_registry.json') -Raw | ConvertFrom-Json
    $knownRequirements = @{}; foreach ($row in @($requirements.requirements)) { $knownRequirements[[string]$row.requirement_id] = $true }
    $sourceRows = foreach ($definition in $sourceDefinitions | Sort-Object name) {
        $file = Get-Item -LiteralPath (Join-Path $packageRoot ('Source\' + $definition.name))
        $identity = Get-CanonicalRepositoryIdentity $file.FullName 'SOURCE_ROLE' $false
        $requirementIds = @($definition.blockers | ForEach-Object { 'R7RM-AR-' + $_.Substring(5) } | Sort-Object -Unique)
        foreach ($id in $requirementIds) { if (-not $knownRequirements.ContainsKey($id)) { throw "Source routing requirement is absent: $id" } }
        [ordered]@{
            architecture_roles = $definition.architecture_roles
            blocker_ids = $definition.blockers
            compiled_into_roles = $allCompiledRoles
            current_static_unit_authority = 'NONAUTHORITATIVE_UNINSTALLED_SOURCE'
            expected_verification = $definition.verification
            git_blob_identity = [string]$identity.canonical_blob
            implementation_surfaces = $definition.implementation_surfaces
            intended_runtime_authority = $definition.intended_authority
            mode = '100644'
            path = ('Source/' + $file.Name)
            primary_architectural_consumers = $definition.consumers
            raw_sha256 = [string]$identity.canonical_sha256
            requirement_ids = $requirementIds
            size = [long]$identity.canonical_size
        }
    }
    $sourceArtifact = [ordered]@{ artifact_type='R7_SOURCE_ROLE_REGISTRY'; current_authority='NONAUTHORITATIVE_STATIC_PROPOSAL'; executable_role_count=$targets.Count; executable_roles=$targets; schema_version='1.0.0'; source_count=@($sourceRows).Count; sources=@($sourceRows); status='STATIC_CLOSED_POSTCOMMIT_BLOB_VERIFICATION_REQUIRED' }
    Queue-CanonicalWrite $sourceArtifact (Join-Path $packageRoot 'source_role_registry.json') 'source-role-registry'
}

if ($GeneratePackageManifest) {
    $manifestPath = Join-Path $packageRoot 'static_package_file_manifest.json'
    $excluded = @('static_package_file_manifest.json')
    $files = @(Get-ChildItem -LiteralPath $packageRoot -Recurse -File -Force | Where-Object { $_.FullName -notlike ((Join-Path $packageRoot 'Build') + '\*') -and $excluded -notcontains $_.Name } | Sort-Object FullName)
    $rows = foreach ($file in $files) {
        $identity = Get-CanonicalRepositoryIdentity $file.FullName 'STATIC_PACKAGE_MANIFEST' $true
        [ordered]@{ git_blob_identity=[string]$identity.canonical_blob; mode='100644'; path=(Get-RelativePath $repositoryRoot $file.FullName); raw_sha256=[string]$identity.canonical_sha256; size=[long]$identity.canonical_size }
    }
    $artifact = [ordered]@{ artifact_type='R7_STATIC_PACKAGE_FILE_MANIFEST'; authority_classification='NONAUTHORITATIVE_STATIC_STAGED_DELTA_MANIFEST'; excluded_self_path=($packageRelativeRoot + '/static_package_file_manifest.json'); file_count=@($rows).Count; files=@($rows); schema_version='1.0.0'; status='COMPLETE_EXCEPT_EXPLICIT_SELF_EXCLUSION' }
    Queue-CanonicalWrite $artifact $manifestPath 'static-package-file-manifest'
}

foreach ($write in $canonicalWriteQueue) { Write-CanonicalNew $write.value $write.path $write.label }

[ordered]@{ artifact_tool_sha256=(Get-LowerHash $artifactToolFull); generated_governed_script_registry=[bool]($GenerateGovernedScriptRegistry -or $GenerateRegistries); generated_package_manifest=[bool]$GeneratePackageManifest; generated_registries=[bool]$GenerateRegistries; measurement_root=$measurementRoot; status='PASS' } | ConvertTo-Json
