[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$SourceCommit,
    [Parameter(Mandatory = $true)][string]$UpgradeBootstrapRecord,
    [Parameter(Mandatory = $true)][string]$UpgradePublicCertificate,
    [Parameter(Mandatory = $true)][string]$TerminalPublicCertificate,
    [Parameter(Mandatory = $true)][string]$OutputRoot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$packageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $packageRoot '..\..\..'))
$safeRepository = $repositoryRoot.Replace('\','/')
$output = [IO.Path]::GetFullPath($OutputRoot)
$compiler = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$ildasm = 'C:\Program Files (x86)\Microsoft SDKs\Windows\v10.0A\bin\NETFX 4.8 Tools\x64\ildasm.exe'
$referenceRoot = 'C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework\v4.8'
$referencePaths = @('mscorlib.dll', 'System.dll', 'System.Core.dll', 'System.Security.dll', 'System.ServiceProcess.dll') | ForEach-Object { Join-Path $referenceRoot $_ }
$machineConfig = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\Config\machine.config'
$serviceControlTool = 'C:\Windows\System32\sc.exe'
$aclTool = 'C:\Windows\System32\icacls.exe'
$governedGitExecutable = 'C:\Program Files\Git\cmd\git.exe'
$terminalInstallRoot = 'C:\Program Files\RandleAI\TerminalAuthorityV4'
$terminalRemediationRoot = 'C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4'
$upgradeInstallRoot = 'C:\Program Files\RandleAI\TerminalUpgradeAuthority'
$upgradeStateRoot = 'C:\ProgramData\RandleAI\TerminalUpgradeAuthority'
$terminalKeyFile = 'C:\ProgramData\Microsoft\Crypto\Keys\1c9681c0b04a3dd4843d8cb457b92413_c5338977-c52f-4ca7-af6f-db9b5e287cca'

function Get-LowerHash([string]$Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function Get-RelativePath([string]$Base, [string]$Path) {
    $baseFull = [IO.Path]::GetFullPath($Base).TrimEnd('\') + '\'
    $pathFull = [IO.Path]::GetFullPath($Path)
    $relative = [Uri]::UnescapeDataString(([Uri]$baseFull).MakeRelativeUri([Uri]$pathFull).ToString())
    return $relative.Replace('/', '\')
}
function Get-StringHash([string]$Value) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value))).Replace('-', '')).ToLowerInvariant() }
    finally { $algorithm.Dispose() }
}
function Get-ByteHash([byte[]]$Value) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($Value)).Replace('-', '')).ToLowerInvariant() }
    finally { $algorithm.Dispose() }
}
function Assert-ExactPropertySet([object]$Value, [string[]]$Expected, [string]$Label) {
    $actual = @($Value.PSObject.Properties.Name | Sort-Object)
    $required = @($Expected | Sort-Object)
    if ($actual.Count -ne $required.Count -or (($actual -join "`n") -cne ($required -join "`n"))) { throw "$Label property set is not exact." }
}
function Assert-NewDirectory([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        if ((Get-ChildItem -LiteralPath $Path -Force | Measure-Object).Count -ne 0) { throw "Output root is not empty: $Path" }
    } else { New-Item -ItemType Directory -Path $Path | Out-Null }
}
function Invoke-Compiler([string]$Main, [string]$Define, [string]$Destination, [string]$IdentitySource) {
    $arguments = @(
        '/nologo', '/noconfig', '/target:exe', '/platform:x64', '/optimize+', '/checked+', '/debug-', '/warn:4', '/nostdlib+', '/langversion:5', '/filealign:512',
        ('/main:' + $Main), ('/out:' + $Destination)
    )
    if ($Define) { $arguments += ('/define:' + $Define) }
    foreach ($reference in $referencePaths) { $arguments += ('/reference:' + $reference) }
    $arguments += $sourcePaths
    $arguments += $IdentitySource
    & $compiler @arguments
    if ($LASTEXITCODE -ne 0) { throw "Compiler failed for $Main" }
}
function Write-RawJson([object]$Value, [string]$Path) {
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 32), [Text.UTF8Encoding]::new($false))
}
function Write-CanonicalJson([object]$Value, [string]$Destination, [string]$Tool) {
    $raw = $Destination + '.raw'
    if (Test-Path -LiteralPath $raw -or Test-Path -LiteralPath $Destination) { throw "Refusing artifact overwrite: $Destination" }
    Write-RawJson $Value $raw
    & $Tool canonicalize $raw $Destination | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Canonicalization failed: $Destination" }
}
function Get-Measurement([string]$Path, [string]$Role, [string]$Tool, [string]$MeasurementRoot) {
    $name = (Get-StringHash ($Role + '|' + $Path)) + '.json'
    $target = Join-Path $MeasurementRoot $name
    & $Tool measure $Path $target
    if ($LASTEXITCODE -ne 0) { throw "Measurement failed: $Path" }
    $value = Get-Content -Raw -LiteralPath $target | ConvertFrom-Json
    return [ordered]@{ role = $Role; measurement = $value }
}
function Get-NormalizedIl([string]$Binary, [string]$Destination) {
    $raw = $Destination + '.raw.il'
    & $ildasm /text /nobar /utf8 ("/out=$raw") $Binary
    if ($LASTEXITCODE -ne 0) { throw "IL disassembly failed: $Binary" }
    $text = [IO.File]::ReadAllText($raw)
    $mvid = [regex]::Match($text, '(?m)^// MVID: \{([0-9A-Fa-f-]+)\}\r?$')
    if (-not $mvid.Success) { throw "IL MVID was not found: $Binary" }
    $text = $text.Replace($mvid.Groups[1].Value, 'NORMALIZED-MVID')
    $text = [regex]::Replace($text, '(?m)^// Image base: 0x[0-9A-Fa-f]+\r?$', '// Image base: NORMALIZED')
    $text = [regex]::Replace($text, '(?m)^// WARNING: Created Win32 resource file .+\.raw\.res\r?$', '// WARNING: Created Win32 resource file NORMALIZED.raw.res')
    [IO.File]::WriteAllText($Destination, $text, [Text.UTF8Encoding]::new($false))
    return Get-LowerHash $Destination
}
function Get-RawDifference([string]$Left, [string]$Right) {
    $a = [IO.File]::ReadAllBytes($Left); $b = [IO.File]::ReadAllBytes($Right)
    $limit = [Math]::Min($a.Length, $b.Length); $offsets = [Collections.Generic.List[long]]::new(); $count = 0L
    for ($index = 0; $index -lt $limit; $index++) { if ($a[$index] -ne $b[$index]) { $count++; if ($offsets.Count -lt 128) { $offsets.Add($index) } } }
    $count += [Math]::Abs($a.Length - $b.Length)
    return [ordered]@{ differing_byte_count = $count; first_differing_offsets = $offsets.ToArray(); left_size = $a.Length; right_size = $b.Length; explanation = 'Raw PE nondeterminism is limited by normalized-IL equality; expected causes are COFF timestamp and MVID/metadata identity bytes.' }
}
function Copy-New([string]$Source, [string]$Destination) {
    if (Test-Path -LiteralPath $Destination) { throw "Refusing staged overwrite: $Destination" }
    $parent = Split-Path -Parent $Destination
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
    Copy-Item -LiteralPath $Source -Destination $Destination
}
function Invoke-GovernedGitRaw([string[]]$Arguments) {
    if ((Get-LowerHash $gitExecutable) -ne $gitExecutableSha256) { throw 'Git executable changed during immutable-object access.' }
    $fixed = @('--no-pager','-c',"safe.directory=$safeRepository",'-c','core.autocrlf=false','-c','core.safecrlf=false','-c','core.attributesfile=NUL','-c','core.fsmonitor=false','-c','core.untrackedCache=false','-c','core.hooksPath=NUL','-c','submodule.recurse=false','-c','diff.external=','-c','i18n.commitEncoding=utf-8','-c','i18n.logOutputEncoding=utf-8','-C',$repositoryRoot)
    foreach ($argument in @($fixed + $Arguments)) { if ([string]$argument -match '[\s"]') { throw "Governed Git argument requires unsupported quoting: $argument" } }
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $gitExecutable
    $start.Arguments = (@($fixed + $Arguments) -join ' ')
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = [Diagnostics.Process]::new(); $process.StartInfo = $start
    try {
        if (-not $process.Start()) { throw 'Governed Git process did not start.' }
        $memory = [IO.MemoryStream]::new()
        try { $process.StandardOutput.BaseStream.CopyTo($memory); $stderr = $process.StandardError.ReadToEnd(); $process.WaitForExit(); $raw = $memory.ToArray() }
        finally { $memory.Dispose() }
        $stderrSha = Get-StringHash $stderr
        $script:governedGitInvocations.Add([ordered]@{arguments=@($Arguments);exit_code=$process.ExitCode;fixed_options=@($fixed);stderr_sha256=$stderrSha;stdout_raw_sha256=(Get-ByteHash $raw);stdout_size=$raw.Length})
        if ($process.ExitCode -ne 0) { throw "Governed Git failed: $($Arguments -join ' ') | $stderr" }
        return ,$raw
    } finally { $process.Dispose() }
}
function Invoke-GovernedGit([string[]]$Arguments) {
    $raw = Invoke-GovernedGitRaw $Arguments
    $text = [Text.UTF8Encoding]::new($false,$true).GetString($raw)
    if ($text.EndsWith("`n",[StringComparison]::Ordinal)) { $text = $text.Substring(0,$text.Length-1) }
    if ($text.Length -eq 0) { return @() }
    return @($text -split "`n" | ForEach-Object { $_.TrimEnd("`r") })
}

