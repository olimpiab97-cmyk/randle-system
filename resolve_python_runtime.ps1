Set-StrictMode -Version 2.0

function Repair-RandleProcessEnvironmentKeyCasing {
    [CmdletBinding()]
    param()

    $variables = [Environment]::GetEnvironmentVariables("Process")
    $groups = @{}
    foreach ($rawKey in @($variables.Keys)) {
        $key = [string]$rawKey
        $normalized = $key.ToUpperInvariant()
        if (-not $groups.ContainsKey($normalized)) {
            $groups[$normalized] = New-Object System.Collections.Generic.List[string]
        }
        $groups[$normalized].Add($key)
    }
    $repaired = New-Object System.Collections.Generic.List[string]
    foreach ($normalized in @($groups.Keys | Sort-Object)) {
        $keys = @($groups[$normalized])
        if ($keys.Count -le 1) { continue }
        if ($normalized -eq "PATH") {
            $orderedKeys = @($keys | Sort-Object @{ Expression = { if ($_ -ceq "Path") { 0 } else { 1 } } }, @{ Expression = { $_ } })
            $segments = New-Object System.Collections.Generic.List[string]
            $seen = @{}
            foreach ($key in $orderedKeys) {
                foreach ($segment in ([string]$variables[$key]).Split(";")) {
                    $trimmed = $segment.Trim()
                    if ([string]::IsNullOrWhiteSpace($trimmed)) { continue }
                    $segmentKey = $trimmed.ToUpperInvariant()
                    if (-not $seen.ContainsKey($segmentKey)) {
                        $seen[$segmentKey] = $true
                        $segments.Add($trimmed)
                    }
                }
            }
            $value = $segments -join ";"
            $canonicalKey = "Path"
        }
        else {
            $values = @($keys | ForEach-Object { [string]$variables[$_] } | Select-Object -Unique)
            if ($values.Count -ne 1) {
                throw "process_environment_authority_unresolved:duplicate_key=$normalized"
            }
            $value = [string]$values[0]
            $canonicalKey = [string](@($keys | Sort-Object)[0])
        }
        foreach ($key in $keys) {
            [Environment]::SetEnvironmentVariable($key, $null, "Process")
        }
        [Environment]::SetEnvironmentVariable($canonicalKey, $value, "Process")
        $repaired.Add($normalized)
    }
    return [PSCustomObject]@{ Ok = $true; RepairedKeys = @($repaired) }
}

function Get-RandlePythonRuntimeContract {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,

        [string]$ManifestPath = ""
    )

    $root = [IO.Path]::GetFullPath($RepositoryRoot)
    if ([string]::IsNullOrWhiteSpace($ManifestPath)) {
        $ManifestPath = Join-Path $root "Architecture\Command_Center\command_center_governed_service_manifest.json"
    }
    $manifest = Get-Content -LiteralPath $ManifestPath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    $runtime = $manifest.python_runtime
    if ($null -eq $runtime) {
        throw "python_runtime_contract_missing"
    }
    $modules = @($runtime.required_modules | ForEach-Object { [string]$_ })
    if ($modules.Count -eq 0) {
        throw "python_runtime_required_modules_missing"
    }
    return [PSCustomObject]@{
        Major = [int]$runtime.major
        Minor = [int]$runtime.minor
        ArchitectureBits = [int]$runtime.architecture_bits
        RequiredModules = $modules
        ConfigurationVariable = [string]$runtime.configuration_variable
        LauncherName = [string]$runtime.windows_launcher
    }
}

function Get-RandleNormalizedExecutablePaths {
    [CmdletBinding()]
    param([AllowNull()][string[]]$Paths)

    $seen = @{}
    foreach ($candidate in @($Paths)) {
        if ([string]::IsNullOrWhiteSpace([string]$candidate)) { continue }
        try {
            $full = [IO.Path]::GetFullPath([string]$candidate)
        }
        catch { continue }
        $key = $full.ToUpperInvariant()
        if (-not $seen.ContainsKey($key)) {
            $seen[$key] = $true
            Write-Output $full
        }
    }
}

function Test-RandlePythonCandidate {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,

        [Parameter(Mandatory = $true)]
        [object]$Contract,

        [scriptblock]$ProbeScript
    )

    try {
        $full = [IO.Path]::GetFullPath($Path)
        $item = Get-Item -LiteralPath $full -Force -ErrorAction Stop
    }
    catch {
        return [PSCustomObject]@{ Ok = $false; Path = $Path; Reason = "candidate_missing" }
    }
    if ($item.PSIsContainer) {
        return [PSCustomObject]@{ Ok = $false; Path = $full; Reason = "candidate_not_file" }
    }
    $isStoreAlias = $full -match '(?i)\\Microsoft\\WindowsApps\\' -or
        [int64]$item.Length -eq 0 -or
        (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)
    if ($isStoreAlias) {
        return [PSCustomObject]@{ Ok = $false; Path = $full; Reason = "windows_store_alias_rejected" }
    }

    if ($ProbeScript) {
        $probe = & $ProbeScript $full ([IO.Path]::GetFullPath($RepositoryRoot)) $Contract
        if ($null -eq $probe) {
            return [PSCustomObject]@{ Ok = $false; Path = $full; Reason = "probe_no_result" }
        }
        return $probe
    }

    $modulesArgument = @($Contract.RequiredModules) -join ";"
    $probeCode = @'
