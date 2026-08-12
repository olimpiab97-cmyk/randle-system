[CmdletBinding()]
param(
    [ValidateRange(5, 300)]
    [int]$ServiceTimeoutSeconds = 30,

    [ValidateRange(5, 300)]
    [int]$ListenerTimeoutSeconds = 60,

    [ValidateRange(5, 120)]
    [int]$NgrokTimeoutSeconds = 75
)

$script:repositoryRoot = [IO.Path]::GetFullPath($PSScriptRoot)
if (-not (Test-Path -LiteralPath $script:repositoryRoot -PathType Container)) {
    throw "repository_root_invalid:$script:repositoryRoot"
}
if (-not $env:RANDLE_DATA_ROOT) {
    throw "RANDLE_DATA_ROOT is required for governed production launch authority."
}
$runtimeDataRootCandidate = $env:RANDLE_DATA_ROOT
$script:runtimeDataRoot = [IO.Path]::GetFullPath($runtimeDataRootCandidate)
$env:TV_CONTEXT_ACCEPTANCE_LEDGER_PATH = Join-Path $script:runtimeDataRoot "entry_agent\tv_context_acceptance_ledger.json"
$env:TV_CONTEXT_SPOOL_DIR = Join-Path $script:runtimeDataRoot "tv_context_spool"
$env:ENTRY_AGENT_TV_CONTEXT_URL = "http://127.0.0.1:7002/webhook/tv-context"
if (-not $env:RANDLE_TRADE_MANAGER_MODE) { $env:RANDLE_TRADE_MANAGER_MODE = "qa_stability" }
$StartupStartedAt = [DateTime]::UtcNow
$LaunchId = Get-Date -Format "yyyyMMdd_HHmmss"
$script:startupLogDirectory = Join-Path $script:runtimeDataRoot "startup"
$StartupLogPath = Join-Path $script:startupLogDirectory "launch_$LaunchId.log"
$EvidencePath = Join-Path $script:startupLogDirectory "launch_$LaunchId.evidence.json"

$ExecutorHealthUrl = "http://127.0.0.1:6001/health"
$ExecutorPipelineUrl = "http://127.0.0.1:6001/debug/tick_pipeline"
$ExecutorPricesUrl = "http://127.0.0.1:6001/debug/live_prices"
$TradeManagerVersionUrl = "http://127.0.0.1:7001/debug/version"
$TradeManagerSafetyUrl = "http://127.0.0.1:7001/trades"
$EntryAgentStatusUrl = "http://127.0.0.1:7002/entry/status?symbols=NQ,YM"
$TradingViewRelayHealthUrl = "http://127.0.0.1:7002/debug/tv-context"
$TradingViewRelayReceiptUrl = "http://127.0.0.1:7002/debug/tv-context-receipt"
$NgrokApiBase = "http://127.0.0.1:4040/api"

$ListenerAuthorityMutexName = "Local\RandleSystem_RithmicLiveListener_Authority_v1"
$TradeManagerAuthorityMutexName = "Local\RandleSystem_TradeManager_Authority_v1"
$RithmicFeedHealthPath = Join-Path $script:runtimeDataRoot "rithmic_feed_health.json"
$CommandCenterPath = Join-Path $script:repositoryRoot "command_center.html"
$PublicHealthHelperPath = Join-Path $script:repositoryRoot "startup_public_health_check.py"
$ExecutorJournalMaintenancePath = Join-Path $script:repositoryRoot "compact_executor_tick_journals.py"
$TradeManagerJournalMaintenancePath = Join-Path $script:repositoryRoot "compact_trade_manager_tick_journals.py"
$script:executorTickJournalDirectory = Join-Path $env:LOCALAPPDATA "RandleRuntimeData\executor_tick_authority"
$script:tradeManagerTickJournalDirectory = Join-Path $env:LOCALAPPDATA "RandleRuntimeData\trade_manager_tick_authority"
$TradeManagerPersistencePath = Join-Path $script:runtimeDataRoot "persistence_state.json"
$ExecutorPersistencePath = Join-Path $script:repositoryRoot "Data\executor_state.json"
$ServiceWrapperPath = Join-Path $script:repositoryRoot "command_center_service_launcher.py"
$ServiceManifestPath = Join-Path $script:repositoryRoot "Architecture\Command_Center\command_center_governed_service_manifest.json"
$PythonResolverPath = Join-Path $script:repositoryRoot "resolve_python_runtime.ps1"
if (-not (Test-Path -LiteralPath $ServiceManifestPath -PathType Leaf)) {
    throw "governed_service_manifest_missing:$ServiceManifestPath"
}
if (-not (Test-Path -LiteralPath $PythonResolverPath -PathType Leaf)) {
    throw "python_runtime_resolver_missing:$PythonResolverPath"
}
$ServiceManifest = Get-Content -LiteralPath $ServiceManifestPath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
$ngrokManifestService = @($ServiceManifest.services | Where-Object { $_.name -eq "ngrok" })
if ($ngrokManifestService.Count -ne 1) {
    throw "ngrok_manifest_authority_unresolved"
}
$script:ngrokPublicHost = [string]$ngrokManifestService[0].readiness.public_host
if ([string]::IsNullOrWhiteSpace($script:ngrokPublicHost)) {
    throw "ngrok_public_host_authority_unresolved"
}
$script:ngrokPublicUrl = "https://$($script:ngrokPublicHost)"
. $PythonResolverPath
$script:processEnvironmentAuthority = Repair-RandleProcessEnvironmentKeyCasing
try {
    [string]$script:pythonExecutable = Resolve-RandlePythonExecutable -RepositoryRoot $script:repositoryRoot -ManifestPath $ServiceManifestPath
}
catch {
    throw "python_runtime_authority_unresolved:$($_.Exception.Message)"
}
$RithmicRecentBarsPath = Join-Path $script:runtimeDataRoot "rithmic_recent_bars.json"
$ExecutorJournalMaintenanceTimeoutSeconds = 300
$TradeManagerJournalMaintenanceTimeoutSeconds = 300
$CanonicalMinuteSeconds = 60
$FirstCompleteCandleIntervalCount = 2
$CanonicalAtrRequiredTrueRangeCount = 14
$MarketReadinessSchedulingAllowanceIntervals = 1
$FirstCompleteCandleMaximumSeconds = $FirstCompleteCandleIntervalCount * $CanonicalMinuteSeconds
$CanonicalAtrWarmupMaximumSeconds = $CanonicalAtrRequiredTrueRangeCount * $CanonicalMinuteSeconds
$MarketReadinessSchedulingAllowanceSeconds = $MarketReadinessSchedulingAllowanceIntervals * $CanonicalMinuteSeconds
$MarketReadinessObservationSeconds = $FirstCompleteCandleMaximumSeconds +
    $CanonicalAtrWarmupMaximumSeconds +
    $MarketReadinessSchedulingAllowanceSeconds
$MarketReadinessStallSeconds = $FirstCompleteCandleMaximumSeconds + $MarketReadinessSchedulingAllowanceSeconds

$ExecutorMarker = '\bexecutor\.py\b'
$TradeManagerMarker = '\bcommand_center_service_launcher\.py\b.*--service\s+trade_manager\b|\bproduction_manager_launcher\.py\b|\bEngines[\\/]trade_manager\.py\b'
$EntryAgentMarker = '\bcommand_center_service_launcher\.py\b.*--service\s+entry_agent\b|\bproduction_entry_launcher\.py\b|\bEntryAgent[\\/]tv_context_server\.py\b'
$ListenerMarker = '\brithmic_live_listener\.py\b'

$ComponentTimeouts = [ordered]@{
    ProductionWriteAuthority = 5
    PreExecutorStartSafetyGate = 10
    StartupExposureGate = 10
    Executor = $ServiceTimeoutSeconds
    TradeManager = $ServiceTimeoutSeconds
    EntryAgent = $ServiceTimeoutSeconds
    TradingViewRelay = 10
    RithmicListenerBridge = $ListenerTimeoutSeconds
    MarketDataReadiness = $MarketReadinessObservationSeconds
    CommandCenter = 1
    CanonicalATR = $ServiceTimeoutSeconds
    Ngrok = $NgrokTimeoutSeconds
    ReadinessVerification = 5
}

$Results = [ordered]@{}
$ChildLogs = [ordered]@{}
$ListenerObservation = $null
$ListenerProcess = $null
$NgrokProcess = $null
$NgrokReadinessStartedAt = $null
$TradingViewContextBaseline = $null
$PublicSelfProbeDisabledReason = $null

# Redirected Windows console streams default to cp1252. The existing Executor
# startup banner contains Unicode, so child Python streams must be UTF-8.
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

New-Item -ItemType Directory -Path $script:startupLogDirectory -Force | Out-Null

function Write-StartupLine {
    param(
        [string]$Message,
        [ConsoleColor]$Color = [ConsoleColor]::Gray
    )

    $line = "{0} {1}" -f ([DateTime]::UtcNow.ToString("o")), $Message
    Add-Content -LiteralPath $StartupLogPath -Value $line -Encoding UTF8
    Write-Host $line -ForegroundColor $Color
}

function New-ProbeResult {
    param(
        [bool]$Ok,
        [string]$Reason,
        [object]$Evidence = $null
    )

    return [PSCustomObject]@{
        Ok = $Ok
        Reason = $Reason
        Evidence = $Evidence
    }
}

function Set-ComponentResult {
    param(
        [string]$Name,
        [ValidateSet("READY", "WARMING", "FAILED")]
        [string]$Status,
        [string]$Reason,
        [object]$Evidence = $null
    )

    $script:Results[$Name] = [PSCustomObject]@{
        Component = $Name
        Status = $Status
        Reason = $Reason
        TimeoutSeconds = $ComponentTimeouts[$Name]
        CheckedAtUtc = [DateTime]::UtcNow.ToString("o")
        Evidence = $Evidence
    }

    $color = if ($Status -eq "READY") {
        [ConsoleColor]::Green
    }
    elseif ($Status -eq "WARMING") {
        [ConsoleColor]::Yellow
    }
    else {
        [ConsoleColor]::Red
    }
    Write-StartupLine "COMPONENT=$Name STATUS=$Status REASON=$Reason" $color
}

