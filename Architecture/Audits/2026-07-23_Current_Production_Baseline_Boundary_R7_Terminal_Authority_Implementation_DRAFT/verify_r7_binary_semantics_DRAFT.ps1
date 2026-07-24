[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ReferenceRoot,
    [Parameter(Mandatory=$true)][string]$RebuildRoot,
    [Parameter(Mandatory=$true)][string]$OutputPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$reference = [IO.Path]::GetFullPath($ReferenceRoot)
$rebuild = [IO.Path]::GetFullPath($RebuildRoot)
$output = [IO.Path]::GetFullPath($OutputPath)
$temporaryRoot = [IO.Path]::GetFullPath($env:TEMP).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
foreach ($path in @($reference,$rebuild,$output)) {
    if (-not $path.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'SEMANTIC_VERIFICATION_PATH_OUTSIDE_TEMP' }
}
if (-not (Test-Path -LiteralPath $reference -PathType Container) -or -not (Test-Path -LiteralPath $rebuild -PathType Container)) { throw 'BINARY_ROOT_MISSING' }
if (Test-Path -LiteralPath $output) { throw 'SEMANTIC_OUTPUT_EXISTS' }

$ildasm = 'C:\Program Files (x86)\Microsoft SDKs\Windows\v10.0A\bin\NETFX 4.8 Tools\x64\ildasm.exe'
$compiler = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$expectedCompiler = 'adeda78a951529462f9411e016c1a1b87ddfd94c55912cbd2957817f39929af1'

function Get-LowerSha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-TextSha256([string]$Value) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash([Text.UTF8Encoding]::new($false).GetBytes($Value))).Replace('-','').ToLowerInvariant()) }
    finally { $algorithm.Dispose() }
}

function Get-NormalizedIl([string]$Path) {
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $ildasm
    $start.Arguments = '/text /nobar /tokens /bytes "' + $Path.Replace('"','\"') + '"'
    $start.CreateNoWindow = $true
    $start.RedirectStandardError = $true
    $start.RedirectStandardOutput = $true
    $start.UseShellExecute = $false
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    if (-not $process.Start()) { throw 'ILDASM_START_FAILED' }
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(120000)) { try { $process.Kill() } catch { }; throw 'ILDASM_TIMEOUT' }
    $process.WaitForExit()
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    $exitCode = $process.ExitCode
    $process.Dispose()
    if ($exitCode -ne 0 -or -not [string]::IsNullOrWhiteSpace($stderr)) { throw "ILDASM_REJECTED:${exitCode}:$stderr" }
    $lines = [Regex]::Split($stdout, '\r?\n') | Where-Object { $_ -notmatch '^// (MVID|Image base):' }
    return ($lines -join "`n")
}

if ((Get-LowerSha256 $compiler) -cne $expectedCompiler) { throw 'SEMANTIC_COMPILER_IDENTITY' }

$binaries = @(
    [pscustomobject]@{ Name='RandleTerminalAuthority.exe'; Installed='C:\Program Files\RandleAI\TerminalAuthority\RandleTerminalAuthority.exe' },
    [pscustomobject]@{ Name='RandleTerminalAuthorityR7Worker.exe'; Installed='C:\Program Files\RandleAI\TerminalAuthority\RandleTerminalAuthorityR7Worker.exe' },
    [pscustomobject]@{ Name='RandleTerminalAuthorityR7Client.exe'; Installed='C:\Program Files\RandleAI\TerminalAuthority\RandleTerminalAuthorityR7Client.exe' },
    [pscustomobject]@{ Name='RandleTerminalAuthorityR7PublicVerifier.exe'; Installed='C:\Program Files\RandleAI\TerminalAuthority\RandleTerminalAuthorityR7PublicVerifier.exe' },
    [pscustomobject]@{ Name='RandleTerminalAuthorityR7AdversarialProbe.exe'; Installed=$null },
    [pscustomobject]@{ Name='RandleTerminalAuthorityR7FixtureHost.exe'; Installed='C:\Program Files\RandleAI\TerminalAuthority\R7ExecutionSubject\powershell.exe' },
    [pscustomobject]@{ Name='RandleTerminalAuthorityR7SubjectLauncher.exe'; Installed='C:\Program Files\RandleAI\TerminalAuthority\RandleTerminalAuthorityR7SubjectLauncher.exe' }
)

$rows = @()
foreach ($binary in $binaries) {
    $referencePath = Join-Path $reference $binary.Name
    $rebuildPath = Join-Path $rebuild $binary.Name
    if (-not (Test-Path -LiteralPath $referencePath -PathType Leaf) -or -not (Test-Path -LiteralPath $rebuildPath -PathType Leaf)) { throw "BINARY_MISSING:$($binary.Name)" }
    $referenceIl = Get-NormalizedIl $referencePath
    $rebuildIl = Get-NormalizedIl $rebuildPath
    $referenceIlHash = Get-TextSha256 $referenceIl
    $rebuildIlHash = Get-TextSha256 $rebuildIl
    if ($referenceIlHash -cne $rebuildIlHash -or $referenceIl -cne $rebuildIl) { throw "SEMANTIC_IL_MISMATCH:$($binary.Name)" }
    $referenceHash = Get-LowerSha256 $referencePath
    $installedHash = $null
    if ($null -ne $binary.Installed) {
        if (-not (Test-Path -LiteralPath $binary.Installed -PathType Leaf)) { throw "INSTALLED_BINARY_MISSING:$($binary.Name)" }
        $installedHash = Get-LowerSha256 $binary.Installed
        if ($installedHash -cne $referenceHash) { throw "INSTALLED_REFERENCE_MISMATCH:$($binary.Name)" }
    }
    if ((Get-Item -LiteralPath $referencePath).Length -ne (Get-Item -LiteralPath $rebuildPath).Length) { throw "REBUILD_SIZE_MISMATCH:$($binary.Name)" }
    $rows += [ordered]@{
        installed_path = $binary.Installed
        installed_sha256 = $installedHash
        name = $binary.Name
        normalized_il_sha256 = $referenceIlHash
        reference_sha256 = $referenceHash
        rebuild_sha256 = Get-LowerSha256 $rebuildPath
        semantic_equality = $true
        size = (Get-Item -LiteralPath $referencePath).Length
    }
}

$result = [ordered]@{
    artifact_type = 'R7_SOURCE_TO_BINARY_SEMANTIC_VERIFICATION_RESULT'
    compiler_path = $compiler
    compiler_sha256 = Get-LowerSha256 $compiler
    ildasm_path = $ildasm
    ildasm_sha256 = Get-LowerSha256 $ildasm
    normalization = 'ILDASM_TEXT_TOKENS_BYTES_WITH_MVID_AND_LOAD_IMAGE_BASE_REMOVED'
    outputs = $rows
    reference_root = $reference
    rebuild_root = $rebuild
    schema_version = '7.1.0-DRAFT'
    status = 'PASS'
}
$json = $result | ConvertTo-Json -Depth 8 -Compress
[IO.File]::WriteAllText($output, $json + "`n", [Text.UTF8Encoding]::new($false))
[ordered]@{ status='PASS'; output=$output; sha256=Get-LowerSha256 $output; binary_count=$rows.Count } | ConvertTo-Json -Compress
