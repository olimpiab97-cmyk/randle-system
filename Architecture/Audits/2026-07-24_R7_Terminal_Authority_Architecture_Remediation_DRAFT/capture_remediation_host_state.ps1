[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$EvidenceRoot,
    [Parameter(Mandatory = $true)][ValidateSet('PRECHANGE','POSTINSTALL','POSTMATRIX','FINAL')][string]$Phase,
    [string]$ActiveProductionRoot = 'C:\Webhook\RandleSystem',
    [string]$ExpectedActiveStatusStdoutSha256,
    [string]$ExpectedActiveStatusStderrSha256,
    [switch]$ActiveRootOnly,
    [switch]$IncludeIgnoredFiles
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$gitExecutable = 'C:\Program Files\Git\cmd\git.exe'
$scExecutable = 'C:\Windows\System32\sc.exe'

$evidence = [IO.Path]::GetFullPath($EvidenceRoot)
$activeRoot = [IO.Path]::GetFullPath($ActiveProductionRoot)
$legacyTerminalInstallRoot = 'C:\Program Files\RandleAI\TerminalAuthority'
$terminalInstallRoot = 'C:\Program Files\RandleAI\TerminalAuthorityV4'
$terminalStateRoot = 'C:\ProgramData\RandleAI\TerminalAuthority'
$upgradeInstallRoot = 'C:\Program Files\RandleAI\TerminalUpgradeAuthority'
$upgradeStateRoot = 'C:\ProgramData\RandleAI\TerminalUpgradeAuthority'
$executionRoot = 'C:\ProgramData\RandleAI\TerminalExecution'
$observationRoot = 'C:\ProgramData\RandleAI\TerminalObservation'
$comparatorRoot = 'C:\ProgramData\RandleAI\TerminalComparator'
$terminalKeyPath = 'C:\ProgramData\Microsoft\Crypto\Keys\1c9681c0b04a3dd4843d8cb457b92413_c5338977-c52f-4ca7-af6f-db9b5e287cca'
$serviceNames = @('RandleTerminalAuthority','RandleTerminalUpgradeAuthority','RandleTerminalExecution','RandleTerminalObservation','RandleTerminalComparator')

function Get-LowerHash([string]$Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path -ErrorAction Stop).Hash.ToLowerInvariant() }
function Get-TextHash([string]$Value) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value))).Replace('-', '')).ToLowerInvariant() }
    finally { $algorithm.Dispose() }
}
function Write-JsonNew([object]$Value, [string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if (Test-Path -LiteralPath $full) { throw "Refusing host evidence overwrite: $full" }
    [IO.File]::WriteAllText($full, ($Value | ConvertTo-Json -Depth 100), [Text.UTF8Encoding]::new($false))
}
function Invoke-RawProcess([string]$FileName, [string[]]$Arguments, [string]$StdoutPath, [string]$StderrPath) {
    $psi = [Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $FileName
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.Arguments = (($Arguments | ForEach-Object { '"' + ([string]$_).Replace('"','\"') + '"' }) -join ' ')
    $process = [Diagnostics.Process]::new(); $process.StartInfo = $psi
    if (-not $process.Start()) { throw "Unable to start $FileName" }
    $stdout = [IO.MemoryStream]::new(); $stderr = [IO.MemoryStream]::new()
    $stdoutTask = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
    $stderrTask = $process.StandardError.BaseStream.CopyToAsync($stderr)
    $process.WaitForExit(); [void]$stdoutTask.GetAwaiter().GetResult(); [void]$stderrTask.GetAwaiter().GetResult()
    [IO.File]::WriteAllBytes($StdoutPath,$stdout.ToArray()); [IO.File]::WriteAllBytes($StderrPath,$stderr.ToArray())
    $exit = $process.ExitCode
    $process.Dispose(); $stdout.Dispose(); $stderr.Dispose()
    return $exit
}
function Capture-TextCommand([string]$FileName, [string[]]$Arguments, [string]$Stem) {
    $stdout = $Stem + '.stdout.bin'; $stderr = $Stem + '.stderr.bin'
    $exit = Invoke-RawProcess $FileName $Arguments $stdout $stderr
    return [ordered]@{ exit_code = $exit; stderr_path = $stderr; stderr_sha256 = (Get-LowerHash $stderr); stdout_path = $stdout; stdout_sha256 = (Get-LowerHash $stdout) }
}
function Inventory-Root([string]$Root, [string]$Class) {
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { return [ordered]@{ class = $Class; exists = $false; files = @(); root = $Root } }
    $rows = [Collections.Generic.List[object]]::new()
    $directoryRows = [Collections.Generic.List[object]]::new()
    foreach ($directory in @((Get-Item -LiteralPath $Root -Force)) + @(Get-ChildItem -LiteralPath $Root -Recurse -Directory -Force | Sort-Object FullName)) {
        $directoryAcl = Get-Acl -LiteralPath $directory.FullName
        $directoryRows.Add([ordered]@{acl_sddl_sha256=(Get-TextHash $directoryAcl.Sddl);attributes=$directory.Attributes.ToString();full_name=$directory.FullName;owner=$directoryAcl.Owner;reparse_point=(($directory.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)})
    }
    foreach ($file in Get-ChildItem -LiteralPath $Root -Recurse -File -Force | Sort-Object FullName) {
        $acl = Get-Acl -LiteralPath $file.FullName
        $streams = @(Get-Item -LiteralPath $file.FullName -Stream * -ErrorAction Stop | Sort-Object Stream | ForEach-Object { [ordered]@{ length = $_.Length; stream = $_.Stream } })
        $rows.Add([ordered]@{
            acl_sddl_sha256 = Get-TextHash $acl.Sddl
            full_name = $file.FullName
            owner = $acl.Owner
            raw_sha256 = Get-LowerHash $file.FullName
            size = $file.Length
            streams = $streams
        })
    }
    return [ordered]@{ class = $Class; directories = $directoryRows.ToArray(); directory_count = $directoryRows.Count; exists = $true; file_count = $rows.Count; files = $rows.ToArray(); root = $Root }
}
function Capture-ActiveWorkingTree([string]$Root, [string]$SafeRoot, [bool]$IncludeIgnored) {
    $trackedStdout = Join-Path $evidence 'active-root-files-tracked-and-untracked.stdout.bin'
    $trackedStderr = Join-Path $evidence 'active-root-files-tracked-and-untracked.stderr.bin'
    $ignoredStdout = Join-Path $evidence 'active-root-files-ignored.stdout.bin'
    $ignoredStderr = Join-Path $evidence 'active-root-files-ignored.stderr.bin'
    if ((Invoke-RawProcess $gitExecutable @('-c','core.longpaths=true','-c',"safe.directory=$SafeRoot",'-C',$Root,'ls-files','-z','--cached','--others','--exclude-standard') $trackedStdout $trackedStderr) -ne 0) { throw 'Active-root tracked/untracked enumeration failed.' }
    if ($IncludeIgnored) {
        if ((Invoke-RawProcess $gitExecutable @('-c','core.longpaths=true','-c',"safe.directory=$SafeRoot",'-C',$Root,'ls-files','-z','--others','--ignored','--exclude-standard') $ignoredStdout $ignoredStderr) -ne 0) { throw 'Active-root ignored enumeration failed.' }
    } else {
        [IO.File]::WriteAllBytes($ignoredStdout,[byte[]]@()); [IO.File]::WriteAllBytes($ignoredStderr,[byte[]]@())
    }
    $pathSet = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($listPath in @($trackedStdout,$ignoredStdout)) {
        $text = [Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes($listPath))
        foreach ($relative in $text.Split([char]0,[StringSplitOptions]::RemoveEmptyEntries)) { if ([string]::IsNullOrEmpty($relative)) { continue }; if (-not $pathSet.Add($relative)) { continue } }
    }
    $paths = @($pathSet); [Array]::Sort($paths,[StringComparer]::Ordinal)
    $rows = [Collections.Generic.List[object]]::new()
    foreach ($relative in $paths) {
        $full = [IO.Path]::GetFullPath((Join-Path $Root $relative))
        if (-not $full.StartsWith($Root.TrimEnd('\') + '\',[StringComparison]::Ordinal)) { throw "Active-root path escaped: $relative" }
        if (-not (Test-Path -LiteralPath $full)) { $rows.Add([ordered]@{relative_path=$relative.Replace('\','/');state='ABSENT'}); continue }
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { $rows.Add([ordered]@{relative_path=$relative.Replace('\','/');state='NON_FILE'}); continue }
        $item = Get-Item -LiteralPath $full -Force
        try { $rows.Add([ordered]@{attributes=$item.Attributes.ToString();raw_sha256=(Get-LowerHash $full);relative_path=$relative.Replace('\','/');size=$item.Length;state='FILE'}) }
        catch { $rows.Add([ordered]@{attributes=$item.Attributes.ToString();error_type=$_.Exception.GetType().FullName;relative_path=$relative.Replace('\','/');size=$item.Length;state='FILE_ACCESS_DENIED'}) }
    }
    $manifestPath = Join-Path $evidence 'active-working-tree-content-manifest.json'
    Write-JsonNew ([ordered]@{artifact_type='R7_ACTIVE_WORKING_TREE_CONTENT_MANIFEST';file_count=$rows.Count;files=$rows.ToArray();ignored_files_included=$IncludeIgnored;root=$Root;schema_version='1.0.0'}) $manifestPath
    return [ordered]@{file_count=$rows.Count;manifest_path=$manifestPath;manifest_sha256=(Get-LowerHash $manifestPath)}
}
function Service-Record([string]$Name) {
    $service = Get-CimInstance Win32_Service -Filter ("Name='" + $Name.Replace("'","''") + "'") -ErrorAction SilentlyContinue
    if ($null -eq $service) { return [ordered]@{ exists = $false; name = $Name } }
    $process = $null
    if ([int]$service.ProcessId -gt 0) { $process = Get-Process -Id ([int]$service.ProcessId) -ErrorAction SilentlyContinue }
    $binary = $null
    if ($null -ne $process) { try { $binary = $process.Path } catch {} }
    $modules = @()
    if ($null -ne $process) {
        try { $modules = @($process.Modules | Sort-Object FileName | ForEach-Object { [ordered]@{ file_name = $_.FileName; raw_sha256 = $(if (Test-Path -LiteralPath $_.FileName -PathType Leaf) { Get-LowerHash $_.FileName } else { $null }) } }) } catch { $modules = @([ordered]@{ error = $_.Exception.Message }) }
    }
    $scRoot = Join-Path $evidence ('service-' + $Name)
    $qc = Capture-TextCommand $scExecutable @('qc',$Name) ($scRoot + '-qc')
    $sid = Capture-TextCommand $scExecutable @('qsidtype',$Name) ($scRoot + '-sidtype')
    $privs = Capture-TextCommand $scExecutable @('qprivs',$Name) ($scRoot + '-privs')
    return [ordered]@{
        account = $service.StartName
        binary_path = $binary
        binary_sha256 = $(if ($null -ne $binary -and (Test-Path -LiteralPath $binary -PathType Leaf)) { Get-LowerHash $binary } else { $null })
        exists = $true
        modules = $modules
        name = $Name
        path_name = $service.PathName
        process_id = [int]$service.ProcessId
        privileges_capture = $privs
        service_config_capture = $qc
        service_sid_capture = $sid
        start_mode = $service.StartMode
        state = $service.State
    }
}

if (Test-Path -LiteralPath $evidence) { throw "Evidence root already exists: $evidence" }
New-Item -ItemType Directory -Path $evidence | Out-Null
if (-not (Test-Path -LiteralPath $activeRoot -PathType Container)) { throw 'Active production root is absent.' }
$safeActiveRoot = $activeRoot.Replace('\','/')
$statusStdout = Join-Path $evidence 'active-root-status.stdout.bin'
$statusStderr = Join-Path $evidence 'active-root-status.stderr.bin'
$statusExit = Invoke-RawProcess $gitExecutable @('-c','core.longpaths=true','-c',"safe.directory=$safeActiveRoot",'-C',$activeRoot,'status','--porcelain=v2','-z','--branch','--untracked-files=all') $statusStdout $statusStderr
if ($statusExit -ne 0) { throw 'Active-root raw status failed.' }
$stdoutHash = Get-LowerHash $statusStdout; $stderrHash = Get-LowerHash $statusStderr
if (-not [string]::IsNullOrWhiteSpace($ExpectedActiveStatusStdoutSha256) -and $stdoutHash -ne $ExpectedActiveStatusStdoutSha256) { throw "Active-root stdout changed: $stdoutHash" }
if (-not [string]::IsNullOrWhiteSpace($ExpectedActiveStatusStderrSha256) -and $stderrHash -ne $ExpectedActiveStatusStderrSha256) { throw "Active-root stderr changed: $stderrHash" }
$head = (& $gitExecutable -c "safe.directory=$safeActiveRoot" -C $activeRoot rev-parse HEAD).Trim()
$branch = (& $gitExecutable -c "safe.directory=$safeActiveRoot" -C $activeRoot branch --show-current).Trim()
$stdoutBytes = [IO.File]::ReadAllBytes($statusStdout); $stderrBytes = [IO.File]::ReadAllBytes($statusStderr)
$nulCount = @($stdoutBytes | Where-Object { $_ -eq 0 }).Count
$stderrText = [Text.Encoding]::UTF8.GetString($stderrBytes)
$warningCount = @([regex]::Matches($stderrText,'(?im)^warning:')).Count
$activeWorkingTree = Capture-ActiveWorkingTree $activeRoot $safeActiveRoot ([bool]$IncludeIgnoredFiles)

if ($ActiveRootOnly) {
    $activeOnlyResult = [ordered]@{
        active_production_root = [ordered]@{branch=((& $gitExecutable -c "safe.directory=$safeActiveRoot" -C $activeRoot branch --show-current).Trim());head=((& $gitExecutable -c "safe.directory=$safeActiveRoot" -C $activeRoot rev-parse HEAD).Trim());path=$activeRoot;status_nul_record_count=$nulCount;status_stderr_sha256=$stderrHash;status_stdout_sha256=$stdoutHash;warning_count=$warningCount;working_tree_content=$activeWorkingTree}
        artifact_type = 'R7_ACTIVE_PRODUCTION_ROOT_PRESERVATION_CAPTURE'
        phase = $Phase
        schema_version = '1.0.0'
    }
    $activeOnlyOutput = Join-Path $evidence 'host-state.json'
    Write-JsonNew $activeOnlyResult $activeOnlyOutput
    Write-Output ([ordered]@{active_status_stderr_sha256=$stderrHash;active_status_stdout_sha256=$stdoutHash;output=$activeOnlyOutput;output_sha256=(Get-LowerHash $activeOnlyOutput);phase=$Phase}|ConvertTo-Json)
    return
}

$serviceRows = [Collections.Generic.List[object]]::new()
foreach ($name in $serviceNames) { $serviceRows.Add((Service-Record $name)) }
$relatedServices = @(Get-CimInstance Win32_Service | Where-Object { $_.Name -match '(?i)Randle|Entry|Trade|Executor|Rithmic|Ngrok|TradingView|Webhook' -or $_.DisplayName -match '(?i)Randle|Entry|Trade|Executor|Rithmic|Ngrok|TradingView|Webhook' } | Sort-Object Name | ForEach-Object { [ordered]@{ name = $_.Name; path_name = $_.PathName; process_id = [int]$_.ProcessId; start_mode = $_.StartMode; start_name = $_.StartName; state = $_.State } })
$keyMetadata = [ordered]@{ exists = (Test-Path -LiteralPath $terminalKeyPath -PathType Leaf); path = $terminalKeyPath; private_key_bytes_read = $false }
if ($keyMetadata.exists) {
    try {
        $keyItem = Get-Item -LiteralPath $terminalKeyPath
        $keyAcl = Get-Acl -LiteralPath $terminalKeyPath
        $keyMetadata['acl_sddl_sha256'] = Get-TextHash $keyAcl.Sddl
        $keyMetadata['length'] = $keyItem.Length
        $keyMetadata['metadata_access'] = 'AVAILABLE'
        $keyMetadata['owner'] = $keyAcl.Owner
    } catch {
        $keyMetadata['metadata_access'] = 'DENIED_TO_CAPTURE_PRINCIPAL'
        $keyMetadata['metadata_error_type'] = $_.Exception.GetType().FullName
    }
}
$ledgerRoot = Join-Path $terminalStateRoot 'Ledger'
$checkpoint = Join-Path $ledgerRoot 'checkpoint.json'
$ledgerEntries = @(Get-ChildItem -LiteralPath $ledgerRoot -Filter '*.entry.json' -File -ErrorAction SilentlyContinue)
$lockFiles = @(Get-ChildItem -LiteralPath (Join-Path $activeRoot '.git') -Recurse -Filter '*.lock' -File -ErrorAction SilentlyContinue | ForEach-Object FullName)
$unmerged = @(& $gitExecutable -c "safe.directory=$safeActiveRoot" -C $activeRoot diff --name-only --diff-filter=U)

$inventories = @(
    (Inventory-Root $legacyTerminalInstallRoot 'LEGACY_TERMINAL_PROGRAM_FILES')
    (Inventory-Root $terminalInstallRoot 'TERMINAL_PROGRAM_FILES')
    (Inventory-Root $terminalStateRoot 'TERMINAL_PROGRAM_DATA')
    (Inventory-Root $upgradeInstallRoot 'UPGRADE_PROGRAM_FILES')
    (Inventory-Root $upgradeStateRoot 'UPGRADE_PROGRAM_DATA')
    (Inventory-Root $executionRoot 'EXECUTION_PROGRAM_DATA')
    (Inventory-Root $observationRoot 'OBSERVATION_PROGRAM_DATA')
    (Inventory-Root $comparatorRoot 'COMPARATOR_PROGRAM_DATA')
)
$result = [ordered]@{
    active_production_root = [ordered]@{
        branch = $branch
        head = $head
        path = $activeRoot
        working_tree_content = $activeWorkingTree
        status_nul_record_count = $nulCount
        status_stderr_sha256 = $stderrHash
        status_stdout_sha256 = $stdoutHash
        warning_count = $warningCount
    }
    artifact_type = 'R7_REMEDIATION_HOST_STATE_CAPTURE'
    captured_at = [DateTimeOffset]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'")
    checkpoint = [ordered]@{ exists = (Test-Path -LiteralPath $checkpoint -PathType Leaf); path = $checkpoint; raw_sha256 = $(if (Test-Path -LiteralPath $checkpoint -PathType Leaf) { Get-LowerHash $checkpoint } else { $null }) }
    git_lock_files = $lockFiles
    inventories = $inventories
    ledger_entry_file_count = $ledgerEntries.Count
    phase = $Phase
    private_key = $keyMetadata
    related_production_and_trading_services = $relatedServices
    schema_version = '1.0.0'
    terminal_authority_services = $serviceRows.ToArray()
    unmerged_paths = $unmerged
}
$output = Join-Path $evidence 'host-state.json'
Write-JsonNew $result $output
Write-Output ([ordered]@{ active_status_stderr_sha256 = $stderrHash; active_status_stdout_sha256 = $stdoutHash; output = $output; output_sha256 = (Get-LowerHash $output); phase = $Phase } | ConvertTo-Json)
