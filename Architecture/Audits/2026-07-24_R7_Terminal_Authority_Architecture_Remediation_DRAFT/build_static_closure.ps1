[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [ValidatePattern('^(?:[0-9a-f]{40}|PRECOMMIT)$')][string]$SourceCommit = 'PRECOMMIT'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$packageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $packageRoot '..\..\..'))
$packageRelativeRoot = 'Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT'
$output = [IO.Path]::GetFullPath($OutputRoot)
$compilerOptions = @('/nologo','/noconfig','/target:exe','/platform:x64','/optimize+','/checked+','/debug-','/warn:4','/nostdlib+','/langversion:5','/filealign:512')

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::Open([IO.Path]::GetFullPath($Path), [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
    finally { $algorithm.Dispose(); $stream.Dispose() }
}
function Get-BytesSha256([byte[]]$Bytes) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant() }
    finally { $algorithm.Dispose() }
}
function Get-TextSha256([string]$Value) { return Get-BytesSha256 ([Text.UTF8Encoding]::new($false).GetBytes($Value)) }
function Get-GitBlobIdentity([string]$Path) {
    $bytes = [IO.File]::ReadAllBytes([IO.Path]::GetFullPath($Path))
    $header = [Text.Encoding]::ASCII.GetBytes(('blob ' + $bytes.Length + [char]0))
    $all = New-Object byte[] ($header.Length + $bytes.Length)
    [Buffer]::BlockCopy($header, 0, $all, 0, $header.Length)
    [Buffer]::BlockCopy($bytes, 0, $all, $header.Length, $bytes.Length)
    $algorithm = [Security.Cryptography.SHA1]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($all))).Replace('-','').ToLowerInvariant() }
    finally { $algorithm.Dispose() }
}
function Get-RelativePath([string]$Base, [string]$Path) {
    $baseFull = [IO.Path]::GetFullPath($Base).TrimEnd('\') + '\'
    $pathFull = [IO.Path]::GetFullPath($Path)
    return [Uri]::UnescapeDataString(([Uri]$baseFull).MakeRelativeUri([Uri]$pathFull).ToString()).Replace('\','/')
}
function Assert-NewDirectory([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        if (@(Get-ChildItem -LiteralPath $Path -Force).Count -ne 0) { throw "Static build output root is not empty: $Path" }
    } else { New-Item -ItemType Directory -Path $Path | Out-Null }
}
function Read-Json([string]$Path) { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }
function Write-RawJson([object]$Value, [string]$Path) { [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 100), [Text.UTF8Encoding]::new($false)) }
function Write-CanonicalNew([object]$Value, [string]$Path, [string]$Tool) {
    if (Test-Path -LiteralPath $Path) { throw "Refusing static artifact overwrite: $Path" }
    $raw = $Path + '.raw'
    if (Test-Path -LiteralPath $raw) { throw "Refusing static raw artifact overwrite: $raw" }
    Write-RawJson $Value $raw
    & $Tool canonicalize $raw $Path | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Canonicalization failed: $Path" }
}
function Get-Utility([object]$Registry, [string]$Role) {
    $rows = @($Registry.utilities | Where-Object { [string]$_.role -ceq $Role })
    if ($rows.Count -ne 1) { throw "External utility role is not unique: $Role" }
    return $rows[0]
}
function Assert-UtilityContent([object]$Row) {
    $path = [IO.Path]::GetFullPath([string]$Row.path)
    if ([bool]$Row.path_search_allowed -or [bool]$Row.runtime_authority -or -not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "External utility policy invalid: $($Row.role)" }
    if ((Get-Sha256 $path) -cne [string]$Row.measurement.sha256 -or (Get-Item -LiteralPath $path).Length -ne [long]$Row.measurement.size) { throw "External utility content changed: $($Row.role)" }
}
function Invoke-Compiler([object]$Target, [string[]]$Sources, [string]$IdentitySource, [string]$Destination, [string]$Compiler, [string[]]$References) {
    $arguments = @($compilerOptions + ('/main:' + [string]$Target.main), ('/out:' + $Destination))
    if (-not [string]::IsNullOrEmpty([string]$Target.define)) { $arguments += ('/define:' + [string]$Target.define) }
    foreach ($reference in $References) { $arguments += ('/reference:' + $reference) }
    $arguments += $Sources
    $arguments += $IdentitySource
    & $Compiler @arguments
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Destination -PathType Leaf)) { throw "Compiler failed for $($Target.role)" }
}
function Get-NormalizedIl([string]$Binary, [string]$Destination, [string]$Ildasm) {
    $raw = $Destination + '.raw.il'
    & $Ildasm /text /nobar /utf8 ("/out=$raw") $Binary | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $raw -PathType Leaf)) { throw "IL disassembly failed: $Binary" }
    $text = [IO.File]::ReadAllText($raw)
    $mvid = [regex]::Match($text, '(?m)^// MVID: \{([0-9A-Fa-f-]+)\}\r?$')
    if (-not $mvid.Success) { throw "IL MVID was not found: $Binary" }
    $text = $text.Replace($mvid.Groups[1].Value, 'NORMALIZED-MVID')
    $text = [regex]::Replace($text, '(?m)^// Image base: 0x[0-9A-Fa-f]+\r?$', '// Image base: NORMALIZED')
    $text = [regex]::Replace($text, '(?m)^// WARNING: Created Win32 resource file .+\.raw\.res\r?$', '// WARNING: Created Win32 resource file NORMALIZED.raw.res')
    [IO.File]::WriteAllText($Destination, $text, [Text.UTF8Encoding]::new($false))
    return Get-Sha256 $Destination
}
function Get-RawDifference([string]$Left, [string]$Right) {
    $a = [IO.File]::ReadAllBytes($Left); $b = [IO.File]::ReadAllBytes($Right)
    $limit = [Math]::Min($a.Length, $b.Length); $offsets = [Collections.Generic.List[long]]::new(); $count = 0L
    for ($index = 0; $index -lt $limit; $index++) { if ($a[$index] -ne $b[$index]) { $count++; if ($offsets.Count -lt 128) { $offsets.Add($index) } } }
    $count += [Math]::Abs($a.Length - $b.Length)
    return [ordered]@{ differing_byte_count=$count; first_differing_offsets=$offsets.ToArray(); left_size=$a.Length; right_size=$b.Length; explanation='Raw PE identity is recorded but is not treated as reproducible; normalized IL must be byte-identical across separated compilations.' }
}
function Invoke-Git([string]$Git, [string[]]$Arguments) {
    $oldNoSystem = $env:GIT_CONFIG_NOSYSTEM; $oldGlobal = $env:GIT_CONFIG_GLOBAL; $oldSystem = $env:GIT_CONFIG_SYSTEM; $oldOptional = $env:GIT_OPTIONAL_LOCKS
    try {
        $env:GIT_CONFIG_NOSYSTEM='1'; $env:GIT_CONFIG_GLOBAL='NUL'; $env:GIT_CONFIG_SYSTEM='NUL'; $env:GIT_OPTIONAL_LOCKS='0'
        $result = @(& $Git --no-pager -c "safe.directory=$($repositoryRoot.Replace('\','/'))" -c core.autocrlf=false -c core.safecrlf=false -c core.fsmonitor=false -c core.hooksPath=NUL -C $repositoryRoot @Arguments)
        if ($LASTEXITCODE -ne 0) { throw "Governed Git failed: $($Arguments -join ' ')" }
        return $result
    } finally { $env:GIT_CONFIG_NOSYSTEM=$oldNoSystem; $env:GIT_CONFIG_GLOBAL=$oldGlobal; $env:GIT_CONFIG_SYSTEM=$oldSystem; $env:GIT_OPTIONAL_LOCKS=$oldOptional }
}
function Measure-Utility([object]$Row, [string]$Tool, [string]$MeasurementRoot, [string]$Phase) {
    $destination = Join-Path $MeasurementRoot (([string]$Row.role) + '.' + $Phase + '.json')
    & $Tool measure ([string]$Row.path) $destination | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Utility measurement failed: $($Row.role)" }
    $actual = Read-Json $destination
    foreach ($field in @('file_identity','hard_link_count','owner_sid','path','security_descriptor_sha256','sha256','size','volume_identity')) {
        if ([string]$actual.$field -cne [string]$Row.measurement.$field) { throw "Utility measurement changed for $($Row.role): $field" }
    }
    return [ordered]@{ measurement=$actual; measurement_raw_sha256=(Get-Sha256 $destination); phase=$Phase; role=[string]$Row.role }
}

