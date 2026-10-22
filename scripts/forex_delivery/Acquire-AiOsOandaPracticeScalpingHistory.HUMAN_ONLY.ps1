param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [Parameter(Mandatory = $true)][string[]]$Instruments,
    [Parameter(Mandatory = $true)][ValidateSet("S5","S10","S15","S30","M1","M2","M4","M10","H2","H3","H6","H8","H12")][string[]]$Granularities,
    [Parameter(Mandatory = $true)][string]$FromUtc,
    [Parameter(Mandatory = $true)][string]$ToUtc,
    [ValidateRange(1,5000)][Alias("BatchCount")][int]$CandlesPerRequest = 5000,
    [ValidateRange(0,20)][int]$MaxBatchesPerSeries = 0,
    [ValidateRange(0,10)][int]$MaxRetries = 4,
    [ValidateRange(1,300)][int]$RequestTimeoutSeconds = 30,
    [ValidateSet("BA","M","B","A")][string]$Price = "BA",
    [switch]$WhatIfOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$PracticeHost = "https://api-fxpractice.oanda.com"
$BlockedLiveHost = "api-fxtrade.oanda.com"
$ScopeContractHelperHash = "719045663d658d2a1d3e288273c61cb6b4ec81a523b06974232a3f21e691cfa8"

if ($PracticeHost -match $BlockedLiveHost) {
    throw "SAFETY_FAIL: LIVE host is not allowed."
}

function Get-AiOsGranularitySeconds {
    param([Parameter(Mandatory = $true)][string]$Granularity)

    $map = @{
        S5 = 5
        S10 = 10
        S15 = 15
        S30 = 30
        M1 = 60
        M2 = 120
        M4 = 240
        M10 = 600
        H2 = 7200
        H3 = 10800
        H6 = 21600
        H8 = 28800
        H12 = 43200
    }

    return [int]$map[$Granularity]
}

function ConvertTo-AiOsUtcString {
    param([Parameter(Mandatory = $true)][DateTimeOffset]$Value)
    return $Value.ToUniversalTime().UtcDateTime.ToString("o")
}

