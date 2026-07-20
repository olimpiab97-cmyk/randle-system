[CmdletBinding()]
param(
    [ValidateRange(5, 300)]
    [int]$ServiceTimeoutSeconds = 30,

    [ValidateRange(5, 300)]
    [int]$ListenerTimeoutSeconds = 60,

    [ValidateRange(5, 120)]
    [int]$NgrokTimeoutSeconds = 75,

    [ValidateRange(30, 300)]
    [int]$AtrTimeoutSeconds = 90
)

$script:repositoryRoot = [IO.Path]::GetFullPath($PSScriptRoot)
if (-not (Test-Path -LiteralPath $script:repositoryRoot -PathType Container)) {
    throw "repository_root_invalid:$script:repositoryRoot"
}
$runtimeDataRootCandidate = if ($env:RANDLE_DATA_ROOT) { $env:RANDLE_DATA_ROOT } else { Join-Path $script:repositoryRoot "Data" }
$script:runtimeDataRoot = [IO.Path]::GetFullPath($runtimeDataRootCandidate)
$StartupStartedAt = [DateTime]::UtcNow
$LaunchId = Get-Date -Format "yyyyMMdd_HHmmss"
$script:startupLogDirectory = Join-Path $script:runtimeDataRoot "startup"
$StartupLogPath = Join-Path $script:startupLogDirectory "launch_$LaunchId.log"
$EvidencePath = Join-Path $script:startupLogDirectory "launch_$LaunchId.evidence.json"

$ExecutorHealthUrl = "http://127.0.0.1:6001/health"
$ExecutorPipelineUrl = "http://127.0.0.1:6001/debug/tick_pipeline"
$ExecutorPricesUrl = "http://127.0.0.1:6001/debug/live_prices"
$TradeManagerHealthUrl = "http://127.0.0.1:7001/health"
$TradeManagerPipelineUrl = "http://127.0.0.1:7001/debug/tick_pipeline"
$TradeManagerCanonicalAtrStatusUrl = "http://127.0.0.1:7001/debug/canonical/atr_status"
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
$script:executorTickJournalDirectory = Join-Path $env:LOCALAPPDATA "RandleRuntimeData\executor_tick_authority"
$ExecutorJournalMaintenanceTimeoutSeconds = 300

$ExecutorMarker = '\bexecutor\.py\b'
$TradeManagerMarker = '\bEngines[\\/]trade_manager\.py\b'
$EntryAgentMarker = '\bEntryAgent[\\/]tv_context_server\.py\b'
$ListenerMarker = '\brithmic_live_listener\.py\b'

$ComponentTimeouts = [ordered]@{
    Executor = $ServiceTimeoutSeconds
    TradeManager = $ServiceTimeoutSeconds
    EntryAgent = $ServiceTimeoutSeconds
    TradingViewRelay = 10
    RithmicListenerBridge = $ListenerTimeoutSeconds
    CommandCenter = 1
    CanonicalATR = $AtrTimeoutSeconds
    Ngrok = $NgrokTimeoutSeconds
    ReadinessVerification = 5
}