if ($output.StartsWith($repositoryRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Static build output must be outside the repository checkout.' }
Assert-NewDirectory $output
foreach ($directory in @('Bootstrap','Closures','Generated','Measurements','NormalizedIL','PassA','PassB')) { New-Item -ItemType Directory -Path (Join-Path $output $directory) | Out-Null }

$scriptRegistryPath = Join-Path $packageRoot 'governed_script_registry.json'
$utilityRegistryPath = Join-Path $packageRoot 'external_utility_registry.json'
$sourceRegistryPath = Join-Path $packageRoot 'source_role_registry.json'
foreach ($required in @($scriptRegistryPath,$utilityRegistryPath,$sourceRegistryPath)) { if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Static closure registry missing: $required" } }
$scriptRegistry = Read-Json $scriptRegistryPath
$utilityRegistry = Read-Json $utilityRegistryPath
$sourceRegistry = Read-Json $sourceRegistryPath

$actualScripts = @(Get-ChildItem -LiteralPath $packageRoot -Filter '*.ps1' -File | Sort-Object Name)
$declaredScripts = @($scriptRegistry.scripts | Sort-Object path)
if ([int]$scriptRegistry.script_count -ne $declaredScripts.Count -or $declaredScripts.Count -ne $actualScripts.Count) { throw 'Governed script count mismatch.' }
$declaredScriptNames = @($declaredScripts | ForEach-Object { Split-Path -Leaf ([string]$_.path) } | Sort-Object)
$actualScriptNames = @($actualScripts | ForEach-Object Name | Sort-Object)
if (($declaredScriptNames -join "`n") -cne ($actualScriptNames -join "`n")) { throw 'Governed script set mismatch.' }
foreach ($row in $declaredScripts) {
    $path = Join-Path $repositoryRoot ([string]$row.path).Replace('/','\')
    if ([string]$row.mode -cne '100644' -or (Get-Sha256 $path) -cne [string]$row.raw_sha256 -or (Get-GitBlobIdentity $path) -cne [string]$row.git_blob_identity -or (Get-Item -LiteralPath $path).Length -ne [long]$row.size) { throw "Governed script identity mismatch: $($row.path)" }
    if (@($row.allowed_invocation_stages).Count -eq 0 -or @($row.dependencies).Count -eq 0 -or [string]::IsNullOrWhiteSpace([string]$row.role) -or [string]::IsNullOrWhiteSpace([string]$row.execution_class) -or [string]::IsNullOrWhiteSpace([string]$row.authority_classification)) { throw "Governed script classification incomplete: $($row.path)" }
}

$actualSources = @(Get-ChildItem -LiteralPath (Join-Path $packageRoot 'Source') -Filter '*.cs' -File | Sort-Object Name)
$declaredSources = @($sourceRegistry.sources | Sort-Object path)
if ([int]$sourceRegistry.source_count -ne $declaredSources.Count -or $declaredSources.Count -ne $actualSources.Count) { throw 'Source-role registry count mismatch.' }
$declaredSourceNames = @($declaredSources | ForEach-Object { Split-Path -Leaf ([string]$_.path) } | Sort-Object)
$actualSourceNames = @($actualSources | ForEach-Object Name | Sort-Object)
if (($declaredSourceNames -join "`n") -cne ($actualSourceNames -join "`n")) { throw 'Source-role registry set mismatch.' }
foreach ($row in $declaredSources) {
    $path = Join-Path $packageRoot ([string]$row.path).Replace('/','\')
    if ([string]$row.mode -cne '100644' -or (Get-Sha256 $path) -cne [string]$row.raw_sha256 -or (Get-GitBlobIdentity $path) -cne [string]$row.git_blob_identity -or (Get-Item -LiteralPath $path).Length -ne [long]$row.size) { throw "Source-role identity mismatch: $($row.path)" }
    if (@($row.requirement_ids).Count -eq 0 -or @($row.blocker_ids).Count -eq 0 -or @($row.expected_verification).Count -eq 0 -or @($row.compiled_into_roles).Count -eq 0) { throw "Source reverse trace incomplete: $($row.path)" }
}

if ([int]$utilityRegistry.utility_count -ne @($utilityRegistry.utilities).Count) { throw 'External utility count mismatch.' }
foreach ($row in @($utilityRegistry.utilities)) { Assert-UtilityContent $row }
$compilerRow = Get-Utility $utilityRegistry 'CSC_COMPILER'
$ildasmRow = Get-Utility $utilityRegistry 'ILDASM_TOOL'
$gitRow = Get-Utility $utilityRegistry 'GIT_BUILD_AND_VERIFICATION'
$powershellRow = Get-Utility $utilityRegistry 'POWERSHELL_ORCHESTRATOR'
$referenceRoles = @('COMPILER_REFERENCE_mscorlib.dll','COMPILER_REFERENCE_System.dll','COMPILER_REFERENCE_System.Core.dll','COMPILER_REFERENCE_System.Security.dll','COMPILER_REFERENCE_System.ServiceProcess.dll')
$references = @($referenceRoles | ForEach-Object { [string](Get-Utility $utilityRegistry $_).path })
$compiler = [string]$compilerRow.path; $ildasm = [string]$ildasmRow.path; $git = [string]$gitRow.path
if (-not [string]::Equals([IO.Path]::GetFullPath((Get-Process -Id $PID).Path), [IO.Path]::GetFullPath([string]$powershellRow.path), [StringComparison]::OrdinalIgnoreCase)) { throw 'Static build is not running under the governed PowerShell executable.' }

$sourceTree = ''
$sourceIdentityClass = 'WORKTREE_CONTENT_DERIVATION_STATIC_NONAUTHORITY'
$commitBlobMap = @{}
if ($SourceCommit -cne 'PRECOMMIT') {
    $head = ([string](Invoke-Git $git @('rev-parse','HEAD'))).Trim()
    if ($head -cne $SourceCommit) { throw "Static build HEAD does not match SourceCommit: $head" }
    if (@(Invoke-Git $git @('status','--porcelain=v1','--untracked-files=all')).Count -ne 0) { throw 'Postcommit static build checkout must be clean.' }
    $sourceTree = ([string](Invoke-Git $git @('show','-s','--format=%T',$SourceCommit))).Trim()
    foreach ($line in @(Invoke-Git $git @('ls-tree','-r',$SourceCommit,'--',$packageRelativeRoot))) {
        if ([string]$line -match '^(100644|100755) blob ([0-9a-f]{40})\t(.+)$') { $commitBlobMap[$Matches[3]] = [ordered]@{blob=$Matches[2];mode=$Matches[1]} }
    }
    foreach ($row in @($declaredScripts + $declaredSources)) {
        $relative = if ([string]$row.path -like 'Source/*') { $packageRelativeRoot + '/' + [string]$row.path } else { [string]$row.path }
        if (-not $commitBlobMap.ContainsKey($relative) -or [string]$commitBlobMap[$relative].blob -cne [string]$row.git_blob_identity -or [string]$commitBlobMap[$relative].mode -cne [string]$row.mode) { throw "Committed blob binding mismatch: $relative" }
    }
    $sourceIdentityClass = 'EXACT_COMMIT_AND_TREE_STATIC_NONAUTHORITY'
}
$contractPath = Join-Path $packageRoot 'BuildInputs\R7BuildIdentityContract.cs'
if (-not (Test-Path -LiteralPath $contractPath -PathType Leaf)) { throw 'Build-identity generation contract is absent.' }
$sourcePaths = @($actualSources | ForEach-Object FullName) + $contractPath
if ($SourceCommit -ceq 'PRECOMMIT') {
    $worktreeIdentity = Get-TextSha256 ((@($sourcePaths | Sort-Object | ForEach-Object { (Get-RelativePath $repositoryRoot $_) + '|' + (Get-Sha256 $_) + '|' + (Get-Item -LiteralPath $_).Length }) -join "`n"))
    $identityCommit = $worktreeIdentity.Substring(0,40)
    $sourceTree = (Get-TextSha256 ('R7_STATIC_WORKTREE_TREE_V1|' + $worktreeIdentity)).Substring(0,40)
} else { $identityCommit = $SourceCommit }

$bootstrapDerivation = Get-TextSha256 ('R7_STATIC_BOOTSTRAP_IDENTITY_V1|' + $identityCommit + '|' + $sourceTree + '|' + (Get-Sha256 $utilityRegistryPath))
$bootstrapFileIdentity = $bootstrapDerivation.Substring(0,8) + ':' + $bootstrapDerivation.Substring(8,16)
$bootstrapIdentity = Join-Path $output 'Generated\R7StaticBootstrapIdentity.g.cs'
$bootstrapIdentityText = @"
namespace RandleAI.R7Remediation
{
    internal static class R7BuildIdentity
    {
        internal const string UpgradePolicySha256 = "$bootstrapDerivation";
        internal const string UpgradePublicCertificateSha256 = "$bootstrapDerivation";
        internal const string DependencyManifestSha256 = "$bootstrapDerivation";
        internal const string UpgradeBinaryPath = @"C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradeAuthority.exe";
        internal const string SourceCommit = "$identityCommit";
        internal const string SourceTree = "$sourceTree";
        internal const string RequirementRegistrySha256 = "$bootstrapDerivation";
        internal const string CaseDefinitionsSha256 = "$bootstrapDerivation";
        internal const string ExpectationsSha256 = "$bootstrapDerivation";
        internal const string CoverageProofSha256 = "$bootstrapDerivation";
        internal const string AuthoritySourceManifestSha256 = "$bootstrapDerivation";
        internal const string HistoricalClassificationRegistrySha256 = "$bootstrapDerivation";
        internal const string ExecutionBinaryPath = @"C:\Program Files\RandleAI\TerminalAuthorityV4\RandleTerminalExecution.exe";
        internal const string ObservationBinaryPath = @"C:\Program Files\RandleAI\TerminalAuthorityV4\RandleTerminalObservation.exe";
        internal const string ComparatorBinaryPath = @"C:\Program Files\RandleAI\TerminalAuthorityV4\RandleTerminalComparator.exe";
        internal const string TerminalKeyFilePath = @"$output\IdentityInputs\terminal-$bootstrapDerivation";
        internal const string TerminalKeyFileIdentity = "$bootstrapFileIdentity";
        internal const string TerminalKeyFileOwnerSid = "S-1-5-18";
        internal const string TerminalKeyFileSecurityDescriptorSha256 = "$bootstrapDerivation";
        internal const string TerminalKeyFileVolumeIdentity = "$($bootstrapDerivation.Substring(0,8))";
        internal const uint TerminalKeyFileLinkCount = 1;
        internal const string UpgradeKeyFilePath = @"$output\IdentityInputs\upgrade-$bootstrapDerivation";
        internal const string UpgradeKeyFileIdentity = "$bootstrapFileIdentity";
        internal const string UpgradeKeyFileOwnerSid = "S-1-5-18";
        internal const string UpgradeKeyFileSecurityDescriptorSha256 = "$bootstrapDerivation";
        internal const string UpgradeKeyFileVolumeIdentity = "$($bootstrapDerivation.Substring(0,8))";
        internal const uint UpgradeKeyFileLinkCount = 1;
    }
    internal static class R7Unit2BuildIdentity
    {
        internal const string PublicCertificateSha256 = "$bootstrapDerivation";
        internal const string PolicySha256 = "$bootstrapDerivation";
        internal const string DependencyManifestSha256 = "$bootstrapDerivation";
        internal const string SourceCommit = "$identityCommit";
        internal const string SourceTree = "$sourceTree";
        internal const string KeyFilePath = @"$output\IdentityInputs\upgrade-$bootstrapDerivation";
        internal const string KeyFileOwnerSid = "S-1-5-18";
        internal const string KeyFileSecurityDescriptorSha256 = "$bootstrapDerivation";
        internal const string KeyFileVolumeIdentity = "$($bootstrapDerivation.Substring(0,8))";
        internal const string KeyFileIdentity = "$bootstrapFileIdentity";
        internal const uint KeyFileLinkCount = 1;
        internal const string BuildInputClosureSha256 = "$bootstrapDerivation";
        internal const string PolicyBindingKind = "STATIC_CONTENT_DERIVATION_V1";
    }
}
"@
[IO.File]::WriteAllText($bootstrapIdentity,$bootstrapIdentityText,[Text.UTF8Encoding]::new($false))
$artifactTarget = @($sourceRegistry.executable_roles | Where-Object { [string]$_.role -ceq 'ARTIFACT_TOOL' })
if ($artifactTarget.Count -ne 1) { throw 'Artifact-tool executable role is not unique.' }
$bootstrapTool = Join-Path $output 'Bootstrap\R7ArtifactTool.bootstrap.exe'
Invoke-Compiler $artifactTarget[0] $sourcePaths $bootstrapIdentity $bootstrapTool $compiler $references

$initialUtilityMeasurements = [Collections.Generic.List[object]]::new()
foreach ($row in @($utilityRegistry.utilities | Sort-Object role)) { $initialUtilityMeasurements.Add((Measure-Utility $row $bootstrapTool (Join-Path $output 'Measurements') 'initial')) }

$closureDefinitions = @(
    [ordered]@{role='GIT_INSTALLATION_ROOT';root=(Split-Path -Parent (Split-Path -Parent $git));name='git_installation'},
    [ordered]@{role='DOTNET_COMPILER_FRAMEWORK_ROOT';root=(Split-Path -Parent $compiler);name='dotnet_compiler_framework'},
    [ordered]@{role='DOTNET_REFERENCE_ASSEMBLY_ROOT';root=(Split-Path -Parent $references[0]);name='dotnet_reference_assemblies'},
    [ordered]@{role='ILDASM_TOOL_ROOT';root=(Split-Path -Parent $ildasm);name='ildasm_tool_directory'},
    [ordered]@{role='POWERSHELL_ORCHESTRATOR_ROOT';root=(Split-Path -Parent ([string]$powershellRow.path));name='powershell_orchestrator_directory'}
)
$closures = [Collections.Generic.List[object]]::new()
foreach ($definition in $closureDefinitions) {
    $initial = Join-Path $output ('Closures\' + $definition.name + '.initial.json')
    & $bootstrapTool directory-manifest ([IO.Path]::GetFullPath([string]$definition.root)) $initial | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Initial closure failed: $($definition.role)" }
    $manifest = Read-Json $initial
    $closures.Add([ordered]@{file_count=[long]$manifest.file_count;initial_manifest_raw_sha256=(Get-Sha256 $initial);initial_path=$initial;post_manifest_raw_sha256='PENDING';post_path='PENDING';role=[string]$definition.role;root=[string]$manifest.root;stable_during_use=$false})
}

$moduleSnapshotPath = Join-Path $output 'Generated\runtime_module_snapshot.json'
& $bootstrapTool module-snapshot $moduleSnapshotPath | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Static runtime module snapshot failed.' }
$moduleSnapshot = Read-Json $moduleSnapshotPath
$dependencyManifestPath = Join-Path $output 'Generated\static_dependency_manifest.json'
$dependencyManifest = [ordered]@{
    artifact_type='R7_STATIC_BUILD_AND_ORCHESTRATION_DEPENDENCY_MANIFEST'
    authority_classification='NONAUTHORITATIVE_STATIC_HOST_SPECIFIC_EVIDENCE'
    closed_search_policy=[ordered]@{compiler_path_search='DENIED';git_runtime_authority='DENIED';host_transition_utilities='CLASSIFIED_FUTURE_INPUTS_NOT_INVOKED';python_authority_path='DENIED';utility_path_search='DENIED'}
    external_utility_registry_sha256=(Get-Sha256 $utilityRegistryPath)
    framework_references=$references
    initial_build_input_closures=@($closures | ForEach-Object { [ordered]@{file_count=$_.file_count;manifest_raw_sha256=$_.initial_manifest_raw_sha256;role=$_.role;root=$_.root} })
    runtime_module_snapshot_sha256=(Get-Sha256 $moduleSnapshotPath)
    schema_version='1.0.0'
    status='STATIC_CONTENT_BOUND_RUNTIME_CLOSURE_REMAINS_PENDING_LIVE_PROOF'
}
Write-CanonicalNew $dependencyManifest $dependencyManifestPath $bootstrapTool

$artifactHashes = [ordered]@{
    requirement=(Get-Sha256 (Join-Path $packageRoot 'governed_requirement_registry.json'))
    cases=(Get-Sha256 (Join-Path $packageRoot 'immutable_case_definitions.json'))
    expectations=(Get-Sha256 (Join-Path $packageRoot 'immutable_expectations.json'))
    coverage=(Get-Sha256 (Join-Path $packageRoot 'exact_byte_coverage_proof.json'))
    authority_manifest=(Get-Sha256 (Join-Path $packageRoot 'AuthoritySources\authority_source_manifest.json'))
    history=(Get-Sha256 (Join-Path $packageRoot 'historical_classification_registry.json'))
    dependency=(Get-Sha256 $dependencyManifestPath)
}
$identitySource = Join-Path $output 'Generated\R7StaticBuildIdentity.g.cs'
$staticPolicyIdentity = Get-TextSha256 ('R7_STATIC_POLICY_IDENTITY_V1|' + $identityCommit + '|' + $sourceTree + '|' + $artifactHashes.dependency)
$staticCertificateIdentity = Get-TextSha256 ('R7_STATIC_CERTIFICATE_IDENTITY_V1|' + $identityCommit + '|' + $sourceTree)
$staticKeyIdentity = Get-TextSha256 ('R7_STATIC_KEY_METADATA_IDENTITY_V1|' + $identityCommit + '|' + $sourceTree)
$staticFileIdentity = $staticKeyIdentity.Substring(0,8) + ':' + $staticKeyIdentity.Substring(8,16)
$identityText = @"
namespace RandleAI.R7Remediation
{
    internal static class R7BuildIdentity
    {
        internal const string StaticAuthorityClassification = "UNINSTALLED_NONAUTHORITATIVE_STATIC_COMPILE_IDENTITY";
        internal const string UpgradePolicySha256 = "$staticPolicyIdentity";
        internal const string UpgradePublicCertificateSha256 = "$staticCertificateIdentity";
        internal const string DependencyManifestSha256 = "$($artifactHashes.dependency)";
        internal const string UpgradeBinaryPath = @"C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradeAuthority.exe";
        internal const string SourceCommit = "$identityCommit";
        internal const string SourceTree = "$sourceTree";
        internal const string RequirementRegistrySha256 = "$($artifactHashes.requirement)";
        internal const string CaseDefinitionsSha256 = "$($artifactHashes.cases)";
        internal const string ExpectationsSha256 = "$($artifactHashes.expectations)";
        internal const string CoverageProofSha256 = "$($artifactHashes.coverage)";
        internal const string AuthoritySourceManifestSha256 = "$($artifactHashes.authority_manifest)";
        internal const string HistoricalClassificationRegistrySha256 = "$($artifactHashes.history)";
        internal const string ExecutionBinaryPath = @"C:\Program Files\RandleAI\TerminalAuthorityV4\RandleTerminalExecution.exe";
        internal const string ObservationBinaryPath = @"C:\Program Files\RandleAI\TerminalAuthorityV4\RandleTerminalObservation.exe";
        internal const string ComparatorBinaryPath = @"C:\Program Files\RandleAI\TerminalAuthorityV4\RandleTerminalComparator.exe";
        internal const string TerminalKeyFilePath = @"$output\IdentityInputs\terminal-$staticKeyIdentity";
        internal const string TerminalKeyFileIdentity = "$staticFileIdentity";
        internal const string TerminalKeyFileOwnerSid = "S-1-5-18";
        internal const string TerminalKeyFileSecurityDescriptorSha256 = "$staticKeyIdentity";
        internal const string TerminalKeyFileVolumeIdentity = "$($staticKeyIdentity.Substring(0,8))";
        internal const uint TerminalKeyFileLinkCount = 1;
        internal const string UpgradeKeyFilePath = @"$output\IdentityInputs\upgrade-$staticKeyIdentity";
        internal const string UpgradeKeyFileIdentity = "$staticFileIdentity";
        internal const string UpgradeKeyFileOwnerSid = "S-1-5-18";
        internal const string UpgradeKeyFileSecurityDescriptorSha256 = "$staticKeyIdentity";
        internal const string UpgradeKeyFileVolumeIdentity = "$($staticKeyIdentity.Substring(0,8))";
        internal const uint UpgradeKeyFileLinkCount = 1;
    }
    internal static class R7Unit2BuildIdentity
    {
        internal const string PublicCertificateSha256 = "$staticCertificateIdentity";
        internal const string PolicySha256 = "$staticPolicyIdentity";
        internal const string DependencyManifestSha256 = "$($artifactHashes.dependency)";
        internal const string SourceCommit = "$identityCommit";
        internal const string SourceTree = "$sourceTree";
        internal const string KeyFilePath = @"$output\IdentityInputs\upgrade-$staticKeyIdentity";
        internal const string KeyFileOwnerSid = "S-1-5-18";
        internal const string KeyFileSecurityDescriptorSha256 = "$staticKeyIdentity";
        internal const string KeyFileVolumeIdentity = "$($staticKeyIdentity.Substring(0,8))";
        internal const string KeyFileIdentity = "$staticFileIdentity";
        internal const uint KeyFileLinkCount = 1;
        internal const string BuildInputClosureSha256 = "$staticKeyIdentity";
        internal const string PolicyBindingKind = "STATIC_CONTENT_DERIVATION_V1";
    }
}
"@
[IO.File]::WriteAllText($identitySource, $identityText, [Text.UTF8Encoding]::new($false))
foreach ($identity in $artifactHashes.GetEnumerator()) { if (-not $identityText.Contains([string]$identity.Value)) { throw "Generated identity omitted package input: $($identity.Key)" } }

$targets = @($sourceRegistry.executable_roles | Sort-Object role)
if ([int]$sourceRegistry.executable_role_count -ne $targets.Count -or $targets.Count -eq 0) { throw 'Executable role registry count mismatch.' }
$allRoles = @($targets | ForEach-Object { [string]$_.role } | Sort-Object)
$binaryReceipts = [Collections.Generic.List[object]]::new()
foreach ($target in $targets) {
    $targetSources = @($declaredSources | Where-Object { @($_.compiled_into_roles) -contains [string]$target.role } | Sort-Object path)
    if ($targetSources.Count -eq 0) { throw "Executable role has no source set: $($target.role)" }
    $sourceFiles = @($targetSources | ForEach-Object { Join-Path $packageRoot ([string]$_.path).Replace('/','\') }) + $contractPath
    $passA = Join-Path $output ('PassA\' + [string]$target.file_name)
    $passB = Join-Path $output ('PassB\' + [string]$target.file_name)
    Invoke-Compiler $target $sourceFiles $identitySource $passA $compiler $references
    [Threading.Thread]::Sleep(1100)
    Invoke-Compiler $target $sourceFiles $identitySource $passB $compiler $references
    $ilA = Join-Path $output ('NormalizedIL\' + [string]$target.file_name + '.pass-a.il')
    $ilB = Join-Path $output ('NormalizedIL\' + [string]$target.file_name + '.pass-b.il')
    $ilShaA = Get-NormalizedIl $passA $ilA $ildasm
    $ilShaB = Get-NormalizedIl $passB $ilB $ildasm
    if ($ilShaA -cne $ilShaB) { throw "Normalized IL mismatch: $($target.role)" }
    $binaryReceipts.Add([ordered]@{
        authority_classification='UNINSTALLED_NONAUTHORITATIVE_STATIC_COMPILE_EVIDENCE'
        define=[string]$target.define
        file_name=[string]$target.file_name
        generated_identity_sha256=(Get-Sha256 $identitySource)
        main=[string]$target.main
        normalized_il_equal=$true
        normalized_il_sha256=$ilShaA
        pass_a_raw_sha256=(Get-Sha256 $passA)
        pass_a_size=(Get-Item -LiteralPath $passA).Length
        pass_b_raw_sha256=(Get-Sha256 $passB)
        pass_b_size=(Get-Item -LiteralPath $passB).Length
        raw_difference=(Get-RawDifference $passA $passB)
        role=[string]$target.role
        source_paths=@($targetSources | ForEach-Object { [string]$_.path })
    })
}

$postUtilityMeasurements = [Collections.Generic.List[object]]::new()
foreach ($row in @($utilityRegistry.utilities | Sort-Object role)) { Assert-UtilityContent $row; $postUtilityMeasurements.Add((Measure-Utility $row $bootstrapTool (Join-Path $output 'Measurements') 'post')) }
for ($index = 0; $index -lt $closureDefinitions.Count; $index++) {
    $definition = $closureDefinitions[$index]
    $post = Join-Path $output ('Closures\' + $definition.name + '.post.json')
    & $bootstrapTool directory-manifest ([IO.Path]::GetFullPath([string]$definition.root)) $post | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Post-use closure failed: $($definition.role)" }
    $postHash = Get-Sha256 $post
    if ($postHash -cne [string]$closures[$index].initial_manifest_raw_sha256) { throw "Build input changed during static use: $($definition.role)" }
    $closures[$index].post_manifest_raw_sha256 = $postHash
    $closures[$index].post_path = $post
    $closures[$index].stable_during_use = $true
}

$sourceReceiptRows = @($declaredSources | ForEach-Object { [ordered]@{git_blob_identity=[string]$_.git_blob_identity;mode=[string]$_.mode;path=($packageRelativeRoot + '/' + [string]$_.path);raw_sha256=[string]$_.raw_sha256;size=[long]$_.size} })
$sourceReceiptRows += [ordered]@{git_blob_identity=(Get-GitBlobIdentity $contractPath);mode='100644';path=($packageRelativeRoot + '/BuildInputs/R7BuildIdentityContract.cs');raw_sha256=(Get-Sha256 $contractPath);size=(Get-Item -LiteralPath $contractPath).Length}
$scriptReceiptRows = foreach ($row in $declaredScripts) { [ordered]@{allowed_invocation_stages=@($row.allowed_invocation_stages);authority_classification=[string]$row.authority_classification;dependencies=@($row.dependencies);execution_class=[string]$row.execution_class;git_blob_identity=[string]$row.git_blob_identity;mode=[string]$row.mode;path=[string]$row.path;raw_sha256=[string]$row.raw_sha256;role=[string]$row.role;size=[long]$row.size} }
$receiptPath = Join-Path $output 'static_build_receipt.json'
$receipt = [ordered]@{
    artifact_type='R7_STATIC_SOURCE_TO_BINARY_CLOSURE_RECEIPT'
    authority_classification='NONAUTHORITATIVE_OFFLINE_STATIC_EVIDENCE'
    binaries=$binaryReceipts.ToArray()
    build_input_closures=$closures.ToArray()
    compiler_options=$compilerOptions
    dependency_manifest_raw_sha256=(Get-Sha256 $dependencyManifestPath)
    external_utilities_initial=$initialUtilityMeasurements.ToArray()
    external_utilities_post=$postUtilityMeasurements.ToArray()
    external_utility_registry_raw_sha256=(Get-Sha256 $utilityRegistryPath)
    framework_reference_paths=$references
    generated_identity=[ordered]@{authority_classification='UNINSTALLED_NONAUTHORITATIVE_STATIC_COMPILE_IDENTITY';path=$identitySource;raw_sha256=(Get-Sha256 $identitySource);source_identity_class=$sourceIdentityClass}
    governed_scripts=@($scriptReceiptRows)
    schema_version='1.0.0'
    source_commit=$identityCommit
    source_files=@($sourceReceiptRows)
    source_role_registry_raw_sha256=(Get-Sha256 $sourceRegistryPath)
    source_tree=$sourceTree
    status='PASS'
}
Write-CanonicalNew $receipt $receiptPath $bootstrapTool
$summaryPath = Join-Path $output 'static_build_summary.json'
$summary = [ordered]@{
    artifact_type='R7_STATIC_BUILD_CLOSURE_SUMMARY'
    authority_classification='NONAUTHORITATIVE_OFFLINE_STATIC_EVIDENCE'
    binary_count=$binaryReceipts.Count
    dependency_manifest_raw_sha256=(Get-Sha256 $dependencyManifestPath)
    generated_identity_raw_sha256=(Get-Sha256 $identitySource)
    governed_script_count=$declaredScripts.Count
    prohibited_source_dependency_count=0
    schema_version='1.0.0'
    source_commit=$identityCommit
    source_count=$declaredSources.Count
    source_identity_class=$sourceIdentityClass
    source_tree=$sourceTree
    static_build_receipt_raw_sha256=(Get-Sha256 $receiptPath)
    status='PASS'
    utility_count=@($utilityRegistry.utilities).Count
}
Write-CanonicalNew $summary $summaryPath $bootstrapTool
[ordered]@{binary_count=$binaryReceipts.Count;output_root=$output;receipt_sha256=(Get-Sha256 $receiptPath);source_commit=$identityCommit;source_tree=$sourceTree;status='PASS'} | ConvertTo-Json