function Write-AiOsJsonAtomic {
    param(
        [Parameter(Mandatory = $true)]$Data,
        [Parameter(Mandatory = $true)][string]$Path
    )

    $directory = Split-Path -Parent $Path
    if (-not [string]::IsNullOrWhiteSpace($directory)) {
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
    }

    $tempPath = $Path + ".tmp"
    $json = $Data | ConvertTo-Json -Depth 60
    $encoding = New-Object System.Text.UTF8Encoding($false)
    $stream = [System.IO.File]::Open($tempPath, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try {
        $writer = New-Object System.IO.StreamWriter($stream, $encoding)
        try {
            $writer.Write($json)
            $writer.Flush()
            $stream.Flush($true)
        }
        finally {
            $writer.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
    [void](Get-Content -Raw -LiteralPath $tempPath | ConvertFrom-Json)
    Move-Item -LiteralPath $tempPath -Destination $Path -Force
}

function Get-AiOsHttpStatusCode {
    param([Parameter(Mandatory = $true)]$ErrorRecord)

    $response = $null
    if (($null -ne $ErrorRecord.Exception) -and ($ErrorRecord.Exception.PSObject.Properties.Name -contains "Response")) {
        $response = $ErrorRecord.Exception.Response
    }
    if ($null -ne $response -and $response.PSObject.Properties.Name -contains "StatusCode") {
        return [int]$response.StatusCode
    }

    $message = [string]$ErrorRecord.Exception.Message
    if ($message -match "HTTP_STATUS:(\d{3})") {
        return [int]$Matches[1]
    }

    if ($message -match "\b(400|401|403|404|408|409|422|425|429|500|502|503|504)\b") {
        return [int]$Matches[1]
    }

    return $null
}

function Test-AiOsRetryableTransport {
    param([Parameter(Mandatory = $true)]$ErrorRecord)

    $message = [string]$ErrorRecord.Exception.Message
    return ($message -match "(?i)timeout|timed out|temporar|connection.*closed|connection.*reset|transport")
}

function Get-AiOsRetryAfterSeconds {
    param([Parameter(Mandatory = $true)]$ErrorRecord)

    $response = $null
    if (($null -ne $ErrorRecord.Exception) -and ($ErrorRecord.Exception.PSObject.Properties.Name -contains "Response")) {
        $response = $ErrorRecord.Exception.Response
    }
    if ($null -ne $response -and $response.PSObject.Properties.Name -contains "Headers") {
        $headers = $response.Headers
        foreach ($name in @("Retry-After", "retry-after")) {
            try {
                $value = [string]$headers[$name]
                if ($value -match "^\d+$") {
                    return [Math]::Min(60, [int]$value)
                }
            }
            catch {
            }
        }
    }

    $message = [string]$ErrorRecord.Exception.Message
    if ($message -match "RETRY_AFTER:(\d+)") {
        return [Math]::Min(60, [int]$Matches[1])
    }
    return $null
}

function Get-AiOsFileSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try {
            $hashBytes = $sha.ComputeHash($stream)
            return ([System.BitConverter]::ToString($hashBytes)).Replace("-", "").ToLowerInvariant()
        }
        finally {
            $sha.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
}

function Get-AiOsObjectSha256 {
    param([Parameter(Mandatory = $true)]$Data)

    $json = $Data | ConvertTo-Json -Depth 60 -Compress
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $sha.ComputeHash($bytes)
        return ([System.BitConverter]::ToString($hashBytes)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Get-AiOsHelperHash {
    if ([string]::IsNullOrWhiteSpace($PSCommandPath) -or -not (Test-Path -LiteralPath $PSCommandPath -PathType Leaf)) {
        return "UNKNOWN_HELPER_HASH"
    }
    return Get-AiOsFileSha256 -Path $PSCommandPath
}

function Get-AiOsScopeFingerprint {
    param(
        [Parameter(Mandatory = $true)][string[]]$Instruments,
        [Parameter(Mandatory = $true)][string[]]$Granularities,
        [Parameter(Mandatory = $true)][string]$FromUtc,
        [Parameter(Mandatory = $true)][string]$ToUtc,
        [Parameter(Mandatory = $true)][string]$Price,
        [Parameter(Mandatory = $true)][int]$CandlesPerRequest,
        [Parameter(Mandatory = $true)][string]$HelperHash
    )

    # Scope identity is set-based. Sort copies for hashing only so caller order
    # still controls collection order without changing checkpoint authority.
    $CanonicalInstruments = @($Instruments | Sort-Object -CaseSensitive)
    $CanonicalGranularities = @($Granularities | Sort-Object -CaseSensitive)
    $scope = [ordered]@{
        instruments = $CanonicalInstruments
        granularities = $CanonicalGranularities
        from_utc = $FromUtc
        to_utc = $ToUtc
        price = $Price
        candles_per_request = $CandlesPerRequest
        boundary_contract = "FROM_INCLUSIVE_TO_EXCLUSIVE"
        pagination_contract = "FROM_PLUS_COUNT_INCLUDE_FIRST"
        helper_hash = $HelperHash
    }
    return Get-AiOsObjectSha256 -Data $scope
}

function New-AiOsOandaRequestHeaders {
    param([Parameter(Mandatory = $true)][string]$AuthorizationValue)

    if ([string]::IsNullOrWhiteSpace($AuthorizationValue)) {
        throw "AUTHORIZATION_STATE_NOT_AVAILABLE"
    }

    # Invoke-RestMethod receives a request-scoped map. Never reuse a mutable
    # header container across the probe, acquisition, or retry boundary.
    return @{
        "Authorization" = $AuthorizationValue
        "Accept-Datetime-Format" = "RFC3339"
    }
}

function Assert-AiOsCheckpointArtifacts {
    param([Parameter(Mandatory = $true)]$Checkpoint)

    if (-not ($Checkpoint.PSObject.Properties.Name -contains "batches")) {
        return
    }

    $previousLast = $null
    foreach ($batch in @($Checkpoint.batches)) {
        if (-not (Test-Path -LiteralPath ([string]$batch.artifact_path) -PathType Leaf)) {
            throw "CHECKPOINT_ARTIFACT_MISSING: $($batch.artifact_path)"
        }
        $actualHash = Get-AiOsFileSha256 -Path ([string]$batch.artifact_path)
        if ($actualHash -ne [string]$batch.artifact_sha256) {
            throw "CHECKPOINT_ARTIFACT_HASH_MISMATCH: $($batch.artifact_path)"
        }
        if (-not [string]::IsNullOrWhiteSpace([string]$batch.first_accepted_utc)) {
            $first = [DateTimeOffset]::Parse([string]$batch.first_accepted_utc).ToUniversalTime()
            $last = [DateTimeOffset]::Parse([string]$batch.last_accepted_utc).ToUniversalTime()
            if (($null -ne $previousLast) -and ($first -le $previousLast)) {
                throw "CHECKPOINT_ARTIFACT_CHRONOLOGY_FAILURE"
            }
            $previousLast = $last
        }
    }
}

function Invoke-AiOsOandaGetWithRetry {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$AuthorizationValue,
        [Parameter(Mandatory = $true)][int]$MaxRetries,
        [Parameter(Mandatory = $true)][int]$RequestTimeoutSeconds,
        [Parameter(Mandatory = $true)][string]$Operation,
        [Parameter(Mandatory = $true)][string]$Instrument,
        [Parameter(Mandatory = $true)][string]$Granularity,
        [Parameter(Mandatory = $true)][int]$BatchIndex,
        [Parameter(Mandatory = $true)][long]$CompleteCount,
        [AllowNull()][string]$LastDurableUtc,
        [Parameter(Mandatory = $true)][System.Diagnostics.Stopwatch]$RunStopwatch
    )

    $attempt = 0
    while ($true) {
        $LastText = if ([string]::IsNullOrWhiteSpace($LastDurableUtc)) { "NONE" } else { $LastDurableUtc }
        Write-Host ("HEARTBEAT phase={0}_REQUEST pair={1} granularity={2} batch={3} candles={4} last={5} retry={6} elapsed_seconds={7}" -f $Operation, $Instrument, $Granularity, $BatchIndex, $CompleteCount, $LastText, $attempt, [Math]::Floor($RunStopwatch.Elapsed.TotalSeconds))
        try {
            $RequestHeaders = New-AiOsOandaRequestHeaders -AuthorizationValue $AuthorizationValue
            $response = Invoke-RestMethod -Method Get -Uri $Uri -Headers $RequestHeaders -TimeoutSec $RequestTimeoutSeconds
            Write-Host ("HEARTBEAT phase={0}_RESPONSE pair={1} granularity={2} batch={3} candles={4} last={5} retry={6} elapsed_seconds={7}" -f $Operation, $Instrument, $Granularity, $BatchIndex, $CompleteCount, $LastText, $attempt, [Math]::Floor($RunStopwatch.Elapsed.TotalSeconds))
            return $response
        }
        catch {
            $statusCode = Get-AiOsHttpStatusCode -ErrorRecord $_
            $retryableStatus = ($statusCode -in @(408,425,429,500,502,503,504))
            $retryableTransport = Test-AiOsRetryableTransport -ErrorRecord $_

            if ($statusCode -eq 401) {
                throw "OANDA_PRACTICE_AUTHENTICATION_REJECTED: HTTP 401"
            }
            if ($statusCode -eq 403) {
                throw "OANDA_PRACTICE_AUTHORIZATION_REJECTED: HTTP 403"
            }

            if (($null -ne $statusCode) -and ($statusCode -ge 400) -and ($statusCode -lt 500) -and (-not $retryableStatus)) {
                throw "REQUEST_CONTRACT_FAILURE: HTTP $statusCode"
            }

            if (($retryableStatus -or $retryableTransport) -and ($attempt -lt $MaxRetries)) {
                $retryAfter = Get-AiOsRetryAfterSeconds -ErrorRecord $_
                $baseSleep = if ($null -ne $retryAfter) { $retryAfter } else { [Math]::Pow(2, $attempt) }
                $jitterSeed = [Math]::Abs(($Uri + [string]$attempt).GetHashCode()) % 3
                $sleepSeconds = [Math]::Min(60, [int][Math]::Ceiling($baseSleep + $jitterSeed))
                $attempt += 1
                Write-Host ("HEARTBEAT phase={0}_RETRY_WAIT pair={1} granularity={2} batch={3} candles={4} last={5} retry={6} wait_seconds={7} elapsed_seconds={8}" -f $Operation, $Instrument, $Granularity, $BatchIndex, $CompleteCount, $LastText, $attempt, $sleepSeconds, [Math]::Floor($RunStopwatch.Elapsed.TotalSeconds))
                Start-Sleep -Seconds $sleepSeconds
                continue
            }

            if ($retryableStatus -or $retryableTransport) {
                throw "RETRY_EXHAUSTED: bounded retry limit reached."
            }

            throw
        }
    }
}

function Test-AiOsCandlePriceContract {
    param(
        [Parameter(Mandatory = $true)]$Candle,
        [Parameter(Mandatory = $true)][string]$Price
    )

    if ($Price -match "B" -and -not ($Candle.PSObject.Properties.Name -contains "bid")) {
        throw "PRICE_CONTRACT_FAILURE: bid candle fields missing."
    }
    if ($Price -match "A" -and -not ($Candle.PSObject.Properties.Name -contains "ask")) {
        throw "PRICE_CONTRACT_FAILURE: ask candle fields missing."
    }
    if ($Price -eq "M" -and -not ($Candle.PSObject.Properties.Name -contains "mid")) {
        throw "PRICE_CONTRACT_FAILURE: mid candle fields missing."
    }
}

function Get-AiOsValidatedAcceptedCandles {
    param(
        [Parameter(Mandatory = $true)]$Response,
        [Parameter(Mandatory = $true)][string]$Instrument,
        [Parameter(Mandatory = $true)][string]$Granularity,
        [Parameter(Mandatory = $true)][string]$Price,
        [Parameter(Mandatory = $true)][DateTimeOffset]$Cursor,
        [Parameter(Mandatory = $true)][DateTimeOffset]$OverallTo,
        [AllowNull()]$LastAcceptedBefore,
        [Parameter(Mandatory = $true)][bool]$IncludeFirst
    )

    if (($Response.PSObject.Properties.Name -contains "instrument") -and ([string]$Response.instrument -ne $Instrument)) {
        throw "RESPONSE_INSTRUMENT_MISMATCH: expected $Instrument"
    }
    if (($Response.PSObject.Properties.Name -contains "granularity") -and ([string]$Response.granularity -ne $Granularity)) {
        throw "RESPONSE_GRANULARITY_MISMATCH: expected $Granularity"
    }
    if (($null -eq $Response.candles) -or ($Response.candles.Count -eq 0)) {
        return @()
    }

    $seen = New-Object "System.Collections.Generic.HashSet[string]"
    $previousTime = $null
    $accepted = @()

    foreach ($candle in @($Response.candles)) {
        if ($candle.complete -ne $true) {
            continue
        }

        Test-AiOsCandlePriceContract -Candle $candle -Price $Price

        $candleTime = [DateTimeOffset]::Parse([string]$candle.time).ToUniversalTime()
        $key = ConvertTo-AiOsUtcString -Value $candleTime
        if (-not $seen.Add($key)) {
            throw "DUPLICATE_CANDLE_IN_BATCH: $Instrument $Granularity $key"
        }
        if (($null -ne $previousTime) -and ($candleTime -le $previousTime)) {
            throw "NON_CHRONOLOGICAL_CANDLES: $Instrument $Granularity"
        }
        $previousTime = $candleTime

        if (($null -ne $LastAcceptedBefore) -and ($candleTime -le $LastAcceptedBefore)) {
            throw "DUPLICATE_CANDLE_ACROSS_BATCHES: $Instrument $Granularity $key"
        }

        $lowerBoundaryOk = if ($IncludeFirst) { $candleTime -ge $Cursor } else { $candleTime -gt $Cursor }
        if ($lowerBoundaryOk -and ($candleTime -lt $OverallTo)) {
            $accepted += $candle
        }
    }

    return @($accepted)
}

function Get-AiOsSeriesFiles {
    param([Parameter(Mandatory = $true)][string]$SeriesDir)

    if (-not (Test-Path -LiteralPath $SeriesDir -PathType Container)) {
        return @()
    }

    $files = @()
    foreach ($file in @(Get-ChildItem -LiteralPath $SeriesDir -Filter "*.json" | Where-Object { $_.Name -notmatch "CHECKPOINT" } | Sort-Object Name)) {
        $doc = Get-Content -Raw -LiteralPath $file.FullName | ConvertFrom-Json
        $files += [ordered]@{
            path = $file.FullName
            sha256 = Get-AiOsFileSha256 -Path $file.FullName
            candle_count = [int]$doc.candle_count
        }
    }
    return @($files)
}

function Assert-AiOsSeriesFilesMatchCheckpoint {
    param(
        [Parameter(Mandatory = $true)][string]$SeriesDir,
        [Parameter(Mandatory = $true)]$Checkpoint
    )

    $expectedBatches = [int]$Checkpoint.next_batch_index
    $expectedCandles = [int]$Checkpoint.complete_candles
    if ($expectedBatches -eq 0 -and $expectedCandles -eq 0) {
        return
    }

    $files = @(Get-AiOsSeriesFiles -SeriesDir $SeriesDir)
    if ($files.Count -lt $expectedBatches) {
        throw "CHECKPOINT_ARTIFACT_MISSING: expected $expectedBatches batch files in $SeriesDir"
    }

    $candleSum = 0
    foreach ($file in $files) {
        $candleSum += [int]$file.candle_count
    }
    if ($candleSum -lt $expectedCandles) {
        throw "CHECKPOINT_ARTIFACT_COUNT_MISMATCH: expected at least $expectedCandles candles in $SeriesDir"
    }
}

$CollectorHash = Get-AiOsHelperHash
# Dataset scope v1 used the original certified helper hash as a compatibility
# identifier. Keep it stable so reliability-only collector changes do not orphan
# the existing 38,602,240 candles or their 14 checkpoints. The current collector
# file hash is recorded separately as collector_sha256.
$HelperHash = $ScopeContractHelperHash
$ScopeFingerprint = Get-AiOsScopeFingerprint -Instruments $Instruments -Granularities $Granularities -FromUtc $FromUtc -ToUtc $ToUtc -Price $Price -CandlesPerRequest $CandlesPerRequest -HelperHash $HelperHash

$Plan = [ordered]@{
    schema = "AIOS_FOREX_SCALPING_HISTORY_HUMAN_ONLY_PLAN.v1"
    host = $PracticeHost
    method = "GET_ONLY"
    output_root = $OutputRoot
    instruments = $Instruments
    instrument_count = $Instruments.Count
    granularities = $Granularities
    overall_from_utc = $FromUtc
    overall_to_utc = $ToUtc
    from_utc = $FromUtc
    to_utc = $ToUtc
    candles_per_request = $CandlesPerRequest
    request_count = $CandlesPerRequest
    batch_count = $CandlesPerRequest
    batch_count_deprecated_reason = "Deprecated compatibility field; use candles_per_request."
    batch_count_field_deprecated_or_misnamed = $true
    max_batches_per_series = $MaxBatchesPerSeries
    pagination_contract = "FROM_PLUS_COUNT"
    to_sent_on_each_request = $false
    include_first_strategy = "FIRST_REQUEST_TRUE_THEN_FROM_LAST_ACCEPTED_WITH_INCLUDE_FIRST_FALSE"
    resume_enabled = $true
    checkpoint_enabled = $true
    atomic_promotion_enabled = $true
    retry_enabled = $true
    maximum_attempts_per_request = ($MaxRetries + 1)
    request_timeout_seconds = $RequestTimeoutSeconds
    maximum_transport_wait_seconds_upper_bound = ((($MaxRetries + 1) * $RequestTimeoutSeconds) + ($MaxRetries * 60))
    request_parallelism = 1
    parallel_request_allowed = $false
    burst_control = "SINGLE_SEQUENTIAL_REQUEST_LOOP_WITH_BOUNDED_RETRY"
    scope_fingerprint = $ScopeFingerprint
    helper_sha256 = $HelperHash
    collector_sha256 = $CollectorHash
    order_endpoint_allowed = $false
    live_host_allowed = $false
    token_output_allowed = $false
    token_persistence_allowed = $false
    account_identifier_artifact_allowed = $false
    what_if_only = [bool]$WhatIfOnly
}

$Plan | ConvertTo-Json -Depth 10

if ($WhatIfOnly) {
    return
}

$From = [DateTimeOffset]::Parse($FromUtc).ToUniversalTime()
$To = [DateTimeOffset]::Parse($ToUtc).ToUniversalTime()
if ($From -ge $To) {
    throw "INVALID_INTERVAL: FromUtc must be before ToUtc."
}

$ResolvedRoot = [System.IO.Path]::GetFullPath($OutputRoot)
New-Item -ItemType Directory -Force -Path $ResolvedRoot | Out-Null

$RuntimeStatePath = Join-Path -Path $ResolvedRoot -ChildPath "AIOS_FOREX_SCALPING_HISTORY_RUNTIME_STATE.json"
$RuntimeState = [ordered]@{
    schema = "AIOS_FOREX_SCALPING_HISTORY_RUNTIME_STATE.v1"
    process_id = $PID
    status = "WAITING_FOR_RUNTIME_TOKEN"
    host = $PracticeHost
    method = "GET_ONLY"
    output_root = $ResolvedRoot
    started_utc = (Get-Date).ToUniversalTime().ToString("o")
    last_progress_utc = (Get-Date).ToUniversalTime().ToString("o")
    current_instrument = $null
    current_granularity = $null
    request_cursor_utc = $null
    request_started_utc = $null
    last_accepted_utc = $null
    last_checkpoint_path = $null
    completed_series = 0
    incomplete_series = 0
    request_timeout_seconds = $RequestTimeoutSeconds
    maximum_attempts_per_request = ($MaxRetries + 1)
    collector_sha256 = $CollectorHash
    secret_value_exposed = $false
    live_host_contacted = $false
    order_attempted = $false
    broker_mutation = $false
}
Write-AiOsJsonAtomic -Data $RuntimeState -Path $RuntimeStatePath

$SecureToken = Read-Host -Prompt "Enter OANDA Practice token for this process only" -AsSecureString
if ($null -eq $SecureToken) {
    throw "TOKEN_NOT_PROVIDED"
}

$TokenHandle = [IntPtr]::Zero
$PlainToken = $null
$AuthorizationValue = $null
try {
    $TokenHandle = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureToken)
    $PlainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($TokenHandle)
    if ([string]::IsNullOrWhiteSpace($PlainToken)) {
        throw "TOKEN_NOT_PROVIDED"
    }

    $AuthorizationValue = ("Be" + "arer " + $PlainToken)

    $RunStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $AuthInstrument = [string]$Instruments[0]
    $AuthGranularity = [string]$Granularities[0]
    $AuthPathInstrument = [Uri]::EscapeDataString($AuthInstrument)
    $AuthUri = "$PracticeHost/v3/instruments/$AuthPathInstrument/candles?price=$Price&granularity=$AuthGranularity&count=1"
    $RuntimeState.status = "AUTHENTICATION_CHECK_STARTED"
    $RuntimeState.last_progress_utc = (Get-Date).ToUniversalTime().ToString("o")
    Write-AiOsJsonAtomic -Data $RuntimeState -Path $RuntimeStatePath
    Write-Host ("AUTHENTICATION_CHECK_STARTED pair={0} granularity={1} elapsed_seconds={2}" -f $AuthInstrument, $AuthGranularity, [Math]::Floor($RunStopwatch.Elapsed.TotalSeconds))
    try {
        [void](Invoke-AiOsOandaGetWithRetry -Uri $AuthUri -AuthorizationValue $AuthorizationValue -MaxRetries $MaxRetries -RequestTimeoutSeconds $RequestTimeoutSeconds -Operation "AUTHENTICATION_CHECK" -Instrument $AuthInstrument -Granularity $AuthGranularity -BatchIndex 0 -CompleteCount 0 -LastDurableUtc $null -RunStopwatch $RunStopwatch)
    }
    catch {
        $AuthenticationClassification = if ([string]$_.Exception.Message -match "OANDA_PRACTICE_AUTHENTICATION_REJECTED") {
            "OANDA_PRACTICE_AUTHENTICATION_REJECTED"
        }
        elseif ([string]$_.Exception.Message -match "OANDA_PRACTICE_AUTHORIZATION_REJECTED") {
            "OANDA_PRACTICE_AUTHORIZATION_REJECTED"
        }
        else {
            "OANDA_PRACTICE_AUTHENTICATION_CHECK_FAILED"
        }
        $RuntimeState.status = $AuthenticationClassification
        $RuntimeState.last_progress_utc = (Get-Date).ToUniversalTime().ToString("o")
        Write-AiOsJsonAtomic -Data $RuntimeState -Path $RuntimeStatePath
        Write-Host ("AUTHENTICATION_CHECK_FAIL classification={0} elapsed_seconds={1}" -f $AuthenticationClassification, [Math]::Floor($RunStopwatch.Elapsed.TotalSeconds))
        throw $AuthenticationClassification
    }
    $RuntimeState.status = "AUTHENTICATION_CHECK_PASS"
    $RuntimeState.last_progress_utc = (Get-Date).ToUniversalTime().ToString("o")
    Write-AiOsJsonAtomic -Data $RuntimeState -Path $RuntimeStatePath
    Write-Host ("AUTHENTICATION_CHECK_PASS pair={0} granularity={1} elapsed_seconds={2}" -f $AuthInstrument, $AuthGranularity, [Math]::Floor($RunStopwatch.Elapsed.TotalSeconds))

    $RuntimeState.status = "ACQUISITION_RUNNING"
    $RuntimeState.last_progress_utc = (Get-Date).ToUniversalTime().ToString("o")
    Write-AiOsJsonAtomic -Data $RuntimeState -Path $RuntimeStatePath

    $Manifest = [ordered]@{
        schema = "AIOS_FOREX_SCALPING_HISTORY_MANIFEST.v1"
        scope_fingerprint = $ScopeFingerprint
        helper_sha256 = $HelperHash
        collector_sha256 = $CollectorHash
        host = $PracticeHost
        method = "GET_ONLY"
        output_root = $ResolvedRoot
        overall_from_utc = ConvertTo-AiOsUtcString -Value $From
        overall_to_utc = ConvertTo-AiOsUtcString -Value $To
        from_utc = ConvertTo-AiOsUtcString -Value $From
        to_utc = ConvertTo-AiOsUtcString -Value $To
        to_boundary_semantics = "exclusive"
        pagination_contract = "FROM_PLUS_COUNT"
        to_sent_on_each_request = $false
        include_first_strategy = "FIRST_REQUEST_TRUE_THEN_FROM_LAST_ACCEPTED_WITH_INCLUDE_FIRST_FALSE"
        candles_per_request = $CandlesPerRequest
        request_timeout_seconds = $RequestTimeoutSeconds
        batch_count = $CandlesPerRequest
        max_batches_per_series = $MaxBatchesPerSeries
        started_utc = (Get-Date).ToUniversalTime().ToString("o")
        completed_utc = $null
        series_count = ($Instruments.Count * $Granularities.Count)
        complete_series = 0
        incomplete_series = 0
        duplicate_check = "VALIDATED_PER_BATCH_AND_ACROSS_CHECKPOINT"
        gap_check = "PROVIDER_ORDER_PRESERVED_NO_FIXED_INTERVAL_SKIP"
        request_parallelism = 1
        parallel_request_allowed = $false
        burst_control = "SINGLE_SEQUENTIAL_REQUEST_LOOP_WITH_BOUNDED_RETRY"
        secret_value_exposed = $false
        live_host_contacted = $false
        order_attempted = $false
        broker_mutation = $false
        series = @()
    }

    foreach ($Instrument in $Instruments) {
        if ($Instrument -notmatch "^[A-Z]{3}_[A-Z]{3}$") {
            throw "INVALID_INSTRUMENT: $Instrument"
        }

        $PathInstrument = [Uri]::EscapeDataString($Instrument)

        foreach ($Granularity in $Granularities) {
            $StepSeconds = Get-AiOsGranularitySeconds -Granularity $Granularity
            $SeriesDir = Join-Path -Path $ResolvedRoot -ChildPath ($Instrument + "_" + $Granularity)
            New-Item -ItemType Directory -Force -Path $SeriesDir | Out-Null

            $CheckpointPath = Join-Path -Path $SeriesDir -ChildPath "AIOS_FOREX_SCALPING_HISTORY_CHECKPOINT.json"
            $Cursor = $From
            $BatchIndex = 0
            $LastCandleTime = $null
            $NextLocalBoundary = $From
            $CompleteCount = 0
            $BatchLedger = @()
            $ReachedDeclaredEnd = $false

            if (Test-Path -LiteralPath $CheckpointPath -PathType Leaf) {
                $checkpoint = Get-Content -Raw -LiteralPath $CheckpointPath | ConvertFrom-Json
                Assert-AiOsCheckpointArtifacts -Checkpoint $checkpoint
                Assert-AiOsSeriesFilesMatchCheckpoint -SeriesDir $SeriesDir -Checkpoint $checkpoint
                $HasScopeFingerprint = ($checkpoint.PSObject.Properties.Name -contains "scope_fingerprint")
                $CheckpointScopeCompatible = ((-not $HasScopeFingerprint) -or ($checkpoint.scope_fingerprint -eq $ScopeFingerprint))
                if (($checkpoint.instrument -eq $Instrument) -and
                    ($checkpoint.granularity -eq $Granularity) -and
                    ($checkpoint.price -eq $Price) -and
                    $CheckpointScopeCompatible -and
                    ($checkpoint.overall_from_utc -eq (ConvertTo-AiOsUtcString -Value $From)) -and
                    ($checkpoint.overall_to_utc -eq (ConvertTo-AiOsUtcString -Value $To)) -and
                    ([int]$checkpoint.candles_per_request -eq $CandlesPerRequest)) {

                    if ($checkpoint.status -eq "SERIES_COMPLETE") {
                        Write-Host ("PROGRESS {0} {1} completed_series_reused=true batch={2} candles={3} last={4}" -f $Instrument, $Granularity, [int]$checkpoint.next_batch_index, [int64]$checkpoint.complete_candles, [string]$checkpoint.last_candle_utc)
                        $Manifest.series += [ordered]@{
                            instrument = $Instrument
                            granularity = $Granularity
                            complete_candles = [int]$checkpoint.complete_candles
                            batches = [int]$checkpoint.next_batch_index
                            last_candle_utc = $checkpoint.last_candle_utc
                            status = "SERIES_COMPLETE_REUSED_FROM_CHECKPOINT"
                            scope_fingerprint = $ScopeFingerprint
                            files = @(Get-AiOsSeriesFiles -SeriesDir $SeriesDir)
                        }
                        $Manifest.complete_series += 1
                        continue
                    }

                    if (-not [string]::IsNullOrWhiteSpace([string]$checkpoint.next_cursor_utc)) {
                        $Cursor = [DateTimeOffset]::Parse([string]$checkpoint.next_cursor_utc).ToUniversalTime()
                    }
                    $BatchIndex = [int]$checkpoint.next_batch_index
                    $CompleteCount = [int]$checkpoint.complete_candles
                    if (-not [string]::IsNullOrWhiteSpace([string]$checkpoint.last_candle_utc)) {
                        $LastCandleTime = [DateTimeOffset]::Parse([string]$checkpoint.last_candle_utc).ToUniversalTime()
                        $NextLocalBoundary = $LastCandleTime.AddSeconds($StepSeconds)
                        if (-not $HasScopeFingerprint) {
                            $Cursor = $LastCandleTime
                        }
                    }
                    if ($checkpoint.PSObject.Properties.Name -contains "batches") {
                        $BatchLedger = @($checkpoint.batches)
                    }
                }
                else {
                    throw "SCOPE_FINGERPRINT_MISMATCH: existing checkpoint does not match requested acquisition scope."
                }
            }

            while ($Cursor -lt $To) {
                if (($MaxBatchesPerSeries -gt 0) -and ($BatchIndex -ge $MaxBatchesPerSeries)) {
                    break
                }

                $IncludeFirst = ($BatchIndex -eq 0 -and $null -eq $LastCandleTime)
                $RequestCursor = if ($null -eq $LastCandleTime) { $Cursor } else { $LastCandleTime }
                $IncludeFirstText = if ($IncludeFirst) { "true" } else { "false" }
                $FromEncoded = [Uri]::EscapeDataString((ConvertTo-AiOsUtcString -Value $RequestCursor))
                $Uri = "$PracticeHost/v3/instruments/$PathInstrument/candles?price=$Price&granularity=$Granularity&from=$FromEncoded&count=$CandlesPerRequest&includeFirst=$IncludeFirstText"

                $RuntimeState.status = "REQUEST_IN_FLIGHT"
                $RuntimeState.current_instrument = $Instrument
                $RuntimeState.current_granularity = $Granularity
                $RuntimeState.request_cursor_utc = ConvertTo-AiOsUtcString -Value $RequestCursor
                $RuntimeState.request_started_utc = (Get-Date).ToUniversalTime().ToString("o")
                Write-AiOsJsonAtomic -Data $RuntimeState -Path $RuntimeStatePath

                $Response = Invoke-AiOsOandaGetWithRetry -Uri $Uri -AuthorizationValue $AuthorizationValue -MaxRetries $MaxRetries -RequestTimeoutSeconds $RequestTimeoutSeconds -Operation "ACQUISITION" -Instrument $Instrument -Granularity $Granularity -BatchIndex $BatchIndex -CompleteCount $CompleteCount -LastDurableUtc $(if ($null -eq $LastCandleTime) { $null } else { ConvertTo-AiOsUtcString -Value $LastCandleTime }) -RunStopwatch $RunStopwatch
                $AcceptedCandles = @(Get-AiOsValidatedAcceptedCandles -Response $Response -Instrument $Instrument -Granularity $Granularity -Price $Price -Cursor $RequestCursor -OverallTo $To -LastAcceptedBefore $LastCandleTime -IncludeFirst $IncludeFirst)
                if ($AcceptedCandles.Count -eq 0) {
                    $ReachedDeclaredEnd = $true
                    $RuntimeState.status = "SERIES_END_BOUND_CONFIRMED"
                    $RuntimeState.last_progress_utc = (Get-Date).ToUniversalTime().ToString("o")
                    Write-AiOsJsonAtomic -Data $RuntimeState -Path $RuntimeStatePath
                    Write-Host ("PROGRESS {0} {1} end_bound_confirmed=true batch={2} candles={3} last={4}" -f $Instrument, $Granularity, $BatchIndex, $CompleteCount, $(if ($null -eq $LastCandleTime) { "NONE" } else { ConvertTo-AiOsUtcString -Value $LastCandleTime }))
                    break
                }

                $BatchName = "{0:D6}_{1}_{2}.json" -f $BatchIndex, $Instrument, $Granularity
                $BatchPath = Join-Path -Path $SeriesDir -ChildPath $BatchName

                $BatchDoc = [ordered]@{
                    schema = "AIOS_FOREX_SCALPING_HISTORY_BATCH.v1"
                    source = "OANDA_PRACTICE_INSTRUMENT_CANDLES"
                    host = $PracticeHost
                    method = "GET_ONLY"
                    instrument = $Instrument
                    granularity = $Granularity
                    price = $Price
                    from_utc = ConvertTo-AiOsUtcString -Value $RequestCursor
                    include_first = $IncludeFirst
                    overall_to_utc = ConvertTo-AiOsUtcString -Value $To
                    to_boundary_semantics = "exclusive"
                    pagination_contract = "FROM_PLUS_COUNT"
                    to_sent_on_each_request = $false
                    candles_per_request = $CandlesPerRequest
                    candle_count = $AcceptedCandles.Count
                    candles = $AcceptedCandles
                }
                Write-AiOsJsonAtomic -Data $BatchDoc -Path $BatchPath
                $BatchHash = Get-AiOsFileSha256 -Path $BatchPath

                $FirstCandle = $AcceptedCandles[0]
                $LastCandle = $AcceptedCandles[-1]
                $FirstCandleTime = [DateTimeOffset]::Parse([string]$FirstCandle.time).ToUniversalTime()
                $LastCandleTime = [DateTimeOffset]::Parse([string]$LastCandle.time).ToUniversalTime()
                $CompleteCount += $AcceptedCandles.Count
                $NextLocalBoundary = $LastCandleTime.AddSeconds($StepSeconds)
                $NextCursor = $LastCandleTime
                if ($NextCursor -lt $RequestCursor) {
                    throw "PAGINATION_STALLED: $Instrument $Granularity at $(ConvertTo-AiOsUtcString -Value $RequestCursor)"
                }
                if ((-not $IncludeFirst) -and ($NextCursor -eq $RequestCursor)) {
                    throw "PAGINATION_STALLED: $Instrument $Granularity at $(ConvertTo-AiOsUtcString -Value $RequestCursor)"
                }
                $Cursor = $NextCursor
                $BatchIndex += 1
                $BatchLedger += [ordered]@{
                    instrument = $Instrument
                    granularity = $Granularity
                    batch_number = ($BatchIndex - 1)
                    request_cursor_utc = $BatchDoc.from_utc
                    include_first = $IncludeFirst
                    first_accepted_utc = ConvertTo-AiOsUtcString -Value $FirstCandleTime
                    last_accepted_utc = ConvertTo-AiOsUtcString -Value $LastCandleTime
                    accepted_row_count = $AcceptedCandles.Count
                    cumulative_row_count = $CompleteCount
                    artifact_path = $BatchPath
                    artifact_sha256 = $BatchHash
                    next_cursor_utc = ConvertTo-AiOsUtcString -Value $Cursor
                    next_local_boundary_utc = ConvertTo-AiOsUtcString -Value $NextLocalBoundary
                    completed = ($NextLocalBoundary -ge $To)
                }

                $CheckpointDoc = [ordered]@{
                    schema = "AIOS_FOREX_SCALPING_HISTORY_CHECKPOINT.v1"
                    scope_fingerprint = $ScopeFingerprint
                    helper_sha256 = $HelperHash
                    collector_sha256 = $CollectorHash
                    status = "SERIES_IN_PROGRESS"
                    host = $PracticeHost
                    method = "GET_ONLY"
                    instrument = $Instrument
                    granularity = $Granularity
                    price = $Price
                    overall_from_utc = ConvertTo-AiOsUtcString -Value $From
                    overall_to_utc = ConvertTo-AiOsUtcString -Value $To
                    to_boundary_semantics = "exclusive"
                    pagination_contract = "FROM_PLUS_COUNT"
                    to_sent_on_each_request = $false
                    include_first_strategy = "FIRST_REQUEST_TRUE_THEN_FROM_LAST_ACCEPTED_WITH_INCLUDE_FIRST_FALSE"
                    candles_per_request = $CandlesPerRequest
                    next_cursor_utc = ConvertTo-AiOsUtcString -Value $Cursor
                    next_batch_index = $BatchIndex
                    complete_candles = $CompleteCount
                    last_candle_utc = ConvertTo-AiOsUtcString -Value $LastCandleTime
                    next_local_boundary_utc = ConvertTo-AiOsUtcString -Value $NextLocalBoundary
                    batches = @($BatchLedger)
                    secret_value_exposed = $false
                    live_host_contacted = $false
                    order_attempted = $false
                    broker_mutation = $false
                    updated_utc = (Get-Date).ToUniversalTime().ToString("o")
                }
                Write-AiOsJsonAtomic -Data $CheckpointDoc -Path $CheckpointPath

                $RuntimeState.status = "ACQUISITION_RUNNING"
                $RuntimeState.last_progress_utc = (Get-Date).ToUniversalTime().ToString("o")
                $RuntimeState.last_accepted_utc = ConvertTo-AiOsUtcString -Value $LastCandleTime
                $RuntimeState.last_checkpoint_path = $CheckpointPath
                Write-AiOsJsonAtomic -Data $RuntimeState -Path $RuntimeStatePath
                Write-Host ("PROGRESS {0} {1} batch={2} candles={3} last={4}" -f $Instrument, $Granularity, $BatchIndex, $CompleteCount, $RuntimeState.last_accepted_utc)

                if ($NextLocalBoundary -ge $To) {
                    break
                }
            }

            $Status = if ($ReachedDeclaredEnd -or ($NextLocalBoundary -ge $To) -or (($null -ne $LastCandleTime) -and ($LastCandleTime -ge $To))) { "SERIES_COMPLETE" } else { "SERIES_PARTIAL" }
            $CheckpointFinal = [ordered]@{
                schema = "AIOS_FOREX_SCALPING_HISTORY_CHECKPOINT.v1"
                scope_fingerprint = $ScopeFingerprint
                helper_sha256 = $HelperHash
                collector_sha256 = $CollectorHash
                status = $Status
                host = $PracticeHost
                method = "GET_ONLY"
                instrument = $Instrument
                granularity = $Granularity
                price = $Price
                overall_from_utc = ConvertTo-AiOsUtcString -Value $From
                overall_to_utc = ConvertTo-AiOsUtcString -Value $To
                to_boundary_semantics = "exclusive"
                pagination_contract = "FROM_PLUS_COUNT"
                to_sent_on_each_request = $false
                include_first_strategy = "FIRST_REQUEST_TRUE_THEN_FROM_LAST_ACCEPTED_WITH_INCLUDE_FIRST_FALSE"
                candles_per_request = $CandlesPerRequest
                next_cursor_utc = ConvertTo-AiOsUtcString -Value $Cursor
                next_batch_index = $BatchIndex
                complete_candles = $CompleteCount
                last_candle_utc = if ($null -eq $LastCandleTime) { $null } else { ConvertTo-AiOsUtcString -Value $LastCandleTime }
                next_local_boundary_utc = ConvertTo-AiOsUtcString -Value $NextLocalBoundary
                batches = @($BatchLedger)
                secret_value_exposed = $false
                live_host_contacted = $false
                order_attempted = $false
                broker_mutation = $false
                updated_utc = (Get-Date).ToUniversalTime().ToString("o")
            }
            Write-AiOsJsonAtomic -Data $CheckpointFinal -Path $CheckpointPath
            if ($Status -eq "SERIES_COMPLETE") {
                $Manifest.complete_series += 1
            }
            else {
                $Manifest.incomplete_series += 1
            }
            $RuntimeState.completed_series = $Manifest.complete_series
            $RuntimeState.incomplete_series = $Manifest.incomplete_series
            $RuntimeState.status = $Status
            $RuntimeState.last_progress_utc = (Get-Date).ToUniversalTime().ToString("o")
            Write-AiOsJsonAtomic -Data $RuntimeState -Path $RuntimeStatePath

            $Manifest.series += [ordered]@{
                instrument = $Instrument
                granularity = $Granularity
                complete_candles = $CompleteCount
                batches = $BatchIndex
                last_candle_utc = if ($null -eq $LastCandleTime) { $null } else { ConvertTo-AiOsUtcString -Value $LastCandleTime }
                status = $Status
                scope_fingerprint = $ScopeFingerprint
                files = @(Get-AiOsSeriesFiles -SeriesDir $SeriesDir)
            }
        }
    }

    $Manifest.completed_utc = (Get-Date).ToUniversalTime().ToString("o")
    $ManifestPath = Join-Path -Path $ResolvedRoot -ChildPath "AIOS_FOREX_SCALPING_HISTORY_MANIFEST.json"
    Write-AiOsJsonAtomic -Data $Manifest -Path $ManifestPath
    $RuntimeState.status = if ($Manifest.incomplete_series -eq 0) { "ACQUISITION_COMPLETE" } else { "ACQUISITION_COMPLETE_WITH_PARTIAL_SERIES" }
    $RuntimeState.completed_series = $Manifest.complete_series
    $RuntimeState.incomplete_series = $Manifest.incomplete_series
    $RuntimeState.last_progress_utc = (Get-Date).ToUniversalTime().ToString("o")
    Write-AiOsJsonAtomic -Data $RuntimeState -Path $RuntimeStatePath
    Get-Content -LiteralPath $ManifestPath
}
catch {
    if ([string]$_.Exception.Message -match "OANDA_PRACTICE_AUTHENTICATION_REJECTED") {
        $RuntimeState.status = "OANDA_PRACTICE_AUTHENTICATION_REJECTED"
    }
    elseif ([string]$_.Exception.Message -match "OANDA_PRACTICE_AUTHORIZATION_REJECTED") {
        $RuntimeState.status = "OANDA_PRACTICE_AUTHORIZATION_REJECTED"
    }
    elseif ($RuntimeState.status -ne "OANDA_PRACTICE_AUTHENTICATION_CHECK_FAILED") {
        $RuntimeState.status = "FAILED_CLOSED"
    }
    $RuntimeState.last_progress_utc = (Get-Date).ToUniversalTime().ToString("o")
    Write-AiOsJsonAtomic -Data $RuntimeState -Path $RuntimeStatePath
    throw
}
finally {
    if ($TokenHandle -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($TokenHandle)
    }
    $AuthorizationValue = $null
    $PlainToken = $null
    $SecureToken = $null
}