$Results = [ordered]@{}
$ChildLogs = [ordered]@{}
$ListenerObservation = $null
$ListenerProcess = $null
$NgrokProcess = $null
$CanonicalAtrBaseline = $null
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
        [ValidateSet("READY", "FAILED")]
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

    $color = if ($Status -eq "READY") { [ConsoleColor]::Green } else { [ConsoleColor]::Red }
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
        $requestError = $_.Exception.Message
        $errorResponse = $_.Exception.Response
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
        if ([string]::IsNullOrWhiteSpace($content) -and -not [string]::IsNullOrWhiteSpace([string]$_.ErrorDetails.Message)) {
            $content = [string]$_.ErrorDetails.Message
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
    $processes = @(Get-ManagedProcesses "python" $TradeManagerMarker)
    if ($processes.Count -ne 1) {
        return New-ProbeResult $false ("trade_manager_process_count:{0}" -f $processes.Count) $processes
    }

    try {
        $health = Invoke-LocalJson $TradeManagerHealthUrl
        $pipeline = Invoke-LocalJson $TradeManagerPipelineUrl
        $atr = Invoke-LocalJson $TradeManagerCanonicalAtrStatusUrl
        $portOwners = @(Get-PortOwners 7001)
        $processId = [int]$health.pid
        $pidMatches = @($processes.ProcessId) -contains $processId
        $portMatches = @($portOwners.OwningProcess) -contains $processId
        $ok = $health.ok -eq $true -and
            $pipeline.ok -eq $true -and
            $null -ne $atr -and
            $health.authority_mutex -eq $TradeManagerAuthorityMutexName -and
            $health.tick_pipeline_version -eq "trade_manager_symbol_fifo_wal_v3" -and
            (Test-MutexOwned $TradeManagerAuthorityMutexName) -and
            $pidMatches -and
            $portMatches
        $reason = if ($ok) { "authority_health_required_endpoints_and_port_owner_confirmed" } else { "trade_manager_contract_mismatch" }
        return New-ProbeResult $ok $reason ([PSCustomObject]@{
            Pid = $processId
            Health = $health
            Pipeline = $pipeline
            AtrEndpointResponded = $null -ne $atr
            PortOwners = $portOwners
            Process = $processes[0]
        })
    }
    catch {
        return New-ProbeResult $false ("trade_manager_endpoint_error:{0}" -f $_.Exception.Message)
    }
}

function Test-EntryAgentContract {
    $processes = @(Get-ManagedProcesses "python" $EntryAgentMarker)
    if ($processes.Count -ne 1) {
        return New-ProbeResult $false ("entry_agent_process_count:{0}" -f $processes.Count) $processes
    }

    try {
        $response = Invoke-LocalJsonResponse $EntryAgentStatusUrl 4
        $status = $response.Payload
        $portOwners = @(Get-PortOwners 7002)
        $processId = [int]$processes[0].ProcessId
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
            $baseEvidence["RehydrationFailures"] = $status.rehydration_failures
            $baseEvidence["Symbols"] = $status.symbols
            $reasonDetail = if ($rehydrationFailures.Count -gt 0) { $rehydrationFailures -join "," } else { "reason_unavailable" }
            return New-ProbeResult $false ("entry_agent_fail_closed_rehydrating:{0}" -f $reasonDetail) ([PSCustomObject]$baseEvidence)
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
        $baseEvidence["Symbols"] = $symbolRoots
        return New-ProbeResult $ok $reason ([PSCustomObject]$baseEvidence)
    }
    catch {
        return New-ProbeResult $false ("entry_agent_endpoint_error:{0}" -f $_.Exception.Message)
    }
}

