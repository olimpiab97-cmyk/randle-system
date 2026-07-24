[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$OutputRoot)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$output = [IO.Path]::GetFullPath($OutputRoot)
$temporaryRoot = [IO.Path]::GetFullPath($env:TEMP).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (-not $output.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'BUILD_OUTPUT_OUTSIDE_TEMP' }
if (Test-Path -LiteralPath $output) { throw 'BUILD_OUTPUT_EXISTS' }
New-Item -ItemType Directory -Path $output | Out-Null

$compiler = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$compilerSha256 = 'adeda78a951529462f9411e016c1a1b87ddfd94c55912cbd2957817f39929af1'
$provisioningPackage = Join-Path (Split-Path -Parent $PSScriptRoot) '2026-07-23_Terminal_Authority_Infrastructure_Provisioning_DRAFT'
$baseCommon = Join-Path $provisioningPackage 'TerminalAuthorityCommon_DRAFT.cs'
$r7Common = Join-Path $PSScriptRoot 'TerminalAuthorityR7Common_DRAFT.cs'

function Get-LowerSha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

if ((Get-LowerSha256 $compiler) -cne $compilerSha256) { throw 'COMPILER_IDENTITY_REJECTED' }

$builds = @(
    [pscustomobject]@{ Name='RandleTerminalAuthority.exe'; Platform='anycpu'; Sources=@($baseCommon,$r7Common,(Join-Path $PSScriptRoot 'TerminalAuthorityR7Service_DRAFT.cs')); References=@('System.Core.dll','System.Security.dll','System.ServiceProcess.dll') },
    [pscustomobject]@{ Name='RandleTerminalAuthorityR7Worker.exe'; Platform='anycpu'; Sources=@($baseCommon,$r7Common,(Join-Path $PSScriptRoot 'TerminalAuthorityR7Worker_DRAFT.cs')); References=@('System.Core.dll','System.Security.dll') },
    [pscustomobject]@{ Name='RandleTerminalAuthorityR7Client.exe'; Platform='anycpu'; Sources=@($baseCommon,$r7Common,(Join-Path $PSScriptRoot 'TerminalAuthorityR7Client_DRAFT.cs')); References=@('System.Core.dll','System.Security.dll') },
    [pscustomobject]@{ Name='RandleTerminalAuthorityR7PublicVerifier.exe'; Platform='anycpu'; Sources=@($baseCommon,$r7Common,(Join-Path $PSScriptRoot 'TerminalAuthorityR7PublicVerifier_DRAFT.cs')); References=@('System.Core.dll','System.Security.dll') },
    [pscustomobject]@{ Name='RandleTerminalAuthorityR7AdversarialProbe.exe'; Platform='anycpu'; Sources=@($baseCommon,$r7Common,(Join-Path $PSScriptRoot 'TerminalAuthorityR7AdversarialProbe_DRAFT.cs')); References=@('System.Core.dll','System.Security.dll') },
    [pscustomobject]@{ Name='RandleTerminalAuthorityR7FixtureHost.exe'; Platform='x64'; Sources=@($baseCommon,(Join-Path $PSScriptRoot 'TerminalAuthorityR7FixtureHost_DRAFT.cs')); References=@('System.Core.dll','System.Security.dll') },
    [pscustomobject]@{ Name='RandleTerminalAuthorityR7SubjectLauncher.exe'; Platform='x64'; Sources=@($baseCommon,(Join-Path $PSScriptRoot 'TerminalAuthorityR7SubjectLauncher_DRAFT.cs')); References=@('System.Core.dll','System.Security.dll') }
)

$rows = @()
foreach ($build in $builds) {
    foreach ($source in $build.Sources) { if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "SOURCE_MISSING:$source" } }
    $target = Join-Path $output $build.Name
    $arguments = @('/nologo','/target:exe','/optimize+',('/platform:' + $build.Platform),('/out:' + $target))
    foreach ($reference in $build.References) { $arguments += ('/r:' + $reference) }
    $arguments += $build.Sources
    & $compiler @arguments
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "COMPILATION_FAILED:$($build.Name)" }
    $rows += [ordered]@{
        name = $build.Name
        platform = $build.Platform
        references = @($build.References)
        sha256 = Get-LowerSha256 $target
        size = (Get-Item -LiteralPath $target).Length
        sources = @($build.Sources | ForEach-Object { [ordered]@{ path=[IO.Path]::GetFullPath($_); sha256=Get-LowerSha256 $_; size=(Get-Item -LiteralPath $_).Length } })
    }
}

[ordered]@{
    artifact_type = 'R7_SOURCE_REBUILD_RESULT'
    compiler_path = $compiler
    compiler_sha256 = $compilerSha256
    compiler_options = @('/nologo','/target:exe','/optimize+','/platform:<per-output>')
    output_root = $output
    outputs = $rows
    schema_version = '7.1.0-DRAFT'
    status = 'BUILT_FOR_SEMANTIC_COMPARISON'
} | ConvertTo-Json -Depth 8 -Compress
