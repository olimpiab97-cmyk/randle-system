[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repositoryRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$hostUrl = "http://127.0.0.1:7100"
$healthUrl = "$hostUrl/health"
$controlAuthorityPath = Join-Path $repositoryRoot "Architecture\Command_Center\command_center_governed_service_manifest.json"

function Resolve-CommandCenterControlVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,
        [Parameter(Mandatory = $true)]
        [string]$AuthorityPath
    )

    if (-not (Test-Path -LiteralPath $AuthorityPath -PathType Leaf)) {
        throw "control_version_authority_missing"
    }
    try {
        $authority = Get-Content -LiteralPath $AuthorityPath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw "control_version_authority_malformed"
    }
    [string]$version = $authority.control_version
    if ([string]::IsNullOrWhiteSpace($version) -or $version -cnotmatch '^command_center_service_controls_r[1-9][0-9]*[a-z]?$') {
        throw "control_version_authority_invalid"
    }

    $expectedSourcePaths = @("command_center_service_control.py", "command_center_host.py", "open_command_center.cmd", "open_command_center.ps1")
    $sourceAuthority = $authority.control_generation.source_sha256
    if ($null -eq $sourceAuthority) {
        throw "control_generation_authority_missing"
    }
    $actualSourcePaths = @($sourceAuthority.PSObject.Properties.Name)
    if ($actualSourcePaths.Count -ne $expectedSourcePaths.Count -or @($expectedSourcePaths | Where-Object { $_ -notin $actualSourcePaths }).Count -ne 0) {
        throw "control_generation_authority_invalid"
    }
    $rootPrefix = [IO.Path]::GetFullPath($RepositoryRoot).TrimEnd('\') + '\'
    foreach ($relativePath in $expectedSourcePaths) {
        [string]$expectedHash = $sourceAuthority.$relativePath
        if ($expectedHash -cnotmatch '^[0-9a-f]{64}$') {
            throw "control_generation_hash_invalid"
        }
        $sourcePath = [IO.Path]::GetFullPath((Join-Path $RepositoryRoot $relativePath))
        if (-not $sourcePath.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
            throw "control_generation_source_unavailable"
        }
        $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourcePath -ErrorAction Stop).Hash.ToLowerInvariant()
        if ($actualHash -cne $expectedHash) {
            throw "control_generation_source_mismatch"
        }
    }

    $requiredPaths = @($authority.runtime_deployment.required_paths | ForEach-Object { ([string]$_).Replace('\', '/') })
    $rollbackPaths = @($authority.runtime_deployment.rollback_required_paths | ForEach-Object { ([string]$_).Replace('\', '/') })
    $authorityRelativePath = "Architecture/Command_Center/command_center_governed_service_manifest.json"
    if ($requiredPaths.Count -eq 0 -or $requiredPaths.Count -ne $rollbackPaths.Count -or
        @($requiredPaths | Where-Object { $_ -notin $rollbackPaths }).Count -ne 0 -or
        $authorityRelativePath -notin $requiredPaths -or
        @($expectedSourcePaths | Where-Object { $_ -notin $requiredPaths }).Count -ne 0) {
        throw "control_runtime_deployment_authority_invalid"
    }
    return [string]$version
}

try {
    [string]$expectedVersion = Resolve-CommandCenterControlVersion -RepositoryRoot $repositoryRoot -AuthorityPath $controlAuthorityPath
}
catch {
    throw (("COMMAND CENTER NOT STARTED {0} CONTROL VERSION AUTHORITY UNRESOLVED. Detail: {1}" -f [char]0x2014, $_.Exception.Message))
}
if (-not $env:RANDLE_DATA_ROOT) {
    throw "RANDLE_DATA_ROOT is required for governed Command Center production authority."
}
$runtimeRoot = [IO.Path]::GetFullPath($env:RANDLE_DATA_ROOT)
$logRoot = Join-Path $runtimeRoot "command_center"
$stdoutPath = Join-Path $logRoot "host.stdout.log"
$stderrPath = Join-Path $logRoot "host.stderr.log"
$pythonResolverPath = Join-Path $repositoryRoot "resolve_python_runtime.ps1"
$pythonManifestPath = $controlAuthorityPath
if (-not (Test-Path -LiteralPath $pythonResolverPath -PathType Leaf)) {
    throw ("COMMAND CENTER NOT STARTED {0} PYTHON RUNTIME AUTHORITY UNRESOLVED. Resolver source is missing." -f [char]0x2014)
}
. $pythonResolverPath
$environmentAuthority = Repair-RandleProcessEnvironmentKeyCasing

foreach ($root in @($runtimeRoot, (Join-Path $runtimeRoot "tv_context_spool"), (Join-Path $runtimeRoot "entry_agent"), $logRoot)) {
    New-Item -ItemType Directory -Path $root -Force | Out-Null
    $probe = Join-Path $root (".command-center-host-write-probe-{0}.tmp" -f [Guid]::NewGuid().ToString("N"))
    try {
        [IO.File]::WriteAllText($probe, "command-center-production-write-authority`n", [Text.UTF8Encoding]::new($false))
        if ([IO.File]::ReadAllText($probe, [Text.Encoding]::UTF8) -ne "command-center-production-write-authority`n") {
            throw "write_probe_readback_mismatch"
        }
    }
    finally {
        Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
    }
}

function Get-CommandCenterHealth {
    try {
        return Invoke-RestMethod -Method Get -Uri $healthUrl -TimeoutSec 2 -ErrorAction Stop
    }
    catch {
        return $null
    }
}

$health = Get-CommandCenterHealth
if ($health) {
    if ($health.ok -ne $true -or $health.service -ne "command_center_host" -or $health.version -ne $expectedVersion -or [IO.Path]::GetFullPath([string]$health.repository_root) -ne $repositoryRoot) {
        throw "Port 7100 is occupied by a foreign or source-mismatched Command Center host."
    }
}
else {
    try {
        [string]$python = Resolve-RandlePythonExecutable -RepositoryRoot $repositoryRoot -ManifestPath $pythonManifestPath
    }
    catch {
        throw (("COMMAND CENTER NOT STARTED {0} PYTHON RUNTIME AUTHORITY UNRESOLVED. Expected Python 3.12 x64; configure RANDLE_PYTHON_EXE or install the governed Python launcher. Detail: {1}" -f [char]0x2014, $_.Exception.Message))
    }
    if ([string]::IsNullOrWhiteSpace($python) -or -not [IO.Path]::IsPathRooted($python) -or -not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw ("COMMAND CENTER NOT STARTED {0} PYTHON RUNTIME AUTHORITY UNRESOLVED. Resolver did not return one absolute executable path." -f [char]0x2014)
    }
    $hostScript = Join-Path $repositoryRoot "command_center_host.py"
    Start-Process -FilePath ([string]$python) `
        -ArgumentList @($hostScript, "--host", "127.0.0.1", "--port", "7100") `
        -WorkingDirectory $repositoryRoot `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -WindowStyle Hidden | Out-Null

    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        Start-Sleep -Milliseconds 200
        $health = Get-CommandCenterHealth
    } while (-not $health -and [DateTime]::UtcNow -lt $deadline)

    if (-not $health -or $health.ok -ne $true -or $health.version -ne $expectedVersion) {
        throw "Command Center host did not become ready. Review the nonsecret host logs under the governed runtime data root."
    }
}

if ($env:RANDLE_COMMAND_CENTER_NO_BROWSER -ne "1") {
    Start-Process $hostUrl | Out-Null
}