function Test-TradingViewRelayContract {
    $processes = @(Get-ManagedProcesses "python" $EntryAgentMarker)
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
        $tradeManagerPipeline = Invoke-LocalJson $TradeManagerPipelineUrl
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
            NqTradeManagerCompleted = [int64]$tradeManagerPipeline.symbols.NQ.completed
            YmTradeManagerCompleted = [int64]$tradeManagerPipeline.symbols.YM.completed
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
        $reason = if ($ok) { "single_listener_login_subscriptions_generation_bridge_and_publication_confirmed" } else { $reasonParts -join ";" }

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
    try {
        $payload = Invoke-LocalJson $TradeManagerCanonicalAtrStatusUrl 4
        $entryPayload = Invoke-LocalJson $EntryAgentStatusUrl 4
        if ($payload.ok -ne $true -or $null -eq $payload.symbols) {
            return New-ProbeResult $false "canonical_atr_payload_invalid" $payload
        }

        $records = @()
        if ($payload.symbols -is [System.Collections.IDictionary] -or $payload.symbols.PSObject.Properties.Name -contains "NQ") {
            foreach ($symbolRoot in @("NQ", "YM")) {
                $record = $payload.symbols.$symbolRoot
                if ($null -ne $record) {
                    $records += [PSCustomObject]@{ Symbol = $symbolRoot; Record = $record }
                }
            }
        }
        else {
            foreach ($record in @($payload.symbols)) {
                $symbolRoot = [string]($record.symbol)
                if ($symbolRoot -in @("NQ", "YM")) {
                    $records += [PSCustomObject]@{ Symbol = $symbolRoot; Record = $record }
                }
            }
        }

        $expectedSession = Get-MarketSessionDate
        $failures = @()
        $observations = [ordered]@{}
        foreach ($symbolRoot in @("NQ", "YM")) {
            $wrapped = @($records | Where-Object { $_.Symbol -eq $symbolRoot } | Select-Object -First 1)
            if ($wrapped.Count -ne 1) {
                $failures += "${root}:canonical_record_missing"
                continue
            }
            $record = $wrapped[0].Record
            $canonical = $record.canonical_record
            $entry = @($entryPayload.symbols | Where-Object { $_.symbol -eq $symbolRoot } | Select-Object -First 1)
            $value = if ($record.PSObject.Properties.Name -contains "atr_value") { $record.atr_value } elseif ($record.PSObject.Properties.Name -contains "atr_1m_14") { $record.atr_1m_14 } else { $canonical.atr_value }
            $source = [string]$canonical.atr_source
            $lastBar = [string]$record.last_included_bar
            $included = [int]$record.included_bar_count
            $required = [int]$record.required_bar_count
            $barAgeSeconds = $null
            try { $barAgeSeconds = [math]::Round(([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse($lastBar)).TotalSeconds, 3) } catch { $barAgeSeconds = $null }

            if ($record.ready -ne $true -or $null -eq $value) { $failures += ("{0}:warming:{1}/{2}:{3}" -f $symbolRoot, $included, $required, [string]$record.readiness_reason) }
            if ([string]$record.session_date -ne $expectedSession) { $failures += "${root}:session_not_current" }
            if ([string]::IsNullOrWhiteSpace([string]$record.contract_symbol)) { $failures += "${root}:contract_missing" }
            if ([string]::IsNullOrWhiteSpace($lastBar) -or $null -eq $barAgeSeconds -or $barAgeSeconds -gt 180) { $failures += "${root}:finalized_bar_not_current" }
            if ($source -match "tradingview" -or ($record.ready -eq $true -and $source -ne "rithmic_exchange_time_rma14")) { $failures += "${root}:canonical_authority_invalid" }
            if ($entry.Count -ne 1) {
                $failures += "${root}:entry_projection_missing"
            }
            else {
                $entryRecord = $entry[0]
                if ($entryRecord.canonical_atr_ready -ne $record.ready) { $failures += "${root}:entry_readiness_mismatch" }
                if ([string]$entryRecord.atr_contract_symbol -ne [string]$record.contract_symbol) { $failures += "${root}:entry_contract_mismatch" }
                if ([string]$entryRecord.atr_observation_last_included_bar -ne $lastBar) { $failures += "${root}:entry_bar_mismatch" }
                if ($record.ready -eq $true -and [math]::Abs(([double]$entryRecord.atr_1m_14) - ([double]$value)) -gt 0.000000001) { $failures += "${root}:entry_value_mismatch" }
                if ([string]$entryRecord.atr_source -match "tradingview") { $failures += "${root}:entry_tradingview_atr_detected" }
            }
            $observations[$symbolRoot] = [PSCustomObject]@{
                Contract = $record.contract_symbol
                Session = $record.session_date
                Ready = $record.ready
                Value = $value
                Included = $included
                Required = $required
                LastIncludedBar = $lastBar
                BarAgeSeconds = $barAgeSeconds
                RecordId = $canonical.atr_record_id
                Source = $source
            }
        }

        if ($null -eq $script:CanonicalAtrBaseline) {
            $script:CanonicalAtrBaseline = [ordered]@{}
            foreach ($symbolRoot in @("NQ", "YM")) {
                if ($observations.Contains($symbolRoot)) { $script:CanonicalAtrBaseline[$symbolRoot] = $observations[$symbolRoot].LastIncludedBar }
            }
            $failures += "waiting_for_finalized_bar_advancement_after_startup"
        }
        else {
            foreach ($symbolRoot in @("NQ", "YM")) {
                if (-not $observations.Contains($symbolRoot) -or [string]::IsNullOrWhiteSpace([string]$script:CanonicalAtrBaseline[$symbolRoot]) -or [string]$observations[$symbolRoot].LastIncludedBar -le [string]$script:CanonicalAtrBaseline[$symbolRoot]) {
                    $failures += "${symbolRoot}:finalized_bar_has_not_advanced"
                }
            }
        }

        $ok = $failures.Count -eq 0
        $reason = if ($ok) { "current_rithmic_rma_ready_projected_and_finalized_bars_advanced" } else { $failures -join ";" }
        return New-ProbeResult $ok $reason ([PSCustomObject]@{
            Source = $payload.source
            Policy = $payload.policy
            ExpectedSession = $expectedSession
            Baseline = $script:CanonicalAtrBaseline
            Symbols = $observations
            Failures = $failures
        })
    }
    catch {
        return New-ProbeResult $false ("canonical_atr_endpoint_error:{0}" -f $_.Exception.Message)
    }
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
        [object]$Body = $null
    )

    if (-not (Test-Path -LiteralPath $PublicHealthHelperPath -PathType Leaf)) {
        throw "public_health_helper_missing:$PublicHealthHelperPath"
    }
    if (-not (Test-Path -LiteralPath $script:repositoryRoot -PathType Container)) {
        throw "public_health_working_directory_invalid:$script:repositoryRoot"
    }
    $python = (Get-Command python.exe -ErrorAction Stop).Source
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
        $localUpstreamHealth = Invoke-LocalJson $TradeManagerHealthUrl 2
        $publicVerificationError = $script:PublicSelfProbeDisabledReason
        if ([string]::IsNullOrWhiteSpace([string]$publicVerificationError)) {
          try {
            $publicUpstreamHealth = Invoke-BoundedPublicHealthJson "$publicBase/health" 4
            $receiptId = "startup-$LaunchId-$([Guid]::NewGuid().ToString('N'))"
            $relayPayload = [ordered]@{
                source = "startup_liquidity_relay_probe"
                receipt_id = $receiptId
                sent_at = [DateTime]::UtcNow.ToString("o")
                purpose = "startup_readiness"
            }
            $publicRelayResponse = Invoke-BoundedPublicHealthJson "$publicBase/webhook/tv-context" 4 "POST" $relayPayload
            $localReceipt = Invoke-LocalJson $TradingViewRelayReceiptUrl 2
            $entryRelayResponse = $publicRelayResponse.entry_agent_response
            $selfProbeOk = $localUpstreamHealth.ok -eq $true -and
                [int]$localUpstreamHealth.pid -gt 0 -and
                $publicUpstreamHealth.ok -eq $true -and
                [int]$publicUpstreamHealth.pid -eq [int]$localUpstreamHealth.pid -and
                $publicRelayResponse.ok -eq $true -and
                [int]$publicRelayResponse.entry_agent_status_code -eq 200 -and
                $entryRelayResponse.ok -eq $true -and
                $entryRelayResponse.liquidity_state_changed -eq $false -and
                [string]$entryRelayResponse.receipt_id -eq $receiptId -and
                [string]$localReceipt.receipt.receipt_id -eq $receiptId
            if ($selfProbeOk) {
                return New-ProbeResult $true "single_https_tunnel_public_health_and_liquidity_relay_round_trip_confirmed" ([PSCustomObject]@{
                    Process = $processes[0]
                    PublicBaseUrl = $publicBase
                    PublicWebhookUrl = "$publicBase/webhook/tv-context"
                    Tunnel = $https[0]
                    LocalUpstreamHealth = $localUpstreamHealth
                    PublicUpstreamHealth = $publicUpstreamHealth
                    RelayReceiptId = $receiptId
                    PublicRelayResponse = $publicRelayResponse
                    LocalRelayReceipt = $localReceipt
                    VerificationMode = "verified_tls_self_probe"
                })
            }
            $publicVerificationError = "public_self_probe_contract_mismatch"
          }
          catch {
            $publicVerificationError = $_.Exception.Message
          }
          $script:PublicSelfProbeDisabledReason = $publicVerificationError
        }

        $proxyStatus = Invoke-LocalJson "http://127.0.0.1:7001/debug/tv-context-proxy" 3
        $proxyState = $proxyStatus.state
        $proxyForwardedAt = $null
        try { $proxyForwardedAt = [DateTimeOffset]::Parse([string]$proxyState.last_forwarded_at) } catch { $proxyForwardedAt = $null }
        $publicHost = ([Uri]$publicBase).Host
        $freshTradingViewProxy = $proxyForwardedAt -and
            $proxyForwardedAt.UtcDateTime -ge $script:NgrokReadinessStartedAt -and
            $proxyState.last_ok -eq $true -and
            [int]$proxyState.last_status_code -eq 200 -and
            [string]$proxyState.last_user_agent -match "TradingView Webhook" -and
            [string]$proxyState.last_host -eq $publicHost
        $relayHealth = Invoke-LocalJson $TradingViewRelayHealthUrl 3
        $contextReceipts = [ordered]@{}
        $contextFailures = @()
        foreach ($symbolRoot in @("NQ", "YM")) {
            $context = $relayHealth.symbols.$symbolRoot
            $receivedAt = [string]$context.last_tv_context_received_at
            $baseline = [string]$script:TradingViewContextBaseline[$symbolRoot]
            $contextReceipts[$symbolRoot] = [PSCustomObject]@{
                Session = $context.session_date
                ReceivedAt = $receivedAt
                Baseline = $baseline
                Source = $context.source
            }
            if ([string]::IsNullOrWhiteSpace($receivedAt) -or (-not [string]::IsNullOrWhiteSpace($baseline) -and $receivedAt -le $baseline)) {
                $contextFailures += "${symbolRoot}:fresh_context_receipt_missing"
            }
        }
        $externalRoundTripOk = $localUpstreamHealth.ok -eq $true -and
            $freshTradingViewProxy -and
            $contextFailures.Count -eq 0
        $externalReason = if ($externalRoundTripOk) { "single_https_tunnel_fresh_external_tradingview_round_trip_confirmed" } else { "waiting_for_fresh_external_tradingview_round_trip:$($contextFailures -join ',')" }
        return New-ProbeResult $externalRoundTripOk $externalReason ([PSCustomObject]@{
            Process = $processes[0]
            PublicBaseUrl = $publicBase
            PublicWebhookUrl = "$publicBase/webhook/tv-context"
            Tunnel = $https[0]
            LocalUpstreamHealth = $localUpstreamHealth
            PublicSelfProbeError = $publicVerificationError
            FreshTradingViewProxy = $freshTradingViewProxy
            ProxyState = $proxyState
            ContextReceipts = $contextReceipts
            ContextFailures = $contextFailures
            VerificationMode = "trade_manager_proxy_plus_fresh_entry_receipts"
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
    $python = (Get-Command python.exe -ErrorAction Stop).Source
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
            $python = (Get-Command python.exe -ErrorAction Stop).Source
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

    $processes = @(Get-ManagedProcesses "python" $TradeManagerMarker)
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
            $python = (Get-Command python.exe -ErrorAction Stop).Source
            Start-ManagedProcess "TradeManager" $python @("Engines\trade_manager.py") | Out-Null
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
        $processes = @(Get-ManagedProcesses "python" $EntryAgentMarker)
        if ($processes.Count -gt 1) {
            Set-ComponentResult "EntryAgent" "FAILED" ("duplicate_instances:{0}" -f $processes.Count) $processes
        }
        elseif ($processes.Count -eq 0) {
            if (-not (Test-PortFree 7002)) {
                Set-ComponentResult "EntryAgent" "FAILED" "port_7002_owned_by_non_entry_agent" (Get-PortOwners 7002)
            }
            else {
                try {
                    $python = (Get-Command python.exe -ErrorAction Stop).Source
                    Start-ManagedProcess "EntryAgent" $python @("EntryAgent\tv_context_server.py") | Out-Null
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
        Set-ComponentResult "EntryAgent" "READY" "preserved_healthy_instance" $probe.Evidence
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
            $python = (Get-Command python.exe -ErrorAction Stop).Source
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

function Verify-EntryCurrentSession {
    $entryCurrentSessionTimeoutSeconds = 130
    Write-StartupLine "COMPONENT=EntryAgentCurrentSession ACTION=VERIFY_TODAY_STATE TIMEOUT_SECONDS=$entryCurrentSessionTimeoutSeconds"
    $script:ComponentTimeouts["EntryAgentCurrentSession"] = $entryCurrentSessionTimeoutSeconds
    if ($Results["EntryAgent"].Status -ne "READY") {
        Set-ComponentResult "EntryAgentCurrentSession" "FAILED" "dependency_failed:EntryAgent"
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
    Write-StartupLine "COMPONENT=CanonicalATR ACTION=VERIFY_CURRENT_READY_PROJECTED_AND_ADVANCING TIMEOUT_SECONDS=$AtrTimeoutSeconds"
    if ($Results["TradeManager"].Status -ne "READY") {
        Set-ComponentResult "CanonicalATR" "FAILED" "dependency_failed:TradeManager"
        return
    }
    $probe = Wait-ForContract "CanonicalATR" $AtrTimeoutSeconds { Test-CanonicalAtrContract }
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
            $ngrokArguments = @("http", "7001", ("--log={0}" -f $nativeLogPath), "--log-level=info")
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
    $ngrokProcess = if ($Results["Ngrok"].Status -eq "READY") {
        $Results["Ngrok"].Evidence.Process
    }
    elseif ($Results["Ngrok"].Evidence -and $Results["Ngrok"].Evidence.LastProbe) {
        $Results["Ngrok"].Evidence.LastProbe.Evidence
    }
    else {
        $null
    }

    $processDefinitions = @(
        [PSCustomObject]@{ Component = "Executor"; Process = $Results["Executor"].Evidence.Process },
        [PSCustomObject]@{ Component = "TradeManager"; Process = $Results["TradeManager"].Evidence.Process },
        [PSCustomObject]@{ Component = "EntryAgentAndTradingViewRelay"; Process = $Results["EntryAgent"].Evidence.Process },
        [PSCustomObject]@{ Component = "RithmicListenerBridge"; Process = $Results["RithmicListenerBridge"].Evidence.Process },
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
        @($Results["Executor"].Evidence.PortOwners) +
        @($Results["TradeManager"].Evidence.PortOwners) +
        @($Results["EntryAgent"].Evidence.PortOwners)
    )

    return [PSCustomObject]@{
        CapturedAtUtc = [DateTime]::UtcNow.ToString("o")
        Processes = $inventory
        Ports = $ports
        ChildLogs = $ChildLogs
    }
}

Write-StartupLine "STARTUP_BEGIN launch_id=$LaunchId repository_root=$script:repositoryRoot runtime_data_root=$script:runtimeDataRoot" Cyan
Write-StartupLine "STARTUP_POLICY bounded=true preserve_healthy=true duplicate_policy=reject tradingview_authority=liquidity_only"

try {
    Ensure-Executor
    Ensure-TradeManager
    Ensure-EntryAgentAndRelay
    Ensure-Ngrok
    Ensure-ListenerBridge
    Verify-EntryCurrentSession
    Verify-CommandCenter
    Verify-CanonicalAtr
}
catch {
    $script:ComponentTimeouts["Orchestration"] = 0
    Set-ComponentResult "Orchestration" "FAILED" ("unhandled_orchestration_exception:{0}" -f $_.Exception.Message)
}

$requiredComponents = @(
    "Executor",
    "TradeManager",
    "EntryAgent",
    "TradingViewRelay",
    "RithmicListenerBridge",
    "EntryAgentCurrentSession",
    "CommandCenter",
    "CanonicalATR",
    "Ngrok"
)
$failedComponents = @($requiredComponents | Where-Object {
    -not $Results.Contains($_) -or $Results[$_].Status -ne "READY"
})

if ($failedComponents.Count -eq 0) {
    Set-ComponentResult "ReadinessVerification" "READY" "all_required_component_contracts_passed"
}
else {
    Set-ComponentResult "ReadinessVerification" "FAILED" ("failed_components:{0}" -f ($failedComponents -join ","))
}

$diagnostics = Get-FinalDiagnostics
Write-StartupLine "FINALIZATION_STEP=diagnostics_captured"
$durationSeconds = [math]::Round(([DateTime]::UtcNow - $StartupStartedAt).TotalSeconds, 3)
$finalStatus = if ($failedComponents.Count -eq 0) { "READY" } else { "FAILED" }
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
    FailedComponents = $failedComponents
    Timeouts = $ComponentTimeouts
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
Write-StartupLine "STARTUP_RESULT=$finalStatus duration_seconds=$durationSeconds evidence=$EvidencePath" $(if ($finalStatus -eq "READY") { [ConsoleColor]::Green } else { [ConsoleColor]::Red })

if ($finalStatus -eq "READY") {
    exit 0
}
exit 1