function Wait-ForContract {
    param(
        [string]$Name,
        [int]$TimeoutSeconds,
        [scriptblock]$Probe
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $last = New-ProbeResult $false "probe_not_run"

    do {
        try {
            $last = & $Probe
            if ($last.Ok) {
                return $last
            }
        }
        catch {
            $last = New-ProbeResult $false ("probe_exception:{0}" -f $_.Exception.Message)
        }

        if ([DateTime]::UtcNow -ge $deadline) {
            break
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)

    return $last
}

function Resolve-MarketReadinessState {
    param(
        [bool]$ServiceAvailable,
        [bool]$ObservationValid,
        [bool]$AuthorityReady,
        [bool]$ProgressAdvanced,
        [double]$ElapsedSeconds,
        [double]$SecondsSinceProgress,
        [int]$MaximumObservationSeconds,
        [int]$StallSeconds,
        [ValidateSet("SERVICE_UNAVAILABLE", "COMPLETED_CANDLE_WARMING", "ATR_WARMING", "READY_WAITING_FOR_ADVANCEMENT")]
        [string]$Phase,
        [string]$DetailReason
    )

    if (-not $ServiceAvailable) {
        return [PSCustomObject]@{
            Status = "FAILED"
            Reason = ("service_unavailable:{0}" -f $DetailReason)
            TradingReady = $false
            ProgressAdvancing = $false
        }
    }
    if (-not $ObservationValid) {
        return [PSCustomObject]@{
            Status = "FAILED"
            Reason = ("market_authority_invalid:{0}" -f $DetailReason)
            TradingReady = $false
            ProgressAdvancing = $false
        }
    }
    if ($AuthorityReady -and $ProgressAdvanced) {
        return [PSCustomObject]@{
            Status = "READY"
            Reason = "current_candles_canonical_atr_and_advancement_confirmed"
            TradingReady = $true
            ProgressAdvancing = $true
        }
    }
    if ($SecondsSinceProgress -gt $StallSeconds) {
        return [PSCustomObject]@{
            Status = "FAILED"
            Reason = ("market_readiness_progress_stalled:{0}:seconds_since_progress={1:N1}" -f $Phase, $SecondsSinceProgress)
            TradingReady = $false
            ProgressAdvancing = $false
        }
    }

    $windowState = if ($ElapsedSeconds -ge $MaximumObservationSeconds) {
        "governed_window_elapsed_while_progressing"
    }
    else {
        "governed_observation_in_progress"
    }
    return [PSCustomObject]@{
        Status = "WARMING"
        Reason = ("{0}:{1}:{2}" -f $Phase, $windowState, $DetailReason)
        TradingReady = $false
        ProgressAdvancing = $ProgressAdvanced
    }
}

function Invoke-LocalJson {
    param(
        [string]$Uri,
        [int]$TimeoutSeconds = 2
    )

    return Invoke-RestMethod -Uri $Uri -TimeoutSec $TimeoutSeconds -ErrorAction Stop
}

function Invoke-LocalJsonResponse {
    param(
        [string]$Uri,
        [int]$TimeoutSeconds = 2
    )

    $statusCode = $null
    $content = ""
    $requestError = $null
    try {
        $webResponse = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec $TimeoutSeconds -ErrorAction Stop
        $statusCode = [int]$webResponse.StatusCode
        $content = [string]$webResponse.Content
    }
    catch {
        $caughtError = $_
        $requestError = [string]$caughtError.Exception.Message
        $errorResponse = $caughtError.Exception.Response
        if ($null -ne $errorResponse) {
            try { $statusCode = [int]$errorResponse.StatusCode } catch { $statusCode = $null }
            try {
                $responseStream = $errorResponse.GetResponseStream()
                if ($null -ne $responseStream) {
                    $streamReader = New-Object IO.StreamReader($responseStream)
                    try { $content = $streamReader.ReadToEnd() } finally { $streamReader.Dispose() }
                }
            }
            catch {
                $content = ""
            }
        }
        $errorDetails = $caughtError.ErrorDetails
        if ([string]::IsNullOrWhiteSpace($content) -and
            $null -ne $errorDetails -and
            -not [string]::IsNullOrWhiteSpace([string]$errorDetails.Message)) {
            $content = [string]$errorDetails.Message
        }
    }

    $payload = $null
    $parseError = $null
    if (-not [string]::IsNullOrWhiteSpace($content)) {
        try { $payload = $content | ConvertFrom-Json -ErrorAction Stop } catch { $parseError = $_.Exception.Message }
    }
    return [PSCustomObject]@{
        StatusCode = $statusCode
        Payload = $payload
        Content = $content
        RequestError = $requestError
        ParseError = $parseError
    }
}

function Get-ManagedProcesses {
    param(
        [string]$ProcessName,
        [string]$CommandMarker
    )

    try {
        $matches = @(
            Get-CimInstance Win32_Process -OperationTimeoutSec 3 -ErrorAction Stop |
                Where-Object {
                    $_.Name -match ("^{0}(\.exe)?$" -f [regex]::Escape($ProcessName)) -and
                    $_.CommandLine -match $CommandMarker
                } |
                Select-Object ProcessId, ParentProcessId, Name, CreationDate, ExecutablePath, CommandLine
        )
        return $matches
    }
    catch {
        return
    }
}

function Test-ProductionWriteAuthority {
    $roots = @(
        $script:runtimeDataRoot,
        (Join-Path $script:runtimeDataRoot "tv_context_spool"),
        (Join-Path $script:runtimeDataRoot "entry_agent")
    )
    $evidence = @()
    foreach ($authorityRoot in $roots) {
        $probe = Join-Path $authorityRoot (".launch-write-authority-{0}.tmp" -f [Guid]::NewGuid().ToString("N"))
        try {
            New-Item -ItemType Directory -Path $authorityRoot -Force -ErrorAction Stop | Out-Null
            [IO.File]::WriteAllText($probe, "governed-production-write-authority`n", [Text.UTF8Encoding]::new($false))
            if ([IO.File]::ReadAllText($probe, [Text.Encoding]::UTF8) -ne "governed-production-write-authority`n") {
                throw "write_probe_readback_mismatch"
            }
            $bytes = [Text.Encoding]::UTF8.GetBytes([IO.Path]::GetFullPath($authorityRoot))
            $hasher = [Security.Cryptography.SHA256]::Create()
            try { $pathHash = ([BitConverter]::ToString($hasher.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant() } finally { $hasher.Dispose() }
            $evidence += [PSCustomObject]@{ PathHash = $pathHash; Ok = $true }
        }
        catch {
            return New-ProbeResult $false ("production_write_authority_failed:{0}" -f $_.Exception.GetType().Name) $evidence
        }
        finally {
            Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
        }
    }
    return New-ProbeResult $true "production_write_authority_pass" $evidence
}

function Test-PreExecutorStartSafetyGate {
    $terminalOrders = @("filled", "cancelled", "canceled", "closed", "rejected", "error", "expired")
    $terminalTrades = @("closed", "archived", "rejected", "error", "cancelled", "canceled")
    $executorProcesses = @(Get-ManagedProcesses "python" $ExecutorMarker)
    if ($executorProcesses.Count -gt 1) {
        return New-ProbeResult $false ("executor_duplicate_before_start:{0}" -f $executorProcesses.Count)
    }

    $executorAuthority = "source_defined_empty_executor_state"
    $orderRows = @()
    $positionProperties = @()
    if ($executorProcesses.Count -eq 1) {
        $expectedExecutorPath = [IO.Path]::GetFullPath((Join-Path $script:repositoryRoot "executor.py"))
        $observedExecutorPath = Get-CommandPythonScriptPath $executorProcesses[0].CommandLine
        if (-not $observedExecutorPath -or [IO.Path]::GetFullPath($observedExecutorPath) -ne $expectedExecutorPath) {
            return New-ProbeResult $false "executor_identity_untrusted_before_start"
        }
        try {
            $ordersPayload = Invoke-LocalJson "http://127.0.0.1:6001/orders" 4
            $positionsPayload = Invoke-LocalJson "http://127.0.0.1:6001/positions" 4
        }
        catch {
            return New-ProbeResult $false ("running_executor_state_unavailable:{0}" -f $_.Exception.Message)
        }
        if ($ordersPayload.ok -ne $true -or $positionsPayload.ok -ne $true -or $null -eq $ordersPayload.orders -or $null -eq $positionsPayload.positions) {
            return New-ProbeResult $false "running_executor_state_contract_failed"
        }
        $orderRows = @($ordersPayload.orders)
        $positionProperties = @($positionsPayload.positions.PSObject.Properties)
        $executorAuthority = "live_executor"
    }
    elseif (Test-Path -LiteralPath $ExecutorPersistencePath -PathType Leaf) {
        try { $executorPersisted = Get-Content -LiteralPath $ExecutorPersistencePath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop } catch {
            return New-ProbeResult $false ("persisted_executor_state_invalid:{0}" -f $_.Exception.Message)
        }
        if ($null -eq $executorPersisted.orders -or $null -eq $executorPersisted.positions) {
            return New-ProbeResult $false "persisted_executor_state_contract_failed"
        }
        $orderRows = @($executorPersisted.orders.PSObject.Properties.Value)
        $positionProperties = @($executorPersisted.positions.PSObject.Properties)
        $executorAuthority = "persisted_executor_state"
    }
    $activeOrders = @($orderRows | Where-Object { $terminalOrders -notcontains ([string]$_.status).ToLowerInvariant() })
    $nonzeroPositions = @($positionProperties | Where-Object {
        $value = $_.Value
        $qty = if ($value -is [System.Collections.IDictionary] -or $value.PSObject.Properties["qty"]) { $value.qty } else { $value }
        [math]::Abs([double]($qty -as [double])) -gt 0
    })

    $tradeCandidates = @(Get-ManagedProcesses "python" $TradeManagerMarker)
    $tradeProcesses = @(Get-GovernedWrappedServiceProcesses "trade_manager")
    if ($tradeCandidates.Count -ne $tradeProcesses.Count -or $tradeProcesses.Count -gt 1) {
        return New-ProbeResult $false "trade_manager_identity_untrusted_before_start"
    }
    $pendingTrades = @()
    $orphan = $false
    $tradeAuthority = "persisted_start_gate_only"
    if ($tradeProcesses.Count -eq 1) {
        try { $tradePayload = Invoke-LocalJson "http://127.0.0.1:7001/trades" 4 } catch {
            return New-ProbeResult $false ("running_trade_manager_state_unavailable:{0}" -f $_.Exception.Message)
        }
        if ($tradePayload.ok -ne $true -or $null -eq $tradePayload.trades) {
            return New-ProbeResult $false "running_trade_manager_state_contract_failed"
        }
        $pendingTrades = @($tradePayload.trades.PSObject.Properties.Value | Where-Object { $terminalTrades -notcontains ([string]$_.status).ToLowerInvariant() })
        $orphan = $tradePayload.orphan_exposure.has_orphans -eq $true -or $tradePayload.orphan_exposure.has_manager_state_issue -eq $true
        $tradeAuthority = "live_trade_manager"
    }
    else {
        if (-not (Test-Path -LiteralPath $TradeManagerPersistencePath -PathType Leaf)) {
            return New-ProbeResult $false "persisted_trade_state_unavailable"
        }
        try { $tradePersisted = Get-Content -LiteralPath $TradeManagerPersistencePath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop } catch {
            return New-ProbeResult $false ("persisted_trade_state_invalid:{0}" -f $_.Exception.Message)
        }
        if ($null -eq $tradePersisted.trades) { return New-ProbeResult $false "persisted_trade_state_contract_failed" }
        $pendingTrades = @($tradePersisted.trades.PSObject.Properties.Value | Where-Object { $terminalTrades -notcontains ([string]$_.status).ToLowerInvariant() })
        $topLevelOrphan = $tradePersisted.PSObject.Properties["orphan_exposure"]
        $systemState = $tradePersisted.PSObject.Properties["system"]
        $systemOrphan = if ($null -ne $systemState -and $null -ne $systemState.Value) {
            $systemState.Value.PSObject.Properties["orphan_exposure"]
        }
        else {
            $null
        }
        $orphanState = if ($null -ne $topLevelOrphan) {
            $topLevelOrphan.Value
        }
        elseif ($null -ne $systemOrphan) {
            $systemOrphan.Value
        }
        else {
            [PSCustomObject]@{ has_orphans = $false; has_manager_state_issue = $false }
        }
        $orphan = $orphanState.has_orphans -eq $true -or $orphanState.has_manager_state_issue -eq $true
    }
    $ok = $activeOrders.Count -eq 0 -and $nonzeroPositions.Count -eq 0 -and $pendingTrades.Count -eq 0 -and -not $orphan
    return New-ProbeResult $ok $(if ($ok) { "pre_executor_start_exposure_zero" } else { "pre_executor_start_exposure_active_fail_closed" }) ([PSCustomObject]@{
        ActiveOrders = $activeOrders.Count
        NonzeroPositions = $nonzeroPositions.Count
        PendingExecutableActions = $pendingTrades.Count
        OrphanExposure = $orphan
        ExecutorAuthority = $executorAuthority
        TradeAuthority = $tradeAuthority
    })
}

function Test-StartupExposureGate {
    try {
        $ordersPayload = Invoke-LocalJson "http://127.0.0.1:6001/orders" 4
        $positionsPayload = Invoke-LocalJson "http://127.0.0.1:6001/positions" 4
    }
    catch {
        return New-ProbeResult $false ("executor_live_exposure_unavailable:{0}" -f $_.Exception.Message)
    }
    if ($ordersPayload.ok -ne $true -or $positionsPayload.ok -ne $true) {
        return New-ProbeResult $false "executor_live_exposure_contract_failed"
    }
    $terminalOrders = @("filled", "cancelled", "canceled", "closed", "rejected", "error", "expired")
    $activeOrders = @($ordersPayload.orders | Where-Object { $terminalOrders -notcontains ([string]$_.status).ToLowerInvariant() })
    $nonzeroPositions = @($positionsPayload.positions.PSObject.Properties | Where-Object {
        $value = $_.Value
        $qty = if ($value -is [System.Collections.IDictionary] -or $value.PSObject.Properties["qty"]) { $value.qty } else { $value }
        [math]::Abs([double]($qty -as [double])) -gt 0
    })

    $terminalTrades = @("closed", "archived", "rejected", "error", "cancelled", "canceled")
    $tradeProcesses = @(Get-GovernedWrappedServiceProcesses "trade_manager")
    $pendingTrades = @()
    $orphan = $false
    $tradeAuthority = "persisted_start_gate_only"
    if ($tradeProcesses.Count -eq 1) {
        try { $tradePayload = Invoke-LocalJson "http://127.0.0.1:7001/trades" 4 } catch {
            return New-ProbeResult $false ("running_trade_manager_state_unavailable:{0}" -f $_.Exception.Message)
        }
        if ($tradePayload.ok -ne $true -or $null -eq $tradePayload.trades) {
            return New-ProbeResult $false "running_trade_manager_state_contract_failed"
        }
        $pendingTrades = @($tradePayload.trades.PSObject.Properties.Value | Where-Object { $terminalTrades -notcontains ([string]$_.status).ToLowerInvariant() })
        $orphan = $tradePayload.orphan_exposure.has_orphans -eq $true -or $tradePayload.orphan_exposure.has_manager_state_issue -eq $true
        $tradeAuthority = "live_trade_manager"
    }
    else {
        if (-not (Test-Path -LiteralPath $TradeManagerPersistencePath -PathType Leaf)) {
            return New-ProbeResult $false "persisted_trade_state_unavailable"
        }
        try { $persisted = Get-Content -LiteralPath $TradeManagerPersistencePath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop } catch {
            return New-ProbeResult $false ("persisted_trade_state_invalid:{0}" -f $_.Exception.Message)
        }
        $pendingTrades = @($persisted.trades.PSObject.Properties.Value | Where-Object { $terminalTrades -notcontains ([string]$_.status).ToLowerInvariant() })
        $topLevelOrphan = $persisted.PSObject.Properties["orphan_exposure"]
        $systemState = $persisted.PSObject.Properties["system"]
        $systemOrphan = if ($null -ne $systemState -and $null -ne $systemState.Value) {
            $systemState.Value.PSObject.Properties["orphan_exposure"]
        }
        else {
            $null
        }
        $orphanState = if ($null -ne $topLevelOrphan) {
            $topLevelOrphan.Value
        }
        elseif ($null -ne $systemOrphan) {
            $systemOrphan.Value
        }
        else {
            [PSCustomObject]@{ has_orphans = $false; has_manager_state_issue = $false }
        }
        $orphan = $orphanState.has_orphans -eq $true -or $orphanState.has_manager_state_issue -eq $true
    }
    $ok = $activeOrders.Count -eq 0 -and $nonzeroPositions.Count -eq 0 -and $pendingTrades.Count -eq 0 -and -not $orphan
    return New-ProbeResult $ok $(if ($ok) { "startup_exposure_zero_before_execution_dependencies" } else { "startup_exposure_active_fail_closed" }) ([PSCustomObject]@{
        ActiveOrders = $activeOrders.Count
        NonzeroPositions = $nonzeroPositions.Count
        PendingExecutableActions = $pendingTrades.Count
        OrphanExposure = $orphan
        TradeAuthority = $tradeAuthority
    })
}

function Get-CommandPythonScriptPath {
    param([string]$CommandLine)
    $match = [regex]::Match(
        [string]$CommandLine,
        '(?:"(?<path>[^"]+\.py)"|(?<path>[A-Za-z]:[^\s"]+\.py)|(?<path>(?:\.[\\/])?[A-Za-z0-9_.-]+(?:[\\/][^\s"]+)*\.py))',
        [Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    if (-not $match.Success) { return $null }
    try {
        $observedPath = $match.Groups["path"].Value
        if (-not [IO.Path]::IsPathRooted($observedPath)) {
            $observedPath = Join-Path $script:repositoryRoot $observedPath
        }
        return [IO.Path]::GetFullPath($observedPath)
    }
    catch { return $null }
}

function Test-FileSha256 {
    param([string]$Path, [string]$Expected)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() -eq $Expected.ToLowerInvariant()
}

function Get-GovernedWrappedServiceProcesses {
    param([ValidateSet("entry_agent", "trade_manager")][string]$Service)

    $marker = if ($Service -eq "entry_agent") { $EntryAgentMarker } else { $TradeManagerMarker }
    $legacyName = if ($Service -eq "entry_agent") { "production_entry_launcher.py" } else { "production_manager_launcher.py" }
    $legacySha = if ($Service -eq "entry_agent") {
        "45202326d96023689a53db6b915d9d6557b98ed95e2d5b022a1b9545ef80ce1e"
    } else {
        "005ff8b995b623777b8390c5d9cf66813bcf5326f28ed106a3eaee9a5d874d28"
    }
    $serviceSource = if ($Service -eq "entry_agent") {
        Join-Path $script:repositoryRoot "EntryAgent\tv_context_server.py"
    } else {
        Join-Path $script:repositoryRoot "Engines\trade_manager.py"
    }
    $legacySourceSha = if ($Service -eq "entry_agent") {
        "d4e1361629892febabf61403a2d1ff9652b090e86fe82760723b749d0da1b710"
    } else {
        "d29c15455f0b3cfd027ca2587da17d89b097cdf5b61bbb00511587ff00887315"
    }
    $manifestService = @($ServiceManifest.services | Where-Object { $_.name -eq $Service })
    $canonicalIdentity = @($manifestService.execution_identities | Where-Object { $_.name -eq "canonical_wrapper" })
    if ($manifestService.Count -ne 1 -or $canonicalIdentity.Count -ne 1) { return @() }
    $canonicalSha = [string]$canonicalIdentity[0].wrapper_sha256

    $candidates = @(Get-ManagedProcesses "python" $marker)
    $trusted = @()
    foreach ($process in $candidates) {
        $scriptPath = Get-CommandPythonScriptPath $process.CommandLine
        $canonical = $scriptPath -and
            ([IO.Path]::GetFullPath($scriptPath) -eq [IO.Path]::GetFullPath($ServiceWrapperPath)) -and
            ([string]$process.CommandLine -match ("--service\s+{0}\b" -f [regex]::Escape($Service))) -and
            (Test-FileSha256 $scriptPath $canonicalSha)
        $legacy = $scriptPath -and
            ([IO.Path]::GetFileName($scriptPath) -ieq $legacyName) -and
            (Test-FileSha256 $scriptPath $legacySha) -and
            (Test-FileSha256 $serviceSource $legacySourceSha)
        if ($canonical -or $legacy) { $trusted += $process }
    }
    # Any direct, altered-wrapper, or mixed sibling candidate makes the whole
    # identity set ambiguous; callers then fail closed on the occupied port.
    if ($trusted.Count -ne $candidates.Count) { return @() }
    return @($trusted)
}

function Get-PortOwners {
    param([int]$Port)

    $owners = @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object LocalAddress, LocalPort, OwningProcess, State
    )
    return $owners
}

function Test-PortFree {
    param([int]$Port)
    return @(Get-PortOwners $Port).Count -eq 0
}

function Test-MutexOwned {
    param([string]$Name)

    try {
        $mutex = [System.Threading.Mutex]::OpenExisting($Name)
        $mutex.Dispose()
        return $true
    }
    catch [System.Threading.WaitHandleCannotBeOpenedException] {
        return $false
    }
    catch {
        return $false
    }
}

function Start-ManagedProcess {
    param(
        [string]$Component,
        [string]$FilePath,
        [string[]]$ArgumentList
    )

    if (-not (Test-Path -LiteralPath $script:repositoryRoot -PathType Container)) {
        throw "managed_process_working_directory_invalid:$script:repositoryRoot"
    }
    $stdoutPath = Join-Path $script:startupLogDirectory ("{0}_{1}.stdout.log" -f $Component, $LaunchId)
    $stderrPath = Join-Path $script:startupLogDirectory ("{0}_{1}.stderr.log" -f $Component, $LaunchId)
    Write-StartupLine "COMPONENT=$Component ACTION=START COMMAND=$FilePath $($ArgumentList -join ' ')"
    $startParameters = @{
        FilePath = $FilePath
        ArgumentList = $ArgumentList
        WorkingDirectory = $script:repositoryRoot
        RedirectStandardOutput = $stdoutPath
        RedirectStandardError = $stderrPath
        WindowStyle = "Hidden"
        PassThru = $true
        ErrorAction = "Stop"
    }
    $process = Start-Process @startParameters
    $script:ChildLogs[$Component] = [PSCustomObject]@{
        Pid = $process.Id
        Stdout = $stdoutPath
        Stderr = $stderrPath
    }
    return $process
}

function Get-LogTail {
    param(
        [string]$Path,
        [int]$Lines = 20
    )

    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) {
        return @()
    }
    return @(Get-Content -LiteralPath $Path -Tail $Lines -ErrorAction SilentlyContinue)
}

function Test-ExecutorContract {
    $processes = @(Get-ManagedProcesses "python" $ExecutorMarker)
    if ($processes.Count -ne 1) {
        return New-ProbeResult $false ("executor_process_count:{0}" -f $processes.Count) $processes
    }

    try {
        $health = Invoke-LocalJson $ExecutorHealthUrl
        $pipeline = Invoke-LocalJson $ExecutorPipelineUrl
        $portOwners = @(Get-PortOwners 6001)
        $processId = [int]$pipeline.pid
        $pidMatches = @($processes.ProcessId) -contains $processId
        $portMatches = @($portOwners.OwningProcess) -contains $processId
        $ok = $health.ok -eq $true -and $pipeline.ok -eq $true -and $pidMatches -and $portMatches
        $reason = if ($ok) { "health_pipeline_and_port_owner_confirmed" } else { "executor_contract_mismatch" }
        return New-ProbeResult $ok $reason ([PSCustomObject]@{
            Pid = $processId
            Health = $health
            Pipeline = $pipeline
            PortOwners = $portOwners
            Process = $processes[0]
        })
    }
    catch {
        return New-ProbeResult $false ("executor_endpoint_error:{0}" -f $_.Exception.Message)
    }
}

function Test-TradeManagerContract {
    $processes = @(Get-GovernedWrappedServiceProcesses "trade_manager")
    if ($processes.Count -ne 1) {
        return New-ProbeResult $false ("trade_manager_process_count:{0}" -f $processes.Count) $processes
    }

    $tradeManagerProcess = $processes[0]
    $tradeManagerPortOwners = @(Get-PortOwners 7001)
    try { $version = Invoke-LocalJson $TradeManagerVersionUrl 3 }
    catch {
        return New-ProbeResult $false ("trade_manager_version_endpoint_error:{0}" -f $_.Exception.Message) ([PSCustomObject]@{
            FailedEndpoint = $TradeManagerVersionUrl
            PortOwners = $tradeManagerPortOwners
            Process = $tradeManagerProcess
        })
    }
    try { $safety = Invoke-LocalJson $TradeManagerSafetyUrl 4 }
    catch {
        return New-ProbeResult $false ("trade_manager_safety_endpoint_error:{0}" -f $_.Exception.Message) ([PSCustomObject]@{
            FailedEndpoint = $TradeManagerSafetyUrl
            Version = $version
            PortOwners = $tradeManagerPortOwners
            Process = $tradeManagerProcess
        })
    }

    $processId = [int]$tradeManagerProcess.ProcessId
    $portMatches = $tradeManagerPortOwners.Count -eq 1 -and [int]$tradeManagerPortOwners[0].OwningProcess -eq $processId
    $expectedSourcePath = [IO.Path]::GetFullPath((Join-Path $script:repositoryRoot "Engines\trade_manager.py"))
    $reportedSourcePath = try { [IO.Path]::GetFullPath([string]$version.file_path) } catch { "" }
    $sourceMatches = -not [string]::IsNullOrWhiteSpace($reportedSourcePath) -and
        [string]::Equals($reportedSourcePath, $expectedSourcePath, [StringComparison]::OrdinalIgnoreCase)
    $orphan = $safety.orphan_exposure
    $safetySchema = $safety.ok -eq $true -and
        $null -ne $safety.trades -and
        $null -ne $orphan -and
        ($orphan.PSObject.Properties.Name -contains "has_orphans") -and
        ($orphan.PSObject.Properties.Name -contains "has_manager_state_issue")
    $ok = $version.ok -eq $true -and $sourceMatches -and $safetySchema -and $portMatches
    $reason = if ($ok) { "source_version_safety_schema_and_unique_port_owner_confirmed" } else { "trade_manager_contract_mismatch" }
    return New-ProbeResult $ok $reason ([PSCustomObject]@{
        Pid = $processId
        Version = $version
        Safety = [PSCustomObject]@{
            TradeCount = @($safety.trades.PSObject.Properties).Count
            HasOrphans = $orphan.has_orphans
            HasManagerStateIssue = $orphan.has_manager_state_issue
        }
        ExpectedSourcePath = $expectedSourcePath
        ReportedSourcePath = $reportedSourcePath
        SourceMatches = $sourceMatches
        PortOwners = $tradeManagerPortOwners
        Process = $tradeManagerProcess
    })
}

function Test-EntryAgentContract {
    $processes = @(Get-GovernedWrappedServiceProcesses "entry_agent")
    if ($processes.Count -ne 1) {
        return New-ProbeResult $false ("entry_agent_process_count:{0}" -f $processes.Count) $processes
    }

    try {
        $response = Invoke-LocalJsonResponse $EntryAgentStatusUrl 4
        $status = $response.Payload
        $portOwners = @(Get-PortOwners 7002)
        $processId = [int]$processes[0].ProcessId
        $serviceResponsive = (@($portOwners.OwningProcess) -contains $processId)
        $baseEvidence = [ordered]@{
            Pid = $processId
            HttpStatusCode = $response.StatusCode
            ServiceStatus = if ($status) { $status.service_status } else { $null }
            PortOwners = $portOwners
            Process = $processes[0]
        }

        if ([int]$response.StatusCode -eq 503 -and $status.service_status -eq "REHYDRATING") {
            $rehydrationFailures = @($status.rehydration_failures | ForEach-Object {
                "{0}:{1}" -f $_.symbol, $_.reason
            })
            $baseEvidence["ReadinessClass"] = "expected_fail_closed_rehydration"
            $baseEvidence["ServiceReady"] = $serviceResponsive
            $baseEvidence["TradingReady"] = $false
            $baseEvidence["RehydrationFailures"] = $status.rehydration_failures
            $baseEvidence["Symbols"] = $status.symbols
            $reasonDetail = if ($rehydrationFailures.Count -gt 0) { $rehydrationFailures -join "," } else { "reason_unavailable" }
            return New-ProbeResult $serviceResponsive ("entry_agent_service_responsive_fail_closed_rehydrating:{0}" -f $reasonDetail) ([PSCustomObject]$baseEvidence)
        }
        if ([int]$response.StatusCode -ne 200) {
            $baseEvidence["ReadinessClass"] = "endpoint_http_failure"
            $baseEvidence["RequestError"] = $response.RequestError
            $baseEvidence["ResponseContent"] = $response.Content
            return New-ProbeResult $false ("entry_agent_http_status:{0}:{1}" -f $response.StatusCode, $response.RequestError) ([PSCustomObject]$baseEvidence)
        }
        if ($null -eq $status) {
            $baseEvidence["ReadinessClass"] = "endpoint_payload_invalid"
            $baseEvidence["ParseError"] = $response.ParseError
            return New-ProbeResult $false ("entry_agent_payload_invalid:{0}" -f $response.ParseError) ([PSCustomObject]$baseEvidence)
        }

        $symbolRoots = @($status.symbols | ForEach-Object { $_.symbol })
        $ok = $status.ok -eq $true -and
            $status.service_status -eq "LIVE" -and
            (@($symbolRoots | Where-Object { $_ -eq "NQ" }).Count -eq 1) -and
            (@($symbolRoots | Where-Object { $_ -eq "YM" }).Count -eq 1) -and
            (@($portOwners.OwningProcess) -contains $processId)
        $reason = if ($ok) { "entry_status_responded_for_nq_ym" } else { "entry_agent_contract_mismatch" }
        $baseEvidence["ReadinessClass"] = if ($ok) { "live" } else { "endpoint_contract_mismatch" }
        $baseEvidence["ServiceReady"] = $ok
        $baseEvidence["Symbols"] = $symbolRoots
        return New-ProbeResult $ok $reason ([PSCustomObject]$baseEvidence)
    }
    catch {
        return New-ProbeResult $false ("entry_agent_endpoint_error:{0}" -f $_.Exception.Message)
    }
}

function Test-TradingViewRelayContract {
    $processes = @(Get-GovernedWrappedServiceProcesses "entry_agent")
    if ($processes.Count -ne 1) {
        return New-ProbeResult $false ("tradingview_relay_process_count:{0}" -f $processes.Count) $processes
    }

    try {
        $health = Invoke-LocalJson $TradingViewRelayHealthUrl
        $portOwners = @(Get-PortOwners 7002)
        $processId = [int]$processes[0].ProcessId
        $ok = $health.ok -eq $true -and
            $health.source -eq "tradingview_level_helper" -and
            $health.price_truth -eq "Rithmic" -and
            (@($portOwners.OwningProcess) -contains $processId)
        $reason = if ($ok) { "liquidity_only_relay_listening_with_rithmic_price_truth" } else { "tradingview_relay_contract_mismatch" }
        return New-ProbeResult $ok $reason ([PSCustomObject]@{
            Pid = $processId
            Health = $health
            PortOwners = $portOwners
            Process = $processes[0]
        })
    }
    catch {
        return New-ProbeResult $false ("tradingview_relay_endpoint_error:{0}" -f $_.Exception.Message)
    }
}

function Get-MarketSessionDate {
    try {
        $zone = [TimeZoneInfo]::FindSystemTimeZoneById("Pacific Standard Time")
        return [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $zone).ToString("yyyy-MM-dd")
    }
    catch {
        return (Get-Date).ToString("yyyy-MM-dd")
    }
}

function Get-StaleLifecycleFields {
    param(
        [object]$Status,
        [string]$ExpectedDate
    )

    $stale = @()
    foreach ($property in $Status.PSObject.Properties) {
        if ($property.Name -notmatch '(_at|_time|_started_at|_expires_at)$') {
            continue
        }
        if ($null -eq $property.Value -or [string]::IsNullOrWhiteSpace([string]$property.Value)) {
            continue
        }
        try {
            $timestamp = [DateTimeOffset]::Parse([string]$property.Value)
            $zone = [TimeZoneInfo]::FindSystemTimeZoneById("Pacific Standard Time")
            $localDate = [TimeZoneInfo]::ConvertTime($timestamp, $zone).ToString("yyyy-MM-dd")
            if ($localDate -ne $ExpectedDate) {
                $stale += ("{0}={1}" -f $property.Name, $property.Value)
            }
        }
        catch {
            continue
        }
    }
    return $stale
}

function Test-EntryCurrentSessionContract {
    try {
        $payload = Invoke-LocalJson $EntryAgentStatusUrl 5
        $expectedDate = Get-MarketSessionDate
        $evidence = @()
        $failures = @()

        foreach ($symbolRoot in @("NQ", "YM")) {
            $status = @($payload.symbols | Where-Object { $_.symbol -eq $symbolRoot } | Select-Object -First 1)
            if ($status.Count -ne 1) {
                $failures += "${root}:status_missing"
                continue
            }

            $item = $status[0]
            $sessionAuthority = $item.session_authority
            $context = $item.market_context
            $lockedContext = if ($context) { $context.locked_liquidity_context } else { $null }
            $ladderLevels = if ($context -and $context.liquidity_map) { @($context.liquidity_map.levels) } else { @() }
            $staleLifecycle = @(Get-StaleLifecycleFields $item $expectedDate)
            $candleAgeSeconds = $null
            try {
                $candleAgeSeconds = [math]::Round(([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse([string]$item.candle_time)).TotalSeconds, 3)
            }
            catch {
                $candleAgeSeconds = $null
            }

            $symbolFailures = @()
            if ($sessionAuthority.effective_session_date -ne $expectedDate) { $symbolFailures += "effective_session_not_today" }
            if ($sessionAuthority.rithmic_session_date -ne $expectedDate) { $symbolFailures += "rithmic_session_not_today" }
            if ($context.session_date -ne $expectedDate) { $symbolFailures += "tradingview_context_not_today" }
            if ($lockedContext.session_date -ne $expectedDate) { $symbolFailures += "locked_ladder_not_today" }
            if ($ladderLevels.Count -eq 0) { $symbolFailures += "today_ladder_missing" }
            if ($null -eq $candleAgeSeconds -or $candleAgeSeconds -gt 180) { $symbolFailures += "candle_not_current" }
            if ($staleLifecycle.Count -gt 0) { $symbolFailures += "prior_session_lifecycle_timestamps_present" }
            if ($sessionAuthority.session_context_stale -eq $true) { $symbolFailures += "session_context_stale" }

            if ($symbolFailures.Count -gt 0) {
                $failures += ("{0}:{1}" -f $symbolRoot, ($symbolFailures -join ","))
            }
            $evidence += [PSCustomObject]@{
                Symbol = $symbolRoot
                ExpectedSessionDate = $expectedDate
                EffectiveSessionDate = $sessionAuthority.effective_session_date
                RithmicSessionDate = $sessionAuthority.rithmic_session_date
                TradingViewSessionDate = $sessionAuthority.tradingview_session_date
                ContextSessionDate = $context.session_date
                LockedLadderSessionDate = $lockedContext.session_date
                LadderLevelCount = $ladderLevels.Count
                CandleTime = $item.candle_time
                CandleAgeSeconds = $candleAgeSeconds
                StaleLifecycleFields = $staleLifecycle
                SessionContextStale = $sessionAuthority.session_context_stale
            }
        }

        $ok = $failures.Count -eq 0
        $reason = if ($ok) { "today_session_candles_lifecycle_context_and_ladder_confirmed" } else { $failures -join ";" }
        return New-ProbeResult $ok $reason $evidence
    }
    catch {
        return New-ProbeResult $false ("entry_current_session_probe_error:{0}" -f $_.Exception.Message)
    }
}

function Get-RithmicFeedHealth {
    if (-not (Test-Path -LiteralPath $RithmicFeedHealthPath)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $RithmicFeedHealthPath -Raw -ErrorAction Stop | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Get-CanonicalCompletedCandleEvidence {
    param(
        [string]$NqContract,
        [string]$YmContract
    )

    if (-not (Test-Path -LiteralPath $RithmicRecentBarsPath -PathType Leaf)) {
        return [PSCustomObject]@{
            Ok = $false
            Valid = $true
            Reason = "canonical_completed_candle_authority_missing"
            NQ = $null
            YM = $null
        }
    }

    try {
        $recentBars = Get-Content -LiteralPath $RithmicRecentBarsPath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        $expectedSessionDate = Get-MarketSessionDate
        $evidenceBySymbol = [ordered]@{}
        $failures = @()
        foreach ($symbolRoot in @("NQ", "YM")) {
            $contract = if ($symbolRoot -eq "NQ") { $NqContract } else { $YmContract }
            $contractProperty = if ($recentBars.symbols) { $recentBars.symbols.PSObject.Properties[$contract] } else { $null }
            $bars = if ($contractProperty) { @($contractProperty.Value) } else { @() }
            $currentSessionCompleted = @($bars | Where-Object {
                $_.status -eq "FINAL" -and $_.session_date -eq $expectedSessionDate
            })
            $completed = @($currentSessionCompleted | Select-Object -Last 1)
            $candle = if ($completed.Count -eq 1) { $completed[0] } else { $null }
            $ageSeconds = $null
            if ($candle -and $candle.timestamp) {
                try {
                    $ageSeconds = [math]::Round(([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse([string]$candle.timestamp)).TotalSeconds, 3)
                }
                catch {
                    $ageSeconds = $null
                }
            }
            $current = $null -ne $candle -and
                $candle.session_date -eq $expectedSessionDate -and
                $null -ne $ageSeconds -and
                $ageSeconds -ge -5 -and
                $ageSeconds -le 180
            if (-not $current) {
                $failures += ("{0}:canonical_completed_candle_unavailable" -f $symbolRoot)
            }
            $evidenceBySymbol[$symbolRoot] = [PSCustomObject]@{
                Symbol = $symbolRoot
                Contract = $contract
                ExpectedSessionDate = $expectedSessionDate
                SessionDate = if ($candle) { $candle.session_date } else { $null }
                Timestamp = if ($candle) { $candle.timestamp } else { $null }
                AgeSeconds = $ageSeconds
                BarId = if ($candle) { $candle.bar_id } else { $null }
                CurrentSessionCompletedCount = $currentSessionCompleted.Count
                LastCompletedCandleTime = if ($candle) { $candle.timestamp } else { $null }
                Current = $current
            }
        }
        return [PSCustomObject]@{
            Ok = $failures.Count -eq 0
            Valid = $true
            Reason = if ($failures.Count -eq 0) { "current_canonical_completed_candles_confirmed" } else { $failures -join "," }
            NQ = $evidenceBySymbol["NQ"]
            YM = $evidenceBySymbol["YM"]
        }
    }
    catch {
        return [PSCustomObject]@{
            Ok = $false
            Valid = $false
            Reason = ("canonical_completed_candle_authority_error:{0}" -f $_.Exception.Message)
            NQ = $null
            YM = $null
        }
    }
}

function Test-ListenerBridgeContract {
    $process = $script:ListenerProcess
    if ($null -eq $process -or $null -eq $process.ProcessId) {
        return New-ProbeResult $false "listener_process_not_registered"
    }
    if ($null -eq (Get-Process -Id ([int]$process.ProcessId) -ErrorAction SilentlyContinue)) {
        return New-ProbeResult $false "listener_process_exited" $process
    }
    if (-not (Test-MutexOwned $ListenerAuthorityMutexName)) {
        return New-ProbeResult $false "listener_authority_mutex_not_owned" $process
    }

    try {
        $health = Get-RithmicFeedHealth
        if ($null -eq $health) {
            return New-ProbeResult $false "rithmic_feed_health_missing_or_invalid"
        }

        $updatedAge = ([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse([string]$health.updated_at_utc)).TotalSeconds
        $nq = $health.symbols.NQ
        $ym = $health.symbols.YM
        if ($null -eq $nq -or $null -eq $ym) {
            return New-ProbeResult $false "nq_or_ym_feed_health_missing"
        }

        $executorPipeline = Invoke-LocalJson $ExecutorPipelineUrl
        $livePrices = Invoke-LocalJson $ExecutorPricesUrl
        $nqContract = [string]$nq.resolved_contract
        $ymContract = [string]$ym.resolved_contract
        $nqPrice = $livePrices.last_prices.$nqContract
        $ymPrice = $livePrices.last_prices.$ymContract
        $current = [PSCustomObject]@{
            NqSuccesses = [int64]$nq.price_delivery.successes
            YmSuccesses = [int64]$ym.price_delivery.successes
            NqExecutorCompleted = [int64]$executorPipeline.symbols.NQ.completed
            YmExecutorCompleted = [int64]$executorPipeline.symbols.YM.completed
            NqTradeManagerCompleted = [int64]$executorPipeline.symbols.NQ.counts.completed_by_trade_manager
            YmTradeManagerCompleted = [int64]$executorPipeline.symbols.YM.counts.completed_by_trade_manager
        }

        $healthCurrent = $updatedAge -ge -5 -and $updatedAge -le 15
        $loginAndSubscriptions = $nq.connection_state -eq "CONNECTED" -and
            $ym.connection_state -eq "CONNECTED" -and
            $nq.subscription_state -eq "ACTIVE" -and
            $ym.subscription_state -eq "ACTIVE" -and
            -not [string]::IsNullOrWhiteSpace([string]$nq.resolved_contract) -and
            -not [string]::IsNullOrWhiteSpace([string]$ym.resolved_contract)

        $nqPostAge = if ($nq.last_successful_executor_price_post_timestamp_utc) {
            ([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse([string]$nq.last_successful_executor_price_post_timestamp_utc)).TotalSeconds
        } else { [double]::PositiveInfinity }
        $ymPostAge = if ($ym.last_successful_executor_price_post_timestamp_utc) {
            ([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse([string]$ym.last_successful_executor_price_post_timestamp_utc)).TotalSeconds
        } else { [double]::PositiveInfinity }
        $publicationCurrent = $current.NqSuccesses -gt 0 -and
            $current.YmSuccesses -gt 0 -and
            $current.NqExecutorCompleted -gt 0 -and
            $current.YmExecutorCompleted -gt 0 -and
            $current.NqTradeManagerCompleted -gt 0 -and
            $current.YmTradeManagerCompleted -gt 0 -and
            $nqPostAge -ge -5 -and $nqPostAge -le 30 -and
            $ymPostAge -ge -5 -and $ymPostAge -le 30

        $bridgeHealthy = $nq.price_bridge_status -eq "LIVE" -and
            $ym.price_bridge_status -eq "LIVE" -and
            $nq.last_executor_price_post_failure_reason -ne "stale_listener_generation" -and
            $ym.last_executor_price_post_failure_reason -ne "stale_listener_generation"
        $pricesPresent = $null -ne $nqPrice -and $null -ne $ymPrice
        $ok = $healthCurrent -and $loginAndSubscriptions -and $bridgeHealthy -and $publicationCurrent -and $pricesPresent

        $reasonParts = @()
        if (-not $healthCurrent) { $reasonParts += ("feed_health_age_seconds:{0:N1}" -f $updatedAge) }
        if (-not $loginAndSubscriptions) { $reasonParts += "repository_login_or_subscription_not_ready" }
        if ($nq.last_executor_price_post_failure_reason -eq "stale_listener_generation" -or $ym.last_executor_price_post_failure_reason -eq "stale_listener_generation") { $reasonParts += "stale_listener_generation" }
        if (-not $bridgeHealthy) { $reasonParts += ("price_bridge_status:NQ={0},YM={1}" -f $nq.price_bridge_status, $ym.price_bridge_status) }
        if (-not $publicationCurrent) { $reasonParts += "nq_ym_publication_not_current" }
        if (-not $pricesPresent) { $reasonParts += "executor_nq_ym_prices_missing" }
        $reason = if ($ok) { "single_listener_service_login_subscriptions_generation_bridge_and_publication_confirmed" } else { $reasonParts -join ";" }

        return New-ProbeResult $ok $reason ([PSCustomObject]@{
            Process = $process
            HealthUpdatedAtUtc = $health.updated_at_utc
            HealthAgeSeconds = [math]::Round($updatedAge, 3)
            NQ = [PSCustomObject]@{
                Contract = $nq.resolved_contract
                Connection = $nq.connection_state
                Subscription = $nq.subscription_state
                TickTimestampUtc = $nq.last_tick_timestamp_utc
                Price = $nqPrice
                BridgeStatus = $nq.price_bridge_status
                FailureReason = $nq.last_executor_price_post_failure_reason
                PriceDelivery = $nq.price_delivery
                ExecutorGeneration = $executorPipeline.symbols.NQ.last_listener_generation
            }
            YM = [PSCustomObject]@{
                Contract = $ym.resolved_contract
                Connection = $ym.connection_state
                Subscription = $ym.subscription_state
                TickTimestampUtc = $ym.last_tick_timestamp_utc
                Price = $ymPrice
                BridgeStatus = $ym.price_bridge_status
                FailureReason = $ym.last_executor_price_post_failure_reason
                PriceDelivery = $ym.price_delivery
                ExecutorGeneration = $executorPipeline.symbols.YM.last_listener_generation
            }
            Baseline = $script:ListenerObservation
            Current = $current
            NqLastSuccessfulPostAgeSeconds = [math]::Round($nqPostAge, 3)
            YmLastSuccessfulPostAgeSeconds = [math]::Round($ymPostAge, 3)
        })
    }
    catch {
        return New-ProbeResult $false ("listener_bridge_probe_error:{0}" -f $_.Exception.Message)
    }
}

function Get-CanonicalAtrWarmupEvidence {
    try {
        $response = Invoke-LocalJsonResponse $EntryAgentStatusUrl 5
        $payload = $response.Payload
        if ([int]$response.StatusCode -notin @(200, 503) -or $null -eq $payload -or $null -eq $payload.symbols) {
            return [PSCustomObject]@{
                Valid = $false
                Ready = $false
                Reason = "entry_canonical_atr_projection_unavailable"
                Symbols = [ordered]@{}
            }
        }

        $expectedSession = Get-MarketSessionDate
        $validationFailures = @()
        $warmingReasons = @()
        $observations = [ordered]@{}
        foreach ($symbolRoot in @("NQ", "YM")) {
            $entryRows = @($payload.symbols | Where-Object { $_.symbol -eq $symbolRoot } | Select-Object -First 1)
            if ($entryRows.Count -ne 1) {
                $validationFailures += ("{0}:entry_canonical_atr_projection_missing" -f $symbolRoot)
                continue
            }

            $record = $entryRows[0]
            $canonical = $record.canonical_atr
            $included = [int]$record.atr_included_bar_count
            $required = [int]$record.atr_required_bar_count
            $lastBar = [string]$record.atr_last_included_bar
            $authorityEpoch = if ($canonical) { [string]$canonical.atr_authority_epoch_id } else { "" }
            $source = [string]$record.atr_source
            $sessionDate = if ($canonical -and $canonical.session_date) { [string]$canonical.session_date } elseif ($record.market_context) { [string]$record.market_context.session_date } else { "" }
            $contract = [string]$record.atr_contract_symbol
            $barAgeSeconds = $null
            if (-not [string]::IsNullOrWhiteSpace($lastBar)) {
                try {
                    $barAgeSeconds = [math]::Round(([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse($lastBar)).TotalSeconds, 3)
                }
                catch {
                    $barAgeSeconds = $null
                }
            }

            if ($required -ne $CanonicalAtrRequiredTrueRangeCount) { $validationFailures += ("{0}:required_count_mismatch:{1}" -f $symbolRoot, $required) }
            if ($included -lt 0) { $validationFailures += ("{0}:included_count_negative" -f $symbolRoot) }
            if ($source -ne "rithmic_exchange_time_rma14") { $validationFailures += ("{0}:canonical_authority_invalid" -f $symbolRoot) }
            if ($included -gt 0) {
                if ($sessionDate -ne $expectedSession) { $validationFailures += ("{0}:session_not_current" -f $symbolRoot) }
                if ([string]::IsNullOrWhiteSpace($contract)) { $validationFailures += ("{0}:contract_missing" -f $symbolRoot) }
                if ([string]::IsNullOrWhiteSpace($lastBar) -or $null -eq $barAgeSeconds -or $barAgeSeconds -gt 180) { $validationFailures += ("{0}:last_completed_candle_not_current" -f $symbolRoot) }
            }

            $ready = $record.canonical_atr_ready -eq $true -and
                $null -ne $record.atr_1m_14 -and
                -not [string]::IsNullOrWhiteSpace([string]$record.atr_record_id)
            if ($ready -and [string]::IsNullOrWhiteSpace($authorityEpoch)) { $validationFailures += ("{0}:authority_epoch_missing" -f $symbolRoot) }
            if (-not $ready) {
                $warmingReasons += ("{0}:atr_warming:{1}/{2}:{3}" -f $symbolRoot, $included, $required, [string]$record.atr_readiness_reason)
            }
            $observations[$symbolRoot] = [PSCustomObject]@{
                Symbol = $symbolRoot
                Contract = $contract
                SessionDate = $sessionDate
                AtrIncludedCount = $included
                AtrRequiredCount = $required
                LastCompletedCandleTime = $lastBar
                AuthorityEpoch = $authorityEpoch
                Ready = $ready
                AtrValue = $record.atr_1m_14
                RecordId = $record.atr_record_id
                ReadinessReason = $record.atr_readiness_reason
                Source = $source
                BarAgeSeconds = $barAgeSeconds
            }
        }

        $valid = $validationFailures.Count -eq 0
        $ready = $valid -and $observations.Count -eq 2 -and @($observations.Values | Where-Object { $_.Ready -ne $true }).Count -eq 0
        return [PSCustomObject]@{
            Valid = $valid
            Ready = $ready
            Reason = if (-not $valid) { $validationFailures -join ";" } elseif ($ready) { "canonical_atr_ready" } else { $warmingReasons -join ";" }
            ExpectedSession = $expectedSession
            Symbols = $observations
        }
    }
    catch {
        return [PSCustomObject]@{
            Valid = $false
            Ready = $false
            Reason = ("entry_canonical_atr_projection_error:{0}" -f $_.Exception.Message)
            Symbols = [ordered]@{}
        }
    }
}

function Get-MarketDataReadinessObservation {
    $serviceAvailable = $Results.Contains("TradeManager") -and
        $Results.Contains("RithmicListenerBridge") -and
        $Results["TradeManager"].Status -eq "READY" -and
        $Results["RithmicListenerBridge"].Status -eq "READY"
    if (-not $serviceAvailable) {
        return [PSCustomObject]@{
            ServiceAvailable = $false
            Valid = $false
            AuthorityReady = $false
            Phase = "SERVICE_UNAVAILABLE"
            Reason = "dependency_unavailable:TradeManager_or_RithmicListenerBridge"
            Symbols = [ordered]@{}
        }
    }

    $listenerEvidence = $Results["RithmicListenerBridge"].Evidence
    $nqContract = [string]$listenerEvidence.NQ.Contract
    $ymContract = [string]$listenerEvidence.YM.Contract
    if ([string]::IsNullOrWhiteSpace($nqContract) -or [string]::IsNullOrWhiteSpace($ymContract)) {
        return [PSCustomObject]@{
            ServiceAvailable = $true
            Valid = $false
            AuthorityReady = $false
            Phase = "SERVICE_UNAVAILABLE"
            Reason = "listener_contract_authority_missing"
            Symbols = [ordered]@{}
        }
    }

    $candles = Get-CanonicalCompletedCandleEvidence $nqContract $ymContract
    $atr = Get-CanonicalAtrWarmupEvidence
    $valid = $candles.Valid -eq $true -and $atr.Valid -eq $true
    $authorityReady = $valid -and $candles.Ok -eq $true -and $atr.Ready -eq $true
    $phase = if (-not $candles.Ok) {
        "COMPLETED_CANDLE_WARMING"
    }
    elseif (-not $atr.Ready) {
        "ATR_WARMING"
    }
    else {
        "READY_WAITING_FOR_ADVANCEMENT"
    }
    $symbols = [ordered]@{}
    foreach ($symbolRoot in @("NQ", "YM")) {
        $candle = $candles.$symbolRoot
        $atrRecord = $atr.Symbols[$symbolRoot]
        $symbols[$symbolRoot] = [PSCustomObject]@{
            Symbol = $symbolRoot
            Contract = if ($symbolRoot -eq "NQ") { $nqContract } else { $ymContract }
            CompletedCandleCount = if ($candle) { [int]$candle.CurrentSessionCompletedCount } else { 0 }
            LastCompletedCandleTime = if ($candle) { $candle.LastCompletedCandleTime } else { $null }
            CompletedCandleCurrent = if ($candle) { $candle.Current } else { $false }
            AtrIncludedCount = if ($atrRecord) { [int]$atrRecord.AtrIncludedCount } else { 0 }
            AtrRequiredCount = if ($atrRecord) { [int]$atrRecord.AtrRequiredCount } else { $CanonicalAtrRequiredTrueRangeCount }
            AuthorityEpoch = if ($atrRecord) { $atrRecord.AuthorityEpoch } else { $null }
            AtrReady = if ($atrRecord) { $atrRecord.Ready } else { $false }
        }
    }
    return [PSCustomObject]@{
        ServiceAvailable = $true
        Valid = $valid
        AuthorityReady = $authorityReady
        Phase = $phase
        Reason = if (-not $valid) { "candles=$($candles.Reason);atr=$($atr.Reason)" } elseif ($authorityReady) { "source_authority_ready" } else { "candles=$($candles.Reason);atr=$($atr.Reason)" }
        ExpectedSession = Get-MarketSessionDate
        Symbols = $symbols
    }
}

function Wait-ForMarketDataReadiness {
    $observationStartedAt = [DateTime]::UtcNow
    $lastProgressAt = $observationStartedAt
    $previousObservation = $null
    $progressAdvanced = $false
    $lastLoggedSignature = ""

    while ($true) {
        $observation = Get-MarketDataReadinessObservation
        $now = [DateTime]::UtcNow
        $progressThisPoll = $false
        if ($null -ne $previousObservation -and $observation.Valid -eq $true) {
            foreach ($symbolRoot in @("NQ", "YM")) {
                $previous = $previousObservation.Symbols[$symbolRoot]
                $current = $observation.Symbols[$symbolRoot]
                if ($null -eq $previous -or $null -eq $current) {
                    $observation.Valid = $false
                    $observation.Reason = ("{0}:market_progress_record_missing" -f $symbolRoot)
                    continue
                }
                if ($current.CompletedCandleCount -lt $previous.CompletedCandleCount -or $current.AtrIncludedCount -lt $previous.AtrIncludedCount -or
                    (-not [string]::IsNullOrWhiteSpace([string]$previous.LastCompletedCandleTime) -and [string]$current.LastCompletedCandleTime -lt [string]$previous.LastCompletedCandleTime)) {
                    $observation.Valid = $false
                    $observation.Reason = ("{0}:market_readiness_progress_regressed" -f $symbolRoot)
                }
                if (-not [string]::IsNullOrWhiteSpace([string]$previous.AuthorityEpoch) -and
                    -not [string]::IsNullOrWhiteSpace([string]$current.AuthorityEpoch) -and
                    [string]$previous.AuthorityEpoch -ne [string]$current.AuthorityEpoch) {
                    $observation.Valid = $false
                    $observation.Reason = ("{0}:authority_epoch_changed_during_observation" -f $symbolRoot)
                }
                if ($current.CompletedCandleCount -gt $previous.CompletedCandleCount -or
                    $current.AtrIncludedCount -gt $previous.AtrIncludedCount -or
                    [string]$current.LastCompletedCandleTime -gt [string]$previous.LastCompletedCandleTime) {
                    $progressThisPoll = $true
                }
            }
        }
        if ($progressThisPoll) {
            $progressAdvanced = $true
            $lastProgressAt = $now
        }

        $elapsedSeconds = [math]::Round(($now - $observationStartedAt).TotalSeconds, 3)
        $secondsSinceProgress = [math]::Round(($now - $lastProgressAt).TotalSeconds, 3)
        $state = Resolve-MarketReadinessState `
            -ServiceAvailable ($observation.ServiceAvailable -eq $true) `
            -ObservationValid ($observation.Valid -eq $true) `
            -AuthorityReady ($observation.AuthorityReady -eq $true) `
            -ProgressAdvanced $progressAdvanced `
            -ElapsedSeconds $elapsedSeconds `
            -SecondsSinceProgress $secondsSinceProgress `
            -MaximumObservationSeconds $MarketReadinessObservationSeconds `
            -StallSeconds $MarketReadinessStallSeconds `
            -Phase $observation.Phase `
            -DetailReason $observation.Reason

        $evidence = [PSCustomObject]@{
            Status = $state.Status
            Phase = $observation.Phase
            TradingReady = $state.TradingReady
            ProgressAdvanced = $progressAdvanced
            ProgressAdvancedThisPoll = $progressThisPoll
            SecondsSinceProgress = $secondsSinceProgress
            ElapsedSeconds = $elapsedSeconds
            MaximumObservationSeconds = $MarketReadinessObservationSeconds
            StallSeconds = $MarketReadinessStallSeconds
            FirstCompleteCandleMaximumSeconds = $FirstCompleteCandleMaximumSeconds
            CanonicalAtrRequiredTrueRangeCount = $CanonicalAtrRequiredTrueRangeCount
            CanonicalAtrWarmupMaximumSeconds = $CanonicalAtrWarmupMaximumSeconds
            SchedulingAllowanceSeconds = $MarketReadinessSchedulingAllowanceSeconds
            ExpectedSession = $observation.ExpectedSession
            Symbols = $observation.Symbols
            DetailReason = $observation.Reason
        }
        $symbolProgress = @($observation.Symbols.Keys | ForEach-Object {
            $item = $observation.Symbols[$_]
            "{0}:candle={1}:atr={2}/{3}:last={4}:epoch={5}" -f $_, $item.CompletedCandleCount, $item.AtrIncludedCount, $item.AtrRequiredCount, $item.LastCompletedCandleTime, $item.AuthorityEpoch
        }) -join ","
        $signature = "status=$($state.Status)|phase=$($observation.Phase)|progress=$progressAdvanced|symbols=$symbolProgress"
        if ($signature -ne $lastLoggedSignature) {
            Write-StartupLine ("MARKET_READINESS STATUS={0} PHASE={1} TRADING_READY={2} PROGRESS_ADVANCING={3} ELAPSED_SECONDS={4} MAXIMUM_SECONDS={5} SYMBOLS={6}" -f $state.Status, $observation.Phase, $state.TradingReady, $progressAdvanced, $elapsedSeconds, $MarketReadinessObservationSeconds, $symbolProgress)
            $lastLoggedSignature = $signature
        }

        if ($state.Status -in @("READY", "FAILED")) {
            return [PSCustomObject]@{ Status = $state.Status; Reason = $state.Reason; Evidence = $evidence }
        }
        if ($elapsedSeconds -ge $MarketReadinessObservationSeconds) {
            return [PSCustomObject]@{ Status = "WARMING"; Reason = $state.Reason; Evidence = $evidence }
        }
        $previousObservation = $observation
        Start-Sleep -Seconds 5
    }
}

function Test-CommandCenterContract {
    if (-not (Test-Path -LiteralPath $CommandCenterPath -PathType Leaf)) {
        return New-ProbeResult $false "command_center_html_missing"
    }
    try {
        $content = Get-Content -LiteralPath $CommandCenterPath -Raw -ErrorAction Stop
        $ok = $content -match 'http://127\.0\.0\.1:6001' -and
            $content -match 'http://127\.0\.0\.1:7001' -and
            $content -match 'http://127\.0\.0\.1:7002' -and
            $content -match '/entry/status\?symbols=NQ,YM'
        $reason = if ($ok) { "static_command_center_targets_live_executor_trade_manager_and_entry_agent" } else { "command_center_endpoint_contract_mismatch" }
        return New-ProbeResult $ok $reason ([PSCustomObject]@{
            Path = $CommandCenterPath
            Mode = "static_html_client"
        })
    }
    catch {
        return New-ProbeResult $false ("command_center_read_error:{0}" -f $_.Exception.Message)
    }
}

function Test-CanonicalAtrContract {
    $projection = Get-CanonicalAtrWarmupEvidence
    $ok = $projection.Valid -eq $true -and $projection.Ready -eq $true
    $reason = if ($ok) { "current_rithmic_rma_ready_in_entry_projection" } else { [string]$projection.Reason }
    return New-ProbeResult $ok $reason $projection
}

function Get-NgrokProcesses {
    $byCommand = @(Get-ManagedProcesses "ngrok" '\bhttp\s+7001\b')
    if ($byCommand.Count -gt 0) {
        return $byCommand
    }
    $byPort = @()
    foreach ($owner in @(Get-PortOwners 4040)) {
        $process = Get-Process -Id ([int]$owner.OwningProcess) -ErrorAction SilentlyContinue
        if ($null -ne $process -and $process.ProcessName -eq "ngrok") {
            $byPort += [PSCustomObject]@{
                ProcessId = $process.Id
                ParentProcessId = $null
                Name = $process.ProcessName
                CreationDate = $process.StartTime
                ExecutablePath = $process.Path
                CommandLine = "ngrok http 7001"
            }
        }
    }
    return $byPort
}

function Invoke-BoundedPublicHealthJson {
    param(
        [string]$Uri,
        [int]$TimeoutSeconds = 5,
        [ValidateSet("GET", "POST")]
        [string]$Method = "GET",
        [object]$Body = $null,
        [string]$QueryTokenEnvironment = ""
    )

    if (-not (Test-Path -LiteralPath $PublicHealthHelperPath -PathType Leaf)) {
        throw "public_health_helper_missing:$PublicHealthHelperPath"
    }
    if (-not (Test-Path -LiteralPath $script:repositoryRoot -PathType Container)) {
        throw "public_health_working_directory_invalid:$script:repositoryRoot"
    }
    [string]$python = $script:pythonExecutable
    $token = [Guid]::NewGuid().ToString("N")
    $stdoutPath = Join-Path $env:TEMP ("randle_public_health_{0}.out" -f $token)
    $stderrPath = Join-Path $env:TEMP ("randle_public_health_{0}.err" -f $token)
    $payloadPath = $null
    $process = $null
    try {
        $arguments = @($PublicHealthHelperPath, "--url", $Uri, "--timeout-seconds", [string]$TimeoutSeconds, "--method", $Method)
        if ($Method -eq "POST") {
            $payloadPath = Join-Path $env:TEMP ("randle_public_health_{0}.json" -f $token)
            [IO.File]::WriteAllText($payloadPath, ($Body | ConvertTo-Json -Depth 8 -Compress), (New-Object Text.UTF8Encoding($false)))
            $arguments += @("--json-file", $payloadPath)
        }
        if (-not [string]::IsNullOrWhiteSpace($QueryTokenEnvironment)) {
            $arguments += @("--query-token-env", $QueryTokenEnvironment)
        }
        $process = Start-Process -FilePath $python `
            -ArgumentList $arguments `
            -WorkingDirectory $script:repositoryRoot `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath `
            -WindowStyle Hidden `
            -PassThru `
            -ErrorAction Stop
        if (-not $process.WaitForExit(($TimeoutSeconds + 2) * 1000)) {
            $process.Kill()
            throw "public_health_process_timeout"
        }
        $stdout = if (Test-Path -LiteralPath $stdoutPath) { [IO.File]::ReadAllText($stdoutPath) } else { "" }
        $stderr = if (Test-Path -LiteralPath $stderrPath) { [IO.File]::ReadAllText($stderrPath) } else { "" }
        if ([string]::IsNullOrWhiteSpace($stdout)) {
            throw ("public_health_empty_response:{0}" -f $stderr.Trim())
        }
        $result = $stdout | ConvertFrom-Json -ErrorAction Stop
        if ($process.ExitCode -ne 0 -or $result.ok -ne $true) {
            throw ("public_health_failed:{0}" -f [string]$result.error)
        }
        return $result.health
    }
    finally {
        if (Test-Path -LiteralPath $stdoutPath) { [IO.File]::Delete($stdoutPath) }
        if (Test-Path -LiteralPath $stderrPath) { [IO.File]::Delete($stderrPath) }
        if ($payloadPath -and (Test-Path -LiteralPath $payloadPath)) { [IO.File]::Delete($payloadPath) }
    }
}

function Test-NgrokContract {
    $cached = $script:NgrokProcess
    $processes = @(
        if ($null -ne $cached -and $null -ne (Get-Process -Id ([int]$cached.ProcessId) -ErrorAction SilentlyContinue)) {
            $cached
        }
        else {
            Get-NgrokProcesses
        }
    )
    if ($processes.Count -ne 1) {
        return New-ProbeResult $false ("ngrok_process_count:{0}" -f $processes.Count) $processes
    }
    $script:NgrokProcess = $processes[0]

    try {
        $response = Invoke-LocalJson "$NgrokApiBase/tunnels" 2
        $https = @($response.tunnels | Where-Object {
            $_.proto -eq "https" -and [string]$_.config.addr -match '(localhost|127\.0\.0\.1):7001|:7001$'
        })
        if ($https.Count -ne 1) {
            $status = $null
            try { $status = Invoke-LocalJson "$NgrokApiBase/status" 2 } catch { $status = $_.Exception.Message }
            return New-ProbeResult $false ("active_https_tunnel_count:{0}" -f $https.Count) ([PSCustomObject]@{
                Process = $processes[0]
                ApiStatus = $status
                Tunnels = $response.tunnels
            })
        }

        $publicBase = ([string]$https[0].public_url).TrimEnd('/')
        $publicUri = [Uri]$publicBase
        $commandLine = [string]$processes[0].CommandLine
        $localVersion = Invoke-LocalJson $TradeManagerVersionUrl 3
        $localSafety = Invoke-LocalJson $TradeManagerSafetyUrl 4
        $orphan = $localSafety.orphan_exposure
        $safetySchema = $localSafety.ok -eq $true -and
            $null -ne $localSafety.trades -and
            $null -ne $orphan -and
            ($orphan.PSObject.Properties.Name -contains "has_orphans") -and
            ($orphan.PSObject.Properties.Name -contains "has_manager_state_issue")
        $publicHostMatches = [string]::Equals($publicUri.Host, $script:ngrokPublicHost, [StringComparison]::OrdinalIgnoreCase)
        $inspectionDisabled = $commandLine -match '(?i)--inspect=false'
        $ok = $publicHostMatches -and $inspectionDisabled -and $localVersion.ok -eq $true -and $safetySchema
        $reason = if ($ok) { "single_reserved_https_tunnel_local_trade_authority_and_inspection_disabled_confirmed" } else { "ngrok_governed_tunnel_contract_mismatch" }
        return New-ProbeResult $ok $reason ([PSCustomObject]@{
            Process = $processes[0]
            PublicBaseUrl = $publicBase
            PublicWebhookUrl = "$publicBase/webhook/tv-context"
            Tunnel = $https[0]
            ExpectedPublicHost = $script:ngrokPublicHost
            PublicHostMatches = $publicHostMatches
            InspectionDisabled = $inspectionDisabled
            LocalTradeVersion = $localVersion
            LocalTradeSafetySchema = $safetySchema
            VerificationMode = "local_ngrok_api_reserved_route_plus_trade_authority"
        })
    }
    catch {
        return New-ProbeResult $false ("ngrok_probe_error:{0}" -f $_.Exception.Message) $processes[0]
    }
}

function Invoke-ExecutorJournalMaintenance {
    if (-not (Test-Path -LiteralPath $ExecutorJournalMaintenancePath -PathType Leaf)) {
        throw "executor_journal_maintenance_helper_missing:$ExecutorJournalMaintenancePath"
    }
    if (-not (Test-Path -LiteralPath $script:repositoryRoot -PathType Container)) {
        throw "executor_journal_maintenance_working_directory_invalid:$script:repositoryRoot"
    }
    [string]$python = $script:pythonExecutable
    $stdoutPath = Join-Path $script:startupLogDirectory ("ExecutorJournalMaintenance_{0}.stdout.log" -f $LaunchId)
    $stderrPath = Join-Path $script:startupLogDirectory ("ExecutorJournalMaintenance_{0}.stderr.log" -f $LaunchId)
    Write-StartupLine "COMPONENT=Executor ACTION=JOURNAL_MAINTENANCE TIMEOUT_SECONDS=$ExecutorJournalMaintenanceTimeoutSeconds"
    $process = Start-Process -FilePath $python `
        -ArgumentList @($ExecutorJournalMaintenancePath, "--journal-root", $script:executorTickJournalDirectory) `
        -WorkingDirectory $script:repositoryRoot `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -WindowStyle Hidden `
        -PassThru `
        -ErrorAction Stop
    if (-not $process.WaitForExit($ExecutorJournalMaintenanceTimeoutSeconds * 1000)) {
        $process.Kill()
        throw "executor_journal_maintenance_timeout"
    }
    $process.WaitForExit()
    $process.Refresh()
    $stdout = if (Test-Path -LiteralPath $stdoutPath) { [IO.File]::ReadAllText($stdoutPath).Trim() } else { "" }
    $stderr = if (Test-Path -LiteralPath $stderrPath) { [IO.File]::ReadAllText($stderrPath).Trim() } else { "" }
    $result = if (-not [string]::IsNullOrWhiteSpace($stdout)) { $stdout | ConvertFrom-Json -ErrorAction Stop } else { $null }
    if ($null -eq $result -or $result.ok -ne $true) {
        throw ("executor_journal_maintenance_failed:{0}" -f $stderr)
    }
    Write-StartupLine ("COMPONENT=Executor ACTION=JOURNAL_MAINTENANCE_COMPLETE RESULT={0}" -f $stdout)
}

function Invoke-TradeManagerJournalMaintenance {
    if (-not (Test-Path -LiteralPath $TradeManagerJournalMaintenancePath -PathType Leaf)) {
        throw "trade_manager_journal_maintenance_script_missing:$TradeManagerJournalMaintenancePath"
    }
    if (-not (Test-Path -LiteralPath $TradeManagerPersistencePath -PathType Leaf)) {
        throw "trade_manager_persistence_missing:$TradeManagerPersistencePath"
    }
    if (-not (Test-Path -LiteralPath $script:tradeManagerTickJournalDirectory -PathType Container)) {
        throw "trade_manager_tick_journal_directory_missing:$script:tradeManagerTickJournalDirectory"
    }
    if (-not (Test-Path -LiteralPath $script:executorTickJournalDirectory -PathType Container)) {
        throw "executor_tick_journal_directory_missing:$script:executorTickJournalDirectory"
    }

    [string]$python = $script:pythonExecutable
    $stdoutPath = Join-Path $script:startupLogDirectory ("TradeManagerJournalMaintenance_{0}.stdout.log" -f $LaunchId)
    $stderrPath = Join-Path $script:startupLogDirectory ("TradeManagerJournalMaintenance_{0}.stderr.log" -f $LaunchId)
    Write-StartupLine "COMPONENT=TradeManager ACTION=JOURNAL_MAINTENANCE TIMEOUT_SECONDS=$TradeManagerJournalMaintenanceTimeoutSeconds"
    $process = Start-Process -FilePath $python `
        -ArgumentList @(
            $TradeManagerJournalMaintenancePath,
            "--journal-root", $script:tradeManagerTickJournalDirectory,
            "--executor-journal-root", $script:executorTickJournalDirectory,
            "--persistence-file", $TradeManagerPersistencePath
        ) `
        -WorkingDirectory $script:repositoryRoot `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -WindowStyle Hidden `
        -PassThru `
        -ErrorAction Stop
    if (-not $process.WaitForExit($TradeManagerJournalMaintenanceTimeoutSeconds * 1000)) {
        $process.Kill()
        throw "trade_manager_journal_maintenance_timeout"
    }
    $process.WaitForExit()
    $process.Refresh()
    $stdout = if (Test-Path -LiteralPath $stdoutPath) { [IO.File]::ReadAllText($stdoutPath).Trim() } else { "" }
    $stderr = if (Test-Path -LiteralPath $stderrPath) { [IO.File]::ReadAllText($stderrPath).Trim() } else { "" }
    $result = if (-not [string]::IsNullOrWhiteSpace($stdout)) { $stdout | ConvertFrom-Json -ErrorAction Stop } else { $null }
    if ($null -eq $result -or $result.ok -ne $true) {
        throw ("trade_manager_journal_maintenance_failed:{0}" -f $stderr)
    }
    Write-StartupLine ("COMPONENT=TradeManager ACTION=JOURNAL_MAINTENANCE_COMPLETE RESULT={0}" -f $stdout)
}

function Get-NgrokFailureEvidence {
    param([object]$LastProbe)

    $apiStatus = $null
    $apiTunnels = $null
    try { $apiStatus = Invoke-LocalJson "$NgrokApiBase/status" 2 } catch { $apiStatus = $_.Exception.Message }
    try { $apiTunnels = Invoke-LocalJson "$NgrokApiBase/tunnels" 2 } catch { $apiTunnels = $_.Exception.Message }
    $logs = $ChildLogs["Ngrok"]
    return [PSCustomObject]@{
        LastProbe = $LastProbe
        ApiStatus = $apiStatus
        ApiTunnels = $apiTunnels
        StdoutTail = if ($logs) { Get-LogTail $logs.Stdout } else { @() }
        StderrTail = if ($logs) { Get-LogTail $logs.Stderr } else { @() }
    }
}

function Ensure-Executor {
    Write-StartupLine "COMPONENT=Executor ACTION=START_OR_PRESERVE TIMEOUT_SECONDS=$ServiceTimeoutSeconds"
    $probe = Test-ExecutorContract
    if ($probe.Ok) {
        Set-ComponentResult "Executor" "READY" "preserved_healthy_instance" $probe.Evidence
        return
    }

    $processes = @(Get-ManagedProcesses "python" $ExecutorMarker)
    if ($processes.Count -gt 1) {
        Set-ComponentResult "Executor" "FAILED" ("duplicate_instances:{0}" -f $processes.Count) $processes
        return
    }
    if ($processes.Count -eq 0) {
        if (-not (Test-PortFree 6001)) {
            Set-ComponentResult "Executor" "FAILED" "port_6001_owned_by_non_executor" (Get-PortOwners 6001)
            return
        }
        try {
            Invoke-ExecutorJournalMaintenance
            [string]$python = $script:pythonExecutable
            Start-ManagedProcess "Executor" $python @("executor.py") | Out-Null
        }
        catch {
            Set-ComponentResult "Executor" "FAILED" ("process_start_failed:{0}" -f $_.Exception.Message)
            return
        }
    }
    else {
        Write-StartupLine "COMPONENT=Executor ACTION=PRESERVE_EXISTING_STARTING_PROCESS PID=$($processes[0].ProcessId)"
    }

    $probe = Wait-ForContract "Executor" $ServiceTimeoutSeconds { Test-ExecutorContract }
    if ($probe.Ok) {
        Set-ComponentResult "Executor" "READY" $probe.Reason $probe.Evidence
    }
    else {
        Set-ComponentResult "Executor" "FAILED" ("timeout:{0}" -f $probe.Reason) $probe.Evidence
    }
}

function Ensure-TradeManager {
    Write-StartupLine "COMPONENT=TradeManager ACTION=START_OR_PRESERVE TIMEOUT_SECONDS=$ServiceTimeoutSeconds"
    $probe = Test-TradeManagerContract
    if ($probe.Ok) {
        Set-ComponentResult "TradeManager" "READY" "preserved_healthy_instance" $probe.Evidence
        return
    }

    $processes = @(Get-GovernedWrappedServiceProcesses "trade_manager")
    if ($processes.Count -gt 1) {
        Set-ComponentResult "TradeManager" "FAILED" ("duplicate_instances:{0}" -f $processes.Count) $processes
        return
    }
    if ($processes.Count -eq 0) {
        if ((Test-MutexOwned $TradeManagerAuthorityMutexName)) {
            Set-ComponentResult "TradeManager" "FAILED" "authority_mutex_owned_without_readable_process"
            return
        }
        if (-not (Test-PortFree 7001)) {
            Set-ComponentResult "TradeManager" "FAILED" "port_7001_owned_by_non_trade_manager" (Get-PortOwners 7001)
            return
        }
        try {
            Invoke-TradeManagerJournalMaintenance
        }
        catch {
            Set-ComponentResult "TradeManager" "FAILED" ("journal_maintenance_failed:{0}" -f $_.Exception.Message)
            return
        }
        try {
            [string]$python = $script:pythonExecutable
            Start-ManagedProcess "TradeManager" $python @($ServiceWrapperPath, "--service", "trade_manager") | Out-Null
        }
        catch {
            Set-ComponentResult "TradeManager" "FAILED" ("process_start_failed:{0}" -f $_.Exception.Message)
            return
        }
    }
    else {
        Write-StartupLine "COMPONENT=TradeManager ACTION=PRESERVE_EXISTING_STARTING_PROCESS PID=$($processes[0].ProcessId)"
    }

    $probe = Wait-ForContract "TradeManager" $ServiceTimeoutSeconds { Test-TradeManagerContract }
    if ($probe.Ok) {
        Set-ComponentResult "TradeManager" "READY" $probe.Reason $probe.Evidence
    }
    else {
        Set-ComponentResult "TradeManager" "FAILED" ("timeout:{0}" -f $probe.Reason) $probe.Evidence
    }
}

function Ensure-EntryAgentAndRelay {
    Write-StartupLine "COMPONENT=EntryAgent ACTION=START_OR_PRESERVE TIMEOUT_SECONDS=$ServiceTimeoutSeconds"
    $probe = Test-EntryAgentContract
    if (-not $probe.Ok) {
        $processes = @(Get-GovernedWrappedServiceProcesses "entry_agent")
        if ($processes.Count -gt 1) {
            Set-ComponentResult "EntryAgent" "FAILED" ("duplicate_instances:{0}" -f $processes.Count) $processes
        }
        elseif ($processes.Count -eq 0) {
            if (-not (Test-PortFree 7002)) {
                Set-ComponentResult "EntryAgent" "FAILED" "port_7002_owned_by_non_entry_agent" (Get-PortOwners 7002)
            }
            else {
                try {
                    [string]$python = $script:pythonExecutable
                    Start-ManagedProcess "EntryAgent" $python @($ServiceWrapperPath, "--service", "entry_agent") | Out-Null
                    $probe = Wait-ForContract "EntryAgent" $ServiceTimeoutSeconds { Test-EntryAgentContract }
                    if ($probe.Ok) {
                        Set-ComponentResult "EntryAgent" "READY" $probe.Reason $probe.Evidence
                    }
                    else {
                        Set-ComponentResult "EntryAgent" "FAILED" ("timeout:{0}" -f $probe.Reason) $probe.Evidence
                    }
                }
                catch {
                    Set-ComponentResult "EntryAgent" "FAILED" ("process_start_failed:{0}" -f $_.Exception.Message)
                }
            }
        }
        else {
            Write-StartupLine "COMPONENT=EntryAgent ACTION=PRESERVE_EXISTING_STARTING_PROCESS PID=$($processes[0].ProcessId)"
            $probe = Wait-ForContract "EntryAgent" $ServiceTimeoutSeconds { Test-EntryAgentContract }
            if ($probe.Ok) {
                Set-ComponentResult "EntryAgent" "READY" $probe.Reason $probe.Evidence
            }
            else {
                Set-ComponentResult "EntryAgent" "FAILED" ("timeout:{0}" -f $probe.Reason) $probe.Evidence
            }
        }
    }
    else {
        Set-ComponentResult "EntryAgent" "READY" $probe.Reason $probe.Evidence
    }

    Write-StartupLine "COMPONENT=TradingViewRelay ACTION=VERIFY_LIQUIDITY_ONLY_RELAY TIMEOUT_SECONDS=10"
    if ($Results["EntryAgent"].Status -eq "READY") {
        $relayProbe = Wait-ForContract "TradingViewRelay" 10 { Test-TradingViewRelayContract }
        if ($relayProbe.Ok) {
            Set-ComponentResult "TradingViewRelay" "READY" $relayProbe.Reason $relayProbe.Evidence
        }
        else {
            Set-ComponentResult "TradingViewRelay" "FAILED" ("timeout:{0}" -f $relayProbe.Reason) $relayProbe.Evidence
        }
    }
    else {
        Set-ComponentResult "TradingViewRelay" "FAILED" "dependency_failed:EntryAgent"
    }
}

function Ensure-ListenerBridge {
    Write-StartupLine "COMPONENT=RithmicListenerBridge ACTION=START_OR_PRESERVE TIMEOUT_SECONDS=$ListenerTimeoutSeconds"
    if ($Results["Executor"].Status -ne "READY" -or $Results["TradeManager"].Status -ne "READY") {
        Set-ComponentResult "RithmicListenerBridge" "FAILED" "dependency_failed:Executor_or_TradeManager"
        return
    }

    $processes = @(Get-ManagedProcesses "python" $ListenerMarker)
    if ($processes.Count -gt 1) {
        Set-ComponentResult "RithmicListenerBridge" "FAILED" ("duplicate_instances:{0}" -f $processes.Count) $processes
        return
    }
    if ($processes.Count -eq 0) {
        if (Test-MutexOwned $ListenerAuthorityMutexName) {
            Set-ComponentResult "RithmicListenerBridge" "FAILED" "authority_mutex_owned_without_readable_process"
            return
        }
        try {
            [string]$python = $script:pythonExecutable
            $started = Start-ManagedProcess "RithmicListener" $python @("rithmic_live_listener.py")
            $script:ListenerProcess = [PSCustomObject]@{
                ProcessId = $started.Id
                ParentProcessId = $PID
                Name = $started.ProcessName
                CreationDate = $started.StartTime
                ExecutablePath = $python
                CommandLine = ('"{0}" rithmic_live_listener.py' -f $python)
            }
        }
        catch {
            Set-ComponentResult "RithmicListenerBridge" "FAILED" ("process_start_failed:{0}" -f $_.Exception.Message)
            return
        }
    }
    else {
        $script:ListenerProcess = $processes[0]
        Write-StartupLine "COMPONENT=RithmicListenerBridge ACTION=PRESERVE_EXISTING_PROCESS PID=$($processes[0].ProcessId)"
    }

    $script:ListenerObservation = $null
    $probe = Wait-ForContract "RithmicListenerBridge" $ListenerTimeoutSeconds { Test-ListenerBridgeContract }
    if ($probe.Ok) {
        Set-ComponentResult "RithmicListenerBridge" "READY" $probe.Reason $probe.Evidence
    }
    else {
        Set-ComponentResult "RithmicListenerBridge" "FAILED" ("timeout:{0}" -f $probe.Reason) $probe.Evidence
    }
}

function Verify-MarketDataReadiness {
    Write-StartupLine ("COMPONENT=MarketDataReadiness ACTION=OBSERVE_CANDLES_AND_CANONICAL_ATR MAXIMUM_SECONDS={0} POLICY=first_complete_candle:{1}+true_ranges:{2}x{3}+scheduling_allowance:{4}" -f $MarketReadinessObservationSeconds, $FirstCompleteCandleMaximumSeconds, $CanonicalAtrRequiredTrueRangeCount, $CanonicalMinuteSeconds, $MarketReadinessSchedulingAllowanceSeconds)
    if ($Results["TradeManager"].Status -ne "READY" -or $Results["RithmicListenerBridge"].Status -ne "READY") {
        Set-ComponentResult "MarketDataReadiness" "FAILED" "dependency_failed:TradeManager_or_RithmicListenerBridge"
        return
    }

    $result = Wait-ForMarketDataReadiness
    Set-ComponentResult "MarketDataReadiness" $result.Status $result.Reason $result.Evidence
}

function Verify-EntryCurrentSession {
    $entryCurrentSessionTimeoutSeconds = 130
    Write-StartupLine "COMPONENT=EntryAgentCurrentSession ACTION=VERIFY_TODAY_STATE TIMEOUT_SECONDS=$entryCurrentSessionTimeoutSeconds"
    $script:ComponentTimeouts["EntryAgentCurrentSession"] = $entryCurrentSessionTimeoutSeconds
    if ($Results["EntryAgent"].Status -ne "READY") {
        Set-ComponentResult "EntryAgentCurrentSession" "FAILED" "dependency_failed:EntryAgent"
        return
    }
    if ($Results["MarketDataReadiness"].Status -eq "WARMING") {
        Set-ComponentResult "EntryAgentCurrentSession" "WARMING" "dependency_warming:MarketDataReadiness" $Results["MarketDataReadiness"].Evidence
        return
    }
    if ($Results["MarketDataReadiness"].Status -ne "READY") {
        Set-ComponentResult "EntryAgentCurrentSession" "FAILED" "dependency_failed:MarketDataReadiness" $Results["MarketDataReadiness"].Evidence
        return
    }
    $probe = Wait-ForContract "EntryAgentCurrentSession" $entryCurrentSessionTimeoutSeconds { Test-EntryCurrentSessionContract }
    if ($probe.Ok) {
        Set-ComponentResult "EntryAgentCurrentSession" "READY" $probe.Reason $probe.Evidence
    }
    else {
        Set-ComponentResult "EntryAgentCurrentSession" "FAILED" ("timeout:{0}" -f $probe.Reason) $probe.Evidence
    }
}

function Verify-CommandCenter {
    Write-StartupLine "COMPONENT=CommandCenter ACTION=VERIFY_STATIC_CLIENT_CONTRACT TIMEOUT_SECONDS=1"
    $probe = Test-CommandCenterContract
    if ($probe.Ok) {
        Set-ComponentResult "CommandCenter" "READY" $probe.Reason $probe.Evidence
    }
    else {
        Set-ComponentResult "CommandCenter" "FAILED" $probe.Reason $probe.Evidence
    }
}

function Verify-CanonicalAtr {
    Write-StartupLine "COMPONENT=CanonicalATR ACTION=VERIFY_READY_SOURCE_AND_ENTRY_PROJECTION TIMEOUT_SECONDS=$ServiceTimeoutSeconds"
    if ($Results["TradeManager"].Status -ne "READY") {
        Set-ComponentResult "CanonicalATR" "FAILED" "dependency_failed:TradeManager"
        return
    }
    if ($Results["MarketDataReadiness"].Status -eq "WARMING") {
        Set-ComponentResult "CanonicalATR" "WARMING" "dependency_warming:MarketDataReadiness" $Results["MarketDataReadiness"].Evidence
        return
    }
    if ($Results["MarketDataReadiness"].Status -ne "READY") {
        Set-ComponentResult "CanonicalATR" "FAILED" "dependency_failed:MarketDataReadiness" $Results["MarketDataReadiness"].Evidence
        return
    }
    $probe = Wait-ForContract "CanonicalATR" $ServiceTimeoutSeconds { Test-CanonicalAtrContract }
    if ($probe.Ok) {
        Set-ComponentResult "CanonicalATR" "READY" $probe.Reason $probe.Evidence
    }
    else {
        Set-ComponentResult "CanonicalATR" "FAILED" ("timeout:{0}" -f $probe.Reason) $probe.Evidence
    }
}

function Ensure-Ngrok {
    Write-StartupLine "COMPONENT=Ngrok ACTION=START_OR_PRESERVE TIMEOUT_SECONDS=$NgrokTimeoutSeconds"
    if ($Results["TradeManager"].Status -ne "READY") {
        Set-ComponentResult "Ngrok" "FAILED" "dependency_failed:TradeManager"
        return
    }

    $script:NgrokReadinessStartedAt = [DateTime]::UtcNow
    $script:TradingViewContextBaseline = [ordered]@{}
    try {
        $relayBefore = Invoke-LocalJson $TradingViewRelayHealthUrl 3
        foreach ($symbolRoot in @("NQ", "YM")) {
            $script:TradingViewContextBaseline[$symbolRoot] = [string]$relayBefore.symbols.$symbolRoot.last_tv_context_received_at
        }
    }
    catch {
        foreach ($symbolRoot in @("NQ", "YM")) { $script:TradingViewContextBaseline[$symbolRoot] = "" }
    }

    $probe = Test-NgrokContract
    if ($probe.Ok) {
        Set-ComponentResult "Ngrok" "READY" "preserved_healthy_tunnel" $probe.Evidence
        return
    }

    $processes = @(Get-NgrokProcesses)
    if ($processes.Count -gt 1) {
        Set-ComponentResult "Ngrok" "FAILED" ("duplicate_instances:{0}" -f $processes.Count) $processes
        return
    }
    if ($processes.Count -eq 0) {
        try {
            $ngrokCommand = Get-Command ngrok.exe -CommandType Application -ErrorAction Stop
            $ngrokExecutable = (Resolve-Path -LiteralPath ([string]$ngrokCommand.Source) -ErrorAction Stop).ProviderPath
            if (-not (Test-Path -LiteralPath $ngrokExecutable -PathType Leaf)) {
                Set-ComponentResult "Ngrok" "FAILED" ("executable_invalid:{0}" -f $ngrokExecutable) ([PSCustomObject]@{
                    Executable = $ngrokExecutable
                })
                return
            }

            $ngrokWorkingDirectory = [IO.Path]::GetDirectoryName($ngrokExecutable)
            $nativeLogPath = Join-Path $script:startupLogDirectory ("Ngrok_{0}.native.log" -f $LaunchId)
            $ngrokArguments = @("http", "7001", "--url", $script:ngrokPublicUrl, "--inspect=false", ("--log={0}" -f $nativeLogPath), "--log-level=info")
            Write-StartupLine ("COMPONENT=Ngrok ACTION=START_RESOLVED EXECUTABLE={0} WORKING_DIRECTORY={1} ARGUMENTS={2} LOG_PATH={3}" -f $ngrokExecutable, $ngrokWorkingDirectory, ($ngrokArguments -join " "), $nativeLogPath)
            $ngrokWorkingDirectoryInvalid = [string]::IsNullOrWhiteSpace([string]$ngrokWorkingDirectory) -or
                -not [IO.Path]::IsPathRooted([string]$ngrokWorkingDirectory) -or
                [string]$ngrokWorkingDirectory -in @("NQ", "YM") -or
                -not (Test-Path -LiteralPath $ngrokWorkingDirectory -PathType Container)
            if ($ngrokWorkingDirectoryInvalid) {
                $invalidWorkingDirectory = if ([string]::IsNullOrWhiteSpace([string]$ngrokWorkingDirectory)) { "<empty>" } else { [string]$ngrokWorkingDirectory }
                Set-ComponentResult "Ngrok" "FAILED" ("invalid_working_directory:{0}" -f $invalidWorkingDirectory) ([PSCustomObject]@{
                    Executable = $ngrokExecutable
                    WorkingDirectory = $ngrokWorkingDirectory
                    Arguments = $ngrokArguments
                    LogPath = $nativeLogPath
                })
                return
            }

            $started = Start-Process -FilePath $ngrokExecutable `
                -ArgumentList $ngrokArguments `
                -WorkingDirectory $ngrokWorkingDirectory `
                -WindowStyle Hidden `
                -PassThru `
                -ErrorAction Stop
            if ($null -eq $started -or [int]$started.Id -le 0) {
                throw "ngrok_start_returned_no_pid"
            }
            $script:ChildLogs["Ngrok"] = [PSCustomObject]@{
                Pid = $started.Id
                Stdout = $nativeLogPath
                Stderr = $null
            }
            $script:NgrokProcess = [PSCustomObject]@{
                ProcessId = $started.Id
                ParentProcessId = $PID
                Name = $started.ProcessName
                CreationDate = $started.StartTime
                ExecutablePath = $ngrokExecutable
                CommandLine = ('"{0}" {1}' -f $ngrokExecutable, ($ngrokArguments -join ' '))
                WorkingDirectory = $ngrokWorkingDirectory
            }
        }
        catch {
            Set-ComponentResult "Ngrok" "FAILED" ("process_start_failed:{0}" -f $_.Exception.Message)
            return
        }
    }
    else {
        $script:NgrokProcess = $processes[0]
        Write-StartupLine "COMPONENT=Ngrok ACTION=PRESERVE_EXISTING_CONNECTING_PROCESS PID=$($processes[0].ProcessId)"
    }

    $probe = Wait-ForContract "Ngrok" $NgrokTimeoutSeconds { Test-NgrokContract }
    if ($probe.Ok) {
        Set-ComponentResult "Ngrok" "READY" $probe.Reason $probe.Evidence
    }
    else {
        Set-ComponentResult "Ngrok" "FAILED" ("timeout:{0}" -f $probe.Reason) (Get-NgrokFailureEvidence $probe)
    }
}

function Get-FinalDiagnostics {
    # Component probes already captured process and port ownership. Reusing that
    # proof avoids a second series of WMI scans after readiness has terminated.
    function Get-EvidenceProperty {
        param([object]$Evidence, [string]$Name)
        if ($null -eq $Evidence) { return $null }
        $property = $Evidence.PSObject.Properties[$Name]
        if ($null -eq $property) { return $null }
        return $property.Value
    }

    $componentEvidence = @{}
    foreach ($componentName in @("Executor", "TradeManager", "EntryAgent", "RithmicListenerBridge", "Ngrok")) {
        $componentResult = $Results[$componentName]
        $componentEvidence[$componentName] = if ($null -ne $componentResult -and
            $null -ne $componentResult.PSObject.Properties["Evidence"]) {
            $componentResult.Evidence
        }
        else {
            $null
        }
    }
    $ngrokResult = $Results["Ngrok"]
    $ngrokEvidence = $componentEvidence["Ngrok"]
    $ngrokProcess = if ($null -ne $ngrokResult -and $ngrokResult.Status -eq "READY") {
        Get-EvidenceProperty $ngrokEvidence "Process"
    }
    elseif ($null -ne (Get-EvidenceProperty $ngrokEvidence "LastProbe")) {
        Get-EvidenceProperty (Get-EvidenceProperty $ngrokEvidence "LastProbe") "Evidence"
    }
    else {
        $null
    }

    $processDefinitions = @(
        [PSCustomObject]@{ Component = "Executor"; Process = Get-EvidenceProperty $componentEvidence["Executor"] "Process" },
        [PSCustomObject]@{ Component = "TradeManager"; Process = Get-EvidenceProperty $componentEvidence["TradeManager"] "Process" },
        [PSCustomObject]@{ Component = "EntryAgentAndTradingViewRelay"; Process = Get-EvidenceProperty $componentEvidence["EntryAgent"] "Process" },
        [PSCustomObject]@{ Component = "RithmicListenerBridge"; Process = Get-EvidenceProperty $componentEvidence["RithmicListenerBridge"] "Process" },
        [PSCustomObject]@{ Component = "Ngrok"; Process = $ngrokProcess }
    )
    $inventory = @()
    foreach ($definition in $processDefinitions) {
        foreach ($process in @($definition.Process)) {
            if ($null -eq $process -or $null -eq $process.ProcessId) {
                continue
            }
            $inventory += [PSCustomObject]@{
                Component = $definition.Component
                Pid = $process.ProcessId
                ParentPid = $process.ParentProcessId
                StartTime = $process.CreationDate
                ExecutablePath = $process.ExecutablePath
                CommandLine = $process.CommandLine
            }
        }
    }

    $ports = @(
        @(Get-EvidenceProperty $componentEvidence["Executor"] "PortOwners") +
        @(Get-EvidenceProperty $componentEvidence["TradeManager"] "PortOwners") +
        @(Get-EvidenceProperty $componentEvidence["EntryAgent"] "PortOwners")
    )

    return [PSCustomObject]@{
        CapturedAtUtc = [DateTime]::UtcNow.ToString("o")
        Processes = $inventory
        Ports = $ports
        ChildLogs = $ChildLogs
    }
}

Write-StartupLine "STARTUP_BEGIN launch_id=$LaunchId repository_root=$script:repositoryRoot runtime_data_root=$script:runtimeDataRoot" Cyan
Write-StartupLine ("STARTUP_POLICY bounded=true preserve_healthy=true duplicate_policy=reject tradingview_authority=liquidity_only service_timeout_seconds={0} market_readiness_maximum_seconds={1} market_formula=({2}x{3})+({4}x{3})+({5}x{3})" -f $ServiceTimeoutSeconds, $MarketReadinessObservationSeconds, $FirstCompleteCandleIntervalCount, $CanonicalMinuteSeconds, $CanonicalAtrRequiredTrueRangeCount, $MarketReadinessSchedulingAllowanceIntervals)

try {
    $writeAuthority = Test-ProductionWriteAuthority
    Set-ComponentResult "ProductionWriteAuthority" $(if ($writeAuthority.Ok) { "READY" } else { "FAILED" }) $writeAuthority.Reason $writeAuthority.Evidence
    if (-not $writeAuthority.Ok) { throw "production_write_authority_gate_failed" }
    $preExecutorSafety = Test-PreExecutorStartSafetyGate
    Set-ComponentResult "PreExecutorStartSafetyGate" $(if ($preExecutorSafety.Ok) { "READY" } else { "FAILED" }) $preExecutorSafety.Reason $preExecutorSafety.Evidence
    if (-not $preExecutorSafety.Ok) { throw "pre_executor_start_safety_gate_failed" }
    Ensure-Executor
    $startupExposure = Test-StartupExposureGate
    Set-ComponentResult "StartupExposureGate" $(if ($startupExposure.Ok) { "READY" } else { "FAILED" }) $startupExposure.Reason $startupExposure.Evidence
    if (-not $startupExposure.Ok) { throw "startup_exposure_gate_failed" }
    Ensure-EntryAgentAndRelay
    Ensure-TradeManager
    Ensure-ListenerBridge
    Ensure-Ngrok
    Verify-MarketDataReadiness
    Verify-EntryCurrentSession
    Verify-CommandCenter
    Verify-CanonicalAtr
}
catch {
    $script:ComponentTimeouts["Orchestration"] = 0
    Set-ComponentResult "Orchestration" "FAILED" ("unhandled_orchestration_exception:{0}" -f $_.Exception.Message)
}

$requiredComponents = @(
    "ProductionWriteAuthority",
    "PreExecutorStartSafetyGate",
    "Executor",
    "StartupExposureGate",
    "TradeManager",
    "EntryAgent",
    "TradingViewRelay",
    "RithmicListenerBridge",
    "MarketDataReadiness",
    "EntryAgentCurrentSession",
    "CommandCenter",
    "CanonicalATR",
    "Ngrok"
)
$failedComponents = @($requiredComponents | Where-Object {
    -not $Results.Contains($_) -or $Results[$_].Status -eq "FAILED"
})
$warmingComponents = @($requiredComponents | Where-Object {
    $Results.Contains($_) -and $Results[$_].Status -eq "WARMING"
})

if ($failedComponents.Count -gt 0) {
    Set-ComponentResult "ReadinessVerification" "FAILED" ("failed_components:{0}" -f ($failedComponents -join ","))
}
elseif ($warmingComponents.Count -gt 0) {
    Set-ComponentResult "ReadinessVerification" "WARMING" ("warming_components:{0};trading_readiness=false" -f ($warmingComponents -join ","))
}
else {
    Set-ComponentResult "ReadinessVerification" "READY" "all_required_component_contracts_passed"
}

$diagnostics = Get-FinalDiagnostics
Write-StartupLine "FINALIZATION_STEP=diagnostics_captured"
$durationSeconds = [math]::Round(([DateTime]::UtcNow - $StartupStartedAt).TotalSeconds, 3)
$finalStatus = if ($failedComponents.Count -gt 0) { "FAILED" } elseif ($warmingComponents.Count -gt 0) { "WARMING" } else { "READY" }
$resultSummaries = @()
foreach ($name in $Results.Keys) {
    $result = $Results[$name]
    $resultSummaries += [PSCustomObject]@{
        Component = $name
        Status = $result.Status
        Reason = $result.Reason
        TimeoutSeconds = $result.TimeoutSeconds
        CheckedAtUtc = $result.CheckedAtUtc
    }
}
$evidence = [PSCustomObject]@{
    LaunchId = $LaunchId
    StartedAtUtc = $StartupStartedAt.ToString("o")
    CompletedAtUtc = [DateTime]::UtcNow.ToString("o")
    DurationSeconds = $durationSeconds
    FinalStatus = $finalStatus
    TradingReadiness = $finalStatus -eq "READY"
    FailedComponents = $failedComponents
    WarmingComponents = $warmingComponents
    Timeouts = $ComponentTimeouts
    MarketReadinessPolicy = [PSCustomObject]@{
        CanonicalMinuteSeconds = $CanonicalMinuteSeconds
        FirstCompleteCandleIntervalCount = $FirstCompleteCandleIntervalCount
        FirstCompleteCandleMaximumSeconds = $FirstCompleteCandleMaximumSeconds
        CanonicalAtrRequiredTrueRangeCount = $CanonicalAtrRequiredTrueRangeCount
        CanonicalAtrWarmupMaximumSeconds = $CanonicalAtrWarmupMaximumSeconds
        SchedulingAllowanceIntervals = $MarketReadinessSchedulingAllowanceIntervals
        SchedulingAllowanceSeconds = $MarketReadinessSchedulingAllowanceSeconds
        MaximumObservationSeconds = $MarketReadinessObservationSeconds
        StallSeconds = $MarketReadinessStallSeconds
    }
    Results = $resultSummaries
    Diagnostics = $diagnostics
    StartupLogPath = $StartupLogPath
}
$evidenceJson = $evidence | ConvertTo-Json -Depth 8
Write-StartupLine "FINALIZATION_STEP=evidence_serialized bytes=$([Text.Encoding]::UTF8.GetByteCount($evidenceJson))"
[System.IO.File]::WriteAllText($EvidencePath, $evidenceJson, [System.Text.UTF8Encoding]::new($false))
Write-StartupLine "FINALIZATION_STEP=evidence_written path=$EvidencePath"

Write-StartupLine "STARTUP_SUMMARY_BEGIN" Cyan
foreach ($name in $Results.Keys) {
    $result = $Results[$name]
    Write-StartupLine ("SUMMARY component={0} status={1} timeout_seconds={2} reason={3}" -f $name, $result.Status, $result.TimeoutSeconds, $result.Reason)
}
Write-StartupLine "STARTUP_SUMMARY_END" Cyan
Write-StartupLine "STARTUP_RESULT=$finalStatus trading_readiness=$($finalStatus -eq 'READY') duration_seconds=$durationSeconds evidence=$EvidencePath" $(if ($finalStatus -eq "READY") { [ConsoleColor]::Green } elseif ($finalStatus -eq "WARMING") { [ConsoleColor]::Yellow } else { [ConsoleColor]::Red })

if ($finalStatus -eq "READY") {
    exit 0
}
if ($finalStatus -eq "WARMING") {
    exit 2
}
exit 1