foreach ($required in @($compiler, $ildasm, $machineConfig, $serviceControlTool, $aclTool, $UpgradeBootstrapRecord, $UpgradePublicCertificate, $TerminalPublicCertificate, $terminalKeyFile) + $referencePaths) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required build input missing: $required" }
}
Assert-NewDirectory $output
foreach ($directory in @('Bootstrap', 'Generated', 'Generated\BuildInputClosures', 'Generated\ImmutableRepository', 'Measurements', 'PassA', 'PassB', 'FinalPassA', 'FinalPassB', 'NormalizedIL', 'Staging\bin', 'Staging\config', 'Staging\build', 'Staging\authority', 'UpgradeBootstrap')) { New-Item -ItemType Directory -Path (Join-Path $output $directory) -Force | Out-Null }
if ($output.StartsWith($repositoryRoot.TrimEnd('\') + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Build output must be outside the immutable source checkout.' }

$workingPackageRoot = $packageRoot
$gitExecutable = $governedGitExecutable
$powershellExecutable = (Get-Process -Id $PID).Path
$gitExecutableSha256 = Get-LowerHash $gitExecutable
$governedGitInvocations = [Collections.Generic.List[object]]::new()
$env:GIT_CONFIG_NOSYSTEM = '1'
$env:GIT_CONFIG_GLOBAL = 'NUL'
$env:GIT_CONFIG_SYSTEM = 'NUL'
$env:GIT_OPTIONAL_LOCKS = '0'
$env:GIT_TERMINAL_PROMPT = '0'
$env:GIT_LITERAL_PATHSPECS = '1'
$env:GIT_ATTR_NOSYSTEM = '1'
$env:GIT_PAGER = ''
$env:LANG = 'C'
$env:LC_ALL = 'C'
$gitEnvironment = [ordered]@{GIT_ATTR_NOSYSTEM=$env:GIT_ATTR_NOSYSTEM;GIT_CONFIG_GLOBAL=$env:GIT_CONFIG_GLOBAL;GIT_CONFIG_NOSYSTEM=$env:GIT_CONFIG_NOSYSTEM;GIT_CONFIG_SYSTEM=$env:GIT_CONFIG_SYSTEM;GIT_LITERAL_PATHSPECS=$env:GIT_LITERAL_PATHSPECS;GIT_OPTIONAL_LOCKS=$env:GIT_OPTIONAL_LOCKS;GIT_PAGER=$env:GIT_PAGER;GIT_TERMINAL_PROMPT=$env:GIT_TERMINAL_PROMPT;LANG=$env:LANG;LC_ALL=$env:LC_ALL;path_resolution='RESOLVED_ONCE_THEN_EXACT_EXECUTABLE'}

$head = ([string](Invoke-GovernedGit @('rev-parse','HEAD'))).Trim()
if ($head -ne $SourceCommit) { throw "HEAD $head does not match requested source commit $SourceCommit" }
if (@(Invoke-GovernedGit @('status','--porcelain=v1','--untracked-files=all')).Count -ne 0) { throw 'Source checkout must be clean.' }
$sourceTree = ([string](Invoke-GovernedGit @('show','-s','--format=%T',$SourceCommit))).Trim()
$commitBlobMap = @{}
$commitModeMap = @{}
foreach ($treeRow in @(Invoke-GovernedGit @('ls-tree','-r',$SourceCommit))) {
    if ([string]$treeRow -notmatch '^(100644|100755) blob ([0-9a-f]{40})\t(.+)$') { continue }
    if ($commitBlobMap.ContainsKey($Matches[3])) { throw "Duplicate committed path: $($Matches[3])" }
    $commitBlobMap[$Matches[3]] = $Matches[2]
    $commitModeMap[$Matches[3]] = $Matches[1]
}
$packageRelativeRoot = (Get-RelativePath $repositoryRoot $workingPackageRoot).Replace('\','/')
$immutableRepositoryRoot = Join-Path $output 'Generated\ImmutableRepository'
$immutablePackageRoot = Join-Path $immutableRepositoryRoot $packageRelativeRoot.Replace('/','\')
$extractedPackageBlobs = [Collections.Generic.List[object]]::new()
foreach ($relativePath in @($commitBlobMap.Keys | Where-Object { $_ -eq $packageRelativeRoot -or $_.StartsWith($packageRelativeRoot + '/', [StringComparison]::Ordinal) } | Sort-Object)) {
    $blob = [string]$commitBlobMap[$relativePath]
    $raw = Invoke-GovernedGitRaw @('cat-file','blob',$blob)
    $destination = Join-Path $immutableRepositoryRoot $relativePath.Replace('/','\')
    $parent = Split-Path -Parent $destination
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    if (Test-Path -LiteralPath $destination) { throw "Immutable extraction collision: $relativePath" }
    [IO.File]::WriteAllBytes($destination,$raw)
    $rawSha256 = Get-ByteHash $raw
    if ((Get-LowerHash $destination) -ne $rawSha256) { throw "Immutable extraction verification failed: $relativePath" }
    $extractedPackageBlobs.Add([ordered]@{blob=$blob;extracted_path=$destination;path=$relativePath;raw_sha256=$rawSha256;size=$raw.Length})
}
if ($extractedPackageBlobs.Count -eq 0) { throw 'Immutable package extraction was empty.' }
$packageRoot = $immutablePackageRoot
$sourcePaths = Get-ChildItem -LiteralPath (Join-Path $packageRoot 'Source') -Filter '*.cs' | Sort-Object Name | ForEach-Object FullName
$developmentIdentity = Join-Path $packageRoot 'BuildInputs\R7DevelopmentIdentity.g.cs'
if ($sourcePaths.Count -eq 0 -or -not (Test-Path -LiteralPath $developmentIdentity -PathType Leaf)) { throw 'Immutable C# source extraction is incomplete.' }
$bootstrapTool = Join-Path $output 'Bootstrap\R7ArtifactTool.bootstrap.exe'
$bootstrapToolPassB = Join-Path $output 'Bootstrap\R7ArtifactTool.bootstrap.pass-b.exe'
Invoke-Compiler 'RandleAI.R7Remediation.R7ArtifactToolProgram' '' $bootstrapTool $developmentIdentity
Start-Sleep -Milliseconds 1100
Invoke-Compiler 'RandleAI.R7Remediation.R7ArtifactToolProgram' '' $bootstrapToolPassB $developmentIdentity
$bootstrapLeftIl = Join-Path $output 'NormalizedIL\R7ArtifactTool.bootstrap.pass-a.il'
$bootstrapRightIl = Join-Path $output 'NormalizedIL\R7ArtifactTool.bootstrap.pass-b.il'
$bootstrapLeftIlSha = Get-NormalizedIl $bootstrapTool $bootstrapLeftIl
$bootstrapRightIlSha = Get-NormalizedIl $bootstrapToolPassB $bootstrapRightIl
if ($bootstrapLeftIlSha -ne $bootstrapRightIlSha) { throw 'Normalized IL mismatch for BOOTSTRAP_ARTIFACT_TOOL.' }
$bootstrapBinaryReceipt = [ordered]@{
    role='BOOTSTRAP_ARTIFACT_TOOL';file_name='R7ArtifactTool.bootstrap.exe';pass_a_sha256=(Get-LowerHash $bootstrapTool);pass_b_sha256=(Get-LowerHash $bootstrapToolPassB);
    normalized_il_sha256=$bootstrapLeftIlSha;normalized_il_equal=$true;raw_difference=(Get-RawDifference $bootstrapTool $bootstrapToolPassB);size=(Get-Item -LiteralPath $bootstrapTool).Length
}

$moduleSnapshotPath = Join-Path $output 'Generated\runtime_module_snapshot.json'
& $bootstrapTool module-snapshot $moduleSnapshotPath ([IO.Path]::GetFullPath($TerminalPublicCertificate)) ([IO.Path]::GetFullPath($UpgradePublicCertificate))
if ($LASTEXITCODE -ne 0) { throw 'Runtime module snapshot failed.' }
$moduleSnapshot = Get-Content -Raw -LiteralPath $moduleSnapshotPath | ConvertFrom-Json
$measurementRoot = Join-Path $output 'Measurements'
$buildInputClosures = [Collections.Generic.List[object]]::new()
$closureInputs = @(
    @('GIT_INSTALLATION', (Split-Path -Parent (Split-Path -Parent $gitExecutable)), 'git_installation.json'),
    @('DOTNET_COMPILER_FRAMEWORK', (Split-Path -Parent $compiler), 'dotnet_compiler_framework.json'),
    @('DOTNET_REFERENCE_ASSEMBLIES', $referenceRoot, 'dotnet_reference_assemblies.json'),
    @('ILDASM_TOOL_DIRECTORY', (Split-Path -Parent $ildasm), 'ildasm_tool_directory.json'),
    @('POWERSHELL_ORCHESTRATOR_DIRECTORY', (Split-Path -Parent $powershellExecutable), 'powershell_orchestrator_directory.json')
)
foreach ($closureInput in $closureInputs) {
    $closurePath = Join-Path $output ('Generated\BuildInputClosures\' + $closureInput[2])
    & $bootstrapTool directory-manifest ([IO.Path]::GetFullPath($closureInput[1])) $closurePath
    if ($LASTEXITCODE -ne 0) { throw "Build-input closure failed: $($closureInput[0])" }
    $closure = Get-Content -Raw -LiteralPath $closurePath | ConvertFrom-Json
    $buildInputClosures.Add([ordered]@{file_count=[long]$closure.file_count;manifest_raw_sha256=(Get-LowerHash $closurePath);manifest_relative_path=('BuildInputClosures/' + $closureInput[2]);post_use_manifest_relative_path='PENDING';post_use_raw_sha256='PENDING';role=$closureInput[0];root=[string]$closure.root;stable_during_use=$false})
}
$verificationHead = ([string](Invoke-GovernedGit @('rev-parse','HEAD'))).Trim()
$verificationTree = ([string](Invoke-GovernedGit @('show','-s','--format=%T',$SourceCommit))).Trim()
if ($verificationHead -ne $head -or $verificationTree -ne $sourceTree -or @(Invoke-GovernedGit @('status','--porcelain=v1','--untracked-files=all')).Count -ne 0) { throw 'Immutable source identity changed during extraction.' }
foreach ($record in $extractedPackageBlobs) {
    $verifiedRaw = Invoke-GovernedGitRaw @('cat-file','blob',[string]$record.blob)
    if ($verifiedRaw.Length -ne [long]$record.size -or (Get-ByteHash $verifiedRaw) -ne [string]$record.raw_sha256) { throw "Git blob changed across closed verification: $($record.path)" }
}
$postGitClosurePath = Join-Path $output 'Generated\BuildInputClosures\git_installation.post-use.json'
& $bootstrapTool directory-manifest ([IO.Path]::GetFullPath($closureInputs[0][1])) $postGitClosurePath
if ($LASTEXITCODE -ne 0) { throw 'Post-use Git closure failed.' }
$postGitClosureSha = Get-LowerHash $postGitClosurePath
if ($postGitClosureSha -ne [string]$buildInputClosures[0].manifest_raw_sha256) { throw 'Git installation changed while resolving immutable source objects.' }
$buildInputClosures[0].post_use_raw_sha256 = $postGitClosureSha
$buildInputClosures[0].post_use_manifest_relative_path = 'BuildInputClosures/git_installation.post-use.json'
$buildInputClosures[0].stable_during_use = $true
$buildTools = [Collections.Generic.List[object]]::new()
foreach ($item in @(
    @('CSC', $compiler), @('ILDASM', $ildasm), @('GIT_BUILD_TIME_ONLY', $gitExecutable), @('POWERSHELL_NONAUTHORITATIVE_ORCHESTRATOR', $powershellExecutable), @('BOOTSTRAP_ARTIFACT_TOOL', $bootstrapTool), @('RUNTIME_MACHINE_CONFIG', $machineConfig),
    @('HOST_SERVICE_CONTROL_TOOL', $serviceControlTool), @('HOST_ACL_TOOL', $aclTool)
)) { $buildTools.Add((Get-Measurement $item[1] $item[0] $bootstrapTool $measurementRoot)) }
foreach ($reference in $referencePaths) { $buildTools.Add((Get-Measurement $reference ('COMPILER_REFERENCE_' + [IO.Path]::GetFileName($reference)) $bootstrapTool $measurementRoot)) }
$nativeRuntimeNames = @($moduleSnapshot.runtime_allowlist | ForEach-Object { [IO.Path]::GetFileName([string]$_.path) })
$managedRuntimeNames = @($moduleSnapshot.framework_references | ForEach-Object { [IO.Path]::GetFileName([string]$_.path) })
foreach ($requiredRuntime in @('clr.dll','clrjit.dll')) { if ($nativeRuntimeNames -cnotcontains $requiredRuntime) { throw "Runtime snapshot omitted $requiredRuntime." } }
foreach ($requiredAssembly in @('mscorlib.dll','System.dll','System.Core.dll','System.ServiceProcess.dll')) { if ($managedRuntimeNames -cnotcontains $requiredAssembly) { throw "Runtime snapshot omitted $requiredAssembly." } }
$runtimeConfiguration = @($buildTools | Where-Object { $_.role -ceq 'RUNTIME_MACHINE_CONFIG' } | ForEach-Object { $_.measurement })
if ($runtimeConfiguration.Count -ne 1) { throw 'Runtime machine configuration measurement is not unique.' }

$dependencyManifestPath = Join-Path $output 'Generated\dependency_manifest.json'
$dependencyManifest = [ordered]@{
    artifact_type = 'R7_CLOSED_EXECUTABLE_DEPENDENCY_MANIFEST'
    build_host_architecture = 'x64'
    build_tools = $buildTools.ToArray()
    closed_search_policy = [ordered]@{ application_configuration = 'DENIED'; current_directory_imports = 'DENIED'; environment_imports = 'DENIED'; git_runtime = 'DENIED'; machine_configuration = 'MANIFESTED_AND_HELD'; native_dll_search = 'SYSTEM32_ONLY'; python_runtime = 'DENIED'; runtime_profiler = 'DENIED'; unmanifested_modules = 'DENIED'; user_site = 'DENIED' }
    framework_references = $moduleSnapshot.framework_references
    runtime_allowlist = $moduleSnapshot.runtime_allowlist
    runtime_configuration = $runtimeConfiguration
    schema_version = '1.0.0'
}
Write-CanonicalJson $dependencyManifest $dependencyManifestPath $bootstrapTool
$dependencyManifestSha = Get-LowerHash $dependencyManifestPath

$bootstrap = Get-Content -Raw -LiteralPath $UpgradeBootstrapRecord | ConvertFrom-Json
$upgradeCertificateSha = Get-LowerHash $UpgradePublicCertificate
$provisionScriptPath = Join-Path $packageRoot 'provision_upgrade_authority.ps1'
if ($bootstrap.public_certificate_sha256 -ne $upgradeCertificateSha -or $bootstrap.service_sid -ne 'S-1-5-80-238545627-4117296865-2677355104-248304369-1301198082' -or $bootstrap.source_commit -cne $SourceCommit -or $bootstrap.source_tree -cne $sourceTree -or $bootstrap.provisioning_script_sha256 -cne (Get-LowerHash $provisionScriptPath) -or $bootstrap.interactive_logon_denial -cne 'DEFERRED_TO_MEASURED_PRESTART_BOOTSTRAP') { throw 'Upgrade bootstrap record does not bind the supplied trust, source, script, service SID and prestart boundary obligation.' }
$bootstrapDependencyPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($dependency in @($bootstrap.provisioning_dependencies)) {
    Assert-ExactPropertySet $dependency @('path','raw_sha256','size') ('Bootstrap dependency ' + [string]$dependency.path)
    $path = [IO.Path]::GetFullPath([string]$dependency.path)
    if (-not $bootstrapDependencyPaths.Add($path) -or [string]$dependency.raw_sha256 -notmatch '^[0-9a-f]{64}$' -or -not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-LowerHash $path) -cne [string]$dependency.raw_sha256 -or (Get-Item -LiteralPath $path).Length -ne [long]$dependency.size) { throw "Upgrade bootstrap dependency identity mismatch: $path" }
}
foreach ($requiredBootstrapDependency in @('C:\Windows\System32\sc.exe','C:\Windows\System32\icacls.exe',(Join-Path $PSHOME 'Modules\PKI\PKI.psd1'))) { if (-not $bootstrapDependencyPaths.Contains([IO.Path]::GetFullPath($requiredBootstrapDependency))) { throw "Upgrade bootstrap dependency is absent: $requiredBootstrapDependency" } }
$bootstrapDependenciesJson = @($bootstrap.provisioning_dependencies) | ConvertTo-Json -Depth 8 -Compress
if ((Get-ByteHash ([Text.Encoding]::UTF8.GetBytes($bootstrapDependenciesJson))) -cne [string]$bootstrap.provisioning_dependency_set_sha256) { throw 'Upgrade bootstrap dependency-set identity mismatch.' }
$terminalCertificateSha = Get-LowerHash $TerminalPublicCertificate
if ($terminalCertificateSha -ne 'b84a4de14577580c64ff5b2446f120aa6f9ea60faa2cb5465b495282f0273285') { throw 'Terminal public certificate identity mismatch.' }
$volumeIdentity = [string]$moduleSnapshot.runtime_allowlist[0].volume_identity
$upgradeKeyFile = Join-Path 'C:\ProgramData\Microsoft\Crypto\Keys' ([string]$bootstrap.key_unique_name)
$terminalKeyMetadataPath = Join-Path $output 'Generated\terminal_key_file_metadata.json'
$upgradeKeyMetadataPath = Join-Path $output 'Generated\upgrade_key_file_metadata.json'
& $bootstrapTool measure-metadata $terminalKeyFile $terminalKeyMetadataPath
if ($LASTEXITCODE -ne 0) { throw 'Terminal key metadata measurement failed.' }
& $bootstrapTool measure-metadata $upgradeKeyFile $upgradeKeyMetadataPath
if ($LASTEXITCODE -ne 0) { throw 'Upgrade key metadata measurement failed.' }
$terminalKeyMetadata = Get-Content -Raw -LiteralPath $terminalKeyMetadataPath | ConvertFrom-Json
$upgradeKeyMetadata = Get-Content -Raw -LiteralPath $upgradeKeyMetadataPath | ConvertFrom-Json
foreach ($keyMetadata in @($terminalKeyMetadata,$upgradeKeyMetadata)) {
    if ($keyMetadata.owner_sid -ne 'S-1-5-18' -or [long]$keyMetadata.hard_link_count -ne 1 -or $keyMetadata.volume_identity -ne $volumeIdentity -or @($keyMetadata.streams).Count -ne 1 -or $keyMetadata.streams[0] -ne '::$DATA') { throw 'Signing key metadata violates the governed physical-identity policy.' }
}
if ($upgradeKeyMetadata.security_descriptor_sha256 -ne [string]$bootstrap.key_file_acl_sha256) { throw 'Upgrade key ACL differs from the separately captured bootstrap identity.' }
$upgradeLedgerId = Get-StringHash ('R7_UPGRADE_LEDGER|' + $upgradeCertificateSha + '|899e4db2b5c0f4ad58a09c682324a2ee9e5d7e2f180822ce9300922e56741d52|' + $SourceCommit)

$zeroSha256 = '0000000000000000000000000000000000000000000000000000000000000000'
$componentRules = @(
    [ordered]@{ role='TERMINAL_SIGNER'; staging_relative_path='bin/RandleTerminalAuthority.exe'; final_path=(Join-Path $terminalInstallRoot 'RandleTerminalAuthority.exe'); sha256=$zeroSha256 },
    [ordered]@{ role='EXECUTION'; staging_relative_path='bin/RandleTerminalExecution.exe'; final_path=(Join-Path $terminalInstallRoot 'RandleTerminalExecution.exe'); sha256=$zeroSha256 },
    [ordered]@{ role='OBSERVATION'; staging_relative_path='bin/RandleTerminalObservation.exe'; final_path=(Join-Path $terminalInstallRoot 'RandleTerminalObservation.exe'); sha256=$zeroSha256 },
    [ordered]@{ role='COMPARATOR'; staging_relative_path='bin/RandleTerminalComparator.exe'; final_path=(Join-Path $terminalInstallRoot 'RandleTerminalComparator.exe'); sha256=$zeroSha256 },
    [ordered]@{ role='PUBLIC_VERIFIER'; staging_relative_path='bin/RandleTerminalPublicVerifier.exe'; final_path=(Join-Path $terminalInstallRoot 'RandleTerminalPublicVerifier.exe'); sha256=$zeroSha256 },
    [ordered]@{ role='AUTHORITY_VERIFIER'; staging_relative_path='bin/RandleTerminalAuthorityVerifier.exe'; final_path=(Join-Path $terminalInstallRoot 'RandleTerminalAuthorityVerifier.exe'); sha256=$zeroSha256 },
    [ordered]@{ role='ADVERSARIAL_HARNESS'; staging_relative_path='bin/RandleTerminalAdversarialHarness.exe'; final_path=(Join-Path $terminalInstallRoot 'RandleTerminalAdversarialHarness.exe'); sha256=$zeroSha256 },
    [ordered]@{ role='STATIC_VERIFIER'; staging_relative_path='bin/RandleTerminalStaticVerifier.exe'; final_path=(Join-Path $terminalInstallRoot 'RandleTerminalStaticVerifier.exe'); sha256=$zeroSha256 },
    [ordered]@{ role='TERMINAL_POLICY'; staging_relative_path='config/terminal_authority_v4_policy.json'; final_path=(Join-Path $terminalRemediationRoot 'Config\terminal_authority_v4_policy.json'); sha256=$zeroSha256 },
    [ordered]@{ role='DEPENDENCY_MANIFEST'; staging_relative_path='config/dependency_manifest.json'; final_path=(Join-Path $terminalRemediationRoot 'Config\dependency_manifest.json'); sha256=$zeroSha256 },
    [ordered]@{ role='BUILD_RECEIPT'; staging_relative_path='build/build_receipt.json'; final_path=(Join-Path $terminalRemediationRoot 'Build\build_receipt.json'); sha256=$zeroSha256 },
    [ordered]@{ role='INSTALLER_TOOL'; staging_relative_path='build/R7ArtifactTool.bootstrap.exe'; final_path=(Join-Path $terminalRemediationRoot 'Build\R7ArtifactTool.bootstrap.exe'); sha256=$zeroSha256 },
    [ordered]@{ role='AUTHORITY_PACKAGE_MANIFEST'; staging_relative_path='authority/authority_package_manifest.json'; final_path=(Join-Path $terminalRemediationRoot 'Authority\authority_package_manifest.json'); sha256=$zeroSha256 }
)
$upgradePolicyPath = Join-Path $output 'Generated\upgrade_authority_policy.placeholder.json'
$upgradePolicy = [ordered]@{
    artifact_type = 'R7_SEPARATE_UPGRADE_AUTHORITY_POLICY'
    bootstrap_authority = 'EXPLICIT_R7_ARCHITECTURE_REMEDIATION_AUTHORIZATION'
    dependency_manifest_sha256 = $dependencyManifestSha
    fixed_roots = @($upgradeInstallRoot, $upgradeStateRoot, $terminalInstallRoot, 'C:\ProgramData\RandleAI\TerminalAuthority')
    host_binding = [ordered]@{ terminal_ledger_id='899e4db2b5c0f4ad58a09c682324a2ee9e5d7e2f180822ce9300922e56741d52'; terminal_service_sid='S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948' }
    installer_script_sha256 = (Get-LowerHash (Join-Path $packageRoot 'install_authorized_transition.ps1'))
    interface_version = '1.0.0'
    key_unique_name = [string]$bootstrap.key_unique_name
    ledger_id = $upgradeLedgerId
    old_interface_version = '3.0.0-DRAFT'
    old_policy_sha256 = '76eb2900b2000aa0b41e6040335cc323f7443728aad21cd871d5b6b8e17bcd8b'
    old_service_binary_sha256 = '9ea829416f37c94db2858586fa5e0042652f6caa4637a29fdbefb513577a7526'
    operation_allowlist = @('ACTIVATE_TERMINAL_UPGRADE','AUTHORIZE_TERMINAL_UPGRADE','GET_ACTIVATION','GET_AUTHORIZATION','GET_UPGRADE_INTERACTION','GET_UPGRADE_STATUS','REVOKE_AUTHORIZATION')
    protocol_version = '4.0'
    public_certificate_sha256 = $upgradeCertificateSha
    required_components = $componentRules
    revoked_component_sha256 = @('76eb2900b2000aa0b41e6040335cc323f7443728aad21cd871d5b6b8e17bcd8b','9ea829416f37c94db2858586fa5e0042652f6caa4637a29fdbefb513577a7526')
    schema_version = '1.0.0'
    service_sid = 'S-1-5-80-238545627-4117296865-2677355104-248304369-1301198082'
    source_commit = $SourceCommit
    source_tree = $sourceTree
    threat_model = [ordered]@{ excludes=@('kernel','offline_administrator','physical_attack','TPM_or_HSM_claim'); protects=@('self_authorized_upgrade','component_substitution','downgrade','replay','cross_host_authorization') }
    upgrade_client_sha256 = $zeroSha256
    volume_identity = $volumeIdentity
}
Write-CanonicalJson $upgradePolicy $upgradePolicyPath $bootstrapTool
$upgradePolicySha = Get-LowerHash $upgradePolicyPath

$requirementSha = Get-LowerHash (Join-Path $packageRoot 'governed_requirement_registry.json')
$caseSha = Get-LowerHash (Join-Path $packageRoot 'immutable_case_definitions.json')
$expectationSha = Get-LowerHash (Join-Path $packageRoot 'immutable_expectations.json')
$coverageSha = Get-LowerHash (Join-Path $packageRoot 'exact_byte_coverage_proof.json')
$sourceManifestSha = Get-LowerHash (Join-Path $packageRoot 'AuthoritySources\authority_source_manifest.json')
$historicalClassificationSha = Get-LowerHash (Join-Path $packageRoot 'historical_classification_registry.json')
$identitySource = Join-Path $output 'Generated\R7BuildIdentity.g.cs'
$identityText = @"
namespace RandleAI.R7Remediation
{
    internal static class R7BuildIdentity
    {
        internal const string UpgradePolicySha256 = "$upgradePolicySha";
        internal const string UpgradePublicCertificateSha256 = "$upgradeCertificateSha";
        internal const string DependencyManifestSha256 = "$dependencyManifestSha";
        internal const string UpgradeBinaryPath = @"C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradeAuthority.exe";
        internal const string SourceCommit = "$SourceCommit";
        internal const string SourceTree = "$sourceTree";
        internal const string CaseDefinitionsSha256 = "$caseSha";
        internal const string ExpectationsSha256 = "$expectationSha";
        internal const string RequirementRegistrySha256 = "$requirementSha";
        internal const string CoverageProofSha256 = "$coverageSha";
        internal const string AuthoritySourceManifestSha256 = "$sourceManifestSha";
        internal const string HistoricalClassificationRegistrySha256 = "$historicalClassificationSha";
        internal const string ExecutionBinaryPath = @"C:\Program Files\RandleAI\TerminalAuthorityV4\RandleTerminalExecution.exe";
        internal const string ObservationBinaryPath = @"C:\Program Files\RandleAI\TerminalAuthorityV4\RandleTerminalObservation.exe";
        internal const string ComparatorBinaryPath = @"C:\Program Files\RandleAI\TerminalAuthorityV4\RandleTerminalComparator.exe";
        internal const string TerminalKeyFilePath = @"$terminalKeyFile";
        internal const string TerminalKeyFileIdentity = "$($terminalKeyMetadata.file_identity)";
        internal const string TerminalKeyFileOwnerSid = "$($terminalKeyMetadata.owner_sid)";
        internal const string TerminalKeyFileSecurityDescriptorSha256 = "$($terminalKeyMetadata.security_descriptor_sha256)";
        internal const string TerminalKeyFileVolumeIdentity = "$($terminalKeyMetadata.volume_identity)";
        internal const uint TerminalKeyFileLinkCount = $([uint32]$terminalKeyMetadata.hard_link_count);
        internal const string UpgradeKeyFilePath = @"$upgradeKeyFile";
        internal const string UpgradeKeyFileIdentity = "$($upgradeKeyMetadata.file_identity)";
        internal const string UpgradeKeyFileOwnerSid = "$($upgradeKeyMetadata.owner_sid)";
        internal const string UpgradeKeyFileSecurityDescriptorSha256 = "$($upgradeKeyMetadata.security_descriptor_sha256)";
        internal const string UpgradeKeyFileVolumeIdentity = "$($upgradeKeyMetadata.volume_identity)";
        internal const uint UpgradeKeyFileLinkCount = $([uint32]$upgradeKeyMetadata.hard_link_count);
    }
}
"@
[IO.File]::WriteAllText($identitySource, $identityText, [Text.UTF8Encoding]::new($false))

$targets = @(
    [ordered]@{ role='UPGRADE_AUTHORITY'; name='RandleTerminalUpgradeAuthority.exe'; main='RandleAI.R7Remediation.R7UpgradeServiceProgram'; define='' },
    [ordered]@{ role='UPGRADE_CLIENT'; name='RandleTerminalUpgradeClient.exe'; main='RandleAI.R7Remediation.R7UpgradeClientProgram'; define='' },
    [ordered]@{ role='TERMINAL_SIGNER'; name='RandleTerminalAuthority.exe'; main='RandleAI.R7Remediation.R7TerminalServiceProgram'; define='' },
    [ordered]@{ role='EXECUTION'; name='RandleTerminalExecution.exe'; main='RandleAI.R7Remediation.R7ExecutionServiceProgram'; define='EXECUTION_ROLE' },
    [ordered]@{ role='OBSERVATION'; name='RandleTerminalObservation.exe'; main='RandleAI.R7Remediation.R7ObservationServiceProgram'; define='OBSERVATION_ROLE' },
    [ordered]@{ role='COMPARATOR'; name='RandleTerminalComparator.exe'; main='RandleAI.R7Remediation.R7ComparatorServiceProgram'; define='COMPARATOR_ROLE' },
    [ordered]@{ role='PUBLIC_VERIFIER'; name='RandleTerminalPublicVerifier.exe'; main='RandleAI.R7Remediation.R7PublicVerifierProgram'; define='' },
    [ordered]@{ role='AUTHORITY_VERIFIER'; name='RandleTerminalAuthorityVerifier.exe'; main='RandleAI.R7Remediation.R7AuthorityVerifierProgram'; define='' },
    [ordered]@{ role='ADVERSARIAL_HARNESS'; name='RandleTerminalAdversarialHarness.exe'; main='RandleAI.R7Remediation.R7AdversarialHarnessProgram'; define='' },
    [ordered]@{ role='STATIC_VERIFIER'; name='RandleTerminalStaticVerifier.exe'; main='RandleAI.R7Remediation.R7StaticVerificationProgram'; define='INSTALLED_STATIC_ROLE' }
)
$initialTargets = @($targets | Where-Object { $_.role -ne 'UPGRADE_AUTHORITY' })
foreach ($target in $initialTargets) { Invoke-Compiler $target.main $target.define (Join-Path $output ('PassA\' + $target.name)) $identitySource }
Start-Sleep -Milliseconds 1100
foreach ($target in $initialTargets) { Invoke-Compiler $target.main $target.define (Join-Path $output ('PassB\' + $target.name)) $identitySource }

$binaryReceipts = [Collections.Generic.List[object]]::new()
$binaryReceipts.Add($bootstrapBinaryReceipt)
foreach ($target in $initialTargets) {
    $left = Join-Path $output ('PassA\' + $target.name); $right = Join-Path $output ('PassB\' + $target.name)
    $leftIl = Join-Path $output ('NormalizedIL\' + $target.name + '.pass-a.il'); $rightIl = Join-Path $output ('NormalizedIL\' + $target.name + '.pass-b.il')
    $leftIlSha = Get-NormalizedIl $left $leftIl; $rightIlSha = Get-NormalizedIl $right $rightIl
    if ($leftIlSha -ne $rightIlSha) { throw "Normalized IL mismatch for $($target.role)" }
    $receipt = [ordered]@{
        role=$target.role; file_name=$target.name; pass_a_sha256=(Get-LowerHash $left); pass_b_sha256=(Get-LowerHash $right);
        normalized_il_sha256=$leftIlSha; normalized_il_equal=$true; raw_difference=(Get-RawDifference $left $right); size=(Get-Item -LiteralPath $left).Length
    }
    $binaryReceipts.Add($receipt)
}

for ($closureIndex = 1; $closureIndex -lt $closureInputs.Count; $closureIndex++) {
    $postName = ([IO.Path]::GetFileNameWithoutExtension([string]$closureInputs[$closureIndex][2]) + '.post-use.json')
    $postPath = Join-Path $output ('Generated\BuildInputClosures\' + $postName)
    & $bootstrapTool directory-manifest ([IO.Path]::GetFullPath($closureInputs[$closureIndex][1])) $postPath
    if ($LASTEXITCODE -ne 0) { throw "Post-use build-input closure failed: $($closureInputs[$closureIndex][0])" }
    $postSha = Get-LowerHash $postPath
    if ($postSha -ne [string]$buildInputClosures[$closureIndex].manifest_raw_sha256) { throw "Build input changed while in use: $($closureInputs[$closureIndex][0])" }
    $buildInputClosures[$closureIndex].post_use_manifest_relative_path = 'BuildInputClosures/' + $postName
    $buildInputClosures[$closureIndex].post_use_raw_sha256 = $postSha
    $buildInputClosures[$closureIndex].stable_during_use = $true
}

$sourceReceipts = [Collections.Generic.List[object]]::new()
foreach ($source in $sourcePaths) {
    $relative = (Get-RelativePath $immutableRepositoryRoot $source).Replace('\','/')
    if (-not $commitBlobMap.ContainsKey($relative)) { throw "Source blob not bound in commit: $relative" }
    $sourceReceipts.Add([ordered]@{ path=$relative; blob=[string]$commitBlobMap[$relative]; raw_sha256=(Get-LowerHash $source); size=(Get-Item -LiteralPath $source).Length })
}
$developmentRelative = (Get-RelativePath $immutableRepositoryRoot $developmentIdentity).Replace('\','/')
if (-not $commitBlobMap.ContainsKey($developmentRelative)) { throw "Bootstrap identity blob not bound in commit: $developmentRelative" }
$sourceReceipts.Add([ordered]@{ path=$developmentRelative; blob=[string]$commitBlobMap[$developmentRelative]; raw_sha256=(Get-LowerHash $developmentIdentity); size=(Get-Item -LiteralPath $developmentIdentity).Length })
$sourceReceipts.Add([ordered]@{ path='GENERATED/R7BuildIdentity.g.cs'; blob='GENERATED_BUILD_INPUT'; raw_sha256=(Get-LowerHash $identitySource); size=(Get-Item -LiteralPath $identitySource).Length })

$governedScriptRegistryPath = Join-Path $packageRoot 'governed_script_registry.json'
$governedScriptRegistry = Get-Content -LiteralPath $governedScriptRegistryPath -Raw | ConvertFrom-Json
Assert-ExactPropertySet $governedScriptRegistry @('artifact_type','authority_classification','generated_from_current_bytes','schema_version','script_count','scripts','status') 'Governed script registry'
if ([string]$governedScriptRegistry.artifact_type -cne 'R7_GOVERNED_SCRIPT_REGISTRY' -or [int]$governedScriptRegistry.script_count -ne @($governedScriptRegistry.scripts).Count) { throw 'Governed script registry header is invalid.' }
$actualScriptNames = @(Get-ChildItem -LiteralPath $packageRoot -Filter '*.ps1' -File | ForEach-Object Name | Sort-Object)
$declaredScriptNames = @($governedScriptRegistry.scripts | ForEach-Object { Split-Path -Leaf ([string]$_.path) } | Sort-Object)
if (($actualScriptNames -join "`n") -cne ($declaredScriptNames -join "`n")) { throw 'Governed script registry does not equal the immutable package script set.' }
$governedScripts = [Collections.Generic.List[object]]::new()
foreach ($script in @($governedScriptRegistry.scripts | Sort-Object path)) {
    Assert-ExactPropertySet $script @('allowed_invocation_stages','authority_classification','dependencies','execution_class','git_blob_identity','mode','path','raw_sha256','role','size') ('Governed script ' + [string]$script.path)
    $scriptRelative = [string]$script.path
    if (-not $scriptRelative.StartsWith($packageRelativeRoot + '/', [StringComparison]::Ordinal) -or -not $commitBlobMap.ContainsKey($scriptRelative)) { throw "Governed script blob not bound in commit: $scriptRelative" }
    $scriptPath = Join-Path $immutableRepositoryRoot $scriptRelative.Replace('/','\')
    if ([string]$script.git_blob_identity -cne [string]$commitBlobMap[$scriptRelative] -or [string]$script.mode -cne [string]$commitModeMap[$scriptRelative] -or [string]$script.raw_sha256 -cne (Get-LowerHash $scriptPath) -or [long]$script.size -ne (Get-Item -LiteralPath $scriptPath).Length) { throw "Governed script registry identity mismatch: $scriptRelative" }
    $governedScripts.Add([ordered]@{allowed_invocation_stages=@($script.allowed_invocation_stages);authority_classification=[string]$script.authority_classification;dependencies=@($script.dependencies);execution_class=[string]$script.execution_class;git_blob_identity=[string]$script.git_blob_identity;mode=[string]$script.mode;path=$scriptRelative;raw_sha256=[string]$script.raw_sha256;role=[string]$script.role;size=[long]$script.size})
}

$buildReceiptPath = Join-Path $output 'Generated\build_receipt.json'
$compilerOptions = @('/noconfig','/target:exe','/platform:x64','/optimize+','/checked+','/debug-','/warn:4','/nostdlib+','/langversion:5','/filealign:512')
$buildReceipt = [ordered]@{
    artifact_type='R7_SOURCE_TO_BINARY_BUILD_RECEIPT'; architecture='x64'; binaries=$binaryReceipts.ToArray(); bootstrap_artifact_tool_sha256=(Get-LowerHash $bootstrapTool);
    build_input_closures=$buildInputClosures.ToArray(); compiler_options=$compilerOptions; dependency_manifest_sha256=$dependencyManifestSha; framework_reference_paths=$referencePaths; governed_scripts=$governedScripts.ToArray();
    governed_git=[ordered]@{environment=$gitEnvironment;executable_path=$gitExecutable;executable_sha256=$gitExecutableSha256;invocations=$governedGitInvocations.ToArray();runtime_authority='DENIED';source_bytes='RAW_CAT_FILE_BLOB_BYTES'};
    key_file_metadata=@([ordered]@{private_bytes_read=$false;role='TERMINAL_SIGNING_KEY';measurement=$terminalKeyMetadata},[ordered]@{private_bytes_read=$false;role='UPGRADE_SIGNING_KEY';measurement=$upgradeKeyMetadata}); schema_version='1.0.0';
    source_commit=$SourceCommit; source_files=$sourceReceipts.ToArray(); source_tree=$sourceTree; toolchain=$buildTools.ToArray()
}
Write-CanonicalJson $buildReceipt $buildReceiptPath $bootstrapTool
$buildReceiptSha = Get-LowerHash $buildReceiptPath

$binaryByRole = @{}; foreach ($row in $binaryReceipts) { $binaryByRole[$row.role] = $row }
$terminalComponents = @(
    [ordered]@{role='TERMINAL_SIGNER';path=(Join-Path $terminalInstallRoot 'RandleTerminalAuthority.exe');sha256=$binaryByRole.TERMINAL_SIGNER.pass_a_sha256},
    [ordered]@{role='EXECUTION';path=(Join-Path $terminalInstallRoot 'RandleTerminalExecution.exe');sha256=$binaryByRole.EXECUTION.pass_a_sha256},
    [ordered]@{role='OBSERVATION';path=(Join-Path $terminalInstallRoot 'RandleTerminalObservation.exe');sha256=$binaryByRole.OBSERVATION.pass_a_sha256},
    [ordered]@{role='COMPARATOR';path=(Join-Path $terminalInstallRoot 'RandleTerminalComparator.exe');sha256=$binaryByRole.COMPARATOR.pass_a_sha256},
    [ordered]@{role='PUBLIC_VERIFIER';path=(Join-Path $terminalInstallRoot 'RandleTerminalPublicVerifier.exe');sha256=$binaryByRole.PUBLIC_VERIFIER.pass_a_sha256},
    [ordered]@{role='AUTHORITY_VERIFIER';path=(Join-Path $terminalInstallRoot 'RandleTerminalAuthorityVerifier.exe');sha256=$binaryByRole.AUTHORITY_VERIFIER.pass_a_sha256},
    [ordered]@{role='ADVERSARIAL_HARNESS';path=(Join-Path $terminalInstallRoot 'RandleTerminalAdversarialHarness.exe');sha256=$binaryByRole.ADVERSARIAL_HARNESS.pass_a_sha256},
    [ordered]@{role='STATIC_VERIFIER';path=(Join-Path $terminalInstallRoot 'RandleTerminalStaticVerifier.exe');sha256=$binaryByRole.STATIC_VERIFIER.pass_a_sha256}
)
$terminalPolicyPath = Join-Path $output 'Generated\terminal_authority_v4_policy.json'
$terminalPolicy = [ordered]@{
    artifact_type='R7_TERMINAL_AUTHORITY_REMEDIATION_POLICY';
    authority_identities=[ordered]@{case_definitions_sha256=$caseSha;coverage_proof_sha256=$coverageSha;expectations_sha256=$expectationSha;requirement_registry_sha256=$requirementSha;source_manifest_sha256=$sourceManifestSha};
    build_receipt_sha256=$buildReceiptSha;
    caller_role_sids=[ordered]@{COMPARATOR='S-1-5-80-3174819085-3989415034-4266081362-372562941-1584450511';EXECUTION='S-1-5-80-2354876894-2467424667-1382161683-1170422623-3885682053';OBSERVATION='S-1-5-80-1455550362-116536141-3163605276-3265053646-3003707260';OPERATOR='S-1-5-21-4259795780-3461844753-1172372902-1001';SYSTEM='S-1-5-18';TERMINAL_SIGNER='S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948';UPGRADE_AUTHORITY='S-1-5-80-238545627-4117296865-2677355104-248304369-1301198082'};
    component_identities=$terminalComponents; dependency_manifest_sha256=$dependencyManifestSha;
    fixed_roots=@($terminalInstallRoot,$terminalRemediationRoot,'C:\ProgramData\RandleAI\TerminalAuthority\Ledger',$upgradeStateRoot,'C:\ProgramData\RandleAI\TerminalExecution\TestRoots\PublicVerifierProbes');
    historical_classification_policy=[ordered]@{default_rejected_v3_class='REJECTED_NONAUTHORITATIVE_CANDIDATE_EVIDENCE';retained_history_start_sequence=1;sequence_332_class='INCOMPLETE_ISSUANCE_SUPERSEDED_NONAUTHORITY';sequence_678_class='ABORTED_CLIENT_REJECTED_ISSUANCE_NONAUTHORITY'};
    interface_version='4.0.0-REMEDIATION';ledger_id='899e4db2b5c0f4ad58a09c682324a2ee9e5d7e2f180822ce9300922e56741d52';maximum_frame_bytes=65536;maximum_payload_bytes=65524;protocol_version='4.0';
    revoked_component_sha256=@('76eb2900b2000aa0b41e6040335cc323f7443728aad21cd871d5b6b8e17bcd8b','9ea829416f37c94db2858586fa5e0042652f6caa4637a29fdbefb513577a7526');schema_version='1.0.0';source_commit=$SourceCommit;source_tree=$sourceTree;
    terminal_public_key_identity=$terminalCertificateSha;terminal_service_sid='S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948';
    threat_model=[ordered]@{excludes=@('kernel','offline_administrator','physical_attack','TPM_or_HSM_claim');protects=@('hostile_child','parser_ambiguity','path_substitution','dependency_substitution','crash_recovery','historical_reinterpretation')};
    upgrade_public_certificate_sha256=$upgradeCertificateSha;volume_identity=$volumeIdentity
}
Write-CanonicalJson $terminalPolicy $terminalPolicyPath $bootstrapTool
$terminalPolicySha = Get-LowerHash $terminalPolicyPath

$staging = Join-Path $output 'Staging'
foreach ($target in $targets | Where-Object { $_.role -ne 'UPGRADE_AUTHORITY' -and $_.role -ne 'UPGRADE_CLIENT' }) { Copy-New (Join-Path $output ('PassA\' + $target.name)) (Join-Path $staging ('bin\' + $target.name)) }
Copy-New $terminalPolicyPath (Join-Path $staging 'config\terminal_authority_v4_policy.json')
Copy-New $dependencyManifestPath (Join-Path $staging 'config\dependency_manifest.json')
Copy-New $buildReceiptPath (Join-Path $staging 'build\build_receipt.json')
Copy-New $bootstrapTool (Join-Path $staging 'build\R7ArtifactTool.bootstrap.exe')
Copy-New $terminalKeyMetadataPath (Join-Path $staging 'build\terminal_key_file_metadata.json')
Copy-New $upgradeKeyMetadataPath (Join-Path $staging 'build\upgrade_key_file_metadata.json')
foreach ($closureFile in Get-ChildItem -LiteralPath (Join-Path $output 'Generated\BuildInputClosures') -File | Sort-Object Name) { Copy-New $closureFile.FullName (Join-Path $staging ('build\BuildInputClosures\' + $closureFile.Name)) }
foreach ($sourceReceipt in $sourceReceipts) {
    $sourceInput = if ([string]$sourceReceipt.blob -ceq 'GENERATED_BUILD_INPUT') { $identitySource } else { Join-Path $immutableRepositoryRoot ([string]$sourceReceipt.path).Replace('/','\') }
    if ((Get-LowerHash $sourceInput) -cne [string]$sourceReceipt.raw_sha256 -or (Get-Item -LiteralPath $sourceInput).Length -ne [long]$sourceReceipt.size) { throw "Terminal source input changed before staging: $($sourceReceipt.path)" }
    Copy-New $sourceInput (Join-Path $staging ('build\SourceInputs\' + ([string]$sourceReceipt.path).Replace('/','\')))
}
foreach ($governedScript in $governedScripts) {
    $scriptInput = Join-Path $immutableRepositoryRoot ([string]$governedScript.path).Replace('/','\')
    if ((Get-LowerHash $scriptInput) -cne [string]$governedScript.raw_sha256 -or (Get-Item -LiteralPath $scriptInput).Length -ne [long]$governedScript.size) { throw "Governed script changed before staging: $($governedScript.path)" }
    Copy-New $scriptInput (Join-Path $staging ('build\SourceInputs\' + ([string]$governedScript.path).Replace('/','\')))
}
foreach ($name in @('governed_requirement_registry.json','immutable_case_definitions.json','immutable_expectations.json','exact_byte_coverage_proof.json','historical_classification_registry.json','service_principal_registry.json','governed_script_registry.json','external_utility_registry.json','source_role_registry.json')) { Copy-New (Join-Path $packageRoot $name) (Join-Path $staging ('authority\' + $name)) }
New-Item -ItemType Directory -Path (Join-Path $staging 'authority\AuthoritySources') -Force | Out-Null
$authoritySourceBuildRoot = Join-Path $packageRoot 'AuthoritySources'
foreach ($file in Get-ChildItem -LiteralPath $authoritySourceBuildRoot -File -Recurse | Sort-Object FullName) {
    $sourceRelative = Get-RelativePath $authoritySourceBuildRoot $file.FullName
    Copy-New $file.FullName (Join-Path $staging ('authority\AuthoritySources\' + $sourceRelative))
}

$manifestRows = [Collections.Generic.List[object]]::new()
foreach ($file in Get-ChildItem -LiteralPath $staging -File -Recurse | Sort-Object FullName) {
    $relative = (Get-RelativePath $staging $file.FullName).Replace('\','/')
    $final = if ($relative.StartsWith('bin/')) { Join-Path $terminalInstallRoot $relative.Substring(4) } elseif ($relative.StartsWith('config/')) { Join-Path $terminalRemediationRoot ('Config\' + $relative.Substring(7)) } elseif ($relative.StartsWith('build/')) { Join-Path $terminalRemediationRoot ('Build\' + $relative.Substring(6)) } else { Join-Path $terminalRemediationRoot ('Authority\' + $relative.Substring(10).Replace('/','\')) }
    $manifestRows.Add([ordered]@{final_path=$final;raw_sha256=(Get-LowerHash $file.FullName);size=$file.Length;staging_relative_path=$relative})
}
$authorityManifestPath = Join-Path $output 'Generated\authority_package_manifest.json'
$authorityManifest = [ordered]@{artifact_type='R7_CONTENT_ADDRESSED_AUTHORITY_PACKAGE_MANIFEST';files=$manifestRows.ToArray();prohibited_source_commit='f0cfbce97e913a133530dd66a70326b1e03a0fb6';prohibited_source_dependency_count=0;schema_version='1.0.0';source_commit=$SourceCommit;source_tree=$sourceTree}
Write-CanonicalJson $authorityManifest $authorityManifestPath $bootstrapTool
$authorityManifestSha = Get-LowerHash $authorityManifestPath
Copy-New $authorityManifestPath (Join-Path $staging 'authority\authority_package_manifest.json')

$componentHashes = @{}
foreach ($rule in $componentRules) { $componentHashes[$rule.role] = Get-LowerHash (Join-Path $staging ($rule.staging_relative_path.Replace('/','\'))) }
$components = foreach ($rule in $componentRules) { [ordered]@{final_path=$rule.final_path;role=$rule.role;sha256=$componentHashes[$rule.role];staging_relative_path=$rule.staging_relative_path} }
$installerScript = Join-Path $packageRoot 'install_authorized_transition.ps1'
if (-not (Test-Path -LiteralPath $installerScript -PathType Leaf)) { throw 'Installer script is missing from the governed source package.' }
Copy-New $installerScript (Join-Path $output 'GovernedInstaller\install_authorized_transition.ps1')

# Finalize the non-circular upgrade policy from already-built terminal bytes,
# then compile the upgrade authority against that exact policy identity. The
# upgrade service therefore does not learn component hashes from its caller.
$upgradePolicy.required_components = $components
$upgradePolicy.upgrade_client_sha256 = $binaryByRole.UPGRADE_CLIENT.pass_a_sha256
$finalUpgradePolicyPath = Join-Path $output 'Generated\upgrade_authority_policy.json'
Write-CanonicalJson $upgradePolicy $finalUpgradePolicyPath $bootstrapTool
$upgradePolicySha = Get-LowerHash $finalUpgradePolicyPath
$upgradeIdentitySource = Join-Path $output 'Generated\R7UpgradeBuildIdentity.g.cs'
$baseIdentityText = [IO.File]::ReadAllText($identitySource, [Text.Encoding]::UTF8)
$oldPolicyConstant = 'internal const string UpgradePolicySha256 = "' + (Get-LowerHash $upgradePolicyPath) + '";'
$newPolicyConstant = 'internal const string UpgradePolicySha256 = "' + $upgradePolicySha + '";'
if (-not $baseIdentityText.Contains($oldPolicyConstant)) { throw 'Generated identity does not contain the placeholder upgrade-policy identity.' }
[IO.File]::WriteAllText($upgradeIdentitySource, $baseIdentityText.Replace($oldPolicyConstant, $newPolicyConstant), [Text.UTF8Encoding]::new($false))
$upgradeFinalA = Join-Path $output 'FinalPassA\RandleTerminalUpgradeAuthority.exe'
$upgradeFinalB = Join-Path $output 'FinalPassB\RandleTerminalUpgradeAuthority.exe'
Invoke-Compiler 'RandleAI.R7Remediation.R7UpgradeServiceProgram' '' $upgradeFinalA $upgradeIdentitySource
Start-Sleep -Milliseconds 1100
Invoke-Compiler 'RandleAI.R7Remediation.R7UpgradeServiceProgram' '' $upgradeFinalB $upgradeIdentitySource
$upgradeFinalIlA = Join-Path $output 'NormalizedIL\RandleTerminalUpgradeAuthority.final.pass-a.il'
$upgradeFinalIlB = Join-Path $output 'NormalizedIL\RandleTerminalUpgradeAuthority.final.pass-b.il'
$upgradeFinalIlShaA = Get-NormalizedIl $upgradeFinalA $upgradeFinalIlA
$upgradeFinalIlShaB = Get-NormalizedIl $upgradeFinalB $upgradeFinalIlB
if ($upgradeFinalIlShaA -ne $upgradeFinalIlShaB) { throw 'Normalized IL mismatch for final UPGRADE_AUTHORITY.' }
$upgradeFinalReceipt = [ordered]@{
    role='UPGRADE_AUTHORITY';file_name='RandleTerminalUpgradeAuthority.exe';pass_a_sha256=(Get-LowerHash $upgradeFinalA);pass_b_sha256=(Get-LowerHash $upgradeFinalB);
    normalized_il_sha256=$upgradeFinalIlShaA;normalized_il_equal=$true;raw_difference=(Get-RawDifference $upgradeFinalA $upgradeFinalB);size=(Get-Item -LiteralPath $upgradeFinalA).Length
}
$binaryByRole['UPGRADE_AUTHORITY'] = $upgradeFinalReceipt
$finalBuildInputClosures = [Collections.Generic.List[object]]::new()
for ($closureIndex = 1; $closureIndex -lt $closureInputs.Count; $closureIndex++) {
    $baseName = [IO.Path]::GetFileNameWithoutExtension([string]$closureInputs[$closureIndex][2])
    $finalName = $baseName + '.upgrade-final.json'
    $finalPath = Join-Path $output ('Generated\BuildInputClosures\' + $finalName)
    & $bootstrapTool directory-manifest ([IO.Path]::GetFullPath($closureInputs[$closureIndex][1])) $finalPath
    if ($LASTEXITCODE -ne 0) { throw "Final build-input closure failed: $($closureInputs[$closureIndex][0])" }
    $finalIdentity = Get-LowerHash $finalPath
    if ($finalIdentity -cne [string]$buildInputClosures[$closureIndex].manifest_raw_sha256) { throw "Build input changed during final upgrade-authority build: $($closureInputs[$closureIndex][0])" }
    $finalBuildInputClosures.Add([ordered]@{
        file_count=[long]$buildInputClosures[$closureIndex].file_count
        final_manifest_raw_sha256=$finalIdentity
        initial_manifest_raw_sha256=[string]$buildInputClosures[$closureIndex].manifest_raw_sha256
        manifest_relative_path=('BuildInputClosures/' + $finalName)
        role=[string]$closureInputs[$closureIndex][0]
        stable_during_use=$true
    })
}
$upgradeSourceReceipts = [Collections.Generic.List[object]]::new()
foreach ($sourceReceipt in $sourceReceipts) {
    if ([string]$sourceReceipt.blob -cne 'GENERATED_BUILD_INPUT') { $upgradeSourceReceipts.Add($sourceReceipt) }
}
$upgradeSourceReceipts.Add([ordered]@{path='GENERATED/R7UpgradeBuildIdentity.g.cs';blob='GENERATED_BUILD_INPUT';raw_sha256=(Get-LowerHash $upgradeIdentitySource);size=(Get-Item -LiteralPath $upgradeIdentitySource).Length})
$upgradeAuthorityBuildReceiptPath = Join-Path $output 'Generated\upgrade_authority_build_receipt.json'
$upgradeAuthorityBuildReceipt = [ordered]@{
    artifact_type='R7_UPGRADE_AUTHORITY_SOURCE_TO_BINARY_BUILD_RECEIPT';binary=$upgradeFinalReceipt;compiler_options=$compilerOptions;
    dependency_manifest_sha256=$dependencyManifestSha;final_build_input_closures=$finalBuildInputClosures.ToArray();generated_identity_sha256=(Get-LowerHash $upgradeIdentitySource);governed_scripts=$governedScripts.ToArray();
    schema_version='1.0.0';source_commit=$SourceCommit;source_tree=$sourceTree;source_files=$upgradeSourceReceipts.ToArray();toolchain=$buildTools.ToArray();upgrade_policy_sha256=$upgradePolicySha
}
Write-CanonicalJson $upgradeAuthorityBuildReceipt $upgradeAuthorityBuildReceiptPath $bootstrapTool

Copy-New $upgradeFinalA (Join-Path $output 'UpgradeBootstrap\RandleTerminalUpgradeAuthority.exe')
Copy-New (Join-Path $output 'PassA\RandleTerminalUpgradeClient.exe') (Join-Path $output 'UpgradeBootstrap\RandleTerminalUpgradeClient.exe')
Copy-New $finalUpgradePolicyPath (Join-Path $output 'UpgradeBootstrap\upgrade_authority_policy.json')
Copy-New $upgradeAuthorityBuildReceiptPath (Join-Path $output 'UpgradeBootstrap\upgrade_authority_build_receipt.json')
Copy-New $dependencyManifestPath (Join-Path $output 'UpgradeBootstrap\dependency_manifest.json')
Copy-New $UpgradePublicCertificate (Join-Path $output 'UpgradeBootstrap\upgrade_authority_public.cer')
foreach ($closure in $finalBuildInputClosures) {
    $relative = [string]$closure.manifest_relative_path
    Copy-New (Join-Path $output ('Generated\' + $relative.Replace('/','\'))) (Join-Path $output ('UpgradeBootstrap\' + $relative.Replace('/','\')))
}
foreach ($sourceReceipt in $upgradeSourceReceipts) {
    $sourceInput = if ([string]$sourceReceipt.blob -ceq 'GENERATED_BUILD_INPUT') { $upgradeIdentitySource } else { Join-Path $immutableRepositoryRoot ([string]$sourceReceipt.path).Replace('/','\') }
    if ((Get-LowerHash $sourceInput) -cne [string]$sourceReceipt.raw_sha256 -or (Get-Item -LiteralPath $sourceInput).Length -ne [long]$sourceReceipt.size) { throw "Upgrade source input changed before staging: $($sourceReceipt.path)" }
    Copy-New $sourceInput (Join-Path $output ('UpgradeBootstrap\SourceInputs\' + ([string]$sourceReceipt.path).Replace('/','\')))
}
foreach ($governedScript in $governedScripts) {
    $scriptInput = Join-Path $immutableRepositoryRoot ([string]$governedScript.path).Replace('/','\')
    Copy-New $scriptInput (Join-Path $output ('UpgradeBootstrap\SourceInputs\' + ([string]$governedScript.path).Replace('/','\')))
}

$transitionTemplatePath = Join-Path $output 'Generated\transition_request_template.json'
$transitionTemplate = [ordered]@{
    build_receipt_sha256=$buildReceiptSha;components=$components;dependency_manifest_sha256=$dependencyManifestSha;
    host_binding=[ordered]@{terminal_ledger_id='899e4db2b5c0f4ad58a09c682324a2ee9e5d7e2f180822ce9300922e56741d52';terminal_service_sid='S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948';volume_identity=$volumeIdentity};
    installer_identity=[ordered]@{executable_sha256=$binaryByRole.UPGRADE_CLIENT.pass_a_sha256;script_sha256=(Get-LowerHash $installerScript)};
    new_interface_version='4.0.0-REMEDIATION';old_interface_version='3.0.0-DRAFT';old_policy_sha256='76eb2900b2000aa0b41e6040335cc323f7443728aad21cd871d5b6b8e17bcd8b';old_service_binary_sha256='9ea829416f37c94db2858586fa5e0042652f6caa4637a29fdbefb513577a7526';
    rollback_constraints='PRESERVE_LEDGER_CONTINUITY;PRESERVE_ALL_HISTORICAL_EVIDENCE;REQUIRE_SIGNED_ROLLBACK_AUTHORIZATION;NO_V1_OR_REJECTED_V3_DOWNGRADE';
    source_commit=$SourceCommit;source_tree=$sourceTree;staging_root='SET_BY_GOVERNED_INSTALLER';transition_nonce='SET_BY_GOVERNED_INSTALLER'
}
Write-CanonicalJson $transitionTemplate $transitionTemplatePath $bootstrapTool

$summaryPath = Join-Path $output 'build_summary.json'
$summary = [ordered]@{
    artifact_type='R7_REMEDIATION_BUILD_SUMMARY';authority_package_manifest_sha256=$authorityManifestSha;build_receipt_sha256=$buildReceiptSha;case_definitions_sha256=$caseSha;
    dependency_manifest_sha256=$dependencyManifestSha;expectations_sha256=$expectationSha;installer_script_sha256=(Get-LowerHash $installerScript);interface_version='4.0.0-REMEDIATION';prohibited_source_dependency_count=0;requirement_registry_sha256=$requirementSha;
    schema_version='1.0.0';source_commit=$SourceCommit;source_tree=$sourceTree;terminal_policy_sha256=$terminalPolicySha;upgrade_authority_build_receipt_sha256=(Get-LowerHash $upgradeAuthorityBuildReceiptPath);upgrade_binary_sha256=$binaryByRole.UPGRADE_AUTHORITY.pass_a_sha256;
    upgrade_ledger_id=$upgradeLedgerId;upgrade_policy_sha256=$upgradePolicySha;upgrade_public_certificate_sha256=$upgradeCertificateSha
}
Write-CanonicalJson $summary $summaryPath $bootstrapTool
Write-Output ([ordered]@{output_root=$output;summary_sha256=(Get-LowerHash $summaryPath);source_commit=$SourceCommit;source_tree=$sourceTree} | ConvertTo-Json)