import importlib, json, os, platform, struct, sys
root = os.path.abspath(sys.argv[2])
modules = [value for value in sys.argv[3].split(";") if value]
sys.path.insert(0, root)
for module in modules:
    importlib.import_module(module)
print(json.dumps({
    "executable": os.path.abspath(sys.executable),
    "major": sys.version_info.major,
    "minor": sys.version_info.minor,
    "bits": struct.calcsize("P") * 8,
    "machine": platform.machine(),
    "modules": modules,
    }))
'@
    $probeEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($probeCode))
    try {
        $output = @(& $full -I -c "import base64,sys;exec(base64.b64decode(sys.argv[1]))" $probeEncoded ([IO.Path]::GetFullPath($RepositoryRoot)) $modulesArgument 2>$null)
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0 -or $output.Count -eq 0) {
            return [PSCustomObject]@{ Ok = $false; Path = $full; Reason = "required_module_or_runtime_probe_failed" }
        }
        $payload = [string]$output[-1] | ConvertFrom-Json -ErrorAction Stop
        $reported = [IO.Path]::GetFullPath([string]$payload.executable)
    }
    catch {
        return [PSCustomObject]@{ Ok = $false; Path = $full; Reason = "required_module_or_runtime_probe_failed" }
    }
    if ([int]$payload.major -ne [int]$Contract.Major -or [int]$payload.minor -ne [int]$Contract.Minor) {
        return [PSCustomObject]@{ Ok = $false; Path = $full; Reason = "unsupported_python_version" }
    }
    if ([int]$payload.bits -ne [int]$Contract.ArchitectureBits) {
        return [PSCustomObject]@{ Ok = $false; Path = $full; Reason = "unsupported_python_architecture" }
    }
    if ($reported -ne $full) {
        return [PSCustomObject]@{ Ok = $false; Path = $full; Reason = "interpreter_identity_mismatch" }
    }
    return [PSCustomObject]@{
        Ok = $true
        Path = [string]$full
        Reason = "python_runtime_contract_pass"
        Major = [int]$payload.major
        Minor = [int]$payload.minor
        ArchitectureBits = [int]$payload.bits
        Machine = [string]$payload.machine
    }
}

function Select-RandleValidatedPythonCandidate {
    [CmdletBinding()]
    param(
        [AllowNull()][string[]]$CandidatePaths,

        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,

        [Parameter(Mandatory = $true)]
        [object]$Contract,

        [scriptblock]$ProbeScript,

        [string]$AuthorityName = "candidate"
    )

    $valid = New-Object System.Collections.Generic.List[object]
    foreach ($candidate in @(Get-RandleNormalizedExecutablePaths -Paths $CandidatePaths)) {
        $probe = Test-RandlePythonCandidate -Path $candidate -RepositoryRoot $RepositoryRoot -Contract $Contract -ProbeScript $ProbeScript
        if ($probe.Ok -eq $true) { $valid.Add($probe) }
    }
    if ($valid.Count -ne 1) {
        throw "python_runtime_authority_unresolved:$AuthorityName`:validated_candidate_count=$($valid.Count)"
    }
    return [string]$valid[0].Path
}

function Resolve-RandlePythonExecutable {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,

        [string]$ManifestPath = "",

        [scriptblock]$ProbeScript
    )

    $contract = Get-RandlePythonRuntimeContract -RepositoryRoot $RepositoryRoot -ManifestPath $ManifestPath
    $configured = [Environment]::GetEnvironmentVariable($contract.ConfigurationVariable, "Process")
    if ([string]::IsNullOrWhiteSpace($configured)) {
        $configured = [Environment]::GetEnvironmentVariable($contract.ConfigurationVariable, "User")
    }
    if ([string]::IsNullOrWhiteSpace($configured)) {
        $configured = [Environment]::GetEnvironmentVariable($contract.ConfigurationVariable, "Machine")
    }
    if (-not [string]::IsNullOrWhiteSpace($configured)) {
        return [string](Select-RandleValidatedPythonCandidate -CandidatePaths @($configured) -RepositoryRoot $RepositoryRoot -Contract $contract -ProbeScript $ProbeScript -AuthorityName "configured")
    }

    $launcherCandidates = New-Object System.Collections.Generic.List[string]
    $launchers = @(Get-Command $contract.LauncherName -All -CommandType Application -ErrorAction SilentlyContinue)
    foreach ($launcher in @(Get-RandleNormalizedExecutablePaths -Paths @($launchers | ForEach-Object { $_.Source }))) {
        try {
            $resolved = @(& $launcher ("-{0}.{1}" -f $contract.Major, $contract.Minor) -c "import os,sys; print(os.path.abspath(sys.executable))" 2>$null)
            if ($LASTEXITCODE -eq 0 -and $resolved.Count -gt 0) {
                $launcherCandidates.Add([string]$resolved[-1])
            }
        }
        catch { }
    }
    if ($launcherCandidates.Count -gt 0) {
        return [string](Select-RandleValidatedPythonCandidate -CandidatePaths $launcherCandidates.ToArray() -RepositoryRoot $RepositoryRoot -Contract $contract -ProbeScript $ProbeScript -AuthorityName "windows_launcher")
    }

    $commands = @(Get-Command python.exe -All -CommandType Application -ErrorAction SilentlyContinue)
    return [string](Select-RandleValidatedPythonCandidate -CandidatePaths @($commands | ForEach-Object { $_.Source }) -RepositoryRoot $RepositoryRoot -Contract $contract -ProbeScript $ProbeScript -AuthorityName "validated_path")
}
